#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
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

            def fake_telegram(*, bot_token, chat_id, text, reply_markup=None, parse_mode=""):
                telegram_calls.append(
                    {
                        "bot_token": bot_token,
                        "chat_id": chat_id,
                        "text": text,
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


def test_public_agent_turn_delivery_runs_agent_and_returns_to_public_channel() -> None:
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
        try:
            cfg = control.Config.from_env()
            calls: list[dict[str, object]] = []
            prompts: list[dict[str, str]] = []

            def fake_agent_turn(*, deployment_id: str, prefix: str, prompt: str) -> tuple[str, str]:
                prompts.append({"deployment_id": deployment_id, "prefix": prefix, "prompt": prompt})
                return "Agent heard you.", ""

            def fake_telegram(*, bot_token, chat_id, text, reply_markup=None, parse_mode=""):
                calls.append(
                    {
                        "bot_token": bot_token,
                        "chat_id": chat_id,
                        "text": text,
                        "reply_markup": reply_markup,
                        "parse_mode": parse_mode,
                    }
                )
                return {"ok": True}

            delivery._run_public_agent_turn = fake_agent_turn
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
                        }
                    ),
                },
            )
            expect(error is None, str(error))
            expect(prompts == [{"deployment_id": "arcdep_test", "prefix": "arc-testpod", "prompt": "hello agent"}], str(prompts))
            expect(calls[0]["chat_id"] == "123", str(calls))
            expect(calls[0]["bot_token"] == "telegram-public-token", str(calls))
            expect("Test Agent:\n\nAgent heard you." == calls[0]["text"], str(calls))
            print("PASS test_public_agent_turn_delivery_runs_agent_and_returns_to_public_channel")
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


def main() -> int:
    test_discord_operator_delivery_supports_channel_ids()
    test_public_bot_user_delivery_supports_telegram_and_discord_dm()
    test_public_agent_turn_delivery_runs_agent_and_returns_to_public_channel()
    test_public_agent_turn_runner_prefers_running_gateway_container()
    test_upgrade_notification_delivery_defers_during_deploy_operation()
    print("PASS all 5 notification delivery regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
