#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
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


def _queue_action(dashboard, conn, action_type="restart", target_id="dep_1", target_kind="deployment", key=None, metadata=None):
    import secrets
    return dashboard.queue_arclink_admin_action(
        conn,
        admin_id="admin_1",
        action_type=action_type,
        target_kind=target_kind,
        target_id=target_id,
        reason="test action",
        idempotency_key=key or secrets.token_hex(8),
        metadata=metadata,
    )


def _fake_executor(executor_mod):
    return executor_mod.ArcLinkExecutor(
        config=executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
    )


def test_restart_action_through_fake_executor() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_restart")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_restart")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_restart")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_restart")
    conn = memory_db(control)
    _queue_action(dashboard, conn, action_type="restart")
    executor = _fake_executor(executor_mod)
    result = worker.process_next_arclink_action(conn, executor=executor)
    expect(result is not None, "result returned")
    expect(result["status"] == "succeeded", f"restart succeeded, got {result['status']}")
    expect(result["action_type"] == "restart", "correct action type")
    # Verify intent status updated
    row = conn.execute("SELECT status FROM arclink_action_intents WHERE action_id = ?", (result["action_id"],)).fetchone()
    expect(row["status"] == "succeeded", "intent marked succeeded")
    print("PASS test_restart_action_through_fake_executor")


def test_dns_repair_through_fake_executor() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_dns")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_dns")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_dns")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_dns")
    conn = memory_db(control)
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_1",
        user_id="user_dns_explicit",
        prefix="dns-explicit",
        base_domain="example.test",
        status="provisioning_ready",
    )
    dns_metadata = {"dns": {"web": {"hostname": "test.arclink.online", "record_type": "CNAME", "target": "origin.arclink.online"}}}
    _queue_action(dashboard, conn, action_type="dns_repair", metadata=dns_metadata)
    executor = _fake_executor(executor_mod)
    result = worker.process_next_arclink_action(conn, executor=executor)
    expect(result["status"] == "succeeded", "dns repair succeeded")
    print("PASS test_dns_repair_through_fake_executor")


def test_action_worker_links_admin_action_to_executor_operation() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_operation_link")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_operation_link")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_operation_link")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_operation_link")
    conn = memory_db(control)
    action = _queue_action(dashboard, conn, action_type="restart", target_id="dep_link", key="operator-restart-link-1")
    result = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod))
    expect(result["status"] == "succeeded", str(result))
    expect(result["result"]["operation_kind"] == "docker_compose_lifecycle", str(result))
    row = conn.execute(
        """
        SELECT * FROM arclink_action_operation_links
        WHERE action_id = ? AND operation_kind = ? AND idempotency_key = ?
        """,
        (action["action_id"], "docker_compose_lifecycle", "operator-restart-link-1"),
    ).fetchone()
    expect(row is not None, "expected action-operation link")
    expect(row["target_kind"] == "deployment" and row["target_id"] == "dep_link", str(dict(row)))
    print("PASS test_action_worker_links_admin_action_to_executor_operation")


def test_dns_repair_derives_records_from_control_rows() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_dns_derive")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_dns_derive")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_dns_derive")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_dns_derive")
    ingress = load_module("arclink_ingress.py", "arclink_ingress_aw_dns_derive")
    conn = memory_db(control)
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_dns_derive",
        user_id="user_dns",
        prefix="dns-derive",
        base_domain="example.test",
        status="provisioning_ready",
        metadata={"edge_target": "edge.example.test"},
    )
    ingress.persist_arclink_dns_records(
        conn,
        deployment_id="dep_dns_derive",
        records=ingress.desired_arclink_dns_records(
            prefix="dns-derive",
            base_domain="example.test",
            target="edge.example.test",
        ),
    )
    _queue_action(dashboard, conn, action_type="dns_repair", target_id="dep_dns_derive", metadata={})
    result = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod))
    expect(result["status"] == "succeeded", str(result))
    records = set(result["result"]["records"])
    expect("u-dns-derive.example.test" in records, str(records))
    expect("hermes-dns-derive.example.test" in records, str(records))
    print("PASS test_dns_repair_derives_records_from_control_rows")


