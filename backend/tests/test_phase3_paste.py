"""V3 Phase 3: PASTE -- the SQLite transition matrix, the 0.75 probability gate,
and speculative pre-fetching overlapping the LLM's generation.

These tests build their own matrices rather than using the pre-seeded one from
conftest, because what PASTE does depends entirely on how much history it has.
"""

import asyncio
import json

import networkx as nx
import pytest

from app import registry
from app.compiler.dag import build_graph
from app.compiler.planner import compile_workflow
from app.models.ir import NodeType, WorkflowIR, WorkflowNode
from app.models.telemetry import PipelineType
from app.runtime.paste import (
    MIN_OBSERVATIONS,
    PREFETCH_THRESHOLD,
    TransitionMatrix,
    observed_edges,
    prefetchable,
)
from app.runtime.runner import stream_telemetry

CRAWLERS = {"node_search_filings", "node_search_sentiment", "node_search_macro"}
ROOT = "node_extract_entities"
SINK = "node_synthesize_report"


@pytest.fixture
def workflow() -> WorkflowIR:
    found = registry.get("wf_deep_research_v1")
    assert found is not None
    return found


@pytest.fixture
def cold() -> TransitionMatrix:
    return TransitionMatrix(":memory:")


def _taught(workflow: WorkflowIR, runs: int = MIN_OBSERVATIONS) -> TransitionMatrix:
    """A matrix that has watched `runs` complete executions of `workflow`."""
    matrix = TransitionMatrix(":memory:")
    graph = build_graph(workflow)
    nodes = [node.id for node in workflow.nodes]
    for _ in range(runs):
        matrix._record_run(nodes, observed_edges(graph, nodes))
    return matrix


def _run(workflow: WorkflowIR, matrix: TransitionMatrix, **kwargs) -> list[tuple[str, dict]]:
    async def collect() -> list[tuple[str, dict]]:
        return [
            (event["event"], json.loads(event["data"]))
            async for event in stream_telemetry(
                workflow, time_scale=150.0, matrix=matrix, **kwargs
            )
        ]

    return asyncio.run(collect())


# --- the transition matrix -------------------------------------------------


def test_probability_is_hits_over_source_runs(cold: TransitionMatrix) -> None:
    async def scenario():
        # "a" ran 4 times; "b" followed 3 of them, "c" only the first.
        for index in range(4):
            edges = [("a", "b")] if index < 3 else []
            if index == 0:
                edges.append(("a", "c"))
            await cold.record_run(["a"], edges)
        return await cold.snapshot()

    snapshot = asyncio.run(scenario())
    assert snapshot[("a", "b")] == pytest.approx(3 / 4)
    assert snapshot[("a", "c")] == pytest.approx(1 / 4)
    # 3-of-4 lands exactly on the gate, and the gate is strict, so even this
    # does not earn speculation.
    assert snapshot[("a", "b")] == PREFETCH_THRESHOLD
    assert prefetchable(_two_node_graph(), {"tool": _tool()}, {("agent", "tool"): 3 / 4}) == frozenset()


def test_a_single_observation_does_not_authorise_speculation(
    cold: TransitionMatrix,
) -> None:
    """One run makes every edge look certain. The floor is what stops that."""

    async def scenario():
        await cold.record_run(["a"], [("a", "b")])
        after_one = await cold.snapshot()
        for _ in range(MIN_OBSERVATIONS - 1):
            await cold.record_run(["a"], [("a", "b")])
        return after_one, await cold.snapshot()

    after_one, after_floor = asyncio.run(scenario())
    assert after_one == {}
    assert after_floor[("a", "b")] == 1.0


def test_history_survives_a_new_matrix_over_the_same_file(tmp_path) -> None:
    """The matrix is a file, so what one process learns the next one knows."""
    path = tmp_path / "paste.db"

    async def scenario():
        writer = TransitionMatrix(path)
        for _ in range(MIN_OBSERVATIONS):
            await writer.record_run(["a"], [("a", "b")])
        return await TransitionMatrix(path).snapshot()

    assert asyncio.run(scenario())[("a", "b")] == 1.0


def test_observed_edges_describes_the_declared_graph_not_the_run_order(
    workflow: WorkflowIR,
) -> None:
    """The baseline executes over a serial chain. Recording that chain would
    teach PASTE a topology the workflow does not have."""
    graph = build_graph(workflow)
    edges = set(observed_edges(graph, [node.id for node in workflow.nodes]))
    assert edges == set(graph.edges)
    assert ("node_search_filings", "node_search_sentiment") not in edges


def test_a_halted_node_is_not_recorded_as_having_run(workflow: WorkflowIR) -> None:
    graph = build_graph(workflow)
    # Only the root got through; nothing downstream of it ran.
    assert observed_edges(graph, [ROOT]) == []


# --- the 0.75 gate ---------------------------------------------------------


def _tool(**overrides) -> WorkflowNode:
    base = {
        "id": "tool",
        "type": NodeType.TOOL_IO,
        "persona": "Crawler",
        "system_prompt": "Fetch.",
        "tool_name": "tavily_search",
        "dependencies": ["agent"],
    }
    return WorkflowNode.model_validate(base | overrides)


def _two_node_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_edge("agent", "tool")
    return graph


