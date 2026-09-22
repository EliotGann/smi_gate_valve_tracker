import pytest

from smi_window_tracker.cycles import PumpTracker, Thresholds


def trace(rows, *, max_gap=100):
    tracker = PumpTracker(max_gap_s=max_gap)
    for time, closed, pressure in rows:
        tracker.observe(time, closed=closed, pressure_mbar=pressure)
    return tracker


@pytest.mark.parametrize("closed", [True, False, None])
@pytest.mark.parametrize("pressure", [1000, 0.001, None])
def test_startup_does_not_invent_events(closed, pressure):
    t = trace([(0, closed, pressure)])
    assert (t.open_count, t.close_count, t.closed_pumped_count, t.full_pump_count) == (0, 0, 0, 0)


def test_full_cycle_excludes_atmosphere_dwell_and_uses_strict_target():
    t = trace(
        [
            (0, False, 1000),
            (1, True, 1000),
            (10, True, 900),
            (20, True, 700),
            (30, True, 0.01),
            (40, True, 0.009),
            (50, True, 0.001),
            (60, False, 0.001),
        ]
    )
    assert (t.close_count, t.open_count, t.closed_pumped_count, t.full_pump_count) == (1, 1, 1, 1)
    assert t.cycles[0].start_s == 20
    assert t.cycles[0].end_s == 40
    assert t.cycles[0].duration_s == 20


def test_multiple_pumps_within_one_closure_and_pressure_chatter():
    t = trace(
        [
            (0, False, 1000),
            (1, True, 1000),
            (2, True, 500),
            (3, True, 0.001),
            (8, True, 0.001),
            (9, True, 0.02),
            (10, True, 0.001),
            (11, True, 1000),
            (12, True, 600),
            (13, True, 0.001),
            (18, True, 0.001),
        ]
    )
    assert t.full_pump_count == 2
    assert t.closed_pumped_count == 1


def test_closing_into_vacuum_qualifies_closure_without_full_cycle():
    t = trace(
        [
            (0, False, 0.001),
            (5, False, 0.001),
            (6, True, 0.001),
            (7, False, 0.001),
            (8, True, 0.001),
        ]
    )
    assert t.closed_pumped_count == 2
    assert t.full_pump_count == 0


def test_startup_closed_can_observe_full_cycle_without_claiming_closure():
    t = trace([(0, True, 900), (1, True, 600), (2, True, 0.001), (7, True, 0.001)])
    assert t.full_pump_count == 1
    assert t.closed_pumped_count == t.close_count == 0


def test_no_atmosphere_qualification_at_exact_boundary():
    t = trace([(0, True, 700), (1, True, 500), (2, True, 0.001)])
    assert t.full_pump_count == 0


def test_atmosphere_seen_only_while_open_does_not_arm():
    t = trace([(0, False, 1000), (1, True, 500), (2, True, 0.001), (7, True, 0.001)])
    assert t.full_pump_count == 0
    assert t.closed_pumped_count == 1


def test_return_to_atmosphere_restarts_but_small_rebound_does_not():
    t = trace(
        [
            (0, True, 900),
            (1, True, 499),
            (2, True, 800),
            (3, True, 100),
            (4, True, 600),
            (5, True, 0.001),
            (10, True, 0.001),
        ]
    )
    assert t.cycles[0].duration_s == 2


@pytest.mark.parametrize("bad", [None, -1, float("nan"), float("inf")])
def test_bad_pressure_breaks_cycle_but_preserves_observed_closure(bad):
    t = trace(
        [
            (0, False, 1000),
            (1, True, 1000),
            (2, True, 500),
            (3, True, bad),
            (4, True, 0.001),
            (9, True, 0.001),
        ]
    )
    assert t.full_pump_count == 0
    assert t.closed_pumped_count == 1


@pytest.mark.parametrize("state", [False, None])
def test_open_or_unknown_breaks_cycle(state):
    t = trace([(0, True, 900), (1, True, 500), (2, state, 100), (3, True, 0.001), (8, True, 0.001)])
    assert t.full_pump_count == 0
    assert t.closed_pumped_count == (1 if state is False else 0)


def test_unknown_does_not_invent_transition_on_reconnect():
    t = trace([(0, False, 900), (1, None, 900), (2, True, 0.001)])
    assert t.close_count == t.closed_pumped_count == 0


def test_long_gap_breaks_continuity_and_rebaselines():
    t = trace(
        [(0, False, 900), (1, True, 900), (2, True, 500), (20, True, 0.001), (40, False, 0.001)],
        max_gap=5,
    )
    assert t.close_count == 1
    assert t.full_pump_count == t.closed_pumped_count == t.open_count == 0


def test_exact_gap_limit_and_unresolved_fast_crossing():
    t = trace([(0, True, 900), (5, True, 0.001), (10, True, 0.001)], max_gap=5)
    assert t.full_pump_count == 1
    # Both crossings occur in one sampling interval; zero is an observation-based
    # duration, not a physical claim. Production will also retain crossing brackets.
    assert t.cycles[0].duration_s == 0


@pytest.mark.parametrize("time", [1, 0, float("nan"), float("inf")])
def test_invalid_timestamp_rejected_without_changing_counts(time):
    t = trace([(1, False, 900)])
    with pytest.raises(ValueError):
        t.observe(time, closed=True, pressure_mbar=0.001)
    assert t.close_count == 0
    t.observe(2, closed=True, pressure_mbar=0.001)
    assert t.closed_pumped_count == 0
    t.observe(7, closed=True, pressure_mbar=0.001)
    assert t.closed_pumped_count == 1


@pytest.mark.parametrize("closed", [0, 1, "Closed"])
def test_states_must_be_normalized(closed):
    with pytest.raises(ValueError):
        trace([(0, closed, 0.001)])


@pytest.mark.parametrize("gap", [0, -1, float("nan"), float("inf")])
def test_invalid_gap(gap):
    with pytest.raises(ValueError):
        PumpTracker(max_gap_s=gap)


@pytest.mark.parametrize(
    "high,low", [(0, 1), (1, 1), (700, 0), (700, -1), (float("nan"), 0.01), (700, float("inf"))]
)
def test_invalid_thresholds(high, low):
    with pytest.raises(ValueError):
        Thresholds(high, low)


def test_configurable_thresholds():
    t = PumpTracker(max_gap_s=10, thresholds=Thresholds(800, 0.005))
    for time, pressure in enumerate([900, 750, 0.006, 0.004]):
        t.observe(time, closed=True, pressure_mbar=pressure)
    t.observe(8, closed=True, pressure_mbar=0.004)
    assert t.cycles[0].duration_s == 2
