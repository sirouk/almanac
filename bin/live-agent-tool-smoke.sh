#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

require_real_layout "live agent tool smoke"
ensure_layout

ORIGINAL_ARGS=("$@")
TARGET_UNIX_USER=""
TARGET_AGENT_SELECTOR=""
TAIL_LINES=40
SMOKE_RETRY_ATTEMPT="${ARCLINK_LIVE_AGENT_SMOKE_RETRY_ATTEMPT:-0}"
SMOKE_TIMEOUT_SECONDS="${ARCLINK_LIVE_AGENT_SMOKE_TIMEOUT_SECONDS:-300}"
PROMPT="${ARCLINK_LIVE_AGENT_SMOKE_PROMPT:-Use the ArcLink MCP vault.search-and-fetch rail to search for \"Hermes quota monitoring\" and tell me whether you found relevant vault knowledge in one short sentence. Do not use terminal, local scripts, raw MCP protocol, or secrets files.}"

usage() {
  cat <<'EOF'
Usage: live-agent-tool-smoke.sh [--user UNIX_USER] [--agent AGENT_ID_OR_NAME] [--tail LINES]

Runs a live Hermes tool smoke against one active enrolled user agent.
If no selector is provided, the first active user agent is selected.
EOF
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --user|-u)
      if [[ "$#" -lt 2 || -z "${2:-}" ]]; then
        echo "Missing value for $1" >&2
        usage >&2
        exit 2
      fi
      TARGET_UNIX_USER="$2"
      shift 2
      ;;
    --agent|-a)
      if [[ "$#" -lt 2 || -z "${2:-}" ]]; then
        echo "Missing value for $1" >&2
        usage >&2
        exit 2
      fi
      TARGET_AGENT_SELECTOR="$2"
      shift 2
      ;;
    --tail)
      if [[ "$#" -lt 2 || ! "${2:-}" =~ ^[0-9]+$ || "${2:-0}" -lt 1 ]]; then
        echo "Missing or invalid numeric value for $1" >&2
        usage >&2
        exit 2
      fi
      TAIL_LINES="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    --*)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -n "$TARGET_UNIX_USER" ]]; then
        echo "Unexpected extra argument: $1" >&2
        usage >&2
        exit 2
      fi
      TARGET_UNIX_USER="$1"
      shift
      ;;
  esac
done

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is unavailable; cannot run live agent tool smoke." >&2
  exit 1
fi

if [[ ! "$SMOKE_TIMEOUT_SECONDS" =~ ^[0-9]+$ || "$SMOKE_TIMEOUT_SECONDS" -lt 30 ]]; then
  echo "ARCLINK_LIVE_AGENT_SMOKE_TIMEOUT_SECONDS must be an integer >= 30." >&2
  exit 2
fi

if [[ ! -x "$RUNTIME_DIR/hermes-venv/bin/hermes" ]]; then
  echo "Hermes runtime missing at $RUNTIME_DIR/hermes-venv/bin/hermes" >&2
  exit 1
fi

agent_json="$(python3 - "$ARCLINK_DB_PATH" "$TARGET_UNIX_USER" "$TARGET_AGENT_SELECTOR" <<'PY'
import json
import sqlite3
import sys

db_path = sys.argv[1]
target_unix_user = (sys.argv[2] or "").strip()
target_agent_selector = (sys.argv[3] or "").strip().lower()

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
query = """
    SELECT agent_id, unix_user, hermes_home, display_name
    FROM agents
    WHERE role = 'user' AND status = 'active'
"""
params: list[str] = []
if target_unix_user:
    query += " AND unix_user = ?"
    params.append(target_unix_user)
if target_agent_selector:
    query += """
      AND (
        lower(agent_id) = ?
        OR lower(unix_user) = ?
        OR lower(coalesce(display_name, '')) = ?
      )
    """
    params.extend([target_agent_selector, target_agent_selector, target_agent_selector])
query += " ORDER BY unix_user LIMIT 1"
row = conn.execute(query, params).fetchone()

if row is None:
    print("{}")
else:
    print(json.dumps(dict(row)))
PY
)"

if [[ "$agent_json" == "{}" ]]; then
  echo "No active enrolled user agent is available for live tool smoke; skipping."
  exit 0
fi

TARGET_UNIX_USER="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["unix_user"])' "$agent_json")"
TARGET_HERMES_HOME="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["hermes_home"])' "$agent_json")"
TARGET_DISPLAY_NAME="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get("display_name") or "")' "$agent_json")"
TARGET_HOME="$(getent passwd "$TARGET_UNIX_USER" | cut -d: -f6 || true)"

