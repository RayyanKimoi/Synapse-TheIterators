"""Deterministic cost/latency profile and schedule builder.

When no model is in the loop, per-node latency comes from this hash-seeded
profile. It is deterministic by design: the arena race must look identical in
rehearsal and on stage. At run time, LLM token counts and cost come from the
LiteLLM gateway instead (`runtime/executor.py`); the profile's tokens feed only
the planner's up-front projection and the cost a cache hit avoids.

Placement of nodes in time is NOT computed here for the compiled pipeline.
That belongs to the Ready-Node scheduler: this module says how long a node
takes, the scheduler says when it runs.
"""

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass

import networkx as nx

from ..compiler.scheduler import NodeTiming, ready_node_timings
from ..models.ir import NodeType, WorkflowIR, WorkflowNode
from .fusion import FusionGroup

# Blended $2.00 per 1M tokens — reproduces the PRD section 8.2 sample
# (210 tokens -> $0.00042).
COST_PER_TOKEN_USD = 2e-6

BASE_LATENCY_MS = {NodeType.LLM_AGENT: 4_500, NodeType.TOOL_IO: 8_500}
BASE_TOKENS = {NodeType.LLM_AGENT: 480, NodeType.TOOL_IO: 0}

@dataclass(frozen=True, slots=True)
class NodeWork:
    """How much work a node represents. Says nothing about when it runs."""

    node_id: str
    duration_ms: int
    tokens: int
    cost_usd: float


@dataclass(frozen=True, slots=True)
class ScheduledNode:
    node_id: str
    start_ms: int
    duration_ms: int
    tokens: int
    cost_usd: float

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.duration_ms


def _jitter(node_id: str, spread: float = 0.15) -> float:
    """Stable per-node multiplier in [1-spread, 1+spread]."""
    digest = hashlib.sha256(node_id.encode()).digest()
    unit = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
    return 1.0 + (unit * 2 - 1) * spread


def tokens_cost_usd(tokens: int) -> float:
    return round(tokens * COST_PER_TOKEN_USD, 6)


def node_latency_ms(node: WorkflowNode) -> int:
    return round(BASE_LATENCY_MS[node.type] * _jitter(node.id))


def node_tokens(node: WorkflowNode) -> int:
    return round(BASE_TOKENS[node.type] * _jitter(node.id))


def baseline_reference_costs(workflow: WorkflowIR) -> dict[str, float]:
    """Per-node cost of an unoptimized, uncached run — the savings baseline."""
    return {node.id: tokens_cost_usd(node_tokens(node)) for node in workflow.nodes}


def _prefetch_head_start_ms(
    node: WorkflowNode, graph: nx.DiGraph, nodes: dict[str, WorkflowNode]
) -> int:
    """How much of this tool call PASTE can hide behind its parent.

    Speculation starts when the parent starts generating, so the overlap is the
    parent generation time -- never more. A tool slower than the generation it
    hides behind still has the difference left to run.
    """
    return max(
        (
            node_latency_ms(nodes[parent])
            for parent in graph.predecessors(node.id)
            if nodes[parent].type is NodeType.LLM_AGENT
        ),
        default=0,
    )


def _fused_work(
    node: WorkflowNode, group: FusionGroup, nodes: dict[str, WorkflowNode]
) -> tuple[int, int]:
    """What one member of a fused chain costs.

    A follower costs nothing: the leader already produced its output. The
    leader generates every member's field in one pass, so it keeps the group's
    tokens but pays a single round trip instead of one per member.

    shortcut: the merged call is priced at the slowest member's latency, which
    ignores the extra decode for the additional fields. Split BASE_TOKENS into
    prompt and completion halves to model that properly.
    """
    if node.id != group.leader:
        return 0, 0
    return (
        max(node_latency_ms(nodes[member]) for member in group.members),
        sum(node_tokens(nodes[member]) for member in group.members),
    )


def build_node_work(
    workflow: WorkflowIR,
    graph: nx.DiGraph,
    *,
    compiled: bool,
    prefetch: frozenset[str] = frozenset(),
    fusion: Mapping[str, FusionGroup] | None = None,
) -> dict[str, NodeWork]:
    """Per-node duration/tokens/cost, with V3 gains applied when compiled.

    `prefetch` names the tool nodes PASTE will speculate on; see
    `paste.prefetchable`. Their duration is reduced by the overlap the live
    runtime actually measures, so the projection and the race agree.

    `fusion` names the merged LLM chains; see `fusion.plan_fusion`. A chain
    costs one request, so its leader carries the whole group and its followers
    carry nothing -- exactly what the runtime books.
    """
    fusion = fusion or {}
    nodes = workflow.node_map()
    work: dict[str, NodeWork] = {}
    for node in workflow.nodes:
        latency = node_latency_ms(node)
        tokens = node_tokens(node)

        if compiled:
            if node.id in prefetch:
                latency = max(
                    latency - _prefetch_head_start_ms(node, graph, nodes), 0
                )
            group = fusion.get(node.id)
            if group is not None:
                latency, tokens = _fused_work(node, group, nodes)

        work[node.id] = NodeWork(node.id, latency, tokens, tokens_cost_usd(tokens))
    return work


def _schedule_from(
    workflow: WorkflowIR, work: dict[str, NodeWork], timings: dict[str, NodeTiming]
) -> dict[str, ScheduledNode]:
    return {
        node.id: ScheduledNode(
            node.id,
            timings[node.id].start_ms,
            work[node.id].duration_ms,
            work[node.id].tokens,
            work[node.id].cost_usd,
        )
        for node in workflow.nodes  # declaration order keeps the UI stable
    }


def build_baseline_schedule(
    workflow: WorkflowIR,
    sequence: list[str],
    graph: nx.DiGraph | None = None,
) -> dict[str, ScheduledNode]:
    """One node at a time: total latency is the sum over all nodes."""
    graph = graph if graph is not None else nx.DiGraph()
    work = build_node_work(workflow, graph, compiled=False)
    timings: dict[str, NodeTiming] = {}
    cursor = 0
    for node_id in sequence:
        timings[node_id] = NodeTiming(node_id, cursor, cursor + work[node_id].duration_ms)
        cursor = timings[node_id].end_ms
    return _schedule_from(workflow, work, timings)


def build_compiled_schedule(
    workflow: WorkflowIR,
    graph: nx.DiGraph,
    prefetch: frozenset[str] = frozenset(),
    fusion: Mapping[str, FusionGroup] | None = None,
) -> dict[str, ScheduledNode]:
    """Ready-Node placement: a node starts when its own parents finish.

    No tier barrier. This is the analytical twin of the live scheduler and
    produces the same numbers it records.
    """
    work = build_node_work(
        workflow, graph, compiled=True, prefetch=prefetch, fusion=fusion
    )
    timings = ready_node_timings(graph, lambda node_id: work[node_id].duration_ms)
    return _schedule_from(workflow, work, timings)


def schedule_latency_ms(scheduled: dict[str, ScheduledNode]) -> int:
    return max((entry.end_ms for entry in scheduled.values()), default=0)
