#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Mapping

from almanac_control import (
    advance_arclink_entitlement_gates_for_user,
    append_arclink_audit,
    append_arclink_event,
    set_arclink_user_entitlement,
    upsert_arclink_subscription_mirror,
    utc_now_iso,
)
from arclink_adapters import verify_stripe_webhook
from arclink_onboarding import sync_arclink_onboarding_after_entitlement


class ArcLinkEntitlementError(ValueError):
    pass


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


def _subscription_details_metadata(value: Mapping[str, Any]) -> Mapping[str, Any]:
    details = value.get("subscription_details")
    if not isinstance(details, Mapping):
        return {}
    raw = details.get("metadata")
    return raw if isinstance(raw, Mapping) else {}


def _subscription_details_raw_metadata(details: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = details.get("metadata")
    return raw if isinstance(raw, Mapping) else {}


def _parent_subscription_details(value: Mapping[str, Any]) -> Mapping[str, Any]:
    parent = value.get("parent")
    if not isinstance(parent, Mapping):
        return {}
    details = parent.get("subscription_details")
    return details if isinstance(details, Mapping) else {}


def _stripe_user_id(obj: Mapping[str, Any]) -> str:
    metadata = _metadata(obj)
    parent_subscription_metadata = _subscription_details_raw_metadata(_parent_subscription_details(obj))
    candidates = (
        metadata.get("arclink_user_id"),
        metadata.get("user_id"),
        obj.get("client_reference_id"),
        _subscription_details_metadata(obj).get("arclink_user_id"),
        _subscription_details_metadata(obj).get("user_id"),
        parent_subscription_metadata.get("arclink_user_id"),
        parent_subscription_metadata.get("user_id"),
    )
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value
    raise ArcLinkEntitlementError("Stripe webhook did not include an ArcLink user id")


def _stripe_subscription_id(obj: Mapping[str, Any]) -> str:
    for key in ("subscription", "id"):
        value = str(obj.get(key) or "").strip()
        if value.startswith("sub_"):
            return value
    parent = obj.get("parent")
    if isinstance(parent, Mapping):
        value = str(parent.get("subscription") or "").strip()
        if value.startswith("sub_"):
            return value
    parent_subscription = str(_parent_subscription_details(obj).get("subscription") or "").strip()
    if parent_subscription.startswith("sub_"):
        return parent_subscription
    return ""


def _stripe_onboarding_session_id(obj: Mapping[str, Any]) -> str:
    metadata = _metadata(obj)
    parent_subscription_metadata = _subscription_details_raw_metadata(_parent_subscription_details(obj))
    candidates = (
        metadata.get("arclink_onboarding_session_id"),
        metadata.get("onboarding_session_id"),
        _subscription_details_metadata(obj).get("arclink_onboarding_session_id"),
        _subscription_details_metadata(obj).get("onboarding_session_id"),
        parent_subscription_metadata.get("arclink_onboarding_session_id"),
        parent_subscription_metadata.get("onboarding_session_id"),
    )
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value
    return ""


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
        user_id = _stripe_user_id(obj)
        subscription_id = _stripe_subscription_id(obj)
        stripe_customer_id = str(obj.get("customer") or "").strip()
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
