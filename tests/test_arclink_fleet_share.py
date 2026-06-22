#!/usr/bin/env python3
"""Tests for the Captain fleet shared folder (git-backed, read-write, synced)."""
from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_module(filename: str, name: str):
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    path = PYTHON_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _conn(control):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    return conn


def _seed_user(conn, control, user_id: str) -> None:
    now = control.utc_now_iso()
    conn.execute(
        "INSERT INTO arclink_users (user_id, email, status, created_at, updated_at) VALUES (?, ?, 'active', ?, ?)",
        (user_id, user_id + "@example.test", now, now),
    )


def _seed_deployment(conn, control, *, deployment_id: str, user_id: str, root: Path, status: str = "active") -> None:
    now = control.utc_now_iso()
    metadata = {"state_roots": {"root": str(root), "fleet_shared": str(root / "fleet-shared")}}
    conn.execute(
        "INSERT INTO arclink_deployments (deployment_id, user_id, prefix, status, metadata_json, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (deployment_id, user_id, deployment_id, status, json.dumps(metadata), now, now),
    )


def test_default_hub_ref_is_captain_scoped_and_agent_independent() -> None:
    fleet = load_module("arclink_fleet_share.py", "arclink_fleet_share_hub_test")
    os.environ.pop("ARCLINK_FLEET_SHARE_HUB_URL", None)
    os.environ.pop("ARCLINK_FLEET_SHARE_HUB_ROOT", None)
    ref = fleet.default_hub_ref("user_cap")
    expect(ref == "/arcdata/captains/user_cap/fleet-shared.git", ref)
    # The hub path contains the Captain id but no deployment id, so it survives
    # removing any single agent.
    expect("deployment" not in ref and "dep_" not in ref, ref)
    os.environ["ARCLINK_FLEET_SHARE_HUB_URL"] = "ssh://hub.example/{user}/fleet.git"
    try:
        templated = fleet.default_hub_ref("user_cap")
        expect(templated == "ssh://hub.example/user_cap/fleet.git", templated)
    finally:
        os.environ.pop("ARCLINK_FLEET_SHARE_HUB_URL", None)
    print("PASS test_default_hub_ref_is_captain_scoped_and_agent_independent")


def test_remote_hub_refs_are_reachability_checked() -> None:
    fleet = load_module("arclink_fleet_share.py", "arclink_fleet_share_remote_hub_test")

    class RemoteRunner:
        def __init__(self, *, ok: bool) -> None:
            self.ok = ok
            self.commands = []

        def run(self, args, *, cwd=None):
            self.commands.append(list(args))
            if self.ok:
                return fleet.GitResult(returncode=0, stdout="", stderr="")
            return fleet.GitResult(returncode=128, stdout="", stderr="no route to hub")

    ok_runner = RemoteRunner(ok=True)
    expect(fleet.ensure_hub_repo(ok_runner, "ssh://hub.example/user/fleet.git") is True, "remote hub should pass when reachable")
    expect(ok_runner.commands == [["git", "ls-remote", "ssh://hub.example/user/fleet.git"]], str(ok_runner.commands))

    try:
        fleet.ensure_hub_repo(RemoteRunner(ok=False), "git@hub.example:user/fleet.git")
        raise AssertionError("unreachable remote hub should fail")
    except fleet.ArcLinkFleetShareError as exc:
        expect("not reachable" in str(exc), str(exc))
    print("PASS test_remote_hub_refs_are_reachability_checked")


