#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
MCP_SERVER_PY = REPO / "python" / "almanac_mcp_server.py"
NOTION_WEBHOOK_PY = REPO / "python" / "almanac_notion_webhook.py"
MCP_WRAPPER = REPO / "bin" / "almanac-mcp-server.sh"
NOTION_WRAPPER = REPO / "bin" / "almanac-notion-webhook.sh"


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
    os.environ.pop("ALMANAC_BACKEND_ALLOWED_CIDRS", None)
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    mcp_server = load_module(MCP_SERVER_PY, "almanac_mcp_server_loopback_test")
    notion_webhook = load_module(NOTION_WEBHOOK_PY, "almanac_notion_webhook_loopback_test")

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
    mcp_server = load_module(MCP_SERVER_PY, "almanac_mcp_server_cidr_test")
    notion_webhook = load_module(NOTION_WEBHOOK_PY, "almanac_notion_webhook_cidr_test")

    os.environ["ALMANAC_BACKEND_ALLOWED_CIDRS"] = "172.16.0.0/12"
    try:
        for candidate in ("172.23.0.1", "172.31.255.254"):
            expect(mcp_server.backend_client_allowed(candidate), f"expected Docker bridge CIDR to be accepted: {candidate}")
            expect(notion_webhook.backend_client_allowed(candidate), f"expected Docker bridge CIDR to be accepted: {candidate}")

        for candidate in ("100.120.112.116", "8.8.8.8", "192.168.1.2"):
            expect(not mcp_server.backend_client_allowed(candidate), f"expected outside CIDR to be rejected: {candidate}")
            expect(not notion_webhook.backend_client_allowed(candidate), f"expected outside CIDR to be rejected: {candidate}")
    finally:
        os.environ.pop("ALMANAC_BACKEND_ALLOWED_CIDRS", None)

    print("PASS test_backend_client_allowed_accepts_explicit_cidrs")


def test_wrappers_force_loopback_host_by_default() -> None:
    mcp_text = MCP_WRAPPER.read_text(encoding="utf-8")
    notion_text = NOTION_WRAPPER.read_text(encoding="utf-8")

    expect("--host 127.0.0.1" in mcp_text, "expected almanac-mcp wrapper to force loopback host")
    expect("--host 127.0.0.1" in notion_text, "expected notion webhook wrapper to force loopback host")
    expect("have_host_arg" in mcp_text, "expected almanac-mcp wrapper host override helper")
    expect("have_host_arg" in notion_text, "expected notion webhook wrapper host override helper")

    print("PASS test_wrappers_force_loopback_host_by_default")


def main() -> int:
    test_backend_client_allowed_only_accepts_loopback()
    test_backend_client_allowed_accepts_explicit_cidrs()
    test_wrappers_force_loopback_host_by_default()
    print("PASS all 3 loopback hardening regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
