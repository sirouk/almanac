#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Mapping

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from arclink_chutes import ChutesCatalogClient, ChutesCatalogError, evaluate_chutes_deployment_boundary, record_chutes_usage_event
from arclink_control import (
    ensure_schema,
    get_model_catalog_entry,
    latest_model_in_family,
    model_family_key,
    rate_limit_count,
    record_rate_limit_event,
    upsert_model_catalog,
    verify_llm_router_key,
)
from arclink_secrets_regex import redact_then_truncate


DEFAULT_CHUTES_BASE_URL = "https://llm.chutes.ai/v1"
DEFAULT_MODEL = "moonshotai/Kimi-K2.6-TEE"
DEFAULT_MAX_BODY_BYTES = 1024 * 1024
DEFAULT_PROMPT_ESTIMATE_TOKEN_CAP = 120000
DEFAULT_MAX_TOKENS_CAP = 8192
DEFAULT_DEPLOYMENT_CONCURRENCY_LIMIT = 4
DEFAULT_KEY_REQUESTS_PER_MINUTE = 60
DEFAULT_DEPLOYMENT_REQUESTS_PER_MINUTE = 120
DEFAULT_USER_REQUESTS_PER_MINUTE = 300
DEFAULT_MIN_RESERVATION_CENTS = 1
DEFAULT_INPUT_CENTS_PER_MILLION = 95
DEFAULT_OUTPUT_CENTS_PER_MILLION = 400


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
    deployment_concurrency_limit: int
    key_requests_per_minute: int
    deployment_requests_per_minute: int
    user_requests_per_minute: int
    min_reservation_cents: int
    default_monthly_budget_cents: int
    input_cents_per_million: int
    output_cents_per_million: int

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
    conn = sqlite3.connect(config.db_path)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


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
    conn = _open_control_conn(config)
    try:
        rows = upsert_model_catalog(
            conn,
            provider="chutes",
            models=models,
            mark_missing_unavailable=config.mark_missing_models_unavailable,
        )
    finally:
        conn.close()
    return {
        "status": "ok",
        "model_count": len(rows),
        "mark_missing_unavailable": config.mark_missing_models_unavailable,
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
        ensure_schema(conn)
        try:
            record = verify_llm_router_key(conn, raw_key)
        finally:
            conn.close()
    except sqlite3.Error:
        return None, _router_error(503, "router_db_unavailable", "ArcLink LLM router key database is unavailable.")
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
    body = await request.body()
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


def _requested_max_tokens(payload: Mapping[str, Any]) -> int:
    for name in ("max_tokens", "max_completion_tokens"):
        if name in payload:
            return max(0, _clean_int(payload.get(name), 0))
    return 0


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
) -> int:
    input_cents, output_cents, _ = _model_price_cents(config, catalog_entry)
    output_tokens = max_tokens if max_tokens > 0 else min(config.max_tokens_cap, 1024)
    estimated = ((max(0, input_tokens) * input_cents) + (max(0, output_tokens) * output_cents) + 999999) // 1000000
    return max(config.min_reservation_cents, int(estimated))


def _estimate_usage_cents(config: RouterConfig, input_tokens: int, output_tokens: int, catalog_entry: Mapping[str, Any] | None = None) -> int:
    input_cents, output_cents, _ = _model_price_cents(config, catalog_entry)
    estimated = (
        (max(0, input_tokens) * input_cents)
        + (max(0, output_tokens) * output_cents)
        + 999999
    ) // 1000000
    return max(0, int(estimated))


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


def _router_model_allowed(config: RouterConfig, model: str, allowed_models: tuple[str, ...]) -> bool:
    clean_model = str(model or "").strip()
    if not clean_model:
        return False
    if clean_model in allowed_models:
        return True
    # Some providers accept a comma-bearing model string as provider-side
    # fallback. Preserve that as a single default model even when the allowlist
    # itself is represented as comma-separated values.
    return bool(config.default_model and clean_model == config.default_model)


def _router_fallback_candidates(config: RouterConfig, primary_model: str) -> tuple[str, ...]:
    candidates: list[str] = []
    for model in (str(primary_model or "").strip(), *config.fallback_models):
        clean = str(model or "").strip()
        if clean and clean not in candidates:
            candidates.append(clean)
    return tuple(candidates)


def _upstream_status_is_retryable(config: RouterConfig, status_code: int) -> bool:
    if int(status_code) in set(config.fallback_status_codes):
        return True
    return int(status_code) >= 500


