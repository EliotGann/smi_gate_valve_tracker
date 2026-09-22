from dataclasses import replace
from math import asin, degrees

import pytest

from smi_window_tracker.intervals import Conditions, Increment, account_interval, beam_present
from smi_window_tracker.physics import bragg_energy_ev, interaction_rate, upper_bound_photon_rate


def energy(angle, **kwargs):
    return bragg_energy_ev(angle, **(dict(minimum_ev=2000, maximum_ev=25000) | kwargs))


def interval(duration, **kwargs):
    conditions = Conditions(
        closed=True,
        ring=True,
        front_end=True,
        photon_shutter=True,
        fast_shutter=True,
        upper_bound_photons_s=upper_bound_photon_rate(1),
    )
    return account_interval(
        duration, replace(conditions, **kwargs), max_gap_s=1, loaded_above_mbar=100
    )


def test_bragg_known_angle_and_offset_sign():
    # At 30 degrees, lambda = d for first-order diffraction.
    assert energy(30) == pytest.approx(3962.042629972837, rel=1e-9)
    assert energy(29, offset_deg=1) == energy(30)
    assert energy(10) > energy(20)


@pytest.mark.parametrize("angle", [0, -1, 91, float("nan"), float("inf"), 1e-323])
def test_invalid_bragg_angles(angle):
    with pytest.raises(ValueError):
        energy(angle)


@pytest.mark.parametrize("offset", [float("nan"), float("inf"), 100, -100])
def test_invalid_offsets(offset):
    with pytest.raises(ValueError):
        energy(30, offset_deg=offset)


@pytest.mark.parametrize("angle", [1, 90])
def test_energy_outside_material_range_not_clamped(angle):
    with pytest.raises(ValueError, match="outside"):
        energy(angle)


@pytest.mark.parametrize("low,high", [(0, 25000), (25000, 2000), (2000, 2000)])
def test_invalid_energy_range(low, high):
    with pytest.raises(ValueError):
        energy(30, minimum_ev=low, maximum_ev=high)


def test_energy_range_endpoints_are_inclusive():
    e = energy(30)
    assert energy(30, minimum_ev=e) == e
    assert energy(30, maximum_ev=e) == e


def test_required_high_energy_coverage():
    # Invert the supplied Si(111) model; include the confirmed upper operating energy.
    for expected in (2100, 16100, 20000, 24000):
        angle = degrees(asin(12398.42 / (2 * 3.1293 * expected)))
        assert energy(angle) == pytest.approx(expected)


@pytest.mark.parametrize("transmission,expected", [(0, 0), (0.01, 1e11), (1, 1e13)])
def test_reference_flux_attenuation(transmission, expected):
    assert upper_bound_photon_rate(transmission) == expected


def test_explicit_reference_change():
    assert upper_bound_photon_rate(0.1, unattenuated_photons_s=2e13) == 2e12


@pytest.mark.parametrize("bad", [-0.1, 1.1, float("nan"), float("inf")])
def test_invalid_transmission(bad):
    with pytest.raises(ValueError):
        upper_bound_photon_rate(bad)


@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf")])
def test_invalid_reference(bad):
    with pytest.raises(ValueError):
        upper_bound_photon_rate(1, unattenuated_photons_s=bad)


@pytest.mark.parametrize(
    "value,expected",
    [
        (0.49, False),
        (0.5, False),
        (0.51, True),
        (-1, False),
        (None, None),
        (float("nan"), None),
        (float("inf"), None),
    ],
)
def test_provisional_beam_presence(value, expected):
    assert beam_present(value) is expected


def test_explicit_beam_threshold_and_invalid_configuration():
    assert beam_present(0.51, threshold=0.6) is False
    with pytest.raises(ValueError):
        beam_present(1, threshold=float("nan"))


@pytest.mark.parametrize("present", [True, False, None])
def test_bpm_only_affects_diagnostic_timer(present):
    result = interval(0.1, bpm_present=present)
    assert result["upper_bound_photons"] == Increment(1e12, 0.1, 0)
    assert result["window_beam_s"] == Increment(0.1, 0.1, 0)
    expected = {
        True: Increment(0.1, 0.1, 0),
        False: Increment(0, 0.1, 0),
        None: Increment(0, 0, 0.1),
    }
    assert result["bpm_qualified_window_s"] == expected[present]


def test_fast_shutter_blocks_even_when_bpm_sees_light():
    result = interval(0.5, bpm_present=True, fast_shutter=False)
    assert result["upper_bound_photons"] == Increment(0, 0.5, 0)
    assert result["bpm_qualified_window_s"] == Increment(0, 0.5, 0)


def test_half_second_attenuated_exposure_and_interaction():
    rate = upper_bound_photon_rate(0.01)
    power = interaction_rate(photon_rate=rate, energy_ev=10000, deposited_fraction=0.1)
    result = interval(0.5, upper_bound_photons_s=rate, upper_bound_power_w=power)
    assert result["upper_bound_photons"] == Increment(5e10, 0.5, 0)
    assert result["upper_bound_interaction_j"].value == pytest.approx(8.01088317e-6)


def test_unknown_transmission_preserves_timer_and_known_blocker_establishes_zero():
    result = interval(0.5, upper_bound_photons_s=None)
    assert result["upper_bound_photons"] == Increment(0, 0, 0.5)
    assert result["window_beam_s"] == Increment(0.5, 0.5, 0)
    blocked = interval(0.5, upper_bound_photons_s=None, photon_shutter=False)
    assert blocked["upper_bound_photons"] == Increment(0, 0.5, 0)


def test_observed_pulse_train_accounting():
    # Exact captured edges, not a claim about the real DAC3 update cadence.
    segments = [(0.2, False), (0.1, True), (0.3, False), (0.5, True)]
    results = [interval(dt, fast_shutter=state) for dt, state in segments]
    assert sum(r["window_beam_s"].value for r in results) == pytest.approx(0.6)
    assert sum(r["upper_bound_photons"].value for r in results) == pytest.approx(6e12)
