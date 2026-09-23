# Soft IOC design and implementation plan

Commissioning corrections: primary pump-down input is TCG:9 `P-I`; WAXS TCG:7
is the measured sample-chamber pressure on the opposite face. Both are mbar;
loading uses their difference, not a fixed atmospheric reference. `P-I` remains
numeric, reporting zero below range. The BPM-qualified timer/beam inference is
disabled (0.6 observed without beam); raw SumX remains diagnostic only.
Operator-accepted binary conventions and under-range details are in PVS.md.
The live v2 [closed-window watch](CLOSED_WINDOW_WATCH.md) handles closure with
both sides already pumped followed by upstream venting. It tracks downstream
rise separately from full pump cycles; durable episode recording remains planned.

## 1. Objectives and metric contract

The tracker observes the new Kapton-window valve and relevant beamline readbacks
continuously, independently of Bluesky acquisitions. Publish current status and
lifetime totals through EPICS and retain enough history to explain/recompute
those totals. Use a window installation ID and configuration/calibration epochs.

| Metric | Meaning |
| --- | --- |
| OpenCount / CloseCount | Observed confirmed state transitions; startup creates no transition. |
| ClosedPumpedCount | Each observed closure reaching confirmed/latching vacuum (5 s below 0.01), at most once per closure. |
| FullPumpCount | Each closed-window atmosphere → 700 crossing → <500 within 120 s → qualified vacuum sequence. Several may occur in one closure. |
| LastPumpTime / curve | Crossing-to-target duration, timestamps, threshold brackets, pressure history and quality. |
| Pump milestones / comparisons | Cumulative and stage times at 100, 10, 1, 0.1 mbar and final target; current/last versus fixed early and recent averages/medians. |
| ClosedPumpedTime | Integrated known closed-and-pumped seconds, independent of full-cycle count. |
| LoadedTime / DPIntegral | Closed-window differential-pressure threshold time and mbar s loading proxy. |
| BeamPathTime | Ring eligible and all three shutters open, regardless of valve state. |
| WindowBeamTime | BeamPathTime restricted to confirmed window closed, regardless of pressure. |
| BPMQualifiedWindowTime | Disabled pending calibration; no accepted beam-presence threshold. |
| UpperBoundPhotons | Window-gated integral of 1e13 photons/s × attenuator transmission, with sample transmission assumed one. |
| UpperBoundInteractionJ | Energy/thickness-weighted deposited-energy estimate from the same upper-bound photon model, once material inputs are known. |
| ValidTime / UnknownTime | Separate coverage for each integrated metric, never silently treating unknown as zero exposure. |

Counts are observed counts; outages can hide transitions. Report gap events and
coverage alongside counts. An “all-time” total means since installation/initial
recorded offset, not a claim about activity before tracking began.

Initial exposure model: **one nominal upper-bound channel**, not a calibrated BPM
flux estimate or a parallel BPM-qualified exposure channel. BPM3 SumX provides
raw diagnostics only for now. Derive photon energy from Bragg readback
because no direct energy PV exists. See PHYSICS.md for formulae and future
measured-flux calibration. Main beam-path ordering is now confirmed in PVS.md.

## 2. Architecture

```
CA readback subscriptions + periodic health reads + monotonic timer
        -> normalized input events (value, units, source/receive time, quality)
        -> single ordered reducer
           - input validity and freshness
           - valve/pressure state machines
           - metric-specific interval eligibility and integration
           - completed/aborted cycle and installation events
        -> transaction: event journal + interval increments + checkpoint
        -> committed read-only IOC status/totals
        -> history export and trend analysis
```

Keep the reducer independent of CA, database, clock implementation and IOC
framework. Inputs have a logical name separate from PV name. State mappings,
unit conversions and thresholds live in versioned configuration. No import of
the supplied Bluesky startup modules: many instantiate control devices and local
Python signals that are not usable as independent IOC inputs.

Production modules proposed: `inputs` (CA), `normalize`, `engine`, `physics`,
`storage`, `ioc`, `config`, `replay`, and `cli`. Present foundation modules are
`cycles`, `trends`, `intervals`, `physics`, and `lifecycle`; they are small offline components,
not a complete event-driven service.

## 3. Framework decision

| Option | Advantages here | Questions/costs |
| --- | --- | --- |
| caproto client + server | Python-native CA, asyncio option, easy local fake servers, simple Pixi packaging, shared Python domain model | Confirm controls support, record/alarm behavior, long-lived operation, CA network deployment. |
| pythonSoftIOC + CA client (e.g. cothread/catools) | EPICS Base-backed records, familiar IOC/record behavior and site tooling | More native dependencies; align event loop/threading and supported Python/package stack with controls. |
| EPICS Base records plus sequencer/custom support | Closest fit to an established native IOC deployment | Complex cycle histories, replay and calibration are less convenient; still need a persistence/history component. |

