#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import stat
import sqlite3
import sys
import tempfile
from dataclasses import asdict
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


def sample_intent() -> dict:
    return {
        "deployment": {"deployment_id": "dep_1"},
        "state_roots": {"root": "/arcdata/deployments/dep_1", "config": "/arcdata/deployments/dep_1/config"},
        "compose": {
            "services": {
                "dashboard": {
                    "image": "arclink/app:local",
                    "command": ["./bin/arclink-dashboard-placeholder.sh"],
                    "environment": {},
                    "volumes": [{"source": "/arcdata/deployments/dep_1/config", "target": "/config"}],
                    "labels": {"traefik.http.routers.arclink-dep-1-dashboard.rule": "Host(`u-amber-vault.example.test`)"},
                    "depends_on": [],
                    "secrets": [],
                },
                "nextcloud-db": {
                    "image": "postgres:16-alpine",
                    "command": [],
                    "environment": {"POSTGRES_PASSWORD_FILE": "/run/secrets/nextcloud_db_password"},
                    "volumes": [{"source": "/arcdata/deployments/dep_1/nextcloud/db", "target": "/var/lib/postgresql/data"}],
                    "labels": {},
                    "depends_on": [],
                    "secrets": [{"source": "nextcloud_db_password", "target": "/run/secrets/nextcloud_db_password"}],
                },
            },
            "secrets": {
                "nextcloud_db_password": {
                    "secret_ref": "secret://arclink/nextcloud/dep_1/db-password",
                    "target": "/run/secrets/nextcloud_db_password",
                }
            },
        },
        "dns": {
            "dashboard": {
                "hostname": "u-amber-vault.example.test",
                "record_type": "CNAME",
                "target": "edge.example.test",
                "proxied": True,
            }
        },
        "access": {
            "urls": {"dashboard": "https://u-amber-vault.example.test"},
            "ssh": {"strategy": "cloudflare_access_tcp"},
        },
    }


def test_executor_mutating_operations_fail_closed_without_live_flag() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_fail_closed_test")
    executor = mod.ArcLinkExecutor()
    intent = sample_intent()
    cases = (
        lambda: executor.docker_compose_apply(mod.DockerComposeApplyRequest(deployment_id="dep_1", intent=intent)),
        lambda: executor.cloudflare_dns_apply(mod.CloudflareDnsApplyRequest(deployment_id="dep_1", dns=intent["dns"])),
        lambda: executor.cloudflare_access_apply(mod.CloudflareAccessApplyRequest(deployment_id="dep_1", access=intent["access"])),
        lambda: executor.chutes_key_apply(mod.ChutesKeyApplyRequest(deployment_id="dep_1", action="create")),
        lambda: executor.stripe_action_apply(mod.StripeActionApplyRequest(deployment_id="dep_1", action="refund")),
        lambda: executor.rollback_apply(
            mod.RollbackApplyRequest(deployment_id="dep_1", plan={"actions": ("stop_rendered_services", "preserve_state_roots")})
        ),
    )
    for call in cases:
        try:
            call()
        except mod.ArcLinkLiveExecutionRequired as exc:
            expect("explicitly enabled" in str(exc), str(exc))
        else:
            raise AssertionError("expected executor operation to fail closed")
    print("PASS test_executor_mutating_operations_fail_closed_without_live_flag")


def test_runner_stdout_preserves_compose_ps_json() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_runner_stdout_test")
    json_lines = "\n".join(json.dumps({"Service": f"svc_{idx}", "State": "running"}) for idx in range(300))
    ordinary = "x" * 3000
    expect(mod._runner_stdout(("ps", "--all", "--format", "json"), json_lines) == json_lines, "compose ps JSON must not be truncated")
    expect(mod._runner_stdout(("up", "-d"), ordinary) == ordinary[-2000:], "ordinary command output should stay bounded")
    print("PASS test_runner_stdout_preserves_compose_ps_json")


def test_secret_resolvers_validate_refs_and_hide_material() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_secret_resolver_test")
    secret_ref = "secret://arclink/nextcloud/dep_1/db-password"
    secret_value = "sk_test_executor_plaintext_should_not_escape"
    resolver = mod.FakeSecretResolver({secret_ref: secret_value})
    resolved = resolver.materialize(secret_ref, "/run/secrets/nextcloud_db_password")
    rendered = json.dumps(asdict(resolved), sort_keys=True)
    expect(resolved.target_path == "/run/secrets/nextcloud_db_password", rendered)
    expect(secret_value not in rendered, rendered)

    try:
        resolver.materialize("nextcloud_db_password", "/run/secrets/nextcloud_db_password")
    except mod.ArcLinkSecretResolutionError as exc:
        expect("secret://" in str(exc), str(exc))
    else:
        raise AssertionError("expected invalid secret ref to fail")

    try:
        resolver.materialize("secret://arclink/missing", "/run/secrets/missing")
    except mod.ArcLinkSecretResolutionError as exc:
        expect("missing" in str(exc), str(exc))
    else:
        raise AssertionError("expected missing secret ref to fail")

    with tempfile.TemporaryDirectory() as tmp:
        file_resolver = mod.FileMaterializingSecretResolver(lambda ref: f"value-for-{ref}", Path(tmp))
        file_resolved = file_resolver.materialize(secret_ref, "/run/secrets/nextcloud_db_password")
        expect(file_resolved.target_path == "/run/secrets/nextcloud_db_password", str(file_resolved))
        expect((Path(tmp) / "nextcloud_db_password").read_text(encoding="utf-8") == f"value-for-{secret_ref}", tmp)
        parent_mode = stat.S_IMODE(Path(tmp).stat().st_mode)
        file_mode = stat.S_IMODE((Path(tmp) / "nextcloud_db_password").stat().st_mode)
        expect(parent_mode == 0o700, oct(parent_mode))
        expect(file_mode == 0o600, oct(file_mode))
        expect(
            not any(path.name.startswith(".nextcloud_db_password.") and not path.name.endswith(".lock") for path in Path(tmp).iterdir()),
            tmp,
        )
    print("PASS test_secret_resolvers_validate_refs_and_hide_material")


