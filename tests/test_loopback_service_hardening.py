#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import sys
from email.message import Message
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
MCP_SERVER_PY = REPO / "python" / "arclink_mcp_server.py"
NOTION_WEBHOOK_PY = REPO / "python" / "arclink_notion_webhook.py"
MCP_WRAPPER = REPO / "bin" / "arclink-mcp-server.sh"
NOTION_WRAPPER = REPO / "bin" / "arclink-notion-webhook.sh"
QMD_DAEMON = REPO / "bin" / "qmd-daemon.sh"
QMD_SERVICE = REPO / "systemd" / "user" / "arclink-qmd-mcp.service"


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


def test_backend_client_allowed_only_accepts_loopback() -> None:
    os.environ.pop("ARCLINK_BACKEND_ALLOWED_CIDRS", None)
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    mcp_server = load_module(MCP_SERVER_PY, "arclink_mcp_server_loopback_test")
    notion_webhook = load_module(NOTION_WEBHOOK_PY, "arclink_notion_webhook_loopback_test")

    for candidate in ("127.0.0.1", "::1"):
        expect(mcp_server.backend_client_allowed(candidate), f"expected loopback to be accepted: {candidate}")
        expect(notion_webhook.backend_client_allowed(candidate), f"expected loopback to be accepted: {candidate}")

    for candidate in ("100.120.112.116", "8.8.8.8", "fd7a:115c:a1e0::6c34:7076"):
        expect(not mcp_server.backend_client_allowed(candidate), f"expected non-loopback to be rejected: {candidate}")
        expect(not notion_webhook.backend_client_allowed(candidate), f"expected non-loopback to be rejected: {candidate}")

    print("PASS test_backend_client_allowed_only_accepts_loopback")


def test_backend_client_allowed_accepts_explicit_cidrs() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    mcp_server = load_module(MCP_SERVER_PY, "arclink_mcp_server_cidr_test")
    notion_webhook = load_module(NOTION_WEBHOOK_PY, "arclink_notion_webhook_cidr_test")

    os.environ["ARCLINK_BACKEND_ALLOWED_CIDRS"] = "172.16.0.0/12"
    try:
        for candidate in ("172.23.0.1", "172.31.255.254"):
            expect(mcp_server.backend_client_allowed(candidate), f"expected Docker bridge CIDR to be accepted: {candidate}")
            expect(notion_webhook.backend_client_allowed(candidate), f"expected Docker bridge CIDR to be accepted: {candidate}")

        for candidate in ("100.120.112.116", "8.8.8.8", "192.168.1.2"):
            expect(not mcp_server.backend_client_allowed(candidate), f"expected outside CIDR to be rejected: {candidate}")
            expect(not notion_webhook.backend_client_allowed(candidate), f"expected outside CIDR to be rejected: {candidate}")
    finally:
        os.environ.pop("ARCLINK_BACKEND_ALLOWED_CIDRS", None)

    print("PASS test_backend_client_allowed_accepts_explicit_cidrs")


def test_notion_health_endpoint_is_available_before_transport_guard() -> None:
    body = NOTION_WEBHOOK_PY.read_text(encoding="utf-8")
    health_check = 'if self.path == "/health":'
    transport_guard = "if not self._require_loopback_transport():"
    expect(health_check in body and transport_guard in body, body)
    expect(body.index(health_check) < body.index(transport_guard, body.index("def do_GET")), body)
    print("PASS test_notion_health_endpoint_is_available_before_transport_guard")


def test_wrappers_force_loopback_host_by_default() -> None:
    mcp_text = MCP_WRAPPER.read_text(encoding="utf-8")
    notion_text = NOTION_WRAPPER.read_text(encoding="utf-8")

    expect("--host 127.0.0.1" in mcp_text, "expected arclink-mcp wrapper to force loopback host")
    expect("--host 127.0.0.1" in notion_text, "expected notion webhook wrapper to force loopback host")
    expect("have_host_arg" in mcp_text, "expected arclink-mcp wrapper host override helper")
    expect("have_host_arg" in notion_text, "expected notion webhook wrapper host override helper")

    print("PASS test_wrappers_force_loopback_host_by_default")


def test_qmd_daemon_defaults_to_loopback_without_docker_forwarder_env() -> None:
    body = QMD_DAEMON.read_text(encoding="utf-8")
    service = QMD_SERVICE.read_text(encoding="utf-8")

    expect('loopback_port="${QMD_MCP_LOOPBACK_PORT:-${QMD_MCP_PORT:-8181}}"' in body, body)
    expect('container_port="${QMD_MCP_CONTAINER_PORT:-$loopback_port}"' in body, body)
    expect("mcp --http --host 127.0.0.1 --port" in body, body)
    expect("QMD_MCP_CONTAINER_PORT" not in service, service)
    print("PASS test_qmd_daemon_defaults_to_loopback_without_docker_forwarder_env")


def test_loopback_proxy_identity_headers_are_not_trusted_by_default() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    mcp_server = load_module(MCP_SERVER_PY, "arclink_mcp_server_proxy_header_test")
    handler = object.__new__(mcp_server.Handler)
    handler.client_address = ("127.0.0.1", 12345)
    headers = Message()
    headers["Tailscale-User-Login"] = "spoof@example.test"
    headers["Tailscale-User-Name"] = "Spoof"
    handler.headers = headers

    old_env = os.environ.copy()
    try:
        os.environ.pop("ARCLINK_ALLOW_LOOPBACK_SOURCE_IP_OVERRIDE", None)
        os.environ.pop("ARCLINK_TRUST_TAILSCALE_PROXY_HEADERS", None)
        expect(handler._request_source_ip({"source_ip": "100.64.1.2"}) == "127.0.0.1", "source_ip override should be ignored by default")
        expect(handler._tailscale_identity() == {}, "Tailscale identity headers should be ignored by default")
        os.environ["ARCLINK_ALLOW_LOOPBACK_SOURCE_IP_OVERRIDE"] = "1"
        os.environ["ARCLINK_TRUST_TAILSCALE_PROXY_HEADERS"] = "1"
        expect(handler._request_source_ip({"source_ip": "100.64.1.2"}) == "100.64.1.2", "explicit source override opt-in failed")
        expect(handler._tailscale_identity()["login"] == "spoof@example.test", "explicit proxy header trust opt-in failed")
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    print("PASS test_loopback_proxy_identity_headers_are_not_trusted_by_default")


def main() -> int:
    test_backend_client_allowed_only_accepts_loopback()
    test_backend_client_allowed_accepts_explicit_cidrs()
    test_notion_health_endpoint_is_available_before_transport_guard()
    test_wrappers_force_loopback_host_by_default()
    test_qmd_daemon_defaults_to_loopback_without_docker_forwarder_env()
    test_loopback_proxy_identity_headers_are_not_trusted_by_default()
    print("PASS all 6 loopback hardening regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
