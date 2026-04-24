#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
MCP_SERVER = PYTHON_DIR / "almanac_mcp_server.py"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_module(path: Path, name: str):
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class DummyHandler:
    def __init__(self) -> None:
        self.status: int | None = None
        self.headers: list[tuple[str, str]] = []
        self.wfile = io.BytesIO()

    def send_response(self, status: int) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.headers.append((key, value))

    def end_headers(self) -> None:
        return None


def test_rpc_error_uses_http_200_for_jsonrpc_failures() -> None:
    mod = load_module(MCP_SERVER, "almanac_mcp_server_http_compat_test")
    handler = DummyHandler()
    mod.Handler._rpc_error(
        handler,
        "payload must be an object, not str",
        request_id=2,
        code=-32000,
        status=400,
    )
    expect(handler.status == 200, f"expected HTTP 200 for JSON-RPC error, got {handler.status}")
    payload = json.loads(handler.wfile.getvalue().decode("utf-8"))
    expect(payload["error"]["message"] == "payload must be an object, not str", str(payload))
    print("PASS test_rpc_error_uses_http_200_for_jsonrpc_failures")


def main() -> int:
    test_rpc_error_uses_http_200_for_jsonrpc_failures()
    print("PASS all 1 Almanac MCP HTTP compatibility tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
