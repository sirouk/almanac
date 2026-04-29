#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_REPO_DIR="$(cd "$SKILL_DIR/../.." && pwd)"
DEFAULT_SHARED_REPO_DIR="/home/almanac/almanac"
MCP_URL="${ALMANAC_MCP_URL:-http://127.0.0.1:${ALMANAC_MCP_PORT:-8282}/mcp}"
HERMES_HOME="${HERMES_HOME:-$HOME/.local/share/almanac-agent/hermes-home}"
REPO_DIR="${ALMANAC_REPO_DIR:-${ALMANAC_SHARED_REPO_DIR:-}}"
if [[ -z "$REPO_DIR" && -f "$SOURCE_REPO_DIR/python/almanac_rpc_client.py" ]]; then
  REPO_DIR="$SOURCE_REPO_DIR"
fi
if [[ -z "$REPO_DIR" && -f "$DEFAULT_SHARED_REPO_DIR/python/almanac_rpc_client.py" ]]; then
  REPO_DIR="$DEFAULT_SHARED_REPO_DIR"
fi
if [[ -z "$REPO_DIR" || ! -f "$REPO_DIR/python/almanac_rpc_client.py" ]]; then
  echo "curate-vaults: cannot locate Almanac repo with python/almanac_rpc_client.py; set ALMANAC_REPO_DIR" >&2
  exit 2
fi
TOKEN_FILE="${ALMANAC_BOOTSTRAP_TOKEN_FILE:-${ALMANAC_BOOTSTRAP_TOKEN_PATH:-$HERMES_HOME/secrets/almanac-bootstrap-token}}"
JSON_MODE="0"

usage() {
  cat <<'EOF'
Usage: scripts/curate-vaults.sh [--json] <curate|list|refresh|stubs|subscribe|unsubscribe> [vault-name]

Commands:
  curate        Refresh subscriptions, fetch catalog + plugin-context payload, and print a curation summary.
  list          Fetch the current vault catalog for this agent.
  refresh       Run vaults.refresh for this agent.
  stubs         Fetch the canonical plugin-context payload for this agent.
  subscribe     Subscribe the current agent to <vault-name> and trigger curator fanout.
  unsubscribe   Unsubscribe the current agent from <vault-name> and trigger curator fanout.

Environment:
  ALMANAC_MCP_URL            Override control-plane MCP URL.
  ALMANAC_BOOTSTRAP_TOKEN_FILE / ALMANAC_BOOTSTRAP_TOKEN_PATH
                             Path to the agent bootstrap token.
  HERMES_HOME                Defaults token path under the current agent home.
EOF
}

