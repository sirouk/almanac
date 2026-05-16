#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import random
import re
import sqlite3
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
CONTROL_PY = PYTHON_DIR / "arclink_control.py"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_control():
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    spec = importlib.util.spec_from_file_location("arclink_control_arclink_schema_test", CONTROL_PY)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {CONTROL_PY}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["arclink_control_arclink_schema_test"] = module
    spec.loader.exec_module(module)
    return module


def memory_db(mod):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    mod.ensure_schema(conn)
    return conn


def test_arclink_schema_creates_expected_tables_and_is_idempotent() -> None:
    mod = load_control()
    conn = memory_db(mod)
    mod.ensure_schema(conn)
    names = {
        str(row["name"])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'arclink_%'")
    }
    expected = {
        "arclink_users",
        "arclink_deployments",
        "arclink_subscriptions",
        "arclink_provisioning_jobs",
        "arclink_dns_records",
        "arclink_admins",
        "arclink_user_sessions",
        "arclink_admin_sessions",
        "arclink_admin_roles",
        "arclink_admin_totp_factors",
        "arclink_audit_log",
        "arclink_service_health",
        "arclink_events",
        "arclink_webhook_events",
        "arclink_model_catalog",
        "arclink_onboarding_sessions",
        "arclink_onboarding_events",
        "arclink_action_intents",
        "arclink_action_operation_links",
        "arclink_inventory_machines",
        "arclink_fleet_enrollments",
        "arclink_fleet_host_probes",
        "arclink_fleet_audit_chain",
        "arclink_pod_messages",
        "arclink_pod_migrations",
        "arclink_crew_recipes",
        "arclink_wrapped_reports",
    }
    expect(expected <= names, f"missing ArcLink tables: {sorted(expected - names)}")
    inventory_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(arclink_inventory_machines)").fetchall()}
    for name in ("enrollment_id", "machine_fingerprint", "attested_at", "audit_trail_chain", "provider_billing_ref"):
        expect(name in inventory_columns, str(inventory_columns))
    host_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(arclink_fleet_hosts)").fetchall()}
    for name in ("region_tier", "placement_priority", "last_health_state"):
        expect(name in host_columns, str(host_columns))
    print("PASS test_arclink_schema_creates_expected_tables_and_is_idempotent")


def test_arc_pod_captain_console_wave0_columns_and_indexes_exist() -> None:
    mod = load_control()
    conn = memory_db(mod)
    columns = {
        table: {
            str(row["name"]): str(row["type"]).upper()
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for table in ("arclink_users", "arclink_deployments", "arclink_onboarding_sessions")
    }
    expect("agent_title" in columns["arclink_users"], str(columns["arclink_users"]))
    for name in ("captain_role", "captain_mission", "captain_treatment", "wrapped_frequency"):
        expect(name in columns["arclink_users"], str(columns["arclink_users"]))
    for name in ("agent_name", "agent_title", "asu_weight"):
        expect(name in columns["arclink_deployments"], str(columns["arclink_deployments"]))
    for name in ("agent_name", "agent_title"):
        expect(name in columns["arclink_onboarding_sessions"], str(columns["arclink_onboarding_sessions"]))

    indexes = {
        str(row["name"])
        for row in conn.execute("PRAGMA index_list(arclink_crew_recipes)").fetchall()
    }
    expect("idx_arclink_crew_recipes_one_active" in indexes, str(indexes))
    print("PASS test_arc_pod_captain_console_wave0_columns_and_indexes_exist")


def test_pod_migration_wave3_columns_and_indexes_exist() -> None:
    mod = load_control()
    conn = memory_db(mod)
    columns = {
        str(row["name"]): str(row["type"]).upper()
        for row in conn.execute("PRAGMA table_info(arclink_pod_migrations)").fetchall()
    }
    for name in (
        "source_placement_id",
        "target_placement_id",
        "source_host_id",
        "target_host_id",
        "target_machine_id",
        "source_state_root",
        "target_state_root",
        "capture_dir",
        "verification_json",
        "target_host_metadata_json",
        "source_retention_until",
        "source_garbage_collected_at",
    ):
        expect(name in columns, str(columns))
    indexes = {str(row["name"]) for row in conn.execute("PRAGMA index_list(arclink_pod_migrations)").fetchall()}
    expect("idx_arclink_pod_migrations_gc" in indexes, str(indexes))
    print("PASS test_pod_migration_wave3_columns_and_indexes_exist")


def test_deployment_prefix_reservation_is_unique() -> None:
    mod = load_control()
    conn = memory_db(mod)
    first = mod.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_1",
        user_id="user_1",
        prefix="abc-123",
        base_domain="example.test",
    )
    expect(first["prefix"] == "abc-123", str(dict(first)))
    try:
        mod.reserve_arclink_deployment_prefix(
            conn,
            deployment_id="dep_2",
            user_id="user_2",
            prefix="ABC-123",
            base_domain="example.test",
        )
    except ValueError as exc:
        expect("already reserved" in str(exc), str(exc))
    else:
        raise AssertionError("expected duplicate prefix reservation to fail")
    print("PASS test_deployment_prefix_reservation_is_unique")


