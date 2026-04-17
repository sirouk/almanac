#!/usr/bin/env bash
set -euo pipefail

SOURCE_PATH="${BASH_SOURCE[0]-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SOURCE_PATH")" && pwd)"
LOCAL_REPO_DIR=""
if [[ -x "$SCRIPT_DIR/bin/init.sh" ]]; then
  LOCAL_REPO_DIR="$SCRIPT_DIR"
fi

MODE=""
FORWARD_ARGS=()
REPO_URL="${ALMANAC_INIT_REPO_URL:-https://github.com/sirouk/almanac.git}"
RAW_INIT_URL="${ALMANAC_INIT_RAW_URL:-https://raw.githubusercontent.com/sirouk/almanac/main/init.sh}"
CACHE_DIR="${ALMANAC_INIT_CACHE_DIR:-$HOME/.cache/almanac-init}"
REPO_DIR="$CACHE_DIR/repo"
TARGET_HOST="${ALMANAC_TARGET_HOST:-}"
TARGET_USER="${ALMANAC_TARGET_USER:-$(id -un 2>/dev/null || printf '')}"
PUBLIC_MCP_URL="${ALMANAC_PUBLIC_MCP_URL:-}"
PUBLIC_MCP_PATH="${ALMANAC_PUBLIC_MCP_PATH:-/almanac-mcp}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    agent|infra|update)
      if [[ -z "$MODE" ]]; then
        MODE="$1"
      else
        FORWARD_ARGS+=("$1")
      fi
      shift
      ;;
    --target-host)
      if [[ $# -lt 2 ]]; then
        echo "--target-host requires a hostname." >&2
        exit 2
      fi
      TARGET_HOST="$2"
      shift 2
      ;;
    --target-user)
      if [[ $# -lt 2 ]]; then
        echo "--target-user requires a username." >&2
        exit 2
      fi
      TARGET_USER="$2"
      shift 2
      ;;
    --public-mcp-url)
      if [[ $# -lt 2 ]]; then
        echo "--public-mcp-url requires a URL." >&2
        exit 2
      fi
      PUBLIC_MCP_URL="$2"
      shift 2
      ;;
    --public-mcp-path)
      if [[ $# -lt 2 ]]; then
        echo "--public-mcp-path requires a path." >&2
        exit 2
      fi
      PUBLIC_MCP_PATH="$2"
      shift 2
      ;;
    *)
      FORWARD_ARGS+=("$1")
      shift
      ;;
  esac
done

MODE="${MODE:-agent}"

current_os() {
  uname -s 2>/dev/null || printf 'unknown'
}

have_tty() {
  [[ -e /dev/tty ]] && (: </dev/tty) 2>/dev/null
}

remote_bootstrap_hint() {
  local host_example="${TARGET_HOST:-kor.tailnet.ts.net}"
  cat >&2 <<EOF
Remote enrollment from a non-Linux client needs the Almanac host.

Use one of these forms:
  curl -fsSL $RAW_INIT_URL | ALMANAC_TARGET_HOST=$host_example bash -s -- $MODE
  curl -fsSL $RAW_INIT_URL | bash -s -- $MODE --target-host $host_example

Note: ALMANAC_TARGET_HOST must be set for bash, not curl. This will not work:
  ALMANAC_TARGET_HOST=$host_example curl -fsSL ... | bash -s -- $MODE
EOF
}

prompt_tty() {
  local prompt="$1"
  local default="${2:-}"
  local answer=""

  if ! have_tty; then
    remote_bootstrap_hint
    return 1
  fi

  if [[ -n "$default" ]]; then
    printf '%s [%s]: ' "$prompt" "$default" >/dev/tty
  else
    printf '%s: ' "$prompt" >/dev/tty
  fi
  IFS= read -r answer </dev/tty || true
  if [[ -z "$answer" ]]; then
    answer="$default"
  fi
  printf '%s\n' "$answer"
}

ensure_repo_cache() {
  if [[ -n "$LOCAL_REPO_DIR" ]]; then
    REPO_DIR="$LOCAL_REPO_DIR"
    return 0
  fi

  mkdir -p "$CACHE_DIR"
  if [[ ! -d "$REPO_DIR/.git" ]]; then
    git clone --depth 1 "$REPO_URL" "$REPO_DIR"
  else
    git -C "$REPO_DIR" pull --ff-only
  fi
}

should_delegate_remote() {
  if [[ -n "$TARGET_HOST" ]]; then
    return 0
  fi

  if [[ "$MODE" == "agent" && "$(current_os)" != "Linux" ]]; then
    return 0
  fi

  return 1
}

exec_real_init() {
  local init_path="$1"
  shift

  if have_tty; then
    exec "$init_path" "$@" </dev/tty
  fi

  exec "$init_path" "$@"
}

remote_bootstrap_url() {
  if [[ -n "$PUBLIC_MCP_URL" ]]; then
    printf '%s\n' "$PUBLIC_MCP_URL"
    return 0
  fi
  printf 'https://%s%s\n' "$TARGET_HOST" "$PUBLIC_MCP_PATH"
}

should_remote_public_bootstrap() {
  [[ "$MODE" == "agent" ]] || return 1
  if [[ -n "$TARGET_HOST" ]]; then
    return 0
  fi
  [[ "$(current_os)" != "Linux" ]]
}

request_remote_enrollment() {
  local bootstrap_url requester_identity request_json

  if [[ -z "$TARGET_HOST" ]]; then
    TARGET_HOST="$(prompt_tty "Target Almanac hostname")"
  fi
  if [[ -z "$TARGET_HOST" ]]; then
    echo "Target Almanac hostname is required." >&2
    exit 1
  fi

  if [[ -z "$TARGET_USER" && -n "${ALMANAC_TARGET_USER:-}" ]]; then
    TARGET_USER="$ALMANAC_TARGET_USER"
  fi
  if [[ -z "$TARGET_USER" ]] && have_tty; then
    TARGET_USER="$(prompt_tty "Unix username to provision on $TARGET_HOST" "$(id -un 2>/dev/null || printf '')")"
  fi
  TARGET_USER="${TARGET_USER:-$(id -un 2>/dev/null || printf '')}"
  if [[ -z "$TARGET_USER" ]]; then
    echo "A Unix username is required for remote enrollment." >&2
    exit 1
  fi

  if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required for remote enrollment." >&2
    exit 1
  fi

  bootstrap_url="$(remote_bootstrap_url)"
  requester_identity="${ALMANAC_REQUESTER_IDENTITY:-$(id -un 2>/dev/null || printf "$TARGET_USER")}"

  request_json="$(
    ALMANAC_REMOTE_BOOTSTRAP_URL="$bootstrap_url" \
    ALMANAC_REMOTE_REQUESTER_IDENTITY="$requester_identity" \
    ALMANAC_REMOTE_UNIX_USER="$TARGET_USER" \
    ALMANAC_REMOTE_MODEL_PRESET="${ALMANAC_INIT_MODEL_PRESET:-}" \
    ALMANAC_REMOTE_CHANNELS="${ALMANAC_INIT_CHANNELS:-}" \
    python3 - <<'PY'
import json
import os
import sys
import urllib.error
import urllib.request


def rpc(url: str, payload: dict, session_id: str | None = None) -> tuple[str | None, dict]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["mcp-session-id"] = session_id
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            parsed = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body) if body.strip() else {}
        except json.JSONDecodeError:
            parsed = {}
        message = (((parsed or {}).get("error") or {}).get("message")) or str(exc)
        raise SystemExit(message) from exc
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(str(exc)) from exc

    if "error" in parsed:
        raise SystemExit(parsed["error"].get("message", "remote enrollment failed"))
    return response.headers.get("mcp-session-id") or session_id, parsed


url = os.environ["ALMANAC_REMOTE_BOOTSTRAP_URL"]
channels = [item.strip() for item in os.environ.get("ALMANAC_REMOTE_CHANNELS", "").split(",") if item.strip()]
arguments = {
    "requester_identity": os.environ["ALMANAC_REMOTE_REQUESTER_IDENTITY"],
    "unix_user": os.environ["ALMANAC_REMOTE_UNIX_USER"],
    "auto_provision": True,
}
if os.environ.get("ALMANAC_REMOTE_MODEL_PRESET"):
    arguments["model_preset"] = os.environ["ALMANAC_REMOTE_MODEL_PRESET"]
if channels:
    arguments["channels"] = channels

session_id, _ = rpc(
    url,
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "almanac-init", "version": "1.0"},
        },
    },
)
rpc(url, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}, session_id)
_, response = rpc(
    url,
    {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "bootstrap.handshake", "arguments": arguments},
    },
    session_id,
)
result = ((response or {}).get("result") or {}).get("structuredContent") or {}
print(json.dumps(result))
PY
  )"

  python3 - "$request_json" "$TARGET_HOST" "$bootstrap_url" "$TARGET_USER" "$requester_identity" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
