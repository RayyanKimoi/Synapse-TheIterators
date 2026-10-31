"""Event-driven Ready-Node scheduler (PRD V2 pass).

This replaces fixed topological depth-tier partitioning. Under the legacy
design every node at depth k waited on the *slowest* node at depth k-1, so a
fast node was blocked by an unrelated sibling. Here, each node carries an
`in_degree` countdown of unresolved upstream dependencies. All zero-degree
nodes are pushed onto an `asyncio.Queue`; an `asyncio.TaskGroup` runs a pool of
workers bounded by `max_concurrency`. The instant a node completes, its
children are decremented and any child hitting zero is pushed straight back
onto the queue.

A node fails by raising `HaltBranch` from `work`. Its descendants are never
dispatched — this is how a tripped budget circuit breaker severs a branch —
while independent branches keep running.

`work` returns the node's logical duration in ms, and nodes are placed on that
logical clock (start = latest end among the node's own parents). The same
engine therefore serves deterministic simulated latency and measured live
latency.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import networkx as nx

# Sentinel pushed once per worker to retire the pool once the DAG is drained.
_STOP = object()


class HaltBranch(Exception):
    """Raised by `work` to fail a node and cancel everything downstream of it."""

    def __init__(self, reason: str, duration_ms: int = 0) -> None:
        super().__init__(reason)
        self.reason = reason
        self.duration_ms = duration_ms


@dataclass(frozen=True, slots=True)
class NodeTiming:
    node_id: str
    start_ms: int
    end_ms: int
    failed: bool = False


def in_degrees(graph: nx.DiGraph) -> dict[str, int]:
    """InDegree(v): unresolved upstream dependencies, the scheduler's countdown.

    Distinct from `dag.topological_depths`, which is a static label retained
    only for canvas layout and never consulted for dispatch.
    """
    return {node: int(degree) for node, degree in graph.in_degree()}


def ready_node_timings(
    graph: nx.DiGraph, duration_ms: Callable[[str], int]
) -> dict[str, NodeTiming]:
    """Analytical twin of `run_ready_nodes` for durations known up front.

    A node starts the moment its own parents are done — never when an unrelated
    sibling finishes. Produces the same numbers the live scheduler records.
    """
    timings: dict[str, NodeTiming] = {}
    for node in nx.topological_sort(graph):
        start = max(
            (timings[parent].end_ms for parent in graph.predecessors(node)), default=0
        )
        timings[node] = NodeTiming(node, start, start + duration_ms(node))
    return timings


async def run_ready_nodes(
    graph: nx.DiGraph,
    *,
    work: Callable[[str], Awaitable[int]],
    max_concurrency: int,
    on_start: Callable[[str, int], None] | None = None,
    on_complete: Callable[[NodeTiming], None] | None = None,
    on_skip: Callable[[frozenset[str], str], None] | None = None,
) -> dict[str, NodeTiming]:
    """Execute the DAG under ready-node dispatch; return timings of executed nodes.

    `work(node_id)` performs the node and returns its duration in ms. The
    callbacks let a caller observe progress live, which is what drives the SSE
    stream: `on_skip(nodes, failed_node)` reports descendants cancelled because
    `failed_node` raised `HaltBranch`.
    """
    pending = in_degrees(graph)
    if not pending:
        return {}

    timings: dict[str, NodeTiming] = {}
    parent_end: dict[str, int] = {}
    skipped: set[str] = set()
    ready: asyncio.Queue = asyncio.Queue()

    for node, degree in pending.items():
        if degree == 0:
            ready.put_nowait(node)

    remaining = len(pending)
    workers = max(1, min(max_concurrency, remaining))

    async def worker() -> None:
        nonlocal remaining
        while True:
            node = await ready.get()
            if node is _STOP:
                return

            start = parent_end.get(node, 0)
            if on_start is not None:
                on_start(node, start)

            try:
                duration = await work(node)
                failed = False
            except HaltBranch as halt:
                duration = halt.duration_ms
                failed = True

            # No lock needed: nothing below awaits, so the bookkeeping is atomic
            # on the event loop.
            timing = NodeTiming(node, start, start + duration, failed)
            timings[node] = timing
            if on_complete is not None:
                on_complete(timing)
            remaining -= 1

            if failed:
                doomed = frozenset(nx.descendants(graph, node) - skipped)
                skipped.update(doomed)
                remaining -= len(doomed)
                if doomed and on_skip is not None:
                    on_skip(doomed, node)
            else:
                # The core of the V2 pass: decrement children, dispatch at zero.
                for child in graph.successors(node):
                    if child in skipped:
                        continue
                    parent_end[child] = max(parent_end.get(child, 0), timing.end_ms)
                    pending[child] -= 1
                    if pending[child] == 0:
                        ready.put_nowait(child)

            if remaining == 0:
                for _ in range(workers):
                    ready.put_nowait(_STOP)

    async with asyncio.TaskGroup() as group:
        for _ in range(workers):
            group.create_task(worker())

    return timings


def schedule_span_ms(timings: dict[str, NodeTiming]) -> int:
    return max((timing.end_ms for timing in timings.values()), default=0)
