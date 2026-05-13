#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
STRICT_MODE="${ARCLINK_HEALTH_STRICT:-0}"

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  printf '[ok]   %s\n' "$1"
}

warn() {
  WARN_COUNT=$((WARN_COUNT + 1))
  printf '[warn] %s\n' "$1"
}

fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  printf '[fail] %s\n' "$1"
}

warn_or_fail() {
  local message="$1"

  if [[ "$STRICT_MODE" == "1" ]]; then
    fail "$message"
  else
    warn "$message"
  fi
}

summarize_failed_units() {
  sed -E 's/[[:space:]]+/ /g' | head -5 | paste -sd '; ' -
}

failed_units_are_stale_podman_healthchecks() {
  local output="${1:-}"
  [[ -n "$output" ]] || return 1
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    [[ "$line" == *"/usr/bin/podman healthcheck"* ]] || return 1
  done <<<"$output"
}

check_system_failed_units() {
  local output=""
  if ! command -v systemctl >/dev/null 2>&1; then
    return 0
  fi
  output="$(systemctl --failed --no-legend --plain 2>/dev/null || true)"
  if [[ -z "$output" ]]; then
    pass "no failed system units"
  else
    warn_or_fail "failed system units present: $(printf '%s\n' "$output" | summarize_failed_units)"
  fi
}

check_service_user_failed_units() {
  local output="" after_reset=""
  if ! command -v systemctl >/dev/null 2>&1; then
    return 0
  fi
  output="$(systemctl --user --failed --no-legend --plain 2>/dev/null || true)"
  if [[ -z "$output" ]]; then
    pass "no failed service-user units"
    return 0
  fi
  if failed_units_are_stale_podman_healthchecks "$output"; then
    systemctl --user reset-failed >/dev/null 2>&1 || true
    after_reset="$(systemctl --user --failed --no-legend --plain 2>/dev/null || true)"
    if [[ -z "$after_reset" ]]; then
      pass "cleared stale Podman healthcheck transient failures"
      return 0
    fi
    output="$after_reset"
  fi
  warn_or_fail "failed service-user units present: $(printf '%s\n' "$output" | summarize_failed_units)"
}

trim_secret_marker() {
  local value="${1:-}"

  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

is_placeholder_secret() {
  local value=""

  value="$(trim_secret_marker "${1:-}")"
  case "$(lowercase "$value")" in
    change-me|changeme|generated-at-deploy)
      return 0
      ;;
  esac

  return 1
}

check_placeholder_secrets() {
  if [[ "$ENABLE_NEXTCLOUD" != "1" ]]; then
    return 0
  fi

  if is_placeholder_secret "${POSTGRES_PASSWORD:-}"; then
    warn "POSTGRES_PASSWORD still uses a placeholder secret; rotate it deliberately for the live Nextcloud database with ./deploy.sh rotate-nextcloud-secrets"
  else
    pass "POSTGRES_PASSWORD is not a placeholder secret"
  fi

  if is_placeholder_secret "${NEXTCLOUD_ADMIN_PASSWORD:-}"; then
    warn "NEXTCLOUD_ADMIN_PASSWORD still uses a placeholder secret; rotate the live Nextcloud admin credential with ./deploy.sh rotate-nextcloud-secrets"
  else
    pass "NEXTCLOUD_ADMIN_PASSWORD is not a placeholder secret"
  fi
}

check_curator_gateway_runtime() {
  local output=""
  local status=0
  local runtime_channels="${ARCLINK_CURATOR_CHANNELS:-tui-only}"
  local channel=""
  local filtered_channels=()

  if has_curator_telegram_onboarding; then
    pass "Curator Telegram onboarding owns the Telegram worker"
  fi
  if has_curator_discord_onboarding; then
    pass "Curator Discord onboarding owns the Discord worker"
  fi
  if has_curator_onboarding; then
    if ! has_curator_non_onboarding_gateway_channels; then
      return 0
    fi
    IFS=',' read -r -a filtered_channels <<<"$runtime_channels"
    runtime_channels=""
    for channel in "${filtered_channels[@]}"; do
      channel="${channel//[[:space:]]/}"
      [[ -z "$channel" || "$channel" == "tui-only" ]] && continue
      if [[ "$channel" == "telegram" && "${ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED:-0}" == "1" ]]; then
        continue
      fi
      if [[ "$channel" == "discord" && "${ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED:-0}" == "1" ]]; then
        continue
      fi
      runtime_channels="${runtime_channels:+$runtime_channels,}$channel"
    done
  fi

  if ! has_curator_gateway_channels; then
    return 0
  fi

  if [[ ! -x "$RUNTIME_DIR/hermes-venv/bin/python3" ]]; then
    warn_or_fail "shared Hermes runtime python is missing at $RUNTIME_DIR/hermes-venv/bin/python3"
    return 0
  fi

  if output="$("$RUNTIME_DIR/hermes-venv/bin/python3" - "$runtime_channels" "$RUNTIME_DIR" <<'PY'
import pathlib
import sys

channels = [item.strip() for item in sys.argv[1].split(",") if item.strip()]
runtime_dir = pathlib.Path(sys.argv[2]).resolve()
missing = []

try:
    import hermes_cli  # noqa: F401
except Exception:
    missing.append("hermes-cli runtime package")
else:
    hermes_path = pathlib.Path(hermes_cli.__file__).resolve()
    if not hermes_path.is_relative_to(runtime_dir):
        print(f"Curator runtime is importing Hermes from outside ArcLink runtime: {hermes_path}")
        raise SystemExit(3)
    print(f"Curator runtime imports Hermes from {hermes_path}")

if "telegram" in channels:
    try:
        import telegram  # noqa: F401
    except Exception:
        missing.append("telegram -> python-telegram-bot[webhooks]")

if "discord" in channels:
    try:
        import discord  # noqa: F401
    except Exception:
        missing.append("discord -> discord.py[voice]")

if missing:
    print("Curator gateway runtime is missing adapter dependencies: " + ", ".join(missing))
    raise SystemExit(2)

print("Curator gateway runtime dependencies are installed for configured channels")
PY
  )"; then
    while IFS= read -r line; do
      [[ -n "$line" ]] && pass "$line"
    done <<<"$output"
  else
    status=$?
    case "$status" in
      2)
        while IFS= read -r line; do
          [[ -n "$line" ]] && warn_or_fail "$line"
        done <<<"$output"
        ;;
      3)
        while IFS= read -r line; do
          [[ -n "$line" ]] && warn_or_fail "$line"
        done <<<"$output"
        ;;
      *)
        warn_or_fail "could not verify Curator gateway runtime dependencies"
        ;;
    esac
  fi
}

check_unit_state() {
  local unit="$1"
  local expect="$2"
  local state=""

  state="$(systemctl --user is-active "$unit" 2>/dev/null || true)"

  case "$state" in
    active)
      pass "$unit is active"
      ;;
    activating|reloading)
      warn "$unit is $state"
      ;;
    *)
      if [[ "$expect" == "required" ]]; then
        fail "$unit is ${state:-unknown}"
      else
        warn "$unit is ${state:-unknown}"
      fi
      ;;
  esac
}

check_system_unit_state() {
  local unit="$1"
  local expect="$2"
  local state=""

  state="$(systemctl is-active "$unit" 2>/dev/null || true)"

  case "$state" in
    active)
      pass "$unit is active"
      ;;
    activating|reloading)
      warn "$unit is $state"
      ;;
    *)
      if [[ "$expect" == "required" ]]; then
        fail "$unit is ${state:-unknown}"
      else
        warn "$unit is ${state:-unknown}"
      fi
      ;;
  esac
}

check_user_timer_job_result() {
  local unit="$1"
  local expect="$2"
  local result=""
  local active_state=""
  local sub_state=""
  local state_label=""
  local message=""

  result="$(systemctl --user show "$unit" --property=Result --value 2>/dev/null || true)"
  active_state="$(systemctl --user show "$unit" --property=ActiveState --value 2>/dev/null || true)"
  sub_state="$(systemctl --user show "$unit" --property=SubState --value 2>/dev/null || true)"

  state_label="${active_state:-unknown}"
  if [[ -n "$sub_state" ]]; then
    state_label="$state_label/$sub_state"
  fi

  case "$active_state" in
    activating|deactivating|reloading)
      warn "$unit last result is ${result:-unknown} while state is $state_label"
      return 0
      ;;
  esac

  case "$result" in
    success)
      pass "$unit last result is success"
      ;;
    ""|none|no-result)
      warn "$unit has not reported a completed run yet (state=$state_label)"
      ;;
    *)
      message="$unit last result is ${result:-unknown} (state=$state_label)"
      if [[ "$expect" == "required" ]]; then
        fail "$message"
      else
        warn "$message"
      fi
      ;;
  esac
}

check_port_listening() {
  local port="$1"

  if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq "(^|:)$port$"; then
    pass "port $port is listening"
  else
    fail "port $port is not listening"
  fi
}

