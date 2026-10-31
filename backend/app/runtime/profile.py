"""Deterministic cost/latency profile and schedule builder.

There is no live model in the loop yet, so per-node latency and token counts
come from this hash-seeded profile. It is deterministic by design: the arena
race must look identical in rehearsal and on stage. A later phase swaps
`node_latency_ms`/`node_tokens` for measured values from the LiteLLM gateway
and the Redis semantic cache without touching the scheduler.

Placement of nodes in time is NOT computed here for the compiled pipeline.
That belongs to the Ready-Node scheduler: this module says how long a node
takes, the scheduler says when it runs.
"""

import hashlib
from dataclasses import dataclass

import networkx as nx

from ..compiler.scheduler import NodeTiming, ready_node_timings
from ..models.ir import NodeType, WorkflowIR, WorkflowNode

# Blended $2.00 per 1M tokens — reproduces the PRD section 8.2 sample
# (210 tokens -> $0.00042).
COST_PER_TOKEN_USD = 2e-6

CACHE_HIT_LATENCY_MS = 4
FRESH_SINK_LATENCY_MS = 350

BASE_LATENCY_MS = {NodeType.LLM_AGENT: 4_500, NodeType.TOOL_IO: 8_500}
BASE_TOKENS = {NodeType.LLM_AGENT: 480, NodeType.TOOL_IO: 0}

# Stand-ins for the V3 optimization passes.
SPECULATIVE_PREFETCH_FACTOR = 0.18  # PASTE: perceived tool latency -> ~0
PROMPT_FUSION_FACTOR = 0.55  # DSPy fusion: N round-trips collapsed into 1


@dataclass(frozen=True, slots=True)
class NodeWork:
    """How much work a node represents. Says nothing about when it runs."""

    node_id: str
    duration_ms: int
    tokens: int
    cost_usd: float
    cache_hit: bool


@dataclass(frozen=True, slots=True)
class ScheduledNode:
    node_id: str
    start_ms: int
    duration_ms: int
    tokens: int
    cost_usd: float
    cache_hit: bool

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


def _capped(latency_ms: int, node_id: str, caps: dict[str, int] | None) -> int:
    if not caps or node_id not in caps:
        return latency_ms
    return min(latency_ms, caps[node_id])


def _is_speculatively_prefetched(node: WorkflowNode, graph: nx.DiGraph) -> bool:
    """True when this tool call is fired concurrently with sibling dispatches.

    Replaces the old `len(tier) > 1` test, which depended on depth tiers. A
    tool node whose parent fans out to several children is issued by the
    Ready-Node scheduler alongside those siblings, so PASTE can speculate on it
    while the upstream agent is still generating tokens.
    """
    if node.type is not NodeType.TOOL_IO:
        return False
    return any(graph.out_degree(parent) > 1 for parent in graph.predecessors(node.id))


def build_node_work(
    workflow: WorkflowIR,
    graph: nx.DiGraph,
    *,
    compiled: bool,
    cached_ids: set[str],
    duration_caps_ms: dict[str, int] | None = None,
) -> dict[str, NodeWork]:
    """Per-node duration/tokens/cost, with V3 gains applied when compiled."""
    work: dict[str, NodeWork] = {}
    for node in workflow.nodes:
        if node.id in cached_ids:
            work[node.id] = NodeWork(node.id, CACHE_HIT_LATENCY_MS, 0, 0.0, True)
            continue

        latency = node_latency_ms(node)
        tokens = node_tokens(node)

        if compiled:
            if _is_speculatively_prefetched(node, graph):
                latency = round(latency * SPECULATIVE_PREFETCH_FACTOR)
            if node.type is NodeType.LLM_AGENT and len(node.dependencies) > 1:
                # A fan-in agent fuses its upstream contexts into one prompt.
                latency = round(latency * PROMPT_FUSION_FACTOR)
                tokens = round(tokens * PROMPT_FUSION_FACTOR)

        work[node.id] = NodeWork(
            node.id,
            _capped(latency, node.id, duration_caps_ms),
            tokens,
            tokens_cost_usd(tokens),
            False,
        )
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
            work[node.id].cache_hit,
        )
        for node in workflow.nodes  # declaration order keeps the UI stable
    }


def build_baseline_schedule(
    workflow: WorkflowIR,
    sequence: list[str],
    cached_ids: set[str],
    duration_caps_ms: dict[str, int] | None = None,
    graph: nx.DiGraph | None = None,
) -> dict[str, ScheduledNode]:
    """One node at a time: total latency is the sum over all nodes."""
    graph = graph if graph is not None else nx.DiGraph()
    work = build_node_work(
        workflow,
        graph,
        compiled=False,
        cached_ids=cached_ids,
        duration_caps_ms=duration_caps_ms,
    )
    timings: dict[str, NodeTiming] = {}
    cursor = 0
    for node_id in sequence:
        timings[node_id] = NodeTiming(node_id, cursor, cursor + work[node_id].duration_ms)
        cursor = timings[node_id].end_ms
    return _schedule_from(workflow, work, timings)


def build_compiled_schedule(
    workflow: WorkflowIR,
    graph: nx.DiGraph,
    cached_ids: set[str],
    duration_caps_ms: dict[str, int] | None = None,
) -> dict[str, ScheduledNode]:
    """Ready-Node placement: a node starts when its own parents finish.

    No tier barrier. This is the analytical twin of the live scheduler and
    produces the same numbers it records.
    """
    work = build_node_work(
        workflow,
        graph,
        compiled=True,
        cached_ids=cached_ids,
        duration_caps_ms=duration_caps_ms,
    )
    timings = ready_node_timings(graph, lambda node_id: work[node_id].duration_ms)
    return _schedule_from(workflow, work, timings)


def schedule_latency_ms(scheduled: dict[str, ScheduledNode]) -> int:
    return max((entry.end_ms for entry in scheduled.values()), default=0)
