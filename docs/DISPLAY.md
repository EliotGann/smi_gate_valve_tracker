# CS-Studio BOY screen plan (frontend component)

Current commissioning screen: `frontend/opi/commissioning_overview.opi`, targeting
CS-Studio 4.6.1. Pump-down pressure is TCG:9; sample pressure is WAXS TCG:7, both
mbar. SumX is labeled unused diagnostic: beam inference and BPM-qualified hours
in the future wireframe below are disabled pending calibration.

## Platform and ownership

Target **legacy Eclipse CS-Studio BOY `.opi`**, confirmed by the user. Build the
display alongside the IOC under `frontend/`, isolated from `softioc/` and ready
for optional later extraction into its own repository. Shared `docs/` owns the
metric semantics and interface specification. Only a frontend scaffold exists;
`.opi` screens remain planned work.

Suggested future structure within `frontend/`:

```
opi/window_overview.opi
opi/pump_history.opi
opi/input_diagnostics.opi
opi/model_details.opi
opi/window_history.opi
opi/new_window.opi
assets/
docs/README.md
tests/                 # XML/macro/PV-contract checks and screenshot fixtures
```

Use `$(P)` for the tracker IOC prefix; optional `$(TITLE)` and an agreed history
export link macro. Record supported BOY version and IOC contract version. Keep
beamline input names/configuration in the server, rather than duplicating PV
polarity or flux calculations in display scripts. The display should work from
published tracker PVs and not require access to the IOC database filesystem.

## Overview wireframe

Resolution is adjustable. Use 1280×900 as a wireframe reference, with grouped
panels and expandable detail views; test BOY resize/scaling behavior rather than
assuming browser-like responsive layout.

```
+----------------------------------------------------------------------------+
| SMI Kapton Window   Window/lot ID   Installed date   IOC heartbeat / quality |
| Valve: CLOSED   P: 0.003 mbar   dP: ...   Pump: COMPLETE   Last update: ... |
+----------------------+-----------------------------------------------------+
| LIFETIME             | PUMP PERFORMANCE                                    |
| Opens / closes       | Current: PUMPING / elapsed 02:13 / next <0.1 mbar   |
| Closures pumped      | Last completed: 04:12   cycle ID / date             |
| Full pump cycles     | Early median: 02:48 (n=5)  Recent median: 03:15     |
| Closed+pumped hours  | Last / early: 1.50x (+50%)   Last / recent: 1.29x   |
| Loaded hours         | Reference: ESTABLISHED / collecting n/N / N/A      |
| Pressure-time        +-----------------------------------------------------+
| Beam-path hours      | Threshold | Current | Last | Early avg/med | Recent |
| Window-beam hours    | <100 mbar | ...     | ...  | ...           | ...    |
| BPM-qualified hours  | <10 mbar  | ...     | ...  | ...           | ...    |
| Upper-bound photons  | <1 mbar   | ...     | ...  | ...           | ...    |
| Interaction est. J   | <0.1 mbar | ...     | ...  | ...           | ...    |
| Model/coverage       | <0.01     | ...     | ...  | ...           | ...    |
+----------------------+-----------------------------------------------------+
| PRESSURE vs ELAPSED (log pressure) | TOTAL PUMP TIME vs CYCLE / DATE        |
| Current / last curves             | Completed points; early/recent lines  |
| Historical milestone markers      | Incomplete/excluded markers           |
+-----------------------------------+----------------------------------------+
| Ring | FE | photon | fast | BPM3 present | energy keV | attenuation T        |
| [Pump history] [Input diagnostics] [Model details] [History export/help]     |
+----------------------------------------------------------------------------+
```

The mock numeric values are examples, not limits or operational recommendations.
Pump performance gets the largest area because increasing duration is a key
inspection signal. A full-screen history view expands milestone/stage comparisons,
curves, cycle metadata and notes without crowding the overview.

## Widget and interaction mapping

- BOY Label/Text Update widgets for metrics, units, date/time and explanatory text.
  Display times as minutes/hours for readability while IOC values remain seconds.
  Formatting does not change calculation semantics.
- LED/state indicators with adjacent text for ring/shutters/valve and health.
  Known closed, moving, unknown and disconnected states must be distinct. Do not
  rely on color alone. An open shutter is an informational state, not an alarm.
- Fixed five-row milestone grid using scalar read-only PVs. Columns for current
  reached/time, last time, early/recent means and medians; ratios and sample counts
  available in the expanded view. Each row has validity/reason text.
- XY Graph (verify installed BOY support) for elapsed seconds versus log pressure,
  and cycle/date versus duration. Use server-supplied bounded arrays so data survive
  screen closure/reopening; a locally accumulated Strip Chart is not durable history.
- Action Buttons to open related `.opi` files with propagated macros. History
  export opens an agreed external service/link or documented export workflow;
  no assumed web service exists yet.
- No automatic baseline reset, device actuation or counter edits on the overview.
  Notes/exclusion/rebaseline workflows belong to a separately specified audited
  maintenance interface; initial history can display read-only notes from the server.

## Display semantics

1. **Early and recent are always labeled separately.** Show mean and median,
   counts, reference ID/state and comparison-definition ID. A rolling mean alone
   could conceal gradual deterioration.
