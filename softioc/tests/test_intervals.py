from dataclasses import replace
from itertools import product

import pytest
from hypothesis import given
from hypothesis import strategies as st

from smi_window_tracker.intervals import Conditions, Increment, account_interval, gate

ON = Conditions(True, True, True, True, True, 0.001, 1000, 2, 3, pumped=True)


def account(c=ON, dt=10, **kwargs):
    return account_interval(dt, c, max_gap_s=100, loaded_above_mbar=100, **kwargs)


@pytest.mark.parametrize("states", list(product([True, False, None], repeat=3)))
def test_three_valued_gate(states):
    expected = False if False in states else None if None in states else True
    assert gate(*states) is expected


@pytest.mark.parametrize("bad", [0, 1, "Open"])
def test_gate_rejects_non_normalized_input(bad):
    with pytest.raises(ValueError):
        gate(False, bad)


def test_constant_interval_units():
    result = account()
    assert result["beam_path_s"] == result["window_beam_s"] == Increment(10, 10, 0)
    assert result["closed_pumped_s"] == result["loaded_s"] == Increment(10, 10, 0)
    assert result["dp_mbar_s"].value == pytest.approx(9999.99)
    assert result["upper_bound_photons"] == Increment(20, 10, 0)
    assert result["upper_bound_interaction_j"] == Increment(30, 10, 0)


@pytest.mark.parametrize("blocker", ["ring", "front_end", "photon_shutter", "fast_shutter"])
def test_each_blocker_suppresses_exposure_but_not_loading(blocker):
    result = account(
        replace(ON, **{blocker: False, "upper_bound_photons_s": None, "upper_bound_power_w": None})
    )
    for name in [
        "beam_path_s",
        "window_beam_s",
        "upper_bound_photons",
        "upper_bound_interaction_j",
    ]:
        assert result[name] == Increment(0, 10, 0)
    assert result["closed_pumped_s"].value == 10


def test_window_open_preserves_beam_path_time():
    result = account(replace(ON, closed=False))
    assert result["beam_path_s"].value == 10
    assert all(v == Increment(0, 10, 0) for k, v in result.items() if k != "beam_path_s")


@pytest.mark.parametrize("pressure", [1000, 0.01, None, -1, float("nan"), float("inf")])
def test_beam_exposure_independent_of_pressure(pressure):
    result = account(replace(ON, pressure_mbar=pressure, pumped=None))
    assert result["window_beam_s"].value == 10
    assert result["upper_bound_photons"].value == 20
    assert result["closed_pumped_s"].value == 0


def test_pressure_loss_does_not_suppress_beam_metrics():
    result = account(replace(ON, pressure_mbar=None, pumped=None))
    for name in ["loaded_s", "dp_mbar_s", "closed_pumped_s"]:
        assert result[name] == Increment(0, 0, 10)
    assert result["upper_bound_interaction_j"].value == 30


def test_ambient_loss_only_affects_differential_loading():
    result = account(replace(ON, ambient_mbar=None))
    assert result["dp_mbar_s"].unknown_s == 10
    assert result["closed_pumped_s"].value == 10


def test_absolute_pressure_difference_and_strict_loading_threshold():
    result = account(replace(ON, ambient_mbar=900, pressure_mbar=1000))
    assert result["dp_mbar_s"].value == 1000
    assert result["loaded_s"].value == 0


def test_unknown_window_and_known_blocker():
    result = account(replace(ON, closed=None, fast_shutter=False))
    assert result["window_beam_s"] == Increment(0, 10, 0)
    assert result["closed_pumped_s"] == Increment(0, 0, 10)


def test_unknown_shutter_does_not_mean_zero():
    result = account(replace(ON, fast_shutter=None))
    assert result["beam_path_s"] == Increment(0, 0, 10)
    assert result["upper_bound_photons"] == Increment(0, 0, 10)


@pytest.mark.parametrize("bad", [None, -1, float("inf"), float("nan")])
def test_invalid_weighted_rate_preserves_photon_estimate_and_timers(bad):
    result = account(replace(ON, upper_bound_power_w=bad))
    assert result["upper_bound_interaction_j"] == Increment(0, 0, 10)
    assert result["upper_bound_photons"].value == 20
    assert result["window_beam_s"].value == 10


def test_valid_zero_flux_is_distinct_from_unknown():
    result = account(replace(ON, upper_bound_photons_s=0, upper_bound_power_w=0))
    assert result["upper_bound_photons"] == Increment(0, 10, 0)
    assert result["window_beam_s"].value == 10


def test_long_gap_is_not_extrapolated_even_if_previously_blocked():
    result = account(replace(ON, closed=False), dt=101)
    assert all(v == Increment(0, 0, 101) for v in result.values())


def test_zero_duration_and_exact_gap_bound():
    assert all(v == Increment(0, 0, 0) for v in account(dt=0).values())
    assert account(dt=100)["beam_path_s"].value == 100


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf")])
def test_invalid_duration(bad):
    with pytest.raises(ValueError):
        account(dt=bad)


@pytest.mark.parametrize(
    "name,bad",
    [
        ("max_gap_s", 0),
        ("max_gap_s", float("inf")),
        ("loaded_above_mbar", -1),
        ("loaded_above_mbar", float("nan")),
    ],
)
def test_invalid_configuration(name, bad):
    kwargs = dict(max_gap_s=100, loaded_above_mbar=100)
    kwargs[name] = bad
    with pytest.raises(ValueError):
        account_interval(1, ON, **kwargs)


def test_integration_overflow_is_explicit():
    with pytest.raises(ValueError, match="overflow"):
        account(replace(ON, upper_bound_photons_s=1e308))


@given(st.floats(min_value=0, max_value=40), st.floats(min_value=0, max_value=40))
def test_interval_partition_additivity(a, b):
    whole = account(dt=a + b)
    left, right = account(dt=a), account(dt=b)
    for name in whole:
        assert whole[name].value == pytest.approx(left[name].value + right[name].value)
        assert whole[name].valid_s == pytest.approx(left[name].valid_s + right[name].valid_s)


@given(st.sampled_from([True, False, None]), st.floats(min_value=0, max_value=100))
def test_coverage_partitions_elapsed_time(state, dt):
    for value in account(replace(ON, closed=state), dt=dt).values():
        assert value.valid_s + value.unknown_s == pytest.approx(dt)
