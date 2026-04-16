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

expected_root = sys.argv[1]
expected_qmd = sys.argv[2]
expected_path = sys.argv[3]
web = data.get("Web") or {}

if len(web) != 1:
    raise SystemExit(0)

for host_cfg in web.values():
    handlers = host_cfg.get("Handlers") or {}
    if set(handlers) != {"/", expected_path}:
        raise SystemExit(0)
    root = handlers.get("/") or {}
    qmd = handlers.get(expected_path) or {}
    if root.get("Proxy") == expected_root and qmd.get("Proxy") == expected_qmd:
        print("1")
' "http://127.0.0.1:${NEXTCLOUD_PORT}" "http://127.0.0.1:${QMD_MCP_PORT}/mcp" "${TAILSCALE_QMD_PATH}" || true
)"

if [[ "$owned_config" == "1" ]]; then
  tailscale serve reset >/dev/null 2>&1 || true
fi
