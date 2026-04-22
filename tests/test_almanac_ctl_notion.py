#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CTL_PY = REPO / "python" / "almanac_ctl.py"
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
        "ALMANAC_SSOT_NOTION_ROOT_PAGE_URL": "https://www.notion.so/The-Almanac-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
        "ALMANAC_SSOT_NOTION_ROOT_PAGE_ID": "aaaaaaaa-aaaa-bbbb-bbbb-bbbbbbbbbbbb",
        "ALMANAC_SSOT_NOTION_SPACE_URL": "https://www.notion.so/Acme-SSOT-1234567890abcdef1234567890abcdef",
        "ALMANAC_SSOT_NOTION_SPACE_ID": "12345678-90ab-cdef-1234-567890abcdef",
        "ALMANAC_SSOT_NOTION_SPACE_KIND": "database",
        "ALMANAC_SSOT_NOTION_TOKEN": "secret_test",
        "ALMANAC_SSOT_NOTION_API_VERSION": "2026-03-11",
        "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "tui-only",
        "OPERATOR_NOTIFY_CHANNEL_ID": "",
        "ALMANAC_MODEL_PRESET_CODEX": "openai:codex",
        "ALMANAC_MODEL_PRESET_OPUS": "anthropic:claude-opus",
        "ALMANAC_MODEL_PRESET_CHUTES": "chutes:auto-failover",
        "ALMANAC_CURATOR_CHANNELS": "tui-only",
        "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "0",
        "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED": "0",
    }


def insert_agent(mod, conn, *, agent_id: str, unix_user: str, display_name: str = "Chris") -> None:
    now = mod.utc_now_iso()
    conn.execute(
        """
        INSERT INTO agents (
          agent_id, role, unix_user, display_name, status, hermes_home, manifest_path,
          archived_state_path, model_preset, model_string, channels_json,
          allowed_mcps_json, home_channel_json, operator_notify_channel_json,
          notes, created_at, last_enrolled_at
        ) VALUES (?, 'user', ?, ?, 'active', ?, ?, NULL, 'codex', 'openai:codex', '["tui-only"]', '[]', '{}', '{}', '', ?, ?)
        """,
        (
            agent_id,
            unix_user,
            display_name,
            str(Path("/home") / unix_user / ".local" / "share" / "almanac-agent" / "hermes-home"),
            str(Path("/tmp") / f"{agent_id}-manifest.json"),
            now,
            now,
        ),
    )
    conn.commit()


def test_redact_identity_rows_masks_emails_by_default() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    ctl = load_module(CTL_PY, "almanac_ctl_notion_redact_test")
    rows = [
        {
            "unix_user": "sirouk",
            "claimed_notion_email": "chris@example.com",
            "notion_user_email": "owner@example.com",
            "notion_user_id": "11111111-1111-1111-1111-111111111111",
        }
    ]
    scrubbed = ctl._redact_identity_rows(rows, show_sensitive=False)
    expect(scrubbed[0]["claimed_notion_email"] == "c***@example.com", str(scrubbed))
    expect(scrubbed[0]["notion_user_email"] == "o***@example.com", str(scrubbed))
    expect(scrubbed[0]["notion_user_id"] == "[redacted]", str(scrubbed))
    shown = ctl._redact_identity_rows(rows, show_sensitive=True)
    expect(shown[0]["claimed_notion_email"] == "chris@example.com", str(shown))
    expect(shown[0]["notion_user_email"] == "owner@example.com", str(shown))
    expect(shown[0]["notion_user_id"] == "11111111-1111-1111-1111-111111111111", str(shown))
    print("PASS test_redact_identity_rows_masks_emails_by_default")


