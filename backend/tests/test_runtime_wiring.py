"""V3 Phase 1: gateway wiring, budget circuit breaker, contract assertions, and
the Ready-Node scheduler's dispatch and halt semantics."""

import asyncio
import json

import networkx as nx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import registry
from app.compiler.scheduler import HaltBranch, ready_node_timings, run_ready_nodes
from app.config import Settings
from app.llm.gateway import BudgetExceededError, Guardrails, LLMGateway, RunBudget
from app.main import app
from app.models.ir import WorkflowIR
from app.models.telemetry import PipelineType
from app.runtime.contract import evaluate_contract, extract_json_object
from app.runtime.runner import stream_telemetry

REQUIRED_KEYS = ["summary", "risk_factors", "outlook"]
CRAWLERS = ("node_search_filings", "node_search_sentiment", "node_search_macro")


@pytest.fixture
def workflow() -> WorkflowIR:
    found = registry.get("wf_deep_research_v1")
    assert found is not None
    return found


def _run(workflow: WorkflowIR, **kwargs) -> list[tuple[str, dict]]:
    async def collect() -> list[tuple[str, dict]]:
        return [
            (event["event"], json.loads(event["data"]))
            async for event in stream_telemetry(workflow, time_scale=150.0, **kwargs)
        ]

    return asyncio.run(collect())


def _with_budget(workflow: WorkflowIR, usd: float) -> WorkflowIR:
    return workflow.model_copy(update={"budget_limit_usd": usd})


# --- scheduler -------------------------------------------------------------


def _asymmetric() -> tuple[nx.DiGraph, dict[str, int]]:
    graph = nx.DiGraph()
    graph.add_edges_from([("root", "fast"), ("root", "slow"), ("fast", "tail")])
    return graph, {"root": 500, "fast": 1000, "slow": 9000, "tail": 1000}


def test_ready_node_dispatch_never_waits_on_an_unrelated_sibling() -> None:
    graph, durations = _asymmetric()
    timings = ready_node_timings(graph, durations.__getitem__)
    # Depth tiers would hold `tail` until `slow` finished at 9500 ms.
    assert timings["tail"].start_ms == 1500


def test_live_scheduler_is_concurrent_and_matches_its_analytic_twin() -> None:
    graph, durations = _asymmetric()
    inflight = peak = 0

    async def work(node: str) -> int:
        nonlocal inflight, peak
        inflight += 1
        peak = max(peak, inflight)
        await asyncio.sleep(durations[node] / 1000 / 500)
        inflight -= 1
        return durations[node]

    live = asyncio.run(run_ready_nodes(graph, work=work, max_concurrency=8))
    analytic = ready_node_timings(graph, durations.__getitem__)

    assert peak >= 2
    assert {n: (t.start_ms, t.end_ms) for n, t in live.items()} == {
        n: (t.start_ms, t.end_ms) for n, t in analytic.items()
    }


def test_scheduler_honours_the_concurrency_bound() -> None:
    graph = nx.DiGraph()
    graph.add_edges_from(("root", f"child_{i}") for i in range(6))
    inflight = peak = 0

    async def work(node: str) -> int:
        nonlocal inflight, peak
        inflight += 1
        peak = max(peak, inflight)
        await asyncio.sleep(0.005)
        inflight -= 1
        return 10

    asyncio.run(run_ready_nodes(graph, work=work, max_concurrency=2))
    assert peak == 2


def test_a_halted_node_cancels_only_its_descendants() -> None:
    graph = nx.DiGraph()
    graph.add_edges_from(
        [("a", "b"), ("b", "c"), ("a", "d"), ("d", "e"), ("c", "f"), ("e", "f")]
    )
    ran: list[str] = []
    skipped: dict[str, str] = {}

    async def work(node: str) -> int:
        if node == "b":
            raise HaltBranch("boom")
        ran.append(node)
        return 10

    timings = asyncio.run(
        run_ready_nodes(
            graph,
            work=work,
            max_concurrency=4,
            on_skip=lambda nodes, failed: skipped.update(dict.fromkeys(nodes, failed)),
        )
    )

    assert timings["b"].failed
    assert set(ran) == {"a", "d", "e"}  # the independent branch still runs
    assert skipped == {"c": "b", "f": "b"}  # f joins both branches; one failed parent dooms it


# --- gateway & guardrails --------------------------------------------------


