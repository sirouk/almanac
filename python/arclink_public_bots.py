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
from arclink_control import append_arclink_event, utc_now_iso
from arclink_onboarding import (
    answer_arclink_onboarding_question,
    create_or_resume_arclink_onboarding_session,
    open_arclink_onboarding_checkout,
)
from arclink_product import base_domain as default_base_domain
from arclink_product import chutes_default_model


ARCLINK_PUBLIC_BOT_CHANNELS = frozenset({"telegram", "discord"})
ARCLINK_PUBLIC_BOT_PLANS = frozenset({"starter", "operator", "scale"})
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
ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES = frozenset({"active", "first_contacted"})
ARCLINK_PUBLIC_BOT_AGENT_SWITCH_RE = re.compile(r"^/(?:agent[-_])([a-z0-9][a-z0-9_-]{0,31})$")
GITHUB_OWNER_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


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
        description="Choose starter, operator, or scale",
        discord_options=(
            {
                "type": 3,
                "name": "tier",
                "description": "ArcLink plan",
                "required": True,
                "choices": [
                    {"name": "Starter", "value": "starter"},
                    {"name": "Operator", "value": "operator"},
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


def _agent_label(deployment: Mapping[str, Any], *, index: int = 0) -> str:
    metadata = _metadata(deployment)
    candidate = str(metadata.get("agent_name") or metadata.get("display_name") or "").strip()
    if candidate:
        return candidate[:40]
    agent_id = str(deployment.get("agent_id") or "").strip()
    if agent_id:
        return agent_id[:40]
    prefix = str(deployment.get("prefix") or "").strip()
    if prefix:
        return prefix.replace("arc-", "").replace("-", " ").title()[:40]
    return f"Agent {index + 1}"


def _agent_slug(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(label or "").strip().lower()).strip("-")
    return slug or "agent"


def _metadata(row: Mapping[str, Any] | None) -> dict[str, Any]:
    return json_loads_safe(str((row or {}).get("metadata_json") or "{}"))


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


def _need_finished_onboarding_reply() -> str:
    return (
        "I can open that system once your first agent is aboard ArcLink. Send `/start` to board the vessel, "
        "or finish checkout if your launch is already in motion."
    )


def _deployment_not_ready_reply(deployment: Mapping[str, Any]) -> str:
    status = str(deployment.get("status") or "unknown").strip()
    if status == "entitlement_required":
        return "Your pod is reserved, but billing is not complete yet. Send `checkout` to finish activation."
    if status == "provisioning_failed":
        return "Your pod exists, but provisioning needs operator attention before I can run this workflow."
    return f"Your pod is currently `{status}`. I can continue once provisioning reaches active."


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
        "Let's connect Notion to your ArcLink pod.",
        "",
        "Use this callback URL in the Notion webhook/subscription setup:",
        callback_url or "(callback URL is not available yet)",
        "",
        "Then share the page or database with the ArcLink integration. Do not paste Notion tokens into chat; use the secure dashboard secret field when it is requested.",
        "",
        "Reply `ready` when Notion has sent the verification handshake, or `cancel` to close this workflow.",
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
            "Private backup setup is open.\n\n"
            "Create or choose a private GitHub repository for this pod's Hermes home and configuration snapshots. "
            "Reply with `owner/repo` and ArcLink will keep the request attached to this deployment.\n\n"
            f"Example: `{example}`\n\n"
            "Use a dedicated deploy key for this pod. Do not reuse the ArcLink upstream key or the arclink-priv backup key."
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
                "Your ArcLink crew manifest is empty. Hire the first weapons-grade agent for $35/month, "
                "then I can help you add more specialized agents at $15/month each."
            ),
            session=session,
            buttons=(
                _button("Board ArcLink", command="/start"),
            ),
        )
    user_id = str(deployment.get("user_id") or session.get("user_id") or "").strip()
    deployments = _deployments_for_user(conn, user_id)
    active_id = str(deployment.get("deployment_id") or "")
    buttons: list[ArcLinkPublicBotButton] = []
    lines = [
        "ArcLink crew manifest",
        "",
        "ArcLink is your private agentic vessel: SOTA inference rails, managed memory, tools, vault, and deployment health. "
        "Every agent here is tied to your account and current mission path.",
        "",
    ]
    for index, item in enumerate(deployments):
        label = _agent_label(item, index=index)
        status = str(item.get("status") or "unknown")
        marker = "active" if str(item.get("deployment_id") or "") == active_id else status
        lines.append(f"- {label}: {marker}")
        if str(item.get("deployment_id") or "") != active_id:
            buttons.append(_button(f"Take Helm: {label}", command=f"/agent-{_agent_slug(label)}"))
    if deployments:
        buttons.append(_button("Add Crew - $15/mo", command="/add-agent"))
    if not buttons and deployments:
        buttons.append(_button("Add Crew - $15/mo", command="/add-agent"))
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
        label = _agent_label(item, index=index)
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
                reply=f"Helm transferred to {label}. Notion, backup, and system workflows now target that ArcLink agent.",
                session=updated,
                deployment=item,
                buttons=(
                    _button("Open Crew", command="/agents", style="secondary"),
                    _button("Check Systems", command="/status", style="secondary"),
                ),
            )
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="switch_agent_not_found",
        reply="I do not see that agent on your ArcLink crew manifest. Open `/agents` and use the account-aware helm buttons I show you there.",
        session=session,
        deployment=deployment,
        buttons=(_button("Open Crew", command="/agents"),),
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
    base_domain: str,
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
    price_id = str(additional_agent_price_id or "").strip()
    if not price_id:
        raise ArcLinkPublicBotError("additional agent checkout requires ARCLINK_ADDITIONAL_AGENT_PRICE_ID")

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
        selected_plan_id="additional_agent",
        selected_model_id=chutes_default_model({}),
        current_step="additional_agent",
        metadata={
            "purchase_kind": "additional_agent",
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
            "A new ArcLink crew bay is ready at $15/month. Hire the additional agent through Stripe and I will move that pod into the launch queue."
        ),
        buttons=(
            _button("Hire Additional Agent", url=str(extra_session.get("checkout_url") or "")),
            _button("Back to Crew", command="/agents", style="secondary"),
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
            reply="Closed that ArcLink workflow. Your pod path is still ready when you are. Send `/connect_notion` or `/config_backup` to reopen a setup lane.",
            session=updated,
            deployment=deployment,
        )
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
                reply="Good. I recorded Notion as ready for this pod. If the webhook still says verification is not configured, open the dashboard Notion panel so ArcLink can arm the verification-token install window.",
                session=updated,
                deployment=deployment,
            )
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="prompt_notion_ready",
            reply="Reply `ready` after Notion sends the verification handshake, or `cancel` to close the Notion workflow.",
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
                reply="Send the private GitHub repository as `owner/repo`, or reply `cancel` to close backup setup.",
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
                f"Recorded `{owner_repo}` for this pod's private backup workflow.\n\n"
                "Keep the repository private. ArcLink will use a dedicated pod deploy key with write access; "
                "when the key is prepared, add it here:\n"
                f"{settings_url}\n\n"
                "I also wrote this to the deployment event stream so the admin dashboard can track it."
            ),
            session=updated,
            deployment=deployment,
        )
    return None


