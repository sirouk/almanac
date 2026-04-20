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
ACCESS_PY = REPO / "python" / "almanac_agent_access.py"
PYTHON_DIR = REPO / "python"


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
        "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "tui-only",
        "OPERATOR_NOTIFY_CHANNEL_ID": "",
        "ALMANAC_MODEL_PRESET_CODEX": "openai:codex",
        "ALMANAC_MODEL_PRESET_OPUS": "anthropic:claude-opus",
        "ALMANAC_MODEL_PRESET_CHUTES": "chutes:auto-failover",
        "ALMANAC_CURATOR_CHANNELS": "tui-only",
        "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "0",
        "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED": "0",
        "ALMANAC_AGENT_ENABLE_TAILSCALE_SERVE": "0",
    }


def insert_agent(mod, conn, *, agent_id: str, unix_user: str, hermes_home: Path) -> None:
    now = mod.utc_now_iso()
    conn.execute(
        """
        INSERT INTO agents (
          agent_id, role, unix_user, display_name, status, hermes_home, manifest_path,
          archived_state_path, model_preset, model_string, channels_json,
          allowed_mcps_json, home_channel_json, operator_notify_channel_json,
          created_at, last_enrolled_at
        ) VALUES (?, 'user', ?, ?, 'active', ?, ?, NULL, 'codex', 'openai:codex', '["tui-only"]', '[]', '{}', '{}', ?, ?)
        """,
        (agent_id, unix_user, unix_user, str(hermes_home), str(hermes_home / "manifest.json"), now, now),
    )
    conn.commit()


def test_access_state_persists_password_and_ports() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control")
    access_mod = load_module(ACCESS_PY, "almanac_agent_access_persist")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            hermes_home = root / "home-agent" / ".local" / "share" / "almanac-agent" / "hermes-home"
            hermes_home.mkdir(parents=True, exist_ok=True)
            insert_agent(control, conn, agent_id="agent-one", unix_user="agentone", hermes_home=hermes_home)

            first = access_mod.ensure_access_state(
                conn,
                cfg,
                agent_id="agent-one",
                unix_user="agentone",
                hermes_home=hermes_home,
                uid=os.getuid(),
            )
            second = access_mod.ensure_access_state(
                conn,
                cfg,
                agent_id="agent-one",
                unix_user="agentone",
                hermes_home=hermes_home,
                uid=os.getuid(),
            )

            expect(first["password"] == second["password"], f"password should persist: {first} vs {second}")
            expect(first["dashboard_proxy_port"] == second["dashboard_proxy_port"], f"dashboard port should persist: {first} vs {second}")
            expect((hermes_home / "state" / "almanac-web-access.json").is_file(), "expected persisted access state file")
            print("PASS test_access_state_persists_password_and_ports")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_access_state_avoids_ports_reserved_by_other_agents() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control")
    access_mod = load_module(ACCESS_PY, "almanac_agent_access_collide")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)

            peer_home = root / "home-peer" / ".local" / "share" / "almanac-agent" / "hermes-home"
            peer_home.mkdir(parents=True, exist_ok=True)
            insert_agent(control, conn, agent_id="agent-peer", unix_user="peeruser", hermes_home=peer_home)
            peer_state = {
                "dashboard_backend_port": 19077,
                "dashboard_proxy_port": 29077,
                "code_port": 39077,
                "username": "peeruser",
                "password": "peerpass",
            }
            (peer_home / "state").mkdir(parents=True, exist_ok=True)
            (peer_home / "state" / "almanac-web-access.json").write_text(json.dumps(peer_state), encoding="utf-8")

            hermes_home = root / "home-current" / ".local" / "share" / "almanac-agent" / "hermes-home"
            hermes_home.mkdir(parents=True, exist_ok=True)
            insert_agent(control, conn, agent_id="agent-current", unix_user="current", hermes_home=hermes_home)

            state = access_mod.ensure_access_state(
                conn,
                cfg,
                agent_id="agent-current",
                unix_user="current",
                hermes_home=hermes_home,
                uid=77,
            )

            expect(state["dashboard_backend_port"] != 19077, f"expected collision avoidance for dashboard backend: {state}")
            expect(state["dashboard_proxy_port"] != 29077, f"expected collision avoidance for dashboard proxy: {state}")
            expect(state["code_port"] != 39077, f"expected collision avoidance for code port: {state}")
            print("PASS test_access_state_avoids_ports_reserved_by_other_agents")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_access_state_persists_password_and_ports()
    test_access_state_avoids_ports_reserved_by_other_agents()
    print("PASS all 2 agent-access regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
