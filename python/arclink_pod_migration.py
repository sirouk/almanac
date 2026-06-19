#!/usr/bin/env python3
"""ArcLink 1:1 Pod migration orchestration.

The module keeps migration state in the control plane while routing host
mutation through the existing executor abstraction. File capture is deliberately
small and injectable so tests can use temporary state roots without touching
private live state.
"""
from __future__ import annotations

import hashlib
import fcntl
import json
import os
import secrets
import shutil
import sqlite3
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from arclink_boundary import json_dumps_safe, json_loads_safe, reject_secret_material
from arclink_control import (
    append_arclink_audit,
    append_arclink_event,
    complete_arclink_operation_idempotency,
    ensure_llm_router_key,
    fail_arclink_operation_idempotency,
    generate_llm_router_raw_key,
    reserve_arclink_operation_idempotency,
    utc_now_iso,
)
from arclink_executor import (
    _SUBPROCESS_LONG_TIMEOUT as _EXECUTOR_LONG_OP_TIMEOUT_SECONDS,
    ArcLinkExecutor,
    DockerComposeApplyRequest,
    DockerComposeLifecycleRequest,
)
from arclink_provisioning import render_arclink_provisioning_intent, render_arclink_state_roots
from arclink_secrets_regex import redact_then_truncate


OPERATION_KIND = "pod_migration"
DEFAULT_GC_DAYS = 7
# A live migration that has sat in 'running' longer than this lease has been
# abandoned by a crashed worker (the row is non-terminal so re-runs are otherwise
# refused). Recovery rolls it back to a terminal failed state and releases the
# idempotency row so the deployment can be migrated again.
MIGRATION_RUNNING_LEASE_SECONDS_ENV = "ARCLINK_POD_MIGRATION_RUNNING_LEASE_SECONDS"
# Round 3 / FIX 2 (lease > max-uninterrupted-op duration). The heartbeat
# (_beat_or_abort) only fires AT STEP BOUNDARIES, never DURING a single executor
# call. A single migration step -- most importantly docker_compose_apply -- can
# legitimately run for far longer than one _SUBPROCESS_LONG_TIMEOUT: the SSH
# Docker runner chains mkdir (short) + rsync of the whole deployment root
# (_SUBPROCESS_LONG_TIMEOUT) + bind prepare + `docker compose up` (a SECOND
# _SUBPROCESS_LONG_TIMEOUT) + remote secret cleanup, all without a heartbeat in
# between. If the stale/recovery lease were shorter than that worst case, a
# genuinely-alive worker sitting inside one apply could be declared stale and
# recovered while it is still applying -- exactly the Docker-flapping window this
# round closes (mirrors the LLM reaper TTL > read_timeout fix).
#
# So the FLOOR for the lease is: the longest a single migration step can run
# WITHOUT beating the heartbeat. We model the apply as up to TWO back-to-back
# long executor ops (rsync + compose up) plus headroom for the short ops and the
# migration-capture helper (its own ARCLINK_MIGRATION_CAPTURE_HELPER_TIMEOUT_SECONDS,
# default 300). The default lease (1h) already exceeds this floor with margin;
# the floor is enforced so an operator who SHORTENS the lease via env can never
# push it below the point where an in-flight apply would be falsely recovered.
# The relationship that must always hold:
#     lease_seconds >= (2 * _SUBPROCESS_LONG_TIMEOUT) + margin
# i.e. a worker actively inside ONE migration step can never cross the lease
# before that step returns and the next heartbeat fires.
_MAX_UNINTERRUPTED_MIGRATION_OP_SECONDS = 2 * int(_EXECUTOR_LONG_OP_TIMEOUT_SECONDS)
_MIGRATION_LEASE_SAFETY_MARGIN_SECONDS = 600
MINIMUM_MIGRATION_RUNNING_LEASE_SECONDS = (
    _MAX_UNINTERRUPTED_MIGRATION_OP_SECONDS + _MIGRATION_LEASE_SAFETY_MARGIN_SECONDS
)
# Default lease stays generous and is clamped up to the floor above so the default
# is always heartbeat-safe even if the executor timeout grows.
DEFAULT_MIGRATION_RUNNING_LEASE_SECONDS = max(3600, MINIMUM_MIGRATION_RUNNING_LEASE_SECONDS)
ROOT_CAPTURE_OPT_IN_ENV = "ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE"
MIGRATION_CAPTURE_HELPER_URL_ENV = "ARCLINK_MIGRATION_CAPTURE_HELPER_URL"
MIGRATION_CAPTURE_HELPER_TOKEN_ENV = "ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN"
MIGRATION_CAPTURE_HELPER_TOKEN_HEADER = "X-ArcLink-Migration-Capture-Helper-Token"
TERMINAL_MIGRATION_STATUSES = {"succeeded", "failed", "rolled_back", "cancelled"}
ACTIVE_MIGRATION_STATUSES = {"planned", "running"}


class ArcLinkPodMigrationError(ValueError):
    pass


Verifier = Callable[[sqlite3.Connection, Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any] | bool]


def _migration_id() -> str:
    return f"mig_{secrets.token_hex(12)}"


# C2: per-attempt ownership nonce. The token lives inside rollback_metadata_json
# under this key so no schema change is needed. A worker "owns" a running
# migration only while the DB row carries the token it stamped. The recovery path
# ROTATES the token to a fresh value in the same atomic CAS that claims a stale
# row, which instantly revokes the original (possibly-still-alive) live worker's
# ownership: that worker's _mark_success / _mark_rollback / heartbeat all guard on
# the token and so begin to fail (rowcount 0 == ownership lost) instead of
# continuing to drive Docker lifecycle work or land a terminal status under a row
# another worker is recovering.
# NOTE: the key deliberately avoids the substrings "token"/"key"/"secret" because
# the boundary secret-material guard (path_requires_secret_ref) would otherwise
# reject this non-secret ownership nonce as plaintext secret material. "_owner_nonce"
# is an opaque per-attempt id, not a credential.
OWNER_TOKEN_KEY = "_owner_nonce"
# JSON path of the nonce inside rollback_metadata_json, used by the SQL guards.
_OWNER_TOKEN_JSON_PATH = f"$.{OWNER_TOKEN_KEY}"


def _owner_token() -> str:
    return f"own_{secrets.token_hex(16)}"


def _row_owner_token(row: Mapping[str, Any]) -> str:
    """Read the ownership token a worker holds for ``row`` (empty if none)."""
    meta = json_loads_safe(str(row.get("rollback_metadata_json") or "{}"))
    if isinstance(meta, Mapping):
        return str(meta.get(OWNER_TOKEN_KEY) or "")
    return ""


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


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _require_root_capture_opt_in(env: Mapping[str, str] | None) -> None:
    source = env or os.environ
    if _truthy(source.get(ROOT_CAPTURE_OPT_IN_ENV)):
        return
    raise ArcLinkPodMigrationError(
        "ArcLink Pod migration non-dry-run capture is disabled unless "
        f"{ROOT_CAPTURE_OPT_IN_ENV}=1 is set for an operator-controlled "
        "migration window; run a dry run first or split capture behind a "
        "dedicated helper"
    )


def _migration_capture_helper_config(
    env: Mapping[str, str] | None,
    *,
    require_for_docker: bool = False,
) -> tuple[str, str] | None:
    source = env or os.environ
    url = str(source.get(MIGRATION_CAPTURE_HELPER_URL_ENV) or "").strip().rstrip("/")
    token = str(source.get(MIGRATION_CAPTURE_HELPER_TOKEN_ENV) or "").strip()
    if url or token:
        if not url or not token:
            raise ArcLinkPodMigrationError(
                "ArcLink Pod migration capture helper requires both "
                f"{MIGRATION_CAPTURE_HELPER_URL_ENV} and {MIGRATION_CAPTURE_HELPER_TOKEN_ENV}"
            )
        return url, token
    if require_for_docker and _truthy(source.get("ARCLINK_DOCKER_MODE")):
        raise ArcLinkPodMigrationError(
            "ArcLink Docker-mode Pod migration capture requires "
            f"{MIGRATION_CAPTURE_HELPER_URL_ENV} and {MIGRATION_CAPTURE_HELPER_TOKEN_ENV}"
        )
    return None


