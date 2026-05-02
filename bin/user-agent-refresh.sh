#!/usr/bin/env bash
# Periodic per-user-agent refresh:
#   1. hits vaults.refresh to keep the subscription side up-to-date
#   2. fetches agents.managed-memory and materializes plugin-managed
#      context state in this user's HERMES_HOME (never crosses uid boundaries)
#
# Runs as a systemd user oneshot, every 4h per install-agent-user-services.sh.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MCP_URL="${ARCLINK_MCP_URL:-http://127.0.0.1:${ARCLINK_MCP_PORT:-8282}/mcp}"
HERMES_HOME="${HERMES_HOME:-$HOME/.local/share/arclink-agent/hermes-home}"
TOKEN_FILE="${ARCLINK_BOOTSTRAP_TOKEN_FILE:-$HERMES_HOME/secrets/arclink-bootstrap-token}"
ENROLLMENT_STATE_FILE="${ARCLINK_ENROLLMENT_STATE_FILE:-$HERMES_HOME/state/arclink-enrollment.json}"
ARCLINK_AGENT_ID="${ARCLINK_AGENT_ID:-}"
ARCLINK_AGENTS_STATE_DIR="${ARCLINK_AGENTS_STATE_DIR:-$REPO_DIR/arclink-priv/state/agents}"

if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "Missing bootstrap token file at $TOKEN_FILE" >&2
  exit 1
fi

token="$(tr -d '[:space:]' <"$TOKEN_FILE")"
tmp="$(mktemp)"
notif_file="$(mktemp)"
rpc_args_file="$(mktemp)"
chmod 600 "$tmp" "$notif_file" "$rpc_args_file" || true
trap 'rm -f "$tmp" "$notif_file" "$rpc_args_file"' EXIT

write_rpc_args() {
  local output_file="$1"
  local limit="${2:-}"
  ARCLINK_REFRESH_TOKEN="$token" ARCLINK_REFRESH_LIMIT="$limit" python3 - "$output_file" <<'PY'
import json
import os
import sys
from pathlib import Path

payload = {"token": os.environ["ARCLINK_REFRESH_TOKEN"]}
limit = os.environ.get("ARCLINK_REFRESH_LIMIT", "").strip()
if limit:
    payload["limit"] = int(limit)
Path(sys.argv[1]).write_text(json.dumps(payload) + "\n", encoding="utf-8")
PY
}

if [[ -z "$ARCLINK_AGENT_ID" && -f "$ENROLLMENT_STATE_FILE" ]]; then
  ARCLINK_AGENT_ID="$(
    python3 - "$ENROLLMENT_STATE_FILE" <<'PY'
import json
import sys

try:
    data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
except Exception:
    print("")
    raise SystemExit(0)

print(str(data.get("agent_id", "")))
PY
  )"
fi

if [[ -x "$REPO_DIR/bin/activate-agent.sh" ]]; then
  "$REPO_DIR/bin/activate-agent.sh"
fi

if [[ -f "$ENROLLMENT_STATE_FILE" ]]; then
  enrollment_status="$(
    python3 - "$ENROLLMENT_STATE_FILE" <<'PY'
import json
import sys

try:
    data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
except Exception:
    print("")
    raise SystemExit(0)

print(str(data.get("status", "")))
PY
  )"
  if [[ "$enrollment_status" != "active" ]]; then
    exit 0
  fi
fi

# 1. subscription refresh (also backstops default fanout on the server side)
write_rpc_args "$rpc_args_file"
python3 "$REPO_DIR/python/arclink_rpc_client.py" \
  --url "$MCP_URL" \
  --tool "vaults.refresh" \
  --json-args-file "$rpc_args_file" >/dev/null

# 2. materialize the last curator-published managed-memory payload into plugin
# context state when it is
# available locally and parseable; otherwise fall back to a live fetch. The
# local file is a convenience cache, never a reason to break agent refresh.

managed_payload_path=""
managed_payload_source="live"
if [[ -n "$ARCLINK_AGENT_ID" ]]; then
  managed_payload_path="$ARCLINK_AGENTS_STATE_DIR/$ARCLINK_AGENT_ID/managed-memory.json"
