# Shared Linux IOC host: stability, recovery and resource budgets

## Requirements and framework recommendation

This IOC will run as a service alongside many other soft IOCs, and may be stopped
and restarted frequently. Pump-down frequency is at most approximately once/hour
in normal use. That limits cycle-summary volume (about 8,760/year at continuous
maximum use), **not** PV traffic: pressure, electrometer and shutter events can
arrive much faster. Design and test those loads separately.

Caproto remains a provisional recommendation for CA client/server integration,
with a single ordered calculation engine and SQLite history. Python makes the
custom bookkeeping straightforward; it does not guarantee absence of leaks.
EPICS Base/pythonSoftIOC is a strong alternative if it is the controls team's
supported runtime. Its native components also need resource and reconnect tests.
Make the choice using **site support and measured long-running behavior**, keeping
the domain layer independent of transport. Do not run several competing framework
stacks in the production process just to retain optionality.

Before selecting caproto, test the pinned client and server versions together:
subscription cleanup, reconnect storms, stopped/slow clients, CA discovery/port
coexistence, large-array limits, shutdown cancellation and published alarm behavior.
Use one CA context per process, created once, with one owned subscription per
input. Reconnect must not append new callbacks or spawn another polling loop.

## Process structure and bounded ownership

Proposed runtime: one supervised process with a fixed set of async tasks for
acquisition, ordered reduction, publication and health, and one dedicated storage
worker owning its SQLite connection. No thread/task per sample, no unlimited
executor work queue, no synchronous disk fsync inside the CA event loop. Results
flow back in order; publish durable totals only after a successful commit.

| Resource | Proposed bound / policy (tune with measurements) |
| --- | --- |
| Input FIFO | 4,096 events plus payload byte limit; record depth/high-water mark |
| Storage queue | 4 transaction batches; batch has both byte/event count and <=1 s age limits |
| Input state | One current normalized value/metadata object per configured PV |
| Completed-cycle RAM | 200 most recent summaries; total count independent of cache length |
| Pump curve RAM | Bounded display reduction, 512 points per trace; raw samples streamed to storage |
| Historical statistics | First 5 reference members and latest 20 eligible metrics, loaded by bounded queries |
| History browsing | Keyset-paginated rows, capped page size; no fetch-all or all-window DataFrame |
| Lifecycle requests | One pending arm; immutable bounded fields; no unbounded token registry |
| Logs | Rate-limited repeated diagnostics; journald retention policy set with controls |
| Network outputs | Fixed PV set; bounded waveform lengths; test framework slow-client queues |

These sizes are proposals, not a claim of a measured capacity. Queues must bound
**bytes as well as item count**. Disable unrestricted waveform/string inputs.
History caches retain snapshots, not closures capturing all previous arrays.
Use fixed worker ownership and explicitly cancel/await tasks on shutdown. Keep
subscription cleanup idempotent. Check thread, task, socket and file-descriptor
counts after repeated reconnects and display open/close cycles.

If queues fill, do not silently drop shutter/valve edges or keep integrating an
apparently continuous interval. Mark affected coverage invalid at the earliest
uncertain boundary, expose overload, and rebaseline inputs after recovery. If a
separate reserved health/gap slot is needed, bound it too. A capped queue plus
unbounded blocked producer tasks is still an unbounded design. Never coalesce
pressure/energy/foil events without a documented integration/error policy.

SQLite is the history, not Python containers. The current foundation now bounds
the completed-cycle cache and exposes each completed cycle to its caller; a
future storage adapter must commit every completion before cache eviction can
discard its only durable representation. The foundation is not yet that adapter.

## Durability and restart protocol

Confirmed target: at most **1 second of uncommitted timer/exposure increments**
under healthy normal operation after abrupt termination; pump completions and
window changes commit immediately before acknowledgement/publication. The target
includes oldest-event queue age and commit latency, not merely a 1 Hz timer.
Measure `OldestUncommittedAge` and `LastCommitAge`; if storage cannot keep up,
expose degraded durability rather than promising the one-second bound. Power-loss
durability also depends on filesystem/storage honoring fsync.

Use local SQLite, WAL mode, `synchronous=FULL`, one writer, bounded busy timeout,
explicit transactions and versioned migrations. A transaction includes raw events
or their durable representation, metric increments, attempt/milestone changes,
baseline membership, and checkpoint sequence. Unique event/interval IDs make
retry/replay idempotent. Old lifetime totals and baseline IDs survive a process
restart exactly as last committed; there is no startup reset to zero.

Startup sequence:

1. Acquire an instance lock and validate config, database identity/schema and
   current window. Missing/corrupt expected history is an explicit fault; initial
   creation is a separate administrative operation.