def _absolute_path(value: str, *, label: str) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise ArcLinkPodMigrationError(f"ArcLink Pod migration {label} is required")
    path = Path(raw)
    if not path.is_absolute():
        raise ArcLinkPodMigrationError(f"ArcLink Pod migration {label} must be absolute")
    resolved = path.resolve(strict=False)
    if str(resolved) == "/":
        raise ArcLinkPodMigrationError(f"ArcLink Pod migration {label} must not be filesystem root")
    return resolved


def _expected_deployment_root_name(deployment: Mapping[str, Any]) -> str:
    roots = render_arclink_state_roots(
        deployment_id=str(deployment.get("deployment_id") or ""),
        prefix=str(deployment.get("prefix") or ""),
        state_root_base="/arcdata/deployments",
    )
    return Path(str(roots["root"])).name


def _validate_capture_paths(conn: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    deployment = _load_deployment(conn, str(row["deployment_id"]))
    expected_root_name = _expected_deployment_root_name(deployment)
    source_root = _absolute_path(str(row.get("source_state_root") or ""), label="source state root")
    target_root = _absolute_path(str(row.get("target_state_root") or ""), label="target state root")
    capture_dir = _absolute_path(str(row.get("capture_dir") or ""), label="capture directory")
    if source_root.name != expected_root_name:
        raise ArcLinkPodMigrationError("ArcLink Pod migration source root must be deployment-scoped")
    if target_root.name != expected_root_name:
        raise ArcLinkPodMigrationError("ArcLink Pod migration target root must be deployment-scoped")
    if capture_dir.name != str(row.get("migration_id") or ""):
        raise ArcLinkPodMigrationError("ArcLink Pod migration capture directory must end with the migration id")
    if capture_dir.parent.name != ".migrations" or capture_dir.parent.parent != target_root.parent:
        raise ArcLinkPodMigrationError("ArcLink Pod migration capture directory must stay under the target state-root base")
    try:
        capture_dir.relative_to(source_root)
    except ValueError:
        pass
    else:
        raise ArcLinkPodMigrationError("ArcLink Pod migration capture directory must not be inside the source root")
    try:
        capture_dir.relative_to(target_root)
    except ValueError:
        pass
    else:
        raise ArcLinkPodMigrationError("ArcLink Pod migration capture directory must not be inside the target root")


def _begin_immediate_if_needed(conn: sqlite3.Connection) -> bool:
    if conn.in_transaction:
        return False
    conn.execute("BEGIN IMMEDIATE")
    return True


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


def _require_target_host_available(host: Mapping[str, Any]) -> None:
    if str(host.get("status") or "") != "active" or int(host.get("drain") or 0):
        raise ArcLinkPodMigrationError("ArcLink Pod migration target host is not available")


def _row_is_dry_run(row: Mapping[str, Any]) -> bool:
    metadata = json_loads_safe(str(row.get("target_host_metadata_json") or "{}"))
    return bool(metadata.get("dry_run"))


def _active_live_migration(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    exclude_migration_id: str = "",
) -> dict[str, Any] | None:
    rows = conn.execute(
        """
        SELECT *
        FROM arclink_pod_migrations
        WHERE deployment_id = ?
          AND status IN ('planned', 'running')
        ORDER BY updated_at DESC, migration_id DESC
        """,
        (deployment_id,),
    ).fetchall()
    for raw in rows:
        row = dict(raw)
        if str(row.get("migration_id") or "") == str(exclude_migration_id or ""):
            continue
        if _row_is_dry_run(row):
            continue
        return row
    return None


def _stranded_running_migrations(conn: sqlite3.Connection, *, deployment_id: str) -> list[dict[str, Any]]:
    """Return ALL non-dry-run migrations of this deployment still stuck in 'running'.

    Lease-expiry filtering is left to _recover_stale_running_migration; this only
    surfaces the candidate rows. M4: a crashed worker can strand more than one row
    over time, so recovery loops over every stale 'running' row, not just the
    oldest one.
    """
    clean = str(deployment_id or "").strip()
    if not clean:
        return []
    rows = conn.execute(
        """
        SELECT *
        FROM arclink_pod_migrations
        WHERE deployment_id = ?
          AND status = 'running'
        ORDER BY updated_at ASC, migration_id ASC
        """,
        (clean,),
    ).fetchall()
    return [dict(raw) for raw in rows if not _row_is_dry_run(dict(raw))]


def _stranded_running_migration(conn: sqlite3.Connection, *, deployment_id: str) -> dict[str, Any] | None:
    """Return the oldest non-dry-run migration of this deployment stuck in 'running'.

    Retained for callers/tests that only need a single candidate; recovery in
    migrate_pod loops over _stranded_running_migrations.
    """
    candidates = _stranded_running_migrations(conn, deployment_id=deployment_id)
    return candidates[0] if candidates else None


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

    started_txn = _begin_immediate_if_needed(conn)
    try:
        existing = _migration_row(conn, clean_migration)
        if existing is not None:
            if str(existing["deployment_id"]) != clean_deployment:
                raise ArcLinkPodMigrationError("ArcLink Pod migration id is already bound to another deployment")
            clean_target = str(target_machine_id or "").strip()
            existing_target = str(existing.get("target_machine_id") or "").strip()
            if clean_target and existing_target and clean_target != existing_target:
                raise ArcLinkPodMigrationError("ArcLink Pod migration id is already bound to another target")
            if not dry_run and str(existing.get("status") or "") in ACTIVE_MIGRATION_STATUSES:
                blocker = _active_live_migration(conn, deployment_id=clean_deployment, exclude_migration_id=clean_migration)
                if blocker is not None:
                    raise ArcLinkPodMigrationError(
                        "ArcLink Pod migration already has an active migration for this deployment: "
                        f"{blocker.get('migration_id')}"
                    )
                _require_target_host_available(_host(conn, str(existing["target_host_id"])))
            if started_txn:
                conn.commit()
            return existing

        if not dry_run:
            blocker = _active_live_migration(conn, deployment_id=clean_deployment)
            if blocker is not None:
                raise ArcLinkPodMigrationError(
                    "ArcLink Pod migration already has an active migration for this deployment: "
                    f"{blocker.get('migration_id')}"
                )

        deployment = _load_deployment(conn, clean_deployment)
        source_placement = _active_placement(conn, clean_deployment)
        source_host = _host(conn, str(source_placement["host_id"]))
        source_roots, source_base = _metadata_roots(deployment, source_host)
        target_host, resolved_target = _resolve_target_host(
            conn,
            source_host_id=str(source_placement["host_id"]),
            target_machine_id=target_machine_id,
        )
        _require_target_host_available(target_host)
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
    except Exception:
        if started_txn and conn.in_transaction:
            conn.rollback()
        raise


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
        rel = path.relative_to(staged_root).as_posix()
        if path.is_symlink():
            stat = path.lstat()
            files.append(
                {
                    "path": rel,
                    "boundary": _boundary_for(rel),
                    "type": "symlink",
                    "target": os.readlink(path),
                    "mode": oct(stat.st_mode & 0o777),
                }
            )
            continue
        if not path.is_file():
            continue
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


def _recover_orphan_prev_backup(target_root: Path) -> bool:
    """M3: restore a same-root materialize that crashed between its two os.replace calls.

    The same-root path does ``os.replace(target_root, backup_root)`` then
    ``os.replace(tmp_root, target_root)``. A crash between the two leaves
    target_root MISSING and an orphan ``.{name}.arclink-prev-<pid>`` backup that
    nothing garbage-collects, so the deployment's live data is sitting in a hidden
    sibling. On the next materialize, if target_root is gone, scan the parent for
    that backup and move it back into place. Returns True when a backup was
    restored.
    """
    if target_root.exists() or target_root.is_symlink():
        return False
    parent = target_root.parent
    if not parent.exists():
        return False
    prefix = f".{target_root.name}.arclink-prev-"
    backups = sorted(p for p in parent.iterdir() if p.name.startswith(prefix))
    if not backups:
        return False
    # Restore the first backup; any extras are stale leftovers and are removed.
    restore = backups[0]
    os.replace(restore, target_root)
    for extra in backups[1:]:
        if extra.is_symlink() or extra.is_file():
            extra.unlink()
        else:
            shutil.rmtree(extra, ignore_errors=True)
    return True


def _materialize_capture(capture_dir: Path, target_root: Path, *, source_root: Path | None = None) -> None:
    staged_root = capture_dir / "source-root"
    target_root.parent.mkdir(parents=True, exist_ok=True)

    # M3: if a previous same-root materialize crashed between its two os.replace
    # calls, target_root is missing and the live data is in an orphan
    # .arclink-prev-* backup. Restore it before deciding how to materialize so we
    # never treat a recoverable crash as "target absent" and lose the backup.
    _recover_orphan_prev_backup(target_root)

    # H4: when the migration target root IS the live source root (a "current"
    # in-place migration), the data already lives at target_root. The old
    # rmtree-then-copytree sequence DESTROYED the live data first and would lose
    # everything if the copy then failed. The staged capture is a faithful copy
    # of that same source, so re-materialize ATOMICALLY: build the new tree in a
    # sibling temp dir and os.replace it into place. A crash mid-copy leaves the
    # original target_root untouched.
    same_root = source_root is not None and _same_path(source_root, target_root)
    if same_root:
        if not staged_root.exists():
            # Nothing was captured and the live data is already in place -- a
            # destructive rebuild would be pure data loss. Leave target_root as-is.
            target_root.mkdir(parents=True, exist_ok=True)
            return
        tmp_root = target_root.parent / f".{target_root.name}.arclink-materialize-{os.getpid()}"
        if tmp_root.is_symlink() or tmp_root.is_file():
            tmp_root.unlink()
        elif tmp_root.exists():
            shutil.rmtree(tmp_root)
        shutil.copytree(staged_root, tmp_root, symlinks=True)
        backup_root = target_root.parent / f".{target_root.name}.arclink-prev-{os.getpid()}"
        if backup_root.exists() or backup_root.is_symlink():
            if backup_root.is_symlink() or backup_root.is_file():
                backup_root.unlink()
            else:
                shutil.rmtree(backup_root)
        target_existed = target_root.exists() or target_root.is_symlink()
        if target_existed:
            os.replace(target_root, backup_root)
        try:
            os.replace(tmp_root, target_root)
        except Exception:
            # Restore the original tree if the swap-in failed.
            if target_existed and not (target_root.exists() or target_root.is_symlink()):
                os.replace(backup_root, target_root)
            raise
        if target_existed:
            shutil.rmtree(backup_root, ignore_errors=True)
        return

    if target_root.is_symlink() or target_root.is_file():
        target_root.unlink()
    elif target_root.exists():
        shutil.rmtree(target_root)
    if staged_root.exists():
        shutil.copytree(staged_root, target_root, symlinks=True)
    else:
        target_root.mkdir(parents=True, exist_ok=True)


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve(strict=False) == right.resolve(strict=False)
    except OSError:
        return str(left) == str(right)


def _migration_capture_helper_payload(conn: sqlite3.Connection, row: Mapping[str, Any]) -> dict[str, Any]:
    deployment = _load_deployment(conn, str(row["deployment_id"]))
    return {
        "deployment_id": str(row["deployment_id"]),
        "prefix": str(deployment.get("prefix") or ""),
        "migration_id": str(row["migration_id"]),
        "source_state_root": str(row["source_state_root"]),
        "target_state_root": str(row["target_state_root"]),
        "capture_dir": str(row["capture_dir"]),
    }


def _run_migration_capture_helper(
    operation: str,
    *,
    conn: sqlite3.Connection,
    row: Mapping[str, Any],
    env: Mapping[str, str] | None,
) -> dict[str, Any]:
    config = _migration_capture_helper_config(env, require_for_docker=True)
    if config is None:
        raise ArcLinkPodMigrationError("ArcLink Pod migration capture helper is not configured")
    url, token = config
    source = env or os.environ
    try:
        timeout = int(str(source.get("ARCLINK_MIGRATION_CAPTURE_HELPER_TIMEOUT_SECONDS") or "300").strip())
    except ValueError:
        timeout = 300
    body = _migration_capture_helper_payload(conn, row)
    body["operation"] = str(operation or "").strip()
    request = urllib.request.Request(
        f"{url}/v1/migration-capture",
        data=json.dumps(body, sort_keys=True).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            MIGRATION_CAPTURE_HELPER_TOKEN_HEADER: token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=max(5, timeout)) as response:  # noqa: S310 - internal helper URL
            payload = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8") or "{}")
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            payload = {}
        error = str(payload.get("error") or exc.reason or "migration capture helper rejected request")
        raise ArcLinkPodMigrationError(redact_then_truncate(error, limit=240, tail=True)) from exc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ArcLinkPodMigrationError(
            "migration capture helper request failed: "
            f"{redact_then_truncate(str(exc), limit=240, tail=True)}"
        ) from exc
    if not isinstance(payload, Mapping) or payload.get("ok") is not True:
        error = (
            str(payload.get("error") or "migration capture helper rejected request")
            if isinstance(payload, Mapping)
            else "migration capture helper rejected request"
        )
        raise ArcLinkPodMigrationError(redact_then_truncate(error, limit=240, tail=True))
    result = payload.get("result") if isinstance(payload, Mapping) else {}
    return dict(result) if isinstance(result, Mapping) else {}


def _capture_files(
    conn: sqlite3.Connection,
    *,
    row: Mapping[str, Any],
    env: Mapping[str, str] | None,
) -> dict[str, Any]:
    if _migration_capture_helper_config(env, require_for_docker=True):
        return _run_migration_capture_helper("capture", conn=conn, row=row, env=env)
    return _copy_capture(Path(str(row["source_state_root"])), Path(str(row["capture_dir"])))


def _materialize_files(
    conn: sqlite3.Connection,
    *,
    row: Mapping[str, Any],
    target_root: str,
    env: Mapping[str, str] | None,
) -> None:
    if _migration_capture_helper_config(env, require_for_docker=True):
        _run_migration_capture_helper("materialize", conn=conn, row=row, env=env)
        return
    _materialize_capture(
        Path(str(row["capture_dir"])),
        Path(target_root),
        source_root=Path(str(row["source_state_root"])) if str(row.get("source_state_root") or "").strip() else None,
    )


def _default_verifier(
    conn: sqlite3.Connection,
    migration: Mapping[str, Any],
    intent: Mapping[str, Any],
) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT service_name, status, checked_at FROM arclink_service_health WHERE deployment_id = ?",
        (str(migration["deployment_id"]),),
    ).fetchall()
    checked_after = _parse_iso(str(migration.get("updated_at") or migration.get("created_at") or ""))
    blockers: dict[str, str] = {}
    fresh_services: list[str] = []
    for row in rows:
        service_name = str(row["service_name"])
        status = str(row["status"])
        checked_at = _parse_iso(str(row["checked_at"] or ""))
        if checked_at is None or (checked_after is not None and checked_at < checked_after):
            blockers[service_name] = "stale"
            continue
        fresh_services.append(service_name)
        if status in {"failed", "unhealthy", "missing"}:
            blockers[service_name] = status
    if not rows:
        blockers["service_health"] = "missing"
    return {
        "healthy": not blockers,
        "blockers": blockers,
        "checked": "service_health",
        "fresh_service_count": len(fresh_services),
    }


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


