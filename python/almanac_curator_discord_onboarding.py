#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import os
import sys

from almanac_control import Config
from almanac_discord import discord_get_current_user
from almanac_onboarding_flow import (
    OutboundMessage,
    BotIdentity,
    IncomingMessage,
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

    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)
    validator = _discord_validator(curator_bot_id)
    sync_done = False

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