host = sys.argv[2]
bootstrap_url = sys.argv[3]
unix_user = sys.argv[4]
requester = sys.argv[5]

request_id = payload.get("request_id", "")
status = payload.get("status", "unknown")
agent_id = payload.get("agent_id", "")
resume_existing = bool(payload.get("resume_existing"))

headline = (
    "Enrollment request already pending."
    if resume_existing
    else "Enrollment request submitted."
)
print()
print(headline)
print()
print("Host:")
print(f"  {host}")
print("Requested Unix user:")
print(f"  {unix_user}")
print("Requester identity:")
print(f"  {requester}")
print("Request ID:")
print(f"  {request_id}")
if agent_id:
    print("Planned agent ID:")
    print(f"  {agent_id}")
print("Bootstrap handshake:")
print(f"  {bootstrap_url}")
print("Status:")
print(f"  {status}")
print()
print("Curator/operator approval will create the Unix user and provision the host-side agent.")
print("No host SSH login is required before approval.")
print()
print("Useful follow-up:")
print(f"  Ask the operator to approve request {request_id}")
PY
}

main() {
  if should_remote_public_bootstrap; then
    request_remote_enrollment
    return 0
  fi

  ensure_repo_cache
  exec_real_init "$REPO_DIR/bin/init.sh" "$MODE" "${FORWARD_ARGS[@]}"
}

main "$@"
