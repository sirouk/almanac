#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib import request as urlrequest

from arclink_product import chutes_base_url, chutes_default_model


REQUIRED_CHUTES_CAPABILITIES = ("tools", "reasoning", "structured_outputs")
CURRENT_BILLING_STATES = frozenset({"paid", "comp"})
NONCURRENT_BILLING_STATES = frozenset({"past_due", "unpaid", "cancelled", "none"})
CHUTES_ACCEPTED_ISOLATION_MODES = (
    "per_deployment_secret_ref",
    "per_user_secret_ref",
    "per_user_chutes_account_oauth",
)


@dataclass(frozen=True)
class ChutesModel:
    model_id: str
    supports_tools: bool
    supports_reasoning: bool
    supports_structured_outputs: bool
    confidential_compute: bool
    raw: Mapping[str, Any]

    def missing_capabilities(self, *, require_confidential_compute: bool = True) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.supports_tools:
            missing.append("tools")
        if not self.supports_reasoning:
            missing.append("reasoning")
        if not self.supports_structured_outputs:
            missing.append("structured_outputs")
        if require_confidential_compute and not self.confidential_compute:
            missing.append("confidential_compute")
        return tuple(missing)


class ChutesCatalogError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChutesDeploymentBoundary:
    deployment_id: str
    user_id: str
    provider: str
    isolation_mode: str
    credential_state: str
    secret_ref_present: bool
    key_id: str
    monthly_budget_cents: int
    used_cents: int
    remaining_cents: int
    warning_threshold_percent: float
    hard_limit_percent: float
    usage_percent: float
    budget_status: str
    allow_inference: bool
    reason: str
    billing_state: str
    billing_lifecycle: Mapping[str, Any]

    def to_public(self, *, include_user_id: bool = False, include_admin_fields: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider": self.provider,
            "deployment_id": self.deployment_id,
            "isolation_mode": self.isolation_mode,
            "credential_state": self.credential_state,
            "secret_ref_present": self.secret_ref_present,
            "allow_inference": self.allow_inference,
            "reason": self.reason,
            "credential_lifecycle": chutes_credential_lifecycle(
                isolation_mode=self.isolation_mode,
                credential_state=self.credential_state,
                allow_inference=self.allow_inference,
            ),
            "budget": {
                "status": self.budget_status,
                "monthly_cents": self.monthly_budget_cents,
                "used_cents": self.used_cents,
                "remaining_cents": self.remaining_cents,
                "usage_percent": self.usage_percent,
                "warning_threshold_percent": self.warning_threshold_percent,
                "hard_limit_percent": self.hard_limit_percent,
                "limit_enforced": True,
            },
            "billing_lifecycle": dict(self.billing_lifecycle),
        }
        threshold_policy = chutes_threshold_continuation_policy(
            budget_status=self.budget_status,
            credential_state=self.credential_state,
        )
        if threshold_policy.get("status") != "not_applicable":
            payload["threshold_continuation"] = threshold_policy
        if include_user_id:
            payload["user_id"] = self.user_id
        if include_admin_fields:
            payload["key_id"] = _safe_public_identifier(self.key_id)
        return payload


@dataclass(frozen=True)
class ChutesUsageIngestionResult:
    deployment_id: str
    user_id: str
    usage_event_id: str
    recorded: bool
    delta_cents: int
    used_cents_before: int
    used_cents_after: int
    boundary: ChutesDeploymentBoundary

    def to_public(self, *, include_user_id: bool = False, include_admin_fields: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider": "chutes",
            "deployment_id": self.deployment_id,
            "usage_event_id": self.usage_event_id,
            "recorded": self.recorded,
            "delta_cents": self.delta_cents,
            "used_cents_before": self.used_cents_before,
            "used_cents_after": self.used_cents_after,
            "boundary": self.boundary.to_public(
                include_user_id=include_user_id,
                include_admin_fields=include_admin_fields,
            ),
        }
        if include_user_id:
            payload["user_id"] = self.user_id
        return payload


class ChutesHttpClient(Protocol):
    def get_json(self, path: str, *, headers: Mapping[str, str] | None = None) -> Mapping[str, Any]:
        ...


class UrlLibChutesHttpClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def get_json(self, path: str, *, headers: Mapping[str, str] | None = None) -> Mapping[str, Any]:
        request = urlrequest.Request(self.base_url + path, headers=dict(headers or {}))
        with urlrequest.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ChutesCatalogError("Chutes catalog response was not an object")
        return payload


