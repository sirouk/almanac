#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$BOOTSTRAP_DIR/bin/common.sh"

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run this as root or with sudo."
  exit 1
fi

TARGET_DIR="/etc/systemd/system"
CONFIG_PATH="${CONFIG_FILE:-$ARCLINK_PRIV_CONFIG_DIR/arclink.env}"
mkdir -p "$TARGET_DIR"

reject_systemd_unit_value() {
  local name="$1" value="$2"
  case "$value" in
    *$'\n'*|*$'\r'*)
      echo "Refusing to render systemd unit with control characters in $name" >&2
      exit 1
      ;;
    *'$'*)
      echo "Refusing to render systemd unit with dollar-sign substitution in $name" >&2
      exit 1
      ;;
  esac
}

systemd_quote_value() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//%/%%}"
  printf '"%s"' "$value"
}

systemd_quote_exec_arg() {
  local value="$1"
  systemd_quote_value "$value"
}

reject_systemd_unit_value "ARCLINK_CONFIG_FILE" "$CONFIG_PATH"
reject_systemd_unit_value "ARCLINK_REPO_DIR" "$ARCLINK_REPO_DIR"
SYSTEMD_CONFIG_ENV="$(systemd_quote_value "ARCLINK_CONFIG_FILE=$CONFIG_PATH")"
SYSTEMD_PROVISION_EXEC="$(systemd_quote_exec_arg "$ARCLINK_REPO_DIR/bin/arclink-enrollment-provision.sh")"

cat >"$TARGET_DIR/arclink-enrollment-provision.service" <<EOF
[Unit]
Description=Provision approved ArcLink enrollments
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
Environment=HOME=/root
Environment=$SYSTEMD_CONFIG_ENV
ExecStart=$SYSTEMD_PROVISION_EXEC
EOF

cat >"$TARGET_DIR/arclink-enrollment-provision.timer" <<EOF
[Unit]
Description=Scan for approved ArcLink enrollments that need host provisioning

[Timer]
OnBootSec=45s
OnUnitActiveSec=1m
Persistent=true
Unit=arclink-enrollment-provision.service

[Install]
WantedBy=timers.target
EOF

cat >"$TARGET_DIR/arclink-notion-claim-poll.service" <<EOF
[Unit]
Description=Poll pending ArcLink self-serve Notion claims
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
Environment=HOME=/root
Environment=$SYSTEMD_CONFIG_ENV
ExecStart=$SYSTEMD_PROVISION_EXEC --claims-only
EOF

cat >"$TARGET_DIR/arclink-notion-claim-poll.timer" <<EOF
[Unit]
Description=Poll pending ArcLink self-serve Notion claims

[Timer]
OnBootSec=90s
OnUnitActiveSec=2m
Persistent=true
Unit=arclink-notion-claim-poll.service

[Install]
WantedBy=timers.target
EOF

chmod 0644 \
  "$TARGET_DIR/arclink-enrollment-provision.service" \
  "$TARGET_DIR/arclink-enrollment-provision.timer" \
  "$TARGET_DIR/arclink-notion-claim-poll.service" \
  "$TARGET_DIR/arclink-notion-claim-poll.timer"

start_system_service_if_idle() {
  local unit="$1" state=""
  state="$(systemctl show -p ActiveState --value "$unit" 2>/dev/null || true)"
  case "$state" in
    active|activating|reloading|deactivating)
      return 0
      ;;
  esac
  systemctl start "$unit" >/dev/null 2>&1 || true
}

systemctl daemon-reload
systemctl enable arclink-enrollment-provision.timer >/dev/null
systemctl restart arclink-enrollment-provision.timer
start_system_service_if_idle arclink-enrollment-provision.service
systemctl enable arclink-notion-claim-poll.timer >/dev/null
systemctl restart arclink-notion-claim-poll.timer
start_system_service_if_idle arclink-notion-claim-poll.service
