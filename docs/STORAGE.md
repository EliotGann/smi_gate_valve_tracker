# Deployment storage and file lifecycle

Default directory: **`/nsls2/data/smi/shared/config/kaptondb`**.
Default database: **`history.sqlite`** within that directory.
`--database /other/path/history.sqlite` overrides it for beamtime/testing. The
default log is `kapton-monitor.log` beside the selected database; `--log-file`
overrides that separately. The app does not create missing parent directories.
Provision the mounted directory with write permissions for the IOC account.

## Single database, many windows

The database is created **once**, explicitly with `--init --window-id ID`.
Normal startup opens that file and resumes its active window. A missing database
is an error, not an automatic reset. Omit `--window-id` on normal startups so a
window replacement does not leave a stale identity in the startup script.

A confirmed replacement does **not** create another file. One transaction:

1. Flushes accepted observations and the old window's final totals.
2. Retires its `installations` record, preserving dates, totals and audit metadata.
3. Creates a new installation record, makes it current and stores its installation date.
4. Starts a new session linked by `session_windows`; future events/cycles belong
   to that window through their session ID.
5. Writes a fresh current-window checkpoint and a durable replacement receipt.

Thus the same file contains all physical windows, sessions, selected raw input
history, pump cycles, procedure events, snapshots, configuration epochs and
current restart checkpoint. Old data is retained; only active totals reset.
All windows and histories are included in one SQLite backup.

## Files and when they appear

| File | Created/updated when | Growth/lifetime |
| --- | --- | --- |
| `history.sqlite` | Explicit first `--init`; updated while running | Persistent history for every window; grows with selected events/snapshots |
| `history.sqlite.lock` | First attempted database open | Tiny lock file; remains after shutdown; OS releases lock when process exits |
| `history.sqlite-journal` | SQLite write transaction | Transient rollback journal; normally removed on commit; may survive a crash for recovery—do not delete manually |
| `kapton-monitor.log` | Backend startup after database opens | Application/framework log, rotates at 10 MiB |
| `kapton-monitor.log.1` … `.5` | Log rollover | Five backups; about 60 MiB total across current + backups |
| `history.sqlite.compacting` | Explicit offline compaction only | Temporary smaller replacement database; renamed over original after validation; may remain after a failed compaction |
| Backup/export/resource logs | Only when separately requested/run | No automatic backup or external resource logger is started by this app |

Older versions used `history.sqlite-wal` and `history.sqlite-shm`. On a stopped
legacy database, startup transitions to rollback journaling, preserving history.
These old sidecars should disappear when SQLite checkpoints/closes them; do not
manually discard a WAL because it may contain committed data.

Startup before logging initialization (bad path, permission, mismatched config,
database lock) reports to stderr. The rotating file captures subsequent Python
logging, including caproto diagnostics; unhandled tracebacks may also go to stderr.
Any external shell `>> output.log` or IOC-manager console capture needs its own
rotation policy on this volume. Pixi environments/caches remain package-install
artifacts elsewhere, not recorder history.

## Filesystem and single-writer deployment

On the current workstation this requested path resolves to **NFSv4**. SQLite WAL
does not support network filesystems, so the recorder now uses **DELETE rollback
journaling + synchronous=FULL**, with the existing instance lock. One IOC process
on one designated server should own the database. Correct operation depends on
working NFS advisory locking and storage sync semantics; locking, latency and
recovery on the actual IOC server still require deployment testing. Hard-mounted
NFS can stall during outages. There is no fallback database on the root disk.

Do not switch a live database's files or journal mode while the old recorder is
running. To move the existing beamtime history, stop it and use SQLite's backup
API/`.backup` to create `history.sqlite` in the new directory, then start without
`--init`. Moving it is **not** performed by changing the default. Keep the explicit
`--database "$HOME/kapton-monitor-beamtime/history.sqlite"` argument to continue
the present test in its original location.

## Bash startup

One-time creation on the provisioned deployment volume:

```bash
bash /path/to/softioc/start-monitor.sh --mode softioc \
  --interface IOC_SERVER_IP --beacon-address SUBNET_BROADCAST_IP \
  --init --window-id "physical-window-001"
```

Every normal start, including after a window replacement:

```bash
bash /path/to/softioc/start-monitor.sh --mode softioc \
  --interface IOC_SERVER_IP --beacon-address SUBNET_BROADCAST_IP
```

Equivalent command from `softioc/`:

```bash
pixi run -e caproto smi-kapton-monitor --config config/commissioning.toml \
  --mode local --database "$HOME/kapton-monitor-beamtime/history.sqlite"
```

Storage handling is identical in both modes. `softioc` serves the selected network
interfaces; `local` binds only loopback. Neither automatically moves existing data.
See [DEPLOYMENT.md](DEPLOYMENT.md) for CA discovery and exact mode options.