def test_ensure_share_and_membership_crud_is_idempotent() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_crud_test")
    fleet = load_module("arclink_fleet_share.py", "arclink_fleet_share_crud_test")
    conn = _conn(control)
    _seed_user(conn, control, "user_cap")
    share = fleet.ensure_fleet_share(conn, owner_user_id="user_cap")
    expect(share["status"] == "active", share["status"])
    expect(share["access_mode"] == "read-write", share["access_mode"])
    # Idempotent: a second ensure returns the same share row.
    share2 = fleet.ensure_fleet_share(conn, owner_user_id="user_cap")
    expect(share2["share_id"] == share["share_id"], "ensure_fleet_share must be idempotent")

    fleet.add_fleet_share_member(conn, owner_user_id="user_cap", deployment_id="dep_a", working_path="/w/a")
    fleet.add_fleet_share_member(conn, owner_user_id="user_cap", deployment_id="dep_b", working_path="/w/b")
    fleet.add_fleet_share_member(conn, owner_user_id="user_cap", deployment_id="dep_a", working_path="/w/a2")  # re-add updates
    active = fleet.list_fleet_share_members(conn, owner_user_id="user_cap", status="active")
    expect(len(active) == 2, f"expected 2 active members, got {len(active)}")
    paths = {m["deployment_id"]: m["working_path"] for m in active}
    expect(paths["dep_a"] == "/w/a2", paths["dep_a"])

    removed = fleet.remove_fleet_share_member(conn, deployment_id="dep_a")
    expect(removed == 1, f"expected 1 removed, got {removed}")
    active = fleet.list_fleet_share_members(conn, owner_user_id="user_cap", status="active")
    expect(len(active) == 1 and active[0]["deployment_id"] == "dep_b", str(active))
    print("PASS test_ensure_share_and_membership_crud_is_idempotent")


def test_share_and_member_insert_races_return_winning_rows() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_race_test")
    fleet = load_module("arclink_fleet_share.py", "arclink_fleet_share_race_test")
    conn = _conn(control)
    _seed_user(conn, control, "race_owner")
    real_share_id = fleet._fleet_share_id
    real_member_id = fleet._fleet_share_member_id

    def racing_share_id():
        now = control.utc_now_iso()
        conn.execute(
            """
            INSERT INTO arclink_fleet_shares (
              share_id, owner_user_id, hub_ref, folder_label, access_mode, status,
              metadata_json, created_at, updated_at
            ) VALUES ('flsh_race_winner', 'race_owner', 'triggered-hub', 'Fleet',
                      'read-write', 'active', '{}', ?, ?)
            """,
            (now, now),
        )
        return "flsh_race_loser"

    try:
        fleet._fleet_share_id = racing_share_id
        share = fleet.ensure_fleet_share(conn, owner_user_id="race_owner", hub_ref="/desired/hub.git")
    finally:
        fleet._fleet_share_id = real_share_id
    expect(share["share_id"] == "flsh_race_winner", str(share))
    expect(share["hub_ref"] == "/desired/hub.git", str(share))

    def racing_member_id():
        now = control.utc_now_iso()
        conn.execute(
            """
            INSERT INTO arclink_fleet_share_members (
              member_id, share_id, owner_user_id, deployment_id, working_path, role,
              status, joined_at, metadata_json, created_at, updated_at
            ) VALUES ('flsm_race_winner', ?, 'race_owner', 'dep_race', '/old/path',
                      'member', 'active', ?, '{}', ?, ?)
            """,
            (share["share_id"], now, now, now),
        )
        return "flsm_race_loser"

    try:
        fleet._fleet_share_member_id = racing_member_id
        member = fleet.add_fleet_share_member(
            conn,
            owner_user_id="race_owner",
            deployment_id="dep_race",
            working_path="/new/path",
            role="lead",
        )
    finally:
        fleet._fleet_share_member_id = real_member_id
    expect(member["member_id"] == "flsm_race_winner", str(member))
    expect(member["working_path"] == "/new/path" and member["role"] == "lead", str(member))
    print("PASS test_share_and_member_insert_races_return_winning_rows")


def test_remove_fleet_share_member_rejects_empty_deployment() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_empty_member_remove_test")
    fleet = load_module("arclink_fleet_share.py", "arclink_fleet_share_empty_member_remove_test")
    conn = _conn(control)
    try:
        fleet.remove_fleet_share_member(conn, deployment_id="")
        raise AssertionError("empty deployment id should be rejected")
    except fleet.ArcLinkFleetShareError:
        pass
    print("PASS test_remove_fleet_share_member_rejects_empty_deployment")