if [[ -z "$TARGET_HOME" || ! -d "$TARGET_HOME" ]]; then
  echo "Active agent unix user $TARGET_UNIX_USER has no usable home directory." >&2
  exit 1
fi

run_as_target_user() {
  if [[ "$(id -un)" == "$TARGET_UNIX_USER" ]]; then
    env HOME="$TARGET_HOME" HERMES_HOME="$TARGET_HERMES_HOME" "$@"
  elif [[ "$(id -u)" -eq 0 ]]; then
    runuser -u "$TARGET_UNIX_USER" -- env HOME="$TARGET_HOME" HERMES_HOME="$TARGET_HERMES_HOME" "$@"
  else
    echo "Live agent tool smoke must run as root or $TARGET_UNIX_USER to inspect private Hermes home at $TARGET_HERMES_HOME." >&2
    return 77
  fi
}

if ! run_as_target_user test -d "$TARGET_HERMES_HOME"; then
  echo "Active agent Hermes home is missing or inaccessible at $TARGET_HERMES_HOME" >&2
  exit 1
fi

telemetry_path="$TARGET_HERMES_HOME/state/arclink-context-telemetry.jsonl"
sessions_dir="$TARGET_HERMES_HOME/sessions"
agent_log_path="$TARGET_HERMES_HOME/logs/agent.log"
output_file="$(mktemp /tmp/arclink-live-agent-smoke.XXXXXX.log)"
trap 'rm -f "$output_file"' EXIT

before_latest_session="$(run_as_target_user bash -lc 'find "$HERMES_HOME/sessions" -maxdepth 1 -type f -name "session_*.json" -printf "%f\n" 2>/dev/null | sort | tail -1' || true)"

smoke_command_status=0
set +e
run_as_target_user env \
  TARGET_PROMPT="$PROMPT" \
  TARGET_HERMES_BIN="$RUNTIME_DIR/hermes-venv/bin/hermes" \
  TARGET_TIMEOUT_SECONDS="$SMOKE_TIMEOUT_SECONDS" \
  bash -lc 'cd "$HOME" && timeout --foreground --kill-after=30s "${TARGET_TIMEOUT_SECONDS}s" "$TARGET_HERMES_BIN" chat -q "$TARGET_PROMPT"' >"$output_file" 2>&1
smoke_command_status=$?
set -e
if [[ "$smoke_command_status" != "0" ]]; then
  echo "Live agent tool smoke command exited with status $smoke_command_status for ${TARGET_DISPLAY_NAME:-$TARGET_UNIX_USER}; inspecting any captured session." >&2
fi
if [[ "$(id -u)" -eq 0 ]]; then
  chown "$TARGET_UNIX_USER" "$output_file"
fi
chmod 0600 "$output_file"

if ! session_id="$(run_as_target_user python3 - "$output_file" "$sessions_dir" "$before_latest_session" <<'PY'
import re
import sys
from pathlib import Path

output_path = Path(sys.argv[1])
sessions_dir = Path(sys.argv[2])
before_latest = sys.argv[3]
text = output_path.read_text(encoding="utf-8", errors="replace")
match = re.search(r"Session:\s+(\S+)", text)
if match:
    print(match.group(1))
    raise SystemExit(0)

latest = ""
for path in sorted(sessions_dir.glob("session_*.json")):
    if path.name > before_latest:
        latest = path.stem.removeprefix("session_")
if latest:
    print(latest)
PY
)"; then
  echo "Could not inspect the live smoke output/session directory for ${TARGET_DISPLAY_NAME:-$TARGET_UNIX_USER}" >&2
  exit 1
fi

if [[ -z "$session_id" ]]; then
  echo "Could not determine the live smoke session id for ${TARGET_DISPLAY_NAME:-$TARGET_UNIX_USER}" >&2
  tail -"$TAIL_LINES" "$output_file" >&2 || true
  if [[ "$smoke_command_status" != "0" ]]; then
    exit "$smoke_command_status"
  fi
  exit 1
fi

session_file="$sessions_dir/session_${session_id}.json"
if ! run_as_target_user test -f "$session_file"; then
  echo "Expected live smoke session file at $session_file" >&2
  exit 1
fi

validation_status=0
set +e
validation_result="$(
run_as_target_user python3 - "$session_file" "$telemetry_path" "$session_id" "$output_file" "$agent_log_path" "$smoke_command_status" <<'PY'
import json
import re
import sys
import time
from pathlib import Path