def test_generated_deployment_prefixes_validate_denylist_and_retry_collisions() -> None:
    mod = load_control()
    conn = memory_db(mod)
    pattern = re.compile(r"^[a-z0-9][a-z0-9-]{2,31}$")
    first_rng = random.Random(42)
    first_prefix = mod.generate_arclink_deployment_prefix(rng=first_rng)
    expect(pattern.match(first_prefix) is not None, first_prefix)
    mod.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_existing",
        user_id="user_1",
        prefix=first_prefix,
    )
    generated = mod.reserve_generated_arclink_deployment_prefix(
        conn,
        deployment_id="dep_generated",
        user_id="user_1",
        rng=random.Random(42),
    )
    expect(generated["prefix"] != first_prefix, str(generated))
    expect(pattern.match(generated["prefix"]) is not None, str(generated))
    try:
        mod.normalize_arclink_deployment_prefix("Admin-Portal")
    except ValueError as exc:
        expect("reserved substring" in str(exc), str(exc))
    else:
        raise AssertionError("expected denylisted prefix to fail")
    print("PASS test_generated_deployment_prefixes_validate_denylist_and_retry_collisions")


def test_generated_deployment_prefix_pool_is_large_and_public_safe() -> None:
    mod = load_control()
    namespace_size = (
        len(mod.ARCLINK_PREFIX_ADJECTIVES)
        * len(mod.ARCLINK_PREFIX_NOUNS)
        * (len(mod.ARCLINK_PREFIX_CODE_ALPHABET) ** mod.ARCLINK_PREFIX_CODE_LENGTH)
    )
    expect(namespace_size > 1_000_000_000, str(namespace_size))
    longest = max(
        len(adjective) + len(noun) + mod.ARCLINK_PREFIX_CODE_LENGTH + 2
        for adjective in mod.ARCLINK_PREFIX_ADJECTIVES
        for noun in mod.ARCLINK_PREFIX_NOUNS
    )
    expect(longest <= 32, str(longest))
    recognizable_media_terms = {
        "rocinante",
        "protomolecule",
        "beltalowda",
        "skaikru",
        "wanheda",
        "nightblood",
        "azgeda",
        "heda",
    }
    pool_terms = set(mod.ARCLINK_PREFIX_ADJECTIVES) | set(mod.ARCLINK_PREFIX_NOUNS)
    expect(not (pool_terms & recognizable_media_terms), str(pool_terms & recognizable_media_terms))

    generated = [mod.generate_arclink_deployment_prefix(rng=random.Random(seed)) for seed in range(250)]
    expect(len(set(generated)) == len(generated), str(generated))
    for prefix in generated:
        expect(mod.ARCLINK_DEPLOYMENT_PREFIX_PATTERN.match(prefix) is not None, prefix)
        expect(not prefix.startswith("arc-"), prefix)
        mod.normalize_arclink_deployment_prefix(prefix)

    print("PASS test_generated_deployment_prefix_pool_is_large_and_public_safe")


