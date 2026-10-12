"""History selection only: every observation still reaches the live reducer.

Selected records are observations, not an exhaustive receipt journal. Source
timestamp churn and numeric text formatting alone do not trigger history writes.
"""

from math import isfinite

POLICY = "changes-v1"
PERIOD_S = 60.0
GAP_S = 5.0


def value_key(payload):
    value = payload.get("value")
    if isinstance(value, (float, int)) and isfinite(value):
        return ("number", value)
    return ("unknown", str(payload.get("text", "")))


def quality_key(payload):
    return (
        payload.get("connected", True),
        payload.get("severity", -1),
        payload.get("status", -1),
        value_key(payload)[0],
    )


class EventSelector:
    """One previous observation and last retained time per input; session-local.

    All value changes except unused BPM and periodic ring current; all quality
    changes and receipt gaps. Ring zero/nonzero transitions bypass the period.
    A one-minute unchanged observation anchors quiet-input history. BPM keeps
    only baseline/quality/gap records, not routine values.
    """

    def __init__(self):
        self.previous = {}
        self.retained_at = {}

    def select(self, name, mono, payload):
        if name == "restart_gap":
            return "session"
        previous = self.previous.get(name)
        self.previous[name] = (mono, payload)
        if previous is None:
            reason = "baseline"
        elif not 0 <= mono - previous[0] <= GAP_S:
            reason = "receipt_gap"
        elif quality_key(payload) != quality_key(previous[1]):
            reason = "quality"
        elif name == "ring_current" and (value_key(payload) == ("number", 0)) != (
            value_key(previous[1]) == ("number", 0)
        ):
            reason = "ring_zero_transition"
        elif name not in ("bpm3_sum_x", "ring_current") and (
            value_key(payload) != value_key(previous[1])
        ):
            reason = "value"
        elif name != "bpm3_sum_x" and mono - self.retained_at[name] >= PERIOD_S:
            reason = "periodic"
        else:
            return None
        self.retained_at[name] = mono
        return reason


class SnapshotSelector:
    """Minute snapshots plus pump/closure/quality state boundaries."""

    def __init__(self):
        self.last_time = None
        self.previous = None

    def select(self, now, state, *, force=False):
        watch = state.get("watch", {}).get("Status", "")
        if "; closed observation" in watch:
            # Do not record a new totals snapshot on every tiny slope reversal.
            watch = "active" + watch.partition("; closed observation")[2]
        key = (
            tuple(state.get("counts", [])),
            state.get("interrupted"),
            state.get("active"),
            state.get("pump_state"),
            state.get("pumped"),
            watch,
        )
        selected = (
            force
            or self.last_time is None
            or key != self.previous
            or not 0 <= now - self.last_time < PERIOD_S
        )
        self.previous = key
        if selected:
            self.last_time = now
        return selected
