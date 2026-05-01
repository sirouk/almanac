#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import asdict, dataclass
import sqlite3
from typing import Any, Mapping

from arclink_api_auth import check_arclink_rate_limit
from arclink_onboarding import (
    answer_arclink_onboarding_question,
    create_or_resume_arclink_onboarding_session,
    open_arclink_onboarding_checkout,
)
from arclink_product import base_domain as default_base_domain
from arclink_product import chutes_default_model


ARCLINK_PUBLIC_BOT_CHANNELS = frozenset({"telegram", "discord"})
ARCLINK_PUBLIC_BOT_PLANS = frozenset({"starter", "operator", "scale"})
ARCLINK_PUBLIC_BOT_TURN_LIMIT = 5
ARCLINK_PUBLIC_BOT_RATE_WINDOW_SECONDS = 900


class ArcLinkPublicBotError(ValueError):
    pass


@dataclass(frozen=True)
class ArcLinkPublicBotTurn:
    channel: str
    channel_identity: str
    session_id: str
    status: str
    current_step: str
    action: str
    reply: str
    checkout_url: str = ""
    user_id: str = ""
    deployment_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean_channel(channel: str) -> str:
    clean = str(channel or "").strip().lower()
    if clean not in ARCLINK_PUBLIC_BOT_CHANNELS:
        raise ArcLinkPublicBotError(f"unsupported ArcLink public bot channel: {clean or 'blank'}")
    return clean


def _clean_identity(identity: str) -> str:
    clean = str(identity or "").strip()
    if not clean:
        raise ArcLinkPublicBotError("ArcLink public bot channel identity is required")
    return clean


def _reply(session: Mapping[str, Any], *, action: str, reply: str) -> ArcLinkPublicBotTurn:
    return ArcLinkPublicBotTurn(
        channel=str(session.get("channel") or ""),
        channel_identity=str(session.get("channel_identity") or ""),
        session_id=str(session.get("session_id") or ""),
        status=str(session.get("status") or ""),
        current_step=str(session.get("current_step") or ""),
        action=action,
        reply=reply,
        checkout_url=str(session.get("checkout_url") or ""),
        user_id=str(session.get("user_id") or ""),
        deployment_id=str(session.get("deployment_id") or ""),
    )


def _parse_answer(text: str, prefix: str) -> str:
    _, _, value = text.partition(prefix)
    return value.strip()


def _check_public_bot_rate_limit(conn: sqlite3.Connection, *, channel: str, channel_identity: str) -> None:
    check_arclink_rate_limit(
        conn,
        scope=f"onboarding:{channel}",
        subject=channel_identity,
        limit=ARCLINK_PUBLIC_BOT_TURN_LIMIT,
        window_seconds=ARCLINK_PUBLIC_BOT_RATE_WINDOW_SECONDS,
    )


def handle_arclink_public_bot_turn(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    text: str,
    stripe_client: Any | None = None,
    price_id: str = "price_arclink_starter",
    base_domain: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> ArcLinkPublicBotTurn:
    clean_channel = _clean_channel(channel)
    clean_identity = _clean_identity(channel_identity)
    _check_public_bot_rate_limit(conn, channel=clean_channel, channel_identity=clean_identity)
    message = str(text or "").strip()
    command = message.lower()
    session = create_or_resume_arclink_onboarding_session(
        conn,
        channel=clean_channel,
        channel_identity=clean_identity,
        selected_model_id=chutes_default_model({}),
        metadata=metadata,
    )

    if command in {"", "/start", "start", "restart"}:
        return _reply(
            session,
            action="prompt_identity",
            reply="ArcLink deploys a private AI workspace. Send `email you@example.com` to continue.",
        )
    if command in {"status", "/status"}:
        return _reply(
            session,
            action="show_status",
            reply=f"Session {session['session_id']} is {session['status']}. Current step: {session['current_step'] or 'started'}.",
        )
    if command.startswith("email "):
        email = _parse_answer(message, " ")
        session = answer_arclink_onboarding_question(
            conn,
            session_id=str(session["session_id"]),
            question_key="email",
            answer_summary="email captured",
            email_hint=email,
        )
        return _reply(
            session,
            action="prompt_name",
            reply="Email saved. Send `name Your Name` next.",
        )
    if command.startswith("name "):
        name = _parse_answer(message, " ")
        session = answer_arclink_onboarding_question(
            conn,
            session_id=str(session["session_id"]),
            question_key="name",
            answer_summary="display name captured",
            display_name_hint=name,
        )
        return _reply(
            session,
            action="prompt_plan",
            reply="Name saved. Send `plan starter`, `plan operator`, or `plan scale`.",
        )
    if command.startswith("plan "):
        plan = _parse_answer(command, " ")
        if plan not in ARCLINK_PUBLIC_BOT_PLANS:
            raise ArcLinkPublicBotError(f"unsupported ArcLink public bot plan: {plan or 'blank'}")
        session = answer_arclink_onboarding_question(
            conn,
            session_id=str(session["session_id"]),
            question_key="plan",
            answer_summary=f"selected {plan}",
            selected_plan_id=plan,
            selected_model_id=chutes_default_model({}),
        )
        return _reply(
            session,
            action="prompt_checkout",
            reply="Plan saved. Send `checkout` to open the no-secret checkout contract.",
        )
    if command in {"checkout", "/checkout"}:
        if stripe_client is None:
            raise ArcLinkPublicBotError("checkout requires an injected Stripe client")
        root = f"https://{str(base_domain or default_base_domain({})).strip().strip('/')}"
        session = open_arclink_onboarding_checkout(
            conn,
            session_id=str(session["session_id"]),
            stripe_client=stripe_client,
            price_id=price_id,
            success_url=f"{root}/checkout/success",
            cancel_url=f"{root}/checkout/cancel",
            base_domain=base_domain or default_base_domain({}),
        )
        return _reply(
            session,
            action="open_checkout",
            reply=f"Checkout opened: {session['checkout_url']}",
        )
    return _reply(
        session,
        action="prompt_command",
        reply="Use `email`, `name`, `plan`, `checkout`, or `status`.",
    )
