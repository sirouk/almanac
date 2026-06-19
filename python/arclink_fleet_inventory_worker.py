#!/usr/bin/env python3
"""Periodic Sovereign fleet probe worker."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from arclink_asu import compute_asu, current_load
from arclink_boundary import json_loads_safe
from arclink_control import Config, append_arclink_audit, connect_db, ensure_schema, parse_utc_iso, queue_notification, utc_now, utc_now_iso
from arclink_fleet import fleet_host_ssh_endpoint, fleet_host_ssh_user
from arclink_secrets_regex import redact_secret_material, redact_then_truncate


PROBE_KINDS = ("liveness", "capacity", "inventory")
DEFAULT_CADENCES = {"liveness": 60, "capacity": 300, "inventory": 900}
DEFAULT_RETENTION = 1000
DEFAULT_MAX_PROBED_CAPACITY_SLOTS = 64
LOCAL_SSH_HOST_ALIASES = {"localhost", "127.0.0.1", "::1"}


class ArcLinkFleetInventoryWorkerError(ValueError):
    pass


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    payload: Mapping[str, Any] | None = None
    error: str = ""
    latency_ms: int = 0


ProbeRunner = Callable[[Mapping[str, Any], str], ProbeResult]


def _probe_id() -> str:
    import secrets

    return f"flprb_{secrets.token_hex(12)}"


def _clean_kind(kind: str) -> str:
    clean = str(kind or "").strip().lower()
    if clean not in PROBE_KINDS:
        raise ArcLinkFleetInventoryWorkerError(f"unsupported fleet probe kind: {clean or '<empty>'}")
    return clean


def _secretish_key(key: str) -> bool:
    lowered = str(key or "").lower()
    return any(part in lowered for part in ("token", "secret", "password", "api_key", "apikey", "credential", "authorization"))


def _redact_json_value(value: Any, *, key: str = "", string_limit: int = 400) -> Any:
    if isinstance(value, Mapping):
        return {str(child_key): _redact_json_value(child, key=str(child_key), string_limit=string_limit) for child_key, child in value.items()}
    if isinstance(value, list):
        return [_redact_json_value(child, string_limit=string_limit) for child in value]
    if isinstance(value, tuple):
        return [_redact_json_value(child, string_limit=string_limit) for child in value]
    if isinstance(value, str):
        if _secretish_key(key) and value.strip():
            return "[REDACTED]"
        return redact_then_truncate(value, limit=string_limit)
    return value


def _redacted_json(value: Mapping[str, Any] | None) -> str:
    try:
        return json.dumps(_redact_json_value(dict(value or {})), sort_keys=True)
    except (TypeError, ValueError):
        return json.dumps({"raw": redact_then_truncate(str(value or {}), limit=1000)}, sort_keys=True)


def _max_probed_capacity_slots() -> int:
    try:
        value = int(os.environ.get("ARCLINK_FLEET_PROBED_MAX_CAPACITY_SLOTS") or DEFAULT_MAX_PROBED_CAPACITY_SLOTS)
    except (TypeError, ValueError):
        value = DEFAULT_MAX_PROBED_CAPACITY_SLOTS
    return max(1, value)


def _now_from_iso(value: str | None):
    return parse_utc_iso(value) or utc_now()


def _latest_probe_at(conn: sqlite3.Connection, *, host_id: str, kind: str) -> str:
    row = conn.execute(
        """
        SELECT probed_at
        FROM arclink_fleet_host_probes
        WHERE host_id = ? AND kind = ?
        ORDER BY probed_at DESC, rowid DESC
        LIMIT 1
        """,
        (host_id, kind),
    ).fetchone()
    return str(row["probed_at"] or "") if row is not None else ""


def _truthy_env(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _is_local_ssh_host(ssh_host: str) -> bool:
    return str(ssh_host or "").strip().lower().rstrip(".") in LOCAL_SSH_HOST_ALIASES


def _is_docker_local_starter_host(host: Mapping[str, Any], metadata: Mapping[str, Any], executor: str) -> bool:
    if not _truthy_env("ARCLINK_DOCKER_MODE"):
        return False
    ssh_host = str(host.get("ssh_host") or metadata.get("ssh_host") or "").strip()
    if not _is_local_ssh_host(ssh_host):
        return False
    mode = str(metadata.get("control_network_mode") or metadata.get("arcpod_control_network_mode") or "").strip().lower()
    return (
        executor == "local"
        or bool(metadata.get("control_plane_host"))
        or mode in {"local", "docker", "control", "shared", "on", "1", "true"}
    )


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _docker_local_starter_probe(host: Mapping[str, Any], clean_kind: str) -> ProbeResult:
    capacity_slots = max(1, _int_value(host.get("capacity_slots"), 1))
    observed_load = max(0, _int_value(host.get("observed_load"), 0))
    payload: dict[str, Any] = {
        "ok": True,
        "kind": clean_kind,
        "admitting": True,
        "hostname": str(host.get("hostname") or ""),
        "observed_at": utc_now_iso(),
        "probe_mode": "docker-local-starter",
        "capacity_slots": capacity_slots,
        "observed_load": observed_load,
    }
    if clean_kind in {"capacity", "inventory"}:
        payload["hardware_summary"] = {"capacity_slots": capacity_slots}
    return ProbeResult(ok=True, payload=payload, latency_ms=0)


def probe_due(conn: sqlite3.Connection, *, host_id: str, kind: str, now_iso: str, cadence_seconds: int) -> bool:
    last = parse_utc_iso(_latest_probe_at(conn, host_id=host_id, kind=kind))
    if last is None:
        return True
    return (_now_from_iso(now_iso) - last).total_seconds() >= max(0, int(cadence_seconds))


class SshProbeRunner:
    """Run the worker-local allowlisted probe wrapper over SSH."""

    def __init__(self, *, key_path: str = "", known_hosts_file: str = "", timeout: int = 20) -> None:
        self.key_path = str(key_path or "")
        self.known_hosts_file = str(known_hosts_file or "")
        self.timeout = max(1, int(timeout))

    def __call__(self, host: Mapping[str, Any], kind: str) -> ProbeResult:
        clean_kind = _clean_kind(kind)
        if host.get("_arclink_docker_local_starter_probe"):
            return _docker_local_starter_probe(host, clean_kind)
        ssh_host = str(host.get("ssh_host") or host.get("hostname") or "").strip()
        ssh_user = str(host.get("ssh_user") or "arclink").strip()
        if not ssh_host:
            return ProbeResult(ok=False, error="fleet host has no SSH endpoint")
        command = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
        if self.known_hosts_file:
            command.extend(["-o", f"UserKnownHostsFile={self.known_hosts_file}"])
        if self.key_path:
            command.extend(["-i", self.key_path])
        command.extend([f"{ssh_user}@{ssh_host}", "--", "arclink-fleet-probe-wrapper", clean_kind])
        started = time.monotonic()
        try:
            completed = subprocess.run(command, text=True, capture_output=True, timeout=self.timeout, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            return ProbeResult(ok=False, error=str(exc), latency_ms=int((time.monotonic() - started) * 1000))
        latency_ms = int((time.monotonic() - started) * 1000)
        if completed.returncode != 0:
            return ProbeResult(ok=False, error=completed.stderr or completed.stdout or "probe failed", latency_ms=latency_ms)
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return ProbeResult(ok=False, error="probe returned invalid JSON", latency_ms=latency_ms)
        if not isinstance(payload, Mapping):
            return ProbeResult(ok=False, error="probe returned non-object JSON", latency_ms=latency_ms)
        return ProbeResult(ok=bool(payload.get("ok", True)), payload=dict(payload), latency_ms=latency_ms)


def _host_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT h.*, m.machine_id, m.ssh_host, m.ssh_user, m.status AS machine_status
        FROM arclink_fleet_hosts h
        LEFT JOIN arclink_inventory_machines m
          ON m.machine_host_link = h.host_id
         AND m.status != 'removed'
        ORDER BY h.hostname, h.host_id
        """
    ).fetchall()
    normalized: list[dict[str, Any]] = []
    for row in rows:
        host = dict(row)
        metadata = json_loads_safe(str(host.get("metadata_json") or "{}"))
        if isinstance(metadata, Mapping):
            host["ssh_host"] = fleet_host_ssh_endpoint(host)
            host["ssh_user"] = fleet_host_ssh_user(host, default=str(host.get("ssh_user") or "arclink"))
            executor = str(metadata.get("executor") or "").strip().lower()
        else:
            executor = ""
        host["_arclink_docker_local_starter_probe"] = _is_docker_local_starter_host(
            host,
            metadata if isinstance(metadata, Mapping) else {},
            executor,
        )
        normalized.append(host)
    return normalized


