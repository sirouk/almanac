#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <agent-id> <shared-repo-dir> <hermes-home> [channels-json] [activation-trigger-path] [hermes-bin]" >&2
  exit 2
fi

AGENT_ID="$1"
SHARED_REPO_DIR="$2"
HERMES_HOME="$3"
CHANNELS_JSON="${4:-[\"tui-only\"]}"
ACTIVATION_TRIGGER_PATH="${5:-}"
HERMES_BIN="${6:-${ARCLINK_HERMES_BIN:-$SHARED_REPO_DIR/bin/hermes-shell.sh}}"
ACCESS_STATE_FILE="$HERMES_HOME/state/arclink-web-access.json"
TARGET_DIR="$HOME/.config/systemd/user"
PYTHON3_BIN="$(command -v python3 || true)"
PODMAN_BIN="$(command -v podman || true)"
ARCLINK_AGENTS_STATE_DIR="${ARCLINK_AGENTS_STATE_DIR:-$SHARED_REPO_DIR/arclink-priv/state/agents}"
ARCLINK_AGENT_VAULT_DIR="${ARCLINK_AGENT_VAULT_DIR:-${VAULT_DIR:-}}"
mkdir -p "$TARGET_DIR"

if [[ -z "$HERMES_BIN" || ! -x "$HERMES_BIN" ]]; then
  if command -v hermes >/dev/null 2>&1; then
    HERMES_BIN="$(command -v hermes)"
  else
    echo "Hermes binary not found. Expected executable at $HERMES_BIN" >&2
    exit 1
  fi
fi

