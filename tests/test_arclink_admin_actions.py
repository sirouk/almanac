#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
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


def test_admin_action_requires_reason_and_queues_audited_intent() -> None:
    control = load_module("arclink_control.py", "arclink_control_admin_action_reason_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_admin_action_reason_test")
    conn = memory_db(control)
    try:
        dashboard.queue_arclink_admin_action(
            conn,
            admin_id="admin_1",
            action_type="restart",
            target_kind="deployment",
            target_id="dep_1",
            reason="",
            idempotency_key="restart-1",
        )
    except dashboard.ArcLinkDashboardError as exc:
        expect("reason" in str(exc), str(exc))
    else:
        raise AssertionError("expected reasonless admin action to fail")

    action = dashboard.queue_arclink_admin_action(
        conn,
        admin_id="admin_1",
        action_type="restart",
        target_kind="deployment",
        target_id="dep_1",
        reason="operator requested restart",
        idempotency_key="restart-1",
        metadata={"source": "admin_dashboard"},
    )
    expect(action["status"] == "queued", str(action))
    expect(action["audit_id"], str(action))
    audits = conn.execute("SELECT * FROM arclink_audit_log WHERE target_id = 'dep_1'").fetchall()
    expect(len(audits) == 1, str([dict(row) for row in audits]))
    expect(audits[0]["action"] == "admin_action:restart", str(dict(audits[0])))
    print("PASS test_admin_action_requires_reason_and_queues_audited_intent")


def test_admin_action_idempotency_reuses_intent_without_duplicate_audit() -> None:
    control = load_module("arclink_control.py", "arclink_control_admin_action_idempotency_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_admin_action_idempotency_test")
    conn = memory_db(control)
    first = dashboard.queue_arclink_admin_action(
        conn,
        admin_id="admin_1",
        action_type="dns_repair",
        target_kind="deployment",
        target_id="dep_1",
        reason="repair recorded DNS drift",
        idempotency_key="dns-repair-1",
    )
    second = dashboard.queue_arclink_admin_action(
        conn,
        admin_id="admin_1",
        action_type="dns_repair",
        target_kind="deployment",
        target_id="dep_1",
        reason="repair recorded DNS drift",
        idempotency_key="dns-repair-1",
    )
    expect(first["action_id"] == second["action_id"], str((first, second)))
    audit_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_audit_log").fetchone()["n"]
    expect(audit_count == 1, str(audit_count))
    try:
        dashboard.queue_arclink_admin_action(
            conn,
            admin_id="admin_1",
            action_type="restart",
            target_kind="deployment",
            target_id="dep_1",
            reason="different action with reused key",
            idempotency_key="dns-repair-1",
        )
    except dashboard.ArcLinkDashboardError as exc:
        expect("idempotency" in str(exc), str(exc))
    else:
        raise AssertionError("expected conflicting idempotency key to fail")
    print("PASS test_admin_action_idempotency_reuses_intent_without_duplicate_audit")


def test_admin_action_rejects_unwired_action_types() -> None:
    control = load_module("arclink_control.py", "arclink_control_admin_action_unwired_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_admin_action_unwired_test")
    conn = memory_db(control)
    for action_type in ("force_resynth", "rotate_bot_key", "suspend", "unsuspend"):
        try:
            dashboard.queue_arclink_admin_action(
                conn,
                admin_id="admin_1",
                action_type=action_type,
                target_kind="deployment",
                target_id=f"dep_{action_type}",
                reason="operator requested unsupported action",
                idempotency_key=f"{action_type}-1",
            )
        except dashboard.ArcLinkDashboardError as exc:
            expect("not queueable" in str(exc), str(exc))
        else:
            raise AssertionError(f"expected {action_type} to be rejected before queueing")
    queued = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]
    expect(queued == 0, str(queued))
    print("PASS test_admin_action_rejects_unwired_action_types")


def test_admin_action_accepts_reprovision_as_executable() -> None:
    control = load_module("arclink_control.py", "arclink_control_admin_action_reprovision_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_admin_action_reprovision_test")
    conn = memory_db(control)
    action = dashboard.queue_arclink_admin_action(
        conn,
        admin_id="admin_1",
        action_type="reprovision",
        target_kind="deployment",
        target_id="dep_1",
        reason="operator requested redeploy in place",
        idempotency_key="reprovision-1",
        metadata={"target_machine_id": "current"},
    )
    expect(action["status"] == "queued", str(action))
    expect(json.loads(action["metadata_json"])["target_machine_id"] == "current", str(action))
    print("PASS test_admin_action_accepts_reprovision_as_executable")


