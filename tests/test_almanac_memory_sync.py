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
            expect(managed_payload.get("active_subscriptions") == ["Projects"], managed_payload)
            expect("vault-topology" in managed_payload, managed_payload)
            expect("Vault subscription hierarchy" in managed_payload["vault-topology"], managed_payload["vault-topology"])
            expect("Projects" in managed_payload["vault-topology"], managed_payload["vault-topology"])
            expect(managed_payload["subscriptions"][0]["hierarchy_source"] == "catalog-default", managed_payload["subscriptions"])
            expect(bool(managed_payload["subscriptions"][0]["push_enabled"]) is True, managed_payload["subscriptions"])
            expect("Dedicated agent name: Test User" in managed_payload["vault-ref"], managed_payload["vault-ref"])
            expect("resource-ref" in managed_payload, managed_payload)
            expect("Hermes dashboard: https://kor.tail77f45e.ts.net:30042/" in managed_payload["resource-ref"], managed_payload["resource-ref"])
            expect("Code workspace: https://kor.tail77f45e.ts.net:40042/" in managed_payload["resource-ref"], managed_payload["resource-ref"])
            expect("Shared Notion SSOT: https://www.notion.so/Acme-SSOT-1234567890abcdef1234567890abcdef" in managed_payload["resource-ref"], managed_payload["resource-ref"])
            expect("Credentials are intentionally omitted from managed memory." in managed_payload["resource-ref"], managed_payload["resource-ref"])
            expect("agent-facing source of truth" in managed_payload["resource-ref"], managed_payload["resource-ref"])
            expect("notion-stub" in managed_payload, managed_payload)
            expect("Shared Notion digest:" in managed_payload["notion-stub"], managed_payload["notion-stub"])
            expect("today-plate" in managed_payload, managed_payload)
            expect("Today plate:" in managed_payload["today-plate"], managed_payload["today-plate"])
            expect("not ready for a structured work plate" in managed_payload["today-plate"], managed_payload["today-plate"])
            expect("managed_memory_revision" in managed_payload, managed_payload)
            expect(len(str(managed_payload["managed_memory_revision"])) >= 12, managed_payload)
            expect(
                "All vaults remain retrievable through Almanac/qmd" in managed_payload["almanac-skill-ref"],
                managed_payload["almanac-skill-ref"],
            )
            expect("Current Almanac capability snapshot:" in managed_payload["almanac-skill-ref"], managed_payload["almanac-skill-ref"])
            expect("almanac-ssot" in managed_payload["almanac-skill-ref"], managed_payload["almanac-skill-ref"])
            expect("optional personal Notion helper" in managed_payload["almanac-skill-ref"], managed_payload["almanac-skill-ref"])
            expect("default shared Almanac workspace-search lane" in managed_payload["almanac-skill-ref"], managed_payload["almanac-skill-ref"])
            expect("Human-facing completion or onboarding messages may omit machine-facing MCP/control rails" in managed_payload["almanac-skill-ref"], managed_payload["almanac-skill-ref"])
            expect("almanac-managed-context plugin can inject refreshed local Almanac context into future turns" in managed_payload["almanac-skill-ref"], managed_payload["almanac-skill-ref"])
            expect("next session, /reset, or gateway restart" not in managed_payload["almanac-skill-ref"], managed_payload["almanac-skill-ref"])
            expect("Treat the skill as the workflow and guardrail layer" in managed_payload["almanac-skill-ref"], managed_payload["almanac-skill-ref"])
            expect("do not rediscover the qmd rail by repo-wide search" in managed_payload["almanac-skill-ref"], managed_payload["almanac-skill-ref"])
            expect("When a brokered action is refused" in managed_payload["almanac-skill-ref"], managed_payload["almanac-skill-ref"])
            expect("Use almanac-ssot" in managed_payload["qmd-ref"], managed_payload["qmd-ref"])
            expect("start with this rail before searching repo files, docs" in managed_payload["qmd-ref"], managed_payload["qmd-ref"])
            expect("initialize -> capture mcp-session-id" in managed_payload["qmd-ref"], managed_payload["qmd-ref"])
            expect("Send the same mcp-session-id header returned by initialize" in managed_payload["qmd-ref"], managed_payload["qmd-ref"])
            expect('"method":"tools/call"' in managed_payload["qmd-ref"], managed_payload["qmd-ref"])
            expect('"name":"query"' in managed_payload["qmd-ref"], managed_payload["qmd-ref"])
            expect('"collections":["vault"]' in managed_payload["qmd-ref"], managed_payload["qmd-ref"])
            expect("result.content[].text and result.structuredContent.results[]" in managed_payload["qmd-ref"], managed_payload["qmd-ref"])
            expect("combining lex and vec searches" in managed_payload["qmd-ref"], managed_payload["qmd-ref"])
            expect("Only inspect docs/hermes-qmd-config.yaml or qmd daemon files if the" in managed_payload["qmd-ref"], managed_payload["qmd-ref"])
            expect("human-facing message leaves those rail URLs out" in managed_payload["qmd-ref"], managed_payload["qmd-ref"])
            expect("notion-ref" in managed_payload, managed_payload)
            expect("Shared Notion knowledge rail" in managed_payload["notion-ref"], managed_payload["notion-ref"])
            expect("notion.search" in managed_payload["notion-ref"], managed_payload["notion-ref"])
            expect("notion.fetch" in managed_payload["notion-ref"], managed_payload["notion-ref"])
            expect("notion.query" in managed_payload["notion-ref"], managed_payload["notion-ref"])
            expect("one search, then zero-to-three fetches" in managed_payload["notion-ref"], managed_payload["notion-ref"])
            expect("shared read rail" in managed_payload["notion-ref"], managed_payload["notion-ref"])

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


