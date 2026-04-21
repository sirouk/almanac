#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import pwd
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from almanac_control import (
    Config,
    RateLimitError,
    approve_request,
    cancel_onboarding_session,
    config_env_value,
    connect_db,
    find_latest_onboarding_session_for_sender,
    find_active_onboarding_session,
    get_notion_identity_claim,
    onboarding_session_has_started_provisioning,
    operator_telegram_action_extra,
    queue_notification,
    request_bootstrap,
    save_onboarding_session,
    start_notion_identity_claim,
    start_onboarding_session,
    utc_now_iso,
    write_onboarding_secret,
    write_onboarding_platform_token_secret,
)
from almanac_discord import discord_send_message
from almanac_onboarding_provider_auth import (
    ProviderSetupSpec,
    complete_anthropic_pkce_authorization,
    normalize_anthropic_credential,
    normalize_api_key_credential,
    provider_browser_auth_prompt,
    provider_credential_prompt,
    provider_secret_name,
    provider_setup_from_dict,
    resolve_provider_setup,
    start_anthropic_pkce_authorization,
    start_codex_device_authorization,
)
from almanac_telegram import telegram_send_message


START_COMMANDS = {"/start", "/onboard", "start", "onboard"}
STATUS_COMMANDS = {"/status", "status"}
CANCEL_COMMANDS = {"/cancel", "cancel"}
VERIFY_NOTION_COMMANDS = {"/verify-notion", "verify-notion", "verify notion"}
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
    telegram_reply_markup: dict[str, Any] | None = None
    discord_components: list[dict[str, Any]] | None = None


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


def send_session_message(
    cfg: Config,
    session: dict[str, Any],
    text: str,
    *,
    telegram_reply_markup: dict[str, Any] | None = None,
    discord_components: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    platform = str(session.get("platform") or "").strip().lower()
    chat_id = str(session.get("chat_id") or "").strip()
    if not platform or not chat_id or not text:
        return None
    if platform == "telegram":
        token = resolve_curator_telegram_bot_token(cfg)
        if token:
            try:
                return telegram_send_message(
                    bot_token=token,
                    chat_id=chat_id,
                    text=text,
                    reply_markup=telegram_reply_markup,
                )
            except Exception:
                return None
        return None
    if platform == "discord":
        token = resolve_curator_discord_bot_token(cfg)
        if token:
            try:
                return discord_send_message(
                    bot_token=token,
                    channel_id=chat_id,
                    text=text,
                    components=discord_components,
                )
            except Exception:
                return None
    return None


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
                "Tap Approve / Deny below, or use one of these commands:",
                f"Telegram approve: /approve {session_id}",
                f"Telegram deny: /deny {session_id} optional reason",
            ]
        )
    elif cfg.operator_notify_platform == "discord":
        lines.extend(
            [
                "Use the configured primary Discord operator channel for approvals:",
                f"Discord approve: /approve {session_id}",
                f"Discord deny: /deny {session_id} optional reason",
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
        extra=operator_telegram_action_extra(
            cfg,
            scope="onboarding",
            target_id=str(session.get("session_id") or ""),
        ),
    )


def _bot_platform_name(session: dict[str, Any]) -> str:
    return str(session.get("answers", {}).get("bot_platform") or "telegram").strip().lower() or "telegram"


def _preferred_bot_name(session: dict[str, Any]) -> str:
    return str(session.get("answers", {}).get("preferred_bot_name") or "your bot")


def _model_options(cfg: Config) -> str:
    return ", ".join(sorted(cfg.model_presets))


def _session_requester_identity(session: dict[str, Any]) -> str:
    answers = session.get("answers", {})
    return format_user_label(
        str(session.get("platform") or ""),
        str(session.get("sender_username") or ""),
        str(session.get("sender_display_name") or answers.get("full_name") or ""),
        str(session.get("sender_id") or ""),
    )


def _provider_setup(session: dict[str, Any]) -> ProviderSetupSpec | None:
    answers = session.get("answers", {})
    return provider_setup_from_dict(answers.get("provider_setup"))


def _provider_auth_state(session: dict[str, Any]) -> dict[str, Any]:
    answers = session.get("answers", {})
    raw = answers.get("provider_browser_auth")
    return raw if isinstance(raw, dict) else {}

def _codex_browser_auth_error_state(message: str) -> dict[str, Any]:
    compact = message.strip() or "unknown OpenAI Codex auth error"
    return {
        "flow": "device_code",
        "provider": "openai-codex",
        "status": "error",
        "error_message": compact,
    }


def _bot_identity_answers(bot_platform: str, bot_identity: BotIdentity) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "bot_platform": bot_platform,
        "bot_id": bot_identity.bot_id,
        "bot_username": bot_identity.username,
        "bot_display_name": bot_identity.display_name,
    }
    if bot_platform == "telegram":
        payload["telegram_bot_id"] = bot_identity.bot_id
        payload["telegram_bot_username"] = bot_identity.username
    return payload


