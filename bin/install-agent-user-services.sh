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
TARGET_DIR="$HOME/.config/systemd/user"
mkdir -p "$TARGET_DIR"

if [[ -z "$HERMES_BIN" || ! -x "$HERMES_BIN" ]]; then
  if command -v hermes >/dev/null 2>&1; then
    HERMES_BIN="$(command -v hermes)"
  else
    echo "Hermes binary not found. Expected executable at $HERMES_BIN" >&2
    exit 1
  fi
fi

cat >"$TARGET_DIR/almanac-user-agent-refresh.service" <<EOF
[Unit]
Description=Almanac user-agent refresh for $AGENT_ID

[Service]
Type=oneshot
Environment=ALMANAC_AGENT_ID=$AGENT_ID
Environment=HERMES_HOME=$HERMES_HOME
Environment=ALMANAC_SHARED_REPO_DIR=$SHARED_REPO_DIR
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

if [[ -n "$ACTIVATION_TRIGGER_PATH" ]]; then
  cat >"$TARGET_DIR/almanac-user-agent-activate.path" <<EOF
[Unit]
Description=Watch for Almanac activation events for $AGENT_ID

[Path]
PathChanged=$ACTIVATION_TRIGGER_PATH
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
ExecStart=$HERMES_BIN gateway
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
else
  rm -f "$TARGET_DIR/almanac-user-agent-gateway.service"
fi

uid="$(id -u)"
runtime_dir="/run/user/$uid"
bus_path="$runtime_dir/bus"
env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user daemon-reload
env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user enable almanac-user-agent-refresh.timer >/dev/null
env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" systemctl --user restart almanac-user-agent-refresh.timer >/dev/null

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
