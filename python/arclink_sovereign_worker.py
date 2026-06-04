#!/usr/bin/env python3
"""ArcLink Sovereign control-node provisioner.

This worker is the connective tissue between hosted onboarding/billing and the
per-Captain ArcPod runtime. It intentionally operates on existing ArcLink
contracts: deployments, fleet hosts, provisioning jobs, DNS records, service
health, audit, and events.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import secrets
import shutil
import socket
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from arclink_boundary import json_dumps_safe, json_loads_safe, reject_secret_material
from arclink_control import (
    Config,
    append_arclink_audit,
    append_arclink_event,
    arclink_deployment_can_provision,
    connect_db,
    create_arclink_provisioning_job,
    ensure_llm_router_key,
    generate_llm_router_raw_key,
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
    ArcLinkExecutorError,
    ArcLinkSecretResolutionError,
    ChutesKeyApplyRequest,
    CloudflareDnsApplyRequest,
    CloudflareDnsApplyResult,
    CloudflareDnsTeardownRequest,
    DockerComposeApplyRequest,
    DockerComposeApplyResult,
    DockerComposeLifecycleRequest,
    FileMaterializingSecretResolver,
    ResolvedSecretFile,
    executor_for_fleet_host,
)
from arclink_fleet import (
    ArcLinkFleetError,
    control_host_max_arcpod_slots,
    place_deployment,
    reconcile_fleet_observed_loads,
    register_fleet_host,
    remove_placement,
)
from arclink_fleet_share import SubprocessGitRunner, ensure_fleet_share, ensure_hub_repo
from arclink_ingress import arclink_dns_records_for_teardown, mark_arclink_dns_torn_down, persist_arclink_dns_records
from arclink_provisioning import (
    ARCLINK_PROVISIONING_SERVICE_NAMES,
    render_arclink_provisioning_intent,
    render_arclink_state_roots,
)
from arclink_adapters import DnsRecord
from arclink_onboarding import record_arclink_onboarding_first_agent_contact
from arclink_api_auth import set_arclink_user_password, set_deployment_share_request_broker_token_hash


class ArcLinkSovereignWorkerError(RuntimeError):
    pass


SOLO_JOB_KIND = "sovereign_pod_apply"
TEARDOWN_JOB_KIND = "sovereign_pod_teardown"
TERMINAL_JOB_STATUSES = {"succeeded", "cancelled"}
TEARDOWN_REQUEST_STATUSES = {"teardown_requested", "teardown_failed", "cancelled"}
TEARDOWN_TERMINAL_STATUSES = {"torn_down", "teardown_complete"}
MISSING_CHUTES_CLIENT_ERROR = "ArcLink live Chutes key execution requires an injectable ChutesKeyClient"
REQUIRED_HERMES_HOME_PLUGIN_SURFACES = {
    "drive": ("plugin", "module", "dashboard"),
    "code": ("plugin", "module", "dashboard"),
    "terminal": ("plugin", "module", "dashboard"),
    "arclink-managed-context": ("plugin", "module"),
}


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
        if resolved.source_path:
            _align_materialized_compose_secret(Path(resolved.source_path), self.env)
        return resolved

    def _value_for_ref(self, secret_ref: str) -> str:
        provider_env = _provider_env_for_ref(secret_ref)
        if provider_env:
            value = str(self.env.get(provider_env) or "").strip()
            if not value:
                raise ArcLinkSecretResolutionError(f"missing ArcLink secret material for {secret_ref}: set {provider_env}")
            return value
        value, _created = self._generated_secret_value_with_created(secret_ref)
        return value

    def _generated_secret_value(self, secret_ref: str) -> str:
        value, _created = self._generated_secret_value_with_created(secret_ref)
        return value

    def _generated_secret_value_with_created(self, secret_ref: str) -> tuple[str, bool]:
        path = self._generated_secret_path(secret_ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o700)
        lock_path = path.with_name(f".{path.name}.lock")
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        tmp_name = ""
        try:
            with os.fdopen(lock_fd, "w") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                if path.exists():
                    return path.read_text(encoding="utf-8").strip(), False
                if secret_ref.startswith("secret://arclink/llm-router/"):
                    value = generate_llm_router_raw_key()
                else:
                    value = f"arc_{secrets.token_urlsafe(36)}"
                with tempfile.NamedTemporaryFile(
                    "w",
                    encoding="utf-8",
                    dir=path.parent,
                    prefix=f".{path.name}.",
                    delete=False,
                ) as tmp:
                    tmp_name = tmp.name
                    tmp.write(value + "\n")
                    tmp.flush()
                    os.fsync(tmp.fileno())
                os.chmod(tmp_name, 0o600)
                os.replace(tmp_name, path)
                return value, True
        except Exception:
            if tmp_name:
                try:
                    Path(tmp_name).unlink()
                except OSError:
                    pass
            raise

    def _generated_secret_path(self, secret_ref: str) -> Path:
        if secret_ref.startswith("secret://arclink/dashboard/users/"):
            return self.secret_store_dir.parent / "users" / f"{hashlib.sha256(secret_ref.encode('utf-8')).hexdigest()}.secret"
        return self.secret_store_dir / f"{hashlib.sha256(secret_ref.encode('utf-8')).hexdigest()}.secret"


def _compose_secret_owner(env: Mapping[str, str]) -> tuple[int, int] | None:
    uid_raw = str(env.get("ARCLINK_DOCKER_UID") or env.get("ARCLINK_UID") or "").strip()
    gid_raw = str(env.get("ARCLINK_DOCKER_GID") or env.get("ARCLINK_GID") or "").strip()
    if not uid_raw or not gid_raw:
        return None
    try:
        uid = int(uid_raw)
        gid = int(gid_raw)
    except ValueError:
        return None
    if uid < 0 or gid < 0:
        return None
    return uid, gid


def _align_materialized_compose_secret(path: Path, env: Mapping[str, str]) -> None:
    path.chmod(0o600)
    owner = _compose_secret_owner(env)
    if owner is None:
        return
    uid, gid = owner
    try:
        os.chown(path, uid, gid)
    except PermissionError as exc:
        try:
            current = path.stat()
        except OSError:
            current = None
        if current is not None and current.st_uid == uid and current.st_gid == gid:
            return
        raise ArcLinkSecretResolutionError("failed to align ArcLink compose secret file owner") from exc


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
    local_capacity_slots = max(1, int(source.get("ARCLINK_LOCAL_FLEET_CAPACITY_SLOTS", "4")))
    if _truthy(source.get("ARCLINK_REGISTER_LOCAL_FLEET_HOST", "0")):
        local_capacity_slots = min(local_capacity_slots, control_host_max_arcpod_slots(source))
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
        local_capacity_slots=local_capacity_slots,
        secret_store_dir=Path(source.get("ARCLINK_SECRET_STORE_DIR") or cfg.state_dir / "sovereign-secrets").resolve(),
        env=source,
    )


def _clean_host_name(value: Any) -> str:
    return str(value or "").strip().lower().strip(".")


def _is_local_host_ref(value: Any, *, worker: SovereignWorkerConfig | None = None) -> bool:
    clean = _clean_host_name(value)
    if clean in {"", "localhost", "localhost.localdomain", "127.0.0.1", "::1", "0.0.0.0"}:
        return True
    local_names = {
        _clean_host_name(socket.gethostname()),
        _clean_host_name(socket.getfqdn()),
    }
    if worker is not None:
        local_names.update(
            {
                _clean_host_name(worker.local_hostname),
                _clean_host_name(worker.local_ssh_host),
            }
        )
    return clean in {name for name in local_names if name}


def _host_is_remote_worker(
    *,
    worker: SovereignWorkerConfig,
    host: Mapping[str, Any],
    host_meta: Mapping[str, Any],
) -> bool:
    mode = str(host_meta.get("control_network_mode") or host_meta.get("arcpod_control_network_mode") or "").strip().lower()
    if mode in {"remote", "tailnet", "tailscale", "none", "off", "0", "false"}:
        return True
    if mode in {"local", "docker", "control", "shared", "on", "1", "true"}:
        return False
    ssh_host = str(host_meta.get("ssh_host") or host.get("hostname") or "").strip()
    if _is_local_host_ref(ssh_host, worker=worker):
        return False
    private_host = str(
        host_meta.get("private_dns_name")
        or host_meta.get("wireguard_dns_name")
        or host_meta.get("private_mesh_dns_name")
        or ""
    ).strip()
    if private_host and not _is_local_host_ref(private_host, worker=worker):
        return True
    executor = str(host_meta.get("executor") or "").strip().lower()
    if executor == "ssh":
        return True
    return worker.executor_adapter == "ssh" and bool(ssh_host)


def _host_requests_local_executor(host_meta: Mapping[str, Any]) -> bool:
    executor = str(host_meta.get("executor") or "").strip().lower()
    if executor != "local":
        return False
    mode = str(host_meta.get("control_network_mode") or host_meta.get("arcpod_control_network_mode") or "").strip().lower()
    return bool(host_meta.get("control_plane_host")) or mode in {"local", "docker", "control", "shared", "on", "1", "true"}


def _host_tailscale_dns_name(
    *,
    worker: SovereignWorkerConfig,
    host: Mapping[str, Any],
    host_meta: Mapping[str, Any],
) -> str:
    for key in ("private_dns_name", "wireguard_dns_name", "private_mesh_dns_name", "tailscale_dns_name", "tailnet_dns_name", "magicdns_name"):
        value = _clean_host_name(host_meta.get(key))
        if value:
            return value
    ssh_host = _clean_host_name(host_meta.get("ssh_host"))
    if ssh_host and not _is_local_host_ref(ssh_host, worker=worker):
        return ssh_host
    hostname = _clean_host_name(host.get("hostname"))
    if hostname and not _is_local_host_ref(hostname, worker=worker):
        return hostname
    return _clean_host_name(worker.tailscale_dns_name or worker.base_domain)


def _host_private_dns_name(
    *,
    worker: SovereignWorkerConfig,
    host: Mapping[str, Any],
    host_meta: Mapping[str, Any],
) -> str:
    for key in ("private_dns_name", "wireguard_dns_name", "private_mesh_dns_name"):
        value = _clean_host_name(host_meta.get(key))
        if value:
            return value
    ssh_host = _clean_host_name(host_meta.get("ssh_host"))
    if ssh_host and not ssh_host.endswith(".ts.net") and not _is_local_host_ref(ssh_host, worker=worker):
        return ssh_host
    hostname = _clean_host_name(host.get("hostname"))
    if hostname and "." in hostname and not hostname.endswith(".ts.net") and not _is_local_host_ref(hostname, worker=worker):
        return hostname
    return ""


def _host_tailscale_compat_dns_name(
    *,
    worker: SovereignWorkerConfig,
    host_meta: Mapping[str, Any],
) -> str:
    for key in ("tailscale_dns_name", "tailnet_dns_name", "magicdns_name"):
        value = _clean_host_name(host_meta.get(key))
        if value:
            return value
    ssh_host = _clean_host_name(host_meta.get("ssh_host"))
    if ssh_host.endswith(".ts.net"):
        return ssh_host
    return _clean_host_name(worker.tailscale_dns_name)


def _private_control_url(worker: SovereignWorkerConfig) -> str:
    value = str(
        worker.env.get("ARCLINK_CONTROL_PRIVATE_BASE_URL")
        or worker.env.get("ARCLINK_WIREGUARD_CONTROL_URL")
        or worker.env.get("ARCLINK_PRIVATE_MESH_CONTROL_URL")
        or worker.env.get("ARCLINK_TAILSCALE_CONTROL_URL")
        or ""
    ).strip().rstrip("/")
    if value:
        return value
    host = _clean_host_name(
        worker.env.get("ARCLINK_PRIVATE_DNS_NAME")
        or worker.env.get("ARCLINK_WIREGUARD_DNS_NAME")
        or worker.env.get("ARCLINK_PRIVATE_MESH_DNS_NAME")
        or worker.tailscale_dns_name
    )
    if not host:
        return ""
    port = str(
        worker.env.get("ARCLINK_CONTROL_PRIVATE_HTTPS_PORT")
        or worker.env.get("ARCLINK_WIREGUARD_HTTPS_PORT")
        or worker.env.get("ARCLINK_PRIVATE_MESH_HTTPS_PORT")
        or worker.tailscale_https_port
        or "443"
    ).strip()
    suffix = "" if port in {"", "443"} else f":{port}"
    return f"https://{host}{suffix}"


def _render_env_for_host(
    *,
    worker: SovereignWorkerConfig,
    host: Mapping[str, Any],
    host_meta: Mapping[str, Any],
) -> dict[str, str]:
    render_env = dict(worker.env)
    remote = _host_is_remote_worker(worker=worker, host=host, host_meta=host_meta)
    host_mode = str(host_meta.get("control_network_mode") or host_meta.get("arcpod_control_network_mode") or "").strip()
    if host_mode:
        render_env["ARCLINK_ARCPOD_CONTROL_NETWORK_MODE"] = host_mode
    elif remote:
        render_env["ARCLINK_ARCPOD_CONTROL_NETWORK_MODE"] = "remote"
    else:
        render_env.setdefault("ARCLINK_ARCPOD_CONTROL_NETWORK_MODE", "local")
    if remote and not str(render_env.get("ARCLINK_TAILSCALE_CONTROL_URL") or "").strip():
        control_url = _private_control_url(worker)
        if control_url:
            render_env["ARCLINK_TAILSCALE_CONTROL_URL"] = control_url
            render_env.setdefault("ARCLINK_CONTROL_PRIVATE_BASE_URL", control_url)
    fleet_share = host_meta.get("fleet_share") if isinstance(host_meta.get("fleet_share"), Mapping) else {}
    if isinstance(fleet_share, Mapping):
        key_path = str(fleet_share.get("ssh_key_path") or "").strip()
        known_hosts = str(fleet_share.get("known_hosts_file") or "").strip()
        if key_path:
            render_env["ARCLINK_FLEET_SHARE_SSH_KEY_PATH"] = key_path
        if known_hosts:
            render_env["ARCLINK_FLEET_SHARE_SSH_KNOWN_HOSTS_FILE"] = known_hosts
    return render_env


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
            "executor": "local",
            "provisioner_executor_adapter": worker.executor_adapter,
            "ingress_mode": worker.ingress_mode,
            "edge_target": worker.edge_target,
            "state_root_base": worker.state_root_base,
            "control_plane_host": True,
            "placement_role": "control_reserve",
            "max_arcpod_slots": control_host_max_arcpod_slots(worker.env),
        }
        if worker.local_ssh_host:
            local_metadata["ssh_host"] = worker.local_ssh_host
        if worker.local_ssh_user:
            local_metadata["ssh_user"] = worker.local_ssh_user
        if worker.tailscale_dns_name:
            local_metadata["tailscale_dns_name"] = worker.tailscale_dns_name
        private_dns_name = _clean_host_name(
            worker.env.get("ARCLINK_PRIVATE_DNS_NAME")
            or worker.env.get("ARCLINK_WIREGUARD_DNS_NAME")
            or worker.env.get("ARCLINK_PRIVATE_MESH_DNS_NAME")
            or ""
        )
        if private_dns_name:
            local_metadata["private_dns_name"] = private_dns_name
        local_metadata["control_network_mode"] = "local"
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
    teardown_rows = conn.execute(
        """
        SELECT d.*
        FROM arclink_deployments d
        LEFT JOIN arclink_provisioning_jobs j
          ON j.deployment_id = d.deployment_id
         AND j.job_kind = ?
        WHERE d.status = 'teardown_requested'
           OR (
             d.status = 'cancelled'
             AND (
               EXISTS (
                 SELECT 1 FROM arclink_deployment_placements p
                 WHERE p.deployment_id = d.deployment_id AND p.status = 'active'
               )
               OR EXISTS (
                 SELECT 1 FROM arclink_dns_records r
                 WHERE r.deployment_id = d.deployment_id AND r.status != 'torn_down'
               )
             )
           )
           OR (
             d.status = 'teardown_failed'
             AND (
               j.status IS NULL
               OR j.status != 'failed'
               OR COALESCE(j.attempt_count, 0) < ?
               OR instr(COALESCE(j.error, ''), ?) > 0
             )
           )
        ORDER BY d.updated_at ASC, d.deployment_id ASC
        LIMIT ?
        """,
        (TEARDOWN_JOB_KIND, worker.max_attempts, MISSING_CHUTES_CLIENT_ERROR, worker.batch_size),
    ).fetchall()
    teardown_results = [
        process_sovereign_teardown(conn, deployment=dict(row), worker=worker, executor=executor)
        for row in teardown_rows
    ]
    rows = conn.execute(
        """
        SELECT d.*
        FROM arclink_deployments d
        LEFT JOIN arclink_provisioning_jobs j
          ON j.deployment_id = d.deployment_id
         AND j.job_kind = ?
        WHERE (
             d.status = 'provisioning_ready'
             OR (
               d.status = 'provisioning_failed'
               AND j.status = 'failed'
               AND COALESCE(j.attempt_count, 0) < ?
             )
           )
          AND COALESCE(d.metadata_json, '') NOT LIKE '%"operator_agent"%'
        ORDER BY d.updated_at ASC, d.deployment_id ASC
        LIMIT ?
        """,
        (SOLO_JOB_KIND, worker.max_attempts, worker.batch_size),
    ).fetchall()
    results = list(teardown_results)
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
        _refresh_crew_dashboard_access_states(conn, user_id=str(deployment.get("user_id") or ""), worker=worker)
        urls = _handoff_urls_for_recovery(conn, deployment=deployment, worker=worker)
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
        _ensure_deployment_fleet_share_hub(conn, deployment=deployment)
        deployment = _ensure_tailnet_service_ports(conn, deployment=deployment, worker=worker)
        result = _apply_deployment(conn, deployment=deployment, job=job, worker=worker, executor=executor)
        transition_arclink_provisioning_job(conn, job_id=str(job["job_id"]), status="succeeded")
        _mark_deployment_status(conn, deployment_id=deployment_id, status="active")
        _refresh_crew_dashboard_access_states(conn, user_id=str(deployment.get("user_id") or ""), worker=worker)
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
        _mark_deployment_failed_if_still_provisioning(conn, deployment_id=deployment_id)
        _record_service_status(conn, deployment_id=deployment_id, status="failed", detail={"error": error})
        append_arclink_event(
            conn,
            subject_kind="deployment",
            subject_id=deployment_id,
            event_type="sovereign_provisioning_failed",
            metadata={"job_id": str(job["job_id"]), "error": error},
        )
        return {"deployment_id": deployment_id, "job_id": str(job["job_id"]), "status": "failed", "error": error}


def _ensure_deployment_fleet_share_hub(conn: sqlite3.Connection, *, deployment: Mapping[str, Any]) -> dict[str, Any]:
    user_id = str(deployment.get("user_id") or "").strip()
    if not user_id:
        raise ArcLinkSovereignWorkerError("deployment has no Captain user id for Fleet shared folder")
    share = ensure_fleet_share(conn, owner_user_id=user_id)
    hub_ref = str(share.get("hub_ref") or "").strip()
    if hub_ref:
        ensure_hub_repo(SubprocessGitRunner(), hub_ref)
    return share


def process_sovereign_teardown(
    conn: sqlite3.Connection,
    *,
    deployment: Mapping[str, Any],
    worker: SovereignWorkerConfig,
    executor: ArcLinkExecutor | None = None,
) -> dict[str, Any]:
    deployment_id = str(deployment["deployment_id"])
    current_status = str(deployment.get("status") or "").strip()
    if current_status in TEARDOWN_TERMINAL_STATUSES:
        return {"deployment_id": deployment_id, "status": "already_torn_down"}
    job = _ensure_teardown_job(conn, deployment_id=deployment_id)
    if str(job["status"]) in TERMINAL_JOB_STATUSES:
        _mark_deployment_status(conn, deployment_id=deployment_id, status="torn_down")
        return {"deployment_id": deployment_id, "job_id": str(job["job_id"]), "status": "already_torn_down"}
    if str(job["status"]) == "running":
        return {"deployment_id": deployment_id, "job_id": str(job["job_id"]), "status": "already_running"}
    if str(job["status"]) == "failed":
        if int(job["attempt_count"] or 0) >= worker.max_attempts and not _teardown_failure_retryable_after_upgrade(job):
            return {"deployment_id": deployment_id, "job_id": str(job["job_id"]), "status": "max_attempts_exhausted"}
        transition_arclink_provisioning_job(conn, job_id=str(job["job_id"]), status="queued")

    transition_arclink_provisioning_job(conn, job_id=str(job["job_id"]), status="running")
    _mark_deployment_status(conn, deployment_id=deployment_id, status="teardown_running")
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=deployment_id,
        event_type="sovereign_teardown_started",
        metadata={"job_id": str(job["job_id"]), "previous_status": current_status},
    )
    try:
        result = _teardown_deployment(conn, deployment=dict(deployment), job=job, worker=worker, executor=executor)
        transition_arclink_provisioning_job(conn, job_id=str(job["job_id"]), status="succeeded")
        _mark_deployment_status(conn, deployment_id=deployment_id, status="torn_down")
        append_arclink_event(
            conn,
            subject_kind="deployment",
            subject_id=deployment_id,
            event_type="sovereign_teardown_completed",
            metadata={"job_id": str(job["job_id"]), **result},
        )
        append_arclink_audit(
            conn,
            action="sovereign_pod_teardown",
            actor_id="system:sovereign_worker",
            target_kind="deployment",
            target_id=deployment_id,
            reason="deployment teardown lifecycle completed",
            metadata={"job_id": str(job["job_id"]), **result},
        )
        return {"deployment_id": deployment_id, "job_id": str(job["job_id"]), "status": "torn_down", **result}
    except Exception as exc:
        error = _safe_error(exc)
        transition_arclink_provisioning_job(conn, job_id=str(job["job_id"]), status="failed", error=error)
        _mark_deployment_status(conn, deployment_id=deployment_id, status="teardown_failed")
        _record_service_status(conn, deployment_id=deployment_id, status="failed", detail={"error": error, "lifecycle": "teardown"})
        append_arclink_event(
            conn,
            subject_kind="deployment",
            subject_id=deployment_id,
            event_type="sovereign_teardown_failed",
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
    # Kept as a pre-placement recheck hook before any fleet placement or DNS
    # side effects. The actual port allocation needs the selected worker.
    del conn
    del worker
    return dict(deployment)


def _ensure_tailnet_service_ports_for_host(
    conn: sqlite3.Connection,
    *,
    deployment: Mapping[str, Any],
    worker: SovereignWorkerConfig,
    host: Mapping[str, Any],
    executor: ArcLinkExecutor | None = None,
) -> dict[str, Any]:
    if worker.ingress_mode != "tailscale" or worker.tailscale_host_strategy != "path":
        return dict(deployment)
    roles = ("hermes",)
    deployment_id = str(deployment["deployment_id"])
    metadata = json_loads_safe(str(deployment.get("metadata_json") or "{}"))
    ports = _tailnet_ports_from_metadata(metadata)
    host_id = str(host.get("host_id") or "").strip()
    if not host_id:
        raise ArcLinkSovereignWorkerError("ArcLink tailnet service port allocation requires a fleet host")

    used = _tailnet_service_ports_used_on_host(conn, host_id=host_id, exclude_deployment_id=deployment_id)
    live_ports = _tailnet_live_published_ports(executor)
    used.update(live_ports)
    if set(roles) <= set(ports) and all(port not in used for port in ports.values()):
        return dict(deployment)

    try:
        next_block = int(str(worker.env.get("ARCLINK_TAILNET_SERVICE_PORT_BASE") or "8443"))
    except ValueError:
        next_block = 8443
    if next_block < 1 or next_block + len(roles) >= 65536:
        next_block = 8443
    previous_ports = dict(ports)
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
            "tailnet_service_ports_host_id": host_id,
            "tailnet_service_ports_live_checked": bool(live_ports),
        }
    )
    if previous_ports and previous_ports != ports:
        metadata["tailnet_service_ports_previous"] = previous_ports
        metadata["tailnet_service_ports_reassigned_at"] = utc_now_iso()
    conn.execute(
        "UPDATE arclink_deployments SET metadata_json = ? WHERE deployment_id = ?",
        (json.dumps(metadata, sort_keys=True), deployment_id),
    )
    conn.commit()
    updated = dict(deployment)
    updated["metadata_json"] = json.dumps(metadata, sort_keys=True)
    return updated


def _tailnet_service_ports_used_on_host(
    conn: sqlite3.Connection,
    *,
    host_id: str,
    exclude_deployment_id: str,
) -> set[int]:
    used: set[int] = set()
    rows = conn.execute(
        """
        SELECT d.deployment_id, d.status, d.metadata_json, p.host_id AS placement_host_id
        FROM arclink_deployments d
        LEFT JOIN arclink_deployment_placements p
          ON p.deployment_id = d.deployment_id
         AND p.status = 'active'
        WHERE d.status NOT IN ('cancelled', 'torn_down', 'teardown_complete')
        """
    ).fetchall()
    for row in rows:
        deployment_id = str(row["deployment_id"] or "")
        if deployment_id == exclude_deployment_id:
            continue
        metadata = json_loads_safe(str(row["metadata_json"] or "{}"))
        metadata_host_id = str(metadata.get("fleet_host_id") or metadata.get("tailnet_service_ports_host_id") or "").strip()
        placement_host_id = str(row["placement_host_id"] or "").strip()
        if host_id not in {placement_host_id, metadata_host_id}:
            continue
        used.update(_tailnet_ports_from_metadata(metadata).values())
    return used


def _tailnet_live_published_ports(executor: ArcLinkExecutor | None) -> set[int]:
    runner = getattr(executor, "docker_runner", None)
    lister = getattr(runner, "list_published_host_ports", None)
    if not callable(lister):
        return set()
    try:
        return {_tailnet_port(port) for port in lister() if _tailnet_port(port)}
    except ArcLinkExecutorError as exc:
        raise ArcLinkSovereignWorkerError(f"ArcLink worker port inspection failed: {exc}") from exc


def _apply_deployment(
    conn: sqlite3.Connection,
    *,
    deployment: Mapping[str, Any],
    job: Mapping[str, Any],
    worker: SovereignWorkerConfig,
    executor: ArcLinkExecutor | None,
) -> dict[str, Any]:
    deployment_id = str(deployment["deployment_id"])
    deployment = _reload_apply_ready_deployment(conn, deployment_id=deployment_id)
    metadata = json_loads_safe(str(deployment.get("metadata_json") or "{}"))
    placement = place_deployment(
        conn,
        deployment_id=deployment_id,
        region=str(metadata.get("region") or ""),
        required_tags=metadata.get("required_tags") if isinstance(metadata.get("required_tags"), Mapping) else None,
    )
    deployment = _reload_apply_ready_deployment(conn, deployment_id=deployment_id)
    host = _host_for_placement(conn, placement)
    host_meta = json_loads_safe(str(host.get("metadata_json") or "{}"))
    edge_target = str(host_meta.get("edge_target") or worker.edge_target)
    state_root_base = str(host_meta.get("state_root_base") or worker.state_root_base)
    host_tailscale_dns_name = _host_tailscale_dns_name(worker=worker, host=host, host_meta=host_meta)
    host_private_dns_name = _host_private_dns_name(worker=worker, host=host, host_meta=host_meta)
    host_tailscale_compat_dns_name = _host_tailscale_compat_dns_name(worker=worker, host_meta=host_meta)
    render_env = _render_env_for_host(worker=worker, host=host, host_meta=host_meta)
    render_base_domain = host_tailscale_dns_name if worker.ingress_mode == "tailscale" and host_tailscale_dns_name else worker.base_domain
    intent = render_arclink_provisioning_intent(
        conn,
        deployment_id=deployment_id,
        base_domain=render_base_domain,
        edge_target=edge_target,
        state_root_base=state_root_base,
        ingress_mode=worker.ingress_mode,
        tailscale_dns_name=host_tailscale_dns_name if worker.ingress_mode == "tailscale" else worker.tailscale_dns_name,
        tailscale_host_strategy=worker.tailscale_host_strategy,
        tailscale_notion_path=worker.tailscale_notion_path,
        env=render_env,
    )
    selected_executor = executor or _executor_for_host(worker=worker, host=host, intent=intent)
    deployment = _ensure_tailnet_service_ports_for_host(
        conn,
        deployment=deployment,
        worker=worker,
        host=host,
        executor=selected_executor,
    )
    intent = render_arclink_provisioning_intent(
        conn,
        deployment_id=deployment_id,
        base_domain=render_base_domain,
        edge_target=edge_target,
        state_root_base=state_root_base,
        ingress_mode=worker.ingress_mode,
        tailscale_dns_name=host_tailscale_dns_name if worker.ingress_mode == "tailscale" else worker.tailscale_dns_name,
        tailscale_host_strategy=worker.tailscale_host_strategy,
        tailscale_notion_path=worker.tailscale_notion_path,
        env=render_env,
    )
    _reload_apply_ready_deployment(conn, deployment_id=deployment_id)
    _persist_deployment_runtime_metadata(
        conn,
        deployment_id=deployment_id,
        urls=intent["access"]["urls"],
        state_roots=intent["state_roots"],
        state_root_base=state_root_base,
        runtime_metadata={
            "fleet_host_id": str(placement["host_id"]),
            "fleet_host_hostname": str(host.get("hostname") or ""),
            "ingress_mode": worker.ingress_mode,
            "private_dns_name": host_private_dns_name if worker.ingress_mode == "tailscale" else "",
            "tailscale_dns_name": host_tailscale_compat_dns_name if worker.ingress_mode == "tailscale" else "",
            "tailscale_host_strategy": worker.tailscale_host_strategy if worker.ingress_mode == "tailscale" else "",
            "control_network_mode": str(intent.get("execution", {}).get("control_network_mode") or ""),
        },
    )
    _reload_apply_ready_deployment(conn, deployment_id=deployment_id)
    _ensure_share_request_broker_token_hash(
        conn,
        deployment=deployment,
        worker=worker,
        intent=intent,
    )
    _reload_apply_ready_deployment(conn, deployment_id=deployment_id)
    _persist_dns_from_intent(conn, deployment_id=deployment_id, dns=intent["dns"])
    _ensure_llm_router_key_registered(conn, deployment=deployment, worker=worker, intent=intent)
    if worker.ingress_mode == "domain" and intent["dns"]:
        _reload_apply_ready_deployment(conn, deployment_id=deployment_id)
        dns_result = selected_executor.cloudflare_dns_apply(
            CloudflareDnsApplyRequest(
                deployment_id=deployment_id,
                dns=intent["dns"],
                zone_id=worker.cloudflare_zone_id,
                idempotency_key=f"arclink:sovereign:dns:{deployment_id}",
            )
        )
        _mark_dns_provisioned(conn, deployment_id=deployment_id, dns_result=dns_result)
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
    _reload_apply_ready_deployment(conn, deployment_id=deployment_id)
    dashboard_password_preexisted = _dashboard_password_secret_preexisted(
        deployment=deployment,
        worker=worker,
        intent=intent,
    )
    docker_result = selected_executor.docker_compose_apply(
        DockerComposeApplyRequest(
            deployment_id=deployment_id,
            intent=intent,
            idempotency_key=f"arclink:sovereign:compose:{deployment_id}",
        )
    )
    deployment = _reload_apply_ready_deployment(conn, deployment_id=deployment_id)
    _sync_dashboard_password_hash_from_secret(
        conn,
        deployment=deployment,
        worker=worker,
        intent=intent,
        password_secret_preexisted=dashboard_password_preexisted,
    )
    _reload_apply_ready_deployment(conn, deployment_id=deployment_id)
    service_statuses = _record_service_status_after_compose(
        conn,
        deployment_id=deployment_id,
        job_id=str(job["job_id"]),
        executor=selected_executor,
        docker_result=docker_result,
    )
    if _truthy(str(worker.env.get("ARCLINK_SOVEREIGN_HANDOFF_REQUIRES_HEALTHY_SERVICES") or "1")):
        blockers = {
            service: status
            for service, status in service_statuses.items()
            if status in {"failed", "unhealthy", "missing"}
        }
        if blockers:
            raise ArcLinkSovereignWorkerError(
                "ArcLink deployment compose services are not ready for handoff: "
                + ", ".join(f"{service}={status}" for service, status in sorted(blockers.items()))
            )
    if _truthy(str(worker.env.get("ARCLINK_SOVEREIGN_HANDOFF_REQUIRES_HERMES_HOME_READY") or "1")):
        try:
            hermes_ready = _validate_hermes_home_ready(
                deployment_id=deployment_id,
                intent=intent,
                executor=selected_executor,
            )
        except ArcLinkSovereignWorkerError as exc:
            upsert_arclink_service_health(
                conn,
                deployment_id=deployment_id,
                service_name="hermes-home-ready",
                status="failed",
                detail={"job_id": str(job["job_id"]), "error": str(exc)},
            )
            raise
        upsert_arclink_service_health(
            conn,
            deployment_id=deployment_id,
            service_name="hermes-home-ready",
            status="healthy",
            detail={"job_id": str(job["job_id"]), **hermes_ready},
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


def _teardown_deployment(
    conn: sqlite3.Connection,
    *,
    deployment: Mapping[str, Any],
    job: Mapping[str, Any],
    worker: SovereignWorkerConfig,
    executor: ArcLinkExecutor | None,
) -> dict[str, Any]:
    deployment_id = str(deployment["deployment_id"])
    metadata = json_loads_safe(str(deployment.get("metadata_json") or "{}"))
    remove_volumes = _teardown_removes_volumes(metadata)
    placement = _active_placement_with_host(conn, deployment_id=deployment_id)
    selected_executor = executor
    intent = _minimal_teardown_intent(deployment=deployment, worker=worker)
    if selected_executor is None and placement is not None:
        selected_executor = _executor_for_host(worker=worker, host=placement["host"], intent=intent)
    if selected_executor is None:
        selected_executor = ArcLinkExecutor(
            config=ArcLinkExecutorConfig(live_enabled=True, adapter_name=worker.executor_adapter),
        )

    compose_status = "skipped"
    if placement is not None or executor is not None:
        compose_result = selected_executor.docker_compose_lifecycle(
            DockerComposeLifecycleRequest(
                deployment_id=deployment_id,
                action="teardown",
                env_file=str(Path(str(intent["state_roots"]["config"])) / "arclink.env"),
                compose_file=str(Path(str(intent["state_roots"]["config"])) / "compose.yaml"),
                idempotency_key=f"arclink:sovereign:compose-teardown:{deployment_id}",
                remove_volumes=remove_volumes,
            )
        )
        compose_status = compose_result.status

    dns_records = arclink_dns_records_for_teardown(conn, deployment_id=deployment_id)
    dns_status = "skipped"
    removed_dns: list[str] = []
    if worker.ingress_mode == "domain" and dns_records:
        dns_result = selected_executor.cloudflare_dns_teardown(
            CloudflareDnsTeardownRequest(
                deployment_id=deployment_id,
                records=dns_records,
                zone_id=worker.cloudflare_zone_id,
                idempotency_key=f"arclink:sovereign:dns-teardown:{deployment_id}",
            )
        )
        dns_status = dns_result.status
        removed_dns = list(dns_result.records)
        mark_arclink_dns_torn_down(
            conn,
            deployment_id=deployment_id,
            removed=removed_dns,
            metadata={"provider_status": dns_status, "job_id": str(job["job_id"])},
        )
    elif dns_records:
        mark_arclink_dns_torn_down(
            conn,
            deployment_id=deployment_id,
            removed=[],
            metadata={"provider_status": "skipped", "ingress_mode": worker.ingress_mode, "job_id": str(job["job_id"])},
        )

    chutes_status = "skipped"
    chutes_secret_ref = _chutes_secret_ref_for_teardown(metadata, deployment_id=deployment_id)
    if chutes_secret_ref and _executor_can_revoke_chutes_key(selected_executor):
        chutes_result = selected_executor.chutes_key_apply(
            ChutesKeyApplyRequest(
                deployment_id=deployment_id,
                action="revoke",
                secret_ref=chutes_secret_ref,
                idempotency_key=f"arclink:sovereign:chutes-revoke:{deployment_id}",
            )
        )
        chutes_status = chutes_result.status
    elif chutes_secret_ref:
        chutes_status = "skipped_no_chutes_client"

    private_store_cleanup = _cleanup_deployment_secret_store(worker=worker, deployment_id=deployment_id)
    removed_placement = remove_placement(conn, deployment_id=deployment_id)
    repaired_loads = reconcile_fleet_observed_loads(conn)
    _release_tailnet_service_ports(conn, deployment_id=deployment_id)
    _record_service_status(
        conn,
        deployment_id=deployment_id,
        status="torn_down",
        detail={
            "job_id": str(job["job_id"]),
            "compose_status": compose_status,
            "dns_status": dns_status,
            "chutes_status": chutes_status,
            "private_store_cleanup_status": private_store_cleanup["status"],
            "remove_volumes": remove_volumes,
        },
    )
    return {
        "compose_status": compose_status,
        "dns_status": dns_status,
        "chutes_status": chutes_status,
        "private_store_cleanup": private_store_cleanup,
        "dns_records": removed_dns,
        "placement_removed": removed_placement is not None,
        "repaired_fleet_loads": repaired_loads,
        "remove_volumes": remove_volumes,
    }


def _cleanup_deployment_secret_store(*, worker: SovereignWorkerConfig, deployment_id: str) -> dict[str, str]:
    clean_id = str(deployment_id or "").strip()
    if not clean_id or clean_id in {".", ".."} or "/" in clean_id or "\\" in clean_id:
        raise ArcLinkSovereignWorkerError(f"refusing unsafe ArcLink deployment secret cleanup id: {clean_id!r}")
    base = worker.secret_store_dir.resolve()
    path = worker.secret_store_dir / clean_id
    if path.parent.resolve() != base:
        raise ArcLinkSovereignWorkerError(f"refusing ArcLink secret cleanup outside secret store: {path}")
    if not path.exists() and not path.is_symlink():
        return {"status": "missing", "path": str(path)}
    if path.is_symlink() or path.is_file():
        path.unlink()
        return {"status": "removed", "path": str(path)}
    if not path.is_dir():
        raise ArcLinkSovereignWorkerError(f"refusing unsupported ArcLink secret cleanup path: {path}")
    try:
        path.resolve().relative_to(base)
    except ValueError as exc:
        raise ArcLinkSovereignWorkerError(f"refusing ArcLink secret cleanup outside secret store: {path}") from exc
    shutil.rmtree(path)
    return {"status": "removed", "path": str(path)}


def _minimal_teardown_intent(*, deployment: Mapping[str, Any], worker: SovereignWorkerConfig) -> dict[str, Any]:
    deployment_id = str(deployment["deployment_id"])
    metadata = json_loads_safe(str(deployment.get("metadata_json") or "{}"))
    raw_roots = metadata.get("state_roots")
    if isinstance(raw_roots, Mapping):
        roots = {str(key): str(value) for key, value in raw_roots.items() if str(value or "").strip()}
    else:
        roots = {}
    if not roots.get("root") or not roots.get("config"):
        state_root_base = str(metadata.get("state_root_base") or worker.state_root_base)
        roots = render_arclink_state_roots(
            deployment_id=deployment_id,
            prefix=str(deployment.get("prefix") or ""),
            state_root_base=state_root_base,
        )
    return {
        "deployment": {"deployment_id": deployment_id},
        "state_roots": roots,
        "compose": {"secrets": {}},
    }


def _active_placement_with_host(conn: sqlite3.Connection, *, deployment_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT
          p.placement_id,
          p.deployment_id,
          p.host_id,
          p.status,
          p.placed_at,
          h.hostname,
          h.metadata_json
        FROM arclink_deployment_placements p
        JOIN arclink_fleet_hosts h ON h.host_id = p.host_id
        WHERE p.deployment_id = ?
          AND p.status = 'active'
        ORDER BY p.placed_at DESC
        LIMIT 1
        """,
        (deployment_id,),
    ).fetchone()
    if row is None:
        return None
    placement = dict(row)
    host = {
        "host_id": str(placement["host_id"]),
        "hostname": str(placement["hostname"]),
        "metadata_json": str(placement["metadata_json"] or "{}"),
    }
    return {"placement": placement, "host": host}


