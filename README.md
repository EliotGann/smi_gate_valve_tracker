# SMI Kapton-window lifetime tracker

Design and offline foundation for a soft IOC that monitors a window-equipped gate
valve at NSLS-II SMI. The first release should record mechanical cycles, pump-down
curves and durations, vacuum/loading time, and beam exposure with an energy-aware
nominal upper-bound interaction estimate.

## Current status

**Local beamtime app:** see [startup and OPI instructions](docs/BEAMTIME.md).
`smi-kapton-monitor` serves read-only `XF:12IDC-ES{KaptonMon:1}...` PVs on
loopback only, journals live inputs to SQLite, restores counters/timers on restart,
and supplies `frontend/opi/window_overview.opi`. Exposure/material calibration
and installation-maintenance workflows remain incomplete.

The user selected **design and foundation** for this pass. Implemented here:

- Pixi development environment and a commissioning-only read-only caproto observer.
- Pure Python pump-cycle/valve counters, interval accounting, Bragg-energy
  conversion, beam-presence thresholding, and upper-bound/slab physics helpers.
- Offline example-based and property-based tests.
- Efficient pump milestone capture and offline early/recent duration comparisons.
- Bounded cycle cache, retained-Python-memory regression test, and offline
  expiring/one-use window-change confirmation guard.
- Detailed implementation plan, PV inventory, assumptions, physics, and test plan.

The commissioning observer remains a diagnostic-only option. The beamtime app
adds a reducer and durable SQLite recording. Material tables and supervised
production service deployment remain subsequent milestones.
The supplied Bluesky files in `docs/examples/bluesky/` are reference material; the package does
not import them or depend on a running Bluesky session.

## Repository layout

```text
softioc/                 Python application, tests, configuration, Pixi environment
  pixi.toml              App development tasks and dependencies
  pixi.lock              Locked environment
  pyproject.toml         Package and test configuration
  src/smi_window_tracker/
  tests/
  config/design.toml     Design inputs (not yet live IOC configuration)
frontend/                BOY .opi implementation scaffold and developer notes
docs/                    Design, requirements, operational and display plans
  examples/bluesky/      Supplied beamline reference Python files
```

See the [app guide](softioc/README.md), [frontend guide](frontend/README.md), and
[documentation index](docs/README.md). Frontend work is isolated in its own folder;
it can be extracted into a separate repository later if needed.

## Development (from the repository root)

```bash
pixi install --manifest-path softioc/pixi.toml
pixi run --manifest-path softioc/pixi.toml check
pixi run --manifest-path softioc/pixi.toml test
# Optional framework investigation, after controls discussion:
pixi run --manifest-path softioc/pixi.toml -e caproto python -c "import caproto; print(caproto.__version__)"
```

`softioc/pixi.lock` captures the resolved development/evaluation environments. Tests use
synthetic pressures, timestamps, and coefficients; no beamline network is needed.
`softioc/config/design.toml` records agreed values and unresolved selections, and is a
design artifact rather than a deployable IOC configuration.

## Start reading

1. [Design and milestones](docs/DESIGN.md)
2. [Confirmed choices and provisional assumptions](docs/ASSUMPTIONS.md)
3. [PV inventory](docs/PVS.md)
4. [Exposure and mechanical-loading physics](docs/PHYSICS.md)
5. [Remaining design questions](docs/QUESTIONS.md)
6. [Test and commissioning plan](docs/TESTING.md)
7. [Pump-down milestones and historical comparisons](docs/PUMP_TRENDS.md)
8. [Companion CS-Studio BOY screen layout](docs/DISPLAY.md)
9. [Shared Linux service, resource budgets and recovery](docs/SERVICE.md)
10. [Window replacement and lifetime history](docs/WINDOW_LIFECYCLE.md)

Commissioning correction: TCG:9 `P-I` (formerly MAXS) is the pump-down side;
TCG:7 WAXS is the sample chamber. Both are mbar; loading uses their measured
pressure difference. TCG:9 `P-I` reports numeric 0E0 below gauge range.
Atmosphere qualification is `P > 700 mbar`; pumped qualification is `P < 0.01 mbar`.
Retain both completed full pump cycles and closures reaching
vacuum, and both beam-path time and closed-window exposure time. Framework
selection awaits discussion with controls.

Pressure-noise qualification: a 700 mbar crossing must reach **<500 within 120 s**.
Keep one candidate with a fixed deadline, discarding expired candidates. Vacuum
requires **5 s below 0.01**, then stays latched until **>0.02 mbar**. Pump duration
uses the qualifying crossing timestamps; pumped-time integration starts at confirmation.

The initial exposure model uses **1e13 photons/s × attenuator transmission**,
gated by ring, all three shutters and closed window, ignoring sample absorption.
BPM3 beam inference and its separate timer are disabled: SumX reads 0.6 without
beam. Raw diagnostics remain visible; BPM3 does not gate or scale the exposure estimate. Energy is
derived from the Bragg readback. Fast-shutter timing must resolve rare **0.1 s**
exposures (usually >=0.5 s). BPM3 photon-flux calibration is future work.

Plan energy support through **24 keV**. Record pump milestones at **100, 10, 1,
0.1 mbar** and final completion, displaying current/last durations against fixed
early and recent history. Slowdown ratios are informational initially. The BOY
`.opi` screens will be implemented under `frontend/` using the layout here.

The service plan restores the current window after restart and targets <=1 s of
uncommitted increments under healthy operation. New physical windows use an
expiring arm/token/typed-ID confirmation, preserve retired histories, and start
fresh active statistics. SQLite transactions and live CA/service soak tests are
still future work; the offline guard does not reset or persist statistics itself.
