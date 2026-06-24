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
    # Establish the local-dev env so the LLM router-key hash pepper (sec-C1) uses
    # its documented dev fallback instead of fail-closing. Mirrors the canonical
    # arclink_test_helpers.memory_db / the session-pepper tests.
    os.environ.setdefault("ARCLINK_CONFIG_FILE", os.devnull)
    os.environ["ARCLINK_BASE_DOMAIN"] = "example.test"
    os.environ.pop("ARCLINK_LLM_ROUTER_KEY_HASH_PEPPER_REQUIRED", None)
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


class _PermissiveSecretResolver:
    def __init__(self, executor_mod):
        self.executor_mod = executor_mod

    def materialize(self, secret_ref: str, target_path: str):
        return self.executor_mod.ResolvedSecretFile(secret_ref=secret_ref, target_path=target_path)


def _fake_executor_with_secrets(executor_mod):
    return executor_mod.ArcLinkExecutor(
        config=executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
        secret_resolver=_PermissiveSecretResolver(executor_mod),
    )


class _NoSideEffectExecutor:
    def __init__(self, executor_mod):
        self.config = executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake")

    def __getattr__(self, name: str):
        def fail(*args, **kwargs):
            raise AssertionError(f"rollout local materialization must not call executor method {name}")

        return fail


def _rollout_state_roots(deployment_id: str) -> dict[str, str]:
    root = f"/arcdata/deployments/{deployment_id}"
    return {
        "root": root,
        "config": f"{root}/config",
        "state": f"{root}/state",
        "vault": f"{root}/vault",
        "hermes_home": f"{root}/state/hermes-home",
    }


def _seed_rollout_arcpod(
    control,
    conn,
    *,
    deployment_id: str,
    current_version: str = "v1.0.0",
    health_status: str = "healthy",
) -> None:
    user_id = f"user_{deployment_id}"
    control.upsert_arclink_user(
        conn,
        user_id=user_id,
        email=f"{deployment_id}@example.test",
        entitlement_state="paid",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id=deployment_id,
        user_id=user_id,
        prefix=f"{deployment_id.replace('_', '-')}-pod",
        base_domain="example.test",
        status="active",
        metadata={
            "release_version": current_version,
            "state_roots": _rollout_state_roots(deployment_id),
            "dashboard_password": f"secret://arclink/deployments/{deployment_id}/dashboard",
        },
    )
    for service_name in ("hermes-gateway", "hermes-dashboard", "qmd-mcp"):
        control.upsert_arclink_service_health(
            conn,
            deployment_id=deployment_id,
            service_name=service_name,
            status=health_status,
        )


def _seed_academy_apply_preview(control, conn, academy) -> dict[str, str]:
    user_id = "user_academy_preview"
    recipe_id = "crew_academy_preview"
    control.upsert_arclink_user(
        conn,
        user_id=user_id,
        email="academy-preview@example.test",
        entitlement_state="paid",
    )
    source = academy.fake_academy_source(
        source_id="src-worker-academy",
        lane_id="wikimedia",
        title="Worker Academy Source",
        origin_url="https://example.test/wiki/worker-academy",
        retrieved_at="2026-05-27T00:00:00Z",
        license_status="cc-by-sa",
        permission_status="public_allowed",
        storage_policy="derived_summary",
        content="Academy worker previews must record readiness without applying files.",
        citations=["worker source", "preview source", "no-write source"],
        metadata={"revision": "worker-academy-1", "official": True, "examples": True},
    )
    manifest = academy.build_academy_corpus(
        role_id="role-worker-academy",
        role_title="Worker Academy Agent",
        topic="Academy action worker previews",
        sources=[source],
        created_at="2026-05-27T01:00:00Z",
    )
    application = academy.build_agent_application_plan(
        manifest,
        agent_id="agent-worker-academy",
        created_at="2026-05-27T02:00:00Z",
    )
    status = academy.build_academy_review_status(
        manifest=manifest,
        application_plan=application,
        staged_at="2026-05-27T03:00:00Z",
    )
    status["recipe_id"] = recipe_id
    status["review_persisted"] = True
    conn.execute(
        """
        INSERT INTO arclink_crew_recipes (
          recipe_id, user_id, preset, capacity, role, mission, treatment,
          soul_overlay_json, applied_at, archived_at, status
        ) VALUES (?, ?, 'Frontier', 'development', 'founder', 'ship safely', 'peer', ?, ?, '', 'active')
        """,
        (
            recipe_id,
            user_id,
            json.dumps({"crew_recipe_text": "Crew Recipe", "academy_training": status}, sort_keys=True),
            "2026-05-27T03:00:00+00:00",
        ),
    )
    conn.commit()
    return {
        "user_id": user_id,
        "recipe_id": recipe_id,
        "manifest_id": manifest.manifest_id,
        "application_plan_id": application.plan_id,
        "agent_id": "agent-worker-academy",
    }


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
    row = conn.execute(
        """
        SELECT hostname, record_type, target, status
        FROM arclink_dns_records
        WHERE deployment_id = 'dep_1'
        """
    ).fetchone()
    expect(row is not None, "explicit DNS repair should persist control-plane DNS tracking")
    expect(row["hostname"] == "test.arclink.online", str(dict(row)))
    expect(row["status"] == "provisioned", str(dict(row)))
    print("PASS test_dns_repair_through_fake_executor")


def test_dns_repair_backfills_provider_record_ids_after_apply() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_dns_provider_id")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_dns_provider_id")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_dns_provider_id")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_dns_provider_id")
    conn = memory_db(control)
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_dns_provider",
        user_id="user_dns_provider",
        prefix="dns-provider",
        base_domain="example.test",
        status="provisioning_ready",
    )
    dns_metadata = {
        "dns": {
            "dashboard": {
                "hostname": "u-dns-provider.example.test",
                "record_type": "CNAME",
                "target": "edge.example.test",
            }
        }
    }
    _queue_action(dashboard, conn, action_type="dns_repair", target_id="dep_dns_provider", metadata=dns_metadata)

    class ProviderIdExecutor:
        def __init__(self):
            self.config = executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake")

        def cloudflare_dns_apply(self, request):
            return executor_mod.CloudflareDnsApplyResult(
                deployment_id=request.deployment_id,
                live=True,
                status="applied",
                records=("u-dns-provider.example.test",),
                metadata={"provider_record_ids": ("cf_record_1",)},
            )

    result = worker.process_next_arclink_action(conn, executor=ProviderIdExecutor())
    expect(result["status"] == "succeeded", str(result))
    row = conn.execute(
        "SELECT status, provider_record_id FROM arclink_dns_records WHERE deployment_id = 'dep_dns_provider'"
    ).fetchone()
    expect(row["status"] == "provisioned", str(dict(row)))
    expect(row["provider_record_id"] == "cf_record_1", str(dict(row)))
    print("PASS test_dns_repair_backfills_provider_record_ids_after_apply")


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


def test_restart_action_rejects_lifecycle_path_overrides_by_default() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_restart_path_guard")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_restart_path_guard")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_restart_path_guard")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_restart_path_guard")
    conn = memory_db(control)
    _queue_action(
        dashboard,
        conn,
        action_type="restart",
        metadata={
            "project_name": "arclink-outside",
            "env_file": "/tmp/outside.env",
            "compose_file": "/tmp/outside-compose.yaml",
        },
    )
    result = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod))
    expect(result is not None, "expected failed action result")
    expect(result["status"] == "failed", str(result))
    expect("metadata override" in result["error"] and "ARCLINK_ACTION_WORKER_ALLOW_LIFECYCLE_PATH_OVERRIDES" in result["error"], str(result))
    print("PASS test_restart_action_rejects_lifecycle_path_overrides_by_default")


def test_restart_action_lifecycle_path_overrides_require_explicit_operator_flag() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_restart_path_override")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_restart_path_override")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_restart_path_override")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_restart_path_override")
    conn = memory_db(control)
    _queue_action(
        dashboard,
        conn,
        action_type="restart",
        metadata={
            "project_name": "arclink-emergency",
            "env_file": "/tmp/emergency.env",
            "compose_file": "/tmp/emergency-compose.yaml",
        },
    )

    class RecordingExecutor:
        def __init__(self):
            self.config = executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake")
            self.request = None

        def docker_compose_lifecycle(self, request):
            self.request = request
            return executor_mod.DockerComposeLifecycleResult(
                deployment_id=request.deployment_id,
                live=False,
                status="completed",
                action=request.action,
            )

    executor = RecordingExecutor()
    result = worker.process_next_arclink_action(
        conn,
        executor=executor,
        env={"ARCLINK_ACTION_WORKER_ALLOW_LIFECYCLE_PATH_OVERRIDES": "1"},
    )
    expect(result is not None and result["status"] == "succeeded", str(result))
    expect(executor.request is not None, "expected lifecycle request")
    expect(executor.request.project_name == "arclink-emergency", str(executor.request))
    expect(executor.request.env_file == "/tmp/emergency.env", str(executor.request))
    expect(executor.request.compose_file == "/tmp/emergency-compose.yaml", str(executor.request))
    print("PASS test_restart_action_lifecycle_path_overrides_require_explicit_operator_flag")


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
    statuses = {
        row["hostname"]: row["status"]
        for row in conn.execute(
            "SELECT hostname, status FROM arclink_dns_records WHERE deployment_id = 'dep_dns_derive'"
        ).fetchall()
    }
    expect(statuses == {
        "u-dns-derive.example.test": "provisioned",
        "hermes-dns-derive.example.test": "provisioned",
    }, str(statuses))
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
    rows = conn.execute("SELECT * FROM arclink_dns_records WHERE deployment_id = 'dep_dns_secret'").fetchall()
    expect(len(rows) == 0, str([dict(row) for row in rows]))
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
    rows = conn.execute(
        "SELECT hostname, status FROM arclink_dns_records WHERE deployment_id = 'dep_dns_dep'"
    ).fetchall()
    statuses = {row["hostname"]: row["status"] for row in rows}
    expect(statuses == {
        "u-dns-dep.example.test": "provisioned",
        "hermes-dns-dep.example.test": "provisioned",
    }, str(statuses))
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


def test_stripe_entitlement_recovery_action_dry_run_and_apply() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_stripe_recovery")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_stripe_recovery")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_stripe_recovery")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_stripe_recovery")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_stripe_recovery", entitlement_state="none")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_stripe_recovery",
        user_id="user_stripe_recovery",
        prefix="recover-aw",
        base_domain="example.test",
        status="entitlement_required",
    )
    _queue_action(
        dashboard,
        conn,
        action_type="stripe_entitlement_recovery",
        target_kind="user",
        target_id="user_stripe_recovery",
        key="stripe-recovery-dry-run",
        metadata={
            "dry_run": True,
            "actor_id": "operator:admin_1",
            "stripe_customer_id": "cus_action_recovery_full",
            "stripe_subscription_id": "sub_action_recovery_full",
        },
    )
    dry_result = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod))
    user = conn.execute("SELECT entitlement_state, stripe_customer_id FROM arclink_users WHERE user_id = 'user_stripe_recovery'").fetchone()
    dry_audit = conn.execute(
        "SELECT metadata_json FROM arclink_audit_log WHERE action = 'stripe_entitlement_recovery_dry_run' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    expect(dry_result["status"] == "succeeded", str(dry_result))
    expect(dry_result["result"]["status"] == "planned" and dry_result["result"]["dry_run"] is True, str(dry_result))
    expect(user["entitlement_state"] == "none" and user["stripe_customer_id"] == "", str(dict(user)))
    expect(dry_audit is not None, "expected dry-run recovery audit")
    expect("cus_action_recovery_full" not in dry_audit["metadata_json"], dry_audit["metadata_json"])
    expect("sub_action_recovery_full" not in dry_audit["metadata_json"], dry_audit["metadata_json"])

    _queue_action(
        dashboard,
        conn,
        action_type="stripe_entitlement_recovery",
        target_kind="user",
        target_id="user_stripe_recovery",
        key="stripe-recovery-apply",
        metadata={
            "actor_id": "operator:admin_1",
            "reason": "verified Stripe recovery import",
            "stripe_customer_id": "cus_action_recovery_full",
            "stripe_subscription_id": "sub_action_recovery_full",
        },
    )
    applied_result = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod))
    user = conn.execute("SELECT entitlement_state, stripe_customer_id FROM arclink_users WHERE user_id = 'user_stripe_recovery'").fetchone()
    dep = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_stripe_recovery'").fetchone()
    sub = conn.execute("SELECT status, user_id FROM arclink_subscriptions WHERE stripe_subscription_id = 'sub_action_recovery_full'").fetchone()
    applied_audit = conn.execute(
        "SELECT reason, metadata_json FROM arclink_audit_log WHERE action = 'stripe_entitlement_recovery_applied' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    link = conn.execute(
        "SELECT operation_kind FROM arclink_action_operation_links WHERE idempotency_key = 'stripe-recovery-apply'"
    ).fetchone()
    expect(applied_result["status"] == "succeeded", str(applied_result))
    expect(applied_result["result"]["status"] == "applied", str(applied_result))
    expect(user["entitlement_state"] == "paid" and user["stripe_customer_id"] == "cus_action_recovery_full", str(dict(user)))
    expect(dep["status"] == "provisioning_ready", str(dict(dep)))
    expect(sub["status"] == "active" and sub["user_id"] == "user_stripe_recovery", str(dict(sub)))
    expect(applied_audit["reason"] == "verified Stripe recovery import", str(dict(applied_audit)))
    expect("cus_action_recovery_full" not in applied_audit["metadata_json"], applied_audit["metadata_json"])
    expect("sub_action_recovery_full" not in applied_audit["metadata_json"], applied_audit["metadata_json"])
    expect(link["operation_kind"] == "control_db_stripe_entitlement_recovery", str(dict(link)))
    print("PASS test_stripe_entitlement_recovery_action_dry_run_and_apply")


