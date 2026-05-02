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

from arclink_adapters import FakeStripeClient, StripeWebhookError
from arclink_entitlements import process_stripe_webhook, StripeWebhookResult
from arclink_api_auth import (
    GENERIC_ARCLINK_API_ERROR,
    ArcLinkApiAuthError,
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
    read_admin_service_health_api,
    read_user_billing_api,
    read_user_dashboard_api,
    read_user_provisioning_status_api,
    require_arclink_csrf,
    revoke_arclink_session,
    start_public_onboarding_api,
)
from arclink_product import base_domain as default_base_domain

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


# --- Router -------------------------------------------------------------------

# Route table: (method, path_suffix) -> handler_key
_ROUTES: dict[tuple[str, str], str] = {
    ("POST", "/onboarding/start"): "public_onboarding_start",
    ("POST", "/onboarding/answer"): "public_onboarding_answer",
    ("POST", "/onboarding/checkout"): "public_onboarding_checkout",
    ("POST", "/webhooks/stripe"): "stripe_webhook",
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
    ("POST", "/admin/sessions/revoke"): "session_revoke",
}

# Routes that require no session authentication (public endpoints)
_PUBLIC_ROUTES = frozenset({
    "public_onboarding_start",
    "public_onboarding_answer",
    "public_onboarding_checkout",
    "stripe_webhook",
    "admin_login",
    "user_login",
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
        stripe = stripe_client or FakeStripeClient()

        if route_key == "public_onboarding_start":
            result = _handle_public_onboarding_start(conn, parsed_body, request_id, cfg)
        elif route_key == "public_onboarding_answer":
            result = _handle_public_onboarding_answer(conn, parsed_body, request_id, cfg)
        elif route_key == "public_onboarding_checkout":
            result = _handle_public_onboarding_checkout(conn, parsed_body, request_id, cfg, stripe)
        elif route_key == "stripe_webhook":
            result = _handle_stripe_webhook(conn, body, headers, request_id, cfg)
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
        }.get(status_code, f"{status_code} OK")
        response_body = json.dumps(payload, sort_keys=True).encode("utf-8") if payload else b""
        start_response(status_text, response_headers)
        return [response_body]

    return app
