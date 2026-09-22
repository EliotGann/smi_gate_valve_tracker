import gc
import tracemalloc

import pytest

from smi_window_tracker.cycles import PumpTracker
from smi_window_tracker.lifecycle import WindowChangeGuard, WindowProposal


def pump_batch(tracker, start, count):
    for cycle in range(start, start + count):
        for dt, pressure in ((0, 900), (1, 500), (2, 50), (3, 0.009), (8, 0.009)):
            tracker.observe(cycle * 10 + dt, closed=True, pressure_mbar=pressure)


def test_bounded_history_returns_every_completion_without_losing_total():
    tracker = PumpTracker(max_gap_s=10, history_limit=2)
    completed = []
    for cycle in range(10):
        tracker.observe(cycle * 10, closed=True, pressure_mbar=900)
        tracker.observe(cycle * 10 + 1, closed=True, pressure_mbar=0.009)
        completed.append(tracker.observe(cycle * 10 + 6, closed=True, pressure_mbar=0.009))
    assert tracker.full_pump_count == 10
    assert len(tracker.cycles) == 2
    assert list(tracker.cycles) == completed[-2:]
    assert all(c is not None for c in completed)


@pytest.mark.parametrize("bad", [0, -1, 1.5, True])
def test_history_limit_validation(bad):
    with pytest.raises(ValueError):
        PumpTracker(max_gap_s=10, history_limit=bad)


def test_retained_python_memory_plateaus_after_warmup():
    # Broad regression tolerance, not a live-IOC RSS/soak acceptance budget.
    tracker = PumpTracker(max_gap_s=10, history_limit=20)
    guard = WindowChangeGuard()
    p = WindowProposal("W1", 1, "W2", "preventive", "test")
    tracemalloc.start()
    try:
        pump_batch(tracker, 0, 1000)
        for i in range(1000):
            guard.arm(p, now_s=i, new_id_exists=False)
        gc.collect()
        before = tracemalloc.get_traced_memory()[0]
        pump_batch(tracker, 1000, 20000)
        for i in range(1000, 21000):
            guard.arm(p, now_s=i, new_id_exists=False)
        gc.collect()
        retained = tracemalloc.get_traced_memory()[0] - before
        assert retained < 256 * 1024
        assert tracker.full_pump_count == 21000
        assert len(tracker.cycles) == 20
        assert guard.pending(now_s=21000).proposal == p
    finally:
        tracemalloc.stop()