def test_curator_fanout_skips_refresh_signal_when_payload_cache_matches() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_memory_sync_cache_hit_test")
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

            for _ in range(2):
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
                if _ == 0:
                    first_body = managed_path.read_text(encoding="utf-8")
                    trigger_path = mod.activation_trigger_path(cfg, "agent-test")
                    expect(trigger_path.is_file(), f"expected activation trigger on first publish: {trigger_path}")
                    trigger_path.unlink()
                else:
                    expect(bool(published.get("changed")) is False, str(published))
                    expect("activation_trigger_path" not in published, str(published))
                    expect(managed_path.read_text(encoding="utf-8") == first_body, "managed payload should stay byte-identical on cache hit")
                    trigger_path = mod.activation_trigger_path(cfg, "agent-test")
                    expect(not trigger_path.exists(), f"unexpected activation trigger on cache hit: {trigger_path}")
            print("PASS test_curator_fanout_skips_refresh_signal_when_payload_cache_matches")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_curator_fanout_retries_failed_agent_without_dropping_work() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_memory_sync_retry_test")
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
            for agent_id, unix_user in (("agent-a", "usera"), ("agent-b", "userb")):
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
                        unix_user,
                        agent_id,
                        "active",
                        str(root / unix_user / ".local" / "share" / "almanac-agent" / "hermes-home"),
                        str(root / "state" / "agents" / agent_id / "manifest.json"),
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

            mod.queue_notification(
                conn,
                target_kind="curator",
                target_id="curator",
                channel_kind="brief-fanout",
                message="catalog refresh",
            )
            attempts: dict[str, int] = {}

            def fake_publish(conn, cfg, *, agent_id: str, notion_stub_cache=None):
                attempts[agent_id] = attempts.get(agent_id, 0) + 1
                if agent_id == "agent-b" and attempts[agent_id] == 1:
                    raise RuntimeError("temporary notion throttle")
                out_path = root / "state" / "agents" / agent_id / "managed-memory.json"
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(json.dumps({"agent_id": agent_id}) + "\n", encoding="utf-8")
                return {
                    "path": str(out_path),
                    "changed": True,
                    "managed_memory_revision": f"rev-{agent_id}",
                    "managed_payload_cache_key": f"cache-{agent_id}",
                }

            mod.publish_central_managed_memory = fake_publish
            mod.signal_agent_refresh_from_curator = lambda *args, **kwargs: None

            first = mod.consume_curator_brief_fanout(conn, cfg)
            expect(first["expanded_notifications"] == 1, str(first))
            expect(first["expanded_agents"] == 2, str(first))
            expect(len(first["published_agents"]) == 1, str(first))
            expect(len(first["failures"]) == 1 and "agent-b" in first["failures"][0], str(first))

            rows = conn.execute(
                """
                SELECT target_id, delivered_at, attempt_count, delivery_error, next_attempt_at
                FROM notification_outbox
                WHERE target_kind = 'curator' AND channel_kind = 'brief-fanout'
                ORDER BY id ASC
                """
            ).fetchall()
            expect(len(rows) == 3, str([dict(row) for row in rows]))
            expect(str(rows[0]["target_id"]) == "curator" and str(rows[0]["delivered_at"] or "") != "", str(dict(rows[0])))
            expect(str(rows[1]["target_id"]) == "agent-a" and str(rows[1]["delivered_at"] or "") != "", str(dict(rows[1])))
            expect(str(rows[2]["target_id"]) == "agent-b" and str(rows[2]["delivered_at"] or "") == "", str(dict(rows[2])))
            expect(int(rows[2]["attempt_count"] or 0) == 1, str(dict(rows[2])))
            expect("temporary notion throttle" in str(rows[2]["delivery_error"] or ""), str(dict(rows[2])))

            conn.execute(
                """
                UPDATE notification_outbox
                SET next_attempt_at = ?
                WHERE target_kind = 'curator' AND channel_kind = 'brief-fanout' AND target_id = 'agent-b'
                """,
                (mod.auto_provision_stale_before_iso(600),),
            )
            conn.commit()

            second = mod.consume_curator_brief_fanout(conn, cfg)
            expect(len(second["published_agents"]) == 1, str(second))
            expect(second["published_agents"][0]["agent_id"] == "agent-b", str(second))
            expect(second["failures"] == [], str(second))
            retried = conn.execute(
                """
                SELECT delivered_at, attempt_count
                FROM notification_outbox
                WHERE target_kind = 'curator' AND channel_kind = 'brief-fanout' AND target_id = 'agent-b'
                ORDER BY id DESC LIMIT 1
                """
            ).fetchone()
            expect(retried is not None and str(retried["delivered_at"] or "") != "", str(dict(retried) if retried else {}))
            expect(int(retried["attempt_count"] or 0) == 1, str(dict(retried)))
            print("PASS test_curator_fanout_retries_failed_agent_without_dropping_work")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_curator_fanout_reuses_shared_notions_snapshot_cache_per_batch() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_memory_sync_shared_cache_test")
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
            for agent_id, unix_user, notion_id, notion_email in (
                ("agent-a", "usera", "11111111-1111-1111-1111-111111111111", "a@example.com"),
                ("agent-b", "userb", "22222222-2222-2222-2222-222222222222", "b@example.com"),
            ):
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
                        unix_user,
                        agent_id,
                        "active",
                        str(root / unix_user / ".local" / "share" / "almanac-agent" / "hermes-home"),
                        str(root / "state" / "agents" / agent_id / "manifest.json"),
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
                mod.upsert_agent_identity(
                    conn,
                    agent_id=agent_id,
                    unix_user=unix_user,
                    human_display_name=agent_id,
                    notion_user_id=notion_id,
                    notion_user_email=notion_email,
                    verification_status="verified",
                    write_mode="verified_limited",
                    verified_at=now,
                )
            conn.commit()

            mod.queue_notification(
                conn,
                target_kind="curator",
                target_id="agent-a",
                channel_kind="brief-fanout",
                message="refresh agent-a",
            )
            mod.queue_notification(
                conn,
                target_kind="curator",
                target_id="agent-b",
                channel_kind="brief-fanout",
                message="refresh agent-b",
            )

            stats = {"schema": 0, "team": 0, "scoped": 0}

            def fake_schema_loader(*, target_id, settings, notion_kwargs=None):
                stats["schema"] += 1
                return (
                    {"id": target_id, "properties": {"Owner": {"type": "people"}}},
                    {"properties": {"Owner": {"type": "people"}}},
                )

            def fake_query_notion_collection(**kwargs):
                payload = kwargs.get("payload") or {}
                if "filter" in payload:
                    stats["scoped"] += 1
                    return {"result": {"results": []}}
                stats["team"] += 1
                return {"result": {"results": []}}

            mod._load_notion_collection_schema = fake_schema_loader
            mod.query_notion_collection = fake_query_notion_collection
            mod.signal_agent_refresh_from_curator = lambda *args, **kwargs: None

            result = mod.consume_curator_brief_fanout(conn, cfg)
            expect(result["failures"] == [], str(result))
            expect(len(result["published_agents"]) == 2, str(result))
            expect(stats["schema"] == 1, str(stats))
            expect(stats["team"] == 1, str(stats))
            expect(stats["scoped"] == 2, str(stats))
            print("PASS test_curator_fanout_reuses_shared_notions_snapshot_cache_per_batch")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_write_managed_memory_stubs_skips_local_rewrites_on_cache_hit() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_memory_sync_local_cache_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        hermes_home = root / "hermes-home"
        memory_path = hermes_home / "memories" / "MEMORY.md"
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        memory_path.write_text("Persistent preference", encoding="utf-8")
        payload = {
            "agent_id": "agent-test",
            "almanac-skill-ref": "Use almanac-qmd-mcp for retrieval.",
            "vault-ref": "Vault root: /srv/almanac/vault\nDedicated agent name: Test User",
            "resource-ref": "Canonical user access rails and shared Almanac addresses:\n- Credentials are intentionally omitted from managed memory.",
            "qmd-ref": "qmd MCP (deep retrieval): http://127.0.0.1:8181/mcp",
            "notion-ref": "Shared Notion knowledge rail: notion.search / notion.fetch / notion.query via Almanac MCP.",
            "vault-topology": "Vault subscription hierarchy (precedence: user override > catalog default; push follows effective subscription):\n  + Projects: source=default, default=on, push=on — Active project workspaces",
            "notion-stub": "Shared Notion digest:\n- No shared digest published yet.",
            "catalog": [{"vault_name": "Projects", "default_subscribed": 1, "description": "Active project workspaces"}],
            "subscriptions": [
                {
                    "vault_name": "Projects",
                    "subscribed": 1,
                    "default_subscribed": 1,
                    "hierarchy_source": "catalog-default",
                    "push_enabled": True,
                    "subscription_state": "default-in",
                }
            ],
            "active_subscriptions": ["Projects"],
        }

        first = mod.write_managed_memory_stubs(hermes_home=hermes_home, payload=payload)
        expect(bool(first.get("changed")) is True, str(first))
        state_path = Path(first["state_path"])
        stub_path = Path(first["stub_path"])
        first_state = state_path.read_text(encoding="utf-8")
        first_stub = stub_path.read_text(encoding="utf-8")
        first_memory = memory_path.read_text(encoding="utf-8")
        expect("notion-ref" in json.loads(first_state), first_state)
        expect("today-plate" in json.loads(first_state), first_state)
        expect("[managed:notion-ref]" in first_stub, first_stub)
        expect("[managed:today-plate]" in first_stub, first_stub)
        expect("[managed:notion-ref]" in first_memory, first_memory)
        expect("[managed:today-plate]" in first_memory, first_memory)

        second = mod.write_managed_memory_stubs(hermes_home=hermes_home, payload=payload)
        expect(bool(second.get("changed")) is False, str(second))
        expect(state_path.read_text(encoding="utf-8") == first_state, "state payload should not rewrite on cache hit")
        expect(stub_path.read_text(encoding="utf-8") == first_stub, "stub mirror should not rewrite on cache hit")
        expect(memory_path.read_text(encoding="utf-8") == first_memory, "MEMORY.md should not rewrite on cache hit")
        expect("Persistent preference" in first_memory, first_memory)
        print("PASS test_write_managed_memory_stubs_skips_local_rewrites_on_cache_hit")


