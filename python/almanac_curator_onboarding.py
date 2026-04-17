#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import pwd
import re
import sys
import time
from pathlib import Path
from typing import Any

from almanac_control import (
    Config,
    RateLimitError,
    approve_onboarding_session,
    approve_request,
    clear_onboarding_update_failure,
    config_env_value,
    connect_db,
    deny_onboarding_session,
    find_active_onboarding_session,
    get_onboarding_session,
    get_setting,
    mark_onboarding_update_skipped,
    record_onboarding_update_failure,
    request_bootstrap,
    save_onboarding_session,
    start_onboarding_session,
    upsert_setting,
    write_onboarding_bot_token_secret,
)
from almanac_telegram import telegram_get_me, telegram_get_updates, telegram_send_message


OFFSET_SETTING_KEY = "curator_telegram_onboarding_update_offset"
ONBOARDING_PLATFORM = "telegram"
BOT_TOKEN_PATTERN = re.compile(r"^[0-9]{6,}:[A-Za-z0-9_-]{20,}$")
UNIX_USER_PATTERN = re.compile(r"^[a-z_][a-z0-9_-]{0,30}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Telegram-first onboarding worker for Almanac Curator.")
    parser.add_argument("--once", action="store_true", help="Poll once, then exit.")
    parser.add_argument("--poll-timeout", type=int, default=int(os.environ.get("ALMANAC_ONBOARDING_POLL_TIMEOUT_SECONDS", "20")))
    parser.add_argument("--idle-sleep", type=float, default=float(os.environ.get("ALMANAC_ONBOARDING_IDLE_SLEEP_SECONDS", "2")))
    return parser.parse_args()


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


def resolve_bot_token(cfg: Config) -> str:
    token = config_env_value("TELEGRAM_BOT_TOKEN", "").strip()
    if token:
        return token
    return read_env_file_value(cfg.curator_hermes_home / ".env", "TELEGRAM_BOT_TOKEN").strip()


def format_user_label(username: str, display_name: str, sender_id: str) -> str:
    if username:
        return f"@{username}"
    if display_name:
        return display_name
    return f"telegram:{sender_id}"


def desired_unix_user_available(unix_user: str) -> tuple[bool, str]:
    candidate = unix_user.strip().lower()
    if not UNIX_USER_PATTERN.fullmatch(candidate):
        return False, "Use 1-31 chars: lowercase letters, digits, `_`, or `-`, starting with a letter or `_`."
    try:
        pwd.getpwnam(candidate)
        return False, f"`{candidate}` already exists on the host. Pick another Unix username."
    except KeyError:
        return True, ""


def session_prompt(session: dict[str, Any]) -> str:
    state = str(session.get("state") or "")
    answers = session.get("answers", {})
    preferred_bot_name = str(answers.get("preferred_bot_name") or "your bot")
    if state == "awaiting-name":
        return "Hi. I’m Curator. What should I call you?"
    if state == "awaiting-unix-user":
        return "What Unix username do you want on this host?"
    if state == "awaiting-purpose":
        return "What do you want this agent to help you do?"
    if state == "awaiting-bot-name":
        return "What name do you want for your own bot? A short plain-English name is enough."
    if state == "awaiting-operator-approval":
        return "Thanks. I’ve asked the operator for approval. I’ll continue here once I hear back."
    if state == "awaiting-bot-token":
        return (
            "You’re approved. Create your bot with BotFather, give it the name you want, "
            f"and send me the API token for {preferred_bot_name}. I’ll wire it to your agent and then step out."
        )
    if state == "provision-pending":
        return "I’m provisioning your agent and wiring your bot now. This usually lands within a minute."
    if state == "denied":
        reason = str(session.get("denial_reason") or "").strip()
        if reason:
            return f"The operator declined this onboarding request: {reason}"
        return "The operator declined this onboarding request."
    if state == "completed":
        bot_username = str(session.get("telegram_bot_username") or "").strip()
        if bot_username:
            return f"Your agent is live at @{bot_username}. Talk to it there from now on."
        return "Your agent is live. Talk to your own bot from now on."
    return "Send /start when you want to begin onboarding."


def send_text(bot_token: str, chat_id: str, text: str, *, reply_to_message_id: int | None = None) -> None:
    telegram_send_message(
        bot_token=bot_token,
        chat_id=chat_id,
        text=text,
        reply_to_message_id=reply_to_message_id,
    )


def prompt_session(bot_token: str, session: dict[str, Any], *, reply_to_message_id: int | None = None) -> None:
    send_text(
        bot_token,
        str(session["chat_id"]),
        session_prompt(session),
        reply_to_message_id=reply_to_message_id,
    )


