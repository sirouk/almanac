#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
import sys
import tempfile
import json
import hashlib
import stat
from pathlib import Path

from arclink_test_helpers import expect, load_module


def memory_db(control):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    return conn


def seed_ready_deployment(control, conn):
    control.upsert_arclink_user(
        conn,
        user_id="user_1",
        email="user@example.test",
        display_name="User One",
        entitlement_state="paid",
    )
    deployment = control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_1",
        user_id="user_1",
        prefix="amber-vault-1234",
        base_domain="example.test",
        status="provisioning_ready",
    )
    now = control.utc_now_iso()
    conn.execute(
        """
        INSERT INTO arclink_onboarding_sessions (
          session_id, channel, channel_identity, status, current_step,
          email_hint, display_name_hint, selected_plan_id, selected_model_id,
          user_id, deployment_id, checkout_state, metadata_json, created_at, updated_at
        ) VALUES (
          'onb_worker_1', 'telegram', 'tg:100', 'provisioning_ready', 'provisioning_requested',
          'user@example.test', 'User One', 'starter', 'moonshotai/Kimi-K2.6-TEE',
          'user_1', 'dep_1', 'paid', '{}', ?, ?
        )
        """,
        (now, now),
    )
    conn.commit()
    return deployment


def worker_config(worker_mod, tmpdir, *, enabled=True, register_local=True):
    return worker_mod.SovereignWorkerConfig(
        enabled=enabled,
        ingress_mode="domain",
        base_domain="example.test",
        edge_target="edge.example.test",
        tailscale_dns_name="",
        tailscale_host_strategy="path",
        tailscale_https_port="443",
        tailscale_notion_path="/notion/webhook",
        state_root_base=f"{tmpdir}/deployments",
        cloudflare_zone_id="zone_fake",
        executor_adapter="fake",
        batch_size=5,
        max_attempts=3,
        running_stale_seconds=60,
        register_local_host=register_local,
        local_hostname="worker-1.example.test",
        local_ssh_host="",
        local_ssh_user="root",
        local_region="us-east",
        local_capacity_slots=2,
        secret_store_dir=Path(tmpdir) / "secrets",
        env={
            "ARCLINK_BASE_DOMAIN": "example.test",
            "ARCLINK_PRIMARY_PROVIDER": "chutes",
            "ARCLINK_CHUTES_BASE_URL": "https://llm.chutes.ai/v1",
            "ARCLINK_CHUTES_DEFAULT_MODEL": "moonshotai/Kimi-K2.6-TEE",
        },
    )


