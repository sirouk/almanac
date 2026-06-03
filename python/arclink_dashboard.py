#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from arclink_control import ARCLINK_ACTION_INTENT_STATUSES, append_arclink_audit, append_arclink_event, get_setting, utc_now_iso
from arclink_adapters import arclink_access_urls
from arclink_boundary import json_dumps_safe, json_loads_safe, reject_secret_material, rowdict
from arclink_chutes import evaluate_chutes_deployment_boundary, renewal_lifecycle_for_billing_state
from arclink_product import primary_provider
from arclink_wrapped import list_user_wrapped_reports, wrapped_admin_aggregate


ARCLINK_ADMIN_ACTION_TYPES = frozenset(
    {
        "restart",
        "reprovision",
        "suspend",
        "unsuspend",
        "force_resynth",
        "rotate_bot_key",
        "rotate_chutes_key",
        "dns_repair",
        "refund",
        "comp",
        "cancel",
        "backup_write_check",
        "rollout",
        "academy_apply_preview",
        "academy_apply",
    }
)
ARCLINK_ADMIN_TARGET_KINDS = frozenset({"deployment", "user", "subscription", "dns_record", "system"})
ARCLINK_EXECUTABLE_ADMIN_ACTION_TYPES = frozenset({"restart", "reprovision", "dns_repair", "rotate_chutes_key", "refund", "cancel", "comp", "backup_write_check", "rollout", "academy_apply_preview", "academy_apply"})
ARCLINK_PENDING_ADMIN_ACTION_TYPES = ARCLINK_ADMIN_ACTION_TYPES - ARCLINK_EXECUTABLE_ADMIN_ACTION_TYPES
ARCLINK_ADMIN_ACTION_SUPPORT: dict[str, dict[str, Any]] = {
    "restart": {
        "label": "Restart",
        "worker_support": "wired",
        "operation_kind": "docker_compose_lifecycle",
        "target_kinds": ("deployment",),
        "required_adapter": "ARCLINK_EXECUTOR_ADAPTER=fake|local|ssh",
        "live_proof_gate": "PG-PROVISION",
        "local_contract": "queues an audited Docker Compose lifecycle restart intent; fake adapter results are non-live evidence only",
    },
    "reprovision": {
        "label": "Reprovision",
        "worker_support": "wired",
        "operation_kind": "pod_migration",
        "target_kinds": ("deployment",),
        "required_adapter": "ARCLINK_EXECUTOR_ADAPTER=fake|local|ssh",
        "live_proof_gate": "PG-PROVISION",
        "local_contract": "queues an audited operator-only Pod migration or redeploy intent through the action worker",
    },
    "dns_repair": {
        "label": "DNS repair",
        "worker_support": "wired",
        "operation_kind": "cloudflare_dns_apply",
        "target_kinds": ("deployment", "dns_record"),
        "required_adapter": "ARCLINK_EXECUTOR_ADAPTER=fake|local|ssh plus configured DNS provider credentials for live mutation",
        "live_proof_gate": "PG-INGRESS",
        "local_contract": "queues an audited DNS repair intent and derives desired records from deployment metadata or stored DNS rows",
    },
    "rotate_chutes_key": {
        "label": "Rotate Chutes key",
        "worker_support": "wired",
        "operation_kind": "chutes_key_apply",
        "target_kinds": ("deployment",),
        "required_adapter": "ARCLINK_EXECUTOR_ADAPTER=fake|local|ssh plus Chutes key client for live mutation",
        "live_proof_gate": "PG-PROVIDER",
        "local_contract": "queues an audited provider-key rotation intent using secret references, never plaintext keys",
    },
    "refund": {
        "label": "Refund",
        "worker_support": "wired",
        "operation_kind": "stripe_action_apply",
        "target_kinds": ("deployment", "user", "subscription"),
        "required_adapter": "ARCLINK_EXECUTOR_ADAPTER=fake|local|ssh plus Stripe action client for live mutation",
        "live_proof_gate": "PG-STRIPE",
        "local_contract": "queues an audited Stripe refund intent after resolving the target through the control DB",
    },
    "cancel": {
        "label": "Cancel",
        "worker_support": "wired",
        "operation_kind": "stripe_action_apply",
        "target_kinds": ("deployment", "user", "subscription"),
        "required_adapter": "ARCLINK_EXECUTOR_ADAPTER=fake|local|ssh plus Stripe action client for live mutation",
        "live_proof_gate": "PG-STRIPE",
        "local_contract": "queues an audited Stripe cancellation intent after resolving the target through the control DB",
    },
    "comp": {
        "label": "Comp",
        "worker_support": "wired",
        "operation_kind": "control_db_comp",
        "target_kinds": ("deployment", "user"),
        "required_adapter": "action worker with control DB access; no external provider adapter",
        "live_proof_gate": "LOCAL-CONTROL-DB",
        "local_contract": "applies an audited local entitlement comp through the control DB, not an external provider mutation",
    },
    "backup_write_check": {
        "label": "Backup write check",
        "worker_support": "wired",
        "operation_kind": "backup_git_write_check",
        "target_kinds": ("deployment",),
        "required_adapter": "authorized PG-BACKUP runner; unattended local runs record failed_closed without invoking git",
        "live_proof_gate": "PG-BACKUP",
        "local_contract": "records the GitHub write-check boundary and keeps backup activation inactive unless verified write evidence exists",
    },
    "academy_apply_preview": {
        "label": "Academy apply preview",
        "worker_support": "wired",
        "operation_kind": "academy_application_preview",
        "target_kinds": ("user", "deployment"),
        "required_adapter": "action worker with control DB access; no executor, filesystem, provider, bot, Docker, SSH, or deploy adapter",
        "live_proof_gate": "PG-HERMES/PG-PROVIDER",
        "local_contract": "queues an audited no-write Academy application preview from a staged Crew Recipe review; real Agent application remains proof-gated",
    },
    "academy_apply": {
        "label": "Academy apply",
        "worker_support": "wired",
        "operation_kind": "academy_agent_apply",
        "target_kinds": ("user", "deployment"),
        "required_adapter": "action worker with control DB access; live Agent-home writes require a live executor adapter plus ARCLINK_ACADEMY_APPLY_LIVE (PG-HERMES)",
        "live_proof_gate": "PG-HERMES/PG-PROVIDER",
        "local_contract": "stages a graduated Trainee's additive SOUL/skills/qmd/vault application plan; record-only adapters stage, live adapters without PG-HERMES authorization fail closed, and authorized runs hand off to the Hermes-home seam",
    },
    "suspend": {
        "label": "Suspend",
        "worker_support": "pending_not_implemented",
        "operation_kind": "",
        "target_kinds": ("deployment", "user"),
        "required_adapter": "not queueable until worker dispatch lands",
        "live_proof_gate": "policy-gated",
        "local_contract": "visible as a planned operation only; no queueing or live side effect is exposed",
    },
    "unsuspend": {
        "label": "Unsuspend",
        "worker_support": "pending_not_implemented",
        "operation_kind": "",
        "target_kinds": ("deployment", "user"),
        "required_adapter": "not queueable until worker dispatch lands",
        "live_proof_gate": "policy-gated",
        "local_contract": "visible as a planned operation only; no queueing or live side effect is exposed",
    },
    "force_resynth": {
        "label": "Force resynth",
        "worker_support": "pending_not_implemented",
        "operation_kind": "",
        "target_kinds": ("deployment", "user"),
        "required_adapter": "not queueable until worker dispatch lands",
        "live_proof_gate": "PG-HERMES",
        "local_contract": "visible as a planned operation only; no queueing or live side effect is exposed",
    },
    "rotate_bot_key": {
        "label": "Rotate bot key",
        "worker_support": "pending_not_implemented",
        "operation_kind": "",
        "target_kinds": ("deployment", "user"),
        "required_adapter": "not queueable until worker dispatch lands",
        "live_proof_gate": "PG-BOTS",
        "local_contract": "visible as a planned operation only; no queueing or live side effect is exposed",
    },
    "rollout": {
        "label": "Rollout",
        "worker_support": "wired",
        "operation_kind": "arcpod_update_rollout",
        "target_kinds": ("deployment", "system"),
        "required_adapter": "action worker with control DB access; explicit fake/local record-only execution contract for bounded batch execution",
        "live_proof_gate": "PG-UPGRADE/PG-HERMES",
        "local_contract": "queues audited local ArcPod update rollout rows from a ready dry-run preflight plan and can record one bounded fake/local batch; live refresh and health/smoke proof remain gated",
    },
}
ARCLINK_USER_DASHBOARD_SECTIONS = (
    "deployment_health",
    "access_links",
    "wrapped",
    "academy_training",
    "bot_setup",
    "backup",
    "files",
    "code",
    "terminal",
    "hermes",
    "qmd_memory",
    "skills",
    "model",
    "billing",
    "security",
    "support",
)
ARCLINK_BACKUP_OWNER_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ARCLINK_BACKUP_PUBLIC_KEY_RE = re.compile(r"^ssh-ed25519 [A-Za-z0-9+/=]{40,220}(?: [\x20-\x7e]{0,120})?$")
ARCLINK_BACKUP_PUBLIC_STATUSES = frozenset(
    {
        "awaiting_private_repo",
        "repo_recorded_pending_key_setup",
    }
)
ARCLINK_BACKUP_WRITE_CHECK_STATUSES = frozenset({"not_run", "pending_operator_setup", "failed_closed", "verified"})
ARCLINK_BACKUP_ACTIVATION_STATUSES = frozenset({"not_active", "pending_operator_setup", "failed_closed", "active"})
ARCLINK_BACKUP_FAILED_CLOSED_REASON = (
    "GitHub write verification requires an authorized PG-BACKUP runner; no live git command was run."
)


def _admin_action_worker_support(action_type: str) -> str:
    return str(ARCLINK_ADMIN_ACTION_SUPPORT.get(action_type, {}).get("worker_support") or "pending_not_implemented")


