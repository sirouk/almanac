#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

require_real_layout "notion webhook startup"
ensure_layout

export PYTHONPATH="$BOOTSTRAP_DIR/python${PYTHONPATH:+:$PYTHONPATH}"
PYTHON_BIN="$(require_runtime_python)"
exec "$PYTHON_BIN" "$BOOTSTRAP_DIR/python/almanac_notion_webhook.py" "$@"
