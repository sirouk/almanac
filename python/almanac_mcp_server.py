#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from almanac_control import (
    Config,
    RateLimitError,
    approve_request,
    bootstrap_status,
    build_managed_memory_payload,
    connect_db,
    consume_agent_notifications,
    consume_curator_brief_fanout,
    deny_request,
    enqueue_ssot_write,
    is_loopback_ip,
    is_tailnet_ip,
    list_notifications,
    list_requests,
    list_vault_warnings,
    note_refresh_job,
    queue_notification,
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
    "agents.managed-memory": "Fetch the caller's canonical managed-memory payload.",
    "agents.consume-notifications": "Atomically read+ack notifications targeted at the caller's agent.",
    "curator.fanout": "Run the curator brief-fanout consumer. Requires operator-class token.",
    "notifications.list": "List queued notifications. Requires operator-class token.",
    "ssot.write": "Queue a Notion SSOT write (insert/update). Archive/delete are rejected.",
}


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
                    "inputSchema": {"type": "object"},
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
                    auto_provision=bool(arguments.get("auto_provision")),
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
                result = set_subscription_from_token(
                    conn,
                    raw_token=str(arguments.get("token") or ""),
                    vault_name=str(arguments.get("vault_name") or ""),
                    subscribed=bool(arguments.get("subscribed")),
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
                limit = int(arguments.get("limit") or 100)
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
                    undelivered_only=bool(arguments.get("undelivered_only")),
                )
                return {"notifications": notifications}

            if tool_name == "ssot.write":
                token_row = validate_token(conn, str(arguments.get("token") or ""))
                return enqueue_ssot_write(
                    conn,
                    cfg,
                    agent_id=str(token_row["agent_id"]),
                    operation=str(arguments.get("operation") or "").strip().lower(),
                    target_id=str(arguments.get("target_id") or ""),
                    payload=arguments.get("payload") or {},
                    requested_by_actor=str(arguments.get("actor") or token_row["agent_id"]),
                )

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
