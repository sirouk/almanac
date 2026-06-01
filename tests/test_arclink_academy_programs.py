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
    control = load_module(CONTROL_PY, "arclink_control_academy_programs_test")
    programs = load_module(PROGRAMS_PY, "arclink_academy_programs_test")
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    config_path = root / "config" / "arclink.env"
    write_config(config_path, config_values(root))
    old_env = os.environ.copy()
    os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
    try:
        cfg = control.Config.from_env()
        conn = control.connect_db(cfg)
        return tmp, old_env, conn, control, programs
    except Exception:
        os.environ.clear()
        os.environ.update(old_env)
        tmp.cleanup()
        raise


def cleanup(tmp, old_env) -> None:
    os.environ.clear()
    os.environ.update(old_env)
    tmp.cleanup()


def test_academy_catalog_seed_is_idempotent_and_browsable() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        expect(ap.list_academy_programs(conn) == [], "catalog empty before seed")
        n1 = ap.seed_default_academy_programs(conn)
        n2 = ap.seed_default_academy_programs(conn)
        expect(n1 == n2 and n1 >= 5, f"seed idempotent + >=5 majors, got {n1}/{n2}")
        majors = ap.list_academy_programs(conn)
        expect(len(majors) == n1, "no duplicate majors after re-seed")
        labels = {m["label"] for m in majors}
        expect("Systems-Practice Engineer" in labels and "Research Analyst" in labels, str(labels))
        # every Major references only known governed source lanes
        from arclink_academy_trainer import default_source_lane_registry
        known = set(default_source_lane_registry().keys())
        for m in majors:
            expect(m["source_lanes"] and set(m["source_lanes"]).issubset(known), str(m))
        print("PASS test_academy_catalog_seed_is_idempotent_and_browsable")
    finally:
        cleanup(tmp, old_env)


def test_academy_enroll_open_sticky_and_graduate() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        trainee = ap.enroll_academy_trainee(
            conn, program_id="research_analyst", user_id="user-1",
            deployment_id="dep-1", name="Ada", captain_steer={"focus": "evals"},
        )
        expect(trainee["status"] == "enrolled" and trainee["program_id"] == "research_analyst", str(trainee))
        expect(trainee["depth"] == "deep", "depth defaults from the Major")

        opened = ap.open_academy_mode(conn, trainee_id=trainee["trainee_id"], opened_by="tg:42", opened_via="command")
        expect(opened["created"] is True and opened["session"]["status"] == "open", str(opened))
        expect(opened["trainee"]["status"] == "in_academy" and opened["trainee"]["mode_open"] is True, str(opened["trainee"]))

        # Sticky: re-opening returns the SAME open session, not a new one.
        reopened = ap.open_academy_mode(conn, trainee_id=trainee["trainee_id"], opened_by="tg:42")
        expect(reopened["created"] is False, "mode is sticky; re-open returns existing session")
        expect(reopened["session"]["session_id"] == opened["session"]["session_id"], "same session id")

        status = ap.academy_mode_status(conn, trainee_id=trainee["trainee_id"])
        expect(status["mode_open"] is True and status["session"] is not None, str(status))
        expect(status["program"]["label"] == "Research Analyst", str(status["program"]))

        # The mode does not end on its own; the Captain ends it -> graduate + commit + forward-maintain.
        ended = ap.end_academy_mode(conn, session_id=opened["session"]["session_id"], actor="tg:42", graduate=True)
        expect(ended["graduated"] is True, str(ended))
        expect(ended["mutation_performed"] is False and ended["workspace_mutation_performed"] is False, "no live writes at control plane")
        expect(ended["trainee"]["status"] == "graduated" and ended["trainee"]["mode_open"] is False, str(ended["trainee"]))
        expect(ended["trainee"]["forward_maintained"] is True, "forward-maintenance armed on graduation")
        cs = ended["session"]["commit_summary"]
        expect("PG-HERMES" in cs.get("apply_proof_gates", []), str(cs))
        expect(cs["trainer_deep_dive_status"] == "queued_for_review", str(cs))
        expect(cs["canon_status"] == "not_canon_until_trainer_deep_dive_and_apply", str(cs))
        expect(ended["session"]["status"] == "closed", str(ended["session"]))
        print("PASS test_academy_enroll_open_sticky_and_graduate")
    finally:
        cleanup(tmp, old_env)


