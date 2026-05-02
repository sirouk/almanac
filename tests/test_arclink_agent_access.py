#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTROL_PY = REPO / "python" / "arclink_control.py"
ACCESS_PY = REPO / "python" / "arclink_agent_access.py"
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
        "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "tui-only",
        "OPERATOR_NOTIFY_CHANNEL_ID": "",
        "ARCLINK_MODEL_PRESET_CODEX": "openai:codex",
        "ARCLINK_MODEL_PRESET_OPUS": "anthropic:claude-opus",
        "ARCLINK_MODEL_PRESET_CHUTES": "chutes:model-router",
        "ARCLINK_CURATOR_CHANNELS": "tui-only",
        "ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "0",
        "ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED": "0",
        "ARCLINK_AGENT_ENABLE_TAILSCALE_SERVE": "0",
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
    control = load_module(CONTROL_PY, "arclink_control")
    access_mod = load_module(ACCESS_PY, "arclink_agent_access_persist")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            hermes_home = root / "home-agent" / ".local" / "share" / "arclink-agent" / "hermes-home"
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
            expect((hermes_home / "state" / "arclink-web-access.json").is_file(), "expected persisted access state file")
            print("PASS test_access_state_persists_password_and_ports")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_access_state_avoids_ports_reserved_by_other_agents() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control")
    access_mod = load_module(ACCESS_PY, "arclink_agent_access_collide")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)

            peer_home = root / "home-peer" / ".local" / "share" / "arclink-agent" / "hermes-home"
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
            (peer_home / "state" / "arclink-web-access.json").write_text(json.dumps(peer_state), encoding="utf-8")

            hermes_home = root / "home-current" / ".local" / "share" / "arclink-agent" / "hermes-home"
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


def test_access_state_uses_tailscale_port_urls_when_enabled() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_tailscale_paths")
    access_mod = load_module(ACCESS_PY, "arclink_agent_access_tailscale_paths")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        values = config_values(root)
        values["ARCLINK_AGENT_ENABLE_TAILSCALE_SERVE"] = "1"
        config_path = root / "config" / "arclink.env"
        write_config(config_path, values)
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            hermes_home = root / "home-current" / ".local" / "share" / "arclink-agent" / "hermes-home"
            hermes_home.mkdir(parents=True, exist_ok=True)
            insert_agent(control, conn, agent_id="agent-current", unix_user="current", hermes_home=hermes_home)
            access_mod.detect_tailscale_dns_name = lambda: "arclink.example.test"

            state = access_mod.ensure_access_state(
                conn,
                cfg,
                agent_id="agent-current",
                unix_user="current",
                hermes_home=hermes_home,
                uid=77,
            )

            expect(state["dashboard_label"] == "agent-current-dash", state)
            expect(state["code_label"] == "agent-current-code", state)
            expect(state["dashboard_url"] == f"https://arclink.example.test:{state['dashboard_proxy_port']}/", state)
            expect(state["code_url"] == f"https://arclink.example.test:{state['code_port']}/", state)
            print("PASS test_access_state_uses_tailscale_port_urls_when_enabled")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_publish_tailscale_https_uses_dedicated_ports() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    access_mod = load_module(ACCESS_PY, "arclink_agent_access_publish_paths")
    calls: list[tuple[str, ...]] = []
    access_mod._run_tailscale_serve = lambda *args: calls.append(tuple(args))
    access_mod.detect_tailscale_dns_name = lambda: "arclink.example.test"
    access = {
        "dashboard_proxy_port": 30011,
        "code_port": 40011,
        "dashboard_label": "agent-alex-dash",
        "code_label": "agent-alex-code",
    }

    updated = access_mod.publish_tailscale_https(dict(access))

    expect(
        ("--bg", "--yes", "--https=30011", "http://127.0.0.1:30011") in calls,
        f"expected dedicated dashboard port publish, saw {calls!r}",
    )
    expect(
        ("--bg", "--yes", "--https=40011", "http://127.0.0.1:40011") in calls,
        f"expected dedicated code port publish, saw {calls!r}",
    )
    expect(updated["dashboard_url"] == "https://arclink.example.test:30011/", updated)
    expect(updated["code_url"] == "https://arclink.example.test:40011/", updated)
    print("PASS test_publish_tailscale_https_uses_dedicated_ports")


def test_clear_tailscale_https_removes_dedicated_ports() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    access_mod = load_module(ACCESS_PY, "arclink_agent_access_clear_paths")
    calls: list[tuple[str, ...]] = []
    access_mod._run_tailscale_serve = lambda *args: calls.append(tuple(args))
    access_mod.shutil_which = lambda program: "/usr/bin/tailscale" if program == "tailscale" else ""

    with tempfile.TemporaryDirectory() as tmp:
        hermes_home = Path(tmp)
        state_dir = hermes_home / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "arclink-web-access.json").write_text(
            json.dumps(
                {
                    "dashboard_label": "agent-alex-dash",
                    "code_label": "agent-alex-code",
                    "dashboard_proxy_port": 30011,
                    "code_port": 40011,
                }
            ),
            encoding="utf-8",
        )

        access_mod.clear_tailscale_https(hermes_home)

    expect(("--https=30011", "off") in calls, f"expected dashboard port cleanup, saw {calls!r}")
    expect(("--https=40011", "off") in calls, f"expected code port cleanup, saw {calls!r}")
    print("PASS test_clear_tailscale_https_removes_dedicated_ports")


def test_docker_port_allocation_skips_host_listeners() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    access_mod = load_module(ACCESS_PY, "arclink_agent_access_docker_port_probe")
    old_env = os.environ.copy()
    os.environ["ARCLINK_DOCKER_MODE"] = "1"
    try:
        access_mod._docker_host_port_is_listening = lambda port: port == 29077
        reserved_now: set[int] = set()
        chosen = access_mod._preserve_or_allocate_port(
            existing=None,
            reserved_other=set(),
            reserved_now=reserved_now,
            base=29000,
            span=5000,
            slot=77,
        )
        expect(chosen != 29077, f"expected occupied host port to be skipped, got {chosen}")
        expect(chosen == 29078, f"expected next coherent port, got {chosen}")
        print("PASS test_docker_port_allocation_skips_host_listeners")
    finally:
        os.environ.clear()
        os.environ.update(old_env)


def main() -> int:
    test_access_state_persists_password_and_ports()
    test_access_state_avoids_ports_reserved_by_other_agents()
    test_access_state_uses_tailscale_port_urls_when_enabled()
    test_publish_tailscale_https_uses_dedicated_ports()
    test_clear_tailscale_https_removes_dedicated_ports()
    test_docker_port_allocation_skips_host_listeners()
    print("PASS all 6 agent-access regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
