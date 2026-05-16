#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hmac
import os
import re
import sys
import time
from typing import Any

from arclink_control import (
    Config,
    approve_ssot_pending_write,
    approve_request,
    approve_onboarding_session,
    clear_onboarding_update_failure,
    config_env_value,
    connect_db,
    deny_request,
    deny_ssot_pending_write,
    deny_onboarding_session,
    dismiss_pin_upgrade_action,
    find_active_onboarding_session,
    get_pin_upgrade_action_payload,
    get_onboarding_session,
    request_operator_action,
    get_setting,
    mark_onboarding_update_skipped,
    record_onboarding_update_failure,
    retry_discord_contact,
    save_onboarding_session,
    utc_now_iso,
    upsert_setting,
)
from arclink_onboarding_completion import (
    completion_followup_telegram_markup,
    completion_followup_telegram_parse_mode_for_session,
    completion_followup_text_for_session,
    completion_scrubbed_text_for_session,
)
from arclink_onboarding_flow import (
    BotIdentity,
    IncomingMessage,
    notify_session_state,
    parse_notion_setup_callback_data,
    process_onboarding_message,
    resolve_curator_telegram_bot_token,
)
from arclink_telegram import (
    telegram_answer_callback_query,
    telegram_edit_message_text,
    telegram_edit_message_reply_markup,
    telegram_get_me,
    telegram_get_updates,
    telegram_set_my_commands,
    telegram_send_message,
)


OFFSET_SETTING_KEY = "curator_telegram_onboarding_update_offset"
BOT_TOKEN_PATTERN = re.compile(r"^[0-9]{6,}:[A-Za-z0-9_-]{20,}$")
TELEGRAM_USER_COMMANDS = [
    {"command": "start", "description": "Start private onboarding"},
    {"command": "onboard", "description": "Start private onboarding"},
    {"command": "status", "description": "Show onboarding status"},
    {"command": "cancel", "description": "Cancel current onboarding"},
    {"command": "restart", "description": "Restart provider authorization"},
    {"command": "verify_notion", "description": "Resume Notion verification"},
    {"command": "setup_backup", "description": "Set up private backup"},
    {"command": "backup", "description": "Set up private backup"},
    {"command": "ssh_key", "description": "Install remote-Hermes SSH key"},
    {"command": "sshkey", "description": "Install remote-Hermes SSH key"},
]
TELEGRAM_OPERATOR_COMMANDS = [
    {"command": "approve", "description": "Approve onboarding/request/write"},
    {"command": "deny", "description": "Deny onboarding/request/write"},
    {"command": "upgrade", "description": "Queue ArcLink host upgrade"},
    {"command": "retry_contact", "description": "Retry Discord agent-bot handoff"},
]
TELEGRAM_USER_COMMAND_NAMES = {
    str(item.get("command") or "").strip().lower()
    for item in TELEGRAM_USER_COMMANDS
    if str(item.get("command") or "").strip()
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Telegram onboarding worker for Raven, Curator of the Console.")
    parser.add_argument("--once", action="store_true", help="Poll once, then exit.")
    parser.add_argument("--register-commands", action="store_true", help="Refresh Telegram bot command menus, then exit.")
    parser.add_argument("--poll-timeout", type=int, default=int(os.environ.get("ARCLINK_ONBOARDING_POLL_TIMEOUT_SECONDS", "20")))
    parser.add_argument("--idle-sleep", type=float, default=float(os.environ.get("ARCLINK_ONBOARDING_IDLE_SLEEP_SECONDS", "2")))
    return parser.parse_args()


def _telegram_command_token(raw: str) -> str:
    return str(raw or "").strip().split("@", 1)[0].lower()


def register_telegram_bot_commands(cfg: Config, bot_token: str) -> list[str]:
    errors: list[str] = []
    registrations = [
        (
            "default",
            TELEGRAM_USER_COMMANDS,
            {"type": "default"},
        ),
        (
            "private",
            TELEGRAM_USER_COMMANDS,
            {"type": "all_private_chats"},
        ),
    ]
    if cfg.operator_notify_platform == "telegram" and str(cfg.operator_notify_channel_id or "").strip():
        registrations.append(
            (
                "operator",
                [*TELEGRAM_USER_COMMANDS, *TELEGRAM_OPERATOR_COMMANDS],
                {
                    "type": "chat",
                    "chat_id": str(cfg.operator_notify_channel_id).strip(),
                },
            )
        )
    for label, commands, scope in registrations:
        try:
            telegram_set_my_commands(bot_token=bot_token, commands=commands, scope=scope)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}: {exc}")
    return errors


def send_text(
    bot_token: str,
    chat_id: str,
    text: str,
    *,
    reply_to_message_id: int | None = None,
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str = "",
) -> None:
    telegram_send_message(
        bot_token=bot_token,
        chat_id=chat_id,
        text=text,
        reply_to_message_id=reply_to_message_id,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )


def _format_actor_label(message_like: dict[str, Any]) -> str:
    sender = message_like.get("from") or {}
    username = str(sender.get("username") or "").strip()
    if username:
        return f"@{username}"
    first_name = str(sender.get("first_name") or "").strip()
    if first_name:
        return first_name
    return f"telegram:{sender.get('id') or 'unknown'}"


def notify_operator_worker_failure(
    bot_token: str,
    cfg: Config,
    *,
    update: dict[str, Any],
    failure_count: int,
    error: str,
    skipped: bool,
) -> None:
    operator_chat_id = str(cfg.operator_notify_channel_id or "")
    if cfg.operator_notify_platform != "telegram" or not operator_chat_id:
        return
    if failure_count > 1 and not skipped:
        return
    callback_query = update.get("callback_query") or {}
    message = update.get("message") or callback_query.get("message") or {}
    sender = callback_query.get("from") or message.get("from") or {}
    username = str(sender.get("username") or "").strip()
    sender_label = f"@{username}" if username else str(sender.get("id") or "unknown")
    status = "skipped" if skipped else "will retry"
    lines = [
        f"Curator onboarding worker {status} Telegram update {update.get('update_id')}.",
        f"Sender: {sender_label}",
        f"Failures: {failure_count}/{cfg.onboarding_update_failure_limit}",
        f"Error: {error}",
    ]
    try:
        send_text(bot_token, operator_chat_id, "\n".join(lines))
    except Exception:
        return


def _operator_sender_allowed(
    cfg: Config,
    *,
    chat_id: str,
    sender_id: str,
    chat_type: str,
) -> bool:
    if cfg.operator_notify_platform != "telegram" or not cfg.operator_notify_channel_id:
        return False
    if chat_id != str(cfg.operator_notify_channel_id):
        return False
    if cfg.operator_telegram_user_ids:
        return sender_id in cfg.operator_telegram_user_ids
    return chat_type == "private" and chat_id == sender_id


def operator_message_allowed(cfg: Config, message: dict[str, Any]) -> bool:
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    return _operator_sender_allowed(
        cfg,
        chat_id=str(chat.get("id") or ""),
        sender_id=str(sender.get("id") or ""),
        chat_type=str(chat.get("type") or ""),
    )


def _operator_command_requested(text: str) -> bool:
    parts = text.strip().split(maxsplit=1)
    command = _telegram_command_token(parts[0] if parts else "")
    return command in {"/approve", "/deny", "/upgrade", "/retry-contact", "/retry_contact"} or command.startswith("/retry")


def _operator_approval_code() -> str:
    return (
        config_env_value("ARCLINK_OPERATOR_TELEGRAM_APPROVAL_CODE", "").strip()
        or config_env_value("ARCLINK_OPERATOR_APPROVAL_CODE", "").strip()
    )


def _operator_approval_tail(*, command: str, text: str, bot_token: str, operator_chat_id: str) -> str | None:
    code = _operator_approval_code()
    if not code:
        parts = text.strip().split(maxsplit=2)
        return parts[2].strip() if len(parts) > 2 and command == "/deny" else ""
    parts = text.strip().split(maxsplit=2)
    tail = parts[2].strip() if len(parts) > 2 else ""
    code_parts = tail.split(maxsplit=1)
    if not code_parts or not hmac.compare_digest(code_parts[0], code):
        send_text(
            bot_token,
            operator_chat_id,
            "Approval code required. Use /approve <target> <operator-code> or /deny <target> <operator-code> optional reason.",
        )
        return None
    return code_parts[1].strip() if len(code_parts) > 1 and command == "/deny" else ""


def _operator_command_code_ok(*, command: str, text: str, bot_token: str, operator_chat_id: str) -> bool:
    code = _operator_approval_code()
    if not code:
        return True
    parts = text.strip().split()
    supplied = parts[-1] if len(parts) > 1 else ""
    if hmac.compare_digest(supplied, code):
        return True
    usage = "/upgrade <operator-code>" if command == "/upgrade" else f"{command} <target> <operator-code>"
    send_text(bot_token, operator_chat_id, f"Operator code required. Use {usage}.")
    return False


def _user_command_requested(text: str) -> bool:
    parts = text.strip().split(maxsplit=1)
    command = _telegram_command_token(parts[0] if parts else "").lstrip("/")
    if not command:
        return False
    normalized = command.replace("-", "_")
    return normalized in TELEGRAM_USER_COMMAND_NAMES


def _operator_private_chat_has_active_onboarding(cfg: Config, message: dict[str, Any]) -> bool:
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    if str(chat.get("type") or "") != "private":
        return False
    sender_id = str(sender.get("id") or "")
    if not sender_id:
        return False
    with connect_db(cfg) as conn:
        return find_active_onboarding_session(conn, platform="telegram", sender_id=sender_id) is not None


