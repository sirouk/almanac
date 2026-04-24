#!/usr/bin/env bash
# Periodic per-user-agent refresh:
#   1. hits vaults.refresh to keep the subscription side up-to-date
#   2. fetches agents.managed-memory and materializes the managed-memory
#      stubs in this user's HERMES_HOME (never crosses uid boundaries)
#
# Runs as a systemd user oneshot, every 4h per install-agent-user-services.sh.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MCP_URL="${ALMANAC_MCP_URL:-http://127.0.0.1:${ALMANAC_MCP_PORT:-8282}/mcp}"
HERMES_HOME="${HERMES_HOME:-$HOME/.local/share/almanac-agent/hermes-home}"
TOKEN_FILE="${ALMANAC_BOOTSTRAP_TOKEN_FILE:-$HERMES_HOME/secrets/almanac-bootstrap-token}"
ENROLLMENT_STATE_FILE="${ALMANAC_ENROLLMENT_STATE_FILE:-$HERMES_HOME/state/almanac-enrollment.json}"
ALMANAC_AGENT_ID="${ALMANAC_AGENT_ID:-}"
ALMANAC_AGENTS_STATE_DIR="${ALMANAC_AGENTS_STATE_DIR:-$REPO_DIR/almanac-priv/state/agents}"

if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "Missing bootstrap token file at $TOKEN_FILE" >&2
  exit 1
fi

token="$(tr -d '[:space:]' <"$TOKEN_FILE")"

if [[ -z "$ALMANAC_AGENT_ID" && -f "$ENROLLMENT_STATE_FILE" ]]; then
  ALMANAC_AGENT_ID="$(
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
python3 "$REPO_DIR/python/almanac_rpc_client.py" \
  --url "$MCP_URL" \
  --tool "vaults.refresh" \
  --json-args "$(ALMANAC_REFRESH_TOKEN="$token" python3 - <<'PY'
import json, os
print(json.dumps({"token": os.environ["ALMANAC_REFRESH_TOKEN"]}))
PY
  )" >/dev/null

# 2. materialize the last curator-published managed-memory payload when it is
# available locally and parseable; otherwise fall back to a live fetch. The
# local file is a convenience cache, never a reason to break agent refresh.
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

managed_payload_path=""
managed_payload_source="live"
if [[ -n "$ALMANAC_AGENT_ID" ]]; then
  managed_payload_path="$ALMANAC_AGENTS_STATE_DIR/$ALMANAC_AGENT_ID/managed-memory.json"
fi
if [[ -n "$managed_payload_path" && -r "$managed_payload_path" ]] && python3 - "$managed_payload_path" "$tmp" <<'PY'
import json
import shutil
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
try:
    payload = json.loads(source.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"Ignoring invalid central managed-memory payload at {source}: {exc}", file=sys.stderr)
    raise SystemExit(1)

if not isinstance(payload, dict):
    print(f"Ignoring invalid central managed-memory payload at {source}: not a JSON object", file=sys.stderr)
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
  python3 "$REPO_DIR/python/almanac_rpc_client.py" \
    --url "$MCP_URL" \
    --tool "agents.managed-memory" \
    --json-args "$(ALMANAC_REFRESH_TOKEN="$token" python3 - <<'PY'
import json, os
print(json.dumps({"token": os.environ["ALMANAC_REFRESH_TOKEN"]}))
PY
    )" >"$tmp"
fi

ALMANAC_MANAGED_PAYLOAD="$tmp" ALMANAC_HERMES_HOME="$HERMES_HOME" ALMANAC_MANAGED_PAYLOAD_SOURCE="$managed_payload_source" \
PYTHONPATH="$REPO_DIR/python${PYTHONPATH:+:$PYTHONPATH}" \
python3 - <<'PY'
import json
import os
from pathlib import Path

import almanac_control

payload = json.loads(Path(os.environ["ALMANAC_MANAGED_PAYLOAD"]).read_text())
hermes_home = Path(os.environ["ALMANAC_HERMES_HOME"])
paths = almanac_control.write_managed_memory_stubs(hermes_home=hermes_home, payload=payload)
print(json.dumps({"agent_id": payload["agent_id"], "source": os.environ.get("ALMANAC_MANAGED_PAYLOAD_SOURCE", "live"), **paths}, sort_keys=True))
PY

# 3. drain agent-targeted notifications (SSOT nudges, subscription signals)
# and append them to a local recent-events log so the agent can see them on
# its next session start.
notif_file="$(mktemp)"
trap 'rm -f "$tmp" "$notif_file"' EXIT

python3 "$REPO_DIR/python/almanac_rpc_client.py" \
  --url "$MCP_URL" \
  --tool "agents.consume-notifications" \
  --json-args "$(ALMANAC_REFRESH_TOKEN="$token" python3 - <<'PY'
import json, os
print(json.dumps({"token": os.environ["ALMANAC_REFRESH_TOKEN"], "limit": 200}))
PY
  )" >"$notif_file"

ALMANAC_NOTIF_FILE="$notif_file" ALMANAC_HERMES_HOME="$HERMES_HOME" \
python3 - <<'PY'
import json
import os
from pathlib import Path
import tempfile

notif_path = Path(os.environ["ALMANAC_NOTIF_FILE"])
hermes_home = Path(os.environ["ALMANAC_HERMES_HOME"])
payload = json.loads(notif_path.read_text())


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".almanac-events-", suffix=".tmp")
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
events_path = events_dir / "almanac-recent-events.json"

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
