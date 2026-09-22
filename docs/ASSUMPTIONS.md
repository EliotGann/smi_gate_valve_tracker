# Decisions and assumptions

Status vocabulary: **confirmed** = user answer; **observed** = supplied source
code, not live validation; **proposed** = design awaiting agreement; **unknown** =
must be supplied. Update this ledger as the design evolves. Date: 2026-09-22.

## Confirmed in the first discussion

| ID | Decision |
| --- | --- |
| C1 | Completion means strictly below **0.01 mbar**, correcting the original `1e2` notation to `1e-2`. |
| C2 | Atmosphere qualification means strictly above **700 mbar**. |
| C3 | Evacuated-side pressure is WAXS `XF:12IDC-VA:2{Det:300KW-TCG:7}P:Raw-I`, in mbar. |
| C4 | The other window face is at atmosphere; loading grows as the chamber is pumped. |
| C5 | Primary pump duration starts at the downward 700 mbar crossing, after atmosphere was observed. |
| C6 | Retain both full vent/pump counts and one count per closure that reaches pumped state. |
| C7 | Retain beam-path-enabled time regardless of window position and closed-window beam exposure time. |
| C8 | BPM3 **SumX** is selected for provisional beam-presence diagnostics. Photon-flux calibration is future work. |
| C9 | New valve full PV and polarity will be verified later. |
| C10 | Thickness, aperture, footprint and beam-position history will be verified later. |
| C11 | Consult controls before choosing the IOC framework. |
| C12 | This pass delivers design, Pixi, and tested offline primitives, not a simulated or live IOC. |

## Confirmed in the follow-up discussion

| ID | Decision |
| --- | --- |
| C13 | Exposures rarely reach **0.1 s**; generally they are **at least 0.5 s**. Repetition rate and edge reporting fidelity remain unknown. |
| C14 | Beam path: **FE → mono → BPM2 → photon shutter → BPM3 → fast shutter → attenuators → sample → GV6W → SAXS detector**. |
| C15 | BPM3 is upstream of the fast shutter and attenuators. It cannot confirm fast-shutter transmission or downstream attenuation. |
| C16 | There is no direct photon-energy PV. Plan to derive energy from the supplied Bragg readback conversion; units, offset and supported range still need verification. |
| C17 | Use **1e13 photons/s** as the user-supplied nominal unattenuated worst-case reference, multiplying by attenuator transmission and assuming sample transmission of one. |
| C18 | Keep **one upper-bound exposure model** initially, gated by ring, three shutters and closed window. BPM3 does not gate or scale this model. No parallel BPM-qualified exposure estimate. |
| C19 | Provisional beam-present comparator is **BPM3 SumX > 0.5 in native PV units**. Verify units, polarity, noise and hysteresis. Retain shutter-only timers and a separate BPM-qualified window timer. |
| C20 | Fast shutter is triggered through EPICS or hardware; its PV is expected to change in both cases. Actual edge cadence/latency still needs measurement. |
| C21 | Required energy coverage extends through **24 keV**. The 2.1 keV lower limit is proposed from source code, not newly confirmed. |
| C22 | Both attenuator banks are adjacent, after the fast shutter and before the sample. |
| C23 | Record pump milestones at **100, 10, 1 and 0.1 mbar**, alongside completion below 0.01 mbar; show current/last versus history. |
| C24 | Use both a fixed early reference and rolling recent history. Display ratios first; defer slowdown alarm thresholds until commissioning. |
| C25 | Setup is usually constant; use one normal population per window with optional notes for unusual cycles, rather than routine operator setup selection. |
| C26 | Display targets **legacy CS-Studio BOY `.opi`**. Originally planned as a separate repo; current organization uses `frontend/`, with optional later extraction. Shared documentation holds the layout and contract. |
| C27 | Normal pump-cycle frequency is approximately **at most once/hour**; display resolution may be adjustable. |
| C28 | Deploy as a service on a shared Linux IOC server, prioritizing bounded memory, stable resource use and frequent restart recovery. |
| C29 | Accept up to **1 s of uncommitted timer/exposure increments** after abrupt stop under healthy operation; immediately commit pump completion/window changes, and flush on graceful stop. |
| C30 | New window uses a **60 s arm, one-use token, typed current ID and explicit confirmation**. Restarts invalidate pending arms. Preserve old-window history and start fresh current-window statistics. |
| C31 | Record removal reason and report retired-window histories/averages by reason; current in-service window is excluded from completed-lifetime averages. |
| C32 | New-window action means a never-before-used physical window. Retired IDs cannot be reused; reinstallation is not initially supported. |
| C33 | A downward 700 crossing is only a candidate. Confirm at **P < 500 mbar within 120 s** of the original crossing; chatter does not extend its deadline. Keep rearming at **P > 700**, not 750/800. |
| C34 | Retain only one pending start crossing; discard expired candidates. Keep only the successful candidate in completed-cycle history, with bounded diagnostics rather than an ever-growing crossing list. |
| C35 | Vacuum qualifies after **5 s continuously observed below 0.01 mbar** and remains latched until **P > 0.02 mbar**. Record both the qualifying first-crossing time and confirmation time. |
| C36 | Pump duration ends at the successful vacuum dwell's first crossing. Integrated pumped time starts at confirmation, with no backdating of the dwell. |
| C37 | Organize the repository into `softioc/` (own Pixi project), `frontend/`, and `docs/`, with supplied Python examples under `docs/examples/bluesky/`. |

