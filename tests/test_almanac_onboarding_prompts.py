#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import pwd
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
CONTROL_PY = PYTHON_DIR / "almanac_control.py"
ONBOARDING_PY = PYTHON_DIR / "almanac_onboarding_flow.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_config(path: Path, values: dict[str, str]) -> None:
    lines = [f"{key}={json.dumps(value)}" for key, value in values.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_discord_prompt_and_operator_review_reflect_primary_control_channel() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_onboarding_prompt_test")
    onboarding = load_module(ONBOARDING_PY, "almanac_onboarding_prompt_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(
            config_path,
            {
                "ALMANAC_USER": "almanac",
                "ALMANAC_HOME": str(root / "home-almanac"),
                "ALMANAC_REPO_DIR": str(REPO),
                "ALMANAC_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(root / "state"),
                "RUNTIME_DIR": str(root / "state" / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ALMANAC_DB_PATH": str(root / "state" / "almanac-control.sqlite3"),
                "ALMANAC_AGENTS_STATE_DIR": str(root / "state" / "agents"),
                "ALMANAC_CURATOR_DIR": str(root / "state" / "curator"),
                "ALMANAC_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
                "ALMANAC_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
                "ALMANAC_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
                "ALMANAC_RELEASE_STATE_FILE": str(root / "state" / "almanac-release.json"),
                "ALMANAC_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ALMANAC_MCP_HOST": "127.0.0.1",
                "ALMANAC_MCP_PORT": "8282",
                "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "discord",
                "OPERATOR_NOTIFY_CHANNEL_ID": "123456789012345678",
                "ALMANAC_CURATOR_CHANNELS": "tui-only",
            },
        )

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            expect(cfg.curator_discord_onboarding_enabled is True, f"expected discord onboarding to default on, got {cfg}")

            opening = onboarding.session_prompt(
                cfg,
                {
                    "state": "awaiting-name",
                    "answers": {},
                },
            )
            expect("keep us on the rails" in opening, opening)

            purpose_prompt = onboarding.session_prompt(
                cfg,
                {
                    "state": "awaiting-purpose",
                    "answers": {},
                },
            )
            expect("practice or get done" in purpose_prompt, purpose_prompt)

            unix_prompt = onboarding.session_prompt(
                cfg,
                {
                    "state": "awaiting-unix-user",
                    "answers": {},
                },
            )
            expect("shared host" in unix_prompt.lower(), unix_prompt)
            expect("unix account" in unix_prompt.lower(), unix_prompt)

            prompt = onboarding.session_prompt(
                cfg,
                {
                    "state": "awaiting-bot-token",
                    "answers": {
                        "bot_platform": "discord",
                        "preferred_bot_name": "KorBon",
                    },
                },
            )
            expect("Open Installation and copy the install link" in prompt, prompt)
            expect("share a server" in prompt or "Add App" in prompt, prompt)

            notion_access_prompt = onboarding.session_prompt(
                cfg,
                {
                    "state": "awaiting-notion-access",
                    "answers": {},
                },
            )
            expect("shared Almanac page" in notion_access_prompt, notion_access_prompt)
            expect("ready" in notion_access_prompt.lower(), notion_access_prompt)
            expect("skip" in notion_access_prompt.lower(), notion_access_prompt)

            notion_email_prompt = onboarding.session_prompt(
                cfg,
                {
                    "state": "awaiting-notion-email",
                    "answers": {},
                },
            )
            expect("Notion email" in notion_email_prompt or "Notion" in notion_email_prompt, notion_email_prompt)
            expect("skip" in notion_email_prompt.lower(), notion_email_prompt)

            notion_verify_prompt = onboarding.session_prompt(
                cfg,
                {
                    "state": "awaiting-notion-verification",
                    "answers": {
                        "notion_claim_email": "chris@example.com",
                        "notion_claim_url": "https://www.notion.so/claim",
                        "notion_claim_expires_at": "2026-04-21T00:00:00+00:00",
                    },
                },
            )
            expect("https://www.notion.so/claim" in notion_verify_prompt, notion_verify_prompt)
            expect("chris@example.com" in notion_verify_prompt, notion_verify_prompt)
            expect("Request access" in notion_verify_prompt, notion_verify_prompt)

            provisioning_error_prompt = onboarding.session_prompt(
                cfg,
                {
                    "state": "provision-pending",
                    "answers": {},
                    "provision_error": "gateway startup failed",
                },
            )
            expect("gateway startup failed" in provisioning_error_prompt, provisioning_error_prompt)
            expect("/status" in provisioning_error_prompt, provisioning_error_prompt)

            review = onboarding._operator_review_message(  # noqa: SLF001
                cfg,
                {
                    "session_id": "onb_test",
                    "platform": "discord",
                    "sender_id": "42",
                    "sender_username": "operator-user",
                    "sender_display_name": "Operator User",
                    "answers": {
                        "full_name": "Operator User",
                        "unix_user": "operatoruser",
                        "purpose": "Keep the org moving",
                        "bot_platform": "discord",
                        "preferred_bot_name": "KorBon",
                        "model_preset": "codex",
                    },
                },
            )
            expect("Discord approve: /approve onb_test" in review, review)
            expect("configured primary Discord operator channel" in review, review)
            print("PASS test_discord_prompt_and_operator_review_reflect_primary_control_channel")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_onboarding_intake_asks_purpose_before_unix_and_skips_platform_question() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_onboarding_order_test")
    onboarding = load_module(ONBOARDING_PY, "almanac_onboarding_order_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(
            config_path,
            {
                "ALMANAC_USER": "almanac",
                "ALMANAC_HOME": str(root / "home-almanac"),
                "ALMANAC_REPO_DIR": str(REPO),
                "ALMANAC_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(root / "state"),
                "RUNTIME_DIR": str(root / "state" / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ALMANAC_DB_PATH": str(root / "state" / "almanac-control.sqlite3"),
                "ALMANAC_AGENTS_STATE_DIR": str(root / "state" / "agents"),
                "ALMANAC_CURATOR_DIR": str(root / "state" / "curator"),
                "ALMANAC_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
                "ALMANAC_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
                "ALMANAC_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
                "ALMANAC_RELEASE_STATE_FILE": str(root / "state" / "almanac-release.json"),
                "ALMANAC_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ALMANAC_MCP_HOST": "127.0.0.1",
                "ALMANAC_MCP_PORT": "8282",
                "ALMANAC_MODEL_PRESET_CODEX": "openai:codex",
                "ALMANAC_CURATOR_CHANNELS": "telegram",
                "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "1",
                "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED": "0",
            },
        )

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            desired_unix_user = "almanac-intake"
            try:
                pwd.getpwnam(desired_unix_user)
            except KeyError:
                pass
            else:
                desired_unix_user = "almanac-intake-01"

            def fake_validate(_token: str):
                raise AssertionError("bot token validation should not run in intake-order test")

            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="telegram",
                    chat_id="123",
                    sender_id="123",
                    text="/start",
                    sender_username="sirouk",
                    sender_display_name="Chris",
                ),
                validate_bot_token=fake_validate,
            )
            expect("What should I call you?" in replies[0].text, replies[0].text)

            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="telegram",
                    chat_id="123",
                    sender_id="123",
                    text="Chris",
                    sender_username="sirouk",
                    sender_display_name="Chris",
                ),
                validate_bot_token=fake_validate,
            )
            expect("practice or get done" in replies[0].text, replies[0].text)

            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="telegram",
                    chat_id="123",
                    sender_id="123",
                    text="Keep the org moving",
                    sender_username="sirouk",
                    sender_display_name="Chris",
                ),
                validate_bot_token=fake_validate,
            )
            expect("Unix account" in replies[0].text or "Unix username" in replies[0].text, replies[0].text)

            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="telegram",
                    chat_id="123",
                    sender_id="123",
                    text=desired_unix_user,
                    sender_username="sirouk",
                    sender_display_name="Chris",
                ),
                validate_bot_token=fake_validate,
            )
            expect("bot carry" in replies[0].text, replies[0].text)
            expect("telegram" in replies[0].text.lower(), replies[0].text)
            print("PASS test_onboarding_intake_asks_purpose_before_unix_and_skips_platform_question")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_discord_prompt_and_operator_review_reflect_primary_control_channel()
    test_onboarding_intake_asks_purpose_before_unix_and_skips_platform_question()
    print("PASS all 2 onboarding prompt regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
