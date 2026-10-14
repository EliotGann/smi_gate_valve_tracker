import logging
import sqlite3

from smi_window_tracker.beamtime import Store
from smi_window_tracker.runtime import DEFAULT_DATABASE, configure_logging, recorder_parser


def test_defaults_and_local_override():
    args = recorder_parser().parse_args(["--config", "config/commissioning.toml"])
    assert str(args.database) == "/nsls2/data/smi/shared/config/kaptondb/history.sqlite"
    assert args.database == DEFAULT_DATABASE and args.window_id is None and args.log_file is None
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
