#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
from typing import Any, Mapping

from arclink_api_auth import ArcLinkApiAuthError, check_arclink_rate_limit
from arclink_boundary import json_loads_safe, rowdict
from arclink_control import (
    append_arclink_audit,
    append_arclink_event,
    queue_notification,
    utc_now,
    utc_now_iso,
)


POD_COMMS_RESOURCE_KIND = "pod_comms"
POD_MESSAGE_RATE_LIMIT = 60
POD_MESSAGE_RATE_WINDOW_SECONDS = 60
POD_MESSAGE_MAX_BODY_CHARS = 8000
POD_MESSAGE_MAX_ATTACHMENTS = 10


def _deployment(conn: sqlite3.Connection, deployment_id: str, *, label: str) -> dict[str, Any]:
    clean = str(deployment_id or "").strip()
    if not clean:
        raise ValueError(f"{label} deployment id is required")
    row = conn.execute(
        """
        SELECT deployment_id, user_id, agent_id, agent_name, agent_title, status
        FROM arclink_deployments
        WHERE deployment_id = ?
        """,
        (clean,),
    ).fetchone()
    if row is None:
        raise KeyError(clean)
    deployment = rowdict(row)
    if not str(deployment.get("user_id") or "").strip():
        raise PermissionError(f"{label} deployment is not linked to a Captain")
    return deployment


