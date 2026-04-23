#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from almanac_control import (
    Config,
    RateLimitError,
    approve_request,
    approve_ssot_pending_write,
    bootstrap_status,
    build_managed_memory_payload,
    connect_db,
    consume_agent_notifications,
    consume_curator_brief_fanout,
    deny_request,
    deny_ssot_pending_write,
    enqueue_ssot_write,
    get_ssot_pending_write,
    is_loopback_ip,
    is_tailnet_ip,
    list_notifications,
    list_agent_ssot_pending_writes,
    count_ssot_pending_writes,
    list_requests,
    list_vault_warnings,
    notion_fetch,
    notion_query,
    notion_search,
    note_refresh_job,
    preflight_ssot_write,
    queue_notification,
    read_ssot,
    refresh_agent_context,
    register_agent,
    reinstate_token,
    reload_vault_definitions,
    request_bootstrap,
    revoke_token,
    set_subscription_from_token,
    subscription_catalog,
    validate_operator_token,
    validate_token,
)


TOOLS = {
    "status": "Return control-plane status and vault warnings.",
    "bootstrap.request": "Request agent enrollment approval.",
    "bootstrap.handshake": "Start enrollment immediately; manual flows receive a pending token, while auto-provisioned flows queue operator approval without SSH.",
    "bootstrap.status": "Poll bootstrap request status and receive the issued token once.",
    "bootstrap.approve": "Approve a bootstrap request. Requires operator-class token.",
    "bootstrap.deny": "Deny a bootstrap request. Requires operator-class token.",
    "bootstrap.revoke": "Revoke a token by token_id or agent_id. Requires operator-class token.",
    "bootstrap.reinstate": "Reinstate a revoked token. Requires operator-class token.",
    "agents.register": "Register or reenroll a Curator or user agent.",
    "catalog.vaults": "List active vault catalog entries for an authenticated agent.",
    "vaults.refresh": "Run an authenticated subscription refresh for an agent.",
    "vaults.subscribe": "Subscribe or unsubscribe an authenticated agent to a vault.",
    "vaults.reload-defs": "Reload .vault definitions from disk. Requires operator-class token.",
    "agents.managed-memory": "Fetch the caller's canonical managed-memory payload, including routing stubs, Notion digest, and the user-scoped today-plate work snapshot.",
    "agents.consume-notifications": "Atomically read+ack notifications targeted at the caller's agent.",
    "curator.fanout": "Run the curator brief-fanout consumer. Requires operator-class token.",
    "notifications.list": "List queued notifications. Requires operator-class token.",
    "ssot.read": "Read the shared Notion SSOT through the central broker with caller-scoped filtering. Use for scoped shared-database reads (org rows owned/assigned to the caller). For broad knowledge lookup by phrase, call notion.search or notion.search-and-fetch instead.",
    "ssot.pending": "List the caller's own shared Notion writes that are pending or recently decided. Use when the user asks about their queue in general; for a specific pending_id, call ssot.status instead.",
    "ssot.preflight": "Check whether a Notion SSOT write would apply, queue for user approval, or fail before attempting the write. Use quietly when writeability is uncertain.",
    "ssot.write": "Apply a Notion SSOT write (insert/update/append) through the central broker. Out-of-scope writes queue for user approval; surface the returned pending_id only when needed. Archive/delete are rejected. For cross-turn follow-up on a queued write, call ssot.status.",
    "ssot.status": "Check one previously queued SSOT write by pending_id for the calling agent. Prefer over ssot.pending when the pending_id is already known.",
    "ssot.approve": "Approve one of the caller's own queued Notion writes after the user explicitly approves it in chat.",
    "ssot.deny": "Deny one of the caller's own queued Notion writes after the user declines it in chat.",
    "notion.search": "Search shared Notion knowledge through Almanac's qmd-backed indexed Notion rail. Call when the user wants a phrase/title discovery only; prefer notion.search-and-fetch when you also need the body to answer.",
    "notion.fetch": "Fetch the live body or schema of a shared Notion page/database/data source by exact id or URL. Prefer over notion.search when the user already gave a URL or id, or says they just edited the page.",
    "notion.query": "Run a live structured query against a shared Notion database/data source. Prefer for owner/status/due/assignee filters instead of page-by-page search.",
    "notion.search-and-fetch": "Search shared Notion knowledge and fetch bounded live page bodies for the top matching pages. One-shot replacement for \"search, pick, fetch\" loops; bounded by search_limit ≤10, fetch_limit ≤3, body_char_limit ≤12000.",
}


