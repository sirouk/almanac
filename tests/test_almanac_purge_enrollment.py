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
CONTROL_PY = PYTHON_DIR / "almanac_control.py"
CTL_PY = PYTHON_DIR / "almanac_ctl.py"


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
    state_dir = root / "state"
    return {
        "ALMANAC_USER": "almanac",
        "ALMANAC_HOME": str(root / "home-almanac"),
        "ALMANAC_REPO_DIR": str(REPO),
        "ALMANAC_PRIV_DIR": str(root / "priv"),
        "STATE_DIR": str(state_dir),
        "RUNTIME_DIR": str(state_dir / "runtime"),
        "VAULT_DIR": str(root / "vault"),
        "ALMANAC_DB_PATH": str(state_dir / "almanac-control.sqlite3"),
        "ALMANAC_AGENTS_STATE_DIR": str(state_dir / "agents"),
        "ALMANAC_CURATOR_DIR": str(state_dir / "curator"),
        "ALMANAC_CURATOR_MANIFEST": str(state_dir / "curator" / "manifest.json"),
        "ALMANAC_CURATOR_HERMES_HOME": str(state_dir / "curator" / "hermes-home"),
        "ALMANAC_ARCHIVED_AGENTS_DIR": str(state_dir / "archived-agents"),
        "ALMANAC_RELEASE_STATE_FILE": str(state_dir / "almanac-release.json"),
        "ALMANAC_QMD_URL": "http://127.0.0.1:8181/mcp",
        "ALMANAC_MCP_HOST": "127.0.0.1",
        "ALMANAC_MCP_PORT": "8282",
        "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "telegram",
        "OPERATOR_NOTIFY_CHANNEL_ID": "1000000001",
        "ENABLE_NEXTCLOUD": "1",
        "ALMANAC_NAME": "almanac",
    }


