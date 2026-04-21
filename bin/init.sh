#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-agent}"
if [[ $# -gt 0 ]]; then
  shift
fi

BOOTSTRAP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SHARED_REPO_DIR="${ALMANAC_SHARED_REPO_DIR:-$BOOTSTRAP_DIR}"
ALMANAC_SERVICE_USER="${ALMANAC_SERVICE_USER:-almanac}"
ALMANAC_MCP_PORT="${ALMANAC_MCP_PORT:-8282}"
ALMANAC_MCP_URL="${ALMANAC_MCP_URL:-http://127.0.0.1:${ALMANAC_MCP_PORT}/mcp}"
ALMANAC_BOOTSTRAP_URL="${ALMANAC_BOOTSTRAP_URL:-$ALMANAC_MCP_URL}"
ALMANAC_QMD_URL="${ALMANAC_QMD_URL:-http://127.0.0.1:${QMD_MCP_PORT:-8181}/mcp}"
CHUTES_MCP_URL="${CHUTES_MCP_URL:-}"
HERMES_HOME_DEFAULT="${ALMANAC_AGENT_HERMES_HOME:-$HOME/.local/share/almanac-agent/hermes-home}"

json_get() {
  local file="$1"
  local expr="$2"
  python3 - "$file" "$expr" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)

value = data
for part in sys.argv[2].split("."):
    if not part:
        continue
    if isinstance(value, dict):
        value = value.get(part)
    else:
        value = None
        break
print("" if value is None else json.dumps(value) if isinstance(value, (dict, list)) else str(value))
PY
}

lower_ascii() {
  printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]'
}

is_yes() {
  case "$(lower_ascii "${1:-}")" in
    y|yes|1|true)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

require_linux_host() {
  local action="$1"
  local os_name=""

  os_name="$(uname -s 2>/dev/null || printf 'unknown')"
  if [[ "$os_name" == "Linux" ]]; then
    return 0
  fi

  cat >&2 <<EOF
Almanac v1 $action must run on the Almanac host after SSHing in as your assigned Unix user.
Current OS: $os_name

SSH to the Almanac host, then rerun:
  init.sh $MODE
EOF
  return 1
}

# almanac-rpc does not surface 429 Retry-After; handle it here by retrying with
# a backoff that honors Retry-After when the server provides it.
rpc_call_with_retry() {
  local out_file="$1"
  shift
  local max_attempts="${ALMANAC_INIT_RPC_MAX_ATTEMPTS:-4}"
  local attempt=0
  local exit_code=0
  local err_file=""
  err_file="$(mktemp)"
  while (( attempt < max_attempts )); do
    attempt=$((attempt + 1))
    if "$SHARED_REPO_DIR/bin/almanac-rpc" "$@" >"$out_file" 2>"$err_file"; then
      rm -f "$err_file"
      return 0
    fi
    exit_code=$?
    if grep -qi 'rate-limited' "$err_file"; then
      local retry_after=""
      retry_after="$(grep -oE '[0-9]+' "$err_file" | head -n1 || true)"
      retry_after="${retry_after:-30}"
      if (( retry_after > 300 )); then retry_after=300; fi
      echo "Bootstrap rate-limited; sleeping ${retry_after}s before retry ($attempt/$max_attempts)..." >&2
      sleep "$retry_after"
      continue
    fi
    cat "$err_file" >&2
    rm -f "$err_file"
    return "$exit_code"
  done
  rm -f "$err_file"
  echo "Gave up after $max_attempts rate-limited attempts." >&2
  return 1
}

choose_model_preset() {
  local default="${1:-codex}"
  local answer=""
  if [[ -n "${ALMANAC_INIT_MODEL_PRESET:-}" ]]; then
    printf '%s\n' "$ALMANAC_INIT_MODEL_PRESET"
    return 0
  fi
  if [[ ! -t 0 ]]; then
    printf '%s\n' "$default"
    return 0
  fi
  echo "Model preset: codex / opus / chutes"
  read -r -p "Choose model preset [$default]: " answer
  printf '%s\n' "${answer:-$default}"
}