def test_dns_repair_missing_deployment_fails_closed() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_dns_missing")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_dns_missing")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_dns_missing")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_dns_missing")
    conn = memory_db(control)
    _queue_action(dashboard, conn, action_type="dns_repair", target_id="dep_missing", metadata={})
    result = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod))
    expect(result["status"] == "failed", str(result))
    expect("deployment was not found" in result["error"], str(result))
    expect("sk_" not in result["error"], str(result))
    print("PASS test_dns_repair_missing_deployment_fails_closed")


def test_dns_repair_validation_error_redacts_secret_material() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_dns_secret")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_dns_secret")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_dns_secret")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_dns_secret")
    conn = memory_db(control)
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_dns_secret",
        user_id="user_dns",
        prefix="dns-secret",
        base_domain="example.test",
        status="provisioning_ready",
    )
    conn.execute(
        """
        INSERT INTO arclink_action_intents (
          action_id, admin_id, action_type, target_kind, target_id, status,
          idempotency_key, reason, metadata_json, created_at, updated_at
        ) VALUES (
          'act_dns_secret', 'admin_1', 'dns_repair', 'deployment', 'dep_dns_secret', 'queued',
          'dns-secret-key', 'test redaction', ?, '2026-05-11T00:00:00+00:00', '2026-05-11T00:00:00+00:00'
        )
        """,
        (json.dumps({
            "dns": {
                "web": {
                    "hostname": "u-dns-secret.example.test",
                    "record_type": "sk_test_secretvalue123",
                    "target": "edge.example.test",
                }
            }
        }),),
    )
    conn.commit()
    result = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod))
    expect(result["status"] == "failed", str(result))
    expect("unsupported ArcLink DNS record type" in result["error"], str(result))
    expect("sk_test_secretvalue123" not in result["error"], str(result))
    print("PASS test_dns_repair_validation_error_redacts_secret_material")


def test_dns_repair_derives_records_from_deployment_when_rows_empty() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_dns_dep")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_dns_dep")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_dns_dep")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_dns_dep")
    conn = memory_db(control)
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_dns_dep",
        user_id="user_dns",
        prefix="dns-dep",
        base_domain="example.test",
        status="provisioning_ready",
        metadata={"edge_target": "edge.example.test"},
    )
    _queue_action(dashboard, conn, action_type="dns_repair", target_id="dep_dns_dep", metadata={})
    result = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod))
    expect(result["status"] == "succeeded", str(result))
    records = set(result["result"]["records"])
    expect("u-dns-dep.example.test" in records, str(records))
    print("PASS test_dns_repair_derives_records_from_deployment_when_rows_empty")


def test_rotate_chutes_key_uses_secret_ref() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_keyrot")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_keyrot")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_keyrot")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_keyrot")
    conn = memory_db(control)
    _queue_action(dashboard, conn, action_type="rotate_chutes_key", metadata={"secret_ref": "secret://arclink/chutes/dep_1"})
    executor = _fake_executor(executor_mod)
    result = worker.process_next_arclink_action(conn, executor=executor)
    expect(result["status"] == "succeeded", "chutes key rotation succeeded")
    expect("key_id" in result.get("result", {}), "key_id in result")
    print("PASS test_rotate_chutes_key_uses_secret_ref")


def test_refund_through_stripe_fake() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_refund")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_refund")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_refund")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_refund")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_refund", stripe_customer_id="cus_refund", entitlement_state="paid")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_refund",
        user_id="user_refund",
        prefix="refund-test",
        base_domain="example.test",
        status="provisioning_ready",
    )
    _queue_action(dashboard, conn, action_type="refund", target_id="dep_refund")
    executor = _fake_executor(executor_mod)
    result = worker.process_next_arclink_action(conn, executor=executor)
    expect(result["status"] == "succeeded", "refund succeeded")
    expect(result["result"]["target_resolved_by"] == "control_db", str(result))
    print("PASS test_refund_through_stripe_fake")


