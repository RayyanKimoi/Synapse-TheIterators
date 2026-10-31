"""Real outbound tool calls.

There is exactly one rule here: a tool either performs its actual network call
or it fails. It never invents a result. A fabricated search result is worse
than a failed node, because a failed node is visible in the arena and a
fabricated one silently becomes the input to every agent downstream.

`llm_offline_mode` is the one switch that allows a simulated tool. It exists so
the test suite can run deterministically with no network, and it is off for the
live demo -- see `Settings.llm_offline_mode`.
"""

import json
import logging
import time

import httpx

from ..config import Settings
from ..models.ir import WorkflowNode
from .profile import node_latency_ms

logger = logging.getLogger(__name__)

TAVILY_URL = "https://api.tavily.com/search"
TOOL_TIMEOUT_S = 30.0
# Keys shipped in .env.example. Running with one of these means the operator
# never supplied a credential, which is a configuration error, not an outage.
PLACEHOLDER_PREFIXES = ("tvly-placeholder", "sk-placeholder")


class ToolError(RuntimeError):
    """A tool could not be executed. Halts the node, never substitutes a result."""


async def run_tool(
    node: WorkflowNode, query: str, settings: Settings
) -> tuple[str, int]:
    """Execute `node`'s tool and return (payload JSON, measured latency ms)."""
    if settings.llm_offline_mode:
        return _offline_stub(node)

    if node.tool_name == "tavily_search":
        return await _tavily_search(node, query, settings)

    # Better to stop than to let an unimplemented tool look like it worked.
    raise ToolError(
        f"node '{node.id}': no client implemented for tool '{node.tool_name}'"
    )


async def _tavily_search(
    node: WorkflowNode, query: str, settings: Settings
) -> tuple[str, int]:
    key = settings.tavily_api_key
    if not key or key.startswith(PLACEHOLDER_PREFIXES):
        raise ToolError(
            f"node '{node.id}': TAVILY_API_KEY is unset or still the placeholder. "
            "Set a real key, or run with LLM_OFFLINE_MODE=true to simulate tools."
        )

    # The node's declared params steer the search; the run's query is the subject.
    body = {
        "api_key": key,
        "query": f"{query} {node.system_prompt}".strip(),
        "max_results": int(node.params.get("max_results", 5)),
        "search_depth": str(node.params.get("search_depth", "basic")),
    }

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=TOOL_TIMEOUT_S) as client:
            response = await client.post(TAVILY_URL, json=body)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise ToolError(
            f"node '{node.id}': tavily returned {exc.response.status_code}"
        ) from exc
    except httpx.HTTPError as exc:
        raise ToolError(f"node '{node.id}': {type(exc).__name__}: {exc}") from exc

    results = [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
        }
        for item in payload.get("results", [])
    ]
    text = json.dumps(
        {"tool": node.tool_name, "query": body["query"], "results": results},
        sort_keys=True,
    )
    return text, int((time.perf_counter() - started) * 1000)


def _offline_stub(node: WorkflowNode) -> tuple[str, int]:
    """Only reachable with `llm_offline_mode` on, which the demo does not use.

    Labelled `offline_stub` in its own payload so a simulated result can never
    be mistaken for a real one by anything reading it downstream.
    """
    return (
        json.dumps(
            {"tool": node.tool_name, "status": "offline_stub", "params": node.params},
            sort_keys=True,
        ),
        node_latency_ms(node),
    )
