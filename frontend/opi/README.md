# BOY screens

- `window_overview.opi`: SQLite-backed beamtime app overview.
- `commissioning_overview.opi`: input diagnostics and closed-window watch.
- `beamline_schematic.opi`: right-to-left beamline layout, chamber pressures,
  moving valve symbols, qualitative Kapton bow and beam/energy/intensity display.
- `pv_manifest.json`: read-only output PV suffixes and default facility-style prefix.

Use `P=XF:12IDC-ES{KaptonMon:1}`. These files are generated; see
[frontend guide](../README.md) and [beamtime runbook](../../docs/BEAMTIME.md).
All served outputs are local-only; input PV names live exclusively in the backend.
