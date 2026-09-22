import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from smi_window_tracker.physics import (
    EV_TO_J,
    dose_rate_gy_s,
    illuminated_mass_kg,
    interaction_rate,
    slab_fractions,
)


def fractions(**kwargs):
    # Synthetic coefficients/geometry, deliberately not a Kapton calibration.
    params = dict(thickness_um=100, density_g_cm3=1, mu_mass_cm2_g=100, mu_en_mass_cm2_g=50)
    return slab_fractions(**(params | kwargs))


def test_analytic_slab_and_deposition_distinction():
    f = fractions()
    assert f.transmitted == pytest.approx(math.exp(-1))
    assert f.removed == pytest.approx(1 - math.exp(-1))
    assert f.deposited == pytest.approx(0.5 * (1 - math.exp(-1)))


def test_transparent_limits():
    for f in [fractions(thickness_um=0), fractions(mu_mass_cm2_g=0, mu_en_mass_cm2_g=0)]:
        assert f.transmitted == 1
        assert f.removed == f.deposited == 0


def test_opaque_limit_and_thin_numerical_precision():
    assert fractions(thickness_um=1e8).deposited == 0.5
    assert fractions(thickness_um=1e8).transmitted == 0
    f = fractions(thickness_um=1e-12)
    assert f.removed == pytest.approx(1e-14, rel=1e-12, abs=0)


def test_illuminated_mass_unit_conversion():
    # 1 cm thick, 1 cm² area, 1 g/cm³ = 1 gram.
    assert illuminated_mass_kg(thickness_um=10000, density_g_cm3=1, area_mm2=100) == 0.001


def test_energy_rate_and_dose_units():
    power = interaction_rate(photon_rate=1e12, energy_ev=10000, deposited_fraction=0.1)
    assert power == pytest.approx(1.602176634e-4)
    assert dose_rate_gy_s(deposited_power_w=power, mass_kg=1e-6) == pytest.approx(160.2176634)
    assert interaction_rate(photon_rate=0, energy_ev=10000, deposited_fraction=1) == 0


def test_area_dose_scaling():
    m1 = illuminated_mass_kg(thickness_um=10, density_g_cm3=1, area_mm2=1)
    m2 = illuminated_mass_kg(thickness_um=10, density_g_cm3=1, area_mm2=2)
    assert dose_rate_gy_s(deposited_power_w=1, mass_kg=m2) == pytest.approx(
        dose_rate_gy_s(deposited_power_w=1, mass_kg=m1) / 2
    )


def test_thin_limit_dose_thickness_cancels():
    rates = []
    for thickness in [1e-4, 2e-4]:
        f = fractions(thickness_um=thickness)
        mass = illuminated_mass_kg(thickness_um=thickness, density_g_cm3=1, area_mm2=1)
        power = interaction_rate(photon_rate=1e10, energy_ev=10000, deposited_fraction=f.deposited)
        rates.append(dose_rate_gy_s(deposited_power_w=power, mass_kg=mass))
    assert rates[0] == pytest.approx(rates[1], rel=1e-5)


@pytest.mark.parametrize(
    "name", ["thickness_um", "density_g_cm3", "mu_mass_cm2_g", "mu_en_mass_cm2_g"]
)
@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf")])
def test_invalid_slab_inputs(name, bad):
    with pytest.raises(ValueError):
        fractions(**{name: bad})


def test_inconsistent_coefficients_or_density():
    with pytest.raises(ValueError):
        fractions(mu_en_mass_cm2_g=101)
    with pytest.raises(ValueError):
        fractions(density_g_cm3=0)


def test_optical_depth_overflow():
    with pytest.raises(ValueError, match="overflow"):
        fractions(thickness_um=1e308, density_g_cm3=1e308)


@pytest.mark.parametrize("name", ["thickness_um", "density_g_cm3", "area_mm2"])
@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf")])
def test_invalid_mass_inputs(name, bad):
    params = dict(thickness_um=1, density_g_cm3=1, area_mm2=1)
    params[name] = bad
    with pytest.raises(ValueError):
        illuminated_mass_kg(**params)


@pytest.mark.parametrize("value", [1e308, 1e-308])
def test_mass_overflow_and_underflow(value):
    with pytest.raises(ValueError):
        illuminated_mass_kg(thickness_um=value, density_g_cm3=value, area_mm2=value)


@pytest.mark.parametrize(
    "name,bad",
    [
        ("photon_rate", -1),
        ("photon_rate", float("nan")),
        ("energy_ev", 0),
        ("energy_ev", float("inf")),
        ("deposited_fraction", -1),
        ("deposited_fraction", 1.1),
    ],
)
def test_invalid_interaction_inputs(name, bad):
    params = dict(photon_rate=1, energy_ev=1000, deposited_fraction=0.5)
    params[name] = bad
    with pytest.raises(ValueError):
        interaction_rate(**params)


def test_interaction_overflow():
    with pytest.raises(ValueError):
        interaction_rate(photon_rate=1e308, energy_ev=1e308, deposited_fraction=1)


@pytest.mark.parametrize(
    "power,mass", [(-1, 1), (1, 0), (1, -1), (float("nan"), 1), (1, float("inf")), (1e308, 1e-308)]
)
def test_invalid_dose_inputs(power, mass):
    with pytest.raises(ValueError):
        dose_rate_gy_s(deposited_power_w=power, mass_kg=mass)


@given(st.floats(min_value=0, max_value=1e5), st.floats(min_value=0, max_value=1))
def test_fractions_bounded_and_transmission_monotonic(thickness, ratio):
    a = fractions(thickness_um=thickness, mu_en_mass_cm2_g=100 * ratio)
    b = fractions(thickness_um=thickness * 2, mu_en_mass_cm2_g=100 * ratio)
    assert 0 <= a.deposited <= a.removed <= 1
    assert a.transmitted + a.removed == pytest.approx(1)
    assert b.transmitted <= a.transmitted
    assert b.deposited >= a.deposited


def test_energy_conversion_constant():
    assert EV_TO_J == 1.602176634e-19