def test_fake_sovereign_worker_applies_ready_deployment() -> None:
    control = load_module("arclink_control.py", "arclink_control_sovereign_apply")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_sovereign_apply")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_apply")
    conn = memory_db(control)
    seed_ready_deployment(control, conn)
    opened = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:100",
        text="/link-channel",
    )
    code_row = conn.execute(
        """
        SELECT code, status
        FROM arclink_channel_pairing_codes
        WHERE source_session_id = 'onb_worker_1'
        """
    ).fetchone()
    expect(opened.action == "pair_channel_code", str(opened))
    expect(code_row is not None and code_row["status"] == "open", str(dict(code_row or {})))
    claimed = bots.handle_arclink_public_bot_turn(
        conn,
        channel="discord",
        channel_identity="discord:200",
        text=f"/link-channel {code_row['code']}",
    )
    expect(claimed.action == "pair_channel_claimed", str(claimed))
    expect(claimed.deployment_id == "dep_1", str(claimed))
    with tempfile.TemporaryDirectory() as tmpdir:
        results = worker_mod.process_sovereign_batch(conn, worker=worker_config(worker_mod, tmpdir))

    expect(len(results) == 1, str(results))
    result = results[0]
    expect(result["status"] == "applied", str(result))
    expect(result["placement"]["hostname"] == "worker-1.example.test", str(result))
    expect("dashboard" in result["services"], str(result))
    dep = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()
    expect(dep["status"] == "active", str(dict(dep)))
    job = conn.execute("SELECT job_kind, status, attempt_count FROM arclink_provisioning_jobs").fetchone()
    expect(job["job_kind"] == "sovereign_pod_apply" and job["status"] == "succeeded", str(dict(job)))
    expect(int(job["attempt_count"]) == 1, str(dict(job)))
    dns_statuses = {row["status"] for row in conn.execute("SELECT status FROM arclink_dns_records").fetchall()}
    expect(dns_statuses == {"provisioned"}, str(dns_statuses))
    health_statuses = {row["status"] for row in conn.execute("SELECT status FROM arclink_service_health").fetchall()}
    expect(health_statuses == {"healthy"}, str(health_statuses))
    event_types = {row["event_type"] for row in conn.execute("SELECT event_type FROM arclink_events").fetchall()}
    expect({"sovereign_provisioning_started", "sovereign_pod_applied", "user_handoff_ready", "public_bot:vessel_online_ping_queued"} <= event_types, str(event_types))
    notifications = [
        dict(row)
        for row in conn.execute(
            """
            SELECT target_kind, target_id, channel_kind, message, extra_json
            FROM notification_outbox
            WHERE target_kind = 'public-bot-user'
            ORDER BY channel_kind, target_id
            """
        ).fetchall()
    ]
    targets = {(item["channel_kind"], item["target_id"]) for item in notifications}
    expect(targets == {("discord", "200"), ("telegram", "100")}, str(notifications))
    notification = next(item for item in notifications if item["channel_kind"] == "telegram")
    expect("Agent online" in notification["message"], str(notification["message"]))
    expect("Stage 4 complete: your ArcLink agent is ready" in notification["message"], str(notification["message"]))
    expect("Dashboard: https://u-amber-vault-1234.example.test" in notification["message"], str(notification["message"]))
    expect("Hermes:" in notification["message"], str(notification["message"]))
    expect("Use /credentials or tap Credentials" in notification["message"], str(notification["message"]))
    extra = json.loads(notification["extra_json"])
    expect("telegram_reply_markup" in extra and "discord_components" in extra, str(extra))
    telegram_buttons = [
        button
        for row in extra["telegram_reply_markup"]["inline_keyboard"]
        for button in row
    ]
    expect(any(button.get("text") == "Open Helm" and button.get("url") for button in telegram_buttons), str(extra))
    expect(any(button.get("text") == "Credentials" and button.get("callback_data") == "arclink:/raven credentials dep_1" for button in telegram_buttons), str(extra))
    expect(any(button.get("text") == "Show My Crew" and button.get("callback_data") == "arclink:/raven agents" for button in telegram_buttons), str(extra))
    expect(any(button.get("text") == "Link Channel" and button.get("callback_data") == "arclink:/raven link-channel" for button in telegram_buttons), str(extra))
    session = conn.execute("SELECT status, current_step, metadata_json FROM arclink_onboarding_sessions WHERE session_id = 'onb_worker_1'").fetchone()
    expect(session["status"] == "first_contacted" and session["current_step"] == "first_agent_contact", str(dict(session)))
    session_meta = json.loads(session["metadata_json"])
    expect(session_meta.get("active_deployment_id") == "dep_1", str(session_meta))
    paired = conn.execute(
        """
        SELECT status, current_step, metadata_json
        FROM arclink_onboarding_sessions
        WHERE channel = 'discord'
          AND channel_identity = 'discord:200'
        """
    ).fetchone()
    expect(paired["status"] == "first_contacted" and paired["current_step"] == "first_agent_contact", str(dict(paired)))
    paired_meta = json.loads(paired["metadata_json"])
    expect(paired_meta.get("active_deployment_id") == "dep_1", str(paired_meta))
    queued_event = conn.execute(
        """
        SELECT metadata_json
        FROM arclink_events
        WHERE subject_kind = 'deployment'
          AND subject_id = 'dep_1'
          AND event_type = 'public_bot:vessel_online_ping_queued'
        """
    ).fetchone()
    queued_meta = json.loads(queued_event["metadata_json"])
    expect(queued_meta["notification_count"] == 2, str(queued_meta))
    expect(queued_meta["channels"] == ["discord", "telegram"], str(queued_meta))
    print("PASS test_fake_sovereign_worker_applies_ready_deployment")


class AnySecretResolver:
    def __init__(self, executor_mod):
        self.executor_mod = executor_mod

    def materialize(self, secret_ref: str, target_path: str):
        return self.executor_mod.ResolvedSecretFile(secret_ref=secret_ref, target_path=target_path)


