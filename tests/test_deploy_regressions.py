#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEPLOY_SH = REPO / "bin" / "deploy.sh"
CONTROL_PY = REPO / "python" / "almanac_control.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=False)


def extract(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def bash(script: str) -> subprocess.CompletedProcess[str]:
    return run(["bash", "-lc", script], cwd=REPO)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_bool_env_blank_uses_default() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_regression")
    expect(mod.bool_env("X", default=True, env={"X": ""}) is True, "blank string should fall back to default=True")
    expect(mod.bool_env("X", default=False, env={"X": ""}) is False, "blank string should fall back to default=False")
    expect(mod.bool_env("X", default=True, env={"X": "   "}) is True, "whitespace string should fall back to default=True")
    expect(mod.bool_env("X", default=False, env={"X": "1"}) is True, "explicit 1 should be true")
    print("PASS test_bool_env_blank_uses_default")


def render_runtime_config(channels: str, notify_platform: str, tg_flag: str = "", dc_flag: str = "") -> str:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "write_kv() {", "write_runtime_config() {")
    script = f"""
{snippet}
ALMANAC_NAME=almanac
ALMANAC_USER=almanac
ALMANAC_HOME=/home/almanac
ALMANAC_REPO_DIR=/home/almanac/almanac
ALMANAC_PRIV_DIR=/home/almanac/almanac/almanac-priv
ALMANAC_PRIV_CONFIG_DIR=/home/almanac/almanac/almanac-priv/config
VAULT_DIR=/home/almanac/almanac/almanac-priv/vault
STATE_DIR=/home/almanac/almanac/almanac-priv/state
NEXTCLOUD_STATE_DIR=/home/almanac/almanac/almanac-priv/state/nextcloud
RUNTIME_DIR=/home/almanac/almanac/almanac-priv/state/runtime
PUBLISHED_DIR=/home/almanac/almanac/almanac-priv/published
QMD_INDEX_NAME=almanac
QMD_COLLECTION_NAME=vault
BACKUP_GIT_BRANCH=main
NEXTCLOUD_PORT=18080
NEXTCLOUD_TRUSTED_DOMAIN=almanac.example.ts.net
POSTGRES_DB=nextcloud
POSTGRES_USER=nextcloud
POSTGRES_PASSWORD=dbpass
NEXTCLOUD_ADMIN_USER=admin
NEXTCLOUD_ADMIN_PASSWORD=adminpass
ENABLE_NEXTCLOUD=0
ENABLE_TAILSCALE_SERVE=0
ENABLE_PRIVATE_GIT=1
ENABLE_QUARTO=1
SEED_SAMPLE_VAULT=1
QUARTO_PROJECT_DIR=/tmp/quarto
QUARTO_OUTPUT_DIR=/tmp/published
ALMANAC_CURATOR_CHANNELS={shlex.quote(channels)}
OPERATOR_NOTIFY_CHANNEL_PLATFORM={shlex.quote(notify_platform)}
ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED={shlex.quote(tg_flag)}
ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED={shlex.quote(dc_flag)}
emit_runtime_config
"""
    result = bash(script)
    expect(result.returncode == 0, f"emit_runtime_config failed: {result.stderr}")
    return result.stdout


def source_value(config_text: str, key: str) -> str:
    with tempfile.NamedTemporaryFile("w", delete=False) as handle:
        handle.write(config_text)
        temp_path = handle.name
    try:
        script = f"source {shlex.quote(temp_path)} && printf '%s' \"${{{key}:-}}\""
        result = bash(script)
        expect(result.returncode == 0, f"failed to source generated config for {key}: {result.stderr}")
        return result.stdout
    finally:
        os.unlink(temp_path)


def test_emit_runtime_config_normalizes_curator_onboarding_flags() -> None:
    config = render_runtime_config("tui-only,telegram,discord", "telegram", "", "")
    tg = source_value(config, "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED")
    dc = source_value(config, "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED")
    expect(tg == "1", f"expected telegram onboarding flag to normalize to 1, got {tg!r}")
    expect(dc == "1", f"expected discord onboarding flag to normalize to 1, got {dc!r}")

    config = render_runtime_config("tui-only", "tui-only", "", "")
    tg = source_value(config, "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED")
    dc = source_value(config, "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED")
    expect(tg == "0", f"expected telegram onboarding flag to normalize to 0, got {tg!r}")
    expect(dc == "0", f"expected discord onboarding flag to normalize to 0, got {dc!r}")
    print("PASS test_emit_runtime_config_normalizes_curator_onboarding_flags")


