#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Mapping

from arclink_control import (
    append_arclink_audit,
    append_arclink_event,
    arclink_deployment_can_provision,
    arclink_deployment_entitlement_state,
    create_arclink_provisioning_job,
    transition_arclink_provisioning_job,
    upsert_arclink_service_health,
    utc_now_iso,
)
from arclink_access import build_arclink_ssh_access_record
from arclink_adapters import arclink_access_urls, arclink_hostnames, arclink_tailscale_hostnames
from arclink_ingress import desired_arclink_ingress_records, render_traefik_dynamic_labels
from arclink_onboarding import clean_arclink_agent_name, clean_arclink_agent_title, default_arclink_agent_profile
from arclink_product import chutes_base_url, chutes_default_model, model_reasoning_default, primary_provider
from arclink_secrets_regex import (
    contains_secret_material,
    is_run_secret_path,
    is_secret_ref,
    path_allows_compose_secret_source,
    path_requires_secret_ref,
)


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
    "notion-webhook",
    "notification-delivery",
    "arclink-wrapped",
    "health-watch",
    "fleet-share-sync",
    "managed-context-install",
)

CONTAINER_HERMES_HOME = "/home/arclink/.hermes"
CONTAINER_QMD_STATE_DIR = "/home/arclink/.qmd"
CONTAINER_VAULT_DIR = "/srv/vault"
CONTAINER_MEMORY_STATE_DIR = "/srv/memory"
CONTAINER_CODE_WORKSPACE_DIR = "/workspace"
CONTAINER_LINKED_RESOURCES_DIR = "/linked-resources"
CONTAINER_FLEET_SHARED_DIR = "/fleet-shared"
CONTAINER_FLEET_SHARE_HUB_DIR = "/fleet-share-hub.git"
IDENTITY_STATE_FILENAME = "arclink-identity-context.json"


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


def _deployment_theme_profile(metadata: Mapping[str, Any]) -> dict[str, str]:
    try:
        index = int(str(metadata.get("bundle_agent_index") or metadata.get("agent_index") or "1"))
    except (TypeError, ValueError):
        index = 1
    plan_id = str(metadata.get("selected_plan_id") or metadata.get("plan_id") or "").strip()
    profile = default_arclink_agent_profile(index, plan_id=plan_id)
    return {
        "dashboard_theme": str(metadata.get("dashboard_theme") or profile.get("dashboard_theme") or "arclink").strip(),
        "theme_label": str(metadata.get("theme_label") or profile.get("theme_label") or "ArcLink Signal Orange").strip(),
        "theme_accent_hex": str(metadata.get("theme_accent_hex") or profile.get("theme_accent_hex") or "#FB5005").strip(),
    }


def _safe_segment(value: str) -> str:
    segment = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip(".-")
    if not segment:
        raise ArcLinkProvisioningError("ArcLink provisioning path segment cannot be empty")
    return segment