def test_fake_executor_consumes_rendered_intent_without_secret_leakage() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_fake_apply_test")
    intent = sample_intent()
    secret_ref = intent["compose"]["secrets"]["nextcloud_db_password"]["secret_ref"]
    secret_value = "sk_test_executor_plaintext_should_not_escape"
    executor = mod.ArcLinkExecutor(
        config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
        secret_resolver=mod.FakeSecretResolver({secret_ref: secret_value}),
    )
    docker = executor.docker_compose_apply(
        mod.DockerComposeApplyRequest(deployment_id="dep_1", intent=intent, idempotency_key="compose-1")
    )
    dns = executor.cloudflare_dns_apply(mod.CloudflareDnsApplyRequest(deployment_id="dep_1", dns=intent["dns"], zone_id="zone_test"))
    access = executor.cloudflare_access_apply(mod.CloudflareAccessApplyRequest(deployment_id="dep_1", access=intent["access"]))
    chutes = executor.chutes_key_apply(mod.ChutesKeyApplyRequest(deployment_id="dep_1", action="create", idempotency_key="chutes-1"))
    stripe = executor.stripe_action_apply(
        mod.StripeActionApplyRequest(
            deployment_id="dep_1",
            action="refund",
            customer_ref="secret://arclink/stripe/customer/dep_1",
            idempotency_key="refund-1",
        )
    )
    rollback = executor.rollback_apply(
        mod.RollbackApplyRequest(
            deployment_id="dep_1",
            plan={"actions": ("stop_rendered_services", "remove_unhealthy_containers", "preserve_state_roots")},
            idempotency_key="rollback-1",
        )
    )
    expect(docker.project_name == "arclink-dep_1", str(docker))
    expect(docker.services == ("dashboard", "nextcloud-db"), str(docker))
    expect(docker.secrets == {"nextcloud_db_password": "/run/secrets/nextcloud_db_password"}, str(docker))
    expect(dns.records == ("u-amber-vault.example.test",), str(dns))
    expect(access.applications == ("https://u-amber-vault.example.test",), str(access))
    expect(chutes.secret_ref == "secret://arclink/chutes/dep_1", str(chutes))
    expect(stripe.metadata["customer_ref"] == "secret://arclink/stripe/customer/dep_1", str(stripe))
    expect(rollback.preserve_state_roots, str(rollback))
    rendered = json.dumps(
        [asdict(docker), asdict(dns), asdict(access), asdict(chutes), asdict(stripe), asdict(rollback)],
        sort_keys=True,
    )
    expect(secret_value not in rendered, rendered)
    print("PASS test_fake_executor_consumes_rendered_intent_without_secret_leakage")


def test_fake_docker_compose_adapter_plans_paths_and_resumes_partial_apply() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_fake_compose_plan_test")
    intent = sample_intent()
    intent["compose"]["services"]["nextcloud"] = {
        "image": "nextcloud:31-apache",
        "command": ["apache2-foreground"],
        "environment": {
            "POSTGRES_HOST": "nextcloud-db",
            "POSTGRES_PASSWORD_FILE": "/run/secrets/nextcloud_db_password",
        },
        "volumes": [{"source": "/arcdata/deployments/dep_1/nextcloud/html", "target": "/var/www/html"}],
        "labels": {"traefik.http.routers.arclink-dep-1-files.rule": "Host(`files-amber-vault.example.test`)"},
        "depends_on": ["nextcloud-db"],
        "secrets": [{"source": "nextcloud_db_password", "target": "/run/secrets/nextcloud_db_password"}],
    }
    secret_ref = intent["compose"]["secrets"]["nextcloud_db_password"]["secret_ref"]
    executor = mod.ArcLinkExecutor(
        config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
        secret_resolver=mod.FakeSecretResolver({secret_ref: "sk_test_executor_plaintext_should_not_escape"}),
    )

    failed = executor.docker_compose_apply(
        mod.DockerComposeApplyRequest(
            deployment_id="dep_1",
            intent=intent,
            idempotency_key="compose-resume-1",
            fake_fail_after_services=2,
        )
    )
    expect(failed.status == "failed", str(failed))
    expect(failed.env_file == "/arcdata/deployments/dep_1/config/arclink.env", str(failed))
    expect(failed.compose_file == "/arcdata/deployments/dep_1/config/compose.yaml", str(failed))
    expect(failed.service_start_order == ("dashboard", "nextcloud-db", "nextcloud"), str(failed))
    expect(failed.metadata["applied_services"] == ("dashboard", "nextcloud-db"), str(failed.metadata))
    expect(failed.metadata["label_count"] == 2, str(failed.metadata))

    resumed = executor.docker_compose_apply(
        mod.DockerComposeApplyRequest(deployment_id="dep_1", intent=intent, idempotency_key="compose-resume-1")
    )
    expect(resumed.status == "applied", str(resumed))
    expect(resumed.metadata["resumed_from_service_count"] == 2, str(resumed.metadata))
    expect(resumed.metadata["applied_services"] == resumed.service_start_order, str(resumed.metadata))
    expect("/arcdata/deployments/dep_1/nextcloud/html" in resumed.volumes, str(resumed.volumes))

    replay = executor.docker_compose_apply(
        mod.DockerComposeApplyRequest(deployment_id="dep_1", intent=intent, idempotency_key="compose-resume-1")
    )
    expect(replay.status == "applied", str(replay))
    expect(replay.metadata["idempotent_replay"], str(replay.metadata))
    expect(replay.metadata["attempts"] == resumed.metadata["attempts"], str(replay.metadata))
    print("PASS test_fake_docker_compose_adapter_plans_paths_and_resumes_partial_apply")


def test_fake_docker_compose_rejects_explicit_key_reuse_after_applied_intent_changes() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_fake_compose_applied_digest_test")
    intent = sample_intent()
    secret_ref = intent["compose"]["secrets"]["nextcloud_db_password"]["secret_ref"]
    executor = mod.ArcLinkExecutor(
        config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
        secret_resolver=mod.FakeSecretResolver({secret_ref: "sk_test_executor_plaintext_should_not_escape"}),
    )

    applied = executor.docker_compose_apply(
        mod.DockerComposeApplyRequest(deployment_id="dep_1", intent=intent, idempotency_key="compose-digest-1")
    )
    changed = sample_intent()
    changed["compose"]["services"]["dashboard"]["environment"] = {"ARCLINK_PUBLIC_BASE_URL": "https://changed.example.test"}

    try:
        executor.docker_compose_apply(
            mod.DockerComposeApplyRequest(deployment_id="dep_1", intent=changed, idempotency_key="compose-digest-1")
        )
    except mod.ArcLinkExecutorError as exc:
        expect("different rendered intent digest" in str(exc), str(exc))
    else:
        raise AssertionError("expected explicit idempotency key reuse with changed intent to fail")
    expect(applied.status == "applied", str(applied))
    print("PASS test_fake_docker_compose_rejects_explicit_key_reuse_after_applied_intent_changes")


def test_fake_docker_compose_replays_applied_state_without_rematerializing_secrets() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_fake_compose_secret_replay_test")
    intent = sample_intent()
    secret_ref = intent["compose"]["secrets"]["nextcloud_db_password"]["secret_ref"]
    resolver_values = {secret_ref: "sk_test_executor_plaintext_should_not_escape"}
    resolver = mod.FakeSecretResolver(resolver_values)
    executor = mod.ArcLinkExecutor(
        config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
        secret_resolver=resolver,
    )

    applied = executor.docker_compose_apply(
        mod.DockerComposeApplyRequest(deployment_id="dep_1", intent=intent, idempotency_key="compose-secret-replay-1")
    )
    resolver_values.clear()
    replay = executor.docker_compose_apply(
        mod.DockerComposeApplyRequest(deployment_id="dep_1", intent=intent, idempotency_key="compose-secret-replay-1")
    )

    expect(applied.status == "applied", str(applied))
    expect(replay.status == "applied", str(replay))
    expect(replay.metadata["idempotent_replay"], str(replay.metadata))
    expect(len(resolver.resolved) == 1, str(resolver.resolved))
    expect(replay.secrets == {"nextcloud_db_password": "/run/secrets/nextcloud_db_password"}, str(replay))
    print("PASS test_fake_docker_compose_replays_applied_state_without_rematerializing_secrets")


