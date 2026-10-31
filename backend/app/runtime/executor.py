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

Adjacent read-only LLM nodes are merged by `fusion.plan_fusion` into a single
request: the group leader calls the model once and keeps every member's slice,
so each follower costs a dictionary lookup rather than a round trip.

Tool nodes have no live client yet and return a labelled stub, cached under the
short real-time TTL.
"""

import asyncio
import json
import time
from dataclasses import dataclass

import networkx as nx

from ..compiler.scheduler import HaltBranch
from ..llm.cache import SemanticCache, node_namespace, ttl_for
from ..llm.gateway import BudgetExceededError, LLMGateway, RunBudget
from ..models.ir import NodeType, WorkflowIR, WorkflowNode
from .contract import extract_json_object
from .fusion import FusionGroup, fused_system_prompt
from .profile import NodeWork, node_latency_ms


@dataclass(frozen=True, slots=True)
class NodeOutcome:
    node_id: str
    output: str
    # litellm_proxy | ollama | mock (gateway), tool_stub, tool_prefetched,
    # cache_redis, cache_memory, breaker
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
        prefetch: frozenset[str] = frozenset(),
        fusion: dict[str, FusionGroup] | None = None,
        prime: bool = False,
    ) -> None:
        self.prime = prime
        self.graph = graph
        self.prefetch = prefetch
        self.fusion = fusion or {}
        self._speculated: dict[str, asyncio.Task[str]] = {}
        # Follower output waiting to be collected, written by the group leader.
        self._fused_slices: dict[str, str] = {}
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
        if self.prime and node_id in self.sinks:
            # Priming deliberately leaves the terminal node cold, so the warm
            # run still has real work to finish on and a non-zero clock.
            return 0

        question, context = self._prompt_parts(node)
        namespace = node_namespace(self.scope, node)

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
        elif node_id in self.fusion:
            outcome, duration = await self._run_fused(node, _joined(question, context))
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

    async def _run_fused(self, node: WorkflowNode, prompt: str) -> tuple[NodeOutcome, int]:
        """One member of a fused chain.

        The leader issues the single merged request and keeps every member's
        slice; each follower then costs a dictionary lookup instead of a round
        trip. Tokens and spend are booked once, on the leader, because one call
        was made -- counting them again per follower would invent usage.
        """
        group = self.fusion[node.id]
        if node.id != group.leader:
            slice_text = self._fused_slices.pop(node.id, "")
            return NodeOutcome(node.id, slice_text, "fused_follower"), 0

        planned = self.plan[node.id]
        self._speculate(node)
        try:
            result = await self.gateway.complete(
                prompt=prompt,
                system_prompt=fused_system_prompt(group),
                model=node.model,
                # One call now carries every member's output.
                max_tokens=512 * len(group.members),
                budget=self.budget,
                response_keys=None,  # the fused signature already states them
            )
        except BudgetExceededError as exc:
            self.outcomes[node.id] = NodeOutcome(
                node.id, "", "breaker", error=f"circuit breaker: {exc}"
            )
            raise HaltBranch(str(exc)) from exc

        merged = extract_json_object(result.text) or {}
        for member, field in group.fields.items():
            if member != node.id:
                self._fused_slices[member] = str(merged.get(field, ""))

        if result.source == "mock":
            await self._simulate(planned.duration_ms - result.latency_ms)
            duration = planned.duration_ms
        else:
            duration = result.latency_ms

        leader_field = group.fields[node.id]
        return (
            NodeOutcome(
                node.id,
                str(merged.get(leader_field, result.text)),
                # The raw gateway source, so `llm_calls` still counts the one
                # request the group made. `fused_follower` is what marks the
                # calls fusion removed.
                result.source,
                tokens=result.tokens_consumed,
                cost_usd=result.cost_usd,
            ),
            duration,
        )

    async def _run_tool(self, node: WorkflowNode) -> tuple[NodeOutcome, int]:
        speculated = self._speculated.pop(node.id, None)
        if speculated is not None:
            started = time.perf_counter()
            output = await speculated
            # Whatever overlapped the parent's generation is already paid for;
            # only the remainder is still on the critical path. This is the
            # measured number that used to be a 0.18 multiplier.
            remaining = int((time.perf_counter() - started) * 1000 * self.time_scale)
            return NodeOutcome(node.id, output, "tool_prefetched"), remaining

        duration = self.plan[node.id].duration_ms
        await self._simulate(duration)
        return NodeOutcome(node.id, _tool_stub(node), "tool_stub"), duration

    async def _tool_request(self, node: WorkflowNode) -> str:
        """The outbound tool call on its own, with no cache or bookkeeping.

        Safe to start before the parent has produced anything, because the
        request is determined entirely by the node's declared `params`.
        """
        await self._simulate(node_latency_ms(node))
        return _tool_stub(node)

    def _speculate(self, node: WorkflowNode) -> None:
        """Fire eligible downstream tool calls now, while this node generates."""
        for child_id in self.graph.successors(node.id):
            if child_id in self.prefetch and child_id not in self._speculated:
                self._speculated[child_id] = asyncio.create_task(
                    self._tool_request(self.nodes[child_id])
                )

    async def aclose(self) -> None:
        """Drop speculations nothing ended up waiting for -- a branch that
        halted, or a tool the cache answered after the request was already out."""
        pending = list(self._speculated.values())
        self._speculated.clear()
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    async def _run_llm(self, node: WorkflowNode, prompt: str) -> tuple[NodeOutcome, int]:
        planned = self.plan[node.id]
        # Before the await, so the tool requests overlap the decode rather than
        # queueing behind it.
        self._speculate(node)
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