check_port_loopback_only() {
  local port="$1"
  local label="${2:-port $port}"
  local severity="${3:-warn}"
  local output=""
  local status=0

  if ! command -v python3 >/dev/null 2>&1; then
    warn "python3 is unavailable; skipping $label loopback-bind probe"
    return 0
  fi

  if output="$(ss -ltnH 2>/dev/null | python3 -c '
import ipaddress
import sys

port = str(sys.argv[1])
label = sys.argv[2]
matches: list[str] = []
unsafe: list[str] = []

for raw_line in sys.stdin:
    parts = raw_line.split()
    if len(parts) < 4:
        continue
    local_address = parts[3]
    host = ""
    actual_port = ""
    if local_address.startswith("["):
        end = local_address.rfind("]")
        if end == -1 or end + 1 >= len(local_address) or local_address[end + 1] != ":":
            continue
        host = local_address[1:end]
        actual_port = local_address[end + 2 :]
    else:
        if ":" not in local_address:
            continue
        host, actual_port = local_address.rsplit(":", 1)
    if actual_port != port:
        continue
    if host not in matches:
        matches.append(host)
    normalized = host.strip()
    if normalized.lower() == "localhost":
        continue
    try:
        if ipaddress.ip_address(normalized).is_loopback:
            continue
    except ValueError:
        pass
    if host not in unsafe:
        unsafe.append(host)

if not matches:
    print(f"{label} has no listening sockets")
    raise SystemExit(2)
if unsafe:
    print(label + " is exposed on non-loopback listener(s): " + ", ".join(unsafe))
    raise SystemExit(1)

print(label + " only accepts loopback connections (" + ", ".join(matches) + ")")
' "$port" "$label")"; then
    while IFS= read -r line; do
      [[ -n "$line" ]] && pass "$line"
    done <<<"$output"
  else
    status=$?
    case "$status" in
      1|2)
        while IFS= read -r line; do
          if [[ -n "$line" ]]; then
            if [[ "$severity" == "required" ]]; then
              fail "$line"
            else
              warn_or_fail "$line"
            fi
          fi
        done <<<"$output"
        ;;
      *)
        warn_or_fail "could not verify $label loopback binding"
        ;;
    esac
  fi
}

check_http_json_health() {
  local url="$1"
  local label="$2"
  local output=""

  if ! command -v python3 >/dev/null 2>&1; then
    warn "python3 is unavailable; skipping $label probe"
    return 0
  fi

  if output="$(python3 - "$url" "$label" <<'PY'
import json
import sys
import urllib.request

url = sys.argv[1]
label = sys.argv[2]

try:
    with urllib.request.urlopen(url, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
except Exception:
    raise SystemExit(1)

if not payload.get("ok", True):
    raise SystemExit(2)

service = payload.get("service") or label
extra = []
for key in ("port", "vault_warning_count"):
    if key in payload:
        extra.append(f"{key}={payload[key]}")

suffix = f" ({', '.join(extra)})" if extra else ""
print(f"{label} responded: {service}{suffix}")
PY
  )"; then
    while IFS= read -r line; do
      [[ -n "$line" ]] && pass "$line"
    done <<<"$output"
  else
    warn_or_fail "$label did not respond successfully at $url"
  fi
}

check_arclink_mcp_status() {
  local output=""

  if [[ ! -x "$BOOTSTRAP_DIR/bin/arclink-rpc" ]]; then
    warn_or_fail "arclink-rpc helper is missing"
    return 0
  fi

  if output="$("$BOOTSTRAP_DIR/bin/arclink-rpc" --url "$ARCLINK_MCP_URL" --tool status 2>/dev/null)"; then
    while IFS= read -r line; do
      [[ -n "$line" ]] && pass "$line"
    done < <(python3 - "$output" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
count = int(payload.get("vault_warning_count", 0))
print(f"arclink-mcp status ok; qmd_url={payload.get('qmd_url', 'unknown')}; vault_warning_count={count}")
PY
)
  else
    warn_or_fail "could not query arclink-mcp status via $ARCLINK_MCP_URL"
  fi
}

