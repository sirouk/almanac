#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <access-state-file> <workspace-home> <hermes-home>" >&2
  exit 2
fi

ACCESS_STATE_FILE="$1"
WORKSPACE_HOME="$2"
HERMES_HOME="$3"

if [[ ! -f "$ACCESS_STATE_FILE" ]]; then
  echo "Access state file not found: $ACCESS_STATE_FILE" >&2
  exit 1
fi

resolve_container_runtime() {
  local requested="${ALMANAC_CONTAINER_RUNTIME:-}"

  case "$requested" in
    docker|podman)
      if command -v "$requested" >/dev/null 2>&1; then
        printf '%s\n' "$requested"
        return 0
      fi
      echo "$requested is required for the agent code workspace." >&2
      return 1
      ;;
    "")
      ;;
    *)
      echo "Unsupported ALMANAC_CONTAINER_RUNTIME=$requested; expected docker or podman." >&2
      return 1
      ;;
  esac

  if [[ "${ALMANAC_DOCKER_MODE:-0}" == "1" ]] && command -v docker >/dev/null 2>&1; then
    printf '%s\n' docker
    return 0
  fi

  if command -v podman >/dev/null 2>&1; then
    printf '%s\n' podman
    return 0
  fi

  if command -v docker >/dev/null 2>&1; then
    printf '%s\n' docker
    return 0
  fi

  echo "podman or docker is required for the agent code workspace." >&2
  return 1
}

CONTAINER_RUNTIME="$(resolve_container_runtime)"

docker_host_path() {
  local path="$1"
  local container_priv="${ALMANAC_DOCKER_CONTAINER_PRIV_DIR:-${ALMANAC_PRIV_DIR:-/home/almanac/almanac/almanac-priv}}"
  local host_priv="${ALMANAC_DOCKER_HOST_PRIV_DIR:-}"

  if [[ "$CONTAINER_RUNTIME" == "docker" && -n "$host_priv" && "$path" == "$container_priv"* ]]; then
    printf '%s%s\n' "$host_priv" "${path#"$container_priv"}"
    return 0
  fi

  printf '%s\n' "$path"
}

eval "$(
  python3 - "$ACCESS_STATE_FILE" "$WORKSPACE_HOME" "$HERMES_HOME" <<'PY'
import json
import os
import shlex
import sys
from pathlib import Path

state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
workspace_home = Path(sys.argv[2])
hermes_home = Path(sys.argv[3])
code_state_dir = hermes_home / "state" / "code-server"
config_dir = code_state_dir / "config"
data_dir = code_state_dir / "data"
workspace_dir = code_state_dir / "workspace"
workspace_file = workspace_dir / "almanac.code-workspace"
app_name = f"Almanac Agent Code ({state.get('unix_user') or 'agent'})"

vault_dir = ""
vault_alias = ""

def symlink_target_dir(candidate: Path) -> str:
    if candidate.is_symlink():
        target = os.readlink(candidate)
        if not os.path.isabs(target):
            target = str((candidate.parent / target).resolve(strict=False))
        if Path(target).is_dir():
            return target
    return ""

for alias_name in ("Almanac", "Vault"):
    target = symlink_target_dir(workspace_home / alias_name)
    if target:
        vault_dir = target
        vault_alias = alias_name
        break

if not vault_dir:
    for alias_name in ("Almanac", "Vault"):
        target = symlink_target_dir(hermes_home / alias_name)
        if target:
            vault_dir = target
            break

if vault_dir and vault_alias != "Almanac":
    almanac_alias = workspace_home / "Almanac"
    if not almanac_alias.exists() and not almanac_alias.is_symlink():
        try:
            almanac_alias.symlink_to(vault_dir)
            vault_alias = "Almanac"
        except OSError:
            pass

vault_container_dir = "/almanac-vault"
open_path = "/workspace"

values = {
    "CODE_PORT": str(state["code_port"]),
    "PASSWORD": str(state["password"]),
    "IMAGE": str(state.get("code_server_image") or "docker.io/codercom/code-server:4.116.0"),
    "CONTAINER_NAME": str(state.get("code_container_name") or "almanac-agent-code"),
    "CONFIG_DIR": str(config_dir),
    "DATA_DIR": str(data_dir),
    "WORKSPACE_FILE": str(workspace_file),
    "VAULT_DIR": vault_dir,
    "VAULT_CONTAINER_DIR": vault_container_dir,
    "OPEN_PATH": open_path,
    "APP_NAME": app_name,
}
for key, value in values.items():
    print(f"{key}={shlex.quote(value)}")