def test_write_managed_memory_stubs_repairs_matching_cache_key_state_drift() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_memory_sync_state_drift_test")
    with tempfile.TemporaryDirectory() as tmp:
        hermes_home = Path(tmp)
        memory_path = hermes_home / "memories" / "MEMORY.md"
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        memory_path.write_text("Persistent preference", encoding="utf-8")
        payload = {
            "agent_id": "agent-test",
            "almanac-skill-ref": "Use almanac-qmd-mcp for retrieval.",
            "vault-ref": "Vault root: /srv/almanac/vault\nDedicated agent name: Test User",
            "resource-ref": "Canonical user access rails and shared Almanac addresses:\n- Credentials are intentionally omitted from managed memory.",
            "qmd-ref": "qmd MCP (deep retrieval): http://127.0.0.1:8181/mcp",
            "notion-ref": "Shared Notion knowledge rail: notion.search / notion.fetch / notion.query via Almanac MCP.",
            "vault-topology": "Vault subscription hierarchy (precedence: user override > catalog default; push follows effective subscription):\n  + Projects: source=default, default=on, push=on — Active project workspaces",
            "notion-stub": "Shared Notion digest:\n- No shared digest published yet.",
            "catalog": [{"vault_name": "Projects", "default_subscribed": 1, "description": "Active project workspaces"}],
            "subscriptions": [
                {
                    "vault_name": "Projects",
                    "subscribed": 1,
                    "default_subscribed": 1,
                    "hierarchy_source": "catalog-default",
                    "push_enabled": True,
                    "subscription_state": "default-in",
                }
            ],
            "active_subscriptions": ["Projects"],
        }

        first = mod.write_managed_memory_stubs(hermes_home=hermes_home, payload=payload)
        state_path = Path(first["state_path"])
        stub_path = Path(first["stub_path"])
        original_stub = stub_path.read_text(encoding="utf-8")
        original_memory = memory_path.read_text(encoding="utf-8")
        drifted_state = json.loads(state_path.read_text(encoding="utf-8"))
        drifted_state.pop("notion-ref", None)
        state_path.write_text(json.dumps(drifted_state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        repaired = mod.write_managed_memory_stubs(hermes_home=hermes_home, payload=payload)
        expect(bool(repaired.get("state_changed")) is True, str(repaired))
        expect(bool(repaired.get("stub_changed")) is False, str(repaired))
        expect(bool(repaired.get("memory_changed")) is False, str(repaired))

        repaired_state = json.loads(state_path.read_text(encoding="utf-8"))
        expect("notion-ref" in repaired_state, repaired_state)
        expect("today-plate" in repaired_state, repaired_state)
        expect("notion.search / notion.fetch / notion.query" in repaired_state["notion-ref"], repaired_state)
        expect(stub_path.read_text(encoding="utf-8") == original_stub, "stub mirror should stay unchanged when only state drifted")
        expect(memory_path.read_text(encoding="utf-8") == original_memory, "MEMORY.md should stay unchanged when only state drifted")
        print("PASS test_write_managed_memory_stubs_repairs_matching_cache_key_state_drift")


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
                    "Status": {"type": "status", "status": {"name": "In Progress"}},
                    "Priority": {"type": "select", "select": {"name": "High"}},
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
            notion_stub_cache: dict[str, object] = {}
            stub = mod._build_notion_stub(conn, agent_row=agent_row, identity=identity, notion_stub_cache=notion_stub_cache)
            expect("Own Task" in stub, stub)
            expect("Other Task" not in stub, stub)
            expect("Alex" not in stub, stub)
            expect("Largest current owner loads:" in stub, stub)
            plate = mod._build_today_plate(conn, agent_row=agent_row, identity=identity, notion_stub_cache=notion_stub_cache)
            expect("Today plate:" in plate, plate)
            expect("Verification: confirmed for chris@example.com" in plate, plate)
            expect("Scoped work: 1 owned/assigned record(s)." in plate, plate)
            expect("Due today/overdue: 1" in plate, plate)
            expect("Own Task" in plate, plate)
            expect("status In Progress" in plate, plate)
            expect("priority High" in plate, plate)
            expect("overdue 2026-04-21" in plate, plate)
            expect("Other Task" not in plate, plate)
            expect("Alex" not in plate, plate)
            expect("NEW since last plate" not in plate, plate)
            expect(notion_stub_cache.get("today-plate-ids:agent-test") == ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"], notion_stub_cache)
            new_plate = mod._build_today_plate(
                conn,
                agent_row=agent_row,
                identity=identity,
                notion_stub_cache=notion_stub_cache,
                previous_item_ids=["old-task"],
            )
            expect("Own Task" in new_plate, new_plate)
            expect("NEW since last plate" in new_plate, new_plate)
            stable_plate = mod._build_today_plate(
                conn,
                agent_row=agent_row,
                identity=identity,
                notion_stub_cache=notion_stub_cache,
                previous_item_ids=["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"],
            )
            expect("NEW since last plate" not in stable_plate, stable_plate)
            managed_payload = mod.build_managed_memory_payload(
                conn,
                cfg,
                agent_id="agent-test",
                notion_stub_cache={},
                previous_today_plate_item_ids=["old-task"],
            )
            expect(managed_payload.get("today_plate_item_ids") == ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"], managed_payload)
            expect("NEW since last plate" in managed_payload["today-plate"], managed_payload["today-plate"])
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
            expect("Current rail map:" in stub, stub)
            print("PASS test_managed_notion_stub_reports_pending_claim_status")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_managed_notion_stub_reports_pending_write_approvals() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_memory_sync_pending_ssot_write_test")
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
            pending_row, _ = mod.request_ssot_pending_write(
                conn,
                agent_id="agent-test",
                unix_user="testuser",
                notion_user_id="11111111-1111-1111-1111-111111111111",
                operation="append",
                target_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                payload={"children": [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": []}}]},
                requested_by_actor="agent-test",
                request_source="scope-mismatch",
                request_reason="outside edit lane",
                owner_identity="22222222-2222-2222-2222-222222222222",
                owner_source="ownership-mismatch",
                ttl_seconds=cfg.ssot_pending_write_ttl_seconds,
            )
            mod.retrieve_notion_database = lambda **kwargs: {
                "id": "12345678-90ab-cdef-1234-567890abcdef",
                "properties": {"Owner": {"type": "people"}},
            }
            mod.query_notion_collection = lambda **kwargs: {"result": {"results": []}}
            agent_row = conn.execute("SELECT * FROM agents WHERE agent_id = 'agent-test'").fetchone()
            identity = mod.get_agent_identity(conn, agent_id="agent-test", unix_user="testuser")
            stub = mod._build_notion_stub(conn, agent_row=agent_row, identity=identity)
            expect("Pending shared-write approvals: 1." in stub, stub)
            expect(str(pending_row["pending_id"]) in stub, stub)
            expect("Use ssot.pending for live status" in stub, stub)
            expect("append aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in stub, stub)
            print("PASS test_managed_notion_stub_reports_pending_write_approvals")
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
            expect("Current SSOT shape: page-scoped." in stub, stub)
            expect("Verification: confirmed for chris@example.com." in stub, stub)
            expect("Shared brokered reads and writes are enabled within your scoped rails." in stub, stub)
            expect("Plain child pages can be more fragile under strict scope checks." in stub, stub)
            expect("do not describe that as the skill being missing or the rail disappearing" in stub, stub)
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
    test_curator_fanout_skips_refresh_signal_when_payload_cache_matches()
    test_curator_fanout_retries_failed_agent_without_dropping_work()
    test_curator_fanout_reuses_shared_notions_snapshot_cache_per_batch()
    test_write_managed_memory_stubs_skips_local_rewrites_on_cache_hit()
    test_write_managed_memory_stubs_repairs_matching_cache_key_state_drift()
    test_managed_notion_stub_stays_scoped_to_verified_user()
    test_managed_notion_stub_reports_pending_claim_status()
    test_managed_notion_stub_reports_pending_write_approvals()
    test_managed_notion_stub_reports_verified_page_scoped_write_access()
    test_managed_notion_stub_reports_verification_not_started()
    print("PASS all 11 memory sync regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
