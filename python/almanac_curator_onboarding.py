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
    approve_onboarding_session,
    clear_onboarding_update_failure,
    connect_db,
    deny_onboarding_session,
    get_onboarding_session,
    get_setting,
    mark_onboarding_update_skipped,
    record_onboarding_update_failure,
    upsert_setting,
)
from almanac_onboarding_flow import (
    BotIdentity,
    IncomingMessage,
    notify_session_state,
    process_onboarding_message,
    resolve_curator_telegram_bot_token,
)
from almanac_telegram import telegram_get_me, telegram_get_updates, telegram_send_message


OFFSET_SETTING_KEY = "curator_telegram_onboarding_update_offset"
BOT_TOKEN_PATTERN = re.compile(r"^[0-9]{6,}:[A-Za-z0-9_-]{20,}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Telegram onboarding worker for Almanac Curator.")
    parser.add_argument("--once", action="store_true", help="Poll once, then exit.")
    parser.add_argument("--poll-timeout", type=int, default=int(os.environ.get("ALMANAC_ONBOARDING_POLL_TIMEOUT_SECONDS", "20")))
    parser.add_argument("--idle-sleep", type=float, default=float(os.environ.get("ALMANAC_ONBOARDING_IDLE_SLEEP_SECONDS", "2")))
    return parser.parse_args()


def send_text(bot_token: str, chat_id: str, text: str, *, reply_to_message_id: int | None = None) -> None:
    telegram_send_message(
        bot_token=bot_token,
        chat_id=chat_id,
        text=text,
        reply_to_message_id=reply_to_message_id,
    )


def _format_actor_label(message: dict[str, Any]) -> str:
    sender = message.get("from") or {}
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
    message = update.get("message") or {}
    sender = message.get("from") or {}
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


def operator_message_allowed(cfg: Config, message: dict[str, Any]) -> bool:
    if cfg.operator_notify_platform != "telegram" or not cfg.operator_notify_channel_id:
        return False
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    chat_id = str(chat.get("id") or "")
    sender_id = str(sender.get("id") or "")
    if chat_id != str(cfg.operator_notify_channel_id):
        return False
    if cfg.operator_telegram_user_ids:
        return sender_id in cfg.operator_telegram_user_ids
    return chat.get("type") == "private" and chat_id == sender_id


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
            send_text(bot_token, operator_chat_id, "Use /approve onb_xxx or /deny onb_xxx optional reason.")
        return
    session_id = parts[1].strip()
    actor = _format_actor_label(message)
    with connect_db(cfg) as conn:
        session = get_onboarding_session(conn, session_id)
        if session is None:
            send_text(bot_token, operator_chat_id, f"Unknown onboarding session: {session_id}")
            return
        if command == "/approve":
            updated = approve_onboarding_session(conn, session_id=session_id, actor=actor)
            send_text(
                bot_token,
                operator_chat_id,
                f"Approved {session_id} for {updated['answers'].get('full_name') or updated.get('sender_display_name') or updated.get('sender_id')}.",
            )
            notify_session_state(cfg, updated)
            return
        reason = parts[2].strip() if len(parts) > 2 else ""
        updated = deny_onboarding_session(conn, session_id=session_id, actor=actor, reason=reason)
        send_text(bot_token, operator_chat_id, f"Denied {session_id}.")
        notify_session_state(cfg, updated)


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
        )


def process_update(*, cfg: Config, bot_token: str, curator_bot_id: str, update: dict[str, Any]) -> None:
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
