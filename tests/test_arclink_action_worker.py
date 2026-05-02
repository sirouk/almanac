#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
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


def _queue_action(dashboard, conn, action_type="restart", target_id="dep_1", key=None, metadata=None):
    import secrets
    return dashboard.queue_arclink_admin_action(
        conn,
        admin_id="admin_1",
        action_type=action_type,
        target_kind="deployment",
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
    control = load_module("almanac_control.py", "almanac_control_aw_restart")
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
    control = load_module("almanac_control.py", "almanac_control_aw_dns")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_dns")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_dns")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_dns")
    conn = memory_db(control)
    dns_metadata = {"dns": {"web": {"hostname": "test.arclink.online", "record_type": "CNAME", "target": "origin.arclink.online"}}}
    _queue_action(dashboard, conn, action_type="dns_repair", metadata=dns_metadata)
    executor = _fake_executor(executor_mod)
    result = worker.process_next_arclink_action(conn, executor=executor)
    expect(result["status"] == "succeeded", "dns repair succeeded")
    print("PASS test_dns_repair_through_fake_executor")


def test_rotate_chutes_key_uses_secret_ref() -> None:
    control = load_module("almanac_control.py", "almanac_control_aw_keyrot")
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
    control = load_module("almanac_control.py", "almanac_control_aw_refund")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_refund")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_refund")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_refund")
    conn = memory_db(control)
    _queue_action(dashboard, conn, action_type="refund")
    executor = _fake_executor(executor_mod)
    result = worker.process_next_arclink_action(conn, executor=executor)
    expect(result["status"] == "succeeded", "refund succeeded")
    print("PASS test_refund_through_stripe_fake")


def test_cancel_through_stripe_fake() -> None:
    control = load_module("almanac_control.py", "almanac_control_aw_cancel")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_cancel")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_cancel")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_cancel")
    conn = memory_db(control)
    _queue_action(dashboard, conn, action_type="cancel")
    executor = _fake_executor(executor_mod)
    result = worker.process_next_arclink_action(conn, executor=executor)
    expect(result["status"] == "succeeded", "cancel succeeded")
    print("PASS test_cancel_through_stripe_fake")


def test_comp_local_state() -> None:
    control = load_module("almanac_control.py", "almanac_control_aw_comp")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_comp")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_comp")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_comp")
    conn = memory_db(control)
    _queue_action(dashboard, conn, action_type="comp")
    executor = _fake_executor(executor_mod)
    result = worker.process_next_arclink_action(conn, executor=executor)
    expect(result["status"] == "succeeded", "comp succeeded")
    print("PASS test_comp_local_state")


def test_batch_processing() -> None:
    control = load_module("almanac_control.py", "almanac_control_aw_batch")
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
    control = load_module("almanac_control.py", "almanac_control_aw_empty")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_empty")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_empty")
    conn = memory_db(control)
    executor = _fake_executor(executor_mod)
    result = worker.process_next_arclink_action(conn, executor=executor)
    expect(result is None, "empty queue returns None")
    print("PASS test_empty_queue_returns_none")


def test_action_attempt_recorded() -> None:
    control = load_module("almanac_control.py", "almanac_control_aw_att")
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


def test_stale_action_recovery() -> None:
    control = load_module("almanac_control.py", "almanac_control_aw_stale")
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
    control = load_module("almanac_control.py", "almanac_control_aw_idem")
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
    control = load_module("almanac_control.py", "almanac_control_aw_secret_err")
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
    expect("sk_test_secretvalue123" not in result["error"], f"secret leaked in returned error: {result}")
    attempts = worker.list_action_attempts(conn, action_id=result["action_id"])
    expect("sk_test_secretvalue123" not in attempts[0]["error"], f"secret leaked in stored attempt: {attempts[0]}")
    print("PASS test_executor_error_secret_material_is_redacted")


if __name__ == "__main__":
    test_restart_action_through_fake_executor()
    test_dns_repair_through_fake_executor()
    test_rotate_chutes_key_uses_secret_ref()
    test_refund_through_stripe_fake()
    test_cancel_through_stripe_fake()
    test_comp_local_state()
    test_batch_processing()
    test_empty_queue_returns_none()
    test_action_attempt_recorded()
    test_stale_action_recovery()
    test_idempotent_retry()
    test_executor_error_secret_material_is_redacted()
    print(f"\nAll 12 action worker tests passed.")
