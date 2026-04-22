#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from almanac_control import (
    Config,
    connect_db,
    get_setting,
    is_loopback_ip,
    note_refresh_job,
    notion_verify_signature,
    parse_utc_iso,
    store_notion_event,
    upsert_setting,
    utc_after_seconds_iso,
    utc_now,
    utc_now_iso,
)

NOTION_WEBHOOK_VERIFICATION_TOKEN_KEY = "notion_webhook_verification_token"
NOTION_WEBHOOK_VERIFICATION_TOKEN_ARMED_UNTIL_KEY = "notion_webhook_verification_token_armed_until"
NOTION_WEBHOOK_VERIFICATION_TOKEN_INSTALLED_AT_KEY = "notion_webhook_verification_token_installed_at"
NOTION_WEBHOOK_VERIFICATION_TOKEN_LAST_ARMED_AT_KEY = "notion_webhook_verification_token_last_armed_at"
NOTION_WEBHOOK_VERIFICATION_TOKEN_LAST_ARMED_BY_KEY = "notion_webhook_verification_token_last_armed_by"
NOTION_WEBHOOK_VERIFICATION_TOKEN_LAST_RESET_AT_KEY = "notion_webhook_verification_token_last_reset_at"
NOTION_WEBHOOK_VERIFICATION_TOKEN_LAST_RESET_BY_KEY = "notion_webhook_verification_token_last_reset_by"


def backend_client_allowed(remote_ip: str) -> bool:
    return is_loopback_ip(str(remote_ip or "").strip())


def _verification_token_install_armed(conn) -> tuple[bool, str]:
    armed_until = str(get_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_ARMED_UNTIL_KEY, "") or "").strip()
    if not armed_until:
        return False, ""
    parsed = parse_utc_iso(armed_until)
    if parsed is None or parsed < utc_now():
        upsert_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_ARMED_UNTIL_KEY, "")
        return False, ""
    return True, armed_until


def arm_verification_token_install(conn, *, ttl_seconds: int, actor: str) -> dict:
    normalized_ttl = max(60, int(ttl_seconds or 0))
    actor_label = str(actor or "").strip() or "operator"
    armed_until = utc_after_seconds_iso(normalized_ttl)
    upsert_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_ARMED_UNTIL_KEY, armed_until)
    upsert_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_LAST_ARMED_AT_KEY, utc_now_iso())
    upsert_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_LAST_ARMED_BY_KEY, actor_label)
    note_refresh_job(
        conn,
        job_name="notion-webhook-token",
        job_kind="notion-webhook-token",
        target_id="notion-webhook",
        schedule="operator-armed handshake window",
        status="warn",
        note=f"verification token install armed by {actor_label} until {armed_until}",
    )
    return {
        "ok": True,
        "armed": True,
        "armed_until": armed_until,
        "actor": actor_label,
        "ttl_seconds": normalized_ttl,
    }


def reset_verification_token(conn, *, actor: str, rearm_ttl_seconds: int = 0) -> dict:
    actor_label = str(actor or "").strip() or "operator"
    previously_set = bool(str(get_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_KEY, "") or "").strip())
    upsert_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_KEY, "")
    upsert_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_INSTALLED_AT_KEY, "")
    upsert_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_LAST_RESET_AT_KEY, utc_now_iso())
    upsert_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_LAST_RESET_BY_KEY, actor_label)
    if int(rearm_ttl_seconds or 0) > 0:
        armed_payload = arm_verification_token_install(conn, ttl_seconds=int(rearm_ttl_seconds), actor=actor_label)
    else:
        upsert_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_ARMED_UNTIL_KEY, "")
        armed_payload = {"armed": False, "armed_until": ""}
    note_refresh_job(
        conn,
        job_name="notion-webhook-token",
        job_kind="notion-webhook-token",
        target_id="notion-webhook",
        schedule="operator reset / arm",
        status="warn",
        note=(
            f"verification token cleared by {actor_label}; "
            + (
                f"install window armed until {armed_payload['armed_until']}"
                if armed_payload.get("armed")
                else "install window not armed"
            )
        ),
    )
    return {
        "ok": True,
        "previously_set": previously_set,
        "armed": bool(armed_payload.get("armed")),
        "armed_until": str(armed_payload.get("armed_until") or ""),
        "actor": actor_label,
        "note": (
            "stored verification token cleared; next handshake POST from Notion can install a fresh secret"
            if armed_payload.get("armed")
            else "stored verification token cleared"
        ),
    }


def get_verification_token_state(conn) -> dict:
    configured = bool(str(get_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_KEY, "") or "").strip())
    armed, armed_until = _verification_token_install_armed(conn)
    return {
        "configured": configured,
        "installed_at": str(get_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_INSTALLED_AT_KEY, "") or "").strip(),
        "armed": armed,
        "armed_until": armed_until,
        "last_armed_at": str(get_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_LAST_ARMED_AT_KEY, "") or "").strip(),
        "last_armed_by": str(get_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_LAST_ARMED_BY_KEY, "") or "").strip(),
        "last_reset_at": str(get_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_LAST_RESET_AT_KEY, "") or "").strip(),
        "last_reset_by": str(get_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_LAST_RESET_BY_KEY, "") or "").strip(),
    }


def handle_verification_token_post(conn, candidate_token: str) -> tuple[int, dict]:
    """Policy for storing a Notion webhook verification token.

    Notion's handshake POSTs the verification token exactly once during
    integration setup. Refuse subsequent overwrites so that an unprivileged
    process on a multi-user host cannot replace the secret and forge signed
    events. Operators must explicitly arm the install window before the
    first or next handshake is allowed on a shared host.
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
    armed, armed_until = _verification_token_install_armed(conn)
    if not armed:
        return (
            HTTPStatus.PRECONDITION_FAILED,
            {
                "error": (
                    "verification token install is not armed; an operator must run "
                    "`almanac-ctl notion webhook-arm-install` before the Notion handshake arrives"
                )
            },
        )
    upsert_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_KEY, candidate)
    upsert_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_INSTALLED_AT_KEY, utc_now_iso())
    upsert_setting(conn, NOTION_WEBHOOK_VERIFICATION_TOKEN_ARMED_UNTIL_KEY, "")
    note_refresh_job(
        conn,
        job_name="notion-webhook-token",
        job_kind="notion-webhook-token",
        target_id="notion-webhook",
        schedule="webhook handshake",
        status="ok",
        note=f"verification token installed via webhook handshake; install window previously armed until {armed_until}",
    )
    # Notion expects a 200 response once the verification token POST is
    # received successfully. Returning 202 causes the Notion UI to treat the
    # delivery as failed even though we stored the token.
    return HTTPStatus.OK, {"status": "verification_token_stored"}


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

        # Notion expects webhook deliveries to acknowledge with HTTP 200.
        self._send_json({"status": "accepted", "event_id": event_id}, status=HTTPStatus.OK)

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
