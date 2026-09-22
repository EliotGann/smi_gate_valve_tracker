# Verification strategy

## Offline foundation (implemented)

Pressure-qualification regressions cover fixed deadlines under 700 mbar chatter,
strict 500 mbar confirmation and inclusive 120 s timeout boundary, timeout/rearming,
5 s vacuum dwell with interrupted dips, hysteresis through 0.02, disconnect/gap
requalification, integration from confirmation only, and retained-memory checks
over 51,000 chattering pressure observations without accumulating failed crossings.

Resource/lifecycle regression tests also cover 21,000 synthetic cycles with a
bounded cache and retained Python allocations after warm-up, repeated arm replacement,
expiry/cancel/restart behavior, mismatched identities, superseded tokens and
one-use consumption. This is not yet an RSS/native-memory or live-CA soak test.
See SERVICE.md for the staged memory, FD/task, overload and crash-injection matrix.

From `softioc/`, `pixi run check` runs lint, formatting checks and branch coverage.
From the repository root use `pixi run --manifest-path softioc/pixi.toml check`.
Tests exercise:

- Startup in open/closed/vacuum states without invented transitions.
- First-crossing milestone latches, strict boundaries, several thresholds crossed
  in one sample, immutable current/completed snapshots, resets on interrupted attempts.
- Early/recent mean/median comparisons, no self-inclusion when passed prior history,
  history readiness, zero/unresolved durations and gradual drift against the fixed reference.
- Atmosphere qualification, strict boundaries, vent dwell exclusion, full cycles,
  repeated cycles within a closure, and closing into existing vacuum.
- Return to atmosphere, opening mid-cycle, unknown/invalid pressure or valve state,
  time gaps, duplicate/backward timestamps, and reconnect baselines.
- Three-valued gating; every shutter/ring blocker; independent metric validity;
  pressure-independent exposure; upper-bound photon integration independent of BPM3.
- Bragg conversion against independent angular/energy examples and invalid-domain
  rejection; nominal reference-flux scaling, threshold boundary/unknown inputs.
- 0.1 s and 0.5 s observed shutter intervals, separating the diagnostic BPM timer
  from the single photon/interaction model; missing transmission versus known blockers.
- Dimensional examples for pressure-time, beam time and integrated interaction.
- Slab transmission/deposition limits, conversion of eV to joules, illuminated
  mass, beam-area dependence, thickness behavior, and invalid inputs.
- Property-based checks for bounded deposition and additive interval accounting.

The branch coverage target is 95% for the small offline package. Coverage is not
validation of PV mappings or Kapton material parameters. Test constants for
coefficients, density, thickness, area, ambient pressure and maximum gaps are
synthetic and are not deployment defaults.

## Full reducer tests (phase 2)

- Recorded pressure traces including slow leaks, rough/turbo handoff, gauge
  changes, no atmosphere seen, under-range, stuck readings, noise and dwell.
- Stable-state debounce, MOVING across endpoint transitions, fault/reconnect
  distinction, hysteresis and accurate candidate/confirmation timestamps.
- Interval splitting at transitions, refresh expiry, calibration/installation
  boundaries; equal-time atomic updates; delayed/out-of-order source events.
- Midnight, DST, NTP wall-clock steps and reboot monotonic reset.
- Reference numerical integrals for variable energy/flux and shutter duty cycles;
  rate/resolution sensitivity with analytic ground-truth traces.
- Property/stateful tests: counts nonnegative, at most one qualification per
  closure, window time <= beam-path time when comparing the same valid intervals,
  no dose during known blocked intervals, deterministic replay.

## Persistence and transport tests (phases 3–4)

- Process kill before/after each transaction boundary; recovery must yield either
  a whole committed increment or none. Replay duplicates cannot double-count.
- Disk full, lock contention, corrupt checkpoint, missing database, migration
  errors, interrupted pump cycle, backup/restore and two-process writer exclusion.
- Loopback fake input IOC on isolated local CA ports; real selected CA client and
  output IOC; enum strings/numerics, disconnect/reconnect, alarms and refresh reads.
- Quiet unchanged PV remains healthy with successful refresh; connected-but-stalled
  acquisition marked unknown when the appropriate heartbeat stops.
- Read-only output writes rejected; input adapter has no actuator-write path.
- CA count precision, engineering units, ID string lengths, alarm propagation,
  durable sequence consistency and listener cleanup on shutdown.

## Physics and calibration tests (phase 5)

- Independent material-table reference points across the supported energy range;
  near-edge interpolation, range rejection, table checksum/provenance checks.
- Thin/thick slab limits; zero attenuation; energy-absorption versus attenuation
  coefficients; expected dose-area scaling. Monitor-response calibration is future work.
- Beam-path attenuator ordering, inserted-state polarity, dark/gain changes and
  explicit no-double-correction cases. Reject unsupported setup/calibration epochs.
- Validation against known foil transmission and measured flux where feasible.

## Beamline acceptance and soak (phases 6–7)

Validate fast-shutter readback edges for **both EPICS and hardware trigger paths**.
Check Bragg-derived energy and attenuation/model coverage through **24 keV**.
Use annotated pump histories to validate early/recent membership, milestone times,
displayed averages/ratios and preservation of slow/aborted cycles. A slow trace
must remain visible; it must not be automatically removed as an outlier.

BOY `.opi` layout, fake-server scenarios, array consistency and cross-component
contract checks are specified in DISPLAY.md. Tests here cover server-side offline
primitives; actual BOY runtime acceptance belongs to the `frontend/` component.

Use a manually annotated set of vent/pump/valve operations, deliberate IOC restarts,
shutter pulses at **0.1 s and 0.5 s** and longer, beam trips, and energy
changes. Compare cycle counts, timing resolution and exposure estimates against
independent records. Record expected accuracy before accepting results.

Soak long enough to include normal beamline operating changes; monitor memory,
queue depth, reconnect recovery, disk growth, database latency and backup health.
Publish measured uncertainty/coverage and ensure displays distinguish unknown
from zero. Exercise a window replacement and restored history before routine use.