def test_reconcile_tracks_active_agents_and_deregisters_removed_without_touching_hub() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_reconcile_test")
    fleet = load_module("arclink_fleet_share.py", "arclink_fleet_share_reconcile_test")
    conn = _conn(control)
    tmp = Path(tempfile.mkdtemp())
    _seed_user(conn, control, "user_cap")
    _seed_deployment(conn, control, deployment_id="dep_a", user_id="user_cap", root=tmp / "a")
    _seed_deployment(conn, control, deployment_id="dep_b", user_id="user_cap", root=tmp / "b")
    summary = fleet.reconcile_fleet_share_membership(conn, owner_user_id="user_cap")
    expect(summary["active_members"] == 2, str(summary))
    active = {m["deployment_id"] for m in fleet.list_fleet_share_members(conn, owner_user_id="user_cap", status="active")}
    expect(active == {"dep_a", "dep_b"}, str(active))
    member = fleet.list_fleet_share_members(conn, owner_user_id="user_cap", status="active")[0]
    expect(member["working_path"].endswith("/fleet-shared"), member["working_path"])

    # Tear down the first agent; reconcile must deregister it and keep the share.
    conn.execute("UPDATE arclink_deployments SET status = 'torn_down' WHERE deployment_id = 'dep_a'")
    conn.commit()
    summary = fleet.reconcile_fleet_share_membership(conn, owner_user_id="user_cap")
    active = {m["deployment_id"] for m in fleet.list_fleet_share_members(conn, owner_user_id="user_cap", status="active")}
    expect(active == {"dep_b"}, f"removing dep_a should leave only dep_b: {active}")
    expect(summary["removed"] == 1, str(summary))
    # The fleet share itself still exists (independent of any single agent).
    expect(fleet.get_fleet_share_for_user(conn, "user_cap")["status"] == "active", "share must survive agent removal")
    print("PASS test_reconcile_tracks_active_agents_and_deregisters_removed_without_touching_hub")


def test_sync_engine_converges_read_write_across_agents_and_flags_conflicts() -> None:
    fleet = load_module("arclink_fleet_share.py", "arclink_fleet_share_sync_test")
    tmp = Path(tempfile.mkdtemp())
    hub = str(tmp / "hub.git")
    a = str(tmp / "agent_a")
    b = str(tmp / "agent_b")
    runner = fleet.SubprocessGitRunner()
    fleet.ensure_hub_repo(runner, hub)
    fleet.ensure_member_working_copy(runner, hub_ref=hub, working_path=a)
    fleet.ensure_member_working_copy(runner, hub_ref=hub, working_path=b)

    (Path(a) / "plan.md").write_text("from agent a\n", encoding="utf-8")
    res = fleet.sync_member(runner, working_path=a, hub_ref=hub, deployment_id="dep_a")
    expect(res.status == "synced" and res.pushed, str(res))

    res = fleet.sync_member(runner, working_path=b, hub_ref=hub, deployment_id="dep_b")
    expect(res.status == "synced" and res.pulled, str(res))
    expect((Path(b) / "plan.md").read_text(encoding="utf-8").strip() == "from agent a", "agent b should receive agent a's file")

    # Read-write from both sides: b writes, a receives.
    (Path(b) / "notes.md").write_text("from agent b\n", encoding="utf-8")
    fleet.sync_member(runner, working_path=b, hub_ref=hub, deployment_id="dep_b")
    fleet.sync_member(runner, working_path=a, hub_ref=hub, deployment_id="dep_a")
    expect((Path(a) / "notes.md").exists(), "agent a should receive agent b's file")

    # Conflicting concurrent edits: first wins, second is flagged (never clobbered).
    (Path(a) / "plan.md").write_text("a rewrite\n", encoding="utf-8")
    (Path(b) / "plan.md").write_text("b rewrite\n", encoding="utf-8")
    res_a = fleet.sync_member(runner, working_path=a, hub_ref=hub, deployment_id="dep_a")
    res_b = fleet.sync_member(runner, working_path=b, hub_ref=hub, deployment_id="dep_b")
    expect(res_a.status == "synced", str(res_a))
    expect(res_b.status == "conflict", str(res_b))
    # b's local edit must be preserved (rebase aborted, not clobbered).
    expect((Path(b) / "plan.md").read_text(encoding="utf-8").strip() == "b rewrite", "conflict must not clobber local edits")
    print("PASS test_sync_engine_converges_read_write_across_agents_and_flags_conflicts")


