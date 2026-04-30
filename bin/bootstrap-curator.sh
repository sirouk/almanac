#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

ask_default() {
  local prompt="$1"
  local default="${2:-}"
  local answer=""
  if [[ ! -t 0 ]]; then
    printf '%s' "$default"
    return 0
  fi
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
  local normalized_answer=""

  [[ "$default" == "no" ]] && hint="y/N"
  if [[ ! -t 0 ]]; then
    normalized_answer="$(printf '%s' "$default" | tr '[:upper:]' '[:lower:]')"
    [[ "$normalized_answer" =~ ^(y|yes|1)$ ]]
    return
  fi
  read -r -p "$prompt [$hint]: " answer
  answer="${answer:-$default}"
  normalized_answer="$(printf '%s' "$answer" | tr '[:upper:]' '[:lower:]')"
  [[ "$normalized_answer" =~ ^(y|yes|1)$ ]]
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
  local existing_channels="${ALMANAC_CURATOR_CHANNELS:-}"
  local reuse_existing="${ALMANAC_CURATOR_FORCE_CHANNEL_RECONFIGURE:-0}"
  local skip_setup="${ALMANAC_CURATOR_SKIP_HERMES_SETUP:-0}"
  local skip_gateway_setup="${ALMANAC_CURATOR_SKIP_GATEWAY_SETUP:-0}"
  local default_discord="no"
  local default_telegram="no"
  local normalized_discord="" normalized_telegram=""

  if [[ "$skip_setup" == "1" && "$skip_gateway_setup" == "1" && -n "$existing_channels" ]]; then
    printf '%s\n' "$existing_channels"
    return 0
  fi

  if [[ ",${existing_channels}," == *",discord,"* ]]; then
    default_discord="yes"
  fi
  if [[ ",${existing_channels}," == *",telegram,"* ]]; then
    default_telegram="yes"
  fi

  if [[ -n "$existing_channels" && "$reuse_existing" != "1" ]]; then
    if [[ "$existing_channels" != "tui-only" || -f "$ALMANAC_CURATOR_MANIFEST" ]]; then
      if [[ ! -t 0 ]] || confirm_default "Reuse existing Curator chat channels ($existing_channels)?" "yes"; then
        printf '%s\n' "$existing_channels"
        return 0
      fi
    fi
  fi

  local discord="" telegram="" channels="tui-only"
  discord="$(ask_default "Enable Discord for Curator gateway? (yes/no)" "$default_discord")"
  telegram="$(ask_default "Enable Telegram for Curator gateway? (yes/no)" "$default_telegram")"
  normalized_discord="$(printf '%s' "$discord" | tr '[:upper:]' '[:lower:]')"
  normalized_telegram="$(printf '%s' "$telegram" | tr '[:upper:]' '[:lower:]')"
  if [[ "$normalized_discord" =~ ^(y|yes|1)$ ]]; then
    channels="$channels,discord"
  fi
  if [[ "$normalized_telegram" =~ ^(y|yes|1)$ ]]; then
    channels="$channels,telegram"
  fi
  printf '%s\n' "$channels"
}

default_notify_platform_for_channels() {
  local channels_csv="$1"
  local channel="" chosen=""
  local channels=()

  IFS=',' read -r -a channels <<<"$channels_csv"
  for channel in "${channels[@]}"; do
    channel="${channel//[[:space:]]/}"
    case "$channel" in
      ""|tui-only) ;;
      discord|telegram)
        if [[ -n "$chosen" && "$chosen" != "$channel" ]]; then
          printf '\n'
          return 0
        fi
        chosen="$channel"
        ;;
    esac
  done

  printf '%s\n' "$chosen"
}

describe_notify_channel_prompt() {
  local platform="${1:-tui-only}"

  case "$platform" in
    discord) printf '%s\n' "Operator notification Discord channel ID or webhook URL" ;;
    telegram) printf '%s\n' "Operator notification Telegram chat ID" ;;
    *) printf '%s\n' "Operator notification channel/chat ID" ;;
  esac
}