def test_events_and_audit_are_append_only_by_primary_key() -> None:
    mod = load_control()
    conn = memory_db(mod)
    event_id = mod.append_arclink_event(
        conn,
        event_id="evt_fixed",
        subject_kind="deployment",
        subject_id="dep_1",
        event_type="created",
    )
    audit_id = mod.append_arclink_audit(
        conn,
        audit_id="aud_fixed",
        action="comp_subscription",
        actor_id="admin_1",
        target_kind="deployment",
        target_id="dep_1",
        reason="test",
    )
    expect(event_id == "evt_fixed", event_id)
    expect(audit_id == "aud_fixed", audit_id)
    for fn, kwargs in (
        (
            mod.append_arclink_event,
            {
                "event_id": "evt_fixed",
                "subject_kind": "deployment",
                "subject_id": "dep_1",
                "event_type": "changed",
            },
        ),
        (
            mod.append_arclink_audit,
            {
                "audit_id": "aud_fixed",
                "action": "changed",
                "actor_id": "admin_1",
            },
        ),
    ):
        try:
            fn(conn, **kwargs)
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("expected duplicate append id to fail")
    print("PASS test_events_and_audit_are_append_only_by_primary_key")


def test_subscription_health_and_provisioning_helpers() -> None:
    mod = load_control()
    conn = memory_db(mod)
    mod.upsert_arclink_subscription_mirror(
        conn,
        subscription_id="sub_local",
        user_id="user_1",
        stripe_customer_id="cus_test",
        stripe_subscription_id="sub_test",
        status="active",
    )
    mod.upsert_arclink_subscription_mirror(
        conn,
        subscription_id="sub_local",
        user_id="user_1",
        stripe_customer_id="cus_test",
        stripe_subscription_id="sub_test",
        status="past_due",
    )
    row = conn.execute("SELECT status FROM arclink_subscriptions WHERE subscription_id = 'sub_local'").fetchone()
    expect(row["status"] == "past_due", str(dict(row)))

    mod.upsert_arclink_service_health(
        conn,
        deployment_id="dep_1",
        service_name="qmd",
        status="healthy",
        detail={"latency_ms": 12},
    )
    mod.upsert_arclink_service_health(conn, deployment_id="dep_1", service_name="qmd", status="degraded")
    row = conn.execute("SELECT status FROM arclink_service_health WHERE deployment_id = 'dep_1' AND service_name = 'qmd'").fetchone()
    expect(row["status"] == "degraded", str(dict(row)))

    mod.create_arclink_provisioning_job(conn, job_id="job_1", deployment_id="dep_1", job_kind="docker_dry_run")
    mod.transition_arclink_provisioning_job(conn, job_id="job_1", status="running")
    mod.transition_arclink_provisioning_job(conn, job_id="job_1", status="succeeded")
    row = conn.execute("SELECT status, attempt_count FROM arclink_provisioning_jobs WHERE job_id = 'job_1'").fetchone()
    expect(row["status"] == "succeeded" and row["attempt_count"] == 1, str(dict(row)))
    print("PASS test_subscription_health_and_provisioning_helpers")


def test_arclink_drift_detection_reports_missing_linked_rows() -> None:
    mod = load_control()
    conn = memory_db(mod)
    mod.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_missing_links",
        user_id="user_1",
        prefix="missing-links",
        agent_id="agent_missing",
        session_id="session_missing",
        bootstrap_request_id="request_missing",
    )
    mod.upsert_arclink_subscription_mirror(conn, subscription_id="sub_missing_user", user_id="user_missing", status="active")
    drift = mod.arclink_drift_checks(conn)
    kinds = {item["kind"] for item in drift}
    expect(
        {
            "deployment_agent_missing",
            "deployment_session_missing",
            "deployment_bootstrap_request_missing",
            "subscription_user_missing",
        }
        <= kinds,
        str(drift),
    )
    print("PASS test_arclink_drift_detection_reports_missing_linked_rows")