def test_manual_verify_notion_user_fetches_and_validates_email() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    ctl = load_module(CTL_PY, "almanac_ctl_notion_verify_test")
    original_config_env_value = ctl.config_env_value
    original_retrieve_notion_user = ctl.retrieve_notion_user
    try:
        ctl.config_env_value = lambda key, default="": {
            "ALMANAC_SSOT_NOTION_TOKEN": "secret_test",
            "ALMANAC_SSOT_NOTION_API_VERSION": "2026-03-11",
        }.get(key, default)
        ctl.retrieve_notion_user = lambda **kwargs: {
            "id": "11111111-1111-1111-1111-111111111111",
            "type": "person",
            "person": {"email": "chris@example.com"},
        }
        notion_user_id, notion_user_email = ctl._manual_verify_notion_user(
            "11111111-1111-1111-1111-111111111111",
            expected_email="chris@example.com",
        )
        expect(notion_user_id == "11111111-1111-1111-1111-111111111111", notion_user_id)
        expect(notion_user_email == "chris@example.com", notion_user_email)
        try:
            ctl._manual_verify_notion_user(
                "11111111-1111-1111-1111-111111111111",
                expected_email="other@example.com",
            )
        except SystemExit as exc:
            expect("mismatch" in str(exc).lower(), str(exc))
        else:
            raise AssertionError("expected email mismatch to abort manual verification")
        print("PASS test_manual_verify_notion_user_fetches_and_validates_email")
    finally:
        ctl.config_env_value = original_config_env_value
        ctl.retrieve_notion_user = original_retrieve_notion_user


