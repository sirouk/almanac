#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

ensure_layout
if [[ ! -x "$RUNTIME_DIR/hermes-venv/bin/hermes" ]]; then
  echo "Hermes is not installed for curator at $RUNTIME_DIR/hermes-venv/bin/hermes" >&2
  exit 1
fi

export HERMES_HOME="$ALMANAC_CURATOR_HERMES_HOME"
mkdir -p "$HERMES_HOME"

if ! has_curator_gateway_channels; then
  echo "Curator messaging gateway is not configured; nothing to start." >&2
  exit 0
fi

hermes_env_file="$HERMES_HOME/.env"
if [[ ",${ALMANAC_CURATOR_CHANNELS:-tui-only}," == *",telegram,"* ]]; then
  hermes_telegram_token="$(env_file_value "$hermes_env_file" "TELEGRAM_BOT_TOKEN")"
  if [[ -z "$hermes_telegram_token" && -n "${TELEGRAM_BOT_TOKEN:-}" ]]; then
    export TELEGRAM_BOT_TOKEN
  fi

  if [[ "${OPERATOR_NOTIFY_CHANNEL_PLATFORM:-}" == "telegram" && -n "${OPERATOR_NOTIFY_CHANNEL_ID:-}" ]]; then
    if [[ -z "$(env_file_value "$hermes_env_file" "TELEGRAM_ALLOWED_USERS")" && -z "${TELEGRAM_ALLOWED_USERS:-}" ]]; then
      export TELEGRAM_ALLOWED_USERS="$OPERATOR_NOTIFY_CHANNEL_ID"
    fi
    if [[ -z "$(env_file_value "$hermes_env_file" "TELEGRAM_HOME_CHANNEL")" && -z "${TELEGRAM_HOME_CHANNEL:-}" ]]; then
      export TELEGRAM_HOME_CHANNEL="$OPERATOR_NOTIFY_CHANNEL_ID"
    fi
  fi

  if [[ -z "$(env_file_value "$hermes_env_file" "TELEGRAM_BOT_TOKEN")" && -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
    echo "Curator Telegram gateway is enabled but TELEGRAM_BOT_TOKEN is missing from both $hermes_env_file and almanac.env." >&2
    exit 1
  fi
fi

exec "$RUNTIME_DIR/hermes-venv/bin/hermes" gateway
