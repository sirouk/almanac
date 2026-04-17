#!/usr/bin/env python3
from __future__ import annotations

import pwd
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from almanac_control import (
    Config,
    RateLimitError,
    approve_request,
    config_env_value,
    connect_db,
    find_active_onboarding_session,
    queue_notification,
    request_bootstrap,
    save_onboarding_session,
    start_onboarding_session,
    utc_now_iso,
    write_onboarding_platform_token_secret,
)
from almanac_discord import discord_send_message
from almanac_telegram import telegram_send_message


START_COMMANDS = {"/start", "/onboard", "start", "onboard"}
STATUS_COMMANDS = {"/status", "status"}
CANCEL_COMMANDS = {"/cancel", "cancel"}
UNIX_USER_PATTERN = re.compile(r"^[a-z_][a-z0-9_-]{0,30}$")
PLATFORM_ALIASES = {
    "telegram": "telegram",
    "tg": "telegram",
    "discord": "discord",
    "dc": "discord",
}


@dataclass(frozen=True)
class IncomingMessage:
    platform: str
    chat_id: str
    sender_id: str
    text: str
    sender_username: str = ""
    sender_display_name: str = ""
    reply_to_message_id: int | None = None


@dataclass(frozen=True)
class OutboundMessage:
    chat_id: str
    text: str
    reply_to_message_id: int | None = None


@dataclass(frozen=True)
class BotIdentity:
    bot_id: str
    username: str = ""
    display_name: str = ""


BotTokenValidator = Callable[[str], BotIdentity]


def read_env_file_value(path: Path, key: str) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() != key:
            continue
        return value.strip().strip("'\"")
    return ""


def resolve_curator_telegram_bot_token(cfg: Config) -> str:
    token = config_env_value("TELEGRAM_BOT_TOKEN", "").strip()
    if token:
        return token
    return read_env_file_value(cfg.curator_hermes_home / ".env", "TELEGRAM_BOT_TOKEN").strip()


def resolve_curator_discord_bot_token(cfg: Config) -> str:
    token = config_env_value("DISCORD_BOT_TOKEN", "").strip()
    if token:
        return token
    return read_env_file_value(cfg.curator_hermes_home / ".env", "DISCORD_BOT_TOKEN").strip()


def send_session_message(cfg: Config, session: dict[str, Any], text: str) -> None:
    platform = str(session.get("platform") or "").strip().lower()
    chat_id = str(session.get("chat_id") or "").strip()
    if not platform or not chat_id or not text:
        return
    if platform == "telegram":
        token = resolve_curator_telegram_bot_token(cfg)
        if token:
            try:
                telegram_send_message(bot_token=token, chat_id=chat_id, text=text)
            except Exception:
                return
        return
    if platform == "discord":
        token = resolve_curator_discord_bot_token(cfg)
        if token:
            try:
                discord_send_message(bot_token=token, channel_id=chat_id, text=text)
            except Exception:
                return


def notify_session_state(cfg: Config, session: dict[str, Any]) -> None:
    send_session_message(cfg, session, session_prompt(cfg, session))


def format_user_label(platform: str, username: str, display_name: str, sender_id: str) -> str:
    normalized_platform = str(platform or "").strip().lower()
    if username:
        return f"@{username}" if normalized_platform == "telegram" else username
    if display_name:
        return display_name
    return f"{normalized_platform or 'user'}:{sender_id}"


def desired_unix_user_available(unix_user: str) -> tuple[bool, str]:
    candidate = unix_user.strip().lower()
    if not UNIX_USER_PATTERN.fullmatch(candidate):
        return False, "Use 1-31 chars: lowercase letters, digits, `_`, or `-`, starting with a letter or `_`."
    try:
        pwd.getpwnam(candidate)
        return False, f"`{candidate}` already exists on the host. Pick another Unix username."
    except KeyError:
        return True, ""


def _operator_target(cfg: Config) -> tuple[str, str]:
    return (
        cfg.operator_notify_channel_id or cfg.operator_notify_platform or "operator",
        cfg.operator_notify_platform or "tui-only",
    )


def _parse_platform_choice(raw_text: str) -> str:
    return PLATFORM_ALIASES.get(raw_text.strip().lower(), "")


