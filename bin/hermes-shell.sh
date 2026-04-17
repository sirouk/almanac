#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

HERMES_BIN="$(require_runtime_hermes)"
exec "$HERMES_BIN" "$@"
