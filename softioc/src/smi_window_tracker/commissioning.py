"""Read-only CA commissioning observer.

This is intentionally a diagnostic mirror, not the lifetime-tracking reducer.
It performs CA reads/subscriptions only on configured source PVs and republishes
their latest values and metadata under the tracker prefix for a BOY screen.
"""

import argparse
import asyncio
import os
import time
import tomllib
from dataclasses import dataclass
from math import isfinite
from numbers import Real
from pathlib import Path
from time import monotonic

from .contract import APP_FIELDS, PREFIX, TREND_SUFFIXES, VERSION, input_suffix
from .diagnostics import Diagnostics, Sample
from .time_text import ObservationTimes, source_time_text

TREND_FIELDS = {
    "Status": ("Waiting for inputs", None),
    "Baseline": (float("nan"), "mbar"),
    "Change": (float("nan"), "mbar"),
    "Rate": (float("nan"), "mbar/s"),
    "Span": (float("nan"), "s"),
    "Elapsed": (float("nan"), "s"),
    "UpstreamChange": (float("nan"), "mbar"),
    "DeltaP": (float("nan"), "mbar"),
}


@dataclass(frozen=True)
class InputSpec:
    """One explicitly configured read-only commissioning input."""

    name: str
    pv: str | None
    description: str


def load_inputs(path: Path) -> tuple[InputSpec, ...]:
    """Load and validate the small, explicit input map used by the observer."""
    with path.open("rb") as config_file:
        document = tomllib.load(config_file)
    inputs = document.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("Configuration requires an [inputs] table")

    specs = []
    for name, definition in inputs.items():
        if not isinstance(name, str) or not isinstance(definition, dict):
            raise ValueError("Each input must be a named TOML table")
        pv = definition.get("pv")
        if pv is not None and (not isinstance(pv, str) or not pv.strip()):
            raise ValueError(f"Input {name!r} has an invalid PV name")
        description = definition.get("description", "")
        if not isinstance(description, str):
            raise ValueError(f"Input {name!r} has an invalid description")
        specs.append(InputSpec(name=name, pv=pv, description=description))
    if not specs:
        raise ValueError("At least one input must be configured")
    return tuple(specs)


def _first_value(response) -> object | None:
    """Extract the scalar payload from a caproto response without assuming its type."""
    data = response.data
    if len(data) == 0:
        return None
    value = data[0]
    return value.decode(errors="replace") if isinstance(value, bytes) else value


def _numeric(value: object | None) -> float:
    """Accept finite native numbers or numeric scalar text, including EPICS E notation.

    Preserve raw text separately; do not coerce status labels, units or nonfinite
    values into pressure. Python's float parser handles both E/e and whitespace.
    """
    if not isinstance(value, (Real, str, bytes)):
        return float("nan")
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return float("nan")
    return number if isfinite(number) else float("nan")


def _text(value: object | None) -> str:
    return "" if value is None else str(value)


