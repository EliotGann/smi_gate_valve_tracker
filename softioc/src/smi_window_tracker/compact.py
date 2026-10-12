"""Offline streaming history compaction; preserve identity, totals and cycle records.

python -m smi_window_tracker.compact /path/history.sqlite --replace
The recorder must be stopped. A validated temporary database replaces the source
only after integrity and preserved-table checks; redundant raw history is discarded.
"""

import argparse
import fcntl
import json
import os
import sqlite3
import time
from pathlib import Path

from .retention import POLICY, EventSelector, SnapshotSelector


def compact(source: Path, destination: Path):
    """Caller owns the source lock; destination must not exist. Return audit counts."""
    destination.touch(exist_ok=False)
    original = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
    original.execute("PRAGMA query_only=ON")
    target = sqlite3.connect(destination)
    audit = {"policy": POLICY, "utc": time.time(), "original_bytes": source.stat().st_size}
    try:
        if original.execute("SELECT schema FROM identity").fetchone() != (1,):
            raise ValueError("Unsupported database schema")
        target.execute("PRAGMA cache_size=-16384")
        for name, sql in original.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ):
            target.execute(sql)
            if name not in ("events", "snapshots"):
                cursor = original.execute(f'SELECT * FROM "{name}"')
                placeholders = ",".join("?" for _ in cursor.description)
                target.executemany(f'INSERT INTO "{name}" VALUES({placeholders})', cursor)
        selector = EventSelector()
        session = None
        last = {}
        seen = retained = 0
        for row in original.execute("SELECT * FROM events ORDER BY id"):
            seen += 1
            if row[1] != session:
                for final in last.values():
                    target.execute("INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?)", final)
                selector, session, last = EventSelector(), row[1], {}
            payload = json.loads(row[5])
            reason = selector.select(row[4], row[3], payload)
            last[row[4]] = row
            if reason:
                # Preserve original payload and IDs verbatim, including source/receipt times.
                target.execute("INSERT INTO events VALUES(?,?,?,?,?,?)", row)
                retained += 1
            if seen % 1000000 == 0:
                target.commit()
                print(f"events scanned={seen:,} selected={retained:,}", flush=True)
        for final in last.values():
            target.execute("INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?)", final)
        audit["events_before"] = seen
        audit["events_after"] = target.execute("SELECT count(*) FROM events").fetchone()[0]
        selector = SnapshotSelector()
        session = None
        previous = None
        seen = 0
        for row in original.execute("SELECT * FROM snapshots ORDER BY seq"):
            seen += 1
            if row[2] != session:
                if previous:
                    target.execute("INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?)", previous)
                selector, session = SnapshotSelector(), row[2]
            if selector.select(row[1], json.loads(row[3])):
                target.execute("INSERT INTO snapshots VALUES(?,?,?,?)", row)
            previous = row
            if seen % 100000 == 0:
                target.commit()
        if previous:
            target.execute("INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?)", previous)
        audit["snapshots_before"] = seen
        audit["snapshots_after"] = target.execute("SELECT count(*) FROM snapshots").fetchone()[0]
        for name in ("identity", "checkpoint", "sessions", "cycles"):
            # Compare in streams, so validation also stays bounded for future larger histories.
            left = original.execute(f'SELECT * FROM "{name}" ORDER BY rowid')
            right = target.execute(f'SELECT * FROM "{name}" ORDER BY rowid')
            if any(a != b for a, b in zip(left, right, strict=True)):
                raise ValueError(f"Preservation check failed: {name}")
        if target.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Compacted database failed integrity check")
        target.execute("CREATE TABLE IF NOT EXISTS compaction_audit (utc REAL, payload TEXT)")
        target.execute(
            "INSERT INTO compaction_audit VALUES(?,?)", (audit["utc"], json.dumps(audit))
        )
        target.commit()
    finally:
        original.close()
        target.close()
    audit["compacted_bytes"] = destination.stat().st_size
    return audit


def replace_database(source: Path):
    """Hold the same instance lock as Store through validation and atomic replacement."""
    lock_path = source.with_suffix(source.suffix + ".lock")
    temporary = source.with_name(source.name + ".compacting")
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Flush a stopped recorder's residual WAL before replacing the main file.
        with sqlite3.connect(source.resolve().as_uri() + "?mode=rw", uri=True) as db:
            if db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] != 0:
                raise RuntimeError("Database still has active readers/writers; retry when stopped")
        db.close()
        audit = compact(source, temporary)
        os.chmod(temporary, source.stat().st_mode & 0o777)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, source)
        directory = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return audit


def main():  # pragma: no cover - thin command-line entry point
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--replace", action="store_true", required=True)
    args = parser.parse_args()
    print(json.dumps(replace_database(args.database), indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
