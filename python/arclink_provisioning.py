#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from typing import Any, Mapping

from arclink_control import (
    append_arclink_event,
    arclink_deployment_can_provision,
    arclink_deployment_entitlement_state,
    create_arclink_provisioning_job,
    transition_arclink_provisioning_job,
    upsert_arclink_service_health,
)
from arclink_access import build_arclink_ssh_access_record
from arclink_adapters import arclink_access_urls, arclink_hostnames, arclink_tailscale_hostnames
from arclink_ingress import desired_arclink_ingress_records, render_traefik_dynamic_labels
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
    "notion-webhook",
    "notification-delivery",
    "health-watch",
    "managed-context-install",
)

CONTAINER_HERMES_HOME = "/home/arclink/.hermes"
CONTAINER_QMD_STATE_DIR = "/home/arclink/.qmd"
CONTAINER_VAULT_DIR = "/srv/vault"
CONTAINER_MEMORY_STATE_DIR = "/srv/memory"

_SECRET_KEY_RE = re.compile(r"(secret|token|api[_-]?key|password|credential|client[_-]?secret)", re.I)
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
        "notion_webhook_secret": _secret_ref(
            metadata,
            "notion_webhook_secret_ref",
            f"secret://arclink/notion/{deployment_id}/webhook-secret",
        ),
        "stripe_customer": str(metadata.get("stripe_customer_ref") or "").strip(),
        "cloudflare_tunnel": str(metadata.get("cloudflare_tunnel_token_ref") or "").strip(),
    }


def _host_urls(hostnames: Mapping[str, str]) -> dict[str, str]:
    return {role: f"https://{hostname}" for role, hostname in hostnames.items()}


def _clean_ingress_mode(value: str | None) -> str:
    mode = str(value or "domain").strip().lower()
    if mode not in {"domain", "tailscale"}:
        raise ArcLinkProvisioningError("ArcLink ingress mode must be domain or tailscale")
    return mode


def _clean_tailscale_strategy(value: str | None) -> str:
    strategy = str(value or "path").strip().lower()
    if strategy not in {"path", "subdomain"}:
        raise ArcLinkProvisioningError("ArcLink Tailscale host strategy must be path or subdomain")
    return strategy


def _notion_callback_path(prefix: str, *, ingress_mode: str, tailscale_host_strategy: str) -> str:
    clean_prefix = str(prefix or "").strip().lower()
    if ingress_mode == "tailscale" and tailscale_host_strategy == "path":
        return f"/u/{clean_prefix}/notion/webhook"
    return "/notion/webhook"


def _notion_callback_url(access_urls: Mapping[str, str]) -> str:
    dashboard_url = str(access_urls.get("dashboard") or "").rstrip("/")
    if not dashboard_url:
        raise ArcLinkProvisioningError("ArcLink dashboard URL is required for Notion callback intent")
    return f"{dashboard_url}/notion/webhook"


def _render_notion_webhook_labels(
    *,
    prefix: str,
    hostname: str,
    callback_path: str,
    strip_prefix: str = "",
    port: int = 8283,
    docker_network: str = "",
    priority: int = 200,
) -> dict[str, str]:
    router = f"arclink-{prefix}-notion-webhook"
    clean_path = str(callback_path or "/notion/webhook").strip()
    if not clean_path.startswith("/"):
        clean_path = f"/{clean_path}"
    labels = {
        "traefik.enable": "true",
        f"traefik.http.routers.{router}.rule": f"Host(`{hostname}`) && PathPrefix(`{clean_path}`)",
        f"traefik.http.routers.{router}.entrypoints": "web",
        f"traefik.http.services.{router}.loadbalancer.server.port": str(int(port)),
    }
    clean_network = str(docker_network or "").strip()
    if clean_network:
        labels["traefik.docker.network"] = clean_network
    if int(priority or 0) > 0:
        labels[f"traefik.http.routers.{router}.priority"] = str(int(priority))
    clean_strip = str(strip_prefix or "").strip()
    if clean_strip:
        if not clean_strip.startswith("/"):
            clean_strip = f"/{clean_strip}"
        middleware = f"{router}-strip-user-prefix"
        labels[f"traefik.http.routers.{router}.middlewares"] = middleware
        labels[f"traefik.http.middlewares.{middleware}.stripprefix.prefixes"] = clean_strip
    return labels


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


