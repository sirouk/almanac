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
        "ALMANAC_MODEL_PRESET_CHUTES": "chutes:auto-failover",
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
            "Chris",
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
                sender_username="sirouk",
                sender_display_name="Chris",
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
            insert_agent(control, conn, agent_id="agent-sirouk", unix_user="sirouk")
            control.upsert_agent_identity(
                conn,
                agent_id="agent-sirouk",
                unix_user="sirouk",
                human_display_name="Chris",
                verification_status="unverified",
                write_mode="read_only",
            )
            session = control.start_onboarding_session(
                conn,
                cfg,
                platform="telegram",
                chat_id="123456",
                sender_id="123456",
                sender_username="sirouk",
                sender_display_name="Chris",
            )
            session = control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-notion-verification",
                linked_agent_id="agent-sirouk",
                answers={
                    "unix_user": "sirouk",
                    "bot_platform": "telegram",
                    "bot_username": "Jeef",
                    "preferred_bot_name": "Jeef",
                    "full_name": "Chris",
                    "notion_claim_id": "nclaim_complete",
                    "notion_claim_email": "chris@example.com",
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
                    "agent-sirouk",
                    "sirouk",
                    "chris@example.com",
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
            provisioner._notify_user_via_curator = (
                lambda cfg, *, session, message, telegram_reply_markup=None, discord_components=None: deliveries.append(
                    {
                        "message": message,
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
                    "person": {"email": "chris@example.com"},
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
            expect(str(answers.get("notion_verified_email") or "") == "chris@example.com", str(answers))
            identity = control.get_agent_identity(conn, agent_id="agent-sirouk", unix_user="sirouk")
            expect(identity is not None and identity["verification_status"] == "verified", str(identity))
            expect(refresh_calls == [("identity", "sirouk"), ("memory", "agent-sirouk")], str(refresh_calls))
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
                sender_username="sirouk",
                sender_display_name="Chris",
            )
            session = control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="provision-pending",
                linked_agent_id="agent-sirouk",
                answers={
                    "bot_platform": "telegram",
                    "bot_username": "Jeef",
                    "preferred_bot_name": "Jeef",
                    "unix_user": "sirouk",
                },
            )
            provisioner.list_pending_onboarding_bot_configurations = lambda conn: [control.get_onboarding_session(conn, str(session["session_id"]), redact_secrets=False)]
            provisioner._migrate_legacy_onboarding_session = lambda conn, cfg, session: session
            provisioner._configure_user_telegram_gateway = lambda conn, cfg, session: (_ for _ in ()).throw(RuntimeError("gateway startup failed"))
            notifications: list[str] = []
            provisioner._notify_user_via_curator = lambda cfg, *, session, message, telegram_reply_markup=None, discord_components=None: notifications.append(message) or {"message_id": "1"}

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
        values["OPERATOR_NOTIFY_CHANNEL_ID"] = "1994645819"
        write_config(config_path, values)
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            action_row, created = control.request_operator_action(
                conn,
                action_kind="upgrade",
                requested_by="@sirouk",
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


def main() -> int:
    test_onboarding_paths_refresh_managed_memory_after_access_surfaces_exist()
    test_onboarding_paths_enter_notion_phase_before_final_completion()
    test_completion_bundle_send_is_idempotent()
    test_webhook_verified_claim_finishes_onboarding_and_sends_completion_bundle()
    test_gateway_failures_notify_user_with_provision_error_status()
    test_operator_upgrade_actions_run_root_upgrade_and_notify_operator()
    print("PASS all 6 enrollment provisioner regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