def test_fake_docker_compose_rejects_explicit_key_reuse_after_partial_failed_intent_changes() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_fake_compose_failed_digest_test")
    intent = sample_intent()
    secret_ref = intent["compose"]["secrets"]["nextcloud_db_password"]["secret_ref"]
    executor = mod.ArcLinkExecutor(
        config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
        secret_resolver=mod.FakeSecretResolver({secret_ref: "sk_test_executor_plaintext_should_not_escape"}),
    )

    failed = executor.docker_compose_apply(
        mod.DockerComposeApplyRequest(
            deployment_id="dep_1",
            intent=intent,
            idempotency_key="compose-digest-partial-1",
            fake_fail_after_services=1,
        )
    )
    changed = sample_intent()
    changed["compose"]["services"]["worker"] = {
        "image": "arclink/app:local",
        "command": ["./bin/arclink-worker-placeholder.sh"],
        "environment": {},
        "volumes": [],
        "labels": {},
        "depends_on": ["dashboard"],
        "secrets": [],
    }

    try:
        executor.docker_compose_apply(
            mod.DockerComposeApplyRequest(deployment_id="dep_1", intent=changed, idempotency_key="compose-digest-partial-1")
        )
    except mod.ArcLinkExecutorError as exc:
        expect("different rendered intent digest" in str(exc), str(exc))
    else:
        raise AssertionError("expected changed partial run intent to fail before resume")
    expect(failed.status == "failed", str(failed))
    print("PASS test_fake_docker_compose_rejects_explicit_key_reuse_after_partial_failed_intent_changes")


def test_fake_docker_compose_rejects_zero_failure_limit() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_fake_compose_zero_fail_test")
    intent = sample_intent()
    secret_ref = intent["compose"]["secrets"]["nextcloud_db_password"]["secret_ref"]
    executor = mod.ArcLinkExecutor(
        config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
        secret_resolver=mod.FakeSecretResolver({secret_ref: "sk_test_executor_plaintext_should_not_escape"}),
    )

    try:
        executor.docker_compose_apply(
            mod.DockerComposeApplyRequest(
                deployment_id="dep_1",
                intent=intent,
                idempotency_key="compose-zero-fail-1",
                fake_fail_after_services=0,
            )
        )
    except mod.ArcLinkExecutorError as exc:
        expect("greater than zero" in str(exc), str(exc))
    else:
        raise AssertionError("expected zero fake failure limit to be rejected")
    print("PASS test_fake_docker_compose_rejects_zero_failure_limit")


