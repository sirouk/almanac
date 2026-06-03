#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from arclink_control import Config, connect_db, ensure_agent_mcp_bootstrap_token, json_loads
from arclink_onboarding import default_arclink_agent_profile


STOP = False
SAFE_PATH = "/home/arclink/.local/bin:/opt/arclink/runtime/hermes-venv/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin"
PROVISIONER_BASE_ENV_KEYS = (
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "TERM",
    "TMPDIR",
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
)
PROVISIONER_ALLOWED_PARENT_ENV_KEYS = (
    "ARCLINK_DOCKER_AGENT_HOME_ROOT",
    "ARCLINK_DOCKER_HOST_REPO_DIR",
    "ARCLINK_DOCKER_HOST_PRIV_DIR",
    "ARCLINK_DOCKER_IMAGE",
    "ARCLINK_DOCKER_NETWORK",
    "ARCLINK_MCP_URL",
    "ARCLINK_BOOTSTRAP_URL",
    "ARCLINK_QMD_URL",
    "ARCLINK_OPERATOR_SQLITE_RETRY_SECONDS",
    "ARCLINK_AGENT_USER_HELPER_URL",
    "ARCLINK_AGENT_USER_HELPER_TOKEN",
    "ARCLINK_AGENT_PROCESS_HELPER_URL",
    "ARCLINK_AGENT_PROCESS_HELPER_TOKEN",
    "ARCLINK_AGENT_SUPERVISOR_BROKER_URL",
    "ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN",
    "ARCLINK_OPERATOR_UPGRADE_BROKER_URL",
    "ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN",
)
AGENT_SUPERVISOR_BROKER_TOKEN_HEADER = "X-ArcLink-Agent-Supervisor-Broker-Token"
AGENT_USER_HELPER_TOKEN_HEADER = "X-ArcLink-Agent-User-Helper-Token"
AGENT_PROCESS_HELPER_TOKEN_HEADER = "X-ArcLink-Agent-Process-Helper-Token"
SAFE_AGENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")
SAFE_UNIX_USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,30}$")
SAFE_LOG_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,120}$")
SAFE_ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
HERMES_HOME_SUFFIX = Path(".local/share/arclink-agent/hermes-home")
PROCESS_KINDS = {"gateway", "dashboard"}
MIN_AGENT_PROCESS_ID = 1
MAX_AGENT_PROCESS_ID = 2147483647
AGENT_PROCESS_ENV_BLOCKLIST = {
    "ARCLINK_AGENT_PROCESS_HELPER_TOKEN",
    "ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN",
    "ARCLINK_AGENT_USER_HELPER_TOKEN",
    "ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN",
    "ARCLINK_GATEWAY_EXEC_BROKER_TOKEN",
    "ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN",
    "ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN",
}
AGENT_PROCESS_UNAPPROVED_ENV_KEYS = {
    "BASH_ENV",
    "ENV",
    "GIT_ASKPASS",
    "GIT_SSH",
    "GIT_SSH_COMMAND",
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "SSH_ASKPASS",
    "SSH_AUTH_SOCK",
}
AGENT_PROCESS_UNAPPROVED_ENV_PREFIXES = ("LD_",)
AGENT_PROCESS_SECRET_ENV_SUFFIXES = ("_TOKEN", "_SECRET", "_PASSWORD", "_KEY")


def _stop(_signum, _frame) -> None:
    global STOP
    STOP = True


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)


def docker_mode_env(cfg: Config) -> dict[str, str]:
    env = {
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
        "ARCLINK_AGENT_SUPERVISOR_BROKER_URL": str(
            os.environ.get("ARCLINK_AGENT_SUPERVISOR_BROKER_URL") or "http://agent-supervisor-broker:8913"
        ),
    }
    broker_token = str(os.environ.get("ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN") or "").strip()
    if broker_token:
        env["ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN"] = broker_token
    return env


def _single_line_env_value(key: str, value: str | None, *, max_chars: int = 4096) -> str:
    clean = str(value or "").strip()
    if not clean:
        return ""
    if "\n" in clean or "\r" in clean or "\x00" in clean:
        raise ValueError(f"Docker agent supervisor env value for {key} must be a single line")
    if len(clean) > max_chars:
        raise ValueError(f"Docker agent supervisor env value for {key} is too long")
    return clean