def _safe_upstream_error(value: Any) -> str:
    return redact_then_truncate(value, limit=300)


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


def _record_rate_limits(conn: sqlite3.Connection, auth_record: Mapping[str, Any]) -> None:
    key_id = str(auth_record.get("key_id") or "")
    deployment_id = str(auth_record.get("deployment_id") or "")
    user_id = str(auth_record.get("user_id") or "")
    for scope, subject in (
        ("llm-router:key", key_id),
        ("llm-router:deployment", deployment_id),
        ("llm-router:user", user_id),
    ):
        if subject:
            record_rate_limit_event(conn, scope, subject)


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


def _create_budget_reservation(
    conn: sqlite3.Connection,
    *,
    request_id: str,
    deployment_id: str,
    user_id: str,
    reserved_cents: int,
) -> dict[str, Any]:
    reservation_id = f"llmres_{uuid.uuid4().hex[:24]}"
    conn.execute(
        """
        INSERT INTO arclink_llm_budget_reservations (
          reservation_id, request_id, deployment_id, user_id, reserved_cents, status, created_at
        ) VALUES (?, ?, ?, ?, ?, 'reserved', ?)
        """,
        (reservation_id, request_id, deployment_id, user_id, max(1, int(reserved_cents)), _utc_now_iso()),
    )
    conn.commit()
    return {
        "reservation_id": reservation_id,
        "request_id": request_id,
        "deployment_id": deployment_id,
        "user_id": user_id,
        "reserved_cents": max(1, int(reserved_cents)),
    }


