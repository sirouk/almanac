#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

require_real_layout "qmd daemon startup"
ensure_nvm
mkdir -p "$(dirname "$QMD_INDEX_DB_PATH")"
exec qmd --index "$QMD_INDEX_NAME" mcp --http --port "$QMD_MCP_PORT"