resolve_hermes_runtime_dir() {
  local candidate=""

  if [[ -n "${RUNTIME_DIR:-}" ]]; then
    candidate="$RUNTIME_DIR"
    if [[ -f "$candidate/hermes-agent-src/tools/skills_sync.py" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi

  candidate="$(cd "$(dirname "$HERMES_BIN")/../.." 2>/dev/null && pwd -P || true)"
  if [[ -n "$candidate" && -f "$candidate/hermes-agent-src/tools/skills_sync.py" ]]; then
    printf '%s\n' "$candidate"
    return 0
  fi

  candidate="$SHARED_REPO_DIR/arclink-priv/state/runtime"
  if [[ -f "$candidate/hermes-agent-src/tools/skills_sync.py" ]]; then
    printf '%s\n' "$candidate"
    return 0
  fi

  return 1
}

HERMES_RUNTIME_DIR="$(resolve_hermes_runtime_dir || true)"
HERMES_BUNDLED_SKILLS_DIR=""
if [[ -n "$HERMES_RUNTIME_DIR" && -d "$HERMES_RUNTIME_DIR/hermes-agent-src/skills" ]]; then
  HERMES_BUNDLED_SKILLS_DIR="$HERMES_RUNTIME_DIR/hermes-agent-src/skills"
fi

if [[ -z "$PYTHON3_BIN" || ! -x "$PYTHON3_BIN" ]]; then
  echo "python3 is required for agent web services." >&2
  exit 1
fi
if [[ -z "$PODMAN_BIN" ]]; then
  PODMAN_BIN="/usr/bin/podman"
fi

if [[ -z "$ARCLINK_AGENT_VAULT_DIR" && -d "$SHARED_REPO_DIR/arclink-priv/vault" ]]; then
  ARCLINK_AGENT_VAULT_DIR="$SHARED_REPO_DIR/arclink-priv/vault"
fi

ensure_one_vault_link() {
  local link_path="$1"
  local target_path="$ARCLINK_AGENT_VAULT_DIR"
  local parent_dir=""

  if [[ -z "$target_path" || ! -d "$target_path" ]]; then
    return 0
  fi

  parent_dir="$(dirname "$link_path")"
  mkdir -p "$parent_dir"

  if [[ -L "$link_path" ]]; then
    local existing_target=""
    existing_target="$(readlink "$link_path" || true)"
    if [[ "$existing_target" == "$target_path" ]]; then
      return 0
    fi
    rm -f "$link_path"
  elif [[ -e "$link_path" ]]; then
    echo "Vault shortcut path already exists and is not a symlink: $link_path" >&2
    return 1
  fi

  ln -s "$target_path" "$link_path"
}

ensure_user_vault_links() {
  local status=0
  ensure_one_vault_link "$HOME/ArcLink" || status=1
  ensure_one_vault_link "$HERMES_HOME/Vault" || status=1
  ensure_one_vault_link "$HERMES_HOME/ArcLink" || status=1
  return "$status"
}

install_arclink_runtime_assets() {
  local bundled_skills_script="$SHARED_REPO_DIR/bin/sync-hermes-bundled-skills.sh"
  local skills_script="$SHARED_REPO_DIR/bin/install-arclink-skills.sh"
  local plugins_script="$SHARED_REPO_DIR/bin/install-arclink-plugins.sh"
  local mcps_script="$SHARED_REPO_DIR/bin/upsert-hermes-mcps.sh"
  local migrate_script="$SHARED_REPO_DIR/bin/migrate-hermes-config.sh"
  local runtime_dir=""

  if [[ -x "$bundled_skills_script" ]]; then
    "$bundled_skills_script" "$HERMES_HOME" "$HERMES_RUNTIME_DIR"
  fi
  if [[ -x "$skills_script" ]]; then
    "$skills_script" "$SHARED_REPO_DIR" "$HERMES_HOME"
  fi
  if [[ -x "$plugins_script" ]]; then
    "$plugins_script" "$SHARED_REPO_DIR" "$HERMES_HOME"
  fi
  if [[ -x "$mcps_script" ]]; then
    runtime_dir="${HERMES_RUNTIME_DIR:-$(cd "$(dirname "$HERMES_BIN")/../.." && pwd -P)}"
    if [[ -x "$runtime_dir/hermes-venv/bin/python3" ]]; then
      RUNTIME_DIR="$runtime_dir" "$mcps_script" "$HERMES_HOME"
    fi
  fi
  if [[ -x "$migrate_script" ]]; then
    "$migrate_script" "$HERMES_HOME" "$HERMES_RUNTIME_DIR"
  fi
}

install_arclink_cron_jobs() {
  local cron_jobs_script="$SHARED_REPO_DIR/bin/install-agent-cron-jobs.sh"
  if [[ -x "$cron_jobs_script" ]]; then
    "$cron_jobs_script" "$SHARED_REPO_DIR" "$HERMES_HOME" >/dev/null
  fi
}

install_local_user_wrappers() {
  local target_local_bin_dir="$HOME/.local/bin"
  local wrapper_path="$target_local_bin_dir/arclink-agent-hermes"
  local backup_wrapper="$target_local_bin_dir/arclink-agent-configure-backup"

  mkdir -p "$target_local_bin_dir"
  cat >"$wrapper_path" <<EOF
#!/usr/bin/env bash
set -euo pipefail
HERMES_HOME="\${HERMES_HOME:-$HERMES_HOME}"
HERMES_BUNDLED_SKILLS="\${HERMES_BUNDLED_SKILLS:-$HERMES_BUNDLED_SKILLS_DIR}"

should_restart_gateway() {
  case "\${1:-}" in
    setup|model|auth|login|logout|config|tools|mcp|plugins|skills)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

restart_gateway_if_possible() {
  local uid runtime_dir bus_path
  uid="\$(id -u)"
  runtime_dir="\${XDG_RUNTIME_DIR:-/run/user/\$uid}"
  bus_path="\$runtime_dir/bus"
  if [[ ! -S "\$bus_path" ]] || ! command -v systemctl >/dev/null 2>&1; then
    return 0
  fi
  printf '%s\n' "Restarting ArcLink messaging gateway so config changes apply..." >&2
  env XDG_RUNTIME_DIR="\$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=\$bus_path" \\
    systemctl --user restart arclink-user-agent-gateway.service >/dev/null 2>&1 || \\
    printf '%s\n' "Note: could not restart ArcLink messaging gateway automatically; run 'systemctl --user restart arclink-user-agent-gateway.service' in the remote account." >&2
}

set +e
env HERMES_HOME="\$HERMES_HOME" HERMES_BUNDLED_SKILLS="\$HERMES_BUNDLED_SKILLS" "$HERMES_BIN" "\$@"
status="\$?"
set -e
if [[ "\$status" -ne 0 ]]; then
  exit "\$status"
fi
if should_restart_gateway "\${1:-}"; then
  restart_gateway_if_possible
fi
EOF
  chmod 755 "$wrapper_path"

  cat >"$backup_wrapper" <<EOF
#!/usr/bin/env bash
set -euo pipefail
HERMES_HOME="\${HERMES_HOME:-$HERMES_HOME}"
exec env HERMES_HOME="\$HERMES_HOME" "$SHARED_REPO_DIR/bin/configure-agent-backup.sh" "\$HERMES_HOME" "\$@"
EOF
  chmod 755 "$backup_wrapper"
}

install_arclink_runtime_assets
install_arclink_cron_jobs
install_local_user_wrappers
ensure_user_vault_links

if [[ "${ARCLINK_AGENT_SERVICE_MANAGER:-systemd}" != "systemd" ]]; then
  exit 0
fi

disable_native_hermes_gateway_units() {
  local runtime_dir="$1"
  local bus_path="$2"
  local units=""

  units="$(
    env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" \
      systemctl --user list-unit-files 'hermes-gateway*' --no-legend --plain 2>/dev/null | awk '{print $1}' || true
  )"
  if [[ -z "$units" ]]; then
    return 0
  fi

  # ArcLink owns the enrolled-agent user accounts and manages their gateway
  # lifecycle via the arclink-user-agent-* units below. Disable any Hermes-
  # native gateway services in the same user manager so we never have two
  # service managers racing over one HERMES_HOME.
  # shellcheck disable=SC2086
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" \
    systemctl --user disable --now $units >/dev/null 2>&1 || true
}

enable_access_surfaces="0"
dashboard_backend_port=""
dashboard_proxy_port=""

if [[ -f "$ACCESS_STATE_FILE" ]]; then
  enable_access_surfaces="1"
  eval "$(
    python3 - "$ACCESS_STATE_FILE" <<'PY'
import json
import shlex
import sys
from pathlib import Path

state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
values = {
    "dashboard_backend_port": str(state["dashboard_backend_port"]),
    "dashboard_proxy_port": str(state["dashboard_proxy_port"]),
}
for key, value in values.items():
    print(f"{key}={shlex.quote(value)}")
PY
  )"
