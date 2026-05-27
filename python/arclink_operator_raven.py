#!/usr/bin/env python3
"""Read-only and dry-run Operator Raven command surface."""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable, Mapping


class OperatorRavenError(ValueError):
    pass


UpgradeCheckRunner = Callable[[], Mapping[str, Any]]


@dataclass(frozen=True)
class OperatorRavenCommand:
    name: str
    args: tuple[str, ...]
    dry_run: bool
    raw_text: str


_COMMAND_ALIASES = {
    "operator_status": "status",
    "operatorstatus": "status",
    "raven_status": "status",
    "ravenstatus": "status",
    "control_status": "status",
    "controlstatus": "status",
    "op_status": "status",
    "opstatus": "status",
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
    "pod_repair": "pod_repair_dry_run",
    "podrepair": "pod_repair_dry_run",
    "repair_pod": "pod_repair_dry_run",
    "repairpod": "pod_repair_dry_run",
    "operator_upgrade_check": "upgrade_check",
    "operatorupgradecheck": "upgrade_check",
    "upgrade_check": "upgrade_check",
    "upgradecheck": "upgrade_check",
}

_SECRETISH_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization|bearer|oauth|webhook[_-]?secret)"
)


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
    dry_run = any(arg.strip().lower() in {"--dry-run", "--dry_run", "dry-run", "dry_run"} for arg in args)
    clean_args = tuple(arg for arg in args if arg.strip().lower() not in {"--dry-run", "--dry_run", "dry-run", "dry_run"})
    return OperatorRavenCommand(name=name, args=clean_args, dry_run=dry_run, raw_text=raw)


def operator_raven_command_requested(text: str) -> bool:
    return parse_operator_raven_command(text) is not None


def dispatch_operator_raven_command(
    conn: sqlite3.Connection,
    text: str,
    *,
    env: Mapping[str, str] | None = None,
    upgrade_check_runner: UpgradeCheckRunner | None = None,
) -> dict[str, Any]:
    command = parse_operator_raven_command(text)
    if command is None:
        return {"handled": False, "message": "", "mutation_performed": False}
    handlers = {
        "status": _handle_status,
        "fleet_list": _handle_fleet_list,
        "worker_probe": _handle_worker_probe,
        "user_lookup": _handle_user_lookup,
        "pod_repair_dry_run": _handle_pod_repair_dry_run,
        "upgrade_check": _handle_upgrade_check,
    }
    result = handlers[command.name](
        conn,
        command,
        env=env or {},
        upgrade_check_runner=upgrade_check_runner,
    )
    result.setdefault("handled", True)
    result.setdefault("command", command.name)
    result.setdefault("mutation_performed", False)
    result["message"] = _redact_text(str(result.get("message") or ""))
    return result


def _handle_status(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
) -> dict[str, Any]:
    from arclink_dashboard import admin_action_execution_readiness
    from arclink_fleet import fleet_capacity_summary

    capacity = _safe_call(lambda: fleet_capacity_summary(conn), default={"hosts": [], "available_slots": 0})
    readiness = _safe_call(lambda: admin_action_execution_readiness(env=env), default={"executor_adapter": "disabled", "action_support": {}})
    eligible = [
        host for host in capacity.get("hosts", [])
        if str(host.get("status") or "") == "active"
        and not bool(host.get("drain"))
        and int(host.get("headroom") or 0) > 0
    ]
    provisioner_enabled = _truthy(env.get("ARCLINK_CONTROL_PROVISIONER_ENABLED", ""))
    if provisioner_enabled and eligible:
        provisioning = f"ready to provision ArcPods ({len(eligible)} eligible worker(s), {int(capacity.get('available_slots') or 0)} available slot(s))"
    elif provisioner_enabled:
        provisioning = "blocked, provisioner enabled but no eligible worker has available capacity"
    else:
        provisioning = "control plane up, ArcPod provisioning disabled until a worker is registered and smoke-tested"
    user_counts = _count_by_status(conn, "arclink_users")
    deployment_counts = _count_by_status(conn, "arclink_deployments")
    support = readiness.get("action_support") if isinstance(readiness, Mapping) else {}
    queueable = sum(1 for item in (support or {}).values() if bool(item.get("queueable")))
    lines = [
        "Operator Raven status",
        f"Provisioning: {provisioning}",
        f"Fleet: {int(capacity.get('active_hosts') or 0)} active / {int(capacity.get('total_hosts') or 0)} total worker(s)",
        f"Users: {_format_counts(user_counts)}",
        f"Deployments: {_format_counts(deployment_counts)}",
        f"Admin actions: {queueable} queueable via {readiness.get('executor_adapter', 'disabled')}",
        "Live proof still required: PG-PROD, PG-BOTS, PG-PROVIDER, PG-PROVISION, PG-UPGRADE",
        "Next: /operator_fleet, /user_lookup <query>, /pod_repair <deployment> --dry-run, /upgrade_check",
    ]
    return {"message": "\n".join(lines), "readiness": provisioning}


