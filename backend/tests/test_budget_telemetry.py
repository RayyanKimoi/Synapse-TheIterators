"""Frames carry the budget the breaker enforces, so a client's "% of budget"
is computed against the same number that trips the circuit breaker."""

import asyncio

from app import registry
from app.config import get_settings
from app.llm.cache import get_cache
from app.models.ir import WorkflowIR
from app.models.telemetry import CircuitBreakerStatus, PipelineType, TelemetryFrame
from app.runtime.runner import stream_telemetry

WORKFLOW = registry.get("wf_deep_research_v1")


def _frames(workflow: WorkflowIR) -> list[TelemetryFrame]:
    async def scenario():
        frames = []
        async for message in stream_telemetry(workflow, mode=PipelineType.BASELINE, time_scale=200.0):
            if message["event"] == "telemetry_update":
                frames.append(TelemetryFrame.model_validate_json(message["data"]))
        return frames

    return asyncio.run(scenario())


def test_frames_report_the_clamped_budget_not_the_declared_one() -> None:
    ceiling = get_settings().max_budget_per_workflow_usd
    generous = WORKFLOW.model_copy(update={"budget_limit_usd": ceiling * 4})
    budgets = {frame.aggregate_metrics.budget_limit_usd for frame in _frames(generous)}
    assert budgets == {ceiling}


def test_a_budget_below_the_run_cost_trips_the_breaker_it_reports() -> None:
    full_cost = _frames(WORKFLOW)[-1].aggregate_metrics.total_cost_usd
    assert full_cost > 0
    get_cache.cache_clear()  # else the second run is served from the first's cache, for $0
    tight = WORKFLOW.model_copy(update={"budget_limit_usd": full_cost / 2})
    frames = _frames(tight)
    final = frames[-1].aggregate_metrics
    assert final.budget_limit_usd == full_cost / 2
    assert final.circuit_breaker_status is CircuitBreakerStatus.TRIGGERED
    # Spend never passes the budget: the breaker refuses the call that would.
    assert all(f.aggregate_metrics.total_cost_usd <= f.aggregate_metrics.budget_limit_usd for f in frames)
