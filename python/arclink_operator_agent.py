#!/usr/bin/env python3
"""The Operator's single Hermes agent identity.

Captains can buy several agents; the Operator gets exactly ONE. That one agent
is a first-class service inside the Sovereign Control Node Compose stack, not a
tenant ArcPod and not a legacy shared-host Unix-user install. The control DB
still keeps a stable ``arclink_deployments`` identity row so the existing
operator chat, audit, notification, and command-scope paths have one canonical
subject to reference, but sovereign fleet workers must not provision or place it
like a Captain deployment.

This module is the single source of truth for that agent:

* ``ensure_operator_agent_user`` / ``ensure_operator_agent_deployment`` create
  (idempotently) the operator user and the single control-stack identity,
  enforcing the one-agent invariant.
* ``operator_agent_deployment`` / ``operator_conversation_routable`` resolve it.
* ``enqueue_operator_agent_turn`` routes a free-form operator message to that
  in-stack Hermes gateway through the existing ``public-agent-turn``
  notification worker with ``operator_turn`` metadata.

It is intentionally control-DB only: it queues and resolves, it never runs
Docker/SSH/provider commands. Runtime setup is handled by the Control Node
Compose services and ``bin/install-operator-hermes-home.sh``.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from typing import Any, Mapping


class OperatorAgentError(ValueError):
    pass


# Settings keys (arclink_settings) that pin the operator's single agent.
OPERATOR_AGENT_DEPLOYMENT_SETTING = "operator_agent_deployment_id"
OPERATOR_AGENT_USER_SETTING = "operator_agent_user_id"
OPERATOR_AGENT_RUNTIME_SETTING = "operator_agent_runtime"

# The reserved, stable identifiers for the operator's one agent. Stable ids keep
# rollout/restart semantics uniform and make the one-agent invariant obvious.
DEFAULT_OPERATOR_AGENT_DEPLOYMENT_ID = "operator"
DEFAULT_OPERATOR_AGENT_PREFIX = "operator-helm"
DEFAULT_OPERATOR_AGENT_USER_ID = "operator"
DEFAULT_OPERATOR_AGENT_RUNTIME = "control-stack"

# Deployment statuses a routable, talk-to-able operator agent can be in. Mirrors
# arclink_public_bots.ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES.
OPERATOR_AGENT_READY_STATUSES = frozenset({"active", "first_contacted"})


def ensure_operator_agent_user(
    conn: sqlite3.Connection,
    *,
    user_id: str = DEFAULT_OPERATOR_AGENT_USER_ID,
    email: str = "",
    display_name: str = "",
) -> dict[str, Any]:
    """Upsert the ArcLink user that owns the operator's single Hermes agent.

    The operator user is a comped account (entitlement ``comp``) so it never
    enters the Stripe billing lane; it is provisioned by the control node, not
    self-serve checkout.
    """
    from arclink_control import upsert_arclink_user, upsert_setting

    clean_user = str(user_id or "").strip() or DEFAULT_OPERATOR_AGENT_USER_ID
    user = upsert_arclink_user(
        conn,
        user_id=clean_user,
        email=str(email or "").strip(),
        display_name=str(display_name or "").strip() or "ArcLink Operator",
        status="active",
        entitlement_state="comp",
    )
    upsert_setting(conn, OPERATOR_AGENT_USER_SETTING, clean_user)
    return user


def ensure_operator_agent_deployment(
    conn: sqlite3.Connection,
    *,
    user_id: str = DEFAULT_OPERATOR_AGENT_USER_ID,
    deployment_id: str = DEFAULT_OPERATOR_AGENT_DEPLOYMENT_ID,
    prefix: str = DEFAULT_OPERATOR_AGENT_PREFIX,
    base_domain: str = "",
    status: str = "active",
    agent_title: str = "Operator Hermes",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Reserve the operator's single control-stack identity.

    Idempotent: re-running returns the existing operator deployment. Refuses to
    create a *second* operator agent -- if a different operator deployment is
    already pinned, this raises, so the operator can never accrue Captain-style
    multi-agent fan-out.
    """
    from arclink_control import (
        get_setting,
        reserve_arclink_deployment_prefix,
        upsert_setting,
    )

    clean_user = str(user_id or "").strip() or DEFAULT_OPERATOR_AGENT_USER_ID
    clean_deployment = str(deployment_id or "").strip() or DEFAULT_OPERATOR_AGENT_DEPLOYMENT_ID

    pinned = str(get_setting(conn, OPERATOR_AGENT_DEPLOYMENT_SETTING, "")).strip()
    if pinned and pinned != clean_deployment:
        existing = _deployment_row(conn, pinned)
        if existing is not None:
            raise OperatorAgentError(
                f"operator already has a single Hermes agent ({pinned}); refusing to create a second ({clean_deployment})"
            )
        # The pinned id no longer resolves to a row; allow re-pinning below.

    merged_metadata: dict[str, Any] = {
        "operator_agent": True,
        "operator_agent_runtime": DEFAULT_OPERATOR_AGENT_RUNTIME,
        "provisioning_mode": DEFAULT_OPERATOR_AGENT_RUNTIME,
        "not_arcpod": True,
        "bundle_agent_count": 1,
        "bundle_agent_index": 1,
    }
    if metadata:
        merged_metadata.update(dict(metadata))

    existing = _deployment_row(conn, clean_deployment)

    # The Operator owns the universe: their own Pod is metered/observable like a Captain
    # Pod but is effectively unlimited and never fails closed on budget, so Operator Raven
    # inference can always remedy the stack. Stamp budget_policy=observe_only_unlimited
    # while PRESERVING any accumulated chutes usage so the running total survives a control
    # re-deploy. See evaluate_chutes_deployment_boundary.
    from arclink_boundary import json_loads_safe

    operator_chutes: dict[str, Any] = {}
    if isinstance(merged_metadata.get("chutes"), Mapping):
        operator_chutes.update(dict(merged_metadata["chutes"]))
    if existing is not None:
        raw_existing_meta = existing.get("metadata_json")
        existing_meta = json_loads_safe(raw_existing_meta) if isinstance(raw_existing_meta, str) else raw_existing_meta
        if isinstance(existing_meta, Mapping) and isinstance(existing_meta.get("chutes"), Mapping):
            for key, value in dict(existing_meta["chutes"]).items():
                operator_chutes.setdefault(key, value)
    operator_chutes["monthly_budget_cents"] = 0
    operator_chutes["budget_policy"] = "observe_only_unlimited"
    merged_metadata["chutes"] = operator_chutes
    if existing is None:
        deployment = reserve_arclink_deployment_prefix(
            conn,
            deployment_id=clean_deployment,
            user_id=clean_user,
            prefix=prefix,
            base_domain=base_domain,
            agent_title=agent_title,
            status=status,
            metadata=merged_metadata,
        )
    else:
        deployment = _stamp_existing_operator_deployment(
            conn,
            existing,
            status=status,
            metadata=merged_metadata,
        )

    upsert_setting(conn, OPERATOR_AGENT_DEPLOYMENT_SETTING, clean_deployment)
    upsert_setting(conn, OPERATOR_AGENT_USER_SETTING, clean_user)
    upsert_setting(conn, OPERATOR_AGENT_RUNTIME_SETTING, DEFAULT_OPERATOR_AGENT_RUNTIME)
    return deployment


