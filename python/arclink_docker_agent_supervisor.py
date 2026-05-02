#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pwd
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from arclink_control import Config, connect_db, ensure_agent_mcp_bootstrap_token, json_loads


STOP = False
SAFE_PATH = "/home/arclink/.local/bin:/opt/arclink/runtime/hermes-venv/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin"


def _stop(_signum, _frame) -> None:
    global STOP
    STOP = True


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)


def docker_mode_env(cfg: Config) -> dict[str, str]:
    return {
        "PATH": SAFE_PATH,
        "ARCLINK_DOCKER_MODE": "1",
        "ARCLINK_AGENT_SERVICE_MANAGER": "docker-supervisor",
        "ARCLINK_CONTAINER_RUNTIME": "docker",
        "ARCLINK_CONFIG_FILE": str(os.environ.get("ARCLINK_CONFIG_FILE") or cfg.private_dir / "config" / "docker.env"),
        "ARCLINK_REPO_DIR": str(cfg.repo_dir),
        "ARCLINK_PRIV_DIR": str(cfg.private_dir),
        "ARCLINK_AGENTS_STATE_DIR": str(cfg.agents_state_dir),
        "ARCLINK_AGENT_VAULT_DIR": str(cfg.vault_dir),
        "ARCLINK_MCP_URL": str(os.environ.get("ARCLINK_MCP_URL") or "http://arclink-mcp:8282/mcp"),
        "ARCLINK_BOOTSTRAP_URL": str(os.environ.get("ARCLINK_BOOTSTRAP_URL") or "http://arclink-mcp:8282/mcp"),
        "ARCLINK_QMD_URL": str(os.environ.get("ARCLINK_QMD_URL") or "http://qmd-mcp:8181/mcp"),
        "RUNTIME_DIR": str(cfg.runtime_dir),
        "HERMES_BUNDLED_SKILLS": str(cfg.runtime_dir / "hermes-agent-src" / "skills"),
        "ARCLINK_DOCKER_HOST_REPO_DIR": str(os.environ.get("ARCLINK_DOCKER_HOST_REPO_DIR") or ""),
        "ARCLINK_DOCKER_HOST_PRIV_DIR": str(os.environ.get("ARCLINK_DOCKER_HOST_PRIV_DIR") or ""),
        "ARCLINK_DOCKER_IMAGE": str(os.environ.get("ARCLINK_DOCKER_IMAGE") or "arclink/app:local"),
        "ARCLINK_DOCKER_NETWORK": str(os.environ.get("ARCLINK_DOCKER_NETWORK") or "arclink_default"),
    }


def docker_name(value: str, *, fallback: str = "agent") -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return name or fallback


def docker_host_priv_dir(cfg: Config) -> str:
    host_priv = str(os.environ.get("ARCLINK_DOCKER_HOST_PRIV_DIR") or "").strip()
    if not host_priv:
        raise RuntimeError("ARCLINK_DOCKER_HOST_PRIV_DIR is required for Docker-published agent web surfaces")
    return host_priv


