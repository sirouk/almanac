#!/usr/bin/env python3
"""ArcLink Sovereign control-node provisioner.

This worker is the connective tissue between hosted onboarding/billing and the
per-user Sovereign pod runtime. It intentionally operates on existing ArcLink
contracts: deployments, fleet hosts, provisioning jobs, DNS records, service
health, audit, and events.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import socket
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from arclink_boundary import json_dumps_safe, json_loads_safe, reject_secret_material
from arclink_control import (
    Config,
    append_arclink_audit,
    append_arclink_event,
    connect_db,
    create_arclink_provisioning_job,
    parse_utc_iso,
    queue_notification,
    transition_arclink_provisioning_job,
    upsert_arclink_service_health,
    utc_now,
    utc_now_iso,
)
from arclink_executor import (
    ArcLinkExecutor,
    ArcLinkExecutorConfig,
    ArcLinkSecretResolutionError,
    CloudflareDnsApplyRequest,
    CloudflareDnsApplyResult,
    DockerComposeApplyRequest,
    DockerComposeApplyResult,
    FakeSecretResolver,
    FileMaterializingSecretResolver,
    ResolvedSecretFile,
    SshDockerComposeRunner,
    SubprocessDockerComposeRunner,
)
from arclink_fleet import ArcLinkFleetError, place_deployment, reconcile_fleet_observed_loads, register_fleet_host
from arclink_ingress import persist_arclink_dns_records
from arclink_provisioning import (
    ARCLINK_PROVISIONING_SERVICE_NAMES,
    render_arclink_provisioning_intent,
)
from arclink_adapters import DnsRecord
from arclink_onboarding import record_arclink_onboarding_first_agent_contact
from arclink_api_auth import set_arclink_user_password


class ArcLinkSovereignWorkerError(RuntimeError):
    pass


SOLO_JOB_KIND = "sovereign_pod_apply"
TERMINAL_JOB_STATUSES = {"succeeded", "cancelled"}


@dataclass(frozen=True)
class SovereignWorkerConfig:
    enabled: bool
    ingress_mode: str
    base_domain: str
    edge_target: str
    tailscale_dns_name: str
    tailscale_host_strategy: str
    tailscale_https_port: str
    tailscale_notion_path: str
    state_root_base: str
    cloudflare_zone_id: str
    executor_adapter: str
    batch_size: int
    max_attempts: int
    running_stale_seconds: int
    register_local_host: bool
    local_hostname: str
    local_ssh_host: str
    local_ssh_user: str
    local_region: str
    local_capacity_slots: int
    secret_store_dir: Path
    env: Mapping[str, str]


class SovereignSecretResolver(FileMaterializingSecretResolver):
    """Resolve secret:// references from env or an operator-local secret store."""

    def __init__(self, *, env: Mapping[str, str], secret_store_dir: Path, materialization_root: Path) -> None:
        self.env = env
        self.secret_store_dir = secret_store_dir
        super().__init__(value_provider=self._value_for_ref, materialization_root=materialization_root)

    def materialize(self, secret_ref: str, target_path: str) -> ResolvedSecretFile:
        resolved = super().materialize(secret_ref, target_path)
        return resolved

    def _value_for_ref(self, secret_ref: str) -> str:
        provider_env = _provider_env_for_ref(secret_ref)
        if provider_env:
            value = str(self.env.get(provider_env) or "").strip()
            if not value:
                raise ArcLinkSecretResolutionError(f"missing ArcLink secret material for {secret_ref}: set {provider_env}")
            return value
        return self._generated_secret_value(secret_ref)

    def _generated_secret_value(self, secret_ref: str) -> str:
        self.secret_store_dir.mkdir(parents=True, exist_ok=True)
        path = self.secret_store_dir / f"{hashlib.sha256(secret_ref.encode('utf-8')).hexdigest()}.secret"
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        value = f"arc_{secrets.token_urlsafe(36)}"
        path.write_text(value + "\n", encoding="utf-8")
        path.chmod(0o600)
        return value


def _provider_env_for_ref(secret_ref: str) -> str:
    if secret_ref.startswith("secret://arclink/chutes/"):
        return "CHUTES_API_KEY"
    if secret_ref.startswith("secret://arclink/telegram/"):
        return "TELEGRAM_BOT_TOKEN"
    if secret_ref.startswith("secret://arclink/discord/"):
        return "DISCORD_BOT_TOKEN"
    if secret_ref.startswith("secret://arclink/notion/"):
        if secret_ref.rstrip("/").endswith("/webhook-secret"):
            return ""
        return "NOTION_TOKEN"
    if secret_ref.startswith("secret://arclink/stripe/"):
        return "STRIPE_SECRET_KEY"
    if secret_ref.startswith("secret://arclink/cloudflare/"):
        return "CLOUDFLARE_API_TOKEN"
    return ""


