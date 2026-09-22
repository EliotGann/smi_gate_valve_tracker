"""Metric-specific accounting for a caller-validated, left-held interval."""

from dataclasses import dataclass
from math import isfinite

from .cycles import valid_pressure


def beam_present(sum_x: float | None, *, threshold: float = 0.5) -> bool | None:
    """Provisional native-unit comparator; no gain conversion or hysteresis.

    The adapter supplies None for disconnected/stale/alarmed/out-of-range inputs.
    A finite below-threshold reading is false, including a negative dark reading.
    """
    if not isfinite(threshold):
        raise ValueError("Beam-presence threshold must be finite")
    if sum_x is None or not isfinite(sum_x):
        return None
    return sum_x > threshold


def gate(*states: bool | None) -> bool | None:
    """Three-valued AND: a known blocker is enough to establish zero exposure."""
    if any(state is not None and type(state) is not bool for state in states):
        raise ValueError("Gate states must be normalized bools or None")
    if False in states:
        return False
    if None in states:
        return None
    return True


@dataclass(frozen=True)
class Increment:
    value: float
    valid_s: float
    unknown_s: float


@dataclass(frozen=True)
class Conditions:
    """Values valid over an entire interval; the adapter must split at expiries.

    ``upper_bound_photons_s`` includes attenuator transmission, not sample loss.
    ``upper_bound_power_w`` is the same model weighted by energy and deposition.
    Missing model inputs yield None. ``bpm_present`` affects only its extra timer.
    ``pumped`` is the qualified pressure latch, supplied by the state machine;
    callers integrate preceding state before applying each confirmation/exit event.
    """

    closed: bool | None = None
    ring: bool | None = None
    front_end: bool | None = None
    photon_shutter: bool | None = None
    fast_shutter: bool | None = None
    pressure_mbar: float | None = None
    ambient_mbar: float | None = None
    upper_bound_photons_s: float | None = None
    upper_bound_power_w: float | None = None
    bpm_present: bool | None = None
    pumped: bool | None = None


def _increment(dt: float, enabled: bool | None, rate: float | None = 1.0) -> Increment:
    if enabled is False:
        return Increment(0.0, dt, 0.0)
    if enabled is None or rate is None or not isfinite(rate) or rate < 0:
        return Increment(0.0, 0.0, dt)
    value = dt * rate
    if not isfinite(value):
        raise ValueError("Integrated value overflow")
    return Increment(value, dt, 0.0)


def account_interval(
    duration_s: float,
    conditions: Conditions,
    *,
    max_gap_s: float,
    loaded_above_mbar: float,
) -> dict[str, Increment]:
    """Account a single interval, never extrapolating across a gap above the bound.

    Callers manage asynchronous input timestamps and individual validity windows.
    Zero-length intervals are allowed; negative/nonfinite durations are errors.
    """
    if not isfinite(duration_s) or duration_s < 0:
        raise ValueError("duration_s must be nonnegative and finite")
    if not isfinite(max_gap_s) or max_gap_s <= 0:
        raise ValueError("max_gap_s must be positive and finite")
    if not isfinite(loaded_above_mbar) or loaded_above_mbar < 0:
        raise ValueError("loaded_above_mbar must be nonnegative and finite")

    c = conditions
    beam = gate(c.ring, c.front_end, c.photon_shutter, c.fast_shutter)
    window_beam = gate(c.closed, beam)
    dp = (
        abs(c.ambient_mbar - c.pressure_mbar)
        if valid_pressure(c.ambient_mbar) and valid_pressure(c.pressure_mbar)
        else None
    )
    rates = {
        "beam_path_s": (beam, 1.0),
        "window_beam_s": (window_beam, 1.0),
        "bpm_qualified_window_s": (gate(window_beam, c.bpm_present), 1.0),
        "closed_pumped_s": (gate(c.closed, c.pumped), 1.0),
        "loaded_s": (gate(c.closed, dp > loaded_above_mbar if dp is not None else None), 1.0),
        "dp_mbar_s": (c.closed, dp),
        "upper_bound_photons": (window_beam, c.upper_bound_photons_s),
        "upper_bound_interaction_j": (window_beam, c.upper_bound_power_w),
    }
    if duration_s > max_gap_s:
        return {name: Increment(0.0, 0.0, duration_s) for name in rates}
    return {name: _increment(duration_s, enabled, rate) for name, (enabled, rate) in rates.items()}
