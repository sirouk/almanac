#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
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
ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES = frozenset({"active", "first_contacted"})
GITHUB_OWNER_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class ArcLinkPublicBotError(ValueError):
    pass


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


def _reply(session: Mapping[str, Any], *, action: str, reply: str) -> ArcLinkPublicBotTurn:
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
    )


def _turn(
    *,
    channel: str,
    channel_identity: str,
    action: str,
    reply: str,
    session: Mapping[str, Any] | None = None,
    deployment: Mapping[str, Any] | None = None,
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
    )


def _parse_answer(text: str, prefix: str) -> str:
    _, _, value = text.partition(prefix)
    return value.strip()


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
        "I can do that after your ArcLink pod exists. Send `/start` to begin onboarding, "
        "or finish checkout if you already have a session open."
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
        "Let’s connect Notion to your ArcLink pod.",
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
            "Create or choose a private GitHub repository for this pod’s Hermes home and configuration snapshots. "
            "Reply with `owner/repo` and ArcLink will keep the request attached to this deployment.\n\n"
            f"Example: `{example}`\n\n"
            "Use a dedicated deploy key for this pod. Do not reuse the ArcLink upstream key or the arclink-priv backup key."
        ),
        session=session,
        deployment=deployment,
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
            reply="Closed that ArcLink workflow. Send `/connect-notion` or `/config-backup` whenever you want to reopen it.",
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
                f"Recorded `{owner_repo}` for this pod’s private backup workflow.\n\n"
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
            "ArcLink bot commands:\n"
            "`/start` - begin onboarding\n"
            "`/status` - show onboarding status\n"
            "`/checkout` - open checkout when your plan is selected\n"
            "`/connect-notion` - connect your pod to Notion\n"
            "`/config-backup` - configure private pod backup\n"
            "`/cancel` - close the active workflow"
        ),
        session=session,
    )


def handle_arclink_public_bot_turn(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    text: str,
    stripe_client: Any | None = None,
    price_id: str = "price_arclink_starter",
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
            action="prompt_identity",
            reply="ArcLink deploys a private AI workspace. Send `email you@example.com` to continue.",
        )
    if command in {"status", "/status"}:
        return _reply(
            session,
            action="show_status",
            reply=f"Session {session['session_id']} is {session['status']}. Current step: {session['current_step'] or 'started'}.",
        )
    if command.startswith("email "):
        email = _parse_answer(message, " ")
        session = answer_arclink_onboarding_question(
            conn,
            session_id=str(session["session_id"]),
            question_key="email",
            answer_summary="email captured",
            email_hint=email,
        )
        return _reply(
            session,
            action="prompt_name",
            reply="Email saved. Send `name Your Name` next.",
        )
    if command.startswith("name "):
        name = _parse_answer(message, " ")
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
            reply="Name saved. Send `plan starter`, `plan operator`, or `plan scale`.",
        )
    if command.startswith("plan "):
        plan = _parse_answer(command, " ")
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
            reply="Plan saved. Send `checkout` to open the no-secret checkout contract.",
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
            reply=f"Checkout opened: {session['checkout_url']}",
        )
    return _reply(
        session,
        action="prompt_command",
        reply="Use `email`, `name`, `plan`, `checkout`, `status`, `/connect-notion`, or `/config-backup`.",
    )
