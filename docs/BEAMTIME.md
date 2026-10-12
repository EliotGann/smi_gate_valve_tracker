# Local KaptonMon beamtime app

The proposed service name is **KaptonMon**, prefix **`XF:12IDC-ES{KaptonMon:1}`**.
This follows the supplied facility-style device/field naming; site approval of
the precise name is pending. No trailing colon is added after `}`.

Examples (all read-only):

```
XF:12IDC-ES{KaptonMon:1}Pressure:Downstream-I
XF:12IDC-ES{KaptonMon:1}Pressure:Sample-I
XF:12IDC-ES{KaptonMon:1}Valve:Pos:State-Sts
XF:12IDC-ES{KaptonMon:1}Pump:Count-I
XF:12IDC-ES{KaptonMon:1}VacWatch:Rate-I
XF:12IDC-ES{KaptonMon:1}Storage:State-Sts
```

`frontend/opi/pv_manifest.json` is the complete contract. The old
`SMI:WINDOW:COMM:Input:*` names are retired. Reopen the matching displays; remove
old `P` overrides. The full app and diagnostic observer use the same names, so
stop the old observer before starting the beamtime app.

## First start (from softioc/)

Select a local, persistent filesystem (not a network share) with room for the
beamtime journal. Substitute the real window/beamtime identity below. The name
identifies observation history; it does not reconstruct pre-tracking exposure.

```bash
pixi install --locked -e caproto
mkdir -p "$HOME/kapton-monitor-beamtime"
pixi run -e caproto smi-kapton-monitor \
  --config config/commissioning.toml \
  --database "$HOME/kapton-monitor-beamtime/history.sqlite" \
  --window-id "beamtime-window-001" --init
```

`--init` creates new history and refuses to overwrite an existing database.
On every subsequent start use **the same command without `--init`**. A missing
database is an error rather than a silent statistics reset. The config contents
and window ID must match; archive changes as a new explicit recording database
until configuration-epoch migrations are implemented. One writer per database
is enforced by a file lock. Do not delete the database to fix a startup error.

If an earlier version failed at startup with `KeyError: 'KaptonMon'`, update to
the brace-handling fix and restart **without `--init`**: initialization already
created the database before that failure. Keep the ordinary single braces in
the prefix and BOY macro. The adapter now escapes them internally for caproto's
Python-format macro expansion; the actual CA names keep single braces.

The launcher always binds CA server TCP/UDP to **127.0.0.1** and forces loopback
beacons. No flags enable external serving. Input discovery retains the shell's
existing `EPICS_CA_*` settings so the app can read the real beamline PVs.
The network will still see input CA searches/reads/subscriptions; only the
monitor's output service is local. No source PV write API is used.

If loopback beacon sends get `ConnectionRefusedError`, run
`pixi run -e caproto caproto-repeater` in another terminal. An already-running
repeater is sufficient. No manual beacon exports are needed by this launcher.

## BOY 4.6.1

Open **`frontend/opi/window_overview.opi`** in BOY Runtime on the same host as
the backend. Default macro: `P=XF:12IDC-ES{KaptonMon:1}`. Add `127.0.0.1` to BOY's
CA address list (preserve beamline entries). The **Input diagnostics** button
opens the commissioning OPI; it has a return button. The overview is 1680×1190;
use scroll/zoom on smaller screens. Macro inheritance is enabled.

The overview contains identity/session/storage health, durable sequence and
commit time, opens/closes, closures reaching vacuum, full pump cycles,
interrupted attempts, current/last pump duration, last milestones, early/recent
medians and counts, shutter-only timers, closed-pumped timer, pressure integral,
unknown-coverage times, live pressure/valve states and the closed-window watch.
Recent durations are a server-supplied text summary; raw curves are in SQLite.
Historical plots, maintenance/window replacement and a history browser remain
separate future screens rather than nonfunctional buttons.

## Recording and interpretation

### Reduced history (`changes-v1`)

All observations still reach live calculations, liveness checks and displays.
Only historical storage is filtered:

- Valve/shutters/ring mode: every value, alarm/status or connection change,
  baseline, receipt gap (>5 s), and one unchanged anchor per minute.
- Both pressures and Bragg: every numeric change plus the same quality boundaries
  and minute anchors. No pressure deadband or state-only coalescing is applied.
- Ring current: one sample per minute plus zero/nonzero and quality transitions.
  These are periodic samples, not averages. Ring gating remains unconfigured.
- Unused BPM3: baseline/quality/gap records only; no routine value history.
- Source timestamp churn and numeric text formatting alone do not create rows.
- Recovery checkpoints still update approximately twice per second in one
  replaceable row. Historical snapshots are minute-spaced, with additional
  pump/state/quality boundaries and shutdown. Slope-sign chatter is not a boundary.

`Storage:Seq-I` counts **commits**, not snapshot rows. Its value and totals are
checkpointed atomically even when no historical snapshot is inserted. Sparse
history is not an exhaustive receipt stream: do not interpret intervals between
retained rows as acquisition gaps or replay them using the live 5 s expiry rule.
Use explicit quality/gap events, minute anchors and checkpoint coverage.

