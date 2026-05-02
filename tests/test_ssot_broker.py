#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTROL_PY = REPO / "python" / "arclink_control.py"


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
        "ARCLINK_SSOT_NOTION_ROOT_PAGE_URL": "https://www.notion.so/The-ArcLink-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
        "ARCLINK_SSOT_NOTION_ROOT_PAGE_ID": "aaaaaaaa-aaaa-bbbb-bbbb-bbbbbbbbbbbb",
        "ARCLINK_SSOT_NOTION_SPACE_URL": "https://www.notion.so/Acme-SSOT-1234567890abcdef1234567890abcdef",
        "ARCLINK_SSOT_NOTION_SPACE_ID": "12345678-90ab-cdef-1234-567890abcdef",
        "ARCLINK_SSOT_NOTION_SPACE_KIND": "database",
        "ARCLINK_SSOT_NOTION_TOKEN": "secret_test",
        "ARCLINK_SSOT_NOTION_API_VERSION": "2026-03-11",
        "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "tui-only",
        "OPERATOR_NOTIFY_CHANNEL_ID": "",
        "ARCLINK_MODEL_PRESET_CODEX": "openai:codex",
        "ARCLINK_MODEL_PRESET_OPUS": "anthropic:claude-opus",
        "ARCLINK_MODEL_PRESET_CHUTES": "chutes:model-router",
        "ARCLINK_CURATOR_CHANNELS": "tui-only",
        "ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "0",
        "ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED": "0",
    }


def insert_agent(mod, conn, *, agent_id: str, unix_user: str, display_name: str = "Alex") -> None:
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
            str(Path("/home") / unix_user / ".local" / "share" / "arclink-agent" / "hermes-home"),
            str(Path("/tmp") / f"{agent_id}-manifest.json"),
            now,
            now,
        ),
    )
    conn.commit()


