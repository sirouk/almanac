#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
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
        result = migration.migrate_pod(
            conn,
            executor=fake_executor(executor_mod),
            deployment_id="dep_1",
            target_machine_id="host_target",
            migration_id="mig_111111111111111111111111",
            reason="operator moving Pod to new host",
            verifier=lambda _conn, _row, _intent: {"healthy": True, "session_continuity": "checked"},
            retention_days=7,
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
        expect("vault/outside-link" not in paths, str(paths))
        expect(not (target_base / "dep_1-captain-one" / "vault" / "outside-link").exists(), "symlink should not be materialized")
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
            "SELECT rollback_metadata_json FROM arclink_pod_migrations WHERE migration_id = ?",
            (result["migration_id"],),
        ).fetchone()
        rollback = json.loads(row["rollback_metadata_json"])
        expect(rollback["lifecycle"]["target_teardown"]["action"] == "teardown", str(rollback))
        expect(rollback["lifecycle"]["source_restart"]["action"] == "restart", str(rollback))
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
            "SELECT rollback_metadata_json FROM arclink_pod_migrations WHERE migration_id = ?",
            (result["migration_id"],),
        ).fetchone()
        rollback = json.loads(row["rollback_metadata_json"])
        expect("target_teardown" not in rollback["lifecycle"], str(rollback))
        expect(rollback["lifecycle"]["source_restart"]["action"] == "restart", str(rollback))
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


def main() -> int:
    test_migration_captures_materializes_verifies_and_replays()
    test_migration_rolls_back_on_verification_failure()
    test_redeploy_in_place_rollback_restarts_source_without_target_teardown()
    test_migration_gc_marks_expired_successes_only()
    test_migration_dry_run_plans_without_mutating_files_or_placements()
    print("PASS all 5 ArcLink Pod migration tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
