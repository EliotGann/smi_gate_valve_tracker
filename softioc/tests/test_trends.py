import pytest

from smi_window_tracker.trends import compare_duration


def test_early_and_recent_expose_drift_and_keep_slow_cycles():
    history = (100.0,) * 5 + (200.0,) * 20
    result = compare_duration(300, history)
    assert result.early.baseline.mean_s == result.early.baseline.median_s == 100
    assert result.early.baseline.count == 5
    assert result.early.ratio_to_median == 3
    assert result.early.delta_from_median_s == 200
    assert result.recent.baseline.mean_s == result.recent.baseline.median_s == 200
    assert result.recent.baseline.count == 20
    assert result.recent.ratio_to_median == 1.5
    assert result.recent.delta_from_median_s == 100
    # Current is not appended before comparison. Only subsequent comparisons see it.
    following = compare_duration(300, (*history, 300))
    assert following.early == result.early
    assert following.recent.baseline.mean_s == 205


def test_mean_and_median_are_distinct_and_no_outliers_removed():
    result = compare_duration(20, (10, 10, 10, 10, 1000))
    assert result.early.baseline.mean_s == 208
    assert result.early.baseline.median_s == 10
    assert result.early.ratio_to_median == 2


@pytest.mark.parametrize("count", [0, 1, 4])
def test_insufficient_history_has_counts_but_no_ratio(count):
    result = compare_duration(100, (100,) * count)
    for comparison in (result.early, result.recent):
        assert comparison.baseline.count == count
        assert comparison.baseline.ready is False
        assert comparison.ratio_to_median is None
        assert comparison.delta_from_median_s is None
        assert comparison.baseline.mean_s == (100 if count else None)


def test_full_early_membership_required_even_if_minimum_is_lower():
    result = compare_duration(100, (100,) * 3, early_size=5, minimum_history=3)
    assert result.early.baseline.ready is False
    assert result.recent.baseline.ready is True
    assert result.recent.ratio_to_median == 1


@pytest.mark.parametrize("current", [None, 0])
def test_unknown_or_unresolved_current_preserves_statistics(current):
    result = compare_duration(current, (100,) * 5)
    assert result.early.baseline.ready
    assert result.early.baseline.mean_s == 100
    assert result.early.ratio_to_median is None


def test_zero_baseline_is_not_a_ratio_denominator():
    result = compare_duration(100, (0,) * 5)
    assert result.early.baseline.count == 5
    assert result.early.baseline.median_s == 0
    assert result.early.ratio_to_median is None


def test_even_count_median_and_explicit_elapsed_comparison():
    result = compare_duration(15, (10, 20), early_size=2, recent_size=2, minimum_history=2)
    assert result.early.baseline.median_s == 15
    assert result.early.ratio_to_median == 1


@pytest.mark.parametrize("field", ["early_size", "recent_size", "minimum_history"])
@pytest.mark.parametrize("bad", [0, -1, 2.5, True])
def test_invalid_reference_sizes(field, bad):
    with pytest.raises(ValueError):
        compare_duration(100, (), **{field: bad})


def test_minimum_must_fit_reference_sizes():
    with pytest.raises(ValueError):
        compare_duration(100, (), minimum_history=6)


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf")])
def test_invalid_current_and_history(bad):
    with pytest.raises(ValueError):
        compare_duration(bad, ())
    with pytest.raises(ValueError):
        compare_duration(100, (bad,))


def test_ratio_overflow_is_explicit():
    with pytest.raises(ValueError, match="overflow"):
        compare_duration(1e308, (1e-308,) * 5)