def test_fake_provider_and_edge_adapters_are_idempotent_and_secret_ref_only() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_fake_provider_edge_test")
    intent = sample_intent()
    executor = mod.ArcLinkExecutor(config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"))

    dns = executor.cloudflare_dns_apply(
        mod.CloudflareDnsApplyRequest(deployment_id="dep_1", dns=intent["dns"], zone_id="zone_test", idempotency_key="dns-1")
    )
    dns_replay = executor.cloudflare_dns_apply(
        mod.CloudflareDnsApplyRequest(deployment_id="dep_1", dns=intent["dns"], zone_id="zone_test", idempotency_key="dns-1")
    )
    access = executor.cloudflare_access_apply(
        mod.CloudflareAccessApplyRequest(deployment_id="dep_1", access=intent["access"], idempotency_key="access-1")
    )
    created = executor.chutes_key_apply(
        mod.ChutesKeyApplyRequest(
            deployment_id="dep_1",
            action="create",
            secret_ref="secret://arclink/chutes/dep_1",
            idempotency_key="chutes-create-1",
        )
    )
    rotated = executor.chutes_key_apply(
        mod.ChutesKeyApplyRequest(
            deployment_id="dep_1",
            action="rotate",
            secret_ref="secret://arclink/chutes/dep_1",
            idempotency_key="chutes-rotate-1",
        )
    )
    revoked = executor.chutes_key_apply(
        mod.ChutesKeyApplyRequest(
            deployment_id="dep_1",
            action="revoke",
            secret_ref="secret://arclink/chutes/dep_1",
            idempotency_key="chutes-revoke-1",
        )
    )
    revoke_replay = executor.chutes_key_apply(
        mod.ChutesKeyApplyRequest(
            deployment_id="dep_1",
            action="revoke",
            secret_ref="secret://arclink/chutes/dep_1",
            idempotency_key="chutes-revoke-1",
        )
    )

    expect(dns.records == ("u-amber-vault.example.test",), str(dns))
    expect(dns.metadata["desired_records"] == ("CNAME u-amber-vault.example.test -> edge.example.test proxied",), str(dns))
    expect(dns_replay.metadata["idempotent_replay"], str(dns_replay.metadata))
    expect(access.applications == ("https://u-amber-vault.example.test",), str(access))
    expect(access.metadata["ssh_strategy"] == "cloudflare_access_tcp", str(access.metadata))
    expect(created.secret_ref == "secret://arclink/chutes/dep_1", str(created))
    expect(rotated.secret_ref == created.secret_ref, str(rotated))
    expect(rotated.key_id != created.key_id, f"expected rotation to create a new fake key: {created} {rotated}")
    expect(rotated.metadata["previous_key_id"] == created.key_id, str(rotated.metadata))
    expect(revoked.status == "applied", str(revoked))
    expect(revoke_replay.key_id == revoked.key_id, str(revoke_replay))
    expect(revoke_replay.metadata["idempotent_replay"], str(revoke_replay.metadata))

    rendered = json.dumps([asdict(dns), asdict(access), asdict(created), asdict(rotated), asdict(revoked)], sort_keys=True)
    expect("sk_" not in rendered and "api_key" not in rendered.lower(), rendered)

    try:
        executor.cloudflare_access_apply(
            mod.CloudflareAccessApplyRequest(
                deployment_id="dep_1",
                access={"urls": {}, "ssh": {"strategy": "raw_http", "hostname": "ssh.example.test"}},
            )
        )
    except mod.ArcLinkExecutorError as exc:
        expect("Cloudflare Access TCP" in str(exc), str(exc))
    else:
        raise AssertionError("expected non-Cloudflare TCP SSH strategy to fail")
    print("PASS test_fake_provider_and_edge_adapters_are_idempotent_and_secret_ref_only")


def test_fake_dns_rejects_idempotency_key_reuse_with_changed_records() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_fake_dns_replay_digest_test")
    intent = sample_intent()
    executor = mod.ArcLinkExecutor(config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"))

    applied = executor.cloudflare_dns_apply(
        mod.CloudflareDnsApplyRequest(deployment_id="dep_1", dns=intent["dns"], zone_id="zone_test", idempotency_key="dns-digest-1")
    )
    changed = sample_intent()
    changed["dns"]["dashboard"]["target"] = "other-edge.example.test"

    try:
        executor.cloudflare_dns_apply(
            mod.CloudflareDnsApplyRequest(
                deployment_id="dep_1",
                dns=changed["dns"],
                zone_id="zone_test",
                idempotency_key="dns-digest-1",
            )
        )
    except mod.ArcLinkExecutorError as exc:
        expect("cloudflare_dns_apply" in str(exc), str(exc))
        expect("different inputs" in str(exc), str(exc))
    else:
        raise AssertionError("expected reused DNS idempotency key with changed records to fail")
    expect(applied.status == "applied", str(applied))
    print("PASS test_fake_dns_rejects_idempotency_key_reuse_with_changed_records")


def test_fake_access_rejects_idempotency_key_reuse_with_changed_plan() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_fake_access_replay_digest_test")
    intent = sample_intent()
    executor = mod.ArcLinkExecutor(config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"))

    applied = executor.cloudflare_access_apply(
        mod.CloudflareAccessApplyRequest(deployment_id="dep_1", access=intent["access"], idempotency_key="access-digest-1")
    )
    changed_app = sample_intent()
    changed_app["access"]["urls"]["dashboard"] = "https://changed.example.test"
    changed_ssh = sample_intent()
    changed_ssh["access"]["ssh"]["hostname"] = "ssh.changed.example.test"

    for changed in (changed_app, changed_ssh):
        try:
            executor.cloudflare_access_apply(
                mod.CloudflareAccessApplyRequest(
                    deployment_id="dep_1",
                    access=changed["access"],
                    idempotency_key="access-digest-1",
                )
            )
        except mod.ArcLinkExecutorError as exc:
            expect("cloudflare_access_apply" in str(exc), str(exc))
            expect("different inputs" in str(exc), str(exc))
        else:
            raise AssertionError("expected reused Access idempotency key with changed plan to fail")
    expect(applied.status == "applied", str(applied))
    print("PASS test_fake_access_rejects_idempotency_key_reuse_with_changed_plan")


def test_fake_chutes_replay_is_bound_to_action_and_secret_ref() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_fake_chutes_replay_digest_test")
    executor = mod.ArcLinkExecutor(config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"))

    created = executor.chutes_key_apply(
        mod.ChutesKeyApplyRequest(
            deployment_id="dep_1",
            action="create",
            secret_ref="secret://arclink/chutes/dep_1",
            idempotency_key="chutes-digest-1",
        )
    )
    replay = executor.chutes_key_apply(
        mod.ChutesKeyApplyRequest(
            deployment_id="dep_1",
            action="create",
            secret_ref="secret://arclink/chutes/dep_1",
            idempotency_key="chutes-digest-1",
        )
    )
    expect(replay.action == created.action, str(replay))
    expect(replay.secret_ref == created.secret_ref, str(replay))
    expect(replay.key_id == created.key_id, str(replay))
    expect(replay.metadata["idempotent_replay"], str(replay.metadata))

    changed_requests = (
        mod.ChutesKeyApplyRequest(
            deployment_id="dep_1",
            action="rotate",
            secret_ref="secret://arclink/chutes/dep_1",
            idempotency_key="chutes-digest-1",
        ),
        mod.ChutesKeyApplyRequest(
            deployment_id="dep_1",
            action="create",
            secret_ref="secret://arclink/chutes/dep_2",
            idempotency_key="chutes-digest-1",
        ),
    )
    for request in changed_requests:
        try:
            executor.chutes_key_apply(request)
        except mod.ArcLinkExecutorError as exc:
            expect("chutes_key_apply" in str(exc), str(exc))
            expect("different inputs" in str(exc), str(exc))
        else:
            raise AssertionError("expected reused Chutes idempotency key with changed inputs to fail")
    print("PASS test_fake_chutes_replay_is_bound_to_action_and_secret_ref")


def test_live_chutes_client_receives_idempotency_key_and_replays_result() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_live_chutes_client_test")
    control = load_module("arclink_control.py", "arclink_control_live_chutes_client_test")

    class RecordingChutesClient:
        def __init__(self) -> None:
            self.calls = []

        def create_key(self, *, deployment_id, label, secret_ref, idempotency_key):
            self.calls.append(
                {
                    "deployment_id": deployment_id,
                    "label": label,
                    "secret_ref": secret_ref,
                    "idempotency_key": idempotency_key,
                }
            )
            return {"id": f"ck_live_{len(self.calls)}", "status": "applied"}

        def rotate_key(self, *, deployment_id, label, secret_ref, idempotency_key):
            raise AssertionError("unexpected rotate")

        def revoke_key(self, *, deployment_id, label, secret_ref, idempotency_key):
            raise AssertionError("unexpected revoke")

    client = RecordingChutesClient()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    executor = mod.ArcLinkExecutor(
        config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="live"),
        chutes_client=client,
        operation_conn=conn,
    )
    request = mod.ChutesKeyApplyRequest(
        deployment_id="dep_1",
        action="create",
        secret_ref="secret://arclink/chutes/dep_1",
        label="dep_1_key",
        idempotency_key="chutes-live-1",
    )
    created = executor.chutes_key_apply(request)
    replay = executor.chutes_key_apply(request)

    expect(created.live is True, str(created))
    expect(created.key_id == "ck_live_1", str(created))
    expect(created.metadata["idempotency_key"] == "chutes-live-1", str(created.metadata))
    expect(created.metadata["provider_refs"]["chutes_key_id"] == "ck_live_1", str(created.metadata))
    expect(replay.key_id == created.key_id, str(replay))
    expect(replay.metadata["idempotent_replay"], str(replay.metadata))
    expect(len(client.calls) == 1, str(client.calls))
    expect(client.calls[0]["idempotency_key"] == "chutes-live-1", str(client.calls))
    row = conn.execute(
        "SELECT status, provider_refs_json, result_json FROM arclink_operation_idempotency WHERE operation_kind = ? AND idempotency_key = ?",
        ("chutes_key_apply", "chutes-live-1"),
    ).fetchone()
    expect(row is not None and row["status"] == "succeeded", str(dict(row) if row else {}))
    expect(json.loads(row["provider_refs_json"]) == {"chutes_key_id": "ck_live_1"}, str(dict(row)))
    print("PASS test_live_chutes_client_receives_idempotency_key_and_replays_result")


def test_live_chutes_client_missing_fails_closed() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_live_chutes_missing_test")
    executor = mod.ArcLinkExecutor(config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="live"))
    try:
        executor.chutes_key_apply(
            mod.ChutesKeyApplyRequest(
                deployment_id="dep_1",
                action="create",
                secret_ref="secret://arclink/chutes/dep_1",
                idempotency_key="chutes-missing-1",
            )
        )
    except mod.ArcLinkExecutorError as exc:
        expect("ChutesKeyClient" in str(exc), str(exc))
    else:
        raise AssertionError("expected missing live Chutes client to fail closed")
    print("PASS test_live_chutes_client_missing_fails_closed")


def test_live_stripe_client_receives_idempotency_key_and_replays_result() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_live_stripe_client_test")
    control = load_module("arclink_control.py", "arclink_control_live_stripe_client_test")

    class RecordingStripeClient:
        def __init__(self) -> None:
            self.calls = []

        def refund(self, *, deployment_id, customer_ref, idempotency_key, metadata):
            self.calls.append(
                {
                    "action": "refund",
                    "deployment_id": deployment_id,
                    "customer_ref": customer_ref,
                    "idempotency_key": idempotency_key,
                    "metadata": dict(metadata),
                }
            )
            return {"refund_id": f"re_live_{len(self.calls)}", "status": "applied"}

        def cancel(self, *, deployment_id, customer_ref, idempotency_key, metadata):
            raise AssertionError("unexpected cancel")

        def portal(self, *, deployment_id, customer_ref, idempotency_key, metadata):
            raise AssertionError("unexpected portal")

    client = RecordingStripeClient()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    executor = mod.ArcLinkExecutor(
        config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="live"),
        stripe_client=client,
        operation_conn=conn,
    )
    request = mod.StripeActionApplyRequest(
        deployment_id="dep_1",
        action="refund",
        customer_ref="secret://arclink/stripe/customer/dep_1",
        idempotency_key="stripe-refund-1",
        metadata={"reason": "operator_test"},
    )
    refunded = executor.stripe_action_apply(request)
    replay = executor.stripe_action_apply(request)

    expect(refunded.live is True, str(refunded))
    expect(refunded.metadata["idempotency_key"] == "stripe-refund-1", str(refunded.metadata))
    expect(refunded.metadata["provider_refs"]["stripe_action_id"] == "re_live_1", str(refunded.metadata))
    expect(replay.metadata["idempotent_replay"], str(replay.metadata))
    expect(len(client.calls) == 1, str(client.calls))
    expect(client.calls[0]["idempotency_key"] == "stripe-refund-1", str(client.calls))
    expect(client.calls[0]["customer_ref"] == "secret://arclink/stripe/customer/dep_1", str(client.calls))
    row = conn.execute(
        "SELECT status, provider_refs_json, result_json FROM arclink_operation_idempotency WHERE operation_kind = ? AND idempotency_key = ?",
        ("stripe_action_apply", "stripe-refund-1"),
    ).fetchone()
    expect(row is not None and row["status"] == "succeeded", str(dict(row) if row else {}))
    expect(json.loads(row["provider_refs_json"]) == {"stripe_action_id": "re_live_1"}, str(dict(row)))
    print("PASS test_live_stripe_client_receives_idempotency_key_and_replays_result")


def test_live_stripe_client_missing_fails_closed() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_live_stripe_missing_test")
    executor = mod.ArcLinkExecutor(config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="live"))
    try:
        executor.stripe_action_apply(
            mod.StripeActionApplyRequest(
                deployment_id="dep_1",
                action="refund",
                customer_ref="secret://arclink/stripe/customer/dep_1",
                idempotency_key="stripe-missing-1",
            )
        )
    except mod.ArcLinkExecutorError as exc:
        expect("StripeActionClient" in str(exc), str(exc))
    else:
        raise AssertionError("expected missing live Stripe client to fail closed")
    print("PASS test_live_stripe_client_missing_fails_closed")