print_notify_channel_guidance() {
  local platform="${1:-tui-only}"

  case "$platform" in
    discord)
      cat >&2 <<'EOF'
Discord operator notifications accept a channel ID or webhook URL, not a user ID.
  - Enable Developer Mode in Discord settings.
  - Right-click the destination channel and choose Copy Channel ID.
  - A Discord webhook URL also works for operator-only notifications.

EOF
      ;;
    telegram)
      cat >&2 <<'EOF'
Telegram operator notifications use the numeric chat ID for the destination chat.
  - Open a DM with the bot and press Start first.
  - For a 1:1 operator DM, use the numeric ID from that chat.
  - If you need to discover it, send the bot a message and inspect Bot API getUpdates for message.chat.id.

EOF
      ;;
  esac
}

channels_csv_covers_requested() {
  local actual_csv="$1"
  local expected_csv="$2"
  local channel=""
  local expected_channels=()

  IFS=',' read -r -a expected_channels <<<"$expected_csv"
  for channel in "${expected_channels[@]}"; do
    channel="${channel//[[:space:]]/}"
    case "$channel" in
      ""|tui-only) continue ;;
    esac
    if [[ ",${actual_csv}," != *",${channel},"* ]]; then
      return 1
    fi
  done

  return 0
}

describe_operator_channel() {
  local platform="${1:-tui-only}"
  local channel_id="${2:-}"

  if [[ -z "$platform" || "$platform" == "tui-only" ]]; then
    printf '%s\n' "tui-only"
    return 0
  fi

  if [[ -n "$channel_id" ]]; then
    printf '%s\n' "$platform $channel_id"
    return 0
  fi

  printf '%s\n' "$platform (channel unset)"
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
  - Almanac manages the Curator gateway as an Almanac systemd user service.
    Hermes-native service install prompts are skipped during setup.

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

  python3 - "$dump_file" "${ALMANAC_MODEL_PRESET_CODEX:-openai-codex:gpt-5.5}" "${ALMANAC_MODEL_PRESET_OPUS:-anthropic:claude-opus-4-7}" "${ALMANAC_MODEL_PRESET_CHUTES:-chutes:moonshotai/Kimi-K2.6-TEE}" <<'PY'
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

run_curator_gateway_setup() {
  local requested_channels_csv="$1"
  local hermes_bin="$2"
  local hermes_home="$3"
  local detected_channels_csv=""
  local state_file=""
  local setup_cmd="$BOOTSTRAP_DIR/bin/almanac-hermes-gateway-setup.sh"

  print_gateway_setup_guidance "$requested_channels_csv"
  echo "Running curator Hermes gateway setup ..."
  if [[ -x "$setup_cmd" ]]; then
    if "$setup_cmd" "$hermes_bin" "$hermes_home"; then
      return 0
    fi
  elif HERMES_HOME="$hermes_home" "$hermes_bin" gateway setup; then
    return 0
  fi

  state_file="$(mktemp)"
  if probe_hermes_state_json "$hermes_home" "$hermes_bin" >"$state_file"; then
    detected_channels_csv="$(python3 - "$state_file" <<'PY'
import json
import sys
print((json.load(open(sys.argv[1]))).get("channels_csv", ""))
PY
)"
  fi
  rm -f "$state_file"

  if channels_csv_covers_requested "$detected_channels_csv" "$requested_channels_csv"; then
    echo "Hermes saved the gateway config; Almanac will restart the configured gateway service below." >&2
    return 0
  fi

  echo "Hermes gateway setup returned non-zero before Almanac could confirm the saved gateway config. Almanac will keep going and restart the configured gateway itself if present." >&2
  return 1
}

