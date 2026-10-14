# KaptonMon IOC deployment

## 1. Install and choose mode

Deploy the repository at a stable absolute path on the IOC server. Install once,
before handing the launcher to the site's IOC manager:

```bash
pixi install --locked --manifest-path /path/to/softioc/pixi.toml -e caproto
```

Run under the designated IOC account with access to the CA network and storage.
The bash launcher uses `exec` and the locked Pixi environment. Do not run a second
copy with the same database or output prefix. SIGTERM and Ctrl-C cancel acquisition,
finish in-flight SQLite work, flush accepted events and close the recording session.

### Network soft IOC (default mode)

Replace the address placeholders with actual site values:

```bash
bash /path/to/softioc/start-monitor.sh --mode softioc \
  --interface IOC_SERVER_IP \
  --beacon-address SUBNET_BROADCAST_IP
```

The interface must be a specific local IPv4 address. Repeat `--interface` to
serve multiple interfaces, including 127.0.0.1 if local clients need it. Repeat
`--beacon-address` for subnet broadcasts or individual client/repeater addresses;
an optional `:PORT` suffix overrides the beacon destination port (normally 5065).
Automatic/global broadcast is disabled to avoid the blocked 255.255.255.255
destination encountered during commissioning. Missing explicit network settings
cause a startup error before database/log files are touched.

The full application's default mode is `softioc`. To avoid accidentally exposing
a test instance, always specify `--mode local` for a workstation test.

### Local-only mode

```bash
bash /path/to/softioc/start-monitor.sh --mode local \
  --database "$HOME/kapton-monitor-beamtime/history.sqlite"
```

Local mode forces output listeners/beacons to 127.0.0.1, overriding inherited
`EPICS_CAS_*` settings. It rejects network-interface/beacon arguments. BOY must
run on the same host and include 127.0.0.1 in its CA address list. The optional
`smi-window-commissioning` diagnostic-only entry point defaults to local mode;
it accepts the same mode/interface/beacon/port arguments but has no recorder.

### Equivalent Pixi commands (from softioc/)

```bash
pixi run -e caproto smi-kapton-monitor --mode softioc \
  --config config/commissioning.toml \
  --interface IOC_SERVER_IP --beacon-address SUBNET_BROADCAST_IP

pixi run -e caproto smi-kapton-monitor --mode local \
  --config config/commissioning.toml \
  --database "$HOME/kapton-monitor-beamtime/history.sqlite"
```

## 2. CA discovery and coexistence

`--server-port` defaults to 5064 and sets only `EPICS_CAS_SERVER_PORT`. Server
interfaces are passed explicitly to caproto. Input reads retain the IOC account's
existing **`EPICS_CA_ADDR_LIST` / `EPICS_CA_AUTO_ADDR_LIST` / client port settings**.
Do not point the application's input discovery only at itself.

Clients need CA search access to the configured server interface/port. In BOY's
CA preferences, include `IOC_SERVER_IP` (or `IOC_SERVER_IP:PORT` for a nonstandard
search port). BOY may use preferences instead of shell variables. A direct host
entry avoids relying on broadcast routing across subnets. Beacons help discovery
and reconnect but do not replace client search configuration.

The conventional traffic is UDP searches on 5064, TCP CA connections on the
server's advertised TCP port, and UDP beacons to client repeaters on 5065. If
another IOC occupies the TCP port, caproto can advertise a fallback port; check
startup logs/listeners and the server firewall rather than assuming all TCP
connections use 5064. A dedicated address or port simplifies shared-host operation.
Clients using an explicit host:port should point at the search port.

Check from an operator workstation:

```bash
EPICS_CA_AUTO_ADDR_LIST=NO EPICS_CA_ADDR_LIST=IOC_SERVER_IP \
  caget 'XF:12IDC-ES{KaptonMon:1}Heartbeat-I'
EPICS_CA_AUTO_ADDR_LIST=NO EPICS_CA_ADDR_LIST=IOC_SERVER_IP \
  caget 'XF:12IDC-ES{KaptonMon:1}Storage:Seq-I'
```