def test_cloudflare_dns_apply_rejects_unsupported_record_types() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_dns_record_type_test")
    intent = sample_intent()
    intent["dns"]["dashboard"]["record_type"] = "MX"
    executor = mod.ArcLinkExecutor(config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"))

    try:
        executor.cloudflare_dns_apply(mod.CloudflareDnsApplyRequest(deployment_id="dep_1", dns=intent["dns"], zone_id="zone_test"))
    except mod.ArcLinkExecutorError as exc:
        expect("unsupported ArcLink DNS record type" in str(exc), str(exc))
        expect("CNAME" in str(exc) and "TXT" in str(exc), str(exc))
    else:
        raise AssertionError("expected unsupported DNS record type to fail")
    print("PASS test_cloudflare_dns_apply_rejects_unsupported_record_types")


def test_live_cloudflare_dns_apply_accepts_secret_ref_token_and_cleans_copy() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_cloudflare_token_ref_test")
    intent = sample_intent()
    original_find = mod._cloudflare_find_dns_record
    original_request = mod._cloudflare_request
    old_env = os.environ.copy()
    calls: list[tuple[str, str]] = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "materialized"
            resolver = mod.FileMaterializingSecretResolver(
                lambda ref: "cf_token_from_secret_ref" if ref == "secret://arclink/cloudflare/api-token" else "",
                root,
            )
            os.environ.pop("CLOUDFLARE_API_TOKEN", None)
            os.environ["CLOUDFLARE_API_TOKEN_REF"] = "secret://arclink/cloudflare/api-token"
            mod._cloudflare_find_dns_record = lambda *, zone_id, token, record: calls.append(("find", token)) or {}
            mod._cloudflare_request = lambda method, path, *, token, body=None: calls.append((method, token)) or {"result": {"id": "dns_1"}}
            executor = mod.ArcLinkExecutor(
                config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="local"),
                secret_resolver=resolver,
            )
            result = executor.cloudflare_dns_apply(
                mod.CloudflareDnsApplyRequest(deployment_id="dep_1", dns=intent["dns"], zone_id="zone_test")
            )
            expect(result.records == ("u-amber-vault.example.test",), str(result))
            expect(calls == [("find", "cf_token_from_secret_ref"), ("POST", "cf_token_from_secret_ref")], str(calls))
            expect(not root.exists() or not any(root.iterdir()), f"expected materialized token copy to be cleaned: {root}")
    finally:
        mod._cloudflare_find_dns_record = original_find
        mod._cloudflare_request = original_request
        os.environ.clear()
        os.environ.update(old_env)
    print("PASS test_live_cloudflare_dns_apply_accepts_secret_ref_token_and_cleans_copy")


