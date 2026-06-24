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
os.environ.setdefault("ARCLINK_SESSION_HASH_PEPPER", "raven-journey-harness-test-pepper")


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


def seed_ready_deployment(control, conn: sqlite3.Connection, *, channel: str = "telegram", channel_identity: str = "tg:journey") -> dict[str, str]:
    now = control.utc_now_iso()
    user_id = "arcusr_raven_journey"
    deployment_id = "arcdep_raven_journey"
    session_id = "onb_raven_journey"
    control.upsert_arclink_user(
        conn,
        user_id=user_id,
        email="journey@example.test",
        display_name="Journey Tester",
        entitlement_state="paid",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id=deployment_id,
        user_id=user_id,
        prefix="journey-atlas",
        base_domain="control.example.test",
        agent_name="Atlas",
        agent_title="Domain Tutor",
        status="active",
        metadata={"selected_plan_id": "sovereign"},
    )
    # Regression for a live journey failure: unrelated deployment metadata can
    # contain secret-adjacent hash/ref fields. Academy status persistence must
    # screen the new Academy payload without re-rejecting preserved metadata.
    row = conn.execute("SELECT metadata_json FROM arclink_deployments WHERE deployment_id = ?", (deployment_id,)).fetchone()
    metadata = json.loads(str(row["metadata_json"] or "{}")) if row is not None else {}
    metadata["share_request_broker"] = {
        "enabled": True,
        "token_hash": "sha256-placeholder-token-hash",
        "token_ref": "secret://share_request_broker/token",
        "updated_at": now,
    }
    conn.execute(
        "UPDATE arclink_deployments SET metadata_json = ? WHERE deployment_id = ?",
        (json.dumps(metadata, sort_keys=True), deployment_id),
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="arcdep_raven_journey_other",
        user_id=user_id,
        prefix="journey-forge",
        base_domain="control.example.test",
        agent_name="Forge",
        agent_title="Systems Builder",
        status="active",
        metadata={"selected_plan_id": "sovereign"},
    )
    conn.execute(
        """
        INSERT INTO arclink_onboarding_sessions (
          session_id, channel, channel_identity, status, current_step,
          email_hint, display_name_hint, selected_plan_id, selected_model_id,
          user_id, deployment_id, checkout_state, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, 'first_contacted', 'first_agent_contact', ?, ?, 'sovereign',
          'moonshotai/Kimi-K2.6-TEE', ?, ?, 'paid', '{}', ?, ?)
        """,
        (
            session_id,
            channel,
            channel_identity,
            "journey@example.test",
            "Journey Tester",
            user_id,
            deployment_id,
            now,
            now,
        ),
    )
    conn.commit()
    return {"user_id": user_id, "deployment_id": deployment_id, "session_id": session_id, "channel_identity": channel_identity}


def test_raven_journey_harness_replays_entry_academy_and_crew_paths() -> None:
    control = load_module("arclink_control.py", "arclink_control_raven_journey_harness")
    programs = load_module("arclink_academy_programs.py", "arclink_academy_programs_raven_journey_harness")
    harness = load_module("arclink_raven_journey_harness.py", "arclink_raven_journey_harness_test")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "control.sqlite3"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        control.ensure_schema(conn)
        seeded = seed_ready_deployment(control, conn)
        programs.seed_default_academy_programs(conn)
        conn.close()

        result = harness.run_harness(
            db_path=db_path,
            channel="telegram",
            deployment_id=seeded["deployment_id"],
            mode="all",
            open_academy_mode=False,
            confirm_crew=False,
        )
        open_result = harness.run_harness(
            db_path=db_path,
            channel="telegram",
            deployment_id=seeded["deployment_id"],
            mode="academy",
            open_academy_mode=True,
            validate_backend=True,
        )

    payload = result.to_dict()
    expect(result.ok, json.dumps(payload, indent=2))
    expect(result.copied_db is True, "harness must default to copied DB")
    by_name = {step.name: step for step in result.steps}
    expect(by_name["agents_menu"].checks["telegram_active_academy_raven"], str(by_name["agents_menu"]))
    expect(by_name["agents_menu"].checks["discord_active_academy_raven"], str(by_name["agents_menu"]))
    expect(by_name["academy_entry"].action == "academy_training_select_agent", str(by_name["academy_entry"]))
    expect(seeded["deployment_id"] in by_name["academy_select_agent"].sent, str(by_name["academy_select_agent"]))
    expect(by_name["academy_choose_major"].action == "academy_training_focus", str(by_name["academy_choose_major"]))
    expect(by_name["academy_boundaries"].action == "academy_training_charter_preview", str(by_name["academy_boundaries"]))
    expect(by_name["crew_entry"].action == "crew_training_prompt_role", str(by_name["crew_entry"]))
    expect(by_name["crew_capacity"].action == "crew_training_review", str(by_name["crew_capacity"]))
    expect(open_result.ok, json.dumps(open_result.to_dict(), indent=2))
    open_by_name = {step.name: step for step in open_result.steps}
    expect(open_by_name["academy_open_mode"].action == "academy_mode_opened", str(open_by_name["academy_open_mode"]))
    expect(open_result.backend["graduated"] is True, str(open_result.backend))
    expect(open_result.backend["synthesis_authored"] is True, str(open_result.backend))
    expect(open_result.backend["exam_passed"] is True, str(open_result.backend))
    expect(open_result.backend["graduation_state"] == "graduated", str(open_result.backend))
    expect(open_result.backend["apply_status"] == "handoff_to_hermes_home", str(open_result.backend))
    expect(open_result.backend["apply_writes_enabled"] is True, str(open_result.backend))
    print("PASS test_raven_journey_harness_replays_entry_academy_and_crew_paths")


if __name__ == "__main__":
    test_raven_journey_harness_replays_entry_academy_and_crew_paths()
