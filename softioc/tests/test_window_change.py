import json
import sqlite3

import pytest

from smi_window_tracker.beamtime import Recorder, Store
from smi_window_tracker.diagnostics import Sample
from smi_window_tracker.time_text import date_text, duration_text, pressure_text
from smi_window_tracker.window_change import WindowRequests


def arm(requests, store, **overrides):
    message = dict(
        op="arm",
        request_id="request1",
        session=store.session,
        current_id=store.window,
        new_id="new-window",
        operator="tester",
        reason="preventive",
        installed_utc="2026-01-01T00:00:00Z",
    )
    message.update(overrides)
    return requests.handle(json.dumps(message), store, mono=1, utc=1800000000)[0]


def confirm(requests, store, reply, **overrides):
    message = dict(
        op="confirm",
        request_id=reply["request_id"],
        token=reply["token"],
        session=store.session,
        typed_current_id=store.window,
    )
    message.update(overrides)
    return requests.handle(json.dumps(message), store, mono=2, utc=1800000000)[1]


def test_atomic_retire_replace_and_restart(tmp_path):
    path = tmp_path / "db"
    store = Store(path, "old", "c", create=True)
    rec = Recorder()
    rec.offsets = [5, 6, 7, 8]
    requests = WindowRequests()
    reply = arm(requests, store)
    replacement = confirm(requests, store, reply)
    fresh = Recorder().snapshot()
    store.commit([], [], rec.snapshot(), final=True, replacement=(*replacement, fresh))
    assert store.window == "new-window"
    assert store.installed_utc == 1767225600
    old = json.loads(
        store.db.execute("SELECT final_state FROM installations WHERE id='old'").fetchone()[0]
    )
    assert old["counts"] == [5, 6, 7, 8]
    assert store.db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 2
    assert json.loads(store.receipt)["new_id"] == "new-window"
    with pytest.raises(ValueError):
        confirm(requests, store, reply)
    store.close()
    restored = Store(path, None, "c")
    assert restored.window == "new-window" and restored.restored["counts"] == [0, 0, 0, 0]
    assert restored.window_exists("old")
    with pytest.raises(ValueError):
        arm(WindowRequests(), restored, new_id="old")
    restored.close()


def test_replacement_failure_rolls_back_old_totals_and_identity(tmp_path):
    store = Store(tmp_path / "db", "old", "c", create=True)
    original = Recorder().snapshot()
    store.commit([], [], original)
    requests = WindowRequests()
    replacement = confirm(requests, store, arm(requests, store))
    store.db.execute(
        "CREATE TRIGGER fail BEFORE INSERT ON window_changes BEGIN SELECT RAISE(ABORT,'test'); END"
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.commit([], [], original, replacement=(*replacement, Recorder().snapshot()))
    assert store.window == "old" and not store.window_exists("new-window")
    assert (
        store.db.execute("SELECT retired_utc FROM installations WHERE id='old'").fetchone()[0]
        is None
    )
    store.close()


@pytest.mark.parametrize(
    "bad",
    [
        dict(typed_current_id="wrong"),
        dict(token="wrong"),
        dict(request_id="other"),
        dict(session="other"),
    ],
)
def test_confirmation_identity_and_token_guard(tmp_path, bad):
    store = Store(tmp_path / "db", "old", "c", create=True)
    requests = WindowRequests()
    reply = arm(requests, store)
    with pytest.raises(ValueError):
        confirm(requests, store, reply, **bad)
    assert requests.guard.pending(now_s=2) is None
    store.close()


@pytest.mark.parametrize(
    "bad",
    [
        dict(installed_utc="2026-01-01"),
        dict(installed_utc="2100-01-01T00:00:00Z"),
        dict(session="other"),
        dict(request_id=""),
        dict(current_id="other"),
        dict(reason="invalid"),
    ],
)
def test_invalid_proposal(tmp_path, bad):
    store = Store(tmp_path / "db", "old", "c", create=True)
    with pytest.raises(ValueError):
        arm(WindowRequests(), store, **bad)
    store.close()


def test_cancel_expiry_and_bad_requests(tmp_path):
    store = Store(tmp_path / "db", "old", "c", create=True)
    requests = WindowRequests()
    reply = arm(requests, store)
    result, _ = requests.handle(
        json.dumps(dict(op="cancel", token=reply["token"])), store, mono=2, utc=1800000000
    )
    assert result["status"] == "cancelled"
    for message in ("{}", '{"op":"oops"}', '{"op":"cancel"}', "x" * 5000, "null"):
        with pytest.raises(ValueError):
            requests.handle(message, store, mono=2, utc=1800000000)
    reply = arm(requests, store)
    requests.guard.pending(now_s=62)
    with pytest.raises(ValueError):
        confirm(requests, store, reply)
    store.close()


def test_human_formats_and_pump600():
    assert duration_text(24 * 86400 + 8 * 3600 + 301) == "24 days 8:05:01"
    assert duration_text(59.6) == "0 days 0:01:00"
    assert duration_text(float("nan")) == "N/A"
    assert date_text(None) == "Unknown installation date"
    assert date_text(1767225600) == "2026-01-01 00:00:00 UTC"
    assert [pressure_text(v) for v in (800, 600, 0.003, 0.00003)] == [
        "800",
        "600",
        "0.003",
        "3e-05",
    ]
    assert pressure_text(None) == "N/A"
    r = Recorder()
    r.event("valve", Sample(0, 0))
    for t, value in enumerate((800, 700, 650, 600, 700, 600), 1):
        r.event("valve", Sample(0, t - 0.1))
        r.event("pressure", Sample(value, t))
        assert r.pump.pump_state == "armed"
    r.event("pressure", Sample(599, 7))
    assert r.pump.pump_state == "candidate"


def test_vent_hysteresis_preserves_hold_down_to_600():
    from smi_window_tracker.diagnostics import Diagnostics
    from smi_window_tracker.procedure import Procedure

    d, p = Diagnostics(), Procedure(hold_seconds=3)
    for t, valve, upstream in [
        (0, 1, 0.003),
        (1, 0, 0.003),
        (2, 0, 800),
        (3, 0, 650),
        (4, 0, 600),
        (5, 0, 650),
        (6, 0, 599),
    ]:
        for name, value in (
            ("valve", valve),
            ("chamber_pressure", upstream),
            ("pressure", 0.003),
            ("downstream_valve", 0),
        ):
            d.update(name, Sample(value, t))
        p.observe(t, d, utc=10000 + t)
        if t == 5:
            assert p.hold_elapsed == 3
            assert "Minimum hold met" in p.phase
    assert p.hold_elapsed == 0


def test_timing_definition_upgrade_keeps_totals_not_mixed_references():
    old = Recorder().snapshot()
    old.pop("timing_definition")
    old["counts"] = [1, 2, 3, 4]
    old["early"] = [100]
    old["recent"] = [100]
    old["path_durations"] = {"manual-pump": [100]}
    restored = Recorder(old)
    assert restored.snapshot()["counts"] == [1, 2, 3, 4]
    assert restored.early == restored.recent == []
    assert restored.path_durations == {}
