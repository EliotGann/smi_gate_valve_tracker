import json

import pytest

from smi_window_tracker.beamtime import Recorder, Store
from smi_window_tracker.diagnostics import Diagnostics, Sample
from smi_window_tracker.procedure import Procedure


def step(proc, data, t, *, kapton=0, gv7=0, up=800.0, down=0.003):
    for name, value in (
        ("valve", kapton),
        ("downstream_valve", gv7),
        ("chamber_pressure", up),
        ("pressure", down),
    ):
        data.update(name, Sample(value, t))
    return proc.observe(t, data, utc=1000000 + t)


def test_vacuum_first_vent_hold_and_detector_connection():
    p, d = Procedure(), Diagnostics()
    step(p, d, 0, kapton=1, up=0.003)
    step(p, d, 1, up=0.003)
    assert p.path == "vacuum-first"
    assert p.phase == "Venting WAXS"
    step(p, d, 2, up=700)
    assert p.hold_start is None
    step(p, d, 3, up=700.1)
    for t in range(4, 304):
        step(p, d, t, down=0.003 + (t - 3) * 0.00001)
    assert p.hold_elapsed == 300
    assert p.phase == "Minimum hold met; continue observing"
    assert not p.warnings()
    step(p, d, 304, gv7=1)
    assert not p.warnings()
    assert "Detector connected" in p.phase
    step(p, d, 305, kapton=1, gv7=1)
    assert p.last["path"] == "vacuum-first"
    assert p.episode is None


@pytest.mark.parametrize("gv7,phrase", [(1, "GV7 OPEN"), (None, "UNVERIFIED")])
def test_wrong_closure_order_latches_even_after_corrected(gv7, phrase):
    p, d = Procedure(), Diagnostics()
    step(p, d, 0, kapton=1, up=0.003)
    step(p, d, 1, gv7=float("nan") if gv7 is None else gv7, up=0.003)
    assert any(phrase in message for message in p.warnings())
    step(p, d, 2, gv7=0)
    assert any(phrase in message for message in p.warnings())
    assert p.outputs()["ProcedureSeverity"] == 2


def test_early_open_and_pressure_boundary():
    p, d = Procedure(), Diagnostics()
    step(p, d, 0, kapton=1, up=0.003)
    step(p, d, 1, up=0.003)
    step(p, d, 2)
    step(p, d, 3, down=0.009)
    assert p.hold_elapsed == 0
    assert "Downstream pressure at/above 0.009 mbar" in p.warnings()
    step(p, d, 4, gv7=1, down=0.009)
    assert "GV7 opened before isolated hold completed" in p.warnings()
    assert "GV7 opened at/above 0.009 mbar" in p.warnings()


def test_manual_path_expected_high_pressure_and_separate_completion():
    p, d = Procedure(), Diagnostics()
    step(p, d, 0, kapton=1, down=800)
    step(p, d, 1, down=800)
    assert p.path == "manual-pump"
    assert not p.warnings()
    step(p, d, 2, down=0.008)
    assert "below opening threshold" in p.phase
    step(p, d, 3, gv7=1, down=0.008)
    assert not p.warnings()  # Five-minute rule belongs to vacuum-first path.


def test_unknowns_reset_hold_and_restart_never_restores_credit():
    p, d = Procedure(hold_seconds=2), Diagnostics()
    step(p, d, 0, kapton=1, up=0.003)
    step(p, d, 1, up=0.003)
    step(p, d, 2)
    step(p, d, 3)
    step(p, d, 4, down=0)
    assert p.hold_elapsed == 0
    assert p.outputs()["ProcedureSeverity"] == 3
    step(p, d, 5)
    assert p.hold_elapsed == 0
    recovered = Procedure(json.loads(json.dumps(p.snapshot())))
    assert recovered.last["result"].startswith("Interrupted")
    step(recovered, Diagnostics(), 0)
    assert recovered.path == "unclassified"
    assert recovered.hold_elapsed == 0


def test_gap_revoking_hold_and_upstream_revent_and_reisolate():
    p, d = Procedure(hold_seconds=2), Diagnostics()
    step(p, d, 0, kapton=1, up=0.003)
    step(p, d, 1, up=0.003)
    step(p, d, 2)
    step(p, d, 3)
    step(p, d, 10)
    assert p.hold_elapsed == 0
    assert p.warnings()
    step(p, d, 11, up=599)
    assert p.hold_start is None
    step(p, d, 12)
    step(p, d, 14, gv7=1)
    assert "before isolated hold" not in ";".join(p.warnings())
    step(p, d, 15, gv7=0)
    assert p.hold_elapsed == 0
    assert "GV7 reclosed: new isolated observation required" in p.warnings()


def test_input_loss_on_open_is_not_pass_and_unclassified_never_infers_path():
    p, d = Procedure(), Diagnostics()
    step(p, d, 0)
    assert p.path == "unclassified"
    step(p, d, 1, gv7=1, down=0)
    assert "GV7 opened with required input unavailable" in p.warnings()
    step(p, d, 2, gv7=1, up=100)
    assert "GV7 opened with unclassified preparation" in p.warnings()
    assert "GV7 opened before WAXS >700 mbar" in p.warnings()


def test_config_change_is_explicit_audited_and_preserves_checkpoint(tmp_path):
    path = tmp_path / "db"
    old = Store(path, "window", "original", create=True)
    old.commit([], [], {"counts": [1, 2, 3, 4]})
    old.close()
    with pytest.raises(ValueError, match="config differs"):
        Store(path, "window", "updated")
    new = Store(path, "window", "updated", accept_config_change=True)
    assert new.restored["counts"] == [1, 2, 3, 4]
    configs = {row[0] for row in new.db.execute("SELECT config FROM config_epochs")}
    assert configs == {"original", "updated"}
    new.close()
    with pytest.raises(ValueError):
        Procedure(hold_seconds=0)


def test_recorder_keeps_sparse_procedure_transitions():
    recorder = Recorder()
    for name, value in (
        ("downstream_valve", 0),
        ("chamber_pressure", 0.003),
        ("pressure", 0.003),
        ("valve", 1),
    ):
        recorder.event(name, Sample(value, 0))
    recorder.event("valve", Sample(0, 1))
    recorder.event("chamber_pressure", Sample(800, 2))
    assert recorder.outputs()["ProcedurePath"] == "vacuum-first"
    assert any(event[2] == "procedure" for event in recorder.events)
    assert recorder.snapshot()["procedure"]["episode"]["vent_complete_utc"] is not None
