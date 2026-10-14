# KaptonMon CS-Studio BOY frontend (4.6.1)

Open **`opi/window_overview.opi`** with macro **`P=XF:12IDC-ES{KaptonMon:1}`**.
This is the visual default: beam right-to-left through WAXS/sample → GV6W Kapton
→ intermediate TCG:9 → detector gate GV7 → Pilatus. The detector graphic is a
location label, not a detector-vacuum measurement.

## Connecting

- **Network IOC:** include the IOC server address (and search port if nonstandard)
  in BOY's CA address list. The display may run on another workstation.
- **Local mode:** run BOY on the backend host, with 127.0.0.1 in its CA list.
- BOY may use preferences instead of shell environment variables. Preserve site
  CA settings for other displays. No database filesystem mount is needed.

See [DEPLOYMENT.md](../docs/DEPLOYMENT.md) for commands. Remove old
`SMI:WINDOW:COMM:` overrides. Static labels must render without the IOC; if blank,
inspect Window → Show View → Other → General → Error Log.

## Screens

| File | Purpose |
| --- | --- |
| `window_overview.opi` | Default visual monitor, installed-window summary, compact state box |
| `beamline_schematic.opi` | Alias of the visual monitor |
| `window_details.opi` | Counters, milestones, references, coverage and recording statistics |
| `commissioning_overview.opi` | Raw/normalized inputs, source/receipt/change times and vacuum watch |
| `change_window.opi` | Identity-bound arm/token/typed-ID replacement workflow |

Window summary: ID, installed UTC, closed+pumped time, closed-window shutters-open
time and pump cycles. Durations use `24 days 8:05:01`, rounded to seconds, with
numeric PVs retained. Unknown legacy dates stay unknown. Pressure formatting
uses three significant digits (`800`, `0.003`, `3e-05`).

Beam arrow: green = all shutters open; red = known blocker; gray = unknown.
It is eligibility, not measured flux. Ring/BPM do not gate it. BPM3 is raw
intensity; energy is Bragg-derived keV. Chamber fills: blue <0.01 mbar, white
>=600, amber between, purple zero under-range, gray unknown. These are raw
ranges, not vacuum dwell or the 0.009 mbar detector-opening threshold. Bowing
is exaggerated toward lower pressure with a 1 mbar deadband, not a stress model.

Last read is monitor/health-read receipt; last change is locally observed change,
timed monotonically. “Just now” lasts 5 seconds. Startup/reconnect/gaps establish
baselines. Source UTC is separate; 1990-era dates are suspect. A recent read does
not certify hardware acquisition liveness.

## Maintenance and generation

Only the change screen writes `Window:Change-Cmd`, a history-maintenance endpoint.
See [window workflow](../docs/WINDOW_LIFECYCLE.md); success requires a durable
receipt. In network mode it is reachable by CA clients; the token is not
authentication. Site network access policy applies. No source PV is written.

Sources are `display.py`, `visual_display.py`, `change_display.py` under
`softioc/src/smi_window_tracker/`. Do not hand-edit generated XML. From repo root:

```bash
pixi run --manifest-path softioc/pixi.toml python -m smi_window_tracker.display frontend/opi
pixi run --manifest-path softioc/pixi.toml pytest frontend/tests
```

`opi/pv_manifest.json` lists suffixes and the sole writable command. Tests check
generation, geometry, references, BOY rules and embedded command syntax. Runtime
rendering/Jython interaction must also be checked in BOY. Historical plot/browser
screens remain future work.