**Recommendation for discussion:** caproto for this small calculation/history IOC,
if controls will support it. **Decision:** pending controls consultation. Keep
transport independent so changing the framework does not rewrite the physics or
counter semantics. An optional Pixi caproto environment supports evaluation.

Shared-host resource ownership, framework acceptance tests and restart durability
are detailed in [SERVICE.md](SERVICE.md). Choose based on controls support and
measured reconnect/soak results, not a presumed leak-free framework.

## 4. Valve and pump state machines

For this commissioning scope use operator-accepted 1=open/0=closed for GV6W,
1=closed/0=open for FE and photon shutters, and 7=closed/0=open for fast shutter.
The first two conventions include assumed endpoints from negated status bits;
other codes or invalid inputs are unknown. The richer endpoint model below is
a future option, not a requirement to acquire opposite-status PVs now.
Normalize valve inputs to OPEN, CLOSED, MOVING, UNKNOWN/FAULT. Production should
use positive endpoint confirmation; never equate every non-open value to closed.
Debounce mechanical endpoints without discarding physical moves. Count arrival
at the opposite confirmed endpoint across a normal MOVING state, but not across
a disconnect where hidden transitions could have occurred. The primitive takes
already-resolved bool/None states and does not implement MOVING handling.

Pump sequence:

1. IDLE: await continuously closed window and a valid atmosphere observation.
2. ARMED: `P > 700`; update the atmosphere-side crossing bracket as samples arrive.
3. CANDIDATE: first sample at/below 700 latches a single candidate time. Require
   P < 500 by candidate time +120 s (inclusive deadline); P=500 is insufficient.
   Ignore 700 chatter while pending. Timeout discards the candidate; a fresh
   >700 observation re-arms, with no accumulation of failed crossing records.
4. PUMPING: after confirmation, use the original candidate time as start. Store
   the successful attempt's milestones/curve; pending display is not yet “pumping.”
5. VACUUM QUALIFYING: P < 0.01 must persist for 5 s of valid observations. Any
   observation >=0.01 before confirmation resets this low candidate.
6. COMPLETE: at dwell confirmation, increment once and record both first crossing
   and confirmation time. Duration ends at the first crossing, not confirmation.
7. Await another atmosphere observation to re-arm. Threshold chatter near vacuum
   must not count additional full cycles.

Opening, invalid pressure, loss of window state, or excessive acquisition gap
interrupts a pending cycle. Save an aborted/partial record in production rather
than making it disappear. If pressure returns above 700 after confirmed start, close the incomplete
attempt and arm a new one. Pump-on readbacks can supply a secondary duration but
are not necessary for the agreed pressure-crossing duration.

ClosedPumpedCount is independent: track a closure episode from an observed
open→closed transition, increment once when pumped, and allow full pump cycles to
repeat within it. Startup already pumped contributes known pumped time but
does not invent a closure or a completed historical pump cycle.

For production dwell confirmation, retain both first-candidate crossing time and
confirmation time, so increasing dwell does not silently bias trend duration.
Store start/end sample brackets. If start is in [s0,s1] and end in [e0,e1], a
duration lies in [max(0,e0-s1), e1-s0]. Interpolation is an optional versioned
estimate, not a replacement for brackets. Foundation uses first-observed times.

The independent pumped-state latch becomes true only at vacuum confirmation,
remains true through 0.01–0.02 mbar, and becomes false strictly above 0.02.
Invalid pressure/gaps clear qualification to unknown; reconnect requires a new
dwell. Integrated closed+pumped time begins at confirmation without backdating.
Vacuum can qualify while the valve is open; closing into already confirmed vacuum
qualifies a closure immediately, but creates no full pump cycle. The future
adapter integrates old state before applying each confirmation/exit event.

Detailed milestone recording, baseline eligibility and live/last comparison
semantics are in [PUMP_TRENDS.md](PUMP_TRENDS.md). Intermediate crossings are
latched once using existing pressure events. Keep fixed early and recent baselines
for the normal setup on each window; show ratios without slowdown alarms initially.

## 5. Integration, timestamps, and data quality

- On any input event or timer tick, integrate the preceding piecewise-constant
  interval before applying the new input. Split exactly at expiry and state edges.
- Use monotonic receipt time for causal online accounting; retain source UTC and
  receipt UTC for diagnosis. Source time may improve shutter edge timing only
  after verifying synchronization and ordering. Keep ordering/late-event policy explicit.
- Reject duplicate/reversed reducer timestamps or identify them by sequence number.
  Coalesce same-time updates atomically. Never integrate a negative duration.