choose_channels_csv() {
  local default="${1:-tui-only}"
  local answer="" discord="" telegram="" channels="tui-only"
  if [[ -n "${ALMANAC_INIT_CHANNELS:-}" ]]; then
    printf '%s\n' "$ALMANAC_INIT_CHANNELS"
    return 0
  fi
  if [[ ! -t 0 ]]; then
    printf '%s\n' "$default"
    return 0
  fi
  read -r -p "Enable Discord? [y/N]: " discord
  read -r -p "Enable Telegram? [y/N]: " telegram
  if is_yes "$discord"; then
    channels="$channels,discord"
  fi
  if is_yes "$telegram"; then
    channels="$channels,telegram"
  fi
  printf '%s\n' "${channels:-$default}"
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

resolve_shared_hermes_bin() {
  local wrapper_bin="$SHARED_REPO_DIR/bin/hermes-shell.sh"
  local hermes_bin="${ALMANAC_HERMES_BIN:-}"
  if [[ -x "$wrapper_bin" ]]; then
    printf '%s\n' "$wrapper_bin"
    return 0
  fi
  if [[ -n "$hermes_bin" && -x "$hermes_bin" ]]; then
    printf '%s\n' "$hermes_bin"
    return 0
  fi
  hermes_bin="${RUNTIME_DIR:-}/hermes-venv/bin/hermes"
  if [[ -x "$hermes_bin" ]]; then
    printf '%s\n' "$hermes_bin"
    return 0
  fi
  return 1
}

current_hermes_bin() {
  local hermes_bin=""
  if hermes_bin="$(resolve_shared_hermes_bin 2>/dev/null)"; then
    printf '%s\n' "$hermes_bin"
    return 0
  fi
  if command -v hermes >/dev/null 2>&1; then
    command -v hermes
    return 0
  fi
  return 1
}

ensure_hermes_installed() {
  local hermes_bin=""
  if hermes_bin="$(resolve_shared_hermes_bin 2>/dev/null)"; then
    export ALMANAC_HERMES_BIN="$hermes_bin"
    export PATH="$(dirname "$hermes_bin"):$HOME/.local/bin:$PATH"
    return 0
  fi
  if command -v hermes >/dev/null 2>&1; then
    export ALMANAC_HERMES_BIN="$(command -v hermes)"
    export PATH="$(dirname "$ALMANAC_HERMES_BIN"):$HOME/.local/bin:$PATH"
    return 0
  fi
  if [[ "${ALMANAC_INIT_SKIP_HERMES_INSTALL:-0}" == "1" ]]; then
    echo "Hermes is not installed and ALMANAC_INIT_SKIP_HERMES_INSTALL=1 was set." >&2
    return 1
  fi
  curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
  export PATH="$HOME/.local/bin:$PATH"
  if command -v hermes >/dev/null 2>&1; then
    export ALMANAC_HERMES_BIN="$(command -v hermes)"
    return 0
  fi
  return 1
}

install_default_skills() {
  local hermes_home="$1"
  "$SHARED_REPO_DIR/bin/install-almanac-skills.sh" \
    "$SHARED_REPO_DIR" \
    "$hermes_home" \
    almanac-qmd-mcp \
    almanac-vault-reconciler \
    almanac-first-contact \
    almanac-vaults \
    almanac-ssot \
    almanac-notion-knowledge \
    almanac-ssot-connect \
    almanac-notion-mcp
}

install_default_plugins() {
  local hermes_home="$1"
  "$SHARED_REPO_DIR/bin/install-almanac-plugins.sh" \
    "$SHARED_REPO_DIR" \
    "$hermes_home" \
    almanac-managed-context
}

register_default_mcps() {
  local hermes_home="$1"
  local hermes_bin=""
  hermes_bin="$(current_hermes_bin)"
  HERMES_HOME="$hermes_home" "$hermes_bin" mcp add almanac-mcp --url "$ALMANAC_MCP_URL" >/dev/null 2>&1 || true
  HERMES_HOME="$hermes_home" "$hermes_bin" mcp add almanac-qmd --url "$ALMANAC_QMD_URL" >/dev/null 2>&1 || true
  if [[ -n "$CHUTES_MCP_URL" ]]; then
    HERMES_HOME="$hermes_home" "$hermes_bin" mcp add chutes-kb --url "$CHUTES_MCP_URL" >/dev/null 2>&1 || true
  fi
}

write_enrollment_state() {
  local state_file="$1"
  local request_id="$2"
  local agent_id="$3"
  local requester_identity="$4"
  local unix_user="$5"
  local hermes_home="$6"
  local model_preset="$7"
  local model_string="$8"
  local channels_json="$9"
  mkdir -p "$(dirname "$state_file")"
  REQUEST_ID="$request_id" \
  AGENT_ID="$agent_id" \
  REQUESTER_IDENTITY="$requester_identity" \
  UNIX_USER="$unix_user" \
  HERMES_HOME_ARG="$hermes_home" \
  MODEL_PRESET="$model_preset" \
  MODEL_STRING="$model_string" \
  CHANNELS_JSON="$channels_json" \
  ALMANAC_CONTROL_URL="$ALMANAC_MCP_URL" \
  ALMANAC_BOOTSTRAP_URL_VALUE="$ALMANAC_BOOTSTRAP_URL" \
  ALMANAC_QMD_URL_VALUE="$ALMANAC_QMD_URL" \
  python3 - "$state_file" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

payload = {
    "status": "pending",
    "request_id": os.environ["REQUEST_ID"],
    "agent_id": os.environ["AGENT_ID"],
    "requester_identity": os.environ["REQUESTER_IDENTITY"],
    "unix_user": os.environ["UNIX_USER"],
    "hermes_home": os.environ["HERMES_HOME_ARG"],
    "model_preset": os.environ["MODEL_PRESET"],
    "model_string": os.environ["MODEL_STRING"],
    "channels": json.loads(os.environ["CHANNELS_JSON"]),
    "control_plane_url": os.environ["ALMANAC_CONTROL_URL"],
    "bootstrap_url": os.environ["ALMANAC_BOOTSTRAP_URL_VALUE"],
    "qmd_url": os.environ["ALMANAC_QMD_URL_VALUE"],
    "requested_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
}
state_path = Path(sys.argv[1])
state_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

run_agent_flow() {
  local requester_identity="" unix_user="" source_ip="" request_file="" request_id="" prior_default_model=""
  local prior_default_channels="" model_preset="" channels_csv="" channels_json="" model_string="" token="" hermes_home=""
  local agent_id="" token_file="" hermes_state_file="" state_file="" activation_status="" activation_trigger_path=""
  local resuming_pending="0"
  local hermes_bin=""
  local preseeded_request_id="${ALMANAC_BOOTSTRAP_REQUEST_ID:-}"
  local preseeded_raw_token="${ALMANAC_BOOTSTRAP_RAW_TOKEN:-}"
  local preseeded_agent_id="${ALMANAC_BOOTSTRAP_AGENT_ID:-}"
  local preseeded_requester_identity="${ALMANAC_REQUESTER_IDENTITY:-}"
  local preseeded_source_ip="${ALMANAC_BOOTSTRAP_SOURCE_IP:-}"
  unset ALMANAC_BOOTSTRAP_REQUEST_ID ALMANAC_BOOTSTRAP_RAW_TOKEN ALMANAC_BOOTSTRAP_AGENT_ID
  unset ALMANAC_REQUESTER_IDENTITY ALMANAC_BOOTSTRAP_SOURCE_IP

  export PATH="$HOME/.local/bin:$PATH"
  require_linux_host "enrollment"
  requester_identity="${preseeded_requester_identity:-$(id -un)}"
  unix_user="$(id -un)"
  source_ip="${preseeded_source_ip:-$(awk '{print $1}' <<<"${SSH_CONNECTION:-${SSH_CLIENT:-127.0.0.1}}")}"
  hermes_home="$HERMES_HOME_DEFAULT"
  token_file="$hermes_home/secrets/almanac-bootstrap-token"
  state_file="$hermes_home/state/almanac-enrollment.json"
  mkdir -p "$hermes_home/secrets" "$hermes_home/state"
  request_file="$(mktemp)"
  trap 'rm -f "${request_file:-}" "${hermes_state_file:-}"' EXIT

  if [[ -n "$preseeded_request_id" && -n "$preseeded_raw_token" ]]; then
    request_id="$preseeded_request_id"
    token="$preseeded_raw_token"
    agent_id="${preseeded_agent_id:-}"
    requester_identity="${preseeded_requester_identity:-$requester_identity}"
    resuming_pending="1"
    echo "Using approved Almanac enrollment bootstrap: $request_id"
  elif [[ -f "$state_file" && -f "$token_file" && "$(json_get "$state_file" "status")" == "pending" ]]; then
    request_id="$(json_get "$state_file" "request_id")"
    agent_id="$(json_get "$state_file" "agent_id")"
    token="$(tr -d '[:space:]' <"$token_file")"
    model_preset="$(json_get "$state_file" "model_preset")"
    model_string="$(json_get "$state_file" "model_string")"
    channels_json="$(json_get "$state_file" "channels")"
    requester_identity="$(json_get "$state_file" "requester_identity")"
    if [[ -z "$requester_identity" ]]; then
      requester_identity="${ALMANAC_REQUESTER_IDENTITY:-$(id -un)}"
    fi
    if [[ -n "$channels_json" && "$channels_json" != "[]" ]]; then
      channels_csv="$(
        python3 - "$channels_json" <<'PY'
import json
import sys
channels = json.loads(sys.argv[1])
print(",".join(channels))
PY
      )"
    fi
    resuming_pending="1"
    echo "Resuming pending Almanac enrollment: $request_id"
  else
    rpc_call_with_retry "$request_file" \
      --url "$ALMANAC_BOOTSTRAP_URL" \
      --tool "bootstrap.handshake" \
      --json-args "$(REQUESTER_IDENTITY="$requester_identity" UNIX_USER="$unix_user" SOURCE_IP="$source_ip" python3 - <<'PY'
import json
import os
print(json.dumps({
  "requester_identity": os.environ["REQUESTER_IDENTITY"],
  "unix_user": os.environ["UNIX_USER"],
  "source_ip": os.environ["SOURCE_IP"],
}))
PY
      )"

    request_id="$(json_get "$request_file" "request_id")"
    if [[ -z "$request_id" ]]; then
      echo "Failed to create bootstrap request." >&2
      cat "$request_file" >&2
      exit 1
    fi

    token="$(json_get "$request_file" "raw_token")"
    if [[ -z "$token" ]]; then
      if [[ "$(json_get "$request_file" "resume_existing")" == "True" && -f "$token_file" ]]; then
        token="$(tr -d '[:space:]' <"$token_file")"
      else
        if [[ "$(json_get "$request_file" "resume_existing")" == "True" ]]; then
          echo "A pending bootstrap handshake already exists, but no local token file was found at $token_file." >&2
          echo "Reuse the original host-side enrollment session or clear the pending request before starting over." >&2
        fi
        echo "Bootstrap handshake did not return a pending token." >&2
        cat "$request_file" >&2
        exit 1
      fi
    fi
    agent_id="$(json_get "$request_file" "agent_id")"
    echo "Bootstrap handshake submitted: $request_id"
    echo "A pending Almanac key was issued; it will activate automatically after operator approval."

    prior_default_model="$(json_get "$request_file" "prior_defaults.model_preset")"
    prior_default_channels="$(json_get "$request_file" "prior_defaults.channels")"
    if [[ "$prior_default_channels" == "[]" || -z "$prior_default_channels" ]]; then
      prior_default_channels="tui-only"
    else
      prior_default_channels="$(
        python3 - "$prior_default_channels" <<'PY'
import json
import sys
channels = json.loads(sys.argv[1])
print(",".join(channels))
PY
      )"
    fi
  fi
  # Run Hermes setup BEFORE we capture model_preset/channels so the user's
  # final choice inside Hermes is the source of truth. Otherwise the manifest
  # and systemd gateway installation can drift from what Hermes is actually
  # running (e.g. the user picks a different model or gateway in the wizard).
  ensure_hermes_installed
  hermes_bin="$(current_hermes_bin)"

  if [[ -z "$preseeded_request_id" && "$resuming_pending" != "1" && "${ALMANAC_INIT_SKIP_HERMES_SETUP:-0}" != "1" && -t 0 ]]; then
    echo
    echo "Launching 'hermes setup' — Almanac will read back your model choice from Hermes when it finishes."
    HERMES_HOME="$hermes_home" "$hermes_bin" setup
  fi

  # Gateway setup only makes sense if we actually want Discord/Telegram. Ask
  # up front in a narrow prompt so we know whether to run the wizard.
  want_gateway="no"
  if [[ -z "$preseeded_request_id" && "$resuming_pending" != "1" && "${ALMANAC_INIT_SKIP_GATEWAY_SETUP:-0}" != "1" && -t 0 ]]; then
    read -r -p "Configure Hermes gateway for Discord/Telegram? [y/N]: " want_gateway_answer
    if is_yes "$want_gateway_answer"; then
      want_gateway="yes"
      if ! HERMES_HOME="$hermes_home" "$hermes_bin" gateway setup; then
        echo "Hermes gateway setup returned non-zero; Almanac will continue and install the gateway service from the saved Hermes config." >&2
      fi
    fi
  fi

  hermes_state_file="$(mktemp)"
  if probe_hermes_state_json "$hermes_home" "$hermes_bin" >"$hermes_state_file"; then
    model_preset="$(json_get "$hermes_state_file" "model_preset")"
    model_string="$(json_get "$hermes_state_file" "model_string")"
    channels_csv="$(json_get "$hermes_state_file" "channels_csv")"
  fi

  # Hermes is the source of truth after setup. Fall back to the seeded presets
  # only when Hermes has not produced a readable config yet.
  if [[ -z "${model_preset:-}" ]]; then
    model_preset="$(choose_model_preset "${prior_default_model:-codex}")"
  fi
  if [[ -z "${channels_csv:-}" ]]; then
    if [[ "$want_gateway" == "yes" ]]; then
      channels_csv="$(choose_channels_csv "${prior_default_channels:-tui-only}")"
    else
      channels_csv="tui-only"
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
  if [[ "$want_gateway" != "yes" && -z "${ALMANAC_INIT_CHANNELS:-}" ]]; then
    # If this enrollment skipped gateway setup, do not preserve stale external
    # channels from an older HERMES_HOME.
    channels_csv="tui-only"
    channels_json='["tui-only"]'
  fi
  if [[ -z "${model_string:-}" ]]; then
    case "${model_preset:-}" in
      codex) model_string="${ALMANAC_MODEL_PRESET_CODEX:-openai:codex}" ;;
      opus) model_string="${ALMANAC_MODEL_PRESET_OPUS:-anthropic:claude-opus}" ;;
      chutes) model_string="${ALMANAC_MODEL_PRESET_CHUTES:-chutes:auto-failover}" ;;
      *) model_string="${ALMANAC_MODEL_PRESET_CODEX:-openai:codex}" ;;
    esac
  fi

  printf '%s\n' "$token" >"$token_file"
  chmod 600 "$token_file"
  write_enrollment_state "$state_file" "$request_id" "$agent_id" "$requester_identity" "$unix_user" "$hermes_home" "$model_preset" "$model_string" "$channels_json"

  install_default_skills "$hermes_home"
  install_default_plugins "$hermes_home"
  register_default_mcps "$hermes_home"

  activation_trigger_path="${ALMANAC_ACTIVATION_TRIGGER_PATH:-${ALMANAC_PRIV_DIR:-$SHARED_REPO_DIR/almanac-priv}/state/activation-triggers/$agent_id.json}"
  "$SHARED_REPO_DIR/bin/install-agent-user-services.sh" \
    "$agent_id" \
    "$SHARED_REPO_DIR" \
    "$hermes_home" \
    "$channels_json" \
    "$activation_trigger_path" \
    "$hermes_bin"

  if [[ -x "$SHARED_REPO_DIR/bin/activate-agent.sh" ]]; then
    HERMES_HOME="$hermes_home" \
    ALMANAC_MCP_URL="$ALMANAC_MCP_URL" \
    ALMANAC_QMD_URL="$ALMANAC_QMD_URL" \
    ALMANAC_BOOTSTRAP_TOKEN_FILE="$token_file" \
    ALMANAC_ENROLLMENT_STATE_FILE="$state_file" \
    "$SHARED_REPO_DIR/bin/activate-agent.sh" || true
  fi

  activation_status="$(json_get "$state_file" "status")"
  if [[ "$activation_status" == "active" ]]; then
    HERMES_HOME="$hermes_home" \
    ALMANAC_MCP_URL="$ALMANAC_MCP_URL" \
    ALMANAC_QMD_URL="$ALMANAC_QMD_URL" \
    ALMANAC_BOOTSTRAP_TOKEN_FILE="$token_file" \
    ALMANAC_ENROLLMENT_STATE_FILE="$state_file" \
    "$SHARED_REPO_DIR/bin/user-agent-refresh.sh" >/dev/null 2>&1 || true
  elif [[ "${ALMANAC_INIT_WAIT_FOR_APPROVAL:-0}" == "1" ]]; then
    echo "Waiting for operator approval..."
    while true; do
      sleep 3
      "$SHARED_REPO_DIR/bin/almanac-rpc" \
        --url "$ALMANAC_BOOTSTRAP_URL" \
        --tool "bootstrap.status" \
        --json-args "$(REQUEST_ID="$request_id" SOURCE_IP="$source_ip" python3 - <<'PY'