class ChutesCatalogClient:
    def __init__(self, http_client: ChutesHttpClient | None = None, *, base_url: str = "") -> None:
        self.http_client = http_client or UrlLibChutesHttpClient(base_url or chutes_base_url())

    def list_models(self, *, api_key: str = "", auth_strategy: str = "x-api-key") -> dict[str, ChutesModel]:
        headers: dict[str, str] = {}
        if api_key:
            if auth_strategy == "x-api-key":
                headers["X-API-Key"] = api_key
            elif auth_strategy == "bearer":
                headers["Authorization"] = f"Bearer {api_key}"
            else:
                raise ChutesCatalogError(f"unsupported Chutes auth strategy: {auth_strategy}")
        payload = self.http_client.get_json("/models", headers=headers)
        return parse_chutes_models(payload)


def _bool_from_model(model: Mapping[str, Any], *keys: str) -> bool:
    capabilities = model.get("capabilities")
    if isinstance(capabilities, Mapping):
        for key in keys:
            if bool(capabilities.get(key)):
                return True
    for key in keys:
        if bool(model.get(key)):
            return True
    return False


def parse_chutes_models(payload: Mapping[str, Any]) -> dict[str, ChutesModel]:
    data = payload.get("data")
    if not isinstance(data, list):
        raise ChutesCatalogError("Chutes catalog response is missing data[]")
    models: dict[str, ChutesModel] = {}
    for item in data:
        if not isinstance(item, Mapping):
            continue
        model_id = str(item.get("id") or "").strip()
        if not model_id:
            continue
        models[model_id] = ChutesModel(
            model_id=model_id,
            supports_tools=_bool_from_model(item, "tools", "tool_calls", "function_calling"),
            supports_reasoning=_bool_from_model(item, "reasoning", "thinking"),
            supports_structured_outputs=_bool_from_model(item, "structured_outputs", "json_schema"),
            confidential_compute=_bool_from_model(item, "confidential_compute", "tee", "trusted_execution"),
            raw=dict(item),
        )
    return models


def validate_default_chutes_model(
    models: Mapping[str, ChutesModel],
    *,
    env: Mapping[str, str] | None = None,
    require_confidential_compute: bool = True,
) -> ChutesModel:
    model_id = chutes_default_model(env)
    model = models.get(model_id)
    if model is None:
        raise ChutesCatalogError(f"configured default Chutes model is not in catalog: {model_id}")
    missing = model.missing_capabilities(require_confidential_compute=require_confidential_compute)
    if missing:
        raise ChutesCatalogError(f"configured default Chutes model lacks required capabilities: {', '.join(missing)}")
    return model


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_public_identifier(value: Any) -> str:
    text = _clean_text(value)
    lowered = text.lower()
    if not text:
        return ""
    if any(marker in lowered for marker in ("secret", "token", "password", "api_key", "apikey", "sk_", "whsec_")):
        return ""
    return text


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _truthy(value: Any) -> bool:
    return _clean_text(value).lower() in {"1", "true", "yes", "on", "suspended"}


def _clean_int(value: Any, default: int = 0) -> int:
    text = _clean_text(value)
    if not text:
        return max(0, int(default))
    try:
        return max(0, int(float(text)))
    except (TypeError, ValueError):
        return max(0, int(default))


def _clean_percent(value: Any, default: float) -> float:
    text = _clean_text(value)
    if not text:
        return float(default)
    try:
        parsed = float(text)
    except (TypeError, ValueError):
        return float(default)
    if 0 < parsed <= 1:
        parsed *= 100
    return max(0.0, parsed)


def _first_text(*values: Any) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_loads_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    try:
        payload = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _json_dumps_object(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"), default=str)


def _clean_money_cents(event: Mapping[str, Any]) -> int:
    cents = _first_text(
        event.get("cost_cents"),
        event.get("usage_cents"),
        event.get("spent_cents"),
        event.get("amount_cents"),
        event.get("delta_cents"),
    )
    if cents:
        return _clean_int(cents)
    dollars = _first_text(event.get("cost_usd"), event.get("amount_usd"), event.get("usd"))
    if not dollars:
        return 0
    try:
        return max(0, int(round(float(dollars) * 100)))
    except (TypeError, ValueError):
        return 0


def _safe_usage_text(value: Any, *, fallback: str = "", max_len: int = 160) -> str:
    clean = _safe_public_identifier(value)
    if not clean:
        return fallback
    return clean[:max_len]


def _usage_event_identity(deployment_id: str, event: Mapping[str, Any]) -> tuple[str, str]:
    external_id = _first_text(
        event.get("usage_event_id"),
        event.get("event_id"),
        event.get("idempotency_key"),
        event.get("request_id"),
        event.get("completion_id"),
    )
    canonical = _json_dumps_object(event)
    digest_source = f"{deployment_id}\0{external_id or canonical}"
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:24]
    public_id = _safe_usage_text(external_id, fallback=f"metered-{digest}", max_len=96)
    return f"chutes_usage_{digest}", public_id