def operator_agent_deployment(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Resolve the operator's single agent deployment row, or None if unset."""
    from arclink_control import get_setting

    deployment_id = str(get_setting(conn, OPERATOR_AGENT_DEPLOYMENT_SETTING, "")).strip()
    if not deployment_id:
        return None
    return _deployment_row(conn, deployment_id)


def operator_agent_is_ready(deployment: Mapping[str, Any] | None) -> bool:
    if not deployment:
        return False
    return str(deployment.get("status") or "") in OPERATOR_AGENT_READY_STATUSES


def operator_conversation_routable(conn: sqlite3.Connection) -> bool:
    """True when the operator's free-form chat can reach a live Hermes agent."""
    return operator_agent_is_ready(operator_agent_deployment(conn))


def assert_single_operator_agent(conn: sqlite3.Connection) -> int:
    """Verify at most one operator-marked deployment exists. Returns the count."""
    count = 0
    try:
        rows = conn.execute(
            "SELECT metadata_json FROM arclink_deployments WHERE metadata_json LIKE '%\"operator_agent\"%'"
        ).fetchall()
    except sqlite3.Error:
        return 0
    from arclink_boundary import json_loads_safe

    for row in rows:
        meta = json_loads_safe(row["metadata_json"]) if not isinstance(row["metadata_json"], dict) else row["metadata_json"]
        if isinstance(meta, Mapping) and bool(meta.get("operator_agent")):
            count += 1
    if count > 1:
        raise OperatorAgentError(f"one-agent invariant violated: {count} operator agents exist")
    return count


def enqueue_operator_agent_turn(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    text: str,
    deployment: Mapping[str, Any] | None = None,
    reply_to_message_id: str = "",
    display_name: str = "",
    discord_channel_id: str = "",
    discord_user_id: str = "",
    discord_chat_type: str = "",
    platform_metadata: Mapping[str, Any] | None = None,
) -> int | None:
    """Queue a free-form operator message for the operator's one Hermes agent.

    Mirrors the Captain ``public-agent-turn`` enqueue, but stamps
    ``operator_turn`` so delivery uses the in-stack control-node gateway instead
    of a per-deployment ArcPod gateway. Returns the notification id, or None
    when no routable operator agent exists.
    """
    from arclink_control import append_arclink_event, queue_notification

    target = deployment if deployment is not None else operator_agent_deployment(conn)
    if not operator_agent_is_ready(target):
        return None
    clean_channel = str(channel or "").strip().lower()
    extra: dict[str, Any] = {
        "deployment_id": str(target.get("deployment_id") or ""),
        "prefix": str(target.get("prefix") or ""),
        "user_id": str(target.get("user_id") or ""),
        "agent_label": str(target.get("agent_title") or display_name or "Operator Hermes"),
        "source_kind": "operator_chat",
        "operator_turn": True,
    }
    if display_name:
        extra["display_name"] = display_name
    if platform_metadata:
        for key in ("telegram_update_kind", "telegram_update_json", "telegram_native_callback"):
            value = platform_metadata.get(key)
            if value not in (None, ""):
                extra[key] = value
    if clean_channel == "telegram" and reply_to_message_id:
        extra["telegram_reply_to_message_id"] = reply_to_message_id
    if clean_channel == "discord":
        if discord_channel_id:
            extra["discord_channel_id"] = discord_channel_id
        if discord_user_id:
            extra["discord_user_id"] = discord_user_id
        if discord_chat_type:
            extra["discord_chat_type"] = discord_chat_type
        if reply_to_message_id:
            extra["discord_message_id"] = reply_to_message_id
    notification_id = queue_notification(
        conn,
        target_kind="public-agent-turn",
        target_id=str(channel_identity or ""),
        channel_kind=clean_channel,
        message=str(text or ""),
        extra=extra,
    )
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=str(target.get("deployment_id") or ""),
        event_type="operator_agent:turn_queued",
        metadata={"channel": clean_channel, "source_kind": "operator_chat"},
    )
    return notification_id


