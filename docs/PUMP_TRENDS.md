# Pump-down milestones and degradation trends

## Purpose and agreed scope

Track changes in pump-down performance as a possible indication of a deteriorating
Kapton window. A longer duration alone does not identify the cause: pump performance,
outgassing after a long vent, leaks elsewhere and gauge changes also matter. The
initial display reports measurements and comparison ratios, **without automatic
slowdown alarms or a “window failed” diagnosis**. Data-quality alarms remain separate.

Agreed: milestones at 100, 10, 1, 0.1 mbar plus completion below 0.01 mbar; both
fixed early and rolling recent references; normally constant setup, optional notes
for unusual cycles. Population defaults to this window's normal setup.

## Milestone semantics and efficient recording

- Start is the first observed P <= 700 after P > 700 while closed, **accepted only
  when P < 500 within 120 s**. Retain its original timestamp; no restart of that
  deadline when pressure chatters around 700. Discard timeout candidates and
  require a fresh >700 observation to re-arm. Only one candidate is held in RAM.
- Each milestone latches the first valid observation **strictly below** its
  threshold after start. Final completion requires a 5 s dwell strictly below
  0.01; its endpoint is the first crossing of that successful dwell, with a separate
  confirmation timestamp. Intermediate milestones remain simple first-crossing latches.
- For each crossing retain elapsed seconds from start, source/receipt UTC,
  preceding/current sample bracket, observed pressure, quality and timing-definition ID.
- Store cumulative durations and derive stage durations by subtraction:
  700→100, 100→10, 10→1, 1→0.1, 0.1→0.01 mbar. A rebound does not reset a latched
  milestone; stage durations include subsequent rebounds/stalls until the next crossing.
- A single sample may cross several thresholds: latch all at that observation
  time, mark unresolved stage timings, and retain brackets. Zero observed stage
  duration is not a resolved physical zero; do not use it as a ratio denominator.
- Preserve partial milestones for interrupted confirmed cycles in production. Re-venting
  above 700 after start confirmation ends that attempt and starts fresh atmosphere qualification. Opening,
  invalid input and acquisition gaps follow the existing interrupted-cycle policy.

No additional PV polling is needed: evaluate the four pending milestone comparisons
on pressure events already acquired for the curve. At most four milestone records
and one completion per attempt, plus the existing pressure history. Group writes
transactionally with the event/checkpoint; do not make a disk transaction per
threshold comparison. Once latched, a milestone never generates repeated events.

Candidate crossings are not pump attempts/history rows. Do not emit a log/event
or retain a curve for every 700 crossing. Retain one candidate timestamp and, if
needed for plots, a byte/sample-bounded 120 s preview ring. On timeout discard it;
on confirmation retain the successful candidate/preview. Rate-limit diagnostics.
The vacuum qualifier also retains one timestamp, replacing it on failed dwells.
The foundation's milestone list is fixed by the configured milestone count.

This update is timing definition `qualified-pressure-v2`. Do not silently mix
its duration/pumped-time baselines with the earlier unqualified-threshold definition.

Propose retaining raw accepted pressure events throughout a pump attempt, batched
to disk; separately produce bounded/downsampled arrays for the display. Preserve
threshold-neighbor points, extrema and gaps when reducing curves. Measurement
rate must be established from actual pressure update cadence and desired timing
uncertainty, not from display refresh frequency. This foundation stores latched
elapsed times, not the production curve/bracket history.

## Baseline membership and statistics

User estimates approximately one pump-down/hour as an upper operational rate.
Cycle summaries and reference calculations are therefore small; first-5 and
recent-20 histories correspond to at least several hours and roughly a day at
that maximum rate, and may span much longer during ordinary operation. Use cycle
counts rather than an assumed daily rate. Frequent service restarts must preserve
reference membership and prior comparison results; a new physical window clears
its active reference population while retired-window history remains available.

Proposed defaults, awaiting commissioning: **first 5 eligible cycles** for the early
reference, **latest 20 prior eligible cycles** for the recent reference, minimum
**5** usable observations for a comparison. Publish mean, median, sample count and
spread (median absolute deviation is a useful future addition). Primary ratio
uses median; mean is also visible to satisfy average-based comparison needs.

