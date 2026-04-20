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
CONTROL_PY = REPO / "python" / "almanac_control.py"
COMPLETION_PY = REPO / "python" / "almanac_onboarding_completion.py"
PYTHON_DIR = REPO / "python"


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
        "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "tui-only",
        "OPERATOR_NOTIFY_CHANNEL_ID": "",
        "ALMANAC_MODEL_PRESET_CODEX": "openai:codex",
        "ALMANAC_MODEL_PRESET_OPUS": "anthropic:claude-opus",
        "ALMANAC_MODEL_PRESET_CHUTES": "chutes:auto-failover",
        "ALMANAC_CURATOR_CHANNELS": "tui-only",
        "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "0",
        "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED": "0",
        "ALMANAC_AGENT_ENABLE_TAILSCALE_SERVE": "1",
        "ENABLE_TAILSCALE_SERVE": "1",
        "ENABLE_NEXTCLOUD": "1",
        "TAILSCALE_DNS_NAME": "kor.tail77f45e.ts.net",
        "NEXTCLOUD_TRUSTED_DOMAIN": "kor.tail77f45e.ts.net",
        "TAILSCALE_QMD_PATH": "/mcp",
        "TAILSCALE_ALMANAC_MCP_PATH": "/almanac-mcp",
        "CHUTES_MCP_URL": "https://chutes.example/mcp",
    }


def insert_agent(mod, conn, *, agent_id: str, unix_user: str, hermes_home: Path) -> None:
    now = mod.utc_now_iso()
    conn.execute(
        """
        INSERT INTO agents (
          agent_id, role, unix_user, display_name, status, hermes_home, manifest_path,
          archived_state_path, model_preset, model_string, channels_json,
          allowed_mcps_json, home_channel_json, operator_notify_channel_json,
          created_at, last_enrolled_at
        ) VALUES (?, 'user', ?, ?, 'active', ?, ?, NULL, 'codex', 'openai:codex', '["tui-only","discord"]', '[]', '{}', '{}', ?, ?)
        """,
        (agent_id, unix_user, unix_user, str(hermes_home), str(hermes_home / "manifest.json"), now, now),
    )
    conn.commit()


def test_completion_bundle_lists_resources_and_scrubs_password() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_completion_test")
    completion = load_module(COMPLETION_PY, "almanac_onboarding_completion_test")
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
            user_home = Path(pwd.getpwnam(unix_user).pw_dir)
            hermes_home = root / "homes" / unix_user / ".local" / "share" / "almanac-agent" / "hermes-home"
            (hermes_home / "state").mkdir(parents=True, exist_ok=True)
            insert_agent(control, conn, agent_id="agent-sirouk", unix_user=unix_user, hermes_home=hermes_home)

            session = control.start_onboarding_session(
                conn,
                cfg,
                platform="discord",
                chat_id="123456789",
                sender_id="123456789",
                sender_username="sirouk",
                sender_display_name="Chris",
            )
            session = control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="completed",
                linked_agent_id="agent-sirouk",
                answers={
                    "bot_platform": "discord",
                    "bot_username": "Jeef",
                    "preferred_bot_name": "Jeef",
                },
            )

            access = {
                "unix_user": unix_user,
                "username": unix_user,
                "password": "sup3r-secret",
                "dashboard_url": "https://kor.tail77f45e.ts.net:30011/",
                "code_url": "https://kor.tail77f45e.ts.net:40011/",
            }
            (hermes_home / "state" / "almanac-web-access.json").write_text(
                json.dumps(access),
                encoding="utf-8",
            )

            bundle = completion.completion_bundle_for_session(conn, cfg, session)
            expect(bundle is not None, "expected completion bundle")
            full_text = str(bundle["full_text"])
            scrubbed_text = str(bundle["scrubbed_text"])

            expect("Shared password: sup3r-secret" in full_text, full_text)
            expect("Shared password: sup3r-secret" not in scrubbed_text, scrubbed_text)
            expect("Shared password: removed after you confirmed you recorded it." in scrubbed_text, scrubbed_text)
            expect(f"Nextcloud login: {unix_user} (same shared password)" in full_text, full_text)
            expect("Shared resources:" in full_text, full_text)
            expect("https://kor.tail77f45e.ts.net/" in full_text, full_text)
            expect("https://kor.tail77f45e.ts.net/mcp" in full_text, full_text)
            expect("https://kor.tail77f45e.ts.net/almanac-mcp" in full_text, full_text)
            expect("Chutes KB MCP: https://chutes.example/mcp" in full_text, full_text)
            expect("Notion webhook: shared operator-managed service on this host" in full_text, full_text)
            expect(str(user_home) in full_text, full_text)

            telegram_button = bundle["telegram_reply_markup"]["inline_keyboard"][0][0]
            discord_button = bundle["discord_components"][0]["components"][0]
            expect(
                telegram_button["callback_data"] == completion.completion_ack_callback_data(str(session["session_id"])),
                telegram_button,
            )
            expect(
                discord_button["custom_id"] == completion.completion_ack_callback_data(str(session["session_id"])),
                discord_button,
            )
            print("PASS test_completion_bundle_lists_resources_and_scrubs_password")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_completion_bundle_lists_resources_and_scrubs_password()
    print("PASS all 1 onboarding completion regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
