#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${1:-/home/arclink/arclink}"
HERMES_HOME_TARGET="${2:-${HERMES_HOME:-/home/arclink/.hermes}}"
RUNTIME_DIR_TARGET="${RUNTIME_DIR:-/opt/arclink/runtime}"
PYTHON_BIN="$RUNTIME_DIR_TARGET/hermes-venv/bin/python3"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "python3 is required to seed the deployment Hermes home." >&2
  exit 1
fi

"$REPO_DIR/bin/sync-hermes-bundled-skills.sh" "$HERMES_HOME_TARGET" "$RUNTIME_DIR_TARGET"
"$REPO_DIR/bin/install-arclink-skills.sh" "$REPO_DIR" "$HERMES_HOME_TARGET"
"$REPO_DIR/bin/install-arclink-plugins.sh" "$REPO_DIR" "$HERMES_HOME_TARGET"
if [[ -x "$REPO_DIR/bin/migrate-hermes-config.sh" ]]; then
  HERMES_HOME="$HERMES_HOME_TARGET" "$REPO_DIR/bin/migrate-hermes-config.sh" "$HERMES_HOME_TARGET" "$RUNTIME_DIR_TARGET" >/dev/null
fi

if [[ -n "${VAULT_DIR:-}" ]]; then
  mkdir -p "$VAULT_DIR"
  hermes_skills_args=()
  if [[ -d "$RUNTIME_DIR_TARGET/hermes-agent-src/skills" ]]; then
    hermes_skills_args=(--hermes-skills-dir "$RUNTIME_DIR_TARGET/hermes-agent-src/skills")
  fi
  "$PYTHON_BIN" "$REPO_DIR/bin/reconcile-vault-layout.py" \
    --repo-dir "$REPO_DIR" \
    --vault-dir "$VAULT_DIR" \
    "${hermes_skills_args[@]}"
  if [[ "${ARCLINK_HERMES_DOCS_SYNC_ENABLED:-1}" == "1" ]]; then
    docs_state_dir="${ARCLINK_HERMES_DOCS_STATE_DIR:-/tmp/arclink-hermes-docs-src}"
    docs_vault_dir="${ARCLINK_HERMES_DOCS_VAULT_DIR:-$VAULT_DIR/Agents_KB/hermes-agent-docs}"
    if ! ARCLINK_CONFIG_FILE=/dev/null \
      ARCLINK_ALLOW_SCAFFOLD_DEFAULTS=1 \
      ARCLINK_PRIV_DIR=/tmp/arclink-priv \
      ARCLINK_PRIV_CONFIG_DIR=/tmp/arclink-priv/config \
      STATE_DIR=/tmp/arclink-state \
      RUNTIME_DIR="$RUNTIME_DIR_TARGET" \
      VAULT_DIR="$VAULT_DIR" \
      ARCLINK_HERMES_DOCS_STATE_DIR="$docs_state_dir" \
      ARCLINK_HERMES_DOCS_VAULT_DIR="$docs_vault_dir" \
      "$REPO_DIR/bin/sync-hermes-docs-into-vault.sh"; then
      echo "Hermes docs sync failed; continuing with the existing vault contents." >&2
    fi
  fi
fi

mkdir -p "$HERMES_HOME_TARGET/state"
"$PYTHON_BIN" - "$HERMES_HOME_TARGET/state/arclink-web-access.json" <<'PY'
from __future__ import annotations

import json
import os
import secrets
import sys
import tempfile
from pathlib import Path

path = Path(os.environ.get("ARCLINK_HERMES_DASHBOARD_ACCESS_FILE") or sys.argv[1])
try:
    existing = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(existing, dict):
        existing = {}
except Exception:
    existing = {}

username = str(os.environ.get("ARCLINK_DASHBOARD_USERNAME") or existing.get("username") or os.environ.get("ARCLINK_PREFIX") or "arclink").strip().lower()
username = "".join(ch for ch in username if ch.isalnum() or ch in "@._-").strip(".-_") or "arclink"
password_file = str(os.environ.get("ARCLINK_DASHBOARD_PASSWORD_FILE") or "").strip()
password_from_file = ""
if password_file:
    try:
        password_from_file = Path(password_file).read_text(encoding="utf-8").splitlines()[0].strip()
    except Exception:
        password_from_file = ""
password = str(os.environ.get("ARCLINK_DASHBOARD_PASSWORD") or password_from_file or existing.get("password") or secrets.token_urlsafe(24))
session_secret = str(existing.get("session_secret") or secrets.token_urlsafe(32))
payload = {
    **existing,
    "auth_scheme": "signed-session",
    "username": username,
    "password": password,
    "session_secret": session_secret,
    "dashboard_url": str(os.environ.get("ARCLINK_HERMES_URL") or ""),
    "drive_url": (str(os.environ.get("ARCLINK_HERMES_URL") or "").rstrip("/") + "/drive") if os.environ.get("ARCLINK_HERMES_URL") else "",
    "code_url": (str(os.environ.get("ARCLINK_HERMES_URL") or "").rstrip("/") + "/code") if os.environ.get("ARCLINK_HERMES_URL") else "",
}
path.parent.mkdir(parents=True, exist_ok=True)
fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".arclink-web-access-", suffix=".tmp")
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_name, path)
finally:
    try:
        os.unlink(tmp_name)
    except FileNotFoundError:
        pass
path.chmod(0o600)
PY

provider="${ARCLINK_PRIMARY_PROVIDER:-chutes}"
secret_file="${ARCLINK_CHUTES_API_KEY_FILE:-/run/secrets/chutes_api_key}"
if [[ "$provider" == "chutes" && -r "$secret_file" && -s "$secret_file" ]]; then
  provider_spec="$(
    "$PYTHON_BIN" - <<'PY'
import json
import os

print(json.dumps({
    "preset": "chutes",
    "provider_id": "chutes",
    "model_id": os.environ.get("ARCLINK_CHUTES_DEFAULT_MODEL", "moonshotai/Kimi-K2.6-TEE"),
    "display_name": "Chutes provider",
    "auth_flow": "api-key",
    "key_env": "CHUTES_API_KEY",
    "base_url": os.environ.get("ARCLINK_CHUTES_BASE_URL", "https://llm.chutes.ai/v1"),
    "api_mode": "chat_completions",
    "is_custom": True,
    "reasoning_effort": os.environ.get("ARCLINK_MODEL_REASONING_DEFAULT", "medium"),
}, sort_keys=True))
PY
  )"
  HERMES_HOME="$HERMES_HOME_TARGET" "$PYTHON_BIN" \
    "$REPO_DIR/python/arclink_headless_hermes_setup.py" \
    --provider-spec-json "$provider_spec" \
    --secret-path "$secret_file" \
    --bot-name "${ARCLINK_PREFIX:-ArcLink} Hermes" \
    --unix-user "arclink" \
    --user-name "${ARCLINK_PREFIX:-ArcLink}" >/dev/null
fi