def test_cancel_through_stripe_fake() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_cancel")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_cancel")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_cancel")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_cancel")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_cancel", stripe_customer_id="cus_cancel", entitlement_state="paid")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_cancel",
        user_id="user_cancel",
        prefix="cancel-test",
        base_domain="example.test",
        status="provisioning_ready",
    )
    control.upsert_arclink_subscription_mirror(
        conn,
        subscription_id="subrow_cancel",
        user_id="user_cancel",
        stripe_customer_id="cus_cancel",
        stripe_subscription_id="sub_cancel",
        status="active",
    )
    _queue_action(dashboard, conn, action_type="cancel", target_id="dep_cancel")
    executor = _fake_executor(executor_mod)
    result = worker.process_next_arclink_action(conn, executor=executor)
    expect(result["status"] == "succeeded", "cancel succeeded")
    print("PASS test_cancel_through_stripe_fake")


def test_refund_missing_customer_fails_closed() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_refund_missing")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_refund_missing")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_refund_missing")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_refund_missing")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_refund_missing", entitlement_state="paid")
    _queue_action(
        dashboard,
        conn,
        action_type="refund",
        target_id="user_refund_missing",
        target_kind="user",
        metadata={"stripe_customer_ref": "secret://arclink/stripe/customer/user_refund_missing"},
    )
    result = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod))
    expect(result["status"] == "failed", str(result))
    expect("Stripe customer" in result["error"], str(result))
    print("PASS test_refund_missing_customer_fails_closed")


def test_cancel_missing_subscription_fails_closed() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_cancel_missing")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_cancel_missing")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_cancel_missing")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_cancel_missing")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_cancel_missing", stripe_customer_id="cus_missing", entitlement_state="paid")
    _queue_action(
        dashboard,
        conn,
        action_type="cancel",
        target_id="user_cancel_missing",
        target_kind="user",
        metadata={"stripe_customer_id": "cus_missing"},
    )
    result = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod))
    expect(result["status"] == "failed", str(result))
    expect("Stripe subscription" in result["error"], str(result))
    expect("cus_missing" not in result["error"], str(result))
    print("PASS test_cancel_missing_subscription_fails_closed")


def test_comp_applies_entitlement_gate() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_comp")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_comp")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_comp")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_comp")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_comp", entitlement_state="none")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_comp",
        user_id="user_comp",
        prefix="comp-test",
        base_domain="example.test",
        status="entitlement_required",
    )
    _queue_action(dashboard, conn, action_type="comp", target_id="dep_comp")
    executor = _fake_executor(executor_mod)
    result = worker.process_next_arclink_action(conn, executor=executor)
    expect(result["status"] == "succeeded", f"comp applied, got {result['status']}")
    expect(result["result"]["status"] == "applied", str(result))
    row = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_comp'").fetchone()
    expect(row["status"] == "provisioning_ready", str(dict(row)))
    print("PASS test_comp_applies_entitlement_gate")


def test_comp_replay_does_not_duplicate_audit() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_comp_replay")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_comp_replay")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_comp_replay")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_comp_replay")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_comp_replay", entitlement_state="none")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_comp_replay",
        user_id="user_comp_replay",
        prefix="comp-replay",
        base_domain="example.test",
        status="entitlement_required",
    )
    _queue_action(dashboard, conn, action_type="comp", target_id="dep_comp_replay", key="comp-replay-1")
    _queue_action(dashboard, conn, action_type="comp", target_id="dep_comp_replay", key="comp-replay-2")
    results = worker.process_arclink_action_batch(conn, executor=_fake_executor(executor_mod), batch_size=2)
    expect([result["status"] for result in results] == ["succeeded", "succeeded"], str(results))
    audits = conn.execute(
        "SELECT COUNT(*) AS c FROM arclink_audit_log WHERE action = 'comp_subscription'"
    ).fetchone()
    expect(int(audits["c"]) == 1, str(audits["c"]))
    print("PASS test_comp_replay_does_not_duplicate_audit")


def test_batch_processing() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_batch")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_batch")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_batch")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_batch")
    conn = memory_db(control)
    for i in range(3):
        _queue_action(dashboard, conn, action_type="restart", target_id=f"dep_{i}")
    executor = _fake_executor(executor_mod)
    results = worker.process_arclink_action_batch(conn, executor=executor, batch_size=10)
    expect(len(results) == 3, f"processed 3 actions, got {len(results)}")
    expect(all(r["status"] == "succeeded" for r in results), "all succeeded")
    print("PASS test_batch_processing")