“Upper bound” denotes a nominal model over valid observation intervals, conditional
on the reference flux, transmission model and captured shutter edges. It is not a
proven bound on actual lifetime dose. Sample absorption is ignored deliberately;
sample-induced changes to the footprint still matter to any local-dose estimate.

## Proposed semantics implemented in the offline primitives

| ID | Assumption / consequence |
| --- | --- |
| P1 | Inputs are already normalized, time-ordered, and (where appropriate) debounced by a future adapter. `None` means unknown, not false. |
| P2 | Start/reconnect samples establish a baseline, never an invented open/close transition. Any unknown valve state or excessive time gap breaks transition continuity. |
| P3 | Full pump cycles require the window continuously known closed, a valid atmosphere observation, and subsequent target observation. Opening, invalid pressure, or a long gap invalidates an incomplete cycle. |
| P4 | Pump duration uses the latched `P <= 700` crossing only after timely <500 confirmation, and ends at the first <0.01 observation of a successful 5 s dwell. No sub-sample accuracy is claimed. |
| P5 | While start is pending, ignore repeated 700 crossings without resetting time. After confirmed start, a return to >700 aborts/re-arms; smaller rebounds do not restart timing. After timeout, a fresh >700 observation is needed to re-arm. |
| P6 | A closure observed from open to closed qualifies once when pumped, even if it closed into an already evacuated chamber. Startup-closed does not invent a closure; a full pump cycle may still be witnessed after startup. |
| P7 | Unknown pressure cancels an in-progress pump curve but does not erase a continuously observed closure. Unknown valve state does erase that closure's eligibility. |
| P8 | Interval accounting uses left-held values only over a caller-validated interval. Durations exceeding an explicitly supplied maximum gap produce unknown coverage, with no integrated quantities. |
| P9 | Metrics have separate validity: bad pressure or BPM3 does not suppress upper-bound exposure. Bad energy may invalidate attenuator transmission and deposited-energy weighting while timers continue. Known blockers establish zero exposure even if irrelevant model inputs are unknown. |
| P10 | Upper-bound photon rate is a finite nonnegative reference multiplied by valid transmission in [0,1]. Unknown foil states/model inputs are unknown, never silently unattenuated or zero. BPM3 values are only thresholded for diagnostics; invalid/stale readings produce unknown beam presence. |
| P11 | No automatic monitor fallback or calibration change; changes create a new model epoch. |
| P12 | Exposure is gated by closed window and beam-path eligibility, independent of pump state. |
| P13 | Intermediate milestones use first observed **P < threshold**, once per attempt, with elapsed time relative to the 700 mbar start. Crossing several thresholds in one sample gives equal observed times, not interpolated timings. |
| P14 | Baseline inputs are prior, completed, good-quality, comparable cycles only. Compare before admitting the current cycle to history; never reject a cycle merely because it is slow. |
| P15 | Proposed reference sizes are first 5 eligible cycles and most recent 20, minimum 5 for ratios. Sizes remain configurable/provisional. Mean, median and count are shown; default ratio uses median. |
| P16 | Early reference membership is frozen when established. Changes/removals require a new reference revision with reason. Recent history continues to update after each completed cycle. |

