#!/usr/bin/env python3
"""Run ArcLink health and notify the operator when failures change."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from arclink_control import (
    Config,
    active_deploy_operation,
    connect_db,
    get_setting,
    queue_notification,
    upsert_setting,
    utc_now_iso,
)


STATUS_KEY = "arclink_health_watch_last_status"
FINGERPRINT_KEY = "arclink_health_watch_last_fingerprint"
SUMMARY_KEY = "arclink_health_watch_last_summary"
LAST_NOTIFIED_AT_KEY = "arclink_health_watch_last_notified_at"

SUMMARY_RE = re.compile(r"Summary:\s+(\d+)\s+ok,\s+(\d+)\s+warn,\s+(\d+)\s+fail", re.IGNORECASE)


def _bool_env(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _health_command(cfg: Config) -> list[str]:
    configured = str(os.environ.get("ARCLINK_HEALTH_WATCH_HEALTH_CMD") or "").strip()
    if configured:
        return shlex.split(configured)
    return [str(cfg.repo_dir / "bin" / "health.sh")]


def _config_file_for_child(cfg: Config) -> str:
    configured = str(os.environ.get("ARCLINK_CONFIG_FILE") or "").strip()
    if configured:
        return configured
    candidate = cfg.private_dir / "config" / "arclink.env"
    return str(candidate)


def _run_health(cfg: Config, *, timeout_seconds: int, strict: bool) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["ARCLINK_CONFIG_FILE"] = _config_file_for_child(cfg)
    env["ARCLINK_HEALTH_WATCH_CHILD"] = "1"
    env["ARCLINK_HEALTH_STRICT"] = "1" if strict else env.get("ARCLINK_HEALTH_STRICT", "0")
    return subprocess.run(
        _health_command(cfg),
        text=True,
        capture_output=True,
        check=False,
        timeout=max(5, int(timeout_seconds)),
        env=env,
    )


def _summary_from_output(stdout: str) -> dict[str, Any]:
    summary: dict[str, Any] = {"ok": 0, "warn": 0, "fail": 0, "line": ""}
    for line in stdout.splitlines():
        match = SUMMARY_RE.search(line)
        if not match:
            continue
        summary = {
            "ok": int(match.group(1)),
            "warn": int(match.group(2)),
            "fail": int(match.group(3)),
            "line": line.strip(),
        }
    return summary


def _health_lines(stdout: str, marker: str) -> list[str]:
    prefix = f"[{marker}]"
    legacy_prefix = f"{marker.upper()} "
    lines: list[str] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if line.startswith(prefix):
            lines.append(line[len(prefix) :].strip())
        elif line.startswith(legacy_prefix):
            lines.append(line)
    return lines


def _clip_lines(lines: list[str], *, max_lines: int = 12, max_chars: int = 2200) -> list[str]:
    clipped: list[str] = []
    used = 0
    for line in lines:
        clean = " ".join(str(line).split())
        if not clean:
            continue
        if len(clipped) >= max_lines or used + len(clean) > max_chars:
            remaining = max(0, len(lines) - len(clipped))
            if remaining:
                clipped.append(f"... {remaining} more; run ./deploy.sh health for the full report")
            break
        clipped.append(clean)
        used += len(clean)
    return clipped


def _failure_fingerprint(payload: dict[str, Any]) -> str:
    material = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _operator_target(cfg: Config) -> tuple[str, str]:
    channel_kind = str(cfg.operator_notify_platform or "tui-only").strip().lower() or "tui-only"
    target_id = str(cfg.operator_notify_channel_id or channel_kind or "operator").strip() or "operator"
    return target_id, channel_kind


def _queue_operator_message(cfg: Config, message: str) -> None:
    with connect_db(cfg) as conn:
        target_id, channel_kind = _operator_target(cfg)
        queue_notification(
            conn,
            target_kind="operator",
            target_id=target_id,
            channel_kind=channel_kind,
            message=message,
        )


def _format_problem_message(status: str, summary: dict[str, Any], fingerprint: str, problem_lines: list[str]) -> str:
    title = "ArcLink health-watch detected a failing health check"
    if status == "warn":
        title = "ArcLink health-watch detected health warnings"
    lines = [
        title,
        f"Time: {utc_now_iso()}",
        f"Summary: {summary.get('line') or 'health summary unavailable'}",
        f"Fingerprint: {fingerprint}",
        "",
        "Run: ./deploy.sh health",
    ]
    if problem_lines:
        lines.extend(["", "Current signals:"])
        lines.extend(f"- {line}" for line in _clip_lines(problem_lines))
    return "\n".join(lines)


def _format_recovery_message(summary: dict[str, Any], previous_fingerprint: str) -> str:
    return "\n".join(
        [
            "ArcLink health-watch recovered",
            f"Time: {utc_now_iso()}",
            f"Summary: {summary.get('line') or 'health summary unavailable'}",
            f"Previous fingerprint: {previous_fingerprint or 'unknown'}",
            "",
            "Run: ./deploy.sh health",
        ]
    )


def run_once(
    cfg: Config,
    *,
    timeout_seconds: int = 300,
    strict: bool = False,
    notify_warnings: bool = False,
) -> dict[str, Any]:
    deploy_operation = active_deploy_operation(cfg)
    if deploy_operation is not None:
        return {
            "ok": True,
            "status": "skipped",
            "returncode": 0,
            "summary": {"ok": 0, "warn": 0, "fail": 0, "line": ""},
            "fingerprint": "",
            "notified": False,
            "failures": 0,
            "warnings": 0,
            "deploy_operation_active": True,
            "deploy_operation": deploy_operation,
        }

    stdout = ""
    stderr = ""
    returncode = 0
    command_error = ""
    try:
        result = _run_health(cfg, timeout_seconds=timeout_seconds, strict=strict)
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        returncode = int(result.returncode)
    except subprocess.TimeoutExpired as exc:
        returncode = 124
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        command_error = f"health command timed out after {timeout_seconds}s"
    except Exception as exc:  # noqa: BLE001
        returncode = 1
        command_error = f"could not run health command: {exc}"

    summary = _summary_from_output(stdout)
    fail_lines = _health_lines(stdout, "fail")
    warn_lines = _health_lines(stdout, "warn")
    if command_error:
        fail_lines.append(command_error)
    if returncode != 0 and not fail_lines and int(summary.get("fail") or 0) <= 0:
        fail_lines.append(f"health command exited with status {returncode}")

    stderr_lines = ["stderr: " + line.strip() for line in stderr.splitlines() if line.strip()]
    if returncode != 0:
        fail_lines.extend(stderr_lines[:3])

    status = "ok"
    problem_lines: list[str] = []
    if int(summary.get("fail") or 0) > 0 or returncode != 0 or fail_lines:
        status = "fail"
        problem_lines = fail_lines
    elif notify_warnings and int(summary.get("warn") or 0) > 0:
        status = "warn"
        problem_lines = warn_lines

    fingerprint_payload = {
        "status": status,
        "returncode": returncode,
        "summary": summary,
        "problem_lines": problem_lines[:30],
    }
    fingerprint = "" if status == "ok" else _failure_fingerprint(fingerprint_payload)

    notified = False
    with connect_db(cfg) as conn:
        previous_status = get_setting(conn, STATUS_KEY, "ok")
        previous_fingerprint = get_setting(conn, FINGERPRINT_KEY, "")

        if status in {"fail", "warn"} and fingerprint != previous_fingerprint:
            target_id, channel_kind = _operator_target(cfg)
            queue_notification(
                conn,
                target_kind="operator",
                target_id=target_id,
                channel_kind=channel_kind,
                message=_format_problem_message(status, summary, fingerprint, problem_lines),
            )
            upsert_setting(conn, LAST_NOTIFIED_AT_KEY, utc_now_iso())
            notified = True
        elif status == "ok" and previous_status in {"fail", "warn"}:
            target_id, channel_kind = _operator_target(cfg)
            queue_notification(
                conn,
                target_kind="operator",
                target_id=target_id,
                channel_kind=channel_kind,
                message=_format_recovery_message(summary, previous_fingerprint),
            )
            upsert_setting(conn, LAST_NOTIFIED_AT_KEY, utc_now_iso())
            notified = True

        upsert_setting(conn, STATUS_KEY, status)
        upsert_setting(conn, FINGERPRINT_KEY, fingerprint)
        upsert_setting(conn, SUMMARY_KEY, str(summary.get("line") or ""))

    return {
        "ok": status == "ok",
        "status": status,
        "returncode": returncode,
        "summary": summary,
        "fingerprint": fingerprint,
        "notified": notified,
        "failures": len(fail_lines),
        "warnings": int(summary.get("warn") or 0),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ArcLink health and notify the operator on changed failures.")
    parser.add_argument("--timeout-seconds", type=int, default=int(os.environ.get("ARCLINK_HEALTH_WATCH_TIMEOUT_SECONDS", "300")))
    parser.add_argument("--strict", action="store_true", default=_bool_env("ARCLINK_HEALTH_WATCH_STRICT", False))
    parser.add_argument(
        "--notify-warnings",
        action="store_true",
        default=_bool_env("ARCLINK_HEALTH_WATCH_NOTIFY_WARNINGS", False),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = Config.from_env()
    summary = run_once(
        cfg,
        timeout_seconds=args.timeout_seconds,
        strict=bool(args.strict),
        notify_warnings=bool(args.notify_warnings),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
