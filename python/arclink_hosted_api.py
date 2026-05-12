#!/usr/bin/env python3
"""ArcLink Hosted API - production HTTP boundary over existing contracts.

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
import threading
import time
import hmac
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse
from wsgiref.simple_server import make_server

from arclink_adapters import FakeStripeClient, StripeWebhookError, resolve_stripe_client
from arclink_chutes import renewal_lifecycle_for_billing_state
from arclink_control import (
    Config,
    append_arclink_event,
    connect_db,
    is_ip_in_cidrs,
    is_loopback_ip,
    queue_notification,
)
from arclink_entitlements import process_stripe_webhook, StripeWebhookResult
from arclink_api_auth import (
    GENERIC_ARCLINK_API_ERROR,
    GENERIC_ARCLINK_AUTH_ERROR,
    ArcLinkApiAuthError,
    ArcLinkRateLimitError,
    _header as _api_header,
    accept_user_share_grant_api,
    acknowledge_user_credential_api,
    answer_public_onboarding_api,
    authenticate_arclink_admin_session,
    approve_user_share_grant_api,
    check_arclink_rate_limit,
    create_arclink_admin_login_session_api,
    create_arclink_user_login_session_api,
    create_user_share_grant_api,
    create_user_portal_link_api,
    deny_user_share_grant_api,
    extract_arclink_csrf_token,
    extract_arclink_browser_session_credentials,
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
    cancel_onboarding_session_api,
    claim_session_from_onboarding_api,
    read_provider_state_api,
    read_user_credentials_api,
    authenticate_arclink_user_session,
    read_user_billing_api,
    read_user_dashboard_api,
    read_user_linked_resources_api,
    read_user_provisioning_status_api,
    require_arclink_csrf,
    revoke_arclink_session,
    revoke_user_share_grant_api,
    start_public_onboarding_api,
)
from arclink_dashboard import build_operator_snapshot, build_scale_operations_snapshot
from arclink_discord import (
    ArcLinkDiscordError,
    DiscordConfig,
    handle_discord_webhook_request,
)
from arclink_notification_delivery import run_public_agent_turns_once
from arclink_product import base_domain as default_base_domain
from arclink_secrets_regex import redact_then_truncate
from arclink_telegram import LiveTelegramTransport, TelegramConfig, handle_telegram_update

logger = logging.getLogger("arclink.hosted_api")


def _log_error_text(exc: Exception, *, limit: int) -> str:
    return redact_then_truncate(exc, limit=limit)

_PUBLIC_AGENT_LIVE_TRIGGER_LOCK = threading.Lock()
_PUBLIC_AGENT_LIVE_TRIGGER_EXECUTOR: ThreadPoolExecutor | None = None
_PUBLIC_AGENT_LIVE_TRIGGER_EXECUTOR_WORKERS = 0
_PUBLIC_AGENT_LIVE_TRIGGER_SEMAPHORE: threading.BoundedSemaphore | None = None
_PUBLIC_AGENT_LIVE_TRIGGER_PENDING_LIMIT = 0

# --- Configuration -----------------------------------------------------------

HOSTED_API_PREFIX = "/api/v1"
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
CORS_ALLOWED_METHODS = "GET, POST, OPTIONS"
CORS_ALLOWED_HEADERS = (
    "Content-Type, "
    "X-ArcLink-Session-Id, X-ArcLink-Session-Token, X-ArcLink-CSRF-Token, "
    "X-ArcLink-Request-Id"
)
CORS_MAX_AGE = "86400"
REQUEST_ID_HEADER = "x-arclink-request-id"
DEFAULT_MAX_BODY_BYTES = 1024 * 1024
DEFAULT_WEBHOOK_MAX_BODY_BYTES = 2 * 1024 * 1024


class HostedApiConfig:
    """Runtime configuration resolved from environment."""

    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        e = dict(env or os.environ)
        self.env: dict[str, str] = e
        self.base_domain: str = default_base_domain(e)
        self.cors_origin: str = str(e.get("ARCLINK_CORS_ORIGIN", "")).strip()
        self.cookie_domain: str = str(e.get("ARCLINK_COOKIE_DOMAIN", "")).strip()
        self.cookie_samesite: str = _normalize_cookie_samesite(str(e.get("ARCLINK_COOKIE_SAMESITE", SESSION_COOKIE_SAMESITE)))
        cookie_secure_raw = str(e.get("ARCLINK_COOKIE_SECURE", "")).strip()
        self.cookie_secure: bool = (
            cookie_secure_raw != "0"
            if cookie_secure_raw
            else not _is_local_http_origin(self.cors_origin)
        )
        self.stripe_webhook_secret: str = str(e.get("STRIPE_WEBHOOK_SECRET", "")).strip()
        self.telegram_webhook_secret: str = str(e.get("TELEGRAM_WEBHOOK_SECRET", "")).strip()
        self.log_level: str = str(e.get("ARCLINK_LOG_LEVEL", "INFO")).strip().upper()
        self.max_body_bytes: int = _bounded_env_int(
            e,
            "ARCLINK_HOSTED_API_MAX_BODY_BYTES",
            DEFAULT_MAX_BODY_BYTES,
            minimum=1,
            maximum=32 * 1024 * 1024,
        )
        self.webhook_max_body_bytes: int = _bounded_env_int(
            e,
            "ARCLINK_HOSTED_API_WEBHOOK_MAX_BODY_BYTES",
            DEFAULT_WEBHOOK_MAX_BODY_BYTES,
            minimum=1,
            maximum=32 * 1024 * 1024,
        )
        self.backend_allowed_cidrs: str = str(e.get("ARCLINK_BACKEND_ALLOWED_CIDRS", "")).strip()
        self.webhook_rate_limit_window_seconds: int = _bounded_env_int(
            e,
            "ARCLINK_WEBHOOK_RATE_LIMIT_WINDOW_SECONDS",
            60,
            minimum=1,
            maximum=3600,
        )
        self.webhook_rate_limit_default: int = _bounded_env_int(
            e,
            "ARCLINK_WEBHOOK_RATE_LIMIT_DEFAULT",
            60,
            minimum=1,
            maximum=10000,
        )
        self.webhook_rate_limit_stripe: int = _bounded_env_int(
            e,
            "ARCLINK_WEBHOOK_RATE_LIMIT_STRIPE",
            self.webhook_rate_limit_default,
            minimum=1,
            maximum=10000,
        )
        self.webhook_rate_limit_telegram: int = _bounded_env_int(
            e,
            "ARCLINK_WEBHOOK_RATE_LIMIT_TELEGRAM",
            self.webhook_rate_limit_default,
            minimum=1,
            maximum=10000,
        )
        self.webhook_rate_limit_discord: int = _bounded_env_int(
            e,
            "ARCLINK_WEBHOOK_RATE_LIMIT_DISCORD",
            self.webhook_rate_limit_default,
            minimum=1,
            maximum=10000,
        )
        self.default_price_id: str = str(
            e.get("ARCLINK_FOUNDERS_PRICE_ID")
            or e.get("ARCLINK_DEFAULT_PRICE_ID")
            or e.get("ARCLINK_SOVEREIGN_PRICE_ID")
            or e.get("ARCLINK_FIRST_AGENT_PRICE_ID")
            or "price_arclink_founders"
        ).strip()
        self.founders_price_id: str = str(e.get("ARCLINK_FOUNDERS_PRICE_ID") or self.default_price_id).strip()
        self.sovereign_price_id: str = str(e.get("ARCLINK_SOVEREIGN_PRICE_ID") or "price_arclink_sovereign").strip()
        self.scale_price_id: str = str(e.get("ARCLINK_SCALE_PRICE_ID") or "price_arclink_scale").strip()
        self.sovereign_agent_expansion_price_id: str = str(
            e.get("ARCLINK_SOVEREIGN_AGENT_EXPANSION_PRICE_ID")
            or e.get("ARCLINK_ADDITIONAL_AGENT_PRICE_ID")
            or "price_arclink_sovereign_agent_expansion"
        ).strip()
        self.scale_agent_expansion_price_id: str = str(
            e.get("ARCLINK_SCALE_AGENT_EXPANSION_PRICE_ID")
            or "price_arclink_scale_agent_expansion"
        ).strip()
        self.additional_agent_price_id: str = self.sovereign_agent_expansion_price_id


# --- Request / Response helpers -----------------------------------------------


class HostedApiBodyError(ValueError):
    """Raised when the HTTP body fails the hosted API ingress contract."""

    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


def _bounded_env_int(
    env: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw = str(env.get(name, str(default))).strip()
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _is_local_http_origin(origin: str) -> bool:
    parsed = urlparse(str(origin or "").strip())
    if parsed.scheme != "http":
        return False
    host = (parsed.hostname or "").strip().lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def _normalize_cookie_samesite(value: str) -> str:
    clean = str(value or SESSION_COOKIE_SAMESITE).strip().lower()
    if clean == "none":
        return "None"
    if clean == "lax":
        return "Lax"
    return "Strict"


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
        raise HostedApiBodyError(400, "invalid_json")
    if not isinstance(parsed, dict):
        raise HostedApiBodyError(400, "invalid_json")
    return dict(parsed)


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


def _cookie_flags(config: HostedApiConfig, *, expire: bool = False, httponly: bool = True) -> str:
    flags = f"; Path=/; SameSite={config.cookie_samesite}"
    if httponly:
        flags += "; HttpOnly"
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
    """Build Set-Cookie headers for session credentials.

    Session ID and token cookies are HttpOnly (server-only extraction).
    The CSRF cookie is explicitly non-HttpOnly so browser JS can read it
    and send the value as a header for mutation requests.
    """
    cookies: list[tuple[str, str]] = []
    prefix = f"arclink_{kind}"
    httponly_flags = _cookie_flags(config)
    csrf_flags = _cookie_flags(config, httponly=False)
    for field, suffix, flags in (
        ("session_id", "session_id", httponly_flags),
        ("session_token", "session_token", httponly_flags),
        ("csrf_token", "csrf", csrf_flags),
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


def _response_with_cors(
    result: tuple[int, dict[str, Any], list[tuple[str, str]]],
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    cors = _cors_headers(config)
    if not cors:
        return result
    return (result[0], result[1], [*result[2], *cors])


def _route_body_limit(config: HostedApiConfig, route_key: str | None) -> int:
    if route_key in {"stripe_webhook", "telegram_webhook", "discord_webhook"}:
        return config.webhook_max_body_bytes
    return config.max_body_bytes


def _body_size_bytes(body: str) -> int:
    return len(body.encode("utf-8"))


def _remote_ip_from_headers(
    config: HostedApiConfig,
    headers: Mapping[str, Any],
    remote_addr: str = "",
) -> str:
    """Resolve the client IP used for CIDR decisions.

    Forwarded headers are trusted only when the direct peer is already a
    local/trusted backend peer. This preserves reverse-proxy behavior without
    letting an arbitrary public client spoof an allowed source.
    """
    direct = str(remote_addr or "").strip() or _api_header(headers, "x-real-ip") or "127.0.0.1"
    forwarded = _api_header(headers, "x-forwarded-for")
    if forwarded and _backend_client_allowed(config, direct):
        candidate = forwarded.split(",", 1)[0].strip()
        if candidate:
            return candidate
    return direct


def _backend_client_allowed(config: HostedApiConfig, remote_ip: str) -> bool:
    normalized = str(remote_ip or "").strip()
    if is_loopback_ip(normalized):
        return True
    return is_ip_in_cidrs(normalized, config.backend_allowed_cidrs)


def _webhook_provider_for_route(route_key: str) -> str:
    return str(route_key or "").removesuffix("_webhook").strip().lower()


def _webhook_rate_limit_for_provider(config: HostedApiConfig, provider: str) -> int:
    return {
        "stripe": config.webhook_rate_limit_stripe,
        "telegram": config.webhook_rate_limit_telegram,
        "discord": config.webhook_rate_limit_discord,
    }.get(provider, config.webhook_rate_limit_default)


def _check_webhook_rate_limit(
    conn: sqlite3.Connection,
    *,
    config: HostedApiConfig,
    route_key: str,
    headers: Mapping[str, Any],
    remote_addr: str,
) -> None:
    provider = _webhook_provider_for_route(route_key)
    if not provider:
        return
    client_ip = _remote_ip_from_headers(config, headers, remote_addr)
    subject = f"ip:{client_ip or 'unknown'}"
    check_arclink_rate_limit(
        conn,
        scope=f"webhook:{provider}",
        subject=subject,
        limit=_webhook_rate_limit_for_provider(config, provider),
        window_seconds=config.webhook_rate_limit_window_seconds,
    )


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
        selected_plan_id=str(body.get("plan_id") or "founders"),
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
    session_id = str(body.get("session_id") or "")
    session_row = conn.execute("SELECT selected_plan_id FROM arclink_onboarding_sessions WHERE session_id = ?", (session_id,)).fetchone()
    selected_plan_id = str((dict(session_row) if session_row is not None else {}).get("selected_plan_id") or body.get("plan_id") or "").strip().lower()
    price_id = str(body.get("price_id") or config.default_price_id)
    if selected_plan_id == "founders" and config.founders_price_id:
        price_id = config.founders_price_id
    if selected_plan_id == "sovereign" and config.sovereign_price_id:
        price_id = config.sovereign_price_id
    if selected_plan_id == "scale" and config.scale_price_id:
        price_id = config.scale_price_id
    result = open_public_onboarding_checkout_api(
        conn,
        session_id=session_id,
        stripe_client=stripe_client,
        price_id=price_id,
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
        # Money-safety: Stripe stops retrying on 2xx, so a 200 here would silently
        # accept payments while never crediting entitlements. Return 503 so Stripe
        # retries for up to 3 days and operators are forced to notice.
        logger.error(
            "stripe_webhook_misconfigured: STRIPE_WEBHOOK_SECRET is not set; rejecting webhook so Stripe retries request_id=%s",
            request_id,
        )
        return _json_response(
            503,
            {"error": "stripe_webhook_secret_unset", "request_id": request_id},
            request_id=request_id,
        )
    sig = _api_header(headers, "stripe-signature")
    result: StripeWebhookResult = process_stripe_webhook(
        conn, payload=raw_body, signature=sig, secret=config.stripe_webhook_secret,
    )
    logger.info(
        "stripe_webhook event_type=%s event_id=%s user_id=%s entitlement=%s replayed=%s request_id=%s",
        result.event_type, result.event_id, result.user_id, result.entitlement_state, result.replayed, request_id,
    )

    # Raven speaks before silence: queue a "payment cleared" ping back to the
    # user's originating channel the first time entitlement transitions to paid.
    if not result.replayed and result.entitlement_state == "paid" and result.user_id:
        try:
            _queue_paid_ping(conn, user_id=result.user_id, request_id=request_id)
        except Exception:  # noqa: BLE001 - never fail the webhook over a ping
            logger.exception("paid_ping_failed user_id=%s request_id=%s", result.user_id, request_id)
    elif not result.replayed and result.entitlement_state != "paid" and result.user_id:
        try:
            _queue_billing_noncurrent_ping(
                conn,
                user_id=result.user_id,
                entitlement_state=result.entitlement_state,
                request_id=request_id,
            )
        except Exception:  # noqa: BLE001 - never fail the webhook over a ping
            logger.exception("billing_noncurrent_ping_failed user_id=%s request_id=%s", result.user_id, request_id)

    return _json_response(200, {
        "status": "processed",
        "event_id": result.event_id,
        "event_type": result.event_type,
        "replayed": result.replayed,
    }, request_id=request_id)


def _queue_paid_ping(conn: sqlite3.Connection, *, user_id: str, request_id: str) -> int | None:
    """Queue an outbound 'payment cleared' message back to the user's original
    public channel. Returns the queued notification id, or None if no eligible
    channel was found (e.g., web-only user - they get a different surface).
    """
    row = conn.execute(
        """
        SELECT session_id, channel, channel_identity, display_name_hint
        FROM arclink_onboarding_sessions
        WHERE user_id = ?
          AND channel IN ('telegram', 'discord')
          AND channel_identity != ''
        ORDER BY updated_at DESC, created_at DESC, session_id DESC
        LIMIT 1
        """,
        (str(user_id or "").strip(),),
    ).fetchone()
    if row is None:
        return None
    session_id = str(row["session_id"] or "").strip()
    if session_id:
        existing = conn.execute(
            """
            SELECT 1
            FROM arclink_events
            WHERE subject_kind = 'onboarding_session'
              AND subject_id = ?
              AND event_type = 'public_bot:payment_cleared_ping_queued'
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        if existing is not None:
            return None
    channel = str(row["channel"] or "").strip().lower()
    target_id = _public_bot_target_id(channel=channel, channel_identity=str(row["channel_identity"] or ""))
    if channel not in {"telegram", "discord"} or not target_id:
        return None
    name = str(row["display_name_hint"] or "").strip()
    greeting = f"Captain {name}, " if name else ""
    message = (
        f"{greeting}payment cleared.\n\n"
        "Stage 2 complete: Stripe confirmed the handoff.\n"
        "Stage 3 is starting now: I am preparing your ArcLink resources, wiring the agent, and checking the deployment health.\n\n"
        "Stay in this channel. I will report back here with the result and working links as soon as the agent is ready."
    )
    nid = queue_notification(
        conn,
        target_kind="public-bot-user",
        target_id=target_id,
        channel_kind=channel,
        message=message,
        extra=_public_bot_ping_actions(),
    )
    if session_id:
        append_arclink_event(
            conn,
            subject_kind="onboarding_session",
            subject_id=session_id,
            event_type="public_bot:payment_cleared_ping_queued",
            metadata={"notification_id": nid, "channel": channel},
        )
    logger.info(
        "paid_ping_queued user_id=%s channel=%s notification_id=%d request_id=%s",
        user_id, channel, nid, request_id,
    )
    return nid