def begin_onboarding_provisioning(
    conn,
    cfg: Config,
    session: dict[str, Any],
    *,
    provider_secret_path: str,
) -> dict[str, Any]:
    if str(session.get("linked_request_id") or "").strip() and str(session.get("state") or "") == "provision-pending":
        return session

    answers = session.get("answers", {})
    bot_platform = _bot_platform_name(session)
    request = request_bootstrap(
        conn,
        cfg,
        requester_identity=_session_requester_identity(session),
        unix_user=str(answers.get("unix_user") or session.get("sender_id") or ""),
        source_ip=f"{session.get('platform') or 'chat'}:{session.get('sender_id') or 'unknown'}",
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
        actor=str(session.get("approved_by_actor") or f"{session.get('platform') or 'chat'}-operator"),
        cfg=cfg,
    )
    save_kwargs: dict[str, Any] = {
        "session_id": str(session["session_id"]),
        "state": "provision-pending",
        "answers": {
            "pending_provider_secret_path": provider_secret_path,
            "provider_browser_auth": {},
        },
        "linked_request_id": str(request["request_id"]),
        "linked_agent_id": str(request.get("agent_id") or ""),
        "provision_error": "",
    }
    if bot_platform == "telegram":
        save_kwargs["telegram_bot_id"] = str(answers.get("bot_id") or "")
        save_kwargs["telegram_bot_username"] = str(answers.get("bot_username") or "")
    return save_onboarding_session(conn, **save_kwargs)