def _handle_operator_command(
    *,
    cfg: Config,
    bot_token: str,
    text: str,
    message: dict[str, Any],
) -> None:
    parts = text.strip().split(maxsplit=2)
    command = _telegram_command_token(parts[0] if parts else "")
    operator_chat_id = str((message.get("chat") or {}).get("id") or "")
    if command == "/upgrade":
        if not _operator_command_code_ok(command=command, text=text, bot_token=bot_token, operator_chat_id=operator_chat_id):
            return
        actor = _format_actor_label(message)
        try:
            with connect_db(cfg) as conn:
                action_row, created = request_operator_action(
                    conn,
                    action_kind="upgrade",
                    requested_by=actor,
                    request_source="telegram-command",
                    requested_target="",
                )
            status = str(action_row.get("status") or "pending")
            if created:
                send_text(
                    bot_token,
                    operator_chat_id,
                    "Queued ArcLink upgrade/repair. The root maintenance loop will pick it up within about a minute.",
                )
            elif status == "running":
                send_text(bot_token, operator_chat_id, "ArcLink upgrade is already running.")
            else:
                send_text(bot_token, operator_chat_id, "ArcLink upgrade is already queued.")
        except Exception as exc:  # noqa: BLE001
            send_text(bot_token, operator_chat_id, f"Could not queue ArcLink upgrade: {exc}")
        return

    if command in {"/retry-contact", "/retry_contact"}:
        retry_parts = text.strip().split(maxsplit=2)
        if len(retry_parts) < 2 or not retry_parts[1].strip():
            send_text(bot_token, operator_chat_id, "Use /retry_contact <unixusername|discordname>.")
            return
        if not _operator_command_code_ok(command="/retry_contact", text=text, bot_token=bot_token, operator_chat_id=operator_chat_id):
            return
        actor = _format_actor_label(message)
        try:
            with connect_db(cfg) as conn:
                result = retry_discord_contact(
                    conn,
                    cfg,
                    target=retry_parts[1].strip(),
                    actor=actor,
                    request_source="telegram-retry-contact",
                )
            send_text(bot_token, operator_chat_id, str(result.get("message") or "Queued contact retry."))
        except Exception as exc:  # noqa: BLE001
            send_text(bot_token, operator_chat_id, f"Could not retry contact: {exc}")
        return

    if command not in {"/approve", "/deny"} or len(parts) < 2:
        if command.startswith("/approve") or command.startswith("/deny") or command.startswith("/retry"):
            send_text(
                bot_token,
                operator_chat_id,
                "Use /upgrade, /approve onb_xxx, /deny onb_xxx optional reason, /approve req_xxx, /deny req_xxx, /approve ssotw_xxx, /deny ssotw_xxx optional reason, or /retry_contact <unixusername|discordname>.",
            )
        return
    target_id = parts[1].strip()
    operator_reason = _operator_approval_tail(command=command, text=text, bot_token=bot_token, operator_chat_id=operator_chat_id)
    if operator_reason is None:
        return
    actor = _format_actor_label(message)
    with connect_db(cfg) as conn:
        if target_id.startswith("onb_"):
            session = get_onboarding_session(conn, target_id)
            if session is None:
                send_text(bot_token, operator_chat_id, f"Unknown onboarding session: {target_id}")
                return
            if command == "/approve":
                updated = approve_onboarding_session(conn, session_id=target_id, actor=actor)
                send_text(
                    bot_token,
                    operator_chat_id,
                    f"Approved {target_id} for {updated['answers'].get('full_name') or updated.get('sender_display_name') or updated.get('sender_id')}.",
                )
                notify_session_state(cfg, updated)
                return
            updated = deny_onboarding_session(conn, session_id=target_id, actor=actor, reason=operator_reason)
            send_text(bot_token, operator_chat_id, f"Denied {target_id}.")
            notify_session_state(cfg, updated)
            return
        if target_id.startswith("req_"):
            if command == "/approve":
                approve_request(conn, request_id=target_id, surface="curator-channel", actor=actor, cfg=cfg)
                send_text(bot_token, operator_chat_id, f"Approved {target_id}.")
                return
            deny_request(conn, request_id=target_id, surface="curator-channel", actor=actor, cfg=cfg)
            send_text(bot_token, operator_chat_id, f"Denied {target_id}.")
            return
        if target_id.startswith("ssotw_"):
            if command == "/approve":
                approve_ssot_pending_write(
                    conn,
                    cfg,
                    pending_id=target_id,
                    surface="curator-channel",
                    actor=actor,
                )
                send_text(bot_token, operator_chat_id, f"Approved {target_id}.")
                return
            deny_ssot_pending_write(
                conn,
                cfg,
                pending_id=target_id,
                surface="curator-channel",
                actor=actor,
                reason=operator_reason,
            )
            send_text(bot_token, operator_chat_id, f"Denied {target_id}.")
            return
        send_text(bot_token, operator_chat_id, f"Unknown approval target: {target_id}")


