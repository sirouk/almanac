#!/usr/bin/env python3
"""ArcLink Hosted API — production HTTP boundary over existing contracts.

This module wraps the existing ArcLink helper layer into a hosted WSGI
application with proper authentication middleware, request IDs, structured
logging, cookie/header session transport, CORS, and deployment config.

The product surface prototype (arclink_product_surface.py) remains a local
no-secret smoke tool. This module is the boundary intended for hosted use.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import sqlite3
import time
from typing import Any, Mapping
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

from arclink_adapters import StripeWebhookError, resolve_stripe_client
from arclink_control import Config, connect_db
from arclink_entitlements import process_stripe_webhook, StripeWebhookResult
from arclink_api_auth import (
    GENERIC_ARCLINK_API_ERROR,
    ArcLinkApiAuthError,
    ArcLinkRateLimitError,
    _header as _api_header,
    answer_public_onboarding_api,
    authenticate_arclink_admin_session,
    create_arclink_admin_login_session_api,
    create_arclink_user_login_session_api,
    create_user_portal_link_api,
    extract_arclink_csrf_token,
    extract_arclink_session_credentials,
    open_public_onboarding_checkout_api,
    queue_admin_action_api,
    read_admin_dashboard_api,
    read_admin_audit_api,
    read_admin_dns_drift_api,
    read_admin_events_api,
    read_admin_provisioning_jobs_api,
    read_admin_queued_actions_api,
    read_admin_reconciliation_api,
    read_admin_service_health_api,
    read_provider_state_api,
    read_user_billing_api,
    read_user_dashboard_api,
    read_user_provisioning_status_api,
    require_arclink_csrf,
    revoke_arclink_session,
    start_public_onboarding_api,
)
from arclink_dashboard import build_operator_snapshot, build_scale_operations_snapshot
from arclink_discord import (
    ArcLinkDiscordError,
    DiscordConfig,
    handle_discord_webhook_request,
)
from arclink_product import base_domain as default_base_domain
from arclink_telegram import TelegramConfig, handle_telegram_update

logger = logging.getLogger("arclink.hosted_api")

# --- Configuration -----------------------------------------------------------

HOSTED_API_PREFIX = "/api/v1"
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CORS_ALLOWED_METHODS = "GET, POST, OPTIONS"
CORS_ALLOWED_HEADERS = (
    "Content-Type, Authorization, "
    "X-ArcLink-Session-Id, X-ArcLink-Session-Token, X-ArcLink-CSRF-Token, "
    "X-ArcLink-Request-Id"
)
CORS_MAX_AGE = "86400"
REQUEST_ID_HEADER = "x-arclink-request-id"


class HostedApiConfig:
    """Runtime configuration resolved from environment."""

    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        e = dict(env or os.environ)
        self.env: dict[str, str] = e
        self.base_domain: str = default_base_domain(e)
        self.cors_origin: str = str(e.get("ARCLINK_CORS_ORIGIN", "")).strip()
        self.cookie_domain: str = str(e.get("ARCLINK_COOKIE_DOMAIN", "")).strip()
        self.cookie_secure: bool = str(e.get("ARCLINK_COOKIE_SECURE", "1")).strip() != "0"
        self.stripe_webhook_secret: str = str(e.get("STRIPE_WEBHOOK_SECRET", "")).strip()
        self.log_level: str = str(e.get("ARCLINK_LOG_LEVEL", "INFO")).strip().upper()
        self.default_price_id: str = str(e.get("ARCLINK_DEFAULT_PRICE_ID", "price_arclink_starter")).strip()


# --- Request / Response helpers -----------------------------------------------


def _request_id(headers: Mapping[str, Any]) -> str:
    """Extract or generate a request ID."""
    candidate = _api_header(headers, REQUEST_ID_HEADER)[:64]
    return candidate if candidate else f"req_{secrets.token_hex(12)}"


def _json_body(body: str) -> dict[str, Any]:
    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _form_body(body: str) -> dict[str, str]:
    parsed = parse_qs(body)
    return {k: v[0] for k, v in parsed.items() if v}


def _json_response(
    status: int,
    payload: Mapping[str, Any],
    *,
    request_id: str = "",
    extra_headers: list[tuple[str, str]] | None = None,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    headers = [("Content-Type", "application/json")]
    if request_id:
        headers.append(("X-ArcLink-Request-Id", request_id))
    if extra_headers:
        headers.extend(extra_headers)
    return status, dict(payload), headers


def _cookie_flags(config: HostedApiConfig, *, expire: bool = False) -> str:
    flags = "; Path=/; HttpOnly; SameSite=Lax"
    if expire:
        flags += "; Max-Age=0"
    if config.cookie_secure:
        flags += "; Secure"
    if config.cookie_domain:
        flags += f"; Domain={config.cookie_domain}"
    return flags


def _session_cookies(
    session: Mapping[str, Any],
    *,
    kind: str,
    config: HostedApiConfig,
) -> list[tuple[str, str]]:
    """Build Set-Cookie headers for session credentials."""
    cookies: list[tuple[str, str]] = []
    prefix = f"arclink_{kind}"
    flags = _cookie_flags(config)
    for field, suffix in (
        ("session_id", "session_id"),
        ("session_token", "session_token"),
        ("csrf_token", "csrf"),
    ):
        value = str(session.get(field) or "")
        if value:
            cookies.append(("Set-Cookie", f"{prefix}_{suffix}={value}{flags}"))
    return cookies


def _clear_session_cookies(kind: str, *, config: HostedApiConfig) -> list[tuple[str, str]]:
    """Build Set-Cookie headers that expire session cookies."""
    prefix = f"arclink_{kind}"
    flags = _cookie_flags(config, expire=True)
    return [("Set-Cookie", f"{prefix}_{suffix}={flags}") for suffix in ("session_id", "session_token", "csrf")]


def _cors_headers(config: HostedApiConfig) -> list[tuple[str, str]]:
    if not config.cors_origin:
        return []
    return [
        ("Access-Control-Allow-Origin", config.cors_origin),
        ("Access-Control-Allow-Methods", CORS_ALLOWED_METHODS),
        ("Access-Control-Allow-Headers", CORS_ALLOWED_HEADERS),
        ("Access-Control-Allow-Credentials", "true"),
        ("Access-Control-Max-Age", CORS_MAX_AGE),
    ]


# --- Route handlers -----------------------------------------------------------


def _handle_public_onboarding_start(
    conn: sqlite3.Connection,
    body: dict[str, Any],
    request_id: str,
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    result = start_public_onboarding_api(
        conn,
        channel=str(body.get("channel") or "web"),
        channel_identity=str(body.get("channel_identity") or body.get("email") or ""),
        email_hint=str(body.get("email") or ""),
        display_name_hint=str(body.get("display_name") or ""),
        selected_plan_id=str(body.get("plan_id") or "starter"),
        selected_model_id=str(body.get("model_id") or ""),
        metadata=body.get("metadata"),
    )
    return _json_response(result.status, result.payload, request_id=request_id)


def _handle_public_onboarding_answer(
    conn: sqlite3.Connection,
    body: dict[str, Any],
    request_id: str,
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    result = answer_public_onboarding_api(
        conn,
        session_id=str(body.get("session_id") or ""),
        question_key=str(body.get("question_key") or ""),
        answer_summary=str(body.get("answer_summary") or ""),
        email_hint=str(body.get("email") or ""),
        display_name_hint=str(body.get("display_name") or ""),
        selected_plan_id=str(body.get("plan_id") or ""),
        selected_model_id=str(body.get("model_id") or ""),
    )
    return _json_response(result.status, result.payload, request_id=request_id)


def _handle_public_onboarding_checkout(
    conn: sqlite3.Connection,
    body: dict[str, Any],
    request_id: str,
    config: HostedApiConfig,
    stripe_client: Any,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    result = open_public_onboarding_checkout_api(
        conn,
        session_id=str(body.get("session_id") or ""),
        stripe_client=stripe_client,
        price_id=str(body.get("price_id") or config.default_price_id),
        success_url=str(body.get("success_url") or ""),
        cancel_url=str(body.get("cancel_url") or ""),
        base_domain=config.base_domain,
    )
    return _json_response(result.status, result.payload, request_id=request_id)


def _handle_stripe_webhook(
    conn: sqlite3.Connection,
    raw_body: str,
    headers: Mapping[str, Any],
    request_id: str,
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    if not config.stripe_webhook_secret:
        return _json_response(200, {"status": "skipped", "reason": "no_webhook_secret"}, request_id=request_id)
    sig = _api_header(headers, "stripe-signature")
    result: StripeWebhookResult = process_stripe_webhook(
        conn, payload=raw_body, signature=sig, secret=config.stripe_webhook_secret,
    )
    logger.info(
        "stripe_webhook event_type=%s event_id=%s user_id=%s entitlement=%s replayed=%s request_id=%s",
        result.event_type, result.event_id, result.user_id, result.entitlement_state, result.replayed, request_id,
    )
    return _json_response(200, {
        "status": "processed",
        "event_id": result.event_id,
        "event_type": result.event_type,
        "replayed": result.replayed,
    }, request_id=request_id)


def _handle_admin_login(
    conn: sqlite3.Connection,
    body: dict[str, Any],
    request_id: str,
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    result = create_arclink_admin_login_session_api(
        conn,
        email=str(body.get("email") or ""),
        login_subject=str(body.get("login_subject") or body.get("email") or ""),
        mfa_verified=bool(body.get("mfa_verified")),
        metadata=body.get("metadata"),
    )
    cookies = _session_cookies(result.payload.get("session", {}), kind="admin", config=config)
    return _json_response(result.status, result.payload, request_id=request_id, extra_headers=cookies)


def _handle_user_login(
    conn: sqlite3.Connection,
    body: dict[str, Any],
    request_id: str,
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    result = create_arclink_user_login_session_api(
        conn,
        email=str(body.get("email") or ""),
        login_subject=str(body.get("login_subject") or body.get("email") or ""),
        metadata=body.get("metadata"),
    )
    cookies = _session_cookies(result.payload.get("session", {}), kind="user", config=config)
    return _json_response(result.status, result.payload, request_id=request_id, extra_headers=cookies)


def _handle_logout(
    conn: sqlite3.Connection,
    headers: Mapping[str, Any],
    request_id: str,
    config: HostedApiConfig,
    kind: str,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    creds = extract_arclink_session_credentials(headers, session_kind=kind)
    csrf = extract_arclink_csrf_token(headers, session_kind=kind)
    require_arclink_csrf(conn, session_id=creds["session_id"], csrf_token=csrf, session_kind=kind)
    result = revoke_arclink_session(
        conn,
        session_id=creds["session_id"],
        session_kind=kind,
        actor_id=creds["session_id"],
        reason=f"{kind}_logout",
    )
    extra = _clear_session_cookies(kind, config=config)
    return _json_response(200, {"session": result}, request_id=request_id, extra_headers=extra)


def _handle_user_dashboard(
    conn: sqlite3.Connection,
    headers: Mapping[str, Any],
    query: dict[str, str],
    request_id: str,
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    creds = extract_arclink_session_credentials(headers, session_kind="user")
    result = read_user_dashboard_api(
        conn,
        session_id=creds["session_id"],
        session_token=creds["session_token"],
        user_id=query.get("user_id", ""),
    )
    return _json_response(result.status, result.payload, request_id=request_id)


def _handle_admin_dashboard(
    conn: sqlite3.Connection,
    headers: Mapping[str, Any],
    query: dict[str, str],
    request_id: str,
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    creds = extract_arclink_session_credentials(headers, session_kind="admin")
    result = read_admin_dashboard_api(
        conn,
        session_id=creds["session_id"],
        session_token=creds["session_token"],
        **{k: v for k, v in query.items() if k in ("channel", "status", "deployment_id", "user_id", "since")},
    )
    return _json_response(result.status, result.payload, request_id=request_id)


def _handle_admin_action(
    conn: sqlite3.Connection,
    headers: Mapping[str, Any],
    body: dict[str, Any],
    request_id: str,
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    creds = extract_arclink_session_credentials(headers, session_kind="admin")
    csrf = extract_arclink_csrf_token(headers, session_kind="admin")
    result = queue_admin_action_api(
        conn,
        session_id=creds["session_id"],
        session_token=creds["session_token"],
        csrf_token=csrf,
        action_type=str(body.get("action_type") or ""),
        target_kind=str(body.get("target_kind") or ""),
        target_id=str(body.get("target_id") or ""),
        reason=str(body.get("reason") or ""),
        idempotency_key=str(body.get("idempotency_key") or ""),
        metadata=body.get("metadata"),
    )
    return _json_response(result.status, result.payload, request_id=request_id)


def _handle_user_billing(
    conn: sqlite3.Connection,
    headers: Mapping[str, Any],
    request_id: str,
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    creds = extract_arclink_session_credentials(headers, session_kind="user")
    result = read_user_billing_api(conn, session_id=creds["session_id"], session_token=creds["session_token"])
    return _json_response(result.status, result.payload, request_id=request_id)


def _handle_user_portal_link(
    conn: sqlite3.Connection,
    headers: Mapping[str, Any],
    body: dict[str, Any],
    request_id: str,
    config: HostedApiConfig,
    stripe_client: Any,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    creds = extract_arclink_session_credentials(headers, session_kind="user")
    csrf = extract_arclink_csrf_token(headers, session_kind="user")
    require_arclink_csrf(conn, session_id=creds["session_id"], csrf_token=csrf, session_kind="user")
    result = create_user_portal_link_api(
        conn, session_id=creds["session_id"], session_token=creds["session_token"],
        stripe_client=stripe_client,
        return_url=str(body.get("return_url") or ""),
    )
    return _json_response(result.status, result.payload, request_id=request_id)


def _handle_user_provisioning_status(
    conn: sqlite3.Connection,
    headers: Mapping[str, Any],
    query: dict[str, str],
    request_id: str,
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    creds = extract_arclink_session_credentials(headers, session_kind="user")
    result = read_user_provisioning_status_api(
        conn, session_id=creds["session_id"], session_token=creds["session_token"],
        deployment_id=query.get("deployment_id", ""),
    )
    return _json_response(result.status, result.payload, request_id=request_id)


_ADMIN_READ_HANDLERS: dict[str, tuple[Any, tuple[str, ...]]] = {
    "admin_service_health": (read_admin_service_health_api, ("deployment_id", "status", "since")),
    "admin_provisioning_jobs": (read_admin_provisioning_jobs_api, ("deployment_id", "status", "since")),
    "admin_audit": (read_admin_audit_api, ("deployment_id", "since")),
    "admin_events": (read_admin_events_api, ("deployment_id", "since")),
    "admin_queued_actions": (read_admin_queued_actions_api, ("deployment_id", "status", "since")),
    "admin_dns_drift": (read_admin_dns_drift_api, ("deployment_id", "since")),
    "admin_reconciliation": (read_admin_reconciliation_api, ()),
}


def _handle_admin_read(
    conn: sqlite3.Connection,
    headers: Mapping[str, Any],
    query: dict[str, str],
    request_id: str,
    config: HostedApiConfig,
    route_key: str,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    api_fn, allowed_keys = _ADMIN_READ_HANDLERS[route_key]
    creds = extract_arclink_session_credentials(headers, session_kind="admin")
    result = api_fn(
        conn, session_id=creds["session_id"], session_token=creds["session_token"],
        **{k: v for k, v in query.items() if k in allowed_keys},
    )
    return _json_response(result.status, result.payload, request_id=request_id)


def _handle_session_revoke(
    conn: sqlite3.Connection,
    headers: Mapping[str, Any],
    body: dict[str, Any],
    request_id: str,
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    session_kind = str(body.get("session_kind") or "").strip().lower()
    creds = extract_arclink_session_credentials(headers, session_kind="admin")
    authenticate_arclink_admin_session(conn, session_id=creds["session_id"], session_token=creds["session_token"])
    csrf = extract_arclink_csrf_token(headers, session_kind="admin")
    require_arclink_csrf(conn, session_id=creds["session_id"], csrf_token=csrf, session_kind="admin")
    result = revoke_arclink_session(
        conn,
        session_id=str(body.get("target_session_id") or ""),
        session_kind=session_kind,
        actor_id=creds["session_id"],
        reason=str(body.get("reason") or ""),
    )
    extra = _clear_session_cookies(session_kind, config=config) if str(body.get("target_session_id") or "") == creds["session_id"] else []
    return _json_response(200, {"session": result}, request_id=request_id, extra_headers=extra)


def _handle_provider_state(
    conn: sqlite3.Connection,
    headers: Mapping[str, Any],
    request_id: str,
    config: HostedApiConfig,
    session_kind: str,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    creds = extract_arclink_session_credentials(headers, session_kind=session_kind)
    result = read_provider_state_api(
        conn,
        session_id=creds["session_id"],
        session_token=creds["session_token"],
        session_kind=session_kind,
    )
    return _json_response(result.status, result.payload, request_id=request_id)



def _handle_admin_operator_snapshot(
    conn: sqlite3.Connection,
    headers: Mapping[str, Any],
    request_id: str,
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    creds = extract_arclink_session_credentials(headers, session_kind="admin")
    authenticate_arclink_admin_session(conn, session_id=creds["session_id"], session_token=creds["session_token"])
    snapshot = build_operator_snapshot(env=config.env, skip_ports=True)
    return _json_response(200, snapshot, request_id=request_id)


def _handle_admin_scale_operations(
    conn: sqlite3.Connection,
    headers: Mapping[str, Any],
    request_id: str,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    creds = extract_arclink_session_credentials(headers, session_kind="admin")
    authenticate_arclink_admin_session(conn, session_id=creds["session_id"], session_token=creds["session_token"])
    snapshot = build_scale_operations_snapshot(conn)
    return _json_response(200, snapshot, request_id=request_id)


def _handle_health(
    conn: sqlite3.Connection,
    request_id: str,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    """Simple liveness check — verifies DB is reachable."""
    try:
        conn.execute("SELECT 1").fetchone()
        db_ok = True
    except Exception:
        db_ok = False
    status = 200 if db_ok else 503
    return _json_response(status, {"status": "ok" if db_ok else "degraded", "db": db_ok}, request_id=request_id)


def _handle_telegram_webhook(
    conn: sqlite3.Connection,
    body: dict[str, Any],
    request_id: str,
    config: HostedApiConfig,
    stripe_client: Any,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    """Handle an incoming Telegram Bot API update (webhook mode)."""
    result = handle_telegram_update(
        conn, body,
        stripe_client=stripe_client,
        price_id=config.default_price_id,
        base_domain=config.base_domain,
    )
    if result is None:
        return _json_response(200, {"ok": True, "action": "ignored"}, request_id=request_id)
    return _json_response(200, {"ok": True, "action": result.get("action", "reply")}, request_id=request_id)


def _handle_discord_webhook(
    conn: sqlite3.Connection,
    raw_body: str,
    headers: Mapping[str, Any],
    request_id: str,
    config: HostedApiConfig,
    discord_config: DiscordConfig | None,
    stripe_client: Any,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    """Handle an incoming Discord interaction webhook."""
    dc = discord_config or DiscordConfig.from_env()
    if not dc.public_key:
        return _json_response(500, {"error": "discord_not_configured"}, request_id=request_id)
    sig = _api_header(headers, "x-signature-ed25519")
    ts = _api_header(headers, "x-signature-timestamp")
    try:
        response = handle_discord_webhook_request(
            conn,
            body=raw_body,
            signature=sig,
            timestamp=ts,
            config=dc,
            stripe_client=stripe_client,
            price_id=config.default_price_id,
            base_domain=config.base_domain,
        )
    except ArcLinkDiscordError as exc:
        return _json_response(401, {"error": str(exc)}, request_id=request_id)
    return _json_response(200, response, request_id=request_id)


# --- OpenAPI spec builder -----------------------------------------------------


def _openapi_json_body(properties: dict[str, Any], *, required: list[str] | None = None) -> dict:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return {"content": {"application/json": {"schema": schema}}}


def _qparam(name: str) -> dict:
    return {"name": name, "in": "query", "schema": {"type": "string"}}


_RESP_OK_UNAUTH = {"200": {"description": "OK"}, "401": {"description": "Unauthorized"}}
_RESP_CREATED_UNAUTH = {"201": {"description": "Session created with Set-Cookie"}, "401": {"description": "Unknown email"}, "429": {"description": "Rate limit exceeded"}}
_RESP_OK_INVALID = {"200": {"description": "OK"}, "400": {"description": "Invalid input"}}
_WEBHOOK_BODY = _openapi_json_body({})

_ROUTE_DESCRIPTIONS: dict[str, dict[str, Any]] = {
    "public_onboarding_start": {
        "summary": "Begin onboarding flow",
        "tags": ["onboarding"],
        "requestBody": _openapi_json_body({
            "channel": {"type": "string", "enum": ["web", "telegram", "discord"]},
            "channel_identity": {"type": "string"},
            "email": {"type": "string", "format": "email"},
            "display_name": {"type": "string"},
            "plan_id": {"type": "string"},
            "model_id": {"type": "string"},
            "metadata": {"type": "object"},
        }),
        "responses": {"201": {"description": "Onboarding session created"}, "400": {"description": "Invalid input"}},
    },
    "public_onboarding_answer": {
        "summary": "Answer onboarding question",
        "tags": ["onboarding"],
        "requestBody": _openapi_json_body({
            "session_id": {"type": "string"},
            "question_key": {"type": "string"},
            "answer_summary": {"type": "string"},
            "email": {"type": "string"},
            "display_name": {"type": "string"},
            "plan_id": {"type": "string"},
            "model_id": {"type": "string"},
        }),
        "responses": {"200": {"description": "Answer recorded"}, "400": {"description": "Invalid input"}},
    },
    "public_onboarding_checkout": {
        "summary": "Open Stripe checkout for onboarding session",
        "tags": ["onboarding"],
        "requestBody": _openapi_json_body({
            "session_id": {"type": "string"},
            "price_id": {"type": "string"},
            "success_url": {"type": "string", "format": "uri"},
            "cancel_url": {"type": "string", "format": "uri"},
        }),
        "responses": {"200": {"description": "Checkout URL returned"}, "400": {"description": "Invalid input"}},
    },
    "stripe_webhook": {
        "summary": "Stripe webhook receiver",
        "tags": ["webhooks"],
        "requestBody": _WEBHOOK_BODY,
        "responses": {"200": {"description": "Webhook processed"}, "400": {"description": "Invalid signature"}},
    },
    "telegram_webhook": {
        "summary": "Telegram Bot API webhook receiver",
        "tags": ["webhooks"],
        "requestBody": _WEBHOOK_BODY,
        "responses": {"200": {"description": "Update processed"}},
    },
    "discord_webhook": {
        "summary": "Discord interaction webhook receiver",
        "tags": ["webhooks"],
        "requestBody": _WEBHOOK_BODY,
        "responses": {"200": {"description": "Interaction handled"}, "401": {"description": "Invalid signature"}},
    },
    "admin_login": {
        "summary": "Admin login (creates session)",
        "tags": ["auth"],
        "requestBody": _openapi_json_body({
            "email": {"type": "string", "format": "email"},
            "login_subject": {"type": "string"},
            "mfa_verified": {"type": "boolean"},
            "metadata": {"type": "object"},
        }, required=["email"]),
        "responses": _RESP_CREATED_UNAUTH,
    },
    "user_login": {
        "summary": "User login (creates session)",
        "tags": ["auth"],
        "requestBody": _openapi_json_body({
            "email": {"type": "string", "format": "email"},
            "login_subject": {"type": "string"},
            "metadata": {"type": "object"},
        }, required=["email"]),
        "responses": _RESP_CREATED_UNAUTH,
    },
    "user_logout": {
        "summary": "User logout (revokes session)",
        "tags": ["auth"],
        "responses": {"200": {"description": "Session revoked"}, "401": {"description": "Missing session or CSRF"}},
    },
    "admin_logout": {
        "summary": "Admin logout (revokes session)",
        "tags": ["auth"],
        "responses": {"200": {"description": "Session revoked"}, "401": {"description": "Missing session or CSRF"}},
    },
    "user_dashboard": {
        "summary": "Read user dashboard",
        "tags": ["user"],
        "parameters": [_qparam("user_id")],
        "responses": {"200": {"description": "Dashboard data"}, "401": {"description": "Unauthorized"}},
    },
    "user_billing": {
        "summary": "Read user billing and entitlement state",
        "tags": ["user"],
        "responses": {"200": {"description": "Billing data"}, "401": {"description": "Unauthorized"}},
    },
    "user_portal_link": {
        "summary": "Generate Stripe billing portal link",
        "tags": ["user"],
        "requestBody": _openapi_json_body({"return_url": {"type": "string", "format": "uri"}}),
        "responses": {"200": {"description": "Portal URL returned"}, "401": {"description": "Unauthorized or missing CSRF"}},
    },
    "user_provisioning_status": {
        "summary": "Read user provisioning and deployment status",
        "tags": ["user"],
        "parameters": [_qparam("deployment_id")],
        "responses": {"200": {"description": "Provisioning data"}, "401": {"description": "Unauthorized"}},
    },
    "admin_dashboard": {
        "summary": "Read admin dashboard (all deployments)",
        "tags": ["admin"],
        "parameters": [_qparam("channel"), _qparam("status"), _qparam("deployment_id"), _qparam("user_id"), _qparam("since")],
        "responses": {"200": {"description": "Admin dashboard data"}, "401": {"description": "Unauthorized"}},
    },
    "admin_service_health": {
        "summary": "Read service health across deployments",
        "tags": ["admin"],
        "parameters": [_qparam("deployment_id"), _qparam("status"), _qparam("since")],
        "responses": {"200": {"description": "Service health data"}, "401": {"description": "Unauthorized"}},
    },
    "admin_provisioning_jobs": {
        "summary": "Read provisioning job queue",
        "tags": ["admin"],
        "parameters": [_qparam("deployment_id"), _qparam("status"), _qparam("since")],
        "responses": {"200": {"description": "Provisioning jobs"}, "401": {"description": "Unauthorized"}},
    },
    "admin_dns_drift": {
        "summary": "Read DNS drift reports",
        "tags": ["admin"],
        "parameters": [_qparam("deployment_id"), _qparam("since")],
        "responses": {"200": {"description": "DNS drift data"}, "401": {"description": "Unauthorized"}},
    },
    "admin_audit": {
        "summary": "Read audit trail",
        "tags": ["admin"],
        "parameters": [_qparam("deployment_id"), _qparam("since")],
        "responses": {"200": {"description": "Audit entries"}, "401": {"description": "Unauthorized"}},
    },
    "admin_events": {
        "summary": "Read structured events",
        "tags": ["admin"],
        "parameters": [_qparam("deployment_id"), _qparam("since")],
        "responses": {"200": {"description": "Event entries"}, "401": {"description": "Unauthorized"}},
    },
    "admin_queued_actions": {
        "summary": "Read queued admin actions",
        "tags": ["admin"],
        "parameters": [_qparam("deployment_id"), _qparam("status"), _qparam("since")],
        "responses": {"200": {"description": "Queued actions"}, "401": {"description": "Unauthorized"}},
    },
    "admin_action": {
        "summary": "Queue an admin action (mutation)",
        "tags": ["admin"],
        "requestBody": _openapi_json_body({
            "action_type": {"type": "string"},
            "target_kind": {"type": "string"},
            "target_id": {"type": "string"},
            "reason": {"type": "string"},
            "idempotency_key": {"type": "string"},
            "metadata": {"type": "object"},
        }, required=["action_type", "target_kind", "target_id"]),
        "responses": {"202": {"description": "Action queued"}, "401": {"description": "Unauthorized or missing CSRF"}},
    },
    "admin_reconciliation": {
        "summary": "Read Stripe-vs-local reconciliation report",
        "tags": ["admin"],
        "responses": {"200": {"description": "Reconciliation data"}, "401": {"description": "Unauthorized"}},
    },
    "admin_operator_snapshot": {
        "summary": "Read operator snapshot (host readiness, diagnostics, journey, evidence)",
        "tags": ["admin"],
        "responses": {"200": {"description": "Operator snapshot"}, "401": {"description": "Unauthorized"}},
    },
    "admin_scale_operations": {
        "summary": "Read scale operations snapshot (fleet, placements, action attempts, rollouts)",
        "tags": ["admin"],
        "responses": {"200": {"description": "Scale operations snapshot"}, "401": {"description": "Unauthorized"}},
    },
    "admin_provider_state": {
        "summary": "Read provider/model state (admin)",
        "tags": ["admin"],
        "responses": {"200": {"description": "Provider state"}, "401": {"description": "Unauthorized"}},
    },
    "session_revoke": {
        "summary": "Revoke a session (admin action)",
        "tags": ["admin"],
        "requestBody": _openapi_json_body({
            "target_session_id": {"type": "string"},
            "session_kind": {"type": "string", "enum": ["user", "admin"]},
            "reason": {"type": "string"},
        }, required=["target_session_id", "session_kind"]),
        "responses": {"200": {"description": "Session revoked"}, "401": {"description": "Unauthorized or missing CSRF"}},
    },
    "user_provider_state": {
        "summary": "Read provider/model state (user)",
        "tags": ["user"],
        "responses": {"200": {"description": "Provider state"}, "401": {"description": "Unauthorized"}},
    },
    "health": {
        "summary": "Liveness/readiness health check",
        "tags": ["health"],
        "responses": {"200": {"description": "Healthy"}, "503": {"description": "Degraded (DB unreachable)"}},
    },
    "openapi_spec": {
        "summary": "OpenAPI 3.1 specification",
        "tags": ["meta"],
        "responses": {"200": {"description": "OpenAPI JSON document"}},
    },
}


def build_arclink_openapi_spec() -> dict[str, Any]:
    """Build an OpenAPI 3.1 spec from the canonical _ROUTES table."""
    paths: dict[str, Any] = {}

    for (method, path_suffix), route_key in sorted(_ROUTES.items(), key=lambda x: x[0][1]):
        full_path = f"{HOSTED_API_PREFIX}{path_suffix}"
        op = _ROUTE_DESCRIPTIONS.get(route_key, {
            "summary": route_key.replace("_", " ").title(),
            "responses": {"200": {"description": "OK"}},
        })
        operation: dict[str, Any] = {
            "operationId": route_key,
            "summary": op.get("summary", route_key),
            "tags": op.get("tags", []),
            "responses": op.get("responses", {"200": {"description": "OK"}}),
        }
        if "requestBody" in op:
            operation["requestBody"] = op["requestBody"]
        if "parameters" in op:
            operation["parameters"] = op["parameters"]
        if route_key not in _PUBLIC_ROUTES:
            operation["security"] = [{"sessionAuth": []}]

        paths.setdefault(full_path, {})[method.lower()] = operation

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "ArcLink Hosted API",
            "version": "1.0.0",
            "description": "ArcLink self-serve AI deployment platform API.",
        },
        "servers": [{"url": "/", "description": "Relative to deployment host"}],
        "paths": paths,
        "components": {
            "securitySchemes": {
                "sessionAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-ArcLink-Session-Id",
                    "description": "Session-based auth via cookies or headers.",
                },
            },
        },
    }


# --- Router -------------------------------------------------------------------

# Route table: (method, path_suffix) -> handler_key
_ROUTES: dict[tuple[str, str], str] = {
    ("POST", "/onboarding/start"): "public_onboarding_start",
    ("POST", "/onboarding/answer"): "public_onboarding_answer",
    ("POST", "/onboarding/checkout"): "public_onboarding_checkout",
    ("POST", "/webhooks/stripe"): "stripe_webhook",
    ("POST", "/webhooks/telegram"): "telegram_webhook",
    ("POST", "/webhooks/discord"): "discord_webhook",
    ("POST", "/auth/admin/login"): "admin_login",
    ("POST", "/auth/user/login"): "user_login",
    ("POST", "/auth/user/logout"): "user_logout",
    ("POST", "/auth/admin/logout"): "admin_logout",
    ("GET", "/user/dashboard"): "user_dashboard",
    ("GET", "/user/billing"): "user_billing",
    ("POST", "/user/portal"): "user_portal_link",
    ("GET", "/user/provisioning"): "user_provisioning_status",
    ("GET", "/admin/dashboard"): "admin_dashboard",
    ("GET", "/admin/service-health"): "admin_service_health",
    ("GET", "/admin/provisioning-jobs"): "admin_provisioning_jobs",
    ("GET", "/admin/dns-drift"): "admin_dns_drift",
    ("GET", "/admin/audit"): "admin_audit",
    ("GET", "/admin/events"): "admin_events",
    ("GET", "/admin/actions"): "admin_queued_actions",
    ("POST", "/admin/actions"): "admin_action",
    ("GET", "/admin/reconciliation"): "admin_reconciliation",
    ("GET", "/admin/provider-state"): "admin_provider_state",
    ("POST", "/admin/sessions/revoke"): "session_revoke",
    ("GET", "/admin/operator-snapshot"): "admin_operator_snapshot",
    ("GET", "/admin/scale-operations"): "admin_scale_operations",
    ("GET", "/user/provider-state"): "user_provider_state",
    ("GET", "/health"): "health",
    ("GET", "/openapi.json"): "openapi_spec",
}

# Routes that require no session authentication (public endpoints)
_PUBLIC_ROUTES = frozenset({
    "public_onboarding_start",
    "public_onboarding_answer",
    "public_onboarding_checkout",
    "stripe_webhook",
    "telegram_webhook",
    "discord_webhook",
    "admin_login",
    "user_login",
    "health",
    "openapi_spec",
})


def route_arclink_hosted_api(
    conn: sqlite3.Connection,
    *,
    method: str,
    path: str,
    headers: Mapping[str, Any],
    body: str = "",
    query: Mapping[str, str] | None = None,
    config: HostedApiConfig | None = None,
    stripe_client: Any | None = None,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    """Route a single API request and return (status, payload, headers).

    This is the main entry point for the hosted API boundary. It can be
    called directly in tests or wrapped in a WSGI/ASGI adapter.
    """
    cfg = config or HostedApiConfig()
    request_id = _request_id(headers)
    clean_method = str(method or "GET").upper()
    clean_path = str(path or "").rstrip("/")
    clean_query = dict(query or {})

    # CORS preflight
    if clean_method == "OPTIONS":
        cors = _cors_headers(cfg)
        return 204, {}, [("Content-Length", "0"), *cors]

    # Strip API prefix
    if clean_path.startswith(HOSTED_API_PREFIX):
        route_path = clean_path[len(HOSTED_API_PREFIX):]
    else:
        route_path = clean_path

    route_key = _ROUTES.get((clean_method, route_path))
    if route_key is None:
        return _json_response(404, {"error": "not_found"}, request_id=request_id)

    start = time.monotonic()
    try:
        parsed_body = _json_body(body) if body else {}
        stripe = stripe_client or resolve_stripe_client(cfg.env)

        if route_key == "public_onboarding_start":
            result = _handle_public_onboarding_start(conn, parsed_body, request_id, cfg)
        elif route_key == "public_onboarding_answer":
            result = _handle_public_onboarding_answer(conn, parsed_body, request_id, cfg)
        elif route_key == "public_onboarding_checkout":
            result = _handle_public_onboarding_checkout(conn, parsed_body, request_id, cfg, stripe)
        elif route_key == "stripe_webhook":
            result = _handle_stripe_webhook(conn, body, headers, request_id, cfg)
        elif route_key == "telegram_webhook":
            result = _handle_telegram_webhook(conn, parsed_body, request_id, cfg, stripe)
        elif route_key == "discord_webhook":
            result = _handle_discord_webhook(conn, body, headers, request_id, cfg, None, stripe)
        elif route_key == "admin_login":
            result = _handle_admin_login(conn, parsed_body, request_id, cfg)
        elif route_key == "user_login":
            result = _handle_user_login(conn, parsed_body, request_id, cfg)
        elif route_key == "user_logout":
            result = _handle_logout(conn, headers, request_id, cfg, "user")
        elif route_key == "admin_logout":
            result = _handle_logout(conn, headers, request_id, cfg, "admin")
        elif route_key == "user_dashboard":
            result = _handle_user_dashboard(conn, headers, clean_query, request_id, cfg)
        elif route_key == "user_billing":
            result = _handle_user_billing(conn, headers, request_id, cfg)
        elif route_key == "user_portal_link":
            result = _handle_user_portal_link(conn, headers, parsed_body, request_id, cfg, stripe)
        elif route_key == "user_provisioning_status":
            result = _handle_user_provisioning_status(conn, headers, clean_query, request_id, cfg)
        elif route_key == "admin_dashboard":
            result = _handle_admin_dashboard(conn, headers, clean_query, request_id, cfg)
        elif route_key in _ADMIN_READ_HANDLERS:
            result = _handle_admin_read(conn, headers, clean_query, request_id, cfg, route_key)
        elif route_key == "admin_action":
            result = _handle_admin_action(conn, headers, parsed_body, request_id, cfg)
        elif route_key == "session_revoke":
            result = _handle_session_revoke(conn, headers, parsed_body, request_id, cfg)
        elif route_key == "admin_operator_snapshot":
            result = _handle_admin_operator_snapshot(conn, headers, request_id, cfg)
        elif route_key == "admin_scale_operations":
            result = _handle_admin_scale_operations(conn, headers, request_id)
        elif route_key == "admin_provider_state":
            result = _handle_provider_state(conn, headers, request_id, cfg, "admin")
        elif route_key == "user_provider_state":
            result = _handle_provider_state(conn, headers, request_id, cfg, "user")
        elif route_key == "health":
            result = _handle_health(conn, request_id)
        elif route_key == "openapi_spec":
            result = _json_response(200, build_arclink_openapi_spec(), request_id=request_id)
        else:
            result = _json_response(404, {"error": "not_found"}, request_id=request_id)

        elapsed = time.monotonic() - start
        logger.info(
            "api_request method=%s path=%s route=%s status=%d elapsed=%.3fs request_id=%s",
            clean_method, route_path, route_key, result[0], elapsed, request_id,
        )

        # Append CORS headers
        cors = _cors_headers(cfg)
        if cors:
            result = (result[0], result[1], [*result[2], *cors])
        return result

    except ArcLinkRateLimitError as exc:
        elapsed = time.monotonic() - start
        reset_at = int(time.time()) + exc.reset_seconds
        logger.warning(
            "api_rate_limit method=%s path=%s route=%s elapsed=%.3fs request_id=%s",
            clean_method, route_path, route_key, elapsed, request_id,
        )
        rate_headers = [
            ("Retry-After", str(exc.reset_seconds)),
            ("X-RateLimit-Limit", str(exc.limit)),
            ("X-RateLimit-Remaining", str(exc.remaining)),
            ("X-RateLimit-Reset", str(reset_at)),
        ]
        cors = _cors_headers(cfg)
        return _json_response(
            429, {"error": str(exc), "request_id": request_id},
            request_id=request_id, extra_headers=[*rate_headers, *cors],
        )
    except ArcLinkApiAuthError as exc:
        elapsed = time.monotonic() - start
        logger.warning(
            "api_auth_error method=%s path=%s route=%s error=%s elapsed=%.3fs request_id=%s",
            clean_method, route_path, route_key, str(exc), elapsed, request_id,
        )
        return _json_response(401, {"error": str(exc), "request_id": request_id}, request_id=request_id)
    except StripeWebhookError as exc:
        elapsed = time.monotonic() - start
        logger.warning(
            "stripe_webhook_error path=%s error=%s elapsed=%.3fs request_id=%s",
            route_path, str(exc), elapsed, request_id,
        )
        return _json_response(400, {"error": str(exc), "request_id": request_id}, request_id=request_id)
    except KeyError:
        return _json_response(404, {"error": "not_found", "request_id": request_id}, request_id=request_id)
    except Exception:
        elapsed = time.monotonic() - start
        logger.exception(
            "api_error method=%s path=%s route=%s elapsed=%.3fs request_id=%s",
            clean_method, route_path, route_key, elapsed, request_id,
        )
        return _json_response(400, {"error": GENERIC_ARCLINK_API_ERROR, "request_id": request_id}, request_id=request_id)


# --- WSGI adapter -------------------------------------------------------------


def make_arclink_hosted_api_wsgi(
    conn: sqlite3.Connection,
    *,
    config: HostedApiConfig | None = None,
    stripe_client: Any | None = None,
) -> Any:
    """Return a WSGI application wrapping route_arclink_hosted_api."""
    cfg = config or HostedApiConfig()

    def app(environ: Mapping[str, Any], start_response: Any) -> list[bytes]:
        method = str(environ.get("REQUEST_METHOD", "GET"))
        path = str(environ.get("PATH_INFO", "/"))
        qs = str(environ.get("QUERY_STRING", ""))
        query = {k: v[0] for k, v in parse_qs(qs).items() if v}
        length = int(str(environ.get("CONTENT_LENGTH") or "0") or 0)
        body = environ["wsgi.input"].read(length).decode("utf-8") if length else ""

        # Build headers dict from CGI environ
        headers: dict[str, str] = {}
        for key, value in dict(environ).items():
            if key.startswith("HTTP_"):
                header_name = key[5:].replace("_", "-").lower()
                headers[header_name] = str(value or "")
            elif key == "CONTENT_TYPE":
                headers["content-type"] = str(value or "")

        status_code, payload, response_headers = route_arclink_hosted_api(
            conn,
            method=method,
            path=path,
            headers=headers,
            body=body,
            query=query,
            config=cfg,
            stripe_client=stripe_client,
        )
        status_text = {
            200: "200 OK",
            201: "201 Created",
            202: "202 Accepted",
            204: "204 No Content",
            400: "400 Bad Request",
            401: "401 Unauthorized",
            404: "404 Not Found",
            429: "429 Too Many Requests",
            500: "500 Internal Server Error",
            503: "503 Service Unavailable",
        }.get(status_code, f"{status_code} OK")
        response_body = json.dumps(payload, sort_keys=True).encode("utf-8") if payload else b""
        start_response(status_text, response_headers)
        return [response_body]

    return app


def main() -> int:
    """Run the hosted API with the standard-library WSGI server.

    Production deployments can still place this WSGI app behind a stronger
    process manager, but the Docker control-node path needs a direct, boring
    executable entrypoint.
    """
    hosted_config = HostedApiConfig()
    logging.basicConfig(level=getattr(logging, hosted_config.log_level, logging.INFO))
    cfg = Config.from_env()
    host = str(os.environ.get("ARCLINK_API_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    port = int(str(os.environ.get("ARCLINK_API_PORT") or "8900"))
    conn = connect_db(cfg)
    app = make_arclink_hosted_api_wsgi(conn, config=hosted_config)
    logger.info("ArcLink hosted API listening on %s:%s", host, port)
    with make_server(host, port, app) as server:
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