check_notion_webhook_funnel() {
  local output=""
  local ts_json=""
  local funnel_path="${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH:-/notion/webhook}"

  if [[ "$funnel_path" != /* ]]; then
    funnel_path="/$funnel_path"
  fi

  if ! command -v tailscale >/dev/null 2>&1; then
    warn_or_fail "tailscale CLI is not installed; cannot verify the public Notion webhook Funnel"
    return 0
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    warn_or_fail "python3 is unavailable; cannot verify the public Notion webhook Funnel"
    return 0
  fi

  ts_json="$(tailscale funnel status --json 2>/dev/null || true)"
  if [[ -z "$ts_json" ]]; then
    warn_or_fail "tailscale funnel status returned no JSON for the public Notion webhook route"
    return 0
  fi

  if output="$(
    TAILSCALE_FUNNEL_JSON="$ts_json" python3 - \
      "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-443}" \
      "$funnel_path" \
      "${ARCLINK_NOTION_WEBHOOK_PORT:-8283}" \
      "${ARCLINK_NOTION_WEBHOOK_PUBLIC_URL:-}" <<'PY'
import json
import os
import sys

port = str(sys.argv[1])
path = sys.argv[2]
backend_port = str(sys.argv[3])
expected_url = sys.argv[4]

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
    handler = handlers.get("/") or {}
    if handler.get("Proxy") != expected_proxy:
        continue
    if not allow.get(hostport):
        continue
    host = hostport.rsplit(":", 1)[0]
    actual_url = f"https://{host}{path}" if port == "443" else f"https://{host}:{port}{path}"
    if expected_url and actual_url != expected_url:
        print(f"mismatch:{actual_url}")
        raise SystemExit(2)
    print(actual_url)
    raise SystemExit(0)

raise SystemExit(1)
PY
  )"; then
    pass "Tailscale Funnel publishes only the configured Notion webhook route: $output"
  elif [[ "$output" == mismatch:* ]]; then
    warn_or_fail "Tailscale Funnel is live for the Notion webhook, but it does not match ARCLINK_NOTION_WEBHOOK_PUBLIC_URL: ${output#mismatch:}"
  else
    warn_or_fail "Tailscale Funnel is enabled for the Notion webhook, but the expected public route is not live"
  fi
}

check_tailscale_serve_routes() {
  local output=""
  local ts_json=""

  if ! command -v tailscale >/dev/null 2>&1; then
    warn_or_fail "tailscale CLI is not installed; cannot verify the tailnet-only Tailscale Serve routes"
    return 0
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    warn_or_fail "python3 is unavailable; cannot verify the tailnet-only Tailscale Serve routes"
    return 0
  fi

  ts_json="$(tailscale serve status --json 2>/dev/null || true)"
  if [[ -z "$ts_json" ]]; then
    warn_or_fail "tailscale serve status returned no JSON for the tailnet-only ArcLink routes"
    return 0
  fi

  if output="$(
    TAILSCALE_SERVE_JSON="$ts_json" python3 - \
      "${TAILSCALE_SERVE_PORT:-443}" \
      "${TAILSCALE_QMD_PATH:-/mcp}" \
      "${TAILSCALE_ARCLINK_MCP_PATH:-/arclink-mcp}" \
      "${NEXTCLOUD_PORT:-18080}" \
      "${QMD_MCP_PORT:-8181}" \
      "${ARCLINK_MCP_PORT:-8282}" <<'PY'
import json
import os
import sys

serve_port = str(sys.argv[1])
qmd_path = sys.argv[2]
arclink_mcp_path = sys.argv[3]
nextcloud_port = str(sys.argv[4])
qmd_port = str(sys.argv[5])
arclink_mcp_port = str(sys.argv[6])

try:
    data = json.loads(os.environ["TAILSCALE_SERVE_JSON"])
except Exception:
    raise SystemExit(1)

web = data.get("Web") or {}

for hostport, entry in web.items():
    host, sep, port = hostport.rpartition(":")
    actual_port = port if sep and port.isdigit() else "443"
    actual_host = host if sep and port.isdigit() else hostport
    if actual_port != serve_port:
        continue
    handlers = (entry or {}).get("Handlers") or {}
    root = handlers.get("/") or {}
    qmd = handlers.get(qmd_path) or {}
    arclink = handlers.get(arclink_mcp_path) or {}
    if (
        root.get("Proxy") == f"http://127.0.0.1:{nextcloud_port}"
        and qmd.get("Proxy") == f"http://127.0.0.1:{qmd_port}/mcp"
        and arclink.get("Proxy") == f"http://127.0.0.1:{arclink_mcp_port}/mcp"
    ):
        base = f"https://{actual_host}" if serve_port == "443" else f"https://{actual_host}:{serve_port}"
        print(base)
        raise SystemExit(0)

raise SystemExit(1)
PY
  )"; then
    pass "Tailscale HTTPS proxy is configured (tailnet only): $output"
  else
    warn_or_fail "Tailscale HTTPS proxy is not configured on the expected tailnet-only port ${TAILSCALE_SERVE_PORT:-443}"
  fi
}

check_retired_tailscale_nextcloud_routes() {
  if [[ -x "$SCRIPT_DIR/tailscale-nextcloud-serve.sh" ]] \
    && grep -q "no longer publishes Nextcloud or internal MCP routes" "$SCRIPT_DIR/tailscale-nextcloud-serve.sh"; then
    pass "legacy Tailscale Serve routes for Nextcloud and internal MCP are intentionally retired"
    return 0
  fi

  check_tailscale_serve_routes
}

check_activation_trigger_write_access() {
  local trigger_dir="$STATE_DIR/activation-triggers"
  local probe_path=""

  if ! mkdir -p "$trigger_dir" 2>/dev/null; then
    warn_or_fail "activation trigger directory is not writable: $trigger_dir"
    return 0
  fi

  if probe_path="$(mktemp "$trigger_dir/.arclink-health-trigger-XXXXXX" 2>/dev/null)"; then
    rm -f "$probe_path"
    pass "activation trigger directory is writable: $trigger_dir"
  else
    warn_or_fail "activation trigger directory is not writable: $trigger_dir"
  fi
}

check_vault_definition_health() {
  local output=""
  local status=0

  if ! command -v python3 >/dev/null 2>&1; then
    warn "python3 is unavailable; skipping .vault definition probe"
    return 0
  fi

  if output="$(PYTHONPATH="$BOOTSTRAP_DIR/python${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
from arclink_control import Config, connect_db, reload_vault_definitions

cfg = Config.from_env()
with connect_db(cfg) as conn:
    scan = reload_vault_definitions(conn, cfg)

warnings = scan.get("warnings", [])
print(f"vault definition scan found {len(scan.get('active_vaults', []))} active vault(s)")
for warning in warnings:
    print(warning)

raise SystemExit(2 if warnings else 0)
PY
  )"; then
    while IFS= read -r line; do
      [[ -n "$line" ]] && pass "$line"
    done <<<"$output"
  else
    status=$?
    case "$status" in
      2)
        local first_line="1"
        while IFS= read -r line; do
          [[ -z "$line" ]] && continue
          if [[ "$first_line" == "1" ]]; then
            pass "$line"
            first_line="0"
          else
            warn "$line"
          fi
        done <<<"$output"
        ;;
      *)
        fail "could not reload .vault definitions"
        ;;
    esac
  fi
}

check_curator_state() {
  local output=""
  local status=0

  if [[ -f "$ARCLINK_CURATOR_MANIFEST" ]]; then
    pass "Curator manifest exists: $ARCLINK_CURATOR_MANIFEST"
  else
    fail "Curator manifest missing: $ARCLINK_CURATOR_MANIFEST"
  fi

  if output="$(python3 - "$ARCLINK_DB_PATH" 2>&1 <<'PY'
import datetime as dt
import json
import sqlite3
import sys

db_path = sys.argv[1]
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

curator = conn.execute(
    "SELECT agent_id, unix_user, model_preset, channels_json, operator_notify_channel_json FROM agents WHERE role = 'curator' ORDER BY last_enrolled_at DESC LIMIT 1"
).fetchone()
if curator is None:
    raise SystemExit(2)

job = conn.execute(
    "SELECT last_run_at, last_status FROM refresh_jobs WHERE job_name = 'curator-refresh'"
).fetchone()
if job is None or not job["last_run_at"]:
    print(f"curator registered as {curator['agent_id']} but has never completed a curator-refresh run")
    raise SystemExit(3)

last_run = dt.datetime.fromisoformat(job["last_run_at"])
if last_run.tzinfo is None:
    last_run = last_run.replace(tzinfo=dt.timezone.utc)
age_seconds = (dt.datetime.now(dt.timezone.utc) - last_run).total_seconds()
channels = json.loads(curator["channels_json"] or "[]")
notify = json.loads(curator["operator_notify_channel_json"] or "{}")
print(
    f"Curator agent {curator['agent_id']} for unix user {curator['unix_user']} uses model preset {curator['model_preset'] or 'unknown'} "
    f"with channels {','.join(channels) if channels else 'none'} and operator notifications on "
    f"{notify.get('platform') or 'tui-only'} {notify.get('channel_id') or '(tui-only)'}"
)

if age_seconds > 7200:
    print(f"curator refresh is stale: last_run_at={job['last_run_at']} status={job['last_status'] or 'unknown'}")
    raise SystemExit(4)

raise SystemExit(0)
PY
  )"; then
    while IFS= read -r line; do
      [[ -n "$line" ]] && pass "$line"
    done <<<"$output"
  else
    status=$?
    case "$status" in
      2)
        fail "Curator is not registered in the shared control-plane DB"
        ;;
      3|4)
        while IFS= read -r line; do
          [[ -n "$line" ]] && fail "$line"
        done <<<"$output"
        ;;
      *)
        fail "could not inspect Curator state in $ARCLINK_DB_PATH"
        ;;
    esac
  fi
}

check_active_agent_state() {
  local output=""

  if ! command -v python3 >/dev/null 2>&1; then
    warn "python3 is unavailable; skipping enrolled-agent probe"
    return 0
  fi

if output="$(python3 - "$ARCLINK_DB_PATH" "$VAULT_DIR" "${ARCLINK_HOME:-}" 2>&1 <<'PY'
import datetime as dt
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

db_path = sys.argv[1]
vault_dir_raw = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("VAULT_DIR", "").strip()
arclink_home_raw = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("ARCLINK_HOME", "").strip()
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

agents = conn.execute(
    "SELECT agent_id, unix_user, display_name, hermes_home, manifest_path, channels_json FROM agents WHERE role = 'user' AND status = 'active' ORDER BY unix_user"
).fetchall()

if not agents:
    completed = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM bootstrap_requests
        WHERE auto_provision = 1
          AND status = 'approved'
          AND COALESCE(provisioned_at, '') != ''
        """
    ).fetchone()
    completed_count = int(completed["count"] if completed is not None else 0)
    if completed_count:
        print(f"FAIL no active enrolled user agents despite {completed_count} completed auto-provision enrollment(s)")
    else:
        print("OK no active enrolled user agents yet")
    raise SystemExit(0)

failures = 0
required_skill_names = [
    "arclink-qmd-mcp",
    "arclink-vault-reconciler",
    "arclink-first-contact",
    "arclink-vaults",
    "arclink-ssot",
    "arclink-notion-knowledge",
    "arclink-ssot-connect",
    "arclink-notion-mcp",
    "arclink-resources",
]
required_bundled_skill_paths = [
    ("email/himalaya", "himalaya"),
    ("productivity/google-workspace", "google-workspace"),
]


def acl_effective_perms(line):
    body, _, comment = line.partition("#")
    perms = body.rsplit(":", 1)[-1].strip()
    marker = "effective:"
    if marker in comment:
        perms = comment.split(marker, 1)[1].strip().split()[0]
    return perms


def acl_has_rwx(text, prefix):
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith(prefix + ":"):
            continue
        return acl_effective_perms(line) == "rwx"
    return False


def acl_has_perms(text, prefix, required):
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith(prefix + ":"):
            continue
        perms = acl_effective_perms(line)
        return all(char in perms for char in required)
    return False


def first_subuid_for_user(unix_user):
    subuid_file = Path(os.environ.get("ARCLINK_ROOTLESS_SUBUID_FILE", "/etc/subuid"))
    try:
        lines = subuid_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) < 3 or parts[0] != unix_user:
            continue
        try:
            start = int(parts[1])
            count = int(parts[2])
        except ValueError:
            continue
        if start > 0 and count > 0:
            return str(start)
    return ""


def acl_subjects_for_user(unix_user):
    subjects = [(unix_user, unix_user)]
    subuid = first_subuid_for_user(unix_user)
    if subuid:
        subjects.append((subuid, f"rootless Podman subuid {subuid} for {unix_user}"))
    return subjects


def shared_vault_acl_dirs(vault_dir):
    dirs = [vault_dir]
    warnings = []
    try:
        children = sorted(vault_dir.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        warnings.append(f"could not list shared vault children for ACL probe: {exc}")
        return dirs, warnings
    for child in children:
        try:
            if child.is_dir() and not child.is_symlink():
                dirs.append(child)
        except OSError:
            continue
    return dirs, warnings


def shared_vault_mount_source_dirs(vault_dir, arclink_home):
    if not arclink_home:
        return []
    try:
        arclink_home_path = Path(arclink_home)
    except TypeError:
        return []
    dirs = []
    for parent in vault_dir.parents:
        try:
            under_arclink_home = parent == arclink_home_path or parent.is_relative_to(arclink_home_path)
        except ValueError:
            under_arclink_home = False
        if under_arclink_home:
            dirs.append(parent)
    return dirs


def check_shared_vault_acl(vault_dir_raw, unix_user):
    if not vault_dir_raw:
        return [], [], []
    vault_dir = Path(vault_dir_raw)
    try:
        vault_exists = vault_dir.is_dir()
    except OSError:
        vault_exists = False
    if not vault_exists:
        return [], [], []
    getfacl = shutil.which("getfacl")
    if not getfacl:
        return [], ["shared vault ACL probe skipped because getfacl is unavailable"], []

    failures = []
    warnings = []
    subjects = acl_subjects_for_user(unix_user)
    dirs, list_warnings = shared_vault_acl_dirs(vault_dir)
    warnings.extend(list_warnings)
    for path in dirs:
        result = subprocess.run([getfacl, "-cp", str(path)], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown getfacl error").strip()
            failures.append(f"could not inspect shared vault ACL at {path}: {detail}")
            continue
        for subject, label in subjects:
            if not acl_has_rwx(result.stdout, f"user:{subject}"):
                failures.append(f"shared vault ACL for {label} is missing rwx on {path}")
            if not acl_has_rwx(result.stdout, f"default:user:{subject}"):
                failures.append(f"shared vault default ACL for {label} is missing rwx on {path}")

    for path in shared_vault_mount_source_dirs(vault_dir, arclink_home_raw):
        result = subprocess.run([getfacl, "-cp", str(path)], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown getfacl error").strip()
            failures.append(f"could not inspect shared vault mount-source ACL at {path}: {detail}")
            continue
        for subject, label in subjects:
            if not acl_has_perms(result.stdout, f"user:{subject}", "rx"):
                failures.append(f"shared vault mount-source ACL for {label} is missing rX on {path}")

    if len(failures) > 5:
        failures = failures[:5] + [f"{len(failures) - 5} additional shared vault ACL issue(s) omitted"]
    return failures, warnings, ["shared vault ACL ok"] if not failures else []


def parse_iso(value):
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def check_agent_backup_cron(hermes_home):
    failures = []
    warnings = []
    notes = []
    state_file = hermes_home / "state" / "arclink-agent-backup.env"
    try:
        configured = state_file.is_file()
    except PermissionError:
        return [], [], ["agent backup state private"]
    if not configured:
        return [], [], ["agent backup not configured"]

    script_path = hermes_home / "scripts" / "arclink_agent_backup.py"
    jobs_path = hermes_home / "cron" / "jobs.json"
    try:
        if not script_path.is_file():
            failures.append(f"agent backup Hermes cron script missing at {script_path}")
        if not jobs_path.is_file():
            failures.append(f"agent backup Hermes cron jobs file missing at {jobs_path}")
            return failures, warnings, notes
        payload = json.loads(jobs_path.read_text(encoding="utf-8"))
    except PermissionError:
        return [], [], ["agent backup cron state private"]
    except Exception as exc:
        failures.append(f"agent backup Hermes cron state is unreadable: {exc}")
        return failures, warnings, notes

    jobs = [
        job for job in payload.get("jobs", [])
        if isinstance(job, dict)
        and (
            job.get("id") == "a1bac0ffee42"
            or (job.get("managed_by") == "arclink" and job.get("managed_kind") == "agent-home-backup")
        )
    ]
    if not jobs:
        failures.append("agent backup Hermes cron job is missing")
        return failures, warnings, notes

    job = jobs[0]
    if not job.get("enabled", True):
        failures.append(f"agent backup Hermes cron job is disabled (state={job.get('state', 'unknown')})")
    if job.get("script") != "arclink_agent_backup.py":
        failures.append(f"agent backup Hermes cron job uses unexpected script {job.get('script')!r}")
    schedule = job.get("schedule") or {}
    try:
        schedule_minutes = int(schedule.get("minutes") or 0)
    except (TypeError, ValueError):
        schedule_minutes = 0
    if schedule.get("kind") != "interval" or schedule_minutes != 240:
        failures.append(f"agent backup Hermes cron job uses unexpected schedule {schedule!r}")
    if job.get("last_status") == "error":
        failures.append(f"agent backup Hermes cron job last_status=error: {job.get('last_error') or 'unknown error'}")

    last_run_path = hermes_home / "state" / "agent-home-backup" / "last-run.json"
    try:
        if not last_run_path.is_file():
            warnings.append("agent backup Hermes cron has not recorded a backup run yet")
            return failures, warnings, notes
        last_run = json.loads(last_run_path.read_text(encoding="utf-8"))
    except PermissionError:
        notes.append("agent backup last-run state private")
        return failures, warnings, notes
    except Exception as exc:
        failures.append(f"agent backup last-run state is unreadable: {exc}")
        return failures, warnings, notes

    if not bool(last_run.get("ok")):
        failures.append(f"agent backup last run failed: {str(last_run.get('summary') or 'unknown error')[:300]}")
        return failures, warnings, notes

    ran_at = parse_iso(last_run.get("ran_at"))
    if ran_at is None:
        warnings.append("agent backup last-run timestamp is missing or invalid")
        return failures, warnings, notes
    age_seconds = (dt.datetime.now(dt.timezone.utc) - ran_at).total_seconds()
    if age_seconds > 10 * 3600:
        failures.append(f"agent backup stale since {last_run.get('ran_at')}")
    else:
        notes.append(f"agent backup ok at {last_run.get('ran_at')}")
    return failures, warnings, notes


for agent in agents:
    agent_id = agent["agent_id"]
    unix_user = str(agent["unix_user"] or "").strip()
    manifest_path = Path(agent["manifest_path"] or "")
    hermes_home = Path(agent["hermes_home"] or "")
    channels = json.loads(agent["channels_json"] or "[]")
    privacy_notes = []
    status_notes = []

    if not manifest_path.is_file():
        print(f"FAIL {agent_id}: manifest missing at {manifest_path}")
        failures += 1
        continue
    if not unix_user:
        print(f"FAIL {agent_id}: missing unix_user in agent registry")
        failures += 1
        continue
    try:
        hermes_home_exists = hermes_home.exists()
    except PermissionError:
        hermes_home_exists = True
        privacy_notes.append("hermes_home private")
    if not hermes_home_exists:
        print(f"FAIL {agent_id}: hermes home missing at {hermes_home}")
        failures += 1
        continue
    skill_root = hermes_home / "skills"
    try:
        missing_skills = [
            skill_name
            for skill_name in required_skill_names
            if not (skill_root / skill_name / "SKILL.md").is_file()
        ]
    except PermissionError:
        missing_skills = []
        privacy_notes.append("skills private")
    if missing_skills:
        print(
            f"FAIL {agent_id}: missing managed ArcLink skills in {skill_root}: "
            + ", ".join(missing_skills)
        )
        failures += 1
        continue
    try:
        missing_bundled_skills = [
            label
            for rel_path, label in required_bundled_skill_paths
            if not (skill_root / rel_path / "SKILL.md").is_file()
        ]
    except PermissionError:
        missing_bundled_skills = []
        if "skills private" not in privacy_notes:
            privacy_notes.append("skills private")
    if missing_bundled_skills:
        print(
            f"FAIL {agent_id}: missing bundled Hermes skills in {skill_root}: "
            + ", ".join(missing_bundled_skills)
        )
        failures += 1
        continue

    token_count_row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM bootstrap_tokens
        WHERE agent_id = ?
          AND revoked_at IS NULL
          AND COALESCE(activated_at, '') != ''
        """,
        (agent_id,),
    ).fetchone()
    active_token_count = int(token_count_row["count"] if token_count_row is not None else 0)
    if active_token_count <= 0:
        print(f"FAIL {agent_id}: no active ArcLink MCP bootstrap token row")
        failures += 1
        continue
    status_notes.append("MCP bootstrap token row active")

    vault_failures, vault_warnings, vault_notes = check_shared_vault_acl(vault_dir_raw, unix_user)
    for warning in vault_warnings:
        print(f"WARN {agent_id}: {warning}")
    if vault_failures:
        for failure in vault_failures:
            print(f"FAIL {agent_id}: {failure}")
        failures += len(vault_failures)
        continue
    status_notes.extend(vault_notes)

    backup_failures, backup_warnings, backup_notes = check_agent_backup_cron(hermes_home)
    for warning in backup_warnings:
        print(f"WARN {agent_id}: {warning}")
    if backup_failures:
        for failure in backup_failures:
            print(f"FAIL {agent_id}: {failure}")
        failures += len(backup_failures)
        continue
    status_notes.extend(backup_notes)

    job = conn.execute(
        "SELECT last_run_at, last_status FROM refresh_jobs WHERE job_name = ?",
        (f"{agent_id}-refresh",),
    ).fetchone()
    if job is None or not job["last_run_at"]:
        print(f"FAIL {agent_id}: missing refresh job record")
        failures += 1
        continue

    last_run = dt.datetime.fromisoformat(job["last_run_at"])
    if last_run.tzinfo is None:
        last_run = last_run.replace(tzinfo=dt.timezone.utc)
    age_seconds = (dt.datetime.now(dt.timezone.utc) - last_run).total_seconds()
    if age_seconds > 8 * 3600:
        print(f"FAIL {agent_id}: refresh stale since {job['last_run_at']} (status={job['last_status'] or 'unknown'})")
        failures += 1
        continue
    if str(job["last_status"] or "") != "ok":
        print(f"FAIL {agent_id}: refresh job last_status={job['last_status'] or 'unknown'}")
        failures += 1
        continue
    status_notes.append("MCP token validated by user-owned refresh job")

    state_dir = Path(db_path).parent
    central_payload_path = state_dir / "agents" / agent_id / "managed-memory.json"
    central_payload_updated = None
    try:
        if central_payload_path.is_file():
            try:
                central_payload = json.loads(central_payload_path.read_text(encoding="utf-8"))
                central_payload_updated = parse_iso(central_payload.get("updated_at"))
            except Exception:
                central_payload_updated = dt.datetime.fromtimestamp(
                    central_payload_path.stat().st_mtime,
                    tz=dt.timezone.utc,
                )
    except OSError:
        central_payload_updated = None
    if central_payload_updated and central_payload_updated > last_run + dt.timedelta(seconds=30):
        print(
            f"WARN {agent_id}: central managed context updated at "
            f"{central_payload_updated.isoformat().replace('+00:00', '+00:00')} "
            f"but user-owned refresh last ran at {job['last_run_at']}; "
            "start arclink-user-agent-refresh.service for this user to apply it immediately"
        )

    trigger_path = state_dir / "activation-triggers" / f"{agent_id}.json"
    try:
        if trigger_path.is_file():
            trigger_updated = dt.datetime.fromtimestamp(trigger_path.stat().st_mtime, tz=dt.timezone.utc)
            if trigger_updated > last_run + dt.timedelta(seconds=30):
                print(
                    f"WARN {agent_id}: activation trigger is newer than the last user-owned refresh "
                    f"(trigger={trigger_updated.isoformat().replace('+00:00', '+00:00')}, "
                    f"refresh={job['last_run_at']}); verify arclink-user-agent-activate.path is active"
                )
    except OSError:
        pass

    note_parts = []
    if privacy_notes:
        note_parts.append(f"{'; '.join(privacy_notes)}; verified by user-owned refresh/service state")
    note_parts.extend(status_notes)
    print(
        f"OK {agent_id}: unix_user={unix_user} display_name={agent['display_name']} "
        f"channels={','.join(channels) if channels else 'tui-only'} refresh={job['last_run_at']}"
        + (f" ({'; '.join(note_parts)})" if note_parts else "")
    )

raise SystemExit(1 if failures else 0)
PY
  )"; then
    :
  else
    if [[ -z "$output" || "$output" != *$'\n'FAIL\ * && "$output" != FAIL\ * && "$output" != *$'\n'WARN\ * && "$output" != WARN\ * && "$output" != *$'\n'OK\ * && "$output" != OK\ * ]]; then
      fail "could not inspect active enrolled-agent state in $ARCLINK_DB_PATH"
      return 0
    fi
  fi

  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    case "$line" in
      FAIL\ *) fail "${line#FAIL }" ;;
      OK\ *) pass "${line#OK }" ;;
      WARN\ *) warn "${line#WARN }" ;;
      *) warn_or_fail "$line" ;;
    esac
  done <<<"$output"
}

check_auto_provision_state() {
  local output=""

  if ! command -v python3 >/dev/null 2>&1; then
    warn "python3 is unavailable; skipping auto-provision probe"
    return 0
  fi

if output="$(python3 - "$ARCLINK_DB_PATH" "${ARCLINK_AUTO_PROVISION_MAX_ATTEMPTS:-5}" 2>&1 <<'PY'
import datetime as dt
import sqlite3
import sys

conn = sqlite3.connect(sys.argv[1])
conn.row_factory = sqlite3.Row
max_attempts = int(sys.argv[2])

rows = conn.execute(
    """
    SELECT request_id, unix_user, status, approved_at, provisioned_at,
           provision_error, provision_attempts, provision_next_attempt_at
    FROM bootstrap_requests
    WHERE auto_provision = 1
    ORDER BY requested_at DESC
    """
).fetchall()

if not rows:
    print("OK no auto-provision enrollments recorded")
    raise SystemExit(0)

now = dt.datetime.now(dt.timezone.utc)
failed = 0
warned = 0
ok = 0
for row in rows:
    status = str(row["status"] or "")
    if status == "cancelled":
        ok += 1
        continue
    if row["provisioned_at"]:
        ok += 1
        continue
    if status != "approved":
        continue

    attempts = int(row["provision_attempts"] or 0)
    approved_at = row["approved_at"]
    approved_dt = dt.datetime.fromisoformat(approved_at) if approved_at else now
    if approved_dt.tzinfo is None:
        approved_dt = approved_dt.replace(tzinfo=dt.timezone.utc)
    age_seconds = (now - approved_dt).total_seconds()
    next_attempt_at = row["provision_next_attempt_at"]
    next_attempt_dt = None
    if next_attempt_at:
        next_attempt_dt = dt.datetime.fromisoformat(next_attempt_at)
        if next_attempt_dt.tzinfo is None:
            next_attempt_dt = next_attempt_dt.replace(tzinfo=dt.timezone.utc)

    if row["provision_error"] and attempts >= max_attempts and not next_attempt_at:
        print(
            f"FAIL auto-provision exhausted retries for {row['request_id']} "
            f"({row['unix_user']}): {row['provision_error']}"
        )
        failed += 1
    elif row["provision_error"] and next_attempt_dt is not None and next_attempt_dt > now:
        print(
            f"WARN auto-provision retry scheduled for {row['request_id']} "
            f"({row['unix_user']}) at {next_attempt_at} after error: {row['provision_error']}"
        )
        warned += 1
    elif row["provision_error"]:
        print(
            f"WARN auto-provision retry due now for {row['request_id']} "
            f"({row['unix_user']}): {row['provision_error']}"
        )
        warned += 1
    elif age_seconds > 300:
        print(f"FAIL auto-provision stalled for {row['request_id']} ({row['unix_user']}) since {approved_at}")
        failed += 1
    else:
        print(f"WARN auto-provision pending for {row['request_id']} ({row['unix_user']}) since {approved_at}")
        warned += 1

if ok:
    print(f"OK {ok} approved auto-provision enrollment(s) already completed")

raise SystemExit(1 if failed else 2 if warned else 0)
PY
  )"; then
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      case "$line" in
        OK\ *) pass "${line#OK }" ;;
        *) warn_or_fail "$line" ;;
      esac
    done <<<"$output"
  else
    if [[ -z "$output" || "$output" != *$'\n'FAIL\ * && "$output" != FAIL\ * && "$output" != *$'\n'WARN\ * && "$output" != WARN\ * && "$output" != *$'\n'OK\ * && "$output" != OK\ * ]]; then
      fail "could not inspect auto-provision state in $ARCLINK_DB_PATH"
      return 0
    fi
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      case "$line" in
        FAIL\ *) fail "${line#FAIL }" ;;
        WARN\ *) warn "${line#WARN }" ;;
        OK\ *) pass "${line#OK }" ;;
        *) warn_or_fail "$line" ;;
      esac
    done <<<"$output"
  fi
}

check_notification_delivery_state() {
  if ! command -v python3 >/dev/null 2>&1; then
    warn "python3 is unavailable; skipping notification delivery probe"
    return 0
  fi

  local output=""
  if ! output="$(python3 - "$ARCLINK_DB_PATH" 2>&1 <<'PY'
import datetime as dt
import sqlite3
import sys

db_path = sys.argv[1]
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

total = conn.execute(
    """
    SELECT COUNT(*) AS c
    FROM notification_outbox
    WHERE delivered_at IS NULL
      AND target_kind != 'user-agent'
    """
).fetchone()["c"]

deferred_user_agents = conn.execute(
    """
    SELECT COUNT(*) AS c
    FROM notification_outbox
    WHERE delivered_at IS NULL
      AND target_kind = 'user-agent'
    """
).fetchone()["c"]

failed = conn.execute(
    """
    SELECT COUNT(*) AS c
    FROM notification_outbox
    WHERE delivered_at IS NULL
      AND target_kind != 'user-agent'
      AND delivery_error IS NOT NULL
    """
).fetchone()["c"]

stuck = conn.execute(
    """
    SELECT COUNT(*) AS c
    FROM notification_outbox
    WHERE delivered_at IS NULL
      AND target_kind != 'user-agent'
      AND created_at < ?
    """,
    ((dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=15)).replace(microsecond=0).isoformat(),),
).fetchone()["c"]

if failed:
    print(f"FAIL notification delivery errors present: {failed} row(s) with delivery_error")
elif stuck:
    print(f"FAIL notifications stuck undelivered >15m: {stuck} row(s); delivery worker may be failing")
elif total and deferred_user_agents:
    print(
        f"OK {total} deliverable notification(s) pending; "
        f"{deferred_user_agents} user-agent notification(s) queued for refresh"
    )
elif total:
    print(f"OK {total} notification(s) pending delivery (no errors, none stale)")
elif deferred_user_agents:
    print(f"OK {deferred_user_agents} user-agent notification(s) queued for refresh")
else:
    print("OK notification outbox clean (no undelivered rows)")

raise SystemExit(0 if not (failed or stuck) else 1)
PY
  )"; then
    if [[ -z "$output" || "$output" != *$'\n'FAIL\ * && "$output" != FAIL\ * && "$output" != *$'\n'WARN\ * && "$output" != WARN\ * && "$output" != *$'\n'OK\ * && "$output" != OK\ * ]]; then
      fail "could not inspect notification delivery state in $ARCLINK_DB_PATH"
      return 0
    fi
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      case "$line" in
        FAIL\ *) fail "${line#FAIL }" ;;
        OK\ *) pass "${line#OK }" ;;
        *) warn_or_fail "$line" ;;
      esac
    done <<<"$output"
  else
    while IFS= read -r line; do
      [[ -n "$line" ]] && pass "$line"
    done <<<"$output"
  fi
}

check_upgrade_state() {
  if ! command -v python3 >/dev/null 2>&1; then
    warn "python3 is unavailable; skipping upgrade-state probe"
    return 0
  fi

  local output=""
  local status_code=0
  if ! output="$(ARCLINK_RELEASE_STATE_FILE="$ARCLINK_RELEASE_STATE_FILE" \
                ARCLINK_DB_PATH="$ARCLINK_DB_PATH" \
                ARCLINK_UPSTREAM_REPO_URL="${ARCLINK_UPSTREAM_REPO_URL:-}" \
                ARCLINK_UPSTREAM_BRANCH="${ARCLINK_UPSTREAM_BRANCH:-arclink}" \
                python3 - 2>&1 <<'PY'
import datetime as dt
import json
import os
import sqlite3
import sys
from pathlib import Path

release_path = Path(os.environ.get("ARCLINK_RELEASE_STATE_FILE") or "")
db_path = os.environ.get("ARCLINK_DB_PATH") or ""
upstream_repo = os.environ.get("ARCLINK_UPSTREAM_REPO_URL") or ""
upstream_branch = os.environ.get("ARCLINK_UPSTREAM_BRANCH") or "arclink"

release_state = {}
if release_path.is_file():
    try:
        release_state = json.loads(release_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        release_state = {}

deployed_commit = str(release_state.get("deployed_commit") or "").strip()
deployed_short = deployed_commit[:12]
tracked_repo = str(release_state.get("tracked_upstream_repo_url") or upstream_repo or "").strip()
tracked_branch = str(release_state.get("tracked_upstream_branch") or upstream_branch or "arclink").strip() or "arclink"

if not release_path.is_file() or not deployed_commit:
    print(f"WARN ArcLink release state missing or empty at {release_path}; run ./deploy.sh install or upgrade")
    raise SystemExit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
job = conn.execute(
    "SELECT last_run_at, last_status, last_note FROM refresh_jobs WHERE job_name = 'arclink-upgrade-check'"
).fetchone()
last_seen_sha_row = conn.execute(
    "SELECT value FROM settings WHERE key = 'arclink_upgrade_last_seen_sha'"
).fetchone()
relation_row = conn.execute(
    "SELECT value FROM settings WHERE key = 'arclink_upgrade_relation'"
).fetchone()
last_seen_sha = str(last_seen_sha_row["value"]) if last_seen_sha_row else ""
relation = str(relation_row["value"] or "") if relation_row else ""

if job is None or not job["last_run_at"]:
    print(
        f"WARN ArcLink upgrade-check has never run; deployed {deployed_short} "
        f"from {tracked_repo}#{tracked_branch}. Run ./bin/arclink-ctl upgrade check."
    )
    raise SystemExit(1)

last_run = dt.datetime.fromisoformat(job["last_run_at"])
if last_run.tzinfo is None:
    last_run = last_run.replace(tzinfo=dt.timezone.utc)
age_seconds = (dt.datetime.now(dt.timezone.utc) - last_run).total_seconds()

# The curator-refresh timer runs every 1h; a stale probe means the timer or
# Curator itself is dead. Flag anything older than 2h15m.
if age_seconds > 2 * 3600 + 900:
    print(
        f"FAIL ArcLink upgrade-check is stale (last_run_at={job['last_run_at']}, "
        f"age={int(age_seconds / 60)}m); Curator hourly refresh may be dead"
    )
    raise SystemExit(2)

if relation == "behind" and last_seen_sha and last_seen_sha != deployed_commit:
    print(
        f"WARN ArcLink upstream ahead of deployed: deployed {deployed_short} -> "
        f"upstream {last_seen_sha[:12]} on {tracked_repo}#{tracked_branch}; "
        "run ./deploy.sh upgrade"
    )
    raise SystemExit(1)
if relation == "ahead" and last_seen_sha and last_seen_sha != deployed_commit:
    print(
        f"WARN ArcLink deployed release is ahead of tracked upstream: deployed {deployed_short} "
        f"vs upstream {last_seen_sha[:12]} on {tracked_repo}#{tracked_branch}; "
        "review local commits before running ./deploy.sh upgrade"
    )
    raise SystemExit(1)
if relation in {"diverged", "different"} and last_seen_sha and last_seen_sha != deployed_commit:
    print(
        f"WARN ArcLink deployed release differs from tracked upstream: deployed {deployed_short} "
        f"vs upstream {last_seen_sha[:12]} on {tracked_repo}#{tracked_branch}; "
        "review repo state before upgrading"
    )
    raise SystemExit(1)
if last_seen_sha and last_seen_sha != deployed_commit and not relation:
    print(
        f"WARN ArcLink deployed release differs from tracked upstream: deployed {deployed_short} "
        f"vs upstream {last_seen_sha[:12]} on {tracked_repo}#{tracked_branch}; "
        "run ./bin/arclink-ctl upgrade check to refresh relation state"
    )
    raise SystemExit(1)

status = str(job["last_status"] or "unknown")
note = str(job["last_note"] or "")
print(
    f"OK ArcLink up to date at {deployed_short} on {tracked_repo}#{tracked_branch}; "
    f"last upgrade-check {status} ({int(age_seconds / 60)}m ago)"
)
raise SystemExit(0)
PY
  )"; then
    status_code=$?
    if [[ -z "$output" || "$output" != *$'\n'FAIL\ * && "$output" != FAIL\ * && "$output" != *$'\n'WARN\ * && "$output" != WARN\ * && "$output" != *$'\n'OK\ * && "$output" != OK\ * ]]; then
      fail "could not inspect ArcLink upgrade state in $ARCLINK_DB_PATH"
      return 0
    fi
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      case "$line" in
        FAIL\ *) fail "${line#FAIL }" ;;
        WARN\ *) warn "${line#WARN }" ;;
        OK\ *) pass "${line#OK }" ;;
        *) warn_or_fail "$line" ;;
      esac
    done <<<"$output"
    return 0
  fi
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    case "$line" in
      OK\ *) pass "${line#OK }" ;;
      *) pass "$line" ;;
    esac
  done <<<"$output"
}

check_qmd_mcp_status() {
  local disk_source_count=0
  local disk_derived_count=0
  local status=0
  local output=""

  if ! command -v python3 >/dev/null 2>&1; then
    warn "python3 is unavailable; skipping qmd MCP status probe"
    return 0
  fi

  disk_source_count="$(vault_source_file_count "$VAULT_DIR")"

  if [[ "$PDF_INGEST_ENABLED" == "1" && -d "$PDF_INGEST_MARKDOWN_DIR" ]]; then
    disk_derived_count="$(pdf_ingest_markdown_file_count "$PDF_INGEST_MARKDOWN_DIR")"
  fi

  if output="$(python3 - "$QMD_MCP_PORT" "$disk_source_count" "$disk_derived_count" <<'PY'
import json
import sys
import urllib.request

port = int(sys.argv[1])
disk_source_count = int(sys.argv[2])
disk_derived_count = int(sys.argv[3])
url = f"http://127.0.0.1:{port}/mcp"
headers = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def rpc(payload, session_id=None):
    request_headers = dict(headers)
    if session_id:
        request_headers["mcp-session-id"] = session_id
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=request_headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        parsed = json.loads(body) if body.strip() else {}
        return resp.headers.get("mcp-session-id") or session_id, parsed


try:
    session_id, _ = rpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "arclink-health", "version": "1.0"},
            },
        }
    )
    rpc({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}, session_id)
    _, status_body = rpc(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "status", "arguments": {}},
        },
        session_id,
    )
except Exception:
    raise SystemExit(1)

structured = ((status_body or {}).get("result") or {}).get("structuredContent") or {}
total_documents = int(structured.get("totalDocuments", 0))
collections = structured.get("collections") or []
collection_count = len(collections)
needs_embedding = int(structured.get("needsEmbedding", 0))

print(
    "qmd MCP status sees "
    f"{total_documents} document(s) across {collection_count} active collection(s); "
    f"{needs_embedding} need embedding"
)

if (disk_source_count + disk_derived_count) > 0 and total_documents == 0:
    print(
        "qmd MCP status is empty even though "
        f"{disk_source_count} vault source file(s) and {disk_derived_count} generated ingest markdown file(s) exist in the shared vault/index inputs"
    )
    raise SystemExit(3)

raise SystemExit(0)
PY
)"; then
    while IFS= read -r line; do
      [[ -n "$line" ]] && pass "$line"
    done <<<"$output"
  else
    status=$?
    case "$status" in
      3)
        while IFS= read -r line; do
          [[ -n "$line" ]] && warn_or_fail "$line"
        done <<<"$output"
        ;;
      *)
        warn_or_fail "could not query qmd MCP status on port $QMD_MCP_PORT"
        ;;
    esac
  fi
}

check_nextcloud_vault_mount() {
  local mounts_json=""

  podman_for_current_user() {
    local runtime_dir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    local podman_cwd="${HOME:-/tmp}"
    if [[ ! -d "$podman_cwd" || ! -x "$podman_cwd" ]]; then
      podman_cwd="/tmp"
    fi
    if [[ -d "$runtime_dir" ]]; then
      (cd "$podman_cwd" && env XDG_RUNTIME_DIR="$runtime_dir" podman "$@")
    else
      (cd "$podman_cwd" && podman "$@")
    fi
  }

  if command -v podman >/dev/null 2>&1; then
    if ! podman_for_current_user container inspect "$(nextcloud_app_container_name)" >/dev/null 2>&1; then
      warn_or_fail "Nextcloud app container is not present"
      return 0
    fi

    if ! mounts_json="$(podman_for_current_user exec -u 33:33 "$(nextcloud_app_container_name)" php /var/www/html/occ files_external:list --output=json 2>/dev/null)"; then
      warn_or_fail "could not inspect Nextcloud external-storage mounts"
      return 0
    fi

    if podman_for_current_user exec -u 33:33 "$(nextcloud_app_container_name)" sh -lc "test -w '$NEXTCLOUD_VAULT_CONTAINER_PATH'" >/dev/null 2>&1; then
      pass "Nextcloud can write the shared vault mount"
    else
      warn_or_fail "Nextcloud cannot write the shared vault mount at $NEXTCLOUD_VAULT_CONTAINER_PATH"
    fi
  elif have_compose_runtime; then
    if ! mounts_json="$(run_compose "$BOOTSTRAP_DIR/compose/nextcloud-compose.yml" exec -T -u 33:33 app php /var/www/html/occ files_external:list --output=json 2>/dev/null)"; then
      warn_or_fail "could not inspect Nextcloud external-storage mounts"
      return 0
    fi

    if run_compose "$BOOTSTRAP_DIR/compose/nextcloud-compose.yml" exec -T -u 33:33 app sh -lc "test -w '$NEXTCLOUD_VAULT_CONTAINER_PATH'" >/dev/null 2>&1; then
      pass "Nextcloud can write the shared vault mount"
    else
      warn_or_fail "Nextcloud cannot write the shared vault mount at $NEXTCLOUD_VAULT_CONTAINER_PATH"
    fi
  else
    warn "Nextcloud vault mount check skipped: no compose or podman runtime available"
    return 0
  fi

  if NEXTCLOUD_MOUNTS_JSON="$mounts_json" python3 - "$NEXTCLOUD_VAULT_MOUNT_POINT" "$NEXTCLOUD_VAULT_CONTAINER_PATH" <<'PY'
import json
import os
import sys

mount_point = sys.argv[1]
datadir = sys.argv[2]
try:
    mounts = json.loads(os.environ["NEXTCLOUD_MOUNTS_JSON"])
except Exception:
    raise SystemExit(1)

for mount in mounts:
    if mount.get("mount_point") == mount_point:
        config = mount.get("configuration") or {}
        if config.get("datadir") == datadir and not (mount.get("applicable_users") or []) and not (mount.get("applicable_groups") or []):
            raise SystemExit(0)
        raise SystemExit(2)

raise SystemExit(1)
PY
  then
    pass "Nextcloud exposes the shared vault at $NEXTCLOUD_VAULT_MOUNT_POINT"
  else
    case "$?" in
      2)
        warn_or_fail "Nextcloud vault mount exists but is not configured as a global $NEXTCLOUD_VAULT_MOUNT_POINT -> $NEXTCLOUD_VAULT_CONTAINER_PATH mount"
        ;;
      *)
        warn_or_fail "Nextcloud vault mount $NEXTCLOUD_VAULT_MOUNT_POINT is missing"
        ;;
    esac
  fi
}

check_pdf_ingest_status() {
  local backend=""

  if [[ "$PDF_INGEST_ENABLED" != "1" ]]; then
    pass "PDF ingestion disabled in config"
    return 0
  fi

  if backend="$(resolve_pdf_ingest_backend 2>/dev/null)"; then
    if [[ "$backend" == "disabled" ]]; then
      warn_or_fail "PDF ingestion is enabled, but the extractor backend resolved to disabled"
    else
      pass "PDF ingest backend available: $backend"
    fi
  else
    warn_or_fail "no PDF ingest backend available; looked for docling and pdftotext"
  fi

  if have_pdf_vision_backend; then
    pass "PDF vision captions configured via $(resolve_pdf_vision_endpoint) (model $PDF_VISION_MODEL, first ${PDF_VISION_MAX_PAGES:-6} page(s))"
  elif have_pdf_vision_partial_config; then
    warn_or_fail "PDF vision caption config is incomplete; set PDF_VISION_ENDPOINT, PDF_VISION_MODEL, and PDF_VISION_API_KEY together"
  elif command -v pdftoppm >/dev/null 2>&1; then
    pass "PDF vision captions disabled in config"
  else
    warn_or_fail "pdftoppm is not installed, so PDF vision captions are unavailable"
  fi

  if command -v qmd >/dev/null 2>&1; then
    if qmd --index "$QMD_INDEX_NAME" collection show "$PDF_INGEST_COLLECTION_NAME" >/dev/null 2>&1; then
      pass "qmd collection '$PDF_INGEST_COLLECTION_NAME' exists in index '$QMD_INDEX_NAME'"
    else
      warn_or_fail "qmd collection '$PDF_INGEST_COLLECTION_NAME' is missing from index '$QMD_INDEX_NAME'"
    fi
  fi

  if [[ -f "$PDF_INGEST_STATUS_FILE" ]]; then
    if PDF_INGEST_STATUS_JSON="$(cat "$PDF_INGEST_STATUS_FILE")" python3 - <<'PY'
import json
import os

status = json.loads(os.environ["PDF_INGEST_STATUS_JSON"])
doc_failed = int(status.get("failed", 0))
total = int(status.get("total_pdfs", 0))
backend = status.get("backend", "unknown")
print(f"last PDF ingest run saw {total} pdf(s) with backend {backend}")

if status.get("vision_enabled"):
    rendered = int(status.get("vision_pages_rendered", 0))
    captioned = int(status.get("vision_pages_captioned", 0))
    failed = int(status.get("vision_pages_failed", 0))
    model = status.get("vision_model", "unknown")
    print(f"last PDF vision pass rendered {rendered} page image(s), captioned {captioned}, {failed} failed (model: {model})")

if doc_failed:
    print(f"{doc_failed} PDF(s) currently failed ingestion")
    raise SystemExit(2)

vision_failed = int(status.get("vision_pages_failed", 0))
if vision_failed:
    raise SystemExit(3)

raise SystemExit(0)
PY
    then
      while IFS= read -r line; do
        [[ -n "$line" ]] && pass "$line"
      done < <(PDF_INGEST_STATUS_JSON="$(cat "$PDF_INGEST_STATUS_FILE")" python3 - <<'PY'
import json
import os

status = json.loads(os.environ["PDF_INGEST_STATUS_JSON"])
total = int(status.get("total_pdfs", 0))
backend = status.get("backend", "unknown")
print(f"last PDF ingest run saw {total} pdf(s) with backend {backend}")

if status.get("vision_enabled"):
    rendered = int(status.get("vision_pages_rendered", 0))
    captioned = int(status.get("vision_pages_captioned", 0))
    failed = int(status.get("vision_pages_failed", 0))
    model = status.get("vision_model", "unknown")
    print(f"last PDF vision pass rendered {rendered} page image(s), captioned {captioned}, {failed} failed (model: {model})")
PY
)
    else
      case "$?" in
        2|3)
          while IFS= read -r line; do
            [[ -n "$line" ]] && warn_or_fail "$line"
          done < <(PDF_INGEST_STATUS_JSON="$(cat "$PDF_INGEST_STATUS_FILE")" python3 - <<'PY'
import json
import os

status = json.loads(os.environ["PDF_INGEST_STATUS_JSON"])
doc_failed = int(status.get("failed", 0))
total = int(status.get("total_pdfs", 0))
backend = status.get("backend", "unknown")
print(f"last PDF ingest run saw {total} pdf(s) with backend {backend}")

if status.get("vision_enabled"):
    rendered = int(status.get("vision_pages_rendered", 0))
    captioned = int(status.get("vision_pages_captioned", 0))
    failed = int(status.get("vision_pages_failed", 0))
    model = status.get("vision_model", "unknown")
    print(f"last PDF vision pass rendered {rendered} page image(s), captioned {captioned}, {failed} failed (model: {model})")

if doc_failed:
    print(f"{doc_failed} PDF(s) currently failed ingestion")

vision_failed = int(status.get("vision_pages_failed", 0))
if vision_failed:
    print(f"{vision_failed} PDF page caption(s) failed during the last run")
PY
)
          ;;
        *)
          warn_or_fail "could not parse $PDF_INGEST_STATUS_FILE"
          ;;
      esac
    fi
  else
    warn "PDF ingest has not written a status file yet: $PDF_INGEST_STATUS_FILE"
  fi
}

check_memory_synth_status() {
  local enabled_raw="${ARCLINK_MEMORY_SYNTH_ENABLED:-auto}"
  local endpoint="${ARCLINK_MEMORY_SYNTH_ENDPOINT:-${PDF_VISION_ENDPOINT:-}}"
  local model="${ARCLINK_MEMORY_SYNTH_MODEL:-${PDF_VISION_MODEL:-}}"
  local api_key="${ARCLINK_MEMORY_SYNTH_API_KEY:-${PDF_VISION_API_KEY:-}}"
  local explicit_enabled=1
  local enabled=0
  local resolved_endpoint=""

  case "$(lowercase "$enabled_raw")" in
    ""|auto)
      explicit_enabled=0
      if [[ -n "$endpoint" && -n "$model" && -n "$api_key" ]]; then
        enabled=1
      fi
      ;;
    1|true|yes|on|enabled)
      enabled=1
      ;;
    *)
      enabled=0
      ;;
  esac

  if [[ "$enabled" != "1" ]]; then
    if [[ "$explicit_enabled" == "0" ]]; then
      pass "memory synthesis auto-disabled until LLM endpoint/model/key are configured"
    else
      pass "memory synthesis disabled in config"
    fi
  elif [[ -n "$endpoint" && -n "$model" && -n "$api_key" ]]; then
    resolved_endpoint="$(resolve_pdf_vision_endpoint "$endpoint" 2>/dev/null || printf '%s' "$endpoint")"
    pass "memory synthesis configured via $resolved_endpoint (model $model)"
  else
    warn_or_fail "memory synthesis is enabled, but ARCLINK_MEMORY_SYNTH_ENDPOINT, MODEL, and API_KEY are not complete"
  fi

  if [[ -f "$ARCLINK_MEMORY_SYNTH_STATUS_FILE" ]]; then
    local memory_status_output=""
    local memory_status_rc=0
    memory_status_output="$(
      ARCLINK_MEMORY_SYNTH_STATUS_JSON="$(cat "$ARCLINK_MEMORY_SYNTH_STATUS_FILE")" python3 - <<'PY'
import json
import os

status = json.loads(os.environ["ARCLINK_MEMORY_SYNTH_STATUS_JSON"])
state = str(status.get("status") or "unknown")
candidate_count = int(status.get("candidate_count") or 0)
changed = int(status.get("changed") or 0)
synthesized = int(status.get("synthesized") or 0)
failed = int(status.get("failed") or 0)
finished_at = str(status.get("finished_at") or "")
print(f"last memory synthesis run status={state}; candidates={candidate_count}; synthesized={synthesized}; changed={changed}; failed={failed}; finished_at={finished_at or 'unknown'}")
raise SystemExit(2 if state in {"fail", "failed"} or failed else 0)
PY
    )" || memory_status_rc=$?
    if [[ "$memory_status_rc" != "0" && -z "$memory_status_output" ]]; then
      warn_or_fail "could not parse $ARCLINK_MEMORY_SYNTH_STATUS_FILE"
      return 0
    fi
    while IFS= read -r line; do
      if [[ -z "$line" ]]; then
        continue
      fi
      if [[ "$memory_status_rc" == "0" ]]; then
        pass "$line"
      else
        warn_or_fail "$line"
      fi
    done <<<"$memory_status_output"
  else
    warn "memory synthesis status file not found yet at $ARCLINK_MEMORY_SYNTH_STATUS_FILE"
  fi
}

if [[ -n "${CONFIG_FILE:-}" ]]; then
  pass "config loaded from $CONFIG_FILE"
else
  warn "no arclink.env found; using script defaults"
fi

if [[ -d "$ARCLINK_PRIV_DIR" ]]; then
  pass "private repo dir exists: $ARCLINK_PRIV_DIR"
else
  fail "private repo dir missing: $ARCLINK_PRIV_DIR"
fi

if [[ -d "$VAULT_DIR" ]]; then
  pass "vault dir exists: $VAULT_DIR"
else
  fail "vault dir missing: $VAULT_DIR"
fi

ensure_uv
ensure_nvm

if command -v qmd >/dev/null 2>&1; then
  pass "qmd available at $(command -v qmd)"
else
  fail "qmd is not on PATH"
fi

if [[ -x "$RUNTIME_DIR/hermes-venv/bin/hermes" ]]; then
  pass "hermes available at $RUNTIME_DIR/hermes-venv/bin/hermes"
  if shared_runtime_python_is_share_safe "$RUNTIME_DIR/hermes-venv"; then
    pass "shared Hermes runtime uses a user-shareable Python interpreter"
  else
    warn_or_fail "shared Hermes runtime python resolves outside shared/system paths; rebuild with bootstrap-userland or deploy.sh upgrade"
  fi
else
  warn "hermes venv not found at $RUNTIME_DIR/hermes-venv/bin/hermes"
fi

if command -v qmd >/dev/null 2>&1; then
  if qmd --index "$QMD_INDEX_NAME" collection show "$QMD_COLLECTION_NAME" >/dev/null 2>&1; then
    pass "qmd collection '$QMD_COLLECTION_NAME' exists in index '$QMD_INDEX_NAME'"
  else
    fail "qmd collection '$QMD_COLLECTION_NAME' is missing from index '$QMD_INDEX_NAME'"
  fi
  if qmd --index "$QMD_INDEX_NAME" collection show "$ARCLINK_NOTION_INDEX_COLLECTION_NAME" >/dev/null 2>&1; then
    if [[ -n "${ARCLINK_NOTION_INDEX_ROOTS:-}" || -n "${ARCLINK_SSOT_NOTION_SPACE_URL:-}" ]]; then
      pass "qmd collection '$ARCLINK_NOTION_INDEX_COLLECTION_NAME' exists for shared Notion knowledge"
    else
      pass "qmd collection '$ARCLINK_NOTION_INDEX_COLLECTION_NAME' is provisioned for optional shared Notion indexing"
    fi
  elif [[ -n "${ARCLINK_NOTION_INDEX_ROOTS:-}" || -n "${ARCLINK_SSOT_NOTION_SPACE_URL:-}" ]]; then
    fail "qmd collection '$ARCLINK_NOTION_INDEX_COLLECTION_NAME' is missing from index '$QMD_INDEX_NAME'"
  else
    warn "qmd collection '$ARCLINK_NOTION_INDEX_COLLECTION_NAME' is not provisioned yet"
  fi
fi

check_pdf_ingest_status
check_memory_synth_status

case "${QMD_EMBED_PROVIDER:-local}" in
  endpoint|openai-compatible|remote|api)
    if [[ -n "${QMD_EMBED_ENDPOINT:-}" && -n "${QMD_EMBED_ENDPOINT_MODEL:-}" && -n "${QMD_EMBED_API_KEY:-}" ]]; then
      pass "qmd remote embedding endpoint config captured; local qmd vector embedding is intentionally skipped"
    else
      warn_or_fail "qmd remote embedding endpoint config is incomplete; set QMD_EMBED_ENDPOINT, QMD_EMBED_ENDPOINT_MODEL, and QMD_EMBED_API_KEY together"
    fi
    ;;
  none|off|disabled)
    warn "qmd embeddings are disabled; text index search remains available"
    ;;
  *)
    if [[ "$QMD_RUN_EMBED" == "1" ]]; then
      pass "qmd refresh will run local embeddings"
    else
      warn "qmd local embeddings are disabled; set QMD_RUN_EMBED=1"
    fi
    ;;
esac

if [[ -d "$ARCLINK_PRIV_DIR/.git" ]]; then
  pass "private git repo initialized"
else
  warn "private git repo not initialized at $ARCLINK_PRIV_DIR"
fi

if [[ -n "$BACKUP_GIT_REMOTE" ]]; then
  pass "backup remote configured: $BACKUP_GIT_REMOTE"
  if require_private_github_backup_remote "$BACKUP_GIT_REMOTE"; then
    pass "backup remote is not public"
  else
    warn_or_fail "backup remote visibility check failed or repo is public"
  fi
  if backup_git_remote_uses_ssh "$BACKUP_GIT_REMOTE"; then
    if [[ -f "$BACKUP_GIT_DEPLOY_KEY_PATH" ]]; then
      pass "backup deploy key exists at $BACKUP_GIT_DEPLOY_KEY_PATH"
    else
      warn_or_fail "backup deploy key missing at $BACKUP_GIT_DEPLOY_KEY_PATH"
    fi
  fi
else
  warn "BACKUP_GIT_REMOTE is empty"
fi

check_placeholder_secrets

if have_compose_runtime; then
  pass "compose runtime available: $(compose_runtime_label)"
else
  warn "no compose runtime available for Nextcloud"
fi

if set_user_systemd_bus_env; then
  check_unit_state arclink-mcp.service required
  check_unit_state arclink-notion-webhook.service required
  check_unit_state arclink-ssot-batcher.timer required
  check_unit_state arclink-notification-delivery.timer required
  check_unit_state arclink-health-watch.timer required
  if [[ "${ARCLINK_HEALTH_WATCH_CHILD:-0}" != "1" ]]; then
    check_user_timer_job_result arclink-health-watch.service required
  fi
  check_unit_state arclink-curator-refresh.timer required
  check_unit_state arclink-memory-synth.timer required
  check_user_timer_job_result arclink-memory-synth.service required
  check_unit_state arclink-qmd-mcp.service required
  check_unit_state arclink-qmd-update.timer required
  check_unit_state arclink-vault-watch.service required
  if [[ "${ARCLINK_HERMES_DOCS_SYNC_ENABLED:-1}" == "1" ]]; then
    check_unit_state arclink-hermes-docs-sync.timer required
  fi
  if [[ "$PDF_INGEST_ENABLED" == "1" ]]; then
    check_unit_state arclink-pdf-ingest.timer required
  else
    pass "PDF ingest timer disabled in config"
  fi
  check_unit_state arclink-github-backup.timer required
  if [[ -n "$BACKUP_GIT_REMOTE" ]]; then
    check_user_timer_job_result arclink-github-backup.service required
  fi

  if [[ "$ENABLE_NEXTCLOUD" == "1" ]]; then
    if ! nextcloud_runtime_available; then
      warn "Nextcloud enabled in config but no Nextcloud runtime is available; install podman or docker compose"
    elif [[ "$STRICT_MODE" == "1" ]]; then
      check_unit_state arclink-nextcloud.service required
    else
      check_unit_state arclink-nextcloud.service optional
    fi
  else
    pass "Nextcloud disabled in config"
  fi

  if [[ "$ENABLE_QUARTO" == "1" ]]; then
    check_unit_state arclink-quarto-render.timer optional
  else
    pass "Quarto timer disabled in config"
  fi

  if has_curator_telegram_onboarding; then
    check_unit_state arclink-curator-onboarding.service required
  else
    pass "Curator Telegram onboarding disabled in config"
  fi

  if has_curator_discord_onboarding; then
    check_unit_state arclink-curator-discord-onboarding.service required
  else
    pass "Curator Discord onboarding disabled in config"
  fi

  if has_curator_gateway_channels && { ! has_curator_onboarding || has_curator_non_onboarding_gateway_channels; }; then
    check_unit_state arclink-curator-gateway.service required
  else
    pass "Curator gateway service not required for configured channels"
  fi
  check_service_user_failed_units
else
  warn "systemd user bus unavailable; skipping service status checks"
fi

check_port_listening "$ARCLINK_MCP_PORT"
check_port_loopback_only "$ARCLINK_MCP_PORT" "arclink-mcp backend port $ARCLINK_MCP_PORT"
check_http_json_health "http://127.0.0.1:$ARCLINK_MCP_PORT/health" "arclink-mcp health"
check_arclink_mcp_status
check_activation_trigger_write_access
check_port_listening "$ARCLINK_NOTION_WEBHOOK_PORT"
check_port_loopback_only "$ARCLINK_NOTION_WEBHOOK_PORT" "arclink-notion-webhook backend port $ARCLINK_NOTION_WEBHOOK_PORT"
check_http_json_health "http://127.0.0.1:$ARCLINK_NOTION_WEBHOOK_PORT/health" "arclink-notion-webhook health"
if [[ -n "${ARCLINK_SSOT_NOTION_SPACE_URL:-}" ]]; then
  if [[ -n "${ARCLINK_NOTION_WEBHOOK_PUBLIC_URL:-}" ]]; then
    pass "Notion webhook public URL configured: $ARCLINK_NOTION_WEBHOOK_PUBLIC_URL"
    if [[ "${ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL:-0}" == "1" ]]; then
      check_notion_webhook_funnel
    fi
    if command -v sqlite3 >/dev/null 2>&1 && [[ -n "${ARCLINK_DB_PATH:-}" && -f "$ARCLINK_DB_PATH" ]]; then
      notion_webhook_token_state="$(
        sqlite3 "$ARCLINK_DB_PATH" "SELECT value FROM settings WHERE key = 'notion_webhook_verification_token' LIMIT 1;" 2>/dev/null || true
      )"
      if [[ -n "${notion_webhook_token_state//[[:space:]]/}" ]]; then
        notion_webhook_verified_at="$(
          sqlite3 "$ARCLINK_DB_PATH" "SELECT value FROM settings WHERE key = 'notion_webhook_verified_at' LIMIT 1;" 2>/dev/null || true
        )"
        notion_webhook_verified_by="$(
          sqlite3 "$ARCLINK_DB_PATH" "SELECT value FROM settings WHERE key = 'notion_webhook_verified_by' LIMIT 1;" 2>/dev/null || true
        )"
        if [[ -n "${notion_webhook_verified_at//[[:space:]]/}" ]]; then
          if [[ -n "${notion_webhook_verified_by//[[:space:]]/}" ]]; then
            pass "Notion webhook verification confirmed at ${notion_webhook_verified_at} by ${notion_webhook_verified_by}"
          else
            pass "Notion webhook verification confirmed at ${notion_webhook_verified_at}"
          fi
        else
          warn "Notion webhook verification token is installed, but operator confirmation is still pending: rerun \`$ARCLINK_REPO_DIR/deploy.sh notion-ssot\` or run \`arclink-ctl notion webhook-confirm-verified --actor <operator>\` after Notion accepts the token"
        fi
      else
        warn "Notion webhook public URL is configured, but no verification token is installed yet: run \`arclink-ctl notion webhook-arm-install\` before completing the Notion webhook handshake"
      fi
    fi
  else
    warn "Notion webhook public URL not configured: the independent claim poller still covers self-serve verification, but shared Notion content freshness falls back to the 4-hour Curator sweep instead of webhook-driven minutes-scale updates"
  fi
else
  pass "Notion webhook public URL not required because shared Notion SSOT is not configured"
fi
check_vault_definition_health
check_curator_state
check_curator_gateway_runtime
check_active_agent_state
check_auto_provision_state
check_notification_delivery_state
check_upgrade_state

check_port_listening "$QMD_MCP_PORT"
check_port_loopback_only "$QMD_MCP_PORT" "qmd MCP backend port $QMD_MCP_PORT" required
check_qmd_mcp_status

if nextcloud_effectively_enabled; then
  if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq "(^|:)$NEXTCLOUD_PORT$"; then
    pass "Nextcloud port $NEXTCLOUD_PORT is listening"
  else
    warn_or_fail "Nextcloud port $NEXTCLOUD_PORT is not listening"
  fi
  check_port_loopback_only "$NEXTCLOUD_PORT" "Nextcloud backend port $NEXTCLOUD_PORT"

  if command -v curl >/dev/null 2>&1; then
    if curl --max-time 5 -fsS -H "Host: $NEXTCLOUD_TRUSTED_DOMAIN" "http://127.0.0.1:$NEXTCLOUD_PORT/status.php" >/dev/null 2>&1; then
      pass "Nextcloud HTTP endpoint responded"
      check_nextcloud_vault_mount
    else
      warn_or_fail "Nextcloud HTTP endpoint is not ready"
    fi
  fi

  if [[ "$ENABLE_TAILSCALE_SERVE" == "1" ]]; then
    check_retired_tailscale_nextcloud_routes
  fi
fi

check_system_unit_state arclink-enrollment-provision.timer required
check_system_unit_state arclink-notion-claim-poll.timer required
check_system_failed_units

printf '\nSummary: %s ok, %s warn, %s fail\n' "$PASS_COUNT" "$WARN_COUNT" "$FAIL_COUNT"

if [[ "$FAIL_COUNT" -gt 0 ]]; then
  exit 1
fi