def _clear_operator_callback_buttons(bot_token: str, callback_query: dict[str, Any]) -> None:
    message = callback_query.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id") or "")
    message_id = message.get("message_id")
    if not chat_id or not isinstance(message_id, int):
        return
    try:
        telegram_edit_message_reply_markup(
            bot_token=bot_token,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup={"inline_keyboard": []},
        )
    except Exception:
        return


def _replace_operator_callback_message(
    bot_token: str,
    callback_query: dict[str, Any],
    *,
    text: str,
) -> None:
    message = callback_query.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id") or "")
    message_id = message.get("message_id")
    if not chat_id or not isinstance(message_id, int):
        return
    try:
        telegram_edit_message_text(
            bot_token=bot_token,
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup={"inline_keyboard": []},
        )
    except Exception:
        _clear_operator_callback_buttons(bot_token, callback_query)


def _handle_user_completion_callback(
    *,
    cfg: Config,
    bot_token: str,
    callback_query: dict[str, Any],
) -> bool:
    callback_query_id = str(callback_query.get("id") or "")
    data = str(callback_query.get("data") or "").strip()
    message = callback_query.get("message") or {}
    chat = message.get("chat") or {}
    sender = callback_query.get("from") or {}
    chat_id = str(chat.get("id") or "")
    sender_id = str(sender.get("id") or "")
    message_id = message.get("message_id")
    if not callback_query_id or not data.startswith("arclink:onboarding-complete:ack:"):
        return False
    session_id = data.rsplit(":", 1)[-1].strip()
    if not session_id or not chat_id or not isinstance(message_id, int):
        telegram_answer_callback_query(
            bot_token=bot_token,
            callback_query_id=callback_query_id,
            text="That onboarding receipt is malformed.",
            show_alert=True,
        )
        return True
    with connect_db(cfg) as conn:
        session = get_onboarding_session(conn, session_id, redact_secrets=False)
        if session is None or str(session.get("state") or "") != "completed":
            telegram_answer_callback_query(
                bot_token=bot_token,
                callback_query_id=callback_query_id,
                text="That onboarding receipt is no longer active.",
                show_alert=True,
            )
            return True
        if sender_id != str(session.get("sender_id") or "") or chat_id != str(session.get("chat_id") or ""):
            telegram_answer_callback_query(
                bot_token=bot_token,
                callback_query_id=callback_query_id,
                text="Only the onboarding recipient can confirm this.",
                show_alert=True,
            )
            return True
        scrubbed_text = completion_scrubbed_text_for_session(conn, cfg, session)
        if not scrubbed_text:
            telegram_answer_callback_query(
                bot_token=bot_token,
                callback_query_id=callback_query_id,
                text="I couldn't reconstruct the onboarding details to scrub them.",
                show_alert=True,
            )
            return True
        try:
            telegram_edit_message_text(
                bot_token=bot_token,
                chat_id=chat_id,
                message_id=message_id,
                text=scrubbed_text,
                reply_markup={"inline_keyboard": []},
            )
        except Exception as exc:  # noqa: BLE001
            telegram_answer_callback_query(
                bot_token=bot_token,
                callback_query_id=callback_query_id,
                text=(str(exc).strip() or "Failed to scrub the password.")[:200],
                show_alert=True,
            )
            return True
        completion_delivery = dict((session.get("answers") or {}).get("completion_delivery") or {})
        completion_delivery.update(
            {
                "platform": "telegram",
                "chat_id": chat_id,
                "message_id": str(message_id),
                "scrubbed_text": scrubbed_text,
                "password_scrubbed": True,
            }
        )
        followup_text = completion_followup_text_for_session(conn, cfg, session)
        followup_parse_mode = completion_followup_telegram_parse_mode_for_session(conn, cfg, session)
        followup_reply_markup = completion_followup_telegram_markup(
            session_id,
            agent_backup_verified=bool((session.get("answers") or {}).get("agent_backup_verified")),
        )
        if followup_text and not bool(completion_delivery.get("followup_sent")):
            try:
                send_text(
                    bot_token=bot_token,
                    chat_id=chat_id,
                    text=followup_text,
                    reply_to_message_id=message_id,
                    reply_markup=followup_reply_markup,
                    parse_mode=followup_parse_mode,
                )
                completion_delivery["followup_sent"] = True
            except Exception:
                completion_delivery["followup_sent"] = False
        save_onboarding_session(
            conn,
            session_id=session_id,
            answers={
                "completion_delivery": completion_delivery,
                "completion_secret_acknowledged_at": utc_now_iso(),
            },
        )
    telegram_answer_callback_query(
        bot_token=bot_token,
        callback_query_id=callback_query_id,
        text="Password removed from the message.",
        show_alert=False,
    )
    return True