The main OPI's bottom panel shows received/retained/skipped observation counts
for this process session; total database event/snapshot rows; and database + WAL
size in MiB. Session counters reset on restart, unlike lifetime totals. The restart
marker is an extra event, so session retained count is not exactly the row increment.

With the backend stopped, compact old history using:

```bash
pixi run python -m smi_window_tracker.compact \
  "$HOME/kapton-monitor-beamtime/history.sqlite" --replace
```

The tool takes the recorder lock, streams selected history to a new file, checks
integrity and identity/sessions/cycles/checkpoint preservation, then atomically
replaces the original. Redundant history is discarded to save space. Original
selected IDs/timestamps and final session observations are retained. Before/after
counts go in `compaction_audit`. Temporary space is required for the compact copy.
Restart normally **without `--init`**. Input configuration and its hash are unchanged.

### Calculation and durability details

- Every retained observation/disconnect is journaled with
  source timestamp, receipt UTC/monotonic time, raw value/text, status and severity.
  Both pressure traces, shutter edges and valve changes can be inspected later.
- Finite numeric strings such as WAXS `8.1E+02` are parsed as 810 mbar while
  preserving their original text. `Lo`, malformed text and nonfinite numbers
  remain unknown; `0E0` retains its under-range meaning. Restart after this parser
  correction with the same database/config (without `--init`). Previously recorded
  unknown coverage is preserved rather than silently recalculated.
- A serialized reducer integrates at received edges, with 5 s input freshness,
  metric-specific unknown coverage and no integration across large scheduler gaps.
  Pressure observations/health reads qualify dwell; display ticks do not replay
  stale pressure to qualify vacuum. Timing is receipt-based, not source-clock corrected.
- Counters use the tested >700 → <=700 → <500/120 s → <0.01/5 s sequence,
  plus independent observed closures reaching vacuum. Positive pressures only:
  under-range zero remains unknown until the gauge's reporting bound is supplied.
  This can prevent cycle completion while the gauge reports zero; it is visible
  in unknown coverage and the input state column.
- Closed-pumped time starts at confirmation. Closed-window load proxy integrates
  `abs(TCG9 - TCG7)` in mbar s. The closed-window watch is also snapshotted, so
  the both-pumped → close → vent-WAXS case is recorded independently of pump cycles.
- Beam timers here are **shutter-only observed eligibility**, including the
  window-closed restriction where labeled. Ring-mode/current policy is not yet
  configured. BPM is unused. Attenuation, photons/J, material lifetime and loaded
  threshold-time remain explicitly incomplete rather than fabricated metrics.
- Early summary retains first 5 completed durations; recent retains last 20.
  These include the latest completed cycle, are descriptive summaries (not a
  prior-only slowdown comparison), and show counts while collecting.
- Pending events are capped at 4096; overload stops the app rather than silently
  discarding edges. SQLite work runs outside the CA event loop in one serial worker.
  The worker commits approximately every 0.5 s, with completion-triggered wakeup.
  This cadence is not a measured power-loss guarantee under arbitrary I/O load.
  Check storage age/sequence and disk growth during beamtime.
- A transaction saves selected events, cycles, optional snapshot and checkpoint before
  publishing durable totals; live input/watch readbacks can be newer. `Storage:Seq-I`
  is published last. Separate CA scalar updates are not an atomic screen snapshot.
  SQLite uses WAL and synchronous=FULL. New history uses the selection policy
  above; existing history is reduced only by the explicit compaction command.
- Restart restores committed totals/history, records a session gap, interrupts an
  active attempt and reacquires baselines. It never counts downtime or hidden
  transitions as known time. Window changes currently require a separate database;
  the planned audited installation workflow is not part of this beamtime launcher.

## Inspect and back up recording

SQLite tables: `identity`, `sessions`, `events`, `cycles`, `snapshots`, `checkpoint`.
JSON payloads retain raw values (including NaN for unknown). IDs are monotonic
SQLite row IDs; cycles and raw receipt monotonic times are associated with sessions.
For example, with the SQLite command-line client:

```bash
sqlite3 "$HOME/kapton-monitor-beamtime/history.sqlite" \
  'SELECT name,count(*) FROM events GROUP BY name;'
sqlite3 "$HOME/kapton-monitor-beamtime/history.sqlite" \
  'SELECT id,session,payload FROM cycles ORDER BY id DESC LIMIT 10;'
sqlite3 "$HOME/kapton-monitor-beamtime/history.sqlite" \
  ".backup '$HOME/kapton-monitor-beamtime/backup.sqlite'"
```

Use SQLite's backup operation instead of copying only the main file while WAL
is active. Stop with Ctrl-C to flush accepted data. Restart and verify totals and
last-cycle values persist. Raw monitor volume depends on source rates; check file
growth and available disk space during the beamtime debug run.

## Verification

`pixi run check` includes backend tests and generated BOY/manifest checks.
`pixi run -e caproto pytest tests/test_commissioning_ca.py` uses a synthetic CA
source, exercises the full SQLite-backed IOC on loopback, verifies all served
PVs are read-only, and checks journal/snapshots after shutdown. Reducer tests
cover short shutter intervals, pump completion, expiry, restart and transactional
rollback. This is a local beamtime implementation, not completed service/soak,
material calibration, maintenance UI or facility naming acceptance.
