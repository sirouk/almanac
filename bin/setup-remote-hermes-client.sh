#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: setup-remote-hermes-client.sh [--host tailnet-host] [--user remote-unix-user] [--org organization-name] [--key-path ~/.ssh/key]

Create a local SSH/tailnet wrapper that starts Hermes on a remote
Almanac-enrolled user account. This is remote-agent control, not local Hermes
with a remote terminal backend.
EOF
}

TARGET_HOST="${ALMANAC_REMOTE_HERMES_HOST:-}"
TARGET_USER="${ALMANAC_REMOTE_HERMES_USER:-}"
TARGET_ORG="${ALMANAC_REMOTE_HERMES_ORG:-}"
KEY_PATH="${ALMANAC_REMOTE_HERMES_KEY_PATH:-$HOME/.ssh/almanac-remote-hermes-ed25519}"

is_tailnet_host() {
  python3 - "$1" <<'PY'
from __future__ import annotations

import ipaddress
import sys

host = sys.argv[1].strip().lower()
if host.endswith(".ts.net"):
    raise SystemExit(0)

try:
    ip = ipaddress.ip_address(host)
except ValueError:
    raise SystemExit(1)

if ip.version == 4 and ip in ipaddress.ip_network("100.64.0.0/10"):
    raise SystemExit(0)
if ip.version == 6 and ip in ipaddress.ip_network("fd7a:115c:a1e0::/48"):
    raise SystemExit(0)
raise SystemExit(1)
PY
}

slugify_label() {
  python3 - "$1" <<'PY'
from __future__ import annotations

import re
import sys

value = sys.argv[1].strip().lower()
value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
print(value)
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      TARGET_HOST="${2:-}"
      shift 2
      ;;
    --user)
      TARGET_USER="${2:-}"
      shift 2
      ;;
    --org|--org-name)
      TARGET_ORG="${2:-}"
      shift 2
      ;;
    --key-path)
      KEY_PATH="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

prompt_tty() {
  local prompt="$1"
  local default="${2:-}"
  local answer=""
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

if [[ -z "$TARGET_HOST" && -t 0 ]]; then
  TARGET_HOST="$(prompt_tty "Tailnet hostname for your remote Hermes agent")"
fi
if [[ -z "$TARGET_USER" && -t 0 ]]; then
  TARGET_USER="$(prompt_tty "Remote Unix user for your agent lane" "$(id -un 2>/dev/null || printf '')")"
fi
if [[ -z "$TARGET_ORG" && -t 0 ]]; then
  TARGET_ORG="$(prompt_tty "Organization label for the local wrapper name (optional)")"
fi

if [[ -z "$TARGET_HOST" || -z "$TARGET_USER" ]]; then
  echo "Both --host and --user are required." >&2
  exit 1
fi

if ! is_tailnet_host "$TARGET_HOST"; then
  echo "Remote Hermes connectivity is restricted to Tailscale tailnet hosts (.ts.net or Tailscale IPs)." >&2
  exit 1
fi

mkdir -p "$(dirname "$KEY_PATH")" "$HOME/.local/bin"
if [[ ! -f "$KEY_PATH" ]]; then
  key_comment="almanac-remote-hermes@$(hostname -s 2>/dev/null || printf 'client')"
  ssh-keygen -q -t ed25519 -N '' -C "$key_comment" -f "$KEY_PATH"
fi
chmod 600 "$KEY_PATH"
chmod 644 "${KEY_PATH}.pub"

if command -v ssh-keyscan >/dev/null 2>&1; then
  mkdir -p "$HOME/.ssh"
  touch "$HOME/.ssh/known_hosts"
  if ! ssh-keygen -F "$TARGET_HOST" -f "$HOME/.ssh/known_hosts" >/dev/null 2>&1; then
    ssh-keyscan -H "$TARGET_HOST" >>"$HOME/.ssh/known_hosts" 2>/dev/null || true
  fi
fi

user_slug="$(slugify_label "$TARGET_USER")"
org_slug="$(slugify_label "$TARGET_ORG")"
if [[ -z "$org_slug" ]]; then
  org_slug="$(slugify_label "$TARGET_HOST")"
fi
if [[ -z "$user_slug" || -z "$org_slug" ]]; then
  echo "Could not derive a safe wrapper name from --user/--org." >&2
  exit 1
fi
wrapper_path="$HOME/.local/bin/hermes-${org_slug}-remote-${user_slug}"

cat >"$wrapper_path" <<EOF
#!/usr/bin/env bash
set -euo pipefail
remote_cmd='exec "\$HOME/.local/bin/almanac-agent-hermes"'
for arg in "\$@"; do
  printf -v quoted '%q' "\$arg"
  remote_cmd+=" \$quoted"
done
ssh_tty_args=()
if [[ -t 0 && -t 1 ]]; then
  ssh_tty_args=(-t)
fi
exec ssh \\
  -i "$KEY_PATH" \\
  -o IdentitiesOnly=yes \\
  -o BatchMode=yes \\
  -o StrictHostKeyChecking=yes \\
  "\${ssh_tty_args[@]}" \\
  "$TARGET_USER@$TARGET_HOST" \\
  "\$remote_cmd"
EOF
chmod 755 "$wrapper_path"

cat <<EOF
Remote Hermes client prepared
  wrapper: $wrapper_path
  target: $TARGET_USER@$TARGET_HOST
  organization: ${TARGET_ORG:-$TARGET_HOST}

What this does:
  The wrapper runs Hermes on the remote Almanac host inside your agent lane.
  It uses the remote Hermes config, skills, MCP tools, plugins, and files.
  Do not run your local 'hermes' command for this path; run the wrapper below.

Reply to Curator with:
  /ssh-key $(cat "${KEY_PATH}.pub")

Curator will bind that key to Unix user $TARGET_USER and install it on the host with Tailscale-only SSH restrictions.
After Curator confirms the key is installed, run:
  $wrapper_path chat
EOF
