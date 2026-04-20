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
ALMANAC_CURATOR_CHANNELS=tui-only
ALMANAC_CURATOR_MANIFEST={shlex.quote(str(manifest_path))}
ALMANAC_CURATOR_FORCE_CHANNEL_RECONFIGURE=0
ALMANAC_CURATOR_SKIP_HERMES_SETUP=0
ALMANAC_CURATOR_SKIP_GATEWAY_SETUP=0
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
ALMANAC_CURATOR_CHANNELS=tui-only,discord
ALMANAC_CURATOR_MANIFEST={shlex.quote(str(manifest_path))}
ALMANAC_CURATOR_FORCE_CHANNEL_RECONFIGURE=0
ALMANAC_CURATOR_SKIP_HERMES_SETUP=0
ALMANAC_CURATOR_SKIP_GATEWAY_SETUP=0
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
ALMANAC_CURATOR_FORCE_CHANNEL_RECONFIGURE=0
ALMANAC_CURATOR_SKIP_HERMES_SETUP=0
ALMANAC_CURATOR_SKIP_GATEWAY_SETUP=0
ALMANAC_CURATOR_NOTIFY_PLATFORM=
ALMANAC_CURATOR_NOTIFY_CHANNEL_ID=
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
mapfile -t result < <(resolve_notify_channel "tui-only,discord")
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
  ALMANAC_CURATOR_HERMES_HOME=/tmp/hermes-home
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
            "could not restart the service itself without root" in result.stderr,
            f"expected root-restart soft-success warning, got: {result.stderr!r}",
        )
    print("PASS test_run_curator_gateway_setup_treats_root_restart_as_soft_success")


def test_operator_notify_falls_back_to_tui_only_when_target_verification_fails() -> None:
    text = BOOTSTRAP_CURATOR.read_text()
    helpers = extract(text, "channels_csv_covers_requested() {", "resolve_notify_channel() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        bootstrap_dir = tmp_path / "bootstrap"
        ctl_path = bootstrap_dir / "bin" / "almanac-ctl"
        log_path = tmp_path / "almanac-ctl.log"
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
mapfile -t configured < <(configure_operator_notify_channel "discord" "555026921809772555")
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


def main() -> int:
    tests = [
        test_fresh_install_prompts_for_channels_even_with_tui_only_default,
        test_existing_channels_reuse_noninteractive_without_prompt,
        test_notify_channel_defaults_to_only_selected_platform_without_reusing_tui_only,
        test_probe_hermes_state_does_not_override_selected_channels_without_gateway_setup,
        test_run_curator_gateway_setup_treats_root_restart_as_soft_success,
        test_operator_notify_falls_back_to_tui_only_when_target_verification_fails,
    ]
    for test in tests:
        test()
    print(f"PASS all {len(tests)} bootstrap-curator regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
