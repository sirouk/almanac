#!/usr/bin/env python3
"""Broker Docker dashboard sidecar operations for the agent supervisor.

The Docker-mode agent supervisor runs as root so it can create container-local
Unix users and chown their homes. This broker owns the Docker socket for the
separate dashboard network/proxy sidecar lifecycle, reconstructing the allowed
Docker commands locally and rejecting raw command input.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import ipaddress
import json
import os
import re
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from arclink_boundary import (
    TRUSTED_DOCKER_BINARY_PATHS,
    require_docker_trusted_host_risk_accepted,
    require_trusted_docker_binary,
)
from arclink_rejection_incidents import private_state_rejection_path, record_rejection_incident


MAX_REQUEST_BYTES = 16384
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8913
AGENT_SUPERVISOR_BROKER_TOKEN_HEADER = "X-ArcLink-Agent-Supervisor-Broker-Token"
SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")
SAFE_CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
SERVICE_NAME = "agent-supervisor-broker"
CONTAINER_PRIVATE_ROOT = "/home/arclink/arclink/arclink-priv"


def _broker_token() -> str:
    return str(os.environ.get("ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN") or "").strip()


def _docker_binary() -> str:
    return require_trusted_docker_binary(
        os.environ.get("ARCLINK_DOCKER_BINARY"),
        service="agent supervisor broker",
        trusted_paths=TRUSTED_DOCKER_BINARY_PATHS,
        which=shutil.which,
    )


def _docker_command(*args: str) -> list[str]:
    return [_docker_binary(), *args]


def docker_name(value: str, *, fallback: str = "agent") -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return name or fallback


def docker_dashboard_network_name(agent_id: str) -> str:
    return f"arclink-agent-dashboard-{docker_name(agent_id)}"


def docker_dashboard_proxy_container_name(agent_id: str) -> str:
    return f"arclink-agent-dashboard-proxy-{docker_name(agent_id)}"


def _require_safe_segment(value: str, *, label: str) -> str:
    clean = str(value or "").strip()
    if not SAFE_SEGMENT_RE.fullmatch(clean):
        raise ValueError(f"agent supervisor broker {label} is not a safe identifier")
    return clean


def _require_safe_container(value: str, *, label: str) -> str:
    clean = str(value or "").strip()
    if not SAFE_CONTAINER_RE.fullmatch(clean):
        raise ValueError(f"agent supervisor broker {label} is not a safe container name")
    return clean


def _require_port(value: Any, *, label: str) -> int:
    try:
        port = int(str(value or "").strip())
    except (TypeError, ValueError):
        raise ValueError(f"agent supervisor broker {label} is not a valid port") from None
    if port < 1 or port > 65535:
        raise ValueError(f"agent supervisor broker {label} is outside the valid port range")
    return port


def _require_backend_host(value: str) -> str:
    clean = str(value or "").strip()
    try:
        parsed = ipaddress.ip_address(clean)
    except ValueError:
        raise ValueError("agent supervisor broker backend host must be a Docker network IP") from None
    if parsed.is_unspecified:
        raise ValueError("agent supervisor broker backend host must not be a wildcard address")
    if parsed.is_multicast:
        raise ValueError("agent supervisor broker backend host must not be multicast")
    if parsed.is_global:
        raise ValueError("agent supervisor broker backend host must not be globally routable")
    if not (parsed.is_loopback or parsed.is_private or parsed.is_link_local):
        raise ValueError("agent supervisor broker backend host must be loopback or Docker-internal")
    return clean


def _docker_json(command: list[str]) -> Any:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout or "null")
    except json.JSONDecodeError:
        return None


def _network_container_ip(network_name: str, container_name: str) -> str:
    payload = _docker_json(_docker_command("network", "inspect", network_name))
    if not isinstance(payload, list) or not payload:
        return ""
    containers = payload[0].get("Containers") if isinstance(payload[0], dict) else None
    if not isinstance(containers, dict):
        return ""
    container_name = container_name.strip()
    for container_id, info in containers.items():
        if not isinstance(info, dict):
            continue
        names = {
            str(container_id or "").strip(),
            str(info.get("Name") or "").strip(),
            str(info.get("Name") or "").strip().lstrip("/"),
        }
        if container_name not in names and not str(container_id or "").startswith(container_name):
            continue
        raw_addr = str(info.get("IPv4Address") or "").strip()
        return raw_addr.split("/", 1)[0].strip()
    return ""


def _reject_raw_commands(request_body: dict[str, Any]) -> None:
    if any(key in request_body for key in ("args", "cmd", "command")):
        raise ValueError("agent supervisor broker does not accept raw commands")


def _ensure_dashboard_network(request_body: dict[str, Any]) -> dict[str, Any]:
    _reject_raw_commands(request_body)
    agent_id = _require_safe_segment(str(request_body.get("agent_id") or ""), label="agent id")
    supervisor_container = _require_safe_container(
        str(request_body.get("supervisor_container") or ""),
        label="supervisor container",
    )
    network_name = docker_dashboard_network_name(agent_id)
    supplied_network = str(request_body.get("network") or network_name).strip()
    if supplied_network != network_name:
        raise ValueError("agent supervisor broker dashboard network does not match agent id")

    docker = _docker_binary()
    inspect = subprocess.run(
        [docker, "network", "inspect", network_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if inspect.returncode != 0:
        subprocess.run([docker, "network", "create", "--internal", network_name], check=True)

    backend_host = _network_container_ip(network_name, supervisor_container)
    if not backend_host:
        subprocess.run(
            [
                docker,
                "network",
                "connect",
                "--alias",
                f"dashboard-backend-{docker_name(agent_id)}",
                network_name,
                supervisor_container,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        backend_host = _network_container_ip(network_name, supervisor_container)
    if not backend_host:
        raise RuntimeError(f"could not attach supervisor container to isolated dashboard network {network_name}")
    backend_host = _require_backend_host(backend_host)
    return {"network": network_name, "backend_host": backend_host}


def _host_priv_dir() -> str:
    host_priv = str(os.environ.get("ARCLINK_DOCKER_HOST_PRIV_DIR") or "")
    return _require_private_bind_root(host_priv, container=False)


def _container_priv_dir() -> str:
    container_priv = str(
        os.environ.get("ARCLINK_DOCKER_CONTAINER_PRIV_DIR") or CONTAINER_PRIVATE_ROOT
    )
    return _require_private_bind_root(container_priv, container=True)


def _require_private_bind_root(value: str, *, container: bool) -> str:
    raw = str(value or "")
    clean = raw.strip()
    invalid = ValueError("agent supervisor broker private bind root is not a safe ArcLink private-state path")
    if not clean or clean != raw:
        raise invalid
    if any(char in clean for char in ("\x00", "\n", "\r")):
        raise invalid
    if ":" in clean:
        raise invalid
    if not clean.startswith("/") or clean == "/":
        raise invalid
    parts = clean.split("/")
    if parts[0] != "" or any(part == "" for part in parts[1:]):
        raise invalid
    if any(part in (".", "..") for part in parts[1:]):
        raise invalid
    if Path(clean).name != "arclink-priv":
        raise invalid
    if container and clean != CONTAINER_PRIVATE_ROOT:
        raise invalid
    return clean


def _require_container_priv_path(value: str, *, label: str) -> str:
    container_priv = Path(_container_priv_dir()).resolve()
    try:
        path = Path(str(value or "").strip()).resolve()
    except OSError:
        raise ValueError(f"agent supervisor broker {label} is not a valid path") from None
    try:
        path.relative_to(container_priv)
    except ValueError:
        raise ValueError(f"agent supervisor broker {label} must stay under ARCLINK_DOCKER_CONTAINER_PRIV_DIR") from None
    return str(path)


def _proxy_config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _container_running_with_hash(container_name: str, config_hash: str) -> bool:
    payload = _docker_json(_docker_command("container", "inspect", container_name))
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        return False
    state = payload[0].get("State")
    config = payload[0].get("Config")
    labels = config.get("Labels") if isinstance(config, dict) else None
    return (
        isinstance(state, dict)
        and state.get("Running") is True
        and isinstance(labels, dict)
        and labels.get("arclink.proxy_config_hash") == config_hash
    )


def _ensure_dashboard_proxy(request_body: dict[str, Any]) -> dict[str, Any]:
    _reject_raw_commands(request_body)
    agent_id = _require_safe_segment(str(request_body.get("agent_id") or ""), label="agent id")
    network_name = docker_dashboard_network_name(agent_id)
    supplied_network = str(request_body.get("network") or "").strip()
    if supplied_network != network_name:
        raise ValueError("agent supervisor broker proxy network does not match agent id")
    proxy_container_name = docker_dashboard_proxy_container_name(agent_id)
    supplied_container = str(request_body.get("container_name") or proxy_container_name).strip()
    if supplied_container != proxy_container_name:
        raise ValueError("agent supervisor broker proxy container does not match agent id")
    backend_host = _require_backend_host(str(request_body.get("backend_host") or ""))
    backend_port = _require_port(request_body.get("backend_port"), label="backend port")
    proxy_port = _require_port(request_body.get("proxy_port"), label="proxy port")
    host_priv = _host_priv_dir()
    container_priv = _container_priv_dir()
    access_file = _require_container_priv_path(str(request_body.get("access_file") or ""), label="access file")
    image = str(os.environ.get("ARCLINK_DOCKER_IMAGE") or "arclink/app:local").strip()
    repo_dir = str(os.environ.get("ARCLINK_REPO_DIR") or "/home/arclink/arclink").rstrip("/")
    if not image:
        raise ValueError("ARCLINK_DOCKER_IMAGE is required for dashboard proxy sidecars")
    if not repo_dir.startswith("/home/arclink/arclink"):
        raise ValueError("ARCLINK_REPO_DIR is not an ArcLink container repo path")

    config = {
        "agent_id": agent_id,
        "backend_host": backend_host,
        "backend_port": backend_port,
        "container_priv": container_priv,
        "host_priv": host_priv,
        "image": image,
        "network": network_name,
        "proxy_port": proxy_port,
        "repo_dir": repo_dir,
        "access_file": access_file,
    }
    config_hash = _proxy_config_hash(config)
    if _container_running_with_hash(proxy_container_name, config_hash):
        return {"container": proxy_container_name, "changed": False}

    docker = _docker_binary()
    subprocess.run([docker, "rm", "-f", proxy_container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    cmd = [
        docker,
        "run",
        "-d",
        "--rm",
        "--name",
        proxy_container_name,
        "--pull",
        "never",
        "--network",
        network_name,
        "-p",
        f"127.0.0.1:{proxy_port}:{proxy_port}",
        "-v",
        f"{host_priv}:{container_priv}:rw",
        "--label",
        f"arclink.agent_id={agent_id}",
        "--label",
        f"arclink.proxy_config_hash={config_hash}",
        image,
        "python3",
        f"{repo_dir}/python/arclink_dashboard_auth_proxy.py",
        "--listen-host",
        "0.0.0.0",
        "--listen-port",
        str(proxy_port),
        "--target",
        f"http://{backend_host}:{backend_port}",
        "--access-file",
        access_file,
        "--realm",
        "Hermes",
    ]
    result = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        tail = detail[-1][:220] if detail else f"exit status {result.returncode}"
        raise RuntimeError(f"dashboard proxy sidecar failed: {tail}")
    return {"container": proxy_container_name, "changed": True}


def _remove_dashboard_proxy(request_body: dict[str, Any]) -> dict[str, Any]:
    _reject_raw_commands(request_body)
    agent_id = _require_safe_segment(str(request_body.get("agent_id") or ""), label="agent id")
    proxy_container_name = docker_dashboard_proxy_container_name(agent_id)
    supplied_container = str(request_body.get("container_name") or proxy_container_name).strip()
    if supplied_container != proxy_container_name:
        raise ValueError("agent supervisor broker proxy container does not match agent id")
    result = subprocess.run(
        [_docker_binary(), "rm", "-f", proxy_container_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return {"container": proxy_container_name, "removed": result.returncode == 0}


def _rejection_reason(exc: BaseException) -> str:
    text = str(exc).lower()
    if "raw commands" in text:
        return "raw_command_rejected"
    if "trusted-host residual risk" in text:
        return "trusted_host_risk_not_accepted"
    if "operation" in text and "allowlisted" in text:
        return "operation_not_allowlisted"
    if "docker cli" in text:
        return "docker_cli_rejected"
    if "backend host" in text:
        return "dashboard_backend_host_rejected"
    if "private bind root" in text or "private-state path" in text:
        return "private_bind_root_rejected"
    if "network" in text:
        return "dashboard_network_rejected"
    if "container" in text:
        return "dashboard_container_rejected"
    if isinstance(exc, subprocess.SubprocessError):
        return "subprocess_failed"
    if isinstance(exc, OSError):
        return "filesystem_error"
    return "validation_rejected"


def _rejection_message(reason: str) -> str:
    messages = {
        "raw_command_rejected": "Rejected raw command input.",
        "trusted_host_risk_not_accepted": "Rejected request before trusted-host acknowledgement.",
        "operation_not_allowlisted": "Rejected non-allowlisted dashboard broker operation.",
        "docker_cli_rejected": "Rejected unsafe Docker CLI configuration.",
        "dashboard_backend_host_rejected": "Rejected unsafe dashboard backend host.",
        "private_bind_root_rejected": "Rejected unsafe private bind root.",
        "dashboard_network_rejected": "Rejected unsafe dashboard network.",
        "dashboard_container_rejected": "Rejected unsafe dashboard container.",
        "subprocess_failed": "Dashboard broker subprocess failed.",
        "filesystem_error": "Dashboard broker filesystem preflight failed.",
        "validation_rejected": "Rejected agent supervisor broker request during validation.",
    }
    return messages.get(reason, messages["validation_rejected"])


def _incident_metadata(request_body: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if not isinstance(request_body, dict):
        return metadata
    operation = str(request_body.get("operation") or "").strip()
    if operation in {"ensure_dashboard_network", "ensure_dashboard_proxy", "remove_dashboard_proxy"}:
        metadata["operation"] = operation
    agent_id = str(request_body.get("agent_id") or "").strip()
    if SAFE_SEGMENT_RE.fullmatch(agent_id):
        metadata["agent_id"] = agent_id
    return metadata


def _record_rejection_incident(request_body: Any, exc: BaseException) -> None:
    reason = _rejection_reason(exc)
    record_rejection_incident(
        private_state_rejection_path(SERVICE_NAME),
        service=SERVICE_NAME,
        event="agent_supervisor_broker_request_rejected",
        reason=reason,
        message=_rejection_message(reason),
        error_class=exc.__class__.__name__,
        metadata=_incident_metadata(request_body),
    )


def run_agent_supervisor_request(request_body: dict[str, Any]) -> tuple[bool, dict[str, Any] | str]:
    try:
        require_docker_trusted_host_risk_accepted(service=SERVICE_NAME, error_cls=ValueError)
        if not isinstance(request_body, dict):
            raise ValueError("agent supervisor broker request must be a JSON object")
        operation = str(request_body.get("operation") or "").strip()
        if operation == "ensure_dashboard_network":
            return True, _ensure_dashboard_network(request_body)
        if operation == "ensure_dashboard_proxy":
            return True, _ensure_dashboard_proxy(request_body)
        if operation == "remove_dashboard_proxy":
            return True, _remove_dashboard_proxy(request_body)
        raise ValueError("agent supervisor broker operation is not allowlisted")
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        _record_rejection_incident(request_body, exc)
        return False, str(exc)


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _is_authorized(headers: Any) -> bool:
    expected = _broker_token()
    supplied = str(headers.get(AGENT_SUPERVISOR_BROKER_TOKEN_HEADER) or "").strip()
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


class AgentSupervisorBrokerHandler(BaseHTTPRequestHandler):
    server_version = "ArcLinkAgentSupervisorBroker/1"

    def log_message(self, fmt: str, *args: Any) -> None:
        del fmt, args

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            _json_response(self, 404, {"ok": False, "error": "not found"})
            return
        if not _broker_token():
            _json_response(self, 503, {"ok": False, "error": "agent supervisor broker token is not configured"})
            return
        _json_response(self, 200, {"ok": True})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/agent-supervisor":
            _json_response(self, 404, {"ok": False, "error": "not found"})
            return
        if not _is_authorized(self.headers):
            _json_response(self, 401, {"ok": False, "error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_REQUEST_BYTES:
            _json_response(self, 413, {"ok": False, "error": "invalid agent supervisor request size"})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            _json_response(self, 400, {"ok": False, "error": "invalid JSON"})
            return
        if not isinstance(body, dict):
            _json_response(self, 400, {"ok": False, "error": "agent supervisor request must be a JSON object"})
            return
        ok, payload = run_agent_supervisor_request(body)
        if ok:
            _json_response(self, 200, {"ok": True, "result": payload if isinstance(payload, dict) else {}})
        else:
            _json_response(self, 400, {"ok": False, "error": str(payload)})


def serve(*, host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), AgentSupervisorBrokerHandler)
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ArcLink agent supervisor broker")
    parser.add_argument("--host", default=os.environ.get("ARCLINK_AGENT_SUPERVISOR_BROKER_HOST", DEFAULT_HOST))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("ARCLINK_AGENT_SUPERVISOR_BROKER_PORT", str(DEFAULT_PORT)) or DEFAULT_PORT),
    )
    args = parser.parse_args(argv)
    require_docker_trusted_host_risk_accepted(service=SERVICE_NAME, error_cls=SystemExit)
    if not _broker_token():
        raise SystemExit("ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN is required")
    serve(host=str(args.host), port=int(args.port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