def test_member_working_copy_seeds_fleet_shared_resource_layout() -> None:
    fleet = load_module("arclink_fleet_share.py", "arclink_fleet_share_layout_test")
    tmp = Path(tempfile.mkdtemp())
    hub = str(tmp / "hub.git")
    working = tmp / "agent_a"
    runner = fleet.SubprocessGitRunner()
    fleet.ensure_hub_repo(runner, hub)
    fleet.ensure_member_working_copy(runner, hub_ref=hub, working_path=str(working))
    # Fleet holds ONLY the shared libraries; per-agent work folders (Projects, Repos,
    # Research) must NOT be seeded into the shared root (no Fleet/Workspace duplication).
    expected = {"Agents_KB", "Agents_Skills", "Agents_Plugins"}
    for dirname in expected:
        readme = working / dirname / "README.md"
        expect(readme.is_file(), f"missing Fleet layout readme: {dirname}")
    for absent in ("Projects", "Repos", "Research"):
        expect(not (working / absent).exists(), f"Fleet must not seed per-agent work folder: {absent}")
    fleet.sync_member(runner, working_path=str(working), hub_ref=hub, deployment_id="dep_a")
    clone = tmp / "agent_b"
    fleet.ensure_member_working_copy(runner, hub_ref=hub, working_path=str(clone))
    fleet.sync_member(runner, working_path=str(clone), hub_ref=hub, deployment_id="dep_b")
    for dirname in expected:
        expect((clone / dirname / "README.md").is_file(), f"Fleet layout should sync to peer: {dirname}")
    print("PASS test_member_working_copy_seeds_fleet_shared_resource_layout")


def test_worker_cycle_reconciles_and_syncs_all_agents() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_worker_test")
    fleet = load_module("arclink_fleet_share.py", "arclink_fleet_share_worker_test")
    conn = _conn(control)
    tmp = Path(tempfile.mkdtemp())
    hub = str(tmp / "hub.git")
    _seed_user(conn, control, "user_cap")
    _seed_deployment(conn, control, deployment_id="dep_a", user_id="user_cap", root=tmp / "a")
    _seed_deployment(conn, control, deployment_id="dep_b", user_id="user_cap", root=tmp / "b")
    fleet.ensure_fleet_share(conn, owner_user_id="user_cap", hub_ref=hub)

    # Seed one agent's working copy with content before the cycle runs.
    runner = fleet.SubprocessGitRunner()
    summary = fleet.run_fleet_share_cycle(conn, runner=runner, owner_user_id="user_cap")
    expect(len(summary) == 1 and summary[0]["members"] == 2, str(summary))
    expect(summary[0]["errors"] == 0, str(summary))

    # Both working copies now exist and are git repos pointed at the hub.
    for dep in ("a", "b"):
        expect((tmp / dep / "fleet-shared" / ".git").exists(), f"agent {dep} working copy should be cloned")

    # Agent A writes, two cycles propagate to agent B (read-write, synced).
    (tmp / "a" / "fleet-shared" / "shared.txt").write_text("hello fleet\n", encoding="utf-8")
    fleet.run_fleet_share_cycle(conn, runner=runner, owner_user_id="user_cap")
    fleet.run_fleet_share_cycle(conn, runner=runner, owner_user_id="user_cap")
    expect((tmp / "b" / "fleet-shared" / "shared.txt").exists(), "agent b should converge to agent a's write")

    members = fleet.list_fleet_share_members(conn, owner_user_id="user_cap", status="active")
    expect(all(m["last_sync_status"] in {"synced"} for m in members), str([m["last_sync_status"] for m in members]))
    print("PASS test_worker_cycle_reconciles_and_syncs_all_agents")


