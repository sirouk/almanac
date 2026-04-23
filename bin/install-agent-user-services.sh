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
HERMES_BIN="${6:-${ALMANAC_HERMES_BIN:-$SHARED_REPO_DIR/bin/hermes-shell.sh}}"
ACCESS_STATE_FILE="$HERMES_HOME/state/almanac-web-access.json"
AGENT_BACKUP_STATE_FILE="$HERMES_HOME/state/almanac-agent-backup.env"
TARGET_DIR="$HOME/.config/systemd/user"
PYTHON3_BIN="$(command -v python3 || true)"
PODMAN_BIN="$(command -v podman || true)"
ALMANAC_AGENTS_STATE_DIR="${ALMANAC_AGENTS_STATE_DIR:-$SHARED_REPO_DIR/almanac-priv/state/agents}"
mkdir -p "$TARGET_DIR"

if [[ -z "$HERMES_BIN" || ! -x "$HERMES_BIN" ]]; then
  if command -v hermes >/dev/null 2>&1; then
    HERMES_BIN="$(command -v hermes)"
  else
    echo "Hermes binary not found. Expected executable at $HERMES_BIN" >&2
    exit 1
  fi
fi

if [[ -z "$PYTHON3_BIN" || ! -x "$PYTHON3_BIN" ]]; then
  echo "python3 is required for agent web services." >&2
  exit 1
fi
if [[ -z "$PODMAN_BIN" ]]; then
  PODMAN_BIN="/usr/bin/podman"
fi

disable_native_hermes_gateway_units() {
  local runtime_dir="$1"
  local bus_path="$2"
  local units=""

  units="$(
    env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" \
      systemctl --user list-unit-files 'hermes-gateway*' --no-legend --plain 2>/dev/null | awk '{print $1}'
  )"
  if [[ -z "$units" ]]; then
    return 0
  fi

  # Almanac owns the enrolled-agent user accounts and manages their gateway
  # lifecycle via the almanac-user-agent-* units below. Disable any Hermes-
  # native gateway services in the same user manager so we never have two
  # service managers racing over one HERMES_HOME.
  # shellcheck disable=SC2086
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" \
    systemctl --user disable --now $units >/dev/null 2>&1 || true
}

enable_access_surfaces="0"
dashboard_backend_port=""
dashboard_proxy_port=""
code_port=""

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
    "code_port": str(state["code_port"]),
}
for key, value in values.items():
    print(f"{key}={shlex.quote(value)}")
PY
  )"
fi

cat >"$TARGET_DIR/almanac-user-agent-refresh.service" <<EOF
[Unit]
Description=Almanac user-agent refresh for $AGENT_ID

[Service]
Type=oneshot
Environment=ALMANAC_AGENT_ID=$AGENT_ID
Environment=HERMES_HOME=$HERMES_HOME
Environment=ALMANAC_SHARED_REPO_DIR=$SHARED_REPO_DIR
Environment=ALMANAC_AGENTS_STATE_DIR=$ALMANAC_AGENTS_STATE_DIR
ExecStart=$SHARED_REPO_DIR/bin/user-agent-refresh.sh
EOF

cat >"$TARGET_DIR/almanac-user-agent-refresh.timer" <<EOF
[Unit]
Description=Run Almanac user-agent refresh for $AGENT_ID every 4 hours

[Timer]
OnBootSec=2m
OnUnitActiveSec=4h
Unit=almanac-user-agent-refresh.service

[Install]
WantedBy=timers.target
EOF

cat >"$TARGET_DIR/almanac-user-agent-backup.service" <<EOF
[Unit]
Description=Back up Hermes home for $AGENT_ID to a private Git repository

[Service]
Type=oneshot
Environment=HERMES_HOME=$HERMES_HOME
ExecStart=$SHARED_REPO_DIR/bin/backup-agent-home.sh $HERMES_HOME
EOF

cat >"$TARGET_DIR/almanac-user-agent-backup.timer" <<EOF
[Unit]
Description=Back up Hermes home for $AGENT_ID every 4 hours

[Timer]
OnBootSec=5m
OnUnitActiveSec=4h
Unit=almanac-user-agent-backup.service

[Install]
WantedBy=timers.target
EOF

if [[ -n "$ACTIVATION_TRIGGER_PATH" ]]; then
  ACTIVATION_TRIGGER_DIR="$(dirname "$ACTIVATION_TRIGGER_PATH")"
  cat >"$TARGET_DIR/almanac-user-agent-activate.path" <<EOF
[Unit]
Description=Watch for Almanac activation events for $AGENT_ID

