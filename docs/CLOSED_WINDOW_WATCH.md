# Closed-window commissioning watch (observer contract v2)

## Operating sequence

An important sequence is: both TCG:9 downstream and WAXS TCG:7 sample chamber
are pumped down, GV6W closes, then the upstream sample chamber is vented slowly.
This is **not a new downstream pump-down**. The interesting diagnostic is whether
downstream pressure rises (vacuum worsens), how quickly, and how this relates to
upstream pressure. Upstream vent duration is not a pump-performance metric.

The commissioning observer now publishes `Input:<name>:State` and a read-only
`ClosedWatch:*` group. It remains live-only: these diagnostics are not persisted
and do not implement the lifetime counters or full pump reducer.

## State column

- GV6W: 1 → Open, 0 → Closed (assumed).
- FE/photon: 1 → Closed, 0 → Open (assumed).
- Fast shutter: 7 → Closed, 0 → Open. Other codes → Unknown code.
- Pressure: positive <0.01 mbar → Pumped down (raw <0.01); >700 → Atmosphere;
  intermediate → Above pump target. These are instantaneous ranges, not the
  five-second vacuum latch or proof a complete pump cycle occurred.
- Reported zero → Under range; negative/nonnumeric → Invalid/Unknown.
- Bragg → photon energy in keV over the configured design range 2.1–24 keV.
- SumX → Unused: no beam inference. Ring current/mode have no accepted gating
  policy and are explicitly labeled accordingly.

Disconnected, failed reads, INVALID alarms, and >5 s without a fresh received
sample/read override interpretations. Minor/major alarm codes are appended to
state text and remain available in the source severity column. Pressure-watch
numbers still use finite values with minor/major alarms; inspect severity too.

The CA client retains edge subscriptions and independently performs health reads
at roughly 1 s intervals (1 s timeout) for quiet PVs. A read is discarded if a
newer monitor or connection event arrived meanwhile. State/derived outputs refresh
at roughly 1 Hz. This establishes CA connectivity, not physical gauge acquisition
liveness: an IOC can answer reads while its hardware acquisition is stuck.

## Pressure watch semantics

The watch is enabled whenever GV6W is interpreted closed. It requires no prior
atmosphere observation, pump cycle, or automatic vent detection. It also starts
if the observer first connects with the valve already closed; in that case its
baseline is an **observation baseline**, not a claimed historical closure value.

| Suffix under `ClosedWatch:` | Meaning |
| --- | --- |
| `Status` | Collecting / Rising / Falling / Unchanged, or explicit missing-data reason |
| `Baseline` | First valid positive downstream pressure after closure/recovery, mbar |
| `Change` | Latest retained downstream pressure minus baseline, mbar (signed) |
| `Rate` | Signed endpoint slope over recent retained points, mbar/s |
| `Span` | Actual endpoint separation used for rate, seconds (up to 30) |
| `Elapsed` | Time from baseline to latest retained observation, seconds |
| `UpstreamChange` | WAXS change since its first valid reading in this segment, mbar |
| `DeltaP` | Absolute latest pressure difference between the two gauges, mbar |

Rate uses monotonic receipt time and at most one retained point per second, over
the last 30 seconds; storage is bounded to 61 points. At least one second of
data is needed. There is no arbitrary slowdown/leak alarm threshold or smoothing
claim. A positive slope means downstream pressure is rising, **not proof of a
Kapton leak**: pumping, valves, outgassing and gauge behavior can contribute.
It is not gas throughput in mbar L/s.

Opening, unknown valve state, invalid/stale downstream data or under-range zero
clears the segment. Recovery starts a fresh baseline and cannot bridge missing
data. Upstream loss leaves the downstream watch running, but upstream change
and differential pressure are unavailable; its recovered baseline is new.
`DeltaP` is a pressure difference, even when the valve is open, not a calculated
mechanical load. Latest source values are asynchronous, not an atomic gauge pair.

Zero is an under-range sentinel of unconfirmed bound. Exact baseline/change/rate
and differential pressure cannot be derived from it; numeric unavailable values
are NaN, with an explanatory status. Emergence from zero starts a new in-range
baseline rather than inventing a rise from physical zero. The main State column
still makes emergence visible. Establishing a bound could support future bounded
loading/rise estimates.

## Commissioning exercise

Close GV6W during normal operation with both sides pumped, then observe the usual
upstream vent. Confirm the watch starts without a downstream pump-down, WAXS
change rises, and downstream change/rate follow the independent vacuum screen.
Reopen/reclose and verify baseline reset. Check under-range and source-disconnect
states separately. No controls are provided on this screen.

Restart the observer and reload the matching v2 OPI after updating. The screen is
1680×950; the State column is to the right of the source timestamp column.
The existing CA beacon environment settings still apply. A later durable recorder
should retain both gauge traces, valve edges and data-quality breaks for offline
comparison of these closed-window vent episodes.
