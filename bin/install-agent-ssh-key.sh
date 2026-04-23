#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: install-agent-ssh-key.sh --unix-user <user> [--pubkey-file <path>|--pubkey <key>]

Install a public SSH key for one enrolled Unix user so a tailnet-only remote
Hermes wrapper can connect over SSH.
EOF
}

UNIX_USER=""
PUBKEY_FILE=""
PUBKEY_VALUE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --unix-user)
      UNIX_USER="${2:-}"
      shift 2
      ;;
    --pubkey-file)
      PUBKEY_FILE="${2:-}"
      shift 2
      ;;
    --pubkey)
      PUBKEY_VALUE="${2:-}"
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

if [[ -z "$UNIX_USER" ]]; then
  usage
  exit 2
fi

if [[ -z "$PUBKEY_VALUE" && -n "$PUBKEY_FILE" ]]; then
  PUBKEY_VALUE="$(cat "$PUBKEY_FILE")"
fi
if [[ -z "$PUBKEY_VALUE" ]]; then
  PUBKEY_VALUE="$(cat)"
fi
PUBKEY_VALUE="$(printf '%s' "$PUBKEY_VALUE" | tr -d '\r' | sed 's/[[:space:]]*$//')"

if [[ ! "$PUBKEY_VALUE" =~ ^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384|ecdsa-sha2-nistp521)[[:space:]]+[A-Za-z0-9+/=]+([[:space:]].*)?$ ]]; then
  echo "Refusing to install an invalid SSH public key." >&2
  exit 1
fi

if ! id "$UNIX_USER" >/dev/null 2>&1; then
  echo "Unix user does not exist: $UNIX_USER" >&2
  exit 1
fi

HOME_DIR="$(getent passwd "$UNIX_USER" | cut -d: -f6)"
if [[ -z "$HOME_DIR" ]]; then
  echo "Could not resolve home directory for $UNIX_USER" >&2
  exit 1
fi

ALLOWED_FROM="${ALMANAC_AGENT_REMOTE_SSH_FROM:-100.64.0.0/10,fd7a:115c:a1e0::/48}"
KEY_OPTIONS="from=\"$ALLOWED_FROM\",no-agent-forwarding,no-port-forwarding,no-user-rc,no-X11-forwarding"
AUTHORIZED_KEY_LINE="$KEY_OPTIONS $PUBKEY_VALUE"

SSH_DIR="$HOME_DIR/.ssh"
AUTH_KEYS="$SSH_DIR/authorized_keys"
mkdir -p "$SSH_DIR"
touch "$AUTH_KEYS"
chmod 700 "$SSH_DIR"
chmod 600 "$AUTH_KEYS"
chown "$UNIX_USER:$UNIX_USER" "$SSH_DIR" "$AUTH_KEYS"

if ! grep -Fqx "$AUTHORIZED_KEY_LINE" "$AUTH_KEYS"; then
  tmp_file="$(mktemp)"
  python3 - "$AUTH_KEYS" "$tmp_file" "$PUBKEY_VALUE" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
pubkey = sys.argv[3].strip()
parts = pubkey.split()
key_type = parts[0]
key_body = parts[1]
pattern = re.compile(
    r"(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384|ecdsa-sha2-nistp521)\s+([A-Za-z0-9+/=]+)(?:\s+.*)?$"
)
kept: list[str] = []
for raw_line in src.read_text(encoding="utf-8").splitlines():
    line = raw_line.rstrip("\n")
    if not line.strip():
        kept.append(line)
        continue
    match = pattern.search(line)
    if match and match.group(1) == key_type and match.group(2) == key_body:
        continue
    kept.append(line)
dst.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
PY
  mv "$tmp_file" "$AUTH_KEYS"
  printf '%s\n' "$AUTHORIZED_KEY_LINE" >>"$AUTH_KEYS"
fi

chown "$UNIX_USER:$UNIX_USER" "$AUTH_KEYS"
echo "Installed SSH key for $UNIX_USER at $AUTH_KEYS"