def _control_network_alias(prefix: str, service_name: str) -> str:
    clean_prefix = re.sub(r"[^a-z0-9-]+", "-", str(prefix or "").strip().lower()).strip("-")
    clean_service = re.sub(r"[^a-z0-9-]+", "-", str(service_name or "").strip().lower()).strip("-")
    return f"arclink-{clean_prefix}-{clean_service}"


def _control_network(prefix: str, service_name: str) -> dict[str, Any]:
    return {
        "default": {},
        "arclink-control": {
            "aliases": [_control_network_alias(prefix, service_name)],
        },
    }


def _service(
    *,
    image: str,
    command: list[str],
    entrypoint: list[str] | None = None,
    environment: Mapping[str, str],
    volumes: list[dict[str, str]] | None = None,
    labels: Mapping[str, str] | None = None,
    depends_on: list[str] | None = None,
    secrets: list[dict[str, str]] | None = None,
    deploy: Mapping[str, Any] | None = None,
    healthcheck: Mapping[str, str] | None = None,
    networks: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    svc: dict[str, Any] = {
        "image": image,
        "command": command,
        "environment": dict(environment),
        "volumes": list(volumes or []),
        "labels": dict(labels or {}),
        "depends_on": list(depends_on or []),
        "secrets": list(secrets or []),
    }
    if entrypoint:
        svc["entrypoint"] = list(entrypoint)
    if deploy:
        svc["deploy"] = dict(deploy)
    if healthcheck:
        svc["healthcheck"] = dict(healthcheck)
    if networks:
        svc["networks"] = dict(networks)
    return svc


def _resource_limit(memory: str, cpus: str) -> dict[str, Any]:
    return {"resources": {"limits": {"memory": memory, "cpus": cpus}}}


ARCLINK_DEFAULT_RESOURCE_LIMITS: dict[str, dict[str, Any]] = {
    "dashboard":               _resource_limit("256M", "0.5"),
    "hermes-gateway":          _resource_limit("512M", "1.0"),
    "hermes-dashboard":        _resource_limit("256M", "0.5"),
    "qmd-mcp":                 _resource_limit("512M", "1.0"),
    "vault-watch":             _resource_limit("128M", "0.25"),
    "memory-synth":            _resource_limit("256M", "0.5"),
    "nextcloud-db":            _resource_limit("512M", "0.5"),
    "nextcloud-redis":         _resource_limit("128M", "0.25"),
    "nextcloud":               _resource_limit("512M", "1.0"),
    "code-server":             _resource_limit("1G",   "1.0"),
    "notion-webhook":          _resource_limit("128M", "0.25"),
    "notification-delivery":   _resource_limit("128M", "0.25"),
    "health-watch":            _resource_limit("128M", "0.25"),
    "managed-context-install": _resource_limit("128M", "0.25"),
}


ARCLINK_DEFAULT_HEALTHCHECKS: dict[str, dict[str, str]] = {
    "nextcloud-db":    {"test": "pg_isready -U nextcloud", "interval": "30s", "timeout": "5s", "retries": "3"},
    "nextcloud-redis": {"test": "redis-cli ping", "interval": "30s", "timeout": "5s", "retries": "3"},
    "nextcloud":       {"test": "curl -f http://localhost/status.php || exit 1", "interval": "60s", "timeout": "10s", "retries": "3"},
    "code-server":     {"test": "curl -f http://localhost:8080/healthz || exit 1", "interval": "60s", "timeout": "5s", "retries": "3"},
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
    app_image = "${ARCLINK_DOCKER_IMAGE:-arclink/app:local}"
    secret_target = {name: str(spec["target"]) for name, spec in compose_secrets.items()}

    _limits = ARCLINK_DEFAULT_RESOURCE_LIMITS.get
    _hc = ARCLINK_DEFAULT_HEALTHCHECKS.get

    return {
        "dashboard": _service(
            image=app_image,
            command=["./bin/arclink-dashboard-placeholder.sh"],
            environment=env,
            labels=labels["dashboard"],
            deploy=_limits("dashboard"),
            networks=_control_network(prefix, "dashboard"),
        ),
        "hermes-gateway": _service(
            image=app_image,
            command=["hermes", "gateway", "run", "--replace"],
            environment=env,
            volumes=[{"source": roots["hermes_home"], "target": CONTAINER_HERMES_HOME}],
            depends_on=["qmd-mcp", "managed-context-install"],
            deploy=_limits("hermes-gateway"),
        ),
        "hermes-dashboard": _service(
            image=app_image,
            command=["hermes", "dashboard", "--host", "0.0.0.0", "--port", "3210", "--insecure"],
            environment=env,
            volumes=[{"source": roots["hermes_home"], "target": CONTAINER_HERMES_HOME}],
            labels=labels["hermes"],
            depends_on=["managed-context-install"],
            deploy=_limits("hermes-dashboard"),
            networks=_control_network(prefix, "hermes"),
        ),
        "qmd-mcp": _service(
            image=app_image,
            command=["./bin/qmd-daemon.sh"],
            environment=env,
            volumes=[
                {"source": roots["vault"], "target": CONTAINER_VAULT_DIR},
                {"source": roots["qmd"], "target": CONTAINER_QMD_STATE_DIR},
            ],
            deploy=_limits("qmd-mcp"),
        ),
        "vault-watch": _service(
            image=app_image,
            command=["./bin/vault-watch.sh"],
            environment=env,
            volumes=[{"source": roots["vault"], "target": CONTAINER_VAULT_DIR}],
            depends_on=["qmd-mcp"],
            deploy=_limits("vault-watch"),
        ),
        "memory-synth": _service(
            image=app_image,
            command=["./bin/docker-job-loop.sh", "memory-synth", "1800", "./bin/memory-synth.sh"],
            environment=env,
            volumes=[{"source": roots["memory"], "target": CONTAINER_MEMORY_STATE_DIR}],
            depends_on=["qmd-mcp"],
            deploy=_limits("memory-synth"),
        ),
        "nextcloud-db": _service(
            image="${ARCLINK_POSTGRES_IMAGE:-docker.io/library/postgres}:${ARCLINK_POSTGRES_TAG:-16-alpine}",
            command=[],
            environment={
                "POSTGRES_DB": f"nextcloud_{deployment_id}",
                "POSTGRES_USER": "nextcloud",
                "POSTGRES_PASSWORD_FILE": secret_target["nextcloud_db_password"],
            },
            volumes=[{"source": roots["nextcloud_db"], "target": "/var/lib/postgresql/data"}],
            secrets=[{"source": "nextcloud_db_password", "target": secret_target["nextcloud_db_password"]}],
            deploy=_limits("nextcloud-db"),
            healthcheck=_hc("nextcloud-db"),
        ),
        "nextcloud-redis": _service(
            image="${ARCLINK_REDIS_IMAGE:-docker.io/library/redis}:${ARCLINK_REDIS_TAG:-7-alpine}",
            command=["redis-server", "--appendonly", "yes"],
            environment={},
            volumes=[{"source": roots["nextcloud_redis"], "target": "/data"}],
            deploy=_limits("nextcloud-redis"),
            healthcheck=_hc("nextcloud-redis"),
        ),
        "nextcloud": _service(
            image="${ARCLINK_NEXTCLOUD_IMAGE:-docker.io/library/nextcloud}:${ARCLINK_NEXTCLOUD_TAG:-31-apache}",
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
            deploy=_limits("nextcloud"),
            healthcheck=_hc("nextcloud"),
            networks=_control_network(prefix, "nextcloud"),
        ),
        "code-server": _service(
            image="${ARCLINK_AGENT_CODE_SERVER_IMAGE:-docker.io/codercom/code-server:4.116.0}",
            entrypoint=["/bin/sh", "-lc"],
            command=[
                f"PASSWORD=\"$(cat {secret_target['code_server_password']})\" "
                "exec code-server --bind-addr 0.0.0.0:8080 /workspace",
            ],
            environment={
                "ARCLINK_DEPLOYMENT_ID": deployment_id,
            },
            volumes=[{"source": roots["code_workspace"], "target": "/workspace"}],
            labels=labels["code"],
            secrets=[{"source": "code_server_password", "target": secret_target["code_server_password"]}],
            deploy=_limits("code-server"),
            healthcheck=_hc("code-server"),
            networks=_control_network(prefix, "code"),
        ),
        "notion-webhook": _service(
            image=app_image,
            command=["./bin/arclink-notion-webhook.sh", "--host", "0.0.0.0", "--port", "8283"],
            environment=env,
            volumes=[{"source": roots["vault"], "target": CONTAINER_VAULT_DIR}],
            labels=labels["notion"],
            secrets=[
                {"source": "notion_webhook_secret", "target": secret_target["notion_webhook_secret"]},
            ] if "notion_webhook_secret" in secret_target else [],
            deploy=_limits("notion-webhook"),
            networks=_control_network(prefix, "notion"),
        ),
        "notification-delivery": _service(
            image=app_image,
            command=["./bin/docker-job-loop.sh", "notification-delivery", "60", "./bin/arclink-notification-delivery.sh"],
            environment=env,
            deploy=_limits("notification-delivery"),
        ),
        "health-watch": _service(
            image=app_image,
            command=["./bin/docker-job-loop.sh", "health-watch", "300", "./bin/health-watch.sh"],
            environment=env,
            deploy=_limits("health-watch"),
        ),
        "managed-context-install": _service(
            image=app_image,
            command=["./bin/install-arclink-plugins.sh", "/home/arclink/arclink", env["HERMES_HOME"]],
            environment={
                "HERMES_HOME": env["HERMES_HOME"],
                "ARCLINK_DEPLOYMENT_ID": deployment_id,
            },
            volumes=[{"source": roots["hermes_home"], "target": CONTAINER_HERMES_HOME}],
            deploy=_limits("managed-context-install"),
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
    ingress_mode: str = "",
    tailscale_dns_name: str = "",
    tailscale_host_strategy: str = "",
    tailscale_notion_path: str = "",
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    deployment = _load_deployment(conn, deployment_id)
    metadata = _json_loads(str(deployment.get("metadata_json") or "{}"))
    user = _load_user(conn, str(deployment["user_id"]))
    source_env = dict(env or {})
    clean_ingress_mode = _clean_ingress_mode(
        ingress_mode or str(source_env.get("ARCLINK_INGRESS_MODE") or "") or str(metadata.get("ingress_mode") or "") or "domain"
    )
    clean_tailscale_dns_name = str(
        tailscale_dns_name
        or source_env.get("ARCLINK_TAILSCALE_DNS_NAME")
        or metadata.get("tailscale_dns_name")
        or ""
    ).strip().lower().strip(".")
    clean_tailscale_strategy = _clean_tailscale_strategy(
        tailscale_host_strategy
        or str(source_env.get("ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY") or "")
        or str(metadata.get("tailscale_host_strategy") or "")
        or "path"
    )
    clean_base_domain = str(base_domain or deployment.get("base_domain") or metadata.get("base_domain") or "localhost").strip()
    if clean_ingress_mode == "tailscale":
        clean_base_domain = clean_tailscale_dns_name or clean_base_domain
        if not clean_tailscale_dns_name:
            clean_tailscale_dns_name = clean_base_domain
    clean_edge_target = str(edge_target or metadata.get("edge_target") or f"edge.{clean_base_domain}").strip()
    control_network_name = str(
        source_env.get("ARCLINK_CONTROL_DOCKER_NETWORK")
        or source_env.get("ARCLINK_DOCKER_NETWORK")
        or "arclink_default"
    ).strip()
    prefix = str(deployment["prefix"])
    roots = render_arclink_state_roots(deployment_id=deployment_id, prefix=prefix, state_root_base=state_root_base)
    if clean_ingress_mode == "tailscale":
        hostnames = arclink_tailscale_hostnames(prefix, clean_tailscale_dns_name, strategy=clean_tailscale_strategy)
    else:
        hostnames = arclink_hostnames(prefix, clean_base_domain)
    dns_records = desired_arclink_ingress_records(
        prefix=prefix,
        base_domain=clean_base_domain,
        target=clean_edge_target,
        ingress_mode=clean_ingress_mode,
        tailscale_dns_name=clean_tailscale_dns_name,
        tailscale_host_strategy=clean_tailscale_strategy,
    )
    labels = render_traefik_dynamic_labels(
        prefix=prefix,
        base_domain=clean_base_domain,
        ingress_mode=clean_ingress_mode,
        tailscale_dns_name=clean_tailscale_dns_name,
        tailscale_host_strategy=clean_tailscale_strategy,
        docker_network=control_network_name,
    )
    secret_refs = _render_secret_refs(deployment_id, metadata)
    compose_secrets = _render_compose_secrets(secret_refs)
    access_urls = arclink_access_urls(
        prefix=prefix,
        base_domain=clean_base_domain,
        ingress_mode=clean_ingress_mode,
        tailscale_dns_name=clean_tailscale_dns_name,
        tailscale_host_strategy=clean_tailscale_strategy,
    )
    notion_callback_path = _notion_callback_path(
        prefix,
        ingress_mode=clean_ingress_mode,
        tailscale_host_strategy=clean_tailscale_strategy,
    )
    notion_callback_url = _notion_callback_url(access_urls)
    labels = dict(labels)
    labels["notion"] = _render_notion_webhook_labels(
        prefix=prefix,
        hostname=hostnames["dashboard"],
        callback_path=notion_callback_path,
        strip_prefix=f"/u/{prefix}" if clean_ingress_mode == "tailscale" and clean_tailscale_strategy == "path" else "",
        docker_network=control_network_name,
    )
    deployment_env = {
        "ARCLINK_DEPLOYMENT_ID": deployment_id,
        "ARCLINK_USER_ID": str(deployment["user_id"]),
        "ARCLINK_PREFIX": prefix,
        "ARCLINK_BASE_DOMAIN": clean_base_domain,
        "ARCLINK_INGRESS_MODE": clean_ingress_mode,
        "ARCLINK_TAILSCALE_DNS_NAME": clean_tailscale_dns_name,
        "ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY": clean_tailscale_strategy,
        "ARCLINK_TAILSCALE_NOTION_PATH": str(
            tailscale_notion_path
            or source_env.get("ARCLINK_TAILSCALE_NOTION_PATH")
            or source_env.get("TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH")
            or "/notion/webhook"
        ),
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
        "QMD_INDEX_NAME": f"vault-{deployment_id}",
        "QMD_COLLECTION_NAME": f"vault-{deployment_id}",
        "ARCLINK_MEMORY_SYNTH_ENABLED": "auto",
        "ARCLINK_MEMORY_SYNTH_STATE_DIR": CONTAINER_MEMORY_STATE_DIR,
        "TELEGRAM_BOT_TOKEN_REF": secret_refs["telegram_bot_token"],
        "DISCORD_BOT_TOKEN_REF": secret_refs["discord_bot_token"],
        "NOTION_TOKEN_REF": secret_refs["notion_token"],
        "NOTION_WEBHOOK_SECRET_REF": secret_refs["notion_webhook_secret"],
        "ARCLINK_NOTION_CALLBACK_URL": notion_callback_url,
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
        hostname=clean_tailscale_dns_name if clean_ingress_mode == "tailscale" else f"ssh-{prefix}.{clean_base_domain}",
        strategy="tailscale_direct_ssh" if clean_ingress_mode == "tailscale" else "cloudflare_access_tcp",
    )
    intent = {
        "deployment": {
            "deployment_id": deployment_id,
            "user_id": str(deployment["user_id"]),
            "user_email": str(user.get("email") or ""),
            "prefix": prefix,
            "base_domain": clean_base_domain,
            "ingress_mode": clean_ingress_mode,
            "status": str(deployment["status"]),
        },
        "state_roots": roots,
        "environment": deployment_env,
        "secret_refs": secret_refs,
        "compose": {
            "services": services,
            "secrets": compose_secrets,
            "networks": {
                "arclink-control": {
                    "external": True,
                    "name": control_network_name,
                }
            },
        },
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
                    "notion_webhook_secret",
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
            "urls": {**access_urls, "notion": notion_callback_url},
            "ssh": {
                "strategy": ssh.strategy,
                "username": ssh.username,
                "hostname": ssh.hostname,
                "command_hint": ssh.command_hint,
            },
        },
        "integrations": {
            "notion": {
                "mode": "per_deployment",
                "callback_url": notion_callback_url,
                "callback_path": notion_callback_path,
                "token_ref": secret_refs["notion_token"],
                "secret_ref": secret_refs["notion_webhook_secret"],
            }
        },
        "execution": {
            "ready": executable,
            "blocked_reason": "" if executable else "entitlement_required",
            "entitlement_state": entitlement_state,
            "ingress_mode": clean_ingress_mode,
            "dns_provider": "cloudflare" if clean_ingress_mode == "domain" else "tailscale",
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
    ingress_mode: str = "",
    tailscale_dns_name: str = "",
    tailscale_host_strategy: str = "",
    tailscale_notion_path: str = "",
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
                ingress_mode=ingress_mode,
                tailscale_dns_name=tailscale_dns_name,
                tailscale_host_strategy=tailscale_host_strategy,
                tailscale_notion_path=tailscale_notion_path,
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
            ingress_mode=ingress_mode,
            tailscale_dns_name=tailscale_dns_name,
            tailscale_host_strategy=tailscale_host_strategy,
            tailscale_notion_path=tailscale_notion_path,
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