import json
import os
print(json.dumps({
  "request_id": os.environ["REQUEST_ID"],
  "source_ip": os.environ["SOURCE_IP"],
}))
PY
        )" >/dev/null
      HERMES_HOME="$hermes_home" \
      ALMANAC_MCP_URL="$ALMANAC_MCP_URL" \
      ALMANAC_QMD_URL="$ALMANAC_QMD_URL" \
      ALMANAC_BOOTSTRAP_TOKEN_FILE="$token_file" \
      ALMANAC_ENROLLMENT_STATE_FILE="$state_file" \
      "$SHARED_REPO_DIR/bin/activate-agent.sh" || true
      activation_status="$(json_get "$state_file" "status")"
      if [[ "$activation_status" == "active" || "$activation_status" == "denied" || "$activation_status" == "expired" ]]; then
        break
      fi
    done
  fi

  if [[ "$activation_status" == "active" ]]; then
    cat <<EOF

Agent enrollment complete.

Agent ID:
  $agent_id
Hermes home:
  $hermes_home
Bootstrap token file:
  $token_file
Enrollment state:
  $state_file
Model preset:
  $model_preset -> $model_string
Channels:
  $channels_csv
Shared repo:
  $SHARED_REPO_DIR
Control plane:
  $ALMANAC_MCP_URL