def provisioner_child_env(cfg: Config) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in PROVISIONER_BASE_ENV_KEYS:
        value = _single_line_env_value(key, os.environ.get(key))
        if value:
            env[key] = value

    env.update(docker_mode_env(cfg))
    container_priv_dir = _single_line_env_value(
        "ARCLINK_DOCKER_CONTAINER_PRIV_DIR",
        os.environ.get("ARCLINK_DOCKER_CONTAINER_PRIV_DIR"),
    )
    env.update(
        {
            "ARCLINK_PRIV_CONFIG_DIR": str(cfg.private_dir / "config"),
            "STATE_DIR": str(cfg.state_dir),
            "VAULT_DIR": str(cfg.vault_dir),
            "ARCLINK_DB_PATH": str(getattr(cfg, "db_path", cfg.state_dir / "arclink-control.sqlite3")),
            "ARCLINK_DOCKER_CONTAINER_PRIV_DIR": container_priv_dir or str(cfg.private_dir),
        }
    )
    env.setdefault("HOME", "/home/arclink")
    env["PATH"] = SAFE_PATH

    for key in PROVISIONER_ALLOWED_PARENT_ENV_KEYS:
        value = _single_line_env_value(key, os.environ.get(key))
        if value:
            env[key] = value
    for key, value in list(env.items()):
        if not SAFE_ENV_KEY_RE.fullmatch(str(key or "")):
            raise ValueError("Docker agent supervisor provisioner env key is not safe")
        env[str(key)] = _single_line_env_value(str(key), str(value))
    return env


def _resolve_absolute_path(value: str | Path, *, label: str) -> Path:
    try:
        path = Path(str(value or "")).resolve(strict=False)
    except (OSError, RuntimeError):
        raise ValueError(f"Docker agent supervisor {label} is not a valid path") from None
    if not path.is_absolute():
        raise ValueError(f"Docker agent supervisor {label} must be absolute")
    return path


def _require_safe_agent_id(value: str, *, label: str = "agent_id") -> str:
    clean = str(value or "").strip()
    if not SAFE_AGENT_ID_RE.fullmatch(clean):
        raise ValueError(f"Docker agent supervisor {label} is not a safe identifier")
    return clean


def _require_safe_unix_user(value: str) -> str:
    clean = str(value or "").strip().lower()
    if not SAFE_UNIX_USER_RE.fullmatch(clean):
        raise ValueError("Docker agent supervisor unix_user is not a safe local account name")
    return clean


def docker_agent_home_root(cfg: Config) -> Path:
    configured = str(os.environ.get("ARCLINK_DOCKER_AGENT_HOME_ROOT") or "").strip()
    root = Path(configured) if configured else cfg.state_dir / "docker" / "users"
    return _resolve_absolute_path(root, label="agent home root")


def _require_agent_home(unix_user: str, home: Path, *, home_root: Path | None = None) -> Path:
    unix_user = _require_safe_unix_user(unix_user)
    home_path = _resolve_absolute_path(home, label="agent home")
    if home_path.name != unix_user:
        raise ValueError("Docker agent supervisor agent home must be named for unix_user")
    if home_root is not None:
        expected = (_resolve_absolute_path(home_root, label="agent home root") / unix_user).resolve(strict=False)
        if home_path != expected:
            raise ValueError("Docker agent supervisor agent home must stay under the Docker agent home root")
    return home_path


def _require_hermes_home(home: Path, hermes_home: Path) -> Path:
    home = _resolve_absolute_path(home, label="agent home")
    hermes = _resolve_absolute_path(hermes_home, label="Hermes home")
    expected = (home / HERMES_HOME_SUFFIX).resolve(strict=False)
    if hermes != expected:
        raise ValueError("Docker agent supervisor Hermes home must be the canonical child of the agent home")
    return hermes


