#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

detect_tailscale_runtime() {
  TAILSCALE_DNS_NAME=""

  if ! command -v tailscale >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
    return 1
  fi

  local ts_json=""
  ts_json="$(tailscale status --json 2>/dev/null || true)"
  if [[ -z "$ts_json" ]]; then
    return 1
  fi

  TAILSCALE_DNS_NAME="$(
    printf '%s' "$ts_json" | python3 -c '
import json
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    raise SystemExit(0)

self_info = data.get("Self") or {}
dns = (self_info.get("DNSName") or "").rstrip(".")
if dns:
    print(dns)
' || true
  )"

  [[ -n "$TAILSCALE_DNS_NAME" ]]
}

run_serve_cmd() {
  local output=""
  local status=0
  local attempt=0

  for attempt in 1 2 3 4 5; do
    output="$("$@" 2>&1)" && status=0 || status=$?
    if [[ "$status" -eq 0 ]]; then
      return 0
    fi

    if printf '%s\n' "$output" | grep -Eqi 'etag mismatch|another client is changing the serve config|preconditions failed'; then
      sleep 1
      continue
    fi

    printf '%s\n' "$output" >&2
    return "$status"
  done

  printf '%s\n' "$output" >&2
  return 1
}

print_serve_summary() {
  local status_text=""

  status_text="$(tailscale serve status 2>/dev/null || true)"
  if [[ -n "$status_text" ]]; then
    printf '%s\n' "$status_text"
  fi
}

verify_serve_config() {
  local ts_json=""

  ts_json="$(tailscale serve status --json 2>/dev/null || true)"
  if [[ -z "$ts_json" ]]; then
    echo "tailscale serve status returned no JSON." >&2
    return 1
  fi

  if TAILSCALE_SERVE_JSON="$ts_json" python3 - "http://127.0.0.1:${NEXTCLOUD_PORT}" "http://127.0.0.1:${QMD_MCP_PORT}/mcp" "${TAILSCALE_QMD_PATH}" "http://127.0.0.1:${ALMANAC_MCP_PORT}/mcp" "${TAILSCALE_ALMANAC_MCP_PATH}" <<'PY'
import json
import os
import sys

expected_root = sys.argv[1]
expected_qmd = sys.argv[2]
expected_path = sys.argv[3]
expected_almanac_mcp = sys.argv[4]
expected_almanac_mcp_path = sys.argv[5]

try:
    data = json.loads(os.environ["TAILSCALE_SERVE_JSON"])
except Exception:
    raise SystemExit(1)

web = data.get("Web") or {}

for host_cfg in web.values():
    handlers = host_cfg.get("Handlers") or {}
    root = handlers.get("/") or {}
    qmd = handlers.get(expected_path) or {}
    almanac_mcp = handlers.get(expected_almanac_mcp_path) or {}
    if (
        root.get("Proxy") == expected_root
        and qmd.get("Proxy") == expected_qmd
        and almanac_mcp.get("Proxy") == expected_almanac_mcp
    ):
        raise SystemExit(0)

raise SystemExit(1)
PY
  then
    return 0
  fi

  echo "tailscale serve config does not expose Nextcloud, qmd MCP, and Almanac MCP as expected." >&2
  return 1
}

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run this as root or with sudo."
  exit 1
fi

if [[ "$ENABLE_NEXTCLOUD" != "1" || "$ENABLE_TAILSCALE_SERVE" != "1" ]]; then
  exit 0
fi

if ! command -v tailscale >/dev/null 2>&1; then
  echo "tailscale is not installed."
  exit 1
fi

if ! tailscale status --json >/dev/null 2>&1; then
  echo "tailscale is not running."
  exit 1
fi

detect_tailscale_runtime || true

run_serve_cmd tailscale serve --bg --yes "http://127.0.0.1:${NEXTCLOUD_PORT}"
run_serve_cmd tailscale serve --bg --yes --set-path "${TAILSCALE_QMD_PATH}" "http://127.0.0.1:${QMD_MCP_PORT}/mcp"
run_serve_cmd tailscale serve --bg --yes --set-path "${TAILSCALE_ALMANAC_MCP_PATH}" "http://127.0.0.1:${ALMANAC_MCP_PORT}/mcp"
verify_serve_config
print_serve_summary
