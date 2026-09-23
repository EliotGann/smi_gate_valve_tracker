import pytest

from smi_window_tracker.time_text import ObservationTimes, age_text, source_time_text

STAMP = 1704067200.0  # 2024-01-01 00:00:00 UTC


@pytest.mark.parametrize(
    "age,expected",
    [
        (0, "just now"),
        (0.9, "just now"),
        (1, "just now"),
        (4.999, "just now"),
        (5, "5 seconds ago"),
        (59, "59 seconds ago"),
        (60, "1 minute ago"),
        (56 * 60, "56 minutes ago"),
        (3 * 3600, "3 hours ago"),
        (86400, "1 day ago"),
        (2 * 86400, "2 days ago"),
        (-60, "future / clock skew"),
        (-0.5, "future / clock skew"),
    ],
)
def test_relative_and_exact_utc(age, expected):
    assert source_time_text(STAMP, STAMP + age) == expected + " | 2024-01-01 00:00:00 UTC"


@pytest.mark.parametrize("stamp", [0, -1, float("nan"), float("inf")])
def test_missing_source_time(stamp):
    assert source_time_text(stamp, STAMP) == "No source timestamp"


def test_out_of_range_and_invalid_clock():
    assert source_time_text(1e100, STAMP) == "Invalid source timestamp"
    assert source_time_text(STAMP, float("nan")) == "No source timestamp"


def test_quiet_source_age_updates_without_new_source_event():
    assert source_time_text(STAMP, STAMP + 59).startswith("59 seconds ago")
    assert source_time_text(STAMP, STAMP + 60).startswith("1 minute ago")


def test_epics_epoch_is_suspect_but_original_date_is_retained():
    assert source_time_text(631152000, STAMP) == "Suspect IOC time | 1990-01-01 00:00:00 UTC"
    assert age_text(float("nan")) == "Unknown age"


def test_receipts_refresh_but_repeated_values_and_formatting_do_not_change_time():
    clock = ObservationTimes()
    assert clock.labels(0) == ("No read received", "Unknown (waiting / gap)")
    clock.observe(810, "8.1E+02", mono=0, utc=STAMP)
    for second in range(1, 62):
        clock.observe(810, "810.0", mono=second, utc=STAMP + second)
    assert clock.labels(61) == ("just now", "No change seen; baseline 1 minute ago")
    assert clock.change_utc == 0
    clock.observe(7, "7", mono=62, utc=STAMP + 62)
    clock.observe(7, "7", mono=66, utc=STAMP + 66)
    assert clock.labels(66) == ("just now", "just now")
    assert clock.labels(67) == ("just now", "5 seconds ago")
    assert clock.read_utc == STAMP + 66
    assert clock.change_utc == STAMP + 62


def test_clock_steps_do_not_change_local_elapsed_age():
    clock = ObservationTimes()
    clock.observe(7, "7", mono=0, utc=STAMP)
    clock.observe(0, "0", mono=1, utc=STAMP - 100)
    assert clock.labels(5) == ("just now", "just now")


@pytest.mark.parametrize("break_kind", ["disconnect", "invalid", "stale_tick", "stale_event"])
def test_changes_not_invented_across_observation_breaks(break_kind):
    clock = ObservationTimes()
    clock.observe(7, "7", mono=0, utc=STAMP)
    clock.observe(0, "0", mono=1, utc=STAMP + 1)
    if break_kind == "disconnect":
        clock.interrupt()
    elif break_kind == "invalid":
        clock.observe(7, "7", mono=2, utc=STAMP + 2, valid=False)
    elif break_kind == "stale_tick":
        assert clock.labels(7)[1] == "Unknown (waiting / gap)"
    mono = 8 if break_kind.startswith("stale") else 3
    clock.observe(7, "7", mono=mono, utc=STAMP + mono)
    assert clock.change_utc == 0
    assert clock.labels(mono)[1] == "No change seen; baseline just now"


def test_unknown_text_comparison_is_stable():
    clock = ObservationTimes()
    clock.observe(float("nan"), "Lo", mono=0, utc=STAMP)
    clock.observe(float("nan"), "Lo", mono=1, utc=STAMP + 1)
    assert clock.change_utc == 0
    clock.observe(float("nan"), "Hi", mono=2, utc=STAMP + 2)
    assert clock.change_utc == STAMP + 2
