#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import datetime as dt
import hmac
import json
import os
import sys

from arclink_control import (
    Config,
    approve_ssot_pending_write,
    approve_onboarding_session,
    approve_request,
    config_env_value,
    connect_db,
    deny_ssot_pending_write,
    deny_onboarding_session,
    deny_request,
    dismiss_pin_upgrade_action,
    get_onboarding_session,
    get_pin_upgrade_action_payload,
    request_operator_action,
    retry_discord_contact,
    save_onboarding_session,
    utc_now_iso,
    upsert_setting,
)
from arclink_discord import discord_get_current_user
from arclink_discord import discord_send_message
from arclink_onboarding_completion import (
    completion_followup_discord_components,
    completion_followup_text_for_session,
    completion_scrubbed_text_for_session,
    ensure_discord_agent_dm_confirmation_code,
)
from arclink_onboarding_flow import (
    OutboundMessage,
    BotIdentity,
    IncomingMessage,
    notify_session_state,
    parse_notion_setup_callback_data,
    process_onboarding_message,
    resolve_curator_discord_bot_token,
)
from arclink_operator_raven import (
    dispatch_operator_raven_command,
    operator_approval_code,
    operator_raven_command_is_mutating,
    operator_raven_command_requested,
    strip_operator_approval_code,
)


DISCORD_SEEN_MESSAGE_PREFIX = "curator_discord_onboarding_seen_message:"
DISCORD_SEEN_MESSAGE_MAX_ROWS = 10000
DISCORD_SEEN_MESSAGE_TTL_SECONDS = 30 * 24 * 60 * 60
DISCORD_PROCESSING_CLAIM_TTL_SECONDS = 10 * 60


def _discord_seen_message_key(message_id: str) -> str:
    return f"{DISCORD_SEEN_MESSAGE_PREFIX}{str(message_id or '').strip()}"


def _discord_seen_cutoff_iso(seconds: int) -> str:
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=max(1, int(seconds)))).replace(microsecond=0).isoformat()


def _prune_discord_seen_messages(conn) -> None:  # type: ignore[no-untyped-def]
    prefix_len = len(DISCORD_SEEN_MESSAGE_PREFIX)
    stale_seen_cutoff = _discord_seen_cutoff_iso(DISCORD_SEEN_MESSAGE_TTL_SECONDS)
    stale_processing_cutoff = _discord_seen_cutoff_iso(DISCORD_PROCESSING_CLAIM_TTL_SECONDS)
    conn.execute(
        """
        DELETE FROM settings
        WHERE substr(key, 1, ?) = ?
          AND (
            updated_at < ?
            OR (value = 'processing' AND updated_at < ?)
          )
        """,
        (prefix_len, DISCORD_SEEN_MESSAGE_PREFIX, stale_seen_cutoff, stale_processing_cutoff),
    )
    conn.execute(
        """
        DELETE FROM settings
        WHERE key IN (
          SELECT key
          FROM settings
          WHERE substr(key, 1, ?) = ?
          ORDER BY updated_at DESC, key DESC
          LIMIT -1 OFFSET ?
        )
        """,
        (prefix_len, DISCORD_SEEN_MESSAGE_PREFIX, DISCORD_SEEN_MESSAGE_MAX_ROWS),
    )


def _discord_operator_approval_code() -> str:
    return operator_approval_code(
        {
            "ARCLINK_OPERATOR_TELEGRAM_APPROVAL_CODE": config_env_value(
                "ARCLINK_OPERATOR_TELEGRAM_APPROVAL_CODE",
                "",
            ),
            "ARCLINK_OPERATOR_APPROVAL_CODE": config_env_value("ARCLINK_OPERATOR_APPROVAL_CODE", ""),
        }
    )


def _discord_operator_code_ok(supplied_code: str) -> bool:
    code = _discord_operator_approval_code()
    return not code or hmac.compare_digest(str(supplied_code or "").strip(), code)


def _discord_operator_code_required_message() -> str:
    return (
        "Operator code required for this action. Include your configured operator code "
        "as the operator_code field or as the token after the target id."
    )


def _discord_operator_action_tail(*, command: str, text: str) -> tuple[bool, str]:
    code = _discord_operator_approval_code()
    parts = text.strip().split(maxsplit=2)
    if not code:
        return True, parts[2].strip() if len(parts) > 2 and command == "/deny" else ""
    tail = parts[2].strip() if len(parts) > 2 else ""
    code_parts = tail.split(maxsplit=1)
    if not code_parts or not hmac.compare_digest(code_parts[0], code):
        return False, ""
    return True, code_parts[1].strip() if len(code_parts) > 1 and command == "/deny" else ""


def _discord_retry_contact_target(text: str) -> tuple[bool, str]:
    parts = text.strip().split(maxsplit=1)
    target_tail = parts[1].strip() if len(parts) > 1 else ""
    code = _discord_operator_approval_code()
    if not code:
        return bool(target_tail), target_tail
    target, _, supplied = target_tail.rpartition(" ")
    if not target.strip() or not supplied.strip() or not hmac.compare_digest(supplied.strip(), code):
        return False, ""
    return True, target.strip()


def _discord_component_requires_operator_code(*, scope: str, action: str) -> bool:
    if not _discord_operator_approval_code():
        return False
    normalized_scope = scope.strip().lower()
    normalized_action = action.strip().lower()
    if normalized_scope == "ssot" and normalized_action in {"approve", "deny"}:
        return True
    if normalized_scope in {"upgrade", "pin-upgrade"} and normalized_action in {"dismiss", "install"}:
        return True
    return False


def _discord_validator(curator_bot_id: str):
    def _validate(raw_token: str) -> BotIdentity:
        normalized = raw_token.strip()
        try:
            bot_profile = discord_get_current_user(bot_token=normalized)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Discord rejected that token: {exc}") from exc
        if not bool(bot_profile.get("bot")):
            raise RuntimeError("That token does not belong to a Discord bot application.")
        if str(bot_profile.get("id") or "") == curator_bot_id:
            raise RuntimeError("That token is for Curator’s Discord bot. Create a new bot application and send me that bot token instead.")
        display_name = str(bot_profile.get("global_name") or bot_profile.get("username") or "")
        return BotIdentity(
            bot_id=str(bot_profile.get("id") or ""),
            username=str(bot_profile.get("username") or ""),
            display_name=display_name,
        )

    return _validate


