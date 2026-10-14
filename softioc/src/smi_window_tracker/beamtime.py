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
from copy import copy
from dataclasses import asdict
from pathlib import Path
from statistics import median

from .contract import METRICS
from .cycles import PumpTracker, Thresholds
from .diagnostics import Diagnostics
from .intervals import Conditions, account_interval
from .procedure import Procedure
from .retention import POLICY, EventSelector, SnapshotSelector
from .time_text import duration_text

SCHEMA = 1


def encode(value):
    return json.dumps(value, allow_nan=True, separators=(",", ":"))


class Store:
    """One writer; init is explicit, restart requires matching window/config.

    Methods run serially in a worker thread, never concurrently. DELETE/FULL commits
    atomically include raw events, cycles, observation snapshots and totals.
    """

    def __init__(
        self,
        path: Path,
        window: str | None,
        config: str,
        *,
        create: bool = False,
        accept_config_change: bool = False,
    ):
        if (window is None and create) or (
            window is not None and (not window.strip() or len(window.encode()) > 128)
        ):
            raise ValueError("Window ID must be nonempty and <=128 UTF-8 bytes")
        self.lock = path.with_suffix(path.suffix + ".lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if create:
                path.touch(exist_ok=False)
            self.db = sqlite3.connect(
                f"{path.resolve().as_uri()}?mode=rw", uri=True, timeout=2, check_same_thread=False
            )
            # Rollback journal supports the deployment NFS path; WAL does not.
            # This also checkpoints a stopped legacy WAL database on upgrade.
            mode = self.db.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
            if mode != "delete":
                raise RuntimeError("Could not enable SQLite rollback journal mode")
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
            if identity[0] != SCHEMA or (window is not None and identity[1] != window):
                raise ValueError("Database schema/window/config differs; use its original identity")
            if identity[2] != digest and not accept_config_change:
                raise ValueError(
                    "Database config differs; use --accept-config-change to record an epoch"
                )
            with self.db:
                self.db.execute(
                    "CREATE TABLE IF NOT EXISTS installations "
                    "(id TEXT PRIMARY KEY, installed_utc REAL, retired_utc REAL, "
                    "revision INTEGER, final_state TEXT, metadata TEXT)"
                )
                self.db.execute(
                    "INSERT OR IGNORE INTO installations VALUES(?,NULL,NULL,0,NULL,?)",
                    (identity[1], encode({"date_source": "legacy/initial date unknown"})),
                )
                self.db.execute(
                    "CREATE TABLE IF NOT EXISTS session_windows "
                    "(session TEXT PRIMARY KEY, window_id TEXT)"
                )
                self.db.execute(
                    "INSERT OR IGNORE INTO session_windows SELECT id,? FROM sessions",
                    (identity[1],),
                )
                self.db.execute(
                    "CREATE TABLE IF NOT EXISTS window_changes "
                    "(request_id TEXT PRIMARY KEY, utc REAL, receipt TEXT)"
                )
                self.db.execute(
                    "CREATE TABLE IF NOT EXISTS config_epochs "
                    "(session TEXT, utc REAL, config_hash TEXT, config TEXT)"
                )
                if identity[2] != digest:
                    old_config = self.db.execute("SELECT config FROM identity").fetchone()[0]
                    self.db.execute(
                        "INSERT INTO config_epochs VALUES(?,?,?,?)",
                        ("prior-config", time.time(), identity[2], old_config),
                    )
                    self.db.execute("UPDATE identity SET config_hash=?,config=?", (digest, config))
            row = self.db.execute("SELECT payload FROM checkpoint WHERE id=1").fetchone()
            self.restored = json.loads(row[0]) if row else {}
            legacy_seq = self.db.execute("SELECT coalesce(max(seq),0) FROM snapshots").fetchone()[0]
            self.sequence = max(self.restored.get("storage_sequence", 0), legacy_seq)
            self.snapshot_selector = SnapshotSelector()
            self.event_rows = self.db.execute("SELECT count(*) FROM events").fetchone()[0]
            self.snapshot_rows = self.db.execute("SELECT count(*) FROM snapshots").fetchone()[0]
            self.path = path
            self.session = str(uuid.uuid4())
            self.window = identity[1]
            self.installed_utc, self.revision = self.db.execute(
                "SELECT installed_utc,revision FROM installations WHERE id=?", (self.window,)
            ).fetchone()
            receipt = self.db.execute(
                "SELECT receipt FROM window_changes ORDER BY utc DESC LIMIT 1"
            ).fetchone()
            self.receipt = receipt[0] if receipt else "No window replacement recorded"
            self.config = config
            self.db.execute("INSERT INTO sessions VALUES (?,?,NULL)", (self.session, time.time()))
            self.db.execute("INSERT INTO session_windows VALUES(?,?)", (self.session, self.window))
            self.db.execute(
                "INSERT INTO config_epochs VALUES(?,?,?,?)",
                (self.session, time.time(), digest, config),
            )
            self.db.commit()
        except BaseException:
            if hasattr(self, "db"):
                self.db.close()
            self.lock.close()
            raise

    def commit(self, events, cycles, state, *, final=False, replacement=None):
        now = time.time()
        sequence = self.sequence + 1
        # Work on an independent checkpoint; never mutate the reducer's snapshot.
        checkpoint = {
            **state,
            "storage_sequence": sequence,
            "history_policy": POLICY,
            "window_id": self.window,
            "installed_utc": self.installed_utc,
        }
        important = replacement is not None or any(
            name in ("valve", "downstream_valve", "procedure", "restart_gap")
            or payload.get("history_reason") in ("quality", "receipt_gap")
            for _, _, name, payload in events
        )
        selector = copy(self.snapshot_selector)
        history = selector.select(time.monotonic(), state, force=bool(cycles) or final or important)
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
            if history:
                self.db.execute(
                    "INSERT INTO snapshots(seq,utc,session,payload) VALUES(?,?,?,?)",
                    (sequence, now, self.session, encode(checkpoint)),
                )
            self.db.execute("INSERT OR REPLACE INTO checkpoint VALUES(1,?)", (encode(checkpoint),))
            if replacement is not None:
                proposal, request_id, installed_utc, fresh = replacement
                current = self.db.execute("SELECT window FROM identity").fetchone()[0]
                revision = self.db.execute(
                    "SELECT revision FROM installations WHERE id=?", (current,)
                ).fetchone()[0]
                if current != proposal.current_id or revision != proposal.current_revision:
                    raise ValueError("Current window identity/revision changed")
                new_revision = revision + 1
                receipt = encode(
                    {
                        "request_id": request_id,
                        "old_id": current,
                        "new_id": proposal.new_id,
                        "committed_utc": now,
                    }
                )
                self.db.execute(
                    "UPDATE installations SET retired_utc=?,final_state=?,metadata=? WHERE id=?",
                    (now, encode(state), encode(asdict(proposal)), current),
                )
                self.db.execute(
                    "INSERT INTO installations VALUES(?,?,NULL,?,NULL,?)",
                    (proposal.new_id, installed_utc, new_revision, encode(asdict(proposal))),
                )
                self.db.execute(
                    "INSERT INTO window_changes VALUES(?,?,?)", (request_id, now, receipt)
                )
                self.db.execute("UPDATE identity SET window=?", (proposal.new_id,))
                self.db.execute("UPDATE sessions SET end_utc=? WHERE id=?", (now, self.session))
                new_session = str(uuid.uuid4())
                self.db.execute("INSERT INTO sessions VALUES(?,?,NULL)", (new_session, now))
                self.db.execute(
                    "INSERT INTO session_windows VALUES(?,?)", (new_session, proposal.new_id)
                )
                self.db.execute(
                    "INSERT INTO config_epochs VALUES(?,?,?,?)",
                    (
                        new_session,
                        now,
                        hashlib.sha256(self.config.encode()).hexdigest(),
                        self.config,
                    ),
                )
                checkpoint = {
                    **fresh,
                    "storage_sequence": sequence,
                    "history_policy": POLICY,
                    "window_id": proposal.new_id,
                    "installed_utc": installed_utc,
                }
                self.db.execute(
                    "INSERT OR REPLACE INTO checkpoint VALUES(1,?)", (encode(checkpoint),)
                )
        self.sequence = sequence
        self.snapshot_selector = selector
        self.event_rows += len(events)
        self.snapshot_rows += int(history)
        if replacement is not None:
            self.window, self.session = proposal.new_id, new_session
            self.installed_utc, self.revision, self.receipt = installed_utc, new_revision, receipt
            self.snapshot_selector = SnapshotSelector()
        return sequence, now

    def window_exists(self, name):
        return (
            self.db.execute("SELECT 1 FROM installations WHERE id=?", (name,)).fetchone()
            is not None
        )

    def history_outputs(self):
        """Cheap per-commit counters and file sizes (including SQLite sidecars)."""
        size = sum(
            p.stat().st_size
            for p in (self.path, Path(str(self.path) + "-wal"), Path(str(self.path) + "-journal"))
            if p.exists()
        )
        return {
            "HistoryRows": float(self.event_rows),
            "SnapshotRows": float(self.snapshot_rows),
            "DatabaseMiB": size / 2**20,
            "Retention": POLICY,
        }

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

    def __init__(self, restored=None, *, hold_seconds=300.0):
        state = restored or {}
        self.inputs = Diagnostics()
        self.pump = PumpTracker(max_gap_s=5, thresholds=Thresholds(entry_below_mbar=600))
        self.previous = None
        self.offsets = state.get("counts", [0, 0, 0, 0])
        self.interrupted = state.get("interrupted", 0) + int(state.get("active", False))
        self.totals = state.get(
            "totals", {name: dict(value=0.0, valid_s=0.0, unknown_s=0.0) for name in METRICS}
        )
        self.early = state.get("early", [])
        self.recent = state.get("recent", [])
        self.last = state.get("last")
        self.path_durations = state.get("path_durations", {})
        if state and state.get("timing_definition") != "qualified-pressure-v3-entry600":
            # Old durations remain in cycles/last, but don't mix timing definitions
            # in the new baseline population. Counts and integrated totals persist.
            self.early, self.recent, self.path_durations = [], [], {}
        self.events = []
        self.cycles = []
        self.watch = {}
        self.pump_time = None
        self.procedure = Procedure(state.get("procedure"), hold_seconds=hold_seconds)
        self.selector = EventSelector()
        self.received = 0
        self.retained = 0
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
        if not before_event:
            self.observe_procedure(now)

    def observe_procedure(self, now):
        transition = self.procedure.observe(now, self.inputs, utc=time.time())
        if transition:
            if len(self.events) >= 4096:
                raise RuntimeError("Recording backlog exceeded 4096 events; stopping")
            self.events.append((time.time(), now, "procedure", json.loads(encode(transition))))

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
            payload["timing_definition"] = "qualified-pressure-v3-entry600"
            payload["completed_utc"] = time.time()
            payload["operating_path"] = self.procedure.path
            path = self.procedure.path
            self.path_durations[path] = (self.path_durations.get(path, []) + [cycle.duration_s])[
                -20:
            ]
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
        self.observe_procedure(sample.received_s)
        if name in ("pressure", "valve"):
            self.observe_pump(sample.received_s)
        payload = {
            **asdict(sample),
            "text": text[:256],
            "source_time": source_time,
            "status": status,
        }
        self.received += 1
        previous = self.selector.previous.get(name)
        reason = self.selector.select(name, sample.received_s, payload)
        if reason:
            payload = {**payload, "history_reason": reason}
            if reason == "receipt_gap":
                payload["previous_receipt_mono"] = previous[0]
            self.events.append((time.time(), sample.received_s, name, payload))
            self.retained += 1

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
            "path_durations": self.path_durations,
            "timing_definition": "qualified-pressure-v3-entry600",
            "active": self.pump.pump_state in ("candidate", "pumping"),
            "pump_state": self.pump.pump_state,
            "pumped": self.pump.pumped,
            "elapsed": self.pump.current_elapsed_s,
            "watch": self.watch,
            "procedure": self.procedure.snapshot(),
            "recording_session": {"received": self.received, "retained": self.retained},
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
                "HistoryReceived": float(self.received),
                "HistoryRetained": float(self.retained),
                "HistorySkipped": float(self.received - self.retained),
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
                "PathHistory": "; ".join(
                    f"{name}: n={len(values)}, median={median(values):.2f} s"
                    for name, values in sorted(self.path_durations.items())
                    if values
                )
                or "No classified pump durations yet",
            }
        )
        for name, fields in self.totals.items():
            result.update({f"{name}_{field}": value for field, value in fields.items()})
        result.update(self.procedure.outputs())
        result["PumpedTimeText"] = duration_text(self.totals["closed_pumped_s"]["value"])
        result["BeamTimeText"] = duration_text(self.totals["window_beam_s"]["value"])
        result["HoldRemainingText"] = duration_text(result["HoldRemaining"])
        result["PumpElapsedText"] = duration_text(result["PumpElapsed"])
        milestones = (
            {item["pressure_mbar"]: item["elapsed_s"] for item in self.last["milestones"]}
            if self.last
            else {}
        )
        for label, pressure in (("100", 100), ("10", 10), ("1", 1), ("0p1", 0.1)):
            result[f"Milestone{label}"] = milestones.get(pressure, float("nan"))
        return result