def test_backup_write_check_fails_closed_without_authorized_runner() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_backup_verify")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_backup_verify")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_backup_verify")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_backup_verify")
    conn = memory_db(control)
    public_key = "ssh-ed25519 " + ("A" * 80) + " arclink-agent-backup-test"
    control.upsert_arclink_user(conn, user_id="user_backup_verify", entitlement_state="paid")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_backup_verify",
        user_id="user_backup_verify",
        prefix="backup-verify",
        base_domain="example.test",
        status="active",
        metadata={
            "backup_owner_repo": "owner/private-agent-backup",
            "backup_deploy_key_public": public_key,
            "backup_deploy_key_status": "staged_pending_github_install",
            "backup_github_write_check": "not_run",
            "backup_activation": "active",
        },
    )
    action = _queue_action(
        dashboard,
        conn,
        action_type="backup_write_check",
        target_id="dep_backup_verify",
        key="backup-write-check-1",
        metadata={"activate_after_verify": True},
    )
    result = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod))
    expect(result["status"] == "failed_closed", str(result))
    expect(result["result"]["status"] == "failed_closed", str(result))
    expect(result["result"]["operation_kind"] == "backup_git_write_check", str(result))
    expect("PG-BACKUP" in result["result"]["note"], str(result))

    intent = conn.execute("SELECT status FROM arclink_action_intents WHERE action_id = ?", (action["action_id"],)).fetchone()
    expect(intent["status"] == "failed", str(dict(intent)))
    row = conn.execute("SELECT metadata_json FROM arclink_deployments WHERE deployment_id = 'dep_backup_verify'").fetchone()
    metadata = json.loads(row["metadata_json"])
    expect(metadata["backup_github_write_check"] == "failed_closed", str(metadata))
    expect(metadata["backup_activation"] == "not_active", str(metadata))
    expect("PG-BACKUP" in metadata["backup_github_write_check_reason"], str(metadata))
    link = conn.execute(
        """
        SELECT * FROM arclink_action_operation_links
        WHERE action_id = ? AND operation_kind = 'backup_git_write_check'
        """,
        (action["action_id"],),
    ).fetchone()
    expect(link is not None and link["idempotency_key"] == "backup-write-check-1", str(link))
    print("PASS test_backup_write_check_fails_closed_without_authorized_runner")


def test_academy_apply_preview_action_records_no_write_result_without_executor() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_academy_preview")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_academy_preview")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_academy_preview")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_academy_preview")
    academy = load_module("arclink_academy_trainer.py", "arclink_academy_aw_preview")
    conn = memory_db(control)
    seeded = _seed_academy_apply_preview(control, conn, academy)
    action = _queue_action(
        dashboard,
        conn,
        action_type="academy_apply_preview",
        target_kind="user",
        target_id=seeded["user_id"],
        key="academy-preview-action-1",
        metadata={
            "recipe_id": seeded["recipe_id"],
            "manifest_id": seeded["manifest_id"],
            "application_plan_id": seeded["application_plan_id"],
            "agent_id": seeded["agent_id"],
            "local_only": True,
            "no_write": True,
            "writes_enabled": False,
            "proof_gates": ["PG-PROVIDER", "PG-HERMES"],
        },
    )
    result = worker.process_next_arclink_action(conn, executor=_NoSideEffectExecutor(executor_mod))
    expect(result is not None and result["status"] == "succeeded", str(result))
    preview = result["result"]
    expect(preview["status"] == "ready_for_application_proof", str(preview))
    expect(preview["operation_kind"] == "academy_application_preview", str(preview))
    expect(preview["no_write"] is True and preview["writes_enabled"] is False, str(preview))
    expect(preview["mutation_performed"] is False, str(preview))
    expect(preview["workspace_mutation_performed"] is False, str(preview))
    expect(preview["filesystem_mutation_performed"] is False, str(preview))
    expect(preview["executor_called"] is False, str(preview))
    expect({"PG-PROVIDER", "PG-HERMES"} <= set(preview["proof_gates"]), str(preview))
    expect("content" not in json.dumps(preview, sort_keys=True).casefold(), str(preview))

    link = conn.execute(
        """
        SELECT * FROM arclink_action_operation_links
        WHERE action_id = ? AND operation_kind = 'academy_application_preview'
        """,
        (action["action_id"],),
    ).fetchone()
    expect(link is not None and link["idempotency_key"] == "academy-preview-action-1", str(link))
    event_types = [row["event_type"] for row in conn.execute("SELECT event_type FROM arclink_events ORDER BY created_at").fetchall()]
    expect("academy_application_preview_recorded" in event_types, str(event_types))
    audit_actions = [row["action"] for row in conn.execute("SELECT action FROM arclink_audit_log ORDER BY created_at").fetchall()]
    expect("academy_application_preview_recorded" in audit_actions, str(audit_actions))
    print("PASS test_academy_apply_preview_action_records_no_write_result_without_executor")


def test_academy_apply_preview_action_fails_closed_on_workspace_write_request() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_academy_preview_fail")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_academy_preview_fail")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_academy_preview_fail")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_academy_preview_fail")
    academy = load_module("arclink_academy_trainer.py", "arclink_academy_aw_preview_fail")
    conn = memory_db(control)
    seeded = _seed_academy_apply_preview(control, conn, academy)
    action = _queue_action(
        dashboard,
        conn,
        action_type="academy_apply_preview",
        target_kind="user",
        target_id=seeded["user_id"],
        key="academy-preview-action-fail-1",
        metadata={
            "recipe_id": seeded["recipe_id"],
            "manifest_id": seeded["manifest_id"],
            "application_plan_id": seeded["application_plan_id"],
            "agent_id": seeded["agent_id"],
            "local_only": True,
            "no_write": True,
            "writes_enabled": True,
            "workspace_path": "/home/user/.local/share/arclink-agent/hermes-home/SOUL.md",
            "proof_gates": ["PG-PROVIDER", "PG-HERMES"],
        },
    )
    result = worker.process_next_arclink_action(conn, executor=_NoSideEffectExecutor(executor_mod))
    expect(result is not None and result["status"] == "failed", str(result))
    expect("workspace" in result["error"].casefold() or "writes_enabled" in result["error"].casefold(), str(result))
    expect("SOUL.md" not in result["error"], str(result))
    intent = conn.execute("SELECT status FROM arclink_action_intents WHERE action_id = ?", (action["action_id"],)).fetchone()
    expect(intent["status"] == "failed", str(dict(intent)))
    links = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_operation_links").fetchone()
    expect(int(links["n"]) == 0, str(dict(links)))
    print("PASS test_academy_apply_preview_action_fails_closed_on_workspace_write_request")


def _seed_academy_graduate(control, conn, programs) -> dict[str, str]:
    user_id = "user_academy_apply"
    deployment_id = "dep_academy_apply"
    control.upsert_arclink_user(conn, user_id=user_id, email="academy-apply@example.test", entitlement_state="paid")
    programs.seed_default_academy_programs(conn)
    trainee = programs.enroll_academy_trainee(
        conn, program_id="systems_practice_engineer", user_id=user_id, deployment_id=deployment_id, name="Apply Grace"
    )
    session = programs.open_academy_mode(conn, trainee_id=trainee["trainee_id"], opened_by=user_id)
    programs.record_academy_resource_proposal(
        conn,
        deployment_id=deployment_id,
        lane_id="web_article",
        title="Apply gate source",
        origin_url="https://example.test/academy-apply-source",
        summary="Compressed source notes that allow the Academy trainee to graduate before apply.",
        proposed_by="agent-apply",
    )
    programs.end_academy_mode(conn, session_id=session["session"]["session_id"], actor=user_id, graduate=True)
    return {"user_id": user_id, "deployment_id": deployment_id, "trainee_id": trainee["trainee_id"]}


def test_academy_apply_action_stages_fail_closed_without_authorization() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_academy_apply")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_academy_apply")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_academy_apply")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_academy_apply")
    programs = load_module("arclink_academy_programs.py", "arclink_academy_programs_aw_apply")
    conn = memory_db(control)
    seeded = _seed_academy_graduate(control, conn, programs)
    action = _queue_action(
        dashboard,
        conn,
        action_type="academy_apply",
        target_kind="deployment",
        target_id=seeded["deployment_id"],
        key="academy-apply-action-1",
        metadata={"trainee_id": seeded["trainee_id"]},
    )
    result = worker.process_next_arclink_action(conn, executor=_NoSideEffectExecutor(executor_mod))
    expect(result is not None and result["status"] == "succeeded", str(result))
    applied = result["result"]
    # Fake adapter -> staged, never writes.
    expect(applied["status"] == "staged", str(applied))
    expect(applied["operation_kind"] == "academy_agent_apply", str(applied))
    expect(applied["writes_enabled"] is False, str(applied))
    expect(applied["mutation_performed"] is False and applied["filesystem_mutation_performed"] is False, str(applied))
    expect({"PG-PROVIDER", "PG-HERMES"} <= set(applied["proof_gates"]), str(applied))
    expect("content" not in json.dumps(applied, sort_keys=True).casefold(), str(applied))
    link = conn.execute(
        """
        SELECT * FROM arclink_action_operation_links
        WHERE action_id = ? AND operation_kind = 'academy_agent_apply'
        """,
        (action["action_id"],),
    ).fetchone()
    expect(link is not None and link["idempotency_key"] == "academy-apply-action-1", str(link))
    audit_actions = [row["action"] for row in conn.execute("SELECT action FROM arclink_audit_log ORDER BY created_at").fetchall()]
    expect("academy_agent_apply_recorded" in audit_actions, str(audit_actions))
    print("PASS test_academy_apply_action_stages_fail_closed_without_authorization")


