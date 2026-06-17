#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
ROOT_CAPTURE_ENV = {"ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE": "1"}
os.environ.setdefault("ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED", "accepted")


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


def memory_db(control):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    return conn


class PermissiveSecretResolver:
    def __init__(self, executor_mod):
        self.executor_mod = executor_mod
        self.resolved = []

    def materialize(self, secret_ref: str, target_path: str):
        result = self.executor_mod.ResolvedSecretFile(secret_ref=secret_ref, target_path=target_path)
        self.resolved.append(result)
        return result


def fake_executor(executor_mod):
    return executor_mod.ArcLinkExecutor(
        config=executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
        secret_resolver=PermissiveSecretResolver(executor_mod),
    )


def seed_deployment(control, conn, tmp: Path):
    source_base = tmp / "source"
    target_base = tmp / "target"
    source_roots = load_module("arclink_provisioning.py", "arclink_provisioning_pod_seed").render_arclink_state_roots(
        deployment_id="dep_1",
        prefix="captain-one",
        state_root_base=str(source_base),
    )
    source_root = Path(source_roots["root"])
    (source_root / "vault").mkdir(parents=True)
    (source_root / "vault" / "mission.md").write_text("captain state\n", encoding="utf-8")
    (source_root / "state" / "memory").mkdir(parents=True)
    (source_root / "state" / "memory" / "recall.json").write_text('{"ok": true}\n', encoding="utf-8")
    (source_root / "state" / "hermes-home" / "sessions").mkdir(parents=True)
    (source_root / "state" / "hermes-home" / "sessions" / "session.json").write_text('{"turns": 3}\n', encoding="utf-8")
    (source_root / "config").mkdir(parents=True)
    (source_root / "config" / "config.yaml").write_text("agent: captain-one\n", encoding="utf-8")

    now = control.utc_now_iso()
    control.upsert_arclink_user(conn, user_id="user_1", email="captain@example.test", entitlement_state="paid")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_1",
        user_id="user_1",
        prefix="captain-one",
        base_domain="example.test",
        status="active",
        metadata={
            "state_roots": source_roots,
            "state_root_base": str(source_base),
            "base_domain": "example.test",
            "secret_refs": {
                "telegram_bot_token": "secret://arclink/telegram/dep_1",
                "discord_bot_token": "secret://arclink/discord/dep_1",
            },
        },
    )
    conn.execute(
        """
        INSERT INTO arclink_fleet_hosts (
          host_id, hostname, status, capacity_slots, observed_load, metadata_json, created_at, updated_at
        ) VALUES
          ('host_source', 'source.example.test', 'active', 10, 1, ?, ?, ?),
          ('host_target', 'target.example.test', 'active', 10, 0, ?, ?, ?)
        """,
        (
            json.dumps({"state_root_base": str(source_base), "edge_target": "source-edge.example.test"}),
            now,
            now,
            json.dumps({"state_root_base": str(target_base), "edge_target": "target-edge.example.test"}),
            now,
            now,
        ),
    )
    conn.execute(
        """
        INSERT INTO arclink_deployment_placements (placement_id, deployment_id, host_id, status, placed_at)
        VALUES ('plc_source', 'dep_1', 'host_source', 'active', ?)
        """,
        (now,),
    )
    conn.execute(
        """
        INSERT INTO arclink_dns_records (record_id, deployment_id, hostname, record_type, target, status, created_at, updated_at)
        VALUES ('dns_dep_1_dashboard', 'dep_1', 'captain-one.example.test', 'CNAME', 'source-edge.example.test', 'active', ?, ?)
        """,
        (now, now),
    )
    conn.commit()
    return source_roots, source_base, target_base


