#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROVISIONER_PY = REPO / "python" / "almanac_enrollment_provisioner.py"
CONTROL_PY = REPO / "python" / "almanac_control.py"
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


def extract(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


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
        "ALMANAC_SSOT_NOTION_SPACE_URL": "https://www.notion.so/Acme-SSOT-1234567890abcdef1234567890abcdef",
        "ALMANAC_SSOT_NOTION_SPACE_ID": "12345678-90ab-cdef-1234-567890abcdef",
        "ALMANAC_SSOT_NOTION_SPACE_KIND": "database",
        "ALMANAC_SSOT_NOTION_TOKEN": "secret_test",
        "ALMANAC_SSOT_NOTION_API_VERSION": "2026-03-11",
        "ALMANAC_MODEL_PRESET_CODEX": "openai:codex",
        "ALMANAC_MODEL_PRESET_OPUS": "anthropic:claude-opus",
        "ALMANAC_MODEL_PRESET_CHUTES": "chutes:model-router",
        "ALMANAC_CURATOR_CHANNELS": "telegram",
        "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "1",
        "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED": "0",
    }


def insert_agent(mod, conn, *, agent_id: str, unix_user: str) -> None:
    now = mod.utc_now_iso()
    hermes_home = Path("/home") / unix_user / ".local" / "share" / "almanac-agent" / "hermes-home"
    conn.execute(
        """
        INSERT INTO agents (
          agent_id, role, unix_user, display_name, status, hermes_home, manifest_path,
          archived_state_path, model_preset, model_string, channels_json,
          allowed_mcps_json, home_channel_json, operator_notify_channel_json,
          notes, created_at, last_enrolled_at
        ) VALUES (?, 'user', ?, ?, 'active', ?, ?, NULL, 'codex', 'openai:codex', '["telegram"]', '[]', '{}', '{}', '', ?, ?)
        """,
        (
            agent_id,
            unix_user,
            "Alex",
            str(hermes_home),
            str(hermes_home / "manifest.json"),
            now,
            now,
        ),
    )
    conn.commit()


def test_onboarding_paths_refresh_managed_memory_after_access_surfaces_exist() -> None:
    text = PROVISIONER_PY.read_text(encoding="utf-8")
    telegram = extract(text, "def _configure_user_telegram_gateway", "def _configure_user_discord_gateway")
    discord = extract(text, "def _configure_user_discord_gateway", "def _run_pending_onboarding_gateway_configs")
    auto = extract(text, "def _run_one(conn, cfg: Config, row: dict) -> None:", "def main() -> None:")

    expect("_refresh_user_agent_memory(" in telegram, "telegram onboarding should refresh managed memory")
    expect("_refresh_user_agent_memory(" in discord, "discord onboarding should refresh managed memory")
    expect("_refresh_user_agent_memory(" in auto, "auto-provision onboarding should refresh managed memory")
    print("PASS test_onboarding_paths_refresh_managed_memory_after_access_surfaces_exist")


def test_onboarding_paths_enter_notion_phase_before_final_completion() -> None:
    text = PROVISIONER_PY.read_text(encoding="utf-8")
    telegram = extract(text, "def _configure_user_telegram_gateway", "def _configure_user_discord_gateway")
    discord = extract(text, "def _configure_user_discord_gateway", "def _run_pending_onboarding_gateway_configs")

    expect("_begin_notion_onboarding_phase(" in telegram, "telegram onboarding should enter notion verification when configured")
    expect("_begin_notion_onboarding_phase(" in discord, "discord onboarding should enter notion verification when configured")
    expect("_run_pending_onboarding_notion_verifications(" in text, "provisioner should poll pending notion verifications")
    print("PASS test_onboarding_paths_enter_notion_phase_before_final_completion")


def test_onboarding_notion_verification_poll_is_single_flight() -> None:
    text = PROVISIONER_PY.read_text(encoding="utf-8")
    wrapper = extract(
        text,
        "def _run_pending_onboarding_notion_verifications(conn, cfg: Config) -> None:",
        "def _run_pending_onboarding_notion_verifications_locked(conn, cfg: Config) -> None:",
    )
    expect("notion-claim-poll.lock" in wrapper, wrapper)
    expect("fcntl.LOCK_EX | fcntl.LOCK_NB" in wrapper, wrapper)
    expect("_run_pending_onboarding_notion_verifications_locked(conn, cfg)" in wrapper, wrapper)
    print("PASS test_onboarding_notion_verification_poll_is_single_flight")


def test_onboarding_gateway_updates_agent_runtime_model_after_provider_seed() -> None:
    text = PROVISIONER_PY.read_text(encoding="utf-8")
    telegram = extract(text, "def _configure_user_telegram_gateway", "def _configure_user_discord_gateway")
    discord = extract(text, "def _configure_user_discord_gateway", "def _run_pending_onboarding_gateway_configs")

    expect("def _session_runtime_model(" in text, "provisioner should derive the final provider/model after seeding Hermes")
    expect("model_preset, model_string = _session_runtime_model(cfg, session, provider_runtime)" in telegram, telegram)
    expect("model_preset=model_preset" in telegram, telegram)
    expect("model_string=model_string" in telegram, telegram)
    expect("model_preset, model_string = _session_runtime_model(cfg, session, provider_runtime)" in discord, discord)
    expect("model_preset=model_preset" in discord, discord)
    expect("model_string=model_string" in discord, discord)
    print("PASS test_onboarding_gateway_updates_agent_runtime_model_after_provider_seed")