def docker_rm_container(name: str) -> None:
    subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def active_agents(cfg: Config) -> list[dict[str, Any]]:
    with connect_db(cfg) as conn:
        rows = conn.execute(
            """
            SELECT
              a.agent_id,
              a.unix_user,
              a.display_name,
              a.hermes_home,
              a.channels_json,
              COALESCE(NULLIF(ai.agent_name, ''), a.display_name, a.unix_user) AS agent_label,
              COALESCE(NULLIF(ai.human_display_name, ''), a.unix_user) AS user_label
            FROM agents a
            LEFT JOIN agent_identity ai ON ai.agent_id = a.agent_id
            WHERE a.role = 'user' AND a.status = 'active'
            ORDER BY a.agent_id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def home_from_hermes(hermes_home: Path) -> Path:
    try:
        return hermes_home.parents[3]
    except IndexError:
        return hermes_home.parent


def ensure_container_user(unix_user: str, home: Path) -> tuple[int, int]:
    home.mkdir(parents=True, exist_ok=True)
    if subprocess.run(["id", "-u", unix_user], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
        subprocess.run(["useradd", "--home-dir", str(home), "--shell", "/bin/bash", "--create-home", unix_user], check=True)
    info = pwd.getpwnam(unix_user)
    for path in (
        home / ".config" / "systemd" / "user",
        home / ".local" / "share" / "arclink-agent",
        home / ".local" / "state" / "arclink-agent",
    ):
        path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["chown", "-R", f"{unix_user}:{unix_user}", str(home)], check=False)
    return info.pw_uid, info.pw_gid


def user_env(cfg: Config, agent: dict[str, Any], home: Path, hermes_home: Path) -> dict[str, str]:
    env = docker_mode_env(cfg)
    unix_user = str(agent["unix_user"])
    env.update(
        {
            "HOME": str(home),
            "USER": unix_user,
            "LOGNAME": unix_user,
            "HERMES_HOME": str(hermes_home),
            "ARCLINK_AGENT_ID": str(agent["agent_id"]),
        }
    )
    return env


def runuser_cmd(unix_user: str, env: dict[str, str], cmd: list[str]) -> list[str]:
    env_args = [f"{key}={value}" for key, value in sorted(env.items()) if value is not None]
    return ["runuser", "-u", unix_user, "--", "env", *env_args, *cmd]


def log_handle(cfg: Config, name: str):
    log_dir = cfg.state_dir / "docker" / "agent-supervisor"
    log_dir.mkdir(parents=True, exist_ok=True)
    return (log_dir / f"{name}.log").open("a", encoding="utf-8")


def install_agent_assets(cfg: Config, agent: dict[str, Any], home: Path, hermes_home: Path, channels: list[str]) -> None:
    unix_user = str(agent["unix_user"])
    env = user_env(cfg, agent, home, hermes_home)
    cmd = runuser_cmd(
        unix_user,
        env,
        [
            str(cfg.repo_dir / "bin" / "install-agent-user-services.sh"),
            str(agent["agent_id"]),
            str(cfg.repo_dir),
            str(hermes_home),
            json.dumps(channels),
            str(cfg.state_dir / "activation-triggers" / f"{agent['agent_id']}.json"),
            str(cfg.repo_dir / "bin" / "hermes-shell.sh"),
        ],
    )
    with log_handle(cfg, f"{agent['agent_id']}-install") as log:
        result = subprocess.run(cmd, cwd=str(cfg.repo_dir), text=True, stdout=log, stderr=subprocess.STDOUT, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"agent install failed for {agent['agent_id']} with exit {result.returncode}")
    run_headless_identity_setup(cfg, agent, home, hermes_home)


def run_headless_identity_setup(cfg: Config, agent: dict[str, Any], home: Path, hermes_home: Path) -> None:
    unix_user = str(agent["unix_user"])
    env = user_env(cfg, agent, home, hermes_home)
    python_bin = cfg.runtime_dir / "hermes-venv" / "bin" / "python3"
    if not python_bin.exists():
        python_bin = Path("python3")
    bot_name = str(agent.get("agent_label") or agent.get("display_name") or unix_user)
    user_name = str(agent.get("user_label") or unix_user)
    cmd = runuser_cmd(
        unix_user,
        env,
        [
            str(python_bin),
            str(cfg.repo_dir / "python" / "arclink_headless_hermes_setup.py"),
            "--identity-only",
            "--bot-name",
            bot_name,
            "--unix-user",
            unix_user,
            "--user-name",
            user_name,
        ],
    )
    with log_handle(cfg, f"{agent['agent_id']}-install") as log:
        result = subprocess.run(cmd, cwd=str(cfg.repo_dir), text=True, stdout=log, stderr=subprocess.STDOUT, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"agent identity refresh failed for {agent['agent_id']} with exit {result.returncode}")


def ensure_agent_mcp_auth(cfg: Config, agent: dict[str, Any], hermes_home: Path) -> None:
    unix_user = str(agent["unix_user"])
    with connect_db(cfg) as conn:
        result = ensure_agent_mcp_bootstrap_token(
            conn,
            unix_user=unix_user,
            hermes_home=hermes_home,
            actor="docker-agent-supervisor",
        )
    if result.get("changed"):
        log_agent_error(
            cfg,
            str(agent["agent_id"]),
            "repaired ArcLink MCP bootstrap token for Docker agent runtime",
        )


def access_state(hermes_home: Path) -> dict[str, Any]:
    path = hermes_home / "state" / "arclink-web-access.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def desired_specs(cfg: Config, agent: dict[str, Any], home: Path, hermes_home: Path) -> dict[str, tuple[list[str], dict[str, str], Path]]:
    unix_user = str(agent["unix_user"])
    channels = [str(channel).lower() for channel in json_loads(str(agent.get("channels_json") or "[]"), [])]
    env = user_env(cfg, agent, home, hermes_home)
    specs: dict[str, tuple[list[str], dict[str, str], Path]] = {}
    if any(channel in {"discord", "telegram"} for channel in channels):
        specs[f"{agent['agent_id']}:gateway"] = (
            runuser_cmd(unix_user, env, [str(cfg.repo_dir / "bin" / "hermes-shell.sh"), "gateway", "run", "--replace"]),
            env,
            hermes_home,
        )

    access = access_state(hermes_home)
    if access:
        dashboard_backend_port = str(access.get("dashboard_backend_port") or "")
        dashboard_proxy_port = str(access.get("dashboard_proxy_port") or "")
        if dashboard_backend_port:
            specs[f"{agent['agent_id']}:dashboard"] = (
                runuser_cmd(
                    unix_user,
                    env,
                    [
                        str(cfg.repo_dir / "bin" / "hermes-shell.sh"),
                        "dashboard",
                        "--host",
                        "0.0.0.0",
                        "--port",
                        dashboard_backend_port,
                        "--no-open",
                    ],
                ),
                env,
                hermes_home,
            )
        if dashboard_proxy_port and dashboard_backend_port:
            root_env = env.copy()
            proxy_container_name = f"arclink-agent-dashboard-proxy-{docker_name(str(agent['agent_id']))}"
            root_env.update(
                {
                    "HOME": "/root",
                    "ARCLINK_DOCKER_CONTAINER_NAME": proxy_container_name,
                }
            )
            specs[f"{agent['agent_id']}:dashboard-proxy"] = (
                [
                    "docker",
                    "run",
                    "--rm",
                    "--name",
                    proxy_container_name,
                    "--pull",
                    "never",
                    "--network",
                    str(root_env["ARCLINK_DOCKER_NETWORK"]),
                    "-p",
                    f"127.0.0.1:{dashboard_proxy_port}:{dashboard_proxy_port}",
                    "-v",
                    f"{docker_host_priv_dir(cfg)}:{root_env['ARCLINK_DOCKER_CONTAINER_PRIV_DIR']}:rw",
                    str(root_env["ARCLINK_DOCKER_IMAGE"]),
                    "python3",
                    str(cfg.repo_dir / "python" / "arclink_basic_auth_proxy.py"),
                    "--listen-host",
                    "0.0.0.0",
                    "--listen-port",
                    dashboard_proxy_port,
                    "--target",
                    f"http://{os.environ.get('ARCLINK_DOCKER_AGENT_SUPERVISOR_HOST') or 'agent-supervisor'}:{dashboard_backend_port}",
                    "--access-file",
                    str(hermes_home / "state" / "arclink-web-access.json"),
                    "--realm",
                    "ArcLink Hermes",
                ],
                root_env,
                cfg.repo_dir,
            )
        if access.get("code_port"):
            root_env = env.copy()
            root_env.update({"HOME": "/root", "HERMES_HOME": str(hermes_home)})
            specs[f"{agent['agent_id']}:code"] = (
                [
                    str(cfg.repo_dir / "bin" / "run-agent-code-server.sh"),
                    str(hermes_home / "state" / "arclink-web-access.json"),
                    str(home),
                    str(hermes_home),
                ],
                root_env,
                hermes_home,
            )
    return specs


def start_process(cfg: Config, key: str, cmd: list[str], env: dict[str, str], cwd: Path) -> subprocess.Popen[str]:
    name = key.replace(":", "-")
    log = log_handle(cfg, name)
    log.write(f"\n[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] starting: {' '.join(cmd)}\n")
    log.flush()
    container_name = str(env.get("ARCLINK_DOCKER_CONTAINER_NAME") or "").strip()
    if container_name:
        docker_rm_container(container_name)
    return subprocess.Popen(cmd, cwd=str(cwd), env=env, text=True, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)


def run_refresh(cfg: Config, agent: dict[str, Any], home: Path, hermes_home: Path, *, cron_tick: bool) -> None:
    unix_user = str(agent["unix_user"])
    env = user_env(cfg, agent, home, hermes_home)
    commands = [[str(cfg.repo_dir / "bin" / "user-agent-refresh.sh")]]
    if cron_tick:
        commands.append([str(cfg.repo_dir / "bin" / "hermes-shell.sh"), "cron", "tick"])
    with log_handle(cfg, f"{agent['agent_id']}-refresh") as log:
        for command in commands:
            try:
                subprocess.run(
                    runuser_cmd(unix_user, env, command),
                    cwd=str(cfg.repo_dir),
                    text=True,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                    timeout=1800,
                )
            except subprocess.TimeoutExpired:
                log.write(f"\nrefresh command timed out: {' '.join(command)}\n")
                log.flush()


def run_provisioner(cfg: Config) -> None:
    env = os.environ.copy()
    env.update(docker_mode_env(cfg))
    with log_handle(cfg, "enrollment-provisioner") as log:
        try:
            subprocess.run(
                [str(cfg.repo_dir / "bin" / "arclink-enrollment-provision.sh")],
                cwd=str(cfg.repo_dir),
                env=env,
                text=True,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=3600,
            )
        except subprocess.TimeoutExpired:
            log.write("\nenrollment provisioner timed out\n")
            log.flush()


def log_agent_error(cfg: Config, agent_id: str, message: str) -> None:
    with log_handle(cfg, f"{agent_id}-supervisor") as log:
        log.write(f"\n[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {message}\n")
        log.flush()


def terminate_removed(processes: dict[str, subprocess.Popen[str]], desired: set[str], container_names: dict[str, str]) -> None:
    for key in list(processes):
        process = processes[key]
        if key in desired and process.poll() is None:
            continue
        if key not in desired and process.poll() is None:
            process.terminate()
            container_name = container_names.pop(key, "")
            if container_name:
                docker_rm_container(container_name)
        processes.pop(key, None)


def main() -> int:
    cfg = Config.from_env()
    poll_seconds = int(os.environ.get("ARCLINK_DOCKER_AGENT_SUPERVISOR_POLL_SECONDS", "10"))
    provision_seconds = int(os.environ.get("ARCLINK_DOCKER_AGENT_PROVISION_SECONDS", "30"))
    refresh_seconds = int(os.environ.get("ARCLINK_DOCKER_AGENT_REFRESH_SECONDS", "14400"))
    cron_seconds = int(os.environ.get("ARCLINK_DOCKER_AGENT_CRON_SECONDS", "60"))
    processes: dict[str, subprocess.Popen[str]] = {}
    container_names: dict[str, str] = {}
    installed: set[str] = set()
    last_refresh: dict[str, float] = {}
    last_cron: dict[str, float] = {}
    last_provision = 0.0

    while not STOP:
        now = time.time()
        if now - last_provision >= provision_seconds:
            run_provisioner(cfg)
            last_provision = now

        desired_keys: set[str] = set()
        for agent in active_agents(cfg):
            unix_user = str(agent["unix_user"] or "").strip()
            agent_id = str(agent["agent_id"] or "").strip()
            if not unix_user or not agent_id:
                continue
            try:
                hermes_home = Path(str(agent["hermes_home"] or "")).resolve()
                home = home_from_hermes(hermes_home)
                ensure_container_user(unix_user, home)
                ensure_agent_mcp_auth(cfg, agent, hermes_home)
                channels = [str(channel).lower() for channel in json_loads(str(agent.get("channels_json") or "[]"), [])]
                if agent_id not in installed:
                    install_agent_assets(cfg, agent, home, hermes_home, channels)
                    installed.add(agent_id)

                if now - last_refresh.get(agent_id, 0) >= refresh_seconds:
                    run_refresh(cfg, agent, home, hermes_home, cron_tick=False)
                    last_refresh[agent_id] = now
                if now - last_cron.get(agent_id, 0) >= cron_seconds:
                    run_refresh(cfg, agent, home, hermes_home, cron_tick=True)
                    last_cron[agent_id] = now

                specs = desired_specs(cfg, agent, home, hermes_home)
            except Exception as exc:
                log_agent_error(cfg, agent_id, f"agent reconciliation failed: {exc}")
                continue
            desired_keys.update(specs)
            for key, (cmd, env, cwd) in specs.items():
                container_name = str(env.get("ARCLINK_DOCKER_CONTAINER_NAME") or "").strip()
                if container_name:
                    container_names[key] = container_name
                process = processes.get(key)
                if process is not None and process.poll() is None:
                    continue
                processes[key] = start_process(cfg, key, cmd, env, cwd)

        terminate_removed(processes, desired_keys, container_names)
        time.sleep(poll_seconds)

    for process in processes.values():
        if process.poll() is None:
            process.terminate()
    for container_name in container_names.values():
        docker_rm_container(container_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