These proposals are executable discussion aids, not settled beamline operating
definitions. Tests lock the current interpretation so changes can be deliberate.

## Proposed production choices (not yet implemented)

- Observe readbacks only; this tracker has no valve/shutter/pump actuation role.
- Single ordered event reducer; monotonic time for online intervals and UTC plus
  source timestamps for history. Never subtract monotonic times across reboots.
- Per-PV validity, alarm severity, connection status, refresh policy, and expiry.
  A quiet change-only subscription is not evidence of staleness: periodic reads
  or an IOC heartbeat establish freshness independently of value changes.
- Debounce slow mechanical state changes; pressure dwell/hysteresis is now specified
  in C33–C36 and should be validated against measured noise. Fast shutter pulses require edge capture,
  not the same debounce as mechanical valves.
- Nominal atmospheric pressure is a configurable approximation if no barometer
  exists. No numeric production ambient-pressure default has been accepted.
- Loading threshold, mechanical debounce, sampling rates, maximum
  gaps, ring-current threshold/mode policy, and energy-motion policy are unknown.
- Local SQLite plus backed-up history; retain per-window and installation totals.
  One-second commit target is confirmed; retention and host/filesystem await controls input.
- No measured-dose Gy label without calibrated flux, beam geometry, and a documented
  energy-deposition approximation. The initial model may yield nominal photons
  and joules, explicitly labeled upper-bound estimates, not measured values.
  A future geometry-dependent nominal Gy estimate must likewise retain its model
  qualification; it is not a validated local-dose bound. All models carry IDs.
- Kapton is tentatively treated as homogeneous polyimide; grade, density,
  composition, layers, coatings, and coefficient data source require confirmation.

## Boundaries of the foundation

`PumpTracker` keeps in-memory counts and a bounded completed-cycle cache; its observation
times are caller-supplied monotonic seconds. It has no durable event journal,
mechanical debounce, raw pressure-curve store, timestamp-bracketing fields, or
recovery protocol. `account_interval` is one interval, not a scheduler or full
lifetime accumulator. Physics functions require caller-provided coefficients;
tests use synthetic coefficients and do not validate a Kapton dataset. No live
PV names, enumeration mappings, or coefficient values are asserted by tests.

Pressure start qualification and vacuum dwell/hysteresis are implemented offline.
The interval accountant requires the explicit latched `pumped` state, not a raw
threshold comparison. The adapter must deliver fresh valid pressure observations
or verified liveness refreshes and split integration at confirmation/exit/expiry.
It must not qualify a dwell simply by replaying stale cached values on timer ticks.

The milestone primitive retains first-observed times in memory, including a
snapshot while pumping. The comparison helper operates on caller-supplied eligible,
chronological prior durations for one metric/population; persistence, quality
selection, frozen membership/revisions and live elapsed-state classification are
production responsibilities. See PUMP_TRENDS.md for the complete contract.

The offline window-change guard validates and consumes an expiring proposal but
does not switch persistent statistics. SERVICE.md and WINDOW_LIFECYCLE.md specify
the future transaction/recovery and shared-host resource contracts. Offline memory
tests cover Python domain allocations, not yet live CA or database stability.