def _new_message_id(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT lower(hex(randomblob(12))) AS suffix").fetchone()
    return f"podmsg_{row['suffix']}"


def _grant_is_time_active(grant: Mapping[str, Any]) -> bool:
    if str(grant.get("status") or "") != "accepted":
        return False
    if str(grant.get("revoked_at") or ""):
        return False
    expires_at = str(grant.get("expires_at") or "").strip()
    if not expires_at:
        return True
    try:
        from arclink_control import parse_utc_iso

        parsed = parse_utc_iso(expires_at)
    except Exception:
        parsed = None
    return parsed is not None and parsed > utc_now()


def _grant_matches_deployments(
    grant: Mapping[str, Any],
    *,
    sender_deployment_id: str,
    recipient_deployment_id: str,
) -> bool:
    metadata = json_loads_safe(str(grant.get("metadata_json") or "{}"))
    owner_dep = str(metadata.get("owner_deployment_id") or metadata.get("deployment_id") or "").strip()
    recipient_dep = str(metadata.get("recipient_deployment_id") or "").strip()
    if not owner_dep and not recipient_dep:
        return True
    pair = {sender_deployment_id, recipient_deployment_id}
    present = {value for value in (owner_dep, recipient_dep) if value}
    return present <= pair


def find_active_pod_comms_grant(
    conn: sqlite3.Connection,
    *,
    sender_user_id: str,
    recipient_user_id: str,
    sender_deployment_id: str = "",
    recipient_deployment_id: str = "",
) -> dict[str, Any] | None:
    rows = conn.execute(
        """
        SELECT *
        FROM arclink_share_grants
        WHERE resource_kind = ?
          AND (
            (owner_user_id = ? AND recipient_user_id = ?)
            OR (owner_user_id = ? AND recipient_user_id = ?)
          )
        ORDER BY accepted_at DESC, created_at DESC
        """,
        (
            POD_COMMS_RESOURCE_KIND,
            sender_user_id,
            recipient_user_id,
            recipient_user_id,
            sender_user_id,
        ),
    ).fetchall()
    for row in rows:
        grant = rowdict(row)
        if not _grant_is_time_active(grant):
            continue
        if sender_deployment_id and recipient_deployment_id and not _grant_matches_deployments(
            grant,
            sender_deployment_id=sender_deployment_id,
            recipient_deployment_id=recipient_deployment_id,
        ):
            continue
        return grant
    return None


def _require_send_allowed(
    conn: sqlite3.Connection,
    *,
    sender: Mapping[str, Any],
    recipient: Mapping[str, Any],
) -> dict[str, Any] | None:
    sender_user = str(sender.get("user_id") or "")
    recipient_user = str(recipient.get("user_id") or "")
    if sender_user == recipient_user:
        return None
    grant = find_active_pod_comms_grant(
        conn,
        sender_user_id=sender_user,
        recipient_user_id=recipient_user,
        sender_deployment_id=str(sender.get("deployment_id") or ""),
        recipient_deployment_id=str(recipient.get("deployment_id") or ""),
    )
    if grant is None:
        raise PermissionError("cross-Captain Pod Comms requires an active pod_comms share grant")
    return grant


def _clean_body(body: str) -> str:
    text = str(body or "").strip()
    if not text:
        raise ValueError("Pod Comms message body is required")
    if len(text) > POD_MESSAGE_MAX_BODY_CHARS:
        raise ValueError("Pod Comms message body is too long")
    return text


def _public_message(row: Mapping[str, Any]) -> dict[str, Any]:
    try:
        parsed_attachments = json.loads(str(row.get("attachments_json") or "[]"))
    except json.JSONDecodeError:
        parsed_attachments = []
    attachments = parsed_attachments if isinstance(parsed_attachments, list) else []
    status = str(row.get("status") or "")
    return {
        "message_id": str(row.get("message_id") or ""),
        "sender_deployment_id": str(row.get("sender_deployment_id") or ""),
        "recipient_deployment_id": str(row.get("recipient_deployment_id") or ""),
        "sender_user_id": str(row.get("sender_user_id") or ""),
        "recipient_user_id": str(row.get("recipient_user_id") or ""),
        "body": "" if status == "redacted" else str(row.get("body") or ""),
        "attachments": attachments,
        "status": status,
        "created_at": str(row.get("created_at") or ""),
        "delivered_at": str(row.get("delivered_at") or ""),
        "audit_id": str(row.get("audit_id") or ""),
    }


def _message_by_id(conn: sqlite3.Connection, message_id: str) -> dict[str, Any]:
    clean = str(message_id or "").strip()
    if not clean:
        raise ValueError("Pod Comms message id is required")
    row = conn.execute("SELECT * FROM arclink_pod_messages WHERE message_id = ?", (clean,)).fetchone()
    if row is None:
        raise KeyError(clean)
    return rowdict(row)


def _validate_attachment_refs(
    conn: sqlite3.Connection,
    *,
    sender: Mapping[str, Any],
    recipient: Mapping[str, Any],
    attachments: list[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not attachments:
        return []
    if len(attachments) > POD_MESSAGE_MAX_ATTACHMENTS:
        raise ValueError("Pod Comms message has too many attachments")
    clean: list[dict[str, Any]] = []
    for index, item in enumerate(attachments):
        if not isinstance(item, Mapping):
            raise ValueError("Pod Comms attachments must be share projection references")
        grant_id = str(item.get("grant_id") or item.get("share_grant_id") or "").strip()
        if not grant_id:
            raise ValueError("Pod Comms attachments require a share grant reference")
        row = conn.execute("SELECT * FROM arclink_share_grants WHERE grant_id = ?", (grant_id,)).fetchone()
        if row is None:
            raise PermissionError("Pod Comms attachment share grant was not found")
        grant = rowdict(row)
        if not _grant_is_time_active(grant):
            raise PermissionError("Pod Comms attachment requires an active accepted share grant")
        users = {str(sender.get("user_id") or ""), str(recipient.get("user_id") or "")}
        if {str(grant.get("owner_user_id") or ""), str(grant.get("recipient_user_id") or "")} - users:
            raise PermissionError("Pod Comms attachment share grant is outside this conversation")
        clean.append(
            {
                "grant_id": grant_id,
                "resource_kind": str(grant.get("resource_kind") or ""),
                "resource_root": str(grant.get("resource_root") or ""),
                "resource_path": str(grant.get("resource_path") or ""),
                "display_name": str(grant.get("display_name") or item.get("label") or ""),
                "projection": json_loads_safe(str(grant.get("metadata_json") or "{}")).get("projection", {}),
                "index": index,
            }
        )
    return clean


def send_pod_message(
    conn: sqlite3.Connection,
    *,
    sender_deployment_id: str,
    recipient_deployment_id: str,
    body: str,
    attachments: list[Mapping[str, Any]] | None = None,
    actor_id: str = "",
) -> dict[str, Any]:
    sender = _deployment(conn, sender_deployment_id, label="sender")
    recipient = _deployment(conn, recipient_deployment_id, label="recipient")
    if str(sender["deployment_id"]) == str(recipient["deployment_id"]):
        raise ValueError("Pod Comms requires distinct sender and recipient Pods")

    comms_grant = _require_send_allowed(conn, sender=sender, recipient=recipient)
    clean_body = _clean_body(body)
    clean_attachments = _validate_attachment_refs(conn, sender=sender, recipient=recipient, attachments=attachments)
    check_arclink_rate_limit(
        conn,
        scope=f"pod_comms:{sender['deployment_id']}",
        subject=str(sender["deployment_id"]),
        limit=POD_MESSAGE_RATE_LIMIT,
        window_seconds=POD_MESSAGE_RATE_WINDOW_SECONDS,
        commit=False,
    )

    now = utc_now_iso()
    message_id = _new_message_id(conn)
    audit_id = append_arclink_audit(
        conn,
        action="pod_message_sent",
        actor_id=str(actor_id or sender.get("agent_id") or sender["deployment_id"]),
        target_kind="pod_message",
        target_id=message_id,
        reason="Pod Comms message queued",
        metadata={
            "sender_deployment_id": sender["deployment_id"],
            "recipient_deployment_id": recipient["deployment_id"],
            "sender_user_id": sender["user_id"],
            "recipient_user_id": recipient["user_id"],
            "pod_comms_grant_id": str(comms_grant.get("grant_id") or "") if comms_grant else "",
            "attachment_count": len(clean_attachments),
        },
        commit=False,
    )
    conn.execute(
        """
        INSERT INTO arclink_pod_messages (
          message_id, sender_deployment_id, recipient_deployment_id,
          sender_user_id, recipient_user_id, body, attachments_json, status,
          created_at, delivered_at, audit_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?, '', ?)
        """,
        (
            message_id,
            sender["deployment_id"],
            recipient["deployment_id"],
            sender["user_id"],
            recipient["user_id"],
            clean_body,
            json.dumps(clean_attachments, sort_keys=True),
            now,
            audit_id,
        ),
    )
    append_arclink_event(
        conn,
        subject_kind="pod_message",
        subject_id=message_id,
        event_type="pod_message_sent",
        metadata={
            "sender_deployment_id": sender["deployment_id"],
            "recipient_deployment_id": recipient["deployment_id"],
            "attachment_count": len(clean_attachments),
        },
        commit=False,
    )
    conn.commit()

    notification_id = queue_notification(
        conn,
        target_kind="user-agent",
        target_id=str(recipient.get("agent_id") or recipient["deployment_id"]),
        channel_kind="pod-message",
        message=clean_body,
        extra={
            "message_id": message_id,
            "sender_deployment_id": sender["deployment_id"],
            "recipient_deployment_id": recipient["deployment_id"],
            "sender_agent_name": str(sender.get("agent_name") or ""),
            "attachments": clean_attachments,
        },
    )
    message = rowdict(conn.execute("SELECT * FROM arclink_pod_messages WHERE message_id = ?", (message_id,)).fetchone())
    return {"ok": True, "message": _public_message(message), "notification_id": notification_id}


def list_pod_messages(
    conn: sqlite3.Connection,
    *,
    deployment_id: str = "",
    user_id: str = "",
    direction: str = "all",
    limit: int = 50,
) -> dict[str, Any]:
    clean_direction = str(direction or "all").strip().lower()
    if clean_direction not in {"all", "inbox", "outbox"}:
        raise ValueError("Pod Comms direction must be all, inbox, or outbox")
    clean_limit = max(1, min(200, int(limit or 50)))
    clauses: list[str] = []
    params: list[Any] = []
    if deployment_id:
        dep = str(deployment_id).strip()
        if clean_direction == "inbox":
            clauses.append("recipient_deployment_id = ?")
            params.append(dep)
        elif clean_direction == "outbox":
            clauses.append("sender_deployment_id = ?")
            params.append(dep)
        else:
            clauses.append("(sender_deployment_id = ? OR recipient_deployment_id = ?)")
            params.extend([dep, dep])
    if user_id:
        user = str(user_id).strip()
        if clean_direction == "inbox":
            clauses.append("recipient_user_id = ?")
            params.append(user)
        elif clean_direction == "outbox":
            clauses.append("sender_user_id = ?")
            params.append(user)
        else:
            clauses.append("(sender_user_id = ? OR recipient_user_id = ?)")
            params.extend([user, user])
    if not clauses:
        raise ValueError("Pod Comms listing requires deployment_id or user_id")
    where = " AND ".join(f"({clause})" for clause in clauses)
    rows = conn.execute(
        f"""
        SELECT *
        FROM arclink_pod_messages
        WHERE {where}
        ORDER BY created_at DESC, message_id DESC
        LIMIT ?
        """,
        (*params, clean_limit),
    ).fetchall()
    return {
        "messages": [_public_message(rowdict(row)) for row in rows],
        "direction": clean_direction,
        "deployment_id": str(deployment_id or ""),
        "user_id": str(user_id or ""),
        "limit": clean_limit,
    }


def list_all_pod_messages(conn: sqlite3.Connection, *, limit: int = 200) -> dict[str, Any]:
    clean_limit = max(1, min(500, int(limit or 200)))
    rows = conn.execute(
        """
        SELECT *
        FROM arclink_pod_messages
        ORDER BY created_at DESC, message_id DESC
        LIMIT ?
        """,
        (clean_limit,),
    ).fetchall()
    return {"messages": [_public_message(rowdict(row)) for row in rows], "limit": clean_limit}


def mark_pod_message_delivered(
    conn: sqlite3.Connection,
    *,
    message_id: str,
    actor_id: str = "",
) -> dict[str, Any]:
    message = _message_by_id(conn, message_id)
    if str(message.get("status") or "") == "redacted":
        raise ValueError("redacted Pod Comms messages cannot be marked delivered")
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE arclink_pod_messages
        SET status = 'delivered', delivered_at = ?
        WHERE message_id = ?
        """,
        (now, message["message_id"]),
    )
    append_arclink_audit(
        conn,
        action="pod_message_delivered",
        actor_id=str(actor_id or "notification-delivery"),
        target_kind="pod_message",
        target_id=str(message["message_id"]),
        reason="Pod Comms message delivered",
        metadata={
            "sender_deployment_id": str(message.get("sender_deployment_id") or ""),
            "recipient_deployment_id": str(message.get("recipient_deployment_id") or ""),
        },
        commit=False,
    )
    append_arclink_event(
        conn,
        subject_kind="pod_message",
        subject_id=str(message["message_id"]),
        event_type="pod_message_delivered",
        metadata={"recipient_deployment_id": str(message.get("recipient_deployment_id") or "")},
        commit=False,
    )
    conn.commit()
    updated = _message_by_id(conn, message_id)
    return {"ok": True, "message": _public_message(updated)}


def redact_pod_message(
    conn: sqlite3.Connection,
    *,
    message_id: str,
    actor_id: str,
    reason: str = "",
) -> dict[str, Any]:
    message = _message_by_id(conn, message_id)
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE arclink_pod_messages
        SET status = 'redacted', body = '', attachments_json = '[]', delivered_at = CASE WHEN delivered_at = '' THEN ? ELSE delivered_at END
        WHERE message_id = ?
        """,
        (now, message["message_id"]),
    )
    append_arclink_audit(
        conn,
        action="pod_message_redacted",
        actor_id=str(actor_id or "operator"),
        target_kind="pod_message",
        target_id=str(message["message_id"]),
        reason=str(reason or "Pod Comms message redacted"),
        metadata={
            "sender_deployment_id": str(message.get("sender_deployment_id") or ""),
            "recipient_deployment_id": str(message.get("recipient_deployment_id") or ""),
        },
        commit=False,
    )
    append_arclink_event(
        conn,
        subject_kind="pod_message",
        subject_id=str(message["message_id"]),
        event_type="pod_message_redacted",
        metadata={"reason": str(reason or "")[:160]},
        commit=False,
    )
    conn.commit()
    updated = _message_by_id(conn, message_id)
    return {"ok": True, "message": _public_message(updated)}
