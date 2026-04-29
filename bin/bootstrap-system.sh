#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ALMANAC_USER="${ALMANAC_USER:-almanac}"
ALMANAC_HOME="${ALMANAC_HOME:-/home/$ALMANAC_USER}"
ALMANAC_REPO_DIR="${ALMANAC_REPO_DIR:-$ALMANAC_HOME/almanac}"
ALMANAC_PRIV_DIR="${ALMANAC_PRIV_DIR:-$ALMANAC_REPO_DIR/almanac-priv}"
ALMANAC_PRIV_CONFIG_DIR="${ALMANAC_PRIV_CONFIG_DIR:-$ALMANAC_PRIV_DIR/config}"
VAULT_DIR="${VAULT_DIR:-$ALMANAC_PRIV_DIR/vault}"
STATE_DIR="${STATE_DIR:-$ALMANAC_PRIV_DIR/state}"
NEXTCLOUD_STATE_DIR="${NEXTCLOUD_STATE_DIR:-$STATE_DIR/nextcloud}"
PUBLISHED_DIR="${PUBLISHED_DIR:-$ALMANAC_PRIV_DIR/published}"
QUARTO_PROJECT_DIR="${QUARTO_PROJECT_DIR:-$ALMANAC_PRIV_DIR/quarto}"
ENABLE_TAILSCALE_SERVE="${ENABLE_TAILSCALE_SERVE:-0}"
ALMANAC_AGENT_ENABLE_TAILSCALE_SERVE="${ALMANAC_AGENT_ENABLE_TAILSCALE_SERVE:-$ENABLE_TAILSCALE_SERVE}"
ALMANAC_INSTALL_PODMAN="${ALMANAC_INSTALL_PODMAN:-auto}"
ALMANAC_INSTALL_TAILSCALE="${ALMANAC_INSTALL_TAILSCALE:-auto}"
APT_UPDATED="0"

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run this as root or with sudo."
  exit 1
fi

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

host_uname_s() {
  uname -s 2>/dev/null || printf '%s\n' "unknown"
}

host_is_linux() {
  [[ "$(host_uname_s)" == "Linux" ]]
}

host_is_wsl() {
  local marker=""

  if ! host_is_linux; then
    return 1
  fi

  marker="$(cat /proc/sys/kernel/osrelease /proc/version 2>/dev/null || true)"
  [[ "$marker" =~ [Mm]icrosoft|WSL ]]
}

default_home_for_user() {
  local user="${1:-}"

  if [[ -z "$user" ]]; then
    return 1
  fi

  printf '/home/%s\n' "$user"
}

should_install_tool() {
  local tool="$1"
  local policy="${2:-auto}"
  local default_required="${3:-0}"

  if command_exists "$tool"; then
    return 1
  fi

  case "$policy" in
    1|y|Y|yes|YES|true|TRUE|on|ON)
      return 0
      ;;
    0|n|N|no|NO|false|FALSE|off|OFF)
      return 1
      ;;
    auto|"")
      [[ "$default_required" == "1" ]]
      return $?
      ;;
    *)
      [[ "$default_required" == "1" ]]
      return $?
      ;;
  esac
}

apt_update_once() {
  if [[ "$APT_UPDATED" == "1" ]]; then
    return 0
  fi
  apt-get update
  APT_UPDATED="1"
}