def test_suspended_identity_cannot_be_reverified_without_unsuspend() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_identity_transition_test")
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
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="chris@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=control.utc_now_iso(),
            )
            control.suspend_agent_identity(conn, unix_user="sirouk")
            try:
                control.mark_agent_identity_verified(
                    conn,
                    unix_user="sirouk",
                    notion_user_id="11111111-1111-1111-1111-111111111111",
                    notion_user_email="chris@example.com",
                    verification_source="notion-live-check:chris@example.com",
                )
            except ValueError as exc:
                expect("suspended" in str(exc).lower(), str(exc))
            else:
                raise AssertionError("expected suspended identity reverify to be blocked")
            control.unsuspend_agent_identity(conn, unix_user="sirouk")
            refreshed = control.mark_agent_identity_verified(
                conn,
                unix_user="sirouk",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="chris@example.com",
                verification_source="notion-live-check:chris@example.com",
            )
            expect(refreshed["suspended_at"] == "", str(refreshed))
            expect(refreshed["verification_source"] == "notion-live-check:chris@example.com", str(refreshed))
            print("PASS test_suspended_identity_cannot_be_reverified_without_unsuspend")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_notion_suspend_and_unsuspend_cli_audit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        control = load_module(CONTROL_PY, "almanac_control_ctl_suspend_test")
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
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="chris@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=control.utc_now_iso(),
            )
        finally:
            os.environ.clear()
            os.environ.update(old_env)

        env = {
            **os.environ,
            "ALMANAC_CONFIG_FILE": str(config_path),
            "PYTHONPATH": str(PYTHON_DIR),
        }
        suspended = subprocess.run(
            [sys.executable, str(CTL_PY), "--json", "notion", "suspend", "sirouk", "--actor", "operator", "--reason", "test suspend"],
            cwd=str(REPO),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        expect(suspended.returncode == 0, suspended.stderr or suspended.stdout)
        unsuspended = subprocess.run(
            [sys.executable, str(CTL_PY), "--json", "notion", "unsuspend", "sirouk", "--actor", "operator", "--reason", "test unsuspend"],
            cwd=str(REPO),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        expect(unsuspended.returncode == 0, unsuspended.stderr or unsuspended.stdout)

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            identity = control.get_agent_identity(conn, unix_user="sirouk")
            expect(identity is not None, "expected identity row after suspend/unsuspend")
            expect(identity["suspended_at"] in {"", None}, str(identity))
            audit_rows = control.list_ssot_access_audit(conn, unix_user="sirouk", limit=5)
            operations = [row["operation"] for row in audit_rows]
            expect("suspend" in operations, str(audit_rows))
            expect("unsuspend" in operations, str(audit_rows))
            print("PASS test_notion_suspend_and_unsuspend_cli_audit")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_connect_db_migrates_legacy_notion_claim_nonce_column() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_notion_claim_migration_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        db_path = root / "state" / "almanac-control.sqlite3"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            raw = control.sqlite3.connect(db_path)
            raw.executescript(
                """
                CREATE TABLE notion_identity_claims (
                  claim_id TEXT PRIMARY KEY,
                  session_id TEXT NOT NULL DEFAULT '',
                  agent_id TEXT NOT NULL,
                  unix_user TEXT NOT NULL,
                  claimed_notion_email TEXT NOT NULL,
                  notion_page_id TEXT NOT NULL DEFAULT '',
                  notion_page_url TEXT NOT NULL DEFAULT '',
                  verification_nonce TEXT NOT NULL DEFAULT '',
                  status TEXT NOT NULL DEFAULT 'pending',
                  failure_reason TEXT NOT NULL DEFAULT '',
                  verified_notion_user_id TEXT NOT NULL DEFAULT '',
                  verified_notion_email TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  expires_at TEXT NOT NULL,
                  verified_at TEXT
                );
                INSERT INTO notion_identity_claims (
                  claim_id, session_id, agent_id, unix_user, claimed_notion_email,
                  notion_page_id, notion_page_url, verification_nonce, status, failure_reason,
                  verified_notion_user_id, verified_notion_email, created_at, updated_at, expires_at, verified_at
                ) VALUES (
                  'nclaim_old', 'session-1', 'agent-sirouk', 'sirouk', 'chris@example.com',
                  'page-1', 'https://www.notion.so/claim', 'legacy-nonce', 'pending', '',
                  '', '', '2026-04-20T00:00:00+00:00', '2026-04-20T00:00:00+00:00', '2026-04-21T00:00:00+00:00', NULL
                );
                """
            )
            raw.commit()
            raw.close()

            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(notion_identity_claims)").fetchall()}
            expect("verification_nonce" not in columns, str(columns))
            row = conn.execute(
                "SELECT claim_id, claimed_notion_email FROM notion_identity_claims WHERE claim_id = 'nclaim_old'"
            ).fetchone()
            expect(row is not None and row["claimed_notion_email"] == "chris@example.com", str(dict(row) if row else {}))
            print("PASS test_connect_db_migrates_legacy_notion_claim_nonce_column")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_expire_stale_notion_identity_claims_marks_pending_claims_expired() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_expire_claims_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            conn.execute(
                """
                INSERT INTO notion_identity_claims (
                  claim_id, session_id, agent_id, unix_user, claimed_notion_email,
                  notion_page_id, notion_page_url, status, failure_reason,
                  verified_notion_user_id, verified_notion_email, created_at, updated_at, expires_at, verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', '', '', '', ?, ?, ?, NULL)
                """,
                (
                    "nclaim_expire_me",
                    "session-1",
                    "agent-sirouk",
                    "sirouk",
                    "chris@example.com",
                    "page-1",
                    "https://www.notion.so/claim",
                    "2026-04-20T00:00:00+00:00",
                    "2026-04-20T00:00:00+00:00",
                    "2000-01-01T00:00:00+00:00",
                ),
            )
            conn.commit()
            expired = control.expire_stale_notion_identity_claims(conn)
            expect(expired == 1, str(expired))
            claim = control.get_notion_identity_claim(conn, claim_id="nclaim_expire_me")
            expect(claim is not None and claim["status"] == "expired", str(claim))
            expect("expired" in str(claim.get("failure_reason") or "").lower(), str(claim))
            print("PASS test_expire_stale_notion_identity_claims_marks_pending_claims_expired")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_notion_override_cli_round_trip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        control = load_module(CONTROL_PY, "almanac_control_ctl_override_test")
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            insert_agent(control, conn, agent_id="agent-sirouk", unix_user="sirouk")
        finally:
            os.environ.clear()
            os.environ.update(old_env)

        env = {
            **os.environ,
            "ALMANAC_CONFIG_FILE": str(config_path),
            "PYTHONPATH": str(PYTHON_DIR),
        }
        set_result = subprocess.run(
            [
                sys.executable,
                str(CTL_PY),
                "--json",
                "notion",
                "override-set",
                "sirouk",
                "11111111-1111-1111-1111-111111111111",
                "--email",
                "chris@example.com",
                "--notes",
                "seeded from test",
            ],
            cwd=str(REPO),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        expect(set_result.returncode == 0, set_result.stderr or set_result.stdout)
        set_payload = json.loads(set_result.stdout)
        expect(set_payload["notion_user_email"] == "c***@example.com", str(set_payload))
        expect(set_payload["notion_user_id"] == "[redacted]", str(set_payload))

        list_default = subprocess.run(
            [sys.executable, str(CTL_PY), "--json", "notion", "override-list"],
            cwd=str(REPO),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        expect(list_default.returncode == 0, list_default.stderr or list_default.stdout)
        listed = json.loads(list_default.stdout)
        expect(len(listed["overrides"]) == 1, str(listed))
        expect(listed["overrides"][0]["notion_user_email"] == "c***@example.com", str(listed))

        list_sensitive = subprocess.run(
            [sys.executable, str(CTL_PY), "--json", "notion", "override-list", "--show-sensitive"],
            cwd=str(REPO),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        expect(list_sensitive.returncode == 0, list_sensitive.stderr or list_sensitive.stdout)
        sensitive = json.loads(list_sensitive.stdout)
        expect(sensitive["overrides"][0]["notion_user_email"] == "chris@example.com", str(sensitive))
        expect(
            sensitive["overrides"][0]["notion_user_id"] == "11111111-1111-1111-1111-111111111111",
            str(sensitive),
        )

        clear_result = subprocess.run(
            [sys.executable, str(CTL_PY), "--json", "notion", "override-clear", "sirouk"],
            cwd=str(REPO),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        expect(clear_result.returncode == 0, clear_result.stderr or clear_result.stdout)
        cleared = json.loads(clear_result.stdout)
        expect(cleared["cleared"] is True, str(cleared))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            audit_rows = control.list_ssot_access_audit(conn, unix_user="sirouk", limit=5)
            operations = [row["operation"] for row in audit_rows]
            expect("override-identity" in operations, str(audit_rows))
            expect("override-identity-clear" in operations, str(audit_rows))
        finally:
            os.environ.clear()
            os.environ.update(old_env)
        print("PASS test_notion_override_cli_round_trip")


def test_notion_preflight_root_cli_uses_root_page_id() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    ctl = load_module(CTL_PY, "almanac_ctl_notion_preflight_test")
    original_preflight = ctl.preflight_notion_root_children
    original_argv = sys.argv[:]
    old_env = os.environ.copy()
    buffer = io.StringIO()
    calls: list[dict[str, str]] = []
    try:
        os.environ["ALMANAC_SSOT_NOTION_ROOT_PAGE_ID"] = "aaaaaaaa-aaaa-bbbb-bbbb-bbbbbbbbbbbb"
        os.environ["ALMANAC_SSOT_NOTION_TOKEN"] = "secret_test"
        os.environ["ALMANAC_SSOT_NOTION_API_VERSION"] = "2026-03-11"

        def fake_preflight(*, root_page_id: str, token: str, api_version: str, urlopen_fn=None):
            calls.append(
                {
                    "root_page_id": root_page_id,
                    "token": token,
                    "api_version": api_version,
                }
            )
            return {"ok": True, "root_page_id": root_page_id}

        ctl.preflight_notion_root_children = fake_preflight
        sys.argv = [str(CTL_PY), "--json", "notion", "preflight-root"]
        with contextlib.redirect_stdout(buffer):
            ctl.main()
    finally:
        ctl.preflight_notion_root_children = original_preflight
        sys.argv = original_argv
        os.environ.clear()
        os.environ.update(old_env)
    expect(
        calls == [
            {
                "root_page_id": "aaaaaaaa-aaaa-bbbb-bbbb-bbbbbbbbbbbb",
                "token": "secret_test",
                "api_version": "2026-03-11",
            }
        ],
        str(calls),
    )
    payload = json.loads(buffer.getvalue())
    expect(payload["root_page_id"] == "aaaaaaaa-aaaa-bbbb-bbbb-bbbbbbbbbbbb", str(payload))
    print("PASS test_notion_preflight_root_cli_uses_root_page_id")


def test_notion_webhook_cli_requires_force_and_tracks_arm_window() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        values = config_values(root)
        values["ALMANAC_NOTION_WEBHOOK_PUBLIC_URL"] = "https://hooks.example.com/notion/webhook"
        write_config(config_path, values)
        env = {
            **os.environ,
            "ALMANAC_CONFIG_FILE": str(config_path),
            "PYTHONPATH": str(PYTHON_DIR),
        }

        arm = subprocess.run(
            [
                sys.executable,
                str(CTL_PY),
                "--json",
                "notion",
                "webhook-arm-install",
                "--actor",
                "operator",
                "--minutes",
                "12",
            ],
            cwd=str(REPO),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        expect(arm.returncode == 0, arm.stderr or arm.stdout)
        armed_payload = json.loads(arm.stdout)
        expect(armed_payload["armed"] is True, str(armed_payload))
        expect(bool(armed_payload["armed_until"]), str(armed_payload))

        denied = subprocess.run(
            [
                sys.executable,
                str(CTL_PY),
                "--json",
                "notion",
                "webhook-reset-token",
                "--actor",
                "operator",
            ],
            cwd=str(REPO),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        expect(denied.returncode != 0, f"expected webhook reset without --force to fail: {denied.stdout!r} {denied.stderr!r}")
        expect("--force" in (denied.stderr or denied.stdout), denied.stderr or denied.stdout)

        cleared = subprocess.run(
            [
                sys.executable,
                str(CTL_PY),
                "--json",
                "notion",
                "webhook-reset-token",
                "--actor",
                "operator",
                "--minutes",
                "7",
                "--force",
            ],
            cwd=str(REPO),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        expect(cleared.returncode == 0, cleared.stderr or cleared.stdout)
        cleared_payload = json.loads(cleared.stdout)
        expect(cleared_payload["armed"] is True, str(cleared_payload))
        expect(bool(cleared_payload["armed_until"]), str(cleared_payload))

        status = subprocess.run(
            [
                sys.executable,
                str(CTL_PY),
                "--json",
                "notion",
                "webhook-status",
                "--show-public-url",
            ],
            cwd=str(REPO),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        expect(status.returncode == 0, status.stderr or status.stdout)
        status_payload = json.loads(status.stdout)
        expect(status_payload["configured"] is False, str(status_payload))
        expect(status_payload["armed"] is True, str(status_payload))
        expect(status_payload["last_armed_by"] == "operator", str(status_payload))
        expect(status_payload["last_reset_by"] == "operator", str(status_payload))
        expect(status_payload["public_url"] == "https://hooks.example.com/notion/webhook", str(status_payload))
        print("PASS test_notion_webhook_cli_requires_force_and_tracks_arm_window")


def main() -> int:
    test_redact_identity_rows_masks_emails_by_default()
    test_manual_verify_notion_user_fetches_and_validates_email()
    test_suspended_identity_cannot_be_reverified_without_unsuspend()
    test_notion_suspend_and_unsuspend_cli_audit()
    test_connect_db_migrates_legacy_notion_claim_nonce_column()
    test_expire_stale_notion_identity_claims_marks_pending_claims_expired()
    test_notion_override_cli_round_trip()
    test_notion_preflight_root_cli_uses_root_page_id()
    test_notion_webhook_cli_requires_force_and_tracks_arm_window()
    print("PASS all 9 almanac ctl notion tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