def _linked_machine_id(host: Mapping[str, Any]) -> str:
    return str(host.get("machine_id") or "").strip()


def _consecutive_liveness_failures(conn: sqlite3.Connection, *, host_id: str) -> int:
    rows = conn.execute(
        """
        SELECT ok
        FROM arclink_fleet_host_probes
        WHERE host_id = ? AND kind = 'liveness'
        ORDER BY probed_at DESC, rowid DESC
        LIMIT 10
        """,
        (host_id,),
    ).fetchall()
    failures = 0
    for row in rows:
        if int(row["ok"] or 0) == 1:
            break
        failures += 1
    return failures


def _notify_transition(conn: sqlite3.Connection, *, host_id: str, hostname: str, state: str, previous: str) -> None:
    if state == previous:
        return
    severity = "P1" if state == "unreachable" else "P2"
    if state == "active":
        message = f"Fleet host recovered: {hostname}"
    else:
        message = f"{severity} fleet host {state}: {hostname}"
    queue_notification(
        conn,
        target_kind="operator",
        target_id=f"fleet-host:{host_id}",
        channel_kind="operator",
        message=message,
        extra={"host_id": host_id, "hostname": hostname, "state": state, "previous_state": previous},
        commit=False,
    )


def _apply_liveness_state(
    conn: sqlite3.Connection,
    *,
    host: Mapping[str, Any],
    result: ProbeResult,
    notify: bool,
) -> None:
    host_id = str(host["host_id"])
    hostname = str(host["hostname"])
    previous_state = str(host.get("last_health_state") or host.get("status") or "")
    machine_id = _linked_machine_id(host)
    now = utc_now_iso()
    if result.ok:
        # Read-merge-write the LIVE metadata row (not the caller's possibly-stale
        # snapshot) and patch ONLY the two keys we own here. Crucially we serialize
        # with plain json -- NOT _redacted_json -- because the redacting serializer
        # truncates long values and replaces "secretish"-named keys with
        # [REDACTED], which would silently corrupt unrelated gate keys such as
        # image_sync_state / image_sync_digest that the placement-eligibility check
        # depends on. Host metadata is operator-managed config, not a probe payload.
        current_meta_row = conn.execute(
            "SELECT metadata_json FROM arclink_fleet_hosts WHERE host_id = ?",
            (host_id,),
        ).fetchone()
        metadata = json_loads_safe(
            str((current_meta_row["metadata_json"] if current_meta_row is not None else host.get("metadata_json")) or "{}")
        )
        if not isinstance(metadata, dict):
            metadata = {}
        host_sets = ["status = 'active'", "last_health_state = 'active'", "updated_at = ?"]
        host_params: list[Any] = [now]
        if bool(metadata.get("enrollment_pending_probe")):
            metadata["enrollment_pending_probe"] = False
            metadata["placement_activated_at"] = now
            host_sets.append("drain = 0")
            host_sets.append("metadata_json = ?")
            host_params.append(json.dumps(metadata, sort_keys=True))
        host_params.append(host_id)
        conn.execute(f"UPDATE arclink_fleet_hosts SET {', '.join(host_sets)} WHERE host_id = ?", host_params)
        if machine_id:
            conn.execute(
                "UPDATE arclink_inventory_machines SET status = 'ready', connectivity_summary_json = ?, last_probed_at = ? WHERE machine_id = ?",
                (_redacted_json({"ok": True}), now, machine_id),
            )
        if notify and previous_state not in {"", "active"}:
            _notify_transition(conn, host_id=host_id, hostname=hostname, state="active", previous=previous_state)
        return

    failures = _consecutive_liveness_failures(conn, host_id=host_id)
    if failures >= 10:
        next_status = "offline"
        next_state = "unreachable"
    elif failures >= 3:
        next_status = "degraded"
        next_state = "degraded"
    else:
        next_status = str(host.get("status") or "active")
        next_state = "probing_failed"
    conn.execute(
        "UPDATE arclink_fleet_hosts SET status = ?, last_health_state = ?, updated_at = ? WHERE host_id = ?",
        (next_status, next_state, now, host_id),
    )
    if machine_id and next_state in {"degraded", "unreachable"}:
        conn.execute(
            "UPDATE arclink_inventory_machines SET status = 'degraded', connectivity_summary_json = ?, last_probed_at = ? WHERE machine_id = ?",
            (_redacted_json({"ok": False, "error": result.error, "health_state": next_state}), now, machine_id),
        )
    if notify and next_state in {"degraded", "unreachable"}:
        _notify_transition(conn, host_id=host_id, hostname=hostname, state=next_state, previous=previous_state)


