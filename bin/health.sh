#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
STRICT_MODE="${ALMANAC_HEALTH_STRICT:-0}"

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

check_curator_gateway_runtime() {
  local output=""
  local status=0
  local runtime_channels="${ALMANAC_CURATOR_CHANNELS:-tui-only}"
  local channel
  local filtered_channels=()

  if has_curator_telegram_onboarding; then
    pass "Curator Telegram onboarding owns the Telegram worker"
    if ! has_curator_non_telegram_gateway_channels; then
      return 0
    fi
    IFS=',' read -r -a filtered_channels <<<"$runtime_channels"
    runtime_channels=""
    for channel in "${filtered_channels[@]}"; do
      channel="${channel//[[:space:]]/}"
      [[ -z "$channel" || "$channel" == "telegram" || "$channel" == "tui-only" ]] && continue
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

  if output="$("$RUNTIME_DIR/hermes-venv/bin/python3" - "$runtime_channels" <<'PY'
import sys

channels = [item.strip() for item in sys.argv[1].split(",") if item.strip()]
missing = []

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
      *)
        warn_or_fail "could not verify Curator gateway runtime dependencies"
        ;;
    esac
  fi
}

check_unit_state() {
  local unit="$1"
  local expect="$2"
  local state

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
  local state

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

check_port_listening() {
  local port="$1"

  if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq "(^|:)$port$"; then
    pass "port $port is listening"
  else
    fail "port $port is not listening"
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

check_almanac_mcp_status() {
  local output=""

  if [[ ! -x "$BOOTSTRAP_DIR/bin/almanac-rpc" ]]; then
    warn_or_fail "almanac-rpc helper is missing"
    return 0
  fi

  if output="$("$BOOTSTRAP_DIR/bin/almanac-rpc" --url "$ALMANAC_MCP_URL" --tool status 2>/dev/null)"; then
    while IFS= read -r line; do
      [[ -n "$line" ]] && pass "$line"
    done < <(python3 - "$output" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
count = int(payload.get("vault_warning_count", 0))
print(f"almanac-mcp status ok; qmd_url={payload.get('qmd_url', 'unknown')}; vault_warning_count={count}")
PY
)
  else
    warn_or_fail "could not query almanac-mcp status via $ALMANAC_MCP_URL"
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
from almanac_control import Config, connect_db, reload_vault_definitions

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
        warn_or_fail "could not reload .vault definitions"
        ;;
    esac
  fi
}

check_curator_state() {
  local output=""
  local status=0

  if [[ -f "$ALMANAC_CURATOR_MANIFEST" ]]; then
    pass "Curator manifest exists: $ALMANAC_CURATOR_MANIFEST"
  else
    fail "Curator manifest missing: $ALMANAC_CURATOR_MANIFEST"
  fi

  if output="$(python3 - "$ALMANAC_DB_PATH" <<'PY'
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
        warn_or_fail "could not inspect Curator state in $ALMANAC_DB_PATH"
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

  if output="$(python3 - "$ALMANAC_DB_PATH" <<'PY'
import datetime as dt
import json
import os
import sqlite3
import sys
from pathlib import Path

db_path = sys.argv[1]
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

agents = conn.execute(
    "SELECT agent_id, unix_user, display_name, hermes_home, manifest_path, channels_json FROM agents WHERE role = 'user' AND status = 'active' ORDER BY unix_user"
).fetchall()

if not agents:
    print("no active enrolled user agents")
    raise SystemExit(0)

failures = 0
for agent in agents:
    agent_id = agent["agent_id"]
    manifest_path = Path(agent["manifest_path"] or "")
    hermes_home = Path(agent["hermes_home"] or "")
    channels = json.loads(agent["channels_json"] or "[]")

    if not manifest_path.is_file():
        print(f"FAIL {agent_id}: manifest missing at {manifest_path}")
        failures += 1
        continue
    if not hermes_home.exists():
        print(f"FAIL {agent_id}: hermes home missing at {hermes_home}")
        failures += 1
        continue

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

    print(
        f"OK {agent_id}: unix_user={agent['unix_user']} display_name={agent['display_name']} "
        f"channels={','.join(channels) if channels else 'tui-only'} refresh={job['last_run_at']}"
    )

raise SystemExit(1 if failures else 0)
PY
  )"; then
    while IFS= read -r line; do
      [[ -n "$line" ]] && pass "$line"
    done <<<"$output"
  else
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      case "$line" in
        FAIL\ *) fail "${line#FAIL }" ;;
        OK\ *) pass "${line#OK }" ;;
        *) warn_or_fail "$line" ;;
      esac
    done <<<"$output"
  fi
}