def _router_secret_store_dir(env: Mapping[str, str] | None, deployment_id: str) -> Path | None:
    raw = str((env or os.environ).get("ARCLINK_SECRET_STORE_DIR") or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve() / str(deployment_id)


def _router_secret_path(secret_store_dir: Path, secret_ref: str) -> Path:
    return secret_store_dir / f"{hashlib.sha256(secret_ref.encode('utf-8')).hexdigest()}.secret"


def _router_key_value(secret_store_dir: Path, secret_ref: str) -> str:
    path = _router_secret_path(secret_store_dir, secret_ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    lock_path = path.with_name(f".{path.name}.lock")
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    tmp_name = ""
    try:
        with os.fdopen(lock_fd, "w") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            if path.exists():
                return path.read_text(encoding="utf-8").strip()
            value = generate_llm_router_raw_key()
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                delete=False,
            ) as tmp:
                tmp_name = tmp.name
                tmp.write(value + "\n")
                tmp.flush()
                os.fsync(tmp.fileno())
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, path)
            return value
    except Exception:
        if tmp_name:
            try:
                Path(tmp_name).unlink()
            except OSError:
                pass
        raise


def _ensure_llm_router_key_for_intent(
    conn: sqlite3.Connection,
    *,
    deployment: Mapping[str, Any],
    intent: Mapping[str, Any],
    env: Mapping[str, str] | None,
) -> dict[str, Any] | None:
    secret_refs = intent.get("secret_refs") if isinstance(intent.get("secret_refs"), Mapping) else {}
    secret_ref = str(secret_refs.get("llm_router_api_key") or "").strip()
    if not secret_ref:
        return None
    deployment_id = str(deployment.get("deployment_id") or "").strip()
    user_id = str(deployment.get("user_id") or "").strip()
    if not deployment_id or not user_id:
        return None
    secret_store_dir = _router_secret_store_dir(env, deployment_id)
    if secret_store_dir is None:
        return None
    raw_key = _router_key_value(secret_store_dir, secret_ref)
    model = str(
        (env or os.environ).get("ARCLINK_LLM_ROUTER_DEFAULT_MODEL")
        or (env or os.environ).get("ARCLINK_CHUTES_DEFAULT_MODEL")
        or ""
    ).strip()
    return ensure_llm_router_key(
        conn,
        deployment_id=deployment_id,
        user_id=user_id,
        secret_ref=secret_ref,
        raw_key=raw_key,
        allowed_models=[model] if model else None,
        metadata={"source": "pod_migration"},
    )


