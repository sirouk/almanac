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
            expect("Credentials are intentionally omitted from managed memory." in managed_payload["resource-ref"], managed_payload["resource-ref"])
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


def main() -> int:
    test_curator_fanout_writes_managed_payload_and_activation_trigger()
    print("PASS all 1 memory sync regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
