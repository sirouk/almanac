#!/usr/bin/env python3
"""Sovereign fleet enrollment tokens, worker attestation, and audit chain."""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import sqlite3
import sys
from typing import Any, Mapping, Sequence

from arclink_boundary import json_dumps_safe, json_loads_safe
from arclink_control import (
    Config,
    append_arclink_audit,
    connect_db,
    ensure_schema,
    queue_notification,
    utc_now_iso,
    parse_utc_iso,
)
from arclink_inventory import register_inventory_machine
from arclink_secrets_regex import redact_then_truncate


TOKEN_PREFIX = "arcfleet_v1"
DEFAULT_ENROLLMENT_TTL_SECONDS = 3600
DEFAULT_MAX_ENROLLMENT_CAPACITY_SLOTS = 64
_FINGERPRINT_RE = re.compile(r"^[A-Za-z0-9_.:=+/@-]{16,256}$")
_WIREGUARD_PUBLIC_KEY_RE = re.compile(r"^[A-Za-z0-9+/=]{20,100}$")
_HOST_VALUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$")
_SSH_USER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$")
_WIREGUARD_INTERFACE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,15}$")
_WIREGUARD_FIREWALL_STATUS_RE = re.compile(r"^[A-Za-z0-9_.:@/+,-]{0,64}$")
_SSH_PUBLIC_KEY_RE = re.compile(r"^(ssh-ed25519|ssh-rsa|ecdsa-sha2-[A-Za-z0-9_-]+|sk-ssh-ed25519@openssh.com|sk-ecdsa-sha2-[A-Za-z0-9_-]+@openssh.com) [A-Za-z0-9+/=]+(?: .*)?$")


class ArcLinkFleetEnrollmentError(ValueError):
    pass


def _fleet_enrollment_id() -> str:
    return f"flenr_{secrets.token_hex(12)}"


def _chain_entry_id() -> str:
    return f"fachain_{secrets.token_hex(12)}"


def _resolve_secret(secret: str = "") -> bytes:
    value = str(
        secret
        or os.environ.get("ARCLINK_FLEET_ENROLLMENT_SECRET", "")
    ).strip()
    if not value:
        raise ArcLinkFleetEnrollmentError("fleet enrollment HMAC secret is required")
    return value.encode("utf-8")


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _sign_token_parts(*, secret: str = "", enrollment_id: str, nonce: str) -> str:
    key = _resolve_secret(secret)
    signing_input = f"{TOKEN_PREFIX}.{enrollment_id}.{nonce}".encode("utf-8")
    return _b64url(hmac.new(key, signing_input, hashlib.sha256).digest())


def _token_hash(token: str, *, secret: str = "") -> str:
    key = _resolve_secret(secret)
    digest = hmac.new(key, f"fleet-enrollment-token:{token}".encode("utf-8"), hashlib.sha256).hexdigest()
    return f"hmac_sha256_v1${digest}"


def _parse_token(token: str) -> tuple[str, str, str]:
    parts = str(token or "").strip().split(".")
    if len(parts) != 4 or parts[0] != TOKEN_PREFIX:
        raise ArcLinkFleetEnrollmentError("invalid enrollment token")
    enrollment_id, nonce, sig = parts[1], parts[2], parts[3]
    if not enrollment_id.startswith("flenr_") or len(nonce) < 16 or len(sig) < 32:
        raise ArcLinkFleetEnrollmentError("invalid enrollment token")
    return enrollment_id, nonce, sig


def _require_pending_enrollment(
    conn: sqlite3.Connection,
    *,
    token: str,
    secret: str = "",
    now_iso: str = "",
) -> sqlite3.Row:
    enrollment_id, nonce, sig = _parse_token(token)
    expected_sig = _sign_token_parts(secret=secret, enrollment_id=enrollment_id, nonce=nonce)
    if not hmac.compare_digest(sig, expected_sig):
        raise ArcLinkFleetEnrollmentError("invalid enrollment token")
    row = conn.execute(
        "SELECT * FROM arclink_fleet_enrollments WHERE enrollment_id = ?",
        (enrollment_id,),
    ).fetchone()
    if row is None:
        raise ArcLinkFleetEnrollmentError("unknown enrollment token")
    expected_hash = str(row["token_hash"] or "")
    if not hmac.compare_digest(expected_hash, _token_hash(token, secret=secret)):
        raise ArcLinkFleetEnrollmentError("invalid enrollment token")
    status = str(row["status"] or "")
    now = parse_utc_iso(now_iso or utc_now_iso())
    expires = parse_utc_iso(str(row["expires_at"] or ""))
    if status == "pending" and expires is not None and now is not None and expires <= now:
        conn.execute(
            "UPDATE arclink_fleet_enrollments SET status = 'expired' WHERE enrollment_id = ? AND status = 'pending'",
            (enrollment_id,),
        )
        conn.commit()
        status = "expired"
    if status != "pending":
        raise ArcLinkFleetEnrollmentError(f"enrollment token is {status or 'unavailable'}")
    return row