configure_operator_notify_channel() {
  local requested_platform="${1:-tui-only}"
  local requested_channel_id="${2:-}"

  requested_platform="$(printf '%s' "$requested_platform" | tr '[:upper:]' '[:lower:]')"
  if "$BOOTSTRAP_DIR/bin/almanac-ctl" channel reconfigure operator --platform "$requested_platform" --channel-id "$requested_channel_id" >/dev/null; then
    printf '%s\n%s\n' "$requested_platform" "$requested_channel_id"
    return 0
  fi

  echo "Operator notification target verification failed. Curator chat is still configured, but operator notifications will stay on tui-only until you reconfigure a reachable Discord or Telegram target with 'almanac-ctl channel reconfigure operator'." >&2
  "$BOOTSTRAP_DIR/bin/almanac-ctl" channel reconfigure operator --platform "tui-only" --channel-id "" >/dev/null || true
  printf '%s\n%s\n' "tui-only" ""
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
  local channels_csv="${1:-${ALMANAC_CURATOR_CHANNELS:-tui-only}}"
  local existing_platform="${OPERATOR_NOTIFY_CHANNEL_PLATFORM:-tui-only}"
  local existing_channel_id="${OPERATOR_NOTIFY_CHANNEL_ID:-}"
  local platform="${ALMANAC_CURATOR_NOTIFY_PLATFORM:-}"
  local channel_id="${ALMANAC_CURATOR_NOTIFY_CHANNEL_ID:-}"
  local reuse_existing="${ALMANAC_CURATOR_FORCE_CHANNEL_RECONFIGURE:-0}"
  local skip_setup="${ALMANAC_CURATOR_SKIP_HERMES_SETUP:-0}"
  local skip_gateway_setup="${ALMANAC_CURATOR_SKIP_GATEWAY_SETUP:-0}"
  local meaningful_existing="0"
  local existing_label=""
  local inferred_platform=""

  # Upgrades and headless repair flows already know the operator channel from
  # the deployed config. Reuse it silently instead of prompting just because
  # the caller happens to have a controlling TTY.
  if [[ "$skip_setup" == "1" && "$skip_gateway_setup" == "1" && -n "$existing_platform" && -z "$platform" && -z "$channel_id" ]]; then
    printf '%s\n%s\n' "$existing_platform" "$existing_channel_id"
    return 0
  fi

  if [[ "$existing_platform" != "tui-only" || -n "$existing_channel_id" ]]; then
    meaningful_existing="1"
  fi

  existing_label="$(describe_operator_channel "$existing_platform" "$existing_channel_id")"
  if [[ "$reuse_existing" != "1" && "$meaningful_existing" == "1" && -z "$platform" && -z "$channel_id" ]]; then
    if [[ ! -t 0 ]] || confirm_default "Reuse existing operator notification channel ($existing_label)?" "yes"; then
      printf '%s\n%s\n' "$existing_platform" "$existing_channel_id"
      return 0
    fi
  fi

  inferred_platform="$(default_notify_platform_for_channels "$channels_csv")"
  if [[ -z "$platform" ]]; then
    if [[ "$meaningful_existing" == "1" ]]; then
      platform="$existing_platform"
    elif [[ -n "$inferred_platform" ]]; then
      platform="$inferred_platform"
    else
      platform="${existing_platform:-tui-only}"
    fi
  fi
  if [[ -t 0 ]]; then
    platform="$(ask_default "Operator notification channel platform (discord/telegram/tui-only)" "${platform:-tui-only}")"
  fi

  channel_id="${channel_id:-$existing_channel_id}"
  if [[ "$platform" != "tui-only" && -z "$channel_id" && -t 0 ]]; then
    print_notify_channel_guidance "$platform"
    channel_id="$(ask_default "$(describe_notify_channel_prompt "$platform")" "")"
  elif [[ "$platform" != "tui-only" && -t 0 ]]; then
    print_notify_channel_guidance "$platform"
    channel_id="$(ask_default "$(describe_notify_channel_prompt "$platform")" "$channel_id")"
  fi

  printf '%s\n%s\n' "${platform:-tui-only}" "$channel_id"
}

set_config_value() {
  local key="$1"
  local value="$2"
  local config_file="${ALMANAC_CONFIG_FILE:-${ALMANAC_PRIV_CONFIG_DIR}/almanac.env}"

  PYTHONPATH="$BOOTSTRAP_DIR/python${PYTHONPATH:+:$PYTHONPATH}" \
    python3 - "$config_file" "$key" "$value" <<'PY'
import sys
from pathlib import Path

from almanac_control import ensure_config_file_update

path = Path(sys.argv[1])
ensure_config_file_update(path, {sys.argv[2]: sys.argv[3]})
PY
}