def validated_agent_context(cfg: Config, agent: dict[str, Any]) -> tuple[dict[str, Any], Path, Path]:
    agent_id = _require_safe_agent_id(str(agent.get("agent_id") or ""))
    unix_user = _require_safe_unix_user(str(agent.get("unix_user") or ""))
    raw_hermes = str(agent.get("hermes_home") or "").strip()
    if not raw_hermes:
        raise ValueError("Docker agent supervisor Hermes home is required")
    hermes_home = _resolve_absolute_path(raw_hermes, label="Hermes home")
    home = _require_agent_home(unix_user, home_from_hermes(hermes_home), home_root=docker_agent_home_root(cfg))
    hermes_home = _require_hermes_home(home, hermes_home)
    clean_agent = dict(agent)
    clean_agent["agent_id"] = agent_id
    clean_agent["unix_user"] = unix_user
    clean_agent["hermes_home"] = str(hermes_home)
    return clean_agent, home, hermes_home


def _require_log_name(name: str) -> str:
    clean = str(name or "").strip()
    if not SAFE_LOG_NAME_RE.fullmatch(clean):
        raise ValueError("Docker agent supervisor log name is not safe")
    return clean


def _safe_error_log_name(agent_id: str) -> str:
    try:
        return f"{_require_safe_agent_id(agent_id)}-supervisor"
    except ValueError:
        return "invalid-agent-supervisor"


def _require_process_key(key: str) -> str:
    clean = str(key or "").strip()
    agent_id, separator, kind = clean.partition(":")
    if separator != ":" or kind not in PROCESS_KINDS:
        raise ValueError("Docker agent supervisor process key is not an allowlisted agent process")
    try:
        _require_safe_agent_id(agent_id)
    except ValueError:
        raise ValueError("Docker agent supervisor process key is not safe") from None
    return clean


def _require_runuser_env(env: dict[str, str]) -> dict[str, str]:
    clean_env: dict[str, str] = {}
    for key, value in env.items():
        key_text = str(key or "").strip()
        if not SAFE_ENV_KEY_RE.fullmatch(key_text):
            raise ValueError("Docker agent supervisor agent process env key is not safe")
        value_text = str(value)
        if "\x00" in value_text:
            raise ValueError("Docker agent supervisor agent process env value contains a NUL byte")
        clean_env[key_text] = value_text
    return clean_env


def _is_agent_process_control_token_env_key(key: str) -> bool:
    return key in AGENT_PROCESS_ENV_BLOCKLIST or (key.startswith("ARCLINK_") and key.endswith("_TOKEN"))


def _is_agent_process_unapproved_env_key(key: str) -> bool:
    return (
        key in AGENT_PROCESS_UNAPPROVED_ENV_KEYS
        or key.startswith(AGENT_PROCESS_UNAPPROVED_ENV_PREFIXES)
        or key.endswith(AGENT_PROCESS_SECRET_ENV_SUFFIXES)
    )


def _agent_process_env(env: dict[str, str]) -> dict[str, str]:
    clean_env = _require_runuser_env(env)
    process_env: dict[str, str] = {}
    for key, value in clean_env.items():
        if _is_agent_process_control_token_env_key(key):
            continue
        if _is_agent_process_unapproved_env_key(key):
            raise ValueError("Docker agent supervisor agent process env key is not approved for helper dispatch")
        process_env[key] = value
    return process_env


def _require_agent_process_id(value: str | None, *, label: str) -> int:
    text = str(value or "").strip()
    if not text.isdecimal():
        raise ValueError(f"Docker agent supervisor {label} is required for numeric privilege drop")
    numeric = int(text)
    if numeric < MIN_AGENT_PROCESS_ID or numeric > MAX_AGENT_PROCESS_ID:
        raise ValueError(f"Docker agent supervisor {label} is outside the allowed numeric id range")
    return numeric


def docker_name(value: str, *, fallback: str = "agent") -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return name or fallback


def docker_dashboard_network_name(agent_id: str) -> str:
    return f"arclink-agent-dashboard-{docker_name(agent_id)}"


def docker_dashboard_proxy_container_name(agent_id: str) -> str:
    return f"arclink-agent-dashboard-proxy-{docker_name(agent_id)}"


def supervisor_container_name() -> str:
    return str(
        os.environ.get("ARCLINK_DOCKER_AGENT_SUPERVISOR_CONTAINER")
        or os.environ.get("HOSTNAME")
        or socket.gethostname()
    ).strip()


