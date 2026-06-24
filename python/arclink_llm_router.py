#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Mapping

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from arclink_chutes import (
    ChutesCatalogClient,
    ChutesCatalogError,
    evaluate_chutes_deployment_boundary,
    record_chutes_budget_policy_demotion,
    record_chutes_usage_event,
)
from arclink_boundary import json_dumps_safe
from arclink_control import (
    Config,
    ensure_schema,
    get_model_catalog_entry,
    latest_model_in_family,
    model_family_key,
    rate_limit_count,
    report_operator_hiccup,
    resolve_operator_hiccup,
    upsert_model_catalog,
    verify_llm_router_key,
)
from arclink_operator_agent import observe_unlimited_authorized
from arclink_secrets_regex import REDACTION_TEXT, contains_secret_material, redact_then_truncate


DEFAULT_CHUTES_BASE_URL = "https://llm.chutes.ai/v1"
DEFAULT_MODEL = "moonshotai/Kimi-K2.6-TEE"
DEFAULT_MAX_BODY_BYTES = 1024 * 1024
DEFAULT_PROMPT_ESTIMATE_TOKEN_CAP = 120000
DEFAULT_MAX_TOKENS_CAP = 8192
# C1 multi-completion fix: the chat payload is forwarded wholesale, so a caller
# can set ``n`` (and, where the upstream honors it, ``best_of``) to fan a single
# request into several completions -- each up to the per-completion output cap.
# The reservation must price the EFFECTIVE worst-case output (per-completion cap x
# the completion count), and the forwarded count must be clamped so it can never
# exceed what was priced. Default ceiling kept small.
DEFAULT_MAX_COMPLETIONS = 4
DEFAULT_DEPLOYMENT_CONCURRENCY_LIMIT = 4
DEFAULT_KEY_REQUESTS_PER_MINUTE = 60
DEFAULT_DEPLOYMENT_REQUESTS_PER_MINUTE = 120
DEFAULT_USER_REQUESTS_PER_MINUTE = 300
DEFAULT_MIN_RESERVATION_CENTS = 1
DEFAULT_INPUT_CENTS_PER_MILLION = 95
DEFAULT_OUTPUT_CENTS_PER_MILLION = 400
DEFAULT_UPSTREAM_CONNECT_TIMEOUT_SECONDS = 5
DEFAULT_UPSTREAM_READ_TIMEOUT_SECONDS = 300
DEFAULT_UPSTREAM_WRITE_TIMEOUT_SECONDS = 30
DEFAULT_UPSTREAM_POOL_TIMEOUT_SECONDS = 5
DEFAULT_UPSTREAM_MAX_CONNECTIONS = 256
DEFAULT_UPSTREAM_MAX_KEEPALIVE_CONNECTIONS = 64
DEFAULT_UPSTREAM_KEEPALIVE_EXPIRY_SECONDS = 90
DEFAULT_SQLITE_BUSY_TIMEOUT_MS = 15000
_SQLITE_SCHEMA_LOCK = threading.Lock()


def _truthy(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized == "":
        return default
    return normalized in {"1", "true", "yes", "on"}


def _clean_csv(value: str | None) -> tuple[str, ...]:
    items = [item.strip() for item in str(value or "").split(",")]
    return tuple(item for item in items if item)


def _clean_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return int(default)


def _env_text(source: Mapping[str, str], *keys: str, default: str = "") -> str:
    for key in keys:
        value = str(source.get(key) or "").strip()
        if value:
            return value
    return str(default).strip()


def _bounded_env_int(source: Mapping[str, str], key: str, default: int, *, minimum: int) -> int:
    return max(minimum, _clean_int(source.get(key), default))


@dataclass(frozen=True)
class RouterConfig:
    enabled: bool
    db_path: str
    chutes_base_url: str
    chutes_api_key: str
    default_model: str
    allowed_models: tuple[str, ...]
    fallback_models: tuple[str, ...]
    fallback_status_codes: tuple[int, ...]
    model_auto_promote: bool
    model_replacements: Mapping[str, str]
    refresh_model_catalog_on_startup: bool
    mark_missing_models_unavailable: bool
    model_catalog_auth_strategy: str
    max_body_bytes: int
    prompt_estimate_token_cap: int
    max_tokens_cap: int
    max_completions: int
    deployment_concurrency_limit: int
    key_requests_per_minute: int
    deployment_requests_per_minute: int
    user_requests_per_minute: int
    min_reservation_cents: int
    default_monthly_budget_cents: int
    input_cents_per_million: int
    output_cents_per_million: int
    upstream_connect_timeout_seconds: int
    upstream_read_timeout_seconds: int
    upstream_write_timeout_seconds: int
    upstream_pool_timeout_seconds: int
    upstream_max_connections: int
    upstream_max_keepalive_connections: int
    upstream_keepalive_expiry_seconds: int
    upstream_warmup_enabled: bool
    allow_inactive_models: bool

    @property
    def configured(self) -> bool:
        if not self.enabled:
            return True
        return bool(self.chutes_api_key.strip()) and bool(self.db_path.strip())

    def public_status(self) -> dict[str, Any]:
        status = "ok" if self.configured else "unhealthy"
        if not self.enabled:
            status = "disabled"
        return {
            "service": "arclink-llm-router",
            "status": status,
            "enabled": self.enabled,
            "configured": self.configured,
            "chutes_base_url": self.chutes_base_url,
            "db_configured": bool(self.db_path.strip()),
            "model_count": len(self.allowed_models),
            "fallback_model_count": len(self.fallback_models),
            "model_auto_promote": self.model_auto_promote,
            "model_catalog_refresh_on_startup": self.refresh_model_catalog_on_startup,
            "upstream_pool": {
                "max_connections": self.upstream_max_connections,
                "max_keepalive_connections": min(self.upstream_max_connections, self.upstream_max_keepalive_connections),
                "keepalive_expiry_seconds": self.upstream_keepalive_expiry_seconds,
                "connect_timeout_seconds": self.upstream_connect_timeout_seconds,
                "read_timeout_seconds": self.upstream_read_timeout_seconds,
                "write_timeout_seconds": self.upstream_write_timeout_seconds,
                "pool_timeout_seconds": self.upstream_pool_timeout_seconds,
                "warmup_enabled": self.upstream_warmup_enabled,
            },
        }


def load_router_config(env: Mapping[str, str] | None = None) -> RouterConfig:
    source = os.environ if env is None else env
    chutes_key = _env_text(source, "ARCLINK_LLM_ROUTER_CHUTES_API_KEY")
    default_model = _env_text(
        source,
        "ARCLINK_LLM_ROUTER_DEFAULT_MODEL",
        "ARCLINK_CHUTES_DEFAULT_MODEL",
        default=DEFAULT_MODEL,
    )
    allowed_models = _clean_csv(source.get("ARCLINK_LLM_ROUTER_ALLOWED_MODELS"))
    if not allowed_models:
        allowed_models = (default_model,)
    fallback_models = _clean_csv(source.get("ARCLINK_LLM_ROUTER_FALLBACK_MODELS"))
    fallback_status_codes: list[int] = []
    for item in _clean_csv(source.get("ARCLINK_LLM_ROUTER_FALLBACK_STATUS_CODES")):
        try:
            code = int(item)
        except ValueError:
            continue
        if 400 <= code <= 599 and code not in fallback_status_codes:
            fallback_status_codes.append(code)
    if not fallback_status_codes:
        fallback_status_codes = [429, 500, 502, 503, 504]
    replacements: dict[str, str] = {}
    for item in _clean_csv(source.get("ARCLINK_LLM_ROUTER_MODEL_REPLACEMENTS")):
        old, sep, new = item.partition("=")
        if sep and old.strip() and new.strip():
            replacements[old.strip()] = new.strip()
    return RouterConfig(
        enabled=_truthy(source.get("ARCLINK_LLM_ROUTER_ENABLED"), default=True),
        db_path=_env_text(source, "ARCLINK_DB_PATH"),
        chutes_base_url=_env_text(source, "ARCLINK_LLM_ROUTER_CHUTES_BASE_URL", default=DEFAULT_CHUTES_BASE_URL).rstrip("/"),
        chutes_api_key=chutes_key,
        default_model=default_model,
        allowed_models=allowed_models,
        fallback_models=fallback_models,
        fallback_status_codes=tuple(fallback_status_codes),
        model_auto_promote=_truthy(source.get("ARCLINK_LLM_ROUTER_MODEL_AUTO_PROMOTE"), default=True),
        model_replacements=replacements,
        refresh_model_catalog_on_startup=_truthy(
            source.get("ARCLINK_LLM_ROUTER_REFRESH_MODEL_CATALOG_ON_STARTUP"),
            default=True,
        ),
        mark_missing_models_unavailable=_truthy(
            source.get("ARCLINK_LLM_ROUTER_MARK_MISSING_MODELS_UNAVAILABLE"),
            default=True,
        ),
        model_catalog_auth_strategy=_env_text(
            source,
            "ARCLINK_LLM_ROUTER_MODEL_CATALOG_AUTH_STRATEGY",
            default="bearer",
        ).lower(),
        max_body_bytes=_bounded_env_int(source, "ARCLINK_LLM_ROUTER_MAX_BODY_BYTES", DEFAULT_MAX_BODY_BYTES, minimum=1),
        prompt_estimate_token_cap=_bounded_env_int(
            source,
            "ARCLINK_LLM_ROUTER_PROMPT_ESTIMATE_TOKEN_CAP",
            DEFAULT_PROMPT_ESTIMATE_TOKEN_CAP,
            minimum=1,
        ),
        max_tokens_cap=_bounded_env_int(source, "ARCLINK_LLM_ROUTER_MAX_TOKENS_CAP", DEFAULT_MAX_TOKENS_CAP, minimum=1),
        max_completions=_bounded_env_int(
            source,
            "ARCLINK_LLM_ROUTER_MAX_COMPLETIONS",
            DEFAULT_MAX_COMPLETIONS,
            minimum=1,
        ),
        deployment_concurrency_limit=_bounded_env_int(
            source,
            "ARCLINK_LLM_ROUTER_DEPLOYMENT_CONCURRENCY_LIMIT",
            DEFAULT_DEPLOYMENT_CONCURRENCY_LIMIT,
            minimum=1,
        ),
        key_requests_per_minute=_bounded_env_int(
            source,
            "ARCLINK_LLM_ROUTER_KEY_REQUESTS_PER_MINUTE",
            DEFAULT_KEY_REQUESTS_PER_MINUTE,
            minimum=0,
        ),
        deployment_requests_per_minute=_bounded_env_int(
            source,
            "ARCLINK_LLM_ROUTER_DEPLOYMENT_REQUESTS_PER_MINUTE",
            DEFAULT_DEPLOYMENT_REQUESTS_PER_MINUTE,
            minimum=0,
        ),
        user_requests_per_minute=_bounded_env_int(
            source,
            "ARCLINK_LLM_ROUTER_USER_REQUESTS_PER_MINUTE",
            DEFAULT_USER_REQUESTS_PER_MINUTE,
            minimum=0,
        ),
        min_reservation_cents=_bounded_env_int(
            source,
            "ARCLINK_LLM_ROUTER_MIN_RESERVATION_CENTS",
            DEFAULT_MIN_RESERVATION_CENTS,
            minimum=1,
        ),
        default_monthly_budget_cents=_bounded_env_int(
            source,
            "ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS",
            0,
            minimum=0,
        ),
        input_cents_per_million=_bounded_env_int(
            source,
            "ARCLINK_LLM_ROUTER_CENTS_PER_MILLION_INPUT_TOKENS",
            DEFAULT_INPUT_CENTS_PER_MILLION,
            minimum=0,
        ),
        output_cents_per_million=_bounded_env_int(
            source,
            "ARCLINK_LLM_ROUTER_CENTS_PER_MILLION_OUTPUT_TOKENS",
            DEFAULT_OUTPUT_CENTS_PER_MILLION,
            minimum=0,
        ),
        upstream_connect_timeout_seconds=_bounded_env_int(
            source,
            "ARCLINK_LLM_ROUTER_UPSTREAM_CONNECT_TIMEOUT_SECONDS",
            DEFAULT_UPSTREAM_CONNECT_TIMEOUT_SECONDS,
            minimum=1,
        ),
        upstream_read_timeout_seconds=_bounded_env_int(
            source,
            "ARCLINK_LLM_ROUTER_UPSTREAM_READ_TIMEOUT_SECONDS",
            DEFAULT_UPSTREAM_READ_TIMEOUT_SECONDS,
            minimum=1,
        ),
        upstream_write_timeout_seconds=_bounded_env_int(
            source,
            "ARCLINK_LLM_ROUTER_UPSTREAM_WRITE_TIMEOUT_SECONDS",
            DEFAULT_UPSTREAM_WRITE_TIMEOUT_SECONDS,
            minimum=1,
        ),
        upstream_pool_timeout_seconds=_bounded_env_int(
            source,
            "ARCLINK_LLM_ROUTER_UPSTREAM_POOL_TIMEOUT_SECONDS",
            DEFAULT_UPSTREAM_POOL_TIMEOUT_SECONDS,
            minimum=1,
        ),
        upstream_max_connections=_bounded_env_int(
            source,
            "ARCLINK_LLM_ROUTER_UPSTREAM_MAX_CONNECTIONS",
            DEFAULT_UPSTREAM_MAX_CONNECTIONS,
            minimum=1,
        ),
        upstream_max_keepalive_connections=_bounded_env_int(
            source,
            "ARCLINK_LLM_ROUTER_UPSTREAM_MAX_KEEPALIVE_CONNECTIONS",
            DEFAULT_UPSTREAM_MAX_KEEPALIVE_CONNECTIONS,
            minimum=0,
        ),
        upstream_keepalive_expiry_seconds=_bounded_env_int(
            source,
            "ARCLINK_LLM_ROUTER_UPSTREAM_KEEPALIVE_EXPIRY_SECONDS",
            DEFAULT_UPSTREAM_KEEPALIVE_EXPIRY_SECONDS,
            minimum=1,
        ),
        upstream_warmup_enabled=_truthy(source.get("ARCLINK_LLM_ROUTER_UPSTREAM_WARMUP_ENABLED"), default=True),
        # H2 break-glass: forward catalog-inactive models (incident response only).
        allow_inactive_models=_truthy(source.get("ARCLINK_LLM_ROUTER_ALLOW_INACTIVE_MODELS"), default=False),
    )


def _router_error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "message": message,
                "type": "arclink_router_error",
                "code": code,
            }
        },
    )


