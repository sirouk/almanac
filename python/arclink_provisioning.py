#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from typing import Any, Mapping

from almanac_control import (
    append_arclink_event,
    arclink_deployment_can_provision,
    arclink_deployment_entitlement_state,
    create_arclink_provisioning_job,
    transition_arclink_provisioning_job,
    upsert_arclink_service_health,
)
from arclink_access import build_arclink_ssh_access_record
from arclink_adapters import arclink_hostnames
from arclink_ingress import desired_arclink_dns_records, render_traefik_dynamic_labels
from arclink_product import chutes_base_url, chutes_default_model, model_reasoning_default, primary_provider


ARCLINK_PROVISIONING_SERVICE_NAMES = (
    "dashboard",
    "hermes-gateway",
    "hermes-dashboard",
    "qmd-mcp",
    "vault-watch",
    "memory-synth",
    "nextcloud-db",
    "nextcloud-redis",
    "nextcloud",
    "code-server",
    "notification-delivery",
    "health-watch",
    "managed-context-install",
)

CONTAINER_HERMES_HOME = "/home/almanac/.hermes"
CONTAINER_QMD_STATE_DIR = "/home/almanac/.qmd"
CONTAINER_VAULT_DIR = "/srv/vault"
CONTAINER_MEMORY_STATE_DIR = "/srv/memory"

_SECRET_KEY_RE = re.compile(r"(secret|token|api[_-]?key|password|credential|webhook|client[_-]?secret)", re.I)
_PLAINTEXT_SECRET_RE = re.compile(
    r"(?i)("
    r"sk_(live|test)_[a-z0-9]|"
    r"whsec_[a-z0-9]|"
    r"gh[pousr]_[a-z0-9]|"
    r"xox[baprs]-|"
    r"ntn_[a-z0-9]|"
    r"cloudflare[a-z0-9_-]*token|"
    r"\b\d{6,}:[a-z0-9_-]{20,}\b"
    r")"
)


class ArcLinkProvisioningError(RuntimeError):
    pass


class ArcLinkSecretReferenceError(ArcLinkProvisioningError):
    pass


def _json_loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ArcLinkProvisioningError("ArcLink deployment metadata must be a JSON object")
    return dict(parsed)


def _safe_segment(value: str) -> str:
    segment = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip(".-")
    if not segment:
        raise ArcLinkProvisioningError("ArcLink provisioning path segment cannot be empty")
    return segment


def _job_id(idempotency_key: str) -> str:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:24]
    return f"job_{digest}"


def _event_id(job_id: str, phase: str) -> str:
    digest = hashlib.sha256(f"{job_id}:{phase}".encode("utf-8")).hexdigest()[:24]
    return f"evt_{digest}"


