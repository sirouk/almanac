#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_model_provider_yaml_defaults_are_authoritative() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    from almanac_model_providers import provider_default_model, provider_recommended_models, resolve_preset_target

    expect(provider_default_model("chutes", REPO) == "moonshotai/Kimi-K2.6-TEE", "bad chutes default")
    expect(provider_default_model("opus", REPO) == "claude-opus-4-7", "bad opus default")
    expect(provider_default_model("codex", REPO) == "gpt-5.5", "bad codex default")
    expect(resolve_preset_target("chutes", "chutes:model-router", REPO) == "chutes:moonshotai/Kimi-K2.6-TEE", "legacy chutes default should migrate")
    expect(resolve_preset_target("opus", "anthropic:claude-opus", REPO) == "anthropic:claude-opus-4-7", "legacy opus alias should migrate")
    expect(resolve_preset_target("codex", "openai:codex", REPO) == "openai-codex:gpt-5.5", "legacy codex alias should migrate")
    expect(resolve_preset_target("codex", "openai-codex:gpt-5.4", REPO) == "openai-codex:gpt-5.4", "exact codex target should stay exact")
    expect(provider_recommended_models("chutes", REPO)[0] == "moonshotai/Kimi-K2.6-TEE", "chutes suggestions should start with current default")
    print("PASS test_model_provider_yaml_defaults_are_authoritative")


def test_shell_common_reads_model_provider_defaults() -> None:
    result = subprocess.run(
        [
            "bash",
            "-lc",
            "source bin/common.sh; printf '%s\\n' \"$ALMANAC_MODEL_PRESET_CODEX\" \"$ALMANAC_MODEL_PRESET_OPUS\" \"$ALMANAC_MODEL_PRESET_CHUTES\"",
        ],
        cwd=REPO,
        env={
            **os.environ,
            "ALMANAC_MODEL_PRESET_CODEX": "openai:codex",
            "ALMANAC_MODEL_PRESET_OPUS": "anthropic:claude-opus",
            "ALMANAC_MODEL_PRESET_CHUTES": "chutes:model-router",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    expect(result.returncode == 0, result.stderr)
    lines = result.stdout.splitlines()
    expect(lines == ["openai-codex:gpt-5.5", "anthropic:claude-opus-4-7", "chutes:moonshotai/Kimi-K2.6-TEE"], str(lines))
    print("PASS test_shell_common_reads_model_provider_defaults")


def main() -> int:
    test_model_provider_yaml_defaults_are_authoritative()
    test_shell_common_reads_model_provider_defaults()
    print("PASS all 2 model provider tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
