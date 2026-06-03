#!/usr/bin/env python3
"""Captain fleet shared folder: a git-backed, read-write folder every agent in a
Captain's fleet can use, synced across machines.

Design (see [[fleet-shared-folder]] memory): the canonical content lives in a
Captain-scoped *bare hub* repo that is independent of any single agent, so the
Captain can remove any agent (even the first) without orphaning the folder. Each
active agent gets a read-write working clone that the Drive/Code "Fleet" root
surfaces, and a sync pass commits local edits, ``git pull --rebase`` and pushes
so every machine converges. Conflicts are surfaced (never silently clobbered).

The git transport is injectable (``SubprocessGitRunner`` by default) so the sync
engine is unit-testable against real local repos without any live host.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import time
from typing import Any, Callable, Mapping, Sequence

from arclink_boundary import json_dumps_safe, json_loads_safe, rowdict
from arclink_control import (
    Config,
    append_arclink_audit,
    append_arclink_event,
    connect_db,
    ensure_schema,
    utc_now_iso,
)


DEFAULT_BRANCH = "main"
DEFAULT_FOLDER_LABEL = "Fleet"
DEFAULT_ACCESS_MODE = "read-write"
DEFAULT_AUTHOR_NAME = "ArcLink Fleet"
DEFAULT_AUTHOR_EMAIL = "fleet@arclink.local"
DEFAULT_HUB_ROOT = "/arcdata/captains"
_GIT_TIMEOUT_SECONDS = 120
_SEGMENT_RE = re.compile(r"[^A-Za-z0-9._-]+")
FLEET_LAYOUT_READMES = {
    "Projects": "Shared project workspaces for the Captain's fleet. Prefer one folder per collaborative project.\n",
    "Research": "Fleet-wide research notes, source maps, and durable findings that multiple agents can reuse.\n",
    "Repos": "Fleet-visible repository notes and managed mirrors. Avoid concurrent edits inside the same repo without pulling first.\n",
    "Agents_KB": "Fleet-wide agent knowledge base material, including shared operating references and reusable role notes.\n",
    "Agents_Skills": "Fleet-shared Hermes skill workspaces. Contributing agents may enable skills explicitly in their own Hermes config.\n",
    "Agents_Plugins": "Fleet-shared plugin notes and rollout records. Runtime plugin enablement remains per agent.\n",
}


class ArcLinkFleetShareError(ValueError):
    pass


def _fleet_share_id() -> str:
    return f"flsh_{secrets.token_hex(12)}"


def _fleet_share_member_id() -> str:
    return f"flsm_{secrets.token_hex(12)}"


def _safe_segment(value: str, *, fallback: str = "captain") -> str:
    segment = _SEGMENT_RE.sub("-", str(value or "").strip()).strip("-._")
    return (segment[:96] or fallback)


def _json(value: Mapping[str, Any] | None) -> str:
    return json_dumps_safe(value or {}, label="ArcLink fleet share", error_cls=ArcLinkFleetShareError)


# ---------------------------------------------------------------------------
# git transport (injectable)
# ---------------------------------------------------------------------------


@dataclass
class GitResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class SubprocessGitRunner:
    """Runs ``git`` as a subprocess. The default transport for production use."""

    def __init__(self, *, timeout: int = _GIT_TIMEOUT_SECONDS, env: Mapping[str, str] | None = None) -> None:
        self._timeout = int(timeout)
        self._env = dict(env) if env is not None else None

    def run(self, args: Sequence[str], *, cwd: str | None = None) -> GitResult:
        try:
            completed = subprocess.run(  # noqa: S603 - args are constructed internally, never from user text
                list(args),
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                env=self._env,
                check=False,
            )
        except FileNotFoundError as exc:
            return GitResult(returncode=127, stdout="", stderr=str(exc))
        except subprocess.TimeoutExpired as exc:
            return GitResult(returncode=124, stdout="", stderr=f"git timed out: {exc}")
        return GitResult(returncode=completed.returncode, stdout=completed.stdout or "", stderr=completed.stderr or "")


def _git(runner: Any, args: Sequence[str], cwd: str | None = None) -> GitResult:
    return runner.run(["git", *args], cwd=cwd)


def _assert_safe_git_arg(value: str, *, label: str) -> str:
    """Reject values that git could parse as an option or that contain control chars.

    Defense-in-depth: ``hub_ref``/``working_path`` are control-plane generated, but a
    value beginning with ``-`` would be read by git as a flag (option injection).
    """
    text = str(value or "").strip()
    if not text:
        raise ArcLinkFleetShareError(f"fleet share {label} is required")
    if text.startswith("-"):
        raise ArcLinkFleetShareError(f"fleet share {label} cannot start with '-'")
    if "\x00" in text or "\n" in text or "\r" in text:
        raise ArcLinkFleetShareError(f"fleet share {label} contains invalid characters")
    return text


def _is_valid_git_repo(runner: Any, work: Path) -> bool:
    return _git(runner, ["rev-parse", "--git-dir"], cwd=str(work)).ok


def _quarantine_corrupt_working_copy(work: Path) -> Path:
    """Move a corrupt working copy aside (preserving the user's files) so it can be re-cloned."""
    base = work.with_name(work.name + ".corrupt")
    candidate = base
    counter = 1
    while candidate.exists():
        candidate = work.with_name(f"{work.name}.corrupt-{counter}")
        counter += 1
    work.rename(candidate)
    return candidate


@dataclass
class FleetShareSyncResult:
    deployment_id: str
    status: str  # "synced" | "conflict" | "error"
    head_commit: str = ""
    committed: bool = False
    pushed: bool = False
    pulled: bool = False
    detail: str = ""


# ---------------------------------------------------------------------------
# hub + working-copy git operations
# ---------------------------------------------------------------------------


def default_hub_ref(owner_user_id: str) -> str:
    """Where a Captain's canonical bare repo lives, independent of any agent.

    ``ARCLINK_FLEET_SHARE_HUB_URL`` may contain ``{user}`` for an explicit (often
    cross-host, e.g. ssh://) transport; otherwise the hub is a per-Captain bare
    repo under ``ARCLINK_FLEET_SHARE_HUB_ROOT`` (default ``/arcdata/captains``).
    """
    user_segment = _safe_segment(owner_user_id, fallback="captain")
    template = str(os.environ.get("ARCLINK_FLEET_SHARE_HUB_URL") or "").strip()
    if template:
        if "{user}" in template:
            return template.replace("{user}", user_segment)
        return f"{template.rstrip('/')}/{user_segment}/fleet-shared.git"
    root = str(os.environ.get("ARCLINK_FLEET_SHARE_HUB_ROOT") or DEFAULT_HUB_ROOT).rstrip("/")
    return f"{root}/{user_segment}/fleet-shared.git"


def ensure_hub_repo(runner: Any, hub_ref: str) -> bool:
    """Create the bare hub repo for a local hub path. No-op for remote URLs.

    Returns True if a local bare repo now exists (or the ref is a remote URL we
    trust the operator to have provisioned).
    """
    ref = str(hub_ref or "").strip()
    if not ref:
        raise ArcLinkFleetShareError("fleet share hub reference is required")
    _assert_safe_git_arg(ref, label="hub reference")
    if "://" in ref or "@" in ref.split("/", 1)[0]:
        # Remote transport (ssh://, https://, user@host:path) — provisioned out of band.
        return True
    hub_path = Path(ref).expanduser()
    if (hub_path / "HEAD").exists() or (hub_path / "objects").exists():
        return True
    hub_path.mkdir(parents=True, exist_ok=True)
    result = _git(runner, ["init", "--bare", "-b", DEFAULT_BRANCH, str(hub_path)])
    if not result.ok:
        raise ArcLinkFleetShareError(f"failed to initialize fleet share hub: {result.stderr.strip() or result.stdout.strip()}")
    return True


def ensure_default_fleet_layout(working_path: str | Path) -> dict[str, int]:
    """Seed the Fleet root with durable shared-resource folders.

    The function is additive and never overwrites Captain or Agent content. The
    normal fleet sync cycle commits the created files, so all ArcPods converge
    through the existing multi-writer git path.
    """
    work = Path(working_path).expanduser()
    created_dirs = 0
    created_files = 0
    for dirname, body in FLEET_LAYOUT_READMES.items():
        directory = work / dirname
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
            created_dirs += 1
        readme = directory / "README.md"
        if not readme.exists():
            readme.write_text(f"# {dirname}\n\n{body}", encoding="utf-8")
            created_files += 1
    return {"created_dirs": created_dirs, "created_files": created_files}


def ensure_member_working_copy(runner: Any, *, hub_ref: str, working_path: str, branch: str = DEFAULT_BRANCH) -> None:
    """Ensure ``working_path`` is a git working copy whose origin is ``hub_ref``."""
    ref = _assert_safe_git_arg(hub_ref, label="hub reference")
    _assert_safe_git_arg(working_path, label="working path")
    work = Path(working_path).expanduser()
    git_dir = work / ".git"
    if git_dir.exists():
        if _is_valid_git_repo(runner, work):
            # Keep the origin pointed at the current hub ref.
            current = _git(runner, ["remote", "get-url", "origin"], cwd=str(work))
            if not current.ok:
                _git(runner, ["remote", "add", "origin", ref], cwd=str(work))
            elif current.stdout.strip() != ref:
                _git(runner, ["remote", "set-url", "origin", ref], cwd=str(work))
            ensure_default_fleet_layout(work)
            return
        # A partially-corrupt .git (e.g. files deleted via the writable Fleet root)
        # would otherwise wedge forever. Preserve the user's files and re-clone.
        _quarantine_corrupt_working_copy(work)
    work.mkdir(parents=True, exist_ok=True)
    clone = _git(runner, ["-c", f"init.defaultBranch={branch}", "clone", ref, str(work)])
    if clone.ok:
        ensure_default_fleet_layout(work)
        return
    # Hub unreachable as a clone source (e.g. brand-new empty local bare repo on
    # some git versions): fall back to init + remote add so the first sync seeds it.
    init = _git(runner, ["init", "-b", branch, str(work)])
    if not init.ok:
        raise ArcLinkFleetShareError(f"failed to initialize fleet share working copy: {init.stderr.strip() or clone.stderr.strip()}")
    _git(runner, ["remote", "add", "origin", ref], cwd=str(work))
    ensure_default_fleet_layout(work)


def sync_member(
    runner: Any,
    *,
    working_path: str,
    hub_ref: str,
    branch: str = DEFAULT_BRANCH,
    deployment_id: str = "",
    author_name: str = DEFAULT_AUTHOR_NAME,
    author_email: str = DEFAULT_AUTHOR_EMAIL,
    message: str = "",
) -> FleetShareSyncResult:
    """Commit local edits, rebase onto the hub, and push. Surface conflicts.

    Read-write multi-writer convergence: a non-fast-forward push triggers a
    fetch + ``rebase`` retry; an unresolvable rebase is reported as a conflict
    rather than clobbering a peer's writes.
    """
    _assert_safe_git_arg(hub_ref, label="hub reference")
    _assert_safe_git_arg(working_path, label="working path")
    work = Path(working_path).expanduser()
    if not (work / ".git").exists():
        ensure_member_working_copy(runner, hub_ref=hub_ref, working_path=working_path, branch=branch)
    ident = ["-c", f"user.name={author_name}", "-c", f"user.email={author_email}"]
    commit_message = message or "ArcLink fleet shared folder sync"

    committed = False
    pulled = False

    stage = _git(runner, ["add", "-A"], cwd=str(work))
    if not stage.ok:
        return FleetShareSyncResult(deployment_id=deployment_id, status="error", detail=stage.stderr.strip() or "git add failed")
    porcelain = _git(runner, ["status", "--porcelain"], cwd=str(work))
    if porcelain.stdout.strip():
        commit = _git(runner, [*ident, "commit", "-m", commit_message], cwd=str(work))
        if not commit.ok:
            return FleetShareSyncResult(
                deployment_id=deployment_id,
                status="error",
                head_commit=_head_commit(runner, work),
                detail=commit.stderr.strip() or commit.stdout.strip() or "git commit failed",
            )
        committed = True

    for _attempt in range(2):
        fetch = _git(runner, ["fetch", "origin"], cwd=str(work))
        if not fetch.ok and "couldn't find remote ref" not in (fetch.stderr or "").lower():
            # An unreachable hub is a soft error: local edits are committed and
            # will push on the next pass once the hub is reachable again.
            return FleetShareSyncResult(
                deployment_id=deployment_id,
                status="error",
                head_commit=_head_commit(runner, work),
                committed=committed,
                detail=fetch.stderr.strip() or "git fetch failed",
            )
        remote_has = _git(runner, ["rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}"], cwd=str(work)).ok
        head_before = _head_commit(runner, work)
        if remote_has and head_before:
            rebase = _git(runner, [*ident, "rebase", f"origin/{branch}"], cwd=str(work))
            if not rebase.ok:
                _git(runner, ["rebase", "--abort"], cwd=str(work))
                return FleetShareSyncResult(
                    deployment_id=deployment_id,
                    status="conflict",
                    head_commit=head_before,
                    committed=committed,
                    detail="Local edits conflict with the shared folder. Resolve and re-sync.",
                )
            if _head_commit(runner, work) != head_before:
                pulled = True
        elif remote_has and not head_before:
            # Working copy has no commits yet; adopt the hub's history.
            checkout = _git(runner, ["checkout", "-B", branch, f"origin/{branch}"], cwd=str(work))
            pulled = checkout.ok

        head_now = _head_commit(runner, work)
        if not head_now:
            # Nothing committed locally and nothing on the hub yet.
            return FleetShareSyncResult(deployment_id=deployment_id, status="synced", pulled=pulled, detail="empty")
        push = _git(runner, ["push", "origin", f"HEAD:{branch}"], cwd=str(work))
        if push.ok:
            return FleetShareSyncResult(
                deployment_id=deployment_id,
                status="synced",
                head_commit=head_now,
                committed=committed,
                pushed=True,
                pulled=pulled,
            )
        # Non-fast-forward (a peer pushed first): loop to fetch + rebase + retry.
    return FleetShareSyncResult(
        deployment_id=deployment_id,
        status="error",
        head_commit=_head_commit(runner, work),
        committed=committed,
        pulled=pulled,
        detail="could not push to the fleet share hub after rebase",
    )


def _head_commit(runner: Any, work: Path) -> str:
    result = _git(runner, ["rev-parse", "--verify", "--quiet", "HEAD"], cwd=str(work))
    return result.stdout.strip() if result.ok else ""


# ---------------------------------------------------------------------------
# control-plane CRUD
# ---------------------------------------------------------------------------


def get_fleet_share_for_user(conn: sqlite3.Connection, owner_user_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM arclink_fleet_shares WHERE owner_user_id = ?",
        (str(owner_user_id or "").strip(),),
    ).fetchone()
    return rowdict(row) if row is not None else {}


def ensure_fleet_share(
    conn: sqlite3.Connection,
    *,
    owner_user_id: str,
    hub_ref: str = "",
    folder_label: str = DEFAULT_FOLDER_LABEL,
    access_mode: str = DEFAULT_ACCESS_MODE,
    commit: bool = True,
) -> dict[str, Any]:
    owner = str(owner_user_id or "").strip()
    if not owner:
        raise ArcLinkFleetShareError("fleet share requires an owner user")
    if conn.execute("SELECT 1 FROM arclink_users WHERE user_id = ?", (owner,)).fetchone() is None:
        raise KeyError(owner)
    existing = get_fleet_share_for_user(conn, owner)
    now = utc_now_iso()
    resolved_hub = str(hub_ref or "").strip() or (existing.get("hub_ref") if existing else "") or default_hub_ref(owner)
    if existing:
        conn.execute(
            """
            UPDATE arclink_fleet_shares
            SET hub_ref = ?, status = CASE WHEN status = 'removed' THEN 'active' ELSE status END, updated_at = ?
            WHERE share_id = ?
            """,
            (resolved_hub, now, existing["share_id"]),
        )
        if commit:
            conn.commit()
        return get_fleet_share_for_user(conn, owner)
    share_id = _fleet_share_id()
    conn.execute(
        """
        INSERT INTO arclink_fleet_shares (
          share_id, owner_user_id, hub_ref, folder_label, access_mode, status, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'active', '{}', ?, ?)
        """,
        (share_id, owner, resolved_hub, str(folder_label or DEFAULT_FOLDER_LABEL), str(access_mode or DEFAULT_ACCESS_MODE), now, now),
    )
    append_arclink_audit(
        conn,
        action="fleet_share_created",
        actor_id=owner,
        target_kind="fleet_share",
        target_id=share_id,
        reason="captain fleet shared folder created",
        metadata={"hub_ref": resolved_hub, "access_mode": access_mode},
        commit=False,
    )
    if commit:
        conn.commit()
    return get_fleet_share_for_user(conn, owner)


def list_fleet_share_members(
    conn: sqlite3.Connection,
    *,
    owner_user_id: str = "",
    share_id: str = "",
    status: str = "active",
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if owner_user_id:
        clauses.append("owner_user_id = ?")
        params.append(str(owner_user_id).strip())
    if share_id:
        clauses.append("share_id = ?")
        params.append(str(share_id).strip())
    if status:
        clauses.append("status = ?")
        params.append(str(status).strip())
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM arclink_fleet_share_members{where} ORDER BY created_at ASC, member_id ASC",
        params,
    ).fetchall()
    return [rowdict(row) for row in rows]


def add_fleet_share_member(
    conn: sqlite3.Connection,
    *,
    owner_user_id: str,
    deployment_id: str,
    working_path: str,
    role: str = "member",
    commit: bool = True,
) -> dict[str, Any]:
    owner = str(owner_user_id or "").strip()
    deployment = str(deployment_id or "").strip()
    if not deployment:
        raise ArcLinkFleetShareError("fleet share member requires a deployment")
    share = ensure_fleet_share(conn, owner_user_id=owner, commit=False)
    share_id = str(share["share_id"])
    now = utc_now_iso()
    existing = conn.execute(
        "SELECT * FROM arclink_fleet_share_members WHERE share_id = ? AND deployment_id = ?",
        (share_id, deployment),
    ).fetchone()
    if existing is not None:
        conn.execute(
            """
            UPDATE arclink_fleet_share_members
            SET status = 'active', working_path = ?, role = ?, removed_at = '', updated_at = ?,
                joined_at = CASE WHEN joined_at = '' THEN ? ELSE joined_at END
            WHERE member_id = ?
            """,
            (str(working_path or ""), str(role or "member"), now, now, existing["member_id"]),
        )
        if commit:
            conn.commit()
        return rowdict(conn.execute("SELECT * FROM arclink_fleet_share_members WHERE member_id = ?", (existing["member_id"],)).fetchone())
    member_id = _fleet_share_member_id()
    conn.execute(
        """
        INSERT INTO arclink_fleet_share_members (
          member_id, share_id, owner_user_id, deployment_id, working_path, role, status,
          joined_at, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, '{}', ?, ?)
        """,
        (member_id, share_id, owner, deployment, str(working_path or ""), str(role or "member"), now, now, now),
    )
    append_arclink_event(
        conn,
        subject_kind="fleet_share",
        subject_id=share_id,
        event_type="fleet_share_member_joined",
        metadata={"deployment_id": deployment, "owner_user_id": owner},
        commit=False,
    )
    if commit:
        conn.commit()
    return rowdict(conn.execute("SELECT * FROM arclink_fleet_share_members WHERE member_id = ?", (member_id,)).fetchone())


def remove_fleet_share_member(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    share_id: str = "",
    commit: bool = True,
) -> int:
    """Deregister a deployment from the fleet share.

    Only the member row is touched: the hub and every other agent's working copy
    are untouched, so removing any agent never orphans the shared folder.
    """
    deployment = str(deployment_id or "").strip()
    if not deployment:
        return 0
    now = utc_now_iso()
    params: list[Any] = [now, now, deployment]
    extra = ""
    if share_id:
        extra = " AND share_id = ?"
        params.append(str(share_id).strip())
    cursor = conn.execute(
        f"""
        UPDATE arclink_fleet_share_members
        SET status = 'removed', removed_at = ?, updated_at = ?
        WHERE deployment_id = ? AND status != 'removed'{extra}
        """,
        params,
    )
    if cursor.rowcount and commit:
        conn.commit()
    return cursor.rowcount


def record_fleet_share_sync(
    conn: sqlite3.Connection,
    *,
    member_id: str,
    status: str,
    head_commit: str = "",
    detail: str = "",
    commit: bool = True,
) -> None:
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE arclink_fleet_share_members
        SET last_synced_at = ?, last_sync_status = ?, last_sync_commit = ?, last_sync_detail = ?, updated_at = ?
        WHERE member_id = ?
        """,
        (now, str(status or ""), str(head_commit or ""), str(detail or "")[:400], now, str(member_id or "")),
    )
    if commit:
        conn.commit()


# ---------------------------------------------------------------------------
# membership reconciliation + sync worker
# ---------------------------------------------------------------------------


def _active_deployments_for_user(conn: sqlite3.Connection, owner_user_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT deployment_id, prefix, status, metadata_json, created_at
        FROM arclink_deployments
        WHERE user_id = ? AND status IN ('active', 'provisioning', 'provisioning_ready', 'running')
        ORDER BY created_at ASC, deployment_id ASC
        """,
        (str(owner_user_id or "").strip(),),
    ).fetchall()
    return [rowdict(row) for row in rows]


