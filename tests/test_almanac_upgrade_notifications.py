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


def test_upgrade_check_notifies_operator_and_user_agents_once_per_sha() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_upgrade_notification_test")
    ctl = load_module(CTL_PY, "almanac_ctl_upgrade_notification_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state_dir = root / "state"
        release_state_file = state_dir / "almanac-release.json"
        config_path = root / "config" / "almanac.env"
        write_config(
            config_path,
            {
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
                "ALMANAC_RELEASE_STATE_FILE": str(release_state_file),
                "ALMANAC_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ALMANAC_MCP_HOST": "127.0.0.1",
                "ALMANAC_MCP_PORT": "8282",
                "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "telegram",
                "OPERATOR_NOTIFY_CHANNEL_ID": "1994645819",
            },
        )
        release_state_file.parent.mkdir(parents=True, exist_ok=True)
        release_state_file.write_text(
            json.dumps(
                {
                    "deployed_commit": "aaaaaaaaaaaa1111111111111111111111111111",
                    "tracked_upstream_repo_url": "https://github.com/example/almanac.git",
                    "tracked_upstream_branch": "main",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
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
                    str(root / "home-upgradeuser" / ".local" / "share" / "almanac-agent" / "hermes-home"),
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

            ctl._query_upstream_head = lambda repo_url, branch: "bbbbbbbbbbbb2222222222222222222222222222"
            ctl._classify_upstream_relation = lambda *args, **kwargs: "behind"
            result = ctl.upgrade_check(conn, cfg, actor="test", notify=True)
            expect(result["notification_sent"] is True, result)
            expect(result["relation"] == "behind", result)

            operator_rows = conn.execute(
                "SELECT message FROM notification_outbox WHERE target_kind = 'operator' ORDER BY id ASC"
            ).fetchall()
            expect(len(operator_rows) == 1, operator_rows)
            expect("Almanac update available" in str(operator_rows[0]["message"] or ""), operator_rows)

            agent_rows = conn.execute(
                """
                SELECT message
                FROM notification_outbox
                WHERE target_kind = 'user-agent' AND channel_kind = 'almanac-upgrade'
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


def test_upgrade_check_does_not_notify_when_deployed_is_ahead() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_upgrade_ahead_test")
    ctl = load_module(CTL_PY, "almanac_ctl_upgrade_ahead_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state_dir = root / "state"
        release_state_file = state_dir / "almanac-release.json"
        config_path = root / "config" / "almanac.env"
        write_config(
            config_path,
            {
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
                "ALMANAC_RELEASE_STATE_FILE": str(release_state_file),
                "ALMANAC_QMD_URL": "http://127.0.0.1:8181/mcp",
                "ALMANAC_MCP_HOST": "127.0.0.1",
                "ALMANAC_MCP_PORT": "8282",
                "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "telegram",
                "OPERATOR_NOTIFY_CHANNEL_ID": "1994645819",
            },
        )
        release_state_file.parent.mkdir(parents=True, exist_ok=True)
        release_state_file.write_text(
            json.dumps(
                {
                    "deployed_commit": "aaaaaaaaaaaa1111111111111111111111111111",
                    "tracked_upstream_repo_url": "https://github.com/example/almanac.git",
                    "tracked_upstream_branch": "main",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            ctl._query_upstream_head = lambda repo_url, branch: "bbbbbbbbbbbb2222222222222222222222222222"
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


def main() -> int:
    test_upgrade_check_notifies_operator_and_user_agents_once_per_sha()
    test_upgrade_check_does_not_notify_when_deployed_is_ahead()
    print("PASS all 2 upgrade notification regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
