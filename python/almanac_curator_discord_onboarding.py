#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import sys

from almanac_control import Config
from almanac_discord import discord_get_current_user
from almanac_onboarding_flow import (
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
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"discord.py is required for Discord onboarding: {exc}") from exc

    intents = discord.Intents.default()
    intents.dm_messages = True
    intents.guild_messages = True

    client = discord.Client(intents=intents)
    validator = _discord_validator(curator_bot_id)

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

        replies = process_onboarding_message(
            cfg,
            IncomingMessage(
                platform="discord",
                chat_id=str(message.channel.id),
                sender_id=str(message.author.id),
                sender_username=str(getattr(message.author, "name", "") or ""),
                sender_display_name=str(getattr(message.author, "display_name", "") or ""),
                text=content,
            ),
            validate_bot_token=validator,
        )
        for reply in replies:
            if reply.chat_id == str(message.channel.id):
                await message.channel.send(reply.text)
                continue
            try:
                channel = await client.fetch_channel(int(reply.chat_id))
            except Exception:
                continue
            try:
                await channel.send(reply.text)
            except Exception:
                continue

    await client.start(bot_token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
