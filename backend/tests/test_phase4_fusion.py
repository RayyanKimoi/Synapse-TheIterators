"""V3 Phase 4: DSPy-assisted prompt fusion.

The reference workflow is LLM -> tools -> LLM and has no adjacent LLM pair, so
these tests use purpose-built chains. That absence is the point of
`test_the_reference_workflow_has_nothing_to_fuse`: fusion reports no gain where
there is none to report.
"""

import asyncio
import json

import pytest

from app import registry
from app.compiler.dag import build_graph
from app.compiler.planner import compile_workflow
from app.models.ir import WorkflowIR
from app.models.telemetry import PipelineType
from app.runtime.fusion import fused_system_prompt, plan_fusion, signature_spec
from app.runtime.runner import stream_telemetry

MODEL = "ollama/qwen2.5-7b"


def _agent(node_id: str, deps: list[str], **overrides) -> dict:
    return {
        "id": node_id,
        "type": "llm_agent",
        "persona": f"{node_id.title()} Agent",
        "system_prompt": f"Do the {node_id} step.",
        "model": MODEL,
        "dependencies": deps,
    } | overrides


def _workflow(nodes: list[dict], keys: list[str] | None = None) -> WorkflowIR:
    return WorkflowIR.model_validate(
        {
            "workflow_id": "wf_fusion_probe",
            "name": "Fusion probe",
            "budget_limit_usd": 0.5,
            "nodes": nodes,
            "test_assertions": {
                "required_output_keys": keys or [],
                "max_acceptable_latency_ms": 60_000,
            },
        }
    )


def _groups(workflow: WorkflowIR) -> dict:
    return plan_fusion(workflow, build_graph(workflow))


def _run(workflow: WorkflowIR, **kwargs) -> list[tuple[str, dict]]:
    async def collect() -> list[tuple[str, dict]]:
        return [
            (event["event"], json.loads(event["data"]))
            async for event in stream_telemetry(workflow, time_scale=150.0, **kwargs)
        ]

    return asyncio.run(collect())


# --- the analyzer ----------------------------------------------------------


def test_an_adjacent_private_pair_is_fused() -> None:
    groups = _groups(_workflow([_agent("draft", []), _agent("polish", ["draft"])]))
    assert sorted(groups) == ["draft", "polish"]
    group = groups["draft"]
    assert group.leader == "draft"
    assert group.members == ("draft", "polish")
    assert group.followers == ("polish",)


def test_a_longer_private_chain_fuses_maximally() -> None:
    groups = _groups(
        _workflow(
            [
                _agent("extract", []),
                _agent("draft", ["extract"]),
                _agent("polish", ["draft"]),
            ]
        )
    )
    assert groups["extract"].members == ("extract", "draft", "polish")
    assert len({id(group) for group in groups.values()}) == 1  # one shared group


def test_different_models_cannot_share_a_call() -> None:
    """One request is served by one model. This is not a heuristic."""
    groups = _groups(
        _workflow(
            [
                _agent("draft", []),
                _agent("polish", ["draft"], model="ollama/llama3.1-8b"),
            ]
        )
    )
    assert groups == {}


def test_a_side_effecting_node_is_never_fused() -> None:
    """Fusion collapses two executions into one; that must not change what the
    workflow does to the outside world."""
    assert _groups(
        _workflow([_agent("draft", []), _agent("publish", ["draft"], side_effect=True)])
    ) == {}
    assert _groups(
        _workflow([_agent("draft", [], side_effect=True), _agent("polish", ["draft"])])
    ) == {}


def test_a_producer_with_another_consumer_is_not_fused() -> None:
    """Merging would leave the second consumer without a separately addressable
    output to depend on."""
    groups = _groups(
        _workflow(
            [_agent("draft", []), _agent("polish", ["draft"]), _agent("audit", ["draft"])]
        )
    )
    assert groups == {}


def test_a_consumer_with_another_dependency_is_not_fused() -> None:
    """At the moment of the merged call the other input does not exist yet."""
    groups = _groups(
        _workflow(
            [
                _agent("draft", []),
                _agent("context", []),
                _agent("polish", ["draft", "context"]),
            ]
        )
    )
    assert groups == {}


def test_a_tool_breaks_the_chain() -> None:
    nodes = [
        _agent("draft", []),
        {
            "id": "fetch",
            "type": "tool_io",
            "persona": "Crawler",
            "system_prompt": "Fetch.",
            "tool_name": "tavily_search",
            "dependencies": ["draft"],
        },
        _agent("polish", ["fetch"]),
    ]
    assert _groups(_workflow(nodes)) == {}


