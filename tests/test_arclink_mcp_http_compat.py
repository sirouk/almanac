#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
MCP_SERVER = PYTHON_DIR / "arclink_mcp_server.py"


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
    mod = load_module(MCP_SERVER, "arclink_mcp_server_http_compat_test")
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


def test_mcp_session_recovery_accepts_stale_tool_sessions() -> None:
    mod = load_module(MCP_SERVER, "arclink_mcp_server_session_recovery_test")
    sessions: set[str] = set()
    session_id, ok = mod._ensure_mcp_session("tools/call", "stale-after-restart", sessions)
    expect(ok, "stale tools/call session should recover")
    expect(session_id == "stale-after-restart", f"expected stale id to be reused, got {session_id}")
    expect("stale-after-restart" in sessions, f"expected recovered session to be tracked, got {sessions}")
    print("PASS test_mcp_session_recovery_accepts_stale_tool_sessions")


def test_mcp_session_recovery_mints_missing_safe_session() -> None:
    mod = load_module(MCP_SERVER, "arclink_mcp_server_missing_session_recovery_test")
    sessions: set[str] = set()
    session_id, ok = mod._ensure_mcp_session("tools/list", None, sessions)
    expect(ok, "missing tools/list session should recover")
    expect(isinstance(session_id, str) and session_id.startswith("session-"), f"unexpected session id {session_id}")
    expect(session_id in sessions, f"expected minted session to be tracked, got {sessions}")
    print("PASS test_mcp_session_recovery_mints_missing_safe_session")


def test_mcp_session_recovery_still_requires_initialize_for_unknown_methods() -> None:
    mod = load_module(MCP_SERVER, "arclink_mcp_server_unknown_session_recovery_test")
    sessions: set[str] = set()
    session_id, ok = mod._ensure_mcp_session("resources/read", None, sessions)
    expect(not ok, "unknown MCP methods should still require initialize")
    expect(session_id is None, f"unexpected recovered session id {session_id}")
    expect(sessions == set(), f"unexpected sessions created for unsupported method: {sessions}")
    print("PASS test_mcp_session_recovery_still_requires_initialize_for_unknown_methods")


def test_mcp_json_body_rejects_invalid_and_oversized_lengths() -> None:
    mod = load_module(MCP_SERVER, "arclink_mcp_server_body_cap_test")
    old_env = os.environ.copy()
    try:
        bad_length = DummyHandler()
        bad_length.headers = {"Content-Length": "not-a-number"}
        bad_length.rfile = io.BytesIO(b"{}")
        try:
            mod.Handler._json_body(bad_length)
            raise AssertionError("invalid Content-Length should fail")
        except mod.MCPBodyError as exc:
            expect(exc.status == 400 and "Content-Length" in str(exc), str(exc))

        os.environ["ARCLINK_MCP_MAX_REQUEST_BYTES"] = "4"
        oversized = DummyHandler()
        oversized.headers = {"Content-Length": "5"}
        oversized.rfile = io.BytesIO(b"{}")
        try:
            mod.Handler._json_body(oversized)
            raise AssertionError("oversized MCP body should fail")
        except mod.MCPBodyError as exc:
            expect(exc.status == 413 and "too large" in str(exc), str(exc))
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    print("PASS test_mcp_json_body_rejects_invalid_and_oversized_lengths")


def main() -> int:
    test_rpc_error_uses_http_200_for_jsonrpc_failures()
    test_mcp_session_recovery_accepts_stale_tool_sessions()
    test_mcp_session_recovery_mints_missing_safe_session()
    test_mcp_session_recovery_still_requires_initialize_for_unknown_methods()
    test_mcp_json_body_rejects_invalid_and_oversized_lengths()
    print("PASS all 5 ArcLink MCP HTTP compatibility tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