def test_live_sovereign_worker_reconciles_compose_ps_health() -> None:
    control = load_module("arclink_control.py", "arclink_control_sovereign_compose_ps")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_compose_ps")
    import arclink_executor as executor_mod

    class ComposePsRunner(executor_mod.FakeDockerRunner):
        def __init__(self, stdout: str):
            super().__init__()
            self.stdout = stdout

        def run(self, args, *, project_name: str, env_file: str, compose_file: str):
            self.runs.append(
                {
                    "args": args,
                    "project_name": project_name,
                    "env_file": env_file,
                    "compose_file": compose_file,
                }
            )
            if tuple(args) == ("ps", "--all", "--format", "json"):
                return {"status": "ok", "stdout": self.stdout}
            return {"status": "ok", "stdout": ""}

    conn = memory_db(control)
    seed_ready_deployment(control, conn)
    rows = [
        {"Service": service, "State": "running", "Health": "", "Status": "Up 1 second", "Name": f"{service}-1", "Project": "arclink-dep_1"}
        for service in worker_mod.ARCLINK_PROVISIONING_SERVICE_NAMES
    ]
    for row in rows:
        if row["Service"] == "nextcloud":
            row["Health"] = "healthy"
            row["Status"] = "Up 1 second (healthy)"
        if row["Service"] == "managed-context-install":
            row["State"] = "exited"
            row["ExitCode"] = 0
            row["Status"] = "Exited (0)"
    runner = ComposePsRunner("\n".join(json.dumps(row) for row in rows))
    executor = executor_mod.ArcLinkExecutor(
        config=executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="local"),
        secret_resolver=AnySecretResolver(executor_mod),
        docker_runner=runner,
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = worker_config(worker_mod, tmpdir)
        cfg = worker_mod.SovereignWorkerConfig(
            **{
                **cfg.__dict__,
                "ingress_mode": "tailscale",
                "base_domain": "worker.example.test",
                "edge_target": "worker.example.test",
                "tailscale_dns_name": "worker.example.test",
                "tailscale_host_strategy": "path",
                "env": {
                    **dict(cfg.env),
                    "ARCLINK_INGRESS_MODE": "tailscale",
                    "ARCLINK_TAILSCALE_DNS_NAME": "worker.example.test",
                    "ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY": "path",
                },
            }
        )
        results = worker_mod.process_sovereign_batch(conn, worker=cfg, executor=executor)

    expect(results[0]["status"] == "applied", str(results))
    statuses = {
        row["service_name"]: row["status"]
        for row in conn.execute("SELECT service_name, status FROM arclink_service_health").fetchall()
    }
    expect(statuses["dashboard"] == "healthy", str(statuses))
    expect(statuses["nextcloud"] == "healthy", str(statuses))
    expect(statuses["managed-context-install"] == "healthy", str(statuses))
    expect(statuses["notification-delivery"] == "healthy", str(statuses))
    expect(("ps", "--all", "--format", "json") in [tuple(run["args"]) for run in runner.runs], str(runner.runs))
    print("PASS test_live_sovereign_worker_reconciles_compose_ps_health")


