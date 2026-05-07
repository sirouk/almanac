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
CONTROL_PY = REPO / "python" / "arclink_control.py"
COMPLETION_PY = REPO / "python" / "arclink_onboarding_completion.py"
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
        "ARCLINK_USER": "arclink",
        "ARCLINK_ORG_NAME": "OrgName",
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
        "ARCLINK_NOTION_WEBHOOK_HOST": "127.0.0.1",
        "ARCLINK_NOTION_WEBHOOK_PORT": "8283",
        "ARCLINK_SSOT_NOTION_SPACE_URL": "https://www.notion.so/Acme-SSOT-1234567890abcdef1234567890abcdef",
        "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "tui-only",
        "OPERATOR_NOTIFY_CHANNEL_ID": "",
        "ARCLINK_MODEL_PRESET_CODEX": "openai:codex",
        "ARCLINK_MODEL_PRESET_OPUS": "anthropic:claude-opus",
        "ARCLINK_MODEL_PRESET_CHUTES": "chutes:model-router",
        "ARCLINK_CURATOR_CHANNELS": "tui-only",
        "ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "0",
        "ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED": "0",
        "ARCLINK_AGENT_ENABLE_TAILSCALE_SERVE": "1",
        "ENABLE_TAILSCALE_SERVE": "1",
        "TAILSCALE_SERVE_PORT": "8445",
        "ENABLE_NEXTCLOUD": "1",
        "TAILSCALE_DNS_NAME": "arclink.example.test",
        "NEXTCLOUD_TRUSTED_DOMAIN": "arclink.example.test",
        "TAILSCALE_QMD_PATH": "/mcp",
        "TAILSCALE_ARCLINK_MCP_PATH": "/arclink-mcp",
        "ARCLINK_EXTRA_MCP_URL": "https://kb.example/mcp",
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
    control = load_module(CONTROL_PY, "arclink_control_completion_test")
    completion = load_module(COMPLETION_PY, "arclink_onboarding_completion_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            unix_user = pwd.getpwuid(os.getuid()).pw_name
            user_home = Path(pwd.getpwnam(unix_user).pw_dir)
            hermes_home = root / "homes" / unix_user / ".local" / "share" / "arclink-agent" / "hermes-home"
            (hermes_home / "state").mkdir(parents=True, exist_ok=True)
            insert_agent(control, conn, agent_id="agent-alex", unix_user=unix_user, hermes_home=hermes_home)

            session = control.start_onboarding_session(
                conn,
                cfg,
                platform="discord",
                chat_id="123456789",
                sender_id="123456789",
                sender_username="alex",
                sender_display_name="Alex",
            )
            session = control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="completed",
                linked_agent_id="agent-alex",
                answers={
                    "bot_platform": "discord",
                    "bot_username": "Guide",
                    "preferred_bot_name": "Guide",
                    "discord_agent_dm_confirmation_code": "ABC-123",
                },
            )

            access = {
                "unix_user": unix_user,
                "username": unix_user,
                "password": "sup3r-secret",
                "dashboard_url": "https://arclink.example.test:30011/",
                "code_url": "https://arclink.example.test:40011/",
            }
            (hermes_home / "state" / "arclink-web-access.json").write_text(
                json.dumps(access),
                encoding="utf-8",
            )

            bundle = completion.completion_bundle_for_session(conn, cfg, session)
            expect(bundle is not None, "expected completion bundle")
            full_text = str(bundle["full_text"])
            scrubbed_text = str(bundle["scrubbed_text"])
            followup_text = str(bundle["followup_text"])

            expect("Shared password:\n```\nsup3r-secret\n```" in full_text, full_text)
            expect("Shared password: sup3r-secret" not in scrubbed_text, scrubbed_text)
            expect("Shared password: removed after confirmation." in scrubbed_text, scrubbed_text)
            expect(str(bundle.get("telegram_parse_mode") or "") == "", str(bundle))
            expect("Your lane is ready." in full_text, full_text)
            expect("Save this password now." in full_text, full_text)
            expect("send the rest of your links" in full_text, full_text)
            expect(followup_text.startswith("────────\nStart here:"), followup_text)
            expect("Web access:" in followup_text, followup_text)
            expect("Nextcloud login:" not in followup_text, followup_text)
            expect("Shared ArcLink links:" in followup_text, followup_text)
            expect("https://arclink.example.test:8445/" not in followup_text, followup_text)
            expect("https://arclink.example.test/mcp" not in followup_text, followup_text)
            expect("https://arclink.example.test/arclink-mcp" not in followup_text, followup_text)
            expect("QMD MCP retrieval rail:" not in followup_text, followup_text)
            expect("ArcLink MCP control rail:" not in followup_text, followup_text)
            expect("External knowledge rail: https://kb.example/mcp" in followup_text, followup_text)
            expect("Shared Notion SSOT: https://www.notion.so/Acme-SSOT-1234567890abcdef1234567890abcdef" in followup_text, followup_text)
            expect("Notion webhook: shared operator-managed rail on this host" in followup_text, followup_text)
            expect("Shared Notion writes:" in full_text, full_text)
            expect(str(user_home) in followup_text, followup_text)
            expect(str(user_home / "ArcLink") in followup_text, followup_text)
            expect("edit or delete those messages" in followup_text, followup_text)
            expect("Raven can set this up with `/setup-backup`" in followup_text, followup_text)
            expect("arclink-agent-configure-backup" in followup_text, followup_text)
            expect("Do not reuse the ArcLink code-push key" in followup_text, followup_text)
            expect("Discord handoff:" in followup_text, followup_text)
            expect("ABC-123" in followup_text, followup_text)
            expect("If the code matches" in followup_text, followup_text)

            telegram_button = bundle["telegram_reply_markup"]["inline_keyboard"][0][0]
            discord_button = bundle["discord_components"][0]["components"][0]
            telegram_backup_button = bundle["followup_telegram_reply_markup"]["inline_keyboard"][0][0]
            discord_backup_button = bundle["followup_discord_components"][0]["components"][0]
            expect(
                telegram_button["callback_data"] == completion.completion_ack_callback_data(str(session["session_id"])),
                telegram_button,
            )
            expect(
                discord_button["custom_id"] == completion.completion_ack_callback_data(str(session["session_id"])),
                discord_button,
            )
            expect(
                telegram_backup_button["callback_data"]
                == completion.completion_setup_backup_callback_data(str(session["session_id"])),
                telegram_backup_button,
            )
            expect(telegram_backup_button["text"] == "Set up private backup", telegram_backup_button)
            expect(
                discord_backup_button["custom_id"]
                == completion.completion_setup_backup_callback_data(str(session["session_id"])),
                discord_backup_button,
            )
            expect(discord_backup_button["label"] == "Set up private backup", discord_backup_button)

            telegram_bundle = completion.completion_message_bundle(
                cfg,
                session_id="onb_telegram",
                bot_reference="@Guide",
                access={
                    "unix_user": unix_user,
                    "username": unix_user,
                    "password": "copy<&secret",
                    "dashboard_url": "https://arclink.example.test:30011/",
                    "code_url": "https://arclink.example.test:40011/",
                },
                home=user_home,
                bot_platform="telegram",
            )
            telegram_text = str(telegram_bundle["full_text"])
            telegram_followup = str(telegram_bundle["followup_text"])
            expect(str(telegram_bundle.get("telegram_parse_mode") or "") == "HTML", str(telegram_bundle))
            expect(str(telegram_bundle.get("followup_telegram_parse_mode") or "") == "HTML", str(telegram_bundle))
            expect("Shared password:\n<code>copy&lt;&amp;secret</code>" in telegram_text, telegram_text)
            expect("copy<&secret" not in telegram_text, telegram_text)
            expect("Telegram handoff:" in telegram_followup, telegram_followup)
            expect("Tap @Guide and press Start" in telegram_followup, telegram_followup)
            expect("Use that bot chat from here on out." in telegram_followup, telegram_followup)
            expect(
                "<code>curl -fsSL https://raw.githubusercontent.com/example/arclink/main/bin/setup-remote-hermes-client.sh "
                "| bash -s -- --host arclink.example.test --user "
                in telegram_followup,
                telegram_followup,
            )
            expect("`curl -fsSL" not in telegram_followup, telegram_followup)
            expect("`/ssh-key &lt;public key&gt;`" in telegram_followup, telegram_followup)
            print("PASS test_completion_bundle_lists_resources_and_scrubs_password")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_completion_scrubbed_text_uses_stored_receipt_when_reconstruction_fails() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_completion_stored_scrub_test")
    completion = load_module(COMPLETION_PY, "arclink_onboarding_completion_stored_scrub_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            session = control.start_onboarding_session(
                conn,
                cfg,
                platform="discord",
                chat_id="123456789",
                sender_id="123456789",
                sender_username="alex",
                sender_display_name="Alex",
            )
            session = control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="completed",
                answers={
                    "completion_delivery": {
                        "platform": "discord",
                        "chat_id": "123456789",
                        "message_id": "555",
                        "scrubbed_text": "Shared password: removed after confirmation.",
                        "password_scrubbed": False,
                    }
                },
            )

            scrubbed_text = completion.completion_scrubbed_text_for_session(conn, cfg, session)
            expect(
                scrubbed_text == "Shared password: removed after confirmation.",
                scrubbed_text,
            )
            print("PASS test_completion_scrubbed_text_uses_stored_receipt_when_reconstruction_fails")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_completion_bundle_pins_remote_setup_helper_to_deployed_commit() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_completion_remote_url_test")
    completion = load_module(COMPLETION_PY, "arclink_onboarding_completion_remote_url_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        release_state_path = root / "state" / "arclink-release.json"
        release_state_path.parent.mkdir(parents=True, exist_ok=True)
        release_state_path.write_text(
            json.dumps(
                {
                    "tracked_upstream_repo_url": "https://github.com/example/arclink.git",
                    "tracked_upstream_branch": "main",
                    "deployed_commit": "eb41b3fc458071ac08222982d66d225518f01fbe",
                }
            ),
            encoding="utf-8",
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            unix_user = pwd.getpwuid(os.getuid()).pw_name
            hermes_home = root / "homes" / unix_user / ".local" / "share" / "arclink-agent" / "hermes-home"
            (hermes_home / "state").mkdir(parents=True, exist_ok=True)
            insert_agent(control, conn, agent_id="agent-alex", unix_user=unix_user, hermes_home=hermes_home)

            session = control.start_onboarding_session(
                conn,
                cfg,
                platform="discord",
                chat_id="123456789",
                sender_id="123456789",
                sender_username="alex",
                sender_display_name="Alex",
            )
            session = control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="completed",
                linked_agent_id="agent-alex",
                answers={
                    "bot_platform": "discord",
                    "bot_username": "Guide",
                    "preferred_bot_name": "Guide",
                },
            )

            access = {
                "unix_user": unix_user,
                "username": unix_user,
                "password": "sup3r-secret",
                "dashboard_url": "https://arclink.example.test:30011/",
                "code_url": "https://arclink.example.test:40011/",
            }
            (hermes_home / "state" / "arclink-web-access.json").write_text(
                json.dumps(access),
                encoding="utf-8",
            )

            bundle = completion.completion_bundle_for_session(conn, cfg, session)
            expect(bundle is not None, "expected completion bundle")
            followup_text = str(bundle["followup_text"])
            expect(
                "https://raw.githubusercontent.com/example/arclink/eb41b3fc458071ac08222982d66d225518f01fbe/bin/setup-remote-hermes-client.sh"
                in followup_text,
                followup_text,
            )
            expect(
                "Run:\n```bash\ncurl -fsSL https://raw.githubusercontent.com/example/arclink/eb41b3fc458071ac08222982d66d225518f01fbe/bin/setup-remote-hermes-client.sh"
                in followup_text,
                followup_text,
            )
            expect("bash -s -- --host arclink.example.test --user " + unix_user + " --org OrgName" in followup_text, followup_text)
            expect("\n```\n- That helper creates" in followup_text, followup_text)
            expect("- Run: `curl -fsSL" not in followup_text, followup_text)
            expect("reply here with `/ssh-key <public key>`" in followup_text, followup_text)
            expect(f"Use the generated `hermes-orgname-remote-{unix_user}` wrapper, not your local `hermes` command" in followup_text, followup_text)
            expect("remote config, skills, MCP tools, plugins, and files" in followup_text, followup_text)
            expect(f"Raw SSH target for debugging after key install: {unix_user}@arclink.example.test" in followup_text, followup_text)
            expect(
                "https://raw.githubusercontent.com/example/arclink/main/bin/setup-remote-hermes-client.sh"
                not in followup_text,
                followup_text,
            )
            print("PASS test_completion_bundle_pins_remote_setup_helper_to_deployed_commit")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_completion_bundle_falls_back_to_branch_when_deployed_commit_lacks_helper() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_completion_remote_fallback_test")
    completion = load_module(COMPLETION_PY, "arclink_onboarding_completion_remote_fallback_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        release_state_path = root / "state" / "arclink-release.json"
        release_state_path.parent.mkdir(parents=True, exist_ok=True)
        release_state_path.write_text(
            json.dumps(
                {
                    "tracked_upstream_repo_url": "https://github.com/example/arclink.git",
                    "tracked_upstream_branch": "main",
                    "deployed_commit": "3d2f51bb8d532f03a9869244c357b73ef6afddbf",
                }
            ),
            encoding="utf-8",
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            completion._repo_ref_contains_path = lambda _cfg, _ref, _relative_path: False
            conn = control.connect_db(cfg)
            unix_user = pwd.getpwuid(os.getuid()).pw_name
            hermes_home = root / "homes" / unix_user / ".local" / "share" / "arclink-agent" / "hermes-home"
            (hermes_home / "state").mkdir(parents=True, exist_ok=True)
            insert_agent(control, conn, agent_id="agent-alex", unix_user=unix_user, hermes_home=hermes_home)

            session = control.start_onboarding_session(
                conn,
                cfg,
                platform="discord",
                chat_id="123456789",
                sender_id="123456789",
                sender_username="alex",
                sender_display_name="Alex",
            )
            session = control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="completed",
                linked_agent_id="agent-alex",
                answers={
                    "bot_platform": "discord",
                    "bot_username": "Guide",
                    "preferred_bot_name": "Guide",
                },
            )

            access = {
                "unix_user": unix_user,
                "username": unix_user,
                "password": "sup3r-secret",
                "dashboard_url": "https://arclink.example.test:30011/",
                "code_url": "https://arclink.example.test:40011/",
            }
            (hermes_home / "state" / "arclink-web-access.json").write_text(
                json.dumps(access),
                encoding="utf-8",
            )

            bundle = completion.completion_bundle_for_session(conn, cfg, session)
            expect(bundle is not None, "expected completion bundle")
            followup_text = str(bundle["followup_text"])
            expect(
                "https://raw.githubusercontent.com/example/arclink/main/bin/setup-remote-hermes-client.sh"
                in followup_text,
                followup_text,
            )
            expect("bash -s -- --host arclink.example.test --user " + unix_user + " --org OrgName" in followup_text, followup_text)
            expect(
                "https://raw.githubusercontent.com/example/arclink/3d2f51bb8d532f03a9869244c357b73ef6afddbf/bin/setup-remote-hermes-client.sh"
                not in followup_text,
                followup_text,
            )
            print("PASS test_completion_bundle_falls_back_to_branch_when_deployed_commit_lacks_helper")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_completion_bundle_lists_resources_and_scrubs_password()
    test_completion_scrubbed_text_uses_stored_receipt_when_reconstruction_fails()
    test_completion_bundle_pins_remote_setup_helper_to_deployed_commit()
    test_completion_bundle_falls_back_to_branch_when_deployed_commit_lacks_helper()
    print("PASS all 4 onboarding completion regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