def test_fake_rollback_executor_is_idempotent_and_preserves_state_roots() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_fake_rollback_test")
    executor = mod.ArcLinkExecutor(config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"))
    plan = {
        "actions": ("stop_rendered_services", "remove_unhealthy_containers", "preserve_state_roots", "leave_secret_refs_for_manual_review"),
        "compose": {"services": {"dashboard": {}, "nextcloud": {}, "qmd-mcp": {}}},
        "service_health": {"dashboard": {"status": "healthy"}, "nextcloud": {"status": "unhealthy"}, "qmd-mcp": {"status": "failed"}},
        "state_roots": {
            "root": "/arcdata/deployments/dep_1",
            "vault": "/arcdata/deployments/dep_1/vault",
            "nextcloud": "/arcdata/deployments/dep_1/state/nextcloud",
        },
        "secret_refs": {
            "chutes_api_key": "secret://arclink/chutes/dep_1",
            "nextcloud_db_password": "secret://arclink/nextcloud/dep_1/db-password",
        },
    }
    result = executor.rollback_apply(mod.RollbackApplyRequest(deployment_id="dep_1", plan=plan, idempotency_key="rollback-safe-1"))
    replay = executor.rollback_apply(mod.RollbackApplyRequest(deployment_id="dep_1", plan=plan, idempotency_key="rollback-safe-1"))

    expect(result.status == "applied", str(result))
    expect(result.preserve_state_roots, str(result))
    expect("stop:nextcloud" in result.actions, str(result.actions))
    expect("remove_unhealthy:nextcloud" in result.actions, str(result.actions))
    expect("remove_unhealthy:qmd-mcp" in result.actions, str(result.actions))
    expect("/arcdata/deployments/dep_1/vault" in result.metadata["protected_state_roots"], str(result.metadata))
    expect("secret://arclink/chutes/dep_1" in result.metadata["secret_refs_for_review"], str(result.metadata))
    expect(replay.metadata["idempotent_replay"], str(replay.metadata))

    try:
        executor.rollback_apply(
            mod.RollbackApplyRequest(
                deployment_id="dep_1",
                plan={"actions": ("stop_rendered_services", "delete_state_roots"), "state_roots": {"vault": "/arcdata/vault"}},
            )
        )
    except mod.ArcLinkExecutorError as exc:
        expect("preserve" in str(exc) or "must not delete" in str(exc), str(exc))
    else:
        raise AssertionError("expected destructive rollback plan to fail")

    destructive_variants = (
        "state_root_delete",
        "delete-vault-data",
    )
    for action in destructive_variants:
        try:
            executor.rollback_apply(
                mod.RollbackApplyRequest(
                    deployment_id="dep_1",
                    plan={"actions": ("preserve_state_roots", action), "state_roots": {"vault": "/arcdata/vault"}},
                )
            )
        except mod.ArcLinkExecutorError as exc:
            expect("must not delete" in str(exc), str(exc))
        else:
            raise AssertionError(f"expected destructive rollback action to fail: {action}")
    print("PASS test_fake_rollback_executor_is_idempotent_and_preserves_state_roots")


def test_fake_rollback_rejects_idempotency_key_reuse_with_changed_plan() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_fake_rollback_replay_digest_test")
    executor = mod.ArcLinkExecutor(config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"))
    plan = {
        "actions": ("stop_rendered_services", "remove_unhealthy_containers", "preserve_state_roots"),
        "services": ("dashboard", "nextcloud"),
        "service_health": {"dashboard": {"status": "healthy"}, "nextcloud": {"status": "unhealthy"}},
        "state_roots": {"root": "/arcdata/deployments/dep_1", "vault": "/arcdata/deployments/dep_1/vault"},
    }
    applied = executor.rollback_apply(mod.RollbackApplyRequest(deployment_id="dep_1", plan=plan, idempotency_key="rollback-digest-1"))

    changed_health = dict(plan)
    changed_health["service_health"] = {"dashboard": {"status": "unhealthy"}, "nextcloud": {"status": "unhealthy"}}
    changed_actions = dict(plan)
    changed_actions["actions"] = ("stop_rendered_services", "preserve_state_roots")

    for changed in (changed_health, changed_actions):
        try:
            executor.rollback_apply(
                mod.RollbackApplyRequest(deployment_id="dep_1", plan=changed, idempotency_key="rollback-digest-1")
            )
        except mod.ArcLinkExecutorError as exc:
            expect("rollback_apply" in str(exc), str(exc))
            expect("different inputs" in str(exc), str(exc))
        else:
            raise AssertionError("expected reused rollback idempotency key with changed plan to fail")
    expect(applied.status == "applied", str(applied))
    print("PASS test_fake_rollback_rejects_idempotency_key_reuse_with_changed_plan")


def test_fake_docker_compose_rejects_missing_depends_on_service() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_compose_missing_dependency_test")
    intent = sample_intent()
    intent["compose"]["services"]["dashboard"]["depends_on"] = ["missing-db"]
    secret_ref = intent["compose"]["secrets"]["nextcloud_db_password"]["secret_ref"]
    executor = mod.ArcLinkExecutor(
        config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
        secret_resolver=mod.FakeSecretResolver({secret_ref: "sk_test_executor_plaintext_should_not_escape"}),
    )

    try:
        executor.docker_compose_apply(
            mod.DockerComposeApplyRequest(deployment_id="dep_1", intent=intent, idempotency_key="compose-missing-dep-1")
        )
    except mod.ArcLinkExecutorError as exc:
        expect("dashboard" in str(exc), str(exc))
        expect("missing-db" in str(exc), str(exc))
    else:
        raise AssertionError("expected missing Compose dependency to fail")
    print("PASS test_fake_docker_compose_rejects_missing_depends_on_service")


def test_dry_run_output_is_secret_free() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_dry_run_test")
    intent = sample_intent()
    executor = mod.ArcLinkExecutor()
    step = executor.docker_compose_dry_run(
        mod.DockerComposeApplyRequest(deployment_id="dep_1", intent=intent)
    )
    rendered = json.dumps({
        "operation": step.operation,
        "project_name": step.project_name,
        "services": step.services,
        "compose_file": step.compose_file,
        "env_file": step.env_file,
    })
    expect("sk_" not in rendered, f"secret leaked in dry run: {rendered}")
    expect("secret://" not in rendered, f"secret ref leaked in dry run: {rendered}")
    expect(step.project_name == "arclink-dep_1", str(step))
    expect(step.services == ("dashboard", "nextcloud-db"), str(step))
    print("PASS test_dry_run_output_is_secret_free")


def test_injectable_docker_runner_receives_commands() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_runner_test")
    intent = sample_intent()
    secret_ref = intent["compose"]["secrets"]["nextcloud_db_password"]["secret_ref"]
    runner = mod.FakeDockerRunner()
    executor = mod.ArcLinkExecutor(
        config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="live"),
        secret_resolver=mod.FakeSecretResolver({secret_ref: "sk_test_secret"}),
        docker_runner=runner,
    )
    result = executor.docker_compose_apply(
        mod.DockerComposeApplyRequest(deployment_id="dep_1", intent=intent, idempotency_key="runner-1")
    )
    expect(result.status == "applied", str(result))
    expect(result.live, str(result))
    expect(len(runner.runs) == 1, f"expected 1 runner call, got {len(runner.runs)}")
    expect(runner.runs[0]["args"] == ("up", "-d", "--remove-orphans"), str(runner.runs[0]))
    expect(runner.runs[0]["project_name"] == "arclink-dep_1", str(runner.runs[0]))
    # Secret value must not appear in runner record
    rendered = json.dumps(runner.runs)
    expect("sk_test_secret" not in rendered, f"secret leaked to runner: {rendered}")
    print("PASS test_injectable_docker_runner_receives_commands")


def test_live_docker_compose_file_preserves_service_ports() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_compose_ports_test")
    intent = sample_intent()
    secret_ref = intent["compose"]["secrets"]["nextcloud_db_password"]["secret_ref"]
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir) / "deployment"
        intent["state_roots"] = {"root": str(root), "config": str(root / "config")}
        intent["compose"]["services"]["dashboard"]["ports"] = ["127.0.0.1:8443:3210"]

        class RecordingRunner:
            def __init__(self) -> None:
                self.runs: list[dict[str, str | tuple[str, ...]]] = []

            def run(self, args, *, project_name: str, env_file: str, compose_file: str):
                self.runs.append(
                    {
                        "args": tuple(args),
                        "project_name": project_name,
                        "env_file": env_file,
                        "compose_file": compose_file,
                    }
                )

        runner = RecordingRunner()
        executor = mod.ArcLinkExecutor(
            config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="live"),
            secret_resolver=mod.FileMaterializingSecretResolver(
                value_provider=lambda ref: "sk_test_secret" if ref == secret_ref else "",
                materialization_root=root / "materialized",
            ),
            docker_runner=runner,
        )
        executor.docker_compose_apply(
            mod.DockerComposeApplyRequest(deployment_id="dep_1", intent=intent, idempotency_key="ports-1")
        )
        compose_doc = json.loads((root / "config" / "compose.yaml").read_text(encoding="utf-8"))
        expect(compose_doc["services"]["dashboard"]["ports"] == ["127.0.0.1:8443:3210"], str(compose_doc))
    print("PASS test_live_docker_compose_file_preserves_service_ports")