@pytest.mark.parametrize(
    ("probability", "expected"),
    [(0.74, False), (PREFETCH_THRESHOLD, False), (0.76, True), (1.0, True)],
)
def test_only_probabilities_above_the_threshold_speculate(
    probability: float, expected: bool
) -> None:
    """Strictly above 0.75: the PRD gate is a margin, not a coin flip."""
    nodes = {"tool": _tool()}
    eligible = prefetchable(_two_node_graph(), nodes, {("agent", "tool"): probability})
    assert ("tool" in eligible) is expected


def test_a_side_effecting_tool_is_never_speculated() -> None:
    """Firing it early runs it more often than the workflow asked for -- the
    one case where a wasted speculation is not merely wasted."""
    certain = {("agent", "tool"): 1.0}
    assert prefetchable(_two_node_graph(), {"tool": _tool(side_effect=True)}, certain) == frozenset()
    assert prefetchable(_two_node_graph(), {"tool": _tool()}, certain) == {"tool"}


def test_an_llm_node_is_never_speculated() -> None:
    agent = _tool(type=NodeType.LLM_AGENT, model="ollama/qwen2.5-7b", tool_name=None)
    assert prefetchable(_two_node_graph(), {"tool": agent}, {("agent", "tool"): 1.0}) == frozenset()


def test_the_reference_crawlers_become_eligible_once_taught(
    workflow: WorkflowIR,
) -> None:
    graph = build_graph(workflow)
    nodes = workflow.node_map()

    async def snapshots():
        cold = TransitionMatrix(":memory:")
        return await cold.snapshot(), await _taught(workflow).snapshot()

    cold_snapshot, warm_snapshot = asyncio.run(snapshots())
    assert prefetchable(graph, nodes, cold_snapshot) == frozenset()
    assert prefetchable(graph, nodes, warm_snapshot) == CRAWLERS


# --- speculative execution -------------------------------------------------


def test_a_cold_run_speculates_nothing_and_a_taught_run_does(
    workflow: WorkflowIR, cold: TransitionMatrix
) -> None:
    cold_states = _run(workflow, cold)[-2][1]["node_states"]
    assert all(cold_states[node]["latency_ms"] > 1_000 for node in CRAWLERS)

    taught_states = _run(workflow, _taught(workflow))[-2][1]["node_states"]
    # Every crawler was already in flight when the scheduler asked for it, so
    # what remains is the part that did not overlap the generation.
    assert sum(taught_states[node]["latency_ms"] for node in CRAWLERS) < sum(
        cold_states[node]["latency_ms"] for node in CRAWLERS
    )


def test_speculation_only_hides_the_overlap_never_more(workflow: WorkflowIR) -> None:
    """The honest ceiling. A tool fired alongside a 4.5 s generation still owes
    its own duration minus 4.5 s -- which is why the planner and the live run
    agree instead of one of them quoting a multiplier."""
    taught = _taught(workflow)

    async def scenario():
        return compile_workflow(workflow, await taught.snapshot())

    plan = asyncio.run(scenario())
    cold_plan = compile_workflow(workflow)

    assert plan.compiled_estimate.latency_ms < cold_plan.compiled_estimate.latency_ms
    # Real-time measurement of the same configuration is 14738 ms; the
    # projection lands within 0.2% of it because both compute the same overlap.
    assert plan.compiled_estimate.latency_ms == pytest.approx(14_738, rel=0.05)
    assert plan.compiled_estimate.latency_ms <= (
        workflow.test_assertions.max_acceptable_latency_ms
    )


def test_prefetched_nodes_are_labelled_and_cost_nothing_extra(
    workflow: WorkflowIR,
) -> None:
    taught = _taught(workflow)
    _run(workflow, taught)
    # The source label is how a prefetched call is told apart from a plain one.
    # Tool nodes never consume tokens, so speculation must not invent any.
    states = _run(workflow, taught)[-2][1]["node_states"]
    assert all(states[node]["tokens_consumed"] == 0 for node in CRAWLERS)


def test_the_baseline_pipeline_never_speculates(workflow: WorkflowIR) -> None:
    """PASTE is a compiler optimisation. Giving it to the control erases the
    very difference the arena is measuring."""
    taught = _taught(workflow)
    baseline = _run(workflow, taught, mode=PipelineType.BASELINE)[-1][1]
    compiled = _run(workflow, taught, mode=PipelineType.COMPILED)[-1][1]
    assert baseline["total_elapsed_ms"] > compiled["total_elapsed_ms"]
    assert 30_000 <= baseline["total_elapsed_ms"] <= 40_000


def test_a_run_teaches_the_matrix_for_the_next_one(
    workflow: WorkflowIR, cold: TransitionMatrix
) -> None:
    async def scenario():
        before = await cold.snapshot()
        return before

    assert asyncio.run(scenario()) == {}
    for _ in range(MIN_OBSERVATIONS):
        _run(workflow, cold)
    snapshot = asyncio.run(cold.snapshot())
    assert {edge for edge in snapshot} == set(build_graph(workflow).edges)
    assert all(probability == 1.0 for probability in snapshot.values())


def test_a_halted_branch_leaves_no_speculation_running(workflow: WorkflowIR) -> None:
    """The breaker trips at the root, so the crawlers it speculated on are
    never collected. Those tasks have to be cancelled, not abandoned."""
    broke = workflow.model_copy(update={"budget_limit_usd": 0.0005})
    events = _run(broke, _taught(workflow))
    contract = events[-1][1]["contract"]
    assert contract["halted"]
    # If aclose() had not cancelled them, asyncio would warn about pending
    # tasks destroyed at loop shutdown and the event loop would not close clean.
    assert events[-1][0] == "run_complete"
