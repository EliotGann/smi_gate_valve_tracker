"""Deployment paths and bounded process logging."""

import argparse
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

DEFAULT_DIRECTORY = Path("/nsls2/data/smi/shared/config/kaptondb")
DEFAULT_DATABASE = DEFAULT_DIRECTORY / "history.sqlite"


def recorder_parser():
    parser = argparse.ArgumentParser(description="Local-only KaptonMon beamtime recorder")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help=f"Persistent history (default: {DEFAULT_DATABASE})",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Rotating application log (default: kapton-monitor.log beside database)",
    )
    parser.add_argument("--window-id", help="Required for --init; omit to resume active window")
    parser.add_argument("--init", action="store_true", help="Create database; fails if it exists")
    parser.add_argument(
        "--accept-config-change",
        action="store_true",
        help="Record a config epoch and preserve existing totals",
    )
    return parser


def configure_logging(path):
    """Up to 10 MiB current + five rotated files; caller provisions directory."""
    handler = RotatingFileHandler(path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)
    return handler