check_auto_provision_state() {
  local output=""

  if ! command -v python3 >/dev/null 2>&1; then
    warn "python3 is unavailable; skipping auto-provision probe"
    return 0
  fi

if output="$(python3 - "$ALMANAC_DB_PATH" "${ALMANAC_AUTO_PROVISION_MAX_ATTEMPTS:-5}" <<'PY'
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
  if ! output="$(python3 - "$ALMANAC_DB_PATH" <<'PY'
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
  if ! output="$(ALMANAC_RELEASE_STATE_FILE="$ALMANAC_RELEASE_STATE_FILE" \
                ALMANAC_DB_PATH="$ALMANAC_DB_PATH" \
                ALMANAC_UPSTREAM_REPO_URL="${ALMANAC_UPSTREAM_REPO_URL:-}" \
                ALMANAC_UPSTREAM_BRANCH="${ALMANAC_UPSTREAM_BRANCH:-main}" \
                python3 - <<'PY'
import datetime as dt
import json
import os
import sqlite3
import sys
from pathlib import Path

release_path = Path(os.environ.get("ALMANAC_RELEASE_STATE_FILE") or "")
db_path = os.environ.get("ALMANAC_DB_PATH") or ""
upstream_repo = os.environ.get("ALMANAC_UPSTREAM_REPO_URL") or ""
upstream_branch = os.environ.get("ALMANAC_UPSTREAM_BRANCH") or "main"

release_state = {}
if release_path.is_file():
    try:
        release_state = json.loads(release_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        release_state = {}

deployed_commit = str(release_state.get("deployed_commit") or "").strip()
deployed_short = deployed_commit[:12]
tracked_repo = str(release_state.get("tracked_upstream_repo_url") or upstream_repo or "").strip()
tracked_branch = str(release_state.get("tracked_upstream_branch") or upstream_branch or "main").strip() or "main"

if not release_path.is_file() or not deployed_commit:
    print(f"WARN Almanac release state missing or empty at {release_path}; run ./deploy.sh install or upgrade")
    raise SystemExit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
job = conn.execute(
    "SELECT last_run_at, last_status, last_note FROM refresh_jobs WHERE job_name = 'almanac-upgrade-check'"
).fetchone()
last_seen_sha_row = conn.execute(
    "SELECT value FROM settings WHERE key = 'almanac_upgrade_last_seen_sha'"
).fetchone()
last_seen_sha = str(last_seen_sha_row["value"]) if last_seen_sha_row else ""

if job is None or not job["last_run_at"]:
    print(
        f"WARN Almanac upgrade-check has never run; deployed {deployed_short} "
        f"from {tracked_repo}#{tracked_branch}. Run ./bin/almanac-ctl upgrade check."
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
        f"FAIL Almanac upgrade-check is stale (last_run_at={job['last_run_at']}, "
        f"age={int(age_seconds / 60)}m); Curator hourly refresh may be dead"
    )
    raise SystemExit(2)

if last_seen_sha and last_seen_sha != deployed_commit:
    print(
        f"WARN Almanac upstream ahead of deployed: deployed {deployed_short} -> "
        f"upstream {last_seen_sha[:12]} on {tracked_repo}#{tracked_branch}; "
        "run ./deploy.sh upgrade"
    )
    raise SystemExit(1)

status = str(job["last_status"] or "unknown")
note = str(job["last_note"] or "")
print(
    f"OK Almanac up to date at {deployed_short} on {tracked_repo}#{tracked_branch}; "
    f"last upgrade-check {status} ({int(age_seconds / 60)}m ago)"
)
raise SystemExit(0)
PY
  )"; then
    status_code=$?
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
                "clientInfo": {"name": "almanac-health", "version": "1.0"},
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
  local mounts_json

  if command -v podman >/dev/null 2>&1; then
    if ! podman container inspect "$(nextcloud_app_container_name)" >/dev/null 2>&1; then
      warn_or_fail "Nextcloud app container is not present"
      return 0
    fi

    if ! mounts_json="$(podman exec -u 33:33 "$(nextcloud_app_container_name)" php /var/www/html/occ files_external:list --output=json 2>/dev/null)"; then
      warn_or_fail "could not inspect Nextcloud external-storage mounts"
      return 0
    fi

    if podman exec -u 33:33 "$(nextcloud_app_container_name)" sh -lc "test -w '$NEXTCLOUD_VAULT_CONTAINER_PATH'" >/dev/null 2>&1; then
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
  local backend

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

if [[ -n "${CONFIG_FILE:-}" ]]; then
  pass "config loaded from $CONFIG_FILE"
else
  warn "no almanac.env found; using script defaults"
fi

if [[ -d "$ALMANAC_PRIV_DIR" ]]; then
  pass "private repo dir exists: $ALMANAC_PRIV_DIR"
else
  fail "private repo dir missing: $ALMANAC_PRIV_DIR"
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
else
  warn "hermes venv not found at $RUNTIME_DIR/hermes-venv/bin/hermes"
fi

if command -v qmd >/dev/null 2>&1; then
  if qmd --index "$QMD_INDEX_NAME" collection show "$QMD_COLLECTION_NAME" >/dev/null 2>&1; then
    pass "qmd collection '$QMD_COLLECTION_NAME' exists in index '$QMD_INDEX_NAME'"
  else
    fail "qmd collection '$QMD_COLLECTION_NAME' is missing from index '$QMD_INDEX_NAME'"
  fi
fi

check_pdf_ingest_status

if [[ "$QMD_RUN_EMBED" == "1" ]]; then
  pass "qmd refresh will run embeddings"
else
  warn "qmd refresh will not run embeddings; set QMD_RUN_EMBED=1"
fi

if [[ -d "$ALMANAC_PRIV_DIR/.git" ]]; then
  pass "private git repo initialized"
else
  warn "private git repo not initialized at $ALMANAC_PRIV_DIR"
fi

if [[ -n "$BACKUP_GIT_REMOTE" ]]; then
  pass "backup remote configured: $BACKUP_GIT_REMOTE"
else
  warn "BACKUP_GIT_REMOTE is empty"
fi

if have_compose_runtime; then
  pass "compose runtime available: $(compose_runtime_label)"
else
  warn "no compose runtime available for Nextcloud"
fi

if set_user_systemd_bus_env; then
  check_unit_state almanac-mcp.service required
  check_unit_state almanac-notion-webhook.service required
  check_unit_state almanac-ssot-batcher.timer required
  check_unit_state almanac-notification-delivery.timer required
  check_unit_state almanac-curator-refresh.timer required
  check_unit_state almanac-qmd-mcp.service required
  check_unit_state almanac-qmd-update.timer required
  check_unit_state almanac-vault-watch.service required
  if [[ "$PDF_INGEST_ENABLED" == "1" ]]; then
    check_unit_state almanac-pdf-ingest.timer required
  else
    pass "PDF ingest timer disabled in config"
  fi
  check_unit_state almanac-github-backup.timer required

  if [[ "$ENABLE_NEXTCLOUD" == "1" ]]; then
    if [[ "$STRICT_MODE" == "1" ]]; then
      check_unit_state almanac-nextcloud.service required
    else
      check_unit_state almanac-nextcloud.service optional
    fi
  else
    pass "Nextcloud disabled in config"
  fi

  if [[ "$ENABLE_QUARTO" == "1" ]]; then
    check_unit_state almanac-quarto-render.timer optional
  else
    pass "Quarto timer disabled in config"
  fi

  if has_curator_telegram_onboarding; then
    check_unit_state almanac-curator-onboarding.service required
    if has_curator_non_telegram_gateway_channels; then
      check_unit_state almanac-curator-gateway.service required
    else
      check_unit_state almanac-curator-gateway.service optional
    fi
  elif has_curator_gateway_channels; then
    check_unit_state almanac-curator-gateway.service required
  else
    check_unit_state almanac-curator-gateway.service optional
    check_unit_state almanac-curator-onboarding.service optional
  fi
else
  warn "systemd user bus unavailable; skipping service status checks"
fi

check_port_listening "$ALMANAC_MCP_PORT"
check_http_json_health "http://127.0.0.1:$ALMANAC_MCP_PORT/health" "almanac-mcp health"
check_almanac_mcp_status
check_port_listening "$ALMANAC_NOTION_WEBHOOK_PORT"
check_http_json_health "http://127.0.0.1:$ALMANAC_NOTION_WEBHOOK_PORT/health" "almanac-notion-webhook health"
check_vault_definition_health
check_curator_state
check_curator_gateway_runtime
check_active_agent_state
check_auto_provision_state
check_notification_delivery_state
check_upgrade_state

check_port_listening "$QMD_MCP_PORT"
check_qmd_mcp_status

if [[ "$ENABLE_NEXTCLOUD" == "1" ]]; then
  if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq "(^|:)$NEXTCLOUD_PORT$"; then
    pass "Nextcloud port $NEXTCLOUD_PORT is listening"
  else
    warn_or_fail "Nextcloud port $NEXTCLOUD_PORT is not listening"
  fi

  if command -v curl >/dev/null 2>&1; then
    if curl --max-time 5 -fsS -H "Host: $NEXTCLOUD_TRUSTED_DOMAIN" "http://127.0.0.1:$NEXTCLOUD_PORT/status.php" >/dev/null 2>&1; then
      pass "Nextcloud HTTP endpoint responded"
      check_nextcloud_vault_mount
    else
      warn_or_fail "Nextcloud HTTP endpoint is not ready"
    fi
  fi

  if [[ "$ENABLE_TAILSCALE_SERVE" == "1" ]]; then
    if command -v tailscale >/dev/null 2>&1; then
      ts_status="$(tailscale serve status 2>/dev/null || true)"
      if printf '%s\n' "$ts_status" | grep -q "proxy http://127.0.0.1:$NEXTCLOUD_PORT"; then
        if printf '%s\n' "$ts_status" | grep -q "(tailnet only)"; then
          pass "Tailscale HTTPS proxy is configured (tailnet only)"
        else
          warn_or_fail "Tailscale HTTPS proxy is configured, but exposure is not clearly tailnet-only"
        fi
      else
        warn_or_fail "Tailscale HTTPS proxy is not configured for Nextcloud"
      fi

      if printf '%s\n' "$ts_status" | grep -q "proxy http://127.0.0.1:$QMD_MCP_PORT/mcp"; then
        pass "Tailscale qmd MCP proxy is configured"
      else
        warn_or_fail "Tailscale qmd MCP proxy is not configured"
      fi

      if printf '%s\n' "$ts_status" | grep -q "proxy http://127.0.0.1:$ALMANAC_MCP_PORT/mcp"; then
        pass "Tailscale Almanac MCP proxy is configured"
      else
        warn_or_fail "Tailscale Almanac MCP proxy is not configured"
      fi
    else
      warn_or_fail "tailscale CLI is not installed"
    fi
  fi
fi

check_system_unit_state almanac-enrollment-provision.timer required

printf '\nSummary: %s ok, %s warn, %s fail\n' "$PASS_COUNT" "$WARN_COUNT" "$FAIL_COUNT"

if [[ "$FAIL_COUNT" -gt 0 ]]; then
  exit 1
fi
