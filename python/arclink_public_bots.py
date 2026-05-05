#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
import secrets
import sqlite3
from typing import Any, Mapping

from arclink_api_auth import check_arclink_rate_limit
from arclink_adapters import arclink_access_urls
from arclink_boundary import json_dumps_safe, json_loads_safe
from arclink_control import append_arclink_event, utc_after_seconds_iso, utc_now_iso
from arclink_onboarding import (
    answer_arclink_onboarding_question,
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
ARCLINK_PUBLIC_BOT_HELP_COMMANDS = frozenset({"/help", "help", "commands", "/commands"})
ARCLINK_PUBLIC_BOT_CANCEL_COMMANDS = frozenset({"/cancel", "cancel", "stop"})
ARCLINK_PUBLIC_BOT_AGENTS_COMMANDS = frozenset({"/agents", "agents", "my agents", "agent roster"})
ARCLINK_PUBLIC_BOT_ADD_AGENT_COMMANDS = frozenset(
    {"/add-agent", "/add_agent", "add-agent", "add agent", "hire another agent", "add another agent"}
)
ARCLINK_PUBLIC_BOT_PAIR_CHANNEL_COMMANDS = frozenset(
    {"/pair-channel", "/pair_channel", "pair-channel", "pair_channel", "pair channel", "pair"}
)
ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES = frozenset({"active", "first_contacted"})
ARCLINK_PUBLIC_BOT_AGENT_SWITCH_RE = re.compile(r"^/(?:agent[-_])([a-z0-9][a-z0-9_-]{0,31})$")
ARCLINK_PUBLIC_BOT_PAIR_CODE_RE = re.compile(r"^[A-Z0-9]{6}$")
GITHUB_OWNER_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
PAIR_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PAIR_CODE_TTL_SECONDS = 10 * 60
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


def _button(label: str, *, command: str = "", url: str = "", style: str = "primary") -> ArcLinkPublicBotButton:
    return ArcLinkPublicBotButton(label=label, command=command, url=url, style=style)


def _reply(
    session: Mapping[str, Any],
    *,
    action: str,
    reply: str,
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
        buttons=buttons,
    )


def _package_prompt_reply(
    session: Mapping[str, Any],
    *,
    greeting: str = "",
    standard: bool = False,
) -> ArcLinkPublicBotTurn:
    name = str(session.get("display_name_hint") or "").strip()
    header = greeting or (f"Welcome aboard, {name}." if name else "Raven here. ArcLink is in range.")
    if standard:
        return _reply(
            session,
            action="prompt_package",
            reply=(
                f"{header}\n\n"
                "Choose your standard ArcLink vessel.\n\n"
                f"Sovereign is ${SOVEREIGN_MONTHLY_DOLLARS}/month: one private agent plus ArcLink systems.\n"
                f"Scale is ${SCALE_MONTHLY_DOLLARS}/month: three agents, ArcLink systems, and Federation.\n\n"
                f"Agentic Expansion after launch: Sovereign agents are ${SOVEREIGN_AGENT_EXPANSION_MONTHLY_DOLLARS}/month each; "
                f"Scale agents are ${SCALE_AGENT_EXPANSION_MONTHLY_DOLLARS}/month each."
            ),
            buttons=(
                _button(f"Sovereign - ${SOVEREIGN_MONTHLY_DOLLARS}/month", command="/plan sovereign"),
                _button(f"Scale - ${SCALE_MONTHLY_DOLLARS}/month", command="/plan scale", style="secondary"),
            ),
        )
    return _reply(
        session,
        action="prompt_package",
        reply=(
            f"{header}\n\n"
            f"Choose your ArcLink vessel.\n\n"
            f"Limited 100 Founders is ${FOUNDERS_MONTHLY_DOLLARS}/month: Sovereign-equivalent access for the first 100 aboard.\n"
            f"Sovereign is ${SOVEREIGN_MONTHLY_DOLLARS}/month. Scale is ${SCALE_MONTHLY_DOLLARS}/month.\n\n"
            f"Agentic Expansion after launch starts at ${SCALE_AGENT_EXPANSION_MONTHLY_DOLLARS}/month on Scale "
            f"and ${SOVEREIGN_AGENT_EXPANSION_MONTHLY_DOLLARS}/month on Sovereign."
        ),
        buttons=(
            _button(f"Founders - ${FOUNDERS_MONTHLY_DOLLARS}/month", command="/plan founders"),
            _button("Sovereign / Scale", command="/packages standard", style="secondary"),
        ),
    )


def _turn(
    *,
    channel: str,
    channel_identity: str,
    action: str,
    reply: str,
    session: Mapping[str, Any] | None = None,
    deployment: Mapping[str, Any] | None = None,
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


def arclink_public_bot_turn_telegram_reply_markup(turn: ArcLinkPublicBotTurn) -> dict[str, Any] | None:
    buttons = tuple(turn.buttons or ())
    if not buttons:
        return None
    rows: list[list[dict[str, Any]]] = []
    row: list[dict[str, Any]] = []
    for button in buttons:
        payload: dict[str, Any] = {"text": button.label[:64]}
        if button.url:
            payload["url"] = button.url
        else:
            payload["callback_data"] = f"arclink:{button.command or button.label}"[:64]
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


def _pair_channel_value(message: str, command: str) -> str | None:
    if command in ARCLINK_PUBLIC_BOT_PAIR_CHANNEL_COMMANDS:
        return ""
    return _command_value(
        message,
        command,
        (
            "/pair-channel",
            "/pair_channel",
            "pair-channel",
            "pair_channel",
            "pair channel",
            "pair",
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
    active_deployment_id = str(_metadata(session).get("active_deployment_id") or "").strip()
    if active_deployment_id:
        row = conn.execute("SELECT * FROM arclink_deployments WHERE deployment_id = ?", (active_deployment_id,)).fetchone()
        if row is not None:
            return dict(row)
    deployment_id = str(session.get("deployment_id") or "").strip()
    if deployment_id:
        row = conn.execute("SELECT * FROM arclink_deployments WHERE deployment_id = ?", (deployment_id,)).fetchone()
        if row is not None:
            return dict(row)
    user_id = str(session.get("user_id") or "").strip()
    if not user_id:
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
        (user_id,),
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
    2. The user's onboarding display_name_hint (the name they actually picked).
       If that user has multiple pods sharing the same display name, append a
       short prefix tail like "#69f2" so they're distinguishable in the roster.
    3. Explicit agent_id
    4. A clean "Agent #<prefix-tail>" rather than the cryptic Title-Cased hash
    5. "Agent N" as a last resort.
    """
    metadata = _metadata(deployment)
    candidate = str(metadata.get("agent_name") or metadata.get("display_name") or "").strip()
    if candidate:
        return candidate[:40]

    deployment_id = str(deployment.get("deployment_id") or "").strip()
    user_id = str(deployment.get("user_id") or "").strip()
    if conn is not None:
        row = None
        if deployment_id:
            row = conn.execute(
                "SELECT display_name_hint FROM arclink_onboarding_sessions "
                "WHERE deployment_id = ? AND display_name_hint != '' "
                "ORDER BY updated_at DESC LIMIT 1",
                (deployment_id,),
            ).fetchone()
        if row is None and user_id:
            row = conn.execute(
                "SELECT display_name_hint FROM arclink_onboarding_sessions "
                "WHERE user_id = ? AND display_name_hint != '' "
                "ORDER BY updated_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        if row is not None:
            display_name = str(row["display_name_hint"] or "").strip()
            if display_name:
                tail = ""
                if user_id:
                    others = conn.execute(
                        "SELECT COUNT(*) AS c FROM arclink_deployments "
                        "WHERE user_id = ? AND deployment_id != ?",
                        (user_id, deployment_id),
                    ).fetchone()
                    if others and others["c"] > 0:
                        prefix = str(deployment.get("prefix") or "")
                        prefix_tail = prefix.rsplit("-", 1)[-1][:4]
                        if prefix_tail:
                            tail = f" #{prefix_tail}"
                return (display_name + tail)[:40]

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


def _deployment_access(deployment: Mapping[str, Any]) -> dict[str, str]:
    metadata = _metadata(deployment)
    base_domain = str(deployment.get("base_domain") or metadata.get("base_domain") or "").strip().lower().strip(".")
    ingress_mode = str(metadata.get("ingress_mode") or "").strip().lower()
    if not ingress_mode:
        ingress_mode = "tailscale" if base_domain.endswith(".ts.net") else "domain"
    tailscale_dns_name = str(metadata.get("tailscale_dns_name") or base_domain).strip().lower().strip(".")
    tailscale_strategy = str(metadata.get("tailscale_host_strategy") or "path").strip().lower()
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


def _aboard_freeform_reply(
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any],
    conn: sqlite3.Connection | None = None,
) -> ArcLinkPublicBotTurn:
    """Routing law: once a user has a live pod, freeform messages on this
    channel belong to their private agent on the Helm, not to Raven. Raven
    keeps slash commands; everything else is a clear handoff with the helm
    URL and a short slash-command map for the times the user wanted Raven.
    """
    label = _agent_label(deployment, index=0, conn=conn)
    access = _deployment_access(deployment)
    helm = str(access.get("dashboard") or "").rstrip("/")
    lines = [
        f"I'm Raven, onboarding only. Your agent **{label}** is awake on the helm, and freeform messages on this channel reach me, not it.",
        "",
        "Open the helm to talk to your agent directly:" if helm else "Open the helm to talk to your agent directly.",
    ]
    if helm:
        lines.append(helm)
    lines.append("")
    lines.append(
        "If you wanted to call me back, the slash commands still route here: `/help`, `/agents`, `/status`, "
        "`/connect_notion`, `/config_backup`, `/pair-channel`."
    )
    buttons: list[ArcLinkPublicBotButton] = []
    if helm:
        buttons.append(_button("Open Helm", url=helm))
    buttons.append(_button("Show My Crew", command="/agents", style="secondary"))
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="aboard_freeform",
        reply="\n".join(lines),
        session=session,
        deployment=deployment,
        buttons=tuple(buttons),
    )


def _need_finished_onboarding_reply() -> str:
    return (
        "That lane opens once your first agent is awake aboard ArcLink. Send `/start` and I will walk you to the hatch, "
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
) -> ArcLinkPublicBotTurn:
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
            "If your pod is already online, the other channel gets the same ArcLink identity, crew, tools, vault, Notion lane, and system status. "
            "The chat session stays separate; the vessel underneath is the same."
            if deployment
            else "If you are still prelaunch, the other channel joins this same launch path."
        )
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="pair_channel_code",
            reply=(
                "Pairing lane open.\n\n"
                f"On the other channel, tell Raven: `/pair-channel {code}`\n\n"
                f"This code expires in 10 minutes. {live_note}"
            ),
            session=updated,
            deployment=deployment,
            buttons=(
                _button("Show My Crew", command="/agents", style="secondary"),
                _button("Run Systems Check", command="/status", style="secondary"),
            ),
        )

    if not ARCLINK_PUBLIC_BOT_PAIR_CODE_RE.fullmatch(clean_code):
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="pair_channel_invalid_code",
            reply="That pairing code does not look right. Open `/pair-channel` on the other channel and send me the six-character code it gives you.",
            session=session,
            deployment=deployment,
            buttons=(_button("Try Again", command="/pair-channel", style="secondary"),),
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
            reply="That pairing code has gone cold. Open `/pair-channel` on the first channel and I will mint a fresh one.",
            session=session,
            deployment=deployment,
            buttons=(_button("Open Pairing", command="/pair-channel", style="secondary"),),
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
            "Telegram and Discord keep separate chat threads, but Raven is now looking at the same vessel underneath."
        ),
        session=target,
        deployment=linked_deployment,
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
    callback_url = _notion_callback_url(deployment)
    session = _update_session_metadata(
        conn,
        session_id=str(session["session_id"]),
        updates={
            "public_bot_workflow": "connect_notion",
            "connect_notion_requested_at": utc_now_iso(),
        },
    )
    _record_bot_action(
        conn,
        deployment=deployment,
        action="connect_notion_requested",
        channel=channel,
        channel_identity=channel_identity,
        metadata={"deployment_status": str(deployment.get("status") or "")},
    )
    lines = [
        "Opening the Notion lane into your vessel.",
        "",
        "Drop this callback into the Notion webhook/subscription panel:",
        callback_url or "(callback URL is not available yet)",
        "",
        "Then share the page or database with the ArcLink integration. No tokens in chat - when I need a secret, the secure dashboard field is the only door.",
        "",
        "Send `ready` once Notion completes the verification handshake, or `cancel` and I will seal the lane.",
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
        },
    )
    _record_bot_action(
        conn,
        deployment=deployment,
        action="config_backup_requested",
        channel=channel,
        channel_identity=channel_identity,
        metadata={"deployment_status": str(deployment.get("status") or "")},
    )
    example = f"{str(deployment.get('user_id') or 'you').replace('_', '-')}/arclink-{str(deployment.get('prefix') or 'pod')}"
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="prompt_backup_repo",
        reply=(
            "Opening the private backup lane.\n\n"
            "Choose a private GitHub repository - this is where Hermes' home and the pod's configuration snapshots will rest. "
            "Send me `owner/repo` and I will pin it to this deployment.\n\n"
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
                reply=f"Helm transferred. {label} is on the rail. Notion, backup, and system lanes will route to that agent until you call another to the helm.",
                session=updated,
                deployment=item,
                buttons=(
                    _button("Show My Crew", command="/agents", style="secondary"),
                    _button("Run Systems Check", command="/status", style="secondary"),
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
        success_url=f"{root}/checkout/success?kind=additional_agent",
        cancel_url=f"{root}/checkout/cancel?kind=additional_agent",
        base_domain=base_domain or default_base_domain({}),
    )
    return _reply(
        extra_session,
        action="open_add_agent_checkout",
        reply=(
            f"A bay is open. Agentic Expansion for your {_plan_label(plan)} vessel is {expansion_label}. "
            "Clear the Stripe handoff and I will move the new agent into the launch queue with the rest of your crew."
        ),
        buttons=(
            _button(f"Hire Agent - {expansion_label}", url=str(extra_session.get("checkout_url") or "")),
            _button("Back To My Crew", command="/agents", style="secondary"),
        ),
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
                _button("Run Systems Check", command="/status", style="secondary"),
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
                updates={"connect_notion_user_marked_ready_at": utc_now_iso()},
                clear=("public_bot_workflow",),
            )
            if deployment:
                _record_bot_action(
                    conn,
                    deployment=deployment,
                    action="connect_notion_ready",
                    channel=channel,
                    channel_identity=channel_identity,
                )
            return _turn(
                channel=channel,
                channel_identity=channel_identity,
                action="connect_notion_ready",
                reply="Logged. Notion is marked ready on this pod. If the webhook still reads as unverified, open the dashboard Notion panel - ArcLink will arm the verification-token install window from there.",
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
                metadata={"owner_repo": owner_repo},
            )
        settings_url = f"https://github.com/{owner_repo}/settings/keys"
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="record_backup_repo",
            reply=(
                f"Logged. `{owner_repo}` is bound to this pod's private backup lane.\n\n"
                "Keep the repository private. ArcLink will mint a dedicated pod deploy key with write access; "
                "when the key is ready, set it here:\n"
                f"{settings_url}\n\n"
                "Recorded to the deployment event stream - operators on the admin bridge can see this move."
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
                "I will keep this simple until your first vessel is live. I can help you pick Founders, Sovereign, or Scale, open checkout, or read the board.\n\n"
                "After launch, I reveal the working controls: your crew, Notion, private backups, channel pairing, files, code, and health."
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
            "Your first agent is aboard, so I can show you the machinery now. Use the buttons for the common work. If you prefer typed controls, I read them all: `/agents`, `/status`, `/connect_notion`, `/config_backup`, `/pair_channel`, `/cancel`.\n\n"
            "Pick one lane and I will keep the steps tight and the path clean."
        ),
        session=session,
        deployment=deployment,
        buttons=(
            _button("Show My Crew", command="/agents", style="secondary"),
            _button("Wire Notion", command="/connect_notion", style="secondary"),
        ),
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

    if command in ARCLINK_PUBLIC_BOT_HELP_COMMANDS:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        return _help_reply(
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
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
        return _pair_channel_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=context_session or session,
            deployment=deployment,
            code_value=pair_value,
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
        return _aboard_freeform_reply(
            channel=clean_channel,
            channel_identity=clean_identity,
            session=aboard_session,
            deployment=aboard_deployment,
            conn=conn,
        )

    session = create_or_resume_arclink_onboarding_session(
        conn,
        channel=clean_channel,
        channel_identity=clean_identity,
        selected_model_id=chutes_default_model({}),
        metadata=metadata,
        display_name_hint=captured_display_name,
    )

    if command in {"", "/start", "start", "restart"}:
        # Greet by the name we picked up from the channel profile (Telegram
        # first_name, Discord global_name). The user can override via Update
        # Name -> /name. If nothing was captured, the greeting stays generic.
        name = str(session.get("display_name_hint") or "").strip()
        greeting = f"Welcome aboard, {name}." if name else "Raven here. ArcLink is in range."
        return _reply(
            session,
            action="prompt_name",
            reply=(
                f"{greeting}\n\n"
                "I bring private agents online with memory, files, code workspace, model access, and a live systems board. "
                "No bot-building. No server chores.\n\n"
                "Tap Take Me Aboard to pick Founders, Sovereign, or Scale. Tap Update Name and just tell me what to call you."
            ),
            buttons=(
                _button("Take Me Aboard", command="/packages"),
                _button("Update Name", command="/name", style="secondary"),
            ),
        )
    if command in {"status", "/status"}:
        context_session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        active_session = context_session or session
        deployment_label = _agent_label(deployment or {}, index=0, conn=conn) if deployment else ""
        # Pick the most informative phrase: deployment status outranks session
        # status once a deployment exists (it's closer to the user's reality).
        live_status_code = str((deployment or {}).get("status") or active_session.get("status") or "")
        phrase = launch_phrase(live_status_code)
        lines = [
            f"Reading the board.\n\n{phrase}",
        ]
        if deployment_label:
            lines.append(f"Agent at the helm: {deployment_label}.")
        # Operator-grade trailer for power users - small, dim, never leading.
        lines.append(
            f"\n_session `{active_session['session_id']}` · state `{live_status_code or 'unknown'}` · "
            f"step `{active_session.get('current_step') or 'started'}`_"
        )
        return _reply(
            active_session,
            action="show_status",
            reply="\n".join(lines),
            buttons=(
                _button("Show My Crew", command="/agents", style="secondary"),
                _button("Choose Package", command="/packages", style="secondary"),
            ),
        )
    email = _command_value(message, command, ("email", "/email"))
    if email is not None:
        return _reply(
            session,
            action="prompt_name",
            reply="Keep your email out of comms. Stripe collects it at checkout, and only there. Tap Update Name, then just send the name you want Raven to use.",
        )
    if command in ARCLINK_PUBLIC_BOT_STANDARD_PACKAGE_COMMANDS:
        return _package_prompt_reply(session, standard=True)
    if command in ARCLINK_PUBLIC_BOT_PACKAGE_COMMANDS:
        return _package_prompt_reply(session)
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
        return _package_prompt_reply(session, greeting=f"Welcome aboard, {name}.")
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
                f"Three agents, ArcLink systems, and Federation for ${SCALE_MONTHLY_DOLLARS}/month. "
                "Stripe handles the handoff, then I bring the vessel online and report back here."
            )
        elif plan == "founders":
            plan_reply = (
                "Limited 100 Founders is locked.\n\n"
                f"Sovereign-equivalent access for ${FOUNDERS_MONTHLY_DOLLARS}/month. "
                "You get one private agent plus ArcLink systems while the Founders cohort is open."
            )
        else:
            plan_reply = (
                "Sovereign is locked.\n\n"
                f"One private agent plus ArcLink systems for ${SOVEREIGN_MONTHLY_DOLLARS}/month. "
                "Stripe handles the handoff, then I bring the vessel online and report back here."
            )
        return _reply(
            session,
            action="prompt_checkout",
            reply=plan_reply,
            buttons=(
                _button(_plan_checkout_label(plan), command="/checkout"),
                _button("Change Package", command="/packages", style="secondary"),
            ),
        )
    if command in {"checkout", "/checkout"}:
        if stripe_client is None:
            raise ArcLinkPublicBotError("checkout requires an injected Stripe client")
        root = f"https://{str(base_domain or default_base_domain({})).strip().strip('/')}"
        selected_plan = _normalize_public_bot_plan(str(session.get("selected_plan_id") or "founders"))
        checkout_price_id = str(price_id or "").strip()
        if selected_plan == "founders" and str(founders_price_id or "").strip():
            checkout_price_id = str(founders_price_id or "").strip()
        if selected_plan == "founders" and not checkout_price_id:
            raise ArcLinkPublicBotError("Founders checkout requires ARCLINK_FOUNDERS_PRICE_ID")
        if selected_plan == "scale" and str(scale_price_id or "").strip():
            checkout_price_id = str(scale_price_id or "").strip()
        if selected_plan == "scale" and not str(scale_price_id or "").strip():
            raise ArcLinkPublicBotError("Scale checkout requires ARCLINK_SCALE_PRICE_ID")
        session = open_arclink_onboarding_checkout(
            conn,
            session_id=str(session["session_id"]),
            stripe_client=stripe_client,
            price_id=checkout_price_id,
            success_url=f"{root}/checkout/success",
            cancel_url=f"{root}/checkout/cancel",
            base_domain=base_domain or default_base_domain({}),
        )
        plan_label = _plan_label(selected_plan)
        return _reply(
            session,
            action="open_checkout",
            reply=(
                f"{plan_label} checkout is open. Complete the Stripe handoff at the link below. "
                "The instant payment clears, I move your ArcLink vessel into the launch queue and report back here."
            ),
            buttons=(
                _button(_plan_checkout_label(selected_plan), url=str(session.get("checkout_url") or "")),
                _button("Run Systems Check", command="/status", style="secondary"),
            ),
        )
    return _reply(
        session,
        action="prompt_command",
            reply=(
                "I read you. Raven on the line.\n\n"
                "No command map needed yet. The early lanes stay few on purpose. From here I can help you pick Founders, Sovereign, or Scale, set your name, or read the board. Once your agent is awake on ArcLink, the deeper controls surface as a clean checklist."
            ),
        buttons=(
            _button("Take Me Aboard", command="/packages"),
            _button("Update Name", command="/name", style="secondary"),
        ),
    )
