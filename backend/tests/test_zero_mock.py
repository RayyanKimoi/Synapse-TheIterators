"""No fabricated data may reach a live run.

The mock exists for one reason: `llm_offline_mode`, chosen deliberately, so the
suite and a rehearsal can run with no network. It is never a fallback. Running
live, a model or tool that cannot answer produces a FAILED node, because an
invented answer is indistinguishable from a real one to the contract check, to
the semantic cache that would store it, and to anyone watching the arena.
"""

import asyncio
import json

import pytest

from app import registry
from app.config import Settings
from app.llm.gateway import LLMGateway, LLMUnavailableError
from app.models.ir import NodeType, WorkflowIR, WorkflowNode
from app.models.telemetry import NodeStatus
from app.runtime.runner import stream_telemetry
from app.runtime.tools import ToolError, run_tool

LIVE = Settings(
    llm_offline_mode=False,
    litellm_proxy_url="http://127.0.0.1:1",  # nothing listens here
    tavily_api_key="tvly-placeholder-demo-key",
)


@pytest.fixture
def workflow() -> WorkflowIR:
    found = registry.get("wf_deep_research_v1")
    assert found is not None
    return found


def _tool(**overrides) -> WorkflowNode:
    base = {
        "id": "crawler",
        "type": NodeType.TOOL_IO,
        "persona": "Crawler",
        "system_prompt": "Fetch filings.",
        "tool_name": "tavily_search",
    }
    return WorkflowNode.model_validate(base | overrides)


# --- the live model never invents a completion -----------------------------


def test_an_unreachable_model_raises_instead_of_mocking() -> None:
    async def scenario():
        return await LLMGateway(LIVE).complete(
            prompt="anything", model="openai/qwen2.5-3b-instruct", max_tokens=16
        )

    with pytest.raises(LLMUnavailableError):
        asyncio.run(scenario())


def test_offline_mode_is_the_only_route_to_the_mock() -> None:
    offline = Settings(llm_offline_mode=True, litellm_proxy_url="http://127.0.0.1:1")
    result = asyncio.run(
        LLMGateway(offline).complete(prompt="anything", model="openai/whatever")
    )
    assert result.source == "mock"
    # Simulated output says so in its own text, so it cannot be mistaken later.
    assert "[synapse:mock:" in result.text


def test_the_demo_default_is_live() -> None:
    """A fresh Settings must not silently simulate; the demo runs on real calls."""
    assert Settings().llm_offline_mode is False


# --- the live tools never invent a payload ---------------------------------


def test_a_placeholder_tool_key_is_a_configuration_error() -> None:
    with pytest.raises(ToolError, match="placeholder"):
        asyncio.run(run_tool(_tool(), "query", LIVE))


def test_an_unimplemented_tool_fails_rather_than_pretending() -> None:
    unknown = _tool(tool_name="some_unwired_api")
    with pytest.raises(ToolError, match="no client implemented"):
        asyncio.run(run_tool(unknown, "query", LIVE))


def test_the_offline_stub_labels_itself() -> None:
    offline = Settings(llm_offline_mode=True)
    text, latency_ms = asyncio.run(run_tool(_tool(), "query", offline))
    assert json.loads(text)["status"] == "offline_stub"
    assert latency_ms > 0


# --- a failed tool severs its branch, visibly ------------------------------


def test_a_failing_tool_fails_its_node_and_halts_downstream(
    workflow: WorkflowIR, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no tool credential the crawlers cannot run, so the synthesizer
    below them must never be handed a fabricated input.

    Only the tool is broken here: the model answers normally, so the failure
    being asserted is the tool's own and not an upstream halt.
    """
    monkeypatch.setattr("app.runtime.executor.run_tool", _always_fails)

    async def collect():
        return [
            (event["event"], json.loads(event["data"]))
            async for event in stream_telemetry(workflow, time_scale=1.0)
        ]

    events = asyncio.run(collect())
    frame = events[-2][1]
    states = frame["node_states"]

    for crawler in ("node_search_filings", "node_search_sentiment", "node_search_macro"):
        assert states[crawler]["status"] == NodeStatus.FAILED.value
        assert "tool failed" in (states[crawler]["error"] or "")

    # The node downstream of them never ran, and the run cannot be certified.
    assert states["node_synthesize_report"]["status"] == NodeStatus.FAILED.value
    assert frame["contract"]["halted"]
    assert frame["contract"]["semantic_invariance"] is None
    assert not frame["contract"]["passed"]


async def _always_fails(node, query, settings):
    raise ToolError(f"node '{node.id}': no credential")