def _teardown_removes_volumes(metadata: Mapping[str, Any]) -> bool:
    teardown = metadata.get("teardown") if isinstance(metadata.get("teardown"), Mapping) else {}
    return bool(teardown.get("remove_volumes") is True)


def _chutes_secret_ref_for_teardown(metadata: Mapping[str, Any], *, deployment_id: str) -> str:
    explicit = str(metadata.get("chutes_secret_ref") or "").strip()
    if explicit:
        return explicit
    return f"secret://arclink/chutes/{deployment_id}"


def _executor_can_revoke_chutes_key(executor: ArcLinkExecutor) -> bool:
    if executor.config.adapter_name == "fake":
        return True
    return getattr(executor, "chutes_client", None) is not None


def _teardown_failure_retryable_after_upgrade(job: Mapping[str, Any]) -> bool:
    if str(job.get("status") or "") != "failed":
        return False
    return MISSING_CHUTES_CLIENT_ERROR in str(job.get("error") or "")


def _release_tailnet_service_ports(conn: sqlite3.Connection, *, deployment_id: str) -> None:
    row = conn.execute("SELECT metadata_json FROM arclink_deployments WHERE deployment_id = ?", (deployment_id,)).fetchone()
    if row is None:
        return
    metadata = json_loads_safe(str(row["metadata_json"] or "{}"))
    if not isinstance(metadata, dict):
        metadata = {}
    if metadata.get("tailnet_service_ports"):
        metadata["tailnet_service_ports"] = {}
        metadata["tailnet_service_ports_released_at"] = utc_now_iso()
        conn.execute(
            "UPDATE arclink_deployments SET metadata_json = ?, updated_at = ? WHERE deployment_id = ?",
            (json.dumps(metadata, sort_keys=True), utc_now_iso(), deployment_id),
        )
        conn.commit()


