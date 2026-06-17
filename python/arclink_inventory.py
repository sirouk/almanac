#!/usr/bin/env python3
"""Control-node inventory registry and local CLI."""
from __future__ import annotations

import argparse
import ipaddress
import json
import math
import os
import re
import secrets
import shlex
import sqlite3
import subprocess
import sys
from typing import Any, Callable, Mapping, Sequence

from arclink_asu import ArcLinkASUError, compute_asu, current_load
from arclink_boundary import json_dumps_safe, json_loads_safe
from arclink_control import (
    Config,
    append_arclink_audit,
    complete_arclink_operation_idempotency,
    connect_db,
    ensure_schema,
    fail_arclink_operation_idempotency,
    replay_arclink_operation_idempotency,
    reserve_arclink_operation_idempotency,
    utc_now_iso,
)
from arclink_fleet import list_fleet_hosts, register_fleet_host, update_fleet_host
from arclink_secrets_regex import redact_then_truncate


class ArcLinkInventoryError(ValueError):
    pass


RunFn = Callable[..., subprocess.CompletedProcess[str]]
CLOUD_INVENTORY_PROVIDERS = frozenset({"hetzner", "linode"})
FLEET_JOIN_SCRIPT = "bin/arclink-fleet-join.sh"
FLEET_PREREQ_LIBRARY = "bin/lib/ensure-prereqs.sh"
_HOST_VALUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$")
_SSH_USER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$")
_LABEL_RE = re.compile(r"^[A-Za-z0-9_.-]{0,96}$")
_WIREGUARD_PUBLIC_KEY_RE = re.compile(r"^[A-Za-z0-9+/=]{20,100}$")
_WIREGUARD_INTERFACE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,15}$")


def _inventory_id() -> str:
    return f"machine_{secrets.token_hex(12)}"


def _clean_provider(value: str) -> str:
    provider = str(value or "").strip().lower()
    if provider not in {"local", "manual", "hetzner", "linode"}:
        raise ArcLinkInventoryError(f"unsupported inventory provider: {provider or '<empty>'}")
    return provider


def _clean_cloud_provider(value: str, *, error_message: str = "cloud inventory only supports hetzner or linode") -> str:
    provider = _clean_provider(value)
    if provider not in CLOUD_INVENTORY_PROVIDERS:
        raise ArcLinkInventoryError(error_message)
    return provider


def _clean_status(value: str) -> str:
    status = str(value or "").strip().lower()
    if status not in {"pending", "ready", "draining", "degraded", "removed"}:
        raise ArcLinkInventoryError(f"unsupported inventory machine status: {status or '<empty>'}")
    return status


def _clean_host_value(value: Any, *, label: str, required: bool = False) -> str:
    text = str(value or "").strip().lower().strip(".")
    if not text:
        if required:
            raise ArcLinkInventoryError(f"{label} is required")
        return ""
    if any(ch in text for ch in "\x00\r\n") or not _HOST_VALUE_RE.fullmatch(text):
        raise ArcLinkInventoryError(f"invalid {label}")
    return text


def _clean_ssh_user(value: Any, *, default: str = "") -> str:
    text = str(value or default).strip()
    if not text:
        return ""
    if not _SSH_USER_RE.fullmatch(text):
        raise ArcLinkInventoryError("invalid SSH user")
    return text


def _clean_label(value: Any, *, label: str) -> str:
    text = str(value or "").strip().lower()
    if any(ch in text for ch in "\x00\r\n") or not _LABEL_RE.fullmatch(text):
        raise ArcLinkInventoryError(f"invalid {label}")
    return text


