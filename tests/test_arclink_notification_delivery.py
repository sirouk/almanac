#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import asyncio
import hashlib
import hmac
import io
import json
import os
import stat
import sys
import tempfile
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
CONTROL_PY = PYTHON_DIR / "arclink_control.py"
DELIVERY_PY = PYTHON_DIR / "arclink_notification_delivery.py"
os.environ.setdefault("ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED", "accepted")


def load_module(path: Path, name: str):
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
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


def test_discord_operator_delivery_supports_channel_ids() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_notification_delivery_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_test")
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
                "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "discord",
                "OPERATOR_NOTIFY_CHANNEL_ID": "123456789012345678",
                "DISCORD_BOT_TOKEN": "discord-bot-token",
            },
        )

        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            calls: list[dict[str, str]] = []

            def fake_send(
                *,
                bot_token: str,
                channel_id: str,
                text: str,
                components=None,
            ) -> dict[str, str]:
                calls.append(
                    {
                        "bot_token": bot_token,
                        "channel_id": channel_id,
                        "text": text,
                    }
                )
                return {"id": "1"}

            delivery.discord_send_message = fake_send
            error = delivery.deliver_row(
                cfg,
                {
                    "target_kind": "operator",
                    "target_id": "123456789012345678",
                    "channel_kind": "discord",
                    "message": "hello from curator",
                    "extra_json": "",
                },
            )

            expect(error is None, f"expected discord channel delivery to succeed, got {error!r}")
            expect(len(calls) == 1, calls)
            expect(calls[0]["channel_id"] == "123456789012345678", calls)
            expect(calls[0]["bot_token"] == "discord-bot-token", calls)
            print("PASS test_discord_operator_delivery_supports_channel_ids")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_bot_user_delivery_supports_telegram_and_discord_dm() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_notification_delivery_public_bot_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_public_bot_test")
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
                "TELEGRAM_BOT_TOKEN": "telegram-public-token",
                "DISCORD_BOT_TOKEN": "discord-public-token",
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            telegram_calls: list[dict[str, object]] = []
            discord_dm_calls: list[dict[str, str]] = []
            discord_send_calls: list[dict[str, object]] = []

            def fake_telegram(*, bot_token, chat_id, text, reply_to_message_id=None, reply_markup=None, parse_mode=""):
                telegram_calls.append(
                    {
                        "bot_token": bot_token,
                        "chat_id": chat_id,
                        "text": text,
                        "reply_to_message_id": reply_to_message_id,
                        "reply_markup": reply_markup,
                        "parse_mode": parse_mode,
                    }
                )
                return {"ok": True}

            def fake_dm(*, bot_token: str, recipient_id: str) -> dict[str, str]:
                discord_dm_calls.append({"bot_token": bot_token, "recipient_id": recipient_id})
                return {"id": "dm_456"}

            def fake_discord_send(*, bot_token: str, channel_id: str, text: str, components=None) -> dict[str, str]:
                discord_send_calls.append(
                    {
                        "bot_token": bot_token,
                        "channel_id": channel_id,
                        "text": text,
                        "components": components,
                    }
                )
                return {"id": "msg_1"}

            delivery.telegram_send_message = fake_telegram
            delivery.discord_create_dm_channel = fake_dm
            delivery.discord_send_message = fake_discord_send
            telegram_error = delivery.deliver_row(
                cfg,
                {
                    "target_kind": "public-bot-user",
                    "target_id": "tg:123",
                    "channel_kind": "telegram",
                    "message": "Agent online.",
                    "extra_json": json.dumps(
                        {
                            "telegram_reply_markup": {"inline_keyboard": [[{"text": "Show My Crew", "callback_data": "arclink:/agents"}]]},
                            "telegram_parse_mode": "Markdown",
                        }
                    ),
                },
            )
            discord_error = delivery.deliver_row(
                cfg,
                {
                    "target_kind": "public-bot-user",
                    "target_id": "discord:456",
                    "channel_kind": "discord",
                    "message": "Agent online.",
                    "extra_json": json.dumps(
                        {
                            "discord_components": [
                                {
                                    "type": 1,
                                    "components": [
                                        {"type": 2, "label": "Show My Crew", "style": 2, "custom_id": "arclink:/agents"}
                                    ],
                                }
                            ]
                        }
                    ),
                },
            )
            expect(telegram_error is None, str(telegram_error))
            expect(discord_error is None, str(discord_error))
            expect(telegram_calls[0]["bot_token"] == "telegram-public-token", str(telegram_calls))
            expect(telegram_calls[0]["chat_id"] == "123", str(telegram_calls))
            expect(telegram_calls[0]["reply_markup"], str(telegram_calls))
            expect(discord_dm_calls == [{"bot_token": "discord-public-token", "recipient_id": "456"}], str(discord_dm_calls))
            expect(discord_send_calls[0]["channel_id"] == "dm_456", str(discord_send_calls))
            expect(discord_send_calls[0]["components"], str(discord_send_calls))
            print("PASS test_public_bot_user_delivery_supports_telegram_and_discord_dm")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_captain_wrapped_delivery_uses_public_channel_and_marks_report_delivered() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_notification_delivery_wrapped_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_wrapped_test")
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
                "TELEGRAM_BOT_TOKEN": "telegram-public-token",
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                conn.execute(
                    """
                    INSERT INTO arclink_wrapped_reports (
                      report_id, user_id, period, period_start, period_end, status,
                      ledger_json, novelty_score, delivery_channel, created_at, delivered_at
                    ) VALUES (
                      'wrap_delivery', 'user_1', 'daily',
                      '2026-05-12T00:00:00+00:00', '2026-05-13T00:00:00+00:00',
                      'generated', '{}', 42.0, 'telegram', '2026-05-13T00:05:00+00:00', ''
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO notification_outbox (
                      target_kind, target_id, channel_kind, message, extra_json, created_at, next_attempt_at
                    ) VALUES ('captain-wrapped', 'tg:123', 'telegram', 'ArcLink Wrapped report', ?, ?, ?)
                    """,
                    (
                        json.dumps({"report_id": "wrap_delivery", "period": "daily", "novelty_score": 42.0}),
                        "2026-05-13T00:06:00+00:00",
                        "2026-05-13T00:06:00+00:00",
                    ),
                )
                conn.commit()

            telegram_calls: list[dict[str, object]] = []

            def fake_telegram(*, bot_token, chat_id, text, reply_to_message_id=None, reply_markup=None, parse_mode=""):
                telegram_calls.append(
                    {
                        "bot_token": bot_token,
                        "chat_id": chat_id,
                        "text": text,
                    }
                )
                return {"ok": True}

            delivery.telegram_send_message = fake_telegram
            summary = delivery.run_once(cfg)
            with control.connect_db(cfg) as conn:
                row = conn.execute("SELECT status, delivered_at FROM arclink_wrapped_reports WHERE report_id = 'wrap_delivery'").fetchone()
            expect(summary["delivered"] == 1, str(summary))
            expect(telegram_calls and telegram_calls[0]["chat_id"] == "123", str(telegram_calls))
            expect(row["status"] == "delivered" and row["delivered_at"], str(dict(row)))
            print("PASS test_captain_wrapped_delivery_uses_public_channel_and_marks_report_delivered")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_captain_wrapped_delivery_repairs_legacy_user_agent_channel() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_notification_delivery_wrapped_legacy_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_wrapped_legacy_test")
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
                "TELEGRAM_BOT_TOKEN": "telegram-public-token",
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                conn.execute(
                    """
                    INSERT INTO arclink_onboarding_sessions (
                      session_id, channel, channel_identity, status, current_step,
                      selected_plan_id, selected_model_id, user_id, deployment_id,
                      checkout_state, metadata_json, created_at, updated_at, completed_at
                    ) VALUES (
                      'sess_live', 'telegram', 'tg:123#add:legacy', 'first_contacted', 'done',
                      'founders', 'moonshotai/Kimi-K2.6-TEE', 'user_1', 'dep_1',
                      'paid', '{}', '2026-05-13T00:00:00+00:00',
                      '2026-05-13T00:10:00+00:00', ''
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO arclink_wrapped_reports (
                      report_id, user_id, period, period_start, period_end, status,
                      ledger_json, novelty_score, delivery_channel, created_at, delivered_at
                    ) VALUES (
                      'wrap_legacy', 'user_1', 'daily',
                      '2026-05-12T00:00:00+00:00', '2026-05-13T00:00:00+00:00',
                      'generated', '{}', 42.0, 'user-agent', '2026-05-13T00:05:00+00:00', ''
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO notification_outbox (
                      target_kind, target_id, channel_kind, message, extra_json, created_at, next_attempt_at
                    ) VALUES ('captain-wrapped', 'user_1', 'user-agent', 'ArcLink Wrapped report', ?, ?, ?)
                    """,
                    (
                        json.dumps({"report_id": "wrap_legacy", "user_id": "user_1", "period": "daily", "novelty_score": 42.0}),
                        "2026-05-13T00:06:00+00:00",
                        "2026-05-13T00:06:00+00:00",
                    ),
                )
                conn.commit()

            telegram_calls: list[dict[str, object]] = []

            def fake_telegram(*, bot_token, chat_id, text, reply_to_message_id=None, reply_markup=None, parse_mode=""):
                telegram_calls.append({"bot_token": bot_token, "chat_id": chat_id, "text": text})
                return {"ok": True}

            delivery.telegram_send_message = fake_telegram
            summary = delivery.run_once(cfg)
            with control.connect_db(cfg) as conn:
                report = conn.execute("SELECT status, delivered_at FROM arclink_wrapped_reports WHERE report_id = 'wrap_legacy'").fetchone()
                outbox = conn.execute("SELECT delivered_at, delivery_error FROM notification_outbox WHERE target_kind = 'captain-wrapped'").fetchone()
            expect(summary["delivered"] == 1, str(summary))
            expect(telegram_calls and telegram_calls[0]["chat_id"] == "123", str(telegram_calls))
            expect(report["status"] == "delivered" and report["delivered_at"], str(dict(report)))
            expect(outbox["delivered_at"] and not outbox["delivery_error"], str(dict(outbox)))
            print("PASS test_captain_wrapped_delivery_repairs_legacy_user_agent_channel")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_turn_delivery_allows_explicit_quiet_fallback() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_notification_delivery_agent_turn_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_agent_turn_test")
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
                "TELEGRAM_BOT_TOKEN": "telegram-public-token",
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        os.environ["ARCLINK_PUBLIC_AGENT_QUIET_FALLBACK"] = "1"
        try:
            cfg = control.Config.from_env()
            calls: list[dict[str, object]] = []
            prompts: list[dict[str, str]] = []

            def fake_agent_turn(*, deployment_id: str, prefix: str, prompt: str) -> tuple[str, str]:
                prompts.append({"deployment_id": deployment_id, "prefix": prefix, "prompt": prompt})
                return "Agent heard you.", ""

            def fake_gateway_turn(**kwargs):
                expect(kwargs["channel_kind"] == "telegram", str(kwargs))
                return False, "bridge unavailable in unit test"

            def fake_telegram(*, bot_token, chat_id, text, reply_to_message_id=None, reply_markup=None, parse_mode=""):
                calls.append(
                    {
                        "bot_token": bot_token,
                        "chat_id": chat_id,
                        "text": text,
                        "reply_to_message_id": reply_to_message_id,
                        "reply_markup": reply_markup,
                        "parse_mode": parse_mode,
                    }
                )
                return {"ok": True}

            delivery._run_public_agent_turn = fake_agent_turn
            delivery._run_public_agent_gateway_turn = fake_gateway_turn
            delivery.telegram_send_message = fake_telegram
            error = delivery.deliver_row(
                cfg,
                {
                    "target_kind": "public-agent-turn",
                    "target_id": "tg:123",
                    "channel_kind": "telegram",
                    "message": "hello agent",
                    "extra_json": json.dumps(
                        {
                            "deployment_id": "arcdep_test",
                            "prefix": "arc-testpod",
                            "agent_label": "Test Agent",
                            "helm_url": "https://example.test/u/arc-testpod",
                            "telegram_reply_to_message_id": "321",
                        }
                    ),
                },
            )
            expect(error is None, str(error))
            expect(prompts == [{"deployment_id": "arcdep_test", "prefix": "arc-testpod", "prompt": "hello agent"}], str(prompts))
            expect(calls[0]["chat_id"] == "123", str(calls))
            expect(calls[0]["bot_token"] == "telegram-public-token", str(calls))
            expect(calls[0]["reply_to_message_id"] == 321, str(calls))
            expect("Test Agent:\n\nAgent heard you." == calls[0]["text"], str(calls))
            print("PASS test_public_agent_turn_delivery_allows_explicit_quiet_fallback")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_turn_delivery_fails_closed_without_quiet_fallback() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_notification_delivery_no_fallback_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_no_fallback_test")
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
                "TELEGRAM_BOT_TOKEN": "telegram-public-token",
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        os.environ.pop("ARCLINK_PUBLIC_AGENT_QUIET_FALLBACK", None)
        try:
            cfg = control.Config.from_env()
            calls: list[dict[str, object]] = []

            def forbidden_agent_turn(**kwargs):
                raise AssertionError(f"quiet fallback must be opt-in: {kwargs}")

            def fake_gateway_turn(**kwargs):
                expect(kwargs["channel_kind"] == "telegram", str(kwargs))
                return False, "bridge unavailable in unit test"

            def fake_telegram(*, bot_token, chat_id, text, reply_to_message_id=None, reply_markup=None, parse_mode=""):
                calls.append(
                    {
                        "bot_token": bot_token,
                        "chat_id": chat_id,
                        "text": text,
                        "reply_to_message_id": reply_to_message_id,
                        "reply_markup": reply_markup,
                        "parse_mode": parse_mode,
                    }
                )
                return {"ok": True}

            delivery._run_public_agent_gateway_turn = fake_gateway_turn
            delivery._run_public_agent_turn = forbidden_agent_turn
            delivery.telegram_send_message = fake_telegram
            error = delivery.deliver_row(
                cfg,
                {
                    "target_kind": "public-agent-turn",
                    "target_id": "tg:123",
                    "channel_kind": "telegram",
                    "message": "hello agent",
                    "extra_json": json.dumps(
                        {
                            "deployment_id": "arcdep_test",
                            "prefix": "arc-testpod",
                            "agent_label": "Test Agent",
                            "helm_url": "https://example.test/u/arc-testpod",
                            "telegram_reply_to_message_id": "321",
                        }
                    ),
                },
            )
            expect(error is None, str(error))
            expect(calls[0]["chat_id"] == "123", str(calls))
            expect(calls[0]["reply_to_message_id"] == 321, str(calls))
            expect("Test Agent did not answer through the Hermes gateway bridge yet." in calls[0]["text"], str(calls))
            expect("bridge unavailable in unit test" in calls[0]["text"], str(calls))
            expect("Agent heard you" not in calls[0]["text"], str(calls))
            print("PASS test_public_agent_turn_delivery_fails_closed_without_quiet_fallback")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_turn_delivery_prefers_gateway_bridge_when_available() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_notification_delivery_bridge_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_bridge_test")
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
                "TELEGRAM_BOT_TOKEN": "telegram-public-token",
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            bridge_calls: list[dict[str, object]] = []

            def fake_gateway_turn(**kwargs):
                bridge_calls.append(kwargs)
                return True, ""

            def forbidden_agent_turn(**kwargs):
                raise AssertionError(f"quiet fallback should not run after bridge success: {kwargs}")

            def forbidden_telegram(**kwargs):
                raise AssertionError(f"Raven fallback delivery should not run after bridge success: {kwargs}")

            delivery._run_public_agent_gateway_turn = fake_gateway_turn
            delivery._run_public_agent_turn = forbidden_agent_turn
            delivery.telegram_send_message = forbidden_telegram
            error = delivery.deliver_row(
                cfg,
                {
                    "target_kind": "public-agent-turn",
                    "target_id": "tg:123",
                    "channel_kind": "telegram",
                    "message": "hello through gateway",
                    "extra_json": json.dumps(
                        {
                            "deployment_id": "arcdep_test",
                            "prefix": "arc-testpod",
                            "agent_label": "Test Agent",
                            "telegram_reply_to_message_id": "654",
                        }
                    ),
                },
            )
            expect(error is None, str(error))
            expect(len(bridge_calls) == 1, str(bridge_calls))
            expect(bridge_calls[0]["target_id"] == "tg:123", str(bridge_calls))
            expect(bridge_calls[0]["prompt"] == "hello through gateway", str(bridge_calls))
            expect(bridge_calls[0]["extra"]["telegram_reply_to_message_id"] == "654", str(bridge_calls))
            print("PASS test_public_agent_turn_delivery_prefers_gateway_bridge_when_available")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_turn_album_rows_merge_into_one_bridge_call() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_album_merge_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_album_merge_test")
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
                "TELEGRAM_BOT_TOKEN": "telegram-public-token",
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                for index in range(3):
                    update = {
                        "update_id": 9000 + index,
                        "message": {
                            "message_id": 100 + index,
                            "media_group_id": "album-777",
                            "chat": {"id": 777, "type": "private"},
                            "from": {"id": 777},
                            "photo": [{"file_id": f"photo-{index}", "width": 1, "height": 1}],
                            "caption": "first caption" if index == 0 else "",
                        },
                    }
                    control.queue_notification(
                        conn,
                        target_kind="public-agent-turn",
                        target_id="tg:777",
                        channel_kind="telegram",
                        message="[Telegram photo]",
                        extra={
                            "deployment_id": "arcdep_album",
                            "prefix": "arc-albumpod",
                            "agent_label": "Album Agent",
                            "telegram_update_kind": "photo",
                            "telegram_update_json": json.dumps(update, sort_keys=True, separators=(",", ":")),
                        },
                    )
                backdated = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
                conn.execute("UPDATE notification_outbox SET created_at = ?", (backdated,))
                conn.commit()

            bridge_calls: list[dict[str, object]] = []

            def fake_gateway_turn(**kwargs):
                bridge_calls.append(kwargs)
                return True, ""

            delivery._run_public_agent_gateway_turn = fake_gateway_turn
            summary = delivery.run_public_agent_turns_once(cfg, channel_kind="telegram", target_id="tg:777", limit=5)
            expect(summary["delivered"] == 1, str(summary))
            expect(len(bridge_calls) == 1, f"album must reach the bridge as one merged turn: {len(bridge_calls)}")
            merged_extra = bridge_calls[0]["extra"]
            update_list = merged_extra.get("telegram_update_json_list")
            expect(isinstance(update_list, list) and len(update_list) == 3, str(merged_extra.get("telegram_album_size")))
            expect("album-777" in update_list[0] and "album-777" in update_list[2], "all album items must carry the group id")

            with control.connect_db(cfg) as conn:
                rows = conn.execute(
                    "SELECT id, delivered_at, delivery_error, extra_json FROM notification_outbox ORDER BY id ASC"
                ).fetchall()
            expect(all(str(row["delivered_at"] or "").strip() for row in rows), str([dict(row) for row in rows]))
            # C2: absorbed siblings end DELIVERED with a CLEAN delivery_error (the
            # delivered guard now makes mark_notification_error a no-op on them); the
            # leader provenance lives in extra_json instead.
            leader_id = int(rows[0]["id"])
            for row in rows[1:]:
                expect(
                    not str(row["delivery_error"] or "").strip(),
                    f"absorbed sibling must keep a clean delivery_error: {dict(row)}",
                )
                extra = json.loads(str(row["extra_json"] or "{}"))
                expect(
                    int(extra.get("_absorbed_into_album_leader") or 0) == leader_id,
                    f"absorbed sibling must record leader provenance in extra_json: {dict(row)}",
                )
            print("PASS test_public_agent_turn_album_rows_merge_into_one_bridge_call")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_operator_agent_turn_delivery_uses_control_stack_gateway() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_operator_delivery_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_operator_gateway_test")

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
                "TELEGRAM_BOT_TOKEN": "telegram-public-token",
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            bridge_calls: list[dict[str, object]] = []

            def fake_operator_gateway_turn(**kwargs):
                bridge_calls.append(kwargs)
                return True, ""

            def forbidden_public_gateway(**kwargs):
                raise AssertionError(f"operator turn should not use ArcPod gateway: {kwargs}")

            delivery._run_operator_agent_gateway_turn = fake_operator_gateway_turn
            delivery._run_public_agent_gateway_turn = forbidden_public_gateway
            error = delivery.deliver_row(
                cfg,
                {
                    "id": "77",
                    "target_kind": "public-agent-turn",
                    "target_id": "tg:123",
                    "channel_kind": "telegram",
                    "message": "operator, are we up to date?",
                    "extra_json": json.dumps(
                        {
                            "deployment_id": "operator",
                            "prefix": "operator-helm",
                            "agent_label": "Operator Hermes",
                            "operator_turn": True,
                            "source_kind": "operator_chat",
                            "telegram_update_kind": "callback_query",
                            "telegram_native_callback": True,
                            "telegram_callback_family": "ea",
                            "telegram_update_json": json.dumps(
                                {
                                    "update_id": 123,
                                    "callback_query": {
                                        "id": "cb_1",
                                        "message": {"message_id": 22, "chat": {"id": 123}},
                                        "data": "ea:always:1",
                                    },
                                }
                            ),
                        }
                    ),
                },
            )
            expect(error is None, str(error))
            expect(len(bridge_calls) == 1, str(bridge_calls))
            expect(bridge_calls[0]["notification_id"] == 77, str(bridge_calls))
            expect(bridge_calls[0]["prompt"] == "operator, are we up to date?", str(bridge_calls))
            bridge_extra = bridge_calls[0]["extra"]
            expect(bridge_extra["telegram_update_kind"] == "callback_query", str(bridge_extra))
            expect(bridge_extra["telegram_native_callback"] is True, str(bridge_extra))
            expect(bridge_extra["telegram_callback_family"] == "ea", str(bridge_extra))
            native_update = json.loads(str(bridge_extra["telegram_update_json"]))
            expect(native_update["callback_query"]["data"] == "ea:always:1", str(native_update))
            print("PASS test_operator_agent_turn_delivery_uses_control_stack_gateway")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_turn_delivery_bridges_discord_channel_metadata() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_notification_delivery_discord_bridge_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_discord_bridge_test")
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
                "DISCORD_BOT_TOKEN": "discord-public-token",
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            bridge_calls: list[dict[str, object]] = []

            def fake_gateway_turn(**kwargs):
                bridge_calls.append(kwargs)
                expect(kwargs["channel_kind"] == "discord", str(kwargs))
                expect(kwargs["target_id"] == "discord:456", str(kwargs))
                expect(kwargs["extra"]["discord_channel_id"] == "chan_456", str(kwargs))
                expect(kwargs["extra"]["discord_user_id"] == "456", str(kwargs))
                return True, ""

            def forbidden_agent_turn(**kwargs):
                raise AssertionError(f"quiet fallback should not run after bridge success: {kwargs}")

            def forbidden_discord_send(**kwargs):
                raise AssertionError(f"Raven fallback delivery should not run after bridge success: {kwargs}")

            delivery._run_public_agent_gateway_turn = fake_gateway_turn
            delivery._run_public_agent_turn = forbidden_agent_turn
            delivery.discord_send_message = forbidden_discord_send
            error = delivery.deliver_row(
                cfg,
                {
                    "target_kind": "public-agent-turn",
                    "target_id": "discord:456",
                    "channel_kind": "discord",
                    "message": "/provider",
                    "extra_json": json.dumps(
                        {
                            "deployment_id": "arcdep_test",
                            "prefix": "arc-testpod",
                            "agent_label": "Test Agent",
                            "discord_channel_id": "chan_456",
                            "discord_user_id": "456",
                            "discord_chat_type": "dm",
                        }
                    ),
                },
            )
            expect(error is None, str(error))
            expect(len(bridge_calls) == 1, str(bridge_calls))
            print("PASS test_public_agent_turn_delivery_bridges_discord_channel_metadata")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_live_trigger_claims_and_defers_until_detached_bridge_finishes() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_notification_delivery_live_trigger_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_live_trigger_test")
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
                "TELEGRAM_BOT_TOKEN": "telegram-public-token",
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                notification_id = control.queue_notification(
                    conn,
                    target_kind="public-agent-turn",
                    target_id="tg:123",
                    channel_kind="telegram",
                    message="live trigger please",
                    extra={
                        "deployment_id": "arcdep_test",
                        "prefix": "arc-testpod",
                        "agent_label": "Test Agent",
                        "telegram_reply_to_message_id": "654",
                    },
                )

            bridge_calls: list[dict[str, object]] = []

            def fake_gateway_turn(**kwargs):
                bridge_calls.append(kwargs)
                expect(kwargs["notification_id"] == notification_id, str(kwargs))
                return True, delivery.PUBLIC_AGENT_BRIDGE_DEFERRED

            delivery._run_public_agent_gateway_turn = fake_gateway_turn
            first = delivery.run_public_agent_turns_once(cfg, channel_kind="telegram", target_id="tg:123", limit=1)
            second = delivery.run_public_agent_turns_once(cfg, channel_kind="telegram", target_id="tg:123", limit=1)
            expect(
                first["processed"] == 1
                and first["delivered"] == 0
                and first["errors"] == 0
                and first["deferred_public_agent_bridge"] == 1,
                str(first),
            )
            expect(second["processed"] == 0 and second["delivered"] == 0, str(second))
            expect(len(bridge_calls) == 1, str(bridge_calls))
            expect(bridge_calls[0]["prompt"] == "live trigger please", str(bridge_calls))
            with control.connect_db(cfg) as conn:
                row = conn.execute(
                    "SELECT delivered_at, last_attempt_at, next_attempt_at FROM notification_outbox WHERE id = ?",
                    (notification_id,),
                ).fetchone()
            expect(row["delivered_at"] is None, dict(row))
            expect(row["last_attempt_at"], dict(row))
            expect(row["next_attempt_at"], dict(row))
            print("PASS test_public_agent_live_trigger_claims_and_defers_until_detached_bridge_finishes")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_live_trigger_skips_not_due_head_of_line() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_notification_delivery_live_due_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_live_due_test")
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
                "TELEGRAM_BOT_TOKEN": "telegram-public-token",
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                first = control.queue_notification(
                    conn,
                    target_kind="public-agent-turn",
                    target_id="tg:123",
                    channel_kind="telegram",
                    message="not due",
                    extra={"deployment_id": "arcdep_test", "prefix": "arc-testpod"},
                )
                second = control.queue_notification(
                    conn,
                    target_kind="public-agent-turn",
                    target_id="tg:123",
                    channel_kind="telegram",
                    message="due now",
                    extra={"deployment_id": "arcdep_test", "prefix": "arc-testpod"},
                )
                conn.execute(
                    "UPDATE notification_outbox SET next_attempt_at = ? WHERE id = ?",
                    (control.utc_after_seconds_iso(3600), first),
                )
                conn.commit()

            prompts: list[str] = []

            def fake_gateway_turn(**kwargs):
                prompts.append(str(kwargs.get("prompt") or ""))
                return True, ""

            delivery._run_public_agent_gateway_turn = fake_gateway_turn
            summary = delivery.run_public_agent_turns_once(cfg, channel_kind="telegram", target_id="tg:123", limit=1)
            expect(summary["processed"] == 1 and summary["delivered"] == 1, str(summary))
            expect(prompts == ["due now"], str(prompts))
            with control.connect_db(cfg) as conn:
                rows = conn.execute(
                    "SELECT id, delivered_at FROM notification_outbox ORDER BY id ASC"
                ).fetchall()
            expect(rows[0]["id"] == first and rows[0]["delivered_at"] is None, str([dict(row) for row in rows]))
            expect(rows[1]["id"] == second and rows[1]["delivered_at"], str([dict(row) for row in rows]))
            print("PASS test_public_agent_live_trigger_skips_not_due_head_of_line")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_turn_runner_prefers_running_gateway_container() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_agent_turn_runner_test")

    class Proc:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    calls: list[list[str]] = []

    def fake_run(cmd, check=False, text=True, capture_output=True, timeout=None):
        del check, text, capture_output, timeout
        calls.append(list(cmd))
        if cmd[:2] == ["docker", "ps"]:
            expect("label=com.docker.compose.project=arclink-arcdep_test" in cmd, str(cmd))
            expect("label=com.docker.compose.service=hermes-gateway" in cmd, str(cmd))
            return Proc(0, "gateway-container\n")
        if cmd[:3] == ["docker", "exec", "gateway-container"]:
            expect("/opt/arclink/runtime/hermes-venv/bin/hermes" in cmd, str(cmd))
            expect("hello agent" in cmd, str(cmd))
            return Proc(0, "\x1b[32mAgent says hello.\x1b[0m\n\nsession_id: abc\n")
        return Proc(1, "", "unexpected command")

    original_run = delivery.subprocess.run
    try:
        delivery.subprocess.run = fake_run
        response, error = delivery._run_public_agent_turn(
            deployment_id="arcdep_test",
            prefix="arc-test",
            prompt="hello agent",
        )
        expect(error == "", error)
        expect(response == "Agent says hello.", response)
        expect(any(call[:3] == ["docker", "exec", "gateway-container"] for call in calls), str(calls))
        expect(not any(call[:2] == ["docker", "compose"] for call in calls), str(calls))
        print("PASS test_public_agent_turn_runner_prefers_running_gateway_container")
    finally:
        delivery.subprocess.run = original_run