def run_install_reexec_case(config_mode: int) -> tuple[int, str, str]:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "probe_path_status() {", "run_root_env_cmd() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        protected_dir = tmp_path / "protected"
        protected_dir.mkdir()
        config_path = protected_dir / "almanac.env"
        config_path.write_text("ALMANAC_USER=almanac\n")
        if config_mode == 0:
            protected_dir.chmod(0)
        else:
            config_path.chmod(config_mode)

        artifact_path = tmp_path / ".almanac-operator.env"
        artifact_path.write_text(f"ALMANAC_OPERATOR_DEPLOYED_CONFIG_FILE={shlex.quote(str(config_path))}\n")
        log_path = tmp_path / "sudo.log"

        script = f"""
LOG={shlex.quote(str(log_path))}
sudo() {{ printf '%s\n' "$@" >\"$LOG\"; return 0; }}
BOOTSTRAP_DIR={shlex.quote(str(REPO))}
SELF_PATH=/fake/deploy.sh
MODE=install
ALMANAC_OPERATOR_ARTIFACT_FILE={shlex.quote(str(artifact_path))}
{snippet}
maybe_reexec_install_for_config_defaults install
status=$?
printf 'STATUS=%s\n' "$status"
if [[ -f "$LOG" ]]; then
  printf 'SUDO_LOG_BEGIN\n'
  cat "$LOG"
  printf 'SUDO_LOG_END\n'
fi
"""
        try:
            result = bash(script)
            expect(result.returncode == 0, f"reexec case failed: {result.stderr}")
            status_line = next(line for line in result.stdout.splitlines() if line.startswith("STATUS="))
            status = int(status_line.split("=", 1)[1])
            sudo_log = ""
            if "SUDO_LOG_BEGIN" in result.stdout:
                sudo_log = result.stdout.split("SUDO_LOG_BEGIN\n", 1)[1].split("\nSUDO_LOG_END", 1)[0]
            return status, result.stdout, sudo_log
        finally:
            if config_mode == 0:
                protected_dir.chmod(0o700)


def test_install_reexecs_for_unreadable_breadcrumb_config() -> None:
    status, output, sudo_log = run_install_reexec_case(0)
    expect(status == 0, f"expected unreadable-config case to reexec via sudo, got status {status}")
    expect("Switching to sudo before prompting" in output, "expected install flow to announce sudo-before-prompting path")
    expect("env" in sudo_log and "ALMANAC_CONFIG_FILE=" in sudo_log and "/fake/deploy.sh" in sudo_log and "install" in sudo_log,
           f"unexpected sudo invocation: {sudo_log!r}")
    print("PASS test_install_reexecs_for_unreadable_breadcrumb_config")


def test_install_does_not_reexec_for_readable_breadcrumb_config() -> None:
    status, output, sudo_log = run_install_reexec_case(0o600)
    expect(status == 1, f"expected readable-config case to skip reexec, got status {status}")
    expect("Switching to sudo before prompting" not in output, "readable config should not trigger sudo-before-prompting path")
    expect(sudo_log.strip() == "", f"readable config should not call sudo, got {sudo_log!r}")
    print("PASS test_install_does_not_reexec_for_readable_breadcrumb_config")


