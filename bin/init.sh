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

# almanac-rpc does not surface 429 Retry-After; handle it here by retrying with
# a backoff that honors Retry-After when the server provides it.
rpc_call_with_retry() {
  local out_file="$1"; shift
  local max_attempts="${ALMANAC_INIT_RPC_MAX_ATTEMPTS:-4}"
  local attempt=0
  local exit_code
  local err_file
  err_file="$(mktemp)"
  while (( attempt < max_attempts )); do
    attempt=$((attempt + 1))
    if "$SHARED_REPO_DIR/bin/almanac-rpc" "$@" >"$out_file" 2>"$err_file"; then
      rm -f "$err_file"
      return 0
    fi
    exit_code=$?
    if grep -qi 'rate-limited' "$err_file"; then
      local retry_after
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
  local answer
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
  local answer discord telegram channels="tui-only"
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
  if [[ "${discord,,}" =~ ^(y|yes|1)$ ]]; then
    channels="$channels,discord"
  fi
  if [[ "${telegram,,}" =~ ^(y|yes|1)$ ]]; then
    channels="$channels,telegram"
  fi
  printf '%s\n' "${channels:-$default}"
}

probe_hermes_state_json() {
  local hermes_home="$1"
  local hermes_bin="${2:-hermes}"
  local dump_file
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

ensure_hermes_installed() {
  if command -v hermes >/dev/null 2>&1; then
    return 0
  fi
  if [[ "${ALMANAC_INIT_SKIP_HERMES_INSTALL:-0}" == "1" ]]; then
    echo "Hermes is not installed and ALMANAC_INIT_SKIP_HERMES_INSTALL=1 was set." >&2
    return 1
  fi
  curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
  export PATH="$HOME/.local/bin:$PATH"
  command -v hermes >/dev/null 2>&1
}

install_default_skills() {
  local hermes_home="$1"
  local skill
  for skill in \
    "$SHARED_REPO_DIR/skills/almanac-qmd-mcp" \
    "$SHARED_REPO_DIR/skills/almanac-vault-reconciler" \
    "$SHARED_REPO_DIR/skills/almanac-first-contact" \
    "$SHARED_REPO_DIR/skills/almanac-vaults" \
    "$SHARED_REPO_DIR/skills/almanac-ssot"
  do
    [[ -d "$skill" ]] || continue
    HERMES_HOME="$hermes_home" hermes skills install "$skill" --yes >/dev/null 2>&1 || true
  done
}

register_default_mcps() {
  local hermes_home="$1"
  HERMES_HOME="$hermes_home" hermes mcp add almanac-mcp --url "$ALMANAC_MCP_URL" >/dev/null 2>&1 || true
  HERMES_HOME="$hermes_home" hermes mcp add almanac-qmd --url "$ALMANAC_QMD_URL" >/dev/null 2>&1 || true
  if [[ -n "$CHUTES_MCP_URL" ]]; then
    HERMES_HOME="$hermes_home" hermes mcp add chutes-kb --url "$CHUTES_MCP_URL" >/dev/null 2>&1 || true
  fi
}

run_agent_flow() {
  local requester_identity unix_user source_ip request_file status_file request_id prior_default_model
  local prior_default_channels model_preset channels_csv channels_json model_string token hermes_home
  local register_file refresh_file agent_id token_file hermes_state_file

  export PATH="$HOME/.local/bin:$PATH"
  requester_identity="${ALMANAC_REQUESTER_IDENTITY:-$(id -un)}"
  unix_user="$(id -un)"
  source_ip="$(awk '{print $1}' <<<"${SSH_CONNECTION:-${SSH_CLIENT:-127.0.0.1}}")"
  request_file="$(mktemp)"
  status_file="$(mktemp)"
  trap 'rm -f "$request_file" "$status_file" "${register_file:-}" "${refresh_file:-}" "${hermes_state_file:-}"' EXIT

  rpc_call_with_retry "$request_file" \
    --url "$ALMANAC_MCP_URL" \
    --tool "bootstrap.request" \
    --json-args "$(python3 - <<PY
import json
print(json.dumps({
  "requester_identity": ${requester_identity@Q},
  "unix_user": ${unix_user@Q},
  "source_ip": ${source_ip@Q},
}))
PY
    )"

  request_id="$(json_get "$request_file" "request_id")"
  if [[ -z "$request_id" ]]; then
    echo "Failed to create bootstrap request." >&2
    cat "$request_file" >&2
    exit 1
  fi

  echo "Bootstrap request submitted: $request_id"
  echo "Waiting for operator approval..."

  while true; do
    sleep 3
    "$SHARED_REPO_DIR/bin/almanac-rpc" \
      --url "$ALMANAC_MCP_URL" \
      --tool "bootstrap.status" \
      --json-args "$(python3 - <<PY
import json
print(json.dumps({"request_id": ${request_id@Q}, "source_ip": ${source_ip@Q}}))
PY
      )" >"$status_file"
    case "$(json_get "$status_file" "status")" in
      approved) break ;;
      denied)
        echo "Enrollment request denied." >&2
        cat "$status_file" >&2
        exit 1
        ;;
      expired)
        echo "Enrollment request expired." >&2
        cat "$status_file" >&2
        exit 1
        ;;
    esac
  done

  token="$(json_get "$status_file" "raw_token")"
  if [[ -z "$token" ]]; then
    echo "Approval was granted, but no bootstrap token was returned." >&2
    cat "$status_file" >&2
    exit 1
  fi

  prior_default_model="$(json_get "$status_file" "prior_defaults.model_preset")"
  prior_default_channels="$(json_get "$status_file" "prior_defaults.channels")"
  if [[ "$prior_default_channels" == "[]" || -z "$prior_default_channels" ]]; then
    prior_default_channels="tui-only"
  else
    prior_default_channels="$(
      python3 - <<PY