def _parse_model_preset(cfg: Config, raw_text: str) -> str:
    normalized = raw_text.strip().lower()
    if normalized in cfg.model_presets:
        return normalized
    compact = normalized.replace(" ", "").replace("-", "").replace("_", "")
    for key in cfg.model_presets:
        if compact == key.replace("-", "").replace("_", ""):
            return key
    return ""


def _operator_review_message(cfg: Config, session: dict[str, Any]) -> str:
    answers = session.get("answers", {})
    requester = format_user_label(
        str(session.get("platform") or ""),
        str(session.get("sender_username") or ""),
        str(session.get("sender_display_name") or answers.get("full_name") or ""),
        str(session.get("sender_id") or ""),
    )
    session_id = str(session.get("session_id") or "")
    model_preset = str(answers.get("model_preset") or "codex")
    bot_platform = str(answers.get("bot_platform") or "telegram")
    lines = [
        f"Onboarding request {session_id}",
        f"Requester: {requester}",
        f"Intake platform: {session.get('platform') or '(missing)'}",
        f"Name: {answers.get('full_name') or '(missing)'}",
        f"Unix user: {answers.get('unix_user') or '(missing)'}",
        f"Purpose: {answers.get('purpose') or '(missing)'}",
        f"Bot platform: {bot_platform}",
        f"Preferred bot name: {answers.get('preferred_bot_name') or '(missing)'}",
        f"Model preset: {model_preset}",
        f"Approve: ./bin/almanac-ctl onboarding approve {session_id}",
        f"Deny: ./bin/almanac-ctl onboarding deny {session_id} --reason 'optional reason'",
    ]
    if cfg.operator_notify_platform == "telegram":
        lines.extend(
            [
                f"Telegram approve: /approve {session_id}",
                f"Telegram deny: /deny {session_id} optional reason",
            ]
        )
    return "\n".join(lines)


def _notify_operator(conn, cfg: Config, session: dict[str, Any]) -> None:
    target_id, channel_kind = _operator_target(cfg)
    queue_notification(
        conn,
        target_kind="operator",
        target_id=target_id,
        channel_kind=channel_kind,
        message=_operator_review_message(cfg, session),
    )


def _bot_platform_name(session: dict[str, Any]) -> str:
    return str(session.get("answers", {}).get("bot_platform") or "telegram").strip().lower() or "telegram"


def _preferred_bot_name(session: dict[str, Any]) -> str:
    return str(session.get("answers", {}).get("preferred_bot_name") or "your bot")


def _model_options(cfg: Config) -> str:
    return ", ".join(sorted(cfg.model_presets))


def session_prompt(cfg: Config, session: dict[str, Any]) -> str:
    state = str(session.get("state") or "")
    answers = session.get("answers", {})
    preferred_bot_name = _preferred_bot_name(session)
    bot_platform = _bot_platform_name(session)
    if state == "awaiting-name":
        return "Hi. I’m Curator. What should I call you?"
    if state == "awaiting-unix-user":
        return "What Unix username do you want on this host?"
    if state == "awaiting-purpose":
        return "What do you want this agent to help you do?"
    if state == "awaiting-bot-platform":
        return "Which bot platform should I wire for your own agent: `telegram` or `discord`?"
    if state == "awaiting-bot-name":
        return "What name do you want for your own bot? A short plain-English name is enough."
    if state == "awaiting-model-preset":
        return f"Which model preset should this agent use? Available presets: `{_model_options(cfg)}`."
    if state == "awaiting-operator-approval":
        return "Thanks. I’ve asked the operator for approval. I’ll continue here once I hear back."
    if state == "awaiting-bot-token":
        if bot_platform == "discord":
            return (
                "You’re approved. Create your Discord bot in the Discord developer portal, copy its bot token, "
                f"and send it to me for {preferred_bot_name}. I’ll wire it to your agent and then step out."
            )
        return (
            "You’re approved. Create your bot with BotFather, give it the name you want, "
            f"and send me the API token for {preferred_bot_name}. I’ll wire it to your agent and then step out."
        )
    if state == "provision-pending":
        return "I’m provisioning your agent and wiring your bot now. This usually lands within a minute."
    if state == "denied":
        reason = str(session.get("denial_reason") or "").strip()
        return (
            f"The operator declined this onboarding request: {reason}"
            if reason
            else "The operator declined this onboarding request."
        )
    if state == "completed":
        bot_username = str(answers.get("bot_username") or session.get("telegram_bot_username") or "").strip()
        if bot_platform == "discord" and bot_username:
            return f"Your agent is live through the Discord bot `{bot_username}`. DM it directly from now on."
        if bot_platform == "telegram" and bot_username:
            return f"Your agent is live at @{bot_username}. Talk to it there from now on."
        return "Your agent is live. Talk to your own bot from now on."
    return "Send /start when you want to begin onboarding."


