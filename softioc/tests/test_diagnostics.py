from math import isnan

import pytest

from smi_window_tracker.diagnostics import Diagnostics, Sample, describe


@pytest.mark.parametrize(
    "name,value,expected",
    [
        ("valve", 0, "Closed (assumed)"),
        ("valve", 1, "Open"),
        ("valve", 2, "Unknown code"),
        ("photon_shutter", 0, "Open (assumed)"),
        ("front_end_shutter", 1, "Closed"),
        ("fast_shutter", 7, "Closed"),
        ("fast_shutter", 0, "Open"),
        ("pressure", -1, "Invalid pressure"),
        ("pressure", 0, "Under range (reported zero)"),
        ("pressure", 0.009, "Pumped down (raw <0.01)"),
        ("pressure", 0.01, "Above pump target"),
        ("pressure", 700, "Above pump target"),
        ("chamber_pressure", 701, "Atmosphere (>700 mbar)"),
        ("pressure", float("nan"), "Unknown / nonnumeric"),
        ("bpm3_sum_x", 0.6, "Unused: no beam inference"),
        ("bragg", 0, "Outside energy model"),
        ("ring_current", 400, "Current only; gate not set"),
        ("ring_mode", 1, "Mode mapping not set"),
        ("other", 1, "Diagnostic only"),
    ],
)
def test_operator_state_meaning(name, value, expected):
    assert describe(name, value) == expected


def test_bragg_energy_state():
    assert describe("bragg", 10).startswith("Photon energy 11.408")


def feed(engine, t, downstream=0.003, upstream=0.003, valve=0):
    for name, value in (("valve", valve), ("pressure", downstream), ("chamber_pressure", upstream)):
        engine.update(name, Sample(value, t))
    return engine.snapshot(t)


def test_close_both_pumped_then_vent_upstream_tracks_downstream_without_pump_cycle():
    engine = Diagnostics()
    assert feed(engine, 0, valve=1)["Status"] == "Inactive: valve open"
    start = feed(engine, 1)
    assert start["Baseline"] == 0.003
    assert isnan(start["Rate"])
    result = None
    for t in range(2, 42):
        result = feed(engine, t, 0.003 + (t - 1) * 0.001, 20 * (t - 1))
    assert result["Change"] == pytest.approx(0.04)
    assert result["Rate"] == pytest.approx(0.001)
    assert result["Span"] == 30
    assert result["Elapsed"] == 40
    assert result["UpstreamChange"] == pytest.approx(800 - 0.003)
    assert result["DeltaP"] == pytest.approx(800 - 0.043)
    assert result["Status"].startswith("Rising")
    assert len(engine.trend.points) <= 31
    assert feed(engine, 42, valve=1)["Status"] == "Inactive: valve open"
    assert feed(engine, 43, downstream=0.009)["Baseline"] == 0.009


def test_under_range_unknowns_and_recovery_do_not_create_fictitious_rates():
    engine = Diagnostics()
    feed(engine, 0)
    for t, bad in enumerate([0, -1, float("nan")], 1):
        result = feed(engine, t, downstream=bad)
        assert isnan(result["Rate"])
        assert isnan(result["Baseline"])
    recovery = feed(engine, 4, downstream=0.006)
    assert recovery["Baseline"] == 0.006
    assert isnan(recovery["Rate"])
    assert "Unchanged" in feed(engine, 5, downstream=0.006)["Status"]
    assert "Falling" in feed(engine, 6, downstream=0.002)["Status"]


def test_post_close_read_required_and_startup_closed_is_observation_only():
    engine = Diagnostics()
    engine.update("pressure", Sample(0.003, 0))
    engine.update("valve", Sample(0, 1))
    assert engine.snapshot(1)["Status"] == "Waiting for post-close pressure"
    engine.update("pressure", Sample(0.003, 2))
    result = engine.snapshot(2)
    assert result["Elapsed"] == 0
    assert "upstream unknown" in result["Status"]
    assert isnan(result["DeltaP"])
    assert isnan(result["UpstreamChange"])


def test_upstream_loss_does_not_hide_downstream_rise_but_resets_upstream_baseline():
    engine = Diagnostics()
    feed(engine, 0)
    result = feed(engine, 1, downstream=0.006, upstream=0)
    assert result["Rate"] == pytest.approx(0.003)
    assert isnan(result["UpstreamChange"])
    result = feed(engine, 2, downstream=0.009, upstream=100)
    assert result["UpstreamChange"] == 0


@pytest.mark.parametrize("name", ["pressure", "valve"])
@pytest.mark.parametrize("failure", ["disconnect", "alarm", "gap"])
def test_breaks_reset_baseline_even_without_display_tick_between_events(name, failure):
    engine = Diagnostics()
    feed(engine, 0)
    if failure == "disconnect":
        engine.update(name, Sample(0, 1, connected=False))
    elif failure == "alarm":
        engine.update(name, Sample(0, 1, severity=3))
    t = 10 if failure == "gap" else 2
    result = feed(engine, t, downstream=0.005)
    assert result["Baseline"] == 0.005
    assert isnan(result["Rate"])


def test_stale_tick_clears_rate_and_quality_text_tracks_recovery():
    engine = Diagnostics()
    assert engine.state("pressure", 0) == "Waiting for input"
    assert engine.snapshot(0)["Status"] == "Unknown valve state"
    feed(engine, 0)
    assert engine.state("pressure", 0) == "Pumped down (raw <0.01)"
    assert engine.state("pressure", 6) == "Stale / no fresh read"
    assert isnan(engine.snapshot(6)["Rate"])
    engine.update("pressure", Sample(0.004, 7, severity=3))
    assert engine.state("pressure", 7) == "Invalid source alarm"
    engine.update("pressure", Sample(0.004, 8, connected=False))
    assert engine.state("pressure", 8) == "Disconnected / read failed"
    engine.update("pressure", Sample(0.004, 9, severity=1))
    assert engine.state("pressure", 9).endswith("[alarm 1]")


def test_downstream_stale_or_invalid_with_live_valve_is_explicit():
    engine = Diagnostics()
    feed(engine, 0)
    engine.update("valve", Sample(0, 6))
    assert engine.snapshot(6)["Status"] == "Unknown downstream pressure"


def test_high_rate_input_is_bounded_and_cached_ticks_do_not_advance_time():
    engine = Diagnostics()
    for index in range(1000):
        feed(engine, index / 100, downstream=0.003 + index / 10000)
    assert len(engine.trend.points) <= 10
    before = engine.snapshot(10)
    after = engine.snapshot(11)
    assert after["Elapsed"] == before["Elapsed"]
    assert after["Rate"] == before["Rate"]