fi

cat >"$TARGET_DIR/arclink-user-agent-refresh.service" <<EOF
[Unit]
Description=ArcLink user-agent refresh for $AGENT_ID

[Service]
Type=oneshot
Environment=ARCLINK_AGENT_ID=$AGENT_ID
Environment=HERMES_HOME=$HERMES_HOME
$(if [[ -n "$HERMES_BUNDLED_SKILLS_DIR" ]]; then printf 'Environment=HERMES_BUNDLED_SKILLS=%s\n' "$HERMES_BUNDLED_SKILLS_DIR"; fi)
Environment=ARCLINK_SHARED_REPO_DIR=$SHARED_REPO_DIR
Environment=ARCLINK_AGENTS_STATE_DIR=$ARCLINK_AGENTS_STATE_DIR
ExecStart=$SHARED_REPO_DIR/bin/user-agent-refresh.sh
EOF

cat >"$TARGET_DIR/arclink-user-agent-refresh.timer" <<EOF
[Unit]
Description=Run ArcLink user-agent refresh for $AGENT_ID every 4 hours

[Timer]
OnBootSec=2m
OnUnitActiveSec=4h
Unit=arclink-user-agent-refresh.service

[Install]
WantedBy=timers.target
EOF

cat >"$TARGET_DIR/arclink-user-agent-backup.service" <<EOF
[Unit]
Description=Run an immediate Hermes-home backup for $AGENT_ID

[Service]
Type=oneshot
Environment=HERMES_HOME=$HERMES_HOME
$(if [[ -n "$HERMES_BUNDLED_SKILLS_DIR" ]]; then printf 'Environment=HERMES_BUNDLED_SKILLS=%s\n' "$HERMES_BUNDLED_SKILLS_DIR"; fi)
ExecStart=$SHARED_REPO_DIR/bin/backup-agent-home.sh $HERMES_HOME
EOF

rm -f "$TARGET_DIR/arclink-user-agent-backup.timer"

if [[ -n "$ACTIVATION_TRIGGER_PATH" ]]; then
  ACTIVATION_TRIGGER_DIR="$(dirname "$ACTIVATION_TRIGGER_PATH")"
  cat >"$TARGET_DIR/arclink-user-agent-activate.path" <<EOF
[Unit]
Description=Watch for ArcLink activation events for $AGENT_ID

[Path]
PathChanged=$ACTIVATION_TRIGGER_PATH
PathModified=$ACTIVATION_TRIGGER_PATH
PathChanged=$ACTIVATION_TRIGGER_DIR
PathModified=$ACTIVATION_TRIGGER_DIR
Unit=arclink-user-agent-refresh.service

[Install]
WantedBy=default.target
EOF
else
  rm -f "$TARGET_DIR/arclink-user-agent-activate.path"
fi

enable_gateway="$(
  python3 - "$CHANNELS_JSON" <<'PY'
import json
import sys

channels = json.loads(sys.argv[1])
print("1" if any(channel in {"discord", "telegram"} for channel in channels) else "0")
PY
)"

if [[ "$enable_gateway" == "1" ]]; then
  cat >"$TARGET_DIR/arclink-user-agent-gateway.service" <<EOF
[Unit]
Description=ArcLink user-agent messaging gateway for $AGENT_ID

[Service]
Environment=HERMES_HOME=$HERMES_HOME
$(if [[ -n "$HERMES_BUNDLED_SKILLS_DIR" ]]; then printf 'Environment=HERMES_BUNDLED_SKILLS=%s\n' "$HERMES_BUNDLED_SKILLS_DIR"; fi)
Environment=HERMES_CRON_SCRIPT_TIMEOUT=1800
Environment=TELEGRAM_REACTIONS=true
Environment=DISCORD_REACTIONS=true
WorkingDirectory=$HERMES_HOME
# Use Hermes's replace semantics so stale PID files or pre-reboot gateway
# ownership are reclaimed on startup rather than crash-looping on "race lost".
ExecStart=$HERMES_BIN gateway run --replace
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
else
  rm -f "$TARGET_DIR/arclink-user-agent-gateway.service"
