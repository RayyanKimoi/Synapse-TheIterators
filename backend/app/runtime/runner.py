"""SSE telemetry stream, driven by the live Ready-Node scheduler.

Frames are no longer a replay of a precomputed tier schedule. Both pipelines
run through `compiler.scheduler.run_ready_nodes`; a node is reported RUNNING
when a worker actually picks it up and COMPLETED when that worker finishes it.

The baseline pipeline executes the same way over a *chain* graph, which is what
makes it serial — one code path, and the arena race is a genuine comparison of
two dispatch topologies rather than two arithmetic formulas.

Reported latencies still come from the deterministic profile, so the numbers
are reproducible on stage. Swapping the `work` coroutine for real LLM calls is
the only change needed to put live models behind this contract.
"""

import asyncio
import time
import uuid
from collections.abc import AsyncIterator

import networkx as nx

from ..compiler.dag import assert_acyclic, baseline_sequence, build_graph
from ..compiler.scheduler import NodeTiming, ready_node_timings, run_ready_nodes
from ..config import get_settings
from ..models.ir import WorkflowIR
from ..models.telemetry import (
    AggregateMetrics,
    CircuitBreakerStatus,
    NodeStatus,
    NodeTelemetry,
    PipelineType,
    RunSummary,
    TelemetryFrame,
)
from .profile import (
    FRESH_SINK_LATENCY_MS,
    NodeWork,
    ScheduledNode,
    baseline_reference_costs,
    build_node_work,
)

# A later phase replaces these with measured semantic-invariance scores.
BASELINE_CORRECTNESS_SCORE = 1.0
COMPILED_CORRECTNESS_SCORE = 0.982


def _warm_cache_plan(graph: nx.DiGraph) -> tuple[set[str], dict[str, int]]:
    """Act 4 of the demo: every upstream node is served from the semantic cache,
    and the terminal node only has to compose a short answer from cached context
    for the paraphrased query."""
    cached = {node for node in graph.nodes if graph.out_degree(node) > 0}
    sink_caps = {
        node: FRESH_SINK_LATENCY_MS for node in graph.nodes if graph.out_degree(node) == 0
    }
    return cached, sink_caps


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
    done: dict[str, ScheduledNode],
    running: dict[str, int],
    elapsed_ms: int,
    budget_limit_usd: float,
    reference_costs: dict[str, float],
) -> TelemetryFrame:
    states: dict[str, NodeTelemetry] = {}
    active: list[str] = []
    tokens = 0
    cost = 0.0
    avoided = 0.0

    for node in workflow.nodes:
        node_id = node.id
        if node_id in done:
            entry = done[node_id]
            tokens += entry.tokens
            cost += entry.cost_usd
            # Cost avoided is booked per node as it finishes, so the scoreboard
            # ticker only ever counts up.
            avoided += max(reference_costs.get(node_id, 0.0) - entry.cost_usd, 0.0)
            states[node_id] = NodeTelemetry(
                status=NodeStatus.CACHED if entry.cache_hit else NodeStatus.COMPLETED,
                latency_ms=entry.duration_ms,
                tokens_consumed=entry.tokens,
                cost_usd=entry.cost_usd,
                is_cache_hit=entry.cache_hit,
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

    cost = round(cost, 6)
    metrics = AggregateMetrics(
        total_tokens=tokens,
        total_cost_usd=cost,
        projected_cost_saved_usd=round(avoided, 6),
        circuit_breaker_status=(
            CircuitBreakerStatus.TRIGGERED
            if cost > budget_limit_usd
            else CircuitBreakerStatus.NORMAL
        ),
        correctness_score=(
            (
                BASELINE_CORRECTNESS_SCORE
                if mode is PipelineType.BASELINE
                else COMPILED_CORRECTNESS_SCORE
            )
            if (done or running)
            else 0.0
        ),
    )

    return TelemetryFrame(
        run_id=run_id,
        pipeline_type=mode,
        timestamp_ms=int(time.time() * 1000),
        elapsed_pipeline_ms=elapsed_ms,
        active_nodes=active,
        node_states=states,
        aggregate_metrics=metrics,
    )


async def stream_telemetry(
    workflow: WorkflowIR,
    *,
    mode: PipelineType = PipelineType.COMPILED,
    cache_warm: bool = False,
    tick_ms: int = 100,
    time_scale: float = 1.0,
    run_id: str | None = None,
) -> AsyncIterator[dict[str, str]]:
    """Yield sse-starlette event dicts until the run completes.

    `time_scale` compresses wall-clock time without altering reported
    latencies — 50.0 replays a 35 s baseline in 0.7 s for tests and rehearsal.
    """
    run_id = run_id or f"run_{uuid.uuid4().hex[:8]}"
    settings = get_settings()

    graph = build_graph(workflow)
    assert_acyclic(graph)
    cached, caps = _warm_cache_plan(graph) if cache_warm else (set(), {})

    compiled = mode is PipelineType.COMPILED
    work: dict[str, NodeWork] = build_node_work(
        workflow, graph, compiled=compiled, cached_ids=cached, duration_caps_ms=caps
    )

    # Compiled dispatches over the real DAG; baseline over a chain of the same
    # nodes, so the only difference between the two runs is graph topology.
    execution_graph = (
        graph
        if compiled
        else _serial_graph(baseline_sequence(graph, workflow.declaration_index()))
    )

    def duration_of(node_id: str) -> int:
        return work[node_id].duration_ms

    total_ms = max(
        (
            timing.end_ms
            for timing in ready_node_timings(execution_graph, duration_of).values()
        ),
        default=0,
    )
    reference_costs = baseline_reference_costs(workflow)

    done: dict[str, ScheduledNode] = {}
    running: dict[str, int] = {}

    def on_start(node_id: str, start_ms: int) -> None:
        running[node_id] = start_ms

    def on_complete(timing: NodeTiming) -> None:
        running.pop(timing.node_id, None)
        entry = work[timing.node_id]
        done[timing.node_id] = ScheduledNode(
            timing.node_id,
            timing.start_ms,
            entry.duration_ms,
            entry.tokens,
            entry.cost_usd,
            entry.cache_hit,
        )

    async def do_work(_node_id: str, duration_ms: int) -> None:
        await asyncio.sleep(duration_ms / 1000 / time_scale)

    started = time.perf_counter()
    runner = asyncio.create_task(
        run_ready_nodes(
            execution_graph,
            duration_ms=duration_of,
            max_concurrency=settings.max_concurrent_tasks,
            work=do_work,
            on_start=on_start,
            on_complete=on_complete,
        )
    )

    try:
        while True:
            wall_ms = int((time.perf_counter() - started) * 1000)
            elapsed_ms = min(int(wall_ms * time_scale), total_ms)
            frame = _frame(
                run_id,
                mode,
                workflow,
                done,
                running,
                elapsed_ms,
                workflow.budget_limit_usd,
                reference_costs,
            )
            yield {"event": "telemetry_update", "data": frame.model_dump_json()}
            if runner.done() and elapsed_ms >= total_ms:
                break
            await asyncio.sleep(tick_ms / 1000)
        await runner
    finally:
        if not runner.done():
            runner.cancel()

    summary = RunSummary(
        run_id=run_id,
        pipeline_type=mode,
        total_elapsed_ms=total_ms,
        wall_clock_ms=int((time.perf_counter() - started) * 1000),
        node_count=len(work),
        cache_hits=sum(1 for state in frame.node_states.values() if state.is_cache_hit),
        aggregate_metrics=frame.aggregate_metrics,
    )
    yield {"event": "run_complete", "data": summary.model_dump_json()}