def test_discord_onboarding_writes_home_channel_env() -> None:
    text = PROVISIONER_PY.read_text(encoding="utf-8")
    writer = extract(text, "def _write_env_values", "def _notify_user_via_curator")
    telegram = extract(text, "def _configure_user_telegram_gateway", "def _configure_user_discord_gateway")
    discord = extract(text, "def _configure_user_discord_gateway", "def _run_pending_onboarding_gateway_configs")

    expect('"TELEGRAM_REACTIONS": "true"' in telegram, telegram)
    expect('"DISCORD_REACTIONS": "true"' in telegram, telegram)
    expect("discord_create_dm_channel(" in discord, discord)
    expect('"DISCORD_HOME_CHANNEL": discord_home_channel_id' in discord, discord)
    expect('"DISCORD_HOME_CHANNEL_NAME": "Direct Message"' in discord, discord)
    expect('"channel_id": discord_home_channel_id' in discord, discord)
    expect('"TELEGRAM_REACTIONS": "true"' in discord, discord)
    expect('"DISCORD_REACTIONS": "true"' in discord, discord)
    expect("path.chmod(0o600)" in writer, "gateway env files should be user-only because they contain bot tokens")
    print("PASS test_discord_onboarding_writes_home_channel_env")


def test_discord_completion_handoff_queues_root_dm_action() -> None:
    provisioner_text = PROVISIONER_PY.read_text(encoding="utf-8")
    curator_text = (PYTHON_DIR / "almanac_curator_discord_onboarding.py").read_text(encoding="utf-8")

    expect("def _run_pending_discord_agent_dm_actions" in provisioner_text, "provisioner should own root-side user bot DM sends")
    expect('action_kind="send-discord-agent-dm"' in provisioner_text, "provisioner should process Discord DM handoff actions")
    expect("_run_pending_discord_agent_dm_actions(conn, cfg)" in provisioner_text, "main loop should run Discord DM handoff actions")
    expect('action_kind="send-discord-agent-dm"' in curator_text, "Curator should queue the handoff after completion links")
    expect("ensure_discord_agent_dm_confirmation_code" in curator_text, "Curator should show the same visual confirmation code")
    expect('@tree.command(name="onboard"' in curator_text, "Curator Discord should register /onboard")
    expect('@tree.command(name="backup"' in curator_text, "Curator Discord should register /backup")
    expect('@tree.command(name="sshkey"' in curator_text, "Curator Discord should register /sshkey")
    expect('@tree.command(name="retry-contact"' in curator_text, "Curator Discord should expose /retry-contact")
    expect('target: str = ""' in curator_text, "Curator Discord /retry-contact target should be optional for user self-retry")
    expect('_handle_dm_command(interaction, "/retry-contact")' in curator_text, "Curator Discord should route DM /retry-contact to onboarding flow")
    expect('command in {"/retry-contact", "/retry_contact"}' in curator_text, "Curator Discord should accept typed retry-contact aliases")
    print("PASS test_discord_completion_handoff_queues_root_dm_action")


