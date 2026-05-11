#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
import secrets
import sqlite3
from typing import Any, Mapping

from arclink_api_auth import check_arclink_rate_limit, _resolve_revealable_credential_secret, _stable_handoff_id
from arclink_adapters import arclink_access_urls
from arclink_boundary import json_dumps_safe, json_loads_safe
from arclink_control import append_arclink_audit, append_arclink_event, queue_notification, utc_after_seconds_iso, utc_now_iso
from arclink_onboarding import (
    answer_arclink_onboarding_question,
    cancel_arclink_onboarding_session,
    create_or_resume_arclink_onboarding_session,
    handoff_arclink_onboarding_channel,
    open_arclink_onboarding_checkout,
)
from arclink_product import base_domain as default_base_domain
from arclink_product import chutes_default_model, launch_phrase


ARCLINK_PUBLIC_BOT_CHANNELS = frozenset({"telegram", "discord"})
ARCLINK_PUBLIC_BOT_PLANS = frozenset({"founders", "sovereign", "scale"})
ARCLINK_PUBLIC_BOT_PLAN_ALIASES = {
    "starter": "founders",
    "founder": "founders",
    "founders": "founders",
    "limited": "founders",
    "limited founders": "founders",
    "limited 100 founders": "founders",
    "operator": "sovereign",
    "sovereign": "sovereign",
    "scale": "scale",
}
ARCLINK_PUBLIC_BOT_PACKAGE_COMMANDS = frozenset({"/packages", "packages", "plans", "take me aboard", "aboard"})
ARCLINK_PUBLIC_BOT_STANDARD_PACKAGE_COMMANDS = frozenset({"/packages standard", "packages standard", "/standard-packages", "standard packages"})
ARCLINK_PUBLIC_BOT_TURN_LIMIT = 20
ARCLINK_PUBLIC_BOT_RATE_WINDOW_SECONDS = 900
ARCLINK_PUBLIC_BOT_CONNECT_NOTION_COMMANDS = frozenset(
    {"/connect-notion", "/connect_notion", "/notion", "connect-notion", "connect notion", "notion"}
)
ARCLINK_PUBLIC_BOT_CONFIG_BACKUP_COMMANDS = frozenset(
    {
        "/config-backup",
        "/config_backup",
        "config-backup",
        "config backup",
        "/setup-backup",
        "/setup_backup",
        "/backup",
        "backup",
    }
)
ARCLINK_PUBLIC_BOT_CREDENTIAL_COMMANDS = frozenset(
    {
        "/credentials",
        "/credential",
        "/show-credentials",
        "/show_credentials",
        "credentials",
        "credential",
        "show credentials",
    }
)
ARCLINK_PUBLIC_BOT_CREDENTIAL_ACK_COMMANDS = frozenset(
    {
        "/credentials-stored",
        "/credentials_stored",
        "/credential-stored",
        "/credential_stored",
        "credentials stored",
        "credential stored",
        "i stored it",
    }
)
ARCLINK_PUBLIC_BOT_HELP_COMMANDS = frozenset({"/help", "help", "commands", "/commands"})
ARCLINK_PUBLIC_BOT_CANCEL_COMMANDS = frozenset({"/cancel", "cancel", "stop"})
ARCLINK_PUBLIC_BOT_AGENTS_COMMANDS = frozenset({"/agents", "agents", "my agents", "agent roster"})
ARCLINK_PUBLIC_BOT_RAVEN_NAME_COMMANDS = (
    "/raven-name",
    "/raven_name",
    "raven-name",
    "raven_name",
    "raven name",
)
ARCLINK_PUBLIC_BOT_ADD_AGENT_COMMANDS = frozenset(
    {"/add-agent", "/add_agent", "add-agent", "add agent", "hire another agent", "add another agent"}
)
ARCLINK_PUBLIC_BOT_PAIR_CHANNEL_COMMANDS = frozenset(
    {
        "/pair-channel",
        "/pair_channel",
        "/link-channel",
        "/link_channel",
        "pair-channel",
        "pair_channel",
        "link-channel",
        "link_channel",
        "pair channel",
        "link channel",
        "pair",
        "link",
    }
)
ARCLINK_PUBLIC_BOT_UPGRADE_HERMES_COMMANDS = frozenset(
    {
        "/upgrade-hermes",
        "/upgrade_hermes",
        "/update",
        "upgrade-hermes",
        "upgrade_hermes",
        "upgrade hermes",
    }
)
ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES = frozenset({"active", "first_contacted"})
ARCLINK_PUBLIC_BOT_AGENT_SWITCH_RE = re.compile(r"^/(?:agent[-_])([a-z0-9][a-z0-9_-]{0,31})$")
ARCLINK_PUBLIC_BOT_PAIR_CODE_RE = re.compile(r"^[A-Z0-9]{6}$")
ARCLINK_PUBLIC_BOT_SHARE_ACTION_RE = re.compile(r"^/share-(approve|deny)\s+(share_[0-9a-f]{32})$")
ARCLINK_PUBLIC_BOT_RAVEN_DISPLAY_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 ._-]{0,31}$")
ARCLINK_PUBLIC_BOT_RAVEN_CONTROL_COMMANDS = frozenset({"/raven", "/arclink", "/arclink_control"})
ARCLINK_PUBLIC_BOT_RAVEN_CONTROL_FALLBACK_RE = re.compile(r"^/arclink_ops\d{0,2}$")
ARCLINK_PUBLIC_BOT_AGENT_POLICY_SUPPRESSED_COMMANDS = frozenset({"update"})
ARCLINK_PUBLIC_BOT_COMMAND_NAME_RE = re.compile(r"[^a-z0-9_]")
GITHUB_OWNER_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
PAIR_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PAIR_CODE_TTL_SECONDS = 10 * 60
ARCLINK_PUBLIC_BOT_AGENT_BRIDGE_INTRO_EVENT = "public_bot:agent_bridge_intro_sent"
ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME = "Raven"
FOUNDERS_MONTHLY_DOLLARS = 149
SOVEREIGN_MONTHLY_DOLLARS = 199
SCALE_MONTHLY_DOLLARS = 275
SOVEREIGN_AGENT_EXPANSION_MONTHLY_DOLLARS = 99
SCALE_AGENT_EXPANSION_MONTHLY_DOLLARS = 79


@dataclass(frozen=True)
class ArcLinkPublicBotAction:
    key: str
    telegram_command: str
    discord_command: str
    description: str
    discord_options: tuple[dict[str, Any], ...] = ()


ARCLINK_PUBLIC_BOT_ACTIONS: tuple[ArcLinkPublicBotAction, ...] = (
    ArcLinkPublicBotAction(
        key="start",
        telegram_command="start",
        discord_command="start",
        description="Begin your ArcLink launch path",
    ),
    ArcLinkPublicBotAction(
        key="help",
        telegram_command="help",
        discord_command="help",
        description="Open the ArcLink action palette",
    ),
    ArcLinkPublicBotAction(
        key="status",
        telegram_command="status",
        discord_command="status",
        description="Check onboarding or pod status",
    ),
    ArcLinkPublicBotAction(
        key="credentials",
        telegram_command="credentials",
        discord_command="credentials",
        description="Reveal and acknowledge your dashboard credential",
    ),
    ArcLinkPublicBotAction(
        key="name",
        telegram_command="name",
        discord_command="name",
        description="Name your ArcLink workspace",
        discord_options=(
            {
                "type": 3,
                "name": "display_name",
                "description": "Your name or team name",
                "required": True,
            },
        ),
    ),
    ArcLinkPublicBotAction(
        key="plan",
        telegram_command="plan",
        discord_command="plan",
        description="Choose Founders, Sovereign, or Scale",
        discord_options=(
            {
                "type": 3,
                "name": "tier",
                "description": "ArcLink plan",
                "required": True,
                "choices": [
                    {"name": "Limited 100 Founders", "value": "founders"},
                    {"name": "Sovereign", "value": "sovereign"},
                    {"name": "Scale", "value": "scale"},
                ],
            },
        ),
    ),
    ArcLinkPublicBotAction(
        key="checkout",
        telegram_command="checkout",
        discord_command="checkout",
        description="Hire your first ArcLink agent",
    ),
    ArcLinkPublicBotAction(
        key="agents",
        telegram_command="agents",
        discord_command="agents",
        description="Open your ArcLink crew manifest",
    ),
    ArcLinkPublicBotAction(
        key="agent",
        telegram_command="agent",
        discord_command="agent",
        description="Send a message or command to your active agent",
        discord_options=(
            {
                "type": 3,
                "name": "message",
                "description": "Message or slash command for the active agent",
                "required": True,
            },
        ),
    ),
    ArcLinkPublicBotAction(
        key="raven_name",
        telegram_command="raven_name",
        discord_command="raven-name",
        description="Set Raven's display name for this channel or account",
        discord_options=(
            {
                "type": 3,
                "name": "scope",
                "description": "Where this Raven name applies",
                "required": False,
                "choices": [
                    {"name": "This channel", "value": "channel"},
                    {"name": "Whole account", "value": "account"},
                    {"name": "Reset this channel", "value": "reset"},
                    {"name": "Reset account default", "value": "reset-account"},
                ],
            },
            {
                "type": 3,
                "name": "display_name",
                "description": "New Raven display name",
                "required": False,
            },
        ),
    ),
    ArcLinkPublicBotAction(
        key="connect_notion",
        telegram_command="connect_notion",
        discord_command="connect-notion",
        description="Connect Notion to your live pod",
    ),
    ArcLinkPublicBotAction(
        key="config_backup",
        telegram_command="config_backup",
        discord_command="config-backup",
        description="Configure private pod backup",
    ),
    ArcLinkPublicBotAction(
        key="pair_channel",
        telegram_command="pair_channel",
        discord_command="pair-channel",
        description="Pair Telegram and Discord to the same ArcLink account",
        discord_options=(
            {
                "type": 3,
                "name": "code",
                "description": "Six-character code from Raven on the other channel",
                "required": False,
            },
        ),
    ),
    ArcLinkPublicBotAction(
        key="link_channel",
        telegram_command="link_channel",
        discord_command="link-channel",
        description="Link Telegram and Discord to the same ArcLink account",
        discord_options=(
            {
                "type": 3,
                "name": "code",
                "description": "Six-character code from Raven on the other channel",
                "required": False,
            },
        ),
    ),
    ArcLinkPublicBotAction(
        key="upgrade_hermes",
        telegram_command="upgrade_hermes",
        discord_command="upgrade-hermes",
        description="Check the ArcLink-managed Hermes upgrade lane",
    ),
    ArcLinkPublicBotAction(
        key="cancel",
        telegram_command="cancel",
        discord_command="cancel",
        description="Close the active setup workflow",
    ),
)


class ArcLinkPublicBotError(ValueError):
    pass


@dataclass(frozen=True)
class ArcLinkPublicBotButton:
    label: str
    command: str = ""
    url: str = ""
    style: str = "primary"