def _active_placement_count(conn: sqlite3.Connection, host_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM arclink_deployment_placements WHERE host_id = ? AND status = 'active'",
        (host_id,),
    ).fetchone()
    return int(row["count"] or 0)


def _apply_capacity_or_inventory(
    conn: sqlite3.Connection,
    *,
    host: Mapping[str, Any],
    kind: str,
    result: ProbeResult,
) -> None:
    if not result.ok:
        return
    payload = dict(result.payload or {})
    hardware = dict(payload.get("hardware_summary") or {}) if isinstance(payload.get("hardware_summary"), Mapping) else {}
    capacity_slots = min(
        _max_probed_capacity_slots(),
        max(1, int(payload.get("capacity_slots") or hardware.get("vcpu_cores") or host.get("capacity_slots") or 1)),
    )
    observed_load = int(payload.get("observed_load") or _active_placement_count(conn, str(host["host_id"])))
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE arclink_fleet_hosts
        SET capacity_slots = ?, observed_load = ?, updated_at = ?
        WHERE host_id = ?
        """,
        (max(1, capacity_slots), max(0, observed_load), now, str(host["host_id"])),
    )
    machine_id = _linked_machine_id(host)
    if not machine_id:
        return
    try:
        asu_capacity = compute_asu(hardware) if hardware else float(capacity_slots)
    except Exception as exc:
        # A partial probe (a zero/missing hardware dimension -- e.g. disk_gib=0
        # because the disk could not be measured) makes compute_asu fail closed.
        # We must NOT persist asu_capacity=0/ready from such a probe: that would
        # render an otherwise-healthy host unschedulable (ASU 0). Instead preserve
        # the machine's last known nonzero capacity (falling back to the probed
        # capacity_slots) and keep it ready so scheduling is unaffected, while
        # recording the partial-probe error for observability.
        prior = conn.execute(
            "SELECT asu_capacity, status FROM arclink_inventory_machines WHERE machine_id = ?",
            (machine_id,),
        ).fetchone()
        prior_capacity = float((prior["asu_capacity"] if prior is not None else 0) or 0)
        prior_status = str((prior["status"] if prior is not None else "") or "")
        if prior_capacity > 0 and prior_status == "ready":
            # We have a prior KNOWN-GOOD nonzero capacity from an earlier full
            # probe. A later partial probe must not erase it: keep the machine
            # ready on the preserved capacity so it stays schedulable, and never
            # persist asu_capacity=0 from the partial probe.
            conn.execute(
                """
                UPDATE arclink_inventory_machines
                SET asu_capacity = ?, connectivity_summary_json = ?, last_probed_at = ?
                WHERE machine_id = ?
                """,
                (
                    prior_capacity,
                    _redacted_json(
                        {
                            "ok": False,
                            "probe_kind": kind,
                            "partial_probe": True,
                            "preserved_asu_capacity": prior_capacity,
                            "error": f"invalid hardware summary: {redact_then_truncate(str(exc), limit=240)}",
                        }
                    ),
                    now,
                    machine_id,
                ),
            )
            return
        # No prior known-good capacity to preserve (machine was never fully
        # probed): a partial/invalid summary genuinely degrades it. We still do
        # NOT write a computed 0 capacity -- asu_capacity is left untouched.
        conn.execute(
            """
            UPDATE arclink_inventory_machines
            SET status = 'degraded', connectivity_summary_json = ?, last_probed_at = ?
            WHERE machine_id = ?
            """,
            (
                _redacted_json(
                    {
                        "ok": False,
                        "probe_kind": kind,
                        "error": f"invalid hardware summary: {redact_then_truncate(str(exc), limit=240)}",
                    }
                ),
                now,
                machine_id,
            ),
        )
        return
    asu_consumed = current_load(machine_id, conn)
    sets = [
        "status = 'ready'",
        "asu_capacity = ?",
        "asu_consumed = ?",
        "connectivity_summary_json = ?",
        "last_probed_at = ?",
    ]
    params: list[Any] = [
        float(asu_capacity),
        float(asu_consumed),
        _redacted_json({"ok": True, "probe_kind": kind}),
        now,
    ]
    if hardware:
        sets.append("hardware_summary_json = ?")
        params.append(_redacted_json(hardware))
    if kind == "inventory" and payload.get("machine_fingerprint"):
        sets.append("machine_fingerprint = CASE WHEN machine_fingerprint = '' THEN ? ELSE machine_fingerprint END")
        params.append(redact_secret_material(str(payload.get("machine_fingerprint") or "")))
    params.append(machine_id)
    conn.execute(f"UPDATE arclink_inventory_machines SET {', '.join(sets)} WHERE machine_id = ?", params)


def record_host_probe(
    conn: sqlite3.Connection,
    *,
    host: Mapping[str, Any],
    kind: str,
    result: ProbeResult,
    now_iso: str = "",
    notify: bool = True,
) -> dict[str, Any]:
    clean_kind = _clean_kind(kind)
    host_id = str(host.get("host_id") or "").strip()
    if not host_id:
        raise ArcLinkFleetInventoryWorkerError("fleet probe requires a host id")
    clean_now = now_iso or utc_now_iso()
    error = redact_then_truncate(result.error, limit=1000)
    # Run the SELECT-then-UPDATE state transition under a single BEGIN IMMEDIATE
    # transaction so two concurrent probe passes cannot interleave a stale read
    # with a write (lost-update). Re-read the host row INSIDE the lock so the
    # applied transition is computed from the just-locked committed state, not
    # from the possibly-stale row captured by the caller's pre-pass snapshot.
    own_txn = not conn.in_transaction
    if own_txn:
        conn.execute("BEGIN IMMEDIATE")
    try:
        fresh = conn.execute(
            "SELECT * FROM arclink_fleet_hosts WHERE host_id = ?",
            (host_id,),
        ).fetchone()
        if fresh is not None:
            # Preserve the joined machine-link / endpoint fields the caller
            # resolved (machine_id, ssh_host, ...) while taking the authoritative
            # fleet-host columns from the freshly-locked row.
            host = {**dict(host), **dict(fresh)}
        conn.execute(
            """
            INSERT INTO arclink_fleet_host_probes (
              probe_id, host_id, probed_at, kind, ok, latency_ms, payload_json, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _probe_id(),
                host_id,
                clean_now,
                clean_kind,
                1 if result.ok else 0,
                max(0, int(result.latency_ms or 0)),
                _redacted_json(result.payload),
                error,
            ),
        )
        if clean_kind == "liveness":
            _apply_liveness_state(conn, host=host, result=ProbeResult(result.ok, result.payload, error, result.latency_ms), notify=notify)
        else:
            _apply_capacity_or_inventory(conn, host=host, kind=clean_kind, result=ProbeResult(result.ok, result.payload, error, result.latency_ms))
    except Exception:
        if own_txn and conn.in_transaction:
            conn.rollback()
        raise
    try:
        append_arclink_audit(
            conn,
            action="fleet_host_probed",
            actor_id="system:fleet_inventory_worker",
            target_kind="fleet_host",
            target_id=host_id,
            reason=f"fleet inventory worker recorded {clean_kind} probe",
            metadata={"kind": clean_kind, "ok": bool(result.ok), "hostname": str(host.get("hostname") or "")},
            commit=False,
        )
    except Exception:
        if own_txn and conn.in_transaction:
            conn.rollback()
        raise
    if own_txn:
        conn.commit()
    return dict(conn.execute("SELECT * FROM arclink_fleet_hosts WHERE host_id = ?", (host_id,)).fetchone())


