#!/usr/bin/env python3
"""Root-scoped Pod migration file helper.

The action worker owns queueing, idempotency, lifecycle, and audit rows. This
helper owns only the root file-copy boundary for non-dry-run Pod migrations in
Docker mode. It reconstructs capture/materialize operations from deployment
fields and rejects raw commands.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from arclink_boundary import require_docker_trusted_host_risk_accepted
from arclink_rejection_incidents import record_rejection_incident, state_root_rejection_path
from arclink_pod_migration import (
    MIGRATION_CAPTURE_HELPER_TOKEN_HEADER,
    ArcLinkPodMigrationError,
    _copy_capture,
    _materialize_capture,
)
from arclink_provisioning import ArcLinkProvisioningError, render_arclink_state_roots


MAX_REQUEST_BYTES = 16384
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8914
DEFAULT_STATE_ROOT_BASE = "/arcdata/deployments"
SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
SAFE_MIGRATION_ID_RE = re.compile(r"^mig_[A-Za-z0-9][A-Za-z0-9_.-]{0,96}$")
ALLOWED_OPERATIONS = {"capture", "materialize"}
SERVICE_NAME = "migration-capture-helper"


def _helper_token() -> str:
    return str(os.environ.get("ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN") or "").strip()


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _is_authorized(headers: Any) -> bool:
    expected = _helper_token()
    supplied = str(headers.get(MIGRATION_CAPTURE_HELPER_TOKEN_HEADER) or "").strip()
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def _require_identifier(value: Any, *, label: str) -> str:
    clean = str(value or "").strip()
    if not SAFE_IDENTIFIER_RE.fullmatch(clean):
        raise ValueError(f"migration capture helper {label} is not a safe identifier")
    return clean


def _require_migration_id(value: Any) -> str:
    clean = str(value or "").strip()
    if not SAFE_MIGRATION_ID_RE.fullmatch(clean):
        raise ValueError("migration capture helper migration id is not safe")
    return clean


def _absolute_path(value: Any, *, label: str) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"migration capture helper {label} is required")
    path = Path(raw)
    if not path.is_absolute():
        raise ValueError(f"migration capture helper {label} must be absolute")
    resolved = path.resolve(strict=False)
    if str(resolved) == "/":
        raise ValueError(f"migration capture helper {label} must not be filesystem root")
    return resolved


def _configured_state_root_base() -> Path:
    return _absolute_path(
        os.environ.get("ARCLINK_STATE_ROOT_BASE") or DEFAULT_STATE_ROOT_BASE,
        label="configured state-root base",
    )


def _require_under_configured_base(path: Path, *, state_root_base: Path, label: str) -> None:
    try:
        path.relative_to(state_root_base)
    except ValueError as exc:
        raise ValueError(
            f"migration capture helper {label} must stay under the configured state-root base"
        ) from exc


def _expected_root_name(*, deployment_id: str, prefix: str, state_root_base: Path) -> str:
    try:
        root = render_arclink_state_roots(
            deployment_id=deployment_id,
            prefix=prefix,
            state_root_base=str(state_root_base),
        )["root"]
    except ArcLinkProvisioningError as exc:
        raise ValueError(str(exc)) from exc
    return Path(root).name


def _validate_request(request_body: dict[str, Any]) -> tuple[str, Path, Path, Path]:
    if any(key in request_body for key in ("args", "cmd", "command")):
        raise ValueError("migration capture helper does not accept raw commands")
    operation = str(request_body.get("operation") or "").strip()
    if operation not in ALLOWED_OPERATIONS:
        raise ValueError("migration capture helper operation is not allowlisted")
    deployment_id = _require_identifier(request_body.get("deployment_id"), label="deployment id")
    prefix = _require_identifier(request_body.get("prefix"), label="prefix")
    migration_id = _require_migration_id(request_body.get("migration_id"))
    source_root = _absolute_path(request_body.get("source_state_root"), label="source state root")
    target_root = _absolute_path(request_body.get("target_state_root"), label="target state root")
    capture_dir = _absolute_path(request_body.get("capture_dir"), label="capture directory")
    state_root_base = _configured_state_root_base()

    _require_under_configured_base(source_root, state_root_base=state_root_base, label="source root")
    _require_under_configured_base(target_root, state_root_base=state_root_base, label="target root")
    _require_under_configured_base(capture_dir, state_root_base=state_root_base, label="capture directory")

    expected_root_name = _expected_root_name(
        deployment_id=deployment_id,
        prefix=prefix,
        state_root_base=state_root_base,
    )
    if source_root.name != expected_root_name:
        raise ValueError("migration capture helper source root must be deployment-scoped")
    if target_root.name != expected_root_name:
        raise ValueError("migration capture helper target root must be deployment-scoped")
    if capture_dir.name != migration_id:
        raise ValueError("migration capture helper capture directory must end with the migration id")
    if capture_dir.parent.name != ".migrations" or capture_dir.parent.parent != target_root.parent:
        raise ValueError("migration capture helper capture directory must stay under the target state-root base")
    try:
        capture_dir.relative_to(source_root)
    except ValueError:
        pass
    else:
        raise ValueError("migration capture helper capture directory must not be inside the source root")
    try:
        capture_dir.relative_to(target_root)
    except ValueError:
        pass
    else:
        raise ValueError("migration capture helper capture directory must not be inside the target root")
    return operation, source_root, capture_dir, target_root


def _rejection_reason(exc: BaseException) -> str:
    text = str(exc).lower()
    if "raw commands" in text:
        return "raw_command_rejected"
    if "trusted-host residual risk" in text:
        return "trusted_host_risk_not_accepted"
    if "operation" in text and "allowlisted" in text:
        return "operation_not_allowlisted"
    if "safe identifier" in text or "migration id" in text:
        return "identifier_rejected"
    if "state-root base" in text or "deployment-scoped" in text or "capture directory" in text:
        return "state_root_rejected"
    if isinstance(exc, OSError):
        return "filesystem_error"
    return "validation_rejected"


def _rejection_message(reason: str) -> str:
    messages = {
        "raw_command_rejected": "Rejected raw command input.",
        "trusted_host_risk_not_accepted": "Rejected request before trusted-host acknowledgement.",
        "operation_not_allowlisted": "Rejected non-allowlisted migration operation.",
        "identifier_rejected": "Rejected unsafe deployment or migration identifier.",
        "state_root_rejected": "Rejected unsafe migration state-root path.",
        "filesystem_error": "Migration helper filesystem preflight failed.",
        "validation_rejected": "Rejected migration capture helper request during validation.",
    }
    return messages.get(reason, messages["validation_rejected"])


def _incident_metadata(request_body: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if not isinstance(request_body, dict):
        return metadata
    operation = str(request_body.get("operation") or "").strip()
    if operation in ALLOWED_OPERATIONS:
        metadata["operation"] = operation
    for key, label, pattern in (
        ("deployment_id", "deployment_id", SAFE_IDENTIFIER_RE),
        ("prefix", "prefix", SAFE_IDENTIFIER_RE),
        ("migration_id", "migration_id", SAFE_MIGRATION_ID_RE),
    ):
        clean = str(request_body.get(key) or "").strip()
        if pattern.fullmatch(clean):
            metadata[label] = clean
    return metadata


def _record_rejection_incident(request_body: Any, exc: BaseException) -> None:
    reason = _rejection_reason(exc)
    record_rejection_incident(
        state_root_rejection_path(SERVICE_NAME, helper=True),
        service=SERVICE_NAME,
        event="migration_capture_helper_request_rejected",
        reason=reason,
        message=_rejection_message(reason),
        error_class=exc.__class__.__name__,
        metadata=_incident_metadata(request_body),
    )


def run_migration_capture_request(request_body: dict[str, Any]) -> tuple[bool, dict[str, Any] | str]:
    try:
        require_docker_trusted_host_risk_accepted(service=SERVICE_NAME, error_cls=ValueError)
        operation, source_root, capture_dir, target_root = _validate_request(request_body)
        if operation == "capture":
            return True, _copy_capture(source_root, capture_dir)
        if operation == "materialize":
            _materialize_capture(capture_dir, target_root)
            return True, {"status": "materialized"}
    except (ArcLinkPodMigrationError, OSError, ValueError) as exc:
        _record_rejection_incident(request_body, exc)
        return False, str(exc)
    return False, "migration capture helper operation is not allowlisted"


class MigrationCaptureHelperHandler(BaseHTTPRequestHandler):
    server_version = "ArcLinkMigrationCaptureHelper/1"

    def log_message(self, fmt: str, *args: Any) -> None:
        del fmt, args

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            _json_response(self, 404, {"ok": False, "error": "not found"})
            return
        if not _helper_token():
            _json_response(self, 503, {"ok": False, "error": "migration capture helper token is not configured"})
            return
        _json_response(self, 200, {"ok": True})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/migration-capture":
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
            _json_response(self, 413, {"ok": False, "error": "invalid migration capture request size"})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            _json_response(self, 400, {"ok": False, "error": "invalid JSON"})
            return
        if not isinstance(body, dict):
            _json_response(self, 400, {"ok": False, "error": "migration capture request must be a JSON object"})
            return
        ok, payload = run_migration_capture_request(body)
        if ok:
            _json_response(self, 200, {"ok": True, "result": payload if isinstance(payload, dict) else {}})
        else:
            _json_response(self, 400, {"ok": False, "error": str(payload)})


def serve(*, host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), MigrationCaptureHelperHandler)
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ArcLink migration capture helper")
    parser.add_argument("--host", default=os.environ.get("ARCLINK_MIGRATION_CAPTURE_HELPER_HOST", DEFAULT_HOST))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("ARCLINK_MIGRATION_CAPTURE_HELPER_PORT", str(DEFAULT_PORT)) or DEFAULT_PORT),
    )
    args = parser.parse_args(argv)
    require_docker_trusted_host_risk_accepted(service=SERVICE_NAME, error_cls=SystemExit)
    if not _helper_token():
        raise SystemExit("ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN is required")
    serve(host=str(args.host), port=int(args.port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
