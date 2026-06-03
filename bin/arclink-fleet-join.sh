#!/usr/bin/env bash
set -euo pipefail

case "$-" in
  *x*) set +x ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  arclink-fleet-join.sh --control-url URL (--token-file PATH | --token-stdin) --authorized-key-file PATH [options]

Options:
  --callback-url URL          Full enrollment callback URL. Overrides --control-url.
  --control-url URL           Sovereign Control Node base URL.
  --token-file PATH           Read the one-time enrollment token from the first line of PATH.
  --token-stdin               Read the one-time enrollment token from stdin.
  --authorized-key-file PATH  Public SSH key authorized for Control Node access.
  --hostname NAME             Worker hostname to attest.
  --ssh-host HOST             SSH address reported to the Control Node.
  --private-dns-name NAME     Production private mesh DNS/IP used for ArcPod links.
  --tailscale-dns-name NAME   Optional Tailscale MagicDNS access name for this worker.
  --wireguard-worker-ip IP    Worker WireGuard tunnel IP or CIDR. Used as private DNS/IP when none is supplied.
  --wireguard-control-public-key KEY
                              Control Node WireGuard public key.
  --wireguard-control-public-key-file PATH
                              Read the Control Node WireGuard public key from PATH.
  --wireguard-control-endpoint HOST:PORT
                              Control Node WireGuard endpoint.
  --wireguard-control-allowed-ips CIDR[,CIDR]
                              Worker peer AllowedIPs. Default: 10.44.0.1/32.
  --wireguard-interface NAME  Worker WireGuard interface. Default: wg-arclink.
  --wireguard-listen-port N   Optional worker WireGuard UDP listen port.
  --wireguard-persistent-keepalive N
                              WireGuard peer keepalive seconds. Default: 25.
  --skip-wireguard            Do not configure WireGuard even if WireGuard args/env are present.
  --ssh-user USER             Worker SSH/service user. Default: arclink.
  --ssh-port PORT             Worker SSH port. Default: 22.
  --region REGION             Placement region label.
  --capacity-slots N          Placement capacity slots. Default: 4.
  --provider NAME             Inventory provider. Default: manual.
  --state-root PATH           Worker state root. Default: /var/lib/arclink-fleet.
  --deployment-state-root-base PATH
                              ArcPod deployment root to create for the worker.
  --fleet-share-hub-root PATH Optional Captain fleet-share hub root to create for the worker.
  --fleet-share-ssh-key-path PATH
                              Worker-local SSH key used only by ArcPod Fleet sync jobs.
  --skip-prereq-install       Do not install prerequisites; record a skipped prereq summary.
  --json                      Print machine-readable status.

Enrollment tokens are accepted only from a file or stdin, never from argv.
EOF
}

fail() {
  echo "ArcLink fleet join failed: $*" >&2
  return 1
}

json_status() {
  local status="$1"
  local message="$2"
  python3 - "$status" "$message" "$STATE_ROOT" "$HOSTNAME_VALUE" <<'PY'
import json
import sys
print(json.dumps({"status": sys.argv[1], "message": sys.argv[2], "state_root": sys.argv[3], "hostname": sys.argv[4]}, sort_keys=True))
PY
}

truthy() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

CONTROL_URL=""
CALLBACK_URL=""
TOKEN_FILE=""
TOKEN_STDIN=0
AUTHORIZED_KEY_FILE=""
HOSTNAME_VALUE="$(hostname -f 2>/dev/null || hostname)"
SSH_HOST=""
PRIVATE_DNS_NAME="${ARCLINK_FLEET_PRIVATE_DNS_NAME:-${ARCLINK_FLEET_WIREGUARD_DNS_NAME:-${ARCLINK_FLEET_PRIVATE_MESH_DNS_NAME:-}}}"
TAILSCALE_DNS_NAME="${ARCLINK_FLEET_TAILSCALE_DNS_NAME:-}"
WIREGUARD_SKIP=0
WIREGUARD_CONTROL_PUBLIC_KEY="${ARCLINK_WIREGUARD_CONTROL_PUBLIC_KEY:-}"
WIREGUARD_CONTROL_PUBLIC_KEY_FILE=""
WIREGUARD_CONTROL_ENDPOINT="${ARCLINK_WIREGUARD_CONTROL_ENDPOINT:-}"
WIREGUARD_WORKER_IP="${ARCLINK_WIREGUARD_WORKER_IP:-${ARCLINK_FLEET_WIREGUARD_WORKER_IP:-}}"
WIREGUARD_CONTROL_ALLOWED_IPS="${ARCLINK_WIREGUARD_CONTROL_ALLOWED_IPS:-10.44.0.1/32}"
WIREGUARD_INTERFACE="${ARCLINK_WIREGUARD_INTERFACE:-wg-arclink}"
WIREGUARD_LISTEN_PORT="${ARCLINK_WIREGUARD_LISTEN_PORT:-}"
WIREGUARD_PERSISTENT_KEEPALIVE="${ARCLINK_WIREGUARD_PERSISTENT_KEEPALIVE:-25}"
WIREGUARD_PUBLIC_KEY=""
WIREGUARD_PRIVATE_IP=""
WIREGUARD_PRIVATE_CIDR=""
WIREGUARD_FIREWALL_STATUS="not-configured"
SSH_USER="${ARCLINK_FLEET_WORKER_USER:-arclink}"
SSH_PORT="22"
REGION=""
CAPACITY_SLOTS="4"
PROVIDER="manual"
SYSTEM_ROOT="${ARCLINK_FLEET_JOIN_SYSTEM_ROOT:-}"
STATE_ROOT="${ARCLINK_FLEET_STATE_ROOT:-}"
DEPLOYMENT_STATE_ROOT_BASE="${ARCLINK_DEPLOYMENT_STATE_ROOT_BASE:-${ARCLINK_STATE_ROOT_BASE:-}}"
FLEET_SHARE_HUB_ROOT="${ARCLINK_FLEET_SHARE_HUB_ROOT:-}"
FLEET_SHARE_SSH_KEY_PATH="${ARCLINK_FLEET_SHARE_SSH_KEY_PATH:-}"
FLEET_SHARE_SSH_PUBLIC_KEY=""
FLEET_SHARE_SSH_KNOWN_HOSTS_FILE="${ARCLINK_FLEET_SHARE_SSH_KNOWN_HOSTS_FILE:-}"
SKIP_PREREQS="${ARCLINK_SKIP_PREREQ_INSTALL:-0}"
JSON_OUTPUT=0

