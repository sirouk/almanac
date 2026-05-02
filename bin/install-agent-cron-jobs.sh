#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: install-agent-cron-jobs.sh <repo-dir> <hermes-home>

Install ArcLink-managed Hermes cron jobs for an enrolled user's Hermes home.
The jobs are stored in the agent's native Hermes cron/jobs.json file and are
ticked by the Hermes gateway.
EOF
}

if [[ $# -lt 2 ]]; then
  usage
  exit 2
fi

REPO_DIR="$1"
HERMES_HOME="$2"

python3 - "$REPO_DIR" "$HERMES_HOME" <<'PY'
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import tempfile
from pathlib import Path

repo_dir = Path(sys.argv[1]).expanduser()
hermes_home = Path(sys.argv[2]).expanduser()
if repo_dir.exists():
    repo_dir = repo_dir.resolve()
else:
    repo_dir = repo_dir.absolute()
hermes_home = hermes_home.resolve()

MANAGED_JOB_ID = "a1bac0ffee42"
MANAGED_BY = "arclink"
MANAGED_KIND = "agent-home-backup"
SCRIPT_NAME = "arclink_agent_backup.py"
SCHEDULE_MINUTES = 240

SCRIPT_TEMPLATE = r'''#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    import fcntl
except Exception:  # pragma: no cover - non-Unix fallback
    fcntl = None

ARCLINK_REPO_DIR = Path(__ARCLINK_REPO_DIR__)
DEFAULT_HERMES_HOME = Path(__HERMES_HOME__)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def resolve_hermes_home() -> Path:
    value = os.environ.get("HERMES_HOME", "").strip()
    if value:
        return Path(value).expanduser().resolve()
    return DEFAULT_HERMES_HOME.resolve()


def last_nonempty_line(text: str, limit: int = 500) -> str:
    for raw in reversed((text or "").splitlines()):
        line = raw.strip()
        if line:
            return line[:limit]
    return ""


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".last-run-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def append_log(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(content)
        if not content.endswith("\n"):
            handle.write("\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def write_status(hermes_home: Path, payload: dict) -> None:
    status_path = hermes_home / "state" / "agent-home-backup" / "last-run.json"
    atomic_write_json(status_path, payload)


def print_gate(payload: dict, *, wake_agent: bool = False) -> None:
    payload = dict(payload)
    payload["wakeAgent"] = bool(wake_agent)
    print(json.dumps(payload, sort_keys=True))


def acquire_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("w", encoding="utf-8")
    if fcntl is None:
        return handle
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def main() -> int:
    hermes_home = resolve_hermes_home()
    backup_state = hermes_home / "state" / "arclink-agent-backup.env"
    status_base = {
        "ran_at": now_iso(),
        "hermes_home": str(hermes_home),
        "scheduler": "hermes-cron",
    }

    if not backup_state.is_file():
        payload = {
            **status_base,
            "ok": True,
            "status": "inactive",
            "summary": "ArcLink agent backup is not configured.",
        }
        write_status(hermes_home, payload)
        print_gate({"status": "inactive"})
        return 0

    backup_script = ARCLINK_REPO_DIR / "bin" / "backup-agent-home.sh"
    if not backup_script.is_file():
        payload = {
            **status_base,
            "ok": False,
            "status": "error",
            "summary": f"Backup script is missing at {backup_script}",
        }
        write_status(hermes_home, payload)
        print_gate({"status": "error", "summary": payload["summary"]}, wake_agent=True)
        return 1

    lock_handle = acquire_lock(hermes_home / "state" / "agent-home-backup" / ".backup.lock")
    if lock_handle is None:
        payload = {
            **status_base,
            "ok": True,
            "status": "busy",
            "summary": "Another ArcLink agent backup run is already active.",
        }
        write_status(hermes_home, payload)
        print_gate({"status": "busy"})
        return 0

    started = time.monotonic()
    started_at = status_base["ran_at"]
    env = os.environ.copy()
    env["HERMES_HOME"] = str(hermes_home)
    proc = subprocess.run(
        [str(backup_script), str(hermes_home)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    duration = round(time.monotonic() - started, 3)
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    ok = proc.returncode == 0
    summary = (
        last_nonempty_line(stdout if ok else stderr)
        or last_nonempty_line(stdout)
        or ("backup completed" if ok else "backup failed")
    )

    log_path = hermes_home / "logs" / "arclink-agent-backup.log"
    append_log(
        log_path,
        "\n".join(
            [
                "",
                f"=== {started_at} rc={proc.returncode} duration={duration}s ===",
                f"command: {backup_script} {hermes_home}",
                "--- stdout ---",
                stdout.rstrip(),
                "--- stderr ---",
                stderr.rstrip(),
            ]
        ),
    )
    payload = {
        **status_base,
        "ok": ok,
        "status": "ok" if ok else "error",
        "returncode": proc.returncode,
        "duration_seconds": duration,
        "summary": summary,
        "log_path": str(log_path),
    }
    write_status(hermes_home, payload)
    print_gate(
        {
            "status": payload["status"],
            "returncode": proc.returncode,
            "duration_seconds": duration,
            "summary": summary,
        },
        wake_agent=not ok,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
'''


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def next_run_iso() -> str:
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=SCHEDULE_MINUTES)).isoformat()


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".jobs-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def load_jobs(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    jobs = data.get("jobs", [])
    if not isinstance(jobs, list):
        raise ValueError(f"Invalid Hermes cron jobs file at {path}: jobs is not a list")
    return [job for job in jobs if isinstance(job, dict)]


