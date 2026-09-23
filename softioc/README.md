# KaptonMon application

The local beamtime app reads the beamline PVs, records raw events and calculated
totals in SQLite, and serves read-only facility-style PVs on loopback only.
The service name/prefix is provisional pending facility confirmation:
`XF:12IDC-ES{KaptonMon:1}`.

## Start the recorder

From `softioc/`:

```bash
pixi install --locked -e caproto
mkdir -p "$HOME/kapton-monitor-beamtime"
pixi run -e caproto smi-kapton-monitor \
  --config config/commissioning.toml \
  --database "$HOME/kapton-monitor-beamtime/history.sqlite" \
  --window-id "beamtime-window-001" --init
```

Choose the actual window/beamtime ID. **On restart omit `--init`**, retaining
the same config, database and ID. Stop the previous commissioning observer first.
The launcher binds server TCP/UDP and beacons to 127.0.0.1; it preserves existing
beamline input CA discovery. No source PV writes are performed. If no repeater
is available, run `pixi run -e caproto caproto-repeater` separately.

Open `frontend/opi/window_overview.opi` from the repository root in BOY Runtime.
The default macro is `P=XF:12IDC-ES{KaptonMon:1}`. Set BOY's CA address list to
include `127.0.0.1` on the backend host. Old `SMI:WINDOW:COMM:` names are retired.

See the complete [beamtime runbook](../docs/BEAMTIME.md) for metric semantics,
backup/inspection, local networking and limitations. Exposure/material models
and maintenance workflows remain incomplete; the screen states this explicitly.

## Diagnostic-only mode

```bash
pixi run -e caproto smi-window-commissioning --config config/commissioning.toml
```

This uses the same local-only output names but does not record to SQLite or serve
the main app totals. Use `frontend/opi/commissioning_overview.opi` for this mode.
Do not run both entry points concurrently under the same prefix.

## Development

```bash
pixi run check
pixi run -e caproto pytest tests/test_commissioning_ca.py
pixi run python -m smi_window_tracker.display ../frontend/opi
```

The default checks include offline domain, persistence/restart and generated
BOY/manifest checks. The optional caproto test exercises real synthetic CA sources
and the SQLite-backed app on loopback, without contacting beamline equipment.
Display generation is reproducible; edit `src/smi_window_tracker/display.py`
rather than hand-editing generated OPI files. Shared design documentation lives
under `../docs/`; supplied Bluesky modules are references, not runtime imports.