def test_academy_mode_records_steer_and_resource_proposals() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        trainee = ap.enroll_academy_trainee(
            conn,
            program_id="research_analyst",
            user_id="user-1",
            deployment_id="dep-1",
            captain_steer={"focus": "routing research"},
        )
        opened = ap.open_academy_mode(conn, trainee_id=trainee["trainee_id"], opened_by="captain")
        updated = ap.update_academy_trainee_steer(
            conn,
            trainee_id=trainee["trainee_id"],
            updates={"weekly_review": True},
            append_note="Track source freshness every week.",
            actor="captain",
        )
        expect(updated["captain_steer"]["weekly_review"] == "True", str(updated))
        expect(updated["captain_steer"]["captain_notes"], str(updated))

        proposal = ap.record_academy_resource_proposal(
            conn,
            deployment_id="dep-1",
            lane_id="web_article",
            title="Routing architecture field note",
            origin_url="https://example.test/routing",
            summary="Compressed routing architecture notes for Trainer review.",
            relevance={"role_fit": "supports research analyst training", "weekly_refresh": "check for revisions"},
            citations=["https://example.test/routing"],
            proposed_by="agent-1",
        )
        expect(proposal["status"] == "review_pending", str(proposal))
        expect(proposal["trainee_id"] == trainee["trainee_id"], str(proposal))
        deduped = ap.record_academy_resource_proposal(
            conn,
            deployment_id="dep-1",
            lane_id="web_article",
            title="Routing architecture field note revised",
            origin_url="https://example.test/routing",
            summary="Updated compressed notes.",
            proposed_by="agent-1",
        )
        expect(deduped["proposal_id"] == proposal["proposal_id"], str(deduped))
        expect(deduped["status"] == "deduped", str(deduped))
        offline = ap.record_academy_resource_proposal(
            conn,
            deployment_id="dep-1",
            lane_id="organization_private",
            title="Captain offline source bundle",
            origin_url="",
            summary="Captain-approved offline reference notes, compressed for Trainer review.",
            proposed_by="agent-1",
        )
        offline_deduped = ap.record_academy_resource_proposal(
            conn,
            deployment_id="dep-1",
            lane_id="organization_private",
            title="Captain offline source bundle",
            origin_url="",
            summary="Revised offline source notes.",
            proposed_by="agent-1",
        )
        expect(offline_deduped["proposal_id"] == offline["proposal_id"], str(offline_deduped))
        expect(offline_deduped["status"] == "deduped", str(offline_deduped))
        missing_lane_rejected = False
        try:
            ap.record_academy_resource_proposal(
                conn,
                deployment_id="dep-1",
                lane_id="",
                title="Lane-free source",
                origin_url="https://example.test/lane-free",
                summary="Should fail closed without a governed lane.",
                proposed_by="agent-1",
            )
        except ap.ArcLinkAcademyProgramError:
            missing_lane_rejected = True
        expect(missing_lane_rejected, "resource proposals must name a governed source lane")

        ended = ap.end_academy_mode(conn, session_id=opened["session"]["session_id"], actor="captain", graduate=True)
        cs = ended["session"]["commit_summary"]
        expect(cs["resource_proposal_count"] == 2, str(cs))
        expect(cs["trainer_deep_dive_status"] == "queued_for_review", str(cs))
        closed_steer_rejected = False
        try:
            ap.update_academy_trainee_steer(conn, trainee_id=trainee["trainee_id"], append_note="too late")
        except ap.ArcLinkAcademyProgramError:
            closed_steer_rejected = True
        expect(closed_steer_rejected, "Captain steering updates require open Academy Mode")
        print("PASS test_academy_mode_records_steer_and_resource_proposals")
    finally:
        cleanup(tmp, old_env)


def test_academy_cancel_mode_returns_to_enrolled() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        trainee = ap.enroll_academy_trainee(conn, program_id="domain_tutor", user_id="u", deployment_id="d")
        opened = ap.open_academy_mode(conn, trainee_id=trainee["trainee_id"], opened_by="captain")
        ended = ap.end_academy_mode(conn, session_id=opened["session"]["session_id"], actor="captain", graduate=False)
        expect(ended["graduated"] is False, str(ended))
        expect(ended["trainee"]["status"] == "enrolled" and ended["trainee"]["mode_open"] is False, str(ended["trainee"]))
        expect(ended["session"]["status"] == "cancelled", str(ended["session"]))
        print("PASS test_academy_cancel_mode_returns_to_enrolled")
    finally:
        cleanup(tmp, old_env)


def test_academy_browse_graduates_and_adopt() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="systems_practice_engineer", user_id="u1", deployment_id="dep-a", name="Grace")
        s = ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="u1")
        ap.end_academy_mode(conn, session_id=s["session"]["session_id"], actor="u1", graduate=True, staged_manifest_id="mani-xyz")

        gallery = ap.browse_academy_graduates(conn)
        expect(any(g["trainee_id"] == t["trainee_id"] for g in gallery["graduates"]), "graduate appears in gallery")
        grad = next(g for g in gallery["graduates"] if g["trainee_id"] == t["trainee_id"])
        expect(grad["program_label"] == "Systems-Practice Engineer" and grad["source_lanes"], str(grad))
        expect(len(gallery["programs"]) >= 5, "gallery includes the Major catalog")

        adopted = ap.adopt_academy_graduate(conn, source_trainee_id=t["trainee_id"], user_id="u1", deployment_id="dep-b", name="Grace II")
        expect(adopted["status"] == "graduated" and adopted["adopted_from_trainee_id"] == t["trainee_id"], str(adopted))
        expect(adopted["program_id"] == "systems_practice_engineer" and adopted["staged_manifest_id"] == "mani-xyz", str(adopted))
        expect(adopted["forward_maintained"] is True, "adopted graduate is forward-maintained")
        print("PASS test_academy_browse_graduates_and_adopt")
    finally:
        cleanup(tmp, old_env)


