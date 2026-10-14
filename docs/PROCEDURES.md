# Two-path procedure monitor

The downstream detector-isolation PV is
`XF:12IDC-VA:2{Det:1M-GV:7}Pos-Sts`. Read-only CA inspection found enum codes
**0 = Not Open, 1 = Open**, with 0 observed while the operator confirmed closed.
Use the operator-approved assumed-closed interpretation for 0. MINOR/STATE is
reported separately and does not by itself invalidate this status.

## Agreed limits

- Downstream opening pressure: **strictly below 0.009 mbar**. At equality or above,
  opening is a procedural alarm; this is distinct from the original pump-cycle
  qualification threshold of <0.01 mbar for 5 seconds.
- WAXS fully vented: **strictly above 700 mbar**, no additional dwell requested.
  Once confirmed, vented status latches until **below 600 mbar** to tolerate gauge drift.
- Vacuum-first minimum isolated observation: **300 seconds**, configurable as
  `[procedure] hold_seconds` in `config/commissioning.toml`.
- Rate of rise remains informational. There is no expected-rate limit or learned
  reference yet. Pressure >=0.009 mbar supplies the warning for now.

## Classification at an observed GV6W closure

Fresh positive pressures below 0.009 on both sides select **vacuum-first**.
Both above 700 select **manual-pump**. Other conditions, startup already closed,
or a lost closure edge select **unclassified** rather than guessing a path.
This is an instantaneous classification; it is not certification of stable vacuum.

The operator intends GV7 closed before GV6W closes. GV7 open at closure produces
a latched warning; missing/invalid/stale GV7 data produces an unverified-sequence
warning. The software is read-only and neither implements nor replaces a hardware
permissive. Manual turbo isolation/pump state is not observed.

### Vacuum-first

Both sides initially pumped → GV7 closed → close GV6W → vent WAXS above 700.
Start the hold while GV6W and GV7 remain closed, WAXS >700 and TCG:9 <0.009.
Continue observing after 300 s; display **Minimum hold met; continue observing**,
not “safe” or “permitted.” Opening GV7 before this continuous hold completes is
a procedural warning. Opening ends the isolated rate watch; re-isolation requires
a new hold. Source loss/invalid data, under-range zero, upstream <600, or downstream
>=0.009 resets the current hold rather than granting unobserved time.

### Manual-pump

Both sections vented → GV7 closed → close GV6W → manually pump TCG:9.
Atmospheric pressure is expected initially, not a pressure-rise alarm. Once TCG:9
has been below 0.009, a return to/above it raises a warning. The five-minute
vacuum-first hold is not imposed on this alternative path. Pressure-based pump
milestones still use the existing 700/500 qualification and <0.01/5 s completion.
GV7 opening is checked against <0.009 independently of pump completion.

## Alarms and records

Warnings latch through the closure episode and remain visible in its final result
after GV6W reopens. A new closure starts a new episode; old warnings remain in
SQLite. There is no reset/acknowledge write PV. `Procedure:Alarm-Sts` carries native
CA MAJOR severity for latched warnings and INVALID for current required-input
loss. The OPI shows the alarm text and standard BOY alarm indication.

Sparse `procedure` event records contain classification, threshold definitions,
initial pressures, vent/hold/open timestamps, observed hold, peak downstream
pressure, pressure change and latched warnings. The checkpoint records the current
episode and last result. Restart interrupts an active procedure and starts from
new observations, never restoring elapsed hold credit.

Pump cycle payloads now carry `operating_path`; `Pump:PathHistory-I` reports bounded
recent per-path duration statistics (20 each). Existing generic early/recent
summaries still aggregate completed cycles; old records are not retroactively
classified. Vacuum-first characterization lives in the isolated pressure trace
and procedure records, not in a fabricated pump-down duration.

## Update an existing beamtime database

Adding GV7 changes the configured inputs. Stop the old backend, then explicitly
record the configuration change while preserving totals:

```bash
pixi run -e caproto smi-kapton-monitor --mode local \
  --config config/commissioning.toml \
  --database "$HOME/kapton-monitor-beamtime/history.sqlite" \
  --window-id "beamtime-window-001" --accept-config-change
```

Do **not** use `--init`. The update stores old/new configuration contents in
`config_epochs`. Subsequent identical starts do not require the extra flag.
Reload both OPI files: GV7 appears in diagnostics and on the overview; procedure
phase, timer, pressure limit and warning text are at the bottom of the overview.
Input history retention remains `changes-v1`; procedure transitions force a
snapshot, not every timer increment. Nothing writes to the source PVs.

For network deployment use `--mode softioc` with interface/beacon options from
DEPLOYMENT.md and the deployment database path instead of this local example.