def test_migration_captures_materializes_verifies_and_replays() -> None:
    control = load_module("arclink_control.py", "arclink_control_pod_migration_success")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_pod_migration_success")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_success")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        source_roots, _, target_base = seed_deployment(control, conn, Path(tmpdir))
        outside = Path(tmpdir) / "outside.txt"
        outside.write_text("outside state\n", encoding="utf-8")
        (Path(source_roots["root"]) / "vault" / "outside-link").symlink_to(outside)
        target_root = target_base / "dep_1-captain-one"
        (target_root / "vault").mkdir(parents=True)
        (target_root / "vault" / "stale.md").write_text("stale target state\n", encoding="utf-8")
        result = migration.migrate_pod(
            conn,
            executor=fake_executor(executor_mod),
            deployment_id="dep_1",
            target_machine_id="host_target",
            migration_id="mig_111111111111111111111111",
            reason="operator moving Pod to new host",
            verifier=lambda _conn, _row, _intent: {"healthy": True, "session_continuity": "checked"},
            retention_days=7,
            env=ROOT_CAPTURE_ENV,
        )
        expect(result["status"] == "succeeded", str(result))
        target_file = target_base / "dep_1-captain-one" / "vault" / "mission.md"
        expect(target_file.read_text(encoding="utf-8") == "captain state\n", str(target_file))
        row = conn.execute("SELECT * FROM arclink_pod_migrations WHERE migration_id = ?", (result["migration_id"],)).fetchone()
        manifest = json.loads(row["capture_manifest_json"])
        expect("root" not in manifest, str(manifest))
        paths = {item["path"]: item for item in manifest["files"]}
        expect(paths["vault/mission.md"]["boundary"] == "vault", str(paths))
        expect(len(paths["vault/mission.md"]["sha256"]) == 64, str(paths["vault/mission.md"]))
        expect(paths["vault/outside-link"]["type"] == "symlink", str(paths["vault/outside-link"]))
        target_link = target_root / "vault" / "outside-link"
        expect(target_link.is_symlink() and os.readlink(target_link) == str(outside), "symlink should be preserved")
        expect(not (target_root / "vault" / "stale.md").exists(), "materialize should clear stale target files")
        placements = {
            row["placement_id"]: row["status"]
            for row in conn.execute("SELECT placement_id, status FROM arclink_deployment_placements").fetchall()
        }
        expect(placements["plc_source"] == "removed", str(placements))
        expect(placements[result["target_placement_id"]] == "active", str(placements))
        replay = migration.migrate_pod(
            conn,
            executor=fake_executor(executor_mod),
            deployment_id="dep_1",
            target_machine_id="host_target",
            migration_id="mig_111111111111111111111111",
            verifier=lambda _conn, _row, _intent: {"healthy": True},
        )
        expect(replay["idempotent_replay"] is True and replay["status"] == "succeeded", str(replay))
        try:
            migration.migrate_pod(
                conn,
                executor=fake_executor(executor_mod),
                deployment_id="dep_1",
                target_machine_id="host_source",
                migration_id="mig_111111111111111111111111",
            )
        except migration.ArcLinkPodMigrationError as exc:
            expect("another target" in str(exc), str(exc))
        else:
            raise AssertionError("expected changed migration target to fail idempotency planning")
    print("PASS test_migration_captures_materializes_verifies_and_replays")


def test_migration_capture_requires_explicit_root_opt_in() -> None:
    control = load_module("arclink_control.py", "arclink_control_pod_migration_root_opt_in")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_pod_migration_root_opt_in")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_root_opt_in")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        seed_deployment(control, conn, Path(tmpdir))
        try:
            migration.migrate_pod(
                conn,
                executor=fake_executor(executor_mod),
                deployment_id="dep_1",
                target_machine_id="host_target",
                migration_id="mig_666666666666666666666666",
                verifier=lambda _conn, _row, _intent: {"healthy": True},
            )
        except migration.ArcLinkPodMigrationError as exc:
            expect("ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE=1" in str(exc), str(exc))
        else:
            raise AssertionError("expected non-dry-run migration capture to require explicit root opt-in")
        rows = conn.execute("SELECT COUNT(*) AS c FROM arclink_pod_migrations").fetchone()
        expect(int(rows["c"]) == 0, str(dict(rows)))
    print("PASS test_migration_capture_requires_explicit_root_opt_in")


def test_migration_capture_requires_helper_in_docker_mode() -> None:
    control = load_module("arclink_control.py", "arclink_control_pod_migration_helper_required")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_pod_migration_helper_required")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_helper_required")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        seed_deployment(control, conn, Path(tmpdir))
        try:
            migration.migrate_pod(
                conn,
                executor=fake_executor(executor_mod),
                deployment_id="dep_1",
                target_machine_id="host_target",
                migration_id="mig_888888888888888888888888",
                verifier=lambda _conn, _row, _intent: {"healthy": True},
                env={**ROOT_CAPTURE_ENV, "ARCLINK_DOCKER_MODE": "1"},
            )
        except migration.ArcLinkPodMigrationError as exc:
            expect("ARCLINK_MIGRATION_CAPTURE_HELPER_URL" in str(exc), str(exc))
        else:
            raise AssertionError("expected Docker-mode migration capture to require the helper URL/token")
        rows = conn.execute("SELECT COUNT(*) AS c FROM arclink_pod_migrations").fetchone()
        expect(int(rows["c"]) == 0, str(dict(rows)))
    print("PASS test_migration_capture_requires_helper_in_docker_mode")


