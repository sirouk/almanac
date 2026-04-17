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

gateway_home="$ALMANAC_CURATOR_HERMES_HOME"

if has_curator_telegram_onboarding; then
  if ! has_curator_non_telegram_gateway_channels; then
    echo "Curator Telegram onboarding owns the Telegram bot token; Hermes gateway stays disabled to avoid polling conflicts." >&2
    exit 0
  fi

  gateway_home="$RUNTIME_DIR/curator-gateway-home"
  mkdir -p "$gateway_home"

  python3 - "$ALMANAC_CURATOR_HERMES_HOME" "$gateway_home" <<'PY'
from pathlib import Path
import shutil
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
target.mkdir(parents=True, exist_ok=True)

for existing in list(target.iterdir()):
    if existing.name == ".env":
        continue
    source_entry = source / existing.name
    if source_entry.exists() or source_entry.is_symlink():
        continue
    if existing.is_dir() and not existing.is_symlink():
        shutil.rmtree(existing)
    else:
        existing.unlink()

if source.exists():
    for entry in source.iterdir():
        if entry.name == ".env":
            continue
        link_path = target / entry.name
        if link_path.exists() or link_path.is_symlink():
            if link_path.is_symlink() and link_path.resolve() == entry.resolve():
                continue
            if link_path.is_dir() and not link_path.is_symlink():
                shutil.rmtree(link_path)
            else:
                link_path.unlink()
        link_path.symlink_to(entry)

skip = {
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_ALLOWED_USERS",
    "TELEGRAM_ALLOW_ALL_USERS",
    "TELEGRAM_HOME_CHANNEL",
    "TELEGRAM_HOME_CHANNEL_NAME",
    "TELEGRAM_REPLY_TO_MODE",
    "TELEGRAM_FALLBACK_IPS",
}
source_env = source / ".env"
target_env = target / ".env"
lines = []
if source_env.exists():
    for raw_line in source_env.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if stripped and not stripped.startswith("#") and "=" in raw_line:
            key = raw_line.split("=", 1)[0].strip()
            if key in skip:
                continue
        lines.append(raw_line)
payload = "\n".join(lines)
if payload:
    payload += "\n"
    target_env.write_text(payload, encoding="utf-8")
else:
    target_env.write_text("", encoding="utf-8")
target_env.chmod(0o600)
PY

  unset TELEGRAM_BOT_TOKEN TELEGRAM_ALLOWED_USERS TELEGRAM_ALLOW_ALL_USERS
  unset TELEGRAM_HOME_CHANNEL TELEGRAM_HOME_CHANNEL_NAME TELEGRAM_REPLY_TO_MODE TELEGRAM_FALLBACK_IPS
fi

export HERMES_HOME="$gateway_home"
hermes_env_file="$HERMES_HOME/.env"
if ! has_curator_telegram_onboarding && [[ ",${ALMANAC_CURATOR_CHANNELS:-tui-only}," == *",telegram,"* ]]; then
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
