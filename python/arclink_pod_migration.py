#!/usr/bin/env python3
"""ArcLink 1:1 Pod migration orchestration.

The module keeps migration state in the control plane while routing host
mutation through the existing executor abstraction. File capture is deliberately
small and injectable so tests can use temporary state roots without touching
private live state.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from arclink_boundary import json_dumps_safe, json_loads_safe, reject_secret_material
from arclink_control import (
    append_arclink_audit,
    append_arclink_event,
    complete_arclink_operation_idempotency,
    fail_arclink_operation_idempotency,
    reserve_arclink_operation_idempotency,
    upsert_arclink_service_health,
    utc_now_iso,
)
from arclink_executor import (
    ArcLinkExecutor,
    DockerComposeApplyRequest,
    DockerComposeLifecycleRequest,
)
from arclink_provisioning import render_arclink_provisioning_intent, render_arclink_state_roots


OPERATION_KIND = "pod_migration"
DEFAULT_GC_DAYS = 7


class ArcLinkPodMigrationError(ValueError):
    pass


Verifier = Callable[[sqlite3.Connection, Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any] | bool]


def _migration_id() -> str:
    return f"mig_{secrets.token_hex(12)}"


def _placement_id() -> str:
    return f"plc_{secrets.token_hex(12)}"


def _reject_secrets(value: Any, *, path: str = "$") -> None:
    reject_secret_material(value, path=path, label="ArcLink Pod migration", error_cls=ArcLinkPodMigrationError)


def _json_dumps(value: Any) -> str:
    return json_dumps_safe(value, label="ArcLink Pod migration", error_cls=ArcLinkPodMigrationError)


def _utc(dt: datetime | None = None) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return _utc(dt).isoformat()


def _parse_iso(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _load_deployment(conn: sqlite3.Connection, deployment_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM arclink_deployments WHERE deployment_id = ?", (deployment_id,)).fetchone()
    if row is None:
        raise ArcLinkPodMigrationError(f"ArcLink Pod migration deployment not found: {deployment_id}")
    return dict(row)


def _active_placement(conn: sqlite3.Connection, deployment_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT *
        FROM arclink_deployment_placements
        WHERE deployment_id = ? AND status = 'active'
        ORDER BY placed_at DESC, placement_id DESC
        LIMIT 1
        """,
        (deployment_id,),
    ).fetchone()
    if row is None:
        raise ArcLinkPodMigrationError(f"ArcLink Pod migration requires an active placement: {deployment_id}")
    return dict(row)


