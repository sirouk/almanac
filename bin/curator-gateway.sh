#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

ensure_layout
if [[ ! -x "$RUNTIME_DIR/hermes-venv/bin/hermes" ]]; then
  echo "Hermes is not installed for curator at $RUNTIME_DIR/hermes-venv/bin/hermes" >&2
  exit 1
fi

export HERMES_HOME="$ALMANAC_CURATOR_HERMES_HOME"
mkdir -p "$HERMES_HOME"
exec "$RUNTIME_DIR/hermes-venv/bin/hermes" gateway
