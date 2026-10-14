# SMI Kapton window monitor

Caproto soft IOC for GV6W window use at NSLS-II SMI. Reads beamline PVs, records
window histories in SQLite, and publishes `XF:12IDC-ES{KaptonMon:1}...` PVs for
CS-Studio BOY 4.6.1. **Network IOC and local-only modes use the same application.**

## Run

Install the locked environment once:

```bash
pixi install --locked --manifest-path softioc/pixi.toml -e caproto
```

**IOC server**, inheriting the existing site EPICS environment:

```bash
bash softioc/start-monitor.sh
```

**Local workstation**, keeping the existing beamtime history:

```bash
bash softioc/start-monitor.sh --mode local \
  --database "$HOME/kapton-monitor-beamtime/history.sqlite"
```

`softioc` is the default mode and inherits standard EPICS network environment
variables; interface/beacon CLI flags are optional overrides. `local`
binds output TCP/UDP and beacons to loopback. Neither changes input CA discovery.
Default database: `/nsls2/data/smi/shared/config/kaptondb/history.sqlite`.
Normal startup requires an existing database. Only first-ever creation uses
`--init --window-id UNIQUE_ID`; omit both on subsequent starts. To preserve the
current beamtime history, migrate it rather than initialize another empty file.

See **[deployment runbook](docs/DEPLOYMENT.md)** for discovery/firewall details,
storage migration, initial creation, logging and supervised startup.

## Standard IOC-server installation (manage-iocs)

Install this repository as a subdirectory of the site's softioc instance
directory. The outer `st.cmd` and `config` belong to the server deployment:

```text
<site-softioc-directory>/kapton-monitor/
├── config                       # Site-generated manage-iocs configuration
├── st.cmd                       # Shell entry point run by the IOC manager
└── smi_gate_valve_tracker/       # This Git checkout
    ├── softioc/
    │   ├── start-monitor.sh
    │   ├── pixi.toml
    │   └── config/commissioning.toml
    └── frontend/opi/
```

1. Clone the repository into `smi_gate_valve_tracker/` under the instance directory.
2. As the IOC service account, install the environment once:
   `pixi install --locked --manifest-path smi_gate_valve_tracker/softioc/pixi.toml -e caproto`.
3. Provision `/nsls2/data/smi/shared/config/kaptondb` and migrate the existing
   history with the old recorder stopped, as described in the deployment runbook.
   Use `--init --window-id ID` only for an intentionally new database.
4. Place this POSIX-shell wrapper in the **outer** `st.cmd`:

   ```sh
   #!/bin/sh
   set -eu
   IOC_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
   exec bash "$IOC_DIR/smi_gate_valve_tracker/softioc/start-monitor.sh" "$@"
   ```

5. Have the server's normal IOC configuration launch **`sh st.cmd`** in the
   instance directory, under the intended IOC account with `pixi` available in
   `PATH`. The outer `config` uses the site's existing format and supplies the
   EPICS environment; it is distinct from the application's input-PV TOML.
6. Register/control this instance using the site's usual **manage-iocs** workflow
   for start, stop, restart, status and console access. Keep the process in the
   foreground; do not add `&`, `nohup`, or database initialization to normal startup.

The wrapper deliberately calls **bash** for `start-monitor.sh`, even when the
server invokes `st.cmd` with `sh`. The launcher inherits the site's EPICS network
variables, uses the shared database/log defaults, and resumes the active installed
window. SIGTERM permits a final flush; configure the manager to signal/wait for
the application process or its process group, allowing for storage latency.

Host IPs, manager configuration, account settings and server-specific paths stay
in the **outer deployment directory/environment**, outside this Git checkout.
No edits to Pixi or tracked startup scripts are needed per server. After an update,
install the locked environment as needed and restart through manage-iocs; preserve
the database. Do not leave a hard-coded window ID in `st.cmd` after initialization.

## Operator displays

Open **`frontend/opi/window_overview.opi`**: the visual default view, with chamber
pressures, valve/blade states, qualitative bow, shutter eligibility, energy,
installed-window identity and readable totals. Macro: `P=XF:12IDC-ES{KaptonMon:1}`.
It links to detailed statistics, input diagnostics and confirmed window replacement.
For remote displays, point BOY CA discovery at the IOC server; no database mount
is required on operator workstations.

## Implemented

- Read-only subscriptions/health reads to beamline PVs; state/quality diagnostics.
- Reduced history (`changes-v1`), transactional restart checkpoints and SQLite
  DELETE/FULL journaling; rotating logs on the selected storage volume.
- Opens/closes, closures reaching qualified vacuum, pump cycles/milestones,
  closed-pumped time, shutter-only exposure time and pressure-time loading proxy.
- Vacuum-first and manual-pump paths, GV7 sequence warnings, 300 s isolated hold,
  0.009 mbar warning threshold and a closed-window pressure-rise watch.
- Persistent installations and audited arm/token/typed-ID window replacement.
  `Window:Change-Cmd` is the sole writable tracker PV; it never actuates hardware.
- Human-readable pressure, duration/date, receipt/change ages and raw numeric PVs.
- Offline tests, synthetic CA integration, restart/rollback tests, and a 19-day
  local commissioning soak summarized in the documentation.

## Interpretation and remaining limits

TCG:9 is the pumped side; TCG:7 is WAXS sample pressure, both mbar. Pump entry
requires <600 after >700 arming, then <500 within 120 s; vacuum requires <0.01
for 5 s and exits above 0.02. Procedural vent confirmation sets above 700 and
clears below 600. The GV7 opening check is separately <0.009 mbar.

Beam time is **shutter eligibility**, not measured dose; BPM3 is an uncalibrated
diagnostic and does not gate it. Photon/J models, ring eligibility policy,
material calibration, gauge under-range bounds and historical plotting/browsing
remain unfinished. Procedural warnings are advisory, not hardware interlocks.
Network deployment/NFS performance need verification on the chosen IOC server;
the workstation soak does not constitute that verification.

## Development and layout

```bash
pixi run --manifest-path softioc/pixi.toml check
pixi run --manifest-path softioc/pixi.toml -e caproto pytest softioc/tests/test_commissioning_ca.py
```

The last command is normally run from `softioc/` as
`pixi run -e caproto pytest tests/test_commissioning_ca.py`.

- `softioc/`: runtime, tests, configuration, Pixi environment and bash launcher.
- `frontend/opi/`: generated BOY screens and PV manifest.
- `docs/`: [current guides and design references](docs/README.md).
- `docs/examples/bluesky/`: reference inputs, not runtime imports.
