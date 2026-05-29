#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

from arclink_test_helpers import expect, load_module, seed_active_public_bot_deployment


def test_refresh_active_telegram_command_scopes_records_conflicts_and_alerts_operator() -> None:
    control = load_module("arclink_control.py", "arclink_control_public_command_scope_test")
    commands = load_module("arclink_public_bot_commands.py", "arclink_public_bot_commands_scope_test")
    telegram = sys.modules["arclink_telegram"]

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "arclink-control.sqlite3"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        control.ensure_schema(conn)
        seed_active_public_bot_deployment(
            control,
            conn,
            channel="telegram",
            channel_identity="tg:1994645819",
            prefix="arc-scope",
        )
        conn.close()

        calls: list[dict[str, object]] = []
        commands.refresh_arclink_public_telegram_chat_commands = lambda **kwargs: calls.append(kwargs) or {
            "registered": [],
            "scope": {"type": "chat", "chat_id": 1994645819},
        }
        telegram.telegram_set_my_commands = lambda **kwargs: calls.append({"exact": kwargs}) or {"result": True}
        commands._agent_commands_from_gateway_container = lambda deployment_id: (
            [
                {"command": "agents", "description": "Show Hermes agents"},
                {"command": "status", "description": "Show Hermes status"},
                {"command": "raven", "description": "Unexpected future Hermes command"},
                {"command": "update", "description": "Unsafe direct update"},
                {"command": "model", "description": "Switch model"},
            ],
            "arclink-arcdep-hermes-gateway-1",
            3,
        )

        result = commands.refresh_active_telegram_command_scopes(
            {
                "TELEGRAM_BOT_TOKEN": "123:abc",
                "ARCLINK_DB_PATH": str(db_path),
                "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "tui-only",
            }
        )

        expect(result["refreshed"] == 1, str(result))
        expect(result["issues"] == 1, str(result))
        expect(calls, "expected Telegram command refresh calls")
        exact = [call["exact"] for call in calls if "exact" in call][0]
        names = {item["command"] for item in exact["commands"]}
        expect("arclink" in names, str(names))
        expect("model" in names, str(names))
        expect("raven" not in names and "agents" not in names and "status" not in names, str(names))
        expect("update" not in names, str(names))

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT metadata_json FROM arclink_onboarding_sessions").fetchone()
        metadata = json.loads(str(row["metadata_json"] or "{}"))
        expect(metadata["telegram_raven_control_command"] == "arclink", str(metadata))
        expect("agents" in metadata["telegram_command_scope_legacy_conflicts"], str(metadata))
        expect("raven" in metadata["telegram_command_scope_hard_conflicts"], str(metadata))
        expect("update" in metadata["telegram_command_scope_policy_suppressed"], str(metadata))
        expect(metadata["telegram_active_agent_command_names"] == ["model"], str(metadata))
        expect(metadata["telegram_command_scope_hidden_count"] == 3, str(metadata))
        outbox = conn.execute("SELECT target_kind, message FROM notification_outbox").fetchall()
        expect(len(outbox) == 1 and outbox[0]["target_kind"] == "operator", str([dict(r) for r in outbox]))
        expect("command scope drift" in outbox[0]["message"], outbox[0]["message"])
        expect("hidden=3" in outbox[0]["message"], outbox[0]["message"])
        conn.close()
        print("PASS test_refresh_active_telegram_command_scopes_records_conflicts_and_alerts_operator")


def test_register_public_bot_commands_gives_operator_hermes_scope() -> None:
    commands = load_module("arclink_public_bot_commands.py", "arclink_public_bot_commands_operator_scope_test")
    telegram = sys.modules["arclink_telegram"]

    calls: list[dict[str, object]] = []
    commands.register_arclink_public_telegram_commands = lambda token: {"registered": ["start"], "scopes": ["default"]}
    commands.ensure_arclink_public_telegram_webhook = lambda token, url, secret: {"skipped": True}
    commands.refresh_active_telegram_command_scopes = lambda env: {"refreshed": 0, "issues": 0, "skipped": False}
    commands._operator_agent_commands_from_control_stack = lambda env: (
        [
            {"command": "model", "description": "Switch model"},
            {"command": "provider", "description": "Provider alias"},
            {"command": "agents", "description": "Hermes internal agent tasks"},
            {"command": "update", "description": "Unsafe direct update"},
        ],
        "arclink-control-operator-hermes-gateway-1",
        0,
    )
    telegram.telegram_set_my_commands = lambda **kwargs: calls.append(kwargs) or {"result": True}

    result = commands.register_public_bot_commands(
        {
            "TELEGRAM_BOT_TOKEN": "123:abc",
            "TELEGRAM_WEBHOOK_URL": "https://example.test/tg",
            "TELEGRAM_WEBHOOK_SECRET": "secret",
            "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "telegram",
            "OPERATOR_NOTIFY_CHANNEL_ID": "42",
            "ARCLINK_OPERATOR_TELEGRAM_USER_IDS": "42",
        }
    )

    operator_scopes = result["telegram"]["operator_scopes"]
    expect(operator_scopes["agent_command_source"] == "arclink-control-operator-hermes-gateway-1", str(operator_scopes))
    registered = set(operator_scopes["registered"])
    expect("operator_status" in registered and "agents" in registered and "upgrade" in registered, str(registered))
    expect("model" in registered and "provider" in registered, str(registered))
    expect("update" not in registered, str(registered))
    expect("agents" in operator_scopes["agent_conflicts"], str(operator_scopes))
    exact_names = {item["command"] for call in calls for item in call["commands"]}
    expect("model" in exact_names and "operator_status" in exact_names, str(calls))
    print("PASS test_register_public_bot_commands_gives_operator_hermes_scope")


def main() -> int:
    test_refresh_active_telegram_command_scopes_records_conflicts_and_alerts_operator()
    test_register_public_bot_commands_gives_operator_hermes_scope()
    print("PASS all 2 ArcLink public bot command registration tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
