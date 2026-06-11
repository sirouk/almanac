#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import asyncio
import json
import os
import sys
import tempfile
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
                    "SELECT id, delivered_at, delivery_error FROM notification_outbox ORDER BY id ASC"
                ).fetchall()
            expect(all(str(row["delivered_at"] or "").strip() for row in rows), str([dict(row) for row in rows]))
            absorbed_notes = [str(row["delivery_error"] or "") for row in rows[1:]]
            expect(
                all(note.startswith("absorbed_into_album_leader:") for note in absorbed_notes),
                str(absorbed_notes),
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
                stdout = '{"delivered": true, "ok": true}\n'
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
                    payload={"platform": "telegram", "text": "finish later"},
                    project_name="arclink-arcdep_test",
                )
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
                expect(json.loads(str(run_calls[0]["input"]))["text"] == "finish later", str(run_calls))
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
                "hermes-gateway",
                "/opt/arclink/runtime/hermes-venv/bin/python3",
                "/home/arclink/arclink/python/arclink_public_agent_bridge.py",
            ]
            ok, kind, error = delivery._validate_public_agent_bridge_cmd(
                valid_cmd,
                project_name="arclink-arcdep_test",
            )
            expect(ok is True and kind == "docker-compose-exec-hermes-gateway", error)

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
                        "payload": {"platform": "telegram", "bot_token": "token", "chat_id": "123", "user_id": "123", "text": "finish"},
                        "timeout_seconds": 60,
                    },
                )
                result = delivery._run_public_agent_bridge_worker(job_path)
            finally:
                delivery._run_gateway_exec_broker_request = original_broker_request

            expect(result == 0, str(result))
            expect(broker_requests and broker_requests[0]["deployment_id"] == "arcdep_test", broker_requests)
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
        stdout = '{"ok": true}\n'
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


def test_gateway_exec_broker_rejects_raw_commands_and_builds_vetted_exec() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    broker = load_module(PYTHON_DIR / "arclink_gateway_exec_broker.py", "arclink_gateway_exec_broker_contract_test")

    calls: list[dict[str, object]] = []

    class Proc:
        returncode = 0
        stdout = '{"ok": true}\n'
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
    test_public_agent_turn_runner_prefers_running_gateway_container()
    test_public_agent_gateway_bridge_detaches_long_running_turns()
    test_public_agent_bridge_worker_marks_delivery_after_bridge_success()
    test_public_agent_bridge_worker_rejects_unallowlisted_commands()
    test_public_agent_bridge_command_validator_confines_compose_paths()
    test_public_agent_gateway_bridge_passes_streaming_policy_to_container()
    test_public_agent_gateway_turn_uses_gateway_exec_broker_when_configured()
    test_public_agent_bridge_worker_uses_gateway_exec_broker_request_jobs()
    test_gateway_exec_broker_records_redacted_rejection_incident_before_subprocess()
    test_gateway_exec_broker_rejects_raw_commands_and_builds_vetted_exec()
    test_gateway_exec_broker_rejects_symlinked_compose_fallback_config_before_docker()
    test_upgrade_notification_delivery_defers_during_deploy_operation()
    test_public_agent_bridge_defaults_to_streaming_progress_without_reasoning()
    test_public_agent_bridge_persists_telegram_approval_button_state()
    test_public_agent_bridge_drains_telegram_batch_tasks_before_done()
    test_public_bot_ready_hub_edits_payment_message_when_available()
    test_notification_due_now_normalizes_z_and_offset_timestamps()
    print("PASS all notification delivery regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
