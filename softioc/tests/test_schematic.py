from math import isnan

import pytest

from smi_window_tracker.diagnostics import Diagnostics, Sample
from smi_window_tracker.schematic import pressure_code, visual_values


@pytest.mark.parametrize(
    "value,code",
    [(None, -1), (-1, -1), (0, 3), (0.009, 0), (0.01, 2), (599, 2), (600, 1), (700, 1), (701, 1)],
)
def test_chamber_fill_semantics(value, code):
    assert pressure_code(value) == code


def setup(**overrides):
    values = dict(
        front_end_shutter=0,
        photon_shutter=0,
        fast_shutter=0,
        valve=0,
        downstream_valve=0,
        chamber_pressure=800,
        pressure=0.003,
        bragg=10,
        bpm3_sum_x=0.6,
    )
    values.update(overrides)
    d = Diagnostics()
    for name, value in values.items():
        d.update(name, Sample(value, 0))
    return d


def test_beam_uses_all_shutters_not_bpm_and_bows_toward_lower_pressure():
    state = visual_values(setup(), 0)
    assert state["Beam"] == 1
    assert state["Bow"] == 1
    assert state["Sample"] == 1 and state["Intermediate"] == 0
    assert state["BPM"] == 0.6
    assert state["Energy"] == pytest.approx(11.408, abs=0.001)
    assert visual_values(setup(chamber_pressure=0.003, pressure=800), 0)["Bow"] == 2
    assert visual_values(setup(chamber_pressure=0.003), 0)["Bow"] == 0


@pytest.mark.parametrize(
    "name,closed", [("front_end_shutter", 1), ("photon_shutter", 1), ("fast_shutter", 7)]
)
def test_any_closed_shutter_blocks_beam(name, closed):
    assert visual_values(setup(**{name: closed}), 0)["Beam"] == 0


def test_unknown_stale_and_under_range_not_green_or_fabricated_bowing():
    unknown = visual_values(Diagnostics(), 0)
    assert unknown["Beam"] == unknown["Bow"] == -1
    assert isnan(unknown["Energy"]) and isnan(unknown["BPM"])
    assert visual_values(setup(), 6)["Beam"] == -1
    assert visual_values(setup(pressure=0), 0)["Bow"] == -1
    assert visual_values(setup(valve=1), 0)["Bow"] == 0
    assert isnan(visual_values(setup(bragg=0), 0)["Energy"])
    d = setup()
    d.update("fast_shutter", Sample(0, 0, severity=3))
    assert visual_values(d, 0)["Beam"] == -1