def _queue_billing_noncurrent_ping(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    entitlement_state: str,
    request_id: str,
) -> int | None:
    row = conn.execute(
        """
        SELECT channel, channel_identity, display_name_hint
        FROM arclink_onboarding_sessions
        WHERE user_id = ?
          AND channel IN ('telegram', 'discord')
          AND channel_identity != ''
        ORDER BY updated_at DESC, created_at DESC, session_id DESC
        LIMIT 1
        """,
        (str(user_id or "").strip(),),
    ).fetchone()
    if row is None:
        return None
    channel = str(row["channel"] or "").strip().lower()
    target_id = _public_bot_target_id(channel=channel, channel_identity=str(row["channel_identity"] or ""))
    if channel not in {"telegram", "discord"} or not target_id:
        return None
    lifecycle = renewal_lifecycle_for_billing_state(entitlement_state)
    name = str(row["display_name_hint"] or "").strip()
    greeting = f"Captain {name}, " if name else ""
    message = (
        f"{greeting}billing did not renew, so ArcLink has paused provider access for your agent.\n\n"
        "Raven will remind you once each day while payment is unresolved. "
        "After 7 days unpaid, the reminders will explicitly warn that account and agent data removal is next. "
        "After 14 days unpaid, ArcLink queues audited purge of the deployed agent data. "
        "Update billing from your ArcLink dashboard to restore service."
    )
    nid = queue_notification(
        conn,
        target_kind="public-bot-user",
        target_id=target_id,
        channel_kind=channel,
        message=message,
        extra={
            "billing_state": entitlement_state,
            "lifecycle": lifecycle,
            "buttons": [{"label": "Open billing", "command": "/billing"}],
        },
    )
    logger.info(
        "billing_noncurrent_ping_queued user_id=%s state=%s channel=%s notification_id=%d request_id=%s",
        user_id, entitlement_state, channel, nid, request_id,
    )
    return nid