def test_corrupt_working_copy_is_quarantined_and_recloned() -> None:
    import shutil
    fleet = load_module("arclink_fleet_share.py", "arclink_fleet_share_recover_test")
    tmp = Path(tempfile.mkdtemp())
    hub = str(tmp / "hub.git")
    a = str(tmp / "agent_a")
    runner = fleet.SubprocessGitRunner()
    fleet.ensure_hub_repo(runner, hub)
    fleet.ensure_member_working_copy(runner, hub_ref=hub, working_path=a)
    (Path(a) / "keep.txt").write_text("seed\n", encoding="utf-8")
    expect(fleet.sync_member(runner, working_path=a, hub_ref=hub, deployment_id="a").status == "synced", "seed sync")

    # Partially corrupt .git (contents removed, dir remains) -> must self-heal.
    git_dir = Path(a) / ".git"
    for child in list(git_dir.iterdir()):
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    (Path(a) / "draft-unsynced.txt").write_text("local draft\n", encoding="utf-8")
    expect(fleet._is_valid_git_repo(runner, Path(a)) is False, "repo should read as corrupt")
    fleet.ensure_member_working_copy(runner, hub_ref=hub, working_path=a)
    expect(fleet._is_valid_git_repo(runner, Path(a)) is True, "repo should be valid after recovery")
    expect((Path(a) / "keep.txt").exists(), "re-clone should restore hub content")
    expect((Path(a) / "draft-unsynced.txt").read_text(encoding="utf-8") == "local draft\n", "unsynced local edit should be restored")
    recovery = Path(a) / "ArcLink_Corrupt_Recovery"
    expect((recovery / "agent_a.corrupt" / "draft-unsynced.txt").exists(), "quarantined files should be visible in recovery folder")
    quarantined = list(tmp.glob("agent_a.corrupt*"))
    expect(len(quarantined) == 1, f"corrupt copy should be preserved aside: {quarantined}")
    expect(fleet.sync_member(runner, working_path=a, hub_ref=hub, deployment_id="a").status == "synced", "sync works after recovery")
    print("PASS test_corrupt_working_copy_is_quarantined_and_recloned")


def test_git_arg_guard_rejects_option_injection() -> None:
    fleet = load_module("arclink_fleet_share.py", "arclink_fleet_share_argguard_test")
    runner = fleet.SubprocessGitRunner()
    for bad in ("--upload-pack=touch /tmp/x", "-x", "--bare"):
        try:
            fleet.ensure_hub_repo(runner, bad)
            raise AssertionError(f"hub ref {bad!r} should be rejected")
        except fleet.ArcLinkFleetShareError:
            pass
    try:
        fleet.ensure_hub_repo(runner, "ext::sh -c touch /tmp/arclink-fleet-pwn")
        raise AssertionError("git remote-helper syntax should be rejected")
    except fleet.ArcLinkFleetShareError:
        pass
    try:
        fleet.ensure_member_working_copy(runner, hub_ref="/safe/hub.git", working_path="-evil")
        raise AssertionError("working path '-evil' should be rejected")
    except fleet.ArcLinkFleetShareError:
        pass
    try:
        fleet.sync_member(runner, hub_ref="-evil", working_path="/tmp/fleet-share-test")
        raise AssertionError("sync_member should reject option-looking hub refs")
    except fleet.ArcLinkFleetShareError:
        pass
    print("PASS test_git_arg_guard_rejects_option_injection")


