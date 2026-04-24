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


def config_values(root: Path) -> dict[str, str]:
    return {
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
        "ALMANAC_NOTION_WEBHOOK_HOST": "127.0.0.1",
        "ALMANAC_NOTION_WEBHOOK_PORT": "8283",
        "ALMANAC_SSOT_NOTION_SPACE_URL": "https://www.notion.so/Acme-SSOT-1234567890abcdef1234567890abcdef",
        "ALMANAC_MODEL_PRESET_CODEX": "openai:codex",
        "ALMANAC_MODEL_PRESET_OPUS": "anthropic:claude-opus",
        "ALMANAC_MODEL_PRESET_CHUTES": "chutes:model-router",
        "ALMANAC_CURATOR_CHANNELS": "tui-only,telegram,discord",
        "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "1",
        "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED": "1",
        "ENABLE_TAILSCALE_SERVE": "1",
        "ENABLE_NEXTCLOUD": "1",
        "TAILSCALE_DNS_NAME": "kor.tail77f45e.ts.net",
        "NEXTCLOUD_TRUSTED_DOMAIN": "kor.tail77f45e.ts.net",
    }


def insert_agent(control, conn, *, agent_id: str, unix_user: str, hermes_home: Path) -> None:
    now = control.utc_now_iso()
    conn.execute(
        """
        INSERT INTO agents (
          agent_id, role, unix_user, display_name, status, hermes_home, manifest_path,
          archived_state_path, model_preset, model_string, channels_json,
          allowed_mcps_json, home_channel_json, operator_notify_channel_json,
          created_at, last_enrolled_at
        ) VALUES (?, 'user', ?, ?, 'active', ?, ?, NULL, 'codex', 'openai:codex', '["tui-only","telegram"]', '[]', '{}', '{}', ?, ?)
        """,
        (agent_id, unix_user, unix_user, str(hermes_home), str(hermes_home / "manifest.json"), now, now),
    )
    conn.commit()


def bootstrap_completed_session(control, cfg, conn, *, platform: str = "telegram"):
    session = control.start_onboarding_session(
        conn,
        cfg,
        platform=platform,
        chat_id="123456",
        sender_id="123456",
        sender_username="sirouk",
        sender_display_name="Chris",
    )
    session = control.save_onboarding_session(
        conn,
        session_id=str(session["session_id"]),
        state="completed",
        linked_agent_id="agent-sirouk",
        answers={
            "unix_user": pwd.getpwuid(os.getuid()).pw_name,
            "bot_platform": platform,
            "bot_username": "Jeef",
            "preferred_bot_name": "Jeef",
            "full_name": "Chris",
        },
    )
    return session