PY
)"

mkdir -p "$CONFIG_DIR" "$DATA_DIR"

python3 - "$CONFIG_DIR" "$DATA_DIR" "$WORKSPACE_FILE" <<'PY'
import json
import os
import sys
import tempfile
from pathlib import Path

config_dir = Path(sys.argv[1])
data_dir = Path(sys.argv[2])
workspace_file = Path(sys.argv[3])
legacy_user_dir = config_dir / "User"
user_dir = data_dir / "User"
settings_path = user_dir / "settings.json"
user_dir.mkdir(parents=True, exist_ok=True)

settings = {}
if settings_path.is_file():
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        if not isinstance(settings, dict):
            settings = {}
    except Exception:
        settings = {}
elif (legacy_user_dir / "settings.json").is_file():
    # Older Almanac builds seeded this file under the config dir, but
    # code-server reads VS Code user settings from the data dir.
    try:
        legacy_settings = json.loads((legacy_user_dir / "settings.json").read_text(encoding="utf-8"))
        if isinstance(legacy_settings, dict):
            settings = legacy_settings
    except Exception:
        settings = {}

changed = False
default_settings = {
    "workbench.colorTheme": "Default Dark Modern",
    "workbench.secondarySideBar.defaultVisibility": "hidden",
    "workbench.startupEditor": "none",
}

for key, value in default_settings.items():
    if not str(settings.get(key) or "").strip():
        settings[key] = value
        changed = True

if changed or not settings_path.is_file():
    fd, tmp_path = tempfile.mkstemp(dir=str(user_dir), prefix=".settings-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, settings_path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

try:
    workspace_file.unlink()
except FileNotFoundError:
    pass
PY

mount_args=(
  -v "$(docker_host_path "$WORKSPACE_HOME"):/workspace:rw"
  -v "$(docker_host_path "$CONFIG_DIR"):/home/coder/.config/code-server:rw"
  -v "$(docker_host_path "$DATA_DIR"):/home/coder/.local/share/code-server:rw"
)

if [[ -n "${VAULT_DIR:-}" && -d "$VAULT_DIR" ]]; then
  # Keep the host-level ~/Almanac symlink valid inside the container too.
  mount_args+=(
    -v "$(docker_host_path "$VAULT_DIR"):$VAULT_CONTAINER_DIR:rw"
    -v "$(docker_host_path "$VAULT_DIR"):$VAULT_DIR:rw"
  )
fi

CODE_SERVER_UID="$(stat -c '%u' "$WORKSPACE_HOME" 2>/dev/null || id -u)"
CODE_SERVER_GID="$(stat -c '%g' "$WORKSPACE_HOME" 2>/dev/null || id -g)"
if [[ "$CODE_SERVER_UID" == "0" && "${ALMANAC_AGENT_CODE_ALLOW_ROOT_CONTAINER:-0}" != "1" ]]; then
  echo "Refusing to run code-server as root against read-write Almanac mounts. Fix workspace ownership or set ALMANAC_AGENT_CODE_ALLOW_ROOT_CONTAINER=1 for a deliberate local recovery run." >&2
  exit 1
fi

run_code_server_container() {
  local runtime="$1"
  local run_args=()

  if [[ "$runtime" == "docker" ]]; then
    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
    run_args=(run --rm --name "$CONTAINER_NAME" --pull missing)
  else
    run_args=(run --rm --replace --name "$CONTAINER_NAME" --pull=missing --userns=keep-id)
  fi

  run_args+=(
    --user "$CODE_SERVER_UID:$CODE_SERVER_GID"
    -p "127.0.0.1:${CODE_PORT}:8080"
    -e PASSWORD="$PASSWORD"
    -e HOME=/home/coder
    "${mount_args[@]}"
    "$IMAGE"
    --bind-addr 0.0.0.0:8080
    --auth password
    --app-name "$APP_NAME"
    "$OPEN_PATH"
  )

  exec "$runtime" "${run_args[@]}"
}

run_code_server_container "$CONTAINER_RUNTIME"