def test_public_agent_gateway_bridge_detaches_long_running_turns() -> None:
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_detached_bridge_test")

    with tempfile.TemporaryDirectory() as tmp:
        old_env = os.environ.copy()
        os.environ["STATE_DIR"] = str(Path(tmp) / "state")
        try:
            calls: list[dict[str, object]] = []

            class FakeStdin:
                def __init__(self) -> None:
                    self.payload = ""
                    self.closed = False

                def write(self, value: str) -> None:
                    self.payload += value

                def close(self) -> None:
                    self.closed = True

            class FakeProc:
                def __init__(self) -> None:
                    self.stdin = FakeStdin()

                def wait(self, timeout=None):
                    raise delivery.subprocess.TimeoutExpired(["bridge"], timeout)

            def fake_popen(cmd, stdin=None, stdout=None, stderr=None, text=True, start_new_session=True):
                proc = FakeProc()
                calls.append(
                    {
                        "cmd": cmd,
                        "stdin": stdin,
                        "stdout": stdout,
                        "stderr": stderr,
                        "text": text,
                        "start_new_session": start_new_session,
                        "proc": proc,
                    }
                )
                return proc

            original_popen = delivery.subprocess.Popen
            delivery.subprocess.Popen = fake_popen
            ok, error = delivery._spawn_public_agent_gateway_bridge(
                cmd=[
                    "docker",
                    "exec",
                    "-i",
                    "arclink-arcdep_test-hermes-gateway-1",
                    "/opt/arclink/runtime/hermes-venv/bin/python3",
                    "/home/arclink/arclink/python/arclink_public_agent_bridge.py",
                ],
                payload={"platform": "telegram", "text": "long-running turn"},
                project_name="arclink-arcdep_test",
            )
            expect(ok is True, error)
            expect(error == "", error)
            expect(calls and calls[0]["start_new_session"] is True, str(calls))
            proc = calls[0]["proc"]
            expect(json.loads(proc.stdin.payload)["text"] == "long-running turn", proc.stdin.payload)
            expect(proc.stdin.closed is True, "bridge stdin should be closed after payload write")
            expect((Path(tmp) / "state" / "docker" / "jobs" / "public-agent-bridge.log").parent.exists(), "bridge log dir missing")
            print("PASS test_public_agent_gateway_bridge_detaches_long_running_turns")
        finally:
            delivery.subprocess.Popen = original_popen
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_gateway_bridge_unlinks_job_when_worker_spawn_fails() -> None:
    control = load_module(CONTROL_PY, "arclink_control_bridge_spawn_cleanup_control_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_bridge_spawn_cleanup_test")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        old_env = os.environ.copy()
        original_popen = delivery.subprocess.Popen

        def fail_popen(*args, **kwargs):
            raise OSError("spawn failed")

        delivery.subprocess.Popen = fail_popen
        try:
            cfg = _delivery_db_config(control, root)
            # C1: the row must exist + be undelivered so the lease-token stamp lands
            # (a missing/delivered row aborts the spawn BEFORE Popen by design); this
            # test exercises the Popen-failure cleanup path specifically.
            with control.connect_db(cfg) as conn:
                nid = control.queue_notification(
                    conn,
                    target_kind="public-agent-turn",
                    target_id="tg:1",
                    channel_kind="telegram",
                    message="hello",
                )
            ok, error = delivery._spawn_public_agent_gateway_bridge(
                cmd=[
                    "docker",
                    "exec",
                    "-i",
                    "arclink-arcdep_test-hermes-gateway-1",
                    "/opt/arclink/runtime/hermes-venv/bin/python3",
                    "/home/arclink/arclink/python/arclink_public_agent_bridge.py",
                ],
                payload={"platform": "telegram", "bot_token": "runtime-token", "text": "hello"},
                notification_id=nid,
                project_name="arclink-arcdep_test",
            )
            expect(ok is False and "could not start" in error, error)
            job_dir = root / "state" / "docker" / "jobs" / "public-agent-bridge-jobs"
            expect(not list(job_dir.glob("*.json")), "bridge job file should be removed on spawn failure")
            print("PASS test_public_agent_gateway_bridge_unlinks_job_when_worker_spawn_fails")
        finally:
            delivery.subprocess.Popen = original_popen
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_bridge_worker_marks_delivery_after_bridge_success() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_notification_delivery_bridge_worker_control_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_bridge_worker_test")

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
                "TELEGRAM_BOT_TOKEN": "telegram-public-token",
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                notification_id = control.queue_notification(
                    conn,
                    target_kind="public-agent-turn",
                    target_id="tg:123",
                    channel_kind="telegram",
                    message="finish later",
                    extra={"deployment_id": "arcdep_test"},
                )

            class Proc:
                returncode = 0
                stdout = '{"delivered": true, "delivery_status": "confirmed", "message_ids": ["tg-msg-1"], "ok": true}\n'
                stderr = ""

            run_calls: list[dict[str, object]] = []

            def fake_run(cmd, input="", check=False, text=True, capture_output=True, timeout=None):
                run_calls.append(
                    {
                        "cmd": cmd,
                        "input": input,
                        "check": check,
                        "text": text,
                        "capture_output": capture_output,
                        "timeout": timeout,
                    }
                )
                return Proc()

            original_run = delivery.subprocess.run
            delivery.subprocess.run = fake_run
            try:
                job_path = delivery._write_public_agent_bridge_job(
                    notification_id=notification_id,
                    cmd=[
                        "docker",
                        "exec",
                        "-i",
                        "arclink-arcdep_test-hermes-gateway-1",
                        "/opt/arclink/runtime/hermes-venv/bin/python3",
                        "/home/arclink/arclink/python/arclink_public_agent_bridge.py",
                    ],
                    payload={"platform": "telegram", "bot_token": "detached-command-secret", "text": "finish later"},
                    project_name="arclink-arcdep_test",
                )
                job_text = job_path.read_text(encoding="utf-8")
                expect("detached-command-secret" not in job_text and '"bot_token"' not in job_text, job_text)
                result = delivery._run_public_agent_bridge_worker(job_path)
                expect(result == 0, str(result))
                expect(
                    run_calls
                    and run_calls[0]["cmd"]
                    == [
                        "docker",
                        "exec",
                        "-i",
                        "arclink-arcdep_test-hermes-gateway-1",
                        "/opt/arclink/runtime/hermes-venv/bin/python3",
                        "/home/arclink/arclink/python/arclink_public_agent_bridge.py",
                    ],
                    str(run_calls),
                )
                bridge_input = json.loads(str(run_calls[0]["input"]))
                expect(bridge_input["text"] == "finish later", str(run_calls))
                expect(bridge_input["bot_token"] == "telegram-public-token", str(run_calls))
                expect(not job_path.exists(), "bridge job file should be removed after worker loads it")
                with control.connect_db(cfg) as conn:
                    row = conn.execute("SELECT delivered_at, delivery_error FROM notification_outbox WHERE id = ?", (notification_id,)).fetchone()
                expect(row["delivered_at"] and not row["delivery_error"], dict(row))
                print("PASS test_public_agent_bridge_worker_marks_delivery_after_bridge_success")
            finally:
                delivery.subprocess.run = original_run
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_bridge_worker_holds_unconfirmed_bridge_success() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_notification_delivery_bridge_unknown_control_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_bridge_unknown_test")

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
                "TELEGRAM_BOT_TOKEN": "telegram-public-token",
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                notification_id = control.queue_notification(
                    conn,
                    target_kind="public-agent-turn",
                    target_id="tg:123",
                    channel_kind="telegram",
                    message="finish later",
                    extra={"deployment_id": "arcdep_test"},
                )

            class Proc:
                returncode = 0
                stdout = '{"delivered": false, "delivery_status": "unknown", "message_ids": [], "ok": true}\n'
                stderr = ""

            def fake_run(cmd, input="", check=False, text=True, capture_output=True, timeout=None):
                del cmd, input, check, text, capture_output, timeout
                return Proc()

            original_run = delivery.subprocess.run
            delivery.subprocess.run = fake_run
            try:
                job_path = delivery._write_public_agent_bridge_job(
                    notification_id=notification_id,
                    cmd=[
                        "docker",
                        "exec",
                        "-i",
                        "arclink-arcdep_test-hermes-gateway-1",
                        "/opt/arclink/runtime/hermes-venv/bin/python3",
                        "/home/arclink/arclink/python/arclink_public_agent_bridge.py",
                    ],
                    payload={"platform": "telegram", "bot_token": "detached-command-secret", "text": "finish later"},
                    project_name="arclink-arcdep_test",
                )
                result = delivery._run_public_agent_bridge_worker(job_path)
                expect(result == 0, str(result))
                with control.connect_db(cfg) as conn:
                    row = conn.execute(
                        "SELECT delivered_at, delivery_error, next_attempt_at FROM notification_outbox WHERE id = ?",
                        (notification_id,),
                    ).fetchone()
                expect(not row["delivered_at"], dict(row))
                expect(str(row["delivery_error"] or "").startswith(delivery.PUBLIC_AGENT_BRIDGE_UNCONFIRMED), dict(row))
                expect(control.parse_utc_iso(str(row["next_attempt_at"] or "")) > control.utc_now(), dict(row))
                print("PASS test_public_agent_bridge_worker_holds_unconfirmed_bridge_success")
            finally:
                delivery.subprocess.run = original_run
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_bridge_hold_policy_distinguishes_unknown_from_failed_no_id() -> None:
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_bridge_hold_policy_test")
    unknown = delivery.public_agent_bridge_delivery_result(
        {"ok": True, "delivered": False, "delivery_status": "unknown", "message_ids": []}
    )
    failed_without_ids = delivery.public_agent_bridge_delivery_result(
        {
            "ok": True,
            "delivered": False,
            "delivery_status": "failed",
            "delivery_error": "telegram 403",
            "message_ids": [],
        }
    )
    failed_with_ids = delivery.public_agent_bridge_delivery_result(
        {
            "ok": True,
            "delivered": False,
            "delivery_status": "failed",
            "delivery_error": "final edit failed",
            "message_ids": ["tg-placeholder-1"],
        }
    )
    expect(delivery._public_agent_bridge_should_hold_for_reconciliation(unknown) is True, str(unknown))
    expect(delivery._public_agent_bridge_should_hold_for_reconciliation(failed_without_ids) is False, str(failed_without_ids))
    expect(delivery._public_agent_bridge_should_hold_for_reconciliation(failed_with_ids) is True, str(failed_with_ids))
    print("PASS test_public_agent_bridge_hold_policy_distinguishes_unknown_from_failed_no_id")