@dataclass(frozen=True)
class ArcLinkPublicBotTurn:
    channel: str
    channel_identity: str
    session_id: str
    status: str
    current_step: str
    action: str
    reply: str
    checkout_url: str = ""
    user_id: str = ""
    deployment_id: str = ""
    bot_display_name: str = ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME
    buttons: tuple[ArcLinkPublicBotButton, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean_channel(channel: str) -> str:
    clean = str(channel or "").strip().lower()
    if clean not in ARCLINK_PUBLIC_BOT_CHANNELS:
        raise ArcLinkPublicBotError(f"unsupported ArcLink public bot channel: {clean or 'blank'}")
    return clean


def _clean_identity(identity: str) -> str:
    clean = str(identity or "").strip()
    if not clean:
        raise ArcLinkPublicBotError("ArcLink public bot channel identity is required")
    return clean


def _clean_raven_display_name(raw: str) -> str:
    clean = re.sub(r"\s+", " ", str(raw or "").strip())
    if not clean:
        return ""
    clean = clean[:32].rstrip()
    if not ARCLINK_PUBLIC_BOT_RAVEN_DISPLAY_NAME_RE.fullmatch(clean):
        raise ArcLinkPublicBotError(
            "Raven display name may use letters, numbers, spaces, dot, underscore, or hyphen"
        )
    return clean


def _public_bot_command_name(message: str) -> str:
    token = str(message or "").strip().split(maxsplit=1)[0].split("@", 1)[0]
    name = token.lower().lstrip("/").replace("-", "_")
    name = ARCLINK_PUBLIC_BOT_COMMAND_NAME_RE.sub("", name)
    return name[:32]


def _raven_control_rewrite(message: str, command: str) -> str | None:
    parts = str(message or "").strip().split(maxsplit=1)
    if not parts:
        return "/help"
    control = parts[0].lower().split("@", 1)[0]
    if control not in ARCLINK_PUBLIC_BOT_RAVEN_CONTROL_COMMANDS and not ARCLINK_PUBLIC_BOT_RAVEN_CONTROL_FALLBACK_RE.fullmatch(control):
        return None
    rest = parts[1].strip() if len(parts) > 1 else ""
    rest_parts = rest.split(maxsplit=1)
    raw_verb = rest_parts[0].strip().lower() if rest_parts else ""
    verb = raw_verb.replace("-", "_")
    tail = rest_parts[1].strip() if len(rest_parts) > 1 else ""
    if not verb or verb in {"help", "commands", "menu"}:
        return "/help"
    if verb.startswith("agent_") and len(verb) > len("agent_"):
        return f"/agent-{verb[len('agent_'):]}"
    if verb in {"agent", "agents", "crew", "roster", "manifest"}:
        return "/agents"
    if verb in {"status", "health"}:
        return "/status"
    if verb in {"credentials", "credential"}:
        return "/credentials"
    if verb in {"credentials_stored", "credential_stored", "stored"}:
        return "/credentials-stored"
    if verb in {"notion", "ssot", "connect_notion", "connect-notion"}:
        return "/connect_notion"
    if verb in {"backup", "config_backup", "config-backup"}:
        return "/config_backup"
    if verb in {"link", "pair", "channel", "link_channel", "link-channel", "pair_channel", "pair-channel"}:
        return f"/link_channel {tail}".strip()
    if verb in {"add", "add_agent", "add-agent"}:
        return "/add-agent"
    if verb in {"approve", "share_approve", "share-approve"}:
        return f"/share-approve {tail}".strip()
    if verb in {"deny", "share_deny", "share-deny"}:
        return f"/share-deny {tail}".strip()
    if verb in {"upgrade", "upgrade_hermes", "upgrade-hermes", "update"}:
        return "/upgrade_hermes"
    if verb in {"cancel", "stop"}:
        return "/cancel"
    if verb in {"name", "raven_name", "raven-name"}:
        return f"/raven_name {tail}".strip()
    return "/help"


def _raven_name_command_value(message: str, command: str) -> str | None:
    for name in ARCLINK_PUBLIC_BOT_RAVEN_NAME_COMMANDS:
        if command == name:
            return ""
        prefix = f"{name} "
        if command.startswith(prefix):
            return message[len(prefix):].strip()
    return None


def _raven_identity_user_id(
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
) -> str:
    return str((deployment or {}).get("user_id") or (session or {}).get("user_id") or "").strip()


def _raven_display_name(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None = None,
    deployment: Mapping[str, Any] | None = None,
) -> str:
    user_id = _raven_identity_user_id(session, deployment)
    channel_rows: list[sqlite3.Row] = []
    if user_id:
        channel_rows = conn.execute(
            """
            SELECT raven_display_name
            FROM arclink_public_bot_identity
            WHERE scope_kind = 'channel'
              AND LOWER(channel) = LOWER(?)
              AND channel_identity = ?
              AND user_id IN (?, '')
              AND raven_display_name != ''
            ORDER BY CASE WHEN user_id = ? THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (channel, channel_identity, user_id, user_id),
        ).fetchall()
    else:
        channel_rows = conn.execute(
            """
            SELECT raven_display_name
            FROM arclink_public_bot_identity
            WHERE scope_kind = 'channel'
              AND LOWER(channel) = LOWER(?)
              AND channel_identity = ?
              AND user_id = ''
              AND raven_display_name != ''
            LIMIT 1
            """,
            (channel, channel_identity),
        ).fetchall()
    if channel_rows:
        return str(channel_rows[0]["raven_display_name"] or ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME)

    if user_id:
        row = conn.execute(
            """
            SELECT raven_display_name
            FROM arclink_public_bot_identity
            WHERE scope_kind = 'user'
              AND user_id = ?
              AND channel = ''
              AND channel_identity = ''
              AND raven_display_name != ''
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        if row is not None:
            return str(row["raven_display_name"] or ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME)
    return ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME


def _store_raven_display_name(
    conn: sqlite3.Connection,
    *,
    scope_kind: str,
    user_id: str = "",
    channel: str = "",
    channel_identity: str = "",
    display_name: str = "",
) -> None:
    if scope_kind == "user" and not str(user_id or "").strip():
        raise ArcLinkPublicBotError("Account-scoped Raven display names require an ArcLink user id")
    now = utc_now_iso()
    if display_name:
        conn.execute(
            """
            INSERT INTO arclink_public_bot_identity (
              scope_kind, user_id, channel, channel_identity, raven_display_name, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(scope_kind, user_id, channel, channel_identity) DO UPDATE SET
              raven_display_name = excluded.raven_display_name,
              updated_at = excluded.updated_at
            """,
            (scope_kind, user_id, channel, channel_identity, display_name, now, now),
        )
    else:
        conn.execute(
            """
            DELETE FROM arclink_public_bot_identity
            WHERE scope_kind = ?
              AND user_id = ?
              AND channel = ?
              AND channel_identity = ?
            """,
            (scope_kind, user_id, channel, channel_identity),
        )
    conn.commit()


def _agent_passthrough_message(message: str, command: str) -> str | None:
    if command in {"/agent", "agent"}:
        return ""
    for prefix in ("/agent ", "agent "):
        if command.startswith(prefix):
            return str(message or "")[len(prefix) :].strip()
    return None


def _agent_bridge_channel_subject(channel: str, channel_identity: str) -> str:
    return f"{channel}:{channel_identity}"


def _agent_bridge_intro_already_sent(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM arclink_events
        WHERE subject_kind = 'public_bot_channel'
          AND subject_id = ?
          AND event_type = ?
        LIMIT 1
        """,
        (_agent_bridge_channel_subject(channel, channel_identity), ARCLINK_PUBLIC_BOT_AGENT_BRIDGE_INTRO_EVENT),
    ).fetchone()
    return row is not None


def _claim_agent_bridge_intro(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    deployment: Mapping[str, Any],
) -> bool:
    if _agent_bridge_intro_already_sent(conn, channel=channel, channel_identity=channel_identity):
        return False
    append_arclink_event(
        conn,
        subject_kind="public_bot_channel",
        subject_id=_agent_bridge_channel_subject(channel, channel_identity),
        event_type=ARCLINK_PUBLIC_BOT_AGENT_BRIDGE_INTRO_EVENT,
        metadata={
            "channel": channel,
            "channel_identity": channel_identity,
            "deployment_id": str(deployment.get("deployment_id") or ""),
            "user_id": str(deployment.get("user_id") or ""),
        },
    )
    return True


def _button(label: str, *, command: str = "", url: str = "", style: str = "primary") -> ArcLinkPublicBotButton:
    return ArcLinkPublicBotButton(label=label, command=command, url=url, style=style)


def _reply(
    session: Mapping[str, Any],
    *,
    action: str,
    reply: str,
    bot_display_name: str = ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME,
    buttons: tuple[ArcLinkPublicBotButton, ...] = (),
) -> ArcLinkPublicBotTurn:
    return ArcLinkPublicBotTurn(
        channel=str(session.get("channel") or ""),
        channel_identity=str(session.get("channel_identity") or ""),
        session_id=str(session.get("session_id") or ""),
        status=str(session.get("status") or ""),
        current_step=str(session.get("current_step") or ""),
        action=action,
        reply=reply,
        checkout_url=str(session.get("checkout_url") or ""),
        user_id=str(session.get("user_id") or ""),
        deployment_id=str(session.get("deployment_id") or ""),
        bot_display_name=bot_display_name or ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME,
        buttons=buttons,
    )


def _package_prompt_reply(
    session: Mapping[str, Any],
    *,
    greeting: str = "",
    bot_display_name: str = ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME,
    standard: bool = False,
) -> ArcLinkPublicBotTurn:
    name = str(session.get("display_name_hint") or "").strip()
    raven = bot_display_name or ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME
    header = greeting or (f"Welcome aboard, {name}." if name else f"{raven} here. ArcLink is in range.")
    if standard:
        return _reply(
            session,
            action="prompt_package",
            reply=(
                f"{header}\n\n"
                "Choose how many agents to onboard ArcLink.\n\n"
                f"Sovereign is ${SOVEREIGN_MONTHLY_DOLLARS}/month: agent onboard ArcLink.\n"
                f"Scale is ${SCALE_MONTHLY_DOLLARS}/month: agents onboard ArcLink with Federation.\n\n"
                f"Agentic Expansion after launch: Sovereign agents are ${SOVEREIGN_AGENT_EXPANSION_MONTHLY_DOLLARS}/month each; "
                f"Scale agents are ${SCALE_AGENT_EXPANSION_MONTHLY_DOLLARS}/month each."
            ),
            buttons=(
                _button(f"Sovereign - ${SOVEREIGN_MONTHLY_DOLLARS}/month", command="/plan sovereign"),
                _button(f"Scale - ${SCALE_MONTHLY_DOLLARS}/month", command="/plan scale", style="secondary"),
            ),
            bot_display_name=raven,
        )
    return _reply(
        session,
        action="prompt_package",
        reply=(
            f"{header}\n\n"
            f"Choose your ArcLink onboarding lane.\n\n"
            f"Limited 100 Founders is ${FOUNDERS_MONTHLY_DOLLARS}/month: Sovereign-equivalent access for the first 100 aboard.\n"
            f"Sovereign is ${SOVEREIGN_MONTHLY_DOLLARS}/month. Scale is ${SCALE_MONTHLY_DOLLARS}/month.\n\n"
            f"Agentic Expansion after launch starts at ${SCALE_AGENT_EXPANSION_MONTHLY_DOLLARS}/month on Scale "
            f"and ${SOVEREIGN_AGENT_EXPANSION_MONTHLY_DOLLARS}/month on Sovereign."
        ),
        buttons=(
            _button(f"Founders - ${FOUNDERS_MONTHLY_DOLLARS}/month", command="/plan founders"),
            _button("Sovereign / Scale", command="/packages standard", style="secondary"),
        ),
        bot_display_name=raven,
    )


def _turn(
    *,
    channel: str,
    channel_identity: str,
    action: str,
    reply: str,
    session: Mapping[str, Any] | None = None,
    deployment: Mapping[str, Any] | None = None,
    bot_display_name: str = ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME,
    buttons: tuple[ArcLinkPublicBotButton, ...] = (),
) -> ArcLinkPublicBotTurn:
    session = dict(session or {})
    deployment = dict(deployment or {})
    return ArcLinkPublicBotTurn(
        channel=channel,
        channel_identity=channel_identity,
        session_id=str(session.get("session_id") or ""),
        status=str(deployment.get("status") or session.get("status") or ""),
        current_step=str(session.get("current_step") or ""),
        action=action,
        reply=reply,
        checkout_url=str(session.get("checkout_url") or ""),
        user_id=str(deployment.get("user_id") or session.get("user_id") or ""),
        deployment_id=str(deployment.get("deployment_id") or session.get("deployment_id") or ""),
        bot_display_name=bot_display_name or ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME,
        buttons=buttons,
    )


def _parse_answer(text: str, prefix: str) -> str:
    _, _, value = text.partition(prefix)
    return value.strip()


def arclink_public_bot_actions() -> tuple[ArcLinkPublicBotAction, ...]:
    return ARCLINK_PUBLIC_BOT_ACTIONS


def arclink_public_bot_telegram_commands() -> list[dict[str, str]]:
    return [
        {"command": action.telegram_command, "description": action.description}
        for action in ARCLINK_PUBLIC_BOT_ACTIONS
    ]


def arclink_public_bot_discord_application_commands() -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = [
        {
            "name": "arclink",
            "type": 1,
            "description": "Talk to Raven, your ArcLink guide",
            "options": [
                {
                    "type": 3,
                    "name": "message",
                    "description": "Freeform onboarding message or command",
                    "required": True,
                }
            ],
        }
    ]
    for action in ARCLINK_PUBLIC_BOT_ACTIONS:
        payload: dict[str, Any] = {
            "name": action.discord_command,
            "type": 1,
            "description": action.description,
        }
        if action.discord_options:
            payload["options"] = [dict(item) for item in action.discord_options]
        commands.append(payload)
    return commands


def _active_raven_callback_command(command: str) -> str:
    value = str(command or "").strip()
    mapping = {
        "/help": "/raven help",
        "/commands": "/raven help",
        "/status": "/raven status",
        "/agents": "/raven agents",
        "/credentials": "/raven credentials",
        "/credentials-stored": "/raven credentials_stored",
        "/credentials_stored": "/raven credentials_stored",
        "/connect_notion": "/raven connect_notion",
        "/connect-notion": "/raven connect_notion",
        "/config_backup": "/raven config_backup",
        "/config-backup": "/raven config_backup",
        "/link_channel": "/raven link_channel",
        "/link-channel": "/raven link_channel",
        "/add-agent": "/raven add_agent",
        "/add_agent": "/raven add_agent",
        "/upgrade_hermes": "/raven upgrade_hermes",
        "/upgrade-hermes": "/raven upgrade_hermes",
        "/cancel": "/raven cancel",
    }
    if value.startswith("/agent-") or value.startswith("/agent_"):
        return f"/raven {value.lstrip('/')}"
    share_match = ARCLINK_PUBLIC_BOT_SHARE_ACTION_RE.match(value.lower())
    if share_match:
        action = "approve" if share_match.group(1) == "approve" else "deny"
        return f"/raven {action} {share_match.group(2)}"
    return mapping.get(value, value)


def arclink_public_bot_turn_telegram_reply_markup(turn: ArcLinkPublicBotTurn) -> dict[str, Any] | None:
    buttons = tuple(turn.buttons or ())
    if not buttons:
        return None
    active = turn.status in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES
    rows: list[list[dict[str, Any]]] = []
    row: list[dict[str, Any]] = []
    for button in buttons:
        payload: dict[str, Any] = {"text": button.label[:64]}
        if button.url:
            payload["url"] = button.url
        else:
            command = button.command or button.label
            if active:
                command = _active_raven_callback_command(command)
            payload["callback_data"] = f"arclink:{command}"[:64]
        row.append(payload)
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return {"inline_keyboard": rows}


def arclink_public_bot_turn_discord_components(turn: ArcLinkPublicBotTurn) -> list[dict[str, Any]]:
    buttons = tuple(turn.buttons or ())
    if not buttons:
        return []
    rows: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    for index, button in enumerate(buttons):
        payload: dict[str, Any] = {
            "type": 2,
            "label": button.label[:80],
            "style": 5 if button.url else (2 if button.style == "secondary" else 1),
        }
        if button.url:
            payload["url"] = button.url
        else:
            payload["custom_id"] = f"arclink:{button.command or button.label}"[:100]
        current.append(payload)
        if len(current) == 5 or index == len(buttons) - 1:
            rows.append({"type": 1, "components": current})
            current = []
    return rows


def _command_value(message: str, command: str, names: tuple[str, ...]) -> str | None:
    for name in names:
        prefix = f"{name} "
        if command.startswith(prefix):
            return message[len(prefix):].strip()
    return None


def _is_raven_launch_command(message: str, command: str) -> bool:
    if command in ARCLINK_PUBLIC_BOT_PACKAGE_COMMANDS or command in ARCLINK_PUBLIC_BOT_STANDARD_PACKAGE_COMMANDS:
        return True
    if command in {"checkout", "/checkout", "name", "/name", "plan", "/plan"}:
        return True
    return (
        _command_value(message, command, ("name", "/name")) is not None
        or _command_value(message, command, ("plan", "/plan")) is not None
    )


def _normalize_public_bot_plan(raw: str) -> str:
    return ARCLINK_PUBLIC_BOT_PLAN_ALIASES.get(str(raw or "").strip().lower(), "")


def _plan_label(plan: str) -> str:
    clean = str(plan or "").strip().lower()
    if clean == "scale":
        return "Scale"
    if clean == "founders":
        return "Limited 100 Founders"
    return "Sovereign"


def _plan_agent_count(plan: str) -> int:
    return 3 if str(plan or "").strip().lower() == "scale" else 1


def _plan_checkout_label(plan: str) -> str:
    clean = str(plan or "").strip().lower()
    if clean == "scale":
        return f"Hire Scale - ${SCALE_MONTHLY_DOLLARS}/month"
    if clean == "founders":
        return f"Hire Founders - ${FOUNDERS_MONTHLY_DOLLARS}/month"
    return f"Hire Sovereign - ${SOVEREIGN_MONTHLY_DOLLARS}/month"


def _checkout_price_id_for_plan(
    plan: str,
    *,
    price_id: str,
    founders_price_id: str,
    scale_price_id: str,
) -> str:
    clean = _normalize_public_bot_plan(plan) or "founders"
    checkout_price_id = str(price_id or "").strip()
    if clean == "founders" and str(founders_price_id or "").strip():
        checkout_price_id = str(founders_price_id or "").strip()
    if clean == "founders" and not checkout_price_id:
        raise ArcLinkPublicBotError("Founders checkout requires ARCLINK_FOUNDERS_PRICE_ID")
    if clean == "scale" and str(scale_price_id or "").strip():
        checkout_price_id = str(scale_price_id or "").strip()
    if clean == "scale" and not str(scale_price_id or "").strip():
        raise ArcLinkPublicBotError("Scale checkout requires ARCLINK_SCALE_PRICE_ID")
    if not checkout_price_id:
        raise ArcLinkPublicBotError("Sovereign checkout requires ARCLINK_SOVEREIGN_PRICE_ID")
    return checkout_price_id


def _open_first_agent_checkout_turn(
    conn: sqlite3.Connection,
    session: Mapping[str, Any],
    *,
    stripe_client: Any,
    selected_plan: str,
    price_id: str,
    founders_price_id: str,
    scale_price_id: str,
    base_domain: str,
    bot_display_name: str = ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME,
) -> ArcLinkPublicBotTurn:
    root = f"https://{str(base_domain or default_base_domain({})).strip().strip('/')}"
    checkout_price_id = _checkout_price_id_for_plan(
        selected_plan,
        price_id=price_id,
        founders_price_id=founders_price_id,
        scale_price_id=scale_price_id,
    )
    session = open_arclink_onboarding_checkout(
        conn,
        session_id=str(session["session_id"]),
        stripe_client=stripe_client,
        price_id=checkout_price_id,
        success_url=f"{root}/checkout/success?session={str(session['session_id'])}",
        cancel_url=f"{root}/checkout/cancel?session={str(session['session_id'])}",
        base_domain=base_domain or default_base_domain({}),
    )
    plan_label = _plan_label(selected_plan)
    return _reply(
        session,
        action="open_checkout",
        reply=(
            f"{plan_label} checkout is ready.\n\n"
            "Stage 1: finish the Stripe handoff at the link below.\n"
            "Stage 2: I watch for Stripe confirmation and report back in this same channel.\n"
            "Stage 3: once payment clears, I launch provisioning and keep you posted while Drive, Code, Terminal, memory, and health come online.\n"
            "Stage 4: when the agent is ready, I bring back the working links and credential handoff."
        ),
        buttons=(
            _button(_plan_checkout_label(selected_plan), url=str(session.get("checkout_url") or "")),
            _button("Check Status", command="/status", style="secondary"),
        ),
        bot_display_name=bot_display_name,
    )


def _pair_channel_value(message: str, command: str) -> str | None:
    if command in ARCLINK_PUBLIC_BOT_PAIR_CHANNEL_COMMANDS:
        return ""
    return _command_value(
        message,
        command,
        (
            "/pair-channel",
            "/pair_channel",
            "/link-channel",
            "/link_channel",
            "pair-channel",
            "pair_channel",
            "link-channel",
            "link_channel",
            "pair channel",
            "link channel",
            "pair",
            "link",
        ),
    )


def _normalize_pair_code(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()


def _new_pair_code() -> str:
    return "".join(secrets.choice(PAIR_CODE_ALPHABET) for _ in range(6))


def _check_public_bot_rate_limit(conn: sqlite3.Connection, *, channel: str, channel_identity: str) -> None:
    check_arclink_rate_limit(
        conn,
        scope=f"onboarding:{channel}",
        subject=channel_identity,
        limit=ARCLINK_PUBLIC_BOT_TURN_LIMIT,
        window_seconds=ARCLINK_PUBLIC_BOT_RATE_WINDOW_SECONDS,
    )


def _latest_session_for_contact(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM arclink_onboarding_sessions
        WHERE LOWER(channel) = LOWER(?)
          AND LOWER(channel_identity) = LOWER(?)
        ORDER BY
          CASE WHEN deployment_id != '' THEN 0 ELSE 1 END,
          updated_at DESC,
          created_at DESC,
          session_id DESC
        LIMIT 1
        """,
        (channel, channel_identity),
    ).fetchone()
    return dict(row) if row is not None else None


def _deployment_for_session(conn: sqlite3.Connection, session: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not session:
        return None
    session_user_id = str(session.get("user_id") or "").strip()
    active_deployment_id = str(_metadata(session).get("active_deployment_id") or "").strip()
    if active_deployment_id:
        row = conn.execute("SELECT * FROM arclink_deployments WHERE deployment_id = ?", (active_deployment_id,)).fetchone()
        if row is not None and str(row["user_id"] or "") == session_user_id:
            return dict(row)
    deployment_id = str(session.get("deployment_id") or "").strip()
    if deployment_id:
        row = conn.execute("SELECT * FROM arclink_deployments WHERE deployment_id = ?", (deployment_id,)).fetchone()
        if row is not None and str(row["user_id"] or "") == session_user_id:
            return dict(row)
    if not session_user_id:
        return None
    row = conn.execute(
        """
        SELECT *
        FROM arclink_deployments
        WHERE user_id = ?
        ORDER BY
          CASE status
            WHEN 'active' THEN 0
            WHEN 'first_contacted' THEN 1
            WHEN 'provisioning_ready' THEN 2
            WHEN 'provisioning' THEN 3
            WHEN 'provisioning_failed' THEN 4
            ELSE 5
          END,
          updated_at DESC,
          created_at DESC,
          deployment_id DESC
        LIMIT 1
        """,
        (session_user_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def _deployments_for_user(conn: sqlite3.Connection, user_id: str) -> list[dict[str, Any]]:
    clean_user_id = str(user_id or "").strip()
    if not clean_user_id:
        return []
    rows = conn.execute(
        """
        SELECT *
        FROM arclink_deployments
        WHERE user_id = ?
          AND status NOT IN ('cancelled', 'teardown_complete')
        ORDER BY
          CASE status
            WHEN 'active' THEN 0
            WHEN 'first_contacted' THEN 1
            WHEN 'provisioning_ready' THEN 2
            WHEN 'provisioning' THEN 3
            WHEN 'entitlement_required' THEN 4
            WHEN 'provisioning_failed' THEN 5
            ELSE 6
          END,
          created_at ASC,
          deployment_id ASC
        """,
        (clean_user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _agent_label(
    deployment: Mapping[str, Any],
    *,
    index: int = 0,
    conn: sqlite3.Connection | None = None,
) -> str:
    """Pick the friendliest available label for this deployment.

    Order of preference:
    1. Explicit metadata.agent_name / metadata.display_name
    2. Explicit agent_id
    3. A clean "Agent #<prefix-tail>" rather than the cryptic Title-Cased hash
    4. "Agent N" as a last resort.

    The onboarding display_name_hint is the human's name, not the agent's
    name. Reusing it here makes the roster read as if the agent were named
    after the user.
    """
    metadata = _metadata(deployment)
    candidate = str(metadata.get("agent_name") or metadata.get("display_name") or "").strip()
    if candidate:
        return candidate[:40]

    agent_id = str(deployment.get("agent_id") or "").strip()
    if agent_id:
        return agent_id[:40]
    prefix = str(deployment.get("prefix") or "").strip()
    if prefix:
        prefix_tail = prefix.rsplit("-", 1)[-1][:8]
        if prefix_tail:
            return f"Agent #{prefix_tail}"
    return f"Agent {index + 1}"


def _agent_slug(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(label or "").strip().lower()).strip("-")
    return slug or "agent"


def _metadata(row: Mapping[str, Any] | None) -> dict[str, Any]:
    return json_loads_safe(str((row or {}).get("metadata_json") or "{}"))


def _agent_command_names_from_context(
    turn_metadata: Mapping[str, Any],
    session: Mapping[str, Any] | None,
) -> set[str]:
    names: set[str] = set()
    session_meta = _metadata(session)
    for source in (turn_metadata, session_meta):
        for key in ("active_agent_command_names", "telegram_active_agent_command_names"):
            raw = source.get(key) if isinstance(source, Mapping) else None
            if isinstance(raw, (list, tuple, set)):
                for item in raw:
                    name = _public_bot_command_name(f"/{item}")
                    if name:
                        names.add(name)
    return names


def _deployment_plan_id(session: Mapping[str, Any] | None, deployment: Mapping[str, Any] | None) -> str:
    metadata = _metadata(deployment)
    plan = (
        str(metadata.get("selected_plan_id") or "").strip()
        or str((session or {}).get("selected_plan_id") or "").strip()
    )
    return _normalize_public_bot_plan(plan) or "sovereign"


def _agent_expansion_price_label(plan: str) -> str:
    return (
        f"${SCALE_AGENT_EXPANSION_MONTHLY_DOLLARS}/month"
        if _normalize_public_bot_plan(plan) == "scale"
        else f"${SOVEREIGN_AGENT_EXPANSION_MONTHLY_DOLLARS}/month"
    )


def _update_session_metadata(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    updates: Mapping[str, Any],
    clear: tuple[str, ...] = (),
) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM arclink_onboarding_sessions WHERE session_id = ?", (session_id,)).fetchone()
    if row is None:
        raise KeyError(session_id)
    payload = _metadata(dict(row))
    for key in clear:
        payload.pop(key, None)
    payload.update(dict(updates))
    conn.execute(
        """
        UPDATE arclink_onboarding_sessions
        SET metadata_json = ?, current_step = ?, updated_at = ?
        WHERE session_id = ?
        """,
        (
            json_dumps_safe(payload, label="ArcLink public bot workflow", error_cls=ArcLinkPublicBotError),
            str(payload.get("public_bot_workflow") or ""),
            utc_now_iso(),
            session_id,
        ),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM arclink_onboarding_sessions WHERE session_id = ?", (session_id,)).fetchone())


def _clear_session_workflow(conn: sqlite3.Connection, *, session_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM arclink_onboarding_sessions WHERE session_id = ?", (session_id,)).fetchone()
    if row is None:
        raise KeyError(session_id)
    payload = _metadata(dict(row))
    payload.pop("public_bot_workflow", None)
    conn.execute(
        """
        UPDATE arclink_onboarding_sessions
        SET metadata_json = ?, updated_at = ?
        WHERE session_id = ?
        """,
        (
            json_dumps_safe(payload, label="ArcLink public bot workflow", error_cls=ArcLinkPublicBotError),
            utc_now_iso(),
            session_id,
        ),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM arclink_onboarding_sessions WHERE session_id = ?", (session_id,)).fetchone())


def _deployment_context(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    session = _latest_session_for_contact(conn, channel=channel, channel_identity=channel_identity)
    return session, _deployment_for_session(conn, session)


def _raven_name_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    message: str,
    command: str,
) -> ArcLinkPublicBotTurn:
    session, deployment = _deployment_context(conn, channel=channel, channel_identity=channel_identity)
    value = _raven_name_command_value(message, command)
    user_id = _raven_identity_user_id(session, deployment)
    current = _raven_display_name(
        conn,
        channel=channel,
        channel_identity=channel_identity,
        session=session,
        deployment=deployment,
    )
    if value is None:
        value = ""
    requested = value.strip()
    if not requested:
        account_line = "Account default: not available until this channel is linked to an ArcLink account."
        if user_id:
            row = conn.execute(
                """
                SELECT raven_display_name
                FROM arclink_public_bot_identity
                WHERE scope_kind = 'user'
                  AND user_id = ?
                  AND channel = ''
                  AND channel_identity = ''
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            account_line = f"Account default: `{str(row['raven_display_name'] or 'Raven') if row else 'Raven'}`."
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="raven_name_help",
            reply=(
                "Raven display names are local to ArcLink messages; Telegram and Discord profile names stay controlled by the platform bot registration.\n\n"
                f"Current name in this channel: `{current}`.\n"
                f"{account_line}\n\n"
                "Use `/raven_name channel <name>` for this channel, `/raven_name account <name>` for all linked channels, "
                "`/raven_name reset` for this channel, or `/raven_name reset-account` for the account default."
            ),
            session=session,
            deployment=deployment,
            bot_display_name=current,
            buttons=(
                _button("Show My Crew", command="/agents", style="secondary"),
                _button("Check Status", command="/status", style="secondary"),
            ),
        )

    parts = requested.split(maxsplit=1)
    selector = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""
    scope = "channel"
    reset = False
    raw_name = requested
    if selector in {"channel", "here"}:
        raw_name = rest
    elif selector in {"account", "user", "all"}:
        scope = "user"
        raw_name = rest
    elif selector in {"reset", "default"}:
        raw_name = ""
        reset = True
    elif selector in {"reset-account", "account-reset", "reset_account"}:
        scope = "user"
        raw_name = ""
        reset = True

    if scope == "user" and not user_id:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="raven_name_account_unavailable",
            reply=(
                "Account-wide Raven display names open after this channel is linked to an ArcLink account.\n\n"
                "I can still set a channel-only name here: `/raven_name channel <name>`."
            ),
            session=session,
            deployment=deployment,
            bot_display_name=current,
            buttons=(_button("Take Me Aboard", command="/packages", style="secondary"),),
        )
    if not raw_name and not reset:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="raven_name_missing",
            reply="Send the display name after the scope, for example `/raven_name channel Raven Prime`.",
            session=session,
            deployment=deployment,
            bot_display_name=current,
        )

    display_name = _clean_raven_display_name(raw_name)
    if scope == "user":
        _store_raven_display_name(
            conn,
            scope_kind="user",
            user_id=user_id,
            display_name=display_name,
        )
    else:
        _store_raven_display_name(
            conn,
            scope_kind="channel",
            user_id=user_id,
            channel=channel,
            channel_identity=channel_identity,
            display_name=display_name,
        )
        if user_id and not display_name:
            _store_raven_display_name(
                conn,
                scope_kind="channel",
                user_id="",
                channel=channel,
                channel_identity=channel_identity,
                display_name="",
            )

    updated = _raven_display_name(
        conn,
        channel=channel,
        channel_identity=channel_identity,
        session=session,
        deployment=deployment,
    )
    if scope == "user":
        action = "raven_name_account_reset" if not display_name else "raven_name_account_set"
        reply = (
            f"Account default reset. I will show as `{updated}` unless a channel override is set."
            if not display_name
            else f"Done. Across your linked ArcLink channels I will show as `{display_name}` unless a channel override is set."
        )
    else:
        action = "raven_name_channel_reset" if not display_name else "raven_name_channel_set"
        reply = (
            f"Channel override reset. I will show as `{updated}` here."
            if not display_name
            else f"Done. In this channel I will show as `{display_name}` in ArcLink messages."
        )
    reply += "\n\nPlatform bot profile names are not changed by this local preference."
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action=action,
        reply=reply,
        session=session,
        deployment=deployment,
        bot_display_name=updated,
        buttons=(
            _button("Show My Crew", command="/agents", style="secondary"),
            _button("Check Status", command="/status", style="secondary"),
        ),
    )


def _deployment_access(deployment: Mapping[str, Any]) -> dict[str, str]:
    metadata = _metadata(deployment)
    publish_state = metadata.get("tailnet_app_publication")
    tailnet_apps_unavailable = isinstance(publish_state, Mapping) and str(publish_state.get("status") or "") == "unavailable"
    base_domain = str(deployment.get("base_domain") or metadata.get("base_domain") or "").strip().lower().strip(".")
    ingress_mode = str(metadata.get("ingress_mode") or "").strip().lower()
    if not ingress_mode:
        ingress_mode = "tailscale" if base_domain.endswith(".ts.net") else "domain"
    tailscale_dns_name = str(metadata.get("tailscale_dns_name") or base_domain).strip().lower().strip(".")
    tailscale_strategy = str(metadata.get("tailscale_host_strategy") or "path").strip().lower()
    if ingress_mode == "tailscale" and tailscale_strategy == "path":
        if tailnet_apps_unavailable:
            return {"dashboard": f"https://{tailscale_dns_name or base_domain}/u/{deployment.get('prefix') or ''}"}
        return arclink_access_urls(
            prefix=str(deployment.get("prefix") or ""),
            base_domain=base_domain,
            ingress_mode=ingress_mode,
            tailscale_dns_name=tailscale_dns_name,
            tailscale_host_strategy=tailscale_strategy,
        )
    stored_urls = metadata.get("access_urls")
    if isinstance(stored_urls, Mapping):
        safe_urls = {
            str(role): str(url).strip()
            for role, url in stored_urls.items()
            if str(role).strip() and str(url).strip().startswith("https://")
        }
        if {"dashboard", "files", "code", "hermes"} <= set(safe_urls):
            return safe_urls
        if tailnet_apps_unavailable and safe_urls.get("dashboard"):
            return {"dashboard": safe_urls["dashboard"]}
    if ingress_mode == "tailscale" and tailnet_apps_unavailable:
        return {"dashboard": f"https://{tailscale_dns_name or base_domain}/u/{deployment.get('prefix') or ''}"}
    return arclink_access_urls(
        prefix=str(deployment.get("prefix") or ""),
        base_domain=base_domain,
        ingress_mode=ingress_mode,
        tailscale_dns_name=tailscale_dns_name,
        tailscale_host_strategy=tailscale_strategy,
    )


def _notion_callback_url(deployment: Mapping[str, Any]) -> str:
    dashboard_url = str(_deployment_access(deployment).get("dashboard") or "").rstrip("/")
    return f"{dashboard_url}/notion/webhook" if dashboard_url else ""


def _dashboard_credential_row(conn: sqlite3.Connection, deployment: Mapping[str, Any]) -> dict[str, Any] | None:
    deployment_id = str(deployment.get("deployment_id") or "").strip()
    user_id = str(deployment.get("user_id") or "").strip()
    if not deployment_id or not user_id:
        return None
    now = utc_now_iso()
    metadata = _metadata(deployment)
    refs = metadata.get("secret_refs") if isinstance(metadata.get("secret_refs"), Mapping) else {}
    secret_ref = str(refs.get("dashboard_password") or f"secret://arclink/dashboard/{deployment_id}/password").strip()
    handoff_id = _stable_handoff_id(deployment_id, "dashboard_password")
    conn.execute(
        """
        INSERT INTO arclink_credential_handoffs (
          handoff_id, user_id, deployment_id, credential_kind, display_name,
          secret_ref, delivery_hint, status, created_at, updated_at
        ) VALUES (?, ?, ?, 'dashboard_password', 'Dashboard password', ?, ?, 'available', ?, ?)
        ON CONFLICT(deployment_id, credential_kind) DO UPDATE SET
          user_id = excluded.user_id,
          updated_at = excluded.updated_at
        """,
        (
            handoff_id,
            user_id,
            deployment_id,
            secret_ref,
            "Copy this dashboard password into your password manager, then confirm storage.",
            now,
            now,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM arclink_credential_handoffs WHERE handoff_id = ?", (handoff_id,)).fetchone()
    return dict(row) if row is not None else None


def _credentials_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
) -> ArcLinkPublicBotTurn:
    if deployment is None or str(deployment.get("status") or "") not in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="credentials_not_ready",
            reply=_need_finished_onboarding_reply(),
            session=session,
            deployment=deployment,
            buttons=(_button("Check Status", command="/status", style="secondary"),),
        )
    row = _dashboard_credential_row(conn, deployment)
    if row is None:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="credentials_unavailable",
            reply="I could not find the dashboard credential handoff for this deployment yet. Check status, then try `/credentials` again.",
            session=session,
            deployment=deployment,
            buttons=(_button("Check Status", command="/status", style="secondary"),),
        )
    if str(row.get("status") or "") == "removed" or str(row.get("removed_at") or "").strip():
        access = _deployment_access(deployment)
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="credentials_already_stored",
            reply=(
                "That credential handoff is already closed and removed from future responses.\n\n"
                "If you lost it, ask Raven or the operator to rotate/reissue dashboard access."
            ),
            session=session,
            deployment=deployment,
            buttons=tuple(
                button for button in (
                    _button("Open Helm", url=str(access.get("dashboard") or "")) if access.get("dashboard") else None,
                    _button("Check Status", command="/status", style="secondary"),
                )
                if button is not None
            ),
        )
    raw_secret = _resolve_revealable_credential_secret(row)
    if not raw_secret:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="credentials_secret_not_materialized",
            reply=(
                "The dashboard credential exists, but the secure secret file is not materialized on this control node yet. "
                "I will not invent it. Check status, then try `/credentials` again; if it still does not appear, the operator should rotate/reissue dashboard access."
            ),
            session=session,
            deployment=deployment,
            buttons=(_button("Check Status", command="/status", style="secondary"),),
        )
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE arclink_credential_handoffs
        SET revealed_at = CASE WHEN revealed_at = '' THEN ? ELSE revealed_at END,
            updated_at = ?
        WHERE handoff_id = ? AND user_id = ?
        """,
        (now, now, row["handoff_id"], row["user_id"]),
    )
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=str(deployment.get("deployment_id") or ""),
        event_type="public_bot:dashboard_credential_revealed",
        metadata={"channel": channel, "credential_kind": "dashboard_password"},
        commit=False,
    )
    conn.commit()
    access = _deployment_access(deployment)
    helm = str(access.get("dashboard") or "").rstrip("/")
    lines = [
        "Dashboard credential handoff.",
        "",
        "Copy this password into your password manager now. After you confirm storage, ArcLink removes the handoff from future responses.",
        "",
        f"Password: `{raw_secret}`",
    ]
    if helm:
        lines.extend(["", f"Helm: {helm}"])
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="credentials_revealed",
        reply="\n".join(lines),
        session=session,
        deployment=deployment,
        buttons=tuple(
            button for button in (
                _button("I Stored It", command="/credentials-stored"),
                _button("Open Helm", url=helm) if helm else None,
            )
            if button is not None
        ),
    )


def _credentials_stored_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
) -> ArcLinkPublicBotTurn:
    if deployment is None:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="credentials_ack_no_deployment",
            reply=_need_finished_onboarding_reply(),
            session=session,
            buttons=(_button("Check Status", command="/status", style="secondary"),),
        )
    row = _dashboard_credential_row(conn, deployment)
    if row is None:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="credentials_ack_unavailable",
            reply="I could not find an open dashboard credential handoff to close.",
            session=session,
            deployment=deployment,
            buttons=(_button("Check Status", command="/status", style="secondary"),),
        )
    user_id = str(deployment.get("user_id") or "")
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE arclink_credential_handoffs
        SET status = 'removed',
            acknowledged_at = CASE WHEN acknowledged_at = '' THEN ? ELSE acknowledged_at END,
            removed_at = CASE WHEN removed_at = '' THEN ? ELSE removed_at END,
            updated_at = ?
        WHERE handoff_id = ? AND user_id = ?
        """,
        (now, now, now, row["handoff_id"], user_id),
    )
    append_arclink_audit(
        conn,
        action="credential_handoff_acknowledged",
        actor_id=user_id,
        target_kind="credential_handoff",
        target_id=str(row["handoff_id"]),
        reason="user confirmed dashboard credential storage through Raven",
        metadata={"deployment_id": str(deployment.get("deployment_id") or ""), "credential_kind": "dashboard_password"},
        commit=False,
    )
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=str(deployment.get("deployment_id") or ""),
        event_type="credential_handoff_removed",
        metadata={"credential_kind": "dashboard_password", "user_id": user_id, "channel": channel},
        commit=False,
    )
    conn.commit()
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="credentials_stored",
        reply=(
            "Locked in. I removed that dashboard credential handoff from future ArcLink responses.\n\n"
            "Next clean moves: open Helm, wire Notion, or set private backups."
        ),
        session=session,
        deployment=deployment,
        buttons=(
            _button("Wire Notion", command="/connect_notion", style="secondary"),
            _button("Check Status", command="/status", style="secondary"),
        ),
    )


def _credential_handoffs_confirmed_for_setup(
    conn: sqlite3.Connection,
    deployment: Mapping[str, Any],
) -> tuple[bool, dict[str, Any]]:
    deployment_id = str(deployment.get("deployment_id") or "").strip()
    user_id = str(deployment.get("user_id") or "").strip()
    if not deployment_id or not user_id:
        return False, {"reason": "missing_deployment_identity", "pending": []}
    rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT credential_kind, display_name, status, acknowledged_at, removed_at
            FROM arclink_credential_handoffs
            WHERE deployment_id = ? AND user_id = ?
            ORDER BY credential_kind
            """,
            (deployment_id, user_id),
        ).fetchall()
    ]
    if not rows:
        return False, {"reason": "not_started", "pending": ["credential handoff"], "removed": []}
    pending = [
        str(row.get("display_name") or row.get("credential_kind") or "credential").strip()
        for row in rows
        if str(row.get("status") or "").strip() != "removed" and not str(row.get("removed_at") or "").strip()
    ]
    removed = [
        str(row.get("display_name") or row.get("credential_kind") or "credential").strip()
        for row in rows
        if str(row.get("status") or "").strip() == "removed" or str(row.get("removed_at") or "").strip()
    ]
    return not pending, {"reason": "pending" if pending else "confirmed", "pending": pending, "removed": removed}


def _credential_handoff_required_turn(
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any],
    deployment: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> ArcLinkPublicBotTurn:
    access = _deployment_access(deployment)
    helm = str(access.get("dashboard") or "").rstrip("/")
    pending = [item for item in summary.get("pending", []) if str(item).strip()]
    pending_line = ", ".join(str(item) for item in pending) if pending else "credential handoff"
    lines = [
        "I need the credential handoff closed before I open Notion setup.",
        "",
        f"Still waiting on: {pending_line}.",
        "",
        "Use `/credentials`, copy the dashboard password into your password manager, and confirm storage. After ArcLink removes that handoff from future responses, I can record the brokered SSOT setup intent.",
        "",
        "This keeps Notion setup on the dashboard/operator verification rail. No Notion tokens or API keys belong in chat.",
    ]
    if helm:
        lines.insert(3, f"Helm: {helm}")
        lines.insert(4, "")
    buttons: list[ArcLinkPublicBotButton] = []
    if helm:
        buttons.append(_button("Open Helm", url=helm))
    buttons.append(_button("Credentials", command="/credentials", style="secondary"))
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="connect_notion_credentials_required",
        reply="\n".join(lines),
        session=session,
        deployment=deployment,
        buttons=tuple(buttons),
    )


def _aboard_freeform_reply(
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any],
    bot_display_name: str = ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME,
    conn: sqlite3.Connection | None = None,
    source_kind: str = "chat",
    include_bridge_intro: bool = False,
) -> ArcLinkPublicBotTurn:
    """Queue a public-channel message or command for the selected agent.

    Raven-owned slash commands are handled before this function. Anything that
    reaches here belongs to the selected agent and is processed asynchronously
    so Telegram/Discord webhook handlers do not block on model runtime.
    """
    label = _agent_label(deployment, index=0, conn=conn)
    raven = bot_display_name or ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME
    access = _deployment_access(deployment)
    helm = str(access.get("dashboard") or "").rstrip("/")
    if conn is not None:
        extra = {
            "deployment_id": str(deployment.get("deployment_id") or ""),
            "prefix": str(deployment.get("prefix") or ""),
            "user_id": str(deployment.get("user_id") or ""),
            "agent_label": label,
            "raven_display_name": raven,
            "helm_url": helm,
            "source_kind": source_kind,
        }
        reply_to_message_id = str(deployment.get("_public_bot_reply_to_message_id") or "").strip()
        if channel == "telegram" and reply_to_message_id:
            extra["telegram_reply_to_message_id"] = reply_to_message_id
        if channel == "discord":
            turn_metadata = deployment.get("_public_bot_metadata")
            if isinstance(turn_metadata, Mapping):
                for key in ("discord_channel_id", "discord_user_id", "discord_message_id", "discord_chat_type"):
                    value = str(turn_metadata.get(key) or "").strip()
                    if value:
                        extra[key] = value
            if reply_to_message_id and "discord_message_id" not in extra:
                extra["discord_message_id"] = reply_to_message_id
        queue_notification(
            conn,
            target_kind="public-agent-turn",
            target_id=channel_identity,
            channel_kind=channel,
            message=str(deployment.get("_public_bot_message") or ""),
            extra=extra,
        )
        append_arclink_event(
            conn,
            subject_kind="deployment",
            subject_id=str(deployment.get("deployment_id") or ""),
            event_type="public_bot:agent_turn_queued",
            metadata={"channel": channel, "agent_label": label, "source_kind": source_kind},
        )
    lines: list[str] = []
    if include_bridge_intro:
        lines.extend(
            [
                f"From now on, your normal messages in this channel will be routed to your active agent, **{label}**.",
                "Use `/raven` any time for ArcLink controls and agent selection. Bare slash commands belong to the agent at the helm.",
                "",
            ]
        )
    if include_bridge_intro:
        lines.extend(
            [
                "Your active agent replies here. Raven controls stay behind `/raven`; bare slash commands belong to the agent at the helm.",
            ]
        )
        if helm:
            lines.extend(["", f"Helm stays open too: {helm}"])
    buttons: list[ArcLinkPublicBotButton] = []
    if include_bridge_intro and helm:
        buttons.append(_button("Open Helm", url=helm))
    if include_bridge_intro:
        buttons.append(_button("Show My Crew", command="/agents", style="secondary"))
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="agent_message_queued",
        reply="\n".join(lines),
        session=session,
        deployment=deployment,
        bot_display_name=raven,
        buttons=tuple(buttons),
    )


