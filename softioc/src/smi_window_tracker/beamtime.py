"""Serialized beamtime reducer and transactional SQLite recorder.

No CA client writes, no inferred downtime, and no implicit exposure calibration.
Session shutter timers intentionally omit unconfigured ring eligibility.
"""

import fcntl
import hashlib
import json
import sqlite3
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from statistics import median

from .contract import METRICS
from .cycles import PumpTracker
from .diagnostics import Diagnostics
from .intervals import Conditions, account_interval

SCHEMA = 1


def encode(value):
    return json.dumps(value, allow_nan=True, separators=(",", ":"))


class Store:
    """One writer; init is explicit, restart requires matching window/config.

    Methods run serially in a worker thread, never concurrently. WAL/FULL commits
    atomically include raw events, cycles, observation snapshots and totals.
    """

    def __init__(self, path: Path, window: str, config: str, *, create: bool = False):
        if not window.strip() or len(window.encode()) > 128:
            raise ValueError("Window ID must be nonempty and <=128 UTF-8 bytes")
        self.lock = path.with_suffix(path.suffix + ".lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if create:
                path.touch(exist_ok=False)
            self.db = sqlite3.connect(
                f"{path.resolve().as_uri()}?mode=rw", uri=True, timeout=2, check_same_thread=False
            )
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=FULL")
            digest = hashlib.sha256(config.encode()).hexdigest()
            if create:
                self.db.executescript("""
                    CREATE TABLE identity (schema INTEGER, window TEXT, config_hash TEXT,
                                           config TEXT);
                    CREATE TABLE sessions (id TEXT PRIMARY KEY, start_utc REAL, end_utc REAL);
                    CREATE TABLE events (id INTEGER PRIMARY KEY, session TEXT, receipt_utc REAL,
                                         receipt_mono REAL, name TEXT, payload TEXT);
                    CREATE TABLE cycles (id INTEGER PRIMARY KEY, session TEXT, payload TEXT);
                    CREATE TABLE snapshots (seq INTEGER PRIMARY KEY, utc REAL, session TEXT,
                                            payload TEXT);
                    CREATE TABLE checkpoint (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT);
                """)
                self.db.execute(
                    "INSERT INTO identity VALUES (?,?,?,?)", (SCHEMA, window, digest, config)
                )
                self.db.commit()
            identity = self.db.execute(
                "SELECT schema, window, config_hash FROM identity"
            ).fetchone()
            if identity != (SCHEMA, window, digest):
                raise ValueError("Database schema/window/config differs; use its original identity")
            row = self.db.execute("SELECT payload FROM checkpoint WHERE id=1").fetchone()
            self.restored = json.loads(row[0]) if row else {}
            self.session = str(uuid.uuid4())
            self.window = window
            self.db.execute("INSERT INTO sessions VALUES (?,?,NULL)", (self.session, time.time()))
            self.db.commit()
        except BaseException:
            if hasattr(self, "db"):
                self.db.close()
            self.lock.close()
            raise

    def commit(self, events, cycles, state):
        now = time.time()
        with self.db:
            self.db.executemany(
                "INSERT INTO events(session, receipt_utc, receipt_mono, name, payload) "
                "VALUES(?,?,?,?,?)",
                [
                    (self.session, utc, mono, name, encode(payload))
                    for utc, mono, name, payload in events
                ],
            )
            self.db.executemany(
                "INSERT INTO cycles(session,payload) VALUES(?,?)",
                [(self.session, encode(cycle)) for cycle in cycles],
            )
            cursor = self.db.execute(
                "INSERT INTO snapshots(utc,session,payload) VALUES(?,?,?)",
                (now, self.session, encode(state)),
            )
            self.db.execute("INSERT OR REPLACE INTO checkpoint VALUES(1,?)", (encode(state),))
        return cursor.lastrowid, now

    def close(self):
        with self.db:
            self.db.execute("UPDATE sessions SET end_utc=? WHERE id=?", (time.time(), self.session))
        self.db.close()
        self.lock.close()


class Recorder:
    """Bounded pending batch; advance at events and 1 Hz commit ticks.

    Positive pressure only: zero under-range cannot qualify vacuum until its bound
    is known. Shutter-only beam times are explicitly labeled rather than silently
    assuming an unverified ring-current/mode policy.
    """

    def __init__(self, restored=None):
        state = restored or {}
        self.inputs = Diagnostics()
        self.pump = PumpTracker(max_gap_s=5)
        self.previous = None
        self.offsets = state.get("counts", [0, 0, 0, 0])
        self.interrupted = state.get("interrupted", 0) + int(state.get("active", False))
        self.totals = state.get(
            "totals", {name: dict(value=0.0, valid_s=0.0, unknown_s=0.0) for name in METRICS}
        )
        self.early = state.get("early", [])
        self.recent = state.get("recent", [])
        self.last = state.get("last")
        self.events = []
        self.cycles = []
        self.watch = {}
        self.pump_time = None
        if state:
            self.events.append((time.time(), time.monotonic(), "restart_gap", {}))

    def pressure(self, name, now):
        value = self.inputs.value(name, now)
        return value if value is not None and value > 0 else None

    def closed(self, now):
        return {0: True, 1: False}.get(self.inputs.value("valve", now))

    def conditions(self, now):
        return Conditions(
            closed=self.closed(now),
            ring=True,
            front_end={0: True, 1: False}.get(self.inputs.value("front_end_shutter", now)),
            photon_shutter={0: True, 1: False}.get(self.inputs.value("photon_shutter", now)),
            fast_shutter={0: True, 7: False}.get(self.inputs.value("fast_shutter", now)),
            pressure_mbar=self.pressure("pressure", now),
            ambient_mbar=self.pressure("chamber_pressure", now),
            pumped=self.pump.pumped if self.pressure("pressure", now) is not None else None,
        )

    def advance(self, now, *, before_event=False):
        if self.previous is None:
            self.previous = now
            return
        if now < self.previous:
            raise ValueError("Reducer timestamps must not go backward")
        # Do not extrapolate a scheduler/acquisition stall, even with cached inputs.
        if now - self.previous > 5:
            for totals in self.totals.values():
                totals["unknown_s"] += now - self.previous
            if before_event:
                # Preserve totals but clear transient qualification before reacquisition.
                from math import nextafter

                self.observe_pump(nextafter(now, float("-inf")), force_unknown=True)
            else:
                self.observe_pump(now, force_unknown=True)
        else:
            boundaries = sorted(
                {self.previous, now}
                | {
                    sample.received_s + 5
                    for sample in self.inputs.samples.values()
                    if self.previous < sample.received_s + 5 < now
                }
            )
            for start, end in zip(boundaries, boundaries[1:], strict=False):
                increments = account_interval(
                    end - start,
                    self.conditions((start + end) / 2),
                    max_gap_s=5,
                    loaded_above_mbar=0,
                )
                for name in METRICS:
                    for field, value in asdict(increments[name]).items():
                        self.totals[name][field] += value
            if not before_event and (
                self.pressure("pressure", now) is None or self.closed(now) is None
            ):
                self.observe_pump(now)
        self.previous = now

    def observe_pump(self, now, *, force_unknown=False):
        if self.pump_time is not None and now <= self.pump_time:
            return
        active = self.pump.pump_state in ("candidate", "pumping")
        was_pumping = self.pump.pump_state == "pumping"
        cycle = self.pump.observe(
            now,
            closed=None if force_unknown else self.closed(now),
            pressure_mbar=None if force_unknown else self.pressure("pressure", now),
        )
        self.pump_time = now
        if cycle:
            payload = asdict(cycle)
            payload["duration_s"] = cycle.duration_s
            payload["completed_utc"] = time.time()
            self.cycles.append(payload)
            self.last = payload
            if len(self.early) < 5:
                self.early.append(cycle.duration_s)
            self.recent = (self.recent + [cycle.duration_s])[-20:]
        elif active and (
            self.pump.pump_state not in ("candidate", "pumping")
            or (was_pumping and self.pump.pump_state == "candidate")
        ):
            self.interrupted += 1
            self.cycles.append(
                {"interrupted": True, "end_s": now, "reason": "input/valve/pressure break"}
            )

    def event(self, name, sample, *, text="", source_time=0.0, status=0):
        if len(self.events) >= 4096:
            raise RuntimeError("Recording backlog exceeded 4096 events; stopping")
        self.advance(sample.received_s, before_event=True)
        self.inputs.update(name, sample)
        if name in ("pressure", "valve"):
            self.observe_pump(sample.received_s)
        self.events.append(
            (
                time.time(),
                sample.received_s,
                name,
                {
                    **asdict(sample),
                    "text": text[:256],
                    "source_time": source_time,
                    "status": status,
                },
            )
        )

    def snapshot(self):
        counts = [
            self.pump.open_count,
            self.pump.close_count,
            self.pump.closed_pumped_count,
            self.pump.full_pump_count,
        ]
        return {
            "counts": [a + b for a, b in zip(self.offsets, counts, strict=True)],
            "totals": self.totals,
            "interrupted": self.interrupted,
            "early": self.early,
            "recent": self.recent,
            "last": self.last,
            "active": self.pump.pump_state in ("candidate", "pumping"),
            "pump_state": self.pump.pump_state,
            "pumped": self.pump.pumped,
            "elapsed": self.pump.current_elapsed_s,
            "watch": self.watch,
        }

    def outputs(self):
        state = self.snapshot()
        result = dict(
            zip(
                ("OpenCount", "CloseCount", "ClosedPumpedCount", "FullPumpCount"),
                state["counts"],
                strict=True,
            )
        )
        result.update(
            {
                "InterruptedCount": self.interrupted,
                "PumpState": "Pumped down (qualified)" if self.pump.pumped else state["pump_state"],
                "PumpElapsed": state["elapsed"] if state["elapsed"] is not None else float("nan"),
                "LastPump": self.last["duration_s"] if self.last else float("nan"),
                "EarlyMedian": median(self.early) if self.early else float("nan"),
                "RecentMedian": median(self.recent) if self.recent else float("nan"),
                "EarlyN": len(self.early),
                "RecentN": len(self.recent),
                "PumpHistory": "Recent durations (s): "
                + ", ".join(f"{v:.2f}" for v in self.recent),
            }
        )
        for name, fields in self.totals.items():
            result.update({f"{name}_{field}": value for field, value in fields.items()})
        milestones = (
            {item["pressure_mbar"]: item["elapsed_s"] for item in self.last["milestones"]}
            if self.last
            else {}
        )
        for label, pressure in (("100", 100), ("10", 10), ("1", 1), ("0p1", 0.1)):
            result[f"Milestone{label}"] = milestones.get(pressure, float("nan"))
        return result