def _mark_rollback(
    conn: sqlite3.Connection,
    *,
    row: Mapping[str, Any],
    verification: Mapping[str, Any],
    error: str,
    lifecycle_metadata: Mapping[str, Any] | None = None,
) -> bool:
    """Roll a 'running' migration back to terminal 'rolled_back'.

    C1/C2 fencing: the migration-row flip is conditional on ``status = 'running'``
    AND the caller's ownership token, and is claimed BEFORE any placement mutation
    or capture cleanup. If the fenced claim does not match exactly one row --
    because another worker already drove this migration to a terminal state
    (succeeded / failed / rolled_back), a slow-but-alive run committed
    ``succeeded`` first, or a recovery rotated the ownership token out from under
    this worker -- this is a no-op: no placements are touched, no capture is
    removed, and the live serving target is never clobbered. Returns True when the
    rollback was applied, False on no-op.

    Atomicity (C2): the claim, EVERY placement mutation, and the final terminal
    UPDATE all run inside ONE ``BEGIN IMMEDIATE`` transaction. The claim is NOT
    committed up front (an earlier version did, which let a concurrent
    ``succeeded`` land between the claim and the placement mutations and produce a
    half-rolled-back state). Holding the write lock through the DB work means a
    success can never interleave, and the final guarded UPDATE re-asserts the claim
    so a lost claim aborts the whole rollback rather than half-applying it.

    FIX 3 (write-lock vs filesystem cleanup): the SLOW capture-dir ``rmtree`` is
    NO LONGER performed under that write lock. The DB claim + placement mutation +
    terminal UPDATE COMMIT FIRST (a short writer lock that no longer contends with
    place_deployment across a multi-second/minute filesystem delete); only then is
    the capture rmtree run, OUTSIDE the lock, with its actual result recorded in a
    short follow-up UPDATE. The row is already terminal and ownership-fenced by
    then, so the deferred cleanup cannot race a concurrent terminal transition.
    """
    now = utc_now_iso()
    owner_token = _row_owner_token(row)
    # Fence first, inside a single immediate transaction that we hold through the
    # placement mutations: claim the migration row only while it is still 'running'
    # and still owned by this worker. The final row UPDATE repeats this guard, but
    # claiming the status flip up front under a held write lock means a loser of the
    # race never mutates placements or deletes a capture that a concurrent terminal
    # transition is relying on.
    own_txn = _begin_immediate_if_needed(conn)
    try:
        claimed = conn.execute(
            "UPDATE arclink_pod_migrations SET updated_at = ? "
            "WHERE migration_id = ? AND status = 'running' "
            "AND COALESCE(json_extract(rollback_metadata_json, ?), '') = ?",
            (now, str(row["migration_id"]), _OWNER_TOKEN_JSON_PATH, owner_token),
        )
        if claimed.rowcount != 1:
            # The row is no longer 'running' (terminal already, or another worker
            # won the recovery race / rotated the token). Do nothing destructive.
            if own_txn and conn.in_transaction:
                conn.rollback()
            return False
        # NOTE: intentionally NOT committing here -- the write lock is held through
        # every placement mutation below and the final terminal UPDATE.
    except Exception:
        if own_txn and conn.in_transaction:
            conn.rollback()
        raise
    rollback_metadata = json_loads_safe(str(row.get("rollback_metadata_json") or "{}"))
    if not isinstance(rollback_metadata, Mapping):
        rollback_metadata = {}
    # FIX 3: plan the capture cleanup (fast, stat-only) under the lock; the slow
    # rmtree is deferred until AFTER the terminal commit so the SQLite writer lock
    # is not held across the filesystem delete (which contends with place_deployment
    # and other writers). ``capture_path_to_remove`` is the directory to rmtree once
    # the row is committed terminal; ``capture_cleanup`` is the optimistic result we
    # record now and confirm/overwrite in a short follow-up UPDATE after the rmtree.
    capture_cleanup, capture_path_to_remove = _plan_rolled_back_capture_cleanup(row)
    rollback_payload = dict(rollback_metadata)
    rollback_payload.update(
        {
            "rolled_back_at": now,
            "source_placement_id": str(row["source_placement_id"]),
            "target_placement_id": str(row.get("target_placement_id") or ""),
            "lifecycle": dict(lifecycle_metadata or {}),
            "capture_cleanup": capture_cleanup,
        }
    )
    if str(row.get("target_placement_id") or "") and str(row["target_placement_id"]) != str(row["source_placement_id"]):
        conn.execute(
            "UPDATE arclink_deployment_placements SET status = 'removed', removed_at = ? WHERE placement_id = ?",
            (now, str(row["target_placement_id"])),
        )
    # H3: only re-mark the source placement ACTIVE if the source was actually
    # brought back healthy. The source was stopped before the target was verified;
    # if the rollback restart of the source FAILED, the source is NOT serving and
    # flipping its placement to active would advertise a dead pod as live. In that
    # case leave the placement removed, flag the migration for manual recovery, and
    # alert -- never silently claim the source is back.
    source_restart = (lifecycle_metadata or {}).get("source_restart") if isinstance(lifecycle_metadata, Mapping) else None
    source_restart_failed = bool(
        isinstance(source_restart, Mapping)
        and str(source_restart.get("status") or "").strip().lower() not in {"", "completed"}
    )
    rollback_payload["source_restart_verified"] = not source_restart_failed
    if source_restart_failed:
        rollback_payload["manual_recovery_required"] = True
        # H3 (round 2): in the LIVE flow the source placement is still 'active'
        # (it is never flipped off until success), so a guard like
        # "WHERE status != 'active'" would NO-OP and leave a dead source
        # advertised active. Act on the ACTUAL active source row: mark it removed
        # (not-serving) so nothing routes to a pod that is down. Re-activation only
        # happens on a verified restart in the else branch below.
        conn.execute(
            "UPDATE arclink_deployment_placements SET status = 'removed', removed_at = ? WHERE placement_id = ?",
            (now, str(row["source_placement_id"])),
        )
        append_arclink_event(
            conn,
            subject_kind="deployment",
            subject_id=str(row["deployment_id"]),
            event_type="pod_migration_rollback_source_restart_failed",
            metadata={
                "migration_id": str(row["migration_id"]),
                "source_placement_id": str(row["source_placement_id"]),
                "source_restart": dict(source_restart) if isinstance(source_restart, Mapping) else {},
            },
            commit=False,
        )
        append_arclink_audit(
            conn,
            action="pod_migration_rollback_source_restart_failed",
            actor_id="system:pod_migration",
            target_kind="deployment",
            target_id=str(row["deployment_id"]),
            reason="source restart did not verify healthy during rollback; manual recovery required",
            metadata={"migration_id": str(row["migration_id"]), "source_placement_id": str(row["source_placement_id"])},
            commit=False,
        )
    else:
        conn.execute(
            "UPDATE arclink_deployment_placements SET status = 'active', removed_at = '' WHERE placement_id = ?",
            (str(row["source_placement_id"]),),
        )
    # Preserve the ownership token in the terminal payload so the row's recorded
    # owner stays consistent (the row is terminal now, so it is no longer load-
    # bearing, but keeping it avoids surprising a reader of rollback_metadata_json).
    if owner_token:
        rollback_payload[OWNER_TOKEN_KEY] = owner_token
    finalize = conn.execute(
        """
        UPDATE arclink_pod_migrations
        SET status = 'rolled_back',
            verification_json = ?,
            rollback_metadata_json = ?,
            error = ?,
            source_garbage_collected_at = ?,
            updated_at = ?,
            completed_at = ?
        WHERE migration_id = ? AND status = 'running'
          AND COALESCE(json_extract(rollback_metadata_json, ?), '') = ?
        """,
        (
            _json_dumps(verification),
            _json_dumps(rollback_payload),
            error[:1000],
            # FIX 3: only stamp source_garbage_collected_at under the lock when the
            # capture is already gone (missing, nothing to remove). When we still
            # have to rmtree (capture_path_to_remove is set) leave it blank here and
            # stamp it in the post-commit follow-up UPDATE once the rmtree succeeds,
            # so a deferred-rmtree failure never falsely marks the source GC'd.
            now if (capture_path_to_remove is None and (capture_cleanup.get("removed") or capture_cleanup.get("missing"))) else "",
            now,
            now,
            str(row["migration_id"]),
            _OWNER_TOKEN_JSON_PATH,
            owner_token,
        ),
    )
    if finalize.rowcount != 1:
        # The claim no longer holds at finalize time. Because the whole rollback
        # ran under one held write lock this should be impossible, but if it ever
        # happens, abort the entire rollback (placement mutations included) rather
        # than leave a half-rolled-back state behind.
        if own_txn and conn.in_transaction:
            conn.rollback()
        return False
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
    # FIX 3: COMMIT the claim + placement mutations + terminal UPDATE now, releasing
    # the SQLite writer lock. The row is already terminal ('rolled_back') and fenced
    # by the ownership token, so the deferred filesystem cleanup below cannot race a
    # concurrent terminal transition. This shortens the writer-lock hold to the DB
    # work only -- the slow rmtree no longer blocks place_deployment et al.
    conn.commit()

    # Now perform the slow capture rmtree OUTSIDE the write lock, then record its
    # actual result in a short follow-up UPDATE (the in-row metadata was committed
    # optimistically above). The row is terminal, so this update is unguarded by the
    # ownership token; it only refines capture_cleanup / source_garbage_collected_at.
    if capture_path_to_remove is not None:
        actual_cleanup = _perform_capture_rmtree(capture_path_to_remove)
        rollback_payload["capture_cleanup"] = actual_cleanup
        cleanup_done = bool(actual_cleanup.get("removed") or actual_cleanup.get("missing"))
        conn.execute(
            "UPDATE arclink_pod_migrations "
            "SET rollback_metadata_json = ?, source_garbage_collected_at = ?, updated_at = ? "
            "WHERE migration_id = ? AND status = 'rolled_back'",
            (
                _json_dumps(rollback_payload),
                utc_now_iso() if cleanup_done else "",
                utc_now_iso(),
                str(row["migration_id"]),
            ),
        )
        conn.commit()
    return True


