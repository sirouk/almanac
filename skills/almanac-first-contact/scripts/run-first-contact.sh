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
ENROLLMENT_STATE_FILE="${ALMANAC_ENROLLMENT_STATE_FILE:-$HERMES_HOME/state/almanac-enrollment.json}"
ALMANAC_AGENTS_STATE_DIR="${ALMANAC_AGENTS_STATE_DIR:-$ALMANAC_SHARED_REPO_DIR/almanac-priv/state/agents}"

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
qmd_probe_file="$tmpdir/qmd-probe.json"
notion_probe_file="$tmpdir/notion-probe.json"

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

agent_id=""
if [[ -r "$ENROLLMENT_STATE_FILE" ]]; then
  agent_id="$(
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
managed_payload_path=""
if [[ -n "$agent_id" ]]; then
  managed_payload_path="$ALMANAC_AGENTS_STATE_DIR/$agent_id/managed-memory.json"
fi
if [[ -n "$managed_payload_path" && -r "$managed_payload_path" ]] && python3 - "$managed_payload_path" "$managed_file" <<'PY'
import json
import shutil
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
try:
    payload = json.loads(source.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(1)
if not isinstance(payload, dict):
    raise SystemExit(1)
required = ("agent_id", "vault-ref", "qmd-ref", "catalog", "subscriptions", "vault_path_contract")
if any(key not in payload for key in required):
    raise SystemExit(1)
shutil.copyfile(source, target)
PY
then
  :
else
  "$RPC" --url "$ALMANAC_MCP_URL" --tool "agents.managed-memory" \
    --json-args "$(python3 - "$TOKEN" <<'PY'
import json, sys
print(json.dumps({"token": sys.argv[1]}))
PY
    )" >"$managed_file"
fi

"$RPC" --url "$ALMANAC_MCP_URL" --tool "status" --json-args "{}" >"$status_file"

python3 - "$ALMANAC_QMD_URL" "$qmd_probe_file" <<'PY'
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

qmd_url = sys.argv[1]
output_path = Path(sys.argv[2])
headers = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def fail(message: str) -> "NoReturn":
    raise SystemExit(f"first-contact: {message}")


def post(
    payload: dict[str, object],
    *,
    session_id: str | None = None,
    expect_json: bool = True,
) -> tuple[str | None, dict[str, object] | None]:
    request_headers = dict(headers)
    if session_id:
        request_headers["mcp-session-id"] = session_id
    request = urllib.request.Request(
        qmd_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8")
            response_session_id = response.headers.get("mcp-session-id") or session_id
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        fail(f"qmd probe failed with HTTP {exc.code}: {detail or exc.reason}")
    except OSError as exc:
        fail(f"qmd probe failed: {exc}")
    if not expect_json:
        return response_session_id, None
    if not body.strip():
        fail("qmd probe expected JSON but got an empty response")
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        fail(f"qmd probe returned non-JSON: {body[:200]!r}")
    if not isinstance(parsed, dict):
        fail(f"qmd probe returned unexpected payload: {parsed!r}")
    return response_session_id, parsed


def require_result(payload: dict[str, object], step: str) -> dict[str, object]:
    error = payload.get("error")
    if error is not None:
        fail(f"qmd {step} error: {error}")
    result = payload.get("result")
    if not isinstance(result, dict):
        fail(f"qmd {step} returned no result object")
    return result


session_id, init_payload = post(
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "almanac-first-contact", "version": "1.0"},
        },
    }
)
if init_payload is None:
    fail("qmd initialize returned no payload")
if not session_id:
    fail("qmd initialize did not return mcp-session-id")
init_result = require_result(init_payload, "initialize")
server_info = init_result.get("serverInfo") if isinstance(init_result.get("serverInfo"), dict) else {}
_, _ = post(
    {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
    session_id=session_id,
    expect_json=False,
)
_, tools_payload = post(
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    session_id=session_id,
)
if tools_payload is None:
    fail("qmd tools/list returned no payload")
tools_result = require_result(tools_payload, "tools/list")
tools = tools_result.get("tools")
if not isinstance(tools, list):
    fail("qmd tools/list returned no tools array")
tool_names = [
    str(item.get("name")).strip()
    for item in tools
    if isinstance(item, dict) and str(item.get("name") or "").strip()
]
if "query" not in tool_names:
    fail(f"qmd tools/list did not expose query; saw {tool_names!r}")
_, query_payload = post(
    {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "query",
            "arguments": {
                "searches": [{"type": "lex", "query": "Almanac"}],
                "collections": ["vault"],
                "intent": "Verify qmd retrieval rail during Almanac first-contact",
                "rerank": False,
                "limit": 1,
            },
        },
    },
    session_id=session_id,
)
if query_payload is None:
    fail("qmd tools/call returned no payload")
query_result = require_result(query_payload, "tools/call query")
structured_content = query_result.get("structuredContent") if isinstance(query_result.get("structuredContent"), dict) else {}
results = structured_content.get("results")
result_count = len(results) if isinstance(results, list) else 0
output_path.write_text(
    json.dumps(
        {
            "ok": True,
            "server_name": str(server_info.get("name") or ""),
            "server_version": str(server_info.get("version") or ""),
            "session_header_required": True,
            "tool_names": tool_names,
            "probe_tool": "query",
            "probe_search_type": "lex",
            "probe_collections": ["vault"],
            "probe_result_count": result_count,
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY

notion_expected="0"
if [[ -n "${ALMANAC_NOTION_INDEX_ROOTS:-}" || -n "${ALMANAC_SSOT_NOTION_SPACE_URL:-}" || -n "${ALMANAC_SSOT_NOTION_TOKEN:-}" ]]; then
  notion_expected="1"
fi

if "$RPC" --url "$ALMANAC_MCP_URL" --tool "notion.search" \
  --json-args "$(python3 - "$TOKEN" <<'PY'
import json, sys
print(json.dumps({"token": sys.argv[1], "query": "Almanac", "limit": 3}))
PY
  )" >"$notion_probe_file" 2>"$tmpdir/notion-probe.err"; then
  :
else
  if [[ "$notion_expected" == "1" ]]; then
    echo "first-contact: notion.search probe failed: $(tr '\n' ' ' <"$tmpdir/notion-probe.err" | sed 's/[[:space:]]\\+/ /g')" >&2
    exit 2
  fi
  python3 - "$notion_probe_file" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "ok": False,
            "status": "skipped",
            "reason": "shared Notion knowledge rail is not configured on this host",
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY
fi

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

python3 - "$catalog_file" "$refresh_file" "$status_file" "$managed_file" "$qmd_probe_file" "$notion_probe_file" "$ALMANAC_MCP_URL" "$ALMANAC_QMD_URL" "$HERMES_HOME" <<'PY'
import json
import sys
from pathlib import Path

catalog = json.load(open(sys.argv[1]))
refresh = json.load(open(sys.argv[2]))
status = json.load(open(sys.argv[3]))
managed = json.load(open(sys.argv[4]))
qmd_probe = json.load(open(sys.argv[5]))
notion_probe = json.load(open(sys.argv[6]))
mcp_url, qmd_url, hermes_home = sys.argv[7], sys.argv[8], sys.argv[9]

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
    "qmd_probe": qmd_probe,
    "notion_probe": notion_probe,
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
