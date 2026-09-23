"""Human-readable source timestamps; independent of receipt-time freshness."""

from datetime import UTC, datetime
from math import isfinite


def age_text(age: float) -> str:
    """Human duration with a five-second 'just now' deadband."""
    if not isfinite(age):
        return "Unknown age"
    if age < 0:
        return "future / clock skew"
    if age < 5:
        return "just now"
    for scale, unit in ((86400, "day"), (3600, "hour"), (60, "minute"), (1, "second")):
        if age >= scale:
            count = int(age // scale)
            return f"{count} {unit}{'s' if count != 1 else ''} ago"
    return "Unknown age"  # Nonfinite/invalid clock supplied by a caller.


def source_time_text(timestamp: float, now: float) -> str:
    """Format a Unix source timestamp and its age, explicitly flagging clock skew."""
    if not isfinite(timestamp) or timestamp <= 0 or not isfinite(now):
        return "No source timestamp"
    try:
        date = datetime.fromtimestamp(timestamp, UTC)
        utc = date.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (OverflowError, OSError, ValueError):
        return "Invalid source timestamp"
    # EPICS epoch dates are common unset timestamps. Preserve the exact source
    # value, but label it suspect instead of presenting decades as useful age.
    relative = "Suspect IOC time" if date.year <= 1990 else age_text(now - timestamp)
    return f"{relative} | {utc}"


class ObservationTimes:
    """Receipt/change times within an uninterrupted observation segment.

    Elapsed ages use monotonic time; numeric outputs record receipt UTC. Neither
    claims a hardware transition timestamp. Startup/reconnect establishes a
    baseline and never invents a change. Alarm/status-only changes are not value
    changes. Numeric text is compared numerically by the adapter's parsed value.
    """

    def __init__(self):
        self.read_utc = 0.0
        self.change_utc = 0.0
        self.read_mono: float | None = None
        self.change_mono: float | None = None
        self.baseline_mono: float | None = None
        self.previous = None

    def interrupt(self):
        self.previous = None
        self.change_utc = 0.0
        self.change_mono = None
        self.baseline_mono = None

    def observe(self, value: float, text: str, *, mono: float, utc: float, valid: bool = True):
        if self.read_mono is not None and not 0 <= mono - self.read_mono <= 5:
            self.interrupt()
        self.read_mono, self.read_utc = mono, utc
        if not valid:
            self.interrupt()
            return
        key = ("number", value) if isfinite(value) else ("text", text)
        if self.previous is None:
            self.baseline_mono = mono
        elif key != self.previous:
            self.change_mono, self.change_utc = mono, utc
        self.previous = key

    def labels(self, now_mono: float) -> tuple[str, str]:
        read = "No read received" if self.read_mono is None else age_text(now_mono - self.read_mono)
        if self.read_mono is not None and now_mono - self.read_mono > 5:
            self.interrupt()
        if self.baseline_mono is None:
            change = "Unknown (waiting / gap)"
        elif self.change_mono is None:
            change = "No change seen; baseline " + age_text(now_mono - self.baseline_mono)
        else:
            change = age_text(now_mono - self.change_mono)
        return read, change
