#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NEXTCLOUD_UP = REPO / "bin" / "nextcloud-up.sh"


def run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=False)


def bash(script: str) -> subprocess.CompletedProcess[str]:
    return run(["bash", "-lc", script], cwd=REPO)


def extract(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_ensure_nextcloud_vault_mount_skips_duplicate_option_writes() -> None:
    text = NEXTCLOUD_UP.read_text()
    snippet = extract(text, "nextcloud_mount_state_from_json() {", "run_podman_nextcloud() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        log_path = tmp_path / "occ.log"
        mount_json = (
            '[{"mount_id":1,"mount_point":"\\/Vault","storage":"\\\\OC\\\\Files\\\\Storage\\\\Local",'
            '"authentication_type":"null::null","configuration":{"datadir":"\\/srv\\/vault"},'
            '"options":{"enable_sharing":true,"readonly":false},"applicable_users":[],"applicable_groups":[]}]'
        )
        script = f"""
{snippet}
LOG_PATH={log_path}
NEXTCLOUD_VAULT_MOUNT_POINT=/Vault
NEXTCLOUD_VAULT_CONTAINER_PATH=/srv/vault
nextcloud_occ() {{
  if [[ "$1" == "app:enable" ]]; then
    return 0
  fi
  if [[ "$1" == "files_external:list" ]]; then
    printf '%s\\n' '{mount_json}'
    return 0
  fi
  printf '%s\\n' "$*" >> "$LOG_PATH"
  return 0
}}
nextcloud_exec_www_data() {{
  return 0
}}
ensure_nextcloud_vault_mount
if [[ -f "$LOG_PATH" ]]; then
  cat "$LOG_PATH"
fi
"""
        result = bash(script)
        expect(result.returncode == 0, f"nextcloud mount idempotence case failed: {result.stderr}")
        expect(
            "files_external:option" not in result.stdout,
            f"expected no duplicate option writes when options already match, got: {result.stdout!r}",
        )
    print("PASS test_ensure_nextcloud_vault_mount_skips_duplicate_option_writes")


def test_nextcloud_bootstrap_disables_default_files_and_clears_admin_home() -> None:
    text = NEXTCLOUD_UP.read_text()
    custom_config = extract(text, "write_nextcloud_custom_config() {", "write_nextcloud_hook_script() {")
    hook_writer = extract(text, "write_nextcloud_hook_script() {", "write_nextcloud_post_install_hook() {")
    hook_scripts = extract(text, "write_nextcloud_hook_scripts() {", "wait_for_container_health() {")
    post_install = extract(text, "write_nextcloud_post_install_hook() {", "write_nextcloud_hook_scripts() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config_dir = tmp_path / "config"
        pre_hook_path = tmp_path / "hooks" / "pre-install.sh"
        hook_path = tmp_path / "hooks" / "post-install.sh"
        before_hook_path = tmp_path / "hooks" / "before-start.sh"
        skeleton_dir = tmp_path / "empty-skeleton"
        app_root = tmp_path / "app-root"
        admin_files = app_root / "var" / "www" / "html" / "data" / "admin" / "files"
        admin_files.mkdir(parents=True, exist_ok=True)
        (admin_files / "Documents").mkdir()
        (admin_files / "Documents" / "default.txt").write_text("seed", encoding="utf-8")
        (admin_files / "Photos").mkdir()
        (admin_files / "Photos" / "default.jpg").write_text("seed", encoding="utf-8")
        script = f"""
{custom_config}
{hook_writer}
{post_install}
{hook_scripts}
NEXTCLOUD_CUSTOM_CONFIG_DIR={config_dir}
NEXTCLOUD_EMPTY_SKELETON_DIR={skeleton_dir}
NEXTCLOUD_ARCLINK_CONFIG_FILE={config_dir / 'arclink.config.php'}
NEXTCLOUD_PRE_INSTALL_HOOK_FILE={pre_hook_path}
NEXTCLOUD_POST_INSTALL_HOOK_FILE={hook_path}
NEXTCLOUD_BEFORE_STARTING_HOOK_FILE={before_hook_path}
write_nextcloud_custom_config
write_nextcloud_hook_scripts
"""
        result = bash(script)
        expect(result.returncode == 0, f"nextcloud bootstrap snippet failed: {result.stderr}")

        config_body = (config_dir / "arclink.config.php").read_text(encoding="utf-8")
        expect("skeletondirectory" in config_body, config_body)
        expect("'skeletondirectory' => ''" in config_body, config_body)
        expect("'templatedirectory' => ''" in config_body, config_body)

        pre_hook_body = pre_hook_path.read_text(encoding="utf-8")
        expect("/arclink-config/arclink.config.php" in pre_hook_body, pre_hook_body)
        expect("/var/www/html/config/arclink.config.php" in pre_hook_body, pre_hook_body)

        before_hook_body = before_hook_path.read_text(encoding="utf-8")
        expect(before_hook_body == pre_hook_body, before_hook_body)

        hook_body = hook_path.read_text(encoding="utf-8")
        expect("/var/www/html/data/${admin_user}/files" in hook_body, hook_body)
        expect("find \"$files_dir\" -mindepth 1 -maxdepth 1 -exec rm -rf {} +" in hook_body, hook_body)
    print("PASS test_nextcloud_bootstrap_disables_default_files_and_clears_admin_home")


def test_nextcloud_runtime_mounts_pre_install_hook() -> None:
    compose_body = (REPO / "compose" / "nextcloud-compose.yml").read_text(encoding="utf-8")
    script_body = NEXTCLOUD_UP.read_text(encoding="utf-8")
    mount = "${NEXTCLOUD_PRE_INSTALL_HOOK_DIR}:/docker-entrypoint-hooks.d/pre-installation"
    expect(mount in compose_body, compose_body)
    expect('-v "${NEXTCLOUD_PRE_INSTALL_HOOK_DIR}:/docker-entrypoint-hooks.d/pre-installation"' in script_body, script_body)
    print("PASS test_nextcloud_runtime_mounts_pre_install_hook")


def test_nextcloud_vault_acl_skips_git_internals() -> None:
    script_body = NEXTCLOUD_UP.read_text(encoding="utf-8")
    expect("find \"$VAULT_DIR\" -path '*/.git' -prune -o -type d -print" in script_body, script_body)
    expect("find \"$VAULT_DIR\" -path '*/.git/*' -prune -o -type f -print" in script_body, script_body)
    print("PASS test_nextcloud_vault_acl_skips_git_internals")


def test_nextcloud_docker_mode_uses_compose_backend() -> None:
    script_body = NEXTCLOUD_UP.read_text(encoding="utf-8")
    expect('run_compose_nextcloud() {' in script_body, script_body)
    expect('[[ "${ARCLINK_CONTAINER_RUNTIME:-}" == "docker" || "${ARCLINK_DOCKER_MODE:-0}" == "1" ]]' in script_body, script_body)
    expect('NEXTCLOUD_RUNTIME="compose"' in script_body, script_body)
    expect('if nextcloud_using_podman; then' in script_body, script_body)
    docker_mode = extract(script_body, "if nextcloud_docker_mode_requested; then", "if command -v podman")
    expect('run_compose_nextcloud' in docker_mode, docker_mode)
    print("PASS test_nextcloud_docker_mode_uses_compose_backend")


def main() -> int:
    test_ensure_nextcloud_vault_mount_skips_duplicate_option_writes()
    test_nextcloud_bootstrap_disables_default_files_and_clears_admin_home()
    test_nextcloud_runtime_mounts_pre_install_hook()
    test_nextcloud_vault_acl_skips_git_internals()
    test_nextcloud_docker_mode_uses_compose_backend()
    print("PASS all 5 nextcloud regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
