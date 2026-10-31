#!/usr/bin/env python3
"""Reset the PASTE transition matrix to cold.

Run this right before the presentation so the judges watch the compiler learn
from nothing.

    python clean_db.py            # empty the history (safe while the backend runs)
    python clean_db.py --delete    # also remove the file (backend must be stopped)

Emptying the tables is the default because it is what actually works on
Windows: the lingering handle that blocks deleting paste.db belongs to whatever
process opened it, and no other process can force that handle closed. A
DELETE goes through the same SQLite locking the backend already cooperates
with, so the matrix goes cold with the server still up.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / ".synapse" / "paste.db"
# paste.db plus the journal files SQLite may leave beside it.
SIBLINGS = ("", "-wal", "-shm", "-journal")


def counts(connection: sqlite3.Connection) -> tuple[int, int]:
    def total(table: str) -> int:
        try:
            return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.Error:
            return 0

    return total("node_runs"), total("transitions")


def empty(path: Path) -> int:
    connection = sqlite3.connect(path, timeout=5.0)
    try:
        runs, transitions = counts(connection)
        with connection:
            connection.execute("DELETE FROM transitions")
            connection.execute("DELETE FROM node_runs")
        print(f"  cleared {runs} node_runs row(s) and {transitions} transition row(s)")
        print(f"  remaining: {counts(connection)[0]} / {counts(connection)[1]}")
    except sqlite3.OperationalError as exc:
        print(f"FAIL: {exc}")
        print("  Another process is mid-write. Retry, or stop the backend.")
        return 1
    finally:
        connection.close()
    print("PASTE matrix is cold: the next run will speculate nothing.")
    return 0


def remove(path: Path) -> int:
    missing = True
    for suffix in SIBLINGS:
        target = path.with_name(path.name + suffix)
        if not target.exists():
            continue
        missing = False
        try:
            target.unlink()
            print(f"  deleted {target}")
        except PermissionError:
            print(f"FAIL: {target} is held open by a running process.")
            print("  Stop the backend (uvicorn) and run this again, or use the")
            print("  default mode, which empties the tables without deleting.")
            return 1
    if missing:
        print("  nothing to delete")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--delete",
        action="store_true",
        help="remove paste.db instead of emptying it (needs the backend stopped)",
    )
    parser.add_argument("--path", type=Path, default=DB_PATH)
    args = parser.parse_args()

    print(f"PASTE transition matrix: {args.path}")
    if not args.path.exists():
        print("  no matrix on disk -- already cold.")
        return 0

    return remove(args.path) if args.delete else empty(args.path)


if __name__ == "__main__":
    sys.exit(main())