def _format_actor_label(author) -> str:  # type: ignore[no-untyped-def]
    username = str(getattr(author, "name", "") or "").strip()
    if username:
        return username
    display_name = str(getattr(author, "display_name", "") or "").strip()
    if display_name:
        return display_name
    return f"discord:{getattr(author, 'id', 'unknown')}"


def _csv_env_values(*names: str) -> set[str]:
    values: set[str] = set()
    for name in names:
        raw = str(os.environ.get(name) or config_env_value(name, "") or "").strip()
        for item in raw.replace(";", ",").split(","):
            clean = item.strip()
            if clean:
                values.add(clean)
    return values


async def main() -> None:
    cfg = Config.from_env()
    if not cfg.curator_discord_onboarding_enabled:
        return
    bot_token = resolve_curator_discord_bot_token(cfg)
    if not bot_token:
        raise SystemExit("Curator Discord onboarding requires DISCORD_BOT_TOKEN.")
    try:
        curator_profile = discord_get_current_user(bot_token=bot_token)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Failed to query Discord /users/@me: {exc}") from exc
    curator_bot_id = str(curator_profile.get("id") or "")
    if not curator_bot_id:
        raise SystemExit("Discord /users/@me did not return a bot id.")

    try:
        import discord
        from discord import app_commands
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"discord.py is required for Discord onboarding: {exc}") from exc

    intents = discord.Intents.default()
    intents.dm_messages = True
    intents.guild_messages = True
    intents.message_content = True

    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)
    validator = _discord_validator(curator_bot_id)
    sync_done = False

    def _operator_discord_enabled() -> bool:
        # Discord is an operator control surface when it is the primary response channel
        # OR when it is in the enabled operator channel set (so the operator can run, e.g.,
        # Telegram primary + Discord secondary at the same time).
        if (cfg.operator_notify_platform or "").strip().lower() == "discord":
            return True
        channels = {
            value.strip().lower()
            for value in str(
                os.environ.get("ARCLINK_CURATOR_CHANNELS")
                or config_env_value("ARCLINK_CURATOR_CHANNELS", "")
                or ""
            ).split(",")
            if value.strip()
        }
        return "discord" in channels

    def _operator_channel_id() -> str:
        if not _operator_discord_enabled():
            return ""
        # Prefer an explicit Discord operator channel so Discord can be a SECONDARY
        # operator surface; the shared operator channel id holds the PRIMARY platform's
        # channel, so it is only reused when Discord itself is the primary.
        explicit = str(
            os.environ.get("ARCLINK_OPERATOR_DISCORD_CHANNEL_ID")
            or config_env_value("ARCLINK_OPERATOR_DISCORD_CHANNEL_ID", "")
            or ""
        ).strip()
        if explicit:
            return explicit
        if (cfg.operator_notify_platform or "").strip().lower() == "discord":
            return str(cfg.operator_notify_channel_id or "").strip()
        return ""

    def _operator_discord_user_ids() -> set[str]:
        return _csv_env_values("ARCLINK_OPERATOR_DISCORD_USER_IDS", "OPERATOR_DISCORD_USER_IDS")

    def _operator_discord_role_ids() -> set[str]:
        return _csv_env_values("ARCLINK_OPERATOR_DISCORD_ROLE_IDS", "OPERATOR_DISCORD_ROLE_IDS")

    def _operator_discord_subject_allowed(subject, *, guild) -> tuple[bool, str]:  # type: ignore[no-untyped-def]
        user_id = str(getattr(subject, "id", "") or "").strip()
        allowed_users = _operator_discord_user_ids()
        allowed_roles = _operator_discord_role_ids()
        if allowed_users or allowed_roles:
            if user_id and user_id in allowed_users:
                return True, ""
            subject_roles = {
                str(getattr(role, "id", "") or "").strip()
                for role in getattr(subject, "roles", []) or []
                if str(getattr(role, "id", "") or "").strip()
            }
            if subject_roles & allowed_roles:
                return True, ""
            return False, "This Discord user is not on the Operator Raven allowlist."
        if guild is None:
            return True, ""
        return (
            False,
            "Discord Operator Raven requires ARCLINK_OPERATOR_DISCORD_USER_IDS or "
            "ARCLINK_OPERATOR_DISCORD_ROLE_IDS for guild channels.",
        )

    def _claim_discord_message_once(message_id: str) -> bool:
        normalized = str(message_id or "").strip()
        if not normalized:
            return True
        key = _discord_seen_message_key(normalized)
        with connect_db(cfg) as conn:
            _prune_discord_seen_messages(conn)
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                """,
                (key, "processing", utc_now_iso()),
            )
            if cursor.rowcount == 1:
                _prune_discord_seen_messages(conn)
            conn.commit()
            return cursor.rowcount == 1

    def _mark_discord_message_processed(message_id: str) -> None:
        normalized = str(message_id or "").strip()
        if not normalized:
            return
        with connect_db(cfg) as conn:
            conn.execute(
                """
                UPDATE settings
                SET value = ?, updated_at = ?
                WHERE key = ?
                """,
                ("processed", utc_now_iso(), _discord_seen_message_key(normalized)),
            )
            conn.commit()

    def _release_discord_message_claim(message_id: str) -> None:
        normalized = str(message_id or "").strip()
        if not normalized:
            return
        with connect_db(cfg) as conn:
            conn.execute("DELETE FROM settings WHERE key = ?", (_discord_seen_message_key(normalized),))
            conn.commit()

    def _run_operator_action(*, target_id: str, action: str, actor: str, reason: str = "", scope: str = "") -> str:
        normalized_action = action.strip().lower()
        normalized_scope = scope.strip().lower()
        with connect_db(cfg) as conn:
            if target_id.startswith("onb_"):
                session = get_onboarding_session(conn, target_id)
                if session is None:
                    return f"Unknown onboarding session: {target_id}"
                if normalized_action == "approve":
                    updated = approve_onboarding_session(conn, session_id=target_id, actor=actor)
                    notify_session_state(cfg, updated)
                    return (
                        f"Approved {target_id} for "
                        f"{updated['answers'].get('full_name') or updated.get('sender_display_name') or updated.get('sender_id')}."
                    )
                updated = deny_onboarding_session(
                    conn,
                    session_id=target_id,
                    actor=actor,
                    reason=reason.strip(),
                )
                notify_session_state(cfg, updated)
                return f"Denied {target_id}."
            if target_id.startswith("req_"):
                if normalized_action == "approve":
                    approve_request(conn, request_id=target_id, surface="curator-channel", actor=actor, cfg=cfg)
                    return f"Approved {target_id}."
                deny_request(conn, request_id=target_id, surface="curator-channel", actor=actor, cfg=cfg)
                return f"Denied {target_id}."
            if target_id.startswith("ssotw_"):
                if normalized_action == "approve":
                    approve_ssot_pending_write(
                        conn,
                        cfg,
                        pending_id=target_id,
                        surface="curator-channel",
                        actor=actor,
                    )
                    return f"Approved {target_id}."
                deny_ssot_pending_write(
                    conn,
                    cfg,
                    pending_id=target_id,
                    surface="curator-channel",
                    actor=actor,
                    reason=reason.strip(),
                )
                return f"Denied {target_id}."
            if normalized_scope == "pin-upgrade":
                payload = get_pin_upgrade_action_payload(conn, target_id)
                if payload is None:
                    return f"Unknown pinned-component upgrade action: {target_id}"
                components = ", ".join(item["component"] for item in payload["items"])
                if normalized_action == "dismiss":
                    dismissed = dismiss_pin_upgrade_action(conn, target_id)
                    silenced = ", ".join(dismissed.get("silenced") or dismissed.get("components") or [])
                    return f"Dismissed pinned-component upgrade notice for {silenced or components}."
                if normalized_action in {"preview", "install"}:
                    return (
                        "Pinned-component upgrade preview only: no action was queued from this button. "
                        f"Review {components}, then send `/pin_upgrade <component> confirm` in Operator Raven "
                        "or append your configured operator approval code."
                    )
                return f"Unknown pinned-component upgrade action: {normalized_action}"
            if normalized_action in {"preview", "install", "dismiss"}:
                if normalized_action == "dismiss":
                    upsert_setting(conn, "arclink_upgrade_last_notified_sha", target_id)
                    return f"Dismissed ArcLink update notice for {target_id[:12]}."
                return (
                    "ArcLink upgrade preview only: no action was queued from this button. "
                    "Review the release notice, then send `/upgrade confirm` in Operator Raven "
                    "or append your configured operator approval code."
                )
        return f"Unknown approval target: {target_id}"

    async def _ensure_operator_channel(interaction) -> bool:  # type: ignore[no-untyped-def]
        operator_channel_id = _operator_channel_id()
        if not operator_channel_id:
            await interaction.response.send_message(
                "Discord is not an enabled operator control channel. Enable it in the operator "
                "channel set and set ARCLINK_OPERATOR_DISCORD_CHANNEL_ID (or make Discord the "
                "primary operator channel).",
                ephemeral=True,
            )
            return False
        channel_id = str(getattr(interaction.channel, "id", "") or "")
        if channel_id != operator_channel_id:
            await interaction.response.send_message(
                f"Run this in the configured operator channel <#{operator_channel_id}>.",
                ephemeral=True,
            )
            return False
        allowed, reason = _operator_discord_subject_allowed(
            getattr(interaction, "user", None),
            guild=getattr(interaction, "guild", None),
        )
        if not allowed:
            await interaction.response.send_message(reason, ephemeral=True)
            return False
        return True

    def _operator_raven_response(content: str, *, actor_id: str = "", message_id: str = "") -> str:
        try:
            dispatch_text = content
            if operator_raven_command_is_mutating(content):
                if not actor_id:
                    return (
                        "This Operator Raven action runs for real and must come from the operator channel "
                        "with an identified operator. It was refused."
                    )
                approval_code = _discord_operator_approval_code()
                code_ok, dispatch_text = strip_operator_approval_code(content, approval_code)
                if not code_ok:
                    return (
                        "Operator code required for this action. Append your operator code, "
                        "e.g. /upgrade <operator-code> or /pod_repair <deployment> restart <operator-code>."
                    )
                if approval_code:
                    dispatch_text = f"{dispatch_text} --confirm"
            with connect_db(cfg) as conn:
                result = dispatch_operator_raven_command(
                    conn,
                    dispatch_text,
                    env=os.environ,
                    actor_id=actor_id,
                    idempotency_key=message_id,
                )
            return str(result.get("message") or "Operator Raven command returned no output.")
        except Exception as exc:  # noqa: BLE001
            return f"Operator Raven command failed closed: {exc}"

    def _operator_raven_result(content: str, *, actor_id: str = "", message_id: str = "") -> dict:
        """Dispatch and return the full Operator Raven result (message + one-tap buttons)."""
        try:
            with connect_db(cfg) as conn:
                return dispatch_operator_raven_command(
                    conn,
                    content,
                    env=os.environ,
                    actor_id=actor_id,
                    idempotency_key=message_id,
                )
        except Exception as exc:  # noqa: BLE001
            return {"message": f"Operator Raven command failed closed: {exc}", "buttons": []}

    def _operator_buttons_view(result: dict | None):
        """Render Operator Raven one-tap buttons as a Discord component view."""
        buttons = list((result or {}).get("buttons") or [])
        if not buttons:
            return None
        view = discord.ui.View(timeout=None)
        for button in buttons[:8]:
            label = str(button.get("label") or "").strip()[:80]
            data = str(button.get("callback_data") or "").strip()
            if label and data and len(data) <= 100:
                view.add_item(discord.ui.Button(label=label, custom_id=data, style=discord.ButtonStyle.primary))
        return view if view.children else None

    async def _process_discord_input(
        *,
        chat_id: str,
        sender_id: str,
        sender_username: str,
        sender_display_name: str,
        text: str,
    ) -> list[OutboundMessage]:
        return process_onboarding_message(
            cfg,
            IncomingMessage(
                platform="discord",
                chat_id=chat_id,
                sender_id=sender_id,
                sender_username=sender_username,
                sender_display_name=sender_display_name,
                text=text,
            ),
            validate_bot_token=validator,
        )

    async def _send_replies(
        *,
        replies: list[OutboundMessage],
        origin_chat_id: str,
        interaction=None,
    ) -> None:
        responded = bool(interaction and (interaction.response.is_done() if interaction.response else False))
        for reply in replies:
            if reply.chat_id == origin_chat_id:
                if interaction is not None:
                    if not responded:
                        await interaction.response.send_message(reply.text)
                        responded = True
                    else:
                        await interaction.followup.send(reply.text)
                else:
                    if reply.discord_components:
                        discord_send_message(
                            bot_token=bot_token,
                            channel_id=str(origin_chat_id),
                            text=reply.text,
                            components=reply.discord_components,
                        )
                    else:
                        channel = client.get_channel(int(origin_chat_id))
                        if channel is None:
                            channel = await client.fetch_channel(int(origin_chat_id))
                        if channel is None:
                            raise RuntimeError(f"Discord channel {origin_chat_id} was not available")
                        await channel.send(reply.text)
                continue
            if reply.discord_components:
                discord_send_message(
                    bot_token=bot_token,
                    channel_id=str(reply.chat_id),
                    text=reply.text,
                    components=reply.discord_components,
                )
                continue
            channel = client.get_channel(int(reply.chat_id))
            if channel is None:
                channel = await client.fetch_channel(int(reply.chat_id))
            if channel is None:
                raise RuntimeError(f"Discord channel {reply.chat_id} was not available")
            await channel.send(reply.text)

    async def _handle_dm_command(interaction, text: str) -> None:  # type: ignore[no-untyped-def]
        if interaction.channel is None:
            await interaction.response.send_message("Open a DM with me and try again.", ephemeral=True)
            return
        if interaction.guild is not None:
            try:
                await interaction.user.send("Open a DM with me and send /start there. I only onboard in private.")
            except Exception:
                pass
            await interaction.response.send_message(
                "I only onboard in private. Open a DM with me and send `/start` there.",
                ephemeral=True,
            )
            return
        replies = await _process_discord_input(
            chat_id=str(interaction.channel.id),
            sender_id=str(interaction.user.id),
            sender_username=str(getattr(interaction.user, "name", "") or ""),
            sender_display_name=str(getattr(interaction.user, "display_name", "") or ""),
            text=text,
        )
        await _send_replies(replies=replies, origin_chat_id=str(interaction.channel.id), interaction=interaction)

    async def _handle_operator_channel_message(message, content: str) -> bool:  # type: ignore[no-untyped-def]
        operator_channel_id = _operator_channel_id()
        if not operator_channel_id or str(message.channel.id) != operator_channel_id:
            return False
        allowed, reason = _operator_discord_subject_allowed(message.author, guild=getattr(message, "guild", None))
        if not allowed:
            await message.channel.send(reason)
            return True

        parts = content.strip().split(maxsplit=2)
        command = parts[0].lower() if parts else ""
        if operator_raven_command_requested(content):
            await message.channel.send(
                _operator_raven_response(
                    content,
                    actor_id=_format_actor_label(message.author),
                    message_id=str(getattr(message, "id", "") or ""),
                )
            )
            return True

        # /upgrade is now a first-class Operator Raven command (host_upgrade)
        # handled by the operator_raven_command_requested branch above. The
        # registered /upgrade slash command still uses the operator-action queue.

        if command in {"/retry-contact", "/retry_contact"}:
            target_ok, retry_target = _discord_retry_contact_target(content)
            if not target_ok:
                if content.strip().split(maxsplit=1)[1:]:
                    await message.channel.send(_discord_operator_code_required_message())
                else:
                    await message.channel.send("Use /retry-contact <unixusername|discordname>.")
                return True
            if not retry_target:
                await message.channel.send("Use /retry-contact <unixusername|discordname>.")
                return True
            actor = _format_actor_label(message.author)
            try:
                with connect_db(cfg) as conn:
                    result = retry_discord_contact(
                        conn,
                        cfg,
                        target=retry_target,
                        actor=actor,
                        request_source="discord-retry-contact",
                    )
                await message.channel.send(str(result.get("message") or "Queued contact retry."))
            except Exception as exc:  # noqa: BLE001
                await message.channel.send(f"Could not retry contact: {exc}")
            return True

        if not content.startswith("/"):
            # Free-form operator chat routes to the operator's one Hermes agent
            # when it is live; the gateway-bridge worker replies asynchronously.
            try:
                from arclink_operator_agent import (
                    enqueue_operator_agent_turn,
                    operator_conversation_routable,
                )

                with connect_db(cfg) as conn:
                    if operator_conversation_routable(conn):
                        queued = enqueue_operator_agent_turn(
                            conn,
                            channel="discord",
                            channel_identity=f"discord:{getattr(message.author, 'id', '')}",
                            text=content,
                            reply_to_message_id=str(getattr(message, "id", "") or ""),
                            display_name=_format_actor_label(message.author),
                            discord_channel_id=str(getattr(message.channel, "id", "") or ""),
                            discord_user_id=str(getattr(message.author, "id", "") or ""),
                            discord_chat_type="guild" if getattr(message, "guild", None) is not None else "dm",
                        )
                        if queued is not None:
                            return True
            except Exception:  # noqa: BLE001 - never let the operator channel fail open
                pass
            return False

        if command not in {"/approve", "/deny"}:
            return False
        if len(parts) < 2:
            await message.channel.send(
                "Use /approve onb_xxx, /deny onb_xxx optional reason, /approve req_xxx, /deny req_xxx, /approve ssotw_xxx, /deny ssotw_xxx optional reason, or /retry-contact <unixusername|discordname>."
            )
            return True

        target_id = parts[1].strip()
        code_ok, operator_reason = _discord_operator_action_tail(command=command, text=content)
        if not code_ok:
            await message.channel.send(_discord_operator_code_required_message())
            return True
        actor = _format_actor_label(message.author)
        response = _run_operator_action(
            target_id=target_id,
            action="approve" if command == "/approve" else "deny",
            actor=actor,
            reason=operator_reason if command == "/deny" else "",
        )
        await message.channel.send(response)
        return True

    @tree.command(name="start", description="Start a private onboarding session with Curator.")
    async def start_command(interaction) -> None:  # type: ignore[no-untyped-def]
        await _handle_dm_command(interaction, "/start")

    @tree.command(name="onboard", description="Start a private onboarding session with Curator.")
    async def onboard_command(interaction) -> None:  # type: ignore[no-untyped-def]
        await _handle_dm_command(interaction, "/start")

    @tree.command(name="status", description="Show your current onboarding step.")
    async def status_command(interaction) -> None:  # type: ignore[no-untyped-def]
        await _handle_dm_command(interaction, "/status")

    @tree.command(name="cancel", description="Cancel your current onboarding session.")
    async def cancel_command(interaction) -> None:  # type: ignore[no-untyped-def]
        await _handle_dm_command(interaction, "/cancel")

    @tree.command(name="restart", description="Restart the current provider authorization step.")
    async def restart_command(interaction) -> None:  # type: ignore[no-untyped-def]
        await _handle_dm_command(interaction, "/restart")

    @tree.command(name="verify-notion", description="Resume the shared Notion verification step for your lane.")
    async def verify_notion_command(interaction) -> None:  # type: ignore[no-untyped-def]
        await _handle_dm_command(interaction, "/verify-notion")

    @tree.command(name="setup-backup", description="Set up the private Hermes-home backup for your lane.")
    async def setup_backup_command(interaction) -> None:  # type: ignore[no-untyped-def]
        await _handle_dm_command(interaction, "/setup-backup")

    @tree.command(name="backup", description="Set up the private Hermes-home backup for your lane.")
    async def backup_command(interaction) -> None:  # type: ignore[no-untyped-def]
        await _handle_dm_command(interaction, "/setup-backup")

    @tree.command(name="ssh-key", description="Install your local remote-Hermes SSH public key for tailnet access.")
    @app_commands.describe(public_key="The ssh-ed25519/ssh-rsa public key printed by the remote Hermes helper")
    async def ssh_key_command(interaction, public_key: str) -> None:  # type: ignore[no-untyped-def]
        await _handle_dm_command(interaction, f"/ssh-key {public_key.strip()}")

    @tree.command(name="sshkey", description="Install your local remote-Hermes SSH public key for tailnet access.")
    @app_commands.describe(public_key="The ssh-ed25519/ssh-rsa public key printed by the remote Hermes helper")
    async def sshkey_command(interaction, public_key: str) -> None:  # type: ignore[no-untyped-def]
        await _handle_dm_command(interaction, f"/ssh-key {public_key.strip()}")

    @tree.command(name="approve", description="Approve an onboarding session, provisioning request, or pending SSOT write.")
    @app_commands.describe(
        target_id="onb_xxx, req_xxx, or ssotw_xxx",
        operator_code="Required when an operator approval code is configured",
    )
    async def approve_command(interaction, target_id: str, operator_code: str = "") -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        if not _discord_operator_code_ok(operator_code):
            await interaction.response.send_message(_discord_operator_code_required_message(), ephemeral=True)
            return
        actor = _format_actor_label(interaction.user)
        await interaction.response.send_message(
            _run_operator_action(target_id=target_id.strip(), action="approve", actor=actor)
        )

    @tree.command(name="deny", description="Deny an onboarding session, provisioning request, or pending SSOT write.")
    @app_commands.describe(
        target_id="onb_xxx, req_xxx, or ssotw_xxx",
        reason="Optional deny reason",
        operator_code="Required when an operator approval code is configured",
    )
    async def deny_command(interaction, target_id: str, reason: str = "", operator_code: str = "") -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        if not _discord_operator_code_ok(operator_code):
            await interaction.response.send_message(_discord_operator_code_required_message(), ephemeral=True)
            return
        actor = _format_actor_label(interaction.user)
        normalized_target = target_id.strip()
        response = _run_operator_action(
            target_id=normalized_target,
            action="deny",
            actor=actor,
            reason=reason,
        )
        await interaction.response.send_message(response)

    @tree.command(name="upgrade", description="Preview or confirm an ArcLink host upgrade/repair.")
    @app_commands.describe(confirm="Queue only after reviewing the dry-run", operator_code="Required when an operator approval code is configured")
    async def upgrade_command(interaction, confirm: bool = False, operator_code: str = "") -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        actor = _format_actor_label(interaction.user)
        if not confirm:
            # Bare /upgrade renders the one-tap menu: single-use nonce buttons
            # queue the real action through the same Operator Raven gate.
            menu = _operator_raven_result(
                "/upgrade",
                actor_id=actor,
                message_id=str(getattr(interaction, "id", "") or ""),
            )
            view = _operator_buttons_view(menu)
            message_text = str(menu.get("message") or "Operator Raven upgrade menu")
            if view is not None:
                await interaction.response.send_message(message_text, view=view)
            else:
                await interaction.response.send_message(message_text)
            return
        dispatch = f"/upgrade {(operator_code.strip() or 'confirm')}"
        await interaction.response.send_message(
            _operator_raven_response(dispatch, actor_id=actor, message_id=str(getattr(interaction, "id", "") or ""))
        )

    @tree.command(name="pin-upgrade", description="Preview or confirm a pinned-component upgrade.")
    @app_commands.describe(
        component="hermes, qmd, nextcloud, postgres, redis, nvm, or node",
        confirm="Queue only after reviewing the dry-run",
        operator_code="Required when an operator approval code is configured",
    )
    async def pin_upgrade_command(interaction, component: str, confirm: bool = False, operator_code: str = "") -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        actor = _format_actor_label(interaction.user)
        clean_component = component.strip().lower()
        dispatch = f"/pin_upgrade {clean_component} --dry-run"
        if confirm:
            dispatch = f"/pin_upgrade {clean_component} {(operator_code.strip() or 'confirm')}"
        await interaction.response.send_message(
            _operator_raven_response(dispatch, actor_id=actor, message_id=str(getattr(interaction, "id", "") or ""))
        )

    @tree.command(name="retry-contact", description="Retry a Discord agent-bot contact handoff.")
    @app_commands.describe(
        target="Operator use: Unix username, onboarding session id, Discord user id, username, or display name",
        operator_code="Required when an operator approval code is configured",
    )
    async def retry_contact_command(interaction, target: str = "", operator_code: str = "") -> None:  # type: ignore[no-untyped-def]
        operator_channel_id = _operator_channel_id()
        channel_id = str(getattr(interaction.channel, "id", "") or "")
        if interaction.guild is None and channel_id != operator_channel_id:
            await _handle_dm_command(interaction, "/retry-contact")
            return
        if not await _ensure_operator_channel(interaction):
            return
        if not target.strip():
            await interaction.response.send_message(
                "Use `/retry-contact <unixusername|discordname>` here. Onboarding users can DM me `/retry-contact` for their own handoff.",
                ephemeral=True,
            )
            return
        if not _discord_operator_code_ok(operator_code):
            await interaction.response.send_message(_discord_operator_code_required_message(), ephemeral=True)
            return
        actor = _format_actor_label(interaction.user)
        try:
            with connect_db(cfg) as conn:
                result = retry_discord_contact(
                    conn,
                    cfg,
                    target=target.strip(),
                    actor=actor,
                    request_source="discord-slash-retry-contact",
                )
            await interaction.response.send_message(str(result.get("message") or "Queued contact retry."))
        except Exception as exc:  # noqa: BLE001
            await interaction.response.send_message(f"Could not retry contact: {exc}", ephemeral=True)

    @tree.command(name="operator-status", description="Show Control Node Operator Raven status.")
    async def operator_status_command(interaction) -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        await interaction.response.send_message(_operator_raven_response("/operator_status"))

    @tree.command(name="operator-agents", description="Show ArcLink Captain Agents and ArcPods.")
    async def operator_agents_command(interaction) -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        await interaction.response.send_message(_operator_raven_response("/agents"))

    @tree.command(name="operator-fleet", description="List Sovereign fleet workers.")
    async def operator_fleet_command(interaction) -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        await interaction.response.send_message(_operator_raven_response("/operator_fleet"))

    @tree.command(name="worker-probe", description="Dry-run a worker readiness probe.")
    @app_commands.describe(target="Fleet host id or hostname")
    async def worker_probe_command(interaction, target: str) -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        await interaction.response.send_message(_operator_raven_response(f"/worker_probe {target.strip()} --dry-run"))

    @tree.command(name="user-lookup", description="Look up a Captain account without exposing secrets.")
    @app_commands.describe(query="User id, email, or display name")
    async def user_lookup_command(interaction, query: str) -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        await interaction.response.send_message(_operator_raven_response(f"/user_lookup {query.strip()}"))

    @tree.command(name="billing-status", description="Show billing and refuel credit posture.")
    async def billing_status_command(interaction) -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        await interaction.response.send_message(_operator_raven_response("/billing_status"))

    @tree.command(name="backup-status", description="Show private-backup setup posture.")
    async def backup_status_command(interaction) -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        await interaction.response.send_message(_operator_raven_response("/backup_status"))

    @tree.command(name="workspace-status", description="Show qmd, memory, Notion, and share posture.")
    async def workspace_status_command(interaction) -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        await interaction.response.send_message(_operator_raven_response("/workspace_status"))

    @tree.command(name="pod-repair", description="Dry-run an ArcPod repair plan.")
    @app_commands.describe(deployment_id="ArcPod deployment id")
    async def pod_repair_command(interaction, deployment_id: str) -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        await interaction.response.send_message(_operator_raven_response(f"/pod_repair {deployment_id.strip()} --dry-run"))

    @tree.command(name="upgrade-check", description="Check upgrade status without queuing an upgrade.")
    async def upgrade_check_command(interaction) -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        await interaction.response.send_message(_operator_raven_response("/upgrade_check"))

    @tree.command(name="upgrade-policy", description="Show upgrade policy, proof gates, and rollback posture.")
    @app_commands.describe(component="Optional component, for example hermes, qmd, docker, postgres, redis, nvm, or node")
    async def upgrade_policy_command(interaction, component: str = "") -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        suffix = f" {component.strip()}" if component.strip() else ""
        await interaction.response.send_message(_operator_raven_response(f"/upgrade_policy{suffix}"))

    @tree.command(name="upgrade-sweep", description="Preview or queue pending pinned-component upgrades.")
    @app_commands.describe(
        include_stateful="Include stateful targets only inside a maintenance window",
        confirm="Queue only after reviewing the dry-run",
        operator_code="Required when an operator approval code is configured",
    )
    async def upgrade_sweep_command(
        interaction,
        include_stateful: bool = False,
        confirm: bool = False,
        operator_code: str = "",
    ) -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        actor = _format_actor_label(interaction.user)
        pieces = ["/upgrade_sweep"]
        if include_stateful:
            pieces.append("--include-stateful")
        pieces.append(operator_code.strip() or "confirm" if confirm else "--dry-run")
        await interaction.response.send_message(
            _operator_raven_response(
                " ".join(pieces),
                actor_id=actor,
                message_id=str(getattr(interaction, "id", "") or ""),
            )
        )

    @tree.command(name="fleet-drain", description="Preview or apply fleet worker drain.")
    @app_commands.describe(
        target="Fleet host id or hostname",
        force="Allow draining the last currently eligible worker",
        confirm="Apply only after reviewing the dry-run",
        operator_code="Required when an operator approval code is configured",
    )
    async def fleet_drain_command(
        interaction,
        target: str,
        force: bool = False,
        confirm: bool = False,
        operator_code: str = "",
    ) -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        actor = _format_actor_label(interaction.user)
        pieces = ["/fleet_drain", target.strip()]
        if force:
            pieces.append("--force")
        pieces.append(operator_code.strip() or "confirm" if confirm else "--dry-run")
        await interaction.response.send_message(
            _operator_raven_response(
                " ".join(item for item in pieces if item),
                actor_id=actor,
                message_id=str(getattr(interaction, "id", "") or ""),
            )
        )

    @tree.command(name="fleet-resume", description="Preview or apply fleet worker resume.")
    @app_commands.describe(
        target="Fleet host id or hostname",
        confirm="Apply only after reviewing the dry-run",
        operator_code="Required when an operator approval code is configured",
    )
    async def fleet_resume_command(
        interaction,
        target: str,
        confirm: bool = False,
        operator_code: str = "",
    ) -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        actor = _format_actor_label(interaction.user)
        suffix = operator_code.strip() or "confirm" if confirm else "--dry-run"
        await interaction.response.send_message(
            _operator_raven_response(
                f"/fleet_resume {target.strip()} {suffix}".strip(),
                actor_id=actor,
                message_id=str(getattr(interaction, "id", "") or ""),
            )
        )

    @tree.command(name="rollout", description="Preview or queue an ArcPod rollout.")
    @app_commands.describe(
        target_version="Release/version to roll out",
        batch_size="Optional batch size",
        confirm="Queue only after reviewing the dry-run",
        operator_code="Required when an operator approval code is configured",
    )
    async def rollout_command(
        interaction,
        target_version: str,
        batch_size: int = 0,
        confirm: bool = False,
        operator_code: str = "",
    ) -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        actor = _format_actor_label(interaction.user)
        pieces = ["/rollout", target_version.strip()]
        if batch_size > 0:
            pieces.extend(["--batch-size", str(batch_size)])
        pieces.append(operator_code.strip() or "confirm" if confirm else "--dry-run")
        await interaction.response.send_message(
            _operator_raven_response(
                " ".join(item for item in pieces if item),
                actor_id=actor,
                message_id=str(getattr(interaction, "id", "") or ""),
            )
        )

    @tree.command(name="action-status", description="Track queued Operator Raven actions.")
    @app_commands.describe(target_id="Optional action id")
    async def action_status_command(interaction, target_id: str = "") -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        suffix = f" {target_id.strip()}" if target_id.strip() else ""
        await interaction.response.send_message(_operator_raven_response(f"/action_status{suffix}"))

    @tree.command(name="academy-status", description="Show Academy status for one Captain or the fleet.")
    @app_commands.describe(query="Optional user id, email, or display name")
    async def academy_status_command(interaction, query: str = "") -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        suffix = f" {query.strip()}" if query.strip() else ""
        await interaction.response.send_message(_operator_raven_response(f"/academy_status{suffix}"))

    @tree.command(name="academy-roster", description="Show Academy trainees and graduates.")
    @app_commands.describe(query="Optional user id, email, or display name")
    async def academy_roster_command(interaction, query: str = "") -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        suffix = f" {query.strip()}" if query.strip() else ""
        await interaction.response.send_message(_operator_raven_response(f"/academy_roster{suffix}"))

    @client.event
    async def on_ready() -> None:  # type: ignore[no-untyped-def]
        nonlocal sync_done
        if sync_done:
            return
        guild_ids_raw = str(os.environ.get("ARCLINK_CURATOR_DISCORD_COMMAND_GUILD_IDS", "") or "")
        guild_ids = [item.strip() for item in guild_ids_raw.split(",") if item.strip()]
        try:
            await tree.sync()
            for raw_guild_id in guild_ids:
                guild = discord.Object(id=int(raw_guild_id))
                tree.copy_global_to(guild=guild)
                await tree.sync(guild=guild)
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"Curator Discord command sync failed: {exc}\n")
        sync_done = True

    @client.event
    async def on_message(message) -> None:  # type: ignore[no-untyped-def]
        if message.author.bot:
            return
        content = (message.content or "").strip()
        if not content:
            return
        message_id = str(getattr(message, "id", "") or "")
        if not _claim_discord_message_once(message_id):
            return
        try:
            if await _handle_operator_channel_message(message, content):
                pass
            elif message.guild is not None:
                lower = content.lower()
                if lower in {"/start", "/onboard", "start", "onboard"}:
                    try:
                        await message.author.send("Open a DM with me and send /start there. I only onboard in private.")
                    except Exception:
                        pass
            else:
                replies = await _process_discord_input(
                    chat_id=str(message.channel.id),
                    sender_id=str(message.author.id),
                    sender_username=str(getattr(message.author, "name", "") or ""),
                    sender_display_name=str(getattr(message.author, "display_name", "") or ""),
                    text=content,
                )
                await _send_replies(replies=replies, origin_chat_id=str(message.channel.id))
        except Exception as exc:  # noqa: BLE001
            _release_discord_message_claim(message_id)
            compact_error = (str(exc).strip() or exc.__class__.__name__).replace("\n", " ")[:240]
            sys.stderr.write(f"Curator Discord onboarding failed on message {message_id or '<unknown>'}: {compact_error}\n")
            sys.stderr.flush()
            try:
                await message.channel.send("Curator could not process that message. Please retry in a moment.")
            except Exception:
                pass
            return
        try:
            _mark_discord_message_processed(message_id)
        except Exception as exc:  # noqa: BLE001
            compact_error = (str(exc).strip() or exc.__class__.__name__).replace("\n", " ")[:240]
            sys.stderr.write(
                f"Curator Discord onboarding could not mark message {message_id or '<unknown>'} processed: {compact_error}\n"
            )
            sys.stderr.flush()

    @client.event
    async def on_interaction(interaction) -> None:  # type: ignore[no-untyped-def]
        if interaction.type != discord.InteractionType.component:
            return
        data = getattr(interaction, "data", {}) or {}
        custom_id = str(data.get("custom_id") or "").strip()
        if custom_id.startswith("arclink:/") and operator_raven_command_requested(custom_id[len("arclink:"):]):
            # One-tap operator buttons (for example /upgrade_apply <nonce>):
            # the nonce inside the server-minted command is the single-use
            # confirmation, and the command runs through the same Operator
            # Raven dispatch gate as typed commands.
            if not await _ensure_operator_channel(interaction):
                return
            actor = _format_actor_label(interaction.user)
            result = _operator_raven_result(
                custom_id[len("arclink:"):].strip(),
                actor_id=actor,
                message_id=str(getattr(interaction, "id", "") or ""),
            )
            result_text = str(result.get("message") or "Operator Raven command returned no output.")
            message_text = str(getattr(getattr(interaction, "message", None), "content", "") or "").strip()
            replacement = (message_text + f"\n\n{result_text} ({actor})").strip() if message_text else result_text
            await interaction.response.edit_message(content=replacement, view=None)
            return
        if (
            custom_id.startswith("arclink:upgrade:")
            or custom_id.startswith("arclink:pin-upgrade:")
            or custom_id.startswith("arclink:ssot:")
        ):
            if not await _ensure_operator_channel(interaction):
                return
            try:
                _, scope, action, target_id = custom_id.split(":", 3)
            except ValueError:
                await interaction.response.send_message("That operator action is malformed.", ephemeral=True)
                return
            if scope not in {"upgrade", "pin-upgrade", "ssot"} or not target_id:
                await interaction.response.send_message("That operator action is malformed.", ephemeral=True)
                return
            if _discord_component_requires_operator_code(scope=scope, action=action):
                await interaction.response.send_message(_discord_operator_code_required_message(), ephemeral=True)
                return
            actor = _format_actor_label(interaction.user)
            result_text = _run_operator_action(target_id=target_id, action=action, actor=actor, scope=scope)
            message_text = str(getattr(getattr(interaction, "message", None), "content", "") or "").strip()
            replacement = (message_text + f"\n\n{result_text} ({actor})").strip() if message_text else result_text
            await interaction.response.edit_message(content=replacement, view=None)
            return

        backup_prefix = "arclink:onboarding-complete:setup-backup:"
        if custom_id.startswith(backup_prefix):
            session_id = custom_id[len(backup_prefix):].strip()
            if not session_id:
                await interaction.response.send_message("That backup setup receipt is malformed.", ephemeral=True)
                return
            actual_user = str(getattr(interaction.user, "id", "") or "")
            actual_chat = str(getattr(interaction.channel, "id", "") or "")
            with connect_db(cfg) as conn:
                session = get_onboarding_session(conn, session_id, redact_secrets=False)
                if session is None:
                    await interaction.response.send_message("That onboarding receipt is no longer active.", ephemeral=True)
                    return
                if actual_user != str(session.get("sender_id") or "") or actual_chat != str(session.get("chat_id") or ""):
                    await interaction.response.send_message("Only the onboarding recipient can set this up.", ephemeral=True)
                    return
                answers = session.get("answers", {}) if isinstance(session.get("answers"), dict) else {}
                if bool(answers.get("agent_backup_verified")):
                    await interaction.response.send_message("Private backup is already active for this lane.", ephemeral=True)
                    return
                if str(session.get("state") or "") != "completed":
                    await interaction.response.send_message(
                        "Backup setup is already open or this receipt is no longer active.",
                        ephemeral=True,
                    )
                    return
            replies = await _process_discord_input(
                chat_id=actual_chat,
                sender_id=actual_user,
                sender_username=str(getattr(interaction.user, "name", "") or ""),
                sender_display_name=str(getattr(interaction.user, "display_name", "") or ""),
                text="/setup-backup",
            )
            await _send_replies(replies=replies, origin_chat_id=actual_chat, interaction=interaction)
            return

        notion_parsed = parse_notion_setup_callback_data(custom_id)
        if notion_parsed is not None:
            action, session_id = notion_parsed
            actual_user = str(getattr(interaction.user, "id", "") or "")
            actual_chat = str(getattr(interaction.channel, "id", "") or "")
            if not actual_chat or not session_id:
                await interaction.response.send_message("That Notion setup button is malformed.", ephemeral=True)
                return
            with connect_db(cfg) as conn:
                session = get_onboarding_session(conn, session_id, redact_secrets=False)
                if session is None:
                    await interaction.response.send_message("That Notion setup session is no longer active.", ephemeral=True)
                    return
                if actual_user != str(session.get("sender_id") or "") or actual_chat != str(session.get("chat_id") or ""):
                    await interaction.response.send_message("Only the onboarding recipient can use that Notion setup button.", ephemeral=True)
                    return
            await interaction.response.send_message("Notion choice received.", ephemeral=True)
            text = {"ready": "ready", "skip": "skip", "verify": "/verify-notion"}.get(action, "")
            replies = await _process_discord_input(
                chat_id=actual_chat,
                sender_id=actual_user,
                sender_username=str(getattr(interaction.user, "name", "") or ""),
                sender_display_name=str(getattr(interaction.user, "display_name", "") or ""),
                text=text,
            )
            await _send_replies(replies=replies, origin_chat_id=actual_chat)
            return

        prefix = "arclink:onboarding-complete:ack:"
        if not custom_id.startswith(prefix):
            return
        session_id = custom_id[len(prefix):].strip()
        if not session_id:
            await interaction.response.send_message("That onboarding receipt is malformed.", ephemeral=True)
            return
        with connect_db(cfg) as conn:
            session = get_onboarding_session(conn, session_id, redact_secrets=False)
            if session is None or str(session.get("state") or "") != "completed":
                await interaction.response.send_message("That onboarding receipt is no longer active.", ephemeral=True)
                return
            expected_user = str(session.get("sender_id") or "")
            expected_chat = str(session.get("chat_id") or "")
            actual_user = str(getattr(interaction.user, "id", "") or "")
            actual_chat = str(getattr(interaction.channel, "id", "") or "")
            if actual_user != expected_user or actual_chat != expected_chat:
                await interaction.response.send_message("Only the onboarding recipient can confirm this.", ephemeral=True)
                return
            scrubbed_text = completion_scrubbed_text_for_session(conn, cfg, session)
            if not scrubbed_text:
                await interaction.response.send_message(
                    "I couldn't reconstruct the onboarding details to scrub them.",
                    ephemeral=True,
                )
                return
        try:
            await interaction.response.edit_message(
                content=scrubbed_text,
                view=None,
            )
        except Exception as exc:  # noqa: BLE001
            error_text = str(exc).strip() or "Failed to scrub the password."
            if interaction.response.is_done():
                await interaction.followup.send(error_text, ephemeral=True)
            else:
                await interaction.response.send_message(error_text, ephemeral=True)
            return
        with connect_db(cfg) as conn:
            completion_delivery = dict((session.get("answers") or {}).get("completion_delivery") or {})
            completion_delivery.update(
                {
                    "platform": "discord",
                    "chat_id": actual_chat,
                    "message_id": str(getattr(getattr(interaction, "message", None), "id", "") or ""),
                    "scrubbed_text": scrubbed_text,
                    "password_scrubbed": True,
                }
            )
            answers = session.get("answers", {}) if isinstance(session.get("answers"), dict) else {}
            if str(answers.get("bot_platform") or "").strip().lower() == "discord":
                session, _ = ensure_discord_agent_dm_confirmation_code(conn, session)
            followup_text = completion_followup_text_for_session(conn, cfg, session)
            followup_components = completion_followup_discord_components(
                session_id,
                agent_backup_verified=bool((session.get("answers") or {}).get("agent_backup_verified")),
            )
            session = save_onboarding_session(
                conn,
                session_id=session_id,
                answers={
                    "completion_delivery": completion_delivery,
                    "completion_secret_acknowledged_at": utc_now_iso(),
                },
            )
        if followup_text and not bool(completion_delivery.get("followup_sent")):
            try:
                delivery = discord_send_message(
                    bot_token=bot_token,
                    channel_id=actual_chat,
                    text=followup_text,
                    components=followup_components,
                )
                completion_delivery["followup_sent"] = True
                if isinstance(delivery, dict):
                    completion_delivery["followup_message_id"] = str(delivery.get("id") or "")
            except Exception:
                completion_delivery["followup_sent"] = False
            with connect_db(cfg) as conn:
                session = save_onboarding_session(
                    conn,
                    session_id=session_id,
                    answers={"completion_delivery": completion_delivery},
                )
                answers = session.get("answers", {}) if isinstance(session.get("answers"), dict) else {}
                if completion_delivery.get("followup_sent") and str(answers.get("bot_platform") or "").strip().lower() == "discord":
                    payload = {
                        "session_id": session_id,
                        "agent_id": str(session.get("linked_agent_id") or ""),
                        "recipient_id": actual_user,
                        "confirmation_code": str(answers.get("discord_agent_dm_confirmation_code") or ""),
                    }
                    request_operator_action(
                        conn,
                        action_kind="send-discord-agent-dm",
                        requested_by=f"discord:{actual_user}",
                        request_source="discord-completion-followup",
                        requested_target=json.dumps(payload, sort_keys=True),
                        dedupe_by_target=True,
                    )
                    save_onboarding_session(
                        conn,
                        session_id=session_id,
                        answers={"discord_agent_dm_requested_at": utc_now_iso()},
                    )

    await client.start(bot_token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
