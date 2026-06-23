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
    --fleet-shared-dir "${ARCLINK_FLEET_SHARED_ROOT:-}" \
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
from urllib.parse import urlsplit

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
def read_first_line(path_value: str, *, label: str) -> str:
    if not path_value:
        return ""
    path_obj = Path(path_value)
    try:
        lines = path_obj.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        raise SystemExit(f"{label} secret file is configured but cannot be read: {path_obj}") from exc
    value = lines[0].strip() if lines else ""
    if not value:
        raise SystemExit(f"{label} secret file is configured but empty: {path_obj}")
    return value

password_from_file = read_first_line(password_file, label="ArcLink dashboard password")
password = str(os.environ.get("ARCLINK_DASHBOARD_PASSWORD") or password_from_file or existing.get("password") or secrets.token_urlsafe(24))
session_secret = str(existing.get("session_secret") or secrets.token_urlsafe(32))
sso_secret_file = str(os.environ.get("ARCLINK_DASHBOARD_SSO_SECRET_FILE") or "").strip()
sso_secret_from_file = read_first_line(sso_secret_file, label="ArcLink dashboard SSO")
sso_session_secret = str(
    os.environ.get("ARCLINK_DASHBOARD_SSO_SECRET")
    or sso_secret_from_file
    or existing.get("sso_session_secret")
    or ""
).strip()
sso_subject = str(
    os.environ.get("ARCLINK_DASHBOARD_SSO_SUBJECT")
    or os.environ.get("ARCLINK_USER_ID")
    or existing.get("sso_subject")
    or username
).strip()
revocation_env = {
    "dashboard_auth_revoked_before": "ARCLINK_DASHBOARD_AUTH_REVOKED_BEFORE",
    "dashboard_session_revoked_before": "ARCLINK_DASHBOARD_SESSION_REVOKED_BEFORE",
    "dashboard_sso_revoked_before": "ARCLINK_DASHBOARD_SSO_REVOKED_BEFORE",
    "dashboard_auth_revoked_at": "ARCLINK_DASHBOARD_AUTH_REVOKED_AT",
    "dashboard_auth_revoked_by": "ARCLINK_DASHBOARD_AUTH_REVOKED_BY",
    "dashboard_auth_revocation_reason": "ARCLINK_DASHBOARD_AUTH_REVOCATION_REASON",
}
dashboard_url = str(os.environ.get("ARCLINK_HERMES_URL") or os.environ.get("ARCLINK_DASHBOARD_URL") or "").strip()
drive_url = str(os.environ.get("ARCLINK_FILES_URL") or "").strip()
if not drive_url and dashboard_url:
    drive_url = dashboard_url.rstrip("/") + "/drive"
code_url = str(os.environ.get("ARCLINK_CODE_URL") or "").strip()
if not code_url and dashboard_url:
    code_url = dashboard_url.rstrip("/") + "/code"

def clean_crew_dashboards() -> list[dict[str, object]]:
    raw = os.environ.get("ARCLINK_CREW_DASHBOARDS_JSON")
    if raw is None:
        existing_crew = existing.get("crew_dashboards")
        return list(existing_crew) if isinstance(existing_crew, list) else []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    crew: list[dict[str, object]] = []
    for item in parsed[:24]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("hermes_url") or item.get("dashboard_url") or "").strip()
        parsed_url = urlsplit(url)
        if parsed_url.scheme not in {"https", "http"} or not parsed_url.netloc:
            continue
        if parsed_url.scheme == "http" and parsed_url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            continue
        label = str(item.get("label") or item.get("agent_name") or "Hermes Agent").strip()[:120] or "Hermes Agent"
        title = str(item.get("title") or item.get("agent_title") or "").strip()[:160]
        theme_label = str(item.get("theme_label") or "").strip()[:120]
        status = str(item.get("status") or "").strip()[:80]
        deployment_id = str(item.get("deployment_id") or "").strip()[:120]
        crew.append(
            {
                "deployment_id": deployment_id,
                "label": label,
                "title": title,
                "status": status,
                "url": url,
                "current": bool(item.get("current")),
                "bundle_agent_index": int(item.get("bundle_agent_index") or 0) if str(item.get("bundle_agent_index") or "").isdigit() else 0,
                "bundle_agent_count": int(item.get("bundle_agent_count") or 0) if str(item.get("bundle_agent_count") or "").isdigit() else 0,
                "theme_label": theme_label,
            }
        )
    return crew