def test_academy_apply_action_materializes_local_hermes_home_when_authorized() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_academy_apply_live")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_academy_apply_live")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_academy_apply_live")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_academy_apply_live")
    programs = load_module("arclink_academy_programs.py", "arclink_academy_programs_aw_apply_live")
    org_profile = load_module("arclink_org_profile.py", "arclink_org_profile_aw_academy_apply_live")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir) / "dep-academy-live"
        roots = {
            "root": str(root),
            "config": str(root / "config"),
            "state": str(root / "state"),
            "vault": str(root / "vault"),
            "hermes_home": str(root / "state" / "hermes-home"),
        }
        hermes_home = Path(roots["hermes_home"])
        hermes_home.mkdir(parents=True)
        (hermes_home / "SOUL.md").write_text("# SOUL\nHuman-authored identity.\n", encoding="utf-8")
        (hermes_home / "sessions").mkdir(parents=True)
        (hermes_home / "sessions" / "sessions.json").write_text(
            json.dumps(
                {
                    "agent:main:telegram:dm:captain": {
                        "session_key": "agent:main:telegram:dm:captain",
                        "session_id": "pre_academy_session",
                    }
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        user_id = "user_academy_live"
        deployment_id = "dep_academy_live"
        control.upsert_arclink_user(conn, user_id=user_id, email="academy-live@example.test", entitlement_state="paid")
        control.reserve_arclink_deployment_prefix(
            conn,
            deployment_id=deployment_id,
            user_id=user_id,
            prefix="academy-live",
            base_domain="example.test",
            status="active",
            metadata={"state_roots": roots},
        )
        programs.seed_default_academy_programs(conn)
        charter = programs.build_charter(
            {
                "subject_scope": "Systems practice engineering for fleet operations",
                "acceptance_scenarios": [
                    {"prompt": "Diagnose a failing deploy from the logs and cite the governed runbook.", "pass_criteria": ["cite a governed source"]}
                ],
                "boundaries": ["never reveal the captain's private infrastructure secrets"],
            },
            program=programs.get_academy_program(conn, "systems_practice_engineer"),
        )
        trainee = programs.enroll_academy_trainee(
            conn, program_id="systems_practice_engineer", user_id=user_id, deployment_id=deployment_id,
            name="Apply Live", captain_steer={"charter_json": charter},
        )
        session = programs.open_academy_mode(conn, trainee_id=trainee["trainee_id"], opened_by=user_id)
        programs.record_academy_resource_proposal(
            conn,
            deployment_id=deployment_id,
            lane_id="github_repository",
            title="Live apply source",
            origin_url="https://example.test/live-apply",
            summary="Compressed source notes for the materialized Academy overlay.",
            proposed_by="agent-live",
        )
        programs.end_academy_mode(conn, session_id=session["session"]["session_id"], actor=user_id, graduate=True)

        # M2 fail-closed gate (arclink_academy_programs.py): a live apply no longer rides
        # the central capsule -- it requires the trainee's OWN fresh live-authored PRIVATE
        # synthesis PLUS a PASSED acceptance exam bound to that synthesis. Establish both
        # here so "authorized" means fully authorized under the M2 writes_enabled gate.
        class _ApplyLivePrivate:
            live = True

            def synthesize(self, *, role_title, topic, charter, sources):
                return {
                    "engine": "live-router",
                    "authored": True,
                    "lesson_notes": [
                        {"source_uid": s["source_uid"], "note": f"Authored specialist note for {role_title}."}
                        for s in sources
                    ],
                    "soul_capsule": "You are a Systems Practice Engineer specialist. Cite a governed source before any operational claim.",
                    "retrieval_rules": ["cite a governed source before answering"],
                    "quality_metrics": {},
                }

        programs.run_academy_trainer_synthesize(
            conn, trainee_id=trainee["trainee_id"], scope="private",
            client=_ApplyLivePrivate(), live_authorized=True,
        )
        programs.run_academy_acceptance_exam(
            conn, trainee_id=trainee["trainee_id"],
            agent_runner=programs.FakeAgentRunner(live=True), live_authorized=True,
        )
        action = _queue_action(
            dashboard,
            conn,
            action_type="academy_apply",
            target_kind="deployment",
            target_id=deployment_id,
            key="academy-apply-live-1",
            metadata={"trainee_id": trainee["trainee_id"]},
        )
        executor = executor_mod.ArcLinkExecutor(
            config=executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="local"),
        )
        result = worker.process_next_arclink_action(
            conn,
            executor=executor,
            env={"ARCLINK_ACADEMY_APPLY_LIVE": "1"},
        )
        expect(result is not None and result["status"] == "succeeded", str(result))
        applied = result["result"]
        expect(applied["status"] == "applied_hermes_home", str(applied))
        expect(applied["writes_enabled"] is True and applied["mutation_performed"] is True, str(applied))
        expect(applied["filesystem_mutation_performed"] is True, str(applied))
        expect(any(path.startswith("vault/Academy/") for path in applied["applied_paths"]), str(applied))
        expect("state/arclink-academy-memory-seeds.json" in applied["applied_paths"], str(applied))
        expect("state/arclink-academy-post-apply-refresh.json" in applied["applied_paths"], str(applied))
        expect("state/arclink-academy-session-reset.json" in applied["applied_paths"], str(applied))
        expect(applied["session_reset"]["status"] == "reset", str(applied["session_reset"]))
        expect(applied["session_reset"]["removed_session_count"] == 1, str(applied["session_reset"]))
        expect(json.loads((hermes_home / "sessions" / "sessions.json").read_text(encoding="utf-8")) == {}, "Academy apply must reset pre-Academy Hermes sessions")
        session_reset_file = json.loads((hermes_home / "state" / "arclink-academy-session-reset.json").read_text(encoding="utf-8"))
        expect(session_reset_file["reason"] == "academy_apply_equipped_soul", str(session_reset_file))
        refresh_request = applied["post_apply_refresh_request"]
        expect(refresh_request["status"] == "requested", str(refresh_request))
        expect(refresh_request["deployment_id"] == deployment_id, str(refresh_request))
        refresh_result = applied["post_apply_refresh_result"]
        expect(refresh_result["status"] == "queued", str(refresh_result))
        expect("SOUL.md" in refresh_result["verified_paths"], str(refresh_result))
        expect(refresh_result["missing_paths"] == [], str(refresh_result))
        refresh_kinds = {item["kind"]: item for item in refresh_request["refreshes"]}
        expect(refresh_kinds["qmd_index"]["status"] == "requested", str(refresh_kinds))
        expect(refresh_kinds["memory_synthesis"]["status"] == "requested", str(refresh_kinds))
        expect(refresh_kinds["skill_activation"]["status"] in {"staged", "not_requested"}, str(refresh_kinds))
        expect(refresh_kinds["skill_activation"]["skill_count"] == len(applied["approved_skill_intents"]), str(refresh_kinds))
        soul = (hermes_home / "SOUL.md").read_text(encoding="utf-8")
        expect("Human-authored identity." in soul, soul)
        expect(org_profile.BEGIN_ACADEMY_MARKER in soul and "Systems Practice Engineer specialist" in soul, soul)
        state = json.loads((hermes_home / "state" / "arclink-academy-apply.json").read_text(encoding="utf-8"))
        expect(state["trainee_id"] == trainee["trainee_id"], str(state))
        expect(state["qmd_memory_seed_intents"], str(state))
        expect(state["post_apply_refresh_request"]["request_id"] == refresh_request["request_id"], str(state))
        refresh_file = json.loads((hermes_home / "state" / "arclink-academy-post-apply-refresh.json").read_text(encoding="utf-8"))
        expect(refresh_file["request_id"] == refresh_request["request_id"], str(refresh_file))
        expect(refresh_file["status"] == "queued", str(refresh_file))
        expect({item["status"] for item in refresh_file["refreshes"]} <= {"queued", "staged", "not_requested", "recorded"}, str(refresh_file))
        expect("Docker" in refresh_file["queue_policy"] and "inline" in refresh_file["queue_policy"], str(refresh_file))
        expect((hermes_home / "state" / "arclink-academy-qmd-refresh-request.json").is_file(), str(refresh_file))
        expect((hermes_home / "state" / "arclink-academy-memory-synthesis-request.json").is_file(), str(refresh_file))
        # The queue markers are no longer write-only: each names its consumer
        # and whether it stays runner-gated.
        memory_marker = json.loads((hermes_home / "state" / "arclink-academy-memory-synthesis-request.json").read_text(encoding="utf-8"))
        expect(memory_marker["status"] == "queued" and "memory-synth" in memory_marker["consumer"], str(memory_marker))
        qmd_marker = json.loads((hermes_home / "state" / "arclink-academy-qmd-refresh-request.json").read_text(encoding="utf-8"))
        expect(qmd_marker["runner_gated"] is True and "runner-gated" in qmd_marker["consumer"], str(qmd_marker))
        # academy_apply records central skill enablement intents alongside the
        # Approved_Skills.md audit artifact.
        enablement_rows = control.list_agent_skill_enablement(conn, deployment_id=deployment_id)
        expect(len(enablement_rows) == len(applied["approved_skill_intents"]), str(enablement_rows))
        if enablement_rows:
            expect(enablement_rows[0]["status"] == "approved", str(enablement_rows))
            expect(enablement_rows[0]["source"].startswith("academy:"), str(enablement_rows))
            expect(bool(enablement_rows[0]["provenance_hash"]), str(enablement_rows))
        refresh_job = conn.execute(
            "SELECT * FROM refresh_jobs WHERE job_name = ?",
            (f"academy-post-apply-refresh:{deployment_id}",),
        ).fetchone()
        expect(refresh_job is not None, "Academy apply should record a control-plane post-apply refresh job")
        expect(refresh_job["target_id"] == deployment_id and refresh_job["last_status"] == "queued" and refresh_request["request_id"] in refresh_job["last_note"], str(dict(refresh_job)))
        runner_calls: list[dict[str, str]] = []

        def _proof_runner(payload: dict[str, object]) -> dict[str, object]:
            runner_calls.append({key: str(payload.get(key) or "") for key in ("kind", "deployment_id", "request_id")})
            return {"status": "succeeded", "summary": "local injected proof runner completed"}

        consumed = worker.run_academy_post_apply_refresh(
            conn,
            deployment_id=deployment_id,
            qmd_runner=_proof_runner,
            memory_runner=_proof_runner,
            skill_runner=_proof_runner,
            requested_by="test:academy-refresh",
        )
        expect(consumed["status"] == "succeeded", str(consumed))
        expect({"qmd_index", "memory_synthesis"} <= {item["kind"] for item in runner_calls}, str(runner_calls))
        refreshed_file = json.loads((hermes_home / "state" / "arclink-academy-post-apply-refresh.json").read_text(encoding="utf-8"))
        expect(refreshed_file["status"] == "succeeded", str(refreshed_file))
        expect("secret://" not in json.dumps(refreshed_file, sort_keys=True), str(refreshed_file))
        tampered = dict(refreshed_file)
        tampered["applied_paths"] = ["vault"]
        (hermes_home / "state" / "arclink-academy-post-apply-refresh.json").write_text(
            json.dumps(tampered, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        try:
            worker.run_academy_post_apply_refresh(
                conn,
                deployment_id=deployment_id,
                requested_by="test:academy-refresh-tamper",
            )
        except worker.ArcLinkActionWorkerError as exc:
            expect("no file component" in str(exc), str(exc))
        else:
            raise AssertionError("Academy post-apply refresh should reject root-only applied paths")
        academy_files = list((root / "vault" / "Academy").rglob("*.md"))
        expect(academy_files, "Academy apply should materialize governed vault markdown")
        rendered_vault = "\n".join(path.read_text(encoding="utf-8") for path in academy_files)
        expect("First Week Practice" in rendered_vault and "Source id:" in rendered_vault, rendered_vault)
        link = conn.execute(
            """
            SELECT * FROM arclink_action_operation_links
            WHERE action_id = ? AND operation_kind = 'academy_agent_apply'
            """,
            (action["action_id"],),
        ).fetchone()
        expect(link is not None and link["idempotency_key"] == "academy-apply-live-1", str(link))
        print("PASS test_academy_apply_action_materializes_local_hermes_home_when_authorized")


def test_academy_apply_ssh_materialization_uses_remote_files_not_control_mirror() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_academy_apply_remote_files")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_academy_apply_remote_files")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_academy_apply_remote_files")
    org_profile = load_module("arclink_org_profile.py", "arclink_org_profile_aw_academy_apply_remote_files")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir) / "dep-academy-remote"
        roots = {
            "root": str(root),
            "config": str(root / "config"),
            "state": str(root / "state"),
            "vault": str(root / "vault"),
            "hermes_home": str(root / "state" / "hermes-home"),
        }
        user_id = "user_academy_remote_files"
        deployment_id = "dep_academy_remote_files"
        control.upsert_arclink_user(conn, user_id=user_id, email="academy-remote@example.test", entitlement_state="paid")
        control.reserve_arclink_deployment_prefix(
            conn,
            deployment_id=deployment_id,
            user_id=user_id,
            prefix="academy-remote",
            base_domain="example.test",
            status="active",
            metadata={"state_roots": roots},
        )
        remote_writes: dict[str, str] = {}

        class _FakeAcademyFiles:
            remote = True

            def __init__(self, *, roots, deployment_id, executor):
                self.roots = roots
                self.deployment_id = deployment_id
                self.executor = executor

            def read_text(self, path):
                if str(path).endswith("SOUL.md"):
                    return "# SOUL\nHuman-authored identity.\n"
                return remote_writes.get(str(path), "")

            def write_text(self, path, body):
                remote_writes[str(path)] = str(body)
                return True

            def is_file(self, path):
                return str(path) in remote_writes or str(path).endswith("SOUL.md")

        original_files = worker._AcademyApplyFiles
        worker._AcademyApplyFiles = _FakeAcademyFiles
        try:
            executor = executor_mod.ArcLinkExecutor(
                config=executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="ssh"),
                docker_runner=object(),
            )
            result = worker._materialize_academy_apply(
                conn,
                executor=executor,
                result={
                    "writes_enabled": True,
                    "deployment_id": deployment_id,
                    "user_id": user_id,
                    "trainee_id": "atrn_remote_files",
                    "program_id": "domain_tutor",
                    "manifest_id": "academy-manifest-remote",
                    "plan_id": "academy-plan-remote",
                    "academy_specialist_uid": "private:atrn_remote_files",
                    "academy_capsule_version": 0,
                    "academy_trainer_review_ready": True,
                    "academy_trainer_reviewed_at": "2026-06-24T00:00:00+00:00",
                    "academy_trainer_live_status": "live_authored",
                    "academy_soul_section": org_profile.render_academy_overlay(
                        role_title="Domain Tutor",
                        topic="fitness and nutrition",
                        capsule_body="Coach from the governed Academy notes before answering.",
                    ),
                    "intent_counts": {"vault_file_intents": 1, "qmd_memory_seed_intents": 0, "approved_skill_intents": 0},
                    "vault_file_intents": [{"path": "Academy/domain_tutor/Canon.md", "title": "Canon"}],
                    "qmd_memory_seed_intents": [],
                    "approved_skill_intents": [],
                    "first_week_practice_tasks": [],
                    "evaluation_tasks": [],
                    "proof_gates": ["PG-PROVIDER", "PG-HERMES"],
                    "operation_kind": "academy_agent_apply",
                },
                target_kind="deployment",
                target_id=deployment_id,
                applied_at="2026-06-24T00:00:00+00:00",
            )
        finally:
            worker._AcademyApplyFiles = original_files
        expect(result["status"] == "applied_hermes_home", str(result))
        soul_path = str(Path(roots["hermes_home"]) / "SOUL.md")
        expect(soul_path in remote_writes, str(remote_writes.keys()))
        expect("Human-authored identity." in remote_writes[soul_path], remote_writes[soul_path])
        expect(org_profile.BEGIN_ACADEMY_MARKER in remote_writes[soul_path], remote_writes[soul_path])
        expect(str(Path(roots["vault"]) / "Academy/domain_tutor/Canon.md") in remote_writes, str(remote_writes.keys()))
        expect(str(Path(roots["hermes_home"]) / "state/arclink-academy-apply.json") in remote_writes, str(remote_writes.keys()))
        expect(not (Path(roots["hermes_home"]) / "SOUL.md").exists(), "SSH apply must not write the control mirror path")
        print("PASS test_academy_apply_ssh_materialization_uses_remote_files_not_control_mirror")


def test_reprovision_dispatches_pod_migration() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_reprovision")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_reprovision")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_reprovision")
    provisioning = load_module("arclink_provisioning.py", "arclink_provisioning_aw_reprovision")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_reprovision")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        root_base = Path(tmpdir) / "state"
        roots = provisioning.render_arclink_state_roots(
            deployment_id="dep_reprovision",
            prefix="reprovision-one",
            state_root_base=str(root_base),
        )
        state_root = Path(roots["root"])
        (state_root / "vault").mkdir(parents=True)
        (state_root / "vault" / "note.md").write_text("redeploy me\n", encoding="utf-8")
        now = control.utc_now_iso()
        control.upsert_arclink_user(conn, user_id="user_reprovision", email="owner@example.test", entitlement_state="paid")
        control.reserve_arclink_deployment_prefix(
            conn,
            deployment_id="dep_reprovision",
            user_id="user_reprovision",
            prefix="reprovision-one",
            base_domain="example.test",
            status="active",
            metadata={"state_roots": roots, "state_root_base": str(root_base), "base_domain": "example.test"},
        )
        conn.execute(
            """
            INSERT INTO arclink_fleet_hosts (
              host_id, hostname, status, capacity_slots, observed_load, metadata_json, created_at, updated_at
            ) VALUES ('host_reprovision', 'reprovision.example.test', 'active', 10, 1, ?, ?, ?)
            """,
            (json.dumps({"state_root_base": str(root_base), "edge_target": "edge.example.test"}), now, now),
        )
        conn.execute(
            """
            INSERT INTO arclink_deployment_placements (placement_id, deployment_id, host_id, status, placed_at)
            VALUES ('plc_reprovision', 'dep_reprovision', 'host_reprovision', 'active', ?)
            """,
            (now,),
        )
        conn.execute(
            """
            INSERT INTO arclink_service_health (deployment_id, service_name, status, checked_at, detail_json)
            VALUES ('dep_reprovision', 'gateway', 'healthy', '2999-01-01T00:00:00+00:00', '{}')
            """
        )
        conn.commit()
        action = _queue_action(
            dashboard,
            conn,
            action_type="reprovision",
            target_id="dep_reprovision",
            key="reprovision-action-1",
            metadata={"target_machine_id": "current"},
        )
        result = worker.process_next_arclink_action(
            conn,
            executor=_fake_executor_with_secrets(executor_mod),
            env={
                "ARCLINK_SECRET_STORE_DIR": str(Path(tmpdir) / "secrets"),
                "ARCLINK_LLM_ROUTER_DEFAULT_MODEL": "model-a",
                "ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE": "1",
            },
        )
        expect(result["status"] == "succeeded", str(result))
        migration_row = conn.execute("SELECT * FROM arclink_pod_migrations WHERE deployment_id = 'dep_reprovision'").fetchone()
        expect(migration_row is not None and migration_row["status"] == "succeeded", str(dict(migration_row) if migration_row else None))
        router_key = conn.execute("SELECT * FROM arclink_llm_router_keys WHERE deployment_id = 'dep_reprovision'").fetchone()
        expect(router_key is not None and router_key["secret_ref"] == "secret://arclink/llm-router/dep_reprovision/api-key", str(dict(router_key) if router_key else None))
        expect(str(router_key["key_hash"]).startswith("hmac-sha256$"), str(dict(router_key)))
        link = conn.execute(
            """
            SELECT *
            FROM arclink_action_operation_links
            WHERE action_id = ? AND operation_kind = 'pod_migration'
            """,
            (action["action_id"],),
        ).fetchone()
        expect(link is not None, "expected reprovision action to link to pod_migration")
    print("PASS test_reprovision_dispatches_pod_migration")