def session_prompt(cfg: Config, session: dict[str, Any]) -> str:
    state = str(session.get("state") or "")
    answers = session.get("answers", {})
    preferred_bot_name = _preferred_bot_name(session)
    bot_platform = _bot_platform_name(session)
    provider_setup = _provider_setup(session)
    browser_auth = _provider_auth_state(session)
    if state == "awaiting-name":
        return "Hi. I’m Curator. I’ll guide the setup and keep us on the rails. What should I call you?"
    if state == "awaiting-unix-user":
        return "What Unix username do you want on this host?"
    if state == "awaiting-purpose":
        return "What should this agent help you practice or get done?"
    if state == "awaiting-bot-platform":
        return "Which bot platform should I wire for your own agent: `telegram` or `discord`?"
    if state == "awaiting-bot-name":
        return "What name should your own bot carry? A short plain-English name is enough."
    if state == "awaiting-model-preset":
        return f"Which model preset should this agent use? Available presets: `{_model_options(cfg)}`."
    if state == "awaiting-operator-approval":
        return "Thanks. I’ve sent this to the operator for approval. I’ll keep watch and continue here once I hear back."
    if state == "awaiting-bot-token":
        if bot_platform == "discord":
            return (
                "You’re approved. Set up your Discord bot like this:\n"
                "1. Go to https://discord.com/developers/applications and click New Application.\n"
                f"2. Name it {preferred_bot_name} or whatever you prefer.\n"
                "3. Open the Bot page for that application.\n"
                "4. Turn Public Bot on.\n"
                "5. Leave Requires OAuth2 Code Grant off.\n"
                "6. For DM-only use, you can leave the Permissions Integer at 0.\n"
                "7. Turn Message Content Intent on.\n"
                "8. Turn Server Members Intent on.\n"
                "9. Leave Presence Intent off unless you specifically want it.\n"
                "10. Open Installation and copy the install link for the app.\n"
                "11. Use that link to add the app to one of your servers or use Add App so you can start a DM with it. Discord DMs work once you and the bot share a server or the app has been installed for you.\n"
                "12. Copy the bot token. If needed, use Reset Token to mint a fresh one.\n"
                "13. Paste the bot token back to me here.\n"
                "Once I have the token, I’ll ask for the model provider credential, wire it to your agent, and stay on the handoff until it’s live."
            )
        return (
            "You’re approved. Create your bot with BotFather, give it the name you want, "
            f"and send me the API token for {preferred_bot_name}. I’ll ask for the model provider credential next, then wire everything and stay with it until it’s live."
        )
    if state == "awaiting-provider-credential" and provider_setup is not None:
        return provider_credential_prompt(provider_setup)
    if state == "awaiting-provider-browser-auth" and provider_setup is not None:
        return provider_browser_auth_prompt(provider_setup, browser_auth)
    if state == "provision-pending":
        return "I’m provisioning your agent and wiring your bot now. This usually lands within a minute. I’ll ping you as soon as your lane is ready."
    if state == "awaiting-notion-email":
        return (
            "Your lane is live. One last step for shared Notion access: reply with the Notion email you use in this organization's workspace. "
            "If you want to finish now and leave shared Notion writes disabled, reply `skip`."
        )
    if state == "awaiting-notion-verification":
        claim_url = str(answers.get("notion_claim_url") or "").strip()
        claimed_email = str(answers.get("notion_claim_email") or "").strip()
        expiry = str(answers.get("notion_claim_expires_at") or "").strip()
        expiry_note = ""
        if expiry:
            try:
                expires_at = dt.datetime.fromisoformat(expiry)
                expiry_note = f" This claim expires around {expires_at.strftime('%Y-%m-%d %H:%M UTC')}."
            except ValueError:
                expiry_note = ""
        lines = [
            "Open your Almanac verification page in Notion and make any edit there. A keystroke or property change is enough.",
        ]
        if claim_url:
            lines.append(claim_url)
        if claimed_email:
            lines.append(f"I’m watching for an edit from `{claimed_email}` and will finish automatically once it lands.{expiry_note}")
        else:
            lines.append("I’m watching for your verification edit and will finish automatically once it lands." + expiry_note)
        lines.append("If you want to finish now and leave shared Notion writes disabled, reply `skip`.")
        return "\n".join(lines)
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
            return (
                f"Your agent lane is live through the Discord bot `{bot_username}`. "
                "It already has the Almanac skills active by default, plus the shared Vault/qmd wiring. "
                "Use that bot from here on out. If Discord will not open the DM yet, add the app from the Developer Portal Installation link or place it in a server you both share, then try again."
            )
        if bot_platform == "telegram" and bot_username:
            return (
                f"Your agent lane is live at @{bot_username}. "
                "It already has the Almanac skills active by default, plus the shared Vault/qmd wiring. "
                "Talk to it there from now on."
            )
        return "Your agent lane is live. It already has the Almanac skills active by default, plus the shared Vault/qmd wiring."
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
        if onboarding_session_has_started_provisioning(session):
            request_id = str(session.get("linked_request_id") or "").strip()
            detail = (
                f" Ask an operator to cancel request `{request_id}` if provisioning has not started yet, "
                "or purge the enrollment after the lane is live."
                if request_id
                else " Ask an operator to use the enrollment purge flow if you still want this removed."
            )
            return session, [
                OutboundMessage(
                    incoming.chat_id,
                    "I have already started provisioning your lane, so I cannot wipe this clean from chat anymore."
                    + detail,
                )
            ]
        updated = cancel_onboarding_session(conn, cfg, session_id=str(session["session_id"]))
        return updated, [
            OutboundMessage(
                incoming.chat_id,
                f"Cancelled {updated['session_id']}. I wiped the staged onboarding state. Send /start when you want to try again.",
            )
        ]
    return None, None


def _completion_reply_for_session(
    conn,
    cfg: Config,
    session: dict[str, Any],
    *,
    fallback_text: str,
) -> list[OutboundMessage]:
    from almanac_onboarding_completion import completion_bundle_for_session

    bundle = completion_bundle_for_session(conn, cfg, session)
    if bundle is None:
        return [OutboundMessage(session["chat_id"], fallback_text)]
    return [
        OutboundMessage(
            str(session.get("chat_id") or ""),
            str(bundle.get("full_text") or fallback_text),
            telegram_reply_markup=bundle.get("telegram_reply_markup"),
            discord_components=bundle.get("discord_components"),
        )
    ]


