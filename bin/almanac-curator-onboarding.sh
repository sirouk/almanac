#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"
export PYTHONPATH="$SCRIPT_DIR/../python${PYTHONPATH:+:$PYTHONPATH}"

PYTHON_BIN="$RUNTIME_DIR/hermes-venv/bin/python3"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/../python/almanac_curator_onboarding.py" "$@"