def make_ioc(specs: tuple[InputSpec, ...], store=None):  # pragma: no cover - optional CA runtime
    """Create a caproto PVGroup whose output PVs match the configured inputs."""
    try:
        from caproto.server import PVGroup, pvproperty
    except ImportError as error:  # pragma: no cover - exercised only without optional runtime
        raise RuntimeError("Install the caproto Pixi environment to run the observer") from error

    attributes: dict[str, object] = {
        "ContractVersion": pvproperty(name="Version:Contract-I", value=VERSION, read_only=True),
        "Heartbeat": pvproperty(name="Heartbeat-I", value=0.0, read_only=True),
    }

    def init(self, prefix, **kwargs):
        # PVGroup expands prefix with str.format. Facility device braces are
        # literal PV-name characters, not caproto macros. Escape only at this
        # boundary so config, clients, manifests and displays keep normal names.
        literal_prefix = prefix.replace("{", "{{").replace("}", "}}")
        PVGroup.__init__(self, prefix=literal_prefix, **kwargs)

    attributes["__init__"] = init
    if store is not None:
        for key, (suffix, initial, units) in APP_FIELDS.items():
            options = (
                {"units": units, "precision": 6} if units is not None else {"max_length": 1024}
            )
            attributes["app_" + key] = pvproperty(
                name=suffix, value=initial, read_only=True, **options
            )
    for name, (initial, units) in TREND_FIELDS.items():
        options = {"units": units, "precision": 6} if units else {"max_length": 256}
        attributes["trend_" + name] = pvproperty(
            name=TREND_SUFFIXES[name], value=initial, read_only=True, **options
        )
    for spec in specs:
        attributes[spec.name + "_value"] = pvproperty(
            name=input_suffix(spec.name, "Value"), value=float("nan"), read_only=True, precision=6
        )
        attributes[spec.name + "_text"] = pvproperty(
            name=input_suffix(spec.name, "Text"), value="", read_only=True, max_length=256
        )
        attributes[spec.name + "_connected"] = pvproperty(
            name=input_suffix(spec.name, "Connected"), value=0, read_only=True
        )
        attributes[spec.name + "_severity"] = pvproperty(
            name=input_suffix(spec.name, "Severity"), value=-1, read_only=True
        )
        attributes[spec.name + "_status"] = pvproperty(
            name=input_suffix(spec.name, "Status"), value=-1, read_only=True
        )
        attributes[spec.name + "_timestamp"] = pvproperty(
            name=input_suffix(spec.name, "Timestamp"), value=0.0, read_only=True, precision=6
        )
        attributes[spec.name + "_time_text"] = pvproperty(
            name=input_suffix(spec.name, "TimeText"),
            value="No source timestamp",
            read_only=True,
            max_length=256,
        )
        for field in ("ReadTime", "ChangeTime", "ReadAge", "ChangeAge"):
            numeric = field.endswith("Time")
            attributes[spec.name + "_" + field] = pvproperty(
                name=input_suffix(spec.name, field),
                value=0.0 if numeric else "Waiting for input",
                read_only=True,
                **({"precision": 3, "units": "s"} if numeric else {"max_length": 256}),
            )
        attributes[spec.name + "_state"] = pvproperty(
            name=input_suffix(spec.name, "State"),
            value="Waiting for input",
            read_only=True,
            max_length=256,
        )

    async def publish(self, spec: InputSpec, response) -> None:
        metadata = response.metadata
        sample = Sample(_numeric(_first_value(response)), monotonic(), int(metadata.severity))
        self.observation_times[spec.name].observe(
            sample.value,
            _text(_first_value(response)),
            mono=sample.received_s,
            utc=time.time(),
            valid=0 <= sample.severity < 3,
        )
        if store is not None:
            self.recorder.event(
                spec.name,
                sample,
                text=_text(_first_value(response)),
                source_time=float(metadata.timestamp),
                status=int(metadata.status),
            )
            if self.recorder.cycles:
                self.flush_requested.set()
        else:
            self.diagnostics.update(spec.name, sample)
        await getattr(self, spec.name + "_value").write(_numeric(_first_value(response)))
        await getattr(self, spec.name + "_text").write(_text(_first_value(response)))
        await getattr(self, spec.name + "_connected").write(1)
        await getattr(self, spec.name + "_severity").write(int(metadata.severity))
        await getattr(self, spec.name + "_status").write(int(metadata.status))
        await getattr(self, spec.name + "_timestamp").write(float(metadata.timestamp))
        await getattr(self, spec.name + "_time_text").write(
            source_time_text(float(metadata.timestamp), time.time())
        )
        await getattr(self, spec.name + "_state").write(
            self.diagnostics.state(spec.name, monotonic())
        )

    async def invalidate(self, spec: InputSpec) -> None:
        self.observation_times[spec.name].interrupt()
        sample = Sample(float("nan"), monotonic(), connected=False)
        if store is not None:
            self.recorder.event(spec.name, sample)
        else:
            self.diagnostics.update(spec.name, sample)
        await getattr(self, spec.name + "_connected").write(0)
        await getattr(self, spec.name + "_state").write("Disconnected / read failed")

    async def observe(self) -> None:
        from caproto.asyncio.client import Context

        configured = tuple(spec for spec in specs if spec.pv is not None)
        for spec in specs:
            if spec.pv is None:
                await getattr(self, spec.name + "_text").write("UNCONFIGURED")
                await getattr(self, spec.name + "_state").write("Unconfigured")
        context = Context()
        try:
            by_pv = {
                name: [spec for spec in configured if spec.pv == name]
                for name in (spec.pv for spec in configured)
            }

            async def connection_changed(pv, state):
                if state != "connected":
                    async with self.diagnostic_lock:
                        for spec in by_pv[pv.name]:
                            await invalidate(self, spec)

            pvs = await context.get_pvs(
                *(spec.pv for spec in configured), connection_state_callback=connection_changed
            )

            async def monitor(spec: InputSpec, pv) -> None:
                subscription = pv.subscribe(data_type="time")
                try:
                    async with subscription:
                        async for response in subscription:
                            async with self.diagnostic_lock:
                                await publish(self, spec, response)
                except Exception:
                    async with self.diagnostic_lock:
                        await invalidate(self, spec)
                    raise

            async def refresh(spec: InputSpec, pv) -> None:
                # Quiet change-only PVs need liveness reads, not replay of cached values.
                # Reject a read response if a newer monitor/connection event intervened.
                while True:
                    before = self.diagnostics.samples.get(spec.name)
                    try:
                        response = await pv.read(data_type="time", timeout=1.0)
                    except (TimeoutError, ConnectionError):
                        async with self.diagnostic_lock:
                            if self.diagnostics.samples.get(spec.name) is before:
                                await invalidate(self, spec)
                    else:
                        async with self.diagnostic_lock:
                            if self.diagnostics.samples.get(spec.name) is before:
                                await publish(self, spec, response)
                    await asyncio.sleep(1.0)

            # Monitors retain edges; refresh tasks establish quiet-input liveness.
            async with asyncio.TaskGroup() as tasks:
                for spec, pv in zip(configured, pvs, strict=True):
                    tasks.create_task(monitor(spec, pv))
                    tasks.create_task(refresh(spec, pv))
        finally:
            await context.disconnect()

    async def commit(self):
        import json

        async with self.diagnostic_lock:
            self.recorder.advance(monotonic())
            self.recorder.watch = self.diagnostics.snapshot(monotonic())
            state = json.loads(json.dumps(self.recorder.snapshot()))
            outputs = self.recorder.outputs()
            events, cycles = self.recorder.events, self.recorder.cycles
            self.recorder.events, self.recorder.cycles = [], []
        try:
            work = asyncio.create_task(asyncio.to_thread(store.commit, events, cycles, state))
            try:
                seq, utc = await asyncio.shield(work)
            except asyncio.CancelledError:
                await work  # SQLite connection must not be reused/closed while worker is active.
                raise
        except Exception:
            self.storage_failed = True
            await self.app_Storage.write("FAULT: commit failed; stopping")
            raise
        for key, value in outputs.items():
            await getattr(self, "app_" + key).write(
                float(value) if isinstance(value, int) else value
            )
        await self.app_CommitTime.write(utc)
        self.last_commit_utc = utc
        await self.app_CommitAge.write(max(0, time.time() - utc))
        await self.app_Queue.write(float(len(self.recorder.events)))
        await self.app_Storage.write("Recording (SQLite WAL/FULL)")
        await self.app_Commit.write(float(seq))

    async def writer(self):
        while True:
            self.flush_requested.clear()
            await commit(self)
            try:
                await asyncio.wait_for(self.flush_requested.wait(), timeout=0.5)
            except TimeoutError:
                pass

    async def heartbeat(self, instance, async_lib) -> None:
        # Own acquisition for the entire startup-hook lifetime. A detached task
        # can be garbage-collected, leaving an apparently healthy heartbeat.
        self.diagnostics = Diagnostics()
        self.observation_times = {spec.name: ObservationTimes() for spec in specs}
        self.diagnostic_lock = asyncio.Lock()
        if store is not None:
            from .beamtime import Recorder

            self.recorder = Recorder(store.restored)
            self.diagnostics = self.recorder.inputs
            self.flush_requested = asyncio.Event()
            self.storage_failed = False
            self.last_commit_utc = 0.0
            await self.app_Window.write(store.window)
            await self.app_Session.write(store.session)
        try:
            async with asyncio.TaskGroup() as tasks:
                tasks.create_task(observe(self), name="commissioning-ca-observer")
                if store is not None:
                    tasks.create_task(writer(self), name="sqlite-recorder")
                while True:
                    async with self.diagnostic_lock:
                        now = monotonic()
                        if store is not None:
                            await self.app_CommitAge.write(
                                time.time() - self.last_commit_utc
                                if self.last_commit_utc
                                else float("nan")
                            )
                            await self.app_Queue.write(float(len(self.recorder.events)))
                        for spec in specs:
                            timing = self.observation_times[spec.name]
                            read_age, change_age = timing.labels(now)
                            for field, value in (
                                ("ReadTime", timing.read_utc),
                                ("ChangeTime", timing.change_utc),
                                ("ReadAge", read_age),
                                ("ChangeAge", change_age),
                            ):
                                await getattr(self, spec.name + "_" + field).write(value)
                            if spec.pv is not None:
                                await getattr(self, spec.name + "_state").write(
                                    self.diagnostics.state(spec.name, now)
                                )
                                sample = self.diagnostics.samples.get(spec.name)
                                await getattr(self, spec.name + "_connected").write(
                                    int(sample is not None and sample.connected)
                                )
                            await getattr(self, spec.name + "_time_text").write(
                                source_time_text(
                                    getattr(self, spec.name + "_timestamp").value, time.time()
                                )
                            )
                        for name, value in self.diagnostics.snapshot(now).items():
                            await getattr(self, "trend_" + name).write(value)
                    await instance.write(instance.value + 1)
                    await async_lib.library.sleep(1.0)
        finally:
            # Shutdown flush is performed after acquisition tasks are cancelled.
            if store is not None and not self.storage_failed:
                await commit(self)

    attributes["_publish"] = publish
    attributes["_observe"] = observe
    attributes["Heartbeat"] = attributes["Heartbeat"].startup(heartbeat)
    return type("CommissioningIOC", (PVGroup,), attributes)