Bootstrap handshake:
  $ALMANAC_BOOTSTRAP_URL
qmd:
  $ALMANAC_QMD_URL

EOF
    return 0
  fi

  cat <<EOF

Agent enrollment initialized and pending operator approval.

Request ID:
  $request_id
Agent ID:
  $agent_id
Hermes home:
  $hermes_home
Bootstrap token file:
  $token_file
Enrollment state:
  $state_file
Model preset:
  $model_preset -> $model_string
Channels:
  $channels_csv
Shared repo:
  $SHARED_REPO_DIR
Control plane:
  $ALMANAC_MCP_URL
Bootstrap handshake:
  $ALMANAC_BOOTSTRAP_URL
qmd:
  $ALMANAC_QMD_URL

The installed 4-hour user refresh timer will activate this agent automatically after approval.
EOF
}

run_update_flow() {
  require_linux_host "update"
  ensure_hermes_installed || {
    echo "Hermes is not installed for $(id -un)." >&2
    exit 1
  }
  local hermes_bin=""
  hermes_bin="$(current_hermes_bin)"
  "$hermes_bin" update || true
  if [[ -d "$SHARED_REPO_DIR/skills" ]]; then
    install_default_skills "$HERMES_HOME_DEFAULT"
  fi
  if [[ "$(id -un)" == "$ALMANAC_SERVICE_USER" && -x "$SHARED_REPO_DIR/bin/install-user-services.sh" ]]; then
    ALMANAC_ALLOW_NO_USER_BUS=1 "$SHARED_REPO_DIR/bin/install-user-services.sh" || true
    if [[ -x "$SHARED_REPO_DIR/bin/health.sh" ]]; then
      ALMANAC_ALLOW_SCAFFOLD_DEFAULTS=1 "$SHARED_REPO_DIR/bin/health.sh" || true
    fi
  fi
}

case "$MODE" in
  agent)
    run_agent_flow
    ;;
  infra)
    exec "$SHARED_REPO_DIR/deploy.sh" install "$@"
    ;;
  update)
    run_update_flow
    ;;
  *)
    echo "Usage: init.sh [agent|infra|update]" >&2
    exit 2
    ;;
esac