def _need_finished_onboarding_reply() -> str:
    return (
        "That lane opens once your first agent is awake aboard ArcLink. Send `/start` and I will walk you through onboarding, "
        "or finish checkout if your launch is already in motion."
    )


def _deployment_not_ready_reply(deployment: Mapping[str, Any]) -> str:
    status = str(deployment.get("status") or "unknown").strip()
    phrase = launch_phrase(status)
    if status == "entitlement_required":
        return (
            f"{phrase} Stripe has not cleared the handoff yet - send `checkout` and I will reopen the gate."
        )
    if status == "provisioning_failed":
        return f"{phrase} I'll come back to you on this same channel the moment the lane is safe again."
    return f"{phrase} I will move when it reaches active - not before."


def _record_bot_action(
    conn: sqlite3.Connection,
    *,
    deployment: Mapping[str, Any],
    action: str,
    channel: str,
    channel_identity: str,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    deployment_id = str(deployment.get("deployment_id") or "").strip()
    if not deployment_id:
        return
    payload = {
        "action": action,
        "channel": channel,
        "channel_identity": channel_identity,
    }
    payload.update(dict(metadata or {}))
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=deployment_id,
        event_type=f"public_bot:{action}",
        metadata=payload,
    )


def _create_pair_channel_code(
    conn: sqlite3.Connection,
    *,
    session: Mapping[str, Any],
    deployment: Mapping[str, Any] | None,
) -> tuple[str, str]:
    session_id = str(session.get("session_id") or "").strip()
    if not session_id:
        raise ArcLinkPublicBotError("pair-channel requires an onboarding session")
    now = utc_now_iso()
    expires_at = utc_after_seconds_iso(PAIR_CODE_TTL_SECONDS)
    conn.execute(
        """
        UPDATE arclink_channel_pairing_codes
        SET status = 'superseded'
        WHERE source_session_id = ?
          AND status = 'open'
        """,
        (session_id,),
    )
    for _ in range(24):
        code = _new_pair_code()
        try:
            conn.execute(
                """
                INSERT INTO arclink_channel_pairing_codes (
                  code, source_session_id, source_channel, source_channel_identity,
                  user_id, deployment_id, status, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?)
                """,
                (
                    code,
                    session_id,
                    str(session.get("channel") or ""),
                    str(session.get("channel_identity") or ""),
                    str((deployment or {}).get("user_id") or session.get("user_id") or ""),
                    str((deployment or {}).get("deployment_id") or session.get("deployment_id") or ""),
                    now,
                    expires_at,
                ),
            )
            conn.commit()
            return code, expires_at
        except sqlite3.IntegrityError:
            continue
    raise ArcLinkPublicBotError("could not mint an ArcLink pair-channel code")


