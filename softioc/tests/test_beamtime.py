import json
import sqlite3
import subprocess
import sys

import pytest

from smi_window_tracker.beamtime import Recorder, Store
from smi_window_tracker.commissioning import local_server_environment
from smi_window_tracker.diagnostics import Sample


def event(recorder, t, name, value):
    recorder.event(name, Sample(value, t))


def test_pressure_cycles_and_restart_restore_without_invented_transition(tmp_path):
    db = tmp_path / "history.sqlite"
    store = Store(db, "window1", "config", create=True)
    recorder = Recorder()
    event(recorder, 0, "valve", 1)
    event(recorder, 1, "valve", 0)
    for t, pressure in [
        (2, 800),
        (3, 699),
        (4, 499),
        (5, 90),
        (6, 9),
        (7, 0.9),
        (8, 0.09),
        (9, 0.009),
        (10, 0.008),
        (11, 0.007),
        (12, 0.006),
        (13, 0.005),
        (14, 0.004),
    ]:
        event(recorder, t - 0.1, "valve", 0)
        event(recorder, t, "pressure", pressure)
    assert recorder.outputs()["FullPumpCount"] == 1
    assert recorder.outputs()["ClosedPumpedCount"] == 1
    assert recorder.outputs()["LastPump"] == 6
    store.commit(recorder.events, recorder.cycles, recorder.snapshot())
    store.close()
    store = Store(db, "window1", "config")
    recovered = Recorder(store.restored)
    event(recovered, 0, "valve", 0)
    event(recovered, 1, "pressure", 0.003)
    assert recovered.outputs()["CloseCount"] == 1
    assert recovered.outputs()["FullPumpCount"] == 1
    assert recovered.outputs()["LastPump"] == 6
    store.close()


def test_shutter_pulse_integrated_at_edges_and_pressure_missing_is_independent():
    recorder = Recorder()
    for name, value in (
        ("valve", 0),
        ("front_end_shutter", 0),
        ("photon_shutter", 0),
        ("fast_shutter", 7),
    ):
        event(recorder, 0, name, value)
    event(recorder, 1, "fast_shutter", 0)
    event(recorder, 1.1, "fast_shutter", 7)
    recorder.advance(2)
    assert recorder.totals["window_beam_s"]["value"] == pytest.approx(0.1)
    assert recorder.totals["dp_mbar_s"]["unknown_s"] == 2
    recorder.advance(10)
    assert recorder.totals["window_beam_s"]["unknown_s"] == 8
    with pytest.raises(ValueError):
        recorder.advance(9)


def test_expiry_splits_intervals_and_zero_pressure_is_unknown():
    recorder = Recorder()
    for name, value in (("valve", 0), ("pressure", 0.003), ("chamber_pressure", 100)):
        event(recorder, 0, name, value)
    recorder.advance(4)
    recorder.advance(7)
    assert recorder.totals["dp_mbar_s"]["valid_s"] == 5
    assert recorder.totals["dp_mbar_s"]["unknown_s"] == 2
    event(recorder, 8, "pressure", 0)
    assert recorder.pressure("pressure", 8) is None


def test_database_identity_lock_and_missing_history(tmp_path):
    path = tmp_path / "db.sqlite"
    with pytest.raises(sqlite3.OperationalError):
        Store(path, "id", "c")
    store = Store(path, "id", "c", create=True)
    with pytest.raises(BlockingIOError):
        Store(path, "id", "c")
    store.close()
    with pytest.raises(FileExistsError):
        Store(path, "id", "c", create=True)
    with pytest.raises(ValueError, match="differs"):
        Store(path, "wrong", "c")
    with pytest.raises(ValueError):
        Store(path, "", "c")


def test_transaction_failure_rolls_back_all_tables(tmp_path):
    store = Store(tmp_path / "db", "id", "c", create=True)
    store.commit([], [], {"marker": 1})
    store.db.execute(
        "CREATE TRIGGER fail BEFORE INSERT ON snapshots BEGIN SELECT RAISE(ABORT,'test'); END"
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.commit([(1, 1, "pressure", {"value": 7})], [{"test": 1}], {"marker": 2})
    assert store.db.execute("SELECT count(*) FROM events").fetchone()[0] == 0
    assert store.db.execute("SELECT count(*) FROM cycles").fetchone()[0] == 0
    assert (
        json.loads(store.db.execute("SELECT payload FROM checkpoint").fetchone()[0])["marker"] == 1
    )
    store.close()


def test_local_server_environment_preserves_real_input_discovery(monkeypatch):
    monkeypatch.setenv("EPICS_CA_ADDR_LIST", "192.0.2.5")
    monkeypatch.setenv("EPICS_CAS_AUTO_BEACON_ADDR_LIST", "YES")
    local_server_environment()
    import os

    assert os.environ["EPICS_CA_ADDR_LIST"] == "192.0.2.5"
    assert os.environ["EPICS_CAS_AUTO_BEACON_ADDR_LIST"] == "NO"
    assert os.environ["EPICS_CAS_BEACON_ADDR_LIST"] == "127.0.0.1"
    assert os.environ["EPICS_CAS_INTF_ADDR_LIST"] == "127.0.0.1"


def test_abrupt_exit_recovers_committed_batch_and_marks_active_attempt(tmp_path):
    path = tmp_path / "crash.sqlite"
    code = """
import os, sys
from pathlib import Path
from smi_window_tracker.beamtime import Store, Recorder
from smi_window_tracker.diagnostics import Sample
store = Store(Path(sys.argv[1]), 'window', 'config', create=True)
rec = Recorder()
rec.event('valve', Sample(0, 0))
rec.event('pressure', Sample(800, 1))
rec.event('pressure', Sample(699, 2))
store.commit(rec.events, rec.cycles, rec.snapshot())
# This later event is deliberately uncommitted.
rec.event('pressure', Sample(400, 3))
os._exit(0)
"""
    subprocess.run([sys.executable, "-c", code, str(path)], check=True, timeout=10)
    store = Store(path, "window", "config")
    restored = Recorder(store.restored)
    assert restored.interrupted == 1
    assert restored.pump.pump_state == "idle"
    assert store.db.execute("SELECT count(*) FROM events").fetchone()[0] == 3
    assert (
        store.db.execute("SELECT end_utc FROM sessions ORDER BY start_utc LIMIT 1").fetchone()[0]
        is None
    )
    store.close()


def test_interrupted_attempt_and_bounded_backlog():
    recorder = Recorder()
    event(recorder, 0, "valve", 0)
    event(recorder, 1, "pressure", 800)
    event(recorder, 2, "pressure", 699)
    event(recorder, 3, "valve", 1)
    assert recorder.interrupted == 1
    assert recorder.cycles[0]["interrupted"]
    recorder.events = [(0, 0, "test", {})] * 4096
    with pytest.raises(RuntimeError, match="backlog"):
        event(recorder, 4, "pressure", 500)