[Path]
PathChanged=$ACTIVATION_TRIGGER_PATH
PathModified=$ACTIVATION_TRIGGER_PATH
PathChanged=$ACTIVATION_TRIGGER_DIR
PathModified=$ACTIVATION_TRIGGER_DIR
Unit=almanac-user-agent-refresh.service

[Install]
WantedBy=default.target
EOF
else
  rm -f "$TARGET_DIR/almanac-user-agent-activate.path"
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
  cat >"$TARGET_DIR/almanac-user-agent-gateway.service" <<EOF
[Unit]
Description=Almanac user-agent messaging gateway for $AGENT_ID

[Service]
Environment=HERMES_HOME=$HERMES_HOME
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
  rm -f "$TARGET_DIR/almanac-user-agent-gateway.service"
fi

if [[ "$enable_access_surfaces" == "1" ]]; then
  cat >"$TARGET_DIR/almanac-user-agent-dashboard.service" <<EOF
[Unit]
Description=Almanac Hermes dashboard for $AGENT_ID

[Service]
Environment=HERMES_HOME=$HERMES_HOME
WorkingDirectory=$HERMES_HOME
ExecStart=$HERMES_BIN dashboard --host 127.0.0.1 --port $dashboard_backend_port --no-open
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

  cat >"$TARGET_DIR/almanac-user-agent-dashboard-proxy.service" <<EOF
[Unit]
Description=Almanac authenticated Hermes dashboard for $AGENT_ID
After=almanac-user-agent-dashboard.service
Requires=almanac-user-agent-dashboard.service

[Service]
Environment=HERMES_HOME=$HERMES_HOME
WorkingDirectory=$HERMES_HOME
ExecStart=$PYTHON3_BIN $SHARED_REPO_DIR/python/almanac_basic_auth_proxy.py --listen-host 127.0.0.1 --listen-port $dashboard_proxy_port --target http://127.0.0.1:$dashboard_backend_port --access-file $ACCESS_STATE_FILE --realm "Almanac Hermes"
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

  cat >"$TARGET_DIR/almanac-user-agent-code.service" <<EOF
[Unit]
Description=Almanac agent code workspace for $AGENT_ID
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
print(state.get("code_container_name") or "almanac-agent-code")
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
    "$TARGET_DIR/almanac-user-agent-dashboard.service" \
    "$TARGET_DIR/almanac-user-agent-dashboard-proxy.service" \
    "$TARGET_DIR/almanac-user-agent-code.service"
fi

uid="$(id -u)"
runtime_dir="/run/user/$uid"
bus_path="$runtime_dir/bus"
env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user daemon-reload
disable_native_hermes_gateway_units "$runtime_dir" "$bus_path"
env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user enable almanac-user-agent-refresh.timer >/dev/null
env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user restart almanac-user-agent-refresh.timer >/dev/null

if [[ -f "$AGENT_BACKUP_STATE_FILE" ]]; then
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user enable almanac-user-agent-backup.timer >/dev/null
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user restart almanac-user-agent-backup.timer >/dev/null
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user start almanac-user-agent-backup.service >/dev/null
else
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user disable --now almanac-user-agent-backup.timer >/dev/null 2>&1 || true
fi

if [[ -f "$TARGET_DIR/almanac-user-agent-activate.path" ]]; then
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user enable almanac-user-agent-activate.path >/dev/null
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user restart almanac-user-agent-activate.path >/dev/null
else
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user disable --now almanac-user-agent-activate.path >/dev/null 2>&1 || true
fi

if [[ -f "$TARGET_DIR/almanac-user-agent-gateway.service" ]]; then
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user enable almanac-user-agent-gateway.service >/dev/null
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user restart almanac-user-agent-gateway.service >/dev/null
else
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user disable --now almanac-user-agent-gateway.service >/dev/null 2>&1 || true
fi

if [[ -f "$TARGET_DIR/almanac-user-agent-dashboard.service" ]]; then
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user enable almanac-user-agent-dashboard.service >/dev/null
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user restart almanac-user-agent-dashboard.service >/dev/null
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user enable almanac-user-agent-dashboard-proxy.service >/dev/null
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user restart almanac-user-agent-dashboard-proxy.service >/dev/null
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user enable almanac-user-agent-code.service >/dev/null
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user restart almanac-user-agent-code.service >/dev/null
else
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user disable --now almanac-user-agent-dashboard-proxy.service >/dev/null 2>&1 || true
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user disable --now almanac-user-agent-dashboard.service >/dev/null 2>&1 || true
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user disable --now almanac-user-agent-code.service >/dev/null 2>&1 || true
fi
