#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

require_real_layout "notion webhook startup"
ensure_layout

export PYTHONPATH="$BOOTSTRAP_DIR/python${PYTHONPATH:+:$PYTHONPATH}"
PYTHON_BIN="$(require_runtime_python)"

have_host_arg() {
  local arg=""
  for arg in "$@"; do
    case "$arg" in
      --host|--host=*)
        return 0
        ;;
    esac
  done
  return 1
}

if ! have_host_arg "$@"; then
  set -- --host 127.0.0.1 "$@"
fi

exec "$PYTHON_BIN" "$BOOTSTRAP_DIR/python/arclink_notion_webhook.py" "$@"
