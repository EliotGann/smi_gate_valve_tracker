"""Observed valve transitions and first-observed pressure-crossing cycles.

Inputs must already be normalized/debounced. See docs/ASSUMPTIONS.md for the
provisional semantics. This component does not persist history or recover outages.
"""

from collections import deque
from dataclasses import dataclass
from math import isfinite


def valid_pressure(value: float | None) -> bool:
    return value is not None and isfinite(value) and value >= 0


@dataclass(frozen=True)
class Thresholds:
    atmosphere_mbar: float = 700.0
    pumped_mbar: float = 0.01
    start_confirm_mbar: float = 500.0
    start_timeout_s: float = 120.0
    pumped_dwell_s: float = 5.0
    pumped_exit_mbar: float = 0.02

    def __post_init__(self):
        pressures = (
            self.pumped_mbar,
            self.pumped_exit_mbar,
            self.start_confirm_mbar,
            self.atmosphere_mbar,
        )
        if not all(isfinite(p) and p > 0 for p in pressures) or not all(
            low < high for low, high in zip(pressures[:-1], pressures[1:], strict=True)
        ):
            raise ValueError("Require 0 < pumped < pumped exit < start confirm < atmosphere")
        if not all(isfinite(t) and t > 0 for t in (self.start_timeout_s, self.pumped_dwell_s)):
            raise ValueError("Qualification times must be finite and positive")


@dataclass(frozen=True)
class Milestone:
    pressure_mbar: float
    elapsed_s: float


@dataclass(frozen=True)
class PumpCycle:
    start_s: float
    end_s: float
    milestones: tuple[Milestone, ...] = ()
    confirmed_s: float | None = None

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


class PumpTracker:
    """In-memory counters for one uninterrupted observation session.

    ``max_gap_s`` is a required caller-selected sampling continuity bound.
    ``closed`` must be True, False or None (unknown); timestamps strictly increase.
    An unknown pressure invalidates cycle timing but not a known closure episode.
    """

    def __init__(
        self,
        *,
        max_gap_s: float,
        thresholds: Thresholds | None = None,
        milestones_mbar: tuple[float, ...] = (100.0, 10.0, 1.0, 0.1),
        history_limit: int = 200,
    ):
        if not isfinite(max_gap_s) or max_gap_s <= 0:
            raise ValueError("max_gap_s must be positive and finite")
        if type(history_limit) is not int or history_limit <= 0:
            raise ValueError("history_limit must be a positive integer")
        self.max_gap_s = max_gap_s
        self.thresholds = thresholds if thresholds is not None else Thresholds()
        self.milestones_mbar = tuple(milestones_mbar)
        bounds = (
            self.thresholds.atmosphere_mbar,
            *self.milestones_mbar,
            self.thresholds.pumped_mbar,
        )
        if not all(isfinite(p) for p in bounds) or not all(
            high > low for high, low in zip(bounds[:-1], bounds[1:], strict=True)
        ):
            raise ValueError("Milestones must strictly descend between atmosphere and target")
        self.open_count = 0
        self.close_count = 0
        self.closed_pumped_count = 0
        self.cycles: deque[PumpCycle] = deque(maxlen=history_limit)
        self._full_pump_count = 0
        self._time: float | None = None
        self._closed: bool | None = None
        self._closure_pending = False
        self._armed = False
        self._start: float | None = None
        self._start_confirmed = False
        self._milestones: list[Milestone] = []
        self.pumped: bool | None = None
        self._low_start: float | None = None

    @property
    def full_pump_count(self) -> int:
        return self._full_pump_count

    @property
    def current_milestones(self) -> tuple[Milestone, ...]:
        """Immutable first-observed crossing snapshot; empty after completion/reset."""
        return tuple(self._milestones) if self._start_confirmed else ()

    @property
    def pump_state(self) -> str:
        if self._start is not None:
            return "pumping" if self._start_confirmed else "candidate"
        return "armed" if self._armed else "idle"

    @property
    def candidate_start_s(self) -> float | None:
        return self._start if not self._start_confirmed else None

    @property
    def current_elapsed_s(self) -> float | None:
        """Elapsed at the last valid observation, not a wall-clock prediction."""
        return self._time - self._start if self._start_confirmed else None

    def observe(
        self, time_s: float, *, closed: bool | None, pressure_mbar: float | None
    ) -> PumpCycle | None:
        """Return each completed cycle for storage, independently of the bounded cache.

        This object does not persist anything. A production caller must commit
        completions and counters transactionally before publishing durable totals.
        """
        if closed is not None and type(closed) is not bool:
            raise ValueError("closed must be a normalized bool or None")
        if not isfinite(time_s) or (self._time is not None and time_s <= self._time):
            raise ValueError("Observation times must be finite and strictly increasing")

        if self._time is not None and time_s - self._time > self.max_gap_s:
            self._closed = None
            self._closure_pending = False
            self._reset_cycle()
            self.pumped = None
            self._low_start = None
        self._time = time_s
        self._observe_vacuum(time_s, pressure_mbar)

        if self._closed is False and closed is True:
            self.close_count += 1
            self._closure_pending = True
        elif self._closed is True and closed is False:
            self.open_count += 1
        self._closed = closed

        if closed is not True:
            self._closure_pending = False
            self._reset_cycle()
            return
        if not valid_pressure(pressure_mbar):
            self._reset_cycle()
            return

        if self.pumped is True and self._closure_pending:
            self.closed_pumped_count += 1
            self._closure_pending = False

        # Expiry is checked before pressure: a late <500 observation cannot revive
        # the candidate. A fresh atmosphere observation can re-arm at this point.
        if (
            self._start is not None
            and not self._start_confirmed
            and time_s - self._start > self.thresholds.start_timeout_s
        ):
            self._reset_cycle()

        if self._start is not None and not self._start_confirmed:
            pass  # Chatter never changes the original candidate time/deadline.
        elif pressure_mbar > self.thresholds.atmosphere_mbar:
            self._reset_cycle()
            self._armed = True
            return
        elif self._armed and self._start is None:
            self._start = time_s

        if self._start is not None:
            if pressure_mbar < self.thresholds.start_confirm_mbar:
                self._start_confirmed = True
            for milestone in self.milestones_mbar[len(self._milestones) :]:
                if pressure_mbar >= milestone:
                    break
                self._milestones.append(Milestone(milestone, time_s - self._start))
            if self._start_confirmed and self.pumped is True:
                cycle = PumpCycle(self._start, self._low_start, self.current_milestones, time_s)
                self.cycles.append(cycle)
                self._full_pump_count += 1
                self._reset_cycle()
                return cycle

    def _observe_vacuum(self, time_s: float, pressure_mbar: float | None):
        if not valid_pressure(pressure_mbar):
            self.pumped = None
            self._low_start = None
        elif self.pumped is True:
            if pressure_mbar > self.thresholds.pumped_exit_mbar:
                self.pumped = False
                self._low_start = None
        else:
            self.pumped = False
            if pressure_mbar < self.thresholds.pumped_mbar:
                if self._low_start is None:
                    self._low_start = time_s
                if time_s - self._low_start >= self.thresholds.pumped_dwell_s:
                    self.pumped = True
            else:
                self._low_start = None

    def _reset_cycle(self):
        self._armed = False
        self._start = None
        self._start_confirmed = False
        self._milestones.clear()