def test_tailscale_sovereign_worker_skips_cloudflare_dns() -> None:
    control = load_module("arclink_control.py", "arclink_control_sovereign_tailscale")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_tailscale")
    conn = memory_db(control)
    seed_ready_deployment(control, conn)
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = worker_config(worker_mod, tmpdir)
        cfg = worker_mod.SovereignWorkerConfig(
            **{
                **cfg.__dict__,
                "ingress_mode": "tailscale",
                "base_domain": "worker.example.test",
                "edge_target": "worker.example.test",
                "tailscale_dns_name": "worker.example.test",
                "tailscale_host_strategy": "path",
                "env": {
                    **dict(cfg.env),
                    "ARCLINK_INGRESS_MODE": "tailscale",
                    "ARCLINK_TAILSCALE_DNS_NAME": "worker.example.test",
                    "ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY": "path",
                    "ARCLINK_TAILNET_SERVICE_PORT_BASE": "8443",
                },
            }
        )
        results = worker_mod.process_sovereign_batch(conn, worker=cfg)

    expect(results[0]["status"] == "applied", str(results))
    expect(results[0]["dns_records"] == [], str(results))
    expect(results[0]["urls"]["dashboard"] == "https://worker.example.test/u/amber-vault-1234", str(results))
    expect(results[0]["urls"]["hermes"] == "https://worker.example.test/u/amber-vault-1234/hermes", str(results))
    expect(results[0]["urls"]["files"] == "https://worker.example.test/u/amber-vault-1234/drive", str(results))
    expect(results[0]["urls"]["code"] == "https://worker.example.test/u/amber-vault-1234/code", str(results))
    metadata = json.loads(
        conn.execute("SELECT metadata_json FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()["metadata_json"]
    )
    expect(metadata["tailnet_service_ports"] == {"hermes": 8443}, str(metadata))
    expect(metadata["access_urls"]["hermes"] == "https://worker.example.test/u/amber-vault-1234/hermes", str(metadata))
    expect(metadata["access_urls"]["files"] == "https://worker.example.test/u/amber-vault-1234/drive", str(metadata))
    dns_count = conn.execute("SELECT COUNT(*) AS c FROM arclink_dns_records").fetchone()["c"]
    expect(dns_count == 0, str(dns_count))
    event = conn.execute("SELECT metadata_json FROM arclink_events WHERE event_type = 'sovereign_pod_applied'").fetchone()
    expect('"ingress_mode": "tailscale"' in event["metadata_json"], event["metadata_json"])
    print("PASS test_tailscale_sovereign_worker_skips_cloudflare_dns")


def test_sovereign_worker_tears_down_active_deployment_idempotently() -> None:
    control = load_module("arclink_control.py", "arclink_control_sovereign_teardown")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_teardown")
    import arclink_executor as executor_mod

    conn = memory_db(control)
    seed_ready_deployment(control, conn)
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = worker_config(worker_mod, tmpdir)
        executor = executor_mod.ArcLinkExecutor(
            config=executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
            secret_resolver=executor_mod.FakeSecretResolver({}),
        )
        executor.chutes_key_apply(executor_mod.ChutesKeyApplyRequest(
            deployment_id="dep_1",
            action="create",
            secret_ref="secret://arclink/chutes/dep_1",
            idempotency_key="seed-chutes-key-dep-1",
        ))
        applied = worker_mod.process_sovereign_batch(conn, worker=cfg)
        expect(applied[0]["status"] == "applied", str(applied))
        conn.execute("UPDATE arclink_deployments SET status = 'teardown_requested' WHERE deployment_id = 'dep_1'")
        conn.commit()
        torn_down = worker_mod.process_sovereign_batch(conn, worker=cfg, executor=executor)
        replay = worker_mod.process_sovereign_teardown(
            conn,
            deployment=dict(conn.execute("SELECT * FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()),
            worker=cfg,
            executor=executor,
        )

    expect(torn_down[0]["status"] == "torn_down", str(torn_down))
    expect(torn_down[0]["chutes_status"] == "applied", str(torn_down))
    expect(replay["status"] == "already_torn_down", str(replay))
    dep = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()
    expect(dep["status"] == "torn_down", str(dict(dep)))
    active_placements = conn.execute(
        "SELECT COUNT(*) AS c FROM arclink_deployment_placements WHERE deployment_id = 'dep_1' AND status = 'active'"
    ).fetchone()["c"]
    expect(int(active_placements) == 0, "expected active placement to be removed")
    host = conn.execute("SELECT observed_load FROM arclink_fleet_hosts WHERE hostname = 'worker-1.example.test'").fetchone()
    expect(int(host["observed_load"]) == 0, str(dict(host)))
    dns_statuses = {row["status"] for row in conn.execute("SELECT status FROM arclink_dns_records").fetchall()}
    expect(dns_statuses == {"torn_down"}, str(dns_statuses))
    health_statuses = {row["status"] for row in conn.execute("SELECT status FROM arclink_service_health").fetchall()}
    expect(health_statuses == {"torn_down"}, str(health_statuses))
    health_detail = json.loads(conn.execute("SELECT detail_json FROM arclink_service_health WHERE service_name = 'dashboard'").fetchone()["detail_json"])
    expect(health_detail["chutes_status"] == "applied", str(health_detail))
    event_types = {row["event_type"] for row in conn.execute("SELECT event_type FROM arclink_events").fetchall()}
    expect({"sovereign_teardown_started", "sovereign_teardown_completed", "dns_teardown"} <= event_types, str(event_types))
    print("PASS test_sovereign_worker_tears_down_active_deployment_idempotently")


def test_tailnet_port_allocation_ignores_released_deployments() -> None:
    control = load_module("arclink_control.py", "arclink_control_sovereign_tailnet_reuse")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_tailnet_reuse")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_1", email="user@example.test", entitlement_state="paid")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_old",
        user_id="user_1",
        prefix="old-agent",
        base_domain="worker.example.test",
        status="torn_down",
        metadata={"tailnet_service_ports": {"hermes": 8443}},
    )
    seed_ready_deployment(control, conn)
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = worker_config(worker_mod, tmpdir)
        cfg = worker_mod.SovereignWorkerConfig(
            **{
                **cfg.__dict__,
                "ingress_mode": "tailscale",
                "base_domain": "worker.example.test",
                "edge_target": "worker.example.test",
                "tailscale_dns_name": "worker.example.test",
                "tailscale_host_strategy": "path",
                "env": {
                    **dict(cfg.env),
                    "ARCLINK_INGRESS_MODE": "tailscale",
                    "ARCLINK_TAILSCALE_DNS_NAME": "worker.example.test",
                    "ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY": "path",
                    "ARCLINK_TAILNET_SERVICE_PORT_BASE": "8443",
                },
            }
        )
        results = worker_mod.process_sovereign_batch(conn, worker=cfg)
    expect(results[0]["status"] == "applied", str(results))
    metadata = json.loads(conn.execute("SELECT metadata_json FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()["metadata_json"])
    expect(metadata["tailnet_service_ports"] == {"hermes": 8443}, str(metadata))
    print("PASS test_tailnet_port_allocation_ignores_released_deployments")


def test_sovereign_worker_is_disabled_until_explicitly_enabled() -> None:
    control = load_module("arclink_control.py", "arclink_control_sovereign_disabled")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_disabled")
    conn = memory_db(control)
    seed_ready_deployment(control, conn)
    with tempfile.TemporaryDirectory() as tmpdir:
        results = worker_mod.process_sovereign_batch(conn, worker=worker_config(worker_mod, tmpdir, enabled=False))
    expect(results == [{"status": "disabled", "reason": "ARCLINK_CONTROL_PROVISIONER_ENABLED is not set"}], str(results))
    job_count = conn.execute("SELECT COUNT(*) AS c FROM arclink_provisioning_jobs").fetchone()["c"]
    expect(job_count == 0, str(job_count))
    print("PASS test_sovereign_worker_is_disabled_until_explicitly_enabled")


def test_sovereign_worker_fails_closed_without_fleet_capacity() -> None:
    control = load_module("arclink_control.py", "arclink_control_sovereign_nohost")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_nohost")
    conn = memory_db(control)
    seed_ready_deployment(control, conn)
    with tempfile.TemporaryDirectory() as tmpdir:
        results = worker_mod.process_sovereign_batch(
            conn,
            worker=worker_config(worker_mod, tmpdir, enabled=True, register_local=False),
        )
    expect(results[0]["status"] == "failed", str(results))
    expect("no eligible ArcLink fleet hosts" in results[0]["error"], str(results))
    dep = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()
    expect(dep["status"] == "provisioning_failed", str(dict(dep)))
    print("PASS test_sovereign_worker_fails_closed_without_fleet_capacity")


def test_sovereign_worker_rechecks_lost_entitlement_before_placement() -> None:
    control = load_module("arclink_control.py", "arclink_control_sovereign_lost_entitlement")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_lost_entitlement")
    conn = memory_db(control)
    seed_ready_deployment(control, conn)
    original_ports = worker_mod._ensure_tailnet_service_ports
    original_place = worker_mod.place_deployment
    placement_called = False

    def revoke_entitlement(conn_arg, *, deployment, worker):
        conn_arg.execute(
            "UPDATE arclink_users SET entitlement_state = 'none', entitlement_updated_at = ? WHERE user_id = 'user_1'",
            (control.utc_now_iso(),),
        )
        conn_arg.commit()
        return dict(deployment)

    def forbidden_place(*args, **kwargs):
        nonlocal placement_called
        placement_called = True
        return original_place(*args, **kwargs)

    worker_mod._ensure_tailnet_service_ports = revoke_entitlement
    worker_mod.place_deployment = forbidden_place
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            results = worker_mod.process_sovereign_batch(conn, worker=worker_config(worker_mod, tmpdir))
    finally:
        worker_mod._ensure_tailnet_service_ports = original_ports
        worker_mod.place_deployment = original_place

    expect(results[0]["status"] == "failed", str(results))
    expect("entitlement no longer permits" in results[0]["error"], str(results))
    expect(not placement_called, "placement must not run after entitlement is revoked")
    placements = conn.execute("SELECT COUNT(*) AS c FROM arclink_deployment_placements").fetchone()["c"]
    dns = conn.execute("SELECT COUNT(*) AS c FROM arclink_dns_records").fetchone()["c"]
    expect(int(placements) == 0 and int(dns) == 0, f"unexpected side effects: placements={placements}, dns={dns}")
    print("PASS test_sovereign_worker_rechecks_lost_entitlement_before_placement")


def test_sovereign_worker_rechecks_missing_user_before_placement() -> None:
    control = load_module("arclink_control.py", "arclink_control_sovereign_missing_user")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_missing_user")
    conn = memory_db(control)
    seed_ready_deployment(control, conn)
    original_ports = worker_mod._ensure_tailnet_service_ports
    original_place = worker_mod.place_deployment
    placement_called = False

    def delete_user(conn_arg, *, deployment, worker):
        conn_arg.execute("DELETE FROM arclink_users WHERE user_id = 'user_1'")
        conn_arg.commit()
        return dict(deployment)

    def forbidden_place(*args, **kwargs):
        nonlocal placement_called
        placement_called = True
        return original_place(*args, **kwargs)

    worker_mod._ensure_tailnet_service_ports = delete_user
    worker_mod.place_deployment = forbidden_place
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            results = worker_mod.process_sovereign_batch(conn, worker=worker_config(worker_mod, tmpdir))
    finally:
        worker_mod._ensure_tailnet_service_ports = original_ports
        worker_mod.place_deployment = original_place

    expect(results[0]["status"] == "failed", str(results))
    expect("deployment user missing" in results[0]["error"], str(results))
    expect(not placement_called, "placement must not run after deployment user disappears")
    placements = conn.execute("SELECT COUNT(*) AS c FROM arclink_deployment_placements").fetchone()["c"]
    expect(int(placements) == 0, f"unexpected placement side effect: {placements}")
    print("PASS test_sovereign_worker_rechecks_missing_user_before_placement")


def test_sovereign_worker_rechecks_changed_status_before_placement() -> None:
    control = load_module("arclink_control.py", "arclink_control_sovereign_changed_status")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_changed_status")
    conn = memory_db(control)
    seed_ready_deployment(control, conn)
    original_ports = worker_mod._ensure_tailnet_service_ports
    original_place = worker_mod.place_deployment
    placement_called = False

    def cancel_deployment(conn_arg, *, deployment, worker):
        conn_arg.execute(
            "UPDATE arclink_deployments SET status = 'cancelled', updated_at = ? WHERE deployment_id = 'dep_1'",
            (control.utc_now_iso(),),
        )
        conn_arg.commit()
        return dict(deployment)

    def forbidden_place(*args, **kwargs):
        nonlocal placement_called
        placement_called = True
        return original_place(*args, **kwargs)

    worker_mod._ensure_tailnet_service_ports = cancel_deployment
    worker_mod.place_deployment = forbidden_place
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            results = worker_mod.process_sovereign_batch(conn, worker=worker_config(worker_mod, tmpdir))
    finally:
        worker_mod._ensure_tailnet_service_ports = original_ports
        worker_mod.place_deployment = original_place

    expect(results[0]["status"] == "failed", str(results))
    expect("changed status before apply side effects" in results[0]["error"], str(results))
    expect(not placement_called, "placement must not run after deployment status changes")
    deployment = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()
    placements = conn.execute("SELECT COUNT(*) AS c FROM arclink_deployment_placements").fetchone()["c"]
    expect(deployment["status"] == "cancelled", str(dict(deployment)))
    expect(int(placements) == 0, f"unexpected placement side effect: {placements}")
    print("PASS test_sovereign_worker_rechecks_changed_status_before_placement")


def test_sovereign_worker_repairs_stale_local_host_load() -> None:
    control = load_module("arclink_control.py", "arclink_control_sovereign_stale_load")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_sovereign_stale_load")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_stale_load")
    conn = memory_db(control)
    seed_ready_deployment(control, conn)
    host = fleet.register_fleet_host(conn, hostname="worker-1.example.test", region="old", capacity_slots=2)
    fleet.update_fleet_host(conn, host_id=host["host_id"], observed_load=2)
    with tempfile.TemporaryDirectory() as tmpdir:
        results = worker_mod.process_sovereign_batch(conn, worker=worker_config(worker_mod, tmpdir))
    expect(results[0]["status"] == "applied", str(results))
    refreshed = conn.execute(
        "SELECT region, capacity_slots, observed_load FROM arclink_fleet_hosts WHERE host_id = ?",
        (host["host_id"],),
    ).fetchone()
    expect(refreshed["region"] == "us-east", str(dict(refreshed)))
    expect(int(refreshed["capacity_slots"]) == 2, str(dict(refreshed)))
    expect(int(refreshed["observed_load"]) == 1, str(dict(refreshed)))
    dep = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()
    expect(dep["status"] == "active", str(dict(dep)))
    print("PASS test_sovereign_worker_repairs_stale_local_host_load")


def test_sovereign_worker_recovers_stale_running_job() -> None:
    control = load_module("arclink_control.py", "arclink_control_sovereign_stale_running")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_stale_running")
    conn = memory_db(control)
    seed_ready_deployment(control, conn)
    job = worker_mod._ensure_apply_job(conn, deployment_id="dep_1")
    control.transition_arclink_provisioning_job(conn, job_id=job["job_id"], status="running")
    conn.execute(
        "UPDATE arclink_provisioning_jobs SET started_at = '2000-01-01T00:00:00+00:00' WHERE job_id = ?",
        (job["job_id"],),
    )
    conn.execute("UPDATE arclink_deployments SET status = 'provisioning' WHERE deployment_id = 'dep_1'")
    conn.commit()
    with tempfile.TemporaryDirectory() as tmpdir:
        results = worker_mod.process_sovereign_batch(conn, worker=worker_config(worker_mod, tmpdir))
    expect(results[0]["status"] == "applied", str(results))
    refreshed = conn.execute("SELECT status, attempt_count, error FROM arclink_provisioning_jobs WHERE job_id = ?", (job["job_id"],)).fetchone()
    expect(refreshed["status"] == "succeeded", str(dict(refreshed)))
    expect(int(refreshed["attempt_count"]) == 2, str(dict(refreshed)))
    event_types = {row["event_type"] for row in conn.execute("SELECT event_type FROM arclink_events").fetchall()}
    expect("sovereign_provisioning_recovered_stale_running_job" in event_types, str(event_types))
    print("PASS test_sovereign_worker_recovers_stale_running_job")


def test_sovereign_worker_recovers_succeeded_job_without_handoff() -> None:
    control = load_module("arclink_control.py", "arclink_control_sovereign_succeeded_handoff")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_sovereign_succeeded_handoff")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_succeeded_handoff")
    conn = memory_db(control)
    seed_ready_deployment(control, conn)
    host = fleet.register_fleet_host(
        conn,
        hostname="worker-1.example.test",
        region="us-east",
        capacity_slots=2,
        metadata={"edge_target": "edge.example.test"},
    )
    fleet.place_deployment(conn, deployment_id="dep_1")
    job = worker_mod._ensure_apply_job(conn, deployment_id="dep_1")
    control.transition_arclink_provisioning_job(conn, job_id=job["job_id"], status="running")
    control.transition_arclink_provisioning_job(conn, job_id=job["job_id"], status="succeeded")
    cached_urls = {
        "dashboard": "https://cached.example.test",
        "hermes": "https://cached.example.test/hermes",
        "files": "https://cached.example.test/drive",
        "code": "https://cached.example.test/code",
    }
    conn.execute(
        "UPDATE arclink_deployments SET status = 'provisioning', metadata_json = ? WHERE deployment_id = 'dep_1'",
        (json.dumps({"access_urls": cached_urls}, sort_keys=True),),
    )
    conn.commit()
    with tempfile.TemporaryDirectory() as tmpdir:
        results = worker_mod.process_sovereign_batch(conn, worker=worker_config(worker_mod, tmpdir))
    expect(results == [], str(results))
    dep = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()
    expect(dep["status"] == "active", str(dict(dep)))
    event_types = {row["event_type"] for row in conn.execute("SELECT event_type FROM arclink_events").fetchall()}
    expect("user_handoff_ready" in event_types, str(event_types))
    expect("public_bot:vessel_online_ping_queued" in event_types, str(event_types))
    event = conn.execute("SELECT metadata_json FROM arclink_events WHERE event_type = 'user_handoff_ready'").fetchone()
    expect(json.loads(event["metadata_json"])["urls"]["dashboard"] == "https://cached.example.test", event["metadata_json"])
    queued = conn.execute("SELECT COUNT(*) AS c FROM notification_outbox WHERE target_kind = 'public-bot-user'").fetchone()["c"]
    expect(int(queued) == 1, f"expected recovered handoff notification, got {queued}")
    note = conn.execute("SELECT message FROM notification_outbox WHERE target_kind = 'public-bot-user'").fetchone()
    expect("Dashboard: https://cached.example.test" in note["message"], note["message"])
    refreshed = fleet.get_fleet_host(conn, host_id=host["host_id"])
    expect(int(refreshed["observed_load"]) == 1, str(refreshed))
    print("PASS test_sovereign_worker_recovers_succeeded_job_without_handoff")


def test_compose_ps_transport_failure_records_failed_health() -> None:
    control = load_module("arclink_control.py", "arclink_control_sovereign_ps_failure")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_ps_failure")
    import arclink_executor as executor_mod

    class FailingPsRunner(executor_mod.FakeDockerRunner):
        def run(self, args, *, project_name: str, env_file: str, compose_file: str):
            self.runs.append({"args": args, "project_name": project_name, "env_file": env_file, "compose_file": compose_file})
            if tuple(args) == ("ps", "--all", "--format", "json"):
                raise executor_mod.ArcLinkExecutorError("transport unavailable")
            return {"status": "ok", "stdout": ""}

    conn = memory_db(control)
    seed_ready_deployment(control, conn)
    runner = FailingPsRunner()
    executor = executor_mod.ArcLinkExecutor(
        config=executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="local"),
        secret_resolver=AnySecretResolver(executor_mod),
        docker_runner=runner,
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = worker_config(worker_mod, tmpdir)
        cfg = worker_mod.SovereignWorkerConfig(**{**cfg.__dict__, "ingress_mode": "tailscale"})
        results = worker_mod.process_sovereign_batch(conn, worker=cfg, executor=executor)
    expect(results[0]["status"] == "failed", str(results))
    statuses = {row["status"] for row in conn.execute("SELECT status FROM arclink_service_health").fetchall()}
    expect(statuses == {"failed"}, str(statuses))
    print("PASS test_compose_ps_transport_failure_records_failed_health")


def test_notion_webhook_secret_is_generated_without_notion_token() -> None:
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_notion_secret")
    with tempfile.TemporaryDirectory() as tmpdir:
        resolver = worker_mod.SovereignSecretResolver(
            env={},
            secret_store_dir=Path(tmpdir) / "store",
            materialization_root=Path(tmpdir) / "materialized",
        )
        resolved = resolver.materialize(
            "secret://arclink/notion/dep_1/webhook-secret",
            "/run/secrets/notion_webhook_secret",
        )
        secret_file = Path(resolved.source_path)
        expect(secret_file.exists(), "expected generated Notion webhook secret file")
        expect(secret_file.read_text(encoding="utf-8").strip().startswith("arc_"), "expected generated ArcLink secret")
    print("PASS test_notion_webhook_secret_is_generated_without_notion_token")


def test_dashboard_password_secret_is_generated_for_canonical_handoff_store() -> None:
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_dashboard_secret")
    with tempfile.TemporaryDirectory() as tmpdir:
        secret_store = Path(tmpdir) / "store" / "dep_1"
        resolver = worker_mod.SovereignSecretResolver(
            env={},
            secret_store_dir=secret_store,
            materialization_root=Path(tmpdir) / "materialized",
        )
        secret_ref = "secret://arclink/dashboard/dep_1/password"
        resolved = resolver.materialize(
            secret_ref,
            "/run/secrets/dashboard_password",
        )
        central_secret = secret_store / f"{hashlib.sha256(secret_ref.encode('utf-8')).hexdigest()}.secret"
        materialized_secret = Path(resolved.source_path)
        expect(central_secret.exists(), f"expected canonical dashboard password secret file: {central_secret}")
        expect(materialized_secret.exists(), f"expected materialized compose secret file: {materialized_secret}")
        central_value = central_secret.read_text(encoding="utf-8").strip()
        materialized_value = materialized_secret.read_text(encoding="utf-8").strip()
        expect(central_value == materialized_value, "compose secret must mirror canonical store material")
        expect(central_value.startswith("arc_"), "expected generated ArcLink dashboard password")
        resolver_2 = worker_mod.SovereignSecretResolver(
            env={},
            secret_store_dir=Path(tmpdir) / "store" / "dep_2",
            materialization_root=Path(tmpdir) / "materialized-2",
        )
        user_ref = "secret://arclink/dashboard/users/user_1/password"
        user_first = resolver.materialize(user_ref, "/run/secrets/dashboard_password")
        user_second = resolver_2.materialize(user_ref, "/run/secrets/dashboard_password")
        user_secret = Path(tmpdir) / "store" / "users" / f"{hashlib.sha256(user_ref.encode('utf-8')).hexdigest()}.secret"
        expect(user_secret.exists(), f"expected user-scoped dashboard password secret file: {user_secret}")
        expect(Path(user_first.source_path).read_text(encoding="utf-8") == Path(user_second.source_path).read_text(encoding="utf-8"), "same user ref must materialize the same dashboard password across deployments")
        expect(user_secret.read_text(encoding="utf-8").strip() == Path(user_first.source_path).read_text(encoding="utf-8").strip(), "materialized user secret must mirror canonical user store")
        expect(stat.S_IMODE(user_secret.parent.stat().st_mode) == 0o700, oct(stat.S_IMODE(user_secret.parent.stat().st_mode)))
        expect(stat.S_IMODE(user_secret.stat().st_mode) == 0o600, oct(stat.S_IMODE(user_secret.stat().st_mode)))
        expect(stat.S_IMODE(materialized_secret.parent.stat().st_mode) == 0o700, oct(stat.S_IMODE(materialized_secret.parent.stat().st_mode)))
        expect(stat.S_IMODE(materialized_secret.stat().st_mode) == 0o600, oct(stat.S_IMODE(materialized_secret.stat().st_mode)))
    print("PASS test_dashboard_password_secret_is_generated_for_canonical_handoff_store")


def test_dashboard_password_hash_sync_only_when_secret_is_new() -> None:
    control = load_module("arclink_control.py", "arclink_control_sovereign_password_sync")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_sovereign_password_sync")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_password_sync")
    conn = memory_db(control)
    seed_ready_deployment(control, conn)
    intent = {"secret_refs": {"dashboard_password": "secret://arclink/dashboard/users/user_1/password"}}
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = worker_config(worker_mod, tmpdir)
        deployment = dict(conn.execute("SELECT * FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone())
        worker_mod._sync_dashboard_password_hash_from_secret(
            conn,
            deployment=deployment,
            worker=cfg,
            intent=intent,
            password_secret_preexisted=False,
        )
        first = conn.execute("SELECT password_hash FROM arclink_users WHERE user_id = 'user_1'").fetchone()["password_hash"]
        resolver = worker_mod.SovereignSecretResolver(
            env={},
            secret_store_dir=cfg.secret_store_dir / "dep_1",
            materialization_root=Path(tmpdir) / "materialized",
        )
        password = resolver._generated_secret_value("secret://arclink/dashboard/users/user_1/password")
        expect(api.verify_arclink_password(password, first), str(first))
        worker_mod._sync_dashboard_password_hash_from_secret(
            conn,
            deployment=deployment,
            worker=cfg,
            intent=intent,
            password_secret_preexisted=True,
        )
        second = conn.execute("SELECT password_hash FROM arclink_users WHERE user_id = 'user_1'").fetchone()["password_hash"]
        expect(second == first, f"existing dashboard secret should not force a new password hash: {first} != {second}")
    print("PASS test_dashboard_password_hash_sync_only_when_secret_is_new")


if __name__ == "__main__":
    test_fake_sovereign_worker_applies_ready_deployment()
    test_live_sovereign_worker_reconciles_compose_ps_health()
    test_tailscale_sovereign_worker_skips_cloudflare_dns()
    test_sovereign_worker_tears_down_active_deployment_idempotently()
    test_tailnet_port_allocation_ignores_released_deployments()
    test_sovereign_worker_is_disabled_until_explicitly_enabled()
    test_sovereign_worker_fails_closed_without_fleet_capacity()
    test_sovereign_worker_rechecks_lost_entitlement_before_placement()
    test_sovereign_worker_rechecks_missing_user_before_placement()
    test_sovereign_worker_rechecks_changed_status_before_placement()
    test_sovereign_worker_repairs_stale_local_host_load()
    test_sovereign_worker_recovers_stale_running_job()
    test_sovereign_worker_recovers_succeeded_job_without_handoff()
    test_compose_ps_transport_failure_records_failed_health()
    test_notion_webhook_secret_is_generated_without_notion_token()
    test_dashboard_password_secret_is_generated_for_canonical_handoff_store()
    test_dashboard_password_hash_sync_only_when_secret_is_new()
    print("\nAll 17 Sovereign worker tests passed.")
