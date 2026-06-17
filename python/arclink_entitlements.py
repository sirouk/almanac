#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Mapping

from arclink_control import (
    ARCLINK_ENTITLEMENT_STATES,
    advance_arclink_entitlement_gates_for_user,
    apply_arclink_refuel_credit_to_chutes_budget,
    apply_subscription_inference_allowance,
    append_arclink_audit,
    append_arclink_event,
    grant_arclink_refuel_credit,
    merge_arclink_user_identity_by_email,
    set_arclink_user_entitlement,
    upsert_arclink_user,
    upsert_arclink_subscription_mirror,
    utc_now_iso,
)
from arclink_adapters import verify_stripe_webhook
from arclink_onboarding import sync_arclink_onboarding_after_entitlement


class ArcLinkEntitlementError(ValueError):
    pass


@dataclass(frozen=True)
class ReconciliationDrift:
    kind: str
    user_id: str
    detail: str


SUBSCRIPTION_COVERAGE_STATUSES = frozenset({"active", "trialing", "paid"})
SUBSCRIPTION_OWED_SERVICE_STATUSES = frozenset({"past_due", "unpaid"})
SUBSCRIPTION_MIRROR_STATUSES = frozenset({
    "active",
    "trialing",
    "paid",
    "past_due",
    "unpaid",
    "canceled",
    "cancelled",
    "incomplete",
    "incomplete_expired",
    "paused",
})


def _stripe_subscription_mirror_status(
    *,
    event_type: str,
    obj: Mapping[str, Any],
    entitlement_state: str,
) -> str:
    if event_type.startswith("customer.subscription."):
        candidate = str(obj.get("status") or entitlement_state).strip().lower()
    else:
        candidate = str(entitlement_state or "").strip().lower()
    if candidate in SUBSCRIPTION_MIRROR_STATUSES:
        return candidate
    fallback = str(entitlement_state or "").strip().lower()
    if fallback in SUBSCRIPTION_MIRROR_STATUSES:
        return fallback
    return "incomplete"


def detect_stripe_reconciliation_drift(conn: sqlite3.Connection) -> list[ReconciliationDrift]:
    """Find users with active subscriptions but no deployment, or vice versa."""
    drift: list[ReconciliationDrift] = []
    # Active subscription but no active deployment
    rows = conn.execute(
        """
        SELECT s.user_id, s.stripe_subscription_id
        FROM arclink_subscriptions s
        WHERE s.status IN ('active', 'trialing', 'paid')
          AND NOT EXISTS (
            SELECT 1 FROM arclink_deployments d
            WHERE d.user_id = s.user_id
              AND d.status IN ('provisioning_ready', 'provisioning', 'active')
          )
        """
    ).fetchall()
    for row in rows:
        drift.append(ReconciliationDrift(
            kind="subscription_without_deployment",
            user_id=row["user_id"],
            detail=f"subscription {row['stripe_subscription_id']} active but no deployment",
        ))
    # Active deployment but no active subscription
    rows = conn.execute(
        """
        SELECT d.user_id, d.deployment_id
        FROM arclink_deployments d
        WHERE d.status IN ('provisioning_ready', 'provisioning', 'active')
          AND NOT EXISTS (
            SELECT 1 FROM arclink_subscriptions s
            WHERE s.user_id = d.user_id
              AND s.status IN ('active', 'trialing', 'paid', 'past_due', 'unpaid')
          )
          AND NOT EXISTS (
            SELECT 1 FROM arclink_users u
            WHERE u.user_id = d.user_id
              AND u.entitlement_state = 'comp'
          )
        """
    ).fetchall()
    for row in rows:
        drift.append(ReconciliationDrift(
            kind="deployment_without_subscription",
            user_id=row["user_id"],
            detail=f"deployment {row['deployment_id']} active but no subscription or comp",
        ))
    rows = conn.execute(
        """
        SELECT d.user_id, d.deployment_id, s.stripe_subscription_id, s.status
        FROM arclink_deployments d
        JOIN arclink_subscriptions s ON s.user_id = d.user_id
        WHERE d.status IN ('provisioning_ready', 'provisioning', 'active')
          AND s.status IN ('past_due', 'unpaid')
          AND NOT EXISTS (
            SELECT 1 FROM arclink_subscriptions active_s
            WHERE active_s.user_id = d.user_id
              AND active_s.status IN ('active', 'trialing', 'paid')
          )
          AND NOT EXISTS (
            SELECT 1 FROM arclink_users u
            WHERE u.user_id = d.user_id
              AND u.entitlement_state = 'comp'
          )
        """
    ).fetchall()
    for row in rows:
        drift.append(ReconciliationDrift(
            kind="deployment_subscription_owed_service",
            user_id=row["user_id"],
            detail=(
                f"deployment {row['deployment_id']} has subscription "
                f"{row['stripe_subscription_id']} in owed-service state {row['status']}"
            ),
        ))
    return drift


ENTITLEMENT_MUTATING_STRIPE_EVENTS = frozenset(
    {
        "checkout.session.completed",
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "invoice.payment_failed",
        "invoice.payment_succeeded",
        "invoice.paid",
    }
)