fi
if [[ -n "$managed_payload_path" && -r "$managed_payload_path" ]] && python3 - "$managed_payload_path" "$tmp" "${ARCLINK_AGENT_ID:-}" <<'PY'
import json
import shutil
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
expected_agent_id = str(sys.argv[3] or "").strip()
try:
    payload = json.loads(source.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"Ignoring invalid central managed-memory payload at {source}: {exc}", file=sys.stderr)
    raise SystemExit(1)

if not isinstance(payload, dict):
    print(f"Ignoring invalid central managed-memory payload at {source}: not a JSON object", file=sys.stderr)
    raise SystemExit(1)

payload_agent_id = str(payload.get("agent_id") or "").strip()
if expected_agent_id and payload_agent_id != expected_agent_id:
    print(
        f"Ignoring central managed-memory payload at {source}: agent_id mismatch",
        file=sys.stderr,
    )
    raise SystemExit(1)

required = ("agent_id", "vault-ref", "qmd-ref", "catalog", "subscriptions", "vault_path_contract")
missing = [key for key in required if key not in payload]
if missing:
    print(
        f"Ignoring incomplete central managed-memory payload at {source}: missing {', '.join(missing)}",
        file=sys.stderr,
    )
    raise SystemExit(1)

shutil.copyfile(source, target)
PY
then
  managed_payload_source="central"
else
  write_rpc_args "$rpc_args_file"
  python3 "$REPO_DIR/python/arclink_rpc_client.py" \
    --url "$MCP_URL" \
    --tool "agents.managed-memory" \
    --json-args-file "$rpc_args_file" >"$tmp"
fi

ARCLINK_MANAGED_PAYLOAD="$tmp" ARCLINK_HERMES_HOME="$HERMES_HOME" ARCLINK_MANAGED_PAYLOAD_SOURCE="$managed_payload_source" \
PYTHONPATH="$REPO_DIR/python${PYTHONPATH:+:$PYTHONPATH}" \
python3 - <<'PY'
import json
import os
from pathlib import Path

import arclink_control

payload = json.loads(Path(os.environ["ARCLINK_MANAGED_PAYLOAD"]).read_text())
hermes_home = Path(os.environ["ARCLINK_HERMES_HOME"])
paths = arclink_control.write_managed_memory_stubs(hermes_home=hermes_home, payload=payload)
print(json.dumps({"agent_id": payload["agent_id"], "source": os.environ.get("ARCLINK_MANAGED_PAYLOAD_SOURCE", "live"), **paths}, sort_keys=True))
PY

# 3. drain agent-targeted notifications (SSOT nudges, subscription signals)
# and append them to a local recent-events log so the agent can see them on
# its next session start.

write_rpc_args "$rpc_args_file" 200
python3 "$REPO_DIR/python/arclink_rpc_client.py" \
  --url "$MCP_URL" \
  --tool "agents.consume-notifications" \
  --json-args-file "$rpc_args_file" >"$notif_file"

ARCLINK_NOTIF_FILE="$notif_file" ARCLINK_HERMES_HOME="$HERMES_HOME" \
python3 - <<'PY'
import json
import os
from pathlib import Path
import tempfile

notif_path = Path(os.environ["ARCLINK_NOTIF_FILE"])
hermes_home = Path(os.environ["ARCLINK_HERMES_HOME"])
payload = json.loads(notif_path.read_text())


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".arclink-events-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

events_dir = hermes_home / "state"
events_dir.mkdir(parents=True, exist_ok=True)
events_path = events_dir / "arclink-recent-events.json"

existing: list = []
if events_path.is_file():
    try:
        existing = json.loads(events_path.read_text()).get("events", [])
    except Exception:
        existing = []

new_events = payload.get("notifications", []) or []
# keep the last 200 events total
combined = (existing + new_events)[-200:]
atomic_write_text(
    events_path,
    json.dumps({
        "agent_id": payload.get("agent_id"),
        "events": combined,
        "last_consumed_count": len(new_events),
    }, indent=2, sort_keys=True) + "\n",
)
print(json.dumps({"consumed": len(new_events), "events_file": str(events_path)}, sort_keys=True))
PY
