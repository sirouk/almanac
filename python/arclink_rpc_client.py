#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

from arclink_http import http_request, parse_json_response


def mcp_call(url: str, tool_name: str, arguments: dict) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    def rpc(payload: dict, session_id: str | None = None) -> tuple[str | None, dict]:
        request_headers = dict(headers)
        if session_id:
            request_headers["mcp-session-id"] = session_id
        response = http_request(
            url,
            method="POST",
            headers=request_headers,
            json_payload=payload,
            timeout=20,
        )
        try:
            parsed = parse_json_response(response, label=url)
            if not isinstance(parsed, dict):
                raise RuntimeError("response payload was not a JSON object")
            if "error" in parsed:
                raise RuntimeError(parsed["error"]["message"])
            if response.status_code >= 400:
                raise RuntimeError(f"{url} returned {response.status_code}")
            return response.headers.get("mcp-session-id") or session_id, parsed
        except RuntimeError as exc:
            if response.status_code >= 400:
                try:
                    parsed = parse_json_response(response, label=url)
                except RuntimeError:
                    parsed = {}
                message = (((parsed or {}).get("error") or {}).get("message")) or str(exc)
                raise RuntimeError(message) from exc
            raise

    session_id, _ = rpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "arclink-rpc-client", "version": "1.0"},
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
    result = ((response or {}).get("result") or {})
    structured = result.get("structuredContent")
    if isinstance(structured, dict) and structured:
        return structured
    content = result.get("content")
    if isinstance(content, list) and content:
        text_chunks: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and item.get("text"):
                text_chunks.append(str(item.get("text") or ""))
            resource = item.get("resource")
            if isinstance(resource, dict) and resource.get("text"):
                text_chunks.append(str(resource.get("text") or ""))
        return {
            "content": content,
            "text": "\n\n".join(text_chunks).strip(),
        }
    return {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Call arclink-mcp tools over HTTP.")
    parser.add_argument("--url", required=True, help="Full MCP URL, e.g. http://127.0.0.1:8282/mcp or https://host/arclink-mcp")
    parser.add_argument("--tool", required=True, help="Tool name, e.g. bootstrap.request")
    parser.add_argument("--json-args", default=None, help="JSON object of tool arguments")
    parser.add_argument(
        "--json-args-file",
        default=None,
        help="Read JSON object tool arguments from this file, or '-' for stdin. Prefer this for secret-bearing payloads.",
    )
    return parser.parse_args()


def load_json_args(args: argparse.Namespace) -> dict:
    if args.json_args and args.json_args_file:
        raise SystemExit("choose only one of --json-args or --json-args-file")
    if args.json_args_file:
        try:
            raw_payload = sys.stdin.read() if args.json_args_file == "-" else open(args.json_args_file, "r", encoding="utf-8").read()
        except OSError as exc:
            raise SystemExit(f"cannot read --json-args-file: {exc}") from exc
    else:
        raw_payload = args.json_args or "{}"
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        label = "--json-args-file" if args.json_args_file else "--json-args"
        raise SystemExit(f"invalid {label} payload: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("tool arguments must be a JSON object")
    return payload


def main() -> None:
    args = parse_args()
    payload = load_json_args(args)
    try:
        result = mcp_call(args.url, args.tool, payload)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(str(exc))
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
