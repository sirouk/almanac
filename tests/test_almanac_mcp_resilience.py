#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
MCP_SERVER = REPO / "python" / "almanac_mcp_server.py"
CONTROL = REPO / "python" / "almanac_control.py"
PYTHON_DIR = REPO / "python"


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


class FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeSqliteConn:
    def __init__(self) -> None:
        self.closed = False
        self.executed: list[str] = []
        self.row_factory = None

    def execute(self, sql: str):  # noqa: ANN201
        self.executed.append(sql)
        return self

    def close(self) -> None:
        self.closed = True


def test_control_connect_db_retries_transient_lock_during_startup_maintenance() -> None:
    mod = load_module(CONTROL, "almanac_control_sqlite_retry_test")
    attempts = {"connect": 0, "expire": 0}
    conns: list[FakeSqliteConn] = []
    sleeps: list[float] = []

    def fake_connect(path, timeout):  # noqa: ANN001, ANN202
        attempts["connect"] += 1
        conn = FakeSqliteConn()
        conns.append(conn)
        return conn

    def flaky_expire(conn):  # noqa: ANN001, ANN202
        attempts["expire"] += 1
        if attempts["expire"] == 1:
            raise sqlite3.OperationalError("database is locked")
        return 0

    original_connect = mod.sqlite3.connect
    mod.sqlite3.connect = fake_connect
    mod.ensure_runtime_paths = lambda cfg: None
    mod.ensure_schema = lambda conn, cfg: None
    mod._migrate_onboarding_bot_tokens = lambda conn, cfg: None
    mod.expire_stale_ssot_pending_writes = flaky_expire
    mod.time.sleep = sleeps.append
    mod._control_sqlite_retry_seconds = lambda: 5.0

    try:
        cfg = SimpleNamespace(db_path=Path("/tmp/almanac-control-test.sqlite3"))
        result = mod.connect_db(cfg)
    finally:
        mod.sqlite3.connect = original_connect

    expect(attempts == {"connect": 2, "expire": 2}, f"unexpected attempts: {attempts}")
    expect(sleeps == [0.25], f"expected one control DB retry sleep, got {sleeps}")
    expect(conns[0].closed, "failed startup connection should be closed before retry")
    expect(result is conns[1], "connect_db should return the successful retry connection")
    print("PASS test_control_connect_db_retries_transient_lock_during_startup_maintenance")


def test_mcp_dispatch_retries_transient_sqlite_lock_before_serving_status() -> None:
    mod = load_module(MCP_SERVER, "almanac_mcp_server_sqlite_retry_test")
    attempts = {"count": 0}
    sleeps: list[float] = []

    def flaky_connect_db(cfg):  # noqa: ANN001, ANN202
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise sqlite3.OperationalError("database is locked")
        return FakeConn()

    mod.connect_db = flaky_connect_db
    mod.list_vault_warnings = lambda conn: []
    mod.time.sleep = sleeps.append
    mod._mcp_sqlite_retry_seconds = lambda: 5.0

    handler = object.__new__(mod.Handler)
    handler.server = SimpleNamespace(cfg=SimpleNamespace(qmd_url="http://127.0.0.1:8181/mcp"))

    result = handler._dispatch_tool("status", {})

    expect(attempts["count"] == 2, f"expected one retry after sqlite lock, got {attempts['count']}")
    expect(sleeps == [0.25], f"expected initial sqlite retry sleep, got {sleeps}")
    expect(result["service"] == "almanac-mcp", str(result))
    expect(result["vault_warning_count"] == 0, str(result))
    print("PASS test_mcp_dispatch_retries_transient_sqlite_lock_before_serving_status")


def test_qmd_bridge_retries_locked_or_unreachable_mcp_once_before_returning_result() -> None:
    mod = load_module(MCP_SERVER, "almanac_mcp_server_qmd_retry_test")
    attempts = {"count": 0}
    sleeps: list[float] = []

    def flaky_http_request(url, *, method, headers, json_payload, timeout):  # noqa: ANN001, ANN202
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("database is locked")

        class Response:
            status_code = 200
            headers = {"mcp-session-id": "session-test"}

        if json_payload.get("method") == "tools/call":
            Response.payload = {"jsonrpc": "2.0", "id": 2, "result": {"content": [{"type": "text", "text": "ok"}]}}
        else:
            Response.payload = {"jsonrpc": "2.0", "id": json_payload.get("id"), "result": {}}
        return Response()

    mod.http_request = flaky_http_request
    mod.parse_json_response = lambda response, label: response.payload
    mod.time.sleep = sleeps.append
    mod._mcp_qmd_retry_seconds = lambda: 5.0

    result = mod._mcp_tool_call("http://127.0.0.1:8181/mcp", "get", {"file": "README.md"})

    expect(attempts == {"count": 4}, f"expected failed initialize plus complete retry, got {attempts}")
    expect(sleeps == [0.25], f"expected initial qmd retry sleep, got {sleeps}")
    expect(result["content"][0]["text"] == "ok", str(result))
    print("PASS test_qmd_bridge_retries_locked_or_unreachable_mcp_once_before_returning_result")


def main() -> int:
    test_control_connect_db_retries_transient_lock_during_startup_maintenance()
    test_mcp_dispatch_retries_transient_sqlite_lock_before_serving_status()
    test_qmd_bridge_retries_locked_or_unreachable_mcp_once_before_returning_result()
    print("PASS all Almanac MCP resilience tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
