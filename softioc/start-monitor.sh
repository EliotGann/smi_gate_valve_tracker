#!/usr/bin/env bash
set -euo pipefail

# Network IOC: bash start-monitor.sh (inherits the site's EPICS_CA_* / EPICS_CAS_*)
# Local test: bash start-monitor.sh --mode local --database /local/path/history.sqlite
# Storage defaults to /nsls2/data/smi/shared/config/kaptondb/history.sqlite.
# Provision the directory first. Use --init --window-id ID only on first creation.
APP_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
exec pixi run --locked --manifest-path "$APP_DIR/pixi.toml" -e caproto smi-kapton-monitor \
    --config "$APP_DIR/config/commissioning.toml" "$@"