@dataclass(frozen=True)
class StripeWebhookResult:
    event_id: str
    event_type: str
    user_id: str
    entitlement_state: str
    replayed: bool
    advanced_deployments: tuple[str, ...] = ()


@dataclass(frozen=True)
class StripeEntitlementOwner:
    user_id: str
    source: str
    onboarding_session_id: str = ""
    metadata_user_id: str = ""


def _metadata(value: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = value.get("metadata")
    return raw if isinstance(raw, Mapping) else {}


def _event_object(event: Mapping[str, Any]) -> Mapping[str, Any]:
    data = event.get("data")
    if not isinstance(data, Mapping):
        return {}
    obj = data.get("object")
    return obj if isinstance(obj, Mapping) else {}


def _safe_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _nested_metadata(obj: Mapping[str, Any], *path: str) -> Mapping[str, Any]:
    """Walk a dotted path of mapping keys, returning the final 'metadata' mapping."""
    node: Any = obj
    for key in path:
        node = _safe_mapping(node).get(key)
    return _safe_mapping(_safe_mapping(node).get("metadata"))


def _all_metadata_sources(obj: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Return the three metadata mappings we search for user/session ids."""
    return (
        _metadata(obj),
        _nested_metadata(obj, "subscription_details"),
        _nested_metadata(obj, "parent", "subscription_details"),
    )


def _first_nonempty(candidates: tuple[Any, ...]) -> str:
    """Return the first non-empty string from candidates."""
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value
    return ""


def _stripe_user_id(obj: Mapping[str, Any]) -> str:
    meta, sub_meta, parent_meta = _all_metadata_sources(obj)
    result = _first_nonempty((
        meta.get("arclink_user_id"),
        meta.get("user_id"),
        obj.get("client_reference_id"),
        sub_meta.get("arclink_user_id"),
        sub_meta.get("user_id"),
        parent_meta.get("arclink_user_id"),
        parent_meta.get("user_id"),
    ))
    if not result:
        raise ArcLinkEntitlementError("Stripe webhook did not include an ArcLink user id")
    return result


def _stripe_user_id_or_empty(obj: Mapping[str, Any]) -> str:
    try:
        return _stripe_user_id(obj)
    except ArcLinkEntitlementError:
        return ""


def _stripe_metadata_user_id_or_empty(obj: Mapping[str, Any]) -> str:
    meta, sub_meta, parent_meta = _all_metadata_sources(obj)
    return _first_nonempty((
        meta.get("arclink_user_id"),
        meta.get("user_id"),
        sub_meta.get("arclink_user_id"),
        sub_meta.get("user_id"),
        parent_meta.get("arclink_user_id"),
        parent_meta.get("user_id"),
    ))


def _stripe_user_id_from_local_state(
    conn: sqlite3.Connection,
    *,
    subscription_id: str,
    stripe_customer_id: str,
) -> str:
    clean_subscription_id = str(subscription_id or "").strip()
    if clean_subscription_id:
        row = conn.execute(
            """
            SELECT user_id
            FROM arclink_subscriptions
            WHERE stripe_subscription_id = ?
               OR subscription_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (clean_subscription_id, f"stripe:{clean_subscription_id}"),
        ).fetchone()
        if row is not None:
            return str(row["user_id"] or "").strip()
    clean_customer_id = str(stripe_customer_id or "").strip()
    if clean_customer_id:
        row = conn.execute(
            """
            SELECT user_id
            FROM arclink_users
            WHERE stripe_customer_id = ?
            ORDER BY entitlement_updated_at DESC
            LIMIT 1
            """,
            (clean_customer_id,),
        ).fetchone()
        if row is not None:
            return str(row["user_id"] or "").strip()
    return ""


def _stripe_subscription_id(obj: Mapping[str, Any]) -> str:
    for key in ("subscription", "id"):
        value = str(obj.get(key) or "").strip()
        if value.startswith("sub_"):
            return value
    parent = _safe_mapping(obj.get("parent"))
    for key in ("subscription",):
        value = str(parent.get(key) or "").strip()
        if value.startswith("sub_"):
            return value
    sub_details = _safe_mapping(parent.get("subscription_details"))
    value = str(sub_details.get("subscription") or "").strip()
    if value.startswith("sub_"):
        return value
    return ""


def _stripe_onboarding_session_id(obj: Mapping[str, Any]) -> str:
    meta, sub_meta, parent_meta = _all_metadata_sources(obj)
    return _first_nonempty((
        meta.get("arclink_onboarding_session_id"),
        meta.get("onboarding_session_id"),
        sub_meta.get("arclink_onboarding_session_id"),
        sub_meta.get("onboarding_session_id"),
        parent_meta.get("arclink_onboarding_session_id"),
        parent_meta.get("onboarding_session_id"),
    ))


def _stripe_deployment_id(obj: Mapping[str, Any]) -> str:
    meta, sub_meta, parent_meta = _all_metadata_sources(obj)
    return _first_nonempty((
        meta.get("arclink_deployment_id"),
        meta.get("deployment_id"),
        sub_meta.get("arclink_deployment_id"),
        sub_meta.get("deployment_id"),
        parent_meta.get("arclink_deployment_id"),
        parent_meta.get("deployment_id"),
    ))


def _stripe_purchase_kind(obj: Mapping[str, Any]) -> str:
    meta, sub_meta, parent_meta = _all_metadata_sources(obj)
    return _first_nonempty((
        meta.get("arclink_purchase_kind"),
        meta.get("purchase_kind"),
        sub_meta.get("arclink_purchase_kind"),
        sub_meta.get("purchase_kind"),
        parent_meta.get("arclink_purchase_kind"),
        parent_meta.get("purchase_kind"),
    )).strip().lower()


def _onboarding_session_for_checkout_owner(
    conn: sqlite3.Connection,
    *,
    checkout_session_id: str,
    onboarding_session_id: str,
) -> sqlite3.Row | None:
    rows: list[sqlite3.Row] = []
    clean_checkout = str(checkout_session_id or "").strip()
    if clean_checkout:
        row = conn.execute(
            """
            SELECT *
            FROM arclink_onboarding_sessions
            WHERE checkout_session_id = ?
            LIMIT 1
            """,
            (clean_checkout,),
        ).fetchone()
        if row is not None:
            rows.append(row)
    clean_session = str(onboarding_session_id or "").strip()
    if clean_session:
        row = conn.execute(
            """
            SELECT *
            FROM arclink_onboarding_sessions
            WHERE session_id = ?
            LIMIT 1
            """,
            (clean_session,),
        ).fetchone()
        if row is not None:
            rows.append(row)
    if not rows:
        return None
    session_ids = {str(row["session_id"] or "").strip() for row in rows}
    if len(session_ids) > 1:
        raise ArcLinkEntitlementError("Stripe checkout maps to conflicting ArcLink onboarding sessions")
    return rows[0]


def _validate_onboarding_checkout_owner(
    *,
    obj: Mapping[str, Any],
    session: sqlite3.Row,
) -> StripeEntitlementOwner:
    local_user = str(session["user_id"] or "").strip()
    if not local_user:
        raise ArcLinkEntitlementError("Stripe checkout onboarding session has no ArcLink user id")
    metadata_user = _stripe_metadata_user_id_or_empty(obj)
    if metadata_user and metadata_user != local_user:
        raise ArcLinkEntitlementError("Stripe checkout metadata user does not match ArcLink onboarding owner")
    client_reference = str(obj.get("client_reference_id") or "").strip()
    if client_reference and client_reference != local_user:
        raise ArcLinkEntitlementError("Stripe checkout client reference does not match ArcLink onboarding owner")
    checkout_id = str(obj.get("id") or "").strip()
    local_checkout = str(session["checkout_session_id"] or "").strip()
    if checkout_id and local_checkout and checkout_id != local_checkout:
        raise ArcLinkEntitlementError("Stripe checkout session id does not match ArcLink onboarding session")
    deployment_id = _stripe_deployment_id(obj)
    local_deployment = str(session["deployment_id"] or "").strip()
    if deployment_id and local_deployment and deployment_id != local_deployment:
        raise ArcLinkEntitlementError("Stripe checkout deployment does not match ArcLink onboarding session")
    return StripeEntitlementOwner(
        user_id=local_user,
        source="local_onboarding_checkout",
        onboarding_session_id=str(session["session_id"] or "").strip(),
        metadata_user_id=metadata_user,
    )


def _stripe_user_id_from_local_onboarding_checkout(
    conn: sqlite3.Connection,
    *,
    obj: Mapping[str, Any],
) -> StripeEntitlementOwner | None:
    session = _onboarding_session_for_checkout_owner(
        conn,
        checkout_session_id=str(obj.get("id") or ""),
        onboarding_session_id=_stripe_onboarding_session_id(obj),
    )
    if session is None:
        return None
    return _validate_onboarding_checkout_owner(obj=obj, session=session)


def _resolve_stripe_entitlement_owner(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    obj: Mapping[str, Any],
    subscription_id: str,
    stripe_customer_id: str,
) -> StripeEntitlementOwner:
    metadata_user = _stripe_metadata_user_id_or_empty(obj)
    local_owner = _stripe_user_id_from_local_state(
        conn,
        subscription_id=subscription_id,
        stripe_customer_id=stripe_customer_id,
    )
    checkout_owner: StripeEntitlementOwner | None = None
    if event_type == "checkout.session.completed":
        checkout_owner = _stripe_user_id_from_local_onboarding_checkout(conn, obj=obj)
    if local_owner:
        if metadata_user and metadata_user != local_owner:
            if stripe_customer_id:
                raise ArcLinkEntitlementError("Stripe customer is already bound to another ArcLink account")
            if subscription_id:
                raise ArcLinkEntitlementError("Stripe subscription is already bound to another ArcLink account")
            raise ArcLinkEntitlementError("Stripe webhook metadata user does not match local ArcLink account")
        if checkout_owner is not None and checkout_owner.user_id != local_owner:
            raise ArcLinkEntitlementError("Stripe checkout onboarding owner does not match local ArcLink account")
        return StripeEntitlementOwner(
            user_id=local_owner,
            source="local_stripe_binding",
            onboarding_session_id=checkout_owner.onboarding_session_id if checkout_owner is not None else "",
            metadata_user_id=metadata_user,
        )
    if checkout_owner is not None:
        return checkout_owner
    # Stripe metadata may only AGREE with a locally-resolved owner (the conflict
    # cross-check in the local_owner branch above); it must NEVER originate a first
    # binding. A checkout.session.completed whose obj.id / onboarding link matches no
    # local checkout ArcLink created is unowned even when metadata names an existing
    # user — binding it would let attacker-influenced metadata repoint a named victim
    # to an attacker customer. Fail closed (replayable). All legitimate checkouts are
    # locally recorded (arclink_onboarding.open_arclink_onboarding_checkout stores
    # checkout_session_id), so checkout_owner already covers them.
    # (CANON-07 D1 — federation review hardening; closes the existing-user bypass.)
    raise ArcLinkEntitlementError("Stripe webhook did not resolve a local ArcLink user id")


def _stripe_metadata_positive_int(obj: Mapping[str, Any], *keys: str) -> int:
    for source in _all_metadata_sources(obj):
        for key in keys:
            try:
                value = int(str(source.get(key) or "").strip())
            except ValueError:
                continue
            if value > 0:
                return value
    return 0


def _assert_refuel_checkout_account(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    deployment_id: str,
    stripe_customer_id: str,
    client_reference_id: str,
) -> None:
    clean_user = str(user_id or "").strip()
    clean_deployment = str(deployment_id or "").strip()
    clean_customer = str(stripe_customer_id or "").strip()
    clean_reference = str(client_reference_id or "").strip()
    if clean_reference and clean_reference != clean_user:
        raise ArcLinkEntitlementError("Stripe refuel checkout client reference does not match ArcLink account")
    user_row = conn.execute(
        """
        SELECT stripe_customer_id
        FROM arclink_users
        WHERE user_id = ?
        LIMIT 1
        """,
        (clean_user,),
    ).fetchone()
    if user_row is None:
        raise ArcLinkEntitlementError("Stripe refuel checkout targeted an unknown ArcLink account")
    local_customer = str(user_row["stripe_customer_id"] or "").strip()
    if local_customer and clean_customer and local_customer != clean_customer:
        raise ArcLinkEntitlementError("Stripe refuel checkout customer does not match ArcLink account")
    if clean_customer:
        other_row = conn.execute(
            """
            SELECT user_id
            FROM arclink_users
            WHERE stripe_customer_id = ?
              AND user_id != ?
            LIMIT 1
            """,
            (clean_customer, clean_user),
        ).fetchone()
        if other_row is not None:
            raise ArcLinkEntitlementError("Stripe refuel checkout customer is already bound to another ArcLink account")
    deployment_row = conn.execute(
        """
        SELECT user_id
        FROM arclink_deployments
        WHERE deployment_id = ?
        LIMIT 1
        """,
        (clean_deployment,),
    ).fetchone()
    if deployment_row is None:
        raise ArcLinkEntitlementError("Stripe refuel checkout targeted an unknown ArcPod")
    if str(deployment_row["user_id"] or "").strip() != clean_user:
        raise ArcLinkEntitlementError("Stripe refuel checkout ArcPod does not belong to ArcLink account")


def _stripe_customer_email(obj: Mapping[str, Any]) -> str:
    customer_details = _safe_mapping(obj.get("customer_details"))
    return _first_nonempty((
        customer_details.get("email"),
        obj.get("customer_email"),
        obj.get("receipt_email"),
    ))


def _stripe_object_int(obj: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        raw = obj.get(key)
        if raw is None or raw == "":
            continue
        try:
            return int(str(raw).strip())
        except ValueError:
            continue
    return None


def _require_paid_checkout_session(
    obj: Mapping[str, Any],
    *,
    purchase_kind: str,
    minimum_amount_cents: int = 0,
) -> None:
    payment_status = str(obj.get("payment_status") or "").strip().lower()
    if payment_status != "paid":
        raise ArcLinkEntitlementError(f"Stripe {purchase_kind} checkout is not paid")
    if minimum_amount_cents > 0:
        amount_cents = _stripe_object_int(obj, "amount_total", "amount_paid", "amount_received")
        if amount_cents is None:
            raise ArcLinkEntitlementError(f"Stripe {purchase_kind} checkout did not include a paid amount")
        if amount_cents < minimum_amount_cents:
            raise ArcLinkEntitlementError(f"Stripe {purchase_kind} checkout paid amount is below the expected total")


def _assert_entitlement_account(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    subscription_id: str,
    stripe_customer_id: str,
    client_reference_id: str,
    allowed_user_ids: set[str],
) -> None:
    clean_user = str(user_id or "").strip()
    allowed = {value for value in allowed_user_ids if value}
    allowed.add(clean_user)
    clean_reference = str(client_reference_id or "").strip()
    if clean_reference and clean_reference not in allowed:
        raise ArcLinkEntitlementError("Stripe checkout client reference does not match ArcLink account")
    clean_customer = str(stripe_customer_id or "").strip()
    if clean_customer:
        allowed_placeholders = ",".join("?" for _ in allowed)
        row = conn.execute(
            f"""
            SELECT user_id
            FROM arclink_users
            WHERE stripe_customer_id = ?
              AND user_id NOT IN ({allowed_placeholders})
            LIMIT 1
            """,
            (clean_customer, *sorted(allowed)),
        ).fetchone()
        if row is not None:
            raise ArcLinkEntitlementError("Stripe customer is already bound to another ArcLink account")
    clean_subscription = str(subscription_id or "").strip()
    if clean_subscription:
        allowed_placeholders = ",".join("?" for _ in allowed)
        row = conn.execute(
            f"""
            SELECT user_id
            FROM arclink_subscriptions
            WHERE (stripe_subscription_id = ?
               OR subscription_id = ?)
              AND user_id NOT IN ({allowed_placeholders})
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (clean_subscription, f"stripe:{clean_subscription}", *sorted(allowed)),
        ).fetchone()
        if row is not None:
            raise ArcLinkEntitlementError("Stripe subscription is already bound to another ArcLink account")


def _entitlement_for_stripe_event(event_type: str, obj: Mapping[str, Any]) -> str:
    stripe_status = str(obj.get("status") or "").strip().lower()
    if event_type == "checkout.session.completed":
        return "paid"
    if event_type in {"invoice.payment_succeeded", "invoice.paid"} and stripe_status == "paid":
        return "paid"
    if event_type == "invoice.payment_failed":
        return "past_due"
    if stripe_status in {"active", "trialing"}:
        return "paid"
    if stripe_status in {"past_due", "unpaid"}:
        return "past_due"
    if stripe_status in {"canceled", "cancelled", "incomplete_expired"}:
        return "cancelled"
    return "none"


def _redact_stripe_identifier(value: str) -> str:
    clean = str(value or "").strip()
    if not clean:
        return ""
    if len(clean) <= 8:
        return "present"
    return f"{clean[:4]}...{clean[-4:]}"


def apply_stripe_entitlement_recovery(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    actor_id: str,
    reason: str,
    stripe_customer_id: str = "",
    stripe_subscription_id: str = "",
    entitlement_state: str = "paid",
    subscription_status: str = "active",
    current_period_end: str = "",
    dry_run: bool = False,
    commit: bool = True,
) -> dict[str, Any]:
    clean_user = str(user_id or "").strip()
    clean_actor = str(actor_id or "").strip()
    clean_reason = str(reason or "").strip()
    clean_customer = str(stripe_customer_id or "").strip()
    clean_subscription = str(stripe_subscription_id or "").strip()
    clean_state = str(entitlement_state or "").strip().lower()
    clean_subscription_status = str(subscription_status or "").strip().lower()
    if not clean_user:
        raise ArcLinkEntitlementError("Stripe entitlement recovery requires a local ArcLink user id")
    if not clean_actor or clean_actor == "stripe":
        raise ArcLinkEntitlementError("Stripe entitlement recovery requires an operator actor")
    if not clean_reason:
        raise ArcLinkEntitlementError("Stripe entitlement recovery requires an operator reason")
    if clean_state not in (ARCLINK_ENTITLEMENT_STATES - {"comp"}):
        raise ArcLinkEntitlementError("Stripe entitlement recovery requested an unsupported entitlement state")
    if not clean_customer and not clean_subscription:
        raise ArcLinkEntitlementError("Stripe entitlement recovery requires a Stripe customer or subscription id")
    user = conn.execute("SELECT * FROM arclink_users WHERE user_id = ? LIMIT 1", (clean_user,)).fetchone()
    if user is None:
        raise ArcLinkEntitlementError("Stripe entitlement recovery target user does not exist locally")
    _assert_entitlement_account(
        conn,
        user_id=clean_user,
        subscription_id=clean_subscription,
        stripe_customer_id=clean_customer,
        client_reference_id="",
        allowed_user_ids={clean_user},
    )
    if clean_subscription_status not in SUBSCRIPTION_MIRROR_STATUSES:
        clean_subscription_status = _stripe_subscription_mirror_status(
            event_type="customer.subscription.updated",
            obj={"status": clean_subscription_status},
            entitlement_state=clean_state,
        )
    metadata = {
        "dry_run": bool(dry_run),
        "entitlement_state": clean_state,
        "subscription_status": clean_subscription_status,
        "has_stripe_customer_id": bool(clean_customer),
        "has_stripe_subscription_id": bool(clean_subscription),
        "stripe_customer_id": _redact_stripe_identifier(clean_customer),
        "stripe_subscription_id": _redact_stripe_identifier(clean_subscription),
    }
    own_txn = commit and not conn.in_transaction
    if own_txn:
        conn.execute("BEGIN")
    try:
        if dry_run:
            append_arclink_audit(
                conn,
                action="stripe_entitlement_recovery_dry_run",
                actor_id=clean_actor,
                target_kind="user",
                target_id=clean_user,
                reason=clean_reason,
                metadata=metadata,
                commit=False,
            )
            if own_txn:
                conn.commit()
            return {
                "status": "planned",
                "dry_run": True,
                "user_id": clean_user,
                "entitlement_state": clean_state,
                "subscription_status": clean_subscription_status,
            }
        if clean_subscription:
            upsert_arclink_subscription_mirror(
                conn,
                subscription_id=f"stripe:{clean_subscription}",
                user_id=clean_user,
                stripe_customer_id=clean_customer,
                stripe_subscription_id=clean_subscription,
                status=clean_subscription_status,
                current_period_end=str(current_period_end or ""),
                raw={"source": "operator_recovery"},
                commit=False,
            )
        set_arclink_user_entitlement(
            conn,
            user_id=clean_user,
            entitlement_state=clean_state,
            stripe_customer_id=clean_customer,
            commit=False,
        )
        advanced = tuple(advance_arclink_entitlement_gates_for_user(conn, user_id=clean_user, commit=False))
        append_arclink_audit(
            conn,
            action="stripe_entitlement_recovery_applied",
            actor_id=clean_actor,
            target_kind="user",
            target_id=clean_user,
            reason=clean_reason,
            metadata={**metadata, "advanced_deployments": list(advanced)},
            commit=False,
        )
        append_arclink_event(
            conn,
            subject_kind="user",
            subject_id=clean_user,
            event_type="stripe_entitlement_recovery_applied",
            metadata={**metadata, "advanced_deployments": list(advanced)},
            commit=False,
        )
        if own_txn:
            conn.commit()
        return {
            "status": "applied",
            "dry_run": False,
            "user_id": clean_user,
            "entitlement_state": clean_state,
            "subscription_status": clean_subscription_status,
            "advanced_deployments": advanced,
        }
    except Exception:
        if own_txn and conn.in_transaction:
            conn.rollback()
        raise


def _record_webhook_event(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    event_type: str,
    payload_json: str,
    commit: bool = True,
) -> tuple[bool, str]:
    now = utc_now_iso()
    try:
        conn.execute(
            """
            INSERT INTO arclink_webhook_events (provider, event_id, event_type, received_at, payload_json)
            VALUES ('stripe', ?, ?, ?, ?)
            """,
            (event_id, event_type, now, payload_json),
        )
        if commit:
            conn.commit()
        return (True, "received")
    except sqlite3.IntegrityError:
        row = conn.execute(
            """
            SELECT status
            FROM arclink_webhook_events
            WHERE provider = 'stripe' AND event_id = ?
            """,
            (event_id,),
        ).fetchone()
        status = str(row["status"] or "") if row is not None else ""
        if status in {"failed", "received"}:
            conn.execute(
                """
                UPDATE arclink_webhook_events
                SET event_type = ?,
                    received_at = ?,
                    processed_at = '',
                    status = 'received',
                    payload_json = ?
                WHERE provider = 'stripe' AND event_id = ?
                """,
                (event_type, now, payload_json, event_id),
            )
            if commit:
                conn.commit()
        return (False, status)


def _mark_webhook_processed(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    status: str = "processed",
    commit: bool = True,
) -> None:
    conn.execute(
        """
        UPDATE arclink_webhook_events
        SET status = ?, processed_at = ?
        WHERE provider = 'stripe' AND event_id = ?
        """,
        (status, utc_now_iso(), event_id),
    )
    if commit:
        conn.commit()


def _mark_webhook_failed_replayable(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    event_type: str,
    payload_json: str,
) -> None:
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO arclink_webhook_events (
          provider, event_id, event_type, received_at, processed_at, status, payload_json
        ) VALUES ('stripe', ?, ?, ?, ?, 'failed', ?)
        ON CONFLICT(provider, event_id) DO UPDATE SET
          event_type = excluded.event_type,
          received_at = excluded.received_at,
          processed_at = excluded.processed_at,
          status = 'failed',
          payload_json = excluded.payload_json
        """,
        (event_id, event_type, now, now, payload_json),
    )
    conn.commit()


def process_stripe_webhook(
    conn: sqlite3.Connection,
    *,
    payload: str,
    signature: str,
    secret: str,
) -> StripeWebhookResult:
    event = verify_stripe_webhook(payload, signature, secret)
    event_id = str(event.get("id") or "").strip()
    event_type = str(event.get("type") or "").strip()
    if not event_id or not event_type:
        raise ArcLinkEntitlementError("Stripe webhook event id and type are required")
    if conn.in_transaction:
        raise ArcLinkEntitlementError("Stripe webhook processing requires a connection without an active transaction")

    failure_is_replayable = False
    inserted = False
    try:
        conn.execute("BEGIN")
        inserted, recorded_status = _record_webhook_event(
            conn,
            event_id=event_id,
            event_type=event_type,
            payload_json=payload,
            commit=False,
        )
        if not inserted:
            if recorded_status == "processed":
                conn.rollback()
                return StripeWebhookResult(
                    event_id=event_id,
                    event_type=event_type,
                    user_id="",
                    entitlement_state="",
                    replayed=True,
                )
            if recorded_status not in {"failed", "received"}:
                conn.rollback()
                raise ArcLinkEntitlementError(
                    f"Stripe webhook event is already recorded with status {recorded_status or 'unknown'}"
                )
        failure_is_replayable = True

        if event_type not in ENTITLEMENT_MUTATING_STRIPE_EVENTS:
            _mark_webhook_processed(conn, event_id=event_id, commit=False)
            conn.commit()
            return StripeWebhookResult(
                event_id=event_id,
                event_type=event_type,
                user_id="",
                entitlement_state="",
                replayed=not inserted,
            )

        obj = _event_object(event)
        purchase_kind = _stripe_purchase_kind(obj)
        if event_type == "checkout.session.completed" and purchase_kind == "inference_refuel":
            user_id = _stripe_user_id(obj)
            deployment_id = _stripe_deployment_id(obj)
            credit_cents = _stripe_metadata_positive_int(obj, "credit_cents", "provider_credit_cents")
            retail_cents = _stripe_metadata_positive_int(obj, "retail_cents", "amount_cents")
            if not deployment_id:
                raise ArcLinkEntitlementError("Stripe refuel checkout did not include an ArcLink deployment id")
            if credit_cents <= 0:
                raise ArcLinkEntitlementError("Stripe refuel checkout did not include positive credit cents")
            if retail_cents <= 0:
                raise ArcLinkEntitlementError("Stripe refuel checkout did not include positive retail cents")
            _require_paid_checkout_session(
                obj,
                purchase_kind="refuel",
                minimum_amount_cents=retail_cents,
            )
            stripe_customer_id = str(obj.get("customer") or "").strip()
            stripe_customer_email = _stripe_customer_email(obj)
            _assert_refuel_checkout_account(
                conn,
                user_id=user_id,
                deployment_id=deployment_id,
                stripe_customer_id=stripe_customer_id,
                client_reference_id=str(obj.get("client_reference_id") or ""),
            )
            if stripe_customer_id:
                upsert_arclink_user(
                    conn,
                    user_id=user_id,
                    email=stripe_customer_email,
                    stripe_customer_id=stripe_customer_id,
                    commit=False,
                )
            credit = grant_arclink_refuel_credit(
                conn,
                user_id=user_id,
                deployment_id=deployment_id,
                actor_id="stripe",
                reason="Stripe ArcPod Refueling paid",
                credit_cents=credit_cents,
                source_kind="stripe_checkout",
                source_id=str(obj.get("id") or event_id),
                metadata={
                    "stripe_event_id": event_id,
                    "stripe_checkout_session_id": str(obj.get("id") or ""),
                    "stripe_customer_id": stripe_customer_id,
                    "retail_cents": retail_cents,
                    "credit_cents": credit_cents,
                },
                commit=False,
            )
            applied = apply_arclink_refuel_credit_to_chutes_budget(
                conn,
                user_id=user_id,
                deployment_id=deployment_id,
                requested_cents=credit_cents,
                actor_id="stripe",
                reason="Apply paid ArcPod fuel to ArcPod budget",
                commit=False,
            )
            append_arclink_event(
                conn,
                subject_kind="deployment",
                subject_id=deployment_id,
                event_type="stripe_refuel_checkout_processed",
                metadata={
                    "stripe_event_id": event_id,
                    "stripe_checkout_session_id": str(obj.get("id") or ""),
                    "user_id": user_id,
                    "credit_id": str(credit.get("credit_id") or ""),
                    "retail_cents": retail_cents,
                    "credit_cents": credit_cents,
                    "applied_cents": int(applied.get("applied_cents") or 0),
                },
                commit=False,
            )
            _mark_webhook_processed(conn, event_id=event_id, commit=False)
            conn.commit()
            return StripeWebhookResult(
                event_id=event_id,
                event_type=event_type,
                user_id=user_id,
                entitlement_state="refuel_paid",
                replayed=not inserted,
                advanced_deployments=(deployment_id,),
            )

        subscription_id = _stripe_subscription_id(obj)
        stripe_customer_id = str(obj.get("customer") or "").strip()
        # An unpaid checkout.session.completed is invalid regardless of who it names —
        # reject it BEFORE resolving an owner (also keeps the "not paid" signal from
        # being masked by the fail-closed "did not resolve a local owner" error).
        if event_type == "checkout.session.completed":
            _require_paid_checkout_session(obj, purchase_kind="subscription")
        owner = _resolve_stripe_entitlement_owner(
            conn,
            event_type=event_type,
            obj=obj,
            subscription_id=subscription_id,
            stripe_customer_id=stripe_customer_id,
        )
        user_id = owner.user_id
        entitlement_state = _entitlement_for_stripe_event(event_type, obj)

        # Email-driven user merge: a single human can show up under multiple
        # user_ids (e.g. they started on Telegram earlier under one user_id,
        # then onboarded again on web under a fresh user_id). Stripe always
        # carries the canonical email, so the control plane deterministically
        # picks the canonical row and repoints owned rows before user upsert.
        stripe_customer_email = _stripe_customer_email(obj)
        allowed_user_ids = {user_id}
        if stripe_customer_email:
            merge_candidate_user_id = user_id
            merged = merge_arclink_user_identity_by_email(
                conn,
                email=stripe_customer_email,
                candidate_user_id=merge_candidate_user_id,
                actor_id="stripe",
                reason="Stripe webhook email identity merge",
                metadata={
                    "stripe_event_id": event_id,
                    "stripe_event_type": event_type,
                    "stripe_subscription_id": subscription_id,
                    "stripe_customer_id": stripe_customer_id,
                },
                commit=False,
            )
            user_id = str(merged["user_id"] or user_id)
            merged_ids = list(merged.get("merged_user_ids") or [])
            allowed_user_ids.update(str(value or "").strip() for value in merged_ids)
            allowed_user_ids.add(merge_candidate_user_id)
            if merged_ids:
                append_arclink_event(
                    conn,
                    subject_kind="user",
                    subject_id=user_id,
                    event_type="stripe_user_merged",
                    metadata={
                        "merged_from_user_id": user_id if user_id in merged_ids else (merged_ids[0] if merged_ids else ""),
                        "candidate_user_id": merge_candidate_user_id,
                        "merged_user_ids": merged_ids,
                        "stripe_customer_email": stripe_customer_email,
                        "stripe_event_id": event_id,
                        "stripe_event_type": event_type,
                    },
                    commit=False,
                )

        _assert_entitlement_account(
            conn,
            user_id=user_id,
            subscription_id=subscription_id,
            stripe_customer_id=stripe_customer_id,
            client_reference_id=str(obj.get("client_reference_id") or ""),
            allowed_user_ids=allowed_user_ids,
        )

        if subscription_id:
            mirror_status = _stripe_subscription_mirror_status(
                event_type=event_type,
                obj=obj,
                entitlement_state=entitlement_state,
            )
            upsert_arclink_subscription_mirror(
                conn,
                subscription_id=f"stripe:{subscription_id}",
                user_id=user_id,
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=subscription_id,
                status=mirror_status,
                current_period_end=str(obj.get("current_period_end") or ""),
                raw=obj,
                commit=False,
            )
        if stripe_customer_email:
            upsert_arclink_user(
                conn,
                user_id=user_id,
                email=stripe_customer_email,
                stripe_customer_id=stripe_customer_id,
                entitlement_state=entitlement_state,
                commit=False,
            )
        else:
            set_arclink_user_entitlement(
                conn,
                user_id=user_id,
                entitlement_state=entitlement_state,
                stripe_customer_id=stripe_customer_id,
                commit=False,
            )
        advanced = tuple(advance_arclink_entitlement_gates_for_user(conn, user_id=user_id, commit=False))
        onboarding_session_id = owner.onboarding_session_id
        if event_type == "checkout.session.completed" and onboarding_session_id:
            onboarding_synced = sync_arclink_onboarding_after_entitlement(
                conn,
                session_id=onboarding_session_id,
                checkout_session_id=str(obj.get("id") or ""),
                stripe_customer_id=stripe_customer_id,
                commit=False,
            )
            if not onboarding_synced:
                append_arclink_event(
                    conn,
                    subject_kind="onboarding_session",
                    subject_id=onboarding_session_id,
                    event_type="stripe_onboarding_sync_skipped",
                    metadata={
                        "stripe_event_id": event_id,
                        "stripe_checkout_session_id": str(obj.get("id") or ""),
                        "stripe_customer_id": stripe_customer_id,
                        "user_id": user_id,
                        "reason": "missing_or_unprovisionable_onboarding_deployment",
                    },
                    commit=False,
                )
        inference_allowance: dict[str, Any] = {}
        if event_type in {"invoice.payment_succeeded", "invoice.paid"} and entitlement_state == "paid":
            inference_allowance = apply_subscription_inference_allowance(
                conn,
                user_id=user_id,
                stripe_event_id=event_id,
                invoice_id=str(obj.get("id") or ""),
                subscription_id=subscription_id,
                actor_id="stripe",
                reason="Stripe subscription invoice paid inference allowance",
                commit=False,
            )
        append_arclink_event(
            conn,
            subject_kind="user",
            subject_id=user_id,
            event_type="stripe_webhook_processed",
            metadata={
                "stripe_event_id": event_id,
                "stripe_event_type": event_type,
                "stripe_subscription_id": subscription_id,
                "entitlement_state": entitlement_state,
                "advanced_deployments": list(advanced),
                "inference_allowance": inference_allowance,
            },
            commit=False,
        )
        if entitlement_state in {"past_due", "cancelled"}:
            append_arclink_audit(
                conn,
                action="payment_entitlement_blocked",
                actor_id="stripe",
                target_kind="user",
                target_id=user_id,
                reason=f"Stripe reported {event_type}",
                metadata={"stripe_event_id": event_id, "entitlement_state": entitlement_state},
                commit=False,
            )
        _mark_webhook_processed(conn, event_id=event_id, commit=False)
        conn.commit()
        return StripeWebhookResult(
            event_id=event_id,
            event_type=event_type,
            user_id=user_id,
            entitlement_state=entitlement_state,
            replayed=not inserted,
            advanced_deployments=advanced,
        )
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        if failure_is_replayable:
            _mark_webhook_failed_replayable(
                conn,
                event_id=event_id,
                event_type=event_type,
                payload_json=payload,
            )
        raise