def _require_configured(config: RouterConfig) -> JSONResponse | None:
    if config.configured:
        return None
    return _router_error(
        503,
        "router_misconfigured",
        "ArcLink LLM router is enabled but the upstream provider credential is not configured.",
    )


def _open_control_conn(config: RouterConfig) -> sqlite3.Connection:
    conn = sqlite3.connect(config.db_path, timeout=DEFAULT_SQLITE_BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {DEFAULT_SQLITE_BUSY_TIMEOUT_MS}")
    with _SQLITE_SCHEMA_LOCK:
        ensure_schema(conn)
    return conn


# Floor below which a startup /models response is considered untrustworthy.
# An empty or near-empty successful response (e.g. ``data: []``) must NOT be
# allowed to mark every active row unavailable -- that would silently empty the
# DB-backed allow-list with no notice. This mirrors the last-known-good guard in
# the arclink-llm-model-sync worker.
_STARTUP_REFRESH_MIN_MODELS = 1


def _refresh_model_catalog_once(config: RouterConfig, *, http_client: Any | None = None) -> dict[str, Any]:
    if not config.enabled:
        return {"status": "skipped", "reason": "router_disabled"}
    if not config.configured:
        return {"status": "skipped", "reason": "router_not_configured"}
    strategy = config.model_catalog_auth_strategy
    if strategy not in {"bearer", "x-api-key", "none"}:
        strategy = "bearer"
    catalog = ChutesCatalogClient(http_client, base_url=config.chutes_base_url)
    models = catalog.list_models(
        api_key="" if strategy == "none" else config.chutes_api_key,
        auth_strategy="x-api-key" if strategy == "x-api-key" else "bearer",
    )
    # Last-known-good guard: a successful-but-empty/too-few result must not reach
    # upsert_model_catalog with mark_missing_unavailable, which would flip every
    # active row to unavailable and empty the router's effective allow-list. The
    # hourly arclink-llm-model-sync worker owns the authoritative refresh (with
    # operator notification); here we simply refuse to destroy last-known-good.
    fetched = len(models)
    if fetched < _STARTUP_REFRESH_MIN_MODELS:
        return {
            "status": "skipped",
            "reason": "too_few_models",
            "model_count": fetched,
            "kept_last_known_good": True,
            "auth_strategy": strategy,
        }
    # This best-effort startup refresh only ADDS/UPDATES catalog rows; it never
    # marks any model unavailable. The hourly arclink-llm-model-sync worker is the
    # sole authority that removes -TEE models, and it does so behind its own
    # floor + proportional-drop guards computed on the -TEE subset.
    #
    # Why this is the robust fix: the count/floor guard above is on ALL Chutes
    # models, but the router's effective allow-list reads only
    # ``model_id LIKE '%-TEE'`` (see ``_synced_global_allowed_models``). A /models
    # response with plenty of non-TEE models but zero (or few) -TEE models would
    # clear that all-models guard, then ``mark_missing_unavailable=True`` would flip
    # every active -TEE row to unavailable and EMPTY the allow-list (GLM/Kimi gone)
    # with no operator notice. Forcing mark-missing OFF here makes startup purely
    # additive, so a partial / TEE-light response can never drop GLM-5.x-TEE or
    # Kimi-K2.x-TEE from the allow-list. Destructive removals stay with the guarded,
    # operator-notifying sync worker (which guards on the -TEE subset specifically).
    mark_missing = False
    conn = _open_control_conn(config)
    try:
        rows = upsert_model_catalog(
            conn,
            provider="chutes",
            models=models,
            mark_missing_unavailable=mark_missing,
        )
    finally:
        conn.close()
    return {
        "status": "ok",
        "model_count": len(rows),
        "mark_missing_unavailable": mark_missing,
        "auth_strategy": strategy,
    }


def _extract_bearer_token(request: Request) -> str:
    header = str(request.headers.get("authorization") or "").strip()
    if not header:
        return ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return ""
    return token.strip()


def _authenticate_request(config: RouterConfig, request: Request) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    raw_key = _extract_bearer_token(request)
    if not raw_key:
        return None, _router_error(401, "missing_bearer_token", "ArcLink LLM router requires a Bearer token.")
    try:
        conn = _open_control_conn(config)
        try:
            record = verify_llm_router_key(conn, raw_key)
        finally:
            conn.close()
    except sqlite3.Error:
        return None, _router_error(503, "router_db_unavailable", "ArcLink LLM router key database is unavailable.")
    except ValueError:
        # regr-M5: the fail-closed router-key pepper guard raises ValueError when a
        # real pepper is required (or in a prod domain) but unconfigured. Treat that
        # as a clean 503 misconfiguration instead of letting it surface as a 500.
        return None, _router_error(503, "router_misconfigured", "ArcLink LLM router key verification is misconfigured.")
    if record is None:
        return None, _router_error(401, "invalid_router_key", "ArcLink LLM router key is invalid or inactive.")
    return record, None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_deployment_context(
    conn: sqlite3.Connection,
    auth_record: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    row = conn.execute(
        """
        SELECT d.metadata_json, d.status AS deployment_status, u.entitlement_state
        FROM arclink_deployments d
        LEFT JOIN arclink_users u ON u.user_id = d.user_id
        WHERE d.deployment_id = ? AND d.user_id = ?
        """,
        (str(auth_record.get("deployment_id") or ""), str(auth_record.get("user_id") or "")),
    ).fetchone()
    if row is None:
        return {}, "none"
    metadata = {}
    try:
        import json

        loaded = json.loads(str(row["metadata_json"] or "{}"))
        if isinstance(loaded, dict):
            metadata = loaded
    except Exception:
        metadata = {}
    deployment_status = str(row["deployment_status"] or "").strip().lower()
    if deployment_status in {
        "reserved",
        "entitlement_required",
        "provisioning_ready",
        "provisioning",
        "provisioning_failed",
        "teardown_requested",
        "teardown_running",
        "teardown_complete",
        "teardown_failed",
        "torn_down",
        "cancelled",
    }:
        chutes_meta = dict(metadata.get("chutes") if isinstance(metadata.get("chutes"), dict) else {})
        chutes_meta.update({
            "status": "suspended",
            "suspended": True,
            "suspended_reason": f"deployment_{deployment_status}",
        })
        metadata["chutes"] = chutes_meta
        metadata["deployment_status"] = deployment_status
    subscription = conn.execute(
        """
        SELECT status
        FROM arclink_subscriptions
        WHERE user_id = ?
        ORDER BY updated_at DESC, created_at DESC
        LIMIT 1
        """,
        (str(auth_record.get("user_id") or ""),),
    ).fetchone()
    if subscription is not None:
        status = str(subscription["status"] or "").strip().lower()
        if status in {"active", "trialing", "paid"}:
            return metadata, "paid"
        return metadata, status or "none"
    entitlement = str(row["entitlement_state"] or "").strip().lower()
    return metadata, entitlement if entitlement in {"paid", "comp"} else "none"


def _router_boundary_metadata(metadata: Mapping[str, Any], auth_record: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(metadata or {})
    chutes_meta = dict(merged.get("chutes") if isinstance(merged.get("chutes"), dict) else {})
    if not str(chutes_meta.get("secret_ref") or "").strip():
        chutes_meta["secret_ref"] = str(auth_record.get("secret_ref") or "")
    if not str(chutes_meta.get("key_id") or "").strip():
        chutes_meta["key_id"] = str(auth_record.get("key_id") or "")
    merged["chutes"] = chutes_meta
    return merged


def _json_error(status_code: int, code: str, message: str, *, retry_after: int = 0) -> JSONResponse:
    response = _router_error(status_code, code, message)
    if retry_after > 0:
        response.headers["Retry-After"] = str(retry_after)
    return response


async def _read_json_body(config: RouterConfig, request: Request) -> tuple[dict[str, Any] | None, JSONResponse | None, bytes]:
    content_length = request.headers.get("content-length")
    if content_length and _clean_int(content_length, 0) > config.max_body_bytes:
        return None, _router_error(413, "request_body_too_large", "ArcLink LLM router request body is too large."), b""
    chunks = bytearray()
    async for chunk in request.stream():
        if not chunk:
            continue
        if len(chunks) + len(chunk) > config.max_body_bytes:
            return None, _router_error(413, "request_body_too_large", "ArcLink LLM router request body is too large."), bytes(chunks)
        chunks.extend(chunk)
    body = bytes(chunks)
    if len(body) > config.max_body_bytes:
        return None, _router_error(413, "request_body_too_large", "ArcLink LLM router request body is too large."), body
    try:
        import json

        payload = json.loads(body.decode("utf-8") if body else "{}")
    except Exception:
        return None, _router_error(400, "invalid_json", "ArcLink LLM router requires a JSON request body."), body
    if not isinstance(payload, dict):
        return None, _router_error(400, "invalid_json", "ArcLink LLM router request body must be a JSON object."), body
    return payload, None, body


def _estimate_prompt_tokens(payload: Mapping[str, Any], body: bytes) -> int:
    if body:
        return max(1, (len(body) + 3) // 4)
    return max(1, len(str(payload)) // 4)


_MAX_OUTPUT_TOKEN_KEYS = ("max_tokens", "max_completion_tokens")
# C1 multi-completion fix: keys that fan one request into multiple sampled
# completions, multiplying the worst-case output. ``n`` is the OpenAI-compatible
# chat-completions multiplier (the Chutes ``/v1/chat/completions`` endpoint
# honors it). ``best_of`` is a legacy text-completions param that the OpenAI chat
# endpoint rejects rather than honors -- but since the router forwards the payload
# wholesale we price (and clamp) defensively against the larger of the two so an
# upstream that DID honor ``best_of`` could never settle more output than reserved.
_COMPLETION_MULTIPLIER_KEYS = ("n", "best_of")


def _requested_completions(payload: Mapping[str, Any]) -> int:
    """Worst-case number of sampled completions the payload would fan into.

    The reservation must price ``per-completion output cap x this count``. Takes
    the MAX usable value across the multiplier keys (the largest fan-out the
    caller expressed); defaults to 1 when no key carries a usable positive value.
    """
    usable = [
        value
        for name in _COMPLETION_MULTIPLIER_KEYS
        if name in payload
        for value in (_usable_positive_int(payload.get(name)),)
        if value > 0
    ]
    return max(usable) if usable else 1


def _effective_completions(config: RouterConfig, payload: Mapping[str, Any]) -> int:
    """Completion count clamped into ``1..config.max_completions``.

    Both the reservation pricing and the forwarded payload use this single value
    so the forwarded fan-out can never exceed what was priced.
    """
    return max(1, min(int(config.max_completions), _requested_completions(payload)))


def _usable_positive_int(value: Any) -> int:
    """Return ``value`` as a positive int, or 0 when it is not a usable cap.

    ``null``, booleans, non-numeric strings, and non-positive numbers all map to
    0 so the caller can treat them as "no usable output cap" (omitted) rather than
    an unbounded request. Mirrors ``_clean_int`` but rejects bool/None up front.
    """
    if value is None or isinstance(value, bool):
        return 0
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _requested_max_tokens(payload: Mapping[str, Any]) -> int:
    """Effective requested output cap across ALL max-output keys.

    Round-3 fix: a caller can send several max-output keys at once
    (``max_tokens`` AND ``max_completion_tokens``). The old "first present key"
    logic let ``{max_tokens: null, max_completion_tokens: 999999}`` (or
    ``{max_tokens: 64, max_completion_tokens: 999999}``) bypass the preflight cap
    check and underprice the reservation. The EFFECTIVE requested cap is the MIN of
    the usable positive values across every key (the tightest bound the caller
    actually expressed); 0 ("no usable cap") only when NO key carries a usable
    positive value, in which case the caller prices the bounded reservation default.
    """
    usable = [
        value
        for name in _MAX_OUTPUT_TOKEN_KEYS
        if name in payload
        for value in (_usable_positive_int(payload.get(name)),)
        if value > 0
    ]
    return min(usable) if usable else 0


def _model_price_cents(config: RouterConfig, catalog_entry: Mapping[str, Any] | None) -> tuple[int, int, str]:
    if catalog_entry:
        input_cents = _clean_int(catalog_entry.get("input_cents_per_million"), 0)
        output_cents = _clean_int(catalog_entry.get("output_cents_per_million"), 0)
        if input_cents > 0 and output_cents > 0:
            return input_cents, output_cents, "catalog"
    return config.input_cents_per_million, config.output_cents_per_million, "router_default"


def _estimate_reservation_cents_for_model(
    config: RouterConfig,
    catalog_entry: Mapping[str, Any] | None,
    input_tokens: int,
    max_tokens: int,
    completions: int = 1,
) -> int:
    input_cents, output_cents, _ = _model_price_cents(config, catalog_entry)
    per_completion_output = max_tokens if max_tokens > 0 else min(config.max_tokens_cap, 1024)
    # C1 multi-completion fix: the prompt is sent once but ``n`` (or ``best_of``)
    # samples the output ``completions`` times, so the worst-case BILLED output is
    # the per-completion cap x the completion count. Input is shared across samples.
    output_tokens = max(0, per_completion_output) * max(1, int(completions))
    estimated = ((max(0, input_tokens) * input_cents) + (output_tokens * output_cents) + 999999) // 1000000
    return max(config.min_reservation_cents, int(estimated))


def _estimate_usage_cents(config: RouterConfig, input_tokens: int, output_tokens: int, catalog_entry: Mapping[str, Any] | None = None) -> int:
    input_cents, output_cents, _ = _model_price_cents(config, catalog_entry)
    estimated = (
        (max(0, input_tokens) * input_cents)
        + (max(0, output_tokens) * output_cents)
        + 999999
    ) // 1000000
    return max(0, int(estimated))


def _fallback_reservation_pricing(
    conn: sqlite3.Connection,
    config: RouterConfig,
    *,
    primary_model: str,
    primary_entry: Mapping[str, Any] | None,
    input_tokens: int,
    max_tokens: int,
    completions: int = 1,
    candidates: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    # ``candidates`` lets the caller price only the candidates that will actually
    # be forwarded (the allow-filtered list), so a disallowed fallback is neither
    # priced nor attempted. When omitted, fall back to the raw candidate list.
    candidate_models = candidates if candidates is not None else _router_fallback_candidates(config, primary_model)
    choices: list[dict[str, Any]] = []
    for model in candidate_models:
        entry = primary_entry if model == primary_model else get_model_catalog_entry(conn, provider="chutes", model_id=model)
        input_price, output_price, source = _model_price_cents(config, entry)
        choices.append(
            {
                "model": model,
                "reserved_cents": _estimate_reservation_cents_for_model(config, entry, input_tokens, max_tokens, completions),
                "pricing_source": source,
                "input_cents_per_million": input_price,
                "output_cents_per_million": output_price,
                "catalog_entry": dict(entry or {}),
            }
        )
    if not choices:
        input_price, output_price, source = _model_price_cents(config, primary_entry)
        choices.append(
            {
                "model": primary_model,
                "reserved_cents": _estimate_reservation_cents_for_model(config, primary_entry, input_tokens, max_tokens, completions),
                "pricing_source": source,
                "input_cents_per_million": input_price,
                "output_cents_per_million": output_price,
                "catalog_entry": dict(primary_entry or {}),
            }
        )
    selected = max(choices, key=lambda item: int(item.get("reserved_cents") or 0))
    return {
        "selected": selected,
        "choices": [
            {
                key: item[key]
                for key in (
                    "model",
                    "reserved_cents",
                    "pricing_source",
                    "input_cents_per_million",
                    "output_cents_per_million",
                )
            }
            for item in choices
        ],
    }


def _resolve_router_model(
    conn: sqlite3.Connection,
    config: RouterConfig,
    requested_model: str,
    allowed_models: tuple[str, ...],
) -> tuple[str, dict[str, Any] | None, dict[str, Any]]:
    requested = str(requested_model or "").strip()
    replacement_reason = ""
    replacement = str(config.model_replacements.get(requested) or "").strip()
    entry = get_model_catalog_entry(conn, provider="chutes", model_id=requested)
    if not replacement and entry and str(entry.get("replacement_model_id") or "").strip():
        replacement = str(entry.get("replacement_model_id") or "").strip()
        replacement_reason = f"catalog_{entry.get('status') or 'replacement'}"
    if not replacement and config.model_auto_promote:
        family = str((entry or {}).get("family") or "").strip() or model_family_key(requested)
        latest = latest_model_in_family(conn, provider="chutes", family=family)
        entry_status = str((entry or {}).get("status") or "missing")
        latest_sort = str((latest or {}).get("version_sort_key") or "")
        entry_sort = str((entry or {}).get("version_sort_key") or "")
        if (
            latest
            and str(latest.get("model_id") or "") != requested
            and (entry_status != "active" or (latest_sort and entry_sort and latest_sort > entry_sort))
        ):
            replacement = str(latest.get("model_id") or "")
            replacement_reason = "latest_family_model" if entry_status != "active" else "newer_family_model"
    if replacement:
        target_entry = get_model_catalog_entry(conn, provider="chutes", model_id=replacement)
        metadata = {
            "requested_model": requested,
            "upstream_model": replacement,
            "replacement_reason": replacement_reason or "env_replacement",
        }
        return replacement, target_entry, metadata
    return requested, entry, {"requested_model": requested, "upstream_model": requested, "replacement_reason": ""}


def _synced_global_allowed_models(conn: sqlite3.Connection) -> tuple[str, ...]:
    """Active confidential-compute (``-TEE``) models from the synced catalog.

    The ``arclink-llm-model-sync`` worker keeps ``arclink_model_catalog`` in
    sync with the Chutes ``-TEE`` catalog. Reading it here lets the router's
    effective global allow-list follow the synced set on the very next request
    without a restart (the worker never empties this set on failure). Returns an
    empty tuple if the table is unreadable or holds no active ``-TEE`` rows, so
    callers fall back to the static env allow-list.
    """
    try:
        rows = conn.execute(
            """
            SELECT model_id
            FROM arclink_model_catalog
            WHERE provider = 'chutes' AND status = 'active' AND model_id LIKE '%-TEE'
            ORDER BY model_id
            """
        ).fetchall()
    except sqlite3.Error:
        return ()
    models: list[str] = []
    for row in rows:
        model_id = str((row["model_id"] if isinstance(row, sqlite3.Row) else row[0]) or "").strip()
        if model_id and model_id not in models:
            models.append(model_id)
    return tuple(models)


def _effective_global_allowed_models(
    conn: sqlite3.Connection,
    config: RouterConfig,
) -> tuple[str, ...]:
    """Global allow-list the router enforces, preferring the synced catalog.

    Falls back to ``config.allowed_models`` (the static env list) so the
    allow-list is never empty even if the catalog is empty/unreadable.
    """
    synced = _synced_global_allowed_models(conn)
    return synced or config.allowed_models


def _synced_catalog_ever_succeeded(conn: sqlite3.Connection) -> bool:
    """True if the sync worker ever recorded a successful authoritative sync.

    Lets the router tell "no catalog yet" (cold start, env fallback is expected)
    apart from "catalog emptied during normal op" (a real collapse worth an
    operator alert). Anchored on the same ``llm_router:model_sync_ok`` audit
    action the sync worker writes.
    """
    try:
        row = conn.execute(
            """
            SELECT 1
            FROM arclink_audit_log
            WHERE action = 'llm_router:model_sync_ok'
            LIMIT 1
            """
        ).fetchone()
    except sqlite3.Error:
        return False
    return row is not None


def _router_allow_list_state(conn: sqlite3.Connection, config: RouterConfig) -> dict[str, Any]:
    """Operator-facing snapshot of the effective allow-list source.

    H3: distinguishes a synced catalog from the env fallback and flags a
    *collapse* -- the synced set emptying after a prior successful sync, which
    silently drops the router back to the env default-only list.
    """
    synced = _synced_global_allowed_models(conn)
    ever_synced = _synced_catalog_ever_succeeded(conn)
    using_fallback = not synced
    collapsed = using_fallback and ever_synced
    effective = synced or config.allowed_models
    return {
        "source": "synced_catalog" if synced else "env_fallback",
        "synced_model_count": len(synced),
        "effective_model_count": len(effective),
        "ever_synced": ever_synced,
        "synced_catalog_collapsed": collapsed,
    }


ALLOW_LIST_COLLAPSE_HICCUP_KEY = "llm_router_allow_list_collapsed"


def _report_allow_list_collapse(conn: sqlite3.Connection, state: Mapping[str, Any]) -> None:
    """Alert on allow-list collapse, and RESOLVE the alert on recovery.

    Best-effort and never raises into the request/health path. ``report_operator_hiccup``
    dedups on its audit key, so repeated health checks during the same outage do
    not spam.

    H3 rearm fix: the hiccup alert only re-arms when a matching
    ``resolve_operator_hiccup`` is recorded -- merely *stopping* reporting on
    recovery would leave the key armed forever, suppressing a SECOND collapse. So
    when the synced catalog is non-empty again (no collapse), resolve the key so a
    later collapse re-alerts.
    """
    try:
        cfg = Config.from_env()
    except Exception:
        return
    if not state.get("synced_catalog_collapsed"):
        # Recovered (or never collapsed): re-arm the alert. resolve_operator_hiccup
        # is a cheap no-op when the key is not currently armed.
        try:
            resolve_operator_hiccup(
                conn,
                cfg,
                source="llm_router",
                key=ALLOW_LIST_COLLAPSE_HICCUP_KEY,
                reason="synced -TEE catalog recovered (non-empty allow-list)",
            )
        except Exception:
            return
        return
    try:
        report_operator_hiccup(
            conn,
            cfg,
            source="llm_router",
            key=ALLOW_LIST_COLLAPSE_HICCUP_KEY,
            message=(
                "ArcLink LLM router allow-list COLLAPSED to the env default-only fallback: "
                "the synced -TEE catalog is now empty after a prior successful sync. Customers "
                "can only reach the default model until the catalog is restored."
            ),
            extra={
                "effective_model_count": int(state.get("effective_model_count") or 0),
                "synced_model_count": int(state.get("synced_model_count") or 0),
            },
        )
    except Exception:
        return


def _router_model_allowed(
    config: RouterConfig,
    model: str,
    allowed_models: tuple[str, ...],
    *,
    allow_default_model: bool = True,
) -> bool:
    clean_model = str(model or "").strip()
    if not clean_model:
        return False
    if clean_model in allowed_models:
        return True
    # Some providers accept a comma-bearing model string as provider-side
    # fallback. Preserve that as a single default model even when the allowlist
    # itself is represented as comma-separated values.
    return bool(allow_default_model and config.default_model and clean_model == config.default_model)


def _disallowed_router_model(
    config: RouterConfig,
    models: tuple[str, ...],
    allowed_models: tuple[str, ...],
    *,
    allow_default_model: bool,
) -> str:
    for model in models:
        if not _router_model_allowed(config, model, allowed_models, allow_default_model=allow_default_model):
            return model
    return ""


def _router_fallback_candidates(config: RouterConfig, primary_model: str) -> tuple[str, ...]:
    candidates: list[str] = []
    for model in (str(primary_model or "").strip(), *config.fallback_models):
        clean = str(model or "").strip()
        if clean and clean not in candidates:
            candidates.append(clean)
    return tuple(candidates)


def _allowed_router_fallback_candidates(
    conn: sqlite3.Connection,
    config: RouterConfig,
    primary_model: str,
    allowed_models: tuple[str, ...],
    *,
    allow_default_model: bool,
) -> tuple[str, ...]:
    """Outage fix: a configured fallback that is NOT allowed for this ArcPod (or
    is withdrawn from the catalog) must be SKIPPED, never fatal. Previously the
    preflight HARD-REJECTED the whole request (403 model_not_allowed) whenever ANY
    fallback was disallowed, so a key whose allow-list held only the PRIMARY (with
    a configured fallback that key could not use) 403'd on EVERY turn -- a total
    public-channel outage even though the allowed primary would have worked.

    The resolved primary is ALWAYS kept (its allow/catalog status is validated by
    ``_preflight_chat_request`` before this runs). Only the fallback positions are
    filtered: each must (a) be allowed for this ArcPod and (b) -- unless the
    break-glass ``allow_inactive_models`` env is set -- not have a non-active
    catalog row (matching the primary's H2 guard). This is the SAME list that the
    forward/stream loops iterate, so disallowed fallbacks are never attempted and
    never priced.
    """
    full = _router_fallback_candidates(config, primary_model)
    if not full:
        return full
    primary = full[0]
    kept: list[str] = [primary]
    for candidate in full[1:]:
        if candidate == primary:
            continue
        if not _router_model_allowed(config, candidate, allowed_models, allow_default_model=allow_default_model):
            continue
        if not config.allow_inactive_models:
            entry = get_model_catalog_entry(conn, provider="chutes", model_id=candidate)
            if entry is not None:
                status = str(entry.get("status") or "").strip().lower()
                if status and status != "active":
                    continue
        kept.append(candidate)
    return tuple(kept)


def _reservation_fallback_candidates(
    config: RouterConfig,
    reservation: Mapping[str, Any],
    upstream_model: str,
) -> tuple[str, ...]:
    """Return the candidate list the forward/stream loops should iterate.

    Prefers the allow-filtered list stashed on the reservation at preflight so a
    disallowed fallback is never attempted upstream. Falls back to the raw
    candidate list only if the field is absent/empty (e.g. a reservation created
    before this field existed), and always re-asserts that the primary leads.
    """
    stored = reservation.get("fallback_candidates")
    if isinstance(stored, (list, tuple)):
        cleaned = [str(m or "").strip() for m in stored if str(m or "").strip()]
        if cleaned:
            return tuple(dict.fromkeys(cleaned))
    return _router_fallback_candidates(config, upstream_model)


def _upstream_status_is_retryable(config: RouterConfig, status_code: int) -> bool:
    if int(status_code) in set(config.fallback_status_codes):
        return True
    return int(status_code) >= 500


def _safe_upstream_error(value: Any) -> str:
    redacted = redact_then_truncate(value, limit=300)
    if contains_secret_material(redacted, allow_safe_refs=False):
        return REDACTION_TEXT
    return redacted


def _metadata_json(metadata: Mapping[str, Any]) -> str:
    return json.dumps(dict(metadata or {}), sort_keys=True, separators=(",", ":"))


def _safe_metadata_json(metadata: Mapping[str, Any]) -> str:
    return json_dumps_safe(dict(metadata or {}), label="ArcLink LLM router metadata")


def _public_fallback_attempts(attempts: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    public: list[dict[str, Any]] = []
    for item in attempts:
        public.append(
            {
                "attempt_index": int(item.get("attempt_index") or len(public)),
                "model": str(item.get("attempted_model") or item.get("model") or ""),
                "status_code": int(item.get("status_code") or 0),
                "retryable": bool(item.get("retryable")),
                "outcome": str(item.get("outcome") or ""),
                "next_model": str(item.get("next_model") or ""),
            }
        )
    return public


def _router_metadata_for_response(
    *,
    requested_model: str,
    primary_model: str,
    final_model: str,
    fallback_attempts: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
    streaming_fallback: str = "",
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "requested_model": requested_model,
        "primary_model": primary_model,
        "upstream_model": final_model,
        "fallback_used": final_model != primary_model,
        "fallback_attempts": _public_fallback_attempts(fallback_attempts),
    }
    if streaming_fallback:
        metadata["streaming_fallback"] = streaming_fallback
    return metadata


def _sse_data(payload: Mapping[str, Any]) -> bytes:
    return ("data: " + json.dumps(dict(payload), sort_keys=True, separators=(",", ":")) + "\n\n").encode("utf-8")


def _fallback_attempt_metadata(
    *,
    reservation: Mapping[str, Any],
    auth_record: Mapping[str, Any],
    requested_model: str,
    primary_model: str,
    attempted_model: str,
    next_model: str,
    status_code: int,
    stream: bool,
    outcome: str,
    error_summary: str,
    attempt_index: int,
    retryable: bool,
) -> dict[str, Any]:
    return {
        "request_id": str(reservation.get("request_id") or ""),
        "deployment_id": str(auth_record.get("deployment_id") or reservation.get("deployment_id") or ""),
        "user_id": str(auth_record.get("user_id") or reservation.get("user_id") or ""),
        "provider": "chutes",
        "requested_model": requested_model,
        "primary_model": primary_model,
        "attempted_model": attempted_model,
        "next_model": next_model,
        "status_code": int(status_code),
        "retryable": bool(retryable),
        "stream": bool(stream),
        "outcome": outcome,
        "attempt_index": int(attempt_index),
        "error_summary": _safe_upstream_error(error_summary),
    }


def _record_fallback_attempt_event(config: RouterConfig, metadata: Mapping[str, Any]) -> None:
    try:
        conn = _open_control_conn(config)
        try:
            conn.execute(
                """
                INSERT INTO arclink_events (event_id, subject_kind, subject_id, event_type, metadata_json, created_at)
                VALUES (?, 'deployment', ?, 'llm_router:fallback_attempt', ?, ?)
                """,
                (
                    f"evt_{uuid.uuid4().hex}",
                    str(metadata.get("deployment_id") or ""),
                    _safe_metadata_json(metadata),
                    _utc_now_iso(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except (sqlite3.Error, OSError, ValueError):
        return


def _usage_from_payload(payload: Mapping[str, Any], *, fallback_input_tokens: int, fallback_output_tokens: int) -> tuple[int, int, int, str]:
    usage = payload.get("usage")
    source_kind = "provider_usage" if isinstance(usage, Mapping) else "fallback_estimate"
    usage_map = usage if isinstance(usage, Mapping) else {}
    input_tokens = _clean_int(usage_map.get("prompt_tokens") or usage_map.get("input_tokens"), fallback_input_tokens)
    output_tokens = _clean_int(usage_map.get("completion_tokens") or usage_map.get("output_tokens"), fallback_output_tokens)
    total_tokens = _clean_int(usage_map.get("total_tokens"), input_tokens + output_tokens)
    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens
    return input_tokens, output_tokens, total_tokens, source_kind


def _usage_from_sse_chunk(chunk: bytes) -> tuple[int, int, int] | None:
    try:
        text = chunk.decode("utf-8")
    except UnicodeDecodeError:
        return None
    for line in text.splitlines():
        clean = line.strip()
        if not clean.startswith("data:"):
            continue
        data = clean.removeprefix("data:").strip()
        if not data or data == "[DONE]":
            continue
        try:
            import json

            payload = json.loads(data)
        except Exception:
            continue
        if isinstance(payload, Mapping) and isinstance(payload.get("usage"), Mapping):
            return _usage_from_payload(payload, fallback_input_tokens=0, fallback_output_tokens=0)[:3]
    return None


def _emitted_output_chars_from_sse_chunk(chunk: bytes) -> int:
    """Length of the assistant text actually emitted in one streamed SSE chunk.

    billing-H2: a stream that FAILS mid-flight after emitting chunks has still
    been billed by the provider for the tokens it produced, but no terminal usage
    block arrives. Summing the ``delta.content`` text across the emitted chunks
    gives a local floor (converted to tokens) so the partial output is settled
    instead of charging $0. Counts every completion's delta for n>1 fan-out.
    """
    try:
        text = chunk.decode("utf-8")
    except UnicodeDecodeError:
        return 0
    total = 0
    for line in text.splitlines():
        clean = line.strip()
        if not clean.startswith("data:"):
            continue
        data = clean.removeprefix("data:").strip()
        if not data or data == "[DONE]":
            continue
        try:
            import json

            payload = json.loads(data)
        except Exception:
            continue
        if not isinstance(payload, Mapping):
            continue
        for choice in payload.get("choices") or []:
            if not isinstance(choice, Mapping):
                continue
            delta = choice.get("delta")
            message = choice.get("message")
            content = None
            if isinstance(delta, Mapping):
                content = delta.get("content")
            if content is None and isinstance(message, Mapping):
                content = message.get("content")
            if isinstance(content, str):
                total += len(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, Mapping) and isinstance(part.get("text"), str):
                        total += len(part["text"])
    return total


def _check_rate_limit(conn: sqlite3.Connection, *, scope: str, subject: str, limit: int) -> JSONResponse | None:
    if limit <= 0:
        return None
    since = (datetime.now(timezone.utc) - timedelta(seconds=60)).replace(microsecond=0).isoformat()
    if rate_limit_count(conn, scope, subject, since) >= limit:
        return _json_error(
            429,
            "rate_limited",
            "ArcLink LLM router request rate limit exceeded.",
            retry_after=60,
        )
    return None


def _record_rate_limits(conn: sqlite3.Connection, auth_record: Mapping[str, Any], *, commit: bool = True) -> None:
    key_id = str(auth_record.get("key_id") or "")
    deployment_id = str(auth_record.get("deployment_id") or "")
    user_id = str(auth_record.get("user_id") or "")
    for scope, subject in (
        ("llm-router:key", key_id),
        ("llm-router:deployment", deployment_id),
        ("llm-router:user", user_id),
    ):
        if subject:
            conn.execute(
                "INSERT INTO rate_limits (scope, subject, observed_at) VALUES (?, ?, ?)",
                (scope, subject, _utc_now_iso()),
            )
    if commit:
        conn.commit()


def _open_reserved_count(conn: sqlite3.Connection, deployment_id: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM arclink_llm_budget_reservations
        WHERE deployment_id = ? AND status = 'reserved'
        """,
        (deployment_id,),
    ).fetchone()
    return int(row["count"] if row else 0)


def _open_reserved_cents(conn: sqlite3.Connection, deployment_id: str) -> int:
    """Sum of still-open (status='reserved') reservation amounts for a Pod.

    Settlement only updates ``arclink_chutes_usage`` (which feeds
    ``boundary.remaining_cents``) when a request *completes*. Concurrent
    in-flight requests each hold an OPEN reservation that has not yet been
    charged against the budget. The preflight budget gate must subtract these
    open reservations from the settled ``remaining_cents`` so that N concurrent
    requests cannot collectively reserve more than the budget allows (C1).
    """
    row = conn.execute(
        """
        SELECT COALESCE(SUM(reserved_cents), 0) AS reserved
        FROM arclink_llm_budget_reservations
        WHERE deployment_id = ? AND status = 'reserved'
        """,
        (deployment_id,),
    ).fetchone()
    return int(row["reserved"] if row else 0)


def _create_budget_reservation(
    conn: sqlite3.Connection,
    *,
    request_id: str,
    deployment_id: str,
    user_id: str,
    reserved_cents: int,
    metadata: Mapping[str, Any] | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    reservation_id = f"llmres_{uuid.uuid4().hex[:24]}"
    now_iso = _utc_now_iso()
    conn.execute(
        """
        INSERT INTO arclink_llm_budget_reservations (
          reservation_id, request_id, deployment_id, user_id, reserved_cents, status, metadata_json, created_at, heartbeat_at
        ) VALUES (?, ?, ?, ?, ?, 'reserved', ?, ?, ?)
        """,
        (
            reservation_id,
            request_id,
            deployment_id,
            user_id,
            max(1, int(reserved_cents)),
            _metadata_json(metadata or {}),
            now_iso,
            # C2: stamp the heartbeat at creation so the reaper measures liveness
            # by heartbeat staleness, not by total age (a long-lived stream that
            # keeps yielding chunks stays alive and is never expired mid-flight).
            now_iso,
        ),
    )
    if commit:
        conn.commit()
    return {
        "reservation_id": reservation_id,
        "request_id": request_id,
        "deployment_id": deployment_id,
        "user_id": user_id,
        "reserved_cents": max(1, int(reserved_cents)),
        "heartbeat_at": now_iso,
        "metadata": dict(metadata or {}),
    }


def _release_budget_reservation(
    conn: sqlite3.Connection,
    reservation_id: str,
    *,
    status: str = "released",
    settled_cents: int = 0,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    # C2 reconcile-by-id: settle the reservation BY ID regardless of its current
    # status. The heartbeat reaper may have already flipped a live row to
    # 'expired' (e.g. a long stream whose heartbeat staleness crossed the TTL just
    # before settlement); the settling request must still reconcile it to its
    # terminal 'settled'/'failed' state rather than no-op on a status guard. Only
    # an already-terminal row (settled/failed/released) is left untouched so a
    # double-settle cannot rewrite a finished row.
    if metadata is None:
        conn.execute(
            """
            UPDATE arclink_llm_budget_reservations
            SET status = ?, settled_cents = ?, settled_at = ?
            WHERE reservation_id = ? AND status IN ('reserved', 'expired')
            """,
            (status, max(0, int(settled_cents)), _utc_now_iso(), reservation_id),
        )
    else:
        conn.execute(
            """
            UPDATE arclink_llm_budget_reservations
            SET status = ?, settled_cents = ?, metadata_json = ?, settled_at = ?
            WHERE reservation_id = ? AND status IN ('reserved', 'expired')
            """,
            (status, max(0, int(settled_cents)), _metadata_json(metadata), _utc_now_iso(), reservation_id),
        )
    conn.commit()


# C2: the reaper measures HEARTBEAT staleness, not total age. The heartbeat is
# stamped at reservation creation and refreshed ONLY after a streamed chunk -- so
# the longest a LIVE request can go without refreshing is bounded by the upstream
# httpx READ timeout: time-to-first-byte, the inter-chunk gap, AND a whole
# non-streaming call are each capped at that read timeout (one read window can
# elapse with zero heartbeat refresh). The TTL must therefore be STRICTLY GREATER
# than that read window plus margin, or a legitimately-slow live request whose
# first/next chunk is up to read_timeout away gets false-expired -> dropped from
# the C1 open-reservation headroom sum -> budget over-reserved.
DEFAULT_RESERVATION_HEARTBEAT_TTL_SECONDS = 120
# Throttle: refresh the on-row heartbeat at most this often per reservation, so a
# fast token stream does not issue a DB write per chunk.
RESERVATION_HEARTBEAT_REFRESH_SECONDS = 15
# Slack added on top of the upstream read window so a single read-timeout gap (no
# refresh) can never by itself trip the reaper.
RESERVATION_REAPER_TTL_MARGIN_SECONDS = 120


def _reservation_reaper_ttl_seconds(config: RouterConfig) -> int:
    """Max tolerable heartbeat staleness before a reservation is presumed leaked.

    The heartbeat refreshes only AFTER a streamed chunk, while httpx bounds the
    time-to-first-byte, the inter-chunk gap, and a whole non-streaming call to the
    upstream READ timeout. So a LIVE request can legitimately go up to
    ``upstream_read_timeout_seconds`` without refreshing its heartbeat. The TTL is
    therefore set strictly GREATER than one such read window
    (``read_timeout + margin``) so a single read-timeout gap can never false-expire
    an in-flight reservation; a worker that actually died stops refreshing and ages
    past this larger window. Floored at the legacy fixed window so a tiny configured
    read timeout still leaves comfortable refresh + settlement slack.
    """
    return max(
        DEFAULT_RESERVATION_HEARTBEAT_TTL_SECONDS,
        RESERVATION_HEARTBEAT_REFRESH_SECONDS * 4,
        int(config.upstream_read_timeout_seconds) + RESERVATION_REAPER_TTL_MARGIN_SECONDS,
    )


def _touch_reservation_heartbeat(
    config: RouterConfig,
    reservation: Mapping[str, Any] | dict[str, Any],
) -> None:
    """Refresh a live reservation's heartbeat (throttled, best-effort).

    Called from the active/streaming path. Writes ``heartbeat_at`` at most once
    per ``RESERVATION_HEARTBEAT_REFRESH_SECONDS`` per reservation (tracked on the
    in-memory ``reservation`` dict) so a fast token stream does not issue a DB
    write per chunk. Never raises into the inference path -- a missed heartbeat
    at worst lets the reaper expire a genuinely-stalled row, which settlement
    still reconciles by id.
    """
    reservation_id = str((reservation or {}).get("reservation_id") or "").strip()
    if not reservation_id:
        return
    now = datetime.now(timezone.utc)
    last_raw = str((reservation or {}).get("heartbeat_at") or "").strip()
    if last_raw:
        try:
            last = datetime.fromisoformat(last_raw)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if (now - last) < timedelta(seconds=RESERVATION_HEARTBEAT_REFRESH_SECONDS):
                return
        except ValueError:
            pass
    now_iso = now.replace(microsecond=0).isoformat()
    try:
        conn = _open_control_conn(config)
        try:
            conn.execute(
                """
                UPDATE arclink_llm_budget_reservations
                SET heartbeat_at = ?
                WHERE reservation_id = ? AND status = 'reserved'
                """,
                (now_iso, reservation_id),
            )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error:
        return
    if isinstance(reservation, dict):
        reservation["heartbeat_at"] = now_iso


def _reap_stale_reservations(conn: sqlite3.Connection, config: RouterConfig, *, commit: bool = True) -> int:
    """Expire reservations whose heartbeat went stale past the TTL (idempotent).

    C2 leaked-reservation fix: a worker that dies between forwarding and
    settlement -- or stalls -- stops refreshing ``heartbeat_at``. Once the
    heartbeat is older than the TTL the row can only be leaked, so it is flipped
    to 'expired' (distinct from a clean 'released'): it stops counting against the
    C1 ``status='reserved'`` headroom sum and the concurrency limit, but a
    reaped-but-returning request can still reconcile it by id (settlement matches
    'reserved' OR 'expired'). Keyed on heartbeat staleness -- NOT total age -- so a
    long but live stream that keeps yielding chunks is never expired mid-flight.
    Pure UPDATE, safe to run on every preflight and at startup.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=_reservation_reaper_ttl_seconds(config))).replace(
        microsecond=0
    ).isoformat()
    cursor = conn.execute(
        """
        UPDATE arclink_llm_budget_reservations
        SET status = 'expired', settled_at = ?
        WHERE status = 'reserved'
          AND COALESCE(NULLIF(heartbeat_at, ''), created_at) < ?
        """,
        (_utc_now_iso(), cutoff),
    )
    if commit:
        conn.commit()
    return int(cursor.rowcount or 0)


def _money(cents: int) -> str:
    whole, remainder = divmod(max(0, int(cents or 0)), 100)
    return f"${whole}.{remainder:02d}" if remainder else f"${whole}"


def _captain_public_channel(conn: sqlite3.Connection, *, user_id: str, deployment_id: str) -> dict[str, str] | None:
    row = conn.execute(
        """
        SELECT channel, channel_identity
        FROM arclink_onboarding_sessions
        WHERE user_id = ?
          AND channel IN ('telegram', 'discord')
          AND channel_identity != ''
          AND status IN ('paid', 'provisioning_ready', 'first_contacted', 'completed')
        ORDER BY
          CASE WHEN deployment_id = ? THEN 0 ELSE 1 END,
          updated_at DESC,
          created_at DESC,
          session_id DESC
        LIMIT 1
        """,
        (str(user_id or "").strip(), str(deployment_id or "").strip()),
    ).fetchone()
    if row is None:
        return None
    return {"channel_kind": str(row["channel"] or ""), "target_id": str(row["channel_identity"] or "")}


def _fuel_notice_actions() -> dict[str, Any]:
    return {
        "telegram_reply_markup": {
            "inline_keyboard": [[{"text": "Refuel ArcPod", "callback_data": "arclink:/raven refuel"}]]
        },
        "discord_components": [
            {
                "type": 1,
                "components": [
                    {"type": 2, "label": "Refuel ArcPod", "style": 1, "custom_id": "arclink:/raven refuel"}
                ],
            }
        ],
    }


def _fuel_notice_message(*, severity: str, remaining_cents: int, monthly_budget_cents: int, usage_percent: float) -> str:
    if severity == "empty":
        headline = "ArcPod fuel is empty."
        detail = "Your Agent's Pod has used its available model fuel."
    else:
        headline = "ArcPod fuel is running low."
        detail = (
            f"Your Agent's Pod has about {_money(remaining_cents)} of model fuel left "
            f"from {_money(monthly_budget_cents)}."
        )
    return "\n".join(
        [
            headline,
            "",
            detail,
            f"Current burn is {round(float(usage_percent or 0.0), 2)}% of the configured fuel tank.",
            "",
            "Raven can open ArcPod Refueling whenever you're ready. Use `/refuel` or tap Refuel ArcPod.",
        ]
    )


def _notice_already_queued(conn: sqlite3.Connection, *, deployment_id: str, notice_key: str) -> bool:
    rows = conn.execute(
        """
        SELECT metadata_json
        FROM arclink_events
        WHERE subject_kind = 'deployment'
          AND subject_id = ?
          AND event_type = 'llm_router:arc_pod_fuel_notice_queued'
        ORDER BY created_at DESC
        LIMIT 25
        """,
        (deployment_id,),
    ).fetchall()
    for row in rows:
        try:
            metadata = json.loads(str(row["metadata_json"] or "{}"))
        except Exception:
            metadata = {}
        if isinstance(metadata, dict) and str(metadata.get("notice_key") or "") == notice_key:
            return True
    return False


def _queue_arc_pod_fuel_notice(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    user_id: str,
    boundary: Any,
    severity: str,
    commit: bool = True,
) -> None:
    try:
        clean_deployment = str(deployment_id or "").strip()
        clean_user = str(user_id or "").strip()
        monthly_budget = int(getattr(boundary, "monthly_budget_cents", 0) or 0)
        remaining = int(getattr(boundary, "remaining_cents", 0) or 0)
        usage_percent = float(getattr(boundary, "usage_percent", 0.0) or 0.0)
        if not clean_deployment or not clean_user or monthly_budget <= 0:
            return
        notice_key = f"{severity}:{monthly_budget}:{int(float(getattr(boundary, 'warning_threshold_percent', 0.0) or 0.0))}"
        if _notice_already_queued(conn, deployment_id=clean_deployment, notice_key=notice_key):
            return
        channel = _captain_public_channel(conn, user_id=clean_user, deployment_id=clean_deployment)
        if channel is None:
            return
        cursor = conn.execute(
            """
            INSERT INTO notification_outbox (target_kind, target_id, channel_kind, message, extra_json, created_at)
            VALUES ('public-bot-user', ?, ?, ?, ?, ?)
            """,
            (
                channel["target_id"],
                channel["channel_kind"],
                _fuel_notice_message(
                    severity=severity,
                    remaining_cents=remaining,
                    monthly_budget_cents=monthly_budget,
                    usage_percent=usage_percent,
                ),
                _safe_metadata_json(_fuel_notice_actions()),
                _utc_now_iso(),
            ),
        )
        notification_id = int(cursor.lastrowid or 0)
        conn.execute(
            """
            INSERT INTO arclink_events (event_id, subject_kind, subject_id, event_type, metadata_json, created_at)
            VALUES (?, 'deployment', ?, 'llm_router:arc_pod_fuel_notice_queued', ?, ?)
            """,
            (
                f"evt_{uuid.uuid4().hex}",
                clean_deployment,
                _safe_metadata_json(
                    {
                        "user_id": clean_user,
                        "notice_key": notice_key,
                        "severity": severity,
                        "remaining_cents": remaining,
                        "monthly_budget_cents": monthly_budget,
                        "usage_percent": usage_percent,
                        "notification_id": notification_id,
                    }
                ),
                _utc_now_iso(),
            ),
        )
        if commit:
            conn.commit()
    except Exception:
        # Fuel notices must never slow or fail the Agent's actual inference path.
        return


def _preflight_chat_request(
    conn: sqlite3.Connection,
    config: RouterConfig,
    auth_record: Mapping[str, Any],
    payload: Mapping[str, Any],
    body: bytes,
) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    model = str(payload.get("model") or "").strip()
    if not model:
        return None, _router_error(400, "missing_model", "ArcLink LLM router requires a model.")
    key_allowed_models = tuple(auth_record.get("allowed_models") or ())
    # Per-key allow-lists still win; otherwise the global allow-list reflects
    # the synced Chutes -TEE catalog (DB-backed, so it tracks the sync worker
    # without a router restart), falling back to the static env list.
    allowed_models = key_allowed_models or _effective_global_allowed_models(conn, config)
    allow_default_model = not key_allowed_models
    if not _router_model_allowed(config, model, allowed_models, allow_default_model=allow_default_model):
        return None, _router_error(403, "model_not_allowed", "Requested model is not allowed for this ArcPod.")
    upstream_model, catalog_entry, model_resolution = _resolve_router_model(conn, config, model, allowed_models)
    # H2 default-model catalog bypass fix: ``_router_model_allowed`` admits the
    # configured default model regardless of catalog status, and the catalog can
    # mark a model 'unavailable'/'deprecated' (e.g. the sync worker pulled it).
    # Even for the default, never forward an upstream model whose catalog row
    # exists and is NOT 'active' -- a deprecated row with a replacement is already
    # redirected by _resolve_router_model, so a non-active entry here means it was
    # withdrawn with no live replacement. Break-glass env reopens it for incident
    # response only.
    if not config.allow_inactive_models and catalog_entry is not None:
        upstream_status = str(catalog_entry.get("status") or "").strip().lower()
        if upstream_status and upstream_status != "active":
            return None, _router_error(
                403,
                "model_unavailable",
                "Resolved model is marked unavailable in the ArcLink model catalog.",
            )
    # The RESOLVED primary (after _resolve_router_model redirected/promoted the
    # requested model) must itself be allowed -- a catalog replacement could point
    # at a model this ArcPod's key cannot use. The requested model was checked at
    # ~the top; this guards the resolved target.
    if not _router_model_allowed(config, upstream_model, allowed_models, allow_default_model=allow_default_model):
        return None, _router_error(403, "model_not_allowed", "Resolved model is not allowed for this ArcPod.")
    # Outage fix: a DISALLOWED fallback must be SKIPPED, never fatal. Filter the
    # candidate list down to the primary + only the allowed (and catalog-active)
    # fallbacks; the forward/stream loops iterate THIS list, so an unusable
    # fallback (e.g. a key allowing only the primary while a Kimi fallback is
    # configured) no longer 403's the whole request -- the allowed primary works.
    fallback_candidates = _allowed_router_fallback_candidates(
        conn,
        config,
        upstream_model,
        allowed_models,
        allow_default_model=allow_default_model,
    )
    if not fallback_candidates:
        # Defensive: the primary is always kept above, so this is unreachable in
        # normal operation. Fail closed rather than forward with an empty list.
        return None, _router_error(403, "model_not_allowed", "No allowed model is available for this ArcPod.")

    prompt_tokens = _estimate_prompt_tokens(payload, body)
    if prompt_tokens > config.prompt_estimate_token_cap:
        return None, _router_error(413, "prompt_too_large", "ArcLink LLM router prompt estimate exceeds the configured cap.")
    max_tokens = _requested_max_tokens(payload)
    if max_tokens > config.max_tokens_cap:
        return None, _router_error(400, "max_tokens_too_large", "Requested max_tokens exceeds the ArcLink LLM router cap.")
    # C1 multi-completion fix: a caller can fan one request into several sampled
    # completions via ``n`` (or ``best_of``), each up to the per-completion output
    # cap. Clamp to ``1..config.max_completions`` and price the EFFECTIVE worst-case
    # output (per-completion cap x this count); the SAME clamped value is forwarded
    # (via ``_prepare_upstream_payload``) so the upstream fan-out can never exceed
    # what was reserved.
    effective_completions = _effective_completions(config, payload)

    transaction_started = False
    try:
        conn.execute("BEGIN IMMEDIATE")
        transaction_started = True
        # C2: release any reservation leaked by a worker that died mid-request
        # before we read open reservations / enforce concurrency below. Done
        # inside the write lock so the reap is serialized with this request's own
        # reservation accounting (no commit here -- the whole preflight commits once).
        _reap_stale_reservations(conn, config, commit=False)
        metadata, billing_state = _load_deployment_context(conn, auth_record)
        deployment_id = str(auth_record.get("deployment_id") or "")
        user_id = str(auth_record.get("user_id") or "")
        boundary_metadata = _router_boundary_metadata(metadata, auth_record)
        observe_authorized = observe_unlimited_authorized(conn, deployment_id, user_id)
        boundary = evaluate_chutes_deployment_boundary(
            deployment_id,
            user_id,
            boundary_metadata,
            env={
                "ARCLINK_CHUTES_DEFAULT_MONTHLY_BUDGET_CENTS": str(config.default_monthly_budget_cents),
                "ARCLINK_CHUTES_WARNING_THRESHOLD_PERCENT": "80",
                "ARCLINK_CHUTES_HARD_LIMIT_PERCENT": "100",
            },
            billing_state=billing_state,
            observe_unlimited_authorized=observe_authorized,
        )
        demotion_recorded = record_chutes_budget_policy_demotion(
            conn,
            deployment_id=deployment_id,
            metadata=boundary_metadata,
            observe_unlimited_authorized=observe_authorized,
            source="llm_router_preflight",
            commit=False,
        )
        if not boundary.allow_inference:
            status_code = 402 if boundary.credential_state in {"billing_suspended", "budget_unconfigured", "budget_exhausted"} else 403
            if boundary.credential_state == "budget_exhausted":
                _queue_arc_pod_fuel_notice(
                    conn,
                    deployment_id=deployment_id,
                    user_id=user_id,
                    boundary=boundary,
                    severity="empty",
                    commit=False,
                )
                conn.commit()
            elif demotion_recorded:
                conn.commit()
            else:
                conn.rollback()
            transaction_started = False
            return None, _router_error(status_code, boundary.credential_state, boundary.reason)

        for scope, subject, limit in (
            ("llm-router:key", str(auth_record.get("key_id") or ""), config.key_requests_per_minute),
            ("llm-router:deployment", str(auth_record.get("deployment_id") or ""), config.deployment_requests_per_minute),
            ("llm-router:user", str(auth_record.get("user_id") or ""), config.user_requests_per_minute),
        ):
            error = _check_rate_limit(conn, scope=scope, subject=subject, limit=limit)
            if error is not None:
                conn.rollback()
                transaction_started = False
                return None, error

        if _open_reserved_count(conn, deployment_id) >= config.deployment_concurrency_limit:
            conn.rollback()
            transaction_started = False
            return None, _json_error(
                429,
                "concurrency_limited",
                "ArcLink LLM router deployment concurrency limit exceeded.",
                retry_after=1,
            )

        pricing_choice = _fallback_reservation_pricing(
            conn,
            config,
            primary_model=upstream_model,
            primary_entry=catalog_entry,
            input_tokens=prompt_tokens,
            max_tokens=max_tokens,
            completions=effective_completions,
            candidates=fallback_candidates,
        )
        selected_pricing = dict(pricing_choice["selected"])
        reserved_cents = int(selected_pricing.get("reserved_cents") or config.min_reservation_cents)
        # C1 over-spend fix: ``boundary.remaining_cents`` is computed from SETTLED
        # usage only, so concurrent in-flight requests (each holding an OPEN
        # reservation not yet charged) could collectively reserve past the budget.
        # Subtract the still-open reservation total -- read inside this same
        # BEGIN IMMEDIATE txn so it is serialized against other reservers -- before
        # testing the request's own reservation against the available headroom.
        open_reserved_cents = _open_reserved_cents(conn, deployment_id)
        available_cents = int(boundary.remaining_cents) - open_reserved_cents
        # Observed-unlimited Pods (the Operator's own Pod) are metered but never reservation-
        # blocked, so Raven inference cannot be silenced by a budget cap.
        if str(getattr(boundary, "budget_status", "") or "") != "unlimited" and available_cents < reserved_cents:
            _queue_arc_pod_fuel_notice(
                conn,
                deployment_id=str(auth_record.get("deployment_id") or ""),
                user_id=str(auth_record.get("user_id") or ""),
                boundary=boundary,
                severity="low",
                commit=False,
            )
            conn.commit()
            transaction_started = False
            return None, _router_error(402, "budget_exhausted", "Chutes budget remaining is below the required request reservation.")

        _record_rate_limits(conn, auth_record, commit=False)
        request_id = f"llmreq_{uuid.uuid4().hex[:24]}"
        reservation_metadata = {
            "request_id": request_id,
            "deployment_id": deployment_id,
            "user_id": str(auth_record.get("user_id") or ""),
            "requested_model": model,
            "primary_model": upstream_model,
            "final_model": upstream_model,
            "fallback_used": False,
            "fallback_candidate_count": len(fallback_candidates),
            "fallback_pricing_reserved": str(selected_pricing.get("model") or "") != upstream_model,
            "reservation_pricing_model": str(selected_pricing.get("model") or upstream_model),
            "reservation_pricing_source": str(selected_pricing.get("pricing_source") or ""),
            "reservation_input_cents_per_million": int(selected_pricing.get("input_cents_per_million") or 0),
            "reservation_output_cents_per_million": int(selected_pricing.get("output_cents_per_million") or 0),
            "reserved_cents": reserved_cents,
            "reservation_pricing_candidates": pricing_choice["choices"],
            "pricing_adjusted_at_settlement": False,
            "model_resolution": model_resolution,
            "effective_completions": effective_completions,
        }
        reservation = _create_budget_reservation(
            conn,
            request_id=request_id,
            deployment_id=deployment_id,
            user_id=str(auth_record.get("user_id") or ""),
            reserved_cents=reserved_cents,
            metadata=reservation_metadata,
            commit=False,
        )
        conn.commit()
        transaction_started = False
    except Exception:
        if transaction_started:
            conn.rollback()
        raise
    reservation["input_token_estimate"] = prompt_tokens
    reservation["output_token_estimate"] = max_tokens if max_tokens > 0 else min(config.max_tokens_cap, 1024)
    # C1 multi-completion fix: carry the clamped completion count so the forward
    # path clamps the outgoing ``n``/``best_of`` to the SAME value the reservation
    # priced -- the upstream can never sample more completions than were reserved.
    reservation["effective_completions"] = effective_completions
    reservation["requested_model"] = model
    reservation["upstream_model"] = upstream_model
    # Carry the allow-filtered candidate list so the forward/stream loops iterate
    # ONLY the primary + permitted (catalog-active) fallbacks -- a disallowed
    # fallback is never attempted upstream.
    reservation["fallback_candidates"] = list(fallback_candidates)
    reservation["model_pricing"] = dict(catalog_entry or {})
    reservation["reservation_pricing_model"] = str(selected_pricing.get("model") or upstream_model)
    reservation["reservation_model_pricing"] = dict(selected_pricing.get("catalog_entry") or {})
    reservation["model_resolution"] = model_resolution
    reservation["pricing_source"] = str(selected_pricing.get("pricing_source") or "")
    return reservation, None


def _prepare_upstream_payload(
    payload: Mapping[str, Any],
    *,
    model: str = "",
    max_output_tokens: int = 0,
    max_completions: int = 0,
) -> dict[str, Any]:
    prepared = dict(payload)
    if model:
        prepared["model"] = model
    # missed-H fix: when the caller omitted a usable output cap, the reservation
    # still priced a bounded number of output tokens (``min(cap, 1024)``). Forward
    # that same cap so the upstream cannot settle MORE output than was reserved.
    #
    # missed-H2 fix: a caller can set ``max_tokens: null`` (or a non-positive /
    # non-int value). Preflight's ``_requested_max_tokens`` already treats that as
    # 0 (priced as the bounded default), but the key still EXISTS in the body --
    # so forwarding it verbatim would let upstream interpret ``null`` as unbounded.
    #
    # Round-3 fix: enforce the cap across EVERY max-output key, not just the first.
    # A caller can send several at once (``{max_tokens: null,
    # max_completion_tokens: 999999}`` or ``{max_tokens: 64,
    # max_completion_tokens: 999999}``) where one key undercuts the cap and another
    # blows past it. The reservation priced the EFFECTIVE cap (the tightest usable
    # value, via ``_requested_max_tokens``); ``max_output_tokens`` carries that
    # priced ceiling. So: (1) drop any present-but-unusable key (null / 0 / negative
    # / non-int) so it can never reach upstream as "unbounded"; (2) CLAMP every
    # remaining present key down to <= the priced ceiling; (3) if no usable key
    # survived, inject the ceiling. No key can exceed the reservation after this.
    ceiling = int(max_output_tokens) if max_output_tokens and int(max_output_tokens) > 0 else 0
    any_usable_present = False
    for name in _MAX_OUTPUT_TOKEN_KEYS:
        if name not in prepared:
            continue
        usable = _usable_positive_int(prepared.get(name))
        if usable <= 0:
            # null / 0 / negative / non-int -> treat as omitted: drop it so a
            # null can never reach upstream as "unbounded".
            del prepared[name]
            continue
        any_usable_present = True
        # Lower any value exceeding the priced ceiling so NO present key can settle
        # more output than was reserved.
        prepared[name] = min(usable, ceiling) if ceiling > 0 else usable
    if not any_usable_present and ceiling > 0:
        prepared["max_tokens"] = ceiling
    # C1 multi-completion fix: the reservation priced ``per-completion cap x
    # max_completions`` worth of output. Clamp every completion-multiplier key the
    # caller sent (``n``, and ``best_of`` defensively) down to <= that priced count
    # so the upstream fan-out can never settle more completions than were reserved;
    # drop any present-but-unusable value (null / 0 / negative / non-int) so it
    # cannot reach upstream and be defaulted to something larger.
    completion_ceiling = int(max_completions) if max_completions and int(max_completions) > 0 else 0
    if completion_ceiling > 0:
        for name in _COMPLETION_MULTIPLIER_KEYS:
            if name not in prepared:
                continue
            usable = _usable_positive_int(prepared.get(name))
            if usable <= 0:
                del prepared[name]
                continue
            prepared[name] = min(usable, completion_ceiling)
    if _truthy(str(prepared.get("stream") or "")):
        stream_options = prepared.get("stream_options")
        if not isinstance(stream_options, dict):
            stream_options = {}
        stream_options.setdefault("include_usage", True)
        prepared["stream_options"] = stream_options
    return prepared


def _upstream_headers(config: RouterConfig) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.chutes_api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream, application/json",
    }


def _upstream_url(config: RouterConfig, path: str) -> str:
    return f"{config.chutes_base_url.rstrip('/')}/{path.lstrip('/')}"


def _upstream_timeout(config: RouterConfig) -> httpx.Timeout:
    return httpx.Timeout(
        connect=float(config.upstream_connect_timeout_seconds),
        read=float(config.upstream_read_timeout_seconds),
        write=float(config.upstream_write_timeout_seconds),
        pool=float(config.upstream_pool_timeout_seconds),
    )


def _upstream_limits(config: RouterConfig) -> httpx.Limits:
    return httpx.Limits(
        max_connections=int(config.upstream_max_connections),
        max_keepalive_connections=min(int(config.upstream_max_connections), int(config.upstream_max_keepalive_connections)),
        keepalive_expiry=float(config.upstream_keepalive_expiry_seconds),
    )


def _create_upstream_client(config: RouterConfig, app_state: Any) -> httpx.AsyncClient:
    transport = getattr(app_state, "router_upstream_transport", None)
    return httpx.AsyncClient(
        transport=transport,
        timeout=_upstream_timeout(config),
        limits=_upstream_limits(config),
    )


def _current_loop_key() -> str:
    try:
        return str(id(asyncio.get_running_loop()))
    except RuntimeError:
        return "no-running-loop"


def _upstream_client(config: RouterConfig, app_state: Any) -> httpx.AsyncClient:
    clients = getattr(app_state, "router_upstream_clients", None)
    if not isinstance(clients, dict):
        clients = {}
        app_state.router_upstream_clients = clients
    loop_key = _current_loop_key()
    client = clients.get(loop_key)
    if client is None or bool(getattr(client, "is_closed", False)):
        client = _create_upstream_client(config, app_state)
        clients[loop_key] = client
    return client


async def _close_upstream_clients(app_state: Any) -> None:
    clients = getattr(app_state, "router_upstream_clients", None)
    if not isinstance(clients, dict):
        return
    for client in list(clients.values()):
        if client is not None and not bool(getattr(client, "is_closed", False)):
            await client.aclose()
    clients.clear()


async def _warm_up_upstream_pool(config: RouterConfig, app_state: Any) -> dict[str, Any]:
    if not config.upstream_warmup_enabled:
        return {"status": "disabled"}
    if not config.enabled:
        return {"status": "skipped", "reason": "router_disabled"}
    if not config.configured:
        return {"status": "skipped", "reason": "router_not_configured"}
    if getattr(app_state, "router_upstream_transport", None) is not None:
        return {"status": "skipped", "reason": "test_transport"}
    client = _upstream_client(config, app_state)
    warmup_timeout = httpx.Timeout(
        connect=float(config.upstream_connect_timeout_seconds),
        read=5.0,
        write=5.0,
        pool=float(config.upstream_pool_timeout_seconds),
    )
    try:
        response = await client.get(_upstream_url(config, "models"), headers=_upstream_headers(config), timeout=warmup_timeout)
        await response.aread()
    except httpx.HTTPError as exc:
        return {"status": "failed", "error": _safe_upstream_error(str(exc))}
    if response.status_code in {401, 403}:
        return {"status": "failed", "status_code": response.status_code}
    if response.status_code >= 500:
        return {"status": "degraded", "status_code": response.status_code}
    if response.status_code >= 400:
        return {"status": "degraded", "status_code": response.status_code}
    return {"status": "ok", "status_code": response.status_code}


def _record_router_usage(
    conn: sqlite3.Connection,
    config: RouterConfig,
    *,
    reservation: Mapping[str, Any],
    auth_record: Mapping[str, Any],
    model: str,
    stream: bool,
    status: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    source_kind: str,
    error_summary: str = "",
    fallback_attempts: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] = (),
    streaming_fallback: str = "",
    settle_partial_output_tokens: int = 0,
) -> int:
    reservation_pricing_entry = reservation.get("reservation_model_pricing") if isinstance(reservation.get("reservation_model_pricing"), Mapping) else None
    usage_pricing_entry = get_model_catalog_entry(conn, provider="chutes", model_id=model)
    pricing_entry = usage_pricing_entry if usage_pricing_entry is not None else None
    partial_output_floor = max(0, int(settle_partial_output_tokens))
    if status == "succeeded":
        actual_cents = _estimate_usage_cents(config, input_tokens, output_tokens, pricing_entry)
    elif partial_output_floor > 0:
        # billing-H2: the stream failed after emitting output the provider already
        # billed. Settle the input plus the partial output actually emitted instead
        # of charging $0; the request status remains "failed" for analytics, but the
        # recorded output/total tokens reflect the emitted floor for observability.
        actual_cents = _estimate_usage_cents(config, input_tokens, partial_output_floor, pricing_entry)
        output_tokens = partial_output_floor
        total_tokens = max(0, int(input_tokens)) + partial_output_floor
    else:
        actual_cents = 0
    estimated_cents = int(reservation.get("reserved_cents") or 0)
    now = _utc_now_iso()
    usage_id = f"llmuse_{uuid.uuid4().hex[:24]}"
    request_id = str(reservation.get("request_id") or "")
    deployment_id = str(auth_record.get("deployment_id") or reservation.get("deployment_id") or "")
    user_id = str(auth_record.get("user_id") or reservation.get("user_id") or "")
    requested_model = str(reservation.get("requested_model") or "")
    primary_model = str(reservation.get("upstream_model") or requested_model)
    reservation_pricing_model = str(reservation.get("reservation_pricing_model") or primary_model)
    reservation_pricing_source = str(reservation.get("pricing_source") or "")
    if reservation_pricing_entry is not None:
        _, _, reservation_pricing_source = _model_price_cents(config, reservation_pricing_entry)
    _, _, usage_pricing_source = _model_price_cents(config, pricing_entry)
    pricing_adjusted = bool(model != reservation_pricing_model)
    usage_metadata: dict[str, Any] = {
        "request_id": request_id,
        "reservation_id": str(reservation.get("reservation_id") or ""),
        "deployment_id": deployment_id,
        "user_id": user_id,
        "provider": "chutes",
        "requested_model": requested_model,
        "primary_model": primary_model,
        "usage_model": model,
        "final_model": model,
        "fallback_used": bool(model != primary_model),
        "fallback_pricing_reserved": bool(reservation_pricing_model != primary_model),
        "fallback_attempt_count": len(fallback_attempts),
        "fallback_attempts": _public_fallback_attempts(fallback_attempts),
        "stream": bool(stream),
        "streaming_fallback": streaming_fallback,
        "source_kind": source_kind,
        "status": status,
        "reservation_pricing_model": reservation_pricing_model,
        "reservation_pricing_source": reservation_pricing_source,
        "usage_pricing_model": model,
        "usage_pricing_source": usage_pricing_source,
        "reserved_cents": estimated_cents,
        "settled_cents": actual_cents,
        "pricing_adjusted_at_settlement": pricing_adjusted,
    }
    conn.execute(
        """
        INSERT INTO arclink_llm_usage_events (
          usage_id, request_id, deployment_id, user_id, provider, model,
          input_tokens, output_tokens, total_tokens, estimated_cents, actual_cents,
          status, stream, source_kind, error_summary, metadata_json, started_at, completed_at
        ) VALUES (?, ?, ?, ?, 'chutes', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            usage_id,
            request_id,
            deployment_id,
            user_id,
            model,
            max(0, int(input_tokens)),
            max(0, int(output_tokens)),
            max(0, int(total_tokens)),
            max(0, estimated_cents),
            max(0, actual_cents),
            status,
            1 if stream else 0,
            source_kind,
            _safe_upstream_error(error_summary),
            _metadata_json(usage_metadata),
            now,
            now,
        ),
    )
    usage_result = None
    # billing-H2: also settle when a FAILED stream emitted partial output the
    # provider already billed (actual_cents > 0). The recorded request status stays
    # "failed", but the partial cents are still charged against the deployment budget.
    if status == "succeeded" or actual_cents > 0:
        settled_output_tokens = max(0, int(output_tokens)) if status == "succeeded" else partial_output_floor
        conn.execute("SAVEPOINT llm_router_chutes_usage")
        try:
            usage_result = record_chutes_usage_event(
                conn,
                deployment_id=deployment_id,
                user_id=user_id,
                usage_event={
                    "usage_event_id": usage_id,
                    "request_id": request_id,
                    "model_id": model,
                    "source": "llm-router",
                    "observed_at": now,
                    "input_tokens": max(0, int(input_tokens)),
                    "output_tokens": settled_output_tokens,
                    "total_tokens": max(0, int(input_tokens)) + settled_output_tokens,
                    "delta_cents": actual_cents,
                },
                env={
                    "ARCLINK_CHUTES_DEFAULT_MONTHLY_BUDGET_CENTS": str(config.default_monthly_budget_cents),
                    "ARCLINK_CHUTES_WARNING_THRESHOLD_PERCENT": "80",
                    "ARCLINK_CHUTES_HARD_LIMIT_PERCENT": "100",
                },
                commit=False,
            )
            conn.execute("RELEASE SAVEPOINT llm_router_chutes_usage")
        except (KeyError, PermissionError, ValueError, sqlite3.Error) as exc:
            conn.execute("ROLLBACK TO SAVEPOINT llm_router_chutes_usage")
            conn.execute("RELEASE SAVEPOINT llm_router_chutes_usage")
            usage_metadata["chutes_usage_recorded"] = False
            usage_metadata["chutes_usage_error"] = _safe_upstream_error(str(exc))
        if usage_result is not None and usage_result.boundary.budget_status in {"warning", "exhausted"}:
            _queue_arc_pod_fuel_notice(
                conn,
                deployment_id=deployment_id,
                user_id=user_id,
                boundary=usage_result.boundary,
                severity="empty" if usage_result.boundary.budget_status == "exhausted" else "low",
                commit=False,
            )
    _release_budget_reservation(
        conn,
        str(reservation.get("reservation_id") or ""),
        status="settled" if status == "succeeded" else "failed",
        settled_cents=actual_cents,
        metadata=usage_metadata,
    )
    return actual_cents


async def _forward_non_streaming(
    request: Request,
    config: RouterConfig,
    *,
    auth_record: Mapping[str, Any],
    reservation: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> JSONResponse:
    model = str(payload.get("model") or "").strip()
    upstream_model = str(reservation.get("upstream_model") or model).strip()
    # missed-H: cap forwarded output to the same bound the reservation priced.
    reserved_output_tokens = int(reservation.get("output_token_estimate") or 0)
    # C1 multi-completion: clamp the forwarded fan-out to the priced count.
    reserved_completions = int(reservation.get("effective_completions") or 1)
    # Outage fix: iterate the allow-filtered candidate list computed at preflight
    # (primary + only permitted/active fallbacks). Fall back to the raw list only
    # if a reservation predates this field, so a disallowed fallback is skipped.
    candidates = _reservation_fallback_candidates(config, reservation, upstream_model)
    fallback_attempts: list[dict[str, Any]] = []
    upstream = None
    final_model = upstream_model
    data: dict[str, Any] = {}
    source_kind = "provider_usage"

    client = _upstream_client(config, request.app.state)
    for index, candidate_model in enumerate(candidates):
        final_model = candidate_model
        # C2 retry-heartbeat fix: each upstream attempt can burn a whole read
        # timeout with no streamed chunk to refresh the heartbeat, so N pre-response
        # retries could leave a LIVE reservation un-heartbeated for N x read_timeout
        # and the reaper would false-expire it. Refresh at the START of every attempt
        # (throttled, best-effort) so a live request never goes longer than ONE read
        # window without a heartbeat regardless of retry count.
        _touch_reservation_heartbeat(config, reservation)
        try:
            upstream = await client.post(
                _upstream_url(config, "chat/completions"),
                json=_prepare_upstream_payload(
                    payload,
                    model=candidate_model,
                    max_output_tokens=reserved_output_tokens,
                    max_completions=reserved_completions,
                ),
                headers=_upstream_headers(config),
            )
        except httpx.HTTPError as exc:
            error_summary = _safe_upstream_error(str(exc))
            next_model = candidates[index + 1] if index + 1 < len(candidates) else ""
            attempt = _fallback_attempt_metadata(
                reservation=reservation,
                auth_record=auth_record,
                requested_model=model,
                primary_model=upstream_model,
                attempted_model=candidate_model,
                next_model=next_model,
                status_code=502,
                stream=False,
                outcome="retrying" if next_model else "failed",
                error_summary=error_summary,
                attempt_index=index,
                retryable=bool(next_model),
            )
            fallback_attempts.append(attempt)
            _record_fallback_attempt_event(config, attempt)
            if next_model:
                continue
            conn = _open_control_conn(config)
            try:
                _record_router_usage(
                    conn,
                    config,
                    reservation=reservation,
                    auth_record=auth_record,
                    model=candidate_model,
                    stream=False,
                    status="failed",
                    input_tokens=int(reservation.get("input_token_estimate") or 0),
                    output_tokens=0,
                    total_tokens=int(reservation.get("input_token_estimate") or 0),
                    source_kind="upstream_error",
                    error_summary=error_summary,
                    fallback_attempts=fallback_attempts,
                )
            finally:
                conn.close()
            return _router_error(502, "upstream_unavailable", "Chutes upstream request failed.")

        if upstream.status_code >= 400:
            error_summary = _safe_upstream_error(upstream.text)
            retryable = _upstream_status_is_retryable(config, upstream.status_code)
            next_model = candidates[index + 1] if retryable and index + 1 < len(candidates) else ""
            attempt = _fallback_attempt_metadata(
                reservation=reservation,
                auth_record=auth_record,
                requested_model=model,
                primary_model=upstream_model,
                attempted_model=candidate_model,
                next_model=next_model,
                status_code=upstream.status_code,
                stream=False,
                outcome="retrying" if next_model else "failed",
                error_summary=error_summary,
                attempt_index=index,
                retryable=retryable,
            )
            fallback_attempts.append(attempt)
            _record_fallback_attempt_event(config, attempt)
            if next_model:
                continue
            conn = _open_control_conn(config)
            try:
                _record_router_usage(
                    conn,
                    config,
                    reservation=reservation,
                    auth_record=auth_record,
                    model=candidate_model,
                    stream=False,
                    status="failed",
                    input_tokens=int(reservation.get("input_token_estimate") or 0),
                    output_tokens=0,
                    total_tokens=int(reservation.get("input_token_estimate") or 0),
                    source_kind="upstream_error",
                    error_summary=error_summary,
                    fallback_attempts=fallback_attempts,
                )
            finally:
                conn.close()
            return _router_error(upstream.status_code if upstream.status_code < 500 else 502, "upstream_error", error_summary or "Chutes upstream returned an error.")

        try:
            parsed = upstream.json()
        except Exception:
            error_summary = _safe_upstream_error(upstream.text)
            next_model = candidates[index + 1] if index + 1 < len(candidates) else ""
            attempt = _fallback_attempt_metadata(
                reservation=reservation,
                auth_record=auth_record,
                requested_model=model,
                primary_model=upstream_model,
                attempted_model=candidate_model,
                next_model=next_model,
                status_code=502,
                stream=False,
                outcome="retrying" if next_model else "failed",
                error_summary=error_summary,
                attempt_index=index,
                retryable=bool(next_model),
            )
            fallback_attempts.append(attempt)
            _record_fallback_attempt_event(config, attempt)
            if next_model:
                continue
            conn = _open_control_conn(config)
            try:
                _record_router_usage(
                    conn,
                    config,
                    reservation=reservation,
                    auth_record=auth_record,
                    model=candidate_model,
                    stream=False,
                    status="failed",
                    input_tokens=int(reservation.get("input_token_estimate") or 0),
                    output_tokens=0,
                    total_tokens=int(reservation.get("input_token_estimate") or 0),
                    source_kind="invalid_upstream_json",
                    error_summary=error_summary,
                    fallback_attempts=fallback_attempts,
                )
            finally:
                conn.close()
            return _router_error(502, "invalid_upstream_response", "Chutes upstream returned invalid JSON.")
        data = parsed if isinstance(parsed, dict) else {}
        source_kind = "provider_usage"
        break

    input_tokens, output_tokens, total_tokens, source_kind = _usage_from_payload(
        data,
        fallback_input_tokens=int(reservation.get("input_token_estimate") or 0),
        fallback_output_tokens=0,
    )
    if final_model != upstream_model or fallback_attempts:
        data.setdefault(
            "arclink_router",
            _router_metadata_for_response(
                requested_model=model,
                primary_model=upstream_model,
                final_model=final_model,
                fallback_attempts=fallback_attempts,
            ),
        )
    conn = _open_control_conn(config)
    try:
        _record_router_usage(
            conn,
            config,
            reservation=reservation,
            auth_record=auth_record,
            model=final_model,
            stream=False,
            status="succeeded",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            source_kind=source_kind,
            fallback_attempts=fallback_attempts,
        )
    finally:
        conn.close()
    return JSONResponse(status_code=upstream.status_code if upstream is not None else 200, content=data)


async def _stream_upstream_response(
    request: Request,
    config: RouterConfig,
    *,
    auth_record: Mapping[str, Any],
    reservation: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> AsyncIterator[bytes]:
    model = str(payload.get("model") or "").strip()
    upstream_model = str(reservation.get("upstream_model") or model).strip()
    # Outage fix: iterate the allow-filtered candidate list computed at preflight
    # (primary + only permitted/active fallbacks); raw list only as a safe default.
    candidates = _reservation_fallback_candidates(config, reservation, upstream_model)
    # missed-H: cap forwarded output to the same bound the reservation priced.
    reserved_output_tokens = int(reservation.get("output_token_estimate") or 0)
    # C1 multi-completion: clamp the forwarded fan-out to the priced count.
    reserved_completions = int(reservation.get("effective_completions") or 1)
    input_tokens = int(reservation.get("input_token_estimate") or 0)
    output_tokens = 0
    total_tokens = input_tokens
    source_kind = "fallback_estimate"
    status = "succeeded"
    error_summary = ""
    final_model = upstream_model
    fallback_attempts: list[dict[str, Any]] = []
    streaming_fallback = ""
    yielded_any = False
    # billing-H2: accumulate the assistant text actually streamed so a mid-stream
    # failure (no terminal usage block) can settle the emitted output as a floor
    # instead of charging $0 for tokens the provider already billed.
    emitted_output_chars = 0
    try:
        client = _upstream_client(config, request.app.state)
        for index, candidate_model in enumerate(candidates):
            final_model = candidate_model
            # C2 retry-heartbeat fix: the pre-first-chunk window of each streaming
            # attempt (connect + time-to-first-byte, bounded by the read timeout)
            # refreshes no heartbeat, so N pre-chunk retries could leave a LIVE
            # reservation un-heartbeated for N x read_timeout and the reaper would
            # false-expire it. Refresh at the START of every attempt (throttled,
            # best-effort) so a live request never goes longer than ONE read window
            # without a heartbeat regardless of retry count; the per-chunk touch
            # below keeps a long stream fresh once chunks begin.
            _touch_reservation_heartbeat(config, reservation)
            try:
                async with client.stream(
                    "POST",
                    _upstream_url(config, "chat/completions"),
                    json=_prepare_upstream_payload(
                        payload,
                        model=candidate_model,
                        max_output_tokens=reserved_output_tokens,
                        max_completions=reserved_completions,
                    ),
                    headers=_upstream_headers(config),
                ) as upstream:
                    if upstream.status_code >= 400:
                        status = "failed"
                        error_summary = _safe_upstream_error(await upstream.aread())
                        retryable = _upstream_status_is_retryable(config, upstream.status_code)
                        next_model = candidates[index + 1] if retryable and index + 1 < len(candidates) else ""
                        attempt = _fallback_attempt_metadata(
                            reservation=reservation,
                            auth_record=auth_record,
                            requested_model=model,
                            primary_model=upstream_model,
                            attempted_model=candidate_model,
                            next_model=next_model,
                            status_code=upstream.status_code,
                            stream=True,
                            outcome="retrying" if next_model else "failed",
                            error_summary=error_summary,
                            attempt_index=index,
                            retryable=retryable,
                        )
                        fallback_attempts.append(attempt)
                        _record_fallback_attempt_event(config, attempt)
                        if next_model:
                            streaming_fallback = "pre_stream"
                            continue
                        yield _sse_data(
                            {
                                "error": {
                                    "message": "Chutes upstream returned an error.",
                                    "type": "arclink_router_error",
                                    "code": "upstream_error",
                                },
                                "arclink_router": _router_metadata_for_response(
                                    requested_model=model,
                                    primary_model=upstream_model,
                                    final_model=candidate_model,
                                    fallback_attempts=fallback_attempts,
                                    streaming_fallback=streaming_fallback or "not_available",
                                ),
                            }
                        )
                        return
                    if fallback_attempts or candidate_model != upstream_model:
                        streaming_fallback = streaming_fallback or "pre_stream"
                        yield _sse_data(
                            {
                                "arclink_router": _router_metadata_for_response(
                                    requested_model=model,
                                    primary_model=upstream_model,
                                    final_model=candidate_model,
                                    fallback_attempts=fallback_attempts,
                                    streaming_fallback=streaming_fallback,
                                )
                            }
                        )
                    status = "succeeded"
                    error_summary = ""
                    async for chunk in upstream.aiter_bytes():
                        usage = _usage_from_sse_chunk(chunk)
                        if usage is not None:
                            input_tokens, output_tokens, total_tokens = usage
                            source_kind = "provider_usage"
                        else:
                            # billing-H2: count emitted assistant text as a local
                            # floor in case the stream fails before any usage block.
                            emitted_output_chars += _emitted_output_chars_from_sse_chunk(chunk)
                        yielded_any = True
                        # C2: a long stream legitimately outlives the per-chunk
                        # read timeout; refresh the reservation heartbeat (throttled)
                        # so the reaper never expires this still-live reservation.
                        _touch_reservation_heartbeat(config, reservation)
                        yield chunk
                    return
            except (httpx.HTTPError, OSError) as exc:
                status = "failed"
                error_summary = _safe_upstream_error(str(exc))
                next_model = candidates[index + 1] if (not yielded_any and index + 1 < len(candidates)) else ""
                outcome = "retrying" if next_model else ("failed_after_stream_started" if yielded_any else "failed")
                attempt = _fallback_attempt_metadata(
                    reservation=reservation,
                    auth_record=auth_record,
                    requested_model=model,
                    primary_model=upstream_model,
                    attempted_model=candidate_model,
                    next_model=next_model,
                    status_code=502,
                    stream=True,
                    outcome=outcome,
                    error_summary=error_summary,
                    attempt_index=index,
                    retryable=bool(next_model),
                )
                fallback_attempts.append(attempt)
                _record_fallback_attempt_event(config, attempt)
                if next_model:
                    streaming_fallback = "pre_stream"
                    continue
                if yielded_any:
                    streaming_fallback = streaming_fallback or "unavailable_after_stream_started"
                yield _sse_data(
                    {
                        "error": {
                            "message": "Chutes upstream request failed.",
                            "type": "arclink_router_error",
                            "code": "upstream_unavailable",
                        },
                        "arclink_router": _router_metadata_for_response(
                            requested_model=model,
                            primary_model=upstream_model,
                            final_model=candidate_model,
                            fallback_attempts=fallback_attempts,
                            streaming_fallback=streaming_fallback or "not_available",
                        ),
                    }
                )
                return
    except (asyncio.CancelledError, GeneratorExit):
        status = "cancelled"
        error_summary = "client disconnected before the streaming response completed"
        raise
    finally:
        settle_partial_output_tokens = 0
        if source_kind == "fallback_estimate" and status == "succeeded":
            # regr-M6: ``output_token_estimate`` is the PER-COMPLETION cap; an n>1
            # request sampled the output ``effective_completions`` times, so the
            # no-usage fallback must scale by the completion count or it under-charges
            # an n-way stream by a factor of n.
            per_completion_output = int(reservation.get("output_token_estimate") or 0)
            effective_completions = max(1, int(reservation.get("effective_completions") or 1))
            output_tokens = per_completion_output * effective_completions
            total_tokens = input_tokens + output_tokens
        elif status != "succeeded" and yielded_any and output_tokens <= 0:
            # billing-H2: the stream failed after emitting output. The provider has
            # already billed the tokens it produced, so settle the partial output
            # actually emitted (local floor) instead of charging $0. Summing the
            # streamed assistant text covers the n>1 fan-out (every completion's
            # delta is counted) without scaling separately. The request status stays
            # "failed" for analytics; only the settlement floor is applied.
            settle_partial_output_tokens = max(0, emitted_output_chars) // 4
        conn = _open_control_conn(config)
        try:
            _record_router_usage(
                conn,
                config,
                reservation=reservation,
                auth_record=auth_record,
                model=final_model,
                stream=True,
                status=status,
                settle_partial_output_tokens=settle_partial_output_tokens,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                source_kind=source_kind if status == "succeeded" else ("client_cancelled" if status == "cancelled" else "upstream_error"),
                error_summary=error_summary,
                fallback_attempts=fallback_attempts,
                streaming_fallback=streaming_fallback,
            )
        finally:
            conn.close()


def create_app(
    config: RouterConfig | None = None,
    *,
    upstream_transport: httpx.AsyncBaseTransport | None = None,
    catalog_http_client: Any | None = None,
) -> FastAPI:
    router_config = config or load_router_config()
    app = FastAPI(title="ArcLink LLM Router", version="0.1.0")
    app.state.router_config = router_config
    app.state.router_upstream_transport = upstream_transport
    app.state.router_upstream_clients = {}
    app.state.router_upstream_warmup = {"status": "pending" if router_config.upstream_warmup_enabled else "disabled"}
    app.state.router_catalog_refresh = {"status": "pending" if router_config.refresh_model_catalog_on_startup else "disabled"}

    @app.on_event("startup")
    async def router_startup() -> None:
        app.state.router_upstream_warmup = await _warm_up_upstream_pool(router_config, app.state)
        # C2: clear reservations leaked by a worker that crashed before its prior
        # process settled them, so a restart does not inherit phantom budget holds.
        if router_config.configured:
            try:
                conn = _open_control_conn(router_config)
                try:
                    app.state.router_reservation_reaped = _reap_stale_reservations(conn, router_config)
                finally:
                    conn.close()
            except sqlite3.Error as exc:
                app.state.router_reservation_reaped = {"status": "failed", "error": _safe_upstream_error(str(exc))}
        if router_config.refresh_model_catalog_on_startup:
            try:
                app.state.router_catalog_refresh = await asyncio.to_thread(
                    _refresh_model_catalog_once,
                    router_config,
                    http_client=catalog_http_client,
                )
            except (ChutesCatalogError, sqlite3.Error, OSError, ValueError) as exc:
                app.state.router_catalog_refresh = {
                    "status": "failed",
                    "error": _safe_upstream_error(str(exc)),
                }
        else:
            app.state.router_catalog_refresh = {"status": "disabled"}

    @app.on_event("shutdown")
    async def router_shutdown() -> None:
        await _close_upstream_clients(app.state)

    @app.get("/health")
    async def health() -> JSONResponse:
        payload = router_config.public_status()
        payload["model_catalog_refresh"] = dict(getattr(app.state, "router_catalog_refresh", {}) or {})
        payload["upstream_warmup"] = dict(getattr(app.state, "router_upstream_warmup", {}) or {})
        # H3: surface synced-vs-fallback allow-list state, and alert the Operator
        # once if the synced catalog collapsed to the env default-only fallback.
        if router_config.configured:
            try:
                conn = _open_control_conn(router_config)
                try:
                    allow_list_state = _router_allow_list_state(conn, router_config)
                    payload["allow_list"] = allow_list_state
                    _report_allow_list_collapse(conn, allow_list_state)
                finally:
                    conn.close()
            except sqlite3.Error as exc:
                payload["allow_list"] = {"status": "unavailable", "error": _safe_upstream_error(str(exc))}
        status_code = 200 if router_config.configured else 503
        return JSONResponse(status_code=status_code, content=payload)

    @app.get("/v1/models")
    async def models(request: Request) -> JSONResponse:
        not_configured = _require_configured(router_config)
        if not_configured is not None:
            return not_configured
        auth_record, auth_error = _authenticate_request(router_config, request)
        if auth_error is not None:
            return auth_error
        allowed_models = tuple(auth_record.get("allowed_models") or ()) if auth_record else ()
        if not allowed_models:
            # Reflect the synced Chutes -TEE catalog for the global allow-list,
            # mirroring the per-request enforcement in _preflight_chat_request.
            try:
                conn = _open_control_conn(router_config)
                try:
                    allowed_models = _effective_global_allowed_models(conn, router_config)
                finally:
                    conn.close()
            except sqlite3.Error:
                allowed_models = router_config.allowed_models
        return JSONResponse(
            {
                "object": "list",
                "data": [
                    {
                        "id": model,
                        "object": "model",
                        "created": 0,
                        "owned_by": "arclink-chutes",
                    }
                    for model in allowed_models
                ],
            }
        )

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        not_configured = _require_configured(router_config)
        if not_configured is not None:
            return not_configured
        auth_record, auth_error = _authenticate_request(router_config, request)
        if auth_error is not None:
            return auth_error
        payload, body_error, body = await _read_json_body(router_config, request)
        if body_error is not None:
            return body_error
        reservation: dict[str, Any] | None = None
        try:
            conn = _open_control_conn(router_config)
            try:
                reservation, preflight_error = _preflight_chat_request(conn, router_config, auth_record or {}, payload or {}, body)
                if preflight_error is not None:
                    return preflight_error
            finally:
                conn.close()
        except sqlite3.Error:
            return _router_error(503, "router_db_unavailable", "ArcLink LLM router key database is unavailable.")
        if not reservation:
            return _router_error(500, "reservation_failed", "ArcLink LLM router could not reserve request budget.")
        if _truthy(str((payload or {}).get("stream") or "")):
            return StreamingResponse(
                _stream_upstream_response(
                    request,
                    router_config,
                    auth_record=auth_record or {},
                    reservation=reservation,
                    payload=payload or {},
                ),
                media_type="text/event-stream",
            )
        return await _forward_non_streaming(
            request,
            router_config,
            auth_record=auth_record or {},
            reservation=reservation,
            payload=payload or {},
        )

    return app


app = create_app()