def main() -> None:  # pragma: no cover - command-line caproto integration
    """Run the commissioning observer with an explicitly selected output prefix."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--prefix", default=PREFIX)
    arguments = parser.parse_args()
    local_server_environment()
    ioc_class = make_ioc(load_inputs(arguments.config))
    ioc = ioc_class(prefix=arguments.prefix)
    from caproto.server import run

    run(ioc.pvdb, interfaces=["127.0.0.1"])


def local_server_environment():
    """Only output-server variables; preserve input client's EPICS_CA_* routing."""
    os.environ["EPICS_CAS_AUTO_BEACON_ADDR_LIST"] = "NO"
    os.environ["EPICS_CAS_BEACON_ADDR_LIST"] = "127.0.0.1"
    os.environ["EPICS_CAS_INTF_ADDR_LIST"] = "127.0.0.1"


def beamtime_main():  # pragma: no cover - optional CA entry point
    from .beamtime import Store

    parser = argparse.ArgumentParser(description="Local-only KaptonMon beamtime recorder")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--window-id", required=True)
    parser.add_argument(
        "--init", action="store_true", help="Create new database; fails if it exists"
    )
    args = parser.parse_args()
    specs = load_inputs(args.config)
    local_server_environment()
    store = Store(args.database, args.window_id, args.config.read_text(), create=args.init)
    try:
        from caproto.server import run

        ioc = make_ioc(specs, store=store)(prefix=PREFIX)
        run(ioc.pvdb, interfaces=["127.0.0.1"])
    finally:
        store.close()


if __name__ == "__main__":  # pragma: no cover
    main()