- Inputs with INVALID alarms, nonfinite/out-of-range values, disconnect, unsupported
  enum, or failed liveness refresh are unknown. Gauge under-range is not necessarily
  a numeric zero; interpret its status explicitly.
- AND eligibility is three-valued: any known blocker gives false; otherwise an
  unknown necessary input gives unknown. A known false gate establishes zero rate
  without needing valid pressure/flux/energy irrelevant to that metric.
- Maintain metric-specific coverage and reason codes. Energy loss suspends weighted
  interaction and any energy-dependent foil transmission estimate; timers continue.
  BPM3 loss affects its diagnostic timer, not the upper-bound exposure calculation.
- Do not extrapolate through downtime or across missing rapid shutter pulses.
  Online totals are estimates over valid coverage, not guaranteed lower bounds
  on physical dose. Expose quality and model limits explicitly.
- Sampling proposal to evaluate: pressure/slow diagnostics around 1–10 Hz,
  status subscriptions on every transition, outputs/checkpoints around 1 Hz.
  Final rates follow measurements and timing requirements, not these guesses.
- A fast shutter can pulse between CA updates. Increasing Python polling cannot
  recover unreported edges. Use reliable edge timestamps, cumulative gate time,
  or hardware integration if required by the shortest exposure.

Confirmed exposures: rarely **0.1 s**, usually **>=0.5 s**. Validate both fast-shutter
edges against an independent timing reference at these durations and expected
repetition rates. A 1 Hz output/checkpoint cadence is compatible with faster edge
capture; a 1 Hz input poll is not. No mechanical-state debounce may swallow a
0.1 s shutter pulse. As a proposed accuracy target, 10% duration error at 0.1 s
allows only 10 ms total duration uncertainty; the target still needs agreement.
A cumulative gate-time counter alone is insufficient to apportion exposure across
changing valve, foil and energy states unless its intervals can be aligned.

The shutter is triggered via EPICS or hardware; the user expects the PV to change
for either trigger source. Verify this expectation during commissioning rather
than requiring a different timing source in advance. Energy support must extend
through 24 keV, including the attenuator and Kapton coefficient models.

## 6. Durable history and restarts

Proposed local SQLite schema (schema-versioned migrations):

| Table | Principal fields |
| --- | --- |
| installations | window ID, lot, thickness, aperture, installed/removed UTC, operator, notes |
| model_epochs | config hash, code version, complete config, coefficient/calibration IDs and checksums |
| sessions | session ID, process start/stop UTC, monotonic origin metadata, end reason |
| input_events | sequence, session, logical input, source/receipt timestamps, value, units, alarm/quality |
| intervals | sequence range, installation/epoch, metric increments and valid/unknown durations |
| pump_cycles | cycle/closure IDs, crossing times/brackets, end state, duration, metrics, reason |
| pump_milestones | attempt/threshold key, crossing time/bracket, cumulative time, quality |
| pump_references | fixed/recent membership IDs, definition/revision, statistics, selection reason |
| pump_comparisons | attempt/metric, reference snapshot IDs, duration/ratio/delta, quality |
| pressure_samples | cycle/sequence, times, raw/normalized pressure, gauge quality |
| checkpoints | last committed sequence, counters, reducer snapshot, schema/config identity |
| audit_events | install/remove, config/model changes, initial offsets, explicit corrections/backfills |

Use one writer. Atomically commit event(s), interval increments, cycle changes and
checkpoint; publish durable totals only after successful commit, with a sequence
PV allowing readers to detect a consistent generation. Replay after checkpoint
must be idempotent using unique sequence/interval IDs. Avoid separately committed
counter and event updates. Confirmed normal-operation target is at most 1 s of
uncommitted increments; pump completions/window switches commit immediately.
Monitor total queue/commit age and expose failures to meet that target.

On restart, restore totals and epochs, create a new session, record downtime,
and reacquire input baselines. Do not integrate old monotonic timestamps or
assume an in-progress cycle completed while down. A previous partial cycle is
interrupted unless an explicit, provenance-tagged archive reconstruction is run.

On write failure, freeze committed outputs and expose unhealthy storage status;
bound any in-memory queue. Disk-full/overflow creates a recorded gap after
recovery. A corrupt or missing existing database must not silently reset lifetime
totals. New database creation is a distinct initialization operation.

Choose local storage compatible with SQLite locking/WAL; do not assume an NFS
home directory is appropriate. Use SQLite-aware backups, verify restore, and
retain event/curve exports. Set retention from measured rate × bytes/event ×
operating years. Preserve full pump curves and installation summaries even if
continuous raw diagnostics are downsampled. Store aggregation method and gaps.

Window replacement closes one installation and opens another with new material
parameters; it never erases old history. Keep optional facility-level totals.
Manual corrections are signed deltas with author/reason, not direct overwrites.