def default_working_path_for_deployment(deployment: Mapping[str, Any]) -> str:
    metadata = json_loads_safe(str(deployment.get("metadata_json") or "{}"))
    roots = metadata.get("state_roots")
    if isinstance(roots, Mapping):
        explicit = str(roots.get("fleet_shared") or "").strip()
        if explicit:
            return explicit
        root = str(roots.get("root") or "").strip()
        if root:
            return f"{root.rstrip('/')}/fleet-shared"
    base = str(metadata.get("state_root_base") or os.environ.get("ARCLINK_STATE_ROOT_BASE") or DEFAULT_HUB_ROOT)
    return f"{base.rstrip('/')}/{_safe_segment(str(deployment.get('deployment_id') or ''), fallback='deployment')}/fleet-shared"


def reconcile_fleet_share_membership(
    conn: sqlite3.Connection,
    *,
    owner_user_id: str,
    working_path_for: Callable[[Mapping[str, Any]], str] | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    """Make the fleet share's membership match the Captain's active agents.

    Every active deployment becomes an active member; members whose deployment is
    no longer active are deregistered. The hub is never touched here.
    """
    owner = str(owner_user_id or "").strip()
    if not owner:
        raise ArcLinkFleetShareError("fleet share reconcile requires an owner user")
    resolver = working_path_for or default_working_path_for_deployment
    active = _active_deployments_for_user(conn, owner)
    if not active:
        # No live agents: leave the share + hub in place so it survives until a
        # new agent provisions; just deregister stale members.
        members = list_fleet_share_members(conn, owner_user_id=owner, status="active")
        removed = 0
        for member in members:
            removed += remove_fleet_share_member(conn, deployment_id=str(member["deployment_id"]), commit=False)
        if commit:
            conn.commit()
        return {"share_id": "", "added": [], "removed": removed, "active_members": 0}
    share = ensure_fleet_share(conn, owner_user_id=owner, commit=False)
    share_id = str(share["share_id"])
    active_ids = {str(dep["deployment_id"]) for dep in active}
    added: list[str] = []
    for dep in active:
        working_path = resolver(dep)
        add_fleet_share_member(
            conn,
            owner_user_id=owner,
            deployment_id=str(dep["deployment_id"]),
            working_path=working_path,
            commit=False,
        )
        added.append(str(dep["deployment_id"]))
    removed = 0
    for member in list_fleet_share_members(conn, share_id=share_id, status="active"):
        if str(member["deployment_id"]) not in active_ids:
            removed += remove_fleet_share_member(conn, deployment_id=str(member["deployment_id"]), share_id=share_id, commit=False)
    if commit:
        conn.commit()
    return {"share_id": share_id, "added": added, "removed": removed, "active_members": len(active_ids)}


def process_due_fleet_share_syncs(
    conn: sqlite3.Connection,
    *,
    runner: Any | None = None,
    owner_user_id: str = "",
    author_name: str = DEFAULT_AUTHOR_NAME,
    author_email: str = DEFAULT_AUTHOR_EMAIL,
    ensure_hub: bool = True,
    ensure_working_copies: bool = True,
    limit: int = 0,
) -> list[FleetShareSyncResult]:
    """Sync every active fleet-share member's working copy with its hub."""
    git_runner = runner or SubprocessGitRunner()
    members = list_fleet_share_members(conn, owner_user_id=owner_user_id, status="active")
    if limit and limit > 0:
        members = members[: int(limit)]
    results: list[FleetShareSyncResult] = []
    hub_seen: set[str] = set()
    for member in members:
        share = conn.execute(
            "SELECT hub_ref, status FROM arclink_fleet_shares WHERE share_id = ?",
            (str(member["share_id"]),),
        ).fetchone()
        if share is None or str(share["status"] or "") != "active":
            continue
        hub_ref = str(share["hub_ref"] or "").strip()
        working_path = str(member["working_path"] or "").strip()
        deployment = str(member["deployment_id"] or "")
        if not hub_ref or not working_path:
            record_fleet_share_sync(conn, member_id=str(member["member_id"]), status="error", detail="missing hub or working path", commit=False)
            results.append(FleetShareSyncResult(deployment_id=deployment, status="error", detail="missing hub or working path"))
            continue
        try:
            if ensure_hub and hub_ref not in hub_seen:
                ensure_hub_repo(git_runner, hub_ref)
                hub_seen.add(hub_ref)
            if ensure_working_copies:
                ensure_member_working_copy(git_runner, hub_ref=hub_ref, working_path=working_path)
            result = sync_member(
                git_runner,
                working_path=working_path,
                hub_ref=hub_ref,
                deployment_id=deployment,
                author_name=author_name,
                author_email=author_email,
                message=f"ArcLink fleet sync from {deployment or 'agent'}",
            )
        except ArcLinkFleetShareError as exc:
            result = FleetShareSyncResult(deployment_id=deployment, status="error", detail=str(exc))
        record_fleet_share_sync(
            conn,
            member_id=str(member["member_id"]),
            status=result.status,
            head_commit=result.head_commit,
            detail=result.detail,
            commit=False,
        )
        results.append(result)
    conn.commit()
    return results


def sync_local_working_copy(
    runner: Any | None = None,
    *,
    hub_ref: str = "",
    working_path: str = "",
    deployment_id: str = "",
    branch: str = DEFAULT_BRANCH,
    author_name: str = DEFAULT_AUTHOR_NAME,
    author_email: str = DEFAULT_AUTHOR_EMAIL,
) -> FleetShareSyncResult:
    """Sync THIS agent's own fleet working copy with its hub — no control DB needed.

    This is the cross-machine entry point: it runs *inside an agent pod* (on a
    cron/interval), syncing the locally-mounted ``ARCLINK_FLEET_SHARED_ROOT``
    against the per-Captain hub at ``ARCLINK_FLEET_SHARE_HUB_URL``. The control
    plane separately reconciles membership; the actual git sync must run where the
    working copy physically lives, which is the agent's own filesystem.
    """
    git_runner = runner or SubprocessGitRunner()
    ref = str(hub_ref or os.environ.get("ARCLINK_FLEET_SHARE_HUB_URL") or "").strip()
    work = str(working_path or os.environ.get("ARCLINK_FLEET_SHARED_ROOT") or "").strip()
    dep = str(
        deployment_id
        or os.environ.get("ARCLINK_DEPLOYMENT_ID")
        or os.environ.get("DRIVE_OWNER_DEPLOYMENT_ID")
        or os.environ.get("ARCLINK_OWNER_DEPLOYMENT_ID")
        or ""
    ).strip()
    if not ref or not work:
        raise ArcLinkFleetShareError(
            "fleet share local sync requires ARCLINK_FLEET_SHARE_HUB_URL and ARCLINK_FLEET_SHARED_ROOT"
        )
    if "{user}" in ref:
        raise ArcLinkFleetShareError(
            "ARCLINK_FLEET_SHARE_HUB_URL must be the resolved per-Captain hub, not a {user} template"
        )
    ensure_member_working_copy(git_runner, hub_ref=ref, working_path=work, branch=branch)
    return sync_member(
        git_runner,
        working_path=work,
        hub_ref=ref,
        branch=branch,
        deployment_id=dep,
        author_name=author_name,
        author_email=author_email,
        message=f"ArcLink fleet sync from {dep or 'agent'}",
    )


def list_fleet_share_owner_ids(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT owner_user_id FROM arclink_fleet_shares WHERE status = 'active' ORDER BY owner_user_id ASC"
    ).fetchall()
    return [str(row["owner_user_id"]) for row in rows]


def reconcile_all_fleet_shares(
    conn: sqlite3.Connection,
    *,
    working_path_for: Callable[[Mapping[str, Any]], str] | None = None,
    commit: bool = True,
) -> list[dict[str, Any]]:
    """Reconcile membership for every active fleet share (control-plane, DB-only).

    Reachable from the control node (unlike per-agent git sync, which must run
    in-pod). Only reconciles Captains that already have a fleet share; share
    creation stays an explicit opt-in via ``ensure_fleet_share``.
    """
    summary: list[dict[str, Any]] = []
    for owner in list_fleet_share_owner_ids(conn):
        summary.append(reconcile_fleet_share_membership(conn, owner_user_id=owner, working_path_for=working_path_for, commit=commit))
    return summary


def run_fleet_share_cycle(
    conn: sqlite3.Connection,
    *,
    runner: Any | None = None,
    owner_user_id: str = "",
    working_path_for: Callable[[Mapping[str, Any]], str] | None = None,
    reconcile: bool = True,
    author_name: str = DEFAULT_AUTHOR_NAME,
    author_email: str = DEFAULT_AUTHOR_EMAIL,
) -> list[dict[str, Any]]:
    """Reconcile membership then sync every active fleet share (one Captain or all).

    Eventually-consistent membership: a newly active agent joins on the next
    cycle (and clones on first sync); a torn-down agent is deregistered. The hub
    is never touched by membership changes, so removing any agent is safe.
    """
    git_runner = runner or SubprocessGitRunner()
    owners = [str(owner_user_id).strip()] if owner_user_id else list_fleet_share_owner_ids(conn)
    summary: list[dict[str, Any]] = []
    for owner in owners:
        if not owner:
            continue
        if reconcile:
            reconcile_fleet_share_membership(conn, owner_user_id=owner, working_path_for=working_path_for)
        results = process_due_fleet_share_syncs(
            conn,
            runner=git_runner,
            owner_user_id=owner,
            author_name=author_name,
            author_email=author_email,
        )
        summary.append(
            {
                "owner_user_id": owner,
                "members": len(results),
                "synced": sum(1 for result in results if result.status == "synced"),
                "conflicts": sum(1 for result in results if result.status == "conflict"),
                "errors": sum(1 for result in results if result.status == "error"),
            }
        )
    return summary


# ---------------------------------------------------------------------------
# CLI (ops)
# ---------------------------------------------------------------------------


def _run_once(args) -> str:
    if args.command == "sync-local":
        result = sync_local_working_copy()
        return json_dumps_safe(
            {"deployment_id": result.deployment_id, "status": result.status, "head_commit": result.head_commit, "detail": result.detail},
            label="fleet share sync-local",
            error_cls=ArcLinkFleetShareError,
        )
    conn = connect_db(Config())
    ensure_schema(conn)
    if args.command == "reconcile":
        if getattr(args, "all", False) or not args.user:
            summary = reconcile_all_fleet_shares(conn)
        else:
            summary = reconcile_fleet_share_membership(conn, owner_user_id=args.user)
        return json_dumps_safe(summary, label="fleet share reconcile", error_cls=ArcLinkFleetShareError)
    if args.command == "sync":
        summary = run_fleet_share_cycle(conn, owner_user_id=args.user, reconcile=not args.no_reconcile)
        return json_dumps_safe(summary, label="fleet share sync", error_cls=ArcLinkFleetShareError)
    return ""


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ArcLink fleet shared folder operations")
    sub = parser.add_subparsers(dest="command", required=True)
    reconcile = sub.add_parser("reconcile", help="Reconcile fleet share membership with active agents (control-plane)")
    reconcile.add_argument("--user", default="")
    reconcile.add_argument("--all", action="store_true", help="Reconcile every Captain that has an active fleet share")
    reconcile.add_argument("--interval", type=int, default=0, help="Run repeatedly every N seconds (0 = once)")
    sync = sub.add_parser("sync", help="Reconcile membership then sync co-located working copies (control-plane)")
    sync.add_argument("--user", default="")
    sync.add_argument("--no-reconcile", action="store_true", help="Sync only; skip membership reconcile")
    sync.add_argument("--interval", type=int, default=0, help="Run repeatedly every N seconds (0 = once)")
    sync_local = sub.add_parser("sync-local", help="Sync THIS agent's own working copy with its hub (in-pod, env-driven)")
    sync_local.add_argument("--interval", type=int, default=0, help="Run repeatedly every N seconds (0 = once)")
    args = parser.parse_args(list(argv) if argv is not None else None)
    interval = int(getattr(args, "interval", 0) or 0)
    if interval > 0:
        while True:
            try:
                print(_run_once(args))
            except ArcLinkFleetShareError as exc:
                print(json_dumps_safe({"error": str(exc)}, label="fleet share loop", error_cls=ArcLinkFleetShareError))
            time.sleep(interval)
    output = _run_once(args)
    if not output:
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