def test_reprovision_non_dry_run_requires_root_capture_opt_in() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_reprovision_root_gate")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_reprovision_root_gate")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_reprovision_root_gate")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_reprovision_root_gate")
    conn = memory_db(control)
    _queue_action(
        dashboard,
        conn,
        action_type="reprovision",
        target_id="dep_reprovision_root_gate",
        key="reprovision-root-gate-1",
        metadata={"target_machine_id": "current"},
    )
    result = worker.process_next_arclink_action(conn, executor=_fake_executor_with_secrets(executor_mod))
    expect(result["status"] == "failed", str(result))
    expect("ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE=1" in result["error"], str(result))
    rows = conn.execute("SELECT COUNT(*) AS c FROM arclink_pod_migrations").fetchone()
    expect(int(rows["c"]) == 0, str(dict(rows)))
    print("PASS test_reprovision_non_dry_run_requires_root_capture_opt_in")


def test_reprovision_non_dry_run_requires_migration_capture_helper_in_docker_mode() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_reprovision_helper_gate")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_reprovision_helper_gate")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_reprovision_helper_gate")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_reprovision_helper_gate")
    conn = memory_db(control)
    _queue_action(
        dashboard,
        conn,
        action_type="reprovision",
        target_id="dep_reprovision_helper_gate",
        key="reprovision-helper-gate-1",
        metadata={"target_machine_id": "current"},
    )
    result = worker.process_next_arclink_action(
        conn,
        executor=_fake_executor_with_secrets(executor_mod),
        env={
            "ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE": "1",
            "ARCLINK_DOCKER_MODE": "1",
        },
    )
    expect(result["status"] == "failed", str(result))
    expect("ARCLINK_MIGRATION_CAPTURE_HELPER_URL" in result["error"], str(result))
    rows = conn.execute("SELECT COUNT(*) AS c FROM arclink_pod_migrations").fetchone()
    expect(int(rows["c"]) == 0, str(dict(rows)))
    print("PASS test_reprovision_non_dry_run_requires_migration_capture_helper_in_docker_mode")


def test_reprovision_dry_run_does_not_require_migration_success() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_reprovision_dry")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_reprovision_dry")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_reprovision_dry")
    provisioning = load_module("arclink_provisioning.py", "arclink_provisioning_aw_reprovision_dry")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_reprovision_dry")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        root_base = Path(tmpdir) / "state"
        roots = provisioning.render_arclink_state_roots(
            deployment_id="dep_reprovision_dry",
            prefix="reprovision-dry",
            state_root_base=str(root_base),
        )
        (Path(roots["root"]) / "vault").mkdir(parents=True)
        now = control.utc_now_iso()
        control.upsert_arclink_user(conn, user_id="user_reprovision_dry", email="owner-dry@example.test", entitlement_state="paid")
        control.reserve_arclink_deployment_prefix(
            conn,
            deployment_id="dep_reprovision_dry",
            user_id="user_reprovision_dry",
            prefix="reprovision-dry",
            base_domain="example.test",
            status="active",
            metadata={"state_roots": roots, "state_root_base": str(root_base), "base_domain": "example.test"},
        )
        conn.execute(
            """
            INSERT INTO arclink_fleet_hosts (
              host_id, hostname, status, capacity_slots, observed_load, metadata_json, created_at, updated_at
            ) VALUES ('host_reprovision_dry', 'reprovision-dry.example.test', 'active', 10, 1, ?, ?, ?)
            """,
            (json.dumps({"state_root_base": str(root_base), "edge_target": "edge.example.test"}), now, now),
        )
        conn.execute(
            """
            INSERT INTO arclink_deployment_placements (placement_id, deployment_id, host_id, status, placed_at)
            VALUES ('plc_reprovision_dry', 'dep_reprovision_dry', 'host_reprovision_dry', 'active', ?)
            """,
            (now,),
        )
        conn.commit()
        _queue_action(
            dashboard,
            conn,
            action_type="reprovision",
            target_id="dep_reprovision_dry",
            key="reprovision-action-dry-1",
            metadata={"target_machine_id": "current", "dry_run": True},
        )
        result = worker.process_next_arclink_action(conn, executor=_fake_executor_with_secrets(executor_mod))
        expect(result["status"] == "succeeded", str(result))
        expect(result["result"]["status"] == "planned" and result["result"]["dry_run"] is True, str(result))
        migration_row = conn.execute("SELECT * FROM arclink_pod_migrations WHERE deployment_id = 'dep_reprovision_dry'").fetchone()
        expect(migration_row is not None and migration_row["status"] == "planned", str(dict(migration_row) if migration_row else None))
        placement = conn.execute("SELECT status FROM arclink_deployment_placements WHERE placement_id = 'plc_reprovision_dry'").fetchone()
        expect(placement["status"] == "active", str(dict(placement)))
    print("PASS test_reprovision_dry_run_does_not_require_migration_success")


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


def test_executor_selection_failure_records_failed_attempt() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_select_fail")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_select_fail")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_select_fail")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_select_fail")
    conn = memory_db(control)
    intent = _queue_action(dashboard, conn, action_type="restart")
    original_select = worker._select_action_executor

    def fail_select(*_args, **_kwargs):
        raise RuntimeError("selection failed token=sk-proj-aaaaaaaaaaaaaaaaaaaaaaaa")

    try:
        worker._select_action_executor = fail_select
        result = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod), worker_id="worker_select")
    finally:
        worker._select_action_executor = original_select

    expect(result is not None and result["status"] == "failed", str(result))
    expect(result["attempt_id"], str(result))
    expect("sk-proj-" not in result["error"], str(result))
    row = conn.execute("SELECT status FROM arclink_action_intents WHERE action_id = ?", (intent["action_id"],)).fetchone()
    expect(row["status"] == "failed", dict(row))
    attempts = worker.list_action_attempts(conn, action_id=intent["action_id"])
    expect(len(attempts) == 1 and attempts[0]["status"] == "failed", str(attempts))
    event = conn.execute(
        "SELECT metadata_json FROM arclink_events WHERE event_type = 'action_failed:restart' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    metadata = json.loads(event["metadata_json"])
    expect(metadata.get("phase") == "executor_selection", str(metadata))
    print("PASS test_executor_selection_failure_records_failed_attempt")


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


def test_stale_action_recovery_fails_after_attempt_cap() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_stale_cap")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_stale_cap")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_stale_cap")
    conn = memory_db(control)
    intent = _queue_action(dashboard, conn, action_type="restart")
    conn.execute(
        "UPDATE arclink_action_intents SET status = 'running', updated_at = '2020-01-01T00:00:00+00:00' WHERE action_id = ?",
        (intent["action_id"],),
    )
    for index, status in enumerate(("failed", "failed", "running"), start=1):
        conn.execute(
            """
            INSERT INTO arclink_action_attempts (
              attempt_id, action_id, status, executor_adapter, result_json, error, started_at, finished_at
            ) VALUES (?, ?, ?, 'fake', '{}', '', '2020-01-01T00:00:00+00:00', ?)
            """,
            (f"att_stale_{index}", intent["action_id"], status, "2020-01-01T00:00:00+00:00" if status != "running" else ""),
        )
    conn.commit()
    recovered = worker.recover_stale_actions(conn, stale_threshold_seconds=60, max_attempts=3)
    expect(len(recovered) == 1 and recovered[0]["new_status"] == "failed", str(recovered))
    row = conn.execute("SELECT status FROM arclink_action_intents WHERE action_id = ?", (intent["action_id"],)).fetchone()
    expect(row["status"] == "failed", dict(row))
    running = conn.execute(
        "SELECT COUNT(*) AS n FROM arclink_action_attempts WHERE action_id = ? AND status = 'running'",
        (intent["action_id"],),
    ).fetchone()
    expect(int(running["n"]) == 0, dict(running))
    event = conn.execute("SELECT event_type FROM arclink_events ORDER BY created_at DESC LIMIT 1").fetchone()
    expect(event["event_type"] == "action_stale_failed", dict(event))
    print("PASS test_stale_action_recovery_fails_after_attempt_cap")


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


def test_rollout_action_materializes_ready_three_pod_plan_without_executor_side_effects() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_rollout_ready")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_rollout_ready")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_rollout_ready")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_rollout_ready")
    conn = memory_db(control)
    deployment_ids = ["dep_rollout_a", "dep_rollout_b", "dep_rollout_c"]
    for deployment_id in deployment_ids:
        _seed_rollout_arcpod(control, conn, deployment_id=deployment_id)

    action = _queue_action(
        dashboard,
        conn,
        action_type="rollout",
        target_kind="system",
        target_id="all-arcpods",
        key="rollout-three-pods-worker",
        metadata={"target_version": "v2.0.0", "batch_size": 2, "deployment_ids": deployment_ids},
    )
    result = worker.process_next_arclink_action(conn, executor=_NoSideEffectExecutor(executor_mod))

    expect(result["status"] == "succeeded", str(result))
    expect(result["action_type"] == "rollout", str(result))
    payload = result["result"]
    expect(payload["status"] == "queued_local_job", str(payload))
    expect(payload["operation_kind"] == "arcpod_update_rollout", str(payload))
    expect(payload["operation_idempotency_key"] == "rollout-three-pods-worker", str(payload))
    expect(payload["rollout_count"] == 3, str(payload))
    expect(payload["created_rollout_count"] == 3, str(payload))
    expect(payload["batch_deployment_ids"] == [["dep_rollout_a", "dep_rollout_b"], ["dep_rollout_c"]], str(payload))
    expect(payload["live_mutation_performed"] is False, str(payload))
    expect(payload["proof_gate"] == "PG-UPGRADE/PG-HERMES", str(payload))
    expect("secret://" not in json.dumps(result, sort_keys=True), str(result))

    rows = conn.execute("SELECT * FROM arclink_rollouts ORDER BY created_at ASC, rollout_id ASC").fetchall()
    expect(len(rows) == 3, str([dict(row) for row in rows]))
    metadata = [json.loads(row["metadata_json"]) for row in rows]
    expect([item["batch_index"] for item in metadata] == [1, 1, 2], str(metadata))
    link = conn.execute(
        """
        SELECT * FROM arclink_action_operation_links
        WHERE action_id = ? AND operation_kind = 'arcpod_update_rollout'
        """,
        (action["action_id"],),
    ).fetchone()
    expect(link is not None and link["idempotency_key"] == "rollout-three-pods-worker", str(dict(link) if link else None))
    print("PASS test_rollout_action_materializes_ready_three_pod_plan_without_executor_side_effects")


def test_rollout_action_executes_one_local_batch_when_explicitly_requested() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_rollout_execute")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_rollout_execute")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_rollout_execute")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_rollout_execute")
    conn = memory_db(control)
    deployment_ids = ["dep_rollout_exec_a", "dep_rollout_exec_b", "dep_rollout_exec_c"]
    for deployment_id in deployment_ids:
        _seed_rollout_arcpod(control, conn, deployment_id=deployment_id)

    _queue_action(
        dashboard,
        conn,
        action_type="rollout",
        target_kind="system",
        target_id="all-arcpods",
        key="rollout-execute-local-batch",
        metadata={
            "target_version": "v2.0.0",
            "batch_size": 2,
            "deployment_ids": deployment_ids,
            "execute_local_batch": True,
        },
    )
    result = worker.process_next_arclink_action(conn, executor=_NoSideEffectExecutor(executor_mod))

    expect(result["status"] == "succeeded", str(result))
    payload = result["result"]
    expect(payload["status"] == "executed_local_batch", str(payload))
    expect(payload["batch_execution"]["status"] == "completed", str(payload))
    expect(payload["batch_execution"]["deployment_ids"] == ["dep_rollout_exec_a", "dep_rollout_exec_b"], str(payload))
    expect(payload["batch_execution"]["live_mutation_performed"] is False, str(payload))
    rows = conn.execute("SELECT * FROM arclink_rollouts ORDER BY created_at ASC, rollout_id ASC").fetchall()
    status_by_dep = {row["deployment_id"]: row["status"] for row in rows}
    expect(status_by_dep == {
        "dep_rollout_exec_a": "completed",
        "dep_rollout_exec_b": "completed",
        "dep_rollout_exec_c": "planned",
    }, str(status_by_dep))
    metadata = json.loads(rows[0]["metadata_json"])
    expect(metadata["execution"]["adapter"] == "fake", str(metadata))
    expect(metadata["execution"]["record_only"] is True, str(metadata))
    expect(metadata["health_smoke"]["status"] == "pending_live_proof", str(metadata))
    expect("secret://" not in json.dumps(payload, sort_keys=True), str(payload))
    # GAP-032: an executed rollout batch must attempt a Telegram command-scope
    # refresh for the rolled Pods (best-effort; here it records a safe skip
    # because no bot token or control DB path is configured in the action env).
    refresh = payload.get("telegram_command_scope_refresh")
    expect(isinstance(refresh, dict) and refresh.get("skipped") is True, str(payload.get("telegram_command_scope_refresh")))
    print("PASS test_rollout_action_executes_one_local_batch_when_explicitly_requested")


def test_rollout_action_refuses_blocked_preflight_without_rollout_rows() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_rollout_blocked")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_rollout_blocked")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_rollout_blocked")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_rollout_blocked")
    conn = memory_db(control)
    _seed_rollout_arcpod(control, conn, deployment_id="dep_rollout_ready")
    _seed_rollout_arcpod(control, conn, deployment_id="dep_rollout_blocked", health_status="failed")

    _queue_action(
        dashboard,
        conn,
        action_type="rollout",
        target_kind="system",
        target_id="all-arcpods",
        key="rollout-blocked-worker",
        metadata={"target_version": "v2.0.0", "deployment_ids": ["dep_rollout_ready", "dep_rollout_blocked"]},
    )
    result = worker.process_next_arclink_action(conn, executor=_NoSideEffectExecutor(executor_mod))

    expect(result["status"] == "failed", str(result))
    expect(result["error_code"] == "action_validation_error", str(result))
    expect("ready" in result["error"] or "preflight" in result["error"], str(result))
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_rollouts").fetchone()["n"] == 0, "blocked rollout must not create rows")
    print("PASS test_rollout_action_refuses_blocked_preflight_without_rollout_rows")


