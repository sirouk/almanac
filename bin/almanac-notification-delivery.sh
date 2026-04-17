#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

require_real_layout "notification delivery"
ensure_layout

export PYTHONPATH="$BOOTSTRAP_DIR/python${PYTHONPATH:+:$PYTHONPATH}"
PYTHON_BIN="$(resolve_runtime_python)"
exec "$PYTHON_BIN" "$BOOTSTRAP_DIR/python/almanac_notification_delivery.py" "$@"