def test_user_purge_enrollment_removes_completed_state_and_files() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_purge_enrollment_test")
    ctl = load_module(CTL_PY, "almanac_ctl_purge_enrollment_test")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            now = control.utc_now_iso()
            agent_id = "agent-alex"
            session_id = "onb_test123"
            request_id = "req_test123"
            token_id = "tok_test123"
            hermes_home = root / "home-alex" / ".local" / "share" / "almanac-agent" / "hermes-home"
            access_state_path = hermes_home / "state" / "almanac-web-access.json"
            access_state_path.parent.mkdir(parents=True, exist_ok=True)
            access_state_path.write_text(
                json.dumps(
                    {
                        "agent_id": agent_id,
                        "code_container_name": "almanac-agent-code-agent-alex",
                        "dashboard_proxy_port": 30011,
                        "code_port": 40011,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            manifest_path = cfg.agents_state_dir / agent_id / "manifest.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text("manifest\n", encoding="utf-8")
            activation_path = cfg.state_dir / "activation-triggers" / f"{agent_id}.json"
            activation_path.parent.mkdir(parents=True, exist_ok=True)
            activation_path.write_text("{}\n", encoding="utf-8")
            archive_root = cfg.archived_agents_dir / agent_id / "20260420T000000Z"
            archive_root.mkdir(parents=True, exist_ok=True)
            (archive_root / "placeholder.txt").write_text("archive\n", encoding="utf-8")
            onboarding_secret_dir = cfg.state_dir / "onboarding-secrets" / session_id
            onboarding_secret_dir.mkdir(parents=True, exist_ok=True)
            (onboarding_secret_dir / "secret.txt").write_text("secret\n", encoding="utf-8")
            auto_provision_log = cfg.state_dir / "auto-provision" / f"{request_id}.log"
            auto_provision_log.parent.mkdir(parents=True, exist_ok=True)
            auto_provision_log.write_text("log\n", encoding="utf-8")
            repo_checkout = cfg.state_dir / "repo-sync" / "checkouts" / "alex-almanac"
            repo_checkout.mkdir(parents=True, exist_ok=True)
            (repo_checkout / "README.md").write_text("repo\n", encoding="utf-8")
            repo_mirror = cfg.vault_dir / "Repos" / "_mirrors" / "alex-almanac"
            repo_mirror.mkdir(parents=True, exist_ok=True)
            (repo_mirror / "README.md").write_text("mirror\n", encoding="utf-8")
            nextcloud_data = cfg.state_dir / "nextcloud" / "data" / "alex"
            nextcloud_data.mkdir(parents=True, exist_ok=True)
            (nextcloud_data / "file.txt").write_text("data\n", encoding="utf-8")
            nextcloud_html_data = cfg.state_dir / "nextcloud" / "html" / "data" / "alex"
            nextcloud_html_data.mkdir(parents=True, exist_ok=True)
            (nextcloud_html_data / "file.txt").write_text("html\n", encoding="utf-8")

            conn.execute(
                """
                INSERT INTO agents (
                  agent_id, role, unix_user, display_name, status, hermes_home, manifest_path,
                  archived_state_path, model_preset, model_string, channels_json,
                  allowed_mcps_json, home_channel_json, operator_notify_channel_json,
                  notes, created_at, last_enrolled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    "user",
                    "alex",
                    "Alex",
                    "active",
                    str(hermes_home),
                    str(manifest_path),
                    str(archive_root),
                    "codex",
                    "openai:codex",
                    json.dumps(["tui-only", "discord"]),
                    json.dumps([]),
                    json.dumps({"platform": "discord", "channel_id": "547966246486802432"}),
                    json.dumps({"platform": "telegram", "channel_id": "1000000001"}),
                    "",
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO agent_vault_subscriptions (agent_id, vault_name, subscribed, source, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (agent_id, "Research", 1, "default", now),
            )
            conn.execute(
                """
                INSERT INTO onboarding_sessions (
                  session_id, platform, chat_id, sender_id, sender_username, sender_display_name,
                  state, answers_json, linked_request_id, linked_agent_id, completed_at,
                  created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    "discord",
                    "547966246486802432",
                    "547966246486802432",
                    "alex",
                    "Alex",
                    "completed",
                    json.dumps({"unix_user": "alex", "bot_platform": "discord"}),
                    request_id,
                    agent_id,
                    now,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO bootstrap_requests (
                  request_id, requester_identity, unix_user, source_ip, requested_at, expires_at,
                  status, prior_agent_id, auto_provision, provisioned_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    "Alex",
                    "alex",
                    "100.120.112.116",
                    now,
                    now,
                    "approved",
                    agent_id,
                    1,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO bootstrap_tokens (
                  token_id, agent_id, token_hash, requester_identity, source_ip,
                  issued_at, issued_by, activation_request_id, activated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token_id,
                    agent_id,
                    "hashed-token",
                    "Alex",
                    "100.120.112.116",
                    now,
                    "test",
                    request_id,
                    now,
                ),
            )
            control.upsert_agent_identity(
                conn,
                agent_id=agent_id,
                unix_user="alex",
                human_display_name="Alex",
                claimed_notion_email="alex@example.com",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=now,
                verification_source="test",
            )
            conn.execute(
                """
                INSERT INTO notion_identity_claims (
                  claim_id, session_id, agent_id, unix_user, claimed_notion_email,
                  notion_page_id, notion_page_url, status, failure_reason,
                  verified_notion_user_id, verified_notion_email, created_at,
                  updated_at, expires_at, verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "claim_test123",
                    session_id,
                    agent_id,
                    "alex",
                    "alex@example.com",
                    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "https://www.notion.so/alex-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "verified",
                    "",
                    "11111111-1111-1111-1111-111111111111",
                    "alex@example.com",
                    now,
                    now,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO notion_identity_overrides (
                  unix_user, agent_id, notion_user_id, notion_user_email, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "alex",
                    agent_id,
                    "22222222-2222-2222-2222-222222222222",
                    "alex.alias@example.com",
                    "test override",
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO ssot_pending_writes (
                  pending_id, agent_id, unix_user, notion_user_id, operation, target_id,
                  payload_json, requested_by_actor, request_source, request_reason,
                  owner_identity, owner_source, status, requested_at, expires_at,
                  decision_surface, decided_by_actor, decided_at, decision_note,
                  applied_at, apply_result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "pw_test123",
                    agent_id,
                    "alex",
                    "11111111-1111-1111-1111-111111111111",
                    "update",
                    "page_123",
                    "{}",
                    "agent-alex",
                    "test",
                    "",
                    "alex@example.com",
                    "test",
                    "pending",
                    now,
                    now,
                    "",
                    "",
                    None,
                    "",
                    None,
                    "{}",
                ),
            )
            conn.execute(
                """
                INSERT INTO notification_outbox (
                  target_kind, target_id, channel_kind, message, extra_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "user-agent",
                    agent_id,
                    "discord",
                    "Lane ready for agent-alex",
                    json.dumps({}),
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO notification_outbox (
                  target_kind, target_id, channel_kind, message, extra_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "operator",
                    "1000000001",
                    "telegram",
                    f"Onboarding complete for {agent_id} from {request_id}",
                    json.dumps({"request_id": request_id, "session_id": session_id}),
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO refresh_jobs (job_name, job_kind, target_id, schedule, last_run_at, last_status, last_note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (f"{agent_id}-refresh", "agent-refresh", agent_id, "manual", now, "ok", ""),
            )
            conn.execute(
                """
                INSERT INTO refresh_jobs (job_name, job_kind, target_id, schedule, last_run_at, last_status, last_note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (f"onboarding-{session_id}", "onboarding", agent_id, "manual", now, "ok", session_id),
            )
            conn.execute(
                """
                INSERT INTO refresh_jobs (job_name, job_kind, target_id, schedule, last_run_at, last_status, last_note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (f"auto-provision-{request_id}", "auto-provision", agent_id, "manual", now, "ok", request_id),
            )
            conn.execute(
                "INSERT INTO rate_limits (scope, subject, observed_at) VALUES (?, ?, ?)",
                ("onboarding-user", "discord:547966246486802432", now),
            )
            conn.execute(
                "INSERT INTO rate_limits (scope, subject, observed_at) VALUES (?, ?, ?)",
                ("ip", "100.120.112.116", now),
            )
            conn.execute(
                "INSERT INTO rate_limits (scope, subject, observed_at) VALUES (?, ?, ?)",
                ("onboarding-user", "discord:extra-subject", now),
            )
            conn.commit()

            cleared_tailscale: list[str] = []
            nextcloud_deletes: list[str] = []
            ctl.os.geteuid = lambda: 0
            ctl.clear_tailscale_https = lambda home: cleared_tailscale.append(str(home))
            ctl.delete_nextcloud_user_access = (
                lambda cfg_arg, username: nextcloud_deletes.append(username)
                or {"enabled": True, "deleted": True, "exists": True, "username": username}
            )

            result = ctl.user_purge_enrollment(
                cfg,
                "alex",
                actor="test",
                remove_unix_user=False,
                remove_archives=True,
                purge_rate_limits=True,
                extra_rate_limit_subjects=["discord:extra-subject"],
                remove_nextcloud_user=True,
            )

            expect(result["agent_ids"] == [agent_id], str(result))
            expect(result["session_ids"] == [session_id], str(result))
            expect(result["request_ids"] == [request_id], str(result))
            expect(result["token_ids"] == [token_id], str(result))
            expect("100.120.112.116" in result["rate_limit_subjects"], str(result))
            expect(cleared_tailscale == [str(hermes_home)], str(cleared_tailscale))
            expect(nextcloud_deletes == ["alex"], str(nextcloud_deletes))

            expect(not hermes_home.exists(), f"expected {hermes_home} to be removed")
            expect(not manifest_path.exists(), f"expected {manifest_path} to be removed")
            expect(not activation_path.exists(), f"expected {activation_path} to be removed")
            expect(not onboarding_secret_dir.exists(), f"expected {onboarding_secret_dir} to be removed")
            expect(not auto_provision_log.exists(), f"expected {auto_provision_log} to be removed")
            expect(not repo_checkout.exists(), f"expected {repo_checkout} to be removed")
            expect(not repo_mirror.exists(), f"expected {repo_mirror} to be removed")
            expect(not archive_root.parent.exists(), f"expected {archive_root.parent} to be removed")
            expect(not nextcloud_data.exists(), f"expected {nextcloud_data} to be removed")
            expect(not nextcloud_html_data.exists(), f"expected {nextcloud_html_data} to be removed")

            expect(conn.execute("SELECT COUNT(*) AS count FROM agents").fetchone()["count"] == 0, "agents should be empty")
            expect(
                conn.execute("SELECT COUNT(*) AS count FROM onboarding_sessions").fetchone()["count"] == 0,
                "onboarding_sessions should be empty",
            )
            expect(
                conn.execute("SELECT COUNT(*) AS count FROM bootstrap_requests").fetchone()["count"] == 0,
                "bootstrap_requests should be empty",
            )
            expect(
                conn.execute("SELECT COUNT(*) AS count FROM bootstrap_tokens").fetchone()["count"] == 0,
                "bootstrap_tokens should be empty",
            )
            expect(
                conn.execute("SELECT COUNT(*) AS count FROM notification_outbox").fetchone()["count"] == 0,
                "notification_outbox should be empty",
            )
            expect(
                conn.execute("SELECT COUNT(*) AS count FROM refresh_jobs").fetchone()["count"] == 0,
                "refresh_jobs should be empty",
            )
            expect(
                conn.execute("SELECT COUNT(*) AS count FROM agent_vault_subscriptions").fetchone()["count"] == 0,
                "agent_vault_subscriptions should be empty",
            )
            expect(
                conn.execute("SELECT COUNT(*) AS count FROM agent_identity").fetchone()["count"] == 0,
                "agent_identity should be empty",
            )
            expect(
                conn.execute("SELECT COUNT(*) AS count FROM notion_identity_claims").fetchone()["count"] == 0,
                "notion_identity_claims should be empty",
            )
            expect(
                conn.execute("SELECT COUNT(*) AS count FROM notion_identity_overrides").fetchone()["count"] == 0,
                "notion_identity_overrides should be empty",
            )
            expect(
                conn.execute("SELECT COUNT(*) AS count FROM ssot_pending_writes").fetchone()["count"] == 0,
                "ssot_pending_writes should be empty",
            )
            expect(
                conn.execute("SELECT COUNT(*) AS count FROM rate_limits").fetchone()["count"] == 0,
                "rate_limits should be empty for the matched subjects",
            )
            print("PASS test_user_purge_enrollment_removes_completed_state_and_files")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_connect_db_repairs_legacy_notification_outbox_before_creating_retry_index() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_legacy_notification_outbox_repair_test")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = control.sqlite3.connect(cfg.db_path)
            conn.execute(
                """
                CREATE TABLE notification_outbox (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  target_kind TEXT NOT NULL,
                  target_id TEXT NOT NULL,
                  channel_kind TEXT NOT NULL,
                  message TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  delivered_at TEXT,
                  delivery_error TEXT
                )
                """
            )
            conn.commit()
            conn.close()

            conn = control.connect_db(cfg)
            try:
                columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(notification_outbox)").fetchall()}
                expect("next_attempt_at" in columns, str(sorted(columns)))
                index_names = {str(row["name"]) for row in conn.execute("PRAGMA index_list(notification_outbox)").fetchall()}
                expect(
                    "idx_notification_outbox_pending_target_channel_next_attempt" in index_names,
                    str(sorted(index_names)),
                )
            finally:
                conn.close()

            print("PASS test_connect_db_repairs_legacy_notification_outbox_before_creating_retry_index")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_connect_db_repairs_legacy_ssot_pending_writes_before_creating_expiry_index() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_legacy_ssot_pending_writes_repair_test")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = control.sqlite3.connect(cfg.db_path)
            conn.execute(
                """
                CREATE TABLE ssot_pending_writes (
                  pending_id TEXT PRIMARY KEY,
                  agent_id TEXT NOT NULL,
                  unix_user TEXT NOT NULL,
                  notion_user_id TEXT NOT NULL DEFAULT '',
                  operation TEXT NOT NULL,
                  target_id TEXT NOT NULL,
                  payload_json TEXT NOT NULL DEFAULT '{}',
                  requested_by_actor TEXT NOT NULL DEFAULT '',
                  request_source TEXT NOT NULL DEFAULT '',
                  request_reason TEXT NOT NULL DEFAULT '',
                  owner_identity TEXT NOT NULL DEFAULT '',
                  owner_source TEXT NOT NULL DEFAULT '',
                  status TEXT NOT NULL DEFAULT 'pending',
                  requested_at TEXT NOT NULL,
                  decision_surface TEXT NOT NULL DEFAULT '',
                  decided_by_actor TEXT NOT NULL DEFAULT '',
                  decided_at TEXT,
                  decision_note TEXT NOT NULL DEFAULT '',
                  applied_at TEXT,
                  apply_result_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                INSERT INTO ssot_pending_writes (
                  pending_id, agent_id, unix_user, notion_user_id, operation, target_id,
                  payload_json, requested_by_actor, request_source, request_reason,
                  owner_identity, owner_source, status, requested_at, decision_surface,
                  decided_by_actor, decided_at, decision_note, applied_at, apply_result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "pw_legacy",
                    "agent-alex",
                    "alex",
                    "",
                    "create-page",
                    "page_123",
                    "{}",
                    "operator",
                    "test",
                    "",
                    "alex",
                    "test",
                    "pending",
                    "2026-04-21T00:00:00+00:00",
                    "",
                    "",
                    None,
                    "",
                    None,
                    "{}",
                ),
            )
            conn.commit()
            conn.close()

            conn = control.connect_db(cfg)
            try:
                columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(ssot_pending_writes)").fetchall()}
                expect("expires_at" in columns, str(sorted(columns)))
                index_names = {str(row["name"]) for row in conn.execute("PRAGMA index_list(ssot_pending_writes)").fetchall()}
                expect("idx_ssot_pending_writes_status_expires" in index_names, str(sorted(index_names)))
                row = conn.execute(
                    "SELECT expires_at FROM ssot_pending_writes WHERE pending_id = ?",
                    ("pw_legacy",),
                ).fetchone()
                expect(str(row["expires_at"] or "").strip() != "", str(dict(row)))
            finally:
                conn.close()

            print("PASS test_connect_db_repairs_legacy_ssot_pending_writes_before_creating_expiry_index")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_user_purge_enrollment_removes_completed_state_and_files()
    test_connect_db_repairs_legacy_notification_outbox_before_creating_retry_index()
    test_connect_db_repairs_legacy_ssot_pending_writes_before_creating_expiry_index()
    print("PASS all 3 purge-enrollment regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