def test_write_operator_artifact_falls_back_to_discovered_config() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "probe_path_status() {", "run_as_user() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config_path = tmp_path / "deployed" / "almanac.env"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("ALMANAC_USER=operator-svc\n", encoding="utf-8")
        artifact_path = tmp_path / ".almanac-operator.env"

        script = f"""
BOOTSTRAP_DIR={shlex.quote(str(tmp_path))}
ALMANAC_OPERATOR_ARTIFACT_FILE={shlex.quote(str(artifact_path))}
DISCOVERED_CONFIG={shlex.quote(str(config_path))}
CONFIG_TARGET=""
ALMANAC_USER=operator-svc
ALMANAC_REPO_DIR=/srv/operator-svc/almanac
ALMANAC_PRIV_DIR=/srv/operator-svc/almanac-priv
{snippet}
write_operator_checkout_artifact
printf 'ARTIFACT_BEGIN\\n'
cat {shlex.quote(str(artifact_path))}
printf 'ARTIFACT_END\\n'
"""
        result = bash(script)
        expect(result.returncode == 0, f"artifact fallback case failed: {result.stderr}")
        artifact = result.stdout.split("ARTIFACT_BEGIN\n", 1)[1].split("\nARTIFACT_END", 1)[0]
        expect(
            f"ALMANAC_OPERATOR_DEPLOYED_CONFIG_FILE={config_path}" in artifact,
            f"expected artifact to record discovered config path, got: {artifact!r}",
        )
        expect(
            "ALMANAC_OPERATOR_DEPLOYED_USER=operator-svc" in artifact,
            f"expected artifact to record service user, got: {artifact!r}",
        )
    print("PASS test_write_operator_artifact_falls_back_to_discovered_config")


def test_discover_existing_config_uses_artifact_priv_dir_hint() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "probe_path_status() {", "load_detected_config() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        priv_dir = tmp_path / "deployed" / "almanac-priv"
        config_path = priv_dir / "config" / "almanac.env"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("ALMANAC_USER=operator-svc\n")
        artifact_path = tmp_path / ".almanac-operator.env"
        artifact_path.write_text(
            "\n".join(
                [
                    "ALMANAC_OPERATOR_DEPLOYED_USER=operator-svc",
                    f"ALMANAC_OPERATOR_DEPLOYED_PRIV_DIR={shlex.quote(str(priv_dir))}",
                    "",
                ]
            )
        )
        script = f"""
BOOTSTRAP_DIR={shlex.quote(str(REPO))}
ALMANAC_OPERATOR_ARTIFACT_FILE={shlex.quote(str(artifact_path))}
{snippet}
discover_existing_config
status=$?
printf 'STATUS=%s\\n' "$status"
printf 'DISCOVERED=%s\\n' "${{DISCOVERED_CONFIG:-}}"
"""
        result = bash(script)
        expect(result.returncode == 0, f"discover_existing_config case failed: {result.stderr}")
        expect(f"STATUS=0" in result.stdout, f"expected discover_existing_config to succeed, got: {result.stdout!r}")
        expect(
            f"DISCOVERED={config_path}" in result.stdout,
            f"expected artifact priv-dir hint to resolve {config_path}, got: {result.stdout!r}",
        )
    print("PASS test_discover_existing_config_uses_artifact_priv_dir_hint")


def test_collect_install_answers_defaults_to_detected_service_user() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "collect_install_answers() {", "collect_remove_answers() {")
    script = f"""
{snippet}
ask() {{ printf '%s' "${{2:-}}"; }}
ask_yes_no() {{ printf '%s' "${{2:-0}}"; }}
ask_secret() {{ printf '%s' ""; }}
ask_secret_with_default() {{ printf '%s' "${{2:-}}"; }}
ask_secret_keep_default() {{ printf '%s' "${{2:-}}"; }}
normalize_optional_answer() {{ printf '%s' "${{1:-}}"; }}
random_secret() {{ printf '%s' "generated-secret"; }}
detect_tailscale() {{
  TAILSCALE_DNS_NAME=""
  TAILSCALE_IPV4=""
  TAILSCALE_TAILNET=""
}}
nextcloud_state_has_existing_data() {{ return 1; }}
read_operator_artifact_hints() {{ return 1; }}
resolve_user_home() {{ return 1; }}
collect_backup_git_answers() {{
  BACKUP_GIT_REMOTE=""
  BACKUP_GIT_DEPLOY_KEY_PATH=""
  BACKUP_GIT_KNOWN_HOSTS_FILE=""
}}
load_detected_config() {{
  ALMANAC_USER=operator-svc
  ALMANAC_HOME=/srv/operator-svc
  ALMANAC_REPO_DIR=/srv/operator-svc/almanac
  ALMANAC_PRIV_DIR=/srv/operator-svc/almanac-priv
  BACKUP_GIT_AUTHOR_NAME='Existing Backup'
  BACKUP_GIT_AUTHOR_EMAIL='operator-svc@example.test'
  NEXTCLOUD_ADMIN_USER='operator'
  NEXTCLOUD_ADMIN_PASSWORD='keep-me'
  return 0
}}
MODE=write-config
collect_install_answers
printf 'ALMANAC_USER=%s\\n' "$ALMANAC_USER"
printf 'ALMANAC_HOME=%s\\n' "$ALMANAC_HOME"
printf 'ALMANAC_REPO_DIR=%s\\n' "$ALMANAC_REPO_DIR"
printf 'ALMANAC_PRIV_DIR=%s\\n' "$ALMANAC_PRIV_DIR"
"""
    result = bash(script)
    expect(result.returncode == 0, f"collect_install_answers case failed: {result.stderr}")
    expect("ALMANAC_USER=operator-svc" in result.stdout, f"expected detected service user default, got: {result.stdout!r}")
    expect("ALMANAC_HOME=/srv/operator-svc" in result.stdout, f"expected detected home default, got: {result.stdout!r}")
    expect("ALMANAC_REPO_DIR=/srv/operator-svc/almanac" in result.stdout, f"expected detected repo default, got: {result.stdout!r}")
    expect("ALMANAC_PRIV_DIR=/srv/operator-svc/almanac-priv" in result.stdout, f"expected detected priv default, got: {result.stdout!r}")
    print("PASS test_collect_install_answers_defaults_to_detected_service_user")


