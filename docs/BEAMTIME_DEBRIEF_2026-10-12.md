# First beamtime soak and history compaction

Data: `beamtime-window-001`, 2026-09-23 to 2026-10-12. The final continuous
session lasted 19.07 days and ended normally at 2026-10-12 17:55:23 UTC.

## Resource log

- 5,492 five-minute samples; largest sampling gap 301 seconds.
- RSS: 56.0 MiB initially, peak 88.2 MiB, final 73.9 MiB. No sustained increase.
- VSZ settled at 419.8 MiB; thread count remained 2.
- `ps %CPU` ranged 1.5–1.9%, a lifetime average, not instantaneous peak usage.
- Resource log retained separately in the beamtime directory.

## Recorded behavior

- No complete/partial pump-cycle records. Final counts: one close and one open,
  zero closures reaching qualified vacuum, zero complete pump cycles.
- GV6W closed on October 12 at 17:42:35 UTC and reopened at 17:45:25 UTC,
  approximately 169 seconds later. Otherwise it was observed open.
- Shutter-only beam-path time: 68,001.56868472556 s (18.889 h).
- Closed-window shutters-open time and closed-pumped time: zero.
- Closed-window pressure integral: 6,779.174814838916 mbar s.
- No per-input receipt gap over 5 s. Fast shutter source timestamps were old
  IOC dates, as already identified; receipt timing was used for integration.
- Snapshot intervals peaked at 1.1155 s; this is not a measured fsync-latency bound.
- Source alarm severities were recorded, including major pressure alarms and
  four INVALID downstream pressure readings. Minor/major severity alone does
  not mean a disconnection. Early WAXS numeric-text parsing issues are preserved
  in history rather than retroactively changing totals.

## Compaction performed

Applied `changes-v1` selection offline while the recorder was stopped:

| Measure | Before | After |
| --- | ---: | ---: |
| Database bytes | 8,669,057,024 | 141,791,232 |
| Size | 8.07 GiB | 135.22 MiB |
| Input event rows | 25,981,710 | 533,047 |
| Historical snapshot rows | 3,278,819 | 27,365 |

Space reduction: **98.36%**. The original large database was replaced after
validation, as requested. Identity, all six sessions, cycles and the final
checkpoint were compared verbatim; totals/counters were unchanged. The last
historical sequence remains 3,278,819. SQLite integrity checks passed before
replacement and on the resulting database. The database's `compaction_audit`
table records counts and policy. Selected original row IDs/timestamps remain.

Retained event rows by input: fast shutter 135,351; Bragg 90,580; downstream
pressure 84,611; sample pressure 84,968; FE 27,433; photon shutter 27,782;
GV6W 27,420; ring current 27,526; ring mode 27,362; BPM3 10 (session endpoints);
restart markers 4. Counts include minute anchors and quality changes, not just
value transitions.

## Next-day test

Restart with the same database/config/window ID, **without `--init`**, and reload
the main OPI. Observe `Storage:Policy-Sts = changes-v1`, the per-session
received/retained/skipped counts, database event/snapshot totals and size (MiB,
including WAL). Expect a small WAL startup increase, followed by much slower
growth. Current-process counters reset at restart; accumulated physics/cycle
totals persist. Start a new resource log using the new Python process PID.

Sparse history no longer supports naive replay of every liveness refresh;
retained gaps/quality records and checkpoint coverage must be respected.
No new beamtime process was started as part of the compaction operation.
