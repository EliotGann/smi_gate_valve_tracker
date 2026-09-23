"""Live commissioning interpretations, not durable pump/lifetime accounting.

Pressure states are instantaneous range descriptions, not the five-second vacuum
latch. Trends use monotonic receipt time, with explicit freshness and under-range
handling. A pressure rise does not identify a leak source or measure throughput.
"""

from collections import deque
from dataclasses import dataclass
from math import isfinite

from .physics import bragg_energy_ev

PRESSURES = {"pressure", "chamber_pressure"}
STATE_CODES = {
    "valve": {0: "Closed (assumed)", 1: "Open"},
    "fast_shutter": {0: "Open", 7: "Closed"},
    "photon_shutter": {0: "Open (assumed)", 1: "Closed"},
    "front_end_shutter": {0: "Open (assumed)", 1: "Closed"},
}


def describe(name: str, value: float) -> str:
    """Interpret a healthy raw number using operator-confirmed conventions."""
    if not isfinite(value):
        return "Unknown / nonnumeric"
    if name in STATE_CODES:
        return STATE_CODES[name].get(value, "Unknown code")
    if name in PRESSURES:
        if value < 0:
            return "Invalid pressure"
        if value == 0:
            return "Under range (reported zero)"
        if value < 0.01:
            return "Pumped down (raw <0.01)"
        if value > 700:
            return "Atmosphere (>700 mbar)"
        return "Above pump target"
    if name == "bpm3_sum_x":
        return "Unused: no beam inference"
    if name == "bragg":
        try:
            energy = bragg_energy_ev(value, minimum_ev=2100, maximum_ev=24000)
        except ValueError:
            return "Outside energy model"
        return f"Photon energy {energy / 1000:.3f} keV"
    if name == "ring_current":
        return "Current only; gate not set"
    if name == "ring_mode":
        return "Mode mapping not set"
    return "Diagnostic only"


@dataclass(frozen=True)
class Sample:
    value: float
    received_s: float
    severity: int = 0
    connected: bool = True

    def problem(self, now_s: float, stale_s: float) -> str | None:
        if not self.connected:
            return "Disconnected / read failed"
        if not 0 <= now_s - self.received_s <= stale_s:
            return "Stale / no fresh read"
        if self.severity < 0 or self.severity >= 3:
            return "Invalid source alarm"
        return None


class ClosedPressureTrend:
    """At most 61 ~1 Hz points over 30 s, plus one closure-observation baseline.

    Signed endpoint slope, not a fitted leak rate. First valid downstream reading
    after closure/recovery is the baseline, even at startup already closed. Any
    interruption or under-range value discards the current segment.
    """

    def __init__(self):
        self.points: deque[tuple[float, float]] = deque(maxlen=61)
        self.baseline: tuple[float, float] | None = None
        self.upstream_baseline: float | None = None

    def reset(self):
        self.points.clear()
        self.baseline = None
        self.upstream_baseline = None

    def observe(self, time_s: float, downstream: float, upstream: float | None):
        if self.baseline is None:
            self.baseline = (time_s, downstream)
        if upstream is not None and self.upstream_baseline is None:
            self.upstream_baseline = upstream
        if self.points and time_s - self.points[-1][0] < 1.0:
            return
        self.points.append((time_s, downstream))
        while self.points and time_s - self.points[0][0] > 30:
            self.points.popleft()

    def values(self, upstream: float | None) -> dict[str, float | str]:
        start_s, start_pressure = self.baseline
        end_s, end_pressure = self.points[-1]
        span = end_s - self.points[0][0]
        rate = (end_pressure - self.points[0][1]) / span if span >= 1 else float("nan")
        direction = "Collecting rate"
        if isfinite(rate):
            direction = "Rising" if rate > 0 else "Falling" if rate < 0 else "Unchanged"
        return {
            "Status": f"{direction}; closed observation",
            "Baseline": start_pressure,
            "Change": end_pressure - start_pressure,
            "Rate": rate,
            "Span": span,
            "Elapsed": end_s - start_s,
            "UpstreamChange": (
                upstream - self.upstream_baseline
                if upstream is not None and self.upstream_baseline is not None
                else float("nan")
            ),
        }


class Diagnostics:
    """Serialized latest-input cache and bounded closed-window trend."""

    def __init__(self, *, stale_s: float = 5.0):
        self.stale_s = stale_s
        self.samples: dict[str, Sample] = {}
        self.trend = ClosedPressureTrend()
        self.closed_since_s = float("inf")

    def update(self, name: str, sample: Sample):
        previous = self.samples.get(name)
        self.samples[name] = sample
        if name == "valve":
            if (
                previous is None
                or previous.problem(sample.received_s, self.stale_s)
                or (previous.value != 0)
            ):
                self.closed_since_s = sample.received_s
                self.trend.reset()
            if sample.problem(sample.received_s, self.stale_s) or sample.value != 0:
                self.trend.reset()
        if name == "pressure" and (
            sample.problem(sample.received_s, self.stale_s)
            or not isfinite(sample.value)
            or sample.value <= 0
            or (previous and previous.problem(sample.received_s, self.stale_s))
        ):
            self.trend.reset()
        if name == "chamber_pressure" and (
            sample.problem(sample.received_s, self.stale_s)
            or not isfinite(sample.value)
            or sample.value <= 0
            or (previous and previous.problem(sample.received_s, self.stale_s))
        ):
            self.trend.upstream_baseline = None

    def state(self, name: str, now_s: float) -> str:
        sample = self.samples.get(name)
        if sample is None:
            return "Waiting for input"
        problem = sample.problem(now_s, self.stale_s)
        if problem:
            return problem
        state = describe(name, sample.value)
        return f"{state} [alarm {sample.severity}]" if sample.severity else state

    def value(self, name: str, now_s: float) -> float | None:
        sample = self.samples.get(name)
        if sample is None or sample.problem(now_s, self.stale_s) or not isfinite(sample.value):
            return None
        return sample.value

    def snapshot(self, now_s: float) -> dict[str, float | str]:
        downstream = self.value("pressure", now_s)
        upstream = self.value("chamber_pressure", now_s)
        valve = self.value("valve", now_s)
        upstream = upstream if upstream is not None and upstream > 0 else None
        result = dict.fromkeys(
            ("Baseline", "Change", "Rate", "Span", "Elapsed", "UpstreamChange", "DeltaP"),
            float("nan"),
        )
        if downstream is not None and downstream > 0 and upstream is not None:
            result["DeltaP"] = abs(downstream - upstream)
        if valve != 0:
            self.trend.reset()
            result["Status"] = "Inactive: valve open" if valve == 1 else "Unknown valve state"
        elif downstream is None or downstream < 0:
            self.trend.reset()
            result["Status"] = "Unknown downstream pressure"
        elif downstream == 0:
            self.trend.reset()
            result["Status"] = "Under range: rate unavailable"
        elif self.samples["pressure"].received_s < self.closed_since_s:
            result["Status"] = "Waiting for post-close pressure"
        else:
            self.trend.observe(self.samples["pressure"].received_s, downstream, upstream)
            result.update(self.trend.values(upstream))
            if upstream is None:
                self.trend.upstream_baseline = None
                result["Status"] += "; upstream unknown/under range"
        return result
