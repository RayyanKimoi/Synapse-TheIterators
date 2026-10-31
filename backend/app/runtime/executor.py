"""What a node does when the Ready-Node scheduler dispatches it.

LLM nodes call the LiteLLM gateway with the run's budget attached, so the
circuit breaker is evaluated before every outbound request; a trip fails the
node and halts its branch. Terminal LLM nodes are asked for a JSON object with
the IR's `required_output_keys`, which the contract check reads afterwards.

Tool nodes have no live client yet and return a labelled stub. Warm-cache hits
are still scheduled rather than computed until the semantic cache lands.
"""

import asyncio
import json
from dataclasses import dataclass

import networkx as nx

from ..compiler.scheduler import HaltBranch
from ..llm.gateway import BudgetExceededError, LLMGateway, RunBudget
from ..models.ir import NodeType, WorkflowIR, WorkflowNode
from .profile import NodeWork


@dataclass(frozen=True, slots=True)
class NodeOutcome:
    node_id: str
    output: str
    # litellm_proxy | ollama | mock (gateway), tool_stub, cache, breaker
    source: str
    tokens: int = 0
    cost_usd: float = 0.0
    cache_hit: bool = False
    # Match similarity of a measured cache hit. None for executed nodes and for
    # scheduled warm-cache hits, which are never measured.
    cache_similarity: float | None = None
    error: str | None = None


class NodeExecutor:
    """The `work` coroutine handed to `run_ready_nodes`; records each outcome."""

    def __init__(
        self,
        workflow: WorkflowIR,
        graph: nx.DiGraph,
        plan: dict[str, NodeWork],
        *,
        gateway: LLMGateway,
        budget: RunBudget,
        query: str,
        time_scale: float,
    ) -> None:
        self.nodes = workflow.node_map()
        self.plan = plan
        self.gateway = gateway
        self.budget = budget
        self.query = query
        self.time_scale = time_scale
        self.sinks = frozenset(node for node in graph.nodes if graph.out_degree(node) == 0)
        self.response_keys = list(workflow.test_assertions.required_output_keys) or None
        self.outcomes: dict[str, NodeOutcome] = {}

    async def __call__(self, node_id: str) -> int:
        node = self.nodes[node_id]
        planned = self.plan[node_id]

        if planned.cache_hit:
            await self._simulate(planned.duration_ms)
            self.outcomes[node_id] = NodeOutcome(
                node_id, f"[cache:scheduled] {node_id}", "cache", cache_hit=True
            )
            return planned.duration_ms

        if node.type is NodeType.TOOL_IO:
            await self._simulate(planned.duration_ms)
            self.outcomes[node_id] = NodeOutcome(node_id, _tool_stub(node), "tool_stub")
            return planned.duration_ms

        return await self._run_llm(node, planned)

    async def _run_llm(self, node: WorkflowNode, planned: NodeWork) -> int:
        try:
            result = await self.gateway.complete(
                prompt=self._prompt(node),
                system_prompt=f"You are the {node.persona}. {node.system_prompt}",
                model=node.model,
                budget=self.budget,
                response_keys=self.response_keys if node.id in self.sinks else None,
            )
        except BudgetExceededError as exc:
            self.outcomes[node.id] = NodeOutcome(
                node.id, "", "breaker", error=f"circuit breaker: {exc}"
            )
            raise HaltBranch(str(exc)) from exc

        if result.source == "mock":
            # No model in the loop: hold for the profiled latency so the race
            # timing stays realistic. Live calls report what they measured.
            await self._simulate(planned.duration_ms - result.latency_ms)
            duration = planned.duration_ms
        else:
            duration = result.latency_ms

        self.outcomes[node.id] = NodeOutcome(
            node.id,
            result.text,
            result.source,
            tokens=result.tokens_consumed,
            cost_usd=result.cost_usd,
        )
        return duration

    def _prompt(self, node: WorkflowNode) -> str:
        sections = [f"User query: {self.query}"]
        sections += [
            f"Output from {dependency}:\n{self.outcomes[dependency].output}"
            for dependency in node.dependencies
        ]
        return "\n\n".join(sections)

    async def _simulate(self, duration_ms: int) -> None:
        if duration_ms > 0:
            await asyncio.sleep(duration_ms / 1000 / self.time_scale)


def _tool_stub(node: WorkflowNode) -> str:
    # No live tool client is configured yet; say so rather than invent results.
    return json.dumps(
        {"tool": node.tool_name, "status": "offline_stub", "params": node.params},
        sort_keys=True,
    )