def _pair_channel_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any],
    deployment: Mapping[str, Any] | None,
    code_value: str,
    bot_display_name: str = ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME,
) -> ArcLinkPublicBotTurn:
    raven = bot_display_name or ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME
    clean_code = _normalize_pair_code(code_value)
    if not clean_code:
        code, expires_at = _create_pair_channel_code(conn, session=session, deployment=deployment)
        updated = _update_session_metadata(
            conn,
            session_id=str(session["session_id"]),
            updates={
                "public_bot_workflow": "pair_channel",
                "pair_channel_code": code,
                "pair_channel_expires_at": expires_at,
            },
        )
        live_note = (
            "If your agent is already online, the other channel gets the same ArcLink identity, crew, tools, vault, Notion lane, and status. "
            "The chat session stays separate; ArcLink links both channels to the same agent account."
            if deployment
            else "If you are still prelaunch, the other channel joins this same launch path."
        )
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="pair_channel_code",
            reply=(
                "Pairing lane open.\n\n"
                f"On the other channel, tell {raven}: `/link-channel {code}`\n\n"
                f"This code expires in 10 minutes. {live_note}"
            ),
            session=updated,
            deployment=deployment,
            bot_display_name=raven,
            buttons=(
                _button("Show My Crew", command="/agents", style="secondary"),
                _button("Check Status", command="/status", style="secondary"),
            ),
        )

    if not ARCLINK_PUBLIC_BOT_PAIR_CODE_RE.fullmatch(clean_code):
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="pair_channel_invalid_code",
            reply="That pairing code does not look right. Open `/link-channel` on the other channel and send me the six-character code it gives you.",
            session=session,
            deployment=deployment,
            bot_display_name=raven,
            buttons=(_button("Try Again", command="/link-channel", style="secondary"),),
        )

    row = conn.execute(
        """
        SELECT *
        FROM arclink_channel_pairing_codes
        WHERE code = ?
          AND status = 'open'
        """,
        (clean_code,),
    ).fetchone()
    now = utc_now_iso()
    if row is None or str(row["expires_at"] or "") < now:
        if row is not None:
            conn.execute("UPDATE arclink_channel_pairing_codes SET status = 'expired' WHERE code = ?", (clean_code,))
            conn.commit()
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="pair_channel_expired",
            reply="That pairing code has gone cold. Open `/link-channel` on the first channel and I will mint a fresh one.",
            session=session,
            deployment=deployment,
            bot_display_name=raven,
            buttons=(_button("Open Pairing", command="/link-channel", style="secondary"),),
        )
    source_channel = str(row["source_channel"] or "")
    source_identity = str(row["source_channel_identity"] or "")
    if source_channel == channel and source_identity == channel_identity:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="pair_channel_same_channel",
            reply="You are holding that code in the channel that minted it. Take it to the other channel and I will bridge the identity there.",
            session=session,
            deployment=deployment,
            bot_display_name=raven,
        )

    source_user_id = str(row["user_id"] or "").strip()
    source_deployment_id = str(row["deployment_id"] or "").strip()
    target_user_id = str(session.get("user_id") or "").strip()
    target_deployment_id = str(session.get("deployment_id") or "").strip()
    if target_user_id:
        target_is_other_account = not source_user_id or target_user_id != source_user_id
    else:
        target_is_other_account = bool(
            target_deployment_id
            and (not source_deployment_id or target_deployment_id != source_deployment_id)
        )
    if target_is_other_account:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="pair_channel_account_mismatch",
            reply=(
                "That channel is already linked to a different ArcLink account. "
                "Open `/link-channel` from the account you want to use, or continue in the original channel."
            ),
            session=session,
            deployment=deployment,
            bot_display_name=raven,
            buttons=(_button("Show My Crew", command="/agents", style="secondary"),),
        )

    target = handoff_arclink_onboarding_channel(
        conn,
        source_session_id=str(row["source_session_id"]),
        target_channel=channel,
        target_channel_identity=channel_identity,
    )
    source = conn.execute("SELECT * FROM arclink_onboarding_sessions WHERE session_id = ?", (str(row["source_session_id"]),)).fetchone()
    source_meta = _metadata(dict(source or {}))
    target_updates: dict[str, Any] = {
        "paired_from_session_id": str(row["source_session_id"]),
        "paired_from_channel": source_channel,
        "paired_from_channel_identity": source_identity,
        "paired_at": now,
    }
    active_deployment_id = str(source_meta.get("active_deployment_id") or row["deployment_id"] or target.get("deployment_id") or "")
    if active_deployment_id:
        target_updates["active_deployment_id"] = active_deployment_id
    target = _update_session_metadata(
        conn,
        session_id=str(target["session_id"]),
        updates=target_updates,
        clear=("public_bot_workflow", "pair_channel_code", "pair_channel_expires_at"),
    )
    _update_session_metadata(
        conn,
        session_id=str(row["source_session_id"]),
        updates={
            "paired_to_session_id": str(target["session_id"]),
            "paired_to_channel": channel,
            "paired_to_channel_identity": channel_identity,
            "paired_at": now,
        },
        clear=("public_bot_workflow", "pair_channel_code", "pair_channel_expires_at"),
    )
    conn.execute(
        """
        UPDATE arclink_channel_pairing_codes
        SET status = 'claimed',
            claimed_session_id = ?,
            claimed_channel = ?,
            claimed_channel_identity = ?,
            claimed_at = ?
        WHERE code = ?
        """,
        (str(target["session_id"]), channel, channel_identity, now, clean_code),
    )
    conn.commit()
    linked_deployment = _deployment_for_session(conn, target)
    if linked_deployment:
        _record_bot_action(
            conn,
            deployment=linked_deployment,
            action="pair_channel_claimed",
            channel=channel,
            channel_identity=channel_identity,
            metadata={"source_channel": source_channel, "target_session_id": str(target["session_id"])},
        )
    buttons: list[ArcLinkPublicBotButton] = [_button("Show My Crew", command="/agents", style="secondary")]
    access = _deployment_access(linked_deployment or {}) if linked_deployment else {}
    if access.get("dashboard"):
        buttons.insert(0, _button("Open Helm", url=str(access["dashboard"])))
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="pair_channel_claimed",
        reply=(
            "Channels paired.\n\n"
            "Same ArcLink identity, same crew, same tools, same vault, same Notion rail. "
            f"Telegram and Discord keep separate chat threads, but {raven} is now looking at the same ArcLink account."
        ),
        session=target,
        deployment=linked_deployment,
        bot_display_name=raven,
        buttons=tuple(buttons),
    )


