#!/usr/bin/env python3
"""Control-node inventory registry and local CLI."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shlex
import sqlite3
import subprocess
import sys
from typing import Any, Callable, Mapping, Sequence

from arclink_asu import ArcLinkASUError, compute_asu, current_load
from arclink_boundary import json_dumps_safe, json_loads_safe
from arclink_control import Config, append_arclink_audit, connect_db, ensure_schema, utc_now_iso
from arclink_fleet import register_fleet_host, update_fleet_host
from arclink_secrets_regex import redact_then_truncate


class ArcLinkInventoryError(ValueError):
    pass


RunFn = Callable[..., subprocess.CompletedProcess[str]]


def _inventory_id() -> str:
    return f"machine_{secrets.token_hex(12)}"


def _clean_provider(value: str) -> str:
    provider = str(value or "").strip().lower()
    if provider not in {"local", "manual", "hetzner", "linode"}:
        raise ArcLinkInventoryError(f"unsupported inventory provider: {provider or '<empty>'}")
    return provider


def _clean_status(value: str) -> str:
    status = str(value or "").strip().lower()
    if status not in {"pending", "ready", "draining", "degraded", "removed"}:
        raise ArcLinkInventoryError(f"unsupported inventory machine status: {status or '<empty>'}")
    return status


def _safe_json(value: Mapping[str, Any] | None) -> str:
    return json_dumps_safe(value, label="ArcLink inventory", error_cls=ArcLinkInventoryError)


def register_inventory_machine(
    conn: sqlite3.Connection,
    *,
    provider: str,
    hostname: str,
    ssh_host: str = "",
    ssh_user: str = "",
    region: str = "",
    provider_resource_id: str = "",
    status: str = "pending",
    asu_capacity: float = 0,
    asu_consumed: float = 0,
    hardware_summary: Mapping[str, Any] | None = None,
    connectivity_summary: Mapping[str, Any] | None = None,
    machine_host_link: str = "",
    capacity_slots: int | None = None,
    tags: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    clean_provider = _clean_provider(provider)
    clean_hostname = str(hostname or "").strip().lower()
    if not clean_hostname:
        raise ArcLinkInventoryError("inventory machines require a hostname")
    clean_status = _clean_status(status)
    clean_region = str(region or "").strip().lower()
    clean_ssh_host = str(ssh_host or "").strip()
    clean_ssh_user = str(ssh_user or "").strip()
    clean_resource_id = str(provider_resource_id or "").strip()
    host_link = str(machine_host_link or "").strip()
    now = utc_now_iso()

    if not host_link and capacity_slots is not None:
        host = register_fleet_host(
            conn,
            hostname=clean_hostname,
            region=clean_region,
            capacity_slots=max(1, int(capacity_slots)),
            tags=tags,
            metadata=metadata,
        )
        host_link = str(host["host_id"])

    existing = conn.execute(
        """
        SELECT * FROM arclink_inventory_machines
        WHERE provider = ?
          AND ((provider_resource_id != '' AND provider_resource_id = ?) OR LOWER(hostname) = ?)
        ORDER BY registered_at ASC
        LIMIT 1
        """,
        (clean_provider, clean_resource_id, clean_hostname),
    ).fetchone()
    if existing is not None:
        conn.execute(
            """
            UPDATE arclink_inventory_machines
            SET provider_resource_id = ?, hostname = ?, ssh_host = ?, ssh_user = ?,
                region = ?, status = ?, asu_capacity = ?, asu_consumed = ?,
                hardware_summary_json = ?, connectivity_summary_json = ?,
                machine_host_link = ?
            WHERE machine_id = ?
            """,
            (
                clean_resource_id,
                clean_hostname,
                clean_ssh_host,
                clean_ssh_user,
                clean_region,
                clean_status,
                float(asu_capacity),
                float(asu_consumed),
                _safe_json(hardware_summary),
                _safe_json(connectivity_summary),
                host_link,
                str(existing["machine_id"]),
            ),
        )
        machine_id = str(existing["machine_id"])
    else:
        machine_id = _inventory_id()
        conn.execute(
            """
            INSERT INTO arclink_inventory_machines (
              machine_id, provider, provider_resource_id, hostname, ssh_host, ssh_user,
              region, status, asu_capacity, asu_consumed, hardware_summary_json,
              connectivity_summary_json, machine_host_link, registered_at, last_probed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '')
            """,
            (
                machine_id,
                clean_provider,
                clean_resource_id,
                clean_hostname,
                clean_ssh_host,
                clean_ssh_user,
                clean_region,
                clean_status,
                float(asu_capacity),
                float(asu_consumed),
                _safe_json(hardware_summary),
                _safe_json(connectivity_summary),
                host_link,
                now,
            ),
        )
    append_arclink_audit(
        conn,
        action="inventory_machine_registered",
        target_kind="inventory_machine",
        target_id=machine_id,
        reason="operator registered inventory machine",
        metadata={"provider": clean_provider, "hostname": clean_hostname, "machine_host_link": host_link},
        commit=False,
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM arclink_inventory_machines WHERE machine_id = ?", (machine_id,)).fetchone())


def list_inventory_machines(conn: sqlite3.Connection, *, include_removed: bool = False) -> list[dict[str, Any]]:
    if include_removed:
        rows = conn.execute("SELECT * FROM arclink_inventory_machines ORDER BY provider, hostname").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM arclink_inventory_machines WHERE status != 'removed' ORDER BY provider, hostname"
        ).fetchall()
    machines = []
    for row in rows:
        item = dict(row)
        try:
            item["asu_consumed"] = current_load(str(item["machine_id"]), conn)
        except ArcLinkASUError:
            item["asu_consumed"] = float(item.get("asu_consumed") or 0)
        machines.append(item)
    return machines


def get_inventory_machine(conn: sqlite3.Connection, key: str) -> dict[str, Any]:
    clean = str(key or "").strip()
    row = conn.execute(
        """
        SELECT * FROM arclink_inventory_machines
        WHERE machine_id = ? OR LOWER(hostname) = LOWER(?)
        LIMIT 1
        """,
        (clean, clean),
    ).fetchone()
    if row is None:
        raise ArcLinkInventoryError(f"unknown inventory machine: {key}")
    return dict(row)


def parse_probe_output(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in str(stdout or "").splitlines() if line.strip()]
    if not lines:
        raise ArcLinkInventoryError("empty probe output")
    try:
        vcpu = int(lines[0])
    except ValueError as exc:
        raise ArcLinkInventoryError("probe output missing nproc result") from exc
    mem_kib = 0
    disk_gib = 0
    docker_version = ""
    compose_version = ""
    for line in lines[1:]:
        if line.startswith("MemTotal:"):
            parts = line.split()
            if len(parts) >= 2:
                mem_kib = int(parts[1])
        elif line.startswith("/dev/") or line.startswith("overlay") or line.startswith("Filesystem"):
            continue
        elif line.lower().startswith("docker version"):
            docker_version = line
        elif line.lower().startswith("docker compose"):
            compose_version = line
        else:
            fields = line.split()
            if len(fields) >= 2 and fields[1].endswith("G"):
                try:
                    disk_gib = max(disk_gib, int(fields[1].rstrip("G")))
                except ValueError:
                    pass
    return {
        "vcpu_cores": vcpu,
        "ram_gib": round(mem_kib / 1024 / 1024, 2) if mem_kib else 0,
        "disk_gib": disk_gib,
        "docker_version": docker_version,
        "docker_compose_version": compose_version,
    }


def probe_inventory_machine(
    conn: sqlite3.Connection,
    *,
    key: str,
    fleet_key_path: str = "",
    known_hosts_file: str = "",
    runner: RunFn = subprocess.run,
) -> dict[str, Any]:
    machine = get_inventory_machine(conn, key)
    ssh_host = str(machine.get("ssh_host") or machine.get("hostname") or "").strip()
    ssh_user = str(machine.get("ssh_user") or "arclink").strip()
    if not ssh_host:
        raise ArcLinkInventoryError("inventory machine has no SSH host")
    remote = "nproc; cat /proc/meminfo | head -3; df -BG / /var/lib/docker 2>/dev/null; docker --version; docker compose version"
    command = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
    if known_hosts_file:
        command.extend(["-o", f"UserKnownHostsFile={known_hosts_file}"])
    if fleet_key_path:
        command.extend(["-i", fleet_key_path])
    command.extend([f"{ssh_user}@{ssh_host}", "--", remote])
    try:
        completed = runner(command, text=True, capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        message = redact_then_truncate(str(exc), limit=240)
        conn.execute(
            """
            UPDATE arclink_inventory_machines
            SET status = 'degraded', connectivity_summary_json = ?, last_probed_at = ?
            WHERE machine_id = ?
            """,
            (_safe_json({"ok": False, "error": message}), utc_now_iso(), machine["machine_id"]),
        )
        conn.commit()
        raise ArcLinkInventoryError(message) from exc
    if completed.returncode != 0:
        message = redact_then_truncate(completed.stderr or completed.stdout or "probe failed", limit=240)
        conn.execute(
            """
            UPDATE arclink_inventory_machines
            SET status = 'degraded', connectivity_summary_json = ?, last_probed_at = ?
            WHERE machine_id = ?
            """,
            (_safe_json({"ok": False, "error": message}), utc_now_iso(), machine["machine_id"]),
        )
        conn.commit()
        raise ArcLinkInventoryError(message)
    hardware = parse_probe_output(completed.stdout)
    asu_capacity = compute_asu(hardware)
    consumed = current_load(str(machine["machine_id"]), conn)
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE arclink_inventory_machines
        SET status = 'ready', asu_capacity = ?, asu_consumed = ?,
            hardware_summary_json = ?, connectivity_summary_json = ?,
            last_probed_at = ?
        WHERE machine_id = ?
        """,
        (
            float(asu_capacity),
            float(consumed),
            _safe_json(hardware),
            _safe_json({"ok": True, "ssh_host": ssh_host}),
            now,
            machine["machine_id"],
        ),
    )
    if machine.get("machine_host_link"):
        update_fleet_host(conn, host_id=str(machine["machine_host_link"]), status="active", observed_load=int(consumed))
    append_arclink_audit(
        conn,
        action="inventory_machine_probed",
        target_kind="inventory_machine",
        target_id=str(machine["machine_id"]),
        reason="operator probed inventory machine",
        metadata={"asu_capacity": asu_capacity, "hostname": machine.get("hostname", "")},
        commit=False,
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM arclink_inventory_machines WHERE machine_id = ?", (machine["machine_id"],)).fetchone())


def drain_inventory_machine(conn: sqlite3.Connection, key: str) -> dict[str, Any]:
    machine = get_inventory_machine(conn, key)
    if machine.get("machine_host_link"):
        update_fleet_host(conn, host_id=str(machine["machine_host_link"]), drain=True)
    conn.execute("UPDATE arclink_inventory_machines SET status = 'draining' WHERE machine_id = ?", (machine["machine_id"],))
    append_arclink_audit(
        conn,
        action="inventory_machine_drained",
        target_kind="inventory_machine",
        target_id=str(machine["machine_id"]),
        reason="operator drained inventory machine",
        metadata={"hostname": machine.get("hostname", "")},
        commit=False,
    )
    conn.commit()
    return get_inventory_machine(conn, str(machine["machine_id"]))


def remove_inventory_machine(conn: sqlite3.Connection, key: str) -> dict[str, Any]:
    machine = get_inventory_machine(conn, key)
    host_id = str(machine.get("machine_host_link") or "")
    if host_id:
        active = conn.execute(
            "SELECT COUNT(*) AS count FROM arclink_deployment_placements WHERE host_id = ? AND status = 'active'",
            (host_id,),
        ).fetchone()["count"]
        if int(active or 0) > 0:
            raise ArcLinkInventoryError("inventory machine has active placements; migrate or drain first")
        update_fleet_host(conn, host_id=host_id, status="offline", drain=True)
    conn.execute("UPDATE arclink_inventory_machines SET status = 'removed' WHERE machine_id = ?", (machine["machine_id"],))
    append_arclink_audit(
        conn,
        action="inventory_machine_removed",
        target_kind="inventory_machine",
        target_id=str(machine["machine_id"]),
        reason="operator removed inventory machine",
        metadata={"hostname": machine.get("hostname", "")},
        commit=False,
    )
    conn.commit()
    return get_inventory_machine(conn, str(machine["machine_id"]))


def _print_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("No inventory machines registered.")
        return
    print("machine_id provider hostname status asu_capacity asu_consumed last_probed_at")
    for row in rows:
        print(
            " ".join(
                [
                    str(row["machine_id"]),
                    str(row["provider"]),
                    str(row["hostname"]),
                    str(row["status"]),
                    f"{float(row.get('asu_capacity') or 0):g}",
                    f"{float(row.get('asu_consumed') or 0):g}",
                    str(row.get("last_probed_at") or "-"),
                ]
            )
        )


def _load_conn() -> sqlite3.Connection:
    cfg = Config.from_env()
    conn = connect_db(cfg)
    ensure_schema(conn, cfg)
    return conn


def _cmd_add_cloud(provider: str) -> int:
    if provider == "hetzner":
        token_name = "HETZNER_API_TOKEN"
        from arclink_inventory_hetzner import HetznerInventoryProvider as Provider
    else:
        token_name = "LINODE_API_TOKEN"
        from arclink_inventory_linode import LinodeInventoryProvider as Provider
    try:
        client = Provider(token=os.environ.get(token_name, ""))
    except Exception:
        print(f"Configure {token_name} to enable {provider} inventory.", file=sys.stderr)
        return 1
    servers = client.list_servers()
    print(json.dumps({"provider": provider, "servers": servers}, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arclink-inventory")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    probe = sub.add_parser("probe")
    probe.add_argument("machine")
    add = sub.add_parser("add")
    add_sub = add.add_subparsers(dest="provider", required=True)
    manual = add_sub.add_parser("manual")
    manual.add_argument("--hostname", required=True)
    manual.add_argument("--ssh-host", default="")
    manual.add_argument("--ssh-user", default="arclink")
    manual.add_argument("--region", default="")
    manual.add_argument("--capacity-slots", type=int, default=4)
    manual.add_argument("--tags-json", default="{}")
    add_sub.add_parser("hetzner")
    add_sub.add_parser("linode")
    drain = sub.add_parser("drain")
    drain.add_argument("machine")
    remove = sub.add_parser("remove")
    remove.add_argument("machine")
    strategy = sub.add_parser("set-strategy")
    strategy.add_argument("strategy", choices=("headroom", "standard_unit"))

    args = parser.parse_args(argv)
    try:
        if args.command == "add" and args.provider in {"hetzner", "linode"}:
            return _cmd_add_cloud(args.provider)
        conn = _load_conn()
        if args.command == "list":
            _print_table(list_inventory_machines(conn))
        elif args.command == "probe":
            row = probe_inventory_machine(
                conn,
                key=args.machine,
                fleet_key_path=os.environ.get("ARCLINK_FLEET_SSH_KEY_PATH", ""),
                known_hosts_file=os.environ.get("ARCLINK_FLEET_SSH_KNOWN_HOSTS_FILE", ""),
            )
            print(json.dumps(dict(row), sort_keys=True))
        elif args.command == "add" and args.provider == "manual":
            tags = json_loads_safe(args.tags_json)
            row = register_inventory_machine(
                conn,
                provider="manual",
                hostname=args.hostname,
                ssh_host=args.ssh_host or args.hostname,
                ssh_user=args.ssh_user,
                region=args.region,
                status="pending",
                capacity_slots=args.capacity_slots,
                tags=tags,
                metadata={"ssh_host": args.ssh_host or args.hostname, "ssh_user": args.ssh_user},
            )
            print(json.dumps(dict(row), sort_keys=True))
        elif args.command == "drain":
            print(json.dumps(drain_inventory_machine(conn, args.machine), sort_keys=True))
        elif args.command == "remove":
            print(json.dumps(remove_inventory_machine(conn, args.machine), sort_keys=True))
        elif args.command == "set-strategy":
            print(f"ARCLINK_FLEET_PLACEMENT_STRATEGY={args.strategy}")
        return 0
    except Exception as exc:
        print(redact_then_truncate(str(exc), limit=300), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
