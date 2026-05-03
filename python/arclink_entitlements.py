#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Mapping

from arclink_control import (
    advance_arclink_entitlement_gates_for_user,
    append_arclink_audit,
    append_arclink_event,
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
    kind: str  # "subscription_without_deployment" or "deployment_without_subscription"
    user_id: str
    detail: str


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
              AND d.status NOT IN ('entitlement_required', 'teardown_complete', 'cancelled')
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
        WHERE d.status NOT IN ('entitlement_required', 'teardown_complete', 'cancelled')
          AND NOT EXISTS (
            SELECT 1 FROM arclink_subscriptions s
            WHERE s.user_id = d.user_id
              AND s.status IN ('active', 'trialing', 'paid')
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


def _stripe_customer_email(obj: Mapping[str, Any]) -> str:
    customer_details = _safe_mapping(obj.get("customer_details"))
    return _first_nonempty((
        customer_details.get("email"),
        obj.get("customer_email"),
        obj.get("receipt_email"),
    ))


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
        subscription_id = _stripe_subscription_id(obj)
        stripe_customer_id = str(obj.get("customer") or "").strip()
        user_id = _first_nonempty((
            _stripe_user_id_or_empty(obj),
            _stripe_user_id_from_local_state(
                conn,
                subscription_id=subscription_id,
                stripe_customer_id=stripe_customer_id,
            ),
        ))
        if not user_id:
            raise ArcLinkEntitlementError("Stripe webhook did not include an ArcLink user id")
        entitlement_state = _entitlement_for_stripe_event(event_type, obj)

        if subscription_id:
            mirror_status = entitlement_state if event_type == "invoice.payment_failed" else str(obj.get("status") or entitlement_state)
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
        stripe_customer_email = _stripe_customer_email(obj)
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
        onboarding_session_id = _stripe_onboarding_session_id(obj)
        if event_type == "checkout.session.completed" and onboarding_session_id:
            sync_arclink_onboarding_after_entitlement(
                conn,
                session_id=onboarding_session_id,
                checkout_session_id=str(obj.get("id") or ""),
                stripe_customer_id=stripe_customer_id,
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