[WINDOW_LIFECYCLE.md](WINDOW_LIFECYCLE.md) specifies the agreed expiring arm/token/
typed-ID confirmation, atomic switch, retired-window comparisons and removal
reasons. New windows start zeroed totals and fresh pump references; restarts restore
the existing window. Pending confirmations are never restored. Old physical IDs
cannot be reused. All-history queries are paginated; lifetime aggregates belong
in storage, not ever-growing in-memory lists.

## 7. Proposed published PV contract

Prefix is **TBD**, suffixes illustrative and read-only unless explicitly agreed.

- Identity: `WindowID`, `ConfigID`, `ModelID`, `Version`, `SessionID`.
- Current inputs/states: `ValveState`, `Pressure`, `DeltaP`, `PumpState`,
  `BeamEligible`, `Energy`, `BPM3SumX`, `BPMBeamPresent`, `UpperBoundPhotonRate`,
  per-input `Quality`/`Age`.
- Counters: `OpenCount`, `CloseCount`, `ClosedPumpedCount`, `FullPumpCount`,
  `InterruptedPumpCount`.
- Time/loading: `ClosedPumpedTime`, `LoadedTime`, `DPIntegral`, `BeamPathTime`,
  `WindowBeamTime`, `BPMQualifiedWindowTime` (seconds or mbar s in engineering units).
- Exposure: `UpperBoundPhotons`, `UpperBoundInteractionJ` with independent quality
  and model identity. Future measured-flux/dose outputs require a new calibration
  epoch; they do not silently replace or relabel the existing model totals.
- Pump summary: `LastPumpTime`, `LastPumpStart`, `LastPumpEnd`, `LastPumpQuality`,
  current elapsed time and last-cycle ID; milestone and early/recent comparison
  groups in PUMP_TRENDS.md. Detailed curves live in history, with bounded arrays
  for the BOY plots as specified in DISPLAY.md.
- Health: `Heartbeat`, `StorageOK`, `LastCommitUTC`, `CommitSeq`, `QueueDepth`,
  input/metric quality bitmasks, per-metric valid/unknown time.

Use a deliberate CA numeric representation: classic LONG is signed 32-bit.
Double-valued counts represent integers exactly up to 2^53; retain Python/SQLite
integers internally and document wire limits. Test strings/IDs against CA length
limits; waveform strings may be needed. All counters must remain monotonic within
an epoch except explicitly reported corrections. Display units and last-update
quality, including whether an exposure value is nominal upper-bound or calibrated.

## 8. Milestones and acceptance criteria

| Phase | Deliverable | Exit criterion |
| --- | --- | --- |
| 0 (this pass) | Requirements, PV map, architecture/physics, Pixi, offline primitives | Reviewed assumptions; automated offline checks pass. |
| 1 | Controls decision; exact PV/enum/units survey; beam-path drawing; material/geometry inputs | Every required signal mapped with evidence; rapid-shutter observability demonstrated. |
| 2 | Full reducer/config validation/replay and pressure history | Synthetic and recorded traces give agreed counts, curves, bounds and selective coverage. |
| 3 | SQLite transactions, installations, epochs, backup/recovery | Crash injection and duplicate replay produce no double counts; restore verified. |
| 4 | Selected CA client/server, fake input IOC, metric PVs | Loopback tests verify connection/alarm handling, PV metadata and read-only metrics. |
| 5 | Upper-bound reference, validated attenuator transmission and versioned Kapton coefficient data | Reference-point physics tests, unit audit and model provenance checks pass; BPM3 calibration deferred. |
| 6 | Read-only beamline shadow run and operator display/trends | Compare manual cycle log, known shutter exposures and independent timer for an agreed period. |
| 7 | Supervised service, backups, ownership and maintenance runbook | Restart/power-loss exercise and window-change workflow accepted by beamline/controls. |

Useful first plots: pump duration versus cycle/date (with incomplete cycles and
timing uncertainty visible), overlaid log-pressure curves, cumulative loaded
hours, beam hours, upper-bound photon exposure and interaction estimate with model epochs and
coverage gaps. Export CSV summaries plus machine-readable raw event/curve data.

## 9. Companion operator display

Build a **CS-Studio BOY `.opi`** display under `frontend/` alongside the
`softioc/` application. It can be extracted into a separate repository later.
[DISPLAY.md](DISPLAY.md) defines the overview wireframe, related screens,
PV/array contract, data-quality presentation and acceptance plan. Develop against
fake PVs in phase 4, review pump-trend views during phases 5–6, and release with
an IOC/display compatibility version. Display-side logic formats and plots values;
the server owns history, reference selection and calculations.

Add retired-window history, current/last-window comparison and an explicit
maintenance-only new-window workflow. Layout is adjustable; the wireframe size
is a starting point, not a fixed workstation-resolution requirement.
