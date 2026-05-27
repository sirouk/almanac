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
  --ssh-user USER             Worker SSH/service user. Default: arclink.
  --ssh-port PORT             Worker SSH port. Default: 22.
  --region REGION             Placement region label.
  --capacity-slots N          Placement capacity slots. Default: 4.
  --provider NAME             Inventory provider. Default: manual.
  --state-root PATH           Worker state root. Default: /var/lib/arclink-fleet.
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
SSH_USER="${ARCLINK_FLEET_WORKER_USER:-arclink}"
SSH_PORT="22"
REGION=""
CAPACITY_SLOTS="4"
PROVIDER="manual"
SYSTEM_ROOT="${ARCLINK_FLEET_JOIN_SYSTEM_ROOT:-}"
STATE_ROOT="${ARCLINK_FLEET_STATE_ROOT:-}"
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
  if [[ -n "$SYSTEM_ROOT" ]]; then
    chmod 755 "$STATE_ROOT" 2>/dev/null || true
    return 0
  fi
  chown -R "$SSH_USER:$SSH_USER" "$STATE_ROOT" 2>/dev/null || true
  chmod 700 "$STATE_ROOT" 2>/dev/null || true
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
  } >"$CONFIG_FILE"
  chmod 644 "$CONFIG_FILE" 2>/dev/null || true
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
  python3 - "$PAYLOAD_FILE" "$SYSTEM_ROOT" "$HOSTNAME_VALUE" "$SSH_HOST" "$SSH_USER" "$SSH_PORT" "$REGION" "$CAPACITY_SLOTS" "$PROVIDER" "$fingerprint" "$PREREQ_AUDIT_FILE" <<'PY'
import json
import os
import platform
import sys

payload_path, system_root, hostname, ssh_host, ssh_user, ssh_port, region, capacity_slots, provider, fingerprint, prereq_audit_file = sys.argv[1:12]
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
}
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
  ensure_docker_group
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