def test_academy_many_types_as_data_and_lane_validation() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        before = len(ap.list_academy_programs(conn))
        # A brand-new trainee TYPE is added as data (a row), not code.
        ap.upsert_academy_program(
            conn, program_id="incident_commander", label="Incident Commander",
            summary="Runs incident response", topic_map="incidents, runbooks, postmortems",
            source_lanes=["github_repository", "web_article"], role_template="You command incidents.",
            default_depth="working",
        )
        after = ap.list_academy_programs(conn)
        expect(len(after) == before + 1, "custom Major added as data")
        expect(any(m["program_id"] == "incident_commander" for m in after), "custom Major browsable")

        # Unknown source lane is rejected (governed registry).
        raised = False
        try:
            ap.upsert_academy_program(conn, program_id="bad", label="Bad", source_lanes=["not_a_real_lane"])
        except ap.ArcLinkAcademyProgramError:
            raised = True
        expect(raised, "unknown source lane must be rejected")
        print("PASS test_academy_many_types_as_data_and_lane_validation")
    finally:
        cleanup(tmp, old_env)


def test_academy_rejects_secret_material_and_unknown_program() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        unknown = False
        try:
            ap.enroll_academy_trainee(conn, program_id="does_not_exist", user_id="u", deployment_id="d")
        except ap.ArcLinkAcademyProgramError:
            unknown = True
        expect(unknown, "enrolling into an unknown Major must fail")

        secretish = False
        try:
            ap.enroll_academy_trainee(
                conn, program_id="domain_tutor", user_id="u", deployment_id="d",
                captain_steer={"note": "api_key=sk-livesecretvalue1234567890"},
            )
        except Exception:
            secretish = True
        expect(secretish, "secret-looking steer must be rejected")
        print("PASS test_academy_rejects_secret_material_and_unknown_program")
    finally:
        cleanup(tmp, old_env)


def test_academy_curation_builds_corpus_plan_and_stages() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="systems_practice_engineer", user_id="u", deployment_id="dep-c")
        result = ap.curate_academy_trainee(conn, trainee_id=t["trainee_id"])
        expect(result["manifest_id"], "curation produces a manifest id")
        expect(result["source_count"] == 3, f"systems-practice major has 3 lanes, got {result['source_count']}")
        expect(result["mutation_performed"] is False and result["workspace_mutation_performed"] is False, "no Agent writes")
        review = result["review"]
        expect(review.get("status") in {"ready_for_review", "live_proof_pending"}, str(review))
        refreshed = ap.get_academy_trainee(conn, t["trainee_id"])
        expect(refreshed["staged_manifest_id"] == result["manifest_id"], "manifest staged on trainee")
        print("PASS test_academy_curation_builds_corpus_plan_and_stages")
    finally:
        cleanup(tmp, old_env)


def test_academy_commit_curates_on_graduation() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="research_analyst", user_id="u", deployment_id="dep-d")
        s = ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="u")
        ended = ap.end_academy_mode(conn, session_id=s["session"]["session_id"], actor="u", graduate=True)
        grad = ended["trainee"]
        expect(grad["status"] == "graduated", str(grad))
        expect(grad["staged_manifest_id"], "graduation curated + staged a manifest")
        cs = ended["session"]["commit_summary"]
        expect(cs.get("manifest_id") == grad["staged_manifest_id"], str(cs))
        expect(cs.get("review_status") in {"ready_for_review", "live_proof_pending"}, str(cs))
        expect("PG-HERMES" in cs.get("apply_proof_gates", []), str(cs))
        expect(ended["mutation_performed"] is False, "no live Agent writes at commit")
        print("PASS test_academy_commit_curates_on_graduation")
    finally:
        cleanup(tmp, old_env)


def test_academy_continuing_education_is_no_write() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="domain_tutor", user_id="u", deployment_id="dep-e")
        ce = ap.academy_continuing_education(conn, trainee_id=t["trainee_id"], observed_sources=[])
        expect("agent_update_status" in ce, str(ce.keys()))
        expect(ce["mutation_performed"] is False, "continuing education is no-write")
        expect(ce["trainee_id"] == t["trainee_id"], str(ce))
        print("PASS test_academy_continuing_education_is_no_write")
    finally:
        cleanup(tmp, old_env)


def _graduate(ap, conn, program_id, user_id, deployment_id):
    t = ap.enroll_academy_trainee(conn, program_id=program_id, user_id=user_id, deployment_id=deployment_id)
    s = ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by=user_id)
    program = ap.get_academy_program(conn, program_id) or {}
    lane = next((item for item in (program.get("source_lanes") or []) if item != "organization_private"), "web_article")
    ap.record_academy_resource_proposal(
        conn,
        deployment_id=deployment_id,
        lane_id=lane,
        title=f"{program_id} trainer-reviewed source for {deployment_id}",
        origin_url=f"https://example.test/academy/{program_id}/{deployment_id}",
        summary="Compressed public-lane source notes for the Trainer-reviewed Academy capsule.",
        proposed_by="test-agent",
    )
    ap.end_academy_mode(conn, session_id=s["session"]["session_id"], actor=user_id, graduate=True)
    return t