def test_rollout_action_idempotent_replay_does_not_duplicate_rollout_rows() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_rollout_idem")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_rollout_idem")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_rollout_idem")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_rollout_idem")
    conn = memory_db(control)
    deployment_ids = ["dep_rollout_idem_a", "dep_rollout_idem_b"]
    for deployment_id in deployment_ids:
        _seed_rollout_arcpod(control, conn, deployment_id=deployment_id)
    metadata = {"target_version": "v2.0.0", "batch_size": 1, "deployment_ids": deployment_ids}

    first_action = _queue_action(
        dashboard,
        conn,
        action_type="rollout",
        target_kind="system",
        target_id="all-arcpods",
        key="rollout-idem-worker",
        metadata=metadata,
    )
    first = worker.process_next_arclink_action(conn, executor=_NoSideEffectExecutor(executor_mod))
    expect(first["status"] == "succeeded", str(first))
    expect(first["result"]["created_rollout_count"] == 2, str(first))

    conn.execute(
        "UPDATE arclink_action_intents SET status = 'queued', worker_id = '', claimed_at = '', updated_at = ? WHERE action_id = ?",
        (control.utc_now_iso(), first_action["action_id"]),
    )
    conn.commit()
    replay = worker.process_next_arclink_action(conn, executor=_NoSideEffectExecutor(executor_mod))

    expect(replay["status"] == "succeeded", str(replay))
    expect(replay["result"]["created_rollout_count"] == 0, str(replay))
    expect(replay["result"]["rollout_ids"] == first["result"]["rollout_ids"], str((first, replay)))
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_rollouts").fetchone()["n"] == 2, "replay must not duplicate rollout rows")
    links = conn.execute(
        "SELECT action_id FROM arclink_action_operation_links WHERE operation_kind = 'arcpod_update_rollout' ORDER BY action_id"
    ).fetchall()
    expect([row["action_id"] for row in links] == [first_action["action_id"]], str([dict(row) for row in links]))
    print("PASS test_rollout_action_idempotent_replay_does_not_duplicate_rollout_rows")


def test_legacy_unwired_action_rows_fail_safely() -> None:
    """Legacy rows for not-yet-wired action types fail instead of staying queueable."""
    control = load_module("arclink_control.py", "arclink_control_aw_pending_all")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_pending_all")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_pending_all")
    conn = memory_db(control)
    unwired_types = ["suspend", "unsuspend", "force_resynth", "rotate_bot_key"]
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


def test_deployment_action_routes_to_active_placement_host() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_route")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_route")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_route")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_route")
    conn = memory_db(control)
    now = control.utc_now_iso()
    conn.execute(
        """
        INSERT INTO arclink_fleet_hosts (
          host_id, hostname, region, tags_json, status, drain, capacity_slots,
          observed_load, metadata_json, created_at, updated_at
        ) VALUES
          ('host_a', 'worker-a.example.test', '', '{}', 'active', 0, 4, 0,
           '{"ssh_host":"10.0.0.41","ssh_user":"arclink"}', ?, ?),
          ('host_b', 'worker-b.example.test', '', '{}', 'active', 0, 4, 0,
           '{"ssh_host":"10.0.0.42","ssh_user":"arclink"}', ?, ?)
        """,
        (now, now, now, now),
    )
    conn.execute("INSERT INTO arclink_deployment_placements (placement_id, deployment_id, host_id, status, placed_at) VALUES ('plc_route', 'dep_route', 'host_b', 'active', ?)", (now,))
    conn.commit()
    _queue_action(dashboard, conn, action_type="restart", target_id="dep_route", key="route-host-b")
    selected_hosts: list[dict[str, object]] = []
    original = worker._executor_for_action_host
    def recording_executor(*, env, host, metadata, cache, deployment_id=""):
        selected_hosts.append(dict(host))
        return _fake_executor(executor_mod)
    try:
        worker._executor_for_action_host = recording_executor
        result = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod), env={"ARCLINK_EXECUTOR_ADAPTER": "ssh"}, executor_cache={})
    finally:
        worker._executor_for_action_host = original
    expect(result["status"] == "succeeded", str(result))
    expect(selected_hosts and selected_hosts[0]["host_id"] == "host_b", str(selected_hosts))
    expect("10.0.0.42" in str(selected_hosts[0]["metadata_json"]), str(selected_hosts))
    audit = conn.execute("SELECT metadata_json FROM arclink_audit_log WHERE action = 'action_worker_attempt_started:restart' ORDER BY created_at DESC LIMIT 1").fetchone()
    metadata = json.loads(audit["metadata_json"])
    expect(metadata["host_id"] == "host_b", str(metadata))
    print("PASS test_deployment_action_routes_to_active_placement_host")


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


def test_action_worker_local_docker_mode_requires_deployment_exec_broker() -> None:
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_local_broker_policy")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_local_broker_policy")
    with tempfile.TemporaryDirectory() as tmp:
        base_env = {
            "ARCLINK_EXECUTOR_ADAPTER": "local",
            "ARCLINK_DOCKER_MODE": "1",
            "ARCLINK_SECRET_STORE_DIR": str(Path(tmp) / "secrets"),
        }
        try:
            worker._executor_from_env(base_env)
        except worker.ArcLinkActionWorkerError as exc:
            expect("DEPLOYMENT_EXEC_BROKER" in str(exc), str(exc))
        else:
            raise AssertionError("expected Docker-mode local action worker without deployment exec broker to fail closed")

        executor = worker._executor_from_env(
            {
                **base_env,
                "ARCLINK_DEPLOYMENT_EXEC_BROKER_URL": "http://deployment-exec-broker:8912",
                "ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN": "broker-token",
            }
        )
        expect(executor.config.adapter_name == "local", str(executor.config))
        expect(executor.docker_runner.__class__.__name__ == "BrokeredDockerComposeRunner", str(executor.docker_runner))
        expect(executor.docker_runner.broker_url == "http://deployment-exec-broker:8912", str(executor.docker_runner))
        expect(executor.docker_runner.token == "broker-token", str(executor.docker_runner))
    print("PASS test_action_worker_local_docker_mode_requires_deployment_exec_broker")


def test_action_worker_main_reuses_single_db_connection_for_once_batch() -> None:
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_db_reuse")
    calls: list[str] = []
    gc_calls: list[str] = []

    class ConnContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    original_db_connect = worker._db_connect
    original_executor_from_env = worker._executor_from_env
    original_recover = worker.recover_stale_actions
    original_process = worker.process_arclink_action_batch
    original_gc = worker.run_pod_migration_gc
    old_env = os.environ.copy()
    try:
        os.environ["ARCLINK_EXECUTOR_ADAPTER"] = "fake"
        worker._db_connect = lambda path: calls.append(path) or ConnContext()
        worker._executor_from_env = lambda env: object()
        worker.recover_stale_actions = lambda conn: []
        worker.process_arclink_action_batch = lambda conn, **kwargs: []
        worker.run_pod_migration_gc = lambda conn: gc_calls.append("gc") or []
        rc = worker.main(["--once", "--json", "--db", "/tmp/arclink-test.sqlite3"])
        expect(rc == 0, f"expected clean once run, got {rc}")
        expect(calls == ["/tmp/arclink-test.sqlite3"], str(calls))
        expect(gc_calls == ["gc"], str(gc_calls))
    finally:
        worker._db_connect = original_db_connect
        worker._executor_from_env = original_executor_from_env
        worker.recover_stale_actions = original_recover
        worker.process_arclink_action_batch = original_process
        worker.run_pod_migration_gc = original_gc
        os.environ.clear()
        os.environ.update(old_env)
    print("PASS test_action_worker_main_reuses_single_db_connection_for_once_batch")


def test_agent_skill_enablement_registry_records_and_transitions() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_skill_registry")
    conn = memory_db(control)
    table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'arclink_agent_skill_enablement'"
    ).fetchone()
    expect(table is not None, "ensure_schema must create arclink_agent_skill_enablement")
    recorded = control.record_agent_skill_enablement_intent(
        conn,
        deployment_id="dep_skill_reg",
        skill_id="retrieval-and-cite",
        source="academy:systems-practice-engineer",
        status="approved",
        provenance_hash="abc123",
        requested_by="test:registry",
        metadata={"review_status": "approved"},
    )
    expect(recorded["status"] == "approved", str(recorded))
    # Idempotent upsert: same (deployment, skill, source) does not duplicate.
    control.record_agent_skill_enablement_intent(
        conn,
        deployment_id="dep_skill_reg",
        skill_id="retrieval-and-cite",
        source="academy:systems-practice-engineer",
        status="approved",
        provenance_hash="abc456",
        requested_by="test:registry",
    )
    rows = control.list_agent_skill_enablement(conn, deployment_id="dep_skill_reg")
    expect(len(rows) == 1, str(rows))
    expect(rows[0]["provenance_hash"] == "abc456", str(rows))
    expect(rows[0]["applied_at"] == "", str(rows))
    expect(rows[0]["metadata"] == {}, str(rows))
    changed = control.mark_agent_skill_enablement_applied(
        conn, enablement_id=rows[0]["enablement_id"], status="enabled"
    )
    expect(changed is True, "mark applied must update the row")
    enabled_rows = control.list_agent_skill_enablement(
        conn, deployment_id="dep_skill_reg", statuses=["enabled"]
    )
    expect(len(enabled_rows) == 1 and bool(enabled_rows[0]["applied_at"]), str(enabled_rows))
    # Fail closed on bad input.
    for kwargs in (
        {"deployment_id": "", "skill_id": "x"},
        {"deployment_id": "dep_skill_reg", "skill_id": ""},
        {"deployment_id": "dep_skill_reg", "skill_id": "x", "status": "bogus"},
    ):
        try:
            control.record_agent_skill_enablement_intent(conn, **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {kwargs}")
    print("PASS test_agent_skill_enablement_registry_records_and_transitions")


def test_academy_skill_enablement_runner_records_verified_and_missing() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_skill_runner")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_skill_runner")
    conn = memory_db(control)
    intents = [
        {
            "kind": "approved_skill_intent",
            "source_id": "src-skill-1",
            "skill_id": "retrieval-and-cite",
            "review_status": "approved",
            "tool_recipes": ["knowledge.search-and-fetch"],
        },
        # No skill_id AND no source_id fallback (the trainer derives skill_id
        # from source_id when metadata omits it): recorded as missing.
        {"kind": "approved_skill_intent", "source_id": "", "skill_id": "", "review_status": "approved"},
    ]
    runner = worker._academy_skill_enablement_runner(conn, approved_skill_intents=intents)
    result = runner(
        {
            "deployment_id": "dep_skill_runner",
            "program_id": "systems_practice_engineer",
            "trainee_id": "trainee-1",
            "request_id": "req-runner-1",
            "kind": "skill_activation",
        }
    )
    expect(result["status"] == "recorded", str(result))
    expect(result["verified_skills"] == ["retrieval-and-cite"], str(result))
    expect(result["missing_skills"] == ["unknown"], str(result))
    expect(result["proof"] == "arclink_agent_skill_enablement", str(result))
    rows = control.list_agent_skill_enablement(conn, deployment_id="dep_skill_runner")
    expect(len(rows) == 1, str(rows))
    expect(rows[0]["skill_id"] == "retrieval-and-cite", str(rows))
    expect(rows[0]["source"].startswith("academy:"), str(rows))
    expect(rows[0]["metadata"].get("effective_at") == "next_session", str(rows))
    # Missing deployment id fails closed without raising.
    blocked = runner({"deployment_id": "", "kind": "skill_activation"})
    expect(blocked["status"] == "blocked", str(blocked))
    print("PASS test_academy_skill_enablement_runner_records_verified_and_missing")


def test_consume_academy_refresh_queue_markers_transitions_on_lane_evidence() -> None:
    control = load_module("arclink_control.py", "arclink_control_aw_marker_consumer")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_marker_consumer")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir) / "dep-markers"
        roots = {
            "root": str(root),
            "config": str(root / "config"),
            "state": str(root / "state"),
            "vault": str(root / "vault"),
            "hermes_home": str(root / "state" / "hermes-home"),
        }
        state_dir = Path(roots["hermes_home"]) / "state"
        state_dir.mkdir(parents=True)
        control.upsert_arclink_user(conn, user_id="user_markers", email="markers@example.test", entitlement_state="paid")
        control.reserve_arclink_deployment_prefix(
            conn,
            deployment_id="dep_markers",
            user_id="user_markers",
            prefix="markers-one",
            base_domain="example.test",
            status="active",
            metadata={"state_roots": roots},
        )
        for kind in ("qmd_index", "memory_synthesis"):
            queued = worker._academy_durable_refresh_queue_runner(
                {
                    "kind": kind,
                    "state": str(state_dir),
                    "deployment_id": "dep_markers",
                    "request_id": "req-markers-1",
                }
            )
            expect(queued["status"] == "queued", str(queued))
        # Without lane evidence both markers stay queued (qmd_index has no
        # default evidence; memory-synth has no refresh_jobs record yet).
        untouched = worker.consume_academy_refresh_queue_markers(
            conn, deployment_id="dep_markers", consumed_by="test:no-evidence"
        )
        expect(untouched["consumed"] == 0, str(untouched))
        expect({item["status"] for item in untouched["markers"]} == {"queued"}, str(untouched))
        # A completed memory-synth lane is the default consumption evidence.
        control.note_refresh_job(
            conn,
            job_name="memory-synth",
            job_kind="memory-synth",
            target_id="global",
            schedule="timer",
            status="ok",
            note="test lane completion",
        )
        consumed = worker.consume_academy_refresh_queue_markers(
            conn, deployment_id="dep_markers", consumed_by="test:memory-synth"
        )
        expect(consumed["consumed"] == 1, str(consumed))
        statuses = {item["kind"]: item["status"] for item in consumed["markers"]}
        expect(statuses["memory_synthesis"] == "consumed", str(consumed))
        expect(statuses["qmd_index"] == "queued", str(consumed))
        memory_marker = json.loads(
            (state_dir / "arclink-academy-memory-synthesis-request.json").read_text(encoding="utf-8")
        )
        expect(memory_marker["status"] == "consumed" and memory_marker["consumed_by"] == "test:memory-synth", str(memory_marker))
        expect(bool(memory_marker["consumed_at"]) and bool(memory_marker["lane_completed_at"]), str(memory_marker))
        # qmd_index consumes only with explicit lane evidence (runner-gated).
        with_evidence = worker.consume_academy_refresh_queue_markers(
            conn,
            deployment_id="dep_markers",
            lane_evidence={"qmd_index": control.utc_now_iso()},
            consumed_by="test:qmd-lane",
        )
        expect(with_evidence["consumed"] == 1, str(with_evidence))
        qmd_marker = json.loads(
            (state_dir / "arclink-academy-qmd-refresh-request.json").read_text(encoding="utf-8")
        )
        expect(qmd_marker["status"] == "consumed", str(qmd_marker))
        # The all-deployments wrapper used by memory-synth run_once: re-queue a
        # memory marker and consume across deployments with explicit evidence.
        worker._academy_durable_refresh_queue_runner(
            {
                "kind": "memory_synthesis",
                "state": str(state_dir),
                "deployment_id": "dep_markers",
                "request_id": "req-markers-2",
            }
        )
        swept = worker.consume_academy_refresh_queue_markers_for_all(
            conn,
            kind="memory_synthesis",
            lane_completed_at=control.utc_now_iso(),
            consumed_by="memory-synth:run_once",
        )
        expect(swept["ok"] is True and swept["consumed"] == 1, str(swept))
        expect(swept["deployments"] == ["dep_markers"], str(swept))
    print("PASS test_consume_academy_refresh_queue_markers_transitions_on_lane_evidence")


