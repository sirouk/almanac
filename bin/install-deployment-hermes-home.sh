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

"$REPO_DIR/bin/install-arclink-plugins.sh" "$REPO_DIR" "$HERMES_HOME_TARGET"

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
    "display_name": "Chutes",
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