import json
channels = json.loads(${prior_default_channels@Q})
print(",".join(channels))
PY
    )"
  fi
  # Run Hermes setup BEFORE we capture model_preset/channels so the user's
  # final choice inside Hermes is the source of truth. Otherwise the manifest
  # and systemd gateway installation can drift from what Hermes is actually
  # running (e.g. the user picks a different model or gateway in the wizard).
  ensure_hermes_installed
  hermes_home="$HERMES_HOME_DEFAULT"
  mkdir -p "$hermes_home/secrets"

  if [[ "${ALMANAC_INIT_SKIP_HERMES_SETUP:-0}" != "1" && -t 0 ]]; then
    echo
    echo "Launching 'hermes setup' — Almanac will read back your model choice from Hermes when it finishes."
    HERMES_HOME="$hermes_home" hermes setup
  fi

  # Gateway setup only makes sense if we actually want Discord/Telegram. Ask
  # up front in a narrow prompt so we know whether to run the wizard.
  want_gateway="no"
  if [[ "${ALMANAC_INIT_SKIP_GATEWAY_SETUP:-0}" != "1" && -t 0 ]]; then
    read -r -p "Configure Hermes gateway for Discord/Telegram? [y/N]: " want_gateway_answer
    if [[ "${want_gateway_answer,,}" =~ ^(y|yes|1)$ ]]; then
      want_gateway="yes"
      HERMES_HOME="$hermes_home" hermes gateway setup
    fi
  fi

  hermes_state_file="$(mktemp)"
  if probe_hermes_state_json "$hermes_home" >"$hermes_state_file"; then
    model_preset="$(json_get "$hermes_state_file" "model_preset")"
    model_string="$(json_get "$hermes_state_file" "model_string")"
    channels_csv="$(json_get "$hermes_state_file" "channels_csv")"
  fi

  # Hermes is the source of truth after setup. Fall back to the seeded presets
  # only when Hermes has not produced a readable config yet.
  if [[ -z "$model_preset" ]]; then
    model_preset="$(choose_model_preset "${prior_default_model:-codex}")"
  fi
  if [[ -z "$channels_csv" ]]; then
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
  if [[ -z "$model_string" ]]; then
    case "$model_preset" in
      codex) model_string="${ALMANAC_MODEL_PRESET_CODEX:-openai:codex}" ;;
      opus) model_string="${ALMANAC_MODEL_PRESET_OPUS:-anthropic:claude-opus}" ;;
      chutes) model_string="${ALMANAC_MODEL_PRESET_CHUTES:-chutes:auto-failover}" ;;
      *) model_string="${ALMANAC_MODEL_PRESET_CODEX:-openai:codex}" ;;
    esac
  fi

  token_file="$hermes_home/secrets/almanac-bootstrap-token"
  printf '%s\n' "$token" >"$token_file"
  chmod 600 "$token_file"

  register_file="$(mktemp)"
  "$SHARED_REPO_DIR/bin/almanac-rpc" \
    --url "$ALMANAC_MCP_URL" \
    --tool "agents.register" \
    --json-args "$(python3 - <<PY
