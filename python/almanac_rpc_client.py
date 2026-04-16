#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def mcp_call(url: str, tool_name: str, arguments: dict) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    def rpc(payload: dict, session_id: str | None = None) -> tuple[str | None, dict]:
        request_headers = dict(headers)
        if session_id:
            request_headers["mcp-session-id"] = session_id
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=request_headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read().decode("utf-8", errors="replace")
                parsed = json.loads(body) if body.strip() else {}
                if "error" in parsed:
                    raise RuntimeError(parsed["error"]["message"])
                return response.headers.get("mcp-session-id") or session_id, parsed
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body) if body.strip() else {}
            except json.JSONDecodeError:
                parsed = {}
            message = (((parsed or {}).get("error") or {}).get("message")) or str(exc)
            raise RuntimeError(message) from exc

    session_id, _ = rpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "almanac-rpc-client", "version": "1.0"},
            },
        }
    )
    rpc({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}, session_id)
    _, response = rpc(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        },
        session_id,
    )
    return ((response or {}).get("result") or {}).get("structuredContent") or {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Call almanac-mcp tools over HTTP.")
    parser.add_argument("--url", required=True, help="Full http://host:port/mcp URL")
    parser.add_argument("--tool", required=True, help="Tool name, e.g. bootstrap.request")
    parser.add_argument("--json-args", default="{}", help="JSON object of tool arguments")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        payload = json.loads(args.json_args)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid --json-args payload: {exc}")
    try:
        result = mcp_call(args.url, args.tool, payload)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(str(exc))
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
