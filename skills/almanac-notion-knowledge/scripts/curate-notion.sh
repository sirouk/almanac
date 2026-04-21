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
  echo "curate-notion: cannot locate Almanac repo with python/almanac_rpc_client.py; set ALMANAC_REPO_DIR" >&2
  exit 2
fi
TOKEN_FILE="${ALMANAC_BOOTSTRAP_TOKEN_FILE:-${ALMANAC_BOOTSTRAP_TOKEN_PATH:-$HERMES_HOME/secrets/almanac-bootstrap-token}}"
JSON_MODE="0"

usage() {
  cat <<'EOF'
Usage: scripts/curate-notion.sh [--json] <search|fetch|query> [args...]

Commands:
  search <query>                        Search shared Notion knowledge.
  fetch <page-or-database-id-or-url>   Fetch one exact live page or database.
  query <database-id-or-url> [json]    Run a live structured database query.

Environment:
  ALMANAC_MCP_URL                      Override control-plane MCP URL.
  ALMANAC_BOOTSTRAP_TOKEN_FILE / ALMANAC_BOOTSTRAP_TOKEN_PATH
                                       Path to the agent bootstrap token.
  HERMES_HOME                          Defaults token path under the current agent home.
EOF
}

if [[ $# -gt 0 && "$1" == "--json" ]]; then
  JSON_MODE="1"
  shift
fi

COMMAND="${1:-search}"
shift || true

if [[ ! -r "$TOKEN_FILE" ]]; then
  echo "curate-notion: cannot read bootstrap token at $TOKEN_FILE" >&2
  exit 2
fi
TOKEN="$(tr -d '[:space:]' <"$TOKEN_FILE")"
RPC=(python3 "$REPO_DIR/python/almanac_rpc_client.py" --url "$MCP_URL")

call_tool() {
  local tool_name="$1"
  local payload_json="$2"
  "${RPC[@]}" --tool "$tool_name" --json-args "$payload_json"
}

if [[ "$COMMAND" == "search" ]]; then
  QUERY="${*:-}"
  if [[ -z "$QUERY" ]]; then
    usage >&2
    exit 2
  fi
  payload="$(
    python3 - "$TOKEN" "$QUERY" <<'PY'
import json
import sys
print(json.dumps({"token": sys.argv[1], "query": sys.argv[2], "limit": 5}))
PY
  )"
  result="$(call_tool "notion.search" "$payload")"
  if [[ "$JSON_MODE" == "1" ]]; then
    printf '%s\n' "$result"
    exit 0
  fi
  python3 - "$result" <<'PY'
import json, sys
payload = json.loads(sys.argv[1])
results = payload.get("results") or []
print(f"Shared Notion search: {len(results)} hit(s)")
for hit in results:
    title = str(hit.get("page_title") or hit.get("page_id") or "untitled")
    section = str(hit.get("section_heading") or "").strip()
    breadcrumb = " > ".join(str(part) for part in (hit.get("breadcrumb") or []) if str(part).strip())
    url = str(hit.get("page_url") or "").strip()
    print(f"- {title}")
    if section:
        print(f"  section: {section}")
    if breadcrumb:
        print(f"  breadcrumb: {breadcrumb}")
    if url:
        print(f"  url: {url}")
PY
  exit 0
fi

if [[ "$COMMAND" == "fetch" ]]; then
  TARGET="${1:-}"
  if [[ -z "$TARGET" ]]; then
    usage >&2
    exit 2
  fi
  payload="$(
    python3 - "$TOKEN" "$TARGET" <<'PY'
import json
import sys
print(json.dumps({"token": sys.argv[1], "target_id": sys.argv[2]}))
PY
  )"
  result="$(call_tool "notion.fetch" "$payload")"
  if [[ "$JSON_MODE" == "1" ]]; then
    printf '%s\n' "$result"
    exit 0
  fi
  python3 - "$result" <<'PY'
import json, sys
payload = json.loads(sys.argv[1])
kind = str(payload.get("target_kind") or "")
print(f"Fetched shared Notion {kind}: {payload.get('target_id')}")
if kind == "page":
    page = payload.get("page") or {}
    title = ""
    properties = page.get("properties") if isinstance(page, dict) else {}
    if isinstance(properties, dict):
        for prop in properties.values():
            if isinstance(prop, dict) and str(prop.get("type") or "") == "title":
                title = "".join(str(item.get("plain_text") or "") for item in prop.get("title") or [] if isinstance(item, dict)).strip()
                if title:
                    break
    if title:
        print(f"title: {title}")
    print(payload.get("markdown") or "")
else:
    database = payload.get("database") or {}
    print(json.dumps(database, indent=2, sort_keys=True))
PY
  exit 0
fi

if [[ "$COMMAND" == "query" ]]; then
  TARGET="${1:-}"
  QUERY_JSON="${2:-{}}"
  if [[ -z "$TARGET" ]]; then
    usage >&2
    exit 2
  fi
  payload="$(
    python3 - "$TOKEN" "$TARGET" "$QUERY_JSON" <<'PY'
import json
import sys
query = json.loads(sys.argv[3]) if sys.argv[3].strip() else {}
print(json.dumps({"token": sys.argv[1], "target_id": sys.argv[2], "query": query, "limit": 25}))
PY
  )"
  result="$(call_tool "notion.query" "$payload")"
  if [[ "$JSON_MODE" == "1" ]]; then
    printf '%s\n' "$result"
    exit 0
  fi
  python3 - "$result" <<'PY'
import json, sys
payload = json.loads(sys.argv[1])
results = payload.get("results") or []
print(f"Shared Notion query: {len(results)} row(s)")
for item in results:
    title = ""
    properties = item.get("properties") if isinstance(item, dict) else {}
    if isinstance(properties, dict):
        for prop in properties.values():
            if isinstance(prop, dict) and str(prop.get("type") or "") == "title":
                title = "".join(str(entry.get("plain_text") or "") for entry in prop.get("title") or [] if isinstance(entry, dict)).strip()
                if title:
                    break
    print(f"- {title or item.get('id') or 'untitled'}")
PY
  exit 0
fi

usage >&2
exit 2
