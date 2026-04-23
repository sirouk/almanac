#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

require_real_layout "live agent tool smoke"
ensure_layout

TARGET_UNIX_USER="${1:-}"
PROMPT="${ALMANAC_LIVE_AGENT_SMOKE_PROMPT:-Use the Almanac vault catalog rail to tell me my current subscribed vaults in one short sentence. Do not use terminal, python heredocs, or read any secrets files.}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is unavailable; cannot run live agent tool smoke." >&2
  exit 1
fi

if [[ ! -x "$RUNTIME_DIR/hermes-venv/bin/hermes" ]]; then
  echo "Hermes runtime missing at $RUNTIME_DIR/hermes-venv/bin/hermes" >&2
  exit 1
fi

agent_json="$(python3 - "$ALMANAC_DB_PATH" "$TARGET_UNIX_USER" <<'PY'
import json
import sqlite3
import sys

db_path = sys.argv[1]
target_unix_user = (sys.argv[2] or "").strip()

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
if target_unix_user:
    row = conn.execute(
        """
        SELECT unix_user, hermes_home, display_name
        FROM agents
        WHERE role = 'user' AND status = 'active' AND unix_user = ?
        ORDER BY unix_user
        LIMIT 1
        """,
        (target_unix_user,),
    ).fetchone()
else:
    row = conn.execute(
        """
        SELECT unix_user, hermes_home, display_name
        FROM agents
        WHERE role = 'user' AND status = 'active'
        ORDER BY unix_user
        LIMIT 1
        """
    ).fetchone()

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

if [[ ! -d "$TARGET_HERMES_HOME" ]]; then
  echo "Active agent hermes home is missing at $TARGET_HERMES_HOME" >&2
  exit 1
fi

telemetry_path="$TARGET_HERMES_HOME/state/almanac-context-telemetry.jsonl"
sessions_dir="$TARGET_HERMES_HOME/sessions"
output_file="$(mktemp /tmp/almanac-live-agent-smoke.XXXXXX.log)"
trap 'rm -f "$output_file"' EXIT

before_latest_session="$(find "$sessions_dir" -maxdepth 1 -type f -name 'session_*.json' -printf '%f\n' 2>/dev/null | sort | tail -1 || true)"

if ! runuser -u "$TARGET_UNIX_USER" -- env TARGET_HERMES_HOME="$TARGET_HERMES_HOME" TARGET_PROMPT="$PROMPT" TARGET_HERMES_BIN="$RUNTIME_DIR/hermes-venv/bin/hermes" \
  bash -lc 'cd "$HOME" && HERMES_HOME="$TARGET_HERMES_HOME" timeout 90 "$TARGET_HERMES_BIN" chat -q "$TARGET_PROMPT"' >"$output_file" 2>&1; then
  echo "Live agent tool smoke failed for ${TARGET_DISPLAY_NAME:-$TARGET_UNIX_USER}. Recent output:" >&2
  tail -40 "$output_file" >&2 || true
  exit 1
fi

session_id="$(python3 - "$output_file" "$sessions_dir" "$before_latest_session" <<'PY'
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
)"

if [[ -z "$session_id" ]]; then
  echo "Could not determine the live smoke session id for ${TARGET_DISPLAY_NAME:-$TARGET_UNIX_USER}" >&2
  tail -20 "$output_file" >&2 || true
  exit 1
fi

session_file="$sessions_dir/session_${session_id}.json"
if [[ ! -f "$session_file" ]]; then
  echo "Expected live smoke session file at $session_file" >&2
  exit 1
fi

python3 - "$session_file" "$telemetry_path" "$session_id" <<'PY'
import json
import re
import sys
import time
from pathlib import Path

session_path = Path(sys.argv[1])
telemetry_path = Path(sys.argv[2])
session_id = sys.argv[3]

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
for message in session.get("messages", []):
    for call in message.get("tool_calls") or []:
        name = (((call or {}).get("function") or {}).get("name"))
        if isinstance(name, str) and name:
            functions.append(name)
    content = message.get("content")
    if isinstance(content, str):
        texts.append(content)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                texts.append(item["text"])

joined = "\n".join(texts)
errors: list[str] = []
if not tool_token_event:
    errors.append("no tool_token_injected telemetry event was recorded for the smoke session")
if re.search(r"python(?:3)?\s*-\s*<<\s*\S+", joined):
    errors.append("session content still mentions a python heredoc")
if "almanac-bootstrap-token" in joined:
    errors.append("session content still mentions the bootstrap token path")
if any(name in {"terminal", "execute_code"} for name in functions):
    errors.append(f"session invoked terminal-style tools: {functions}")

if errors:
    raise SystemExit("\n".join(errors))

print(json.dumps({"session_id": session_id, "functions": functions}, sort_keys=True))
PY

echo "Live agent tool smoke ok for ${TARGET_DISPLAY_NAME:-$TARGET_UNIX_USER}: session=$session_id"