fi

if [[ "$enable_access_surfaces" == "1" ]]; then
  cat >"$TARGET_DIR/arclink-user-agent-dashboard.service" <<EOF
[Unit]
Description=ArcLink Hermes dashboard for $AGENT_ID

[Service]
Environment=HERMES_HOME=$HERMES_HOME
$(if [[ -n "$HERMES_BUNDLED_SKILLS_DIR" ]]; then printf 'Environment=HERMES_BUNDLED_SKILLS=%s\n' "$HERMES_BUNDLED_SKILLS_DIR"; fi)
WorkingDirectory=$HERMES_HOME
ExecStart=$HERMES_BIN dashboard --host 127.0.0.1 --port $dashboard_backend_port --no-open
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

  cat >"$TARGET_DIR/arclink-user-agent-dashboard-proxy.service" <<EOF
[Unit]
Description=ArcLink authenticated Hermes dashboard for $AGENT_ID
After=arclink-user-agent-dashboard.service
Requires=arclink-user-agent-dashboard.service

[Service]
Environment=HERMES_HOME=$HERMES_HOME
WorkingDirectory=$HERMES_HOME
ExecStart=$PYTHON3_BIN $SHARED_REPO_DIR/python/arclink_basic_auth_proxy.py --listen-host 127.0.0.1 --listen-port $dashboard_proxy_port --target http://127.0.0.1:$dashboard_backend_port --access-file $ACCESS_STATE_FILE --realm "ArcLink Hermes"
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

  cat >"$TARGET_DIR/arclink-user-agent-code.service" <<EOF
[Unit]
Description=ArcLink agent code workspace for $AGENT_ID
After=network-online.target
Wants=network-online.target

[Service]
Environment=HERMES_HOME=$HERMES_HOME
WorkingDirectory=$HERMES_HOME
ExecStart=$SHARED_REPO_DIR/bin/run-agent-code-server.sh $ACCESS_STATE_FILE $HOME $HERMES_HOME
ExecStop=$PODMAN_BIN stop -t 10 $($PYTHON3_BIN - "$ACCESS_STATE_FILE" <<'PY'
import json
import sys
from pathlib import Path
state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(state.get("code_container_name") or "arclink-agent-code")
PY
)
Restart=always
RestartSec=10
TimeoutStartSec=300

[Install]
WantedBy=default.target
EOF
else
  rm -f \
    "$TARGET_DIR/arclink-user-agent-dashboard.service" \
    "$TARGET_DIR/arclink-user-agent-dashboard-proxy.service" \
    "$TARGET_DIR/arclink-user-agent-code.service"
fi

uid="$(id -u)"
runtime_dir="/run/user/$uid"
bus_path="$runtime_dir/bus"
env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user daemon-reload
disable_native_hermes_gateway_units "$runtime_dir" "$bus_path"
env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user enable arclink-user-agent-refresh.timer >/dev/null
env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user restart arclink-user-agent-refresh.timer >/dev/null

env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user disable --now arclink-user-agent-backup.timer >/dev/null 2>&1 || true

if [[ -f "$TARGET_DIR/arclink-user-agent-activate.path" ]]; then
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user enable arclink-user-agent-activate.path >/dev/null
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user restart arclink-user-agent-activate.path >/dev/null
else
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user disable --now arclink-user-agent-activate.path >/dev/null 2>&1 || true
fi

if [[ -f "$TARGET_DIR/arclink-user-agent-gateway.service" ]]; then
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user enable arclink-user-agent-gateway.service >/dev/null
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user restart arclink-user-agent-gateway.service >/dev/null
else
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user disable --now arclink-user-agent-gateway.service >/dev/null 2>&1 || true
fi

if [[ -f "$TARGET_DIR/arclink-user-agent-dashboard.service" ]]; then
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user enable arclink-user-agent-dashboard.service >/dev/null
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user restart arclink-user-agent-dashboard.service >/dev/null
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user enable arclink-user-agent-dashboard-proxy.service >/dev/null
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user restart arclink-user-agent-dashboard-proxy.service >/dev/null
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user enable arclink-user-agent-code.service >/dev/null
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user restart arclink-user-agent-code.service >/dev/null
else
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user disable --now arclink-user-agent-dashboard-proxy.service >/dev/null 2>&1 || true
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user disable --now arclink-user-agent-dashboard.service >/dev/null 2>&1 || true
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user disable --now arclink-user-agent-code.service >/dev/null 2>&1 || true
fi