def _handle_user_backup_callback(
    *,
    cfg: Config,
    bot_token: str,
    callback_query: dict[str, Any],
) -> bool:
    callback_query_id = str(callback_query.get("id") or "")
    data = str(callback_query.get("data") or "").strip()
    message = callback_query.get("message") or {}
    chat = message.get("chat") or {}
    sender = callback_query.get("from") or {}
    chat_id = str(chat.get("id") or "")
    sender_id = str(sender.get("id") or "")
    if not callback_query_id or not data.startswith("arclink:onboarding-complete:setup-backup:"):
        return False
    session_id = data.rsplit(":", 1)[-1].strip()
    if not session_id or not chat_id:
        telegram_answer_callback_query(
            bot_token=bot_token,
            callback_query_id=callback_query_id,
            text="That backup setup receipt is malformed.",
            show_alert=True,
        )
        return True
    with connect_db(cfg) as conn:
        session = get_onboarding_session(conn, session_id, redact_secrets=False)
        if session is None:
            telegram_answer_callback_query(
                bot_token=bot_token,
                callback_query_id=callback_query_id,
                text="That onboarding receipt is no longer active.",
                show_alert=True,
            )
            return True
        if sender_id != str(session.get("sender_id") or "") or chat_id != str(session.get("chat_id") or ""):
            telegram_answer_callback_query(
                bot_token=bot_token,
                callback_query_id=callback_query_id,
                text="Only the onboarding recipient can set this up.",
                show_alert=True,
            )
            return True
        answers = session.get("answers", {}) if isinstance(session.get("answers"), dict) else {}
        if bool(answers.get("agent_backup_verified")):
            telegram_answer_callback_query(
                bot_token=bot_token,
                callback_query_id=callback_query_id,
                text="Private backup is already active for this lane.",
                show_alert=True,
            )
            return True
        if str(session.get("state") or "") != "completed":
            telegram_answer_callback_query(
                bot_token=bot_token,
                callback_query_id=callback_query_id,
                text="Backup setup is already open or this receipt is no longer active.",
                show_alert=True,
            )
            return True

    display_name = " ".join(
        item.strip()
        for item in (str(sender.get("first_name") or ""), str(sender.get("last_name") or ""))
        if item.strip()
    )
    replies = process_onboarding_message(
        cfg,
        IncomingMessage(
            platform="telegram",
            chat_id=chat_id,
            sender_id=sender_id,
            sender_username=str(sender.get("username") or ""),
            sender_display_name=display_name,
            text="/setup-backup",
        ),
        validate_bot_token=lambda token: BotIdentity(bot_id="unused"),
    )
    for reply in replies:
        send_text(
            bot_token,
            reply.chat_id,
            reply.text,
            reply_markup=reply.telegram_reply_markup,
            parse_mode=reply.telegram_parse_mode,
        )
    telegram_answer_callback_query(
        bot_token=bot_token,
        callback_query_id=callback_query_id,
        text="Backup setup opened.",
        show_alert=False,
    )
    return True


def _handle_user_notion_callback(
    *,
    cfg: Config,
    bot_token: str,
    callback_query: dict[str, Any],
) -> bool:
    callback_query_id = str(callback_query.get("id") or "")
    data = str(callback_query.get("data") or "").strip()
    parsed = parse_notion_setup_callback_data(data)
    if not callback_query_id or parsed is None:
        return False
    action, session_id = parsed
    message = callback_query.get("message") or {}
    chat = message.get("chat") or {}
    sender = callback_query.get("from") or {}
    chat_id = str(chat.get("id") or "")
    sender_id = str(sender.get("id") or "")
    if not chat_id or not session_id:
        telegram_answer_callback_query(
            bot_token=bot_token,
            callback_query_id=callback_query_id,
            text="That Notion setup button is malformed.",
            show_alert=True,
        )
        return True
    with connect_db(cfg) as conn:
        session = get_onboarding_session(conn, session_id, redact_secrets=False)
        if session is None:
            telegram_answer_callback_query(
                bot_token=bot_token,
                callback_query_id=callback_query_id,
                text="That Notion setup session is no longer active.",
                show_alert=True,
            )
            return True
        if sender_id != str(session.get("sender_id") or "") or chat_id != str(session.get("chat_id") or ""):
            telegram_answer_callback_query(
                bot_token=bot_token,
                callback_query_id=callback_query_id,
                text="Only the onboarding recipient can use that Notion setup button.",
                show_alert=True,
            )
            return True

    telegram_answer_callback_query(
        bot_token=bot_token,
        callback_query_id=callback_query_id,
        text="Notion choice received.",
        show_alert=False,
    )
    display_name = " ".join(
        item.strip()
        for item in (str(sender.get("first_name") or ""), str(sender.get("last_name") or ""))
        if item.strip()
    )
    text = {"ready": "ready", "skip": "skip", "verify": "/verify-notion"}.get(action, "")
    replies = process_onboarding_message(
        cfg,
        IncomingMessage(
            platform="telegram",
            chat_id=chat_id,
            sender_id=sender_id,
            sender_username=str(sender.get("username") or ""),
            sender_display_name=display_name,
            text=text,
        ),
        validate_bot_token=lambda token: BotIdentity(bot_id="unused"),
    )
    for reply in replies:
        send_text(
            bot_token,
            reply.chat_id,
            reply.text,
            reply_markup=reply.telegram_reply_markup,
            parse_mode=reply.telegram_parse_mode,
        )
    return True


