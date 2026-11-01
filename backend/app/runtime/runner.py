"""SSE telemetry stream for one pipeline run.

Both pipelines run through `compiler.scheduler.run_ready_nodes` with a
`NodeExecutor` as the work coroutine: LLM nodes call the LiteLLM gateway under
the run's budget, and a tripped circuit breaker halts everything downstream of
the failing node. The baseline executes over a *chain* graph, which is what
makes it serial — one code path, so the arena race compares two dispatch
topologies rather than two formulas.

When no model is in the loop (offline mode, or a live call that fell back to the
mock), node latency comes from the deterministic profile, so the race is
reproducible on stage. Once the last node terminates the IR contract is
evaluated and carried on the final frame and on `run_complete`.
"""

import asyncio
import math
import time
import uuid
from collections import Counter
from collections.abc import AsyncIterator
from typing import get_args

import networkx as nx

from .. import alerts
from ..compiler.dag import assert_acyclic, baseline_sequence, build_graph
from ..compiler.planner import (
    graph_without_rejected_parallelism,
    nodes_denied_concurrency,
)
from ..compiler.scheduler import NodeTiming, ready_node_timings, run_ready_nodes
from ..config import Settings, get_settings
from ..llm.cache import SemanticCache, get_cache
from ..llm.gateway import Guardrails, LLMGateway, LLMSource, RunBudget
from ..models.ir import WorkflowIR
from ..models.telemetry import (
    AggregateMetrics,
    CircuitBreakerStatus,
    ContractReport,
    NodeStatus,
    NodeTelemetry,
    PipelineType,
    RunSummary,
    TelemetryFrame,
)
from .contract import evaluate_contract, final_payload
from .executor import NodeExecutor, NodeOutcome
from .fusion import plan_fusion
from .paste import TransitionMatrix, get_matrix, observed_edges, prefetchable
from .profile import NodeWork, baseline_reference_costs, build_node_work

LLM_SOURCES = frozenset(get_args(LLMSource))

# A priming pass only has to populate the cache, so its simulated latency is
# collapsed to effectively zero.
PRIME_TIME_SCALE = 1e6


def _serial_graph(sequence: list[str]) -> nx.DiGraph:
    """A chain over the baseline order: every node waits for the previous one."""
    chain = nx.DiGraph()
    chain.add_nodes_from(sequence)
    for before, after in zip(sequence, sequence[1:]):
        chain.add_edge(before, after)
    return chain


def _frame(
    run_id: str,
    mode: PipelineType,
    workflow: WorkflowIR,
    *,
    outcomes: dict[str, NodeOutcome],
    done: dict[str, NodeTiming],
    running: dict[str, int],
    halted: dict[str, str],
    elapsed_ms: int,
    budget: RunBudget,
    reference_costs: dict[str, float],
    contract: ContractReport | None = None,
) -> TelemetryFrame:
    states: dict[str, NodeTelemetry] = {}
    active: list[str] = []
    tokens = 0
    cost = 0.0
    avoided = 0.0

    for node in workflow.nodes:
        node_id = node.id
        timing = done.get(node_id)
        if timing is not None and not timing.failed:
            outcome = outcomes[node_id]
            tokens += outcome.tokens
            cost += outcome.cost_usd
            if outcome.cache_hit:
                # A hit avoids the cost of the call it replaced.
                avoided += reference_costs.get(node_id, 0.0)
            states[node_id] = NodeTelemetry(
                status=NodeStatus.CACHED if outcome.cache_hit else NodeStatus.COMPLETED,
                latency_ms=timing.end_ms - timing.start_ms,
                tokens_consumed=outcome.tokens,
                cost_usd=outcome.cost_usd,
                is_cache_hit=outcome.cache_hit,
            )
        elif timing is not None:
            states[node_id] = NodeTelemetry(
                status=NodeStatus.FAILED, error=outcomes[node_id].error
            )
        elif node_id in halted:
            states[node_id] = NodeTelemetry(
                status=NodeStatus.FAILED,
                error=f"halted: upstream node '{halted[node_id]}' failed",
            )
        elif node_id in running:
            # Tokens and cost are only booked on completion, matching the
            # section 8.2 sample where RUNNING nodes report zero.
            active.append(node_id)
            states[node_id] = NodeTelemetry(
                status=NodeStatus.RUNNING,
                latency_ms=max(elapsed_ms - running[node_id], 0),
            )
        else:
            states[node_id] = NodeTelemetry()

    metrics = AggregateMetrics(
        total_tokens=tokens,
        total_cost_usd=round(cost, 6),
        projected_cost_saved_usd=round(avoided, 6),
        circuit_breaker_status=(
            CircuitBreakerStatus.TRIGGERED if budget.tripped else CircuitBreakerStatus.NORMAL
        ),
        # Certified only once the run has finished; see contract.evaluate_contract.
        correctness_score=(contract.semantic_invariance or 0.0) if contract else 0.0,
        budget_limit_usd=budget.limit_usd if math.isfinite(budget.limit_usd) else 0.0,
    )

    return TelemetryFrame(
        run_id=run_id,
        pipeline_type=mode,
        timestamp_ms=int(time.time() * 1000),
        elapsed_pipeline_ms=elapsed_ms,
        active_nodes=active,
        node_states=states,
        aggregate_metrics=metrics,
        contract=contract,
    )


