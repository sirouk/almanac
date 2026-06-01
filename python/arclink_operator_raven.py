#!/usr/bin/env python3
"""Operator Raven command surface: read/dry-run previews plus real action queueing.

Read commands (``status``, ``fleet_list``, ``user_lookup``, ``academy_status``,
``upgrade_check``, ``action_status``) never mutate. The mutation commands
(``pod_repair``, ``rollout``, ``host_upgrade``, ``pin_upgrade``) behave in three
ways:

* ``--dry-run`` -> a preview that changes nothing (the historical behavior).
* no ``--dry-run`` and no operator ``actor_id`` -> fail closed (read-only
  refusal). The adapter must prove operator identity before a real action runs.
* no ``--dry-run`` with an operator ``actor_id`` but no explicit confirmation
  token -> refuse. The operator must append ``confirm`` or the configured
  approval code after reviewing a dry-run preview.
* no ``--dry-run`` with an operator ``actor_id`` and explicit confirmation ->
  QUEUE a real, audited intent that the ArcLink action worker / enrollment
  provisioner executes asynchronously, honoring the configured
  ``ARCLINK_EXECUTOR_ADAPTER`` (``fake`` records only). Operator Raven never
  runs Docker/SSH/provider commands inline; it only queues intents. Live
  mutation stays gated by the executor adapter and the per-action live proof
  gate.
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
    "worker_probe": "worker_probe",
    "workerprobe": "worker_probe",
    "probe_worker": "worker_probe",
    "probeworker": "worker_probe",
    "operator_user": "user_lookup",
    "operatoruser": "user_lookup",
    "user_lookup": "user_lookup",
    "userlookup": "user_lookup",
    "user": "user_lookup",
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

# Commands that, outside of --dry-run, queue a real audited intent. The adapter
# must supply an operator actor identity plus an explicit confirmation token
# (or clear any configured approval code) before these run for real.
MUTATING_COMMANDS = frozenset({"pod_repair", "rollout", "host_upgrade", "pin_upgrade"})

# Pinned components the operator can upgrade through Operator Raven. Mirrors the
# component-upgrade rails in bin/deploy.sh / bin/component-upgrade.sh.
PIN_UPGRADE_COMPONENTS = (
    "hermes",
    "qmd",
    "nextcloud",
    "postgres",
    "redis",
    "nvm",
    "node",
)

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
        "worker_probe": _handle_worker_probe,
        "user_lookup": _handle_user_lookup,
        "pod_repair": _handle_pod_repair,
        "upgrade_check": _handle_upgrade_check,
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
        "Act: /pod_repair <deployment> [restart|reprovision|dns_repair], /rollout <target>, /upgrade, /pin_upgrade <component> (add --dry-run to preview; append confirm or the operator approval code to queue)",
        "Next: /operator_fleet, /user_lookup <query>, /academy_status <query>, /action_status, then act with the commands above",
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
    lines.append("No upgrade was queued or run. Run /upgrade to apply the host upgrade, or /pin_upgrade <component>.")
    return {"message": "\n".join(lines), "upgrade": result}


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
    if command.dry_run:
        return {
            "message": (
                f"Pin upgrade dry-run for {component}: would queue an operator 'pin-upgrade' action that the root "
                f"maintenance loop applies (config/pins.json bump + component upgrade). No action was queued."
            ),
        }
    blocked = _require_operator_actor(actor_id, "Pin upgrade")
    if blocked is not None:
        return blocked
    needs_confirm = _require_operator_confirmation(command)
    if needs_confirm is not None:
        return needs_confirm
    try:
        from arclink_control import request_operator_action

        action_row, created = request_operator_action(
            conn,
            action_kind="pin-upgrade",
            requested_by=actor_id,
            request_source="operator-raven",
            requested_target=component,
            dedupe_by_target=True,
        )
    except Exception as exc:  # noqa: BLE001
        return {"message": f"Could not queue pinned-component upgrade: {exc}"}
    status = str(action_row.get("status") or "pending")
    if created:
        message = f"Operator Raven queued a pinned-component upgrade for {component}. The root maintenance loop will apply it. Track it with /action_status."
    elif status == "running":
        message = f"A {component} pinned-component upgrade is already running. Track it with /action_status."
    else:
        message = f"A {component} pinned-component upgrade is already queued. Track it with /action_status."
    return {
        "message": message,
        "mutation_performed": bool(created),
        "operator_action": action_row,
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
    except sqlite3.Error:
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
        if _SECRETISH_RE.search(line) and "=" in line:
            key, _, _value = line.partition("=")
            lines.append(f"{key}=<redacted>")
        else:
            lines.append(line)
    return "\n".join(lines)