def _clean_optional_wireguard_public_key(value: Any) -> str:
    clean = str(value or "").strip()
    if not clean:
        return ""
    clean = re.sub(r"\s+", "", clean)
    if not _WIREGUARD_PUBLIC_KEY_RE.fullmatch(clean):
        raise ArcLinkFleetEnrollmentError("invalid WireGuard public key")
    return clean


def _clean_optional_wireguard_cidr(value: Any) -> str:
    clean = str(value or "").strip()
    if not clean:
        return ""
    if "/" not in clean:
        try:
            prefix = 128 if ipaddress.ip_address(clean).version == 6 else 32
        except ValueError:
            prefix = 32
        clean = f"{clean}/{prefix}"
    if any(ch in clean for ch in "\x00\r\n"):
        raise ArcLinkFleetEnrollmentError("invalid WireGuard private CIDR")
    try:
        interface = ipaddress.ip_interface(clean)
    except ValueError as exc:
        raise ArcLinkFleetEnrollmentError("invalid WireGuard private CIDR") from exc
    return str(interface)


def mint_fleet_enrollment(
    conn: sqlite3.Connection,
    *,
    created_by_user_id: str,
    ttl_seconds: int = DEFAULT_ENROLLMENT_TTL_SECONDS,
    secret: str = "",
    enrollment_id: str = "",
    now_iso: str = "",
) -> dict[str, Any]:
    clean_actor = str(created_by_user_id or "").strip() or "operator"
    clean_id = str(enrollment_id or "").strip() or _fleet_enrollment_id()
    nonce = _b64url(secrets.token_bytes(24))
    sig = _sign_token_parts(secret=secret, enrollment_id=clean_id, nonce=nonce)
    token = f"{TOKEN_PREFIX}.{clean_id}.{nonce}.{sig}"
    now = now_iso or utc_now_iso()
    now_dt = parse_utc_iso(now)
    if now_dt is None:
        raise ArcLinkFleetEnrollmentError("invalid enrollment timestamp")
    expires_at = (now_dt.timestamp() + max(1, int(ttl_seconds)))
    import datetime as dt

    expires_iso = dt.datetime.fromtimestamp(expires_at, dt.timezone.utc).replace(microsecond=0).isoformat()
    conn.execute(
        """
        INSERT INTO arclink_fleet_enrollments (
          enrollment_id, token_hash, created_by_user_id, created_at, expires_at, status
        ) VALUES (?, ?, ?, ?, ?, 'pending')
        """,
        (clean_id, _token_hash(token, secret=secret), clean_actor, now, expires_iso),
    )
    append_arclink_audit(
        conn,
        action="fleet_enrollment_minted",
        actor_id=clean_actor,
        target_kind="fleet_enrollment",
        target_id=clean_id,
        reason="operator minted fleet enrollment token",
        metadata={"expires_at": expires_iso},
        commit=False,
    )
    conn.commit()
    return {
        "enrollment_id": clean_id,
        "token": token,
        "created_by_user_id": clean_actor,
        "created_at": now,
        "expires_at": expires_iso,
        "status": "pending",
    }