2. **Current is not last completed.** During a run, show elapsed-so-far and reached
   milestones. Unreached targets say “not yet reached.” A live ratio is labeled
   “elapsed / historical duration,” never a predicted final pump time.
   A pending 700 crossing says “candidate: waiting for <500 mbar within 120 s,”
   not “pumping.” Vacuum qualification says “below target, confirming 5 s dwell.”
   Show raw pressure and pumped latch separately: a latched 0.015 mbar reading
   is expected. Timed-out candidates disappear without filling pump-history tables.
3. **Ratios first, no slowdown alarm initially.** Show numeric changes without
   arbitrary red/yellow thresholds. Text may state “elapsed exceeds early median.”
   Reserve alarm styling for actual input/storage/data-quality faults. Avoid a
   computed “Kapton healthy/failed” badge from pump duration alone.
4. **N/A is not zero.** Missing reference, interrupted attempt, disconnected PV,
   unresolved time and stale data have explicit labels. Show n/N while collecting
   the early reference. Preserve last valid results with a stale indication.
5. **Exposure model is visible.** Label photons and joules “nominal upper-bound
   estimate”; show 1e13 photons/s reference, attenuation, model ID and valid/unknown
   coverage. Until thickness/coefficients exist, interaction says “model incomplete.”
6. Beam status follows the confirmed physical order. BPM3 is before the fast
   shutter: a lit BPM indicator with the fast shutter closed is expected. The
   BPM threshold does not suppress the upper-bound exposure counter.

## IOC/display interface and array publication

### Window history and deliberate replacement

Add a “Window history” navigation button with current/last-retired summary cards
and a paginated retired-window table. Show ID/dates, reason for removal, pump and
mechanical cycles, load/beam hours, upper-bound photons/J and nominal Gy when
available, with model and coverage. Group average/median service-to-removal values
by removal reason and compatible model. The in-service window is shown separately
and excluded from completed-lifetime means. Missing dose reads N/A, not zero.

Place “Install new window…” on a maintenance/detail screen, not beside routine
readouts. The screen shows old totals and proposed new ID/material parameters,
requires a removal reason and operator label, then offers **Arm**. Only after the
server returns a proposal/token does it show the 60 s countdown and an empty
“Type current window ID” field plus **Retire OLD and start NEW**. Provide Cancel.
Fields bound to the proposal become read-only after arm; editing requires rearm.
Success is displayed only from the durable server receipt. Expiry, restart,
disconnect, wrong confirmation or stale current identity clears/disables the action.

Implement the server protocol in WINDOW_LIFECYCLE.md, not shared staging fields
plus an unqualified Confirm bit. The pending token is not a saved screen preference
and must never be auto-restored or auto-confirmed on reconnect. Test double-clicks,
two simultaneous screens and a lost commit response. This workflow changes tracker
history only; it does not actuate beamline hardware.

### Read-only summaries and plot transport

Scalar groups are specified in DESIGN.md and PUMP_TRENDS.md. Add `ContractVersion`
and display-compatible string lengths/units. Use a versioned machine-readable PV
manifest when the IOC is implemented; the display repo tests its PV references
against it. Baseline statistics and ratios are calculated by the server.

Proposed array budget: at most **512 points per pressure trace** and **200 recent
cycle results** on the overview; configurable after testing. Publish point count,
cycle ID, quality and generation with each aligned x/y set. A 512-element double
array is 4096 bytes, but verify complete CA payloads and site array-size settings.
Unused tail values must be masked/ignored, not plotted as zero pressure. For log
axes, zero or invalid gauge values are masked and retained as quality markers in
history, never silently replaced with invented positive pressure.

CA multi-PV updates are not atomic. Define generation/commit sequencing: mark a
plot update in progress, write matching arrays/count/ID, then publish completed
generation. Prototype a minimal BOY script or supported freeze/update mechanism
that only redraws a consistent completed set; do not claim the generic XY widget
automatically makes separate PVs coherent. GUI scripts only manage presentation,
not statistics. If the installed BOY version cannot achieve this, use a packed
single-waveform snapshot plus a tested adapter rather than mixed-generation plots.

Refresh scalar live elapsed/status and current plot at approximately 1 Hz; historical
summaries/arrays update on completion, selection or reference changes. This is
independent of faster acquisition and fast-shutter edge processing. History selection
mechanism (read-only service versus explicit selector PV) remains a later interface
decision; initial overview needs only current/last and a bounded recent history.

## Development and acceptance alongside the IOC

1. Publish the PV manifest and fake-data fixtures from the server project.
2. Build the BOY overview against a simulated CA server in the frontend component.
3. Exercise startup/no history, reference collecting, normal/slow pump, stalled
   attempt, interruption, window replacement, missing model and data disconnect.
4. Check all macros resolve, units/enum labels match, string lengths fit, and
   out-of-range/nonfinite/unknown values render as explicit missing states.
5. Test consistent curve generations, log-axis behavior, bounded waveform sizes,
   retained history after screen restart and navigation macro propagation.
6. Review screenshots with operators; test on the actual installed BOY runtime.
7. Release IOC and display versions with an explicit compatibility table. Keep
   the display independent of a running Bluesky session and local IOC files.
8. Exercise arm/expiry/cancel/typed-ID/new-window success/failure with two screens,
   and verify old history survives while the new current view resets only on commit.
