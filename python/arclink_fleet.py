#!/usr/bin/env python3
"""ArcLink fleet host registry and deterministic placement."""
from __future__ import annotations

import secrets
import sqlite3
from typing import Any, Mapping

from arclink_control import append_arclink_audit, append_arclink_event, utc_now_iso
from arclink_boundary import json_dumps_safe, json_loads_safe, reject_secret_material, rowdict


class ArcLinkFleetError(ValueError):
    pass


FLEET_HOST_STATUSES = frozenset({"active", "degraded", "offline"})
PLACEMENT_STATUSES = frozenset({"active", "removed"})


def _fleet_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def _reject_secrets(value: Any, *, path: str = "$") -> None:
    reject_secret_material(value, path=path, label="ArcLink fleet", error_cls=ArcLinkFleetError)


# ---------------------------------------------------------------------------
# Host registry
# ---------------------------------------------------------------------------

def register_fleet_host(
    conn: sqlite3.Connection,
    *,
    hostname: str,
    region: str = "",
    tags: Mapping[str, Any] | None = None,
    capacity_slots: int = 10,
    host_id: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    clean_hostname = str(hostname or "").strip().lower()
    if not clean_hostname:
        raise ArcLinkFleetError("ArcLink fleet hosts require a hostname")
    clean_region = str(region or "").strip().lower()
    if tags is not None:
        _reject_secrets(tags, path="$.tags")
    if metadata is not None:
        _reject_secrets(metadata, path="$.metadata")
    tags_json = (
        json_dumps_safe(tags, label="ArcLink fleet", error_cls=ArcLinkFleetError)
        if tags is not None
        else None
    )
    metadata_json = (
        json_dumps_safe(metadata, label="ArcLink fleet", error_cls=ArcLinkFleetError)
        if metadata is not None
        else None
    )
    if capacity_slots < 1:
        raise ArcLinkFleetError("ArcLink fleet host capacity must be at least 1")

    existing = conn.execute(
        "SELECT * FROM arclink_fleet_hosts WHERE LOWER(hostname) = ?",
        (clean_hostname,),
    ).fetchone()
    if existing is not None:
        sets: list[str] = []
        params: list[Any] = []
        if str(existing["region"] or "") != clean_region:
            sets.append("region = ?")
            params.append(clean_region)
        if int(existing["capacity_slots"]) != int(capacity_slots):
            sets.append("capacity_slots = ?")
            params.append(int(capacity_slots))
        if tags_json is not None and str(existing["tags_json"] or "{}") != tags_json:
            sets.append("tags_json = ?")
            params.append(tags_json)
        if metadata_json is not None and str(existing["metadata_json"] or "{}") != metadata_json:
            sets.append("metadata_json = ?")
            params.append(metadata_json)
        if sets:
            sets.append("updated_at = ?")
            params.append(utc_now_iso())
            params.append(str(existing["host_id"]))
            conn.execute(f"UPDATE arclink_fleet_hosts SET {', '.join(sets)} WHERE host_id = ?", params)
            conn.commit()
            existing = conn.execute(
                "SELECT * FROM arclink_fleet_hosts WHERE host_id = ?",
                (str(existing["host_id"]),),
            ).fetchone()
        return dict(existing)

    clean_id = host_id.strip() if host_id else _fleet_id("host")
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO arclink_fleet_hosts (
          host_id, hostname, region, tags_json, status, drain, capacity_slots,
          observed_load, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'active', 0, ?, 0, ?, ?, ?)
        """,
        (clean_id, clean_hostname, clean_region, tags_json or "{}", capacity_slots, metadata_json or "{}", now, now),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM arclink_fleet_hosts WHERE host_id = ?", (clean_id,)).fetchone())


def update_fleet_host(
    conn: sqlite3.Connection,
    *,
    host_id: str,
    status: str | None = None,
    drain: bool | None = None,
    observed_load: int | None = None,
    capacity_slots: int | None = None,
) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM arclink_fleet_hosts WHERE host_id = ?", (host_id,)).fetchone()
    if row is None:
        raise ArcLinkFleetError(f"unknown ArcLink fleet host: {host_id}")
    sets: list[str] = []
    params: list[Any] = []
    if status is not None:
        if status not in FLEET_HOST_STATUSES:
            raise ArcLinkFleetError(f"unsupported fleet host status: {status}")
        sets.append("status = ?")
        params.append(status)
    if drain is not None:
        sets.append("drain = ?")
        params.append(1 if drain else 0)
    if observed_load is not None:
        if observed_load < 0:
            raise ArcLinkFleetError("observed load cannot be negative")
        sets.append("observed_load = ?")
        params.append(observed_load)
    if capacity_slots is not None:
        if capacity_slots < 1:
            raise ArcLinkFleetError("capacity must be at least 1")
        sets.append("capacity_slots = ?")
        params.append(capacity_slots)
    if not sets:
        return dict(row)
    sets.append("updated_at = ?")
    params.append(utc_now_iso())
    params.append(host_id)
    conn.execute(f"UPDATE arclink_fleet_hosts SET {', '.join(sets)} WHERE host_id = ?", params)
    conn.commit()
    return dict(conn.execute("SELECT * FROM arclink_fleet_hosts WHERE host_id = ?", (host_id,)).fetchone())


def get_fleet_host(conn: sqlite3.Connection, *, host_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM arclink_fleet_hosts WHERE host_id = ?", (host_id,)).fetchone()
    if row is None:
        raise ArcLinkFleetError(f"unknown ArcLink fleet host: {host_id}")
    return dict(row)


def list_fleet_hosts(conn: sqlite3.Connection, *, status: str = "") -> list[dict[str, Any]]:
    if status:
        rows = conn.execute(
            "SELECT * FROM arclink_fleet_hosts WHERE status = ? ORDER BY hostname",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM arclink_fleet_hosts ORDER BY hostname").fetchall()
    return [dict(r) for r in rows]


def fleet_capacity_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    hosts = list_fleet_hosts(conn)
    total_slots = sum(int(h["capacity_slots"]) for h in hosts)
    total_load = sum(int(h["observed_load"]) for h in hosts)
    active_hosts = [h for h in hosts if h["status"] == "active" and not int(h["drain"])]
    return {
        "total_hosts": len(hosts),
        "active_hosts": len(active_hosts),
        "total_slots": total_slots,
        "total_load": total_load,
        "available_slots": total_slots - total_load,
        "hosts": [
            {
                "host_id": h["host_id"],
                "hostname": h["hostname"],
                "region": h["region"],
                "status": h["status"],
                "drain": bool(int(h["drain"])),
                "capacity_slots": int(h["capacity_slots"]),
                "observed_load": int(h["observed_load"]),
                "headroom": int(h["capacity_slots"]) - int(h["observed_load"]),
            }
            for h in hosts
        ],
    }


def reconcile_fleet_observed_loads(conn: sqlite3.Connection, *, host_id: str = "") -> list[dict[str, Any]]:
    """Repair host load from active placement rows without deleting host registrations."""
    clean_host_id = str(host_id or "").strip()
    params: list[Any] = []
    where = ""
    if clean_host_id:
        where = "WHERE h.host_id = ?"
        params.append(clean_host_id)
    rows = conn.execute(
        f"""
        SELECT
          h.host_id,
          h.hostname,
          h.observed_load AS old_load,
          COUNT(p.placement_id) AS active_load
        FROM arclink_fleet_hosts h
        LEFT JOIN arclink_deployment_placements p
          ON p.host_id = h.host_id
         AND p.status = 'active'
        {where}
        GROUP BY h.host_id, h.hostname, h.observed_load
        """,
        params,
    ).fetchall()
    repaired: list[dict[str, Any]] = []
    now = utc_now_iso()
    for row in rows:
        old_load = int(row["old_load"])
        active_load = int(row["active_load"])
        if old_load == active_load:
            continue
        conn.execute(
            "UPDATE arclink_fleet_hosts SET observed_load = ?, updated_at = ? WHERE host_id = ?",
            (active_load, now, row["host_id"]),
        )
        repaired.append(
            {
                "host_id": str(row["host_id"]),
                "hostname": str(row["hostname"]),
                "old_load": old_load,
                "observed_load": active_load,
            }
        )
    if repaired:
        conn.commit()
    return repaired


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------

def place_deployment(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    region: str = "",
    required_tags: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Choose the best healthy host with enough headroom."""
    clean_deployment = str(deployment_id or "").strip()
    if not clean_deployment:
        raise ArcLinkFleetError("ArcLink placement requires a deployment id")
    _reject_secrets(required_tags, path="$.required_tags")

    # Check for existing active placement
    existing = conn.execute(
        "SELECT * FROM arclink_deployment_placements WHERE deployment_id = ? AND status = 'active'",
        (clean_deployment,),
    ).fetchone()
    if existing is not None:
        return dict(existing)

    hosts = list_fleet_hosts(conn)
    candidates = _filter_placement_candidates(hosts, region=region, required_tags=required_tags)
    if not candidates:
        raise ArcLinkFleetError(_placement_rejection_summary(hosts, region=region, required_tags=required_tags))

    # Deterministic: pick host with most headroom, break ties by hostname.
    best = sorted(candidates, key=lambda h: (-int(h["headroom"]), str(h["hostname"])))[0]

    placement_id = _fleet_id("plc")
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO arclink_deployment_placements (placement_id, deployment_id, host_id, status, placed_at)
        VALUES (?, ?, ?, 'active', ?)
        """,
        (placement_id, clean_deployment, best["host_id"], now),
    )
    # Increment observed load
    conn.execute(
        "UPDATE arclink_fleet_hosts SET observed_load = observed_load + 1, updated_at = ? WHERE host_id = ?",
        (now, best["host_id"]),
    )
    conn.commit()
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=clean_deployment,
        event_type="placement_assigned",
        metadata={"host_id": best["host_id"], "hostname": best["hostname"], "placement_id": placement_id},
    )
    return dict(conn.execute("SELECT * FROM arclink_deployment_placements WHERE placement_id = ?", (placement_id,)).fetchone())


def remove_placement(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM arclink_deployment_placements WHERE deployment_id = ? AND status = 'active'",
        (deployment_id,),
    ).fetchone()
    if row is None:
        return None
    now = utc_now_iso()
    conn.execute(
        "UPDATE arclink_deployment_placements SET status = 'removed', removed_at = ? WHERE placement_id = ?",
        (now, row["placement_id"]),
    )
    conn.execute(
        "UPDATE arclink_fleet_hosts SET observed_load = MAX(0, observed_load - 1), updated_at = ? WHERE host_id = ?",
        (now, row["host_id"]),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM arclink_deployment_placements WHERE placement_id = ?", (row["placement_id"],)).fetchone())


def get_deployment_placement(conn: sqlite3.Connection, *, deployment_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM arclink_deployment_placements WHERE deployment_id = ? AND status = 'active'",
        (deployment_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def _filter_placement_candidates(
    hosts: list[dict[str, Any]],
    *,
    region: str = "",
    required_tags: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    result = []
    for h in hosts:
        if h["status"] != "active":
            continue
        if int(h.get("drain", 0)):
            continue
        headroom = int(h["capacity_slots"]) - int(h["observed_load"])
        if headroom <= 0:
            continue
        if region and h.get("region", "") != region:
            continue
        if required_tags:
            host_tags = json_loads_safe(h.get("tags_json", "{}"))
            if not all(host_tags.get(k) == v for k, v in required_tags.items()):
                continue
        result.append({**h, "headroom": headroom})
    return result


def _placement_rejection_summary(
    hosts: list[dict[str, Any]],
    *,
    region: str = "",
    required_tags: Mapping[str, str] | None = None,
) -> str:
    if not hosts:
        return "no eligible ArcLink fleet hosts for placement: no active hosts registered"
    reasons: set[str] = set()
    for h in hosts:
        if h["status"] != "active":
            reasons.add("unhealthy")
            continue
        if int(h.get("drain", 0)):
            reasons.add("draining")
            continue
        headroom = int(h["capacity_slots"]) - int(h["observed_load"])
        if headroom <= 0:
            reasons.add("saturated")
            continue
        if region and h.get("region", "") != region:
            reasons.add("region_mismatch")
            continue
        if required_tags:
            host_tags = json_loads_safe(h.get("tags_json", "{}"))
            if not all(host_tags.get(k) == v for k, v in required_tags.items()):
                reasons.add("tag_mismatch")
                continue
    detail = ", ".join(sorted(reasons)) or "no matching host"
    return f"no eligible ArcLink fleet hosts for placement: {detail}"
