#!/usr/bin/env python3
"""Operator Raven command surface: read/dry-run previews plus real action queueing.

Read commands (``status``, ``fleet_list``, ``user_lookup``, ``billing_status``,
``backup_status``, ``workspace_status``, ``academy_status``, ``upgrade_check``,
``upgrade_policy``, ``action_status``) never mutate. The
mutation commands (``pod_repair``, ``rollout``, ``host_upgrade``,
``pin_upgrade``, ``upgrade_sweep``, ``fleet_drain``, ``fleet_resume``) behave in four
ways:

* ``--dry-run`` -> a preview that changes nothing (the historical behavior).
* no ``--dry-run`` and no operator ``actor_id`` -> fail closed (read-only
  refusal). The adapter must prove operator identity before a real action runs.
* no ``--dry-run`` with an operator ``actor_id`` but no explicit confirmation
  token -> refuse. The operator must append ``confirm`` or the configured
  approval code after reviewing a dry-run preview.
* no ``--dry-run`` with an operator ``actor_id`` and explicit confirmation ->
  QUEUE a real audited intent that the ArcLink action worker / enrollment
  provisioner executes asynchronously, or apply the modeled local fleet-state
  mutation with audit/event rows. Operator Raven never runs Docker/SSH/provider
  commands inline. Live mutation stays gated by the executor adapter and the
  per-action live proof gate.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from arclink_secrets_regex import redact_secret_material
from arclink_upgrade_policy import PIN_UPGRADE_COMPONENTS, STATEFUL_PIN_UPGRADE_COMPONENTS


class OperatorRavenError(ValueError):
    pass


UpgradeCheckRunner = Callable[[], Mapping[str, Any]]


@dataclass(frozen=True)
class OperatorRavenCommand:
    name: str
    args: tuple[str, ...]
    dry_run: bool
    raw_text: str
    component: str = ""
    confirmed: bool = False


_COMMAND_ALIASES = {
    "operator_status": "status",
    "operatorstatus": "status",
    "raven_status": "status",
    "ravenstatus": "status",
    "control_status": "status",
    "controlstatus": "status",
    "op_status": "status",
    "opstatus": "status",
    "operator_agents": "agents",
    "operatoragents": "agents",
    "agents": "agents",
    "agent_roster": "agents",
    "agentroster": "agents",
    "crew": "agents",
    "pods": "agents",
    "arcpods": "agents",
    "operator_fleet": "fleet_list",
    "operatorfleet": "fleet_list",
    "fleet": "fleet_list",
    "fleet_list": "fleet_list",
    "fleetlist": "fleet_list",
    "fleet_drain": "fleet_drain",
    "fleetdrain": "fleet_drain",
    "drain_fleet": "fleet_drain",
    "drainfleet": "fleet_drain",
    "drain_worker": "fleet_drain",
    "drainworker": "fleet_drain",
    "worker_drain": "fleet_drain",
    "workerdrain": "fleet_drain",
    "fleet_resume": "fleet_resume",
    "fleetresume": "fleet_resume",
    "fleet_undrain": "fleet_resume",
    "fleetundrain": "fleet_resume",
    "undrain_fleet": "fleet_resume",
    "undrainfleet": "fleet_resume",
    "resume_worker": "fleet_resume",
    "resumeworker": "fleet_resume",
    "worker_resume": "fleet_resume",
    "workerresume": "fleet_resume",
    "worker_undrain": "fleet_resume",
    "workerundrain": "fleet_resume",
    "worker_probe": "worker_probe",
    "workerprobe": "worker_probe",
    "probe_worker": "worker_probe",
    "probeworker": "worker_probe",
    "operator_user": "user_lookup",
    "operatoruser": "user_lookup",
    "user_lookup": "user_lookup",
    "userlookup": "user_lookup",
    "user": "user_lookup",
    "billing_status": "billing_status",
    "billingstatus": "billing_status",
    "operator_billing": "billing_status",
    "operatorbilling": "billing_status",
    "billing": "billing_status",
    "credit_status": "billing_status",
    "creditstatus": "billing_status",
    "credits_status": "billing_status",
    "creditsstatus": "billing_status",
    "backup_status": "backup_status",
    "backupstatus": "backup_status",
    "operator_backup": "backup_status",
    "operatorbackup": "backup_status",
    "backups": "backup_status",
    "backup": "backup_status",
    "workspace_status": "workspace_status",
    "workspacestatus": "workspace_status",
    "operator_workspace": "workspace_status",
    "operatorworkspace": "workspace_status",
    "memory_status": "workspace_status",
    "memorystatus": "workspace_status",
    "qmd_status": "workspace_status",
    "qmdstatus": "workspace_status",
    "notion_status": "workspace_status",
    "notionstatus": "workspace_status",
    "ssot_status": "workspace_status",
    "ssotstatus": "workspace_status",
    "pod_repair": "pod_repair",
    "podrepair": "pod_repair",
    "repair_pod": "pod_repair",
    "repairpod": "pod_repair",
    "operator_upgrade_check": "upgrade_check",
    "operatorupgradecheck": "upgrade_check",
    "upgrade_check": "upgrade_check",
    "upgradecheck": "upgrade_check",
    "upgrade_hermes": "upgrade_check",
    "upgradehermes": "upgrade_check",
    "hermes_upgrade": "upgrade_check",
    "hermesupgrade": "upgrade_check",
    "upgrade_policy": "upgrade_policy",
    "upgradepolicy": "upgrade_policy",
    "update_policy": "upgrade_policy",
    "updatepolicy": "upgrade_policy",
    "dependency_policy": "upgrade_policy",
    "dependencypolicy": "upgrade_policy",
    "dependency_updates": "upgrade_policy",
    "dependencyupdates": "upgrade_policy",
    "updates": "upgrade_policy",
    "upgrade_sweep": "upgrade_sweep",
    "upgradesweep": "upgrade_sweep",
    "update_sweep": "upgrade_sweep",
    "updatesweep": "upgrade_sweep",
    "upgrade_all": "upgrade_sweep",
    "upgradeall": "upgrade_sweep",
    "update_all": "upgrade_sweep",
    "updateall": "upgrade_sweep",
    "apply_updates": "upgrade_sweep",
    "applyupdates": "upgrade_sweep",
    "pin_upgrade_all": "upgrade_sweep",
    "pinupgradeall": "upgrade_sweep",
    "host_upgrade": "host_upgrade",
    "hostupgrade": "host_upgrade",
    "control_upgrade": "host_upgrade",
    "controlupgrade": "host_upgrade",
    "self_upgrade": "host_upgrade",
    "selfupgrade": "host_upgrade",
    "apply_upgrade": "host_upgrade",
    "applyupgrade": "host_upgrade",
    "upgrade": "host_upgrade",
    "update": "host_upgrade",
    "pin_upgrade": "pin_upgrade",
    "pinupgrade": "pin_upgrade",
    "component_upgrade": "pin_upgrade",
    "componentupgrade": "pin_upgrade",
    "upgrade_component": "pin_upgrade",
    "upgradecomponent": "pin_upgrade",
    "upgrade_menu": "upgrade_menu",
    "upgrademenu": "upgrade_menu",
    "upgrades": "upgrade_menu",
    "upgrade_apply": "upgrade_apply",
    "upgradeapply": "upgrade_apply",
    "upgrade_go": "upgrade_apply",
    "upgradego": "upgrade_apply",
    "rollout_plan": "rollout",
    "rolloutplan": "rollout",
    "rollout": "rollout",
    "rollout_execute": "rollout",
    "rolloutexecute": "rollout",
    "rollout_apply": "rollout",
    "rolloutapply": "rollout",
    "upgrade_plan": "rollout",
    "upgradeplan": "rollout",
    "arcpod_rollout": "rollout",
    "arcpodrollout": "rollout",
    "action_status": "action_status",
    "actionstatus": "action_status",
    "actions": "action_status",
    "ops_status": "action_status",
    "opsstatus": "action_status",
    "jobs": "action_status",
    "academy_status": "academy_status",
    "academystatus": "academy_status",
    "academy": "academy_status",
    "crew_academy": "academy_status",
    "crewacademy": "academy_status",
    "academy_roster": "academy_roster",
    "academyroster": "academy_roster",
    "academy_graduates": "academy_roster",
    "academygraduates": "academy_roster",
    "graduates": "academy_roster",
    "trainees": "academy_roster",
    "academy_trainees": "academy_roster",
    "roster": "academy_roster",
}

# Commands that, outside of --dry-run, queue or apply a real audited mutation.
# The adapter must supply an operator actor identity plus an explicit
# confirmation token (or clear any configured approval code) before these run
# for real.
MUTATING_COMMANDS = frozenset({"pod_repair", "rollout", "host_upgrade", "pin_upgrade", "upgrade_sweep", "fleet_drain", "fleet_resume"})

_POD_REPAIR_ACTIONS = ("restart", "reprovision", "dns_repair")

_DRY_RUN_TOKENS = {"--dry-run", "dry-run"}
_CONFIRM_TOKENS = {"--confirm", "--confirmed", "confirm", "confirmed"}

_SECRETISH_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization|bearer|oauth|webhook[_-]?secret)"
)


def _operator_token(value: str) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def parse_operator_raven_command(text: str) -> OperatorRavenCommand | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    parts = raw.split()
    first = parts[0].split("@", 1)[0].strip().lower()
    args = list(parts[1:])
    if first in {"operator", "raven"} and args:
        first = args.pop(0).strip().lower()
    token = first.lstrip("/!").replace("-", "_")
    normalized = re.sub(r"[^a-z0-9_]", "", token)
    name = _COMMAND_ALIASES.get(normalized)
    if not name:
        return None
    dry_run = any(_operator_token(arg) in _DRY_RUN_TOKENS for arg in args)
    confirmed = any(_operator_token(arg) in _CONFIRM_TOKENS for arg in args)
    clean_args = tuple(
        arg
        for arg in args
        if _operator_token(arg) not in _DRY_RUN_TOKENS and _operator_token(arg) not in _CONFIRM_TOKENS
    )
    component = _infer_pin_component(normalized, clean_args) if name == "pin_upgrade" else ""
    # A bare /upgrade or /pin_upgrade (no arguments, no confirm, no dry-run) is
    # a menu request: it renders the one-tap upgrade menu and mutates nothing,
    # so it must not trip the transports' mutating-command approval-code wall.
    if (
        name in {"host_upgrade", "pin_upgrade"}
        and not clean_args
        and not confirmed
        and not dry_run
    ):
        name = "upgrade_menu"
    return OperatorRavenCommand(
        name=name,
        args=clean_args,
        dry_run=dry_run,
        raw_text=raw,
        component=component,
        confirmed=confirmed,
    )


def _infer_pin_component(normalized: str, args: Sequence[str]) -> str:
    # Use the same option-aware scan as rollout so flags like --batch-size N do
    # not get mistaken for the component name.
    candidate = _first_non_option_arg(args).strip().lower()
    if candidate:
        return candidate
    # Allow shorthand like /upgrade_hermes -> component "hermes" if it ever maps
    # here; today those alias to upgrade_check, but keep the inference robust.
    for component in PIN_UPGRADE_COMPONENTS:
        if component in normalized:
            return component
    return ""


def operator_raven_command_requested(text: str) -> bool:
    return parse_operator_raven_command(text) is not None


def operator_raven_command_is_mutating(text: str) -> bool:
    """True when ``text`` would queue a real action (not a --dry-run preview)."""
    command = parse_operator_raven_command(text)
    if command is None:
        return False
    return command.name in MUTATING_COMMANDS and not command.dry_run


_APPROVAL_CODE_KEYS = ("ARCLINK_OPERATOR_TELEGRAM_APPROVAL_CODE", "ARCLINK_OPERATOR_APPROVAL_CODE")


def operator_approval_code(env: Mapping[str, str] | None = None) -> str:
    """Resolve the configured operator approval code from an env mapping.

    Returns the first non-blank value of ARCLINK_OPERATOR_TELEGRAM_APPROVAL_CODE
    or ARCLINK_OPERATOR_APPROVAL_CODE, or "" when no code is configured (no code
    required).
    """
    source = env or {}
    for key in _APPROVAL_CODE_KEYS:
        value = str(source.get(key) or "").strip()
        if value:
            return value
    return ""


def strip_operator_approval_code(text: str, code: str) -> tuple[bool, str]:
    """Verify and strip a trailing operator approval code.

    When ``code`` is blank no code is required and the text passes through. When
    a code is configured, the last whitespace-delimited token must match it via
    a constant-time compare; the verified code is then stripped so the command
    parser never treats it as an argument. Returns ``(ok, cleaned_text)``.
    """
    configured = str(code or "").strip()
    raw = str(text or "")
    if not configured:
        return True, raw
    stripped = raw.strip()
    if not stripped:
        return False, raw
    head, _, tail = stripped.rpartition(" ")
    supplied = tail.strip()
    if not head or not supplied or not hmac.compare_digest(supplied, configured):
        return False, raw
    return True, head.strip()


def dispatch_operator_raven_command(
    conn: sqlite3.Connection,
    text: str,
    *,
    env: Mapping[str, str] | None = None,
    upgrade_check_runner: UpgradeCheckRunner | None = None,
    actor_id: str = "",
    idempotency_key: str = "",
) -> dict[str, Any]:
    command = parse_operator_raven_command(text)
    if command is None:
        return {"handled": False, "message": "", "mutation_performed": False}
    handlers = {
        "status": _handle_status,
        "agents": _handle_agents,
        "fleet_list": _handle_fleet_list,
        "fleet_drain": _handle_fleet_drain,
        "fleet_resume": _handle_fleet_resume,
        "worker_probe": _handle_worker_probe,
        "user_lookup": _handle_user_lookup,
        "billing_status": _handle_billing_status,
        "backup_status": _handle_backup_status,
        "workspace_status": _handle_workspace_status,
        "pod_repair": _handle_pod_repair,
        "upgrade_check": _handle_upgrade_check,
        "upgrade_policy": _handle_upgrade_policy,
        "upgrade_sweep": _handle_upgrade_sweep,
        "upgrade_menu": _handle_upgrade_menu,
        "upgrade_apply": _handle_upgrade_apply,
        "host_upgrade": _handle_host_upgrade,
        "pin_upgrade": _handle_pin_upgrade,
        "rollout": _handle_rollout,
        "action_status": _handle_action_status,
        "academy_status": _handle_academy_status,
        "academy_roster": _handle_academy_roster,
    }
    result = handlers[command.name](
        conn,
        command,
        env=env or {},
        upgrade_check_runner=upgrade_check_runner,
        actor_id=str(actor_id or "").strip(),
        idempotency_key=str(idempotency_key or "").strip(),
    )
    result.setdefault("handled", True)
    result.setdefault("command", command.name)
    result.setdefault("mutation_performed", False)
    result["message"] = _redact_text(str(result.get("message") or ""))
    return result


def _require_operator_actor(actor_id: str, command_label: str) -> dict[str, Any] | None:
    if actor_id:
        return None
    return {
        "message": (
            f"{command_label} runs a real, audited action and requires a verified operator identity. "
            f"This call supplied none, so it failed closed. Preview safely with --dry-run, or run it "
            f"from the configured operator channel."
        ),
    }


def _require_operator_confirmation(command: OperatorRavenCommand) -> dict[str, Any] | None:
    if command.confirmed:
        return None
    return {
        "message": (
            "That is a real Operator Raven action. Preview it with `--dry-run` first, then append "
            "`confirm` or your configured operator approval code to queue it. No action was queued."
        ),
    }


def _executor_adapter(env: Mapping[str, str]) -> str:
    return str(env.get("ARCLINK_EXECUTOR_ADAPTER") or "disabled").strip().lower() or "disabled"


def _action_idempotency_key(provided: str, *, kind: str, target: str) -> str:
    clean = str(provided or "").strip()
    if clean:
        digest = hashlib.sha256(f"{kind}:{target}:{clean}".encode("utf-8")).hexdigest()[:24]
        return f"opraven-{kind}-{digest}"
    return f"opraven-{kind}-{secrets.token_hex(8)}"


def _handle_status(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    from arclink_dashboard import admin_action_execution_readiness, control_node_provisioning_readiness
    from arclink_fleet import fleet_capacity_summary

    capacity = _safe_call(lambda: fleet_capacity_summary(conn), default={"hosts": [], "available_slots": 0})
    readiness = _safe_call(lambda: admin_action_execution_readiness(env=env), default={"executor_adapter": "disabled", "action_support": {}})
    provisioning_readiness = _safe_call(
        lambda: control_node_provisioning_readiness(conn, env=env),
        default={
            "summary": "control plane up; ArcPod provisioning status unavailable",
            "state": "unknown",
            "next_action": "Open the admin dashboard readiness panel.",
        },
    )
    provisioning = str(provisioning_readiness.get("summary") or "control plane up; ArcPod provisioning status unavailable")
    user_counts = _count_by_status(conn, "arclink_users")
    deployment_counts = _count_by_status(conn, "arclink_deployments")
    rollout_counts = _count_by_status(conn, "arclink_rollouts")
    support = readiness.get("action_support") if isinstance(readiness, Mapping) else {}
    queueable = sum(1 for item in (support or {}).values() if bool(item.get("queueable")))
    adapter = str(readiness.get("executor_adapter") or "disabled")
    action_counts = _operator_action_status_counts(conn)
    lines = [
        "Operator Raven status",
        f"Provisioning: {provisioning}",
        f"Fleet: {int(capacity.get('active_hosts') or 0)} active / {int(capacity.get('total_hosts') or 0)} total worker(s)",
        f"Users: {_format_counts(user_counts)}",
        f"Deployments: {_format_counts(deployment_counts)}",
        f"Rollouts: {_format_counts(rollout_counts)}",
        f"Admin actions: {queueable} queueable via {adapter}",
        f"Queued/running operator actions: {_format_counts(action_counts)}",
        "Live actions honor ARCLINK_EXECUTOR_ADAPTER (fake = record-only); set it to local/ssh after the live proof gate.",
        "Act: /pod_repair <deployment> [restart|reprovision|dns_repair], /rollout <target>, /upgrade, /pin_upgrade <component>, /upgrade_sweep, /fleet_drain <worker>, /fleet_resume <worker> (add --dry-run to preview; append confirm or the operator approval code to queue or apply)",
        "Next: /billing_status, /backup_status, /workspace_status, /upgrade_policy, /operator_fleet, /user_lookup <query>, /academy_status <query>, /academy_roster [query], /action_status, then act with the commands above",
        "Live proof still required for live mutation: PG-PROD, PG-BOTS, PG-PROVIDER, PG-PROVISION, PG-UPGRADE",
    ]
    return {
        "message": "\n".join(lines),
        "readiness": provisioning,
        "provisioning_readiness": provisioning_readiness,
    }


def _handle_agents(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    rows = _deployment_rows(conn)
    operator_rows = [row for row in rows if _deployment_is_operator(row)]
    captain_rows = [row for row in rows if not _deployment_is_operator(row)]
    active_captains = [row for row in captain_rows if str(row.get("status") or "") == "active"]
    captain_counts: dict[str, int] = {}
    for row in captain_rows:
        status = str(row.get("status") or "unknown")
        captain_counts[status] = captain_counts.get(status, 0) + 1
    legacy_active = _legacy_agent_count(conn)
    lines = [
        "Operator Raven ArcLink agents",
        f"Captain ArcPods: {len(captain_rows)} total ({_format_counts(captain_counts)}), {len(active_captains)} active",
        f"Operator Hermes: {_operator_agent_line(operator_rows)}",
        f"Legacy Shared-Host agent rows: {legacy_active} active (not the Sovereign ArcPod roster)",
        "",
        "Active Captain Agents:",
    ]
    if active_captains:
        for row in active_captains[:12]:
            deployment_id = str(row.get("deployment_id") or "")
            prefix = str(row.get("prefix") or "")
            label = _deployment_label(row)
            health = _deployment_health_summary(conn, deployment_id)
            lines.append(
                f"- {label}: {deployment_id} prefix={prefix or 'unset'} user={row.get('user_id') or 'unknown'} "
                f"status={row.get('status') or 'unknown'} health={health}"
            )
        if len(active_captains) > 12:
            lines.append(f"... {len(active_captains) - 12} more active Captain Agent(s) omitted.")
    else:
        lines.append("- none")
    non_active = [row for row in captain_rows if str(row.get("status") or "") != "active"]
    if non_active:
        lines.append("")
        lines.append("Non-active ArcPods:")
        for row in non_active[:8]:
            lines.append(
                f"- {_deployment_label(row)}: {row.get('deployment_id')} status={row.get('status') or 'unknown'} "
                f"user={row.get('user_id') or 'unknown'}"
            )
    lines.extend(
        [
            "",
            "Note: Hermes /agents means internal helper/task agents. On Operator surfaces, /agents now reports ArcLink Captain Agents and ArcPods.",
            "Use /operator_fleet for worker capacity, /user_lookup <query> for account detail, and /action_status for queued work.",
        ]
    )
    return {
        "message": "\n".join(lines),
        "deployments": [_deployment_public(row) for row in captain_rows],
        "operator_agents": [_deployment_public(row) for row in operator_rows],
        "legacy_active_agents": legacy_active,
    }


def _handle_fleet_list(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    from arclink_fleet import list_fleet_hosts

    hosts = _safe_call(lambda: list_fleet_hosts(conn), default=[])
    lines = ["Operator Raven fleet list"]
    if not hosts:
        lines.append("No fleet workers are registered. ArcPod provisioning is blocked until a worker is admitted.")
        return {"message": "\n".join(lines), "hosts": []}
    for host in hosts[:10]:
        state = str(host.get("status") or "unknown")
        drained = "drained" if bool(int(host.get("drain") or 0)) else "accepting"
        region = str(host.get("region") or "unregioned")
        lines.append(
            f"- {host.get('hostname')}: {state}, {drained}, "
            f"{int(host.get('headroom') or 0)} slot(s) free, {region}"
        )
    if len(hosts) > 10:
        lines.append(f"... {len(hosts) - 10} more worker(s) omitted.")
    return {"message": "\n".join(lines), "hosts": hosts}


def _handle_fleet_drain(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    return _handle_fleet_drain_state(
        conn,
        command,
        actor_id=actor_id,
        drain=True,
        command_label="Fleet drain",
        verb="drain",
    )


def _handle_fleet_resume(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    return _handle_fleet_drain_state(
        conn,
        command,
        actor_id=actor_id,
        drain=False,
        command_label="Fleet resume",
        verb="resume",
    )


def _handle_fleet_drain_state(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    actor_id: str,
    drain: bool,
    command_label: str,
    verb: str,
) -> dict[str, Any]:
    target = _first_non_option_arg(command.args)
    if not target:
        return {"message": f"Use /fleet_{verb} <host-id-or-hostname> (add --dry-run to preview)."}
    host = _find_fleet_host(conn, target)
    if host is None:
        return {"message": f"{command_label}: no registered worker matches {target}."}

    force = _has_force_flag(command.args)
    guard = _fleet_last_capacity_guard(conn, host, drain=drain, force=force)
    currently_drained = bool(int(host.get("drain") or 0))
    desired_drained = bool(drain)

    if command.dry_run:
        lines = [
            f"{command_label} dry-run",
            f"Worker: {host.get('hostname')} ({host.get('host_id')})",
            f"Current: status={host.get('status') or 'unknown'} drain={str(currently_drained).lower()}",
            f"Would set drain={str(desired_drained).lower()}.",
        ]
        if guard:
            lines.append(f"Blocked unless --force: {guard}")
        lines.append("No fleet state, placement, SSH, Docker, provider, or firewall setting was changed.")
        return {"message": "\n".join(lines), "host": host, "capacity_guard": guard}

    blocked = _require_operator_actor(actor_id, command_label)
    if blocked is not None:
        return blocked
    if guard:
        return {
            "message": (
                f"{command_label} blocked: {guard} Re-run with --dry-run to inspect, add --force only during an explicit maintenance window, "
                "then append confirm or the operator approval code. No fleet state changed."
            ),
        }
    needs_confirm = _require_operator_confirmation(command)
    if needs_confirm is not None:
        return needs_confirm

    if currently_drained == desired_drained:
        state = "drained" if desired_drained else "accepting placements"
        return {
            "message": f"{command_label}: {host.get('hostname')} is already {state}. No fleet state changed.",
            "host": host,
        }

    try:
        from arclink_control import append_arclink_audit, append_arclink_event
        from arclink_fleet import update_fleet_host

        updated = update_fleet_host(conn, host_id=str(host.get("host_id") or ""), drain=desired_drained)
        event_type = "fleet_worker_drained" if desired_drained else "fleet_worker_resumed"
        append_arclink_event(
            conn,
            subject_kind="fleet_host",
            subject_id=str(updated.get("host_id") or ""),
            event_type=event_type,
            metadata={
                "hostname": str(updated.get("hostname") or ""),
                "actor_id": actor_id,
                "source": "operator_raven",
                "force": force,
            },
            commit=False,
        )
        append_arclink_audit(
            conn,
            action=f"operator_raven:{event_type}",
            actor_id=actor_id,
            target_kind="fleet_host",
            target_id=str(updated.get("host_id") or ""),
            reason=f"Operator Raven {verb} worker request",
            metadata={
                "hostname": str(updated.get("hostname") or ""),
                "previous_drain": currently_drained,
                "new_drain": desired_drained,
                "force": force,
            },
            commit=False,
        )
        conn.commit()
    except Exception as exc:  # noqa: BLE001
        return {"message": f"{command_label} failed closed: {exc}"}

    state = "drained; new ArcPod placements will avoid it" if desired_drained else "resumed; placement eligibility still depends on health and capacity"
    lines = [
        f"Operator Raven {command_label.lower()} applied",
        f"Worker: {updated.get('hostname')} ({updated.get('host_id')})",
        f"State: {state}",
        "No SSH, Docker, provider, firewall, or port-22 setting was changed by this chat command.",
    ]
    return {
        "message": "\n".join(lines),
        "mutation_performed": True,
        "host": updated,
    }


def _handle_worker_probe(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    if not command.dry_run:
        return {
            "message": "Worker probe is dry-run only in this Operator Raven slice. Use /worker_probe <host-id-or-hostname> --dry-run.",
        }
    target = command.args[0] if command.args else ""
    if not target:
        return {"message": "Use /worker_probe <host-id-or-hostname> --dry-run."}
    host = _find_fleet_host(conn, target)
    if host is None:
        return {"message": f"Worker probe dry-run: no registered worker matches {target}."}
    headroom = int(host.get("capacity_slots") or 0) - int(host.get("observed_load") or 0)
    lines = [
        "Worker probe dry-run",
        f"Worker: {host.get('hostname')} ({host.get('host_id')})",
        f"Local state: status={host.get('status')}, drain={bool(int(host.get('drain') or 0))}, headroom={headroom}",
        "No SSH, provider, Docker, or health-probe command was run.",
    ]
    return {"message": "\n".join(lines), "host": host}


def _handle_user_lookup(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    query = " ".join(command.args).strip()
    if not query:
        return {"message": "Use /user_lookup <user-id|email|display-name>."}
    rows = _find_users(conn, query)
    lines = ["Operator Raven user lookup"]
    if not rows:
        lines.append(f"No user matched {query}.")
        return {"message": "\n".join(lines), "users": []}
    for row in rows:
        deployments = _deployments_for_user(conn, str(row.get("user_id") or ""))
        dep_counts: dict[str, int] = {}
        for dep in deployments:
            dep_counts[str(dep.get("status") or "unknown")] = dep_counts.get(str(dep.get("status") or "unknown"), 0) + 1
        academy = _academy_summary_for_user(conn, str(row.get("user_id") or ""))
        lines.append(
            f"- {row.get('user_id')}: {row.get('display_name') or 'unnamed'} "
            f"<{row.get('email') or 'no-email'}>, status={row.get('status')}, "
            f"entitlement={row.get('entitlement_state') or 'none'}, deployments={_format_counts(dep_counts)}, "
            f"academy={academy['status']}"
        )
    if len(rows) == 5:
        lines.append("Showing first 5 matches.")
    return {"message": "\n".join(lines), "users": rows}


def _handle_billing_status(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    entitlement_counts = _group_counts(conn, "arclink_users", "entitlement_state")
    subscription_counts = _group_counts(conn, "arclink_subscriptions", "status")
    deployment_counts = _group_counts(conn, "arclink_deployments", "status")
    credit_counts = _group_counts(conn, "arclink_refuel_credits", "status")
    remaining_cents = _sum_int(conn, "arclink_refuel_credits", "remaining_cents", where="status = 'active'")
    total_credit_cents = _sum_int(conn, "arclink_refuel_credits", "credit_cents")
    active_users = _count_rows(conn, "arclink_users", where="status = 'active'")
    lines = [
        "Operator Raven billing status",
        f"Users: active={active_users}; entitlement={_format_counts(entitlement_counts)}",
        f"Subscriptions: {_format_counts(subscription_counts)}",
        f"ArcPods: {_format_counts(deployment_counts)}",
        f"Refuel credits: {_format_counts(credit_counts)}; remaining=${remaining_cents / 100:.2f}; issued=${total_credit_cents / 100:.2f}",
        "No Stripe, provider, budget, or entitlement mutation was run.",
        "Next: /user_lookup <query> for one Captain, /action_status for queued billing-adjacent work, /upgrade_policy router for inference policy.",
    ]
    return {
        "message": "\n".join(lines),
        "billing_status": {
            "entitlements": entitlement_counts,
            "subscriptions": subscription_counts,
            "deployments": deployment_counts,
            "refuel_credits": credit_counts,
            "remaining_credit_cents": remaining_cents,
            "issued_credit_cents": total_credit_cents,
        },
    }


def _handle_backup_status(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    try:
        from arclink_dashboard import _deployment_backup_setup
    except Exception:  # noqa: BLE001 - keep the operator surface fail-closed.
        _deployment_backup_setup = None  # type: ignore[assignment]

    rows = [row for row in _deployment_rows(conn) if not _deployment_is_operator(row)]
    counts: dict[str, int] = {}
    github_checks: dict[str, int] = {}
    activation_counts: dict[str, int] = {}
    flagged: list[dict[str, str]] = []
    for row in rows:
        deployment_id = str(row.get("deployment_id") or "")
        metadata = _deployment_metadata(row)
        if _deployment_backup_setup is not None:
            setup = _safe_call(
                lambda row=row, metadata=metadata: _deployment_backup_setup(  # type: ignore[misc]
                    conn,
                    deployment_id=str(row.get("deployment_id") or ""),
                    deployment_metadata=metadata,
                ),
                default={"status": "unavailable", "verification": {}},
            )
        else:
            setup = {"status": "unavailable", "verification": {}}
        verification = setup.get("verification") if isinstance(setup, Mapping) else {}
        status = str((setup if isinstance(setup, Mapping) else {}).get("status") or "unknown")
        github = str((verification if isinstance(verification, Mapping) else {}).get("github_write_check") or "unknown")
        activation = str((verification if isinstance(verification, Mapping) else {}).get("backup_activation") or "unknown")
        counts[status] = counts.get(status, 0) + 1
        github_checks[github] = github_checks.get(github, 0) + 1
        activation_counts[activation] = activation_counts.get(activation, 0) + 1
        if status not in {"not_requested", "active", "verified"} or github in {"failed_closed", "failed"}:
            flagged.append(
                {
                    "deployment_id": deployment_id,
                    "user_id": str(row.get("user_id") or ""),
                    "status": status,
                    "github_write_check": github,
                    "backup_activation": activation,
                }
            )
    lines = [
        "Operator Raven backup status",
        f"Deployments: {len(rows)} Captain ArcPod(s)",
        f"Backup setup: {_format_counts(counts)}",
        f"GitHub write checks: {_format_counts(github_checks)}",
        f"Activation: {_format_counts(activation_counts)}",
    ]
    if flagged:
        lines.append("Needs attention:")
        for item in flagged[:8]:
            lines.append(
                f"- {item['deployment_id']} user={item['user_id']} "
                f"status={item['status']} write_check={item['github_write_check']} activation={item['backup_activation']}"
            )
        if len(flagged) > 8:
            lines.append(f"... {len(flagged) - 8} more backup item(s) omitted.")
    else:
        lines.append("Needs attention: none from local metadata.")
    lines.append("No GitHub, SSH, deploy-key, or backup mutation was run.")
    return {
        "message": "\n".join(lines),
        "backup_status": {
            "deployments": len(rows),
            "counts": counts,
            "github_write_checks": github_checks,
            "activation": activation_counts,
            "flagged": flagged,
        },
    }


def _handle_workspace_status(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    qmd_health = _service_status_counts(conn, "qmd-mcp")
    memory_health = _service_status_counts(conn, "memory-synth")
    context_health = _service_status_counts(conn, "managed-context")
    notion_docs = _count_rows(conn, "notion_index_documents", where="state = 'active'")
    memory_cards = _group_counts(conn, "memory_synthesis_cards", "status")
    refresh_jobs = _group_counts(conn, "refresh_jobs", "last_status")
    share_grants = _group_counts(conn, "arclink_share_grants", "status")
    recent_changed = _recent_workspace_events(conn)
    lines = [
        "Operator Raven workspace status",
        f"qmd service health: {_format_counts(qmd_health)}",
        f"Memory synthesis service health: {_format_counts(memory_health)}",
        f"Managed context health: {_format_counts(context_health)}",
        f"Memory cards: {_format_counts(memory_cards)}",
        f"Shared Notion index: {notion_docs} active document(s)",
        f"Refresh jobs: {_format_counts(refresh_jobs)}",
        f"Share grants: {_format_counts(share_grants)}",
    ]
    if recent_changed:
        lines.append("Recent workspace-related events:")
        for item in recent_changed[:6]:
            lines.append(f"- {item.get('event_type')} {item.get('subject_kind')}:{item.get('subject_id')}")
    lines.append("No qmd, Notion, memory, share, filesystem, or provider mutation was run.")
    return {
        "message": "\n".join(lines),
        "workspace_status": {
            "qmd_health": qmd_health,
            "memory_health": memory_health,
            "managed_context_health": context_health,
            "notion_index_active_documents": notion_docs,
            "memory_cards": memory_cards,
            "refresh_jobs": refresh_jobs,
            "share_grants": share_grants,
            "recent_events": recent_changed,
        },
    }


def _handle_academy_status(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    query = " ".join(command.args).strip()
    if not query:
        return {"message": "Use /academy_status <user-id|email|display-name>."}
    rows = _find_users(conn, query)
    lines = ["Operator Raven Academy status"]
    if not rows:
        lines.append(f"No user matched {query}.")
        return {"message": "\n".join(lines), "users": []}
    payloads = []
    for row in rows[:5]:
        user_id = str(row.get("user_id") or "")
        academy = _academy_summary_for_user(conn, user_id)
        payloads.append({"user_id": user_id, "academy_training": academy})
        lines.append(
            f"- {user_id}: {row.get('display_name') or 'unnamed'}, "
            f"academy={academy['status']}, sources={academy['source_count']}, "
            f"weekly={academy.get('weekly_review_status') or 'not_started'}, "
            f"evaluation={academy.get('evaluation_status') or 'not_started'}, "
            f"graduation={academy.get('graduation_status') or 'not_started'}, "
            f"review_needed={int(academy.get('review_needed_count') or 0)}, "
            f"blocked_sources={int(academy.get('blocked_source_count') or 0)}, "
            f"next_review={academy.get('next_review_at') or 'not_scheduled'}, "
            f"proof={','.join(academy.get('proof_gates') or [])}"
        )
        next_actions = academy.get("next_actions") if isinstance(academy.get("next_actions"), list) else []
        if next_actions:
            lines.append(f"  Next: {next_actions[0]}")
    lines.append("No action was queued. Academy live generation and workspace proof remain PG-PROVIDER/PG-HERMES gated.")
    return {"message": "\n".join(lines), "academy": payloads}


def _handle_academy_roster(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Read-only Academy roster across the fleet: graduates + in-progress trainees.

    Optionally scoped to a user when an argument is supplied. No action is queued;
    live generation + Agent application remain PG-PROVIDER/PG-HERMES gated.
    """
    from arclink_academy_programs import (
        browse_academy_graduates,
        list_academy_trainees,
        seed_default_academy_programs,
    )

    seed_default_academy_programs(conn)
    scope_user = ""
    if command.args:
        rows = _find_users(conn, " ".join(command.args).strip())
        if not rows:
            return {"message": f"Academy roster: no user matched {' '.join(command.args).strip()}."}
        scope_user = str(rows[0].get("user_id") or "")

    gallery = browse_academy_graduates(conn, user_id=scope_user or None)
    graduates = gallery.get("graduates", [])
    in_academy = list_academy_trainees(conn, user_id=scope_user or None, status="in_academy")
    enrolled = list_academy_trainees(conn, user_id=scope_user or None, status="enrolled")

    header = "Operator Raven Academy roster" + (f" (user {scope_user})" if scope_user else " (fleet-wide)")
    lines = [
        header,
        f"Majors: {len(gallery.get('programs', []))} | "
        f"graduates: {len(graduates)} | in-academy: {len(in_academy)} | enrolled: {len(enrolled)}",
    ]
    for grad in graduates[:8]:
        lines.append(
            f"- graduate {grad.get('trainee_id')}: {grad.get('name') or 'unnamed'} "
            f"[{grad.get('program_label') or grad.get('program_id')}] "
            f"forward_maintained={bool(grad.get('forward_maintained'))}"
        )
    for trainee in in_academy[:8]:
        lines.append(
            f"- in-academy {trainee.get('trainee_id')}: {trainee.get('name') or 'unnamed'} "
            f"[{trainee.get('program_id')}] mode_open={bool(trainee.get('mode_open'))} "
            f"(ends only when the Captain closes Academy Mode)"
        )
    for trainee in enrolled[:8]:
        lines.append(
            f"- enrolled {trainee.get('trainee_id')}: {trainee.get('name') or 'unnamed'} [{trainee.get('program_id')}]"
        )
    lines.append("No action was queued. Academy live generation and Agent SOUL writes remain PG-PROVIDER/PG-HERMES gated.")
    return {
        "message": "\n".join(lines),
        "academy_roster": {
            "scope_user": scope_user,
            "majors": len(gallery.get("programs", [])),
            "graduates": graduates,
            "in_academy": in_academy,
            "enrolled": enrolled,
        },
    }


