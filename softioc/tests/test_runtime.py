import logging
import os
import sqlite3

import pytest

from smi_window_tracker.beamtime import Store
from smi_window_tracker.runtime import (
    DEFAULT_DATABASE,
    configure_logging,
    log_epics_network_config,
    recorder_parser,
    server_environment,
)


def test_defaults_and_local_override():
    args = recorder_parser().parse_args(["--config", "config/commissioning.toml"])
    assert str(args.database) == "/nsls2/data/smi/shared/config/kaptondb/history.sqlite"
    assert args.database == DEFAULT_DATABASE and args.window_id is None and args.log_file is None
    assert args.mode == "softioc"
    args = recorder_parser().parse_args(["--config", "test.toml", "--database", "/tmp/test.sqlite"])
    assert str(args.database.parent / "kapton-monitor.log") == "/tmp/kapton-monitor.log"


def test_log_rotation(tmp_path):
    root = logging.getLogger()
    level = root.level
    handler = configure_logging(tmp_path / "kapton-monitor.log")
    try:
        assert handler.maxBytes == 10 * 1024 * 1024
        assert handler.backupCount == 5
        handler.maxBytes = 100
        for i in range(20):
            logging.info("test bounded logging entry %s %s", i, "x" * 80)
        assert len(list(tmp_path.glob("kapton-monitor.log*"))) <= 6
        assert "entry 19" in (tmp_path / "kapton-monitor.log").read_text()
    finally:
        root.removeHandler(handler)
        handler.close()
        root.setLevel(level)


def test_existing_wal_database_converts_without_reset(tmp_path):
    path = tmp_path / "history.sqlite"
    store = Store(path, "installed", "config", create=True)
    store.commit([], [], {"counts": [1, 2, 3, 4]})
    store.close()
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    db.close()
    store = Store(path, None, "config")
    assert store.db.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    assert store.db.execute("PRAGMA synchronous").fetchone()[0] == 2
    assert store.restored["counts"] == [1, 2, 3, 4]
    store.close()


@pytest.mark.parametrize("mode", ["local", "softioc"])
def test_output_network_does_not_change_input_discovery(monkeypatch, mode):
    monkeypatch.setenv("EPICS_CA_ADDR_LIST", "192.0.2.10 192.0.2.11")
    monkeypatch.setenv("EPICS_CA_AUTO_ADDR_LIST", "YES")
    for key in (
        "EPICS_CAS_AUTO_BEACON_ADDR_LIST",
        "EPICS_CAS_BEACON_ADDR_LIST",
        "EPICS_CAS_INTF_ADDR_LIST",
        "EPICS_CAS_SERVER_PORT",
    ):
        monkeypatch.setenv(key, "inherited")
    command = ["--config", "test.toml", "--mode", mode, "--server-port", "15064"]
    if mode == "softioc":
        command += [
            "--interface",
            "192.0.2.20",
            "--beacon-address",
            "192.0.2.255",
            "--beacon-address",
            "192.0.2.30:15065",
        ]
    interfaces = server_environment(recorder_parser().parse_args(command))
    assert interfaces == (["127.0.0.1"] if mode == "local" else ["192.0.2.20"])
    assert os.environ["EPICS_CAS_INTF_ADDR_LIST"] == interfaces[0]
    assert os.environ["EPICS_CAS_AUTO_BEACON_ADDR_LIST"] == "NO"
    assert os.environ["EPICS_CAS_SERVER_PORT"] == "15064"
    assert os.environ["EPICS_CAS_BEACON_ADDR_LIST"] == (
        "127.0.0.1" if mode == "local" else "192.0.2.255 192.0.2.30:15065"
    )
    assert os.environ["EPICS_CA_ADDR_LIST"] == "192.0.2.10 192.0.2.11"
    assert os.environ["EPICS_CA_AUTO_ADDR_LIST"] == "YES"


@pytest.mark.parametrize(
    "flags",
    [
        ["--mode", "local", "--interface", "192.0.2.20"],
        ["--mode", "local", "--server-port", "0"],
        ["--interface", "0.0.0.0", "--beacon-address", "192.0.2.255"],
        ["--interface", "192.0.2.20", "--beacon-address", "192.0.2.255:bad"],
        ["--interface", "not-an-ip", "--beacon-address", "192.0.2.255"],
    ],
)
def test_invalid_network_arguments(flags):
    with pytest.raises(ValueError):
        server_environment(recorder_parser().parse_args(["--config", "test.toml", *flags]))


def test_softioc_inherits_site_environment_without_rewriting(monkeypatch):
    settings = {
        "EPICS_CA_ADDR_LIST": "site-gateway",
        "EPICS_CAS_INTF_ADDR_LIST": "192.0.2.20 127.0.0.1",
        "EPICS_CAS_BEACON_ADDR_LIST": "192.0.2.255",
        "EPICS_CAS_AUTO_BEACON_ADDR_LIST": "YES",
        "EPICS_CAS_SERVER_PORT": "15064",
    }
    for key, value in settings.items():
        monkeypatch.setenv(key, value)
    args = recorder_parser().parse_args(["--config", "test.toml"])
    assert server_environment(args) is None
    assert {key: os.environ[key] for key in settings} == settings


def test_cli_only_overrides_requested_settings(monkeypatch):
    monkeypatch.setenv("EPICS_CAS_SERVER_PORT", "15064")
    monkeypatch.setenv("EPICS_CAS_AUTO_BEACON_ADDR_LIST", "YES")
    monkeypatch.setenv("EPICS_CAS_BEACON_ADDR_LIST", "192.0.2.255")
    args = recorder_parser().parse_args(["--config", "test.toml", "--interface", "192.0.2.20"])
    assert server_environment(args) == ["192.0.2.20"]
    assert os.environ["EPICS_CAS_AUTO_BEACON_ADDR_LIST"] == "YES"
    assert os.environ["EPICS_CAS_BEACON_ADDR_LIST"] == "192.0.2.255"
    assert os.environ["EPICS_CAS_SERVER_PORT"] == "15064"
    args = recorder_parser().parse_args(["--config", "test.toml", "--beacon-address", "192.0.2.30"])
    assert server_environment(args) is None
    assert os.environ["EPICS_CAS_AUTO_BEACON_ADDR_LIST"] == "NO"
    assert os.environ["EPICS_CAS_BEACON_ADDR_LIST"] == "192.0.2.30"


def test_network_logging_includes_input_settings_and_resolved_interfaces(monkeypatch, caplog):
    monkeypatch.setenv("EPICS_CA_ADDR_LIST", "192.0.2.10")
    monkeypatch.delenv("EPICS_CAS_SERVER_PORT", raising=False)
    log_epics_network_config({"interfaces": ["192.0.2.20"]})
    assert "EPICS_CA_ADDR_LIST=192.0.2.10" in caplog.text
    assert "EPICS_CAS_SERVER_PORT=<unset; caproto default>" in caplog.text
    assert "caproto server interfaces=['192.0.2.20']" in caplog.text