def test_admin_action_metadata_rejects_plaintext_secrets_and_has_no_live_side_effects() -> None:
    control = load_module("arclink_control.py", "arclink_control_admin_action_secret_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_admin_action_secret_test")
    conn = memory_db(control)
    try:
        dashboard.queue_arclink_admin_action(
            conn,
            admin_id="admin_1",
            action_type="rotate_chutes_key",
            target_kind="deployment",
            target_id="dep_1",
            reason="rotate leaked test fixture",
            idempotency_key="rotate-1",
            metadata={"provider_api_key": "sk_test_plaintext"},
        )
    except dashboard.ArcLinkDashboardError as exc:
        expect("secret material" in str(exc), str(exc))
    else:
        raise AssertionError("expected plaintext metadata secret to fail")
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"] == 0, "unexpected action")

    action = dashboard.queue_arclink_admin_action(
        conn,
        admin_id="admin_1",
        action_type="rotate_chutes_key",
        target_kind="deployment",
        target_id="dep_1",
        reason="rotate provider key through executor later",
        idempotency_key="rotate-2",
        metadata={"provider_api_key_ref": "secret://arclink/provider/dep_1"},
    )
    rendered = json.dumps(dict(action), sort_keys=True)
    expect("sk_test" not in rendered and "secret://" in rendered, rendered)
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_provisioning_jobs").fetchone()["n"] == 0, "live job was created")
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_dns_records").fetchone()["n"] == 0, "DNS was mutated")
    print("PASS test_admin_action_metadata_rejects_plaintext_secrets_and_has_no_live_side_effects")


def test_admin_refund_and_cancel_actions_record_audited_notes() -> None:
    control = load_module("arclink_control.py", "arclink_control_admin_refund_cancel_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_admin_refund_cancel_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_1", entitlement_state="paid")
    control.reserve_arclink_deployment_prefix(
        conn, deployment_id="dep_1", user_id="user_1",
        prefix="refund-test", status="provisioning_ready",
    )
    # Queue a refund admin action with admin notes
    refund = dashboard.queue_arclink_admin_action(
        conn,
        admin_id="admin_1",
        action_type="refund",
        target_kind="user",
        target_id="user_1",
        reason="customer requested refund for billing error",
        idempotency_key="refund-user1-1",
        metadata={"stripe_customer_ref": "secret://arclink/stripe/customer/user_1", "admin_note": "prorated refund approved"},
    )
    expect(refund["status"] == "queued", str(refund))
    # Queue a cancel admin action
    cancel = dashboard.queue_arclink_admin_action(
        conn,
        admin_id="admin_1",
        action_type="cancel",
        target_kind="user",
        target_id="user_1",
        reason="customer requested subscription cancellation",
        idempotency_key="cancel-user1-1",
        metadata={"admin_note": "immediate cancellation per support ticket #42"},
    )
    expect(cancel["status"] == "queued", str(cancel))
    # Both actions should have audit entries with reasons
    audits = conn.execute(
        "SELECT action, reason FROM arclink_audit_log WHERE target_id = 'user_1' ORDER BY created_at"
    ).fetchall()
    expect(len(audits) == 2, str([dict(r) for r in audits]))
    expect(audits[0]["action"] == "admin_action:refund", str(dict(audits[0])))
    expect("billing error" in audits[0]["reason"], str(dict(audits[0])))
    expect(audits[1]["action"] == "admin_action:cancel", str(dict(audits[1])))
    expect("cancellation" in audits[1]["reason"], str(dict(audits[1])))
    # Action intents store the admin notes in metadata
    intents = conn.execute(
        "SELECT action_type, metadata_json FROM arclink_action_intents WHERE target_id = 'user_1' ORDER BY created_at"
    ).fetchall()
    expect(len(intents) == 2, str([dict(r) for r in intents]))
    refund_meta = json.loads(intents[0]["metadata_json"])
    expect("admin_note" in refund_meta, str(refund_meta))
    expect(refund_meta["admin_note"] == "prorated refund approved", str(refund_meta))
    cancel_meta = json.loads(intents[1]["metadata_json"])
    expect("admin_note" in cancel_meta, str(cancel_meta))
    # No plaintext secrets in stored metadata
    for intent in intents:
        expect("sk_" not in intent["metadata_json"], str(dict(intent)))
    print("PASS test_admin_refund_and_cancel_actions_record_audited_notes")