def test_academy_apply_is_fail_closed() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = _graduate(ap, conn, "systems_practice_engineer", "u", "dep-apply")

        # Record-only adapter -> staged, no writes.
        staged = ap.stage_academy_apply(conn, trainee_id=t["trainee_id"], adapter_name="fake")
        expect(staged["status"] == "staged", str(staged))
        expect(staged["writes_enabled"] is False, "fake adapter never writes")
        expect(staged["operation_kind"] == "academy_agent_apply", str(staged))
        expect(staged["intent_counts"]["soul_overlay_sections"] >= 0, str(staged["intent_counts"]))
        expect("PG-HERMES" in staged["proof_gates"], str(staged))

        # Live adapter without PG-HERMES authorization -> failed_closed, no writes.
        closed = ap.stage_academy_apply(conn, trainee_id=t["trainee_id"], adapter_name="ssh", live_authorized=False)
        expect(closed["status"] == "failed_closed", str(closed))
        expect(closed["writes_enabled"] is False, "live adapter without authorization never writes")

        # Live adapter WITH authorization -> handoff to the PG-HERMES Hermes-home seam.
        authd = ap.stage_academy_apply(conn, trainee_id=t["trainee_id"], adapter_name="ssh", live_authorized=True)
        expect(authd["status"] == "handoff_to_hermes_home", str(authd))
        expect(authd["writes_enabled"] is True, "authorized live apply hands off to the imparting seam")
        expect(authd["academy_trainer_review_ready"] is True, str(authd))
        expect(authd["mutation_performed"] is False, "control plane itself performs no filesystem write")
        print("PASS test_academy_apply_is_fail_closed")
    finally:
        cleanup(tmp, old_env)


def test_academy_apply_requires_graduated_trainee() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="research_analyst", user_id="u", deployment_id="dep-ng")
        raised = False
        try:
            ap.stage_academy_apply(conn, trainee_id=t["trainee_id"], adapter_name="fake")
        except ap.ArcLinkAcademyProgramError:
            raised = True
        expect(raised, "apply must reject a non-graduated trainee")
        print("PASS test_academy_apply_requires_graduated_trainee")
    finally:
        cleanup(tmp, old_env)


def test_academy_apply_validates_staged_contract_and_fails_closed_on_major_drift() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = _graduate(ap, conn, "research_analyst", "u", "dep-drift")
        staged = ap.get_academy_trainee(conn, t["trainee_id"])

        # Fresh graduate: recomputed contract matches the Captain-approved staged ids.
        fresh = ap.stage_academy_apply(conn, trainee_id=t["trainee_id"], adapter_name="ssh", live_authorized=True)
        expect(fresh["contract_fresh"] is True, str(fresh))
        expect(fresh["manifest_id"] == staged["staged_manifest_id"], "apply reports the approved staged manifest")
        expect(fresh["status"] == "handoff_to_hermes_home" and fresh["writes_enabled"] is True, str(fresh))

        # Edit the Major after graduation -> recomputed corpus diverges from the
        # reviewed staged contract -> apply MUST fail closed (no unreviewed write).
        ap.upsert_academy_program(
            conn, program_id="research_analyst", label="Research Analyst",
            topic_map="ENTIRELY DIFFERENT TOPIC after graduation",
            source_lanes=["wikimedia", "web_article"], role_template="changed",
        )
        stale = ap.stage_academy_apply(conn, trainee_id=t["trainee_id"], adapter_name="ssh", live_authorized=True)
        expect(stale["status"] == "stale_requires_regraduation", str(stale))
        expect(stale["writes_enabled"] is False, "a Major edited post-graduation must NOT enable writes")
        expect(stale["manifest_id"] == staged["staged_manifest_id"], "still reports the approved staged manifest, not the drifted one")
        print("PASS test_academy_apply_validates_staged_contract_and_fails_closed_on_major_drift")
    finally:
        cleanup(tmp, old_env)


def test_academy_apply_rejects_target_owner_mismatch() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = _graduate(ap, conn, "research_analyst", "owner-a", "dep-a")
        # target deployment that is not the trainee's deployment -> hard fail
        raised = False
        try:
            ap.stage_academy_apply(conn, trainee_id=t["trainee_id"], adapter_name="fake", target_kind="deployment", target_id="dep-SOMEONE-ELSE")
        except ap.ArcLinkAcademyProgramError:
            raised = True
        expect(raised, "apply must reject a target deployment that isn't the trainee's")
        # matching target is accepted
        ok = ap.stage_academy_apply(conn, trainee_id=t["trainee_id"], adapter_name="fake", target_kind="deployment", target_id="dep-a")
        expect(ok["status"] == "staged", str(ok))
        print("PASS test_academy_apply_rejects_target_owner_mismatch")
    finally:
        cleanup(tmp, old_env)


def test_academy_trainee_quota_enforced() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        os.environ["ARCLINK_ACADEMY_MAX_TRAINEES_PER_USER"] = "2"
        ap.seed_default_academy_programs(conn)
        ap.enroll_academy_trainee(conn, program_id="domain_tutor", user_id="capped", deployment_id="d")
        ap.enroll_academy_trainee(conn, program_id="domain_tutor", user_id="capped", deployment_id="d")
        raised = False
        try:
            ap.enroll_academy_trainee(conn, program_id="domain_tutor", user_id="capped", deployment_id="d")
        except ap.ArcLinkAcademyProgramError:
            raised = True
        expect(raised, "third enrollment past the cap must be rejected")
        # a different user is unaffected
        other = ap.enroll_academy_trainee(conn, program_id="domain_tutor", user_id="other", deployment_id="d")
        expect(other["status"] == "enrolled", "quota is per-user")
        print("PASS test_academy_trainee_quota_enforced")
    finally:
        cleanup(tmp, old_env)


