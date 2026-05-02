#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_module(filename: str, name: str):
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    path = PYTHON_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def memory_db(control):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    return conn


def _rollback_plan():
    return {
        "actions": ["preserve_state_roots", "stop_rendered_services"],
        "state_roots": {"root": "/arcdata/deployments/dep_1", "vault": "/arcdata/deployments/dep_1/vault"},
    }


def test_create_rollout() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_create")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_create")
    conn = memory_db(control)
    r = rollout.create_rollout(
        conn,
        deployment_id="dep_1",
        version_tag="v1.2.0",
        waves=[{"hosts": ["h1"], "percentage": 50}, {"hosts": ["h2"], "percentage": 100}],
        rollback_plan=_rollback_plan(),
    )
    expect(r["status"] == "planned", "initial status is planned")
    expect(int(r["wave_count"]) == 2, "two waves")
    expect(int(r["current_wave"]) == 0, "no waves advanced yet")
    print("PASS test_create_rollout")


def test_advance_rollout_waves() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_advance")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_advance")
    conn = memory_db(control)
    r = rollout.create_rollout(
        conn, deployment_id="dep_1", version_tag="v1.0",
        waves=[{"hosts": ["h1"]}, {"hosts": ["h2"]}],
        rollback_plan=_rollback_plan(),
    )
    r = rollout.advance_rollout_wave(conn, rollout_id=r["rollout_id"])
    expect(r["status"] == "in_progress", "in progress after first wave")
    expect(int(r["current_wave"]) == 1, "wave 1")
    r = rollout.advance_rollout_wave(conn, rollout_id=r["rollout_id"])
    expect(r["status"] == "completed", "completed after all waves")
    expect(int(r["current_wave"]) == 2, "wave 2")
    print("PASS test_advance_rollout_waves")


def test_pause_rollout() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_pause")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_pause")
    conn = memory_db(control)
    r = rollout.create_rollout(
        conn, deployment_id="dep_1", version_tag="v1.0",
        waves=[{"hosts": ["h1"]}, {"hosts": ["h2"]}],
        rollback_plan=_rollback_plan(),
    )
    r = rollout.advance_rollout_wave(conn, rollout_id=r["rollout_id"])
    r = rollout.pause_rollout(conn, rollout_id=r["rollout_id"])
    expect(r["status"] == "paused", "paused")
    print("PASS test_pause_rollout")


def test_fail_rollout() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_fail")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_fail")
    conn = memory_db(control)
    r = rollout.create_rollout(
        conn, deployment_id="dep_1", version_tag="v1.0",
        waves=[{"hosts": ["h1"]}],
        rollback_plan=_rollback_plan(),
    )
    r = rollout.fail_rollout(conn, rollout_id=r["rollout_id"], reason="health check failed")
    expect(r["status"] == "failed", "failed")
    print("PASS test_fail_rollout")


def test_rollback_preserves_state_roots() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_rb")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_rb")
    conn = memory_db(control)
    r = rollout.create_rollout(
        conn, deployment_id="dep_1", version_tag="v1.0",
        waves=[{"hosts": ["h1"]}, {"hosts": ["h2"]}],
        rollback_plan=_rollback_plan(),
    )
    r = rollout.advance_rollout_wave(conn, rollout_id=r["rollout_id"])
    expect(r["status"] == "in_progress", "in progress after first wave")
    r = rollout.rollback_rollout(conn, rollout_id=r["rollout_id"], reason="regression found")
    expect(r["status"] == "rolled_back", "rolled back")
    # Verify events recorded
    events = conn.execute(
        "SELECT * FROM arclink_events WHERE event_type = 'rollout_rolled_back'",
    ).fetchall()
    expect(len(events) == 1, "rollback event recorded")
    print("PASS test_rollback_preserves_state_roots")


def test_rollback_plan_requires_preserve_state_roots() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_req")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_req")
    conn = memory_db(control)
    try:
        rollout.create_rollout(
            conn, deployment_id="dep_1", version_tag="v1.0",
            waves=[{"hosts": ["h1"]}],
            rollback_plan={"actions": ["stop_rendered_services"]},
        )
        raise AssertionError("should require preserve_state_roots")
    except rollout.ArcLinkRolloutError:
        pass
    print("PASS test_rollback_plan_requires_preserve_state_roots")


def test_version_drift() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_drift")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_drift")
    conn = memory_db(control)
    r = rollout.create_rollout(
        conn, deployment_id="dep_1", version_tag="v1.0",
        waves=[{"hosts": ["h1"]}],
        rollback_plan=_rollback_plan(),
    )
    rollout.advance_rollout_wave(conn, rollout_id=r["rollout_id"])
    rollout.create_rollout(
        conn, deployment_id="dep_1", version_tag="v2.0",
        waves=[{"hosts": ["h1"]}],
        rollback_plan=_rollback_plan(),
    )
    drift = rollout.rollout_version_drift(conn, deployment_id="dep_1")
    expect(drift["current_version"] == "v1.0", "current is v1.0")
    expect(drift["pending_version"] == "v2.0", "pending is v2.0")
    expect(drift["has_drift"] is True, "drift detected")
    print("PASS test_version_drift")


def test_list_rollouts() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_list")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_list")
    conn = memory_db(control)
    rollout.create_rollout(
        conn, deployment_id="dep_1", version_tag="v1.0",
        waves=[{"hosts": ["h1"]}], rollback_plan=_rollback_plan(),
    )
    rollout.create_rollout(
        conn, deployment_id="dep_2", version_tag="v2.0",
        waves=[{"hosts": ["h1"]}], rollback_plan=_rollback_plan(),
    )
    all_rollouts = rollout.list_rollouts(conn)
    expect(len(all_rollouts) == 2, "two rollouts")
    dep1_rollouts = rollout.list_rollouts(conn, deployment_id="dep_1")
    expect(len(dep1_rollouts) == 1, "one for dep_1")
    print("PASS test_list_rollouts")


def test_cannot_advance_completed() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_adv_done")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_adv_done")
    conn = memory_db(control)
    r = rollout.create_rollout(
        conn, deployment_id="dep_1", version_tag="v1.0",
        waves=[{"hosts": ["h1"]}], rollback_plan=_rollback_plan(),
    )
    rollout.advance_rollout_wave(conn, rollout_id=r["rollout_id"])
    try:
        rollout.advance_rollout_wave(conn, rollout_id=r["rollout_id"])
        raise AssertionError("should not advance completed rollout")
    except rollout.ArcLinkRolloutError:
        pass
    print("PASS test_cannot_advance_completed")


if __name__ == "__main__":
    test_create_rollout()
    test_advance_rollout_waves()
    test_pause_rollout()
    test_fail_rollout()
    test_rollback_preserves_state_roots()
    test_rollback_plan_requires_preserve_state_roots()
    test_version_drift()
    test_list_rollouts()
    test_cannot_advance_completed()
    print(f"\nAll 9 rollout tests passed.")