sync_org_provider_from_curator_codex() {
  local auth_file="$ALMANAC_CURATOR_HERMES_HOME/auth.json"
  local secret_json=""

  if [[ "${ALMANAC_ORG_PROVIDER_ENABLED:-0}" != "1" ]]; then
    return 0
  fi
  if [[ "${ALMANAC_ORG_PROVIDER_PRESET:-}" != "codex" ]]; then
    return 0
  fi
  if [[ -n "${ALMANAC_ORG_PROVIDER_SECRET:-}" ]]; then
    return 0
  fi
  if [[ ! -r "$auth_file" ]]; then
    echo "Org-provided Codex is pending: Curator has not saved a Codex sign-in yet." >&2
    return 0
  fi

  if ! secret_json="$(python3 - "$auth_file" <<'PY'
import json
import sys

path = sys.argv[1]
try:
    data = json.load(open(path, "r", encoding="utf-8"))
except Exception:
    raise SystemExit(1)

provider = (data.get("providers") or {}).get("openai-codex") or {}
tokens = provider.get("tokens") or {}
access_token = str(tokens.get("access_token") or "").strip()
refresh_token = str(tokens.get("refresh_token") or "").strip()
if not access_token or not refresh_token:
    raise SystemExit(1)

print(json.dumps(
    {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "last_refresh": str(provider.get("last_refresh") or "").strip(),
        "base_url": "https://chatgpt.com/backend-api/codex",
    },
    sort_keys=True,
))
PY
)"; then
    echo "Org-provided Codex is pending: Curator auth.json does not contain Codex tokens." >&2
    return 0
  fi

  set_config_value "ALMANAC_ORG_PROVIDER_SECRET_PROVIDER" "codex"
  set_config_value "ALMANAC_ORG_PROVIDER_SECRET" "$secret_json"
  echo "Org-provided Codex credential captured from Curator Codex sign-in."
}