def load_worker_config(cfg: Config, env: Mapping[str, str] | None = None) -> SovereignWorkerConfig:
    source = dict(env or os.environ)
    ingress_mode = str(source.get("ARCLINK_INGRESS_MODE") or "domain").strip().lower()
    if ingress_mode not in {"domain", "tailscale"}:
        ingress_mode = "domain"
    tailscale_dns_name = str(source.get("ARCLINK_TAILSCALE_DNS_NAME") or "").strip().lower().strip(".")
    base_domain = str(source.get("ARCLINK_BASE_DOMAIN") or tailscale_dns_name or "arclink.online").strip().lower().strip(".")
    if ingress_mode == "tailscale" and tailscale_dns_name:
        base_domain = tailscale_dns_name
    edge_target = str(source.get("ARCLINK_EDGE_TARGET") or (tailscale_dns_name if ingress_mode == "tailscale" else f"edge.{base_domain}")).strip().lower()
    local_hostname = str(source.get("ARCLINK_LOCAL_FLEET_HOSTNAME") or socket.getfqdn() or socket.gethostname()).strip().lower()
    return SovereignWorkerConfig(
        enabled=_truthy(source.get("ARCLINK_CONTROL_PROVISIONER_ENABLED", "1")),
        ingress_mode=ingress_mode,
        base_domain=base_domain,
        edge_target=edge_target,
        tailscale_dns_name=tailscale_dns_name,
        tailscale_host_strategy=str(source.get("ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY") or "path").strip().lower(),
        tailscale_https_port=str(source.get("ARCLINK_TAILSCALE_HTTPS_PORT") or "443").strip(),
        tailscale_notion_path=str(source.get("ARCLINK_TAILSCALE_NOTION_PATH") or source.get("TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH") or "/notion/webhook").strip(),
        state_root_base=str(source.get("ARCLINK_STATE_ROOT_BASE") or "/arcdata/deployments").strip(),
        cloudflare_zone_id=str(source.get("CLOUDFLARE_ZONE_ID") or "").strip(),
        executor_adapter=str(source.get("ARCLINK_EXECUTOR_ADAPTER") or "disabled").strip().lower(),
        batch_size=max(1, int(source.get("ARCLINK_CONTROL_PROVISIONER_BATCH_SIZE", "5"))),
        max_attempts=max(1, int(source.get("ARCLINK_SOVEREIGN_PROVISION_MAX_ATTEMPTS", "5"))),
        running_stale_seconds=max(60, int(source.get("ARCLINK_SOVEREIGN_RUNNING_STALE_SECONDS", "900"))),
        register_local_host=_truthy(source.get("ARCLINK_REGISTER_LOCAL_FLEET_HOST", "0")),
        local_hostname=local_hostname,
        local_ssh_host=str(source.get("ARCLINK_LOCAL_FLEET_SSH_HOST") or "").strip().lower(),
        local_ssh_user=str(source.get("ARCLINK_LOCAL_FLEET_SSH_USER") or "arclink").strip(),
        local_region=str(source.get("ARCLINK_LOCAL_FLEET_REGION") or "").strip().lower(),
        local_capacity_slots=max(1, int(source.get("ARCLINK_LOCAL_FLEET_CAPACITY_SLOTS", "4"))),
        secret_store_dir=Path(source.get("ARCLINK_SECRET_STORE_DIR") or cfg.state_dir / "sovereign-secrets").resolve(),
        env=source,
    )


def process_sovereign_batch(
    conn: sqlite3.Connection,
    *,
    worker: SovereignWorkerConfig,
    executor: ArcLinkExecutor | None = None,
) -> list[dict[str, Any]]:
    if not worker.enabled:
        return [{"status": "disabled", "reason": "ARCLINK_CONTROL_PROVISIONER_ENABLED is not set"}]
    if worker.register_local_host:
        local_metadata: dict[str, Any] = {
            "executor": worker.executor_adapter,
            "ingress_mode": worker.ingress_mode,
            "edge_target": worker.edge_target,
            "state_root_base": worker.state_root_base,
        }
        if worker.local_ssh_host:
            local_metadata["ssh_host"] = worker.local_ssh_host
        if worker.local_ssh_user:
            local_metadata["ssh_user"] = worker.local_ssh_user
        register_fleet_host(
            conn,
            hostname=worker.local_hostname,
            region=worker.local_region,
            capacity_slots=worker.local_capacity_slots,
            metadata=local_metadata,
        )
    reconcile_fleet_observed_loads(conn)
    recover_stale_sovereign_jobs(conn, stale_seconds=worker.running_stale_seconds)
    recover_succeeded_sovereign_handoffs(conn, worker=worker)
    rows = conn.execute(
        """
        SELECT d.*
        FROM arclink_deployments d
        LEFT JOIN arclink_provisioning_jobs j
          ON j.deployment_id = d.deployment_id
         AND j.job_kind = ?
        WHERE d.status = 'provisioning_ready'
           OR (
             d.status = 'provisioning_failed'
             AND j.status = 'failed'
             AND COALESCE(j.attempt_count, 0) < ?
           )
        ORDER BY d.updated_at ASC, d.deployment_id ASC
        LIMIT ?
        """,
        (SOLO_JOB_KIND, worker.max_attempts, worker.batch_size),
    ).fetchall()
    results = []
    for row in rows:
        results.append(process_sovereign_deployment(conn, deployment=dict(row), worker=worker, executor=executor))
    return results


