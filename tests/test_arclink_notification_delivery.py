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


def test_public_agent_live_trigger_claims_and_delivers_once() -> None:
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
                return True, ""

            delivery._run_public_agent_gateway_turn = fake_gateway_turn
            first = delivery.run_public_agent_turns_once(cfg, channel_kind="telegram", target_id="tg:123", limit=1)
            second = delivery.run_public_agent_turns_once(cfg, channel_kind="telegram", target_id="tg:123", limit=1)
            expect(first["processed"] == 1 and first["delivered"] == 1 and first["errors"] == 0, str(first))
            expect(second["processed"] == 0 and second["delivered"] == 0, str(second))
            expect(len(bridge_calls) == 1, str(bridge_calls))
            expect(bridge_calls[0]["prompt"] == "live trigger please", str(bridge_calls))
            with control.connect_db(cfg) as conn:
                row = conn.execute(
                    "SELECT delivered_at, last_attempt_at, next_attempt_at FROM notification_outbox WHERE id = ?",
                    (notification_id,),
                ).fetchone()
            expect(row["delivered_at"], dict(row))
            expect(row["last_attempt_at"], dict(row))
            print("PASS test_public_agent_live_trigger_claims_and_delivers_once")
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

            delivery.subprocess.Popen = fake_popen
            ok, error = delivery._spawn_public_agent_gateway_bridge(
                cmd=["docker", "exec", "-i", "gateway", "bridge.py"],
                payload={"platform": "telegram", "text": "long-running turn"},
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
            delivery._deployment_service_container = lambda *, project_name, service: "gateway-container"

            def fake_spawn(*, cmd, payload):
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
            expect(payloads[-1]["streaming_enabled"] is False, payloads[-1])

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


def test_public_agent_bridge_defaults_to_final_send_and_can_enable_streaming_without_reasoning() -> None:
    bridge = load_module(PYTHON_DIR / "arclink_public_agent_bridge.py", "arclink_public_agent_bridge_contract_test")
    bridge_source = (PYTHON_DIR / "arclink_public_agent_bridge.py").read_text(encoding="utf-8")
    expect("ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING" in bridge_source, bridge_source)
    expect("streaming.enabled = True" in bridge_source, bridge_source)
    expect("show_reasoning = True" not in bridge_source, bridge_source)
    old_env = os.environ.copy()
    try:
        os.environ.pop("ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING", None)
        expect(bridge._public_bridge_streaming_enabled() is False, "public bridge should default to final-send mode")
        os.environ["ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING"] = "1"
        expect(bridge._public_bridge_streaming_enabled() is True, "streaming should remain operator opt-in")
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
    print("PASS test_public_agent_bridge_defaults_to_final_send_and_can_enable_streaming_without_reasoning")


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
    test_public_agent_turn_delivery_allows_explicit_quiet_fallback()
    test_public_agent_turn_delivery_fails_closed_without_quiet_fallback()
    test_public_agent_turn_delivery_prefers_gateway_bridge_when_available()
    test_public_agent_turn_delivery_bridges_discord_channel_metadata()
    test_public_agent_live_trigger_claims_and_delivers_once()
    test_public_agent_turn_runner_prefers_running_gateway_container()
    test_public_agent_gateway_bridge_detaches_long_running_turns()
    test_public_agent_gateway_bridge_passes_streaming_policy_to_container()
    test_upgrade_notification_delivery_defers_during_deploy_operation()
    test_public_agent_bridge_defaults_to_final_send_and_can_enable_streaming_without_reasoning()
    test_public_agent_bridge_drains_telegram_batch_tasks_before_done()
    test_notification_due_now_normalizes_z_and_offset_timestamps()
    print("PASS all 14 notification delivery regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