def test_academy_open_mode_scrubs_opened_via_and_is_idempotent() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="domain_tutor", user_id="u", deployment_id="d")
        secretish = False
        try:
            ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="u", opened_via="api_key=sk-livesecretvalue1234567890")
        except Exception:
            secretish = True
        expect(secretish, "secret-shaped opened_via must be rejected")
        first = ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="u", opened_via="dashboard")
        again = ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="u", opened_via="dashboard")
        expect(first["created"] is True and again["created"] is False, "open is idempotent (sticky)")
        expect(again["session"]["session_id"] == first["session"]["session_id"], "same open session returned")
        print("PASS test_academy_open_mode_scrubs_opened_via_and_is_idempotent")
    finally:
        cleanup(tmp, old_env)


def test_academy_mode_session_growth_is_bounded() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="domain_tutor", user_id="u", deployment_id="d")
        for _ in range(ap.MODE_SESSION_RETENTION_PER_TRAINEE + 12):
            s = ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="u")
            ap.end_academy_mode(conn, session_id=s["session"]["session_id"], actor="u", graduate=False)
        n = conn.execute("SELECT COUNT(*) AS n FROM academy_mode_sessions WHERE trainee_id = ?", (t["trainee_id"],)).fetchone()["n"]
        expect(int(n) <= ap.MODE_SESSION_RETENTION_PER_TRAINEE, f"closed/cancelled sessions are bounded, got {n}")
        print("PASS test_academy_mode_session_growth_is_bounded")
    finally:
        cleanup(tmp, old_env)


def test_academy_graduate_card_redacts_tenant_identity() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(
            conn, program_id="research_analyst", user_id="secret-user", deployment_id="secret-dep",
            agent_id="secret-agent", captain_steer={"focus": "confidential-MnA-target"},
        )
        s = ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="secret-user")
        ap.end_academy_mode(conn, session_id=s["session"]["session_id"], actor="secret-user", graduate=True)
        gallery = ap.browse_academy_graduates(conn, user_id="secret-user")
        grad = gallery["graduates"][0]
        card = ap.academy_graduate_card(grad)
        blob = json.dumps(card, sort_keys=True)
        for leak in ("secret-user", "secret-dep", "secret-agent", "confidential-MnA-target"):
            expect(leak not in blob, f"redacted card must not leak {leak}: {blob}")
        expect(card["trainee_id"] == t["trainee_id"] and "name" in card, "card keeps display fields")
        print("PASS test_academy_graduate_card_redacts_tenant_identity")
    finally:
        cleanup(tmp, old_env)


def test_academy_seed_refreshes_default_catalog_drift() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        conn.execute(
            "UPDATE academy_programs SET label = 'Stale Label', quality_floor = 999 WHERE program_id = 'domain_tutor'"
        )
        conn.commit()

        ap.seed_default_academy_programs(conn)
        program = ap.get_academy_program(conn, "domain_tutor")
        expect(program["label"] == "Domain Tutor", str(program))
        expect(program["quality_floor"] == 66, str(program))
        print("PASS test_academy_seed_refreshes_default_catalog_drift")
    finally:
        cleanup(tmp, old_env)


def test_academy_adopt_helper_blocks_cross_owner_clone() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = _graduate(ap, conn, "systems_practice_engineer", "owner-a", "dep-a")

        raised = False
        try:
            ap.adopt_academy_graduate(
                conn,
                source_trainee_id=t["trainee_id"],
                user_id="owner-b",
                deployment_id="dep-b",
                name="Cross Owner Clone",
            )
        except ap.ArcLinkAcademyProgramError:
            raised = True
        expect(raised, "low-level adopt helper must block cross-owner clone attempts")

        own_copy = ap.adopt_academy_graduate(
            conn,
            source_trainee_id=t["trainee_id"],
            user_id="owner-a",
            deployment_id="dep-a-2",
            name="Owned Clone",
        )
        expect(own_copy["adopted_from_trainee_id"] == t["trainee_id"], str(own_copy))
        print("PASS test_academy_adopt_helper_blocks_cross_owner_clone")
    finally:
        cleanup(tmp, old_env)


def _propose(ap, conn, deployment_id, *, lane_id, title, origin_url, summary, citations=None):
    return ap.record_academy_resource_proposal(
        conn,
        deployment_id=deployment_id,
        lane_id=lane_id,
        title=title,
        origin_url=origin_url,
        summary=summary,
        citations=citations or ([origin_url] if origin_url else []),
        proposed_by="agent-x",
    )


