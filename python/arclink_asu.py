#!/usr/bin/env python3
"""ArcPod Standard Unit capacity helpers."""
from __future__ import annotations

import math
import os
import sqlite3
from typing import Any, Mapping


class ArcLinkASUError(ValueError):
    pass


def _float_env(env: Mapping[str, str], name: str, default: float) -> float:
    raw = str(env.get(name, "") or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ArcLinkASUError(f"{name} must be numeric") from exc
    if value <= 0:
        raise ArcLinkASUError(f"{name} must be greater than zero")
    return value


def _number(payload: Mapping[str, Any], names: tuple[str, ...], *, label: str) -> float:
    for name in names:
        if name not in payload:
            continue
        raw = payload.get(name)
        if raw in (None, ""):
            continue
        try:
            return float(raw)
        except (TypeError, ValueError) as exc:
            raise ArcLinkASUError(f"{label} must be numeric") from exc
    raise ArcLinkASUError(f"hardware summary missing {label}")


def compute_asu(hardware_summary: Mapping[str, Any], env: Mapping[str, str] | None = None) -> int:
    """Compute how many standard Pods fit on a machine.

    The defaults are intentionally conservative: 1 vCPU, 4 GiB RAM, and
    30 GiB disk per ArcPod.
    """
    source_env = env or os.environ
    vcpu_per_pod = _float_env(source_env, "ARCLINK_ASU_VCPU_PER_POD", 1.0)
    ram_per_pod = _float_env(source_env, "ARCLINK_ASU_RAM_PER_POD", 4.0)
    disk_per_pod = _float_env(source_env, "ARCLINK_ASU_DISK_PER_POD", 30.0)

    vcpu = _number(hardware_summary, ("vcpu_cores", "vcpus", "cpu_count", "nproc"), label="vCPU count")
    ram = _number(hardware_summary, ("ram_gib", "memory_gib", "memory_total_gib"), label="RAM GiB")
    disk = _number(hardware_summary, ("disk_gib", "disk_total_gib", "root_disk_gib"), label="disk GiB")

    if vcpu <= 0:
        raise ArcLinkASUError("vCPU count must be greater than zero")
    if ram < 0 or disk < 0:
        raise ArcLinkASUError("RAM and disk cannot be negative")
    return max(0, int(min(math.floor(vcpu / vcpu_per_pod), math.floor(ram / ram_per_pod), math.floor(disk / disk_per_pod))))


def current_load(machine_id: str, conn: sqlite3.Connection) -> float:
    """Return active ArcPod load for a registered inventory machine."""
    row = conn.execute(
        "SELECT machine_host_link, asu_consumed FROM arclink_inventory_machines WHERE machine_id = ?",
        (str(machine_id or "").strip(),),
    ).fetchone()
    if row is None:
        raise ArcLinkASUError(f"unknown inventory machine: {machine_id}")
    host_id = str(row["machine_host_link"] or "")
    if not host_id:
        return float(row["asu_consumed"] or 0)
    count = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM arclink_deployment_placements
        WHERE host_id = ? AND status = 'active'
        """,
        (host_id,),
    ).fetchone()["count"]
    return float(count or 0)
