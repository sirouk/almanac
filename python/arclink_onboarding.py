#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from typing import Any, Mapping

from arclink_control import (
    advance_arclink_entitlement_gate,
    arclink_deployment_can_provision,
    reserve_arclink_deployment_prefix,
    upsert_arclink_user,
    utc_now_iso,
)


ARCLINK_PUBLIC_ONBOARDING_CHANNELS = frozenset({"web", "telegram", "discord"})
ARCLINK_ONBOARDING_ACTIVE_STATUSES = frozenset(
    {
        "started",
        "collecting",
        "checkout_open",
        "payment_pending",
        "paid",
        "provisioning_ready",
        "first_contacted",
    }
)
ARCLINK_ONBOARDING_TERMINAL_STATUSES = frozenset(
    {
        "payment_cancelled",
        "payment_expired",
        "payment_failed",
        "completed",
        "abandoned",
    }
)
ARCLINK_ONBOARDING_STATUSES = ARCLINK_ONBOARDING_ACTIVE_STATUSES | ARCLINK_ONBOARDING_TERMINAL_STATUSES
ARCLINK_ONBOARDING_EVENT_TYPES = frozenset(
    {
        "started",
        "question_answered",
        "checkout_opened",
        "payment_success",
        "payment_failure",
        "payment_cancelled",
        "payment_expired",
        "provisioning_requested",
        "first_agent_contact",
        "channel_handoff",
    }
)

_SECRET_KEY_RE = re.compile(r"(secret|token|api[_-]?key|password|credential|webhook|client[_-]?secret)", re.I)
_PLAINTEXT_SECRET_RE = re.compile(
    r"(?i)("
    r"sk_(live|test)_[a-z0-9]|"
    r"whsec_[a-z0-9]|"
    r"gh[pousr]_[a-z0-9]|"
    r"xox[baprs]-|"
    r"ntn_[a-z0-9]|"
    r"cloudflare[a-z0-9_-]*token|"
    r"\b\d{6,}:[a-z0-9_-]{20,}\b"
    r")"
)


class ArcLinkOnboardingError(ValueError):
    pass


def _json(value: Mapping[str, Any] | None) -> str:
    _reject_secret_material(value or {}, path="$")
    return json.dumps(dict(value or {}), sort_keys=True)