def list_fleet_enrollments(
    conn: sqlite3.Connection,
    *,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    where = "" if include_inactive else "WHERE status = 'pending'"
    rows = conn.execute(
        f"""
        SELECT enrollment_id, created_by_user_id, created_at, expires_at,
               consumed_at, redeemed_by_inventory_id, status, audit_ref
        FROM arclink_fleet_enrollments
        {where}
        ORDER BY created_at DESC, enrollment_id DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _public_enrollment_row(row: sqlite3.Row | Mapping[str, Any]) -> dict[str, Any]:
    source = dict(row)
    return {
        "enrollment_id": str(source.get("enrollment_id") or ""),
        "created_by_user_id": str(source.get("created_by_user_id") or ""),
        "created_at": str(source.get("created_at") or ""),
        "expires_at": str(source.get("expires_at") or ""),
        "consumed_at": str(source.get("consumed_at") or ""),
        "redeemed_by_inventory_id": str(source.get("redeemed_by_inventory_id") or ""),
        "status": str(source.get("status") or ""),
        "audit_ref": str(source.get("audit_ref") or ""),
    }


def revoke_fleet_enrollment(
    conn: sqlite3.Connection,
    *,
    enrollment_id: str,
    actor: str = "operator",
) -> dict[str, Any]:
    clean_id = str(enrollment_id or "").strip()
    row = conn.execute("SELECT * FROM arclink_fleet_enrollments WHERE enrollment_id = ?", (clean_id,)).fetchone()
    if row is None:
        raise ArcLinkFleetEnrollmentError("unknown fleet enrollment")
    if str(row["status"] or "") == "pending":
        conn.execute(
            "UPDATE arclink_fleet_enrollments SET status = 'revoked' WHERE enrollment_id = ? AND status = 'pending'",
            (clean_id,),
        )
        append_arclink_audit(
            conn,
            action="fleet_enrollment_revoked",
            actor_id=str(actor or "operator"),
            target_kind="fleet_enrollment",
            target_id=clean_id,
            reason="operator revoked fleet enrollment token",
            metadata={},
            commit=False,
        )
        conn.commit()
    return _public_enrollment_row(
        conn.execute("SELECT * FROM arclink_fleet_enrollments WHERE enrollment_id = ?", (clean_id,)).fetchone()
    )


def expire_pending_fleet_enrollments(
    conn: sqlite3.Connection,
    *,
    now_iso: str = "",
    notify: bool = False,
) -> int:
    now = now_iso or utc_now_iso()
    cur = conn.execute(
        "UPDATE arclink_fleet_enrollments SET status = 'expired' WHERE status = 'pending' AND expires_at <= ?",
        (now,),
    )
    count = int(cur.rowcount or 0)
    if notify and count > 0:
        queue_notification(
            conn,
            target_kind="operator",
            target_id="fleet-enrollment-expiry",
            channel_kind="tui-only",
            message=f"ArcLink expired {count} pending fleet enrollment token(s).",
            extra={"severity": "P2", "expired_count": count},
        )
    conn.commit()
    return count


def record_fleet_enrollment_secret_rotation(
    conn: sqlite3.Connection,
    *,
    actor: str = "operator",
    reason: str = "",
) -> dict[str, Any]:
    """Record an operator HMAC-root rotation and revoke outstanding tokens."""
    clean_actor = str(actor or "").strip() or "operator"
    clean_reason = redact_then_truncate(str(reason or "operator rotated fleet enrollment HMAC root"), limit=180)
    now = utc_now_iso()
    cur = conn.execute(
        """
        UPDATE arclink_fleet_enrollments
        SET status = 'revoked'
        WHERE status = 'pending'
        """
    )
    revoked = int(cur.rowcount or 0)
    append_arclink_audit(
        conn,
        action="fleet_enrollment_hmac_root_rotated",
        actor_id=clean_actor,
        target_kind="fleet_enrollment_secret",
        target_id="hmac-root",
        reason=clean_reason,
        metadata={"revoked_pending_enrollments": revoked, "rotated_at": now},
        commit=False,
    )
    conn.commit()
    return {
        "rotated": True,
        "rotated_at": now,
        "actor": clean_actor,
        "revoked_pending_enrollments": revoked,
    }


def _clean_fingerprint(value: Any) -> str:
    text = str(value or "").strip()
    if not _FINGERPRINT_RE.match(text):
        raise ArcLinkFleetEnrollmentError("invalid machine fingerprint")
    return text


def _clean_host_value(value: Any, *, label: str, required: bool = False) -> str:
    text = str(value or "").strip().lower().strip(".")
    if not text:
        if required:
            raise ArcLinkFleetEnrollmentError(f"{label} is required")
        return ""
    if any(ch in text for ch in "\x00\r\n") or not _HOST_VALUE_RE.fullmatch(text):
        raise ArcLinkFleetEnrollmentError(f"invalid {label}")
    return text


def _clean_hostname(value: Any) -> str:
    return _clean_host_value(value, label="worker hostname", required=True)


def _clean_optional_hostname(value: Any) -> str:
    return _clean_host_value(value, label="host name")


def _clean_ssh_user(value: Any) -> str:
    text = str(value or "arclink").strip()
    if not _SSH_USER_RE.fullmatch(text):
        raise ArcLinkFleetEnrollmentError("invalid SSH user")
    return text


def _clean_optional_wireguard_interface(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if any(ch in text for ch in "\x00\r\n") or not _WIREGUARD_INTERFACE_RE.fullmatch(text):
        raise ArcLinkFleetEnrollmentError("invalid WireGuard interface")
    return text


def _clean_optional_wireguard_endpoint(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if any(ch in text for ch in "\x00\r\n"):
        raise ArcLinkFleetEnrollmentError("invalid WireGuard control endpoint")
    host, sep, port_text = text.rpartition(":")
    if not sep or not host or not port_text:
        raise ArcLinkFleetEnrollmentError("invalid WireGuard control endpoint")
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    _clean_host_value(host, label="WireGuard control endpoint host", required=True)
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ArcLinkFleetEnrollmentError("invalid WireGuard control endpoint") from exc
    if port < 1 or port > 65535:
        raise ArcLinkFleetEnrollmentError("invalid WireGuard control endpoint")
    if ":" in host:
        return f"[{host}]:{port}"
    return f"{host}:{port}"


def _clean_optional_wireguard_firewall_status(value: Any) -> str:
    text = str(value or "").strip().lower()[:64]
    if any(ch in text for ch in "\x00\r\n") or not _WIREGUARD_FIREWALL_STATUS_RE.fullmatch(text):
        raise ArcLinkFleetEnrollmentError("invalid WireGuard firewall status")
    return text


def _clean_optional_abs_path(value: Any, *, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "\x00" in text or "\n" in text or "\r" in text or not text.startswith("/") or text == "/":
        raise ArcLinkFleetEnrollmentError(f"invalid {label}")
    return text[:512]


def _clean_optional_ssh_public_key(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if not _SSH_PUBLIC_KEY_RE.fullmatch(text):
        raise ArcLinkFleetEnrollmentError("invalid fleet-share SSH public key")
    return text[:2048]


def _safe_mapping(value: Any, *, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ArcLinkFleetEnrollmentError(f"{label} must be an object")
    return json.loads(json_dumps_safe(dict(value), label="ArcLink fleet enrollment", error_cls=ArcLinkFleetEnrollmentError))


def _bounded_capacity_slots(value: Any) -> int:
    try:
        requested = int(value or 4)
    except (TypeError, ValueError) as exc:
        raise ArcLinkFleetEnrollmentError("invalid worker capacity slots") from exc
    try:
        maximum = int(os.environ.get("ARCLINK_FLEET_ENROLLMENT_MAX_CAPACITY_SLOTS") or DEFAULT_MAX_ENROLLMENT_CAPACITY_SLOTS)
    except (TypeError, ValueError):
        maximum = DEFAULT_MAX_ENROLLMENT_CAPACITY_SLOTS
    return max(1, min(max(1, maximum), requested))


def _audit_chain_secret(secret: str = "") -> str:
    return str(
        secret
        or os.environ.get("ARCLINK_FLEET_AUDIT_CHAIN_SECRET", "")
        or os.environ.get("ARCLINK_FLEET_ENROLLMENT_SECRET", "")
    ).strip()


def _chain_hash(
    *,
    inventory_id: str,
    event: str,
    actor: str,
    event_at: str,
    prev_hash: str,
    metadata_json: str,
    secret: str = "",
) -> str:
    payload = {
        "actor": actor,
        "event": event,
        "event_at": event_at,
        "inventory_id": inventory_id,
        "metadata": json_loads_safe(metadata_json),
        "prev_hash": prev_hash,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    key = _audit_chain_secret(secret)
    if key:
        return "hmac_sha256_v1$" + hmac.new(key.encode("utf-8"), encoded, hashlib.sha256).hexdigest()
    return hashlib.sha256(encoded).hexdigest()


def append_fleet_audit_chain_entry(
    conn: sqlite3.Connection,
    *,
    inventory_id: str,
    event: str,
    actor: str,
    metadata: Mapping[str, Any] | None = None,
    event_at: str = "",
    audit_secret: str = "",
) -> dict[str, Any]:
    if event not in {"enrolled", "verified", "activated", "degraded", "drained", "resumed", "removed", "re-attested"}:
        raise ArcLinkFleetEnrollmentError(f"unsupported fleet audit-chain event: {event}")
    clean_inventory = str(inventory_id or "").strip()
    if not clean_inventory:
        raise ArcLinkFleetEnrollmentError("fleet audit-chain entry requires an inventory id")
    clean_actor = str(actor or "").strip() or "system:fleet"
    metadata_json = json_dumps_safe(metadata, label="ArcLink fleet audit chain", error_cls=ArcLinkFleetEnrollmentError)
    previous = conn.execute(
        """
        SELECT entry_hash
        FROM arclink_fleet_audit_chain
        WHERE inventory_id = ?
        ORDER BY rowid DESC
        LIMIT 1
        """,
        (clean_inventory,),
    ).fetchone()
    prev_hash = str(previous["entry_hash"] or "") if previous is not None else ""
    clean_event_at = event_at or utc_now_iso()
    entry_hash = _chain_hash(
        inventory_id=clean_inventory,
        event=event,
        actor=clean_actor,
        event_at=clean_event_at,
        prev_hash=prev_hash,
        metadata_json=metadata_json,
        secret=audit_secret,
    )
    entry_id = _chain_entry_id()
    conn.execute(
        """
        INSERT INTO arclink_fleet_audit_chain (
          entry_id, inventory_id, event, actor, event_at, prev_hash, entry_hash, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (entry_id, clean_inventory, event, clean_actor, clean_event_at, prev_hash, entry_hash, metadata_json),
    )
    return dict(conn.execute("SELECT * FROM arclink_fleet_audit_chain WHERE entry_id = ?", (entry_id,)).fetchone())


def consume_fleet_enrollment(
    conn: sqlite3.Connection,
    *,
    token: str,
    payload: Mapping[str, Any],
    secret: str = "",
    actor: str = "worker-bootstrap",
    source_ip: str = "",
    source_ip_trust: str = "",
) -> dict[str, Any]:
    enrollment = _require_pending_enrollment(conn, token=token, secret=secret)
    body = dict(payload or {})
    fingerprint = _clean_fingerprint(body.get("machine_fingerprint") or body.get("fingerprint"))
    hostname = _clean_hostname(body.get("hostname"))
    ssh_host = _clean_host_value(body.get("ssh_host") or hostname, label="SSH host", required=True)
    tailscale_dns_name = _clean_optional_hostname(
        body.get("tailscale_dns_name")
        or body.get("tailnet_dns_name")
        or body.get("magicdns_name")
        or ""
    )
    private_dns_name = _clean_optional_hostname(
        body.get("private_dns_name")
        or body.get("wireguard_dns_name")
        or body.get("private_mesh_dns_name")
        or ""
    )
    wireguard_private_cidr = _clean_optional_wireguard_cidr(
        body.get("wireguard_private_cidr")
        or body.get("wireguard_worker_cidr")
        or body.get("wireguard_worker_ip")
        or body.get("wireguard_private_ip")
        or ""
    )
    wireguard_private_ip = ""
    wireguard_private_ip_raw = str(body.get("wireguard_private_ip") or "").strip()
    if wireguard_private_ip_raw:
        wireguard_private_ip_cidr = _clean_optional_wireguard_cidr(wireguard_private_ip_raw)
        wireguard_private_ip = wireguard_private_ip_cidr.split("/", 1)[0]
        if wireguard_private_cidr and wireguard_private_ip != wireguard_private_cidr.split("/", 1)[0]:
            raise ArcLinkFleetEnrollmentError("WireGuard private IP does not match private CIDR")
        if not wireguard_private_cidr:
            wireguard_private_cidr = wireguard_private_ip_cidr
    elif wireguard_private_cidr:
        wireguard_private_ip = wireguard_private_cidr.split("/", 1)[0]
    wireguard_public_key = _clean_optional_wireguard_public_key(body.get("wireguard_public_key") or "")
    wireguard_interface = _clean_optional_wireguard_interface(body.get("wireguard_interface") or "")
    wireguard_control_endpoint = _clean_optional_wireguard_endpoint(body.get("wireguard_control_endpoint") or "")
    wireguard_firewall_status = _clean_optional_wireguard_firewall_status(body.get("wireguard_firewall_status") or "")
    if (wireguard_private_cidr or wireguard_public_key) and not wireguard_interface:
        wireguard_interface = "wg-arclink"
    fleet_share_ssh_key_path = _clean_optional_abs_path(body.get("fleet_share_ssh_key_path"), label="fleet-share SSH key path")
    fleet_share_known_hosts_file = _clean_optional_abs_path(
        body.get("fleet_share_ssh_known_hosts_file"),
        label="fleet-share SSH known_hosts path",
    )
    fleet_share_public_key = _clean_optional_ssh_public_key(body.get("fleet_share_ssh_public_key"))
    try:
        wireguard_listen_port = int(body.get("wireguard_listen_port") or 0)
    except (TypeError, ValueError) as exc:
        raise ArcLinkFleetEnrollmentError("invalid WireGuard listen port") from exc
    if wireguard_listen_port < 0 or wireguard_listen_port > 65535:
        raise ArcLinkFleetEnrollmentError("invalid WireGuard listen port")
    if not private_dns_name and wireguard_private_ip:
        private_dns_name = _clean_optional_hostname(wireguard_private_ip)
    if not tailscale_dns_name and ssh_host.strip().lower().endswith(".ts.net"):
        tailscale_dns_name = _clean_optional_hostname(ssh_host)
    ssh_user = _clean_ssh_user(body.get("ssh_user") or "arclink")
    region = str(body.get("region") or "").strip().lower()
    capacity_slots = _bounded_capacity_slots(body.get("capacity_slots") or 4)
    provider = str(body.get("provider") or "manual").strip().lower()
    if provider not in {"local", "manual", "hetzner", "linode"}:
        raise ArcLinkFleetEnrollmentError("unsupported worker provider")
    hardware = _safe_mapping(body.get("hardware_summary"), label="hardware_summary")
    connectivity = _safe_mapping(body.get("connectivity_summary"), label="connectivity_summary")
    prereq_audit = _safe_mapping(body.get("prereq_audit"), label="prereq_audit")
    tags = _safe_mapping(body.get("tags"), label="tags")
    metadata = {
        "ssh_host": ssh_host,
        "ssh_user": ssh_user,
        "enrollment_id": str(enrollment["enrollment_id"]),
        "enrollment_pending_probe": True,
        "prereq_audit": prereq_audit,
    }
    if tailscale_dns_name:
        metadata["tailscale_dns_name"] = tailscale_dns_name
        metadata["control_network_mode"] = "remote"
    if private_dns_name:
        metadata["private_dns_name"] = private_dns_name
        metadata["control_network_mode"] = "remote"
    if wireguard_private_cidr or wireguard_public_key:
        metadata["wireguard"] = {
            "interface": wireguard_interface,
            "private_ip": wireguard_private_ip,
            "private_cidr": wireguard_private_cidr,
            "public_key": wireguard_public_key,
            "control_endpoint": wireguard_control_endpoint,
            "listen_port": wireguard_listen_port,
            "firewall_status": wireguard_firewall_status,
        }
        metadata["control_network_mode"] = "remote"
    if fleet_share_ssh_key_path or fleet_share_public_key:
        metadata["fleet_share"] = {
            "ssh_key_path": fleet_share_ssh_key_path,
            "known_hosts_file": fleet_share_known_hosts_file,
            "public_key": fleet_share_public_key,
            "transport": "worker-local-ssh-key",
        }
    if source_ip:
        metadata["source_ip"] = source_ip
    clean_source_ip_trust = str(source_ip_trust or "").strip()
    if clean_source_ip_trust:
        metadata["source_ip_trust"] = clean_source_ip_trust

    existing = conn.execute(
        """
        SELECT machine_id, machine_fingerprint
        FROM arclink_inventory_machines
        WHERE status != 'removed'
          AND (enrollment_id = ? OR LOWER(hostname) = LOWER(?))
        ORDER BY registered_at ASC
        LIMIT 1
        """,
        (str(enrollment["enrollment_id"]), hostname),
    ).fetchone()
    if existing is not None:
        existing_fp = str(existing["machine_fingerprint"] or "")
        if existing_fp and not hmac.compare_digest(existing_fp, fingerprint):
            raise ArcLinkFleetEnrollmentError("machine fingerprint mismatch; explicit re-attest required")

    # H7: the host+machine enrollment is one read->merge->write critical section.
    # register_inventory_machine(commit=False) borrows OUR transaction and in turn
    # calls register_fleet_host(commit=False), whose existence SELECT -> image_sync_*
    # merge -> whole-metadata_json UPDATE only runs under a write lock if WE hold one.
    # Without an outer BEGIN IMMEDIATE the merge runs in autocommit and a concurrent
    # liveness/gate metadata write committing between our read and our write can drop
    # the image_sync_* placement-gate keys -> a host wrongly becomes placement-eligible.
    # So we own (begin + commit/rollback) the transaction here whenever we are in
    # autocommit; a caller that handed us an already-open txn governs the lock itself.
    own_txn = not conn.in_transaction
    if own_txn:
        conn.execute("BEGIN IMMEDIATE")
    try:
        machine = register_inventory_machine(
            conn,
            provider=provider,
            hostname=hostname,
            ssh_host=ssh_host,
            ssh_user=ssh_user,
            region=region,
            status="pending",
            hardware_summary=hardware,
            connectivity_summary={
                **connectivity,
                "ok": False,
                "status": "awaiting_control_probe",
            },
            capacity_slots=capacity_slots,
            tags=tags,
            metadata=metadata,
            commit=False,
        )
        now = utc_now_iso()
        conn.execute(
            """
            UPDATE arclink_inventory_machines
            SET enrollment_id = ?, machine_fingerprint = ?, attested_at = ?, last_probed_at = ?
            WHERE machine_id = ?
            """,
            (str(enrollment["enrollment_id"]), fingerprint, now, now, str(machine["machine_id"])),
        )
        host_id = str(machine.get("machine_host_link") or "").strip()
        if host_id:
            conn.execute(
                """
                UPDATE arclink_fleet_hosts
                SET status = 'degraded', drain = 1, last_health_state = 'awaiting_control_probe',
                    capacity_slots = ?, updated_at = ?
                WHERE host_id = ?
                """,
                (capacity_slots, now, host_id),
            )
        consumed = conn.execute(
            """
            UPDATE arclink_fleet_enrollments
            SET status = 'consumed', consumed_at = ?, redeemed_by_inventory_id = ?
            WHERE enrollment_id = ? AND status = 'pending'
            """,
            (now, str(machine["machine_id"]), str(enrollment["enrollment_id"])),
        )
        if int(consumed.rowcount or 0) != 1:
            raise ArcLinkFleetEnrollmentError("enrollment token could not be consumed")
        root = append_fleet_audit_chain_entry(
            conn,
            inventory_id=str(machine["machine_id"]),
            event="enrolled",
            actor=str(actor or "worker-bootstrap"),
            metadata={
                "enrollment_id": str(enrollment["enrollment_id"]),
                "hostname": hostname,
                "provider": provider,
                "private_dns_name": private_dns_name,
                "tailscale_dns_name": tailscale_dns_name,
                "wireguard_private_ip": wireguard_private_ip,
                "fleet_share_transport": "worker-local-ssh-key" if fleet_share_public_key else "",
            },
            audit_secret=secret,
        )
        verified = append_fleet_audit_chain_entry(
            conn,
            inventory_id=str(machine["machine_id"]),
            event="verified",
            actor=str(actor or "worker-bootstrap"),
            metadata={
                "enrollment_id": str(enrollment["enrollment_id"]),
                "hostname": hostname,
                "region": region,
                "capacity_slots": capacity_slots,
                "placement_state": "awaiting_control_probe",
                "private_dns_name": private_dns_name,
                "tailscale_dns_name": tailscale_dns_name,
                "wireguard_private_ip": wireguard_private_ip,
                "fleet_share_transport": "worker-local-ssh-key" if fleet_share_public_key else "",
            },
            audit_secret=secret,
        )
        conn.execute(
            "UPDATE arclink_inventory_machines SET audit_trail_chain = ? WHERE machine_id = ?",
            (str(verified["entry_hash"]), str(machine["machine_id"])),
        )
        conn.execute(
            "UPDATE arclink_fleet_enrollments SET audit_ref = ? WHERE enrollment_id = ?",
            (str(root["entry_id"]), str(enrollment["enrollment_id"])),
        )
        append_arclink_audit(
            conn,
            action="fleet_enrollment_consumed",
            actor_id=str(actor or "worker-bootstrap"),
            target_kind="inventory_machine",
            target_id=str(machine["machine_id"]),
            reason="worker attested with fleet enrollment token",
            metadata={
                "enrollment_id": str(enrollment["enrollment_id"]),
                "hostname": hostname,
                "host_id": str(machine.get("machine_host_link") or ""),
                "private_dns_name": private_dns_name,
                "tailscale_dns_name": tailscale_dns_name,
                "wireguard_private_ip": wireguard_private_ip,
                "fleet_share_transport": "worker-local-ssh-key" if fleet_share_public_key else "",
            },
            commit=False,
        )
        if own_txn:
            conn.commit()
    except Exception:
        # Only roll back the transaction WE own. A caller that handed us an already-open
        # txn governs its own rollback -- we must not tear down its transaction.
        if own_txn and conn.in_transaction:
            conn.rollback()
        raise
    machine = dict(conn.execute("SELECT * FROM arclink_inventory_machines WHERE machine_id = ?", (str(machine["machine_id"]),)).fetchone())
    return {
        "enrollment_id": str(enrollment["enrollment_id"]),
        "machine_id": str(machine["machine_id"]),
        "host_id": str(machine.get("machine_host_link") or ""),
        "hostname": str(machine["hostname"]),
        "private_dns_name": private_dns_name,
        "tailscale_dns_name": tailscale_dns_name,
        "wireguard_private_ip": wireguard_private_ip,
        "wireguard_private_cidr": wireguard_private_cidr,
        "wireguard_public_key": wireguard_public_key,
        "fleet_share_ssh_public_key": fleet_share_public_key,
        "fleet_share_ssh_key_path": fleet_share_ssh_key_path,
        "status": str(machine["status"]),
        "attested_at": str(machine["attested_at"]),
        "audit_chain_root": str(root["entry_id"]),
        "audit_chain_head": str(verified["entry_hash"]),
    }


def reattest_inventory_machine(
    conn: sqlite3.Connection,
    *,
    key: str,
    machine_fingerprint: str,
    actor: str = "operator",
    reason: str = "",
) -> dict[str, Any]:
    clean = str(key or "").strip()
    fingerprint = _clean_fingerprint(machine_fingerprint)
    machine = conn.execute(
        """
        SELECT *
        FROM arclink_inventory_machines
        WHERE machine_id = ? OR LOWER(hostname) = LOWER(?)
        LIMIT 1
        """,
        (clean, clean),
    ).fetchone()
    if machine is None:
        raise ArcLinkFleetEnrollmentError(f"unknown inventory machine: {key}")
    if str(machine["status"] or "") == "removed":
        raise ArcLinkFleetEnrollmentError("removed inventory machines cannot be re-attested")
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE arclink_inventory_machines
        SET machine_fingerprint = ?, attested_at = ?
        WHERE machine_id = ?
        """,
        (fingerprint, now, str(machine["machine_id"])),
    )
    entry = append_fleet_audit_chain_entry(
        conn,
        inventory_id=str(machine["machine_id"]),
        event="re-attested",
        actor=str(actor or "operator"),
        metadata={
            "hostname": str(machine["hostname"] or ""),
            "reason": redact_then_truncate(str(reason or "operator re-attestation"), limit=160),
        },
    )
    conn.execute(
        "UPDATE arclink_inventory_machines SET audit_trail_chain = ? WHERE machine_id = ?",
        (str(entry["entry_hash"]), str(machine["machine_id"])),
    )
    append_arclink_audit(
        conn,
        action="inventory_machine_re_attested",
        actor_id=str(actor or "operator"),
        target_kind="inventory_machine",
        target_id=str(machine["machine_id"]),
        reason="operator explicitly re-attested inventory machine fingerprint",
        metadata={"hostname": str(machine["hostname"] or ""), "audit_chain_entry": str(entry["entry_id"])},
        commit=False,
    )
    conn.commit()
    refreshed = conn.execute(
        "SELECT machine_id, hostname, status, attested_at, audit_trail_chain FROM arclink_inventory_machines WHERE machine_id = ?",
        (str(machine["machine_id"]),),
    ).fetchone()
    return dict(refreshed)


def verify_fleet_audit_chain(
    conn: sqlite3.Connection,
    *,
    inventory_id: str = "",
    notify: bool = False,
    secret: str = "",
) -> dict[str, Any]:
    clean_inventory = str(inventory_id or "").strip()
    chain_secret = _audit_chain_secret(secret)
    params: list[Any] = []
    where = ""
    if clean_inventory:
        where = "WHERE inventory_id = ?"
        params.append(clean_inventory)
    rows = conn.execute(
        f"""
        SELECT *
        FROM arclink_fleet_audit_chain
        {where}
        ORDER BY inventory_id ASC, rowid ASC
        """,
        params,
    ).fetchall()
    errors: list[dict[str, Any]] = []
    prev_by_inventory: dict[str, str] = {}
    for row in rows:
        inv = str(row["inventory_id"] or "")
        expected_prev = prev_by_inventory.get(inv, "")
        actual_prev = str(row["prev_hash"] or "")
        metadata_json = str(row["metadata_json"] or "{}")
        expected_hash = _chain_hash(
            inventory_id=inv,
            event=str(row["event"] or ""),
            actor=str(row["actor"] or ""),
            event_at=str(row["event_at"] or ""),
            prev_hash=actual_prev,
            metadata_json=metadata_json,
            secret=chain_secret,
        )
        actual_hash = str(row["entry_hash"] or "")
        if actual_prev != expected_prev:
            errors.append({"entry_id": str(row["entry_id"]), "inventory_id": inv, "error": "prev_hash_mismatch"})
        if actual_hash.startswith("hmac_sha256_v1$"):
            if not chain_secret:
                errors.append({"entry_id": str(row["entry_id"]), "inventory_id": inv, "error": "audit_hmac_secret_missing"})
            elif not hmac.compare_digest(actual_hash, expected_hash):
                errors.append({"entry_id": str(row["entry_id"]), "inventory_id": inv, "error": "entry_hash_mismatch"})
        else:
            if chain_secret:
                errors.append({"entry_id": str(row["entry_id"]), "inventory_id": inv, "error": "legacy_unkeyed_entry"})
                prev_by_inventory[inv] = actual_hash
                continue
            legacy_hash = _chain_hash(
                inventory_id=inv,
                event=str(row["event"] or ""),
                actor=str(row["actor"] or ""),
                event_at=str(row["event_at"] or ""),
                prev_hash=actual_prev,
                metadata_json=metadata_json,
                secret="",
            )
            if not hmac.compare_digest(actual_hash, legacy_hash):
                errors.append({"entry_id": str(row["entry_id"]), "inventory_id": inv, "error": "entry_hash_mismatch"})
        prev_by_inventory[inv] = actual_hash
    if errors and notify:
        queue_notification(
            conn,
            target_kind="operator",
            target_id="fleet-audit-chain",
            channel_kind="tui-only",
            message="P0: ArcLink fleet audit-chain integrity check failed.",
            extra={"severity": "P0", "errors": errors[:10]},
        )
    return {
        "ok": not errors,
        "checked_entries": len(rows),
        "checked_inventories": len(prev_by_inventory),
        "errors": errors,
    }


def _redacted_error(exc: Exception) -> str:
    return redact_then_truncate(str(exc), limit=220)


def _load_conn(db_path: str = "") -> sqlite3.Connection:
    if db_path:
        conn = sqlite3.connect(db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 15000")
        conn.execute("PRAGMA foreign_keys = ON")
        ensure_schema(conn)
        return conn
    return connect_db(Config.from_env())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arclink-fleet-enrollment")
    parser.add_argument("--db", default=os.environ.get("ARCLINK_DB_PATH", ""))
    sub = parser.add_subparsers(dest="command", required=True)
    mint = sub.add_parser("mint")
    mint.add_argument("--actor", default=os.environ.get("USER", "operator"))
    mint.add_argument("--ttl-seconds", type=int, default=DEFAULT_ENROLLMENT_TTL_SECONDS)
    mint.add_argument("--json", action="store_true")
    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--all", action="store_true")
    list_cmd.add_argument("--json", action="store_true")
    revoke = sub.add_parser("revoke")
    revoke.add_argument("enrollment_id")
    revoke.add_argument("--actor", default=os.environ.get("USER", "operator"))
    revoke.add_argument("--json", action="store_true")
    rotate = sub.add_parser("rotate-secret")
    rotate.add_argument("--actor", default=os.environ.get("USER", "operator"))
    rotate.add_argument("--reason", default="")
    rotate.add_argument("--json", action="store_true")
    verify = sub.add_parser("verify-audit-chain")
    verify.add_argument("--inventory-id", default="")
    verify.add_argument("--notify", action="store_true")
    verify.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    conn: sqlite3.Connection | None = None
    try:
        conn = _load_conn(args.db)
        if args.command == "mint":
            result = mint_fleet_enrollment(conn, created_by_user_id=args.actor, ttl_seconds=args.ttl_seconds)
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.command == "list":
            result = {"enrollments": list_fleet_enrollments(conn, include_inactive=args.all)}
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.command == "revoke":
            result = revoke_fleet_enrollment(conn, enrollment_id=args.enrollment_id, actor=args.actor)
            print(json.dumps({"enrollment": result}, sort_keys=True))
            return 0
        if args.command == "rotate-secret":
            result = record_fleet_enrollment_secret_rotation(conn, actor=args.actor, reason=args.reason)
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.command == "verify-audit-chain":
            result = verify_fleet_audit_chain(conn, inventory_id=args.inventory_id, notify=args.notify)
            print(json.dumps(result, sort_keys=True))
            return 0
        return 1
    except Exception as exc:
        print(_redacted_error(exc), file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
