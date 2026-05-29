#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${ARCLINK_REPO_DIR:-/home/arclink/arclink}"
HERMES_HOME_TARGET="${HERMES_HOME:-/home/arclink/arclink/arclink-priv/state/operator/hermes-home}"
OPERATOR_STATE_DIR="${ARCLINK_OPERATOR_STATE_DIR:-/home/arclink/arclink/arclink-priv/state/operator}"
OPERATOR_SECRET_DIR="${ARCLINK_OPERATOR_SECRET_DIR:-$OPERATOR_STATE_DIR/secrets}"
RUNTIME_DIR_TARGET="${RUNTIME_DIR:-/opt/arclink/runtime}"
PYTHON_BIN="$RUNTIME_DIR_TARGET/hermes-venv/bin/python3"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "python3 is required to seed the Operator Hermes home." >&2
  exit 1
fi

mkdir -p "$HERMES_HOME_TARGET/state" "$OPERATOR_SECRET_DIR"

(
  flock 9

  if [[ -n "${CHUTES_API_KEY:-}" && -z "${ARCLINK_CHUTES_API_KEY_FILE:-}" ]]; then
    umask 077
    printf '%s' "$CHUTES_API_KEY" >"$OPERATOR_SECRET_DIR/chutes_api_key"
    export ARCLINK_CHUTES_API_KEY_FILE="$OPERATOR_SECRET_DIR/chutes_api_key"
  fi

  export ARCLINK_DEPLOYMENT_ID="${ARCLINK_DEPLOYMENT_ID:-operator}"
  export ARCLINK_USER_ID="${ARCLINK_USER_ID:-operator}"
  export ARCLINK_PREFIX="${ARCLINK_PREFIX:-operator}"
  export ARCLINK_AGENT_NAME="${ARCLINK_AGENT_NAME:-Operator Hermes}"
  export ARCLINK_AGENT_TITLE="${ARCLINK_AGENT_TITLE:-ArcLink Operator Hermes}"
  export ARCLINK_CAPTAIN_NAME="${ARCLINK_CAPTAIN_NAME:-ArcLink Operator}"
  export ARCLINK_CAPTAIN_EMAIL="${ARCLINK_CAPTAIN_EMAIL:-${ARCLINK_OPERATOR_AGENT_EMAIL:-}}"
  export ARCLINK_DASHBOARD_USERNAME="${ARCLINK_DASHBOARD_USERNAME:-${ARCLINK_OPERATOR_AGENT_EMAIL:-operator}}"

  HERMES_HOME="$HERMES_HOME_TARGET" "$REPO_DIR/bin/install-deployment-hermes-home.sh" \
    "$REPO_DIR" "$HERMES_HOME_TARGET"

  "$PYTHON_BIN" - "$REPO_DIR/templates/SOUL.operator.md.tmpl" "$HERMES_HOME_TARGET/SOUL.md" <<'PY'
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from string import Template

template_path = Path(sys.argv[1])
target = Path(sys.argv[2])
template = Template(template_path.read_text(encoding="utf-8"))
values = {
    "repo_dir": os.environ.get("ARCLINK_REPO_DIR", "/home/arclink/arclink"),
    "priv_dir": os.environ.get("ARCLINK_PRIV_DIR", "/home/arclink/arclink/arclink-priv"),
    "db_path": os.environ.get("ARCLINK_DB_PATH", "/home/arclink/arclink/arclink-priv/state/arclink-control.sqlite3"),
    "vault_dir": os.environ.get("VAULT_DIR", "/home/arclink/arclink/arclink-priv/state/operator/vault"),
    "control_api": os.environ.get("ARCLINK_API_INTERNAL_URL", "http://control-api:8900"),
    "upgrade_broker": os.environ.get("ARCLINK_OPERATOR_UPGRADE_BROKER_URL", "http://operator-upgrade-broker:8917"),
    "gateway_broker": os.environ.get("ARCLINK_GATEWAY_EXEC_BROKER_URL", "http://gateway-exec-broker:8911"),
    "operator_channel": os.environ.get("OPERATOR_NOTIFY_CHANNEL_ID", ""),
}
text = template.safe_substitute(values)
target.parent.mkdir(parents=True, exist_ok=True)
fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=".SOUL.operator-", suffix=".tmp")
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
        if not text.endswith("\n"):
            handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_name, target)
finally:
    try:
        os.unlink(tmp_name)
    except FileNotFoundError:
        pass
target.chmod(0o600)
PY
) 9>"$HERMES_HOME_TARGET/state/operator-install.lock"