def test_secret_prompt_helpers_do_not_prefix_newlines() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "ask_secret() {", "choose_mode() {")
    script = f"""
{snippet}
ask_result="$(ask_secret 'Secret' <<< 'hunter2')"
with_default_result="$(ask_secret_with_default 'Secret' 'keep-me' <<< '')"
keep_default_result="$(ask_secret_keep_default 'Secret' 'keep-me' <<< '')"
printf 'ASK=%q\\n' "$ask_result"
printf 'WITH_DEFAULT=%q\\n' "$with_default_result"
printf 'KEEP_DEFAULT=%q\\n' "$keep_default_result"
"""
    result = bash(script)
    expect(result.returncode == 0, f"secret prompt helper case failed: {result.stderr}")
    expect("ASK=hunter2" in result.stdout, f"expected ask_secret to return plain value, got: {result.stdout!r}")
    expect(
        "WITH_DEFAULT=keep-me" in result.stdout,
        f"expected ask_secret_with_default to keep plain default, got: {result.stdout!r}",
    )
    expect(
        "KEEP_DEFAULT=keep-me" in result.stdout,
        f"expected ask_secret_keep_default to keep plain default, got: {result.stdout!r}",
    )
    expect("$'\\n" not in result.stdout, f"expected no quoted leading newline escapes, got: {result.stdout!r}")
    print("PASS test_secret_prompt_helpers_do_not_prefix_newlines")


def test_collect_install_answers_randomizes_placeholder_passwords() -> None:
    text = DEPLOY_SH.read_text()
    helpers = extract(text, "random_secret() {", "write_kv() {")
    collect = extract(text, "collect_install_answers() {", "collect_remove_answers() {")
    script = f"""
{helpers}
{collect}
ask() {{ printf '%s' "${{2:-}}"; }}
ask_yes_no() {{ printf '%s' "${{2:-0}}"; }}
ask_secret() {{ printf '%s' ""; }}
ask_secret_with_default() {{ printf '%s' "${{2:-}}"; }}
ask_secret_keep_default() {{ printf '%s' "${{2:-}}"; }}
normalize_optional_answer() {{ printf '%s' "${{1:-}}"; }}
detect_tailscale() {{
  TAILSCALE_DNS_NAME=""
  TAILSCALE_IPV4=""
  TAILSCALE_TAILNET=""
}}
nextcloud_state_has_existing_data() {{ return 1; }}
read_operator_artifact_hints() {{ return 1; }}
resolve_user_home() {{ return 1; }}
collect_backup_git_answers() {{
  BACKUP_GIT_REMOTE=""
  BACKUP_GIT_DEPLOY_KEY_PATH=""
  BACKUP_GIT_KNOWN_HOSTS_FILE=""
}}
load_detected_config() {{
  ALMANAC_USER=operator-svc
  ALMANAC_HOME=/srv/operator-svc
  ALMANAC_REPO_DIR=/srv/operator-svc/almanac
  ALMANAC_PRIV_DIR=/srv/operator-svc/almanac-priv
  POSTGRES_PASSWORD='change-me'
  NEXTCLOUD_ADMIN_PASSWORD='generated-at-deploy'
  NEXTCLOUD_ADMIN_USER='operator'
  return 0
}}
random_secret() {{ printf '%s' "generated-secret"; }}
MODE=write-config
collect_install_answers
printf 'POSTGRES_PASSWORD=%s\\n' "$POSTGRES_PASSWORD"
printf 'NEXTCLOUD_ADMIN_PASSWORD=%s\\n' "$NEXTCLOUD_ADMIN_PASSWORD"
"""
    result = bash(script)
    expect(result.returncode == 0, f"placeholder-password case failed: {result.stderr}")
    expect(
        "POSTGRES_PASSWORD=generated-secret" in result.stdout,
        f"expected placeholder Postgres password to randomize, got: {result.stdout!r}",
    )
    expect(
        "NEXTCLOUD_ADMIN_PASSWORD=generated-secret" in result.stdout,
        f"expected placeholder Nextcloud admin password to randomize, got: {result.stdout!r}",
    )
    expect("change-me" not in result.stdout, f"expected placeholders to be replaced, got: {result.stdout!r}")
    print("PASS test_collect_install_answers_randomizes_placeholder_passwords")


