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
CURATOR_DISCORD_ONBOARDING_PY = PYTHON_DIR / "arclink_curator_discord_onboarding.py"
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


def test_telegram_operator_approval_code_blocks_single_step_approve() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_curator_approval_code_test")
    curator = load_module(CURATOR_ONBOARDING_PY, "arclink_curator_approval_code_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        values = base_config_values(root)
        values["ARCLINK_OPERATOR_TELEGRAM_APPROVAL_CODE"] = "approve-4242"
        write_config(config_path, values)
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

            outbound: list[str] = []
            curator.notify_session_state = lambda cfg, updated: None
            curator.send_text = lambda bot_token, chat_id, text, **kwargs: outbound.append(text)
            message = {"chat": {"id": "42", "type": "private"}, "from": {"id": "42", "username": "operator"}}

            curator._handle_operator_command(
                cfg=cfg,
                bot_token="test-token",
                text=f"/approve {session['session_id']}",
                message=message,
            )
            blocked = control.get_onboarding_session(conn, str(session["session_id"]))
            expect(str(blocked.get("state") or "") == "awaiting-operator-approval", str(blocked))
            expect(any("Approval code required" in item for item in outbound), str(outbound))

            curator._handle_operator_command(
                cfg=cfg,
                bot_token="test-token",
                text=f"/approve {session['session_id']} approve-4242",
                message=message,
            )
            refreshed = control.get_onboarding_session(conn, str(session["session_id"]))
            expect(str(refreshed.get("state") or "") == "awaiting-bot-token", str(refreshed))
            print("PASS test_telegram_operator_approval_code_blocks_single_step_approve")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_discord_operator_direct_actions_require_configured_code() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    discord_curator = load_module(
        CURATOR_DISCORD_ONBOARDING_PY,
        "arclink_curator_discord_code_gate_test",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        values = base_config_values(root)
        values["ARCLINK_OPERATOR_APPROVAL_CODE"] = "discord-4242"
        write_config(config_path, values)
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            expect(not discord_curator._discord_operator_code_ok(""), "blank Discord operator code must fail")
            expect(
                discord_curator._discord_operator_code_ok("discord-4242"),
                "configured Discord operator code must pass",
            )
            ok, reason = discord_curator._discord_operator_action_tail(
                command="/approve",
                text="/approve onb_test",
            )
            expect(not ok and reason == "", f"expected missing direct approve code to fail, got {ok=} {reason=!r}")
            ok, reason = discord_curator._discord_operator_action_tail(
                command="/deny",
                text="/deny onb_test discord-4242 not enough context",
            )
            expect(ok and reason == "not enough context", f"expected deny reason after code, got {ok=} {reason=!r}")
            ok, target = discord_curator._discord_retry_contact_target("/retry-contact Alex Rivera discord-4242")
            expect(ok and target == "Alex Rivera", f"expected retry-contact target before code, got {ok=} {target=!r}")
            expect(
                discord_curator._discord_component_requires_operator_code(scope="ssot", action="approve"),
                "SSOT component approve must require a code when configured",
            )
            expect(
                discord_curator._discord_component_requires_operator_code(scope="upgrade", action="dismiss"),
                "upgrade dismiss mutates notification state and must require a code when configured",
            )
            expect(
                not discord_curator._discord_component_requires_operator_code(scope="upgrade", action="preview"),
                "upgrade preview is non-mutating and should not require a code",
            )
            print("PASS test_discord_operator_direct_actions_require_configured_code")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_discord_seen_message_prune_bounds_settings_rows() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_discord_seen_prune_test")
    discord_curator = load_module(
        CURATOR_DISCORD_ONBOARDING_PY,
        "arclink_curator_discord_seen_prune_test",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, base_config_values(root))
        old_env = os.environ.copy()
        old_max = discord_curator.DISCORD_SEEN_MESSAGE_MAX_ROWS
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        discord_curator.DISCORD_SEEN_MESSAGE_MAX_ROWS = 2
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            prefix = discord_curator.DISCORD_SEEN_MESSAGE_PREFIX
            for idx, updated_at in enumerate(
                [
                    "2000-01-01T00:00:00+00:00",
                    "2099-01-01T00:00:01+00:00",
                    "2099-01-01T00:00:02+00:00",
                    "2099-01-01T00:00:03+00:00",
                ]
            ):
                conn.execute(
                    "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                    (f"{prefix}{idx}", "processed", updated_at),
                )
            conn.commit()
            discord_curator._prune_discord_seen_messages(conn)
            conn.commit()
            rows = conn.execute(
                """
                SELECT key FROM settings
                WHERE substr(key, 1, ?) = ?
                ORDER BY key
                """,
                (len(prefix), prefix),
            ).fetchall()
            keys = [str(row["key"]) for row in rows]
            expect(keys == [f"{prefix}2", f"{prefix}3"], str(keys))
            print("PASS test_discord_seen_message_prune_bounds_settings_rows")
        finally:
            discord_curator.DISCORD_SEEN_MESSAGE_MAX_ROWS = old_max
            os.environ.clear()
            os.environ.update(old_env)


def test_discord_message_handler_releases_claim_on_processing_error() -> None:
    source = CURATOR_DISCORD_ONBOARDING_PY.read_text(encoding="utf-8")
    start = source.index("    @client.event\n    async def on_message")
    end = source.index("    @client.event\n    async def on_interaction", start)
    snippet = source[start:end]
    expect("_release_discord_message_claim(message_id)" in snippet, snippet)
    expect("_mark_discord_message_processed(message_id)" in snippet, snippet)
    print("PASS test_discord_message_handler_releases_claim_on_processing_error")


def test_discord_reply_delivery_failures_propagate() -> None:
    source = CURATOR_DISCORD_ONBOARDING_PY.read_text(encoding="utf-8")
    start = source.index("    async def _send_replies")
    end = source.index("    async def _handle_dm_command", start)
    snippet = source[start:end]
    expect("except Exception" not in snippet, snippet)
    expect("raise RuntimeError" in snippet, snippet)
    print("PASS test_discord_reply_delivery_failures_propagate")


def test_telegram_upgrade_dismiss_updates_live_notification_dedupe_key() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_curator_upgrade_dismiss_test")
    curator = load_module(CURATOR_ONBOARDING_PY, "arclink_curator_upgrade_dismiss_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, base_config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            target_sha = "b" * 40
            replacements: list[str] = []
            answers: list[str] = []
            curator._replace_operator_callback_message = (
                lambda bot_token, callback_query, text: replacements.append(text)
            )
            curator._clear_operator_callback_buttons = lambda bot_token, callback_query: None
            curator.telegram_answer_callback_query = (
                lambda **kwargs: answers.append(str(kwargs.get("text") or ""))
            )

            curator._handle_operator_callback(
                cfg=cfg,
                bot_token="test-token",
                callback_query={
                    "id": "cb_dismiss",
                    "data": f"arclink:upgrade:dismiss:{target_sha}",
                    "message": {
                        "chat": {"id": "42", "type": "private"},
                        "message_id": 9,
                        "text": "ArcLink update available.",
                    },
                    "from": {"id": "42", "username": "operator"},
                },
            )

            expect(control.get_setting(conn, "arclink_upgrade_last_notified_sha", "") == target_sha, "dismiss must update live dedupe key")
            expect(control.get_setting(conn, "arclink_upgrade_last_dismissed_sha", "") == "", "dead dismissed key must not be written")
            expect(replacements and "Dismissed by @operator" in replacements[0], str(replacements))
            expect(answers and "Dismissed ArcLink update notice" in answers[0], str(answers))
            print("PASS test_telegram_upgrade_dismiss_updates_live_notification_dedupe_key")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_telegram_malformed_upgrade_callback_reports_unknown_action() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_curator_malformed_upgrade_test")
    curator = load_module(CURATOR_ONBOARDING_PY, "arclink_curator_malformed_upgrade_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, base_config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            answers: list[str] = []
            curator.telegram_answer_callback_query = (
                lambda **kwargs: answers.append(str(kwargs.get("text") or ""))
            )
            curator._handle_operator_callback(
                cfg=cfg,
                bot_token="test-token",
                callback_query={
                    "id": "cb_bad_upgrade",
                    "data": f"arclink:upgrade:explode:{'c' * 40}",
                    "message": {"chat": {"id": "42", "type": "private"}, "message_id": 9},
                    "from": {"id": "42", "username": "operator"},
                },
            )
            expect(answers == ["unknown upgrade action: explode"], str(answers))
            print("PASS test_telegram_malformed_upgrade_callback_reports_unknown_action")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_telegram_failure_ledger_error_stops_worker() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_curator_failure_ledger_test")
    curator = load_module(CURATOR_ONBOARDING_PY, "arclink_curator_failure_ledger_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, base_config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        old_get_updates = curator.telegram_get_updates
        old_process_update = curator.process_update
        old_record_failure = curator.record_onboarding_update_failure
        try:
            cfg = control.Config.from_env()
            control.connect_db(cfg).close()
            curator.telegram_get_updates = lambda **kwargs: [{"update_id": 123, "message": {"text": "/start"}}]

            def _raise_process_update(**kwargs):
                raise RuntimeError("handler failed")

            def _raise_record_failure(*args, **kwargs):
                raise RuntimeError("database is unwritable")

            curator.process_update = _raise_process_update
            curator.record_onboarding_update_failure = _raise_record_failure
            try:
                curator.run_once(cfg, "test-token", "curator-bot-id", poll_timeout=0)
            except SystemExit as exc:
                expect(exc.code == 1, f"expected SystemExit(1), got {exc.code!r}")
            else:
                raise AssertionError("expected failure-ledger write failure to stop the worker")
            print("PASS test_telegram_failure_ledger_error_stops_worker")
        finally:
            curator.telegram_get_updates = old_get_updates
            curator.process_update = old_process_update
            curator.record_onboarding_update_failure = old_record_failure
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
            markups: list[dict | None] = []

            def _capture_send(bot_token, chat_id, text, **kwargs):
                outbound.append(text)
                markups.append(kwargs.get("reply_markup"))

            curator.send_text = _capture_send
            answered: list[str] = []
            curator.telegram_answer_callback_query = lambda **kwargs: answered.append(str(kwargs.get("text") or ""))

            curator._handle_operator_command(
                cfg=cfg,
                bot_token="test-token",
                text="/upgrade",
                message={"chat": {"id": "42"}, "from": {"id": "42", "username": "operator"}},
            )

            row = conn.execute("SELECT * FROM operator_actions WHERE action_kind = 'upgrade'").fetchone()
            expect(row is None, "bare /upgrade renders the one-tap menu and must not queue")
            expect(outbound and "upgrade menu" in outbound[-1], str(outbound))
            menu_markup = markups[-1] or {}
            menu_rows = menu_markup.get("inline_keyboard") or []
            expect(menu_rows and menu_rows[0][0]["text"] == "Apply Control Upgrade", str(menu_markup))
            one_tap_data = str(menu_rows[0][0]["callback_data"])
            expect(one_tap_data.startswith("arclink:/upgrade_apply "), one_tap_data)

            # Pressing the menu button on the long-poll transport queues the
            # upgrade through the same Operator Raven gate: one tap, no typing.
            curator._handle_operator_callback(
                cfg=cfg,
                bot_token="test-token",
                callback_query={
                    "id": "cbq-menu-1",
                    "data": one_tap_data,
                    "from": {"id": "42", "username": "operator"},
                    "message": {"message_id": 7, "chat": {"id": "42", "type": "private"}},
                },
            )
            row = conn.execute("SELECT * FROM operator_actions WHERE action_kind = 'upgrade'").fetchone()
            expect(row is not None, "one-tap menu button must queue the upgrade")
            expect(row["request_source"] == "operator-raven", str(dict(row)))
            expect(answered and "queued an ArcLink upgrade" in answered[-1], str(answered))

            # Replaying the same callback fails closed (single-use nonce).
            before = conn.execute("SELECT COUNT(*) AS n FROM operator_actions").fetchone()["n"]
            curator._handle_operator_callback(
                cfg=cfg,
                bot_token="test-token",
                callback_query={
                    "id": "cbq-menu-2",
                    "data": one_tap_data,
                    "from": {"id": "42", "username": "operator"},
                    "message": {"message_id": 7, "chat": {"id": "42", "type": "private"}},
                },
            )
            expect(answered and "expired or was already used" in answered[-1], str(answered[-1]))
            after = conn.execute("SELECT COUNT(*) AS n FROM operator_actions").fetchone()["n"]
            expect(after == before, "nonce replay must not queue a second action")
            conn.execute("DELETE FROM operator_actions")
            conn.commit()

            curator._handle_operator_command(
                cfg=cfg,
                bot_token="test-token",
                text="/upgrade confirm",
                message={"chat": {"id": "42"}, "from": {"id": "42", "username": "operator"}},
            )

            row = conn.execute("SELECT * FROM operator_actions WHERE action_kind = 'upgrade'").fetchone()
            expect(row is not None, "expected /upgrade to queue an operator upgrade action")
            expect(row["requested_target"] == "", str(dict(row)))
            expect(row["requested_by"] == "@operator", str(dict(row)))
            # /upgrade is now a first-class Operator Raven action on every operator surface.
            expect(row["request_source"] == "operator-raven", str(dict(row)))
            expect(outbound and "queued an ArcLink upgrade/repair" in outbound[-1], str(outbound))
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
            expect("pin_upgrade" in command_sets["chat"], str(command_sets))
            expect("upgrade_policy" in command_sets["chat"], str(command_sets))
            expect("upgrade_sweep" in command_sets["chat"], str(command_sets))
            expect("fleet_drain" in command_sets["chat"], str(command_sets))
            expect("fleet_resume" in command_sets["chat"], str(command_sets))
            expect("action_status" in command_sets["chat"], str(command_sets))
            expect("academy_roster" in command_sets["chat"], str(command_sets))
            expect("approve" in command_sets["chat"], str(command_sets))
            expect(calls[-1]["scope"]["chat_id"] == "42", str(calls[-1]))
            print("PASS test_telegram_command_registration_includes_user_and_operator_commands")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_discord_operator_slash_registration_matches_raven_operator_surface() -> None:
    source = CURATOR_DISCORD_ONBOARDING_PY.read_text(encoding="utf-8")
    for command in (
        "operator-status",
        "operator-agents",
        "operator-fleet",
        "worker-probe",
        "user-lookup",
        "billing-status",
        "backup-status",
        "workspace-status",
        "pod-repair",
        "upgrade-check",
        "upgrade-policy",
        "upgrade",
        "pin-upgrade",
        "upgrade-sweep",
        "fleet-drain",
        "fleet-resume",
        "rollout",
        "action-status",
        "academy-status",
        "academy-roster",
        "retry-contact",
    ):
        needle = f'@tree.command(name="{command}"'
        expect(needle in source, f"missing Discord Operator slash registration for /{command}")
    print("PASS test_discord_operator_slash_registration_matches_raven_operator_surface")


def main() -> int:
    test_telegram_operator_approve_callback_replaces_message_and_clears_buttons()
    test_telegram_operator_approval_code_blocks_single_step_approve()
    test_discord_operator_direct_actions_require_configured_code()
    test_discord_seen_message_prune_bounds_settings_rows()
    test_discord_message_handler_releases_claim_on_processing_error()
    test_discord_reply_delivery_failures_propagate()
    test_telegram_upgrade_dismiss_updates_live_notification_dedupe_key()
    test_telegram_malformed_upgrade_callback_reports_unknown_action()
    test_telegram_failure_ledger_error_stops_worker()
    test_stale_telegram_request_callback_clears_buttons_with_status()
    test_telegram_backup_callback_reopens_completed_lane_backup_setup()
    test_telegram_operator_retry_contact_queues_discord_handoff()
    test_telegram_operator_upgrade_command_queues_upgrade_action()
    test_telegram_operator_private_chat_can_start_personal_onboarding()
    test_retry_contact_refuses_missing_confirmation_code()
    test_discord_onboarding_user_retry_contact_queues_own_handoff()
    test_telegram_command_registration_includes_user_and_operator_commands()
    test_discord_operator_slash_registration_matches_raven_operator_surface()
    print("PASS all 18 curator onboarding regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