def test_migration_capture_uses_helper_when_configured() -> None:
    control = load_module("arclink_control.py", "arclink_control_pod_migration_helper_used")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_pod_migration_helper_used")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_helper_used")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        source_roots, _, target_base = seed_deployment(control, conn, Path(tmpdir))
        calls: list[str] = []
        original_helper = migration._run_migration_capture_helper

        def fake_helper(operation, *, conn, row, env):
            calls.append(str(operation))
            if operation == "capture":
                return migration._copy_capture(Path(str(row["source_state_root"])), Path(str(row["capture_dir"])))
            if operation == "materialize":
                migration._materialize_capture(Path(str(row["capture_dir"])), Path(str(row["target_state_root"])))
                return {"status": "materialized"}
            raise AssertionError(f"unexpected helper operation {operation}")

        migration._run_migration_capture_helper = fake_helper
        try:
            result = migration.migrate_pod(
                conn,
                executor=fake_executor(executor_mod),
                deployment_id="dep_1",
                target_machine_id="host_target",
                migration_id="mig_999999999999999999999999",
                verifier=lambda _conn, _row, _intent: {"healthy": True},
                env={
                    **ROOT_CAPTURE_ENV,
                    "ARCLINK_DOCKER_MODE": "1",
                    "ARCLINK_MIGRATION_CAPTURE_HELPER_URL": "http://migration-capture-helper:8914",
                    "ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN": "helper-token",
                },
            )
        finally:
            migration._run_migration_capture_helper = original_helper
        expect(result["status"] == "succeeded", str(result))
        expect(calls == ["capture", "materialize"], str(calls))
        expect((target_base / "dep_1-captain-one" / "vault" / "mission.md").read_text(encoding="utf-8") == "captain state\n", str(target_base))
        expect((Path(source_roots["root"]) / "vault" / "mission.md").exists(), "source state should be retained after helper capture")
    print("PASS test_migration_capture_uses_helper_when_configured")


def test_migration_capture_helper_rejects_raw_commands_and_unscoped_paths() -> None:
    helper = load_module("arclink_migration_capture_helper.py", "arclink_migration_capture_helper_contract")
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        old_base = os.environ.get("ARCLINK_STATE_ROOT_BASE")
        os.environ["ARCLINK_STATE_ROOT_BASE"] = str(root)
        source_root = root / "source" / "dep_1-captain-one"
        target_root = root / "target" / "dep_1-captain-one"
        capture_dir = root / "target" / ".migrations" / "mig_aaaaaaaaaaaaaaaaaaaaaaaa"
        (source_root / "vault").mkdir(parents=True)
        (source_root / "vault" / "mission.md").write_text("captain state\n", encoding="utf-8")
        request = {
            "operation": "capture",
            "deployment_id": "dep_1",
            "prefix": "captain-one",
            "migration_id": "mig_aaaaaaaaaaaaaaaaaaaaaaaa",
            "source_state_root": str(source_root),
            "target_state_root": str(target_root),
            "capture_dir": str(capture_dir),
        }
        try:
            ok, payload = helper.run_migration_capture_request(dict(request))
            expect(ok is True and payload["file_count"] == 1, str(payload))
            ok, payload = helper.run_migration_capture_request({**request, "operation": "materialize"})
            expect(ok is True and payload["status"] == "materialized", str(payload))
            expect((target_root / "vault" / "mission.md").read_text(encoding="utf-8") == "captain state\n", str(target_root))

            ok, error = helper.run_migration_capture_request({**request, "cmd": ["cp", "-a"]})
            expect(ok is False and "does not accept raw commands" in str(error), str(error))
            ok, error = helper.run_migration_capture_request({**request, "source_state_root": str(root / "source" / "not-this-deployment")})
            expect(ok is False and "source root must be deployment-scoped" in str(error), str(error))
            ok, error = helper.run_migration_capture_request({**request, "capture_dir": str(root / "outside" / "mig_aaaaaaaaaaaaaaaaaaaaaaaa")})
            expect(ok is False and "capture directory must stay under the target state-root base" in str(error), str(error))
        finally:
            if old_base is None:
                os.environ.pop("ARCLINK_STATE_ROOT_BASE", None)
            else:
                os.environ["ARCLINK_STATE_ROOT_BASE"] = old_base
    print("PASS test_migration_capture_helper_rejects_raw_commands_and_unscoped_paths")