def test_sync_member_surfaces_commit_failure_without_pushing() -> None:
    fleet = load_module("arclink_fleet_share.py", "arclink_fleet_share_commit_failure_test")
    tmp = Path(tempfile.mkdtemp())
    hub = str(tmp / "hub.git")
    work = str(tmp / "agent_a")
    base = fleet.SubprocessGitRunner()
    fleet.ensure_hub_repo(base, hub)
    fleet.ensure_member_working_copy(base, hub_ref=hub, working_path=work)
    (Path(work) / "blocked.txt").write_text("local edit\n", encoding="utf-8")

    class CommitFailRunner:
        def run(self, args, *, cwd=None):
            if "commit" in list(args):
                return fleet.GitResult(returncode=1, stdout="", stderr="commit blocked by test")
            return base.run(args, cwd=cwd)

    result = fleet.sync_member(CommitFailRunner(), hub_ref=hub, working_path=work, deployment_id="dep_a")
    expect(result.status == "error", str(result))
    expect("commit blocked" in result.detail, str(result))
    refs = base.run(["git", "show-ref"], cwd=hub)
    expect(refs.returncode != 0 or "refs/heads/main" not in refs.stdout, refs.stdout)
    print("PASS test_sync_member_surfaces_commit_failure_without_pushing")


def test_sync_local_is_env_driven_and_needs_no_db() -> None:
    fleet = load_module("arclink_fleet_share.py", "arclink_fleet_share_local_test")
    tmp = Path(tempfile.mkdtemp())
    hub = str(tmp / "hub.git")
    a = str(tmp / "agent_a")
    b = str(tmp / "agent_b")
    runner = fleet.SubprocessGitRunner()
    fleet.ensure_hub_repo(runner, hub)
    fleet.ensure_member_working_copy(runner, hub_ref=hub, working_path=a)
    (Path(a) / "fleet.txt").write_text("seed from a\n", encoding="utf-8")
    fleet.sync_member(runner, working_path=a, hub_ref=hub, deployment_id="a")

    saved = {k: os.environ.get(k) for k in ("ARCLINK_FLEET_SHARE_HUB_URL", "ARCLINK_FLEET_SHARED_ROOT", "ARCLINK_DEPLOYMENT_ID")}
    try:
        os.environ["ARCLINK_FLEET_SHARE_HUB_URL"] = hub
        os.environ["ARCLINK_FLEET_SHARED_ROOT"] = b
        os.environ["ARCLINK_DEPLOYMENT_ID"] = "dep_b"
        result = fleet.sync_local_working_copy(runner)
        expect(result.status == "synced", str(result))
        expect(result.deployment_id == "dep_b", result.deployment_id)
        expect((Path(b) / "fleet.txt").exists(), "sync-local should clone + pull the hub content")
        # A {user} template must be rejected (the pod needs the resolved hub).
        os.environ["ARCLINK_FLEET_SHARE_HUB_URL"] = "ssh://hub/{user}/fleet.git"
        try:
            fleet.sync_local_working_copy(runner)
            raise AssertionError("templated hub URL should be rejected for in-pod sync")
        except fleet.ArcLinkFleetShareError:
            pass
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    print("PASS test_sync_local_is_env_driven_and_needs_no_db")


def test_sync_local_rejects_overbroad_env_working_root() -> None:
    fleet = load_module("arclink_fleet_share.py", "arclink_fleet_share_local_root_guard_test")

    class NoGitRunner:
        def run(self, args, *, cwd=None):
            raise AssertionError(f"git should not run for unsafe root: {args}")

    saved = {k: os.environ.get(k) for k in ("ARCLINK_FLEET_SHARE_HUB_URL", "ARCLINK_FLEET_SHARED_ROOT", "ARCLINK_DEPLOYMENT_ID")}
    try:
        os.environ["ARCLINK_FLEET_SHARE_HUB_URL"] = "/tmp/arclink-fleet-hub.git"
        os.environ["ARCLINK_FLEET_SHARED_ROOT"] = str(REPO)
        os.environ["ARCLINK_DEPLOYMENT_ID"] = "dep_bad"
        try:
            fleet.sync_local_working_copy(NoGitRunner())
            raise AssertionError("repo root must not be accepted as the fleet shared root")
        except fleet.ArcLinkFleetShareError as exc:
            expect("allowed fleet state root" in str(exc), str(exc))
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    print("PASS test_sync_local_rejects_overbroad_env_working_root")