def _plan_rolled_back_capture_cleanup(row: Mapping[str, Any]) -> tuple[dict[str, Any], Path | None]:
    """FAST capture-cleanup planning: validate the path and check existence only.

    Round 3 / FIX 3: the slow ``rmtree`` is no longer performed under the
    ``_mark_rollback`` write lock. This split does the cheap stat-only work (path
    safety + existence) and returns ``(plan, path_to_remove)``:
      * ``path_to_remove`` is the directory to ``rmtree`` OUTSIDE the lock, or
        None when there is nothing safe/present to remove.
      * ``plan`` is the optimistic cleanup result recorded in the terminal row's
        rollback_metadata under the lock. For the ``removed`` case it records
        ``{"removed": True}`` optimistically; the post-commit ``rmtree`` then
        confirms (or overwrites with an error) via a short follow-up UPDATE.
    """
    raw = str(row.get("capture_dir") or "").strip()
    if not raw:
        return {"removed": False, "reason": "no_capture_dir"}, None
    path = Path(raw)
    if ".migrations" not in path.parts:
        return {"removed": False, "reason": "unsafe_capture_dir"}, None
    if not path.exists():
        return {"removed": False, "missing": True}, None
    return {"removed": True}, path


def _perform_capture_rmtree(path: Path) -> dict[str, Any]:
    """SLOW capture cleanup: the actual filesystem ``rmtree``, run OUTSIDE any DB
    write lock (Round 3 / FIX 3)."""
    try:
        shutil.rmtree(path)
    except OSError as exc:
        return {"removed": False, "error": str(exc)[:240]}
    return {"removed": True}


def _cleanup_rolled_back_capture(row: Mapping[str, Any]) -> dict[str, Any]:
    """Combined plan+rmtree, retained for callers/tests that want the old one-shot
    behavior. _mark_rollback no longer uses this (it splits the slow rmtree out of
    the write lock); kept so the cleanup logic has a single tested entry point."""
    plan, path = _plan_rolled_back_capture_cleanup(row)
    if path is None:
        return plan
    return _perform_capture_rmtree(path)


def _record_pod_migration_health(conn: sqlite3.Connection, *, row: Mapping[str, Any], checked_at: str) -> None:
    conn.execute(
        """
        INSERT INTO arclink_service_health (deployment_id, service_name, status, checked_at, detail_json)
        VALUES (?, 'pod-migration', 'healthy', ?, ?)
        ON CONFLICT(deployment_id, service_name) DO UPDATE SET
          status = excluded.status,
          checked_at = excluded.checked_at,
          detail_json = excluded.detail_json
        """,
        (
            str(row["deployment_id"]),
            checked_at,
            _json_dumps({"migration_id": str(row["migration_id"]), "target_host_id": str(row["target_host_id"])}),
        ),
    )


