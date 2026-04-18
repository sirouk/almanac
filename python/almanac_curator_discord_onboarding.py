#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import os
import sys

from almanac_control import (
    Config,
    approve_onboarding_session,
    approve_request,
    connect_db,
    deny_onboarding_session,
    deny_request,
    get_onboarding_session,
)
from almanac_discord import discord_get_current_user
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

    def _run_operator_action(*, target_id: str, action: str, actor: str, reason: str = "") -> str:
        normalized_action = action.strip().lower()
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
                    channel = client.get_channel(int(origin_chat_id))
                    if channel is None:
                        try:
                            channel = await client.fetch_channel(int(origin_chat_id))
                        except Exception:
                            channel = None
                    if channel is not None:
                        await channel.send(reply.text)
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
        if command not in {"/approve", "/deny"}:
            return False
        if len(parts) < 2:
            await message.channel.send(
                "Use /approve onb_xxx, /deny onb_xxx optional reason, /approve req_xxx, or /deny req_xxx."
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

    @tree.command(name="status", description="Show your current onboarding step.")
    async def status_command(interaction) -> None:  # type: ignore[no-untyped-def]
        await _handle_dm_command(interaction, "/status")

    @tree.command(name="cancel", description="Cancel your current onboarding session.")
    async def cancel_command(interaction) -> None:  # type: ignore[no-untyped-def]
        await _handle_dm_command(interaction, "/cancel")

    @tree.command(name="restart", description="Restart the current provider authorization step.")
    async def restart_command(interaction) -> None:  # type: ignore[no-untyped-def]
        await _handle_dm_command(interaction, "/restart")

    @tree.command(name="approve", description="Approve an onboarding session or provisioning request.")
    @app_commands.describe(target_id="onb_xxx or req_xxx")
    async def approve_command(interaction, target_id: str) -> None:  # type: ignore[no-untyped-def]
        if not await _ensure_operator_channel(interaction):
            return
        actor = _format_actor_label(interaction.user)
        await interaction.response.send_message(
            _run_operator_action(target_id=target_id.strip(), action="approve", actor=actor)
        )

    @tree.command(name="deny", description="Deny an onboarding session or provisioning request.")
    @app_commands.describe(target_id="onb_xxx or req_xxx", reason="Optional deny reason for onboarding sessions")
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

    await client.start(bot_token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
