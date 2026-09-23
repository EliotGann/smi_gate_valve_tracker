"""Real CA transport regression; run in the optional caproto environment."""

import os
import signal
import socket
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("caproto")


@pytest.mark.parametrize("recording", [False, True])
def test_exact_facility_prefix_matches_manifest(tmp_path, recording):
    import json

    from smi_window_tracker.beamtime import Store
    from smi_window_tracker.commissioning import load_inputs, make_ioc
    from smi_window_tracker.contract import APP_FIELDS, PREFIX

    root = Path(__file__).resolve().parents[2]
    specs = load_inputs(root / "softioc/config/commissioning.toml")
    manifest = json.loads((root / "frontend/opi/pv_manifest.json").read_text())
    store = Store(tmp_path / "db.sqlite", "test", "config", create=True) if recording else None
    try:
        ioc = make_ioc(specs, store=store)(prefix=PREFIX)
        expected = set(manifest["suffixes"])
        if not recording:
            expected -= {definition[0] for definition in APP_FIELDS.values()}
        assert ioc.prefix == PREFIX
        assert set(ioc.pvdb) == {PREFIX + suffix for suffix in expected}
        assert all(pv.pvname == name for name, pv in ioc.pvdb.items())
        assert all(pv.pvspec.read_only for pv in ioc.pvdb.values())
    finally:
        if store is not None:
            store.close()