def _usage_event_metadata(
    *,
    event: Mapping[str, Any],
    public_usage_event_id: str,
    delta_cents: int,
    used_cents_before: int,
    used_cents_after: int,
    now: str,
) -> dict[str, Any]:
    input_tokens = _clean_int(_first_text(event.get("input_tokens"), event.get("prompt_tokens")))
    output_tokens = _clean_int(_first_text(event.get("output_tokens"), event.get("completion_tokens")))
    total_tokens = _clean_int(event.get("total_tokens"))
    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens
    return {
        "provider": "chutes",
        "usage_event_id": public_usage_event_id,
        "request_id": _safe_usage_text(event.get("request_id"), max_len=96),
        "completion_id": _safe_usage_text(event.get("completion_id"), max_len=96),
        "model_id": _safe_usage_text(event.get("model_id") or event.get("model"), max_len=160),
        "source": _safe_usage_text(event.get("source"), fallback="runtime-meter", max_len=80),
        "observed_at": _safe_usage_text(event.get("observed_at"), fallback=now, max_len=64),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "delta_cents": delta_cents,
        "used_cents_before": used_cents_before,
        "used_cents_after": used_cents_after,
    }


def renewal_lifecycle_for_billing_state(billing_state: str = "") -> dict[str, str]:
    """Return the approved local failed-renewal lifecycle."""
    clean_state = _clean_text(billing_state).lower()
    if not clean_state:
        return {
            "payment_state": "not_evaluated",
            "provider_access": "not_evaluated",
            "warning_cadence": "not_evaluated",
            "grace_period": "not_evaluated",
            "data_retention": "not_evaluated",
            "purge_policy": "not_evaluated",
            "reason": "Billing state was not supplied for this local provider evaluation.",
        }
    if clean_state in CURRENT_BILLING_STATES:
        return {
            "payment_state": clean_state,
            "provider_access": "allowed",
            "warning_cadence": "not_applicable",
            "grace_period": "not_applicable",
            "data_retention": "active",
            "purge_policy": "not_applicable",
            "reason": "Billing is current for this deployment.",
        }
    if clean_state in NONCURRENT_BILLING_STATES:
        return {
            "payment_state": clean_state,
            "provider_access": "suspended",
            "warning_cadence": "immediate_notice_then_daily_reminders",
            "grace_period": "provider_suspended_immediately",
            "data_retention": "account_data_removed_warning_day_7",
            "purge_policy": "audited_purge_queue_day_14",
            "day_7_action": "warn_account_and_data_removal",
            "day_14_action": "queue_audited_purge",
            "reason": (
                "Payment is not current; ArcLink suspends provider access locally "
                "until billing is satisfied, sends an immediate Raven notice, "
                "reminds daily, warns on day 7 that account/data removal is next, "
                "and queues audited purge review on day 14."
            ),
        }
    return {
        "payment_state": clean_state,
        "provider_access": "suspended",
        "warning_cadence": "immediate_notice_then_daily_reminders",
        "grace_period": "provider_suspended_immediately",
        "data_retention": "account_data_removed_warning_day_7",
        "purge_policy": "audited_purge_queue_day_14",
        "day_7_action": "warn_account_and_data_removal",
        "day_14_action": "queue_audited_purge",
        "reason": "Billing state is unknown; ArcLink fails provider access closed until billing is resolved.",
    }