def _handle_fleet_list(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
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
        lines.append(
            f"- {row.get('user_id')}: {row.get('display_name') or 'unnamed'} "
            f"<{row.get('email') or 'no-email'}>, status={row.get('status')}, "
            f"entitlement={row.get('entitlement_state') or 'none'}, deployments={_format_counts(dep_counts)}"
        )
    if len(rows) == 5:
        lines.append("Showing first 5 matches.")
    return {"message": "\n".join(lines), "users": rows}


def _handle_pod_repair_dry_run(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
) -> dict[str, Any]:
    if not command.dry_run:
        return {
            "message": "Pod repair is dry-run only in this Operator Raven slice. Use /pod_repair <deployment-id> --dry-run.",
        }
    deployment_id = command.args[0] if command.args else ""
    if not deployment_id:
        return {"message": "Use /pod_repair <deployment-id> --dry-run."}
    deployment = _find_deployment(conn, deployment_id)
    if deployment is None:
        return {"message": f"Pod repair dry-run: no deployment matched {deployment_id}."}
    from arclink_dashboard import admin_action_execution_readiness

    readiness = admin_action_execution_readiness(env=env)
    support = readiness.get("action_support", {})
    candidates = [
        name for name in ("restart", "reprovision", "dns_repair")
        if bool((support.get(name) or {}).get("queueable"))
    ]
    if not candidates:
        candidates_text = "no repair actions are queueable until executor probes pass"
    else:
        candidates_text = ", ".join(candidates)
    lines = [
        "Pod repair dry-run",
        f"Deployment: {deployment.get('deployment_id')} status={deployment.get('status')} user={deployment.get('user_id')}",
        f"Candidate local actions: {candidates_text}",
        "No action was queued and no deployment, Docker, DNS, SSH, or provider state was changed.",
    ]
    return {"message": "\n".join(lines), "deployment": deployment}


def _handle_upgrade_check(
    conn: sqlite3.Connection,
    command: OperatorRavenCommand,
    *,
    env: Mapping[str, str],
    upgrade_check_runner: UpgradeCheckRunner | None,
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
    lines.append("No upgrade was queued or run.")
    return {"message": "\n".join(lines), "upgrade": result}


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() not in {"", "0", "false", "no", "off"}


def _safe_call(func: Callable[[], Any], *, default: Any) -> Any:
    try:
        return func()
    except sqlite3.Error:
        return default


def _count_by_status(conn: sqlite3.Connection, table: str) -> dict[str, int]:
    if table not in {"arclink_users", "arclink_deployments"}:
        return {}
    try:
        rows = conn.execute(f"SELECT status, COUNT(*) AS count FROM {table} GROUP BY status ORDER BY status").fetchall()
    except sqlite3.Error:
        return {}
    return {str(row["status"] or "unknown"): int(row["count"] or 0) for row in rows}


def _format_counts(counts: Mapping[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{status}={count}" for status, count in sorted(counts.items()))


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