def test_admin_dashboard_exposes_action_execution_readiness() -> None:
    control = load_module("arclink_control.py", "arclink_control_admin_action_readiness_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_admin_action_readiness_test")
    conn = memory_db(control)
    view = dashboard.read_arclink_admin_dashboard(conn)
    readiness = view["action_execution_readiness"]
    expect(readiness["executable"] == [], str(readiness))
    expect("restart" in readiness["disabled"], str(readiness))
    expect("fail closed" in readiness["note"], str(readiness))

    ready = dashboard.admin_action_execution_readiness(env={"ARCLINK_EXECUTOR_ADAPTER": "fake"})
    expect("restart" in ready["executable"], str(ready))
    expect("reprovision" in ready["executable"], str(ready))
    expect("dns_repair" in ready["executable"], str(ready))
    expect("comp" in ready["executable"], str(ready))
    expect("rollout" in ready["executable"], str(ready))
    expect("academy_apply_preview" in ready["executable"], str(ready))
    expect("force_resynth" in ready["disabled"], str(ready))
    expect(ready["probes"][0]["ok"] is True, str(ready))
    expect(set(ready["executable"]).isdisjoint(set(ready["pending_not_implemented"])), str(ready))
    ssh_blocked = dashboard.admin_action_execution_readiness(env={"ARCLINK_EXECUTOR_ADAPTER": "ssh"})
    expect(ssh_blocked["executable"] == [], str(ssh_blocked))
    expect(any(probe["name"] == "ssh_key" and not probe["ok"] for probe in ssh_blocked["probes"]), str(ssh_blocked))
    print("PASS test_admin_dashboard_exposes_action_execution_readiness")


def test_admin_action_readiness_publishes_source_owned_support_matrix() -> None:
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_admin_action_matrix_test")
    ready = dashboard.admin_action_execution_readiness(env={"ARCLINK_EXECUTOR_ADAPTER": "fake"})
    support = ready["action_support"]
    expect(set(support) == set(dashboard.ARCLINK_ADMIN_ACTION_TYPES), str(support))
    expect(len(ready["action_matrix"]) == len(dashboard.ARCLINK_ADMIN_ACTION_TYPES), str(ready["action_matrix"]))

    restart = support["restart"]
    expect(restart["queueable"] is True, str(restart))
    expect(restart["readiness"] == "queueable", str(restart))
    expect(restart["operation_kind"] == "docker_compose_lifecycle", str(restart))
    expect(restart["live_proof_gate"] == "PG-PROVISION", str(restart))
    expect("fake|local|ssh" in restart["required_adapter"], str(restart))
    expect("queues" in restart["local_contract"], str(restart))
    expect(restart["fail_closed_reason"] == "", str(restart))

    expected_gates = {
        "reprovision": "PG-PROVISION",
        "dns_repair": "PG-INGRESS",
        "rotate_chutes_key": "PG-PROVIDER",
        "refund": "PG-STRIPE",
        "cancel": "PG-STRIPE",
        "comp": "LOCAL-CONTROL-DB",
        "rollout": "PG-UPGRADE/PG-HERMES",
        "academy_apply_preview": "PG-HERMES/PG-PROVIDER",
    }
    for action_type, proof_gate in expected_gates.items():
        entry = support[action_type]
        expect(entry["queueable"] is True, str(entry))
        expect(entry["live_proof_gate"] == proof_gate, str(entry))
        expect(entry["worker_support"] == "wired", str(entry))
        expect(entry["local_contract"], str(entry))
        expect(entry["required_adapter"], str(entry))

    rollout = support["rollout"]
    expect(rollout["queueable"] is True, str(rollout))
    expect(rollout["readiness"] == "queueable", str(rollout))
    expect(rollout["operation_kind"] == "arcpod_update_rollout", str(rollout))
    expect("dry-run preflight" in rollout["local_contract"], str(rollout))
    expect("rollout" not in ready["pending_not_implemented"], str(ready))

    academy_preview = support["academy_apply_preview"]
    expect(academy_preview["queueable"] is True, str(academy_preview))
    expect(academy_preview["operation_kind"] == "academy_application_preview", str(academy_preview))
    expect("no-write Academy application preview" in academy_preview["local_contract"], str(academy_preview))
    expect("no executor" in academy_preview["required_adapter"], str(academy_preview))

    blocked = dashboard.admin_action_execution_readiness(env={})
    blocked_restart = blocked["action_support"]["restart"]
    expect(blocked_restart["queueable"] is False, str(blocked_restart))
    expect(blocked_restart["readiness"] == "disabled", str(blocked_restart))
    expect("executor probes" in blocked_restart["fail_closed_reason"], str(blocked_restart))
    print("PASS test_admin_action_readiness_publishes_source_owned_support_matrix")