def _public_bot_target_id(*, channel: str, channel_identity: str) -> str:
    value = str(channel_identity or "").strip()
    if channel == "telegram" and value.lower().startswith("tg:"):
        return value[3:].strip()
    if channel == "discord" and value.lower().startswith("discord:"):
        return value[len("discord:"):].strip()
    return value


def _public_bot_ping_actions() -> dict[str, Any]:
    return {
        "telegram_reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "Check Status", "callback_data": "arclink:/raven status"},
                    {"text": "Show My Crew", "callback_data": "arclink:/raven agents"},
                ],
            ],
        },
        "discord_components": [
            {
                "type": 1,
                "components": [
                    {"type": 2, "label": "Check Status", "style": 2, "custom_id": "arclink:/status"},
                    {"type": 2, "label": "Show My Crew", "style": 2, "custom_id": "arclink:/agents"},
                ],
            }
        ],
    }


def _handle_admin_login(
    conn: sqlite3.Connection,
    body: dict[str, Any],
    request_id: str,
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    result = create_arclink_admin_login_session_api(
        conn,
        email=str(body.get("email") or ""),
        password=str(body.get("password") or ""),
        login_subject=str(body.get("login_subject") or body.get("email") or ""),
        mfa_verified=False,
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
        password=str(body.get("password") or ""),
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
    creds = extract_arclink_browser_session_credentials(headers, session_kind=kind)
    if kind == "admin":
        authenticate_arclink_admin_session(conn, session_id=creds["session_id"], session_token=creds["session_token"])
    else:
        authenticate_arclink_user_session(conn, session_id=creds["session_id"], session_token=creds["session_token"])
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
    creds = extract_arclink_browser_session_credentials(headers, session_kind="admin")
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
    creds = extract_arclink_browser_session_credentials(headers, session_kind="user")
    authenticate_arclink_user_session(conn, session_id=creds["session_id"], session_token=creds["session_token"])
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


def _handle_user_credentials(
    conn: sqlite3.Connection,
    headers: Mapping[str, Any],
    query: dict[str, str],
    request_id: str,
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    creds = extract_arclink_session_credentials(headers, session_kind="user")
    result = read_user_credentials_api(
        conn,
        session_id=creds["session_id"],
        session_token=creds["session_token"],
        deployment_id=query.get("deployment_id", ""),
    )
    return _json_response(result.status, result.payload, request_id=request_id)


def _handle_user_credential_ack(
    conn: sqlite3.Connection,
    headers: Mapping[str, Any],
    body: dict[str, Any],
    request_id: str,
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    creds = extract_arclink_browser_session_credentials(headers, session_kind="user")
    csrf = extract_arclink_csrf_token(headers, session_kind="user")
    result = acknowledge_user_credential_api(
        conn,
        session_id=creds["session_id"],
        session_token=creds["session_token"],
        csrf_token=csrf,
        handoff_id=str(body.get("handoff_id") or ""),
    )
    return _json_response(result.status, result.payload, request_id=request_id)


def _handle_user_share_grant_create(
    conn: sqlite3.Connection,
    headers: Mapping[str, Any],
    body: dict[str, Any],
    request_id: str,
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    creds = extract_arclink_browser_session_credentials(headers, session_kind="user")
    csrf = extract_arclink_csrf_token(headers, session_kind="user")
    result = create_user_share_grant_api(
        conn,
        session_id=creds["session_id"],
        session_token=creds["session_token"],
        csrf_token=csrf,
        recipient_user_id=str(body.get("recipient_user_id") or ""),
        resource_kind=str(body.get("resource_kind") or "drive"),
        resource_root=str(body.get("resource_root") or "vault"),
        resource_path=str(body.get("resource_path") or ""),
        display_name=str(body.get("display_name") or ""),
        access_mode=str(body.get("access_mode") or "read"),
        metadata=body.get("metadata"),
    )
    return _json_response(result.status, result.payload, request_id=request_id)


def _handle_user_share_grant_approve(
    conn: sqlite3.Connection,
    headers: Mapping[str, Any],
    body: dict[str, Any],
    request_id: str,
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    creds = extract_arclink_browser_session_credentials(headers, session_kind="user")
    csrf = extract_arclink_csrf_token(headers, session_kind="user")
    result = approve_user_share_grant_api(
        conn,
        session_id=creds["session_id"],
        session_token=creds["session_token"],
        csrf_token=csrf,
        grant_id=str(body.get("grant_id") or ""),
    )
    return _json_response(result.status, result.payload, request_id=request_id)


def _handle_user_share_grant_deny(
    conn: sqlite3.Connection,
    headers: Mapping[str, Any],
    body: dict[str, Any],
    request_id: str,
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    creds = extract_arclink_browser_session_credentials(headers, session_kind="user")
    csrf = extract_arclink_csrf_token(headers, session_kind="user")
    result = deny_user_share_grant_api(
        conn,
        session_id=creds["session_id"],
        session_token=creds["session_token"],
        csrf_token=csrf,
        grant_id=str(body.get("grant_id") or ""),
    )
    return _json_response(result.status, result.payload, request_id=request_id)


def _handle_user_share_grant_accept(
    conn: sqlite3.Connection,
    headers: Mapping[str, Any],
    body: dict[str, Any],
    request_id: str,
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    creds = extract_arclink_browser_session_credentials(headers, session_kind="user")
    csrf = extract_arclink_csrf_token(headers, session_kind="user")
    result = accept_user_share_grant_api(
        conn,
        session_id=creds["session_id"],
        session_token=creds["session_token"],
        csrf_token=csrf,
        grant_id=str(body.get("grant_id") or ""),
    )
    return _json_response(result.status, result.payload, request_id=request_id)


def _handle_user_share_grant_revoke(
    conn: sqlite3.Connection,
    headers: Mapping[str, Any],
    body: dict[str, Any],
    request_id: str,
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    creds = extract_arclink_browser_session_credentials(headers, session_kind="user")
    csrf = extract_arclink_csrf_token(headers, session_kind="user")
    result = revoke_user_share_grant_api(
        conn,
        session_id=creds["session_id"],
        session_token=creds["session_token"],
        csrf_token=csrf,
        grant_id=str(body.get("grant_id") or ""),
    )
    return _json_response(result.status, result.payload, request_id=request_id)


def _handle_user_linked_resources(
    conn: sqlite3.Connection,
    headers: Mapping[str, Any],
    query: dict[str, str],
    request_id: str,
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    creds = extract_arclink_session_credentials(headers, session_kind="user")
    result = read_user_linked_resources_api(
        conn,
        session_id=creds["session_id"],
        session_token=creds["session_token"],
        user_id=query.get("user_id", ""),
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
    creds = extract_arclink_browser_session_credentials(headers, session_kind="admin")
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
        env=config.env,
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


def _handle_onboarding_status(
    conn: sqlite3.Connection,
    query: dict[str, str],
    request_id: str,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    """Return current onboarding/entitlement state for a session.

    Used by checkout success page to poll until webhook confirms payment.
    """
    session_id = str(query.get("session_id") or "").strip()
    if not session_id:
        return _json_response(400, {"error": "session_id required"}, request_id=request_id)
    row = conn.execute(
        """
        SELECT s.session_id, s.status, s.user_id, s.channel, s.channel_identity,
               s.display_name_hint, s.selected_plan_id
        FROM arclink_onboarding_sessions s
        WHERE s.session_id = ?
        """,
        (session_id,),
    ).fetchone()
    if row is None:
        return _json_response(404, {"error": "session_not_found"}, request_id=request_id)
    row_dict = dict(row)
    user_id = str(row_dict.get("user_id") or "").strip()
    entitlement_state = "unknown"
    if user_id:
        user_row = conn.execute(
            "SELECT entitlement_state FROM arclink_users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if user_row is not None:
            entitlement_state = str(dict(user_row).get("entitlement_state") or "unknown")
    return _json_response(200, {
        "session_id": session_id,
        "status": row_dict.get("status") or "open",
        "user_id": user_id,
        "entitlement_state": entitlement_state,
        "plan_id": row_dict.get("selected_plan_id") or "",
        "display_name": row_dict.get("display_name_hint") or "",
        "channel": row_dict.get("channel") or "",
        "channel_identity": row_dict.get("channel_identity") or "",
    }, request_id=request_id)


def _handle_onboarding_claim_session(
    conn: sqlite3.Connection,
    body: dict[str, Any],
    request_id: str,
    config: HostedApiConfig,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    result = claim_session_from_onboarding_api(
        conn,
        onboarding_session_id=str(body.get("session_id") or ""),
        browser_claim_token=str(body.get("claim_token") or ""),
    )
    cookies: list[tuple[str, str]] = []
    if result.status == 201:
        cookies = _session_cookies(result.payload.get("session", {}), kind="user", config=config)
    return _json_response(result.status, result.payload, request_id=request_id, extra_headers=cookies)


def _handle_onboarding_cancel(
    conn: sqlite3.Connection,
    body: dict[str, Any],
    request_id: str,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    result = cancel_onboarding_session_api(
        conn,
        onboarding_session_id=str(body.get("session_id") or ""),
        browser_cancel_token=str(body.get("cancel_token") or ""),
    )
    return _json_response(result.status, result.payload, request_id=request_id)


def _handle_adapter_mode(
    config: HostedApiConfig,
    request_id: str,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    """Report whether the system is running with fake or live adapters."""
    from arclink_adapters import resolve_stripe_client, FakeStripeClient
    stripe = resolve_stripe_client(config.env)
    fake_stripe = isinstance(stripe, FakeStripeClient)
    fake_mode = fake_stripe or str(config.env.get("ARCLINK_FAKE_MODE") or config.env.get("ARCLINK_FAKE_ADAPTERS") or "").strip().lower() in ("1", "true", "yes")
    return _json_response(200, {
        "fake_mode": fake_mode,
        "fake_stripe": fake_stripe,
    }, request_id=request_id)


def _handle_health(
    conn: sqlite3.Connection,
    request_id: str,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    """Simple liveness check - verifies DB is reachable."""
    try:
        conn.execute("SELECT 1").fetchone()
        db_ok = True
    except Exception:
        db_ok = False
    status = 200 if db_ok else 503
    return _json_response(status, {"status": "ok" if db_ok else "degraded", "db": db_ok}, request_id=request_id)


def _public_agent_live_trigger_enabled(config: HostedApiConfig) -> bool:
    return str(config.env.get("ARCLINK_PUBLIC_AGENT_LIVE_TRIGGER", "1")).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _public_agent_live_trigger_can_run_locally(config: HostedApiConfig) -> bool:
    """Return whether this API process may run public-agent delivery work.

    In Dockerized Control Node mode, the API container deliberately does not
    mount the Docker socket. The delivery worker has that trusted-host
    boundary instead. Auto mode therefore only runs the low-latency in-process
    trigger when the process can actually reach the local Docker API.
    """
    mode = str(config.env.get("ARCLINK_PUBLIC_AGENT_LIVE_TRIGGER_RUNNER", "auto")).strip().lower()
    if mode in {"0", "false", "no", "off", "queue", "worker", "delivery-worker", "notification-delivery"}:
        return False
    if mode in {"1", "true", "yes", "on", "local", "inline", "api"}:
        return True
    return os.path.exists("/var/run/docker.sock")


def _bounded_int_config(
    config: HostedApiConfig,
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw = str(config.env.get(name, str(default))).strip()
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _public_agent_live_trigger_pool(
    config: HostedApiConfig,
) -> tuple[ThreadPoolExecutor, threading.BoundedSemaphore]:
    """Return the bounded live-trigger executor.

    The public webhook handler is an ingress boundary. It must acknowledge
    Telegram/Discord quickly and never spawn unbounded work. Durable outbox
    rows remain the source of truth; if this bounded kick is saturated, the
    notification worker will recover the pending turn.
    """
    workers = _bounded_int_config(
        config,
        "ARCLINK_PUBLIC_AGENT_LIVE_TRIGGER_WORKERS",
        4,
        minimum=1,
        maximum=64,
    )
    pending_limit = _bounded_int_config(
        config,
        "ARCLINK_PUBLIC_AGENT_LIVE_TRIGGER_MAX_PENDING",
        64,
        minimum=1,
        maximum=4096,
    )
    global _PUBLIC_AGENT_LIVE_TRIGGER_EXECUTOR
    global _PUBLIC_AGENT_LIVE_TRIGGER_EXECUTOR_WORKERS
    global _PUBLIC_AGENT_LIVE_TRIGGER_SEMAPHORE
    global _PUBLIC_AGENT_LIVE_TRIGGER_PENDING_LIMIT
    with _PUBLIC_AGENT_LIVE_TRIGGER_LOCK:
        if (
            _PUBLIC_AGENT_LIVE_TRIGGER_EXECUTOR is None
            or _PUBLIC_AGENT_LIVE_TRIGGER_EXECUTOR_WORKERS != workers
        ):
            old_executor = _PUBLIC_AGENT_LIVE_TRIGGER_EXECUTOR
            _PUBLIC_AGENT_LIVE_TRIGGER_EXECUTOR = ThreadPoolExecutor(
                max_workers=workers,
                thread_name_prefix="arclink-public-agent-live-trigger",
            )
            _PUBLIC_AGENT_LIVE_TRIGGER_EXECUTOR_WORKERS = workers
            if old_executor is not None:
                old_executor.shutdown(wait=False, cancel_futures=True)
        if (
            _PUBLIC_AGENT_LIVE_TRIGGER_SEMAPHORE is None
            or _PUBLIC_AGENT_LIVE_TRIGGER_PENDING_LIMIT != pending_limit
        ):
            _PUBLIC_AGENT_LIVE_TRIGGER_SEMAPHORE = threading.BoundedSemaphore(pending_limit)
            _PUBLIC_AGENT_LIVE_TRIGGER_PENDING_LIMIT = pending_limit
        return _PUBLIC_AGENT_LIVE_TRIGGER_EXECUTOR, _PUBLIC_AGENT_LIVE_TRIGGER_SEMAPHORE


def _kick_public_agent_live_trigger(
    *,
    config: HostedApiConfig,
    channel_kind: str,
    target_id: str,
    request_id: str,
) -> bool:
    if not _public_agent_live_trigger_enabled(config):
        return False
    clean_channel = str(channel_kind or "").strip().lower()
    clean_target = str(target_id or "").strip()
    if clean_channel not in {"telegram", "discord"} or not clean_target:
        return False
    if not _public_agent_live_trigger_can_run_locally(config):
        logger.debug(
            "public_agent_live_trigger_deferred channel=%s target=%s runner=notification-delivery request_id=%s",
            clean_channel,
            clean_target,
            request_id,
        )
        return False
    executor, pending_gate = _public_agent_live_trigger_pool(config)
    if not pending_gate.acquire(blocking=False):
        logger.warning(
            "public_agent_live_trigger_saturated channel=%s target=%s pending_limit=%s request_id=%s",
            clean_channel,
            clean_target,
            _bounded_int_config(
                config,
                "ARCLINK_PUBLIC_AGENT_LIVE_TRIGGER_MAX_PENDING",
                64,
                minimum=1,
                maximum=4096,
            ),
            request_id,
        )
        return False

    def _worker() -> None:
        try:
            summary = run_public_agent_turns_once(
                Config.from_env(),
                channel_kind=clean_channel,
                target_id=clean_target,
                limit=1,
            )
            logger.info(
                "public_agent_live_trigger channel=%s target=%s delivered=%s errors=%s request_id=%s",
                clean_channel,
                clean_target,
                summary.get("delivered", 0),
                summary.get("errors", 0),
                request_id,
            )
        except Exception as exc:  # noqa: BLE001 - webhook has already been acknowledged
            logger.warning(
                "public_agent_live_trigger_failed channel=%s target=%s error=%s request_id=%s",
                clean_channel,
                clean_target,
                _log_error_text(exc, limit=240),
                request_id,
            )

    try:
        future = executor.submit(_worker)
    except Exception as exc:  # noqa: BLE001 - leave the durable row for the worker
        pending_gate.release()
        logger.warning(
            "public_agent_live_trigger_submit_failed channel=%s target=%s error=%s request_id=%s",
            clean_channel,
            clean_target,
            _log_error_text(exc, limit=240),
            request_id,
        )
        return False

    def _release_live_trigger_slot(_future: Any) -> None:
        try:
            pending_gate.release()
        except ValueError:
            logger.warning(
                "public_agent_live_trigger_slot_release_failed channel=%s target=%s request_id=%s",
                clean_channel,
                clean_target,
                request_id,
            )

    future.add_done_callback(_release_live_trigger_slot)
    return True


def _handle_telegram_webhook(
    conn: sqlite3.Connection,
    body: dict[str, Any],
    request_id: str,
    config: HostedApiConfig,
    stripe_client: Any,
    telegram_transport: Any | None = None,
    headers: Mapping[str, Any] | None = None,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    """Handle an incoming Telegram Bot API update (webhook mode)."""
    if not config.telegram_webhook_secret:
        logger.error(
            "telegram_webhook_misconfigured: TELEGRAM_WEBHOOK_SECRET is not set; rejecting request_id=%s",
            request_id,
        )
        return _json_response(
            503,
            {"error": "telegram_webhook_secret_unset", "request_id": request_id},
            request_id=request_id,
        )
    supplied_secret = _api_header(headers or {}, "x-telegram-bot-api-secret-token")
    if not supplied_secret or not hmac.compare_digest(supplied_secret, config.telegram_webhook_secret):
        return _json_response(401, {"error": "invalid_telegram_webhook_secret"}, request_id=request_id)
    telegram_config = TelegramConfig.from_env(config.env)
    result = handle_telegram_update(
        conn, body,
        stripe_client=stripe_client,
        price_id=config.sovereign_price_id,
        founders_price_id=config.founders_price_id,
        scale_price_id=config.scale_price_id,
        additional_agent_price_id=config.additional_agent_price_id,
        sovereign_agent_expansion_price_id=config.sovereign_agent_expansion_price_id,
        scale_agent_expansion_price_id=config.scale_agent_expansion_price_id,
        base_domain=config.base_domain,
        telegram_bot_token=telegram_config.bot_token,
    )
    if result is None:
        return _json_response(200, {"ok": True, "action": "ignored"}, request_id=request_id)
    sent = False
    edited = False
    callback_acknowledged = False
    callback_query_id = str(result.get("callback_query_id") or "").strip()
    callback_message_id = str(result.get("callback_message_id") or "").strip()
    should_edit_callback_message = (
        str(result.get("action") or "") == "credentials_stored"
        and bool(callback_query_id)
        and bool(callback_message_id)
    )

    def _try_edit_callback_message(transport: Any, *, transport_label: str) -> bool:
        if not should_edit_callback_message or not hasattr(transport, "edit_message_text"):
            return False
        reply_text = str(result.get("text") or "").strip()
        if not reply_text:
            return False
        try:
            transport.edit_message_text(
                result["chat_id"],
                int(callback_message_id),
                reply_text,
                reply_markup=result.get("reply_markup"),
            )
            return True
        except Exception as exc:  # noqa: BLE001 - do not make Telegram retry a credential ack forever
            logger.warning(
                "telegram_callback_message_edit_failed transport=%s action=%s error=%s",
                transport_label,
                result.get("action", ""),
                _log_error_text(exc, limit=160),
            )
            return False

    if telegram_transport is not None:
        if callback_query_id and hasattr(telegram_transport, "answer_callback_query"):
            try:
                telegram_transport.answer_callback_query(callback_query_id)
                callback_acknowledged = True
            except Exception as exc:  # noqa: BLE001 - webhook must acknowledge update even if callback ack fails
                logger.warning("telegram_callback_ack_failed transport=injected action=%s error=%s", result.get("action", ""), _log_error_text(exc, limit=160))
        edited = _try_edit_callback_message(telegram_transport, transport_label="injected")
        reply_text = str(result.get("text") or "").strip()
        if reply_text and not edited:
            try:
                telegram_transport.send_message(result["chat_id"], result["text"], reply_markup=result.get("reply_markup"))
                sent = True
            except Exception as exc:  # noqa: BLE001 - webhook must not retry forever on reply transport failure
                logger.warning("telegram_reply_send_failed transport=injected action=%s error=%s", result.get("action", ""), _log_error_text(exc, limit=160))
    else:
        if telegram_config.is_live:
            live_transport = LiveTelegramTransport(telegram_config)
            if callback_query_id:
                try:
                    live_transport.answer_callback_query(callback_query_id)
                    callback_acknowledged = True
                except Exception as exc:  # noqa: BLE001 - still try to send the actual reply
                    logger.warning("telegram_callback_ack_failed transport=live action=%s error=%s", result.get("action", ""), _log_error_text(exc, limit=160))
            edited = _try_edit_callback_message(live_transport, transport_label="live")
            reply_text = str(result.get("text") or "").strip()
            if reply_text and not edited:
                try:
                    live_transport.send_message(result["chat_id"], result["text"], reply_markup=result.get("reply_markup"))
                    sent = True
                except Exception as exc:  # noqa: BLE001 - acknowledge Telegram update even if the reply API errors
                    logger.warning("telegram_reply_send_failed transport=live action=%s error=%s", result.get("action", ""), _log_error_text(exc, limit=160))
    live_triggered = False
    if str(result.get("action") or "") == "agent_message_queued":
        live_triggered = _kick_public_agent_live_trigger(
            config=config,
            channel_kind="telegram",
            target_id=str(result.get("channel_identity") or ""),
            request_id=request_id,
        )
    return _json_response(
        200,
        {
            "ok": True,
            "action": result.get("action", "reply"),
            "sent": sent,
            "edited": edited,
            "callback_acknowledged": callback_acknowledged,
            "live_triggered": live_triggered,
        },
        request_id=request_id,
    )


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
            price_id=config.sovereign_price_id,
            founders_price_id=config.founders_price_id,
            scale_price_id=config.scale_price_id,
            additional_agent_price_id=config.additional_agent_price_id,
            sovereign_agent_expansion_price_id=config.sovereign_agent_expansion_price_id,
            scale_agent_expansion_price_id=config.scale_agent_expansion_price_id,
            base_domain=config.base_domain,
        )
    except ArcLinkDiscordError as exc:
        return _json_response(401, {"error": str(exc)}, request_id=request_id)
    if str(response.get("action") or "") == "agent_message_queued":
        _kick_public_agent_live_trigger(
            config=config,
            channel_kind="discord",
            target_id=str(response.get("channel_identity") or ""),
            request_id=request_id,
        )
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
            "password": {"type": "string", "format": "password"},
            "login_subject": {"type": "string"},
            "mfa_verified": {"type": "boolean"},
            "metadata": {"type": "object"},
        }, required=["email", "password"]),
        "responses": _RESP_CREATED_UNAUTH,
    },
    "user_login": {
        "summary": "User login (creates session)",
        "tags": ["auth"],
        "requestBody": _openapi_json_body({
            "email": {"type": "string", "format": "email"},
            "password": {"type": "string", "format": "password"},
            "login_subject": {"type": "string"},
            "metadata": {"type": "object"},
        }, required=["email", "password"]),
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
    "user_credentials": {
        "summary": "Read pending credential handoff state",
        "tags": ["user"],
        "parameters": [_qparam("deployment_id")],
        "responses": {"200": {"description": "Credential handoff metadata"}, "401": {"description": "Unauthorized"}},
    },
    "user_credential_ack": {
        "summary": "Acknowledge credential storage and remove future handoff visibility",
        "tags": ["user"],
        "requestBody": _openapi_json_body({"handoff_id": {"type": "string"}}, required=["handoff_id"]),
        "responses": {"200": {"description": "Credential handoff removed"}, "401": {"description": "Unauthorized or missing CSRF"}},
    },
    "user_share_grant_create": {
        "summary": "Request a read-only Drive/Code share grant",
        "tags": ["user"],
        "requestBody": _openapi_json_body({
            "recipient_user_id": {"type": "string"},
            "resource_kind": {"type": "string", "enum": ["drive", "code"]},
            "resource_root": {"type": "string", "enum": ["vault", "workspace"]},
            "resource_path": {"type": "string"},
            "display_name": {"type": "string"},
            "access_mode": {"type": "string", "enum": ["read"]},
        }, required=["recipient_user_id", "resource_kind", "resource_root", "resource_path"]),
        "responses": {"201": {"description": "Share grant requested"}, "401": {"description": "Unauthorized or missing CSRF"}},
    },
    "user_share_grant_approve": {
        "summary": "Owner-approve a pending share grant",
        "tags": ["user"],
        "requestBody": _openapi_json_body({"grant_id": {"type": "string"}}, required=["grant_id"]),
        "responses": {"200": {"description": "Share grant approved"}, "401": {"description": "Unauthorized or missing CSRF"}},
    },
    "user_share_grant_deny": {
        "summary": "Owner-deny a pending share grant",
        "tags": ["user"],
        "requestBody": _openapi_json_body({"grant_id": {"type": "string"}}, required=["grant_id"]),
        "responses": {"200": {"description": "Share grant denied"}, "401": {"description": "Unauthorized or missing CSRF"}},
    },
    "user_share_grant_accept": {
        "summary": "Accept an approved linked resource share",
        "tags": ["user"],
        "requestBody": _openapi_json_body({"grant_id": {"type": "string"}}, required=["grant_id"]),
        "responses": {"200": {"description": "Share accepted"}, "401": {"description": "Unauthorized or missing CSRF"}},
    },
    "user_share_grant_revoke": {
        "summary": "Owner-revoke a share grant",
        "tags": ["user"],
        "requestBody": _openapi_json_body({"grant_id": {"type": "string"}}, required=["grant_id"]),
        "responses": {"200": {"description": "Share revoked"}, "401": {"description": "Unauthorized or missing CSRF"}},
    },
    "user_linked_resources": {
        "summary": "Read accepted linked resources for the authenticated user",
        "tags": ["user"],
        "parameters": [_qparam("user_id")],
        "responses": {"200": {"description": "Linked resources"}, "401": {"description": "Unauthorized"}},
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
        "summary": "Read provider/model state plus sanitized Chutes budget, credential-lifecycle, and threshold policy boundary (admin)",
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
        "summary": "Read provider/model state plus sanitized Chutes budget, credential-lifecycle, and threshold policy boundary (user)",
        "tags": ["user"],
        "responses": {"200": {"description": "Provider state"}, "401": {"description": "Unauthorized"}},
    },
    "onboarding_claim_session": {
        "summary": "Claim user session after paid onboarding",
        "tags": ["onboarding"],
        "requestBody": _openapi_json_body({
            "session_id": {"type": "string"},
        }, required=["session_id"]),
        "responses": {
            "201": {"description": "User session created with Set-Cookie"},
            "402": {"description": "Entitlement not yet paid"},
            "404": {"description": "Onboarding session not found"},
        },
    },
    "onboarding_cancel": {
        "summary": "Cancel an onboarding session",
        "tags": ["onboarding"],
        "requestBody": _openapi_json_body({
            "session_id": {"type": "string"},
        }, required=["session_id"]),
        "responses": {"200": {"description": "Session cancelled or already final"}, "404": {"description": "Session not found"}},
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
    ("GET", "/user/credentials"): "user_credentials",
    ("POST", "/user/credentials/acknowledge"): "user_credential_ack",
    ("POST", "/user/share-grants"): "user_share_grant_create",
    ("POST", "/user/share-grants/approve"): "user_share_grant_approve",
    ("POST", "/user/share-grants/deny"): "user_share_grant_deny",
    ("POST", "/user/share-grants/accept"): "user_share_grant_accept",
    ("POST", "/user/share-grants/revoke"): "user_share_grant_revoke",
    ("GET", "/user/linked-resources"): "user_linked_resources",
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
    ("GET", "/onboarding/status"): "onboarding_status",
    ("POST", "/onboarding/claim-session"): "onboarding_claim_session",
    ("POST", "/onboarding/cancel"): "onboarding_cancel",
    ("GET", "/adapter-mode"): "adapter_mode",
    ("GET", "/health"): "health",
    ("GET", "/openapi.json"): "openapi_spec",
}

# Routes that require no session authentication (public endpoints)
_PUBLIC_ROUTES = frozenset({
    "public_onboarding_start",
    "public_onboarding_answer",
    "public_onboarding_checkout",
    "onboarding_status",
    "onboarding_claim_session",
    "onboarding_cancel",
    "adapter_mode",
    "stripe_webhook",
    "telegram_webhook",
    "discord_webhook",
    "admin_login",
    "user_login",
    "health",
    "openapi_spec",
})

_CIDR_PROTECTED_ROUTES = frozenset({
    "admin_login",
    "admin_logout",
    "admin_dashboard",
    "admin_service_health",
    "admin_provisioning_jobs",
    "admin_dns_drift",
    "admin_audit",
    "admin_events",
    "admin_queued_actions",
    "admin_action",
    "admin_reconciliation",
    "admin_provider_state",
    "session_revoke",
    "admin_operator_snapshot",
    "admin_scale_operations",
    "adapter_mode",
})

_JSON_OBJECT_ROUTES = frozenset({
    "public_onboarding_start",
    "public_onboarding_answer",
    "public_onboarding_checkout",
    "telegram_webhook",
    "admin_login",
    "user_login",
    "user_logout",
    "admin_logout",
    "user_portal_link",
    "user_credential_ack",
    "user_share_grant_create",
    "user_share_grant_approve",
    "user_share_grant_deny",
    "user_share_grant_accept",
    "user_share_grant_revoke",
    "admin_action",
    "session_revoke",
    "onboarding_claim_session",
    "onboarding_cancel",
})


def _allowed_methods_for_path(route_path: str) -> list[str]:
    return sorted(method for (method, path_suffix), _route_key in _ROUTES.items() if path_suffix == route_path)


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
    remote_addr: str = "",
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

    # Strip API prefix
    if clean_path.startswith(HOSTED_API_PREFIX):
        route_path = clean_path[len(HOSTED_API_PREFIX):]
    else:
        route_path = clean_path

    # CORS preflight
    if clean_method == "OPTIONS":
        allowed_methods = _allowed_methods_for_path(route_path)
        if not allowed_methods:
            return _response_with_cors(
                _json_response(404, {"error": "not_found"}, request_id=request_id),
                cfg,
            )
        requested_method = _api_header(headers, "access-control-request-method").upper()
        allow_value = ", ".join([*allowed_methods, "OPTIONS"])
        preflight_headers = [("Content-Length", "0"), ("Allow", allow_value), *_cors_headers(cfg)]
        if requested_method and requested_method not in allowed_methods:
            return 405, {}, preflight_headers
        return 204, {}, preflight_headers

    route_key = _ROUTES.get((clean_method, route_path))
    if route_key is None:
        return _response_with_cors(
            _json_response(404, {"error": "not_found"}, request_id=request_id),
            cfg,
        )

    body_limit = _route_body_limit(cfg, route_key)
    if body and _body_size_bytes(body) > body_limit:
        return _response_with_cors(
            _json_response(413, {"error": "body_too_large", "request_id": request_id}, request_id=request_id),
            cfg,
        )

    if route_key in _CIDR_PROTECTED_ROUTES:
        client_ip = _remote_ip_from_headers(cfg, headers, remote_addr)
        if not _backend_client_allowed(cfg, client_ip):
            logger.warning(
                "api_cidr_denied method=%s path=%s route=%s remote_ip=%s request_id=%s",
                clean_method, route_path, route_key, client_ip, request_id,
            )
            return _response_with_cors(
                _json_response(403, {"error": "forbidden", "request_id": request_id}, request_id=request_id),
                cfg,
            )

    start = time.monotonic()
    try:
        if route_key in {"stripe_webhook", "telegram_webhook", "discord_webhook"}:
            _check_webhook_rate_limit(
                conn,
                config=cfg,
                route_key=route_key,
                headers=headers,
                remote_addr=remote_addr,
            )
        parsed_body = _json_body(body) if route_key in _JSON_OBJECT_ROUTES else {}
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
            result = _handle_telegram_webhook(conn, parsed_body, request_id, cfg, stripe, headers=headers)
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
        elif route_key == "user_credentials":
            result = _handle_user_credentials(conn, headers, clean_query, request_id, cfg)
        elif route_key == "user_credential_ack":
            result = _handle_user_credential_ack(conn, headers, parsed_body, request_id, cfg)
        elif route_key == "user_share_grant_create":
            result = _handle_user_share_grant_create(conn, headers, parsed_body, request_id, cfg)
        elif route_key == "user_share_grant_approve":
            result = _handle_user_share_grant_approve(conn, headers, parsed_body, request_id, cfg)
        elif route_key == "user_share_grant_deny":
            result = _handle_user_share_grant_deny(conn, headers, parsed_body, request_id, cfg)
        elif route_key == "user_share_grant_accept":
            result = _handle_user_share_grant_accept(conn, headers, parsed_body, request_id, cfg)
        elif route_key == "user_share_grant_revoke":
            result = _handle_user_share_grant_revoke(conn, headers, parsed_body, request_id, cfg)
        elif route_key == "user_linked_resources":
            result = _handle_user_linked_resources(conn, headers, clean_query, request_id, cfg)
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
        elif route_key == "onboarding_status":
            result = _handle_onboarding_status(conn, clean_query, request_id)
        elif route_key == "onboarding_claim_session":
            result = _handle_onboarding_claim_session(conn, parsed_body, request_id, cfg)
        elif route_key == "onboarding_cancel":
            result = _handle_onboarding_cancel(conn, parsed_body, request_id)
        elif route_key == "adapter_mode":
            result = _handle_adapter_mode(cfg, request_id)
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

        return _response_with_cors(result, cfg)

    except HostedApiBodyError as exc:
        elapsed = time.monotonic() - start
        logger.warning(
            "api_body_error method=%s path=%s route=%s error=%s elapsed=%.3fs request_id=%s",
            clean_method, route_path, route_key, exc.code, elapsed, request_id,
        )
        return _response_with_cors(
            _json_response(exc.status, {"error": exc.code, "request_id": request_id}, request_id=request_id),
            cfg,
        )
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
        cors = _cors_headers(cfg)
        return _json_response(401, {"error": GENERIC_ARCLINK_AUTH_ERROR, "request_id": request_id}, request_id=request_id, extra_headers=cors)
    except StripeWebhookError as exc:
        elapsed = time.monotonic() - start
        logger.warning(
            "stripe_webhook_error path=%s error=%s elapsed=%.3fs request_id=%s",
            route_path, str(exc), elapsed, request_id,
        )
        cors = _cors_headers(cfg)
        return _json_response(400, {"error": str(exc), "request_id": request_id}, request_id=request_id, extra_headers=cors)
    except KeyError:
        cors = _cors_headers(cfg)
        return _json_response(404, {"error": "not_found", "request_id": request_id}, request_id=request_id, extra_headers=cors)
    except Exception:
        elapsed = time.monotonic() - start
        logger.exception(
            "api_error method=%s path=%s route=%s elapsed=%.3fs request_id=%s",
            clean_method, route_path, route_key, elapsed, request_id,
        )
        cors = _cors_headers(cfg)
        return _json_response(400, {"error": GENERIC_ARCLINK_API_ERROR, "request_id": request_id}, request_id=request_id, extra_headers=cors)


# --- WSGI adapter -------------------------------------------------------------


def make_arclink_hosted_api_wsgi(
    conn: sqlite3.Connection | None = None,
    *,
    config: HostedApiConfig | None = None,
    stripe_client: Any | None = None,
    db_config: Config | None = None,
    connect: Any | None = None,
) -> Any:
    """Return a WSGI application wrapping route_arclink_hosted_api."""
    cfg = config or HostedApiConfig()
    control_config = db_config or Config.from_env()
    connect_db_fn = connect or connect_db

    def app(environ: Mapping[str, Any], start_response: Any) -> list[bytes]:
        method = str(environ.get("REQUEST_METHOD", "GET"))
        path = str(environ.get("PATH_INFO", "/"))
        qs = str(environ.get("QUERY_STRING", ""))
        query = {k: v[0] for k, v in parse_qs(qs).items() if v}
        clean_method = method.upper()
        clean_path = path.rstrip("/")
        route_path = clean_path[len(HOSTED_API_PREFIX):] if clean_path.startswith(HOSTED_API_PREFIX) else clean_path
        route_key = _ROUTES.get((clean_method, route_path))
        body_limit = _route_body_limit(cfg, route_key) if route_key else cfg.max_body_bytes
        request_id = _request_id({
            key[5:].replace("_", "-").lower(): str(value or "")
            for key, value in dict(environ).items()
            if key.startswith("HTTP_")
        })

        try:
            length = int(str(environ.get("CONTENT_LENGTH") or "0") or 0)
        except ValueError:
            result = _response_with_cors(
                _json_response(400, {"error": "invalid_content_length", "request_id": request_id}, request_id=request_id),
                cfg,
            )
            status_code, payload, response_headers = result
            response_body = json.dumps(payload, sort_keys=True).encode("utf-8")
            start_response(_status_text(status_code), response_headers)
            return [response_body]
        if length > body_limit:
            result = _response_with_cors(
                _json_response(413, {"error": "body_too_large", "request_id": request_id}, request_id=request_id),
                cfg,
            )
            status_code, payload, response_headers = result
            response_body = json.dumps(payload, sort_keys=True).encode("utf-8")
            start_response(_status_text(status_code), response_headers)
            return [response_body]
        body = environ["wsgi.input"].read(length).decode("utf-8") if length else ""

        # Build headers dict from CGI environ
        headers: dict[str, str] = {}
        for key, value in dict(environ).items():
            if key.startswith("HTTP_"):
                header_name = key[5:].replace("_", "-").lower()
                headers[header_name] = str(value or "")
            elif key == "CONTENT_TYPE":
                headers["content-type"] = str(value or "")

        request_conn = conn or connect_db_fn(control_config)
        try:
            status_code, payload, response_headers = route_arclink_hosted_api(
                request_conn,
                method=method,
                path=path,
                headers=headers,
                body=body,
                query=query,
                config=cfg,
                stripe_client=stripe_client,
                remote_addr=str(environ.get("REMOTE_ADDR") or ""),
            )
        finally:
            if conn is None:
                request_conn.close()
        response_body = json.dumps(payload, sort_keys=True).encode("utf-8") if payload else b""
        start_response(_status_text(status_code), response_headers)
        return [response_body]

    return app


def _status_text(status_code: int) -> str:
    return {
        200: "200 OK",
        201: "201 Created",
        202: "202 Accepted",
        204: "204 No Content",
        400: "400 Bad Request",
        401: "401 Unauthorized",
        403: "403 Forbidden",
        404: "404 Not Found",
        413: "413 Payload Too Large",
        429: "429 Too Many Requests",
        500: "500 Internal Server Error",
        503: "503 Service Unavailable",
    }.get(status_code, f"{status_code} OK")


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
    app = make_arclink_hosted_api_wsgi(None, config=hosted_config, db_config=cfg)
    logger.info("ArcLink hosted API listening on %s:%s", host, port)
    with make_server(host, port, app) as server:
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
