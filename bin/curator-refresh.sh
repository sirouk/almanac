#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

export PYTHONPATH="$BOOTSTRAP_DIR/python${PYTHONPATH:+:$PYTHONPATH}"
PYTHON_BIN="$(require_runtime_python)"
exec "$PYTHON_BIN" "$BOOTSTRAP_DIR/python/almanac_ctl.py" internal curator-refresh