def test_admin_action_matrix_marks_academy_apply_preview_queueable_but_pg_hermes_gated() -> None:
    control = load_module("arclink_control.py", "arclink_control_admin_academy_preview_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_admin_academy_preview_test")
    conn = memory_db(control)
    action = dashboard.queue_arclink_admin_action(
        conn,
        admin_id="admin_1",
        action_type="academy_apply_preview",
        target_kind="user",
        target_id="user_academy",
        reason="operator requested no-write Academy application preview",
        idempotency_key="academy-preview-admin-1",
        metadata={
            "recipe_id": "crew_academy",
            "manifest_id": "academy-123",
            "application_plan_id": "academy-plan-123",
            "agent_id": "agent-academy",
            "local_only": True,
            "no_write": True,
            "writes_enabled": False,
            "proof_gates": ["PG-PROVIDER", "PG-HERMES"],
        },
    )
    expect(action["status"] == "queued", str(action))
    metadata = json.loads(action["metadata_json"])
    expect(metadata["writes_enabled"] is False, str(metadata))
    ready = dashboard.admin_action_execution_readiness(env={"ARCLINK_EXECUTOR_ADAPTER": "fake"})
    academy_preview = ready["action_support"]["academy_apply_preview"]
    expect(academy_preview["queueable"] is True, str(academy_preview))
    expect(academy_preview["worker_support"] == "wired", str(academy_preview))
    expect(academy_preview["live_proof_gate"] == "PG-HERMES/PG-PROVIDER", str(academy_preview))
    expect("academy_apply_preview" not in ready["pending_not_implemented"], str(ready))
    expect("PG-HERMES" in academy_preview["live_proof_gate"], str(academy_preview))
    print("PASS test_admin_action_matrix_marks_academy_apply_preview_queueable_but_pg_hermes_gated")


def test_admin_action_queue_enforces_per_action_target_kinds() -> None:
    control = load_module("arclink_control.py", "arclink_control_admin_action_target_kinds_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_admin_action_target_kinds_test")
    conn = memory_db(control)
    invalid = (
        ("rollout", "user"),
        ("academy_apply_preview", "subscription"),
        ("restart", "user"),
    )
    for action_type, target_kind in invalid:
        try:
            dashboard.queue_arclink_admin_action(
                conn,
                admin_id="admin_1",
                action_type=action_type,
                target_kind=target_kind,
                target_id="target_1",
                reason="target kind contract check",
                idempotency_key=f"{action_type}-{target_kind}-invalid",
            )
            raise AssertionError(f"expected {action_type} to reject target kind {target_kind}")
        except dashboard.ArcLinkDashboardError as exc:
            expect("does not support target kind" in str(exc), str(exc))
    expect(
        conn.execute("SELECT COUNT(*) AS count FROM arclink_action_intents").fetchone()["count"] == 0,
        "invalid target kinds should not leave queued action rows",
    )
    print("PASS test_admin_action_queue_enforces_per_action_target_kinds")


