from math import isnan
from pathlib import Path
from types import SimpleNamespace

import pytest

from smi_window_tracker.commissioning import InputSpec, _first_value, _numeric, _text, load_inputs
from smi_window_tracker.diagnostics import Diagnostics, Sample


def test_load_inputs_accepts_configured_and_explicitly_unconfigured_inputs(tmp_path: Path):
    path = tmp_path / "commissioning.toml"
    path.write_text(
        "[inputs.pressure]\npv = 'TEST:PRESSURE'\ndescription = 'pressure'\n"
        "[inputs.valve]\ndescription = 'waiting for controls'\n"
    )

    assert load_inputs(path) == (
        InputSpec("pressure", "TEST:PRESSURE", "pressure"),
        InputSpec("valve", None, "waiting for controls"),
    )


def test_load_inputs_rejects_invalid_pv_name(tmp_path: Path):
    path = tmp_path / "commissioning.toml"
    path.write_text("[inputs.pressure]\npv = ''\n")

    with pytest.raises(ValueError, match="invalid PV name"):
        load_inputs(path)


@pytest.mark.parametrize("value", [0.0, 0, 1.5, 1e-5, True])
def test_native_numeric_pressure_preserved_including_under_range_zero(value):
    raw = _first_value(SimpleNamespace(data=[value]))
    assert _numeric(raw) == float(value)
    assert _text(raw) == str(value)


@pytest.mark.parametrize("value", [b"Lo", "Lo", None, float("nan"), float("inf")])
def test_non_numeric_or_nonfinite_values_do_not_become_zero(value):
    raw = _first_value(SimpleNamespace(data=[] if value is None else [value]))
    assert isnan(_numeric(raw))
    if value in (b"Lo", "Lo"):
        assert _text(raw) == "Lo"
    elif value is None:
        assert _text(raw) == ""


def test_numpy_scalar_payloads():
    # Optional CA runtime uses NumPy for some native numeric payloads.
    np = pytest.importorskip("numpy")
    for value in (np.float32(0.0), np.float32(1.25), np.int16(1)):
        assert _numeric(value) == float(value)


@pytest.mark.parametrize(
    "raw,expected",
    [
        (b"8.1E+02", 810.0),
        ("8.1E+02", 810.0),
        ("2.5e-03", 0.0025),
        (" 8.1E+02 \t", 810.0),
        ("0E0", 0.0),
        ("-1.2E+01", -12.0),
    ],
)
def test_numeric_epics_text(raw, expected):
    value = _first_value(SimpleNamespace(data=[raw]))
    assert _numeric(value) == expected
    assert _text(value) == (raw.decode() if isinstance(raw, bytes) else raw)


@pytest.mark.parametrize("raw", ["", "Lo", "810 mbar", "8.1E+", "nan", "inf", "1E999", b"\xff"])
def test_invalid_numeric_text_remains_unknown(raw):
    assert isnan(_numeric(raw))


def test_numeric_text_reaches_pressure_state_and_preserves_alarm_validity():
    diagnostics = Diagnostics()
    value = _numeric("8.1E+02")
    diagnostics.update("chamber_pressure", Sample(value, 0))
    assert diagnostics.state("chamber_pressure", 0) == "Atmosphere (>700 mbar)"
    diagnostics.update("chamber_pressure", Sample(value, 1, severity=3))
    assert diagnostics.state("chamber_pressure", 1) == "Invalid source alarm"
    diagnostics.update("chamber_pressure", Sample(_numeric("0E0"), 2))
    assert diagnostics.state("chamber_pressure", 2) == "Under range (reported zero)"
