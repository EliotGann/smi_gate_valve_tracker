# CS-Studio BOY frontend (4.6.1)

Open **`opi/window_overview.opi`** for the local beamtime recorder. The default
macro is **`P=XF:12IDC-ES{KaptonMon:1}`**, without a trailing colon. Remove any
old `SMI:WINDOW:COMM:` overrides. Start/restart instructions and model limitations
are in [BEAMTIME.md](../docs/BEAMTIME.md).

The main display includes stored counters, qualified pump status, last milestones,
early/recent summaries, timers and unknown coverage, pressure integral, recording
health and the live closed-window vacuum watch. The **Input diagnostics** button
opens `commissioning_overview.opi`; it includes raw values and friendly states.
Both screens are 1680×1190. Use scroll/zoom as needed.

The backend serves only loopback: run BOY on the same workstation, with
`127.0.0.1` included in BOY's CA address list. Titles and static labels must render
even without the IOC. Reload both backend and displays after contract changes.

Debug rows show **Last read** (successful monitor/health-read receipt) and **Last
observed value change**, both timed by the backend's monotonic clock. Repeated
values refresh only Last read. “Just now” persists for five seconds. On startup,
reconnect, invalid alarm or a freshness gap, change tracking starts a new baseline
rather than inventing a transition. These diagnostic ages are session-local;
the raw event journal retains receipt and source timestamps for historical analysis.

Source times still appear below the receipt/change ages as
`56 minutes ago | 2026-09-23 10:00:00 UTC`. Dates in/before the 1990 EPICS epoch
are labeled **Suspect IOC time**, with the original date preserved. Missing and
future source times are explicitly labeled. Neither an old source timestamp nor
a recent read proves the hardware itself is updating. Numeric `:SourceTime-I`,
`:ReadTime-I` and `:ChangeTime-I` remain available; zero change time means no
observed change in the current valid segment.
If entirely blank, check BOY's Error Log (Window → Show View → Other → General).

Legacy BOY `typeId`, font and String waveform conventions are used; all buttons
only navigate between displays. There are no source writes or writable controls.
Actual workstation layout/navigation acceptance remains part of commissioning.

## Maintain and test

`opi/pv_manifest.json` is generated from `softioc/src/smi_window_tracker/contract.py`.
The display source is `softioc/src/smi_window_tracker/display.py`:

```bash
pixi run --manifest-path softioc/pixi.toml python -m smi_window_tracker.display frontend/opi
pixi run --manifest-path softioc/pixi.toml pytest frontend/tests
```

Tests check regenerated files, legacy widget IDs, dimensions, navigation targets
and every PV reference against the contract. Historical plots, a database browser,
and the future audited window-replacement UI remain unimplemented.