def chutes_threshold_continuation_policy(
    *,
    budget_status: str = "",
    credential_state: str = "",
    force_policy_question: bool = False,
) -> dict[str, str]:
    """Publish the threshold-continuation posture without inventing product policy."""
    budget = _clean_text(budget_status).lower()
    state = _clean_text(credential_state).lower()
    threshold_active = budget in {"warning", "exhausted"} or state in {"budget_warning", "budget_exhausted"}
    if not threshold_active and not force_policy_question:
        return {
            "status": "not_applicable",
            "dashboard_guidance": "no_threshold_warning_active",
            "raven_notifications": "not_applicable",
            "provider_fallback": "policy_question",
            "overage_refill": "policy_question",
            "warning_cadence": "policy_question",
            "reason": "No threshold warning or exhaustion is active for this deployment.",
        }
    return {
        "status": "policy_question",
        "dashboard_guidance": "show_sanitized_threshold_state_only",
        "raven_notifications": "disabled_until_warning_cadence_policy",
        "provider_fallback": "policy_question",
        "overage_refill": "policy_question",
        "warning_cadence": "policy_question",
        "reason": (
            "ArcLink exposes sanitized Chutes warning/exhaustion state only. "
            "Provider fallback, overage refill, and Raven warning cadence require "
            "operator policy before continuation guidance is shown."
        ),
    }


def _contains_scope(secret_ref: str, *, deployment_id: str, user_id: str) -> bool:
    if not secret_ref.startswith("secret://"):
        return False
    scope_parts = {part for part in (deployment_id, user_id) if part}
    return bool(scope_parts and any(part in secret_ref for part in scope_parts))


def chutes_credential_lifecycle(
    *,
    isolation_mode: str = "",
    credential_state: str = "",
    allow_inference: bool = False,
) -> dict[str, Any]:
    """Publish ArcLink's local Chutes credential posture without key material."""
    current_mode = _clean_text(isolation_mode) or "not_evaluated"
    state = _clean_text(credential_state) or "not_evaluated"
    if allow_inference:
        posture = "active_scoped_secret_ref"
    elif state in {"missing_secret_ref", "budget_unconfigured", "not_evaluated"}:
        posture = "disabled_until_scoped_secret_ref_and_budget"
    elif state in {"unscoped_secret_ref", "invalid_secret_ref"} or current_mode.endswith("_rejected"):
        posture = "rejected_unisolated_or_plaintext_secret"
    elif state in {"billing_suspended", "suspended", "budget_exhausted"}:
        posture = "suspended_or_exhausted"
    else:
        posture = "disabled_fail_closed"
    return {
        "canonical_mode": "scoped_secret_ref_per_user_or_deployment",
        "accepted_modes": list(CHUTES_ACCEPTED_ISOLATION_MODES),
        "current_mode": current_mode,
        "status": state,
        "posture": posture,
        "secret_material": "never_returned",
        "operator_shared_key_policy": "rejected_for_user_isolation",
        "live_key_creation": "proof_gated",
        "per_key_metering": "proof_gated",
        "fallback": "per_user_chutes_account_oauth_required_when_per_key_metering_unavailable",
    }


