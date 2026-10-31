"""Deterministic cost/latency profile and schedule builder.

Phase 1 has no live model in the loop, so node latencies, token counts and the
gains attributed to each optimization pass come from this hash-seeded profile.
It is deterministic by design: the arena race must look identical in rehearsal
and on stage. Phase 3 replaces `build_compiled_schedule` with the real
`asyncio.gather` engine and Phase 4 replaces the cache-hit path with Redis.
"""

import hashlib
from dataclasses import dataclass

from ..models.ir import NodeType, WorkflowIR, WorkflowNode

# Blended $2.00 per 1M tokens — reproduces the PRD section 8.2 sample
# (210 tokens -> $0.00042).
COST_PER_TOKEN_USD = 2e-6

CACHE_HIT_LATENCY_MS = 4
FRESH_SINK_LATENCY_MS = 350

BASE_LATENCY_MS = {NodeType.LLM_AGENT: 4_500, NodeType.TOOL_IO: 8_500}
BASE_TOKENS = {NodeType.LLM_AGENT: 480, NodeType.TOOL_IO: 0}

# Mock stand-ins for the Phase 3 optimization passes.
SPECULATIVE_PREFETCH_FACTOR = 0.18  # section 6.3: perceived tool latency -> ~0
PROMPT_FUSION_FACTOR = 0.55  # section 6.4: N round-trips collapsed into 1


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


def _cached_entry(node_id: str, start_ms: int) -> ScheduledNode:
    return ScheduledNode(node_id, start_ms, CACHE_HIT_LATENCY_MS, 0, 0.0, True)


def build_baseline_schedule(
    workflow: WorkflowIR,
    sequence: list[str],
    cached_ids: set[str],
    duration_caps_ms: dict[str, int] | None = None,
) -> dict[str, ScheduledNode]:
    """One node at a time: total latency is the sum over all nodes."""
    nodes = workflow.node_map()
    scheduled: dict[str, ScheduledNode] = {}
    cursor = 0
    for node_id in sequence:
        if node_id in cached_ids:
            entry = _cached_entry(node_id, cursor)
        else:
            node = nodes[node_id]
            tokens = node_tokens(node)
            latency = _capped(node_latency_ms(node), node_id, duration_caps_ms)
            entry = ScheduledNode(
                node_id, cursor, latency, tokens, tokens_cost_usd(tokens), False
            )
        scheduled[node_id] = entry
        cursor = entry.end_ms
    return _in_declaration_order(workflow, scheduled)


def build_compiled_schedule(
    workflow: WorkflowIR,
    tiers: list[list[str]],
    cached_ids: set[str],
    duration_caps_ms: dict[str, int] | None = None,
) -> dict[str, ScheduledNode]:
    """Tier T_k dispatches concurrently: tier latency is max, not sum."""
    nodes = workflow.node_map()
    scheduled: dict[str, ScheduledNode] = {}
    cursor = 0
    for tier in tiers:
        for node_id in tier:
            if node_id in cached_ids:
                scheduled[node_id] = _cached_entry(node_id, cursor)
                continue
            node = nodes[node_id]
            latency = node_latency_ms(node)
            tokens = node_tokens(node)
            if node.type is NodeType.TOOL_IO and len(tier) > 1:
                # Independent I/O in the same tier is speculatively pre-fetched
                # while the upstream agent is still generating tokens.
                latency = round(latency * SPECULATIVE_PREFETCH_FACTOR)
            if node.type is NodeType.LLM_AGENT and len(node.dependencies) > 1:
                # A fan-in agent fuses its upstream contexts into one prompt.
                latency = round(latency * PROMPT_FUSION_FACTOR)
                tokens = round(tokens * PROMPT_FUSION_FACTOR)
            scheduled[node_id] = ScheduledNode(
                node_id,
                cursor,
                _capped(latency, node_id, duration_caps_ms),
                tokens,
                tokens_cost_usd(tokens),
                False,
            )
        cursor = max(scheduled[node_id].end_ms for node_id in tier)
    return _in_declaration_order(workflow, scheduled)


def _capped(latency_ms: int, node_id: str, caps: dict[str, int] | None) -> int:
    if not caps or node_id not in caps:
        return latency_ms
    return min(latency_ms, caps[node_id])


def _in_declaration_order(
    workflow: WorkflowIR, scheduled: dict[str, ScheduledNode]
) -> dict[str, ScheduledNode]:
    return {node.id: scheduled[node.id] for node in workflow.nodes}


def schedule_latency_ms(scheduled: dict[str, ScheduledNode]) -> int:
    return max((entry.end_ms for entry in scheduled.values()), default=0)
