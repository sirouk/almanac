#!/usr/bin/env python3
from __future__ import annotations

import pwd
from pathlib import Path
from typing import Any

from almanac_agent_access import load_access_state
from almanac_control import Config, config_env_value, get_agent


def completion_ack_callback_data(session_id: str) -> str:
    return f"almanac:onboarding-complete:ack:{session_id.strip()}"


def completion_ack_telegram_markup(session_id: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [[
            {
                "text": "I recorded this safely",
                "callback_data": completion_ack_callback_data(session_id),
            }
        ]]
    }


def completion_ack_discord_components(session_id: str) -> list[dict[str, Any]]:
    return [
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 2,
                    "label": "I recorded this safely",
                    "custom_id": completion_ack_callback_data(session_id),
                }
            ],
        }
    ]


def _shared_tailnet_host() -> str:
    if config_env_value("ENABLE_TAILSCALE_SERVE", "0").strip() != "1":
        return ""
    for raw in (
        config_env_value("TAILSCALE_DNS_NAME", "").strip(),
        config_env_value("NEXTCLOUD_TRUSTED_DOMAIN", "").strip(),
    ):
        if raw:
            return raw
    return ""


def _shared_resource_lines(cfg: Config) -> list[str]:
    lines = ["Shared resources:"]
    host = _shared_tailnet_host()
    nextcloud_enabled = config_env_value("ENABLE_NEXTCLOUD", "1").strip() == "1"
    qmd_path = config_env_value("TAILSCALE_QMD_PATH", "/mcp").strip() or "/mcp"
    almanac_mcp_path = config_env_value("TAILSCALE_ALMANAC_MCP_PATH", "/almanac-mcp").strip() or "/almanac-mcp"

    if nextcloud_enabled:
        if host:
            lines.append(f"- Nextcloud vault: https://{host}/ (shared mount: /Vault)")
        else:
            lines.append("- Nextcloud vault: shared on this host (mounted as /Vault)")

    if host:
        lines.append(f"- QMD MCP: https://{host}{qmd_path}")
        lines.append(f"- Almanac MCP: https://{host}{almanac_mcp_path}")
    else:
        lines.append(f"- QMD MCP: {cfg.qmd_url}")
        lines.append(f"- Almanac MCP: http://{cfg.public_mcp_host}:{cfg.public_mcp_port}/mcp")

    if cfg.chutes_mcp_url:
        lines.append(f"- Chutes KB MCP: {cfg.chutes_mcp_url}")

    lines.append("- Notion webhook: shared operator-managed service on this host")
    return lines


def completion_message_bundle(
    cfg: Config,
    *,
    session_id: str,
    bot_reference: str,
    access: dict[str, Any],
    home: Path,
    discord_note: bool = False,
) -> dict[str, Any]:
    nextcloud_username = str(access.get("nextcloud_username") or access.get("username") or "").strip()
    base_lines = [
        f"Everything is ready. Your own bot is {bot_reference} now.",
        f"Unix user: {access.get('unix_user') or access.get('username')}",
        f"Hermes dashboard: {access.get('dashboard_url')}",
        f"Dashboard username: {access.get('username')}",
        f"Nextcloud login: {nextcloud_username} (same shared password)" if nextcloud_username else "",
        f"Code workspace: {access.get('code_url')}",
        f"Workspace root: {home}",
        *_shared_resource_lines(cfg),
        "The shared MCP endpoints are already wired into your agent by default.",
    ]
    base_lines = [line for line in base_lines if line]
    if discord_note:
        base_lines.append(
            "If Discord does not open the DM yet, use the app's Installation link from the Discord Developer Portal to add it, or place it in a server you both share, then try again."
        )
    full_lines = list(base_lines)
    full_lines.insert(4, f"Shared password: {access.get('password')}")
    full_lines.append("After you've recorded this safely, click the button below and I'll remove the password from this message.")

    scrubbed_lines = list(base_lines)
    scrubbed_lines.insert(4, "Shared password: removed after you confirmed you recorded it.")
    scrubbed_lines.append("Password removed after confirmation.")

    return {
        "full_text": "\n".join(full_lines),
        "scrubbed_text": "\n".join(scrubbed_lines),
        "telegram_reply_markup": completion_ack_telegram_markup(session_id),
        "discord_components": completion_ack_discord_components(session_id),
    }


def completion_bundle_for_session(
    conn,
    cfg: Config,
    session: dict[str, Any],
) -> dict[str, Any] | None:
    agent_id = str(session.get("linked_agent_id") or "").strip()
    session_id = str(session.get("session_id") or "").strip()
    if not agent_id or not session_id:
        return None
    agent = get_agent(conn, agent_id)
    if agent is None:
        return None

    unix_user = str(agent.get("unix_user") or "").strip()
    hermes_home = Path(str(agent.get("hermes_home") or "")).expanduser()
    access = load_access_state(hermes_home)
    if not access:
        return None

    try:
        home = Path(pwd.getpwnam(unix_user).pw_dir)
    except KeyError:
        home = hermes_home.parent.parent.parent if hermes_home.parts else Path("/")

    answers = session.get("answers", {})
    bot_platform = str(answers.get("bot_platform") or "").strip().lower()
    bot_username = str(answers.get("bot_username") or session.get("telegram_bot_username") or "").strip()
    bot_display = str(answers.get("bot_display_name") or answers.get("preferred_bot_name") or "your bot").strip() or "your bot"
    if bot_platform == "telegram":
        bot_reference = f"@{bot_username or bot_display}"
    elif bot_platform == "discord":
        bot_reference = f"`{bot_username or bot_display}`"
    else:
        bot_reference = bot_display

    return completion_message_bundle(
        cfg,
        session_id=session_id,
        bot_reference=bot_reference,
        access=access,
        home=home,
        discord_note=(bot_platform == "discord"),
    )
