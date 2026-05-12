#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

import arclink_secrets_regex as secrets_regex


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_secret_detection_covers_provider_token_families() -> None:
    samples = [
        "OPENAI_API_KEY=sk-proj-" + "A" * 32,
        "ANTHROPIC_API_KEY=sk-ant-" + "B" * 32,
        "AWS_ACCESS_KEY_ID=AKIA" + "C" * 16,
        "CHUTES_API_KEY=cpk_test_secret_value_12345",
        "DISCORD_BOT_TOKEN=discord-bot-token-plaintext",
        "GITLAB_TOKEN=glpat-" + "D" * 24,
        "TELEGRAM_BOT_TOKEN=123456:" + "e" * 24,
        "JWT=eyJ" + "a" * 12 + ".eyJ" + "b" * 12 + "." + "c" * 16,
        "-----BEGIN PRIVATE KEY-----\nabc123\n-----END PRIVATE KEY-----",
    ]
    for sample in samples:
        expect(secrets_regex.contains_secret_material(sample), sample)
        redacted = secrets_regex.redact_secret_material(sample)
        expect("[REDACTED]" in redacted, redacted)
        expect("sk-proj-" not in redacted and "sk-ant-" not in redacted, redacted)
        expect("AKIA" not in redacted and "cpk_test_secret" not in redacted, redacted)
        expect("glpat-" not in redacted and "BEGIN PRIVATE KEY" not in redacted, redacted)
    print("PASS test_secret_detection_covers_provider_token_families")


def test_safe_secret_reference_exceptions_and_path_checks() -> None:
    expect(secrets_regex.is_secret_ref("secret://arclink/chutes/dep_1"), "secret ref rejected")
    expect(secrets_regex.is_run_secret_path("/run/secrets/chutes_api_key"), "run secret path rejected")
    expect(not secrets_regex.contains_secret_material("secret://arclink/chutes/dep_1"), "secret ref detected")
    expect(not secrets_regex.contains_secret_material("/run/secrets/chutes_api_key"), "run secret path detected")
    expect(secrets_regex.path_requires_secret_ref("$.secret_refs.chutes_api_key"), "secret_refs key not detected")
    expect(secrets_regex.path_requires_secret_ref("$.environment.TELEGRAM_BOT_TOKEN_REF"), "token ref key not detected")
    expect(not secrets_regex.path_requires_secret_ref("$.integrations.notion.callback_url"), "webhook callback overmatched")
    expect(
        secrets_regex.path_allows_compose_secret_source("$.compose.secrets.chutes_api_key.source", "chutes_api_key"),
        "compose secret source not allowed",
    )
    print("PASS test_safe_secret_reference_exceptions_and_path_checks")


def test_redact_then_truncate_redacts_before_limit() -> None:
    raw = "api_key=sk-proj-" + "A" * 80 + " trailing public context"
    redacted = secrets_regex.redact_then_truncate(raw, limit=18)
    expect("sk-proj-" not in redacted, redacted)
    expect(redacted.startswith("api_key=[REDACTED"), redacted)
    tail = secrets_regex.redact_then_truncate("prefix " + raw, limit=24, tail=True)
    expect("sk-proj-" not in tail and "A" * 8 not in tail, tail)
    print("PASS test_redact_then_truncate_redacts_before_limit")


def main() -> int:
    test_secret_detection_covers_provider_token_families()
    test_safe_secret_reference_exceptions_and_path_checks()
    test_redact_then_truncate_redacts_before_limit()
    print("PASS all 3 ArcLink secret regex tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