def _connect_notion_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
) -> ArcLinkPublicBotTurn:
    if not session or not deployment:
        return _turn(channel=channel, channel_identity=channel_identity, action="connect_notion_unavailable", reply=_need_finished_onboarding_reply(), session=session)
    if str(deployment.get("status") or "") not in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="connect_notion_blocked",
            reply=_deployment_not_ready_reply(deployment),
            session=session,
            deployment=deployment,
        )
    confirmed, summary = _credential_handoffs_confirmed_for_setup(conn, deployment)
    if not confirmed:
        _record_bot_action(
            conn,
            deployment=deployment,
            action="connect_notion_credentials_required",
            channel=channel,
            channel_identity=channel_identity,
            metadata={"credential_handoff_status": str(summary.get("reason") or "unknown")},
        )
        return _credential_handoff_required_turn(
            channel=channel,
            channel_identity=channel_identity,
            session=session,
            deployment=deployment,
            summary=summary,
        )
    callback_url = _notion_callback_url(deployment)
    session = _update_session_metadata(
        conn,
        session_id=str(session["session_id"]),
        updates={
            "public_bot_workflow": "connect_notion",
            "connect_notion_requested_at": utc_now_iso(),
            "connect_notion_public_status": "awaiting_user_setup",
        },
    )
    _record_bot_action(
        conn,
        deployment=deployment,
        action="connect_notion_requested",
        channel=channel,
        channel_identity=channel_identity,
        metadata={
            "deployment_status": str(deployment.get("status") or ""),
            "setup_mode": "public_preparation_only",
        },
    )
    lines = [
        "Opening the Notion SSOT preparation lane for your ArcLink account.",
        "",
        "Current model: ArcLink uses a brokered shared-root Notion SSOT rail with dashboard/operator verification. This command records setup intent and callback only; it does not verify the Notion integration, install secrets, support user-owned OAuth, or bypass the verification rail.",
        "",
        "Drop this callback into the Notion webhook/subscription panel:",
        callback_url or "(callback URL is not available yet)",
        "",
        "Then share the page or database with the ArcLink integration. Email sharing alone is not treated as proof of API access. No tokens in chat - when I need a secret, the secure dashboard field is the only door.",
        "",
        "Send `ready` after you finish the Notion-side setup. I will mark it ready for dashboard verification, or send `cancel` and I will seal the lane.",
    ]
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="connect_notion",
        reply="\n".join(lines),
        session=session,
        deployment=deployment,
    )


