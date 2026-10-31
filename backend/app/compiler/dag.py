"""DAG construction and structural analysis (PRD V1 pass).

Pure graph math over NetworkX. No runtime, cost or latency concerns live here.

Depth is a *layout* label only: it positions nodes left-to-right on the arena
canvas. It does not partition execution. Dispatch is owned by the Ready-Node
scheduler in `scheduler.py`, which the V2 pass mandates in place of depth tiers.
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
    """Longest-path depth, used for canvas column placement only.

    Depth(v) = 0 with no parents, else max(Depth(parents)) + 1. This is a static
    label; the mutable per-node countdown that actually gates dispatch is
    `scheduler.in_degrees`.
    """
    depths: dict[str, int] = {}
    for node in nx.topological_sort(graph):
        parents = list(graph.predecessors(node))
        depths[node] = 0 if not parents else max(depths[p] for p in parents) + 1
    return depths


def layout_tiers(workflow: WorkflowIR, depths: dict[str, int]) -> list[list[str]]:
    """Group nodes by depth into canvas columns. NOT an execution partition.

    The arena draws each group as a column. Nothing waits on a group boundary:
    the Ready-Node scheduler dispatches a node the moment its own parents
    resolve, so a fast node never blocks behind a slow unrelated sibling.
    """
    tiers: dict[int, list[str]] = {}
    for node in workflow.nodes:  # declaration order keeps tiers stable for the UI
        tiers.setdefault(depths[node.id], []).append(node.id)
    return [tiers[depth] for depth in sorted(tiers)]


def baseline_sequence(graph: nx.DiGraph, declaration_index: dict[str, int]) -> list[str]:
    """The single-file order an imperative framework would execute."""
    return list(
        nx.lexicographical_topological_sort(graph, key=lambda node: declaration_index[node])
    )