payload = {
    **existing,
    "auth_scheme": "signed-session",
    "username": username,
    "password": password,
    "session_secret": session_secret,
    "sso_session_secret": sso_session_secret,
    "sso_subject": sso_subject,
    "sso_cookie_domain": str(os.environ.get("ARCLINK_DASHBOARD_SSO_COOKIE_DOMAIN") or existing.get("sso_cookie_domain") or "").strip(),
    "dashboard_url": dashboard_url,
    "drive_url": drive_url,
    "code_url": code_url,
    "crew_dashboards": clean_crew_dashboards(),
    "share_request_broker_url": str(os.environ.get("ARCLINK_SHARE_REQUEST_BROKER_URL") or "").strip(),
    "notion_callback_url": str(os.environ.get("ARCLINK_NOTION_CALLBACK_URL") or "").strip(),
    "notion_root_url": str(
        os.environ.get("ARCLINK_NOTION_ROOT_URL")
        or os.environ.get("ARCLINK_SSOT_NOTION_ROOT_PAGE_URL")
        or os.environ.get("ARCLINK_SSOT_NOTION_SPACE_URL")
        or ""
    ).strip(),
    "deployment_id": str(os.environ.get("ARCLINK_DEPLOYMENT_ID") or "").strip(),
    "prefix": str(os.environ.get("ARCLINK_PREFIX") or "").strip(),
    "captain_name": str(os.environ.get("ARCLINK_CAPTAIN_NAME") or "").strip(),
    "captain_email": str(os.environ.get("ARCLINK_CAPTAIN_EMAIL") or "").strip(),
}
for key, env_name in revocation_env.items():
    value = str(os.environ.get(env_name) or "").strip()
    if value:
        payload[key] = value
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

agent_name="${ARCLINK_AGENT_NAME:-}"
if [[ -z "$agent_name" ]]; then
  agent_name="${ARCLINK_PREFIX:-ArcLink} Hermes"
fi
agent_title="${ARCLINK_AGENT_TITLE:-}"
captain_name="${ARCLINK_CAPTAIN_NAME:-${ARCLINK_USER_NAME:-${ARCLINK_PREFIX:-ArcLink}}}"

HERMES_HOME="$HERMES_HOME_TARGET" "$PYTHON_BIN" \
  "$REPO_DIR/python/arclink_headless_hermes_setup.py" \
  --identity-only \
  --bot-name "$agent_name" \
  --agent-title "$agent_title" \
  --unix-user "arclink" \
  --user-name "$captain_name" >/dev/null

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
    --bot-name "$agent_name" \
    --agent-title "$agent_title" \
    --unix-user "arclink" \
    --user-name "$captain_name" >/dev/null
fi

ready_file="${ARCLINK_HERMES_HOME_READY_FILE:-$HERMES_HOME_TARGET/state/arclink-hermes-home-ready.json}"
"$PYTHON_BIN" - "$ready_file" "$HERMES_HOME_TARGET" <<'PY'
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ready_path = Path(sys.argv[1])
hermes_home = Path(sys.argv[2])
plugins = {}
for name in ("drive", "code", "terminal", "arclink-managed-context"):
    root = hermes_home / "plugins" / name
    plugins[name] = {
        "plugin": (root / "plugin.yaml").is_file(),
        "module": (root / "__init__.py").is_file(),
        "dashboard": (root / "dashboard" / "manifest.json").is_file(),
    }

payload = {
    "status": "ready",
    "ready_at": datetime.now(timezone.utc).isoformat(),
    "deployment_id": str(os.environ.get("ARCLINK_DEPLOYMENT_ID") or "").strip(),
    "prefix": str(os.environ.get("ARCLINK_PREFIX") or "").strip(),
    "agent_name": str(os.environ.get("ARCLINK_AGENT_NAME") or "").strip(),
    "plugins": plugins,
}
ready_path.parent.mkdir(parents=True, exist_ok=True)
fd, tmp_name = tempfile.mkstemp(dir=str(ready_path.parent), prefix=".arclink-hermes-home-ready-", suffix=".tmp")
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_name, ready_path)
finally:
    try:
        os.unlink(tmp_name)
    except FileNotFoundError:
        pass
ready_path.chmod(0o600)
PY