if [[ $# -gt 0 && "$1" == "--json" ]]; then
  JSON_MODE="1"
  shift
fi

COMMAND="${1:-curate}"
shift || true
VAULT_NAME="${1:-}"

if [[ ! -r "$TOKEN_FILE" ]]; then
  echo "curate-vaults: cannot read bootstrap token at $TOKEN_FILE" >&2
  exit 2
fi
TOKEN="$(tr -d '[:space:]' <"$TOKEN_FILE")"
RPC=(python3 "$REPO_DIR/python/almanac_rpc_client.py" --url "$MCP_URL")

call_tool() {
  local tool_name="$1"
  local payload_json="$2"
  "${RPC[@]}" --tool "$tool_name" --json-args "$payload_json"
}

auth_payload() {
  python3 - "$TOKEN" <<'PY'
import json
import sys
print(json.dumps({"token": sys.argv[1]}))
PY
}

subscribe_payload() {
  local vault_name="$1"
  local subscribed="$2"
  python3 - "$TOKEN" "$vault_name" "$subscribed" <<'PY'
import json
import sys
print(json.dumps({
    "token": sys.argv[1],
    "vault_name": sys.argv[2],
    "subscribed": sys.argv[3].lower() in {"1", "true", "yes", "on"},
}))
PY
}

catalog_json() {
  call_tool "catalog.vaults" "$(auth_payload)"
}

refresh_json() {
  call_tool "vaults.refresh" "$(auth_payload)"
}

managed_json() {
  call_tool "agents.managed-memory" "$(auth_payload)"
}

if [[ "$COMMAND" == "list" ]]; then
  payload="$(catalog_json)"
  if [[ "$JSON_MODE" == "1" ]]; then
    printf '%s\n' "$payload"
    exit 0
  fi
  python3 - "$payload" <<'PY'
import json, sys
payload = json.loads(sys.argv[1])
vaults = payload.get("vaults") or []
print(f"Vault catalog ({len(vaults)} vaults):")
for vault in vaults:
    mark = "+" if vault.get("subscribed") else ("·" if vault.get("default_subscribed") else "-")
    desc = (vault.get("description") or "").strip()
    print(f"  {mark} {vault.get('vault_name')}: {desc}")
PY
  exit 0
fi

if [[ "$COMMAND" == "refresh" ]]; then
  payload="$(refresh_json)"
  if [[ "$JSON_MODE" == "1" ]]; then
    printf '%s\n' "$payload"
    exit 0
  fi
  python3 - "$payload" <<'PY'
import json, sys
payload = json.loads(sys.argv[1])
active = payload.get("active_subscriptions") or []
print("Active subscriptions after refresh:")
for name in active:
    print(f"  + {name}")
if not active:
    print("  (none)")
print(f"qmd_url: {payload.get('qmd_url')}")
PY
  exit 0
fi

if [[ "$COMMAND" == "stubs" ]]; then
  payload="$(managed_json)"
  if [[ "$JSON_MODE" == "1" ]]; then
    printf '%s\n' "$payload"
    exit 0
  fi
  python3 - "$payload" <<'PY'
import json, sys
payload = json.loads(sys.argv[1])
print(f"agent_id: {payload.get('agent_id')}")
for key in ("almanac-skill-ref", "vault-ref", "qmd-ref", "vault-topology"):
    print(f"\n[{key}]")
    print(str(payload.get(key) or "").strip())
PY
  exit 0
fi

if [[ "$COMMAND" == "subscribe" || "$COMMAND" == "unsubscribe" ]]; then
  if [[ -z "$VAULT_NAME" ]]; then
    usage >&2
    exit 2
  fi
  desired="0"
  if [[ "$COMMAND" == "subscribe" ]]; then
    desired="1"
  fi
  result="$(call_tool "vaults.subscribe" "$(subscribe_payload "$VAULT_NAME" "$desired")")"
  if [[ "$JSON_MODE" == "1" ]]; then
    printf '%s\n' "$result"
    exit 0
  fi
  python3 - "$result" <<'PY'
import json, sys
payload = json.loads(sys.argv[1])
state = "subscribed" if payload.get("subscribed") else "unsubscribed"
print(f"{payload.get('agent_id')}: {payload.get('vault_name')} -> {state}")
print("Curator brief-fanout has been queued; the per-user refresh rail will update plugin-managed context.")
PY
  exit 0
fi

if [[ "$COMMAND" != "curate" ]]; then
  usage >&2
  exit 2
fi

catalog_payload="$(catalog_json)"
refresh_payload="$(refresh_json)"
managed_payload="$(managed_json)"
combined="$(python3 - "$catalog_payload" "$refresh_payload" "$managed_payload" <<'PY'
import json, sys
catalog = json.loads(sys.argv[1])
refresh = json.loads(sys.argv[2])
managed = json.loads(sys.argv[3])
vaults = catalog.get("vaults") or []
subscribed = sorted(v.get("vault_name") for v in vaults if v.get("subscribed"))
default_only = sorted(v.get("vault_name") for v in vaults if (not v.get("subscribed")) and v.get("default_subscribed"))
unsubscribed = sorted(v.get("vault_name") for v in vaults if not v.get("subscribed") and not v.get("default_subscribed"))
payload = {
    "agent_id": managed.get("agent_id") or refresh.get("agent_id"),
    "qmd_url": refresh.get("qmd_url") or managed.get("qmd_url"),
    "active_subscriptions": refresh.get("active_subscriptions") or subscribed,
    "subscribed_vaults": subscribed,
    "default_unsubscribed_vaults": default_only,
    "explicitly_unsubscribed_vaults": unsubscribed,
    "vault_topology": managed.get("vault-topology") or "",
    "catalog": vaults,
    "managed_memory_keys": [
        key for key in ("almanac-skill-ref", "vault-ref", "qmd-ref", "vault-topology")
        if managed.get(key)
    ],
    "trigger_contract": {
        "subscription_change": "vaults.subscribe queues curator brief-fanout for the targeted agent",
        "catalog_reload": "vault catalog diffs queue curator brief-fanout for all active agents",
        "delivery_worker": "notification delivery runs curator fanout and publishes central managed-memory payloads for plugin context",
        "agent_refresh": "almanac-user-agent-refresh rewrites local plugin-managed context state on timer and activation-trigger path changes",
    },
}
print(json.dumps(payload, sort_keys=True))
PY
)"

if [[ "$JSON_MODE" == "1" ]]; then
  printf '%s\n' "$combined"
  exit 0
fi

python3 - "$combined" <<'PY'
import json, sys
payload = json.loads(sys.argv[1])
print(f"agent_id: {payload.get('agent_id')}")
print(f"qmd_url:  {payload.get('qmd_url')}")
print("")
print("Stub-aware vault curation:")
for name in payload.get("subscribed_vaults") or []:
    print(f"  + {name}")
for name in payload.get("default_unsubscribed_vaults") or []:
    print(f"  · {name} (default, not currently subscribed)")
for name in payload.get("explicitly_unsubscribed_vaults") or []:
    print(f"  - {name}")
print("")
print("Managed-memory keys present:")
for key in payload.get("managed_memory_keys") or []:
    print(f"  - {key}")
print("")
print("Trigger rail:")
for key, value in (payload.get("trigger_contract") or {}).items():
    print(f"  - {key}: {value}")
print("")
print("[managed:vault-topology]")
print(payload.get("vault_topology") or "")
PY