Open `frontend/opi/window_overview.opi`, macro `P=XF:12IDC-ES{KaptonMon:1}`.
Confirm heartbeat/commit progress, fresh source reads and expected pressure/valve
states. Network mode exposes the intentional `Window:Change-Cmd` history-maintenance
endpoint to reachable CA clients. Its token workflow prevents accidental replay,
not unauthorized access; operator names are audit labels. The application has no
authenticated user/host ACL. Use the site's controls-network access policy.

## 3. Persistent storage

Default database: `/nsls2/data/smi/shared/config/kaptondb/history.sqlite`.
Default rotating log: `kapton-monitor.log` beside the chosen database.
Provision directory/mount/permissions before startup; no fallback or automatic
directory creation occurs. `--database` and `--log-file` override these paths.
Logs rotate at 10 MiB with five backups. See [STORAGE.md](STORAGE.md) for files.

The target path resolves to NFSv4 on the commissioning workstation. Current runtime
uses SQLite **DELETE rollback journal + synchronous=FULL**, not WAL. Exactly one
IOC host/process owns the database; verify NFS locking/sync behavior and commit
latency on that host. A missing/unavailable mount or a hard-NFS stall is not hidden
by switching to a new local database. Supervisor timeout must allow storage recovery.

### Preserve the existing beamtime history

Stop the workstation recorder first. Confirm the destination file does not exist.
Use SQLite's backup operation to copy committed history (including legacy WAL):

```bash
sqlite3 "$HOME/kapton-monitor-beamtime/history.sqlite" \
  ".backup '/nsls2/data/smi/shared/config/kaptondb/history.sqlite'"
```

Start the deployment command **without `--init`**. Retain the original until the
destination identity/totals/history have been checked. Do not serve both copies.
The application converts stopped legacy WAL databases on open without resetting
their contents. This deployment preparation does not automatically migrate data.

### Empty first installation only

If there is intentionally no prior history, append `--init --window-id UNIQUE_ID`
to the deployment command once. It refuses to overwrite an existing file. Normal
starts omit both flags and restore the active installed window. New physical
windows are created via the confirmed OPI workflow in the **same database**.
Installation date for the initial legacy-style record is unknown until supplied
through a supported installation workflow; no startup date is invented.

Configuration changes require `--accept-config-change` once, recording old/new
config epochs while preserving totals. Do not leave a stale explicit window ID
in the server script. Input configuration is `softioc/config/commissioning.toml`
(historical filename; it is the current runtime input map).

## 4. Operator and maintenance checks

- Observe `Storage:Age-I`, `Storage:Pending-I`, `Storage:State-Sts` and commit
  sequence. Counts/timers resume; pending pump/hold observations rebaseline after
  restart, and ephemeral replacement tokens do not survive.
- `changes-v1` retains meaningful changes, quality boundaries and periodic anchors.
  Frequent recovery checkpoints overwrite one row; full historical snapshots are
  sparse. No automatic deletion of existing window history occurs.
- Back up with SQLite `.backup` or its API, not a live main-file-only copy. Keep
  backup/export/resource-monitor logs on the data volume with their own retention.
- Explicit offline compaction: `pixi run python -m smi_window_tracker.compact
  /path/history.sqlite --replace` from `softioc/`, with the IOC stopped.
- Rotation covers application logs, not an external IOC-manager console capture.
  Configure its retention separately. Do not install/solve packages on every restart.

## 5. Verification and scope

`pixi run check` and `pixi run -e caproto pytest tests/test_commissioning_ca.py`
exercise domain/storage/display contracts, network-mode configuration, loopback
CA transport, lifecycle commands and SIGTERM shutdown. Network-mode tests use an
isolated loopback interface; actual routed discovery/firewall/NFS acceptance must
be done at deployment. The 19-day local soak showed bounded memory, not a guarantee
for every target host/network/storage configuration.

This is a monitoring IOC, not a safety interlock. Device source PVs are never
written. Exposure time means shutter eligibility; BPM3 is raw diagnostic only.
Calibrated photon/J/dose, accepted ring policy, gauge under-range bounds, and a
historical plotting/browser UI remain future work. Current procedure/threshold,
window-change and history semantics are in the linked guides.