def test_slow_but_alive_action_lease_renewal_blocks_reclaim() -> None:
    # conc-H1: a claimed action whose lease heartbeat (claimed_at) is fresh must
    # NOT be reclaimed by stale recovery, even if it has been 'running' a while.
    control = load_module("arclink_control.py", "arclink_control_aw_lease")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_lease")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_lease")
    conn = memory_db(control)
    intent = _queue_action(dashboard, conn, action_type="restart")
    action_id = intent["action_id"]
    claim = worker._claim_next_queued_action(conn, worker_id="worker_alive")
    expect(claim["action_id"] == action_id, str(claim))
    expect(claim["status"] == "running", str(claim))

    # Simulate a long-running action: push updated_at far into the past but keep
    # the lease heartbeat (claimed_at) fresh via the renewal helper.
    conn.execute(
        "UPDATE arclink_action_intents SET updated_at = '2020-01-01T00:00:00+00:00' WHERE action_id = ?",
        (action_id,),
    )
    conn.commit()
    new_claimed, still_owned = worker._renew_action_lease(
        conn, action_id=action_id, worker_id="worker_alive", claimed_at=str(claim["claimed_at"]),
    )
    expect(still_owned is True, "owning worker keeps its lease")
    expect(bool(new_claimed) and new_claimed != "2020-01-01T00:00:00+00:00", str(new_claimed))

    # Recovery with a tiny threshold must STILL skip it because the fresh lease
    # heartbeat is younger than the threshold.
    recovered = worker.recover_stale_actions(conn, stale_threshold_seconds=60)
    expect(recovered == [], f"fresh-lease action must not be reclaimed: {recovered}")
    row = conn.execute("SELECT status, worker_id FROM arclink_action_intents WHERE action_id = ?", (action_id,)).fetchone()
    expect(row["status"] == "running" and row["worker_id"] == "worker_alive", str(dict(row)))

    # A renewal attempt from a stale claimed_at value (i.e. the worker lost the
    # lease) reports still_owned False without mutating the row.
    _, lost = worker._renew_action_lease(
        conn, action_id=action_id, worker_id="worker_alive", claimed_at="1999-01-01T00:00:00+00:00",
    )
    expect(lost is False, "stale-identity renewal must report lost ownership")

    # Now age the lease itself; recovery reclaims it back to queued.
    conn.execute(
        "UPDATE arclink_action_intents SET claimed_at = '2020-01-01T00:00:00+00:00', updated_at = '2020-01-01T00:00:00+00:00' WHERE action_id = ?",
        (action_id,),
    )
    conn.commit()
    recovered = worker.recover_stale_actions(conn, stale_threshold_seconds=60)
    expect(len(recovered) == 1 and recovered[0]["new_status"] == "queued", str(recovered))
    row = conn.execute("SELECT status FROM arclink_action_intents WHERE action_id = ?", (action_id,)).fetchone()
    expect(row["status"] == "queued", str(dict(row)))
    print("PASS test_slow_but_alive_action_lease_renewal_blocks_reclaim")


def test_two_recoveries_cannot_both_reclaim() -> None:
    # conc-H1: two concurrent stale recoveries racing the same stale running row
    # must net exactly one reclaim (CAS on the exact identity read).
    control = load_module("arclink_control.py", "arclink_control_aw_double_recover")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_double_recover")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_double_recover")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "actions.sqlite3"
        setup = sqlite3.connect(db_path, timeout=15.0)
        setup.row_factory = sqlite3.Row
        control.ensure_schema(setup)
        intent = _queue_action(dashboard, setup, action_type="restart", key="double_recover")
        action_id = intent["action_id"]
        setup.execute(
            "UPDATE arclink_action_intents SET status = 'running', worker_id = 'dead_worker', "
            "claimed_at = '2020-01-01T00:00:00+00:00', updated_at = '2020-01-01T00:00:00+00:00' WHERE action_id = ?",
            (action_id,),
        )
        setup.commit()
        setup.close()

        barrier = threading.Barrier(2)
        results: list[list] = []
        errors: list[BaseException] = []
        lock = threading.Lock()

        def run_recovery() -> None:
            conn = sqlite3.connect(db_path, timeout=15.0)
            conn.row_factory = sqlite3.Row
            try:
                barrier.wait()
                recovered = worker.recover_stale_actions(conn, stale_threshold_seconds=60)
                with lock:
                    results.append(recovered)
            except BaseException as exc:
                with lock:
                    errors.append(exc)
            finally:
                conn.close()

        threads = [threading.Thread(target=run_recovery) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        expect(not errors, f"recovery errors: {errors}")
        total_reclaimed = sum(len(r) for r in results)
        expect(total_reclaimed == 1, f"exactly one recovery should reclaim, got {results}")

        verify = sqlite3.connect(db_path, timeout=15.0)
        verify.row_factory = sqlite3.Row
        row = verify.execute("SELECT status FROM arclink_action_intents WHERE action_id = ?", (action_id,)).fetchone()
        events = verify.execute(
            "SELECT COUNT(*) AS c FROM arclink_events WHERE event_type = 'action_stale_recovered'"
        ).fetchone()
        verify.close()
        expect(row["status"] == "queued", str(dict(row)))
        expect(int(events["c"]) == 1, f"exactly one recovery event, got {dict(events)}")
    print("PASS test_two_recoveries_cannot_both_reclaim")


def test_poison_row_does_not_crash_batch_loop() -> None:
    # conc-H8: a poison row whose PRE-DISPATCH ledger write blows up (runs outside
    # the dispatch except) must not kill the batch; the next action still runs.
    control = load_module("arclink_control.py", "arclink_control_aw_poison")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_poison")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_poison")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_poison")
    conn = memory_db(control)
    poison = _queue_action(dashboard, conn, action_type="restart", target_id="dep_poison", key="poison_1")
    healthy = _queue_action(dashboard, conn, action_type="restart", target_id="dep_ok", key="poison_2")

    original_audit = worker.append_arclink_audit

    def poison_audit(conn_arg, *args, **kwargs):
        action_meta = kwargs.get("metadata") or {}
        if str(action_meta.get("action_id") or "") == poison["action_id"] and str(kwargs.get("action", "")).startswith("action_worker_attempt_started"):
            raise sqlite3.IntegrityError("simulated poison ledger write")
        return original_audit(conn_arg, *args, **kwargs)

    try:
        worker.append_arclink_audit = poison_audit
        results = worker.process_arclink_action_batch(
            conn, executor=_fake_executor(executor_mod), batch_size=5, worker_id="worker_poison",
        )
    finally:
        worker.append_arclink_audit = original_audit

    statuses = {r["action_id"]: r["status"] for r in results}
    expect(statuses.get(poison["action_id"]) == "failed", f"poison row should be dead-lettered: {results}")
    expect(statuses.get(healthy["action_id"]) == "succeeded", f"healthy row should still process: {results}")

    poison_row = conn.execute("SELECT status FROM arclink_action_intents WHERE action_id = ?", (poison["action_id"],)).fetchone()
    healthy_row = conn.execute("SELECT status FROM arclink_action_intents WHERE action_id = ?", (healthy["action_id"],)).fetchone()
    expect(poison_row["status"] == "failed", str(dict(poison_row)))
    expect(healthy_row["status"] == "succeeded", str(dict(healthy_row)))
    dead_letter = conn.execute(
        "SELECT COUNT(*) AS c FROM arclink_events WHERE event_type = 'action_poison_dead_lettered'"
    ).fetchone()
    expect(int(dead_letter["c"]) == 1, f"poison row should emit a dead-letter event: {dict(dead_letter)}")
    print("PASS test_poison_row_does_not_crash_batch_loop")


def test_refund_downgrades_entitlement() -> None:
    # billing-H4: a successful refund must close the entitlement gates locally
    # (a refund emits no subscription.deleted webhook), moving the user off paid --
    # BUT only when the refund EXPLICITLY maps to one of the user's active-paid
    # subscriptions. This exercises the explicit-subscription-target downgrade.
    control = load_module("arclink_control.py", "arclink_control_aw_refund_downgrade")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_refund_downgrade")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_refund_downgrade")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_refund_downgrade")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_refund_dg", stripe_customer_id="cus_refund_dg", entitlement_state="paid")
    # The user's active-paid subscription that the refund explicitly targets.
    control.upsert_arclink_subscription_mirror(
        conn,
        subscription_id="sub_refund_dg",
        user_id="user_refund_dg",
        status="active",
        stripe_customer_id="cus_refund_dg",
        stripe_subscription_id="stripe_sub_refund_dg",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_refund_dg",
        user_id="user_refund_dg",
        prefix="refund-dg",
        base_domain="example.test",
        status="provisioning_ready",
    )
    before = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = ?", ("user_refund_dg",)).fetchone()
    expect(before["entitlement_state"] == "paid", str(dict(before)))

    _queue_action(
        dashboard,
        conn,
        action_type="refund",
        target_kind="subscription",
        target_id="sub_refund_dg",
    )
    result = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod))
    expect(result["status"] == "succeeded", str(result))
    expect(result["result"].get("entitlement_downgraded") is True, str(result))
    expect(result["result"].get("entitlement_state") == "cancelled", str(result))

    after = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = ?", ("user_refund_dg",)).fetchone()
    expect(after["entitlement_state"] == "cancelled", f"refund must downgrade entitlement: {dict(after)}")
    can_provision = control.arclink_deployment_can_provision(conn, deployment_id="dep_refund_dg")
    expect(can_provision is False, "refunded customer must lose the provisioning gate")
    event = conn.execute(
        "SELECT COUNT(*) AS c FROM arclink_events WHERE event_type = 'entitlement_downgraded_on_refund'"
    ).fetchone()
    expect(int(event["c"]) == 1, str(dict(event)))
    print("PASS test_refund_downgrades_entitlement")


def test_refund_with_no_subscription_link_downgrades_nothing() -> None:
    # billing-H4 (tightened): a refund of a user/deployment with NO explicit
    # subscription link must NOT auto-attach the user's latest active subscription
    # and must cancel NOTHING. A non-subscription refund (a one-off charge) cannot be
    # allowed to silently cancel an unrelated, still-active subscription.
    control = load_module("arclink_control.py", "arclink_control_aw_no_sublink")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_no_sublink")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_no_sublink")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_no_sublink")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_nolink", stripe_customer_id="cus_nolink", entitlement_state="paid")
    # The user HAS a latest active subscription -- the OLD auto-attach would have grabbed
    # this and wrongly cancelled it for a plain deployment refund.
    control.upsert_arclink_subscription_mirror(
        conn,
        subscription_id="sub_nolink_active",
        user_id="user_nolink",
        status="active",
        stripe_customer_id="cus_nolink",
        stripe_subscription_id="stripe_sub_nolink_active",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_nolink",
        user_id="user_nolink",
        prefix="nolink",
        base_domain="example.test",
        status="provisioning_ready",
    )

    # A plain deployment refund -- names no subscription, no invoice, not a subscription
    # target.
    _queue_action(dashboard, conn, action_type="refund", target_id="dep_nolink")
    result = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod))
    expect(result["status"] == "succeeded", str(result))
    expect(
        result["result"].get("entitlement_downgraded") is False,
        f"a refund with no subscription link must downgrade nothing: {result}",
    )
    expect(
        result["result"].get("entitlement_downgrade_reason") == "no_explicit_subscription_link",
        str(result),
    )

    after = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = ?", ("user_nolink",)).fetchone()
    expect(after["entitlement_state"] == "paid", f"entitlement must stay paid for a non-subscription refund: {dict(after)}")
    active = conn.execute("SELECT status FROM arclink_subscriptions WHERE subscription_id = 'sub_nolink_active'").fetchone()
    expect(active["status"] == "active", f"the unrelated active subscription must survive: {dict(active)}")
    events = conn.execute(
        "SELECT COUNT(*) AS c FROM arclink_events WHERE event_type = 'entitlement_downgraded_on_refund'"
    ).fetchone()
    expect(int(events["c"]) == 0, f"no downgrade event for a no-subscription-link refund: {dict(events)}")
    print("PASS test_refund_with_no_subscription_link_downgrades_nothing")


def test_old_owner_cannot_overwrite_reclaimed_intent() -> None:
    # conc-M5: a worker whose lease was lost (stale recovery re-queued the intent /
    # a NEW owner re-claimed it) during a long dispatch must NOT stamp the intent
    # terminal afterwards. The post-dispatch _update_intent_status CAS is guarded on
    # (status='running' AND worker_id=<original>), so the late write is a no-op and
    # the recovery/new owner's state survives.
    control = load_module("arclink_control.py", "arclink_control_aw_m5")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_m5")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_m5")
    conn = memory_db(control)
    intent = _queue_action(dashboard, conn, action_type="restart")
    action_id = intent["action_id"]
    claim = worker._claim_next_queued_action(conn, worker_id="old_owner")
    expect(claim["status"] == "running" and claim["worker_id"] == "old_owner", str(claim))

    # Simulate stale recovery re-queuing + a NEW owner re-claiming the row while the
    # old owner's dispatch was still in flight.
    requeued = worker._update_intent_status(conn, action_id=action_id, status="queued")
    expect(requeued is True, "recovery should re-queue the stale running intent")
    conn.commit()
    reclaim = worker._claim_next_queued_action(conn, worker_id="new_owner")
    expect(reclaim is not None and reclaim["worker_id"] == "new_owner" and reclaim["status"] == "running", str(reclaim))
    conn.commit()

    # The OLD owner now tries to stamp the intent terminal. Guarded on its own
    # worker_id, the write must be refused (rowcount 0) and NOT clobber new_owner.
    wrote = worker._update_intent_status(conn, action_id=action_id, status="succeeded", worker_id="old_owner")
    expect(wrote is False, "old owner must not overwrite a re-claimed intent")
    row = conn.execute("SELECT status, worker_id FROM arclink_action_intents WHERE action_id = ?", (action_id,)).fetchone()
    expect(row["status"] == "running" and row["worker_id"] == "new_owner", f"new owner must still govern the intent: {dict(row)}")

    # The legitimate still-owning worker (new_owner) CAN complete it.
    wrote2 = worker._update_intent_status(conn, action_id=action_id, status="succeeded", worker_id="new_owner")
    expect(wrote2 is True, "still-owning worker must be able to complete the intent")
    row2 = conn.execute("SELECT status FROM arclink_action_intents WHERE action_id = ?", (action_id,)).fetchone()
    expect(row2["status"] == "succeeded", str(dict(row2)))
    print("PASS test_old_owner_cannot_overwrite_reclaimed_intent")


