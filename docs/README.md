# Documentation index

Start with **DEPLOYMENT.md** for launch/network commands and **STORAGE.md** for
files, shared-volume migration and backups. BEAMTIME.md defines current metrics.
DESIGN/DISPLAY/PUMP_TRENDS/ASSUMPTIONS retain explicitly labeled design targets;
they are not deployment instructions. The dated debrief is historical evidence.

| Document | Contents |
| --- | --- |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Network soft IOC versus local mode, installation and operations |
| [DESIGN.md](DESIGN.md) | Architecture, metric contract, state machines and milestones |
| [BEAMTIME.md](BEAMTIME.md) | Local-only KaptonMon recorder, facility-style names, main OPI, restart and backup |
| [STORAGE.md](STORAGE.md) | Default deployment volume, database/window records, file lifecycle and rotating logs |
| [PROCEDURES.md](PROCEDURES.md) | Vacuum-first/manual-pump classification, GV7 sequence alarms and five-minute isolated hold |
| [ASSUMPTIONS.md](ASSUMPTIONS.md) | Confirmed decisions, proposals and implementation boundaries |
| [PVS.md](PVS.md) | Beamline PV inventory, source references and verification needs |
| [CLOSED_WINDOW_WATCH.md](CLOSED_WINDOW_WATCH.md) | Live state column and downstream pressure-rise diagnostics during upstream venting |
| [PHYSICS.md](PHYSICS.md) | Mechanical loading, upper-bound exposure and deposition model |
| [PUMP_TRENDS.md](PUMP_TRENDS.md) | Pressure milestones, early/recent references and comparisons |
| [SERVICE.md](SERVICE.md) | Shared-host Linux service, persistence and stability test strategy |
| [WINDOW_LIFECYCLE.md](WINDOW_LIFECYCLE.md) | New-window confirmation, retired history and lifetime summaries |
| [DISPLAY.md](DISPLAY.md) | BOY screen wireframe and frontend/server contract |
| [TESTING.md](TESTING.md) | Offline and planned integration/commissioning verification |
| [QUESTIONS.md](QUESTIONS.md) | Remaining design and commissioning questions |
| [examples/bluesky/](examples/bluesky/README.md) | Supplied Python reference files |

Application code/configuration is in [../softioc/](../softioc/README.md); display
commissioning implementation is in [../frontend/](../frontend/README.md).