def _handle_pod_repair(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    deployment_id = command.args[0] if command.args else ""
    if not deployment_id:
        return {"message": "Use /pod_repair <deployment-id> [restart|reprovision|dns_repair] (add --dry-run to preview)."}
    deployment = _find_deployment(conn, deployment_id)
    if deployment is None:
        return {"message": f"Pod repair: no deployment matched {deployment_id}."}

    from arclink_dashboard import admin_action_execution_readiness

    readiness = admin_action_execution_readiness(env=env)
    support = readiness.get("action_support", {})
    candidates = [
        name for name in _POD_REPAIR_ACTIONS
        if bool((support.get(name) or {}).get("queueable"))
    ]
    requested_action = _selected_pod_repair_action(command.args)
    default_action = requested_action or (candidates[0] if candidates else "restart")

    if command.dry_run:
        candidates_text = ", ".join(candidates) if candidates else "no repair actions are queueable until executor probes pass"
        would_queue = default_action if default_action in candidates else f"{default_action} (blocked until executor probes pass)"
        lines = [
            "Pod repair dry-run",
            f"Deployment: {deployment.get('deployment_id')} status={deployment.get('status')} user={deployment.get('user_id')}",
            f"Candidate local actions: {candidates_text}",
            f"Would queue: {would_queue}",
            "No action was queued and no deployment, Docker, DNS, SSH, or provider state was changed.",
        ]
        return {"message": "\n".join(lines), "deployment": deployment}

    blocked = _require_operator_actor(actor_id, "Pod repair")
    if blocked is not None:
        return blocked

    action_type = default_action
    if action_type not in _POD_REPAIR_ACTIONS:
        return {"message": f"Pod repair: unknown action {action_type}. Choose one of {', '.join(_POD_REPAIR_ACTIONS)}."}
    if action_type not in candidates:
        gate = str((support.get(action_type) or {}).get("live_proof_gate") or "PG-PROVISION")
        adapter = _executor_adapter(env)
        return {
            "message": (
                f"Pod repair blocked: {action_type} is not queueable with executor adapter '{adapter}'. "
                f"Set ARCLINK_EXECUTOR_ADAPTER and clear the {gate} proof gate first. No action was queued."
            ),
        }
    needs_confirm = _require_operator_confirmation(command)
    if needs_confirm is not None:
        return needs_confirm

    target_kind = "deployment"
    key = _action_idempotency_key(idempotency_key, kind=f"podrepair-{action_type}", target=str(deployment.get("deployment_id")))
    reason = f"Operator Raven pod_repair {action_type} for {deployment.get('deployment_id')}"
    already_queued = _admin_action_intent_exists(conn, key)
    try:
        from arclink_dashboard import queue_arclink_admin_action

        intent = queue_arclink_admin_action(
            conn,
            admin_id=actor_id,
            action_type=action_type,
            target_kind=target_kind,
            target_id=str(deployment.get("deployment_id")),
            reason=reason,
            idempotency_key=key,
            metadata={"source": "operator_raven", "actor_id": actor_id, "requested_by": actor_id},
        )
    except Exception as exc:  # noqa: BLE001 - fail closed and surface the boundary
        return {"message": f"Pod repair failed closed: {exc}"}
    adapter = _executor_adapter(env)
    record_only = adapter == "fake"
    queued_note = "already queued (idempotent)" if already_queued else "queued"
    lines = [
        f"Operator Raven pod repair {queued_note}",
        f"Deployment: {deployment.get('deployment_id')} action={action_type}",
        f"Action id: {intent.get('action_id')} status={intent.get('status')}",
        f"Executor adapter: {adapter}{' (record-only)' if record_only else ''}",
        "The ArcLink action worker will execute this intent. Track it with /action_status.",
    ]
    return {
        "message": "\n".join(lines),
        "mutation_performed": not already_queued,
        "action_intent": intent,
    }


def _selected_pod_repair_action(args: Sequence[str]) -> str:
    for arg in args[1:]:
        value = str(arg or "").strip().lower().replace("-", "_")
        if value in _POD_REPAIR_ACTIONS:
            return value
    return ""


def _handle_upgrade_check(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    if upgrade_check_runner is None:
        return {
            "message": (
                "Upgrade check is fail-closed in this Operator Raven slice because no local runner was supplied. "
                "Use the CLI or an authorized operator proof window for live git/deploy-key checks."
            ),
        }
    try:
        result = dict(upgrade_check_runner())
    except Exception as exc:  # noqa: BLE001
        return {"message": f"Upgrade check failed closed: {exc}"}
    status = str(result.get("status") or "unknown")
    current = str(result.get("current") or result.get("deployed") or "")
    available = str(result.get("available") or result.get("upstream") or "")
    note = str(result.get("note") or result.get("message") or "")
    lines = ["Operator Raven upgrade check", f"Status: {status}"]
    if current:
        lines.append(f"Current: {current[:12]}")
    if available:
        lines.append(f"Available: {available[:12]}")
    if note:
        lines.append(f"Note: {note}")
    lines.append("No upgrade was queued or run. Run /upgrade for the host upgrade, /pin_upgrade <component> for one pending detector target, or /upgrade_sweep for all pending detector targets.")
    return {"message": "\n".join(lines), "upgrade": result}


def _handle_upgrade_policy(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    from arclink_upgrade_policy import policy_components_by_scope, upgrade_policy_summary

    component = _first_non_option_arg(command.args)
    try:
        summary = upgrade_policy_summary(component)
    except ValueError as exc:
        return {"message": f"Operator Raven upgrade policy\nStatus: blocked\nRepair: {exc}"}

    if summary["mode"] == "component":
        policy = dict(summary["policy"])
        lines = [
            f"Operator Raven upgrade policy: {policy['label']}",
            f"Component: {policy['component']} ({policy['scope']})",
            f"Order: {policy['rollout_order']}",
            f"Operator command: {policy['operator_command']}",
            f"Strategy: {policy['strategy']}",
            f"Downtime posture: {policy['downtime_posture']}",
            f"Default batch: {policy['default_batch_size']}",
            "Preflight: " + "; ".join(policy.get("preflight_checks") or []),
            "Proof gates: " + ", ".join(policy.get("proof_gates") or []),
            "Rollback: " + "; ".join(policy.get("rollback_contract") or []),
            "No action was queued. Use the listed command with --dry-run before confirming any mutation.",
        ]
        return {"message": "\n".join(lines), "upgrade_policy": summary}

    lines = [
        "Operator Raven upgrade policy",
        "Sequence: control plane first; ArcPod runtime in bounded batches; knowledge jobs async; stateful services in maintenance windows; worker fabric one drained worker at a time.",
    ]
    for scope, components in policy_components_by_scope(summary):
        lines.append(f"- {scope}: {', '.join(components)}")
    lines.extend(
        [
            "Commands: /upgrade, /pin_upgrade <component>, /upgrade_sweep, /rollout <target>, /fleet_drain <worker>, /fleet_resume <worker>.",
            "No action was queued. Ask /upgrade_policy <component> for the exact preflight, proof, downtime, and rollback contract.",
        ]
    )
    return {"message": "\n".join(lines), "upgrade_policy": summary}


def _pin_payload_component_names(payload: Mapping[str, Any]) -> set[str]:
    names: set[str] = set()
    for item in list(payload.get("items") or []) + list(payload.get("install_items") or []):
        component = str(item.get("component") or "").strip().lower()
        if component:
            names.add(component)
    return names


def _pin_payload_operator_names(payload: Mapping[str, Any]) -> set[str]:
    names = _pin_payload_component_names(payload)
    operator_names = set(names)
    if "hermes-agent" in names or "hermes-docs" in names:
        operator_names.add("hermes")
    return operator_names


def _pin_payload_is_stateful(payload: Mapping[str, Any]) -> bool:
    return bool(_pin_payload_operator_names(payload) & set(STATEFUL_PIN_UPGRADE_COMPONENTS))


def _pin_payload_line(payload: Mapping[str, Any]) -> str:
    token = str(payload.get("token") or "").strip()
    parts: list[str] = []
    for item in payload.get("install_items") or payload.get("items") or []:
        component = str(item.get("component") or "").strip()
        target = str(item.get("target") or "").strip()
        if str(item.get("kind") or "") == "git-commit" and len(target) >= 12:
            target = target[:12]
        if component:
            parts.append(f"{component}->{target or '?'}")
    return f"{token}: " + ", ".join(parts or ["pending pinned component"])


def _pending_pin_payloads_for_component(conn: sqlite3.Connection, component: str) -> list[dict[str, Any]]:
    from arclink_control import list_pin_upgrade_action_payloads

    return list_pin_upgrade_action_payloads(conn, component=component, active_only=True)


def _pending_pin_payloads(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    from arclink_control import list_pin_upgrade_action_payloads

    return list_pin_upgrade_action_payloads(conn, active_only=True)


def _operator_action_authorization(
    *,
    actor_id: str,
    action_kind: str,
    target: str,
    command_name: str,
    idempotency_key: str,
) -> dict[str, Any]:
    from arclink_control import OPERATOR_ACTION_AUTH_KIND_OPERATOR_RAVEN, OPERATOR_ACTION_AUTH_TTL_SECONDS

    clean_target = str(target or "").strip()
    confirmation_id = _action_idempotency_key(
        idempotency_key,
        kind=f"operator-action-{action_kind}",
        target=clean_target or command_name,
    )
    return {
        "kind": OPERATOR_ACTION_AUTH_KIND_OPERATOR_RAVEN,
        "actor_id": str(actor_id or "").strip(),
        "ttl_seconds": OPERATOR_ACTION_AUTH_TTL_SECONDS,
        "payload": {
            "source": "operator-raven",
            "command": command_name,
            "action_kind": action_kind,
            "target_hash": hashlib.sha256(clean_target.encode("utf-8")).hexdigest(),
            "confirmation_id": confirmation_id,
            "reason": f"Operator Raven confirmed {command_name}",
        },
    }


def _queue_pin_upgrade_payloads(
    conn: sqlite3.Connection,
    *,
    payloads: Sequence[Mapping[str, Any]],
    actor_id: str,
    idempotency_key: str = "",
) -> tuple[list[dict[str, Any]], int]:
    from arclink_control import request_operator_action

    queued: list[dict[str, Any]] = []
    created_count = 0
    for payload in payloads:
        token = str(payload.get("token") or "").strip()
        if not token:
            continue
        action_row, created = request_operator_action(
            conn,
            action_kind="pin-upgrade",
            requested_by=actor_id,
            request_source="operator-raven",
            requested_target=token,
            dedupe_by_target=True,
            authorization=_operator_action_authorization(
                actor_id=actor_id,
                action_kind="pin-upgrade",
                target=token,
                command_name="pin_upgrade",
                idempotency_key=idempotency_key,
            ),
        )
        queued.append(action_row)
        if created:
            created_count += 1
    return queued, created_count


OPERATOR_BUTTON_NONCE_TTL_SECONDS = 900
_OPERATOR_BUTTON_NONCE_PREFIX = "operator_button_nonce:"


def operator_button_approvals_enabled(env: Mapping[str, str] | None = None) -> bool:
    """One-tap upgrade buttons are on unless the operator opts out.

    A button press carries a fresh single-use server-minted nonce on the
    gated operator channel, which is the structured confirmation for the
    mapped action. Set ARCLINK_OPERATOR_BUTTON_APPROVALS=0 to require typed
    confirm/approval-code flows instead.
    """
    raw = str((env or {}).get("ARCLINK_OPERATOR_BUTTON_APPROVALS") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _prune_operator_button_nonces(conn: sqlite3.Connection) -> None:
    from arclink_control import parse_utc_iso, utc_now

    rows = conn.execute(
        "SELECT key, value FROM settings WHERE key LIKE ?",
        (_OPERATOR_BUTTON_NONCE_PREFIX + "%",),
    ).fetchall()
    now_ts = utc_now().timestamp()
    for row in rows:
        try:
            payload = json.loads(str(row["value"] or "{}"))
        except ValueError:
            payload = {}
        expires = parse_utc_iso(str(payload.get("expires_at") or ""))
        if payload.get("used_at") or expires is None or expires.timestamp() <= now_ts:
            conn.execute("DELETE FROM settings WHERE key = ?", (str(row["key"]),))
    conn.commit()


def mint_operator_button_nonce(conn: sqlite3.Connection, *, command: str) -> str:
    """Mint a single-use, short-lived nonce mapping to one confirmed command."""
    from arclink_control import upsert_setting, utc_after_seconds_iso

    _prune_operator_button_nonces(conn)
    raw = secrets.token_urlsafe(18)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    payload = {
        "command": str(command or "").strip(),
        "expires_at": utc_after_seconds_iso(OPERATOR_BUTTON_NONCE_TTL_SECONDS),
        "used_at": "",
    }
    upsert_setting(conn, _OPERATOR_BUTTON_NONCE_PREFIX + digest, json.dumps(payload, sort_keys=True))
    return raw


def consume_operator_button_nonce(conn: sqlite3.Connection, raw_nonce: str) -> str:
    """Validate and burn a button nonce; returns the mapped command or ''."""
    from arclink_control import parse_utc_iso, utc_now, utc_now_iso

    clean = str(raw_nonce or "").strip()
    if not clean:
        return ""
    digest = hashlib.sha256(clean.encode("utf-8")).hexdigest()
    key = _OPERATOR_BUTTON_NONCE_PREFIX + digest
    own_txn = not conn.in_transaction
    if own_txn:
        conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            if own_txn:
                conn.commit()
            return ""
        original_value = str(row["value"] or "{}")
        try:
            payload = json.loads(original_value)
        except ValueError:
            if own_txn:
                conn.commit()
            return ""
        if str(payload.get("used_at") or "").strip():
            if own_txn:
                conn.commit()
            return ""
        expires = parse_utc_iso(str(payload.get("expires_at") or ""))
        if expires is None or expires.timestamp() <= utc_now().timestamp():
            if own_txn:
                conn.commit()
            return ""
        command = str(payload.get("command") or "").strip()
        payload["used_at"] = utc_now_iso()
        cursor = conn.execute(
            "UPDATE settings SET value = ?, updated_at = ? WHERE key = ? AND value = ?",
            (json.dumps(payload, sort_keys=True), payload["used_at"], key, original_value),
        )
        if own_txn:
            conn.commit()
        return command if cursor.rowcount == 1 else ""
    except Exception:
        if own_txn and conn.in_transaction:
            conn.rollback()
        raise


def _upgrade_one_tap_button(
    conn: sqlite3.Connection,
    *,
    label: str,
    command: str,
) -> dict[str, str]:
    nonce = mint_operator_button_nonce(conn, command=command)
    return {"label": label[:60], "callback_data": f"arclink:/upgrade_apply {nonce}"}


def _pin_payload_button_label(payload: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for item in payload.get("install_items") or payload.get("items") or []:
        component = str(item.get("component") or "").strip()
        target = str(item.get("target") or "").strip()
        if str(item.get("kind") or "") == "git-commit" and len(target) >= 12:
            target = target[:12]
        if component:
            parts.append(f"{component} -> {target or '?'}")
    return ("Pin " + ", ".join(parts))[:60] if parts else "Pin upgrade"


def _handle_upgrade_menu(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Render the one-tap upgrade menu. Read-only: nothing is queued here."""
    from arclink_control import get_active_operator_action

    lines = ["Operator Raven upgrade menu"]
    buttons: list[dict[str, str]] = []
    # Nonce buttons are minted only for a proven operator identity; an
    # actorless render stays a plain read-only summary.
    one_tap = operator_button_approvals_enabled(env) and bool(actor_id)
    active_upgrade = None
    try:
        active_upgrade = get_active_operator_action(conn, action_kind="upgrade")
    except Exception:  # noqa: BLE001 - menu must render even if the queue read fails
        active_upgrade = None
    if active_upgrade is not None:
        status = str(active_upgrade.get("status") or "pending")
        lines.append(f"- Control upgrade already {status}. Track it with /action_status.")
    else:
        lines.append("- Control Node upgrade/repair: ready to queue (git pull + control/docker upgrade + reconcile + health).")
        if one_tap:
            buttons.append(_upgrade_one_tap_button(conn, label="Apply Control Upgrade", command="/upgrade confirm"))
    try:
        payloads = _pending_pin_payloads(conn)
    except Exception as exc:  # noqa: BLE001
        payloads = []
        lines.append(f"- Pinned components: could not read detector payloads ({_redact_text(str(exc))[:120]}).")
    if payloads:
        lines.append("Pending pinned-component upgrades:")
        for payload in payloads[:6]:
            stateful = " (stateful: needs maintenance window)" if _pin_payload_is_stateful(payload) else ""
            lines.append(f"- {_pin_payload_line(payload)}{stateful}")
            if one_tap and not _pin_payload_is_stateful(payload):
                components = sorted(_pin_payload_operator_names(payload))
                component = components[0] if components else ""
                if component:
                    buttons.append(
                        _upgrade_one_tap_button(
                            conn,
                            label=_pin_payload_button_label(payload),
                            command=f"/pin_upgrade {component} confirm",
                        )
                    )
        if any(_pin_payload_is_stateful(payload) for payload in payloads):
            lines.append("Stateful components (postgres/redis/nextcloud) stay typed-only: /upgrade_sweep --include-stateful confirm after a backup.")
    else:
        lines.append("No pinned-component upgrades are pending. The hourly detector refreshes this list.")
    if one_tap and buttons:
        lines.append("")
        lines.append("Tap a button to queue it. Buttons are single-use and expire in 15 minutes; send /upgrade again for a fresh menu.")
    elif not one_tap:
        lines.append("")
        lines.append("One-tap buttons are disabled (ARCLINK_OPERATOR_BUTTON_APPROVALS=0). Use /upgrade confirm or /pin_upgrade <component> confirm with your approval code.")
    return {
        "message": "\n".join(lines),
        "buttons": buttons,
        "mutation_performed": False,
    }


def _handle_upgrade_apply(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Apply a one-tap upgrade button: nonce is the structured confirmation."""
    blocked = _require_operator_actor(actor_id, "One-tap upgrade")
    if blocked is not None:
        return blocked
    if not operator_button_approvals_enabled(env):
        return {
            "message": (
                "One-tap upgrade buttons are disabled (ARCLINK_OPERATOR_BUTTON_APPROVALS=0). "
                "Use /upgrade confirm or /pin_upgrade <component> confirm instead. No action was queued."
            ),
        }
    nonce = _first_non_option_arg(command.args)
    mapped = consume_operator_button_nonce(conn, nonce)
    if not mapped:
        return {
            "message": (
                "That upgrade button expired or was already used. Send /upgrade for a fresh menu. "
                "No action was queued."
            ),
        }
    result = dispatch_operator_raven_command(
        conn,
        mapped,
        env=env,
        upgrade_check_runner=upgrade_check_runner,
        actor_id=actor_id,
        idempotency_key=idempotency_key or hashlib.sha256(nonce.encode("utf-8")).hexdigest()[:24],
    )
    result["command"] = "upgrade_apply"
    result.setdefault("applied_command", mapped.split(" confirm")[0].strip())
    return result


def _handle_host_upgrade(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    if command.dry_run:
        return {
            "message": (
                "Host upgrade dry-run: would queue an operator 'upgrade' action that the root maintenance loop "
                "executes (git pull + control/docker upgrade + reconcile + health). No action was queued."
            ),
        }
    blocked = _require_operator_actor(actor_id, "Host upgrade")
    if blocked is not None:
        return blocked
    needs_confirm = _require_operator_confirmation(command)
    if needs_confirm is not None:
        return needs_confirm
    # Host/component upgrades use the operator-action queue, which the root
    # maintenance loop / enrollment provisioner drains through the upgrade
    # broker -- not ARCLINK_EXECUTOR_ADAPTER. There is no executor-adapter gate
    # to check here; the action is always queueable and brokered.
    try:
        from arclink_control import request_operator_action

        action_row, created = request_operator_action(
            conn,
            action_kind="upgrade",
            requested_by=actor_id,
            request_source="operator-raven",
            requested_target="",
            authorization=_operator_action_authorization(
                actor_id=actor_id,
                action_kind="upgrade",
                target="",
                command_name="upgrade",
                idempotency_key=idempotency_key,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return {"message": f"Could not queue ArcLink upgrade: {exc}"}
    status = str(action_row.get("status") or "pending")
    if created:
        message = "Operator Raven queued an ArcLink upgrade/repair. The root maintenance loop will pick it up within about a minute. Track it with /action_status."
    elif status == "running":
        message = "ArcLink upgrade is already running. Track it with /action_status."
    else:
        message = "ArcLink upgrade is already queued. Track it with /action_status."
    return {
        "message": message,
        "mutation_performed": bool(created),
        "operator_action": action_row,
    }


def _handle_pin_upgrade(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    component = str(command.component or "").strip().lower()
    if not component:
        return {
            "message": (
                "Use /pin_upgrade <component>. Components: " + ", ".join(PIN_UPGRADE_COMPONENTS) + "."
            ),
        }
    if component not in PIN_UPGRADE_COMPONENTS:
        return {
            "message": (
                f"Pin upgrade: unknown component '{component}'. Choose one of {', '.join(PIN_UPGRADE_COMPONENTS)}."
            ),
        }
    try:
        payloads = _pending_pin_payloads_for_component(conn, component)
    except Exception as exc:  # noqa: BLE001
        return {"message": f"Could not inspect pending pinned-component upgrades: {exc}"}
    if not payloads:
        return {
            "message": (
                f"Pin upgrade: no active detector payload is pending for {component}. "
                "Wait for the hourly detector or run the pinned-component check from the control node, then retry. "
                "No action was queued."
            ),
        }
    payload = payloads[0]
    token = str(payload.get("token") or "").strip()
    if command.dry_run:
        return {
            "message": (
                f"Pin upgrade dry-run for {component}: would queue detector payload {_pin_payload_line(payload)}. "
                "The root maintenance loop applies config/pins.json bumps plus the component upgrade. No action was queued."
            ),
        }
    blocked = _require_operator_actor(actor_id, "Pin upgrade")
    if blocked is not None:
        return blocked
    needs_confirm = _require_operator_confirmation(command)
    if needs_confirm is not None:
        if operator_button_approvals_enabled(env) and not _pin_payload_is_stateful(payload):
            needs_confirm["buttons"] = [
                _upgrade_one_tap_button(
                    conn,
                    label=_pin_payload_button_label(payload),
                    command=f"/pin_upgrade {component} confirm",
                )
            ]
        return needs_confirm
    try:
        queued, created_count = _queue_pin_upgrade_payloads(
            conn,
            payloads=[payload],
            actor_id=actor_id,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:  # noqa: BLE001
        return {"message": f"Could not queue pinned-component upgrade: {exc}"}
    action_row = queued[0] if queued else {}
    status = str(action_row.get("status") or "pending")
    if created_count:
        message = f"Operator Raven queued a pinned-component upgrade for {component} ({_pin_payload_line(payload)}). The root maintenance loop will apply it. Track it with /action_status."
    elif status == "running":
        message = f"A {component} pinned-component upgrade is already running. Track it with /action_status."
    else:
        message = f"A {component} pinned-component upgrade is already queued. Track it with /action_status."
    return {
        "message": message,
        "mutation_performed": bool(created_count),
        "operator_action": action_row,
    }


def _handle_upgrade_sweep(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    include_stateful = _has_include_stateful_flag(command.args)
    try:
        payloads = _pending_pin_payloads(conn)
    except Exception as exc:  # noqa: BLE001
        return {"message": f"Could not inspect pending pinned-component upgrades: {exc}"}

    if not payloads:
        return {
            "message": (
                "Upgrade sweep: no active pinned-component detector payloads are pending. "
                "The hourly detector will notify the Operator when concrete targets exist. No action was queued."
            ),
        }

    selected: list[dict[str, Any]] = []
    skipped_stateful: list[dict[str, Any]] = []
    seen_tokens: set[str] = set()
    for payload in payloads:
        token = str(payload.get("token") or "").strip()
        if not token or token in seen_tokens:
            continue
        seen_tokens.add(token)
        if _pin_payload_is_stateful(payload) and not include_stateful:
            skipped_stateful.append(payload)
            continue
        selected.append(payload)

    if not selected:
        return {
            "message": (
                "Upgrade sweep: only stateful pinned-component targets are pending. "
                "Use /upgrade_sweep --include-stateful --dry-run during a maintenance window, then confirm. "
                "No action was queued."
            ),
            "skipped_stateful": skipped_stateful,
        }

    lines = [
        "Operator Raven upgrade sweep",
        f"Pending detector payloads selected: {len(selected)}",
    ]
    lines.extend(f"- {_pin_payload_line(payload)}" for payload in selected)
    if skipped_stateful:
        lines.append("")
        lines.append(
            "Skipped stateful target(s): "
            + "; ".join(_pin_payload_line(payload) for payload in skipped_stateful)
        )
        lines.append("Add --include-stateful only inside an explicit maintenance window.")
    if command.dry_run:
        lines.append("")
        lines.append(
            "Dry-run only: no action was queued. Confirming queues these detector payloads; the root maintenance loop applies them sequentially, then normal ArcPod rollouts remain bounded/canary controlled."
        )
        return {
            "message": "\n".join(lines),
            "payloads": selected,
            "skipped_stateful": skipped_stateful,
        }

    blocked = _require_operator_actor(actor_id, "Upgrade sweep")
    if blocked is not None:
        return blocked
    needs_confirm = _require_operator_confirmation(command)
    if needs_confirm is not None:
        return needs_confirm
    try:
        queued, created_count = _queue_pin_upgrade_payloads(
            conn,
            payloads=selected,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:  # noqa: BLE001
        return {"message": f"Could not queue upgrade sweep: {exc}"}
    lines.append("")
    if created_count:
        lines.append(f"Queued {created_count} pinned-component upgrade action(s).")
    else:
        lines.append("All selected pinned-component upgrade action(s) were already queued or running.")
    lines.append("Track the sweep with /action_status.")
    return {
        "message": "\n".join(lines),
        "mutation_performed": bool(created_count),
        "operator_actions": queued,
        "skipped_stateful": skipped_stateful,
    }


def _handle_rollout(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    target_version = _first_non_option_arg(command.args) or str(env.get("ARCLINK_ROLLOUT_TARGET_VERSION") or "").strip()
    if not target_version:
        return {"message": "Use /rollout <target-version> [--batch-size N] (add --dry-run to preview the batches)."}
    try:
        batch_size = _batch_size_arg(command.args)
    except OperatorRavenError as exc:
        return {
            "message": (
                "Operator Raven rollout\n"
                f"Status: blocked\nTarget: {target_version}\nRepair: {exc}\n"
                "No rollout or action was queued."
            ),
        }

    from arclink_rollout import ArcLinkRolloutError, plan_arcpod_update_rollout

    try:
        plan = plan_arcpod_update_rollout(
            conn,
            target_version=target_version,
            batch_size=batch_size,
            env=env,
        )
    except ArcLinkRolloutError as exc:
        return {
            "message": (
                "Operator Raven rollout\n"
                f"Status: blocked\nTarget: {target_version}\nRepair: {exc}\n"
                "No rollout or action was queued."
            ),
        }

    if command.dry_run:
        lines = [
            "Operator Raven rollout plan dry-run",
            f"Target: {plan['target_version']}",
            f"Status: {plan['status']}",
            f"Candidates: {plan['candidate_count']} ready={plan['ready_count']} blocked={plan['blocked_count']}",
            f"Batches: {plan['batch_count']} at batch size {plan['batch_size']}",
            f"Stop on failure: {str(bool(plan['stop_on_failure'])).lower()}",
            f"Proof gate: {plan['proof_gate']}",
        ]
        if plan["status"] == "blocked":
            for item in plan.get("repair_summary", [])[:5]:
                lines.append(f"Repair: {item}")
        else:
            for batch in plan.get("batches", [])[:5]:
                lines.append(f"Batch {batch['batch_index']}: {', '.join(batch['deployment_ids'])}")
        lines.append("No rollout or action was queued. Re-run without --dry-run to queue the rollout.")
        return {"message": "\n".join(lines), "rollout_plan": plan}

    blocked = _require_operator_actor(actor_id, "Rollout")
    if blocked is not None:
        return blocked
    if plan["status"] == "blocked":
        lines = [
            "Operator Raven rollout blocked",
            f"Target: {plan['target_version']}",
            f"Candidates: {plan['candidate_count']} ready={plan['ready_count']} blocked={plan['blocked_count']}",
        ]
        for item in plan.get("repair_summary", [])[:5]:
            lines.append(f"Repair: {item}")
        lines.append("No rollout or action was queued.")
        return {"message": "\n".join(lines), "rollout_plan": plan}

    from arclink_dashboard import admin_action_execution_readiness

    readiness = admin_action_execution_readiness(env=env)
    rollout_support = (readiness.get("action_support", {}) or {}).get("rollout") or {}
    if not bool(rollout_support.get("queueable")):
        adapter = _executor_adapter(env)
        gate = str(rollout_support.get("live_proof_gate") or "PG-UPGRADE/PG-HERMES")
        return {
            "message": (
                f"Rollout blocked: not queueable with executor adapter '{adapter}'. "
                f"Set ARCLINK_EXECUTOR_ADAPTER and clear the {gate} proof gate first. No rollout was queued."
            ),
        }
    needs_confirm = _require_operator_confirmation(command)
    if needs_confirm is not None:
        return needs_confirm

    execute_local_batch = _has_execute_batch_flag(command.args)
    key = _action_idempotency_key(idempotency_key, kind="rollout", target=str(target_version))
    metadata: dict[str, Any] = {
        "target_version": target_version,
        "source": "operator_raven",
        "actor_id": actor_id,
    }
    if batch_size is not None:
        metadata["batch_size"] = batch_size
    if execute_local_batch:
        metadata["execute_local_batch"] = True
    already_queued = _admin_action_intent_exists(conn, key)
    try:
        from arclink_dashboard import queue_arclink_admin_action

        intent = queue_arclink_admin_action(
            conn,
            admin_id=actor_id,
            action_type="rollout",
            target_kind="system",
            target_id="arcpod-fleet",
            reason=f"Operator Raven rollout to {target_version}",
            idempotency_key=key,
            metadata=metadata,
        )
    except Exception as exc:  # noqa: BLE001
        return {"message": f"Rollout failed closed: {exc}"}
    adapter = _executor_adapter(env)
    queued_note = "already queued (idempotent)" if already_queued else "queued"
    lines = [
        f"Operator Raven rollout {queued_note}",
        f"Target: {target_version}",
        f"Candidates: {plan['candidate_count']} ready={plan['ready_count']} blocked={plan['blocked_count']}",
        f"Batches: {plan['batch_count']} at batch size {plan['batch_size']}",
        f"Action id: {intent.get('action_id')} status={intent.get('status')}",
        f"Executor adapter: {adapter}{' (record-only)' if adapter == 'fake' else ''}",
        "The ArcLink action worker will materialize the rollout. Live Pod refresh stays PG-UPGRADE gated. Track it with /action_status.",
    ]
    return {
        "message": "\n".join(lines),
        "mutation_performed": not already_queued,
        "rollout_plan": plan,
        "action_intent": intent,
    }


def _handle_action_status(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    target = command.args[0].strip() if command.args else ""
    lines = ["Operator Raven action status"]
    intents = _recent_action_intents(conn, action_id=target)
    operator_actions = _recent_operator_actions(conn)
    if not intents and not operator_actions:
        lines.append("No queued action intents or operator actions are on record.")
        return {"message": "\n".join(lines), "action_intents": [], "operator_actions": []}
    if intents:
        lines.append("Admin action intents:")
        for row in intents:
            lines.append(
                f"- {row.get('action_id')}: {row.get('action_type')} {row.get('target_kind')}:{row.get('target_id')} "
                f"status={row.get('status')} by={row.get('admin_id')}"
            )
    if operator_actions:
        lines.append("Operator actions:")
        for row in operator_actions:
            lines.append(
                f"- #{row.get('id')}: {row.get('action_kind')}"
                f"{(' ' + str(row.get('requested_target'))) if row.get('requested_target') else ''} "
                f"status={row.get('status')} by={row.get('requested_by')}"
            )
    return {
        "message": "\n".join(lines),
        "action_intents": intents,
        "operator_actions": operator_actions,
    }


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() not in {"", "0", "false", "no", "off"}


def _has_execute_batch_flag(args: Sequence[str]) -> bool:
    flags = {"--execute", "--execute-batch", "--execute_batch", "--execute-local-batch", "--apply-batch"}
    return any(str(arg or "").strip().lower() in flags for arg in args)


def _has_force_flag(args: Sequence[str]) -> bool:
    return any(str(arg or "").strip().lower() in {"--force", "force"} for arg in args)


def _has_include_stateful_flag(args: Sequence[str]) -> bool:
    return any(
        str(arg or "").strip().lower().replace("_", "-") in {
            "--include-stateful",
            "include-stateful",
            "--stateful",
            "stateful",
        }
        for arg in args
    )


def _fleet_last_capacity_guard(
    conn: sqlite3.Connection,
    host: Mapping[str, Any],
    *,
    drain: bool,
    force: bool,
) -> str:
    if not drain or force:
        return ""
    host_id = str(host.get("host_id") or "")
    try:
        from arclink_fleet import host_is_placement_eligible, list_fleet_hosts

        hosts = list_fleet_hosts(conn)
    except Exception:  # noqa: BLE001 - keep Raven fail-closed and conservative.
        return "could not prove other eligible worker capacity"
    target = next((item for item in hosts if str(item.get("host_id") or "") == host_id), host)
    if not host_is_placement_eligible(target):
        return ""
    other_eligible = [
        item
        for item in hosts
        if str(item.get("host_id") or "") != host_id and host_is_placement_eligible(item)
    ]
    if other_eligible:
        return ""
    return "draining this worker would leave zero active, healthy, undrained workers with placement capacity"


def _first_non_option_arg(args: Sequence[str]) -> str:
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        value = str(arg or "").strip()
        if not value:
            continue
        if value in {"--batch-size", "--batch_size"}:
            skip_next = True
            continue
        if value.startswith("--batch-size=") or value.startswith("--batch_size=") or value.startswith("batch_size="):
            continue
        if value.startswith("--"):
            continue
        return value
    return ""


def _batch_size_arg(args: Sequence[str]) -> int | None:
    args_list = [str(arg or "").strip() for arg in args]
    for index, value in enumerate(args_list):
        if value in {"--batch-size", "--batch_size"} and index + 1 < len(args_list):
            try:
                return int(args_list[index + 1])
            except ValueError:
                raise OperatorRavenError("rollout plan batch size must be an integer")
        for prefix in ("--batch-size=", "--batch_size=", "batch_size="):
            if value.startswith(prefix):
                try:
                    return int(value[len(prefix):])
                except ValueError:
                    raise OperatorRavenError("rollout plan batch size must be an integer")
    return None


def _safe_call(func: Callable[[], Any], *, default: Any) -> Any:
    try:
        return func()
    except Exception:  # noqa: BLE001 - read-only Operator status surfaces fail closed.
        return default


def _format_counts(counts: Mapping[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{status}={count}" for status, count in sorted(counts.items()))


def _count_by_status(conn: sqlite3.Connection, table: str) -> dict[str, int]:
    if table not in {"arclink_users", "arclink_deployments", "arclink_rollouts"}:
        return {}
    try:
        rows = conn.execute(f"SELECT status, COUNT(*) AS count FROM {table} GROUP BY status ORDER BY status").fetchall()
    except sqlite3.Error:
        return {}
    return {str(row["status"] or "unknown"): int(row["count"] or 0) for row in rows}


_GROUPABLE_COLUMNS = {
    "arclink_users": {"status", "entitlement_state"},
    "arclink_subscriptions": {"status"},
    "arclink_deployments": {"status"},
    "arclink_refuel_credits": {"status"},
    "memory_synthesis_cards": {"status"},
    "refresh_jobs": {"last_status"},
    "arclink_share_grants": {"status"},
}

_COUNTABLE_TABLES = frozenset(_GROUPABLE_COLUMNS) | {"notion_index_documents"}


def _group_counts(conn: sqlite3.Connection, table: str, column: str) -> dict[str, int]:
    if column not in _GROUPABLE_COLUMNS.get(table, set()):
        return {}
    try:
        rows = conn.execute(
            f"SELECT {column} AS value, COUNT(*) AS count FROM {table} GROUP BY {column} ORDER BY {column}"
        ).fetchall()
    except sqlite3.Error:
        return {}
    return {str(row["value"] or "unknown"): int(row["count"] or 0) for row in rows}


def _count_rows(conn: sqlite3.Connection, table: str, *, where: str = "") -> int:
    if table not in _COUNTABLE_TABLES:
        return 0
    allowed_where = {
        "": "",
        "status = 'active'": "status = 'active'",
        "state = 'active'": "state = 'active'",
    }
    clause = allowed_where.get(str(where or "").strip())
    if clause is None:
        return 0
    sql = f"SELECT COUNT(*) AS count FROM {table}"
    if clause:
        sql += f" WHERE {clause}"
    try:
        row = conn.execute(sql).fetchone()
    except sqlite3.Error:
        return 0
    return int(row["count"] if row is not None else 0)


def _sum_int(conn: sqlite3.Connection, table: str, column: str, *, where: str = "") -> int:
    allowed = {
        ("arclink_refuel_credits", "remaining_cents"),
        ("arclink_refuel_credits", "credit_cents"),
    }
    if (table, column) not in allowed:
        return 0
    allowed_where = {"": "", "status = 'active'": "status = 'active'"}
    clause = allowed_where.get(str(where or "").strip())
    if clause is None:
        return 0
    sql = f"SELECT COALESCE(SUM({column}), 0) AS total FROM {table}"
    if clause:
        sql += f" WHERE {clause}"
    try:
        row = conn.execute(sql).fetchone()
    except sqlite3.Error:
        return 0
    return int(row["total"] if row is not None else 0)


def _service_status_counts(conn: sqlite3.Connection, service_name: str) -> dict[str, int]:
    clean = str(service_name or "").strip()
    if clean not in {"qmd-mcp", "memory-synth", "managed-context"}:
        return {}
    try:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM arclink_service_health
            WHERE service_name = ?
            GROUP BY status
            ORDER BY status
            """,
            (clean,),
        ).fetchall()
    except sqlite3.Error:
        return {}
    return {str(row["status"] or "unknown"): int(row["count"] or 0) for row in rows}


def _recent_workspace_events(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(
            """
            SELECT subject_kind, subject_id, event_type
            FROM arclink_events
            WHERE event_type LIKE 'qmd_%'
               OR event_type LIKE 'memory_%'
               OR event_type LIKE 'notion_%'
               OR event_type LIKE 'share_%'
               OR event_type LIKE 'academy_%'
            ORDER BY created_at DESC, event_id DESC
            LIMIT 6
            """
        ).fetchall()
    except sqlite3.Error:
        return []
    return [dict(row) for row in rows]


def _operator_action_status_counts(conn: sqlite3.Connection) -> dict[str, int]:
    try:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS count FROM operator_actions WHERE status IN ('pending','running') GROUP BY status ORDER BY status"
        ).fetchall()
    except sqlite3.Error:
        return {}
    return {str(row["status"] or "unknown"): int(row["count"] or 0) for row in rows}


def _deployment_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(
            """
            SELECT deployment_id, user_id, prefix, status, agent_id, agent_title,
                   metadata_json, updated_at
            FROM arclink_deployments
            ORDER BY
              CASE WHEN status = 'active' THEN 0 ELSE 1 END,
              updated_at DESC,
              deployment_id
            """
        ).fetchall()
    except sqlite3.Error:
        return []
    return [dict(row) for row in rows]


def _deployment_metadata(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = str(row.get("metadata_json") or "{}")
    try:
        loaded = json.loads(raw)
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _deployment_is_operator(row: Mapping[str, Any]) -> bool:
    metadata = _deployment_metadata(row)
    return bool(metadata.get("operator_agent")) or str(row.get("deployment_id") or "") == "operator"


def _deployment_label(row: Mapping[str, Any]) -> str:
    metadata = _deployment_metadata(row)
    for key in ("agent_label", "agent_name", "display_name", "name"):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    for key in ("agent_title", "prefix", "deployment_id"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return "unnamed"


def _deployment_public(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "deployment_id": str(row.get("deployment_id") or ""),
        "user_id": str(row.get("user_id") or ""),
        "prefix": str(row.get("prefix") or ""),
        "status": str(row.get("status") or ""),
        "label": _deployment_label(row),
        "operator_agent": _deployment_is_operator(row),
        "updated_at": str(row.get("updated_at") or ""),
    }


def _operator_agent_line(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return "missing"
    row = rows[0]
    status = str(row.get("status") or "unknown")
    deployment_id = str(row.get("deployment_id") or "operator")
    if len(rows) == 1:
        return f"{status} ({deployment_id})"
    return f"{status} ({deployment_id}); WARNING {len(rows)} operator rows found"


def _legacy_agent_count(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("SELECT COUNT(*) AS count FROM agents WHERE status = 'active'").fetchone()
    except sqlite3.Error:
        return 0
    return int(row["count"] or 0) if row is not None else 0


def _deployment_health_summary(conn: sqlite3.Connection, deployment_id: str) -> str:
    if not deployment_id:
        return "unknown"
    try:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM arclink_service_health
            WHERE deployment_id = ?
            GROUP BY status
            ORDER BY status
            """,
            (deployment_id,),
        ).fetchall()
    except sqlite3.Error:
        return "unknown"
    counts = {str(row["status"] or "unknown"): int(row["count"] or 0) for row in rows}
    return _format_counts(counts)


def _admin_action_intent_exists(conn: sqlite3.Connection, idempotency_key: str) -> bool:
    clean = str(idempotency_key or "").strip()
    if not clean:
        return False
    try:
        row = conn.execute(
            "SELECT 1 FROM arclink_action_intents WHERE idempotency_key = ? LIMIT 1",
            (clean,),
        ).fetchone()
    except sqlite3.Error:
        return False
    return row is not None


def _recent_action_intents(conn: sqlite3.Connection, *, action_id: str = "") -> list[dict[str, Any]]:
    try:
        if action_id:
            rows = conn.execute(
                """
                SELECT action_id, admin_id, action_type, target_kind, target_id, status
                FROM arclink_action_intents
                WHERE action_id = ?
                """,
                (action_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT action_id, admin_id, action_type, target_kind, target_id, status
                FROM arclink_action_intents
                ORDER BY created_at DESC, action_id DESC
                LIMIT 8
                """
            ).fetchall()
    except sqlite3.Error:
        return []
    return [dict(row) for row in rows]


def _recent_operator_actions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(
            """
            SELECT id, action_kind, requested_target, requested_by, status
            FROM operator_actions
            ORDER BY id DESC
            LIMIT 8
            """
        ).fetchall()
    except sqlite3.Error:
        return []
    return [dict(row) for row in rows]


def _find_fleet_host(conn: sqlite3.Connection, target: str) -> dict[str, Any] | None:
    clean = str(target or "").strip().lower()
    if not clean:
        return None
    try:
        row = conn.execute(
            "SELECT * FROM arclink_fleet_hosts WHERE LOWER(host_id) = ? OR LOWER(hostname) = ?",
            (clean, clean),
        ).fetchone()
    except sqlite3.Error:
        return None
    return dict(row) if row is not None else None


def _find_users(conn: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
    clean = str(query or "").strip()
    if not clean:
        return []
    pattern = f"%{clean.lower()}%"
    try:
        rows = conn.execute(
            """
            SELECT user_id, email, display_name, status, entitlement_state
            FROM arclink_users
            WHERE LOWER(user_id) = ?
               OR LOWER(email) = ?
               OR LOWER(display_name) LIKE ?
               OR LOWER(email) LIKE ?
            ORDER BY user_id
            LIMIT 5
            """,
            (clean.lower(), clean.lower(), pattern, pattern),
        ).fetchall()
    except sqlite3.Error:
        return []
    return [dict(row) for row in rows]


def _deployments_for_user(conn: sqlite3.Connection, user_id: str) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(
            """
            SELECT deployment_id, status
            FROM arclink_deployments
            WHERE user_id = ?
            ORDER BY deployment_id
            """,
            (user_id,),
        ).fetchall()
    except sqlite3.Error:
        return []
    return [dict(row) for row in rows]


def _academy_summary_for_user(conn: sqlite3.Connection, user_id: str) -> dict[str, Any]:
    try:
        from arclink_crew_recipes import crew_academy_status

        status = crew_academy_status(conn, user_id=user_id)
    except Exception:  # noqa: BLE001 - Operator Raven status must fail closed.
        status = {
            "status": "unavailable",
            "summary": "Academy status unavailable; open the dashboard Crew Training panel.",
            "source_count": 0,
            "weekly_review_status": "unavailable",
            "evaluation_status": "unavailable",
            "graduation_status": "unavailable",
            "next_review_at": "",
            "review_needed_count": 0,
            "blocked_source_count": 0,
            "proof_gates": ["PG-PROVIDER", "PG-HERMES"],
            "next_actions": ["Open the dashboard Crew Training panel."],
            "live_proof_required": True,
        }
    return {
        "status": str(status.get("status") or "unknown"),
        "summary": str(status.get("summary") or ""),
        "source_count": int(status.get("source_count") or 0),
        "weekly_review_status": str(status.get("weekly_review_status") or "not_started"),
        "evaluation_status": str(status.get("evaluation_status") or "not_started"),
        "graduation_status": str(status.get("graduation_status") or "not_started"),
        "next_review_at": str(status.get("next_review_at") or ""),
        "review_needed_count": int(status.get("review_needed_count") or 0),
        "blocked_source_count": int(status.get("blocked_source_count") or 0),
        "proof_gates": [str(item) for item in status.get("proof_gates") or []],
        "next_actions": [str(item) for item in status.get("next_actions") or []],
        "manifest_id": str(status.get("manifest_id") or ""),
        "live_proof_required": bool(status.get("live_proof_required", True)),
    }


def _find_deployment(conn: sqlite3.Connection, deployment_id: str) -> dict[str, Any] | None:
    clean = str(deployment_id or "").strip()
    if not clean:
        return None
    try:
        row = conn.execute(
            """
            SELECT deployment_id, user_id, prefix, status, agent_id, agent_title
            FROM arclink_deployments
            WHERE deployment_id = ?
            """,
            (clean,),
        ).fetchone()
    except sqlite3.Error:
        return None
    return dict(row) if row is not None else None


def _redact_text(text: str) -> str:
    lines = []
    for line in str(text or "").splitlines():
        redacted = redact_secret_material(line)
        if redacted != line:
            lines.append(redacted)
        elif _SECRETISH_RE.search(line) and "=" in line:
            key, _, _value = line.partition("=")
            lines.append(f"{key}=<redacted>")
        else:
            lines.append(line)
    return "\n".join(lines)
