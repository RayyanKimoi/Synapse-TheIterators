"""Phase 1 acceptance checks: IR validation, DAG passes, SSE contract, gateway."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import registry
from app.compiler.dag import CompileError, build_graph, topological_depths
from app.compiler.planner import compile_workflow
from app.llm.cache import get_cache
from app.llm.gateway import BudgetExceededError, LLMGateway, RunBudget
from app.main import app
from app.models.ir import WorkflowIR
from app.models.telemetry import NodeStatus, PipelineType
from app.runtime.runner import stream_telemetry

client = TestClient(app)


@pytest.fixture
def workflow() -> WorkflowIR:
    found = registry.get("wf_deep_research_v1")
    assert found is not None, "workflows/deep_research.json must load"
    return found


def _collect(**kwargs) -> list[tuple[str, dict]]:
    async def run() -> list[tuple[str, dict]]:
        return [
            (event["event"], json.loads(event["data"]))
            async for event in stream_telemetry(time_scale=120.0, **kwargs)
        ]

    return asyncio.run(run())


# --- IR schema -------------------------------------------------------------


def test_reference_workflow_loads(workflow: WorkflowIR) -> None:
    assert len(workflow.nodes) == 5
    assert workflow.schema_url is not None  # "$schema" alias is accepted
    assert workflow.test_assertions.min_semantic_similarity == 0.95


def test_llm_agent_requires_model() -> None:
    with pytest.raises(ValidationError, match="requires 'model'"):
        WorkflowIR.model_validate(
            {
                "workflow_id": "wf",
                "name": "n",
                "nodes": [
                    {"id": "a", "type": "llm_agent", "persona": "p", "system_prompt": "s"}
                ],
            }
        )


def test_unknown_dependency_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown node"):
        WorkflowIR.model_validate(
            {
                "workflow_id": "wf",
                "name": "n",
                "nodes": [
                    {
                        "id": "a",
                        "type": "tool_io",
                        "tool_name": "t",
                        "persona": "p",
                        "system_prompt": "s",
                        "dependencies": ["ghost"],
                    }
                ],
            }
        )


# --- compiler --------------------------------------------------------------


def test_topological_tiers_partition_independent_nodes(workflow: WorkflowIR) -> None:
    plan = compile_workflow(workflow)
    assert plan.execution_tiers == [
        ["node_extract_entities"],
        ["node_search_filings", "node_search_sentiment", "node_search_macro"],
        ["node_synthesize_report"],
    ]
    assert plan.max_depth == 2
    assert plan.edge_count == 6


def test_compiled_plan_beats_baseline(workflow: WorkflowIR) -> None:
    plan = compile_workflow(workflow)
    assert plan.compiled_estimate.latency_ms < plan.baseline_estimate.latency_ms
    assert plan.latency_reduction_pct > 50.0
    kinds = {candidate.kind for candidate in plan.optimization_candidates}
    assert kinds == {"parallelize", "prompt_fusion"}


def test_cycle_is_rejected() -> None:
    cyclic = WorkflowIR.model_validate(
        {
            "workflow_id": "wf_cycle",
            "name": "cyclic",
            "nodes": [
                {
                    "id": "a",
                    "type": "tool_io",
                    "tool_name": "t",
                    "persona": "p",
                    "system_prompt": "s",
                    "dependencies": ["b"],
                },
                {
                    "id": "b",
                    "type": "tool_io",
                    "tool_name": "t",
                    "persona": "p",
                    "system_prompt": "s",
                    "dependencies": ["a"],
                },
            ],
        }
    )
    with pytest.raises(CompileError) as excinfo:
        compile_workflow(cyclic)
    assert excinfo.value.cycle


def test_depths_follow_longest_path(workflow: WorkflowIR) -> None:
    depths = topological_depths(build_graph(workflow))
    assert depths["node_extract_entities"] == 0
    assert depths["node_synthesize_report"] == 2


# --- telemetry stream ------------------------------------------------------


def test_stream_ends_with_every_node_terminal(workflow: WorkflowIR) -> None:
    events = _collect(workflow=workflow, mode=PipelineType.COMPILED)
    assert events[-1][0] == "run_complete"
    final_frame = events[-2][1]
    assert {state["status"] for state in final_frame["node_states"].values()} == {"COMPLETED"}
    assert final_frame["active_nodes"] == []
    assert final_frame["aggregate_metrics"]["total_tokens"] > 0


def test_compiled_stream_is_faster_than_baseline(workflow: WorkflowIR) -> None:
    compiled = _collect(workflow=workflow, mode=PipelineType.COMPILED)[-1][1]
    baseline = _collect(workflow=workflow, mode=PipelineType.BASELINE)[-1][1]
    assert compiled["total_elapsed_ms"] < baseline["total_elapsed_ms"]
    # PRD demo target: ~35 s baseline collapsing to ~8 s compiled.
    assert 30_000 <= baseline["total_elapsed_ms"] <= 40_000
    assert 6_000 <= compiled["total_elapsed_ms"] <= 11_000


def test_warm_cache_run_is_sub_second_and_free(workflow: WorkflowIR) -> None:
    summary = _collect(
        workflow=workflow, mode=PipelineType.COMPILED, cache_warm=True
    )[-1][1]
    # Priming ran the whole graph, so every node is now served from vectors.
    assert summary["cache_hits"] == len(workflow.nodes)
    assert summary["total_elapsed_ms"] < 1_000
    assert summary["aggregate_metrics"]["total_tokens"] == 0
    assert summary["aggregate_metrics"]["total_cost_usd"] == 0
    assert summary["aggregate_metrics"]["projected_cost_saved_usd"] > 0


def test_cached_nodes_report_zero_tokens(workflow: WorkflowIR) -> None:
    events = _collect(workflow=workflow, mode=PipelineType.COMPILED, cache_warm=True)
    states = events[-2][1]["node_states"]
    cached = [s for s in states.values() if s["status"] == NodeStatus.CACHED.value]
    assert cached and all(s["tokens_consumed"] == 0 and s["latency_ms"] <= 5 for s in cached)


def test_telemetry_is_deterministic(workflow: WorkflowIR) -> None:
    first = _collect(workflow=workflow, mode=PipelineType.COMPILED)[-1][1]
    # Without this the second run would legitimately be served from the first
    # one, which is the cache working -- but not what this test is measuring.
    get_cache.cache_clear()
    second = _collect(workflow=workflow, mode=PipelineType.COMPILED)[-1][1]
    assert first["total_elapsed_ms"] == second["total_elapsed_ms"]
    assert first["aggregate_metrics"] == second["aggregate_metrics"]


# --- gateway ---------------------------------------------------------------


def test_offline_gateway_is_deterministic_and_priced() -> None:
    async def run():
        gateway = LLMGateway()
        return await asyncio.gather(
            gateway.complete(prompt="summarize CPI", model="ollama/qwen2.5-7b"),
            gateway.complete(prompt="summarize CPI", model="ollama/qwen2.5-7b"),
        )

    first, second = asyncio.run(run())
    assert first.source == "mock"
    assert first.text == second.text
    assert first.tokens_consumed == second.tokens_consumed
    assert first.cost_usd > 0


def test_budget_circuit_breaker_trips() -> None:
    budget = RunBudget(limit_usd=0.0001)
    with pytest.raises(BudgetExceededError):
        asyncio.run(LLMGateway().complete(prompt="expensive", budget=budget))


# --- HTTP surface ----------------------------------------------------------


def test_health_and_workflow_listing() -> None:
    assert client.get("/api/v1/health").json()["status"] == "ok"
    listed = client.get("/api/v1/workflows").json()
    assert any(item["workflow_id"] == "wf_deep_research_v1" for item in listed)


def test_compile_endpoint(workflow: WorkflowIR) -> None:
    response = client.post("/api/v1/compile", json=workflow.model_dump(by_alias=True))
    assert response.status_code == 200
    assert len(response.json()["execution_tiers"]) == 3


def test_compile_endpoint_rejects_cycle() -> None:
    response = client.post(
        "/api/v1/compile",
        json={
            "workflow_id": "wf_cycle",
            "name": "cyclic",
            "nodes": [
                {
                    "id": "a",
                    "type": "tool_io",
                    "tool_name": "t",
                    "persona": "p",
                    "system_prompt": "s",
                    "dependencies": ["b"],
                },
                {
                    "id": "b",
                    "type": "tool_io",
                    "tool_name": "t",
                    "persona": "p",
                    "system_prompt": "s",
                    "dependencies": ["a"],
                },
            ],
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["cycle"]


def test_execute_stream_emits_sse_frames() -> None:
    with client.stream(
        "POST",
        "/api/v1/execute/stream",
        json={
            "workflow_id": "wf_deep_research_v1",
            "mode": "compiled",
            "cache_warm": True,
            "time_scale": 120.0,
        },
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())
    assert "event: telemetry_update" in body
    assert "event: run_complete" in body


def test_execute_stream_requires_exactly_one_target() -> None:
    response = client.post("/api/v1/execute/stream", json={"mode": "compiled"})
    assert response.status_code == 422
