#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

require_real_layout "ArcLink Wrapped"
ensure_layout

export PYTHONPATH="$BOOTSTRAP_DIR/python${PYTHONPATH:+:$PYTHONPATH}"
PYTHON_BIN="$(require_runtime_python)"
exec "$PYTHON_BIN" "$BOOTSTRAP_DIR/python/arclink_wrapped.py" "$@"
