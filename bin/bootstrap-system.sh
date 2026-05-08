#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ARCLINK_USER="${ARCLINK_USER:-arclink}"
ARCLINK_HOME="${ARCLINK_HOME:-/home/$ARCLINK_USER}"
ARCLINK_REPO_DIR="${ARCLINK_REPO_DIR:-$ARCLINK_HOME/arclink}"
ARCLINK_PRIV_DIR="${ARCLINK_PRIV_DIR:-$ARCLINK_REPO_DIR/arclink-priv}"
ARCLINK_PRIV_CONFIG_DIR="${ARCLINK_PRIV_CONFIG_DIR:-$ARCLINK_PRIV_DIR/config}"
VAULT_DIR="${VAULT_DIR:-$ARCLINK_PRIV_DIR/vault}"
STATE_DIR="${STATE_DIR:-$ARCLINK_PRIV_DIR/state}"
NEXTCLOUD_STATE_DIR="${NEXTCLOUD_STATE_DIR:-$STATE_DIR/nextcloud}"
PUBLISHED_DIR="${PUBLISHED_DIR:-$ARCLINK_PRIV_DIR/published}"
QUARTO_PROJECT_DIR="${QUARTO_PROJECT_DIR:-$ARCLINK_PRIV_DIR/quarto}"
ENABLE_TAILSCALE_SERVE="${ENABLE_TAILSCALE_SERVE:-0}"
ARCLINK_AGENT_ENABLE_TAILSCALE_SERVE="${ARCLINK_AGENT_ENABLE_TAILSCALE_SERVE:-$ENABLE_TAILSCALE_SERVE}"
ARCLINK_INSTALL_PODMAN="${ARCLINK_INSTALL_PODMAN:-auto}"
ARCLINK_INSTALL_TAILSCALE="${ARCLINK_INSTALL_TAILSCALE:-auto}"
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
bootstrap-system.sh supports full ArcLink host deployment only on Debian/Ubuntu-style
Linux hosts. Native macOS can still use `./deploy.sh write-config`, but the shared
service host needs Linux `systemd`, `loginctl`, and dedicated Unix users.
EOF
    exit 1
  fi

  if ! command_exists apt-get; then
    cat >&2 <<'EOF'
bootstrap-system.sh currently supports Debian/Ubuntu-style Linux hosts with `apt`.
Use Ubuntu or Debian for ArcLink host deployment.
EOF
    exit 1
  fi

  if ! command_exists systemctl || ! command_exists loginctl || [[ ! -d /run/systemd/system ]]; then
    if host_is_wsl; then
      cat >&2 <<'EOF'
WSL2 was detected, but the Linux guest is not ready for full ArcLink deployment.
Enable systemd inside the Ubuntu guest by adding this to /etc/wsl.conf:
  [boot]
  systemd=true

Then restart WSL from Windows with:
  wsl --shutdown
EOF
    else
      cat >&2 <<'EOF'
ArcLink host deployment requires `systemd` and `loginctl` on the target Linux host.
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
    iproute2 \
    git \
    jq \
    python3 \
    python3-jsonschema \
    python3-yaml \
    poppler-utils \
    uidmap \
    slirp4netns \
    fuse-overlayfs \
    sqlite3 \
    rsync
}

install_podman_if_requested() {
  if should_install_tool "podman" "$ARCLINK_INSTALL_PODMAN" "1"; then
    install_apt_packages podman
    return 0
  fi

  if ! command_exists podman; then
    echo "Podman is not installed. Nextcloud and per-agent code workspaces will stay unavailable until you install it." >&2
  fi
}

install_tailscale_if_requested() {
  local tailscale_default="0"

  if [[ "$ENABLE_TAILSCALE_SERVE" == "1" || "$ARCLINK_AGENT_ENABLE_TAILSCALE_SERVE" == "1" ]]; then
    tailscale_default="1"
  fi

  if should_install_tool "tailscale" "$ARCLINK_INSTALL_TAILSCALE" "$tailscale_default"; then
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
  if id -u "$ARCLINK_USER" >/dev/null 2>&1; then
    return 0
  fi

  useradd -m -s /bin/bash "$ARCLINK_USER"
}

chown_tree_excluding_path() {
  local root="$1"
  local excluded="${2:-}"

  if [[ ! -e "$root" ]]; then
    return 0
  fi

  if [[ -n "$excluded" && -e "$excluded" ]]; then
    find "$root" -ignore_readdir_race \
      -path "$excluded" -prune -o \
      -exec chown -h "$ARCLINK_USER:$ARCLINK_USER" {} +
    return 0
  fi

  find "$root" -ignore_readdir_race \
    -exec chown -h "$ARCLINK_USER:$ARCLINK_USER" {} +
}

require_supported_host
install_base_linux_packages
install_podman_if_requested
install_tailscale_if_requested

if [[ -z "${ARCLINK_HOME:-}" ]]; then
  ARCLINK_HOME="$(default_home_for_user "$ARCLINK_USER")"
fi

ensure_service_user

install -d -m 0750 -o "$ARCLINK_USER" -g "$ARCLINK_USER" \
  "$ARCLINK_HOME" \
  "$ARCLINK_PRIV_DIR" \
  "$ARCLINK_PRIV_CONFIG_DIR" \
  "$VAULT_DIR" \
  "$STATE_DIR" \
  "$NEXTCLOUD_STATE_DIR" \
  "$PUBLISHED_DIR" \
  "$QUARTO_PROJECT_DIR"
install -d -m 0755 -o "$ARCLINK_USER" -g "$ARCLINK_USER" "$ARCLINK_REPO_DIR"

rsync -a --delete \
  --exclude ".git" \
  --exclude ".git/" \
  --exclude "arclink-priv/" \
  --exclude "config/arclink.env" \
  "$BOOTSTRAP_DIR/" "$ARCLINK_REPO_DIR/"
chown_tree_excluding_path "$ARCLINK_REPO_DIR" "$ARCLINK_PRIV_DIR"
chown_tree_excluding_path "$ARCLINK_PRIV_DIR" "$NEXTCLOUD_STATE_DIR"
chmod 0755 "$ARCLINK_REPO_DIR"

loginctl enable-linger "$ARCLINK_USER" || true
systemctl start "user@$(id -u "$ARCLINK_USER").service" || true

cat <<EOF

System bootstrap complete.

Next steps:
  Write private config to: $ARCLINK_PRIV_CONFIG_DIR/arclink.env
  sudo -iu $ARCLINK_USER env ARCLINK_CONFIG_FILE="$ARCLINK_PRIV_CONFIG_DIR/arclink.env" "$ARCLINK_REPO_DIR/bin/bootstrap-userland.sh"
  sudo -iu $ARCLINK_USER env ARCLINK_CONFIG_FILE="$ARCLINK_PRIV_CONFIG_DIR/arclink.env" "$ARCLINK_REPO_DIR/bin/install-user-services.sh"

EOF
