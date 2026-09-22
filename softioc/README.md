# Soft IOC application

This directory is the independently packaged Python application and offline test
suite. The live CA adapters, SQLite persistence and service entry point remain
planned work; no command starts a live IOC yet.

## Development

Run these commands **from this directory**:

```bash
pixi install --locked
pixi run check
pixi run test
```

From the repository root, use `pixi run --manifest-path softioc/pixi.toml check`.
The optional `caproto` environment supports framework evaluation:

```bash
pixi run -e caproto python -c "import caproto; print(caproto.__version__)"
```

- `src/smi_window_tracker/`: domain logic for cycles, intervals, physics, trends
  and window-change confirmation.
- `tests/`: offline unit, property and retained-memory regression tests.
- `config/design.toml`: recorded design inputs; not a deployment configuration.
- `pixi.toml` / `pixi.lock`: app environment and development tasks.
- `pyproject.toml`: Python package, pytest and Ruff configuration.

The [shared design documentation](../docs/README.md) lives outside the package.
References to `docs/` in code docstrings are repository-root paths. Supplied
[Bluesky examples](../docs/examples/bluesky/README.md) are documentation inputs,
not importable application dependencies.