2. Restore current-window totals, model epochs, early/recent baseline membership,
   last cycle/comparison, and quality coverage with bounded queries. Do not load
   all raw history. Establish a new process/session ID.
3. Record the gap since last durable observation, with uncertainty if wall time
   changed. Do not integrate across reboot monotonic origins. Interrupt any prior
   active pump attempt and clear ephemeral valve/pressure qualification.
4. Start subscriptions/health reads and obtain fresh baselines before resuming
   integration. A startup closed valve never invents an extra closure.
5. Publish restored committed values with acquiring/quality status; then mark
   ready when required input validity is established. All pending arms are absent.

Graceful SIGTERM: stop admitting new lifecycle requests, drain accepted data in
order, finalize elapsed intervals to the last justified valid boundary, commit,
close CA tasks and database, exit. Stop timeout is bounded; any forced kill leaves
recovery to the last transaction. One service instance per database/prefix.

WAL growth needs a policy too: short read transactions, bounded export pages,
periodic checkpoints, disk/WAL-size metrics and a maintenance budget. Do not let a
long-running display query pin the WAL indefinitely. Back up with SQLite's backup
API or an equivalent consistent procedure, and test restores. Backup retention
must include retired windows and model/reference definitions.

## Service deployment (plan, not a runnable unit yet)

Use the site's IOC manager or systemd, with a dedicated account, explicit working
directory and persistent local state directory. Install a tested pinned environment
before starting the service; do not solve/install Pixi packages on each restart.
Invoke the deployed executable/environment directly with explicit config/database
paths. No shell-dependent user startup scripts or Bluesky session required.

For systemd evaluate `Restart=on-failure`, restart backoff/start limits,
`TimeoutStopSec`, `MemoryHigh`, `MemoryMax`, `CPUQuota`, `TasksMax` and `LimitNOFILE`
against measured load and controls host policy. Avoid arbitrary memory/CPU caps
that kill healthy work or starve edge handling. Resource limits contain failures;
they do not fix leaks. Watchdog notifications are useful only if they reflect
reducer/storage progress, not a timer firing while a critical worker is stuck.

Use explicit CA network/interface settings, unique output prefix and compatible
server/repeater/discovery behavior on the shared host. Do not change host-wide
EPICS variables or ports used by other IOCs. Validate alongside representative
neighbors before rollout. Publish RSS, queue ages, task/subscription counts, event
rate, event-loop lag, commit latency, reconnect count and disk/WAL use at low rate.

## Leak and stability tests

Tests can detect regressions and boundedness violations, not prove every possible
leak absent. `tracemalloc` measures retained Python allocations; it misses native
and kernel memory. Combine it with process RSS/USS (e.g. psutil in the integration
harness), open descriptors, threads, tasks, subscription counts and queue limits.
RSS may retain allocator arenas after a burst; inspect sustained growth after
warm-up rather than requiring every byte to return immediately.

| Tier | Test and acceptance |
| --- | --- |
| Fast offline | Tens of thousands of synthetic cycles; total count grows while retained cycle cache stays bounded. Snapshot retained Python memory after warm-up and GC; fixed tolerance catches accidental full-history retention. |
| CA integration | Repeated connect/disconnect, resubscribe, screen client churn, invalid alarms, both shutter trigger paths, quiet inputs and slow clients; owned task/subscription/FD counts return to steady state. |
| Accelerated soak | At least 24 h initially, event traffic above measured peak, pump bursts far above 1/hour, pressure streams and repeated lifecycle/service sessions. Fit post-warm-up memory slope across multiple windows, inspect allocation diffs and maximum queues. |
| Deployment soak | Several days on the intended Linux stack with realistic clients; measure CPU, RSS/USS, descriptors, commit age and neighboring-IOC impact. Establish numerical regression budgets from this run. |
| Crash/recovery | Subprocess SIGKILL at each transaction boundary; either the whole batch/window switch is present or none. Repeat restart hundreds of times; no counter duplication, baseline loss, or token survival. |
| Storage failures | Disk-full, locked/busy storage, fsync delay, WAL-pinned reader, corrupt/missing DB, migration rejection and restored backup. Durable outputs never pretend uncommitted state is saved. |
| Lifecycle races | Duplicate arm/confirm, expiry, wrong identity, stale current window, two clients, same retired ID, lost response after commit, SIGTERM during change. Exactly one durable installation switch. |

The current offline retained-memory regression tests exercise domain objects only.
CA soak, RSS/FD checks, subprocess crash injection and database durability tests
are mandatory later milestones once those adapters exist; current unit coverage
must not be presented as evidence that the future live IOC is leak-free.