def _admin_action_support_entries(
    *,
    executor_adapter: str,
    probes_ready: bool,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    support: dict[str, dict[str, Any]] = {}
    matrix: list[dict[str, Any]] = []
    for action_type in sorted(ARCLINK_ADMIN_ACTION_TYPES):
        base = dict(ARCLINK_ADMIN_ACTION_SUPPORT.get(action_type) or {})
        worker_support = str(base.get("worker_support") or "pending_not_implemented")
        is_wired = worker_support == "wired"
        queueable = is_wired and probes_ready
        if not is_wired:
            readiness = "pending_not_implemented"
            fail_closed_reason = "worker support is not implemented; action remains visible but not queueable"
        elif not probes_ready:
            readiness = "disabled"
            fail_closed_reason = "executor probes are not ready; action fails closed before queueing"
        else:
            readiness = "queueable"
            fail_closed_reason = ""
        entry = {
            "action_type": action_type,
            "label": str(base.get("label") or action_type.replace("_", " ").title()),
            "readiness": readiness,
            "queueable": queueable,
            "worker_support": worker_support,
            "operation_kind": str(base.get("operation_kind") or ""),
            "target_kinds": list(base.get("target_kinds") or ()),
            "required_adapter": str(base.get("required_adapter") or ""),
            "live_proof_gate": str(base.get("live_proof_gate") or ""),
            "local_contract": str(base.get("local_contract") or ""),
            "executor_adapter": executor_adapter,
            "fail_closed_reason": fail_closed_reason,
        }
        support[action_type] = entry
        matrix.append(entry)
    return support, matrix


def admin_action_execution_readiness(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source_env = env or os.environ
    executor_adapter = str(source_env.get("ARCLINK_EXECUTOR_ADAPTER") or "disabled").strip().lower() or "disabled"
    probes: list[dict[str, Any]] = [
        {
            "name": "executor_adapter",
            "ok": executor_adapter in {"fake", "local", "ssh"},
            "detail": executor_adapter,
        }
    ]
    require_worker = env is None and str(source_env.get("ARCLINK_ADMIN_ACTION_REQUIRE_WORKER_READY") or "1").strip().lower() not in {"0", "false", "no", "off"}
    if require_worker:
        probes.append(_action_worker_liveness_probe(source_env))
    if executor_adapter == "ssh":
        machine_enabled = _truthy(source_env.get("ARCLINK_EXECUTOR_MACHINE_MODE_ENABLED") or source_env.get("ARCLINK_ACTION_WORKER_SSH_ENABLED") or "")
        host = str(source_env.get("ARCLINK_ACTION_WORKER_SSH_HOST") or source_env.get("ARCLINK_LOCAL_FLEET_SSH_HOST") or "").strip().lower()
        allowed_hosts = _csv_set(
            str(source_env.get("ARCLINK_EXECUTOR_MACHINE_HOST_ALLOWLIST") or source_env.get("ARCLINK_ACTION_WORKER_SSH_HOST_ALLOWLIST") or "")
        )
        key_path = str(source_env.get("ARCLINK_FLEET_SSH_KEY_PATH") or "").strip()
        probes.append({"name": "ssh_machine_mode", "ok": machine_enabled, "detail": "enabled" if machine_enabled else "disabled"})
        probes.append({"name": "ssh_host", "ok": bool(host) and host in allowed_hosts, "detail": "allowlisted" if host and host in allowed_hosts else "missing_or_not_allowlisted"})
        probes.append({"name": "ssh_key", "ok": bool(key_path), "detail": "configured" if key_path else "missing"})
    probes_ready = all(bool(probe["ok"]) for probe in probes)
    executable = sorted(ARCLINK_EXECUTABLE_ADMIN_ACTION_TYPES) if probes_ready else []
    disabled = sorted(ARCLINK_ADMIN_ACTION_TYPES - set(executable))
    action_support, action_matrix = _admin_action_support_entries(
        executor_adapter=executor_adapter,
        probes_ready=probes_ready,
    )
    return {
        "executable": executable,
        "pending_not_implemented": sorted(ARCLINK_PENDING_ADMIN_ACTION_TYPES),
        "disabled": disabled,
        "action_support": action_support,
        "action_matrix": action_matrix,
        "executor_adapter": executor_adapter,
        "probes": probes,
        "queue_policy": "admin UI queues only modeled worker actions; pending actions stay disabled until worker wiring lands",
        "note": (
            "modeled actions are executable only when executor probes pass"
            if executable
            else "executor probes are not ready; admin actions fail closed in the UI"
        ),
    }


def control_node_provisioning_readiness(
    conn: sqlite3.Connection,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return the local Control Node ArcPod provisioning readiness read model.

    This helper is intentionally read-only. SSH, Docker, provider, ingress, and
    live worker probes stay under PG-FLEET/PG-PROVISION.
    """
    from arclink_fleet import fleet_capacity_summary, host_is_placement_eligible

    source_env = env if env is not None else os.environ
    provisioner_enabled = _truthy(source_env.get("ARCLINK_CONTROL_PROVISIONER_ENABLED"))
    executor_adapter = str(source_env.get("ARCLINK_EXECUTOR_ADAPTER") or "disabled").strip().lower() or "disabled"
    capacity = fleet_capacity_summary(conn)
    hosts = list(capacity.get("hosts") or [])
    eligible_workers = [
        {
            "host_id": str(host.get("host_id") or ""),
            "hostname": str(host.get("hostname") or ""),
            "region": str(host.get("region") or ""),
            "headroom": max(0, int(host.get("headroom") or 0)),
            "effective_capacity_slots": max(0, int(host.get("effective_capacity_slots") or host.get("capacity_slots") or 0)),
            "control_plane_reserve": bool(host.get("control_plane_reserve")),
            "last_health_state": str(host.get("last_health_state") or ""),
            "executor_adapter": executor_adapter,
        }
        for host in hosts
        if host_is_placement_eligible(host)
    ]
    eligible_slots = sum(int(host["headroom"]) for host in eligible_workers)
    blockers: list[dict[str, str]] = []

    if executor_adapter not in {"fake", "local", "ssh"}:
        blockers.append(
            {
                "name": "executor_adapter",
                "detail": "ARCLINK_EXECUTOR_ADAPTER must be fake, local, or ssh before ArcPod provisioning can run.",
            }
        )
    if not eligible_workers:
        blockers.append(
            {
                "name": "worker_capacity",
                "detail": "No active, undrained worker has available capacity.",
            }
        )

    ssh_blockers: list[dict[str, str]] = []
    if executor_adapter == "ssh":
        machine_enabled = _truthy(
            source_env.get("ARCLINK_EXECUTOR_MACHINE_MODE_ENABLED")
            or source_env.get("ARCLINK_ACTION_WORKER_SSH_ENABLED")
        )
        host = str(
            source_env.get("ARCLINK_ACTION_WORKER_SSH_HOST")
            or source_env.get("ARCLINK_LOCAL_FLEET_SSH_HOST")
            or ""
        ).strip().lower()
        allowed_hosts = _csv_set(
            str(
                source_env.get("ARCLINK_EXECUTOR_MACHINE_HOST_ALLOWLIST")
                or source_env.get("ARCLINK_ACTION_WORKER_SSH_HOST_ALLOWLIST")
                or ""
            )
        )
        key_path = str(source_env.get("ARCLINK_FLEET_SSH_KEY_PATH") or "").strip()
        if not machine_enabled:
            ssh_blockers.append({"name": "ssh_machine_mode", "detail": "SSH machine mode is disabled."})
        if not host or host not in allowed_hosts:
            ssh_blockers.append({"name": "ssh_host", "detail": "SSH host is missing or not allowlisted."})
        if not key_path:
            ssh_blockers.append({"name": "ssh_key", "detail": "Fleet SSH key path is missing."})
        blockers.extend(ssh_blockers)

    if not provisioner_enabled:
        state = "control_plane_only"
        ready = False
        next_action = "Register and smoke-test a Sovereign worker, then enable ARCLINK_CONTROL_PROVISIONER_ENABLED."
        summary = "control plane up; ArcPod provisioning disabled until a worker is registered and smoke-tested"
    elif ssh_blockers:
        state = "pending_ssh"
        ready = False
        next_action = "Complete SSH machine-mode host allowlist and fleet key configuration, then run an authorized worker smoke proof."
        summary = "blocked pending SSH worker configuration"
    elif eligible_workers and executor_adapter in {"fake", "local", "ssh"}:
        state = "ready_to_provision"
        ready = True
        next_action = "Run PG-FLEET/PG-PROVISION before claiming live worker readiness."
        summary = f"ready to provision ArcPods ({len(eligible_workers)} eligible worker(s), {eligible_slots} available slot(s))"
    elif not eligible_workers:
        state = "blocked_no_worker"
        ready = False
        next_action = "Register, probe, and un-drain at least one worker with available capacity."
        summary = "blocked; no eligible worker has available capacity"
    else:
        state = "blocked_executor"
        ready = False
        next_action = "Configure a supported executor adapter and rerun the local readiness check."
        summary = "blocked; executor adapter is not configured for provisioning"

    return {
        "state": state,
        "ready_to_provision": ready,
        "summary": summary,
        "provisioner_enabled": provisioner_enabled,
        "executor_adapter": executor_adapter,
        "eligible_worker_count": len(eligible_workers),
        "available_slots": eligible_slots,
        "total_workers": int(capacity.get("total_hosts") or 0),
        "active_workers": int(capacity.get("active_hosts") or 0),
        "eligible_workers": eligible_workers,
        "blockers": blockers,
        "next_action": next_action,
        "proof_gate": "PG-FLEET/PG-PROVISION",
        "live_proof_required": True,
        "note": "Local readiness is not live worker proof; no SSH, Docker, provider, ingress, or deploy command was run.",
    }


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _csv_set(value: str) -> set[str]:
    return {item.strip().lower() for item in str(value or "").split(",") if item.strip()}


def _action_worker_liveness_probe(env: Mapping[str, str]) -> dict[str, Any]:
    status_dir = str(env.get("ARCLINK_DOCKER_JOB_STATUS_DIR") or "").strip()
    if not status_dir:
        state_dir = str(env.get("STATE_DIR") or env.get("ARCLINK_STATE_DIR") or "").strip()
        if not state_dir:
            priv_dir = str(env.get("ARCLINK_PRIV_DIR") or "/home/arclink/arclink/arclink-priv").strip()
            state_dir = str(Path(priv_dir) / "state")
        status_dir = str(Path(state_dir) / "docker" / "jobs")
    status_file = Path(status_dir) / "control-action-worker.json"
    try:
        status_file_exists = status_file.is_file()
    except OSError:
        status_file_exists = False
    if not status_file_exists:
        return {"name": "control_action_worker", "ok": False, "detail": "missing_status_file"}
    try:
        data = json.loads(status_file.read_text(encoding="utf-8"))
    except Exception:
        return {"name": "control_action_worker", "ok": False, "detail": "invalid_status_file"}
    status = str(data.get("status") or "").strip().lower()
    finished = _parse_probe_time(str(data.get("finished_at") or ""))
    started = _parse_probe_time(str(data.get("started_at") or ""))
    try:
        interval = int(data.get("interval_seconds") or 0)
    except Exception:
        interval = 0
    stale_after = max(600, interval * 3 + 120) if interval else 7200
    now = datetime.now(timezone.utc)
    if status in {"ok", "success", "skipped"} and finished is not None:
        age = (now - finished).total_seconds()
        return {
            "name": "control_action_worker",
            "ok": age <= stale_after,
            "detail": f"{status}:{int(age)}s",
        }
    if status == "running" and started is not None:
        age = (now - started).total_seconds()
        return {
            "name": "control_action_worker",
            "ok": age <= stale_after,
            "detail": f"running:{int(age)}s",
        }
    return {"name": "control_action_worker", "ok": False, "detail": status or "unknown"}


def _parse_probe_time(value: str) -> datetime | None:
    clean = str(value or "").strip()
    if not clean:
        return None
    if clean.endswith("Z"):
        clean = clean[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(clean)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
ARCLINK_ADMIN_DASHBOARD_SECTIONS = (
    "onboarding_funnel",
    "users",
    "deployments",
    "wrapped",
    "payments",
    "infrastructure",
    "bots",
    "security_abuse",
    "releases_maintenance",
    "logs_events",
    "audit",
    "queued_actions",
)

class ArcLinkDashboardError(ValueError):
    pass


def build_operator_snapshot(
    *,
    env: dict[str, str] | None = None,
    skip_ports: bool = True,
    docker_binary: str = "docker",
) -> dict[str, Any]:
    """Build a read-only operator snapshot aggregating host readiness,
    provider diagnostics, live journey blockers, and evidence status.

    Never returns secret values - only credential names and presence.
    """
    from arclink_host_readiness import run_readiness
    from arclink_diagnostics import run_diagnostics
    from arclink_live_journey import build_journey

    readiness = run_readiness(env=env, skip_ports=skip_ports, docker_binary=docker_binary)
    diagnostics = run_diagnostics(env=env, docker_binary=docker_binary)

    env_source = env if env is not None else os.environ
    journey_steps = build_journey()
    journey_blockers: list[dict[str, Any]] = []
    for step in journey_steps:
        missing = [key for key in step.required_env if not str(env_source.get(key, "")).strip()]
        if missing:
            journey_blockers.append({"step": step.name, "missing_env": missing})

    all_journey_creds_present = len(journey_blockers) == 0
    template_state = operator_evidence_template_state(env_source)

    return {
        "host_readiness": readiness.to_dict(),
        "provider_diagnostics": diagnostics.to_dict(),
        "live_journey": {
            "total_steps": len(journey_steps),
            "blocked_steps": len(journey_blockers),
            "all_credentials_present": all_journey_creds_present,
            "blockers": journey_blockers,
        },
        "evidence": {
            "template_ready": template_state["ready"],
            "template": template_state,
            "credentialed_evidence": "missing" if not all_journey_creds_present else "pending_run",
            "live_proof": "blocked" if not all_journey_creds_present else "pending_credentialed_run",
        },
    }


def operator_evidence_template_state(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source_env = env or os.environ
    template_path = Path(
        str(source_env.get("ARCLINK_LIVE_EVIDENCE_TEMPLATE") or Path(__file__).resolve().parents[1] / "docs" / "arclink" / "live-e2e-evidence-template.md")
    )
    try:
        text = template_path.read_text(encoding="utf-8")[:12_000]
    except OSError:
        text = ""
    required_markers = ("Evidence", "Run", "Credentials")
    missing_markers = [marker for marker in required_markers if marker.casefold() not in text.casefold()]
    return {
        "ready": template_path.is_file() and not missing_markers,
        "path": str(template_path),
        "missing_markers": missing_markers,
    }


def build_scale_operations_snapshot(
    conn: sqlite3.Connection,
    *,
    stale_action_threshold_seconds: int = 3600,
    rollout_target_version: str = "",
    rollout_batch_size: int | None = None,
) -> dict[str, Any]:
    """Build operator-visible scale operations read model."""
    from arclink_fleet import fleet_capacity_summary
    from arclink_inventory import list_inventory_machines
    from arclink_rollout import ArcLinkRolloutError, plan_arcpod_update_rollout

    capacity = fleet_capacity_summary(conn)
    inventory = [
        {
            "machine_id": str(row["machine_id"]),
            "provider": str(row["provider"]),
            "hostname": str(row["hostname"]),
            "ssh_host": str(row["ssh_host"] or ""),
            "ssh_user": str(row["ssh_user"] or ""),
            "region": str(row["region"] or ""),
            "status": str(row["status"]),
            "asu_capacity": float(row["asu_capacity"] or 0),
            "asu_consumed": float(row["asu_consumed"] or 0),
            "last_probed_at": str(row["last_probed_at"] or ""),
            "machine_host_link": str(row["machine_host_link"] or ""),
        }
        for row in list_inventory_machines(conn)
    ]

    # Stale queued actions (queued for over threshold)
    from arclink_control import parse_utc_iso, utc_now
    now = utc_now()
    queued_rows = conn.execute(
        "SELECT * FROM arclink_action_intents WHERE status IN ('queued', 'running') ORDER BY created_at ASC",
    ).fetchall()
    stale_actions = []
    for row in queued_rows:
        created = parse_utc_iso(row["created_at"])
        if created is None:
            continue
        elapsed = (now - created).total_seconds()
        if elapsed >= stale_action_threshold_seconds:
            stale_actions.append({
                "action_id": str(row["action_id"]),
                "action_type": str(row["action_type"]),
                "status": str(row["status"]),
                "target": f"{row['target_kind']}:{row['target_id']}",
                "elapsed_seconds": int(elapsed),
            })

    # Recent action attempts
    recent_attempts = [
        {
            "attempt_id": str(r["attempt_id"]),
            "action_id": str(r["action_id"]),
            "status": str(r["status"]),
            "executor_adapter": str(r["executor_adapter"]),
            "error": str(r["error"] or ""),
            "started_at": str(r["started_at"]),
            "finished_at": str(r["finished_at"] or ""),
        }
        for r in conn.execute(
            "SELECT * FROM arclink_action_attempts ORDER BY started_at DESC LIMIT 20",
        ).fetchall()
    ]
    placements = [
        {
            "placement_id": str(r["placement_id"]),
            "deployment_id": str(r["deployment_id"]),
            "host_id": str(r["host_id"]),
            "status": str(r["status"]),
            "placed_at": str(r["placed_at"]),
            "removed_at": str(r["removed_at"] or ""),
        }
        for r in conn.execute(
            "SELECT * FROM arclink_deployment_placements ORDER BY placed_at DESC LIMIT 20",
        ).fetchall()
    ]

    # Active rollouts
    active_rollouts = []
    for r in conn.execute(
        "SELECT * FROM arclink_rollouts WHERE status IN ('planned', 'in_progress', 'paused', 'failed') ORDER BY created_at DESC LIMIT 20",
    ).fetchall():
        rollout_metadata = json_loads_safe(str(r["metadata_json"] or "{}"))
        rollout_metadata = dict(rollout_metadata) if isinstance(rollout_metadata, Mapping) else {}
        execution = rollout_metadata.get("execution")
        execution = dict(execution) if isinstance(execution, Mapping) else {}
        health_smoke = rollout_metadata.get("health_smoke")
        health_smoke = dict(health_smoke) if isinstance(health_smoke, Mapping) else {}
        active_rollouts.append(
            {
                "rollout_id": str(r["rollout_id"]),
                "deployment_id": str(r["deployment_id"]),
                "version_tag": str(r["version_tag"]),
                "status": str(r["status"]),
                "current_wave": int(r["current_wave"]),
                "wave_count": int(r["wave_count"]),
                "rollout_group_id": str(rollout_metadata.get("rollout_group_id") or ""),
                "batch_index": int(rollout_metadata.get("batch_index") or 0),
                "batch_position": int(rollout_metadata.get("batch_position") or 0),
                "execution_status": str(execution.get("status") or ""),
                "execution_adapter": str(execution.get("adapter") or ""),
                "health_smoke_status": str(health_smoke.get("status") or ""),
                "proof_gate": str(rollout_metadata.get("proof_gate") or ""),
                "live_proof_required": bool(rollout_metadata.get("live_proof_required")),
            }
        )

    action_readiness = admin_action_execution_readiness()
    provisioning_readiness = control_node_provisioning_readiness(conn)
    clean_rollout_target = str(
        rollout_target_version
        or os.environ.get("ARCLINK_ROLLOUT_TARGET_VERSION")
        or os.environ.get("ARCLINK_UPGRADE_TARGET_VERSION")
        or ""
    ).strip()
    if clean_rollout_target:
        try:
            rollout_dry_run_plan = plan_arcpod_update_rollout(
                conn,
                target_version=clean_rollout_target,
                batch_size=rollout_batch_size,
                env=os.environ,
            )
        except ArcLinkRolloutError as exc:
            rollout_dry_run_plan = {
                "plan_kind": "arcpod_update_rollout",
                "mode": "dry_run",
                "status": "blocked",
                "target_version": clean_rollout_target,
                "preflight_blockers": [{"code": "planner_error", "message": str(exc)}],
                "repair_summary": [str(exc)],
                "execution": {"enabled": False, "reason": "dry-run planner refused the rollout request"},
                "mutation_performed": False,
                "proof_gate": "PG-UPGRADE/PG-HERMES",
                "live_proof_required": True,
            }
    else:
        rollout_dry_run_plan = {
            "plan_kind": "arcpod_update_rollout",
            "mode": "dry_run",
            "status": "not_configured",
            "target_version": "",
            "summary": "Set ARCLINK_ROLLOUT_TARGET_VERSION or pass rollout_target_version to preview a bounded ArcPod update plan.",
            "execution": {"enabled": False, "reason": "no target version configured"},
            "mutation_performed": False,
            "proof_gate": "PG-UPGRADE/PG-HERMES",
            "live_proof_required": True,
        }

    return {
        "fleet_capacity": capacity,
        "fleet_surface": "internal_read_only",
        "inventory": {
            "machines": inventory,
            "strategy": os.environ.get("ARCLINK_FLEET_PLACEMENT_STRATEGY", "headroom").strip() or "headroom",
        },
        "placements": placements,
        "stale_actions": stale_actions,
        "recent_action_attempts": recent_attempts,
        "last_executor_result": recent_attempts[0] if recent_attempts else {},
        "active_rollouts": active_rollouts,
        "rollout_dry_run_plan": rollout_dry_run_plan,
        "rollout_surface": "local_job_queueable_with_bounded_fake_execution",
        "rollout_execution_boundary": "dry-run previews are read-only; queued rollout actions can materialize rows and explicitly record one fake/local batch, but live refresh, health, and smoke proof remain PG-UPGRADE/PG-HERMES gated",
        "provisioner": {
            "enabled": bool(provisioning_readiness["provisioner_enabled"]),
            "executor_adapter": action_readiness["executor_adapter"],
            "status": str(provisioning_readiness["state"]),
            "note": str(provisioning_readiness["summary"]),
        },
        "provisioning_readiness": provisioning_readiness,
        "action_execution_readiness": action_readiness,
    }


def _json_loads(value: str | None) -> dict[str, Any]:
    return json_loads_safe(value)


def _reject_secret_material(value: Any, *, path: str = "$") -> None:
    reject_secret_material(value, path=path, label="ArcLink dashboard contract", error_cls=ArcLinkDashboardError)


def _safe_json(value: Mapping[str, Any] | None) -> str:
    return json_dumps_safe(value, label="ArcLink dashboard contract", error_cls=ArcLinkDashboardError)


def _stable_action_id(idempotency_key: str) -> str:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:24]
    return f"act_{digest}"


def _limit(value: int) -> int:
    return min(100, max(1, int(value or 25)))


def _deployment_urls(prefix: str, base_domain: str, metadata: Mapping[str, Any] | None = None) -> dict[str, str]:
    if not str(prefix or "").strip() or not str(base_domain or "").strip():
        return {}
    meta = dict(metadata or {})
    publish_state = meta.get("tailnet_app_publication")
    tailnet_apps_unavailable = isinstance(publish_state, Mapping) and str(publish_state.get("status") or "") == "unavailable"
    ingress_mode = str(meta.get("ingress_mode") or os.environ.get("ARCLINK_INGRESS_MODE") or "domain").strip().lower()
    tailscale_dns_name = str(
        meta.get("tailscale_dns_name") or os.environ.get("ARCLINK_TAILSCALE_DNS_NAME") or base_domain
    ).strip()
    tailscale_host_strategy = str(
        meta.get("tailscale_host_strategy")
        or os.environ.get("ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY")
        or "path"
    ).strip()
    if ingress_mode == "tailscale" and tailscale_host_strategy == "path":
        if tailnet_apps_unavailable:
            host = tailscale_dns_name or base_domain
            return {
                "dashboard": f"https://{host}/u/{prefix}",
                "notion": f"https://{host}/u/{prefix}/notion/webhook",
            }
        tailnet_ports = meta.get("tailnet_service_ports") if isinstance(meta.get("tailnet_service_ports"), Mapping) else None
        try:
            hermes_port = int((tailnet_ports or {}).get("hermes") or 0)
        except (TypeError, ValueError):
            hermes_port = 0
        if 0 < hermes_port < 65536:
            urls = arclink_access_urls(
                prefix=prefix,
                base_domain=base_domain,
                ingress_mode=ingress_mode,
                tailscale_dns_name=tailscale_dns_name,
                tailscale_host_strategy=tailscale_host_strategy,
                tailnet_service_ports=tailnet_ports,
            )
            urls["notion"] = f"https://{tailscale_dns_name or base_domain}/u/{prefix}/notion/webhook"
            return urls
        stored_urls = meta.get("access_urls")
        if isinstance(stored_urls, Mapping):
            safe_urls = {
                str(role): str(url).strip()
                for role, url in stored_urls.items()
                if str(role).strip() and str(url).strip().startswith("https://")
            }
            if {"dashboard", "files", "code", "hermes"} <= set(safe_urls):
                return safe_urls
        return arclink_access_urls(
            prefix=prefix,
            base_domain=base_domain,
            ingress_mode=ingress_mode,
            tailscale_dns_name=tailscale_dns_name,
            tailscale_host_strategy=tailscale_host_strategy,
            tailnet_service_ports=tailnet_ports,
        )
    stored_urls = meta.get("access_urls")
    if isinstance(stored_urls, Mapping):
        safe_urls = {
            str(role): str(url).strip()
            for role, url in stored_urls.items()
            if str(role).strip() and str(url).strip().startswith("https://")
        }
        if {"dashboard", "files", "code", "hermes"} <= set(safe_urls):
            return safe_urls
        if tailnet_apps_unavailable and safe_urls.get("dashboard"):
            limited = {"dashboard": safe_urls["dashboard"]}
            if safe_urls.get("notion"):
                limited["notion"] = safe_urls["notion"]
            return limited
    if ingress_mode == "tailscale" and tailnet_apps_unavailable:
        host = tailscale_dns_name or base_domain
        return {
            "dashboard": f"https://{host}/u/{prefix}",
            "notion": f"https://{host}/u/{prefix}/notion/webhook",
        }
    tailnet_ports = meta.get("tailnet_service_ports") if isinstance(meta.get("tailnet_service_ports"), Mapping) else None
    return arclink_access_urls(
        prefix=prefix,
        base_domain=base_domain,
        ingress_mode=ingress_mode,
        tailscale_dns_name=tailscale_dns_name,
        tailscale_host_strategy=tailscale_host_strategy,
        tailnet_service_ports=tailnet_ports,
    )


def _count(conn: sqlite3.Connection, sql: str, args: tuple[Any, ...] = ()) -> int:
    row = conn.execute(sql, args).fetchone()
    return int(row[0] if row is not None else 0)


def _health_status(health: list[dict[str, Any]]) -> str:
    statuses = {str(item.get("status") or "").lower() for item in health}
    if statuses & {"failed", "unhealthy"}:
        return "unhealthy"
    if statuses & {"degraded"}:
        return "degraded"
    if statuses & {"healthy"}:
        return "healthy"
    if statuses & {"planned", "pending"}:
        return "planned"
    return "unknown"


def _notion_index_available(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM notion_index_documents WHERE state = 'active' LIMIT 1"
    ).fetchone()
    return row is not None


def _join_url_path(base_url: str, path: str) -> str:
    clean_base = str(base_url or "").strip().rstrip("/")
    if not clean_base:
        return ""
    if not clean_base.startswith(("https://", "http://")):
        clean_base = f"https://{clean_base}"
    clean_path = "/" + str(path or "/").strip().lstrip("/")
    return f"{clean_base}{clean_path}"


def _control_notion_webhook_public_url() -> str:
    explicit = str(os.environ.get("ARCLINK_NOTION_WEBHOOK_PUBLIC_URL") or "").strip()
    if explicit:
        return explicit
    path = str(
        os.environ.get("ARCLINK_TAILSCALE_NOTION_PATH")
        or os.environ.get("TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH")
        or "/notion/webhook"
    ).strip() or "/notion/webhook"
    control_url = str(os.environ.get("ARCLINK_TAILSCALE_CONTROL_URL") or "").strip()
    if control_url:
        return _join_url_path(control_url, path)
    host = str(
        os.environ.get("ARCLINK_TAILSCALE_DNS_NAME")
        or os.environ.get("TAILSCALE_DNS_NAME")
        or ""
    ).strip().lower().strip(".")
    if not host:
        return ""
    # This is the shared control-node callback, not a deployment Hermes Dashboard
    # URL. TAILSCALE_SERVE_PORT can be a per-agent app port such as 8444.
    port = str(
        os.environ.get("ARCLINK_TAILSCALE_HTTPS_PORT")
        or os.environ.get("TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT")
        or "443"
    ).strip()
    if port and port != "443":
        host = f"{host}:{port}"
    return _join_url_path(host, path)


def _deployment_session_metadata(conn: sqlite3.Connection, deployment_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT metadata_json
        FROM arclink_onboarding_sessions
        WHERE deployment_id = ?
        ORDER BY updated_at DESC, created_at DESC
        LIMIT 1
        """,
        (deployment_id,),
    ).fetchone()
    return _json_loads(str(row["metadata_json"] or "{}")) if row is not None else {}


def _deployment_notion_setup(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    urls: Mapping[str, str],
) -> dict[str, Any]:
    session_metadata = _deployment_session_metadata(conn, deployment_id)
    public_status = str(session_metadata.get("connect_notion_public_status") or "").strip()
    configured = bool(str(get_setting(conn, "notion_webhook_verification_token", "") or "").strip())
    installed_at = str(get_setting(conn, "notion_webhook_verification_token_installed_at", "") or "").strip()
    verified_at = str(get_setting(conn, "notion_webhook_verified_at", "") or "").strip()
    armed_until = str(get_setting(conn, "notion_webhook_verification_token_armed_until", "") or "").strip()
    index_available = _notion_index_available(conn)
    dashboard_url = str(urls.get("dashboard") or "").rstrip("/")
    callback_url = str(
        _control_notion_webhook_public_url()
        or urls.get("notion")
        or (f"{dashboard_url}/notion/webhook" if dashboard_url else "")
    ).strip()
    ready_for_dashboard = public_status == "ready_for_dashboard_verification"
    if configured and verified_at:
        webhook_state = "webhook_verified"
    elif configured:
        webhook_state = "webhook_token_installed"
    elif armed_until:
        webhook_state = "webhook_install_armed"
    else:
        webhook_state = "not_configured"
    index_state = "available" if index_available else "not_seen"
    if ready_for_dashboard and verified_at and configured and index_available:
        status = "local_metadata_verified"
    elif ready_for_dashboard and verified_at and configured:
        status = "webhook_verified_waiting_for_index"
    elif ready_for_dashboard:
        status = "pending_dashboard_verification"
    elif public_status == "awaiting_user_setup":
        status = "awaiting_user_setup"
    elif armed_until:
        status = "webhook_install_armed"
    elif configured:
        status = "webhook_token_installed"
    elif callback_url:
        status = "available"
    else:
        status = "unavailable"
    return {
        "status": status,
        "model": "brokered_shared_root",
        "callback_url": callback_url,
        "public_status": public_status or "not_requested",
        "requested_at": str(session_metadata.get("connect_notion_requested_at") or ""),
        "ready_at": str(session_metadata.get("connect_notion_user_marked_ready_at") or ""),
        "webhook": {
            "configured": configured,
            "verified": bool(verified_at),
            "status": webhook_state,
            "installed_at": installed_at,
            "verified_at": verified_at,
            "armed": bool(armed_until),
            "armed_until": armed_until,
        },
        "index": {
            "status": index_state,
        },
        "verification": {
            "state": status,
            "dashboard": status,
            "setup_intent": public_status or "not_requested",
            "local_metadata": "local_metadata_verified"
            if ready_for_dashboard and verified_at and configured and index_available
            else "local_metadata_pending",
            "email_share": "not_proof",
            "user_owned_oauth": "policy_question",
            "shared_root_live_read": "proof_gated",
            "brokered_write_preflight": "proof_gated",
            "live_workspace": "proof_gated",
        },
    }


def _safe_backup_owner_repo(value: str) -> str:
    clean = str(value or "").strip()
    if len(clean) > 160 or not ARCLINK_BACKUP_OWNER_REPO_RE.fullmatch(clean):
        return ""
    try:
        _reject_secret_material(clean, path="$.backup_setup.owner_repo")
    except ArcLinkDashboardError:
        return ""
    return clean


def _safe_backup_public_key(value: str) -> str:
    clean = str(value or "").strip()
    if len(clean) > 420 or not ARCLINK_BACKUP_PUBLIC_KEY_RE.fullmatch(clean):
        return ""
    try:
        _reject_secret_material(clean, path="$.backup_setup.deploy_key.public_key")
    except ArcLinkDashboardError:
        return ""
    return clean


def _safe_backup_status(value: str, allowed: frozenset[str], fallback: str) -> str:
    clean = str(value or "").strip().lower()
    return clean if clean in allowed else fallback


def _safe_backup_reason(value: str) -> str:
    clean = str(value or "").strip() or ARCLINK_BACKUP_FAILED_CLOSED_REASON
    clean = clean[:500]
    try:
        _reject_secret_material(clean, path="$.backup_setup.verification.reason")
    except ArcLinkDashboardError:
        return ARCLINK_BACKUP_FAILED_CLOSED_REASON
    return clean


def _backup_key_private_ref(deployment_id: str) -> str:
    digest = hashlib.sha256(str(deployment_id or "").encode("utf-8")).hexdigest()[:24]
    return f"server_state:agent-backup-deploy-key:{digest}"


def _backup_key_paths(key_staging_dir: str, deployment_id: str) -> tuple[Path, Path]:
    clean_dir = str(key_staging_dir or "").strip()
    if not clean_dir:
        raise ArcLinkDashboardError("ArcLink backup deploy-key staging is not configured")
    digest = hashlib.sha256(str(deployment_id or "").encode("utf-8")).hexdigest()[:24]
    key_dir = Path(clean_dir).expanduser() / digest
    return key_dir / "arclink-agent-backup-ed25519", key_dir / "arclink-agent-backup-ed25519.pub"


def _stage_backup_deploy_key_file(*, key_staging_dir: str, deployment_id: str) -> str:
    private_key, public_key_path = _backup_key_paths(key_staging_dir, deployment_id)
    private_key.parent.mkdir(parents=True, exist_ok=True)
    if not public_key_path.is_file():
        comment = f"arclink-agent-backup-{hashlib.sha256(deployment_id.encode('utf-8')).hexdigest()[:12]}"
        result = subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", comment, "-f", str(private_key)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ArcLinkDashboardError("ArcLink backup deploy-key staging failed closed")
    try:
        os.chmod(private_key, 0o600)
        os.chmod(public_key_path, 0o644)
        public_key = public_key_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ArcLinkDashboardError("ArcLink backup deploy-key staging failed closed") from exc
    safe_public_key = _safe_backup_public_key(public_key)
    if not safe_public_key:
        raise ArcLinkDashboardError("ArcLink backup deploy-key staging produced an invalid public key")
    return safe_public_key


def _deployment_backup_setup(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    deployment_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    session_metadata = _deployment_session_metadata(conn, deployment_id)
    deployment_meta = dict(deployment_metadata or {})
    raw_public_status = str(session_metadata.get("config_backup_public_status") or "").strip()
    public_status = raw_public_status if raw_public_status in ARCLINK_BACKUP_PUBLIC_STATUSES else "not_requested"
    owner_repo = _safe_backup_owner_repo(
        str(session_metadata.get("config_backup_owner_repo") or deployment_meta.get("backup_owner_repo") or "")
    )
    requested_at = str(session_metadata.get("config_backup_requested_at") or "")
    staged_public_key = _safe_backup_public_key(str(deployment_meta.get("backup_deploy_key_public") or ""))
    staged_at = str(deployment_meta.get("backup_deploy_key_staged_at") or "")
    github_write_check = _safe_backup_status(
        str(deployment_meta.get("backup_github_write_check") or "not_run"),
        ARCLINK_BACKUP_WRITE_CHECK_STATUSES,
        "not_run",
    )
    backup_activation = _safe_backup_status(
        str(deployment_meta.get("backup_activation") or "not_active"),
        ARCLINK_BACKUP_ACTIVATION_STATUSES,
        "not_active",
    )
    if backup_activation == "active" and github_write_check != "verified":
        backup_activation = "not_active"
    write_check_reason = _safe_backup_reason(str(deployment_meta.get("backup_github_write_check_reason") or ""))
    write_check_checked_at = str(deployment_meta.get("backup_github_write_check_checked_at") or "").strip()

    if public_status == "awaiting_private_repo":
        status = "awaiting_private_repo"
    elif public_status == "repo_recorded_pending_key_setup" or owner_repo:
        status = "pending_key_setup"
    else:
        status = "not_requested"

    if staged_public_key:
        deploy_key_state = str(deployment_meta.get("backup_deploy_key_status") or "staged_pending_github_install")
        if deploy_key_state not in {"staged_pending_github_install", "pending_operator_setup"}:
            deploy_key_state = "staged_pending_github_install"
    else:
        deploy_key_state = "pending_operator_setup" if status == "pending_key_setup" else "not_requested"
    repo_state = "recorded" if owner_repo else ("awaiting_user" if status == "awaiting_private_repo" else "not_recorded")
    settings_url = f"https://github.com/{owner_repo}/settings/keys" if owner_repo else ""
    return {
        "status": status,
        "model": "public_preparation_then_operator_verification",
        "public_status": public_status,
        "owner_repo": owner_repo,
        "settings_url": settings_url,
        "requested_at": requested_at,
        "private_repo_required": True,
        "deploy_key": {
            "status": deploy_key_state,
            "public_key": staged_public_key,
            "staged_at": staged_at,
            "settings_url": settings_url,
            "write_access_required": True,
            "private_key_storage": "server_side_only" if staged_public_key else "",
        },
        "guidance": (
            "Raven can record the intended private GitHub repository. Backup remains inactive until a dedicated "
            "pod deploy key is minted, installed with write access, and verified by the dashboard/operator rail."
        ),
        "verification": {
            "state": status,
            "setup_intent": public_status,
            "repo": repo_state,
            "deploy_key": deploy_key_state,
            "github_write_check": github_write_check,
            "github_write_check_reason": write_check_reason if github_write_check == "failed_closed" else "",
            "github_write_check_checked_at": write_check_checked_at,
            "backup_activation": backup_activation,
            "restore_proof": "proof_gated",
            "live_restore": "proof_gated",
        },
    }


def request_arclink_backup_deploy_key(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    deployment_id: str,
    key_staging_dir: str,
) -> dict[str, Any]:
    clean_user = str(user_id or "").strip()
    clean_deployment = str(deployment_id or "").strip()
    if not clean_user or not clean_deployment:
        raise ArcLinkDashboardError("ArcLink backup deploy-key staging requires a user and deployment")
    own_txn = not conn.in_transaction
    if own_txn:
        conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT user_id, metadata_json FROM arclink_deployments WHERE deployment_id = ?",
            (clean_deployment,),
        ).fetchone()
        if row is None:
            raise KeyError(clean_deployment)
        if str(row["user_id"] or "") != clean_user:
            raise ArcLinkDashboardError("ArcLink backup deploy-key target does not belong to user")
        session_metadata = _deployment_session_metadata(conn, clean_deployment)
        owner_repo = _safe_backup_owner_repo(str(session_metadata.get("config_backup_owner_repo") or ""))
        if not owner_repo:
            raise ArcLinkDashboardError("ArcLink backup deploy-key staging requires a recorded private GitHub repository")
        metadata = _json_loads(str(row["metadata_json"] or "{}"))
        public_key = _safe_backup_public_key(str(metadata.get("backup_deploy_key_public") or ""))
        now = utc_now_iso()
        if not public_key:
            public_key = _stage_backup_deploy_key_file(
                key_staging_dir=key_staging_dir,
                deployment_id=clean_deployment,
            )
        metadata.update(
            {
                "backup_owner_repo": owner_repo,
                "backup_deploy_key_public": public_key,
                "backup_deploy_key_status": "staged_pending_github_install",
                "backup_deploy_key_staged_at": str(metadata.get("backup_deploy_key_staged_at") or now),
                "backup_deploy_key_private_ref": _backup_key_private_ref(clean_deployment),
                "backup_github_write_check": str(metadata.get("backup_github_write_check") or "not_run"),
                "backup_activation": "not_active",
                "backup_restore_proof": "proof_gated",
            }
        )
        conn.execute(
            """
            UPDATE arclink_deployments
            SET metadata_json = ?, updated_at = ?
            WHERE deployment_id = ?
            """,
            (_safe_json(metadata), now, clean_deployment),
        )
        append_arclink_audit(
            conn,
            action="backup_deploy_key_staged",
            actor_id=clean_user,
            target_kind="deployment",
            target_id=clean_deployment,
            reason="Captain requested backup deploy-key setup from dashboard",
            metadata={
                "owner_repo": owner_repo,
                "deploy_key_status": "staged_pending_github_install",
                "github_write_check": "not_run",
                "backup_activation": "not_active",
            },
            commit=False,
        )
        if own_txn:
            conn.commit()
    except Exception:
        if own_txn:
            conn.rollback()
        raise
    return _deployment_backup_setup(conn, deployment_id=clean_deployment, deployment_metadata=metadata)


def record_arclink_backup_write_check_failed_closed(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    actor_id: str,
    reason: str = "",
) -> dict[str, Any]:
    clean_deployment = str(deployment_id or "").strip()
    clean_actor = str(actor_id or "").strip() or "system:backup_verification"
    if not clean_deployment:
        raise ArcLinkDashboardError("ArcLink backup write check requires a deployment")
    own_txn = not conn.in_transaction
    if own_txn:
        conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT user_id, metadata_json FROM arclink_deployments WHERE deployment_id = ?",
            (clean_deployment,),
        ).fetchone()
        if row is None:
            raise KeyError(clean_deployment)
        metadata = _json_loads(str(row["metadata_json"] or "{}"))
        session_metadata = _deployment_session_metadata(conn, clean_deployment)
        owner_repo = _safe_backup_owner_repo(str(session_metadata.get("config_backup_owner_repo") or metadata.get("backup_owner_repo") or ""))
        if not owner_repo:
            raise ArcLinkDashboardError("ArcLink backup write check requires a recorded private GitHub repository")
        staged_public_key = _safe_backup_public_key(str(metadata.get("backup_deploy_key_public") or ""))
        if not staged_public_key:
            raise ArcLinkDashboardError("ArcLink backup write check requires a staged deploy-key public key")
        now = utc_now_iso()
        safe_reason = _safe_backup_reason(reason)
        metadata.update(
            {
                "backup_owner_repo": owner_repo,
                "backup_deploy_key_status": str(metadata.get("backup_deploy_key_status") or "staged_pending_github_install"),
                "backup_github_write_check": "failed_closed",
                "backup_github_write_check_checked_at": now,
                "backup_github_write_check_reason": safe_reason,
                "backup_activation": "not_active",
                "backup_restore_proof": "proof_gated",
            }
        )
        conn.execute(
            """
            UPDATE arclink_deployments
            SET metadata_json = ?, updated_at = ?
            WHERE deployment_id = ?
            """,
            (_safe_json(metadata), now, clean_deployment),
        )
        append_arclink_audit(
            conn,
            action="backup_write_check_failed_closed",
            actor_id=clean_actor,
            target_kind="deployment",
            target_id=clean_deployment,
            reason="GitHub backup write verification failed closed before live git access",
            metadata={
                "owner_repo": owner_repo,
                "github_write_check": "failed_closed",
                "backup_activation": "not_active",
                "reason": safe_reason,
            },
            commit=False,
        )
        append_arclink_event(
            conn,
            subject_kind="deployment",
            subject_id=clean_deployment,
            event_type="backup_write_check_failed_closed",
            metadata={
                "owner_repo": owner_repo,
                "github_write_check": "failed_closed",
                "backup_activation": "not_active",
            },
            commit=False,
        )
        if own_txn:
            conn.commit()
    except Exception:
        if own_txn:
            conn.rollback()
        raise
    return _deployment_backup_setup(conn, deployment_id=clean_deployment, deployment_metadata=metadata)


def request_arclink_backup_write_check(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    deployment_id: str,
) -> dict[str, Any]:
    clean_user = str(user_id or "").strip()
    clean_deployment = str(deployment_id or "").strip()
    if not clean_user or not clean_deployment:
        raise ArcLinkDashboardError("ArcLink backup write check requires a user and deployment")
    row = conn.execute(
        "SELECT user_id FROM arclink_deployments WHERE deployment_id = ?",
        (clean_deployment,),
    ).fetchone()
    if row is None:
        raise KeyError(clean_deployment)
    if str(row["user_id"] or "") != clean_user:
        raise ArcLinkDashboardError("ArcLink backup write check target does not belong to user")
    return record_arclink_backup_write_check_failed_closed(
        conn,
        deployment_id=clean_deployment,
        actor_id=clean_user,
        reason=ARCLINK_BACKUP_FAILED_CLOSED_REASON,
    )


def _user_dashboard_sections(
    *,
    urls: Mapping[str, str],
    health: list[dict[str, Any]],
    onboarding: Mapping[str, Any],
    model: Mapping[str, Any],
    billing: Mapping[str, Any],
    notion_setup: Mapping[str, Any],
    backup_setup: Mapping[str, Any],
    academy_training: Mapping[str, Any],
) -> list[dict[str, Any]]:
    qmd = next((item for item in health if item["service_name"] == "qmd-mcp"), {"status": "unknown", "checked_at": ""})
    memory = next((item for item in health if item["service_name"] == "memory-synth"), {"status": "unknown", "checked_at": ""})
    health_index = {str(item["service_name"]): item for item in health}
    hermes_url = str(urls.get("hermes") or "").rstrip("/")
    drive_url = str(urls.get("files") or "").strip() or (f"{hermes_url}/drive" if hermes_url else "")
    code_url = str(urls.get("code") or "").strip() or (f"{hermes_url}/code" if hermes_url else "")
    terminal_url = f"{hermes_url}/terminal" if hermes_url else str(urls.get("terminal") or "")
    plugin_links = [
        {"role": "Hermes Dashboard", "url": str(urls.get("hermes") or urls.get("dashboard") or "")},
        {"role": "Drive", "url": drive_url},
        {"role": "Code", "url": code_url},
        {"role": "Terminal", "url": terminal_url},
    ]
    return [
        {
            "section": "deployment_health",
            "label": "Deployment Health",
            "status": _health_status(health),
            "services": health,
        },
        {
            "section": "access_links",
            "label": "Access Links",
            "status": "ready" if urls else "pending",
            "links": [link for link in plugin_links if link["url"]],
        },
        {
            "section": "wrapped",
            "label": "ArcLink Wrapped",
            "status": "ready",
            "summary": "Captain-facing period reports and cadence controls",
        },
        {
            "section": "academy_training",
            "label": "Academy Training",
            "status": str(academy_training.get("status") or "not_started"),
            "summary": str(academy_training.get("summary") or ""),
            "proof_gates": list(academy_training.get("proof_gates") or []),
            "source_count": int(academy_training.get("source_count") or 0),
            "weekly_review_status": str(academy_training.get("weekly_review_status") or "not_started"),
            "evaluation_status": str(academy_training.get("evaluation_status") or "not_started"),
            "graduation_status": str(academy_training.get("graduation_status") or "not_started"),
            "next_review_at": str(academy_training.get("next_review_at") or ""),
            "review_needed_count": int(academy_training.get("review_needed_count") or 0),
            "blocked_source_count": int(academy_training.get("blocked_source_count") or 0),
            "source_state_counts": dict(academy_training.get("source_state_counts") or {}),
        },
        {
            "section": "bot_setup",
            "label": "Bot Setup",
            "status": "contacted" if onboarding.get("first_contacted") else "pending",
            "channel": str(onboarding.get("channel") or ""),
            "handoff_recorded": bool(onboarding.get("handoff_recorded")),
        },
        {
            "section": "backup",
            "label": "Private Backup",
            "status": str(backup_setup.get("status") or "not_requested"),
            "backup": backup_setup,
        },
        {
            "section": "files",
            "label": "Drive",
            "status": "ready" if drive_url else "pending",
            "url": drive_url,
        },
        {
            "section": "code",
            "label": "Code",
            "status": "ready" if code_url else "pending",
            "url": code_url,
        },
        {
            "section": "terminal",
            "label": "Terminal",
            "status": "ready" if terminal_url else "pending",
            "url": terminal_url,
        },
        {
            "section": "hermes",
            "label": "Hermes Dashboard",
            "status": "ready" if urls.get("hermes") else "pending",
            "url": str(urls.get("hermes") or ""),
        },
        {
            "section": "qmd_memory",
            "label": "qmd And Memory",
            "status": _health_status([qmd, memory]),
            "qmd": qmd,
            "memory": memory,
            "notion": notion_setup,
        },
        {
            "section": "skills",
            "label": "Skills",
            "status": str(health_index.get("managed-context", {}).get("status") or "planned"),
            "summary": "managed context and org-published skills",
        },
        {
            "section": "model",
            "label": "Model",
            "status": str(model.get("credential_state") or "unknown"),
            "provider": str(model.get("provider") or ""),
            "model_id": str(model.get("model_id") or ""),
        },
        {
            "section": "billing",
            "label": "Billing",
            "status": str(billing.get("entitlement_state") or "none"),
            "subscriptions": billing.get("subscriptions") or [],
        },
        {
            "section": "security",
            "label": "Security",
            "status": "masked",
            "summary": "session-scoped dashboard access; secrets are reference-only",
        },
        {
            "section": "support",
            "label": "Support",
            "status": "available",
            "summary": "operator support actions are reason-required, queued, and audited",
        },
    ]


def _service_health(conn: sqlite3.Connection, deployment_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT service_name, status, checked_at, detail_json
        FROM arclink_service_health
        WHERE deployment_id = ?
        ORDER BY service_name
        """,
        (deployment_id,),
    ).fetchall()
    return [
        {
            "service_name": str(row["service_name"] or ""),
            "status": str(row["status"] or ""),
            "checked_at": str(row["checked_at"] or ""),
            "detail": _json_loads(str(row["detail_json"] or "{}")),
        }
        for row in rows
    ]


def _deployment_events(conn: sqlite3.Connection, deployment_id: str, *, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT event_id, event_type, metadata_json, created_at
        FROM arclink_events
        WHERE subject_kind = 'deployment' AND subject_id = ?
        ORDER BY created_at DESC, event_id DESC
        LIMIT ?
        """,
        (deployment_id, _limit(limit)),
    ).fetchall()
    return [
        {
            "event_id": str(row["event_id"] or ""),
            "event_type": str(row["event_type"] or ""),
            "metadata": _json_loads(str(row["metadata_json"] or "{}")),
            "created_at": str(row["created_at"] or ""),
        }
        for row in rows
    ]


def _deployment_onboarding(conn: sqlite3.Connection, deployment_id: str) -> dict[str, Any]:
    session = conn.execute(
        """
        SELECT session_id, channel, channel_identity, status, checkout_state, selected_model_id, updated_at
        FROM arclink_onboarding_sessions
        WHERE deployment_id = ?
        ORDER BY updated_at DESC, created_at DESC
        LIMIT 1
        """,
        (deployment_id,),
    ).fetchone()
    if session is None:
        return {
            "session_id": "",
            "channel": "",
            "status": "",
            "checkout_state": "",
            "first_contacted": False,
            "handoff_recorded": False,
        }
    events = {
        str(row["event_type"] or "")
        for row in conn.execute(
            "SELECT event_type FROM arclink_onboarding_events WHERE session_id = ?",
            (str(session["session_id"] or ""),),
        ).fetchall()
    }
    return {
        "session_id": str(session["session_id"] or ""),
        "channel": str(session["channel"] or ""),
        "status": str(session["status"] or ""),
        "checkout_state": str(session["checkout_state"] or ""),
        "selected_model_id": str(session["selected_model_id"] or ""),
        "first_contacted": "first_agent_contact" in events or str(session["status"] or "") in {"first_contacted", "completed"},
        "handoff_recorded": "channel_handoff" in events,
        "updated_at": str(session["updated_at"] or ""),
    }


def _deployment_agent_label(
    conn: sqlite3.Connection,
    deployment: Mapping[str, Any],
    *,
    metadata: Mapping[str, Any],
) -> str:
    candidate = str(metadata.get("agent_name") or metadata.get("display_name") or "").strip()
    if candidate:
        return candidate[:80]
    deployment_id = str(deployment.get("deployment_id") or "").strip()
    if deployment_id:
        row = conn.execute(
            """
            SELECT display_name_hint
            FROM arclink_onboarding_sessions
            WHERE deployment_id = ? AND display_name_hint != ''
            ORDER BY updated_at DESC, created_at DESC
            LIMIT 1
            """,
            (deployment_id,),
        ).fetchone()
        if row is not None and str(row["display_name_hint"] or "").strip():
            return str(row["display_name_hint"] or "").strip()[:80]
    agent_id = str(deployment.get("agent_id") or "").strip()
    if agent_id:
        return agent_id[:80]
    prefix = str(deployment.get("prefix") or "").strip()
    if prefix:
        return f"Agent {prefix.rsplit('-', 1)[-1][:24]}"
    return "Private agent"


def _user_share_inbox_summary(conn: sqlite3.Connection, user_id: str) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT owner_user_id, recipient_user_id, status
        FROM arclink_share_grants
        WHERE owner_user_id = ? OR recipient_user_id = ?
        """,
        (user_id, user_id),
    ).fetchall()
    summary = {
        "pending_owner_approvals": 0,
        "waiting_on_owner_approval": 0,
        "pending_recipient_acceptance": 0,
        "accepted": 0,
        "denied": 0,
        "revoked": 0,
        "expired": 0,
        "total": len(rows),
        "recovery_action": "open_dashboard_share_inbox",
    }
    for row in rows:
        status = str(row["status"] or "")
        is_owner = str(row["owner_user_id"] or "") == user_id
        is_recipient = str(row["recipient_user_id"] or "") == user_id
        if is_owner and status == "pending_owner_approval":
            summary["pending_owner_approvals"] += 1
        if is_recipient and status == "pending_owner_approval":
            summary["waiting_on_owner_approval"] += 1
        if is_recipient and status == "approved":
            summary["pending_recipient_acceptance"] += 1
        if status in {"accepted", "denied", "revoked", "expired"}:
            summary[status] += 1
    summary["attention_count"] = (
        summary["pending_owner_approvals"]
        + summary["waiting_on_owner_approval"]
        + summary["pending_recipient_acceptance"]
    )
    return summary


def read_arclink_user_dashboard(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    deployment_id: str = "",
    recent_limit: int = 10,
) -> dict[str, Any]:
    user = conn.execute("SELECT * FROM arclink_users WHERE user_id = ?", (user_id,)).fetchone()
    if user is None:
        raise KeyError(user_id)
    deployment_args: list[Any] = [user_id]
    deployment_filter = ""
    if deployment_id:
        deployment_filter = "AND deployment_id = ?"
        deployment_args.append(deployment_id)
    deployments = conn.execute(
        f"""
        SELECT *
        FROM arclink_deployments
        WHERE user_id = ? {deployment_filter}
        ORDER BY created_at DESC, deployment_id DESC
        """,
        tuple(deployment_args),
    ).fetchall()
    subscriptions = [
        rowdict(row)
        for row in conn.execute(
            """
            SELECT subscription_id, stripe_customer_id, stripe_subscription_id, status, current_period_end, updated_at
            FROM arclink_subscriptions
            WHERE user_id = ?
            ORDER BY updated_at DESC, subscription_id DESC
            """,
            (user_id,),
        ).fetchall()
    ]
    deployment_cards: list[dict[str, Any]] = []
    wrapped = list_user_wrapped_reports(conn, user_id)
    from arclink_crew_recipes import crew_academy_status
    academy_training = crew_academy_status(conn, user_id=user_id)
    for row in deployments:
        dep = dict(row)
        health = _service_health(conn, str(dep["deployment_id"]))
        onboarding = _deployment_onboarding(conn, str(dep["deployment_id"]))
        metadata = _json_loads(str(dep.get("metadata_json") or "{}"))
        model_id = onboarding.get("selected_model_id") or metadata.get("selected_model_id") or ""
        urls = _deployment_urls(str(dep["prefix"] or ""), str(dep["base_domain"] or ""), metadata)
        notion_setup = _deployment_notion_setup(conn, deployment_id=str(dep["deployment_id"] or ""), urls=urls)
        backup_setup = _deployment_backup_setup(
            conn,
            deployment_id=str(dep["deployment_id"] or ""),
            deployment_metadata=metadata,
        )
        billing = {
            "entitlement_state": str(user["entitlement_state"] or "none"),
            "entitlement_updated_at": str(user["entitlement_updated_at"] or ""),
            "subscriptions": subscriptions,
            "renewal_lifecycle": renewal_lifecycle_for_billing_state(str(user["entitlement_state"] or "")),
        }
        provider = primary_provider({})
        model = {
            "provider": provider,
            "model_id": str(model_id or ""),
            "credential_state": "secret_ref_pending",
        }
        if provider == "chutes":
            boundary = evaluate_chutes_deployment_boundary(
                str(dep["deployment_id"] or ""),
                str(dep["user_id"] or ""),
                metadata,
                env=os.environ,
                billing_state=str(user["entitlement_state"] or ""),
            )
            public_boundary = boundary.to_public()
            model.update(
                {
                    "credential_state": boundary.credential_state,
                    "allow_inference": boundary.allow_inference,
                    "isolation_mode": boundary.isolation_mode,
                    "credential_lifecycle": public_boundary.get("credential_lifecycle", {}),
                    "budget": public_boundary.get("budget", {}),
                    "billing_lifecycle": public_boundary.get("billing_lifecycle", {}),
                    "threshold_continuation": public_boundary.get("threshold_continuation", {}),
                    "provider_note": boundary.reason,
                }
            )
        deployment_cards.append(
            {
                "deployment_id": str(dep["deployment_id"] or ""),
                "agent_label": _deployment_agent_label(conn, dep, metadata=metadata),
                "agent_title": str(dep.get("agent_title") or ""),
                "status": str(dep["status"] or ""),
                "prefix": str(dep["prefix"] or ""),
                "base_domain": str(dep["base_domain"] or ""),
                "access": {"urls": urls},
                "billing": billing,
                "bot_contact": onboarding,
                "model": model,
                "notion_setup": notion_setup,
                "backup_setup": backup_setup,
                "academy_training": academy_training,
                "freshness": {
                    "qmd": next((item for item in health if item["service_name"] == "qmd-mcp"), {"status": "unknown", "checked_at": ""}),
                    "memory": next((item for item in health if item["service_name"] == "memory-synth"), {"status": "unknown", "checked_at": ""}),
                },
                "sections": _user_dashboard_sections(
                    urls=urls,
                    health=health,
                    onboarding=onboarding,
                    model=model,
                    billing=billing,
                    notion_setup=notion_setup,
                    backup_setup=backup_setup,
                    academy_training=academy_training,
                ),
                "service_health": health,
                "recent_events": _deployment_events(conn, str(dep["deployment_id"]), limit=recent_limit),
            }
        )
    return {
        "sections": [{"section": section, "label": section.replace("_", " ").title()} for section in ARCLINK_USER_DASHBOARD_SECTIONS],
        "user": {
            "user_id": str(user["user_id"] or ""),
            "email": str(user["email"] or ""),
            "display_name": str(user["display_name"] or ""),
            "status": str(user["status"] or ""),
        },
        "entitlement": {
            "state": str(user["entitlement_state"] or "none"),
            "updated_at": str(user["entitlement_updated_at"] or ""),
            "renewal_lifecycle": renewal_lifecycle_for_billing_state(str(user["entitlement_state"] or "")),
        },
        "wrapped": wrapped,
        "share_inbox": _user_share_inbox_summary(conn, user_id),
        "academy_training": academy_training,
        "deployments": deployment_cards,
    }


def _time_filter(column: str, since: str, args: list[Any]) -> str:
    clean = str(since or "").strip()
    if not clean:
        return ""
    args.append(clean)
    return f" AND {column} >= ?"


def read_arclink_admin_dashboard(
    conn: sqlite3.Connection,
    *,
    channel: str = "",
    status: str = "",
    deployment_id: str = "",
    user_id: str = "",
    since: str = "",
    recent_limit: int = 25,
) -> dict[str, Any]:
    limit = _limit(recent_limit)
    filters = {
        "channel": str(channel or "").strip().lower(),
        "status": str(status or "").strip().lower(),
        "deployment_id": str(deployment_id or "").strip(),
        "user_id": str(user_id or "").strip(),
        "since": str(since or "").strip(),
    }

    onboarding_args: list[Any] = []
    onboarding_where = "WHERE 1 = 1"
    if filters["channel"]:
        onboarding_where += " AND LOWER(channel) = LOWER(?)"
        onboarding_args.append(filters["channel"])
    if filters["status"]:
        onboarding_where += " AND status = ?"
        onboarding_args.append(filters["status"])
    onboarding_where += _time_filter("created_at", filters["since"], onboarding_args)
    session_counts = [
        rowdict(row)
        for row in conn.execute(
            f"""
            SELECT channel, status, COUNT(*) AS count
            FROM arclink_onboarding_sessions
            {onboarding_where}
            GROUP BY channel, status
            ORDER BY channel, status
            """,
            tuple(onboarding_args),
        ).fetchall()
    ]

    event_args: list[Any] = []
    event_where = "WHERE 1 = 1"
    if filters["channel"]:
        event_where += " AND LOWER(channel) = LOWER(?)"
        event_args.append(filters["channel"])
    event_where += _time_filter("created_at", filters["since"], event_args)
    event_counts = [
        rowdict(row)
        for row in conn.execute(
            f"""
            SELECT event_type, COUNT(*) AS count
            FROM arclink_onboarding_events
            {event_where}
            GROUP BY event_type
            ORDER BY event_type
            """,
            tuple(event_args),
        ).fetchall()
    ]

    deployment_args: list[Any] = []
    deployment_where = "WHERE 1 = 1"
    if filters["deployment_id"]:
        deployment_where += " AND deployment_id = ?"
        deployment_args.append(filters["deployment_id"])
    if filters["user_id"]:
        deployment_where += " AND user_id = ?"
        deployment_args.append(filters["user_id"])
    if filters["status"]:
        deployment_where += " AND status = ?"
        deployment_args.append(filters["status"])
    deployment_where += _time_filter("created_at", filters["since"], deployment_args)

    deployments = [
        {
            "deployment_id": str(row["deployment_id"] or ""),
            "user_id": str(row["user_id"] or ""),
            "prefix": str(row["prefix"] or ""),
            "base_domain": str(row["base_domain"] or ""),
            "status": str(row["status"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }
        for row in conn.execute(
            f"""
            SELECT deployment_id, user_id, prefix, base_domain, status, updated_at, created_at
            FROM arclink_deployments
            {deployment_where}
            ORDER BY created_at DESC, deployment_id DESC
            LIMIT ?
            """,
            (*deployment_args, limit),
        ).fetchall()
    ]

    subscription_args: list[Any] = []
    subscription_where = "WHERE 1 = 1"
    if filters["user_id"]:
        subscription_where += " AND user_id = ?"
        subscription_args.append(filters["user_id"])
    if filters["status"]:
        subscription_where += " AND status = ?"
        subscription_args.append(filters["status"])
    subscription_where += _time_filter("updated_at", filters["since"], subscription_args)
    subscriptions = [
        rowdict(row)
        for row in conn.execute(
            f"""
            SELECT subscription_id, user_id, stripe_customer_id, stripe_subscription_id, status, current_period_end, updated_at
            FROM arclink_subscriptions
            {subscription_where}
            ORDER BY updated_at DESC, subscription_id DESC
            LIMIT ?
            """,
            (*subscription_args, limit),
        ).fetchall()
    ]

    health_args: list[Any] = []
    health_where = "WHERE 1 = 1"
    if filters["deployment_id"]:
        health_where += " AND h.deployment_id = ?"
        health_args.append(filters["deployment_id"])
    if filters["user_id"]:
        health_where += " AND d.user_id = ?"
        health_args.append(filters["user_id"])
    if filters["status"]:
        health_where += " AND h.status = ?"
        health_args.append(filters["status"])
    health_where += _time_filter("h.checked_at", filters["since"], health_args)
    service_health = [
        {
            "deployment_id": str(row["deployment_id"] or ""),
            "service_name": str(row["service_name"] or ""),
            "status": str(row["status"] or ""),
            "checked_at": str(row["checked_at"] or ""),
        }
        for row in conn.execute(
            f"""
            SELECT h.deployment_id, h.service_name, h.status, h.checked_at
            FROM arclink_service_health h
            LEFT JOIN arclink_deployments d ON d.deployment_id = h.deployment_id
            {health_where}
            ORDER BY h.checked_at DESC, h.deployment_id, h.service_name
            LIMIT ?
            """,
            (*health_args, limit),
        ).fetchall()
    ]

    jobs_args: list[Any] = []
    jobs_where = "WHERE 1 = 1"
    if filters["deployment_id"]:
        jobs_where += " AND deployment_id = ?"
        jobs_args.append(filters["deployment_id"])
    if filters["status"]:
        jobs_where += " AND status = ?"
        jobs_args.append(filters["status"])
    jobs_where += _time_filter("requested_at", filters["since"], jobs_args)
    provisioning_jobs = [
        rowdict(row)
        for row in conn.execute(
            f"""
            SELECT job_id, deployment_id, job_kind, status, attempt_count, requested_at, started_at, finished_at, error
            FROM arclink_provisioning_jobs
            {jobs_where}
            ORDER BY requested_at DESC, job_id DESC
            LIMIT ?
            """,
            (*jobs_args, limit),
        ).fetchall()
    ]

    general_event_args: list[Any] = []
    general_event_where = "WHERE 1 = 1"
    if filters["deployment_id"]:
        general_event_where += " AND subject_id = ?"
        general_event_args.append(filters["deployment_id"])
    general_event_where += _time_filter("created_at", filters["since"], general_event_args)
    events = [
        {
            "event_id": str(row["event_id"] or ""),
            "subject_kind": str(row["subject_kind"] or ""),
            "subject_id": str(row["subject_id"] or ""),
            "event_type": str(row["event_type"] or ""),
            "deployment_id": str(row["subject_id"] or ""),
            "created_at": str(row["created_at"] or ""),
        }
        for row in conn.execute(
            f"""
            SELECT event_id, subject_kind, subject_id, event_type, created_at
            FROM arclink_events
            {general_event_where}
            ORDER BY created_at DESC, event_id DESC
            LIMIT ?
            """,
            (*general_event_args, limit),
        ).fetchall()
    ]

    dns_args: list[Any] = []
    dns_where = """
    WHERE e.event_type = 'dns_drift'
      AND COALESCE(d.status, '') NOT IN ('cancelled', 'torn_down', 'teardown_complete')
    """
    if filters["deployment_id"]:
        dns_where += " AND e.subject_id = ?"
        dns_args.append(filters["deployment_id"])
    dns_where += _time_filter("e.created_at", filters["since"], dns_args)
    dns_drift = [
        {
            "deployment_id": str(row["subject_id"] or ""),
            "metadata": _json_loads(str(row["metadata_json"] or "{}")),
            "created_at": str(row["created_at"] or ""),
        }
        for row in conn.execute(
            f"""
            SELECT e.subject_id, e.metadata_json, e.created_at
            FROM arclink_events e
            LEFT JOIN arclink_deployments d ON d.deployment_id = e.subject_id
            {dns_where}
            ORDER BY e.created_at DESC, e.event_id DESC
            LIMIT ?
            """,
            (*dns_args, limit),
        ).fetchall()
    ]

    audit_args: list[Any] = []
    audit_where = "WHERE 1 = 1"
    if filters["deployment_id"]:
        audit_where += " AND target_id = ?"
        audit_args.append(filters["deployment_id"])
    audit_where += _time_filter("created_at", filters["since"], audit_args)
    audit_rows = [
        {
            "audit_id": str(row["audit_id"] or ""),
            "actor_id": str(row["actor_id"] or ""),
            "action": str(row["action"] or ""),
            "target_kind": str(row["target_kind"] or ""),
            "target_id": str(row["target_id"] or ""),
            "reason": str(row["reason"] or ""),
            "created_at": str(row["created_at"] or ""),
        }
        for row in conn.execute(
            f"""
            SELECT audit_id, actor_id, action, target_kind, target_id, reason, created_at
            FROM arclink_audit_log
            {audit_where}
            ORDER BY created_at DESC, audit_id DESC
            LIMIT ?
            """,
            (*audit_args, limit),
        ).fetchall()
    ]

    action_args: list[Any] = []
    action_where = "WHERE 1 = 1"
    if filters["deployment_id"]:
        action_where += " AND target_id = ?"
        action_args.append(filters["deployment_id"])
    if filters["status"]:
        action_where += " AND status = ?"
        action_args.append(filters["status"])
    action_where += _time_filter("created_at", filters["since"], action_args)
    action_intents = [
        {
            "action_id": str(row["action_id"] or ""),
            "admin_id": str(row["admin_id"] or ""),
            "action_type": str(row["action_type"] or ""),
            "target_kind": str(row["target_kind"] or ""),
            "target_id": str(row["target_id"] or ""),
            "status": str(row["status"] or ""),
            "reason": str(row["reason"] or ""),
            "audit_id": str(row["audit_id"] or ""),
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }
        for row in conn.execute(
            f"""
            SELECT action_id, admin_id, action_type, target_kind, target_id, status, reason, audit_id, created_at, updated_at
            FROM arclink_action_intents
            {action_where}
            ORDER BY created_at DESC, action_id DESC
            LIMIT ?
            """,
            (*action_args, limit),
        ).fetchall()
    ]

    failure_job_args: list[Any] = []
    failure_job_where = "WHERE status = 'failed'"
    if filters["deployment_id"]:
        failure_job_where += " AND deployment_id = ?"
        failure_job_args.append(filters["deployment_id"])
    failure_job_where += _time_filter("COALESCE(finished_at, requested_at)", filters["since"], failure_job_args)
    recent_failures = [
        {"kind": "provisioning_job", **rowdict(row)}
        for row in conn.execute(
            f"""
            SELECT job_id, deployment_id, job_kind, status, error, finished_at AS occurred_at
            FROM arclink_provisioning_jobs
            {failure_job_where}
            ORDER BY COALESCE(finished_at, requested_at) DESC, job_id DESC
            LIMIT ?
            """,
            (*failure_job_args, limit),
        ).fetchall()
    ]
    failure_health_args: list[Any] = []
    failure_health_where = "WHERE h.status IN ('degraded', 'unhealthy', 'failed')"
    if filters["deployment_id"]:
        failure_health_where += " AND h.deployment_id = ?"
        failure_health_args.append(filters["deployment_id"])
    if filters["user_id"]:
        failure_health_where += " AND d.user_id = ?"
        failure_health_args.append(filters["user_id"])
    failure_health_where += _time_filter("h.checked_at", filters["since"], failure_health_args)
    recent_failures.extend(
        {
            "kind": "service_health",
            "deployment_id": str(row["deployment_id"] or ""),
            "service_name": str(row["service_name"] or ""),
            "status": str(row["status"] or ""),
            "occurred_at": str(row["checked_at"] or ""),
        }
        for row in conn.execute(
            f"""
            SELECT h.deployment_id, h.service_name, h.status, h.checked_at
            FROM arclink_service_health h
            LEFT JOIN arclink_deployments d ON d.deployment_id = h.deployment_id
            {failure_health_where}
            ORDER BY h.checked_at DESC, h.deployment_id, h.service_name
            LIMIT ?
            """,
            (*failure_health_args, limit),
        ).fetchall()
    )
    user_args: list[Any] = []
    user_where = "WHERE 1 = 1"
    if filters["user_id"]:
        user_where += " AND user_id = ?"
        user_args.append(filters["user_id"])
    if filters["status"]:
        user_where += " AND entitlement_state = ?"
        user_args.append(filters["status"])
    user_where += _time_filter("created_at", filters["since"], user_args)
    users = [
        {
            "user_id": str(row["user_id"] or ""),
            "email": str(row["email"] or ""),
            "display_name": str(row["display_name"] or ""),
            "status": str(row["status"] or ""),
            "stripe_customer_id": str(row["stripe_customer_id"] or ""),
            "entitlement_state": str(row["entitlement_state"] or ""),
            "created_at": str(row["created_at"] or ""),
        }
        for row in conn.execute(
            f"""
            SELECT user_id, email, display_name, status, stripe_customer_id, entitlement_state, created_at
            FROM arclink_users
            {user_where}
            ORDER BY created_at DESC, user_id DESC
            LIMIT ?
            """,
            (*user_args, limit),
        ).fetchall()
    ]
    user_count = _count(conn, "SELECT COUNT(*) FROM arclink_users")
    now = utc_now_iso()
    active_user_sessions = _count(
        conn,
        """
        SELECT COUNT(*)
        FROM arclink_user_sessions
        WHERE status = 'active' AND revoked_at = '' AND expires_at > ?
        """,
        (now,),
    )
    active_admin_sessions = _count(
        conn,
        """
        SELECT COUNT(*)
        FROM arclink_admin_sessions
        WHERE status = 'active' AND revoked_at = '' AND expires_at > ?
        """,
        (now,),
    )
    admin_count = _count(conn, "SELECT COUNT(*) FROM arclink_admins WHERE status = 'active'")
    rate_limit_observations = _count(conn, "SELECT COUNT(*) FROM rate_limits")
    public_bot_sessions = _count(
        conn,
        "SELECT COUNT(*) FROM arclink_onboarding_sessions WHERE LOWER(channel) IN ('telegram', 'discord')",
    )
    event_count = _count(conn, "SELECT COUNT(*) FROM arclink_events")
    audit_count = _count(conn, "SELECT COUNT(*) FROM arclink_audit_log")
    queued_action_count = _count(conn, "SELECT COUNT(*) FROM arclink_action_intents WHERE status = 'queued'")
    failed_job_count = _count(conn, "SELECT COUNT(*) FROM arclink_provisioning_jobs WHERE status = 'failed'")
    wrapped = wrapped_admin_aggregate(conn)
    admin_sections = [
        {
            "section": "onboarding_funnel",
            "label": "Onboarding Funnel",
            "status": "ready",
            "counts": {"sessions": sum(int(row["count"]) for row in session_counts), "events": sum(int(row["count"]) for row in event_counts)},
        },
        {"section": "users", "label": "Users", "status": "ready", "counts": {"users": user_count}},
        {
            "section": "deployments",
            "label": "Deployments",
            "status": "ready",
            "counts": {"visible": len(deployments)},
        },
        {
            "section": "wrapped",
            "label": "ArcLink Wrapped",
            "status": "attention" if wrapped["failed_count"] else "ready",
            "counts": {
                "due": wrapped["due_count"],
                "failed": wrapped["failed_count"],
                "reports": sum(int(count) for count in wrapped["reports_by_status"].values()),
            },
        },
        {
            "section": "payments",
            "label": "Payments",
            "status": "ready",
            "counts": {"subscriptions": len(subscriptions)},
        },
        {
            "section": "infrastructure",
            "label": "Infrastructure",
            "status": "degraded" if recent_failures or dns_drift else "ready",
            "counts": {"service_health": len(service_health), "dns_drift": len(dns_drift), "failed_jobs": failed_job_count},
        },
        {
            "section": "bots",
            "label": "Bots",
            "status": "ready",
            "counts": {"public_bot_sessions": public_bot_sessions},
        },
        {
            "section": "security_abuse",
            "label": "Security And Abuse",
            "status": "ready",
            "counts": {
                "active_admins": admin_count,
                "active_user_sessions": active_user_sessions,
                "active_admin_sessions": active_admin_sessions,
                "rate_limit_observations": rate_limit_observations,
            },
        },
        {
            "section": "releases_maintenance",
            "label": "Releases And Maintenance",
            "status": "ready",
            "counts": {"rollout_actions": sum(1 for row in action_intents if row["action_type"] == "rollout")},
        },
        {
            "section": "logs_events",
            "label": "Logs And Events",
            "status": "ready",
            "counts": {"events": event_count, "recent_failures": len(recent_failures[:limit])},
        },
        {"section": "audit", "label": "Audit", "status": "ready", "counts": {"audit_rows": audit_count}},
        {
            "section": "queued_actions",
            "label": "Queued Actions",
            "status": "pending" if queued_action_count else "clear",
            "counts": {"queued": queued_action_count},
        },
    ]

    return {
        "filters": filters,
        "sections": admin_sections,
        "onboarding_funnel": {"sessions": session_counts, "events": event_counts},
        "users": users,
        "subscriptions": subscriptions,
        "deployments": deployments,
        "service_health": service_health,
        "dns_drift": dns_drift,
        "provisioning_jobs": provisioning_jobs,
        "provisioning_readiness": control_node_provisioning_readiness(conn),
        "action_intents": action_intents,
        "action_execution_readiness": admin_action_execution_readiness(),
        "wrapped": wrapped,
        "events": events,
        "audit_rows": audit_rows,
        "audit": audit_rows,
        "recent_failures": recent_failures[:limit],
        "active_sessions": {"user": active_user_sessions, "admin": active_admin_sessions},
    }


def queue_arclink_admin_action(
    conn: sqlite3.Connection,
    *,
    admin_id: str,
    action_type: str,
    target_kind: str,
    target_id: str,
    reason: str,
    idempotency_key: str,
    metadata: Mapping[str, Any] | None = None,
    action_id: str = "",
) -> dict[str, Any]:
    clean_admin = str(admin_id or "").strip()
    clean_action = str(action_type or "").strip().lower()
    clean_target_kind = str(target_kind or "").strip().lower()
    clean_target_id = str(target_id or "").strip()
    clean_reason = str(reason or "").strip()
    clean_key = str(idempotency_key or "").strip()
    if not clean_admin:
        raise ArcLinkDashboardError("ArcLink admin actions require an admin id")
    if clean_action not in ARCLINK_ADMIN_ACTION_TYPES:
        raise ArcLinkDashboardError(f"unsupported ArcLink admin action type: {clean_action or 'blank'}")
    if _admin_action_worker_support(clean_action) != "wired":
        raise ArcLinkDashboardError(f"ArcLink admin action type is not queueable until worker support lands: {clean_action}")
    if clean_target_kind not in ARCLINK_ADMIN_TARGET_KINDS or not clean_target_id:
        raise ArcLinkDashboardError("ArcLink admin actions require a supported target")
    allowed_target_kinds = tuple(ARCLINK_ADMIN_ACTION_SUPPORT.get(clean_action, {}).get("target_kinds") or ())
    if allowed_target_kinds and clean_target_kind not in allowed_target_kinds:
        allowed = ", ".join(str(kind) for kind in allowed_target_kinds)
        raise ArcLinkDashboardError(
            f"ArcLink admin action {clean_action} does not support target kind {clean_target_kind}; allowed: {allowed}"
        )
    if not clean_reason:
        raise ArcLinkDashboardError("ArcLink admin actions require a reason")
    if not clean_key:
        raise ArcLinkDashboardError("ArcLink admin actions require an idempotency key")
    metadata_json = _safe_json(metadata)

    existing = conn.execute(
        "SELECT * FROM arclink_action_intents WHERE idempotency_key = ?",
        (clean_key,),
    ).fetchone()
    if existing is not None:
        row = dict(existing)
        if (
            row["admin_id"] != clean_admin
            or row["action_type"] != clean_action
            or row["target_kind"] != clean_target_kind
            or row["target_id"] != clean_target_id
        ):
            raise ArcLinkDashboardError("ArcLink admin action idempotency key is already bound to another request")
        return row

    clean_action_id = action_id.strip() if action_id else _stable_action_id(clean_key)
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO arclink_action_intents (
          action_id, admin_id, action_type, target_kind, target_id, status,
          idempotency_key, reason, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?)
        """,
        (
            clean_action_id,
            clean_admin,
            clean_action,
            clean_target_kind,
            clean_target_id,
            clean_key,
            clean_reason,
            metadata_json,
            now,
            now,
        ),
    )
    audit_id = append_arclink_audit(
        conn,
        action=f"admin_action:{clean_action}",
        actor_id=clean_admin,
        target_kind=clean_target_kind,
        target_id=clean_target_id,
        reason=clean_reason,
        metadata={"action_id": clean_action_id, "idempotency_key": clean_key, "queued": True},
        commit=False,
    )
    conn.execute(
        "UPDATE arclink_action_intents SET audit_id = ? WHERE action_id = ?",
        (audit_id, clean_action_id),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM arclink_action_intents WHERE action_id = ?", (clean_action_id,)).fetchone())
