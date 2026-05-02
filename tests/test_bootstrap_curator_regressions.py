#!/usr/bin/env python3
from __future__ import annotations

import shlex
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BOOTSTRAP_CURATOR = REPO / "bin" / "bootstrap-curator.sh"


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


def test_fresh_install_prompts_for_channels_even_with_tui_only_default() -> None:
    text = BOOTSTRAP_CURATOR.read_text()
    snippet = extract(text, "choose_channels_csv() {", "print_gateway_setup_guidance() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        manifest_path = tmp_path / "curator-manifest.json"
        script = f"""
ARCLINK_CURATOR_CHANNELS=tui-only
ARCLINK_CURATOR_MANIFEST={shlex.quote(str(manifest_path))}
ARCLINK_CURATOR_FORCE_CHANNEL_RECONFIGURE=0
ARCLINK_CURATOR_SKIP_HERMES_SETUP=0
ARCLINK_CURATOR_SKIP_GATEWAY_SETUP=0
ask_default() {{
  case "$1" in
    *Discord*) printf '%s' yes ;;
    *Telegram*) printf '%s' no ;;
    *) printf '%s' "${{2:-}}" ;;
  esac
}}
confirm_default() {{
  echo "confirm_default should not run for a fresh install" >&2
  return 1
}}
{snippet}
result="$(choose_channels_csv)"
printf 'RESULT=%s\\n' "$result"
"""
        result = bash(script)
        expect(result.returncode == 0, f"fresh-install channel prompt case failed: {result.stderr}")
        expect(
            "RESULT=tui-only,discord" in result.stdout,
            f"expected fresh install to prompt and enable discord, got: {result.stdout!r}",
        )
    print("PASS test_fresh_install_prompts_for_channels_even_with_tui_only_default")


def test_existing_channels_reuse_noninteractive_without_prompt() -> None:
    text = BOOTSTRAP_CURATOR.read_text()
    snippet = extract(text, "choose_channels_csv() {", "print_gateway_setup_guidance() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        manifest_path = tmp_path / "curator-manifest.json"
        manifest_path.write_text("{}", encoding="utf-8")
        prompt_log = tmp_path / "prompt.log"
        script = f"""
ARCLINK_CURATOR_CHANNELS=tui-only,discord
ARCLINK_CURATOR_MANIFEST={shlex.quote(str(manifest_path))}
ARCLINK_CURATOR_FORCE_CHANNEL_RECONFIGURE=0
ARCLINK_CURATOR_SKIP_HERMES_SETUP=0
ARCLINK_CURATOR_SKIP_GATEWAY_SETUP=0
PROMPT_LOG={shlex.quote(str(prompt_log))}
ask_default() {{
  printf '%s\\n' "$1" >> "$PROMPT_LOG"
  printf '%s' no
}}
confirm_default() {{
  printf '%s\\n' "$1" >> "$PROMPT_LOG"
  return 0
}}
{snippet}
result="$(choose_channels_csv)"
printf 'RESULT=%s\\n' "$result"
if [[ -f "$PROMPT_LOG" ]]; then
  printf 'PROMPTS_BEGIN\\n'
  cat "$PROMPT_LOG"
  printf 'PROMPTS_END\\n'
fi
"""
        result = bash(script)
        expect(result.returncode == 0, f"existing-channel reuse case failed: {result.stderr}")
        expect(
            "RESULT=tui-only,discord" in result.stdout,
            f"expected existing channels to be reused, got: {result.stdout!r}",
        )
        expect(
            "PROMPTS_BEGIN" not in result.stdout,
            f"expected noninteractive reuse without prompts, got: {result.stdout!r}",
        )
    print("PASS test_existing_channels_reuse_noninteractive_without_prompt")


def test_notify_channel_defaults_to_only_selected_platform_without_reusing_tui_only() -> None:
    text = BOOTSTRAP_CURATOR.read_text()
    helpers = extract(text, "default_notify_platform_for_channels() {", "print_gateway_setup_guidance() {")
    snippet = extract(text, "resolve_notify_channel() {", "set_config_value() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        prompt_log = tmp_path / "prompt.log"
        script = f"""
PROMPT_LOG={shlex.quote(str(prompt_log))}
OPERATOR_NOTIFY_CHANNEL_PLATFORM=tui-only
OPERATOR_NOTIFY_CHANNEL_ID=
ARCLINK_CURATOR_FORCE_CHANNEL_RECONFIGURE=0
ARCLINK_CURATOR_SKIP_HERMES_SETUP=0
ARCLINK_CURATOR_SKIP_GATEWAY_SETUP=0
ARCLINK_CURATOR_NOTIFY_PLATFORM=
ARCLINK_CURATOR_NOTIFY_CHANNEL_ID=
ask_default() {{
  printf '%s\\n' "$1 [$2]" >> "$PROMPT_LOG"
  printf '%s' "${{2:-}}"
}}
confirm_default() {{
  printf 'confirm:%s\\n' "$1" >> "$PROMPT_LOG"
  return 0
}}
{helpers}
{snippet}
result=()
while IFS= read -r line; do
  result+=("$line")
done < <(resolve_notify_channel "tui-only,discord")
printf 'PLATFORM=%s\\n' "${{result[0]:-}}"
printf 'CHANNEL=%s\\n' "${{result[1]:-}}"
printf 'PROMPTS_BEGIN\\n'
cat "$PROMPT_LOG"
printf 'PROMPTS_END\\n'
"""
        result = bash(script)
        expect(result.returncode == 0, f"notify default case failed: {result.stderr}")
        expect("PLATFORM=discord" in result.stdout, f"expected discord default, got: {result.stdout!r}")
        prompts = result.stdout.split("PROMPTS_BEGIN\n", 1)[1].split("\nPROMPTS_END", 1)[0]
        expect(
            "Reuse existing operator notification channel" not in prompts,
            f"did not expect tui-only reuse prompt, got: {prompts!r}",
        )
    print("PASS test_notify_channel_defaults_to_only_selected_platform_without_reusing_tui_only")


def test_notify_channel_guidance_clarifies_platform_specific_ids() -> None:
    text = BOOTSTRAP_CURATOR.read_text()
    helpers = extract(text, "describe_notify_channel_prompt() {", "describe_operator_channel() {")
    script = f"""
{helpers}
printf 'DISCORD_PROMPT=%s\\n' "$(describe_notify_channel_prompt discord)"
printf 'TELEGRAM_PROMPT=%s\\n' "$(describe_notify_channel_prompt telegram)"
printf 'DISCORD_GUIDANCE_BEGIN\\n'
print_notify_channel_guidance discord
printf 'DISCORD_GUIDANCE_END\\n'
printf 'TELEGRAM_GUIDANCE_BEGIN\\n'
print_notify_channel_guidance telegram
printf 'TELEGRAM_GUIDANCE_END\\n'
"""
    result = bash(script)
    expect(result.returncode == 0, f"notify guidance case failed: {result.stderr}")
    combined_output = result.stdout + result.stderr
    expect(
        "DISCORD_PROMPT=Operator notification Discord channel ID or webhook URL" in result.stdout,
        f"expected Discord-specific prompt label, got: {result.stdout!r}",
    )
    expect(
        "TELEGRAM_PROMPT=Operator notification Telegram chat ID" in result.stdout,
        f"expected Telegram-specific prompt label, got: {result.stdout!r}",
    )
    expect("not a user ID" in combined_output, f"expected Discord guidance to reject user IDs, got: {combined_output!r}")
    expect("message.chat.id" in combined_output, f"expected Telegram guidance to mention message.chat.id, got: {combined_output!r}")
    print("PASS test_notify_channel_guidance_clarifies_platform_specific_ids")


def test_ensure_curator_hermes_reuses_healthy_runtime_before_refreshing() -> None:
    text = BOOTSTRAP_CURATOR.read_text()
    snippet = extract(text, "ensure_curator_hermes() {", "main() {")
    script = f"""
RUNTIME_DIR=/srv/arclink/runtime
runtime_python_has_pip() {{ return 0; }}
shared_runtime_python_is_share_safe() {{ return 0; }}
ensure_shared_hermes_runtime() {{
  echo "should not refresh"
  return 99
}}
mkdir() {{ command mkdir "$@"; }}
{snippet}
mkdir -p /tmp/arclink-bootstrap-curator-test/hermes-venv/bin
RUNTIME_DIR=/tmp/arclink-bootstrap-curator-test
touch "$RUNTIME_DIR/hermes-venv/bin/hermes" "$RUNTIME_DIR/hermes-venv/bin/python3"
chmod +x "$RUNTIME_DIR/hermes-venv/bin/hermes" "$RUNTIME_DIR/hermes-venv/bin/python3"
ensure_curator_hermes
printf 'RESULT=ok\\n'
"""
    result = bash(script)
    expect(result.returncode == 0, f"ensure_curator_hermes reuse case failed: {result.stderr}")
    expect("RESULT=ok" in result.stdout, f"expected healthy runtime reuse, got: {result.stdout!r}")
    expect("should not refresh" not in result.stdout, f"did not expect shared runtime refresh, got: {result.stdout!r}")
    print("PASS test_ensure_curator_hermes_reuses_healthy_runtime_before_refreshing")


def test_curator_defaults_wires_vault_agents_skills_without_exported_env() -> None:
    text = BOOTSTRAP_CURATOR.read_text()
    snippet = extract(text, "ensure_hermes_agent_defaults() {", "ensure_curator_hermes() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        hermes_home = tmp_path / "hermes-home"
        vault_dir = tmp_path / "vault"
        skill_root = vault_dir / "Agents_Skills" / "ralphie" / "skills"
        skill_file = skill_root / "software-development" / "ralphie-orchestration" / "SKILL.md"
        skill_file.parent.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(
            "---\n"
            "name: ralphie-orchestration\n"
            "description: Test shared skill.\n"
            "---\n"
            "# Ralphie\n",
            encoding="utf-8",
        )
        script = f"""
set -euo pipefail
VAULT_DIR={shlex.quote(str(vault_dir))}
unset ARCLINK_AGENT_VAULT_DIR
unset ARCLINK_SHARED_SKILLS_DIR
RUNTIME_DIR=/tmp/unused-runtime
{snippet}
ensure_hermes_agent_defaults {shlex.quote(str(hermes_home))} python3
cat {shlex.quote(str(hermes_home / "config.yaml"))}
"""
        result = bash(script)
        expect(result.returncode == 0, f"curator shared-skill env case failed: {result.stderr}")
        expect("external_dirs:" in result.stdout, f"expected external_dirs in config, got: {result.stdout!r}")
        expect(str(skill_root) in result.stdout, f"expected shared skill root in config, got: {result.stdout!r}")
    print("PASS test_curator_defaults_wires_vault_agents_skills_without_exported_env")


def test_main_runs_curator_defaults_when_setup_is_skipped() -> None:
    text = BOOTSTRAP_CURATOR.read_text()
    snippet = extract(text, "main() {", '\nmain "$@"')
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        bootstrap_dir = tmp_path / "bootstrap"
        (bootstrap_dir / "bin").mkdir(parents=True)
        (bootstrap_dir / "python").mkdir()
        for name in ("sync-hermes-bundled-skills.sh", "install-arclink-skills.sh", "install-arclink-plugins.sh", "migrate-hermes-config.sh"):
            script_path = bootstrap_dir / "bin" / name
            script_path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            script_path.chmod(0o755)
        ctl_path = bootstrap_dir / "python" / "arclink_ctl.py"
        ctl_path.write_text("import sys\nraise SystemExit(0)\n", encoding="utf-8")

        script = f"""
set -euo pipefail
BOOTSTRAP_DIR={shlex.quote(str(bootstrap_dir))}
RUNTIME_DIR={shlex.quote(str(tmp_path / "runtime"))}
ARCLINK_USER=arclink
ARCLINK_CURATOR_HERMES_HOME={shlex.quote(str(tmp_path / "hermes-home"))}
ARCLINK_CURATOR_SKIP_HERMES_SETUP=1
ARCLINK_CURATOR_SKIP_GATEWAY_SETUP=1
ARCLINK_CURATOR_FORCE_HERMES_SETUP=0
ARCLINK_CURATOR_FORCE_GATEWAY_SETUP=0
ARCLINK_MODEL_PRESET_CODEX=openai-codex:gpt-5.5
ARCLINK_MODEL_PRESET_OPUS=anthropic:claude-opus-4-7
ARCLINK_MODEL_PRESET_CHUTES=chutes:moonshotai/Kimi-K2.6-TEE
OPERATOR_NOTIFY_CHANNEL_PLATFORM=tui-only
OPERATOR_NOTIFY_CHANNEL_ID=
OPERATOR_GENERAL_CHANNEL_PLATFORM=
OPERATOR_GENERAL_CHANNEL_ID=
defaults_calls=0
require_real_layout() {{ :; }}
ensure_layout() {{ :; }}
ensure_curator_hermes() {{ :; }}
choose_model_preset() {{ printf '%s\\n' codex; }}
choose_channels_csv() {{ printf '%s\\n' tui-only; }}
resolve_notify_channel() {{ printf '%s\\n\\n' tui-only; }}
configure_operator_notify_channel() {{ printf '%s\\n\\n' "${{1:-tui-only}}"; }}
set_config_value() {{ :; }}
probe_hermes_state_json() {{ return 1; }}
ensure_hermes_agent_defaults() {{ defaults_calls=$((defaults_calls + 1)); }}
sync_org_provider_from_curator_codex() {{ :; }}
set_user_systemd_bus_env() {{ return 1; }}
describe_operator_channel() {{ printf '%s\\n' "${{1:-tui-only}}"; }}
{snippet}
main
printf 'DEFAULTS_CALLS=%s\\n' "$defaults_calls"
"""
        result = bash(script)
        expect(result.returncode == 0, f"curator skipped-setup defaults case failed: {result.stderr}")
        expect("DEFAULTS_CALLS=1" in result.stdout, f"expected defaults repair during skipped setup, got: {result.stdout!r}")
    print("PASS test_main_runs_curator_defaults_when_setup_is_skipped")


def test_probe_hermes_state_does_not_override_selected_channels_without_gateway_setup() -> None:
    text = BOOTSTRAP_CURATOR.read_text()
    snippet = extract(text, '  hermes_state_file="$(mktemp)"', '  channels_json="$(')
    script = f"""
test_case() {{
  model_preset=codex
  model_string=openai:codex
  channels_csv=tui-only,discord
  ran_model_setup=0
  ran_gateway_setup=0
  hermes_state_file=
  ARCLINK_CURATOR_HERMES_HOME=/tmp/hermes-home
  hermes_bin=/tmp/hermes
  probe_hermes_state_json() {{
    printf '%s' '{{"model_preset":"custom","model_string":"stale:model","channels_csv":"tui-only"}}'
  }}
{snippet}
  printf 'CHANNELS=%s\\n' "$channels_csv"
  printf 'MODEL=%s\\n' "$model_preset"
  printf 'MODEL_STRING=%s\\n' "$model_string"
}}
test_case
"""
    result = bash(script)
    expect(result.returncode == 0, f"probe-hermes-state override case failed: {result.stderr}")
    expect("CHANNELS=tui-only,discord" in result.stdout, f"expected chosen channels to win, got: {result.stdout!r}")
    expect("MODEL=codex" in result.stdout, f"expected model preset to stay local when setup was skipped, got: {result.stdout!r}")
    expect(
        "MODEL_STRING=openai:codex" in result.stdout,
        f"expected model string to stay local when setup was skipped, got: {result.stdout!r}",
    )
    print("PASS test_probe_hermes_state_does_not_override_selected_channels_without_gateway_setup")


def test_run_curator_gateway_setup_treats_root_restart_as_soft_success() -> None:
    text = BOOTSTRAP_CURATOR.read_text()
    helpers = extract(text, "channels_csv_covers_requested() {", "resolve_notify_channel() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fake_hermes = tmp_path / "fake-hermes"
        fake_hermes.write_text(
            """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "gateway" && "${2:-}" == "setup" ]]; then
  exit 1
fi
if [[ "${1:-}" == "dump" ]]; then
  cat <<'EOF'
model: gpt-5.4
provider: openai-codex
platforms: discord
EOF
  exit 0
fi
exit 1
""",
            encoding="utf-8",
        )
        fake_hermes.chmod(0o755)
        script = f"""
print_gateway_setup_guidance() {{
  :
}}
{helpers}
if run_curator_gateway_setup "tui-only,discord" {shlex.quote(str(fake_hermes))} /tmp/hermes-home; then
  echo "RESULT=success"
else
  echo "RESULT=failure"
fi
"""
        result = bash(script)
        expect(result.returncode == 0, f"gateway soft-success case failed: {result.stderr}")
        expect("RESULT=success" in result.stdout, f"expected soft success, got: {result.stdout!r}")
        expect(
            "ArcLink will restart the configured gateway service below" in result.stderr,
            f"expected root-restart soft-success warning, got: {result.stderr!r}",
        )
    print("PASS test_run_curator_gateway_setup_treats_root_restart_as_soft_success")


def test_operator_notify_falls_back_to_tui_only_when_target_verification_fails() -> None:
    text = BOOTSTRAP_CURATOR.read_text()
    helpers = extract(text, "channels_csv_covers_requested() {", "resolve_notify_channel() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        bootstrap_dir = tmp_path / "bootstrap"
        ctl_path = bootstrap_dir / "bin" / "arclink-ctl"
        log_path = tmp_path / "arclink-ctl.log"
        ctl_path.parent.mkdir(parents=True, exist_ok=True)
        ctl_path.write_text(
            f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> {shlex.quote(str(log_path))}
if [[ "$*" == *"--platform discord"* ]]; then
  echo "channel test ping failed (discord http 404: {{\\"message\\": \\"Unknown Channel\\", \\"code\\": 10003}})" >&2
  exit 1
fi
exit 0
""",
            encoding="utf-8",
        )
        ctl_path.chmod(0o755)
        script = f"""
BOOTSTRAP_DIR={shlex.quote(str(bootstrap_dir))}
{helpers}
configured=()
while IFS= read -r line; do
  configured+=("$line")
done < <(configure_operator_notify_channel "discord" "555026921809772555")
printf 'PLATFORM=%s\\n' "${{configured[0]:-}}"
printf 'CHANNEL=%s\\n' "${{configured[1]:-}}"
printf 'LOG_BEGIN\\n'
cat {shlex.quote(str(log_path))}
printf 'LOG_END\\n'
"""
        result = bash(script)
        expect(result.returncode == 0, f"operator notify fallback case failed: {result.stderr}")
        expect("PLATFORM=tui-only" in result.stdout, f"expected tui-only fallback, got: {result.stdout!r}")
        expect("CHANNEL=" in result.stdout, f"expected blank channel id after fallback, got: {result.stdout!r}")
        log = result.stdout.split("LOG_BEGIN\n", 1)[1].split("\nLOG_END", 1)[0]
        expect("--platform discord --channel-id 555026921809772555" in log, f"expected initial discord verify call, got: {log!r}")
        expect("--platform tui-only --channel-id " in log, f"expected tui-only fallback call, got: {log!r}")
        expect(
            "Operator notification target verification failed" in result.stderr,
            f"expected operator fallback warning, got: {result.stderr!r}",
        )
    print("PASS test_operator_notify_falls_back_to_tui_only_when_target_verification_fails")


def test_disable_curator_native_gateway_resets_failed_state() -> None:
    text = BOOTSTRAP_CURATOR.read_text()
    snippet = extract(text, "disable_curator_native_gateway_unit() {", "main() {")
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "systemctl.log"
        script = f"""
set -euo pipefail
SYSTEMCTL_LOG={shlex.quote(str(log_path))}
curator_native_gateway_unit_name() {{
  printf '%s\\n' "hermes-gateway-curatorhash.service"
}}
systemctl() {{
  printf '%s\\n' "$*" >> "$SYSTEMCTL_LOG"
}}
{snippet}
disable_curator_native_gateway_unit
cat "$SYSTEMCTL_LOG"
"""
        result = bash(script)
        expect(result.returncode == 0, f"native gateway reset case failed: {result.stderr}")
        expect(
            "--user disable --now hermes-gateway-curatorhash.service" in result.stdout,
            f"expected disable command, got: {result.stdout!r}",
        )
        expect(
            "--user reset-failed hermes-gateway-curatorhash.service" in result.stdout,
            f"expected reset-failed command, got: {result.stdout!r}",
        )
    print("PASS test_disable_curator_native_gateway_resets_failed_state")


def test_hermes_setup_runs_with_utf8_environment() -> None:
    text = BOOTSTRAP_CURATOR.read_text()
    expect("run_hermes_utf8()" in text, "expected shared UTF-8 Hermes wrapper")
    expect('LANG="${ARCLINK_UTF8_LOCALE:-C.UTF-8}"' in text, "expected Hermes wrapper to force UTF-8 LANG")
    expect('LC_ALL="${ARCLINK_UTF8_LOCALE:-C.UTF-8}"' in text, "expected Hermes wrapper to force UTF-8 LC_ALL")
    expect('PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"' in text, "expected Hermes wrapper to force UTF-8 Python I/O")
    expect(
        'run_hermes_utf8 "$ARCLINK_CURATOR_HERMES_HOME" "$hermes_bin" setup model' in text,
        "expected model setup to use UTF-8 wrapper",
    )
    expect(
        'run_hermes_utf8 "$hermes_home" "$hermes_bin" gateway setup' in text,
        "expected gateway setup to use UTF-8 wrapper",
    )
    expect(
        'run_hermes_utf8 "$hermes_home" "$hermes_bin" dump' in text,
        "expected Hermes state probe to use UTF-8 wrapper",
    )
    print("PASS test_hermes_setup_runs_with_utf8_environment")


def main() -> int:
    tests = [
        test_fresh_install_prompts_for_channels_even_with_tui_only_default,
        test_existing_channels_reuse_noninteractive_without_prompt,
        test_notify_channel_defaults_to_only_selected_platform_without_reusing_tui_only,
        test_notify_channel_guidance_clarifies_platform_specific_ids,
        test_ensure_curator_hermes_reuses_healthy_runtime_before_refreshing,
        test_curator_defaults_wires_vault_agents_skills_without_exported_env,
        test_main_runs_curator_defaults_when_setup_is_skipped,
        test_probe_hermes_state_does_not_override_selected_channels_without_gateway_setup,
        test_run_curator_gateway_setup_treats_root_restart_as_soft_success,
        test_operator_notify_falls_back_to_tui_only_when_target_verification_fails,
        test_disable_curator_native_gateway_resets_failed_state,
        test_hermes_setup_runs_with_utf8_environment,
    ]
    for test in tests:
        test()
    print(f"PASS all {len(tests)} bootstrap-curator regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