def test_live_docker_compose_apply_keeps_file_backed_secrets_for_container_restart() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_secret_restart_test")
    intent = sample_intent()
    secret_ref = intent["compose"]["secrets"]["nextcloud_db_password"]["secret_ref"]
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir) / "materialized"
        runner = mod.FakeDockerRunner()
        resolver = mod.FileMaterializingSecretResolver(
            value_provider=lambda ref: "sk_test_secret" if ref == secret_ref else "",
            materialization_root=root,
        )
        executor = mod.ArcLinkExecutor(
            config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="live"),
            secret_resolver=resolver,
            docker_runner=runner,
        )
        result = executor.docker_compose_apply(
            mod.DockerComposeApplyRequest(deployment_id="dep_1", intent=intent, idempotency_key="cleanup-1")
        )
        secret_copy = root / "nextcloud_db_password"
        expect(result.status == "applied", str(result))
        expect(secret_copy.is_file(), f"compose secret source must remain for docker restart: {secret_copy}")
        expect(secret_copy.stat().st_mode & 0o777 == 0o600, oct(secret_copy.stat().st_mode & 0o777))
    print("PASS test_live_docker_compose_apply_keeps_file_backed_secrets_for_container_restart")


def test_live_docker_compose_apply_cleans_materialized_secret_copies_on_runner_failure() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_secret_cleanup_failure_test")
    intent = sample_intent()
    secret_ref = intent["compose"]["secrets"]["nextcloud_db_password"]["secret_ref"]
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir) / "deployment"
        intent["state_roots"] = {"root": str(root), "config": str(root / "config")}
        secrets_root = root / "config" / "secrets"

        class FailingRunner:
            def run(self, args, *, project_name: str, env_file: str, compose_file: str):
                expect((secrets_root / "nextcloud_db_password").is_file(), "secret must be materialized before runner")
                raise mod.ArcLinkExecutorError("compose transport failed")

        resolver = mod.FileMaterializingSecretResolver(
            value_provider=lambda ref: "sk_test_secret" if ref == secret_ref else "",
            materialization_root=secrets_root,
        )
        executor = mod.ArcLinkExecutor(
            config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="live"),
            secret_resolver=resolver,
            docker_runner=FailingRunner(),
        )
        try:
            executor.docker_compose_apply(
                mod.DockerComposeApplyRequest(deployment_id="dep_1", intent=intent, idempotency_key="cleanup-failure-1")
            )
        except mod.ArcLinkExecutorError as exc:
            expect("compose transport failed" in str(exc), str(exc))
        else:
            raise AssertionError("expected runner failure")
        expect(not (secrets_root / "nextcloud_db_password").exists(), f"materialized secret should be cleaned: {secrets_root}")
        expect(not any(secrets_root.glob(".nextcloud_db_password.*")), f"temporary secret files should be cleaned: {list(secrets_root.iterdir()) if secrets_root.exists() else []}")
    print("PASS test_live_docker_compose_apply_cleans_materialized_secret_copies_on_runner_failure")


def test_ssh_docker_runner_cleans_remote_secrets_after_compose_failure() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_ssh_cleanup_failure_test")

    class Proc:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    calls: list[tuple[str, ...]] = []
    original_run = mod.subprocess.run

    def fake_run(cmd, **kwargs):
        call = tuple(str(part) for part in cmd)
        calls.append(call)
        rendered = " ".join(call)
        if "docker compose" in rendered:
            return Proc(1, stderr="compose failed after sync")
        return Proc(0, stdout="ok")

    with tempfile.TemporaryDirectory() as tmpdir:
        compose_file = Path(tmpdir) / "dep" / "config" / "compose.yaml"
        env_file = compose_file.parent / "arclink.env"
        compose_file.parent.mkdir(parents=True)
        compose_file.write_text("services: {}\n", encoding="utf-8")
        env_file.write_text("", encoding="utf-8")
        try:
            mod.subprocess.run = fake_run
            runner = mod.SshDockerComposeRunner(
                host="worker.example.test",
                user="arclink",
                allowed_hosts=("worker.example.test",),
            )
            try:
                runner.run(
                    ("up", "-d", "--remove-orphans"),
                    project_name="arclink-dep",
                    env_file=str(env_file),
                    compose_file=str(compose_file),
                )
            except mod.ArcLinkExecutorError as exc:
                expect("ssh docker compose failed" in str(exc), str(exc))
            else:
                raise AssertionError("expected SSH compose failure")
        finally:
            mod.subprocess.run = original_run
    cleanup_calls = [call for call in calls if "rm -rf --" in " ".join(call)]
    expect(cleanup_calls, f"expected remote secret cleanup call, saw {calls}")
    expect(any("config/secrets" in " ".join(call) for call in cleanup_calls), str(cleanup_calls))
    print("PASS test_ssh_docker_runner_cleans_remote_secrets_after_compose_failure")


def test_ssh_docker_runner_requires_explicit_host_allowlist() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_ssh_allowlist_test")
    runner = mod.SshDockerComposeRunner(host="worker.example.test")
    try:
        runner.run(
            ("ps", "--format", "json"),
            project_name="arclink-dep",
            env_file="/tmp/arclink.env",
            compose_file="/tmp/dep/config/compose.yaml",
        )
    except mod.ArcLinkExecutorError as exc:
        expect("allowlist" in str(exc), str(exc))
    else:
        raise AssertionError("expected missing SSH host allowlist to fail")
    print("PASS test_ssh_docker_runner_requires_explicit_host_allowlist")


def test_fleet_host_executor_helper_builds_ssh_runner_from_host_metadata() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_fleet_host_helper")
    executor = mod.executor_for_fleet_host(
        adapter="ssh",
        env={"ARCLINK_EXECUTOR_MACHINE_MODE_ENABLED": "1", "ARCLINK_EXECUTOR_MACHINE_HOST_ALLOWLIST": "10.0.0.42"},
        host={"host_id": "host_b", "hostname": "worker-b.example.test", "metadata_json": json.dumps({"ssh_host": "10.0.0.42", "ssh_user": "worker"})},
        secret_resolver=mod.FakeSecretResolver({}),
    )
    runner = executor.docker_runner
    expect(executor.config.adapter_name == "ssh", str(executor.config))
    expect(runner.host == "10.0.0.42", str(runner))
    expect(runner.user == "worker", str(runner))
    expect(runner.allowed_hosts == ("10.0.0.42",), str(runner))
    print("PASS test_fleet_host_executor_helper_builds_ssh_runner_from_host_metadata")


