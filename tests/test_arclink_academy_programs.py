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
        expect(ended["session"]["status"] == "closed", str(ended["session"]))
        print("PASS test_academy_enroll_open_sticky_and_graduate")
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

        adopted = ap.adopt_academy_graduate(conn, source_trainee_id=t["trainee_id"], user_id="u2", deployment_id="dep-b", name="Grace II")
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


if __name__ == "__main__":
    test_academy_apply_is_fail_closed()
    test_academy_apply_requires_graduated_trainee()
    test_academy_curation_builds_corpus_plan_and_stages()
    test_academy_commit_curates_on_graduation()
    test_academy_continuing_education_is_no_write()
    test_academy_catalog_seed_is_idempotent_and_browsable()
    test_academy_enroll_open_sticky_and_graduate()
    test_academy_cancel_mode_returns_to_enrolled()
    test_academy_browse_graduates_and_adopt()
    test_academy_many_types_as_data_and_lane_validation()
    test_academy_rejects_secret_material_and_unknown_program()
    print("PASS all academy programs tests")
