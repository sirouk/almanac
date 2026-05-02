#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
CONTROL_PY = PYTHON_DIR / "arclink_control.py"
CURATOR_ONBOARDING_PY = PYTHON_DIR / "arclink_curator_onboarding.py"
ONBOARDING_PY = PYTHON_DIR / "arclink_onboarding_flow.py"


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


def base_config_values(root: Path) -> dict[str, str]:
    return {
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
        ) VALUES (?, 'user', ?, ?, 'active', ?, ?, NULL, 'codex', 'openai:codex', '["tui-only","telegram"]', '[]', '{}', '{}', ?, ?)
        """,
        (agent_id, unix_user, unix_user, str(hermes_home), str(hermes_home / "manifest.json"), now, now),
    )
    conn.commit()


def test_telegram_operator_approve_callback_replaces_message_and_clears_buttons() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_curator_onboarding_callback_test")
    curator = load_module(CURATOR_ONBOARDING_PY, "arclink_curator_onboarding_callback_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, base_config_values(root))
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
                state="awaiting-operator-approval",
                answers={"full_name": "Alex"},
            )

            replacements: list[str] = []
            answers: list[str] = []
            outbound: list[str] = []

            curator.notify_session_state = lambda cfg, updated: None
            curator._replace_operator_callback_message = (
                lambda bot_token, callback_query, text: replacements.append(text)
            )
            curator._clear_operator_callback_buttons = lambda bot_token, callback_query: outbound.append("cleared")
            curator.telegram_answer_callback_query = (
                lambda **kwargs: answers.append(str(kwargs.get("text") or ""))
            )
            curator.send_text = lambda bot_token, chat_id, text, **kwargs: outbound.append(text)

            curator._handle_operator_callback(
                cfg=cfg,
                bot_token="test-token",
                callback_query={
                    "id": "cb_1",
                    "data": f"arclink:onboarding:approve:{session['session_id']}",
                    "message": {
                        "chat": {"id": "42", "type": "private"},
                        "message_id": 7,
                        "text": "Review this onboarding request.",
                    },
                    "from": {"id": "42", "username": "alexuser"},
                },
            )

            refreshed = control.get_onboarding_session(conn, str(session["session_id"]))
            expect(refreshed is not None, "expected refreshed onboarding session")
            expect(str(refreshed.get("state") or "") == "awaiting-bot-token", str(refreshed))
            expect(len(replacements) == 1, str(replacements))
            expect("Approved" in replacements[0], replacements[0])
            expect("@alexuser" in replacements[0], replacements[0])
            expect(outbound == [], str(outbound))
            expect(len(answers) == 1 and "Approved" in answers[0], str(answers))
            print("PASS test_telegram_operator_approve_callback_replaces_message_and_clears_buttons")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_stale_telegram_request_callback_clears_buttons_with_status() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_curator_stale_request_callback_test")
    curator = load_module(CURATOR_ONBOARDING_PY, "arclink_curator_stale_request_callback_test")
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
            },
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            request = control.request_bootstrap(
                conn,
                cfg,
                requester_identity="Alex",
                unix_user="dkstale",
                source_ip="telegram:100",
                auto_provision=True,
            )
            request_id = str(request["request_id"])
            control.approve_request(
                conn,
                request_id=request_id,
                surface="curator-channel",
                actor="@operator",
                cfg=cfg,
            )

            replacements: list[str] = []
            answers: list[str] = []
            outbound: list[str] = []

            curator._replace_operator_callback_message = (
                lambda bot_token, callback_query, text: replacements.append(text)
            )
            curator._clear_operator_callback_buttons = lambda bot_token, callback_query: outbound.append("cleared")
            curator.telegram_answer_callback_query = (
                lambda **kwargs: answers.append(str(kwargs.get("text") or ""))
            )
            curator.send_text = lambda bot_token, chat_id, text, **kwargs: outbound.append(text)

            curator._handle_operator_callback(
                cfg=cfg,
                bot_token="test-token",
                callback_query={
                    "id": "cb_2",
                    "data": f"arclink:request:approve:{request_id}",
                    "message": {
                        "chat": {"id": "42", "type": "private"},
                        "message_id": 8,
                        "text": "Pending request with stale buttons.",
                    },
                    "from": {"id": "42", "username": "alexuser"},
                },
            )

            expect(len(replacements) == 1, str(replacements))
            expect("already approved" in replacements[0], replacements[0])
            expect("@alexuser" in replacements[0], replacements[0])
            expect(outbound == [], str(outbound))
            expect(len(answers) == 1 and "already approved" in answers[0], str(answers))
            print("PASS test_stale_telegram_request_callback_clears_buttons_with_status")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_telegram_backup_callback_reopens_completed_lane_backup_setup() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_curator_backup_callback_test")
    curator = load_module(CURATOR_ONBOARDING_PY, "arclink_curator_backup_callback_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, base_config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            hermes_home = root / "homes" / "alex" / ".local" / "share" / "arclink-agent" / "hermes-home"
            hermes_home.mkdir(parents=True, exist_ok=True)
            insert_agent(control, conn, agent_id="agent-alex", unix_user="alex", hermes_home=hermes_home)
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
                state="completed",
                linked_agent_id="agent-alex",
                answers={"unix_user": "alex", "bot_platform": "telegram"},
            )

            answers: list[str] = []
            outbound: list[str] = []
            curator.telegram_answer_callback_query = (
                lambda **kwargs: answers.append(str(kwargs.get("text") or ""))
            )
            curator.send_text = lambda bot_token, chat_id, text, **kwargs: outbound.append(text)

            handled = curator._handle_user_backup_callback(
                cfg=cfg,
                bot_token="test-token",
                callback_query={
                    "id": "cb_backup",
                    "data": f"arclink:onboarding-complete:setup-backup:{session['session_id']}",
                    "message": {
                        "chat": {"id": "100", "type": "private"},
                        "message_id": 9,
                    },
                    "from": {"id": "100", "username": "alex", "first_name": "Alex"},
                },
            )

            refreshed = control.get_onboarding_session(conn, str(session["session_id"]), redact_secrets=False)
            expect(handled is True, "expected backup callback to be handled")
            expect(refreshed["state"] == "awaiting-agent-backup-repo", str(refreshed))
            expect(outbound and "private backup repo" in outbound[0], str(outbound))
            expect(answers == ["Backup setup opened."], str(answers))
            print("PASS test_telegram_backup_callback_reopens_completed_lane_backup_setup")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_telegram_operator_retry_contact_queues_discord_handoff() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_curator_retry_contact_test")
    curator = load_module(CURATOR_ONBOARDING_PY, "arclink_curator_retry_contact_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, base_config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            hermes_home = root / "homes" / "alex" / ".local" / "share" / "arclink-agent" / "hermes-home"
            hermes_home.mkdir(parents=True, exist_ok=True)
            insert_agent(control, conn, agent_id="agent-alex", unix_user="alex", hermes_home=hermes_home)
            session = control.start_onboarding_session(
                conn,
                cfg,
                platform="discord",
                chat_id="555",
                sender_id="777",
                sender_username="alex.discord",
                sender_display_name="Alex Rivera",
            )
            session = control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="completed",
                linked_agent_id="agent-alex",
                answers={
                    "unix_user": "alex",
                    "full_name": "Alex Rivera",
                    "bot_platform": "discord",
                    "discord_agent_dm_confirmation_code": "ABC-123",
                    "discord_agent_dm_handoff_sent_at": "2026-04-29T00:00:00+00:00",
                },
            )

            outbound: list[str] = []
            curator.send_text = lambda bot_token, chat_id, text, **kwargs: outbound.append(text)
            curator._handle_operator_command(
                cfg=cfg,
                bot_token="test-token",
                text="/retry_contact alex",
                message={"chat": {"id": "42"}, "from": {"id": "42", "username": "operator"}},
            )

            row = conn.execute(
                "SELECT * FROM operator_actions WHERE action_kind = 'send-discord-agent-dm'"
            ).fetchone()
            expect(row is not None, "expected retry-contact to queue a Discord DM action")
            payload = json.loads(str(row["requested_target"] or "{}"))
            expect(payload["session_id"] == session["session_id"], str(payload))
            expect(payload["agent_id"] == "agent-alex", str(payload))
            expect(payload["recipient_id"] == "777", str(payload))
            expect(payload["confirmation_code"] == "ABC-123", str(payload))
            expect(payload["force"] is True, str(payload))
            refreshed = control.get_onboarding_session(conn, str(session["session_id"]), redact_secrets=False)
            expect(
                bool((refreshed.get("answers") or {}).get("discord_agent_dm_retry_requested_at")),
                str(refreshed),
            )
            expect(outbound and "Queued Discord contact retry" in outbound[0], str(outbound))
            expect("ABC-123" in outbound[0], str(outbound))
            print("PASS test_telegram_operator_retry_contact_queues_discord_handoff")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_telegram_operator_upgrade_command_queues_upgrade_action() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_curator_upgrade_command_test")
    curator = load_module(CURATOR_ONBOARDING_PY, "arclink_curator_upgrade_command_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, base_config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            outbound: list[str] = []
            curator.send_text = lambda bot_token, chat_id, text, **kwargs: outbound.append(text)

            curator._handle_operator_command(
                cfg=cfg,
                bot_token="test-token",
                text="/upgrade",
                message={"chat": {"id": "42"}, "from": {"id": "42", "username": "operator"}},
            )

            row = conn.execute("SELECT * FROM operator_actions WHERE action_kind = 'upgrade'").fetchone()
            expect(row is not None, "expected /upgrade to queue an operator upgrade action")
            expect(row["requested_target"] == "", str(dict(row)))
            expect(row["requested_by"] == "@operator", str(dict(row)))
            expect(row["request_source"] == "telegram-command", str(dict(row)))
            expect(outbound and "Queued ArcLink upgrade/repair" in outbound[0], str(outbound))
            print("PASS test_telegram_operator_upgrade_command_queues_upgrade_action")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_telegram_operator_private_chat_can_start_personal_onboarding() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_operator_self_onboard_test")
    curator = load_module(CURATOR_ONBOARDING_PY, "arclink_curator_operator_self_onboard_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, base_config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            outbound: list[tuple[str, str]] = []
            curator.send_text = (
                lambda bot_token, chat_id, text, **kwargs: outbound.append((str(chat_id), str(text)))
            )

            curator.process_update(
                cfg=cfg,
                bot_token="test-token",
                curator_bot_id="curator-bot-id",
                update={
                    "update_id": 1,
                    "message": {
                        "chat": {"id": "42", "type": "private"},
                        "from": {"id": "42", "username": "operator", "first_name": "Op"},
                        "message_id": 9,
                        "text": "/start",
                    },
                },
            )

            with control.connect_db(cfg) as conn:
                session = control.find_active_onboarding_session(
                    conn,
                    platform="telegram",
                    sender_id="42",
                )
            expect(session is not None, "expected operator private DM to open onboarding")
            expect(session["state"] in {"awaiting-name", "awaiting-purpose"}, str(session))
            expect(outbound and outbound[0][0] == "42", str(outbound))
            expect("onboarding" in outbound[0][1].lower() or "agent" in outbound[0][1].lower(), outbound[0][1])

            curator.process_update(
                cfg=cfg,
                bot_token="test-token",
                curator_bot_id="curator-bot-id",
                update={
                    "update_id": 2,
                    "message": {
                        "chat": {"id": "42", "type": "private"},
                        "from": {"id": "42", "username": "operator", "first_name": "Op"},
                        "message_id": 10,
                        "text": "Help me approve and monitor ArcLink without losing my own work lane.",
                    },
                },
            )
            with control.connect_db(cfg) as conn:
                session = control.find_active_onboarding_session(
                    conn,
                    platform="telegram",
                    sender_id="42",
                )
            expect(session is not None, "expected operator onboarding to remain active")
            expect(session["state"] == "awaiting-unix-user", str(session))
            print("PASS test_telegram_operator_private_chat_can_start_personal_onboarding")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_retry_contact_refuses_missing_confirmation_code() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_retry_contact_missing_code_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, base_config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            hermes_home = root / "homes" / "alex" / ".local" / "share" / "arclink-agent" / "hermes-home"
            hermes_home.mkdir(parents=True, exist_ok=True)
            insert_agent(control, conn, agent_id="agent-alex", unix_user="alex", hermes_home=hermes_home)
            session = control.start_onboarding_session(
                conn,
                cfg,
                platform="discord",
                chat_id="555",
                sender_id="777",
                sender_username="alex.discord",
                sender_display_name="Alex Rivera",
            )
            control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="completed",
                linked_agent_id="agent-alex",
                answers={"unix_user": "alex", "full_name": "Alex Rivera", "bot_platform": "discord"},
            )
            try:
                control.retry_discord_contact(
                    conn,
                    cfg,
                    target="alex",
                    actor="operator",
                    request_source="test",
                )
            except ValueError as exc:
                expect("no stored Curator confirmation code" in str(exc), str(exc))
            else:
                raise AssertionError("retry_contact should reject contacts without a stored confirmation code")
            row = conn.execute(
                "SELECT * FROM operator_actions WHERE action_kind = 'send-discord-agent-dm'"
            ).fetchone()
            expect(row is None, "missing-code retry-contact must not queue a DM action")
            print("PASS test_retry_contact_refuses_missing_confirmation_code")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_discord_onboarding_user_retry_contact_queues_own_handoff() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_self_retry_contact_test")
    onboarding = load_module(ONBOARDING_PY, "arclink_onboarding_self_retry_contact_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, base_config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            hermes_home = root / "homes" / "alex" / ".local" / "share" / "arclink-agent" / "hermes-home"
            hermes_home.mkdir(parents=True, exist_ok=True)
            insert_agent(control, conn, agent_id="agent-alex", unix_user="alex", hermes_home=hermes_home)
            session = control.start_onboarding_session(
                conn,
                cfg,
                platform="discord",
                chat_id="555",
                sender_id="777",
                sender_username="alex.discord",
                sender_display_name="Alex Rivera",
            )
            session = control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="completed",
                linked_agent_id="agent-alex",
                answers={
                    "unix_user": "alex",
                    "full_name": "Alex Rivera",
                    "bot_platform": "discord",
                    "bot_username": "Guide",
                    "discord_agent_dm_confirmation_code": "ABC-123",
                },
            )

            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="discord",
                    chat_id="555",
                    sender_id="777",
                    sender_username="alex.discord",
                    sender_display_name="Alex Rivera",
                    text="/retry-contact",
                ),
                validate_bot_token=lambda raw: onboarding.BotIdentity("unused"),
            )

            row = conn.execute(
                "SELECT * FROM operator_actions WHERE action_kind = 'send-discord-agent-dm'"
            ).fetchone()
            expect(row is not None, "expected self retry-contact to queue a Discord DM action")
            payload = json.loads(str(row["requested_target"] or "{}"))
            expect(payload["session_id"] == session["session_id"], str(payload))
            expect(payload["agent_id"] == "agent-alex", str(payload))
            expect(payload["recipient_id"] == "777", str(payload))
            expect(payload["confirmation_code"] == "ABC-123", str(payload))
            expect(payload["force"] is True, str(payload))
            expect(row["request_source"] == "discord-self-retry-contact", str(dict(row)))
            expect("queued your agent bot" in replies[0].text, replies[0].text)
            expect("ABC-123" in replies[0].text, replies[0].text)
            print("PASS test_discord_onboarding_user_retry_contact_queues_own_handoff")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_telegram_command_registration_includes_user_and_operator_commands() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_curator_command_registration_test")
    curator = load_module(CURATOR_ONBOARDING_PY, "arclink_curator_command_registration_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, base_config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            calls: list[dict[str, object]] = []
            curator.telegram_set_my_commands = lambda **kwargs: calls.append(kwargs) or {"result": True}

            errors = curator.register_telegram_bot_commands(cfg, "telegram-token")

            expect(errors == [], str(errors))
            expect(len(calls) == 3, str(calls))
            command_sets = {
                str((call.get("scope") or {}).get("type")): {item["command"] for item in call["commands"]}
                for call in calls
            }
            expect("setup_backup" in command_sets["default"], str(command_sets))
            expect("verify_notion" in command_sets["default"], str(command_sets))
            expect("ssh_key" in command_sets["default"], str(command_sets))
            expect("retry_contact" not in command_sets["default"], str(command_sets))
            expect("upgrade" not in command_sets["default"], str(command_sets))
            expect("retry_contact" in command_sets["chat"], str(command_sets))
            expect("upgrade" in command_sets["chat"], str(command_sets))
            expect("approve" in command_sets["chat"], str(command_sets))
            expect(calls[-1]["scope"]["chat_id"] == "42", str(calls[-1]))
            print("PASS test_telegram_command_registration_includes_user_and_operator_commands")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_telegram_operator_approve_callback_replaces_message_and_clears_buttons()
    test_stale_telegram_request_callback_clears_buttons_with_status()
    test_telegram_backup_callback_reopens_completed_lane_backup_setup()
    test_telegram_operator_retry_contact_queues_discord_handoff()
    test_telegram_operator_upgrade_command_queues_upgrade_action()
    test_telegram_operator_private_chat_can_start_personal_onboarding()
    test_retry_contact_refuses_missing_confirmation_code()
    test_discord_onboarding_user_retry_contact_queues_own_handoff()
    test_telegram_command_registration_includes_user_and_operator_commands()
    print("PASS all 9 curator onboarding regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
