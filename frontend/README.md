# CS-Studio BOY frontend

This folder is reserved for the **legacy BOY `.opi`** frontend. It currently
contains the implementation guide and OPI scaffold; screens are not implemented.
It is kept separate from the Python app and can later be extracted into its own
repository. BOY does not require the soft IOC's Pixi environment to display PVs.

## Specifications

- [Screen layout and PV/array contract](../docs/DISPLAY.md)
- [Pump-trend calculations and display semantics](../docs/PUMP_TRENDS.md)
- [Window replacement confirmation and history](../docs/WINDOW_LIFECYCLE.md)
- [IOC architecture](../docs/DESIGN.md)

Implement screens under `opi/`. Use `$(P)` for the IOC prefix, adjustable display
resolution, and related screens for history/diagnostics/maintenance. Keep all
counter, qualification and baseline calculations in the server. Frontend scripts
handle presentation and atomic lifecycle command transport only.

When implementation begins, add BOY XML/macro/PV-manifest checks and simulator
fixtures in `tests/`; record the supported BOY/IOC contract versions. No Python
build or placeholder frontend dependency environment is needed at this stage.