def _clean_optional_wireguard_cidr(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "/" not in text:
        try:
            prefix = 128 if ipaddress.ip_address(text).version == 6 else 32
        except ValueError:
            prefix = 32
        text = f"{text}/{prefix}"
    if any(ch in text for ch in "\x00\r\n"):
        raise ArcLinkInventoryError("invalid WireGuard private CIDR")
    try:
        return str(ipaddress.ip_interface(text))
    except ValueError as exc:
        raise ArcLinkInventoryError("invalid WireGuard private CIDR") from exc


def _clean_optional_wireguard_public_key(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\s+", "", text)
    if not _WIREGUARD_PUBLIC_KEY_RE.fullmatch(text):
        raise ArcLinkInventoryError("invalid WireGuard public key")
    return text


def _clean_optional_wireguard_interface(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if any(ch in text for ch in "\x00\r\n") or not _WIREGUARD_INTERFACE_RE.fullmatch(text):
        raise ArcLinkInventoryError("invalid WireGuard interface")
    return text


def _safe_json(value: Mapping[str, Any] | None) -> str:
    return json_dumps_safe(value, label="ArcLink inventory", error_cls=ArcLinkInventoryError)


def register_inventory_machine(
    conn: sqlite3.Connection,
    *,
    provider: str,
    hostname: str,
    ssh_host: str = "",
    ssh_user: str = "",
    region: str = "",
    provider_resource_id: str = "",
    status: str = "pending",
    asu_capacity: float = 0,
    asu_consumed: float = 0,
    hardware_summary: Mapping[str, Any] | None = None,
    connectivity_summary: Mapping[str, Any] | None = None,
    machine_host_link: str = "",
    capacity_slots: int | None = None,
    tags: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    provider_billing_ref: str = "",
) -> dict[str, Any]:
    clean_provider = _clean_provider(provider)
    clean_hostname = _clean_host_value(hostname, label="inventory hostname", required=True)
    clean_status = _clean_status(status)
    clean_region = _clean_label(region, label="inventory region")
    clean_ssh_host = _clean_host_value(ssh_host, label="SSH host")
    clean_ssh_user = _clean_ssh_user(ssh_user)
    clean_resource_id = str(provider_resource_id or "").strip()
    clean_billing_ref = str(provider_billing_ref or "").strip()
    host_link = str(machine_host_link or "").strip()
    now = utc_now_iso()
    clean_capacity_slots = max(1, int(capacity_slots)) if capacity_slots is not None else None
    hardware_json = _safe_json(hardware_summary)
    connectivity_json = _safe_json(connectivity_summary)
    metadata_json = _safe_json(metadata or {})
    metadata_update_json = _safe_json(metadata) if metadata is not None else None
    if tags is not None:
        _safe_json(tags)

    wrote = False
    try:
        if not host_link and clean_capacity_slots is not None:
            wrote = True
            host = register_fleet_host(
                conn,
                hostname=clean_hostname,
                region=clean_region,
                capacity_slots=clean_capacity_slots,
                tags=tags,
                metadata=metadata,
                commit=False,
            )
            host_link = str(host["host_id"])

        existing = conn.execute(
            """
            SELECT * FROM arclink_inventory_machines
            WHERE provider = ?
              AND ((provider_resource_id != '' AND provider_resource_id = ?) OR LOWER(hostname) = ?)
            ORDER BY registered_at ASC
            LIMIT 1
            """,
            (clean_provider, clean_resource_id, clean_hostname),
        ).fetchone()
        if existing is not None:
            next_metadata_json = metadata_update_json if metadata is not None else str(existing["metadata_json"] or "{}")
            conn.execute(
                """
                UPDATE arclink_inventory_machines
                SET provider_resource_id = ?, hostname = ?, ssh_host = ?, ssh_user = ?,
                    region = ?, status = ?, asu_capacity = ?, asu_consumed = ?,
                    hardware_summary_json = ?, connectivity_summary_json = ?,
                    machine_host_link = ?, provider_billing_ref = ?, metadata_json = ?
                WHERE machine_id = ?
                """,
                (
                    clean_resource_id,
                    clean_hostname,
                    clean_ssh_host,
                    clean_ssh_user,
                    clean_region,
                    clean_status,
                    float(asu_capacity),
                    float(asu_consumed),
                    hardware_json,
                    connectivity_json,
                    host_link,
                    clean_billing_ref,
                    next_metadata_json,
                    str(existing["machine_id"]),
                ),
            )
            wrote = True
            machine_id = str(existing["machine_id"])
        else:
            machine_id = _inventory_id()
            conn.execute(
                """
                INSERT INTO arclink_inventory_machines (
                  machine_id, provider, provider_resource_id, hostname, ssh_host, ssh_user,
                  region, status, asu_capacity, asu_consumed, hardware_summary_json,
                  connectivity_summary_json, machine_host_link, provider_billing_ref,
                  metadata_json, registered_at, last_probed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '')
                """,
                (
                    machine_id,
                    clean_provider,
                    clean_resource_id,
                    clean_hostname,
                    clean_ssh_host,
                    clean_ssh_user,
                    clean_region,
                    clean_status,
                    float(asu_capacity),
                    float(asu_consumed),
                    hardware_json,
                    connectivity_json,
                    host_link,
                    clean_billing_ref,
                    metadata_json,
                    now,
                ),
            )
            wrote = True
        append_arclink_audit(
            conn,
            action="inventory_machine_registered",
            target_kind="inventory_machine",
            target_id=machine_id,
            reason="operator registered inventory machine",
            metadata={"provider": clean_provider, "hostname": clean_hostname, "machine_host_link": host_link},
            commit=False,
        )
        conn.commit()
    except Exception:
        if wrote:
            conn.rollback()
        raise
    return dict(conn.execute("SELECT * FROM arclink_inventory_machines WHERE machine_id = ?", (machine_id,)).fetchone())


def _parse_gib_token(token: str) -> int | None:
    text = str(token or "").strip()
    if not text.endswith("G"):
        return None
    try:
        value = float(text[:-1])
    except ValueError:
        return None
    if value < 0:
        return None
    return int(value)


def _mark_probe_degraded(conn: sqlite3.Connection, *, machine_id: str, message: str) -> None:
    conn.execute(
        """
        UPDATE arclink_inventory_machines
        SET status = 'degraded', connectivity_summary_json = ?, last_probed_at = ?
        WHERE machine_id = ?
        """,
        (_safe_json({"ok": False, "error": message}), utc_now_iso(), machine_id),
    )
    conn.commit()


def _matches_inventory_filters(row: Mapping[str, Any], filters: Sequence[str]) -> bool:
    for raw in filters:
        item = str(raw or "").strip()
        if not item:
            continue
        if "=" not in item:
            needle = item.lower()
            haystack = " ".join(
                str(row.get(key) or "")
                for key in ("machine_id", "provider", "hostname", "ssh_host", "region", "status", "machine_host_link")
            ).lower()
            if needle not in haystack:
                return False
            continue
        key, value = item.split("=", 1)
        key = key.strip().lower().replace("-", "_")
        value = value.strip().lower()
        allowed = {
            "machine_id",
            "provider",
            "hostname",
            "ssh_host",
            "ssh_user",
            "region",
            "status",
            "machine_host_link",
            "host_id",
        }
        if key not in allowed:
            raise ArcLinkInventoryError(f"unsupported inventory filter: {key}")
        source_key = "machine_host_link" if key == "host_id" else key
        actual = str(row.get(source_key) or "").lower()
        if actual != value:
            return False
    return True


def list_inventory_machines(
    conn: sqlite3.Connection,
    *,
    include_removed: bool = False,
    filters: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    if include_removed:
        rows = conn.execute("SELECT * FROM arclink_inventory_machines ORDER BY provider, hostname").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM arclink_inventory_machines WHERE status != 'removed' ORDER BY provider, hostname"
        ).fetchall()
    machines = []
    for row in rows:
        item = dict(row)
        try:
            item["asu_consumed"] = current_load(str(item["machine_id"]), conn)
        except ArcLinkASUError:
            item["asu_consumed"] = float(item.get("asu_consumed") or 0)
        machines.append(item)
    if filters:
        machines = [machine for machine in machines if _matches_inventory_filters(machine, filters)]
    return machines


def _matches_fleet_host_filters(row: Mapping[str, Any], filters: Sequence[str] | None) -> bool:
    for raw in filters or []:
        text = str(raw or "").strip().lower()
        if not text:
            continue
        if "=" not in text:
            haystack = " ".join(
                str(row.get(key) or "").lower()
                for key in ("host_id", "hostname", "region", "status", "last_health_state")
            )
            if text not in haystack:
                return False
            continue
        key, value = [part.strip().lower() for part in text.split("=", 1)]
        allowed = {"provider", "hostname", "region", "status", "host_id", "machine_host_link", "health_state"}
        if key not in allowed:
            raise ArcLinkInventoryError(f"unsupported inventory filter: {key}")
        if key == "provider":
            actual = "fleet"
        elif key in {"host_id", "machine_host_link"}:
            actual = str(row.get("host_id") or "").lower()
        elif key == "health_state":
            actual = str(row.get("last_health_state") or "").lower()
        else:
            actual = str(row.get(key) or "").lower()
        if actual != value:
            return False
    return True


def list_fleet_inventory_hosts(
    conn: sqlite3.Connection,
    *,
    include_removed: bool = False,
    filters: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    hosts = list_fleet_hosts(conn)
    if not include_removed:
        hosts = [host for host in hosts if str(host.get("status") or "") != "removed"]
    if filters:
        hosts = [host for host in hosts if _matches_fleet_host_filters(host, filters)]
    return hosts


def get_inventory_machine(conn: sqlite3.Connection, key: str) -> dict[str, Any]:
    clean = str(key or "").strip()
    row = conn.execute(
        """
        SELECT * FROM arclink_inventory_machines
        WHERE machine_id = ? OR LOWER(hostname) = LOWER(?)
        LIMIT 1
        """,
        (clean, clean),
    ).fetchone()
    if row is None:
        raise ArcLinkInventoryError(f"unknown inventory machine: {key}")
    return dict(row)


def parse_probe_output(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in str(stdout or "").splitlines() if line.strip()]
    if not lines:
        raise ArcLinkInventoryError("empty probe output")
    try:
        vcpu = int(lines[0])
    except ValueError as exc:
        raise ArcLinkInventoryError("probe output missing nproc result") from exc
    mem_kib = 0
    disk_gib = 0
    docker_version = ""
    compose_version = ""
    for line in lines[1:]:
        if line.startswith("MemTotal:"):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    mem_kib = int(parts[1])
                except ValueError as exc:
                    raise ArcLinkInventoryError("probe output has invalid MemTotal") from exc
            continue
        lower = line.lower()
        if lower.startswith("docker version"):
            docker_version = line
            continue
        if lower.startswith("docker compose"):
            compose_version = line
            continue
        fields = line.split()
        if not fields or fields[0].lower() == "filesystem":
            continue
        size_gib = None
        if len(fields) >= 4 and str(fields[3]).endswith("%"):
            size_gib = _parse_gib_token(fields[0])
        if size_gib is None and len(fields) >= 2:
            size_gib = _parse_gib_token(fields[1])
        if size_gib is not None:
            disk_gib = max(disk_gib, size_gib)
    if mem_kib <= 0:
        raise ArcLinkInventoryError("probe output missing MemTotal")
    if disk_gib <= 0:
        raise ArcLinkInventoryError("probe output missing disk size")
    return {
        "vcpu_cores": vcpu,
        "ram_gib": round(mem_kib / 1024 / 1024, 2) if mem_kib else 0,
        "disk_gib": disk_gib,
        "docker_version": docker_version,
        "docker_compose_version": compose_version,
    }


def probe_inventory_machine(
    conn: sqlite3.Connection,
    *,
    key: str,
    fleet_key_path: str = "",
    known_hosts_file: str = "",
    runner: RunFn = subprocess.run,
) -> dict[str, Any]:
    machine = get_inventory_machine(conn, key)
    ssh_host = _clean_host_value(machine.get("ssh_host") or machine.get("hostname") or "", label="SSH host", required=True)
    ssh_user = _clean_ssh_user(machine.get("ssh_user") or "arclink", default="arclink")
    if not ssh_host:
        raise ArcLinkInventoryError("inventory machine has no SSH host")
    remote = "nproc; cat /proc/meminfo | head -3; df -BG / /var/lib/docker 2>/dev/null; docker --version; docker compose version"
    command = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
    if known_hosts_file:
        command.extend(["-o", f"UserKnownHostsFile={known_hosts_file}"])
    if fleet_key_path:
        command.extend(["-i", fleet_key_path])
    command.extend([f"{ssh_user}@{ssh_host}", "--", remote])
    try:
        completed = runner(command, text=True, capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        message = redact_then_truncate(str(exc), limit=240)
        _mark_probe_degraded(conn, machine_id=str(machine["machine_id"]), message=message)
        raise ArcLinkInventoryError(message) from exc
    if completed.returncode != 0:
        message = redact_then_truncate(completed.stderr or completed.stdout or "probe failed", limit=240)
        _mark_probe_degraded(conn, machine_id=str(machine["machine_id"]), message=message)
        raise ArcLinkInventoryError(message)
    try:
        hardware = parse_probe_output(completed.stdout)
        asu_capacity = compute_asu(hardware)
        consumed = current_load(str(machine["machine_id"]), conn)
        observed_load = max(0, int(math.ceil(float(consumed))))
    except (ArcLinkInventoryError, ArcLinkASUError) as exc:
        message = redact_then_truncate(str(exc), limit=240)
        _mark_probe_degraded(conn, machine_id=str(machine["machine_id"]), message=message)
        raise ArcLinkInventoryError(message) from exc
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE arclink_inventory_machines
        SET status = 'ready', asu_capacity = ?, asu_consumed = ?,
            hardware_summary_json = ?, connectivity_summary_json = ?,
            last_probed_at = ?
        WHERE machine_id = ?
        """,
        (
            float(asu_capacity),
            float(consumed),
            _safe_json(hardware),
            _safe_json({"ok": True, "ssh_host": ssh_host}),
            now,
            machine["machine_id"],
        ),
    )
    if machine.get("machine_host_link"):
        update_fleet_host(conn, host_id=str(machine["machine_host_link"]), status="active", observed_load=observed_load)
    append_arclink_audit(
        conn,
        action="inventory_machine_probed",
        target_kind="inventory_machine",
        target_id=str(machine["machine_id"]),
        reason="operator probed inventory machine",
        metadata={"asu_capacity": asu_capacity, "hostname": machine.get("hostname", "")},
        commit=False,
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM arclink_inventory_machines WHERE machine_id = ?", (machine["machine_id"],)).fetchone())


def drain_inventory_machine(conn: sqlite3.Connection, key: str) -> dict[str, Any]:
    machine = get_inventory_machine(conn, key)
    if machine.get("machine_host_link"):
        update_fleet_host(conn, host_id=str(machine["machine_host_link"]), drain=True)
    conn.execute("UPDATE arclink_inventory_machines SET status = 'draining' WHERE machine_id = ?", (machine["machine_id"],))
    append_arclink_audit(
        conn,
        action="inventory_machine_drained",
        target_kind="inventory_machine",
        target_id=str(machine["machine_id"]),
        reason="operator drained inventory machine",
        metadata={"hostname": machine.get("hostname", "")},
        commit=False,
    )
    conn.commit()
    return get_inventory_machine(conn, str(machine["machine_id"]))


def remove_inventory_machine(conn: sqlite3.Connection, key: str) -> dict[str, Any]:
    machine = get_inventory_machine(conn, key)
    host_id = str(machine.get("machine_host_link") or "")
    if host_id:
        active = conn.execute(
            "SELECT COUNT(*) AS count FROM arclink_deployment_placements WHERE host_id = ? AND status = 'active'",
            (host_id,),
        ).fetchone()["count"]
        if int(active or 0) > 0:
            raise ArcLinkInventoryError("inventory machine has active placements; migrate or drain first")
        update_fleet_host(conn, host_id=host_id, status="offline", drain=True)
    conn.execute("UPDATE arclink_inventory_machines SET status = 'removed' WHERE machine_id = ?", (machine["machine_id"],))
    append_arclink_audit(
        conn,
        action="inventory_machine_removed",
        target_kind="inventory_machine",
        target_id=str(machine["machine_id"]),
        reason="operator removed inventory machine",
        metadata={"hostname": machine.get("hostname", "")},
        commit=False,
    )
    conn.commit()
    return get_inventory_machine(conn, str(machine["machine_id"]))


def _operation_result(row: Mapping[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(str(row.get("result_json") or "{}"))
    except (TypeError, json.JSONDecodeError):
        value = {}
    return value if isinstance(value, dict) else {}


def _cloud_operation_kind(provider: str, action: str) -> str:
    clean_provider = _clean_cloud_provider(provider)
    clean_action = str(action or "").strip().lower()
    if clean_action not in {"create", "remove"}:
        raise ArcLinkInventoryError(f"unsupported cloud inventory operation: {clean_action or '<empty>'}")
    return f"inventory_{clean_provider}_{clean_action}"


def _idempotent_replay_result(row: Mapping[str, Any]) -> dict[str, Any]:
    result = _operation_result(row)
    result["replay"] = True
    if str(row.get("status") or "") == "failed":
        error = str(row.get("error") or result.get("error") or "previous cloud inventory operation failed").strip()
        message = redact_then_truncate(error, limit=300)
        raise ArcLinkInventoryError(f"previous cloud inventory operation failed: {message}")
    return result


def _redacted_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    text = json_dumps_safe(dict(value), label="ArcLink inventory", error_cls=ArcLinkInventoryError)
    redacted = redact_then_truncate(text, limit=4000)
    try:
        parsed = json.loads(redacted)
    except json.JSONDecodeError:
        return {"summary": redacted}
    return parsed if isinstance(parsed, dict) else {"summary": redacted}


def _existing_cloud_machine(conn: sqlite3.Connection, *, provider: str, hostname: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT * FROM arclink_inventory_machines
        WHERE provider = ? AND LOWER(hostname) = LOWER(?) AND status != 'removed'
        ORDER BY registered_at ASC
        LIMIT 1
        """,
        (provider, hostname),
    ).fetchone()
    return dict(row) if row is not None else None


def _cloud_operation_intent(
    *,
    provider: str,
    hostname: str,
    server_type: str,
    image: str,
    region: str,
    ssh_user: str,
    capacity_slots: int,
    tags: Mapping[str, Any] | None,
    provider_billing_ref: str,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "hostname": hostname,
        "server_type": server_type,
        "image": image,
        "region": region,
        "ssh_user": ssh_user,
        "capacity_slots": int(capacity_slots),
        "tags": dict(tags or {}),
        "provider_billing_ref": provider_billing_ref,
        "bootstrap": {
            "script": FLEET_JOIN_SCRIPT,
            "prereq_library": FLEET_PREREQ_LIBRARY,
        },
    }


def _bootstrap_refs(**extra: Any) -> dict[str, Any]:
    return {"join_script": FLEET_JOIN_SCRIPT, "prereq_library": FLEET_PREREQ_LIBRARY, **extra}


def _bootstrap_context(
    *,
    provider: str,
    hostname: str,
    ssh_host: str,
    ssh_user: str,
    region: str,
    provider_resource_id: str,
) -> dict[str, Any]:
    return _bootstrap_refs(
        provider=provider,
        hostname=hostname,
        ssh_host=ssh_host,
        ssh_user=ssh_user,
        region=region,
        provider_resource_id=provider_resource_id,
    )


def _row_count_map(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    return {str(row[key] or "unknown"): int(row["count"] or 0) for row in rows}


def _fleet_host_state_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "status": str(row["status"] or "unknown"),
            "drain": bool(row["drain"]),
            "count": int(row["count"] or 0),
            "capacity_slots": int(row["capacity_slots"] or 0),
            "observed_load": int(row["observed_load"] or 0),
        }
        for row in rows
    ]


def _call_provider_create(
    provider: str,
    client: Any,
    *,
    hostname: str,
    server_type: str,
    image: str,
    region: str,
    ssh_keys: Sequence[str],
) -> dict[str, Any]:
    if provider == "hetzner":
        return dict(
            client.provision_server(
                name=hostname,
                server_type=server_type,
                image=image,
                location=region,
                ssh_keys=list(ssh_keys),
            )
        )
    if provider == "linode":
        return dict(
            client.provision_server(
                label=hostname,
                linode_type=server_type,
                image=image,
                region=region,
                authorized_keys=list(ssh_keys),
            )
        )
    raise ArcLinkInventoryError(f"unsupported cloud inventory provider: {provider}")


def create_cloud_inventory_machine(
    conn: sqlite3.Connection,
    *,
    provider: str,
    client: Any,
    hostname: str,
    server_type: str,
    image: str,
    region: str,
    ssh_keys: Sequence[str] | None = None,
    ssh_user: str = "arclink",
    capacity_slots: int = 4,
    tags: Mapping[str, Any] | None = None,
    idempotency_key: str = "",
    provider_billing_ref: str = "",
    bootstrap_runner: Callable[[Mapping[str, Any]], Mapping[str, Any] | None] | None = None,
) -> dict[str, Any]:
    clean_provider = _clean_cloud_provider(
        provider,
        error_message="cloud inventory create only supports hetzner or linode",
    )
    clean_hostname = str(hostname or "").strip().lower()
    if not clean_hostname:
        raise ArcLinkInventoryError("cloud inventory create requires a hostname")
    clean_region = str(region or "").strip().lower()
    if not clean_region:
        raise ArcLinkInventoryError("cloud inventory create requires a region")
    clean_server_type = str(server_type or "").strip()
    clean_image = str(image or "").strip()
    if not clean_server_type or not clean_image:
        raise ArcLinkInventoryError("cloud inventory create requires server type and image")
    slots = max(1, int(capacity_slots))
    clean_key = str(idempotency_key or f"{clean_provider}:create:{clean_hostname}").strip()
    operation_kind = _cloud_operation_kind(clean_provider, "create")
    clean_billing_ref = str(provider_billing_ref or "").strip()
    clean_tags = dict(tags or {})

    intent = _cloud_operation_intent(
        provider=clean_provider,
        hostname=clean_hostname,
        server_type=clean_server_type,
        image=clean_image,
        region=clean_region,
        ssh_user=str(ssh_user or "arclink").strip() or "arclink",
        capacity_slots=slots,
        tags=clean_tags,
        provider_billing_ref=clean_billing_ref,
    )
    replay = replay_arclink_operation_idempotency(
        conn,
        operation_kind=operation_kind,
        idempotency_key=clean_key,
        intent=intent,
    )
    if replay is not None:
        return _idempotent_replay_result(replay)

    existing = _existing_cloud_machine(conn, provider=clean_provider, hostname=clean_hostname)
    if existing is not None:
        return {"status": "existing", "replay": True, "machine": existing}

    reserved = reserve_arclink_operation_idempotency(
        conn,
        operation_kind=operation_kind,
        idempotency_key=clean_key,
        intent=intent,
        status="running",
    )
    if reserved.get("replay"):
        return _idempotent_replay_result(reserved)

    resource_id = ""
    machine_registered = False
    try:
        server = _call_provider_create(
            clean_provider,
            client,
            hostname=clean_hostname,
            server_type=clean_server_type,
            image=clean_image,
            region=clean_region,
            ssh_keys=list(ssh_keys or []),
        )
        resource_id = str(server.get("provider_resource_id") or "")
        metadata = {
            "provider_bootstrap": _bootstrap_refs(status="operator_gated" if bootstrap_runner is None else "pending"),
            "provider_intent": intent,
        }
        status = "pending"
        if bootstrap_runner is not None:
            try:
                bootstrap_result = bootstrap_runner(
                    _bootstrap_context(
                        provider=clean_provider,
                        hostname=clean_hostname,
                        ssh_host=str(server.get("ssh_host") or ""),
                        ssh_user=str(intent["ssh_user"]),
                        region=clean_region,
                        provider_resource_id=resource_id,
                    )
                ) or {}
                metadata["provider_bootstrap"] = _bootstrap_refs(
                    status="succeeded",
                    result=_redacted_mapping(dict(bootstrap_result)),
                )
            except Exception:
                metadata["provider_bootstrap"] = _bootstrap_refs(
                    status="failed",
                    error="bootstrap failed; sensitive detail redacted",
                )
                status = "degraded"
        machine = register_inventory_machine(
            conn,
            provider=clean_provider,
            hostname=clean_hostname,
            ssh_host=str(server.get("ssh_host") or ""),
            ssh_user=str(intent["ssh_user"]),
            region=clean_region,
            provider_resource_id=resource_id,
            status=status,
            hardware_summary=server.get("hardware_summary") if isinstance(server.get("hardware_summary"), Mapping) else {},
            connectivity_summary={"ok": False, "status": "awaiting_fleet_probe"},
            capacity_slots=slots,
            tags=clean_tags,
            metadata=metadata,
            provider_billing_ref=clean_billing_ref,
        )
        machine_registered = True
        result = {"status": status, "replay": False, "machine": machine}
        complete_arclink_operation_idempotency(
            conn,
            operation_kind=operation_kind,
            idempotency_key=clean_key,
            intent=intent,
            provider_refs={"provider_resource_id": resource_id},
            result=result,
        )
        return result
    except Exception as exc:
        message = redact_then_truncate(str(exc), limit=300)
        provider_refs = {"provider_resource_id": resource_id} if resource_id else {}
        failure_result: dict[str, Any] = {"status": "failed", "replay": False, "error": message}
        if resource_id and not machine_registered:
            cleanup: dict[str, Any] = {"attempted": True, "destroy": True, "removed": False}
            try:
                client.remove_server(resource_id, destroy=True)
                cleanup["removed"] = True
            except Exception as cleanup_exc:
                cleanup["error"] = redact_then_truncate(str(cleanup_exc), limit=300)
            failure_result["cleanup"] = cleanup
        fail_arclink_operation_idempotency(
            conn,
            operation_kind=operation_kind,
            idempotency_key=clean_key,
            intent=intent,
            error=message,
            provider_refs=provider_refs,
            result=failure_result,
        )
        raise


def remove_cloud_inventory_machine(
    conn: sqlite3.Connection,
    *,
    key: str,
    client: Any,
    destroy: bool = False,
    force: bool = False,
    idempotency_key: str = "",
) -> dict[str, Any]:
    machine = get_inventory_machine(conn, key)
    provider = _clean_cloud_provider(
        str(machine.get("provider") or ""),
        error_message="cloud inventory remove only supports hetzner or linode machines",
    )
    if not destroy:
        raise ArcLinkInventoryError("cloud inventory destroy requires --destroy")
    if str(machine.get("status") or "") not in {"draining", "removed"} and not force:
        raise ArcLinkInventoryError("drain the cloud inventory machine before removal, or pass --force")
    resource_id = str(machine.get("provider_resource_id") or "")
    if not resource_id:
        raise ArcLinkInventoryError("cloud inventory machine has no provider resource id")

    clean_key = str(idempotency_key or f"{provider}:remove:{resource_id}").strip()
    operation_kind = _cloud_operation_kind(provider, "remove")
    intent = {
        "provider": provider,
        "machine_id": str(machine["machine_id"]),
        "provider_resource_id": resource_id,
        "destroy": bool(destroy),
        "force": bool(force),
    }
    reserved = reserve_arclink_operation_idempotency(
        conn,
        operation_kind=operation_kind,
        idempotency_key=clean_key,
        intent=intent,
        status="running",
    )
    if reserved.get("replay"):
        return _idempotent_replay_result(reserved)
    try:
        client.remove_server(resource_id, destroy=True)
        removed = remove_inventory_machine(conn, str(machine["machine_id"]))
        result = {"status": "removed", "replay": False, "machine": removed}
        complete_arclink_operation_idempotency(
            conn,
            operation_kind=operation_kind,
            idempotency_key=clean_key,
            intent=intent,
            provider_refs={"provider_resource_id": resource_id},
            result=result,
        )
        return result
    except Exception as exc:
        message = redact_then_truncate(str(exc), limit=300)
        fail_arclink_operation_idempotency(
            conn,
            operation_kind=operation_kind,
            idempotency_key=clean_key,
            intent=intent,
            error=message,
            provider_refs={"provider_resource_id": resource_id},
            result={"status": "failed", "replay": False, "error": message},
        )
        raise


def fleet_inventory_health(conn: sqlite3.Connection, *, notify: bool = False) -> dict[str, Any]:
    from arclink_fleet_enrollment import expire_pending_fleet_enrollments, verify_fleet_audit_chain

    expired = expire_pending_fleet_enrollments(conn, notify=notify)
    audit_chain = verify_fleet_audit_chain(conn, notify=notify)
    machine_rows = conn.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM arclink_inventory_machines
        GROUP BY status
        """
    ).fetchall()
    host_rows = conn.execute(
        """
        SELECT status, drain, COUNT(*) AS count,
               COALESCE(SUM(capacity_slots), 0) AS capacity_slots,
               COALESCE(SUM(observed_load), 0) AS observed_load
        FROM arclink_fleet_hosts
        GROUP BY status, drain
        """
    ).fetchall()
    region_rows = conn.execute(
        """
        SELECT COALESCE(NULLIF(region, ''), 'unspecified') AS region, COUNT(*) AS count
        FROM arclink_fleet_hosts
        GROUP BY COALESCE(NULLIF(region, ''), 'unspecified')
        ORDER BY region
        """
    ).fetchall()
    health_rows = conn.execute(
        """
        SELECT COALESCE(NULLIF(last_health_state, ''), status) AS health_state, COUNT(*) AS count
        FROM arclink_fleet_hosts
        GROUP BY COALESCE(NULLIF(last_health_state, ''), status)
        """
    ).fetchall()
    probe_row = conn.execute(
        """
        SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE WHEN ok = 1 THEN 1 ELSE 0 END), 0) AS ok_count,
               MAX(probed_at) AS last_probed_at
        FROM arclink_fleet_host_probes
        """
    ).fetchone()
    active_capacity = conn.execute(
        """
        SELECT COALESCE(SUM(capacity_slots), 0) AS capacity_slots,
               COALESCE(SUM(observed_load), 0) AS observed_load
        FROM arclink_fleet_hosts
        WHERE status = 'active' AND drain = 0
        """
    ).fetchone()
    capacity_slots = int(active_capacity["capacity_slots"] or 0)
    observed_load = int(active_capacity["observed_load"] or 0)
    total_probes = int(probe_row["total"] or 0)
    ok_probes = int(probe_row["ok_count"] or 0)
    return {
        "ok": bool(audit_chain.get("ok")),
        "strategy": os.environ.get("ARCLINK_FLEET_PLACEMENT_STRATEGY", "headroom"),
        "inventory": _row_count_map(machine_rows, "status"),
        "hosts": {
            "by_state": _fleet_host_state_rows(host_rows),
            "regions": _row_count_map(region_rows, "region"),
            "health_states": _row_count_map(health_rows, "health_state"),
            "capacity_slots": capacity_slots,
            "observed_load": observed_load,
            "available_slots": max(0, capacity_slots - observed_load),
        },
        "probes": {
            "total": total_probes,
            "ok": ok_probes,
            "success_ratio": (ok_probes / total_probes) if total_probes else None,
            "last_probed_at": str(probe_row["last_probed_at"] or ""),
        },
        "enrollments": {"expired_now": expired},
        "audit_chain": audit_chain,
    }


def _print_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    print("machine_id provider hostname status asu_capacity asu_consumed last_probed_at")
    for row in rows:
        print(
            " ".join(
                [
                    str(row["machine_id"]),
                    str(row["provider"]),
                    str(row["hostname"]),
                    str(row["status"]),
                    f"{float(row.get('asu_capacity') or 0):g}",
                    f"{float(row.get('asu_consumed') or 0):g}",
                    str(row.get("last_probed_at") or "-"),
                ]
            )
        )


def _print_fleet_hosts_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    print("host_id provider hostname status health capacity effective_capacity observed_load headroom reserve region")
    for row in rows:
        print(
            " ".join(
                [
                    str(row.get("host_id") or ""),
                    "fleet",
                    str(row.get("hostname") or ""),
                    str(row.get("status") or ""),
                    str(row.get("last_health_state") or "-"),
                    str(int(row.get("capacity_slots") or 0)),
                    str(int(row.get("effective_capacity_slots") or row.get("capacity_slots") or 0)),
                    str(int(row.get("observed_load") or 0)),
                    str(int(row.get("headroom") or 0)),
                    "yes" if bool(row.get("control_plane_reserve")) else "no",
                    str(row.get("region") or "-"),
                ]
            )
        )


def _load_conn() -> sqlite3.Connection:
    cfg = Config.from_env()
    conn = connect_db(cfg)
    ensure_schema(conn, cfg)
    return conn


def _cloud_provider_client(provider: str) -> Any:
    if provider == "hetzner":
        token_name = "HETZNER_API_TOKEN"
        from arclink_inventory_hetzner import HetznerInventoryProvider as Provider
    else:
        token_name = "LINODE_API_TOKEN"
        from arclink_inventory_linode import LinodeInventoryProvider as Provider
    return Provider(token=os.environ.get(token_name, ""))


def _cmd_add_cloud(args: Any) -> int:
    provider = str(args.provider)
    try:
        client = _cloud_provider_client(provider)
    except Exception as exc:
        print(redact_then_truncate(str(exc), limit=240), file=sys.stderr)
        return 1
    if not args.hostname:
        servers = client.list_servers()
        print(json.dumps({"provider": provider, "servers": servers}, sort_keys=True))
        return 0
    try:
        conn = _load_conn()
        tags = json_loads_safe(args.tags_json)
        result = create_cloud_inventory_machine(
            conn,
            provider=provider,
            client=client,
            hostname=args.hostname,
            server_type=args.server_type,
            image=args.image,
            region=args.region,
            ssh_keys=args.ssh_key or [],
            ssh_user=args.ssh_user,
            capacity_slots=args.capacity_slots,
            tags=tags,
            idempotency_key=args.idempotency_key,
            provider_billing_ref=args.billing_ref,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(redact_then_truncate(str(exc), limit=300), file=sys.stderr)
        return 1


def _add_cloud_provider_parser(
    add_sub: argparse._SubParsersAction[argparse.ArgumentParser],
    provider: str,
    *,
    server_type: str,
    image: str,
    region: str,
) -> None:
    parser = add_sub.add_parser(provider)
    parser.add_argument("--hostname", "--name", dest="hostname", default="")
    parser.add_argument("--server-type", default=server_type)
    parser.add_argument("--image", default=image)
    if provider == "hetzner":
        parser.add_argument("--region", "--location", dest="region", default=region)
    else:
        parser.add_argument("--region", default=region)
    parser.add_argument("--ssh-key", action="append", default=[])
    parser.add_argument("--ssh-user", default="arclink")
    parser.add_argument("--capacity-slots", type=int, default=4)
    parser.add_argument("--tags-json", default="{}")
    parser.add_argument("--billing-ref", default="")
    parser.add_argument("--idempotency-key", default="")
    parser.add_argument("--json", action="store_true")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arclink-inventory")
    sub = parser.add_subparsers(dest="command", required=True)
    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--all", action="store_true")
    list_cmd.add_argument("--filter", action="append", default=[])
    list_cmd.add_argument("--json", action="store_true")
    probe = sub.add_parser("probe")
    probe.add_argument("machine")
    probe.add_argument("--json", action="store_true")
    probe_all = sub.add_parser("probe-all")
    probe_all.add_argument("--json", action="store_true")
    probe_all.add_argument("--notify", action="store_true")
    add = sub.add_parser("add")
    add_sub = add.add_subparsers(dest="provider", required=True)
    manual = add_sub.add_parser("manual")
    manual.add_argument("--hostname", required=True)
    manual.add_argument("--ssh-host", default="")
    manual.add_argument("--private-dns-name", "--wireguard-dns-name", "--private-mesh-dns-name", dest="private_dns_name", default="")
    manual.add_argument("--tailscale-dns-name", "--tailnet-dns-name", "--magicdns-name", dest="tailscale_dns_name", default="")
    manual.add_argument("--wireguard-private-ip", "--wireguard-worker-ip", dest="wireguard_private_ip", default="")
    manual.add_argument("--wireguard-public-key", dest="wireguard_public_key", default="")
    manual.add_argument("--wireguard-interface", dest="wireguard_interface", default="")
    manual.add_argument("--ssh-user", default="arclink")
    manual.add_argument("--region", default="")
    manual.add_argument("--capacity-slots", type=int, default=4)
    manual.add_argument("--tags-json", default="{}")
    manual.add_argument("--json", action="store_true")
    _add_cloud_provider_parser(
        add_sub,
        "hetzner",
        server_type="cx22",
        image="ubuntu-24.04",
        region="fsn1",
    )
    _add_cloud_provider_parser(
        add_sub,
        "linode",
        server_type="g6-standard-2",
        image="linode/ubuntu24.04",
        region="us-east",
    )
    drain = sub.add_parser("drain")
    drain.add_argument("machine")
    drain.add_argument("--json", action="store_true")
    remove = sub.add_parser("remove")
    remove.add_argument("machine")
    remove.add_argument("--destroy", action="store_true")
    remove.add_argument("--force", action="store_true")
    remove.add_argument("--idempotency-key", default="")
    remove.add_argument("--json", action="store_true")
    reattest = sub.add_parser("re-attest")
    reattest.add_argument("machine")
    reattest.add_argument("--machine-fingerprint", required=True)
    reattest.add_argument("--actor", default=os.environ.get("USER", "operator"))
    reattest.add_argument("--reason", default="")
    reattest.add_argument("--json", action="store_true")
    health = sub.add_parser("health")
    health.add_argument("--notify", action="store_true")
    health.add_argument("--json", action="store_true")
    strategy = sub.add_parser("set-strategy")
    strategy.add_argument("strategy", choices=("headroom", "standard_unit"))
    strategy.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "add" and args.provider in {"hetzner", "linode"}:
            return _cmd_add_cloud(args)
        conn = _load_conn()
        if args.command == "list":
            rows = list_inventory_machines(conn, include_removed=args.all, filters=args.filter)
            hosts = list_fleet_inventory_hosts(conn, include_removed=args.all, filters=args.filter)
            if args.json:
                print(json.dumps({"machines": rows, "fleet_hosts": hosts}, sort_keys=True))
            else:
                if not rows and not hosts:
                    print("No inventory machines or fleet hosts registered.")
                else:
                    _print_table(rows)
                    _print_fleet_hosts_table(hosts)
        elif args.command == "probe":
            row = probe_inventory_machine(
                conn,
                key=args.machine,
                fleet_key_path=os.environ.get("ARCLINK_FLEET_SSH_KEY_PATH", ""),
                known_hosts_file=os.environ.get("ARCLINK_FLEET_SSH_KNOWN_HOSTS_FILE", ""),
            )
            print(json.dumps(dict(row), sort_keys=True))
        elif args.command == "probe-all":
            from arclink_fleet_inventory_worker import process_due_hosts

            result = process_due_hosts(conn, force=True, notify=args.notify)
            if args.json:
                print(json.dumps(result, sort_keys=True))
            else:
                print(f"fleet_probe_all probes={result['probe_count']} pruned={result['pruned']}")
        elif args.command == "add" and args.provider == "manual":
            tags = json_loads_safe(args.tags_json)
            ssh_host = _clean_host_value(args.ssh_host or args.hostname, label="SSH host", required=True)
            ssh_user = _clean_ssh_user(args.ssh_user, default="arclink")
            private_dns_name = _clean_host_value(args.private_dns_name, label="private DNS name")
            tailscale_dns_name = _clean_host_value(args.tailscale_dns_name, label="Tailscale DNS name")
            wireguard_private_ip = _clean_optional_wireguard_cidr(args.wireguard_private_ip)
            wireguard_public_key = _clean_optional_wireguard_public_key(args.wireguard_public_key)
            wireguard_interface = _clean_optional_wireguard_interface(args.wireguard_interface)
            if not private_dns_name and wireguard_private_ip:
                private_dns_name = wireguard_private_ip.split("/", 1)[0].lower().strip(".")
            if not tailscale_dns_name and str(ssh_host).strip().lower().endswith(".ts.net"):
                tailscale_dns_name = str(ssh_host).strip().lower().strip(".")
            metadata = {"ssh_host": ssh_host, "ssh_user": ssh_user}
            if private_dns_name:
                metadata["private_dns_name"] = private_dns_name
                metadata["control_network_mode"] = "remote"
            if tailscale_dns_name:
                metadata["tailscale_dns_name"] = tailscale_dns_name
                metadata["control_network_mode"] = "remote"
            if wireguard_private_ip or wireguard_public_key:
                metadata["wireguard"] = {
                    "interface": wireguard_interface,
                    "private_ip": wireguard_private_ip.split("/", 1)[0],
                    "private_cidr": wireguard_private_ip,
                    "public_key": wireguard_public_key,
                }
                metadata["control_network_mode"] = "remote"
            row = register_inventory_machine(
                conn,
                provider="manual",
                hostname=args.hostname,
                ssh_host=ssh_host,
                ssh_user=ssh_user,
                region=args.region,
                status="pending",
                capacity_slots=args.capacity_slots,
                tags=tags,
                metadata=metadata,
            )
            print(json.dumps(dict(row), sort_keys=True))
        elif args.command == "drain":
            print(json.dumps(drain_inventory_machine(conn, args.machine), sort_keys=True))
        elif args.command == "remove":
            machine = get_inventory_machine(conn, args.machine)
            if args.destroy and str(machine.get("provider") or "") in {"hetzner", "linode"}:
                result = remove_cloud_inventory_machine(
                    conn,
                    key=args.machine,
                    client=_cloud_provider_client(str(machine["provider"])),
                    destroy=args.destroy,
                    force=args.force,
                    idempotency_key=args.idempotency_key,
                )
                print(json.dumps(result, sort_keys=True))
            else:
                print(json.dumps(remove_inventory_machine(conn, args.machine), sort_keys=True))
        elif args.command == "re-attest":
            from arclink_fleet_enrollment import reattest_inventory_machine

            row = reattest_inventory_machine(
                conn,
                key=args.machine,
                machine_fingerprint=args.machine_fingerprint,
                actor=args.actor,
                reason=args.reason,
            )
            print(json.dumps({"machine": row}, sort_keys=True))
        elif args.command == "health":
            result = fleet_inventory_health(conn, notify=args.notify)
            if args.json:
                print(json.dumps(result, sort_keys=True))
            else:
                print(
                    "fleet_health "
                    f"ok={str(bool(result['ok'])).lower()} "
                    f"available_slots={result['hosts']['available_slots']} "
                    f"audit_chain_ok={str(bool(result['audit_chain']['ok'])).lower()}"
                )
        elif args.command == "set-strategy":
            if args.json:
                print(json.dumps({"strategy": args.strategy}, sort_keys=True))
            else:
                print(f"ARCLINK_FLEET_PLACEMENT_STRATEGY={args.strategy}")
        return 0
    except Exception as exc:
        print(redact_then_truncate(str(exc), limit=300), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
