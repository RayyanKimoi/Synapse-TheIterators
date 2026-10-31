"""Event-driven Ready-Node scheduler (PRD V2 pass).

This replaces fixed topological depth-tier partitioning. Under the legacy
design every node at depth k waited on the *slowest* node at depth k-1, so a
fast node was blocked by an unrelated sibling. Here, each node carries an
`in_degree` countdown of unresolved upstream dependencies. All zero-degree
nodes are pushed onto an `asyncio.Queue`; an `asyncio.TaskGroup` runs a pool of
workers bounded by `max_concurrency`. The instant a node completes, its
children are decremented and any child hitting zero is pushed straight back
onto the queue.

Reported timings come from the deterministic profile rather than measured wall
clock, so the arena race is reproducible in rehearsal and on stage. The
dispatch order, the concurrency bound and the dependency resolution are real:
swapping `work` for live LLM calls in a later phase needs no change here.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import networkx as nx

# Sentinel pushed once per worker to retire the pool once the DAG is drained.
_STOP = object()


@dataclass(frozen=True, slots=True)
class NodeTiming:
    node_id: str
    start_ms: int
    end_ms: int


def in_degrees(graph: nx.DiGraph) -> dict[str, int]:
    """InDegree(v): unresolved upstream dependencies, the scheduler's countdown.

    Distinct from `dag.topological_depths`, which is a static label retained
    only for canvas layout and never consulted for dispatch.
    """
    return {node: int(degree) for node, degree in graph.in_degree()}


def ready_node_timings(
    graph: nx.DiGraph, duration_ms: Callable[[str], int]
) -> dict[str, NodeTiming]:
    """Analytical twin of `run_ready_nodes`, for the synchronous /compile estimate.

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
    duration_ms: Callable[[str], int],
    max_concurrency: int,
    work: Callable[[str, int], Awaitable[None]],
    on_start: Callable[[str, int], None] | None = None,
    on_complete: Callable[[NodeTiming], None] | None = None,
) -> dict[str, NodeTiming]:
    """Execute the DAG under ready-node dispatch; return per-node logical timings.

    `work(node_id, duration_ms)` performs the node's actual work. `on_start` and
    `on_complete` let a caller observe progress live, which is what drives the
    SSE telemetry stream.
    """
    pending = in_degrees(graph)
    timings: dict[str, NodeTiming] = {}
    parent_end: dict[str, int] = {}
    ready: asyncio.Queue = asyncio.Queue()

    for node, degree in pending.items():
        if degree == 0:
            parent_end[node] = 0
            ready.put_nowait(node)

    remaining = len(pending)
    workers = max(1, min(max_concurrency, len(pending) or 1))
    lock = asyncio.Lock()

    async def worker() -> None:
        nonlocal remaining
        while True:
            node = await ready.get()
            if node is _STOP:
                return

            start = parent_end.get(node, 0)
            duration = duration_ms(node)
            if on_start is not None:
                on_start(node, start)

            await work(node, duration)

            timing = NodeTiming(node, start, start + duration)
            async with lock:
                timings[node] = timing
                if on_complete is not None:
                    on_complete(timing)
                # The core of the V2 pass: decrement children, dispatch at zero.
                for child in graph.successors(node):
                    parent_end[child] = max(parent_end.get(child, 0), timing.end_ms)
                    pending[child] -= 1
                    if pending[child] == 0:
                        ready.put_nowait(child)
                remaining -= 1
                if remaining == 0:
                    for _ in range(workers):
                        ready.put_nowait(_STOP)

    async with asyncio.TaskGroup() as group:
        for _ in range(workers):
            group.create_task(worker())

    return timings


def schedule_span_ms(timings: dict[str, NodeTiming]) -> int:
    return max((timing.end_ms for timing in timings.values()), default=0)