def _config_backup_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
) -> ArcLinkPublicBotTurn:
    if not session or not deployment:
        return _turn(channel=channel, channel_identity=channel_identity, action="config_backup_unavailable", reply=_need_finished_onboarding_reply(), session=session)
    if str(deployment.get("status") or "") not in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="config_backup_blocked",
            reply=_deployment_not_ready_reply(deployment),
            session=session,
            deployment=deployment,
        )
    session = _update_session_metadata(
        conn,
        session_id=str(session["session_id"]),
        updates={
            "public_bot_workflow": "config_backup_repo",
            "config_backup_requested_at": utc_now_iso(),
            "config_backup_public_status": "awaiting_private_repo",
        },
    )
    _record_bot_action(
        conn,
        deployment=deployment,
        action="config_backup_requested",
        channel=channel,
        channel_identity=channel_identity,
        metadata={
            "deployment_status": str(deployment.get("status") or ""),
            "setup_mode": "public_preparation_only",
        },
    )
    example = f"{str(deployment.get('user_id') or 'you').replace('_', '-')}/arclink-{str(deployment.get('prefix') or 'pod')}"
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="prompt_backup_repo",
        reply=(
            "Opening the private backup preparation lane.\n\n"
            "This public command records the intended private GitHub repository. It does not mint, install, or verify the deploy key; the dashboard/operator backup rail completes that step.\n\n"
            "Choose a private GitHub repository - this is where Hermes' home and the pod's configuration snapshots will rest after key setup is verified. "
            "Send me `owner/repo` and I will attach it to this deployment as pending setup.\n\n"
            f"Example: `{example}`\n\n"
            "Use a dedicated deploy key for this pod. The ArcLink upstream key and the arclink-priv backup key stay where they are."
        ),
        session=session,
        deployment=deployment,
    )


def _agents_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
) -> ArcLinkPublicBotTurn:
    if not session or not deployment:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="agents_unavailable",
            reply=(
                f"No crew on your manifest yet. Limited 100 Founders brings Sovereign-equivalent access for ${FOUNDERS_MONTHLY_DOLLARS}/month. "
                f"Sovereign is ${SOVEREIGN_MONTHLY_DOLLARS}/month. Scale launches three agents with Federation for ${SCALE_MONTHLY_DOLLARS}/month."
            ),
            session=session,
            buttons=(
                _button("Take Me Aboard", command="/packages"),
            ),
        )
    user_id = str(deployment.get("user_id") or session.get("user_id") or "").strip()
    deployments = _deployments_for_user(conn, user_id)
    active_id = str(deployment.get("deployment_id") or "")
    buttons: list[ArcLinkPublicBotButton] = []
    lines = [
        "Your ArcLink crew",
        "",
        "I keep this roster sealed to you. Every agent below carries its own pod, memory rail, tool lane, vault access, and system health - all bound to your account, no one else's.",
        "",
    ]
    for index, item in enumerate(deployments):
        label = _agent_label(item, index=index, conn=conn)
        status = str(item.get("status") or "unknown")
        marker = "active" if str(item.get("deployment_id") or "") == active_id else status
        lines.append(f"- {label}: {marker}")
        if str(item.get("deployment_id") or "") != active_id:
            buttons.append(_button(f"Take Helm: {label}", command=f"/agent-{_agent_slug(label)}"))
    if deployments:
        buttons.append(_button("Add Agent", command="/add-agent"))
    if not buttons and deployments:
        buttons.append(_button("Add Agent", command="/add-agent"))
    if len(buttons) > 2:
        add_buttons = [button for button in buttons if button.command == "/add-agent"]
        helm_buttons = [button for button in buttons if button.command != "/add-agent"]
        buttons = (helm_buttons[:1] + add_buttons[:1]) or buttons[:2]
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="show_agents",
        reply="\n".join(lines),
        session=session,
        deployment=deployment,
        buttons=tuple(buttons),
    )


def _switch_agent_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    requested_slug: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
) -> ArcLinkPublicBotTurn:
    if not session or not deployment:
        return _turn(channel=channel, channel_identity=channel_identity, action="switch_agent_unavailable", reply=_need_finished_onboarding_reply(), session=session)
    deployments = _deployments_for_user(conn, str(deployment.get("user_id") or ""))
    requested = str(requested_slug or "").strip().lower()
    for index, item in enumerate(deployments):
        label = _agent_label(item, index=index, conn=conn)
        if requested in {_agent_slug(label), _agent_slug(str(item.get("prefix") or "")), _agent_slug(str(item.get("agent_id") or ""))}:
            updated = _update_session_metadata(
                conn,
                session_id=str(session["session_id"]),
                updates={"active_deployment_id": str(item.get("deployment_id") or ""), "active_agent_label": label},
            )
            return _turn(
                channel=channel,
                channel_identity=channel_identity,
                action="switch_agent",
                reply=f"Focus moved. {label} is on the rail. Notion, backup, and status lanes will route to that agent until you choose another.",
                session=updated,
                deployment=item,
                buttons=(
                    _button("Show My Crew", command="/agents", style="secondary"),
                    _button("Check Status", command="/status", style="secondary"),
                ),
            )
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="switch_agent_not_found",
        reply="That name is not on your ArcLink roster. Open `/agents` and take the helm from the buttons I build for your account.",
        session=session,
        deployment=deployment,
        buttons=(_button("Show My Crew", command="/agents"),),
    )


def _add_agent_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
    stripe_client: Any | None,
    additional_agent_price_id: str,
    sovereign_agent_expansion_price_id: str = "",
    scale_agent_expansion_price_id: str = "",
    base_domain: str = "",
) -> ArcLinkPublicBotTurn:
    if not session or not deployment:
        return _turn(channel=channel, channel_identity=channel_identity, action="add_agent_unavailable", reply=_need_finished_onboarding_reply(), session=session)
    if str(deployment.get("status") or "") not in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="add_agent_blocked",
            reply=_deployment_not_ready_reply(deployment),
            session=session,
            deployment=deployment,
        )
    if stripe_client is None:
        raise ArcLinkPublicBotError("additional agent checkout requires an injected Stripe client")
    plan = _deployment_plan_id(session, deployment)
    expansion_label = _agent_expansion_price_label(plan)
    if plan == "scale":
        price_id = str(scale_agent_expansion_price_id or additional_agent_price_id or "").strip()
    else:
        price_id = str(sovereign_agent_expansion_price_id or additional_agent_price_id or "").strip()
    if not price_id:
        raise ArcLinkPublicBotError("Agentic Expansion checkout requires a configured expansion Stripe price")

    user_id = str(deployment.get("user_id") or session.get("user_id") or "").strip()
    root = f"https://{str(base_domain or default_base_domain({})).strip().strip('/')}"
    add_token = secrets.token_hex(10)
    extra_identity = f"{channel_identity}#add:{add_token}"
    extra_session = create_or_resume_arclink_onboarding_session(
        conn,
        channel=channel,
        channel_identity=extra_identity,
        session_id=f"onb_add_{add_token}",
        display_name_hint=str(session.get("display_name_hint") or ""),
        selected_plan_id=f"agent_expansion_{plan}",
        selected_model_id=chutes_default_model({}),
        current_step="additional_agent",
        metadata={
            "purchase_kind": "additional_agent",
            "agent_expansion_plan_id": plan,
            "agent_expansion_monthly_price": expansion_label,
            "public_channel_identity": channel_identity,
            "parent_deployment_id": str(deployment.get("deployment_id") or ""),
            "parent_session_id": str(session.get("session_id") or ""),
            "active_deployment_id": str(deployment.get("deployment_id") or ""),
        },
        force_new=True,
    )
    conn.execute(
        """
        UPDATE arclink_onboarding_sessions
        SET user_id = ?, updated_at = ?
        WHERE session_id = ?
        """,
        (user_id, utc_now_iso(), str(extra_session["session_id"])),
    )
    conn.commit()
    extra_session = open_arclink_onboarding_checkout(
        conn,
        session_id=str(extra_session["session_id"]),
        stripe_client=stripe_client,
        price_id=price_id,
        success_url=f"{root}/checkout/success?kind=additional_agent&session={str(extra_session['session_id'])}",
        cancel_url=f"{root}/checkout/cancel?kind=additional_agent&session={str(extra_session['session_id'])}",
        base_domain=base_domain or default_base_domain({}),
    )
    return _reply(
        extra_session,
        action="open_add_agent_checkout",
        reply=(
            f"Agentic Expansion for your {_plan_label(plan)} plan is {expansion_label}. "
            "Clear the Stripe handoff and I will move the new agent into the launch queue with the rest of your crew."
        ),
        buttons=(
            _button(f"Hire Agent - {expansion_label}", url=str(extra_session.get("checkout_url") or "")),
            _button("Back To My Crew", command="/agents", style="secondary"),
        ),
    )