def _schema(
    properties: dict[str, dict],
    *,
    required: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


AGENT_TOKEN_PROP = {
    "type": "string",
    "minLength": 1,
    "description": "Harness-injected agent bootstrap token. Hermes agents should omit this field; almanac-managed-context fills it before dispatch. Legacy/operator CLIs may still pass it explicitly.",
}
REGISTRATION_TOKEN_PROP = {
    "type": "string",
    "minLength": 1,
    "description": "Enrollment or bootstrap token for registration flows. Normal enrolled-agent tools use a harness-injected token instead.",
}
OPERATOR_TOKEN_PROP = {
    "type": "string",
    "minLength": 1,
    "description": "Operator-class token for admin-only tools. The server also accepts this value as token for legacy callers, but operator_token is preferred.",
}
ACTOR_PROP = {
    "type": "string",
    "description": "Optional audit actor label. Defaults to the authenticated agent_id.",
}
SURFACE_PROP = {
    "type": "string",
    "enum": ["curator-channel", "curator-tui", "ctl"],
    "default": "curator-channel",
    "description": "Operator decision surface. Invalid values normalize to the default in the server.",
}
NOTION_QUERY_PROP = {
    "type": "object",
    "description": "Notion API query payload, such as filter, sorts, start_cursor, or page_size.",
    "additionalProperties": True,
}
SSOT_PAYLOAD_PROP = {
    "type": "object",
    "description": "Notion write payload. update/insert usually use properties. For append, pass exactly {'children': [...]} with no 'after'. Almanac strips/stamps Changed By, Author, and Requested By attribution fields.",
    "additionalProperties": True,
}


def _operator_schema(properties: dict[str, dict], *, required: list[str] | tuple[str, ...] = ()) -> dict[str, Any]:
    return _schema(
        {
            "operator_token": OPERATOR_TOKEN_PROP,
            "token": OPERATOR_TOKEN_PROP,
            **properties,
        },
        required=tuple(dict.fromkeys(("operator_token", *required))),
    )


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "status": _schema({}),
    "bootstrap.request": _schema(
        {
            "requester_identity": {"type": "string", "description": "Human or system requesting enrollment."},
            "unix_user": {"type": "string", "description": "Requested Unix account/user name."},
            "source_ip": {"type": "string", "description": "Optional caller IP override accepted only from loopback."},
            "auto_provision": {"type": "boolean", "description": "Queue an operator-approved auto-provision flow instead of a manual request."},
            "model_preset": {"type": "string", "description": "Optional requested Almanac model preset."},
            "channels": {"type": "array", "items": {"type": "string"}, "description": "Requested delivery channels, e.g. tui-only, discord, telegram."},
        },
        required=("unix_user",),
    ),
    "bootstrap.handshake": _schema(
        {
            "requester_identity": {"type": "string", "description": "Human or system requesting enrollment."},
            "unix_user": {"type": "string", "description": "Requested Unix account/user name."},
            "source_ip": {"type": "string", "description": "Optional caller IP override accepted only from loopback."},
            "auto_provision": {"type": "boolean", "description": "Queue an operator-approved auto-provision flow."},
            "model_preset": {"type": "string", "description": "Optional requested Almanac model preset."},
            "channels": {"type": "array", "items": {"type": "string"}, "description": "Requested delivery channels, e.g. tui-only, discord, telegram."},
        },
        required=("unix_user",),
    ),
    "bootstrap.status": _schema(
        {
            "request_id": {"type": "string", "description": "Bootstrap request id returned by bootstrap.request or bootstrap.handshake."},
            "source_ip": {"type": "string", "description": "Optional original source IP when polling through loopback."},
        },
        required=("request_id",),
    ),
    "bootstrap.approve": _operator_schema(
        {
            "request_id": {"type": "string"},
            "surface": SURFACE_PROP,
            "actor": {"type": "string"},
        },
        required=("request_id",),
    ),
    "bootstrap.deny": _operator_schema(
        {
            "request_id": {"type": "string"},
            "surface": SURFACE_PROP,
            "actor": {"type": "string"},
        },
        required=("request_id",),
    ),
    "bootstrap.revoke": _operator_schema(
        {
            "target": {"type": "string", "description": "Token id or agent id to revoke."},
            "surface": SURFACE_PROP,
            "actor": {"type": "string"},
            "reason": {"type": "string", "default": "revoked"},
        },
        required=("target",),
    ),
    "bootstrap.reinstate": _operator_schema(
        {
            "token_id": {"type": "string"},
            "surface": SURFACE_PROP,
            "actor": {"type": "string"},
        },
        required=("token_id",),
    ),
    "agents.register": _schema(
        {
            "token": REGISTRATION_TOKEN_PROP,
            "unix_user": {"type": "string"},
            "display_name": {"type": "string"},
            "role": {"type": "string", "enum": ["user", "curator"], "default": "user"},
            "hermes_home": {"type": "string", "description": "Absolute HERMES_HOME path for this agent."},
            "model_preset": {"type": "string"},
            "model_string": {"type": "string"},
            "channels": {"type": "array", "items": {"type": "string"}},
            "home_channel": {"type": "object", "additionalProperties": True},
            "operator_notify_channel": {"type": "object", "additionalProperties": True},
        },
        required=("token", "unix_user", "hermes_home"),
    ),
    "catalog.vaults": _schema({"token": AGENT_TOKEN_PROP}),
    "vaults.refresh": _schema({"token": AGENT_TOKEN_PROP}),
    "vaults.subscribe": _schema(
        {
            "token": AGENT_TOKEN_PROP,
            "vault_name": {"type": "string"},
            "subscribed": {"type": "boolean", "description": "true subscribes; false unsubscribes."},
        },
        required=("vault_name", "subscribed"),
    ),
    "vaults.reload-defs": _operator_schema({}),
    "agents.managed-memory": _schema({"token": AGENT_TOKEN_PROP}),
    "agents.consume-notifications": _schema(
        {
            "token": AGENT_TOKEN_PROP,
            "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 100},
        },
    ),
    "curator.fanout": _operator_schema({}),
    "notifications.list": _operator_schema(
        {
            "target_kind": {"type": "string", "description": "Optional target kind filter."},
            "target_id": {"type": "string", "description": "Optional target id filter."},
            "undelivered_only": {"type": "boolean", "default": False},
        },
    ),
    "ssot.read": _schema(
        {
            "token": AGENT_TOKEN_PROP,
            "target_id": {"type": "string", "description": "Optional page/database/data-source id or URL. Omit for the configured shared SSOT database."},
            "query": NOTION_QUERY_PROP,
            "include_markdown": {"type": "boolean", "default": False, "description": "For page reads, include live markdown body."},
            "actor": ACTOR_PROP,
        },
    ),
    "ssot.pending": _schema(
        {
            "token": AGENT_TOKEN_PROP,
            "status": {"type": "string", "enum": ["pending", "applied", "denied", "expired"], "default": "pending"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
        },
    ),
    "ssot.status": _schema(
        {
            "token": AGENT_TOKEN_PROP,
            "pending_id": {"type": "string", "minLength": 1, "description": "Pending id returned by ssot.write when final_state is queued."},
        },
        required=("pending_id",),
    ),
    "ssot.approve": _schema(
        {
            "token": AGENT_TOKEN_PROP,
            "pending_id": {"type": "string", "minLength": 1, "description": "Pending id returned by ssot.write when final_state is queued."},
            "actor": ACTOR_PROP,
        },
        required=("pending_id",),
    ),
    "ssot.deny": _schema(
        {
            "token": AGENT_TOKEN_PROP,
            "pending_id": {"type": "string", "minLength": 1, "description": "Pending id returned by ssot.write when final_state is queued."},
            "reason": {"type": "string", "description": "Optional user-facing reason."},
            "actor": ACTOR_PROP,
        },
        required=("pending_id",),
    ),
    "ssot.preflight": _schema(
        {
            "token": AGENT_TOKEN_PROP,
            "operation": {"type": "string", "enum": ["insert", "update", "append"], "description": "Mutating SSOT operation to check without applying."},
            "target_id": {"type": "string", "description": "Target page/database/data-source id or URL."},
            "payload": SSOT_PAYLOAD_PROP,
            "actor": ACTOR_PROP,
        },
        required=("operation", "payload"),
    ),
    "ssot.write": _schema(
        {
            "token": AGENT_TOKEN_PROP,
            "operation": {"type": "string", "enum": ["insert", "update", "append"], "description": "Mutating SSOT operation. Archive/delete/trash/destroy are intentionally unsupported and rejected by the broker."},
            "target_id": {"type": "string", "description": "Required for append/update. For insert, use the parent page/database/data-source id or URL when the configured SSOT target is not enough."},
            "payload": SSOT_PAYLOAD_PROP,
            "read_after": {"type": "boolean", "default": False, "description": "When true and the write applies immediately, include a brokered ssot.read of the resulting target. Leave false unless the user asked to verify live state."},
            "read_after_include_markdown": {"type": "boolean", "default": False, "description": "When read_after is true, include live markdown for page targets."},
            "actor": ACTOR_PROP,
        },
        required=("operation", "payload"),
    ),
    "notion.search": _schema(
        {
            "token": AGENT_TOKEN_PROP,
            "query": {"type": "string", "minLength": 1, "description": "Search text for shared Notion knowledge. Indexed/qmd-backed and may lag recent edits."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
            "rerank": {"type": "boolean", "default": False, "description": "Use only when quality matters more than latency."},
            "actor": ACTOR_PROP,
        },
        required=("query",),
    ),
    "notion.fetch": _schema(
        {
            "token": AGENT_TOKEN_PROP,
            "target_id": {"type": "string", "minLength": 1, "description": "Exact Notion page/database/data-source id or URL. Live read; prefer for recent or exact pages."},
            "actor": ACTOR_PROP,
        },
        required=("target_id",),
    ),
    "notion.query": _schema(
        {
            "token": AGENT_TOKEN_PROP,
            "target_id": {"type": "string", "description": "Database/data-source id or URL. Optional only when a default shared database is configured."},
            "query": NOTION_QUERY_PROP,
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
            "actor": ACTOR_PROP,
        },
    ),
    "notion.search-and-fetch": _schema(
        {
            "token": AGENT_TOKEN_PROP,
            "query": {"type": "string", "minLength": 1, "description": "Search text for shared Notion knowledge. The search step is indexed/qmd-backed and may lag recent edits."},
            "search_limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
            "fetch_limit": {"type": "integer", "minimum": 0, "maximum": 3, "default": 2},
            "body_char_limit": {"type": "integer", "minimum": 200, "maximum": 12000, "default": 4000},
            "rerank": {"type": "boolean", "default": False},
            "actor": ACTOR_PROP,
        },
        required=("query",),
    ),
}


def _tool_schema(name: str) -> dict[str, Any]:
    return TOOL_SCHEMAS.get(name, {"type": "object", "properties": {}, "additionalProperties": False})


def _clamp_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        if value is None or value == "":
            parsed = default
        else:
            parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _bool_arg(arguments: dict, name: str, *, default: bool = False, required: bool = False) -> bool:
    if name not in arguments or arguments.get(name) is None:
        if required:
            raise ValueError(f"{name} must be a boolean")
        return default
    value = arguments.get(name)
    if isinstance(value, bool):
        return value
    raise ValueError(f"{name} must be a boolean, not {type(value).__name__}")


def _dict_arg(arguments: dict, name: str, *, default_empty: bool = True, required: bool = False) -> dict:
    if name not in arguments or arguments.get(name) is None:
        if required:
            raise ValueError(f"{name} must be an object")
        return {} if default_empty else None  # type: ignore[return-value]
    value = arguments.get(name)
    if isinstance(value, dict):
        return value
    raise ValueError(f"{name} must be an object, not {type(value).__name__}")


def _trim_text(value: object, limit: int) -> tuple[str, bool]:
    text = str(value or "")
    if len(text) <= limit:
        return text, False
    suffix = "..."
    return text[: max(0, limit - len(suffix))].rstrip() + suffix, True


def _notion_search_hit_target_id(hit: dict[str, Any]) -> str:
    for key in ("page_id", "page_url", "target_id", "id", "url"):
        value = str(hit.get(key) or "").strip()
        if value:
            return value

    # qmd-backed Notion index hits may only expose the markdown path. Those
    # files are named <notion-page-id>-000.md, so recover the id from there.
    file_value = str(hit.get("file") or "").strip()
    if file_value:
        stem = Path(file_value).stem
        match = re.search(r"([0-9a-fA-F]{32})(?:-\d+)?$", stem)
        if match:
            return match.group(1)
    return ""


def _compact_notion_search_hit(hit: dict[str, Any], *, snippet_char_limit: int = 700) -> dict[str, Any]:
    snippet, snippet_truncated = _trim_text(hit.get("snippet"), snippet_char_limit)
    target_id = _notion_search_hit_target_id(hit)
    result = {
        "source": str(hit.get("source") or ""),
        "root_id": str(hit.get("root_id") or ""),
        "page_id": str(hit.get("page_id") or target_id),
        "page_url": str(hit.get("page_url") or ""),
        "page_title": str(hit.get("page_title") or ""),
        "section_heading": str(hit.get("section_heading") or ""),
        "breadcrumb": hit.get("breadcrumb") if isinstance(hit.get("breadcrumb"), list) else [],
        "owners": hit.get("owners") if isinstance(hit.get("owners"), list) else [],
        "last_edited_time": str(hit.get("last_edited_time") or ""),
        "file": str(hit.get("file") or ""),
        "score": hit.get("score"),
        "snippet": snippet,
        "snippet_truncated": snippet_truncated,
    }
    return result


def _compact_notion_search_result(result: dict[str, Any], *, snippet_char_limit: int = 700) -> dict[str, Any]:
    hits = result.get("results") if isinstance(result.get("results"), list) else []
    return {
        "ok": bool(result.get("ok")),
        "query": str(result.get("query") or ""),
        "collection": str(result.get("collection") or ""),
        "index_ready": bool(result.get("index_ready")),
        "index_doc_count": int(result.get("index_doc_count") or 0),
        "roots": result.get("roots") if isinstance(result.get("roots"), list) else [],
        "results": [
            _compact_notion_search_hit(hit, snippet_char_limit=snippet_char_limit)
            for hit in hits
            if isinstance(hit, dict)
        ],
    }


def _compact_notion_fetch_result(result: dict[str, Any], *, body_char_limit: int) -> dict[str, Any]:
    target_kind = str(result.get("target_kind") or "")
    if target_kind != "page":
        return {
            "ok": bool(result.get("ok")),
            "target_id": str(result.get("target_id") or ""),
            "target_kind": target_kind,
            "indexed": bool(result.get("indexed")),
            "database_id": str(result.get("database_id") or ""),
            "data_source_id": str(result.get("data_source_id") or ""),
        }
    markdown, truncated = _trim_text(result.get("markdown"), body_char_limit)
    page = result.get("page") if isinstance(result.get("page"), dict) else {}
    return {
        "ok": bool(result.get("ok")),
        "target_id": str(result.get("target_id") or ""),
        "target_kind": "page",
        "indexed": bool(result.get("indexed")),
        "indexed_roots": result.get("indexed_roots") if isinstance(result.get("indexed_roots"), list) else [],
        "page_url": str(page.get("url") or ""),
        "markdown": markdown,
        "markdown_truncated": truncated,
        "attachments": result.get("attachments") if isinstance(result.get("attachments"), list) else [],
    }


def _ssot_final_state(payload: dict[str, Any]) -> str:
    if bool(payload.get("applied")):
        return "applied"
    if bool(payload.get("queued")) or bool(payload.get("approval_required")):
        return "queued"
    return str(payload.get("status") or "unknown")


def _normalize_ssot_write_result(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.setdefault("final_state", _ssot_final_state(result))
    return result


def backend_client_allowed(remote_ip: str) -> bool:
    return is_loopback_ip(str(remote_ip or "").strip())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Almanac control-plane HTTP server.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    return parser.parse_args()


class AlmanacServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler_cls: type[BaseHTTPRequestHandler], cfg: Config):
        super().__init__(server_address, handler_cls)
        self.cfg = cfg
        self.sessions: set[str] = set()


class Handler(BaseHTTPRequestHandler):
    server: AlmanacServer

    def _require_loopback_transport(self, *, request_id: int | str | None = None) -> bool:
        remote_ip = str(self.client_address[0] or "").strip()
        if backend_client_allowed(remote_ip):
            return True
        self._rpc_error(
            "backend only accepts loopback connections",
            request_id,
            code=-32001,
            status=403,
        )
        return False

    def _send_json(self, payload: dict, status: int = HTTPStatus.OK, session_id: str | None = None) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        if session_id:
            self.send_header("mcp-session-id", session_id)
        self.end_headers()
        self.wfile.write(raw)

    def _json_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(content_length)
        return json.loads(raw.decode("utf-8") or "{}")

    def _rpc_success(self, result: dict, request_id: int | str | None, session_id: str | None) -> None:
        self._send_json({"jsonrpc": "2.0", "id": request_id, "result": result}, session_id=session_id)

    def _rpc_error(
        self,
        message: str,
        request_id: int | str | None,
        code: int = -32000,
        status: int = 400,
        extra_data: dict | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        error: dict[str, Any] = {"code": code, "message": message}
        if extra_data:
            error["data"] = extra_data
        raw = json.dumps({"jsonrpc": "2.0", "id": request_id, "error": error}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        if not self._require_loopback_transport():
            return
        if self.path != "/health":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        with connect_db(self.server.cfg) as conn:
            warnings = list_vault_warnings(conn)
        self._send_json(
            {
                "ok": True,
                "service": "almanac-mcp",
                "port": self.server.cfg.public_mcp_port,
                "vault_warning_count": len(warnings),
            }
        )

    def do_POST(self) -> None:  # noqa: N802
        if not self._require_loopback_transport():
            return
        if self.path != "/mcp":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        try:
            body = self._json_body()
        except json.JSONDecodeError:
            self._rpc_error("invalid JSON body", None, status=400)
            return

        method = body.get("method")
        request_id = body.get("id")
        session_id = self.headers.get("mcp-session-id")

        if method == "initialize":
            session_id = session_id or f"session-{secrets.token_hex(8)}"
            self.server.sessions.add(session_id)
            self._rpc_success(
                {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "almanac-mcp", "version": "1.0"},
                },
                request_id,
                session_id,
            )
            return

        if session_id not in self.server.sessions:
            self._rpc_error("missing or invalid mcp-session-id; initialize first", request_id, status=400)
            return

        if method == "notifications/initialized":
            self._send_json({}, session_id=session_id)
            return

        if method == "tools/list":
            tools = [
                {
                    "name": name,
                    "description": description,
                    "inputSchema": _tool_schema(name),
                }
                for name, description in TOOLS.items()
            ]
            self._rpc_success({"tools": tools}, request_id, session_id)
            return

        if method != "tools/call":
            self._rpc_error(f"unsupported method: {method}", request_id, status=400)
            return

        params = body.get("params") or {}
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}

        try:
            result = self._dispatch_tool(str(tool_name), arguments)
        except PermissionError as exc:
            self._rpc_error(str(exc), request_id, code=-32001, status=403)
            return
        except RateLimitError as exc:
            self._rpc_error(
                str(exc),
                request_id,
                code=-32029,
                status=429,
                extra_data={"retry_after_seconds": exc.retry_after_seconds, "scope": exc.scope},
                extra_headers={"Retry-After": str(exc.retry_after_seconds)},
            )
            return
        except RuntimeError as exc:
            self._rpc_error(str(exc), request_id, code=-32029, status=429)
            return
        except Exception as exc:  # noqa: BLE001
            self._rpc_error(str(exc), request_id, status=400)
            return

        self._rpc_success(
            {
                "content": [{"type": "text", "text": json.dumps(result, sort_keys=True)}],
                "structuredContent": result,
            },
            request_id,
            session_id,
        )

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _request_source_ip(self, arguments: dict) -> str:
        remote_ip = self.client_address[0]
        declared_ip = str(arguments.get("source_ip") or "").strip()
        if is_loopback_ip(remote_ip) and declared_ip:
            return declared_ip
        return remote_ip

    def _ensure_bootstrap_source_allowed(self, source_ip: str) -> None:
        if is_tailnet_ip(source_ip) or is_loopback_ip(source_ip):
            return
        raise PermissionError(f"bootstrap tool rejected for non-tailnet source: {source_ip}")

    def _tailscale_identity(self) -> dict[str, str]:
        """Extract the Tailscale Serve proxy identity headers.

        Tailscale Serve strips client-supplied copies and injects these
        cryptographically-verified values on every proxied request. When
        present, they are the authoritative caller identity — much stronger
        than the raw source_ip (which behind the proxy is always 127.0.0.1).
        Returns an empty dict when the request did not come through Tailscale
        Serve (direct loopback, local testing, etc.).
        """
        login = (self.headers.get("Tailscale-User-Login") or "").strip()
        name = (self.headers.get("Tailscale-User-Name") or "").strip()
        profile_pic = (self.headers.get("Tailscale-User-Profile-Pic") or "").strip()
        if not login and not name:
            return {}
        return {"login": login, "name": name, "profile_pic": profile_pic}

    def _require_operator(self, conn, arguments: dict) -> str:
        raw_token = str(arguments.get("operator_token") or arguments.get("token") or "")
        if not raw_token:
            raise PermissionError("operator_token required for admin tool")
        row = validate_operator_token(conn, raw_token)
        return str(row["agent_id"])

    def _match_status_request(self, conn, arguments: dict) -> str:
        """bootstrap.status is gated by (request_id + source_ip) match, acting as a capability."""
        request_id = str(arguments.get("request_id") or "")
        if not request_id:
            raise PermissionError("request_id required")
        row = conn.execute(
            "SELECT source_ip FROM bootstrap_requests WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        if row is None:
            raise PermissionError("unknown request_id")
        source_ip = self._request_source_ip(arguments)
        if str(row["source_ip"]) != source_ip:
            raise PermissionError("source IP does not match request origin")
        return request_id

    def _dispatch_tool(self, tool_name: str, arguments: dict) -> dict:
        cfg = self.server.cfg
        with connect_db(cfg) as conn:
            if tool_name == "status":
                warnings = list_vault_warnings(conn)
                return {
                    "service": "almanac-mcp",
                    "qmd_url": cfg.qmd_url,
                    "vault_warning_count": len(warnings),
                    "vault_warnings": warnings,
                }

            if tool_name in {"bootstrap.request", "bootstrap.handshake"}:
                source_ip = self._request_source_ip(arguments)
                self._ensure_bootstrap_source_allowed(source_ip)
                ts_identity = self._tailscale_identity()
                # When Tailscale Serve forwards the request, prefer the verified
                # identity over whatever the client put in `requester_identity`.
                # The raw source_ip is always loopback behind the proxy, so use
                # the tailnet login as the rate-limit subject too — otherwise one
                # noisy caller exhausts the per-IP bucket for the whole tailnet.
                if ts_identity.get("login"):
                    requester_identity = ts_identity["login"]
                else:
                    requester_identity = str(arguments.get("requester_identity") or arguments.get("unix_user") or "unknown")
                return request_bootstrap(
                    conn,
                    cfg,
                    requester_identity=requester_identity,
                    unix_user=str(arguments.get("unix_user") or "unknown"),
                    source_ip=source_ip,
                    tailnet_identity=ts_identity,
                    issue_pending_token=(tool_name == "bootstrap.handshake"),
                    auto_provision=_bool_arg(arguments, "auto_provision"),
                    requested_model_preset=str(arguments.get("model_preset") or ""),
                    requested_channels=list(arguments.get("channels") or []),
                )

            if tool_name == "bootstrap.status":
                request_id = self._match_status_request(conn, arguments)
                return bootstrap_status(conn, cfg, request_id)

            if tool_name == "bootstrap.approve":
                actor_agent = self._require_operator(conn, arguments)
                return approve_request(
                    conn,
                    request_id=str(arguments.get("request_id") or ""),
                    surface=str(arguments.get("surface") or "curator-channel"),
                    actor=str(arguments.get("actor") or actor_agent),
                    cfg=cfg,
                )

            if tool_name == "bootstrap.deny":
                actor_agent = self._require_operator(conn, arguments)
                return deny_request(
                    conn,
                    request_id=str(arguments.get("request_id") or ""),
                    surface=str(arguments.get("surface") or "curator-channel"),
                    actor=str(arguments.get("actor") or actor_agent),
                    cfg=cfg,
                )

            if tool_name == "bootstrap.revoke":
                actor_agent = self._require_operator(conn, arguments)
                count = revoke_token(
                    conn,
                    target=str(arguments.get("target") or ""),
                    surface=str(arguments.get("surface") or "curator-channel"),
                    actor=str(arguments.get("actor") or actor_agent),
                    reason=str(arguments.get("reason") or "revoked"),
                    cfg=cfg,
                )
                return {"revoked": count}

            if tool_name == "bootstrap.reinstate":
                actor_agent = self._require_operator(conn, arguments)
                return reinstate_token(
                    conn,
                    token_id=str(arguments.get("token_id") or ""),
                    actor=str(arguments.get("actor") or actor_agent),
                    surface=str(arguments.get("surface") or "curator-channel"),
                    cfg=cfg,
                )

            if tool_name == "agents.register":
                return register_agent(
                    conn,
                    cfg,
                    raw_token=str(arguments.get("token") or ""),
                    unix_user=str(arguments.get("unix_user") or ""),
                    display_name=str(arguments.get("display_name") or arguments.get("unix_user") or ""),
                    role=str(arguments.get("role") or "user"),
                    hermes_home=str(arguments.get("hermes_home") or ""),
                    model_preset=str(arguments.get("model_preset") or ""),
                    model_string=str(arguments.get("model_string") or ""),
                    channels=list(arguments.get("channels") or []),
                    home_channel=arguments.get("home_channel"),
                    operator_notify_channel=arguments.get("operator_notify_channel"),
                )

            if tool_name == "catalog.vaults":
                return {"vaults": subscription_catalog(conn, str(arguments.get("token") or ""))}

            if tool_name == "vaults.refresh":
                return refresh_agent_context(conn, cfg, raw_token=str(arguments.get("token") or ""))

            if tool_name == "vaults.subscribe":
                subscribed = _bool_arg(arguments, "subscribed", required=True)
                result = set_subscription_from_token(
                    conn,
                    raw_token=str(arguments.get("token") or ""),
                    vault_name=str(arguments.get("vault_name") or ""),
                    subscribed=subscribed,
                )
                note_refresh_job(
                    conn,
                    job_name=f"{result['agent_id']}-subscription",
                    job_kind="agent-subscription",
                    target_id=result["agent_id"],
                    schedule="manual",
                    status="ok",
                    note=f"{result['vault_name']} -> {result['subscribed']}",
                )
                queue_notification(
                    conn,
                    target_kind="curator",
                    target_id=result["agent_id"],
                    channel_kind="brief-fanout",
                    message=(
                        f"{result['agent_id']} subscription change: "
                        f"{result['vault_name']} -> {result['subscribed']}"
                    ),
                )
                return result

            if tool_name == "vaults.reload-defs":
                self._require_operator(conn, arguments)
                return reload_vault_definitions(conn, cfg)

            if tool_name == "agents.managed-memory":
                token_row = validate_token(conn, str(arguments.get("token") or ""))
                return build_managed_memory_payload(
                    conn, cfg, agent_id=str(token_row["agent_id"])
                )

            if tool_name == "agents.consume-notifications":
                token_row = validate_token(conn, str(arguments.get("token") or ""))
                limit = _clamp_int(arguments.get("limit"), default=100, minimum=1, maximum=200)
                return {
                    "agent_id": str(token_row["agent_id"]),
                    "notifications": consume_agent_notifications(
                        conn, agent_id=str(token_row["agent_id"]), limit=limit
                    ),
                }

            if tool_name == "curator.fanout":
                self._require_operator(conn, arguments)
                return consume_curator_brief_fanout(conn, cfg)

            if tool_name == "notifications.list":
                self._require_operator(conn, arguments)
                notifications = list_notifications(
                    conn,
                    target_kind=arguments.get("target_kind"),
                    target_id=arguments.get("target_id"),
                    undelivered_only=_bool_arg(arguments, "undelivered_only"),
                )
                return {"notifications": notifications}

            if tool_name == "notion.search":
                token_row = validate_token(conn, str(arguments.get("token") or ""))
                return notion_search(
                    conn,
                    cfg,
                    agent_id=str(token_row["agent_id"]),
                    query_text=str(arguments.get("query") or ""),
                    limit=_clamp_int(arguments.get("limit"), default=5, minimum=1, maximum=10),
                    rerank=_bool_arg(arguments, "rerank"),
                    requested_by_actor=str(arguments.get("actor") or token_row["agent_id"]),
                )

            if tool_name == "notion.search-and-fetch":
                token_row = validate_token(conn, str(arguments.get("token") or ""))
                actor = str(arguments.get("actor") or token_row["agent_id"])
                body_char_limit = _clamp_int(
                    arguments.get("body_char_limit"),
                    default=4000,
                    minimum=200,
                    maximum=12000,
                )
                search_result = notion_search(
                    conn,
                    cfg,
                    agent_id=str(token_row["agent_id"]),
                    query_text=str(arguments.get("query") or ""),
                    limit=_clamp_int(arguments.get("search_limit"), default=5, minimum=1, maximum=10),
                    rerank=_bool_arg(arguments, "rerank"),
                    requested_by_actor=actor,
                )
                fetch_limit = _clamp_int(arguments.get("fetch_limit"), default=2, minimum=0, maximum=3)
                fetched: list[dict[str, Any]] = []
                seen_targets: set[str] = set()
                raw_hits = search_result.get("results") if isinstance(search_result.get("results"), list) and fetch_limit > 0 else []
                for hit in raw_hits:
                    if not isinstance(hit, dict):
                        continue
                    target_id = _notion_search_hit_target_id(hit)
                    if not target_id or target_id in seen_targets:
                        continue
                    seen_targets.add(target_id)
                    try:
                        fetch_result = notion_fetch(
                            conn,
                            cfg,
                            agent_id=str(token_row["agent_id"]),
                            target_id=target_id,
                            requested_by_actor=actor,
                        )
                        fetched.append(
                            {
                                "search_hit": {
                                    "page_id": str(hit.get("page_id") or ""),
                                    "page_url": str(hit.get("page_url") or ""),
                                    "page_title": str(hit.get("page_title") or ""),
                                    "section_heading": str(hit.get("section_heading") or ""),
                                    "score": hit.get("score"),
                                    "snippet": str(hit.get("snippet") or ""),
                                },
                                "fetch": _compact_notion_fetch_result(fetch_result, body_char_limit=body_char_limit),
                            }
                        )
                    except Exception as exc:  # noqa: BLE001
                        fetched.append(
                            {
                                "search_hit": _compact_notion_search_hit(hit),
                                "fetch_error": str(exc),
                            }
                        )
                    if len(fetched) >= fetch_limit:
                        break
                return {
                    "ok": True,
                    "query": search_result.get("query"),
                    "collection": search_result.get("collection"),
                    "search": _compact_notion_search_result(search_result),
                    "fetched": fetched,
                    "fetch_limit": fetch_limit,
                    "body_char_limit": body_char_limit,
                }

            if tool_name == "notion.fetch":
                token_row = validate_token(conn, str(arguments.get("token") or ""))
                return notion_fetch(
                    conn,
                    cfg,
                    agent_id=str(token_row["agent_id"]),
                    target_id=str(arguments.get("target_id") or ""),
                    requested_by_actor=str(arguments.get("actor") or token_row["agent_id"]),
                )

            if tool_name == "notion.query":
                token_row = validate_token(conn, str(arguments.get("token") or ""))
                query = _dict_arg(arguments, "query")
                return notion_query(
                    conn,
                    cfg,
                    agent_id=str(token_row["agent_id"]),
                    target_id=str(arguments.get("target_id") or ""),
                    query=query,
                    limit=_clamp_int(arguments.get("limit"), default=25, minimum=1, maximum=100),
                    requested_by_actor=str(arguments.get("actor") or token_row["agent_id"]),
                )

            if tool_name == "ssot.read":
                token_row = validate_token(conn, str(arguments.get("token") or ""))
                query = _dict_arg(arguments, "query")
                return read_ssot(
                    conn,
                    cfg,
                    agent_id=str(token_row["agent_id"]),
                    target_id=str(arguments.get("target_id") or ""),
                    query=query,
                    include_markdown=_bool_arg(arguments, "include_markdown"),
                    requested_by_actor=str(arguments.get("actor") or token_row["agent_id"]),
                )

            if tool_name == "ssot.pending":
                token_row = validate_token(conn, str(arguments.get("token") or ""))
                status = str(arguments.get("status") or "pending").strip().lower()
                if status not in {"pending", "applied", "denied", "expired"}:
                    raise ValueError("status must be one of pending, applied, denied, expired")
                limit = _clamp_int(arguments.get("limit"), default=25, minimum=1, maximum=100)
                agent_id = str(token_row["agent_id"])
                return {
                    "agent_id": agent_id,
                    "status": status,
                    "count": count_ssot_pending_writes(
                        conn,
                        status=status,
                        agent_id=agent_id,
                    ),
                    "pending_writes": list_agent_ssot_pending_writes(
                        conn,
                        agent_id=agent_id,
                        status=status,
                        limit=limit,
                    ),
                }

            if tool_name == "ssot.status":
                token_row = validate_token(conn, str(arguments.get("token") or ""))
                pending_id = str(arguments.get("pending_id") or "").strip()
                if not pending_id:
                    raise ValueError("pending_id required")
                agent_id = str(token_row["agent_id"])
                row = get_ssot_pending_write(conn, pending_id)
                if row is None:
                    return {
                        "agent_id": agent_id,
                        "pending_id": pending_id,
                        "found": False,
                        "final_state": "unknown",
                    }
                if str(row.get("agent_id") or "") != agent_id:
                    raise PermissionError("pending SSOT write is outside this agent's scope")
                return {
                    "agent_id": agent_id,
                    "pending_id": pending_id,
                    "found": True,
                    "final_state": _ssot_final_state(row),
                    "pending_write": row,
                }

            if tool_name == "ssot.approve":
                token_row = validate_token(conn, str(arguments.get("token") or ""))
                pending_id = str(arguments.get("pending_id") or "").strip()
                if not pending_id:
                    raise ValueError("pending_id required")
                agent_id = str(token_row["agent_id"])
                row = get_ssot_pending_write(conn, pending_id)
                if row is None:
                    raise ValueError(f"unknown pending SSOT write: {pending_id}")
                if str(row.get("agent_id") or "") != agent_id:
                    raise PermissionError("pending SSOT write is outside this agent's scope")
                return approve_ssot_pending_write(
                    conn,
                    cfg,
                    pending_id=pending_id,
                    surface="user-agent",
                    actor=str(arguments.get("actor") or agent_id),
                )

            if tool_name == "ssot.deny":
                token_row = validate_token(conn, str(arguments.get("token") or ""))
                pending_id = str(arguments.get("pending_id") or "").strip()
                if not pending_id:
                    raise ValueError("pending_id required")
                agent_id = str(token_row["agent_id"])
                row = get_ssot_pending_write(conn, pending_id)
                if row is None:
                    raise ValueError(f"unknown pending SSOT write: {pending_id}")
                if str(row.get("agent_id") or "") != agent_id:
                    raise PermissionError("pending SSOT write is outside this agent's scope")
                return deny_ssot_pending_write(
                    conn,
                    cfg,
                    pending_id=pending_id,
                    surface="user-agent",
                    actor=str(arguments.get("actor") or agent_id),
                    reason=str(arguments.get("reason") or "denied by user"),
                )

            if tool_name == "ssot.preflight":
                token_row = validate_token(conn, str(arguments.get("token") or ""))
                agent_id = str(token_row["agent_id"])
                return preflight_ssot_write(
                    conn,
                    cfg,
                    agent_id=agent_id,
                    operation=str(arguments.get("operation") or "").strip().lower(),
                    target_id=str(arguments.get("target_id") or ""),
                    payload=_dict_arg(arguments, "payload", required=True),
                    requested_by_actor=str(arguments.get("actor") or agent_id),
                )

            if tool_name == "ssot.write":
                token_row = validate_token(conn, str(arguments.get("token") or ""))
                agent_id = str(token_row["agent_id"])
                actor = str(arguments.get("actor") or token_row["agent_id"])
                result = _normalize_ssot_write_result(
                    enqueue_ssot_write(
                        conn,
                        cfg,
                        agent_id=agent_id,
                        operation=str(arguments.get("operation") or "").strip().lower(),
                        target_id=str(arguments.get("target_id") or ""),
                        payload=_dict_arg(arguments, "payload", required=True),
                        requested_by_actor=actor,
                    )
                )
                if _bool_arg(arguments, "read_after") and result.get("final_state") == "applied":
                    target_id = str(result.get("target_id") or "").strip()
                    if target_id:
                        try:
                            result["read_after"] = read_ssot(
                                conn,
                                cfg,
                                agent_id=agent_id,
                                target_id=target_id,
                                query={},
                                include_markdown=_bool_arg(arguments, "read_after_include_markdown"),
                                requested_by_actor=actor,
                            )
                        except Exception as exc:  # noqa: BLE001
                            result["read_after_error"] = str(exc)
                return result

            raise ValueError(f"unknown tool: {tool_name}")


def main() -> None:
    args = parse_args()
    cfg = Config.from_env()
    host = args.host or cfg.public_mcp_host
    port = args.port or cfg.public_mcp_port
    server = AlmanacServer((host, port), Handler, cfg)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