def _operator_chat_id(cfg: Config) -> str:
    if cfg.operator_notify_platform != "telegram":
        return ""
    return str(cfg.operator_notify_channel_id or "")


def notify_operator(bot_token: str, cfg: Config, session: dict[str, Any]) -> None:
    operator_chat_id = _operator_chat_id(cfg)
    if not operator_chat_id:
        return
    answers = session.get("answers", {})
    requester = format_user_label(
        str(session.get("sender_username") or ""),
        str(session.get("sender_display_name") or answers.get("full_name") or ""),
        str(session.get("sender_id") or ""),
    )
    lines = [
        f"Onboarding request {session['session_id']}",
        f"Requester: {requester}",
        f"Name: {answers.get('full_name') or '(missing)'}",
        f"Unix user: {answers.get('unix_user') or '(missing)'}",
        f"Purpose: {answers.get('purpose') or '(missing)'}",
        f"Preferred bot name: {answers.get('preferred_bot_name') or '(missing)'}",
        f"Approve: /approve {session['session_id']}",
        f"Deny: /deny {session['session_id']} optional reason",
    ]
    send_text(bot_token, operator_chat_id, "\n".join(lines))


def notify_operator_worker_failure(
    bot_token: str,
    cfg: Config,
    *,
    update: dict[str, Any],
    failure_count: int,
    error: str,
    skipped: bool,
) -> None:
    operator_chat_id = _operator_chat_id(cfg)
    if not operator_chat_id:
        return
    if failure_count > 1 and not skipped:
        return
    message = update.get("message") or {}
    sender = message.get("from") or {}
    sender_label = format_user_label(
        str(sender.get("username") or ""),
        " ".join(
            item.strip()
            for item in (str(sender.get("first_name") or ""), str(sender.get("last_name") or ""))
            if item.strip()
        ),
        str(sender.get("id") or ""),
    )
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
    if command not in {"/approve", "/deny"} or len(parts) < 2:
        if command.startswith("/approve") or command.startswith("/deny"):
            send_text(bot_token, str((message.get("chat") or {}).get("id") or ""), "Use /approve onb_xxx or /deny onb_xxx optional reason.")
        return
    session_id = parts[1].strip()
    actor = format_user_label(
        str((message.get("from") or {}).get("username") or ""),
        str((message.get("from") or {}).get("first_name") or ""),
        str((message.get("from") or {}).get("id") or ""),
    )
    with connect_db(cfg) as conn:
        session = get_onboarding_session(conn, session_id)
        if session is None:
            send_text(bot_token, str((message.get("chat") or {}).get("id") or ""), f"Unknown onboarding session: {session_id}")
            return
        if command == "/approve":
            updated = approve_onboarding_session(conn, session_id=session_id, actor=actor)
            send_text(
                bot_token,
                str((message.get("chat") or {}).get("id") or ""),
                f"Approved {session_id} for {updated['answers'].get('full_name') or updated.get('sender_display_name') or updated.get('sender_id')}.",
            )
            prompt_session(bot_token, updated)
            return
        reason = parts[2].strip() if len(parts) > 2 else ""
        updated = deny_onboarding_session(conn, session_id=session_id, actor=actor, reason=reason)
        send_text(
            bot_token,
            str((message.get("chat") or {}).get("id") or ""),
            f"Denied {session_id}.",
        )
        prompt_session(bot_token, updated)


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
    chat_id = str(chat.get("id") or "")
    sender_id = str(sender.get("id") or "")
    sender_username = str(sender.get("username") or "")
    display_name = " ".join(
        item.strip()
        for item in (str(sender.get("first_name") or ""), str(sender.get("last_name") or ""))
        if item.strip()
    )

    with connect_db(cfg) as conn:
        if text.strip().lower() == "/start":
            try:
                session = start_onboarding_session(
                    conn,
                    cfg,
                    platform=ONBOARDING_PLATFORM,
                    chat_id=chat_id,
                    sender_id=sender_id,
                    sender_username=sender_username,
                    sender_display_name=display_name,
                )
            except RateLimitError as exc:
                send_text(bot_token, chat_id, f"Slow down a bit. Try again in about {exc.retry_after_seconds}s.")
                return
            prompt_session(bot_token, session, reply_to_message_id=message.get("message_id"))
            return

        session = find_active_onboarding_session(conn, platform=ONBOARDING_PLATFORM, sender_id=sender_id)
        if session is None:
            send_text(bot_token, chat_id, "Send /start when you want Curator to open an onboarding session.")
            return

        normalized = text.strip()
        state = str(session.get("state") or "")
        if normalized.lower() == "/status":
            prompt_session(bot_token, session)
            return
        if normalized.lower() == "/cancel":
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="cancelled",
                completed_at=now_iso,
            )
            send_text(bot_token, chat_id, f"Cancelled {updated['session_id']}. Send /start when you want to try again.")
            return

        if state == "awaiting-name":
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-unix-user",
                answers={"full_name": normalized},
                chat_id=chat_id,
                sender_username=sender_username,
                sender_display_name=display_name or normalized,
            )
            prompt_session(bot_token, updated)
            return

        if state == "awaiting-unix-user":
            candidate = normalized.lower()
            ok, reason = desired_unix_user_available(candidate)
            if not ok:
                send_text(bot_token, chat_id, reason)
                return
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-purpose",
                answers={"unix_user": candidate},
                chat_id=chat_id,
                sender_username=sender_username,
                sender_display_name=display_name,
            )
            prompt_session(bot_token, updated)
            return

        if state == "awaiting-purpose":
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-bot-name",
                answers={"purpose": normalized},
            )
            prompt_session(bot_token, updated)
            return

        if state == "awaiting-bot-name":
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-operator-approval",
                answers={"preferred_bot_name": normalized},
            )
            if not session.get("operator_notified_at"):
                notify_operator(bot_token, cfg, updated)
                updated = save_onboarding_session(
                    conn,
                    session_id=str(session["session_id"]),
                    operator_notified_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                )
            prompt_session(bot_token, updated)
            return

        if state == "awaiting-operator-approval":
            prompt_session(bot_token, session)
            return

        if state == "awaiting-bot-token":
            if not BOT_TOKEN_PATTERN.fullmatch(normalized):
                send_text(bot_token, chat_id, "That doesn’t look like a Telegram bot token. It should look like `123456:ABC...`.")
                return
            try:
                bot_profile = telegram_get_me(bot_token=normalized)
            except Exception as exc:  # noqa: BLE001
                send_text(bot_token, chat_id, f"Telegram rejected that token: {exc}")
                return
            if str(bot_profile.get("id") or "") == curator_bot_id:
                send_text(bot_token, chat_id, "That token is for Curator’s bot. Create a new bot in BotFather and send me that token instead.")
                return
            answers = session.get("answers", {})
            try:
                request = request_bootstrap(
                    conn,
                    cfg,
                    requester_identity=format_user_label(sender_username, display_name or str(answers.get("full_name") or ""), sender_id),
                    unix_user=str(answers.get("unix_user") or sender_id),
                    source_ip=f"telegram:{sender_id}",
                    tailnet_identity=None,
                    issue_pending_token=False,
                    auto_provision=True,
                    requested_model_preset="codex",
                    requested_channels=["telegram"],
                )
                approve_request(
                    conn,
                    request_id=str(request["request_id"]),
                    surface="curator-channel",
                    actor=str(session.get("approved_by_actor") or "telegram-operator"),
                    cfg=cfg,
                )
                pending_bot_token_path = write_onboarding_bot_token_secret(
                    cfg,
                    str(session["session_id"]),
                    normalized,
                )
            except Exception as exc:  # noqa: BLE001
                send_text(bot_token, chat_id, f"I couldn't start provisioning yet: {exc}")
                return
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="provision-pending",
                pending_bot_token="",
                pending_bot_token_path=pending_bot_token_path,
                telegram_bot_id=str(bot_profile.get("id") or ""),
                telegram_bot_username=str(bot_profile.get("username") or ""),
                linked_request_id=str(request["request_id"]),
                linked_agent_id=str(request.get("agent_id") or ""),
                provision_error="",
            )
            send_text(
                bot_token,
                chat_id,
                (
                    f"Thanks. I’m provisioning `{answers.get('unix_user')}` now and wiring "
                    f"@{bot_profile.get('username') or 'your bot'}. I’ll tell you when it’s ready."
                ),
            )
            return

        prompt_session(bot_token, session)


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
            sys.stderr.write(
                f"Curator onboarding failed on update {update_key or '<unknown>'}: {compact_error}\n"
            )
            sys.stderr.flush()
            if not update_key:
                break
            with connect_db(cfg) as conn:
                failure = record_onboarding_update_failure(
                    conn,
                    update_id=update_key,
                    error=compact_error,
                )
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
    if cfg.operator_notify_platform != "telegram":
        raise SystemExit("Curator Telegram onboarding requires OPERATOR_NOTIFY_CHANNEL_PLATFORM=telegram.")
    bot_token = resolve_bot_token(cfg)
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
