"""Agent terminal: plain English reads into the right steps, and every step does
real work through the compiler, runtime and cache."""

import asyncio
import json

from fastapi.testclient import TestClient

from app import registry
from app.agent.terminal import plan, run_agent, suggest
from app.main import create_app
from app.models.telemetry import PipelineType

WF = registry.summaries()[0].workflow_id


def _collect(text: str, workflow_id: str | None = None) -> list[dict]:
    async def scenario():
        return [event async for event in run_agent(text, workflow_id=workflow_id)]

    return asyncio.run(scenario())


def _text(events: list[dict]) -> str:
    return "\n".join(event["text"] for event in events if event["type"] == "line")


# --- planning ----------------------------------------------------------------


def test_plain_english_becomes_ordered_steps() -> None:
    steps = plan("compile and race the market workflow with a warm cache")
    assert [step.tool for step in steps] == ["compile", "race"]
    assert all(step.workflow_id == WF for step in steps)
    assert steps[1].warm


def test_then_splits_clauses_and_a_pass_can_be_rejected() -> None:
    steps = plan("run baseline then run compiled without fusion")
    assert [(s.tool, s.mode) for s in steps] == [
        ("run", PipelineType.BASELINE),
        ("run", PipelineType.COMPILED),
    ]
    assert steps[0].disable == ()
    assert steps[1].disable == ("prompt_fusion",)


def test_commands_and_flags_parse_like_a_shell() -> None:
    (step,) = plan(f"run {WF} baseline --warm --disable paste")
    assert step.tool == "run" and step.workflow_id == WF
    assert step.mode is PipelineType.BASELINE and step.warm
    assert step.disable == ("speculative_prefetch",)


def test_ambiguous_words_resolve_to_the_obvious_tool() -> None:
    assert [s.tool for s in plan("show workflows")] == ["workflows"]
    assert [s.tool for s in plan("show me the passes")] == ["passes"]
    assert [s.tool for s in plan("list the nodes")] == ["inspect"]
    assert [s.tool for s in plan("show the market pipeline")] == ["inspect"]
    assert [s.tool for s in plan("what is paste?")] == ["explain"]
    assert [s.tool for s in plan("run baseline vs compiled")] == ["race"]
    assert [s.tool for s in plan("?")] == ["help"]


def test_a_clause_without_a_workflow_inherits_the_last_one() -> None:
    steps = plan("inspect then race it", workflow_id=WF)
    assert [s.workflow_id for s in steps] == [WF, WF]


def test_unknown_input_plans_nothing_and_suggests_a_command() -> None:
    assert plan("frobnicate the widgets") == []
    assert "compile" in suggest("compiel")


# --- execution: every step does real work ----------------------------------------


def test_compile_prints_tiers_estimates_and_points_the_dashboard() -> None:
    events = _collect(f"compile {WF}")
    out = _text(events)
    assert "tier 0" in out and "baseline" in out and "projected latency cut" in out
    assert {"type": "ui", "action": "select", "workflow_id": WF} in events
    assert events[-1]["type"] == "done" and events[-1]["ok"]


def test_race_executes_both_pipelines_and_reports_the_speedup() -> None:
    events = _collect("race it", workflow_id=WF)
    out = _text(events)
    assert "baseline" in out and "compiled" in out
    assert "dispatched" in out  # node-level progress streamed while running
    assert "contract" in out
    assert "× faster" in out
    assert events[-1]["ok"]


def test_a_warm_run_is_served_from_the_semantic_cache() -> None:
    out = _text(_collect("run it compiled with a warm cache", workflow_id=WF))
    assert "served from cache" in out


def test_a_failed_step_stops_the_plan_without_raising() -> None:
    events = _collect("compile wf_nope then race it")
    assert "no workflow 'wf_nope'" in _text(events)
    assert not any(e["type"] == "step" and e["index"] == 1 for e in events)
    assert events[-1]["type"] == "done" and not events[-1]["ok"]


def test_health_and_cache_report_live_state() -> None:
    out = _text(_collect("health then cache"))
    assert f"{len(registry.summaries())} loaded" in out
    assert "SimHash" in out and "Hamming" in out


def test_explain_answers_from_the_projects_own_vocabulary() -> None:
    events = _collect("how does prefetch work?")
    assert [e for e in events if e["type"] == "line"][0]["text"] == "paste"


def test_the_endpoint_streams_agent_events() -> None:
    response = TestClient(create_app()).post("/api/v1/agent/run", json={"input": "workflows"})
    assert response.status_code == 200
    payloads = [
        json.loads(line[len("data:"):])
        for line in response.text.splitlines()
        if line.startswith("data:")
    ]
    assert payloads[-1]["type"] == "done" and payloads[-1]["ok"]
    assert any(WF in payload.get("text", "") for payload in payloads)
