#!/usr/bin/env bash
set -euo pipefail

# Run with: bash /path/to/softioc/start-monitor.sh
# Storage defaults to /nsls2/data/smi/shared/config/kaptondb/history.sqlite.
# Provision the directory first. Use --init --window-id ID only on first creation.
APP_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
exec pixi run --manifest-path "$APP_DIR/pixi.toml" -e caproto smi-kapton-monitor \
    --config "$APP_DIR/config/commissioning.toml" "$@"