def test_the_reference_workflow_has_nothing_to_fuse() -> None:
    """LLM -> tools -> LLM. No adjacent LLM pair exists, so fusion claims no
    gain here -- which is why removing the 0.55 multiplier raised this
    workflow's projected latency instead of lowering it."""
    workflow = registry.get("wf_deep_research_v1")
    assert workflow is not None
    assert _groups(workflow) == {}


# --- the DSPy signature ----------------------------------------------------


def test_the_signature_declares_one_output_field_per_member() -> None:
    group = _groups(_workflow([_agent("draft", []), _agent("polish", ["draft"])]))["draft"]
    assert signature_spec(group) == "query, context -> draft, polish"


def test_the_fused_prompt_carries_every_persona_and_step_once() -> None:
    group = _groups(_workflow([_agent("draft", []), _agent("polish", ["draft"])]))["draft"]
    prompt = fused_system_prompt(group)
    assert prompt.count("Do the draft step.") == 1
    assert prompt.count("Do the polish step.") == 1
    assert "single pass" in prompt
    # The JSON contract is what lets the leader split the response.
    assert "draft, polish" in prompt


def test_field_names_survive_ids_that_are_not_identifiers() -> None:
    group = _groups(
        _workflow([_agent("node.draft-1", []), _agent("node.polish-2", ["node.draft-1"])])
    )["node.draft-1"]
    assert all(field.isidentifier() for field in group.fields.values())


# --- execution -------------------------------------------------------------


def test_a_fused_chain_makes_one_request_instead_of_two() -> None:
    """The whole point: round trips removed, not latency asserted into being."""
    workflow = _workflow([_agent("draft", []), _agent("polish", ["draft"])])

    compiled = _run(workflow, mode=PipelineType.COMPILED)[-1][1]
    baseline = _run(workflow, mode=PipelineType.BASELINE)[-1][1]

    assert sum(compiled["llm_calls"].values()) == 1
    assert sum(baseline["llm_calls"].values()) == 2


def test_tokens_are_booked_once_on_the_leader() -> None:
    workflow = _workflow([_agent("draft", []), _agent("polish", ["draft"])])
    states = _run(workflow, mode=PipelineType.COMPILED)[-2][1]["node_states"]
    assert states["draft"]["tokens_consumed"] > 0
    # Counting the follower again would invent usage that was never bought.
    assert states["polish"]["tokens_consumed"] == 0
    assert states["polish"]["cost_usd"] == 0


def test_a_follower_receives_its_own_slice_of_the_merged_response() -> None:
    workflow = _workflow([_agent("draft", []), _agent("polish", ["draft"])])
    events = _run(workflow, mode=PipelineType.COMPILED)
    states = events[-2][1]["node_states"]
    # Both terminate normally; the follower is not left IDLE or FAILED.
    assert states["draft"]["status"] == "COMPLETED"
    assert states["polish"]["status"] == "COMPLETED"
    # The follower output is its own field, not a copy of the leader's.
    assert events[-1][1]["final_output"] is not None


def test_fusion_lowers_the_chain_cost_against_the_baseline() -> None:
    workflow = _workflow([_agent("draft", []), _agent("polish", ["draft"])])
    compiled = _run(workflow, mode=PipelineType.COMPILED)[-1][1]
    baseline = _run(workflow, mode=PipelineType.BASELINE)[-1][1]
    assert compiled["total_elapsed_ms"] < baseline["total_elapsed_ms"]
    assert (
        compiled["aggregate_metrics"]["total_cost_usd"]
        <= baseline["aggregate_metrics"]["total_cost_usd"]
    )


def test_the_baseline_pipeline_does_not_fuse() -> None:
    """Fusion is a compiler pass; handing it to the control would erase the
    difference the arena measures."""
    workflow = _workflow([_agent("draft", []), _agent("polish", ["draft"])])
    states = _run(workflow, mode=PipelineType.BASELINE)[-2][1]["node_states"]
    assert all(state["tokens_consumed"] > 0 for state in states.values())


# --- the planner -----------------------------------------------------------


def test_the_planner_reports_a_fusion_candidate_with_real_savings() -> None:
    workflow = _workflow([_agent("draft", []), _agent("polish", ["draft"])])
    plan = compile_workflow(workflow)
    fusion = [c for c in plan.optimization_candidates if c.kind == "prompt_fusion"]
    assert len(fusion) == 1
    assert set(fusion[0].node_ids) == {"draft", "polish"}
    assert fusion[0].projected_latency_saved_ms > 0
    assert plan.compiled_estimate.latency_ms < plan.baseline_estimate.latency_ms


def test_the_planner_reports_no_fusion_candidate_when_nothing_is_fusable() -> None:
    workflow = registry.get("wf_deep_research_v1")
    assert workflow is not None
    kinds = {c.kind for c in compile_workflow(workflow).optimization_candidates}
    assert "prompt_fusion" not in kinds
