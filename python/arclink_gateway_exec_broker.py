#!/usr/bin/env python3
"""Narrow gateway-exec broker for public selected-Agent turns.

This process owns Docker exec authority for Raven-mediated public-channel
Agent replies. Notification delivery sends a deployment-scoped request; the
broker reconstructs the only supported Docker command locally and rejects raw
command input.
"""
from __future__ import annotations

import argparse
import hmac
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
from arclink_rejection_incidents import record_rejection_incident, state_root_rejection_path
import arclink_notification_delivery as delivery


MAX_REQUEST_BYTES = 65536
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8911
DEPLOYMENT_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$")
SERVICE_NAME = "gateway-exec-broker"


def _broker_token() -> str:
    return delivery.config_env_value("ARCLINK_GATEWAY_EXEC_BROKER_TOKEN", "").strip()


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _is_authorized(headers: Any) -> bool:
    expected = _broker_token()
    supplied = str(headers.get(delivery.GATEWAY_EXEC_BROKER_TOKEN_HEADER) or "").strip()
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def _clean_timeout(value: Any) -> int:
    try:
        raw = int(value)
    except (TypeError, ValueError):
        raw = 240
    return max(30, min(86400, raw))


def _docker_binary() -> str:
    return require_trusted_docker_binary(
        os.environ.get("ARCLINK_DOCKER_BINARY"),
        service="gateway exec broker",
        trusted_paths=TRUSTED_DOCKER_BINARY_PATHS,
        which=shutil.which,
    )


def _incident_deployment_id(request_body: Any) -> str | None:
    if not isinstance(request_body, dict):
        return None
    clean = str(request_body.get("deployment_id") or "").strip()
    if DEPLOYMENT_SEGMENT_RE.fullmatch(clean):
        return clean
    return None


def _incident_project_name(deployment_id: str | None) -> str | None:
    if not deployment_id:
        return None
    project_name = delivery._compose_project_name(deployment_id)
    if delivery.PUBLIC_AGENT_BRIDGE_PROJECT_RE.fullmatch(project_name):
        return project_name
    return None


