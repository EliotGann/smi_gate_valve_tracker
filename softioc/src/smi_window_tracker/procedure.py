"""Read-only procedure observation; never an equipment permissive/interlock.

Two paths are classified from fresh pressure observations at Kapton closure.
Monotonic hold time requires continuously observed isolation and valid pressure.
All warnings latch for the episode, and its final result survives restart.
"""

from math import isfinite

LIMIT_MBAR = 0.009
VENTED_MBAR = 700.0


class Procedure:
    def __init__(self, restored=None, *, hold_seconds=300.0):
        if not isfinite(hold_seconds) or hold_seconds <= 0:
            raise ValueError("Hold duration must be finite and positive")
        self.hold_seconds = hold_seconds
        saved = restored or {}
        self.number = saved.get("number", 0)
        self.last = saved.get("last")
        active = saved.get("episode")
        if active:
            self.last = {**active, "result": "Interrupted by restart; no hold restored"}
        self.episode = None
        self.kapton = None
        self.downstream = None
        self.previous_time = None
        self.hold_start = None
        self.hold_elapsed = 0.0
        self.phase = "Acquiring valve states"
        self.current_problem = ""
        self.last_signature = None

    @property
    def path(self):
        return self.episode["path"] if self.episode else "unclassified"

    def _warn(self, message):
        if message not in self.episode["warnings"]:
            self.episode["warnings"].append(message)

    def observe(self, now, inputs, *, utc):
        """Return a sparse transition record (or None), after each event and tick."""
        valve = inputs.value("valve", now)
        detector = inputs.value("downstream_valve", now)
        up = inputs.value("chamber_pressure", now)
        down = inputs.value("pressure", now)
        up = up if up is not None and up > 0 else None
        down = down if down is not None and down > 0 else None
        gap = self.previous_time is not None and not 0 <= now - self.previous_time <= 5
        if gap:
            self.kapton = self.downstream = None
            self.hold_start = None
            self.hold_elapsed = 0.0
            if self.episode:
                self._warn("Observation gap: sequence not verified")

        # Baseline closed is explicitly unclassified: never infer a closure edge.
        if valve == 0 and self.episode is None:
            observed = self.kapton == 1
            path = "unclassified"
            if observed and up is not None and down is not None:
                if up < LIMIT_MBAR and down < LIMIT_MBAR:
                    path = "vacuum-first"
                elif up > VENTED_MBAR and down > VENTED_MBAR:
                    path = "manual-pump"
            self.number += 1
            self.episode = {
                "id": self.number,
                "path": path,
                "start_utc": utc,
                "closure_observed": observed,
                "initial_upstream": up,
                "initial_downstream": down,
                "downstream_at_close": detector,
                "warnings": [],
                "hold_required_s": self.hold_seconds,
                "pressure_limit_mbar": LIMIT_MBAR,
                "vent_threshold_mbar": VENTED_MBAR,
                "vent_complete_utc": None,
                "hold_baseline_mbar": None,
                "peak_downstream_mbar": down,
                "hold_completed": False,
                "detector_open_utc": None,
                "saw_low_pressure": down is not None and down < LIMIT_MBAR,
            }
            if not observed:
                self._warn("Closure not observed: initial sequence unverified")
            if detector == 1:
                self._warn("Kapton closed while GV7 OPEN")
            elif detector != 0:
                self._warn("Kapton closure: GV7 closed status UNVERIFIED")

        self.current_problem = ""
        if self.episode:
            e = self.episode
            if (
                detector == 1
                and self.downstream == 0
                and (valve != 0 or up is None or down is None)
            ):
                self._warn("GV7 opened with required input unavailable")
            if self.kapton is None and valve == 0 and self.previous_time is not None:
                self._warn("Observation gap: sequence not verified")
            if valve == 1:
                self.last = {**e, "end_utc": utc, "result": "Kapton reopened"}
                self.episode = None
                self.hold_start, self.hold_elapsed = None, 0.0
                self.phase = "Kapton open; last result retained"
            elif valve != 0 or detector not in (0, 1) or up is None or down is None:
                self.current_problem = "Required valve/pressure unknown or under range"
                self._warn("Observation interrupted: required input unavailable")
                self.hold_start, self.hold_elapsed = None, 0.0
                self.phase = "Observation incomplete"
            elif detector == 1:
                if e["detector_open_utc"] is None:
                    if self.hold_start is not None and up > VENTED_MBAR and down < LIMIT_MBAR:
                        self.hold_elapsed = now - self.hold_start
                    e["detector_open_utc"] = utc
                    e["pressure_at_open_mbar"] = down
                    e["hold_at_open_s"] = self.hold_elapsed
                    if self.downstream != 0:
                        self._warn("GV7 opening not observed: sequence unverified")
                    if down >= LIMIT_MBAR:
                        self._warn("GV7 opened at/above 0.009 mbar")
                    if e["path"] == "vacuum-first" and self.hold_elapsed < self.hold_seconds:
                        self._warn("GV7 opened before isolated hold completed")
                    if e["path"] == "unclassified":
                        self._warn("GV7 opened with unclassified preparation")
                    if up <= VENTED_MBAR:
                        self._warn("GV7 opened before WAXS >700 mbar")
                self.hold_start = None
                self.phase = "Detector connected; isolated test ended"
                if down >= LIMIT_MBAR:
                    self._warn("Downstream pressure at/above 0.009 mbar")
            else:
                if e["detector_open_utc"] is not None:
                    # A re-isolation needs a new observation period; never reuse a past hold.
                    e["detector_open_utc"] = None
                    self.hold_start, self.hold_elapsed = None, 0.0
                    self._warn("GV7 reclosed: new isolated observation required")
                peak = e["peak_downstream_mbar"]
                e["peak_downstream_mbar"] = down if peak is None else max(peak, down)
                if down < LIMIT_MBAR:
                    e["saw_low_pressure"] = True
                # Atmosphere is expected while manually pumping; alarm on failure
                # to maintain vacuum only after this path first reaches the limit.
                if down >= LIMIT_MBAR and (e["path"] == "vacuum-first" or e["saw_low_pressure"]):
                    self._warn("Downstream pressure at/above 0.009 mbar")
                if up > VENTED_MBAR and e["vent_complete_utc"] is None:
                    e["vent_complete_utc"] = utc
                if e["path"] == "vacuum-first":
                    if up <= VENTED_MBAR or down >= LIMIT_MBAR:
                        self.hold_start, self.hold_elapsed = None, 0.0
                        self.phase = (
                            "Venting WAXS" if up <= VENTED_MBAR else "Pressure limit exceeded"
                        )
                    else:
                        if self.hold_start is None:
                            self.hold_start = now
                            e["hold_baseline_mbar"] = down
                            e["hold_start_utc"] = utc
                        self.hold_elapsed = now - self.hold_start
                        e["hold_elapsed_s"] = self.hold_elapsed
                        e["hold_pressure_change_mbar"] = down - e["hold_baseline_mbar"]
                        e["hold_completed"] = self.hold_elapsed >= self.hold_seconds
                        self.phase = (
                            "Minimum hold met; continue observing"
                            if e["hold_completed"]
                            else "Isolated hold in progress"
                        )
                elif e["path"] == "manual-pump":
                    self.phase = (
                        "Manual pump: below opening threshold"
                        if down < LIMIT_MBAR
                        else "Manual pump: above opening threshold"
                    )
                else:
                    self.phase = "Unclassified closure; observe pressures"
        else:
            self.phase = "Kapton open" if valve == 1 else "Acquiring valve states"
            if valve not in (0, 1) or detector not in (0, 1):
                self.current_problem = "Valve status unavailable; sequence not verified"
        self.kapton = valve if valve in (0, 1) else None
        self.downstream = detector if detector in (0, 1) else None
        self.previous_time = now
        # Timer increments/pressure noise go in the checkpoint, not new event rows.
        signature = (self.number, self.phase, self.current_problem, tuple(self.warnings()))
        if signature != self.last_signature:
            self.last_signature = signature
            return {"utc": utc, "phase": self.phase, **self.snapshot()}
        return None

    def warnings(self):
        return (self.episode or self.last or {}).get("warnings", [])

    def snapshot(self):
        return {"number": self.number, "episode": self.episode, "last": self.last}

    def outputs(self):
        warnings = self.warnings()
        level = 3 if self.current_problem else 2 if warnings else 0
        alarm = self.current_problem or "; ".join(warnings) or "No observed procedural warning"
        return {
            "ProcedurePath": self.path,
            "ProcedureState": self.phase,
            "ProcedureAlarm": alarm,
            "ProcedureSeverity": float(level),
            "HoldElapsed": self.hold_elapsed,
            "HoldRemaining": max(0, self.hold_seconds - self.hold_elapsed),
            "OpeningLimit": LIMIT_MBAR,
            "LastProcedure": (
                f"#{self.last['id']} {self.last['path']}: {self.last['result']}; "
                f"warnings={len(self.last['warnings'])}"
                if self.last
                else "No completed procedure episode"
            ),
        }
