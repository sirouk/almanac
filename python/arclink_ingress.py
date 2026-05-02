#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Mapping

from arclink_control import append_arclink_event, utc_now_iso
from arclink_adapters import DnsRecord, arclink_hostnames, render_traefik_http_labels


ARCLINK_HOST_ROLES = ("dashboard", "files", "code", "hermes")
ARCLINK_DEFAULT_SERVICE_PORTS = {
    "dashboard": 3000,
    "files": 8080,
    "code": 8080,
    "hermes": 3210,
}


@dataclass(frozen=True)
class DnsDrift:
    kind: str
    record_type: str
    hostname: str


def desired_arclink_dns_records(*, prefix: str, base_domain: str, target: str) -> dict[str, DnsRecord]:
    clean_target = str(target or "").strip().lower().strip(".")
    if not clean_target:
        raise ValueError("ArcLink DNS target is required")
    return {
        role: DnsRecord(hostname=hostname, record_type="CNAME", target=clean_target, proxied=True)
        for role, hostname in arclink_hostnames(prefix, base_domain).items()
    }


def persist_arclink_dns_records(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    records: Mapping[str, DnsRecord],
) -> None:
    now = utc_now_iso()
    for role, record in records.items():
        record_id = f"dns_{deployment_id}_{role}"
        conn.execute(
            """
            INSERT INTO arclink_dns_records (
              record_id, deployment_id, hostname, record_type, target, status,
              last_checked_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'desired', ?, ?, ?)
            ON CONFLICT(record_id) DO UPDATE SET
              hostname = excluded.hostname,
              record_type = excluded.record_type,
              target = excluded.target,
              status = excluded.status,
              last_checked_at = excluded.last_checked_at,
              updated_at = excluded.updated_at
            """,
            (
                record_id,
                deployment_id,
                record.hostname,
                record.record_type.upper(),
                record.target,
                now,
                now,
                now,
            ),
        )
    conn.commit()


def _parse_cloudflare_drift(raw: str) -> DnsDrift:
    parts = str(raw or "").split()
    if len(parts) != 3 or parts[0] not in {"missing", "changed"}:
        raise ValueError(f"unsupported Cloudflare drift format: {raw}")
    return DnsDrift(kind=parts[0], record_type=parts[1].upper(), hostname=parts[2].lower())


def reconcile_arclink_dns(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    prefix: str,
    base_domain: str,
    target: str,
    cloudflare: Any,
) -> list[DnsDrift]:
    records = desired_arclink_dns_records(prefix=prefix, base_domain=base_domain, target=target)
    persist_arclink_dns_records(conn, deployment_id=deployment_id, records=records)
    drift = [_parse_cloudflare_drift(item) for item in cloudflare.drift(list(records.values()))]
    for item in drift:
        append_arclink_event(
            conn,
            subject_kind="deployment",
            subject_id=deployment_id,
            event_type="dns_drift",
            metadata={"kind": item.kind, "record_type": item.record_type, "hostname": item.hostname},
        )
    return drift


def _mark_dns_status(
    conn: sqlite3.Connection,
    deployment_id: str,
    status: str,
    event_type: str,
    metadata: dict[str, Any],
) -> None:
    now = utc_now_iso()
    conn.execute(
        "UPDATE arclink_dns_records SET status = ?, updated_at = ? WHERE deployment_id = ?",
        (status, now, deployment_id),
    )
    conn.commit()
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=deployment_id,
        event_type=event_type,
        metadata=metadata,
    )


def teardown_arclink_dns(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    prefix: str,
    base_domain: str,
    cloudflare: Any,
) -> list[str]:
    """Remove all DNS records for a deployment and mark them torn down."""
    hostnames = arclink_hostnames(prefix, base_domain)
    removed = cloudflare.teardown_records(list(hostnames.values()))
    _mark_dns_status(conn, deployment_id, "torn_down", "dns_teardown",
                     {"removed": removed, "prefix": prefix})
    return removed


def provision_arclink_dns(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    prefix: str,
    base_domain: str,
    target: str,
    cloudflare: Any,
    max_retries: int = 2,
) -> dict[str, DnsRecord]:
    """Create DNS records with retry safety. Idempotent via upsert."""
    records = desired_arclink_dns_records(prefix=prefix, base_domain=base_domain, target=target)
    persist_arclink_dns_records(conn, deployment_id=deployment_id, records=records)
    last_error: Exception | None = None
    for attempt in range(1 + max_retries):
        try:
            for record in records.values():
                cloudflare.upsert_record(record)
            _mark_dns_status(conn, deployment_id, "provisioned", "dns_provisioned",
                             {"prefix": prefix, "attempt": attempt + 1})
            return records
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return records


def render_traefik_dynamic_labels(
    *,
    prefix: str,
    base_domain: str,
    service_ports: Mapping[str, int] | None = None,
) -> dict[str, dict[str, str]]:
    ports = dict(ARCLINK_DEFAULT_SERVICE_PORTS)
    ports.update(dict(service_ports or {}))
    hostnames = arclink_hostnames(prefix, base_domain)
    labels: dict[str, dict[str, str]] = {}
    for role in ARCLINK_HOST_ROLES:
        labels[role] = render_traefik_http_labels(
            service_name=f"{prefix}-{role}",
            hostname=hostnames[role],
            port=int(ports[role]),
        )
    return labels