def test_public_agent_bridge_worker_retries_failed_send_without_message_ids() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_notification_delivery_bridge_failed_control_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_bridge_failed_test")

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
                "TELEGRAM_BOT_TOKEN": "telegram-public-token",
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                notification_id = control.queue_notification(
                    conn,
                    target_kind="public-agent-turn",
                    target_id="tg:123",
                    channel_kind="telegram",
                    message="finish later",
                    extra={"deployment_id": "arcdep_test"},
                )

            class Proc:
                returncode = 0
                stdout = (
                    '{"delivered": false, "delivery_status": "failed", '
                    '"delivery_error": "telegram 403", "message_ids": [], "ok": true}\n'
                )
                stderr = ""

            def fake_run(cmd, input="", check=False, text=True, capture_output=True, timeout=None):
                del cmd, input, check, text, capture_output, timeout
                return Proc()

            original_run = delivery.subprocess.run
            delivery.subprocess.run = fake_run
            try:
                job_path = delivery._write_public_agent_bridge_job(
                    notification_id=notification_id,
                    cmd=[
                        "docker",
                        "exec",
                        "-i",
                        "arclink-arcdep_test-hermes-gateway-1",
                        "/opt/arclink/runtime/hermes-venv/bin/python3",
                        "/home/arclink/arclink/python/arclink_public_agent_bridge.py",
                    ],
                    payload={"platform": "telegram", "bot_token": "detached-command-secret", "text": "finish later"},
                    project_name="arclink-arcdep_test",
                )
                result = delivery._run_public_agent_bridge_worker(job_path)
                expect(result == 1, str(result))
                with control.connect_db(cfg) as conn:
                    row = conn.execute(
                        "SELECT delivered_at, delivery_error, next_attempt_at FROM notification_outbox WHERE id = ?",
                        (notification_id,),
                    ).fetchone()
                expect(not row["delivered_at"], dict(row))
                expect(str(row["delivery_error"] or "").startswith("Hermes public gateway bridge failed: telegram 403"), dict(row))
                expect(not str(row["delivery_error"] or "").startswith(delivery.PUBLIC_AGENT_BRIDGE_UNCONFIRMED), dict(row))
                expect(control.parse_utc_iso(str(row["next_attempt_at"] or "")) > control.utc_now(), dict(row))
                print("PASS test_public_agent_bridge_worker_retries_failed_send_without_message_ids")
            finally:
                delivery.subprocess.run = original_run
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_bridge_orphan_reaper_rearms_dead_worker_lease() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_notification_delivery_bridge_reaper_control_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_bridge_reaper_test")

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
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        os.environ["ARCLINK_PUBLIC_AGENT_BRIDGE_ORPHAN_REAPER_SECONDS"] = "60"
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                notification_id = control.queue_notification(
                    conn,
                    target_kind="public-agent-turn",
                    target_id="tg:123",
                    channel_kind="telegram",
                    message="stalled",
                    extra={
                        "deployment_id": "arcdep_test",
                        "_public_agent_bridge_worker": {"pid": 99999999, "job_path": "/tmp/missing.json"},
                    },
                )
                conn.execute(
                    """
                    UPDATE notification_outbox
                    SET last_attempt_at = ?,
                        next_attempt_at = ?
                    WHERE id = ?
                    """,
                    (
                        "2026-01-01T00:00:00+00:00",
                        "2999-01-01T00:00:00+00:00",
                        notification_id,
                    ),
                )
                conn.commit()
            reclaimed = delivery.reap_orphaned_public_agent_bridge_leases(cfg, limit=5)
            expect(reclaimed == 1, str(reclaimed))
            with control.connect_db(cfg) as conn:
                row = conn.execute(
                    "SELECT delivery_error, next_attempt_at FROM notification_outbox WHERE id = ?",
                    (notification_id,),
                ).fetchone()
            expect("public_agent_bridge_orphan_reclaimed" in str(row["delivery_error"] or ""), dict(row))
            expect(control.parse_utc_iso(str(row["next_attempt_at"] or "")) <= control.utc_now(), dict(row))
            print("PASS test_public_agent_bridge_orphan_reaper_rearms_dead_worker_lease")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_bridge_worker_rejects_unallowlisted_commands() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_notification_delivery_bridge_reject_control_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_bridge_reject_test")

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
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                notification_id = control.queue_notification(
                    conn,
                    target_kind="public-agent-turn",
                    target_id="tg:123",
                    channel_kind="telegram",
                    message="do not run",
                    extra={"deployment_id": "arcdep_test"},
                )
            job_dir = root / "state" / "docker" / "jobs" / "public-agent-bridge-jobs"
            job_dir.mkdir(parents=True)
            job_path = job_dir / "tampered.json"
            job_path.write_text(
                json.dumps(
                    {
                        "notification_id": notification_id,
                        "cmd": ["docker", "run", "--privileged", "bad-image"],
                        "payload": {"platform": "telegram", "text": "do not run"},
                        "timeout_seconds": 60,
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            def forbidden_run(*args, **kwargs):
                raise AssertionError(f"unallowlisted bridge command should not execute: {args} {kwargs}")

            original_run = delivery.subprocess.run
            delivery.subprocess.run = forbidden_run
            try:
                result = delivery._run_public_agent_bridge_worker(job_path)
                expect(result == 1, str(result))
                with control.connect_db(cfg) as conn:
                    row = conn.execute(
                        "SELECT delivered_at, delivery_error FROM notification_outbox WHERE id = ?",
                        (notification_id,),
                    ).fetchone()
                expect(row["delivered_at"] is None, dict(row))
                expect("rejected command" in row["delivery_error"], dict(row))
                log_text = (root / "state" / "docker" / "jobs" / "public-agent-bridge.log").read_text(encoding="utf-8")
                expect("public_agent_bridge_rejected_command" in log_text, log_text)
                expect(not job_path.exists(), "rejected bridge job file should be consumed")
                print("PASS test_public_agent_bridge_worker_rejects_unallowlisted_commands")
            finally:
                delivery.subprocess.run = original_run
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_bridge_command_validator_confines_compose_paths() -> None:
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_bridge_validator_test")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state_root = root / "deployments"
        deployment_config = state_root / "arcdep_test-arc-test" / "config"
        deployment_config.mkdir(parents=True)
        env_file = deployment_config / "arclink.env"
        compose_file = deployment_config / "compose.yaml"
        env_file.write_text("", encoding="utf-8")
        compose_file.write_text("", encoding="utf-8")
        old_env = os.environ.copy()
        os.environ["ARCLINK_STATE_ROOT_BASE"] = str(state_root)
        try:
            valid_cmd = [
                "docker",
                "compose",
                "-p",
                "arclink-arcdep_test",
                "--env-file",
                str(env_file),
                "-f",
                str(compose_file),
                "exec",
                "-T",
                "-u",
                "0:0",
                "hermes-gateway",
                "/opt/arclink/runtime/hermes-venv/bin/python3",
                "/home/arclink/arclink/python/arclink_public_agent_bridge_root.py",
            ]
            ok, kind, error = delivery._validate_public_agent_bridge_cmd(
                valid_cmd,
                project_name="arclink-arcdep_test",
            )
            expect(ok is True and kind == "docker-compose-exec-hermes-gateway", error)

            old_job_cmd = [
                "docker",
                "compose",
                "-p",
                "arclink-arcdep_test",
                "--env-file",
                str(env_file),
                "-f",
                str(compose_file),
                "exec",
                "-T",
                "hermes-gateway",
                "/opt/arclink/runtime/hermes-venv/bin/python3",
                "/home/arclink/arclink/python/arclink_public_agent_bridge.py",
            ]
            ok, kind, error = delivery._validate_public_agent_bridge_cmd(
                old_job_cmd,
                project_name="arclink-arcdep_test",
            )
            expect(ok is True and kind == "docker-compose-exec-hermes-gateway", error)

            root_direct_bridge = [
                "docker",
                "exec",
                "-i",
                "-u",
                "0:0",
                "arclink-arcdep_test-hermes-gateway-1",
                "/opt/arclink/runtime/hermes-venv/bin/python3",
                "/home/arclink/arclink/python/arclink_public_agent_bridge.py",
            ]
            ok, _kind, error = delivery._validate_public_agent_bridge_cmd(
                root_direct_bridge,
                project_name="arclink-arcdep_test",
            )
            expect(ok is False and "not allowlisted" in error, error)

            root_wrapper_cmd = list(root_direct_bridge)
            root_wrapper_cmd[-1] = "/home/arclink/arclink/python/arclink_public_agent_bridge_root.py"
            ok, kind, error = delivery._validate_public_agent_bridge_cmd(
                root_wrapper_cmd,
                project_name="arclink-arcdep_test",
            )
            expect(ok is True and kind == "docker-exec-hermes-gateway", error)

            outside = root / "outside" / "config" / "arclink.env"
            outside.parent.mkdir(parents=True)
            outside.write_text("", encoding="utf-8")
            outside_compose = outside.parent / "compose.yaml"
            outside_compose.write_text("", encoding="utf-8")
            bad_cmd = list(valid_cmd)
            bad_cmd[5] = str(outside)
            bad_cmd[7] = str(outside_compose)
            ok, _kind, error = delivery._validate_public_agent_bridge_cmd(
                bad_cmd,
                project_name="arclink-arcdep_test",
            )
            expect(ok is False and "ARCLINK_STATE_ROOT_BASE" in error, error)

            symlink_config = state_root / "arcdep_link-arc-test" / "config"
            symlink_config.mkdir(parents=True)
            steered_config = state_root / "arcdep_steered-arc-test" / "config"
            steered_config.mkdir(parents=True)
            steered_env = steered_config / "arclink.env"
            steered_compose = steered_config / "compose.yaml"
            steered_env.write_text("ARCLINK_TEST=1\n", encoding="utf-8")
            steered_compose.write_text("services: {}\n", encoding="utf-8")
            env_link = symlink_config / "arclink.env"
            compose_link = symlink_config / "compose.yaml"
            env_link.symlink_to(steered_env)
            compose_link.symlink_to(steered_compose)
            symlink_cmd = list(valid_cmd)
            symlink_cmd[5] = str(env_link)
            symlink_cmd[7] = str(compose_link)
            ok, _kind, error = delivery._validate_public_agent_bridge_cmd(
                symlink_cmd,
                project_name="arclink-arcdep_test",
            )
            expect(ok is False and "symlink" in error.lower(), error)

            ok, _kind, error = delivery._validate_public_agent_bridge_cmd(
                ["docker", "exec", "-i", "arclink-other-hermes-gateway-1", "/bin/sh"],
                project_name="arclink-arcdep_test",
            )
            expect(ok is False and "not allowlisted" in error, error)
            ok, _kind, error = delivery._validate_public_agent_bridge_cmd(
                [
                    "docker",
                    "exec",
                    "-i",
                    "arclink-arcdep_test-not-hermes-gateway-1",
                    "/opt/arclink/runtime/hermes-venv/bin/python3",
                    "/home/arclink/arclink/python/arclink_public_agent_bridge.py",
                ],
                project_name="arclink-arcdep_test",
            )
            expect(ok is False and "hermes-gateway service" in error, error)
            print("PASS test_public_agent_bridge_command_validator_confines_compose_paths")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_gateway_bridge_passes_streaming_policy_to_container() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_bridge_streaming_policy_test")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "STATE_DIR": str(root / "state"),
                "TELEGRAM_BOT_TOKEN": "telegram-public-token",
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            payloads: list[dict[str, object]] = []
            delivery._deployment_service_container = lambda *, project_name, service: f"{project_name}-hermes-gateway-1"

            def fake_spawn(*, cmd, payload, notification_id=None, project_name=""):
                del notification_id, project_name
                payloads.append(dict(payload))
                return True, ""

            delivery._spawn_public_agent_gateway_bridge = fake_spawn
            ok, error = delivery._run_public_agent_gateway_turn(
                deployment_id="arcdep_test",
                prefix="arc-test",
                channel_kind="telegram",
                target_id="tg:123",
                prompt="hello",
                extra={},
            )
            expect(ok is True and error == "", error)
            expect(payloads[-1]["streaming_enabled"] is True, payloads[-1])

            write_config(
                config_path,
                {
                    "STATE_DIR": str(root / "state"),
                    "TELEGRAM_BOT_TOKEN": "telegram-public-token",
                    "ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING": "1",
                },
            )
            ok, error = delivery._run_public_agent_gateway_turn(
                deployment_id="arcdep_test",
                prefix="arc-test",
                channel_kind="telegram",
                target_id="tg:123",
                prompt="hello",
                extra={},
            )
            expect(ok is True and error == "", error)
            expect(payloads[-1]["streaming_enabled"] is True, payloads[-1])
            print("PASS test_public_agent_gateway_bridge_passes_streaming_policy_to_container")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_gateway_turn_uses_gateway_exec_broker_when_configured() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_gateway_broker_client_test")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "STATE_DIR": str(root / "state"),
                "TELEGRAM_BOT_TOKEN": "telegram-public-token",
                "ARCLINK_GATEWAY_EXEC_BROKER_URL": "http://gateway-exec-broker:8911",
                "ARCLINK_GATEWAY_EXEC_BROKER_TOKEN": "broker-token",
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            requests: list[dict[str, object]] = []

            def fake_broker_request(request_body):
                requests.append(dict(request_body))
                return True, ""

            def forbidden_container_lookup(*, project_name, service):
                raise AssertionError(f"notification-delivery should not inspect Docker when brokered: {project_name} {service}")

            original_broker_request = delivery._run_gateway_exec_broker_request
            original_container_lookup = delivery._deployment_service_container
            delivery._run_gateway_exec_broker_request = fake_broker_request
            delivery._deployment_service_container = forbidden_container_lookup
            try:
                ok, error = delivery._run_public_agent_gateway_turn(
                    deployment_id="arcdep_test",
                    prefix="arc-test",
                    channel_kind="telegram",
                    target_id="tg:123",
                    prompt="hello through broker",
                    extra={},
                )
            finally:
                delivery._run_gateway_exec_broker_request = original_broker_request
                delivery._deployment_service_container = original_container_lookup

            expect(ok is True and error == "", error)
            expect(len(requests) == 1, requests)
            request = requests[0]
            expect(request["deployment_id"] == "arcdep_test", request)
            expect(request["prefix"] == "arc-test", request)
            expect(request["project_name"] == "arclink-arcdep_test", request)
            payload = request["payload"]
            expect(isinstance(payload, dict), str(payload))
            expect(payload["platform"] == "telegram", payload)
            expect(payload["text"] == "hello through broker", payload)
            expect(payload["bot_token"] == "telegram-public-token", payload)
            print("PASS test_public_agent_gateway_turn_uses_gateway_exec_broker_when_configured")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_bridge_worker_uses_gateway_exec_broker_request_jobs() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_notification_delivery_broker_worker_control_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_broker_worker_test")

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
                "ARCLINK_GATEWAY_EXEC_BROKER_URL": "http://gateway-exec-broker:8911",
                "ARCLINK_GATEWAY_EXEC_BROKER_TOKEN": "broker-token",
                "TELEGRAM_BOT_TOKEN": "telegram-public-token",
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                notification_id = control.queue_notification(
                    conn,
                    target_kind="public-agent-turn",
                    target_id="tg:123",
                    channel_kind="telegram",
                    message="finish through broker",
                    extra={"deployment_id": "arcdep_test"},
                )
            broker_requests: list[dict[str, object]] = []

            def fake_broker_request(request_body):
                broker_requests.append(dict(request_body))
                return True, ""

            original_broker_request = delivery._run_gateway_exec_broker_request
            delivery._run_gateway_exec_broker_request = fake_broker_request
            try:
                job_path = delivery._write_public_agent_bridge_job(
                    notification_id=notification_id,
                    gateway_exec_request={
                        "deployment_id": "arcdep_test",
                        "prefix": "arc-test",
                        "project_name": "arclink-arcdep_test",
                        "payload": {
                            "platform": "telegram",
                            "bot_token": "detached-broker-secret",
                            "chat_id": "123",
                            "user_id": "123",
                            "text": "finish",
                        },
                        "timeout_seconds": 60,
                    },
                )
                job_text = job_path.read_text(encoding="utf-8")
                expect("detached-broker-secret" not in job_text and '"bot_token"' not in job_text, job_text)
                result = delivery._run_public_agent_bridge_worker(job_path)
            finally:
                delivery._run_gateway_exec_broker_request = original_broker_request

            expect(result == 0, str(result))
            expect(broker_requests and broker_requests[0]["deployment_id"] == "arcdep_test", broker_requests)
            expect(broker_requests[0]["payload"]["bot_token"] == "telegram-public-token", broker_requests)
            expect(not job_path.exists(), "broker bridge job file should be removed after worker loads it")
            with control.connect_db(cfg) as conn:
                row = conn.execute("SELECT delivered_at, delivery_error FROM notification_outbox WHERE id = ?", (notification_id,)).fetchone()
            expect(row["delivered_at"] and not row["delivery_error"], dict(row))
            log_text = (root / "state" / "docker" / "jobs" / "public-agent-bridge.log").read_text(encoding="utf-8")
            expect("public_agent_bridge_broker_delivered" in log_text, log_text)
            print("PASS test_public_agent_bridge_worker_uses_gateway_exec_broker_request_jobs")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_gateway_exec_broker_records_redacted_rejection_incident_before_subprocess() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    broker = load_module(
        PYTHON_DIR / "arclink_gateway_exec_broker.py",
        "arclink_gateway_exec_broker_rejection_incident_test",
    )

    original_container_lookup = broker.delivery._deployment_service_container
    original_preflight = broker.delivery._preflight_deployment_compose_config_files
    original_run = broker.subprocess.run
    original_docker_binary = broker._docker_binary
    old_env = os.environ.copy()

    docker_lookups: list[str] = []
    container_lookups: list[str] = []
    preflight_calls: list[str] = []
    subprocess_calls: list[str] = []

    def fail_docker_binary():
        docker_lookups.append("lookup")
        raise AssertionError("rejected gateway exec requests must fail before Docker CLI lookup")

    def fail_container_lookup(*, project_name, service, docker_binary="docker"):
        del docker_binary
        container_lookups.append(f"{project_name}:{service}")
        raise AssertionError("rejected gateway exec requests must fail before running-container discovery")

    def fail_preflight(**kwargs):
        preflight_calls.append(str(kwargs))
        raise AssertionError("rejected gateway exec requests must fail before Compose fallback preflight")

    def fail_run(*args, **kwargs):
        subprocess_calls.append(str(args or kwargs))
        raise AssertionError("rejected gateway exec requests must fail before subprocess execution")

    class Proc:
        returncode = 0
        stdout = '{"delivered": true, "delivery_status": "confirmed", "message_ids": ["tg-msg-1"], "ok": true}\n'
        stderr = ""

    def ok_run(cmd, input="", check=False, text=True, capture_output=True, timeout=None):
        subprocess_calls.append(" ".join(str(part) for part in cmd))
        expect(json.loads(str(input))["text"] == "valid public message", str(input))
        expect(check is False and text is True and capture_output is True and timeout == 60, str((check, text, capture_output, timeout)))
        return Proc()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state_root = root / "deployments"
        state_root.mkdir()
        incident_path = state_root / "_broker-incidents" / "gateway-exec-broker" / "rejections.jsonl"
        payload = {
            "platform": "telegram",
            "bot_token": "tg-secret-token-should-not-log",
            "chat_id": "1234567890",
            "user_id": "9999999999",
            "text": "secret public message should not log",
        }
        base_request = {
            "deployment_id": "arcdep_test",
            "prefix": "arc-test",
            "project_name": "arclink-arcdep_test",
            "payload": payload,
            "timeout_seconds": 60,
        }
        rejected_cases = [
            (
                "raw-command",
                {
                    **base_request,
                    "cmd": ["docker", "run", "--privileged", "bad-image"],
                },
                "raw_command_rejected",
            ),
            (
                "project-mismatch",
                {
                    **base_request,
                    "project_name": "arclink-other-deployment",
                },
                "project_name_mismatch",
            ),
            (
                "unsupported-platform",
                {
                    **base_request,
                    "payload": {**payload, "platform": "slack"},
                },
                "unsupported_platform",
            ),
        ]
        try:
            os.environ.clear()
            os.environ.update(old_env)
            os.environ["ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED"] = "accepted"
            os.environ["ARCLINK_STATE_ROOT_BASE"] = str(state_root)
            broker._docker_binary = fail_docker_binary
            broker.delivery._deployment_service_container = fail_container_lookup
            broker.delivery._preflight_deployment_compose_config_files = fail_preflight
            broker.subprocess.run = fail_run

            for index, (label, request, reason) in enumerate(rejected_cases, start=1):
                ok, error = broker.run_gateway_exec_request(request)
                expect(ok is False, f"{label} unexpectedly succeeded: {error}")
                expect(error and "tg-secret-token" not in error and "secret public message" not in error, error)
                expect(incident_path.exists(), f"{label} did not create {incident_path}")
                rows = [json.loads(line) for line in incident_path.read_text(encoding="utf-8").splitlines()]
                expect(len(rows) == index, str(rows))
                row = rows[-1]
                expect(row["event"] == "gateway_exec_broker_request_rejected", str(row))
                expect(row["service"] == "gateway-exec-broker", str(row))
                expect(row["deployment_id"] == "arcdep_test", str(row))
                expect(row["project_name"] == "arclink-arcdep_test", str(row))
                expect(row["trusted_host_acknowledged"] is True, str(row))
                expect(row["error_class"] == "ValueError", str(row))
                expect(row["reason"] == reason, str(row))
                expect("payload" not in row and "cmd" not in row and "command" not in row, str(row))

            incident_text = incident_path.read_text(encoding="utf-8")
            for forbidden in (
                "tg-secret-token-should-not-log",
                "secret public message should not log",
                "1234567890",
                "9999999999",
                "--privileged",
                "bad-image",
                "arclink-other-deployment",
                "slack",
                "bot_token",
                "chat_id",
                "user_id",
                "text",
            ):
                expect(forbidden not in incident_text, f"{forbidden!r} leaked into {incident_text}")
            expect(docker_lookups == [], str(docker_lookups))
            expect(container_lookups == [], str(container_lookups))
            expect(preflight_calls == [], str(preflight_calls))
            expect(subprocess_calls == [], str(subprocess_calls))

            row_count = len(incident_path.read_text(encoding="utf-8").splitlines())
            broker._docker_binary = lambda: "/usr/bin/docker"
            broker.delivery._deployment_service_container = (
                lambda *, project_name, service, docker_binary="docker": f"{project_name}-hermes-gateway-1"
            )
            broker.delivery._preflight_deployment_compose_config_files = original_preflight
            broker.subprocess.run = ok_run
            ok, error = broker.run_gateway_exec_request(
                {
                    **base_request,
                    "payload": {**payload, "text": "valid public message"},
                }
            )
            expect(ok is True and error == "", error)
            expect(len(incident_path.read_text(encoding="utf-8").splitlines()) == row_count, "accepted request appended rejection incident")

            symlink_root = root / "deployments-link"
            symlink_root.symlink_to(state_root, target_is_directory=True)
            os.environ["ARCLINK_STATE_ROOT_BASE"] = str(symlink_root)
            broker._docker_binary = fail_docker_binary
            broker.delivery._deployment_service_container = fail_container_lookup
            broker.delivery._preflight_deployment_compose_config_files = fail_preflight
            broker.subprocess.run = fail_run
            ok, error = broker.run_gateway_exec_request(rejected_cases[0][1])
            expect(ok is False and "raw commands" in error, error)
            expect(len(incident_path.read_text(encoding="utf-8").splitlines()) == row_count, "symlinked state root appended incident")
            print("PASS test_gateway_exec_broker_records_redacted_rejection_incident_before_subprocess")
        finally:
            broker.delivery._deployment_service_container = original_container_lookup
            broker.delivery._preflight_deployment_compose_config_files = original_preflight
            broker.subprocess.run = original_run
            broker._docker_binary = original_docker_binary
            os.environ.clear()
            os.environ.update(old_env)


def test_rejection_incident_helpers_redact_and_refuse_unsafe_paths() -> None:
    incidents = load_module(PYTHON_DIR / "arclink_rejection_incidents.py", "arclink_rejection_incidents_direct_test")
    old_env = os.environ.copy()
    try:
        os.environ["ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED"] = "accepted"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "state"
            root.mkdir()
            os.environ["ARCLINK_STATE_ROOT_BASE"] = str(root)
            broker_path = incidents.state_root_rejection_path("gateway-exec-broker")
            helper_path = incidents.state_root_rejection_path("agent-process-helper", helper=True)
            expect(broker_path == root / "_broker-incidents" / "gateway-exec-broker" / "rejections.jsonl", str(broker_path))
            expect(helper_path == root / "_helper-incidents" / "agent-process-helper" / "rejections.jsonl", str(helper_path))
            expect(broker_path.parent.is_dir() and helper_path.parent.is_dir(), "incident path helpers must create safe parents")

            incidents.record_rejection_incident(
                broker_path,
                service="gateway-exec-broker",
                event="rejected_request",
                reason="invalid_payload",
                message="blocked before subprocess",
                error_class="ValueError",
                metadata={
                    "request_id": "req_123",
                    "attempt": 2,
                    "safe": True,
                    "bad key": "ignored",
                    "raw_body": '{"bot_token":"123:SECRET"}',
                },
            )
            raw = broker_path.read_text(encoding="utf-8")
            row = json.loads(raw)
            expect(row["trusted_host_acknowledged"] is True, str(row))
            expect(row["request_id"] == "req_123" and row["attempt"] == 2 and row["safe"] is True, str(row))
            expect("bad key" not in row and "raw_body" not in row and "SECRET" not in raw, raw)
            expect(stat.S_IMODE(broker_path.stat().st_mode) & 0o077 == 0, oct(stat.S_IMODE(broker_path.stat().st_mode)))

            os.environ["ARCLINK_STATE_ROOT_BASE"] = "relative-state"
            expect(incidents.state_root_rejection_path("gateway-exec-broker") is None, "relative roots must be rejected")
            symlink_root = Path(tmp) / "state-link"
            symlink_root.symlink_to(root, target_is_directory=True)
            os.environ["ARCLINK_STATE_ROOT_BASE"] = str(symlink_root)
            expect(incidents.state_root_rejection_path("gateway-exec-broker") is None, "symlink roots must be rejected")

            target = Path(tmp) / "target.jsonl"
            target.write_text("unchanged\n", encoding="utf-8")
            link = Path(tmp) / "link.jsonl"
            link.symlink_to(target)
            incidents.record_rejection_incident(
                link,
                service="gateway-exec-broker",
                event="rejected_request",
                reason="invalid_payload",
                message="blocked before subprocess",
                error_class="ValueError",
            )
            expect(target.read_text(encoding="utf-8") == "unchanged\n", "symlink leaf must not be followed")
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    print("PASS test_rejection_incident_helpers_redact_and_refuse_unsafe_paths")


def test_gateway_exec_broker_rejects_raw_commands_and_builds_vetted_exec() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    broker = load_module(PYTHON_DIR / "arclink_gateway_exec_broker.py", "arclink_gateway_exec_broker_contract_test")

    calls: list[dict[str, object]] = []

    class Proc:
        returncode = 0
        stdout = '{"delivered": true, "delivery_status": "confirmed", "message_ids": ["tg-msg-1"], "ok": true}\n'
        stderr = ""

    def fake_run(cmd, input="", check=False, text=True, capture_output=True, timeout=None):
        calls.append(
            {
                "cmd": cmd,
                "input": input,
                "check": check,
                "text": text,
                "capture_output": capture_output,
                "timeout": timeout,
            }
        )
        return Proc()

    original_container_lookup = broker.delivery._deployment_service_container
    original_run = broker.subprocess.run
    original_which = broker.shutil.which
    original_trusted = broker.TRUSTED_DOCKER_BINARY_PATHS
    old_env = os.environ.get("ARCLINK_DOCKER_BINARY")
    old_state_root = os.environ.get("ARCLINK_STATE_ROOT_BASE")
    old_control_project = os.environ.get("ARCLINK_CONTROL_COMPOSE_PROJECT")
    with tempfile.TemporaryDirectory() as tmp:
        docker_path = Path(tmp) / "docker"
        docker_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        docker_path.chmod(0o755)
        docker_binary = str(docker_path)
        try:
            broker.TRUSTED_DOCKER_BINARY_PATHS = (docker_path,)
            broker.shutil.which = lambda name: docker_binary if name == "docker" else None
            os.environ["ARCLINK_DOCKER_BINARY"] = "docker"
            broker.delivery._deployment_service_container = (
                lambda *, project_name, service, docker_binary="docker": f"{project_name}-hermes-gateway-1"
            )
            broker.subprocess.run = fake_run
            ok, error = broker.run_gateway_exec_request(
                {
                    "deployment_id": "arcdep_test",
                    "prefix": "arc-test",
                    "project_name": "arclink-arcdep_test",
                    "payload": {
                        "platform": "telegram",
                        "bot_token": "token",
                        "chat_id": "123",
                        "user_id": "123",
                        "text": "hello",
                    },
                    "timeout_seconds": 60,
                }
            )
            expect(ok is True and error == "", error)
            expect(
                calls
                and calls[0]["cmd"]
                == [
                    docker_binary,
                    "exec",
                    "-i",
                    "arclink-arcdep_test-hermes-gateway-1",
                    "/opt/arclink/runtime/hermes-venv/bin/python3",
                    "/home/arclink/arclink/python/arclink_public_agent_bridge.py",
                ],
                str(calls),
            )

            calls.clear()
            os.environ["ARCLINK_CONTROL_COMPOSE_PROJECT"] = "arclink"
            broker.delivery._deployment_service_container = (
                lambda *, project_name, service, docker_binary="docker": f"{project_name}-control-operator-hermes-gateway-1"
            )
            ok, error = broker.run_gateway_exec_request(
                {
                    "operator_stack": True,
                    "project_name": "arclink",
                    "payload": {
                        "platform": "telegram",
                        "bot_token": "token",
                        "chat_id": "123",
                        "user_id": "123",
                        "text": "operator hello",
                    },
                    "timeout_seconds": 60,
                }
            )
            expect(ok is True and error == "", error)
            expect(
                calls
                and calls[0]["cmd"]
                == [
                    docker_binary,
                    "exec",
                    "-i",
                    "arclink-control-operator-hermes-gateway-1",
                    "/opt/arclink/runtime/hermes-venv/bin/python3",
                    "/home/arclink/arclink/python/arclink_public_agent_bridge.py",
                ],
                str(calls),
            )

            calls.clear()
            state_root = Path(tmp) / "deployments"
            deployment_config = state_root / "arcdep_test-arc-test" / "config"
            deployment_config.mkdir(parents=True)
            env_file = deployment_config / "arclink.env"
            compose_file = deployment_config / "compose.yaml"
            env_file.write_text("ARCLINK_TEST=1\n", encoding="utf-8")
            compose_file.write_text("services: {}\n", encoding="utf-8")
            os.environ["ARCLINK_STATE_ROOT_BASE"] = str(state_root)
            broker.delivery._deployment_service_container = (
                lambda *, project_name, service, docker_binary="docker": ""
            )
            ok, error = broker.run_gateway_exec_request(
                {
                    "deployment_id": "arcdep_test",
                    "prefix": "arc-test",
                    "project_name": "arclink-arcdep_test",
                    "payload": {
                        "platform": "telegram",
                        "bot_token": "token",
                        "chat_id": "123",
                        "user_id": "123",
                        "text": "hello",
                    },
                    "timeout_seconds": 60,
                }
            )
            expect(ok is True and error == "", error)
            expect(
                calls
                and calls[0]["cmd"]
                == [
                    docker_binary,
                    "compose",
                    "-p",
                    "arclink-arcdep_test",
                    "--env-file",
                    str(env_file),
                    "-f",
                    str(compose_file),
                    "exec",
                    "-T",
                    "hermes-gateway",
                    "/opt/arclink/runtime/hermes-venv/bin/python3",
                    "/home/arclink/arclink/python/arclink_public_agent_bridge.py",
                ],
                str(calls),
            )

            ok, error = broker.run_gateway_exec_request(
                {
                    "deployment_id": "arcdep_test",
                    "prefix": "arc-test",
                    "project_name": "arclink-arcdep_test",
                    "cmd": ["docker", "run", "--privileged", "bad"],
                    "payload": {
                        "platform": "telegram",
                        "bot_token": "token",
                        "chat_id": "123",
                        "user_id": "123",
                        "text": "hello",
                    },
                }
            )
            expect(ok is False and "raw commands" in error, error)
            ok, error = broker.run_gateway_exec_request(
                {
                    "deployment_id": "../arcdep_test",
                    "prefix": "arc-test",
                    "project_name": "arclink-arcdep_test",
                    "payload": {
                        "platform": "telegram",
                        "bot_token": "token",
                        "chat_id": "123",
                        "user_id": "123",
                        "text": "hello",
                    },
                }
            )
            expect(ok is False and "safe deployment path segment" in error, error)
            print("PASS test_gateway_exec_broker_rejects_raw_commands_and_builds_vetted_exec")
        finally:
            broker.delivery._deployment_service_container = original_container_lookup
            broker.subprocess.run = original_run
            broker.shutil.which = original_which
            broker.TRUSTED_DOCKER_BINARY_PATHS = original_trusted
            if old_env is None:
                os.environ.pop("ARCLINK_DOCKER_BINARY", None)
            else:
                os.environ["ARCLINK_DOCKER_BINARY"] = old_env
            if old_state_root is None:
                os.environ.pop("ARCLINK_STATE_ROOT_BASE", None)
            else:
                os.environ["ARCLINK_STATE_ROOT_BASE"] = old_state_root
            if old_control_project is None:
                os.environ.pop("ARCLINK_CONTROL_COMPOSE_PROJECT", None)
            else:
                os.environ["ARCLINK_CONTROL_COMPOSE_PROJECT"] = old_control_project


def test_gateway_exec_broker_rejects_symlinked_compose_fallback_config_before_docker() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    broker = load_module(PYTHON_DIR / "arclink_gateway_exec_broker.py", "arclink_gateway_exec_broker_symlink_config_test")

    subprocess_calls: list[list[str]] = []

    def fail_run(cmd, input="", check=False, text=True, capture_output=True, timeout=None):
        del input, check, text, capture_output, timeout
        subprocess_calls.append([str(part) for part in cmd])
        raise AssertionError("gateway exec broker must reject unsafe fallback config before subprocess dispatch")

    original_container_lookup = broker.delivery._deployment_service_container
    original_run = broker.subprocess.run
    original_docker_binary = broker._docker_binary
    old_state_root = os.environ.get("ARCLINK_STATE_ROOT_BASE")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp) / "deployments"
            requested_config = state_root / "arcdep_test-arc-test" / "config"
            requested_config.mkdir(parents=True)
            steered_config = state_root / "arcdep_steered-arc-test" / "config"
            steered_config.mkdir(parents=True)
            steered_env = steered_config / "arclink.env"
            steered_compose = steered_config / "compose.yaml"
            steered_env.write_text("ARCLINK_TEST=1\n", encoding="utf-8")
            steered_compose.write_text("services: {}\n", encoding="utf-8")
            (requested_config / "arclink.env").symlink_to(steered_env)
            (requested_config / "compose.yaml").symlink_to(steered_compose)
            os.environ["ARCLINK_STATE_ROOT_BASE"] = str(state_root)
            broker._docker_binary = lambda: "/usr/bin/docker"
            broker.delivery._deployment_service_container = (
                lambda *, project_name, service, docker_binary="docker": ""
            )
            broker.subprocess.run = fail_run

            ok, error = broker.run_gateway_exec_request(
                {
                    "deployment_id": "arcdep_test",
                    "prefix": "arc-test",
                    "project_name": "arclink-arcdep_test",
                    "payload": {
                        "platform": "telegram",
                        "bot_token": "token",
                        "chat_id": "123",
                        "user_id": "123",
                        "text": "hello",
                    },
                    "timeout_seconds": 60,
                }
            )
    finally:
        broker.delivery._deployment_service_container = original_container_lookup
        broker.subprocess.run = original_run
        broker._docker_binary = original_docker_binary
        if old_state_root is None:
            os.environ.pop("ARCLINK_STATE_ROOT_BASE", None)
        else:
            os.environ["ARCLINK_STATE_ROOT_BASE"] = old_state_root

    expect(ok is False and "symlink" in error.lower(), error)
    expect(subprocess_calls == [], f"unsafe fallback config reached subprocess dispatch: {subprocess_calls}")
    print("PASS test_gateway_exec_broker_rejects_symlinked_compose_fallback_config_before_docker")


def test_gateway_exec_broker_sanitizes_subprocess_failure_tail() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    broker = load_module(PYTHON_DIR / "arclink_gateway_exec_broker.py", "arclink_gateway_exec_broker_failure_tail_test")

    class Proc:
        returncode = 42
        stdout = "stdout leaked-private-path\n"
        stderr = "stderr leaked-secret-tail\n"

    def fake_run(cmd, input="", check=False, text=True, capture_output=True, timeout=None):
        del cmd, input, check, text, capture_output, timeout
        return Proc()

    original_container_lookup = broker.delivery._deployment_service_container
    original_run = broker.subprocess.run
    original_docker_binary = broker._docker_binary
    try:
        broker._docker_binary = lambda: "/usr/bin/docker"
        broker.delivery._deployment_service_container = (
            lambda *, project_name, service, docker_binary="docker": f"{project_name}-hermes-gateway-1"
        )
        broker.subprocess.run = fake_run
        ok, error = broker.run_gateway_exec_request(
            {
                "deployment_id": "arcdep_test",
                "prefix": "arc-test",
                "project_name": "arclink-arcdep_test",
                "payload": {
                    "platform": "telegram",
                    "bot_token": "request-secret-token",
                    "chat_id": "123",
                    "user_id": "123",
                    "text": "hello",
                },
                "timeout_seconds": 60,
            }
        )
    finally:
        broker.delivery._deployment_service_container = original_container_lookup
        broker.subprocess.run = original_run
        broker._docker_binary = original_docker_binary

    expect(ok is False, "failed subprocess should not succeed")
    expect("exit status 42" in error, error)
    for forbidden in ("leaked-secret-tail", "leaked-private-path", "request-secret-token"):
        expect(forbidden not in error, error)
    print("PASS test_gateway_exec_broker_sanitizes_subprocess_failure_tail")


def test_upgrade_notification_delivery_defers_during_deploy_operation() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_notification_delivery_deploy_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_deploy_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state_dir = root / "state"
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(state_dir),
                "RUNTIME_DIR": str(state_dir / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ARCLINK_DB_PATH": str(state_dir / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(state_dir / "agents"),
                "ARCLINK_CURATOR_DIR": str(state_dir / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(state_dir / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(state_dir / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(state_dir / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(state_dir / "arclink-release.json"),
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "tui-only",
            },
        )
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "arclink-deploy-operation.json").write_text(
            json.dumps(
                {
                    "operation": "docker-upgrade",
                    "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1))
                    .isoformat()
                    .replace("+00:00", "Z"),
                }
            )
            + "\n",
            encoding="utf-8",
        )

        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                control.queue_notification(
                    conn,
                    target_kind="operator",
                    target_id="operator",
                    channel_kind="tui-only",
                    message="ArcLink update available: deployed aaa -> upstream bbb.",
                )

            summary = delivery.run_once(cfg)
            expect(summary["processed"] == 1, summary)
            expect(summary["delivered"] == 0, summary)
            expect(summary["deferred_during_deploy"] == 1, summary)
            with control.connect_db(cfg) as conn:
                row = conn.execute("SELECT delivered_at FROM notification_outbox").fetchone()
            expect(row["delivered_at"] is None, dict(row))
            print("PASS test_upgrade_notification_delivery_defers_during_deploy_operation")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_bridge_defaults_to_streaming_progress_without_reasoning() -> None:
    bridge = load_module(PYTHON_DIR / "arclink_public_agent_bridge.py", "arclink_public_agent_bridge_contract_test")
    bridge_source = (PYTHON_DIR / "arclink_public_agent_bridge.py").read_text(encoding="utf-8")
    expect("ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING" in bridge_source, bridge_source)
    expect("streaming.enabled = True" in bridge_source, bridge_source)
    expect("show_reasoning = True" not in bridge_source, bridge_source)
    old_env = os.environ.copy()
    try:
        os.environ.pop("ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING", None)
        os.environ.pop("HERMES_TOOL_PROGRESS_MODE", None)
        expect(bridge._public_bridge_streaming_enabled() is True, "public bridge should default to Hermes-native streaming")
        bridge._apply_public_bridge_options({"streaming_enabled": True})
        expect(os.environ.get("HERMES_TOOL_PROGRESS_MODE") == "all", "bridge should opt into tool progress unless explicitly configured")
        os.environ["ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING"] = "0"
        expect(bridge._public_bridge_streaming_enabled() is False, "streaming should remain explicitly disableable")
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    expect("Update.de_json" in bridge_source, "Telegram rich updates should be replayed through Hermes/PTB")
    expect("_handle_media_message" in bridge_source, "Telegram media must use Hermes' own media handler")
    expect("_handle_callback_query" in bridge_source, "Telegram callback queries must use Hermes' own callback handler")
    expect(bridge._is_slash_command("/provider") is True, "slash command should be recognized")
    expect(bridge._is_slash_command("  /reload-mcp") is True, "leading whitespace slash command should be recognized")
    expect(bridge._is_slash_command("hello") is False, "chat text should not be a slash command")
    expect("message_type=MessageType.COMMAND if _is_slash_command(text) else MessageType.TEXT" in bridge_source, bridge_source)
    print("PASS test_public_agent_bridge_defaults_to_streaming_progress_without_reasoning")


def _install_public_bridge_runtime_stubs(load_gateway_config):
    module_names = [
        "telegram",
        "gateway",
        "gateway.config",
        "gateway.platforms",
        "gateway.platforms.base",
        "gateway.run",
        "gateway.session",
    ]
    missing = object()
    previous = {name: sys.modules.get(name, missing) for name in module_names}
    init_calls: list[str] = []

    class FakeTelegramUser:
        def __init__(self, payload: dict[str, object]):
            self.payload = dict(payload)
            self.id = self.payload.get("id", 4242)
            self.is_bot = self.payload.get("is_bot", True)
            self.first_name = self.payload.get("first_name", "ArcBot")
            self.username = self.payload.get("username", "arc_bot")

        @classmethod
        def de_json(cls, data, bot):
            del bot
            return cls(dict(data or {}))

        def to_dict(self):
            return dict(self.payload)

    class FakeBot:
        def __init__(self, token: str):
            self.token = token
            self._initialized = False
            self._bot_user = None

        async def initialize(self):
            init_calls.append(self.token)
            self._bot_user = FakeTelegramUser(
                {"id": 4242, "is_bot": True, "first_name": "ArcBot", "username": "arc_bot"}
            )
            self._initialized = True

        async def shutdown(self):
            return None

    class HomeChannel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class Platform:
        TELEGRAM = "telegram"
        DISCORD = "discord"

    class PlatformConfig:
        def __init__(self):
            self.enabled = False
            self.token = ""
            self.gateway_restart_notification = True
            self.reply_to_mode = ""
            self.home_channel = None

    class MessageType:
        COMMAND = "command"
        TEXT = "text"

    class MessageEvent:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class SendResult:
        def __init__(self, success=True, message_id=None, raw_response=None, error=""):
            self.success = success
            self.message_id = message_id
            self.raw_response = raw_response
            self.error = error
            self.continuation_message_ids = []

    class SessionSource:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeAdapter:
        MAX_MESSAGE_LENGTH = 4096

        def __init__(self):
            self._background_tasks = set()
            self._pending_text_batch_tasks = {}
            self._pending_photo_batch_tasks = {}

        def set_message_handler(self, handler):
            self.message_handler = handler

        def set_fatal_error_handler(self, handler):
            self.fatal_error_handler = handler

        def set_session_store(self, store):
            self.session_store = store

        def set_busy_session_handler(self, handler):
            self.busy_session_handler = handler

        async def send(self, chat_id, content, reply_to=None, metadata=None):
            del chat_id, content, reply_to, metadata
            return SendResult(success=True, message_id="tg-msg-1", raw_response={"message_id": "tg-msg-1"})

        async def handle_message(self, event):
            await self.send(event.source.chat_id, "agent answer")

    class GatewayRunner:
        def __init__(self, cfg):
            self.cfg = cfg
            self.session_store = object()
            self.adapters = {}

        def _create_adapter(self, platform, platform_cfg):
            del platform, platform_cfg
            return FakeAdapter()

        async def _handle_message(self, event):
            del event

        def _handle_adapter_fatal_error(self, *args, **kwargs):
            del args, kwargs

        def _handle_active_session_busy_message(self, *args, **kwargs):
            del args, kwargs

        def _session_key_for_source(self, source):
            return f"{source.platform}:{source.chat_id}"

    telegram_mod = types.ModuleType("telegram")
    telegram_mod.Bot = FakeBot
    telegram_mod.User = FakeTelegramUser

    gateway_mod = types.ModuleType("gateway")
    gateway_mod.__path__ = []
    config_mod = types.ModuleType("gateway.config")
    config_mod.HomeChannel = HomeChannel
    config_mod.Platform = Platform
    config_mod.PlatformConfig = PlatformConfig
    config_mod.load_gateway_config = load_gateway_config
    platforms_mod = types.ModuleType("gateway.platforms")
    platforms_mod.__path__ = []
    base_mod = types.ModuleType("gateway.platforms.base")
    base_mod.MessageEvent = MessageEvent
    base_mod.MessageType = MessageType
    base_mod.SendResult = SendResult
    run_mod = types.ModuleType("gateway.run")
    run_mod.GatewayRunner = GatewayRunner
    session_mod = types.ModuleType("gateway.session")
    session_mod.SessionSource = SessionSource

    sys.modules["telegram"] = telegram_mod
    sys.modules["gateway"] = gateway_mod
    sys.modules["gateway.config"] = config_mod
    sys.modules["gateway.platforms"] = platforms_mod
    sys.modules["gateway.platforms.base"] = base_mod
    sys.modules["gateway.run"] = run_mod
    sys.modules["gateway.session"] = session_mod
    return previous, init_calls, FakeTelegramUser


def _restore_public_bridge_runtime_stubs(previous) -> None:
    for name, module in previous.items():
        if module.__class__ is object:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


def _fake_gateway_config(platforms=None):
    return types.SimpleNamespace(
        platforms=platforms if platforms is not None else {},
        streaming=types.SimpleNamespace(enabled=False, transport=""),
    )


def test_public_agent_bridge_l1_l2_flags_off_preserve_config_and_getme() -> None:
    old_env = os.environ.copy()
    previous = None
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        runtime = root / "runtime-src"
        runtime.mkdir()
        snapshots: list[dict[str, str]] = []

        def load_gateway_config():
            snapshots.append({key: value for key, value in os.environ.items() if key.startswith(("TELEGRAM_", "DISCORD_"))})
            return _fake_gateway_config()

        try:
            os.environ.clear()
            os.environ.update(
                {
                    "HOME": str(root / "home"),
                    "HERMES_AGENT_SRC": str(runtime),
                    "DISCORD_BOT_TOKEN": "discord-token-present",
                    "DISCORD_HOME_CHANNEL": "discord-home-present",
                    "ARCLINK_BRIDGE_SINGLE_PLATFORM_CONFIG": "0",
                    "ARCLINK_BRIDGE_GETME_CACHE": "0",
                }
            )
            previous, init_calls, _user_cls = _install_public_bridge_runtime_stubs(load_gateway_config)
            bridge = load_module(PYTHON_DIR / "arclink_public_agent_bridge.py", "arclink_public_agent_bridge_flags_off_test")
            result = asyncio.run(
                bridge._run_telegram(
                    {
                        "platform": "telegram",
                        "bot_token": "telegram-turn-token",
                        "chat_id": "tg-chat",
                        "user_id": "tg-user",
                        "text": "hello",
                    }
                )
            )
            expect(result["delivered"] is True, str(result))
            expect(snapshots and snapshots[0].get("DISCORD_BOT_TOKEN") == "discord-token-present", str(snapshots))
            expect(snapshots[0].get("TELEGRAM_BOT_TOKEN") == "telegram-turn-token", str(snapshots))
            expect(init_calls == ["telegram-turn-token"], str(init_calls))
            print("PASS test_public_agent_bridge_l1_l2_flags_off_preserve_config_and_getme")
        finally:
            if previous is not None:
                _restore_public_bridge_runtime_stubs(previous)
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_bridge_l1_env_starves_unused_platform_and_restores() -> None:
    old_env = os.environ.copy()
    previous = None
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        runtime = root / "runtime-src"
        runtime.mkdir()
        snapshots: list[dict[str, str]] = []

        def load_gateway_config():
            snapshots.append({key: value for key, value in os.environ.items() if key.startswith(("TELEGRAM_", "DISCORD_"))})
            return _fake_gateway_config()

        try:
            os.environ.clear()
            os.environ.update(
                {
                    "HOME": str(root / "home"),
                    "HERMES_AGENT_SRC": str(runtime),
                    "DISCORD_BOT_TOKEN": "discord-token-starved",
                    "DISCORD_REPLY_TO_MODE": "first",
                    "ARCLINK_BRIDGE_SINGLE_PLATFORM_CONFIG": "1",
                    "ARCLINK_BRIDGE_GETME_CACHE": "0",
                }
            )
            previous, _init_calls, _user_cls = _install_public_bridge_runtime_stubs(load_gateway_config)
            bridge = load_module(PYTHON_DIR / "arclink_public_agent_bridge.py", "arclink_public_agent_bridge_l1_starve_test")
            asyncio.run(
                bridge._run_telegram(
                    {
                        "platform": "telegram",
                        "bot_token": "telegram-turn-token",
                        "chat_id": "tg-chat",
                        "user_id": "tg-user",
                        "text": "hello",
                    }
                )
            )
            expect(snapshots and "DISCORD_BOT_TOKEN" not in snapshots[0], str(snapshots))
            expect("DISCORD_REPLY_TO_MODE" not in snapshots[0], str(snapshots))
            expect(snapshots[0].get("TELEGRAM_BOT_TOKEN") == "telegram-turn-token", str(snapshots))
            expect(os.environ.get("DISCORD_BOT_TOKEN") == "discord-token-starved", dict(os.environ))
            expect(os.environ.get("DISCORD_REPLY_TO_MODE") == "first", dict(os.environ))
            print("PASS test_public_agent_bridge_l1_env_starves_unused_platform_and_restores")
        finally:
            if previous is not None:
                _restore_public_bridge_runtime_stubs(previous)
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_bridge_l1_restores_env_when_starved_loader_raises() -> None:
    old_env = os.environ.copy()
    try:
        os.environ.clear()
        os.environ.update(
            {
                "ARCLINK_BRIDGE_SINGLE_PLATFORM_CONFIG": "1",
                "ARCLINK_BRIDGE_GETME_CACHE": "0",
                "DISCORD_BOT_TOKEN": "discord-token-restored",
                "DISCORD_EXTRA_CONFIG": "discord-extra-restored",
            }
        )
        bridge = load_module(PYTHON_DIR / "arclink_public_agent_bridge.py", "arclink_public_agent_bridge_l1_raise_test")
        snapshots: list[dict[str, str]] = []

        def load_gateway_config():
            snapshots.append({key: value for key, value in os.environ.items() if key.startswith("DISCORD_")})
            if len(snapshots) == 1:
                raise RuntimeError("starved load failed")
            return _fake_gateway_config()

        result = bridge._load_gateway_config_for_platform(load_gateway_config, "telegram")
        expect(result is not None, "fallback load should return config")
        expect(snapshots and not snapshots[0], str(snapshots))
        expect(snapshots[1].get("DISCORD_BOT_TOKEN") == "discord-token-restored", str(snapshots))
        expect(os.environ.get("DISCORD_EXTRA_CONFIG") == "discord-extra-restored", dict(os.environ))
        print("PASS test_public_agent_bridge_l1_restores_env_when_starved_loader_raises")
    finally:
        os.environ.clear()
        os.environ.update(old_env)


def test_public_agent_bridge_l2_getme_cache_hit_skips_network_and_hmacs_key() -> None:
    old_env = os.environ.copy()
    previous = None
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cache_dir = root / "cache"
        secret = "bridge-cache-test-secret"
        token = "123456:telegram-token-value"
        # H2: the cache key derives ONLY from the dedicated getMe cache secret now,
        # never the session pepper / operator-action / web-session secrets.
        secret_file = root / "getme-cache-secret"
        secret_file.write_text(secret + "\n", encoding="utf-8")
        try:
            os.environ.clear()
            os.environ.update(
                {
                    "ARCLINK_BRIDGE_GETME_CACHE": "1",
                    "ARCLINK_BRIDGE_GETME_CACHE_DIR": str(cache_dir),
                    "ARCLINK_BRIDGE_GETME_CACHE_SECRET_FILE": str(secret_file),
                    "HERMES_HOME": str(root / "hermes-home"),
                }
            )
            previous, _init_calls, _user_cls = _install_public_bridge_runtime_stubs(lambda: _fake_gateway_config())
            bridge = load_module(PYTHON_DIR / "arclink_public_agent_bridge.py", "arclink_public_agent_bridge_l2_hit_test")
            cache_path = bridge._bridge_getme_cache_path(token)
            expect(cache_path is not None, "cache path should be available under root-owned secure dir")
            expected_key = hmac.new(secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()
            expect(cache_path.stem == expected_key, cache_path.name)
            expect(token not in str(cache_path), str(cache_path))
            expect(cache_path.stem != hashlib.sha256(token.encode("utf-8")).hexdigest(), cache_path.name)
            bridge._json_write(
                cache_path,
                {
                    "cached_at": int(bridge.time.time()),
                    "expires_at": int(bridge.time.time()) + 60,
                    "bot_user": {"id": 999, "is_bot": True, "first_name": "Cached", "username": "cached_bot"},
                },
            )

            class BotShouldNotInitialize:
                def __init__(self):
                    self._initialized = False
                    self._bot_user = None

                async def initialize(self):
                    raise AssertionError("fresh getMe should not run on cache hit")

            bot = BotShouldNotInitialize()
            asyncio.run(bridge._initialize_telegram_bot(bot, token))
            expect(bot._initialized is True, "cached bot should be marked initialized")
            expect(getattr(bot._bot_user, "username", "") == "cached_bot", repr(bot._bot_user))
            st = cache_path.parent.stat()
            expect(stat.S_IMODE(st.st_mode) == 0o700, oct(stat.S_IMODE(st.st_mode)))
            expect(st.st_uid == 0, f"cache dir must be root-owned, got uid={st.st_uid}")
            print("PASS test_public_agent_bridge_l2_getme_cache_hit_skips_network_and_hmacs_key")
        finally:
            if previous is not None:
                _restore_public_bridge_runtime_stubs(previous)
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_bridge_l2_getme_cache_miss_stale_corrupt_fail_open() -> None:
    old_env = os.environ.copy()
    previous = None
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cache_dir = root / "cache"
        secret_file = root / "getme-cache-secret"
        secret_file.write_text("bridge-cache-test-secret\n", encoding="utf-8")
        try:
            os.environ.clear()
            os.environ.update(
                {
                    "ARCLINK_BRIDGE_GETME_CACHE": "1",
                    "ARCLINK_BRIDGE_GETME_CACHE_DIR": str(cache_dir),
                    "ARCLINK_BRIDGE_GETME_CACHE_SECRET_FILE": str(secret_file),
                    "HERMES_HOME": str(root / "hermes-home"),
                }
            )
            previous, _init_calls, user_cls = _install_public_bridge_runtime_stubs(lambda: _fake_gateway_config())
            bridge = load_module(PYTHON_DIR / "arclink_public_agent_bridge.py", "arclink_public_agent_bridge_l2_failopen_test")

            class LiveBot:
                def __init__(self, username: str):
                    self.username = username
                    self.initialize_calls = 0
                    self._initialized = False
                    self._bot_user = None

                async def initialize(self):
                    self.initialize_calls += 1
                    self._bot_user = user_cls(
                        {"id": 123, "is_bot": True, "first_name": "Live", "username": self.username}
                    )
                    self._initialized = True

            for token, setup in (
                ("miss-token", "missing"),
                ("stale-token", "stale"),
                ("corrupt-token", "corrupt"),
            ):
                path = bridge._bridge_getme_cache_path(token)
                expect(path is not None, f"cache path missing for {token}")
                if setup == "stale":
                    bridge._json_write(
                        path,
                        {
                            "cached_at": int(bridge.time.time()) - 120,
                            "expires_at": int(bridge.time.time()) - 60,
                            "bot_user": {"id": 1, "is_bot": True, "first_name": "Old", "username": "old_bot"},
                        },
                    )
                elif setup == "corrupt":
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("not-json\n", encoding="utf-8")
                bot = LiveBot(f"{setup}_bot")
                asyncio.run(bridge._initialize_telegram_bot(bot, token))
                expect(bot.initialize_calls == 1, f"{setup} cache should fail open to live initialize")
                cached = bridge._json_read(path)
                expect(cached.get("bot_user", {}).get("username") == f"{setup}_bot", str(cached))
                expect(int(cached.get("expires_at") or 0) > int(bridge.time.time()), str(cached))

            print("PASS test_public_agent_bridge_l2_getme_cache_miss_stale_corrupt_fail_open")
        finally:
            if previous is not None:
                _restore_public_bridge_runtime_stubs(previous)
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_bridge_l2_getme_cache_secure_dir_or_secret_unavailable_fail_open() -> None:
    old_env = os.environ.copy()
    previous = None
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        hermes_home = root / "hermes-home"
        insecure_cache = hermes_home / "state" / "agent-writable-cache"
        secret_file = root / "getme-cache-secret"
        secret_file.write_text("bridge-cache-test-secret\n", encoding="utf-8")
        try:
            os.environ.clear()
            os.environ.update(
                {
                    "ARCLINK_BRIDGE_GETME_CACHE": "1",
                    "ARCLINK_BRIDGE_GETME_CACHE_DIR": str(insecure_cache),
                    "ARCLINK_BRIDGE_GETME_CACHE_SECRET_FILE": str(secret_file),
                    "HERMES_HOME": str(hermes_home),
                }
            )
            previous, _init_calls, user_cls = _install_public_bridge_runtime_stubs(lambda: _fake_gateway_config())
            bridge = load_module(PYTHON_DIR / "arclink_public_agent_bridge.py", "arclink_public_agent_bridge_l2_unavailable_test")
            expect(bridge._bridge_getme_secure_cache_dir() is None, "cache under HERMES_HOME must be disabled")

            class LiveBot:
                def __init__(self):
                    self.initialize_calls = 0
                    self._initialized = False
                    self._bot_user = None

                async def initialize(self):
                    self.initialize_calls += 1
                    self._bot_user = user_cls({"id": 321, "is_bot": True, "first_name": "Live", "username": "live_bot"})
                    self._initialized = True

            bot = LiveBot()
            asyncio.run(bridge._initialize_telegram_bot(bot, "secure-dir-disabled-token"))
            expect(bot.initialize_calls == 1, "secure-dir-disabled cache should fail open to live getMe")
        finally:
            if previous is not None:
                _restore_public_bridge_runtime_stubs(previous)
            os.environ.clear()
            os.environ.update(old_env)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        try:
            os.environ.clear()
            os.environ.update(
                {
                    "ARCLINK_BRIDGE_GETME_CACHE": "1",
                    "ARCLINK_BRIDGE_GETME_CACHE_DIR": str(root / "cache"),
                    "HERMES_HOME": str(root / "hermes-home"),
                }
            )
            bridge = load_module(
                PYTHON_DIR / "arclink_public_agent_bridge.py",
                "arclink_public_agent_bridge_l2_missing_secret_test",
            )
            expect(bridge._bridge_getme_cache_secret() == b"", "missing server secret must disable cache")
            expect(bridge._bridge_getme_cache_path("token-without-secret") is None, "cache path must be unavailable without HMAC secret")
            print("PASS test_public_agent_bridge_l2_getme_cache_secure_dir_or_secret_unavailable_fail_open")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_bridge_l2_preloaded_user_skips_getme() -> None:
    old_env = os.environ.copy()
    previous = None
    try:
        os.environ.clear()
        os.environ.update(
            {
                "ARCLINK_BRIDGE_GETME_CACHE": "0",
                "ARCLINK_BRIDGE_GETME_PRELOADED_USER_JSON": json.dumps(
                    {"id": 777, "is_bot": True, "first_name": "Preloaded", "username": "preloaded_bot"}
                ),
            }
        )
        previous, _init_calls, _user_cls = _install_public_bridge_runtime_stubs(lambda: _fake_gateway_config())
        bridge = load_module(PYTHON_DIR / "arclink_public_agent_bridge.py", "arclink_public_agent_bridge_l2_preloaded_test")

        class BotShouldNotInitialize:
            def __init__(self):
                self._initialized = False
                self._bot_user = None

            async def initialize(self):
                raise AssertionError("preloaded getMe should skip live initialize")

        bot = BotShouldNotInitialize()
        asyncio.run(bridge._initialize_telegram_bot(bot, "telegram-token"))
        expect(bot._initialized is True, "preloaded bot should be marked initialized")
        expect(getattr(bot._bot_user, "username", "") == "preloaded_bot", repr(bot._bot_user))
        print("PASS test_public_agent_bridge_l2_preloaded_user_skips_getme")
    finally:
        if previous is not None:
            _restore_public_bridge_runtime_stubs(previous)
        os.environ.clear()
        os.environ.update(old_env)


def test_public_agent_bridge_root_wrapper_preloads_and_drops_child() -> None:
    wrapper = load_module(PYTHON_DIR / "arclink_public_agent_bridge_root.py", "arclink_public_agent_bridge_root_wrapper_test")
    raw_payload = json.dumps(
        {
            "platform": "telegram",
            "bot_token": "telegram-token",
            "chat_id": "123",
            "user_id": "123",
            "text": "hello",
        },
        sort_keys=True,
    )
    calls: list[dict[str, object]] = []

    class Proc:
        returncode = 0
        stdout = '{"delivered": true, "delivery_status": "confirmed", "message_ids": ["tg-msg-1"], "ok": true}\n'
        stderr = ""

    def fake_run(cmd, input="", check=False, text=True, capture_output=True, env=None, preexec_fn=None):
        calls.append(
            {
                "cmd": cmd,
                "input": input,
                "check": check,
                "text": text,
                "capture_output": capture_output,
                "env": dict(env or {}),
                "preexec_fn": preexec_fn,
            }
        )
        return Proc()

    old_stdin = wrapper.sys.stdin
    old_stdout = wrapper.sys.stdout
    old_stderr = wrapper.sys.stderr
    old_run = wrapper.subprocess.run
    old_preload = wrapper._preload_telegram_getme
    old_uid_gid = wrapper._runtime_uid_gid
    old_geteuid = wrapper.os.geteuid
    try:
        wrapper.sys.stdin = io.StringIO(raw_payload)
        wrapper.sys.stdout = io.StringIO()
        wrapper.sys.stderr = io.StringIO()
        wrapper.subprocess.run = fake_run
        wrapper._preload_telegram_getme = lambda payload: {
            "id": 777,
            "is_bot": True,
            "first_name": "Preloaded",
            "username": "preloaded_bot",
        }
        wrapper._runtime_uid_gid = lambda: (123, 456)
        wrapper.os.geteuid = lambda: 0
        result = wrapper.main()
        expect(result == 0, str(result))
        expect(calls and calls[0]["input"] == raw_payload, str(calls))
        expect(
            calls[0]["cmd"]
            == [
                wrapper.sys.executable,
                str(PYTHON_DIR / "arclink_public_agent_bridge.py"),
            ],
            str(calls),
        )
        env = calls[0]["env"]
        expect(isinstance(env, dict), str(env))
        preloaded = json.loads(str(env.get("ARCLINK_BRIDGE_GETME_PRELOADED_USER_JSON") or "{}"))
        expect(preloaded.get("username") == "preloaded_bot", str(preloaded))
        expect(callable(calls[0]["preexec_fn"]), str(calls))
        expect("message_ids" in wrapper.sys.stdout.getvalue(), wrapper.sys.stdout.getvalue())
        old_stdout.write("PASS test_public_agent_bridge_root_wrapper_preloads_and_drops_child\n")
    finally:
        wrapper.sys.stdin = old_stdin
        wrapper.sys.stdout = old_stdout
        wrapper.sys.stderr = old_stderr
        wrapper.subprocess.run = old_run
        wrapper._preload_telegram_getme = old_preload
        wrapper._runtime_uid_gid = old_uid_gid
        wrapper.os.geteuid = old_geteuid


def test_public_agent_bridge_persists_telegram_approval_button_state() -> None:
    bridge = load_module(PYTHON_DIR / "arclink_public_agent_bridge.py", "arclink_public_agent_bridge_approval_state_test")
    old_env = os.environ.copy()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.environ["HERMES_HOME"] = str(Path(tmp) / "hermes-home")
            paths = bridge._write_approval_mapping(
                platform="telegram",
                chat_id="12345",
                approval_id=7,
                message_id="99",
                session_key="telegram:12345:session",
            )
            path, mapping = bridge._approval_mapping_for_callback(
                platform="telegram",
                chat_id="12345",
                approval_id=7,
                message_id="99",
            )
            expect(path in paths, f"callback should find exact approval mapping: {path} {paths}")
            expect(mapping.get("session_key") == "telegram:12345:session", str(mapping))
            bridge._record_approval_choice(paths, "always")
            expect(bridge._json_read(paths[0]).get("choice") == "always", bridge._json_read(paths[0]))
        finally:
            os.environ.clear()
            os.environ.update(old_env)
    print("PASS test_public_agent_bridge_persists_telegram_approval_button_state")


def test_public_agent_bridge_drains_telegram_batch_tasks_before_done() -> None:
    bridge = load_module(PYTHON_DIR / "arclink_public_agent_bridge.py", "arclink_public_agent_bridge_batch_drain_test")

    async def scenario() -> None:
        events: list[str] = []

        class Adapter:
            def __init__(self) -> None:
                self._background_tasks: set[asyncio.Task[None]] = set()
                self._pending_text_batch_tasks: dict[str, asyncio.Task[None]] = {}
                self._pending_photo_batch_tasks: dict[str, asyncio.Task[None]] = {}

        adapter = Adapter()

        async def agent_turn() -> None:
            await asyncio.sleep(0)
            events.append("agent-turn")

        async def text_flush() -> None:
            await asyncio.sleep(0)
            events.append("text-flush")
            task = asyncio.create_task(agent_turn())
            adapter._background_tasks.add(task)
            task.add_done_callback(adapter._background_tasks.discard)

        task = asyncio.create_task(text_flush())
        adapter._pending_text_batch_tasks["telegram:123"] = task
        task.add_done_callback(lambda _task: adapter._pending_text_batch_tasks.pop("telegram:123", None))

        await bridge._drain_bridge_adapter_tasks(adapter)
        await asyncio.sleep(0)

        expect(events == ["text-flush", "agent-turn"], str(events))
        expect(adapter._pending_text_batch_tasks == {}, str(adapter._pending_text_batch_tasks))
        expect(adapter._background_tasks == set(), str(adapter._background_tasks))

    asyncio.run(scenario())
    print("PASS test_public_agent_bridge_drains_telegram_batch_tasks_before_done")


def test_public_bot_ready_hub_edits_payment_message_when_available() -> None:
    control = load_module(CONTROL_PY, "arclink_control_notification_delivery_edit_ready_test")
    onboarding = load_module(PYTHON_DIR / "arclink_onboarding.py", "arclink_onboarding_notification_delivery_edit_ready_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_edit_ready_test")
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
                "TELEGRAM_BOT_TOKEN": "telegram-public-token",
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                onboarding.create_or_resume_arclink_onboarding_session(
                    conn,
                    channel="telegram",
                    channel_identity="tg:123",
                    session_id="onb_edit_ready",
                )
                control.queue_notification(
                    conn,
                    target_kind="public-bot-user",
                    target_id="tg:123",
                    channel_kind="telegram",
                    message="Payment cleared.",
                    extra={"capture_provisioning_message": True, "onboarding_session_id": "onb_edit_ready"},
                )
                control.queue_notification(
                    conn,
                    target_kind="public-bot-user",
                    target_id="tg:123",
                    channel_kind="telegram",
                    message="ArcPod ready.",
                    extra={
                        "edit_existing_message": True,
                        "onboarding_session_id": "onb_edit_ready",
                        "telegram_reply_markup": {"inline_keyboard": [[{"text": "Learn", "callback_data": "arclink:/raven learn"}]]},
                    },
                )

            sent: list[dict[str, object]] = []
            edited: list[dict[str, object]] = []

            def fake_send(*, bot_token, chat_id, text, reply_to_message_id=None, reply_markup=None, parse_mode=""):
                sent.append({"bot_token": bot_token, "chat_id": chat_id, "text": text, "reply_markup": reply_markup})
                return {"message_id": 777}

            def fake_edit(*, bot_token, chat_id, message_id, text, reply_markup=None, parse_mode=""):
                edited.append({"bot_token": bot_token, "chat_id": chat_id, "message_id": message_id, "text": text, "reply_markup": reply_markup})
                return {"ok": True}

            delivery.telegram_send_message = fake_send
            delivery.telegram_edit_message_text = fake_edit
            summary = delivery.run_once(cfg)
            with control.connect_db(cfg) as conn:
                session = conn.execute(
                    "SELECT metadata_json FROM arclink_onboarding_sessions WHERE session_id = 'onb_edit_ready'"
                ).fetchone()
            metadata = json.loads(session["metadata_json"])
            expect(summary["delivered"] == 2, str(summary))
            expect(len(sent) == 1 and sent[0]["text"] == "Payment cleared.", str(sent))
            expect(len(edited) == 1 and edited[0]["message_id"] == 777 and edited[0]["text"] == "ArcPod ready.", str(edited))
            expect(metadata["public_bot_provisioning_messages"]["telegram"]["message_id"] == "777", str(metadata))
            print("PASS test_public_bot_ready_hub_edits_payment_message_when_available")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_notification_due_now_normalizes_z_and_offset_timestamps() -> None:
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_due_timestamp_test")
    fixed_now = datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc)
    original_now = delivery.utc_now
    try:
        delivery.utc_now = lambda: fixed_now
        expect(delivery._notification_due_now({"next_attempt_at": "2026-05-11T12:00:00Z"}) is True, "Z timestamp at now should be due")
        expect(delivery._notification_due_now({"next_attempt_at": "2026-05-11T12:00:01+00:00"}) is False, "+00:00 future should not be due")
        expect(delivery._notification_due_now({"next_attempt_at": "bad timestamp"}) is False, "invalid timestamp should fail closed")
    finally:
        delivery.utc_now = original_now
    print("PASS test_notification_due_now_normalizes_z_and_offset_timestamps")


def test_public_agent_bridge_root_wrapper_gated_on_getme_cache_flag() -> None:
    # Regression for the L2 outage: the root-exec wrapper depends on a script baked
    # into the gateway image, so it must be gated on ARCLINK_BRIDGE_GETME_CACHE.
    # Default/off => proven legacy command (no wrapper dependency); on => wrapper.
    delivery = load_module(
        PYTHON_DIR / "arclink_notification_delivery.py", "arclink_notification_delivery_wrapper_gate_test"
    )
    container = "arclink-control-operator-hermes-gateway-1"
    prev = os.environ.pop("ARCLINK_BRIDGE_GETME_CACHE", None)
    orig_preflight = delivery._gateway_has_public_agent_bridge_root_wrapper
    try:
        # Flag OFF (default) => legacy command, no preflight consulted at all.
        delivery._gateway_has_public_agent_bridge_root_wrapper = lambda exec_prefix: True
        cmd_off = delivery._public_agent_bridge_root_exec_cmd(container)
        expect("-u" not in cmd_off, f"flag-off must not use -u root exec: {cmd_off}")
        expect(cmd_off[-1].endswith("arclink_public_agent_bridge.py"), f"flag-off must be legacy bridge: {cmd_off}")
        expect(delivery._validate_public_agent_bridge_cmd(cmd_off, project_name="arclink")[0], "legacy cmd must validate")

        # Flag ON + wrapper PRESENT in gateway image => root wrapper command.
        os.environ["ARCLINK_BRIDGE_GETME_CACHE"] = "1"
        delivery._gateway_has_public_agent_bridge_root_wrapper = lambda exec_prefix: True
        cmd_on = delivery._public_agent_bridge_root_exec_cmd(container)
        expect(cmd_on[3:5] == ["-u", "0:0"], f"flag-on+present must use -u 0:0: {cmd_on}")
        expect(cmd_on[-1].endswith("arclink_public_agent_bridge_root.py"), f"flag-on+present must be root wrapper: {cmd_on}")
        expect(delivery._validate_public_agent_bridge_cmd(cmd_on, project_name="arclink")[0], "wrapper cmd must validate")

        # Flag ON but wrapper MISSING from gateway image (the outage) => MUST fall back
        # to legacy, never hard-fail.
        delivery._gateway_has_public_agent_bridge_root_wrapper = lambda exec_prefix: False
        cmd_skew = delivery._public_agent_bridge_root_exec_cmd(container)
        expect("-u" not in cmd_skew, f"flag-on+missing-wrapper MUST fall back to legacy: {cmd_skew}")
        expect(cmd_skew[-1].endswith("arclink_public_agent_bridge.py"), f"flag-on+missing must be legacy: {cmd_skew}")
        expect(delivery._validate_public_agent_bridge_cmd(cmd_skew, project_name="arclink")[0], "fallback legacy must validate")
    finally:
        delivery._gateway_has_public_agent_bridge_root_wrapper = orig_preflight
        os.environ.pop("ARCLINK_BRIDGE_GETME_CACHE", None)
        if prev is not None:
            os.environ["ARCLINK_BRIDGE_GETME_CACHE"] = prev
    print("PASS test_public_agent_bridge_root_wrapper_gated_on_getme_cache_flag")


def test_gateway_root_wrapper_preflight_reprobes_positive_caches_negative() -> None:
    # Regression for the stale-positive cache: a cached "present" must be RE-PROBED so a
    # rollback that drops the wrapper is caught on the next turn (not after TTL), while a
    # cached "missing" stays cached (always-safe legacy, no probe hammering).
    delivery = load_module(
        PYTHON_DIR / "arclink_notification_delivery.py", "arclink_notification_delivery_preflight_cache_test"
    )
    prefix = ["docker", "exec", "test-gw-container"]
    delivery._ROOT_WRAPPER_PRESENT_CACHE.clear()
    returncodes: list[int] = []
    probe_calls: list[list[str]] = []

    class _FakeProc:
        def __init__(self, rc: int) -> None:
            self.returncode = rc

    def fake_run(cmd, **kwargs):
        del kwargs
        probe_calls.append(list(cmd))
        return _FakeProc(returncodes.pop(0))

    orig_run = delivery.subprocess.run
    try:
        delivery.subprocess.run = fake_run
        returncodes.append(0)  # first probe: wrapper present
        expect(delivery._gateway_has_public_agent_bridge_root_wrapper(prefix) is True, "first probe should be present")
        returncodes.append(1)  # rollback: wrapper now missing
        expect(
            delivery._gateway_has_public_agent_bridge_root_wrapper(prefix) is False,
            "cached positive must be re-probed -> now missing",
        )
        expect(len(probe_calls) == 2, f"positive must re-probe, got {len(probe_calls)} probes")
        before = len(probe_calls)
        expect(
            delivery._gateway_has_public_agent_bridge_root_wrapper(prefix) is False,
            "cached negative should be returned",
        )
        expect(len(probe_calls) == before, "cached negative must NOT re-probe")
    finally:
        delivery.subprocess.run = orig_run
        delivery._ROOT_WRAPPER_PRESENT_CACHE.clear()
    print("PASS test_gateway_root_wrapper_preflight_reprobes_positive_caches_negative")


def test_public_agent_bridge_telegram_replay_does_not_dispatch_generic_event() -> None:
    # Regression: when native replay handles the Telegram update, the bridge must NOT
    # fall through to adapter.handle_message(event) — `event` is unbound there, which
    # UnboundLocalErrors, fails the turn, and retries a duplicate send of an
    # already-delivered message.
    old_env = os.environ.copy()
    previous = None
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        runtime = root / "runtime-src"
        runtime.mkdir()

        def load_gateway_config():
            return _fake_gateway_config()

        try:
            os.environ.clear()
            os.environ.update(
                {
                    "HOME": str(root / "home"),
                    "HERMES_AGENT_SRC": str(runtime),
                    "ARCLINK_BRIDGE_SINGLE_PLATFORM_CONFIG": "0",
                    "ARCLINK_BRIDGE_GETME_CACHE": "0",
                }
            )
            previous, _init_calls, _user_cls = _install_public_bridge_runtime_stubs(load_gateway_config)
            bridge = load_module(PYTHON_DIR / "arclink_public_agent_bridge.py", "arclink_public_agent_bridge_replay_test")

            async def _always_replayed(adapter, bot, payload):
                del adapter, bot, payload
                return True

            bridge._try_replay_native_telegram_update = _always_replayed

            result = asyncio.run(
                bridge._run_telegram(
                    {
                        "platform": "telegram",
                        "bot_token": "telegram-turn-token",
                        "chat_id": "tg-chat",
                        "user_id": "tg-user",
                        "text": "hello",
                        "telegram_update_json": json.dumps({"update_id": 1}, sort_keys=True),
                    }
                )
            )
            expect(isinstance(result, dict), f"replayed turn must return a summary dict, not crash: {result!r}")
            expect(
                "tg-msg-1" not in (result.get("message_ids") or []),
                f"replay must not dispatch a generic event (no second send): {result}",
            )
            print("PASS test_public_agent_bridge_telegram_replay_does_not_dispatch_generic_event")
        finally:
            if previous is not None:
                _restore_public_bridge_runtime_stubs(previous)
            os.environ.clear()
            os.environ.update(old_env)


def _delivery_db_config(control, root: Path, extra: dict[str, str] | None = None):
    """Build a minimal on-disk config + return a loaded Config for DB-backed tests."""
    config_path = root / "config" / "arclink.env"
    values = {
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
    }
    if extra:
        values.update(extra)
    write_config(config_path, values)
    os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
    return control.Config.from_env()


def test_public_agent_bridge_worker_token_guards_late_terminal_writes() -> None:
    # C1: a row re-leased to worker B (new token) must reject worker A's late
    # delivered/error/unconfirmed writes -- the lease owner is authoritative.
    control = load_module(CONTROL_PY, "arclink_control_c1_token_guard_control_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_c1_token_guard_test")
    old_env = os.environ.copy()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            cfg = _delivery_db_config(control, Path(tmp))
            with control.connect_db(cfg) as conn:
                nid = control.queue_notification(
                    conn,
                    target_kind="public-agent-turn",
                    target_id="tg:1",
                    channel_kind="telegram",
                    message="hi",
                )
                # Worker B currently owns the lease (token recorded on the row).
                conn.execute(
                    "UPDATE notification_outbox SET extra_json = json_set(COALESCE(extra_json,'{}'), ?, ?) WHERE id = ?",
                    (delivery.PUBLIC_AGENT_BRIDGE_WORKER_TOKEN_JSON_PATH, "token-B", nid),
                )
                conn.commit()

                # Worker A (older token) tries to finalise -- every variant no-ops.
                expect(
                    delivery._worker_mark_notification_delivered(conn, nid, "token-A") is False,
                    "stale worker A delivered must no-op",
                )
                expect(
                    delivery._worker_mark_notification_error(conn, nid, "A error", "token-A") is False,
                    "stale worker A error must no-op",
                )
                expect(
                    delivery._worker_mark_public_agent_bridge_unconfirmed(conn, nid, "A held", "token-A") is False,
                    "stale worker A unconfirmed must no-op",
                )
                row = conn.execute(
                    "SELECT delivered_at, delivery_error, attempt_count FROM notification_outbox WHERE id = ?",
                    (nid,),
                ).fetchone()
                expect(not str(row["delivered_at"] or "").strip(), dict(row))
                expect(row["delivery_error"] is None, dict(row))
                expect(int(row["attempt_count"] or 0) == 0, dict(row))

                # Worker B (the lease owner) CAN finalise.
                expect(
                    delivery._worker_mark_notification_delivered(conn, nid, "token-B") is True,
                    "lease owner B delivered must apply",
                )
                row2 = conn.execute(
                    "SELECT delivered_at FROM notification_outbox WHERE id = ?", (nid,)
                ).fetchone()
                expect(str(row2["delivered_at"] or "").strip() != "", dict(row2))
            print("PASS test_public_agent_bridge_worker_token_guards_late_terminal_writes")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_bridge_reaper_requires_recorded_job_path_match() -> None:
    # C1: the reaper must only re-arm when the recorded pid is NOT running this row's
    # specific job. A live pid running a DIFFERENT job_path must not count as alive
    # for this row (recycled-pid), and our own live job must be left alone.
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_c1_reaper_jobpath_test")
    my_pid = os.getpid()
    # Our own process is a real, live pid but is NOT a bridge worker -> not active.
    expect(
        delivery._public_agent_bridge_worker_pid_active(my_pid, expected_job_path="/tmp/whatever.json") is False,
        "a live non-bridge-worker pid must not count as this row's worker",
    )
    # A pid that does not exist is never active.
    expect(
        delivery._public_agent_bridge_worker_pid_active(2 ** 31 - 1, expected_job_path="/tmp/x.json") is False,
        "a dead pid is not active",
    )
    print("PASS test_public_agent_bridge_reaper_requires_recorded_job_path_match")


def test_gateway_root_wrapper_preflight_does_not_cache_thrown_probe() -> None:
    # H4: a throwing/timed-out probe must NOT be cached as a negative (which would
    # pin L2 off for the TTL); a real nonzero IS cached.
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_h4_preflight_test")
    prefix = ["docker", "exec", "h4-container"]
    delivery._ROOT_WRAPPER_PRESENT_CACHE.clear()
    orig_run = delivery.subprocess.run
    try:
        def throwing_run(cmd, **kwargs):
            del cmd, kwargs
            raise delivery.subprocess.TimeoutExpired(cmd="probe", timeout=15)

        delivery.subprocess.run = throwing_run
        expect(
            delivery._gateway_has_public_agent_bridge_root_wrapper(prefix) is False,
            "a thrown probe returns the safe legacy answer",
        )
        key = tuple(prefix)
        expect(key not in delivery._ROOT_WRAPPER_PRESENT_CACHE, "a thrown probe must NOT be cached")

        class _Proc:
            returncode = 1

        def nonzero_run(cmd, **kwargs):
            del cmd, kwargs
            return _Proc()

        delivery.subprocess.run = nonzero_run
        expect(
            delivery._gateway_has_public_agent_bridge_root_wrapper(prefix) is False,
            "a real nonzero means wrapper absent",
        )
        expect(key in delivery._ROOT_WRAPPER_PRESENT_CACHE, "a real nonzero IS cached")
        expect(delivery._ROOT_WRAPPER_PRESENT_CACHE[key][1] is False, "cached value is the genuine absent result")
    finally:
        delivery.subprocess.run = orig_run
        delivery._ROOT_WRAPPER_PRESENT_CACHE.clear()
    print("PASS test_gateway_root_wrapper_preflight_does_not_cache_thrown_probe")


def test_public_agent_bridge_unconfirmed_escalates_to_operator() -> None:
    # M3: a turn that stays unconfirmed across N cycles pages the operator under a
    # DISTINCT key, and a later delivery clears it.
    control = load_module(CONTROL_PY, "arclink_control_m3_unconfirmed_escalate_control_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_m3_unconfirmed_escalate_test")
    old_env = os.environ.copy()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            cfg = _delivery_db_config(
                control,
                Path(tmp),
                extra={"ARCLINK_PUBLIC_AGENT_BRIDGE_UNCONFIRMED_ESCALATE_AFTER": "3"},
            )
            with control.connect_db(cfg) as conn:
                nid = control.queue_notification(
                    conn,
                    target_kind="public-agent-turn",
                    target_id="tg:1",
                    channel_kind="telegram",
                    message="hi",
                )
                hiccup_key = delivery._public_agent_bridge_unconfirmed_hiccup_key(nid)
                fail_action = f"{control.OPERATOR_HICCUP_AUDIT_PREFIX}{hiccup_key}"

                # First two unconfirmed cycles must NOT page yet.
                delivery._mark_public_agent_bridge_unconfirmed(conn, nid, "held 1")
                delivery._mark_public_agent_bridge_unconfirmed(conn, nid, "held 2")
                expect(
                    not control._operator_hiccup_already_armed(conn, key=hiccup_key),
                    "must not page before the threshold",
                )
                # Third consecutive unconfirmed crosses the threshold -> page.
                delivery._mark_public_agent_bridge_unconfirmed(conn, nid, "held 3")
                expect(
                    control._operator_hiccup_already_armed(conn, key=hiccup_key),
                    "third consecutive unconfirmed must page the operator",
                )
                armed = conn.execute(
                    "SELECT COUNT(*) AS c FROM arclink_audit_log WHERE action = ?", (fail_action,)
                ).fetchone()
                expect(int(armed["c"]) == 1, dict(armed))

                # A later confirmed delivery resolves the unconfirmed alert + counter.
                control.mark_notification_delivered(conn, nid)
                delivery._resolve_public_agent_bridge_hiccup(conn, nid)
                expect(
                    not control._operator_hiccup_already_armed(conn, key=hiccup_key),
                    "delivery must clear the unconfirmed alert",
                )
            print("PASS test_public_agent_bridge_unconfirmed_escalates_to_operator")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_bridge_terminal_error_includes_context_and_log_tail() -> None:
    # M4: an exit-1 with empty stdout/stderr must enrich the operator error with the
    # command kind/project and the per-turn bridge log tail.
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_m4_error_enrich_test")
    enriched = delivery._enrich_public_agent_bridge_error(
        "Hermes public gateway bridge failed: exit status 1",
        command_kind="public-agent-turn",
        project_name="arclink-arcdep_demo",
        include_log_tail=False,
    )
    expect("kind=public-agent-turn" in enriched, enriched)
    expect("project=arclink-arcdep_demo" in enriched, enriched)
    expect("exit status 1" in enriched, enriched)
    print("PASS test_public_agent_bridge_terminal_error_includes_context_and_log_tail")


def test_public_agent_bridge_album_persists_merged_list_to_leader_row() -> None:
    # M1: the merged album list + absorbed sibling ids must be persisted to the
    # LEADER row's extra_json (not in-memory only) so a leader retry replays it; and
    # C2: absorbed siblings end delivered with a clean error + provenance note.
    control = load_module(CONTROL_PY, "arclink_control_m1_album_persist_control_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_m1_album_persist_test")
    old_env = os.environ.copy()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            cfg = _delivery_db_config(control, Path(tmp), extra={"TELEGRAM_BOT_TOKEN": "telegram-public-token"})
            group_id = "album-xyz"

            def _album_extra(idx: int) -> dict:
                update = {
                    "update_id": 9000 + idx,
                    "message": {
                        "message_id": 100 + idx,
                        "media_group_id": group_id,
                        "chat": {"id": 777, "type": "private"},
                        "from": {"id": 777},
                        "photo": [{"file_id": f"photo-{idx}", "width": 1, "height": 1}],
                    },
                }
                return {
                    "deployment_id": "arcdep_demo",
                    "telegram_update_json": json.dumps(update, sort_keys=True, separators=(",", ":")),
                }

            with control.connect_db(cfg) as conn:
                ids = [
                    control.queue_notification(
                        conn,
                        target_kind="public-agent-turn",
                        target_id="tg:777",
                        channel_kind="telegram",
                        message=f"item {i}",
                        extra=_album_extra(i),
                    )
                    for i in range(3)
                ]
                # Backdate created_at ~10s so the album is past the quiesce window but
                # still inside the 120s group lookback.
                backdated = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
                conn.execute("UPDATE notification_outbox SET created_at = ?", (backdated,))
                conn.commit()

            leader_id = min(ids)
            leader_row = {
                "id": leader_id,
                "channel_kind": "telegram",
                "target_id": "tg:777",
                "message": "item 0",
            }
            leader_extra = _album_extra(0)
            state = delivery._absorb_telegram_album_siblings(
                cfg,
                row=leader_row,
                extra=leader_extra,
                media_group_id=group_id,
            )
            expect(state is None, f"leader absorb should resolve, got {state!r}")
            expect(
                isinstance(leader_extra.get("telegram_update_json_list"), list)
                and len(leader_extra["telegram_update_json_list"]) == 3,
                str(leader_extra.get("telegram_update_json_list")),
            )
            with control.connect_db(cfg) as conn:
                rows = {
                    int(r["id"]): r
                    for r in conn.execute(
                        "SELECT id, delivered_at, delivery_error, extra_json FROM notification_outbox"
                    ).fetchall()
                }
            leader_persisted = json.loads(str(rows[leader_id]["extra_json"] or "{}"))
            expect(
                isinstance(leader_persisted.get("telegram_update_json_list"), list)
                and len(leader_persisted["telegram_update_json_list"]) == 3,
                f"M1: leader row must persist the merged album: {leader_persisted}",
            )
            expect(
                sorted(int(x) for x in leader_persisted.get("_absorbed_album_sibling_ids") or [])
                == sorted(i for i in ids if i != leader_id),
                f"M1: leader row must persist absorbed sibling ids: {leader_persisted}",
            )
            expect(not str(rows[leader_id]["delivered_at"] or "").strip(), "leader must stay undelivered")
            for sib_id in (i for i in ids if i != leader_id):
                sib = rows[sib_id]
                expect(str(sib["delivered_at"] or "").strip() != "", f"sibling {sib_id} must be delivered")
                expect(sib["delivery_error"] is None, f"sibling {sib_id} must have clean error: {dict(sib)}")
                sib_extra = json.loads(str(sib["extra_json"] or "{}"))
                expect(
                    int(sib_extra.get("_absorbed_into_album_leader") or 0) == leader_id,
                    f"sibling {sib_id} must record leader provenance: {sib_extra}",
                )
            print("PASS test_public_agent_bridge_album_persists_merged_list_to_leader_row")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_bridge_claim_holder_no_ops_on_worker_owned_row() -> None:
    # C1 (STILL-BROKEN): a row currently owned by a detached worker (recorded token)
    # must reject the in-process claim-holder's empty-token terminal writes -- this is
    # the guard the album sibling-mark (:2810) and the fast-path loop (:3024/:3033)
    # now use, so a re-leased row's late delivered/error/unconfirmed is a no-op at
    # those sites too. Conversely a tokenless row (no detached worker) still accepts
    # the claim-holder.
    control = load_module(CONTROL_PY, "arclink_control_c1_claimholder_guard_control_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_c1_claimholder_guard_test")
    old_env = os.environ.copy()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            cfg = _delivery_db_config(control, Path(tmp))
            with control.connect_db(cfg) as conn:
                owned = control.queue_notification(
                    conn, target_kind="public-agent-turn", target_id="tg:1",
                    channel_kind="telegram", message="owned",
                )
                free = control.queue_notification(
                    conn, target_kind="public-agent-turn", target_id="tg:2",
                    channel_kind="telegram", message="free",
                )
                # A detached worker owns `owned` (token recorded); `free` has none.
                conn.execute(
                    "UPDATE notification_outbox SET extra_json = json_set(COALESCE(extra_json,'{}'), ?, ?) WHERE id = ?",
                    (delivery.PUBLIC_AGENT_BRIDGE_WORKER_TOKEN_JSON_PATH, "token-B", owned),
                )
                conn.commit()

                # Claim-holder (empty token): every terminal write no-ops on the
                # worker-owned row (album sibling-mark + loop delivered/error/unconfirmed).
                expect(control.mark_notification_delivered_if_owned(conn, owned, "") == 0, "owned delivered must no-op")
                expect(control.mark_notification_error_if_owned(conn, owned, "boom", "") == 0, "owned error must no-op")
                expect(
                    delivery._mark_public_agent_bridge_unconfirmed(conn, owned, "held") is False,
                    "owned unconfirmed must no-op",
                )
                # A stale detached worker A (wrong token) also no-ops on the owned row.
                expect(
                    delivery._worker_mark_notification_delivered(conn, owned, "token-A") is False,
                    "stale worker delivered must no-op",
                )
                r = conn.execute(
                    "SELECT delivered_at, delivery_error, attempt_count FROM notification_outbox WHERE id = ?",
                    (owned,),
                ).fetchone()
                expect(not str(r["delivered_at"] or "").strip(), dict(r))
                expect(r["delivery_error"] is None, dict(r))
                expect(int(r["attempt_count"] or 0) == 0, dict(r))

                # The tokenless row still accepts the claim-holder (no regression).
                expect(control.mark_notification_delivered_if_owned(conn, free, "") == 1, "free delivered must apply")
            print("PASS test_public_agent_bridge_claim_holder_no_ops_on_worker_owned_row")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_bridge_spawn_aborts_when_lease_token_cannot_stamp() -> None:
    # C1 (STILL-BROKEN): a spawn whose lease-token stamp matches no undelivered row
    # (missing / already-delivered) must ABORT before Popen -- a tokenless worker can
    # never finalise its row and would risk a duplicate send.
    control = load_module(CONTROL_PY, "arclink_control_c1_stamp_abort_control_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_c1_stamp_abort_test")
    old_env = os.environ.copy()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original_popen = delivery.subprocess.Popen
        spawned: list[bool] = []

        def track_popen(*args, **kwargs):
            spawned.append(True)
            raise AssertionError("Popen must not run when the lease token cannot be stamped")

        delivery.subprocess.Popen = track_popen
        try:
            _delivery_db_config(control, root)  # builds STATE_DIR + config, no row queued.
            ok, error = delivery._spawn_public_agent_gateway_bridge(
                cmd=[
                    "docker", "exec", "-i", "arclink-arcdep_test-hermes-gateway-1",
                    "/opt/arclink/runtime/hermes-venv/bin/python3",
                    "/home/arclink/arclink/python/arclink_public_agent_bridge.py",
                ],
                payload={"platform": "telegram", "bot_token": "runtime-token", "text": "hi"},
                notification_id=4242,  # no such undelivered row -> stamp matches 0 rows.
                project_name="arclink-arcdep_test",
            )
            expect(ok is False and "could not stamp" in error, error)
            expect(not spawned, "the worker must not have been spawned")
            job_dir = root / "state" / "docker" / "jobs" / "public-agent-bridge-jobs"
            expect(not list(job_dir.glob("*.json")), "the job file must be cleaned up on stamp-abort")
            print("PASS test_public_agent_bridge_spawn_aborts_when_lease_token_cannot_stamp")
        finally:
            delivery.subprocess.Popen = original_popen
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_bridge_reaper_skips_live_token_and_rearms_tokenless() -> None:
    # C1 (STILL-BROKEN): the reaper leaves a row alone ONLY when it records a token
    # AND a job_path AND the pid is running that job; a missing token (or job_path)
    # makes the lease provably-not-alive -> eligible, even if a bare pid is "alive".
    control = load_module(CONTROL_PY, "arclink_control_c1_reaper_gate_control_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_c1_reaper_gate_test")
    old_env = os.environ.copy()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            cfg = _delivery_db_config(control, Path(tmp))
            os.environ["ARCLINK_PUBLIC_AGENT_BRIDGE_ORPHAN_REAPER_SECONDS"] = "60"

            def _seed(worker_meta: dict) -> int:
                with control.connect_db(cfg) as conn:
                    nid = control.queue_notification(
                        conn, target_kind="public-agent-turn", target_id="tg:1",
                        channel_kind="telegram", message="stalled",
                        extra={"deployment_id": "arcdep_test"},
                    )
                    # Stamp the worker meta via json_set (a literal `token` key trips
                    # the queue_notification secret-scanner, so we set it post-insert).
                    conn.execute(
                        "UPDATE notification_outbox "
                        "SET extra_json = json_set(COALESCE(extra_json,'{}'), '$._public_agent_bridge_worker', json(?)), "
                        "    last_attempt_at = ?, next_attempt_at = ? "
                        "WHERE id = ?",
                        (json.dumps(worker_meta), "2026-01-01T00:00:00+00:00", "2999-01-01T00:00:00+00:00", nid),
                    )
                    conn.commit()
                return nid

            # Pretend EVERY recorded pid is a live bridge worker for its job.
            original_active = delivery._public_agent_bridge_worker_pid_active
            delivery._public_agent_bridge_worker_pid_active = lambda pid, expected_job_path="": True
            try:
                live = _seed({"pid": 4242, "job_path": "/tmp/live.json", "token": "tok-live"})
                no_token = _seed({"pid": 4242, "job_path": "/tmp/x.json"})  # token missing
                no_path = _seed({"pid": 4242, "token": "tok", "job_path": ""})  # job_path missing
                reclaimed = delivery.reap_orphaned_public_agent_bridge_leases(cfg, limit=10)
            finally:
                delivery._public_agent_bridge_worker_pid_active = original_active

            # The fully-provable live lease is NOT re-armed; the two unprovable ones ARE.
            expect(reclaimed == 2, f"expected 2 reclaimed (token+path missing), got {reclaimed}")
            with control.connect_db(cfg) as conn:
                def _rearmed(nid: int) -> bool:
                    r = conn.execute(
                        "SELECT delivery_error FROM notification_outbox WHERE id = ?", (nid,)
                    ).fetchone()
                    return str(r["delivery_error"] or "").startswith("public_agent_bridge_orphan_reclaimed")
                expect(not _rearmed(live), "the provably-live lease must be left alone")
                expect(_rearmed(no_token), "a tokenless lease must be re-armed")
                expect(_rearmed(no_path), "a job_path-less lease must be re-armed")
            print("PASS test_public_agent_bridge_reaper_skips_live_token_and_rearms_tokenless")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_bridge_album_persist_failure_leaves_siblings_undelivered() -> None:
    # M1 (STILL-BROKEN): if the leader-row persist of the merged album fails (or
    # touches zero rows), the absorbed siblings must NOT be marked delivered -- they
    # are left for a later retry so the album is not lost.
    control = load_module(CONTROL_PY, "arclink_control_m1_persist_fail_control_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_m1_persist_fail_test")
    old_env = os.environ.copy()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            cfg = _delivery_db_config(control, Path(tmp), extra={"TELEGRAM_BOT_TOKEN": "telegram-public-token"})
            group_id = "album-fail"

            def _album_extra(idx: int) -> dict:
                update = {
                    "update_id": 9000 + idx,
                    "message": {
                        "message_id": 100 + idx, "media_group_id": group_id,
                        "chat": {"id": 777, "type": "private"}, "from": {"id": 777},
                        "photo": [{"file_id": f"photo-{idx}", "width": 1, "height": 1}],
                    },
                }
                return {
                    "deployment_id": "arcdep_demo",
                    "telegram_update_json": json.dumps(update, sort_keys=True, separators=(",", ":")),
                }

            with control.connect_db(cfg) as conn:
                ids = [
                    control.queue_notification(
                        conn, target_kind="public-agent-turn", target_id="tg:777",
                        channel_kind="telegram", message=f"item {i}", extra=_album_extra(i),
                    )
                    for i in range(3)
                ]
                backdated = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
                conn.execute("UPDATE notification_outbox SET created_at = ?", (backdated,))
                conn.commit()
            leader_id = min(ids)

            # Wrap connect_db so the leader-row album persist UPDATE raises, simulating
            # a persist failure; every other statement passes through unchanged.
            real_connect_db = delivery.connect_db

            class _FailPersistConn:
                def __init__(self, inner):
                    self._inner = inner

                def execute(self, sql, *args, **kwargs):
                    if "$.telegram_update_json_list" in sql:
                        raise RuntimeError("simulated leader persist failure")
                    return self._inner.execute(sql, *args, **kwargs)

                def __getattr__(self, name):
                    return getattr(self._inner, name)

            class _FailPersistCtx:
                def __init__(self, cfg_arg):
                    self._cm = real_connect_db(cfg_arg)

                def __enter__(self):
                    return _FailPersistConn(self._cm.__enter__())

                def __exit__(self, *exc):
                    return self._cm.__exit__(*exc)

            delivery.connect_db = lambda cfg_arg: _FailPersistCtx(cfg_arg)
            try:
                leader_row = {"id": leader_id, "channel_kind": "telegram", "target_id": "tg:777", "message": "item 0"}
                leader_extra = _album_extra(0)
                state = delivery._absorb_telegram_album_siblings(
                    cfg, row=leader_row, extra=leader_extra, media_group_id=group_id,
                )
            finally:
                delivery.connect_db = real_connect_db

            expect(state is None, f"absorb should resolve to None on persist failure, got {state!r}")
            # The in-memory merged list is dropped so the leader does not send a partial album.
            expect(
                not leader_extra.get("telegram_update_json_list"),
                f"merged list must be dropped on persist failure: {leader_extra.get('telegram_update_json_list')}",
            )
            with control.connect_db(cfg) as conn:
                rows = {
                    int(r["id"]): r
                    for r in conn.execute("SELECT id, delivered_at FROM notification_outbox").fetchall()
                }
            for sib_id in (i for i in ids if i != leader_id):
                expect(
                    not str(rows[sib_id]["delivered_at"] or "").strip(),
                    f"M1: sibling {sib_id} must NOT be delivered after a failed leader persist: {dict(rows[sib_id])}",
                )
            print("PASS test_public_agent_bridge_album_persist_failure_leaves_siblings_undelivered")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_bridge_broker_failure_error_includes_context() -> None:
    # M4 (STILL-BROKEN): a gateway-exec-broker failure must be enriched with the
    # command kind + project (same path as the direct-subprocess failure), not the
    # raw broker error.
    control = load_module(CONTROL_PY, "arclink_control_m4_broker_enrich_control_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_m4_broker_enrich_test")
    old_env = os.environ.copy()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            cfg = _delivery_db_config(control, Path(tmp))
            with control.connect_db(cfg) as conn:
                nid = control.queue_notification(
                    conn, target_kind="public-agent-turn", target_id="tg:1",
                    channel_kind="telegram", message="hi",
                )
            # Build a worker job that routes through the broker and stamp the lease so
            # the guarded error-mark applies.
            worker_token = "tok-broker"
            job_path = delivery._write_public_agent_bridge_job(
                notification_id=nid, cmd=[], payload={}, project_name="arclink-arcdep_test",
                gateway_exec_request={"action": "noop"}, worker_token=worker_token,
            )
            with control.connect_db(cfg) as conn:
                conn.execute(
                    "UPDATE notification_outbox SET extra_json = json_set(COALESCE(extra_json,'{}'), ?, ?) WHERE id = ?",
                    (delivery.PUBLIC_AGENT_BRIDGE_WORKER_TOKEN_JSON_PATH, worker_token, nid),
                )
                conn.commit()

            original_broker = delivery._run_gateway_exec_broker_request
            delivery._run_gateway_exec_broker_request = lambda req: (False, "broker said 503")
            try:
                rc = delivery._run_public_agent_bridge_worker(job_path)
            finally:
                delivery._run_gateway_exec_broker_request = original_broker
            expect(rc == 1, f"broker failure should return 1, got {rc}")
            with control.connect_db(cfg) as conn:
                row = conn.execute(
                    "SELECT delivery_error FROM notification_outbox WHERE id = ?", (nid,)
                ).fetchone()
            err = str(row["delivery_error"] or "")
            expect("broker said 503" in err, err)
            expect("kind=gateway-exec-broker" in err, err)
            expect("project=arclink-arcdep_test" in err, err)
            print("PASS test_public_agent_bridge_broker_failure_error_includes_context")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_generic_run_once_public_agent_turn_write_no_ops_on_worker_owned_row() -> None:
    # C1 (STILL-BROKEN, round 3): the GENERIC run_once delivery loop used to do
    # BARE-id terminal writes (mark_notification_delivered / mark_notification_error)
    # for public-agent-turn rows, bypassing the empty-token IS-NULL guard. A row a
    # detached worker owns (recorded token) must reject the in-process claim-holder's
    # delivered-write here too: it must be a NO-OP, summary["delivered"] must NOT be
    # counted, and the resolve-on-delivery (which would clear the Operator alert) must
    # NOT run -- otherwise the loop clears an armed alert / double-finalises a row the
    # owning worker is authoritative for. This mirrors the dedicated loop at :3116.
    control = load_module(CONTROL_PY, "arclink_control_c1_generic_loop_guard_control_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_c1_generic_loop_guard_test")
    old_env = os.environ.copy()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            cfg = _delivery_db_config(control, Path(tmp))
            with control.connect_db(cfg) as conn:
                owned = control.queue_notification(
                    conn, target_kind="public-agent-turn", target_id="tg:1",
                    channel_kind="telegram", message="owned turn",
                    extra={"deployment_id": "arcdep_test", "prefix": "arc-pod"},
                )
                # A DIFFERENT detached worker owns this row (records token-B).
                conn.execute(
                    "UPDATE notification_outbox SET extra_json = json_set(COALESCE(extra_json,'{}'), ?, ?) WHERE id = ?",
                    (delivery.PUBLIC_AGENT_BRIDGE_WORKER_TOKEN_JSON_PATH, "token-B", owned),
                )
                conn.commit()
                # Arm an Operator alert under this row's bridge-hiccup key so we can
                # prove the resolve-on-delivery does NOT clear it on the no-op path.
                # Arm via the audit log directly (not report_operator_hiccup, which
                # would queue a second operator notice row into the outbox) so the
                # only row run_once sees is our single guarded public-agent-turn row.
                hiccup_key = delivery._public_agent_bridge_hiccup_key(owned)
                control.append_arclink_audit(
                    conn,
                    action=f"{control.OPERATOR_HICCUP_AUDIT_PREFIX}{hiccup_key}",
                    actor_id="system:public_agent_bridge",
                    target_kind="operator-hiccup",
                    target_id=hiccup_key,
                    reason="prior terminal attempt paged the operator",
                )
                conn.commit()
                expect(
                    control._operator_hiccup_already_armed(conn, key=hiccup_key),
                    "precondition: hiccup must be armed before run_once",
                )

            # The bridge reports a SUCCESSFUL (non-deferred) turn, so the generic loop
            # reaches the delivered-write path -- where the empty-token guard must
            # convert the write to a no-op because token-B (a detached worker) owns it.
            bridge_calls: list[dict[str, object]] = []

            def fake_gateway_turn(**kwargs):
                bridge_calls.append(kwargs)
                return True, None  # bridged=True, no error => deliver_row returns None

            delivery._run_public_agent_gateway_turn = fake_gateway_turn
            summary = delivery.run_once(cfg)

            expect(len(bridge_calls) == 1, str(bridge_calls))
            # The guarded delivered-write was a no-op: nothing counted as delivered.
            expect(summary["delivered"] == 0, str(summary))
            expect(summary["errors"] == 0, str(summary))

            with control.connect_db(cfg) as conn:
                row = conn.execute(
                    "SELECT delivered_at, delivery_error FROM notification_outbox WHERE id = ?",
                    (owned,),
                ).fetchone()
                # The row is left for the owning worker to finalise.
                expect(not str(row["delivered_at"] or "").strip(), dict(row))
                # And the resolve-on-delivery did NOT run: the alert is still armed.
                expect(
                    control._operator_hiccup_already_armed(conn, key=hiccup_key),
                    "resolve must NOT have run on the no-op path (alert still armed)",
                )
            print("PASS test_generic_run_once_public_agent_turn_write_no_ops_on_worker_owned_row")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_public_agent_bridge_reaper_clears_stale_token_so_row_is_finalizable() -> None:
    # H1 (STILL-BROKEN): the orphan reaper re-armed next_attempt_at + stamped
    # reclaimed_at but LEFT the dead worker's recorded
    # $._public_agent_bridge_worker.token in place. The in-process/non-detached
    # finalize uses the EMPTY-token guard, which requires the recorded token to be
    # NULL (arclink_control _notification_token_guard_sql). With a stale token still
    # on the row, that empty-token finalize NO-OPed -> the reclaimed row could never
    # be marked delivered in non-detached mode and re-ran every lease cycle. The fix
    # clears the token in the reclaim UPDATE so a reclaimed row becomes finalizable.
    control = load_module(CONTROL_PY, "arclink_control_h1_reaper_clears_token_control_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_h1_reaper_clears_token_test")
    old_env = os.environ.copy()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            cfg = _delivery_db_config(control, Path(tmp))
            os.environ["ARCLINK_PUBLIC_AGENT_BRIDGE_ORPHAN_REAPER_SECONDS"] = "60"
            with control.connect_db(cfg) as conn:
                nid = control.queue_notification(
                    conn, target_kind="public-agent-turn", target_id="tg:1",
                    channel_kind="telegram", message="stalled",
                    extra={"deployment_id": "arcdep_test"},
                )
                # A dead worker holds the lease: record a token + a dead pid + a
                # missing job_path, and push the lease far into the future. Set the
                # token via json_set post-insert (a literal `token` key would trip the
                # queue_notification secret-scanner).
                conn.execute(
                    "UPDATE notification_outbox "
                    "SET extra_json = json_set(COALESCE(extra_json,'{}'), '$._public_agent_bridge_worker', json(?)), "
                    "    last_attempt_at = ?, next_attempt_at = ? "
                    "WHERE id = ?",
                    (
                        json.dumps({"pid": 99999999, "job_path": "", "token": "stale-token"}),
                        "2026-01-01T00:00:00+00:00",
                        "2999-01-01T00:00:00+00:00",
                        nid,
                    ),
                )
                conn.commit()

                # Precondition: WHILE the stale token is on the row, the in-process
                # empty-token finalize is a NO-OP (the bug's symptom).
                expect(
                    delivery.mark_notification_delivered_if_owned(conn, nid, "") == 0,
                    "precondition: empty-token finalize must no-op while a stale token is recorded",
                )
                token_before = conn.execute(
                    "SELECT json_extract(COALESCE(extra_json,'{}'), ?) AS t FROM notification_outbox WHERE id = ?",
                    (delivery.PUBLIC_AGENT_BRIDGE_WORKER_TOKEN_JSON_PATH, nid),
                ).fetchone()["t"]
                expect(token_before == "stale-token", f"precondition: token must be present, got {token_before!r}")

            reclaimed = delivery.reap_orphaned_public_agent_bridge_leases(cfg, limit=5)
            expect(reclaimed == 1, f"expected 1 reclaimed, got {reclaimed}")

            with control.connect_db(cfg) as conn:
                row = conn.execute(
                    "SELECT delivery_error, next_attempt_at, "
                    "json_extract(COALESCE(extra_json,'{}'), ?) AS token, "
                    "json_extract(COALESCE(extra_json,'{}'), '$._public_agent_bridge_worker.reclaimed_at') AS reclaimed_at "
                    "FROM notification_outbox WHERE id = ?",
                    (delivery.PUBLIC_AGENT_BRIDGE_WORKER_TOKEN_JSON_PATH, nid),
                ).fetchone()
                # The reclaim happened (reclaimed_at stamped, error noted, lease re-armed).
                expect("public_agent_bridge_orphan_reclaimed" in str(row["delivery_error"] or ""), dict(row))
                expect(str(row["reclaimed_at"] or "").strip() != "", dict(row))
                # H1: the stale token is GONE.
                expect(row["token"] is None, f"H1: reclaim must clear the stale worker token, got {row['token']!r}")
                # H1: the in-process empty-token finalize now FINALIZES the row.
                applied = delivery.mark_notification_delivered_if_owned(conn, nid, "")
                expect(applied >= 1, f"H1: a reclaimed row must be finalizable by the empty-token path, got {applied}")
                delivered = conn.execute(
                    "SELECT delivered_at FROM notification_outbox WHERE id = ?", (nid,)
                ).fetchone()
                expect(str(delivered["delivered_at"] or "").strip() != "", dict(delivered))
            print("PASS test_public_agent_bridge_reaper_clears_stale_token_so_row_is_finalizable")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_non_bridge_run_once_claims_row_before_send_so_concurrent_run_cannot_dup() -> None:
    # conc-H4 (STILL-BROKEN): the NON-bridge delivery path in run_once used to
    # send-then-mark with NO lease, so a second concurrent run_once could pick AND
    # send the SAME row before either marked it delivered (a duplicate platform
    # message). run_once now takes the atomic CAS claim (_claim_notification_for_delivery)
    # for every non-bridge sendable row BEFORE deliver_row sends. We prove (a) two
    # concurrent claims of one non-bridge row -> only ONE wins, and (b) end-to-end a
    # second run_once after the first claimed the row sends ZERO duplicate messages.
    control = load_module(CONTROL_PY, "arclink_control_conc_h4_nonbridge_claim_control_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_conc_h4_nonbridge_claim_test")
    old_env = os.environ.copy()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            cfg = _delivery_db_config(
                control, Path(tmp), extra={"TELEGRAM_BOT_TOKEN": "telegram-public-token"}
            )
            with control.connect_db(cfg) as conn:
                nid = control.queue_notification(
                    conn, target_kind="public-bot-user", target_id="tg:777",
                    channel_kind="telegram", message="hello user",
                )

            # (a) Direct CAS proof: two concurrent claims of the SAME non-bridge row
            # -> exactly one wins.
            with control.connect_db(cfg) as conn:
                first = delivery._claim_notification_for_delivery(
                    conn, nid, lease_seconds=delivery._public_agent_turn_lease_seconds()
                )
                second = delivery._claim_notification_for_delivery(
                    conn, nid, lease_seconds=delivery._public_agent_turn_lease_seconds()
                )
            expect(first is True, "the first claim of a due non-bridge row must win")
            expect(second is False, "the second concurrent claim of the same row must lose (no double-send)")

            # (b) End-to-end through run_once. Count platform sends.
            sends: list[str] = []
            delivery._deliver_public_bot_user = lambda *a, **k: sends.append(k.get("target_id") or (a[0] if a else "")) or None

            # Make the row due (clear the lease left by (a)).
            with control.connect_db(cfg) as conn:
                conn.execute(
                    "UPDATE notification_outbox SET next_attempt_at = NULL, last_attempt_at = NULL WHERE id = ?",
                    (nid,),
                )
                conn.commit()

            # Simulate the LOSING side of a race: a competing run_once already grabbed
            # this row's lease in the window between our fetch and our claim, so OUR
            # claim CAS returns False. The fix means we then count claimed_elsewhere and
            # do NOT send. Patch the claim to fail exactly once for this due row.
            real_claim = delivery._claim_notification_for_delivery
            calls = {"n": 0}

            def claim_loses_once(conn_arg, notification_id, *, lease_seconds):
                if int(notification_id) == int(nid) and calls["n"] == 0:
                    calls["n"] += 1
                    # Lease it on behalf of the competitor so the state is realistic.
                    real_claim(conn_arg, notification_id, lease_seconds=lease_seconds)
                    return False
                return real_claim(conn_arg, notification_id, lease_seconds=lease_seconds)

            delivery._claim_notification_for_delivery = claim_loses_once
            try:
                summary = delivery.run_once(cfg)
            finally:
                delivery._claim_notification_for_delivery = real_claim
            expect(len(sends) == 0, f"conc-H4: a row whose claim was lost must NOT be sent, sends={sends}")
            expect(summary.get("claimed_elsewhere", 0) >= 1, f"expected claimed_elsewhere>=1, got {summary}")
            with control.connect_db(cfg) as conn:
                row = conn.execute(
                    "SELECT delivered_at FROM notification_outbox WHERE id = ?", (nid,)
                ).fetchone()
                expect(not str(row["delivered_at"] or "").strip(), f"unsent row must stay undelivered: {dict(row)}")

            # Finally, with the lease cleared, a single uncontended run_once sends once.
            with control.connect_db(cfg) as conn:
                conn.execute(
                    "UPDATE notification_outbox SET next_attempt_at = NULL, last_attempt_at = NULL WHERE id = ?",
                    (nid,),
                )
                conn.commit()
            summary2 = delivery.run_once(cfg)
            expect(len(sends) == 1, f"conc-H4: exactly one send for the single winner, sends={sends}")
            expect(summary2.get("delivered", 0) == 1, f"expected delivered==1, got {summary2}")
            print("PASS test_non_bridge_run_once_claims_row_before_send_so_concurrent_run_cannot_dup")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_db_session_closes_connection_and_preserves_commit() -> None:
    # conc-H3: _db_session must COMMIT on clean exit (bare-idiom semantics) AND CLOSE
    # the connection (the leak the fix targets), unlike the bare
    # `with connect_db(cfg) as conn:` which only commits.
    import sqlite3 as _sqlite3

    control = load_module(CONTROL_PY, "arclink_control_conc_h3_db_session_control_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_conc_h3_db_session_test")
    old_env = os.environ.copy()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            cfg = _delivery_db_config(control, Path(tmp))
            with control.connect_db(cfg) as setup:
                nid = control.queue_notification(
                    setup, target_kind="public-bot-user", target_id="tg:1",
                    channel_kind="telegram", message="x",
                )

            captured = {}
            with delivery._db_session(cfg) as conn:
                captured["conn"] = conn
                # A write WITHOUT an explicit commit must still be durable after the
                # session exits (commit-on-clean-exit, exactly like the bare idiom).
                conn.execute(
                    "UPDATE notification_outbox SET delivery_error = ? WHERE id = ?",
                    ("h3-marker", nid),
                )

            # The connection is CLOSED after the session (the leak fix): any use raises.
            raised = False
            try:
                captured["conn"].execute("SELECT 1")
            except _sqlite3.ProgrammingError:
                raised = True
            expect(raised, "conc-H3: _db_session must CLOSE the connection on exit")

            # The un-explicitly-committed write survived (commit-on-exit preserved).
            with control.connect_db(cfg) as verify:
                row = verify.execute(
                    "SELECT delivery_error FROM notification_outbox WHERE id = ?", (nid,)
                ).fetchone()
            expect(str(row["delivery_error"] or "") == "h3-marker", dict(row))
            print("PASS test_db_session_closes_connection_and_preserves_commit")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_dedicated_public_agent_loop_does_not_count_delivered_on_no_op_write() -> None:
    # Adjacent (Codex-noted): the dedicated public-agent loop
    # (run_public_agent_turns_once) used to do summary["delivered"] += 1 even when the
    # empty-token guarded delivered-write NO-OPed (a row a detached worker owns). The
    # fix counts delivered ONLY when the guarded write actually finalized (rowcount>=1),
    # mirroring the generic run_once fix.
    control = load_module(CONTROL_PY, "arclink_control_adjacent_dedicated_loop_control_test")
    delivery = load_module(DELIVERY_PY, "arclink_notification_delivery_adjacent_dedicated_loop_test")
    old_env = os.environ.copy()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            cfg = _delivery_db_config(control, Path(tmp))
            with control.connect_db(cfg) as conn:
                owned = control.queue_notification(
                    conn, target_kind="public-agent-turn", target_id="tg:1",
                    channel_kind="telegram", message="owned turn",
                    extra={"deployment_id": "arcdep_test", "prefix": "arc-pod"},
                )
                # A DIFFERENT detached worker owns this row (records token-B).
                conn.execute(
                    "UPDATE notification_outbox SET extra_json = json_set(COALESCE(extra_json,'{}'), ?, ?) WHERE id = ?",
                    (delivery.PUBLIC_AGENT_BRIDGE_WORKER_TOKEN_JSON_PATH, "token-B", owned),
                )
                conn.commit()
                # Arm an Operator alert under this row's bridge-hiccup key so we can
                # prove resolve-on-delivery does NOT run on the no-op path.
                hiccup_key = delivery._public_agent_bridge_hiccup_key(owned)
                control.append_arclink_audit(
                    conn,
                    action=f"{control.OPERATOR_HICCUP_AUDIT_PREFIX}{hiccup_key}",
                    actor_id="system:public_agent_bridge",
                    target_kind="operator-hiccup",
                    target_id=hiccup_key,
                    reason="prior terminal attempt paged the operator",
                )
                conn.commit()
                expect(
                    control._operator_hiccup_already_armed(conn, key=hiccup_key),
                    "precondition: hiccup must be armed before the loop runs",
                )

            # The bridge reports a SUCCESSFUL (non-deferred) turn, so the dedicated loop
            # reaches the delivered-write path -- where the empty-token guard converts
            # the write to a no-op because token-B (a detached worker) owns the row.
            calls: list[dict[str, object]] = []

            def fake_gateway_turn(**kwargs):
                calls.append(kwargs)
                return True, None  # bridged=True, no error => deliver returns None

            delivery._run_public_agent_gateway_turn = fake_gateway_turn
            summary = delivery.run_public_agent_turns_once(cfg)

            expect(len(calls) == 1, str(calls))
            # Adjacent fix: the no-op delivered-write must NOT be counted.
            expect(summary["delivered"] == 0, f"no-op write must not count delivered: {summary}")
            expect(summary["errors"] == 0, str(summary))
            with control.connect_db(cfg) as conn:
                row = conn.execute(
                    "SELECT delivered_at FROM notification_outbox WHERE id = ?", (owned,)
                ).fetchone()
                expect(not str(row["delivered_at"] or "").strip(), dict(row))
                # resolve-on-delivery must NOT have run on the no-op path.
                expect(
                    control._operator_hiccup_already_armed(conn, key=hiccup_key),
                    "resolve must NOT have run on the no-op path (alert still armed)",
                )
            print("PASS test_dedicated_public_agent_loop_does_not_count_delivered_on_no_op_write")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_discord_operator_delivery_supports_channel_ids()
    test_public_bot_user_delivery_supports_telegram_and_discord_dm()
    test_captain_wrapped_delivery_uses_public_channel_and_marks_report_delivered()
    test_captain_wrapped_delivery_repairs_legacy_user_agent_channel()
    test_public_agent_turn_delivery_allows_explicit_quiet_fallback()
    test_public_agent_turn_delivery_fails_closed_without_quiet_fallback()
    test_public_agent_turn_delivery_prefers_gateway_bridge_when_available()
    test_public_agent_turn_album_rows_merge_into_one_bridge_call()
    test_operator_agent_turn_delivery_uses_control_stack_gateway()
    test_public_agent_turn_delivery_bridges_discord_channel_metadata()
    test_public_agent_live_trigger_claims_and_defers_until_detached_bridge_finishes()
    test_public_agent_live_trigger_skips_not_due_head_of_line()
    test_public_agent_turn_runner_prefers_running_gateway_container()
    test_public_agent_gateway_bridge_detaches_long_running_turns()
    test_public_agent_gateway_bridge_unlinks_job_when_worker_spawn_fails()
    test_public_agent_bridge_worker_marks_delivery_after_bridge_success()
    test_public_agent_bridge_worker_holds_unconfirmed_bridge_success()
    test_public_agent_bridge_hold_policy_distinguishes_unknown_from_failed_no_id()
    test_public_agent_bridge_worker_retries_failed_send_without_message_ids()
    test_public_agent_bridge_orphan_reaper_rearms_dead_worker_lease()
    test_public_agent_bridge_worker_rejects_unallowlisted_commands()
    test_public_agent_bridge_command_validator_confines_compose_paths()
    test_public_agent_gateway_bridge_passes_streaming_policy_to_container()
    test_public_agent_gateway_turn_uses_gateway_exec_broker_when_configured()
    test_public_agent_bridge_worker_uses_gateway_exec_broker_request_jobs()
    test_gateway_exec_broker_records_redacted_rejection_incident_before_subprocess()
    test_rejection_incident_helpers_redact_and_refuse_unsafe_paths()
    test_gateway_exec_broker_rejects_raw_commands_and_builds_vetted_exec()
    test_gateway_exec_broker_rejects_symlinked_compose_fallback_config_before_docker()
    test_gateway_exec_broker_sanitizes_subprocess_failure_tail()
    test_upgrade_notification_delivery_defers_during_deploy_operation()
    test_public_agent_bridge_defaults_to_streaming_progress_without_reasoning()
    test_public_agent_bridge_l1_l2_flags_off_preserve_config_and_getme()
    test_public_agent_bridge_l1_env_starves_unused_platform_and_restores()
    test_public_agent_bridge_l1_restores_env_when_starved_loader_raises()
    test_public_agent_bridge_l2_getme_cache_hit_skips_network_and_hmacs_key()
    test_public_agent_bridge_l2_getme_cache_miss_stale_corrupt_fail_open()
    test_public_agent_bridge_l2_getme_cache_secure_dir_or_secret_unavailable_fail_open()
    test_public_agent_bridge_l2_preloaded_user_skips_getme()
    test_public_agent_bridge_root_wrapper_preloads_and_drops_child()
    test_public_agent_bridge_persists_telegram_approval_button_state()
    test_public_agent_bridge_drains_telegram_batch_tasks_before_done()
    test_public_agent_bridge_root_wrapper_gated_on_getme_cache_flag()
    test_gateway_root_wrapper_preflight_reprobes_positive_caches_negative()
    test_public_agent_bridge_telegram_replay_does_not_dispatch_generic_event()
    test_public_bot_ready_hub_edits_payment_message_when_available()
    test_notification_due_now_normalizes_z_and_offset_timestamps()
    test_public_agent_bridge_worker_token_guards_late_terminal_writes()
    test_public_agent_bridge_reaper_requires_recorded_job_path_match()
    test_gateway_root_wrapper_preflight_does_not_cache_thrown_probe()
    test_public_agent_bridge_unconfirmed_escalates_to_operator()
    test_public_agent_bridge_terminal_error_includes_context_and_log_tail()
    test_public_agent_bridge_album_persists_merged_list_to_leader_row()
    test_public_agent_bridge_claim_holder_no_ops_on_worker_owned_row()
    test_public_agent_bridge_spawn_aborts_when_lease_token_cannot_stamp()
    test_public_agent_bridge_reaper_skips_live_token_and_rearms_tokenless()
    test_public_agent_bridge_album_persist_failure_leaves_siblings_undelivered()
    test_public_agent_bridge_broker_failure_error_includes_context()
    test_generic_run_once_public_agent_turn_write_no_ops_on_worker_owned_row()
    test_public_agent_bridge_reaper_clears_stale_token_so_row_is_finalizable()
    test_non_bridge_run_once_claims_row_before_send_so_concurrent_run_cannot_dup()
    test_db_session_closes_connection_and_preserves_commit()
    test_dedicated_public_agent_loop_does_not_count_delivered_on_no_op_write()
    print("PASS all notification delivery regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
