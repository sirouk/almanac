#!/usr/bin/env python3
from __future__ import annotations

import os
import pathlib
import shlex
import sys
from typing import Any, Mapping

_PYTHON_DIR = pathlib.Path(__file__).resolve().parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from arclink_discord import DiscordConfig, register_arclink_public_discord_commands
from arclink_telegram import TelegramConfig, register_arclink_public_telegram_commands


def _load_shell_env_file(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    candidate = pathlib.Path(str(path or "")).expanduser()
    if not candidate.is_file():
        return env
    for raw_line in candidate.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        try:
            parts = shlex.split(f"VALUE={raw_value}", posix=True)
            value = parts[0].split("=", 1)[1] if parts else ""
        except ValueError:
            value = raw_value.strip().strip("'\"")
        env[key] = value
    return env


def _merged_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    merged = dict(os.environ)
    config_file = str(merged.get("ARCLINK_CONFIG_FILE") or "").strip()
    if config_file:
        for key, value in _load_shell_env_file(config_file).items():
            merged.setdefault(key, value)
    if env:
        merged.update(dict(env))
    return merged


def register_public_bot_commands(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    merged = _merged_env(env)
    results: dict[str, Any] = {"telegram": {"skipped": True}, "discord": {"skipped": True}, "errors": []}

    telegram = TelegramConfig.from_env(merged)
    if telegram.bot_token:
        try:
            results["telegram"] = register_arclink_public_telegram_commands(telegram.bot_token)
        except Exception as exc:  # noqa: BLE001 - keep registering other platforms
            results["telegram"] = {"error": str(exc)}
            results["errors"].append("telegram")

    discord = DiscordConfig.from_env(merged)
    if discord.bot_token and discord.app_id:
        try:
            results["discord"] = register_arclink_public_discord_commands(discord)
        except Exception as exc:  # noqa: BLE001 - keep the deploy flow resilient
            results["discord"] = {"error": str(exc)}
            results["errors"].append("discord")

    return results


def main() -> int:
    result = register_public_bot_commands()

    telegram = result.get("telegram") or {}
    discord = result.get("discord") or {}
    if telegram.get("skipped"):
        print("Telegram public bot actions: skipped (no bot token)")
    elif telegram.get("error"):
        print(f"Telegram public bot actions: failed ({telegram.get('error')})", file=sys.stderr)
    else:
        print(
            "Telegram public bot actions: registered "
            f"{len(telegram.get('registered') or [])} command(s) across "
            f"{', '.join(telegram.get('scopes') or [])}"
        )
    if discord.get("skipped"):
        print("Discord public bot actions: skipped (missing bot token or application ID)")
    elif discord.get("error"):
        print(f"Discord public bot actions: failed ({discord.get('error')})", file=sys.stderr)
    else:
        print(
            "Discord public bot actions: registered "
            f"{len(discord.get('registered') or [])} command(s) to {discord.get('scope')}"
        )
    return 1 if result.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