def test_control_node_provisioning_readiness_surfaces_worker_capacity_without_live_probe() -> None:
    control = load_module("arclink_control.py", "arclink_control_provisioning_readiness_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_provisioning_readiness_test")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_provisioning_readiness_test")
    conn = memory_db(control)

    control_plane_only = dashboard.control_node_provisioning_readiness(
        conn,
        env={"ARCLINK_CONTROL_PROVISIONER_ENABLED": "0"},
    )
    expect(control_plane_only["state"] == "control_plane_only", str(control_plane_only))
    expect(control_plane_only["ready_to_provision"] is False, str(control_plane_only))
    expect(control_plane_only["eligible_worker_count"] == 0, str(control_plane_only))
    expect("Register and smoke-test" in control_plane_only["next_action"], str(control_plane_only))

    blocked = dashboard.control_node_provisioning_readiness(
        conn,
        env={"ARCLINK_CONTROL_PROVISIONER_ENABLED": "1", "ARCLINK_EXECUTOR_ADAPTER": "local"},
    )
    expect(blocked["state"] == "blocked_no_worker", str(blocked))
    expect(blocked["ready_to_provision"] is False, str(blocked))
    expect(any(item["name"] == "worker_capacity" for item in blocked["blockers"]), str(blocked))

    fleet.register_fleet_host(
        conn,
        host_id="host-local",
        hostname="local-worker.example.test",
        region="iad",
        capacity_slots=3,
    )
    local_ready = dashboard.control_node_provisioning_readiness(
        conn,
        env={"ARCLINK_CONTROL_PROVISIONER_ENABLED": "1", "ARCLINK_EXECUTOR_ADAPTER": "local"},
    )
    expect(local_ready["state"] == "ready_to_provision", str(local_ready))
    expect(local_ready["ready_to_provision"] is True, str(local_ready))
    expect(local_ready["eligible_worker_count"] == 1, str(local_ready))
    expect(local_ready["available_slots"] == 3, str(local_ready))
    expect(local_ready["proof_gate"] == "PG-FLEET/PG-PROVISION", str(local_ready))
    expect("no SSH" in local_ready["note"], str(local_ready))

    remote_pending = dashboard.control_node_provisioning_readiness(
        conn,
        env={"ARCLINK_CONTROL_PROVISIONER_ENABLED": "1", "ARCLINK_EXECUTOR_ADAPTER": "ssh"},
    )
    expect(remote_pending["state"] == "pending_ssh", str(remote_pending))
    expect(remote_pending["ready_to_provision"] is False, str(remote_pending))
    expect(any(item["name"] == "ssh_key" for item in remote_pending["blockers"]), str(remote_pending))

    remote_ready = dashboard.control_node_provisioning_readiness(
        conn,
        env={
            "ARCLINK_CONTROL_PROVISIONER_ENABLED": "1",
            "ARCLINK_EXECUTOR_ADAPTER": "ssh",
            "ARCLINK_EXECUTOR_MACHINE_MODE_ENABLED": "1",
            "ARCLINK_ACTION_WORKER_SSH_HOST": "local-worker.example.test",
            "ARCLINK_EXECUTOR_MACHINE_HOST_ALLOWLIST": "local-worker.example.test",
            "ARCLINK_FLEET_SSH_KEY_PATH": "/tmp/arclink-fake-fleet-key",
        },
    )
    expect(remote_ready["state"] == "ready_to_provision", str(remote_ready))
    expect(remote_ready["ready_to_provision"] is True, str(remote_ready))
    expect(remote_ready["eligible_workers"][0]["hostname"] == "local-worker.example.test", str(remote_ready))

    view = dashboard.read_arclink_admin_dashboard(conn)
    expect("provisioning_readiness" in view, str(view.keys()))
    expect("ready_to_provision" in view["provisioning_readiness"], str(view["provisioning_readiness"]))
    scale = dashboard.build_scale_operations_snapshot(conn)
    expect("provisioning_readiness" in scale, str(scale.keys()))
    expect(scale["provisioner"]["status"] == scale["provisioning_readiness"]["state"], str(scale["provisioner"]))
    print("PASS test_control_node_provisioning_readiness_surfaces_worker_capacity_without_live_probe")


def main() -> int:
    test_admin_action_requires_reason_and_queues_audited_intent()
    test_admin_action_idempotency_reuses_intent_without_duplicate_audit()
    test_admin_action_rejects_unwired_action_types()
    test_admin_action_accepts_reprovision_as_executable()
    test_admin_action_metadata_rejects_plaintext_secrets_and_has_no_live_side_effects()
    test_admin_refund_and_cancel_actions_record_audited_notes()
    test_admin_dashboard_exposes_action_execution_readiness()
    test_admin_action_readiness_publishes_source_owned_support_matrix()
    test_admin_action_matrix_marks_academy_apply_preview_queueable_but_pg_hermes_gated()
    test_admin_action_queue_enforces_per_action_target_kinds()
    test_control_node_provisioning_readiness_surfaces_worker_capacity_without_live_probe()
    print("PASS all 10 ArcLink admin action tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