def _deployment_row(conn: sqlite3.Connection, deployment_id: str) -> dict[str, Any] | None:
    clean = str(deployment_id or "").strip()
    if not clean:
        return None
    try:
        row = conn.execute(
            "SELECT * FROM arclink_deployments WHERE deployment_id = ?",
            (clean,),
        ).fetchone()
    except sqlite3.Error:
        return None
    return dict(row) if row is not None else None


def _stamp_existing_operator_deployment(
    conn: sqlite3.Connection,
    deployment: Mapping[str, Any],
    *,
    status: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge the control-stack operator stamp onto an existing row."""
    from arclink_boundary import json_loads_safe
    from arclink_control import json_dumps, utc_now_iso

    raw_metadata = deployment.get("metadata_json")
    current_metadata = json_loads_safe(raw_metadata) if isinstance(raw_metadata, str) else raw_metadata
    if not isinstance(current_metadata, Mapping):
        current_metadata = {}
    merged_metadata = {**dict(current_metadata), **dict(metadata)}
    clean_status = str(status or "").strip() or str(deployment.get("status") or "").strip() or "active"
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE arclink_deployments
           SET status = ?, metadata_json = ?, updated_at = ?
         WHERE deployment_id = ?
        """,
        (
            clean_status,
            json_dumps(merged_metadata),
            now,
            str(deployment.get("deployment_id") or ""),
        ),
    )
    conn.commit()
    updated = dict(deployment)
    updated["status"] = clean_status
    updated["metadata_json"] = json_dumps(merged_metadata)
    updated["updated_at"] = now
    return updated