def test_empty_queue_returns_none() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_empty")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_empty")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_empty")
    conn = memory_db(control)
    executor = _fake_executor(executor_mod)
    result = worker.process_next_arclink_action(conn, executor=executor)
    expect(result is None, "empty queue returns None")
    print("PASS test_empty_queue_returns_none")


def test_action_attempt_recorded() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_att")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_att")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_att")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_att")
    conn = memory_db(control)
    _queue_action(dashboard, conn, action_type="restart")
    executor = _fake_executor(executor_mod)
    result = worker.process_next_arclink_action(conn, executor=executor)
    attempts = worker.list_action_attempts(conn, action_id=result["action_id"])
    expect(len(attempts) == 1, "one attempt recorded")
    expect(attempts[0]["status"] == "succeeded", "attempt marked succeeded")
    print("PASS test_action_attempt_recorded")


def test_concurrent_workers_claim_action_once() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_claim")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_claim")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_claim")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_claim")

    class SlowExecutor:
        config = executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake")

        def __init__(self) -> None:
            self.calls = 0
            self.lock = threading.Lock()

        def docker_compose_lifecycle(self, request):
            with self.lock:
                self.calls += 1
            time.sleep(0.2)
            return executor_mod.DockerComposeLifecycleResult(
                deployment_id=request.deployment_id,
                live=False,
                status="completed",
                action=request.action,
            )

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "actions.sqlite3"
        setup = sqlite3.connect(db_path, timeout=15.0)
        setup.row_factory = sqlite3.Row
        control.ensure_schema(setup)
        queued = _queue_action(dashboard, setup, action_type="restart", key="claim_once")
        setup.close()

        executor = SlowExecutor()
        barrier = threading.Barrier(2)
        results: list[dict | None] = []
        errors: list[BaseException] = []
        result_lock = threading.Lock()

        def run_worker(name: str) -> None:
            conn = sqlite3.connect(db_path, timeout=15.0)
            conn.row_factory = sqlite3.Row
            try:
                barrier.wait()
                result = worker.process_next_arclink_action(conn, executor=executor, worker_id=name)
                with result_lock:
                    results.append(result)
            except BaseException as exc:
                with result_lock:
                    errors.append(exc)
            finally:
                conn.close()

        threads = [
            threading.Thread(target=run_worker, args=("worker_a",)),
            threading.Thread(target=run_worker, args=("worker_b",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        expect(not errors, f"worker errors: {errors}")
        processed = [r for r in results if r is not None]
        expect(len(processed) == 1, f"exactly one worker should process the action, got {results}")
        expect(executor.calls == 1, f"side effect should run once, got {executor.calls}")

        verify = sqlite3.connect(db_path, timeout=15.0)
        verify.row_factory = sqlite3.Row
        row = verify.execute(
            "SELECT status, worker_id, claimed_at FROM arclink_action_intents WHERE action_id = ?",
            (queued["action_id"],),
        ).fetchone()
        verify.close()
        expect(row["status"] == "succeeded", str(dict(row)))
        expect(row["worker_id"] in {"worker_a", "worker_b"}, str(dict(row)))
        expect(bool(row["claimed_at"]), str(dict(row)))
    print("PASS test_concurrent_workers_claim_action_once")


def test_attempt_audit_is_persisted_before_side_effect() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_audit_order")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_audit_order")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_audit_order")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_audit_order")
    conn = memory_db(control)
    _queue_action(dashboard, conn, action_type="restart")
    observed: list[str] = []

    class OrderingExecutor:
        config = executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake")

        def docker_compose_lifecycle(self, request):
            attempts = conn.execute(
                "SELECT COUNT(*) AS c FROM arclink_action_attempts WHERE status = 'running'"
            ).fetchone()
            audits = conn.execute(
                "SELECT COUNT(*) AS c FROM arclink_audit_log WHERE action = 'action_worker_attempt_started:restart'"
            ).fetchone()
            expect(int(attempts["c"]) == 1, "running attempt must be durable before side effect")
            expect(int(audits["c"]) == 1, "attempt audit must be durable before side effect")
            observed.append("side_effect")
            raise RuntimeError("provider failed after ordering proof")

    result = worker.process_next_arclink_action(conn, executor=OrderingExecutor(), worker_id="worker_order")
    expect(result["status"] == "failed", str(result))
    expect(observed == ["side_effect"], str(observed))
    attempts = worker.list_action_attempts(conn, action_id=result["action_id"])
    expect(attempts[0]["status"] == "failed", str(attempts[0]))
    audits = conn.execute(
        "SELECT COUNT(*) AS c FROM arclink_audit_log WHERE action = 'action_worker_attempt_started:restart'"
    ).fetchone()
    expect(int(audits["c"]) == 1, "pre-side-effect audit should remain after failure")
    print("PASS test_attempt_audit_is_persisted_before_side_effect")


def test_stale_action_recovery() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_stale")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_stale")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_stale")
    conn = memory_db(control)
    intent = _queue_action(dashboard, conn, action_type="restart")
    # Manually set to running with old timestamp
    conn.execute(
        "UPDATE arclink_action_intents SET status = 'running', updated_at = '2020-01-01T00:00:00+00:00' WHERE action_id = ?",
        (intent["action_id"],),
    )
    conn.commit()
    recovered = worker.recover_stale_actions(conn, stale_threshold_seconds=60)
    expect(len(recovered) == 1, "one stale action recovered")
    expect(recovered[0]["new_status"] == "queued", "returned to queued")
    row = conn.execute("SELECT status FROM arclink_action_intents WHERE action_id = ?", (intent["action_id"],)).fetchone()
    expect(row["status"] == "queued", "intent status returned to queued")
    print("PASS test_stale_action_recovery")