def _handle_operator_callback(
    *,
    cfg: Config,
    bot_token: str,
    callback_query: dict[str, Any],
) -> None:
    callback_query_id = str(callback_query.get("id") or "")
    data = str(callback_query.get("data") or "").strip()
    message = callback_query.get("message") or {}
    chat = message.get("chat") or {}
    sender = callback_query.get("from") or {}
    chat_id = str(chat.get("id") or "")
    sender_id = str(sender.get("id") or "")
    chat_type = str(chat.get("type") or "")
    if not callback_query_id or not data.startswith("arclink:"):
        return
    if not _operator_sender_allowed(
        cfg,
        chat_id=chat_id,
        sender_id=sender_id,
        chat_type=chat_type,
    ):
        telegram_answer_callback_query(
            bot_token=bot_token,
            callback_query_id=callback_query_id,
            text="Operator approval is restricted in this chat.",
            show_alert=True,
        )
        return
    try:
        _, scope, action, target_id = data.split(":", 3)
    except ValueError:
        telegram_answer_callback_query(
            bot_token=bot_token,
            callback_query_id=callback_query_id,
            text="Malformed approval action.",
            show_alert=True,
        )
        return
    if _operator_approval_code() and action in {"approve", "deny", "install"}:
        telegram_answer_callback_query(
            bot_token=bot_token,
            callback_query_id=callback_query_id,
            text="Use the typed operator command with the approval code for this action.",
            show_alert=True,
        )
        return
    actor = _format_actor_label({"from": sender})
    try:
        visible_reply: str | None = None
        replacement_text: str | None = None
        message_text = str(message.get("text") or "").strip()
        with connect_db(cfg) as conn:
            if scope == "onboarding" and target_id.startswith("onb_"):
                if action == "approve":
                    updated = approve_onboarding_session(conn, session_id=target_id, actor=actor)
                    result_text = (
                        f"Approved {target_id} for "
                        f"{updated['answers'].get('full_name') or updated.get('sender_display_name') or updated.get('sender_id')}."
                    )
                elif action == "deny":
                    updated = deny_onboarding_session(conn, session_id=target_id, actor=actor, reason="")
                    result_text = f"Denied {target_id}."
                else:
                    raise ValueError(f"unknown onboarding action: {action}")
                notify_session_state(cfg, updated)
                if message_text:
                    replacement_text = (message_text + f"\n\n{result_text} ({actor})").strip()
                else:
                    visible_reply = result_text
            elif scope == "request" and target_id.startswith("req_"):
                row = conn.execute(
                    "SELECT status FROM bootstrap_requests WHERE request_id = ?",
                    (target_id,),
                ).fetchone()
                if row is None:
                    raise ValueError(f"unknown bootstrap request: {target_id}")
                status = str(row["status"] or "").strip()
                if status != "pending":
                    result_text = f"Enrollment request {target_id} is already {status or 'not pending'}."
                elif action == "approve":
                    approve_request(conn, request_id=target_id, surface="curator-channel", actor=actor, cfg=cfg)
                    result_text = f"Approved {target_id}."
                elif action == "deny":
                    deny_request(conn, request_id=target_id, surface="curator-channel", actor=actor, cfg=cfg)
                    result_text = f"Denied {target_id}."
                else:
                    raise ValueError(f"unknown request action: {action}")
                if message_text:
                    replacement_text = (message_text + f"\n\n{result_text} ({actor})").strip()
                else:
                    visible_reply = result_text
            elif scope == "ssot" and target_id.startswith("ssotw_"):
                if action == "approve":
                    approve_ssot_pending_write(
                        conn,
                        cfg,
                        pending_id=target_id,
                        surface="curator-channel",
                        actor=actor,
                    )
                    result_text = f"Approved {target_id}."
                elif action == "deny":
                    deny_ssot_pending_write(
                        conn,
                        cfg,
                        pending_id=target_id,
                        surface="curator-channel",
                        actor=actor,
                        reason="",
                    )
                    result_text = f"Denied {target_id}."
                else:
                    raise ValueError(f"unknown ssot action: {action}")
                replacement_text = (message_text + f"\n\n{result_text} ({actor})").strip() if message_text else result_text
            elif scope == "upgrade":
                if action == "dismiss":
                    upsert_setting(conn, "arclink_upgrade_last_dismissed_sha", target_id)
                    result_text = f"Dismissed ArcLink update notice for {target_id[:12]}."
                    replacement_text = (message_text + f"\n\nDismissed by {actor}.").strip()
                elif action == "install":
                    action_row, created = request_operator_action(
                        conn,
                        action_kind="upgrade",
                        requested_by=actor,
                        request_source="telegram-button",
                        requested_target=target_id,
                    )
                    status = str(action_row.get("status") or "pending")
                    if created:
                        result_text = "Queued ArcLink upgrade. The root maintenance loop will pick it up within about a minute."
                    elif status == "running":
                        result_text = "ArcLink upgrade is already running."
                    else:
                        result_text = "ArcLink upgrade is already queued."
                    replacement_text = (message_text + f"\n\n{result_text} ({actor})").strip()
            elif scope == "pin-upgrade":
                payload = get_pin_upgrade_action_payload(conn, target_id)
                if payload is None:
                    raise ValueError(f"unknown pinned-component upgrade action: {target_id}")
                components = ", ".join(item["component"] for item in payload["items"])
                if action == "dismiss":
                    dismissed = dismiss_pin_upgrade_action(conn, target_id)
                    silenced = ", ".join(dismissed.get("silenced") or dismissed.get("components") or [])
                    result_text = f"Dismissed pinned-component upgrade notice for {silenced or components}."
                elif action == "install":
                    action_row, created = request_operator_action(
                        conn,
                        action_kind="pin-upgrade",
                        requested_by=actor,
                        request_source="telegram-button",
                        requested_target=target_id,
                        dedupe_by_target=True,
                    )
                    status = str(action_row.get("status") or "pending")
                    if created:
                        result_text = "Queued pinned-component upgrade. The root maintenance loop will pick it up within about a minute."
                    elif status == "running":
                        result_text = "Pinned-component upgrade is already running."
                    else:
                        result_text = "Pinned-component upgrade is already queued."
                else:
                    raise ValueError(f"unknown pinned-component upgrade action: {action}")
                replacement_text = (message_text + f"\n\n{result_text} ({actor})").strip() if message_text else result_text
            else:
                raise ValueError(f"unknown approval target: {target_id}")
        if replacement_text:
            _replace_operator_callback_message(bot_token, callback_query, text=replacement_text)
        else:
            _clear_operator_callback_buttons(bot_token, callback_query)
        telegram_answer_callback_query(
            bot_token=bot_token,
            callback_query_id=callback_query_id,
            text=result_text,
            show_alert=False,
        )
        if visible_reply and chat_id:
            send_text(bot_token, chat_id, visible_reply)
    except Exception as exc:  # noqa: BLE001
        compact_error = (str(exc).strip() or exc.__class__.__name__).replace("\n", " ")[:200]
        telegram_answer_callback_query(
            bot_token=bot_token,
            callback_query_id=callback_query_id,
            text=compact_error,
            show_alert=True,
        )