Eligibility is completed, quality-valid and same window / normal setup /
timing-definition epoch. Matching includes pressure source, thresholds, crossing
estimator and dwell policy; changing these changes the comparison definition.
Keep unusual cycles visible in history. A note alone does not exclude a cycle:
exclusion requires an explicit reason and audit event. **Do not automatically
discard slow cycles as outliers**, since those are the signal of interest.

Freeze early cycle IDs once N eligible cycles establish that reference. Show
“collecting reference: n/N” before that, rather than calling a partial reference
established. Recent history rolls forward and can drift with degradation; the
fixed early reference preserves visibility of that drift. New windows get new
references. A deliberate maintenance/reconfiguration baseline revision retains
the old reference and records its reason; no automatic rebaseline on slowdown.

Freeze comparison membership at pump-start. Compare the new cycle against **prior
cycles only**, and save the reference IDs/statistics used with the result. Admit
the cycle to future recent history only after completion/comparison. This avoids
allowing a slow pump-down to raise its own reference. The last-cycle comparison
must not change as future cycles or reference revisions arrive.

Missing or unresolved milestone values are omitted only from that metric's
statistics, with a per-metric count/quality shown. Keep the same frozen early
cycle membership across milestones; do not silently substitute later cycles for
missing early milestones. Aborted/incomplete cycles are not successful duration
samples; show their count and partial curves to avoid hiding failure to complete.

## Current versus most recent cycle

For a completed metric duration d and baseline statistic b:

```
ratio = d / b
percent_change = 100 * (ratio - 1)
delta_s = d - b
```

Show `1.50× / +50% / +120 s` with baseline count and identity. Insufficient history,
zero/unresolved baseline, and invalid current data produce **N/A + reason**, not
zero, infinity or a green “normal” indicator.

While pumping:

- Display elapsed time, current pressure, reached milestones and next target.
- Reached milestones have final observed crossing-time comparisons.
- For an unreached milestone, display **“elapsed so far / historical time to
  this milestone”**, explicitly unfinished. Once its expected duration has passed,
  wording can be “not yet reached; elapsed exceeds early median by 35 s.”
- Compare total elapsed with historical total similarly. It is not an estimated
  final duration and not proof that the cycle is fast when the ratio is below one.
- If inputs become unknown, mark the attempt interrupted/quality-limited; never
  continue an apparently healthy live ratio through a data gap.

Retain last completed-cycle results alongside the current attempt. A current
attempt must never overwrite “last completed” until it actually completes.

## Suggested server/display contract

Use server-calculated statistics so BOY does not query SQLite or implement
baseline logic. See DISPLAY.md for widget layout. Prefix TBD; names illustrative.

| Group | Proposed read-only values |
| --- | --- |
| Attempt | Current ID/state, elapsed seconds, next milestone, quality, start UTC |
| Last | Last completed ID/start/end, total duration and saved reference IDs |
| Each of M100, M10, M1, M0p1, Total | Current reached flag/time, last time, early/recent mean/median/count, last ratio/delta, current elapsed ratio with unfinished flag, quality/reason |
| Reference | Early state/ID/member count, recent snapshot ID/count, comparison-definition ID |
| Stages | Last stage duration and early/recent statistics, with unresolved-stage quality |
| History | Bounded aligned arrays of cycle index or UTC and total duration; separate excluded/incomplete markers |
| Curves | Bounded elapsed-time and pressure arrays for current and last; count, cycle ID and generation |

Baseline mean/median **pressure curves** are optional later work; pressure-versus-time
alignment and incomplete curves need more care than scalar milestone statistics.
Initially overlay current and last pressure curves, with early/recent median
milestone points, and plot total pump duration by cycle/date with baseline lines.

Production persistence additions: milestone child records keyed by (attempt ID,
threshold), comparison-reference membership/revisions, per-result reference snapshots,
notes and explicit exclusion events. Unique keys make replay idempotent. Milestones
and current progress must recover or be labeled interrupted under the existing
session restart policy.
