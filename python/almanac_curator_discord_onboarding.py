#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import sys

from almanac_control import (
    Config,
    approve_ssot_pending_write,
    approve_onboarding_session,
    approve_request,
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
from almanac_discord import discord_get_current_user
from almanac_discord import discord_send_message
from almanac_onboarding_completion import (
    completion_followup_discord_components,
    completion_followup_text_for_session,
    completion_scrubbed_text_for_session,
    ensure_discord_agent_dm_confirmation_code,
)
from almanac_onboarding_flow import (
    OutboundMessage,
    BotIdentity,
    IncomingMessage,
    notify_session_state,
    process_onboarding_message,
    resolve_curator_discord_bot_token,
)


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

    def _operator_channel_id() -> str:
        if (cfg.operator_notify_platform or "").strip().lower() != "discord":
            return ""
        return str(cfg.operator_notify_channel_id or "").strip()

    def _claim_discord_message_once(message_id: str) -> bool:
        normalized = str(message_id or "").strip()
        if not normalized:
            return True
        key = f"curator_discord_onboarding_seen_message:{normalized}"
        with connect_db(cfg) as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                """,
                (key, "1", utc_now_iso()),
            )
            conn.commit()
            return cursor.rowcount == 1

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
                if normalized_action == "install":
                    action_row, created = request_operator_action(
                        conn,
                        action_kind="pin-upgrade",
                        requested_by=actor,
                        request_source="discord-button",
                        requested_target=target_id,
                        dedupe_by_target=True,
                    )
                    status = str(action_row.get("status") or "pending")
                    if created:
                        return "Queued pinned-component upgrade. The root maintenance loop will pick it up within about a minute."
                    if status == "running":
                        return "Pinned-component upgrade is already running."
                    return "Pinned-component upgrade is already queued."
                return f"Unknown pinned-component upgrade action: {normalized_action}"
            if normalized_action in {"install", "dismiss"}:
                if normalized_action == "dismiss":
                    upsert_setting(conn, "almanac_upgrade_last_dismissed_sha", target_id)
                    return f"Dismissed Almanac update notice for {target_id[:12]}."
                action_row, created = request_operator_action(
                    conn,
                    action_kind="upgrade",
                    requested_by=actor,
                    request_source="discord-button",
                    requested_target=target_id,
                )
                status = str(action_row.get("status") or "pending")
                if created:
                    return "Queued Almanac upgrade. The root maintenance loop will pick it up within about a minute."
                if status == "running":
                    return "Almanac upgrade is already running."
                return "Almanac upgrade is already queued."
        return f"Unknown approval target: {target_id}"

    async def _ensure_operator_channel(interaction) -> bool:  # type: ignore[no-untyped-def]
        operator_channel_id = _operator_channel_id()
        if not operator_channel_id:
            await interaction.response.send_message(
                "Discord is not configured as the primary operator control channel.",
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
        return True

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
                        try:
                            discord_send_message(
                                bot_token=bot_token,
                                channel_id=str(origin_chat_id),
                                text=reply.text,
                                components=reply.discord_components,
                            )
                        except Exception:
                            pass
                    else:
                        channel = client.get_channel(int(origin_chat_id))
                        if channel is None:
                            try:
                                channel = await client.fetch_channel(int(origin_chat_id))
                            except Exception:
                                channel = None
                        if channel is not None:
                            await channel.send(reply.text)
                continue
            if reply.discord_components:
                try:
                    discord_send_message(
                        bot_token=bot_token,
                        channel_id=str(reply.chat_id),
                        text=reply.text,
                        components=reply.discord_components,
                    )
                except Exception:
                    continue
                continue
            try:
                channel = client.get_channel(int(reply.chat_id))
                if channel is None:
                    channel = await client.fetch_channel(int(reply.chat_id))
            except Exception:
                continue
            try:
                await channel.send(reply.text)
            except Exception:
                continue

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

        parts = content.strip().split(maxsplit=2)
        command = parts[0].lower() if parts else ""
        if command in {"/retry-contact", "/retry_contact"}:
            retry_parts = content.strip().split(maxsplit=1)
            if len(retry_parts) < 2 or not retry_parts[1].strip():
                await message.channel.send("Use /retry-contact <unixusername|discordname>.")
                return True
            actor = _format_actor_label(message.author)
            try:
                with connect_db(cfg) as conn:
                    result = retry_discord_contact(
                        conn,
                        cfg,
                        target=retry_parts[1].strip(),
                        actor=actor,
                        request_source="discord-retry-contact",
                    )
                await message.channel.send(str(result.get("message") or "Queued contact retry."))
            except Exception as exc:  # noqa: BLE001
                await message.channel.send(f"Could not retry contact: {exc}")
            return True

        if command not in {"/approve", "/deny"}:
            return False
        if len(parts) < 2:
            await message.channel.send(
                "Use /approve onb_xxx, /deny onb_xxx optional reason, /approve req_xxx, /deny req_xxx, /approve ssotw_xxx, /deny ssotw_xxx optional reason, or /retry-contact <unixusername|discordname>."
            )
            return True

        target_id = parts[1].strip()
        actor = _format_actor_label(message.author)
        response = _run_operator_action(
            target_id=target_id,
            action="approve" if command == "/approve" else "deny",
            actor=actor,
            reason=parts[2].strip() if command == "/deny" and len(parts) > 2 else "",
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
    @app_commands.describe(target_id="onb_xxx, req_xxx, or ssotw_xxx")
    async def approve_command(interaction, target_id: str) -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        actor = _format_actor_label(interaction.user)
        await interaction.response.send_message(
            _run_operator_action(target_id=target_id.strip(), action="approve", actor=actor)
        )

    @tree.command(name="deny", description="Deny an onboarding session, provisioning request, or pending SSOT write.")
    @app_commands.describe(target_id="onb_xxx, req_xxx, or ssotw_xxx", reason="Optional deny reason")
    async def deny_command(interaction, target_id: str, reason: str = "") -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
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

    @tree.command(name="retry-contact", description="Retry a Discord agent-bot contact handoff.")
    @app_commands.describe(target="Operator use: Unix username, onboarding session id, Discord user id, username, or display name")
    async def retry_contact_command(interaction, target: str = "") -> None:  # type: ignore[no-untyped-def]
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

    @client.event
    async def on_ready() -> None:  # type: ignore[no-untyped-def]
        nonlocal sync_done
        if sync_done:
            return
        guild_ids_raw = str(os.environ.get("ALMANAC_CURATOR_DISCORD_COMMAND_GUILD_IDS", "") or "")
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
        if not _claim_discord_message_once(str(getattr(message, "id", "") or "")):
            return
        if await _handle_operator_channel_message(message, content):
            return
        if message.guild is not None:
            lower = content.lower()
            if lower in {"/start", "/onboard", "start", "onboard"}:
                try:
                    await message.author.send("Open a DM with me and send /start there. I only onboard in private.")
                except Exception:
                    pass
            return

        replies = await _process_discord_input(
            chat_id=str(message.channel.id),
            sender_id=str(message.author.id),
            sender_username=str(getattr(message.author, "name", "") or ""),
            sender_display_name=str(getattr(message.author, "display_name", "") or ""),
            text=content,
        )
        await _send_replies(replies=replies, origin_chat_id=str(message.channel.id))

    @client.event
    async def on_interaction(interaction) -> None:  # type: ignore[no-untyped-def]
        if interaction.type != discord.InteractionType.component:
            return
        data = getattr(interaction, "data", {}) or {}
        custom_id = str(data.get("custom_id") or "").strip()
        if (
            custom_id.startswith("almanac:upgrade:")
            or custom_id.startswith("almanac:pin-upgrade:")
            or custom_id.startswith("almanac:ssot:")
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
            actor = _format_actor_label(interaction.user)
            result_text = _run_operator_action(target_id=target_id, action=action, actor=actor, scope=scope)
            message_text = str(getattr(getattr(interaction, "message", None), "content", "") or "").strip()
            replacement = (message_text + f"\n\n{result_text} ({actor})").strip() if message_text else result_text
            await interaction.response.edit_message(content=replacement, view=None)
            return

        backup_prefix = "almanac:onboarding-complete:setup-backup:"
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

        prefix = "almanac:onboarding-complete:ack:"
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
