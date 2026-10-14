"""Deployment paths and bounded process logging."""

import argparse
import ipaddress
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

DEFAULT_DIRECTORY = Path("/nsls2/data/smi/shared/config/kaptondb")
DEFAULT_DATABASE = DEFAULT_DIRECTORY / "history.sqlite"


def recorder_parser():
    parser = argparse.ArgumentParser(description="KaptonMon soft IOC and local test recorder")
    parser.add_argument("--config", type=Path, required=True)
    add_network_arguments(parser)
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


def add_network_arguments(parser, *, default_mode="softioc"):
    parser.add_argument(
        "--mode",
        choices=("softioc", "local"),
        default=default_mode,
        help=f"Output CA serving mode (default: {default_mode})",
    )
    parser.add_argument(
        "--interface",
        action="append",
        default=[],
        metavar="IP",
        help="Override EPICS_CAS_INTF_ADDR_LIST; repeat for multiple interfaces",
    )
    parser.add_argument(
        "--beacon-address",
        action="append",
        default=[],
        metavar="IP[:PORT]",
        help="Override EPICS_CAS_BEACON_ADDR_LIST and disable automatic beacons",
    )
    parser.add_argument(
        "--server-port",
        type=int,
        default=None,
        help="Override EPICS_CAS_SERVER_PORT (caproto default: 5064); inputs unchanged",
    )


def server_environment(args):
    """Configure only output CA settings, never EPICS_CA_* source discovery.

    Softioc mode inherits site EPICS settings and caproto defaults unless a CLI
    override is supplied. Returning None lets caproto resolve its normal interface
    list from EPICS_CAS_INTF_ADDR_LIST. Local mode always forces loopback.
    """
    if args.server_port is not None and not 1 <= args.server_port <= 65535:
        raise ValueError("--server-port must be between 1 and 65535")
    if args.mode == "local":
        if args.interface or args.beacon_address:
            raise ValueError("--interface/--beacon-address apply only to --mode softioc")
        interfaces, beacons = ["127.0.0.1"], ["127.0.0.1"]
        os.environ["EPICS_CAS_AUTO_BEACON_ADDR_LIST"] = "NO"
        os.environ["EPICS_CAS_BEACON_ADDR_LIST"] = " ".join(beacons)
        os.environ["EPICS_CAS_INTF_ADDR_LIST"] = " ".join(interfaces)
    else:
        interfaces, beacons = args.interface, args.beacon_address
        for address in interfaces:
            ip = ipaddress.IPv4Address(address)
            if ip.is_unspecified or ip.is_multicast or address == "255.255.255.255":
                raise ValueError("Bind a specific unicast IPv4 interface, not a wildcard/broadcast")
        for address in beacons:
            host, _, port = address.partition(":")
            ipaddress.IPv4Address(host)
            if ":" in address and (not port.isdigit() or not 1 <= int(port) <= 65535):
                raise ValueError("Beacon port must be between 1 and 65535")
        if interfaces:
            os.environ["EPICS_CAS_INTF_ADDR_LIST"] = " ".join(interfaces)
        if beacons:
            os.environ["EPICS_CAS_AUTO_BEACON_ADDR_LIST"] = "NO"
            os.environ["EPICS_CAS_BEACON_ADDR_LIST"] = " ".join(beacons)
    if args.server_port is not None:
        os.environ["EPICS_CAS_SERVER_PORT"] = str(args.server_port)
    return interfaces or None


def log_epics_network_config(run_options: dict):
    """Report the inherited/overridden environment and actual server bind list."""
    log = logging.getLogger(__name__)
    for name in (
        "EPICS_CA_AUTO_ADDR_LIST",
        "EPICS_CA_ADDR_LIST",
        "EPICS_CA_SERVER_PORT",
        "EPICS_CA_REPEATER_PORT",
        "EPICS_CAS_AUTO_BEACON_ADDR_LIST",
        "EPICS_CAS_BEACON_ADDR_LIST",
        "EPICS_CAS_INTF_ADDR_LIST",
        "EPICS_CAS_SERVER_PORT",
    ):
        log.warning("%s=%s", name, os.environ.get(name, "<unset; caproto default>"))
    log.warning("caproto server interfaces=%s", run_options.get("interfaces"))


def configure_logging(path):
    """Up to 10 MiB current + five rotated files; caller provisions directory."""
    handler = RotatingFileHandler(path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)
    return handler