def _append_timeline_event_once(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    job_id: str,
    phase: str,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    payload = {"job_id": job_id, "phase": phase}
    payload.update(dict(metadata or {}))
    try:
        append_arclink_event(
            conn,
            event_id=_event_id(job_id, phase),
            subject_kind="deployment",
            subject_id=deployment_id,
            event_type=f"provisioning_{phase}",
            metadata=payload,
        )
    except sqlite3.IntegrityError:
        pass


def _ensure_job(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    job_kind: str,
    idempotency_key: str,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM arclink_provisioning_jobs WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()
    if row is not None:
        existing = dict(row)
        if str(existing["deployment_id"]) != deployment_id or str(existing["job_kind"]) != job_kind:
            raise ArcLinkProvisioningError("ArcLink provisioning idempotency key is already bound to another job")
        return existing
    job_id = _job_id(idempotency_key)
    create_arclink_provisioning_job(
        conn,
        job_id=job_id,
        deployment_id=deployment_id,
        job_kind=job_kind,
        idempotency_key=idempotency_key,
        metadata=metadata,
    )
    _append_timeline_event_once(conn, deployment_id=deployment_id, job_id=job_id, phase="planned")
    return dict(conn.execute("SELECT * FROM arclink_provisioning_jobs WHERE job_id = ?", (job_id,)).fetchone())


def _load_deployment(conn: sqlite3.Connection, deployment_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM arclink_deployments WHERE deployment_id = ?", (deployment_id,)).fetchone()
    if row is None:
        raise KeyError(deployment_id)
    return dict(row)


def _load_user(conn: sqlite3.Connection, user_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM arclink_users WHERE user_id = ?", (user_id,)).fetchone()
    return {} if row is None else dict(row)


def render_arclink_state_roots(
    *,
    deployment_id: str,
    prefix: str,
    state_root_base: str = "/arcdata/deployments",
) -> dict[str, str]:
    root = f"{str(state_root_base).rstrip('/')}/{_safe_segment(deployment_id)}-{_safe_segment(prefix)}"
    return {
        "root": root,
        "config": f"{root}/config",
        "state": f"{root}/state",
        "vault": f"{root}/vault",
        "hermes_home": f"{root}/state/hermes-home",
        "qmd": f"{root}/state/qmd",
        "memory": f"{root}/state/memory",
        "nextcloud": f"{root}/state/nextcloud",
        "nextcloud_html": f"{root}/state/nextcloud/html",
        "nextcloud_db": f"{root}/state/nextcloud/db",
        "nextcloud_redis": f"{root}/state/nextcloud/redis",
        "code_workspace": f"{root}/workspace",
        "logs": f"{root}/logs",
    }


def _secret_ref(metadata: Mapping[str, Any], key: str, default: str) -> str:
    value = str(metadata.get(key) or "").strip()
    return value or default


def _render_secret_refs(deployment_id: str, metadata: Mapping[str, Any]) -> dict[str, str]:
    return {
        "chutes_api_key": _secret_ref(metadata, "chutes_secret_ref", f"secret://arclink/chutes/{deployment_id}"),
        "nextcloud_admin_password": _secret_ref(
            metadata,
            "nextcloud_admin_password_ref",
            f"secret://arclink/nextcloud/{deployment_id}/admin-password",
        ),
        "nextcloud_db_password": _secret_ref(
            metadata,
            "nextcloud_db_password_ref",
            f"secret://arclink/nextcloud/{deployment_id}/db-password",
        ),
        "code_server_password": _secret_ref(
            metadata,
            "code_server_password_ref",
            f"secret://arclink/code-server/{deployment_id}/password",
        ),
        "telegram_bot_token": str(metadata.get("telegram_bot_token_ref") or "").strip(),
        "discord_bot_token": str(metadata.get("discord_bot_token_ref") or "").strip(),
        "notion_token": str(metadata.get("notion_token_ref") or "").strip(),
        "stripe_customer": str(metadata.get("stripe_customer_ref") or "").strip(),
        "cloudflare_tunnel": str(metadata.get("cloudflare_tunnel_token_ref") or "").strip(),
    }


def _host_urls(hostnames: Mapping[str, str]) -> dict[str, str]:
    return {role: f"https://{hostname}" for role, hostname in hostnames.items()}


def _compose_secret_name(key: str) -> str:
    return re.sub(r"[^a-z0-9_.-]+", "_", key.lower()).strip("_.-")


def _render_compose_secrets(secret_refs: Mapping[str, str]) -> dict[str, dict[str, str]]:
    secrets: dict[str, dict[str, str]] = {}
    for key, secret_ref in secret_refs.items():
        if not secret_ref:
            continue
        name = _compose_secret_name(key)
        secrets[name] = {
            "secret_ref": secret_ref,
            "target": f"/run/secrets/{name}",
        }
    return secrets


def _service(
    *,
    image: str,
    command: list[str],
    environment: Mapping[str, str],
    volumes: list[dict[str, str]] | None = None,
    labels: Mapping[str, str] | None = None,
    depends_on: list[str] | None = None,
    secrets: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "image": image,
        "command": command,
        "environment": dict(environment),
        "volumes": list(volumes or []),
        "labels": dict(labels or {}),
        "depends_on": list(depends_on or []),
        "secrets": list(secrets or []),
    }


def _render_services(
    *,
    deployment_id: str,
    prefix: str,
    roots: Mapping[str, str],
    env: Mapping[str, str],
    labels: Mapping[str, Mapping[str, str]],
    compose_secrets: Mapping[str, Mapping[str, str]],
) -> dict[str, dict[str, Any]]:
    app_image = "${ALMANAC_DOCKER_IMAGE:-almanac/app:local}"
    secret_target = {name: str(spec["target"]) for name, spec in compose_secrets.items()}
    return {
        "dashboard": _service(
            image=app_image,
            command=["./bin/arclink-dashboard-placeholder.sh"],
            environment=env,
            labels=labels["dashboard"],
        ),
        "hermes-gateway": _service(
            image=app_image,
            command=["hermes", "gateway", "run", "--replace"],
            environment=env,
            volumes=[{"source": roots["hermes_home"], "target": CONTAINER_HERMES_HOME}],
            labels=labels["hermes"],
            depends_on=["qmd-mcp", "managed-context-install"],
        ),
        "hermes-dashboard": _service(
            image=app_image,
            command=["hermes", "dashboard", "--host", "0.0.0.0"],
            environment=env,
            volumes=[{"source": roots["hermes_home"], "target": CONTAINER_HERMES_HOME}],
            depends_on=["managed-context-install"],
        ),
        "qmd-mcp": _service(
            image=app_image,
            command=["./bin/qmd-daemon.sh"],
            environment=env,
            volumes=[
                {"source": roots["vault"], "target": CONTAINER_VAULT_DIR},
                {"source": roots["qmd"], "target": CONTAINER_QMD_STATE_DIR},
            ],
        ),
        "vault-watch": _service(
            image=app_image,
            command=["./bin/vault-watch.sh"],
            environment=env,
            volumes=[{"source": roots["vault"], "target": CONTAINER_VAULT_DIR}],
            depends_on=["qmd-mcp"],
        ),
        "memory-synth": _service(
            image=app_image,
            command=["./bin/docker-job-loop.sh", "memory-synth", "1800", "./bin/memory-synth.sh"],
            environment=env,
            volumes=[{"source": roots["memory"], "target": CONTAINER_MEMORY_STATE_DIR}],
            depends_on=["qmd-mcp"],
        ),
        "nextcloud-db": _service(
            image="${ALMANAC_POSTGRES_IMAGE:-docker.io/library/postgres}:${ALMANAC_POSTGRES_TAG:-16-alpine}",
            command=[],
            environment={
                "POSTGRES_DB": f"nextcloud_{deployment_id}",
                "POSTGRES_USER": "nextcloud",
                "POSTGRES_PASSWORD_FILE": secret_target["nextcloud_db_password"],
            },
            volumes=[{"source": roots["nextcloud_db"], "target": "/var/lib/postgresql/data"}],
            secrets=[{"source": "nextcloud_db_password", "target": secret_target["nextcloud_db_password"]}],
        ),
        "nextcloud-redis": _service(
            image="${ALMANAC_REDIS_IMAGE:-docker.io/library/redis}:${ALMANAC_REDIS_TAG:-7-alpine}",
            command=["redis-server", "--appendonly", "yes"],
            environment={},
            volumes=[{"source": roots["nextcloud_redis"], "target": "/data"}],
        ),
        "nextcloud": _service(
            image="${ALMANAC_NEXTCLOUD_IMAGE:-docker.io/library/nextcloud}:${ALMANAC_NEXTCLOUD_TAG:-31-apache}",
            command=["apache2-foreground"],
            environment={
                "POSTGRES_HOST": "nextcloud-db",
                "POSTGRES_DB": f"nextcloud_{deployment_id}",
                "POSTGRES_USER": "nextcloud",
                "POSTGRES_PASSWORD_FILE": secret_target["nextcloud_db_password"],
                "NEXTCLOUD_ADMIN_USER": "admin",
                "NEXTCLOUD_ADMIN_PASSWORD_FILE": secret_target["nextcloud_admin_password"],
                "NEXTCLOUD_TRUSTED_DOMAINS": env["ARCLINK_FILES_HOST"],
                "REDIS_HOST": "nextcloud-redis",
            },
            volumes=[
                {"source": roots["nextcloud_html"], "target": "/var/www/html"},
                {"source": roots["vault"], "target": CONTAINER_VAULT_DIR},
            ],
            labels=labels["files"],
            depends_on=["nextcloud-db", "nextcloud-redis"],
            secrets=[
                {"source": "nextcloud_db_password", "target": secret_target["nextcloud_db_password"]},
                {"source": "nextcloud_admin_password", "target": secret_target["nextcloud_admin_password"]},
            ],
        ),
        "code-server": _service(
            image="${ALMANAC_AGENT_CODE_SERVER_IMAGE:-docker.io/codercom/code-server:4.116.0}",
            command=[
                "sh",
                "-lc",
                f"PASSWORD=\"$(cat {secret_target['code_server_password']})\" "
                "exec code-server --bind-addr 0.0.0.0:8080 /workspace",
            ],
            environment={
                "ARCLINK_DEPLOYMENT_ID": deployment_id,
            },
            volumes=[{"source": roots["code_workspace"], "target": "/workspace"}],
            labels=labels["code"],
            secrets=[{"source": "code_server_password", "target": secret_target["code_server_password"]}],
        ),
        "notification-delivery": _service(
            image=app_image,
            command=["./bin/docker-job-loop.sh", "notification-delivery", "60", "./bin/almanac-notification-delivery.sh"],
            environment=env,
        ),
        "health-watch": _service(
            image=app_image,
            command=["./bin/docker-job-loop.sh", "health-watch", "300", "./bin/health-watch.sh"],
            environment=env,
        ),
        "managed-context-install": _service(
            image=app_image,
            command=["./bin/install-almanac-plugins.sh", env["HERMES_HOME"]],
            environment={
                "HERMES_HOME": env["HERMES_HOME"],
                "ARCLINK_DEPLOYMENT_ID": deployment_id,
            },
            volumes=[{"source": roots["hermes_home"], "target": CONTAINER_HERMES_HOME}],
        ),
    }


def validate_no_plaintext_secrets(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            validate_no_plaintext_secrets(child, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            validate_no_plaintext_secrets(child, path=f"{path}[{index}]")
        return
    if not isinstance(value, str):
        return

    text = value.strip()
    if not text:
        return
    path_requires_secret_ref = _SECRET_KEY_RE.search(path) is not None
    if path_requires_secret_ref and text.startswith("/run/secrets/"):
        return
    if path_requires_secret_ref and path.endswith(".source") and re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", text):
        return
    if path_requires_secret_ref and not text.startswith("secret://"):
        raise ArcLinkSecretReferenceError(f"plaintext-looking secret value in provisioning output at {path}")
    if _PLAINTEXT_SECRET_RE.search(text):
        raise ArcLinkSecretReferenceError(f"plaintext-looking secret value in provisioning output at {path}")


def render_arclink_provisioning_intent(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    base_domain: str = "",
    edge_target: str = "",
    state_root_base: str = "/arcdata/deployments",
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    deployment = _load_deployment(conn, deployment_id)
    metadata = _json_loads(str(deployment.get("metadata_json") or "{}"))
    user = _load_user(conn, str(deployment["user_id"]))
    clean_base_domain = str(base_domain or deployment.get("base_domain") or metadata.get("base_domain") or "localhost").strip()
    clean_edge_target = str(edge_target or metadata.get("edge_target") or f"edge.{clean_base_domain}").strip()
    prefix = str(deployment["prefix"])
    roots = render_arclink_state_roots(deployment_id=deployment_id, prefix=prefix, state_root_base=state_root_base)
    hostnames = arclink_hostnames(prefix, clean_base_domain)
    dns_records = desired_arclink_dns_records(prefix=prefix, base_domain=clean_base_domain, target=clean_edge_target)
    labels = render_traefik_dynamic_labels(prefix=prefix, base_domain=clean_base_domain)
    secret_refs = _render_secret_refs(deployment_id, metadata)
    compose_secrets = _render_compose_secrets(secret_refs)
    deployment_env = {
        "ARCLINK_DEPLOYMENT_ID": deployment_id,
        "ARCLINK_USER_ID": str(deployment["user_id"]),
        "ARCLINK_PREFIX": prefix,
        "ARCLINK_BASE_DOMAIN": clean_base_domain,
        "ARCLINK_DASHBOARD_HOST": hostnames["dashboard"],
        "ARCLINK_FILES_HOST": hostnames["files"],
        "ARCLINK_CODE_HOST": hostnames["code"],
        "ARCLINK_HERMES_HOST": hostnames["hermes"],
        "ARCLINK_PRIMARY_PROVIDER": primary_provider(env),
        "ARCLINK_CHUTES_BASE_URL": chutes_base_url(env),
        "ARCLINK_CHUTES_DEFAULT_MODEL": chutes_default_model(env),
        "ARCLINK_MODEL_REASONING_DEFAULT": model_reasoning_default(env),
        "ARCLINK_CHUTES_API_KEY_REF": secret_refs["chutes_api_key"],
        "NEXTCLOUD_ADMIN_PASSWORD_REF": secret_refs["nextcloud_admin_password"],
        "NEXTCLOUD_DB_PASSWORD_REF": secret_refs["nextcloud_db_password"],
        "CODE_SERVER_PASSWORD_REF": secret_refs["code_server_password"],
        "HERMES_HOME": CONTAINER_HERMES_HOME,
        "VAULT_DIR": CONTAINER_VAULT_DIR,
        "QMD_STATE_DIR": CONTAINER_QMD_STATE_DIR,
        "QMD_COLLECTION_NAME": f"vault-{deployment_id}",
        "ALMANAC_MEMORY_SYNTH_ENABLED": "auto",
        "ALMANAC_MEMORY_SYNTH_STATE_DIR": CONTAINER_MEMORY_STATE_DIR,
        "TELEGRAM_BOT_TOKEN_REF": secret_refs["telegram_bot_token"],
        "DISCORD_BOT_TOKEN_REF": secret_refs["discord_bot_token"],
        "NOTION_TOKEN_REF": secret_refs["notion_token"],
    }
    services = _render_services(
        deployment_id=deployment_id,
        prefix=prefix,
        roots=roots,
        env=deployment_env,
        labels=labels,
        compose_secrets=compose_secrets,
    )
    entitlement_state = arclink_deployment_entitlement_state(conn, deployment_id=deployment_id)
    executable = arclink_deployment_can_provision(conn, deployment_id=deployment_id)
    ssh = build_arclink_ssh_access_record(
        username=f"arc-{prefix}",
        hostname=f"ssh-{prefix}.{clean_base_domain}",
    )
    intent = {
        "deployment": {
            "deployment_id": deployment_id,
            "user_id": str(deployment["user_id"]),
            "user_email": str(user.get("email") or ""),
            "prefix": prefix,
            "base_domain": clean_base_domain,
            "status": str(deployment["status"]),
        },
        "state_roots": roots,
        "environment": deployment_env,
        "secret_refs": secret_refs,
        "compose": {"services": services, "secrets": compose_secrets},
        "runtime_resolution": {
            "stock_image_file_env": {
                "nextcloud-db": ["POSTGRES_PASSWORD_FILE"],
                "nextcloud": ["POSTGRES_PASSWORD_FILE", "NEXTCLOUD_ADMIN_PASSWORD_FILE"],
            },
            "entrypoint_file_resolver": {
                "code-server": {
                    "env_var": "PASSWORD",
                    "source_file": compose_secrets["code_server_password"]["target"],
                }
            },
            "app_ref_resolver_required": [
                name
                for name in (
                    "chutes_api_key",
                    "telegram_bot_token",
                    "discord_bot_token",
                    "notion_token",
                )
                if secret_refs.get(name)
            ],
        },
        "dns": {
            role: {
                "hostname": record.hostname,
                "record_type": record.record_type,
                "target": record.target,
                "proxied": record.proxied,
            }
            for role, record in dns_records.items()
        },
        "traefik": {"labels": {role: dict(role_labels) for role, role_labels in labels.items()}},
        "access": {
            "urls": _host_urls(hostnames),
            "ssh": {
                "strategy": ssh.strategy,
                "username": ssh.username,
                "hostname": ssh.hostname,
                "command_hint": ssh.command_hint,
            },
        },
        "execution": {
            "ready": executable,
            "blocked_reason": "" if executable else "entitlement_required",
            "entitlement_state": entitlement_state,
        },
    }
    validate_no_plaintext_secrets(intent)
    return intent


def _record_health_placeholders(conn: sqlite3.Connection, *, deployment_id: str) -> None:
    for service_name in ARCLINK_PROVISIONING_SERVICE_NAMES:
        upsert_arclink_service_health(
            conn,
            deployment_id=deployment_id,
            service_name=service_name,
            status="planned",
            detail={"source": "arclink_provisioning_dry_run"},
        )


def _update_job_metadata(conn: sqlite3.Connection, *, job_id: str, metadata: Mapping[str, Any]) -> None:
    conn.execute(
        """
        UPDATE arclink_provisioning_jobs
        SET metadata_json = ?
        WHERE job_id = ?
        """,
        (json.dumps(dict(metadata), sort_keys=True), job_id),
    )
    conn.commit()


def render_arclink_provisioning_dry_run(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    base_domain: str = "",
    edge_target: str = "",
    state_root_base: str = "/arcdata/deployments",
    idempotency_key: str = "",
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    key = idempotency_key or f"arclink:provisioning:dry-run:{deployment_id}"
    job = _ensure_job(
        conn,
        deployment_id=deployment_id,
        job_kind="docker_dry_run",
        idempotency_key=key,
        metadata={"deployment_id": deployment_id, "dry_run": True},
    )
    job_id = str(job["job_id"])
    status = str(job["status"] or "")
    try:
        if status == "cancelled":
            raise ArcLinkProvisioningError("cancelled ArcLink provisioning jobs cannot be resumed")
        if status == "succeeded":
            intent = render_arclink_provisioning_intent(
                conn,
                deployment_id=deployment_id,
                base_domain=base_domain,
                edge_target=edge_target,
                state_root_base=state_root_base,
                env=env,
            )
            return {"job_id": job_id, "intent": intent}
        if status == "failed":
            transition_arclink_provisioning_job(conn, job_id=job_id, status="queued")
            status = "queued"
        if status == "queued":
            transition_arclink_provisioning_job(conn, job_id=job_id, status="running")
        intent = render_arclink_provisioning_intent(
            conn,
            deployment_id=deployment_id,
            base_domain=base_domain,
            edge_target=edge_target,
            state_root_base=state_root_base,
            env=env,
        )
        _record_health_placeholders(conn, deployment_id=deployment_id)
        _update_job_metadata(
            conn,
            job_id=job_id,
            metadata={
                "deployment_id": deployment_id,
                "dry_run": True,
                "service_count": len(intent["compose"]["services"]),
                "ready_for_execution": bool(intent["execution"]["ready"]),
            },
        )
        transition_arclink_provisioning_job(conn, job_id=job_id, status="succeeded")
        _append_timeline_event_once(
            conn,
            deployment_id=deployment_id,
            job_id=job_id,
            phase="rendered",
            metadata={"service_count": len(intent["compose"]["services"])},
        )
        if intent["execution"]["ready"]:
            _append_timeline_event_once(
                conn,
                deployment_id=deployment_id,
                job_id=job_id,
                phase="ready_for_execution",
                metadata={"entitlement_state": intent["execution"]["entitlement_state"]},
            )
        return {"job_id": job_id, "intent": intent}
    except Exception as exc:
        current = conn.execute("SELECT status FROM arclink_provisioning_jobs WHERE job_id = ?", (job_id,)).fetchone()
        terminal = current is not None and str(current["status"] or "") in {"succeeded", "cancelled"}
        if current is not None and not terminal:
            transition_arclink_provisioning_job(conn, job_id=job_id, status="failed", error=str(exc))
            _append_timeline_event_once(
                conn,
                deployment_id=deployment_id,
                job_id=job_id,
                phase="failed",
                metadata={"error": str(exc)},
            )
        raise


def plan_arclink_provisioning_rollback(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    failed_job_id: str,
    idempotency_key: str = "",
) -> dict[str, Any]:
    failed = conn.execute(
        "SELECT * FROM arclink_provisioning_jobs WHERE job_id = ? AND deployment_id = ?",
        (failed_job_id, deployment_id),
    ).fetchone()
    if failed is None:
        raise KeyError(failed_job_id)
    if str(failed["status"] or "") != "failed":
        raise ArcLinkProvisioningError("rollback planning requires a failed provisioning job")
    key = idempotency_key or f"arclink:provisioning:rollback:{deployment_id}:{failed_job_id}"
    job = _ensure_job(
        conn,
        deployment_id=deployment_id,
        job_kind="docker_rollback_plan",
        idempotency_key=key,
        metadata={"deployment_id": deployment_id, "failed_job_id": failed_job_id},
    )
    plan = {
        "job_id": str(job["job_id"]),
        "deployment_id": deployment_id,
        "failed_job_id": failed_job_id,
        "actions": (
            "stop_rendered_services",
            "remove_unhealthy_containers",
            "preserve_state_roots",
            "leave_secret_refs_for_manual_review",
        ),
    }
    _update_job_metadata(conn, job_id=str(job["job_id"]), metadata=plan)
    _append_timeline_event_once(
        conn,
        deployment_id=deployment_id,
        job_id=str(job["job_id"]),
        phase="rollback_requested",
        metadata={"failed_job_id": failed_job_id},
    )
    return plan