def prune_host_probes(conn: sqlite3.Connection, *, retention_per_host_kind: int = DEFAULT_RETENTION) -> int:
    keep = max(1, int(retention_per_host_kind))
    before = conn.total_changes
    conn.execute(
        """
        DELETE FROM arclink_fleet_host_probes
        WHERE rowid IN (
          SELECT rowid
          FROM (
            SELECT rowid,
                   ROW_NUMBER() OVER (
                     PARTITION BY host_id, kind
                     ORDER BY probed_at DESC, rowid DESC
                   ) AS rn
            FROM arclink_fleet_host_probes
          )
          WHERE rn > ?
        )
        """,
        (keep,),
    )
    deleted = conn.total_changes - before
    if deleted:
        conn.commit()
    return int(deleted)


def process_due_hosts(
    conn: sqlite3.Connection,
    *,
    runner: ProbeRunner | None = None,
    now_iso: str = "",
    cadences: Mapping[str, int] | None = None,
    force: bool = False,
    notify: bool = True,
    retention_per_host_kind: int = DEFAULT_RETENTION,
) -> dict[str, Any]:
    clean_now = now_iso or utc_now_iso()
    effective_cadences = {**DEFAULT_CADENCES, **dict(cadences or {})}
    probe_runner = runner or SshProbeRunner(
        key_path=os.environ.get("ARCLINK_FLEET_SSH_KEY_PATH", ""),
        known_hosts_file=os.environ.get("ARCLINK_FLEET_SSH_KNOWN_HOSTS_FILE", ""),
        timeout=int(os.environ.get("ARCLINK_FLEET_PROBE_TIMEOUT_SECONDS", "20") or "20"),
    )
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    try:
        for host in _host_rows(conn):
            for kind in PROBE_KINDS:
                if not force and not probe_due(
                    conn,
                    host_id=str(host["host_id"]),
                    kind=kind,
                    now_iso=clean_now,
                    cadence_seconds=int(effective_cadences[kind]),
                ):
                    continue
                try:
                    result = probe_runner(host, kind)
                except Exception as exc:
                    result = ProbeResult(ok=False, error=str(exc))
                # Each host's state transition is its own BEGIN IMMEDIATE
                # transaction inside record_host_probe; wrap the whole body in a
                # log-and-continue guard so a single bad row (a failed UPDATE,
                # a serialization conflict, ...) cannot abort the entire pass and
                # starve every other due host. The failed host's transaction is
                # rolled back independently and the next pass retries it.
                try:
                    refreshed = record_host_probe(conn, host=host, kind=kind, result=result, now_iso=clean_now, notify=notify)
                except Exception as exc:
                    if conn.in_transaction:
                        conn.rollback()
                    errors.append(
                        {
                            "host_id": str(host.get("host_id") or ""),
                            "hostname": str(host.get("hostname") or ""),
                            "kind": kind,
                            "error": redact_then_truncate(str(exc), limit=240),
                        }
                    )
                    continue
                host = {**host, **refreshed}
                results.append(
                    {
                        "host_id": str(host["host_id"]),
                        "hostname": str(host["hostname"]),
                        "kind": kind,
                        "ok": bool(result.ok),
                        "status": str(refreshed["status"]),
                        "health_state": str(refreshed["last_health_state"] or refreshed["status"]),
                        "error": redact_then_truncate(result.error, limit=240),
                    }
                )
    finally:
        # Retention pruning must always run, even if the loop above raised, so a
        # probe-history table cannot grow without bound after a bad pass.
        pruned = prune_host_probes(conn, retention_per_host_kind=retention_per_host_kind)
    return {"probes": results, "probe_count": len(results), "pruned": pruned, "errors": errors, "error_count": len(errors)}


def _load_conn() -> sqlite3.Connection:
    cfg = Config.from_env()
    conn = connect_db(cfg)
    ensure_schema(conn, cfg)
    return conn


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arclink-fleet-inventory-worker")
    parser.add_argument("--once", action="store_true", help="run one due-probe pass")
    parser.add_argument("--force", action="store_true", help="probe every host/kind regardless of cadence")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--notify", action="store_true")
    parser.add_argument("--retention-per-host-kind", type=int, default=int(os.environ.get("ARCLINK_FLEET_PROBE_RETENTION", str(DEFAULT_RETENTION)) or DEFAULT_RETENTION))
    args = parser.parse_args(argv)
    try:
        conn = _load_conn()
        result = process_due_hosts(conn, force=args.force, notify=args.notify, retention_per_host_kind=args.retention_per_host_kind)
        if args.json:
            print(json.dumps(result, sort_keys=True))
        else:
            print(f"fleet_inventory_worker probes={result['probe_count']} pruned={result['pruned']}")
        return 0
    except Exception as exc:
        print(redact_then_truncate(str(exc), limit=300), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