def _host(conn: sqlite3.Connection, host_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM arclink_fleet_hosts WHERE host_id = ?", (host_id,)).fetchone()
    if row is None:
        raise ArcLinkPodMigrationError(f"ArcLink Pod migration host not found: {host_id}")
    return dict(row)


def _resolve_target_host(
    conn: sqlite3.Connection,
    *,
    source_host_id: str,
    target_machine_id: str,
) -> tuple[dict[str, Any], str]:
    clean_target = str(target_machine_id or "").strip()
    if not clean_target or clean_target.lower() == "current":
        return _host(conn, source_host_id), "current"

    machine = conn.execute(
        """
        SELECT *
        FROM arclink_inventory_machines
        WHERE machine_id = ? AND status != 'removed'
        """,
        (clean_target,),
    ).fetchone()
    if machine is not None:
        host_id = str(machine["machine_host_link"] or "").strip()
        if not host_id:
            raise ArcLinkPodMigrationError(f"ArcLink inventory machine has no fleet host link: {clean_target}")
        return _host(conn, host_id), clean_target

    host = conn.execute("SELECT * FROM arclink_fleet_hosts WHERE host_id = ?", (clean_target,)).fetchone()
    if host is not None:
        return dict(host), clean_target
    raise ArcLinkPodMigrationError(f"ArcLink Pod migration target machine/host not found: {clean_target}")


def _metadata_roots(deployment: Mapping[str, Any], host: Mapping[str, Any]) -> tuple[dict[str, str], str]:
    metadata = json_loads_safe(str(deployment.get("metadata_json") or "{}"))
    raw_roots = metadata.get("state_roots") if isinstance(metadata, Mapping) else {}
    if isinstance(raw_roots, Mapping) and str(raw_roots.get("root") or "").strip():
        roots = {str(key): str(value) for key, value in raw_roots.items() if str(value or "").strip()}
        base = str(metadata.get("state_root_base") or Path(str(roots["root"])).parent)
        return roots, base
    host_meta = json_loads_safe(str(host.get("metadata_json") or "{}"))
    base = str(host_meta.get("state_root_base") or os.environ.get("ARCLINK_STATE_ROOT_BASE") or "/arcdata/deployments")
    roots = render_arclink_state_roots(
        deployment_id=str(deployment["deployment_id"]),
        prefix=str(deployment["prefix"]),
        state_root_base=base,
    )
    return roots, base


def _target_state_root_base(host: Mapping[str, Any], fallback: str) -> str:
    host_meta = json_loads_safe(str(host.get("metadata_json") or "{}"))
    return str(host_meta.get("state_root_base") or fallback or os.environ.get("ARCLINK_STATE_ROOT_BASE") or "/arcdata/deployments")


def _ensure_removed_target_placement(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    source_placement_id: str,
    source_host_id: str,
    target_host_id: str,
) -> str:
    if source_host_id == target_host_id:
        return source_placement_id
    existing = conn.execute(
        """
        SELECT placement_id
        FROM arclink_deployment_placements
        WHERE deployment_id = ? AND host_id = ? AND status = 'removed'
        ORDER BY placed_at DESC, placement_id DESC
        LIMIT 1
        """,
        (deployment_id, target_host_id),
    ).fetchone()
    if existing is not None:
        return str(existing["placement_id"])
    placement_id = _placement_id()
    conn.execute(
        """
        INSERT INTO arclink_deployment_placements (placement_id, deployment_id, host_id, status, placed_at, removed_at)
        VALUES (?, ?, ?, 'removed', ?, ?)
        """,
        (placement_id, deployment_id, target_host_id, utc_now_iso(), "migration_target_pending"),
    )
    return placement_id


def _migration_row(conn: sqlite3.Connection, migration_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM arclink_pod_migrations WHERE migration_id = ?", (migration_id,)).fetchone()
    return dict(row) if row is not None else None


def plan_pod_migration(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    target_machine_id: str = "",
    migration_id: str = "",
    reason: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    clean_deployment = str(deployment_id or "").strip()
    if not clean_deployment:
        raise ArcLinkPodMigrationError("ArcLink Pod migration requires a deployment id")
    clean_migration = str(migration_id or "").strip() or _migration_id()
    clean_reason = str(reason or "").strip()
    _reject_secrets({"reason": clean_reason, "target_machine_id": target_machine_id}, path="$")

    existing = _migration_row(conn, clean_migration)
    if existing is not None:
        if str(existing["deployment_id"]) != clean_deployment:
            raise ArcLinkPodMigrationError("ArcLink Pod migration id is already bound to another deployment")
        clean_target = str(target_machine_id or "").strip()
        existing_target = str(existing.get("target_machine_id") or "").strip()
        if clean_target and existing_target and clean_target != existing_target:
            raise ArcLinkPodMigrationError("ArcLink Pod migration id is already bound to another target")
        return existing

    deployment = _load_deployment(conn, clean_deployment)
    source_placement = _active_placement(conn, clean_deployment)
    source_host = _host(conn, str(source_placement["host_id"]))
    source_roots, source_base = _metadata_roots(deployment, source_host)
    target_host, resolved_target = _resolve_target_host(
        conn,
        source_host_id=str(source_placement["host_id"]),
        target_machine_id=target_machine_id,
    )
    if str(target_host.get("status") or "") != "active" or int(target_host.get("drain") or 0):
        raise ArcLinkPodMigrationError("ArcLink Pod migration target host is not available")
    target_base = _target_state_root_base(target_host, source_base)
    target_roots = render_arclink_state_roots(
        deployment_id=clean_deployment,
        prefix=str(deployment["prefix"]),
        state_root_base=target_base,
    )
    target_placement_id = ""
    if not dry_run:
        target_placement_id = _ensure_removed_target_placement(
            conn,
            deployment_id=clean_deployment,
            source_placement_id=str(source_placement["placement_id"]),
            source_host_id=str(source_placement["host_id"]),
            target_host_id=str(target_host["host_id"]),
        )
    capture_dir = str(Path(target_base) / ".migrations" / clean_migration)
    host_meta = {
        "host_id": str(target_host["host_id"]),
        "hostname": str(target_host["hostname"]),
        "state_root_base": target_base,
        "dry_run": bool(dry_run),
    }
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO arclink_pod_migrations (
          migration_id, deployment_id, source_placement_id, target_placement_id,
          source_host_id, target_host_id, target_machine_id, source_state_root,
          target_state_root, capture_dir, status, operation_idempotency_key,
          capture_manifest_json, rollback_metadata_json, target_host_metadata_json,
          created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'planned', ?, '{}', ?, ?, ?, ?)
        """,
        (
            clean_migration,
            clean_deployment,
            str(source_placement["placement_id"]),
            target_placement_id,
            str(source_placement["host_id"]),
            str(target_host["host_id"]),
            resolved_target,
            str(source_roots.get("root") or ""),
            str(target_roots.get("root") or ""),
            capture_dir,
            f"arclink:migration:{clean_migration}",
            _json_dumps({"source_placement_id": str(source_placement["placement_id"]), "reason": clean_reason}),
            _json_dumps(host_meta),
            now,
            now,
        ),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM arclink_pod_migrations WHERE migration_id = ?", (clean_migration,)).fetchone())


def _operation_intent(row: Mapping[str, Any], *, dry_run: bool) -> dict[str, Any]:
    return {
        "migration_id": str(row["migration_id"]),
        "deployment_id": str(row["deployment_id"]),
        "source_host_id": str(row["source_host_id"]),
        "target_host_id": str(row["target_host_id"]),
        "target_machine_id": str(row["target_machine_id"]),
        "source_state_root": str(row["source_state_root"]),
        "target_state_root": str(row["target_state_root"]),
        "dry_run": bool(dry_run),
    }


def _boundary_for(rel_path: str) -> str:
    clean = rel_path.replace("\\", "/")
    if clean == "vault" or clean.startswith("vault/"):
        return "vault"
    if clean.startswith("state/memory/") or clean == "state/memory":
        return "memory"
    if clean.startswith("state/hermes-home/sessions/"):
        return "sessions"
    if clean == "config" or clean.startswith("config/"):
        return "configs"
    if clean.startswith("state/hermes-home/"):
        return "hermes_home"
    if "secrets" in clean.split("/"):
        return "secrets"
    return "state"


def _copy_capture(source_root: Path, capture_dir: Path) -> dict[str, Any]:
    staged_root = capture_dir / "source-root"
    capture_dir.mkdir(parents=True, exist_ok=True)
    if staged_root.exists():
        shutil.rmtree(staged_root)
    if source_root.exists():
        shutil.copytree(source_root, staged_root, symlinks=True)
    else:
        staged_root.mkdir(parents=True, exist_ok=True)

    files: list[dict[str, Any]] = []
    for path in sorted(staged_root.rglob("*")):
        if path.is_symlink():
            path.unlink()
            continue
        if not path.is_file():
            continue
        rel = path.relative_to(staged_root).as_posix()
        stat = path.stat()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append(
            {
                "path": rel,
                "boundary": _boundary_for(rel),
                "size": stat.st_size,
                "mode": oct(stat.st_mode & 0o777),
                "sha256": digest,
            }
        )
    return {"files": files, "file_count": len(files)}


def _materialize_capture(capture_dir: Path, target_root: Path) -> None:
    staged_root = capture_dir / "source-root"
    target_root.mkdir(parents=True, exist_ok=True)
    if staged_root.exists():
        shutil.copytree(staged_root, target_root, dirs_exist_ok=True, symlinks=True)


def _default_verifier(
    conn: sqlite3.Connection,
    migration: Mapping[str, Any],
    intent: Mapping[str, Any],
) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT service_name, status FROM arclink_service_health WHERE deployment_id = ?",
        (str(migration["deployment_id"]),),
    ).fetchall()
    blockers = {
        str(row["service_name"]): str(row["status"])
        for row in rows
        if str(row["status"]) in {"failed", "unhealthy", "missing"}
    }
    return {"healthy": not blockers, "blockers": blockers, "checked": "service_health"}


def _normalize_verification(value: Mapping[str, Any] | bool) -> dict[str, Any]:
    if isinstance(value, Mapping):
        result = dict(value)
        result["healthy"] = bool(result.get("healthy"))
        return result
    return {"healthy": bool(value)}


def _deployment_lifecycle_files(row: Mapping[str, Any]) -> tuple[str, str, str]:
    config_root = Path(str(row.get("source_state_root") or "")) / "config"
    return (
        str(row["deployment_id"]),
        str(config_root / "arclink.env"),
        str(config_root / "compose.yaml"),
    )


def _intent_lifecycle_files(deployment_id: str, intent: Mapping[str, Any]) -> tuple[str, str, str]:
    roots = intent.get("state_roots") if isinstance(intent.get("state_roots"), Mapping) else {}
    config_root = Path(str((roots or {}).get("root") or "")) / "config"
    return (
        deployment_id,
        str(config_root / "arclink.env"),
        str(config_root / "compose.yaml"),
    )


def _compose_lifecycle_metadata(result: Any) -> dict[str, Any]:
    return {
        "status": str(getattr(result, "status", "")),
        "action": str(getattr(result, "action", "")),
        "live": bool(getattr(result, "live", False)),
    }


def _rollback_lifecycle(
    *,
    executor: ArcLinkExecutor,
    row: Mapping[str, Any],
    operation_key: str,
    target_intent: Mapping[str, Any] | None = None,
    source_stopped: bool = False,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    target_is_source = str(row.get("target_host_id") or "") == str(row.get("source_host_id") or "") or (
        str(row.get("target_placement_id") or "") != ""
        and str(row.get("target_placement_id") or "") == str(row.get("source_placement_id") or "")
    )
    if target_intent is not None and not target_is_source:
        deployment_id, env_file, compose_file = _intent_lifecycle_files(str(row["deployment_id"]), target_intent)
        try:
            result = executor.docker_compose_lifecycle(
                DockerComposeLifecycleRequest(
                    deployment_id=deployment_id,
                    action="teardown",
                    env_file=env_file,
                    compose_file=compose_file,
                    idempotency_key=f"{operation_key}:teardown-target-rollback",
                    remove_volumes=False,
                )
            )
            metadata["target_teardown"] = _compose_lifecycle_metadata(result)
        except Exception as exc:
            metadata["target_teardown"] = {"status": "failed", "error_type": exc.__class__.__name__}
    if source_stopped:
        deployment_id, env_file, compose_file = _deployment_lifecycle_files(row)
        try:
            result = executor.docker_compose_lifecycle(
                DockerComposeLifecycleRequest(
                    deployment_id=deployment_id,
                    action="restart",
                    env_file=env_file,
                    compose_file=compose_file,
                    idempotency_key=f"{operation_key}:restart-source-rollback",
                )
            )
            metadata["source_restart"] = _compose_lifecycle_metadata(result)
        except Exception as exc:
            metadata["source_restart"] = {"status": "failed", "error_type": exc.__class__.__name__}
    return metadata


def _render_target_intent(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    target_host: Mapping[str, Any],
    fallback_base: str,
    env: Mapping[str, str] | None,
) -> dict[str, Any]:
    deployment = _load_deployment(conn, deployment_id)
    metadata = json_loads_safe(str(deployment.get("metadata_json") or "{}"))
    target_base = _target_state_root_base(target_host, fallback_base)
    host_meta = json_loads_safe(str(target_host.get("metadata_json") or "{}"))
    return render_arclink_provisioning_intent(
        conn,
        deployment_id=deployment_id,
        base_domain=str(metadata.get("base_domain") or deployment.get("base_domain") or ""),
        edge_target=str(host_meta.get("edge_target") or metadata.get("edge_target") or ""),
        state_root_base=target_base,
        ingress_mode=str(metadata.get("ingress_mode") or ""),
        tailscale_dns_name=str(metadata.get("tailscale_dns_name") or ""),
        tailscale_host_strategy=str(metadata.get("tailscale_host_strategy") or ""),
        env=env,
    )


def _mark_rollback(
    conn: sqlite3.Connection,
    *,
    row: Mapping[str, Any],
    verification: Mapping[str, Any],
    error: str,
    lifecycle_metadata: Mapping[str, Any] | None = None,
) -> None:
    now = utc_now_iso()
    rollback_metadata = json_loads_safe(str(row.get("rollback_metadata_json") or "{}"))
    if not isinstance(rollback_metadata, Mapping):
        rollback_metadata = {}
    rollback_payload = dict(rollback_metadata)
    rollback_payload.update(
        {
            "rolled_back_at": now,
            "source_placement_id": str(row["source_placement_id"]),
            "target_placement_id": str(row.get("target_placement_id") or ""),
            "lifecycle": dict(lifecycle_metadata or {}),
        }
    )
    if str(row.get("target_placement_id") or "") and str(row["target_placement_id"]) != str(row["source_placement_id"]):
        conn.execute(
            "UPDATE arclink_deployment_placements SET status = 'removed', removed_at = ? WHERE placement_id = ?",
            (now, str(row["target_placement_id"])),
        )
    conn.execute(
        "UPDATE arclink_deployment_placements SET status = 'active', removed_at = '' WHERE placement_id = ?",
        (str(row["source_placement_id"]),),
    )
    conn.execute(
        """
        UPDATE arclink_pod_migrations
        SET status = 'rolled_back',
            verification_json = ?,
            rollback_metadata_json = ?,
            error = ?,
            updated_at = ?,
            completed_at = ?
        WHERE migration_id = ?
        """,
        (_json_dumps(verification), _json_dumps(rollback_payload), error[:1000], now, now, str(row["migration_id"])),
    )
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=str(row["deployment_id"]),
        event_type="pod_migration_rolled_back",
        metadata={"migration_id": str(row["migration_id"]), "verification": dict(verification)},
        commit=False,
    )
    append_arclink_audit(
        conn,
        action="pod_migration_rolled_back",
        actor_id="system:pod_migration",
        target_kind="deployment",
        target_id=str(row["deployment_id"]),
        reason=error[:500],
        metadata={"migration_id": str(row["migration_id"])},
        commit=False,
    )
    conn.commit()


def _mark_success(
    conn: sqlite3.Connection,
    *,
    row: Mapping[str, Any],
    target_intent: Mapping[str, Any],
    capture_manifest: Mapping[str, Any],
    verification: Mapping[str, Any],
    retention_days: int,
) -> dict[str, Any]:
    now_dt = _utc()
    now = _iso(now_dt)
    retention_until = _iso(now_dt + timedelta(days=max(0, int(retention_days))))
    source_placement_id = str(row["source_placement_id"])
    target_placement_id = str(row["target_placement_id"])
    if target_placement_id and target_placement_id != source_placement_id:
        conn.execute(
            "UPDATE arclink_deployment_placements SET status = 'removed', removed_at = ? WHERE placement_id = ?",
            (now, source_placement_id),
        )
        conn.execute(
            "UPDATE arclink_deployment_placements SET status = 'active', removed_at = '' WHERE placement_id = ?",
            (target_placement_id,),
        )
        conn.execute(
            "UPDATE arclink_fleet_hosts SET observed_load = MAX(0, observed_load - 1), updated_at = ? WHERE host_id = ?",
            (now, str(row["source_host_id"])),
        )
        conn.execute(
            "UPDATE arclink_fleet_hosts SET observed_load = observed_load + 1, updated_at = ? WHERE host_id = ?",
            (now, str(row["target_host_id"])),
        )

    deployment = _load_deployment(conn, str(row["deployment_id"]))
    metadata = json_loads_safe(str(deployment.get("metadata_json") or "{}"))
    metadata["state_roots"] = {
        str(key): str(value)
        for key, value in dict(target_intent.get("state_roots") or {}).items()
        if str(value or "").strip()
    }
    root = str(metadata["state_roots"].get("root") or row["target_state_root"])
    metadata["state_root_base"] = str(Path(root).parent) if root else ""
    metadata["pod_migration"] = {
        "migration_id": str(row["migration_id"]),
        "target_host_id": str(row["target_host_id"]),
        "completed_at": now,
    }
    conn.execute(
        "UPDATE arclink_deployments SET metadata_json = ?, updated_at = ? WHERE deployment_id = ?",
        (json.dumps(metadata, sort_keys=True), now, str(row["deployment_id"])),
    )
    conn.execute(
        """
        UPDATE arclink_pod_migrations
        SET status = 'succeeded',
            capture_manifest_json = ?,
            verification_json = ?,
            source_retention_until = ?,
            updated_at = ?,
            completed_at = ?
        WHERE migration_id = ?
        """,
        (
            _json_dumps(capture_manifest),
            _json_dumps(verification),
            retention_until,
            now,
            now,
            str(row["migration_id"]),
        ),
    )
    upsert_arclink_service_health(
        conn,
        deployment_id=str(row["deployment_id"]),
        service_name="pod-migration",
        status="healthy",
        detail={"migration_id": str(row["migration_id"]), "target_host_id": str(row["target_host_id"])},
    )
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=str(row["deployment_id"]),
        event_type="pod_migration_completed",
        metadata={"migration_id": str(row["migration_id"]), "target_placement_id": target_placement_id},
        commit=False,
    )
    append_arclink_audit(
        conn,
        action="pod_migration_completed",
        actor_id="system:pod_migration",
        target_kind="deployment",
        target_id=str(row["deployment_id"]),
        reason="Pod migration completed",
        metadata={
            "migration_id": str(row["migration_id"]),
            "source_placement_id": source_placement_id,
            "target_placement_id": target_placement_id,
        },
        commit=False,
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM arclink_pod_migrations WHERE migration_id = ?", (str(row["migration_id"]),)).fetchone())


def _result_from_row(row: Mapping[str, Any], *, idempotent_replay: bool = False, dry_run: bool | None = None) -> dict[str, Any]:
    result = {
        "migration_id": str(row["migration_id"]),
        "deployment_id": str(row["deployment_id"]),
        "status": str(row["status"]),
        "operation_kind": OPERATION_KIND,
        "operation_idempotency_key": str(row["operation_idempotency_key"]),
        "source_placement_id": str(row.get("source_placement_id") or ""),
        "target_placement_id": str(row.get("target_placement_id") or ""),
        "source_host_id": str(row.get("source_host_id") or ""),
        "target_host_id": str(row.get("target_host_id") or ""),
        "idempotent_replay": bool(idempotent_replay),
    }
    if dry_run is not None:
        result["dry_run"] = bool(dry_run)
    return result


def migrate_pod(
    conn: sqlite3.Connection,
    *,
    executor: ArcLinkExecutor,
    deployment_id: str,
    target_machine_id: str = "",
    migration_id: str = "",
    reason: str = "",
    dry_run: bool = False,
    env: Mapping[str, str] | None = None,
    verifier: Verifier | None = None,
    retention_days: int | None = None,
) -> dict[str, Any]:
    row = plan_pod_migration(
        conn,
        deployment_id=deployment_id,
        target_machine_id=target_machine_id,
        migration_id=migration_id,
        reason=reason,
        dry_run=dry_run,
    )
    operation_key = str(row["operation_idempotency_key"] or f"arclink:migration:{row['migration_id']}")
    intent = _operation_intent(row, dry_run=dry_run)
    replay = reserve_arclink_operation_idempotency(
        conn,
        operation_kind=OPERATION_KIND,
        idempotency_key=operation_key,
        intent=intent,
        status="running",
    )
    if bool(replay.get("replay")):
        refreshed = _migration_row(conn, str(row["migration_id"])) or row
        return _result_from_row(refreshed, idempotent_replay=True, dry_run=dry_run)
    if str(row["status"]) in {"succeeded", "failed", "rolled_back", "cancelled"}:
        return _result_from_row(row, idempotent_replay=True, dry_run=dry_run)

    if dry_run:
        target_host = _host(conn, str(row["target_host_id"]))
        target_intent = _render_target_intent(
            conn,
            deployment_id=str(row["deployment_id"]),
            target_host=target_host,
            fallback_base=str(Path(str(row["target_state_root"])).parent),
            env=env,
        )
        dry_step = executor.docker_compose_dry_run(
            DockerComposeApplyRequest(
                deployment_id=str(row["deployment_id"]),
                intent=target_intent,
                idempotency_key=f"{operation_key}:compose-target:dry-run",
            )
        )
        verification = {
            "healthy": True,
            "checked": "dry_run",
            "docker_dry_run": {
                "operation": dry_step.operation,
                "project_name": dry_step.project_name,
                "services": list(dry_step.services),
                "compose_file": dry_step.compose_file,
                "env_file": dry_step.env_file,
            },
        }
        now = utc_now_iso()
        conn.execute(
            """
            UPDATE arclink_pod_migrations
            SET verification_json = ?, updated_at = ?
            WHERE migration_id = ?
            """,
            (_json_dumps(verification), now, str(row["migration_id"])),
        )
        append_arclink_event(
            conn,
            subject_kind="deployment",
            subject_id=str(row["deployment_id"]),
            event_type="pod_migration_dry_run_planned",
            metadata={"migration_id": str(row["migration_id"]), "target_host_id": str(row["target_host_id"])},
            commit=False,
        )
        append_arclink_audit(
            conn,
            action="pod_migration_dry_run_planned",
            actor_id="system:pod_migration",
            target_kind="deployment",
            target_id=str(row["deployment_id"]),
            reason=str(reason or "operator requested Pod migration dry run"),
            metadata={"migration_id": str(row["migration_id"]), "target_host_id": str(row["target_host_id"])},
            commit=False,
        )
        conn.commit()
        refreshed = _migration_row(conn, str(row["migration_id"])) or row
        result = _result_from_row(refreshed, dry_run=True)
        result["docker_dry_run"] = verification["docker_dry_run"]
        complete_arclink_operation_idempotency(
            conn,
            operation_kind=OPERATION_KIND,
            idempotency_key=operation_key,
            intent=intent,
            provider_refs={"target_host_id": str(row["target_host_id"]), "dry_run": True},
            result=result,
        )
        return result

    conn.execute(
        "UPDATE arclink_pod_migrations SET status = 'running', updated_at = ? WHERE migration_id = ?",
        (utc_now_iso(), str(row["migration_id"])),
    )
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=str(row["deployment_id"]),
        event_type="pod_migration_started",
        metadata={"migration_id": str(row["migration_id"]), "target_host_id": str(row["target_host_id"])},
        commit=False,
    )
    append_arclink_audit(
        conn,
        action="pod_migration_started",
        actor_id="system:pod_migration",
        target_kind="deployment",
        target_id=str(row["deployment_id"]),
        reason=str(reason or "operator requested Pod migration"),
        metadata={"migration_id": str(row["migration_id"]), "target_host_id": str(row["target_host_id"])},
        commit=False,
    )
    conn.commit()

    capture_manifest: dict[str, Any] = {}
    source_stopped = False
    target_intent: dict[str, Any] | None = None
    try:
        deployment_id_for_lifecycle, env_file, compose_file = _deployment_lifecycle_files(row)
        executor.docker_compose_lifecycle(
            DockerComposeLifecycleRequest(
                deployment_id=deployment_id_for_lifecycle,
                action="stop",
                env_file=env_file,
                compose_file=compose_file,
                idempotency_key=f"{operation_key}:stop-source",
            )
        )
        source_stopped = True

        capture_manifest = _copy_capture(Path(str(row["source_state_root"])), Path(str(row["capture_dir"])))
        conn.execute(
            "UPDATE arclink_pod_migrations SET capture_manifest_json = ?, updated_at = ? WHERE migration_id = ?",
            (_json_dumps(capture_manifest), utc_now_iso(), str(row["migration_id"])),
        )
        conn.commit()

        target_host = _host(conn, str(row["target_host_id"]))
        target_intent = _render_target_intent(
            conn,
            deployment_id=str(row["deployment_id"]),
            target_host=target_host,
            fallback_base=str(Path(str(row["target_state_root"])).parent),
            env=env,
        )
        _materialize_capture(Path(str(row["capture_dir"])), Path(str(target_intent["state_roots"]["root"])))
        docker_result = executor.docker_compose_apply(
            DockerComposeApplyRequest(
                deployment_id=str(row["deployment_id"]),
                intent=target_intent,
                idempotency_key=f"{operation_key}:compose-target",
            )
        )
        verification = _normalize_verification((verifier or _default_verifier)(conn, row, target_intent))
        verification["docker_status"] = docker_result.status
        if not bool(verification.get("healthy")):
            error = "ArcLink Pod migration verification failed"
            lifecycle_metadata = _rollback_lifecycle(
                executor=executor,
                row=row,
                operation_key=operation_key,
                target_intent=target_intent,
                source_stopped=source_stopped,
            )
            _mark_rollback(conn, row=row, verification=verification, error=error, lifecycle_metadata=lifecycle_metadata)
            failed_row = _migration_row(conn, str(row["migration_id"])) or row
            fail_arclink_operation_idempotency(
                conn,
                operation_kind=OPERATION_KIND,
                idempotency_key=operation_key,
                intent=intent,
                error=error,
                result=_result_from_row(failed_row),
            )
            return _result_from_row(failed_row)

        days = retention_days
        if days is None:
            days = int(str((env or os.environ).get("ARCLINK_MIGRATION_GC_DAYS") or DEFAULT_GC_DAYS))
        succeeded = _mark_success(
            conn,
            row=row,
            target_intent=target_intent,
            capture_manifest=capture_manifest,
            verification=verification,
            retention_days=days,
        )
        result = _result_from_row(succeeded)
        complete_arclink_operation_idempotency(
            conn,
            operation_kind=OPERATION_KIND,
            idempotency_key=operation_key,
            intent=intent,
            provider_refs={"target_host_id": str(row["target_host_id"])},
            result=result,
        )
        return result
    except Exception as exc:
        error = str(exc)[:1000]
        current = _migration_row(conn, str(row["migration_id"])) or row
        if str(current.get("status") or "") not in {"rolled_back", "succeeded"}:
            lifecycle_metadata = _rollback_lifecycle(
                executor=executor,
                row=row,
                operation_key=operation_key,
                target_intent=target_intent,
                source_stopped=source_stopped,
            )
            _mark_rollback(
                conn,
                row=row,
                verification={"healthy": False, "error": error},
                error=error,
                lifecycle_metadata=lifecycle_metadata,
            )
            current = _migration_row(conn, str(row["migration_id"])) or current
        fail_arclink_operation_idempotency(
            conn,
            operation_kind=OPERATION_KIND,
            idempotency_key=operation_key,
            intent=intent,
            error=error,
            result=_result_from_row(current),
        )
        raise


def garbage_collect_pod_migrations(
    conn: sqlite3.Connection,
    *,
    retention_days: int | None = None,
    now: datetime | None = None,
    remove_artifacts: bool = True,
) -> list[dict[str, Any]]:
    cutoff = _utc(now)
    if retention_days is not None:
        cutoff = cutoff - timedelta(days=max(0, int(retention_days)))
    rows = conn.execute(
        """
        SELECT *
        FROM arclink_pod_migrations
        WHERE status = 'succeeded'
          AND source_garbage_collected_at = ''
          AND source_retention_until != ''
        ORDER BY source_retention_until ASC, migration_id ASC
        """
    ).fetchall()
    collected: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        retention_until = _parse_iso(str(row.get("source_retention_until") or ""))
        if retention_until is None or retention_until > cutoff:
            continue
        capture_dir = Path(str(row.get("capture_dir") or ""))
        removed = False
        if remove_artifacts and capture_dir.exists():
            shutil.rmtree(capture_dir)
            removed = True
        collected_at = utc_now_iso()
        conn.execute(
            "UPDATE arclink_pod_migrations SET source_garbage_collected_at = ?, updated_at = ? WHERE migration_id = ?",
            (collected_at, collected_at, str(row["migration_id"])),
        )
        append_arclink_event(
            conn,
            subject_kind="deployment",
            subject_id=str(row["deployment_id"]),
            event_type="pod_migration_gc_completed",
            metadata={"migration_id": str(row["migration_id"]), "removed_artifacts": removed},
            commit=False,
        )
        collected.append({"migration_id": str(row["migration_id"]), "removed_artifacts": removed})
    if collected:
        conn.commit()
    return collected