install_apt_packages() {
  local -a packages=("$@")

  if (( ${#packages[@]} == 0 )); then
    return 0
  fi

  apt_update_once
  DEBIAN_FRONTEND=noninteractive apt-get install -y "${packages[@]}"
}

require_supported_host() {
  if ! host_is_linux; then
    cat >&2 <<'EOF'
bootstrap-system.sh supports full Almanac host deployment only on Debian/Ubuntu-style
Linux hosts. Native macOS can still use `./deploy.sh write-config`, but the shared
service host needs Linux `systemd`, `loginctl`, and dedicated Unix users.
EOF
    exit 1
  fi

  if ! command_exists apt-get; then
    cat >&2 <<'EOF'
bootstrap-system.sh currently supports Debian/Ubuntu-style Linux hosts with `apt`.
Use Ubuntu or Debian for Almanac host deployment.
EOF
    exit 1
  fi

  if ! command_exists systemctl || ! command_exists loginctl || [[ ! -d /run/systemd/system ]]; then
    if host_is_wsl; then
      cat >&2 <<'EOF'
WSL2 was detected, but the Linux guest is not ready for full Almanac deployment.
Enable systemd inside the Ubuntu guest by adding this to /etc/wsl.conf:
  [boot]
  systemd=true

Then restart WSL from Windows with:
  wsl --shutdown
EOF
    else
      cat >&2 <<'EOF'
Almanac host deployment requires `systemd` and `loginctl` on the target Linux host.
EOF
    fi
    exit 1
  fi
}

install_base_linux_packages() {
  install_apt_packages \
    acl \
    curl \
    dbus-user-session \
    espeak-ng \
    inotify-tools \
    git \
    python3 \
    poppler-utils \
    uidmap \
    slirp4netns \
    fuse-overlayfs \
    sqlite3 \
    rsync
}

install_podman_if_requested() {
  if should_install_tool "podman" "$ALMANAC_INSTALL_PODMAN" "1"; then
    install_apt_packages podman
    return 0
  fi

  if ! command_exists podman; then
    echo "Podman is not installed. Nextcloud and per-agent code workspaces will stay unavailable until you install it." >&2
  fi
}

install_tailscale_if_requested() {
  local tailscale_default="0"

  if [[ "$ENABLE_TAILSCALE_SERVE" == "1" || "$ALMANAC_AGENT_ENABLE_TAILSCALE_SERVE" == "1" ]]; then
    tailscale_default="1"
  fi

  if should_install_tool "tailscale" "$ALMANAC_INSTALL_TAILSCALE" "$tailscale_default"; then
    if ! command_exists curl; then
      install_apt_packages curl
    fi
    curl -fsSL https://tailscale.com/install.sh | sh
    return 0
  fi

  if ! command_exists tailscale && [[ "$tailscale_default" == "1" ]]; then
    echo "Tailscale is not installed. Tailnet HTTPS serve and private ingress will stay unavailable until you install it." >&2
  fi
}

ensure_service_user() {
  if id -u "$ALMANAC_USER" >/dev/null 2>&1; then
    return 0
  fi

  useradd -m -s /bin/bash "$ALMANAC_USER"
}

require_supported_host
install_base_linux_packages
install_podman_if_requested
install_tailscale_if_requested

if [[ -z "${ALMANAC_HOME:-}" ]]; then
  ALMANAC_HOME="$(default_home_for_user "$ALMANAC_USER")"
fi

ensure_service_user

install -d -m 0750 -o "$ALMANAC_USER" -g "$ALMANAC_USER" \
  "$ALMANAC_HOME" \
  "$ALMANAC_PRIV_DIR" \
  "$ALMANAC_PRIV_CONFIG_DIR" \
  "$VAULT_DIR" \
  "$STATE_DIR" \
  "$NEXTCLOUD_STATE_DIR" \
  "$PUBLISHED_DIR" \
  "$QUARTO_PROJECT_DIR"
install -d -m 0755 -o "$ALMANAC_USER" -g "$ALMANAC_USER" "$ALMANAC_REPO_DIR"

rsync -a --delete \
  --exclude ".git" \
  --exclude ".git/" \
  --exclude "almanac-priv/" \
  --exclude "config/almanac.env" \
  "$BOOTSTRAP_DIR/" "$ALMANAC_REPO_DIR/"
chown -hR "$ALMANAC_USER:$ALMANAC_USER" "$ALMANAC_REPO_DIR" "$ALMANAC_PRIV_DIR"
chmod 0755 "$ALMANAC_REPO_DIR"

loginctl enable-linger "$ALMANAC_USER" || true
systemctl start "user@$(id -u "$ALMANAC_USER").service" || true

cat <<EOF

System bootstrap complete.

Next steps:
  Write private config to: $ALMANAC_PRIV_CONFIG_DIR/almanac.env
  sudo -iu $ALMANAC_USER env ALMANAC_CONFIG_FILE="$ALMANAC_PRIV_CONFIG_DIR/almanac.env" "$ALMANAC_REPO_DIR/bin/bootstrap-userland.sh"
  sudo -iu $ALMANAC_USER env ALMANAC_CONFIG_FILE="$ALMANAC_PRIV_CONFIG_DIR/almanac.env" "$ALMANAC_REPO_DIR/bin/install-user-services.sh"

EOF