def _resume_verify_notion_session(
    conn,
    cfg: Config,
    incoming: IncomingMessage,
) -> list[OutboundMessage]:
    session = find_latest_onboarding_session_for_sender(
        conn,
        platform=incoming.platform,
        sender_id=incoming.sender_id,
        redact_secrets=False,
    )
    if session is None or not str(session.get("linked_agent_id") or "").strip():
        return [OutboundMessage(incoming.chat_id, "Send /start when you want Curator to open an onboarding session.")]
    updated = save_onboarding_session(
        conn,
        session_id=str(session["session_id"]),
        state="awaiting-notion-email",
        chat_id=incoming.chat_id,
        sender_username=incoming.sender_username,
        sender_display_name=incoming.sender_display_name or str(session.get("sender_display_name") or ""),
        completed_at="",
        last_prompt_at=utc_now_iso(),
    )
    return [OutboundMessage(incoming.chat_id, session_prompt(cfg, updated))]


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
        if session is None and lower in VERIFY_NOTION_COMMANDS:
            return _resume_verify_notion_session(conn, cfg, incoming)
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
                pending_bot_token_path = write_onboarding_platform_token_secret(
                    cfg,
                    str(session["session_id"]),
                    bot_platform,
                    text,
                )
                provider_setup = resolve_provider_setup(cfg, str(answers.get("model_preset") or "codex"))
            except Exception as exc:  # noqa: BLE001
                return [OutboundMessage(incoming.chat_id, f"I couldn't continue onboarding yet: {exc}")]

            extra_answers = _bot_identity_answers(bot_platform, bot_identity)
            extra_answers["provider_setup"] = provider_setup.as_dict()
            save_kwargs: dict[str, Any] = {
                "session_id": str(session["session_id"]),
                "state": "awaiting-provider-credential",
                "answers": extra_answers,
                "pending_bot_token": "",
                "pending_bot_token_path": pending_bot_token_path,
                "provision_error": "",
            }
            if bot_platform == "telegram":
                save_kwargs["telegram_bot_id"] = bot_identity.bot_id
                save_kwargs["telegram_bot_username"] = bot_identity.username
            updated = save_onboarding_session(conn, **save_kwargs)
            if provider_setup.auth_flow == "codex-device":
                try:
                    auth_state = start_codex_device_authorization()
                except Exception as exc:  # noqa: BLE001
                    updated = save_onboarding_session(
                        conn,
                        session_id=str(session["session_id"]),
                        state="awaiting-provider-browser-auth",
                        answers={"provider_browser_auth": _codex_browser_auth_error_state(str(exc))},
                        provision_error=str(exc).strip() or "failed to mint OpenAI Codex sign-in code",
                    )
                    return [OutboundMessage(incoming.chat_id, session_prompt(cfg, updated))]
                updated = save_onboarding_session(
                    conn,
                    session_id=str(session["session_id"]),
                    state="awaiting-provider-browser-auth",
                    answers={"provider_browser_auth": auth_state},
                    provision_error="",
                )
            elif provider_setup.auth_flow == "anthropic-credential":
                try:
                    auth_state = start_anthropic_pkce_authorization()
                    updated = save_onboarding_session(
                        conn,
                        session_id=str(session["session_id"]),
                        state="awaiting-provider-browser-auth",
                        answers={"provider_browser_auth": auth_state},
                        provision_error="",
                    )
                except Exception as exc:  # noqa: BLE001
                    return [OutboundMessage(incoming.chat_id, f"I couldn't start the Claude authorization flow: {exc}")]
            return [OutboundMessage(incoming.chat_id, session_prompt(cfg, updated))]

        if state == "awaiting-provider-credential":
            provider_setup = _provider_setup(session)
            if provider_setup is None:
                return [OutboundMessage(incoming.chat_id, "I lost track of the provider setup for this session. Send /start and we’ll begin again.")]
            if provider_setup.auth_flow == "codex-device":
                try:
                    updated = save_onboarding_session(
                        conn,
                        session_id=str(session["session_id"]),
                        state="awaiting-provider-browser-auth",
                        answers={"provider_browser_auth": start_codex_device_authorization()},
                        provision_error="",
                    )
                except Exception as exc:  # noqa: BLE001
                    updated = save_onboarding_session(
                        conn,
                        session_id=str(session["session_id"]),
                        state="awaiting-provider-browser-auth",
                        answers={"provider_browser_auth": _codex_browser_auth_error_state(str(exc))},
                        provision_error=str(exc).strip() or "failed to mint OpenAI Codex sign-in code",
                    )
                return [OutboundMessage(incoming.chat_id, session_prompt(cfg, updated))]
            try:
                if provider_setup.provider_id == "anthropic" and lower in {"oauth", "/oauth", "browser"}:
                    updated = save_onboarding_session(
                        conn,
                        session_id=str(session["session_id"]),
                        state="awaiting-provider-browser-auth",
                        answers={"provider_browser_auth": start_anthropic_pkce_authorization()},
                    )
                    return [OutboundMessage(incoming.chat_id, session_prompt(cfg, updated))]
                if provider_setup.provider_id == "anthropic":
                    provider_secret = normalize_anthropic_credential(text)
                else:
                    provider_secret = normalize_api_key_credential(provider_setup, text)
                provider_secret_path = write_onboarding_secret(
                    cfg,
                    str(session["session_id"]),
                    provider_secret_name(provider_setup),
                    provider_secret,
                )
                updated = save_onboarding_session(
                    conn,
                    session_id=str(session["session_id"]),
                    answers={"pending_provider_secret_path": provider_secret_path},
                )
                updated = begin_onboarding_provisioning(conn, cfg, updated, provider_secret_path=provider_secret_path)
            except Exception as exc:  # noqa: BLE001
                return [OutboundMessage(incoming.chat_id, str(exc).strip() or "That credential was rejected.")]

            bot_label = str(updated.get("answers", {}).get("bot_username") or updated.get("answers", {}).get("bot_display_name") or _preferred_bot_name(updated))
            unix_user = str(updated.get("answers", {}).get("unix_user") or incoming.sender_id)
            if _bot_platform_name(updated) == "discord":
                return [OutboundMessage(incoming.chat_id, f"Good. I have what I need. I’m provisioning `{unix_user}` now and wiring `{bot_label}`. I’ll tell you when the lane is ready.")]
            return [OutboundMessage(incoming.chat_id, f"Good. I have what I need. I’m provisioning `{unix_user}` now and wiring @{bot_label}. I’ll tell you when the lane is ready.")]

        if state == "awaiting-provider-browser-auth":
            provider_setup = _provider_setup(session)
            if provider_setup is None:
                return [OutboundMessage(incoming.chat_id, "I lost track of the provider setup for this session. Send /start and we’ll begin again.")]
            if lower in {"restart", "/restart"} and provider_setup.auth_flow == "codex-device":
                try:
                    auth_state = start_codex_device_authorization()
                    updated = save_onboarding_session(
                        conn,
                        session_id=str(session["session_id"]),
                        answers={"provider_browser_auth": auth_state},
                        provision_error="",
                    )
                except Exception as exc:  # noqa: BLE001
                    updated = save_onboarding_session(
                        conn,
                        session_id=str(session["session_id"]),
                        answers={"provider_browser_auth": _codex_browser_auth_error_state(str(exc))},
                        provision_error=str(exc).strip() or "failed to mint OpenAI Codex sign-in code",
                    )
                return [OutboundMessage(incoming.chat_id, session_prompt(cfg, updated))]
            if provider_setup.provider_id != "anthropic":
                return [OutboundMessage(incoming.chat_id, session_prompt(cfg, session))]
            try:
                stripped = text.strip()
                if stripped.startswith("sk-ant-api-") or stripped.startswith("sk-ant-oat-"):
                    provider_secret = normalize_anthropic_credential(stripped)
                    auth_state = dict(_provider_auth_state(session) or {})
                    auth_state["status"] = "bypassed"
                else:
                    provider_secret, auth_state = complete_anthropic_pkce_authorization(_provider_auth_state(session), text)
                provider_secret_path = write_onboarding_secret(
                    cfg,
                    str(session["session_id"]),
                    provider_secret_name(provider_setup),
                    provider_secret,
                )
                updated = save_onboarding_session(
                    conn,
                    session_id=str(session["session_id"]),
                    answers={
                        "provider_browser_auth": auth_state,
                        "pending_provider_secret_path": provider_secret_path,
                    },
                )
                updated = begin_onboarding_provisioning(conn, cfg, updated, provider_secret_path=provider_secret_path)
            except Exception as exc:  # noqa: BLE001
                return [OutboundMessage(incoming.chat_id, str(exc).strip() or "That Claude authorization code was rejected.")]

            bot_label = str(updated.get("answers", {}).get("bot_username") or updated.get("answers", {}).get("bot_display_name") or _preferred_bot_name(updated))
            unix_user = str(updated.get("answers", {}).get("unix_user") or incoming.sender_id)
            if _bot_platform_name(updated) == "discord":
                return [OutboundMessage(incoming.chat_id, f"Good. I have what I need. I’m provisioning `{unix_user}` now and wiring `{bot_label}`. I’ll tell you when the lane is ready.")]
            return [OutboundMessage(incoming.chat_id, f"Good. I have what I need. I’m provisioning `{unix_user}` now and wiring @{bot_label}. I’ll tell you when the lane is ready.")]

        if state == "awaiting-notion-email":
            if lower == "skip":
                updated = save_onboarding_session(
                    conn,
                    session_id=str(session["session_id"]),
                    state="completed",
                    answers={
                        "notion_verification_skipped": True,
                        "notion_claim_email": "",
                        "notion_claim_id": "",
                        "notion_claim_url": "",
                        "notion_claim_expires_at": "",
                    },
                    completed_at=utc_now_iso(),
                )
                return _completion_reply_for_session(
                    conn,
                    cfg,
                    updated,
                    fallback_text=(
                        "Your lane is ready. Shared Notion writes stay read-only until you reply "
                        "`/verify-notion` here and finish the claim."
                    ),
                )
            agent_id = str(session.get("linked_agent_id") or "").strip()
            answers = session.get("answers", {})
            unix_user = str(answers.get("unix_user") or "").strip()
            if not agent_id or not unix_user:
                return [OutboundMessage(incoming.chat_id, "I lost track of your lane details. Send /start and I’ll re-open onboarding cleanly.")]
            try:
                claim = start_notion_identity_claim(
                    conn,
                    session_id=str(session["session_id"]),
                    agent_id=agent_id,
                    unix_user=unix_user,
                    claimed_notion_email=text,
                )
            except Exception as exc:  # noqa: BLE001
                return [OutboundMessage(incoming.chat_id, str(exc).strip() or "I couldn't start Notion verification yet.")]
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-notion-verification",
                answers={
                    "notion_verification_skipped": False,
                    "notion_claim_email": str(claim.get("claimed_notion_email") or ""),
                    "notion_claim_id": str(claim.get("claim_id") or ""),
                    "notion_claim_url": str(claim.get("notion_page_url") or ""),
                    "notion_claim_expires_at": str(claim.get("expires_at") or ""),
                },
            )
            return [OutboundMessage(incoming.chat_id, session_prompt(cfg, updated))]

        if state == "awaiting-notion-verification":
            if lower == "skip":
                claim_id = str((session.get("answers") or {}).get("notion_claim_id") or "").strip()
                if claim_id:
                    try:
                        from almanac_control import mark_notion_identity_claim

                        mark_notion_identity_claim(
                            conn,
                            claim_id=claim_id,
                            status="skipped",
                            failure_reason="user skipped self-serve notion verification during onboarding",
                        )
                    except Exception:
                        pass
                updated = save_onboarding_session(
                    conn,
                    session_id=str(session["session_id"]),
                    state="completed",
                    answers={"notion_verification_skipped": True},
                    completed_at=utc_now_iso(),
                )
                return _completion_reply_for_session(
                    conn,
                    cfg,
                    updated,
                    fallback_text=(
                        "Your lane is ready. Shared Notion writes stay read-only until you reply "
                        "`/verify-notion` here and finish the claim."
                    ),
                )
            if lower in VERIFY_NOTION_COMMANDS or lower == "status":
                claim_id = str((session.get("answers") or {}).get("notion_claim_id") or "").strip()
                claim = get_notion_identity_claim(conn, claim_id=claim_id) if claim_id else None
                if claim is not None and str(claim.get("status") or "").strip() == "expired":
                    updated = save_onboarding_session(
                        conn,
                        session_id=str(session["session_id"]),
                        state="awaiting-notion-email",
                        answers={
                            "notion_claim_email": "",
                            "notion_claim_id": "",
                            "notion_claim_url": "",
                            "notion_claim_expires_at": "",
                        },
                    )
                    return [
                        OutboundMessage(
                            incoming.chat_id,
                            "That verification link expired, so I opened a fresh claim step for you.\n\n"
                            + session_prompt(cfg, updated),
                        )
                    ]
            return [OutboundMessage(incoming.chat_id, session_prompt(cfg, session))]

        return [OutboundMessage(incoming.chat_id, session_prompt(cfg, session))]