def test_reconcile_all_covers_every_captain_with_an_active_share() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_all_test")
    fleet = load_module("arclink_fleet_share.py", "arclink_fleet_share_all_test")
    conn = _conn(control)
    tmp = Path(tempfile.mkdtemp())
    for cap in ("cap_a", "cap_b"):
        _seed_user(conn, control, cap)
        _seed_deployment(conn, control, deployment_id=f"dep_{cap}", user_id=cap, root=tmp / cap)
        fleet.ensure_fleet_share(conn, owner_user_id=cap)
    # cap_c has deployments but no fleet share -> reconcile_all must NOT auto-create one.
    _seed_user(conn, control, "cap_c")
    _seed_deployment(conn, control, deployment_id="dep_cap_c", user_id="cap_c", root=tmp / "cap_c")
    summary = fleet.reconcile_all_fleet_shares(conn)
    expect(len(summary) == 2, f"reconcile_all should cover the 2 Captains with shares: {summary}")
    expect(fleet.get_fleet_share_for_user(conn, "cap_c") == {}, "reconcile_all must not auto-create a share for cap_c")
    for cap in ("cap_a", "cap_b"):
        active = fleet.list_fleet_share_members(conn, owner_user_id=cap, status="active")
        expect(len(active) == 1, f"{cap} should have 1 member: {active}")
    print("PASS test_reconcile_all_covers_every_captain_with_an_active_share")


def test_control_plane_cli_uses_env_config_for_db_connection() -> None:
    fleet = load_module("arclink_fleet_share.py", "arclink_fleet_share_cli_config_test")
    tmp = Path(tempfile.mkdtemp())
    config_path = tmp / "arclink.env"
    config_path.write_text(
        "\n".join(
            [
                f"ARCLINK_REPO_DIR={REPO}",
                f"ARCLINK_PRIV_DIR={tmp / 'priv'}",
                f"STATE_DIR={tmp / 'state'}",
                f"RUNTIME_DIR={tmp / 'runtime'}",
                f"VAULT_DIR={tmp / 'vault'}",
                f"ARCLINK_DB_PATH={tmp / 'state' / 'control.sqlite3'}",
            ]
        ),
        encoding="utf-8",
    )
    old_env = dict(os.environ)
    try:
        os.environ.clear()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = fleet.main(["reconcile", "--all"])
        expect(rc == 0, f"expected reconcile CLI success, got {rc}: {stdout.getvalue()}")
        expect(json.loads(stdout.getvalue()) == {"command": "reconcile", "shares": []}, stdout.getvalue())
        expect((tmp / "state" / "control.sqlite3").is_file(), "CLI should create/connect to the env-configured DB")
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    print("PASS test_control_plane_cli_uses_env_config_for_db_connection")


def main() -> int:
    test_default_hub_ref_is_captain_scoped_and_agent_independent()
    test_remote_hub_refs_are_reachability_checked()
    test_ensure_share_and_membership_crud_is_idempotent()
    test_share_and_member_insert_races_return_winning_rows()
    test_remove_fleet_share_member_rejects_empty_deployment()
    test_reconcile_tracks_active_agents_and_deregisters_removed_without_touching_hub()
    test_sync_engine_converges_read_write_across_agents_and_flags_conflicts()
    test_member_working_copy_seeds_fleet_shared_resource_layout()
    test_worker_cycle_reconciles_and_syncs_all_agents()
    test_corrupt_working_copy_is_quarantined_and_recloned()
    test_git_arg_guard_rejects_option_injection()
    test_sync_member_surfaces_commit_failure_without_pushing()
    test_sync_local_is_env_driven_and_needs_no_db()
    test_sync_local_rejects_overbroad_env_working_root()
    test_reconcile_all_covers_every_captain_with_an_active_share()
    test_control_plane_cli_uses_env_config_for_db_connection()
    print("PASS all 17 ArcLink fleet-share tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
