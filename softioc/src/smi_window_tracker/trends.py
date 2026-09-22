"""Offline per-metric comparison of one pump-down with eligible prior durations.

The caller supplies chronological history for one window/setup/timing definition,
excluding the cycle being compared. Production owns eligibility, frozen baseline
IDs/revisions and persistence. No statistical outlier rejection is performed here.
"""

from dataclasses import dataclass
from math import isfinite
from statistics import fmean, median


@dataclass(frozen=True)
class Baseline:
    count: int
    mean_s: float | None
    median_s: float | None
    ready: bool


@dataclass(frozen=True)
class Comparison:
    baseline: Baseline
    ratio_to_median: float | None
    delta_from_median_s: float | None


@dataclass(frozen=True)
class PumpComparison:
    early: Comparison
    recent: Comparison


def compare_duration(
    duration_s: float | None,
    prior_durations_s: tuple[float, ...],
    *,
    early_size: int = 5,
    recent_size: int = 20,
    minimum_history: int = 5,
) -> PumpComparison:
    """Compare a completed duration or explicitly labeled elapsed-so-far value.

    Early reference requires its full requested size. Recent requires at least
    minimum_history. Zero observed durations are retained in summaries but cannot
    establish a ratio when the current value or baseline median is unresolved zero.
    Missing current value preserves baseline statistics but yields no comparison.
    """
    sizes = (early_size, recent_size, minimum_history)
    if any(type(n) is not int or n <= 0 for n in sizes):
        raise ValueError("Reference sizes must be positive integers")
    if minimum_history > min(early_size, recent_size):
        raise ValueError("Minimum history must fit both reference sizes")
    prior = tuple(prior_durations_s)
    values = prior if duration_s is None else (*prior, duration_s)
    if any(not isfinite(value) or value < 0 for value in values):
        raise ValueError("Durations must be finite and nonnegative")

    def comparison(history: tuple[float, ...], required: int) -> Comparison:
        baseline = Baseline(
            count=len(history),
            mean_s=fmean(history) if history else None,
            median_s=float(median(history)) if history else None,
            ready=len(history) >= required,
        )
        if not (
            baseline.ready and baseline.median_s > 0 and duration_s is not None and duration_s > 0
        ):
            return Comparison(baseline, None, None)
        ratio = duration_s / baseline.median_s
        if not isfinite(ratio):
            raise ValueError("Comparison ratio overflow")
        return Comparison(baseline, ratio, duration_s - baseline.median_s)

    return PumpComparison(
        early=comparison(prior[:early_size], early_size),
        recent=comparison(prior[-recent_size:], minimum_history),
    )
