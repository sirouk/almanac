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


def main() -> int:
    tests = [
        test_fresh_install_prompts_for_channels_even_with_tui_only_default,
        test_existing_channels_reuse_noninteractive_without_prompt,
    ]
    for test in tests:
        test()
    print(f"PASS all {len(tests)} bootstrap-curator regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