def _share_grant_action_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    requested_action: str,
    grant_id: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
) -> ArcLinkPublicBotTurn:
    if not session or not str(session.get("user_id") or "").strip():
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="share_grant_unavailable",
            reply="I cannot approve a share from this channel until it is linked to your ArcLink account.",
            session=session,
            deployment=deployment,
            buttons=(_button("Link Channel", command="/link-channel", style="secondary"),),
        )
    owner_user = str(session.get("user_id") or "").strip()
    row = conn.execute("SELECT * FROM arclink_share_grants WHERE grant_id = ?", (grant_id,)).fetchone()
    if row is None or str(row["owner_user_id"] or "") != owner_user:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="share_grant_not_found",
            reply="I cannot find a pending share approval for this ArcLink account.",
            session=session,
            deployment=deployment,
            buttons=(_button("Show My Crew", command="/agents", style="secondary"),),
        )
    grant = dict(row)
    current_status = str(grant.get("status") or "")
    label = str(grant.get("display_name") or grant.get("resource_path") or "linked resource")
    if current_status != "pending_owner_approval":
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="share_grant_noop",
            reply=f"No change made. `{label}` is already `{current_status or 'unknown'}`.",
            session=session,
            deployment=deployment,
            buttons=(_button("Show My Crew", command="/agents", style="secondary"),),
        )

    now = utc_now_iso()
    if requested_action == "approve":
        new_status = "approved"
        sql = """
            UPDATE arclink_share_grants
            SET status = 'approved', approved_at = ?, updated_at = ?
            WHERE grant_id = ? AND owner_user_id = ? AND status = 'pending_owner_approval'
        """
        params = (now, now, grant_id, owner_user)
        audit_action = "share_grant_approved"
        reply = (
            f"Approved. `{label}` is ready for the recipient to accept as a read-only Linked resource. "
            "They still cannot reshare it from their account."
        )
        turn_action = "share_grant_approved"
    else:
        new_status = "denied"
        sql = """
            UPDATE arclink_share_grants
            SET status = 'denied', updated_at = ?
            WHERE grant_id = ? AND owner_user_id = ? AND status = 'pending_owner_approval'
        """
        params = (now, grant_id, owner_user)
        audit_action = "share_grant_denied"
        reply = f"Denied. `{label}` stays closed and will not appear in the recipient's Linked resources."
        turn_action = "share_grant_denied"
    cursor = conn.execute(sql, params)
    if cursor.rowcount != 1:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="share_grant_noop",
            reply=f"No change made. `{label}` is no longer awaiting owner approval.",
            session=session,
            deployment=deployment,
        )
    append_arclink_audit(
        conn,
        action=audit_action,
        actor_id=owner_user,
        target_kind="share_grant",
        target_id=grant_id,
        reason=f"owner {new_status} linked resource share via Raven",
        metadata={"channel": channel, "resource_root": str(grant.get("resource_root") or ""), "resource_path": str(grant.get("resource_path") or "")},
        commit=False,
    )
    append_arclink_event(
        conn,
        subject_kind="share_grant",
        subject_id=grant_id,
        event_type=f"public_bot:{audit_action}",
        metadata={"channel": channel, "owner_user_id": owner_user},
        commit=False,
    )
    conn.commit()
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action=turn_action,
        reply=reply,
        session=session,
        deployment=deployment,
        buttons=(_button("Show My Crew", command="/agents", style="secondary"),),
    )


def _handle_active_workflow(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    message: str,
    command: str,
) -> ArcLinkPublicBotTurn | None:
    session, deployment = _deployment_context(conn, channel=channel, channel_identity=channel_identity)
    if not session:
        return None
    workflow = str(_metadata(session).get("public_bot_workflow") or "").strip()
    if not workflow:
        return None
    if command in ARCLINK_PUBLIC_BOT_CANCEL_COMMANDS:
        updated = _update_session_metadata(
            conn,
            session_id=str(session["session_id"]),
            updates={},
            clear=("public_bot_workflow",),
        )
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="workflow_cancelled",
            reply=(
                "Lane sealed.\n\n"
                "Nothing was lost in the closing. When you return, I can put you back on the launch path or surface the next clean step."
            ),
            session=updated,
            deployment=deployment,
            buttons=(
                _button("Take Me Aboard", command="/packages"),
                _button("Check Status", command="/status", style="secondary"),
            ),
        )
    if workflow == "name_update":
        explicit_name = _command_value(message, command, ("name", "/name"))
        if explicit_name is not None:
            new_name = explicit_name.strip()
        elif command in {"name", "/name"}:
            new_name = ""
        elif command.startswith("/"):
            return None
        else:
            new_name = message.strip()
        if not new_name:
            return _turn(
                channel=channel,
                channel_identity=channel_identity,
                action="prompt_name_input",
                reply="I am listening. Send the name you want Raven to use, or send `cancel` to close this lane.",
                session=session,
                deployment=deployment,
                buttons=(_button("Cancel", command="/cancel", style="secondary"),),
            )
        updated = answer_arclink_onboarding_question(
            conn,
            session_id=str(session["session_id"]),
            question_key="name",
            answer_summary="display name captured",
            display_name_hint=new_name,
        )
        updated = _update_session_metadata(
            conn,
            session_id=str(updated["session_id"]),
            updates={},
            clear=("public_bot_workflow",),
        )
        return _package_prompt_reply(updated, greeting=f"Welcome aboard, {new_name}.")
    if workflow == "connect_notion":
        if command in {"ready", "done", "verified", "complete"}:
            updated = _update_session_metadata(
                conn,
                session_id=str(session["session_id"]),
                updates={
                    "connect_notion_user_marked_ready_at": utc_now_iso(),
                    "connect_notion_public_status": "ready_for_dashboard_verification",
                },
                clear=("public_bot_workflow",),
            )
            if deployment:
                _record_bot_action(
                    conn,
                    deployment=deployment,
                    action="connect_notion_ready",
                    channel=channel,
                    channel_identity=channel_identity,
                    metadata={"verification_status": "pending_dashboard_verification"},
                )
            return _turn(
                channel=channel,
                channel_identity=channel_identity,
                action="connect_notion_ready",
                reply="Logged as ready for dashboard verification. This is not a completed Notion verification yet; open the dashboard Notion panel or operator rail to arm and confirm the verification-token install window.",
                session=updated,
                deployment=deployment,
            )
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="prompt_notion_ready",
            reply="Send `ready` once Notion completes the verification handshake. Send `cancel` and I will seal the Notion lane.",
            session=session,
            deployment=deployment,
        )
    if workflow == "config_backup_repo":
        owner_repo = message.strip().removeprefix("repo ").strip()
        if not GITHUB_OWNER_REPO_RE.fullmatch(owner_repo):
            return _turn(
                channel=channel,
                channel_identity=channel_identity,
                action="prompt_backup_repo",
                reply="Send the private GitHub repository in `owner/repo` form. Send `cancel` and I will seal the backup lane.",
                session=session,
                deployment=deployment,
            )
        updated = _update_session_metadata(
            conn,
            session_id=str(session["session_id"]),
            updates={
                "config_backup_owner_repo": owner_repo,
                "config_backup_requested_at": utc_now_iso(),
                "config_backup_public_status": "repo_recorded_pending_key_setup",
            },
            clear=("public_bot_workflow",),
        )
        if deployment:
            _record_bot_action(
                conn,
                deployment=deployment,
                action="config_backup_repo_recorded",
                channel=channel,
                channel_identity=channel_identity,
                metadata={"owner_repo": owner_repo, "verification_status": "pending_deploy_key_setup"},
            )
        settings_url = f"https://github.com/{owner_repo}/settings/keys"
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="record_backup_repo",
            reply=(
                f"Logged as pending key setup. `{owner_repo}` is attached to this pod's private backup lane, but backup is not active yet.\n\n"
                "Keep the repository private. ArcLink will mint a dedicated pod deploy key with write access; "
                "when the dashboard/operator rail produces the key, set it here:\n"
                f"{settings_url}\n\n"
                "Recorded to the deployment event stream - operators on the admin bridge can see this move and finish verification."
            ),
            session=updated,
            deployment=deployment,
        )
    return None


def _help_reply(
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None = None,
    deployment: Mapping[str, Any] | None = None,
) -> ArcLinkPublicBotTurn:
    ready = bool(deployment and str(deployment.get("status") or "") in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES)
    if not ready:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="show_help",
            reply=(
                "Comms are open.\n\n"
                "I will keep this simple until your first agent is live. I can help you pick Founders, Sovereign, or Scale, open checkout, or read the board.\n\n"
                "After launch, I reveal the working controls: credentials, your crew, Notion, private backups, channel pairing, files, code, and health."
            ),
            session=session,
            buttons=(
                _button("Take Me Aboard", command="/packages"),
                _button("Update Name", command="/name", style="secondary"),
            ),
        )
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="show_help",
        reply=(
            "Bridge is open.\n\n"
            "Your first agent is aboard, so I can show you the machinery now. Use the buttons for the common work. If you prefer typed controls, use `/raven agents`, `/raven status`, `/raven credentials`, `/raven connect_notion`, `/raven config_backup`, `/raven link_channel`, or `/raven cancel`.\n\n"
            "Pick one lane and I will keep the steps tight and the path clean."
        ),
        session=session,
        deployment=deployment,
        buttons=(
            _button("Show My Crew", command="/agents", style="secondary"),
            _button("Wire Notion", command="/connect_notion", style="secondary"),
        ),
    )


def _upgrade_hermes_reply(
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
) -> ArcLinkPublicBotTurn:
    ready = bool(deployment and str(deployment.get("status") or "") in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES)
    if not ready:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="upgrade_hermes_unavailable",
            reply=(
                "Hermes upgrades stay on ArcLink-managed rails.\n\n"
                "I cannot run an unmanaged `hermes update` from public chat. Once your first agent is live, I can show the active agent and status; operators use ArcLink deploy/control upgrade checks for runtime changes."
            ),
            session=session,
            deployment=deployment,
            buttons=(
                _button("Take Me Aboard", command="/packages"),
                _button("Check Status", command="/status", style="secondary"),
            ),
        )
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="upgrade_hermes_controlled",
        reply=(
            "Hermes is pinned and upgraded through ArcLink, not direct `hermes update` commands.\n\n"
            "For this agent, use the operator-controlled upgrade rails: component pin checks, ArcLink deploy upgrade, and the post-upgrade health/smoke path. I will keep user chat on status, agents, Notion, backups, channels, files, code, and health."
        ),
        session=session,
        deployment=deployment,
        buttons=(
            _button("Check Status", command="/status", style="secondary"),
            _button("Show My Crew", command="/agents", style="secondary"),
        ),
    )


def _status_reply(
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any],
    deployment: Mapping[str, Any] | None,
    conn: sqlite3.Connection,
) -> ArcLinkPublicBotTurn:
    deployment_label = _agent_label(deployment or {}, index=0, conn=conn) if deployment else ""
    live_status_code = str((deployment or {}).get("status") or session.get("status") or "")
    phrase = launch_phrase(live_status_code)
    lines = [
        f"Reading the board.\n\n{phrase}",
    ]
    if deployment_label:
        lines.append(f"Agent at the helm: {deployment_label}.")
    lines.append(
        f"\n_session `{session['session_id']}` · state `{live_status_code or 'unknown'}` · "
        f"step `{session.get('current_step') or 'started'}`_"
    )
    buttons: list[ArcLinkPublicBotButton] = [_button("Show My Crew", command="/agents", style="secondary")]
    access = _deployment_access(deployment or {}) if deployment else {}
    if access.get("dashboard"):
        buttons.append(_button("Open Helm", url=str(access["dashboard"])))
    else:
        buttons.append(_button("Choose Package", command="/packages", style="secondary"))
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="show_status",
        reply="\n".join(lines),
        session=session,
        deployment=deployment,
        buttons=tuple(buttons),
    )