def _clean_git_ref(value: str, *, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ArcLinkProvisioningError(f"ArcLink {label} cannot be empty")
    if text.startswith("-") or any(char in text for char in "\x00\r\n"):
        raise ArcLinkProvisioningError(f"ArcLink {label} contains unsafe git reference characters")
    return text


def _is_remote_git_ref(value: str) -> bool:
    text = str(value or "").strip()
    return "://" in text or "@" in text.split("/", 1)[0]


def _postgres_db_name(*, prefix: str, deployment_id: str) -> str:
    clean = re.sub(r"[^a-z0-9_]+", "_", str(deployment_id or "").strip().lower()).strip("_")
    if not clean:
        digest = hashlib.sha256(str(deployment_id or "").encode("utf-8")).hexdigest()[:12]
        clean = f"deployment_{digest}"
    name = f"{prefix}_{clean}"
    if len(name) <= 63:
        return name
    digest = hashlib.sha256(str(deployment_id or "").encode("utf-8")).hexdigest()[:12]
    keep = max(1, 63 - len(prefix) - len(digest) - 2)
    return f"{prefix}_{clean[:keep].rstrip('_')}_{digest}"


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


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".arclink-identity-", suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8", closefd=True) as handle:
            handle.write(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n")
            handle.flush()
        Path(tmp_path).replace(path)
        path.chmod(0o600)
    except BaseException:
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass
        raise


def project_arclink_deployment_identity_context(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    source: str = "agent_identity_update",
) -> dict[str, Any]:
    """Refresh an already-provisioned Pod's local managed-context identity file.

    The control node only writes when the deployment metadata points at a local
    Hermes home that already exists. Remote fleet projection is intentionally
    left to a worker/migration transport instead of creating lookalike local
    paths on the control node.
    """
    deployment = _load_deployment(conn, deployment_id)
    user = _load_user(conn, str(deployment["user_id"]))
    metadata = _json_loads(str(deployment.get("metadata_json") or "{}"))
    roots = metadata.get("state_roots") if isinstance(metadata.get("state_roots"), Mapping) else {}
    hermes_home = str((roots or {}).get("hermes_home") or "").strip()
    if not hermes_home:
        return {"status": "skipped", "reason": "state_roots_missing"}
    hermes_home_path = Path(hermes_home)
    if not hermes_home_path.is_dir():
        return {"status": "skipped", "reason": "local_hermes_home_missing", "hermes_home": hermes_home}
    identity_path = hermes_home_path / "state" / IDENTITY_STATE_FILENAME
    existing: dict[str, Any] = {}
    if identity_path.exists():
        try:
            parsed = json.loads(identity_path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                existing = dict(parsed)
        except (OSError, json.JSONDecodeError):
            existing = {}
    payload = dict(existing)
    agent_label = str(deployment.get("agent_name") or "").strip() or str(deployment.get("prefix") or "").strip()
    agent_title = str(deployment.get("agent_title") or user.get("agent_title") or "").strip()
    theme_profile = _deployment_theme_profile(metadata)
    payload.update(
        {
            "agent_label": agent_label or "your Hermes Agent",
            "agent_title": agent_title,
            "agent_personality": str(metadata.get("agent_personality") or payload.get("agent_personality") or "").strip(),
            "dashboard_theme": str(metadata.get("dashboard_theme") or payload.get("dashboard_theme") or theme_profile["dashboard_theme"]).strip(),
            "theme_label": str(metadata.get("theme_label") or payload.get("theme_label") or theme_profile["theme_label"]).strip(),
            "theme_accent_hex": str(metadata.get("theme_accent_hex") or payload.get("theme_accent_hex") or theme_profile["theme_accent_hex"]).strip(),
            "deployment_id": str(deployment["deployment_id"]),
            "user_id": str(deployment["user_id"]),
            "user_name": str(user.get("display_name") or payload.get("user_name") or "").strip(),
            "identity_source": str(source or "agent_identity_update"),
        }
    )
    academy_training = metadata.get("academy_training") if isinstance(metadata.get("academy_training"), Mapping) else {}
    if academy_training:
        payload.update(
            {
                "academy_status": str(academy_training.get("status") or "").strip(),
                "academy_summary": str(academy_training.get("summary") or "").strip(),
                "academy_role_title": str(academy_training.get("agent_title") or academy_training.get("role_title") or "").strip(),
                "academy_manifest_id": str(academy_training.get("manifest_id") or "").strip(),
                "academy_source_count": str(academy_training.get("source_count") or "").strip(),
                "academy_graduation_status": str(academy_training.get("graduation_status") or "").strip(),
            }
        )
    recipe_row = conn.execute(
        """
        SELECT soul_overlay_json
        FROM arclink_crew_recipes
        WHERE user_id = ? AND status = 'active'
        ORDER BY applied_at DESC, recipe_id DESC
        LIMIT 1
        """,
        (str(deployment["user_id"]),),
    ).fetchone()
    if recipe_row is not None:
        recipe_overlay = _json_loads(str(recipe_row["soul_overlay_json"] or "{}"))
        if isinstance(recipe_overlay, Mapping):
            for key in (
                "crew_preset",
                "crew_capacity",
                "captain_role",
                "captain_mission",
                "captain_treatment",
                "applied_at",
                "crew_recipe_text",
            ):
                value = recipe_overlay.get(key)
                if value is not None:
                    payload[key] = value
    _atomic_write_json(identity_path, payload)
    return {
        "status": "projected",
        "identity_state_file": str(identity_path),
        "agent_label": payload["agent_label"],
        "agent_title": payload["agent_title"],
    }


def update_arclink_deployment_identity(
    conn: sqlite3.Connection,
    *,
    deployment: Mapping[str, Any],
    agent_name: str | None = None,
    agent_title: str | None = None,
    actor_id: str = "",
    reason: str = "updated Agent identity",
    channel: str = "",
    projection_source: str = "agent_identity_update",
) -> dict[str, Any]:
    deployment_row = dict(deployment)
    deployment_id = str(deployment_row.get("deployment_id") or "").strip()
    user_id = str(deployment_row.get("user_id") or actor_id or "").strip()
    if not deployment_id or not user_id:
        raise ArcLinkProvisioningError("Agent identity update requires a deployment")

    old_name = str(deployment_row.get("agent_name") or "").strip()
    old_title = str(deployment_row.get("agent_title") or "").strip()
    clean_name = old_name if agent_name is None else clean_arclink_agent_name(agent_name, required=True)
    clean_title = old_title if agent_title is None else clean_arclink_agent_title(agent_title, required=True)
    clean_reason = str(reason or "updated Agent identity").strip()
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE arclink_deployments
        SET agent_name = ?, agent_title = ?, updated_at = ?
        WHERE deployment_id = ? AND user_id = ?
        """,
        (clean_name, clean_title, now, deployment_id, user_id),
    )
    audit_metadata: dict[str, Any] = {
        "old_name": old_name,
        "new_name": clean_name,
        "old_title": old_title,
        "new_title": clean_title,
    }
    clean_channel = str(channel or "").strip()
    if clean_channel:
        audit_metadata["channel"] = clean_channel
    append_arclink_audit(
        conn,
        action=f"agent_identity_renamed:{deployment_id}",
        actor_id=str(actor_id or user_id).strip(),
        target_kind="deployment",
        target_id=deployment_id,
        reason=clean_reason,
        metadata=audit_metadata,
        commit=False,
    )
    projection = project_arclink_deployment_identity_context(
        conn,
        deployment_id=deployment_id,
        source=projection_source,
    )
    event_metadata: dict[str, Any] = {
        "user_id": user_id,
        "agent_name": clean_name,
        "agent_title": clean_title,
        "identity_projection": projection,
    }
    if clean_channel:
        event_metadata["channel"] = clean_channel
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=deployment_id,
        event_type="agent_identity_updated",
        metadata=event_metadata,
        commit=False,
    )
    conn.commit()
    row = conn.execute("SELECT * FROM arclink_deployments WHERE deployment_id = ?", (deployment_id,)).fetchone()
    return {
        "deployment": dict(row) if row is not None else deployment_row,
        "identity_projection": projection,
    }


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
        "linked_resources": f"{root}/linked-resources",
        "hermes_home": f"{root}/state/hermes-home",
        "qmd": f"{root}/state/qmd",
        "memory": f"{root}/state/memory",
        "nextcloud": f"{root}/state/nextcloud",
        "nextcloud_html": f"{root}/state/nextcloud/html",
        "nextcloud_db": f"{root}/state/nextcloud/db",
        "nextcloud_redis": f"{root}/state/nextcloud/redis",
        "code_workspace": f"{root}/workspace",
        "fleet_shared": f"{root}/fleet-shared",
        "logs": f"{root}/logs",
    }


def _secret_ref(metadata: Mapping[str, Any], key: str, default: str) -> str:
    value = str(metadata.get(key) or "").strip()
    return value or default


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _allow_direct_chutes(env: Mapping[str, str] | None) -> bool:
    return _truthy((env or {}).get("ARCLINK_ALLOW_DIRECT_CHUTES_IN_ARCPODS"))


def _control_network_mode(env: Mapping[str, str] | None, metadata: Mapping[str, Any] | None = None) -> str:
    source = env or {}
    meta = metadata or {}
    value = str(
        meta.get("control_network_mode")
        or meta.get("arcpod_control_network_mode")
        or source.get("ARCLINK_ARCPOD_CONTROL_NETWORK_MODE")
        or source.get("ARCLINK_DEPLOYMENT_CONTROL_NETWORK_MODE")
        or "local"
    ).strip().lower()
    if value in {"", "local", "docker", "control", "shared", "on", "1", "true"}:
        return "local"
    if value in {"remote", "tailnet", "tailscale", "none", "off", "0", "false"}:
        return "remote"
    raise ArcLinkProvisioningError("ArcLink ArcPod control network mode must be local or remote")


def _control_public_base_url(env: Mapping[str, str] | None) -> str:
    source = env or {}
    private_value = str(
        source.get("ARCLINK_CONTROL_PRIVATE_BASE_URL")
        or source.get("ARCLINK_WIREGUARD_CONTROL_URL")
        or source.get("ARCLINK_PRIVATE_MESH_CONTROL_URL")
        or ""
    ).strip().rstrip("/")
    if private_value:
        return private_value
    private_host = str(
        source.get("ARCLINK_PRIVATE_DNS_NAME")
        or source.get("ARCLINK_WIREGUARD_DNS_NAME")
        or source.get("ARCLINK_PRIVATE_MESH_DNS_NAME")
        or ""
    ).strip().lower().strip(".")
    if private_host:
        port = str(
            source.get("ARCLINK_CONTROL_PRIVATE_HTTPS_PORT")
            or source.get("ARCLINK_WIREGUARD_HTTPS_PORT")
            or source.get("ARCLINK_PRIVATE_MESH_HTTPS_PORT")
            or source.get("ARCLINK_TAILSCALE_HTTPS_PORT")
            or "443"
        ).strip()
        suffix = "" if port in {"", "443"} else f":{port}"
        return f"https://{private_host}{suffix}"
    value = str(
        source.get("ARCLINK_CONTROL_PUBLIC_BASE_URL")
        or source.get("ARCLINK_TAILSCALE_CONTROL_URL")
        or ""
    ).strip().rstrip("/")
    if value:
        return value
    tailnet_host = str(source.get("ARCLINK_TAILSCALE_DNS_NAME") or "").strip().lower().strip(".")
    if tailnet_host:
        port = str(source.get("ARCLINK_TAILSCALE_HTTPS_PORT") or "443").strip()
        suffix = "" if port in {"", "443"} else f":{port}"
        return f"https://{tailnet_host}{suffix}"
    return ""


def _looks_like_control_docker_url(value: str) -> bool:
    text = str(value or "").strip().lower()
    return "://control-" in text or "://control_" in text or "://control." in text


def _append_control_path(base_url: str, path: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    clean_path = "/" + str(path or "").strip().lstrip("/")
    if not base:
        return ""
    if base.endswith(clean_path):
        return base
    return f"{base}{clean_path}"


def _append_control_api_path(base_url: str, path: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    clean_path = "/" + str(path or "").strip().lstrip("/")
    if not base:
        return ""
    if base.endswith(clean_path):
        return base
    if base.endswith("/api/v1"):
        return f"{base}{clean_path.removeprefix('/api/v1')}"
    if base.endswith("/api"):
        return f"{base}/v1{clean_path.removeprefix('/api/v1')}"
    return f"{base}{clean_path}"


def _llm_router_base_url(env: Mapping[str, str] | None, *, control_network_mode: str = "local") -> str:
    source = env or {}
    public_value = str(source.get("ARCLINK_LLM_ROUTER_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if public_value:
        return public_value
    base_value = str(source.get("ARCLINK_LLM_ROUTER_BASE_URL") or "").strip().rstrip("/")
    if base_value and (control_network_mode != "remote" or not _looks_like_control_docker_url(base_value)):
        return base_value
    if control_network_mode == "remote":
        control_base = _control_public_base_url(source)
        if control_base:
            return _append_control_path(control_base, "/v1")
        raise ArcLinkProvisioningError(
            "Remote ArcPod rendering requires ARCLINK_LLM_ROUTER_PUBLIC_BASE_URL "
            "or ARCLINK_CONTROL_PRIVATE_BASE_URL/ARCLINK_WIREGUARD_CONTROL_URL "
            "so pods do not depend on control-node Docker DNS"
        )
    return "http://control-llm-router:8090/v1"


def _share_request_broker_url(env: Mapping[str, str] | None, *, control_network_mode: str = "local") -> str:
    source = env or {}
    explicit = str(source.get("ARCLINK_SHARE_REQUEST_BROKER_URL") or "").strip().rstrip("/")
    if explicit:
        if control_network_mode == "remote" and _looks_like_control_docker_url(explicit):
            explicit = ""
        else:
            return _append_control_api_path(explicit, "/api/v1/user/share-grants/broker")
    api_base = str(source.get("ARCLINK_API_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if control_network_mode == "remote":
        if not api_base:
            maybe_internal = str(source.get("ARCLINK_API_INTERNAL_URL") or "").strip().rstrip("/")
            if maybe_internal and not _looks_like_control_docker_url(maybe_internal):
                api_base = maybe_internal
        if not api_base:
            api_base = _control_public_base_url(source)
        if api_base:
            return _append_control_api_path(api_base, "/api/v1/user/share-grants/broker")
        raise ArcLinkProvisioningError(
            "Remote ArcPod rendering requires ARCLINK_SHARE_REQUEST_BROKER_URL, "
            "ARCLINK_API_PUBLIC_BASE_URL, or ARCLINK_CONTROL_PRIVATE_BASE_URL/"
            "ARCLINK_WIREGUARD_CONTROL_URL"
        )
    value = str(source.get("ARCLINK_API_INTERNAL_URL") or "http://control-api:8900").strip().rstrip("/")
    return _append_control_api_path(value or "http://control-api:8900", "/api/v1/user/share-grants/broker")


def _fleet_share_hub_host_ref(env: Mapping[str, str] | None, *, user_id: str, control_network_mode: str = "local") -> str:
    source = env or {}
    clean_user = _safe_segment(user_id)
    template = str(source.get("ARCLINK_FLEET_SHARE_HUB_URL") or "").strip()
    if template:
        ref = template.replace("{user}", clean_user) if "{user}" in template else f"{template.rstrip('/')}/{clean_user}/fleet-shared.git"
        clean_ref = _clean_git_ref(ref, label="fleet-share hub ref")
        if control_network_mode == "remote" and not _is_remote_git_ref(clean_ref):
            raise ArcLinkProvisioningError(
                "Remote ArcPod rendering requires ARCLINK_FLEET_SHARE_HUB_URL to be a remote git ref "
                "so Captain shared folders do not split across worker-local disks"
            )
        return clean_ref
    if control_network_mode == "remote":
        raise ArcLinkProvisioningError(
            "Remote ArcPod rendering requires ARCLINK_FLEET_SHARE_HUB_URL with a remote git ref "
            "for the Captain shared folder hub"
        )
    root = str(source.get("ARCLINK_FLEET_SHARE_HUB_ROOT") or "/arcdata/captains").strip().rstrip("/") or "/arcdata/captains"
    return _clean_git_ref(f"{root}/{clean_user}/fleet-shared.git", label="fleet-share hub ref")


def _fleet_share_hub_container_ref(host_ref: str) -> str:
    clean_ref = _clean_git_ref(host_ref, label="fleet-share hub ref")
    if _is_remote_git_ref(clean_ref):
        return clean_ref
    return CONTAINER_FLEET_SHARE_HUB_DIR


def dashboard_password_secret_ref(*, deployment_id: str, user_id: str, metadata: Mapping[str, Any]) -> str:
    explicit = str(metadata.get("dashboard_password_ref") or "").strip()
    if explicit:
        return explicit
    clean_user = _safe_segment(user_id)
    if clean_user:
        return f"secret://arclink/dashboard/users/{clean_user}/password"
    return f"secret://arclink/dashboard/{deployment_id}/password"


def dashboard_sso_secret_ref(*, deployment_id: str, user_id: str, metadata: Mapping[str, Any]) -> str:
    explicit = str(metadata.get("dashboard_sso_secret_ref") or "").strip()
    if explicit:
        return explicit
    clean_user = _safe_segment(user_id)
    if clean_user:
        return f"secret://arclink/dashboard/users/{clean_user}/sso-session-secret"
    return f"secret://arclink/dashboard/{deployment_id}/sso-session-secret"


def _render_secret_refs(
    deployment_id: str,
    user_id: str,
    metadata: Mapping[str, Any],
    *,
    direct_chutes: bool = False,
) -> dict[str, str]:
    provider_key = {
        "chutes_api_key": _secret_ref(metadata, "chutes_secret_ref", f"secret://arclink/chutes/{deployment_id}")
    } if direct_chutes else {
        "llm_router_api_key": _secret_ref(
            metadata,
            "llm_router_api_key_ref",
            f"secret://arclink/llm-router/{deployment_id}/api-key",
        )
    }
    return {
        **provider_key,
        "dashboard_password": dashboard_password_secret_ref(deployment_id=deployment_id, user_id=user_id, metadata=metadata),
        "dashboard_sso_secret": dashboard_sso_secret_ref(deployment_id=deployment_id, user_id=user_id, metadata=metadata),
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
        "telegram_bot_token": str(metadata.get("telegram_bot_token_ref") or "").strip(),
        "discord_bot_token": str(metadata.get("discord_bot_token_ref") or "").strip(),
        "notion_token": str(metadata.get("notion_token_ref") or "").strip(),
        "notion_webhook_secret": _secret_ref(
            metadata,
            "notion_webhook_secret_ref",
            f"secret://arclink/notion/{deployment_id}/webhook-secret",
        ),
        "share_request_broker_token": _secret_ref(
            metadata,
            "share_request_broker_token_ref",
            f"secret://arclink/share-request-broker/{deployment_id}/token",
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
    if strategy == "subdomain":
        raise ArcLinkProvisioningError(
            "Tailscale MagicDNS/Funnel does not support ArcLink dynamic per-Captain "
            "subdomains; use path routing or domain ingress with wildcard DNS"
        )
    if strategy != "path":
        raise ArcLinkProvisioningError("ArcLink Tailscale host strategy must be path")
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


def _notion_callback_url_for_ingress(
    access_urls: Mapping[str, str],
    *,
    prefix: str,
    ingress_mode: str,
    tailscale_dns_name: str,
    tailscale_host_strategy: str,
) -> str:
    if ingress_mode == "tailscale" and tailscale_host_strategy == "path":
        host = str(tailscale_dns_name or "").strip().lower().strip(".")
        if not host:
            raise ArcLinkProvisioningError("ArcLink Tailscale DNS name is required for Notion callback intent")
        clean_prefix = str(prefix or "").strip().lower()
        return f"https://{host}/u/{clean_prefix}/notion/webhook"
    return _notion_callback_url(access_urls)


def _clean_tailnet_service_ports(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    ports: dict[str, int] = {}
    for role in ("hermes",):
        try:
            port = int(value.get(role) or 0)
        except (TypeError, ValueError):
            continue
        if 0 < port < 65536:
            ports[role] = port
    return ports


def _int_or_zero(value: Any) -> int:
    try:
        return int(str(value or "0"))
    except (TypeError, ValueError):
        return 0


def _crew_dashboard_links(
    conn: sqlite3.Connection,
    *,
    current_deployment_id: str,
    user_id: str,
    base_domain: str,
    ingress_mode: str,
    tailscale_dns_name: str,
    tailscale_host_strategy: str,
    current_metadata: Mapping[str, Any],
    limit: int = 24,
) -> list[dict[str, Any]]:
    current_session_id = str(current_metadata.get("onboarding_session_id") or "").strip()
    current_primary = str(current_metadata.get("bundle_primary_deployment_id") or current_deployment_id).strip()
    rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT deployment_id, user_id, prefix, base_domain, agent_name, agent_title,
                   status, metadata_json, created_at
            FROM arclink_deployments
            WHERE user_id = ?
            ORDER BY created_at, deployment_id
            """,
            (user_id,),
        ).fetchall()
    ]
    links: list[dict[str, Any]] = []
    for row in rows:
        deployment_id = str(row.get("deployment_id") or "").strip()
        try:
            metadata = _json_loads(str(row.get("metadata_json") or "{}"))
        except Exception:
            metadata = {}
        row_session_id = str(metadata.get("onboarding_session_id") or "").strip()
        row_primary = str(metadata.get("bundle_primary_deployment_id") or deployment_id).strip()
        if current_session_id:
            if deployment_id != current_deployment_id and row_session_id != current_session_id:
                continue
        elif current_primary:
            if deployment_id != current_deployment_id and row_primary != current_primary:
                continue
        status = str(row.get("status") or "").strip()
        if status in {"archived", "deleted", "retired"}:
            continue
        prefix = str(row.get("prefix") or "").strip()
        if not prefix:
            continue
        stored_urls = metadata.get("access_urls") if isinstance(metadata.get("access_urls"), Mapping) else {}
        if stored_urls:
            urls = {str(role): str(url).strip() for role, url in dict(stored_urls).items() if str(url or "").strip()}
        else:
            row_base_domain = str(row.get("base_domain") or base_domain).strip() or base_domain
            row_tailnet_ports = _clean_tailnet_service_ports(metadata.get("tailnet_service_ports"))
            row_tailscale_dns_name = str(metadata.get("tailscale_dns_name") or tailscale_dns_name).strip().lower().strip(".")
            row_tailscale_strategy = str(metadata.get("tailscale_host_strategy") or tailscale_host_strategy).strip().lower()
            urls = arclink_access_urls(
                prefix=prefix,
                base_domain=row_base_domain,
                ingress_mode=str(metadata.get("ingress_mode") or ingress_mode),
                tailscale_dns_name=row_tailscale_dns_name,
                tailscale_host_strategy=row_tailscale_strategy,
                tailnet_service_ports=row_tailnet_ports,
            )
        label = str(row.get("agent_name") or "").strip() or f"Hermes Agent {_int_or_zero(metadata.get('bundle_agent_index')) or len(links) + 1}"
        theme = _deployment_theme_profile(metadata)
        links.append(
            {
                "deployment_id": deployment_id,
                "label": label,
                "title": str(row.get("agent_title") or "").strip(),
                "status": status,
                "url": str(urls.get("hermes") or urls.get("dashboard") or "").strip(),
                "dashboard_url": str(urls.get("dashboard") or "").strip(),
                "hermes_url": str(urls.get("hermes") or "").strip(),
                "current": deployment_id == current_deployment_id,
                "bundle_agent_index": _int_or_zero(metadata.get("bundle_agent_index")),
                "bundle_agent_count": _int_or_zero(metadata.get("bundle_agent_count")),
                "theme_label": theme["theme_label"],
            }
        )
    links.sort(key=lambda item: (_int_or_zero(item.get("bundle_agent_index")) or 9999, str(item.get("label") or ""), str(item.get("deployment_id") or "")))
    return links[: max(1, int(limit or 24))]


def _url_hostport(value: str) -> str:
    text = str(value or "").strip()
    if not text.startswith("https://"):
        return ""
    hostport, _, path = text.removeprefix("https://").partition("/")
    if path.strip("/"):
        return ""
    return hostport


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
        f"traefik.http.routers.{router}.service": router,
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


def _service_networks(prefix: str, service_name: str, *, use_control_network: bool) -> dict[str, Any] | None:
    if not use_control_network:
        return None
    return _control_network(prefix, service_name)


def _service(
    *,
    image: str,
    command: list[str],
    entrypoint: list[str] | None = None,
    environment: Mapping[str, str],
    volumes: list[dict[str, str]] | None = None,
    ports: list[str] | None = None,
    labels: Mapping[str, str] | None = None,
    depends_on: list[str] | Mapping[str, Any] | None = None,
    secrets: list[dict[str, str]] | None = None,
    deploy: Mapping[str, Any] | None = None,
    healthcheck: Mapping[str, str] | None = None,
    networks: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(depends_on, Mapping):
        rendered_depends_on: list[str] | dict[str, Any] = dict(depends_on)
    else:
        rendered_depends_on = list(depends_on or [])
    svc: dict[str, Any] = {
        "image": image,
        "command": command,
        "environment": dict(environment),
        "volumes": list(volumes or []),
        "labels": dict(labels or {}),
        "depends_on": rendered_depends_on,
        "secrets": list(secrets or []),
    }
    if ports:
        svc["ports"] = list(ports)
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
    "notion-webhook":          _resource_limit("128M", "0.25"),
    "notification-delivery":   _resource_limit("128M", "0.25"),
    "arclink-wrapped":         _resource_limit("128M", "0.25"),
    "health-watch":            _resource_limit("128M", "0.25"),
    "fleet-share-sync":        _resource_limit("128M", "0.25"),
    "managed-context-install": _resource_limit("128M", "0.25"),
}


ARCLINK_DEFAULT_HEALTHCHECKS: dict[str, dict[str, str]] = {
    "nextcloud-db":    {"test": "pg_isready -U nextcloud", "interval": "30s", "timeout": "5s", "retries": "3"},
    "nextcloud-redis": {"test": "redis-cli ping", "interval": "30s", "timeout": "5s", "retries": "3"},
    "nextcloud":       {"test": "curl -f http://localhost/status.php || exit 1", "interval": "60s", "timeout": "10s", "retries": "3"},
}


def _render_services(
    *,
    deployment_id: str,
    prefix: str,
    roots: Mapping[str, str],
    env: Mapping[str, str],
    labels: Mapping[str, Mapping[str, str]],
    compose_secrets: Mapping[str, Mapping[str, str]],
    fleet_share_hub_host_ref: str = "",
    tailnet_service_ports: Mapping[str, int] | None = None,
    use_control_network: bool = True,
) -> dict[str, dict[str, Any]]:
    app_image = "${ARCLINK_DOCKER_IMAGE:-arclink/app:local}"
    secret_target = {name: str(spec["target"]) for name, spec in compose_secrets.items()}
    provider_secret_name = "chutes_api_key" if "chutes_api_key" in secret_target else "llm_router_api_key"
    nextcloud_db_name = _postgres_db_name(prefix="nextcloud", deployment_id=deployment_id)
    memory_volume = {"source": roots["memory"], "target": CONTAINER_MEMORY_STATE_DIR}
    vault_volume = {"source": roots["vault"], "target": CONTAINER_VAULT_DIR}
    workspace_volume = {"source": roots["code_workspace"], "target": CONTAINER_CODE_WORKSPACE_DIR}
    linked_resources_volume = {
        "source": roots["linked_resources"],
        "target": CONTAINER_LINKED_RESOURCES_DIR,
    }
    fleet_shared_volume = {
        "source": roots["fleet_shared"],
        "target": CONTAINER_FLEET_SHARED_DIR,
    }
    fleet_share_hub_volume = None
    if fleet_share_hub_host_ref and not _is_remote_git_ref(fleet_share_hub_host_ref):
        fleet_share_hub_volume = {
            "source": fleet_share_hub_host_ref,
            "target": CONTAINER_FLEET_SHARE_HUB_DIR,
        }
    fleet_share_sync_env = {
        key: str(env[key])
        for key in (
            "ARCLINK_DEPLOYMENT_ID",
            "ARCLINK_USER_ID",
            "ARCLINK_PREFIX",
            "ARCLINK_FLEET_SHARE_HUB_URL",
            "ARCLINK_FLEET_SHARED_ROOT",
        )
        if key in env
    }
    fleet_share_sync_volumes = [fleet_shared_volume]
    if fleet_share_hub_volume is not None:
        fleet_share_sync_volumes.append(fleet_share_hub_volume)
    hermes_host_ports: list[str] = []
    if (
        str(env.get("ARCLINK_INGRESS_MODE") or "").strip().lower() == "tailscale"
        and str(env.get("ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY") or "").strip().lower() == "path"
    ):
        hermes_tailnet_port = int(dict(tailnet_service_ports or {}).get("hermes") or 0)
        if 0 < hermes_tailnet_port < 65536:
            hermes_host_ports.append(f"127.0.0.1:{hermes_tailnet_port}:3210")

    _limits = ARCLINK_DEFAULT_RESOURCE_LIMITS.get
    _hc = ARCLINK_DEFAULT_HEALTHCHECKS.get
    installer_complete_depends_on = {"managed-context-install": {"condition": "service_completed_successfully"}}

    return {
        "dashboard": _service(
            image=app_image,
            command=["./bin/arclink-dashboard-placeholder.sh"],
            environment=env,
            volumes=[vault_volume, memory_volume],
            labels=labels["dashboard"],
            deploy=_limits("dashboard"),
            networks=_service_networks(prefix, "dashboard", use_control_network=use_control_network),
        ),
        "hermes-gateway": _service(
            image=app_image,
            command=["hermes", "gateway", "run", "--replace"],
            environment=env,
            volumes=[
                {"source": roots["hermes_home"], "target": CONTAINER_HERMES_HOME},
                vault_volume,
                memory_volume,
                workspace_volume,
                linked_resources_volume,
                fleet_shared_volume,
            ],
            depends_on={
                "qmd-mcp": {"condition": "service_started"},
                "managed-context-install": {"condition": "service_completed_successfully"},
            },
            secrets=[{"source": provider_secret_name, "target": secret_target[provider_secret_name]}],
            deploy=_limits("hermes-gateway"),
            networks=_service_networks(prefix, "hermes-gateway", use_control_network=use_control_network),
        ),
        "hermes-dashboard": _service(
            image=app_image,
            command=["./bin/run-hermes-dashboard-proxy.sh"],
            environment=env,
            volumes=[
                {"source": roots["hermes_home"], "target": CONTAINER_HERMES_HOME},
                vault_volume,
                memory_volume,
                workspace_volume,
                linked_resources_volume,
                fleet_shared_volume,
            ],
            ports=hermes_host_ports,
            labels=labels["hermes"],
            depends_on=installer_complete_depends_on,
            secrets=[
                {"source": provider_secret_name, "target": secret_target[provider_secret_name]},
                {"source": "share_request_broker_token", "target": secret_target["share_request_broker_token"]},
            ],
            deploy=_limits("hermes-dashboard"),
            networks=_service_networks(prefix, "hermes", use_control_network=use_control_network),
        ),
        "qmd-mcp": _service(
            image=app_image,
            command=["./bin/qmd-daemon.sh"],
            environment=env,
            volumes=[
                vault_volume,
                {"source": roots["qmd"], "target": CONTAINER_QMD_STATE_DIR},
                memory_volume,
            ],
            deploy=_limits("qmd-mcp"),
        ),
        "vault-watch": _service(
            image=app_image,
            command=["./bin/vault-watch.sh"],
            environment=env,
            volumes=[vault_volume, memory_volume],
            depends_on=["qmd-mcp"],
            deploy=_limits("vault-watch"),
        ),
        "memory-synth": _service(
            image=app_image,
            command=["./bin/docker-job-loop.sh", "memory-synth", "1800", "./bin/memory-synth.sh"],
            environment=env,
            volumes=[
                vault_volume,
                memory_volume,
                linked_resources_volume,
                fleet_shared_volume,
            ],
            depends_on=["qmd-mcp"],
            deploy=_limits("memory-synth"),
        ),
        "nextcloud-db": _service(
            image="${ARCLINK_POSTGRES_IMAGE:-docker.io/library/postgres}:${ARCLINK_POSTGRES_TAG:-16-alpine}",
            command=[],
            environment={
                "POSTGRES_DB": nextcloud_db_name,
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
                "POSTGRES_DB": nextcloud_db_name,
                "POSTGRES_USER": "nextcloud",
                "POSTGRES_PASSWORD_FILE": secret_target["nextcloud_db_password"],
                "NEXTCLOUD_ADMIN_USER": "admin",
                "NEXTCLOUD_ADMIN_PASSWORD_FILE": secret_target["nextcloud_admin_password"],
                "NEXTCLOUD_TRUSTED_DOMAINS": env["ARCLINK_FILES_HOST"],
                "REDIS_HOST": "nextcloud-redis",
            },
            volumes=[
                {"source": roots["nextcloud_html"], "target": "/var/www/html"},
                vault_volume,
            ],
            labels=labels.get("files", {}),
            depends_on=["nextcloud-db", "nextcloud-redis"],
            secrets=[
                {"source": "nextcloud_db_password", "target": secret_target["nextcloud_db_password"]},
                {"source": "nextcloud_admin_password", "target": secret_target["nextcloud_admin_password"]},
            ],
            deploy=_limits("nextcloud"),
            healthcheck=_hc("nextcloud"),
            networks=_service_networks(prefix, "nextcloud", use_control_network=use_control_network),
        ),
        "notion-webhook": _service(
            image=app_image,
            command=["./bin/arclink-notion-webhook.sh", "--host", "0.0.0.0", "--port", "8283"],
            environment=env,
            volumes=[vault_volume, memory_volume],
            labels=labels["notion"],
            secrets=[
                {"source": "notion_webhook_secret", "target": secret_target["notion_webhook_secret"]},
            ] if "notion_webhook_secret" in secret_target else [],
            deploy=_limits("notion-webhook"),
            networks=_service_networks(prefix, "notion", use_control_network=use_control_network),
        ),
        "notification-delivery": _service(
            image=app_image,
            command=["./bin/docker-job-loop.sh", "notification-delivery", "5", "./bin/arclink-notification-delivery.sh"],
            environment=env,
            volumes=[vault_volume, memory_volume],
            deploy=_limits("notification-delivery"),
        ),
        "arclink-wrapped": _service(
            image=app_image,
            command=["./bin/docker-job-loop.sh", "arclink-wrapped", "300", "./bin/arclink-wrapped.sh", "--json"],
            environment=env,
            volumes=[vault_volume, memory_volume],
            deploy=_limits("arclink-wrapped"),
        ),
        "health-watch": _service(
            image=app_image,
            command=["./bin/docker-job-loop.sh", "health-watch", "300", "./bin/health-watch.sh"],
            environment=env,
            volumes=[vault_volume, memory_volume],
            deploy=_limits("health-watch"),
        ),
        "fleet-share-sync": _service(
            image=app_image,
            command=["./bin/docker-job-loop.sh", "fleet-share-sync", "120", "python3", "python/arclink_fleet_share.py", "sync-local"],
            environment=fleet_share_sync_env,
            volumes=fleet_share_sync_volumes,
            depends_on=installer_complete_depends_on,
            deploy=_limits("fleet-share-sync"),
        ),
        "managed-context-install": _service(
            image=app_image,
            command=["./bin/install-deployment-hermes-home.sh", "/home/arclink/arclink", env["HERMES_HOME"]],
            environment={
                "HERMES_HOME": env["HERMES_HOME"],
                "RUNTIME_DIR": "/opt/arclink/runtime",
                "VAULT_DIR": CONTAINER_VAULT_DIR,
                "ARCLINK_HERMES_DOCS_STATE_DIR": "/tmp/arclink-hermes-docs-src",
                "ARCLINK_HERMES_DOCS_VAULT_DIR": f"{CONTAINER_VAULT_DIR}/Agents_KB/hermes-agent-docs",
                "ARCLINK_DEPLOYMENT_ID": deployment_id,
                "ARCLINK_PREFIX": prefix,
                "ARCLINK_AGENT_NAME": env["ARCLINK_AGENT_NAME"],
                "ARCLINK_AGENT_TITLE": env["ARCLINK_AGENT_TITLE"],
                "ARCLINK_DASHBOARD_AGENT_LABEL": env["ARCLINK_DASHBOARD_AGENT_LABEL"],
                "ARCLINK_DASHBOARD_AGENT_TITLE": env["ARCLINK_DASHBOARD_AGENT_TITLE"],
                "ARCLINK_DASHBOARD_THEME": env["ARCLINK_DASHBOARD_THEME"],
                "ARCLINK_DASHBOARD_THEME_LABEL": env["ARCLINK_DASHBOARD_THEME_LABEL"],
                "ARCLINK_DASHBOARD_ACCENT_HEX": env["ARCLINK_DASHBOARD_ACCENT_HEX"],
                "ARCLINK_DASHBOARD_USERNAME": env["ARCLINK_DASHBOARD_USERNAME"],
                "ARCLINK_CAPTAIN_NAME": env["ARCLINK_CAPTAIN_NAME"],
                "ARCLINK_CAPTAIN_EMAIL": env["ARCLINK_CAPTAIN_EMAIL"],
                "ARCLINK_DASHBOARD_URL": env["ARCLINK_DASHBOARD_URL"],
                "ARCLINK_HERMES_URL": env["ARCLINK_HERMES_URL"],
                "ARCLINK_FILES_URL": env["ARCLINK_FILES_URL"],
                "ARCLINK_CODE_URL": env["ARCLINK_CODE_URL"],
                "ARCLINK_SHARE_REQUEST_BROKER_URL": env["ARCLINK_SHARE_REQUEST_BROKER_URL"],
                "ARCLINK_NOTION_CALLBACK_URL": env["ARCLINK_NOTION_CALLBACK_URL"],
                "ARCLINK_NOTION_ROOT_URL": env["ARCLINK_NOTION_ROOT_URL"],
                "ARCLINK_PRIMARY_PROVIDER": env["ARCLINK_PRIMARY_PROVIDER"],
                "ARCLINK_CHUTES_BASE_URL": env["ARCLINK_CHUTES_BASE_URL"],
                "ARCLINK_CHUTES_DEFAULT_MODEL": env["ARCLINK_CHUTES_DEFAULT_MODEL"],
                "ARCLINK_MODEL_REASONING_DEFAULT": env["ARCLINK_MODEL_REASONING_DEFAULT"],
                "ARCLINK_CHUTES_API_KEY_FILE": secret_target[provider_secret_name],
                "ARCLINK_DASHBOARD_PASSWORD_FILE": secret_target["dashboard_password"],
                "ARCLINK_DASHBOARD_SSO_SECRET_FILE": secret_target["dashboard_sso_secret"],
                "ARCLINK_DASHBOARD_SSO_SUBJECT": env["ARCLINK_USER_ID"],
                "ARCLINK_DASHBOARD_SSO_COOKIE_DOMAIN": env["ARCLINK_DASHBOARD_SSO_COOKIE_DOMAIN"],
                "ARCLINK_DASHBOARD_AUTH_REVOKED_BEFORE": env["ARCLINK_DASHBOARD_AUTH_REVOKED_BEFORE"],
                "ARCLINK_DASHBOARD_SESSION_REVOKED_BEFORE": env["ARCLINK_DASHBOARD_SESSION_REVOKED_BEFORE"],
                "ARCLINK_DASHBOARD_SSO_REVOKED_BEFORE": env["ARCLINK_DASHBOARD_SSO_REVOKED_BEFORE"],
                "ARCLINK_DASHBOARD_AUTH_REVOKED_AT": env["ARCLINK_DASHBOARD_AUTH_REVOKED_AT"],
                "ARCLINK_DASHBOARD_AUTH_REVOKED_BY": env["ARCLINK_DASHBOARD_AUTH_REVOKED_BY"],
                "ARCLINK_DASHBOARD_AUTH_REVOCATION_REASON": env["ARCLINK_DASHBOARD_AUTH_REVOCATION_REASON"],
                "ARCLINK_CREW_DASHBOARDS_JSON": env.get("ARCLINK_CREW_DASHBOARDS_JSON", "[]"),
            },
            volumes=[
                {"source": roots["hermes_home"], "target": CONTAINER_HERMES_HOME},
                vault_volume,
            ],
            secrets=[
                {"source": provider_secret_name, "target": secret_target[provider_secret_name]},
                {"source": "dashboard_password", "target": secret_target["dashboard_password"]},
                {"source": "dashboard_sso_secret", "target": secret_target["dashboard_sso_secret"]},
            ],
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
    requires_secret_ref = path_requires_secret_ref(path)
    if requires_secret_ref and is_run_secret_path(text):
        return
    if requires_secret_ref and path_allows_compose_secret_source(path, text):
        return
    if requires_secret_ref and not is_secret_ref(text):
        raise ArcLinkSecretReferenceError(f"plaintext-looking secret value in provisioning output at {path}")
    if contains_secret_material(text):
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
        or source_env.get("ARCLINK_PRIVATE_DNS_NAME")
        or source_env.get("ARCLINK_WIREGUARD_DNS_NAME")
        or source_env.get("ARCLINK_PRIVATE_MESH_DNS_NAME")
        or source_env.get("ARCLINK_TAILSCALE_DNS_NAME")
        or metadata.get("private_dns_name")
        or metadata.get("wireguard_dns_name")
        or metadata.get("private_mesh_dns_name")
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
    control_network_mode = _control_network_mode(source_env, metadata)
    use_control_network = control_network_mode == "local"
    control_network_name = str(
        source_env.get("ARCLINK_CONTROL_DOCKER_NETWORK")
        or source_env.get("ARCLINK_DOCKER_NETWORK")
        or "arclink_default"
    ).strip()
    prefix = str(deployment["prefix"])
    agent_name = str(deployment.get("agent_name") or "").strip()
    agent_title = str(deployment.get("agent_title") or user.get("agent_title") or "").strip()
    theme_profile = _deployment_theme_profile(metadata)
    dashboard_theme = theme_profile["dashboard_theme"]
    dashboard_theme_label = theme_profile["theme_label"]
    dashboard_accent_hex = theme_profile["theme_accent_hex"]
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
        docker_network=control_network_name if use_control_network else "",
    )
    direct_chutes = _allow_direct_chutes(env)
    provider_secret_name = "chutes_api_key" if direct_chutes else "llm_router_api_key"
    secret_refs = _render_secret_refs(
        deployment_id,
        str(deployment["user_id"]),
        metadata,
        direct_chutes=direct_chutes,
    )
    compose_secrets = _render_compose_secrets(secret_refs)
    tailnet_service_ports = _clean_tailnet_service_ports(metadata.get("tailnet_service_ports"))
    access_urls = arclink_access_urls(
        prefix=prefix,
        base_domain=clean_base_domain,
        ingress_mode=clean_ingress_mode,
        tailscale_dns_name=clean_tailscale_dns_name,
        tailscale_host_strategy=clean_tailscale_strategy,
        tailnet_service_ports=tailnet_service_ports,
    )
    crew_dashboard_links = _crew_dashboard_links(
        conn,
        current_deployment_id=deployment_id,
        user_id=str(deployment["user_id"]),
        base_domain=clean_base_domain,
        ingress_mode=clean_ingress_mode,
        tailscale_dns_name=clean_tailscale_dns_name,
        tailscale_host_strategy=clean_tailscale_strategy,
        current_metadata=metadata,
    )
    fleet_share_hub_host_ref = _fleet_share_hub_host_ref(
        source_env,
        user_id=str(deployment["user_id"]),
        control_network_mode=control_network_mode,
    )
    fleet_share_hub_container_ref = _fleet_share_hub_container_ref(fleet_share_hub_host_ref)
    notion_callback_path = _notion_callback_path(
        prefix,
        ingress_mode=clean_ingress_mode,
        tailscale_host_strategy=clean_tailscale_strategy,
    )
    notion_callback_url = _notion_callback_url_for_ingress(
        access_urls,
        prefix=prefix,
        ingress_mode=clean_ingress_mode,
        tailscale_dns_name=clean_tailscale_dns_name,
        tailscale_host_strategy=clean_tailscale_strategy,
    )
    labels = dict(labels)
    labels["notion"] = _render_notion_webhook_labels(
        prefix=prefix,
        hostname=hostnames["dashboard"],
        callback_path=notion_callback_path,
        strip_prefix=f"/u/{prefix}" if clean_ingress_mode == "tailscale" and clean_tailscale_strategy == "path" else "",
        docker_network=control_network_name if use_control_network else "",
    )
    llm_router_base_url = _llm_router_base_url(source_env, control_network_mode=control_network_mode)
    share_request_broker_url = _share_request_broker_url(source_env, control_network_mode=control_network_mode)
    deployment_env = {
        "ARCLINK_DEPLOYMENT_ID": deployment_id,
        "ARCLINK_ARCPOD_CONTROL_NETWORK_MODE": control_network_mode,
        "ARCLINK_USER_ID": str(deployment["user_id"]),
        "ARCLINK_PREFIX": prefix,
        "ARCLINK_AGENT_NAME": agent_name,
        "ARCLINK_AGENT_TITLE": agent_title,
        "ARCLINK_DASHBOARD_AGENT_LABEL": agent_name or prefix,
        "ARCLINK_DASHBOARD_AGENT_TITLE": agent_title,
        "ARCLINK_DASHBOARD_THEME": dashboard_theme,
        "ARCLINK_DASHBOARD_THEME_LABEL": dashboard_theme_label,
        "ARCLINK_DASHBOARD_ACCENT_HEX": dashboard_accent_hex,
        "ARCLINK_BASE_DOMAIN": clean_base_domain,
        "ARCLINK_INGRESS_MODE": clean_ingress_mode,
        "ARCLINK_PRIVATE_DNS_NAME": clean_tailscale_dns_name if clean_ingress_mode == "tailscale" else "",
        "ARCLINK_PRIVATE_MESH_DNS_NAME": clean_tailscale_dns_name if clean_ingress_mode == "tailscale" else "",
        "ARCLINK_TAILSCALE_DNS_NAME": clean_tailscale_dns_name,
        "ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY": clean_tailscale_strategy,
        "ARCLINK_TAILSCALE_NOTION_PATH": str(
            tailscale_notion_path
            or source_env.get("ARCLINK_TAILSCALE_NOTION_PATH")
            or source_env.get("TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH")
            or "/notion/webhook"
        ),
        "ARCLINK_BACKEND_ALLOWED_CIDRS": str(source_env.get("ARCLINK_BACKEND_ALLOWED_CIDRS") or "172.16.0.0/12"),
        "ARCLINK_DASHBOARD_HOST": hostnames["dashboard"],
        "ARCLINK_DASHBOARD_USERNAME": str(user.get("email") or deployment["user_id"]),
        "ARCLINK_DASHBOARD_MANAGED_LIFECYCLE_CONTROLS": "1",
        "ARCLINK_DASHBOARD_SSO_COOKIE_DOMAIN": clean_base_domain if clean_ingress_mode == "domain" and "." in clean_base_domain and clean_base_domain != "localhost" else "",
        "ARCLINK_DASHBOARD_AUTH_REVOKED_BEFORE": str(metadata.get("dashboard_auth_revoked_before") or "").strip(),
        "ARCLINK_DASHBOARD_SESSION_REVOKED_BEFORE": str(metadata.get("dashboard_session_revoked_before") or "").strip(),
        "ARCLINK_DASHBOARD_SSO_REVOKED_BEFORE": str(metadata.get("dashboard_sso_revoked_before") or "").strip(),
        "ARCLINK_DASHBOARD_AUTH_REVOKED_AT": str(metadata.get("dashboard_auth_revoked_at") or "").strip(),
        "ARCLINK_DASHBOARD_AUTH_REVOKED_BY": str(metadata.get("dashboard_auth_revoked_by") or "").strip(),
        "ARCLINK_DASHBOARD_AUTH_REVOCATION_REASON": str(metadata.get("dashboard_auth_revocation_reason") or "").strip(),
        "ARCLINK_CREW_DASHBOARDS_JSON": json.dumps(crew_dashboard_links, separators=(",", ":"), sort_keys=True),
        "ARCLINK_FILES_HOST": hostnames["files"],
        "ARCLINK_CODE_HOST": hostnames["code"],
        "ARCLINK_HERMES_HOST": hostnames["hermes"],
        "ARCLINK_DASHBOARD_URL": access_urls["dashboard"],
        "ARCLINK_FILES_URL": access_urls["files"],
        "ARCLINK_CODE_URL": access_urls["code"],
        "ARCLINK_HERMES_URL": access_urls["hermes"],
        "ARCLINK_SHARE_REQUEST_BROKER_URL": share_request_broker_url,
        "ARCLINK_SHARE_REQUEST_BROKER_TOKEN_FILE": compose_secrets["share_request_broker_token"]["target"],
        "ARCLINK_PRIMARY_PROVIDER": primary_provider(env),
        "ARCLINK_CHUTES_BASE_URL": chutes_base_url(env) if direct_chutes else llm_router_base_url,
        "ARCLINK_CHUTES_DEFAULT_MODEL": chutes_default_model(env),
        "ARCLINK_MODEL_REASONING_DEFAULT": model_reasoning_default(env),
        "ARCLINK_CHUTES_API_KEY_REF": secret_refs[provider_secret_name],
        "ARCLINK_CHUTES_API_KEY_FILE": compose_secrets[provider_secret_name]["target"],
        "ARCLINK_LLM_ROUTER_BASE_URL": llm_router_base_url,
        "ARCLINK_LLM_ROUTER_API_KEY_REF": secret_refs.get("llm_router_api_key", ""),
        "NEXTCLOUD_ADMIN_PASSWORD_REF": secret_refs["nextcloud_admin_password"],
        "NEXTCLOUD_DB_PASSWORD_REF": secret_refs["nextcloud_db_password"],
        "HERMES_HOME": CONTAINER_HERMES_HOME,
        "VAULT_DIR": CONTAINER_VAULT_DIR,
        "DRIVE_ROOT": CONTAINER_VAULT_DIR,
        "CODE_WORKSPACE_ROOT": CONTAINER_CODE_WORKSPACE_DIR,
        "DRIVE_LINKED_ROOT": CONTAINER_LINKED_RESOURCES_DIR,
        "CODE_LINKED_ROOT": CONTAINER_LINKED_RESOURCES_DIR,
        "ARCLINK_LINKED_RESOURCES_ROOT": CONTAINER_LINKED_RESOURCES_DIR,
        "ARCLINK_FLEET_SHARE_HUB_URL": fleet_share_hub_container_ref,
        "ARCLINK_FLEET_SHARED_ROOT": CONTAINER_FLEET_SHARED_DIR,
        "DRIVE_FLEET_SHARED_ROOT": CONTAINER_FLEET_SHARED_DIR,
        "CODE_FLEET_SHARED_ROOT": CONTAINER_FLEET_SHARED_DIR,
        "TERMINAL_WORKSPACE_ROOT": CONTAINER_CODE_WORKSPACE_DIR,
        "TERMINAL_TUI_COMMAND": "/opt/arclink/runtime/hermes-venv/bin/hermes",
        "ARCLINK_DRIVE_ROOT": CONTAINER_VAULT_DIR,
        "ARCLINK_CODE_WORKSPACE_ROOT": CONTAINER_CODE_WORKSPACE_DIR,
        "ARCLINK_TERMINAL_TUI_COMMAND": "/opt/arclink/runtime/hermes-venv/bin/hermes",
        "HERMES_TUI_DIR": "/opt/arclink/runtime/hermes-agent-src/ui-tui",
        "TELEGRAM_REACTIONS": "true",
        "DISCORD_REACTIONS": "true",
        "QMD_STATE_DIR": CONTAINER_QMD_STATE_DIR,
        "QMD_MCP_CONTAINER_PORT": "8181",
        "QMD_MCP_LOOPBACK_PORT": "18181",
        "QMD_INDEX_NAME": f"vault-{deployment_id}",
        "QMD_COLLECTION_NAME": f"vault-{deployment_id}",
        "ARCLINK_MEMORY_SYNTH_ENABLED": "auto",
        "ARCLINK_MEMORY_SYNTH_STATE_DIR": CONTAINER_MEMORY_STATE_DIR,
        "ARCLINK_MEMORY_SYNTH_MAX_CONTENT_HASH_BYTES": str(source_env.get("ARCLINK_MEMORY_SYNTH_MAX_CONTENT_HASH_BYTES") or "8388608"),
        "TELEGRAM_BOT_TOKEN_REF": secret_refs["telegram_bot_token"],
        "DISCORD_BOT_TOKEN_REF": secret_refs["discord_bot_token"],
        "NOTION_TOKEN_REF": secret_refs["notion_token"],
        "NOTION_WEBHOOK_SECRET_REF": secret_refs["notion_webhook_secret"],
        "ARCLINK_NOTION_CALLBACK_URL": notion_callback_url,
        "ARCLINK_NOTION_ROOT_URL": str(
            source_env.get("ARCLINK_SSOT_NOTION_ROOT_PAGE_URL")
            or source_env.get("ARCLINK_SSOT_NOTION_SPACE_URL")
            or source_env.get("ARCLINK_NOTION_INDEX_ROOTS")
            or ""
        ).strip(),
        "ARCLINK_CAPTAIN_NAME": str(user.get("display_name") or user.get("email") or deployment["user_id"]).strip(),
        "ARCLINK_CAPTAIN_EMAIL": str(user.get("email") or "").strip(),
        "ARCLINK_RUNTIME_ENV_CONFIG": "1",
        "ARCLINK_RUNTIME_CONFIG_FILE": "/tmp/arclink-runtime.env",
        "STATE_DIR": CONTAINER_MEMORY_STATE_DIR,
        "PUBLISHED_DIR": f"{CONTAINER_MEMORY_STATE_DIR}/published",
        "ARCLINK_DB_PATH": f"{CONTAINER_MEMORY_STATE_DIR}/arclink-control.sqlite3",
        "ARCLINK_NOTION_INDEX_DIR": f"{CONTAINER_MEMORY_STATE_DIR}/notion-index",
        "ARCLINK_NOTION_INDEX_MARKDOWN_DIR": f"{CONTAINER_MEMORY_STATE_DIR}/notion-index/markdown",
        "PDF_INGEST_DIR": f"{CONTAINER_MEMORY_STATE_DIR}/pdf-ingest",
        "PDF_INGEST_MARKDOWN_DIR": f"{CONTAINER_MEMORY_STATE_DIR}/pdf-ingest/markdown",
        "PDF_INGEST_STATUS_FILE": f"{CONTAINER_MEMORY_STATE_DIR}/pdf-ingest/status.json",
        "PDF_INGEST_MANIFEST_DB": f"{CONTAINER_MEMORY_STATE_DIR}/pdf-ingest/manifest.sqlite3",
        "PDF_INGEST_LOCK_FILE": f"{CONTAINER_MEMORY_STATE_DIR}/pdf-ingest/ingest.lock",
        "QMD_REFRESH_LOCK_FILE": f"{CONTAINER_MEMORY_STATE_DIR}/qmd-refresh.lock",
        "ARCLINK_MEMORY_SYNTH_STATUS_FILE": f"{CONTAINER_MEMORY_STATE_DIR}/memory-synth/status.json",
        "ARCLINK_MEMORY_SYNTH_LOCK_FILE": f"{CONTAINER_MEMORY_STATE_DIR}/memory-synth/synth.lock",
    }
    services = _render_services(
        deployment_id=deployment_id,
        prefix=prefix,
        roots=roots,
        env=deployment_env,
        labels=labels,
        compose_secrets=compose_secrets,
        fleet_share_hub_host_ref=fleet_share_hub_host_ref,
        tailnet_service_ports=tailnet_service_ports,
        use_control_network=use_control_network,
    )
    nextcloud_hostport = _url_hostport(access_urls["files"])
    if nextcloud_hostport:
        nextcloud_env = services["nextcloud"]["environment"]
        nextcloud_env["NEXTCLOUD_TRUSTED_DOMAINS"] = f"{hostnames['files']} {nextcloud_hostport}"
        nextcloud_env["OVERWRITEPROTOCOL"] = "https"
        nextcloud_env["OVERWRITEHOST"] = nextcloud_hostport
        nextcloud_env["OVERWRITECLIURL"] = access_urls["files"].rstrip("/")
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
            } if use_control_network else {},
        },
        "runtime_resolution": {
            "stock_image_file_env": {
                "nextcloud-db": ["POSTGRES_PASSWORD_FILE"],
                "nextcloud": ["POSTGRES_PASSWORD_FILE", "NEXTCLOUD_ADMIN_PASSWORD_FILE"],
            },
            "entrypoint_file_resolver": {},
            "app_ref_resolver_required": [
                name
                for name in (
                    provider_secret_name,
                    "dashboard_password",
                    "dashboard_sso_secret",
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
            "control_network_mode": control_network_mode,
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
            status="dry_run_planned",
            detail={"source": "arclink_provisioning_dry_run", "note": "planning only — not yet applied"},
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
                "outcome": "dry_run_succeeded",
                "service_count": len(intent["compose"]["services"]),
                "ready_for_execution": bool(intent["execution"]["ready"]),
                "note": "planning only — no services were started or applied",
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