def test_academy_proposals_feed_corpus_not_fixtures() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="research_analyst", user_id="u", deployment_id="dep-pf")
        ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="u")
        _propose(ap, conn, "dep-pf", lane_id="web_article", title="Routing notes",
                 origin_url="https://example.test/routing", summary="Compressed derived routing notes.")

        # read_academy_proposals is no longer a write-only dead table.
        proposals = ap.read_academy_proposals(conn, trainee_id=t["trainee_id"])
        expect(len(proposals) == 1, str(proposals))

        # The corpus now reflects the single proposed source, NOT the 3 lane fixtures.
        curated = ap.curate_academy_trainee(conn, trainee_id=t["trainee_id"])
        expect(curated["source_count"] == 1, f"proposals should feed the corpus, got {curated['source_count']}")
        print("PASS test_academy_proposals_feed_corpus_not_fixtures")
    finally:
        cleanup(tmp, old_env)


def test_academy_graduation_promotes_public_sources_and_skips_private_and_raw() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="systems_practice_engineer", user_id="capt-a", deployment_id="dep-prom")
        s = ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="capt-a")
        _propose(ap, conn, "dep-prom", lane_id="github_repository", title="Reference repo",
                 origin_url="https://example.test/repo", summary="Compressed architecture patterns derived from the repo.")
        _propose(ap, conn, "dep-prom", lane_id="organization_private", title="Private bundle",
                 origin_url="", summary="Captain-only private notes that must never go central.")
        _propose(ap, conn, "dep-prom", lane_id="web_article", title="Raw page",
                 origin_url="https://example.test/raw", summary="<html><div><span>raw markup</span></div></html> not derived notes")

        ended = ap.end_academy_mode(conn, session_id=s["session"]["session_id"], actor="capt-a", graduate=True)
        cs = ended["session"]["commit_summary"]
        expect(cs["central_sources_promoted"] == 1, f"only the public derived source promotes: {cs}")
        expect(cs["central_share_scope"] == "redacted_public", str(cs))

        # academy_sources holds exactly the one public, derived, non-private source.
        rows = conn.execute("SELECT lane_id, canonical_url FROM academy_sources").fetchall()
        expect(len(rows) == 1 and rows[0]["lane_id"] == "github_repository", str([dict(r) for r in rows]))
        # organization_private never reaches the central corpus.
        org = conn.execute("SELECT COUNT(*) AS n FROM academy_sources WHERE lane_id = 'organization_private'").fetchone()
        expect(int(org["n"]) == 0, "organization_private must stay per-tenant")

        # A redacted, identity-free public card is browsable.
        spec_uid = cs["central_specialist_uid"]
        card = ap.academy_specialist_public_card(conn, specialist_uid=spec_uid)
        expect(card is not None and card["source_count"] == 1, str(card))
        expect("user_id" not in card and "contributor_user_id" not in card, "public card must not leak tenant identity")
        expect(card["captain_count"] == 1, str(card))

        # The replaceable compressed-knowledge capsule is composed and versioned.
        expect(cs["central_capsule_version"] >= 1, str(cs))
        spec_row = conn.execute(
            "SELECT compressed_soul_capsule, capsule_version FROM academy_corpus_specialists WHERE specialist_uid = ?",
            (spec_uid,),
        ).fetchone()
        capsule = str(spec_row["compressed_soul_capsule"])
        expect("Academy specialist" in capsule and "Reference repo" in capsule, "capsule carries derived knowledge")
        expect("<html" not in capsule and "raw markup" not in capsule, "capsule never contains raw content")
        print("PASS test_academy_graduation_promotes_public_sources_and_skips_private_and_raw")
    finally:
        cleanup(tmp, old_env)


def test_academy_opt_out_keeps_specialist_private() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="domain_tutor", user_id="capt-x", deployment_id="dep-opt",
                                      captain_steer={"share": "private"})
        s = ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="capt-x")
        _propose(ap, conn, "dep-opt", lane_id="web_article", title="Tutor source",
                 origin_url="https://example.test/tutor", summary="Compressed tutor notes.")
        ap.end_academy_mode(conn, session_id=s["session"]["session_id"], actor="capt-x", graduate=True)
        rows = conn.execute("SELECT COUNT(*) AS n FROM academy_sources").fetchone()
        expect(int(rows["n"]) == 0, "opt-out Captain shares nothing centrally")
        subs = conn.execute("SELECT COUNT(*) AS n FROM academy_specialist_subscriptions").fetchone()
        expect(int(subs["n"]) == 0, "opt-out Captain creates no subscription")
        print("PASS test_academy_opt_out_keeps_specialist_private")
    finally:
        cleanup(tmp, old_env)


