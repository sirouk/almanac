#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"
export PYTHONPATH="$SCRIPT_DIR/../python${PYTHONPATH:+:$PYTHONPATH}"

PYTHON_BIN="$(require_runtime_python)"
exec "$PYTHON_BIN" "$SCRIPT_DIR/../python/almanac_curator_discord_onboarding.py" "$@"
