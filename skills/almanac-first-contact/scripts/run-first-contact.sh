#!/usr/bin/env bash
set -euo pipefail

# first-contact verification: check MCPs are reachable, pull vault catalog,
# run a subscription refresh, materialize the managed-memory stubs, and
# emit a JSON summary. Called by init.sh right after agent registration and
# also available as an operator diagnostic.

: "${ALMANAC_MCP_URL:?ALMANAC_MCP_URL is required}"
: "${ALMANAC_QMD_URL:?ALMANAC_QMD_URL is required}"
: "${ALMANAC_BOOTSTRAP_TOKEN_FILE:?ALMANAC_BOOTSTRAP_TOKEN_FILE is required}"
: "${ALMANAC_SHARED_REPO_DIR:?ALMANAC_SHARED_REPO_DIR is required}"

HERMES_HOME="${HERMES_HOME:-$HOME/.local/share/almanac-agent/hermes-home}"

if [[ ! -r "$ALMANAC_BOOTSTRAP_TOKEN_FILE" ]]; then
  echo "first-contact: cannot read bootstrap token at $ALMANAC_BOOTSTRAP_TOKEN_FILE" >&2
  exit 2
fi

TOKEN="$(tr -d '[:space:]' <"$ALMANAC_BOOTSTRAP_TOKEN_FILE")"
RPC="$ALMANAC_SHARED_REPO_DIR/bin/almanac-rpc"

if [[ ! -x "$RPC" ]]; then
  echo "first-contact: missing $RPC" >&2
  exit 2
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

catalog_file="$tmpdir/catalog.json"
refresh_file="$tmpdir/refresh.json"
status_file="$tmpdir/status.json"
managed_file="$tmpdir/managed.json"

"$RPC" --url "$ALMANAC_MCP_URL" --tool "catalog.vaults" \
  --json-args "$(python3 - "$TOKEN" <<'PY'
import json, sys
print(json.dumps({"token": sys.argv[1]}))
PY
  )" >"$catalog_file"

"$RPC" --url "$ALMANAC_MCP_URL" --tool "vaults.refresh" \
  --json-args "$(python3 - "$TOKEN" <<'PY'
import json, sys
print(json.dumps({"token": sys.argv[1]}))
PY
  )" >"$refresh_file"

"$RPC" --url "$ALMANAC_MCP_URL" --tool "agents.managed-memory" \
  --json-args "$(python3 - "$TOKEN" <<'PY'
import json, sys
print(json.dumps({"token": sys.argv[1]}))
PY
  )" >"$managed_file"

"$RPC" --url "$ALMANAC_MCP_URL" --tool "status" --json-args "{}" >"$status_file"

# Materialize the managed-memory stubs in this user's HERMES_HOME.
ALMANAC_MANAGED_PAYLOAD="$managed_file" ALMANAC_HERMES_HOME="$HERMES_HOME" \
PYTHONPATH="$ALMANAC_SHARED_REPO_DIR/python${PYTHONPATH:+:$PYTHONPATH}" \
python3 - <<'PY' >/dev/null
import json
import os
from pathlib import Path

import almanac_control

payload = json.loads(Path(os.environ["ALMANAC_MANAGED_PAYLOAD"]).read_text())
hermes_home = Path(os.environ["ALMANAC_HERMES_HOME"])
almanac_control.write_managed_memory_stubs(hermes_home=hermes_home, payload=payload)
PY

python3 - "$catalog_file" "$refresh_file" "$status_file" "$managed_file" "$ALMANAC_MCP_URL" "$ALMANAC_QMD_URL" "$HERMES_HOME" <<'PY'
import json
import sys
from pathlib import Path

catalog = json.load(open(sys.argv[1]))
refresh = json.load(open(sys.argv[2]))
status = json.load(open(sys.argv[3]))
managed = json.load(open(sys.argv[4]))
mcp_url, qmd_url, hermes_home = sys.argv[5], sys.argv[6], sys.argv[7]

vaults = catalog.get("vaults") or []
default_subs = [v["vault_name"] for v in vaults if v.get("default_subscribed") and v.get("subscribed")]
non_default_subs = [v["vault_name"] for v in vaults if v.get("subscribed") and not v.get("default_subscribed")]
unsubscribed = [v["vault_name"] for v in vaults if not v.get("subscribed")]

state_path = Path(hermes_home) / "state" / "almanac-vault-reconciler.json"
stub_path = Path(hermes_home) / "memories" / "almanac-managed-stubs.md"

summary = {
    "ok": True,
    "mcp_url": mcp_url,
    "qmd_url": qmd_url,
    "agent_id": managed.get("agent_id"),
    "vault_warning_count": status.get("vault_warning_count", 0),
    "active_subscriptions": refresh.get("active_subscriptions", []),
    "default_subscriptions_applied": sorted(default_subs),
    "user_subscriptions": sorted(non_default_subs),
    "unsubscribed_vaults": sorted(unsubscribed),
    "catalog_size": len(vaults),
    "managed_memory": {
        "state_path": str(state_path),
        "stub_path": str(stub_path),
        "state_written": state_path.is_file(),
        "stub_written": stub_path.is_file(),
    },
}

if status.get("vault_warning_count", 0) > 0:
    summary["warnings"] = status.get("vault_warnings") or []

print(json.dumps(summary, indent=2, sort_keys=True))
PY