ensure_hermes_agent_defaults() {
  local hermes_home="$1"
  local hermes_python="${2:-$RUNTIME_DIR/hermes-venv/bin/python3}"
  local shared_skills_dir="${ALMANAC_SHARED_SKILLS_DIR:-}"
  local agent_vault_dir="${ALMANAC_AGENT_VAULT_DIR:-${VAULT_DIR:-}}"

  if [[ -z "$shared_skills_dir" && -n "${VAULT_DIR:-}" ]]; then
    shared_skills_dir="${VAULT_DIR%/}/Agents_Skills"
  fi

  ALMANAC_SHARED_SKILLS_DIR="$shared_skills_dir" \
    ALMANAC_AGENT_VAULT_DIR="$agent_vault_dir" \
    VAULT_DIR="${VAULT_DIR:-}" \
    HERMES_HOME="$hermes_home" \
    "$hermes_python" <<'PY'
from __future__ import annotations

import os
import shlex
from pathlib import Path

import yaml


def read_env_map(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in raw_line:
            continue
        key, raw_value = raw_line.split("=", 1)
        key = key.strip()
        try:
            parsed = shlex.split(raw_value, posix=True)
        except ValueError:
            parsed = []
        values[key] = parsed[0] if parsed else raw_value.strip().strip("'\"")
    return values


def write_env_value(path: Path, key: str, value: str) -> bool:
    lines: list[str] = []
    updated = False
    try:
        existing = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        existing = []
    for raw_line in existing:
        stripped = raw_line.strip()
        if stripped and not stripped.startswith("#") and "=" in raw_line:
            name = raw_line.split("=", 1)[0].strip()
            if name == key:
                lines.append(f"{key}={value}")
                updated = True
                continue
        lines.append(raw_line)
    if not updated:
        lines.append(f"{key}={value}")
    payload = "\n".join(lines).rstrip()
    if payload:
        payload += "\n"
    old_payload = ""
    try:
        old_payload = path.read_text(encoding="utf-8")
    except OSError:
        pass
    if payload == old_payload:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    path.chmod(0o600)
    return True


def path_key(path_value: str) -> str:
    expanded = os.path.expandvars(os.path.expanduser(str(path_value or "").strip()))
    if not expanded:
        return ""
    try:
        return str(Path(expanded).resolve())
    except OSError:
        return str(Path(expanded).absolute())


def external_dirs_list(raw_value) -> list[str]:
    if raw_value is None:
        raw_values = []
    elif isinstance(raw_value, str):
        raw_values = [raw_value]
    elif isinstance(raw_value, list):
        raw_values = raw_value
    else:
        raw_values = []
    result: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        text = str(value or "").strip()
        key = path_key(text)
        if not text or not key or key in seen:
            continue
        result.append(text)
        seen.add(key)
    return result


def discover_org_skill_external_dirs(home: Path) -> list[str]:
    bases: list[Path] = []
    for env_key in ("ALMANAC_SHARED_SKILLS_DIR",):
        value = str(os.environ.get(env_key) or "").strip()
        if value:
            bases.append(Path(value).expanduser())
    for env_key in ("VAULT_DIR", "ALMANAC_AGENT_VAULT_DIR"):
        value = str(os.environ.get(env_key) or "").strip()
        if value:
            bases.append(Path(value).expanduser() / "Agents_Skills")
    bases.append(Path(os.environ.get("HOME") or str(Path.home())).expanduser() / "Almanac" / "Agents_Skills")
    bases.append(home / "Almanac" / "Agents_Skills")
    bases.append(home / "Vault" / "Agents_Skills")

    discovered: list[str] = []
    seen_bases: set[str] = set()
    seen_dirs: set[str] = set()
    for base in bases:
        base_key = path_key(str(base))
        if not base_key or base_key in seen_bases or not base.is_dir():
            continue
        seen_bases.add(base_key)
        for child in sorted(base.iterdir(), key=lambda item: item.name.lower()):
            if child.name.startswith(".") or not child.is_dir():
                continue
            skill_root = child / "skills"
            if not skill_root.is_dir() or not any(skill_root.rglob("SKILL.md")):
                continue
            key = path_key(str(skill_root))
            if not key or key in seen_dirs:
                continue
            discovered.append(str(skill_root))
            seen_dirs.add(key)
    return discovered


def ensure_org_skill_external_dirs(config: dict, home: Path) -> bool:
    skills = config.setdefault("skills", {})
    if not isinstance(skills, dict):
        skills = {}
        config["skills"] = skills
    existing = external_dirs_list(skills.get("external_dirs"))
    merged = list(existing)
    seen = {path_key(value) for value in existing}
    changed = False
    for value in discover_org_skill_external_dirs(home):
        key = path_key(value)
        if not key or key in seen:
            continue
        merged.append(value)
        seen.add(key)
        changed = True
    if changed or skills.get("external_dirs") != merged:
        skills["external_dirs"] = merged
        return True
    return False


home = Path(os.environ["HERMES_HOME"])
config_path = home / "config.yaml"
home.mkdir(parents=True, exist_ok=True)
try:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
except Exception:
    config = {}
if not isinstance(config, dict):
    config = {}

notes: list[str] = []
config_changed = False

agent = config.setdefault("agent", {})
if not isinstance(agent, dict):
    agent = {}
    config["agent"] = agent
if agent.get("max_turns") is None:
    agent["max_turns"] = 90
    notes.append("Max iterations: 90")
    config_changed = True

display = config.setdefault("display", {})
if not isinstance(display, dict):
    display = {}
    config["display"] = display
if display.get("tool_progress") in (None, ""):
    display["tool_progress"] = "all"
    notes.append("Tool progress: all")
    config_changed = True

compression = config.setdefault("compression", {})
if not isinstance(compression, dict):
    compression = {}
    config["compression"] = compression
compression_note = False
if compression.get("enabled") is None:
    compression["enabled"] = True
    config_changed = True
    compression_note = True
if compression.get("threshold") is None:
    compression["threshold"] = 0.50
    config_changed = True
    compression_note = True
if compression_note:
    notes.append("Compression threshold: 0.50")

session_reset = config.setdefault("session_reset", {})
if not isinstance(session_reset, dict):
    session_reset = {}
    config["session_reset"] = session_reset
session_reset_changed = False
if session_reset.get("mode") in (None, ""):
    session_reset["mode"] = "both"
    config_changed = True
    session_reset_changed = True
if session_reset.get("idle_minutes") is None:
    session_reset["idle_minutes"] = 1440
    config_changed = True
    session_reset_changed = True
if session_reset.get("at_hour") is None:
    session_reset["at_hour"] = 4
    config_changed = True
    session_reset_changed = True
if session_reset_changed:
    notes.append("Session reset: inactivity (1440 min) + daily (4:00)")

if ensure_org_skill_external_dirs(config, home):
    notes.append("Shared org skill dirs: enabled")
    config_changed = True

terminal = config.setdefault("terminal", {})
if not isinstance(terminal, dict):
    terminal = {}
    config["terminal"] = terminal
if terminal.get("backend") in (None, ""):
    terminal["backend"] = "local"
    config_changed = True

if config_changed:
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

env_values = read_env_map(home / ".env")
max_iterations = str(agent.get("max_turns") or 90)
env_changed = False
if not env_values.get("HERMES_MAX_ITERATIONS", "").strip():
    env_changed = write_env_value(home / ".env", "HERMES_MAX_ITERATIONS", max_iterations)

if notes or env_changed:
    print("Applied Hermes recommended defaults for missing agent settings:")
    for note in notes:
        print(f"  {note}")
    print("  Run `hermes setup agent` later to customize.")
PY
}

ensure_curator_hermes() {
  local venv_dir="$RUNTIME_DIR/hermes-venv"
  local hermes_bin="$venv_dir/bin/hermes"
  local python_bin="$venv_dir/bin/python3"

  if [[ -x "$hermes_bin" ]] && runtime_python_has_pip "$python_bin" && shared_runtime_python_is_share_safe "$venv_dir"; then
    return 0
  fi
  if ensure_shared_hermes_runtime; then
    return 0
  fi
  echo "Curator Hermes runtime is unavailable; run bootstrap-userland first." >&2
  exit 1
}

curator_native_gateway_unit_name() {
  local python_bin="$RUNTIME_DIR/hermes-venv/bin/python3"
  if [[ ! -x "$python_bin" ]]; then
    return 1
  fi

  HERMES_HOME="$ALMANAC_CURATOR_HERMES_HOME" "$python_bin" <<'PY'
try:
    from hermes_cli.gateway import get_service_name
except Exception:
    raise SystemExit(1)

print(f"{get_service_name()}.service")
PY
}

disable_curator_native_gateway_unit() {
  local unit=""

  unit="$(curator_native_gateway_unit_name 2>/dev/null || true)"
  if [[ -z "$unit" ]]; then
    return 0
  fi

  systemctl --user disable --now "$unit" >/dev/null 2>&1 || true
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
  local ran_model_setup="0"
  local ran_gateway_setup="0"
  local line=""

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

  notify_values=()
  while IFS= read -r line; do
    notify_values+=("$line")
  done < <(resolve_notify_channel "$channels_csv")
  notify_platform="${notify_values[0]:-tui-only}"
  notify_channel_id="${notify_values[1]:-}"
  if [[ "$notify_platform" == "${OPERATOR_NOTIFY_CHANNEL_PLATFORM:-tui-only}" && "$notify_channel_id" == "${OPERATOR_NOTIFY_CHANNEL_ID:-}" ]]; then
    reuse_note=" (reused existing channel config)"
  fi

  general_platform="${ALMANAC_CURATOR_GENERAL_PLATFORM:-${OPERATOR_GENERAL_CHANNEL_PLATFORM:-}}"
  general_channel_id="${ALMANAC_CURATOR_GENERAL_CHANNEL_ID:-${OPERATOR_GENERAL_CHANNEL_ID:-}}"

  mkdir -p "$ALMANAC_CURATOR_HERMES_HOME"

  if [[ "$skip_setup" != "1" && -t 0 ]] && should_rerun_setup "Hermes model/provider setup" "$force_setup"; then
    echo "Running curator Hermes model/provider setup in $ALMANAC_CURATOR_HERMES_HOME ..."
    HERMES_HOME="$ALMANAC_CURATOR_HERMES_HOME" "$hermes_bin" setup model
    ran_model_setup="1"
  fi
  ensure_hermes_agent_defaults "$ALMANAC_CURATOR_HERMES_HOME" "$RUNTIME_DIR/hermes-venv/bin/python3"

  if [[ "$skip_gateway_setup" != "1" && -t 0 ]] && [[ "$channels_csv" == *discord* || "$channels_csv" == *telegram* ]] && should_rerun_setup "Hermes gateway setup" "$force_gateway_setup"; then
    if run_curator_gateway_setup "$channels_csv" "$hermes_bin" "$ALMANAC_CURATOR_HERMES_HOME"; then
      ran_gateway_setup="1"
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
    if [[ "$ran_model_setup" == "1" ]]; then
      [[ -n "$detected_model_preset" ]] && model_preset="$detected_model_preset"
      [[ -n "$detected_model_string" ]] && model_string="$detected_model_string"
    fi
    if [[ "$ran_gateway_setup" == "1" ]]; then
      [[ -n "$detected_channels_csv" ]] && channels_csv="$detected_channels_csv"
    fi
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
  sync_org_provider_from_curator_codex
  notify_values=()
  while IFS= read -r line; do
    notify_values+=("$line")
  done < <(configure_operator_notify_channel "$notify_platform" "$notify_channel_id")
  notify_platform="${notify_values[0]:-tui-only}"
  notify_channel_id="${notify_values[1]:-}"
  if [[ "$notify_platform" != "${OPERATOR_NOTIFY_CHANNEL_PLATFORM:-tui-only}" || "$notify_channel_id" != "${OPERATOR_NOTIFY_CHANNEL_ID:-}" ]]; then
    reuse_note=""
  fi
  set_config_value "OPERATOR_GENERAL_CHANNEL_PLATFORM" "$general_platform"
  set_config_value "OPERATOR_GENERAL_CHANNEL_ID" "$general_channel_id"
  if [[ ",${channels_csv}," == *",telegram,"* || "$notify_platform" == "telegram" ]]; then
    set_config_value "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED" "1"
  else
    set_config_value "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED" "0"
  fi
  if [[ ",${channels_csv}," == *",discord,"* ]]; then
    set_config_value "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED" "1"
  else
    set_config_value "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED" "0"
  fi

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

  "$BOOTSTRAP_DIR/bin/sync-hermes-bundled-skills.sh" \
    "$ALMANAC_CURATOR_HERMES_HOME" \
    "$RUNTIME_DIR"

  "$BOOTSTRAP_DIR/bin/install-almanac-skills.sh" \
    "$BOOTSTRAP_DIR" \
    "$ALMANAC_CURATOR_HERMES_HOME" \
    almanac-qmd-mcp \
    almanac-vault-reconciler \
    almanac-first-contact \
    almanac-vaults \
    almanac-ssot \
    almanac-notion-knowledge \
    almanac-ssot-connect \
    almanac-notion-mcp \
    almanac-resources \
    almanac-upgrade-orchestrator

  "$BOOTSTRAP_DIR/bin/install-almanac-plugins.sh" \
    "$BOOTSTRAP_DIR" \
    "$ALMANAC_CURATOR_HERMES_HOME" \
    almanac-managed-context

  if set_user_systemd_bus_env; then
    systemctl --user daemon-reload
    disable_curator_native_gateway_unit
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
  $(describe_operator_channel "$notify_platform" "$notify_channel_id")$reuse_note

Recovery path:
  HERMES_HOME=$ALMANAC_CURATOR_HERMES_HOME $hermes_bin

EOF

  rm -f "$hermes_state_file"
}

main "$@"
