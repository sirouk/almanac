#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MCP_URL="${ALMANAC_MCP_URL:-http://127.0.0.1:${ALMANAC_MCP_PORT:-8282}/mcp}"
QMD_URL="${ALMANAC_QMD_URL:-http://127.0.0.1:${QMD_MCP_PORT:-8181}/mcp}"
HERMES_HOME="${HERMES_HOME:-$HOME/.local/share/almanac-agent/hermes-home}"
TOKEN_FILE="${ALMANAC_BOOTSTRAP_TOKEN_FILE:-$HERMES_HOME/secrets/almanac-bootstrap-token}"
STATE_FILE="${ALMANAC_ENROLLMENT_STATE_FILE:-$HERMES_HOME/state/almanac-enrollment.json}"
FIRST_CONTACT_SCRIPT="$REPO_DIR/skills/almanac-first-contact/scripts/run-first-contact.sh"
FIRST_CONTACT_LOG="$HERMES_HOME/state/almanac-first-contact.log"

json_get() {
  local file="$1"
  local expr="$2"
  python3 - "$file" "$expr" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)

value = data
for part in sys.argv[2].split("."):
    if not part:
        continue
    if isinstance(value, dict):
        value = value.get(part)
    else:
        value = None
        break

if isinstance(value, (dict, list)):
    print(json.dumps(value))
elif value is None:
    print("")
else:
    print(str(value))
PY
}

update_state_patch() {
  local patch_json="$1"
  python3 - "$STATE_FILE" "$patch_json" <<'PY'
import json
import sys
from pathlib import Path

state_path = Path(sys.argv[1])
patch = json.loads(sys.argv[2])
data = {}
if state_path.is_file():
    data = json.loads(state_path.read_text(encoding="utf-8"))
data.update(patch)
state_path.parent.mkdir(parents=True, exist_ok=True)
state_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

if [[ ! -f "$STATE_FILE" ]]; then
  exit 0
fi

if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "Missing bootstrap token file at $TOKEN_FILE" >&2
  exit 1
fi

status="$(json_get "$STATE_FILE" "status")"
needs_registration="1"
if [[ "$status" == "active" ]]; then
  needs_registration="0"
fi
if [[ "$status" == "denied" || "$status" == "expired" ]]; then
  echo "Almanac enrollment $status." >&2
  exit 0
fi

token="$(tr -d '[:space:]' <"$TOKEN_FILE")"
register_out="$(mktemp)"
register_err="$(mktemp)"
trap 'rm -f "$register_out" "$register_err"' EXIT

if [[ "$needs_registration" == "1" ]]; then
if python3 "$REPO_DIR/python/almanac_rpc_client.py" \
  --url "$MCP_URL" \
  --tool "agents.register" \
  --json-args "$(
    ALMANAC_ENROLLMENT_STATE_FILE="$STATE_FILE" \
    ALMANAC_REGISTER_TOKEN="$token" \
    python3 - <<'PY'
import json
import os
from pathlib import Path

state = json.loads(Path(os.environ["ALMANAC_ENROLLMENT_STATE_FILE"]).read_text(encoding="utf-8"))
print(json.dumps({
    "token": os.environ["ALMANAC_REGISTER_TOKEN"],
    "unix_user": state["unix_user"],
    "display_name": state["requester_identity"],
    "role": "user",
    "hermes_home": state["hermes_home"],
    "model_preset": state["model_preset"],
    "model_string": state["model_string"],
    "channels": state.get("channels", ["tui-only"]),
}))
PY
  )" >"$register_out" 2>"$register_err"; then
  activated_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  update_state_patch "$(
    ACTIVATED_AT="$activated_at" REGISTER_OUT="$register_out" python3 - <<'PY'
import json
import os
from pathlib import Path

payload = json.loads(Path(os.environ["REGISTER_OUT"]).read_text(encoding="utf-8"))
print(json.dumps({
    "status": "active",
    "activated_at": os.environ["ACTIVATED_AT"],
    "agent_id": payload.get("agent_id", ""),
    "manifest_path": payload.get("manifest_path", ""),
    "subscriptions": payload.get("subscriptions", []),
    "home_channel": payload.get("home_channel", {}),
}))
PY
  )"
else
  message="$(tr '\n' ' ' <"$register_err")"
  lowered="$(printf '%s' "$message" | tr '[:upper:]' '[:lower:]')"
  if [[ "$lowered" == *"pending operator approval"* || "$lowered" == *"not active"* || "$lowered" == *"pending"*approval* ]]; then
    echo "Almanac enrollment pending operator approval."
    exit 0
  fi
  if [[ "$lowered" == *"denied"* ]]; then
    update_state_patch '{"status":"denied"}'
    echo "Almanac enrollment denied." >&2
    exit 0
  fi
  if [[ "$lowered" == *"expired"* ]]; then
    update_state_patch '{"status":"expired"}'
    echo "Almanac enrollment expired." >&2
    exit 0
  fi
  cat "$register_err" >&2
  exit 1
fi
fi

first_contact_ran_at="$(json_get "$STATE_FILE" "first_contact_ran_at")"
if [[ -z "$first_contact_ran_at" && -x "$FIRST_CONTACT_SCRIPT" ]]; then
  mkdir -p "$(dirname "$FIRST_CONTACT_LOG")"
  if HERMES_HOME="$HERMES_HOME" \
     ALMANAC_MCP_URL="$MCP_URL" \
     ALMANAC_QMD_URL="$QMD_URL" \
     ALMANAC_BOOTSTRAP_TOKEN_FILE="$TOKEN_FILE" \
     ALMANAC_SHARED_REPO_DIR="$REPO_DIR" \
     "$FIRST_CONTACT_SCRIPT" >"$FIRST_CONTACT_LOG" 2>&1; then
    update_state_patch "$(
      LOG_PATH="$FIRST_CONTACT_LOG" python3 - <<'PY'
import json
import os
print(json.dumps({
    "first_contact_ran_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).replace(microsecond=0).isoformat(),
    "first_contact_log": os.environ["LOG_PATH"],
}))
PY
    )"
  else
    update_state_patch "$(
      LOG_PATH="$FIRST_CONTACT_LOG" python3 - <<'PY'
import json
import os
print(json.dumps({
    "first_contact_last_failed_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).replace(microsecond=0).isoformat(),
    "first_contact_log": os.environ["LOG_PATH"],
}))
PY
    )"
    echo "Almanac first-contact retry pending; see $FIRST_CONTACT_LOG" >&2
    exit 0
  fi
fi

echo "Almanac enrollment active."
