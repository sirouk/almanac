#!/usr/bin/env python3
from __future__ import annotations

import pwd
from pathlib import Path
from typing import Any

from almanac_agent_access import load_access_state
from almanac_control import Config, config_env_value, get_agent, get_agent_identity
from almanac_resource_map import shared_resource_lines, shared_tailnet_host


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


def _completion_delivery(session: dict[str, Any]) -> dict[str, Any]:
    answers = session.get("answers", {})
    raw = answers.get("completion_delivery") if isinstance(answers, dict) else None
    return raw if isinstance(raw, dict) else {}


def stored_completion_scrubbed_text(session: dict[str, Any]) -> str:
    return str(_completion_delivery(session).get("scrubbed_text") or "").strip()


def stored_completion_followup_text(session: dict[str, Any]) -> str:
    return str(_completion_delivery(session).get("followup_text") or "").strip()


def _shared_tailnet_host() -> str:
    return shared_tailnet_host(
        tailscale_serve_enabled=(config_env_value("ENABLE_TAILSCALE_SERVE", "0").strip() == "1"),
        tailscale_dns_name=config_env_value("TAILSCALE_DNS_NAME", "").strip(),
        nextcloud_trusted_domain=config_env_value("NEXTCLOUD_TRUSTED_DOMAIN", "").strip(),
    )


def _shared_resource_lines(cfg: Config) -> list[str]:
    host = _shared_tailnet_host()
    shared_lines = shared_resource_lines(
        host=host,
        nextcloud_enabled=(config_env_value("ENABLE_NEXTCLOUD", "1").strip() == "1"),
        qmd_url=cfg.qmd_url,
        public_mcp_host=cfg.public_mcp_host,
        public_mcp_port=cfg.public_mcp_port,
        qmd_path=config_env_value("TAILSCALE_QMD_PATH", "/mcp").strip() or "/mcp",
        almanac_mcp_path=config_env_value("TAILSCALE_ALMANAC_MCP_PATH", "/almanac-mcp").strip() or "/almanac-mcp",
        chutes_mcp_url=cfg.chutes_mcp_url,
        notion_space_url=(
            config_env_value("ALMANAC_SSOT_NOTION_ROOT_PAGE_URL", "").strip()
            or config_env_value("ALMANAC_SSOT_NOTION_SPACE_URL", "").strip()
        ),
    )
    human_lines = [
        line
        for line in shared_lines
        if not line.startswith("QMD MCP retrieval rail:")
        and not line.startswith("Almanac MCP control rail:")
    ]
    return ["Shared Almanac links:", *[f"- {line}" for line in human_lines]]


def completion_message_bundle(
    cfg: Config,
    *,
    session_id: str,
    bot_reference: str,
    access: dict[str, Any],
    home: Path,
    notion_status_line: str = "",
    notion_followup_line: str = "",
    discord_note: bool = False,
) -> dict[str, Any]:
    nextcloud_username = str(access.get("nextcloud_username") or access.get("username") or "").strip()
    first_lines = [
        f"Your lane is ready. Your own bot is {bot_reference} now.",
        f"Unix user: {access.get('unix_user') or access.get('username')}",
        notion_status_line,
        "This shared password unlocks your Almanac dashboard, code workspace, and Nextcloud when it is enabled.",
    ]
    followup_lines = [
        f"Hermes dashboard: {access.get('dashboard_url')}",
        f"Dashboard username: {access.get('username')}",
        f"Nextcloud login: {nextcloud_username} (same shared password)" if nextcloud_username else "",
        f"Code workspace: {access.get('code_url')}",
        f"Workspace root: {home}",
        *_shared_resource_lines(cfg),
        "The shared Vault and control rails are already wired into your agent by default.",
        notion_followup_line,
    ]
    first_lines = [line for line in first_lines if line]
    followup_lines = [line for line in followup_lines if line]
    if discord_note:
        followup_lines.append(
            "If Discord does not open the DM yet, use the app's Installation link from the Discord Developer Portal to add it, or place it in a server you both share, then try again."
        )
    full_lines = list(first_lines)
    full_lines.insert(2, f"Shared password: {access.get('password')}")
    full_lines.append("After you've recorded this safely, click the button below. I’ll remove the password from this message and then send the rest of your links.")

    scrubbed_lines = list(first_lines)
    scrubbed_lines.insert(2, "Shared password: removed after you confirmed you recorded it.")
    scrubbed_lines.append("Password removed after confirmation.")

    return {
        "full_text": "\n".join(full_lines),
        "scrubbed_text": "\n".join(scrubbed_lines),
        "followup_text": "\n".join(followup_lines),
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

    identity = get_agent_identity(conn, agent_id=agent_id, unix_user=unix_user) or {}
    verification_status = str(identity.get("verification_status") or "").strip()
    notion_email = str(identity.get("notion_user_email") or identity.get("claimed_notion_email") or answers.get("notion_claim_email") or "").strip()
    if verification_status == "verified":
        notion_status_line = (
            f"Shared Notion writes: enabled for {notion_email or 'your verified Notion identity'} "
            "(native Notion history shows the Almanac integration; Changed By is stamped to you on supported rows)"
        )
        notion_followup_line = ""
    elif bool(answers.get("notion_verification_skipped")):
        notion_status_line = "Shared Notion writes: read-only until you verify your Notion identity with Curator."
        notion_followup_line = "When you're ready, reply `/verify-notion` here and I'll reopen the verification step."
    else:
        notion_status_line = "Shared Notion writes: read-only until your Notion identity is verified."
        notion_followup_line = "Reply `/verify-notion` here any time you want Curator to resume that step."

    return completion_message_bundle(
        cfg,
        session_id=session_id,
        bot_reference=bot_reference,
        access=access,
        home=home,
        notion_status_line=notion_status_line,
        notion_followup_line=notion_followup_line,
        discord_note=(bot_platform == "discord"),
    )


def completion_scrubbed_text_for_session(
    conn,
    cfg: Config,
    session: dict[str, Any],
) -> str:
    stored = stored_completion_scrubbed_text(session)
    if stored:
        return stored
    bundle = completion_bundle_for_session(conn, cfg, session)
    if bundle is None:
        return ""
    return str(bundle.get("scrubbed_text") or "").strip()


def completion_followup_text_for_session(
    conn,
    cfg: Config,
    session: dict[str, Any],
) -> str:
    stored = stored_completion_followup_text(session)
    if stored:
        return stored
    bundle = completion_bundle_for_session(conn, cfg, session)
    if bundle is None:
        return ""
    return str(bundle.get("followup_text") or "").strip()
