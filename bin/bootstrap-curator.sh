#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

ask_default() {
  local prompt="$1"
  local default="${2:-}"
  local answer=""
  if [[ -n "$default" ]]; then
    read -r -p "$prompt [$default]: " answer
  else
    read -r -p "$prompt: " answer
  fi
  printf '%s' "${answer:-$default}"
}

confirm_default() {
  local prompt="$1"
  local default="${2:-yes}"
  local answer=""
  local hint="Y/n"

  [[ "$default" == "no" ]] && hint="y/N"
  read -r -p "$prompt [$hint]: " answer
  answer="${answer:-$default}"
  [[ "${answer,,}" =~ ^(y|yes|1)$ ]]
}

choose_model_preset() {
  local default="${ALMANAC_CURATOR_MODEL_PRESET:-codex}"
  local answer=""
  if [[ -n "${ALMANAC_CURATOR_MODEL_PRESET:-}" ]]; then
    printf '%s\n' "$ALMANAC_CURATOR_MODEL_PRESET"
    return 0
  fi
  cat <<EOF
Curator model preset
  1) codex  -> $ALMANAC_MODEL_PRESET_CODEX
  2) opus   -> $ALMANAC_MODEL_PRESET_OPUS
  3) chutes -> $ALMANAC_MODEL_PRESET_CHUTES
EOF
  answer="$(ask_default "Choose model preset" "$default")"
  case "$answer" in
    1|codex) printf '%s\n' "codex" ;;
    2|opus) printf '%s\n' "opus" ;;
    3|chutes) printf '%s\n' "chutes" ;;
    *) printf '%s\n' "$default" ;;
  esac
}

choose_channels_csv() {
  if [[ -n "${ALMANAC_CURATOR_CHANNELS:-}" ]]; then
    printf '%s\n' "$ALMANAC_CURATOR_CHANNELS"
    return 0
  fi

  local discord="" telegram="" channels="tui-only"
  discord="$(ask_default "Enable Discord for Curator gateway? (yes/no)" "no")"
  telegram="$(ask_default "Enable Telegram for Curator gateway? (yes/no)" "no")"
  if [[ "${discord,,}" =~ ^(y|yes|1)$ ]]; then
    channels="$channels,discord"
  fi
  if [[ "${telegram,,}" =~ ^(y|yes|1)$ ]]; then
    channels="$channels,telegram"
  fi
  printf '%s\n' "$channels"
}