def evaluate_chutes_deployment_boundary(
    deployment_id: str,
    user_id: str,
    metadata: Mapping[str, Any] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    billing_state: str = "",
) -> ChutesDeploymentBoundary:
    """Evaluate local Chutes credential and budget state without exposing keys.

    ArcLink does not treat an operator-level CHUTES_API_KEY as user isolation.
    A deployment is allowed to use Chutes only when it has a scoped secret://
    reference plus an explicit budget that has not been suspended or exhausted.
    """
    clean_deployment_id = _clean_text(deployment_id)
    clean_user_id = _clean_text(user_id)
    meta = dict(metadata or {})
    chutes_meta = _as_mapping(meta.get("chutes"))
    env_source = env or {}
    secret_ref = _first_text(
        chutes_meta.get("secret_ref"),
        chutes_meta.get("key_secret_ref"),
        meta.get("chutes_secret_ref"),
        meta.get("chutes_key_secret_ref"),
        meta.get("provider_secret_ref"),
    )
    key_id = _first_text(chutes_meta.get("key_id"), meta.get("chutes_key_id"), meta.get("provider_key_id"))
    monthly_budget_cents = _clean_int(
        _first_text(
            chutes_meta.get("monthly_budget_cents"),
            chutes_meta.get("budget_cents"),
            meta.get("chutes_monthly_budget_cents"),
            meta.get("provider_budget_cents"),
            env_source.get("ARCLINK_CHUTES_DEFAULT_MONTHLY_BUDGET_CENTS", ""),
        )
    )
    used_cents = _clean_int(
        _first_text(
            chutes_meta.get("used_cents"),
            chutes_meta.get("spent_cents"),
            meta.get("chutes_used_cents"),
            meta.get("provider_used_cents"),
        )
    )
    warning_threshold_percent = _clean_percent(
        _first_text(
            chutes_meta.get("warning_threshold_percent"),
            meta.get("chutes_warning_threshold_percent"),
            env_source.get("ARCLINK_CHUTES_WARNING_THRESHOLD_PERCENT", ""),
        ),
        80.0,
    )
    hard_limit_percent = _clean_percent(
        _first_text(
            chutes_meta.get("hard_limit_percent"),
            meta.get("chutes_hard_limit_percent"),
            env_source.get("ARCLINK_CHUTES_HARD_LIMIT_PERCENT", ""),
        ),
        100.0,
    )
    if hard_limit_percent <= 0:
        hard_limit_percent = 100.0
    if warning_threshold_percent <= 0 or warning_threshold_percent > hard_limit_percent:
        warning_threshold_percent = min(80.0, hard_limit_percent)

    status_hint = _first_text(chutes_meta.get("status"), meta.get("chutes_status"), meta.get("provider_status")).lower()
    suspended = status_hint in {"suspended", "revoked", "disabled"} or _truthy(chutes_meta.get("suspended")) or _truthy(meta.get("chutes_suspended"))
    lifecycle = renewal_lifecycle_for_billing_state(billing_state)
    secret_present = bool(secret_ref)
    scoped_secret = _contains_scope(secret_ref, deployment_id=clean_deployment_id, user_id=clean_user_id)
    operator_shared_key_present = bool(_first_text(env_source.get("CHUTES_API_KEY"), env_source.get("ARCLINK_CHUTES_API_KEY")))
    per_key_metering_available = str(
        env_source.get("ARCLINK_CHUTES_PER_KEY_METERING_AVAILABLE")
        or env_source.get("ARCLINK_CHUTES_KEY_METERING_AVAILABLE")
        or ""
    ).strip().lower()
    per_key_metering_unavailable = per_key_metering_available in {"0", "false", "no", "off", "unavailable"}
    if scoped_secret:
        isolation_mode = "per_deployment_secret_ref" if clean_deployment_id and clean_deployment_id in secret_ref else "per_user_secret_ref"
    elif secret_ref.startswith("secret://"):
        isolation_mode = "unscoped_secret_ref_rejected"
    elif secret_ref:
        isolation_mode = "plaintext_secret_ref_rejected"
    elif operator_shared_key_present:
        isolation_mode = "operator_shared_key_rejected"
    elif per_key_metering_unavailable:
        isolation_mode = "per_user_chutes_account_oauth_required"
    else:
        isolation_mode = "missing_secret_ref"

    budget_limit_cents = int(monthly_budget_cents * (hard_limit_percent / 100.0)) if monthly_budget_cents else 0
    warning_limit_cents = int(monthly_budget_cents * (warning_threshold_percent / 100.0)) if monthly_budget_cents else 0
    remaining_cents = max(0, budget_limit_cents - used_cents) if budget_limit_cents else 0
    usage_percent = round((used_cents / monthly_budget_cents) * 100.0, 2) if monthly_budget_cents else 0.0

    if monthly_budget_cents <= 0:
        budget_status = "unconfigured"
    elif used_cents >= budget_limit_cents:
        budget_status = "exhausted"
    elif used_cents >= warning_limit_cents:
        budget_status = "warning"
    else:
        budget_status = "ok"

    reason = "Chutes deployment is within its scoped budget."
    credential_state = "active"
    allow_inference = True
    if lifecycle.get("provider_access") == "suspended":
        credential_state = "billing_suspended"
        allow_inference = False
        reason = str(lifecycle.get("reason") or "Billing is not current; provider access is suspended.")
    elif suspended:
        credential_state = "suspended"
        allow_inference = False
        reason = "Chutes access is suspended or revoked for this deployment."
    elif per_key_metering_unavailable and not secret_present:
        credential_state = "account_oauth_required"
        allow_inference = False
        reason = "Per-key Chutes metering is unavailable; ArcLink requires a per-user Chutes account/OAuth lane before inference."
    elif not secret_present:
        credential_state = "missing_secret_ref"
        allow_inference = False
        reason = "No per-user or per-deployment Chutes secret reference is configured."
    elif not secret_ref.startswith("secret://"):
        credential_state = "invalid_secret_ref"
        allow_inference = False
        reason = "Chutes secret material must be stored behind a secret:// reference."
    elif not scoped_secret:
        credential_state = "unscoped_secret_ref"
        allow_inference = False
        reason = "Chutes secret reference is not scoped to this user or deployment."
    elif budget_status == "unconfigured":
        credential_state = "budget_unconfigured"
        allow_inference = False
        reason = "Chutes budget is missing; ArcLink fails closed until a limit is configured."
    elif budget_status == "exhausted":
        credential_state = "budget_exhausted"
        allow_inference = False
        reason = "Chutes budget limit has been reached."
    elif budget_status == "warning":
        credential_state = "budget_warning"
        reason = "Chutes usage is near the configured warning threshold."

    return ChutesDeploymentBoundary(
        deployment_id=clean_deployment_id,
        user_id=clean_user_id,
        provider="chutes",
        isolation_mode=isolation_mode,
        credential_state=credential_state,
        secret_ref_present=secret_present,
        key_id=key_id,
        monthly_budget_cents=monthly_budget_cents,
        used_cents=used_cents,
        remaining_cents=remaining_cents,
        warning_threshold_percent=warning_threshold_percent,
        hard_limit_percent=hard_limit_percent,
        usage_percent=usage_percent,
        budget_status=budget_status,
        allow_inference=allow_inference,
        reason=reason,
        billing_state=str(lifecycle.get("payment_state") or ""),
        billing_lifecycle=lifecycle,
    )