def test_migration_capture_helper_rejects_paths_outside_configured_state_root_base() -> None:
    helper = load_module("arclink_migration_capture_helper.py", "arclink_migration_capture_helper_configured_base")
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        allowed = root / "allowed"
        outside = root / "outside"
        source_root = allowed / "dep_1-captain-one"
        target_root = allowed / "dep_1-captain-one"
        capture_dir = allowed / ".migrations" / "mig_aaaaaaaaaaaaaaaaaaaaaaaa"
        (source_root / "vault").mkdir(parents=True)
        (source_root / "vault" / "mission.md").write_text("captain state\n", encoding="utf-8")
        request = {
            "operation": "capture",
            "deployment_id": "dep_1",
            "prefix": "captain-one",
            "migration_id": "mig_aaaaaaaaaaaaaaaaaaaaaaaa",
            "source_state_root": str(source_root),
            "target_state_root": str(target_root),
            "capture_dir": str(capture_dir),
        }
        old_base = os.environ.get("ARCLINK_STATE_ROOT_BASE")
        original_copy = helper._copy_capture
        original_materialize = helper._materialize_capture
        calls: list[str] = []

        def fail_copy(_source_root, _capture_dir):
            calls.append("copy")
            raise AssertionError("copy should not start for paths outside ARCLINK_STATE_ROOT_BASE")

        def fail_materialize(_capture_dir, _target_root):
            calls.append("materialize")
            raise AssertionError("materialize should not start for paths outside ARCLINK_STATE_ROOT_BASE")

        os.environ["ARCLINK_STATE_ROOT_BASE"] = str(allowed)
        helper._copy_capture = fail_copy
        helper._materialize_capture = fail_materialize
        try:
            cases = [
                (
                    "source_state_root",
                    str(outside / "dep_1-captain-one"),
                    "source root must stay under the configured state-root base",
                    "capture",
                ),
                (
                    "target_state_root",
                    str(outside / "dep_1-captain-one"),
                    "target root must stay under the configured state-root base",
                    "capture",
                ),
                (
                    "capture_dir",
                    str(outside / ".migrations" / "mig_aaaaaaaaaaaaaaaaaaaaaaaa"),
                    "capture directory must stay under the configured state-root base",
                    "capture",
                ),
                (
                    "capture_dir",
                    str(outside / ".migrations" / "mig_aaaaaaaaaaaaaaaaaaaaaaaa"),
                    "capture directory must stay under the configured state-root base",
                    "materialize",
                ),
            ]
            for field, value, expected, operation in cases:
                ok, error = helper.run_migration_capture_request({**request, "operation": operation, field: value})
                expect(ok is False and expected in str(error), f"{field} should fail closed: {error}")
            expect(calls == [], f"helper started file work before configured-base validation: {calls}")
        finally:
            helper._copy_capture = original_copy
            helper._materialize_capture = original_materialize
            if old_base is None:
                os.environ.pop("ARCLINK_STATE_ROOT_BASE", None)
            else:
                os.environ["ARCLINK_STATE_ROOT_BASE"] = old_base
    print("PASS test_migration_capture_helper_rejects_paths_outside_configured_state_root_base")


def test_migration_capture_rejects_unscoped_source_root() -> None:
    control = load_module("arclink_control.py", "arclink_control_pod_migration_root_scope")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_pod_migration_root_scope")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_root_scope")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        source_roots, _, _ = seed_deployment(control, conn, Path(tmpdir))
        bad_roots = dict(source_roots)
        bad_roots["root"] = str(Path(tmpdir) / "source" / "not-the-deployment-root")
        deployment = conn.execute("SELECT metadata_json FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()
        metadata = json.loads(deployment["metadata_json"])
        metadata["state_roots"] = bad_roots
        conn.execute(
            "UPDATE arclink_deployments SET metadata_json = ? WHERE deployment_id = 'dep_1'",
            (json.dumps(metadata, sort_keys=True),),
        )
        conn.commit()
        try:
            migration.migrate_pod(
                conn,
                executor=fake_executor(executor_mod),
                deployment_id="dep_1",
                target_machine_id="host_target",
                migration_id="mig_777777777777777777777777",
                verifier=lambda _conn, _row, _intent: {"healthy": True},
                env=ROOT_CAPTURE_ENV,
            )
        except migration.ArcLinkPodMigrationError as exc:
            expect("source root must be deployment-scoped" in str(exc), str(exc))
        else:
            raise AssertionError("expected unscoped source root to fail before capture")
        row = conn.execute("SELECT status FROM arclink_pod_migrations WHERE migration_id = ?", ("mig_777777777777777777777777",)).fetchone()
        expect(row is not None and row["status"] == "planned", str(dict(row) if row else None))
        expect(not (Path(tmpdir) / "target" / ".migrations" / "mig_777777777777777777777777").exists(), "capture should not be created")
    print("PASS test_migration_capture_rejects_unscoped_source_root")


def test_migration_rolls_back_on_verification_failure() -> None:
    control = load_module("arclink_control.py", "arclink_control_pod_migration_rollback")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_pod_migration_rollback")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_rollback")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        seed_deployment(control, conn, Path(tmpdir))
        executor = fake_executor(executor_mod)
        result = migration.migrate_pod(
            conn,
            executor=executor,
            deployment_id="dep_1",
            target_machine_id="host_target",
            migration_id="mig_222222222222222222222222",
            verifier=lambda _conn, _row, _intent: {"healthy": False, "blockers": {"dashboard": "unhealthy"}},
            env=ROOT_CAPTURE_ENV,
        )
        expect(result["status"] == "rolled_back", str(result))
        source = conn.execute("SELECT status FROM arclink_deployment_placements WHERE placement_id = 'plc_source'").fetchone()
        target = conn.execute("SELECT status FROM arclink_deployment_placements WHERE placement_id = ?", (result["target_placement_id"],)).fetchone()
        expect(source["status"] == "active", str(dict(source)))
        expect(target["status"] == "removed", str(dict(target)))
        event = conn.execute("SELECT event_type FROM arclink_events WHERE event_type = 'pod_migration_rolled_back'").fetchone()
        expect(event is not None, "expected rollback event")
        lifecycle = {
            str(run["action"])
            for key, run in executor._fake_lifecycle_runs.items()
            if str(key).startswith("arclink:migration:mig_222222222222222222222222:")
        }
        expect({"stop", "teardown", "restart"}.issubset(lifecycle), str(lifecycle))
        row = conn.execute(
            "SELECT rollback_metadata_json, capture_dir, source_garbage_collected_at FROM arclink_pod_migrations WHERE migration_id = ?",
            (result["migration_id"],),
        ).fetchone()
        rollback = json.loads(row["rollback_metadata_json"])
        expect(rollback["lifecycle"]["target_teardown"]["action"] == "teardown", str(rollback))
        expect(rollback["lifecycle"]["source_restart"]["action"] == "restart", str(rollback))
        expect(rollback["capture_cleanup"]["removed"] is True, str(rollback))
        expect(row["source_garbage_collected_at"], str(dict(row)))
        expect(not Path(row["capture_dir"]).exists(), row["capture_dir"])
        replay = migration.migrate_pod(
            conn,
            executor=fake_executor(executor_mod),
            deployment_id="dep_1",
            target_machine_id="host_target",
            migration_id="mig_222222222222222222222222",
        )
        expect(replay["idempotent_replay"] is True and replay["status"] == "rolled_back", str(replay))
    print("PASS test_migration_rolls_back_on_verification_failure")


