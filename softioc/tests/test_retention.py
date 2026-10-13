import json
import sqlite3

import pytest

from smi_window_tracker.beamtime import Recorder, Store
from smi_window_tracker.compact import compact, replace_database
from smi_window_tracker.diagnostics import Sample
from smi_window_tracker.retention import EventSelector, SnapshotSelector


def payload(value=1, **kw):
    return {"value": value, "connected": True, "severity": 0, "status": 0, **kw}


def test_discrete_changes_quality_and_gap_preserved_but_timestamp_churn_ignored():
    selector = EventSelector()
    assert selector.select("fast_shutter", 0, payload(7)) == "baseline"
    for t in range(1, 60):
        assert selector.select("fast_shutter", t, payload(7, source_time=t, text="7.0")) is None
    assert selector.select("fast_shutter", 60, payload(7)) == "periodic"
    assert selector.select("fast_shutter", 60.1, payload(0)) == "value"
    assert selector.select("fast_shutter", 60.2, payload(7)) == "value"
    assert selector.select("fast_shutter", 60.3, payload(7, severity=2)) == "quality"
    assert (
        selector.select("fast_shutter", 60.4, payload(7, severity=2, connected=False)) == "quality"
    )
    assert selector.select("fast_shutter", 70, payload(7)) == "receipt_gap"
    assert selector.select("fast_shutter", 69, payload(7)) == "receipt_gap"
    assert selector.select("restart_gap", 0, {}) == "session"


def test_numeric_pressure_changes_not_coalesced_inside_same_state():
    selector = EventSelector()
    assert selector.select("pressure", 0, payload(0.002)) == "baseline"
    assert selector.select("pressure", 1, payload(0.008)) == "value"
    assert selector.select("pressure", 2, payload(0)) == "value"
    assert selector.select("pressure", 3, payload(float("nan"), text="Lo")) == "quality"
    assert selector.select("pressure", 4, payload(float("nan"), text="Lo")) is None


def test_bpm_only_quality_ring_periodic_and_zero_boundaries():
    selector = EventSelector()
    for name in ("bpm3_sum_x", "ring_current"):
        assert selector.select(name, 0, payload(400)) == "baseline"
        for t in range(1, 60):
            assert selector.select(name, t, payload(400 + t)) is None
    assert selector.select("ring_current", 60, payload(500)) == "periodic"
    assert selector.select("bpm3_sum_x", 60, payload(500)) is None
    assert selector.select("bpm3_sum_x", 61, payload(500, severity=3)) == "quality"
    assert selector.select("ring_current", 61, payload(0)) == "ring_zero_transition"
    assert selector.select("ring_current", 62, payload(300)) == "ring_zero_transition"


def test_reducer_sees_repeated_pressure_reads_for_dwell_despite_history_filter():
    recorder = Recorder()
    recorder.event("valve", Sample(0, 0))
    for t in range(1, 7):
        recorder.event("valve", Sample(0, t - 0.1))
        recorder.event("pressure", Sample(0.003, t))
    assert recorder.pump.pumped is True
    assert recorder.received == 13
    assert len([e for e in recorder.events if e[2] != "procedure"]) == 2
    assert recorder.outputs()["HistorySkipped"] == 11


def test_sparse_history_does_not_change_short_shutter_timer():
    rec = Recorder()
    for name in ("valve", "front_end_shutter", "photon_shutter"):
        rec.event(name, Sample(0, 0))
    rec.event("fast_shutter", Sample(7, 0))
    for t in range(1, 4):
        rec.event("fast_shutter", Sample(7, t))
    rec.event("fast_shutter", Sample(0, 4))
    rec.event("fast_shutter", Sample(7, 4.1))
    assert rec.totals["window_beam_s"]["value"] == pytest.approx(0.1)
    assert len([e for e in rec.events if e[2] == "fast_shutter"]) == 3


def test_checkpoint_every_commit_history_only_periodic_and_boundaries(tmp_path, monkeypatch):
    now = [0]
    monkeypatch.setattr("smi_window_tracker.beamtime.time.monotonic", lambda: now[0])
    store = Store(tmp_path / "db", "id", "c", create=True)
    state = Recorder().snapshot()
    for t in range(120):
        now[0] = t
        state["elapsed"] = t
        seq, _ = store.commit([], [], state)
    assert seq == 120
    assert store.db.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 2
    checkpoint = json.loads(store.db.execute("SELECT payload FROM checkpoint").fetchone()[0])
    assert checkpoint["elapsed"] == 119
    assert checkpoint["storage_sequence"] == 120
    state["counts"][0] = 1
    store.commit([], [], state)
    store.commit([], [], state, final=True)
    assert store.snapshot_rows == 4
    assert store.history_outputs()["DatabaseMiB"] > 0
    store.close()
    store = Store(tmp_path / "db", "id", "c")
    assert store.sequence == 122
    assert store.commit([], [], state)[0] == 123
    store.close()


def test_snapshot_slope_chatter_not_a_state_change():
    selector = SnapshotSelector()
    assert selector.select(0, {"watch": {"Status": "Rising; closed observation"}})
    assert not selector.select(1, {"watch": {"Status": "Falling; closed observation"}})
    assert selector.select(2, {"watch": {"Status": "Unknown downstream pressure"}})
    assert selector.select(3, {}, force=True)


def legacy_database(path):
    store = Store(path, "id", "c", create=True)
    state = Recorder().snapshot()
    store.commit([], [{"duration_s": 3}], state)
    session = store.session
    store.close()
    with sqlite3.connect(path) as db:
        for t in range(120):
            for name, value in (
                ("valve", 1 if t < 50 else 0),
                ("bpm3_sum_x", t),
                ("pressure", 0.003 if t < 70 else 0.004),
            ):
                db.execute(
                    "INSERT INTO events(session,receipt_utc,receipt_mono,name,payload) "
                    "VALUES(?,?,?,?,?)",
                    (session, t, t, name, json.dumps(payload(value))),
                )
            db.execute(
                "INSERT INTO snapshots(seq,utc,session,payload) VALUES(?,?,?,?)",
                (t + 2, t, session, json.dumps(state)),
            )


def test_compaction_preserves_totals_sessions_cycles_edges_and_final_samples(tmp_path):
    source, target = tmp_path / "db.sqlite", tmp_path / "small.sqlite"
    legacy_database(source)
    audit = compact(source, target)
    assert audit["events_before"] == 360
    assert audit["events_after"] < 15
    assert audit["snapshots_after"] < 6
    with sqlite3.connect(source) as old, sqlite3.connect(target) as new:
        for table in ("identity", "sessions", "cycles", "checkpoint"):
            assert (
                old.execute(f"SELECT * FROM {table}").fetchall()
                == new.execute(f"SELECT * FROM {table}").fetchall()
            )
        assert new.execute("SELECT receipt_mono FROM events WHERE name='valve'").fetchall() == [
            (0.0,),
            (50.0,),
            (110.0,),
            (119.0,),
        ]
        assert new.execute("SELECT max(seq) FROM snapshots").fetchone()[0] == 121
        assert new.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    with pytest.raises(FileExistsError):
        compact(source, target)
    assert replace_database(source)["events_after"] == audit["events_after"]
    restored = Store(source, "id", "c")
    assert restored.sequence == 121
    restored.close()


def test_compaction_requires_stopped_recorder(tmp_path):
    path = tmp_path / "db.sqlite"
    store = Store(path, "id", "c", create=True)
    with pytest.raises(BlockingIOError):
        replace_database(path)
    store.close()