def _telegram_validator(curator_bot_id: str):
    def _validate(raw_token: str) -> BotIdentity:
        normalized = raw_token.strip()
        if not BOT_TOKEN_PATTERN.fullmatch(normalized):
            raise RuntimeError("That doesn’t look like a Telegram bot token. It should look like `123456:ABC...`.")
        try:
            bot_profile = telegram_get_me(bot_token=normalized)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Telegram rejected that token: {exc}") from exc
        if str(bot_profile.get("id") or "") == curator_bot_id:
            raise RuntimeError("That token is for Curator’s bot. Create a new bot in BotFather and send me that token instead.")
        return BotIdentity(
            bot_id=str(bot_profile.get("id") or ""),
            username=str(bot_profile.get("username") or ""),
            display_name=str(bot_profile.get("first_name") or ""),
        )

    return _validate


def _handle_user_message(
    *,
    cfg: Config,
    bot_token: str,
    curator_bot_id: str,
    text: str,
    message: dict[str, Any],
) -> None:
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    if chat.get("type") != "private":
        return
    display_name = " ".join(
        item.strip()
        for item in (str(sender.get("first_name") or ""), str(sender.get("last_name") or ""))
        if item.strip()
    )
    replies = process_onboarding_message(
        cfg,
        IncomingMessage(
            platform="telegram",
            chat_id=str(chat.get("id") or ""),
            sender_id=str(sender.get("id") or ""),
            sender_username=str(sender.get("username") or ""),
            sender_display_name=display_name,
            text=text,
            reply_to_message_id=message.get("message_id"),
        ),
        validate_bot_token=_telegram_validator(curator_bot_id),
    )
    for reply in replies:
        send_text(
            bot_token,
            reply.chat_id,
            reply.text,
            reply_to_message_id=reply.reply_to_message_id,
            reply_markup=reply.telegram_reply_markup,
            parse_mode=reply.telegram_parse_mode,
        )


