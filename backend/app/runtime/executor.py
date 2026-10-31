"""What a node does when the Ready-Node scheduler dispatches it.

Every node is probed against the semantic cache first. A hit is served for zero
tokens and zero spend, which is also why it is probed *before* the budget: a
cached answer costs nothing, so it is still served once the circuit breaker has
tripped. On a miss, LLM nodes call the LiteLLM gateway with the run's budget
attached, so the breaker is evaluated before every outbound request; a trip
fails the node and halts its branch. Terminal LLM nodes are asked for a JSON
object with the IR's `required_output_keys`, which the contract check reads
afterwards.

Cache namespaces are scoped per pipeline as well as per node: the arena races
the baseline and the compiled run on the same query, and a shared cache would
let whichever ran second answer entirely from the first one's work.

Tool nodes have no live client yet and return a labelled stub, cached under the
short real-time TTL.
"""

import asyncio
import json
from dataclasses import dataclass

import networkx as nx

from ..compiler.scheduler import HaltBranch
from ..llm.cache import SemanticCache, ttl_for
from ..llm.gateway import BudgetExceededError, LLMGateway, RunBudget
from ..models.ir import NodeType, WorkflowIR, WorkflowNode
from .profile import NodeWork


@dataclass(frozen=True, slots=True)
class NodeOutcome:
    node_id: str
    output: str
    # litellm_proxy | ollama | mock (gateway), tool_stub, cache_redis,
    # cache_memory, breaker
    source: str
    tokens: int = 0
    cost_usd: float = 0.0
    cache_hit: bool = False
    # Measured cosine similarity of the match that served this node. None for
    # nodes that actually executed.
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
        cache: SemanticCache,
        scope: str,
        budget: RunBudget,
        query: str,
        time_scale: float,
    ) -> None:
        self.nodes = workflow.node_map()
        self.plan = plan
        self.gateway = gateway
        self.cache = cache
        self.scope = scope
        self.budget = budget
        self.query = query
        self.time_scale = time_scale
        self.sinks = frozenset(node for node in graph.nodes if graph.out_degree(node) == 0)
        self.response_keys = list(workflow.test_assertions.required_output_keys) or None
        self.outcomes: dict[str, NodeOutcome] = {}

    async def __call__(self, node_id: str) -> int:
        node = self.nodes[node_id]
        question, context = self._prompt_parts(node)
        namespace = f"{self.scope}|{node_id}|{node.model or node.tool_name}"

        vectors, hit = await self.cache.probe(namespace, query=question, context=context)
        if hit is not None:
            self.outcomes[node_id] = NodeOutcome(
                node_id,
                hit.text,
                f"cache_{hit.backend}",
                cache_hit=True,
                cache_similarity=hit.similarity,
            )
            return hit.latency_ms

        if node.type is NodeType.TOOL_IO:
            outcome, duration = await self._run_tool(node)
        else:
            outcome, duration = await self._run_llm(node, _joined(question, context))

        # Awaited, not fired and forgotten: the write never blocks the event
        # loop, and a run that warms the cache must be able to rely on it.
        await self.cache.store(
            namespace,
            query=question,
            context=context,
            text=outcome.output,
            vectors=vectors,
            ttl_s=ttl_for(node.type),
        )
        self.outcomes[node.id] = outcome
        return duration

    async def _run_tool(self, node: WorkflowNode) -> tuple[NodeOutcome, int]:
        duration = self.plan[node.id].duration_ms
        await self._simulate(duration)
        return NodeOutcome(node.id, _tool_stub(node), "tool_stub"), duration

    async def _run_llm(self, node: WorkflowNode, prompt: str) -> tuple[NodeOutcome, int]:
        planned = self.plan[node.id]
        try:
            result = await self.gateway.complete(
                prompt=prompt,
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

        return (
            NodeOutcome(
                node.id,
                result.text,
                result.source,
                tokens=result.tokens_consumed,
                cost_usd=result.cost_usd,
            ),
            duration,
        )

    def _prompt_parts(self, node: WorkflowNode) -> tuple[str, str]:
        """The prompt split the way the cache scores it: question, then the
        upstream context it is answered against."""
        context = "\n\n".join(
            f"Output from {dependency}:\n{self.outcomes[dependency].output}"
            for dependency in node.dependencies
        )
        return f"User query: {self.query}", context

    async def _simulate(self, duration_ms: int) -> None:
        if duration_ms > 0:
            await asyncio.sleep(duration_ms / 1000 / self.time_scale)


def _joined(question: str, context: str) -> str:
    return f"{question}\n\n{context}" if context else question


def _tool_stub(node: WorkflowNode) -> str:
    # No live tool client is configured yet; say so rather than invent results.
    return json.dumps(
        {"tool": node.tool_name, "status": "offline_stub", "params": node.params},
        sort_keys=True,
    )
