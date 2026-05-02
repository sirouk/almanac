#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
CONTROL_PY = PYTHON_DIR / "arclink_control.py"
CTL_PY = PYTHON_DIR / "arclink_ctl.py"


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


def test_upgrade_check_notifies_operator_and_user_agents_once_per_sha() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_upgrade_notification_test")
    ctl = load_module(CTL_PY, "arclink_ctl_upgrade_notification_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state_dir = root / "state"
        release_state_file = state_dir / "arclink-release.json"
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(state_dir),
                "RUNTIME_DIR": str(state_dir / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ARCLINK_DB_PATH": str(state_dir / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(state_dir / "agents"),
                "ARCLINK_CURATOR_DIR": str(state_dir / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(state_dir / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(state_dir / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(state_dir / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(release_state_file),
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ARCLINK_MCP_HOST": "127.0.0.1",
                "ARCLINK_MCP_PORT": "8282",
                "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "telegram",
                "OPERATOR_NOTIFY_CHANNEL_ID": "1000000001",
            },
        )
        release_state_file.parent.mkdir(parents=True, exist_ok=True)
        release_state_file.write_text(
            json.dumps(
                {
                    "deployed_commit": "aaaaaaaaaaaa1111111111111111111111111111",
                    "tracked_upstream_repo_url": "https://github.com/example/arclink.git",
                    "tracked_upstream_branch": "main",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            now = control.utc_now_iso()
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
                    "agent-upgrade",
                    "user",
                    "upgradeuser",
                    "Upgrade User",
                    "active",
                    str(root / "home-upgradeuser" / ".local" / "share" / "arclink-agent" / "hermes-home"),
                    str(state_dir / "agents" / "agent-upgrade" / "manifest.json"),
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

            ctl._query_upstream_head = lambda repo_url, branch, env=None: "bbbbbbbbbbbb2222222222222222222222222222"
            ctl._classify_upstream_relation = lambda *args, **kwargs: "behind"
            result = ctl.upgrade_check(conn, cfg, actor="test", notify=True)
            expect(result["notification_sent"] is True, result)
            expect(result["relation"] == "behind", result)

            operator_rows = conn.execute(
                "SELECT message, extra_json FROM notification_outbox WHERE target_kind = 'operator' ORDER BY id ASC"
            ).fetchall()
            expect(len(operator_rows) == 1, operator_rows)
            expect("ArcLink update available" in str(operator_rows[0]["message"] or ""), operator_rows)
            operator_extra = json.loads(str(operator_rows[0]["extra_json"] or "{}"))
            buttons = operator_extra.get("telegram_reply_markup", {}).get("inline_keyboard", [[]])[0]
            expect([button.get("text") for button in buttons] == ["Dismiss", "Install"], str(operator_extra))

            agent_rows = conn.execute(
                """
                SELECT message
                FROM notification_outbox
                WHERE target_kind = 'user-agent' AND channel_kind = 'arclink-upgrade'
                ORDER BY id ASC
                """
            ).fetchall()
            expect(len(agent_rows) == 1, agent_rows)
            expect("shared infrastructure will be refreshed" in str(agent_rows[0]["message"] or ""), agent_rows)

            trigger_path = control.activation_trigger_path(cfg, "agent-upgrade")
            expect(trigger_path.is_file(), f"expected upgrade nudge to trigger agent refresh at {trigger_path}")
            print("PASS test_upgrade_check_notifies_operator_and_user_agents_once_per_sha")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_upgrade_check_adds_discord_buttons_for_operator_channel() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_upgrade_notification_discord_test")
    ctl = load_module(CTL_PY, "arclink_ctl_upgrade_notification_discord_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state_dir = root / "state"
        release_state_file = state_dir / "arclink-release.json"
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(state_dir),
                "RUNTIME_DIR": str(state_dir / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ARCLINK_DB_PATH": str(state_dir / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(state_dir / "agents"),
                "ARCLINK_CURATOR_DIR": str(state_dir / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(state_dir / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(state_dir / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(state_dir / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(release_state_file),
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ARCLINK_MCP_HOST": "127.0.0.1",
                "ARCLINK_MCP_PORT": "8282",
                "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "discord",
                "OPERATOR_NOTIFY_CHANNEL_ID": "123456789012345678",
                "ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED": "1",
            },
        )
        release_state_file.parent.mkdir(parents=True, exist_ok=True)
        release_state_file.write_text(
            json.dumps(
                {
                    "deployed_commit": "aaaaaaaaaaaa1111111111111111111111111111",
                    "tracked_upstream_repo_url": "https://github.com/example/arclink.git",
                    "tracked_upstream_branch": "main",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            ctl._query_upstream_head = lambda repo_url, branch, env=None: "bbbbbbbbbbbb2222222222222222222222222222"
            ctl._classify_upstream_relation = lambda *args, **kwargs: "behind"
            result = ctl.upgrade_check(conn, cfg, actor="test", notify=True)
            expect(result["notification_sent"] is True, result)
            operator_row = conn.execute(
                "SELECT extra_json FROM notification_outbox WHERE target_kind = 'operator' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            extra = json.loads(str(operator_row["extra_json"] or "{}"))
            components = extra.get("discord_components") or []
            expect(len(components) == 1, str(extra))
            buttons = components[0].get("components") or []
            expect([button.get("label") for button in buttons] == ["Dismiss", "Install"], str(extra))
            print("PASS test_upgrade_check_adds_discord_buttons_for_operator_channel")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_upgrade_check_notifies_when_deployed_commit_is_unknown_but_differs() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_upgrade_different_test")
    ctl = load_module(CTL_PY, "arclink_ctl_upgrade_different_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state_dir = root / "state"
        release_state_file = state_dir / "arclink-release.json"
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(state_dir),
                "RUNTIME_DIR": str(state_dir / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ARCLINK_DB_PATH": str(state_dir / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(state_dir / "agents"),
                "ARCLINK_CURATOR_DIR": str(state_dir / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(state_dir / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(state_dir / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(state_dir / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(release_state_file),
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ARCLINK_MCP_HOST": "127.0.0.1",
                "ARCLINK_MCP_PORT": "8282",
                "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "telegram",
                "OPERATOR_NOTIFY_CHANNEL_ID": "1000000001",
            },
        )
        release_state_file.parent.mkdir(parents=True, exist_ok=True)
        release_state_file.write_text(
            json.dumps(
                {
                    "deployed_commit": "0000000000000000000000000000000000000000",
                    "tracked_upstream_repo_url": "https://github.com/example/arclink.git",
                    "tracked_upstream_branch": "main",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            ctl._query_upstream_head = lambda repo_url, branch, env=None: "bbbbbbbbbbbb2222222222222222222222222222"
            ctl._classify_upstream_relation = lambda *args, **kwargs: "different"
            result = ctl.upgrade_check(conn, cfg, actor="test", notify=True)

            expect(result["update_available"] is True, result)
            expect(result["notification_sent"] is True, result)
            expect(result["relation"] == "different", result)

            outbox_count = conn.execute("SELECT COUNT(*) AS count FROM notification_outbox").fetchone()["count"]
            expect(outbox_count == 1, f"expected one queued notification for differing deployed commit, found {outbox_count}")
            print("PASS test_upgrade_check_notifies_when_deployed_commit_is_unknown_but_differs")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_upgrade_check_does_not_notify_when_deployed_is_ahead() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_upgrade_ahead_test")
    ctl = load_module(CTL_PY, "arclink_ctl_upgrade_ahead_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state_dir = root / "state"
        release_state_file = state_dir / "arclink-release.json"
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(state_dir),
                "RUNTIME_DIR": str(state_dir / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ARCLINK_DB_PATH": str(state_dir / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(state_dir / "agents"),
                "ARCLINK_CURATOR_DIR": str(state_dir / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(state_dir / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(state_dir / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(state_dir / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(release_state_file),
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ARCLINK_MCP_HOST": "127.0.0.1",
                "ARCLINK_MCP_PORT": "8282",
                "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "telegram",
                "OPERATOR_NOTIFY_CHANNEL_ID": "1000000001",
            },
        )
        release_state_file.parent.mkdir(parents=True, exist_ok=True)
        release_state_file.write_text(
            json.dumps(
                {
                    "deployed_commit": "aaaaaaaaaaaa1111111111111111111111111111",
                    "tracked_upstream_repo_url": "https://github.com/example/arclink.git",
                    "tracked_upstream_branch": "main",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            ctl._query_upstream_head = lambda repo_url, branch, env=None: "bbbbbbbbbbbb2222222222222222222222222222"
            ctl._classify_upstream_relation = lambda *args, **kwargs: "ahead"
            result = ctl.upgrade_check(conn, cfg, actor="test", notify=True)

            expect(result["notification_sent"] is False, result)
            expect(result["update_available"] is False, result)
            expect(result["relation"] == "ahead", result)
            expect("ahead of tracked upstream" in str(result["note"] or ""), result)

            outbox_count = conn.execute("SELECT COUNT(*) AS count FROM notification_outbox").fetchone()["count"]
            expect(outbox_count == 0, f"expected no queued notifications, found {outbox_count}")
            print("PASS test_upgrade_check_does_not_notify_when_deployed_is_ahead")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_upgrade_check_suppresses_update_notification_during_deploy_operation() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_upgrade_deploy_suppression_test")
    ctl = load_module(CTL_PY, "arclink_ctl_upgrade_deploy_suppression_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state_dir = root / "state"
        release_state_file = state_dir / "arclink-release.json"
        config_path = root / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(state_dir),
                "RUNTIME_DIR": str(state_dir / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ARCLINK_DB_PATH": str(state_dir / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(state_dir / "agents"),
                "ARCLINK_CURATOR_DIR": str(state_dir / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(state_dir / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(state_dir / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(state_dir / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(release_state_file),
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ARCLINK_MCP_HOST": "127.0.0.1",
                "ARCLINK_MCP_PORT": "8282",
                "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "telegram",
                "OPERATOR_NOTIFY_CHANNEL_ID": "1000000001",
            },
        )
        release_state_file.parent.mkdir(parents=True, exist_ok=True)
        release_state_file.write_text(
            json.dumps(
                {
                    "deployed_commit": "aaaaaaaaaaaa1111111111111111111111111111",
                    "tracked_upstream_repo_url": "https://github.com/example/arclink.git",
                    "tracked_upstream_branch": "main",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        marker = state_dir / "arclink-deploy-operation.json"
        marker.write_text(
            json.dumps(
                {
                    "operation": "upgrade",
                    "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1))
                    .isoformat()
                    .replace("+00:00", "Z"),
                }
            )
            + "\n",
            encoding="utf-8",
        )

        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            ctl._query_upstream_head = lambda repo_url, branch, env=None: "bbbbbbbbbbbb2222222222222222222222222222"
            ctl._classify_upstream_relation = lambda *args, **kwargs: "behind"
            result = ctl.upgrade_check(conn, cfg, actor="test", notify=True)

            expect(result["update_available"] is True, result)
            expect(result["notification_sent"] is False, result)
            expect(result["notification_suppressed"] is True, result)
            expect(result["notification_suppressed_reason"] == "deploy-operation-active", result)
            expect(result["deploy_operation_active"] is True, result)
            expect(result["deploy_operation"]["operation"] == "upgrade", result)

            outbox_count = conn.execute("SELECT COUNT(*) AS count FROM notification_outbox").fetchone()["count"]
            expect(outbox_count == 0, f"expected deploy operation marker to suppress update notification, found {outbox_count}")
            last_notified = control.get_setting(conn, "arclink_upgrade_last_notified_sha", "")
            expect(last_notified == "", f"suppressed notifications must not advance dedupe state, got {last_notified!r}")
            print("PASS test_upgrade_check_suppresses_update_notification_during_deploy_operation")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_upgrade_check_uses_configured_upstream_deploy_key_for_ssh_remotes() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_upgrade_deploy_key_test")
    ctl = load_module(CTL_PY, "arclink_ctl_upgrade_deploy_key_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        key_path = root / ".ssh" / "arclink-upstream-ed25519"
        known_hosts = root / ".ssh" / "arclink-upstream-known_hosts"
        write_config(
            config_path,
            {
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
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ARCLINK_MCP_HOST": "127.0.0.1",
                "ARCLINK_MCP_PORT": "8282",
                "ARCLINK_UPSTREAM_REPO_URL": "git@github.com:example/arclink.git",
                "ARCLINK_UPSTREAM_BRANCH": "main",
                "ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED": "1",
                "ARCLINK_UPSTREAM_DEPLOY_KEY_PATH": str(key_path),
                "ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE": str(known_hosts),
            },
        )

        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            git_env = ctl._upstream_git_env(cfg, "git@github.com:example/arclink.git")
            expect(git_env is not None, "expected SSH deploy-key env for configured upstream")
            ssh_command = str(git_env["GIT_SSH_COMMAND"])
            expect(str(key_path) in ssh_command, ssh_command)
            expect(str(known_hosts) in ssh_command, ssh_command)
            expect("-o BatchMode=yes" in ssh_command, ssh_command)
            expect("-o IPQoS=none" in ssh_command, ssh_command)
            expect("-o IdentitiesOnly=yes" in ssh_command, ssh_command)
            expect(
                ctl._upstream_git_env(cfg, "https://github.com/example/arclink.git") is None,
                "HTTPS remotes should not get SSH deploy-key env",
            )
            print("PASS test_upgrade_check_uses_configured_upstream_deploy_key_for_ssh_remotes")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_upgrade_check_falls_back_to_https_when_operator_deploy_key_is_not_service_readable() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_upgrade_https_fallback_test")
    ctl = load_module(CTL_PY, "arclink_ctl_upgrade_https_fallback_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state_dir = root / "state"
        release_state_file = state_dir / "arclink-release.json"
        config_path = root / "config" / "arclink.env"
        key_path = root / "operator-home" / ".ssh" / "arclink-upstream-ed25519"
        known_hosts = root / "operator-home" / ".ssh" / "arclink-upstream-known_hosts"
        deployed_sha = "1481ef8d391794d31bb04efe233a7c3f2a810947"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(state_dir),
                "RUNTIME_DIR": str(state_dir / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ARCLINK_DB_PATH": str(state_dir / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(state_dir / "agents"),
                "ARCLINK_CURATOR_DIR": str(state_dir / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(state_dir / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(state_dir / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(state_dir / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(release_state_file),
                "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ARCLINK_MCP_HOST": "127.0.0.1",
                "ARCLINK_MCP_PORT": "8282",
                "ARCLINK_UPSTREAM_REPO_URL": "git@github.com:example/arclink.git",
                "ARCLINK_UPSTREAM_BRANCH": "main",
                "ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED": "1",
                "ARCLINK_UPSTREAM_DEPLOY_KEY_PATH": str(key_path),
                "ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE": str(known_hosts),
            },
        )
        release_state_file.parent.mkdir(parents=True, exist_ok=True)
        release_state_file.write_text(
            json.dumps(
                {
                    "deployed_commit": deployed_sha,
                    "tracked_upstream_repo_url": "git@github.com:example/arclink.git",
                    "tracked_upstream_branch": "main",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        calls: list[tuple[str, str, bool]] = []

        def fake_query(repo_url: str, branch: str, env=None):
            calls.append((repo_url, branch, env is not None))
            if repo_url == "git@github.com:example/arclink.git":
                raise RuntimeError("operator deploy key is not readable by service user")
            if repo_url == "https://github.com/example/arclink.git":
                return deployed_sha
            raise AssertionError(f"unexpected repo url {repo_url}")

        def fake_classify(repo_dir: Path, repo_url: str, branch: str, deployed_commit: str, upstream_commit: str) -> str:
            expect(repo_url == "https://github.com/example/arclink.git", repo_url)
            expect(branch == "main", branch)
            expect(deployed_commit == deployed_sha, deployed_commit)
            expect(upstream_commit == deployed_sha, upstream_commit)
            return "equal"

        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            ctl._query_upstream_head = fake_query
            ctl._classify_upstream_relation = fake_classify
            result = ctl.upgrade_check(conn, cfg, actor="test", notify=True)
            expect(result["status"] == "ok", result)
            expect(result["relation"] == "equal", result)
            expect(result["upstream_query_url"] == "https://github.com/example/arclink.git", result)
            expect(result["upstream_transport_fallback"] == "https", result)
            expect(calls == [
                ("git@github.com:example/arclink.git", "main", True),
                ("https://github.com/example/arclink.git", "main", False),
            ], calls)
            job = conn.execute(
                "SELECT last_status, last_note FROM refresh_jobs WHERE job_name = 'arclink-upgrade-check'"
            ).fetchone()
            expect(job["last_status"] == "ok", dict(job))
            expect("up to date" in str(job["last_note"] or ""), dict(job))
            print("PASS test_upgrade_check_falls_back_to_https_when_operator_deploy_key_is_not_service_readable")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_query_upstream_head_uses_safe_working_directory() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    ctl = load_module(CTL_PY, "arclink_ctl_upgrade_query_cwd_test")
    seen: dict[str, object] = {}

    def fake_run(args, **kwargs):
        seen["args"] = list(args)
        seen["cwd"] = kwargs.get("cwd")
        seen["env"] = kwargs.get("env")
        return type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": "bbbbbbbbbbbb2222222222222222222222222222\trefs/heads/main\n",
                "stderr": "",
            },
        )()

    original_run = ctl.subprocess.run
    ctl.subprocess.run = fake_run
    try:
        sha = ctl._query_upstream_head("https://github.com/example/arclink.git", "main", None)
    finally:
        ctl.subprocess.run = original_run
    expect(sha == "bbbbbbbbbbbb2222222222222222222222222222", sha)
    expect(seen.get("cwd") == "/", str(seen))
    env = seen.get("env")
    expect(isinstance(env, dict), str(seen))
    expect(env["GIT_TERMINAL_PROMPT"] == "0", str(env))
    expect(env["GIT_ASKPASS"] == "/bin/false", str(env))
    expect(env["SSH_ASKPASS"] == "/bin/false", str(env))
    expect(env["GCM_INTERACTIVE"] == "Never", str(env))
    print("PASS test_query_upstream_head_uses_safe_working_directory")


def test_upgrade_check_git_run_disables_interactive_auth_prompts() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    ctl = load_module(CTL_PY, "arclink_ctl_upgrade_git_run_prompt_env_test")
    seen: dict[str, object] = {}

    def fake_run(args, **kwargs):
        seen["args"] = list(args)
        seen["env"] = kwargs.get("env")
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    original_run = ctl.subprocess.run
    ctl.subprocess.run = fake_run
    try:
        ctl._git_run(REPO, "fetch", "origin", "main")
    finally:
        ctl.subprocess.run = original_run
    env = seen.get("env")
    expect(isinstance(env, dict), str(seen))
    expect(env["GIT_TERMINAL_PROMPT"] == "0", str(env))
    expect(env["GIT_ASKPASS"] == "/bin/false", str(env))
    expect(env["SSH_ASKPASS"] == "/bin/false", str(env))
    expect(env["GCM_INTERACTIVE"] == "Never", str(env))
    expect("BatchMode=yes" in env["GIT_SSH_COMMAND"], str(env))
    print("PASS test_upgrade_check_git_run_disables_interactive_auth_prompts")


def main() -> int:
    test_upgrade_check_notifies_operator_and_user_agents_once_per_sha()
    test_upgrade_check_adds_discord_buttons_for_operator_channel()
    test_upgrade_check_notifies_when_deployed_commit_is_unknown_but_differs()
    test_upgrade_check_does_not_notify_when_deployed_is_ahead()
    test_upgrade_check_suppresses_update_notification_during_deploy_operation()
    test_upgrade_check_uses_configured_upstream_deploy_key_for_ssh_remotes()
    test_upgrade_check_falls_back_to_https_when_operator_deploy_key_is_not_service_readable()
    test_query_upstream_head_uses_safe_working_directory()
    test_upgrade_check_git_run_disables_interactive_auth_prompts()
    print("PASS all 9 upgrade notification regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