def test_exception_path_reports_lease_lost_when_unowned() -> None:
    # conc-M5: when the dispatch RAISES *and* the worker's lease was lost mid-dispatch
    # (stale recovery re-queued / a new owner re-claimed the intent), the exception
    # handler's guarded _update_intent_status returns False. The worker MUST report
    # lease_lost (the new owner governs) instead of overwriting the re-claimed intent
    # with 'failed'. This mirrors the success path's lease_lost handling.
    control = load_module("arclink_control.py", "arclink_control_aw_exc_lease")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_exc_lease")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_exc_lease")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_exc_lease")
    conn = memory_db(control)
    intent = _queue_action(dashboard, conn, action_type="restart")
    action_id = intent["action_id"]

    original_dispatch = worker._dispatch_action

    def stealing_then_raising_dispatch(**kwargs):
        # Simulate stale recovery taking the row from under the running worker mid-
        # dispatch: re-queue (clears worker_id/claimed_at) then re-claim under a NEW
        # owner -- THEN raise so the worker hits the exception path no longer owning it.
        worker._update_intent_status(conn, action_id=action_id, status="queued")
        conn.commit()
        reclaim = worker._claim_next_queued_action(conn, worker_id="exc_new_owner")
        expect(reclaim is not None and reclaim["worker_id"] == "exc_new_owner", str(reclaim))
        conn.commit()
        raise RuntimeError("dispatch blew up after the lease was stolen")

    try:
        worker._dispatch_action = stealing_then_raising_dispatch
        result = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod), worker_id="exc_old_owner")
    finally:
        worker._dispatch_action = original_dispatch

    expect(result is not None, "worker must return a result, not crash")
    expect(
        result["status"] == "lease_lost",
        f"exception path must report lease_lost when the row was re-claimed: {result}",
    )
    expect(result.get("error_code") == "action_lease_lost", str(result))

    # The new owner's re-claimed intent must survive -- NOT be clobbered to 'failed'.
    row = conn.execute("SELECT status, worker_id FROM arclink_action_intents WHERE action_id = ?", (action_id,)).fetchone()
    expect(
        row["status"] == "running" and row["worker_id"] == "exc_new_owner",
        f"the re-claimed intent must still be owned/running by the new owner: {dict(row)}",
    )
    lease_lost_events = conn.execute(
        "SELECT COUNT(*) AS c FROM arclink_events WHERE event_type LIKE 'action_lease_lost_post_dispatch:%'"
    ).fetchone()
    expect(int(lease_lost_events["c"]) == 1, f"a post-dispatch lease_lost event must be emitted: {dict(lease_lost_events)}")
    failed_events = conn.execute(
        "SELECT COUNT(*) AS c FROM arclink_events WHERE event_type LIKE 'action_failed:%'"
    ).fetchone()
    expect(int(failed_events["c"]) == 0, f"no action_failed event when the lease was lost: {dict(failed_events)}")
    print("PASS test_exception_path_reports_lease_lost_when_unowned")


def test_reused_worker_id_cannot_stamp_reclaimed_intent() -> None:
    # conc-M5b: the intent-status CAS pins the EXACT lease (worker_id AND claimed_at).
    # A recycled/reused worker_id alone is NOT a unique lease -- without the claimed_at
    # in the CAS, an OLD attempt (same worker_id, but holding the stale claimed_at)
    # could stamp a row a FRESH re-claim (same worker_id, new claimed_at) already owns.
    # The claimed_at guard must reject the old lease and admit only the current one.
    control = load_module("arclink_control.py", "arclink_control_aw_m5b")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_m5b")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_m5b")
    conn = memory_db(control)
    intent = _queue_action(dashboard, conn, action_type="restart")
    action_id = intent["action_id"]

    # The worker claims the row; capture the EXACT lease it now holds.
    claim = worker._claim_next_queued_action(conn, worker_id="recycled_worker")
    expect(claim["worker_id"] == "recycled_worker" and claim["status"] == "running", str(claim))
    stale_claimed_at = str(claim["claimed_at"])
    conn.commit()

    # Recovery re-queues, then the SAME worker_id is recycled and re-claims the row,
    # producing a DISTINCT current lease (new claimed_at). Force a distinct timestamp
    # so the test is deterministic regardless of second-resolution clocks.
    worker._update_intent_status(conn, action_id=action_id, status="queued")
    conn.commit()
    reclaim = worker._claim_next_queued_action(conn, worker_id="recycled_worker")
    expect(reclaim is not None and reclaim["worker_id"] == "recycled_worker", str(reclaim))
    fresh_claimed_at = "2099-01-01T00:00:00+00:00"
    conn.execute(
        "UPDATE arclink_action_intents SET claimed_at = ? WHERE action_id = ?",
        (fresh_claimed_at, action_id),
    )
    conn.commit()
    expect(fresh_claimed_at != stale_claimed_at, "the fresh lease must differ from the stale one")

    # The OLD attempt -- same worker_id but holding the STALE claimed_at -- must be
    # refused by the CAS (claimed_at mismatch), so it cannot stamp the re-claimed row.
    wrote_stale = worker._update_intent_status(
        conn, action_id=action_id, status="succeeded",
        worker_id="recycled_worker", claimed_at=stale_claimed_at,
    )
    expect(wrote_stale is False, "an old lease (stale claimed_at) must NOT stamp a re-claimed row")
    row = conn.execute("SELECT status, worker_id, claimed_at FROM arclink_action_intents WHERE action_id = ?", (action_id,)).fetchone()
    expect(
        row["status"] == "running" and str(row["claimed_at"]) == fresh_claimed_at,
        f"the current lease's row must be untouched by the stale-lease write: {dict(row)}",
    )

    # The worker holding the CURRENT lease (same worker_id, fresh claimed_at) CAN write.
    wrote_fresh = worker._update_intent_status(
        conn, action_id=action_id, status="succeeded",
        worker_id="recycled_worker", claimed_at=fresh_claimed_at,
    )
    expect(wrote_fresh is True, "the worker holding the exact current lease must be able to write")
    row2 = conn.execute("SELECT status FROM arclink_action_intents WHERE action_id = ?", (action_id,)).fetchone()
    expect(row2["status"] == "succeeded", str(dict(row2)))
    print("PASS test_reused_worker_id_cannot_stamp_reclaimed_intent")


def test_refund_of_non_subscription_does_not_cancel_active_subscription() -> None:
    # billing-H4: refunding an unrelated / one-off charge (a non-active subscription
    # the action explicitly targets) must NOT cancel the user's still-ACTIVE
    # subscription or downgrade their paid entitlement.
    control = load_module("arclink_control.py", "arclink_control_aw_h4")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_h4")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_h4")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_h4")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_h4", stripe_customer_id="cus_h4", entitlement_state="paid")
    # The user's CURRENT, still-active subscription -- must survive the refund.
    control.upsert_arclink_subscription_mirror(
        conn,
        subscription_id="sub_active_h4",
        user_id="user_h4",
        status="active",
        stripe_customer_id="cus_h4",
        stripe_subscription_id="stripe_sub_active_h4",
    )
    # A separate, already-canceled subscription standing in for the one-off / unrelated
    # charge that is being refunded.
    control.upsert_arclink_subscription_mirror(
        conn,
        subscription_id="sub_oneoff_h4",
        user_id="user_h4",
        status="cancelled",
        stripe_customer_id="cus_h4",
        stripe_subscription_id="stripe_sub_oneoff_h4",
    )

    _queue_action(
        dashboard,
        conn,
        action_type="refund",
        target_kind="subscription",
        target_id="sub_oneoff_h4",
        key="refund_oneoff_h4",
    )
    result = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod))
    expect(result["status"] == "succeeded", str(result))
    expect(result["result"].get("entitlement_downgraded") is False, f"unrelated refund must not downgrade: {result}")
    # The refund explicitly TARGETS sub_oneoff_h4, which resolved to a non-active-paid
    # (cancelled) row -> nothing live to cancel; the user's separate active sub survives.
    expect(result["result"].get("entitlement_downgrade_reason") == "subscription_target_not_active", str(result))

    after = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = ?", ("user_h4",)).fetchone()
    expect(after["entitlement_state"] == "paid", f"active subscriber must keep paid entitlement: {dict(after)}")
    active = conn.execute("SELECT status FROM arclink_subscriptions WHERE subscription_id = 'sub_active_h4'").fetchone()
    expect(active["status"] == "active", f"active subscription must survive an unrelated refund: {dict(active)}")
    events = conn.execute(
        "SELECT COUNT(*) AS c FROM arclink_events WHERE event_type = 'entitlement_downgraded_on_refund'"
    ).fetchone()
    expect(int(events["c"]) == 0, f"no downgrade event for an unrelated refund: {dict(events)}")

    # Sanity: refunding the user's ACTUAL active subscription DOES downgrade, and a
    # replay of that same refund is idempotent (no second event).
    _queue_action(
        dashboard,
        conn,
        action_type="refund",
        target_kind="subscription",
        target_id="sub_active_h4",
        key="refund_active_h4_a",
    )
    res_active = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod))
    expect(res_active["status"] == "succeeded", str(res_active))
    expect(res_active["result"].get("entitlement_downgraded") is True, str(res_active))
    state_after = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = ?", ("user_h4",)).fetchone()
    expect(state_after["entitlement_state"] == "cancelled", f"refunding the active sub must downgrade: {dict(state_after)}")

    _queue_action(
        dashboard,
        conn,
        action_type="refund",
        target_kind="subscription",
        target_id="sub_active_h4",
        key="refund_active_h4_b",
    )
    res_replay = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod))
    expect(res_replay["status"] == "succeeded", str(res_replay))
    expect(res_replay["result"].get("entitlement_downgraded") is True, str(res_replay))
    downgrade_events = conn.execute(
        "SELECT COUNT(*) AS c FROM arclink_events WHERE event_type = 'entitlement_downgraded_on_refund'"
    ).fetchone()
    expect(int(downgrade_events["c"]) == 1, f"downgrade event must be emitted exactly once (idempotent): {dict(downgrade_events)}")
    print("PASS test_refund_of_non_subscription_does_not_cancel_active_subscription")


def test_refund_metadata_no_sublink_does_not_cancel_latest_active_subscription() -> None:
    # billing-H4 (round-2, Codex bypass): a user/deployment refund whose metadata names
    # NO subscription -- but the user HAS a latest active subscription -- must NOT
    # auto-attach that active sub via the cancel/customer_ref inference and then cancel it.
    # The latest-active auto-attach populates the working subscription id (for cancel)
    # but must NEVER drive a refund downgrade. The active sub must SURVIVE, no event.
    control = load_module("arclink_control.py", "arclink_control_aw_r2_nolink")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_r2_nolink")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_r2_nolink")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_r2_nolink")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_r2nl", stripe_customer_id="cus_r2nl", entitlement_state="paid")
    # The latest active subscription the OLD auto-attach would have wrongly cancelled.
    control.upsert_arclink_subscription_mirror(
        conn,
        subscription_id="sub_r2nl_active",
        user_id="user_r2nl",
        status="active",
        stripe_customer_id="cus_r2nl",
        stripe_subscription_id="stripe_sub_r2nl_active",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_r2nl",
        user_id="user_r2nl",
        prefix="r2nl-dep",
        base_domain="example.test",
        status="provisioning_ready",
    )

    # A plain deployment refund with NO subscription metadata at all.
    _queue_action(dashboard, conn, action_type="refund", target_id="dep_r2nl")
    result = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod))
    expect(result["status"] == "succeeded", str(result))
    expect(result["result"].get("entitlement_downgraded") is False, f"no-link refund must downgrade nothing: {result}")
    expect(result["result"].get("entitlement_downgrade_reason") == "no_explicit_subscription_link", str(result))

    after = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = ?", ("user_r2nl",)).fetchone()
    expect(after["entitlement_state"] == "paid", f"entitlement must stay paid: {dict(after)}")
    active = conn.execute("SELECT status FROM arclink_subscriptions WHERE subscription_id = 'sub_r2nl_active'").fetchone()
    expect(active["status"] == "active", f"the latest active sub must survive: {dict(active)}")
    events = conn.execute(
        "SELECT COUNT(*) AS c FROM arclink_events WHERE event_type = 'entitlement_downgraded_on_refund'"
    ).fetchone()
    expect(int(events["c"]) == 0, f"no downgrade event for a no-link refund: {dict(events)}")
    print("PASS test_refund_metadata_no_sublink_does_not_cancel_latest_active_subscription")


