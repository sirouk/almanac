#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

require_real_layout "qmd shell access"
ensure_nvm
exec qmd --index "$QMD_INDEX_NAME" "$@"