def ensure_operator_agent(
    conn: sqlite3.Connection,
    *,
    user_id: str = DEFAULT_OPERATOR_AGENT_USER_ID,
    email: str = "",
    display_name: str = "",
    deployment_id: str = DEFAULT_OPERATOR_AGENT_DEPLOYMENT_ID,
    prefix: str = DEFAULT_OPERATOR_AGENT_PREFIX,
    base_domain: str = "",
    status: str = "active",
) -> dict[str, Any]:
    """Idempotently ensure the operator user and single control-stack identity.

    Defaults the row to ``active`` because the runtime is the Control Node's own
    Compose service set, not sovereign worker provisioning. Re-running is safe
    and never creates a second operator agent.
    """
    user = ensure_operator_agent_user(
        conn,
        user_id=user_id,
        email=email,
        display_name=display_name,
    )
    deployment = ensure_operator_agent_deployment(
        conn,
        user_id=str(user.get("user_id") or user_id),
        deployment_id=deployment_id,
        prefix=prefix,
        base_domain=base_domain,
        status=status,
    )
    return {
        "user_id": str(user.get("user_id") or user_id),
        "deployment_id": str(deployment.get("deployment_id") or deployment_id),
        "status": str(deployment.get("status") or status),
        "runtime": DEFAULT_OPERATOR_AGENT_RUNTIME,
        "single_agent_count": assert_single_operator_agent(conn),
    }


def _env_default(name: str, fallback: str) -> str:
    import os

    value = str(os.environ.get(name) or "").strip()
    return value or fallback


def _operator_agent_enabled() -> bool:
    import os

    raw = str(os.environ.get("ARCLINK_OPERATOR_AGENT_ENABLED") or "").strip().lower()
    if raw in {"", "1", "true", "yes", "on"}:
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage the operator's single in-stack Hermes agent identity.")
    sub = parser.add_subparsers(dest="command", required=True)
    ensure = sub.add_parser("ensure", help="Ensure the operator user + single control-stack identity exist (idempotent).")
    ensure.add_argument("--user-id", default=_env_default("ARCLINK_OPERATOR_AGENT_USER_ID", DEFAULT_OPERATOR_AGENT_USER_ID))
    ensure.add_argument("--email", default=_env_default("ARCLINK_OPERATOR_AGENT_EMAIL", ""))
    ensure.add_argument("--display-name", default=_env_default("ARCLINK_OPERATOR_AGENT_DISPLAY_NAME", ""))
    ensure.add_argument("--deployment-id", default=_env_default("ARCLINK_OPERATOR_AGENT_DEPLOYMENT_ID", DEFAULT_OPERATOR_AGENT_DEPLOYMENT_ID))
    ensure.add_argument("--prefix", default=_env_default("ARCLINK_OPERATOR_AGENT_PREFIX", DEFAULT_OPERATOR_AGENT_PREFIX))
    ensure.add_argument("--base-domain", default=_env_default("ARCLINK_OPERATOR_AGENT_BASE_DOMAIN", ""))
    ensure.add_argument(
        "--status",
        default=_env_default("ARCLINK_OPERATOR_AGENT_STATUS", "active"),
        help="Operator identity status (default active; runtime is the Control Node stack).",
    )
    ensure.add_argument(
        "--require-enabled",
        action="store_true",
        help="No-op unless ARCLINK_OPERATOR_AGENT_ENABLED is truthy (for unattended container boot).",
    )
    sub.add_parser("status", help="Print the operator agent deployment, if any.")
    args = parser.parse_args(argv)

    if args.command == "ensure" and getattr(args, "require_enabled", False) and not _operator_agent_enabled():
        print(json.dumps({"ok": True, "skipped": "operator_agent_disabled"}, sort_keys=True))
        return 0

    from arclink_control import Config, connect_db

    cfg = Config.from_env()
    conn = connect_db(cfg)
    try:
        if args.command == "ensure":
            try:
                result = ensure_operator_agent(
                    conn,
                    user_id=args.user_id,
                    email=args.email,
                    display_name=args.display_name,
                    deployment_id=args.deployment_id,
                    prefix=args.prefix,
                    base_domain=args.base_domain,
                    status=args.status,
                )
            except OperatorAgentError as exc:
                print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
                return 2
            print(json.dumps({"ok": True, **result}, sort_keys=True))
            return 0
        if args.command == "status":
            deployment = operator_agent_deployment(conn)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "deployment_id": str((deployment or {}).get("deployment_id") or ""),
                        "status": str((deployment or {}).get("status") or ""),
                        "routable": operator_conversation_routable(conn),
                    },
                    sort_keys=True,
                )
            )
            return 0
    finally:
        conn.close()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
