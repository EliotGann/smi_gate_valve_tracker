# BOY screens

- `window_overview.opi`: SQLite-backed beamtime app overview.
- `commissioning_overview.opi`: input diagnostics and closed-window watch.
- `beamline_schematic.opi`: right-to-left beamline layout, chamber pressures,
  moving valve symbols, qualitative Kapton bow and beam/energy/intensity display.
- `pv_manifest.json`: read-only output PV suffixes and default facility-style prefix.

Use `P=XF:12IDC-ES{KaptonMon:1}`. These files are generated; see
[frontend guide](../README.md) and [beamtime runbook](../../docs/BEAMTIME.md).
Output serving is selected by backend `--mode softioc` or `--mode local`.
Input PV names live exclusively in the backend. The default overview is visual;
`window_details.opi` retains the detailed table view and `change_window.opi`
implements the confirmed tracker-history maintenance command.