def record_chutes_usage_event(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    usage_event: Mapping[str, Any],
    user_id: str = "",
    env: Mapping[str, str] | None = None,
    billing_state: str = "",
    commit: bool = True,
) -> ChutesUsageIngestionResult:
    """Apply a local Chutes usage event to deployment metadata.

    The ingested event is deliberately reduced to cents, token counts, and safe
    identifiers before it is stored. Raw provider payloads, headers, and secret
    references are not persisted.
    """
    clean_deployment_id = _clean_text(deployment_id)
    if not clean_deployment_id:
        raise ValueError("deployment_id is required")
    row = conn.execute(
        "SELECT user_id, metadata_json FROM arclink_deployments WHERE deployment_id = ?",
        (clean_deployment_id,),
    ).fetchone()
    if row is None:
        raise KeyError(clean_deployment_id)
    row_user_id = _clean_text(row["user_id"])
    clean_user_id = _clean_text(user_id) or row_user_id
    if clean_user_id != row_user_id:
        raise PermissionError("Chutes usage event is not scoped to this deployment owner")

    event = dict(usage_event or {})
    event_id, public_usage_event_id = _usage_event_identity(clean_deployment_id, event)
    metadata = _json_loads_object(row["metadata_json"])
    chutes_meta = dict(_as_mapping(metadata.get("chutes")))
    used_cents_before = _clean_int(
        _first_text(chutes_meta.get("used_cents"), chutes_meta.get("spent_cents"), metadata.get("chutes_used_cents"))
    )
    delta_cents = _clean_money_cents(event)

    existing = conn.execute("SELECT 1 FROM arclink_events WHERE event_id = ?", (event_id,)).fetchone()
    if existing is not None:
        boundary = evaluate_chutes_deployment_boundary(
            clean_deployment_id,
            clean_user_id,
            metadata,
            env=env,
            billing_state=billing_state,
        )
        return ChutesUsageIngestionResult(
            deployment_id=clean_deployment_id,
            user_id=clean_user_id,
            usage_event_id=public_usage_event_id,
            recorded=False,
            delta_cents=0,
            used_cents_before=used_cents_before,
            used_cents_after=used_cents_before,
            boundary=boundary,
        )

    now = _utc_now_iso()
    used_cents_after = used_cents_before + delta_cents
    chutes_meta["used_cents"] = used_cents_after
    chutes_meta["usage_source"] = "local_metered_events"
    chutes_meta["usage_event_count"] = _clean_int(chutes_meta.get("usage_event_count")) + 1
    chutes_meta["last_usage_event_id"] = public_usage_event_id
    chutes_meta["last_usage_event_at"] = _safe_usage_text(event.get("observed_at"), fallback=now, max_len=64)
    model_id = _safe_usage_text(event.get("model_id") or event.get("model"), max_len=160)
    if model_id:
        chutes_meta["last_usage_model_id"] = model_id
    metadata["chutes"] = chutes_meta
    conn.execute(
        "UPDATE arclink_deployments SET metadata_json = ? WHERE deployment_id = ?",
        (_json_dumps_object(metadata), clean_deployment_id),
    )
    conn.execute(
        """
        INSERT INTO arclink_events (event_id, subject_kind, subject_id, event_type, metadata_json, created_at)
        VALUES (?, 'deployment', ?, 'chutes_usage_ingested', ?, ?)
        """,
        (
            event_id,
            clean_deployment_id,
            _json_dumps_object(
                _usage_event_metadata(
                    event=event,
                    public_usage_event_id=public_usage_event_id,
                    delta_cents=delta_cents,
                    used_cents_before=used_cents_before,
                    used_cents_after=used_cents_after,
                    now=now,
                )
            ),
            now,
        ),
    )
    if commit:
        conn.commit()
    boundary = evaluate_chutes_deployment_boundary(
        clean_deployment_id,
        clean_user_id,
        metadata,
        env=env,
        billing_state=billing_state,
    )
    return ChutesUsageIngestionResult(
        deployment_id=clean_deployment_id,
        user_id=clean_user_id,
        usage_event_id=public_usage_event_id,
        recorded=True,
        delta_cents=delta_cents,
        used_cents_before=used_cents_before,
        used_cents_after=used_cents_after,
        boundary=boundary,
    )


