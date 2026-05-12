#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Mapping

from arclink_control import append_arclink_event, utc_now_iso
from arclink_adapters import (
    DnsRecord,
    arclink_hostnames,
    arclink_role_path_prefixes,
    arclink_tailscale_hostnames,
    render_traefik_http_labels,
    render_traefik_http_path_labels,
)


ARCLINK_HOST_ROLES = ("dashboard", "hermes")
ARCLINK_DEFAULT_SERVICE_PORTS = {
    "dashboard": 3000,
    "files": 80,
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
        if role in ARCLINK_HOST_ROLES
    }


def desired_arclink_ingress_records(
    *,
    prefix: str,
    base_domain: str,
    target: str,
    ingress_mode: str = "domain",
    tailscale_dns_name: str = "",
    tailscale_host_strategy: str = "path",
) -> dict[str, DnsRecord]:
    mode = str(ingress_mode or "domain").strip().lower()
    if mode == "domain":
        return desired_arclink_dns_records(prefix=prefix, base_domain=base_domain, target=target)
    if mode == "tailscale":
        return {}
    raise ValueError("ArcLink ingress mode must be domain or tailscale")


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
              status = CASE
                WHEN arclink_dns_records.hostname = excluded.hostname
                 AND UPPER(arclink_dns_records.record_type) = UPPER(excluded.record_type)
                 AND arclink_dns_records.target = excluded.target
                 AND arclink_dns_records.status = 'provisioned'
                THEN arclink_dns_records.status
                ELSE excluded.status
              END,
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


def mark_arclink_dns_torn_down(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    removed: list[str] | tuple[str, ...],
    metadata: Mapping[str, Any] | None = None,
) -> None:
    extra = dict(metadata or {})
    extra["removed"] = list(removed)
    _mark_dns_status(conn, deployment_id, "torn_down", "dns_teardown", extra)


def arclink_dns_records_for_teardown(conn: sqlite3.Connection, *, deployment_id: str) -> tuple[dict[str, Any], ...]:
    rows = conn.execute(
        """
        SELECT hostname, record_type, provider_record_id
        FROM arclink_dns_records
        WHERE deployment_id = ?
          AND status != 'torn_down'
        ORDER BY hostname, record_type
        """,
        (deployment_id,),
    ).fetchall()
    return tuple(
        {
            "hostname": str(row["hostname"] or ""),
            "record_type": str(row["record_type"] or ""),
            "provider_record_id": str(row["provider_record_id"] or ""),
        }
        for row in rows
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
    mark_arclink_dns_torn_down(conn, deployment_id=deployment_id, removed=removed, metadata={"prefix": prefix})
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
    ingress_mode: str = "domain",
    tailscale_dns_name: str = "",
    tailscale_host_strategy: str = "path",
    service_ports: Mapping[str, int] | None = None,
    docker_network: str = "",
) -> dict[str, dict[str, str]]:
    ports = dict(ARCLINK_DEFAULT_SERVICE_PORTS)
    ports.update(dict(service_ports or {}))
    mode = str(ingress_mode or "domain").strip().lower()
    strategy = str(tailscale_host_strategy or "path").strip().lower()
    if mode == "tailscale":
        hostnames = arclink_tailscale_hostnames(prefix, tailscale_dns_name or base_domain, strategy=strategy)
    elif mode == "domain":
        hostnames = arclink_hostnames(prefix, base_domain)
    else:
        raise ValueError("ArcLink ingress mode must be domain or tailscale")
    path_prefixes = arclink_role_path_prefixes(prefix) if mode == "tailscale" and strategy == "path" else {}
    labels: dict[str, dict[str, str]] = {}
    if path_prefixes:
        labels["dashboard"] = {}
        root_labels = render_traefik_http_path_labels(
            service_name=f"{prefix}-hermes-root",
            hostname=hostnames["hermes"],
            path_prefix=path_prefixes["dashboard"],
            port=int(ports["hermes"]),
            docker_network=docker_network,
            priority=10,
        )
        alias_labels = render_traefik_http_path_labels(
            service_name=f"{prefix}-hermes",
            hostname=hostnames["hermes"],
            path_prefix=path_prefixes["hermes"],
            port=int(ports["hermes"]),
            docker_network=docker_network,
            priority=100,
        )
        labels["hermes"] = {**root_labels, **alias_labels}
        return labels
    for role in ARCLINK_HOST_ROLES:
        labels[role] = render_traefik_http_labels(
            service_name=f"{prefix}-{role}",
            hostname=hostnames[role],
            port=int(ports[role]),
            docker_network=docker_network,
        )
    return labels