def recover_stale_sovereign_jobs(conn: sqlite3.Connection, *, stale_seconds: int = 900) -> list[dict[str, Any]]:
    threshold = max(60, int(stale_seconds))
    cutoff = utc_now().timestamp() - threshold
    rows = conn.execute(
        """
        SELECT j.job_id, j.deployment_id, j.started_at
        FROM arclink_provisioning_jobs j
        JOIN arclink_deployments d ON d.deployment_id = j.deployment_id
        WHERE j.job_kind = ?
          AND j.status = 'running'
          AND d.status = 'provisioning'
        """,
        (SOLO_JOB_KIND,),
    ).fetchall()
    recovered: list[dict[str, Any]] = []
    for row in rows:
        started = parse_utc_iso(str(row["started_at"] or ""))
        if started is None or started.timestamp() > cutoff:
            continue
        error = f"stale Sovereign provisioning job recovered after {threshold} seconds"
        transition_arclink_provisioning_job(conn, job_id=str(row["job_id"]), status="failed", error=error)
        _mark_deployment_status(conn, deployment_id=str(row["deployment_id"]), status="provisioning_failed")
        append_arclink_event(
            conn,
            subject_kind="deployment",
            subject_id=str(row["deployment_id"]),
            event_type="sovereign_provisioning_recovered_stale_running_job",
            metadata={"job_id": str(row["job_id"]), "error": error},
        )
        recovered.append({"job_id": str(row["job_id"]), "deployment_id": str(row["deployment_id"]), "status": "failed"})
    return recovered


