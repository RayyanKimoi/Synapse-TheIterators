"""Compilation plan returned by POST /api/v1/compile.

Runs the Phase 1 passes (validate -> cycle check -> topological depth -> tier
partition) and reports the projected gains that feed the Optimization
Matchmaker deck in PRD section 9.3.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..models.ir import NodeType, WorkflowIR
from ..runtime.profile import (
    ScheduledNode,
    build_baseline_schedule,
    build_compiled_schedule,
    schedule_latency_ms,
)
from .dag import assert_acyclic, baseline_sequence, build_graph, execution_tiers, topological_depths


class PipelineEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latency_ms: int
    tokens: int
    cost_usd: float


class OptimizationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["parallelize", "prompt_fusion"]
    title: str
    rationale: str
    node_ids: list[str]
    projected_latency_saved_ms: int
    projected_tokens_saved: int
    projected_cost_saved_usd: float


class CompilePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    name: str
    node_count: int
    edge_count: int
    max_depth: int
    node_depths: dict[str, int]
    execution_tiers: list[list[str]]
    baseline_sequence: list[str]
    baseline_estimate: PipelineEstimate
    compiled_estimate: PipelineEstimate
    latency_reduction_pct: float
    optimization_candidates: list[OptimizationCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _estimate(scheduled: dict[str, ScheduledNode]) -> PipelineEstimate:
    return PipelineEstimate(
        latency_ms=schedule_latency_ms(scheduled),
        tokens=sum(entry.tokens for entry in scheduled.values()),
        cost_usd=round(sum(entry.cost_usd for entry in scheduled.values()), 6),
    )


def _candidates(
    workflow: WorkflowIR,
    tiers: list[list[str]],
    baseline: dict[str, ScheduledNode],
    compiled: dict[str, ScheduledNode],
) -> list[OptimizationCandidate]:
    found: list[OptimizationCandidate] = []

    for depth, tier in enumerate(tiers):
        if len(tier) < 2:
            continue
        serial = sum(baseline[node_id].duration_ms for node_id in tier)
        parallel = max(compiled[node_id].duration_ms for node_id in tier)
        found.append(
            OptimizationCandidate(
                id=f"opt_parallelize_t{depth}",
                kind="parallelize",
                title=f"Parallelize {len(tier)} Independent Tasks",
                rationale=(
                    f"Tier {depth} holds {len(tier)} nodes with no data dependency "
                    "between them; they can be dispatched concurrently via asyncio.gather."
                ),
                node_ids=list(tier),
                projected_latency_saved_ms=max(serial - parallel, 0),
                projected_tokens_saved=0,
                projected_cost_saved_usd=0.0,
            )
        )

    for node in workflow.nodes:
        if node.type is not NodeType.LLM_AGENT or len(node.dependencies) < 2:
            continue
        tokens_saved = baseline[node.id].tokens - compiled[node.id].tokens
        found.append(
            OptimizationCandidate(
                id=f"opt_fusion_{node.id}",
                kind="prompt_fusion",
                title=f"Prompt Fusion: Merge {node.persona} Context",
                rationale=(
                    f"'{node.id}' fans in {len(node.dependencies)} upstream contexts. "
                    "Fusing them into one structured prompt removes redundant "
                    "round-trips and shrinks the KV cache footprint."
                ),
                node_ids=[node.id, *node.dependencies],
                projected_latency_saved_ms=max(
                    baseline[node.id].duration_ms - compiled[node.id].duration_ms, 0
                ),
                projected_tokens_saved=max(tokens_saved, 0),
                projected_cost_saved_usd=round(
                    max(baseline[node.id].cost_usd - compiled[node.id].cost_usd, 0.0), 6
                ),
            )
        )

    return found


def compile_workflow(workflow: WorkflowIR) -> CompilePlan:
    """Raises CompileError when the graph is cyclic."""
    graph = build_graph(workflow)
    assert_acyclic(graph)

    depths = topological_depths(graph)
    tiers = execution_tiers(workflow, depths)
    sequence = baseline_sequence(graph, workflow.declaration_index())

    baseline = build_baseline_schedule(workflow, sequence, cached_ids=set())
    compiled = build_compiled_schedule(workflow, tiers, cached_ids=set())
    baseline_estimate = _estimate(baseline)
    compiled_estimate = _estimate(compiled)

    reduction = 0.0
    if baseline_estimate.latency_ms:
        reduction = round(
            (1 - compiled_estimate.latency_ms / baseline_estimate.latency_ms) * 100, 1
        )

    warnings: list[str] = []
    sla_ms = workflow.test_assertions.max_acceptable_latency_ms
    if baseline_estimate.latency_ms > sla_ms:
        warnings.append(
            f"baseline latency {baseline_estimate.latency_ms} ms exceeds the "
            f"{sla_ms} ms assertion; compilation is required to meet it"
        )
    if compiled_estimate.cost_usd > workflow.budget_limit_usd:
        warnings.append(
            f"projected cost ${compiled_estimate.cost_usd} exceeds budget_limit_usd "
            f"${workflow.budget_limit_usd}"
        )

    return CompilePlan(
        workflow_id=workflow.workflow_id,
        name=workflow.name,
        node_count=graph.number_of_nodes(),
        edge_count=graph.number_of_edges(),
        max_depth=max(depths.values()),
        node_depths=depths,
        execution_tiers=tiers,
        baseline_sequence=sequence,
        baseline_estimate=baseline_estimate,
        compiled_estimate=compiled_estimate,
        latency_reduction_pct=reduction,
        optimization_candidates=_candidates(workflow, tiers, baseline, compiled),
        warnings=warnings,
    )