def test_academy_central_specialist_shared_and_deduped_across_captains() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        # Captain A trains + graduates a shared specialist with one public source.
        a = ap.enroll_academy_trainee(conn, program_id="systems_practice_engineer", user_id="capt-a", deployment_id="dep-a")
        sa = ap.open_academy_mode(conn, trainee_id=a["trainee_id"], opened_by="capt-a")
        _propose(ap, conn, "dep-a", lane_id="github_repository", title="Shared repo",
                 origin_url="https://example.test/shared-repo", summary="Derived patterns A gathered.")
        ap.end_academy_mode(conn, session_id=sa["session"]["session_id"], actor="capt-a", graduate=True)

        spec_uid, _ = ap.specialist_uid_for_program(ap.get_academy_program(conn, "systems_practice_engineer"))

        # Captain B enrolls the SAME Major and inherits the shared corpus on enroll.
        b = ap.enroll_academy_trainee(conn, program_id="systems_practice_engineer", user_id="capt-b", deployment_id="dep-b")
        inherited = ap.read_central_specialist_sources(conn, trainee_id=b["trainee_id"])
        expect(len(inherited) == 1 and inherited[0]["lane_id"] == "github_repository",
               f"Captain B should inherit A's shared source: {inherited}")
        # B's curated corpus is non-empty WITHOUT B gathering anything (reuse, not re-train).
        curated_b = ap.curate_academy_trainee(conn, trainee_id=b["trainee_id"])
        expect(curated_b["source_count"] == 1, f"B reuses the central corpus: {curated_b}")

        # B proposes the SAME canonical URL + graduates -> global dedup to ONE row.
        sb = ap.open_academy_mode(conn, trainee_id=b["trainee_id"], opened_by="capt-b")
        _propose(ap, conn, "dep-b", lane_id="github_repository", title="Shared repo (B's take)",
                 origin_url="https://example.test/shared-repo", summary="Derived patterns B also gathered.",
                 citations=["https://example.test/shared-repo", "https://example.test/shared-repo#capt-b"])
        ap.end_academy_mode(conn, session_id=sb["session"]["session_id"], actor="capt-b", graduate=True)
        n_sources = conn.execute("SELECT COUNT(*) AS n FROM academy_sources").fetchone()
        expect(int(n_sources["n"]) == 1, "same canonical source from two captains dedupes to one central row")
        central = conn.execute("SELECT derived_notes, citations_json FROM academy_sources").fetchone()
        expect("Derived patterns A gathered." in str(central["derived_notes"]), "first accepted central notes are retained")
        expect("Derived patterns B also gathered." not in str(central["derived_notes"]), "dedupe must not let later captains overwrite shared notes")
        citations = json.loads(str(central["citations_json"]))
        expect("https://example.test/shared-repo#capt-b" in citations, f"later captains can still add provenance citations: {citations}")
        card = ap.academy_specialist_public_card(conn, specialist_uid=spec_uid)
        expect(card["captain_count"] == 2, f"two distinct captains contributed: {card}")
        gallery = ap.list_central_specialists(conn)
        expect(any(c["specialist_uid"] == spec_uid for c in gallery), "shared specialist appears in the central gallery")
        search = ap.search_academy_reuse_candidates(
            conn,
            user_id="capt-b",
            query="systems practice shared repo architecture",
            program_id="systems_practice_engineer",
        )
        expect(search["candidates"], str(search))
        expect(search["candidates"][0]["kind"] == "central_specialist", str(search))
        blob = json.dumps(search, sort_keys=True)
        expect("dep-a" not in blob and "capt-a" not in blob, f"reuse search must stay redacted: {blob}")
        print("PASS test_academy_central_specialist_shared_and_deduped_across_captains")
    finally:
        cleanup(tmp, old_env)


class _FakeLiveTrainer:
    live = True

    def review(self, *, role_title, topic, sources):
        return {
            "engine": "live-router",
            "live": True,
            "summary": f"Live Trainer review for {role_title}",
            "verdicts": [{"source_uid": s["source_uid"], "verdict": "keep"} for s in sources],
        }


def test_academy_trainer_deep_dive_reviews_and_stamps_and_supports_live() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="systems_practice_engineer", user_id="capt-t", deployment_id="dep-t")
        s = ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="capt-t")
        _propose(ap, conn, "dep-t", lane_id="github_repository", title="Deep dive repo",
                 origin_url="https://example.test/dd-repo", summary="Derived patterns for the deep dive.")
        ended = ap.end_academy_mode(conn, session_id=s["session"]["session_id"], actor="capt-t", graduate=True)
        cs = ended["session"]["commit_summary"]

        # The deterministic Trainer deep dive ran at graduation...
        expect(cs["central_trainer_reviewed"] is True, str(cs))
        expect(cs["central_trainer_engine"] == "deterministic", str(cs))
        # ...but the LIVE (same-inference-model) deep dive stays PG-PROVIDER queued.
        expect(cs["trainer_deep_dive_status"] == "queued_for_review", str(cs))
        expect(cs["central_trainer_live_status"] == "pending_pg_provider", str(cs))

        spec_uid = cs["central_specialist_uid"]
        spec = conn.execute(
            "SELECT enrichment_json FROM academy_corpus_specialists WHERE specialist_uid = ?", (spec_uid,)
        ).fetchone()
        expect('"engine": "deterministic"' in str(spec["enrichment_json"]), str(spec["enrichment_json"]))

        # The contributing proposal carries a Trainer review stamp.
        prop = conn.execute(
            "SELECT trainer_review_json FROM academy_resource_proposals WHERE trainee_id = ?", (t["trainee_id"],)
        ).fetchone()
        expect('"specialist_uid"' in str(prop["trainer_review_json"]), str(prop["trainer_review_json"]))

        # A PG-PROVIDER-authorized live client routes through the live engine.
        live = ap.run_academy_trainer_review(conn, specialist_uid=spec_uid, client=_FakeLiveTrainer(), live_authorized=True)
        expect(live["live"] is True and live["engine"] == "live-router", str(live))
        # Without authorization a live client is ignored (fail-closed to deterministic).
        det = ap.run_academy_trainer_review(conn, specialist_uid=spec_uid, client=_FakeLiveTrainer(), live_authorized=False)
        expect(det["live"] is False and det["engine"] == "deterministic", str(det))
        print("PASS test_academy_trainer_deep_dive_reviews_and_stamps_and_supports_live")
    finally:
        cleanup(tmp, old_env)