def _reload_apply_ready_deployment(conn: sqlite3.Connection, *, deployment_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT d.*, u.user_id AS joined_user_id
        FROM arclink_deployments d
        LEFT JOIN arclink_users u
          ON u.user_id = d.user_id
        WHERE d.deployment_id = ?
        """,
        (deployment_id,),
    ).fetchone()
    if row is None:
        raise ArcLinkSovereignWorkerError(f"ArcLink deployment not found before apply: {deployment_id}")
    result = dict(row)
    if not str(result.get("joined_user_id") or "").strip():
        raise ArcLinkSovereignWorkerError(f"ArcLink deployment user missing before apply: {deployment_id}")
    status = str(result.get("status") or "")
    if status != "provisioning":
        raise ArcLinkSovereignWorkerError(
            f"ArcLink deployment changed status before apply side effects: {deployment_id} is {status or 'unknown'}"
        )
    if not arclink_deployment_can_provision(conn, deployment_id=deployment_id):
        raise ArcLinkSovereignWorkerError(f"ArcLink deployment entitlement no longer permits provisioning: {deployment_id}")
    return result


def _persist_deployment_runtime_metadata(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    urls: Mapping[str, Any],
    state_roots: Mapping[str, Any],
    state_root_base: str,
    runtime_metadata: Mapping[str, Any] | None = None,
) -> None:
    row = conn.execute(
        "SELECT metadata_json FROM arclink_deployments WHERE deployment_id = ?",
        (deployment_id,),
    ).fetchone()
    if row is None:
        raise ArcLinkSovereignWorkerError(f"ArcLink deployment not found: {deployment_id}")
    metadata = json_loads_safe(str(row["metadata_json"] or "{}"))
    metadata["access_urls"] = {str(role): str(url) for role, url in dict(urls).items() if str(url or "").strip()}
    metadata["state_roots"] = {str(key): str(value) for key, value in dict(state_roots).items() if str(value or "").strip()}
    metadata["state_root_base"] = str(state_root_base or "").strip()
    for key, value in dict(runtime_metadata or {}).items():
        if value is None:
            continue
        if isinstance(value, str):
            metadata[str(key)] = value.strip()
            continue
        metadata[str(key)] = value
    conn.execute(
        "UPDATE arclink_deployments SET metadata_json = ?, updated_at = ? WHERE deployment_id = ?",
        (json.dumps(metadata, sort_keys=True), utc_now_iso(), deployment_id),
    )
    conn.commit()


def _executor_for_host(
    *,
    worker: SovereignWorkerConfig,
    host: Mapping[str, Any],
    intent: Mapping[str, Any],
) -> ArcLinkExecutor:
    adapter = worker.executor_adapter
    host_meta = json_loads_safe(str(host.get("metadata_json") or "{}"))
    if adapter != "fake" and isinstance(host_meta, Mapping) and _host_requests_local_executor(host_meta):
        adapter = "local"
    if adapter == "fake":
        refs = _secret_refs(intent)
        deployment_id = str((intent.get("deployment") or {}).get("deployment_id") or "")
        resolver = SovereignSecretResolver(
            env=worker.env,
            secret_store_dir=worker.secret_store_dir / deployment_id,
            materialization_root=Path("/tmp/arclink-fake-compose-secrets"),
        )
        fake_values = {
            ref: resolver._value_for_ref(ref) if ref.startswith("secret://arclink/llm-router/") else "fake-secret-material"
            for ref in refs
        }
        return executor_for_fleet_host(
            adapter=adapter,
            env=worker.env,
            host=host,
            fake_secret_refs=fake_values,
        )
    roots = intent.get("state_roots") if isinstance(intent.get("state_roots"), Mapping) else {}
    materialization_root = Path(str(roots.get("config") or "/tmp/arclink-secrets")) / "secrets"
    resolver = SovereignSecretResolver(
        env=worker.env,
        secret_store_dir=worker.secret_store_dir / str(intent["deployment"]["deployment_id"]),
        materialization_root=materialization_root,
    )
    try:
        return executor_for_fleet_host(adapter=adapter, env=worker.env, host=host, secret_resolver=resolver)
    except ArcLinkExecutorError as exc:
        raise ArcLinkSovereignWorkerError(str(exc) or "failed to build ArcLink fleet host executor") from exc


def _access_urls_for_deployment(
    conn: sqlite3.Connection,
    *,
    deployment: Mapping[str, Any],
    worker: SovereignWorkerConfig,
) -> dict[str, str]:
    host_meta: dict[str, Any] = {}
    placement = conn.execute(
        """
        SELECT h.hostname, h.metadata_json
        FROM arclink_deployment_placements p
        JOIN arclink_fleet_hosts h ON h.host_id = p.host_id
        WHERE p.deployment_id = ?
          AND p.status = 'active'
        ORDER BY p.placed_at DESC
        LIMIT 1
        """,
        (str(deployment["deployment_id"]),),
    ).fetchone()
    placement_hostname = ""
    if placement is not None:
        placement_hostname = str(placement["hostname"] or "")
        host_meta = json_loads_safe(str(placement["metadata_json"] or "{}"))
    host_for_render = {
        "hostname": placement_hostname,
        "metadata_json": json.dumps(host_meta, sort_keys=True),
    }
    host_tailscale_dns_name = _host_tailscale_dns_name(worker=worker, host=host_for_render, host_meta=host_meta)
    render_env = _render_env_for_host(worker=worker, host=host_for_render, host_meta=host_meta)
    render_base_domain = host_tailscale_dns_name if worker.ingress_mode == "tailscale" and host_tailscale_dns_name else worker.base_domain
    intent = render_arclink_provisioning_intent(
        conn,
        deployment_id=str(deployment["deployment_id"]),
        base_domain=render_base_domain,
        edge_target=str(host_meta.get("edge_target") or worker.edge_target),
        state_root_base=str(host_meta.get("state_root_base") or worker.state_root_base),
        ingress_mode=worker.ingress_mode,
        tailscale_dns_name=host_tailscale_dns_name if worker.ingress_mode == "tailscale" else worker.tailscale_dns_name,
        tailscale_host_strategy=worker.tailscale_host_strategy,
        tailscale_notion_path=worker.tailscale_notion_path,
        env=render_env,
    )
    access = intent.get("access") if isinstance(intent.get("access"), Mapping) else {}
    urls = access.get("urls") if isinstance(access.get("urls"), Mapping) else {}
    return {str(k): str(v) for k, v in urls.items()}


def _handoff_urls_for_recovery(
    conn: sqlite3.Connection,
    *,
    deployment: Mapping[str, Any],
    worker: SovereignWorkerConfig,
) -> dict[str, str]:
    deployment_id = str(deployment["deployment_id"])
    metadata = json_loads_safe(str(deployment.get("metadata_json") or "{}"))
    cached = metadata.get("access_urls") if isinstance(metadata.get("access_urls"), Mapping) else {}
    urls = {str(k): str(v) for k, v in cached.items() if str(v or "").strip()}
    if urls:
        return urls
    urls = _access_urls_for_deployment(conn, deployment=deployment, worker=worker)
    if urls:
        metadata_roots = metadata.get("state_roots") if isinstance(metadata.get("state_roots"), Mapping) else {}
        state_root_base = str(metadata.get("state_root_base") or worker.state_root_base)
        if not metadata_roots:
            metadata_roots = render_arclink_state_roots(
                deployment_id=deployment_id,
                prefix=str(deployment.get("prefix") or ""),
                state_root_base=state_root_base,
            )
        _persist_deployment_runtime_metadata(
            conn,
            deployment_id=deployment_id,
            urls=urls,
            state_roots=metadata_roots,
            state_root_base=state_root_base,
        )
    return urls


def _refresh_crew_dashboard_access_states(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    worker: SovereignWorkerConfig,
) -> list[str]:
    clean_user = str(user_id or "").strip()
    if not clean_user:
        return []
    rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM arclink_deployments
            WHERE user_id = ?
              AND status NOT IN ('cancelled', 'teardown_complete', 'torn_down', 'archived', 'deleted', 'retired')
            ORDER BY created_at ASC, deployment_id ASC
            """,
            (clean_user,),
        ).fetchall()
    ]
    refreshed: list[str] = []
    for row in rows:
        deployment_id = str(row.get("deployment_id") or "").strip()
        metadata = json_loads_safe(str(row.get("metadata_json") or "{}"))
        roots = metadata.get("state_roots") if isinstance(metadata.get("state_roots"), Mapping) else {}
        hermes_home = str((roots or {}).get("hermes_home") or "").strip()
        if not hermes_home:
            continue
        access_path = Path(hermes_home) / "state" / "arclink-web-access.json"
        if not access_path.is_file():
            continue
        try:
            intent = render_arclink_provisioning_intent(
                conn,
                deployment_id=deployment_id,
                base_domain=worker.base_domain,
                edge_target=str(metadata.get("edge_target") or worker.edge_target),
                state_root_base=str(metadata.get("state_root_base") or worker.state_root_base),
                ingress_mode=worker.ingress_mode,
                tailscale_dns_name=worker.tailscale_dns_name,
                tailscale_host_strategy=worker.tailscale_host_strategy,
                tailscale_notion_path=worker.tailscale_notion_path,
                env=worker.env,
            )
            crew_raw = str((intent.get("environment") or {}).get("ARCLINK_CREW_DASHBOARDS_JSON") or "[]")
            crew = json.loads(crew_raw)
            if not isinstance(crew, list):
                continue
            existing = json_loads_safe(access_path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                continue
            existing["crew_dashboards"] = crew
            existing["crew_dashboards_refreshed_at"] = utc_now_iso()
            access_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(dir=str(access_path.parent), prefix=".arclink-web-access-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(existing, handle, indent=2, sort_keys=True)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp_name, access_path)
            finally:
                try:
                    os.unlink(tmp_name)
                except FileNotFoundError:
                    pass
            access_path.chmod(0o600)
            refreshed.append(deployment_id)
        except Exception:
            continue
    return refreshed


def _secret_refs(intent: Mapping[str, Any]) -> list[str]:
    refs = []
    compose = intent.get("compose") if isinstance(intent.get("compose"), Mapping) else {}
    for spec in (compose.get("secrets") or {}).values():
        if isinstance(spec, Mapping) and spec.get("secret_ref"):
            refs.append(str(spec["secret_ref"]))
    return refs


def _ensure_llm_router_key_registered(
    conn: sqlite3.Connection,
    *,
    deployment: Mapping[str, Any],
    worker: SovereignWorkerConfig,
    intent: Mapping[str, Any],
) -> dict[str, Any] | None:
    secret_refs = intent.get("secret_refs") if isinstance(intent.get("secret_refs"), Mapping) else {}
    secret_ref = str(secret_refs.get("llm_router_api_key") or "").strip()
    if not secret_ref:
        return None
    deployment_id = str(deployment.get("deployment_id") or "").strip()
    user_id = str(deployment.get("user_id") or "").strip()
    if not deployment_id or not user_id:
        return None
    resolver = SovereignSecretResolver(
        env=worker.env,
        secret_store_dir=worker.secret_store_dir / deployment_id,
        materialization_root=Path("/tmp/arclink-llm-router-key-registration"),
    )
    raw_key = resolver._value_for_ref(secret_ref)
    model = str(
        worker.env.get("ARCLINK_LLM_ROUTER_DEFAULT_MODEL")
        or worker.env.get("ARCLINK_CHUTES_DEFAULT_MODEL")
        or ""
    ).strip()
    return ensure_llm_router_key(
        conn,
        deployment_id=deployment_id,
        user_id=user_id,
        secret_ref=secret_ref,
        raw_key=raw_key,
        allowed_models=[model] if model else None,
        metadata={"source": "sovereign_worker"},
    )


def _ensure_share_request_broker_token_hash(
    conn: sqlite3.Connection,
    *,
    deployment: Mapping[str, Any],
    worker: SovereignWorkerConfig,
    intent: Mapping[str, Any],
) -> dict[str, Any] | None:
    secret_refs = intent.get("secret_refs") if isinstance(intent.get("secret_refs"), Mapping) else {}
    secret_ref = str(secret_refs.get("share_request_broker_token") or "").strip()
    deployment_id = str(deployment.get("deployment_id") or "").strip()
    if not secret_ref or not deployment_id:
        return None
    resolver = SovereignSecretResolver(
        env=worker.env,
        secret_store_dir=worker.secret_store_dir / deployment_id,
        materialization_root=Path("/tmp/arclink-share-request-broker-token-sync"),
    )
    token = resolver._value_for_ref(secret_ref)
    return set_deployment_share_request_broker_token_hash(
        conn,
        deployment_id=deployment_id,
        token=token,
        token_ref=secret_ref,
    )


def _sync_dashboard_password_hash_from_secret(
    conn: sqlite3.Connection,
    *,
    deployment: Mapping[str, Any],
    worker: SovereignWorkerConfig,
    intent: Mapping[str, Any],
    password_secret_preexisted: bool = False,
) -> None:
    secret_refs = intent.get("secret_refs") if isinstance(intent.get("secret_refs"), Mapping) else {}
    secret_ref = str(secret_refs.get("dashboard_password") or "").strip()
    user_id = str(deployment.get("user_id") or "").strip()
    deployment_id = str(deployment.get("deployment_id") or "").strip()
    if not secret_ref or not user_id or not deployment_id:
        return
    if password_secret_preexisted:
        return
    resolver = SovereignSecretResolver(
        env=worker.env,
        secret_store_dir=worker.secret_store_dir / deployment_id,
        materialization_root=Path("/tmp/arclink-dashboard-password-sync"),
    )
    password = resolver._value_for_ref(secret_ref)
    set_arclink_user_password(conn, user_id=user_id, password=password)


def _dashboard_password_secret_preexisted(
    *,
    deployment: Mapping[str, Any],
    worker: SovereignWorkerConfig,
    intent: Mapping[str, Any],
) -> bool:
    secret_refs = intent.get("secret_refs") if isinstance(intent.get("secret_refs"), Mapping) else {}
    secret_ref = str(secret_refs.get("dashboard_password") or "").strip()
    deployment_id = str(deployment.get("deployment_id") or "").strip()
    if not secret_ref or not deployment_id:
        return True
    if _provider_env_for_ref(secret_ref):
        return True
    resolver = SovereignSecretResolver(
        env=worker.env,
        secret_store_dir=worker.secret_store_dir / deployment_id,
        materialization_root=Path("/tmp/arclink-dashboard-password-check"),
    )
    return resolver._generated_secret_path(secret_ref).exists()


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


def _ensure_teardown_job(conn: sqlite3.Connection, *, deployment_id: str) -> dict[str, Any]:
    key = f"arclink:sovereign:teardown:{deployment_id}"
    row = conn.execute("SELECT * FROM arclink_provisioning_jobs WHERE idempotency_key = ?", (key,)).fetchone()
    if row is None:
        create_arclink_provisioning_job(
            conn,
            job_id=f"job_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]}",
            deployment_id=deployment_id,
            job_kind=TEARDOWN_JOB_KIND,
            idempotency_key=key,
            metadata={"deployment_id": deployment_id, "worker": "sovereign", "lifecycle": "teardown"},
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


def _mark_dns_provisioned(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    dns_result: CloudflareDnsApplyResult | None = None,
) -> None:
    now = utc_now_iso()
    conn.execute(
        "UPDATE arclink_dns_records SET status = 'provisioned', updated_at = ?, last_checked_at = ? WHERE deployment_id = ?",
        (now, now, deployment_id),
    )
    provider_ids = ()
    if dns_result is not None and isinstance(dns_result.metadata, Mapping):
        raw_ids = dns_result.metadata.get("provider_record_ids")
        if isinstance(raw_ids, (list, tuple)):
            provider_ids = tuple(str(item or "").strip() for item in raw_ids)
    if provider_ids:
        hostnames = tuple(str(hostname or "").strip().lower() for hostname in (dns_result.records if dns_result is not None else ()))
        for hostname, provider_id in zip(hostnames, provider_ids):
            if hostname and provider_id:
                conn.execute(
                    """
                    UPDATE arclink_dns_records
                    SET provider_record_id = ?
                    WHERE deployment_id = ?
                      AND LOWER(hostname) = ?
                    """,
                    (provider_id, deployment_id, hostname),
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
) -> dict[str, str]:
    detail_base = {"job_id": job_id, "executor": executor.config.adapter_name}
    if executor.config.adapter_name == "fake":
        _record_service_status(conn, deployment_id=deployment_id, status="healthy", detail=detail_base)
        return {service_name: "healthy" for service_name in ARCLINK_PROVISIONING_SERVICE_NAMES}
    if executor.docker_runner is None:
        _record_service_status(
            conn,
            deployment_id=deployment_id,
            status="failed",
            detail={**detail_base, "reconcile_error": "docker_runner_not_available"},
        )
        return {service_name: "failed" for service_name in ARCLINK_PROVISIONING_SERVICE_NAMES}
    try:
        ps_result = executor.docker_runner.run(
            ("ps", "--all", "--format", "json"),
            deployment_id=deployment_id,
            project_name=docker_result.project_name,
            env_file=docker_result.env_file,
            compose_file=docker_result.compose_file,
        )
        rows = _parse_docker_compose_ps_json(str(ps_result.get("stdout") or ""))
        statuses = _docker_compose_service_statuses(rows, project_name=docker_result.project_name)
    except Exception as exc:  # noqa: BLE001 - service health reconciliation must not undo a successful apply
        _record_service_status(
            conn,
            deployment_id=deployment_id,
            status="failed",
            detail={**detail_base, "reconcile_error": _safe_error(exc)},
        )
        return {service_name: "failed" for service_name in ARCLINK_PROVISIONING_SERVICE_NAMES}

    recorded: dict[str, str] = {}
    for service_name in ARCLINK_PROVISIONING_SERVICE_NAMES:
        service = statuses.get(service_name)
        if service is None:
            recorded[service_name] = "missing"
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
        recorded[service_name] = str(service["status"])
    return recorded


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


def _docker_compose_service_statuses(rows: list[Mapping[str, Any]], *, project_name: str = "") -> dict[str, dict[str, Any]]:
    statuses: dict[str, dict[str, Any]] = {}
    for row in rows:
        project = str(row.get("Project") or row.get("project") or "").strip()
        if project_name and project and project != project_name:
            continue
        service_name = str(row.get("Service") or row.get("service") or "").strip()
        if not service_name:
            continue
        state = str(row.get("State") or row.get("state") or "").strip().lower()
        health = str(row.get("Health") or row.get("health") or "").strip().lower()
        exit_code = row.get("ExitCode", row.get("exit_code"))
        status = _docker_compose_row_status(service_name=service_name, state=state, health=health, exit_code=exit_code)
        statuses[service_name] = {
            "status": status,
            "project": project,
            "container": str(row.get("Name") or row.get("Names") or row.get("ID") or ""),
            "state": state,
            "health": health,
            "exit_code": exit_code,
            "status_text": str(row.get("Status") or row.get("status") or ""),
        }
    return statuses


def _validate_hermes_home_ready(
    *,
    deployment_id: str,
    intent: Mapping[str, Any],
    executor: ArcLinkExecutor | None = None,
) -> dict[str, Any]:
    state_roots = intent.get("state_roots") if isinstance(intent.get("state_roots"), Mapping) else {}
    hermes_home = str((state_roots or {}).get("hermes_home") or "").strip()
    if not hermes_home:
        raise ArcLinkSovereignWorkerError("ArcLink Hermes home readiness manifest missing state root")
    ready_file = Path(hermes_home) / "state" / "arclink-hermes-home-ready.json"
    try:
        if ready_file.is_file():
            ready_text = ready_file.read_text(encoding="utf-8")
        else:
            ready_text = _read_remote_hermes_home_ready_file(
                ready_file=str(ready_file),
                state_root=str((state_roots or {}).get("root") or ""),
                executor=executor,
            )
        payload = json.loads(ready_text)
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, ArcLinkSovereignWorkerError):
            raise
        raise ArcLinkSovereignWorkerError(f"ArcLink Hermes home readiness manifest is unreadable: {type(exc).__name__}") from exc
    if not isinstance(payload, Mapping):
        raise ArcLinkSovereignWorkerError("ArcLink Hermes home readiness manifest is not an object")
    status = str(payload.get("status") or "").strip().lower()
    if status != "ready":
        raise ArcLinkSovereignWorkerError(f"ArcLink Hermes home readiness manifest status is {status or 'blank'}")
    manifest_deployment_id = str(payload.get("deployment_id") or "").strip()
    if manifest_deployment_id and manifest_deployment_id != deployment_id:
        raise ArcLinkSovereignWorkerError(
            f"ArcLink Hermes home readiness manifest belongs to {manifest_deployment_id}, not {deployment_id}"
        )
    plugins = payload.get("plugins")
    if not isinstance(plugins, Mapping):
        raise ArcLinkSovereignWorkerError("ArcLink Hermes home readiness manifest is missing plugin status")
    missing: list[str] = []
    for plugin_name, fields in REQUIRED_HERMES_HOME_PLUGIN_SURFACES.items():
        plugin_status = plugins.get(plugin_name)
        if not isinstance(plugin_status, Mapping):
            missing.append(plugin_name)
            continue
        for field in fields:
            if plugin_status.get(field) is not True:
                missing.append(f"{plugin_name}.{field}")
    if missing:
        raise ArcLinkSovereignWorkerError(
            "ArcLink Hermes home readiness manifest is missing required plugin surfaces: "
            + ", ".join(sorted(missing))
        )
    return {
        "ready_file": str(ready_file),
        "ready_at": str(payload.get("ready_at") or ""),
        "required_plugins": sorted(REQUIRED_HERMES_HOME_PLUGIN_SURFACES),
    }


def _read_remote_hermes_home_ready_file(
    *,
    ready_file: str,
    state_root: str,
    executor: ArcLinkExecutor | None,
) -> str:
    runner = getattr(executor, "docker_runner", None)
    reader = getattr(runner, "read_text_file", None)
    if not callable(reader):
        raise ArcLinkSovereignWorkerError(f"ArcLink Hermes home readiness manifest missing: {ready_file}")
    if not str(state_root or "").strip():
        raise ArcLinkSovereignWorkerError("ArcLink Hermes home readiness manifest missing state root")
    try:
        return str(reader(ready_file, allowed_root=state_root))
    except ArcLinkExecutorError as exc:
        raise ArcLinkSovereignWorkerError(f"ArcLink Hermes home readiness manifest is unreadable over SSH: {exc}") from exc


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


def _deployment_dashboard_url(deployment: Mapping[str, Any], *, fallback_urls: Mapping[str, Any] | None = None) -> str:
    metadata = json_loads_safe(str(deployment.get("metadata_json") or "{}"))
    access_urls = metadata.get("access_urls") if isinstance(metadata.get("access_urls"), Mapping) else {}
    dashboard = str((access_urls or {}).get("hermes") or (access_urls or {}).get("dashboard") or "").strip()
    if not dashboard and fallback_urls:
        dashboard = str(fallback_urls.get("hermes") or fallback_urls.get("dashboard") or "").strip()
    return dashboard


def _vessel_online_message(
    conn: sqlite3.Connection,
    *,
    deployment: Mapping[str, Any],
    urls: Mapping[str, Any],
) -> str:
    label = str(deployment.get("agent_name") or "").strip() or f"Hermes Agent #{str(deployment.get('prefix') or '').rsplit('-', 1)[-1]}"
    title = str(deployment.get("agent_title") or "").strip() or "Hermes Agent"
    user_id = str(deployment.get("user_id") or "").strip()
    crew_rows = []
    if user_id:
        crew_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM arclink_deployments
                WHERE user_id = ?
                  AND status NOT IN ('cancelled', 'teardown_complete', 'torn_down')
                ORDER BY created_at ASC, deployment_id ASC
                """,
                (user_id,),
            ).fetchall()
        ]
    if not crew_rows:
        crew_rows = [dict(deployment)]
    crew_lines: list[str] = []
    for index, item in enumerate(crew_rows, start=1):
        item_label = str(item.get("agent_name") or "").strip() or f"Hermes Agent #{str(item.get('prefix') or index).rsplit('-', 1)[-1]}"
        item_title = str(item.get("agent_title") or "").strip() or "Hermes Agent"
        status = str(item.get("status") or "pending").replace("_", " ")
        dashboard = _deployment_dashboard_url(
            item,
            fallback_urls=urls if str(item.get("deployment_id") or "") == str(deployment.get("deployment_id") or "") else None,
        )
        link = f" - {dashboard}" if dashboard else ""
        crew_lines.append(f"- {item_label}: {item_title} ({status}){link}")
    ready_count = sum(1 for item in crew_rows if str(item.get("status") or "").strip() == "active")
    if len(crew_rows) == 1:
        readiness_line = "Your ArcPod is ready." if ready_count else "Your ArcPod launch is in progress."
    elif ready_count == len(crew_rows):
        readiness_line = "Your ArcPods are ready."
    else:
        readiness_line = f"Your Crew launch is in progress: {ready_count}/{len(crew_rows)} Hermes Agent dashboards ready."
    lines = [
        f"{label} is online as a Hermes Agent.",
        "",
        readiness_line,
        "",
        *crew_lines,
    ]
    lines.extend(
        [
            "",
            "Use Show My Crew to switch Hermes Agents. The same dashboard login opens each Hermes Dashboard.",
            "ArcLink skills, Drive, Code, and Terminal are installed there as Hermes Dashboard plugins.",
            "Use Learn when you want the tour; use Crew Training when you are ready to shape the Crew.",
        ]
    )
    return "\n".join(lines)


def _vessel_online_actions(*, deployment_id: str, urls: Mapping[str, Any], session_id: str = "") -> dict[str, Any]:
    dashboard = str(urls.get("hermes") or urls.get("dashboard") or "").strip()
    credential_command = f"/raven credentials {str(deployment_id or '').strip()}".strip()
    telegram_row: list[dict[str, str]] = []
    discord_buttons: list[dict[str, Any]] = []
    if dashboard:
        telegram_row.append({"text": "Open Hermes Dashboard", "url": dashboard})
        discord_buttons.append({"type": 2, "label": "Open Hermes Dashboard", "style": 5, "url": dashboard})
    telegram_row.extend(
        [
            {"text": "Learn", "callback_data": "arclink:/raven learn"},
            {"text": "Crew Training", "callback_data": "arclink:/raven train_crew"},
            {"text": "Credentials", "callback_data": f"arclink:{credential_command}"[:64]},
            {"text": "Show My Crew", "callback_data": "arclink:/raven agents"},
        ]
    )
    discord_buttons.extend(
        [
            {"type": 2, "label": "Learn", "style": 2, "custom_id": "arclink:/learn"},
            {"type": 2, "label": "Crew Training", "style": 2, "custom_id": "arclink:/train-crew"},
            {"type": 2, "label": "Credentials", "style": 2, "custom_id": f"arclink:{credential_command}"[:100]},
            {"type": 2, "label": "Show My Crew", "style": 2, "custom_id": "arclink:/agents"},
        ]
    )
    extra = {
        "telegram_reply_markup": {"inline_keyboard": [telegram_row[:2], telegram_row[2:]] if len(telegram_row) > 2 else [telegram_row]},
        "discord_components": [{"type": 1, "components": discord_buttons[:5]}],
    }
    if session_id:
        extra.update(
            {
                "edit_existing_message": True,
                "edit_existing_session_id": session_id,
                "onboarding_session_id": session_id,
                "edit_fallback_to_send": True,
            }
        )
    return extra


def _focus_public_bot_session_on_deployment(
    conn: sqlite3.Connection,
    *,
    session: Mapping[str, Any],
    deployment: Mapping[str, Any],
) -> None:
    session_id = str(session.get("session_id") or "").strip()
    deployment_id = str(deployment.get("deployment_id") or "").strip()
    if not session_id or not deployment_id:
        return
    metadata = json_loads_safe(str(session.get("metadata_json") or "{}"))
    metadata["active_deployment_id"] = deployment_id
    label = str(deployment.get("agent_name") or "").strip()
    prefix = str(deployment.get("prefix") or "").strip()
    if label:
        metadata["active_agent_label"] = label
    elif prefix:
        metadata["active_agent_label"] = f"Hermes Agent #{prefix.rsplit('-', 1)[-1]}"
    conn.execute(
        """
        UPDATE arclink_onboarding_sessions
        SET metadata_json = ?, updated_at = ?
        WHERE session_id = ?
        """,
        (json_dumps_safe(metadata), utc_now_iso(), session_id),
    )


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
    message = _vessel_online_message(conn, deployment=dict(deployment), urls=urls)
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
        extra = _vessel_online_actions(
            deployment_id=deployment_id,
            urls=urls,
            session_id=str(session.get("session_id") or ""),
        )
        _focus_public_bot_session_on_deployment(conn, session=session, deployment=dict(deployment))
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


def _mark_deployment_failed_if_still_provisioning(conn: sqlite3.Connection, *, deployment_id: str) -> None:
    conn.execute(
        "UPDATE arclink_deployments SET status = 'provisioning_failed', updated_at = ? WHERE deployment_id = ? AND status = 'provisioning'",
        (utc_now_iso(), deployment_id),
    )
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