def test_reservations_stop_concurrent_calls_from_jointly_overspending() -> None:
    budget = RunBudget(limit_usd=1.0)
    budget.reserve(0.6)
    with pytest.raises(BudgetExceededError):
        budget.reserve(0.6)  # 0.6 is already held by a call in flight
    assert budget.tripped
    with pytest.raises(BudgetExceededError, match="already exhausted"):
        budget.reserve(0.01)  # the breaker stays open for the rest of the run


def test_settle_books_the_actual_cost_and_releases_the_hold() -> None:
    budget = RunBudget(limit_usd=1.0)
    budget.reserve(0.5)
    budget.settle(0.5, 0.2)
    assert budget.reserved_usd == 0
    assert budget.spent_usd == pytest.approx(0.2)
    assert not budget.tripped


def test_breaker_trips_before_any_request_is_sent() -> None:
    budget = RunBudget(limit_usd=0.0001)
    with pytest.raises(BudgetExceededError):
        asyncio.run(LLMGateway().complete(prompt="x", budget=budget))
    assert budget.spent_usd == 0
    assert budget.reserved_usd == 0


def test_a_cancelled_call_releases_its_reservation(monkeypatch: pytest.MonkeyPatch) -> None:
    async def hang(self, *args, **kwargs):
        await asyncio.sleep(10)

    monkeypatch.setattr(LLMGateway, "_dispatch", hang)
    budget = RunBudget(limit_usd=1.0)

    async def scenario() -> None:
        gateway = LLMGateway(Settings(llm_offline_mode=False))
        task = asyncio.create_task(gateway.complete(prompt="x", budget=budget))
        await asyncio.sleep(0.01)
        assert budget.reserved_usd > 0
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert budget.reserved_usd == 0
    assert budget.spent_usd == 0


def test_mock_follows_the_json_contract_it_is_given() -> None:
    result = asyncio.run(
        LLMGateway().complete(prompt="brief", response_keys=["summary", "risk_factors"])
    )
    assert set(json.loads(result.text)) == {"summary", "risk_factors"}


def test_guardrails_bind_the_cache_threshold_and_clamp_the_budget(
    workflow: WorkflowIR,
) -> None:
    assert Guardrails.resolve(workflow, Settings()).cache_similarity_threshold == 0.88

    tight = Settings(semantic_cache_similarity_threshold=0.9, max_budget_per_workflow_usd=0.1)
    guardrails = Guardrails.resolve(workflow, tight)
    assert guardrails.cache_similarity_threshold == 0.9
    assert guardrails.budget_limit_usd == 0.1  # the IR asks for 0.50; the ceiling wins


def test_cache_threshold_must_be_a_valid_cosine() -> None:
    with pytest.raises(ValidationError):
        Settings(semantic_cache_similarity_threshold=1.5)


# --- runner wiring ---------------------------------------------------------


def test_llm_nodes_are_served_by_the_gateway(workflow: WorkflowIR) -> None:
    summary = _run(workflow)[-1][1]
    assert summary["llm_calls"] == {"mock": 2}  # both llm_agent nodes, offline mode


def test_the_query_reaches_the_llm_prompts(workflow: WorkflowIR) -> None:
    first = _run(workflow, query="NVIDIA supply chain risk")[-1][1]
    second = _run(workflow, query="Tesla regulatory exposure")[-1][1]
    assert first["final_output"] != second["final_output"]


def test_breaker_at_the_root_halts_every_downstream_node(workflow: WorkflowIR) -> None:
    events = _run(_with_budget(workflow, 0.0005))
    final, summary = events[-2][1], events[-1][1]
    states = final["node_states"]

    assert final["aggregate_metrics"]["circuit_breaker_status"] == "CIRCUIT_BREAKER_TRIGGERED"
    assert states["node_extract_entities"]["status"] == "FAILED"
    assert "circuit breaker" in states["node_extract_entities"]["error"]
    for node in (*CRAWLERS, "node_synthesize_report"):
        assert states[node]["status"] == "FAILED"
        assert "halted" in states[node]["error"]
    assert summary["llm_calls"] == {}
    assert summary["contract"]["halted"]
    assert not summary["contract"]["passed"]


def test_breaker_mid_run_keeps_finished_work_and_fails_the_next_llm_call(
    workflow: WorkflowIR,
) -> None:
    events = _run(_with_budget(workflow, 0.0013))
    final, summary = events[-2][1], events[-1][1]
    states = final["node_states"]

    assert states["node_extract_entities"]["status"] == "COMPLETED"
    assert all(states[node]["status"] == "COMPLETED" for node in CRAWLERS)
    assert states["node_synthesize_report"]["status"] == "FAILED"
    assert final["aggregate_metrics"]["circuit_breaker_status"] == "CIRCUIT_BREAKER_TRIGGERED"
    assert summary["contract"]["missing_output_keys"] == REQUIRED_KEYS