def test_academy_apply_stages_replaceable_soul_section() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        import arclink_org_profile as op

        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="research_analyst", user_id="capt-s", deployment_id="dep-s")
        s = ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="capt-s")
        _propose(ap, conn, "dep-s", lane_id="web_article", title="Capsule source",
                 origin_url="https://example.test/capsule", summary="Derived notes that should land in the capsule.")
        ap.end_academy_mode(conn, session_id=s["session"]["session_id"], actor="capt-s", graduate=True)

        applied = ap.stage_academy_apply(conn, trainee_id=t["trainee_id"], adapter_name="fake")
        section = applied["academy_soul_section"]
        expect(applied["academy_capsule_version"] >= 1, str(applied))
        expect(op.BEGIN_ACADEMY_MARKER in section and op.END_ACADEMY_MARKER in section, section)
        expect("Capsule source" in section, "rendered section carries the curated derived notes")
        expect(applied["writes_enabled"] is False, "record-only apply still writes nothing")

        # The Academy section is additive + replaceable: merging it preserves the
        # human SOUL body and a co-existing org-profile overlay; removing it strips
        # only the Academy block.
        human = "# SOUL\nHuman-authored mission.\n"
        with_org = op.merge_soul_overlay(human, op.render_soul_overlay({"organization": {"name": "Acme"}, "revision": "abc"}))
        with_both = op.merge_academy_overlay(with_org, section)
        expect("Human-authored mission." in with_both, "human SOUL body is preserved")
        expect(op.BEGIN_SOUL_MARKER in with_both and op.BEGIN_ACADEMY_MARKER in with_both, "both overlays co-exist")
        stripped = op.remove_academy_overlay(with_both)
        expect(op.BEGIN_ACADEMY_MARKER not in stripped, "remove strips only the Academy block")
        expect("Human-authored mission." in stripped and op.BEGIN_SOUL_MARKER in stripped, "remove leaves SOUL + org overlay intact")
        print("PASS test_academy_apply_stages_replaceable_soul_section")
    finally:
        cleanup(tmp, old_env)


def test_academy_continuing_education_uses_real_sources() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="research_analyst", user_id="capt-ce", deployment_id="dep-ce")
        s = ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="capt-ce")
        _propose(ap, conn, "dep-ce", lane_id="web_article", title="Weekly real source",
                 origin_url="https://example.test/weekly-real", summary="Compressed weekly source notes.")
        ap.end_academy_mode(conn, session_id=s["session"]["session_id"], actor="capt-ce", graduate=True)

        weekly = ap.academy_continuing_education(conn, trainee_id=t["trainee_id"], created_at="2026-05-31T00:00:00Z")
        refreshes = weekly["source_refreshes"]
        expect(len(refreshes) == 1, f"weekly review should revisit the real Academy source, not fixtures: {weekly}")
        expect(refreshes[0]["lane_id"] == "web_article", str(refreshes))
        expect(weekly["mutation_performed"] is False and weekly["no_write"] is True, "weekly review remains no-write")
        print("PASS test_academy_continuing_education_uses_real_sources")
    finally:
        cleanup(tmp, old_env)


if __name__ == "__main__":
    test_academy_proposals_feed_corpus_not_fixtures()
    test_academy_graduation_promotes_public_sources_and_skips_private_and_raw()
    test_academy_opt_out_keeps_specialist_private()
    test_academy_central_specialist_shared_and_deduped_across_captains()
    test_academy_trainer_deep_dive_reviews_and_stamps_and_supports_live()
    test_academy_apply_stages_replaceable_soul_section()
    test_academy_apply_validates_staged_contract_and_fails_closed_on_major_drift()
    test_academy_apply_rejects_target_owner_mismatch()
    test_academy_continuing_education_uses_real_sources()
    test_academy_trainee_quota_enforced()
    test_academy_open_mode_scrubs_opened_via_and_is_idempotent()
    test_academy_mode_session_growth_is_bounded()
    test_academy_graduate_card_redacts_tenant_identity()
    test_academy_seed_refreshes_default_catalog_drift()
    test_academy_adopt_helper_blocks_cross_owner_clone()
    test_academy_apply_is_fail_closed()
    test_academy_apply_requires_graduated_trainee()
    test_academy_curation_builds_corpus_plan_and_stages()
    test_academy_commit_curates_on_graduation()
    test_academy_continuing_education_is_no_write()
    test_academy_catalog_seed_is_idempotent_and_browsable()
    test_academy_enroll_open_sticky_and_graduate()
    test_academy_mode_records_steer_and_resource_proposals()
    test_academy_cancel_mode_returns_to_enrolled()
    test_academy_browse_graduates_and_adopt()
    test_academy_many_types_as_data_and_lane_validation()
    test_academy_rejects_secret_material_and_unknown_program()
    print("PASS all academy programs tests")
