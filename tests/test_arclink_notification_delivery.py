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
    test_upgrade_notification_delivery_defers_during_deploy_operation()
    print("PASS all 2 notification delivery regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
