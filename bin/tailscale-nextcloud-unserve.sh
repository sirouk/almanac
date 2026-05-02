#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run this as root or with sudo."
  exit 1
fi

if ! command -v tailscale >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
  exit 0
fi

owned_config="$(
  tailscale serve status --json 2>/dev/null | python3 -c '
import json
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    raise SystemExit(0)

serve_port = str(sys.argv[1])
expected_root = sys.argv[2]
expected_qmd = sys.argv[3]
expected_path = sys.argv[4]
expected_arclink_mcp = sys.argv[5]
expected_arclink_mcp_path = sys.argv[6]
web = data.get("Web") or {}

for hostport, host_cfg in web.items():
    host, sep, port = hostport.rpartition(":")
    actual_port = port if sep and port.isdigit() else "443"
    if actual_port != serve_port:
        continue
    handlers = host_cfg.get("Handlers") or {}
    if set(handlers) != {"/", expected_path, expected_arclink_mcp_path}:
        raise SystemExit(0)
    root = handlers.get("/") or {}
    qmd = handlers.get(expected_path) or {}
    arclink_mcp = handlers.get(expected_arclink_mcp_path) or {}
    if (
        root.get("Proxy") == expected_root
        and qmd.get("Proxy") == expected_qmd
        and arclink_mcp.get("Proxy") == expected_arclink_mcp
    ):
        print("1")
' "${TAILSCALE_SERVE_PORT:-443}" "http://127.0.0.1:${NEXTCLOUD_PORT}" "http://127.0.0.1:${QMD_MCP_PORT}/mcp" "${TAILSCALE_QMD_PATH}" "http://127.0.0.1:${ARCLINK_MCP_PORT}/mcp" "${TAILSCALE_ARCLINK_MCP_PATH}" || true
)"

if [[ "$owned_config" == "1" ]]; then
  tailscale serve --yes --https="${TAILSCALE_SERVE_PORT:-443}" off >/dev/null 2>&1 || true
fi