def test_refund_metadata_names_nonactive_sub_does_not_cancel_active_subscription() -> None:
    # billing-H4 (round-2, Codex bypass): a refund whose metadata NAMES a sub that is
    # NOT active (here a non-existent / unknown id) must NOT cause the latest-active sub
    # to be auto-attached and cancelled. The metadata name marks intent, but the
    # downgrade decision keys off the EXPLICIT-link identifiers ONLY -- which stay empty
    # when the named sub does not resolve to a real active row -- so nothing is cancelled.
    control = load_module("arclink_control.py", "arclink_control_aw_r2_nonactive")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_r2_nonactive")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_r2_nonactive")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_r2_nonactive")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_r2na", stripe_customer_id="cus_r2na", entitlement_state="paid")
    # An unrelated, still-active subscription (the auto-attach would grab the latest).
    control.upsert_arclink_subscription_mirror(
        conn,
        subscription_id="sub_r2na_active",
        user_id="user_r2na",
        status="active",
        stripe_customer_id="cus_r2na",
        stripe_subscription_id="stripe_sub_r2na_active",
    )
    # A separate, already-cancelled sub standing in for the refunded one-off charge.
    control.upsert_arclink_subscription_mirror(
        conn,
        subscription_id="sub_r2na_cancelled",
        user_id="user_r2na",
        status="cancelled",
        stripe_customer_id="cus_r2na",
        stripe_subscription_id="stripe_sub_r2na_cancelled",
    )

    # The refund NAMES the cancelled (non-active) subscription in metadata, on a user
    # target -- the round-1 bypass would still cancel the latest-active sub here.
    _queue_action(
        dashboard,
        conn,
        action_type="refund",
        target_kind="user",
        target_id="user_r2na",
        metadata={"subscription_id": "sub_r2na_cancelled"},
    )
    result = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod))
    expect(result["status"] == "succeeded", str(result))
    expect(result["result"].get("entitlement_downgraded") is False, f"non-active-named refund must downgrade nothing: {result}")
    expect(result["result"].get("entitlement_downgrade_reason") == "named_subscription_not_active", str(result))

    after = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = ?", ("user_r2na",)).fetchone()
    expect(after["entitlement_state"] == "paid", f"entitlement must stay paid: {dict(after)}")
    active = conn.execute("SELECT status FROM arclink_subscriptions WHERE subscription_id = 'sub_r2na_active'").fetchone()
    expect(active["status"] == "active", f"the unrelated active sub must survive: {dict(active)}")
    events = conn.execute(
        "SELECT COUNT(*) AS c FROM arclink_events WHERE event_type = 'entitlement_downgraded_on_refund'"
    ).fetchone()
    expect(int(events["c"]) == 0, f"no downgrade event for a non-active-named refund: {dict(events)}")
    print("PASS test_refund_metadata_names_nonactive_sub_does_not_cancel_active_subscription")


def test_refund_metadata_names_active_sub_downgrades_once_idempotent() -> None:
    # billing-H4 (round-2): a refund whose metadata names a stripe_subscription_id that
    # resolves to one of the user's ACTIVE-paid subs is an explicit link -> downgrade
    # EXACTLY once, and a replay of the same refund must be idempotent (no second event).
    control = load_module("arclink_control.py", "arclink_control_aw_r2_active")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_r2_active")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_r2_active")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_r2_active")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_r2a", stripe_customer_id="cus_r2a", entitlement_state="paid")
    control.upsert_arclink_subscription_mirror(
        conn,
        subscription_id="sub_r2a_active",
        user_id="user_r2a",
        status="active",
        stripe_customer_id="cus_r2a",
        stripe_subscription_id="stripe_sub_r2a_active",
    )

    _queue_action(
        dashboard,
        conn,
        action_type="refund",
        target_kind="user",
        target_id="user_r2a",
        metadata={"stripe_subscription_id": "stripe_sub_r2a_active"},
        key="refund_r2a_a",
    )
    result = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod))
    expect(result["status"] == "succeeded", str(result))
    expect(result["result"].get("entitlement_downgraded") is True, f"explicit active-named refund must downgrade: {result}")
    expect(result["result"].get("entitlement_downgrade_reason") == "metadata_matches_active_subscription", str(result))
    after = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = ?", ("user_r2a",)).fetchone()
    expect(after["entitlement_state"] == "cancelled", f"explicit active refund must downgrade: {dict(after)}")

    # Replay the same refund -> idempotent: succeeds, reports already-downgraded, no 2nd event.
    _queue_action(
        dashboard,
        conn,
        action_type="refund",
        target_kind="user",
        target_id="user_r2a",
        metadata={"stripe_subscription_id": "stripe_sub_r2a_active"},
        key="refund_r2a_b",
    )
    replay = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod))
    expect(replay["status"] == "succeeded", str(replay))
    events = conn.execute(
        "SELECT COUNT(*) AS c FROM arclink_events WHERE event_type = 'entitlement_downgraded_on_refund'"
    ).fetchone()
    expect(int(events["c"]) == 1, f"downgrade event must be emitted exactly once (idempotent): {dict(events)}")
    print("PASS test_refund_metadata_names_active_sub_downgrades_once_idempotent")


def test_refund_metadata_invoice_resolves_to_active_sub_downgrades() -> None:
    # billing-H4 (round-2): a refund whose metadata `invoice` resolves (via the
    # subscription mirror raw_json) to one of the user's ACTIVE subs is an explicit link
    # -> downgrade that subscription's entitlement.
    control = load_module("arclink_control.py", "arclink_control_aw_r2_invoice")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_r2_invoice")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_r2_invoice")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_r2_invoice")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_r2i", stripe_customer_id="cus_r2i", entitlement_state="paid")
    # The active sub the invoice maps to (raw_json carries the invoice id).
    control.upsert_arclink_subscription_mirror(
        conn,
        subscription_id="sub_r2i_active",
        user_id="user_r2i",
        status="active",
        stripe_customer_id="cus_r2i",
        stripe_subscription_id="stripe_sub_r2i_active",
        raw={"invoice": "in_r2i_123"},
    )

    _queue_action(
        dashboard,
        conn,
        action_type="refund",
        target_kind="user",
        target_id="user_r2i",
        metadata={"invoice": "in_r2i_123"},
    )
    result = worker.process_next_arclink_action(conn, executor=_fake_executor(executor_mod))
    expect(result["status"] == "succeeded", str(result))
    expect(result["result"].get("entitlement_downgraded") is True, f"invoice-resolved refund must downgrade: {result}")
    expect(result["result"].get("entitlement_downgrade_reason") == "metadata_matches_active_subscription", str(result))
    after = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = ?", ("user_r2i",)).fetchone()
    expect(after["entitlement_state"] == "cancelled", f"invoice-resolved refund must downgrade: {dict(after)}")
    events = conn.execute(
        "SELECT COUNT(*) AS c FROM arclink_events WHERE event_type = 'entitlement_downgraded_on_refund'"
    ).fetchone()
    expect(int(events["c"]) == 1, f"exactly one downgrade event for the invoice-resolved refund: {dict(events)}")
    print("PASS test_refund_metadata_invoice_resolves_to_active_sub_downgrades")


def test_long_reprovision_not_reclaimed_while_migration_heartbeats() -> None:
    # conc-H1: a `reprovision` action's dispatch IS a long migration that heartbeats
    # its own arclink_pod_migrations.updated_at. Even if the action-level lease looks
    # stale, recovery must NOT reclaim/double-dispatch the action while the migration
    # row is still 'running' and beating.
    control = load_module("arclink_control.py", "arclink_control_aw_h1_mig")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_h1_mig")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_h1_mig")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_h1_mig", entitlement_state="paid")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_h1_mig",
        user_id="user_h1_mig",
        prefix="h1-mig",
        base_domain="example.test",
        status="active",
    )
    intent = _queue_action(
        dashboard,
        conn,
        action_type="reprovision",
        target_id="dep_h1_mig",
        target_kind="deployment",
        key="reprovision_h1_mig",
        metadata={"target_machine_id": "current"},
    )
    action_id = intent["action_id"]
    claim = worker._claim_next_queued_action(conn, worker_id="worker_h1_mig")
    expect(claim["status"] == "running", str(claim))

    now = control.utc_now_iso()
    # The action's own lease (claimed_at) is ancient -> looks stale at the action level.
    conn.execute(
        "UPDATE arclink_action_intents SET claimed_at = '2020-01-01T00:00:00+00:00', updated_at = '2020-01-01T00:00:00+00:00' WHERE action_id = ?",
        (action_id,),
    )
    # ...but a 'running' migration for this deployment heartbeat just NOW.
    conn.execute(
        """
        INSERT INTO arclink_pod_migrations (migration_id, deployment_id, status, created_at, updated_at)
        VALUES ('mig_h1_live', 'dep_h1_mig', 'running', ?, ?)
        """,
        (now, now),
    )
    conn.commit()

    recovered = worker.recover_stale_actions(conn, stale_threshold_seconds=60)
    expect(recovered == [], f"live long reprovision must not be reclaimed: {recovered}")
    row = conn.execute("SELECT status, worker_id FROM arclink_action_intents WHERE action_id = ?", (action_id,)).fetchone()
    expect(row["status"] == "running" and row["worker_id"] == "worker_h1_mig", str(dict(row)))

    # Once the migration's heartbeat goes stale (e.g. the worker truly died), the
    # action is reclaimable again.
    conn.execute(
        "UPDATE arclink_pod_migrations SET updated_at = '2020-01-01T00:00:00+00:00' WHERE migration_id = 'mig_h1_live'",
    )
    conn.commit()
    recovered2 = worker.recover_stale_actions(conn, stale_threshold_seconds=60)
    expect(len(recovered2) == 1 and recovered2[0]["new_status"] == "queued", str(recovered2))
    row2 = conn.execute("SELECT status FROM arclink_action_intents WHERE action_id = ?", (action_id,)).fetchone()
    expect(row2["status"] == "queued", str(dict(row2)))
    print("PASS test_long_reprovision_not_reclaimed_while_migration_heartbeats")


def test_process_next_survives_poison_row() -> None:
    # conc-H8: the direct process_next_arclink_action entrypoint must be poison-safe,
    # not just the batch loop. A pre-dispatch ledger write that blows up must be
    # rolled back + dead-lettered, returning a failure result instead of crashing.
    control = load_module("arclink_control.py", "arclink_control_aw_pn_poison")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_aw_pn_poison")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_aw_pn_poison")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_pn_poison")
    conn = memory_db(control)
    poison = _queue_action(dashboard, conn, action_type="restart", target_id="dep_pn_poison", key="pn_poison_1")

    original_audit = worker.append_arclink_audit

    def poison_audit(conn_arg, *args, **kwargs):
        meta = kwargs.get("metadata") or {}
        if str(meta.get("action_id") or "") == poison["action_id"] and str(kwargs.get("action", "")).startswith("action_worker_attempt_started"):
            raise sqlite3.IntegrityError("simulated poison ledger write")
        return original_audit(conn_arg, *args, **kwargs)

    try:
        worker.append_arclink_audit = poison_audit
        # Must NOT raise -- the entrypoint catches + dead-letters.
        result = worker.process_next_arclink_action(
            conn, executor=_fake_executor(executor_mod), worker_id="worker_pn_poison",
        )
    finally:
        worker.append_arclink_audit = original_audit

    expect(result is not None and result["status"] == "failed", f"poison row must be dead-lettered, not raised: {result}")
    expect(result["action_id"] == poison["action_id"], str(result))
    row = conn.execute("SELECT status FROM arclink_action_intents WHERE action_id = ?", (poison["action_id"],)).fetchone()
    expect(row["status"] == "failed", str(dict(row)))
    dead_letter = conn.execute(
        "SELECT COUNT(*) AS c FROM arclink_events WHERE event_type = 'action_poison_dead_lettered'"
    ).fetchone()
    expect(int(dead_letter["c"]) == 1, f"direct entrypoint poison row should emit a dead-letter event: {dict(dead_letter)}")
    print("PASS test_process_next_survives_poison_row")


if __name__ == "__main__":
    test_restart_action_through_fake_executor()
    test_dns_repair_through_fake_executor()
    test_dns_repair_backfills_provider_record_ids_after_apply()
    test_action_worker_links_admin_action_to_executor_operation()
    test_restart_action_rejects_lifecycle_path_overrides_by_default()
    test_restart_action_lifecycle_path_overrides_require_explicit_operator_flag()
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
    test_stripe_entitlement_recovery_action_dry_run_and_apply()
    test_backup_write_check_fails_closed_without_authorized_runner()
    test_academy_apply_preview_action_records_no_write_result_without_executor()
    test_academy_apply_preview_action_fails_closed_on_workspace_write_request()
    test_academy_apply_action_stages_fail_closed_without_authorization()
    test_academy_apply_action_materializes_local_hermes_home_when_authorized()
    test_academy_apply_ssh_materialization_uses_remote_files_not_control_mirror()
    test_agent_skill_enablement_registry_records_and_transitions()
    test_academy_skill_enablement_runner_records_verified_and_missing()
    test_consume_academy_refresh_queue_markers_transitions_on_lane_evidence()
    test_reprovision_dispatches_pod_migration()
    test_reprovision_non_dry_run_requires_root_capture_opt_in()
    test_reprovision_non_dry_run_requires_migration_capture_helper_in_docker_mode()
    test_reprovision_dry_run_does_not_require_migration_success()
    test_batch_processing()
    test_empty_queue_returns_none()
    test_action_attempt_recorded()
    test_concurrent_workers_claim_action_once()
    test_attempt_audit_is_persisted_before_side_effect()
    test_executor_selection_failure_records_failed_attempt()
    test_stale_action_recovery()
    test_stale_action_recovery_fails_after_attempt_cap()
    test_idempotent_retry()
    test_executor_error_secret_material_is_redacted()
    test_action_worker_returns_safe_error_code_for_executor_errors()
    test_rollout_action_materializes_ready_three_pod_plan_without_executor_side_effects()
    test_rollout_action_executes_one_local_batch_when_explicitly_requested()
    test_rollout_action_refuses_blocked_preflight_without_rollout_rows()
    test_rollout_action_idempotent_replay_does_not_duplicate_rollout_rows()
    test_legacy_unwired_action_rows_fail_safely()
    test_fake_executor_live_flag_is_false()
    test_deployment_action_routes_to_active_placement_host()
    test_disabled_action_worker_cli_exits_cleanly()
    test_action_worker_ssh_executor_requires_machine_mode_and_allowlist()
    test_action_worker_local_docker_mode_requires_deployment_exec_broker()
    test_action_worker_main_reuses_single_db_connection_for_once_batch()
    test_slow_but_alive_action_lease_renewal_blocks_reclaim()
    test_two_recoveries_cannot_both_reclaim()
    test_poison_row_does_not_crash_batch_loop()
    test_refund_downgrades_entitlement()
    test_refund_with_no_subscription_link_downgrades_nothing()
    test_old_owner_cannot_overwrite_reclaimed_intent()
    test_exception_path_reports_lease_lost_when_unowned()
    test_reused_worker_id_cannot_stamp_reclaimed_intent()
    test_refund_of_non_subscription_does_not_cancel_active_subscription()
    test_refund_metadata_no_sublink_does_not_cancel_latest_active_subscription()
    test_refund_metadata_names_nonactive_sub_does_not_cancel_active_subscription()
    test_refund_metadata_names_active_sub_downgrades_once_idempotent()
    test_refund_metadata_invoice_resolves_to_active_sub_downgrades()
    test_long_reprovision_not_reclaimed_while_migration_heartbeats()
    test_process_next_survives_poison_row()
    print(f"\nAll 64 action worker tests passed.")