def test_collect_install_answers_preserves_placeholder_passwords_during_stateful_repair() -> None:
    text = DEPLOY_SH.read_text()
    helpers = extract(text, "random_secret() {", "write_kv() {")
    collect = extract(text, "collect_install_answers() {", "collect_remove_answers() {")
    script = f"""
{helpers}
{collect}
ask() {{ printf '%s' "${{2:-}}"; }}
ask_yes_no() {{
  case "$1" in
    *Wipe\ existing\ Nextcloud\ state*) printf '%s' 0 ;;
    *) printf '%s' "${{2:-0}}" ;;
  esac
}}
ask_secret() {{ printf '%s' ""; }}
ask_secret_with_default() {{ printf '%s' "${{2:-}}"; }}
ask_secret_keep_default() {{ printf '%s' "${{2:-}}"; }}
normalize_optional_answer() {{ printf '%s' "${{1:-}}"; }}
detect_tailscale() {{
  TAILSCALE_DNS_NAME=""
  TAILSCALE_IPV4=""
  TAILSCALE_TAILNET=""
}}
nextcloud_state_has_existing_data() {{ return 0; }}
read_operator_artifact_hints() {{ return 1; }}
resolve_user_home() {{ return 1; }}
collect_backup_git_answers() {{
  BACKUP_GIT_REMOTE=""
  BACKUP_GIT_DEPLOY_KEY_PATH=""
  BACKUP_GIT_KNOWN_HOSTS_FILE=""
}}
load_detected_config() {{
  ALMANAC_USER=operator-svc
  ALMANAC_HOME=/srv/operator-svc
  ALMANAC_REPO_DIR=/srv/operator-svc/almanac
  ALMANAC_PRIV_DIR=/srv/operator-svc/almanac-priv
  POSTGRES_PASSWORD='change-me'
  NEXTCLOUD_ADMIN_PASSWORD='change-me'
  NEXTCLOUD_ADMIN_USER='operator'
  return 0
}}
random_secret() {{ printf '%s' "generated-secret"; }}
MODE=install
collect_install_answers
printf 'POSTGRES_PASSWORD=%s\\n' "$POSTGRES_PASSWORD"
printf 'NEXTCLOUD_ADMIN_PASSWORD=%s\\n' "$NEXTCLOUD_ADMIN_PASSWORD"
"""
    result = bash(script)
    expect(result.returncode == 0, f"stateful-repair placeholder case failed: {result.stderr}")
    expect(
        "POSTGRES_PASSWORD=change-me" in result.stdout,
        f"expected stateful repair to preserve existing Postgres password, got: {result.stdout!r}",
    )
    expect(
        "NEXTCLOUD_ADMIN_PASSWORD=change-me" in result.stdout,
        f"expected stateful repair to preserve existing Nextcloud admin password, got: {result.stdout!r}",
    )
    expect(
        "generated-secret" not in result.stdout,
        f"expected no random rotation during stateful repair, got: {result.stdout!r}",
    )
    print("PASS test_collect_install_answers_preserves_placeholder_passwords_during_stateful_repair")


