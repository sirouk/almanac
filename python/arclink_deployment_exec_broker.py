#!/usr/bin/env python3
"""Deployment-scoped Docker Compose broker for the local Control Node executor.

The control provisioner sends a small operation request. This broker owns the
Docker socket, reconstructs the allowed Compose command locally, and rejects
raw command input before invoking Docker.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import shutil
import stat
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from arclink_boundary import (
    TRUSTED_DOCKER_BINARY_PATHS,
    require_docker_trusted_host_risk_accepted,
    require_trusted_docker_binary,
)
from arclink_rejection_incidents import record_rejection_incident, state_root_rejection_path
import arclink_executor as executor


MAX_REQUEST_BYTES = 16384
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8912
ALLOWED_OPERATIONS = {"compose_up", "compose_ps", "compose_down"}
SERVICE_NAME = "deployment-exec-broker"


def _broker_token() -> str:
    return str(os.environ.get("ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN") or "").strip()


def _state_root_base() -> str:
    return str(os.environ.get("ARCLINK_STATE_ROOT_BASE") or "/arcdata/deployments").strip()


def _docker_binary() -> str:
    return require_trusted_docker_binary(
        os.environ.get("ARCLINK_DOCKER_BINARY"),
        service="deployment exec broker",
        trusted_paths=TRUSTED_DOCKER_BINARY_PATHS,
        which=shutil.which,
    )


def _absolute_request_path(value: str, *, label: str) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"deployment exec {label} is required")
    path = Path(raw)
    if not path.is_absolute():
        raise ValueError(f"deployment exec {label} must be absolute")
    return path


def _validate_config_directory(path: Path, *, label: str) -> None:
    try:
        stat_result = path.lstat()
    except OSError as exc:
        raise ValueError(f"deployment exec {label} is missing") from exc
    if stat.S_ISLNK(stat_result.st_mode):
        raise ValueError(f"deployment exec {label} must not be a symlink")
    if not stat.S_ISDIR(stat_result.st_mode):
        raise ValueError(f"deployment exec {label} must be a directory")


def _validate_config_file(path: Path, *, label: str) -> None:
    try:
        stat_result = path.lstat()
    except OSError as exc:
        raise ValueError(f"deployment exec {label} is missing") from exc
    if stat.S_ISLNK(stat_result.st_mode):
        raise ValueError(f"deployment exec {label} must not be a symlink")
    if not stat.S_ISREG(stat_result.st_mode):
        raise ValueError(f"deployment exec {label} must be a regular file")
    if stat_result.st_mode & 0o444 == 0:
        raise ValueError(f"deployment exec {label} must be readable")


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _is_authorized(headers: Any) -> bool:
    expected = _broker_token()
    supplied = str(headers.get(executor.DEPLOYMENT_EXEC_BROKER_TOKEN_HEADER) or "").strip()
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def _compose_args_for_operation(
    operation: str,
    *,
    remove_volumes: bool = False,
    include_all: bool = False,
) -> tuple[str, ...]:
    if operation == "compose_up":
        return ("up", "-d", "--remove-orphans")
    if operation == "compose_ps":
        return ("ps", *(("--all",) if include_all else ()), "--format", "json")
    if operation == "compose_down":
        return ("down", "--remove-orphans", *(("--volumes",) if remove_volumes else ()))
    raise ValueError("deployment exec operation is not allowlisted")


def _validate_request(request_body: dict[str, Any]) -> tuple[str, str, str, str, tuple[str, ...]]:
    if any(key in request_body for key in ("args", "cmd", "command")):
        raise ValueError("deployment exec broker does not accept raw commands")
    deployment_id = executor._require_safe_deployment_id(str(request_body.get("deployment_id") or ""))
    operation = str(request_body.get("operation") or "").strip()
    if operation not in ALLOWED_OPERATIONS:
        raise ValueError("deployment exec operation is not allowlisted")
    project_name = executor._require_compose_project_name(
        str(request_body.get("project_name") or ""),
        deployment_id=deployment_id,
        require_expected=True,
    )
    env_file = str(request_body.get("env_file") or "")
    compose_file = str(request_body.get("compose_file") or "")
    raw_env_path = _absolute_request_path(env_file, label="env file")
    raw_compose_path = _absolute_request_path(compose_file, label="compose file")
    if raw_env_path.parent != raw_compose_path.parent:
        raise ValueError("deployment exec env and compose files must share the deployment config directory")
    env_path = executor._absolute_normalized_path(env_file, label="env file")
    compose_path = executor._absolute_normalized_path(compose_file, label="compose file")
    if env_path.parent != compose_path.parent:
        raise ValueError("deployment exec env and compose files must share the deployment config directory")
    executor._validate_deployment_config_paths(
        deployment_id=deployment_id,
        state_root_base=_state_root_base(),
        root=str(compose_path.parent.parent),
        config_root=str(compose_path.parent),
        env_file=str(env_path),
        compose_file=str(compose_path),
    )
    _validate_config_directory(raw_compose_path.parent.parent, label="deployment root")
    _validate_config_directory(raw_compose_path.parent, label="config root")
    _validate_config_file(raw_env_path, label="env file")
    _validate_config_file(raw_compose_path, label="compose file")
    args = _compose_args_for_operation(
        operation,
        remove_volumes=bool(request_body.get("remove_volumes") is True),
        include_all=bool(request_body.get("include_all") is True),
    )
    return deployment_id, project_name, str(env_path), str(compose_path), args


def _rejection_reason(exc: BaseException) -> str:
    text = str(exc).lower()
    if "raw commands" in text:
        return "raw_command_rejected"
    if "trusted-host residual risk" in text:
        return "trusted_host_risk_not_accepted"
    if "operation" in text and "allowlisted" in text:
        return "operation_not_allowlisted"
    if "project" in text:
        return "project_name_rejected"
    if "docker cli" in text:
        return "docker_cli_rejected"
    if "symlink" in text or "config" in text or "env file" in text or "compose file" in text:
        return "compose_config_rejected"
    if "deployment" in text:
        return "deployment_id_rejected"
    return "validation_rejected"


def _rejection_message(reason: str) -> str:
    messages = {
        "raw_command_rejected": "Rejected raw command input.",
        "trusted_host_risk_not_accepted": "Rejected request before trusted-host acknowledgement.",
        "operation_not_allowlisted": "Rejected non-allowlisted deployment operation.",
        "project_name_rejected": "Rejected unsafe deployment project name.",
        "docker_cli_rejected": "Rejected unsafe Docker CLI configuration.",
        "compose_config_rejected": "Rejected unsafe deployment Compose configuration.",
        "deployment_id_rejected": "Rejected unsafe deployment identifier.",
        "validation_rejected": "Rejected deployment exec broker request during validation.",
    }
    return messages.get(reason, messages["validation_rejected"])


def _incident_metadata(request_body: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if not isinstance(request_body, dict):
        return metadata
    operation = str(request_body.get("operation") or "").strip()
    if operation in ALLOWED_OPERATIONS:
        metadata["operation"] = operation
    try:
        deployment_id = executor._require_safe_deployment_id(str(request_body.get("deployment_id") or ""))
    except executor.ArcLinkExecutorError:
        deployment_id = ""
    if deployment_id:
        metadata["deployment_id"] = deployment_id
        try:
            project_name = executor._require_compose_project_name(
                str(request_body.get("project_name") or ""),
                deployment_id=deployment_id,
                require_expected=True,
            )
        except executor.ArcLinkExecutorError:
            project_name = ""
        if project_name:
            metadata["project_name"] = project_name
    return metadata


def _record_rejection_incident(request_body: Any, exc: BaseException) -> None:
    reason = _rejection_reason(exc)
    record_rejection_incident(
        state_root_rejection_path(SERVICE_NAME),
        service=SERVICE_NAME,
        event="deployment_exec_broker_request_rejected",
        reason=reason,
        message=_rejection_message(reason),
        error_class=exc.__class__.__name__,
        metadata=_incident_metadata(request_body),
    )


def run_deployment_exec_request(request_body: dict[str, Any]) -> tuple[bool, dict[str, Any] | str]:
    try:
        require_docker_trusted_host_risk_accepted(service=SERVICE_NAME, error_cls=ValueError)
        deployment_id, project_name, env_file, compose_file, args = _validate_request(request_body)
    except (executor.ArcLinkExecutorError, ValueError) as exc:
        _record_rejection_incident(request_body, exc)
        return False, str(exc)
    try:
        result = executor.SubprocessDockerComposeRunner(
            docker_binary=_docker_binary()
        ).run(
            args,
            deployment_id=deployment_id,
            project_name=project_name,
            env_file=env_file,
            compose_file=compose_file,
        )
    except (executor.ArcLinkExecutorError, ValueError) as exc:
        _record_rejection_incident(request_body, exc)
        return False, str(exc)
    return True, dict(result)


class DeploymentExecBrokerHandler(BaseHTTPRequestHandler):
    server_version = "ArcLinkDeploymentExecBroker/1"

    def log_message(self, fmt: str, *args: Any) -> None:
        del fmt, args

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            _json_response(self, 404, {"ok": False, "error": "not found"})
            return
        if not _broker_token():
            _json_response(self, 503, {"ok": False, "error": "deployment exec broker token is not configured"})
            return
        _json_response(self, 200, {"ok": True})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/docker-compose":
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
            _json_response(self, 413, {"ok": False, "error": "invalid deployment exec request size"})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            _json_response(self, 400, {"ok": False, "error": "invalid JSON"})
            return
        if not isinstance(body, dict):
            _json_response(self, 400, {"ok": False, "error": "deployment exec request must be a JSON object"})
            return
        ok, payload = run_deployment_exec_request(body)
        if ok:
            _json_response(self, 200, {"ok": True, "result": payload if isinstance(payload, dict) else {}})
        else:
            _json_response(self, 400, {"ok": False, "error": str(payload)})


def serve(*, host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), DeploymentExecBrokerHandler)
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ArcLink deployment exec broker")
    parser.add_argument("--host", default=os.environ.get("ARCLINK_DEPLOYMENT_EXEC_BROKER_HOST", DEFAULT_HOST))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("ARCLINK_DEPLOYMENT_EXEC_BROKER_PORT", str(DEFAULT_PORT)) or DEFAULT_PORT),
    )
    args = parser.parse_args(argv)
    require_docker_trusted_host_risk_accepted(service=SERVICE_NAME, error_cls=SystemExit)
    if not _broker_token():
        raise SystemExit("ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN is required")
    serve(host=str(args.host), port=int(args.port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
