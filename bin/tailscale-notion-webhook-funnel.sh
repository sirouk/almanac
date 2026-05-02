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

tailscale_command_timeout_duration() {
  local requested="${1:-60s}"

  awk -v requested="$requested" '
    BEGIN {
      if (requested == "") {
        requested = "60s"
      }
      if (requested !~ /^([0-9]+(\.[0-9]+)?|\.[0-9]+)[smhd]?$/) {
        print requested
        exit
      }
      unit = substr(requested, length(requested), 1)
      seconds = requested + 0
      if (unit == "m") {
        seconds *= 60
      } else if (unit == "h") {
        seconds *= 3600
      } else if (unit == "d") {
        seconds *= 86400
      }
      print (seconds < 1 ? "1s" : requested)
    }
  '
}

maybe_wait_for_tailscale_funnel_enablement() {
  local output="${1:-}"
  local enable_url=""

  enable_url="$(extract_tailscale_enable_url "$output")"
  if [[ -z "$enable_url" ]]; then
    return 1
  fi

  printf '%s\n' "$output" >&2
  echo >&2
  echo "Tailscale Funnel is not enabled for this tailnet/node yet." >&2
  echo "Open this approval URL as a tailnet admin:" >&2
  echo "  $enable_url" >&2
  echo "This public Funnel is only for the Notion webhook; Nextcloud and MCP stay tailnet-only through Tailscale Serve." >&2
  echo "If the approval page asks for DNS prerequisites, enable MagicDNS and HTTPS Certificates at:" >&2
  echo "  https://login.tailscale.com/admin/dns" >&2
  echo "Press ENTER after enabling Tailscale Funnel to retry, or Ctrl+C to stop." >&2
  if [[ "${ARCLINK_TAILSCALE_INTERACTIVE_ENABLE:-1}" == "1" && -t 0 ]]; then
    read -r -p "> "
    return 0
  fi
  echo "After enabling Funnel, rerun ./deploy.sh install." >&2
  return 1
}

run_funnel_cmd() {
  local output=""
  local status=0
  local _attempt=""
  local timeout_duration="${ARCLINK_TAILSCALE_COMMAND_TIMEOUT:-60s}"
  local command_timeout_duration=""

  command_timeout_duration="$(tailscale_command_timeout_duration "$timeout_duration")"

  for _attempt in 1 2 3 4 5; do
    if command -v timeout >/dev/null 2>&1; then
      output="$(timeout --kill-after=5s "$command_timeout_duration" "$@" 2>&1)" && status=0 || status=$?
    else
      output="$("$@" 2>&1)" && status=0 || status=$?
    fi
    if [[ "$status" -eq 0 ]]; then
      [[ -n "$output" ]] && printf '%s\n' "$output"
      return 0
    fi

    if [[ "$status" -eq 124 || "$status" -eq 137 ]]; then
      if maybe_wait_for_tailscale_funnel_enablement "$output"; then
        continue
      fi
      [[ -n "$output" ]] && printf '%s\n' "$output" >&2
      echo "tailscale funnel command did not complete within ${timeout_duration}." >&2
      echo "If Tailscale says Funnel is not enabled, open the printed https://login.tailscale.com/f/funnel?... URL as a tailnet admin." >&2
      echo "If it asks for DNS prerequisites, open https://login.tailscale.com/admin/dns in the same tailnet, enable MagicDNS and HTTPS Certificates, then rerun ./deploy.sh install." >&2
      return "$status"
    fi

    if printf '%s\n' "$output" | grep -Eqi 'etag mismatch|another client is changing the serve config|preconditions failed'; then
      sleep 1
      continue
    fi

    if maybe_wait_for_tailscale_funnel_enablement "$output"; then
      continue
    fi

    printf '%s\n' "$output" >&2
    return "$status"
  done

  printf '%s\n' "$output" >&2
  return 1
}