def _help_reply(*, channel: str, channel_identity: str, session: Mapping[str, Any] | None = None) -> ArcLinkPublicBotTurn:
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="show_help",
        reply=(
            "Raven comms deck\n\n"
            "I am Raven, your guide aboard ArcLink. ArcLink is the vessel and the harness: private deployment, SOTA model rails, managed memory, tools, files, Notion/backup workflows, and live health checks. You choose the mission; I get the systems online.\n\n"
            "`/start` - board ArcLink and open the launch path\n"
            "`/name Your Name` - name the mission owner\n"
            "`/plan starter` - choose starter, operator, or scale\n"
            "`/checkout` - hire your first $35/month agent\n"
            "`/status` - run a systems check\n"
            "`/agents` - open your account-aware crew manifest\n"
            "`/connect_notion` - connect Notion to the active pod\n"
            "`/config_backup` - configure private pod backup\n"
            "`/cancel` - close the active setup lane"
        ),
        session=session,
        buttons=(
            _button("Board ArcLink", command="/start"),
            _button("View Crew", command="/agents", style="secondary"),
        ),
    )


def handle_arclink_public_bot_turn(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    text: str,
    stripe_client: Any | None = None,
    price_id: str = "price_arclink_starter",
    additional_agent_price_id: str = "",
    base_domain: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> ArcLinkPublicBotTurn:
    clean_channel = _clean_channel(channel)
    clean_identity = _clean_identity(channel_identity)
    _check_public_bot_rate_limit(conn, channel=clean_channel, channel_identity=clean_identity)
    message = str(text or "").strip()
    command = message.lower()

    if command in ARCLINK_PUBLIC_BOT_HELP_COMMANDS:
        return _help_reply(
            channel=clean_channel,
            channel_identity=clean_identity,
            session=_latest_session_for_contact(conn, channel=clean_channel, channel_identity=clean_identity),
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

    session = create_or_resume_arclink_onboarding_session(
        conn,
        channel=clean_channel,
        channel_identity=clean_identity,
        selected_model_id=chutes_default_model({}),
        metadata=metadata,
    )

    if command in {"", "/start", "start", "restart"}:
        return _reply(
            session,
            action="prompt_name",
            reply=(
                "Raven online. ArcLink is in range.\n\n"
                "I am your guide aboard the vessel: a private agentic harness with weapons-grade agents, SOTA model rails, memory, tools, files, and deployment health already wired in. Answer a few clean prompts, hire the first agent, and I move your pod toward launch.\n\n"
                "Stripe will collect your email securely at checkout. Send `/name Your Name` and I will shape the first mission around you."
            ),
            buttons=(
                _button("Choose Mission Tier", command="/plan starter", style="secondary"),
                _button("Open Comms", command="/help", style="secondary"),
            ),
        )
    if command in {"status", "/status"}:
        context_session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        deployment_label = _agent_label(deployment or {}, index=0) if deployment else ""
        return _reply(
            context_session or session,
            action="show_status",
            reply=(
                f"Raven status: session `{(context_session or session)['session_id']}` is `{(context_session or session)['status']}`. "
                f"Current launch step: `{(context_session or session)['current_step'] or 'started'}`."
                + (f"\nActive agent: {deployment_label}." if deployment_label else "")
            ),
            buttons=(
                _button("View Crew", command="/agents", style="secondary"),
                _button("Hire First Agent", command="/checkout", style="secondary"),
            ),
        )
    email = _command_value(message, command, ("email", "/email"))
    if email is not None:
        return _reply(
            session,
            action="prompt_name",
            reply="I do not need your email in chat. Stripe collects it securely at checkout. Send `/name Your Name` and I will shape the first ArcLink mission around you.",
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
        return _reply(
            session,
            action="prompt_plan",
            reply=(
                "Mission owner saved. Choose the tier. Starter boards your first ArcLink agent for $35/month; "
                "additional crew can join for $15/month once your first pod is active."
            ),
            buttons=(
                _button("Starter Crew - $35/mo", command="/plan starter"),
                _button("Operator", command="/plan operator", style="secondary"),
                _button("Scale", command="/plan scale", style="secondary"),
            ),
        )
    plan_answer = _command_value(message, command, ("plan", "/plan"))
    if plan_answer is not None:
        plan = plan_answer.strip().lower()
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
        return _reply(
            session,
            action="prompt_checkout",
            reply="Tier locked. Hit Hire First Agent when you are ready to make the ArcLink vessel real through secure Stripe checkout.",
            buttons=(
                _button("Hire First Agent - $35/mo", command="/checkout"),
                _button("Change Tier", command="/plan starter", style="secondary"),
            ),
        )
    if command in {"checkout", "/checkout"}:
        if stripe_client is None:
            raise ArcLinkPublicBotError("checkout requires an injected Stripe client")
        root = f"https://{str(base_domain or default_base_domain({})).strip().strip('/')}"
        session = open_arclink_onboarding_checkout(
            conn,
            session_id=str(session["session_id"]),
            stripe_client=stripe_client,
            price_id=price_id,
            success_url=f"{root}/checkout/success",
            cancel_url=f"{root}/checkout/cancel",
            base_domain=base_domain or default_base_domain({}),
        )
        return _reply(
            session,
            action="open_checkout",
            reply=(
                "Checkout is armed. Hire your first ArcLink agent through Stripe; when payment clears, I move the pod from manifest to launch queue."
            ),
            buttons=(
                _button("Hire First Agent", url=str(session.get("checkout_url") or "")),
                _button("Check Systems", command="/status", style="secondary"),
            ),
        )
    return _reply(
        session,
        action="prompt_command",
            reply=(
                "Raven is online. ArcLink is the vessel I am guiding you toward: inference, memory, tools, vault, and deployment health in one private agentic harness.\n\n"
                "Use `/start` to board, `/agents` for your crew, `/help` for comms, `/connect_notion` for Notion, or `/config_backup` for private backups."
            ),
        buttons=(
            _button("Board ArcLink", command="/start"),
            _button("View Crew", command="/agents", style="secondary"),
        ),
    )