def test_collect_install_answers_guides_backup_remote_setup() -> None:
    text = DEPLOY_SH.read_text()
    helpers = extract(text, "backup_github_owner_repo_from_remote() {", "collect_install_answers() {")
    collect = extract(text, "collect_install_answers() {", "collect_remove_answers() {")
    script = f"""
{helpers}
{collect}
ask() {{
  case "$1" in
    GitHub\\ owner/repo\\ for\\ almanac-priv\\ backup*) printf '%s' 'acme/almanac-priv' ;;
    *) printf '%s' "${{2:-}}" ;;
  esac
}}
ask_yes_no() {{ printf '%s' "${{2:-0}}"; }}
ask_secret() {{ printf '%s' ""; }}
ask_secret_with_default() {{ printf '%s' "${{2:-}}"; }}
ask_secret_keep_default() {{ printf '%s' "${{2:-}}"; }}
normalize_optional_answer() {{ printf '%s' "${{1:-}}"; }}
random_secret() {{ printf '%s' "generated-secret"; }}
detect_tailscale() {{
  TAILSCALE_DNS_NAME=""
  TAILSCALE_IPV4=""
  TAILSCALE_TAILNET=""
}}
nextcloud_state_has_existing_data() {{ return 1; }}
read_operator_artifact_hints() {{ return 1; }}
resolve_user_home() {{ return 1; }}
load_detected_config() {{
  ALMANAC_USER=operator-svc
  ALMANAC_HOME=/srv/operator-svc
  ALMANAC_REPO_DIR=/srv/operator-svc/almanac
  ALMANAC_PRIV_DIR=/srv/operator-svc/almanac-priv
  NEXTCLOUD_ADMIN_USER='operator'
  NEXTCLOUD_ADMIN_PASSWORD='keep-me'
  return 0
}}
MODE=write-config
collect_install_answers
printf 'BACKUP_GIT_REMOTE=%s\\n' "$BACKUP_GIT_REMOTE"
printf 'BACKUP_GIT_DEPLOY_KEY_PATH=%s\\n' "$BACKUP_GIT_DEPLOY_KEY_PATH"
printf 'BACKUP_GIT_KNOWN_HOSTS_FILE=%s\\n' "$BACKUP_GIT_KNOWN_HOSTS_FILE"
"""
    result = bash(script)
    expect(result.returncode == 0, f"backup-guidance collect_install_answers case failed: {result.stderr}")
    expect(
        "BACKUP_GIT_REMOTE=git@github.com:acme/almanac-priv.git" in result.stdout,
        f"expected GitHub SSH backup remote, got: {result.stdout!r}",
    )
    expect(
        "BACKUP_GIT_DEPLOY_KEY_PATH=/srv/operator-svc/.ssh/almanac-backup-ed25519" in result.stdout,
        f"expected default backup deploy key path, got: {result.stdout!r}",
    )
    expect(
        "BACKUP_GIT_KNOWN_HOSTS_FILE=/srv/operator-svc/.ssh/almanac-backup-known_hosts" in result.stdout,
        f"expected default backup known_hosts path, got: {result.stdout!r}",
    )
    print("PASS test_collect_install_answers_guides_backup_remote_setup")


def test_deploy_reapplies_runtime_access_after_repo_sync() -> None:
    text = DEPLOY_SH.read_text()
    install = extract(text, "run_root_install() {", "run_root_upgrade() {")
    upgrade = extract(text, "run_root_upgrade() {", "run_root_remove() {")
    enrollment_align = extract(text, "run_enrollment_align() {", "run_enrollment_reset() {")
    expect(
        "repair_active_agent_runtime_access" in install,
        "run_root_install should repair enrolled-user runtime access after syncing the shared repo",
    )
    expect(
        "chown_managed_paths" in install,
        "run_root_install should use the scoped ownership helper instead of blanket chowning private state",
    )
    expect(
        "repair_active_agent_runtime_access" in upgrade,
        "run_root_upgrade should repair enrolled-user runtime access after syncing the shared repo",
    )
    expect(
        "chown_managed_paths" in upgrade,
        "run_root_upgrade should use the scoped ownership helper instead of blanket chowning private state",
    )
    expect(
        'user sync-access "$unix_user" --agent-id "$agent_id"' in enrollment_align,
        "run_enrollment_align should reapply per-user runtime access before running user-owned services",
    )
    print("PASS test_deploy_reapplies_runtime_access_after_repo_sync")