ensure_no_conflicting_funnel_service() {
  local ts_json=""
  local result=""

  ts_json="$(tailscale funnel status --json 2>/dev/null || true)"
  if [[ -z "$ts_json" ]]; then
    return 0
  fi

  result="$(
    TAILSCALE_FUNNEL_JSON="$ts_json" python3 - \
      "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-443}" \
      "${ARCLINK_NOTION_WEBHOOK_PORT:-8283}" <<'PY'
import json
import os
import sys

port = str(sys.argv[1])
backend_port = str(sys.argv[2])

try:
    data = json.loads(os.environ["TAILSCALE_FUNNEL_JSON"])
except Exception:
    raise SystemExit(0)

web = data.get("Web") or {}
allow = data.get("AllowFunnel") or {}
expected_proxy = f"http://127.0.0.1:{backend_port}"

for hostport, entry in web.items():
    if not hostport.endswith(f":{port}"):
        continue
    handlers = (entry or {}).get("Handlers") or {}
    if not handlers:
        continue
    owned = (
        len(handlers) == 1
        and "/" in handlers
        and (handlers.get("/") or {}).get("Proxy") == expected_proxy
        and bool(allow.get(hostport))
    )
    if owned:
        print("owned")
        raise SystemExit(0)
    paths = ",".join(sorted(handlers))
    print(f"conflict:{hostport}:{paths}")
    raise SystemExit(0)
PY
  )"

  if [[ "$result" == conflict:* ]]; then
    echo "tailscale Funnel port ${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-443} is already in use by another public service; refusing to overwrite it." >&2
    echo "$result" >&2
    exit 1
  fi
}

verify_funnel_config() {
  local ts_json=""

  ts_json="$(tailscale funnel status --json 2>/dev/null || true)"
  if [[ -z "$ts_json" ]]; then
    echo "tailscale funnel status returned no JSON." >&2
    return 1
  fi

  if TAILSCALE_FUNNEL_JSON="$ts_json" python3 - \
    "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-443}" \
    "${ARCLINK_NOTION_WEBHOOK_PORT:-8283}" <<'PY'
import json
import os
import sys

port = str(sys.argv[1])
backend_port = str(sys.argv[2])

try:
    data = json.loads(os.environ["TAILSCALE_FUNNEL_JSON"])
except Exception:
    raise SystemExit(1)

web = data.get("Web") or {}
allow = data.get("AllowFunnel") or {}
expected_proxy = f"http://127.0.0.1:{backend_port}"

for hostport, entry in web.items():
    if not hostport.endswith(f":{port}"):
        continue
    handlers = (entry or {}).get("Handlers") or {}
    if len(handlers) != 1:
        continue
    handler = handlers.get("/") or {}
    if handler.get("Proxy") != expected_proxy:
        continue
    if not allow.get(hostport):
        continue
    raise SystemExit(0)

raise SystemExit(1)
PY
  then
    return 0
  fi

  echo "tailscale Funnel does not expose only the expected Notion webhook route." >&2
  return 1
}

print_funnel_summary() {
  local status_text=""

  status_text="$(tailscale funnel status 2>/dev/null || true)"
  if [[ -n "$status_text" ]]; then
    printf '%s\n' "$status_text"
  fi
}

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run this as root or with sudo."
  exit 1
fi

if [[ "${ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL:-0}" != "1" ]]; then
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

detect_tailscale_runtime || {
  echo "tailscale DNS name could not be detected; cannot derive the public Notion webhook URL." >&2
  exit 1
}
ensure_no_conflicting_funnel_service
run_funnel_cmd tailscale funnel --yes --https="${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-443}" off >/dev/null 2>&1 || true
run_funnel_cmd tailscale funnel --bg --yes --https="${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-443}" "http://127.0.0.1:${ARCLINK_NOTION_WEBHOOK_PORT:-8283}" >/dev/null
verify_funnel_config
print_funnel_summary
