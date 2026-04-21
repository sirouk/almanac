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


def write_vault_definition(path: Path, *, name: str, description: str, owner: str, default_subscribed: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"name: {name}",
                f"description: {description}",
                f"owner: {owner}",
                f"default_subscribed: {'true' if default_subscribed else 'false'}",
                "category: workspace",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def insert_agent(mod, conn, root: Path, *, agent_id: str, unix_user: str, display_name: str) -> None:
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
            agent_id,
            "user",
            unix_user,
            display_name,
            "active",
            str(root / f"home-{unix_user}" / ".local" / "share" / "almanac-agent" / "hermes-home"),
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


def test_catalog_default_flip_updates_effective_subscriptions_for_default_rows() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_subscription_hierarchy_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        vault_dir = root / "vault"
        values = {
            "ALMANAC_USER": "almanac",
            "ALMANAC_HOME": str(root / "home-almanac"),
            "ALMANAC_REPO_DIR": str(root / "repo"),
            "ALMANAC_PRIV_DIR": str(root / "priv"),
            "STATE_DIR": str(root / "state"),
            "RUNTIME_DIR": str(root / "state" / "runtime"),
            "VAULT_DIR": str(vault_dir),
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
        write_vault_definition(
            vault_dir / "Projects" / ".vault",
            name="Projects",
            description="Active project workspaces",
            owner="operator",
            default_subscribed=False,
        )

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            mod.reload_vault_definitions(conn, cfg)
            insert_agent(mod, conn, root, agent_id="agent-default", unix_user="defaultuser", display_name="Default User")
            mod.ensure_default_subscriptions(conn, "agent-default")

            initial = mod.build_managed_memory_payload(conn, cfg, agent_id="agent-default")
            expect(initial["active_subscriptions"] == [], initial)
            expect(bool(initial["subscriptions"][0]["push_enabled"]) is False, initial["subscriptions"])
            expect(initial["subscriptions"][0]["subscription_state"] == "default-out", initial["subscriptions"])

            write_vault_definition(
                vault_dir / "Projects" / ".vault",
                name="Projects",
                description="Active project workspaces",
                owner="operator",
                default_subscribed=True,
            )
            mod.reload_vault_definitions(conn, cfg)
            updated = mod.build_managed_memory_payload(conn, cfg, agent_id="agent-default")
            expect(updated["active_subscriptions"] == ["Projects"], updated)
            expect(bool(updated["subscriptions"][0]["push_enabled"]) is True, updated["subscriptions"])
            expect(updated["subscriptions"][0]["subscription_state"] == "default-in", updated["subscriptions"])
            expect("default=on" in updated["vault-topology"], updated["vault-topology"])
            print("PASS test_catalog_default_flip_updates_effective_subscriptions_for_default_rows")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_reload_vault_definitions_queues_brief_fanout_on_default_change() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_subscription_default_change_fanout_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        vault_dir = root / "vault"
        values = {
            "ALMANAC_USER": "almanac",
            "ALMANAC_HOME": str(root / "home-almanac"),
            "ALMANAC_REPO_DIR": str(root / "repo"),
            "ALMANAC_PRIV_DIR": str(root / "priv"),
            "STATE_DIR": str(root / "state"),
            "RUNTIME_DIR": str(root / "state" / "runtime"),
            "VAULT_DIR": str(vault_dir),
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
        write_vault_definition(
            vault_dir / "Projects" / ".vault",
            name="Projects",
            description="Active project workspaces",
            owner="operator",
            default_subscribed=False,
        )

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            mod.reload_vault_definitions(conn, cfg)
            insert_agent(mod, conn, root, agent_id="agent-default", unix_user="defaultuser", display_name="Default User")
            mod.ensure_default_subscriptions(conn, "agent-default")
            conn.execute("DELETE FROM notification_outbox")
            conn.commit()

            write_vault_definition(
                vault_dir / "Projects" / ".vault",
                name="Projects",
                description="Active project workspaces",
                owner="operator",
                default_subscribed=True,
            )
            result = mod.reload_vault_definitions(conn, cfg)
            expect(result["diff"]["default_subscribed_changed"] == ["Projects"], result)
            fanout = conn.execute(
                """
                SELECT target_id, message
                FROM notification_outbox
                WHERE target_kind = 'curator' AND channel_kind = 'brief-fanout'
                ORDER BY id ASC
                """
            ).fetchall()
            expect(any(str(row["target_id"] or "") == "curator" for row in fanout), str([dict(row) for row in fanout]))
            expect(any("catalog-reload" in str(row["message"] or "") for row in fanout), str([dict(row) for row in fanout]))
            print("PASS test_reload_vault_definitions_queues_brief_fanout_on_default_change")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_catalog_default_flip_updates_effective_subscriptions_for_default_rows()
    test_reload_vault_definitions_queues_brief_fanout_on_default_change()
    print("PASS all 2 subscription hierarchy regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
