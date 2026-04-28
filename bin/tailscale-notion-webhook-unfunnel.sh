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
  tailscale funnel status --json 2>/dev/null | python3 - \
    "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-8443}" \
    "${ALMANAC_NOTION_WEBHOOK_PORT:-8283}" <<'PY'
import json
import sys

port = str(sys.argv[1])
backend_port = str(sys.argv[2])

try:
    data = json.load(sys.stdin)
except Exception:
    raise SystemExit(0)

web = data.get("Web") or {}
allow = data.get("AllowFunnel") or {}
expected_proxy = f"http://127.0.0.1:{backend_port}"

for hostport, entry in web.items():
    if not hostport.endswith(f":{port}"):
        continue
    handlers = (entry or {}).get("Handlers") or {}
    if (
        len(handlers) == 1
        and "/" in handlers
        and (handlers.get("/") or {}).get("Proxy") == expected_proxy
        and bool(allow.get(hostport))
    ):
        print("1")
        raise SystemExit(0)
PY
)"

if [[ "$owned_config" == "1" ]]; then
  tailscale funnel --yes --https="${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-8443}" off >/dev/null 2>&1 || true
fi