def assert_chutes_inference_allowed(boundary: ChutesDeploymentBoundary | Mapping[str, Any]) -> None:
    if isinstance(boundary, ChutesDeploymentBoundary):
        allowed = boundary.allow_inference
        state = boundary.credential_state
        reason = boundary.reason
    else:
        allowed = bool(boundary.get("allow_inference"))
        state = _clean_text(boundary.get("credential_state") or "unknown")
        reason = _clean_text(boundary.get("reason"))
    if not allowed:
        detail = f": {reason}" if reason else ""
        raise ChutesCatalogError(f"Chutes inference blocked by provider boundary ({state}){detail}")


class FakeChutesKeyManager:
    def __init__(self) -> None:
        self.keys: dict[str, dict[str, str]] = {}

    @staticmethod
    def _clean_deployment_id(deployment_id: str) -> str:
        clean_id = str(deployment_id or "").strip()
        if not clean_id:
            raise ValueError("deployment_id is required")
        return clean_id

    @staticmethod
    def _key_id_for(deployment_id: str) -> str:
        return f"fake_chutes_key_{deployment_id}"

    def create_key(self, deployment_id: str, *, label: str = "") -> dict[str, str]:
        clean_id = self._clean_deployment_id(deployment_id)
        key_id = self._key_id_for(clean_id)
        secret_ref = f"secret://arclink/chutes/{clean_id}"
        record = {"key_id": key_id, "deployment_id": clean_id, "label": label, "secret_ref": secret_ref, "status": "active"}
        self.keys[key_id] = record
        return dict(record)

    def rotate_key(self, deployment_id: str, *, label: str = "") -> dict[str, str]:
        clean_id = self._clean_deployment_id(deployment_id)
        old_key_id = self._key_id_for(clean_id)
        if old_key_id in self.keys:
            self.keys[old_key_id]["status"] = "rotated"
        return self.create_key(clean_id, label=label or "rotated")

    def revoke_key(self, key_id: str) -> dict[str, str]:
        clean_id = str(key_id or "").strip()
        if clean_id not in self.keys:
            raise KeyError(clean_id)
        self.keys[clean_id]["status"] = "revoked"
        return dict(self.keys[clean_id])

    def key_state(self, deployment_id: str) -> dict[str, str] | None:
        clean_id = self._clean_deployment_id(deployment_id)
        key_id = self._key_id_for(clean_id)
        return dict(self.keys[key_id]) if key_id in self.keys else None


class FakeChutesInferenceClient:
    """Fake inference client for smoke testing without live credentials."""

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self._fail = fail

    def chat_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        api_key: str = "",
        boundary: ChutesDeploymentBoundary | Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if boundary is not None:
            assert_chutes_inference_allowed(boundary)
        record = {"model": model, "messages": messages, "api_key_provided": bool(api_key), "boundary_checked": boundary is not None}
        self.calls.append(record)
        if self._fail:
            raise ChutesCatalogError(f"fake inference failure for model {model}")
        return {
            "id": f"fake_cmpl_{len(self.calls)}",
            "model": model,
            "choices": [{"message": {"role": "assistant", "content": "Hello from fake inference."}}],
        }
