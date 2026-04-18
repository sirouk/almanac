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


def test_queue_vault_content_notifications_targets_defaulted_and_opted_in_agents() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_vault_notify_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        vault_dir = root / "vault"
        state_dir = root / "state"
        values = {
            "ALMANAC_USER": "almanac",
            "ALMANAC_HOME": str(root / "home-almanac"),
            "ALMANAC_REPO_DIR": str(root / "repo"),
            "ALMANAC_PRIV_DIR": str(root / "priv"),
            "STATE_DIR": str(state_dir),
            "RUNTIME_DIR": str(state_dir / "runtime"),
            "VAULT_DIR": str(vault_dir),
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
            default_subscribed=True,
        )
        write_vault_definition(
            vault_dir / "Teams" / ".vault",
            name="Teams",
            description="Team spaces that require an explicit opt-in",
            owner="operator",
            default_subscribed=False,
        )
        (vault_dir / "Projects" / "roadmap.md").write_text("projects roadmap\n", encoding="utf-8")
        (vault_dir / "Teams" / "meeting-notes.md").write_text("team notes\n", encoding="utf-8")

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            mod.reload_vault_definitions(conn, cfg)

            insert_agent(mod, conn, root, agent_id="agent-default", unix_user="defaultuser", display_name="Default User")
            insert_agent(mod, conn, root, agent_id="agent-optout", unix_user="optoutuser", display_name="Opt-Out User")
            insert_agent(mod, conn, root, agent_id="agent-optin", unix_user="optinuser", display_name="Opt-In User")

            mod.ensure_default_subscriptions(conn, "agent-default")
            mod.ensure_default_subscriptions(conn, "agent-optout")
            mod.ensure_default_subscriptions(conn, "agent-optin")
            mod.set_vault_subscription(conn, agent_id="agent-optout", vault_name="Projects", subscribed=False, source="user")
            mod.set_vault_subscription(conn, agent_id="agent-optin", vault_name="Projects", subscribed=False, source="user")
            mod.set_vault_subscription(conn, agent_id="agent-optin", vault_name="Teams", subscribed=True, source="user")

            result = mod.queue_vault_content_notifications(
                conn,
                cfg,
                changed_paths=[
                    str(vault_dir / "Projects" / "roadmap.md"),
                    str(vault_dir / "Teams" / "meeting-notes.md"),
                ],
                source="test-suite",
            )

            expect(result["queued_notifications"] == 2, result)
            expect(set(result["vaults_changed"]) == {"Projects", "Teams"}, result)
            expect(set(result["agents_notified"]) == {"agent-default", "agent-optin"}, result)
            expect(result["brief_fanout_queued"] is True, result)

            default_notifs = mod.consume_agent_notifications(conn, agent_id="agent-default")
            optout_notifs = mod.consume_agent_notifications(conn, agent_id="agent-optout")
            optin_notifs = mod.consume_agent_notifications(conn, agent_id="agent-optin")

            expect(len(default_notifs) == 1, default_notifs)
            expect(default_notifs[0]["channel_kind"] == "vault-change", default_notifs)
            expect("Projects" in default_notifs[0]["message"], default_notifs)

            expect(optout_notifs == [], optout_notifs)

            expect(len(optin_notifs) == 1, optin_notifs)
            expect(optin_notifs[0]["channel_kind"] == "vault-change", optin_notifs)
            expect("Teams" in optin_notifs[0]["message"], optin_notifs)

            default_trigger = mod.activation_trigger_path(cfg, "agent-default")
            optout_trigger = mod.activation_trigger_path(cfg, "agent-optout")
            optin_trigger = mod.activation_trigger_path(cfg, "agent-optin")
            expect(default_trigger.is_file(), f"missing activation trigger for default subscriber: {default_trigger}")
            expect(not optout_trigger.exists(), f"unexpected activation trigger for opt-out subscriber: {optout_trigger}")
            expect(optin_trigger.is_file(), f"missing activation trigger for opt-in subscriber: {optin_trigger}")

            curator_rows = conn.execute(
                """
                SELECT message
                FROM notification_outbox
                WHERE target_kind = 'curator' AND channel_kind = 'brief-fanout'
                ORDER BY id ASC
                """
            ).fetchall()
            vault_refresh_rows = [
                str(row["message"] or "")
                for row in curator_rows
                if "vault-content-refresh" in str(row["message"] or "")
            ]
            expect(len(vault_refresh_rows) == 1, curator_rows)
            print("PASS test_queue_vault_content_notifications_targets_defaulted_and_opted_in_agents")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_queue_vault_content_notifications_targets_defaulted_and_opted_in_agents()
    print("PASS all 1 vault notification regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
