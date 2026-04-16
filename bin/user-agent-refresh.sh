#!/usr/bin/env bash
# Periodic per-user-agent refresh:
#   1. hits vaults.refresh to keep the subscription side up-to-date
#   2. fetches agents.managed-memory and materializes the three managed-memory
#      stubs in this user's HERMES_HOME (never crosses uid boundaries)
#
# Runs as a systemd user oneshot, every 4h per install-agent-user-services.sh.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MCP_URL="${ALMANAC_MCP_URL:-http://127.0.0.1:${ALMANAC_MCP_PORT:-8282}/mcp}"
HERMES_HOME="${HERMES_HOME:-$HOME/.local/share/almanac-agent/hermes-home}"
TOKEN_FILE="${ALMANAC_BOOTSTRAP_TOKEN_FILE:-$HERMES_HOME/secrets/almanac-bootstrap-token}"

if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "Missing bootstrap token file at $TOKEN_FILE" >&2
  exit 1
fi

token="$(tr -d '[:space:]' <"$TOKEN_FILE")"

# 1. subscription refresh (also backstops default fanout on the server side)
python3 "$REPO_DIR/python/almanac_rpc_client.py" \
  --url "$MCP_URL" \
  --tool "vaults.refresh" \
  --json-args "$(ALMANAC_REFRESH_TOKEN="$token" python3 - <<'PY'
import json, os
print(json.dumps({"token": os.environ["ALMANAC_REFRESH_TOKEN"]}))
PY
  )" >/dev/null

# 2. fetch managed-memory payload and write stubs locally
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

python3 "$REPO_DIR/python/almanac_rpc_client.py" \
  --url "$MCP_URL" \
  --tool "agents.managed-memory" \
  --json-args "$(ALMANAC_REFRESH_TOKEN="$token" python3 - <<'PY'
import json, os
print(json.dumps({"token": os.environ["ALMANAC_REFRESH_TOKEN"]}))
PY
  )" >"$tmp"

ALMANAC_MANAGED_PAYLOAD="$tmp" ALMANAC_HERMES_HOME="$HERMES_HOME" \
PYTHONPATH="$REPO_DIR/python${PYTHONPATH:+:$PYTHONPATH}" \
python3 - <<'PY'
import json
import os
from pathlib import Path

import almanac_control

payload = json.loads(Path(os.environ["ALMANAC_MANAGED_PAYLOAD"]).read_text())
hermes_home = Path(os.environ["ALMANAC_HERMES_HOME"])
paths = almanac_control.write_managed_memory_stubs(hermes_home=hermes_home, payload=payload)
print(json.dumps({"agent_id": payload["agent_id"], **paths}, sort_keys=True))
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

notif_path = Path(os.environ["ALMANAC_NOTIF_FILE"])
hermes_home = Path(os.environ["ALMANAC_HERMES_HOME"])
payload = json.loads(notif_path.read_text())

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
events_path.write_text(
    json.dumps({
        "agent_id": payload.get("agent_id"),
        "events": combined,
        "last_consumed_count": len(new_events),
    }, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(json.dumps({"consumed": len(new_events), "events_file": str(events_path)}, sort_keys=True))
PY