def test_connect_db_enables_sqlite_wal_and_busy_timeout() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_sqlite_pragmas_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]
            expect(str(journal_mode).lower() == "wal", f"expected WAL journal mode, got {journal_mode!r}")
            # busy_timeout was bumped from 5000 to 15000 ms to absorb full-sweep
            # write windows under the new sub-second webhook -> batcher kick.
            expect(int(busy_timeout) == 15000, f"expected busy_timeout=15000, got {busy_timeout!r}")
            expect(int(synchronous) == 1, f"expected synchronous=NORMAL (1), got {synchronous!r}")
            print("PASS test_connect_db_enables_sqlite_wal_and_busy_timeout")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_read_denies_database_query_until_verified() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_read_deny_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                verification_status="unverified",
                write_mode="read_only",
            )
            try:
                mod.read_ssot(
                    conn,
                    cfg,
                    agent_id="agent-alex",
                    target_id="",
                    query={},
                    include_markdown=False,
                    requested_by_actor="agent-alex",
                )
            except PermissionError as exc:
                expect("verified" in str(exc).lower(), str(exc))
            else:
                raise AssertionError("expected database read to be denied for unverified identity")
            audit = conn.execute(
                "SELECT decision, reason FROM ssot_access_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            expect(audit is not None and audit["decision"] == "deny", str(dict(audit) if audit else {}))
            print("PASS test_ssot_read_denies_database_query_until_verified")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_read_scopes_database_results_to_verified_user() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_read_scope_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )

            mod.retrieve_notion_database = lambda **kwargs: {
                "id": "12345678-90ab-cdef-1234-567890abcdef",
                "properties": {
                    "Owner": {"type": "people"},
                    "Assignee": {"type": "people"},
                },
            }
            mod.query_notion_collection = lambda **kwargs: {
                "query_kind": "database",
                "database": kwargs["payload"],
                "data_source_id": "",
                "result": {
                    "results": [
                        {
                            "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                            "properties": {
                                "Owner": {
                                    "people": [
                                        {
                                            "id": "11111111-1111-1111-1111-111111111111",
                                            "name": "Alex",
                                        }
                                    ]
                                }
                            },
                        },
                        {
                            "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                            "properties": {
                                "Owner": {
                                    "people": [
                                        {
                                            "id": "22222222-2222-2222-2222-222222222222",
                                            "name": "Somebody Else",
                                        }
                                    ]
                                }
                            },
                        },
                    ],
                    "has_more": False,
                    "next_cursor": None,
                },
            }

            result = mod.read_ssot(
                conn,
                cfg,
                agent_id="agent-alex",
                target_id="",
                query={},
                include_markdown=False,
                requested_by_actor="agent-alex",
            )
            expect(result["target_kind"] == "database", result)
            expect(len(result["results"]) == 1, result)
            expect(result["results"][0]["id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", result)
            audit = conn.execute(
                "SELECT decision, reason FROM ssot_access_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            expect(audit is not None and audit["decision"] == "allow", str(dict(audit) if audit else {}))
            print("PASS test_ssot_read_scopes_database_results_to_verified_user")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_read_scopes_database_results_to_identity_override() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_read_override_scope_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.upsert_notion_identity_override(
                conn,
                unix_user="alex",
                notion_user_id="22222222-2222-2222-2222-222222222222",
                notion_user_email="alias@example.com",
                notes="temporary reassignment",
            )

            mod.retrieve_notion_database = lambda **kwargs: {
                "id": "12345678-90ab-cdef-1234-567890abcdef",
                "properties": {
                    "Owner": {"type": "people"},
                    "Assignee": {"type": "people"},
                },
            }
            mod.query_notion_collection = lambda **kwargs: {
                "query_kind": "database",
                "database": kwargs["payload"],
                "data_source_id": "",
                "result": {
                    "results": [
                        {
                            "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                            "properties": {
                                "Owner": {
                                    "people": [
                                        {
                                            "id": "22222222-2222-2222-2222-222222222222",
                                            "name": "Alex Alias",
                                        }
                                    ]
                                }
                            },
                        },
                        {
                            "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                            "properties": {
                                "Owner": {
                                    "people": [
                                        {
                                            "id": "33333333-3333-3333-3333-333333333333",
                                            "name": "Somebody Else",
                                        }
                                    ]
                                }
                            },
                        },
                    ],
                    "has_more": False,
                    "next_cursor": None,
                },
            }

            result = mod.read_ssot(
                conn,
                cfg,
                agent_id="agent-alex",
                target_id="",
                query={},
                include_markdown=False,
                requested_by_actor="agent-alex",
            )
            expect(result["target_kind"] == "database", result)
            expect(len(result["results"]) == 1, result)
            expect(result["results"][0]["id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", result)
            print("PASS test_ssot_read_scopes_database_results_to_identity_override")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_write_requires_verified_write_mode() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_write_gate_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                verification_status="unverified",
                write_mode="read_only",
            )
            try:
                mod.enqueue_ssot_write(
                    conn,
                    cfg,
                    agent_id="agent-alex",
                    operation="insert",
                    target_id="12345678-90ab-cdef-1234-567890abcdef",
                    payload={"properties": {"Owner": {"people": [{"name": "Alex"}]}}},
                    requested_by_actor="agent-alex",
                )
            except PermissionError as exc:
                expect("verified notion claim" in str(exc).lower(), str(exc))
            else:
                raise AssertionError("expected write to be denied for unverified identity")
            audit = conn.execute(
                "SELECT decision FROM ssot_access_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            expect(audit is not None and audit["decision"] == "deny", str(dict(audit) if audit else {}))
            print("PASS test_ssot_write_requires_verified_write_mode")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ensure_notion_verification_database_repairs_missing_managed_schema() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_verify_db_schema_repair_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            mod.upsert_setting(conn, mod.NOTION_VERIFICATION_DB_ID_SETTING, "dddddddd-dddd-dddd-dddd-dddddddddddd")
            mod.upsert_setting(
                conn,
                mod.NOTION_VERIFICATION_DB_URL_SETTING,
                "https://www.notion.so/ArcLink-Verification-dddddddddddddddddddddddddddddddd",
            )
            mod.upsert_setting(conn, mod.NOTION_VERIFICATION_DB_PARENT_SETTING, "aaaaaaaa-aaaa-bbbb-bbbb-bbbbbbbbbbbb")

            data_source_calls = {"count": 0}
            update_calls: list[dict] = []

            mod.retrieve_notion_database = lambda **kwargs: {
                "id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
                "url": "https://www.notion.so/ArcLink-Verification-dddddddddddddddddddddddddddddddd",
                "data_sources": [{"id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"}],
            }

            def fake_retrieve_data_source(**kwargs):
                data_source_calls["count"] += 1
                if data_source_calls["count"] == 1:
                    return {
                        "id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
                        "properties": {"Name": {"type": "title"}},
                    }
                return {
                    "id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
                    "properties": {
                        "Name": {"type": "title"},
                        "Claimed Email": {"type": "email"},
                        "Unix User": {"type": "rich_text"},
                        "Agent ID": {"type": "rich_text"},
                        "Session ID": {"type": "rich_text"},
                        "Status": {"type": "rich_text"},
                        "Verified": {"type": "checkbox"},
                        "Verified At": {"type": "date"},
                    },
                }

            mod.retrieve_notion_data_source = fake_retrieve_data_source
            mod.update_notion_data_source = lambda **kwargs: update_calls.append(kwargs) or {"id": kwargs["data_source_id"]}

            result = mod.ensure_notion_verification_database(conn)
            expect(result["database_id"] == "dddddddd-dddd-dddd-dddd-dddddddddddd", result)
            expect(result["parent_page_id"] == "aaaaaaaa-aaaa-bbbb-bbbb-bbbbbbbbbbbb", result)
            expect(len(update_calls) == 1, str(update_calls))
            repaired = update_calls[0]["payload"]["properties"]
            expect(
                set(repaired) == {"Claimed Email", "Unix User", "Agent ID", "Session ID", "Status", "Verified", "Verified At"},
                str(repaired),
            )
            print("PASS test_ensure_notion_verification_database_repairs_missing_managed_schema")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ensure_notion_verification_database_does_not_recreate_on_wrong_type_drift() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_verify_db_schema_drift_fail_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            mod.upsert_setting(conn, mod.NOTION_VERIFICATION_DB_ID_SETTING, "dddddddd-dddd-dddd-dddd-dddddddddddd")
            mod.upsert_setting(
                conn,
                mod.NOTION_VERIFICATION_DB_URL_SETTING,
                "https://www.notion.so/ArcLink-Verification-dddddddddddddddddddddddddddddddd",
            )
            mod.upsert_setting(conn, mod.NOTION_VERIFICATION_DB_PARENT_SETTING, "aaaaaaaa-aaaa-bbbb-bbbb-bbbbbbbbbbbb")

            mod.retrieve_notion_database = lambda **kwargs: {
                "id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
                "url": "https://www.notion.so/ArcLink-Verification-dddddddddddddddddddddddddddddddd",
                "data_sources": [{"id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"}],
            }
            mod.retrieve_notion_data_source = lambda **kwargs: {
                "id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
                "properties": {
                    "Name": {"type": "title"},
                    "Claimed Email": {"type": "email"},
                    "Unix User": {"type": "rich_text"},
                    "Agent ID": {"type": "rich_text"},
                    "Session ID": {"type": "rich_text"},
                    "Status": {"type": "checkbox"},
                    "Verified": {"type": "checkbox"},
                    "Verified At": {"type": "date"},
                },
            }

            def boom(**kwargs):
                raise AssertionError("cached verification database should not be silently recreated on schema drift")

            mod.create_notion_database = boom

            try:
                mod.ensure_notion_verification_database(conn)
            except RuntimeError as exc:
                expect("schema drift" in str(exc), str(exc))
                expect("wrong types" in str(exc), str(exc))
            else:
                raise AssertionError("expected wrong-type schema drift to fail closed")
            print("PASS test_ensure_notion_verification_database_does_not_recreate_on_wrong_type_drift")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_start_notion_identity_claim_creates_page_under_shared_parent() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_claim_page_parent_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            mod.set_agent_identity_claim = lambda *args, **kwargs: {
                "agent_id": kwargs.get("agent_id", ""),
                "unix_user": kwargs.get("unix_user", ""),
                "claimed_notion_email": kwargs.get("claimed_notion_email", ""),
            }
            create_calls: list[dict[str, object]] = []

            def fake_create_notion_page(**kwargs):
                create_calls.append(kwargs)
                return {
                    "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                    "url": "https://www.notion.so/ArcLink-Verification-alex-cccccccccccccccccccccccccccccccc",
                }

            mod.create_notion_page = fake_create_notion_page
            claim = mod.start_notion_identity_claim(
                conn,
                session_id="onb_test",
                agent_id="agent-alex",
                unix_user="alex",
                claimed_notion_email="alex@example.com",
            )
            expect(len(create_calls) == 1, str(create_calls))
            created = create_calls[0]
            expect(created["parent_kind"] == "page", str(created))
            expect(created["parent_id"] == "aaaaaaaa-aaaa-bbbb-bbbb-bbbbbbbbbbbb", str(created))
            payload = created["payload"]
            expect(isinstance(payload, dict), str(payload))
            properties = payload.get("properties") if isinstance(payload, dict) else {}
            expect(isinstance(properties, dict) and "title" in properties, str(properties))
            title_entries = properties.get("title")
            expect(isinstance(title_entries, list) and title_entries, str(properties))
            children = payload.get("children") if isinstance(payload, dict) else []
            expect(isinstance(children, list) and len(children) >= 3, str(children))
            expect(str(claim.get("verification_parent_page_id") or "") == "aaaaaaaa-aaaa-bbbb-bbbb-bbbbbbbbbbbb", str(claim))
            stored = mod.get_notion_identity_claim(conn, claim_id=str(claim.get("claim_id") or ""))
            expect(stored is not None and stored["notion_page_id"] == "cccccccc-cccc-cccc-cccc-cccccccccccc", str(stored))
            print("PASS test_start_notion_identity_claim_creates_page_under_shared_parent")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_write_applies_verified_owned_update() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_write_apply_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.retrieve_notion_page = lambda **kwargs: {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "parent": {
                    "type": "data_source_id",
                    "data_source_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
                },
                "properties": {
                    "Owner": {
                        "people": [
                            {
                                "id": "11111111-1111-1111-1111-111111111111",
                                "name": "Alex",
                            }
                        ]
                    }
                },
            }
            mod.retrieve_notion_data_source = lambda **kwargs: {
                "id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
                "properties": {
                    "Changed By": {"type": "people"},
                },
            }
            update_calls: list[dict] = []

            def fake_update_notion_page(**kwargs):
                update_calls.append(kwargs)
                return {
                    "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "properties": kwargs["payload"]["properties"],
                }

            mod.update_notion_page = fake_update_notion_page

            result = mod.enqueue_ssot_write(
                conn,
                cfg,
                agent_id="agent-alex",
                operation="update",
                target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                payload={
                    "properties": {
                        "Status": {"status": {"name": "In Progress"}},
                        "Changed By": {"people": [{"id": "99999999-9999-9999-9999-999999999999"}]},
                    }
                },
                requested_by_actor="agent-alex",
            )
            expect(result["applied"] is True, result)
            expect(result["queued"] is False, result)
            expect(len(update_calls) == 1, str(update_calls))
            expect(update_calls[0]["page_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", str(update_calls))
            changed_by = update_calls[0]["payload"]["properties"]["Changed By"]["people"][0]["id"]
            expect(changed_by == "11111111-1111-1111-1111-111111111111", str(update_calls[0]["payload"]))
            refresh_job = conn.execute(
                "SELECT job_kind, last_status FROM refresh_jobs ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            expect(refresh_job is not None and refresh_job["job_kind"] == "ssot-write", str(dict(refresh_job) if refresh_job else {}))
            expect(refresh_job["last_status"] == "applied", str(dict(refresh_job)))
            audit = conn.execute(
                "SELECT decision FROM ssot_access_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            expect(audit is not None and audit["decision"] == "allow", str(dict(audit) if audit else {}))
            print("PASS test_ssot_write_applies_verified_owned_update")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_write_applies_verified_owned_append() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_append_apply_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.retrieve_notion_page = lambda **kwargs: {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "properties": {
                    "Owner": {
                        "people": [
                            {
                                "id": "11111111-1111-1111-1111-111111111111",
                                "name": "Alex",
                            }
                        ]
                    }
                },
            }
            append_calls: list[dict] = []

            def fake_append(**kwargs):
                append_calls.append(kwargs)
                return {
                    "results": kwargs["payload"]["children"],
                }

            mod.append_notion_block_children = fake_append
            result = mod.enqueue_ssot_write(
                conn,
                cfg,
                agent_id="agent-alex",
                operation="append",
                target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                payload={
                    "children": [
                        {
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {"content": "Quick status note"},
                                    }
                                ]
                            },
                        }
                    ]
                },
                requested_by_actor="agent-alex",
            )
            expect(result["applied"] is True, result)
            expect(result["queued"] is False, result)
            expect(len(append_calls) == 1, str(append_calls))
            expect(append_calls[0]["block_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", str(append_calls))
            expect(len(append_calls[0]["payload"]["children"]) == 1, str(append_calls[0]["payload"]))
            audit = conn.execute(
                "SELECT decision, operation FROM ssot_access_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            expect(audit is not None and audit["decision"] == "allow", str(dict(audit) if audit else {}))
            expect(audit["operation"] == "append", str(dict(audit)))
            print("PASS test_ssot_write_applies_verified_owned_append")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_write_applies_verified_owned_insert() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_insert_apply_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.resolve_notion_target = lambda **kwargs: {
                "kind": "database",
                "id": "12345678-90ab-cdef-1234-567890abcdef",
            }
            mod.retrieve_notion_database = lambda **kwargs: {
                "id": "12345678-90ab-cdef-1234-567890abcdef",
                "properties": {
                    "Owner": {"type": "people"},
                    "Changed By": {"type": "people"},
                },
            }
            create_calls: list[dict] = []

            def fake_create_notion_page(**kwargs):
                create_calls.append(kwargs)
                return {
                    "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                    "properties": kwargs["payload"]["properties"],
                }

            mod.create_notion_page = fake_create_notion_page
            result = mod.enqueue_ssot_write(
                conn,
                cfg,
                agent_id="agent-alex",
                operation="insert",
                target_id="12345678-90ab-cdef-1234-567890abcdef",
                payload={
                    "properties": {
                        "Owner": {"people": [{"id": "11111111-1111-1111-1111-111111111111"}]},
                        "Changed By": {"people": [{"id": "99999999-9999-9999-9999-999999999999"}]},
                    }
                },
                requested_by_actor="agent-alex",
            )
            expect(result["applied"] is True, result)
            expect(result["target_id"] == "cccccccc-cccc-cccc-cccc-cccccccccccc", result)
            expect(len(create_calls) == 1, str(create_calls))
            expect(create_calls[0]["parent_kind"] == "database", str(create_calls))
            changed_by = create_calls[0]["payload"]["properties"]["Changed By"]["people"][0]["id"]
            expect(changed_by == "11111111-1111-1111-1111-111111111111", str(create_calls[0]["payload"]))
            refresh_job = conn.execute(
                "SELECT job_kind, last_status FROM refresh_jobs ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            expect(refresh_job is not None and refresh_job["job_kind"] == "ssot-write", str(dict(refresh_job) if refresh_job else {}))
            expect(refresh_job["last_status"] == "applied", str(dict(refresh_job)))
            audit = conn.execute(
                "SELECT decision FROM ssot_access_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            expect(audit is not None and audit["decision"] == "allow", str(dict(audit) if audit else {}))
            print("PASS test_ssot_write_applies_verified_owned_insert")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_write_allows_child_page_insert_under_verified_parent_without_owner_property() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_child_page_insert_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.resolve_notion_target = lambda **kwargs: {
                "kind": "page",
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            }
            mod.retrieve_notion_page = lambda **kwargs: {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "created_by": {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "type": "person",
                },
                "last_edited_by": {
                    "id": "99999999-9999-9999-9999-999999999999",
                    "type": "bot",
                },
                "properties": {},
            }
            create_calls: list[dict] = []

            def fake_create_notion_page(**kwargs):
                create_calls.append(kwargs)
                return {"id": "dddddddd-dddd-dddd-dddd-dddddddddddd"}

            mod.create_notion_page = fake_create_notion_page
            result = mod.enqueue_ssot_write(
                conn,
                cfg,
                agent_id="agent-alex",
                operation="insert",
                target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                payload={
                    "children": [
                        {
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {"type": "text", "text": {"content": "Guide can create normal child pages."}}
                                ]
                            },
                        }
                    ]
                },
                requested_by_actor="agent-alex",
            )
            expect(result["applied"] is True, result)
            expect(result["queued"] is False, result)
            expect(result["target_id"] == "dddddddd-dddd-dddd-dddd-dddddddddddd", result)
            expect(result["owner_source"] == "page-parent-created-by", str(result))
            expect(len(create_calls) == 1, str(create_calls))
            expect(create_calls[0]["parent_kind"] == "page", str(create_calls))
            expect("properties" not in create_calls[0]["payload"], str(create_calls[0]["payload"]))
            audit = conn.execute(
                "SELECT decision, reason FROM ssot_access_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            expect(audit is not None and audit["decision"] == "allow", str(dict(audit) if audit else {}))
            print("PASS test_ssot_write_allows_child_page_insert_under_verified_parent_without_owner_property")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_database_insert_outside_lane_queues_for_user_approval_then_applies() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_user_approved_database_insert_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.resolve_notion_target = lambda **kwargs: {
                "kind": "database",
                "id": "12345678-90ab-cdef-1234-567890abcdef",
            }
            mod.retrieve_notion_database = lambda **kwargs: {
                "id": "12345678-90ab-cdef-1234-567890abcdef",
                "properties": {
                    "Owner": {"type": "people"},
                    "Changed By": {"type": "people"},
                },
            }
            create_calls: list[dict] = []

            def fake_create_notion_page(**kwargs):
                create_calls.append(kwargs)
                return {"id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"}

            mod.create_notion_page = fake_create_notion_page
            result = mod.enqueue_ssot_write(
                conn,
                cfg,
                agent_id="agent-alex",
                operation="insert",
                target_id="12345678-90ab-cdef-1234-567890abcdef",
                payload={"properties": {"Name": {"title": [{"text": {"content": "Cross-lane item"}}]}}},
                requested_by_actor="agent-alex",
            )
            expect(result["applied"] is False, result)
            expect(result["queued"] is True, result)
            expect(result["approval_owner"] == "user", result)
            expect(len(create_calls) == 0, str(create_calls))
            pending_id = str(result["pending_id"])

            queued = conn.execute(
                "SELECT target_kind, target_id, channel_kind, message FROM notification_outbox ORDER BY id DESC LIMIT 1"
            ).fetchone()
            expect(queued is not None and queued["target_kind"] == "user-agent", str(dict(queued) if queued else {}))
            expect(queued["target_id"] == "agent-alex", str(dict(queued)))
            expect(queued["channel_kind"] == "ssot-approval", str(dict(queued)))
            expect(pending_id in str(queued["message"]), str(dict(queued)))

            approved = mod.approve_ssot_pending_write(
                conn,
                cfg,
                pending_id=pending_id,
                surface="user-agent",
                actor="agent-alex",
            )
            expect(approved["status"] == "applied", str(approved))
            expect(len(create_calls) == 1, str(create_calls))
            changed_by = create_calls[0]["payload"]["properties"]["Changed By"]["people"][0]["id"]
            expect(changed_by == "11111111-1111-1111-1111-111111111111", str(create_calls[0]["payload"]))
            print("PASS test_ssot_database_insert_outside_lane_queues_for_user_approval_then_applies")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_create_database_under_shared_root_queues_then_inherits_parent_access() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_create_database_shared_parent_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.resolve_notion_target = lambda **kwargs: {"kind": "page", "id": kwargs["target_id"]}
            mod.retrieve_notion_page = lambda **kwargs: {
                "id": kwargs["page_id"],
                "created_by": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "type": "person",
                },
                "last_edited_by": {
                    "id": "99999999-9999-9999-9999-999999999999",
                    "type": "bot",
                },
                "properties": {},
            }
            create_calls: list[dict] = []

            def fake_create_notion_database(**kwargs):
                create_calls.append(kwargs)
                return {
                    "object": "database",
                    "id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
                    "url": "https://www.notion.so/Org-To-Dos-dddddddddddddddddddddddddddddddd",
                }

            mod.create_notion_database = fake_create_notion_database
            result = mod.enqueue_ssot_write(
                conn,
                cfg,
                agent_id="agent-alex",
                operation="create_database",
                target_id="",
                payload={
                    "title": "Org To-Dos",
                    "is_inline": False,
                    "properties": {
                        "Task": {"type": "title"},
                        "Status": {"select": {"options": [{"name": "Not started"}, {"name": "Done"}]}},
                        "Assignee": {"type": "people"},
                    },
                },
                requested_by_actor="agent-alex",
            )
            expect(result["applied"] is False and result["queued"] is True, result)
            expect(len(create_calls) == 0, str(create_calls))
            pending_id = str(result["pending_id"])

            approved = mod.approve_ssot_pending_write(
                conn,
                cfg,
                pending_id=pending_id,
                surface="user-agent",
                actor="agent-alex",
            )
            expect(approved["status"] == "applied", str(approved))
            expect(len(create_calls) == 1, str(create_calls))
            created = create_calls[0]
            expect(created["parent_page_id"] == "aaaaaaaa-aaaa-bbbb-bbbb-bbbbbbbbbbbb", str(created))
            expect(created["title"] == "Org To-Dos", str(created))
            expect(created["is_inline"] is False, str(created))
            expect(created["properties"]["Task"] == {"title": {}}, str(created))
            expect(created["properties"]["Assignee"] == {"people": {}}, str(created))
            applied = approved["apply_result"]
            expect(applied["target_id"] == "dddddddd-dddd-dddd-dddd-dddddddddddd", str(applied))
            expect(applied["notion_result"]["object"] == "database", str(applied))
            print("PASS test_ssot_create_database_under_shared_root_queues_then_inherits_parent_access")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_create_database_rejects_payload_parent_to_avoid_private_workspace_creation() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_create_database_parent_guard_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.resolve_notion_target = lambda **kwargs: {"kind": "page", "id": kwargs["target_id"]}
            mod.retrieve_notion_page = lambda **kwargs: {
                "id": kwargs["page_id"],
                "created_by": {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "type": "person",
                },
                "last_edited_by": {
                    "id": "99999999-9999-9999-9999-999999999999",
                    "type": "bot",
                },
                "properties": {},
            }
            create_calls: list[dict] = []
            mod.create_notion_database = lambda **kwargs: create_calls.append(kwargs) or {}
            try:
                mod.enqueue_ssot_write(
                    conn,
                    cfg,
                    agent_id="agent-alex",
                    operation="create_database",
                    target_id="",
                    payload={
                        "title": "Private by accident",
                        "parent": {"type": "workspace", "workspace": True},
                        "properties": {"Task": {"title": {}}},
                    },
                    requested_by_actor="agent-alex",
                )
            except ValueError as exc:
                expect("payload.parent" in str(exc), str(exc))
            else:
                raise AssertionError("expected payload parent to be rejected")
            expect(len(create_calls) == 0, str(create_calls))
            print("PASS test_ssot_create_database_rejects_payload_parent_to_avoid_private_workspace_creation")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_create_page_under_shared_root_queues_then_inherits_parent_access() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_create_page_shared_parent_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.resolve_notion_target = lambda **kwargs: {"kind": "page", "id": kwargs["target_id"]}
            mod.retrieve_notion_page = lambda **kwargs: {
                "id": kwargs["page_id"],
                "created_by": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "type": "person",
                },
                "last_edited_by": {
                    "id": "99999999-9999-9999-9999-999999999999",
                    "type": "bot",
                },
                "properties": {},
            }
            create_calls: list[dict] = []

            def fake_create_notion_page(**kwargs):
                create_calls.append(kwargs)
                return {
                    "object": "page",
                    "id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
                    "url": "https://www.notion.so/Project-Notes-eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
                }

            mod.create_notion_page = fake_create_notion_page
            result = mod.enqueue_ssot_write(
                conn,
                cfg,
                agent_id="agent-alex",
                operation="create_page",
                target_id="",
                payload={
                    "title": "Project Notes",
                    "children": [
                        {
                            "type": "bulleted_list_item",
                            "bulleted_list_item": {
                                "rich_text": [
                                    {"type": "text", "text": {"content": "First shared note."}}
                                ]
                            },
                        }
                    ],
                },
                requested_by_actor="agent-alex",
            )
            expect(result["applied"] is False and result["queued"] is True, result)
            expect(len(create_calls) == 0, str(create_calls))
            pending_id = str(result["pending_id"])

            approved = mod.approve_ssot_pending_write(
                conn,
                cfg,
                pending_id=pending_id,
                surface="user-agent",
                actor="agent-alex",
            )
            expect(approved["status"] == "applied", str(approved))
            expect(len(create_calls) == 1, str(create_calls))
            created = create_calls[0]
            expect(created["parent_id"] == "aaaaaaaa-aaaa-bbbb-bbbb-bbbbbbbbbbbb", str(created))
            expect(created["parent_kind"] == "page", str(created))
            created_payload = created["payload"]
            expect(created_payload["properties"]["title"][0]["text"]["content"] == "Project Notes", str(created_payload))
            expect(len(created_payload["children"]) == 1, str(created_payload))
            applied = approved["apply_result"]
            expect(applied["target_id"] == "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee", str(applied))
            expect(applied["notion_result"]["object"] == "page", str(applied))
            print("PASS test_ssot_create_page_under_shared_root_queues_then_inherits_parent_access")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_create_page_rejects_payload_parent_to_avoid_private_workspace_creation() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_create_page_parent_guard_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.resolve_notion_target = lambda **kwargs: {"kind": "page", "id": kwargs["target_id"]}
            mod.retrieve_notion_page = lambda **kwargs: {
                "id": kwargs["page_id"],
                "created_by": {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "type": "person",
                },
                "last_edited_by": {
                    "id": "99999999-9999-9999-9999-999999999999",
                    "type": "bot",
                },
                "properties": {},
            }
            create_calls: list[dict] = []
            mod.create_notion_page = lambda **kwargs: create_calls.append(kwargs) or {}
            try:
                mod.enqueue_ssot_write(
                    conn,
                    cfg,
                    agent_id="agent-alex",
                    operation="create_page",
                    target_id="",
                    payload={
                        "title": "Private by accident",
                        "parent": {"type": "workspace", "workspace": True},
                    },
                    requested_by_actor="agent-alex",
                )
            except ValueError as exc:
                expect("payload.parent" in str(exc), str(exc))
            else:
                raise AssertionError("expected payload parent to be rejected")
            expect(len(create_calls) == 0, str(create_calls))
            print("PASS test_ssot_create_page_rejects_payload_parent_to_avoid_private_workspace_creation")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_create_page_normalizer_fails_closed_on_sloppy_agent_payloads() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_create_page_payload_guard_test")
    block = {
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {"type": "text", "text": {"content": "A bounded shared note."}},
            ],
        },
    }
    nested_block = {
        "type": "toggle",
        "toggle": {
            "rich_text": [
                {"type": "text", "text": {"content": "Open items"}},
            ],
            "children": [block],
        },
    }
    too_deep_block = {
        "type": "toggle",
        "toggle": {
            "rich_text": [
                {"type": "text", "text": {"content": "Outer"}},
            ],
            "children": [
                {
                    "type": "toggle",
                    "toggle": {
                        "rich_text": [
                            {"type": "text", "text": {"content": "Inner"}},
                        ],
                        "children": [block],
                    },
                }
            ],
        },
    }
    try:
        mod._normalize_ssot_create_page_payload({"title": "Bad", "in_trash": True})
    except ValueError as exc:
        expect("unsupported field" in str(exc), str(exc))
    else:
        raise AssertionError("expected create_page to reject unsupported top-level fields")

    try:
        mod._normalize_ssot_create_page_payload({"title": "Too much", "children": [block] * 101})
    except ValueError as exc:
        expect("at most 100" in str(exc), str(exc))
    else:
        raise AssertionError("expected create_page to reject oversized child block batches")

    try:
        mod._normalize_ssot_create_page_payload({"title": "Bad child", "children": ["paragraph"]})
    except ValueError as exc:
        expect("must be an object" in str(exc), str(exc))
    else:
        raise AssertionError("expected create_page to reject non-object child blocks")

    try:
        mod._normalize_ssot_create_page_payload({"title": "Null children", "children": None})
    except ValueError as exc:
        expect("'children' to be a list" in str(exc), str(exc))
    else:
        raise AssertionError("expected create_page to reject null children")

    try:
        mod._normalize_ssot_create_page_payload({"title": "Too deep", "children": [too_deep_block]})
    except ValueError as exc:
        expect("at most 2 inline child block levels" in str(exc), str(exc))
    else:
        raise AssertionError("expected create_page to reject too-deep nested child blocks")

    normalized = mod._normalize_ssot_create_page_payload(
        {
            "title": "Release Notes",
            "children": [block, nested_block],
        }
    )
    expect(normalized["properties"]["title"][0]["text"]["content"] == "Release Notes", str(normalized))
    expect(normalized["children"] == [block, nested_block], str(normalized))
    print("PASS test_ssot_create_page_normalizer_fails_closed_on_sloppy_agent_payloads")


