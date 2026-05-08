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
CONTROL_PY = PYTHON_DIR / "arclink_control.py"
ONBOARDING_PY = PYTHON_DIR / "arclink_onboarding_flow.py"
PROVIDER_AUTH_PY = PYTHON_DIR / "arclink_onboarding_provider_auth.py"
ORG_PROFILE_PY = PYTHON_DIR / "arclink_org_profile.py"


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
    control = load_module(CONTROL_PY, "arclink_control_onboarding_prompt_test")
    onboarding = load_module(ONBOARDING_PY, "arclink_onboarding_prompt_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(root / "state"),
                "RUNTIME_DIR": str(root / "state" / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ARCLINK_DB_PATH": str(root / "state" / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(root / "state" / "agents"),
                "ARCLINK_CURATOR_DIR": str(root / "state" / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(root / "state" / "arclink-release.json"),
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ARCLINK_MCP_HOST": "127.0.0.1",
                "ARCLINK_MCP_PORT": "8282",
                "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "discord",
                "OPERATOR_NOTIFY_CHANNEL_ID": "123456789012345678",
                "ARCLINK_CURATOR_CHANNELS": "tui-only",
            },
        )

        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
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
            expect("Raven, the ArcLink Curator" in opening, opening)
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
                        "preferred_bot_name": "OrgName",
                    },
                },
            )
            expect("Discord setup steps:" in prompt, prompt)
            expect("Install Link" not in prompt, prompt)
            expect("Installation" not in prompt, prompt)
            expect("Add to My Apps" not in prompt, prompt)
            expect("Add to Server" not in prompt, prompt)
            expect("Message Content Intent" in prompt, prompt)
            expect("OAuth2" not in prompt and "URL Generator" not in prompt, prompt)
            expect("Guild Install" not in prompt, prompt)
            expect("Server Members Intent" not in prompt, prompt)
            expect("new agent bot only" in prompt, prompt)
            expect("do not need to add this bot to a server" in prompt, prompt)
            expect("confirmation code" in prompt, prompt)
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
            expect("shared ArcLink page" in notion_access_prompt, notion_access_prompt)
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
                        "notion_claim_email": "alex@example.com",
                        "notion_claim_url": "https://www.notion.so/claim",
                        "notion_claim_expires_at": "2026-04-21T00:00:00+00:00",
                    },
                },
            )
            expect("https://www.notion.so/claim" in notion_verify_prompt, notion_verify_prompt)
            expect("alex@example.com" in notion_verify_prompt, notion_verify_prompt)
            expect("<t:" in notion_verify_prompt, notion_verify_prompt)
            expect("Request access" in notion_verify_prompt, notion_verify_prompt)
            expect("Full access" in notion_verify_prompt, notion_verify_prompt)

            backup_key = "ssh-ed25519 AAAAC3NzaAgentBackupKey arclink-agent-backup@test"
            telegram_backup_key_prompt = onboarding.session_prompt(
                cfg,
                {
                    "platform": "telegram",
                    "state": "awaiting-agent-backup-key-install",
                    "answers": {
                        "agent_backup_owner_repo": "example/arclink_guide",
                        "agent_backup_public_key": backup_key,
                    },
                },
            )
            expect(onboarding.session_prompt_telegram_parse_mode({"platform": "telegram", "state": "awaiting-agent-backup-key-install"}) == "HTML", telegram_backup_key_prompt)
            expect("<code>ssh-ed25519 AAAAC3NzaAgentBackupKey arclink-agent-backup@test</code>" in telegram_backup_key_prompt, telegram_backup_key_prompt)
            expect('href="https://github.com/example/arclink_guide/settings/keys"' in telegram_backup_key_prompt, telegram_backup_key_prompt)

            discord_backup_key_prompt = onboarding.session_prompt(
                cfg,
                {
                    "platform": "discord",
                    "state": "awaiting-agent-backup-key-install",
                    "answers": {
                        "agent_backup_owner_repo": "example/arclink-guide",
                        "agent_backup_public_key": backup_key,
                    },
                },
            )
            expect("```text\nssh-ed25519 AAAAC3NzaAgentBackupKey arclink-agent-backup@test\n```" in discord_backup_key_prompt, discord_backup_key_prompt)

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
                        "preferred_bot_name": "OrgName",
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
    control = load_module(CONTROL_PY, "arclink_control_onboarding_order_test")
    onboarding = load_module(ONBOARDING_PY, "arclink_onboarding_order_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(root / "state"),
                "RUNTIME_DIR": str(root / "state" / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ARCLINK_DB_PATH": str(root / "state" / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(root / "state" / "agents"),
                "ARCLINK_CURATOR_DIR": str(root / "state" / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(root / "state" / "arclink-release.json"),
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ARCLINK_MCP_HOST": "127.0.0.1",
                "ARCLINK_MCP_PORT": "8282",
                "ARCLINK_MODEL_PRESET_CODEX": "openai:codex",
                "ARCLINK_CURATOR_CHANNELS": "telegram",
                "ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "1",
                "ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED": "0",
            },
        )

        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            desired_unix_user = "arclink-intake"
            try:
                pwd.getpwnam(desired_unix_user)
            except KeyError:
                pass
            else:
                desired_unix_user = "arclink-intake-01"

            def fake_validate(_token: str):
                raise AssertionError("bot token validation should not run in intake-order test")

            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="telegram",
                    chat_id="123",
                    sender_id="123",
                    text="/start",
                    sender_username="alex",
                    sender_display_name="Alex",
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
                    sender_username="alex",
                    sender_display_name="Alex",
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
                    sender_username="alex",
                    sender_display_name="Alex",
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


def test_chat_onboarding_reserves_unix_user_before_provisioning() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_onboarding_unix_reservation_test")
    onboarding = load_module(ONBOARDING_PY, "arclink_onboarding_unix_reservation_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(root / "state"),
                "RUNTIME_DIR": str(root / "state" / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ARCLINK_DB_PATH": str(root / "state" / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(root / "state" / "agents"),
                "ARCLINK_CURATOR_DIR": str(root / "state" / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(root / "state" / "arclink-release.json"),
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ARCLINK_MCP_HOST": "127.0.0.1",
                "ARCLINK_MCP_PORT": "8282",
                "ARCLINK_MODEL_PRESET_CODEX": "openai:codex",
                "ARCLINK_CURATOR_CHANNELS": "telegram",
                "ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "1",
                "ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED": "0",
            },
        )

        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            reserved_unix_user = "arclink-reserve-test"
            try:
                pwd.getpwnam(reserved_unix_user)
            except KeyError:
                pass
            else:
                reserved_unix_user = "arclink-reserve-01"

            def fake_validate(_token: str):
                raise AssertionError("bot token validation should not run in unix-reservation test")

            def send(sender_id: str, text: str, display_name: str) -> list[object]:
                return onboarding.process_onboarding_message(
                    cfg,
                    onboarding.IncomingMessage(
                        platform="telegram",
                        chat_id=sender_id,
                        sender_id=sender_id,
                        text=text,
                        sender_username=f"user{sender_id}",
                        sender_display_name=display_name,
                    ),
                    validate_bot_token=fake_validate,
                )

            send("101", "/start", "Alex")
            send("101", "Keep the org moving", "Alex")
            first_reply = send("101", reserved_unix_user, "Alex")[0]
            expect("Now name your" in first_reply.text, first_reply.text)

            send("202", "/start", "Blair")
            send("202", "Build useful habits", "Blair")
            second_reply = send("202", reserved_unix_user, "Blair")[0]
            expect("already being used by an active onboarding session" in second_reply.text, second_reply.text)
            print("PASS test_chat_onboarding_reserves_unix_user_before_provisioning")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_onboarding_offers_safe_org_profile_match_without_forcing_names() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_onboarding_profile_match_test")
    onboarding = load_module(ONBOARDING_PY, "arclink_onboarding_profile_match_test")
    org_profile = load_module(ORG_PROFILE_PY, "arclink_org_profile_onboarding_profile_match_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(root / "state"),
                "RUNTIME_DIR": str(root / "state" / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ARCLINK_DB_PATH": str(root / "state" / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(root / "state" / "agents"),
                "ARCLINK_CURATOR_DIR": str(root / "state" / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(root / "state" / "arclink-release.json"),
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ARCLINK_MCP_HOST": "127.0.0.1",
                "ARCLINK_MCP_PORT": "8282",
                "ARCLINK_MODEL_PRESET_CODEX": "openai:codex",
                "ARCLINK_CURATOR_CHANNELS": "discord",
                "ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "0",
                "ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED": "1",
            },
        )

        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            profile = {
                "version": 1,
                "organization": {
                    "id": "example-context",
                    "name": "Example Context",
                    "profile_kind": "organization",
                    "mission": "Keep a shared operating profile coherent.",
                },
                "roles": {"operator": {"description": "Profile operator"}},
                "people": [
                    {
                        "id": "alex-rivera",
                        "display_name": "Alex Rivera",
                        "role": "operator",
                        "unix_user": "arclink-profile-alex",
                        "agent": {"name": "Atlas", "purpose": "Help Alex operate."},
                    },
                    {
                        "id": "blair-stone",
                        "display_name": "Blair Stone",
                        "role": "operator",
                        "unix_user": "arclink-profile-blair",
                        "agent": {"name": "Comet", "purpose": "Help Blair operate."},
                    },
                ],
                "policies": {
                    "privacy": {
                        "default_people_visibility": "org_visible",
                        "sensitive_fields": ["identity_hints"],
                    }
                },
            }
            with control.connect_db(cfg) as conn:
                applied = org_profile.apply_profile(
                    conn,
                    cfg,
                    profile=profile,
                    source_path=root / "org-profile.yaml",
                    actor="test",
                )
                expect(applied["applied"], str(applied))

            def fake_validate(_token: str):
                raise AssertionError("bot token validation should not run in profile-match test")

            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="discord",
                    chat_id="dm-1",
                    sender_id="user-1",
                    text="/start",
                    sender_username="blair",
                    sender_display_name="Blair Stone",
                ),
                validate_bot_token=fake_validate,
            )
            expect("prepared profile entries" in replies[0].text, replies[0].text)
            expect("Blair Stone" in replies[0].text, replies[0].text)
            expect("not identity verification" in replies[0].text, replies[0].text)

            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="discord",
                    chat_id="dm-1",
                    sender_id="user-1",
                    text="1",
                    sender_username="blair",
                    sender_display_name="Blair Stone",
                ),
                validate_bot_token=fake_validate,
            )
            expect("A little context helps me shape the agent properly." in replies[0].text, replies[0].text)
            with control.connect_db(cfg) as conn:
                session = control.find_active_onboarding_session(conn, platform="discord", sender_id="user-1")
            expect(session is not None, "expected active session")
            answers = session.get("answers") or {}
            expect(answers.get("org_profile_person_id") == "blair-stone", str(answers))
            expect(answers.get("org_profile_match_status") == "user_selected_unverified", str(answers))

            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="discord",
                    chat_id="dm-1",
                    sender_id="user-1",
                    text="Keep launches tidy",
                    sender_username="blair",
                    sender_display_name="Blair Stone",
                ),
                validate_bot_token=fake_validate,
            )
            expect("Reply `default`" in replies[0].text, replies[0].text)
            expect("arclink-profile-blair" in replies[0].text, replies[0].text)

            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="discord",
                    chat_id="dm-1",
                    sender_id="user-1",
                    text="default",
                    sender_username="blair",
                    sender_display_name="Blair Stone",
                ),
                validate_bot_token=fake_validate,
            )
            expect("Now name your discord agent bot." in replies[0].text, replies[0].text)
            with control.connect_db(cfg) as conn:
                session = control.find_active_onboarding_session(conn, platform="discord", sender_id="user-1")
            expect((session.get("answers") or {}).get("unix_user") == "arclink-profile-blair", str(session))
            print("PASS test_onboarding_offers_safe_org_profile_match_without_forcing_names")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_onboarding_respects_disabled_org_profile_roster_prompt() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_onboarding_profile_disabled_test")
    onboarding = load_module(ONBOARDING_PY, "arclink_onboarding_profile_disabled_test")
    org_profile = load_module(ORG_PROFILE_PY, "arclink_org_profile_disabled_match_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(root / "state"),
                "RUNTIME_DIR": str(root / "state" / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ARCLINK_DB_PATH": str(root / "state" / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(root / "state" / "agents"),
                "ARCLINK_CURATOR_DIR": str(root / "state" / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(root / "state" / "arclink-release.json"),
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ARCLINK_MCP_HOST": "127.0.0.1",
                "ARCLINK_MCP_PORT": "8282",
                "ARCLINK_MODEL_PRESET_CODEX": "openai:codex",
                "ARCLINK_CURATOR_CHANNELS": "discord",
                "ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED": "1",
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            profile = {
                "version": 1,
                "organization": {"id": "example", "name": "Example", "profile_kind": "organization", "mission": "Operate."},
                "roles": {"operator": {"description": "Operator"}},
                "people": [
                    {"id": "blair", "display_name": "Blair Stone", "role": "operator", "unix_user": "blair", "agent": {"name": "Comet"}}
                ],
                "identity_verification": {"safe_roster_prompt": False, "allowed_match_visibility": "unclaimed_people_only"},
                "policies": {"privacy": {"default_people_visibility": "org_visible"}},
            }
            with control.connect_db(cfg) as conn:
                org_profile.apply_profile(conn, cfg, profile=profile, source_path=root / "org-profile.yaml", actor="test")
            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="discord",
                    chat_id="dm-1",
                    sender_id="user-1",
                    text="/start",
                    sender_username="blair",
                    sender_display_name="Blair Stone",
                ),
                validate_bot_token=lambda _raw: None,
            )
            expect("prepared operating-profile entries" not in replies[0].text, replies[0].text)
            expect("A little context helps me shape the agent properly." in replies[0].text, replies[0].text)
            print("PASS test_onboarding_respects_disabled_org_profile_roster_prompt")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_onboarding_uses_resolved_sender_display_name_without_reasking() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_onboarding_resolved_name_test")
    onboarding = load_module(ONBOARDING_PY, "arclink_onboarding_resolved_name_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(root / "state"),
                "RUNTIME_DIR": str(root / "state" / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ARCLINK_DB_PATH": str(root / "state" / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(root / "state" / "agents"),
                "ARCLINK_CURATOR_DIR": str(root / "state" / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(root / "state" / "arclink-release.json"),
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ARCLINK_MCP_HOST": "127.0.0.1",
                "ARCLINK_MCP_PORT": "8282",
                "ARCLINK_MODEL_PRESET_CODEX": "openai:codex",
                "ARCLINK_CURATOR_CHANNELS": "telegram",
                "ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "1",
                "ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED": "0",
            },
        )

        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="telegram",
                    chat_id="123",
                    sender_id="123",
                    text="/start",
                    sender_username="alex",
                    sender_display_name="Alex Example",
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
            expect(str((session.get("answers") or {}).get("full_name") or "") == "Alex Example", str(session))
            print("PASS test_onboarding_uses_resolved_sender_display_name_without_reasking")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_shared_team_key_prompt_offers_default_reply_for_chutes() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_onboarding_shared_key_prompt_test")
    onboarding = load_module(ONBOARDING_PY, "arclink_onboarding_shared_key_prompt_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(root / "state"),
                "RUNTIME_DIR": str(root / "state" / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ARCLINK_DB_PATH": str(root / "state" / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(root / "state" / "agents"),
                "ARCLINK_CURATOR_DIR": str(root / "state" / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(root / "state" / "arclink-release.json"),
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ARCLINK_MCP_HOST": "127.0.0.1",
                "ARCLINK_MCP_PORT": "8282",
                "ARCLINK_MODEL_PRESET_CHUTES": "chutes:model-router",
                "CHUTES_API_KEY": "shared-chutes-key",
            },
        )

        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
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
            expect("live provider validation happens during provisioning" in prompt, prompt)
            print("PASS test_shared_team_key_prompt_offers_default_reply_for_chutes")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_shared_team_key_default_reply_uses_configured_secret() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_onboarding_shared_key_default_test")
    onboarding = load_module(ONBOARDING_PY, "arclink_onboarding_shared_key_default_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(root / "state"),
                "RUNTIME_DIR": str(root / "state" / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ARCLINK_DB_PATH": str(root / "state" / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(root / "state" / "agents"),
                "ARCLINK_CURATOR_DIR": str(root / "state" / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(root / "state" / "arclink-release.json"),
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ARCLINK_MCP_HOST": "127.0.0.1",
                "ARCLINK_MCP_PORT": "8282",
                "ARCLINK_MODEL_PRESET_CHUTES": "chutes:model-router",
                "CHUTES_API_KEY": "shared-chutes-key",
            },
        )

        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            session = control.start_onboarding_session(
                conn,
                cfg,
                platform="telegram",
                chat_id="123",
                sender_id="123",
                sender_username="alex",
                sender_display_name="Alex",
            )
            provider_setup = onboarding.resolve_provider_setup(cfg, "chutes", model_id="model-router", reasoning_effort="medium")
            control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-provider-credential",
                answers={
                    "provider_setup": provider_setup.as_dict(),
                    "bot_platform": "telegram",
                    "preferred_bot_name": "Guide",
                    "unix_user": "alex",
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
                            "unix_user": "alex",
                            "bot_platform": "telegram",
                            "bot_username": "Guide",
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
                        sender_username="alex",
                        sender_display_name="Alex",
                    ),
                    validate_bot_token=lambda raw: None,
                )
            finally:
                onboarding.write_onboarding_secret = original_write_secret
                onboarding.begin_onboarding_provisioning = original_begin

            expect(captured["secret"] == "shared-chutes-key", str(captured))
            expect(captured["secret_name"] == "chutes_api_key", str(captured))
            expect("Good. I have what I need." in replies[0].text, replies[0].text)
            expect("live provider validation is pending during provisioning" in replies[0].text, replies[0].text)
            refreshed = control.get_onboarding_session(conn, str(session["session_id"]), redact_secrets=False)
            validation = (refreshed.get("answers") or {}).get("provider_credential_validation") or {}
            expect(validation.get("status") == "runtime_pending", str(validation))
            expect(validation.get("checked") == "present", str(validation))
            expect(validation.get("provider_id") == "chutes", str(validation))
            print("PASS test_shared_team_key_default_reply_uses_configured_secret")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_anthropic_opus_prompt_and_browser_auth_flow_require_oauth() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_onboarding_anthropic_oauth_test")
    onboarding = load_module(ONBOARDING_PY, "arclink_onboarding_anthropic_oauth_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(root / "state"),
                "RUNTIME_DIR": str(root / "state" / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ARCLINK_DB_PATH": str(root / "state" / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(root / "state" / "agents"),
                "ARCLINK_CURATOR_DIR": str(root / "state" / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(root / "state" / "arclink-release.json"),
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ARCLINK_MCP_HOST": "127.0.0.1",
                "ARCLINK_MCP_PORT": "8282",
                "ARCLINK_MODEL_PRESET_OPUS": "anthropic:claude-opus",
                "ARCLINK_CURATOR_CHANNELS": "telegram",
                "ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "1",
                "ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED": "0",
            },
        )

        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            session = {
                "state": "awaiting-provider-browser-auth",
                "answers": {
                    "provider_setup": {
                        "preset": "opus",
                        "provider_id": "anthropic",
                        "model_id": "claude-opus-4-7",
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
                sender_username="alex",
                sender_display_name="Alex",
            )
            live = control.save_onboarding_session(
                conn,
                session_id=str(live["session_id"]),
                state="awaiting-provider-browser-auth",
                answers={
                    "provider_setup": {
                        "preset": "opus",
                        "provider_id": "anthropic",
                        "model_id": "claude-opus-4-7",
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
                    sender_username="alex",
                    sender_display_name="Alex",
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
    provider_auth = load_module(PROVIDER_AUTH_PY, "arclink_provider_auth_anthropic_payload_test")
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
    control = load_module(CONTROL_PY, "arclink_control_onboarding_model_picker_test")
    onboarding = load_module(ONBOARDING_PY, "arclink_onboarding_model_picker_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(root / "state"),
                "RUNTIME_DIR": str(root / "state" / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ARCLINK_DB_PATH": str(root / "state" / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(root / "state" / "agents"),
                "ARCLINK_CURATOR_DIR": str(root / "state" / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(root / "state" / "arclink-release.json"),
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ARCLINK_MCP_HOST": "127.0.0.1",
                "ARCLINK_MCP_PORT": "8282",
                "ARCLINK_MODEL_PRESET_CODEX": "openai:codex",
                "ARCLINK_MODEL_PRESET_OPUS": "anthropic:claude-opus",
                # Legacy installs may still carry auto-failover; onboarding should surface the current
                # Chutes recommendation instead of teaching new users the old alias.
                "ARCLINK_MODEL_PRESET_CHUTES": "chutes:auto-failover",
                "ARCLINK_CURATOR_CHANNELS": "discord",
                "ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "0",
                "ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED": "1",
            },
        )

        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            desired_unix_user = "arclink-model-picker"
            try:
                pwd.getpwnam(desired_unix_user)
            except KeyError:
                pass
            else:
                desired_unix_user = "arclink-model-picker-01"

            def send(text: str):
                return onboarding.process_onboarding_message(
                    cfg,
                    onboarding.IncomingMessage(
                        platform="discord",
                        chat_id="456",
                        sender_id="456",
                        text=text,
                        sender_username="alex",
                        sender_display_name="Alex",
                    ),
                    validate_bot_token=lambda raw: None,
                )

            expect("practice, build, or keep moving" in send("/start")[0].text, "missing purpose prompt")
            send("Build impossible things calmly")
            send(desired_unix_user)
            model_prompt = send("Guide")[0].text
            expect("Now choose what should power this agent" in model_prompt, model_prompt)
            expect(model_prompt.index("1. Chutes") < model_prompt.index("2. Claude Opus"), model_prompt)
            expect(model_prompt.index("2. Claude Opus") < model_prompt.index("3. OpenAI Codex"), model_prompt)

            model_id_prompt = send("1")[0].text
            expect("Great, Chutes it is" in model_id_prompt, model_id_prompt)
            expect("model-router" in model_id_prompt, model_id_prompt)
            expect("moonshotai/Kimi-K2.6-TEE" in model_id_prompt, model_id_prompt)
            expect("zai-org/GLM-5.1-TEE" in model_id_prompt, model_id_prompt)

            thinking_prompt = send("zai-org/GLM-5.1-TEE")[0].text
            expect("How much thinking room" in thinking_prompt, thinking_prompt)
            expect("medium` is a good default" in thinking_prompt, thinking_prompt)
            expect("1. xhigh" in thinking_prompt, thinking_prompt)
            expect("2. high" in thinking_prompt, thinking_prompt)
            expect("3. medium" in thinking_prompt, thinking_prompt)
            expect("6. none" in thinking_prompt, thinking_prompt)
            expect("Chutes thinking mode" in thinking_prompt, thinking_prompt)

            approval_prompt = send("1")[0].text
            expect("onboarding request to the operator" in approval_prompt, approval_prompt)
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


def test_org_provided_model_choice_skips_user_model_and_credential_prompts() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_org_provider_option_test")
    onboarding = load_module(ONBOARDING_PY, "arclink_onboarding_org_provider_option_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(root / "state"),
                "RUNTIME_DIR": str(root / "state" / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ARCLINK_DB_PATH": str(root / "state" / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(root / "state" / "agents"),
                "ARCLINK_CURATOR_DIR": str(root / "state" / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(root / "state" / "arclink-release.json"),
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ARCLINK_MCP_HOST": "127.0.0.1",
                "ARCLINK_MCP_PORT": "8282",
                "ARCLINK_MODEL_PRESET_CODEX": "openai:codex",
                "ARCLINK_MODEL_PRESET_OPUS": "anthropic:claude-opus",
                "ARCLINK_MODEL_PRESET_CHUTES": "chutes:model-router",
                "ARCLINK_ORG_NAME": "ExampleOrg",
                "ARCLINK_ORG_PROVIDER_ENABLED": "1",
                "ARCLINK_ORG_PROVIDER_PRESET": "chutes",
                "ARCLINK_ORG_PROVIDER_MODEL_ID": "moonshotai/Kimi-K2.6-TEE",
                "ARCLINK_ORG_PROVIDER_REASONING_EFFORT": "xhigh",
                "ARCLINK_ORG_PROVIDER_SECRET_PROVIDER": "chutes",
                "ARCLINK_ORG_PROVIDER_SECRET": "org-chutes-key",
                "ARCLINK_CURATOR_CHANNELS": "telegram",
                "ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "1",
            },
        )

        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            expect("org-provided" in cfg.model_presets, str(cfg.model_presets))
            conn = control.connect_db(cfg)

            def send(text: str):
                return onboarding.process_onboarding_message(
                    cfg,
                    onboarding.IncomingMessage(
                        platform="telegram",
                        chat_id="123",
                        sender_id="123",
                        text=text,
                        sender_username="alex",
                        sender_display_name="Alex",
                    ),
                    validate_bot_token=lambda raw: None,
                )

            send("/start")
            send("Practice the system")
            send("orgtest")
            model_prompt = send("Joof")[0].text
            expect("1. Org-provided (Chutes)" in model_prompt, model_prompt)
            expect("moonshotai/Kimi-K2.6-TEE" in model_prompt, model_prompt)
            expect(model_prompt.index("Org-provided") < model_prompt.index("Chutes (`chutes`)"), model_prompt)

            approval_prompt = send("org")[0].text
            expect("Using organization-provided Chutes" in approval_prompt, approval_prompt)
            expect("moonshotai/Kimi-K2.6-TEE" in approval_prompt, approval_prompt)
            expect("hermes-exampleorg-remote-orgtest setup model" in approval_prompt, approval_prompt)
            expect("does not switch Chutes" in approval_prompt, approval_prompt)
            expect("onboarding request to the operator" in approval_prompt, approval_prompt)

            session = control.find_active_onboarding_session(conn, platform="telegram", sender_id="123")
            answers = session.get("answers") or {}
            expect(str(session.get("state") or "") == "awaiting-operator-approval", str(session))
            expect(answers["model_preset"] == "org-provided", str(answers))
            expect(answers["model_id"] == "moonshotai/Kimi-K2.6-TEE", str(answers))
            expect(answers["reasoning_effort"] == "xhigh", str(answers))

            review = onboarding._operator_review_message(cfg, session)  # noqa: SLF001
            expect("Model provider: Org-provided (Chutes) (`org-provided`)" in review, review)
            expect("Model id: moonshotai/Kimi-K2.6-TEE" in review, review)
            print("PASS test_org_provided_model_choice_skips_user_model_and_credential_prompts")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_org_provided_secret_auto_stages_after_bot_token() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_org_provider_secret_test")
    onboarding = load_module(ONBOARDING_PY, "arclink_onboarding_org_provider_secret_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        org_codex_secret = json.dumps(
            {
                "access_token": "access",
                "refresh_token": "refresh",
                "last_refresh": "2026-04-25T00:00:00Z",
                "base_url": "https://chatgpt.com/backend-api/codex",
            },
            sort_keys=True,
        )
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(root / "state"),
                "RUNTIME_DIR": str(root / "state" / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ARCLINK_DB_PATH": str(root / "state" / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(root / "state" / "agents"),
                "ARCLINK_CURATOR_DIR": str(root / "state" / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(root / "state" / "arclink-release.json"),
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ARCLINK_MCP_HOST": "127.0.0.1",
                "ARCLINK_MCP_PORT": "8282",
                "ARCLINK_MODEL_PRESET_CODEX": "openai:codex",
                "ARCLINK_MODEL_PRESET_OPUS": "anthropic:claude-opus",
                "ARCLINK_MODEL_PRESET_CHUTES": "chutes:model-router",
                "ARCLINK_ORG_PROVIDER_ENABLED": "1",
                "ARCLINK_ORG_PROVIDER_PRESET": "codex",
                "ARCLINK_ORG_PROVIDER_MODEL_ID": "gpt-5.4",
                "ARCLINK_ORG_PROVIDER_SECRET_PROVIDER": "codex",
                "ARCLINK_ORG_PROVIDER_SECRET": org_codex_secret,
            },
        )

        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            session = control.start_onboarding_session(
                conn,
                cfg,
                platform="discord",
                chat_id="456",
                sender_id="456",
                sender_username="alex",
                sender_display_name="Alex",
            )
            control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-bot-token",
                answers={
                    "bot_platform": "discord",
                    "preferred_bot_name": "Guide",
                    "unix_user": "orgcodex",
                    "model_preset": "org-provided",
                    "model_id": "gpt-5.4",
                    "reasoning_effort": "medium",
                },
            )

            captured: dict[str, object] = {}
            original_write_secret = onboarding.write_onboarding_secret
            original_write_bot_token = onboarding.write_onboarding_platform_token_secret
            original_begin = onboarding.begin_onboarding_provisioning
            original_start_codex = onboarding.start_codex_device_authorization
            try:
                onboarding.write_onboarding_platform_token_secret = lambda cfg, session_id, platform, token: "/tmp/bot-token"
                onboarding.write_onboarding_secret = lambda cfg, session_id, secret_name, secret: captured.update({"secret_name": secret_name, "secret": secret}) or "/tmp/org-provider.secret"
                onboarding.begin_onboarding_provisioning = (
                    lambda conn, cfg, updated, *, provider_secret_path: captured.update(
                        {
                            "provider_secret_path": provider_secret_path,
                            "provider_setup": (updated.get("answers") or {}).get("provider_setup"),
                        }
                    )
                    or {
                        **updated,
                        "answers": {
                            **(updated.get("answers") or {}),
                            "unix_user": "orgcodex",
                            "bot_platform": "discord",
                            "bot_username": "Guide",
                        },
                    }
                )
                onboarding.start_codex_device_authorization = lambda: (_ for _ in ()).throw(AssertionError("org-provided should not start user Codex auth"))

                replies = onboarding.process_onboarding_message(
                    cfg,
                    onboarding.IncomingMessage(
                        platform="discord",
                        chat_id="456",
                        sender_id="456",
                        text="bot-token",
                        sender_username="alex",
                        sender_display_name="Alex",
                    ),
                    validate_bot_token=lambda raw: onboarding.BotIdentity(bot_id="999", username="Guide", display_name="Guide"),
                )
            finally:
                onboarding.write_onboarding_secret = original_write_secret
                onboarding.write_onboarding_platform_token_secret = original_write_bot_token
                onboarding.begin_onboarding_provisioning = original_begin
                onboarding.start_codex_device_authorization = original_start_codex

            expect(captured["secret_name"] == "openai-codex-oauth", str(captured))
            expect(captured["secret"] == org_codex_secret, str(captured))
            provider_setup = captured["provider_setup"]
            expect(isinstance(provider_setup, dict), str(captured))
            expect(provider_setup["provider_id"] == "openai-codex", str(provider_setup))
            expect(provider_setup["model_id"] == "gpt-5.4", str(provider_setup))
            expect("Good. I have what I need." in replies[0].text, replies[0].text)
            print("PASS test_org_provided_secret_auto_stages_after_bot_token")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_telegram_chutes_model_prompt_uses_copyable_code_entities() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_telegram_model_copy_test")
    onboarding = load_module(ONBOARDING_PY, "arclink_onboarding_telegram_model_copy_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(root / "state"),
                "RUNTIME_DIR": str(root / "state" / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ARCLINK_DB_PATH": str(root / "state" / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(root / "state" / "agents"),
                "ARCLINK_CURATOR_DIR": str(root / "state" / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(root / "state" / "arclink-release.json"),
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ARCLINK_MCP_HOST": "127.0.0.1",
                "ARCLINK_MCP_PORT": "8282",
                "ARCLINK_MODEL_PRESET_CODEX": "openai:codex",
                "ARCLINK_MODEL_PRESET_OPUS": "anthropic:claude-opus",
                "ARCLINK_MODEL_PRESET_CHUTES": "chutes:model-router",
                "ARCLINK_CURATOR_CHANNELS": "telegram",
                "ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "1",
            },
        )

        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            desired_unix_user = "arclink-tg-model"
            try:
                pwd.getpwnam(desired_unix_user)
            except KeyError:
                pass
            else:
                desired_unix_user = "arclink-tg-model-01"

            def send(text: str):
                return onboarding.process_onboarding_message(
                    cfg,
                    onboarding.IncomingMessage(
                        platform="telegram",
                        chat_id="123",
                        sender_id="123",
                        text=text,
                        sender_username="alex",
                        sender_display_name="Alex",
                    ),
                    validate_bot_token=lambda raw: None,
                )

            send("/start")
            send("Build calmly")
            send(desired_unix_user)
            send("Joof")
            model_id_reply = send("1")[0]
            expect(model_id_reply.telegram_parse_mode == "Markdown", str(model_id_reply))
            expect("- `model-router`" in model_id_reply.text, model_id_reply.text)
            expect("- `moonshotai/Kimi-K2.6-TEE`" in model_id_reply.text, model_id_reply.text)
            expect("- `zai-org/GLM-5.1-TEE`" in model_id_reply.text, model_id_reply.text)

            status_reply = send("/status")[0]
            expect(status_reply.telegram_parse_mode == "Markdown", str(status_reply))
            expect("`moonshotai/Kimi-K2.6-TEE`" in status_reply.text, status_reply.text)

            invalid_reply = send("two words")[0]
            expect(invalid_reply.telegram_parse_mode == "Markdown", str(invalid_reply))
            expect("`moonshotai/Kimi-K2.6-TEE`" in invalid_reply.text, invalid_reply.text)

            session = control.find_active_onboarding_session(conn, platform="telegram", sender_id="123")
            expect(onboarding.session_prompt_telegram_parse_mode(session) == "Markdown", str(session))
            print("PASS test_telegram_chutes_model_prompt_uses_copyable_code_entities")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_chat_onboarding_auto_provision_does_not_queue_redundant_request_approval() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_onboarding_auto_provision_notice_test")
    onboarding = load_module(ONBOARDING_PY, "arclink_onboarding_auto_provision_notice_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(root / "state"),
                "RUNTIME_DIR": str(root / "state" / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ARCLINK_DB_PATH": str(root / "state" / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(root / "state" / "agents"),
                "ARCLINK_CURATOR_DIR": str(root / "state" / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(root / "state" / "arclink-release.json"),
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ARCLINK_MCP_HOST": "127.0.0.1",
                "ARCLINK_MCP_PORT": "8282",
                "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "telegram",
                "OPERATOR_NOTIFY_CHANNEL_ID": "42",
                "ARCLINK_CURATOR_CHANNELS": "telegram",
                "ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "1",
                "ARCLINK_MODEL_PRESET_CHUTES": "chutes:model-router",
            },
        )

        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            session = control.start_onboarding_session(
                conn,
                cfg,
                platform="telegram",
                chat_id="100",
                sender_id="100",
                sender_username="alex",
                sender_display_name="Alex",
            )
            session = control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-provider-credential",
                answers={
                    "full_name": "Alex",
                    "unix_user": "tg-auto-provision",
                    "bot_platform": "telegram",
                    "model_preset": "chutes",
                    "model_id": "model-router",
                    "reasoning_effort": "medium",
                },
                approved_by_actor="@operator",
            )

            updated = onboarding.begin_onboarding_provisioning(
                conn,
                cfg,
                session,
                provider_secret_path=str(root / "secret"),
            )
            request_id = str(updated.get("linked_request_id") or "")
            expect(request_id.startswith("req_"), str(updated))

            request_row = conn.execute(
                "SELECT status FROM bootstrap_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            expect(request_row is not None and request_row["status"] == "approved", str(dict(request_row) if request_row else {}))

            rows = conn.execute(
                "SELECT message, extra_json FROM notification_outbox WHERE target_kind = 'operator' ORDER BY id"
            ).fetchall()
            messages = [str(row["message"] or "") for row in rows]
            expect(
                not any("is requesting enrollment" in message and "tap Approve / Deny" in message for message in messages),
                str(messages),
            )
            expect(any("Approved enrollment request" in message for message in messages), str(messages))
            expect(
                not any(f"arclink:request:approve:{request_id}" in str(row["extra_json"] or "") for row in rows),
                str([dict(row) for row in rows]),
            )
            print("PASS test_chat_onboarding_auto_provision_does_not_queue_redundant_request_approval")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_denied_onboarding_deletes_staged_bot_and_provider_secrets() -> None:
    control = load_module(CONTROL_PY, "arclink_control_onboarding_deny_secret_cleanup_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(root / "state"),
                "RUNTIME_DIR": str(root / "state" / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ARCLINK_DB_PATH": str(root / "state" / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(root / "state" / "agents"),
                "ARCLINK_CURATOR_DIR": str(root / "state" / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(root / "state" / "arclink-release.json"),
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ARCLINK_MCP_HOST": "127.0.0.1",
                "ARCLINK_MCP_PORT": "8282",
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            session = control.start_onboarding_session(
                conn,
                cfg,
                platform="discord",
                chat_id="456",
                sender_id="456",
                sender_username="alex",
                sender_display_name="Alex",
            )
            bot_secret = Path(control.write_onboarding_platform_token_secret(cfg, str(session["session_id"]), "discord", "bot-token"))
            provider_secret = Path(control.write_onboarding_secret(cfg, str(session["session_id"]), "chutes_api_key", "provider-token"))
            control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-bot-token",
                pending_bot_token_path=str(bot_secret),
                answers={"pending_provider_secret_path": str(provider_secret)},
            )
            denied = control.deny_onboarding_session(conn, session_id=str(session["session_id"]), actor="operator", reason="not now")
            expect(str(denied.get("state") or "") == "denied", str(denied))
            expect(not bot_secret.exists(), f"bot secret should be deleted: {bot_secret}")
            expect(not provider_secret.exists(), f"provider secret should be deleted: {provider_secret}")
            refreshed = control.get_onboarding_session(conn, str(session["session_id"]), redact_secrets=False)
            expect(not str(refreshed.get("pending_bot_token_path") or "").strip(), str(refreshed))
            expect(not str((refreshed.get("answers") or {}).get("pending_provider_secret_path") or "").strip(), str(refreshed))
            print("PASS test_denied_onboarding_deletes_staged_bot_and_provider_secrets")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    old_env = os.environ.copy()
    try:
        for key in list(os.environ):
            if key.startswith(("ARCLINK", "ANTHROPIC", "CHUTES", "CLAUDE", "OPENAI")):
                os.environ.pop(key, None)
        test_discord_prompt_and_operator_review_reflect_primary_control_channel()
        test_onboarding_intake_asks_purpose_before_unix_and_skips_platform_question()
        test_chat_onboarding_reserves_unix_user_before_provisioning()
        test_onboarding_offers_safe_org_profile_match_without_forcing_names()
        test_onboarding_respects_disabled_org_profile_roster_prompt()
        test_onboarding_uses_resolved_sender_display_name_without_reasking()
        test_shared_team_key_prompt_offers_default_reply_for_chutes()
        test_shared_team_key_default_reply_uses_configured_secret()
        test_anthropic_opus_prompt_and_browser_auth_flow_require_oauth()
        test_anthropic_callback_exchange_returns_claude_code_credentials_payload()
        test_onboarding_model_picker_is_chutes_first_and_collects_reasoning()
        test_org_provided_model_choice_skips_user_model_and_credential_prompts()
        test_org_provided_secret_auto_stages_after_bot_token()
        test_telegram_chutes_model_prompt_uses_copyable_code_entities()
        test_chat_onboarding_auto_provision_does_not_queue_redundant_request_approval()
        test_denied_onboarding_deletes_staged_bot_and_provider_secrets()
        print("PASS all 16 onboarding prompt regression tests")
        return 0
    finally:
        os.environ.clear()
        os.environ.update(old_env)


if __name__ == "__main__":
    raise SystemExit(main())
