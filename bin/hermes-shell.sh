#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

HERMES_BIN="$(require_runtime_hermes)"
if [[ -d "$RUNTIME_DIR/hermes-agent-src/skills" ]]; then
  export HERMES_BUNDLED_SKILLS="${HERMES_BUNDLED_SKILLS:-$RUNTIME_DIR/hermes-agent-src/skills}"
fi
exec "$HERMES_BIN" "$@"