import json
print(json.dumps({
  "token": ${token@Q},
  "unix_user": ${unix_user@Q},
  "display_name": ${requester_identity@Q},
  "role": "user",
  "hermes_home": ${hermes_home@Q},
  "model_preset": ${model_preset@Q},
  "model_string": ${model_string@Q},
  "channels": json.loads(${channels_json@Q}),
}))
PY
    )" >"$register_file"

  agent_id="$(json_get "$register_file" "agent_id")"
  install_default_skills "$hermes_home"
  register_default_mcps "$hermes_home"

  refresh_file="$(mktemp)"
  "$SHARED_REPO_DIR/bin/almanac-rpc" \
    --url "$ALMANAC_MCP_URL" \
    --tool "vaults.refresh" \
    --json-args "$(python3 - <<PY
import json
print(json.dumps({"token": ${token@Q}}))
PY
    )" >"$refresh_file"

  "$SHARED_REPO_DIR/bin/install-agent-user-services.sh" \
    "$agent_id" \
    "$SHARED_REPO_DIR" \
    "$hermes_home" \
    "$channels_json"

  # Execute first-contact verification as code, not prose. Any non-zero exit is
  # a soft warning: enrollment has already succeeded and the operator can rerun
  # via scripts/run-first-contact.sh.
  if [[ -x "$SHARED_REPO_DIR/skills/almanac-first-contact/scripts/run-first-contact.sh" ]]; then
    first_contact_file="$(mktemp)"
    if HERMES_HOME="$hermes_home" \
       ALMANAC_MCP_URL="$ALMANAC_MCP_URL" \
       ALMANAC_QMD_URL="$ALMANAC_QMD_URL" \
       ALMANAC_BOOTSTRAP_TOKEN_FILE="$token_file" \
       ALMANAC_SHARED_REPO_DIR="$SHARED_REPO_DIR" \
       "$SHARED_REPO_DIR/skills/almanac-first-contact/scripts/run-first-contact.sh" >"$first_contact_file" 2>&1; then
      echo "First-contact verification:"
      cat "$first_contact_file"
    else
      echo "First-contact verification reported issues; see $first_contact_file" >&2
      cat "$first_contact_file" >&2
    fi
  fi

  cat <<EOF

Agent enrollment complete.

Agent ID:
  $agent_id
Hermes home:
  $hermes_home
Bootstrap token file:
  $token_file
Model preset:
  $model_preset -> $model_string
Channels:
  $channels_csv
Shared repo:
  $SHARED_REPO_DIR
Control plane:
  $ALMANAC_MCP_URL
qmd:
  $ALMANAC_QMD_URL

EOF
}

run_update_flow() {
  export PATH="$HOME/.local/bin:$PATH"
  command -v hermes >/dev/null 2>&1 || {
    echo "Hermes is not installed for $(id -un)." >&2
    exit 1
  }
  hermes update || true
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
