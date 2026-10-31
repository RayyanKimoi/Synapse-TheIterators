"""Rejecting an optimization in the Matchmaker has to change what runs.

Before this, the deck was a presentation device: approve started a compiled run
and reject did nothing at all, so a developer could swipe left on a pass and get
a byte-identical execution. These tests pin the verdict to the execution.
"""

import asyncio
import json

import pytest

from app import registry
from app.compiler.dag import build_graph
from app.compiler.planner import (
    compile_workflow,
    graph_without_rejected_parallelism,
    nodes_denied_concurrency,
)
from app.config import Settings
from app.llm.cache import SemanticCache
from app.models.ir import WorkflowIR
from app.runtime.paste import MIN_OBSERVATIONS, TransitionMatrix, observed_edges

CRAWLERS = ("node_search_filings", "node_search_sentiment", "node_search_macro")
FUSION_ID = "opt_fusion_node_draft_findings"
PARALLEL_ID = "opt_parallelize_0"


@pytest.fixture
def workflow() -> WorkflowIR:
    found = registry.get("wf_deep_research_v1")
    assert found is not None
    return found


def _run(workflow: WorkflowIR, disabled: list[str]) -> tuple[dict, dict]:
    from app.runtime.runner import stream_telemetry

    graph = build_graph(workflow)
    ids = [node.id for node in workflow.nodes]

    async def collect():
        matrix = TransitionMatrix(":memory:")
        for _ in range(MIN_OBSERVATIONS):
            await matrix.record_run(ids, observed_edges(graph, ids))
        events = [
            (event["event"], json.loads(event["data"]))
            async for event in stream_telemetry(
                workflow,
                # Every assertion here is relative, so compressed time is safe
                # and keeps eight full runs off the suite's clock.
                time_scale=150.0,
                matrix=matrix,
                cache=SemanticCache(Settings(), use_redis=False),
                disabled=frozenset(disabled),
            )
        ]
        return events[-1][1], events[-2][1]

    return asyncio.run(collect())


def _crawler_ms(frame: dict) -> int:
    return sum(frame["node_states"][node]["latency_ms"] for node in CRAWLERS)


# --- the ids the deck shows are the ids the runner honours ------------------


def test_candidate_ids_are_the_contract_between_deck_and_runner(
    workflow: WorkflowIR,
) -> None:
    """A verdict is routed by id, so a renamed candidate would silently stop
    being rejectable."""
    ids = {c.id for c in compile_workflow(workflow).optimization_candidates}
    assert PARALLEL_ID in ids
    assert FUSION_ID in ids


# --- each pass can actually be declined ------------------------------------


def test_rejecting_fusion_costs_an_extra_round_trip(workflow: WorkflowIR) -> None:
    kept, _ = _run(workflow, [])
    declined, declined_frame = _run(workflow, [FUSION_ID])

    assert sum(kept["llm_calls"].values()) == 2
    assert sum(declined["llm_calls"].values()) == 3
    # Unfused, the terminal node generates and pays for its own output.
    assert declined_frame["node_states"]["node_synthesize_report"]["tokens_consumed"] > 0
    assert declined["total_elapsed_ms"] > kept["total_elapsed_ms"]


def test_rejecting_prefetch_puts_the_tool_latency_back(workflow: WorkflowIR) -> None:
    _, kept = _run(workflow, [])
    _, declined = _run(workflow, [f"opt_prefetch_{node}" for node in CRAWLERS])
    assert _crawler_ms(declined) > _crawler_ms(kept)


def test_rejecting_parallelism_also_denies_speculation(workflow: WorkflowIR) -> None:
    """Serialising dispatch alone is not enough: PASTE fires the requests when
    the parent starts, so they would still go out together and the rejection
    would be unobservable. A group denied concurrency is denied speculation."""
    kept, _ = _run(workflow, [])
    declined, _ = _run(workflow, [PARALLEL_ID])
    assert declined["total_elapsed_ms"] > kept["total_elapsed_ms"] * 2


def test_an_unknown_id_is_ignored_rather_than_fatal(workflow: WorkflowIR) -> None:
    """Candidate ids come from a client; a stale one must not break the run."""
    baseline, _ = _run(workflow, [])
    unknown, _ = _run(workflow, ["opt_fusion_does_not_exist", "garbage"])
    assert unknown["total_elapsed_ms"] == pytest.approx(
        baseline["total_elapsed_ms"], rel=0.2
    )


# --- the graph surgery itself ----------------------------------------------


def test_serialising_a_group_adds_edges_without_creating_a_cycle(
    workflow: WorkflowIR,
) -> None:
    import networkx as nx

    graph = build_graph(workflow)
    serialised = graph_without_rejected_parallelism(graph, frozenset({PARALLEL_ID}))
    assert serialised.number_of_edges() > graph.number_of_edges()
    assert nx.is_directed_acyclic_graph(serialised)
    # The original is untouched; rejection must not mutate shared state.
    assert graph.number_of_edges() == 7


def test_nothing_rejected_returns_the_graph_unchanged(workflow: WorkflowIR) -> None:
    graph = build_graph(workflow)
    assert graph_without_rejected_parallelism(graph, frozenset()) is graph
    assert nodes_denied_concurrency(graph, frozenset()) == frozenset()


def test_denied_concurrency_names_the_whole_group(workflow: WorkflowIR) -> None:
    denied = nodes_denied_concurrency(build_graph(workflow), frozenset({PARALLEL_ID}))
    assert denied == set(CRAWLERS)
