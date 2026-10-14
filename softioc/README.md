# KaptonMon soft IOC

For installation beneath a site softioc directory with outer `st.cmd`/`config`
and manage-iocs supervision, see the
[standard installation instructions](../README.md#standard-ioc-server-installation-manage-iocs).
The manager runs `sh st.cmd`; that wrapper uses bash to invoke `start-monitor.sh`.
Site configuration/environment remains outside the checkout.

Install from this directory: `pixi install --locked -e caproto`.

## Network IOC server

```bash
bash start-monitor.sh
```

`softioc` is the default mode; flags override the site's inherited EPICS settings.
With the launch environment configured, just `bash start-monitor.sh --mode softioc`
is sufficient. Repeat either address flag as needed. `--server-port` overrides
`EPICS_CAS_SERVER_PORT` (caproto default 5064). These options
configure only the output server, preserving beamline input `EPICS_CA_*` discovery.

## Local test

```bash
bash start-monitor.sh --mode local \
  --database "$HOME/kapton-monitor-beamtime/history.sqlite"
```

This binds output TCP/UDP and beacons to loopback. Use BOY on the same workstation
with 127.0.0.1 in its CA list. For network mode, BOY points at the IOC host instead.
Open `../frontend/opi/window_overview.opi`, macro `P=XF:12IDC-ES{KaptonMon:1}`.

## Storage and restart

Default history: `/nsls2/data/smi/shared/config/kaptondb/history.sqlite`.
Rotating `kapton-monitor.log` is stored beside the selected database. SQLite uses
DELETE/FULL journaling for the deployment volume. Provision mount/permissions first.
Only first creation uses `--init --window-id UNIQUE_ID`; otherwise omit both to
resume. Migrate existing history via SQLite backup instead of initializing anew.
After a configuration edit, `--accept-config-change` records the new epoch.
Window replacement is a confirmed transaction in the same persistent database.

Read [DEPLOYMENT.md](../docs/DEPLOYMENT.md) and [STORAGE.md](../docs/STORAGE.md)
for networking, NFS details, backups, files and supervisor behavior. Both modes
support graceful SIGTERM. Only the tracker's `Window:Change-Cmd` accepts writes
(history maintenance, not device control). No authenticated user/host ACL is
implemented in the application; network mode exposes it to reachable CA clients.

## Diagnostic-only observer

`pixi run -e caproto smi-window-commissioning --config config/commissioning.toml`
defaults to local mode. It also supports `--mode softioc --interface ...
--beacon-address ...`. It has no SQLite recorder or maintenance command; use the
diagnostic OPI rather than the full overview. Do not run it alongside the full
IOC under the same prefix.

## Development

```bash
pixi run check
pixi run -e caproto pytest tests/test_commissioning_ca.py
pixi run python -m smi_window_tracker.display ../frontend/opi
```

Generated displays/manifest are checked against source. BOY dialog/runtime
acceptance belongs on the actual workstation. Supplied Bluesky modules under
`../docs/examples/` are reference material, not application imports.