while (($#)); do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --control-url)
      CONTROL_URL="${2:-}"
      shift 2
      ;;
    --callback-url)
      CALLBACK_URL="${2:-}"
      shift 2
      ;;
    --token-file)
      TOKEN_FILE="${2:-}"
      shift 2
      ;;
    --token-stdin)
      TOKEN_STDIN=1
      shift
      ;;
    --token|--enrollment-token)
      echo "Enrollment tokens must be supplied with --token-file or --token-stdin, not argv." >&2
      exit 2
      ;;
    --authorized-key-file|--public-key-file)
      AUTHORIZED_KEY_FILE="${2:-}"
      shift 2
      ;;
    --hostname)
      HOSTNAME_VALUE="${2:-}"
      shift 2
      ;;
    --ssh-host)
      SSH_HOST="${2:-}"
      shift 2
      ;;
    --private-dns-name|--wireguard-dns-name|--private-mesh-dns-name)
      PRIVATE_DNS_NAME="${2:-}"
      shift 2
      ;;
    --tailscale-dns-name|--tailnet-dns-name|--magicdns-name)
      TAILSCALE_DNS_NAME="${2:-}"
      shift 2
      ;;
    --wireguard-worker-ip|--wireguard-private-ip)
      WIREGUARD_WORKER_IP="${2:-}"
      shift 2
      ;;
    --wireguard-control-public-key)
      WIREGUARD_CONTROL_PUBLIC_KEY="${2:-}"
      shift 2
      ;;
    --wireguard-control-public-key-file)
      WIREGUARD_CONTROL_PUBLIC_KEY_FILE="${2:-}"
      shift 2
      ;;
    --wireguard-control-endpoint)
      WIREGUARD_CONTROL_ENDPOINT="${2:-}"
      shift 2
      ;;
    --wireguard-control-allowed-ips)
      WIREGUARD_CONTROL_ALLOWED_IPS="${2:-}"
      shift 2
      ;;
    --wireguard-interface)
      WIREGUARD_INTERFACE="${2:-}"
      shift 2
      ;;
    --wireguard-listen-port)
      WIREGUARD_LISTEN_PORT="${2:-}"
      shift 2
      ;;
    --wireguard-persistent-keepalive)
      WIREGUARD_PERSISTENT_KEEPALIVE="${2:-}"
      shift 2
      ;;
    --skip-wireguard)
      WIREGUARD_SKIP=1
      shift
      ;;
    --ssh-user)
      SSH_USER="${2:-}"
      shift 2
      ;;
    --ssh-port)
      SSH_PORT="${2:-}"
      shift 2
      ;;
    --region)
      REGION="${2:-}"
      shift 2
      ;;
    --capacity-slots)
      CAPACITY_SLOTS="${2:-}"
      shift 2
      ;;
    --provider)
      PROVIDER="${2:-}"
      shift 2
      ;;
    --state-root)
      STATE_ROOT="${2:-}"
      shift 2
      ;;
    --deployment-state-root-base|--state-root-base)
      DEPLOYMENT_STATE_ROOT_BASE="${2:-}"
      shift 2
      ;;
    --fleet-share-hub-root)
      FLEET_SHARE_HUB_ROOT="${2:-}"
      shift 2
      ;;
    --fleet-share-ssh-key-path)
      FLEET_SHARE_SSH_KEY_PATH="${2:-}"
      shift 2
      ;;
    --skip-prereq-install)
      SKIP_PREREQS=1
      shift
      ;;
    --json)
      JSON_OUTPUT=1
      shift
      ;;
    *)
      echo "Unknown ArcLink fleet join option: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$STATE_ROOT" ]]; then
  if [[ -n "$SYSTEM_ROOT" ]]; then
    STATE_ROOT="$SYSTEM_ROOT/var/lib/arclink-fleet"
  else
    STATE_ROOT="/var/lib/arclink-fleet"
  fi
