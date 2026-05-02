#!/usr/bin/env python3
from __future__ import annotations

import getpass
import importlib.util
import json
import os
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTROL_PY = REPO / "python" / "arclink_control.py"


def load_control():
    spec = importlib.util.spec_from_file_location("arclink_control_agent_mcp_auth_test", CONTROL_PY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_config(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n", encoding="utf-8")


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
    }


def insert_active_agent(mod, conn: sqlite3.Connection, *, unix_user: str, hermes_home: Path) -> None:
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
            "agent-auth",
            "user",
            unix_user,
            "Auth Test",
            "active",
            str(hermes_home),
            str(hermes_home / "state" / "manifest.json"),
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


def test_agent_mcp_bootstrap_token_repair_is_shared_and_idempotent() -> None:
    mod = load_control()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            unix_user = getpass.getuser()
            hermes_home = root / "home" / ".local" / "share" / "arclink-agent" / "hermes-home"
            insert_active_agent(mod, conn, unix_user=unix_user, hermes_home=hermes_home)

            first = mod.ensure_agent_mcp_bootstrap_token(
                conn,
                unix_user=unix_user,
                hermes_home=hermes_home,
                actor="docker-agent-supervisor",
            )
            token_file = hermes_home / "secrets" / "arclink-bootstrap-token"
            expect(first["changed"] is True, str(first))
            expect(token_file.is_file(), f"expected token file at {token_file}")
            expect(stat.S_IMODE(token_file.stat().st_mode) & 0o077 == 0, oct(token_file.stat().st_mode))
            raw_token = token_file.read_text(encoding="utf-8").strip()
            token_row = mod.validate_token(conn, raw_token)
            expect(str(token_row["agent_id"]) == "agent-auth", dict(token_row))

            second = mod.ensure_agent_mcp_bootstrap_token(
                conn,
                unix_user=unix_user,
                hermes_home=hermes_home,
                actor="refresh-agent-install",
            )
            expect(second["changed"] is False, str(second))
            expect(token_file.read_text(encoding="utf-8").strip() == raw_token, "valid token should be preserved")

            token_file.write_text("not-a-valid-token\n", encoding="utf-8")
            repaired = mod.ensure_agent_mcp_bootstrap_token(
                conn,
                unix_user=unix_user,
                hermes_home=hermes_home,
                actor="docker-agent-supervisor",
            )
            expect(repaired["changed"] is True, str(repaired))
            new_raw_token = token_file.read_text(encoding="utf-8").strip()
            expect(new_raw_token and new_raw_token != raw_token, "expected invalid token file to be replaced")
            active = conn.execute(
                "SELECT COUNT(*) AS count FROM bootstrap_tokens WHERE agent_id = ? AND revoked_at IS NULL",
                ("agent-auth",),
            ).fetchone()
            revoked = conn.execute(
                "SELECT COUNT(*) AS count FROM bootstrap_tokens WHERE agent_id = ? AND revoked_at IS NOT NULL",
                ("agent-auth",),
            ).fetchone()
            expect(int(active["count"]) == 1, str(dict(active)))
            expect(int(revoked["count"]) >= 1, str(dict(revoked)))
            print("PASS test_agent_mcp_bootstrap_token_repair_is_shared_and_idempotent")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_agent_mcp_bootstrap_token_repair_is_shared_and_idempotent()
    print("PASS all 1 agent MCP auth regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
