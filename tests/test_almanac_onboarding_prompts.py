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
PROVIDER_AUTH_PY = PYTHON_DIR / "almanac_onboarding_provider_auth.py"


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
            expect("Almanac’s Curator" in opening, opening)
            expect("First up" in opening, opening)

            purpose_prompt = onboarding.session_prompt(
                cfg,
                {
                    "state": "awaiting-purpose",
                    "answers": {},
                },
            )
            expect("A little context" in purpose_prompt, purpose_prompt)
            expect("practice, build, or keep moving" in purpose_prompt, purpose_prompt)

            unix_prompt = onboarding.session_prompt(
                cfg,
                {
                    "state": "awaiting-unix-user",
                    "answers": {},
                },
            )
            expect("shared host" in unix_prompt.lower(), unix_prompt)
            expect("private Unix account" in unix_prompt, unix_prompt)

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
            expect("Discord setup steps:" in prompt, prompt)
            expect("Install Link" in prompt, prompt)
            expect("Installation" in prompt, prompt)
            expect("Add to My Apps" in prompt, prompt)
            expect("Add to Server" in prompt, prompt)
            expect("Message Content Intent" in prompt, prompt)
            expect("OAuth2" not in prompt and "URL Generator" not in prompt, prompt)
            expect("Guild Install" not in prompt, prompt)
            expect("Server Members Intent" not in prompt, prompt)
            expect("new agent bot only" in prompt, prompt)
            expect("Reset Token" in prompt, prompt)
            expect("copy the bot token" in prompt, prompt)
            expect("paste that token here" in prompt, prompt)

            notion_access_prompt = onboarding.session_prompt(
                cfg,
                {
                    "state": "awaiting-notion-access",
                    "answers": {},
                },
            )
            expect("shared Almanac page" in notion_access_prompt, notion_access_prompt)
            expect("Full access" in notion_access_prompt, notion_access_prompt)
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
                    "platform": "discord",
                    "answers": {
                        "notion_claim_email": "chris@example.com",
                        "notion_claim_url": "https://www.notion.so/claim",
                        "notion_claim_expires_at": "2026-04-21T00:00:00+00:00",
                    },
                },
            )
            expect("https://www.notion.so/claim" in notion_verify_prompt, notion_verify_prompt)
            expect("chris@example.com" in notion_verify_prompt, notion_verify_prompt)
            expect("<t:" in notion_verify_prompt, notion_verify_prompt)
            expect("Request access" in notion_verify_prompt, notion_verify_prompt)
            expect("Full access" in notion_verify_prompt, notion_verify_prompt)

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
            expect("practice, build, or keep moving" in replies[0].text, replies[0].text)

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
            expect("Now name your" in replies[0].text, replies[0].text)
            expect("What should it be called?" in replies[0].text, replies[0].text)
            expect("telegram" in replies[0].text.lower(), replies[0].text)
            print("PASS test_onboarding_intake_asks_purpose_before_unix_and_skips_platform_question")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_onboarding_uses_resolved_sender_display_name_without_reasking() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_onboarding_resolved_name_test")
    onboarding = load_module(ONBOARDING_PY, "almanac_onboarding_resolved_name_test")
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
            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="telegram",
                    chat_id="123",
                    sender_id="123",
                    text="/start",
                    sender_username="sirouk",
                    sender_display_name="Chris Sirouk",
                ),
                validate_bot_token=lambda raw: None,
            )
            expect(len(replies) == 1, str(replies))
            expect("what should i call you" not in replies[0].text.lower(), replies[0].text)
            expect("A little context helps me shape the agent properly." in replies[0].text, replies[0].text)

            with control.connect_db(cfg) as conn:
                session = control.find_active_onboarding_session(conn, platform="telegram", sender_id="123")
            expect(session is not None, "expected active onboarding session")
            expect(str(session.get("state") or "") == "awaiting-purpose", str(session))
            expect(str((session.get("answers") or {}).get("full_name") or "") == "Chris Sirouk", str(session))
            print("PASS test_onboarding_uses_resolved_sender_display_name_without_reasking")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_shared_team_key_prompt_offers_default_reply_for_chutes() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_onboarding_shared_key_prompt_test")
    onboarding = load_module(ONBOARDING_PY, "almanac_onboarding_shared_key_prompt_test")
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
                "ALMANAC_MODEL_PRESET_CHUTES": "chutes:model-router",
                "CHUTES_API_KEY": "shared-chutes-key",
            },
        )

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            provider_setup = onboarding.resolve_provider_setup(cfg, "chutes", model_id="model-router", reasoning_effort="medium")
            prompt = onboarding.session_prompt(
                cfg,
                {
                    "state": "awaiting-provider-credential",
                    "answers": {"provider_setup": provider_setup.as_dict()},
                },
            )
            expect("team already provided" in prompt.lower(), prompt)
            expect("Reply `default`" in prompt, prompt)
            expect("paste a different" in prompt.lower(), prompt)
            print("PASS test_shared_team_key_prompt_offers_default_reply_for_chutes")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_shared_team_key_default_reply_uses_configured_secret() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_onboarding_shared_key_default_test")
    onboarding = load_module(ONBOARDING_PY, "almanac_onboarding_shared_key_default_test")
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
                "ALMANAC_MODEL_PRESET_CHUTES": "chutes:model-router",
                "CHUTES_API_KEY": "shared-chutes-key",
            },
        )

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            session = control.start_onboarding_session(
                conn,
                cfg,
                platform="telegram",
                chat_id="123",
                sender_id="123",
                sender_username="sirouk",
                sender_display_name="Chris",
            )
            provider_setup = onboarding.resolve_provider_setup(cfg, "chutes", model_id="model-router", reasoning_effort="medium")
            control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-provider-credential",
                answers={
                    "provider_setup": provider_setup.as_dict(),
                    "bot_platform": "telegram",
                    "preferred_bot_name": "Jeef",
                    "unix_user": "sirouk",
                },
            )

            captured: dict[str, str] = {}
            original_write_secret = onboarding.write_onboarding_secret
            original_begin = onboarding.begin_onboarding_provisioning
            try:
                onboarding.write_onboarding_secret = lambda cfg, session_id, secret_name, secret: captured.update({"session_id": session_id, "secret_name": secret_name, "secret": secret}) or "/tmp/shared-default.secret"
                onboarding.begin_onboarding_provisioning = (
                    lambda conn, cfg, updated, *, provider_secret_path: {
                        **updated,
                        "answers": {
                            **(updated.get("answers") or {}),
                            "unix_user": "sirouk",
                            "bot_platform": "telegram",
                            "bot_username": "Jeef",
                        },
                        "provider_secret_path": provider_secret_path,
                    }
                )
                replies = onboarding.process_onboarding_message(
                    cfg,
                    onboarding.IncomingMessage(
                        platform="telegram",
                        chat_id="123",
                        sender_id="123",
                        text="default",
                        sender_username="sirouk",
                        sender_display_name="Chris",
                    ),
                    validate_bot_token=lambda raw: None,
                )
            finally:
                onboarding.write_onboarding_secret = original_write_secret
                onboarding.begin_onboarding_provisioning = original_begin

            expect(captured["secret"] == "shared-chutes-key", str(captured))
            expect(captured["secret_name"] == "chutes_api_key", str(captured))
            expect("Good. I have what I need." in replies[0].text, replies[0].text)
            print("PASS test_shared_team_key_default_reply_uses_configured_secret")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_anthropic_opus_prompt_and_browser_auth_flow_require_oauth() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_onboarding_anthropic_oauth_test")
    onboarding = load_module(ONBOARDING_PY, "almanac_onboarding_anthropic_oauth_test")
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
                "ALMANAC_MODEL_PRESET_OPUS": "anthropic:claude-opus",
                "ALMANAC_CURATOR_CHANNELS": "telegram",
                "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "1",
                "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED": "0",
            },
        )

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            session = {
                "state": "awaiting-provider-browser-auth",
                "answers": {
                    "provider_setup": {
                        "preset": "opus",
                        "provider_id": "anthropic",
                        "model_id": "claude-opus-4-6",
                        "display_name": "Claude Opus",
                        "auth_flow": "anthropic-credential",
                    },
                    "provider_browser_auth": {
                        "provider": "anthropic",
                        "auth_url": "https://claude.ai/oauth/authorize?example=1",
                    },
                },
            }
            prompt = onboarding.session_prompt(cfg, session)
            expect("Claude account" in prompt, prompt)
            expect("Claude Max" in prompt or "Max" in prompt, prompt)
            expect("Claude Code credentials" in prompt, prompt)
            expect("sk-ant-api" not in prompt, prompt)
            expect("sk-ant-oat" not in prompt, prompt)

            conn = control.connect_db(cfg)
            live = control.start_onboarding_session(
                conn,
                cfg,
                platform="telegram",
                chat_id="123",
                sender_id="123",
                sender_username="sirouk",
                sender_display_name="Chris",
            )
            live = control.save_onboarding_session(
                conn,
                session_id=str(live["session_id"]),
                state="awaiting-provider-browser-auth",
                answers={
                    "provider_setup": {
                        "preset": "opus",
                        "provider_id": "anthropic",
                        "model_id": "claude-opus-4-6",
                        "display_name": "Claude Opus",
                        "auth_flow": "anthropic-credential",
                    },
                    "provider_browser_auth": {
                        "provider": "anthropic",
                        "auth_url": "https://claude.ai/oauth/authorize?example=1",
                    },
                },
            )
            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="telegram",
                    chat_id="123",
                    sender_id="123",
                    sender_username="sirouk",
                    sender_display_name="Chris",
                    text="sk-ant-api-test-token",
                ),
                validate_bot_token=lambda raw: None,
            )
            expect(len(replies) == 1, str(replies))
            expect("OAuth" in replies[0].text or "browser" in replies[0].text, replies[0].text)
            refreshed = control.get_onboarding_session(conn, str(live["session_id"]), redact_secrets=False)
            expect(str(refreshed.get("state") or "") == "awaiting-provider-browser-auth", str(refreshed))
            print("PASS test_anthropic_opus_prompt_and_browser_auth_flow_require_oauth")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_anthropic_callback_exchange_returns_claude_code_credentials_payload() -> None:
    provider_auth = load_module(PROVIDER_AUTH_PY, "almanac_provider_auth_anthropic_payload_test")
    captured: dict[str, object] = {}

    def fake_request_json(url: str, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return {
            "access_token": "access-test-token",
            "refresh_token": "refresh-test-token",
            "expires_in": 1800,
            "scope": "user:inference user:profile",
        }

    provider_auth._request_json = fake_request_json  # noqa: SLF001
    before_ms = int(provider_auth.time.time() * 1000)
    secret, auth_state = provider_auth.complete_anthropic_pkce_authorization(
        {
            "flow": "claude_code_oauth",
            "provider": "anthropic",
            "state": "state-from-start",
            "verifier": "verifier-from-start",
        },
        "callback-code#state-from-callback",
    )
    payload = json.loads(secret)
    expect(payload["kind"] == "claude_code_oauth", payload)
    expect(payload["accessToken"] == "access-test-token", payload)
    expect(payload["refreshToken"] == "refresh-test-token", payload)
    expect(payload["expiresAt"] >= before_ms + (1700 * 1000), payload)
    expect(payload["scopes"] == ["user:inference", "user:profile"], payload)
    expect(auth_state["status"] == "approved", auth_state)
    expect(auth_state["credential_shape"] == "claude_code_credentials", auth_state)

    request_payload = captured["kwargs"]["payload"]  # type: ignore[index]
    expect(captured["url"] == provider_auth.ANTHROPIC_OAUTH_TOKEN_URL, str(captured))
    expect(request_payload["code"] == "callback-code", str(captured))
    expect(request_payload["state"] == "state-from-callback", str(captured))
    expect(request_payload["code_verifier"] == "verifier-from-start", str(captured))
    print("PASS test_anthropic_callback_exchange_returns_claude_code_credentials_payload")


def test_onboarding_model_picker_is_chutes_first_and_collects_reasoning() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_onboarding_model_picker_test")
    onboarding = load_module(ONBOARDING_PY, "almanac_onboarding_model_picker_test")
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
                "ALMANAC_MODEL_PRESET_OPUS": "anthropic:claude-opus",
                # Legacy installs may still carry auto-failover; onboarding should surface the current
                # Chutes recommendation instead of teaching new users the old alias.
                "ALMANAC_MODEL_PRESET_CHUTES": "chutes:auto-failover",
                "ALMANAC_CURATOR_CHANNELS": "discord",
                "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "0",
                "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED": "1",
            },
        )

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            desired_unix_user = "almanac-model-picker"
            try:
                pwd.getpwnam(desired_unix_user)
            except KeyError:
                pass
            else:
                desired_unix_user = "almanac-model-picker-01"

            def send(text: str):
                return onboarding.process_onboarding_message(
                    cfg,
                    onboarding.IncomingMessage(
                        platform="discord",
                        chat_id="456",
                        sender_id="456",
                        text=text,
                        sender_username="sirouk",
                        sender_display_name="Chris",
                    ),
                    validate_bot_token=lambda raw: None,
                )

            expect("practice, build, or keep moving" in send("/start")[0].text, "missing purpose prompt")
            send("Build impossible things calmly")
            send(desired_unix_user)
            model_prompt = send("Jeef")[0].text
            expect("Now let’s pick the model provider" in model_prompt, model_prompt)
            expect(model_prompt.index("1. Chutes") < model_prompt.index("2. Claude Opus"), model_prompt)
            expect(model_prompt.index("2. Claude Opus") < model_prompt.index("3. OpenAI Codex"), model_prompt)

            model_id_prompt = send("1")[0].text
            expect("Great, Chutes it is" in model_id_prompt, model_id_prompt)
            expect("model-router" in model_id_prompt, model_id_prompt)
            expect("moonshotai/Kimi-K2.6-TEE" in model_id_prompt, model_id_prompt)
            expect("zai-org/GLM-5.1-TEE" in model_id_prompt, model_id_prompt)

            thinking_prompt = send("zai-org/GLM-5.1-TEE")[0].text
            expect("How much thinking room" in thinking_prompt, thinking_prompt)
            expect("Pick the default reasoning depth" in thinking_prompt, thinking_prompt)
            expect("1. xhigh" in thinking_prompt, thinking_prompt)
            expect("2. high" in thinking_prompt, thinking_prompt)
            expect("3. medium" in thinking_prompt, thinking_prompt)
            expect("6. none" in thinking_prompt, thinking_prompt)
            expect("Chutes thinking mode" in thinking_prompt, thinking_prompt)

            approval_prompt = send("1")[0].text
            expect("operator for approval" in approval_prompt, approval_prompt)
            session = control.find_active_onboarding_session(
                conn,
                platform="discord",
                sender_id="456",
            )
            answers = session.get("answers") or {}
            expect(answers["model_preset"] == "chutes", str(answers))
            expect(answers["model_id"] == "zai-org/GLM-5.1-TEE", str(answers))
            expect(answers["reasoning_effort"] == "xhigh", str(answers))

            review = onboarding._operator_review_message(cfg, session)  # noqa: SLF001
            expect("Model provider: Chutes (`chutes`)" in review, review)
            expect("Model id: zai-org/GLM-5.1-TEE" in review, review)
            expect("Thinking level: xhigh" in review, review)

            provider_setup = onboarding.resolve_provider_setup(  # noqa: SLF001
                cfg,
                "chutes",
                model_id="zai-org/GLM-5.1-TEE",
                reasoning_effort="xhigh",
            )
            expect(provider_setup.provider_id == "chutes", str(provider_setup))
            expect(provider_setup.base_url == "https://llm.chutes.ai/v1", str(provider_setup))
            expect(provider_setup.model_id == "zai-org/GLM-5.1-TEE:THINKING", str(provider_setup))
            expect(provider_setup.reasoning_effort == "xhigh", str(provider_setup))
            print("PASS test_onboarding_model_picker_is_chutes_first_and_collects_reasoning")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_discord_prompt_and_operator_review_reflect_primary_control_channel()
    test_onboarding_intake_asks_purpose_before_unix_and_skips_platform_question()
    test_onboarding_uses_resolved_sender_display_name_without_reasking()
    test_shared_team_key_prompt_offers_default_reply_for_chutes()
    test_shared_team_key_default_reply_uses_configured_secret()
    test_anthropic_opus_prompt_and_browser_auth_flow_require_oauth()
    test_anthropic_callback_exchange_returns_claude_code_credentials_payload()
    test_onboarding_model_picker_is_chutes_first_and_collects_reasoning()
    print("PASS all 8 onboarding prompt regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