def test_idempotent_retry() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_idem")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_idem")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_idem")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_idem")
    conn = memory_db(control)
    _queue_action(dashboard, conn, action_type="restart", key="idem_1")
    executor = _fake_executor(executor_mod)
    r1 = worker.process_next_arclink_action(conn, executor=executor)
    expect(r1["status"] == "succeeded", "first run succeeded")
    # Re-queue same key should return existing
    existing = dashboard.queue_arclink_admin_action(
        conn,
        admin_id="admin_1",
        action_type="restart",
        target_kind="deployment",
        target_id="dep_1",
        reason="test action",
        idempotency_key="idem_1",
    )
    expect(existing["status"] == "succeeded", "idempotent re-queue returns existing result")
    print("PASS test_idempotent_retry")


def test_executor_error_secret_material_is_redacted() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_secret_err")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_secret_err")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_secret_err")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_secret_err")
    conn = memory_db(control)
    _queue_action(dashboard, conn, action_type="restart")

    class FailingExecutor:
        config = executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake")

        def docker_compose_lifecycle(self, request):
            raise RuntimeError("provider failed with sk_test_secretvalue123")

    result = worker.process_next_arclink_action(conn, executor=FailingExecutor())
    expect(result["status"] == "failed", "failed action returned")
    expect(result["error_code"] == "unexpected_error", str(result))
    expect("sk_test_secretvalue123" not in result["error"], f"secret leaked in returned error: {result}")
    attempts = worker.list_action_attempts(conn, action_id=result["action_id"])
    expect("sk_test_secretvalue123" not in attempts[0]["error"], f"secret leaked in stored attempt: {attempts[0]}")
    print("PASS test_executor_error_secret_material_is_redacted")


def test_action_worker_returns_safe_error_code_for_executor_errors() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_error_code")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_error_code")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_error_code")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_error_code")
    conn = memory_db(control)
    _queue_action(dashboard, conn, action_type="restart")

    class FailingExecutor:
        config = executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake")

        def docker_compose_lifecycle(self, request):
            raise executor_mod.ArcLinkExecutorError("provider unavailable")

    result = worker.process_next_arclink_action(conn, executor=FailingExecutor())
    expect(result["status"] == "failed", str(result))
    expect(result["error_code"] == "executor_error", str(result))
    event = conn.execute(
        "SELECT metadata_json FROM arclink_events WHERE event_type = 'action_failed:restart'"
    ).fetchone()
    metadata = json.loads(event["metadata_json"])
    expect(metadata["error_code"] == "executor_error", str(metadata))
    print("PASS test_action_worker_returns_safe_error_code_for_executor_errors")