session_path = Path(sys.argv[1])
telemetry_path = Path(sys.argv[2])
session_id = sys.argv[3]
output_path = Path(sys.argv[4])
agent_log_path = Path(sys.argv[5])
command_status = int(sys.argv[6])


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def provider_auth_failure_seen() -> bool:
    markers = (
        "authentication_error",
        "invalid authentication credentials",
        "error code: 401",
        "credential pool: no available entries",
        "marking anthropic_token exhausted",
    )
    output_text = read_text(output_path)
    log_text = read_text(agent_log_path)
    if session_id and log_text:
        relevant_lines = [
            line
            for line in log_text.splitlines()
            if session_id in line or "credential pool:" in line or "authentication_error" in line
        ]
        log_text = "\n".join(relevant_lines[-80:])
    haystack = (output_text + "\n" + log_text).lower()
    return any(marker in haystack for marker in markers)


def provider_unavailable_seen() -> bool:
    markers = (
        "error code: 503",
        "http 503",
        "no instances available",
        "temporarily unavailable",
        "service unavailable",
        "provider unavailable",
    )
    output_text = read_text(output_path)
    log_text = read_text(agent_log_path)
    if session_id and log_text:
        relevant_lines = [
            line
            for line in log_text.splitlines()
            if session_id in line
            or "error code: 503" in line.lower()
            or "http 503" in line.lower()
            or "no instances available" in line.lower()
            or "service unavailable" in line.lower()
        ]
        log_text = "\n".join(relevant_lines[-80:])
    haystack = (output_text + "\n" + log_text).lower()
    return any(marker in haystack for marker in markers)

tool_token_event = False
if telemetry_path.exists():
    deadline = time.time() + 5.0
    while time.time() < deadline and not tool_token_event:
        for raw_line in telemetry_path.read_text(encoding="utf-8", errors="replace").splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if record.get("session_id") != session_id:
                continue
            if record.get("tool_token_injected") is True:
                tool_token_event = True
                break
        if not tool_token_event:
            time.sleep(0.2)

session = json.loads(session_path.read_text(encoding="utf-8"))
functions: list[str] = []
texts: list[str] = []
assistant_texts: list[str] = []
non_user_texts: list[str] = []
tool_result_texts: list[str] = []
for message in session.get("messages", []):
    role = str(message.get("role") or "")
    for call in message.get("tool_calls") or []:
        name = (((call or {}).get("function") or {}).get("name"))
        if isinstance(name, str) and name:
            functions.append(name)
    content = message.get("content")
    if isinstance(content, str):
        texts.append(content)
        if role in {"tool", "function"}:
            tool_result_texts.append(content)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                texts.append(item["text"])
                if role == "assistant":
                    assistant_texts.append(item["text"])
                if role != "user":
                    non_user_texts.append(item["text"])
                if role in {"tool", "function"} or str(item.get("type") or "") in {"tool_result", "function_call_output"}:
                    tool_result_texts.append(item["text"])
        continue
    if isinstance(content, str):
        if role == "assistant":
            assistant_texts.append(content)
        if role != "user":
            non_user_texts.append(content)

joined = "\n".join(texts)
assistant_joined = "\n".join(assistant_texts)
non_user_joined = "\n".join(non_user_texts)
tool_result_joined = "\n".join(tool_result_texts)
output_joined = read_text(output_path)
errors: list[str] = []
stale_transport_session_seen = "missing or invalid mcp-session-id" in tool_result_joined
brokered_arclink_tool_seen = any(
    name
    in {
        "mcp_arclink_mcp_vault_search_and_fetch",
        "mcp_arclink_mcp_knowledge_search_and_fetch",
    }
    for name in functions
)
brokered_tool_returned = brokered_arclink_tool_seen and bool(tool_result_joined.strip())
command_timed_out = command_status in {124, 137, 143} or (
    command_status != 0
    and "interrupted during api call" in output_joined.lower()
    and "keyboardinterrupt" in output_joined.lower()
)
brokered_tool_succeeded = (
    brokered_arclink_tool_seen
    and bool(tool_result_joined.strip())
    and bool(re.search(r"\b(yes|found|relevant|vault knowledge)\b", assistant_joined, re.IGNORECASE))
)
telemetry_missing_but_brokered_tool_succeeded = not tool_token_event and brokered_tool_succeeded
stale_transport_recovered = (
    stale_transport_session_seen
    and brokered_arclink_tool_seen
    and "missing or invalid mcp-session-id" not in assistant_joined.lower()
    and bool(re.search(r"\b(yes|found|relevant|vault knowledge)\b", assistant_joined, re.IGNORECASE))
)
if not tool_token_event and not telemetry_missing_but_brokered_tool_succeeded:
    errors.append("no tool_token_injected telemetry event was recorded for the smoke session")
if re.search(r"python(?:3)?\s*-\s*<<\s*\S+", assistant_joined):
    errors.append("session content still mentions a python heredoc")
if "arclink-bootstrap-token" in assistant_joined:
    errors.append("session content still mentions the bootstrap token path")