async def stream_telemetry(
    workflow: WorkflowIR,
    *,
    mode: PipelineType = PipelineType.COMPILED,
    cache_warm: bool = False,
    tick_ms: int = 100,
    time_scale: float = 1.0,
    run_id: str | None = None,
    query: str | None = None,
    cache: SemanticCache | None = None,
    matrix: TransitionMatrix | None = None,
    disabled: frozenset[str] = frozenset(),
) -> AsyncIterator[dict[str, str]]:
    """Yield sse-starlette event dicts until the run completes.

    `time_scale` compresses simulated latency without altering reported
    latencies — 50.0 replays a 35 s baseline in 0.7 s for tests and rehearsal.
    With live models in the loop it is forced to 1.0: a real call cannot be
    replayed faster.
    """
    run_id = run_id or f"run_{uuid.uuid4().hex[:8]}"
    settings = get_settings()
    if not settings.llm_offline_mode:
        time_scale = 1.0

    graph = build_graph(workflow)
    assert_acyclic(graph)

    compiled = mode is PipelineType.COMPILED
    matrix = matrix if matrix is not None else get_matrix()
    # Only the compiled pipeline speculates; the baseline is the unoptimised
    # control, and giving it PASTE would erase what the arena is comparing.
    prefetch = (
        prefetchable(graph, workflow.node_map(), await matrix.snapshot())
        if compiled
        else frozenset()
    )
    # A pass the developer swiped left on is not applied. The Matchmaker is a
    # control surface, so a rejection has to change what actually runs.
    serial_only = nodes_denied_concurrency(graph, disabled)
    prefetch = frozenset(
        node
        for node in prefetch
        if f"opt_prefetch_{node}" not in disabled and node not in serial_only
    )
    # Fusion is a compiler pass, so the unoptimised baseline does not get it.
    fusion = plan_fusion(workflow, graph) if compiled else {}
    fusion = {
        member: group
        for member, group in fusion.items()
        if f"opt_fusion_{group.leader}" not in disabled
    }
    plan = build_node_work(
        workflow, graph, compiled=compiled, prefetch=prefetch, fusion=fusion
    )
    guardrails = Guardrails.resolve(workflow, settings)
    budget = RunBudget(limit_usd=guardrails.budget_limit_usd)
    gateway = LLMGateway(settings)
    cache = cache if cache is not None else get_cache()
    query = query or workflow.name

    if cache_warm:
        await _prime_cache(
            workflow, graph, plan, gateway, cache, mode.value, query, settings
        )

    executor = NodeExecutor(
        workflow,
        graph,
        plan,
        gateway=gateway,
        cache=cache,
        scope=mode.value,
        budget=budget,
        query=query,
        time_scale=time_scale,
        prefetch=prefetch,
        fusion=fusion,
    )

    # Compiled dispatches over the real DAG; baseline over a chain of the same
    # nodes, so the only difference between the two runs is graph topology.
    execution_graph = (
        graph_without_rejected_parallelism(graph, disabled)
        if compiled
        else _serial_graph(baseline_sequence(graph, workflow.declaration_index()))
    )

    # Offline, every duration is known up front, which bounds the clock so it
    # never runs ahead of the work between frames.
    clock_cap = (
        max(
            timing.end_ms
            for timing in ready_node_timings(
                execution_graph, lambda node_id: plan[node_id].duration_ms
            ).values()
        )
        if settings.llm_offline_mode
        else None
    )
    reference_costs = baseline_reference_costs(workflow)

    done: dict[str, NodeTiming] = {}
    running: dict[str, int] = {}
    halted: dict[str, str] = {}

    def on_start(node_id: str, start_ms: int) -> None:
        running[node_id] = start_ms

    def on_complete(timing: NodeTiming) -> None:
        running.pop(timing.node_id, None)
        done[timing.node_id] = timing

    def on_skip(nodes: frozenset[str], failed_node: str) -> None:
        for node_id in nodes:
            halted[node_id] = failed_node

    def frame(elapsed_ms: int, contract: ContractReport | None = None) -> TelemetryFrame:
        return _frame(
            run_id,
            mode,
            workflow,
            outcomes=executor.outcomes,
            done=done,
            running=running,
            halted=halted,
            elapsed_ms=elapsed_ms,
            budget=budget,
            reference_costs=reference_costs,
            contract=contract,
        )

    started = time.perf_counter()
    runner = asyncio.create_task(
        run_ready_nodes(
            execution_graph,
            work=executor,
            max_concurrency=settings.max_concurrent_tasks,
            on_start=on_start,
            on_complete=on_complete,
            on_skip=on_skip,
        )
    )

    shown_ms = 0
    try:
        while not runner.done():
            elapsed_ms = int((time.perf_counter() - started) * 1000 * time_scale)
            if clock_cap is not None:
                elapsed_ms = min(elapsed_ms, clock_cap)
            shown_ms = max(shown_ms, elapsed_ms)
            yield {"event": "telemetry_update", "data": frame(shown_ms).model_dump_json()}
            await asyncio.wait({runner}, timeout=tick_ms / 1000)
        await runner
    finally:
        if not runner.done():
            runner.cancel()
        await executor.aclose()

    total_ms = max((timing.end_ms for timing in done.values()), default=0)
    sinks = [node for node in graph.nodes if graph.out_degree(node) == 0]
    payload = final_payload(
        {
            node: executor.outcomes[node].output
            for node in sinks
            if node in done and not done[node].failed
        }
    )
    contract = evaluate_contract(
        workflow,
        guardrails,
        payload=payload,
        latency_ms=total_ms,
        cache_hits={
            # `or 0.0` is fail-closed: an unmeasured hit must not certify a run.
            node: outcome.cache_similarity or 0.0
            for node, outcome in executor.outcomes.items()
            if outcome.cache_hit
        },
        halted=bool(halted) or any(timing.failed for timing in done.values()),
    )
    final = frame(total_ms, contract)
    yield {"event": "telemetry_update", "data": final.model_dump_json()}

    # Slack, best-effort and fire-and-forget. Once per halted run, not once per
    # node: a halt has a single root cause and the nodes downstream of it only
    # echo that. Posted after the failure is on the stream, so the dashboard is
    # already truthful by the time anyone follows the link.
    failed = next((node for node, timing in done.items() if timing.failed), None)
    if failed is not None or budget.tripped:
        error = executor.outcomes[failed].error if failed is not None else None
        alerts.notify(
            run_id=run_id,
            failed_node=failed or "n/a",
            reason=error or ("Budget exceeded" if budget.tripped else "Unhandled failure"),
            spent_usd=budget.spent_usd,
            budget_usd=budget.limit_usd if math.isfinite(budget.limit_usd) else 0.0,
            breaker=budget.tripped,
        )

    # History for the next run: the declared DAG, not the chain the baseline
    # executed over.
    executed = [node for node, timing in done.items() if not timing.failed]
    await matrix.record_run(executed, observed_edges(graph, executed))

    summary = RunSummary(
        run_id=run_id,
        pipeline_type=mode,
        total_elapsed_ms=total_ms,
        wall_clock_ms=int((time.perf_counter() - started) * 1000),
        node_count=len(workflow.nodes),
        cache_hits=sum(1 for state in final.node_states.values() if state.is_cache_hit),
        aggregate_metrics=final.aggregate_metrics,
        contract=contract,
        final_output=payload,
        llm_calls=dict(
            Counter(
                outcome.source
                for outcome in executor.outcomes.values()
                if outcome.source in LLM_SOURCES
            )
        ),
    )
    yield {"event": "run_complete", "data": summary.model_dump_json()}


async def _prime_cache(
    workflow: WorkflowIR,
    graph: nx.DiGraph,
    plan: dict[str, NodeWork],
    gateway: LLMGateway,
    cache: SemanticCache,
    scope: str,
    query: str,
    settings: Settings,
) -> None:
    """Act 4 of the demo: `cache_warm` means this workflow has genuinely been
    run before, so run it once -- with the simulated latency collapsed -- and
    let the measured run find the vectors it left behind.

    Terminal nodes are left out: the arena needs a visible finish line, and a
    fully cached run would report a zero-millisecond clock. Everything upstream
    of the answer is warm; composing the answer itself is still real work.

    Priming carries its own unlimited budget: the breaker belongs to the run
    being measured, not to the history behind it.
    """
    await run_ready_nodes(
        graph,
        work=NodeExecutor(
            workflow,
            graph,
            plan,
            gateway=gateway,
            cache=cache,
            scope=scope,
            budget=RunBudget(limit_usd=math.inf),
            prime=True,
            query=query,
            time_scale=PRIME_TIME_SCALE,
        ),
        max_concurrency=settings.max_concurrent_tasks,
    )
