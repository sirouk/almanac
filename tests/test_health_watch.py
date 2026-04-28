#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
CONTROL_PY = PYTHON_DIR / "almanac_control.py"
HEALTH_WATCH_PY = PYTHON_DIR / "almanac_health_watch.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_config(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"{key}={json.dumps(value)}" for key, value in values.items()) + "\n", encoding="utf-8")


def write_health_script(path: Path, *, body: str, exit_code: int) -> None:
    path.write_text(f"#!/usr/bin/env bash\ncat <<'EOF'\n{body.rstrip()}\nEOF\nexit {exit_code}\n", encoding="utf-8")
    path.chmod(0o755)


def config_values(root: Path) -> dict[str, str]:
    return {
        "ALMANAC_USER": "almanac",
        "ALMANAC_HOME": str(root / "home-almanac"),
        "ALMANAC_REPO_DIR": str(REPO),
        "ALMANAC_PRIV_DIR": str(root / "priv"),
        "STATE_DIR": str(root / "state"),
        "RUNTIME_DIR": str(root / "state" / "runtime"),
        "VAULT_DIR": str(root / "vault"),
        "ALMANAC_DB_PATH": str(root / "state" / "almanac-control.sqlite3"),
        "ALMANAC_AGENTS_STATE_DIR": str(root / "state" / "agents"),
        "ALMANAC_CURATOR_DIR": str(root / "state" / "curator"),
        "ALMANAC_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
        "ALMANAC_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
        "ALMANAC_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
        "ALMANAC_RELEASE_STATE_FILE": str(root / "state" / "almanac-release.json"),
        "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "telegram",
        "OPERATOR_NOTIFY_CHANNEL_ID": "1000000001",
        "ALMANAC_QMD_URL": "http://127.0.0.1:8181/mcp",
    }


def notification_messages(db_path: Path) -> list[str]:
    conn = sqlite3.connect(db_path)
    return [
        str(row[0])
        for row in conn.execute(
            "SELECT message FROM notification_outbox WHERE target_kind = 'operator' ORDER BY id"
        ).fetchall()
    ]


def test_health_watch_notifies_on_changed_failures_and_recovery() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_health_watch_test")
    health_watch = load_module(HEALTH_WATCH_PY, "almanac_health_watch_test")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        health_script = root / "fake-health.sh"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        os.environ["ALMANAC_HEALTH_WATCH_HEALTH_CMD"] = str(health_script)
        try:
            cfg = control.Config.from_env()
            write_health_script(
                health_script,
                body="[ok]   qmd active\n[fail] almanac-github-backup.service last result is exit-code\n\nSummary: 1 ok, 0 warn, 1 fail",
                exit_code=1,
            )
            first = health_watch.run_once(cfg, timeout_seconds=5)
            second = health_watch.run_once(cfg, timeout_seconds=5)
            messages = notification_messages(cfg.db_path)
            expect(first["status"] == "fail" and first["notified"] is True, str(first))
            expect(second["status"] == "fail" and second["notified"] is False, str(second))
            expect(len(messages) == 1, str(messages))
            expect("almanac-github-backup.service last result is exit-code" in messages[0], messages[0])

            write_health_script(
                health_script,
                body="[fail] qmd MCP backend port 8181 is not listening\n\nSummary: 0 ok, 0 warn, 1 fail",
                exit_code=1,
            )
            changed = health_watch.run_once(cfg, timeout_seconds=5)
            expect(changed["status"] == "fail" and changed["notified"] is True, str(changed))
            expect(len(notification_messages(cfg.db_path)) == 2, str(notification_messages(cfg.db_path)))

            write_health_script(
                health_script,
                body="[ok]   qmd MCP backend port 8181 only accepts loopback connections\n\nSummary: 1 ok, 0 warn, 0 fail",
                exit_code=0,
            )
            recovered = health_watch.run_once(cfg, timeout_seconds=5)
            messages = notification_messages(cfg.db_path)
            expect(recovered["status"] == "ok" and recovered["notified"] is True, str(recovered))
            expect(len(messages) == 3, str(messages))
            expect("Almanac health-watch recovered" in messages[-1], messages[-1])
            print("PASS test_health_watch_notifies_on_changed_failures_and_recovery")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_health_watch_notifies_on_changed_failures_and_recovery()
    print("PASS all 1 health watch regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
