"""PASTE: speculative pre-fetching driven by a historical transition matrix.

A workflow run is not the first time this graph has executed. SQLite keeps how
often each node ran and how often each downstream tool followed it, so

    P(target | source) = hits(source -> target) / runs(source)

is a frequency measured from real history, not a guess. When that probability
clears `PREFETCH_THRESHOLD` the runtime stops waiting politely: it fires the
tool request the moment its parent *starts* generating, so the network round
trip overlaps the autoregressive decode instead of queueing behind it.

What PASTE can hide is exactly the overlap and no more. A 8.5s tool fired
alongside a 4.5s generation still has 4s left to run when the generation ends.
That is the honest ceiling, and both the live runtime and the planner's
projection compute it the same way.

Two things are never speculated: a node declaring `side_effect`, because firing
it early runs it more often than the workflow asked for, and anything whose
source has fewer than `MIN_OBSERVATIONS` runs behind it, because one
observation makes everything look certain.
"""

import asyncio
import logging
import sqlite3
from collections.abc import Iterable, Mapping
from functools import lru_cache
from pathlib import Path

import networkx as nx

from ..config import get_settings
from ..models.ir import NodeType, WorkflowNode

logger = logging.getLogger(__name__)

# PRD: fire only when the downstream call is more likely than not, by a margin.
PREFETCH_THRESHOLD = 0.75
# One run makes every observed edge look certain; three is the cheapest floor
# that stops a single history from authorising speculation.
MIN_OBSERVATIONS = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS node_runs (
    node TEXT PRIMARY KEY,
    runs INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS transitions (
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    hits INTEGER NOT NULL,
    PRIMARY KEY (source, target)
);
"""

# (source, target) -> probability
Snapshot = Mapping[tuple[str, str], float]


class TransitionMatrix:
    """Observed transition frequencies, persisted in a local SQLite file.

    Every statement runs in a worker thread: sqlite3 is blocking, and the event
    loop here is also serving SSE streams.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        self._connection: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._connection is None:
            if self.path != ":memory:":
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            # check_same_thread=False: every call arrives on a to_thread worker,
            # and the calls are serialised by the single event loop awaiting them.
            self._connection = sqlite3.connect(self.path, check_same_thread=False)
            self._connection.executescript(SCHEMA)
        return self._connection

    def close(self) -> None:
        """Release the SQLite handle. On Windows an open connection is what
        stops the file being deleted, so a reset has to be able to let go."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def reset(self) -> None:
        """Forget all history without touching the file.

        Preferred over deleting it: emptying the tables works while the backend
        is running and holding a connection, so the matrix can be put back to
        cold without stopping the server.
        """
        connection = self._connect()
        with connection:
            connection.execute("DELETE FROM transitions")
            connection.execute("DELETE FROM node_runs")

    async def snapshot(self) -> dict[tuple[str, str], float]:
        """Every transition probability, read once per run.

        Loading the whole matrix up front keeps the dispatch path free of I/O:
        deciding whether to speculate must not cost a database query per node.
        """
        return await asyncio.to_thread(self._snapshot)

    def _snapshot(self) -> dict[tuple[str, str], float]:
        try:
            rows = self._connect().execute(
                "SELECT t.source, t.target, t.hits, r.runs "
                "FROM transitions t JOIN node_runs r ON r.node = t.source "
                "WHERE r.runs >= ?",
                (MIN_OBSERVATIONS,),
            )
            return {(source, target): hits / runs for source, target, hits, runs in rows}
        except sqlite3.Error as exc:
            # No history is a valid state: it means nothing gets speculated.
            logger.warning("transition matrix unreadable (%s); PASTE disabled", exc)
            return {}

    async def record_run(
        self, nodes: Iterable[str], edges: Iterable[tuple[str, str]]
    ) -> None:
        """Fold one completed run into the history, as a single transaction."""
        await asyncio.to_thread(self._record_run, list(nodes), list(edges))

    def _record_run(self, nodes: list[str], edges: list[tuple[str, str]]) -> None:
        try:
            connection = self._connect()
            with connection:
                connection.executemany(
                    "INSERT INTO node_runs (node, runs) VALUES (?, 1) "
                    "ON CONFLICT(node) DO UPDATE SET runs = runs + 1",
                    [(node,) for node in nodes],
                )
                connection.executemany(
                    "INSERT INTO transitions (source, target, hits) VALUES (?, ?, 1) "
                    "ON CONFLICT(source, target) DO UPDATE SET hits = hits + 1",
                    edges,
                )
        except sqlite3.Error as exc:
            # Losing history costs future speculation, never the current run.
            logger.warning("transition matrix not updated (%s)", exc)


def prefetchable(
    graph: nx.DiGraph, nodes: Mapping[str, WorkflowNode], snapshot: Snapshot
) -> frozenset[str]:
    """Tool nodes history says are worth firing before they are asked for."""
    return frozenset(
        node_id
        for node_id, node in nodes.items()
        if node.type is NodeType.TOOL_IO
        and not node.side_effect
        and any(
            snapshot.get((parent, node_id), 0.0) > PREFETCH_THRESHOLD
            for parent in graph.predecessors(node_id)
        )
    )


def observed_edges(
    graph: nx.DiGraph, executed: Iterable[str]
) -> list[tuple[str, str]]:
    """Edges of the real DAG both of whose endpoints ran.

    Always the declared graph, never the chain the baseline executes over: the
    history describes the workflow, not the pipeline that happened to run it.
    """
    ran = set(executed)
    return [
        (parent, node)
        for node in ran
        for parent in graph.predecessors(node)
        if parent in ran
    ]


@lru_cache
def get_matrix() -> TransitionMatrix:
    """Process-wide, like the semantic cache: history is only useful across runs."""
    return TransitionMatrix(get_settings().paste_db_path)