def agent_supervisor_broker_request(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    broker_url = str(os.environ.get("ARCLINK_AGENT_SUPERVISOR_BROKER_URL") or "http://agent-supervisor-broker:8913")
    broker_url = broker_url.strip().rstrip("/")
    broker_token = str(os.environ.get("ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN") or "").strip()
    if not broker_url or not broker_token:
        raise RuntimeError(
            "Docker-mode dashboard proxy reconciliation requires "
            "ARCLINK_AGENT_SUPERVISOR_BROKER_URL and ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN"
        )
    request_body = {**payload, "operation": operation}
    data = json.dumps(request_body, sort_keys=True).encode("utf-8")
    request = urllib.request.Request(
        f"{broker_url}/v1/agent-supervisor",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            AGENT_SUPERVISOR_BROKER_TOKEN_HEADER: broker_token,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload_out = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            error_payload = json.loads(exc.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            error_payload = {}
        raise RuntimeError(str(error_payload.get("error") or f"agent supervisor broker HTTP {exc.code}")) from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"agent supervisor broker request failed: {exc}") from None
    if not isinstance(payload_out, dict) or payload_out.get("ok") is not True:
        raise RuntimeError(str(payload_out.get("error") if isinstance(payload_out, dict) else "invalid broker response"))
    result = payload_out.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("agent supervisor broker returned an invalid result")
    return result


def agent_user_helper_request(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    helper_url = str(os.environ.get("ARCLINK_AGENT_USER_HELPER_URL") or "").strip().rstrip("/")
    helper_token = str(os.environ.get("ARCLINK_AGENT_USER_HELPER_TOKEN") or "").strip()
    if not helper_url or not helper_token:
        raise RuntimeError(
            "Docker-mode user/home setup requires "
            "ARCLINK_AGENT_USER_HELPER_URL and ARCLINK_AGENT_USER_HELPER_TOKEN"
        )
    request_body = {**payload, "operation": operation}
    data = json.dumps(request_body, sort_keys=True).encode("utf-8")
    request = urllib.request.Request(
        f"{helper_url}/v1/agent-user",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            AGENT_USER_HELPER_TOKEN_HEADER: helper_token,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload_out = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            error_payload = json.loads(exc.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            error_payload = {}
        raise RuntimeError(str(error_payload.get("error") or f"agent user helper HTTP {exc.code}")) from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"agent user helper request failed: {exc}") from None
    if not isinstance(payload_out, dict) or payload_out.get("ok") is not True:
        raise RuntimeError(str(payload_out.get("error") if isinstance(payload_out, dict) else "invalid helper response"))
    result = payload_out.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("agent user helper returned an invalid result")
    return result


def agent_process_helper_request(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    helper_url = str(os.environ.get("ARCLINK_AGENT_PROCESS_HELPER_URL") or "").strip().rstrip("/")
    helper_token = str(os.environ.get("ARCLINK_AGENT_PROCESS_HELPER_TOKEN") or "").strip()
    if not helper_url or not helper_token:
        raise RuntimeError(
            "Docker-mode agent process execution requires "
            "ARCLINK_AGENT_PROCESS_HELPER_URL and ARCLINK_AGENT_PROCESS_HELPER_TOKEN"
        )
    request_body = {**payload, "operation": operation}
    data = json.dumps(request_body, sort_keys=True).encode("utf-8")
    request = urllib.request.Request(
        f"{helper_url}/v1/agent-process",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            AGENT_PROCESS_HELPER_TOKEN_HEADER: helper_token,
        },
    )
    try:
        timeout = float(os.environ.get("ARCLINK_AGENT_PROCESS_HELPER_REQUEST_TIMEOUT_SECONDS") or "3700")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload_out = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            error_payload = json.loads(exc.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            error_payload = {}
        raise RuntimeError(str(error_payload.get("error") or f"agent process helper HTTP {exc.code}")) from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"agent process helper request failed: {exc}") from None
    if not isinstance(payload_out, dict) or payload_out.get("ok") is not True:
        raise RuntimeError(str(payload_out.get("error") if isinstance(payload_out, dict) else "invalid helper response"))
    result = payload_out.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("agent process helper returned an invalid result")
    return result


def ensure_dashboard_backend_network(agent_id: str) -> tuple[str, str]:
    network_name = docker_dashboard_network_name(agent_id)
    container_name = supervisor_container_name()
    if not container_name:
        raise RuntimeError("cannot determine Docker agent supervisor container for dashboard backend isolation")
    result = agent_supervisor_broker_request(
        "ensure_dashboard_network",
        {
            "agent_id": agent_id,
            "network": network_name,
            "supervisor_container": container_name,
        },
    )
    backend_host = str(result.get("backend_host") or "").strip()
    returned_network = str(result.get("network") or "").strip()
    if returned_network != network_name:
        raise RuntimeError("agent supervisor broker returned the wrong dashboard network")
    if not backend_host:
        raise RuntimeError(f"could not attach supervisor container to isolated dashboard network {network_name}")
    return network_name, backend_host


def ensure_dashboard_proxy(
    *,
    agent_id: str,
    dashboard_network: str,
    dashboard_backend_host: str,
    dashboard_backend_port: str,
    dashboard_proxy_port: str,
    access_file: Path,
) -> str:
    container_name = docker_dashboard_proxy_container_name(agent_id)
    result = agent_supervisor_broker_request(
        "ensure_dashboard_proxy",
        {
            "agent_id": agent_id,
            "network": dashboard_network,
            "backend_host": dashboard_backend_host,
            "backend_port": dashboard_backend_port,
            "proxy_port": dashboard_proxy_port,
            "container_name": container_name,
            "access_file": str(access_file),
        },
    )
    returned = str(result.get("container") or "").strip()
    if returned != container_name:
        raise RuntimeError("agent supervisor broker returned the wrong dashboard proxy container")
    return container_name


def remove_dashboard_proxy(agent_id: str) -> None:
    agent_supervisor_broker_request(
        "remove_dashboard_proxy",
        {
            "agent_id": agent_id,
            "container_name": docker_dashboard_proxy_container_name(agent_id),
        },
    )


def _theme_profile(metadata: dict[str, Any]) -> dict[str, str]:
    try:
        index = int(str(metadata.get("bundle_agent_index") or metadata.get("agent_index") or "1"))
    except (TypeError, ValueError):
        index = 1
    profile = default_arclink_agent_profile(
        index,
        plan_id=str(metadata.get("selected_plan_id") or metadata.get("plan_id") or ""),
    )
    return {
        "dashboard_theme": str(metadata.get("dashboard_theme") or profile.get("dashboard_theme") or "arclink"),
        "theme_label": str(metadata.get("theme_label") or profile.get("theme_label") or "ArcLink Signal Orange"),
        "theme_accent_hex": str(metadata.get("theme_accent_hex") or profile.get("theme_accent_hex") or "#FB5005"),
    }


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
              COALESCE(NULLIF(d.agent_name, ''), NULLIF(ai.agent_name, ''), a.display_name, a.unix_user) AS agent_label,
              COALESCE(NULLIF(ai.human_display_name, ''), a.unix_user) AS user_label,
              COALESCE(NULLIF(d.agent_title, ''), '') AS agent_title,
              COALESCE(d.metadata_json, '{}') AS deployment_metadata_json
            FROM agents a
            LEFT JOIN agent_identity ai ON ai.agent_id = a.agent_id
            LEFT JOIN arclink_deployments d ON d.agent_id = a.agent_id
            WHERE a.role = 'user' AND a.status = 'active'
            ORDER BY a.agent_id
            """
        ).fetchall()
    agents: list[dict[str, Any]] = []
    for row in rows:
        agent = dict(row)
        metadata = json_loads(str(agent.pop("deployment_metadata_json") or "{}"), {})
        if not isinstance(metadata, dict):
            metadata = {}
        theme_profile = _theme_profile(metadata)
        agent["dashboard_theme"] = theme_profile["dashboard_theme"]
        agent["theme_label"] = theme_profile["theme_label"]
        agent["theme_accent_hex"] = theme_profile["theme_accent_hex"]
        agents.append(agent)
    return agents


def home_from_hermes(hermes_home: Path) -> Path:
    try:
        return hermes_home.parents[3]
    except IndexError:
        return hermes_home.parent


def ensure_container_user(
    agent_id: str,
    unix_user: str,
    home: Path,
    hermes_home: Path,
    *,
    home_root: Path | None = None,
) -> tuple[int, int]:
    agent_id = _require_safe_agent_id(agent_id)
    unix_user = _require_safe_unix_user(unix_user)
    if home_root is None:
        raise ValueError("Docker agent supervisor agent home root is required")
    home = _require_agent_home(unix_user, home, home_root=home_root)
    hermes_home = _require_hermes_home(home, hermes_home)
    workspace_root = hermes_home / "workspace"
    result = agent_user_helper_request(
        "ensure_user_home",
        {
            "agent_id": agent_id,
            "unix_user": unix_user,
            "home_root": str(_resolve_absolute_path(home_root, label="agent home root")),
            "home": str(home),
            "hermes_home": str(hermes_home),
            "workspace": str(workspace_root),
        },
    )
    try:
        uid = int(result["uid"])
        gid = int(result["gid"])
    except (KeyError, TypeError, ValueError):
        raise RuntimeError("agent user helper returned invalid uid/gid") from None
    if uid <= 0 or gid <= 0:
        raise RuntimeError("agent user helper returned root or invalid uid/gid")
    return uid, gid


def user_env(cfg: Config, agent: dict[str, Any], home: Path, hermes_home: Path) -> dict[str, str]:
    env = docker_mode_env(cfg)
    agent_id = _require_safe_agent_id(str(agent["agent_id"]))
    unix_user = _require_safe_unix_user(str(agent["unix_user"]))
    home = _require_agent_home(unix_user, home, home_root=docker_agent_home_root(cfg))
    hermes_home = _require_hermes_home(home, hermes_home)
    workspace_root = hermes_home / "workspace"
    env.update(
        {
            "HOME": str(home),
            "USER": unix_user,
            "LOGNAME": unix_user,
            "HERMES_HOME": str(hermes_home),
            "ARCLINK_WORKSPACE_ROOT": str(workspace_root),
            "DRIVE_WORKSPACE_ROOT": str(workspace_root),
            "CODE_WORKSPACE_ROOT": str(workspace_root),
            "TERMINAL_WORKSPACE_ROOT": str(workspace_root),
            "ARCLINK_AGENT_ID": agent_id,
            "ARCLINK_DASHBOARD_AGENT_LABEL": str(agent.get("agent_label") or agent_id),
            "ARCLINK_DASHBOARD_AGENT_TITLE": str(agent.get("agent_title") or ""),
            "ARCLINK_DASHBOARD_THEME": str(agent.get("dashboard_theme") or ""),
            "ARCLINK_DASHBOARD_THEME_LABEL": str(agent.get("theme_label") or ""),
            "ARCLINK_DASHBOARD_ACCENT_HEX": str(agent.get("theme_accent_hex") or ""),
        }
    )
    uid = agent.get("_docker_uid")
    gid = agent.get("_docker_gid")
    if uid is not None and gid is not None:
        env["ARCLINK_AGENT_UID"] = str(_require_agent_process_id(str(uid), label="agent uid"))
        env["ARCLINK_AGENT_GID"] = str(_require_agent_process_id(str(gid), label="agent gid"))
    return env


def log_handle(cfg: Config, name: str):
    name = _require_log_name(name)
    log_dir = cfg.state_dir / "docker" / "agent-supervisor"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = (log_dir / f"{name}.log").resolve(strict=False)
    try:
        path.relative_to(log_dir.resolve(strict=False))
    except ValueError:
        raise ValueError("Docker agent supervisor log path escaped its state directory") from None
    return path.open("a", encoding="utf-8")


def agent_process_context(cfg: Config, agent: dict[str, Any], home: Path, hermes_home: Path) -> dict[str, Any]:
    agent_id = _require_safe_agent_id(str(agent["agent_id"]))
    unix_user = _require_safe_unix_user(str(agent["unix_user"]))
    home_root = docker_agent_home_root(cfg)
    home = _require_agent_home(unix_user, home, home_root=home_root)
    hermes_home = _require_hermes_home(home, hermes_home)
    workspace = hermes_home / "workspace"
    env = _agent_process_env(user_env(cfg, agent, home, hermes_home))
    uid = _require_agent_process_id(env.get("ARCLINK_AGENT_UID"), label="agent uid")
    gid = _require_agent_process_id(env.get("ARCLINK_AGENT_GID"), label="agent gid")
    return {
        "agent_id": agent_id,
        "unix_user": unix_user,
        "home_root": str(home_root),
        "home": str(home),
        "hermes_home": str(hermes_home),
        "workspace": str(workspace),
        "uid": uid,
        "gid": gid,
        "repo_dir": str(cfg.repo_dir),
        "priv_dir": str(cfg.private_dir),
        "state_dir": str(cfg.state_dir),
        "runtime_dir": str(cfg.runtime_dir),
        "env": env,
    }


def run_agent_once(cfg: Config, agent: dict[str, Any], home: Path, hermes_home: Path, kind: str, **extra: Any) -> dict[str, Any]:
    payload = agent_process_context(cfg, agent, home, hermes_home)
    payload.update(extra)
    payload["kind"] = kind
    result = agent_process_helper_request("run_once", payload)
    returncode = result.get("returncode")
    if returncode not in (0, "0", None):
        raise RuntimeError(f"agent process helper {kind} failed for {payload['agent_id']} with exit {returncode}")
    return result


def install_agent_assets(cfg: Config, agent: dict[str, Any], home: Path, hermes_home: Path, channels: list[str]) -> None:
    agent_id = _require_safe_agent_id(str(agent["agent_id"]))
    run_agent_once(cfg, agent, home, hermes_home, "install", channels=channels)
    run_headless_identity_setup(cfg, agent, home, hermes_home)


def run_headless_identity_setup(cfg: Config, agent: dict[str, Any], home: Path, hermes_home: Path) -> None:
    unix_user = _require_safe_unix_user(str(agent["unix_user"]))
    bot_name = str(agent.get("agent_label") or agent.get("display_name") or unix_user)
    user_name = str(agent.get("user_label") or unix_user)
    run_agent_once(cfg, agent, home, hermes_home, "identity", bot_name=bot_name, user_name=user_name)


def ensure_agent_mcp_auth(cfg: Config, agent: dict[str, Any], hermes_home: Path) -> None:
    agent_id = _require_safe_agent_id(str(agent["agent_id"]))
    unix_user = _require_safe_unix_user(str(agent["unix_user"]))
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
            agent_id,
            "repaired ArcLink MCP bootstrap token for Docker agent runtime",
        )


def access_state(hermes_home: Path) -> dict[str, Any]:
    path = hermes_home / "state" / "arclink-web-access.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def desired_specs(
    cfg: Config,
    agent: dict[str, Any],
    home: Path,
    hermes_home: Path,
) -> tuple[list[dict[str, Any]], set[str]]:
    agent_id = _require_safe_agent_id(str(agent["agent_id"]))
    channels = [str(channel).lower() for channel in json_loads(str(agent.get("channels_json") or "[]"), [])]
    context = agent_process_context(cfg, agent, home, hermes_home)
    specs: list[dict[str, Any]] = []
    proxy_containers: set[str] = set()
    if any(channel in {"discord", "telegram"} for channel in channels):
        specs.append({**context, "kind": "gateway"})

    access = access_state(hermes_home)
    if access:
        dashboard_backend_port = str(access.get("dashboard_backend_port") or "")
        dashboard_proxy_port = str(access.get("dashboard_proxy_port") or "")
        dashboard_network = ""
        dashboard_backend_host = ""
        if dashboard_backend_port:
            dashboard_network, dashboard_backend_host = ensure_dashboard_backend_network(agent_id)
        if dashboard_backend_port:
            specs.append(
                {
                    **context,
                    "kind": "dashboard",
                    "dashboard_backend_host": dashboard_backend_host,
                    "dashboard_backend_port": dashboard_backend_port,
                }
            )
        if dashboard_proxy_port and dashboard_backend_port:
            proxy_containers.add(
                ensure_dashboard_proxy(
                    agent_id=agent_id,
                    dashboard_network=dashboard_network,
                    dashboard_backend_host=dashboard_backend_host,
                    dashboard_backend_port=dashboard_backend_port,
                    dashboard_proxy_port=dashboard_proxy_port,
                    access_file=hermes_home / "state" / "arclink-web-access.json",
                )
            )
    return specs, proxy_containers


def ensure_agent_processes(processes: list[dict[str, Any]]) -> dict[str, Any]:
    return agent_process_helper_request("ensure_processes", {"processes": processes})


def terminate_agent_processes() -> None:
    agent_process_helper_request("terminate_all", {})


def run_refresh(cfg: Config, agent: dict[str, Any], home: Path, hermes_home: Path, *, cron_tick: bool) -> None:
    if cron_tick:
        run_agent_once(cfg, agent, home, hermes_home, "cron")
    else:
        run_agent_once(cfg, agent, home, hermes_home, "refresh")


def run_provisioner(cfg: Config) -> None:
    env = provisioner_child_env(cfg)
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
    with log_handle(cfg, _safe_error_log_name(agent_id)) as log:
        log.write(f"\n[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {message}\n")
        log.flush()


def remove_removed_dashboard_proxies(active: set[str], desired: set[str]) -> set[str]:
    for container_name in sorted(active - desired):
        prefix = "arclink-agent-dashboard-proxy-"
        if not container_name.startswith(prefix):
            continue
        agent_name = container_name[len(prefix) :]
        try:
            remove_dashboard_proxy(agent_name)
        except Exception:
            pass
    return set(desired)


def main() -> int:
    cfg = Config.from_env()
    poll_seconds = int(os.environ.get("ARCLINK_DOCKER_AGENT_SUPERVISOR_POLL_SECONDS", "10"))
    provision_seconds = int(os.environ.get("ARCLINK_DOCKER_AGENT_PROVISION_SECONDS", "30"))
    refresh_seconds = int(os.environ.get("ARCLINK_DOCKER_AGENT_REFRESH_SECONDS", "14400"))
    cron_seconds = int(os.environ.get("ARCLINK_DOCKER_AGENT_CRON_SECONDS", "60"))
    active_proxy_containers: set[str] = set()
    installed: set[str] = set()
    last_refresh: dict[str, float] = {}
    last_cron: dict[str, float] = {}
    last_provision = 0.0

    while not STOP:
        now = time.time()
        if now - last_provision >= provision_seconds:
            run_provisioner(cfg)
            last_provision = now

        desired_processes: list[dict[str, Any]] = []
        desired_proxy_containers: set[str] = set()
        for agent in active_agents(cfg):
            raw_agent_id = str(agent.get("agent_id") or "").strip()
            if not raw_agent_id or not str(agent.get("unix_user") or "").strip():
                continue
            try:
                agent, home, hermes_home = validated_agent_context(cfg, agent)
                unix_user = str(agent["unix_user"])
                agent_id = str(agent["agent_id"])
                uid, gid = ensure_container_user(agent_id, unix_user, home, hermes_home, home_root=docker_agent_home_root(cfg))
                agent["_docker_uid"] = str(uid)
                agent["_docker_gid"] = str(gid)
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

                specs, proxy_containers = desired_specs(cfg, agent, home, hermes_home)
            except Exception as exc:
                log_agent_error(cfg, raw_agent_id, f"agent reconciliation failed: {exc}")
                continue
            desired_processes.extend(specs)
            desired_proxy_containers.update(proxy_containers)

        try:
            ensure_agent_processes(desired_processes)
        except Exception as exc:
            log_agent_error(cfg, "agent-process-helper", f"agent process reconciliation failed: {exc}")
        active_proxy_containers = remove_removed_dashboard_proxies(active_proxy_containers, desired_proxy_containers)
        time.sleep(poll_seconds)

    try:
        terminate_agent_processes()
    except Exception as exc:
        log_agent_error(cfg, "agent-process-helper", f"agent process termination failed: {exc}")
    remove_removed_dashboard_proxies(active_proxy_containers, set())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
