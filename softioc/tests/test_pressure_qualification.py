import gc
import tracemalloc

import pytest

from smi_window_tracker.cycles import PumpTracker, Thresholds
from smi_window_tracker.intervals import Conditions, account_interval


def feed(tracker, time, pressure, closed=True):
    return tracker.observe(time, closed=closed, pressure_mbar=pressure)


def test_start_chatter_keeps_original_time_and_requires_strict_second_threshold():
    t = PumpTracker(max_gap_s=130)
    feed(t, 0, 701)
    feed(t, 1, 700)
    for time, pressure in [(2, 702), (3, 699), (4, 701), (5, 500)]:
        feed(t, time, pressure)
        assert t.pump_state == "candidate"
        assert t.candidate_start_s == 1
        assert t.current_elapsed_s is None
    feed(t, 121, 499)  # inclusive 120-second deadline
    assert t.pump_state == "pumping"
    assert t.current_elapsed_s == 120
    feed(t, 122, 0.009)
    assert t.full_pump_count == 0
    cycle = feed(t, 127, 0.009)
    assert cycle.start_s == 1
    assert cycle.end_s == 122
    assert cycle.confirmed_s == 127


def test_late_confirmation_cannot_revive_candidate_or_restart_below_atmosphere():
    t = PumpTracker(max_gap_s=130)
    for time, pressure in [(0, 900), (1, 700), (120, 701), (122, 499), (123, 400)]:
        feed(t, time, pressure)
    assert t.pump_state == "idle"
    assert t.candidate_start_s is None
    feed(t, 124, 701)
    feed(t, 125, 499)
    assert t.current_elapsed_s == 0


def test_timeout_at_atmosphere_rearms_but_keeps_no_expired_candidate():
    t = PumpTracker(max_gap_s=130)
    for time, pressure in [(0, 701), (1, 700), (122, 701)]:
        feed(t, time, pressure)
    assert t.pump_state == "armed"
    assert t.candidate_start_s is None
    feed(t, 123, 700)
    assert t.candidate_start_s == 123


def test_vacuum_dwell_resets_on_boundary_and_latches_through_exit_boundary():
    t = PumpTracker(max_gap_s=10)
    for time, pressure in [(0, 900), (1, 499), (2, 0.009), (6, 0.01), (7, 0.009), (11, 0.009)]:
        feed(t, time, pressure)
        assert t.pumped is False
    cycle = feed(t, 12, 0.009)
    assert t.pumped is True
    assert cycle.end_s == 7
    assert cycle.confirmed_s == 12
    for time, pressure in [(13, 0.01), (14, 0.02), (15, 0.009)]:
        assert feed(t, time, pressure) is None
        assert t.pumped is True
    feed(t, 16, 0.02001)
    assert t.pumped is False
    feed(t, 17, 0.009)
    feed(t, 22, 0.009)
    assert t.pumped is True
    assert t.full_pump_count == 1  # new vacuum qualification is not a full vent/pump


@pytest.mark.parametrize("bad", [None, -1, float("inf"), float("nan")])
def test_bad_pressure_cancels_vacuum_dwell_and_latch(bad):
    t = PumpTracker(max_gap_s=10)
    feed(t, 0, 0.009)
    feed(t, 4, bad)
    assert t.pumped is None
    feed(t, 5, 0.009)
    feed(t, 9, 0.009)
    assert t.pumped is False
    feed(t, 10, 0.009)
    assert t.pumped is True
    feed(t, 11, bad)
    assert t.pumped is None


def test_long_gap_never_qualifies_vacuum_using_stale_sample():
    t = PumpTracker(max_gap_s=2)
    feed(t, 0, 0.009)
    feed(t, 5, 0.009)
    assert t.pumped is False
    for time in (6, 8, 10):
        feed(t, time, 0.009)
    assert t.pumped is True
    feed(t, 20, 0.009)
    assert t.pumped is False


def test_closed_pumped_count_waits_for_qualification_but_not_full_cycle():
    t = PumpTracker(max_gap_s=10)
    feed(t, 0, 0.009, False)
    feed(t, 1, 0.009, True)
    assert t.closed_pumped_count == 0
    feed(t, 5, 0.009, True)
    assert t.closed_pumped_count == 1
    assert t.full_pump_count == 0


def test_pumped_integral_starts_at_confirmation_and_uses_hysteresis():
    t = PumpTracker(max_gap_s=10)
    feed(t, 0, 0.009)
    total = 0
    previous = 0
    for time, pressure in [(4, 0.009), (5, 0.009), (8, 0.015), (10, 0.021), (11, 0.021)]:
        # Production reducer integrates old state BEFORE applying the event.
        result = account_interval(
            time - previous,
            Conditions(closed=True, pressure_mbar=pressure, pumped=t.pumped),
            max_gap_s=10,
            loaded_above_mbar=100,
        )
        total += result["closed_pumped_s"].value
        feed(t, time, pressure)
        previous = time
    assert total == 5  # [5, 10), not the qualification dwell [0, 5)


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(start_confirm_mbar=700),
        dict(pumped_exit_mbar=0.01),
        dict(start_timeout_s=0),
        dict(start_timeout_s=float("inf")),
        dict(pumped_dwell_s=-1),
        dict(pumped_dwell_s=float("nan")),
    ],
)
def test_invalid_qualification_configuration(kwargs):
    with pytest.raises(ValueError):
        Thresholds(**kwargs)


def test_many_failed_crossings_keep_only_current_candidate_and_bounded_memory():
    t = PumpTracker(max_gap_s=5)

    def chatter(start, stop):
        for time in range(start, stop):
            feed(t, time, 701 if time % 2 == 0 else 699)

    tracemalloc.start()
    try:
        chatter(0, 1000)
        gc.collect()
        before = tracemalloc.get_traced_memory()[0]
        chatter(1000, 51000)
        gc.collect()
        assert tracemalloc.get_traced_memory()[0] - before < 128 * 1024
        assert t.full_pump_count == 0
        assert len(t.cycles) == 0
        assert t.current_milestones == ()
        # Expire old candidate, then retain only the final successful crossing.
        for time in range(51000, 51131):
            feed(t, time, 701)
        feed(t, 51131, 699)
        feed(t, 51132, 499)
        feed(t, 51133, 0.009)
        feed(t, 51138, 0.009)
        assert t.cycles[0].start_s == 51131
    finally:
        tracemalloc.stop()