def test_redeploy_in_place_rollback_restarts_source_without_target_teardown() -> None:
    control = load_module("arclink_control.py", "arclink_control_pod_migration_in_place_rollback")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_pod_migration_in_place_rollback")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_in_place_rollback")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        seed_deployment(control, conn, Path(tmpdir))
        executor = fake_executor(executor_mod)
        result = migration.migrate_pod(
            conn,
            executor=executor,
            deployment_id="dep_1",
            target_machine_id="current",
            migration_id="mig_555555555555555555555555",
            verifier=lambda _conn, _row, _intent: {"healthy": False, "blockers": {"gateway": "unhealthy"}},
            env=ROOT_CAPTURE_ENV,
        )
        expect(result["status"] == "rolled_back", str(result))
        lifecycle = [
            str(run["action"])
            for key, run in executor._fake_lifecycle_runs.items()
            if str(key).startswith("arclink:migration:mig_555555555555555555555555:")
        ]
        expect("stop" in lifecycle and "restart" in lifecycle, str(lifecycle))
        expect("teardown" not in lifecycle, str(lifecycle))
        row = conn.execute(
            "SELECT rollback_metadata_json, capture_dir, source_garbage_collected_at FROM arclink_pod_migrations WHERE migration_id = ?",
            (result["migration_id"],),
        ).fetchone()
        rollback = json.loads(row["rollback_metadata_json"])
        expect("target_teardown" not in rollback["lifecycle"], str(rollback))
        expect(rollback["lifecycle"]["source_restart"]["action"] == "restart", str(rollback))
        expect(rollback["capture_cleanup"]["removed"] is True, str(rollback))
        expect(row["source_garbage_collected_at"], str(dict(row)))
        expect(not Path(row["capture_dir"]).exists(), row["capture_dir"])
    print("PASS test_redeploy_in_place_rollback_restarts_source_without_target_teardown")


def test_migration_gc_marks_expired_successes_only() -> None:
    control = load_module("arclink_control.py", "arclink_control_pod_migration_gc")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_pod_migration_gc")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_gc")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        seed_deployment(control, conn, Path(tmpdir))
        result = migration.migrate_pod(
            conn,
            executor=fake_executor(executor_mod),
            deployment_id="dep_1",
            target_machine_id="host_target",
            migration_id="mig_333333333333333333333333",
            verifier=lambda _conn, _row, _intent: {"healthy": True},
            retention_days=0,
            env=ROOT_CAPTURE_ENV,
        )
        row = conn.execute("SELECT capture_dir FROM arclink_pod_migrations WHERE migration_id = ?", (result["migration_id"],)).fetchone()
        expect(Path(row["capture_dir"]).exists(), row["capture_dir"])
        collected = migration.garbage_collect_pod_migrations(
            conn,
            now=datetime.now(timezone.utc) + timedelta(seconds=1),
        )
        expect(collected == [{"migration_id": result["migration_id"], "removed_artifacts": True}], str(collected))
        expect(not Path(row["capture_dir"]).exists(), row["capture_dir"])
        gc_row = conn.execute("SELECT source_garbage_collected_at FROM arclink_pod_migrations WHERE migration_id = ?", (result["migration_id"],)).fetchone()
        expect(gc_row["source_garbage_collected_at"], str(dict(gc_row)))
    print("PASS test_migration_gc_marks_expired_successes_only")