def _requester_identity(incoming: IncomingMessage, session: dict[str, Any]) -> str:
    answers = session.get("answers", {})
    return format_user_label(
        incoming.platform,
        incoming.sender_username,
        incoming.sender_display_name or str(answers.get("full_name") or ""),
        incoming.sender_id,
    )


def _status_or_cancel(
    cfg: Config,
    conn,
    session: dict[str, Any],
    incoming: IncomingMessage,
) -> tuple[dict[str, Any] | None, list[OutboundMessage] | None]:
    normalized = incoming.text.strip().lower()
    if normalized in STATUS_COMMANDS:
        return session, [OutboundMessage(incoming.chat_id, session_prompt(cfg, session))]
    if normalized in CANCEL_COMMANDS:
        updated = save_onboarding_session(
            conn,
            session_id=str(session["session_id"]),
            state="cancelled",
            completed_at=utc_now_iso(),
        )
        return updated, [OutboundMessage(incoming.chat_id, f"Cancelled {updated['session_id']}. Send /start when you want to try again.")]
    return None, None


def process_onboarding_message(
    cfg: Config,
    incoming: IncomingMessage,
    *,
    validate_bot_token: BotTokenValidator,
) -> list[OutboundMessage]:
    text = incoming.text.strip()
    lower = text.lower()
    with connect_db(cfg) as conn:
        if lower in START_COMMANDS:
            try:
                session = start_onboarding_session(
                    conn,
                    cfg,
                    platform=incoming.platform,
                    chat_id=incoming.chat_id,
                    sender_id=incoming.sender_id,
                    sender_username=incoming.sender_username,
                    sender_display_name=incoming.sender_display_name,
                )
            except RateLimitError as exc:
                return [OutboundMessage(incoming.chat_id, f"Slow down a bit. Try again in about {exc.retry_after_seconds}s.")]
            return [OutboundMessage(incoming.chat_id, session_prompt(cfg, session), incoming.reply_to_message_id)]

        session = find_active_onboarding_session(conn, platform=incoming.platform, sender_id=incoming.sender_id)
        if session is None:
            return [OutboundMessage(incoming.chat_id, "Send /start when you want Curator to open an onboarding session.")]

        _, early_messages = _status_or_cancel(cfg, conn, session, incoming)
        if early_messages is not None:
            return early_messages

        state = str(session.get("state") or "")
        if state == "awaiting-name":
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-unix-user",
                answers={"full_name": text},
                chat_id=incoming.chat_id,
                sender_username=incoming.sender_username,
                sender_display_name=incoming.sender_display_name or text,
            )
            return [OutboundMessage(incoming.chat_id, session_prompt(cfg, updated))]

        if state == "awaiting-unix-user":
            candidate = text.lower()
            ok, reason = desired_unix_user_available(candidate)
            if not ok:
                return [OutboundMessage(incoming.chat_id, reason)]
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-purpose",
                answers={"unix_user": candidate},
                chat_id=incoming.chat_id,
                sender_username=incoming.sender_username,
                sender_display_name=incoming.sender_display_name,
            )
            return [OutboundMessage(incoming.chat_id, session_prompt(cfg, updated))]

        if state == "awaiting-purpose":
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-bot-platform",
                answers={"purpose": text},
            )
            return [OutboundMessage(incoming.chat_id, session_prompt(cfg, updated))]

        if state == "awaiting-bot-platform":
            bot_platform = _parse_platform_choice(text)
            if not bot_platform:
                return [OutboundMessage(incoming.chat_id, "Please answer with `telegram` or `discord`.")]
            if bot_platform != incoming.platform:
                return [
                    OutboundMessage(
                        incoming.chat_id,
                        (
                            "For now, choose the same platform you’re onboarding from. "
                            "That lets me lock your private DM identity correctly before I hand you off."
                        ),
                    )
                ]
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-bot-name",
                answers={"bot_platform": bot_platform},
            )
            return [OutboundMessage(incoming.chat_id, session_prompt(cfg, updated))]

        if state == "awaiting-bot-name":
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-model-preset",
                answers={"preferred_bot_name": text},
            )
            return [OutboundMessage(incoming.chat_id, session_prompt(cfg, updated))]

        if state == "awaiting-model-preset":
            model_preset = _parse_model_preset(cfg, text)
            if not model_preset:
                return [OutboundMessage(incoming.chat_id, f"Choose one of: `{_model_options(cfg)}`.")]
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-operator-approval",
                answers={"model_preset": model_preset},
            )
            if not updated.get("operator_notified_at"):
                _notify_operator(conn, cfg, updated)
                updated = save_onboarding_session(
                    conn,
                    session_id=str(session["session_id"]),
                    operator_notified_at=utc_now_iso(),
                )
            return [OutboundMessage(incoming.chat_id, session_prompt(cfg, updated))]

        if state == "awaiting-operator-approval":
            return [OutboundMessage(incoming.chat_id, session_prompt(cfg, session))]

        if state == "awaiting-bot-token":
            bot_platform = _bot_platform_name(session)
            try:
                bot_identity = validate_bot_token(text)
            except Exception as exc:  # noqa: BLE001
                return [OutboundMessage(incoming.chat_id, str(exc).strip() or "That token was rejected.")]
            answers = session.get("answers", {})
            try:
                request = request_bootstrap(
                    conn,
                    cfg,
                    requester_identity=_requester_identity(incoming, session),
                    unix_user=str(answers.get("unix_user") or incoming.sender_id),
                    source_ip=f"{incoming.platform}:{incoming.sender_id}",
                    tailnet_identity=None,
                    issue_pending_token=False,
                    auto_provision=True,
                    requested_model_preset=str(answers.get("model_preset") or "codex"),
                    requested_channels=[bot_platform],
                )
                approve_request(
                    conn,
                    request_id=str(request["request_id"]),
                    surface="curator-channel",
                    actor=str(session.get("approved_by_actor") or f"{incoming.platform}-operator"),
                    cfg=cfg,
                )
                pending_bot_token_path = write_onboarding_platform_token_secret(
                    cfg,
                    str(session["session_id"]),
                    bot_platform,
                    text,
                )
            except Exception as exc:  # noqa: BLE001
                return [OutboundMessage(incoming.chat_id, f"I couldn't start provisioning yet: {exc}")]

            extra_answers = {
                "bot_platform": bot_platform,
                "bot_id": bot_identity.bot_id,
                "bot_username": bot_identity.username,
                "bot_display_name": bot_identity.display_name,
            }
            save_kwargs: dict[str, Any] = {
                "session_id": str(session["session_id"]),
                "state": "provision-pending",
                "answers": extra_answers,
                "pending_bot_token": "",
                "pending_bot_token_path": pending_bot_token_path,
                "linked_request_id": str(request["request_id"]),
                "linked_agent_id": str(request.get("agent_id") or ""),
                "provision_error": "",
            }
            if bot_platform == "telegram":
                save_kwargs["telegram_bot_id"] = bot_identity.bot_id
                save_kwargs["telegram_bot_username"] = bot_identity.username
            save_onboarding_session(conn, **save_kwargs)
            bot_label = bot_identity.username or bot_identity.display_name or _preferred_bot_name(session)
            if bot_platform == "discord":
                return [
                    OutboundMessage(
                        incoming.chat_id,
                        f"Thanks. I’m provisioning `{answers.get('unix_user')}` now and wiring `{bot_label}`. I’ll tell you when it’s ready.",
                    )
                ]
            return [
                OutboundMessage(
                    incoming.chat_id,
                    f"Thanks. I’m provisioning `{answers.get('unix_user')}` now and wiring @{bot_label}. I’ll tell you when it’s ready.",
                )
            ]

        return [OutboundMessage(incoming.chat_id, session_prompt(cfg, session))]