def _release_budget_reservation(conn: sqlite3.Connection, reservation_id: str, *, status: str = "released", settled_cents: int = 0) -> None:
    conn.execute(
        """
        UPDATE arclink_llm_budget_reservations
        SET status = ?, settled_cents = ?, settled_at = ?
        WHERE reservation_id = ? AND status = 'reserved'
        """,
        (status, max(0, int(settled_cents)), _utc_now_iso(), reservation_id),
    )
    conn.commit()


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
                json.dumps(_fuel_notice_actions(), sort_keys=True),
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
                json.dumps(
                    {
                        "user_id": clean_user,
                        "notice_key": notice_key,
                        "severity": severity,
                        "remaining_cents": remaining,
                        "monthly_budget_cents": monthly_budget,
                        "usage_percent": usage_percent,
                        "notification_id": notification_id,
                    },
                    sort_keys=True,
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
    allowed_models = tuple(auth_record.get("allowed_models") or ()) or config.allowed_models
    if not _router_model_allowed(config, model, allowed_models):
        return None, _router_error(403, "model_not_allowed", "Requested model is not allowed for this ArcPod.")
    upstream_model, catalog_entry, model_resolution = _resolve_router_model(conn, config, model, allowed_models)

    prompt_tokens = _estimate_prompt_tokens(payload, body)
    if prompt_tokens > config.prompt_estimate_token_cap:
        return None, _router_error(413, "prompt_too_large", "ArcLink LLM router prompt estimate exceeds the configured cap.")
    max_tokens = _requested_max_tokens(payload)
    if max_tokens > config.max_tokens_cap:
        return None, _router_error(400, "max_tokens_too_large", "Requested max_tokens exceeds the ArcLink LLM router cap.")

    metadata, billing_state = _load_deployment_context(conn, auth_record)
    boundary = evaluate_chutes_deployment_boundary(
        str(auth_record.get("deployment_id") or ""),
        str(auth_record.get("user_id") or ""),
        _router_boundary_metadata(metadata, auth_record),
        env={
            "ARCLINK_CHUTES_DEFAULT_MONTHLY_BUDGET_CENTS": str(config.default_monthly_budget_cents),
            "ARCLINK_CHUTES_WARNING_THRESHOLD_PERCENT": "80",
            "ARCLINK_CHUTES_HARD_LIMIT_PERCENT": "100",
        },
        billing_state=billing_state,
    )
    if not boundary.allow_inference:
        status_code = 402 if boundary.credential_state in {"billing_suspended", "budget_unconfigured", "budget_exhausted"} else 403
        if boundary.credential_state == "budget_exhausted":
            _queue_arc_pod_fuel_notice(
                conn,
                deployment_id=str(auth_record.get("deployment_id") or ""),
                user_id=str(auth_record.get("user_id") or ""),
                boundary=boundary,
                severity="empty",
            )
        return None, _router_error(status_code, boundary.credential_state, boundary.reason)

    for scope, subject, limit in (
        ("llm-router:key", str(auth_record.get("key_id") or ""), config.key_requests_per_minute),
        ("llm-router:deployment", str(auth_record.get("deployment_id") or ""), config.deployment_requests_per_minute),
        ("llm-router:user", str(auth_record.get("user_id") or ""), config.user_requests_per_minute),
    ):
        error = _check_rate_limit(conn, scope=scope, subject=subject, limit=limit)
        if error is not None:
            return None, error

    deployment_id = str(auth_record.get("deployment_id") or "")
    if _open_reserved_count(conn, deployment_id) >= config.deployment_concurrency_limit:
        return None, _json_error(
            429,
            "concurrency_limited",
            "ArcLink LLM router deployment concurrency limit exceeded.",
            retry_after=1,
        )

    reserved_cents = _estimate_reservation_cents_for_model(config, catalog_entry, prompt_tokens, max_tokens)
    if boundary.remaining_cents < reserved_cents:
        _queue_arc_pod_fuel_notice(
            conn,
            deployment_id=str(auth_record.get("deployment_id") or ""),
            user_id=str(auth_record.get("user_id") or ""),
            boundary=boundary,
            severity="low",
        )
        return None, _router_error(402, "budget_exhausted", "Chutes budget remaining is below the required request reservation.")

    _record_rate_limits(conn, auth_record)
    request_id = f"llmreq_{uuid.uuid4().hex[:24]}"
    reservation = _create_budget_reservation(
        conn,
        request_id=request_id,
        deployment_id=deployment_id,
        user_id=str(auth_record.get("user_id") or ""),
        reserved_cents=reserved_cents,
    )
    reservation["input_token_estimate"] = prompt_tokens
    reservation["output_token_estimate"] = max_tokens if max_tokens > 0 else min(config.max_tokens_cap, 1024)
    reservation["requested_model"] = model
    reservation["upstream_model"] = upstream_model
    reservation["model_pricing"] = dict(catalog_entry or {})
    reservation["model_resolution"] = model_resolution
    reservation["pricing_source"] = _model_price_cents(config, catalog_entry)[2]
    return reservation, None


def _prepare_upstream_payload(payload: Mapping[str, Any], *, model: str = "") -> dict[str, Any]:
    prepared = dict(payload)
    if model:
        prepared["model"] = model
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


def _upstream_client(config: RouterConfig, app_state: Any) -> httpx.AsyncClient:
    transport = getattr(app_state, "router_upstream_transport", None)
    return httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(60.0, connect=10.0))


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
) -> int:
    pricing_entry = reservation.get("model_pricing") if isinstance(reservation.get("model_pricing"), Mapping) else None
    actual_cents = _estimate_usage_cents(config, input_tokens, output_tokens, pricing_entry) if status == "succeeded" else 0
    estimated_cents = int(reservation.get("reserved_cents") or 0)
    now = _utc_now_iso()
    usage_id = f"llmuse_{uuid.uuid4().hex[:24]}"
    request_id = str(reservation.get("request_id") or "")
    deployment_id = str(auth_record.get("deployment_id") or reservation.get("deployment_id") or "")
    user_id = str(auth_record.get("user_id") or reservation.get("user_id") or "")
    conn.execute(
        """
        INSERT INTO arclink_llm_usage_events (
          usage_id, request_id, deployment_id, user_id, provider, model,
          input_tokens, output_tokens, total_tokens, estimated_cents, actual_cents,
          status, stream, source_kind, error_summary, started_at, completed_at
        ) VALUES (?, ?, ?, ?, 'chutes', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            now,
            now,
        ),
    )
    if status == "succeeded":
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
                "output_tokens": max(0, int(output_tokens)),
                "total_tokens": max(0, int(total_tokens)),
                "delta_cents": actual_cents,
            },
            env={
                "ARCLINK_CHUTES_DEFAULT_MONTHLY_BUDGET_CENTS": str(config.default_monthly_budget_cents),
                "ARCLINK_CHUTES_WARNING_THRESHOLD_PERCENT": "80",
                "ARCLINK_CHUTES_HARD_LIMIT_PERCENT": "100",
            },
            commit=False,
        )
        if usage_result.boundary.budget_status in {"warning", "exhausted"}:
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
    candidates = _router_fallback_candidates(config, upstream_model)
    fallback_errors: list[dict[str, Any]] = []
    upstream = None
    final_model = upstream_model
    data: dict[str, Any] = {}
    source_kind = "provider_usage"

    async with _upstream_client(config, request.app.state) as client:
        for index, candidate_model in enumerate(candidates):
            final_model = candidate_model
            try:
                upstream = await client.post(
                    _upstream_url(config, "chat/completions"),
                    json=_prepare_upstream_payload(payload, model=candidate_model),
                    headers=_upstream_headers(config),
                )
            except httpx.HTTPError as exc:
                error_summary = _safe_upstream_error(str(exc))
                fallback_errors.append({"model": candidate_model, "status_code": 502, "error": error_summary})
                if index + 1 < len(candidates):
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
                    )
                finally:
                    conn.close()
                return _router_error(502, "upstream_unavailable", "Chutes upstream request failed.")

            if upstream.status_code >= 400:
                error_summary = _safe_upstream_error(upstream.text)
                fallback_errors.append({"model": candidate_model, "status_code": upstream.status_code, "error": error_summary})
                if _upstream_status_is_retryable(config, upstream.status_code) and index + 1 < len(candidates):
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
                    )
                finally:
                    conn.close()
                return _router_error(upstream.status_code if upstream.status_code < 500 else 502, "upstream_error", error_summary or "Chutes upstream returned an error.")

            try:
                parsed = upstream.json()
            except Exception:
                error_summary = _safe_upstream_error(upstream.text)
                fallback_errors.append({"model": candidate_model, "status_code": 502, "error": error_summary})
                if index + 1 < len(candidates):
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
    if final_model != upstream_model or fallback_errors:
        data.setdefault(
            "arclink_router",
            {
                "requested_model": model,
                "primary_model": upstream_model,
                "upstream_model": final_model,
                "fallback_used": final_model != upstream_model,
                "fallback_attempts": [
                    {"model": item["model"], "status_code": item["status_code"]}
                    for item in fallback_errors
                ],
            },
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
    input_tokens = int(reservation.get("input_token_estimate") or 0)
    output_tokens = 0
    total_tokens = input_tokens
    source_kind = "fallback_estimate"
    status = "succeeded"
    error_summary = ""
    try:
        async with _upstream_client(config, request.app.state) as client:
            async with client.stream(
                "POST",
                _upstream_url(config, "chat/completions"),
                json=_prepare_upstream_payload(payload, model=upstream_model),
                headers=_upstream_headers(config),
            ) as upstream:
                if upstream.status_code >= 400:
                    status = "failed"
                    error_summary = _safe_upstream_error(await upstream.aread())
                    yield (
                        "data: "
                        + '{"error":{"message":"Chutes upstream returned an error.","type":"arclink_router_error","code":"upstream_error"}}'
                        + "\n\n"
                    ).encode("utf-8")
                    return
                async for chunk in upstream.aiter_bytes():
                    usage = _usage_from_sse_chunk(chunk)
                    if usage is not None:
                        input_tokens, output_tokens, total_tokens = usage
                        source_kind = "provider_usage"
                    yield chunk
    except (httpx.HTTPError, OSError) as exc:
        status = "failed"
        error_summary = _safe_upstream_error(str(exc))
        yield (
            "data: "
            + '{"error":{"message":"Chutes upstream request failed.","type":"arclink_router_error","code":"upstream_unavailable"}}'
            + "\n\n"
        ).encode("utf-8")
    finally:
        if source_kind == "fallback_estimate" and status == "succeeded":
            output_tokens = int(reservation.get("output_token_estimate") or 0)
            total_tokens = input_tokens + output_tokens
        conn = _open_control_conn(config)
        try:
            _record_router_usage(
                conn,
                config,
                reservation=reservation,
                auth_record=auth_record,
                model=upstream_model,
                stream=True,
                status=status,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                source_kind=source_kind if status == "succeeded" else "upstream_error",
                error_summary=error_summary,
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
    app.state.router_catalog_refresh = {"status": "pending" if router_config.refresh_model_catalog_on_startup else "disabled"}

    @app.on_event("startup")
    async def refresh_model_catalog_on_startup() -> None:
        if not router_config.refresh_model_catalog_on_startup:
            app.state.router_catalog_refresh = {"status": "disabled"}
            return
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

    @app.get("/health")
    async def health() -> JSONResponse:
        payload = router_config.public_status()
        payload["model_catalog_refresh"] = dict(getattr(app.state, "router_catalog_refresh", {}) or {})
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
