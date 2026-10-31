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

Tool nodes make their real outbound call through `runtime.tools`, cached under
the short real-time TTL. A tool that cannot run fails its node and severs the
branch rather than returning an invented payload.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass

import networkx as nx

from ..compiler.scheduler import HaltBranch
from ..llm.cache import SemanticCache, node_namespace, ttl_for
from ..llm.gateway import (
    BudgetExceededError,
    LLMGateway,
    LLMUnavailableError,
    RunBudget,
)
from ..models.ir import NodeType, WorkflowIR, WorkflowNode
from .contract import extract_json_object
from .fusion import FusionGroup, fused_system_prompt
from .fusion import response_keys as fusion_response_keys
from .fusion import slice_for
from ..observability import fail, record, span
from .tools import ToolError, run_tool
from .profile import NodeWork, node_latency_ms

logger = logging.getLogger(__name__)


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
        # Leaders whose merged response could not be split; their groups run
        # unfused for the rest of this run.
        self._fusion_failed: set[str] = set()
        self.nodes = workflow.node_map()
        self.plan = plan
        self.gateway = gateway
        self.settings = gateway.settings
        self.cache = cache
        self.scope = scope
        self.budget = budget
        self.query = query
        self.time_scale = time_scale
        self.sinks = frozenset(node for node in graph.nodes if graph.out_degree(node) == 0)
        self.response_keys = list(workflow.test_assertions.required_output_keys) or None
        self.outcomes: dict[str, NodeOutcome] = {}

    async def __call__(self, node_id: str) -> int:
        with span(
            f"node {node_id}",
            **{
                "synapse.node.id": node_id,
                "synapse.node.type": self.nodes[node_id].type.value,
                "synapse.pipeline": self.scope,
            },
        ) as active:
            try:
                duration = await self._execute(node_id)
            except HaltBranch as halt:
                fail(active, halt)
                raise
            outcome = self.outcomes.get(node_id)
            record(
                active,
                **{
                    "synapse.node.duration_ms": duration,
                    "synapse.node.source": outcome.source if outcome else None,
                    "synapse.node.tokens": outcome.tokens if outcome else None,
                    "synapse.node.cost_usd": outcome.cost_usd if outcome else None,
                    "synapse.cache.hit": outcome.cache_hit if outcome else None,
                    "synapse.cache.similarity": (
                        outcome.cache_similarity if outcome else None
                    ),
                    "synapse.budget.spent_usd": self.budget.spent_usd,
                    "synapse.budget.tripped": self.budget.tripped,
                },
            )
            return duration

    async def _execute(self, node_id: str) -> int:
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

        group = self.fusion.get(node_id)
        if node.type is NodeType.TOOL_IO:
            outcome, duration = await self._run_tool(node)
        elif (
            group is not None
            and group.leader not in self._fusion_failed
            # A follower may only take the fused path when its slice is really
            # waiting. If the leader was served from cache it never made the
            # merged call, so there is nothing to collect and the follower has
            # to earn its own answer.
            and (node_id == group.leader or node_id in self._fused_slices)
        ):
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
            return NodeOutcome(
                node.id, self._fused_slices.pop(node.id), "fused_follower"
            ), 0

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
                response_keys=fusion_response_keys(group),
            )
        except BudgetExceededError as exc:
            self.outcomes[node.id] = NodeOutcome(
                node.id, "", "breaker", error=f"circuit breaker: {exc}"
            )
            raise HaltBranch(str(exc)) from exc
        except LLMUnavailableError as exc:
            # No completion was produced. Fail the node rather than let an
            # invented answer reach the contract check or the cache.
            self.outcomes[node.id] = NodeOutcome(
                node.id, "", "llm_error", error=f"model unavailable: {exc}"
            )
            raise HaltBranch(str(exc)) from exc

        merged = extract_json_object(result.text) or {}
        unfilled = [
            member
            for member in group.members
            if any(
                not str(merged.get(name, "")).strip() for name in group.fields[member]
            )
        ]
        if unfilled:
            # The model did not honour the merged contract -- a dropped closing
            # brace is enough. The group cannot be split, so abandon fusion for
            # this run and let every member make its own call. That costs the
            # round trips fusion saved, but no node is handed a silent blank.
            logger.warning(
                "fused group %s could not be split (%s unfilled); "
                "falling back to one call per node",
                "+".join(group.members),
                ", ".join(unfilled),
            )
            self._fusion_failed.add(group.leader)
            return await self._run_llm(node, prompt)

        for member, fields in group.fields.items():
            if member != node.id:
                self._fused_slices[member] = slice_for(merged, fields)

        if result.source == "mock":
            await self._simulate(planned.duration_ms - result.latency_ms)
            duration = planned.duration_ms
        else:
            duration = result.latency_ms

        return (
            NodeOutcome(
                node.id,
                slice_for(merged, group.fields[node.id]),
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
            try:
                output = await speculated
            except ToolError as exc:
                return self._tool_failed(node, exc)
            # Whatever overlapped the parent's generation is already paid for;
            # only the remainder is still on the critical path. This is the
            # measured number that used to be a 0.18 multiplier.
            remaining = int((time.perf_counter() - started) * 1000 * self.time_scale)
            return NodeOutcome(node.id, output, "tool_prefetched"), remaining

        try:
            output, measured_ms = await self._tool_call(node)
        except ToolError as exc:
            return self._tool_failed(node, exc)
        return NodeOutcome(node.id, output, self._tool_source()), measured_ms

    def _tool_failed(self, node: WorkflowNode, exc: ToolError) -> tuple[NodeOutcome, int]:
        """A tool that cannot run fails its node and severs the branch.

        The alternative -- returning a plausible-looking payload -- would feed
        invented search results to every agent downstream of it.
        """
        self.outcomes[node.id] = NodeOutcome(
            node.id, "", "tool_error", error=f"tool failed: {exc}"
        )
        raise HaltBranch(str(exc)) from exc

    def _tool_source(self) -> str:
        return "tool_stub" if self.settings.llm_offline_mode else "tool_live"

    async def _tool_call(self, node: WorkflowNode) -> tuple[str, int]:
        """Run the tool, holding for the simulated duration only when offline."""
        output, measured_ms = await run_tool(node, self.query, self.settings)
        if self.settings.llm_offline_mode:
            await self._simulate(measured_ms)
        return output, measured_ms

    async def _tool_request(self, node: WorkflowNode) -> str:
        """The outbound tool call on its own, with no cache or bookkeeping.

        Safe to start before the parent has produced anything, because the
        request is determined entirely by the node's declared `params`.
        """
        output, _ = await self._tool_call(node)
        return output

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
        except LLMUnavailableError as exc:
            # No completion was produced. Fail the node rather than let an
            # invented answer reach the contract check or the cache.
            self.outcomes[node.id] = NodeOutcome(
                node.id, "", "llm_error", error=f"model unavailable: {exc}"
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


