# Beamtime operation and interpretation

For server installation and network/local launch commands, use
**[DEPLOYMENT.md](DEPLOYMENT.md)**. For database files, paths, logs and window
records, use **[STORAGE.md](STORAGE.md)**. This guide describes observed metrics.

## Operator views

Default: `frontend/opi/window_overview.opi` (schematic). It links to
`window_details.opi`, `commissioning_overview.opi` and `change_window.opi`.
Macro: `P=XF:12IDC-ES{KaptonMon:1}`, no trailing colon. State and read/change ages
are calculated by the server; GUI scripts only render state or transport complete
window-change requests. Remote clients do not need database filesystem access.

## Timing and measurement definitions

- TCG:9 is downstream pump pressure; TCG:7 is WAXS sample pressure, both mbar.
  Differential loading proxy integrates their absolute difference while GV6W is
  closed. Zero under-range is unknown until its actual bound is established.
- Numeric strings such as `8.1E+02` parse as 810, with original text retained.
- Live pump definition **v3**: observe >700; start at <600; confirm <500 within
  120 s; finish on first <0.01 observation that subsequently qualifies a 5 s dwell.
  Pumped latch exits above 0.02. Vented display range includes 600–700; procedure
  vent confirmation sets >700 and clears <600.
- Opens/closes are observed transitions, not reconstructed events during downtime.
  Closing into qualified vacuum can count a closure reaching vacuum without a
  complete pump-down. Invalid data/gaps interrupt qualification.
- Closed-pumped integration starts at confirmation, not backdated to the crossing.
  Human-readable totals use `days h:mm:ss`; numeric seconds remain available.
- Beam timers are **shutter-only eligibility**. The window timer also requires
  GV6W closed. Ring policy is unconfigured, BPM3 unused for gating, and photon/J
  models are incomplete. These are not calibrated exposure/dose measurements.
- Duration summaries retain first 5/latest 20 completed cycles, including the
  latest result. Counts identify collecting references. `Pump:PathHistory-I`
  separates operating paths. On upgrade from v2 timing, old cycles remain but
  new early/recent populations start fresh instead of mixing definitions.
- [PROCEDURES.md](PROCEDURES.md) defines vacuum-first/manual-pump classification,
  isolated hold and detector-valve warnings. Watch rate is a pressure slope,
  not gas throughput or proof a window caused a leak.

## `changes-v1` historical recording

Every accepted observation still reaches live reduction and liveness logic.
Only historical persistence is filtered:

| Input | Retention |
| --- | --- |
| Valve/shutters/ring mode | Every value/quality/connection change, baseline, receipt gap, minute anchor |
| Both pressures / Bragg | Every numeric change and same boundaries; no pressure deadband |
| Ring current | Minute sample plus zero/nonzero and quality transitions |
| BPM3 | Baseline/quality/gap records only; live readout continues |
| Procedure | Phase/warning transitions rather than every timer increment |
| Historical snapshots | Approximately once/minute, important boundaries and shutdown |
| Recovery checkpoint | Approximately twice/second, overwriting one row |

Source timestamp churn or numeric formatting alone does not trigger persistence.
Retained events contain receipt UTC/monotonic time, source timestamp, value/text,
source status/severity and selection reason. Quiet anchors are not the input rate;
sparse history cannot be replayed with the live five-second expiry rule to
reconstruct liveness. Preserve recorded coverage and gap records.

`Storage:Seq-I` counts commits, not snapshot rows; it is published after durable
totals. A transaction includes selected events/cycles, optional snapshot and
checkpoint. Separate CA updates are not atomic snapshots. SQLite uses DELETE
journal and FULL sync; cadence is not a measured power-loss latency guarantee
under arbitrary NFS/I/O conditions.

The OPI shows received/retained/skipped observations for this process session,
database total rows, and database + journal size. Session counters reset on restart;
physics totals persist. Restart/procedure markers are extra history rows.

## Restart and maintenance

Startup restores the active window and committed totals, opens a new session,
identifies the gap and reacquires baselines. No hidden activity or hold time is
inferred across restart. `--init` is never a recovery tool.

Use the OPI's confirmed new-window workflow for a physical replacement; history
is retained and new active totals start fresh in the same database. See
[WINDOW_LIFECYCLE.md](WINDOW_LIFECYCLE.md). Unknown legacy installation dates
remain unknown. No automatic history deletion is performed.

Use SQLite backup APIs and the explicit offline compactor described in STORAGE.md.
The first 19-day soak/compaction results are in
[BEAMTIME_DEBRIEF_2026-10-12.md](BEAMTIME_DEBRIEF_2026-10-12.md); its WAL references
describe that historical run, not the current deployed journal mode.