print_gateway_setup_guidance() {
  local channels_csv="$1"

  if [[ "$channels_csv" != *discord* && "$channels_csv" != *telegram* ]]; then
    return 0
  fi

  cat <<EOF

Curator chat gateway notes:
  - The operator notification channel is separate from Curator's user-facing chat
    gateway. A Discord webhook or Telegram operator chat ID only delivers
    operator notices; it does not make Curator reachable to users.

EOF

  if [[ "$channels_csv" == *discord* ]]; then
    cat <<EOF
Discord:
  - In the Discord Developer Portal, use a real bot application and invite it
    with the \`bot\` and \`applications.commands\` scopes.
  - In any server where users should discover Curator, grant at least View
    Channels, Send Messages, and Read Message History.
  - Users can DM Curator after the bot shares a server with them.
  - If Curator needs to read ordinary guild messages beyond DMs, mentions, or
    interactions, enable Message Content intent in the Developer Portal.

EOF
  fi

  if [[ "$channels_csv" == *telegram* ]]; then
    cat <<EOF
Telegram:
  - Create the bot in BotFather, keep its username discoverable, and use that
    token during Hermes gateway setup.
  - Each user must open a DM with the bot and press Start before Curator can
    reply to that user.
  - Privacy mode only affects groups; leave it on unless you intentionally want
    Curator to read ordinary group traffic.

EOF
  fi
}

probe_hermes_state_json() {
  local hermes_home="$1"
  local hermes_bin="${2:-hermes}"
  local dump_file=""
  dump_file="$(mktemp)"
  if ! HERMES_HOME="$hermes_home" "$hermes_bin" dump >"$dump_file" 2>/dev/null; then
    rm -f "$dump_file"
    return 1
  fi

  python3 - "$dump_file" "${ALMANAC_MODEL_PRESET_CODEX:-openai:codex}" "${ALMANAC_MODEL_PRESET_OPUS:-anthropic:claude-opus}" "${ALMANAC_MODEL_PRESET_CHUTES:-chutes:auto-failover}" <<'PY'
import json
import re
import sys

text = open(sys.argv[1], "r", encoding="utf-8").read()
codex_preset = sys.argv[2].strip().lower()
opus_preset = sys.argv[3].strip().lower()
chutes_preset = sys.argv[4].strip().lower()

model = ""
provider = ""
platforms = []
for raw_line in text.splitlines():
    line = raw_line.strip()
    if not line:
        continue
    if line.startswith("model:") and not model:
        model = line.split(":", 1)[1].strip()
        continue
    if line.startswith("provider:") and not provider:
        provider = line.split(":", 1)[1].strip()
        continue
    if line.startswith("platforms:") and not platforms:
        raw = line.split(":", 1)[1].strip().lower()
        platforms = re.findall(r"(discord|telegram)", raw)

model_string = f"{provider}:{model}" if provider and model else ""
provider_l = provider.lower()
model_l = model.lower()
model_string_l = model_string.lower()

model_preset = "custom"
if (
    provider_l == "openai-codex"
    or "codex" in provider_l
    or model_string_l == codex_preset
):
    model_preset = "codex"
elif (
    provider_l.startswith("anthropic")
    or "opus" in model_l
    or model_string_l == opus_preset
):
    model_preset = "opus"
elif (
    "chutes" in provider_l
    or "failover" in model_l
    or model_string_l == chutes_preset
):
    model_preset = "chutes"

channels = ["tui-only"]
for platform in platforms:
    if platform not in channels:
        channels.append(platform)

print(json.dumps({
    "model_preset": model_preset,
    "model_string": model_string,
    "channels_csv": ",".join(channels),
}))
PY
  rm -f "$dump_file"
}

should_rerun_setup() {
  local label="$1"
  local force_flag="${2:-0}"

  if [[ "$force_flag" == "1" ]]; then
    return 0
  fi

  if [[ ! -f "$ALMANAC_CURATOR_MANIFEST" ]]; then
    return 0
  fi

  if [[ ! -t 0 ]]; then
    return 1
  fi

  confirm_default "Curator manifest already exists. Rerun $label?" "no"
}

resolve_notify_channel() {
  local existing_platform="${OPERATOR_NOTIFY_CHANNEL_PLATFORM:-tui-only}"
  local existing_channel_id="${OPERATOR_NOTIFY_CHANNEL_ID:-}"
  local platform="${ALMANAC_CURATOR_NOTIFY_PLATFORM:-}"
  local channel_id="${ALMANAC_CURATOR_NOTIFY_CHANNEL_ID:-}"
  local reuse_existing="${ALMANAC_CURATOR_FORCE_CHANNEL_RECONFIGURE:-0}"
  local skip_setup="${ALMANAC_CURATOR_SKIP_HERMES_SETUP:-0}"
  local skip_gateway_setup="${ALMANAC_CURATOR_SKIP_GATEWAY_SETUP:-0}"

  # Upgrades and headless repair flows already know the operator channel from
  # the deployed config. Reuse it silently instead of prompting just because
  # the caller happens to have a controlling TTY.
  if [[ "$skip_setup" == "1" && "$skip_gateway_setup" == "1" && -n "$existing_platform" && -z "$platform" && -z "$channel_id" ]]; then
    printf '%s\n%s\n' "$existing_platform" "$existing_channel_id"
    return 0
  fi

  if [[ "$reuse_existing" != "1" && -n "$existing_platform" && -z "$platform" && -z "$channel_id" ]]; then
    if [[ ! -t 0 ]] || confirm_default "Reuse existing operator notification channel ($existing_platform ${existing_channel_id:-"(tui-only)"})?" "yes"; then
      printf '%s\n%s\n' "$existing_platform" "$existing_channel_id"
      return 0
    fi
  fi

  platform="${platform:-$existing_platform}"
  if [[ -t 0 ]]; then
    platform="$(ask_default "Operator notification channel platform (discord/telegram/tui-only)" "${platform:-tui-only}")"
  fi

  channel_id="${channel_id:-$existing_channel_id}"
  if [[ "$platform" != "tui-only" && -z "$channel_id" && -t 0 ]]; then
    channel_id="$(ask_default "Operator notification channel/chat ID" "")"
  fi

  printf '%s\n%s\n' "${platform:-tui-only}" "$channel_id"
}

set_config_value() {
  local key="$1"
  local value="$2"
  local config_file="${ALMANAC_PRIV_CONFIG_DIR}/almanac.env"

  PYTHONPATH="$BOOTSTRAP_DIR/python${PYTHONPATH:+:$PYTHONPATH}" \
    python3 - "$config_file" "$key" "$value" <<'PY'
import sys
from pathlib import Path

from almanac_control import ensure_config_file_update

path = Path(sys.argv[1])
ensure_config_file_update(path, {sys.argv[2]: sys.argv[3]})
PY
}

ensure_curator_hermes() {
  if ensure_shared_hermes_runtime; then
    return 0
  fi
  echo "Curator Hermes runtime is unavailable; run bootstrap-userland first." >&2
  exit 1
}

main() {
  require_real_layout "curator bootstrap"
  ensure_layout
  ensure_curator_hermes

  local model_preset=""
  local model_string=""
  local channels_csv=""
  local channels_json=""
  local notify_platform=""
  local notify_channel_id=""
  local general_platform=""
  local general_channel_id=""
  local skip_setup="${ALMANAC_CURATOR_SKIP_HERMES_SETUP:-0}"
  local skip_gateway_setup="${ALMANAC_CURATOR_SKIP_GATEWAY_SETUP:-0}"
  local force_setup="${ALMANAC_CURATOR_FORCE_HERMES_SETUP:-0}"
  local force_gateway_setup="${ALMANAC_CURATOR_FORCE_GATEWAY_SETUP:-0}"
  local hermes_bin="$RUNTIME_DIR/hermes-venv/bin/hermes"
  local notify_values=()
  local reuse_note=""
  local hermes_state_file=""

  model_preset="$(choose_model_preset)"
  case "$model_preset" in
    codex) model_string="$ALMANAC_MODEL_PRESET_CODEX" ;;
    opus) model_string="$ALMANAC_MODEL_PRESET_OPUS" ;;
    chutes) model_string="$ALMANAC_MODEL_PRESET_CHUTES" ;;
    *) model_string="$ALMANAC_MODEL_PRESET_CODEX" ;;
  esac
  channels_csv="$(choose_channels_csv)"
  channels_json="$(
    python3 - "$channels_csv" <<'PY'
import json
import sys

channels = [item.strip() for item in sys.argv[1].split(",") if item.strip()]
if "tui-only" not in channels:
    channels.insert(0, "tui-only")
print(json.dumps(channels))
PY
  )"

  mapfile -t notify_values < <(resolve_notify_channel)
  notify_platform="${notify_values[0]:-tui-only}"
  notify_channel_id="${notify_values[1]:-}"
  if [[ "$notify_platform" == "${OPERATOR_NOTIFY_CHANNEL_PLATFORM:-tui-only}" && "$notify_channel_id" == "${OPERATOR_NOTIFY_CHANNEL_ID:-}" ]]; then
    reuse_note=" (reused existing channel config)"
  fi

  general_platform="${ALMANAC_CURATOR_GENERAL_PLATFORM:-${OPERATOR_GENERAL_CHANNEL_PLATFORM:-}}"
  general_channel_id="${ALMANAC_CURATOR_GENERAL_CHANNEL_ID:-${OPERATOR_GENERAL_CHANNEL_ID:-}}"

  mkdir -p "$ALMANAC_CURATOR_HERMES_HOME"

  if [[ "$skip_setup" != "1" && -t 0 ]] && should_rerun_setup "Hermes setup" "$force_setup"; then
    echo "Running curator Hermes setup in $ALMANAC_CURATOR_HERMES_HOME ..."
    HERMES_HOME="$ALMANAC_CURATOR_HERMES_HOME" "$hermes_bin" setup
  fi

  if [[ "$skip_gateway_setup" != "1" && -t 0 ]] && [[ "$channels_csv" == *discord* || "$channels_csv" == *telegram* ]] && should_rerun_setup "Hermes gateway setup" "$force_gateway_setup"; then
    print_gateway_setup_guidance "$channels_csv"
    echo "Running curator Hermes gateway setup ..."
    if ! HERMES_HOME="$ALMANAC_CURATOR_HERMES_HOME" "$hermes_bin" gateway setup; then
      echo "Hermes gateway setup returned non-zero; Almanac will continue and restart the configured gateway itself." >&2
    fi
  fi

  hermes_state_file="$(mktemp)"
  if probe_hermes_state_json "$ALMANAC_CURATOR_HERMES_HOME" "$hermes_bin" >"$hermes_state_file"; then
    local detected_model_preset="" detected_model_string="" detected_channels_csv=""
    detected_model_preset="$(python3 - "$hermes_state_file" <<'PY'
import json, sys
print((json.load(open(sys.argv[1]))).get("model_preset", ""))
PY
)"
    detected_model_string="$(python3 - "$hermes_state_file" <<'PY'
import json, sys
print((json.load(open(sys.argv[1]))).get("model_string", ""))
PY
)"
    detected_channels_csv="$(python3 - "$hermes_state_file" <<'PY'
import json, sys
print((json.load(open(sys.argv[1]))).get("channels_csv", ""))
PY
)"
    [[ -n "$detected_model_preset" ]] && model_preset="$detected_model_preset"
    [[ -n "$detected_model_string" ]] && model_string="$detected_model_string"
    [[ -n "$detected_channels_csv" ]] && channels_csv="$detected_channels_csv"
  fi
  channels_json="$(
    python3 - "$channels_csv" <<'PY'
import json
import sys

channels = [item.strip() for item in sys.argv[1].split(",") if item.strip()]
if "tui-only" not in channels:
    channels.insert(0, "tui-only")
print(json.dumps(channels))
PY
  )"

  ALMANAC_CURATOR_MODEL_PRESET="$model_preset"
  ALMANAC_CURATOR_CHANNELS="$channels_csv"
  set_config_value "ALMANAC_CURATOR_MODEL_PRESET" "$model_preset"
  set_config_value "ALMANAC_CURATOR_CHANNELS" "$channels_csv"
  "$BOOTSTRAP_DIR/bin/almanac-ctl" channel reconfigure operator --platform "$notify_platform" --channel-id "$notify_channel_id" >/dev/null
  set_config_value "OPERATOR_GENERAL_CHANNEL_PLATFORM" "$general_platform"
  set_config_value "OPERATOR_GENERAL_CHANNEL_ID" "$general_channel_id"

  PYTHONPATH="$BOOTSTRAP_DIR/python${PYTHONPATH:+:$PYTHONPATH}" \
    python3 "$BOOTSTRAP_DIR/python/almanac_ctl.py" internal register-curator \
      --unix-user "$ALMANAC_USER" \
      --display-name "Curator" \
      --hermes-home "$ALMANAC_CURATOR_HERMES_HOME" \
      --model-preset "$model_preset" \
      --model-string "$model_string" \
      --channels-json "$channels_json" \
      --notify-platform "$notify_platform" \
      --notify-channel-id "$notify_channel_id" >/dev/null
  PYTHONPATH="$BOOTSTRAP_DIR/python${PYTHONPATH:+:$PYTHONPATH}" \
    python3 "$BOOTSTRAP_DIR/python/almanac_ctl.py" internal curator-refresh >/dev/null

  HERMES_HOME="$ALMANAC_CURATOR_HERMES_HOME" "$hermes_bin" skills install "$BOOTSTRAP_DIR/skills/almanac-qmd-mcp" --yes >/dev/null 2>&1 || true
  HERMES_HOME="$ALMANAC_CURATOR_HERMES_HOME" "$hermes_bin" skills install "$BOOTSTRAP_DIR/skills/almanac-vault-reconciler" --yes >/dev/null 2>&1 || true
  HERMES_HOME="$ALMANAC_CURATOR_HERMES_HOME" "$hermes_bin" skills install "$BOOTSTRAP_DIR/skills/almanac-first-contact" --yes >/dev/null 2>&1 || true
  HERMES_HOME="$ALMANAC_CURATOR_HERMES_HOME" "$hermes_bin" skills install "$BOOTSTRAP_DIR/skills/almanac-vaults" --yes >/dev/null 2>&1 || true
  HERMES_HOME="$ALMANAC_CURATOR_HERMES_HOME" "$hermes_bin" skills install "$BOOTSTRAP_DIR/skills/almanac-ssot" --yes >/dev/null 2>&1 || true
  HERMES_HOME="$ALMANAC_CURATOR_HERMES_HOME" "$hermes_bin" skills install "$BOOTSTRAP_DIR/skills/almanac-upgrade-orchestrator" --yes >/dev/null 2>&1 || true

  if set_user_systemd_bus_env; then
    systemctl --user daemon-reload
    systemctl --user enable almanac-curator-refresh.timer >/dev/null
    systemctl --user restart almanac-curator-refresh.timer >/dev/null || true
    if has_curator_telegram_onboarding; then
      systemctl --user enable almanac-curator-onboarding.service >/dev/null
      systemctl --user restart almanac-curator-onboarding.service >/dev/null 2>&1 || true
    else
      systemctl --user disable --now almanac-curator-onboarding.service >/dev/null 2>&1 || true
    fi
    if has_curator_discord_onboarding; then
      systemctl --user enable almanac-curator-discord-onboarding.service >/dev/null
      systemctl --user restart almanac-curator-discord-onboarding.service >/dev/null 2>&1 || true
    else
      systemctl --user disable --now almanac-curator-discord-onboarding.service >/dev/null 2>&1 || true
    fi
    if ! has_curator_gateway_channels; then
      systemctl --user disable --now almanac-curator-gateway.service >/dev/null 2>&1 || true
      systemctl --user disable --now almanac-curator-onboarding.service >/dev/null 2>&1 || true
      systemctl --user disable --now almanac-curator-discord-onboarding.service >/dev/null 2>&1 || true
    elif has_curator_non_onboarding_gateway_channels || ! has_curator_onboarding; then
      systemctl --user enable almanac-curator-gateway.service >/dev/null
      systemctl --user restart almanac-curator-gateway.service >/dev/null 2>&1 || true
    else
      systemctl --user disable --now almanac-curator-gateway.service >/dev/null 2>&1 || true
    fi
  fi

  cat <<EOF

Curator bootstrap complete.

Curator Hermes home:
  $ALMANAC_CURATOR_HERMES_HOME
Model preset:
  $model_preset -> $model_string
Channels:
  $channels_csv
Operator notification:
  $notify_platform ${notify_channel_id:-"(tui-only)"}$reuse_note

Recovery path:
  HERMES_HOME=$ALMANAC_CURATOR_HERMES_HOME $hermes_bin

EOF

  rm -f "$hermes_state_file"
}

main "$@"