def test_migration_dry_run_plans_without_mutating_files_or_placements() -> None:
    control = load_module("arclink_control.py", "arclink_control_pod_migration_dry_run")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_pod_migration_dry_run")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_dry_run")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        _, _, target_base = seed_deployment(control, conn, Path(tmpdir))
        result = migration.migrate_pod(
            conn,
            executor=fake_executor(executor_mod),
            deployment_id="dep_1",
            target_machine_id="host_target",
            migration_id="mig_444444444444444444444444",
            reason="operator previewing host move",
            dry_run=True,
            verifier=lambda _conn, _row, _intent: {"healthy": False},
        )
        expect(result["status"] == "planned" and result["dry_run"] is True, str(result))
        expect("docker_dry_run" in result and result["docker_dry_run"]["operation"] == "docker_compose_apply", str(result))
        target_file = target_base / "dep_1-captain-one" / "vault" / "mission.md"
        expect(not target_file.exists(), str(target_file))
        placements = {
            row["placement_id"]: row["status"]
            for row in conn.execute("SELECT placement_id, status FROM arclink_deployment_placements").fetchall()
        }
        expect(placements == {"plc_source": "active"}, str(placements))
        row = conn.execute("SELECT * FROM arclink_pod_migrations WHERE migration_id = ?", (result["migration_id"],)).fetchone()
        verification = json.loads(row["verification_json"])
        expect(row["status"] == "planned" and row["target_placement_id"] == "", str(dict(row)))
        expect(verification["checked"] == "dry_run" and verification["healthy"] is True, str(verification))
    print("PASS test_migration_dry_run_plans_without_mutating_files_or_placements")


def test_default_verifier_requires_fresh_service_health() -> None:
    control = load_module("arclink_control.py", "arclink_control_pod_migration_fresh_health")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_fresh_health")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        seed_deployment(control, conn, Path(tmpdir))
        started = datetime.now(timezone.utc)
        empty = migration._default_verifier(conn, {"deployment_id": "dep_1", "updated_at": started.isoformat()}, {})
        expect(empty["healthy"] is False and empty["blockers"]["service_health"] == "missing", str(empty))
        conn.execute(
            """
            INSERT INTO arclink_service_health (deployment_id, service_name, status, checked_at, detail_json)
            VALUES ('dep_1', 'gateway', 'healthy', ?, '{}')
            """,
            ((started - timedelta(seconds=5)).isoformat(),),
        )
        conn.commit()
        stale = migration._default_verifier(conn, {"deployment_id": "dep_1", "updated_at": started.isoformat()}, {})
        expect(stale["healthy"] is False and stale["blockers"]["gateway"] == "stale", str(stale))
        conn.execute(
            "UPDATE arclink_service_health SET checked_at = ? WHERE deployment_id = 'dep_1' AND service_name = 'gateway'",
            ((started + timedelta(seconds=5)).isoformat(),),
        )
        conn.commit()
        fresh = migration._default_verifier(conn, {"deployment_id": "dep_1", "updated_at": started.isoformat()}, {})
        expect(fresh["healthy"] is True and fresh["fresh_service_count"] == 1, str(fresh))
        gated = migration._apply_docker_status_gate({"healthy": True}, "failed")
        expect(gated["healthy"] is False and gated["blockers"]["docker_compose_apply"] == "failed", str(gated))
    print("PASS test_default_verifier_requires_fresh_service_health")


def test_migration_default_verifier_fails_closed_without_fresh_health() -> None:
    control = load_module("arclink_control.py", "arclink_control_pod_migration_default_verify")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_pod_migration_default_verify")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_default_verify")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        seed_deployment(control, conn, Path(tmpdir))
        result = migration.migrate_pod(
            conn,
            executor=fake_executor(executor_mod),
            deployment_id="dep_1",
            target_machine_id="host_target",
            migration_id="mig_abababababababababababab",
            env=ROOT_CAPTURE_ENV,
        )
        expect(result["status"] == "rolled_back", str(result))
        row = conn.execute("SELECT verification_json FROM arclink_pod_migrations WHERE migration_id = ?", (result["migration_id"],)).fetchone()
        verification = json.loads(row["verification_json"])
        expect(verification["blockers"]["service_health"] == "missing", str(verification))
    print("PASS test_migration_default_verifier_fails_closed_without_fresh_health")


