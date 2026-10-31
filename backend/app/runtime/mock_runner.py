"""Deterministic SSE telemetry source (PRD section 8.2).

Emits a `telemetry_update` frame every `tick_ms` and one terminal
`run_complete` summary. Node timing comes from a schedule computed up front,
then replayed against the wall clock, so the stopwatches in the arena are real
while the numbers stay reproducible.

Phase 3 swaps this for the live `asyncio.gather` engine behind the same event
contract, which is what lets the frontend be built against it today.
"""

import asyncio
import time
import uuid
from collections.abc import AsyncIterator

import networkx as nx

from ..compiler.dag import (
    assert_acyclic,
    baseline_sequence,
    build_graph,
    execution_tiers,
    topological_depths,
)
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
    ScheduledNode,
    baseline_reference_costs,
    build_baseline_schedule,
    build_compiled_schedule,
    schedule_latency_ms,
)

# Phase 6 replaces these with measured semantic-invariance scores.
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


def build_schedule(
    workflow: WorkflowIR, mode: PipelineType, cache_warm: bool
) -> dict[str, ScheduledNode]:
    graph = build_graph(workflow)
    assert_acyclic(graph)
    cached, caps = _warm_cache_plan(graph) if cache_warm else (set(), {})

    if mode is PipelineType.COMPILED:
        tiers = execution_tiers(workflow, topological_depths(graph))
        return build_compiled_schedule(workflow, tiers, cached, caps)

    sequence = baseline_sequence(graph, workflow.declaration_index())
    return build_baseline_schedule(workflow, sequence, cached, caps)


def _frame(
    run_id: str,
    mode: PipelineType,
    scheduled: dict[str, ScheduledNode],
    elapsed_ms: int,
    budget_limit_usd: float,
    reference_costs: dict[str, float],
) -> TelemetryFrame:
    states: dict[str, NodeTelemetry] = {}
    active: list[str] = []
    tokens = 0
    cost = 0.0
    avoided = 0.0

    for node_id, entry in scheduled.items():
        if elapsed_ms < entry.start_ms:
            states[node_id] = NodeTelemetry()
        elif elapsed_ms >= entry.end_ms:
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
        else:
            # Tokens and cost are only booked on completion, matching the
            # section 8.2 sample where RUNNING nodes report zero.
            active.append(node_id)
            states[node_id] = NodeTelemetry(
                status=NodeStatus.RUNNING, latency_ms=elapsed_ms - entry.start_ms
            )

    started = any(state.status is not NodeStatus.IDLE for state in states.values())
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
            if started
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
    scheduled = build_schedule(workflow, mode, cache_warm)
    total_ms = schedule_latency_ms(scheduled)
    reference_costs = baseline_reference_costs(workflow)

    started = time.perf_counter()
    while True:
        wall_ms = int((time.perf_counter() - started) * 1000)
        elapsed_ms = min(int(wall_ms * time_scale), total_ms)
        frame = _frame(
            run_id, mode, scheduled, elapsed_ms, workflow.budget_limit_usd, reference_costs
        )
        yield {"event": "telemetry_update", "data": frame.model_dump_json()}
        if elapsed_ms >= total_ms:
            break
        await asyncio.sleep(tick_ms / 1000)

    summary = RunSummary(
        run_id=run_id,
        pipeline_type=mode,
        total_elapsed_ms=total_ms,
        wall_clock_ms=int((time.perf_counter() - started) * 1000),
        node_count=len(scheduled),
        cache_hits=sum(1 for state in frame.node_states.values() if state.is_cache_hit),
        aggregate_metrics=frame.aggregate_metrics,
    )
    yield {"event": "run_complete", "data": summary.model_dump_json()}
