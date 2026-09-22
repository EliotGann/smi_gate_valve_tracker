"""Normal-incidence slab algebra with explicit, caller-supplied coefficients.

No Kapton table or monitor calibration is implicit. Deposited fraction is a
bulk-coefficient approximation, not a validated thin-film transport calculation.
"""

from dataclasses import dataclass
from math import exp, expm1, isfinite, radians, sin

EV_TO_J = 1.602176634e-19


def bragg_energy_ev(
    angle_deg: float, *, minimum_ev: float, maximum_ev: float, offset_deg: float = 0.0
) -> float:
    """Si(111) first-order energy using the supplied beamline conversion.

    Physical theta = readback + offset. Callers must select the validated energy
    range. Invalid values raise rather than clamping to material-table boundaries.
    """
    _finite_positive(minimum_ev=minimum_ev, maximum_ev=maximum_ev)
    if minimum_ev >= maximum_ev:
        raise ValueError("Energy range must be increasing")
    if not isfinite(angle_deg) or not isfinite(offset_deg):
        raise ValueError("Bragg angle and offset must be finite")
    theta = angle_deg + offset_deg
    if not 0 < theta <= 90:
        raise ValueError("Physical Bragg angle must be in (0, 90] degrees")
    denominator = 2 * 3.1293 * sin(radians(theta))
    if denominator == 0:
        raise ValueError("Bragg angle is too small to resolve")
    energy = 12398.42 / denominator
    if not minimum_ev <= energy <= maximum_ev:
        raise ValueError("Energy outside validated range")
    return energy


def upper_bound_photon_rate(transmission: float, *, unattenuated_photons_s: float = 1e13) -> float:
    """Nominal incident photons/s, ignoring sample absorption; no BPM scaling.

    Transmission must already include valid foil states and energy dependence.
    Gating and unknown-input coverage are handled by the interval accountant.
    """
    _finite_positive(reference=unattenuated_photons_s)
    _finite_nonnegative(transmission=transmission)
    if transmission > 1:
        raise ValueError("Transmission must not exceed one")
    return unattenuated_photons_s * transmission


def _finite_nonnegative(**values: float):
    for name, value in values.items():
        if not isfinite(value) or value < 0:
            raise ValueError(f"{name} must be nonnegative and finite")


def _finite_positive(**values: float):
    _finite_nonnegative(**values)
    if any(value == 0 for value in values.values()):
        raise ValueError("Values must be strictly positive")


@dataclass(frozen=True)
class SlabFractions:
    transmitted: float
    removed: float
    deposited: float


def slab_fractions(
    *,
    thickness_um: float,
    density_g_cm3: float,
    mu_mass_cm2_g: float,
    mu_en_mass_cm2_g: float,
) -> SlabFractions:
    """Return transmission, beam removal, and approximate deposited fraction.

    Coefficients must both apply at the same photon energy and composition.
    ``mu_en <= mu`` is required. Zero thickness and zero attenuation are valid.
    """
    _finite_positive(density=density_g_cm3)
    _finite_nonnegative(thickness=thickness_um, mu=mu_mass_cm2_g, mu_en=mu_en_mass_cm2_g)
    if mu_en_mass_cm2_g > mu_mass_cm2_g:
        raise ValueError("Energy-absorption coefficient must not exceed attenuation coefficient")
    optical_depth = mu_mass_cm2_g * density_g_cm3 * (thickness_um * 1e-4)
    if not isfinite(optical_depth):
        raise ValueError("Optical depth overflow")
    removed = -expm1(-optical_depth)
    deposited = removed * (mu_en_mass_cm2_g / mu_mass_cm2_g) if mu_mass_cm2_g else 0.0
    return SlabFractions(exp(-optical_depth), removed, deposited)


def illuminated_mass_kg(*, thickness_um: float, density_g_cm3: float, area_mm2: float) -> float:
    _finite_positive(thickness=thickness_um, density=density_g_cm3, area=area_mm2)
    mass = density_g_cm3 * (thickness_um * 1e-4) * (area_mm2 * 1e-2) * 1e-3
    _finite_positive(mass=mass)
    return mass


def interaction_rate(*, photon_rate: float, energy_ev: float, deposited_fraction: float) -> float:
    """Deposited W if photon_rate is photons/s; relative rate if it is a proxy.

    A raw electrometer current must first pass through an explicit energy/setup
    response model before it can be used as photon_rate.
    """
    _finite_positive(energy=energy_ev)
    _finite_nonnegative(photon_rate=photon_rate, fraction=deposited_fraction)
    if deposited_fraction > 1:
        raise ValueError("deposited_fraction must not exceed one")
    result = photon_rate * (energy_ev * EV_TO_J) * deposited_fraction
    _finite_nonnegative(result=result)
    return result


def dose_rate_gy_s(*, deposited_power_w: float, mass_kg: float) -> float:
    """Approximate illuminated-mass-average dose; requires calibrated power."""
    _finite_nonnegative(power=deposited_power_w)
    _finite_positive(mass=mass_kg)
    result = deposited_power_w / mass_kg
    _finite_nonnegative(result=result)
    return result