if any(name in {"terminal", "execute_code"} for name in functions):
    errors.append(f"session invoked terminal-style tools: {functions}")
if not brokered_arclink_tool_seen:
    errors.append(f"session did not invoke the brokered ArcLink knowledge/vault MCP rail: {functions}")
if stale_transport_session_seen and not stale_transport_recovered:
    errors.append("session leaked a stale MCP transport-session error to the agent")
if re.search(r"\bcurl\b.*(?:/mcp|127\.0\.0\.1:8[12]8[12])", assistant_joined, re.IGNORECASE | re.DOTALL):
    errors.append("session attempted raw curl/MCP debugging instead of brokered ArcLink tools")
if command_status != 0 and not (command_timed_out and brokered_tool_returned):
    errors.append(f"hermes chat exited with status {command_status}")

if errors:
    if stale_transport_session_seen and not stale_transport_recovered:
        print(
            json.dumps(
                {
                    "retry": "stale_mcp_transport_session",
                    "session_id": session_id,
                    "reason": "a brokered MCP call saw a stale transport session; retry the smoke with a fresh Hermes chat session",
                },
                sort_keys=True,
            )
        )
        raise SystemExit(0)
    if not tool_token_event and not functions and provider_auth_failure_seen():
        print(
            json.dumps(
                {
                    "skipped": "provider_auth_failed",
                    "session_id": session_id,
                    "reason": "model provider rejected the live agent credential before any tool call",
                },
                sort_keys=True,
            )
        )
        raise SystemExit(0)
    if not tool_token_event and not functions and provider_unavailable_seen():
        print(
            json.dumps(
                {
                    "skipped": "provider_unavailable",
                    "session_id": session_id,
                    "reason": "model provider was unavailable before any tool call",
                },
                sort_keys=True,
            )
        )
        raise SystemExit(0)
    raise SystemExit("\n".join(errors))

result = {"session_id": session_id, "functions": functions}
if command_timed_out and brokered_tool_returned:
    result["smoke"] = "timed_out_after_brokered_tool_returned"
    result["command_status"] = command_status
if telemetry_missing_but_brokered_tool_succeeded:
    result["telemetry"] = "missing_tool_token_injected_but_brokered_tool_succeeded"
if stale_transport_recovered:
    result["recovered"] = "stale_mcp_transport_session"
print(json.dumps(result, sort_keys=True))
PY
)"
validation_status=$?
set -e

if [[ "$validation_status" != "0" ]]; then
  echo "Live agent tool smoke failed for ${TARGET_DISPLAY_NAME:-$TARGET_UNIX_USER} during session validation." >&2
  if [[ -n "$validation_result" ]]; then
    echo "$validation_result" >&2
  fi
  echo "Recent output:" >&2
  tail -"$TAIL_LINES" "$output_file" >&2 || true
  exit "$validation_status"
fi

if [[ "$validation_result" == *'"retry": "stale_mcp_transport_session"'* ]]; then
  if [[ "$SMOKE_RETRY_ATTEMPT" == "0" ]]; then
    echo "Live agent tool smoke saw a stale MCP transport session for ${TARGET_DISPLAY_NAME:-$TARGET_UNIX_USER}; retrying once with a fresh chat session."
    rm -f "$output_file"
    export ARCLINK_LIVE_AGENT_SMOKE_RETRY_ATTEMPT=1
    exec "$SCRIPT_DIR/live-agent-tool-smoke.sh" "${ORIGINAL_ARGS[@]}"
  fi
  echo "Live agent tool smoke failed for ${TARGET_DISPLAY_NAME:-$TARGET_UNIX_USER}: stale MCP transport session repeated after one retry." >&2
  echo "$validation_result" >&2
  echo "Recent output:" >&2
  tail -"$TAIL_LINES" "$output_file" >&2 || true
  exit 1
fi

if [[ "$validation_result" == *'"skipped": "provider_auth_failed"'* ]]; then
  echo "Live agent tool smoke skipped for ${TARGET_DISPLAY_NAME:-$TARGET_UNIX_USER}: model provider credentials were rejected before any tool call; ask the user to reauthorize their provider credential."
  echo "$validation_result"
  exit 0
fi
if [[ "$validation_result" == *'"skipped": "provider_unavailable"'* ]]; then
  echo "Live agent tool smoke skipped for ${TARGET_DISPLAY_NAME:-$TARGET_UNIX_USER}: model provider was unavailable before any tool call; rerun when the provider has capacity."
  echo "$validation_result"
  exit 0
fi

echo "Live agent tool smoke ok for ${TARGET_DISPLAY_NAME:-$TARGET_UNIX_USER}: session=$session_id"
echo "$validation_result"