def test_legacy_unwired_action_rows_fail_safely() -> None:
    """Legacy rows for not-yet-wired action types fail instead of staying queueable."""
    control = load_module("arclink_control.py", "arclink_control_aw_pending_all")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_pending_all")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_pending_all")
    conn = memory_db(control)
    unwired_types = ["suspend", "unsuspend", "reprovision", "rollout", "force_resynth", "rotate_bot_key"]
    now = control.utc_now_iso()
    for action_type in unwired_types:
        conn.execute(
            """
            INSERT INTO arclink_action_intents (
              action_id, admin_id, action_type, target_kind, target_id, status,
              idempotency_key, reason, metadata_json, created_at, updated_at
            ) VALUES (?, 'admin_1', ?, 'deployment', ?, 'queued', ?, 'legacy unsupported action', '{}', ?, ?)
            """,
            (
                f"act_legacy_{action_type}",
                action_type,
                f"dep_{action_type}",
                f"legacy-{action_type}",
                now,
                now,
            ),
        )
    conn.commit()
    executor = _fake_executor(executor_mod)
    results = worker.process_arclink_action_batch(conn, executor=executor, batch_size=10)
    expect(len(results) == len(unwired_types), f"processed {len(unwired_types)} actions, got {len(results)}")
    for r in results:
        expect(
            r["status"] == "failed",
            f"{r['action_type']} should fail safely, got {r['status']}",
        )
        expect(
            "unsupported action type" in r["error"],
            f"{r['action_type']} should report unsupported action, got {r}",
        )
    statuses = conn.execute("SELECT status FROM arclink_action_intents").fetchall()
    expect(all(row["status"] == "failed" for row in statuses), str([dict(row) for row in statuses]))
    print("PASS test_legacy_unwired_action_rows_fail_safely")


def test_fake_executor_live_flag_is_false() -> None:
    """Fake executor adapters must set live=False."""
    executor_mod = load_module("arclink_executor.py", "arclink_executor_live_flag")
    executor = _fake_executor(executor_mod)
    result = executor.docker_compose_lifecycle(executor_mod.DockerComposeLifecycleRequest(
        deployment_id="dep_test", action="restart",
    ))
    expect(result.live is False, f"fake lifecycle live should be False, got {result.live}")

    dns_result = executor.cloudflare_dns_apply(executor_mod.CloudflareDnsApplyRequest(
        deployment_id="dep_test",
        dns={"web": {"hostname": "test.example.com", "record_type": "CNAME", "target": "origin.example.com"}},
    ))
    expect(dns_result.live is False, f"fake DNS live should be False, got {dns_result.live}")

    access_result = executor.cloudflare_access_apply(executor_mod.CloudflareAccessApplyRequest(
        deployment_id="dep_test",
        access={"urls": {"dashboard": "https://dash.example.com"}, "ssh": {"strategy": "cloudflare_access_tcp", "hostname": "ssh.example.com"}},
    ))
    expect(access_result.live is False, f"fake access live should be False, got {access_result.live}")

    chutes_result = executor.chutes_key_apply(executor_mod.ChutesKeyApplyRequest(
        deployment_id="dep_test", action="create", secret_ref="secret://arclink/chutes/dep_test",
    ))
    expect(chutes_result.live is False, f"fake Chutes live should be False, got {chutes_result.live}")

    rollback_result = executor.rollback_apply(executor_mod.RollbackApplyRequest(
        deployment_id="dep_test",
        plan={"actions": ["preserve_state_roots", "stop_rendered_services"], "services": {"app": {}}},
    ))
    expect(rollback_result.live is False, f"fake rollback live should be False, got {rollback_result.live}")

    print("PASS test_fake_executor_live_flag_is_false")