def _json_loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    parsed = json.loads(value)
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _reject_secret_material(value: Any, *, path: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            _reject_secret_material(child, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_secret_material(child, path=f"{path}[{index}]")
        return
    if not isinstance(value, str):
        return
    text = value.strip()
    if not text:
        return
    if _SECRET_KEY_RE.search(path) or _PLAINTEXT_SECRET_RE.search(text):
        raise ArcLinkOnboardingError(f"public onboarding state cannot store secret material at {path}")


def _clean_channel(channel: str) -> str:
    clean = str(channel or "").strip().lower()
    if clean not in ARCLINK_PUBLIC_ONBOARDING_CHANNELS:
        raise ArcLinkOnboardingError(f"unsupported ArcLink onboarding channel: {clean or 'blank'}")
    return clean


def _clean_identity(identity: str) -> str:
    clean = str(identity or "").strip()
    if not clean:
        raise ArcLinkOnboardingError("ArcLink onboarding channel identity is required")
    _reject_secret_material(clean, path="$.channel_identity")
    return clean


def normalize_arclink_public_onboarding_contact(*, channel: str, channel_identity: str) -> dict[str, str]:
    return {
        "channel": _clean_channel(channel),
        "channel_identity": _clean_identity(channel_identity),
    }


def _stable_id(prefix: str, *parts: str, length: int = 24) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def _stable_prefix(session_id: str) -> str:
    return f"arc-{hashlib.sha256(session_id.encode('utf-8')).hexdigest()[:12]}"


def _active_session_row(conn: sqlite3.Connection, *, channel: str, channel_identity: str) -> sqlite3.Row | None:
    placeholders = ",".join("?" for _ in ARCLINK_ONBOARDING_ACTIVE_STATUSES)
    return conn.execute(
        f"""
        SELECT *
        FROM arclink_onboarding_sessions
        WHERE LOWER(channel) = LOWER(?)
          AND LOWER(channel_identity) = LOWER(?)
          AND status IN ({placeholders})
        ORDER BY created_at
        LIMIT 1
        """,
        (channel, channel_identity, *sorted(ARCLINK_ONBOARDING_ACTIVE_STATUSES)),
    ).fetchone()


def _session_row(conn: sqlite3.Connection, session_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM arclink_onboarding_sessions WHERE session_id = ?", (session_id,)).fetchone()
    if row is None:
        raise KeyError(session_id)
    return row


def _update_session(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    commit: bool = True,
    **fields: str,
) -> dict[str, Any]:
    allowed = {
        "status",
        "current_step",
        "email_hint",
        "display_name_hint",
        "selected_plan_id",
        "selected_model_id",
        "user_id",
        "deployment_id",
        "checkout_session_id",
        "checkout_url",
        "checkout_state",
        "stripe_customer_id",
        "metadata_json",
        "completed_at",
    }
    updates = {key: value for key, value in fields.items() if key in allowed}
    if "status" in updates and updates["status"] not in ARCLINK_ONBOARDING_STATUSES:
        raise ArcLinkOnboardingError(f"unsupported ArcLink onboarding status: {updates['status']}")
    if not updates:
        return dict(_session_row(conn, session_id))
    updates["updated_at"] = utc_now_iso()
    assignments = ", ".join(f"{key} = ?" for key in updates)
    conn.execute(
        f"UPDATE arclink_onboarding_sessions SET {assignments} WHERE session_id = ?",
        (*updates.values(), session_id),
    )
    if commit:
        conn.commit()
    return dict(_session_row(conn, session_id))


def record_arclink_onboarding_event(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    event_type: str,
    metadata: Mapping[str, Any] | None = None,
    event_id: str = "",
    commit: bool = True,
) -> str:
    clean_type = str(event_type or "").strip().lower()
    if clean_type not in ARCLINK_ONBOARDING_EVENT_TYPES:
        raise ArcLinkOnboardingError(f"unsupported ArcLink onboarding event type: {clean_type}")
    session = _session_row(conn, session_id)
    clean_id = event_id or _stable_id("onbevt", session_id, clean_type, utc_now_iso(), secrets.token_hex(4))
    conn.execute(
        """
        INSERT INTO arclink_onboarding_events (
          event_id, session_id, event_type, channel, channel_identity, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            clean_id,
            session_id,
            clean_type,
            str(session["channel"] or ""),
            str(session["channel_identity"] or ""),
            _json(metadata),
            utc_now_iso(),
        ),
    )
    if commit:
        conn.commit()
    return clean_id


def create_or_resume_arclink_onboarding_session(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session_id: str = "",
    email_hint: str = "",
    display_name_hint: str = "",
    selected_plan_id: str = "",
    selected_model_id: str = "",
    current_step: str = "started",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    clean_channel = _clean_channel(channel)
    clean_identity = _clean_identity(channel_identity)
    for key, value in {
        "email_hint": email_hint,
        "display_name_hint": display_name_hint,
        "selected_plan_id": selected_plan_id,
        "selected_model_id": selected_model_id,
    }.items():
        _reject_secret_material(value, path=f"$.{key}")
    existing = _active_session_row(conn, channel=clean_channel, channel_identity=clean_identity)
    if existing is not None:
        updates: dict[str, str] = {}
        for key, value in (
            ("email_hint", email_hint),
            ("display_name_hint", display_name_hint),
            ("selected_plan_id", selected_plan_id),
            ("selected_model_id", selected_model_id),
        ):
            if value and not str(existing[key] or ""):
                updates[key] = str(value).strip()
        if metadata:
            merged = _json_loads(str(existing["metadata_json"] or "{}"))
            merged.update(dict(metadata))
            updates["metadata_json"] = _json(merged)
        if updates:
            return _update_session(conn, session_id=str(existing["session_id"]), **updates)
        return dict(existing)

    now = utc_now_iso()
    clean_session_id = session_id.strip() or _stable_id("onb", clean_channel, clean_identity, secrets.token_hex(8))
    conn.execute(
        """
        INSERT INTO arclink_onboarding_sessions (
          session_id, channel, channel_identity, status, current_step,
          email_hint, display_name_hint, selected_plan_id, selected_model_id,
          checkout_state, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, 'started', ?, ?, ?, ?, ?, '', ?, ?, ?)
        """,
        (
            clean_session_id,
            clean_channel,
            clean_identity,
            current_step,
            str(email_hint or "").strip(),
            str(display_name_hint or "").strip(),
            str(selected_plan_id or "").strip(),
            str(selected_model_id or "").strip(),
            _json(metadata),
            now,
            now,
        ),
    )
    record_arclink_onboarding_event(
        conn,
        session_id=clean_session_id,
        event_type="started",
        metadata={"channel": clean_channel},
        commit=False,
    )
    conn.commit()
    return dict(_session_row(conn, clean_session_id))


def answer_arclink_onboarding_question(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    question_key: str,
    answer_summary: str = "",
    email_hint: str = "",
    display_name_hint: str = "",
    selected_plan_id: str = "",
    selected_model_id: str = "",
) -> dict[str, Any]:
    updates: dict[str, str] = {"status": "collecting", "current_step": str(question_key or "").strip()}
    for key, value in (
        ("email_hint", email_hint),
        ("display_name_hint", display_name_hint),
        ("selected_plan_id", selected_plan_id),
        ("selected_model_id", selected_model_id),
    ):
        if value:
            _reject_secret_material(value, path=f"$.{key}")
            updates[key] = str(value).strip()
    session = _update_session(conn, session_id=session_id, commit=False, **updates)
    record_arclink_onboarding_event(
        conn,
        session_id=session_id,
        event_type="question_answered",
        metadata={"question_key": question_key, "answer_summary": answer_summary},
        commit=False,
    )
    conn.commit()
    return session


def prepare_arclink_onboarding_deployment(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    base_domain: str = "",
    prefix: str = "",
) -> dict[str, Any]:
    session = dict(_session_row(conn, session_id))
    user_id = str(session.get("user_id") or "") or _stable_id("arcusr", session_id, length=18)
    deployment_id = str(session.get("deployment_id") or "") or _stable_id("arcdep", session_id, length=18)
    upsert_arclink_user(
        conn,
        user_id=user_id,
        email=str(session.get("email_hint") or ""),
        display_name=str(session.get("display_name_hint") or ""),
    )
    existing = conn.execute("SELECT * FROM arclink_deployments WHERE deployment_id = ?", (deployment_id,)).fetchone()
    if existing is None:
        reserve_arclink_deployment_prefix(
            conn,
            deployment_id=deployment_id,
            user_id=user_id,
            prefix=prefix or _stable_prefix(session_id),
            base_domain=base_domain,
            status="entitlement_required",
            metadata={
                "onboarding_session_id": session_id,
                "onboarding_channel": str(session.get("channel") or ""),
                "selected_plan_id": str(session.get("selected_plan_id") or ""),
                "selected_model_id": str(session.get("selected_model_id") or ""),
            },
        )
    session = _update_session(
        conn,
        session_id=session_id,
        user_id=user_id,
        deployment_id=deployment_id,
    )
    return session


def open_arclink_onboarding_checkout(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    stripe_client: Any,
    price_id: str,
    success_url: str,
    cancel_url: str,
    base_domain: str = "",
) -> dict[str, Any]:
    session = prepare_arclink_onboarding_deployment(conn, session_id=session_id, base_domain=base_domain)
    if str(session.get("checkout_session_id") or "") and str(session.get("checkout_state") or "") in {"open", "paid"}:
        return session
    user_id = str(session["user_id"])
    deployment_id = str(session["deployment_id"])
    checkout = stripe_client.create_checkout_session(
        user_id=user_id,
        client_reference_id=user_id,
        price_id=price_id,
        success_url=success_url,
        cancel_url=cancel_url,
        idempotency_key=f"arclink:onboarding:checkout:{session_id}",
        metadata={
            "arclink_user_id": user_id,
            "arclink_onboarding_session_id": session_id,
            "arclink_deployment_id": deployment_id,
        },
    )
    session = _update_session(
        conn,
        session_id=session_id,
        status="checkout_open",
        current_step="checkout",
        checkout_session_id=str(checkout.get("id") or ""),
        checkout_url=str(checkout.get("url") or ""),
        checkout_state="open",
        commit=False,
    )
    record_arclink_onboarding_event(
        conn,
        session_id=session_id,
        event_type="checkout_opened",
        metadata={"checkout_session_id": str(checkout.get("id") or ""), "price_id": price_id},
        commit=False,
    )
    conn.commit()
    return session


def _mark_checkout_terminal(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    status: str,
    checkout_state: str,
    event_type: str,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    session = _update_session(
        conn,
        session_id=session_id,
        status=status,
        current_step=checkout_state,
        checkout_state=checkout_state,
        commit=False,
    )
    record_arclink_onboarding_event(conn, session_id=session_id, event_type=event_type, metadata=metadata, commit=False)
    conn.commit()
    return session


def mark_arclink_onboarding_checkout_cancelled(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    reason: str = "",
) -> dict[str, Any]:
    return _mark_checkout_terminal(
        conn,
        session_id=session_id,
        status="payment_cancelled",
        checkout_state="cancelled",
        event_type="payment_cancelled",
        metadata={"reason": reason},
    )


def mark_arclink_onboarding_checkout_expired(conn: sqlite3.Connection, *, session_id: str) -> dict[str, Any]:
    return _mark_checkout_terminal(
        conn,
        session_id=session_id,
        status="payment_expired",
        checkout_state="expired",
        event_type="payment_expired",
    )


def mark_arclink_onboarding_checkout_failed(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    reason: str = "",
) -> dict[str, Any]:
    return _mark_checkout_terminal(
        conn,
        session_id=session_id,
        status="payment_failed",
        checkout_state="failed",
        event_type="payment_failure",
        metadata={"reason": reason},
    )


def sync_arclink_onboarding_after_entitlement(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    checkout_session_id: str = "",
    stripe_customer_id: str = "",
    commit: bool = True,
) -> bool:
    session = dict(_session_row(conn, session_id))
    deployment_id = str(session.get("deployment_id") or "")
    if not deployment_id or not arclink_deployment_can_provision(conn, deployment_id=deployment_id):
        return False
    advance_arclink_entitlement_gate(conn, deployment_id=deployment_id, commit=commit)
    _update_session(
        conn,
        session_id=session_id,
        status="provisioning_ready",
        current_step="provisioning_requested",
        checkout_session_id=checkout_session_id or str(session.get("checkout_session_id") or ""),
        checkout_state="paid",
        stripe_customer_id=stripe_customer_id or str(session.get("stripe_customer_id") or ""),
        commit=False,
    )
    record_arclink_onboarding_event(
        conn,
        session_id=session_id,
        event_type="payment_success",
        metadata={"checkout_session_id": checkout_session_id},
        commit=False,
    )
    record_arclink_onboarding_event(
        conn,
        session_id=session_id,
        event_type="provisioning_requested",
        metadata={"deployment_id": deployment_id},
        commit=False,
    )
    if commit:
        conn.commit()
    return True


def handoff_arclink_onboarding_channel(
    conn: sqlite3.Connection,
    *,
    source_session_id: str,
    target_channel: str,
    target_channel_identity: str,
) -> dict[str, Any]:
    source = dict(_session_row(conn, source_session_id))
    target = create_or_resume_arclink_onboarding_session(
        conn,
        channel=target_channel,
        channel_identity=target_channel_identity,
        email_hint=str(source.get("email_hint") or ""),
        display_name_hint=str(source.get("display_name_hint") or ""),
        selected_plan_id=str(source.get("selected_plan_id") or ""),
        selected_model_id=str(source.get("selected_model_id") or ""),
        metadata={"handoff_from_session_id": source_session_id},
    )
    updates = {
        key: str(source.get(key) or "")
        for key in ("user_id", "deployment_id", "checkout_session_id", "checkout_url", "checkout_state", "stripe_customer_id")
        if str(source.get(key) or "")
    }
    if updates:
        target = _update_session(conn, session_id=str(target["session_id"]), **updates)
    record_arclink_onboarding_event(
        conn,
        session_id=source_session_id,
        event_type="channel_handoff",
        metadata={
            "target_channel": _clean_channel(target_channel),
            "target_session_id": str(target["session_id"]),
        },
    )
    return target


def record_arclink_onboarding_first_agent_contact(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    channel: str,
    channel_identity: str,
) -> dict[str, Any]:
    session = _update_session(
        conn,
        session_id=session_id,
        status="first_contacted",
        current_step="first_agent_contact",
        commit=False,
    )
    record_arclink_onboarding_event(
        conn,
        session_id=session_id,
        event_type="first_agent_contact",
        metadata={"channel": _clean_channel(channel), "channel_identity": _clean_identity(channel_identity)},
        commit=False,
    )
    conn.commit()
    return session
