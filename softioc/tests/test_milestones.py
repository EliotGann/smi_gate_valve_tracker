import pytest

from smi_window_tracker.cycles import Milestone, PumpTracker, Thresholds


def observe(tracker, time, pressure, closed=True):
    tracker.observe(time, closed=closed, pressure_mbar=pressure)


def test_milestones_latch_once_with_cumulative_and_stage_durations():
    tracker = PumpTracker(max_gap_s=100)
    for time, pressure in [(0, 900), (5, 700), (10, 100), (15, 99), (20, 110), (25, 9)]:
        observe(tracker, time, pressure)
    snapshot = tracker.current_milestones
    assert snapshot == (Milestone(100, 10), Milestone(10, 20))
    assert tracker.current_elapsed_s == 20
    for time, pressure in [(30, 0.9), (40, 0.09), (50, 0.009), (55, 0.009)]:
        observe(tracker, time, pressure)
    cycle = tracker.cycles[0]
    assert cycle.milestones == (*snapshot, Milestone(1, 25), Milestone(0.1, 35))
    assert cycle.duration_s == 45
    times = [0, *(m.elapsed_s for m in cycle.milestones), cycle.duration_s]
    stages = [end - start for start, end in zip(times[:-1], times[1:], strict=True)]
    assert stages == [10, 10, 5, 10, 10]
    assert tracker.current_milestones == ()
    assert tracker.current_elapsed_s is None
    # Completed and previously returned snapshots survive future attempts.
    observe(tracker, 60, 900)
    observe(tracker, 70, 0.009)
    assert tracker.cycles[0] == cycle
    assert len(snapshot) == 2


def test_skipped_thresholds_share_observation_time_without_interpolation():
    tracker = PumpTracker(max_gap_s=10)
    observe(tracker, 0, 900)
    observe(tracker, 1, 500)
    observe(tracker, 2, 0.005)
    observe(tracker, 7, 0.005)
    assert tracker.cycles[0].milestones == tuple(Milestone(p, 1) for p in (100, 10, 1, 0.1))


@pytest.mark.parametrize(
    "pressure,closed,time",
    [(900, True, 3), (None, True, 3), (20, False, 3), (20, None, 3), (20, True, 30)],
)
def test_partial_milestones_reset_when_attempt_continuity_breaks(pressure, closed, time):
    tracker = PumpTracker(max_gap_s=10)
    for t, p in [(0, 900), (1, 500), (2, 50)]:
        observe(tracker, t, p)
    assert tracker.current_milestones == (Milestone(100, 1),)
    observe(tracker, time, pressure, closed)
    assert tracker.current_milestones == ()
    assert tracker.current_elapsed_s is None
    assert tracker.full_pump_count == 0


@pytest.mark.parametrize(
    "milestones",
    [(10, 100), (10, 10), (700,), (0.01,), (0,), (-1,), (float("nan"),), (float("inf"),)],
)
def test_invalid_milestone_configuration(milestones):
    with pytest.raises(ValueError, match="Milestones"):
        PumpTracker(max_gap_s=10, milestones_mbar=milestones)


@pytest.mark.parametrize("milestones", [(), (200, 2)])
def test_custom_or_disabled_milestones(milestones):
    tracker = PumpTracker(
        max_gap_s=10, thresholds=Thresholds(800, 0.005), milestones_mbar=milestones
    )
    for time, pressure in enumerate([900, 750, 0.004]):
        observe(tracker, time, pressure)
    observe(tracker, 7, 0.004)
    assert tracker.cycles[0].milestones == tuple(Milestone(p, 1) for p in milestones)


def test_atmosphere_dwell_has_no_elapsed_pump_time():
    tracker = PumpTracker(max_gap_s=10)
    assert tracker.current_elapsed_s is None
    observe(tracker, 0, 900)
    observe(tracker, 1, 800)
    assert tracker.current_elapsed_s is None
    assert tracker.current_milestones == ()