def test_disabled_action_worker_cli_exits_cleanly() -> None:
    load_module("arclink_control.py", "arclink_control_aw_disabled_cli")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_disabled_cli")
    old_env = os.environ.copy()
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ARCLINK_DB_PATH"] = str(Path(tmp) / "arclink-control.sqlite3")
        os.environ["ARCLINK_EXECUTOR_ADAPTER"] = "disabled"
        try:
            rc = worker.main(["--once", "--json"])
            expect(rc == 0, f"disabled action worker should exit cleanly, got {rc}")
            print("PASS test_disabled_action_worker_cli_exits_cleanly")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_action_worker_ssh_executor_requires_machine_mode_and_allowlist() -> None:
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_ssh_policy")
    base_env = {
        "ARCLINK_EXECUTOR_ADAPTER": "ssh",
        "ARCLINK_ACTION_WORKER_SSH_HOST": "worker.example.test",
    }
    try:
        worker._executor_from_env(base_env)
    except worker.ArcLinkActionWorkerError as exc:
        expect("MACHINE_MODE" in str(exc), str(exc))
    else:
        raise AssertionError("expected SSH executor without machine-mode opt-in to fail")

    try:
        worker._executor_from_env({**base_env, "ARCLINK_EXECUTOR_MACHINE_MODE_ENABLED": "1"})
    except worker.ArcLinkActionWorkerError as exc:
        expect("HOST_ALLOWLIST" in str(exc), str(exc))
    else:
        raise AssertionError("expected SSH executor without host allowlist to fail")

    executor = worker._executor_from_env(
        {
            **base_env,
            "ARCLINK_EXECUTOR_MACHINE_MODE_ENABLED": "1",
            "ARCLINK_EXECUTOR_MACHINE_HOST_ALLOWLIST": "worker.example.test",
        }
    )
    expect(executor.config.adapter_name == "ssh", str(executor.config))
    expect(executor.docker_runner.allowed_hosts == ("worker.example.test",), str(executor.docker_runner))
    print("PASS test_action_worker_ssh_executor_requires_machine_mode_and_allowlist")


def test_action_worker_main_reuses_single_db_connection_for_once_batch() -> None:
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_db_reuse")
    calls: list[str] = []

    class ConnContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    original_db_connect = worker._db_connect
    original_executor_from_env = worker._executor_from_env
    original_recover = worker.recover_stale_actions
    original_process = worker.process_arclink_action_batch
    old_env = os.environ.copy()
    try:
        os.environ["ARCLINK_EXECUTOR_ADAPTER"] = "fake"
        worker._db_connect = lambda path: calls.append(path) or ConnContext()
        worker._executor_from_env = lambda env: object()
        worker.recover_stale_actions = lambda conn: []
        worker.process_arclink_action_batch = lambda conn, **kwargs: []
        rc = worker.main(["--once", "--json", "--db", "/tmp/arclink-test.sqlite3"])
        expect(rc == 0, f"expected clean once run, got {rc}")
        expect(calls == ["/tmp/arclink-test.sqlite3"], str(calls))
    finally:
        worker._db_connect = original_db_connect
        worker._executor_from_env = original_executor_from_env
        worker.recover_stale_actions = original_recover
        worker.process_arclink_action_batch = original_process
        os.environ.clear()
        os.environ.update(old_env)
    print("PASS test_action_worker_main_reuses_single_db_connection_for_once_batch")


if __name__ == "__main__":
    test_restart_action_through_fake_executor()
    test_dns_repair_through_fake_executor()
    test_action_worker_links_admin_action_to_executor_operation()
    test_dns_repair_derives_records_from_control_rows()
    test_dns_repair_missing_deployment_fails_closed()
    test_dns_repair_validation_error_redacts_secret_material()
    test_dns_repair_derives_records_from_deployment_when_rows_empty()
    test_rotate_chutes_key_uses_secret_ref()
    test_refund_through_stripe_fake()
    test_cancel_through_stripe_fake()
    test_refund_missing_customer_fails_closed()
    test_cancel_missing_subscription_fails_closed()
    test_comp_applies_entitlement_gate()
    test_comp_replay_does_not_duplicate_audit()
    test_batch_processing()
    test_empty_queue_returns_none()
    test_action_attempt_recorded()
    test_concurrent_workers_claim_action_once()
    test_attempt_audit_is_persisted_before_side_effect()
    test_stale_action_recovery()
    test_idempotent_retry()
    test_executor_error_secret_material_is_redacted()
    test_action_worker_returns_safe_error_code_for_executor_errors()
    test_legacy_unwired_action_rows_fail_safely()
    test_fake_executor_live_flag_is_false()
    test_disabled_action_worker_cli_exits_cleanly()
    test_action_worker_ssh_executor_requires_machine_mode_and_allowlist()
    test_action_worker_main_reuses_single_db_connection_for_once_batch()
    print(f"\nAll 29 action worker tests passed.")