def process_update(*, cfg: Config, bot_token: str, curator_bot_id: str, update: dict[str, Any]) -> None:
    callback_query = update.get("callback_query")
    if isinstance(callback_query, dict):
        if _handle_user_completion_callback(cfg=cfg, bot_token=bot_token, callback_query=callback_query):
            return
        if _handle_user_backup_callback(cfg=cfg, bot_token=bot_token, callback_query=callback_query):
            return
        if _handle_user_notion_callback(cfg=cfg, bot_token=bot_token, callback_query=callback_query):
            return
        _handle_operator_callback(cfg=cfg, bot_token=bot_token, callback_query=callback_query)
        return
    message = update.get("message")
    if not isinstance(message, dict):
        return
    text = str(message.get("text") or "").strip()
    if not text:
        return
    if operator_message_allowed(cfg, message):
        if _operator_command_requested(text):
            _handle_operator_command(cfg=cfg, bot_token=bot_token, text=text, message=message)
            return
        if not _user_command_requested(text) and not _operator_private_chat_has_active_onboarding(cfg, message):
            return
        # A private operator DM can also be that operator's personal onboarding
        # lane. Let user onboarding commands and active-session replies through
        # while keeping operator control commands above.
        _handle_user_message(
            cfg=cfg,
            bot_token=bot_token,
            curator_bot_id=curator_bot_id,
            text=text,
            message=message,
        )
        return
    _handle_user_message(
        cfg=cfg,
        bot_token=bot_token,
        curator_bot_id=curator_bot_id,
        text=text,
        message=message,
    )


def run_once(cfg: Config, bot_token: str, curator_bot_id: str, *, poll_timeout: int) -> int:
    with connect_db(cfg) as conn:
        offset = get_setting(conn, OFFSET_SETTING_KEY, "")
        next_offset = int(offset) if offset.strip().isdigit() else None
    updates = telegram_get_updates(bot_token=bot_token, offset=next_offset, timeout=poll_timeout)
    processed = 0
    for update in updates:
        update_id = int(update.get("update_id") or 0)
        update_key = str(update_id) if update_id else ""
        try:
            process_update(cfg=cfg, bot_token=bot_token, curator_bot_id=curator_bot_id, update=update)
        except Exception as exc:  # noqa: BLE001
            compact_error = (str(exc).strip() or exc.__class__.__name__).replace("\n", " ")[:500]
            sys.stderr.write(f"Curator onboarding failed on update {update_key or '<unknown>'}: {compact_error}\n")
            sys.stderr.flush()
            if not update_key:
                break
            with connect_db(cfg) as conn:
                failure = record_onboarding_update_failure(conn, update_id=update_key, error=compact_error)
                failure_count = int(failure.get("failure_count") or 1)
                skipped = failure_count >= cfg.onboarding_update_failure_limit
                if skipped:
                    mark_onboarding_update_skipped(conn, update_key)
                    upsert_setting(conn, OFFSET_SETTING_KEY, str(update_id + 1))
                else:
                    notify_operator_worker_failure(
                        bot_token,
                        cfg,
                        update=update,
                        failure_count=failure_count,
                        error=compact_error,
                        skipped=False,
                    )
                    break
            if skipped:
                notify_operator_worker_failure(
                    bot_token,
                    cfg,
                    update=update,
                    failure_count=failure_count,
                    error=compact_error,
                    skipped=True,
                )
                processed += 1
                continue
            break
        if update_key:
            with connect_db(cfg) as conn:
                clear_onboarding_update_failure(conn, update_key)
                upsert_setting(conn, OFFSET_SETTING_KEY, str(update_id + 1))
        processed += 1
    return processed


def main() -> None:
    args = parse_args()
    cfg = Config.from_env()
    if not cfg.curator_telegram_onboarding_enabled:
        return
    bot_token = resolve_curator_telegram_bot_token(cfg)
    if not bot_token:
        raise SystemExit("Curator Telegram onboarding requires TELEGRAM_BOT_TOKEN.")
    try:
        curator_profile = telegram_get_me(bot_token=bot_token)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Failed to query Telegram getMe: {exc}") from exc
    curator_bot_id = str(curator_profile.get("id") or "")
    if not curator_bot_id:
        raise SystemExit("Telegram getMe did not return a bot id.")
    command_errors = register_telegram_bot_commands(cfg, bot_token)
    if command_errors:
        message = "Curator Telegram command registration failed: " + "; ".join(command_errors)
        if args.register_commands:
            raise SystemExit(message)
        sys.stderr.write(message + "\n")
        sys.stderr.flush()
    if args.register_commands:
        return

    while True:
        try:
            processed = run_once(cfg, bot_token, curator_bot_id, poll_timeout=args.poll_timeout)
        except Exception as exc:  # noqa: BLE001
            if args.once:
                raise
            sys.stderr.write(f"Curator onboarding loop error: {exc}\n")
            sys.stderr.flush()
            processed = 0
        if args.once:
            break
        if processed == 0:
            time.sleep(args.idle_sleep)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
