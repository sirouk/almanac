#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
RPC_CLIENT = PYTHON_DIR / "almanac_rpc_client.py"


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


def response(payload: dict, *, session_id: str | None = None) -> SimpleNamespace:
    headers = {"mcp-session-id": session_id} if session_id else {}
    return SimpleNamespace(status_code=200, text=json.dumps(payload), headers=headers)


def test_mcp_call_returns_resource_text_when_structured_content_is_absent() -> None:
    mod = load_module(RPC_CLIENT, "almanac_rpc_client_resource_fallback_test")
    calls: list[dict] = []

    def fake_http_request(url, *, method, headers, json_payload, timeout):  # noqa: ANN001
        calls.append(json_payload)
        rpc_method = json_payload.get("method")
        if rpc_method == "initialize":
            return response({"jsonrpc": "2.0", "id": 1, "result": {}}, session_id="sid-1")
        if rpc_method == "notifications/initialized":
            return response({"jsonrpc": "2.0", "result": {}})
        return response(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "content": [
                        {
                            "type": "resource",
                            "resource": {
                                "uri": "qmd://vault-pdf-ingest/mesh.md",
                                "mimeType": "text/markdown",
                                "text": "Mesh is a Chutes system.\n",
                            },
                        }
                    ]
                },
            }
        )

    mod.http_request = fake_http_request
    result = mod.mcp_call("http://127.0.0.1:8181/mcp", "get", {"file": "#d33c3b"})
    expect(result["text"] == "Mesh is a Chutes system.", str(result))
    expect(result["content"][0]["resource"]["uri"] == "qmd://vault-pdf-ingest/mesh.md", str(result))
    expect(calls[-1]["params"]["name"] == "get", str(calls))
    print("PASS test_mcp_call_returns_resource_text_when_structured_content_is_absent")


def main() -> int:
    test_mcp_call_returns_resource_text_when_structured_content_is_absent()
    print("PASS all 1 Almanac RPC client regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