def test_observer_receives_source_and_heartbeat_survives_gc(tmp_path):
    # Bind a local beacon sink so unicast UDP does not receive port-unreachable.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as beacon:
        beacon.bind(("127.0.0.1", 0))
        beacon_port = beacon.getsockname()[1]
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        env = {
            **os.environ,
            "EPICS_CA_AUTO_ADDR_LIST": "NO",
            "EPICS_CA_ADDR_LIST": f"127.0.0.1:{port}",
            "EPICS_CA_SERVER_PORT": str(port),
            "EPICS_CAS_SERVER_PORT": str(port),
            "EPICS_CAS_AUTO_BEACON_ADDR_LIST": "NO",
            "EPICS_CAS_BEACON_ADDR_LIST": f"127.0.0.1:{beacon_port}",
            "TEST_DATABASE": str(tmp_path / "beamtime.sqlite"),
        }
        server = """
import gc
import os
from pathlib import Path
from caproto import ChannelType
from caproto.server import PVGroup, pvproperty, run
from smi_window_tracker.commissioning import InputSpec, make_ioc
from smi_window_tracker.beamtime import Store
from smi_window_tracker.contract import PREFIX
store = Store(Path(os.environ['TEST_DATABASE']), 'window-test', 'test-config', create=True)
class Source(PVGroup):
    pressure = pvproperty(value=1.234, read_only=True)
    valve = pvproperty(value=0, read_only=True)
    chamber = pvproperty(value="8.1E+02", dtype=ChannelType.STRING, read_only=True)
    @valve.startup
    async def valve(self, instance, async_lib):
        await instance.write(0, timestamp=631152000.0)
    @pressure.scan(period=0.1)
    async def pressure(self, instance, async_lib):
        gc.collect()
        await instance.write(instance.value + 1)
src = Source(prefix="LOCAL:SOURCE:")
obs = make_ioc((InputSpec("pressure", "LOCAL:SOURCE:pressure", "synthetic"),
                InputSpec("valve", "LOCAL:SOURCE:valve", "synthetic"),
                InputSpec("chamber_pressure", "LOCAL:SOURCE:chamber", "synthetic")), store=store)(
    prefix=PREFIX)
assert all(pv.pvspec.read_only for pv in obs.pvdb.values())
try:
    run({**src.pvdb, **obs.pvdb}, interfaces=["127.0.0.1"])
finally:
    store.close()
"""
        client = """
import time
from caproto.sync.client import read as ca_read
from smi_window_tracker.contract import PREFIX, input_suffix, TREND_SUFFIXES
def read(name, **kwargs):
    suffix = name.removeprefix('LOCAL:OBS:')
    if suffix.startswith('Input:'):
        _, key, field = suffix.split(':')
        suffix = input_suffix(key, field)
    elif suffix.startswith('ClosedWatch:'):
        suffix = TREND_SUFFIXES[suffix.split(':')[1]]
    elif suffix == 'Heartbeat':
        suffix = 'Heartbeat-I'
    return ca_read(PREFIX + suffix, **kwargs)
deadline = time.monotonic() + 12
while time.monotonic() < deadline:
    try:
        connected = read("LOCAL:OBS:Input:pressure:Connected", timeout=1).data[0]
        if connected == 1:
            break
    except TimeoutError:
        pass
    time.sleep(0.1)
else:
    raise AssertionError("Observer never received a source sample")
first = read("LOCAL:OBS:Input:pressure:Value", timeout=2).data[0]
heartbeat = read("LOCAL:OBS:Heartbeat", timeout=2).data[0]
time.sleep(3.5)
assert read("LOCAL:OBS:Input:pressure:Value", timeout=2).data[0] > first
assert read("LOCAL:OBS:Heartbeat", timeout=2).data[0] > heartbeat
assert read("LOCAL:OBS:Input:pressure:Timestamp", timeout=2).data[0] > 0
def text(name):
    return bytes(read("LOCAL:OBS:" + name, timeout=2).data).decode().rstrip("\\x00")
assert text("Input:valve:State") == "Closed (assumed)"
assert read('LOCAL:OBS:Input:chamber_pressure:Value', timeout=2).data[0] == 810.0
assert text('Input:chamber_pressure:Text') == '8.1E+02'
assert text('Input:chamber_pressure:State') == 'Atmosphere (>700 mbar)'
source_time_label = text('Input:chamber_pressure:TimeText')
assert text('Input:valve:TimeText').startswith('Suspect IOC time | 1990-')
assert text('Input:valve:ReadAge') == 'just now'
assert text('Input:valve:ChangeAge').startswith('No change seen; baseline')
initial_read_time = read('LOCAL:OBS:Input:valve:ReadTime', timeout=2).data[0]
assert ' | ' in source_time_label and source_time_label.endswith(' UTC')
assert read('LOCAL:OBS:Storage:Seq-I', timeout=2).data[0] > 0
assert text('Storage:State-Sts') == 'Recording (SQLite WAL/FULL)'
assert text("Input:pressure:State") == "Above pump target"
assert text("ClosedWatch:Status").startswith("Rising")
assert read("LOCAL:OBS:ClosedWatch:Rate", timeout=2).data[0] > 0
assert read("LOCAL:OBS:ClosedWatch:Change", timeout=2).data[0] > 0
# A quiet source remains healthy through active liveness reads beyond stale_s.
time.sleep(3)
assert text("Input:valve:State") == "Closed (assumed)"
assert text('Input:chamber_pressure:TimeText') != source_time_label
assert read('LOCAL:OBS:Input:valve:ReadTime', timeout=2).data[0] > initial_read_time
assert read('LOCAL:OBS:Input:valve:ChangeTime', timeout=2).data[0] == 0
assert text('Input:valve:ReadAge') == 'just now'
assert read('LOCAL:OBS:Input:pressure:ChangeTime', timeout=2).data[0] > 0
"""
        proc = subprocess.Popen(
            [sys.executable, "-c", server], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        try:
            result = subprocess.run(
                [sys.executable, "-c", client], env=env, capture_output=True, timeout=20
            )
            assert result.returncode == 0, result.stderr.decode()
            # Verify actual server listening sockets, not just launcher arguments.
            inodes = {
                target[8:-1]
                for fd in Path(f"/proc/{proc.pid}/fd").iterdir()
                if (target := os.readlink(fd)).startswith("socket:[")
            }
            tcp = [line.split() for line in Path("/proc/net/tcp").read_text().splitlines()[1:]]
            listeners = [row for row in tcp if row[9] in inodes and row[3] == "0A"]
            assert listeners and all(row[1].startswith("0100007F:") for row in listeners)
            udp = [line.split() for line in Path("/proc/net/udp").read_text().splitlines()[1:]]
            servers = [row for row in udp if row[9] in inodes and row[1].endswith(f":{port:04X}")]
            assert servers and all(row[1].startswith("0100007F:") for row in servers)
        finally:
            proc.send_signal(signal.SIGINT)
            try:
                _, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                _, stderr = proc.communicate()
        assert b"Task was destroyed" not in stderr, stderr.decode()
        import json
        import sqlite3

        with sqlite3.connect(tmp_path / "beamtime.sqlite") as db:
            assert db.execute("SELECT count(*) FROM events").fetchone()[0] > 10
            assert db.execute("SELECT count(*) FROM snapshots").fetchone()[0] > 1
            assert db.execute("SELECT end_utc FROM sessions").fetchone()[0] is not None
            payload = json.loads(
                db.execute(
                    "SELECT payload FROM events WHERE name='chamber_pressure' "
                    "ORDER BY id DESC LIMIT 1"
                ).fetchone()[0]
            )
            assert payload["value"] == 810.0
            assert payload["text"] == "8.1E+02"
