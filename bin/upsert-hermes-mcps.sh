#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <hermes-home>" >&2
  exit 2
fi

HERMES_HOME_TARGET="$1"
PYTHON_BIN="$(require_runtime_python)"
ARCLINK_MCP_URL="${ARCLINK_MCP_URL:-http://${ARCLINK_MCP_HOST:-127.0.0.1}:${ARCLINK_MCP_PORT:-8282}/mcp}"
ARCLINK_QMD_URL="${ARCLINK_QMD_URL:-http://127.0.0.1:${QMD_MCP_PORT:-8181}/mcp}"
ARCLINK_EXTRA_MCP_NAME="${ARCLINK_EXTRA_MCP_NAME:-external-kb}"
ARCLINK_EXTRA_MCP_URL="${ARCLINK_EXTRA_MCP_URL:-}"

HERMES_HOME="$HERMES_HOME_TARGET" \
ARCLINK_MCP_URL="$ARCLINK_MCP_URL" \
ARCLINK_QMD_URL="$ARCLINK_QMD_URL" \
ARCLINK_EXTRA_MCP_NAME="$ARCLINK_EXTRA_MCP_NAME" \
ARCLINK_EXTRA_MCP_URL="$ARCLINK_EXTRA_MCP_URL" \
"$PYTHON_BIN" - <<'PY'
import os

from hermes_cli.config import load_config, save_config


def upsert_http_server(mcp_servers: dict[str, object], *, name: str, url: str) -> None:
    server = mcp_servers.get(name)
    if not isinstance(server, dict):
        server = {}
    updated = dict(server)
    updated["url"] = url
    updated["enabled"] = True
    updated.setdefault("timeout", 120)
    updated.setdefault("connect_timeout", 60)
    mcp_servers[name] = updated


config = load_config()
mcp_servers = config.get("mcp_servers")
if not isinstance(mcp_servers, dict):
    mcp_servers = {}

upsert_http_server(mcp_servers, name="arclink-mcp", url=os.environ["ARCLINK_MCP_URL"])
upsert_http_server(mcp_servers, name="arclink-qmd", url=os.environ["ARCLINK_QMD_URL"])

extra_url = str(os.environ.get("ARCLINK_EXTRA_MCP_URL") or "").strip()
if extra_url:
    extra_name = str(os.environ.get("ARCLINK_EXTRA_MCP_NAME") or "external-kb").strip() or "external-kb"
    upsert_http_server(mcp_servers, name=extra_name, url=extra_url)

config["mcp_servers"] = mcp_servers
save_config(config)
PY
