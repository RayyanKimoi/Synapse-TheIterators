"""Compilation plan returned by POST /api/v1/compile.

Runs the V1 passes (validate -> cycle check -> in_degree assignment) and
reports the projected gains that feed the Optimization Matchmaker deck.

`node_depths` / `execution_tiers` are retained as *canvas layout* metadata for
the arena. They do not describe dispatch: `node_in_degrees` is the countdown
the Ready-Node scheduler actually consumes.
"""

from typing import Literal

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field

from ..config import get_settings
from ..models.ir import NodeType, WorkflowIR
from ..runtime.profile import (
    ScheduledNode,
    build_baseline_schedule,
    build_compiled_schedule,
    schedule_latency_ms,
)
from .dag import assert_acyclic, baseline_sequence, build_graph, layout_tiers, topological_depths
from .scheduler import in_degrees


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
    node_in_degrees: dict[str, int] = Field(default_factory=dict)
    max_concurrency: int = 0
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


def dispatch_groups(graph: nx.DiGraph) -> list[list[str]]:
    """Sets of nodes the Ready-Node scheduler releases together.

    A group is a fan-out point's children (they become ready on the same
    completion event), plus the roots, which are enqueued at startup. Unlike
    depth tiers these never act as a barrier — they only identify where
    concurrency is actually available.
    """
    groups: list[list[str]] = []
    roots = [node for node, degree in graph.in_degree() if degree == 0]
    if len(roots) > 1:
        groups.append(roots)
    for node in nx.topological_sort(graph):
        children = list(graph.successors(node))
        if len(children) > 1:
            groups.append(children)
    return groups


def _candidates(
    workflow: WorkflowIR,
    graph: nx.DiGraph,
    baseline: dict[str, ScheduledNode],
    compiled: dict[str, ScheduledNode],
) -> list[OptimizationCandidate]:
    found: list[OptimizationCandidate] = []

    for index, group in enumerate(dispatch_groups(graph)):
        serial = sum(baseline[node_id].duration_ms for node_id in group)
        concurrent = max(compiled[node_id].duration_ms for node_id in group)
        found.append(
            OptimizationCandidate(
                id=f"opt_parallelize_{index}",
                kind="parallelize",
                title=f"Ready-Node Speedup: {len(group)} Independent Tasks Detected",
                rationale=(
                    f"{len(group)} nodes become ready on the same completion event "
                    "and share no data dependency. The Ready-Node queue dispatches "
                    "each the instant its in_degree hits zero, so none waits on a "
                    "slower sibling."
                ),
                node_ids=list(group),
                projected_latency_saved_ms=max(serial - concurrent, 0),
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
    tiers = layout_tiers(workflow, depths)
    pending = in_degrees(graph)
    sequence = baseline_sequence(graph, workflow.declaration_index())

    baseline = build_baseline_schedule(workflow, sequence, graph=graph)
    compiled = build_compiled_schedule(workflow, graph)
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
        node_in_degrees=pending,
        max_concurrency=get_settings().max_concurrent_tasks,
        baseline_sequence=sequence,
        baseline_estimate=baseline_estimate,
        compiled_estimate=compiled_estimate,
        latency_reduction_pct=reduction,
        optimization_candidates=_candidates(workflow, graph, baseline, compiled),
        warnings=warnings,
    )