def test_active_live_migration_blocks_distinct_migration_ids() -> None:
    control = load_module("arclink_control.py", "arclink_control_pod_migration_active_block")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_active_block")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        seed_deployment(control, conn, Path(tmpdir))
        first = migration.plan_pod_migration(
            conn,
            deployment_id="dep_1",
            target_machine_id="host_target",
            migration_id="mig_acacacacacacacacacacacac",
        )
        expect(first["status"] == "planned", str(first))
        try:
            migration.plan_pod_migration(
                conn,
                deployment_id="dep_1",
                target_machine_id="host_target",
                migration_id="mig_bcbcbcbcbcbcbcbcbcbcbcbc",
            )
        except migration.ArcLinkPodMigrationError as exc:
            expect("active migration" in str(exc), str(exc))
        else:
            raise AssertionError("expected distinct live migration to be blocked")
    print("PASS test_active_live_migration_blocks_distinct_migration_ids")


def test_running_migration_id_cannot_be_reentered() -> None:
    control = load_module("arclink_control.py", "arclink_control_pod_migration_running_reentry")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_pod_migration_running_reentry")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_running_reentry")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        seed_deployment(control, conn, Path(tmpdir))
        row = migration.plan_pod_migration(
            conn,
            deployment_id="dep_1",
            target_machine_id="host_target",
            migration_id="mig_cdcdcdcdcdcdcdcdcdcdcdcd",
        )
        conn.execute("UPDATE arclink_pod_migrations SET status = 'running' WHERE migration_id = ?", (row["migration_id"],))
        conn.commit()
        executor = fake_executor(executor_mod)
        try:
            migration.migrate_pod(
                conn,
                executor=executor,
                deployment_id="dep_1",
                target_machine_id="host_target",
                migration_id=row["migration_id"],
                verifier=lambda _conn, _row, _intent: {"healthy": True},
                env=ROOT_CAPTURE_ENV,
            )
        except migration.ArcLinkPodMigrationError as exc:
            expect("already running" in str(exc), str(exc))
        else:
            raise AssertionError("expected running migration reentry to fail before host mutation")
        expect(executor._fake_lifecycle_runs == {}, str(executor._fake_lifecycle_runs))
    print("PASS test_running_migration_id_cannot_be_reentered")


def test_existing_plan_rechecks_target_availability() -> None:
    control = load_module("arclink_control.py", "arclink_control_pod_migration_target_recheck")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_pod_migration_target_recheck")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_target_recheck")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        seed_deployment(control, conn, Path(tmpdir))
        row = migration.plan_pod_migration(
            conn,
            deployment_id="dep_1",
            target_machine_id="host_target",
            migration_id="mig_dededededededededededede",
        )
        conn.execute("UPDATE arclink_fleet_hosts SET drain = 1 WHERE host_id = 'host_target'")
        conn.commit()
        executor = fake_executor(executor_mod)
        try:
            migration.migrate_pod(
                conn,
                executor=executor,
                deployment_id="dep_1",
                target_machine_id="host_target",
                migration_id=row["migration_id"],
                verifier=lambda _conn, _row, _intent: {"healthy": True},
                env=ROOT_CAPTURE_ENV,
            )
        except migration.ArcLinkPodMigrationError as exc:
            expect("target host is not available" in str(exc), str(exc))
        else:
            raise AssertionError("expected drained target to fail existing plan recheck")
        expect(executor._fake_lifecycle_runs == {}, str(executor._fake_lifecycle_runs))
    print("PASS test_existing_plan_rechecks_target_availability")


def test_migration_gc_revalidates_capture_path_before_rmtree() -> None:
    control = load_module("arclink_control.py", "arclink_control_pod_migration_gc_guard")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_pod_migration_gc_guard")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_gc_guard")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        seed_deployment(control, conn, Path(tmpdir))
        result = migration.migrate_pod(
            conn,
            executor=fake_executor(executor_mod),
            deployment_id="dep_1",
            target_machine_id="host_target",
            migration_id="mig_efefefefefefefefefefefef",
            verifier=lambda _conn, _row, _intent: {"healthy": True},
            retention_days=0,
            env=ROOT_CAPTURE_ENV,
        )
        unsafe = Path(tmpdir) / "unsafe-delete"
        unsafe.mkdir()
        (unsafe / "keep.txt").write_text("do not delete\n", encoding="utf-8")
        conn.execute(
            "UPDATE arclink_pod_migrations SET capture_dir = ? WHERE migration_id = ?",
            (str(unsafe), result["migration_id"]),
        )
        conn.commit()
        try:
            migration.garbage_collect_pod_migrations(conn, now=datetime.now(timezone.utc) + timedelta(seconds=1))
        except migration.ArcLinkPodMigrationError as exc:
            expect("capture directory" in str(exc), str(exc))
        else:
            raise AssertionError("expected GC to fail closed on an unsafe capture_dir")
        expect((unsafe / "keep.txt").exists(), "GC must not delete an unvalidated capture_dir")
        row = conn.execute("SELECT source_garbage_collected_at FROM arclink_pod_migrations WHERE migration_id = ?", (result["migration_id"],)).fetchone()
        expect(row["source_garbage_collected_at"] == "", str(dict(row)))
    print("PASS test_migration_gc_revalidates_capture_path_before_rmtree")