def _incident_metadata(request_body: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    deployment_id = _incident_deployment_id(request_body)
    project_name = _incident_project_name(deployment_id)
    if deployment_id:
        metadata["deployment_id"] = deployment_id
    if project_name:
        metadata["project_name"] = project_name
    return metadata


def _rejection_reason(exc: BaseException) -> str:
    text = str(exc).lower()
    if "raw commands" in text:
        return "raw_command_rejected"
    if "project name does not match" in text:
        return "project_name_mismatch"
    if "platform is not supported" in text:
        return "unsupported_platform"
    if "trusted-host residual risk" in text:
        return "trusted_host_risk_not_accepted"
    if "safe deployment path segment" in text:
        return "deployment_segment_rejected"
    if "payload must be a json object" in text:
        return "invalid_payload"
    if "payload is missing" in text:
        return "payload_required_field_missing"
    if "payload text exceeds" in text:
        return "payload_text_limit_exceeded"
    if "docker cli" in text:
        return "docker_cli_rejected"
    if "container/root not found" in text:
        return "deployment_not_found"
    if "compose" in text or "symlink" in text:
        return "compose_config_rejected"
    if "command rejected" in text or "allowlisted" in text:
        return "command_not_allowlisted"
    return "validation_rejected"


def _rejection_message(reason: str) -> str:
    messages = {
        "raw_command_rejected": "Rejected raw command input.",
        "project_name_mismatch": "Rejected project-name mismatch.",
        "unsupported_platform": "Rejected unsupported public Agent platform.",
        "trusted_host_risk_not_accepted": "Rejected request before trusted-host acknowledgement.",
        "deployment_segment_rejected": "Rejected unsafe deployment identifier.",
        "invalid_payload": "Rejected invalid public Agent payload shape.",
        "payload_required_field_missing": "Rejected public Agent payload with missing required metadata.",
        "payload_text_limit_exceeded": "Rejected public Agent payload over the size limit.",
        "docker_cli_rejected": "Rejected unsafe Docker CLI configuration.",
        "deployment_not_found": "Rejected request because no deployment runtime was found.",
        "compose_config_rejected": "Rejected unsafe Compose fallback configuration.",
        "command_not_allowlisted": "Rejected non-allowlisted gateway exec command.",
        "validation_rejected": "Rejected gateway exec broker request during validation.",
    }
    return messages.get(reason, messages["validation_rejected"])


def _record_rejection_incident(request_body: Any, exc: BaseException) -> None:
    reason = _rejection_reason(exc)
    record_rejection_incident(
        state_root_rejection_path(SERVICE_NAME),
        service=SERVICE_NAME,
        event="gateway_exec_broker_request_rejected",
        reason=reason,
        message=_rejection_message(reason),
        error_class=exc.__class__.__name__,
        metadata=_incident_metadata(request_body),
    )


def _require_safe_segment(value: str, *, label: str, allow_blank: bool = False) -> str:
    clean = str(value or "").strip()
    if not clean and allow_blank:
        return ""
    if not DEPLOYMENT_SEGMENT_RE.fullmatch(clean):
        raise ValueError(f"gateway exec {label} is not a safe deployment path segment")
    return clean


def _validate_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("gateway exec payload must be a JSON object")
    clean = dict(payload)
    platform = str(clean.get("platform") or "").strip().lower()
    if platform not in {"telegram", "discord"}:
        raise ValueError("gateway exec payload platform is not supported")
    if not str(clean.get("bot_token") or "").strip():
        raise ValueError("gateway exec payload is missing bot token")
    if not str(clean.get("chat_id") or "").strip():
        raise ValueError("gateway exec payload is missing chat id")
    if not str(clean.get("user_id") or "").strip():
        raise ValueError("gateway exec payload is missing user id")
    text = str(clean.get("text") or "")
    if not text.strip():
        raise ValueError("gateway exec payload is missing text")
    if len(text) > 8000:
        raise ValueError("gateway exec payload text exceeds the public bridge limit")
    clean["platform"] = platform
    clean["text"] = text
    return clean


def _build_gateway_exec_command(request_body: dict[str, Any]) -> tuple[list[str], dict[str, Any], int, str]:
    if "cmd" in request_body or "command" in request_body:
        raise ValueError("gateway exec broker does not accept raw commands")
    operator_stack = bool(request_body.get("operator_stack"))
    if operator_stack:
        project_name = str(request_body.get("project_name") or "arclink").strip()
        if not project_name:
            raise ValueError("gateway exec project name is missing")
        if project_name != (os.environ.get("ARCLINK_CONTROL_COMPOSE_PROJECT") or "arclink"):
            raise ValueError("operator gateway exec project does not match the Control Node project")
        if not delivery.PUBLIC_AGENT_BRIDGE_PROJECT_RE.fullmatch(project_name):
            raise ValueError("gateway exec project name is not allowlisted")
        payload = _validate_payload(request_body.get("payload"))
        timeout_seconds = _clean_timeout(request_body.get("timeout_seconds"))
        bridge_cmd = [
            delivery.PUBLIC_AGENT_BRIDGE_PYTHON,
            delivery.PUBLIC_AGENT_BRIDGE_SCRIPT,
        ]
        docker = _docker_binary()
        container = delivery._deployment_service_container(
            project_name=project_name,
            service="control-operator-hermes-gateway",
            docker_binary=docker,
        )
        if not container:
            raise ValueError("operator Hermes gateway container not found in the Control Node stack")
        semantic_cmd = ["docker", "exec", "-i", container, *bridge_cmd]
        valid, _kind, reason = delivery._validate_public_agent_bridge_cmd(semantic_cmd, project_name=project_name)
        if not valid:
            raise ValueError(f"gateway exec command rejected: {reason}")
        return [docker, *semantic_cmd[1:]], payload, timeout_seconds, project_name
    deployment_id = _require_safe_segment(str(request_body.get("deployment_id") or ""), label="deployment id")
    prefix = _require_safe_segment(str(request_body.get("prefix") or ""), label="prefix", allow_blank=True)
    expected_project = delivery._compose_project_name(deployment_id)
    project_name = str(request_body.get("project_name") or "").strip() or expected_project
    if not expected_project:
        raise ValueError("gateway exec deployment id is missing")
    if project_name != expected_project:
        raise ValueError("gateway exec project name does not match deployment id")
    if not delivery.PUBLIC_AGENT_BRIDGE_PROJECT_RE.fullmatch(project_name):
        raise ValueError("gateway exec project name is not allowlisted")
    payload = _validate_payload(request_body.get("payload"))
    timeout_seconds = _clean_timeout(request_body.get("timeout_seconds"))
    bridge_cmd = [
        delivery.PUBLIC_AGENT_BRIDGE_PYTHON,
        delivery.PUBLIC_AGENT_BRIDGE_SCRIPT,
    ]
    docker = _docker_binary()
    container = delivery._deployment_service_container(
        project_name=project_name,
        service="hermes-gateway",
        docker_binary=docker,
    )
    if container:
        semantic_cmd = ["docker", "exec", "-i", container, *bridge_cmd]
        cmd = [docker, *semantic_cmd[1:]]
    else:
        root = delivery._deployment_root(deployment_id=deployment_id, prefix=prefix)
        if root is None:
            raise ValueError("deployment container/root not found for gateway bridge")
        compose_file = root / "config" / "compose.yaml"
        env_file = root / "config" / "arclink.env"
        try:
            delivery._preflight_deployment_compose_config_files(
                env_file=env_file,
                compose_file=compose_file,
                context="gateway exec broker Compose fallback",
            )
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        semantic_cmd = [
            "docker",
            "compose",
            "-p",
            project_name,
            "--env-file",
            str(env_file),
            "-f",
            str(compose_file),
            "exec",
            "-T",
            "hermes-gateway",
            *bridge_cmd,
        ]
        cmd = [docker, *semantic_cmd[1:]]
    valid, _kind, reason = delivery._validate_public_agent_bridge_cmd(semantic_cmd, project_name=project_name)
    if not valid:
        raise ValueError(f"gateway exec command rejected: {reason}")
    return cmd, payload, timeout_seconds, project_name


def run_gateway_exec_request(request_body: dict[str, Any]) -> tuple[bool, str]:
    try:
        require_docker_trusted_host_risk_accepted(service=SERVICE_NAME, error_cls=ValueError)
        cmd, payload, timeout_seconds, _project_name = _build_gateway_exec_command(request_body)
    except ValueError as exc:
        _record_rejection_incident(request_body, exc)
        return False, str(exc)
    try:
        proc = subprocess.run(
            cmd,
            input=json.dumps(payload, sort_keys=True),
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return False, "Hermes public gateway bridge timed out"
    except OSError as exc:
        return False, f"could not start Hermes public gateway bridge: {str(exc)[:180]}"
    if proc.returncode != 0:
        return False, f"Hermes public gateway bridge failed with exit status {proc.returncode}"
    try:
        payload_out = json.loads(str(proc.stdout or "{}").strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        payload_out = {}
    if isinstance(payload_out, dict) and payload_out.get("ok") is True:
        return True, ""
    return False, "Hermes public gateway bridge completed without an ok response"


class GatewayExecBrokerHandler(BaseHTTPRequestHandler):
    server_version = "ArcLinkGatewayExecBroker/1"

    def log_message(self, fmt: str, *args: Any) -> None:
        del fmt, args

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            _json_response(self, 404, {"ok": False, "error": "not found"})
            return
        if not _broker_token():
            _json_response(self, 503, {"ok": False, "error": "gateway exec broker token is not configured"})
            return
        _json_response(self, 200, {"ok": True})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/public-agent-bridge":
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
            _json_response(self, 413, {"ok": False, "error": "invalid gateway exec request size"})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            _json_response(self, 400, {"ok": False, "error": "invalid JSON"})
            return
        if not isinstance(body, dict):
            _json_response(self, 400, {"ok": False, "error": "gateway exec request must be a JSON object"})
            return
        ok, error = run_gateway_exec_request(body)
        if ok:
            _json_response(self, 200, {"ok": True})
        else:
            _json_response(self, 400, {"ok": False, "error": error})


def serve(*, host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), GatewayExecBrokerHandler)
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ArcLink gateway exec broker")
    parser.add_argument("--host", default=os.environ.get("ARCLINK_GATEWAY_EXEC_BROKER_HOST", DEFAULT_HOST))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("ARCLINK_GATEWAY_EXEC_BROKER_PORT", str(DEFAULT_PORT)) or DEFAULT_PORT),
    )
    args = parser.parse_args(argv)
    require_docker_trusted_host_risk_accepted(service=SERVICE_NAME, error_cls=SystemExit)
    if not _broker_token():
        raise SystemExit("ARCLINK_GATEWAY_EXEC_BROKER_TOKEN is required")
    serve(host=str(args.host), port=int(args.port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