fi
SSH_HOST="${SSH_HOST:-$HOSTNAME_VALUE}"
WIREGUARD_PRIVATE_IP="${WIREGUARD_WORKER_IP%%/*}"
if [[ "$WIREGUARD_WORKER_IP" == */* ]]; then
  WIREGUARD_PRIVATE_CIDR="$WIREGUARD_WORKER_IP"
elif [[ -n "$WIREGUARD_WORKER_IP" ]]; then
  WIREGUARD_PRIVATE_CIDR="$WIREGUARD_WORKER_IP/32"
fi
if [[ -z "$PRIVATE_DNS_NAME" && -n "$WIREGUARD_PRIVATE_IP" ]]; then
  PRIVATE_DNS_NAME="$WIREGUARD_PRIVATE_IP"
fi
if [[ -z "$PRIVATE_DNS_NAME" && "$SSH_HOST" == *.wg* ]]; then
  PRIVATE_DNS_NAME="$SSH_HOST"
fi
if [[ -z "$TAILSCALE_DNS_NAME" && "$SSH_HOST" == *.ts.net ]]; then
  TAILSCALE_DNS_NAME="$SSH_HOST"
fi

ETC_DIR="${SYSTEM_ROOT:-}/etc/arclink"
USR_LOCAL_BIN="${SYSTEM_ROOT:-}/usr/local/bin"
if [[ -n "$SYSTEM_ROOT" ]]; then
  HOME_BASE="$SYSTEM_ROOT/home"
else
  HOME_BASE="/home"
fi
CONFIG_FILE="$ETC_DIR/fleet-worker.env"
ADMISSION_FILE="$STATE_ROOT/admission.state"
FINGERPRINT_FILE="$STATE_ROOT/machine-fingerprint"
PREREQ_AUDIT_FILE="$STATE_ROOT/prereq-audit.jsonl"
PAYLOAD_FILE="$STATE_ROOT/enrollment-callback-payload.json"
PROBE_WRAPPER_SOURCE="$SCRIPT_DIR/arclink-fleet-probe-wrapper"
PROBE_WRAPPER_TARGET="$USR_LOCAL_BIN/arclink-fleet-probe-wrapper"
if [[ -z "$FLEET_SHARE_SSH_KEY_PATH" ]]; then
  FLEET_SHARE_SSH_KEY_PATH="$STATE_ROOT/fleet-share-ssh/id_ed25519"
fi
if [[ -z "$FLEET_SHARE_SSH_KNOWN_HOSTS_FILE" ]]; then
  FLEET_SHARE_SSH_KNOWN_HOSTS_FILE="$STATE_ROOT/fleet-share-ssh/known_hosts"
fi

if [[ -z "$CALLBACK_URL" ]]; then
  if [[ -z "$CONTROL_URL" ]]; then
    fail "provide --control-url or --callback-url"
    exit 2
  fi
  CALLBACK_URL="${CONTROL_URL%/}/api/v1/fleet/enrollment/callback"
fi
if [[ "$TOKEN_STDIN" == "1" && -n "$TOKEN_FILE" ]]; then
  fail "choose only one token source"
  exit 2
fi
if [[ -z "$AUTHORIZED_KEY_FILE" || ! -r "$AUTHORIZED_KEY_FILE" ]]; then
  fail "provide a readable --authorized-key-file"
  exit 2
fi
if [[ -z "$HOSTNAME_VALUE" || -z "$SSH_USER" || -z "$SSH_HOST" ]]; then
  fail "hostname, ssh host, and ssh user are required"
  exit 2
fi
if ! [[ "$SSH_PORT" =~ ^[0-9]+$ ]] || (( SSH_PORT < 1 || SSH_PORT > 65535 )); then
  fail "ssh port must be a TCP port number"
  exit 2
fi
if ! [[ "$CAPACITY_SLOTS" =~ ^[0-9]+$ ]] || (( CAPACITY_SLOTS < 1 )); then
  fail "capacity slots must be a positive integer"
  exit 2
fi
if [[ ! -x "$PROBE_WRAPPER_SOURCE" ]]; then
  fail "probe wrapper source is missing or not executable: $PROBE_WRAPPER_SOURCE"
  exit 1
fi

mkdir -p "$STATE_ROOT" "$ETC_DIR" "$USR_LOCAL_BIN"
chmod 700 "$STATE_ROOT" 2>/dev/null || true
if [[ ! -f "$ADMISSION_FILE" ]]; then
  printf 'disabled\n' >"$ADMISSION_FILE"
fi

already_admitting=0
if [[ -f "$ADMISSION_FILE" ]] && grep -qx 'admitting' "$ADMISSION_FILE"; then
  already_admitting=1
fi

wireguard_requested() {
  [[ "$WIREGUARD_SKIP" != "1" ]] && {
    [[ -n "$WIREGUARD_WORKER_IP" ]] || \
    [[ -n "$WIREGUARD_CONTROL_PUBLIC_KEY" ]] || \
    [[ -n "$WIREGUARD_CONTROL_PUBLIC_KEY_FILE" ]] || \
    [[ -n "$WIREGUARD_CONTROL_ENDPOINT" ]]
  }
}

wireguard_should_configure() {
  wireguard_requested && \
    [[ -n "$WIREGUARD_PRIVATE_CIDR" ]] && \
    [[ -n "$WIREGUARD_CONTROL_PUBLIC_KEY" ]] && \
    [[ -n "$WIREGUARD_CONTROL_ENDPOINT" ]]
}

load_wireguard_control_public_key() {
  if [[ -n "$WIREGUARD_CONTROL_PUBLIC_KEY_FILE" ]]; then
    if [[ ! -r "$WIREGUARD_CONTROL_PUBLIC_KEY_FILE" ]]; then
      fail "WireGuard control public key file is not readable"
      return 1
    fi
    IFS= read -r WIREGUARD_CONTROL_PUBLIC_KEY <"$WIREGUARD_CONTROL_PUBLIC_KEY_FILE" || WIREGUARD_CONTROL_PUBLIC_KEY=""
  fi
  WIREGUARD_CONTROL_PUBLIC_KEY="${WIREGUARD_CONTROL_PUBLIC_KEY//[[:space:]]/}"
}

validate_wireguard_args() {
  if [[ "$WIREGUARD_SKIP" == "1" ]]; then
    return 0
  fi
  load_wireguard_control_public_key
  if ! wireguard_requested; then
    return 0
  fi
  if [[ -z "$WIREGUARD_PRIVATE_CIDR" || -z "$WIREGUARD_CONTROL_PUBLIC_KEY" || -z "$WIREGUARD_CONTROL_ENDPOINT" ]]; then
    fail "WireGuard setup requires worker IP, control public key, and control endpoint"
    return 1
  fi
  if [[ ! "$WIREGUARD_PRIVATE_CIDR" =~ ^[A-Za-z0-9_.:-]+/[0-9]{1,3}$ ]]; then
    fail "WireGuard worker IP must be an IP/CIDR such as 10.44.0.11/32"
    return 1
  fi
  if [[ ! "$WIREGUARD_CONTROL_PUBLIC_KEY" =~ ^[A-Za-z0-9+/=]{20,100}$ ]]; then
    fail "WireGuard control public key is not a valid public-key-shaped value"
    return 1
  fi
  if [[ ! "$WIREGUARD_CONTROL_ENDPOINT" =~ ^[A-Za-z0-9_.:-]+:[0-9]{1,5}$ ]]; then
    fail "WireGuard control endpoint must be host:port"
    return 1
  fi
  if [[ ! "$WIREGUARD_INTERFACE" =~ ^[A-Za-z0-9_.-]+$ ]]; then
    fail "WireGuard interface name is unsafe"
    return 1
  fi
  if [[ -n "$WIREGUARD_LISTEN_PORT" ]] && { [[ ! "$WIREGUARD_LISTEN_PORT" =~ ^[0-9]+$ ]] || (( WIREGUARD_LISTEN_PORT < 1 || WIREGUARD_LISTEN_PORT > 65535 )); }; then
    fail "WireGuard listen port must be a UDP port number"
    return 1
  fi
  if [[ ! "$WIREGUARD_PERSISTENT_KEEPALIVE" =~ ^[0-9]+$ ]]; then
    fail "WireGuard persistent keepalive must be a number"
    return 1
  fi
}

if ! validate_wireguard_args; then
  exit 2
fi

ensure_prereqs() {
  if truthy "$SKIP_PREREQS"; then
    python3 - "$PREREQ_AUDIT_FILE" <<'PY'
import json
import sys
from datetime import datetime, timezone
payload = {
    "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "surface": "worker-join",
    "action": "ensure_prereqs",
    "target": "worker",
    "status": "skipped",
    "detail": "--skip-prereq-install",
}
with open(sys.argv[1], "a", encoding="utf-8") as handle:
    handle.write(json.dumps(payload, sort_keys=True) + "\n")
PY
    return 0
  fi
  ARCLINK_PREREQ_SURFACE="worker-join" \
  ARCLINK_PREREQ_WIREGUARD="$(wireguard_should_configure && printf '1' || printf '0')" \
  ARCLINK_PREREQ_AUDIT_FILE="$PREREQ_AUDIT_FILE" \
    "$REPO_DIR/bin/lib/ensure-prereqs.sh"
}

ensure_user() {
  local user_home=""
  if [[ -n "$SYSTEM_ROOT" ]]; then
    user_home="$HOME_BASE/$SSH_USER"
    mkdir -p "$user_home"
    chmod 755 "$user_home" 2>/dev/null || true
    return 0
  fi
  if [[ "$(id -u)" != "0" ]]; then
    fail "run as root to create or repair the worker service user"
    return 1
  fi
  if ! id -u "$SSH_USER" >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash "$SSH_USER"
  fi
}

repair_state_permissions() {
  local root_path="" effective_path=""
  if [[ -n "$SYSTEM_ROOT" ]]; then
    chmod 755 "$STATE_ROOT" 2>/dev/null || true
    for root_path in "$DEPLOYMENT_STATE_ROOT_BASE" "$FLEET_SHARE_HUB_ROOT"; do
      [[ -z "$root_path" ]] && continue
      if [[ "$root_path" != /* || "$root_path" == "/" ]]; then
        fail "worker root path must be an absolute non-root path: $root_path"
        return 1
      fi
      effective_path="$SYSTEM_ROOT$root_path"
      mkdir -p "$effective_path"
      chmod 755 "$effective_path" 2>/dev/null || true
    done
    return 0
  fi
  chown -R "$SSH_USER:$SSH_USER" "$STATE_ROOT" 2>/dev/null || true
  chmod 700 "$STATE_ROOT" 2>/dev/null || true
  for root_path in "$DEPLOYMENT_STATE_ROOT_BASE" "$FLEET_SHARE_HUB_ROOT"; do
    [[ -z "$root_path" ]] && continue
    if [[ "$root_path" != /* || "$root_path" == "/" ]]; then
      fail "worker root path must be an absolute non-root path: $root_path"
      return 1
    fi
    mkdir -p "$root_path"
    chown "$SSH_USER:$SSH_USER" "$root_path" 2>/dev/null || true
    chmod 755 "$root_path" 2>/dev/null || true
  done
}

user_home_dir() {
  if [[ -n "$SYSTEM_ROOT" ]]; then
    printf '%s\n' "$HOME_BASE/$SSH_USER"
  else
    getent passwd "$SSH_USER" | awk -F: '{print $6}'
  fi
}

install_authorized_key() {
  local key_line="" user_home="" ssh_dir="" authorized_keys=""
  IFS= read -r key_line <"$AUTHORIZED_KEY_FILE" || key_line=""
  if [[ -z "$key_line" ]]; then
    fail "authorized key file is empty"
    return 1
  fi
  case "$key_line" in
    ssh-*|ecdsa-*|sk-ssh-*|sk-ecdsa-*) ;;
    *)
      fail "authorized key file does not look like an SSH public key"
      return 1
      ;;
  esac
  user_home="$(user_home_dir)"
  if [[ -z "$user_home" ]]; then
    fail "could not determine home directory for $SSH_USER"
    return 1
  fi
  ssh_dir="$user_home/.ssh"
  authorized_keys="$ssh_dir/authorized_keys"
  mkdir -p "$ssh_dir"
  touch "$authorized_keys"
  chmod 700 "$ssh_dir" 2>/dev/null || true
  chmod 600 "$authorized_keys" 2>/dev/null || true
  if ! grep -Fxq "$key_line" "$authorized_keys"; then
    printf '%s\n' "$key_line" >>"$authorized_keys"
  fi
  if [[ -z "$SYSTEM_ROOT" ]]; then
    chown -R "$SSH_USER:$SSH_USER" "$ssh_dir" 2>/dev/null || true
  fi
}

install_probe_wrapper() {
  cp "$PROBE_WRAPPER_SOURCE" "$PROBE_WRAPPER_TARGET"
  chmod 755 "$PROBE_WRAPPER_TARGET"
  {
    printf 'ARCLINK_FLEET_STATE_ROOT=%q\n' "$STATE_ROOT"
    printf 'ARCLINK_FLEET_ADMISSION_FILE=%q\n' "$ADMISSION_FILE"
    printf 'ARCLINK_FLEET_FINGERPRINT_FILE=%q\n' "$FINGERPRINT_FILE"
    printf 'ARCLINK_FLEET_HOSTNAME=%q\n' "$HOSTNAME_VALUE"
    printf 'ARCLINK_FLEET_SSH_PORT=%q\n' "$SSH_PORT"
    printf 'ARCLINK_FLEET_SHARE_SSH_KEY_PATH=%q\n' "$FLEET_SHARE_SSH_KEY_PATH"
    printf 'ARCLINK_FLEET_SHARE_SSH_KNOWN_HOSTS_FILE=%q\n' "$FLEET_SHARE_SSH_KNOWN_HOSTS_FILE"
  } >"$CONFIG_FILE"
  chmod 644 "$CONFIG_FILE" 2>/dev/null || true
}

ensure_fleet_share_ssh_key() {
  local key_dir="" user_group=""

  if [[ "$FLEET_SHARE_SSH_KEY_PATH" != /* || "$FLEET_SHARE_SSH_KEY_PATH" == "/" ]]; then
    fail "fleet-share SSH key path must be an absolute non-root path"
    return 1
  fi
  if [[ "$FLEET_SHARE_SSH_KNOWN_HOSTS_FILE" != /* || "$FLEET_SHARE_SSH_KNOWN_HOSTS_FILE" == "/" ]]; then
    fail "fleet-share SSH known_hosts path must be an absolute non-root path"
    return 1
  fi
  key_dir="$(dirname "$FLEET_SHARE_SSH_KEY_PATH")"
  mkdir -p "$key_dir" "$(dirname "$FLEET_SHARE_SSH_KNOWN_HOSTS_FILE")"
  chmod 700 "$key_dir" 2>/dev/null || true
  touch "$FLEET_SHARE_SSH_KNOWN_HOSTS_FILE"
  chmod 600 "$FLEET_SHARE_SSH_KNOWN_HOSTS_FILE" 2>/dev/null || true
  if [[ ! -f "$FLEET_SHARE_SSH_KEY_PATH" ]]; then
    if ! command -v ssh-keygen >/dev/null 2>&1; then
      fail "ssh-keygen is required to create the worker-local fleet-share SSH key"
      return 1
    fi
    ssh-keygen -t ed25519 -N "" -C "arclink-fleet-share@$HOSTNAME_VALUE" -f "$FLEET_SHARE_SSH_KEY_PATH" >/dev/null
  fi
  chmod 600 "$FLEET_SHARE_SSH_KEY_PATH" 2>/dev/null || true
  chmod 644 "$FLEET_SHARE_SSH_KEY_PATH.pub" 2>/dev/null || true
  if [[ -z "$SYSTEM_ROOT" ]]; then
    user_group="$(id -gn "$SSH_USER" 2>/dev/null || printf '%s' "$SSH_USER")"
    chown -R "$SSH_USER:$user_group" "$key_dir" "$(dirname "$FLEET_SHARE_SSH_KNOWN_HOSTS_FILE")" 2>/dev/null || true
  fi
  IFS= read -r FLEET_SHARE_SSH_PUBLIC_KEY <"$FLEET_SHARE_SSH_KEY_PATH.pub" || FLEET_SHARE_SSH_PUBLIC_KEY=""
  if [[ -z "$FLEET_SHARE_SSH_PUBLIC_KEY" ]]; then
    fail "could not read worker-local fleet-share SSH public key"
    return 1
  fi
}

ensure_docker_group() {
  if [[ -n "$SYSTEM_ROOT" ]]; then
    printf '%s\n' "$SSH_USER" >"$STATE_ROOT/docker-group-member"
    return 0
  fi
  if getent group docker >/dev/null 2>&1; then
    usermod -aG docker "$SSH_USER"
  fi
}

configure_wireguard_firewall() {
  if ! wireguard_should_configure; then
    WIREGUARD_FIREWALL_STATUS="not-configured"
    return 0
  fi
  if [[ -z "$WIREGUARD_LISTEN_PORT" ]]; then
    WIREGUARD_FIREWALL_STATUS="not-required"
    return 0
  fi
  if [[ -n "$SYSTEM_ROOT" ]]; then
    mkdir -p "$STATE_ROOT/wireguard"
    printf 'allow %s/udp for %s\n' "$WIREGUARD_LISTEN_PORT" "$WIREGUARD_INTERFACE" >"$STATE_ROOT/wireguard/firewall.plan"
    WIREGUARD_FIREWALL_STATUS="planned"
    return 0
  fi
  if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -qi '^Status: active'; then
    ufw allow "$WIREGUARD_LISTEN_PORT/udp" comment 'ArcLink WireGuard fleet mesh' >/dev/null || true
    WIREGUARD_FIREWALL_STATUS="ufw-allowed"
    return 0
  fi
  if command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
    firewall-cmd --permanent --add-port="$WIREGUARD_LISTEN_PORT/udp" >/dev/null || true
    firewall-cmd --reload >/dev/null || true
    WIREGUARD_FIREWALL_STATUS="firewalld-allowed"
    return 0
  fi
  WIREGUARD_FIREWALL_STATUS="unchanged"
  echo "No active ufw/firewalld manager detected; WireGuard worker firewall left unchanged." >&2
}

configure_wireguard() {
  local wg_dir="" private_key_file="" public_key_file="" config_file="" private_key="" listen_line=""

  if ! wireguard_should_configure; then
    return 0
  fi
  if ! command -v wg >/dev/null 2>&1; then
    fail "WireGuard setup requested, but wg is not installed"
    return 1
  fi
  if [[ -n "$SYSTEM_ROOT" ]]; then
    wg_dir="$SYSTEM_ROOT/etc/wireguard"
  else
    wg_dir="/etc/wireguard"
  fi
  mkdir -p "$wg_dir"
  chmod 700 "$wg_dir" 2>/dev/null || true
  private_key_file="$wg_dir/$WIREGUARD_INTERFACE.key"
  public_key_file="$wg_dir/$WIREGUARD_INTERFACE.pub"
  config_file="$wg_dir/$WIREGUARD_INTERFACE.conf"
  if [[ ! -f "$private_key_file" ]]; then
    ( umask 077 && wg genkey >"$private_key_file" )
  fi
  if [[ ! -f "$public_key_file" ]]; then
    wg pubkey <"$private_key_file" >"$public_key_file"
  fi
  chmod 600 "$private_key_file" "$config_file" 2>/dev/null || true
  chmod 644 "$public_key_file" 2>/dev/null || true
  private_key="$(cat "$private_key_file")"
  WIREGUARD_PUBLIC_KEY="$(cat "$public_key_file")"
  if [[ -n "$WIREGUARD_LISTEN_PORT" ]]; then
    listen_line="ListenPort = $WIREGUARD_LISTEN_PORT"
  fi
  (
    umask 077
    {
      printf '[Interface]\n'
      printf 'Address = %s\n' "$WIREGUARD_PRIVATE_CIDR"
      [[ -n "$listen_line" ]] && printf '%s\n' "$listen_line"
      printf 'PrivateKey = %s\n' "$private_key"
      printf '\n[Peer]\n'
      printf 'PublicKey = %s\n' "$WIREGUARD_CONTROL_PUBLIC_KEY"
      printf 'Endpoint = %s\n' "$WIREGUARD_CONTROL_ENDPOINT"
      printf 'AllowedIPs = %s\n' "$WIREGUARD_CONTROL_ALLOWED_IPS"
      printf 'PersistentKeepalive = %s\n' "$WIREGUARD_PERSISTENT_KEEPALIVE"
    } >"$config_file"
  )
  chmod 600 "$config_file" 2>/dev/null || true
  configure_wireguard_firewall
  if [[ -n "$SYSTEM_ROOT" ]]; then
    mkdir -p "$STATE_ROOT/wireguard"
    printf 'planned\n' >"$STATE_ROOT/wireguard/activation.state"
    return 0
  fi
  if wg show "$WIREGUARD_INTERFACE" >/dev/null 2>&1; then
    return 0
  fi
  if command -v systemctl >/dev/null 2>&1; then
    if systemctl enable --now "wg-quick@$WIREGUARD_INTERFACE" >/dev/null 2>&1; then
      return 0
    fi
  fi
  if command -v wg-quick >/dev/null 2>&1; then
    wg-quick up "$WIREGUARD_INTERFACE" >/dev/null 2>&1 || {
      fail "WireGuard config was written, but wg-quick could not activate $WIREGUARD_INTERFACE"
      return 1
    }
    return 0
  fi
  fail "WireGuard config was written, but wg-quick is not installed"
  return 1
}

compute_fingerprint() {
  local machine_id_path=""
  if [[ -n "$SYSTEM_ROOT" && -r "$SYSTEM_ROOT/etc/machine-id" ]]; then
    machine_id_path="$SYSTEM_ROOT/etc/machine-id"
  elif [[ -r /etc/machine-id ]]; then
    machine_id_path="/etc/machine-id"
  else
    machine_id_path="$STATE_ROOT/machine-id"
    if [[ ! -f "$machine_id_path" ]]; then
      python3 - "$machine_id_path" <<'PY'
import secrets
import sys
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    handle.write(secrets.token_hex(32) + "\n")
PY
      chmod 600 "$machine_id_path" 2>/dev/null || true
    fi
  fi
  python3 - "$machine_id_path" "$HOSTNAME_VALUE" "$SSH_PORT" <<'PY'
import hashlib
import sys
machine_id_path, hostname, ssh_port = sys.argv[1:4]
with open(machine_id_path, "r", encoding="utf-8", errors="ignore") as handle:
    machine_id = handle.readline().strip()
digest = hashlib.sha256(f"arclink-fleet-v1\0{machine_id}\0{hostname}\0{ssh_port}".encode("utf-8")).hexdigest()
print(f"sha256:{digest}")
PY
}

build_payload() {
  local fingerprint="$1"
  python3 - "$PAYLOAD_FILE" "$SYSTEM_ROOT" "$HOSTNAME_VALUE" "$SSH_HOST" "$PRIVATE_DNS_NAME" "$TAILSCALE_DNS_NAME" "$SSH_USER" "$SSH_PORT" "$REGION" "$CAPACITY_SLOTS" "$PROVIDER" "$fingerprint" "$PREREQ_AUDIT_FILE" "$WIREGUARD_INTERFACE" "$WIREGUARD_PRIVATE_IP" "$WIREGUARD_PRIVATE_CIDR" "$WIREGUARD_PUBLIC_KEY" "$WIREGUARD_CONTROL_ENDPOINT" "$WIREGUARD_LISTEN_PORT" "$WIREGUARD_FIREWALL_STATUS" "$FLEET_SHARE_SSH_KEY_PATH" "$FLEET_SHARE_SSH_KNOWN_HOSTS_FILE" "$FLEET_SHARE_SSH_PUBLIC_KEY" <<'PY'
import json
import os
import platform
import sys

(
    payload_path,
    system_root,
    hostname,
    ssh_host,
    private_dns_name,
    tailscale_dns_name,
    ssh_user,
    ssh_port,
    region,
    capacity_slots,
    provider,
    fingerprint,
    prereq_audit_file,
    wireguard_interface,
    wireguard_private_ip,
    wireguard_private_cidr,
    wireguard_public_key,
    wireguard_control_endpoint,
    wireguard_listen_port,
    wireguard_firewall_status,
    fleet_share_ssh_key_path,
    fleet_share_ssh_known_hosts_file,
    fleet_share_ssh_public_key,
) = sys.argv[1:24]
os_release_path = os.path.join(system_root, "etc", "os-release") if system_root else "/etc/os-release"
os_version = platform.platform()
if os.path.exists(os_release_path):
    values = {}
    with open(os_release_path, "r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if "=" in line:
                key, value = line.rstrip("\n").split("=", 1)
                values[key] = value.strip().strip('"')
    os_version = values.get("PRETTY_NAME") or values.get("ID") or os_version
prereq_events = []
if os.path.exists(prereq_audit_file):
    with open(prereq_audit_file, "r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            try:
                prereq_events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
prereq_summary = {
    "events": len(prereq_events),
    "statuses": {},
    "last_status": prereq_events[-1].get("status", "") if prereq_events else "",
}
for event in prereq_events:
    status = str(event.get("status", "unknown"))
    prereq_summary["statuses"][status] = prereq_summary["statuses"].get(status, 0) + 1
payload = {
    "hostname": hostname,
    "ssh_host": ssh_host,
    "private_dns_name": private_dns_name.strip().lower().strip("."),
    "tailscale_dns_name": tailscale_dns_name.strip().lower().strip("."),
    "ssh_user": ssh_user,
    "ssh_port": int(ssh_port),
    "region": region,
    "capacity_slots": int(capacity_slots),
    "provider": provider,
    "machine_fingerprint": fingerprint,
    "hardware_summary": {"os_version": os_version, "vcpu_cores": os.cpu_count() or 0},
    "connectivity_summary": {"ok": True, "probe_wrapper": "installed"},
    "prereq_audit": prereq_summary,
    "tags": {"source": "arclink-fleet-join"},
    "fleet_share_ssh_key_path": fleet_share_ssh_key_path,
    "fleet_share_ssh_known_hosts_file": fleet_share_ssh_known_hosts_file,
    "fleet_share_ssh_public_key": fleet_share_ssh_public_key,
}
if wireguard_private_ip or wireguard_public_key:
    payload["wireguard_interface"] = wireguard_interface
    payload["wireguard_private_ip"] = wireguard_private_ip
    payload["wireguard_private_cidr"] = wireguard_private_cidr
    payload["wireguard_public_key"] = wireguard_public_key
    payload["wireguard_control_endpoint"] = wireguard_control_endpoint
    payload["wireguard_listen_port"] = int(wireguard_listen_port) if wireguard_listen_port else 0
    payload["wireguard_firewall_status"] = wireguard_firewall_status
with open(payload_path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, sort_keys=True)
    handle.write("\n")
PY
}

post_callback() {
  local token="$1"
  printf '%s' "$token" | python3 -c '
import json
import os
import sys
import urllib.error
import urllib.request

url, payload_path = sys.argv[1:3]
token = sys.stdin.read().strip()
with open(payload_path, "r", encoding="utf-8") as handle:
    payload = json.load(handle)
sink = os.environ.get("ARCLINK_FLEET_JOIN_CALLBACK_SINK", "")
if sink:
    if os.environ.get("ARCLINK_FLEET_JOIN_CALLBACK_FAIL", "") in {"1", "true", "TRUE", "yes"}:
        print("callback sink forced failure", file=sys.stderr)
        raise SystemExit(1)
    with open(sink, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"authorization": "Bearer <redacted>", "payload": payload}, sort_keys=True) + "\n")
    raise SystemExit(0)
body = json.dumps(payload, sort_keys=True).encode("utf-8")
request = urllib.request.Request(
    url,
    data=body,
    method="POST",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status < 200 or response.status >= 300:
            print(f"callback returned HTTP {response.status}", file=sys.stderr)
            raise SystemExit(1)
except urllib.error.HTTPError as exc:
    print(f"callback returned HTTP {exc.code}", file=sys.stderr)
    raise SystemExit(1)
except urllib.error.URLError as exc:
    print(f"callback failed: {exc.reason}", file=sys.stderr)
    raise SystemExit(1)
' "$CALLBACK_URL" "$PAYLOAD_FILE"
}

read_token() {
  if [[ "$already_admitting" == "1" ]]; then
    printf '\n'
    return 0
  fi
  if [[ "$TOKEN_STDIN" == "1" ]]; then
    local value=""
    IFS= read -r value || true
    printf '%s\n' "$value"
    return 0
  fi
  if [[ -n "$TOKEN_FILE" ]]; then
    local value=""
    if [[ ! -r "$TOKEN_FILE" ]]; then
      fail "token file is not readable"
      return 1
    fi
    IFS= read -r value <"$TOKEN_FILE" || true
    printf '%s\n' "$value"
    return 0
  fi
  fail "provide --token-file or --token-stdin for first-time enrollment"
  return 1
}

main() {
  local token="" fingerprint=""
  printf 'disabled\n' >"$ADMISSION_FILE"
  ensure_prereqs
  ensure_user
  repair_state_permissions
  install_authorized_key
  install_probe_wrapper
  ensure_fleet_share_ssh_key
  ensure_docker_group
  configure_wireguard
  fingerprint="$(compute_fingerprint)"
  printf '%s\n' "$fingerprint" >"$FINGERPRINT_FILE"
  chmod 600 "$FINGERPRINT_FILE" 2>/dev/null || true
  if [[ -z "$SYSTEM_ROOT" ]]; then
    chown "$SSH_USER:$SSH_USER" "$ADMISSION_FILE" "$FINGERPRINT_FILE" 2>/dev/null || true
  fi
  build_payload "$fingerprint"

  if [[ "$already_admitting" == "1" ]]; then
    printf 'admitting\n' >"$ADMISSION_FILE"
    if [[ "$JSON_OUTPUT" == "1" ]]; then
      json_status "ready" "worker already admitted"
    else
      echo "ArcLink fleet worker is already admitted."
    fi
    return 0
  fi

  token="$(read_token)"
  if [[ -z "$token" ]]; then
    fail "enrollment token is empty"
    return 1
  fi
  if ! post_callback "$token"; then
    unset token
    printf 'disabled\n' >"$ADMISSION_FILE"
    fail "enrollment callback was rejected; worker remains non-admitting"
    return 1
  fi
  unset token
  printf 'admitting\n' >"$ADMISSION_FILE"
  if [[ "$JSON_OUTPUT" == "1" ]]; then
    json_status "ready" "worker enrolled and admitted"
  else
    echo "ArcLink fleet worker enrolled and admitted."
  fi
}

main "$@"