def test_ssot_database_and_append_normalizers_reject_sloppy_agent_payloads() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_payload_guard_test")
    block = {
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {"type": "text", "text": {"content": "A bounded shared note."}},
            ],
        },
    }
    try:
        mod._normalize_ssot_create_database_payload(
            {"title": "Bad", "parent": "workspace", "properties": {"Name": {"title": {}}}}
        )
    except ValueError as exc:
        expect("payload.parent" in str(exc), str(exc))
    else:
        raise AssertionError("expected create_database to reject any payload parent")

    try:
        mod._normalize_ssot_create_database_payload(
            {"title": "Bad", "children": [block], "properties": {"Name": {"title": {}}}}
        )
    except ValueError as exc:
        expect("unsupported field" in str(exc), str(exc))
    else:
        raise AssertionError("expected create_database to reject unsupported top-level fields")

    try:
        mod._normalize_ssot_append_payload({"children": [block] * 101})
    except ValueError as exc:
        expect("at most 100" in str(exc), str(exc))
    else:
        raise AssertionError("expected append to reject oversized child block batches")
    print("PASS test_ssot_database_and_append_normalizers_reject_sloppy_agent_payloads")


def test_ssot_preflight_reports_write_vs_user_approval() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_preflight_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.resolve_notion_target = lambda **kwargs: {"kind": "page", "id": kwargs["target_id"]}
            page_owner = {"id": "11111111-1111-1111-1111-111111111111", "type": "person"}
            page_other = {"id": "22222222-2222-2222-2222-222222222222", "type": "person"}

            def fake_retrieve_notion_page(**kwargs):
                page_id = kwargs["page_id"]
                return {
                    "id": page_id,
                    "created_by": page_owner if page_id.startswith("a") else page_other,
                    "last_edited_by": {"id": "99999999-9999-9999-9999-999999999999", "type": "bot"},
                    "properties": {},
                }

            mod.retrieve_notion_page = fake_retrieve_notion_page
            allowed = mod.preflight_ssot_write(
                conn,
                cfg,
                agent_id="agent-alex",
                operation="insert",
                target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                payload={"children": []},
                requested_by_actor="agent-alex",
            )
            expect(allowed["allowed"] is True and allowed["recommended_action"] == "write", str(allowed))
            queued = mod.preflight_ssot_write(
                conn,
                cfg,
                agent_id="agent-alex",
                operation="insert",
                target_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                payload={"children": []},
                requested_by_actor="agent-alex",
            )
            expect(queued["allowed"] is False and queued["approval_owner"] == "user", str(queued))
            expect(queued["recommended_action"] == "ask-user-approval", str(queued))
            print("PASS test_ssot_preflight_reports_write_vs_user_approval")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_create_payload_validation_happens_before_approval_queueing() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_create_payload_prequeue_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )

            def fail_notion_lookup(**_kwargs):
                raise AssertionError("invalid create payload should not inspect Notion scope")

            mod.resolve_notion_target = fail_notion_lookup
            mod.retrieve_notion_page = fail_notion_lookup
            invalid_payload = {
                "title": "Private by accident",
                "parent": {"type": "workspace", "workspace": True},
            }
            preflight = mod.preflight_ssot_write(
                conn,
                cfg,
                agent_id="agent-alex",
                operation="create_page",
                target_id="",
                payload=invalid_payload,
                requested_by_actor="agent-alex",
            )
            expect(preflight["allowed"] is False, str(preflight))
            expect(preflight["would_queue"] is False, str(preflight))
            expect(preflight["recommended_action"] == "fix-payload", str(preflight))
            expect("payload.parent" in preflight["reason"], str(preflight))

            try:
                mod.enqueue_ssot_write(
                    conn,
                    cfg,
                    agent_id="agent-alex",
                    operation="create_page",
                    target_id="",
                    payload=invalid_payload,
                    requested_by_actor="agent-alex",
                )
            except ValueError as exc:
                expect("payload.parent" in str(exc), str(exc))
            else:
                raise AssertionError("expected invalid create_page payload to fail before queueing")
            expect(mod.count_ssot_pending_writes(conn, status="pending", agent_id="agent-alex") == 0, "unexpected pending write")
            outbox_count = conn.execute("SELECT COUNT(*) FROM notification_outbox").fetchone()[0]
            expect(outbox_count == 0, f"unexpected approval notification count {outbox_count}")
            print("PASS test_ssot_create_payload_validation_happens_before_approval_queueing")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_write_allows_page_update_from_prior_agent_history() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_page_history_update_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.log_ssot_access_audit(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                operation="update",
                target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                decision="allow",
                reason="prior brokered write",
                actor="agent-alex",
                request_payload={},
            )
            mod.retrieve_notion_page = lambda **kwargs: {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "created_by": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "name": "Somebody Else",
                },
                "last_edited_by": {
                    "id": "99999999-9999-9999-9999-999999999999",
                    "type": "bot",
                },
                "properties": {},
            }
            update_calls: list[dict] = []

            def fake_update_notion_page(**kwargs):
                update_calls.append(kwargs)
                return {"id": kwargs["page_id"], "properties": kwargs["payload"].get("properties", {})}

            mod.update_notion_page = fake_update_notion_page
            result = mod.enqueue_ssot_write(
                conn,
                cfg,
                agent_id="agent-alex",
                operation="update",
                target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                payload={"properties": {"Status": {"status": {"name": "In Progress"}}}},
                requested_by_actor="agent-alex",
            )
            expect(result["applied"] is True, result)
            expect(result["owner_source"] == "agent-write-history", str(result))
            expect(len(update_calls) == 1, str(update_calls))
            print("PASS test_ssot_write_allows_page_update_from_prior_agent_history")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_write_queues_prior_agent_history_when_page_has_other_owner() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_page_history_owner_guard_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.log_ssot_access_audit(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                operation="update",
                target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                decision="allow",
                reason="prior brokered write",
                actor="agent-alex",
                request_payload={},
            )
            mod.retrieve_notion_page = lambda **kwargs: {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "properties": {
                    "Owner": {
                        "people": [
                            {
                                "id": "22222222-2222-2222-2222-222222222222",
                                "name": "Somebody Else",
                            }
                        ]
                    }
                },
                "last_edited_by": {
                    "id": "99999999-9999-9999-9999-999999999999",
                    "type": "bot",
                },
            }
            result = mod.enqueue_ssot_write(
                conn,
                cfg,
                agent_id="agent-alex",
                operation="update",
                target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                payload={"properties": {"Status": {"status": {"name": "Blocked"}}}},
                requested_by_actor="agent-alex",
            )
            expect(result["applied"] is False, result)
            expect(result["queued"] is True, result)
            expect(result["approval_required"] is True, result)
            expect(str(result["pending_id"]).startswith("ssotw_"), result)
            pending = conn.execute(
                "SELECT status, owner_source FROM ssot_pending_writes WHERE pending_id = ?",
                (str(result["pending_id"]),),
            ).fetchone()
            expect(pending is not None and pending["status"] == "pending", str(dict(pending) if pending else {}))
            expect(pending["owner_source"] == "ownership-mismatch", str(dict(pending)))
            audit = conn.execute(
                "SELECT decision FROM ssot_access_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            expect(audit is not None and audit["decision"] == "queue", str(dict(audit) if audit else {}))
            print("PASS test_ssot_write_queues_prior_agent_history_when_page_has_other_owner")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_write_queues_insert_under_out_of_scope_parent_page() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_page_parent_insert_scope_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.resolve_notion_target = lambda **kwargs: {
                "kind": "page",
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            }
            mod.retrieve_notion_page = lambda **kwargs: {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "created_by": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "name": "Somebody Else",
                },
                "last_edited_by": {
                    "id": "99999999-9999-9999-9999-999999999999",
                    "type": "bot",
                },
                "properties": {},
            }

            def boom(**kwargs):
                raise AssertionError("expected page-scoped insert to stop before create_notion_page")

            mod.create_notion_page = boom
            result = mod.enqueue_ssot_write(
                conn,
                cfg,
                agent_id="agent-alex",
                operation="insert",
                target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                payload={
                    "properties": {
                        "Owner": {"people": [{"id": "11111111-1111-1111-1111-111111111111"}]}
                    }
                },
                requested_by_actor="agent-alex",
            )
            expect(result["applied"] is False, result)
            expect(result["queued"] is True, result)
            expect(result["approval_required"] is True, result)
            audit = conn.execute(
                "SELECT decision, reason FROM ssot_access_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            expect(audit is not None and audit["decision"] == "queue", str(dict(audit) if audit else {}))
            expect("parent page is outside" in str(audit["reason"]).lower(), str(dict(audit)))
            pending = conn.execute(
                "SELECT status, owner_source FROM ssot_pending_writes WHERE pending_id = ?",
                (str(result["pending_id"]),),
            ).fetchone()
            expect(pending is not None and pending["status"] == "pending", str(dict(pending) if pending else {}))
            expect(pending["owner_source"] == "page-parent-ownership-mismatch", str(dict(pending)))
            print("PASS test_ssot_write_queues_insert_under_out_of_scope_parent_page")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_write_applies_without_changed_by_property() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_insert_without_changed_by_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.resolve_notion_target = lambda **kwargs: {
                "kind": "database",
                "id": "12345678-90ab-cdef-1234-567890abcdef",
            }
            mod.retrieve_notion_database = lambda **kwargs: {
                "id": "12345678-90ab-cdef-1234-567890abcdef",
                "properties": {
                    "Owner": {"type": "people"},
                },
            }
            create_calls: list[dict] = []

            def fake_create_notion_page(**kwargs):
                create_calls.append(kwargs)
                return {"id": "cccccccc-cccc-cccc-cccc-cccccccccccc"}

            mod.create_notion_page = fake_create_notion_page
            result = mod.enqueue_ssot_write(
                conn,
                cfg,
                agent_id="agent-alex",
                operation="insert",
                target_id="12345678-90ab-cdef-1234-567890abcdef",
                payload={"properties": {"Owner": {"people": [{"id": "11111111-1111-1111-1111-111111111111"}]}}},
                requested_by_actor="agent-alex",
            )
            expect(result["applied"] is True, result)
            expect("Changed By" not in create_calls[0]["payload"]["properties"], str(create_calls[0]["payload"]))
            print("PASS test_ssot_write_applies_without_changed_by_property")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_write_fails_closed_when_changed_by_schema_lookup_fails() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_changed_by_schema_fail_closed_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.resolve_notion_target = lambda **kwargs: {
                "kind": "database",
                "id": "12345678-90ab-cdef-1234-567890abcdef",
            }

            def boom(**kwargs):
                raise RuntimeError("schema lookup failed")

            mod.retrieve_notion_database = boom
            try:
                mod.enqueue_ssot_write(
                    conn,
                    cfg,
                    agent_id="agent-alex",
                    operation="insert",
                    target_id="12345678-90ab-cdef-1234-567890abcdef",
                    payload={"properties": {"Owner": {"people": [{"id": "11111111-1111-1111-1111-111111111111"}]}}},
                    requested_by_actor="agent-alex",
                )
            except RuntimeError as exc:
                expect("schema lookup failed" in str(exc), str(exc))
            else:
                raise AssertionError("expected Changed By schema lookup failure to abort the write")
            print("PASS test_ssot_write_fails_closed_when_changed_by_schema_lookup_fails")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_write_logs_failure_when_notion_apply_raises() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_write_apply_fail_audit_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.retrieve_notion_page = lambda **kwargs: {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "parent": {"type": "database_id", "database_id": "12345678-90ab-cdef-1234-567890abcdef"},
                "properties": {
                    "Owner": {
                        "people": [
                            {"id": "11111111-1111-1111-1111-111111111111"}
                        ]
                    }
                },
            }
            mod.retrieve_notion_database = lambda **kwargs: {
                "id": "12345678-90ab-cdef-1234-567890abcdef",
                "properties": {"Changed By": {"type": "people"}},
            }

            def boom(**kwargs):
                raise RuntimeError("notion apply exploded")

            mod.update_notion_page = boom
            try:
                mod.enqueue_ssot_write(
                    conn,
                    cfg,
                    agent_id="agent-alex",
                    operation="update",
                    target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    payload={"properties": {}},
                    requested_by_actor="agent-alex",
                )
            except RuntimeError as exc:
                expect("notion apply exploded" in str(exc), str(exc))
            else:
                raise AssertionError("expected ssot write apply failure to propagate")
            audit = conn.execute(
                "SELECT decision, reason FROM ssot_access_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            expect(audit is not None and audit["decision"] == "fail", str(dict(audit) if audit else {}))
            expect("notion apply exploded" in str(audit["reason"] or ""), str(dict(audit)))
            refresh_job = conn.execute(
                "SELECT last_status, last_note FROM refresh_jobs ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            expect(refresh_job is not None and refresh_job["last_status"] == "fail", str(dict(refresh_job) if refresh_job else {}))
            expect("notion apply exploded" in str(refresh_job["last_note"] or ""), str(dict(refresh_job)))
            print("PASS test_ssot_write_logs_failure_when_notion_apply_raises")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_read_denies_suspended_identity() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_read_suspended_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
                suspended_at=mod.utc_now_iso(),
            )
            try:
                mod.read_ssot(
                    conn,
                    cfg,
                    agent_id="agent-alex",
                    target_id="",
                    query={},
                    include_markdown=False,
                    requested_by_actor="agent-alex",
                )
            except PermissionError as exc:
                expect("suspended" in str(exc).lower(), str(exc))
            else:
                raise AssertionError("expected suspended identity read to be denied")
            audit = conn.execute(
                "SELECT decision, reason FROM ssot_access_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            expect(audit is not None and audit["decision"] == "deny", str(dict(audit) if audit else {}))
            expect("suspended" in str(audit["reason"]).lower(), str(dict(audit)))
            print("PASS test_ssot_read_denies_suspended_identity")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_write_queues_cross_owner_update() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_write_cross_owner_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.retrieve_notion_page = lambda **kwargs: {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "properties": {
                    "Owner": {
                        "people": [
                            {
                                "id": "22222222-2222-2222-2222-222222222222",
                                "name": "Somebody Else",
                            }
                        ]
                    }
                },
            }
            result = mod.enqueue_ssot_write(
                conn,
                cfg,
                agent_id="agent-alex",
                operation="update",
                target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                payload={"properties": {"Status": {"status": {"name": "Blocked"}}}},
                requested_by_actor="agent-alex",
            )
            expect(result["applied"] is False, result)
            expect(result["queued"] is True, result)
            expect(result["approval_required"] is True, result)
            audit = conn.execute(
                "SELECT decision FROM ssot_access_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            expect(audit is not None and audit["decision"] == "queue", str(dict(audit) if audit else {}))
            pending = conn.execute(
                "SELECT status, owner_source FROM ssot_pending_writes WHERE pending_id = ?",
                (str(result["pending_id"]),),
            ).fetchone()
            expect(pending is not None and pending["status"] == "pending", str(dict(pending) if pending else {}))
            expect(pending["owner_source"] == "ownership-mismatch", str(dict(pending)))
            print("PASS test_ssot_write_queues_cross_owner_update")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_pending_write_approval_applies_queued_update() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_pending_approve_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            page_payload = {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "properties": {
                    "Owner": {
                        "people": [
                            {
                                "id": "22222222-2222-2222-2222-222222222222",
                                "name": "Somebody Else",
                            }
                        ]
                    }
                },
            }
            mod.retrieve_notion_page = lambda **kwargs: page_payload
            queued = mod.enqueue_ssot_write(
                conn,
                cfg,
                agent_id="agent-alex",
                operation="update",
                target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                payload={"properties": {"Status": {"status": {"name": "Blocked"}}}},
                requested_by_actor="agent-alex",
            )
            update_calls: list[dict] = []

            def fake_update_notion_page(**kwargs):
                update_calls.append(kwargs)
                return {"id": kwargs["page_id"], "properties": kwargs["payload"]["properties"]}

            mod.update_notion_page = fake_update_notion_page
            approved = mod.approve_ssot_pending_write(
                conn,
                cfg,
                pending_id=str(queued["pending_id"]),
                surface="test",
                actor="operator",
            )
            expect(approved["status"] == "applied", approved)
            expect(len(update_calls) == 1, str(update_calls))
            expect(update_calls[0]["page_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", str(update_calls))
            user_notification = conn.execute(
                """
                SELECT target_kind, target_id, channel_kind, message
                FROM notification_outbox
                WHERE target_kind = 'user-agent'
                  AND target_id = 'agent-alex'
                  AND channel_kind = 'ssot-approval'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            expect(user_notification is not None, "expected approval to notify the user agent")
            expect("approved" in str(user_notification["message"]).lower(), str(dict(user_notification)))
            trigger_path = root / "state" / "activation-triggers" / "agent-alex.json"
            expect(trigger_path.is_file(), f"expected user-agent refresh trigger at {trigger_path}")
            trigger_payload = json.loads(trigger_path.read_text(encoding="utf-8"))
            expect(trigger_payload["status"] == "refresh", trigger_payload)
            expect(str(queued["pending_id"]) in trigger_payload["note"], trigger_payload)
            decisions = [
                str(row["decision"])
                for row in conn.execute(
                    "SELECT decision FROM ssot_access_audit ORDER BY id DESC LIMIT 3"
                ).fetchall()
            ]
            expect("allow" in decisions and "approve" in decisions and "queue" in decisions, str(decisions))
            print("PASS test_ssot_pending_write_approval_applies_queued_update")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_pending_write_approval_requires_current_verified_write_mode() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_pending_approval_gate_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.retrieve_notion_page = lambda **kwargs: {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "properties": {
                    "Owner": {
                        "people": [
                            {
                                "id": "22222222-2222-2222-2222-222222222222",
                                "name": "Somebody Else",
                            }
                        ]
                    }
                },
            }
            queued = mod.enqueue_ssot_write(
                conn,
                cfg,
                agent_id="agent-alex",
                operation="update",
                target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                payload={"properties": {"Status": {"status": {"name": "Blocked"}}}},
                requested_by_actor="agent-alex",
            )
            conn.execute(
                """
                UPDATE agent_identity
                SET notion_user_id = '',
                    notion_user_email = '',
                    verification_status = 'unverified',
                    write_mode = 'read_only',
                    verified_at = NULL
                WHERE unix_user = 'alex'
                """
            )
            conn.commit()
            update_calls: list[dict] = []

            def fake_update_notion_page(**kwargs):
                update_calls.append(kwargs)
                return {"id": kwargs["page_id"], "properties": kwargs["payload"]["properties"]}

            mod.update_notion_page = fake_update_notion_page
            try:
                mod.approve_ssot_pending_write(
                    conn,
                    cfg,
                    pending_id=str(queued["pending_id"]),
                    surface="test",
                    actor="operator",
                )
            except PermissionError as exc:
                expect("verified_limited" in str(exc), str(exc))
            else:
                raise AssertionError("expected approval replay to fail once the identity is no longer verified_limited")
            expect(len(update_calls) == 0, str(update_calls))
            pending = conn.execute(
                """
                SELECT status, decision_surface, decided_at
                FROM ssot_pending_writes
                WHERE pending_id = ?
                """,
                (str(queued["pending_id"]),),
            ).fetchone()
            expect(pending is not None and pending["status"] == "pending", str(dict(pending) if pending else {}))
            expect(str(pending["decision_surface"] or "") == "", str(dict(pending)))
            expect(str(pending["decided_at"] or "") == "", str(dict(pending)))
            audit = conn.execute(
                "SELECT decision, reason FROM ssot_access_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            expect(audit is not None and audit["decision"] == "deny", str(dict(audit) if audit else {}))
            expect("approval time" in str(audit["reason"]).lower(), str(dict(audit)))
            print("PASS test_ssot_pending_write_approval_requires_current_verified_write_mode")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_pending_write_denial_marks_pending_row() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_pending_deny_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.retrieve_notion_page = lambda **kwargs: {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "properties": {
                    "Owner": {
                        "people": [
                            {
                                "id": "22222222-2222-2222-2222-222222222222",
                                "name": "Somebody Else",
                            }
                        ]
                    }
                },
            }
            queued = mod.enqueue_ssot_write(
                conn,
                cfg,
                agent_id="agent-alex",
                operation="update",
                target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                payload={"properties": {"Status": {"status": {"name": "Blocked"}}}},
                requested_by_actor="agent-alex",
            )
            denied = mod.deny_ssot_pending_write(
                conn,
                cfg,
                pending_id=str(queued["pending_id"]),
                surface="test",
                actor="operator",
                reason="leave this with the owner",
            )
            expect(denied["status"] == "denied", denied)
            expect(str(denied["decision_note"]) == "leave this with the owner", denied)
            user_notification = conn.execute(
                """
                SELECT target_kind, target_id, channel_kind, message
                FROM notification_outbox
                WHERE target_kind = 'user-agent'
                  AND target_id = 'agent-alex'
                  AND channel_kind = 'ssot-approval'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            expect(user_notification is not None, "expected denial to notify the user agent")
            expect("denied" in str(user_notification["message"]).lower(), str(dict(user_notification)))
            trigger_path = root / "state" / "activation-triggers" / "agent-alex.json"
            expect(trigger_path.is_file(), f"expected user-agent refresh trigger at {trigger_path}")
            trigger_payload = json.loads(trigger_path.read_text(encoding="utf-8"))
            expect(trigger_payload["status"] == "refresh", trigger_payload)
            expect(str(queued["pending_id"]) in trigger_payload["note"], trigger_payload)
            audit = conn.execute(
                "SELECT decision, reason FROM ssot_access_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            expect(audit is not None and audit["decision"] == "deny", str(dict(audit) if audit else {}))
            expect("leave this with the owner" in str(audit["reason"]).lower(), str(dict(audit)))
            print("PASS test_ssot_pending_write_denial_marks_pending_row")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_pending_write_expiry_blocks_approval_replay() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_pending_expiry_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.retrieve_notion_page = lambda **kwargs: {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "properties": {
                    "Owner": {
                        "people": [
                            {
                                "id": "22222222-2222-2222-2222-222222222222",
                                "name": "Somebody Else",
                            }
                        ]
                    }
                },
            }
            queued = mod.enqueue_ssot_write(
                conn,
                cfg,
                agent_id="agent-alex",
                operation="update",
                target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                payload={"properties": {"Status": {"status": {"name": "Blocked"}}}},
                requested_by_actor="agent-alex",
            )
            conn.execute(
                "UPDATE ssot_pending_writes SET expires_at = ? WHERE pending_id = ?",
                (
                    mod.auto_provision_stale_before_iso(600),
                    str(queued["pending_id"]),
                ),
            )
            conn.commit()
            update_calls: list[dict] = []

            def fake_update_notion_page(**kwargs):
                update_calls.append(kwargs)
                return {"id": kwargs["page_id"], "properties": kwargs["payload"]["properties"]}

            mod.update_notion_page = fake_update_notion_page
            try:
                mod.approve_ssot_pending_write(
                    conn,
                    cfg,
                    pending_id=str(queued["pending_id"]),
                    surface="test",
                    actor="operator",
                )
            except PermissionError as exc:
                expect("expired" in str(exc).lower(), str(exc))
            else:
                raise AssertionError("expected expired pending SSOT write to refuse approval replay")
            expect(len(update_calls) == 0, str(update_calls))
            pending = conn.execute(
                """
                SELECT status, decision_surface, decided_by_actor, decision_note
                FROM ssot_pending_writes
                WHERE pending_id = ?
                """,
                (str(queued["pending_id"]),),
            ).fetchone()
            expect(pending is not None and pending["status"] == "expired", str(dict(pending) if pending else {}))
            expect(str(pending["decision_surface"] or "") == "expiry", str(dict(pending)))
            expect(str(pending["decided_by_actor"] or "") == "system", str(dict(pending)))
            expect("expired before user approval" in str(pending["decision_note"] or "").lower(), str(dict(pending)))
            audit = conn.execute(
                "SELECT decision, reason FROM ssot_access_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            expect(audit is not None and audit["decision"] == "deny", str(dict(audit) if audit else {}))
            expect("could not be approved" in str(audit["reason"]).lower(), str(dict(audit)))
            print("PASS test_ssot_pending_write_expiry_blocks_approval_replay")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_list_agent_ssot_pending_writes_stays_scoped_and_expires_stale_rows() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_pending_scope_list_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-casey", unix_user="casey")
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            casey_pending, _ = mod.request_ssot_pending_write(
                conn,
                agent_id="agent-casey",
                unix_user="casey",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                operation="update",
                target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                payload={"properties": {"Status": {"status": {"name": "Blocked"}}}},
                requested_by_actor="agent-casey",
                request_source="scope-mismatch",
                request_reason="outside edit lane",
                owner_identity="22222222-2222-2222-2222-222222222222",
                owner_source="ownership-mismatch",
                ttl_seconds=cfg.ssot_pending_write_ttl_seconds,
            )
            alex_pending, _ = mod.request_ssot_pending_write(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                notion_user_id="33333333-3333-3333-3333-333333333333",
                operation="append",
                target_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                payload={"children": [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": []}}]},
                requested_by_actor="agent-alex",
                request_source="scope-mismatch",
                request_reason="outside edit lane",
                owner_identity="44444444-4444-4444-4444-444444444444",
                owner_source="ownership-mismatch",
                ttl_seconds=cfg.ssot_pending_write_ttl_seconds,
            )
            conn.execute(
                "UPDATE ssot_pending_writes SET expires_at = ? WHERE pending_id = ?",
                (
                    mod.auto_provision_stale_before_iso(600),
                    str(casey_pending["pending_id"]),
                ),
            )
            conn.commit()
            casey_rows = mod.list_agent_ssot_pending_writes(
                conn,
                agent_id="agent-casey",
                status="pending",
                limit=10,
            )
            expect(casey_rows == [], str(casey_rows))
            alex_rows = mod.list_agent_ssot_pending_writes(
                conn,
                agent_id="agent-alex",
                status="pending",
                limit=10,
            )
            expect(len(alex_rows) == 1, str(alex_rows))
            expect(str(alex_rows[0]["pending_id"]) == str(alex_pending["pending_id"]), str(alex_rows))
            expired_rows = mod.list_ssot_pending_writes(
                conn,
                status="expired",
                agent_id="agent-casey",
                limit=10,
            )
            expect(len(expired_rows) == 1, str(expired_rows))
            expect(str(expired_rows[0]["pending_id"]) == str(casey_pending["pending_id"]), str(expired_rows))
            expect(mod.count_ssot_pending_writes(conn, status="pending", agent_id="agent-alex") == 1, "expected alex pending count to remain 1")
            expect(mod.count_ssot_pending_writes(conn, status="pending", agent_id="agent-casey") == 0, "expected casey pending count to drop to 0 after expiry")
            print("PASS test_list_agent_ssot_pending_writes_stays_scoped_and_expires_stale_rows")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_read_denies_name_collision() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_name_collision_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.resolve_notion_target = lambda **kwargs: {
                "kind": "page",
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            }
            mod.retrieve_notion_page = lambda **kwargs: {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "created_by": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "name": "Alex",
                },
            }
            try:
                mod.read_ssot(
                    conn,
                    cfg,
                    agent_id="agent-alex",
                    target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    query={},
                    include_markdown=False,
                    requested_by_actor="agent-alex",
                )
            except PermissionError as exc:
                expect("outside the caller" in str(exc).lower(), str(exc))
            else:
                raise AssertionError("expected name collision page read to be denied")
            audit = conn.execute(
                "SELECT decision, reason FROM ssot_access_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            expect(audit is not None and audit["decision"] == "deny", str(dict(audit) if audit else {}))
            print("PASS test_ssot_read_denies_name_collision")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_read_denies_changed_by_only_match() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_changed_by_only_acl_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.resolve_notion_target = lambda **kwargs: {"kind": "page", "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}
            mod.retrieve_notion_page = lambda **kwargs: {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "properties": {
                    "Changed By": {
                        "people": [{"id": "11111111-1111-1111-1111-111111111111"}]
                    }
                },
            }
            try:
                mod.read_ssot(
                    conn,
                    cfg,
                    agent_id="agent-alex",
                    target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    query={},
                    include_markdown=False,
                    requested_by_actor="agent-alex",
                )
            except PermissionError as exc:
                expect("outside the caller" in str(exc).lower(), str(exc))
            else:
                raise AssertionError("expected Changed By alone to be insufficient for ACL")
            print("PASS test_ssot_read_denies_changed_by_only_match")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_write_denies_suspended_identity() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_write_suspended_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
                suspended_at=mod.utc_now_iso(),
            )
            try:
                mod.enqueue_ssot_write(
                    conn,
                    cfg,
                    agent_id="agent-alex",
                    operation="insert",
                    target_id="12345678-90ab-cdef-1234-567890abcdef",
                    payload={
                        "properties": {
                            "Owner": {"people": [{"id": "11111111-1111-1111-1111-111111111111"}]}
                        }
                    },
                    requested_by_actor="agent-alex",
                )
            except PermissionError as exc:
                expect("suspended" in str(exc).lower(), str(exc))
            else:
                raise AssertionError("expected suspended identity write to be denied")
            audit = conn.execute(
                "SELECT decision, reason FROM ssot_access_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            expect(audit is not None and audit["decision"] == "deny", str(dict(audit) if audit else {}))
            expect("suspended" in str(audit["reason"]).lower(), str(dict(audit)))
            print("PASS test_ssot_write_denies_suspended_identity")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_principal_fails_closed_when_identity_registry_errors() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_ssot_registry_fail_closed_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        original_get_identity = mod.get_agent_identity
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")

            def boom(*args, **kwargs):
                raise mod.sqlite3.OperationalError("boom")

            mod.get_agent_identity = boom
            try:
                mod.read_ssot(
                    conn,
                    cfg,
                    agent_id="agent-alex",
                    target_id="",
                    query={},
                    include_markdown=False,
                    requested_by_actor="agent-alex",
                )
            except PermissionError as exc:
                expect("identity registry" in str(exc).lower(), str(exc))
            else:
                raise AssertionError("expected registry lookup failure to fail closed")
            audit = conn.execute(
                "SELECT decision, reason FROM ssot_access_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            expect(audit is not None and audit["decision"] == "deny", str(dict(audit) if audit else {}))
            expect("identity registry" in str(audit["reason"]).lower(), str(dict(audit)))
            print("PASS test_ssot_principal_fails_closed_when_identity_registry_errors")
        finally:
            mod.get_agent_identity = original_get_identity
            os.environ.clear()
            os.environ.update(old_env)


def test_notion_batcher_hydrates_entity_before_routing() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_notion_batcher_hydrate_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="alex@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.store_notion_event(
                conn,
                event_id="event-1",
                event_type="page.properties_updated",
                payload={
                    "id": "webhook-event-1",
                    "entity": {
                        "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "type": "page",
                    },
                },
            )
            retrieved: list[str] = []

            def fake_retrieve_notion_page(**kwargs):
                retrieved.append(kwargs["page_id"])
                return {
                    "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "object": "page",
                    "properties": {
                        "Name": {
                            "type": "title",
                            "title": [{"plain_text": "Launch checklist"}],
                        },
                        "Owner": {
                            "people": [
                                {"id": "11111111-1111-1111-1111-111111111111"}
                            ]
                        }
                    },
                }

            mod.retrieve_notion_page = fake_retrieve_notion_page
            result = mod.process_pending_notion_events(conn)
            expect(retrieved == ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"], str(retrieved))
            expect(result["processed"] == 1, result)
            expect(result["nudges"].get("agent-alex") == 1, result)
            agent_notice = conn.execute(
                """
                SELECT COUNT(*) AS c, message, extra_json
                FROM notification_outbox
                WHERE target_kind = 'user-agent' AND channel_kind = 'notion-webhook' AND target_id = 'agent-alex'
                """
            ).fetchone()
            expect(int(agent_notice["c"] if agent_notice else 0) == 1, str(dict(agent_notice) if agent_notice else {}))
            expect("Notion digest: 1 scoped update" in str(agent_notice["message"] or ""), str(dict(agent_notice)))
            expect("properties updated on Launch checklist" in str(agent_notice["message"] or ""), str(dict(agent_notice)))
            expect("Check live details with notion.query/notion.fetch, or verified ssot.read for scoped brokered targets, before acting" in str(agent_notice["message"] or ""), str(dict(agent_notice)))
            extra = json.loads(str(agent_notice["extra_json"] or "{}"))
            expect(extra["events"][0]["target"] == "Launch checklist (page aaaaaaaa)", str(extra))
            expect(extra["events"][0]["signal_label"] == "work update", str(extra))
            fanout = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM notification_outbox
                WHERE target_kind = 'curator' AND channel_kind = 'brief-fanout' AND target_id = 'agent-alex'
                """
            ).fetchone()
            expect(int(fanout["c"] if fanout else 0) == 1, str(dict(fanout) if fanout else {}))
            reindex_notice = conn.execute(
                """
                SELECT target_id, extra_json
                FROM notification_outbox
                WHERE target_kind = 'curator' AND channel_kind = 'notion-reindex'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            expect(reindex_notice is not None, "expected notion reindex notification to be queued")
            expect(str(reindex_notice["target_id"] or "") == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", str(dict(reindex_notice)))
            expect("page" in str(reindex_notice["extra_json"] or ""), str(dict(reindex_notice)))
            row = conn.execute(
                "SELECT batch_status FROM notion_webhook_events WHERE event_id = 'event-1'"
            ).fetchone()
            expect(row is not None and row["batch_status"] == "processed", str(dict(row) if row else {}))
            expect(result["reindex_entities"] == 1, result)
            print("PASS test_notion_batcher_hydrates_entity_before_routing")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_notion_batcher_ignores_stale_verified_identity_without_active_agent() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_notion_batcher_stale_identity_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-stale",
                unix_user="stale",
                human_display_name="Stale User",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="stale@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
            )
            mod.store_notion_event(
                conn,
                event_id="event-stale",
                event_type="page.created",
                payload={
                    "id": "webhook-event-stale",
                    "entity": {
                        "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                        "type": "page",
                    },
                    "created_by": {
                        "id": "11111111-1111-1111-1111-111111111111",
                    },
                },
            )

            result = mod.process_pending_notion_events(conn)
            expect(result["processed"] == 1, result)
            expect(result["nudges"] == {}, result)
            expect(result["unresolved_event_ids"] == ["event-stale"], result)
            stale_outbox = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM notification_outbox
                WHERE target_id = 'agent-stale'
                  AND channel_kind IN ('notion-webhook', 'brief-fanout')
                """
            ).fetchone()
            expect(int(stale_outbox["c"] if stale_outbox else 0) == 0, str(dict(stale_outbox) if stale_outbox else {}))
            print("PASS test_notion_batcher_ignores_stale_verified_identity_without_active_agent")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_notion_batcher_retries_when_hydration_fails() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_notion_batcher_retry_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            mod.store_notion_event(
                conn,
                event_id="event-2",
                event_type="page.properties_updated",
                payload={
                    "id": "webhook-event-2",
                    "entity": {
                        "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                        "type": "page",
                    },
                },
            )

            def boom(**kwargs):
                raise RuntimeError("notion temporarily unavailable")

            mod.retrieve_notion_page = boom
            result = mod.process_pending_notion_events(conn)
            expect(result["processed"] == 0, result)
            row = conn.execute(
                "SELECT batch_status, attempt_count, last_error FROM notion_webhook_events WHERE event_id = 'event-2'"
            ).fetchone()
            expect(row is not None and row["batch_status"] == "pending", str(dict(row) if row else {}))
            expect(int(row["attempt_count"] if row is not None else 0) == 1, str(dict(row) if row else {}))
            expect("hydration failed" in str(row["last_error"] or ""), str(dict(row) if row else {}))
            print("PASS test_notion_batcher_retries_when_hydration_fails")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_notion_batcher_marks_event_failed_after_retry_budget() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_notion_batcher_retry_budget_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            mod.store_notion_event(
                conn,
                event_id="event-3",
                event_type="page.properties_updated",
                payload={
                    "id": "webhook-event-3",
                    "entity": {
                        "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                        "type": "page",
                    },
                },
            )
            conn.execute(
                """
                UPDATE notion_webhook_events
                SET attempt_count = ?
                WHERE event_id = 'event-3'
                """,
                (mod.NOTION_WEBHOOK_EVENT_MAX_ATTEMPTS - 1,),
            )
            conn.commit()

            def boom(**kwargs):
                raise RuntimeError("notion still unavailable")

            mod.retrieve_notion_page = boom
            result = mod.process_pending_notion_events(conn)
            expect(result["processed"] == 0, result)
            expect(result["failed_event_ids"] == ["event-3"], result)
            row = conn.execute(
                "SELECT batch_status, attempt_count, last_error, processed_at FROM notion_webhook_events WHERE event_id = 'event-3'"
            ).fetchone()
            expect(row is not None and row["batch_status"] == "failed", str(dict(row) if row else {}))
            expect(
                int(row["attempt_count"] if row is not None else 0) == mod.NOTION_WEBHOOK_EVENT_MAX_ATTEMPTS,
                str(dict(row) if row else {}),
            )
            expect("hydration failed" in str(row["last_error"] or ""), str(dict(row) if row else {}))
            expect(str(row["processed_at"] or "").strip() != "", str(dict(row) if row else {}))
            refresh_job = conn.execute(
                "SELECT last_status, last_note FROM refresh_jobs ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            expect(refresh_job is not None and refresh_job["last_status"] == "fail", str(dict(refresh_job) if refresh_job else {}))
            expect("SLO targets" in str(refresh_job["last_note"] or ""), str(dict(refresh_job)))
            print("PASS test_notion_batcher_marks_event_failed_after_retry_budget")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_notion_batcher_verifies_claim_page_event() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_notion_batcher_claim_verify_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                verification_status="unverified",
                write_mode="read_only",
            )
            now = mod.utc_now_iso()
            conn.execute(
                """
                INSERT INTO notion_identity_claims (
                  claim_id, session_id, agent_id, unix_user, claimed_notion_email,
                  notion_page_id, notion_page_url, status, failure_reason,
                  verified_notion_user_id, verified_notion_email, created_at, updated_at, expires_at, verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', '', '', '', ?, ?, ?, NULL)
                """,
                (
                    "nclaim_test",
                    "onb_test",
                    "agent-alex",
                    "alex",
                    "alex@example.com",
                    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "https://www.notion.so/claim",
                    now,
                    now,
                    (mod.utc_now() + mod.dt.timedelta(hours=1)).replace(microsecond=0).isoformat(),
                ),
            )
            conn.commit()
            mod.store_notion_event(
                conn,
                event_id="event-claim-1",
                event_type="page.properties_updated",
                payload={
                    "entity": {
                        "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "type": "page",
                    }
                },
            )

            mod.retrieve_notion_page = lambda **kwargs: {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "last_edited_by": {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "type": "person",
                    "person": {"email": "alex@example.com"},
                },
                "properties": {},
            }
            update_calls: list[dict[str, object]] = []

            def fake_update_notion_page(**kwargs):
                update_calls.append(kwargs)
                return {
                    "id": kwargs["page_id"],
                    **dict(kwargs.get("payload") or {}),
                }

            mod.update_notion_page = fake_update_notion_page

            result = mod.process_pending_notion_events(conn)
            expect(result["verified_claims"] == 1, result)
            claim = mod.get_notion_identity_claim(conn, claim_id="nclaim_test")
            expect(claim is not None and claim["status"] == "verified", str(claim))
            trash_calls = [
                call for call in update_calls
                if dict(call.get("payload") or {}).get("in_trash") is True
            ]
            expect(len(trash_calls) == 1, str(update_calls))
            expect(trash_calls[0]["page_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", str(update_calls))
            identity = mod.get_agent_identity(conn, agent_id="agent-alex", unix_user="alex")
            expect(identity is not None and identity["verification_status"] == "verified", str(identity))
            audit = conn.execute(
                """
                SELECT decision, reason, operation
                FROM ssot_access_audit
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            expect(audit is not None and audit["decision"] == "allow", str(dict(audit) if audit else {}))
            expect(str(audit["operation"] or "") == "verify-identity", str(dict(audit)))
            queued = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM notification_outbox
                WHERE target_kind = 'curator' AND channel_kind = 'brief-fanout' AND target_id = 'agent-alex'
                """
            ).fetchone()
            expect(int(queued["c"] if queued else 0) >= 1, str(dict(queued) if queued else {}))
            print("PASS test_notion_batcher_verifies_claim_page_event")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_notion_batcher_verifies_claim_page_event_when_page_exposes_user_id_only() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_notion_batcher_claim_verify_user_object_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                verification_status="unverified",
                write_mode="read_only",
            )
            now = mod.utc_now_iso()
            conn.execute(
                """
                INSERT INTO notion_identity_claims (
                  claim_id, session_id, agent_id, unix_user, claimed_notion_email,
                  notion_page_id, notion_page_url, status, failure_reason,
                  verified_notion_user_id, verified_notion_email, created_at, updated_at, expires_at, verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', '', '', '', ?, ?, ?, NULL)
                """,
                (
                    "nclaim_user_object",
                    "onb_test",
                    "agent-alex",
                    "alex",
                    "alex@example.com",
                    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "https://www.notion.so/claim",
                    now,
                    now,
                    (mod.utc_now() + mod.dt.timedelta(hours=1)).replace(microsecond=0).isoformat(),
                ),
            )
            conn.commit()
            mod.store_notion_event(
                conn,
                event_id="event-claim-user-object",
                event_type="page.properties_updated",
                payload={
                    "entity": {
                        "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "type": "page",
                    }
                },
            )

            mod.retrieve_notion_page = lambda **kwargs: {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "last_edited_by": {
                    "object": "user",
                    "id": "11111111-1111-1111-1111-111111111111",
                },
                "properties": {},
            }
            mod.retrieve_notion_user = lambda **kwargs: {
                "object": "user",
                "id": "11111111-1111-1111-1111-111111111111",
                "type": "person",
                "person": {"email": "alex@example.com"},
            }
            update_calls: list[dict[str, object]] = []

            def fake_update_notion_page(**kwargs):
                update_calls.append(kwargs)
                return {
                    "id": kwargs["page_id"],
                    **dict(kwargs.get("payload") or {}),
                }

            mod.update_notion_page = fake_update_notion_page

            result = mod.process_pending_notion_events(conn)
            expect(result["verified_claims"] == 1, result)
            claim = mod.get_notion_identity_claim(conn, claim_id="nclaim_user_object")
            expect(claim is not None and claim["status"] == "verified", str(claim))
            trash_calls = [
                call for call in update_calls
                if dict(call.get("payload") or {}).get("in_trash") is True
            ]
            expect(len(trash_calls) == 1, str(update_calls))
            expect(trash_calls[0]["page_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", str(update_calls))
            identity = mod.get_agent_identity(conn, agent_id="agent-alex", unix_user="alex")
            expect(identity is not None and identity["verification_status"] == "verified", str(identity))
            print("PASS test_notion_batcher_verifies_claim_page_event_when_page_exposes_user_id_only")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_notion_batcher_rejects_claim_page_edit_from_wrong_email() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_notion_batcher_claim_wrong_email_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                verification_status="unverified",
                write_mode="read_only",
            )
            now = mod.utc_now_iso()
            conn.execute(
                """
                INSERT INTO notion_identity_claims (
                  claim_id, session_id, agent_id, unix_user, claimed_notion_email,
                  notion_page_id, notion_page_url, status, failure_reason,
                  verified_notion_user_id, verified_notion_email, created_at, updated_at, expires_at, verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', '', '', '', ?, ?, ?, NULL)
                """,
                (
                    "nclaim_wrong_email",
                    "onb_test",
                    "agent-alex",
                    "alex",
                    "alex@example.com",
                    "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                    "https://www.notion.so/claim",
                    now,
                    now,
                    (mod.utc_now() + mod.dt.timedelta(hours=1)).replace(microsecond=0).isoformat(),
                ),
            )
            conn.commit()
            mod.store_notion_event(
                conn,
                event_id="event-claim-wrong-email",
                event_type="page.properties_updated",
                payload={
                    "entity": {
                        "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                        "type": "page",
                    }
                },
            )
            mod.retrieve_notion_page = lambda **kwargs: {
                "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "last_edited_by": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "type": "person",
                    "person": {"email": "wrong@example.com"},
                },
                "properties": {},
            }
            update_calls: list[dict[str, object]] = []

            def fake_update_notion_page(**kwargs):
                update_calls.append(kwargs)
                return {
                    "id": kwargs["page_id"],
                    **dict(kwargs.get("payload") or {}),
                }

            mod.update_notion_page = fake_update_notion_page

            result = mod.process_pending_notion_events(conn)
            expect(result["verified_claims"] == 0, result)
            claim = mod.get_notion_identity_claim(conn, claim_id="nclaim_wrong_email")
            expect(claim is not None and claim["status"] == "pending", str(claim))
            expect(update_calls == [], str(update_calls))
            expect("different notion email" in str(claim.get("failure_reason") or "").lower(), str(claim))
            identity = mod.get_agent_identity(conn, agent_id="agent-alex", unix_user="alex")
            expect(identity is not None and identity["verification_status"] == "unverified", str(identity))
            audit = conn.execute(
                """
                SELECT decision, reason, operation
                FROM ssot_access_audit
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            expect(audit is not None and audit["decision"] == "deny", str(dict(audit) if audit else {}))
            expect(str(audit["operation"] or "") == "verify-identity", str(dict(audit)))
            expect("different notion email" in str(audit["reason"] or "").lower(), str(dict(audit)))
            print("PASS test_notion_batcher_rejects_claim_page_edit_from_wrong_email")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_notion_batcher_accepts_claim_page_edit_via_identity_override() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_notion_batcher_claim_override_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-alex", unix_user="alex")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-alex",
                unix_user="alex",
                human_display_name="Alex",
                verification_status="unverified",
                write_mode="read_only",
            )
            mod.upsert_notion_identity_override(
                conn,
                unix_user="alex",
                notion_user_id="22222222-2222-2222-2222-222222222222",
                notion_user_email="alias@example.com",
                notes="approved workspace alias",
            )
            now = mod.utc_now_iso()
            conn.execute(
                """
                INSERT INTO notion_identity_claims (
                  claim_id, session_id, agent_id, unix_user, claimed_notion_email,
                  notion_page_id, notion_page_url, status, failure_reason,
                  verified_notion_user_id, verified_notion_email, created_at, updated_at, expires_at, verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', '', '', '', ?, ?, ?, NULL)
                """,
                (
                    "nclaim_override",
                    "onb_test",
                    "agent-alex",
                    "alex",
                    "alex@example.com",
                    "cccccccc-cccc-cccc-cccc-cccccccccccc",
                    "https://www.notion.so/claim",
                    now,
                    now,
                    (mod.utc_now() + mod.dt.timedelta(hours=1)).replace(microsecond=0).isoformat(),
                ),
            )
            conn.commit()
            mod.store_notion_event(
                conn,
                event_id="event-claim-override",
                event_type="page.properties_updated",
                payload={
                    "entity": {
                        "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                        "type": "page",
                    }
                },
            )
            mod.retrieve_notion_page = lambda **kwargs: {
                "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                "last_edited_by": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "type": "person",
                    "person": {"email": "alias@example.com"},
                },
                "properties": {},
            }
            update_calls: list[dict[str, object]] = []

            def fake_update_notion_page(**kwargs):
                update_calls.append(kwargs)
                return {
                    "id": kwargs["page_id"],
                    **dict(kwargs.get("payload") or {}),
                }

            mod.update_notion_page = fake_update_notion_page

            result = mod.process_pending_notion_events(conn)
            expect(result["verified_claims"] == 1, result)
            claim = mod.get_notion_identity_claim(conn, claim_id="nclaim_override")
            expect(claim is not None and claim["status"] == "verified", str(claim))
            trash_calls = [
                call for call in update_calls
                if dict(call.get("payload") or {}).get("in_trash") is True
            ]
            expect(len(trash_calls) == 1, str(update_calls))
            expect(trash_calls[0]["page_id"] == "cccccccc-cccc-cccc-cccc-cccccccccccc", str(update_calls))
            identity = mod.get_agent_identity(conn, agent_id="agent-alex", unix_user="alex")
            expect(identity is not None and identity["verification_status"] == "verified", str(identity))
            print("PASS test_notion_batcher_accepts_claim_page_edit_via_identity_override")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_connect_db_enables_sqlite_wal_and_busy_timeout()
    test_ssot_read_denies_database_query_until_verified()
    test_ssot_read_scopes_database_results_to_verified_user()
    test_ssot_read_scopes_database_results_to_identity_override()
    test_ssot_write_requires_verified_write_mode()
    test_ensure_notion_verification_database_repairs_missing_managed_schema()
    test_ensure_notion_verification_database_does_not_recreate_on_wrong_type_drift()
    test_start_notion_identity_claim_creates_page_under_shared_parent()
    test_ssot_write_applies_verified_owned_update()
    test_ssot_write_applies_verified_owned_append()
    test_ssot_write_applies_verified_owned_insert()
    test_ssot_write_allows_child_page_insert_under_verified_parent_without_owner_property()
    test_ssot_database_insert_outside_lane_queues_for_user_approval_then_applies()
    test_ssot_create_database_under_shared_root_queues_then_inherits_parent_access()
    test_ssot_create_database_rejects_payload_parent_to_avoid_private_workspace_creation()
    test_ssot_create_page_under_shared_root_queues_then_inherits_parent_access()
    test_ssot_create_page_rejects_payload_parent_to_avoid_private_workspace_creation()
    test_ssot_create_page_normalizer_fails_closed_on_sloppy_agent_payloads()
    test_ssot_database_and_append_normalizers_reject_sloppy_agent_payloads()
    test_ssot_preflight_reports_write_vs_user_approval()
    test_ssot_create_payload_validation_happens_before_approval_queueing()
    test_ssot_write_allows_page_update_from_prior_agent_history()
    test_ssot_write_queues_prior_agent_history_when_page_has_other_owner()
    test_ssot_write_queues_insert_under_out_of_scope_parent_page()
    test_ssot_write_applies_without_changed_by_property()
    test_ssot_write_fails_closed_when_changed_by_schema_lookup_fails()
    test_ssot_write_logs_failure_when_notion_apply_raises()
    test_ssot_read_denies_suspended_identity()
    test_ssot_write_queues_cross_owner_update()
    test_ssot_pending_write_approval_applies_queued_update()
    test_ssot_pending_write_approval_requires_current_verified_write_mode()
    test_ssot_pending_write_denial_marks_pending_row()
    test_ssot_pending_write_expiry_blocks_approval_replay()
    test_list_agent_ssot_pending_writes_stays_scoped_and_expires_stale_rows()
    test_ssot_read_denies_name_collision()
    test_ssot_read_denies_changed_by_only_match()
    test_ssot_write_denies_suspended_identity()
    test_ssot_principal_fails_closed_when_identity_registry_errors()
    test_notion_batcher_hydrates_entity_before_routing()
    test_notion_batcher_ignores_stale_verified_identity_without_active_agent()
    test_notion_batcher_retries_when_hydration_fails()
    test_notion_batcher_marks_event_failed_after_retry_budget()
    test_notion_batcher_verifies_claim_page_event()
    test_notion_batcher_verifies_claim_page_event_when_page_exposes_user_id_only()
    test_notion_batcher_rejects_claim_page_edit_from_wrong_email()
    test_notion_batcher_accepts_claim_page_edit_via_identity_override()
    print("PASS all 45 ssot broker tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