def test_invalid_gc_days_fails_before_host_mutation() -> None:
    control = load_module("arclink_control.py", "arclink_control_pod_migration_bad_gc_days")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_pod_migration_bad_gc_days")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_bad_gc_days")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        seed_deployment(control, conn, Path(tmpdir))
        executor = fake_executor(executor_mod)
        try:
            migration.migrate_pod(
                conn,
                executor=executor,
                deployment_id="dep_1",
                target_machine_id="host_target",
                migration_id="mig_fafafafafafafafafafafafa",
                verifier=lambda _conn, _row, _intent: {"healthy": True},
                env={**ROOT_CAPTURE_ENV, "ARCLINK_MIGRATION_GC_DAYS": "not-an-integer"},
            )
        except migration.ArcLinkPodMigrationError as exc:
            expect("ARCLINK_MIGRATION_GC_DAYS" in str(exc), str(exc))
        else:
            raise AssertionError("expected invalid GC days to fail before migration starts")
        rows = conn.execute("SELECT COUNT(*) AS c FROM arclink_pod_migrations").fetchone()
        expect(int(rows["c"]) == 0, str(dict(rows)))
        expect(executor._fake_lifecycle_runs == {}, str(executor._fake_lifecycle_runs))
    print("PASS test_invalid_gc_days_fails_before_host_mutation")


def test_success_and_idempotency_complete_are_atomic() -> None:
    control = load_module("arclink_control.py", "arclink_control_pod_migration_atomic_success")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_pod_migration_atomic_success")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_atomic_success")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        seed_deployment(control, conn, Path(tmpdir))
        original_complete = migration.complete_arclink_operation_idempotency

        def fail_complete(*_args, **_kwargs):
            raise RuntimeError("simulated idempotency complete failure")

        migration.complete_arclink_operation_idempotency = fail_complete
        try:
            try:
                migration.migrate_pod(
                    conn,
                    executor=fake_executor(executor_mod),
                    deployment_id="dep_1",
                    target_machine_id="host_target",
                    migration_id="mig_fbfbfbfbfbfbfbfbfbfbfbfb",
                    verifier=lambda _conn, _row, _intent: {"healthy": True},
                    env=ROOT_CAPTURE_ENV,
                )
            except RuntimeError as exc:
                expect("simulated idempotency" in str(exc), str(exc))
            else:
                raise AssertionError("expected idempotency completion failure")
        finally:
            migration.complete_arclink_operation_idempotency = original_complete
        row = conn.execute("SELECT status FROM arclink_pod_migrations WHERE migration_id = 'mig_fbfbfbfbfbfbfbfbfbfbfbfb'").fetchone()
        expect(row["status"] == "rolled_back", str(dict(row)))
        idem = conn.execute(
            """
            SELECT status
            FROM arclink_operation_idempotency
            WHERE operation_kind = 'pod_migration'
              AND idempotency_key = 'arclink:migration:mig_fbfbfbfbfbfbfbfbfbfbfbfb'
            """
        ).fetchone()
        expect(idem["status"] == "failed", str(dict(idem)))
    print("PASS test_success_and_idempotency_complete_are_atomic")


def main() -> int:
    test_migration_captures_materializes_verifies_and_replays()
    test_migration_capture_requires_explicit_root_opt_in()
    test_migration_capture_requires_helper_in_docker_mode()
    test_migration_capture_uses_helper_when_configured()
    test_migration_capture_helper_rejects_raw_commands_and_unscoped_paths()
    test_migration_capture_helper_rejects_paths_outside_configured_state_root_base()
    test_migration_capture_rejects_unscoped_source_root()
    test_migration_rolls_back_on_verification_failure()
    test_redeploy_in_place_rollback_restarts_source_without_target_teardown()
    test_migration_gc_marks_expired_successes_only()
    test_migration_dry_run_plans_without_mutating_files_or_placements()
    test_default_verifier_requires_fresh_service_health()
    test_migration_default_verifier_fails_closed_without_fresh_health()
    test_active_live_migration_blocks_distinct_migration_ids()
    test_running_migration_id_cannot_be_reentered()
    test_existing_plan_rechecks_target_availability()
    test_migration_gc_revalidates_capture_path_before_rmtree()
    test_invalid_gc_days_fails_before_host_mutation()
    test_success_and_idempotency_complete_are_atomic()
    print("PASS all 19 ArcLink Pod migration tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
