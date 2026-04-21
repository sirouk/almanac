#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from typing import Any

from almanac_control import (
    Config,
    approve_request,
    approve_onboarding_session,
    clear_onboarding_update_failure,
    connect_db,
    deny_request,
    deny_onboarding_session,
    get_onboarding_session,
    get_setting,
    mark_onboarding_update_skipped,
    record_onboarding_update_failure,
    save_onboarding_session,
    utc_now_iso,
    upsert_setting,
)
from almanac_onboarding_completion import completion_followup_text_for_session, completion_scrubbed_text_for_session
from almanac_onboarding_flow import (
    BotIdentity,
    IncomingMessage,
    notify_session_state,
    process_onboarding_message,
    resolve_curator_telegram_bot_token,
)
from almanac_telegram import (
    telegram_answer_callback_query,
    telegram_edit_message_text,
    telegram_edit_message_reply_markup,
    telegram_get_me,
    telegram_get_updates,
    telegram_send_message,
)


OFFSET_SETTING_KEY = "curator_telegram_onboarding_update_offset"
BOT_TOKEN_PATTERN = re.compile(r"^[0-9]{6,}:[A-Za-z0-9_-]{20,}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Telegram onboarding worker for Almanac Curator.")
    parser.add_argument("--once", action="store_true", help="Poll once, then exit.")
    parser.add_argument("--poll-timeout", type=int, default=int(os.environ.get("ALMANAC_ONBOARDING_POLL_TIMEOUT_SECONDS", "20")))
    parser.add_argument("--idle-sleep", type=float, default=float(os.environ.get("ALMANAC_ONBOARDING_IDLE_SLEEP_SECONDS", "2")))
    return parser.parse_args()


def send_text(
    bot_token: str,
    chat_id: str,
    text: str,
    *,
    reply_to_message_id: int | None = None,
    reply_markup: dict[str, Any] | None = None,
) -> None:
    telegram_send_message(
        bot_token=bot_token,
        chat_id=chat_id,
        text=text,
        reply_to_message_id=reply_to_message_id,
        reply_markup=reply_markup,
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


def _handle_operator_command(
    *,
    cfg: Config,
    bot_token: str,
    text: str,
    message: dict[str, Any],
) -> None:
    parts = text.strip().split(maxsplit=2)
    command = parts[0].lower()
    operator_chat_id = str((message.get("chat") or {}).get("id") or "")
    if command not in {"/approve", "/deny"} or len(parts) < 2:
        if command.startswith("/approve") or command.startswith("/deny"):
            send_text(
                bot_token,
                operator_chat_id,
                "Use /approve onb_xxx, /deny onb_xxx optional reason, /approve req_xxx, or /deny req_xxx.",
            )
        return
    target_id = parts[1].strip()
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
            reason = parts[2].strip() if len(parts) > 2 else ""
            updated = deny_onboarding_session(conn, session_id=target_id, actor=actor, reason=reason)
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
    if not callback_query_id or not data.startswith("almanac:onboarding-complete:ack:"):
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
        if followup_text and not bool(completion_delivery.get("followup_sent")):
            try:
                send_text(
                    bot_token=bot_token,
                    chat_id=chat_id,
                    text=followup_text,
                    reply_to_message_id=message_id,
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
    if not callback_query_id or not data.startswith("almanac:"):
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
    actor = _format_actor_label({"from": sender})
    try:
        visible_reply: str | None = None
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
                visible_reply = result_text
            elif scope == "request" and target_id.startswith("req_"):
                if action == "approve":
                    approve_request(conn, request_id=target_id, surface="curator-channel", actor=actor, cfg=cfg)
                    result_text = f"Approved {target_id}."
                elif action == "deny":
                    deny_request(conn, request_id=target_id, surface="curator-channel", actor=actor, cfg=cfg)
                    result_text = f"Denied {target_id}."
                else:
                    raise ValueError(f"unknown request action: {action}")
            else:
                raise ValueError(f"unknown approval target: {target_id}")
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
        )


def process_update(*, cfg: Config, bot_token: str, curator_bot_id: str, update: dict[str, Any]) -> None:
    callback_query = update.get("callback_query")
    if isinstance(callback_query, dict):
        if _handle_user_completion_callback(cfg=cfg, bot_token=bot_token, callback_query=callback_query):
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
        _handle_operator_command(cfg=cfg, bot_token=bot_token, text=text, message=message)
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