def handle_arclink_public_bot_turn(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    text: str,
    stripe_client: Any | None = None,
    price_id: str = "price_arclink_sovereign",
    founders_price_id: str = "price_arclink_founders",
    scale_price_id: str = "",
    additional_agent_price_id: str = "",
    sovereign_agent_expansion_price_id: str = "",
    scale_agent_expansion_price_id: str = "",
    base_domain: str = "",
    metadata: Mapping[str, Any] | None = None,
    display_name_hint: str = "",
) -> ArcLinkPublicBotTurn:
    clean_channel = _clean_channel(channel)
    clean_identity = _clean_identity(channel_identity)
    _check_public_bot_rate_limit(conn, channel=clean_channel, channel_identity=clean_identity)
    message = str(text or "").strip()
    command = message.lower()
    captured_display_name = str(display_name_hint or "").strip()[:40]
    turn_metadata = dict(metadata or {})
    reply_to_message_id = str(
        turn_metadata.get("telegram_message_id")
        or turn_metadata.get("discord_message_id")
        or turn_metadata.get("message_id")
        or ""
    ).strip()
    raven_control_requested = False
    rewritten = _raven_control_rewrite(message, command)
    if rewritten is not None:
        message = rewritten
        command = message.lower()
        raven_control_requested = True

    if message.startswith("/") and not raven_control_requested:
        context_session, context_deployment = _deployment_context(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
        )
        if (
            context_deployment
            and str(context_deployment.get("status") or "") in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES
        ):
            command_name = _public_bot_command_name(message)
            agent_command_names = _agent_command_names_from_context(turn_metadata, context_session)
            if command_name in ARCLINK_PUBLIC_BOT_AGENT_POLICY_SUPPRESSED_COMMANDS:
                return _upgrade_hermes_reply(
                    channel=clean_channel,
                    channel_identity=clean_identity,
                    session=context_session,
                    deployment=context_deployment,
                )
            if command_name and command_name in agent_command_names:
                raven = _raven_display_name(
                    conn,
                    channel=clean_channel,
                    channel_identity=clean_identity,
                    session=context_session,
                    deployment=context_deployment,
                )
                return _aboard_freeform_reply(
                    channel=clean_channel,
                    channel_identity=clean_identity,
                    session=context_session,
                    deployment={
                        **context_deployment,
                        "_public_bot_message": message,
                        "_public_bot_reply_to_message_id": reply_to_message_id,
                        "_public_bot_metadata": turn_metadata,
                    },
                    bot_display_name=raven,
                    conn=conn,
                    source_kind="agent_command",
                    include_bridge_intro=False,
                )

    if _raven_name_command_value(message, command) is not None:
        return _raven_name_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            message=message,
            command=command,
        )

    if command in ARCLINK_PUBLIC_BOT_HELP_COMMANDS:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        return _help_reply(
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
        )

    if command in {"status", "/status"}:
        context_session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        if context_session is not None:
            return _status_reply(
                channel=clean_channel,
                channel_identity=clean_identity,
                session=context_session,
                deployment=deployment,
                conn=conn,
            )

    if command in ARCLINK_PUBLIC_BOT_AGENTS_COMMANDS:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        return _agents_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
        )

    agent_passthrough = _agent_passthrough_message(message, command)
    if agent_passthrough is not None:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        if not deployment or str(deployment.get("status") or "") not in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES:
            return _turn(
                channel=clean_channel,
                channel_identity=clean_identity,
                action="agent_message_unavailable",
                reply=_need_finished_onboarding_reply(),
                session=session,
                deployment=deployment,
                buttons=(_button("Take Me Aboard", command="/packages"),),
            )
        if not agent_passthrough:
            return _turn(
                channel=clean_channel,
                channel_identity=clean_identity,
                action="agent_message_missing",
                reply=(
                    "Tell me what to send to your active agent after `/agent`.\n\n"
                    "Example: `/agent check the vault index` or `/agent /provider`."
                ),
                session=session,
                deployment=deployment,
                buttons=(_button("Show My Crew", command="/agents", style="secondary"),),
            )
        raven = _raven_display_name(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
        )
        return _aboard_freeform_reply(
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment={
                **deployment,
                "_public_bot_message": agent_passthrough,
                "_public_bot_reply_to_message_id": reply_to_message_id,
                "_public_bot_metadata": turn_metadata,
            },
            bot_display_name=raven,
            conn=conn,
            source_kind="agent_command" if agent_passthrough.startswith("/") else "agent_passthrough",
            include_bridge_intro=False,
        )

    pair_value = _pair_channel_value(message, command)
    if pair_value is not None:
        session = create_or_resume_arclink_onboarding_session(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            selected_model_id=chutes_default_model({}),
            metadata=metadata,
            display_name_hint=captured_display_name,
        )
        context_session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        raven = _raven_display_name(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=context_session or session,
            deployment=deployment,
        )
        return _pair_channel_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=context_session or session,
            deployment=deployment,
            code_value=pair_value,
            bot_display_name=raven,
        )

    if command in ARCLINK_PUBLIC_BOT_ADD_AGENT_COMMANDS:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        return _add_agent_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
            stripe_client=stripe_client,
            additional_agent_price_id=additional_agent_price_id,
            sovereign_agent_expansion_price_id=sovereign_agent_expansion_price_id,
            scale_agent_expansion_price_id=scale_agent_expansion_price_id,
            base_domain=base_domain,
        )

    if command in ARCLINK_PUBLIC_BOT_UPGRADE_HERMES_COMMANDS:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        return _upgrade_hermes_reply(
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
        )

    share_match = ARCLINK_PUBLIC_BOT_SHARE_ACTION_RE.match(command)
    if share_match:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        return _share_grant_action_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            requested_action=share_match.group(1),
            grant_id=share_match.group(2),
            session=session,
            deployment=deployment,
        )

    if command in ARCLINK_PUBLIC_BOT_CANCEL_COMMANDS:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        if deployment and str(deployment.get("status") or "") in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES:
            return _turn(
                channel=clean_channel,
                channel_identity=clean_identity,
                action="cancel_unavailable",
                reply=(
                    "No setup workflow is open to cancel. Your agent is already live; use `/agents` or `/status` from here."
                ),
                session=session,
                deployment=deployment,
                buttons=(
                    _button("Show My Crew", command="/agents", style="secondary"),
                    _button("Check Status", command="/status", style="secondary"),
                ),
            )
        if session:
            updated = cancel_arclink_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                reason="public bot cancel command",
            )
            return _turn(
                channel=clean_channel,
                channel_identity=clean_identity,
                action="onboarding_cancelled",
                reply=(
                    "Launch setup cancelled.\n\n"
                    "I closed the open onboarding and checkout state. Send `/packages` when you want to resume with a clean handoff."
                ),
                session=updated,
                deployment=deployment,
                buttons=(
                    _button("Take Me Aboard", command="/packages"),
                    _button("Check Status", command="/status", style="secondary"),
                ),
            )
        return _turn(
            channel=clean_channel,
            channel_identity=clean_identity,
            action="nothing_to_cancel",
            reply="No open ArcLink setup workflow is waiting on this channel. Send `/packages` when you want to start.",
            buttons=(_button("Take Me Aboard", command="/packages"),),
        )

    switch_match = ARCLINK_PUBLIC_BOT_AGENT_SWITCH_RE.match(command)
    if switch_match:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        return _switch_agent_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            requested_slug=switch_match.group(1),
            session=session,
            deployment=deployment,
        )

    if command in ARCLINK_PUBLIC_BOT_CREDENTIAL_COMMANDS:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        return _credentials_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
        )

    if command in ARCLINK_PUBLIC_BOT_CREDENTIAL_ACK_COMMANDS:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        return _credentials_stored_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
        )

    if command in ARCLINK_PUBLIC_BOT_CONNECT_NOTION_COMMANDS:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        return _connect_notion_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
        )

    active_workflow = _handle_active_workflow(
        conn,
        channel=clean_channel,
        channel_identity=clean_identity,
        message=message,
        command=command,
    )
    if active_workflow is not None:
        return active_workflow

    if command in ARCLINK_PUBLIC_BOT_CONFIG_BACKUP_COMMANDS:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        return _config_backup_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
        )

    # Routing law: if the user is already aboard with a live pod, every
    # remaining branch below this point would re-trigger onboarding copy
    # ("Stripe collects your email", "Send /name Your Name") that makes no
    # sense for a paying customer. Hand them a clean Helm pointer instead.
    aboard_session, aboard_deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
    if aboard_deployment and str(aboard_deployment.get("status") or "") in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES:
        if command in {"/start", "start", "restart"} or _is_raven_launch_command(message, command):
            return _help_reply(
                channel=clean_channel,
                channel_identity=clean_identity,
                session=aboard_session,
                deployment=aboard_deployment,
            )
        raven = _raven_display_name(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=aboard_session,
            deployment=aboard_deployment,
        )
        return _aboard_freeform_reply(
            channel=clean_channel,
            channel_identity=clean_identity,
            session=aboard_session,
            deployment={
                **aboard_deployment,
                "_public_bot_message": message,
                "_public_bot_reply_to_message_id": reply_to_message_id,
                "_public_bot_metadata": turn_metadata,
            },
            bot_display_name=raven,
            conn=conn,
            source_kind="agent_command" if message.startswith("/") else "chat",
            include_bridge_intro=(
                bool(message)
                and not message.startswith("/")
                and _claim_agent_bridge_intro(
                    conn,
                    channel=clean_channel,
                    channel_identity=clean_identity,
                    deployment=aboard_deployment,
                )
            ),
        )

    session = create_or_resume_arclink_onboarding_session(
        conn,
        channel=clean_channel,
        channel_identity=clean_identity,
        selected_model_id=chutes_default_model({}),
        metadata=metadata,
        display_name_hint=captured_display_name,
    )
    raven = _raven_display_name(conn, channel=clean_channel, channel_identity=clean_identity, session=session)

    if command in {"", "/start", "start", "restart"}:
        # Greet by the name we picked up from the channel profile (Telegram
        # first_name, Discord global_name). The user can override via Update
        # Name -> /name. If nothing was captured, the greeting stays generic.
        name = str(session.get("display_name_hint") or "").strip()
        greeting = f"Welcome aboard, {name}." if name else f"{raven} here. ArcLink is in range."
        return _reply(
            session,
            action="prompt_name",
            reply=(
                f"{greeting}\n\n"
                "I bring private agents online with memory, files, code workspace, model access, and dashboard visibility. "
                "No bot-building. No server chores.\n\n"
                "Tap Take Me Aboard to pick Founders, Sovereign, or Scale. Tap Update Name and just tell me what to call you."
            ),
            buttons=(
                _button("Take Me Aboard", command="/packages"),
                _button("Update Name", command="/name", style="secondary"),
            ),
            bot_display_name=raven,
        )
    if command in {"status", "/status"}:
        context_session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        return _status_reply(
            channel=clean_channel,
            channel_identity=clean_identity,
            session=context_session or session,
            deployment=deployment,
            conn=conn,
        )
    email = _command_value(message, command, ("email", "/email"))
    if email is not None:
        return _reply(
            session,
            action="prompt_name",
            reply="Keep your email out of comms. Stripe collects it at checkout, and only there. Tap Update Name, then just send the name you want Raven to use.",
        )
    if command in ARCLINK_PUBLIC_BOT_STANDARD_PACKAGE_COMMANDS:
        return _package_prompt_reply(session, standard=True, bot_display_name=raven)
    if command in ARCLINK_PUBLIC_BOT_PACKAGE_COMMANDS:
        return _package_prompt_reply(session, bot_display_name=raven)
    if command in {"name", "/name"}:
        # Bare /name (or the Update Name button) opens a short listening lane.
        # The next plain-text message becomes the display name.
        current = str(session.get("display_name_hint") or "").strip()
        current_line = f"\n\nCurrent name: {current}" if current else ""
        session = _update_session_metadata(
            conn,
            session_id=str(session["session_id"]),
            updates={"public_bot_workflow": "name_update", "name_update_requested_at": utc_now_iso()},
        )
        return _reply(
            session,
            action="prompt_name_input",
            reply=(
                "What should I call you on the ArcLink manifest?\n\n"
                "Send the name as plain text. I am listening."
                f"{current_line}"
            ),
            buttons=(
                _button("Cancel", command="/cancel", style="secondary"),
            ),
        )
    name = _command_value(message, command, ("name", "/name"))
    if name is not None:
        session = answer_arclink_onboarding_question(
            conn,
            session_id=str(session["session_id"]),
            question_key="name",
            answer_summary="display name captured",
            display_name_hint=name,
        )
        return _package_prompt_reply(session, greeting=f"Welcome aboard, {name}.", bot_display_name=raven)
    plan_answer = _command_value(message, command, ("plan", "/plan"))
    if plan_answer is not None:
        plan = _normalize_public_bot_plan(plan_answer)
        if plan not in ARCLINK_PUBLIC_BOT_PLANS:
            raise ArcLinkPublicBotError(f"unsupported ArcLink public bot plan: {plan or 'blank'}")
        session = answer_arclink_onboarding_question(
            conn,
            session_id=str(session["session_id"]),
            question_key="plan",
            answer_summary=f"selected {plan}",
            selected_plan_id=plan,
            selected_model_id=chutes_default_model({}),
        )
        if plan == "scale":
            plan_reply = (
                "Scale is locked.\n\n"
                f"Agents onboard ArcLink with Federation for ${SCALE_MONTHLY_DOLLARS}/month. "
                "Stripe handles the handoff, then I move onboarding into the launch queue and report back here."
            )
        elif plan == "founders":
            plan_reply = (
                "Limited 100 Founders is locked.\n\n"
                f"Sovereign-equivalent access for ${FOUNDERS_MONTHLY_DOLLARS}/month. "
                "Agent onboard ArcLink while the Founders cohort is open."
            )
        else:
            plan_reply = (
                "Sovereign is locked.\n\n"
                f"Agent onboard ArcLink for ${SOVEREIGN_MONTHLY_DOLLARS}/month. "
                "Stripe handles the handoff, then I move onboarding into the launch queue and report back here."
            )
        if stripe_client is not None:
            return _open_first_agent_checkout_turn(
                conn,
                session,
                stripe_client=stripe_client,
                selected_plan=plan,
                price_id=price_id,
                founders_price_id=founders_price_id,
                scale_price_id=scale_price_id,
                base_domain=base_domain,
                bot_display_name=raven,
            )
        return _reply(
            session,
            action="prompt_checkout",
            reply=plan_reply,
            buttons=(
                _button(_plan_checkout_label(plan), command="/checkout"),
                _button("Change Package", command="/packages", style="secondary"),
            ),
            bot_display_name=raven,
        )
    if command in {"checkout", "/checkout"}:
        if stripe_client is None:
            raise ArcLinkPublicBotError("checkout requires an injected Stripe client")
        selected_plan = _normalize_public_bot_plan(str(session.get("selected_plan_id") or "founders"))
        return _open_first_agent_checkout_turn(
            conn,
            session,
            stripe_client=stripe_client,
            selected_plan=selected_plan,
            price_id=price_id,
            founders_price_id=founders_price_id,
            scale_price_id=scale_price_id,
            base_domain=base_domain,
            bot_display_name=raven,
        )
    return _reply(
        session,
        action="prompt_command",
            reply=(
                f"I read you. {raven} on the line.\n\n"
                "No command map needed yet. The early lanes stay few on purpose. From here I can help you pick Founders, Sovereign, or Scale, set your name, or read the board. Once your agent is awake on ArcLink, the deeper controls surface as a clean checklist."
            ),
        buttons=(
            _button("Take Me Aboard", command="/packages"),
            _button("Update Name", command="/name", style="secondary"),
        ),
        bot_display_name=raven,
    )