def recover_succeeded_sovereign_handoffs(
    conn: sqlite3.Connection,
    *,
    worker: SovereignWorkerConfig,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT d.*, j.job_id
        FROM arclink_deployments d
        JOIN arclink_provisioning_jobs j
          ON j.deployment_id = d.deployment_id
         AND j.job_kind = ?
         AND j.status = 'succeeded'
        WHERE d.status IN ('provisioning', 'active')
          AND NOT EXISTS (
            SELECT 1
            FROM arclink_events e
            WHERE e.subject_kind = 'deployment'
              AND e.subject_id = d.deployment_id
              AND e.event_type = 'user_handoff_ready'
          )
        ORDER BY d.updated_at ASC, d.deployment_id ASC
        """,
        (SOLO_JOB_KIND,),
    ).fetchall()
    recovered: list[dict[str, Any]] = []
    for row in rows:
        deployment = dict(row)
        deployment_id = str(deployment["deployment_id"])
        job_id = str(deployment["job_id"])
        if str(deployment.get("status") or "") != "active":
            _mark_deployment_status(conn, deployment_id=deployment_id, status="active")
        urls = _access_urls_for_deployment(conn, deployment=deployment, worker=worker)
        _queue_vessel_online_notifications(conn, deployment_id=deployment_id, urls=urls)
        append_arclink_event(
            conn,
            subject_kind="deployment",
            subject_id=deployment_id,
            event_type="user_handoff_ready",
            metadata={"job_id": job_id, "urls": urls, "recovered": True},
        )
        recovered.append({"deployment_id": deployment_id, "job_id": job_id, "status": "handoff_recovered"})
    return recovered


def process_sovereign_deployment(
    conn: sqlite3.Connection,
    *,
    deployment: Mapping[str, Any],
    worker: SovereignWorkerConfig,
    executor: ArcLinkExecutor | None = None,
) -> dict[str, Any]:
    deployment_id = str(deployment["deployment_id"])
    job = _ensure_apply_job(conn, deployment_id=deployment_id)
    if str(job["status"]) in TERMINAL_JOB_STATUSES:
        _mark_deployment_status(conn, deployment_id=deployment_id, status="active")
        return {"deployment_id": deployment_id, "job_id": str(job["job_id"]), "status": "already_applied"}
    if str(job["status"]) == "running":
        return {"deployment_id": deployment_id, "job_id": str(job["job_id"]), "status": "already_running"}
    if str(job["status"]) == "failed":
        if int(job["attempt_count"] or 0) >= worker.max_attempts:
            return {"deployment_id": deployment_id, "job_id": str(job["job_id"]), "status": "max_attempts_exhausted"}
        transition_arclink_provisioning_job(conn, job_id=str(job["job_id"]), status="queued")

    transition_arclink_provisioning_job(conn, job_id=str(job["job_id"]), status="running")
    _mark_deployment_status(conn, deployment_id=deployment_id, status="provisioning")
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=deployment_id,
        event_type="sovereign_provisioning_started",
        metadata={"job_id": str(job["job_id"])},
    )
    try:
        deployment = _ensure_tailnet_service_ports(conn, deployment=deployment, worker=worker)
        result = _apply_deployment(conn, deployment=deployment, job=job, worker=worker, executor=executor)
        transition_arclink_provisioning_job(conn, job_id=str(job["job_id"]), status="succeeded")
        _mark_deployment_status(conn, deployment_id=deployment_id, status="active")
        _queue_vessel_online_notifications(
            conn,
            deployment_id=deployment_id,
            urls=result.get("urls", {}),
        )
        append_arclink_event(
            conn,
            subject_kind="deployment",
            subject_id=deployment_id,
            event_type="user_handoff_ready",
            metadata={"job_id": str(job["job_id"]), "urls": result.get("urls", {})},
        )
        append_arclink_audit(
            conn,
            action="sovereign_pod_apply",
            actor_id="system:sovereign_worker",
            target_kind="deployment",
            target_id=deployment_id,
            reason="billing-approved deployment applied to fleet",
            metadata={"job_id": str(job["job_id"]), "placement": result.get("placement", {})},
        )
        return {"deployment_id": deployment_id, "job_id": str(job["job_id"]), "status": "applied", **result}
    except Exception as exc:
        error = _safe_error(exc)
        transition_arclink_provisioning_job(conn, job_id=str(job["job_id"]), status="failed", error=error)
        _mark_deployment_status(conn, deployment_id=deployment_id, status="provisioning_failed")
        _record_service_status(conn, deployment_id=deployment_id, status="failed", detail={"error": error})
        append_arclink_event(
            conn,
            subject_kind="deployment",
            subject_id=deployment_id,
            event_type="sovereign_provisioning_failed",
            metadata={"job_id": str(job["job_id"]), "error": error},
        )
        return {"deployment_id": deployment_id, "job_id": str(job["job_id"]), "status": "failed", "error": error}


def _tailnet_port(value: Any) -> int:
    try:
        port = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return port if 0 < port < 65536 else 0


def _tailnet_ports_from_metadata(metadata: Mapping[str, Any]) -> dict[str, int]:
    raw = metadata.get("tailnet_service_ports")
    if not isinstance(raw, Mapping):
        return {}
    roles = ("hermes",)
    return {role: port for role in roles if (port := _tailnet_port(raw.get(role)))}


def _ensure_tailnet_service_ports(
    conn: sqlite3.Connection,
    *,
    deployment: Mapping[str, Any],
    worker: SovereignWorkerConfig,
) -> dict[str, Any]:
    if worker.ingress_mode != "tailscale" or worker.tailscale_host_strategy != "path":
        return dict(deployment)
    roles = ("hermes",)
    deployment_id = str(deployment["deployment_id"])
    metadata = json_loads_safe(str(deployment.get("metadata_json") or "{}"))
    ports = _tailnet_ports_from_metadata(metadata)
    if set(roles) <= set(ports):
        return dict(deployment)

    used: set[int] = set()
    for row in conn.execute("SELECT deployment_id, metadata_json FROM arclink_deployments").fetchall():
        if str(row["deployment_id"]) == deployment_id:
            continue
        used.update(_tailnet_ports_from_metadata(json_loads_safe(str(row["metadata_json"] or "{}"))).values())

    try:
        next_block = int(str(worker.env.get("ARCLINK_TAILNET_SERVICE_PORT_BASE") or "8443"))
    except ValueError:
        next_block = 8443
    if next_block < 1 or next_block + len(roles) >= 65536:
        next_block = 8443
    while True:
        candidate = {role: next_block + offset for offset, role in enumerate(roles)}
        if all(0 < port < 65536 and port not in used for port in candidate.values()):
            ports = candidate
            break
        next_block += len(roles)

    metadata.update(
        {
            "ingress_mode": "tailscale",
            "tailscale_dns_name": worker.tailscale_dns_name or worker.base_domain,
            "tailscale_host_strategy": "path",
            "tailnet_service_ports": ports,
            "tailnet_service_ports_checked_at": utc_now_iso(),
        }
    )
    conn.execute(
        "UPDATE arclink_deployments SET metadata_json = ? WHERE deployment_id = ?",
        (json.dumps(metadata, sort_keys=True), deployment_id),
    )
    conn.commit()
    updated = dict(deployment)
    updated["metadata_json"] = json.dumps(metadata, sort_keys=True)
    return updated


def _apply_deployment(
    conn: sqlite3.Connection,
    *,
    deployment: Mapping[str, Any],
    job: Mapping[str, Any],
    worker: SovereignWorkerConfig,
    executor: ArcLinkExecutor | None,
) -> dict[str, Any]:
    deployment_id = str(deployment["deployment_id"])
    metadata = json_loads_safe(str(deployment.get("metadata_json") or "{}"))
    placement = place_deployment(
        conn,
        deployment_id=deployment_id,
        region=str(metadata.get("region") or ""),
        required_tags=metadata.get("required_tags") if isinstance(metadata.get("required_tags"), Mapping) else None,
    )
    host = _host_for_placement(conn, placement)
    host_meta = json_loads_safe(str(host.get("metadata_json") or "{}"))
    edge_target = str(host_meta.get("edge_target") or worker.edge_target)
    state_root_base = str(host_meta.get("state_root_base") or worker.state_root_base)
    intent = render_arclink_provisioning_intent(
        conn,
        deployment_id=deployment_id,
        base_domain=worker.base_domain,
        edge_target=edge_target,
        state_root_base=state_root_base,
        ingress_mode=worker.ingress_mode,
        tailscale_dns_name=worker.tailscale_dns_name,
        tailscale_host_strategy=worker.tailscale_host_strategy,
        tailscale_notion_path=worker.tailscale_notion_path,
        env=worker.env,
    )
    _persist_dns_from_intent(conn, deployment_id=deployment_id, dns=intent["dns"])
    selected_executor = executor or _executor_for_host(worker=worker, host=host, intent=intent)
    if worker.ingress_mode == "domain" and intent["dns"]:
        dns_result = selected_executor.cloudflare_dns_apply(
            CloudflareDnsApplyRequest(
                deployment_id=deployment_id,
                dns=intent["dns"],
                zone_id=worker.cloudflare_zone_id,
                idempotency_key=f"arclink:sovereign:dns:{deployment_id}",
            )
        )
        _mark_dns_provisioned(conn, deployment_id=deployment_id)
    else:
        dns_result = CloudflareDnsApplyResult(
            deployment_id=deployment_id,
            live=selected_executor.config.live_enabled,
            status="skipped",
            records=(),
            metadata={
                "adapter": selected_executor.config.adapter_name,
                "ingress_mode": worker.ingress_mode,
                "reason": "cloudflare_dns_not_used_for_tailscale_ingress",
            },
        )
    docker_result = selected_executor.docker_compose_apply(
        DockerComposeApplyRequest(
            deployment_id=deployment_id,
            intent=intent,
            idempotency_key=f"arclink:sovereign:compose:{deployment_id}",
        )
    )
    _sync_dashboard_password_hash_from_secret(conn, deployment=deployment, worker=worker, intent=intent)
    _record_service_status_after_compose(
        conn,
        deployment_id=deployment_id,
        job_id=str(job["job_id"]),
        executor=selected_executor,
        docker_result=docker_result,
    )
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=deployment_id,
        event_type="sovereign_pod_applied",
        metadata={
            "job_id": str(job["job_id"]),
            "host_id": str(placement["host_id"]),
            "docker_status": docker_result.status,
            "dns_status": dns_result.status,
            "ingress_mode": worker.ingress_mode,
            "service_count": len(docker_result.services),
        },
    )
    return {
        "placement": {"host_id": str(placement["host_id"]), "hostname": str(host["hostname"])},
        "services": list(docker_result.services),
        "dns_records": list(dns_result.records),
        "urls": dict(intent["access"]["urls"]),
    }


def _executor_for_host(
    *,
    worker: SovereignWorkerConfig,
    host: Mapping[str, Any],
    intent: Mapping[str, Any],
) -> ArcLinkExecutor:
    adapter = worker.executor_adapter
    config = ArcLinkExecutorConfig(live_enabled=True, adapter_name=adapter)
    if adapter == "fake":
        refs = _secret_refs(intent)
        return ArcLinkExecutor(config=config, secret_resolver=FakeSecretResolver({ref: "fake-secret-material" for ref in refs}))
    roots = intent.get("state_roots") if isinstance(intent.get("state_roots"), Mapping) else {}
    materialization_root = Path(str(roots.get("config") or "/tmp/arclink-secrets")) / "secrets"
    resolver = SovereignSecretResolver(
        env=worker.env,
        secret_store_dir=worker.secret_store_dir / str(intent["deployment"]["deployment_id"]),
        materialization_root=materialization_root,
    )
    host_meta = json_loads_safe(str(host.get("metadata_json") or "{}"))
    if adapter == "local":
        runner = SubprocessDockerComposeRunner(docker_binary=str(worker.env.get("ARCLINK_DOCKER_BINARY") or "docker"))
    elif adapter == "ssh":
        ssh_options = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
        key_path = str(worker.env.get("ARCLINK_FLEET_SSH_KEY_PATH") or "").strip()
        known_hosts = str(worker.env.get("ARCLINK_FLEET_SSH_KNOWN_HOSTS_FILE") or "").strip()
        if key_path:
            ssh_options.extend(("-i", key_path))
        if known_hosts:
            ssh_options.extend(("-o", f"UserKnownHostsFile={known_hosts}"))
        runner = SshDockerComposeRunner(
            host=str(host_meta.get("ssh_host") or host["hostname"]),
            user=str(host_meta.get("ssh_user") or "arclink"),
            ssh_binary=str(worker.env.get("ARCLINK_SSH_BINARY") or "ssh"),
            rsync_binary=str(worker.env.get("ARCLINK_RSYNC_BINARY") or "rsync"),
            docker_binary=str(worker.env.get("ARCLINK_DOCKER_BINARY") or "docker"),
            ssh_options=tuple(ssh_options),
        )
    else:
        raise ArcLinkSovereignWorkerError(
            "set ARCLINK_EXECUTOR_ADAPTER to fake, local, or ssh before enabling the Sovereign provisioner"
        )
    return ArcLinkExecutor(config=config, secret_resolver=resolver, docker_runner=runner)


def _access_urls_for_deployment(
    conn: sqlite3.Connection,
    *,
    deployment: Mapping[str, Any],
    worker: SovereignWorkerConfig,
) -> dict[str, str]:
    host_meta: dict[str, Any] = {}
    placement = conn.execute(
        """
        SELECT h.metadata_json
        FROM arclink_deployment_placements p
        JOIN arclink_fleet_hosts h ON h.host_id = p.host_id
        WHERE p.deployment_id = ?
          AND p.status = 'active'
        ORDER BY p.placed_at DESC
        LIMIT 1
        """,
        (str(deployment["deployment_id"]),),
    ).fetchone()
    if placement is not None:
        host_meta = json_loads_safe(str(placement["metadata_json"] or "{}"))
    intent = render_arclink_provisioning_intent(
        conn,
        deployment_id=str(deployment["deployment_id"]),
        base_domain=worker.base_domain,
        edge_target=str(host_meta.get("edge_target") or worker.edge_target),
        state_root_base=str(host_meta.get("state_root_base") or worker.state_root_base),
        ingress_mode=worker.ingress_mode,
        tailscale_dns_name=worker.tailscale_dns_name,
        tailscale_host_strategy=worker.tailscale_host_strategy,
        tailscale_notion_path=worker.tailscale_notion_path,
        env=worker.env,
    )
    access = intent.get("access") if isinstance(intent.get("access"), Mapping) else {}
    urls = access.get("urls") if isinstance(access.get("urls"), Mapping) else {}
    return {str(k): str(v) for k, v in urls.items()}


def _secret_refs(intent: Mapping[str, Any]) -> list[str]:
    refs = []
    compose = intent.get("compose") if isinstance(intent.get("compose"), Mapping) else {}
    for spec in (compose.get("secrets") or {}).values():
        if isinstance(spec, Mapping) and spec.get("secret_ref"):
            refs.append(str(spec["secret_ref"]))
    return refs


def _sync_dashboard_password_hash_from_secret(
    conn: sqlite3.Connection,
    *,
    deployment: Mapping[str, Any],
    worker: SovereignWorkerConfig,
    intent: Mapping[str, Any],
) -> None:
    secret_refs = intent.get("secret_refs") if isinstance(intent.get("secret_refs"), Mapping) else {}
    secret_ref = str(secret_refs.get("dashboard_password") or "").strip()
    user_id = str(deployment.get("user_id") or "").strip()
    deployment_id = str(deployment.get("deployment_id") or "").strip()
    if not secret_ref or not user_id or not deployment_id:
        return
    resolver = SovereignSecretResolver(
        env=worker.env,
        secret_store_dir=worker.secret_store_dir / deployment_id,
        materialization_root=Path("/tmp/arclink-dashboard-password-sync"),
    )
    password = resolver._value_for_ref(secret_ref)
    set_arclink_user_password(conn, user_id=user_id, password=password)


def _ensure_apply_job(conn: sqlite3.Connection, *, deployment_id: str) -> dict[str, Any]:
    key = f"arclink:sovereign:apply:{deployment_id}"
    row = conn.execute("SELECT * FROM arclink_provisioning_jobs WHERE idempotency_key = ?", (key,)).fetchone()
    if row is None:
        create_arclink_provisioning_job(
            conn,
            job_id=f"job_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]}",
            deployment_id=deployment_id,
            job_kind=SOLO_JOB_KIND,
            idempotency_key=key,
            metadata={"deployment_id": deployment_id, "worker": "sovereign"},
        )
        row = conn.execute("SELECT * FROM arclink_provisioning_jobs WHERE idempotency_key = ?", (key,)).fetchone()
    return dict(row)


def _host_for_placement(conn: sqlite3.Connection, placement: Mapping[str, Any]) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM arclink_fleet_hosts WHERE host_id = ?", (str(placement["host_id"]),)).fetchone()
    if row is None:
        raise ArcLinkFleetError(f"placement host disappeared: {placement['host_id']}")
    return dict(row)


def _persist_dns_from_intent(conn: sqlite3.Connection, *, deployment_id: str, dns: Mapping[str, Any]) -> None:
    records = {
        role: DnsRecord(
            hostname=str(record["hostname"]),
            record_type=str(record["record_type"]),
            target=str(record["target"]),
            proxied=bool(record.get("proxied", True)),
        )
        for role, record in dns.items()
        if isinstance(record, Mapping)
    }
    persist_arclink_dns_records(conn, deployment_id=deployment_id, records=records)


def _mark_dns_provisioned(conn: sqlite3.Connection, *, deployment_id: str) -> None:
    now = utc_now_iso()
    conn.execute(
        "UPDATE arclink_dns_records SET status = 'provisioned', updated_at = ?, last_checked_at = ? WHERE deployment_id = ?",
        (now, now, deployment_id),
    )
    conn.commit()


def _record_service_status(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    status: str,
    detail: Mapping[str, Any],
) -> None:
    for service_name in ARCLINK_PROVISIONING_SERVICE_NAMES:
        upsert_arclink_service_health(conn, deployment_id=deployment_id, service_name=service_name, status=status, detail=detail)


def _record_service_status_after_compose(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    job_id: str,
    executor: ArcLinkExecutor,
    docker_result: DockerComposeApplyResult,
) -> None:
    detail_base = {"job_id": job_id, "executor": executor.config.adapter_name}
    if executor.config.adapter_name == "fake":
        _record_service_status(conn, deployment_id=deployment_id, status="healthy", detail=detail_base)
        return
    if executor.docker_runner is None:
        _record_service_status(
            conn,
            deployment_id=deployment_id,
            status="starting",
            detail={**detail_base, "reconcile_error": "docker_runner_not_available"},
        )
        return
    try:
        ps_result = executor.docker_runner.run(
            ("ps", "--all", "--format", "json"),
            project_name=docker_result.project_name,
            env_file=docker_result.env_file,
            compose_file=docker_result.compose_file,
        )
        rows = _parse_docker_compose_ps_json(str(ps_result.get("stdout") or ""))
        statuses = _docker_compose_service_statuses(rows)
    except Exception as exc:  # noqa: BLE001 - service health reconciliation must not undo a successful apply
        _record_service_status(
            conn,
            deployment_id=deployment_id,
            status="starting",
            detail={**detail_base, "reconcile_error": _safe_error(exc)},
        )
        return

    for service_name in ARCLINK_PROVISIONING_SERVICE_NAMES:
        service = statuses.get(service_name)
        if service is None:
            upsert_arclink_service_health(
                conn,
                deployment_id=deployment_id,
                service_name=service_name,
                status="missing",
                detail={**detail_base, "source": "docker_compose_ps", "project": docker_result.project_name},
            )
            continue
        detail = {
            **detail_base,
            "source": "docker_compose_ps",
            "project": service.get("project") or docker_result.project_name,
            "container": service.get("container") or "",
            "state": service.get("state") or "",
            "health": service.get("health") or "",
            "exit_code": service.get("exit_code"),
            "status_text": service.get("status_text") or "",
        }
        upsert_arclink_service_health(
            conn,
            deployment_id=deployment_id,
            service_name=service_name,
            status=str(service["status"]),
            detail=detail,
        )


def _parse_docker_compose_ps_json(stdout: str) -> list[dict[str, Any]]:
    text = str(stdout or "").strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
        if isinstance(payload, list):
            return [dict(item) for item in payload if isinstance(item, Mapping)]
        if isinstance(payload, Mapping):
            return [dict(payload)]
    except json.JSONDecodeError:
        pass
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ArcLinkSovereignWorkerError(f"failed to parse docker compose ps JSON line: {exc}") from exc
        if isinstance(payload, Mapping):
            rows.append(dict(payload))
    return rows


def _docker_compose_service_statuses(rows: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    statuses: dict[str, dict[str, Any]] = {}
    for row in rows:
        service_name = str(row.get("Service") or row.get("service") or "").strip()
        if not service_name:
            continue
        state = str(row.get("State") or row.get("state") or "").strip().lower()
        health = str(row.get("Health") or row.get("health") or "").strip().lower()
        exit_code = row.get("ExitCode", row.get("exit_code"))
        status = _docker_compose_row_status(service_name=service_name, state=state, health=health, exit_code=exit_code)
        statuses[service_name] = {
            "status": status,
            "project": str(row.get("Project") or row.get("project") or ""),
            "container": str(row.get("Name") or row.get("Names") or row.get("ID") or ""),
            "state": state,
            "health": health,
            "exit_code": exit_code,
            "status_text": str(row.get("Status") or row.get("status") or ""),
        }
    return statuses


def _docker_compose_row_status(*, service_name: str, state: str, health: str, exit_code: Any) -> str:
    if state == "running":
        if health == "unhealthy":
            return "unhealthy"
        if health == "starting":
            return "starting"
        return "healthy"
    if state == "exited":
        if service_name == "managed-context-install" and str(exit_code) == "0":
            return "healthy"
        return "failed"
    if state in {"created", "restarting"}:
        return "starting"
    if state in {"paused", "dead", "removing"}:
        return "unhealthy"
    return "missing"


def _public_bot_target_for_session(session: Mapping[str, Any]) -> tuple[str, str] | None:
    channel = str(session.get("channel") or "").strip().lower()
    identity = str(session.get("channel_identity") or "").strip()
    if channel == "telegram":
        return "telegram", identity[3:].strip() if identity.lower().startswith("tg:") else identity
    if channel == "discord":
        return "discord", identity[len("discord:"):].strip() if identity.lower().startswith("discord:") else identity
    return None


def _vessel_online_message(*, urls: Mapping[str, Any]) -> str:
    dashboard = str(urls.get("dashboard") or "").strip()
    files = str(urls.get("files") or "").strip()
    code = str(urls.get("code") or "").strip()
    hermes = str(urls.get("hermes") or "").strip()
    lines = [
        "Agent online.",
        "",
        "Stage 4 complete: your ArcLink agent is ready. Drive, Code, Terminal, memory, and deployment health are lit.",
        "",
    ]
    for label, url in (
        ("Dashboard", dashboard),
        ("Drive", files),
        ("Code", code),
        ("Hermes", hermes),
    ):
        if url:
            lines.append(f"{label}: {url}")
    lines.extend(
        [
            "",
            "Use /raven for ArcLink controls, roster, Notion, backups, and linked channels. Bare slash commands belong to your active agent.",
        ]
    )
    return "\n".join(lines)


def _vessel_online_actions(*, urls: Mapping[str, Any]) -> dict[str, Any]:
    dashboard = str(urls.get("dashboard") or "").strip()
    telegram_row: list[dict[str, str]] = []
    discord_buttons: list[dict[str, Any]] = []
    if dashboard:
        telegram_row.append({"text": "Open Helm", "url": dashboard})
        discord_buttons.append({"type": 2, "label": "Open Helm", "style": 5, "url": dashboard})
    telegram_row.extend(
        [
            {"text": "Show My Crew", "callback_data": "arclink:/raven agents"},
            {"text": "Link Channel", "callback_data": "arclink:/raven link-channel"},
        ]
    )
    discord_buttons.extend(
        [
            {"type": 2, "label": "Show My Crew", "style": 2, "custom_id": "arclink:/agents"},
            {"type": 2, "label": "Link Channel", "style": 2, "custom_id": "arclink:/link-channel"},
        ]
    )
    return {
        "telegram_reply_markup": {"inline_keyboard": [telegram_row[:2], telegram_row[2:]] if len(telegram_row) > 2 else [telegram_row]},
        "discord_components": [{"type": 1, "components": discord_buttons[:5]}],
    }


def _queue_vessel_online_notifications(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    urls: Mapping[str, Any],
) -> int:
    existing = conn.execute(
        """
        SELECT 1
        FROM arclink_events
        WHERE subject_kind = 'deployment'
          AND subject_id = ?
          AND event_type = 'public_bot:vessel_online_ping_queued'
        LIMIT 1
        """,
        (deployment_id,),
    ).fetchone()
    if existing is not None:
        return 0
    deployment = conn.execute("SELECT * FROM arclink_deployments WHERE deployment_id = ?", (deployment_id,)).fetchone()
    if deployment is None:
        return 0
    user_id = str(deployment["user_id"] or "").strip()
    rows = conn.execute(
        """
        SELECT *
        FROM arclink_onboarding_sessions
        WHERE channel IN ('telegram', 'discord')
          AND channel_identity != ''
          AND (
            deployment_id = ?
            OR (? != '' AND user_id = ?)
          )
        ORDER BY
          CASE WHEN deployment_id = ? THEN 0 ELSE 1 END,
          updated_at DESC,
          created_at DESC,
          session_id DESC
        """,
        (deployment_id, user_id, user_id, deployment_id),
    ).fetchall()
    seen: set[tuple[str, str]] = set()
    queued = 0
    message = _vessel_online_message(urls=urls)
    extra = _vessel_online_actions(urls=urls)
    for row in rows:
        session = dict(row)
        target = _public_bot_target_for_session(session)
        if target is None:
            continue
        channel, target_id = target
        if not target_id or "#" in target_id:
            continue
        key = (channel, target_id)
        if key in seen:
            continue
        seen.add(key)
        queue_notification(
            conn,
            target_kind="public-bot-user",
            target_id=target_id,
            channel_kind=channel,
            message=message,
            extra=extra,
        )
        record_arclink_onboarding_first_agent_contact(
            conn,
            session_id=str(session["session_id"]),
            channel=str(session["channel"]),
            channel_identity=str(session["channel_identity"]),
        )
        queued += 1
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=deployment_id,
        event_type="public_bot:vessel_online_ping_queued",
        metadata={"notification_count": queued, "channels": sorted({channel for channel, _ in seen})},
    )
    return queued


def _mark_deployment_status(conn: sqlite3.Connection, *, deployment_id: str, status: str) -> None:
    conn.execute("UPDATE arclink_deployments SET status = ?, updated_at = ? WHERE deployment_id = ?", (status, utc_now_iso(), deployment_id))
    conn.commit()


def _safe_error(exc: Exception) -> str:
    msg = str(exc)[:500]
    try:
        reject_secret_material({"error": msg}, label="ArcLink Sovereign worker", error_cls=ArcLinkSovereignWorkerError)
    except ArcLinkSovereignWorkerError:
        return "Sovereign provisioner error contained secret material and was redacted"
    return msg


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ArcLink Sovereign control-node provisioning worker")
    parser.add_argument("--once", action="store_true", help="process one batch and exit")
    parser.add_argument("--json", action="store_true", help="print JSON result")
    args = parser.parse_args(argv)
    cfg = Config.from_env()
    worker = load_worker_config(cfg)
    with connect_db(cfg) as conn:
        results = process_sovereign_batch(conn, worker=worker)
    if args.json:
        print(json_dumps_safe({"results": results}, label="ArcLink Sovereign worker"))
    else:
        print(json.dumps({"results": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