def test_verify_notion_command_reopens_latest_completed_session() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_onboarding_notion_resume_test")
    onboarding = load_module(ONBOARDING_PY, "almanac_onboarding_notion_resume_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            bootstrap_completed_session(control, cfg, conn)
            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="telegram",
                    chat_id="123456",
                    sender_id="123456",
                    sender_username="sirouk",
                    sender_display_name="Chris",
                    text="/verify-notion",
                ),
                validate_bot_token=lambda raw: None,
            )
            expect(len(replies) == 1, str(replies))
            expect("Notion" in replies[0].text, replies[0].text)
            resumed = control.find_active_onboarding_session(conn, platform="telegram", sender_id="123456", redact_secrets=False)
            expect(resumed is not None, "expected resumed onboarding session")
            expect(str(resumed.get("state") or "") == "awaiting-notion-access", str(resumed))
            print("PASS test_verify_notion_command_reopens_latest_completed_session")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_awaiting_notion_access_skip_returns_completion_bundle() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_onboarding_notion_skip_test")
    onboarding = load_module(ONBOARDING_PY, "almanac_onboarding_notion_skip_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            unix_user = pwd.getpwuid(os.getuid()).pw_name
            hermes_home = root / "homes" / unix_user / ".local" / "share" / "almanac-agent" / "hermes-home"
            (hermes_home / "state").mkdir(parents=True, exist_ok=True)
            (hermes_home / "state" / "almanac-web-access.json").write_text(
                json.dumps(
                    {
                        "unix_user": unix_user,
                        "username": unix_user,
                        "password": "shared-secret",
                        "dashboard_url": "https://kor.tail77f45e.ts.net:30011/",
                        "code_url": "https://kor.tail77f45e.ts.net:40011/",
                    }
                ),
                encoding="utf-8",
            )
            insert_agent(control, conn, agent_id="agent-sirouk", unix_user=unix_user, hermes_home=hermes_home)
            session = bootstrap_completed_session(control, cfg, conn)
            session = control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-notion-access",
            )
            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="telegram",
                    chat_id="123456",
                    sender_id="123456",
                    sender_username="sirouk",
                    sender_display_name="Chris",
                    text="skip",
                ),
                validate_bot_token=lambda raw: None,
            )
            expect(len(replies) == 1, str(replies))
            expect("Shared Notion writes: read-only" in replies[0].text, replies[0].text)
            expect(replies[0].telegram_reply_markup is not None, str(replies[0]))
            refreshed = control.get_onboarding_session(conn, str(session["session_id"]), redact_secrets=False)
            expect(str(refreshed.get("state") or "") == "completed", str(refreshed))
            expect(bool((refreshed.get("answers") or {}).get("notion_verification_skipped")), str(refreshed))
            print("PASS test_awaiting_notion_access_skip_returns_completion_bundle")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_awaiting_notion_access_ready_moves_to_email_step() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_onboarding_notion_access_ready_test")
    onboarding = load_module(ONBOARDING_PY, "almanac_onboarding_notion_access_ready_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            unix_user = pwd.getpwuid(os.getuid()).pw_name
            session = bootstrap_completed_session(control, cfg, conn)
            session = control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-notion-access",
                answers={"unix_user": unix_user},
            )
            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="telegram",
                    chat_id="123456",
                    sender_id="123456",
                    sender_username="sirouk",
                    sender_display_name="Chris",
                    text="ready",
                ),
                validate_bot_token=lambda raw: None,
            )
            expect(len(replies) == 1, str(replies))
            expect("Notion email" in replies[0].text, replies[0].text)
            refreshed = control.get_onboarding_session(conn, str(session["session_id"]), redact_secrets=False)
            expect(str(refreshed.get("state") or "") == "awaiting-notion-email", str(refreshed))
            print("PASS test_awaiting_notion_access_ready_moves_to_email_step")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_awaiting_notion_email_starts_claim_and_moves_to_verification() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_onboarding_notion_claim_test")
    onboarding = load_module(ONBOARDING_PY, "almanac_onboarding_notion_claim_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            unix_user = pwd.getpwuid(os.getuid()).pw_name
            session = bootstrap_completed_session(control, cfg, conn)
            session = control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-notion-email",
                answers={"unix_user": unix_user},
            )

            def fake_start_claim(conn_arg, *, session_id: str, agent_id: str, unix_user: str, claimed_notion_email: str, urlopen_fn=None):
                expect(session_id == str(session["session_id"]), session_id)
                expect(agent_id == "agent-sirouk", agent_id)
                expect(unix_user == pwd.getpwuid(os.getuid()).pw_name, unix_user)
                expect(claimed_notion_email == "chris@example.com", claimed_notion_email)
                return {
                    "claim_id": "nclaim_test",
                    "claimed_notion_email": "chris@example.com",
                    "notion_page_url": "https://www.notion.so/claim-page",
                    "expires_at": "2026-04-21T00:00:00+00:00",
                }

            onboarding.start_notion_identity_claim = fake_start_claim
            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="telegram",
                    chat_id="123456",
                    sender_id="123456",
                    sender_username="sirouk",
                    sender_display_name="Chris",
                    text="chris@example.com",
                ),
                validate_bot_token=lambda raw: None,
            )
            expect(len(replies) == 1, str(replies))
            expect("https://www.notion.so/claim-page" in replies[0].text, replies[0].text)
            refreshed = control.get_onboarding_session(conn, str(session["session_id"]), redact_secrets=False)
            expect(str(refreshed.get("state") or "") == "awaiting-notion-verification", str(refreshed))
            answers = refreshed.get("answers") or {}
            expect(str(answers.get("notion_claim_id") or "") == "nclaim_test", str(answers))
            expect(str(answers.get("notion_claim_email") or "") == "chris@example.com", str(answers))
            print("PASS test_awaiting_notion_email_starts_claim_and_moves_to_verification")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_verify_notion_command_reissues_pending_claim_with_same_email() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_onboarding_notion_reissue_claim_test")
    onboarding = load_module(ONBOARDING_PY, "almanac_onboarding_notion_reissue_claim_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            unix_user = pwd.getpwuid(os.getuid()).pw_name
            session = bootstrap_completed_session(control, cfg, conn)
            session = control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-notion-verification",
                answers={
                    "unix_user": unix_user,
                    "notion_claim_email": "chris@example.com",
                    "notion_claim_id": "nclaim_old",
                    "notion_claim_url": "https://www.notion.so/claim-old",
                    "notion_claim_expires_at": "2026-04-21T00:00:00+00:00",
                },
            )

            def fake_start_claim(conn_arg, *, session_id: str, agent_id: str, unix_user: str, claimed_notion_email: str, urlopen_fn=None):
                expect(session_id == str(session["session_id"]), session_id)
                expect(agent_id == "agent-sirouk", agent_id)
                expect(unix_user == pwd.getpwuid(os.getuid()).pw_name, unix_user)
                expect(claimed_notion_email == "chris@example.com", claimed_notion_email)
                return {
                    "claim_id": "nclaim_fresh",
                    "claimed_notion_email": "chris@example.com",
                    "notion_page_url": "https://www.notion.so/claim-fresh",
                    "expires_at": "2026-04-22T00:00:00+00:00",
                }

            onboarding.start_notion_identity_claim = fake_start_claim
            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="telegram",
                    chat_id="123456",
                    sender_id="123456",
                    sender_username="sirouk",
                    sender_display_name="Chris",
                    text="/verify-notion",
                ),
                validate_bot_token=lambda raw: None,
            )
            expect(len(replies) == 1, str(replies))
            expect("fresh Notion verification page" in replies[0].text, replies[0].text)
            expect("https://www.notion.so/claim-fresh" in replies[0].text, replies[0].text)
            refreshed = control.get_onboarding_session(conn, str(session["session_id"]), redact_secrets=False)
            expect(str(refreshed.get("state") or "") == "awaiting-notion-verification", str(refreshed))
            answers = refreshed.get("answers") or {}
            expect(str(answers.get("notion_claim_email") or "") == "chris@example.com", str(answers))
            expect(str(answers.get("notion_claim_id") or "") == "nclaim_fresh", str(answers))
            expect(str(answers.get("notion_claim_url") or "") == "https://www.notion.so/claim-fresh", str(answers))
            print("PASS test_verify_notion_command_reissues_pending_claim_with_same_email")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_verify_notion_command_reissues_expired_claim_with_same_email() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_onboarding_notion_expired_claim_test")
    onboarding = load_module(ONBOARDING_PY, "almanac_onboarding_notion_expired_claim_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            unix_user = pwd.getpwuid(os.getuid()).pw_name
            hermes_home = root / "homes" / unix_user / ".local" / "share" / "almanac-agent" / "hermes-home"
            insert_agent(control, conn, agent_id="agent-sirouk", unix_user=unix_user, hermes_home=hermes_home)
            session = bootstrap_completed_session(control, cfg, conn)
            session = control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-notion-verification",
                answers={
                    "unix_user": unix_user,
                    "notion_claim_email": "chris@example.com",
                    "notion_claim_id": "nclaim_expired",
                    "notion_claim_url": "https://www.notion.so/claim-page",
                    "notion_claim_expires_at": "2026-04-21T00:00:00+00:00",
                },
            )
            now = control.utc_now_iso()
            conn.execute(
                """
                INSERT INTO notion_identity_claims (
                  claim_id, session_id, agent_id, unix_user, claimed_notion_email,
                  notion_page_id, notion_page_url, status, failure_reason,
                  verified_notion_user_id, verified_notion_email, created_at, updated_at, expires_at, verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'expired', 'claim expired before verification', '', '', ?, ?, ?, NULL)
                """,
                (
                    "nclaim_expired",
                    str(session["session_id"]),
                    "agent-sirouk",
                    unix_user,
                    "chris@example.com",
                    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "https://www.notion.so/claim-page",
                    now,
                    now,
                    now,
                ),
            )
            conn.commit()

            def fake_start_claim(conn_arg, *, session_id: str, agent_id: str, unix_user: str, claimed_notion_email: str, urlopen_fn=None):
                expect(session_id == str(session["session_id"]), session_id)
                expect(agent_id == "agent-sirouk", agent_id)
                expect(unix_user == pwd.getpwuid(os.getuid()).pw_name, unix_user)
                expect(claimed_notion_email == "chris@example.com", claimed_notion_email)
                return {
                    "claim_id": "nclaim_expired_fresh",
                    "claimed_notion_email": "chris@example.com",
                    "notion_page_url": "https://www.notion.so/claim-fresh-expired",
                    "expires_at": "2026-04-22T00:00:00+00:00",
                }

            onboarding.start_notion_identity_claim = fake_start_claim

            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="telegram",
                    chat_id="123456",
                    sender_id="123456",
                    sender_username="sirouk",
                    sender_display_name="Chris",
                    text="/verify-notion",
                ),
                validate_bot_token=lambda raw: None,
            )
            expect(len(replies) == 1, str(replies))
            expect("fresh Notion verification page" in replies[0].text, replies[0].text)
            expect("https://www.notion.so/claim-fresh-expired" in replies[0].text, replies[0].text)
            refreshed = control.get_onboarding_session(conn, str(session["session_id"]), redact_secrets=False)
            expect(str(refreshed.get("state") or "") == "awaiting-notion-verification", str(refreshed))
            answers = refreshed.get("answers") or {}
            expect(str(answers.get("notion_claim_id") or "") == "nclaim_expired_fresh", str(answers))
            expect(str(answers.get("notion_claim_email") or "") == "chris@example.com", str(answers))
            print("PASS test_verify_notion_command_reissues_expired_claim_with_same_email")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_awaiting_notion_verification_skip_marks_claim_and_returns_completion_bundle() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_onboarding_notion_skip_claim_test")
    onboarding = load_module(ONBOARDING_PY, "almanac_onboarding_notion_skip_claim_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            unix_user = pwd.getpwuid(os.getuid()).pw_name
            hermes_home = root / "homes" / unix_user / ".local" / "share" / "almanac-agent" / "hermes-home"
            (hermes_home / "state").mkdir(parents=True, exist_ok=True)
            (hermes_home / "state" / "almanac-web-access.json").write_text(
                json.dumps(
                    {
                        "unix_user": unix_user,
                        "username": unix_user,
                        "password": "shared-secret",
                        "dashboard_url": "https://kor.tail77f45e.ts.net:30011/",
                        "code_url": "https://kor.tail77f45e.ts.net:40011/",
                    }
                ),
                encoding="utf-8",
            )
            insert_agent(control, conn, agent_id="agent-sirouk", unix_user=unix_user, hermes_home=hermes_home)
            session = bootstrap_completed_session(control, cfg, conn)
            session = control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-notion-verification",
                answers={
                    "unix_user": unix_user,
                    "notion_claim_id": "nclaim_skip",
                    "notion_claim_email": "chris@example.com",
                    "notion_claim_url": "https://www.notion.so/claim-page",
                    "notion_claim_expires_at": "2026-04-21T00:00:00+00:00",
                },
            )
            now = control.utc_now_iso()
            conn.execute(
                """
                INSERT INTO notion_identity_claims (
                  claim_id, session_id, agent_id, unix_user, claimed_notion_email,
                  notion_page_id, notion_page_url, status, failure_reason,
                  verified_notion_user_id, verified_notion_email, created_at, updated_at, expires_at, verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', '', '', '', ?, ?, ?, NULL)
                """,
                (
                    "nclaim_skip",
                    str(session["session_id"]),
                    "agent-sirouk",
                    unix_user,
                    "chris@example.com",
                    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "https://www.notion.so/claim-page",
                    now,
                    now,
                    "2026-04-21T00:00:00+00:00",
                ),
            )
            conn.commit()

            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="telegram",
                    chat_id="123456",
                    sender_id="123456",
                    sender_username="sirouk",
                    sender_display_name="Chris",
                    text="skip",
                ),
                validate_bot_token=lambda raw: None,
            )
            expect(len(replies) == 1, str(replies))
            expect("Shared Notion writes: read-only" in replies[0].text, replies[0].text)
            refreshed = control.get_onboarding_session(conn, str(session["session_id"]), redact_secrets=False)
            expect(str(refreshed.get("state") or "") == "completed", str(refreshed))
            claim = control.get_notion_identity_claim(conn, claim_id="nclaim_skip")
            expect(claim is not None and str(claim.get("status") or "") == "skipped", str(claim))
            print("PASS test_awaiting_notion_verification_skip_marks_claim_and_returns_completion_bundle")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_verify_notion_command_reopens_latest_completed_session()
    test_awaiting_notion_access_skip_returns_completion_bundle()
    test_awaiting_notion_access_ready_moves_to_email_step()
    test_awaiting_notion_email_starts_claim_and_moves_to_verification()
    test_verify_notion_command_reissues_pending_claim_with_same_email()
    test_verify_notion_command_reissues_expired_claim_with_same_email()
    test_awaiting_notion_verification_skip_marks_claim_and_returns_completion_bundle()
    print("PASS all 7 onboarding notion tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
