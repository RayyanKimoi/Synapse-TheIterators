"""DAG construction and topological depth partitioning (PRD section 6.1).

Pure graph math over NetworkX. No runtime, cost or latency concerns live here.
"""

import networkx as nx

from ..models.ir import WorkflowIR


class CompileError(ValueError):
    """Raised when a workflow cannot be compiled; surfaced as HTTP 400."""

    def __init__(self, message: str, cycle: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.cycle = cycle or []


def build_graph(workflow: WorkflowIR) -> nx.DiGraph:
    """Build G = (V, E) with edges pointing dependency -> dependent."""
    graph = nx.DiGraph()
    for node in workflow.nodes:
        graph.add_node(
            node.id,
            type=node.type.value,
            persona=node.persona,
            model=node.model,
            tool_name=node.tool_name,
        )
    for node in workflow.nodes:
        for dependency in node.dependencies:
            graph.add_edge(dependency, node.id)
    return graph


def assert_acyclic(graph: nx.DiGraph) -> None:
    try:
        cycle = nx.find_cycle(graph)
    except nx.NetworkXNoCycle:
        return
    path = [edge[0] for edge in cycle] + [cycle[0][0]]
    raise CompileError(
        f"workflow graph contains a cycle: {' -> '.join(path)}", cycle=path
    )


def topological_depths(graph: nx.DiGraph) -> dict[str, int]:
    """Depth(v) = 0 when InDegree(v) = 0, else max(Depth(parents)) + 1."""
    depths: dict[str, int] = {}
    for node in nx.topological_sort(graph):
        parents = list(graph.predecessors(node))
        depths[node] = 0 if not parents else max(depths[p] for p in parents) + 1
    return depths


def execution_tiers(workflow: WorkflowIR, depths: dict[str, int]) -> list[list[str]]:
    """Partition into tiers T_k = {v | Depth(v) = k}; every tier runs concurrently."""
    tiers: dict[int, list[str]] = {}
    for node in workflow.nodes:  # declaration order keeps tiers stable for the UI
        tiers.setdefault(depths[node.id], []).append(node.id)
    return [tiers[depth] for depth in sorted(tiers)]


def baseline_sequence(graph: nx.DiGraph, declaration_index: dict[str, int]) -> list[str]:
    """The single-file order an imperative framework would execute."""
    return list(
        nx.lexicographical_topological_sort(graph, key=lambda node: declaration_index[node])
    )
