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


def test_curator_fanout_writes_managed_payload_and_activation_trigger() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_memory_sync_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        values = {
            "ALMANAC_USER": "almanac",
            "ALMANAC_HOME": str(root / "home-almanac"),
            "ALMANAC_REPO_DIR": str(root / "repo"),
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
            "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "telegram",
            "OPERATOR_NOTIFY_CHANNEL_ID": "1994645819",
            "ALMANAC_MODEL_PRESET_CODEX": "openai:codex",
            "ALMANAC_MODEL_PRESET_OPUS": "anthropic:claude-opus",
            "ALMANAC_MODEL_PRESET_CHUTES": "chutes:auto-failover",
            "ALMANAC_CURATOR_CHANNELS": "tui-only,telegram,discord",
            "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "1",
            "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED": "1",
        }
        write_config(config_path, values)

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            now = mod.utc_now_iso()

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
                    "agent-test",
                    "user",
                    "testuser",
                    "Test User",
                    "active",
                    str(root / "home-testuser" / ".local" / "share" / "almanac-agent" / "hermes-home"),
                    str(root / "state" / "agents" / "agent-test" / "manifest.json"),
                    None,
                    "codex",
                    "openai:codex",
                    json.dumps(["tui-only"]),
                    json.dumps([]),
                    json.dumps({"platform": "tui", "channel_id": ""}),
                    json.dumps({}),
                    "",
                    now,
                    now,
                ),
            )
            conn.execute(
                "INSERT INTO vaults (vault_name, vault_path, state, warning, owner, default_subscribed, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("Projects", str(root / "vault" / "Projects"), "active", None, "operator", 1, now),
            )
            conn.execute(
                """
                INSERT INTO vault_definitions (
                  definition_path, vault_name, vault_path, owner, description, default_subscribed,
                  tags_json, category, brief_template, is_valid, warning, discovered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(root / "vault" / "Projects" / ".vault"),
                    "Projects",
                    str(root / "vault" / "Projects"),
                    "operator",
                    "Active project workspaces",
                    1,
                    json.dumps(["projects"]),
                    "workspace",
                    "Project plans and briefs.",
                    1,
                    None,
                    now,
                ),
            )
            conn.execute(
                "INSERT INTO agent_vault_subscriptions (agent_id, vault_name, subscribed, source, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("agent-test", "Projects", 1, "default", now),
            )
            hermes_home = root / "home-test" / ".local" / "share" / "almanac-agent" / "hermes-home"
            (hermes_home / "state").mkdir(parents=True, exist_ok=True)
            (hermes_home / "state" / "almanac-web-access.json").write_text(
                json.dumps(
                    {
                        "dashboard_url": "https://kor.tail77f45e.ts.net:30042/",
                        "code_url": "https://kor.tail77f45e.ts.net:40042/",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            conn.execute(
                "UPDATE agents SET hermes_home = ? WHERE agent_id = ?",
                (str(hermes_home), "agent-test"),
            )
            conn.commit()

            mod.queue_notification(
                conn,
                target_kind="curator",
                target_id="agent-test",
                channel_kind="brief-fanout",
                message="agent-test subscription change: Projects -> True",
            )

            result = mod.consume_curator_brief_fanout(conn, cfg)
            expect(result["processed_notifications"] == 1, f"expected 1 processed notification, got {result}")
            expect(len(result["published_agents"]) == 1, f"expected one published agent, got {result}")
            published = result["published_agents"][0]
            managed_path = Path(published["path"])
            trigger_path = Path(published["activation_trigger_path"])
            expect(managed_path.is_file(), f"managed-memory payload missing: {managed_path}")
            expect(trigger_path.is_file(), f"activation trigger missing: {trigger_path}")

            managed_payload = json.loads(managed_path.read_text(encoding="utf-8"))
            expect(managed_payload["agent_id"] == "agent-test", managed_payload)
            expect("vault-topology" in managed_payload, managed_payload)
            expect("Projects" in managed_payload["vault-topology"], managed_payload["vault-topology"])
            expect("Dedicated agent name: Test User" in managed_payload["vault-ref"], managed_payload["vault-ref"])
            expect("resource-ref" in managed_payload, managed_payload)
            expect("Hermes dashboard: https://kor.tail77f45e.ts.net:30042/" in managed_payload["resource-ref"], managed_payload["resource-ref"])
            expect("Code workspace: https://kor.tail77f45e.ts.net:40042/" in managed_payload["resource-ref"], managed_payload["resource-ref"])
            expect("Shared Notion SSOT: https://www.notion.so/Acme-SSOT-1234567890abcdef1234567890abcdef" in managed_payload["resource-ref"], managed_payload["resource-ref"])
            expect("Credentials are intentionally omitted from managed memory." in managed_payload["resource-ref"], managed_payload["resource-ref"])
            expect("notion-stub" in managed_payload, managed_payload)
            expect("Shared Notion digest:" in managed_payload["notion-stub"], managed_payload["notion-stub"])
            expect(
                "All vaults remain retrievable through Almanac/qmd" in managed_payload["almanac-skill-ref"],
                managed_payload["almanac-skill-ref"],
            )
            expect("almanac-ssot" in managed_payload["almanac-skill-ref"], managed_payload["almanac-skill-ref"])
            expect("Use almanac-ssot" in managed_payload["qmd-ref"], managed_payload["qmd-ref"])

            trigger_payload = json.loads(trigger_path.read_text(encoding="utf-8"))
            expect(trigger_payload["agent_id"] == "agent-test", trigger_payload)
            expect(trigger_payload["status"] == "refresh", trigger_payload)
            expect("managed memory stubs" in trigger_payload["note"], trigger_payload)

            delivered = conn.execute(
                "SELECT COUNT(*) AS c FROM notification_outbox WHERE target_kind = 'curator' AND delivered_at IS NOT NULL"
            ).fetchone()["c"]
            expect(delivered == 1, f"expected delivered curator notification row, found {delivered}")
            print("PASS test_curator_fanout_writes_managed_payload_and_activation_trigger")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_managed_notion_stub_stays_scoped_to_verified_user() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_memory_sync_notion_scope_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        values = {
            "ALMANAC_USER": "almanac",
            "ALMANAC_HOME": str(root / "home-almanac"),
            "ALMANAC_REPO_DIR": str(root / "repo"),
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
            "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "telegram",
            "OPERATOR_NOTIFY_CHANNEL_ID": "1994645819",
            "ALMANAC_MODEL_PRESET_CODEX": "openai:codex",
            "ALMANAC_MODEL_PRESET_OPUS": "anthropic:claude-opus",
            "ALMANAC_MODEL_PRESET_CHUTES": "chutes:auto-failover",
            "ALMANAC_CURATOR_CHANNELS": "tui-only,telegram,discord",
            "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "1",
            "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED": "1",
        }
        write_config(config_path, values)

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            now = mod.utc_now_iso()
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
                    "agent-test",
                    "user",
                    "testuser",
                    "Test User",
                    "active",
                    str(root / "home-testuser" / ".local" / "share" / "almanac-agent" / "hermes-home"),
                    str(root / "state" / "agents" / "agent-test" / "manifest.json"),
                    None,
                    "codex",
                    "openai:codex",
                    json.dumps(["tui-only"]),
                    json.dumps([]),
                    json.dumps({"platform": "tui", "channel_id": ""}),
                    json.dumps({}),
                    "",
                    now,
                    now,
                ),
            )
            conn.commit()
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-test",
                unix_user="testuser",
                human_display_name="Chris",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="chris@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=now,
            )
            own_item = {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "last_edited_time": now,
                "properties": {
                    "Title": {
                        "type": "title",
                        "title": [{"plain_text": "Own Task"}],
                    },
                    "Owner": {
                        "people": [{"id": "11111111-1111-1111-1111-111111111111", "name": "Chris"}]
                    },
                    "Due": {"type": "date", "date": {"start": "2026-04-21"}},
                },
            }
            other_item = {
                "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "last_edited_time": now,
                "properties": {
                    "Title": {
                        "type": "title",
                        "title": [{"plain_text": "Other Task"}],
                    },
                    "Owner": {
                        "people": [{"id": "22222222-2222-2222-2222-222222222222", "name": "Alex"}]
                    },
                    "Due": {"type": "date", "date": {"start": "2026-04-22"}},
                },
            }
            mod.retrieve_notion_database = lambda **kwargs: {
                "id": "12345678-90ab-cdef-1234-567890abcdef",
                "properties": {
                    "Owner": {"type": "people"},
                    "Assignee": {"type": "people"},
                    "Changed By": {"type": "people"},
                },
            }

            def fake_query_notion_collection(**kwargs):
                payload = kwargs.get("payload") or {}
                if payload.get("filter"):
                    return {"result": {"results": [own_item, other_item]}}
                return {"result": {"results": [own_item, other_item]}}

            mod.query_notion_collection = fake_query_notion_collection
            agent_row = conn.execute(
                "SELECT * FROM agents WHERE agent_id = 'agent-test'"
            ).fetchone()
            identity = mod.get_agent_identity(conn, agent_id="agent-test", unix_user="testuser")
            stub = mod._build_notion_stub(conn, agent_row=agent_row, identity=identity)
            expect("Own Task" in stub, stub)
            expect("Other Task" not in stub, stub)
            expect("Alex" not in stub, stub)
            expect("Largest current owner loads:" in stub, stub)
            print("PASS test_managed_notion_stub_stays_scoped_to_verified_user")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_managed_notion_stub_reports_pending_claim_status() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_memory_sync_notion_pending_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        values = {
            "ALMANAC_USER": "almanac",
            "ALMANAC_HOME": str(root / "home-almanac"),
            "ALMANAC_REPO_DIR": str(root / "repo"),
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
            "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "telegram",
            "OPERATOR_NOTIFY_CHANNEL_ID": "1994645819",
            "ALMANAC_MODEL_PRESET_CODEX": "openai:codex",
            "ALMANAC_MODEL_PRESET_OPUS": "anthropic:claude-opus",
            "ALMANAC_MODEL_PRESET_CHUTES": "chutes:auto-failover",
            "ALMANAC_CURATOR_CHANNELS": "tui-only,telegram,discord",
            "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "1",
            "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED": "1",
        }
        write_config(config_path, values)

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            now = mod.utc_now_iso()
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
                    "agent-test",
                    "user",
                    "testuser",
                    "Test User",
                    "active",
                    str(root / "home-testuser" / ".local" / "share" / "almanac-agent" / "hermes-home"),
                    str(root / "state" / "agents" / "agent-test" / "manifest.json"),
                    None,
                    "codex",
                    "openai:codex",
                    json.dumps(["tui-only"]),
                    json.dumps([]),
                    json.dumps({"platform": "tui", "channel_id": ""}),
                    json.dumps({}),
                    "",
                    now,
                    now,
                ),
            )
            conn.commit()
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-test",
                unix_user="testuser",
                human_display_name="Chris",
                claimed_notion_email="chris@example.com",
                verification_status="pending",
                write_mode="read_only",
            )
            mod.retrieve_notion_database = lambda **kwargs: {
                "id": "12345678-90ab-cdef-1234-567890abcdef",
                "properties": {"Owner": {"type": "people"}},
            }
            mod.query_notion_collection = lambda **kwargs: {"result": {"results": []}}
            agent_row = conn.execute("SELECT * FROM agents WHERE agent_id = 'agent-test'").fetchone()
            identity = mod.get_agent_identity(conn, agent_id="agent-test", unix_user="testuser")
            stub = mod._build_notion_stub(conn, agent_row=agent_row, identity=identity)
            expect("Verification: pending for chris@example.com." in stub, stub)
            expect("Shared writes remain read-only" in stub, stub)
            print("PASS test_managed_notion_stub_reports_pending_claim_status")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_managed_notion_stub_reports_verified_page_scoped_write_access() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_memory_sync_notion_page_scope_verified_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        values = {
            "ALMANAC_USER": "almanac",
            "ALMANAC_HOME": str(root / "home-almanac"),
            "ALMANAC_REPO_DIR": str(root / "repo"),
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
            "ALMANAC_SSOT_NOTION_SPACE_URL": "https://www.notion.so/The-Almanac-1234567890abcdef1234567890abcdef",
            "ALMANAC_SSOT_NOTION_SPACE_ID": "12345678-90ab-cdef-1234-567890abcdef",
            "ALMANAC_SSOT_NOTION_SPACE_KIND": "page",
            "ALMANAC_SSOT_NOTION_TOKEN": "secret_test",
            "ALMANAC_SSOT_NOTION_API_VERSION": "2026-03-11",
            "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "telegram",
            "OPERATOR_NOTIFY_CHANNEL_ID": "1994645819",
            "ALMANAC_MODEL_PRESET_CODEX": "openai:codex",
            "ALMANAC_MODEL_PRESET_OPUS": "anthropic:claude-opus",
            "ALMANAC_MODEL_PRESET_CHUTES": "chutes:auto-failover",
            "ALMANAC_CURATOR_CHANNELS": "tui-only,telegram,discord",
            "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "1",
            "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED": "1",
        }
        write_config(config_path, values)

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            now = mod.utc_now_iso()
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
                    "agent-test",
                    "user",
                    "testuser",
                    "Test User",
                    "active",
                    str(root / "home-testuser" / ".local" / "share" / "almanac-agent" / "hermes-home"),
                    str(root / "state" / "agents" / "agent-test" / "manifest.json"),
                    None,
                    "codex",
                    "openai:codex",
                    json.dumps(["tui-only"]),
                    json.dumps([]),
                    json.dumps({"platform": "tui", "channel_id": ""}),
                    json.dumps({}),
                    "",
                    now,
                    now,
                ),
            )
            conn.commit()
            mod.upsert_agent_identity(
                conn,
                agent_id="agent-test",
                unix_user="testuser",
                human_display_name="Chris",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                notion_user_email="chris@example.com",
                verification_status="verified",
                write_mode="verified_limited",
                verified_at=now,
            )
            agent_row = conn.execute("SELECT * FROM agents WHERE agent_id = 'agent-test'").fetchone()
            identity = mod.get_agent_identity(conn, agent_id="agent-test", unix_user="testuser")
            stub = mod._build_notion_stub(conn, agent_row=agent_row, identity=identity)
            expect("page-scoped right now" in stub, stub)
            expect("Verification: confirmed for chris@example.com." in stub, stub)
            expect("Shared brokered writes are enabled within your scoped rails." in stub, stub)
            print("PASS test_managed_notion_stub_reports_verified_page_scoped_write_access")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_managed_notion_stub_reports_verification_not_started() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_memory_sync_notion_unverified_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        values = {
            "ALMANAC_USER": "almanac",
            "ALMANAC_HOME": str(root / "home-almanac"),
            "ALMANAC_REPO_DIR": str(root / "repo"),
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
            "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "telegram",
            "OPERATOR_NOTIFY_CHANNEL_ID": "1994645819",
            "ALMANAC_MODEL_PRESET_CODEX": "openai:codex",
            "ALMANAC_MODEL_PRESET_OPUS": "anthropic:claude-opus",
            "ALMANAC_MODEL_PRESET_CHUTES": "chutes:auto-failover",
            "ALMANAC_CURATOR_CHANNELS": "tui-only,telegram,discord",
            "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "1",
            "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED": "1",
        }
        write_config(config_path, values)

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            now = mod.utc_now_iso()
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
                    "agent-test",
                    "user",
                    "testuser",
                    "Test User",
                    "active",
                    str(root / "home-testuser" / ".local" / "share" / "almanac-agent" / "hermes-home"),
                    str(root / "state" / "agents" / "agent-test" / "manifest.json"),
                    None,
                    "codex",
                    "openai:codex",
                    json.dumps(["tui-only"]),
                    json.dumps([]),
                    json.dumps({"platform": "tui", "channel_id": ""}),
                    json.dumps({}),
                    "",
                    now,
                    now,
                ),
            )
            conn.commit()
            mod.retrieve_notion_database = lambda **kwargs: {
                "id": "12345678-90ab-cdef-1234-567890abcdef",
                "properties": {"Owner": {"type": "people"}},
            }
            mod.query_notion_collection = lambda **kwargs: {"result": {"results": []}}
            agent_row = conn.execute("SELECT * FROM agents WHERE agent_id = 'agent-test'").fetchone()
            stub = mod._build_notion_stub(conn, agent_row=agent_row, identity=None)
            expect("Verification: not started yet." in stub, stub)
            expect("Shared writes remain read-only" in stub, stub)
            print("PASS test_managed_notion_stub_reports_verification_not_started")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_curator_fanout_writes_managed_payload_and_activation_trigger()
    test_managed_notion_stub_stays_scoped_to_verified_user()
    test_managed_notion_stub_reports_pending_claim_status()
    test_managed_notion_stub_reports_verified_page_scoped_write_access()
    test_managed_notion_stub_reports_verification_not_started()
    print("PASS all 5 memory sync regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
