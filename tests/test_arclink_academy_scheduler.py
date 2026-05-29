#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
CONTROL_PY = PYTHON_DIR / "arclink_control.py"
PROGRAMS_PY = PYTHON_DIR / "arclink_academy_programs.py"
SCHEDULER_PY = PYTHON_DIR / "arclink_academy_scheduler.py"


def load_module(path: Path, name: str):
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
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
    path.write_text("\n".join(f"{k}={json.dumps(v)}" for k, v in values.items()) + "\n", encoding="utf-8")


def config_values(root: Path) -> dict[str, str]:
    return {
        "ARCLINK_USER": "arclink",
        "ARCLINK_HOME": str(root / "home"),
        "ARCLINK_REPO_DIR": str(REPO),
        "ARCLINK_PRIV_DIR": str(root / "priv"),
        "STATE_DIR": str(root / "state"),
        "RUNTIME_DIR": str(root / "state" / "runtime"),
        "VAULT_DIR": str(root / "vault"),
        "ARCLINK_DB_PATH": str(root / "state" / "arclink-control.sqlite3"),
        "ARCLINK_AGENTS_STATE_DIR": str(root / "state" / "agents"),
        "ARCLINK_CURATOR_DIR": str(root / "state" / "curator"),
        "ARCLINK_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
        "ARCLINK_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
        "ARCLINK_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
        "ARCLINK_RELEASE_STATE_FILE": str(root / "state" / "arclink-release.json"),
        "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
        "ARCLINK_MCP_HOST": "127.0.0.1",
        "ARCLINK_MCP_PORT": "8282",
    }


def with_db():
    control = load_module(CONTROL_PY, "arclink_control_academy_sched_test")
    programs = load_module(PROGRAMS_PY, "arclink_academy_programs_sched_test")
    scheduler = load_module(SCHEDULER_PY, "arclink_academy_scheduler_test")
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    config_path = root / "config" / "arclink.env"
    write_config(config_path, config_values(root))
    old_env = os.environ.copy()
    os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
    try:
        cfg = control.Config.from_env()
        conn = control.connect_db(cfg)
        return tmp, old_env, conn, control, programs, scheduler
    except Exception:
        os.environ.clear()
        os.environ.update(old_env)
        tmp.cleanup()
        raise


def cleanup(tmp, old_env) -> None:
    os.environ.clear()
    os.environ.update(old_env)
    tmp.cleanup()


def _graduate(programs, conn, program_id, user_id, deployment_id):
    t = programs.enroll_academy_trainee(conn, program_id=program_id, user_id=user_id, deployment_id=deployment_id)
    s = programs.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by=user_id)
    programs.end_academy_mode(conn, session_id=s["session"]["session_id"], actor=user_id, graduate=True)
    return t


def test_forward_maintenance_reviews_graduates_without_writes() -> None:
    tmp, old_env, conn, _control, programs, scheduler = with_db()
    try:
        programs.seed_default_academy_programs(conn)
        # Two graduates + one still enrolled (should be skipped).
        _graduate(programs, conn, "systems_practice_engineer", "u1", "dep-1")
        _graduate(programs, conn, "research_analyst", "u2", "dep-2")
        programs.enroll_academy_trainee(conn, program_id="domain_tutor", user_id="u3", deployment_id="dep-3")

        before_intents = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]
        result = scheduler.run_academy_forward_maintenance(conn, env={})
        expect(result["status"] == "ok", str(result))
        expect(result["eligible"] == 2, f"only graduates are eligible, got {result['eligible']}")
        expect(result["processed"] == 2 and result["deferred_to_next_run"] == 0, str(result))
        expect(result["no_write"] is True and result["writes_enabled"] is False, str(result))
        for review in result["reviews"]:
            expect(review["manifest_id"], "each review references a staged manifest")
            expect("PG-PROVIDER" in review["proof_gates"] and "PG-HERMES" in review["proof_gates"], str(review))
        # No live action was queued.
        after_intents = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]
        expect(before_intents == after_intents, "forward maintenance must not queue actions")
        # Events + audits were recorded.
        events = [r["event_type"] for r in conn.execute("SELECT event_type FROM arclink_events").fetchall()]
        expect(events.count("academy_forward_maintenance_recorded") == 2, str(events))
        audits = [r["action"] for r in conn.execute("SELECT action FROM arclink_audit_log").fetchall()]
        expect(audits.count("academy_forward_maintenance_recorded") == 2, str(audits))
        print("PASS test_forward_maintenance_reviews_graduates_without_writes")
    finally:
        cleanup(tmp, old_env)


def test_forward_maintenance_caps_and_reports_overflow() -> None:
    tmp, old_env, conn, _control, programs, scheduler = with_db()
    try:
        programs.seed_default_academy_programs(conn)
        for i in range(3):
            _graduate(programs, conn, "research_analyst", f"u{i}", f"dep-{i}")
        result = scheduler.run_academy_forward_maintenance(conn, env={}, limit=2)
        expect(result["eligible"] == 3, str(result))
        expect(result["processed"] == 2, str(result))
        expect(result["deferred_to_next_run"] == 1, "overflow is reported, never silently dropped")
        print("PASS test_forward_maintenance_caps_and_reports_overflow")
    finally:
        cleanup(tmp, old_env)


if __name__ == "__main__":
    test_forward_maintenance_reviews_graduates_without_writes()
    test_forward_maintenance_caps_and_reports_overflow()
    print("PASS all academy scheduler tests")