def test_retry_contact_force_resends_discord_handoff_after_sent_marker() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_retry_contact_force_test")
    provisioner = load_module(PROVISIONER_PY, "almanac_enrollment_provisioner_retry_contact_force_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            hermes_home = root / "homes" / "alex" / ".local" / "share" / "almanac-agent" / "hermes-home"
            hermes_home.mkdir(parents=True, exist_ok=True)
            (hermes_home / ".env").write_text("DISCORD_BOT_TOKEN='agent-token'\n", encoding="utf-8")
            now = control.utc_now_iso()
            conn.execute(
                """
                INSERT INTO agents (
                  agent_id, role, unix_user, display_name, status, hermes_home, manifest_path,
                  archived_state_path, model_preset, model_string, channels_json,
                  allowed_mcps_json, home_channel_json, operator_notify_channel_json,
                  notes, created_at, last_enrolled_at
                ) VALUES (?, 'user', ?, ?, 'active', ?, ?, NULL, 'codex', 'openai:codex', '["discord"]', '[]', '{}', '{}', '', ?, ?)
                """,
                (
                    "agent-alex",
                    "alex",
                    "AlexBot",
                    str(hermes_home),
                    str(hermes_home / "manifest.json"),
                    now,
                    now,
                ),
            )
            conn.commit()
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
                    "bot_platform": "discord",
                    "bot_username": "AlexBot",
                    "discord_agent_dm_confirmation_code": "ABC-123",
                    "discord_agent_dm_handoff_sent_at": "2026-04-20T00:00:00+00:00",
                },
            )
            action_row, created = control.request_operator_action(
                conn,
                action_kind="send-discord-agent-dm",
                requested_by="operator",
                request_source="test-retry-contact",
                requested_target=json.dumps(
                    {
                        "session_id": session["session_id"],
                        "agent_id": "agent-alex",
                        "recipient_id": "777",
                        "force": True,
                    },
                    sort_keys=True,
                ),
                dedupe_by_target=True,
            )
            expect(created, str(action_row))

            sent: list[dict[str, str]] = []
            provisioner.discord_create_dm_channel = lambda **kwargs: {"id": "dm-777"}
            provisioner.discord_send_message = lambda **kwargs: sent.append(kwargs) or {"id": "msg-2"}
            provisioner._run_pending_discord_agent_dm_actions(conn, cfg)

            refreshed_action = conn.execute(
                "SELECT status, note FROM operator_actions WHERE id = ?",
                (int(action_row["id"]),),
            ).fetchone()
            expect(refreshed_action["status"] == "completed", str(dict(refreshed_action)))
            expect(len(sent) == 1, str(sent))
            expect(sent[0]["bot_token"] == "agent-token", str(sent))
            expect(sent[0]["channel_id"] == "dm-777", str(sent))
            expect("ABC-123" in sent[0]["text"], sent[0]["text"])
            refreshed_session = control.get_onboarding_session(conn, str(session["session_id"]), redact_secrets=False)
            answers = refreshed_session.get("answers") or {}
            expect(answers.get("discord_agent_dm_handoff_message_id") == "msg-2", str(answers))
            expect(answers.get("discord_agent_dm_handoff_error") == "", str(answers))

            bad_action, bad_created = control.request_operator_action(
                conn,
                action_kind="send-discord-agent-dm",
                requested_by="operator",
                request_source="test-retry-contact",
                requested_target=json.dumps(
                    {
                        "session_id": session["session_id"],
                        "agent_id": "agent-alex",
                        "recipient_id": "777",
                        "confirmation_code": "WRONG",
                        "force": True,
                    },
                    sort_keys=True,
                ),
                dedupe_by_target=True,
            )
            expect(bad_created, str(bad_action))
            provisioner._run_pending_discord_agent_dm_actions(conn, cfg)
            bad_refreshed = conn.execute(
                "SELECT status, note FROM operator_actions WHERE id = ?",
                (int(bad_action["id"]),),
            ).fetchone()
            expect(bad_refreshed["status"] == "failed", str(dict(bad_refreshed)))
            expect("confirmation code mismatch" in bad_refreshed["note"].lower(), str(dict(bad_refreshed)))
            expect(len(sent) == 1, f"mismatched confirmation code must not send another DM: {sent}")
            print("PASS test_retry_contact_force_resends_discord_handoff_after_sent_marker")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_completion_bundle_send_is_idempotent() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_completion_idempotent_test")
    provisioner = load_module(PROVISIONER_PY, "almanac_enrollment_provisioner_completion_idempotent_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            session = control.start_onboarding_session(
                conn,
                cfg,
                platform="telegram",
                chat_id="123456",
                sender_id="123456",
                sender_username="alex",
                sender_display_name="Alex",
            )
            session = control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="completed",
            )
            deliveries: list[dict[str, str]] = []
            provisioner.completion_bundle_for_session = lambda *args, **kwargs: {
                "full_text": "lane ready",
                "scrubbed_text": "lane ready",
                "followup_text": "links",
                "telegram_reply_markup": None,
                "discord_components": None,
            }
            provisioner._notify_user_via_curator = lambda *args, **kwargs: deliveries.append({"message_id": "42"}) or {"message_id": "42"}

            provisioner._send_completion_bundle(conn, cfg, session)
            refreshed = control.get_onboarding_session(conn, str(session["session_id"]), redact_secrets=False)
            expect(len(deliveries) == 1, str(deliveries))
            expect(bool((refreshed.get("answers") or {}).get("completion_bundle_sent_at")), str(refreshed))

            provisioner._send_completion_bundle(conn, cfg, refreshed)
            expect(len(deliveries) == 1, f"expected duplicate completion delivery to be skipped, got {deliveries}")
            print("PASS test_completion_bundle_send_is_idempotent")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_completed_backup_setup_prompt_backfill_is_idempotent_for_chat_onboarding() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_backup_prompt_backfill_test")
    provisioner = load_module(PROVISIONER_PY, "almanac_enrollment_provisioner_backup_prompt_backfill_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            for agent_id, unix_user in (("agent-alex", "alex"), ("agent-tessa", "tessa"), ("agent-backed", "backed")):
                insert_agent(control, conn, agent_id=agent_id, unix_user=unix_user)

            discord_session = control.start_onboarding_session(
                conn,
                cfg,
                platform="discord",
                chat_id="555",
                sender_id="777",
                sender_username="alex",
                sender_display_name="Alex",
            )
            discord_session = control.save_onboarding_session(
                conn,
                session_id=str(discord_session["session_id"]),
                state="completed",
                linked_agent_id="agent-alex",
                answers={"unix_user": "alex", "bot_platform": "discord"},
            )
            telegram_session = control.start_onboarding_session(
                conn,
                cfg,
                platform="telegram",
                chat_id="123",
                sender_id="123",
                sender_username="tessa",
                sender_display_name="Tessa",
            )
            telegram_session = control.save_onboarding_session(
                conn,
                session_id=str(telegram_session["session_id"]),
                state="completed",
                linked_agent_id="agent-tessa",
                answers={"unix_user": "tessa", "bot_platform": "telegram"},
            )
            verified_session = control.start_onboarding_session(
                conn,
                cfg,
                platform="discord",
                chat_id="999",
                sender_id="999",
                sender_username="backed",
                sender_display_name="Backed",
            )
            control.save_onboarding_session(
                conn,
                session_id=str(verified_session["session_id"]),
                state="completed",
                linked_agent_id="agent-backed",
                answers={"unix_user": "backed", "bot_platform": "discord", "agent_backup_verified": True},
            )

            deliveries: list[dict[str, object]] = []

            def fake_notify(cfg, *, session, message, telegram_reply_markup=None, telegram_parse_mode="", discord_components=None):
                deliveries.append(
                    {
                        "session_id": session["session_id"],
                        "platform": session["platform"],
                        "message": message,
                        "telegram_reply_markup": telegram_reply_markup,
                        "discord_components": discord_components,
                    }
                )
                if session["platform"] == "discord":
                    return {"id": f"discord-{len(deliveries)}", "channel_id": session["chat_id"]}
                return {"message_id": len(deliveries)}

            provisioner._notify_user_via_curator = fake_notify

            provisioner._run_completed_agent_backup_prompt_backfill(conn, cfg)
            expect(len(deliveries) == 2, str(deliveries))
            by_platform = {str(item["platform"]): item for item in deliveries}
            expect("`/setup-backup`" in str(deliveries[0]["message"]), str(deliveries))
            expect(by_platform["discord"]["discord_components"], str(deliveries))
            expect(by_platform["telegram"]["telegram_reply_markup"], str(deliveries))

            refreshed_discord = control.get_onboarding_session(conn, str(discord_session["session_id"]), redact_secrets=False)
            answers = refreshed_discord.get("answers") or {}
            expect(
                answers.get("agent_backup_setup_prompt_version")
                == provisioner.AGENT_BACKUP_SETUP_PROMPT_VERSION,
                str(answers),
            )

            provisioner._run_completed_agent_backup_prompt_backfill(conn, cfg)
            expect(len(deliveries) == 2, f"expected backfill to be one-shot per prompt version, got {deliveries}")
            print("PASS test_completed_backup_setup_prompt_backfill_is_idempotent_for_chat_onboarding")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_webhook_verified_claim_finishes_onboarding_and_sends_completion_bundle() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_provisioner_webhook_complete_test")
    provisioner = load_module(PROVISIONER_PY, "almanac_enrollment_provisioner_webhook_complete_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            insert_agent(control, conn, agent_id="agent-alex", unix_user="alex")
            control.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                verification_status="unverified",
                write_mode="read_only",
            )
            session = control.start_onboarding_session(
                conn,
                cfg,
                platform="telegram",
                chat_id="123456",
                sender_id="123456",
                sender_username="alex",
                sender_display_name="Alex",
            )
            session = control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-notion-verification",
                linked_agent_id="agent-alex",
                answers={
                    "unix_user": "alex",
                    "bot_platform": "telegram",
                    "bot_username": "Guide",
                    "preferred_bot_name": "Guide",
                    "full_name": "Alex",
                    "notion_claim_id": "nclaim_complete",
                    "notion_claim_email": "alex@example.com",
                    "notion_claim_url": "https://www.notion.so/claim-page",
                    "notion_claim_expires_at": "2026-04-21T00:00:00+00:00",
                },
            )
            now = control.utc_now_iso()
            conn.execute(
                """
                INSERT INTO notion_identity_claims (
                  claim_id, session_id, agent_id, unix_user, claimed_notion_email,
                  notion_page_id, notion_page_url, status, failure_reason,
                  verified_notion_user_id, verified_notion_email, created_at, updated_at, expires_at, verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', '', '', '', ?, ?, ?, NULL)
                """,
                (
                    "nclaim_complete",
                    str(session["session_id"]),
                    "agent-alex",
                    "alex",
                    "alex@example.com",
                    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "https://www.notion.so/claim-page",
                    now,
                    now,
                    (control.utc_now() + control.dt.timedelta(hours=1)).replace(microsecond=0).isoformat(),
                ),
            )
            conn.commit()
            deliveries: list[dict[str, object]] = []
            refresh_calls: list[tuple[str, str]] = []
            provisioner.completion_bundle_for_session = lambda *args, **kwargs: {
                "full_text": "lane ready bundle",
                "scrubbed_text": "lane ready bundle",
                "followup_text": "links",
                "telegram_reply_markup": None,
                "discord_components": None,
            }
            provisioner._refresh_user_agent_identity_prompt = (
                lambda cfg, *, unix_user, home, hermes_home, uid, bot_name, user_name: refresh_calls.append(("identity", unix_user))
            )
            provisioner._refresh_user_agent_memory = (
                lambda conn, cfg, *, agent_id, unix_user, home, hermes_home, uid: refresh_calls.append(("memory", agent_id))
            )
            provisioner._restart_user_agent_gateway_if_enabled = (
                lambda *, unix_user, home, hermes_home, uid: refresh_calls.append(("gateway-restart", unix_user)) or True
            )
            provisioner.pwd.getpwnam = lambda unix_user: type(
                "Passwd",
                (),
                {
                    "pw_dir": str(root / "home" / unix_user),
                    "pw_uid": 1000,
                },
            )()
            provisioner._notify_user_via_curator = (
                lambda cfg, *, session, message, telegram_reply_markup=None, telegram_parse_mode="", discord_components=None: deliveries.append(
                    {
                        "message": message,
                        "telegram_parse_mode": telegram_parse_mode,
                        "session_id": str(session.get("session_id") or ""),
                    }
                )
                or {"message_id": str(len(deliveries))}
            )
            control.store_notion_event(
                conn,
                event_id="event-claim-complete",
                event_type="page.properties_updated",
                payload={
                    "entity": {
                        "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "type": "page",
                    }
                },
            )
            control.retrieve_notion_page = lambda **kwargs: {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "last_edited_by": {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "type": "person",
                    "person": {"email": "alex@example.com"},
                },
                "properties": {},
            }
            control.update_notion_page = lambda **kwargs: {
                "id": kwargs["page_id"],
                "properties": kwargs["payload"]["properties"],
            }

            batch_result = control.process_pending_notion_events(conn)
            expect(batch_result["verified_claims"] == 1, str(batch_result))
            provisioner._run_pending_onboarding_notion_verifications(conn, cfg)

            refreshed = control.get_onboarding_session(conn, str(session["session_id"]), redact_secrets=False)
            expect(str(refreshed.get("state") or "") == "completed", str(refreshed))
            answers = refreshed.get("answers") or {}
            expect(bool(answers.get("completion_bundle_sent_at")), str(answers))
            expect(str(answers.get("notion_verified_email") or "") == "alex@example.com", str(answers))
            identity = control.get_agent_identity(conn, agent_id="agent-alex", unix_user="alex")
            expect(identity is not None and identity["verification_status"] == "verified", str(identity))
            expect(
                refresh_calls == [("identity", "alex"), ("memory", "agent-alex"), ("gateway-restart", "alex")],
                str(refresh_calls),
            )
            expect(len(deliveries) == 2, str(deliveries))
            expect("Verified. I can now write to shared Notion" in str(deliveries[0]["message"]), str(deliveries))
            expect(str(deliveries[1]["message"]) == "lane ready bundle", str(deliveries))
            refresh_job = conn.execute(
                """
                SELECT last_status, last_note
                FROM refresh_jobs
                WHERE job_kind = 'notion-claim-poll'
                ORDER BY rowid DESC
                LIMIT 1
                """
            ).fetchone()
            expect(refresh_job is not None and refresh_job["last_status"] == "ok", str(dict(refresh_job) if refresh_job else {}))
            expect("verified_sessions=1" in str(refresh_job["last_note"] or ""), str(dict(refresh_job)))
            expect("SLO targets" in str(refresh_job["last_note"] or ""), str(dict(refresh_job)))
            print("PASS test_webhook_verified_claim_finishes_onboarding_and_sends_completion_bundle")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_gateway_failures_notify_user_with_provision_error_status() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_gateway_failure_notify_test")
    provisioner = load_module(PROVISIONER_PY, "almanac_enrollment_provisioner_gateway_failure_notify_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            session = control.start_onboarding_session(
                conn,
                cfg,
                platform="telegram",
                chat_id="123456",
                sender_id="123456",
                sender_username="alex",
                sender_display_name="Alex",
            )
            session = control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="provision-pending",
                linked_agent_id="agent-alex",
                answers={
                    "bot_platform": "telegram",
                    "bot_username": "Guide",
                    "preferred_bot_name": "Guide",
                    "unix_user": "alex",
                },
            )
            provisioner.list_pending_onboarding_bot_configurations = lambda conn: [control.get_onboarding_session(conn, str(session["session_id"]), redact_secrets=False)]
            provisioner._migrate_legacy_onboarding_session = lambda conn, cfg, session: session
            provisioner._configure_user_telegram_gateway = lambda conn, cfg, session: (_ for _ in ()).throw(RuntimeError("gateway startup failed"))
            notifications: list[str] = []
            provisioner._notify_user_via_curator = lambda cfg, *, session, message, telegram_reply_markup=None, telegram_parse_mode="", discord_components=None: notifications.append(message) or {"message_id": "1"}

            provisioner._run_pending_onboarding_gateway_configs(conn, cfg)

            refreshed = control.get_onboarding_session(conn, str(session["session_id"]), redact_secrets=False)
            expect(str(refreshed.get("provision_error") or "") == "gateway startup failed", str(refreshed))
            expect(len(notifications) == 1, str(notifications))
            expect("gateway startup failed" in notifications[0], str(notifications))
            expect("/status" in notifications[0], str(notifications))
            print("PASS test_gateway_failures_notify_user_with_provision_error_status")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_operator_upgrade_actions_run_root_upgrade_and_notify_operator() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_operator_upgrade_queue_test")
    provisioner = load_module(PROVISIONER_PY, "almanac_enrollment_provisioner_operator_upgrade_queue_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        values = config_values(root)
        values["OPERATOR_NOTIFY_CHANNEL_PLATFORM"] = "telegram"
        values["OPERATOR_NOTIFY_CHANNEL_ID"] = "1000000001"
        write_config(config_path, values)
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            action_row, created = control.request_operator_action(
                conn,
                action_kind="upgrade",
                requested_by="@alex",
                request_source="telegram-button",
                requested_target="bbbbbbbbbbbb2222222222222222222222222222",
            )
            expect(created is True, str(action_row))

            def fake_run_host_upgrade(cfg, *, log_path):
                log_path.write_text("Fetching Almanac upstream...\nAlmanac upgrade complete.\n", encoding="utf-8")
                return subprocess.CompletedProcess(
                    args=[str(cfg.repo_dir / "deploy.sh"), "upgrade"],
                    returncode=0,
                    stdout="",
                    stderr="",
                )

            provisioner._run_host_upgrade = fake_run_host_upgrade
            provisioner._run_pending_operator_actions(conn, cfg)

            refreshed = conn.execute("SELECT status, log_path FROM operator_actions WHERE id = ?", (int(action_row["id"]),)).fetchone()
            expect(refreshed is not None and refreshed["status"] == "completed", str(dict(refreshed) if refreshed else {}))
            expect(str(refreshed["log_path"] or "").endswith(f"upgrade-{action_row['id']}.log"), str(dict(refreshed)))

            operator_rows = conn.execute(
                "SELECT message FROM notification_outbox WHERE target_kind = 'operator' ORDER BY id ASC"
            ).fetchall()
            expect(len(operator_rows) == 2, str([dict(row) for row in operator_rows]))
            expect("Starting Almanac upgrade" in str(operator_rows[0]["message"] or ""), str([dict(row) for row in operator_rows]))
            expect("completed successfully" in str(operator_rows[1]["message"] or ""), str([dict(row) for row in operator_rows]))
            print("PASS test_operator_upgrade_actions_run_root_upgrade_and_notify_operator")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_operator_pin_upgrade_actions_run_component_upgrade_and_notify_operator() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_operator_pin_upgrade_queue_test")
    provisioner = load_module(PROVISIONER_PY, "almanac_enrollment_provisioner_operator_pin_upgrade_queue_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        values = config_values(root)
        values["OPERATOR_NOTIFY_CHANNEL_PLATFORM"] = "telegram"
        values["OPERATOR_NOTIFY_CHANNEL_ID"] = "1000000001"
        write_config(config_path, values)
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            target = "bbbbbbbbbbbb2222222222222222222222222222"
            now = control.utc_now_iso()
            token = control.register_pin_upgrade_action(
                conn,
                items=[
                    {
                        "component": "hermes-agent",
                        "kind": "git-commit",
                        "field": "ref",
                        "current": "aaaaaaaaaaaa1111111111111111111111111111",
                        "target": target,
                    },
                    {
                        "component": "hermes-docs",
                        "kind": "git-commit",
                        "field": "ref",
                        "current": "aaaaaaaaaaaa1111111111111111111111111111",
                        "target": target,
                    },
                ],
                install_items=[
                    {
                        "component": "hermes-agent",
                        "kind": "git-commit",
                        "field": "ref",
                        "current": "aaaaaaaaaaaa1111111111111111111111111111",
                        "target": target,
                    }
                ],
            )
            conn.executemany(
                """
                INSERT INTO pin_upgrade_notifications (
                  component, field, current_pin, target_value, first_seen_at,
                  notify_count, silenced
                ) VALUES (?, 'ref', ?, ?, ?, 2, 0)
                """,
                [
                    ("hermes-agent", "aaaaaaaaaaaa1111111111111111111111111111", target, now),
                    ("hermes-docs", "aaaaaaaaaaaa1111111111111111111111111111", target, now),
                ],
            )
            conn.commit()
            action_row, created = control.request_operator_action(
                conn,
                action_kind="pin-upgrade",
                requested_by="@alex",
                request_source="telegram-button",
                requested_target=token,
                dedupe_by_target=True,
            )
            expect(created is True, str(action_row))

            args = provisioner._pin_upgrade_command_args(
                cfg,
                {
                    "component": "hermes-agent",
                    "kind": "git-commit",
                    "target": target,
                },
                skip_upgrade=False,
            )
            expect(args[-2:] == ["--ref", target], str(args))
            expect(args[1:3] == ["hermes-agent", "apply"], str(args))

            def fake_run_pin_upgrade_action(cfg, payload, *, log_path):
                expect([item["component"] for item in payload["install_items"]] == ["hermes-agent"], str(payload))
                log_path.write_text("Planned: hermes-agent.ref -> target\nAlmanac upgrade complete.\n", encoding="utf-8")
                return subprocess.CompletedProcess(
                    args=["component-upgrade"],
                    returncode=0,
                    stdout="",
                    stderr="",
                )

            verification_calls = []

            def fake_pin_upgrade_canonical_errors(cfg, payload):
                verification_calls.append([item["component"] for item in payload["items"]])
                return []

            provisioner._run_pin_upgrade_action = fake_run_pin_upgrade_action
            provisioner._pin_upgrade_canonical_errors = fake_pin_upgrade_canonical_errors
            provisioner._run_pending_operator_actions(conn, cfg)

            refreshed = conn.execute("SELECT status, log_path FROM operator_actions WHERE id = ?", (int(action_row["id"]),)).fetchone()
            expect(refreshed is not None and refreshed["status"] == "completed", str(dict(refreshed) if refreshed else {}))
            expect(str(refreshed["log_path"] or "").endswith(f"pin-upgrade-{action_row['id']}.log"), str(dict(refreshed)))
            expect(verification_calls == [["hermes-agent", "hermes-docs"]], str(verification_calls))
            remaining = conn.execute("SELECT COUNT(*) FROM pin_upgrade_notifications").fetchone()[0]
            expect(remaining == 0, f"canonical pin success should clear detector rows, found {remaining}")

            operator_rows = conn.execute(
                "SELECT message FROM notification_outbox WHERE target_kind = 'operator' ORDER BY id ASC"
            ).fetchall()
            expect(len(operator_rows) == 2, str([dict(row) for row in operator_rows]))
            expect("Starting pinned-component upgrade" in str(operator_rows[0]["message"] or ""), str([dict(row) for row in operator_rows]))
            expect("completed successfully" in str(operator_rows[1]["message"] or ""), str([dict(row) for row in operator_rows]))
            expect("Canonical pins verified" in str(operator_rows[1]["message"] or ""), str([dict(row) for row in operator_rows]))
            print("PASS test_operator_pin_upgrade_actions_run_component_upgrade_and_notify_operator")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_run_pin_upgrade_action_pins_targets_then_runs_deploy_upgrade() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_pin_upgrade_command_sequence_test")
    provisioner = load_module(PROVISIONER_PY, "almanac_enrollment_provisioner_pin_upgrade_command_sequence_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo_dir = root / "repo"
        (repo_dir / "config").mkdir(parents=True)
        (repo_dir / "bin").mkdir(parents=True)
        pins_path = repo_dir / "config" / "pins.json"
        old_hermes = "aaaaaaaaaaaa1111111111111111111111111111"
        new_hermes = "bbbbbbbbbbbb2222222222222222222222222222"
        new_qmd = "1.2.3"
        pins_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "components": {
                        "hermes-agent": {"kind": "git-commit", "ref": old_hermes},
                        "hermes-docs": {"kind": "git-commit", "ref": old_hermes, "inherits_from": "hermes-agent"},
                        "qmd": {"kind": "npm", "version": "1.0.0"},
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        config_path = root / "config" / "almanac.env"
        values = config_values(root)
        values["ALMANAC_REPO_DIR"] = str(repo_dir)
        write_config(config_path, values)
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            payload = {
                "items": [
                    {"component": "hermes-agent", "kind": "git-commit", "field": "ref", "current": old_hermes, "target": new_hermes},
                    {"component": "hermes-docs", "kind": "git-commit", "field": "ref", "current": old_hermes, "target": new_hermes},
                    {"component": "qmd", "kind": "npm", "field": "version", "current": "1.0.0", "target": new_qmd},
                ],
                "install_items": [
                    {"component": "hermes-agent", "kind": "git-commit", "field": "ref", "current": old_hermes, "target": new_hermes},
                    {"component": "qmd", "kind": "npm", "field": "version", "current": "1.0.0", "target": new_qmd},
                ],
            }
            calls = []

            def fake_run(args, **kwargs):
                argv = list(args)
                calls.append(argv)
                pins = json.loads(pins_path.read_text(encoding="utf-8"))
                if argv[0].endswith("component-upgrade.sh"):
                    component = argv[1]
                    target = argv[4]
                    if component == "hermes-agent":
                        pins["components"]["hermes-agent"]["ref"] = target
                        pins["components"]["hermes-docs"]["ref"] = target
                    elif component == "qmd":
                        pins["components"]["qmd"]["version"] = target
                    else:
                        raise AssertionError(f"unexpected component upgrade call: {argv}")
                    pins_path.write_text(json.dumps(pins) + "\n", encoding="utf-8")
                elif not argv[0].endswith("deploy.sh"):
                    raise AssertionError(f"unexpected subprocess call: {argv}")
                return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

            original_run = provisioner.subprocess.run
            provisioner.subprocess.run = fake_run
            try:
                result = provisioner._run_pin_upgrade_action(cfg, payload, log_path=root / "pin-upgrade.log")
            finally:
                provisioner.subprocess.run = original_run

            expect(result.returncode == 0, str(result))
            expect(
                calls == [
                    [str((repo_dir / "bin" / "component-upgrade.sh").resolve()), "hermes-agent", "apply", "--ref", new_hermes, "--skip-upgrade"],
                    [str((repo_dir / "bin" / "component-upgrade.sh").resolve()), "qmd", "apply", "--version", new_qmd, "--skip-upgrade"],
                    [str((repo_dir / "deploy.sh").resolve()), "upgrade"],
                ],
                str(calls),
            )
            expect(provisioner._pin_upgrade_canonical_errors(cfg, payload) == [], "expected canonical pin verification to pass")
            log_text = (root / "pin-upgrade.log").read_text(encoding="utf-8")
            expect("component-upgrade.sh" in log_text and "deploy.sh' 'upgrade" in log_text, log_text)
            print("PASS test_run_pin_upgrade_action_pins_targets_then_runs_deploy_upgrade")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_operator_upgrade_stale_running_action_fails_closed() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_operator_upgrade_stale_test")
    provisioner = load_module(PROVISIONER_PY, "almanac_enrollment_provisioner_operator_upgrade_stale_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        values = config_values(root)
        values["OPERATOR_NOTIFY_CHANNEL_PLATFORM"] = "telegram"
        values["OPERATOR_NOTIFY_CHANNEL_ID"] = "1000000001"
        write_config(config_path, values)
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            action_row, created = control.request_operator_action(
                conn,
                action_kind="upgrade",
                requested_by="@alex",
                request_source="telegram-button",
                requested_target="bbbbbbbbbbbb2222222222222222222222222222",
            )
            expect(created is True, str(action_row))
            action_id = int(action_row["id"])
            control.mark_operator_action_running(
                conn,
                action_id=action_id,
                note="worker crashed",
                log_path=str(root / "operator-actions" / "upgrade-1.log"),
            )
            conn.execute(
                "UPDATE operator_actions SET started_at = ? WHERE id = ?",
                ("2000-01-01T00:00:00+00:00", action_id),
            )
            conn.commit()

            def fail_if_upgrade_runs(cfg, *, log_path):
                raise AssertionError("stale running upgrade actions must not be rerun automatically")

            provisioner._run_host_upgrade = fail_if_upgrade_runs
            provisioner._run_pending_operator_actions(conn, cfg)

            refreshed = conn.execute("SELECT status, note FROM operator_actions WHERE id = ?", (action_id,)).fetchone()
            expect(refreshed is not None and refreshed["status"] == "failed", str(dict(refreshed) if refreshed else {}))
            expect("stuck in running state" in str(refreshed["note"] or ""), str(dict(refreshed)))
            operator_rows = conn.execute(
                "SELECT message FROM notification_outbox WHERE target_kind = 'operator' ORDER BY id ASC"
            ).fetchall()
            expect(len(operator_rows) == 1, str([dict(row) for row in operator_rows]))
            expect("stuck in running state" in str(operator_rows[0]["message"] or ""), str([dict(row) for row in operator_rows]))
            print("PASS test_operator_upgrade_stale_running_action_fails_closed")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_run_host_upgrade_seeds_home_when_missing() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_run_host_upgrade_home_test")
    provisioner = load_module(PROVISIONER_PY, "almanac_enrollment_provisioner_run_host_upgrade_home_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        os.environ.pop("HOME", None)
        try:
            cfg = control.Config.from_env()
            captured: dict[str, dict[str, str]] = {}

            def fake_subprocess_run(*args, **kwargs):
                captured["env"] = dict(kwargs.get("env") or {})
                captured["cwd"] = str(kwargs.get("cwd") or "")
                return subprocess.CompletedProcess(args=args[0], returncode=0)

            original_run = provisioner.subprocess.run
            provisioner.subprocess.run = fake_subprocess_run
            try:
                provisioner._run_host_upgrade(cfg, log_path=root / "upgrade.log")
            finally:
                provisioner.subprocess.run = original_run

            env = captured.get("env") or {}
            home = env.get("HOME") or ""
            expect(bool(home), f"HOME must be set when subprocess starts: {env}")
            expect(os.path.isabs(home), f"HOME must be absolute: {home!r}")
            print("PASS test_run_host_upgrade_seeds_home_when_missing")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_install_system_services_seeds_home_in_root_units() -> None:
    install_script = REPO / "bin" / "install-system-services.sh"
    text = install_script.read_text(encoding="utf-8")
    for unit_target in (
        '"$TARGET_DIR/almanac-enrollment-provision.service"',
        '"$TARGET_DIR/almanac-notion-claim-poll.service"',
    ):
        opener = f"cat >{unit_target} <<EOF\n"
        start = text.index(opener) + len(opener)
        end = text.index("\nEOF\n", start)
        block = text[start:end]
        expect(
            "Environment=HOME=/root" in block,
            f"{unit_target} unit must seed HOME for root systemd:\n{block}",
        )
    print("PASS test_install_system_services_seeds_home_in_root_units")


def test_install_system_services_does_not_self_deadlock_on_active_oneshots() -> None:
    install_script = REPO / "bin" / "install-system-services.sh"
    text = install_script.read_text(encoding="utf-8")
    expect("start_system_service_if_idle()" in text, text)
    expect("systemctl show -p ActiveState --value" in text, text)
    for state in ("active", "activating", "reloading", "deactivating"):
        expect(state in text, f"missing guarded state {state!r}")
    expect(
        "start_system_service_if_idle almanac-enrollment-provision.service" in text,
        text,
    )
    expect(
        "start_system_service_if_idle almanac-notion-claim-poll.service" in text,
        text,
    )
    expect(
        "systemctl start almanac-enrollment-provision.service >/dev/null 2>&1 || true"
        not in text,
        "enrollment service start must go through the idle guard",
    )
    print("PASS test_install_system_services_does_not_self_deadlock_on_active_oneshots")


def main() -> int:
    test_onboarding_paths_refresh_managed_memory_after_access_surfaces_exist()
    test_onboarding_paths_enter_notion_phase_before_final_completion()
    test_onboarding_notion_verification_poll_is_single_flight()
    test_onboarding_gateway_updates_agent_runtime_model_after_provider_seed()
    test_discord_onboarding_writes_home_channel_env()
    test_discord_completion_handoff_queues_root_dm_action()
    test_retry_contact_force_resends_discord_handoff_after_sent_marker()
    test_completion_bundle_send_is_idempotent()
    test_webhook_verified_claim_finishes_onboarding_and_sends_completion_bundle()
    test_gateway_failures_notify_user_with_provision_error_status()
    test_completed_backup_setup_prompt_backfill_is_idempotent_for_chat_onboarding()
    test_operator_upgrade_actions_run_root_upgrade_and_notify_operator()
    test_operator_pin_upgrade_actions_run_component_upgrade_and_notify_operator()
    test_run_pin_upgrade_action_pins_targets_then_runs_deploy_upgrade()
    test_operator_upgrade_stale_running_action_fails_closed()
    test_run_host_upgrade_seeds_home_when_missing()
    test_install_system_services_seeds_home_in_root_units()
    test_install_system_services_does_not_self_deadlock_on_active_oneshots()
    print("PASS all 18 enrollment provisioner regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