def test_control_py_discovers_artifact_priv_dir_config() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_artifact_discovery")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        priv_dir = tmp_path / "deployed" / "almanac-priv"
        config_path = priv_dir / "config" / "almanac.env"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("ALMANAC_USER=operator-svc\n", encoding="utf-8")
        artifact_path = tmp_path / ".almanac-operator.env"
        artifact_path.write_text(
            "\n".join(
                [
                    "ALMANAC_OPERATOR_DEPLOYED_USER=operator-svc",
                    f"ALMANAC_OPERATOR_DEPLOYED_PRIV_DIR={shlex.quote(str(priv_dir))}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        old_env = os.environ.copy()
        try:
            os.environ.pop("ALMANAC_CONFIG_FILE", None)
            os.environ["ALMANAC_REPO_DIR"] = str(repo_root)
            os.environ["ALMANAC_OPERATOR_ARTIFACT_FILE"] = str(artifact_path)
            discovered = mod._discover_config_file()
        finally:
            os.environ.clear()
            os.environ.update(old_env)

        expect(discovered == config_path, f"expected control module to discover {config_path}, got {discovered!r}")
    print("PASS test_control_py_discovers_artifact_priv_dir_config")


def test_sync_public_repo_preserves_template_almanac_priv_while_excluding_top_level_private_repo() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "sync_public_repo_from_source() {", "git_head_commit() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        source_dir = tmp_path / "source"
        target_dir = tmp_path / "target"
        (source_dir / "almanac-priv").mkdir(parents=True)
        (source_dir / "almanac-priv" / "secret.txt").write_text("should-not-copy\n", encoding="utf-8")
        (source_dir / "templates" / "almanac-priv" / "vault" / "Research").mkdir(parents=True)
        (source_dir / "templates" / "almanac-priv" / "vault" / "Research" / ".vault").write_text("name: Research\n", encoding="utf-8")
        (source_dir / "bin").mkdir(parents=True)
        (source_dir / "bin" / "bootstrap-userland.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        script = f"""
{snippet}
sync_public_repo_from_source {shlex.quote(str(source_dir))} {shlex.quote(str(target_dir))}
if [[ -e {shlex.quote(str(target_dir / 'almanac-priv'))} ]]; then
  echo 'TOP_LEVEL_PRIVATE_PRESENT=1'
else
  echo 'TOP_LEVEL_PRIVATE_PRESENT=0'
fi
if [[ -f {shlex.quote(str(target_dir / 'templates' / 'almanac-priv' / 'vault' / 'Research' / '.vault'))} ]]; then
  echo 'TEMPLATE_PRIVATE_PRESENT=1'
else
  echo 'TEMPLATE_PRIVATE_PRESENT=0'
fi
"""
        result = bash(script)
        expect(result.returncode == 0, f"sync_public_repo_from_source case failed: {result.stderr}")
        expect("TOP_LEVEL_PRIVATE_PRESENT=0" in result.stdout, result.stdout)
        expect("TEMPLATE_PRIVATE_PRESENT=1" in result.stdout, result.stdout)
    print("PASS test_sync_public_repo_preserves_template_almanac_priv_while_excluding_top_level_private_repo")


def main() -> int:
    tests = [
        test_bool_env_blank_uses_default,
        test_emit_runtime_config_normalizes_curator_onboarding_flags,
        test_install_reexecs_for_unreadable_breadcrumb_config,
        test_install_does_not_reexec_for_readable_breadcrumb_config,
        test_write_operator_artifact_falls_back_to_discovered_config,
        test_discover_existing_config_uses_artifact_priv_dir_hint,
        test_collect_install_answers_defaults_to_detected_service_user,
        test_secret_prompt_helpers_do_not_prefix_newlines,
        test_collect_install_answers_randomizes_placeholder_passwords,
        test_collect_install_answers_preserves_placeholder_passwords_during_stateful_repair,
        test_collect_install_answers_guides_backup_remote_setup,
        test_deploy_reapplies_runtime_access_after_repo_sync,
        test_control_py_discovers_artifact_priv_dir_config,
        test_sync_public_repo_preserves_template_almanac_priv_while_excluding_top_level_private_repo,
    ]
    for test in tests:
        test()
    print(f"PASS all {len(tests)} deploy regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
