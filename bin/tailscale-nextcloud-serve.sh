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

extract_tailscale_enable_url() {
  printf '%s\n' "${1:-}" \
    | grep -Eo 'https://login\.tailscale\.com/f/(serve|funnel)\?[^[:space:]]+' \
    | head -n 1 \
    | sed 's/[).,;]*$//' || true
}

maybe_wait_for_tailscale_serve_enablement() {
  local output="${1:-}"
  local enable_url=""
  local answer=""

  enable_url="$(extract_tailscale_enable_url "$output")"
  if [[ -z "$enable_url" ]]; then
    return 1
  fi

  printf '%s\n' "$output" >&2
  echo >&2
  echo "Tailscale Serve is not enabled for this tailnet/node yet." >&2
  echo "Open this approval URL as a tailnet admin:" >&2
  echo "  $enable_url" >&2
  echo "This Serve route is tailnet-only for Nextcloud and internal MCP routes." >&2
  echo "If the approval page asks for DNS prerequisites, enable MagicDNS and HTTPS Certificates at:" >&2
  echo "  https://login.tailscale.com/admin/dns" >&2
  echo "Press ENTER after enabling Tailscale Serve to retry, or Ctrl+C to stop." >&2
  if [[ "${ALMANAC_TAILSCALE_INTERACTIVE_ENABLE:-1}" == "1" && -t 0 ]]; then
    read -r -p "> " answer
    return 0
  fi
  echo "After enabling Serve, rerun ./deploy.sh install." >&2
  return 1
}

run_serve_cmd() {
  local output=""
  local status=0
  local attempt=0
  local timeout_duration="${ALMANAC_TAILSCALE_COMMAND_TIMEOUT:-60s}"

  for attempt in 1 2 3 4 5; do
    if command -v timeout >/dev/null 2>&1; then
      output="$(timeout --kill-after=5s "$timeout_duration" "$@" 2>&1)" && status=0 || status=$?
    else
      output="$("$@" 2>&1)" && status=0 || status=$?
    fi
    if [[ "$status" -eq 0 ]]; then
      return 0
    fi

    if [[ "$status" -eq 124 || "$status" -eq 137 ]]; then
      if maybe_wait_for_tailscale_serve_enablement "$output"; then
        continue
      fi
      [[ -n "$output" ]] && printf '%s\n' "$output" >&2
      echo "tailscale serve command did not complete within ${timeout_duration}." >&2
      echo "If Tailscale says Serve is not enabled, open the printed https://login.tailscale.com/f/serve?... URL as a tailnet admin." >&2
      echo "If it asks for DNS prerequisites, open https://login.tailscale.com/admin/dns in the same tailnet, enable MagicDNS and HTTPS Certificates, then rerun ./deploy.sh install." >&2
      return "$status"
    fi

    if printf '%s\n' "$output" | grep -Eqi 'etag mismatch|another client is changing the serve config|preconditions failed'; then
      sleep 1
      continue
    fi

    if maybe_wait_for_tailscale_serve_enablement "$output"; then
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

  if TAILSCALE_SERVE_JSON="$ts_json" python3 - "${TAILSCALE_SERVE_PORT:-443}" "http://127.0.0.1:${NEXTCLOUD_PORT}" "http://127.0.0.1:${QMD_MCP_PORT}/mcp" "${TAILSCALE_QMD_PATH}" "http://127.0.0.1:${ALMANAC_MCP_PORT}/mcp" "${TAILSCALE_ALMANAC_MCP_PATH}" <<'PY'
import json
import os
import sys

serve_port = str(sys.argv[1])
expected_root = sys.argv[2]
expected_qmd = sys.argv[3]
expected_path = sys.argv[4]
expected_almanac_mcp = sys.argv[5]
expected_almanac_mcp_path = sys.argv[6]

try:
    data = json.loads(os.environ["TAILSCALE_SERVE_JSON"])
except Exception:
    raise SystemExit(1)

web = data.get("Web") or {}

for hostport, host_cfg in web.items():
    host, sep, port = hostport.rpartition(":")
    actual_port = port if sep and port.isdigit() else "443"
    if actual_port != serve_port:
        continue
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

run_serve_cmd tailscale serve --bg --yes --https="${TAILSCALE_SERVE_PORT:-443}" "http://127.0.0.1:${NEXTCLOUD_PORT}"
run_serve_cmd tailscale serve --bg --yes --https="${TAILSCALE_SERVE_PORT:-443}" --set-path "${TAILSCALE_QMD_PATH}" "http://127.0.0.1:${QMD_MCP_PORT}/mcp"
run_serve_cmd tailscale serve --bg --yes --https="${TAILSCALE_SERVE_PORT:-443}" --set-path "${TAILSCALE_ALMANAC_MCP_PATH}" "http://127.0.0.1:${ALMANAC_MCP_PORT}/mcp"
verify_serve_config
print_serve_summary
