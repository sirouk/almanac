#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTROL_PY = REPO / "python" / "almanac_control.py"


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


def test_ssot_read_denies_database_query_until_verified() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_ssot_read_deny_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-sirouk", unix_user="sirouk")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-sirouk",
                unix_user="sirouk",
                human_display_name="Chris",
                verification_status="unverified",
                write_mode="read_only",
            )
            try:
                mod.read_ssot(
                    conn,
                    cfg,
                    agent_id="agent-sirouk",
                    target_id="",
                    query={},
                    include_markdown=False,
                    requested_by_actor="agent-sirouk",
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
    mod = load_module(CONTROL_PY, "almanac_control_ssot_read_scope_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-sirouk", unix_user="sirouk")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-sirouk",
                unix_user="sirouk",
                human_display_name="Chris",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="chris@example.com",
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
                                            "name": "Chris",
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
                agent_id="agent-sirouk",
                target_id="",
                query={},
                include_markdown=False,
                requested_by_actor="agent-sirouk",
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


def test_ssot_write_requires_verified_write_mode() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_ssot_write_gate_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-sirouk", unix_user="sirouk")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-sirouk",
                unix_user="sirouk",
                human_display_name="Chris",
                verification_status="unverified",
                write_mode="read_only",
            )
            try:
                mod.enqueue_ssot_write(
                    conn,
                    cfg,
                    agent_id="agent-sirouk",
                    operation="insert",
                    target_id="12345678-90ab-cdef-1234-567890abcdef",
                    payload={"properties": {"Owner": {"people": [{"name": "Chris"}]}}},
                    requested_by_actor="agent-sirouk",
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


def test_ssot_write_applies_verified_owned_update() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_ssot_write_apply_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-sirouk", unix_user="sirouk")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-sirouk",
                unix_user="sirouk",
                human_display_name="Chris",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="chris@example.com",
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
                                "name": "Chris",
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
                agent_id="agent-sirouk",
                operation="update",
                target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                payload={
                    "properties": {
                        "Status": {"status": {"name": "In Progress"}},
                        "Changed By": {"people": [{"id": "99999999-9999-9999-9999-999999999999"}]},
                    }
                },
                requested_by_actor="agent-sirouk",
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


def test_ssot_write_applies_verified_owned_insert() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_ssot_insert_apply_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-sirouk", unix_user="sirouk")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-sirouk",
                unix_user="sirouk",
                human_display_name="Chris",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="chris@example.com",
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
                agent_id="agent-sirouk",
                operation="insert",
                target_id="12345678-90ab-cdef-1234-567890abcdef",
                payload={
                    "properties": {
                        "Owner": {"people": [{"id": "11111111-1111-1111-1111-111111111111"}]},
                        "Changed By": {"people": [{"id": "99999999-9999-9999-9999-999999999999"}]},
                    }
                },
                requested_by_actor="agent-sirouk",
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


def test_ssot_write_applies_without_changed_by_property() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_ssot_insert_without_changed_by_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-sirouk", unix_user="sirouk")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-sirouk",
                unix_user="sirouk",
                human_display_name="Chris",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="chris@example.com",
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
                agent_id="agent-sirouk",
                operation="insert",
                target_id="12345678-90ab-cdef-1234-567890abcdef",
                payload={"properties": {"Owner": {"people": [{"id": "11111111-1111-1111-1111-111111111111"}]}}},
                requested_by_actor="agent-sirouk",
            )
            expect(result["applied"] is True, result)
            expect("Changed By" not in create_calls[0]["payload"]["properties"], str(create_calls[0]["payload"]))
            print("PASS test_ssot_write_applies_without_changed_by_property")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_write_fails_closed_when_changed_by_schema_lookup_fails() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_ssot_changed_by_schema_fail_closed_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-sirouk", unix_user="sirouk")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-sirouk",
                unix_user="sirouk",
                human_display_name="Chris",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="chris@example.com",
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
                    agent_id="agent-sirouk",
                    operation="insert",
                    target_id="12345678-90ab-cdef-1234-567890abcdef",
                    payload={"properties": {"Owner": {"people": [{"id": "11111111-1111-1111-1111-111111111111"}]}}},
                    requested_by_actor="agent-sirouk",
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
    mod = load_module(CONTROL_PY, "almanac_control_ssot_write_apply_fail_audit_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-sirouk", unix_user="sirouk")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-sirouk",
                unix_user="sirouk",
                human_display_name="Chris",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="chris@example.com",
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
                    agent_id="agent-sirouk",
                    operation="update",
                    target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    payload={"properties": {}},
                    requested_by_actor="agent-sirouk",
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
    mod = load_module(CONTROL_PY, "almanac_control_ssot_read_suspended_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-sirouk", unix_user="sirouk")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-sirouk",
                unix_user="sirouk",
                human_display_name="Chris",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="chris@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
                suspended_at=mod.utc_now_iso(),
            )
            try:
                mod.read_ssot(
                    conn,
                    cfg,
                    agent_id="agent-sirouk",
                    target_id="",
                    query={},
                    include_markdown=False,
                    requested_by_actor="agent-sirouk",
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


def test_ssot_write_denies_cross_owner_update() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_ssot_write_cross_owner_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-sirouk", unix_user="sirouk")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-sirouk",
                unix_user="sirouk",
                human_display_name="Chris",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="chris@example.com",
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
            try:
                mod.enqueue_ssot_write(
                    conn,
                    cfg,
                    agent_id="agent-sirouk",
                    operation="update",
                    target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    payload={"properties": {"Status": {"status": {"name": "Blocked"}}}},
                    requested_by_actor="agent-sirouk",
                )
            except PermissionError as exc:
                expect("outside the verified caller" in str(exc).lower(), str(exc))
            else:
                raise AssertionError("expected cross-owner write to be denied")
            audit = conn.execute(
                "SELECT decision FROM ssot_access_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            expect(audit is not None and audit["decision"] == "deny", str(dict(audit) if audit else {}))
            print("PASS test_ssot_write_denies_cross_owner_update")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_ssot_read_denies_name_collision() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_ssot_name_collision_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-sirouk", unix_user="sirouk")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-sirouk",
                unix_user="sirouk",
                human_display_name="Chris",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="chris@example.com",
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
                    "name": "Chris",
                },
            }
            try:
                mod.read_ssot(
                    conn,
                    cfg,
                    agent_id="agent-sirouk",
                    target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    query={},
                    include_markdown=False,
                    requested_by_actor="agent-sirouk",
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
    mod = load_module(CONTROL_PY, "almanac_control_ssot_changed_by_only_acl_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-sirouk", unix_user="sirouk")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-sirouk",
                unix_user="sirouk",
                human_display_name="Chris",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="chris@example.com",
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
                    agent_id="agent-sirouk",
                    target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    query={},
                    include_markdown=False,
                    requested_by_actor="agent-sirouk",
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
    mod = load_module(CONTROL_PY, "almanac_control_ssot_write_suspended_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-sirouk", unix_user="sirouk")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-sirouk",
                unix_user="sirouk",
                human_display_name="Chris",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="chris@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=mod.utc_now_iso(),
                suspended_at=mod.utc_now_iso(),
            )
            try:
                mod.enqueue_ssot_write(
                    conn,
                    cfg,
                    agent_id="agent-sirouk",
                    operation="insert",
                    target_id="12345678-90ab-cdef-1234-567890abcdef",
                    payload={
                        "properties": {
                            "Owner": {"people": [{"id": "11111111-1111-1111-1111-111111111111"}]}
                        }
                    },
                    requested_by_actor="agent-sirouk",
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
    mod = load_module(CONTROL_PY, "almanac_control_ssot_registry_fail_closed_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        original_get_identity = mod.get_agent_identity
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-sirouk", unix_user="sirouk")

            def boom(*args, **kwargs):
                raise mod.sqlite3.OperationalError("boom")

            mod.get_agent_identity = boom
            try:
                mod.read_ssot(
                    conn,
                    cfg,
                    agent_id="agent-sirouk",
                    target_id="",
                    query={},
                    include_markdown=False,
                    requested_by_actor="agent-sirouk",
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
    mod = load_module(CONTROL_PY, "almanac_control_notion_batcher_hydrate_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-sirouk", unix_user="sirouk")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-sirouk",
                unix_user="sirouk",
                human_display_name="Chris",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="chris@example.com",
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
                    "properties": {
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
            expect(result["nudges"].get("agent-sirouk") == 1, result)
            agent_notice = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM notification_outbox
                WHERE target_kind = 'user-agent' AND channel_kind = 'notion-webhook' AND target_id = 'agent-sirouk'
                """
            ).fetchone()
            expect(int(agent_notice["c"] if agent_notice else 0) == 1, str(dict(agent_notice) if agent_notice else {}))
            fanout = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM notification_outbox
                WHERE target_kind = 'curator' AND channel_kind = 'brief-fanout' AND target_id = 'agent-sirouk'
                """
            ).fetchone()
            expect(int(fanout["c"] if fanout else 0) == 1, str(dict(fanout) if fanout else {}))
            row = conn.execute(
                "SELECT batch_status FROM notion_webhook_events WHERE event_id = 'event-1'"
            ).fetchone()
            expect(row is not None and row["batch_status"] == "processed", str(dict(row) if row else {}))
            print("PASS test_notion_batcher_hydrates_entity_before_routing")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_notion_batcher_retries_when_hydration_fails() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_notion_batcher_retry_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
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
    mod = load_module(CONTROL_PY, "almanac_control_notion_batcher_retry_budget_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
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
            print("PASS test_notion_batcher_marks_event_failed_after_retry_budget")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_notion_batcher_verifies_claim_page_event() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_notion_batcher_claim_verify_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-sirouk", unix_user="sirouk")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-sirouk",
                unix_user="sirouk",
                human_display_name="Chris",
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
                    "agent-sirouk",
                    "sirouk",
                    "chris@example.com",
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
                    "person": {"email": "chris@example.com"},
                },
                "properties": {},
            }
            mod.update_notion_page = lambda **kwargs: {
                "id": kwargs["page_id"],
                "properties": kwargs["payload"]["properties"],
            }

            result = mod.process_pending_notion_events(conn)
            expect(result["verified_claims"] == 1, result)
            claim = mod.get_notion_identity_claim(conn, claim_id="nclaim_test")
            expect(claim is not None and claim["status"] == "verified", str(claim))
            identity = mod.get_agent_identity(conn, agent_id="agent-sirouk", unix_user="sirouk")
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
                WHERE target_kind = 'curator' AND channel_kind = 'brief-fanout' AND target_id = 'agent-sirouk'
                """
            ).fetchone()
            expect(int(queued["c"] if queued else 0) >= 1, str(dict(queued) if queued else {}))
            print("PASS test_notion_batcher_verifies_claim_page_event")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_notion_batcher_rejects_claim_page_edit_from_wrong_email() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_notion_batcher_claim_wrong_email_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-sirouk", unix_user="sirouk")
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-sirouk",
                unix_user="sirouk",
                human_display_name="Chris",
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
                    "agent-sirouk",
                    "sirouk",
                    "chris@example.com",
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

            result = mod.process_pending_notion_events(conn)
            expect(result["verified_claims"] == 0, result)
            claim = mod.get_notion_identity_claim(conn, claim_id="nclaim_wrong_email")
            expect(claim is not None and claim["status"] == "pending", str(claim))
            expect("different notion email" in str(claim.get("failure_reason") or "").lower(), str(claim))
            identity = mod.get_agent_identity(conn, agent_id="agent-sirouk", unix_user="sirouk")
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


def main() -> int:
    test_ssot_read_denies_database_query_until_verified()
    test_ssot_read_scopes_database_results_to_verified_user()
    test_ssot_write_requires_verified_write_mode()
    test_ssot_write_applies_verified_owned_update()
    test_ssot_write_applies_verified_owned_insert()
    test_ssot_write_applies_without_changed_by_property()
    test_ssot_write_fails_closed_when_changed_by_schema_lookup_fails()
    test_ssot_write_logs_failure_when_notion_apply_raises()
    test_ssot_read_denies_suspended_identity()
    test_ssot_write_denies_cross_owner_update()
    test_ssot_read_denies_name_collision()
    test_ssot_read_denies_changed_by_only_match()
    test_ssot_write_denies_suspended_identity()
    test_ssot_principal_fails_closed_when_identity_registry_errors()
    test_notion_batcher_hydrates_entity_before_routing()
    test_notion_batcher_retries_when_hydration_fails()
    test_notion_batcher_marks_event_failed_after_retry_budget()
    test_notion_batcher_verifies_claim_page_event()
    test_notion_batcher_rejects_claim_page_edit_from_wrong_email()
    print("PASS all 19 ssot broker tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