def test_live_executor_requires_docker_runner() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_runner_required_test")
    intent = sample_intent()
    secret_ref = intent["compose"]["secrets"]["nextcloud_db_password"]["secret_ref"]
    executor = mod.ArcLinkExecutor(
        config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="live"),
        secret_resolver=mod.FakeSecretResolver({secret_ref: "sk_test_secret"}),
        # No docker_runner provided
    )
    try:
        executor.docker_compose_apply(
            mod.DockerComposeApplyRequest(deployment_id="dep_1", intent=intent)
        )
    except mod.ArcLinkExecutorError as exc:
        expect("DockerRunner" in str(exc), str(exc))
    else:
        raise AssertionError("expected live execution without runner to fail")
    print("PASS test_live_executor_requires_docker_runner")


def test_fake_docker_compose_lifecycle_operations() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_lifecycle_test")
    executor = mod.ArcLinkExecutor(config=mod.ArcLinkExecutorConfig(adapter_name="fake", live_enabled=True))

    for action in ("stop", "restart", "inspect", "teardown"):
        result = executor.docker_compose_lifecycle(
            mod.DockerComposeLifecycleRequest(
                deployment_id="dep_lifecycle",
                action=action,
                idempotency_key=f"lc-{action}-1",
            )
        )
        expect(result.status == "completed", f"{action} expected completed got {result.status}")
        expect(result.action == action, f"expected {action} got {result.action}")
        expect(result.live is False, f"expected fake (live=False) for {action}")

    replay = executor.docker_compose_lifecycle(
        mod.DockerComposeLifecycleRequest(
            deployment_id="dep_lifecycle",
            action="teardown",
            idempotency_key="lc-teardown-1",
        )
    )
    expect(replay.metadata["idempotent_replay"] is True, str(replay))

    # Invalid action rejected
    try:
        executor.docker_compose_lifecycle(
            mod.DockerComposeLifecycleRequest(deployment_id="dep_lifecycle", action="explode")
        )
    except mod.ArcLinkExecutorError as exc:
        expect("unsupported" in str(exc), str(exc))
    else:
        raise AssertionError("expected unsupported lifecycle action to fail")

    # Lifecycle requires live_enabled
    no_live = mod.ArcLinkExecutor(config=mod.ArcLinkExecutorConfig(adapter_name="fake", live_enabled=False))
    try:
        no_live.docker_compose_lifecycle(
            mod.DockerComposeLifecycleRequest(deployment_id="dep_lifecycle", action="stop")
        )
    except mod.ArcLinkLiveExecutionRequired:
        pass
    else:
        raise AssertionError("expected live execution required error")

    print("PASS test_fake_docker_compose_lifecycle_operations")


def test_live_docker_compose_lifecycle_invokes_runner() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_live_lifecycle_test")
    runner = mod.FakeDockerRunner()
    executor = mod.ArcLinkExecutor(
        config=mod.ArcLinkExecutorConfig(adapter_name="live", live_enabled=True),
        docker_runner=runner,
    )
    result = executor.docker_compose_lifecycle(
        mod.DockerComposeLifecycleRequest(deployment_id="dep_live", action="teardown", remove_volumes=True)
    )
    expect(result.live is True and result.status == "completed", str(result))
    expect(len(runner.runs) == 1, str(runner.runs))
    expect(runner.runs[0]["args"] == ("down", "--remove-orphans", "--volumes"), str(runner.runs[0]))
    expect(runner.runs[0]["project_name"] == "arclink-dep_live", str(runner.runs[0]))
    expect(runner.runs[0]["compose_file"].endswith("/arcdata/deployments/dep_live/config/compose.yaml"), str(runner.runs[0]))
    print("PASS test_live_docker_compose_lifecycle_invokes_runner")


def test_live_docker_compose_lifecycle_transport_failure_is_not_downgraded() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_live_lifecycle_failure_test")

    class FailingRunner:
        def run(self, args, *, project_name: str, env_file: str, compose_file: str):
            raise mod.ArcLinkExecutorError("transport failed")

    executor = mod.ArcLinkExecutor(
        config=mod.ArcLinkExecutorConfig(adapter_name="live", live_enabled=True),
        docker_runner=FailingRunner(),
    )
    try:
        executor.docker_compose_lifecycle(
            mod.DockerComposeLifecycleRequest(deployment_id="dep_live", action="teardown")
        )
    except mod.ArcLinkExecutorError as exc:
        expect("transport failed" in str(exc), str(exc))
    else:
        raise AssertionError("expected lifecycle transport failure to propagate")
    print("PASS test_live_docker_compose_lifecycle_transport_failure_is_not_downgraded")


def main() -> int:
    test_executor_mutating_operations_fail_closed_without_live_flag()
    test_runner_stdout_preserves_compose_ps_json()
    test_secret_resolvers_validate_refs_and_hide_material()
    test_fake_executor_consumes_rendered_intent_without_secret_leakage()
    test_fake_docker_compose_adapter_plans_paths_and_resumes_partial_apply()
    test_fake_docker_compose_rejects_explicit_key_reuse_after_applied_intent_changes()
    test_fake_docker_compose_replays_applied_state_without_rematerializing_secrets()
    test_fake_docker_compose_rejects_explicit_key_reuse_after_partial_failed_intent_changes()
    test_fake_docker_compose_rejects_zero_failure_limit()
    test_fake_provider_and_edge_adapters_are_idempotent_and_secret_ref_only()
    test_fake_dns_rejects_idempotency_key_reuse_with_changed_records()
    test_fake_access_rejects_idempotency_key_reuse_with_changed_plan()
    test_fake_chutes_replay_is_bound_to_action_and_secret_ref()
    test_live_chutes_client_receives_idempotency_key_and_replays_result()
    test_live_chutes_client_missing_fails_closed()
    test_live_stripe_client_receives_idempotency_key_and_replays_result()
    test_live_stripe_client_missing_fails_closed()
    test_cloudflare_dns_apply_rejects_unsupported_record_types()
    test_live_cloudflare_dns_apply_accepts_secret_ref_token_and_cleans_copy()
    test_fake_rollback_executor_is_idempotent_and_preserves_state_roots()
    test_fake_rollback_rejects_idempotency_key_reuse_with_changed_plan()
    test_fake_docker_compose_rejects_missing_depends_on_service()
    test_dry_run_output_is_secret_free()
    test_injectable_docker_runner_receives_commands()
    test_live_docker_compose_file_preserves_service_ports()
    test_live_docker_compose_apply_keeps_file_backed_secrets_for_container_restart()
    test_live_docker_compose_apply_cleans_materialized_secret_copies_on_runner_failure()
    test_ssh_docker_runner_cleans_remote_secrets_after_compose_failure()
    test_ssh_docker_runner_requires_explicit_host_allowlist()
    test_fleet_host_executor_helper_builds_ssh_runner_from_host_metadata()
    test_live_executor_requires_docker_runner()
    test_fake_docker_compose_lifecycle_operations()
    test_live_docker_compose_lifecycle_invokes_runner()
    test_live_docker_compose_lifecycle_transport_failure_is_not_downgraded()
    print("PASS all 34 ArcLink executor tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