# --- contract assertions ---------------------------------------------------


def test_compiled_run_satisfies_the_contract(workflow: WorkflowIR) -> None:
    events = _run(workflow)
    contract = events[-1][1]["contract"]

    assert contract["passed"]
    assert contract["missing_output_keys"] == []
    assert set(REQUIRED_KEYS) <= set(events[-1][1]["final_output"])
    assert contract["semantic_invariance"] == 1.0
    assert contract["cache_similarity_threshold"] == 0.88
    assert events[-2][1]["contract"] == contract  # the final frame carries it too


def test_invariance_is_certified_at_completion_not_hardcoded(workflow: WorkflowIR) -> None:
    events = _run(workflow)
    frames = [data for event, data in events if event == "telemetry_update"]
    assert frames[-1]["aggregate_metrics"]["correctness_score"] == 1.0
    assert all(frame["aggregate_metrics"]["correctness_score"] == 0.0 for frame in frames[:-1])
    assert all(frame["contract"] is None for frame in frames[:-1])


def test_baseline_fails_the_latency_assertion(workflow: WorkflowIR) -> None:
    contract = _run(workflow, mode=PipelineType.BASELINE)[-1][1]["contract"]
    assert contract["latency_ms"] > contract["max_acceptable_latency_ms"]
    assert not contract["latency_ok"]
    assert not contract["passed"]


def test_warm_cache_invariance_is_measured_not_assumed(workflow: WorkflowIR) -> None:
    """A warm run repeats the primed query exactly, so every hit measures 1.0
    and the run certifies -- on measurement, not on a hardcoded constant."""
    events = _run(workflow, cache_warm=True)
    contract = events[-1][1]["contract"]
    assert contract["semantic_invariance"] == 1.0
    assert contract["cache_admission_violations"] == []
    assert contract["passed"]
    assert events[-2][1]["aggregate_metrics"]["correctness_score"] == 1.0


def test_a_halted_run_cannot_certify_invariance(workflow: WorkflowIR) -> None:
    contract = _run(_with_budget(workflow, 0.0005))[-1][1]["contract"]
    assert contract["halted"]
    assert contract["semantic_invariance"] is None
    assert not contract["passed"]


def test_missing_keys_fail_the_contract(workflow: WorkflowIR) -> None:
    # Drop both reasoning agents so the crawlers are terminal. A tool node emits
    # its own payload shape, so nothing in the run produces the declared keys.
    trimmed = workflow.model_copy(update={"nodes": workflow.nodes[:-2]})
    contract = _run(trimmed)[-1][1]["contract"]
    assert contract["missing_output_keys"] == REQUIRED_KEYS
    assert not contract["passed"]


def test_cache_hit_below_the_threshold_is_an_admission_violation(
    workflow: WorkflowIR,
) -> None:
    report = evaluate_contract(
        workflow,
        Guardrails(budget_limit_usd=0.5, cache_similarity_threshold=0.88),
        payload=dict.fromkeys(REQUIRED_KEYS, "x"),
        latency_ms=100,
        cache_hits={"node_extract_entities": 0.81, "node_search_macro": 0.93},
        halted=False,
    )
    assert report.cache_admission_violations == ["node_extract_entities"]
    assert not report.passed


def test_extract_json_object_tolerates_fences_and_prose() -> None:
    assert extract_json_object('Sure!\n```json\n{"summary": "x"}\n```') == {"summary": "x"}
    assert extract_json_object('[1, 2] then {"a": 1}') == {"a": 1}
    assert extract_json_object("no json here") is None


# --- HTTP surface ----------------------------------------------------------


def test_stream_endpoint_accepts_a_query() -> None:
    client = TestClient(app)
    with client.stream(
        "GET",
        "/api/v1/execute/stream",
        params={"workflow_id": "wf_deep_research_v1", "time_scale": 200, "query": "NVIDIA"},
    ) as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    assert '"passed":true' in body


def test_empty_query_is_rejected() -> None:
    response = TestClient(app).get(
        "/api/v1/execute/stream", params={"workflow_id": "wf_deep_research_v1", "query": ""}
    )
    assert response.status_code == 422