def test_arc_pod_captain_console_status_drift_checks() -> None:
    mod = load_control()
    conn = memory_db(mod)
    conn.execute("PRAGMA ignore_check_constraints = ON")
    conn.execute(
        """
        INSERT INTO arclink_inventory_machines (
          machine_id, provider, hostname, status, registered_at
        ) VALUES ('machine_bad', 'manual', 'bad.example.test', 'bogus', '2026-01-01T00:00:00+00:00')
        """
    )
    conn.execute(
        """
        INSERT INTO arclink_pod_messages (
          message_id, sender_deployment_id, recipient_deployment_id,
          sender_user_id, recipient_user_id, status, created_at
        ) VALUES ('msg_bad', 'dep_missing_sender', 'dep_missing_recipient',
          'user_missing_sender', 'user_missing_recipient', 'bogus', '2026-01-01T00:00:00+00:00')
        """
    )
    conn.execute(
        """
        INSERT INTO arclink_pod_migrations (
          migration_id, deployment_id, source_placement_id, target_placement_id,
          source_host_id, target_host_id, status, created_at, updated_at
        ) VALUES ('migration_bad', 'dep_missing', 'plc_missing_source', 'plc_missing_target',
          'host_missing_source', 'host_missing_target', 'bogus', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """
    )
    conn.execute(
        """
        INSERT INTO arclink_pod_migrations (
          migration_id, deployment_id, source_placement_id, source_host_id,
          target_host_id, status, created_at, updated_at
        ) VALUES ('migration_target_required', 'dep_missing', 'plc_missing_source',
          'host_missing_source', 'host_missing_target', 'running', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """
    )
    conn.execute(
        """
        INSERT INTO arclink_crew_recipes (
          recipe_id, user_id, status
        ) VALUES ('recipe_bad', 'user_missing', 'bogus')
        """
    )
    conn.execute(
        """
        INSERT INTO arclink_wrapped_reports (
          report_id, user_id, period, period_start, period_end, status, created_at
        ) VALUES ('wrapped_bad', 'user_missing', 'daily', '2026-01-01', '2026-01-02', 'bogus', '2026-01-02T00:00:00+00:00')
        """
    )
    conn.execute("PRAGMA ignore_check_constraints = OFF")
    drift = mod.arclink_drift_checks(conn)
    kinds = {item["kind"] for item in drift}
    expect("inventory_machine_status_invalid" in kinds, str(drift))
    expect("pod_message_status_invalid" in kinds, str(drift))
    expect("pod_migration_status_invalid" in kinds, str(drift))
    expect("crew_recipe_status_invalid" in kinds, str(drift))
    expect("wrapped_report_status_invalid" in kinds, str(drift))
    expect("pod_message_sender_deployment_missing" in kinds, str(drift))
    expect("pod_migration_deployment_missing" in kinds, str(drift))
    expect("pod_migration_source_placement_missing" in kinds, str(drift))
    expect("pod_migration_target_placement_missing" in kinds, str(drift))
    expect("pod_migration_source_host_missing" in kinds, str(drift))
    expect("pod_migration_target_host_missing" in kinds, str(drift))
    expect("pod_migration_target_placement_required" in kinds, str(drift))
    expect("crew_recipe_user_missing" in kinds, str(drift))
    expect("wrapped_report_user_missing" in kinds, str(drift))
    print("PASS test_arc_pod_captain_console_status_drift_checks")


def main() -> int:
    test_arclink_schema_creates_expected_tables_and_is_idempotent()
    test_arc_pod_captain_console_wave0_columns_and_indexes_exist()
    test_pod_migration_wave3_columns_and_indexes_exist()
    test_deployment_prefix_reservation_is_unique()
    test_generated_deployment_prefixes_validate_denylist_and_retry_collisions()
    test_generated_deployment_prefix_pool_is_large_and_public_safe()
    test_events_and_audit_are_append_only_by_primary_key()
    test_subscription_health_and_provisioning_helpers()
    test_arclink_drift_detection_reports_missing_linked_rows()
    test_arc_pod_captain_console_status_drift_checks()
    print("PASS all 10 ArcLink schema tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