def is_managed_backup_job(job: dict) -> bool:
    if job.get("id") == MANAGED_JOB_ID:
        return True
    return job.get("managed_by") == MANAGED_BY and job.get("managed_kind") == MANAGED_KIND


def build_job(existing: dict | None, active: bool) -> dict:
    existing = existing or {}
    now = now_iso()
    schedule = {"kind": "interval", "minutes": SCHEDULE_MINUTES, "display": f"every {SCHEDULE_MINUTES}m"}
    existing_schedule = existing.get("schedule") if isinstance(existing.get("schedule"), dict) else {}
    schedule_changed = existing_schedule != schedule
    next_run = existing.get("next_run_at")
    if not active:
        next_run = next_run or next_run_iso()
    elif schedule_changed or not next_run or existing.get("state") == "paused":
        next_run = next_run_iso()

    return {
        "id": MANAGED_JOB_ID,
        "name": "ArcLink private Hermes-home backup",
        "prompt": (
            "Run the ArcLink private Hermes-home backup check. The pre-run script "
            "performs the backup itself and suppresses the agent turn on success. "
            "If the pre-run script reports an error, briefly tell the user what "
            "failed and suggest contacting the operator if it persists."
        ),
        "skills": [],
        "skill": None,
        "model": None,
        "provider": None,
        "base_url": None,
        "script": SCRIPT_NAME,
        "context_from": None,
        "schedule": schedule,
        "schedule_display": schedule["display"],
        "repeat": existing.get("repeat") if isinstance(existing.get("repeat"), dict) else {"times": None, "completed": 0},
        "enabled": bool(active),
        "state": "scheduled" if active else "paused",
        "paused_at": None if active else existing.get("paused_at") or now,
        "paused_reason": None if active else "ArcLink agent backup is not configured",
        "created_at": existing.get("created_at") or now,
        "next_run_at": next_run,
        "last_run_at": existing.get("last_run_at"),
        "last_status": existing.get("last_status"),
        "last_error": existing.get("last_error"),
        "last_delivery_error": existing.get("last_delivery_error"),
        "deliver": "origin",
        "origin": None,
        "enabled_toolsets": [],
        "workdir": None,
        "managed_by": MANAGED_BY,
        "managed_kind": MANAGED_KIND,
    }


def install_backup_script() -> Path:
    scripts_dir = hermes_home / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    script_path = scripts_dir / SCRIPT_NAME
    body = (
        SCRIPT_TEMPLATE
        .replace("__ARCLINK_REPO_DIR__", json.dumps(str(repo_dir)))
        .replace("__HERMES_HOME__", json.dumps(str(hermes_home)))
    )
    script_path.write_text(body, encoding="utf-8")
    try:
        os.chmod(scripts_dir, 0o700)
        os.chmod(script_path, 0o700)
    except OSError:
        pass
    return script_path


def ensure_cron_config() -> None:
    config_path = hermes_home / "config.yaml"
    lines = config_path.read_text(encoding="utf-8").splitlines() if config_path.is_file() else []

    def is_top_level_key(line: str) -> bool:
        return bool(re.match(r"^[A-Za-z0-9_][A-Za-z0-9_-]*\s*:", line))

    start = None
    for index, line in enumerate(lines):
        if re.match(r"^cron\s*:\s*(?:#.*)?$", line):
            start = index
            break

    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(["cron:", "  script_timeout_seconds: 1800"])
    else:
        end = len(lines)
        for index in range(start + 1, len(lines)):
            if lines[index].strip() and is_top_level_key(lines[index]):
                end = index
                break
        replaced = False
        for index in range(start + 1, end):
            if re.match(r"^\s+script_timeout_seconds\s*:", lines[index]):
                lines[index] = "  script_timeout_seconds: 1800"
                replaced = True
                break
        if not replaced:
            lines.insert(start + 1, "  script_timeout_seconds: 1800")

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    try:
        os.chmod(config_path, 0o600)
    except OSError:
        pass


def upsert_backup_job() -> str:
    active = (hermes_home / "state" / "arclink-agent-backup.env").is_file()
    cron_dir = hermes_home / "cron"
    jobs_path = cron_dir / "jobs.json"
    cron_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(cron_dir, 0o700)
    except OSError:
        pass

    jobs = load_jobs(jobs_path)
    existing = None
    retained: list[dict] = []
    for job in jobs:
        if is_managed_backup_job(job):
            if existing is None:
                existing = job
            continue
        retained.append(job)

    if not active and existing is None:
        if len(retained) != len(jobs):
            atomic_write_json(jobs_path, {"jobs": retained, "updated_at": now_iso()})
        return "inactive"

    retained.append(build_job(existing, active))
    atomic_write_json(jobs_path, {"jobs": retained, "updated_at": now_iso()})
    return "active" if active else "paused"


script_path = install_backup_script()
ensure_cron_config()
status = upsert_backup_job()
print(
    json.dumps(
        {
            "status": status,
            "job_id": MANAGED_JOB_ID if status != "inactive" else None,
            "script": str(script_path),
        },
        sort_keys=True,
    )
)
PY