def _mark_migration_started(
    conn: sqlite3.Connection,
    *,
    row: Mapping[str, Any],
    reason: str,
) -> dict[str, Any]:
    started_txn = _begin_immediate_if_needed(conn)
    try:
        current = _migration_row(conn, str(row["migration_id"])) or row
        status = str(current.get("status") or "")
        if status != "planned":
            if status == "running":
                raise ArcLinkPodMigrationError(
                    f"ArcLink Pod migration is already running: {current.get('migration_id')}"
                )
            if status in TERMINAL_MIGRATION_STATUSES:
                return dict(current)
            raise ArcLinkPodMigrationError(f"ArcLink Pod migration cannot start from status: {status or 'blank'}")
        blocker = _active_live_migration(
            conn,
            deployment_id=str(current["deployment_id"]),
            exclude_migration_id=str(current["migration_id"]),
        )
        if blocker is not None:
            raise ArcLinkPodMigrationError(
                "ArcLink Pod migration already has an active migration for this deployment: "
                f"{blocker.get('migration_id')}"
            )
        _require_target_host_available(_host(conn, str(current["target_host_id"])))
        now = utc_now_iso()
        # C2: stamp a fresh ownership token into rollback_metadata_json in the SAME
        # atomic UPDATE that flips planned -> running. This worker now exclusively
        # owns the running row; every long-running step and terminal mark guards on
        # this token, so a stale-lease recovery that later rotates the token out can
        # be detected as "ownership lost".
        token = _owner_token()
        conn.execute(
            "UPDATE arclink_pod_migrations "
            "SET status = 'running', "
            "    rollback_metadata_json = json_set(COALESCE(NULLIF(rollback_metadata_json, ''), '{}'), ?, ?), "
            "    updated_at = ? "
            "WHERE migration_id = ? AND status = 'planned'",
            (_OWNER_TOKEN_JSON_PATH, token, now, str(current["migration_id"])),
        )
        append_arclink_event(
            conn,
            subject_kind="deployment",
            subject_id=str(current["deployment_id"]),
            event_type="pod_migration_started",
            metadata={"migration_id": str(current["migration_id"]), "target_host_id": str(current["target_host_id"])},
            commit=False,
        )
        append_arclink_audit(
            conn,
            action="pod_migration_started",
            actor_id="system:pod_migration",
            target_kind="deployment",
            target_id=str(current["deployment_id"]),
            reason=str(reason or "operator requested Pod migration"),
            metadata={"migration_id": str(current["migration_id"]), "target_host_id": str(current["target_host_id"])},
            commit=False,
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM arclink_pod_migrations WHERE migration_id = ?", (str(current["migration_id"]),)).fetchone())
    except Exception:
        if started_txn and conn.in_transaction:
            conn.rollback()
        raise


def _heartbeat_running_migration(
    conn: sqlite3.Connection,
    migration_id: str,
    *,
    owner_token: str = "",
) -> tuple[str, bool]:
    """Touch updated_at on a still-owned 'running' migration; report ownership.

    C1 (heartbeat): the long capture / materialize / docker-apply steps can each
    run for many minutes. Staleness recovery is driven purely by wall-clock age of
    updated_at, so without a periodic touch a live-but-slow migration would be
    declared stale by a concurrent worker, rolled back mid-flight, and could then
    race the success commit. Beating the lease before each long step keeps an
    alive worker's row from ever crossing the lease threshold. The update is
    guarded on status='running' so a heartbeat can never resurrect a terminal row.

    C2 (ownership): the heartbeat ALSO guards on the caller's ownership token, so a
    worker whose stale row was recovered out from under it (the recovery rotated
    the token) sees rowcount 0 and learns it no longer owns the row. Returns
    ``(updated_at, still_owned)``; callers ABORT their Docker lifecycle work when
    ``still_owned`` is False so a recovered-away worker stops mutating live state.
    An empty ``owner_token`` keeps the legacy status-only guard (used where no
    token was ever stamped).
    """
    now = utc_now_iso()
    own_txn = _begin_immediate_if_needed(conn)
    try:
        if owner_token:
            cur = conn.execute(
                "UPDATE arclink_pod_migrations SET updated_at = ? "
                "WHERE migration_id = ? AND status = 'running' "
                "AND COALESCE(json_extract(rollback_metadata_json, ?), '') = ?",
                (now, str(migration_id), _OWNER_TOKEN_JSON_PATH, owner_token),
            )
        else:
            cur = conn.execute(
                "UPDATE arclink_pod_migrations SET updated_at = ? WHERE migration_id = ? AND status = 'running'",
                (now, str(migration_id)),
            )
        still_owned = cur.rowcount >= 1
        if own_txn:
            conn.commit()
    except Exception:
        if own_txn and conn.in_transaction:
            conn.rollback()
        raise
    return now, still_owned


def _retention_days_from_config(retention_days: int | None, env: Mapping[str, str] | None) -> int:
    if retention_days is not None:
        try:
            return int(retention_days)
        except (TypeError, ValueError) as exc:
            raise ArcLinkPodMigrationError("ArcLink Pod migration retention days must be an integer") from exc
    raw = str((env or os.environ).get("ARCLINK_MIGRATION_GC_DAYS") or DEFAULT_GC_DAYS).strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise ArcLinkPodMigrationError("ArcLink Pod migration ARCLINK_MIGRATION_GC_DAYS must be an integer") from exc


def _apply_docker_status_gate(verification: dict[str, Any], docker_status: str) -> dict[str, Any]:
    verification["docker_status"] = docker_status
    if docker_status == "applied":
        return verification
    raw_blockers = verification.get("blockers")
    blockers = dict(raw_blockers) if isinstance(raw_blockers, Mapping) else {}
    blockers["docker_compose_apply"] = docker_status or "missing"
    verification["blockers"] = blockers
    verification["healthy"] = False
    return verification


def _mark_success(
    conn: sqlite3.Connection,
    *,
    row: Mapping[str, Any],
    target_intent: Mapping[str, Any],
    capture_manifest: Mapping[str, Any],
    verification: Mapping[str, Any],
    retention_days: int,
    commit: bool = True,
) -> dict[str, Any]:
    now_dt = _utc()
    now = _iso(now_dt)
    retention_until = _iso(now_dt + timedelta(days=max(0, int(retention_days))))
    source_placement_id = str(row["source_placement_id"])
    target_placement_id = str(row["target_placement_id"])
    owner_token = _row_owner_token(row)
    # C1/C2 fencing: claim the migration row only while it is still 'running' AND
    # this worker still owns it (token unchanged), BEFORE mutating any placements.
    # If a concurrent stale-lease recovery already rolled this migration back to a
    # terminal state OR rotated the ownership token (claiming the still-'running'
    # row for recovery), this claim matches zero rows and we raise so the caller's
    # transaction rolls back -- a terminal 'rolled_back' row is never clobbered back
    # to 'succeeded', and the live serving placement set is never re-flipped under a
    # row that another worker is recovering / already tore down.
    claimed = conn.execute(
        "UPDATE arclink_pod_migrations SET updated_at = ? "
        "WHERE migration_id = ? AND status = 'running' "
        "AND COALESCE(json_extract(rollback_metadata_json, ?), '') = ?",
        (now, str(row["migration_id"]), _OWNER_TOKEN_JSON_PATH, owner_token),
    )
    if claimed.rowcount != 1:
        raise ArcLinkPodMigrationError(
            "ArcLink Pod migration cannot mark succeeded: row is no longer 'running' "
            "or ownership was lost to a concurrent recovery: "
            f"{row['migration_id']}"
        )
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
        (_json_dumps(metadata), now, str(row["deployment_id"])),
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
        WHERE migration_id = ? AND status = 'running'
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
    _record_pod_migration_health(conn, row=row, checked_at=now)
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
    if commit:
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


def _migration_running_lease_seconds(env: Mapping[str, str] | None) -> int:
    source = dict(env) if env is not None else dict(os.environ)
    raw = str(source.get(MIGRATION_RUNNING_LEASE_SECONDS_ENV) or "").strip()
    if not raw:
        return DEFAULT_MIGRATION_RUNNING_LEASE_SECONDS
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MIGRATION_RUNNING_LEASE_SECONDS
    # FIX 2: clamp UP to MINIMUM_MIGRATION_RUNNING_LEASE_SECONDS (not the old 60s
    # floor). The lease must always exceed the longest a single migration step can
    # run without a heartbeat (see the constant's comment), otherwise a worker
    # actively inside one docker_compose_apply could be declared stale and
    # recovered while it is still applying -- reopening the Docker-flapping window.
    return max(MINIMUM_MIGRATION_RUNNING_LEASE_SECONDS, value)


def _recover_stale_running_migration(
    conn: sqlite3.Connection,
    *,
    row: Mapping[str, Any],
    operation_key: str,
    intent: Mapping[str, Any],
    executor: ArcLinkExecutor,
    env: Mapping[str, str] | None,
) -> dict[str, Any] | None:
    """Recover a migration stranded in 'running' by a crashed worker.

    Returns the recovered (terminal) migration row when recovery ran, else None.

    Safety: the source was stopped before the target was verified, so a stranded
    run may have left BOTH source stopped and target half-up. Recovery performs a
    best-effort rollback (restart source, tear down target), marks the migration
    rolled_back/failed (terminal), and FAILS the idempotency row so a fresh
    migration of the same deployment is no longer refused as "already running".
    """
    if str(row.get("status") or "") != "running":
        return None
    observed_updated_at = str(row.get("updated_at") or "")
    last_seen = _parse_iso(observed_updated_at or str(row.get("created_at") or ""))
    if last_seen is None:
        return None
    age_seconds = (_utc() - last_seen).total_seconds()
    if age_seconds < _migration_running_lease_seconds(env):
        return None
    # C1/C2 fencing: claim this stranded row BEFORE any Docker lifecycle work so two
    # workers can never both restart the source / tear down the target for the SAME
    # stranded migration. The claim is an atomic compare-and-swap on
    # (status='running', updated_at=<observed stale value>) under BEGIN IMMEDIATE --
    # exactly one worker matches; the loser's CAS matches zero rows (the winner
    # moved updated_at forward) and it bails out, leaving the winner to drive the
    # rollback. A None updated_at can't be claimed safely, so require a concrete
    # observed value.
    #
    # C2 (exclusive ownership vs the ORIGINAL live worker): the same atomic UPDATE
    # ALSO ROTATES the ownership token to a fresh recovery nonce. This is the
    # "transition OUT of running" mechanism -- it cannot use a literal sentinel
    # status because the schema CHECK constraint forbids one, but rotating the
    # token achieves the same exclusivity: the original live worker (which may
    # still be alive and slow) loses ownership the instant the token changes, so
    # its _mark_success / _mark_rollback / heartbeat all start matching zero rows
    # and abort, while the recovery proceeds under the NEW token. The recovery then
    # drives the rollback lifecycle and sets the terminal status itself.
    if not observed_updated_at:
        return None
    claim_ts = utc_now_iso()
    recovery_token = _owner_token()
    own_txn = _begin_immediate_if_needed(conn)
    try:
        claimed = conn.execute(
            "UPDATE arclink_pod_migrations SET updated_at = ?, "
            "rollback_metadata_json = json_set(COALESCE(NULLIF(rollback_metadata_json, ''), '{}'), ?, ?) "
            "WHERE migration_id = ? AND status = 'running' AND updated_at = ?",
            (claim_ts, _OWNER_TOKEN_JSON_PATH, recovery_token, str(row["migration_id"]), observed_updated_at),
        )
        won = claimed.rowcount == 1
        if own_txn:
            conn.commit()
    except Exception:
        if own_txn and conn.in_transaction:
            conn.rollback()
        raise
    if not won:
        # Another worker already claimed (or the row left 'running'); re-read to be
        # sure we don't proceed against a stale snapshot.
        return None
    # Work on a snapshot whose updated_at AND ownership token match the claim so the
    # downstream _mark_rollback fence (status='running' AND token) sees an owned,
    # still-'running' row. Re-read rollback_metadata_json from the DB so the token
    # we just rotated in is present in the snapshot.
    refreshed = _migration_row(conn, str(row["migration_id"]))
    base = dict(refreshed) if refreshed is not None else dict(row)
    row = {**base, "updated_at": claim_ts}
    error = f"ArcLink Pod migration lease expired after {int(age_seconds)}s in 'running' (stale worker recovery)"
    # H6 (round 2): a stranded run may have already brought the target partway up
    # before crashing. _rollback_lifecycle only tears the target down when it is
    # handed a target_intent, so reconstruct it here from the stranded row's
    # recorded target host/state-root. For an in-place ("current") migration the
    # target IS the source and _rollback_lifecycle skips teardown on its own, so a
    # None intent there is harmless -- only reconstruct for a cross-host target.
    target_intent: dict[str, Any] | None = None
    if str(row.get("target_host_id") or "") != str(row.get("source_host_id") or ""):
        try:
            target_intent = _render_target_intent(
                conn,
                deployment_id=str(row["deployment_id"]),
                target_host=_host(conn, str(row["target_host_id"])),
                fallback_base=str(Path(str(row.get("target_state_root") or "")).parent),
                env=env,
            )
        except Exception:
            # Best-effort recovery: if the intent cannot be rebuilt (e.g. the
            # target host is gone), proceed without target teardown rather than
            # leaving the migration stranded in 'running' forever.
            target_intent = None
    # The stranded run had already stopped the source (that is the first live
    # step), so attempt to restart it during rollback.
    lifecycle_metadata = _rollback_lifecycle(
        executor=executor,
        row=row,
        operation_key=operation_key,
        target_intent=target_intent,
        source_stopped=True,
    )
    _mark_rollback(
        conn,
        row=row,
        verification={"healthy": False, "error": error, "recovered_from": "stale_running_lease"},
        error=error,
        lifecycle_metadata=lifecycle_metadata,
    )
    recovered = _migration_row(conn, str(row["migration_id"])) or dict(row)
    try:
        fail_arclink_operation_idempotency(
            conn,
            operation_kind=OPERATION_KIND,
            idempotency_key=operation_key,
            intent=intent,
            error=error,
            result=_result_from_row(recovered),
        )
    except (KeyError, ValueError):
        # The idempotency row may be absent or already terminal -- the migration
        # row is now terminal regardless, which is what unblocks future migrations.
        pass
    append_arclink_audit(
        conn,
        action="pod_migration_stale_lease_recovered",
        actor_id="system:pod_migration",
        target_kind="deployment",
        target_id=str(row["deployment_id"]),
        reason=error,
        metadata={"migration_id": str(row["migration_id"]), "age_seconds": int(age_seconds)},
    )
    return recovered


def _still_owns_running_row(
    conn: sqlite3.Connection, *, migration_id: str, owner_token: str
) -> bool:
    """Re-read the row and report whether THIS worker still owns a running migration.

    Round 3 / FIX 1: ownership is otherwise only verified at heartbeat STEP
    BOUNDARIES. Before either rollback path runs its Docker lifecycle work
    (source restart / target teardown) we re-confirm against the LIVE DB row that
    a concurrent stale-lease recovery has not rotated our token out -- if it has,
    the recovery owns the rollback and we must NOT run _rollback_lifecycle (which
    would double the Docker work) nor _mark_rollback.
    """
    current = _migration_row(conn, str(migration_id))
    if current is None:
        return False
    if str(current.get("status") or "") not in {"planned", "running"}:
        return False
    return _row_owner_token(current) == owner_token


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
    days: int | None = None
    if not dry_run:
        days = _retention_days_from_config(retention_days, env)
        # H6: before doing anything, reclaim any migration of this deployment that
        # a crashed worker stranded in 'running'. Otherwise the stale non-terminal
        # row blocks every future migration (either as "already running" for the
        # same id, or as the active-migration blocker for a fresh id) -- the
        # deployment can never be migrated again until manual intervention.
        #
        # M4: a crashed worker can strand more than one row over time, so loop over
        # EVERY stale 'running' row, not just the oldest. Recovery returns None for
        # a row whose lease has NOT expired (a live, in-flight migration) or one
        # that another worker just claimed -- in either case we must NOT fall
        # through into the migration body, which would trip "already running" or
        # hit the generic exception path and ROLL BACK a fresh, healthy live
        # migration (H6 NEW-BUG, round 2). Bail out cleanly and do nothing
        # destructive; only proceed once all stale rows are terminal.
        for stranded in _stranded_running_migrations(conn, deployment_id=str(deployment_id or "").strip()):
            recovered = _recover_stale_running_migration(
                conn,
                row=stranded,
                operation_key=str(stranded["operation_idempotency_key"] or f"arclink:migration:{stranded['migration_id']}"),
                intent=_operation_intent(stranded, dry_run=False),
                executor=executor,
                env=env,
            )
            if recovered is None:
                return _result_from_row(stranded, idempotent_replay=True, dry_run=dry_run)
    existing = _migration_row(conn, str(migration_id or "").strip()) if str(migration_id or "").strip() else None
    if not dry_run and (
        existing is None
        or str(existing.get("status") or "") not in TERMINAL_MIGRATION_STATUSES
    ):
        _require_root_capture_opt_in(env)
        _migration_capture_helper_config(env, require_for_docker=True)
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
    if str(row["status"]) in TERMINAL_MIGRATION_STATUSES:
        return _result_from_row(row, idempotent_replay=True, dry_run=dry_run)
    if not dry_run:
        _validate_capture_paths(conn, row)

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

    row = _mark_migration_started(conn, row=row, reason=reason)
    if str(row.get("status") or "") in TERMINAL_MIGRATION_STATUSES:
        return _result_from_row(row, idempotent_replay=True, dry_run=dry_run)

    # C2: the token _mark_migration_started stamped is THIS worker's exclusive
    # ownership of the running row. Every heartbeat below re-asserts it; if a
    # concurrent stale-lease recovery rotates the token, the heartbeat reports lost
    # ownership and we ABORT before doing any further Docker lifecycle work, so a
    # recovered-away worker never keeps materializing / applying / restarting.
    owner_token = _row_owner_token(row)

    def _beat_or_abort() -> None:
        _ts, still_owned = _heartbeat_running_migration(
            conn, str(row["migration_id"]), owner_token=owner_token
        )
        if not still_owned:
            raise ArcLinkPodMigrationError(
                "ArcLink Pod migration lost ownership of its running row to a "
                f"concurrent stale-lease recovery: {row['migration_id']}"
            )

    capture_manifest: dict[str, Any] = {}
    source_stopped = False
    target_intent: dict[str, Any] | None = None
    try:
        # Round 3 / FIX 1: re-check ownership IMMEDIATELY BEFORE the very first live
        # Docker action (the source stop). _mark_migration_started stamped our token
        # and committed, but a concurrent stale-lease recovery could have rotated it
        # out between that commit and here (the prior code's first heartbeat came
        # only AFTER the stop). If we no longer own the row, the recovery owns the
        # lifecycle -- bail BEFORE stopping the source so a recovered-away worker can
        # never take a live deployment down out from under the recovery.
        _beat_or_abort()
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

        # C1 heartbeat / C2 ownership: keep the lease fresh AND confirm we still own
        # the row before the long file capture.
        _beat_or_abort()
        capture_manifest = _capture_files(conn, row=row, env=env)
        conn.execute(
            "UPDATE arclink_pod_migrations SET capture_manifest_json = ?, updated_at = ? "
            "WHERE migration_id = ? AND status = 'running' "
            "AND COALESCE(json_extract(rollback_metadata_json, ?), '') = ?",
            (_json_dumps(capture_manifest), utc_now_iso(), str(row["migration_id"]), _OWNER_TOKEN_JSON_PATH, owner_token),
        )
        conn.commit()

        deployment = _load_deployment(conn, str(row["deployment_id"]))
        target_host = _host(conn, str(row["target_host_id"]))
        _require_target_host_available(target_host)
        target_intent = _render_target_intent(
            conn,
            deployment_id=str(row["deployment_id"]),
            target_host=target_host,
            fallback_base=str(Path(str(row["target_state_root"])).parent),
            env=env,
        )
        _ensure_llm_router_key_for_intent(conn, deployment=deployment, intent=target_intent, env=env)
        # C1 heartbeat / C2 ownership: beat + re-check ownership before the long
        # materialize + docker apply so a recovered-away worker stops here.
        _beat_or_abort()
        _materialize_files(conn, row=row, target_root=str(target_intent["state_roots"]["root"]), env=env)
        # C1 heartbeat / C2 ownership: final beat + ownership re-check before the
        # docker apply -- the last point we can cheaply bail before mutating the
        # target compose project.
        _beat_or_abort()
        docker_result = executor.docker_compose_apply(
            DockerComposeApplyRequest(
                deployment_id=str(row["deployment_id"]),
                intent=target_intent,
                idempotency_key=f"{operation_key}:compose-target",
            )
        )
        verification = _normalize_verification((verifier or _default_verifier)(conn, row, target_intent))
        verification = _apply_docker_status_gate(verification, str(docker_result.status))
        if not bool(verification.get("healthy")):
            error = "ArcLink Pod migration verification failed"
            # Round 3 / FIX 1: re-check ownership IMMEDIATELY BEFORE _rollback_lifecycle.
            # docker_compose_apply can run for many minutes; a concurrent stale-lease
            # recovery could have rotated our token out during it. If we no longer own
            # the row, that recovery owns the rollback -- running our own
            # _rollback_lifecycle here would DOUBLE the source-restart / target-teardown
            # Docker work (the residual flapping window Codex flagged). Skip the Docker
            # lifecycle AND _mark_rollback (which would no-op on the token mismatch
            # anyway) and let the recovery's outcome stand.
            if _still_owns_running_row(
                conn, migration_id=str(row["migration_id"]), owner_token=owner_token
            ):
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

        try:
            succeeded = _mark_success(
                conn,
                row=row,
                target_intent=target_intent,
                capture_manifest=capture_manifest,
                verification=verification,
                retention_days=int(days if days is not None else DEFAULT_GC_DAYS),
                commit=False,
            )
            result = _result_from_row(succeeded)
            complete_arclink_operation_idempotency(
                conn,
                operation_kind=OPERATION_KIND,
                idempotency_key=operation_key,
                intent=intent,
                provider_refs={"target_host_id": str(row["target_host_id"])},
                result=result,
                commit=False,
            )
            conn.commit()
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
        return result
    except Exception as exc:
        error = str(exc)[:1000]
        current = _migration_row(conn, str(row["migration_id"])) or row
        # C2 / Round 3 FIX 1: if a concurrent stale-lease recovery rotated the
        # ownership token out from under us, that recovery now exclusively owns the
        # rollback lifecycle. Doing our own _rollback_lifecycle here would DOUBLE the
        # source-restart / target-teardown Docker work, so only perform rollback
        # while we STILL OWN a still-'running' row (re-read fresh from the DB via the
        # shared ownership check). _mark_rollback itself also no-ops on a token
        # mismatch, but we must skip _rollback_lifecycle (the actual Docker mutation)
        # too -- hence the explicit ownership gate before any Docker lifecycle work.
        if _still_owns_running_row(
            conn, migration_id=str(row["migration_id"]), owner_token=owner_token
        ):
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
        _validate_capture_paths(conn, row)
        capture_dir = Path(str(row.get("capture_dir") or "")).resolve(strict=False)
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
