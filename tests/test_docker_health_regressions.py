#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import shlex
import sqlite3
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def extract(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def test_docker_health_allows_stale_on_demand_operator_actions() -> None:
    body = (REPO / "bin/docker-health.sh").read_text(encoding="utf-8")
    snippet = extract(body, "check_docker_refresh_jobs() {", "\ncheck_docker_refresh_jobs\n")
    snippet += "\ncheck_docker_refresh_jobs\n"
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "control.sqlite3"
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=12)).isoformat(timespec="seconds")
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE refresh_jobs (
              job_name TEXT PRIMARY KEY,
              job_kind TEXT NOT NULL,
              target_id TEXT NOT NULL,
              schedule TEXT,
              last_run_at TEXT,
              last_status TEXT,
              last_note TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO refresh_jobs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "operator-upgrade",
                "operator-action",
                "upgrade",
                "on demand via operator buttons",
                old,
                "ok",
                "last queued upgrade completed",
            ),
        )
        conn.execute(
            "INSERT INTO refresh_jobs VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("curator-refresh", "curator", "curator", "every 1h", old, "ok", "old recurring refresh"),
        )
        conn.commit()
        conn.close()

        script = f"""
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
pass() {{ printf 'PASS:%s\\n' "$1"; }}
warn() {{ printf 'WARN:%s\\n' "$1"; }}
fail() {{ printf 'FAIL:%s\\n' "$1"; }}
SCRIPT_DIR={shlex.quote(str(REPO / "bin"))}
ARCLINK_DB_PATH={shlex.quote(str(db_path))}
PYTHONPATH={shlex.quote(str(PYTHON_DIR))}
export SCRIPT_DIR ARCLINK_DB_PATH PYTHONPATH
{snippet}
"""
        result = subprocess.run(["bash", "-lc", script], cwd=REPO, text=True, capture_output=True, check=False, timeout=30)
    expect(
        result.returncode == 0,
        f"docker health refresh job probe failed: stdout={result.stdout!r} stderr={result.stderr!r}",
    )
    expect("PASS:operator-upgrade: ok (on demand; last run" in result.stdout, result.stdout)
    expect("WARN:operator-upgrade: stale" not in result.stdout, result.stdout)
    expect("WARN:curator-refresh: stale" in result.stdout, result.stdout)
    print("PASS test_docker_health_allows_stale_on_demand_operator_actions")


def main() -> int:
    test_docker_health_allows_stale_on_demand_operator_actions()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
