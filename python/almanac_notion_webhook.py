#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from almanac_control import Config, connect_db, get_setting, is_loopback_ip, notion_verify_signature, store_notion_event, upsert_setting

NOTION_WEBHOOK_VERIFICATION_TOKEN_KEY = "notion_webhook_verification_token"


def backend_client_allowed(remote_ip: str) -> bool:
    return is_loopback_ip(str(remote_ip or "").strip())


def handle_verification_token_post(conn, candidate_token: str) -> tuple[int, dict]:
    """Policy for storing a Notion webhook verification token.

    Notion's handshake POSTs the verification token exactly once during
    integration setup. Refuse subsequent overwrites so that an unprivileged
    process on a multi-user host cannot replace the secret and forge signed
    events. Operators rotate via `almanac-ctl notion webhook-reset-token`,
    which clears the stored token so the next handshake POST can store a
    fresh one.
    """
    candidate = str(candidate_token or "").strip()
    if not candidate:
        return HTTPStatus.BAD_REQUEST, {"error": "verification_token is required"}
    stored = str(get_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_KEY, "") or "").strip()
    if stored:
        return (
            HTTPStatus.CONFLICT,
            {
                "error": (
                    "verification token already configured; rotate via "
                    "`almanac-ctl notion webhook-reset-token` before re-handshaking"
                )
            },
        )
    upsert_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_KEY, candidate)
    return HTTPStatus.ACCEPTED, {"status": "verification_token_stored"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Almanac Notion webhook receiver.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    return parser.parse_args()


class Server(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler_cls: type[BaseHTTPRequestHandler], cfg: Config):
        super().__init__(server_address, handler_cls)
        self.cfg = cfg


class Handler(BaseHTTPRequestHandler):
    server: Server

    def _require_loopback_transport(self) -> bool:
        if backend_client_allowed(str(self.client_address[0] or "").strip()):
            return True
        self._send_json({"error": "backend only accepts loopback connections"}, status=HTTPStatus.FORBIDDEN)
        return False

    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        if not self._require_loopback_transport():
            return
        if self.path != "/health":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._send_json({"ok": True, "service": "almanac-notion-webhook"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._require_loopback_transport():
            return
        if self.path != "/notion/webhook":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw_body = self.rfile.read(length)
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send_json({"error": "invalid json"}, status=HTTPStatus.BAD_REQUEST)
            return

        with connect_db(self.server.cfg) as conn:
            verification_token = str(payload.get("verification_token") or "")
            signature = self.headers.get("X-Notion-Signature", "")
            if verification_token and not signature:
                status, body = handle_verification_token_post(conn, verification_token)
                self._send_json(body, status=status)
                return

            stored_token = get_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_KEY, "")
            if not stored_token:
                self._send_json({"error": "verification token is not configured"}, status=HTTPStatus.PRECONDITION_FAILED)
                return
            if not notion_verify_signature(raw_body, signature, stored_token):
                self._send_json({"error": "signature verification failed"}, status=HTTPStatus.FORBIDDEN)
                return

            event_id = str(payload.get("id") or payload.get("event_id") or payload.get("entity", {}).get("id") or "")
            event_type = str(payload.get("type") or "unknown")
            if not event_id:
                self._send_json({"error": "missing event id"}, status=HTTPStatus.BAD_REQUEST)
                return
            store_notion_event(conn, event_id=event_id, event_type=event_type, payload=payload)

        self._send_json({"status": "accepted", "event_id": event_id}, status=HTTPStatus.ACCEPTED)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def main() -> None:
    args = parse_args()
    cfg = Config.from_env()
    host = args.host or cfg.notion_webhook_host
    port = args.port or cfg.notion_webhook_port
    server = Server((host, port), Handler, cfg)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
