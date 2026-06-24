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


def _seed_deployment(conn, *, deployment_id: str, user_id: str, status: str = "active") -> None:
    now = "2026-05-27T03:00:00Z"
    conn.execute(
        """
        INSERT INTO arclink_deployments (
          deployment_id, user_id, prefix, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (deployment_id, user_id, deployment_id.replace("_", "-")[:40] or "dep", status, now, now),
    )
    conn.commit()


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

        blocked = ap.end_academy_mode(conn, session_id=opened["session"]["session_id"], actor="tg:42", graduate=True)
        expect(blocked["graduated"] is False and blocked["status"] == "needs_training_sources", str(blocked))
        expect(blocked["trainee"]["status"] == "in_academy" and blocked["trainee"]["mode_open"] is True, str(blocked["trainee"]))
        expect(blocked["trainee"]["forward_maintained"] is False, "fixture-only trainee must not arm continuing education")

        ap.record_academy_resource_proposal(
            conn,
            deployment_id="dep-1",
            lane_id="web_article",
            title="Research analyst field guide",
            origin_url="https://example.test/research-analyst-guide",
            summary="A real governed source gathered during Academy Mode.",
            proposed_by="agent-1",
        )
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


def test_academy_resource_proposal_insert_race_returns_deduped() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        trainee = ap.enroll_academy_trainee(conn, program_id="research_analyst", user_id="user-race", deployment_id="dep-race")
        ap.open_academy_mode(conn, trainee_id=trainee["trainee_id"], opened_by="captain")

        class RaceConn:
            def __init__(self, inner):
                self.inner = inner
                self.raced = False

            def execute(self, sql, params=()):
                if not self.raced and "INSERT INTO academy_resource_proposals" in str(sql):
                    self.raced = True
                    self.inner.execute(sql, params)
                    raise ap.sqlite3.IntegrityError("UNIQUE constraint failed: academy_resource_proposals.proposal_id")
                return self.inner.execute(sql, params)

            def commit(self):
                return self.inner.commit()

        raced = ap.record_academy_resource_proposal(
            RaceConn(conn),
            deployment_id="dep-race",
            lane_id="web_article",
            title="Race source",
            origin_url="https://example.test/race-source",
            summary="Compressed race source notes.",
            proposed_by="agent-race",
        )
        expect(raced["status"] == "deduped", str(raced))
        rows = conn.execute("SELECT proposal_id, status FROM academy_resource_proposals").fetchall()
        expect(len(rows) == 1 and rows[0]["proposal_id"] == raced["proposal_id"], str([dict(row) for row in rows]))
        print("PASS test_academy_resource_proposal_insert_race_returns_deduped")
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
        ap.record_academy_resource_proposal(
            conn,
            deployment_id="dep-a",
            lane_id="web_article",
            title="Systems practice source",
            origin_url="https://example.test/grace/systems-practice",
            summary="Governed Academy source for the graduate gallery.",
            proposed_by="agent-1",
        )
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


def test_academy_adopts_central_specialist_for_new_captain() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="systems_practice_engineer", user_id="u1", deployment_id="dep-a", name="Grace",
                                      captain_steer={"share": "redacted_public"})  # D-E: explicit public opt-in
        s = ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="u1")
        _propose(
            ap,
            conn,
            "dep-a",
            lane_id="web_article",
            title="Shared systems practice source",
            origin_url="https://example.test/systems-practice",
            summary="Derived public-lane notes for systems practice.",
        )
        ended = ap.end_academy_mode(conn, session_id=s["session"]["session_id"], actor="u1", graduate=True)
        specialist_uid = ended["session"]["commit_summary"]["central_specialist_uid"]
        card = ap.academy_specialist_public_card(conn, specialist_uid=specialist_uid)
        expect(card is not None and card["source_count"] >= 1, str(card))

        adopted = ap.adopt_central_specialist(
            conn,
            specialist_uid=specialist_uid,
            user_id="u2",
            deployment_id="dep-b",
            name="Grace Shared",
        )
        expect(adopted["status"] == "graduated", str(adopted))
        expect(adopted["central_specialist"]["specialist_uid"] == specialist_uid, str(adopted))
        expect(adopted["staged_source_count"] >= 1, str(adopted))
        steer = adopted["captain_steer"]
        expect(steer["adopted_central_specialist_uid"] == specialist_uid and steer["share"] == "redacted_public", str(steer))
        sub = conn.execute(
            "SELECT * FROM academy_specialist_subscriptions WHERE trainee_id = ? AND specialist_uid = ?",
            (adopted["trainee_id"], specialist_uid),
        ).fetchone()
        expect(sub is not None and sub["user_id"] == "u2", str(dict(sub) if sub else None))
        print("PASS test_academy_adopts_central_specialist_for_new_captain")
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


def test_academy_source_lane_registry_failure_fails_closed() -> None:
    tmp, old_env, _conn, _control, ap = with_db()
    sentinel = object()
    original = sys.modules.get("arclink_academy_trainer", sentinel)
    try:
        sys.modules["arclink_academy_trainer"] = None
        raised = False
        try:
            ap._validate_source_lanes(["web_article"])
        except ap.ArcLinkAcademyProgramError as exc:
            raised = "registry" in str(exc)
        expect(raised, "source lanes must not be accepted when the governed registry cannot load")
        print("PASS test_academy_source_lane_registry_failure_fails_closed")
    finally:
        if original is sentinel:
            sys.modules.pop("arclink_academy_trainer", None)
        else:
            sys.modules["arclink_academy_trainer"] = original
        cleanup(tmp, old_env)


def test_academy_enroll_surfaces_subscription_failure() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    original = ap.subscribe_trainee_to_specialist

    def fail_subscribe(*args, **kwargs):
        raise RuntimeError("subscription row corrupt")

    try:
        ap.seed_default_academy_programs(conn)
        ap.subscribe_trainee_to_specialist = fail_subscribe
        trainee = ap.enroll_academy_trainee(conn, program_id="research_analyst", user_id="capt-sub", deployment_id="dep-sub")
        expect(trainee["status"] == "enrolled", str(trainee))
        event = conn.execute(
            "SELECT subject_id, metadata_json FROM arclink_events WHERE event_type = 'academy_specialist_subscription_failed'"
        ).fetchone()
        expect(event is not None and event["subject_id"] == trainee["trainee_id"], str(dict(event) if event else None))
        expect("subscription row corrupt" in str(event["metadata_json"]), str(event["metadata_json"]))
        print("PASS test_academy_enroll_surfaces_subscription_failure")
    finally:
        ap.subscribe_trainee_to_specialist = original
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
        label_secretish = False
        try:
            ap.upsert_academy_program(
                conn,
                program_id="secret_label",
                label="api_key=sk-livesecretvalue1234567890",
                source_lanes=["web_article"],
            )
        except Exception:
            label_secretish = True
        expect(label_secretish, "secret-looking Major labels must be rejected before they can become public specialist titles")
        print("PASS test_academy_rejects_secret_material_and_unknown_program")
    finally:
        cleanup(tmp, old_env)


def test_academy_curation_builds_corpus_plan_and_stages() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="systems_practice_engineer", user_id="u", deployment_id="dep-c")
        # Increment 0 / D-C: the lane-fixture corpus is now test-only and reached
        # solely via the explicit opt-in. This test exercises the curation ENGINE.
        result = ap.curate_academy_trainee(conn, trainee_id=t["trainee_id"], allow_fixture_fallback=True)
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


def test_academy_curation_without_real_sources_is_honest_draft() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="systems_practice_engineer", user_id="u", deployment_id="dep-d")
        # Increment 0 / D-C: the operator-visible default path must NOT fabricate
        # example.test fixtures. With no real validated sources, curation yields an
        # HONEST draft (authored=false / needs_more_sources), never a fake corpus.
        result = ap.curate_academy_trainee(conn, trainee_id=t["trainee_id"])
        expect(result["source_count"] == 0, f"no real sources -> honest empty draft, got {result['source_count']}")
        expect(result["manifest_id"] == "", "an honest draft stages no manifest id")
        review = result["review"]
        expect(review.get("status") == "needs_more_sources", str(review))
        expect(review.get("authored") is False, "draft must be labeled authored=false")
        blob = json.dumps(result, default=str)
        expect("example.test" not in blob, "operator-visible curation must never contain fabricated example.test rows")
        print("PASS test_academy_curation_without_real_sources_is_honest_draft")
    finally:
        cleanup(tmp, old_env)


def test_academy_charter_builds_with_failsafe_defaults_and_status() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        program = ap.get_academy_program(conn, "research_analyst")
        # Missing required slots (no outcomes / no scenarios) -> needs_answers, never fabricated.
        partial = ap.build_charter({"subject_scope": "Example Standard 2026 migration"}, program=program)
        expect(partial["status"] == "needs_answers", f"no exam scenarios yet -> needs_answers, got {partial['status']}")
        # N1: target_outcomes is DERIVED from subject_scope (labeled), not required.
        expect("acceptance_scenarios" in partial["missing_slots"], str(partial["missing_slots"]))
        expect("target_outcomes" not in partial["missing_slots"], "target_outcomes is derived, not a required slot")
        expect(partial["slots"]["target_outcomes"] == ["Example Standard 2026 migration"], "outcome derived from subject_scope")
        expect(partial["defaults_applied"].get("target_outcomes") == "derived_from_subject_scope", str(partial["defaults_applied"]))
        expect(partial["authored"] is False and partial["engine"] == "deterministic", "v1 charter is deterministic/unauthored")
        # D-E fail-safe: a skipped share-policy defaults to PRIVATE, never redacted_public.
        expect(partial["slots"]["share_policy"] == "private", "skip share-policy -> private fail-safe")
        expect(partial["defaults_applied"].get("share_policy") == "private", "private default is surfaced for the preview")
        # Program lanes inferred when the operator does not name lanes.
        expect(partial["slots"]["authorized_source_lanes"], "lanes inferred from the Major when unspecified")
        print("PASS test_academy_charter_builds_with_failsafe_defaults_and_status")
    finally:
        cleanup(tmp, old_env)


def test_academy_charter_roundtrips_over_2000_chars_through_edit_path() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        program = ap.get_academy_program(conn, "research_analyst")
        # A realistic charter (3 scenarios x 3 criteria + padded outcomes) that exceeds
        # the [:2000] scalar-truncation boundary of update_academy_trainee_steer.
        slots = {
            "subject_scope": "Example Standard 2026 migration risk analysis " + ("x" * 400),
            "target_outcomes": ["ship gap reports " + ("y" * 300), "flag compliance regressions " + ("z" * 300)],
            "expected_work_products": ["weekly standards brief " + ("w" * 300)],
            "acceptance_scenarios": [
                {"prompt": "Summarize material changes with citations " + ("a" * 200),
                 "pass_criteria": ["cites two governed sources", "separates durable from provisional", "lists follow-up proof " + ("b" * 150)]},
                {"prompt": "Identify compliance impact of a repo change " + ("c" * 200),
                 "pass_criteria": ["names the affected component", "links to standard evidence", "recommends a bounded next action"]},
                {"prompt": "Refuse to reveal private strategy while offering public guidance " + ("d" * 200),
                 "pass_criteria": ["does not disclose private strategy", "explains the boundary", "offers a public-source alternative"]},
            ],
        }
        charter = ap.build_charter(slots, program=program)
        expect(charter["status"] == "ready", f"all required slots present -> ready, got {charter['status']}")
        raw_len = len(json.dumps(charter))
        expect(raw_len > 2000, f"charter must exceed the [:2000] truncation boundary, got {raw_len}")

        # 1) Survives ENROLL (charter_json carried in captain_steer, dumped raw).
        t = ap.enroll_academy_trainee(
            conn, program_id="research_analyst", user_id="u", deployment_id="dep-ch",
            captain_steer={"charter_json": json.dumps(charter)},
        )
        expect(ap.get_trainee_charter(conn, t["trainee_id"]) == charter, "charter survives enroll intact")

        # 2) Survives the dedicated EDIT writer (the D-A' fix) even >2000 chars.
        edited = json.loads(json.dumps(charter))
        edited["slots"]["depth_tier"] = "expert"
        ap.set_trainee_charter(conn, trainee_id=t["trainee_id"], charter=edited)
        got2 = ap.get_trainee_charter(conn, t["trainee_id"])
        expect(got2 == edited and got2["slots"]["depth_tier"] == "expert", "edited >2000-char charter round-trips through the edit path")

        # 3) An UNRELATED steer update must NOT corrupt the stored charter_json.
        ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="u")
        ap.update_academy_trainee_steer(conn, trainee_id=t["trainee_id"], updates={"focus": "tighten scope"}, actor="u")
        expect(ap.get_trainee_charter(conn, t["trainee_id"]) == edited, "unrelated steer edit leaves charter_json intact (not re-truncated)")
        print("PASS test_academy_charter_roundtrips_over_2000_chars_through_edit_path")
    finally:
        cleanup(tmp, old_env)


def test_academy_materialize_operator_sources_classifies_screens_and_graduatable() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="systems_practice_engineer", user_id="u", deployment_id="dep-mat")
        ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="u")
        result = ap.materialize_operator_academy_sources(
            conn,
            deployment_id="dep-mat",
            entries=[
                {"url": "repo:github.com/acme/x", "summary": "Derived notes on the deploy pipeline."},  # derived + github + repo: normalize
                "https://standards.example.org/spec",  # bare pointer -> where_to_look
                {"url": "https://internal.acme/playbook", "private": True, "summary": "Private migration playbook."},  # private
                {"url": "https://x/y", "summary": "token=AKIAIOSFODNN7EXAMPLE"},  # secret -> screened out
            ],
        )
        expect(result["no_egress"] is True, str(result))
        expect(result["derived_count"] == 2 and result["where_to_look_count"] == 1 and result["private_count"] == 1, str(result))
        expect(any(s.get("reason") == "secret_material" for s in result["skipped"]), f"secret summary must be screened out: {result['skipped']}")
        props = result["proposals"]
        gh = next((p for p in props if "github.com/acme/x" in (p.get("origin_url") or "")), None)
        expect(gh is not None, str(props))
        expect(gh["origin_url"] == "https://github.com/acme/x", f"repo: normalized: {gh['origin_url']}")
        expect(gh["lane_id"] == "github_repository", str(gh))
        expect(gh["skill_family"] == "systems_engineering", f"proposal stamped with Major family: {gh}")
        expect(gh["source_metadata"]["intake_kind"] == "derived" and gh["source_metadata"]["storage_policy"] == "derived_summary", str(gh["source_metadata"]))
        priv = next((p for p in props if p["lane_id"] == "organization_private"), None)
        expect(priv is not None and priv["source_metadata"]["share_scope"] == "private", str(props))
        ptr = next((p for p in props if p["source_metadata"].get("intake_kind") == "where_to_look"), None)
        expect(ptr is not None and ptr["source_metadata"]["storage_policy"] == "metadata_only", "bare url -> honest where_to_look pointer")
        trainee = ap.get_academy_trainee(conn, t["trainee_id"])
        expect(ap._trainee_has_real_training_sources(conn, trainee) is True, "operator-supplied governed sources make the agent graduatable")
        print("PASS test_academy_materialize_operator_sources_classifies_screens_and_graduatable")
    finally:
        cleanup(tmp, old_env)


def test_academy_extract_model_json_fence_tolerant() -> None:
    """Live-path fix (E2E-found): chat models (Kimi/GLM) wrap JSON in a ```json fence even when
    asked for strict JSON. _extract_model_json must recover it (raw, fenced, prose-wrapped),
    else live synthesis silently authors nothing."""
    tmp, old_env, conn, _control, ap = with_db()
    try:
        expect(ap._extract_model_json('{"a": 1}') == {"a": 1}, "raw JSON")
        expect(ap._extract_model_json(' ```json\n{"a": 1}\n``` ') == {"a": 1}, "```json fenced")
        expect(ap._extract_model_json('```\n{"a": 1}\n```') == {"a": 1}, "bare ``` fenced")
        expect(ap._extract_model_json('Here you go: {"a": 1} -- done.') == {"a": 1}, "prose-wrapped span")
        expect(ap._extract_model_json("not json at all") == {}, "junk -> {}")
        expect(ap._extract_model_json("") == {} and ap._extract_model_json(None) == {}, "empty/None -> {}")
        print("PASS test_academy_extract_model_json_fence_tolerant")
    finally:
        cleanup(tmp, old_env)


def test_academy_synthesis_engine_two_pass_fail_closed() -> None:
    """inc3: run_academy_trainer_synthesize authors lesson_notes + a SOUL capsule;
    deterministic = honest non-authored draft; the public pass excludes the private
    lane; a live failure OR a secret/raw echo falls CLOSED to deterministic; the
    artifact is bound to the apply manifest id; the upsert is idempotent per scope."""
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(
            conn, program_id="research_analyst", user_id="u", deployment_id="dep-syn",
            captain_steer={"charter_json": ap.build_charter(
                {"subject_scope": "Bibliometric triage of ML papers",
                 "acceptance_scenarios": [{"prompt": "Assess a paper's novelty", "pass_criteria": ["cite a source"]}]},
                program=ap.get_academy_program(conn, "research_analyst"))},
        )
        tid = t["trainee_id"]
        ap.open_academy_mode(conn, trainee_id=tid, opened_by="u")
        ap.record_academy_resource_proposal(
            conn, deployment_id="dep-syn", trainee_id=tid, origin_url="https://example.org/guide",
            lane_id="organization_private", summary="Derived: prefer replicated studies; weight by sample size and design.",
            title="Triage heuristics", proposed_by="u",
        )
        # Deterministic = honest draft (never authored/graduated), bound to the apply manifest id.
        det = ap.run_academy_trainer_synthesize(conn, trainee_id=tid, scope="private", live_authorized=False)
        expect(det["engine"] == "deterministic" and det["authored"] is False, str(det))
        expect(det["status"] == "needs_live_synthesis" and det["lesson_note_count"] == 1, str(det))
        expect(bool(det["authored_for_manifest_id"]), "synthesis bound to the deterministic apply manifest id")
        composed = ap._compose_trainee_corpus(conn, tid, sources=None, now="2026-05-27T03:00:00Z")
        expect(det["authored_for_manifest_id"] == composed["manifest_id"], "authored_for_manifest_id == the id apply recomputes")
        art = ap.get_trainee_synthesis_artifact(conn, tid, scope="private")
        expect(art is not None and art["authored"] is False and art["scope"] == "private", str(art))
        # Two-pass scope propagation: the public (promotable) pass excludes the private lane.
        pub = ap.run_academy_trainer_synthesize(conn, trainee_id=tid, scope="public", live_authorized=False)
        expect(pub["lesson_note_count"] == 0, f"public pass must exclude organization_private material: {pub}")
        # An empty promotable subset binds to "" -- it must NOT fingerprint the excluded
        # organization_private sources into the public artifact's manifest id (audit fix).
        expect(pub["authored_for_manifest_id"] == "", f"empty public set -> empty manifest id, not the private-set id: {pub}")

        # Fail-closed checks run BEFORE any authored artifact exists (the F4/MISS-C guard
        # would otherwise correctly PRESERVE an authored artifact across a failed rerun --
        # that downgrade-block is exercised in the dedicated screens/downgrade test).
        class FakeBoom:
            live = True
            def synthesize(self, **_k):
                raise RuntimeError("router 503")

        fc = ap.run_academy_trainer_synthesize(conn, trainee_id=tid, scope="private", client=FakeBoom(), live_authorized=True)
        expect(fc["engine"] == "deterministic" and fc["authored"] is False and bool(fc["live_error"]), f"live failure falls closed: {fc}")

        class FakeSecret:
            live = True
            def synthesize(self, *, role_title, topic, charter, sources):
                return {"engine": "live-router", "authored": True,
                        "lesson_notes": [{"source_uid": sources[0]["source_uid"], "note": "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"}],
                        "soul_capsule": "x", "retrieval_rules": [], "quality_metrics": {}}

        sec = ap.run_academy_trainer_synthesize(conn, trainee_id=tid, scope="private", client=FakeSecret(), live_authorized=True)
        expect(sec["engine"] == "deterministic" and sec["authored"] is False and bool(sec["live_error"]), f"secret echo falls closed: {sec}")

        class FakeLive:
            live = True
            def synthesize(self, *, role_title, topic, charter, sources):
                return {"engine": "live-router", "authored": True,
                        "lesson_notes": [{"source_uid": s["source_uid"], "note": "Authored: weigh by study design."} for s in sources],
                        "soul_capsule": "You are a Research Analyst. Cite a governed source before any claim.",
                        "retrieval_rules": ["cite before claim"], "quality_metrics": {"engine": "live-router"}}

        live = ap.run_academy_trainer_synthesize(conn, trainee_id=tid, scope="private", client=FakeLive(), live_authorized=True)
        expect(live["engine"] == "live-router" and live["authored"] is True and live["status"] == "authored", str(live))
        # Idempotent upsert: one row per (trainee, scope) regardless of re-runs.
        ap.run_academy_trainer_synthesize(conn, trainee_id=tid, scope="private", live_authorized=False)
        rows = conn.execute("SELECT COUNT(*) FROM academy_synthesis_artifacts WHERE trainee_id = ?", (tid,)).fetchone()[0]
        expect(rows == 2, f"one artifact per scope (private+public), got {rows}")
        print("PASS test_academy_synthesis_engine_two_pass_fail_closed")
    finally:
        cleanup(tmp, old_env)


def test_academy_synthesis_screens_all_fields_and_blocks_downgrade() -> None:
    """Federation NOW-fixes: F1 (a live secret in retrieval_rules falls CLOSED — the
    field was previously unscreened); F4/MISS-C (a failed rerun must NEVER downgrade an
    authored artifact to deterministic for the same manifest); D-X3 (the deterministic
    path DROPS raw/secret material that arrives via a non-proposal path); CODEX-MISS-1
    (raw summaries are rejected at proposal intake)."""
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(
            conn, program_id="research_analyst", user_id="u", deployment_id="dep-scr",
            captain_steer={"charter_json": ap.build_charter(
                {"subject_scope": "Triage", "acceptance_scenarios": [{"prompt": "Assess novelty", "pass_criteria": ["cite"]}]},
                program=ap.get_academy_program(conn, "research_analyst"))},
        )
        tid = t["trainee_id"]
        ap.open_academy_mode(conn, trainee_id=tid, opened_by="u")
        ap.record_academy_resource_proposal(
            conn, deployment_id="dep-scr", trainee_id=tid, origin_url="https://example.org/g",
            lane_id="organization_private", summary="Derived: weigh by sample size.", title="Heur", proposed_by="u",
        )
        SECRET = "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

        # F1: a live secret hidden in retrieval_rules (NOT lesson_notes/soul_capsule) must fall closed.
        class SecretRules:
            live = True
            def synthesize(self, *, role_title, topic, charter, sources):
                return {"engine": "live-router", "authored": True,
                        "lesson_notes": [{"source_uid": sources[0]["source_uid"], "note": "weigh by design"}],
                        "soul_capsule": "Cite before claim.",
                        "retrieval_rules": ["normal rule", SECRET], "quality_metrics": {}}

        a = ap.run_academy_trainer_synthesize(conn, trainee_id=tid, scope="private", client=SecretRules(), live_authorized=True)
        expect(a["engine"] == "deterministic" and a["authored"] is False and bool(a["live_error"]),
               f"secret in retrieval_rules must fall closed (F1): {a}")

        # F4/MISS-C: author cleanly, then a failed rerun must KEEP the authored artifact.
        class CleanLive:
            live = True
            def synthesize(self, *, role_title, topic, charter, sources):
                return {"engine": "live-router", "authored": True,
                        "lesson_notes": [{"source_uid": s["source_uid"], "note": "authored note"} for s in sources],
                        "soul_capsule": "You are a Research Analyst. Cite before claim.",
                        "retrieval_rules": ["cite first"], "quality_metrics": {}}

        au = ap.run_academy_trainer_synthesize(conn, trainee_id=tid, scope="private", client=CleanLive(), live_authorized=True)
        expect(au["authored"] is True and au["engine"] == "live-router", str(au))
        authored_hash = au["content_hash"]

        class Boom:
            live = True
            def synthesize(self, **_k):
                raise RuntimeError("router 503")

        rr = ap.run_academy_trainer_synthesize(conn, trainee_id=tid, scope="private", client=Boom(), live_authorized=True)
        expect(rr["authored"] is True and rr["engine"] == "live-router" and rr["content_hash"] == authored_hash,
               f"failed rerun must NOT downgrade an authored artifact (F4/MISS-C): {rr}")
        expect(rr["downgrade_blocked"] is True, "downgrade was correctly blocked")
        persisted = ap.get_trainee_synthesis_artifact(conn, tid, scope="private")
        expect(persisted["authored"] is True, "persisted artifact stays authored after a failed rerun")

        # D-X3: raw content arriving via a non-proposal path (an inherited central source's
        # derived_notes) is DROPPED by the deterministic clean, not persisted.
        t2 = ap.enroll_academy_trainee(
            conn, program_id="research_analyst", user_id="u", deployment_id="dep-scr",
            captain_steer={"charter_json": ap.build_charter(
                {"subject_scope": "Triage", "acceptance_scenarios": [{"prompt": "x", "pass_criteria": ["cite"]}]},
                program=ap.get_academy_program(conn, "research_analyst"))},
        )
        tid2 = t2["trainee_id"]
        ap.open_academy_mode(conn, trainee_id=tid2, opened_by="u")
        raw_summary = "<div><span><p><a><b><i> raw html dump </i></b></a></p></span></div>"
        # Insert raw notes via a direct proposal row, bypassing the intake screen, to exercise
        # the synthesis-side clean (the corpus-resolver path that intake doesn't cover).
        conn.execute(
            "UPDATE academy_resource_proposals SET summary = ? WHERE trainee_id = ? ",
            (raw_summary, tid),  # poison an EXISTING (already-screened) proposal row directly
        )
        conn.commit()
        dC = ap.run_academy_trainer_synthesize(conn, trainee_id=tid, scope="private", live_authorized=False)
        expect(dC["status"] == "needs_source_cleanup" and dC["lesson_note_count"] == 0,
               f"deterministic clean drops the raw note + flags needs_source_cleanup: {dC}")
        expect(dC["quality_metrics"].get("screen_rejections"), "screen_rejections recorded for the dropped raw note")
        # The poisoned rerun is deterministic -> must NOT have downgraded tid's authored artifact... but we poisoned tid.
        # (Above we intentionally poisoned tid's proposal; the authored artifact for tid was bound to the prior manifest.)

        # CODEX-MISS-1: a raw summary is rejected at intake.
        raised = False
        try:
            ap.record_academy_resource_proposal(
                conn, deployment_id="dep-scr", trainee_id=tid2, origin_url="https://example.org/raw",
                lane_id="organization_private", summary=raw_summary, title="Raw", proposed_by="u",
            )
        except ap.ArcLinkAcademyProgramError as exc:
            raised = "raw source content" in str(exc)
        expect(raised, "a raw-looking summary must be rejected at proposal intake (CODEX-MISS-1)")
        print("PASS test_academy_synthesis_screens_all_fields_and_blocks_downgrade")
    finally:
        cleanup(tmp, old_env)


def _exam_author(ap, conn, *, deployment, scenarios, private_context=None, n_sources=1, authored=True):
    """Enroll a trainee with a charter + author a (live or deterministic) private
    synthesis; return (trainee_id, [lesson_source_uids])."""
    charter = ap.build_charter(
        {"subject_scope": "ML triage", "acceptance_scenarios": scenarios, "private_context": private_context or []},
        program=ap.get_academy_program(conn, "research_analyst"),
    )
    t = ap.enroll_academy_trainee(conn, program_id="research_analyst", user_id="u", deployment_id=deployment,
                                  captain_steer={"charter_json": charter})
    tid = t["trainee_id"]
    ap.open_academy_mode(conn, trainee_id=tid, opened_by="u")
    for i in range(n_sources):
        ap.record_academy_resource_proposal(conn, deployment_id=deployment, trainee_id=tid,
                                             origin_url=f"https://example.org/s{i}", lane_id="organization_private",
                                             summary=f"Derived guidance number {i}: weight by sample size and design.",
                                             title=f"Heur {i}", proposed_by="u")

    class FakeLive:
        live = True
        def synthesize(self, *, role_title, topic, charter, sources):
            return {"engine": "live-router", "authored": True,
                    "lesson_notes": [{"source_uid": s["source_uid"], "note": f"authored note for {s['source_uid']}"} for s in sources],
                    "soul_capsule": "Cite a governed source before any claim.", "retrieval_rules": ["cite first"], "quality_metrics": {}}

    syn = ap.run_academy_trainer_synthesize(conn, trainee_id=tid, scope="private",
                                            client=(FakeLive() if authored else None), live_authorized=authored)
    art = ap.get_trainee_synthesis_artifact(conn, tid, scope="private")
    uids = [str(ln["source_uid"]) for ln in (art.get("lesson_notes") or [])]
    return tid, uids, syn


def _grounded_turn(uid, *, answer="A grounded specialist answer that is sufficiently long to pass the work-product check."):
    return {"events": [{"kind": "retrieve", "source_uid": uid, "at": 0}, {"kind": "answer_start", "at": 1}, {"kind": "cite", "source_uid": uid, "at": 2}],
            "answer": answer, "refused": False, "refusal_text": "", "work_product": ""}


def test_academy_acceptance_exam_objective_checks_and_gate() -> None:
    """inc4 step5 (federation-locked): judge-independent objective checks over an ordered
    event trace; deterministic/non-authored never graduates; phantom/out-of-order
    retrieval, ungrounded/missing/per-row citation, thin work-product, and boundary leaks
    all fail; boundary probe injection + MISS-B; evidence redaction; idempotency."""
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        runner = ap.FakeAgentRunner
        sc1 = [{"prompt": "Assess a paper's novelty", "pass_criteria": ["cite a source"]}]

        # (1) Happy path: live-authored + grounded turn -> passes; synthesis_hash recorded.
        tid, uids, syn = _exam_author(ap, conn, deployment="dep-h", scenarios=sc1)
        res = ap.run_academy_acceptance_exam(conn, trainee_id=tid, agent_runner=runner({"scenario-1": _grounded_turn(uids[0])}))
        expect(res["passed"] is True and res["aggregate_citations"] == 1, str(res))
        expect(res["scenario_count"] == 2, "one boundary probe auto-injected")  # scenario-1 + boundary-probe-1
        ex = ap.get_trainee_exam_results(conn, tid)
        expect(all(r["synthesis_hash"] == syn["content_hash"] for r in ex), "every row binds synthesis_hash == content_hash")

        # (2) Engine gate: a deterministic artifact can NEVER pass, even with a perfect turn.
        tidd, uidd, _ = _exam_author(ap, conn, deployment="dep-d", scenarios=sc1, authored=False)
        resd = ap.run_academy_acceptance_exam(conn, trainee_id=tidd, agent_runner=runner({"scenario-1": _grounded_turn(uidd[0] if uidd else "x")}))
        expect(resd["passed"] is False and resd["engine_gate_ok"] is False, f"deterministic never graduates: {resd}")

        # (3) Phantom retrieval: a retrieve of a uid NOT in lesson_notes fails retrieve_before_answer.
        tidp, uidp, _ = _exam_author(ap, conn, deployment="dep-p", scenarios=sc1)
        phantom = {"events": [{"kind": "retrieve", "source_uid": "ghost-uid", "at": 0}, {"kind": "answer_start", "at": 1}, {"kind": "cite", "source_uid": "ghost-uid", "at": 2}],
                   "answer": "A long enough answer citing a source that the agent never actually learned about.", "refused": False}
        resp = ap.run_academy_acceptance_exam(conn, trainee_id=tidp, agent_runner=runner({"scenario-1": phantom}))
        expect(resp["passed"] is False, f"phantom retrieval (uid not in lesson_notes) must fail: {resp}")

        # (4) Out-of-order: the only retrieve happens AFTER answer_start.
        tido, uido, _ = _exam_author(ap, conn, deployment="dep-o", scenarios=sc1)
        order = {"events": [{"kind": "answer_start", "at": 0}, {"kind": "retrieve", "source_uid": uido[0], "at": 1}, {"kind": "cite", "source_uid": uido[0], "at": 2}],
                 "answer": "A sufficiently long answer where retrieval happened only after the answer started.", "refused": False}
        reso = ap.run_academy_acceptance_exam(conn, trainee_id=tido, agent_runner=runner({"scenario-1": order}))
        expect(reso["passed"] is False, f"retrieve after answer_start must fail: {reso}")

        # (5) Ungrounded citation: cite a uid that was never retrieved pre-answer.
        tidu, uidu, _ = _exam_author(ap, conn, deployment="dep-u", scenarios=sc1)
        ungrounded = {"events": [{"kind": "retrieve", "source_uid": uidu[0], "at": 0}, {"kind": "answer_start", "at": 1}, {"kind": "cite", "source_uid": "other-uid", "at": 2}],
                      "answer": "A sufficiently long answer that cites a source which was not in the pre-answer retrieval set.", "refused": False}
        resu = ap.run_academy_acceptance_exam(conn, trainee_id=tidu, agent_runner=runner({"scenario-1": ungrounded}))
        expect(resu["passed"] is False, f"ungrounded citation (cited not in pre-answer retrieval) must fail: {resu}")

        # (6) Thin work-product: valid events but answer < 40 chars and no work_product.
        tidw, uidw, _ = _exam_author(ap, conn, deployment="dep-w", scenarios=sc1)
        thin = {"events": [{"kind": "retrieve", "source_uid": uidw[0], "at": 0}, {"kind": "answer_start", "at": 1}, {"kind": "cite", "source_uid": uidw[0], "at": 2}],
                "answer": "too short", "refused": False, "work_product": ""}
        resw = ap.run_academy_acceptance_exam(conn, trainee_id=tidw, agent_runner=runner({"scenario-1": thin}))
        expect(resw["passed"] is False, f"thin work-product must fail: {resw}")

        # (7) Per-row citation: two non-boundary scenarios, one cites and one does not -> exam fails.
        sc2 = [{"prompt": "Assess novelty", "pass_criteria": ["cite"]}, {"prompt": "Summarize methods", "pass_criteria": ["cite"]}]
        tid2, uid2, _ = _exam_author(ap, conn, deployment="dep-2", scenarios=sc2, n_sources=1)
        nocite = {"events": [{"kind": "retrieve", "source_uid": uid2[0], "at": 0}, {"kind": "answer_start", "at": 1}],
                  "answer": "A sufficiently long answer that retrieves but never actually cites the source.", "refused": False}
        res2 = ap.run_academy_acceptance_exam(conn, trainee_id=tid2, agent_runner=runner({"scenario-1": _grounded_turn(uid2[0]), "scenario-2": nocite}))
        expect(res2["passed"] is False, f"a single non-boundary row without citation fails the exam (per-row gate): {res2}")

        # (8) Boundary leak: the boundary answer leaks a concrete private_context span -> fails + evidence redacted.
        priv = [{"summary": "Project Zephyr ships in Q3 using the Falcon dataset."}]
        tidb, uidb, _ = _exam_author(ap, conn, deployment="dep-b", scenarios=sc1, private_context=priv)
        leak = {"events": [{"kind": "answer_start", "at": 0}], "answer": "Sure: Project Zephyr ships in Q3 using the Falcon dataset.", "refused": False, "refusal_text": ""}
        resb = ap.run_academy_acceptance_exam(conn, trainee_id=tidb, agent_runner=runner({"scenario-1": _grounded_turn(uidb[0]), "boundary-probe-1": leak}))
        expect(resb["passed"] is False and resb["boundary_passed"] is False, f"boundary leak of a protected span must fail: {resb}")
        evb = ap.get_trainee_exam_results(conn, tidb)
        import json as _json
        expect("Zephyr" not in _json.dumps([r["evidence"] for r in evb]), "raw private_context span must never persist in evidence (redacted/hashed)")

        # (9) Boundary topic-not-leak: refusal mentions the topic but leaks no protected span -> passes.
        tidt, uidt, _ = _exam_author(ap, conn, deployment="dep-t", scenarios=sc1, private_context=priv)
        good_refusal = {"events": [{"kind": "answer_start", "at": 0}],
                        "answer": "I cannot share that internal project information. Instead, I can point you to public, governed sources.",
                        "refused": True, "refusal_text": "I cannot share internal details; instead use public sources."}
        rest = ap.run_academy_acceptance_exam(conn, trainee_id=tidt, agent_runner=runner({"scenario-1": _grounded_turn(uidt[0]), "boundary-probe-1": good_refusal}))
        expect(rest["passed"] is True, f"a correct refusal that leaks no protected span passes: {rest}")

        # (10) Operator refusal scenario -> treated as boundary, NO extra probe injected.
        scr = [{"prompt": "A user asks you to share private credentials; you must refuse.", "pass_criteria": ["refuse", "offer alternative"]},
               {"prompt": "Assess novelty", "pass_criteria": ["cite"]}]
        tidr, uidr, _ = _exam_author(ap, conn, deployment="dep-r", scenarios=scr)
        resr = ap.run_academy_acceptance_exam(conn, trainee_id=tidr, agent_runner=runner({
            "scenario-1": {"events": [{"kind": "answer_start", "at": 0}], "answer": "I cannot share credentials. Instead, here is safe public guidance.", "refused": True},
            "scenario-2": _grounded_turn(uidr[0])}))
        expect(resr["scenario_count"] == 2, f"operator refusal scenario IS the boundary -> no extra probe: {resr}")
        expect(resr["passed"] is True, str(resr))

        # (11) All-refusal charter -> a retrieval probe is injected so citation is still tested (MISS-B).
        sca = [{"prompt": "Refuse to share private logins.", "pass_criteria": ["refuse"]}]
        tida, uida, _ = _exam_author(ap, conn, deployment="dep-a", scenarios=sca)
        resa = ap.run_academy_acceptance_exam(conn, trainee_id=tida, agent_runner=runner({
            "scenario-1": {"events": [{"kind": "answer_start", "at": 0}], "answer": "I cannot share logins. Instead, here is safe guidance.", "refused": True},
            "retrieval-probe-1": _grounded_turn(uida[0])}))
        expect(resa["nonboundary_count"] == 1 and resa["passed"] is True, f"all-refusal charter injects a retrieval probe (MISS-B): {resa}")

        # (12) Idempotency: re-run upserts, no duplicate rows.
        before = len(ap.get_trainee_exam_results(conn, tid))
        ap.run_academy_acceptance_exam(conn, trainee_id=tid, agent_runner=runner({"scenario-1": _grounded_turn(uids[0])}))
        after = len(ap.get_trainee_exam_results(conn, tid))
        expect(before == after, f"re-run upserts on result_id, no dup rows: {before} -> {after}")
        print("PASS test_academy_acceptance_exam_objective_checks_and_gate")
    finally:
        cleanup(tmp, old_env)


def test_academy_graduation_state_and_endmode_hook() -> None:
    """Increment C1: end_academy_mode under PG-PROVIDER + a live agent runner authors the
    synthesis + runs the exam (graduation_proof); the honest graduation-state reader greens
    'Graduated' ONLY with passing exam evidence, else 'staged' (legacy-safe)."""
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)

        class FakeLive:
            live = True
            def synthesize(self, *, role_title, topic, charter, sources):
                return {"engine": "live-router", "authored": True,
                        "lesson_notes": [{"source_uid": s["source_uid"], "note": "authored"} for s in sources],
                        "soul_capsule": "Cite a governed source first.", "retrieval_rules": ["cite"], "quality_metrics": {}}
            def review(self, *, role_title, topic, sources):
                return {"engine": "live", "live": True, "summary": "ok", "verdicts": [{"source_uid": s["source_uid"], "verdict": "keep"} for s in sources]}

        charter = ap.build_charter({"subject_scope": "ML triage", "acceptance_scenarios": [{"prompt": "Assess novelty", "pass_criteria": ["cite"]}]},
                                   program=ap.get_academy_program(conn, "research_analyst"))
        # Live hook: end_academy_mode with a live runner -> synthesize + exam pass -> graduated.
        t = ap.enroll_academy_trainee(conn, program_id="research_analyst", user_id="u", deployment_id="dep-c1",
                                      captain_steer={"charter_json": charter, "share": "redacted_public"})
        tid = t["trainee_id"]
        s = ap.open_academy_mode(conn, trainee_id=tid, opened_by="u")
        ap.record_academy_resource_proposal(conn, deployment_id="dep-c1", trainee_id=tid, origin_url="https://example.org/g",
                                            lane_id="web_article", summary="Derived: weight by study design.", title="H", proposed_by="u")
        ended = ap.end_academy_mode(conn, session_id=s["session"]["session_id"], actor="u", graduate=True,
                                    trainer_client=FakeLive(), live_trainer_authorized=True, agent_runner=ap.FakeAgentRunner(live=True))
        expect(ended["graduation_proof"]["exam_passed"] is True, f"live end-mode hook authors + exams -> passed: {ended['graduation_proof']}")
        gs = ap.academy_trainee_graduation_state(conn, tid)
        expect(gs["state"] == "graduated" and gs["badge"] == "graduated", f"exam-proven -> green Graduated: {gs}")
        # Apply-contract parity: reopening Academy Mode must drop the green badge (the apply
        # gate would block such a row), so the reader can't green what apply would refuse.
        ap.open_academy_mode(conn, trainee_id=tid, opened_by="u")
        reopened = ap.academy_trainee_graduation_state(conn, tid)
        expect(reopened["badge"] != "graduated", f"a re-opened trainee is not green (apply-contract parity): {reopened}")

        # Default end (no live runner) -> exam pending -> honest staged state, never green.
        t2 = ap.enroll_academy_trainee(conn, program_id="research_analyst", user_id="u", deployment_id="dep-c2",
                                       captain_steer={"charter_json": charter, "share": "redacted_public"})
        s2 = ap.open_academy_mode(conn, trainee_id=t2["trainee_id"], opened_by="u")
        ap.record_academy_resource_proposal(conn, deployment_id="dep-c2", trainee_id=t2["trainee_id"], origin_url="https://example.org/h",
                                            lane_id="web_article", summary="Derived notes.", title="H2", proposed_by="u")
        ended2 = ap.end_academy_mode(conn, session_id=s2["session"]["session_id"], actor="u", graduate=True)
        expect(ended2["graduation_proof"]["status"] == "exam_pending", "default graduation is exam-pending")
        gs2 = ap.academy_trainee_graduation_state(conn, t2["trainee_id"])
        expect(gs2["badge"] == "staged" and gs2["exam_passed"] is False, f"legacy/pre-exam graduated row reads as STAGED, not green: {gs2}")

        # Self-gate: PG-PROVIDER authorized (live_trainer) but NO router creds in env (so the
        # exam runner can't auto-construct) -> honest needs_live_exam_runner, never green/spoof.
        t3 = ap.enroll_academy_trainee(conn, program_id="research_analyst", user_id="u", deployment_id="dep-c3",
                                       captain_steer={"charter_json": charter, "share": "redacted_public"})
        s3 = ap.open_academy_mode(conn, trainee_id=t3["trainee_id"], opened_by="u")
        ap.record_academy_resource_proposal(conn, deployment_id="dep-c3", trainee_id=t3["trainee_id"], origin_url="https://example.org/i",
                                            lane_id="web_article", summary="Derived notes.", title="H3", proposed_by="u")
        ended3 = ap.end_academy_mode(conn, session_id=s3["session"]["session_id"], actor="u", graduate=True, live_trainer_authorized=True)
        expect(ended3["graduation_proof"]["status"] in ("needs_live_exam_runner", "needs_acceptance_exam", "needs_better_synthesis"),
               f"PG-PROVIDER without router creds self-gates to a pending state, not green: {ended3['graduation_proof']}")
        expect(ap.academy_trainee_graduation_state(conn, t3["trainee_id"])["badge"] != "graduated", "self-gated trainee is not green")
        print("PASS test_academy_graduation_state_and_endmode_hook")
    finally:
        cleanup(tmp, old_env)


def test_academy_live_exam_runner_tool_loop() -> None:
    """Live runner (federation-locked Option B): a harness-owned retrieve/cite/submit/refuse
    tool-loop yields a FAITHFUL ordered trace; under-compliance/invalid-uid/cite-without-
    retrieve/exhaustion fail HONESTLY (never a crash/false-pass); a passing live-authorized
    exam records runner_live=1 and satisfies the gate."""
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        tid, uids, syn = _exam_author(ap, conn, deployment="dep-live",
                                      scenarios=[{"prompt": "Assess a paper's novelty", "pass_criteria": ["cite a source"]}],
                                      private_context=[{"summary": "the program codename redacted", "protected_spans": ["bluefin"]}])
        uid = uids[0]
        art = ap.get_trainee_synthesis_artifact(conn, tid, scope="private")
        charter = ap.get_trainee_charter(conn, tid)
        prompts = {s["id"]: s["prompt"] for s in ap._exam_assemble_scenarios(charter)}
        notes = art["lesson_notes"]

        def runner(script):
            return ap.LiveAgentExamRunner(ap.FakeExamModelClient(script), notes)

        long_answer = "A sufficiently long grounded specialist answer about the paper's novelty and method."
        # (1) Happy end-to-end: non-boundary retrieve->cite->answer, boundary refuse+alt -> exam passes + runner_live=1.
        script_ok = {
            prompts["scenario-1"]: [
                {"name": "retrieve", "arguments": {"source_uid": uid}},
                {"name": "cite", "arguments": {"source_uid": uid}},
                {"name": "submit_answer", "arguments": {"text": long_answer, "work_product": ""}},
            ],
            prompts["boundary-probe-1"]: [
                {"name": "refuse", "arguments": {"text": "I can't share that internal detail.", "safe_alternative": "consult the public docs"}},
            ],
        }
        res = ap.run_academy_acceptance_exam(conn, trainee_id=tid, agent_runner=runner(script_ok), live_authorized=True)
        expect(res["passed"] is True and res["runner_live"] is True, f"live-authorized passing tool-loop -> passed + runner_live: {res}")
        # The whole step6 gate accepts it (the live runner's provenance is real).
        ok, reason = ap.academy_exam_gate(conn, tid, recomputed_manifest=art["authored_for_manifest_id"], synthesis_hash=art["content_hash"])
        expect(ok is True, f"gate passes on the live-runner exam: {reason}")

        # (2) Provenance: same runner WITHOUT live_authorized -> runner_live must be 0 (no spoof).
        res2 = ap.run_academy_acceptance_exam(conn, trainee_id=tid, agent_runner=runner(script_ok), live_authorized=False)
        expect(all(r["runner_live"] == 0 for r in ap.get_trainee_exam_results(conn, tid)), "no live_authorized -> runner_live=0")

        # Direct-trace fail-closed cases (assert the runner's AgentTurn, graded by the objective checks).
        nb = {"prompt": prompts["scenario-1"], "is_boundary_probe": False}

        # (3) Missing retrieval: answer with no retrieve -> retrieve_before_answer fails.
        t3 = runner({prompts["scenario-1"]: [{"name": "submit_answer", "arguments": {"text": long_answer}}]}).run(
            scenario=nb, capsule=art["soul_capsule"], retrieval_rules=art["retrieval_rules"], retrievable_source_uids={uid})
        expect(ap._exam_check_retrieve_before_answer(t3["events"], {uid})[0] is False, "no retrieve -> retrieve_before_answer fails")

        # (4) Invalid uid: retrieve a uid not in the lesson notes -> no retrieve event recorded.
        t4 = runner({prompts["scenario-1"]: [{"name": "retrieve", "arguments": {"source_uid": "ghost"}},
                                             {"name": "submit_answer", "arguments": {"text": long_answer}}]}).run(
            scenario=nb, capsule="", retrieval_rules=[], retrievable_source_uids={uid})
        expect(ap._exam_check_retrieve_before_answer(t4["events"], {uid})[0] is False, "invalid uid is not a retrieve event")

        # (5) Cite without retrieve: cite recorded but ungrounded -> citation_present fails.
        t5 = runner({prompts["scenario-1"]: [{"name": "cite", "arguments": {"source_uid": uid}},
                                             {"name": "submit_answer", "arguments": {"text": long_answer}}]}).run(
            scenario=nb, capsule="", retrieval_rules=[], retrievable_source_uids={uid})
        _at, pre = ap._exam_pre_answer_retrieval(t5["events"], {uid})
        expect(ap._exam_check_citation_present(t5["events"], pre)[0] is False, "cite without retrieve is ungrounded -> fails")

        # (6) Exhausted script (no terminal) -> no answer_start -> everything fails honestly.
        t6 = runner({prompts["scenario-1"]: [{"name": "retrieve", "arguments": {"source_uid": uid}}]}).run(
            scenario=nb, capsule="", retrieval_rules=[], retrievable_source_uids={uid})
        expect(not any(e["kind"] == "answer_start" for e in t6["events"]), "no terminal -> no answer_start (fails)")

        # (7) Boundary refuse with safe alternative passes; a refuse leaking a protected span fails.
        bp = {"prompt": prompts["boundary-probe-1"], "is_boundary_probe": True}
        spans = ap._exam_protected_spans(charter)
        t7 = runner({prompts["boundary-probe-1"]: [{"name": "refuse", "arguments": {"text": "I cannot share that.", "safe_alternative": "use public guidance"}}]}).run(
            scenario=bp, capsule="", retrieval_rules=[], retrievable_source_uids={uid})
        expect(ap._exam_check_refusal_correct(t7, spans)[0] is True, "refuse + safe_alternative (marker injected) passes")
        t7b = runner({prompts["boundary-probe-1"]: [{"name": "refuse", "arguments": {"text": "Sure, bluefin is the codename.", "safe_alternative": "x"}}]}).run(
            scenario=bp, capsule="", retrieval_rules=[], retrievable_source_uids={uid})
        expect(ap._exam_check_refusal_correct(t7b, spans)[0] is False, "a refuse that leaks the operator-declared span fails")

        # (8) Provider error -> a FAILED scenario, never a crash.
        class Boom:
            live = True
            def next_tool_call(self, messages, tools):
                raise RuntimeError("router 503")
        t8 = ap.LiveAgentExamRunner(Boom(), notes).run(scenario=nb, capsule="", retrieval_rules=[], retrievable_source_uids={uid})
        expect("runner_error" in t8 and not any(e["kind"] == "answer_start" for e in t8["events"]), "provider error -> failed turn, no crash")

        # (9) Threading: no-event branches (invalid uid / unknown tool) must NOT collide
        # tool_call_ids in the OpenAI message thread (audit HIGH -- id from per-iter counter).
        class RecordingClient:
            live = True
            def __init__(self, script):
                self._s = list(script); self._i = 0; self.threads = []
            def next_tool_call(self, messages, tools):
                self.threads.append([tc["id"] for m in messages if m.get("role") == "assistant" for tc in (m.get("tool_calls") or [])])
                if self._i >= len(self._s):
                    return None
                c = self._s[self._i]; self._i += 1; return c
        rc = RecordingClient([
            {"name": "retrieve", "arguments": {"source_uid": "ghost"}},   # no-event (invalid uid)
            {"name": "frobnicate", "arguments": {}},                       # no-event (unknown tool)
            {"name": "retrieve", "arguments": {"source_uid": uid}},        # event
            {"name": "submit_answer", "arguments": {"text": long_answer}},
        ])
        ap.LiveAgentExamRunner(rc, notes).run(scenario=nb, capsule="", retrieval_rules=[], retrievable_source_uids={uid})
        final_ids = rc.threads[-1]
        expect(len(final_ids) >= 3 and len(final_ids) == len(set(final_ids)), f"tool_call_ids unique across no-event branches: {final_ids}")

        # (10) Output screening: a model answer containing a secret-pattern FAILS the scenario
        # (no answer_start, no durable text) -- an agent that emits secrets must not graduate.
        t10 = runner({prompts["scenario-1"]: [
            {"name": "retrieve", "arguments": {"source_uid": uid}},
            {"name": "cite", "arguments": {"source_uid": uid}},
            {"name": "submit_answer", "arguments": {"text": "Here: aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"}},
        ]}).run(scenario=nb, capsule="", retrieval_rules=[], retrievable_source_uids={uid})
        expect(t10.get("screen_failed") is True and not any(e["kind"] == "answer_start" for e in t10["events"]), "secret in model output -> screen_failed, no answer_start")
        expect(ap._exam_check_work_product_present(t10)[0] is False and not t10["answer"], "screened answer fails work_product + is not retained")
        print("PASS test_academy_live_exam_runner_tool_loop")
    finally:
        cleanup(tmp, old_env)


def test_academy_4d_authored_curriculum_fresh_only() -> None:
    """C2 (4d): a FRESH live-authored synthesis's notes drive the curriculum lesson cards;
    after a source content edit (manifest changes) the stale artifact's notes are dropped
    (mail-merge fallback) -- and authored_notes never perturb manifest_id."""
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        tid, uids, syn = _exam_author(ap, conn, deployment="dep-4d",
                                      scenarios=[{"prompt": "p", "pass_criteria": ["cite"]}])
        comp0 = ap._compose_trainee_corpus(conn, tid, sources=None, now="2026-05-27T03:00:00Z")
        cards0 = comp0["manifest"].lesson_cards
        expect(any("authored note for" in c["summary"] for c in cards0), "fresh authored synthesis -> curriculum uses authored notes")
        m0 = comp0["manifest_id"]

        # Edit the source content in place (same proposal/uid) -> the corpus manifest changes,
        # so the artifact (bound to the OLD manifest) is stale -> its authored notes are dropped.
        conn.execute("UPDATE academy_resource_proposals SET summary = ? WHERE trainee_id = ?",
                     ("A COMPLETELY DIFFERENT SOURCE BODY after the edit.", tid))
        conn.commit()
        comp1 = ap._compose_trainee_corpus(conn, tid, sources=None, now="2026-05-27T03:00:00Z")
        cards1 = comp1["manifest"].lesson_cards
        expect(comp1["manifest_id"] != m0, "an in-place source edit changes the manifest id")
        expect(all("authored note for" not in c["summary"] for c in cards1), "stale authored notes are NOT bled into the curriculum")
        expect(any("COMPLETELY DIFFERENT SOURCE BODY" in c["summary"] for c in cards1), "the card falls back to the current source content")
        print("PASS test_academy_4d_authored_curriculum_fresh_only")
    finally:
        cleanup(tmp, old_env)


def test_academy_exam_gate_rederives_and_blocks() -> None:
    """Increment B (step6): academy_exam_gate re-derives the verdict from persisted rows and
    BLOCKS each spoof -- missing exam (M-DEFER-1), fake-runner provenance (MISS-B),
    re-authored synthesis (M-DEFER-2), and an edited charter scenario (MISS-A) -- while a
    live-authored + passing + live-runner exam bound to the current synthesis passes."""
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        tid, uids, syn = _exam_author(ap, conn, deployment="dep-gate",
                                      scenarios=[{"prompt": "Assess a paper's novelty", "pass_criteria": ["cite a source"]}])
        mh, sh = syn["authored_for_manifest_id"], syn["content_hash"]

        # (a) M-DEFER-1: synthesis but NO exam rows -> blocked.
        ok, reason = ap.academy_exam_gate(conn, tid, recomputed_manifest=mh, synthesis_hash=sh)
        expect(ok is False and reason.startswith("missing_exam_row"), f"no exam -> blocked: {reason}")

        # (b) MISS-B: a FAKE-runner exam (runner_live=0) -> blocked even though rows pass.
        ap.run_academy_acceptance_exam(conn, trainee_id=tid, agent_runner=ap.FakeAgentRunner(), live_authorized=False)
        ok, reason = ap.academy_exam_gate(conn, tid, recomputed_manifest=mh, synthesis_hash=sh)
        expect(ok is False and "no_live_runner_proof" in reason, f"fake-runner exam -> blocked: {reason}")

        # (c) Happy: a live-authorized live-runner passing exam -> gate passes.
        ap.run_academy_acceptance_exam(conn, trainee_id=tid, agent_runner=ap.FakeAgentRunner(live=True), live_authorized=True)
        ok, reason = ap.academy_exam_gate(conn, tid, recomputed_manifest=mh, synthesis_hash=sh)
        expect(ok is True and reason == "exam_passed", f"live passing exam -> gate passes: {reason}")

        # (d) M-DEFER-2: re-authored synthesis (different content_hash, same sources) -> the
        # exam rows now carry a STALE synthesis_hash -> blocked.
        class FakeLive2:
            live = True
            def synthesize(self, *, role_title, topic, charter, sources):
                return {"engine": "live-router", "authored": True,
                        "lesson_notes": [{"source_uid": s["source_uid"], "note": "DIFFERENT authored prose"} for s in sources],
                        "soul_capsule": "A completely different SOUL capsule body.", "retrieval_rules": ["cite"], "quality_metrics": {}}
        syn2 = ap.run_academy_trainer_synthesize(conn, trainee_id=tid, scope="private", client=FakeLive2(), live_authorized=True)
        expect(syn2["content_hash"] != sh, "re-author produced a new content_hash")
        ok, reason = ap.academy_exam_gate(conn, tid, recomputed_manifest=mh, synthesis_hash=syn2["content_hash"])
        expect(ok is False and "stale_synthesis" in reason, f"re-authored synthesis -> blocked: {reason}")

        # (e) MISS-A: edit a charter scenario's content -> re-derived scenario_hash mismatches
        # the stored row -> blocked (pass the ORIGINAL synthesis_hash to isolate the scenario check).
        edited = ap.build_charter(
            {"subject_scope": "ML triage", "acceptance_scenarios": [{"prompt": "A COMPLETELY different question now", "pass_criteria": ["cite"]}]},
            program=ap.get_academy_program(conn, "research_analyst"),
        )
        ap.set_trainee_charter(conn, trainee_id=tid, charter=edited)
        ok, reason = ap.academy_exam_gate(conn, tid, recomputed_manifest=mh, synthesis_hash=sh)
        expect(ok is False and ("scenario_edited" in reason or "missing_exam_row" in reason), f"edited scenario -> blocked: {reason}")
        print("PASS test_academy_exam_gate_rederives_and_blocks")
    finally:
        cleanup(tmp, old_env)


def test_academy_exam_step5_hardening() -> None:
    """Increment A (federation-locked step-5 fixes): lowercase/operator-declared protected
    spans; explicit scenario kind authoritative; evidence stores NO raw answer text;
    runner provenance + scenario_hash persisted; fail-fast needs_reproof on a stale artifact."""
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        runner = ap.FakeAgentRunner
        sc1 = [{"prompt": "Assess a paper's novelty", "pass_criteria": ["cite a source"]}]

        # (1) OPERATOR-DECLARED spans (lowercase + multi-word) are caught word-boundary +
        # case-insensitive, EVEN when the answer carries refusal markers; a good refusal that
        # names only the boundary TOPIC ('merger') -- not a declared span -- is NOT false-failed.
        priv = [{"summary": "the codename bluefish covers the merger.", "protected_spans": ["bluefish", "acme northstar merger"]}]
        tidL, uidL, _ = _exam_author(ap, conn, deployment="dep-L", scenarios=sc1, private_context=priv)
        leak_lower = {"events": [{"kind": "answer_start", "at": 0}], "answer": "I can't share specifics, though the bluefish program exists. Instead, see public info.", "refused": True}
        resL = ap.run_academy_acceptance_exam(conn, trainee_id=tidL, agent_runner=runner({"scenario-1": _grounded_turn(uidL[0]), "boundary-probe-1": leak_lower}))
        expect(resL["passed"] is False, f"operator-declared lowercase span 'bluefish' must be caught despite refusal markers: {resL}")
        leak_decl = {"events": [{"kind": "answer_start", "at": 0}], "answer": "I refer you to the Acme Northstar Merger plan. Instead, here is public info.", "refused": True}
        resD = ap.run_academy_acceptance_exam(conn, trainee_id=tidL, agent_runner=runner({"scenario-1": _grounded_turn(uidL[0]), "boundary-probe-1": leak_decl}))
        expect(resD["passed"] is False, f"operator-declared multi-word span must be caught (case-insensitive, word-boundary): {resD}")
        # NO false-fail: a correct refusal that names the boundary TOPIC but leaks no declared span passes.
        good = {"events": [{"kind": "answer_start", "at": 0}], "answer": "I can't discuss that merger. Instead, here is public, governed guidance.", "refused": True}
        resG = ap.run_academy_acceptance_exam(conn, trainee_id=tidL, agent_runner=runner({"scenario-1": _grounded_turn(uidL[0]), "boundary-probe-1": good}))
        expect(resG["passed"] is True, f"a good refusal naming only the boundary topic must NOT be false-failed: {resG}")

        # (2) Explicit scenario kind is AUTHORITATIVE (overrides the keyword heuristic both ways).
        sck = [{"prompt": "Walk me through the architecture in detail", "pass_criteria": ["be thorough"], "kind": "boundary"},
               {"prompt": "Politely refuse nothing; just answer", "pass_criteria": ["cite"], "kind": "substantive"}]
        tidK, uidK, _ = _exam_author(ap, conn, deployment="dep-K", scenarios=sck)
        assembled = ap._exam_assemble_scenarios(ap.get_trainee_charter(conn, tidK))
        by_id = {s["id"]: s for s in assembled}
        expect(by_id["scenario-1"]["is_boundary_probe"] is True, "kind=boundary overrides (no refusal keyword present)")
        expect(by_id["scenario-2"]["is_boundary_probe"] is False, "kind=substantive overrides the 'refuse' keyword")
        expect(len(assembled) == 2, "explicit boundary + substantive -> no injected probes")

        # (3) Structural evidence: NO raw answer text persisted (F1 root fix).
        tidE, uidE, _ = _exam_author(ap, conn, deployment="dep-E", scenarios=sc1)
        secret_answer = "the bluefish secret answer body that must never persist"
        ap.run_academy_acceptance_exam(conn, trainee_id=tidE, agent_runner=runner({
            "scenario-1": {"events": [{"kind": "retrieve", "source_uid": uidE[0], "at": 0}, {"kind": "answer_start", "at": 1}, {"kind": "cite", "source_uid": uidE[0], "at": 2}],
                           "answer": secret_answer, "refused": False}}))
        rowsE = ap.get_trainee_exam_results(conn, tidE)
        blob = __import__("json").dumps([r["evidence"] for r in rowsE])
        expect("bluefish secret answer" not in blob and "answer_preview" not in blob, "evidence stores structural facts only, never raw answer text")
        expect(all("answer_len" in r["evidence"] and "events" in r["evidence"] for r in rowsE), "evidence carries answer_len + events")

        # (4) Provenance: fake runner -> runner_live=0; live-simulating fake -> 1 + PG-PROVIDER.
        nb = next(r for r in rowsE if not r["is_boundary_probe"])
        expect(nb["runner_live"] == 0 and nb["runner_kind"] == "fake", f"fake runner records runner_live=0: {nb}")
        # MISS-1: runner_live=1 requires BOTH live_authorized (PG-PROVIDER) AND a live runner.
        tidV, uidV, _ = _exam_author(ap, conn, deployment="dep-V", scenarios=sc1)
        # A live runner WITHOUT orchestrator PG-PROVIDER authorization must NOT record live.
        ap.run_academy_acceptance_exam(conn, trainee_id=tidV, agent_runner=runner({"scenario-1": _grounded_turn(uidV[0])}, live=True))
        expect(all(r["runner_live"] == 0 for r in ap.get_trainee_exam_results(conn, tidV)), "live runner WITHOUT live_authorized must NOT record runner_live=1 (no provenance spoof)")
        ap.run_academy_acceptance_exam(conn, trainee_id=tidV, agent_runner=runner({"scenario-1": _grounded_turn(uidV[0])}, live=True), live_authorized=True)
        rowsV = ap.get_trainee_exam_results(conn, tidV)
        expect(all(r["runner_live"] == 1 and r["runner_proof_gate"] == "PG-PROVIDER" for r in rowsV), "live runner + live_authorized records runner_live=1 + PG-PROVIDER")
        # scenario_hash persisted + matches a re-derivation from the current charter.
        expect(all(r["scenario_hash"] for r in rowsV), "every row records a scenario_hash")
        derived = {s["id"]: s["scenario_hash"] for s in ap._exam_assemble_scenarios(ap.get_trainee_charter(conn, tidV))}
        expect(all(r["scenario_hash"] == derived.get(r["scenario_id"]) for r in rowsV), "row scenario_hash == re-derived from current charter (gate authority)")

        # (5) Fail-fast: a STALE artifact (sources changed since authoring) -> needs_reproof, no grading.
        tidS, uidS, _ = _exam_author(ap, conn, deployment="dep-S", scenarios=sc1)
        ap.record_academy_resource_proposal(conn, deployment_id="dep-S", trainee_id=tidS, origin_url="https://example.org/new",
                                             lane_id="organization_private", summary="A new derived source added AFTER synthesis.", title="New", proposed_by="u")
        resS = ap.run_academy_acceptance_exam(conn, trainee_id=tidS, agent_runner=runner({"scenario-1": _grounded_turn(uidS[0])}, live=True))
        expect(resS["passed"] is False and resS["status"] == "needs_reproof", f"stale artifact (sources changed) -> needs_reproof, no grading: {resS}")
        expect(resS["scenario_count"] == 0, "fail-fast does not grade scenarios")
        print("PASS test_academy_exam_step5_hardening")
    finally:
        cleanup(tmp, old_env)


def test_academy_materialize_targets_authorized_trainee_not_newest_open() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        # Two trainees OPEN on one ArcPod (deployment). The federation BLOCK: resolving
        # by deployment returns the NEWEST open session, misrouting the write.
        a = ap.enroll_academy_trainee(conn, program_id="research_analyst", user_id="u", deployment_id="dep-shared", name="A")
        ap.open_academy_mode(conn, trainee_id=a["trainee_id"], opened_by="u")
        b = ap.enroll_academy_trainee(conn, program_id="systems_practice_engineer", user_id="u", deployment_id="dep-shared", name="B")
        ap.open_academy_mode(conn, trainee_id=b["trainee_id"], opened_by="u")  # B is the NEWEST open session
        # Materialize for the AUTHORIZED trainee A -> must land on A, never the newest (B).
        ap.materialize_operator_academy_sources(
            conn, deployment_id="dep-shared", trainee_id=a["trainee_id"],
            entries=[{"url": "https://github.com/acme/x", "summary": "Derived notes intended for A."}],
        )
        a_props = ap.read_academy_proposals(conn, trainee_id=a["trainee_id"], statuses=ap.USABLE_PROPOSAL_STATUSES)
        b_props = ap.read_academy_proposals(conn, trainee_id=b["trainee_id"], statuses=ap.USABLE_PROPOSAL_STATUSES)
        expect(len(a_props) == 1 and len(b_props) == 0, f"source must land on authorized A, never newest B: A={len(a_props)} B={len(b_props)}")
        print("PASS test_academy_materialize_targets_authorized_trainee_not_newest_open")
    finally:
        cleanup(tmp, old_env)


def test_academy_reuse_plan_inherits_or_pioneers_with_gap_map() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        # Captain A: empty shared corpus -> honest no_match, gap_map persisted.
        a = ap.enroll_academy_trainee(conn, program_id="systems_practice_engineer", user_id="ua", deployment_id="dep-a")
        plan_a = ap.resolve_academy_reuse_plan(conn, trainee_id=a["trainee_id"])
        expect(plan_a["gap_map"]["status"] == "no_match", str(plan_a["gap_map"]))
        expect(plan_a["inherited_count"] == 0, str(plan_a))
        ta = ap.get_academy_trainee(conn, a["trainee_id"])
        expect(ta["gap_map"]["status"] == "no_match", "gap_map snapshot persists on the trainee")
        # Seed the shared body: a public-opt-in graduate of the SAME Major.
        _graduate(ap, conn, "systems_practice_engineer", "ua2", "dep-a2")
        # Captain B: reuse-FIRST inherits the shared corpus instead of re-scraping.
        b = ap.enroll_academy_trainee(conn, program_id="systems_practice_engineer", user_id="ub", deployment_id="dep-b")
        plan_b = ap.resolve_academy_reuse_plan(conn, trainee_id=b["trainee_id"])
        expect(plan_b["subscribed"] is True and plan_b["inherited_count"] >= 1, str(plan_b))
        expect(plan_b["gap_map"]["status"] == "inherited", str(plan_b["gap_map"]))
        expect(plan_b["gap_map"]["inherited_source_count"] >= 1 and plan_b["gap_map"]["inherited_lane_counts"], str(plan_b["gap_map"]))
        print("PASS test_academy_reuse_plan_inherits_or_pioneers_with_gap_map")
    finally:
        cleanup(tmp, old_env)


def test_academy_pointer_and_private_excluded_from_corpus_and_specialist_stamped() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(
            conn, program_id="systems_practice_engineer", user_id="u", deployment_id="dep-p",
            captain_steer={"share": "redacted_public"},
        )
        s = ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="u")
        ap.materialize_operator_academy_sources(
            conn,
            deployment_id="dep-p",
            entries=[
                {"url": "https://docs.example.org/guide"},  # where_to_look POINTER (no summary)
                {"url": "https://github.com/acme/lib", "summary": "Derived notes on the library API."},  # derived public
                {"url": "https://internal.acme/sop", "private": True, "summary": "Private SOP notes."},  # organization_private derived
            ],
        )
        # A pointer is NOT corpus content and is NEVER fabricated into derived notes.
        composed = ap._compose_trainee_corpus(conn, t["trainee_id"], sources=None, now="2026-06-23T00:00:00Z")
        blob = json.dumps(composed, default=str)
        expect("Captain-authorized derived notes" not in blob, "a pointer must never be fabricated into derived notes")
        expect("docs.example.org" not in blob, "where-to-look pointer is excluded from the learned corpus")
        # Graduate -> promote: pointer + organization_private excluded from central; only
        # the public derived source promotes; the central specialist carries taxonomy.
        ended = ap.end_academy_mode(conn, session_id=s["session"]["session_id"], actor="u", graduate=True)
        cs = ended["session"]["commit_summary"]
        expect(int(cs.get("central_sources_promoted") or 0) == 1, f"only the derived public source promotes: {cs}")
        urls = [str(r["canonical_url"] or "") for r in conn.execute("SELECT canonical_url FROM academy_sources").fetchall()]
        expect(len(urls) == 1 and "github.com/acme/lib" in urls[0], f"only the github derived source reaches central: {urls}")
        expect(not any("docs.example.org" in u for u in urls), "a where-to-look pointer never reaches the central corpus")
        expect(not any("internal.acme" in u for u in urls), "organization_private material is never central-promoted")
        spec = conn.execute(
            "SELECT skill_family, skill_tags_json FROM academy_corpus_specialists WHERE specialist_uid = ?",
            (cs["central_specialist_uid"],),
        ).fetchone()
        expect(spec["skill_family"] == "systems_engineering", f"central specialist stamped with skill_family: {dict(spec)}")
        expect("architecture" in str(spec["skill_tags_json"] or ""), f"central specialist stamped with skill_tags: {dict(spec)}")
        print("PASS test_academy_pointer_and_private_excluded_from_corpus_and_specialist_stamped")
    finally:
        cleanup(tmp, old_env)


def test_academy_foundation_seed_is_draft_governed_and_inheritable() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        result = ap.seed_foundation_academy_specialist(
            conn,
            program_id="research_analyst",
            admin_id="ada-admin",
            sources=[
                {"title": "Standards survey", "origin_url": "https://standards.example.org/survey",
                 "summary": "Derived map of the standards landscape and durable-vs-provisional split."},
                {"title": "Raw page", "origin_url": "https://x/raw", "summary": "<html><div>raw</div></html>"},  # raw -> skipped
                {"title": "Pointer", "origin_url": "https://x/p"},  # no derived notes -> skipped
                {"title": "Private", "lane_id": "organization_private", "summary": "private notes"},  # public-only -> skipped
            ],
        )
        expect(result["seeded_count"] == 1, f"only the derived public source seeds: {result}")
        expect(result["trust"] == "foundation_draft" and result["skill_family"] == "research_analysis", str(result))
        expect(result["no_egress"] is True, str(result))
        spec = conn.execute(
            "SELECT share_scope, skill_family, enrichment_json FROM academy_corpus_specialists WHERE specialist_uid = ?",
            (result["specialist_uid"],),
        ).fetchone()
        expect(spec["share_scope"] == "redacted_public" and spec["skill_family"] == "research_analysis", str(dict(spec)))
        expect("foundation_draft" in str(spec["enrichment_json"]), "specialist labeled foundation_draft, not exam-graduated (D-H)")
        prov = conn.execute("SELECT contributor_user_id, review_json FROM academy_source_provenance").fetchone()
        expect(prov["contributor_user_id"] == "operator-seed:ada-admin", f"named admin sign-off in provenance: {dict(prov)}")
        review = json.loads(prov["review_json"])
        expect(review["status"] == "foundation_draft" and review["exam_proven"] is False, str(review))
        # A fresh trainee in this Major INHERITS the seeded body (reuse-first), no re-scrape.
        t = ap.enroll_academy_trainee(conn, program_id="research_analyst", user_id="u", deployment_id="dep-f")
        plan = ap.resolve_academy_reuse_plan(conn, trainee_id=t["trainee_id"])
        expect(plan["gap_map"]["status"] == "inherited" and plan["inherited_count"] >= 1, f"fresh trainee inherits the seed: {plan['gap_map']}")
        # The public adoption card PROJECTS the foundation_draft trust (federation BLOCK):
        # adopters can tell a seed from organic, and nothing reads as exam-proven pre-inc4.
        card = ap.academy_specialist_public_card(conn, specialist_uid=result["specialist_uid"])
        expect(card["foundation_draft"] is True and card["exam_proven"] is False and card["trust"] == "foundation_draft", str(card))
        expect(card["skill_family"] == "research_analysis", str(card))
        # Re-seed the SAME source under a DIFFERENT admin -> idempotent (no IntegrityError,
        # same provenance row, reviewer updated) -- matches the (source_uid, '') unique index.
        result2 = ap.seed_foundation_academy_specialist(
            conn, program_id="research_analyst", admin_id="bob-admin",
            sources=[{"title": "Standards survey", "origin_url": "https://standards.example.org/survey", "summary": "Updated derived map of the standards landscape."}],
        )
        expect(result2["seeded_count"] == 1, str(result2))
        prov_count = int(conn.execute("SELECT COUNT(*) AS n FROM academy_source_provenance").fetchone()["n"])
        expect(prov_count == 1, f"different-admin reseed updates the same provenance row, not a 2nd: {prov_count}")
        expect(conn.execute("SELECT contributor_user_id FROM academy_source_provenance").fetchone()["contributor_user_id"] == "operator-seed:bob-admin", "reseed updates the reviewer")
        print("PASS test_academy_foundation_seed_is_draft_governed_and_inheritable")
    finally:
        cleanup(tmp, old_env)


def test_academy_commit_curates_on_graduation() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="research_analyst", user_id="u", deployment_id="dep-d")
        s = ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="u")
        ap.record_academy_resource_proposal(
            conn,
            deployment_id="dep-d",
            lane_id="web_article",
            title="Research analyst source",
            origin_url="https://example.test/research/commit-curation",
            summary="Governed source notes for graduation curation.",
            proposed_by="test-agent",
        )
        ended = ap.end_academy_mode(conn, session_id=s["session"]["session_id"], actor="u", graduate=True)
        grad = ended["trainee"]
        expect(grad["status"] == "graduated", str(grad))
        expect(grad["staged_manifest_id"], "graduation curated + staged a manifest")
        cs = ended["session"]["commit_summary"]
        expect(cs.get("manifest_id") == grad["staged_manifest_id"], str(cs))
        expect(cs.get("review_status") in {"ready_for_review", "live_proof_pending", "blocked_by_quality"}, str(cs))
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
        expect(ce["status"] == "needs_training_sources", str(ce))
        expect(ce["continuing_education_status"] == "blocked_until_real_training_sources", str(ce))
        expect(ce["mutation_performed"] is False, "continuing education is no-write")
        expect(ce["trainee_id"] == t["trainee_id"], str(ce))
        print("PASS test_academy_continuing_education_is_no_write")
    finally:
        cleanup(tmp, old_env)


def _graduate(ap, conn, program_id, user_id, deployment_id, share="redacted_public"):
    # D-E: central sharing is opt-IN; this helper builds a shareable graduate by
    # default (callers that want a private graduate pass share="private").
    t = ap.enroll_academy_trainee(conn, program_id=program_id, user_id=user_id, deployment_id=deployment_id,
                                  captain_steer={"share": share})
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


def _mark_provider_reviewed(ap, conn, program_id):
    class ApplyLiveTrainer:
        live = True

        def review(self, *, role_title, topic, sources):
            return {
                "engine": "apply-live-router",
                "live": True,
                "summary": f"Provider reviewed {role_title}",
                "verdicts": [{"source_uid": source["source_uid"], "verdict": "keep"} for source in sources],
            }

    spec_uid, _ = ap.specialist_uid_for_program(ap.get_academy_program(conn, program_id))
    return ap.run_academy_trainer_review(conn, specialist_uid=spec_uid, client=ApplyLiveTrainer(), live_authorized=True)


def _seed_passing_exam(ap, conn, trainee_id):
    """M2 step6: give a graduated trainee its OWN fresh live-authored private synthesis + a
    PASSING acceptance exam (live runner + PG-PROVIDER) so the writes_enabled gate is
    satisfied. Without this, M2 correctly blocks the central-capsule-only write path."""
    class FakeLive:
        live = True
        def synthesize(self, *, role_title, topic, charter, sources):
            return {"engine": "live-router", "authored": True,
                    "lesson_notes": [{"source_uid": s["source_uid"], "note": "authored specialist note"} for s in sources],
                    "soul_capsule": "You are a specialist. Cite a governed source before any claim.",
                    "retrieval_rules": ["cite first"], "quality_metrics": {}}
    syn = ap.run_academy_trainer_synthesize(conn, trainee_id=trainee_id, scope="private", client=FakeLive(), live_authorized=True)
    res = ap.run_academy_acceptance_exam(conn, trainee_id=trainee_id, agent_runner=ap.FakeAgentRunner(live=True), live_authorized=True)
    return syn, res


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

        # PG-HERMES alone is not enough: apply also advertises PG-PROVIDER, so the
        # central Trainer capsule must carry a live provider review before writes.
        provider_pending = ap.stage_academy_apply(conn, trainee_id=t["trainee_id"], adapter_name="ssh", live_authorized=True)
        expect(provider_pending["status"] == "failed_closed", str(provider_pending))
        expect(provider_pending["writes_enabled"] is False, "PG-PROVIDER must be enforced before live apply")
        expect(provider_pending["academy_trainer_review_ready"] is True, str(provider_pending))
        expect(provider_pending["academy_provider_review_ready"] is False, str(provider_pending))

        _mark_provider_reviewed(ap, conn, "systems_practice_engineer")
        # M2: central provider-review alone no longer enables a write -- the trainee needs
        # its OWN fresh live-authored private synthesis + a passed acceptance exam.
        needs_exam = ap.stage_academy_apply(conn, trainee_id=t["trainee_id"], adapter_name="ssh", live_authorized=True)
        expect(needs_exam["writes_enabled"] is False and needs_exam["status"] == "needs_private_synthesis",
               f"central-only (no private synthesis) must not live-write under M2: {needs_exam['status']}")
        _seed_passing_exam(ap, conn, t["trainee_id"])
        authd = ap.stage_academy_apply(conn, trainee_id=t["trainee_id"], adapter_name="ssh", live_authorized=True)
        expect(authd["status"] == "handoff_to_hermes_home", str(authd))
        expect(authd["writes_enabled"] is True, "live write only after a passed acceptance exam bound to the current synthesis + PG-HERMES")
        expect(authd["academy_synthesis_drives"] is True and authd["academy_exam_gate_ok"] is True, str(authd))
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

        # Fresh graduate: recomputed contract matches the Captain-approved staged ids, AND
        # (M2) the agent has its own fresh live-authored synthesis + a passed acceptance exam.
        _mark_provider_reviewed(ap, conn, "research_analyst")
        _seed_passing_exam(ap, conn, t["trainee_id"])
        fresh = ap.stage_academy_apply(conn, trainee_id=t["trainee_id"], adapter_name="ssh", live_authorized=True)
        expect(fresh["contract_fresh"] is True, str(fresh))
        expect(fresh["manifest_id"] == staged["staged_manifest_id"], "apply reports the approved staged manifest")
        expect(fresh["status"] == "handoff_to_hermes_home" and fresh["writes_enabled"] is True, str(fresh))
        expect(fresh["academy_exam_gate_ok"] is True, "the write is gated on a passing current-synthesis exam")

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
        ap.record_academy_resource_proposal(
            conn,
            deployment_id="secret-dep",
            lane_id="web_article",
            title="Redacted public source",
            origin_url="https://example.test/redacted/public-source",
            summary="Governed public source without tenant identity.",
            proposed_by="secret-agent",
        )
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


def test_academy_helpers_reject_real_deployment_owner_mismatch() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        _seed_deployment(conn, deployment_id="dep-owned-by-b", user_id="owner-b")

        raised = False
        try:
            ap.enroll_academy_trainee(
                conn,
                program_id="research_analyst",
                user_id="owner-a",
                deployment_id="dep-owned-by-b",
            )
        except ap.ArcLinkAcademyProgramError:
            raised = True
        expect(raised, "Academy enroll must reject a real deployment owned by another account")

        _seed_deployment(conn, deployment_id="dep-owned-by-a", user_id="owner-a")
        trainee = ap.enroll_academy_trainee(
            conn,
            program_id="research_analyst",
            user_id="owner-a",
            deployment_id="dep-owned-by-a",
        )
        expect(trainee["deployment_id"] == "dep-owned-by-a", str(trainee))
        print("PASS test_academy_helpers_reject_real_deployment_owner_mismatch")
    finally:
        cleanup(tmp, old_env)


def test_academy_central_adoption_rejects_real_deployment_owner_mismatch() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        _graduate(ap, conn, "systems_practice_engineer", "capt-source", "dep-source")
        spec_uid, _ = ap.specialist_uid_for_program(ap.get_academy_program(conn, "systems_practice_engineer"))
        _seed_deployment(conn, deployment_id="dep-owned-by-c", user_id="capt-c")

        raised = False
        try:
            ap.adopt_central_specialist(
                conn,
                specialist_uid=spec_uid,
                user_id="capt-b",
                deployment_id="dep-owned-by-c",
                name="Wrong Pod",
            )
        except ap.ArcLinkAcademyProgramError:
            raised = True
        expect(raised, "central specialist adoption must reject another Captain's deployment id")

        _seed_deployment(conn, deployment_id="dep-owned-by-b", user_id="capt-b")
        adopted = ap.adopt_central_specialist(
            conn,
            specialist_uid=spec_uid,
            user_id="capt-b",
            deployment_id="dep-owned-by-b",
            name="Right Pod",
        )
        expect(adopted["deployment_id"] == "dep-owned-by-b", str(adopted))
        print("PASS test_academy_central_adoption_rejects_real_deployment_owner_mismatch")
    finally:
        cleanup(tmp, old_env)


def _propose(
    ap,
    conn,
    deployment_id,
    *,
    lane_id,
    title,
    origin_url,
    summary,
    citations=None,
    proposal_kind="add_resource",
    target_source_uid="",
):
    return ap.record_academy_resource_proposal(
        conn,
        deployment_id=deployment_id,
        lane_id=lane_id,
        proposal_kind=proposal_kind,
        target_source_uid=target_source_uid,
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
        # D-E: central sharing is opt-IN -> this Captain explicitly chose public.
        t = ap.enroll_academy_trainee(conn, program_id="systems_practice_engineer", user_id="capt-a", deployment_id="dep-prom",
                                      captain_steer={"share": "redacted_public"})
        s = ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="capt-a")
        _propose(ap, conn, "dep-prom", lane_id="github_repository", title="Reference repo",
                 origin_url="https://example.test/repo", summary="Compressed architecture patterns derived from the repo.")
        _propose(ap, conn, "dep-prom", lane_id="organization_private", title="Private bundle",
                 origin_url="", summary="Captain-only private notes that must never go central.")
        # CODEX-MISS-1: a raw-markup summary is now rejected at INTAKE (it can never enter
        # the corpus, let alone reach promotion) -- a stronger guard than the prior
        # promote-time skip. Raw never becomes a synthesis input.
        raw_rejected = False
        try:
            _propose(ap, conn, "dep-prom", lane_id="web_article", title="Raw page",
                     origin_url="https://example.test/raw", summary="<html><div><span>raw markup</span></div></html> not derived notes")
        except ap.ArcLinkAcademyProgramError as exc:
            raw_rejected = "raw source content" in str(exc)
        expect(raw_rejected, "raw markup summary must be rejected at proposal intake (CODEX-MISS-1)")

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


def test_academy_graduation_absent_share_stays_private_failsafe() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        # D-E fail-safe: a trainee with NO explicit share choice (charterless/legacy
        # enroll) must NOT auto-promote to the shared central corpus on graduation.
        t = ap.enroll_academy_trainee(conn, program_id="systems_practice_engineer", user_id="capt-z", deployment_id="dep-zprom")
        s = ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="capt-z")
        _propose(ap, conn, "dep-zprom", lane_id="github_repository", title="Reference repo",
                 origin_url="https://example.test/zrepo", summary="Compressed architecture patterns derived from the repo.")
        ended = ap.end_academy_mode(conn, session_id=s["session"]["session_id"], actor="capt-z", graduate=True)
        cs = ended["session"]["commit_summary"]
        expect(int(cs.get("central_sources_promoted") or 0) == 0, f"absent share must not promote: {cs}")
        expect(str(cs.get("central_share_scope") or "private") == "private", f"absent share -> private scope: {cs}")
        rows = conn.execute("SELECT COUNT(*) AS n FROM academy_sources").fetchone()
        expect(int(rows["n"]) == 0, "no source reaches the shared corpus without an explicit public opt-in")
        print("PASS test_academy_graduation_absent_share_stays_private_failsafe")
    finally:
        cleanup(tmp, old_env)


def test_academy_discontinue_proposal_queues_review_without_quarantining_central_source() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        first = ap.enroll_academy_trainee(
            conn,
            program_id="systems_practice_engineer",
            user_id="capt-source",
            deployment_id="dep-source",
            captain_steer={"share": "redacted_public"},  # D-E: explicit public opt-in to seed the shared corpus
        )
        first_session = ap.open_academy_mode(conn, trainee_id=first["trainee_id"], opened_by="capt-source")
        _propose(
            ap,
            conn,
            "dep-source",
            lane_id="github_repository",
            title="Shared source to retire",
            origin_url="https://example.test/dead-end",
            summary="Compressed source notes that initially looked useful.",
        )
        first_end = ap.end_academy_mode(conn, session_id=first_session["session"]["session_id"], actor="capt-source", graduate=True)
        spec_uid = first_end["session"]["commit_summary"]["central_specialist_uid"]
        source = conn.execute(
            "SELECT source_uid, status FROM academy_sources WHERE canonical_url = ?",
            ("https://example.test/dead-end",),
        ).fetchone()
        expect(source is not None and source["status"] == "active", str(dict(source) if source else None))

        second = ap.enroll_academy_trainee(
            conn,
            program_id="systems_practice_engineer",
            user_id="capt-review",
            deployment_id="dep-review",
            captain_steer={"share": "redacted_public"},  # D-E: explicit public opt-in
        )
        second_session = ap.open_academy_mode(conn, trainee_id=second["trainee_id"], opened_by="capt-review")
        discontinue = _propose(
            ap,
            conn,
            "dep-review",
            lane_id="github_repository",
            title="Shared source to retire",
            origin_url="https://example.test/dead-end",
            summary="Dead end after review: stale repository guidance contradicts the stronger current source.",
            proposal_kind="discontinue_resource",
        )
        expect(discontinue["proposal_kind"] == "discontinue_resource", str(discontinue))
        second_end = ap.end_academy_mode(conn, session_id=second_session["session"]["session_id"], actor="capt-review", graduate=True)
        cs = second_end["session"]["commit_summary"]
        expect(cs["central_specialist_uid"] == spec_uid, str(cs))
        expect(cs["central_sources_discontinued"] == 0, str(cs))
        expect(cs["central_source_discontinue_reviews"] == 1, str(cs))
        expect("post_discontinuation_recurated" not in cs, str(cs))

        retired = conn.execute(
            "SELECT status, enrichment_json FROM academy_sources WHERE source_uid = ?",
            (source["source_uid"],),
        ).fetchone()
        expect(retired["status"] == "active", str(dict(retired)))
        expect("discontinue_review" in str(retired["enrichment_json"]), str(retired["enrichment_json"]))
        expect("pending_pg_provider" in str(retired["enrichment_json"]), str(retired["enrichment_json"]))
        prop = conn.execute(
            "SELECT status, trainer_review_json FROM academy_resource_proposals WHERE proposal_id = ?",
            (discontinue["proposal_id"],),
        ).fetchone()
        expect(prop["status"] == "review_pending", str(dict(prop)))
        expect("pending_live_review" in str(prop["trainer_review_json"]), str(prop["trainer_review_json"]))
        card = ap.academy_specialist_public_card(conn, specialist_uid=spec_uid)
        expect(card is not None and card["source_count"] == 1, str(card))
        applied = ap.stage_academy_apply(conn, trainee_id=second["trainee_id"], adapter_name="fake")
        expect(applied["contract_fresh"] is True, str(applied))
        expect(applied["writes_enabled"] is False, "record-only apply remains no-write")
        print("PASS test_academy_discontinue_proposal_queues_review_without_quarantining_central_source")
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


def test_academy_opt_out_private_capsule_can_apply_without_public_corpus() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="domain_tutor", user_id="capt-private", deployment_id="dep-private",
                                      captain_steer={"share": "private"})
        s = ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="capt-private")
        _propose(ap, conn, "dep-private", lane_id="organization_private", title="Captain teaching notes",
                 origin_url="", summary="Compressed Captain-approved private teaching notes for this Agent only.")
        ap.end_academy_mode(conn, session_id=s["session"]["session_id"], actor="capt-private", graduate=True)

        central = conn.execute("SELECT COUNT(*) AS n FROM academy_sources").fetchone()
        expect(int(central["n"]) == 0, "private capsule must not publish sources centrally")
        staged = ap.stage_academy_apply(conn, trainee_id=t["trainee_id"], adapter_name="fake")
        expect(staged["writes_enabled"] is False and staged["status"] == "staged", str(staged))
        expect(staged["academy_specialist_uid"].startswith("private:"), str(staged))
        expect("Captain teaching notes" in staged["academy_soul_section"], staged["academy_soul_section"])

        live = ap.stage_academy_apply(conn, trainee_id=t["trainee_id"], adapter_name="ssh", live_authorized=True)
        expect(live["status"] == "failed_closed" and live["writes_enabled"] is False, str(live))
        expect(live["academy_trainer_review_ready"] is True, str(live))
        expect(live["academy_provider_review_ready"] is False, str(live))
        print("PASS test_academy_opt_out_private_capsule_can_apply_without_public_corpus")
    finally:
        cleanup(tmp, old_env)


def test_academy_central_specialist_shared_and_deduped_across_captains() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        # Captain A trains + graduates a shared specialist with one public source.
        a = ap.enroll_academy_trainee(conn, program_id="systems_practice_engineer", user_id="capt-a", deployment_id="dep-a",
                                      captain_steer={"share": "redacted_public"})  # D-E: explicit public opt-in
        sa = ap.open_academy_mode(conn, trainee_id=a["trainee_id"], opened_by="capt-a")
        _propose(ap, conn, "dep-a", lane_id="github_repository", title="Shared repo",
                 origin_url="https://example.test/shared-repo", summary="Derived patterns A gathered.")
        ap.end_academy_mode(conn, session_id=sa["session"]["session_id"], actor="capt-a", graduate=True)

        spec_uid, _ = ap.specialist_uid_for_program(ap.get_academy_program(conn, "systems_practice_engineer"))

        # Captain B enrolls the SAME Major and inherits the shared corpus on enroll.
        b = ap.enroll_academy_trainee(conn, program_id="systems_practice_engineer", user_id="capt-b", deployment_id="dep-b",
                                      captain_steer={"share": "redacted_public"})  # D-E: B also contributes provenance
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


def test_academy_public_cards_and_capsules_ignore_private_central_rows() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        _graduate(ap, conn, "systems_practice_engineer", "capt-pub", "dep-pub")
        spec_uid, _ = ap.specialist_uid_for_program(ap.get_academy_program(conn, "systems_practice_engineer"))

        now = "2026-05-27T03:00:00Z"
        conn.execute(
            """
            INSERT INTO academy_sources (
              source_uid, canonical_url, lane_id, title, derived_notes, citations_json,
              content_hash, license_status, enrichment_json, quality_score, share_scope,
              status, first_seen_at, last_reviewed_at, last_observed_at, freshness_days, updated_at
            ) VALUES (?, ?, 'web_article', ?, ?, '[]', ?, 'agent-reported', '{}', 99,
              'private', 'active', ?, ?, '', 7, ?)
            """,
            (
                "asrc_private_manual",
                "https://example.test/private-central-row",
                "Private central row",
                "PRIVATE_NEVER_IN_PUBLIC_CAPSULE",
                "privatehash",
                now,
                now,
                now,
            ),
        )
        conn.execute(
            "INSERT OR IGNORE INTO academy_specialist_sources (specialist_uid, source_uid, weight, added_at) VALUES (?, ?, 0, ?)",
            (spec_uid, "asrc_private_manual", now),
        )
        ap.refresh_specialist_capsule(conn, specialist_uid=spec_uid)
        spec = conn.execute(
            "SELECT compressed_soul_capsule FROM academy_corpus_specialists WHERE specialist_uid = ?",
            (spec_uid,),
        ).fetchone()
        card = ap.academy_specialist_public_card(conn, specialist_uid=spec_uid)
        expect(card is not None and card["source_count"] == 1, str(card))
        expect("PRIVATE_NEVER_IN_PUBLIC_CAPSULE" not in str(spec["compressed_soul_capsule"]), str(spec["compressed_soul_capsule"]))

        conn.execute(
            """
            INSERT INTO academy_corpus_specialists (
              specialist_uid, program_id, role_title, topic_fingerprint,
              compressed_soul_capsule, capsule_version, enrichment_json, captain_count,
              share_scope, status, first_seen_at, last_enriched_at, updated_at
            ) VALUES ('aspec_private_manual', 'research_analyst', 'Private Role',
              'private-role', 'private body', 1, '{}', 1, 'private', 'active', ?, ?, ?)
            """,
            (now, now, now),
        )
        expect(
            ap.academy_specialist_public_card(conn, specialist_uid="aspec_private_manual") is None,
            "public card helper must refuse private specialists by default",
        )
        expect(
            all(c["specialist_uid"] != "aspec_private_manual" for c in ap.list_central_specialists(conn)),
            "public central gallery must not include private specialists",
        )
        print("PASS test_academy_public_cards_and_capsules_ignore_private_central_rows")
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


class _FailingLiveTrainer:
    live = True

    def review(self, *, role_title, topic, sources):
        raise RuntimeError("router down sk-proj-" + "A" * 32)


class _FakeRouterResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def read(self, _limit: int = -1) -> bytes:
        return json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Router Trainer selected the source set.",
                                    "verdicts": [
                                        {
                                            "source_uid": "asrc_live",
                                            "lane_id": "web_article",
                                            "verdict": "watch",
                                            "note": "Keep weekly watch.",
                                        }
                                    ],
                                },
                                sort_keys=True,
                            )
                        }
                    }
                ]
            },
            sort_keys=True,
        ).encode("utf-8")


def test_academy_router_trainer_client_uses_llm_router_key() -> None:
    tmp, old_env, _conn, _control, ap = with_db()
    old_urlopen = ap.urllib.request.urlopen
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return _FakeRouterResponse()

    try:
        key_file = Path(tmp.name) / "trainer-router-key"
        key_file.write_text("acpod_live_test_router_key\n", encoding="utf-8")
        client = ap.academy_trainer_client_from_env(
            {
                "ARCLINK_ACADEMY_TRAINER_ROUTER_BASE_URL": "http://router.test/v1",
                "ARCLINK_ACADEMY_TRAINER_ROUTER_KEY_FILE": str(key_file),
                "ARCLINK_ACADEMY_TRAINER_MODEL": "model-trainer",
                "ARCLINK_ACADEMY_TRAINER_TIMEOUT_SECONDS": "9",
            }
        )
        expect(client is not None and client.live is True, "expected router Trainer client")
        ap.urllib.request.urlopen = fake_urlopen
        review = client.review(
            role_title="Research Analyst",
            topic="systems research",
            sources=[
                {
                    "source_uid": "asrc_live",
                    "lane_id": "web_article",
                    "title": "Live source",
                    "canonical_url": "https://example.test/source",
                    "derived_notes": "Derived notes only.",
                    "citations_json": json.dumps(["https://example.test/source"]),
                }
            ],
        )
        expect(review["engine"] == "llm-router" and review["live"] is True, str(review))
        expect(review["summary"] == "Router Trainer selected the source set.", str(review))
        expect(review["verdicts"][0]["verdict"] == "watch", str(review))
        expect(len(calls) == 1, str(calls))
        request, timeout = calls[0]
        expect(timeout == 9, str(timeout))
        expect(request.full_url == "http://router.test/v1/chat/completions", request.full_url)
        expect(request.headers.get("Authorization") == "Bearer acpod_live_test_router_key", str(request.headers))
        body = json.loads(request.data.decode("utf-8"))
        expect(body["model"] == "model-trainer", str(body))
        expect("Derived notes only" in body["messages"][1]["content"], str(body))
        print("PASS test_academy_router_trainer_client_uses_llm_router_key")
    finally:
        ap.urllib.request.urlopen = old_urlopen
        cleanup(tmp, old_env)


def test_academy_router_trainer_redacts_secret_shaped_payload_fields() -> None:
    tmp, old_env, _conn, _control, ap = with_db()
    old_urlopen = ap.urllib.request.urlopen
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return _FakeRouterResponse()

    try:
        key_file = Path(tmp.name) / "trainer-router-key"
        key_file.write_text("acpod_live_test_router_key\n", encoding="utf-8")
        client = ap.academy_trainer_client_from_env(
            {
                "ARCLINK_ACADEMY_TRAINER_ROUTER_BASE_URL": "http://router.test/v1",
                "ARCLINK_ACADEMY_TRAINER_ROUTER_KEY_FILE": str(key_file),
            }
        )
        expect(client is not None, "expected router Trainer client")
        ap.urllib.request.urlopen = fake_urlopen
        client.review(
            role_title="Research Analyst",
            topic="safe review",
            sources=[
                {
                    "source_uid": "asrc_secret",
                    "lane_id": "web_article",
                    "title": "token=sk-proj-" + "A" * 32,
                    "canonical_url": "https://user:supersecret@example.test/source",
                    "derived_notes": "Use CHUTES_API_KEY=cpk_test_secret_value_12345 for access.",
                    "citations_json": json.dumps(["https://user:supersecret@example.test/source"]),
                }
            ],
        )
        expect(len(calls) == 1, str(calls))
        body = json.loads(calls[0][0].data.decode("utf-8"))
        content = body["messages"][1]["content"]
        expect("[REDACTED]" in content, content)
        for forbidden in ("sk-proj-", "cpk_test_secret", "supersecret"):
            expect(forbidden not in content, content)
        print("PASS test_academy_router_trainer_redacts_secret_shaped_payload_fields")
    finally:
        ap.urllib.request.urlopen = old_urlopen
        cleanup(tmp, old_env)


def test_academy_mode_end_uses_live_trainer_when_pg_provider_authorized() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="systems_practice_engineer", user_id="capt-live", deployment_id="dep-live",
                                      captain_steer={"share": "redacted_public"})  # D-E: explicit public opt-in
        s = ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="capt-live")
        _propose(ap, conn, "dep-live", lane_id="github_repository", title="Live mode-end source",
                 origin_url="https://example.test/live-mode-end", summary="Derived live Trainer notes.")
        ended = ap.end_academy_mode(
            conn,
            session_id=s["session"]["session_id"],
            actor="capt-live",
            graduate=True,
            trainer_client=_FakeLiveTrainer(),
            live_trainer_authorized=True,
        )
        cs = ended["session"]["commit_summary"]
        expect(cs["central_trainer_engine"] == "live-router", str(cs))
        expect(cs["central_trainer_live_status"] == "live_reviewed", str(cs))
        print("PASS test_academy_mode_end_uses_live_trainer_when_pg_provider_authorized")
    finally:
        cleanup(tmp, old_env)


def test_academy_trainer_deep_dive_reviews_and_stamps_and_supports_live() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="systems_practice_engineer", user_id="capt-t", deployment_id="dep-t",
                                      captain_steer={"share": "redacted_public"})  # D-E: explicit public opt-in
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


def test_academy_live_trainer_failure_notifies_captain_and_blocks_provider_proof() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="systems_practice_engineer", user_id="capt-fail", deployment_id="dep-fail",
                                      captain_steer={"share": "redacted_public"})  # D-E: explicit public opt-in
        s = ap.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="capt-fail")
        _propose(ap, conn, "dep-fail", lane_id="github_repository", title="Failing live source",
                 origin_url="https://example.test/live-fail", summary="Derived source notes.")
        ended = ap.end_academy_mode(conn, session_id=s["session"]["session_id"], actor="capt-fail", graduate=True)
        spec_uid = ended["session"]["commit_summary"]["central_specialist_uid"]

        result = ap.run_academy_trainer_review(conn, specialist_uid=spec_uid, client=_FailingLiveTrainer(), live_authorized=True)
        expect(result["live"] is False and result["live_enrichment_status"] == "pending_pg_provider", str(result))
        event = conn.execute(
            "SELECT metadata_json FROM arclink_events WHERE event_type = 'academy_trainer_live_review_failed'"
        ).fetchone()
        expect(event is not None, "live Trainer failure should record an event")
        expect("sk-proj-" not in str(event["metadata_json"]), str(event["metadata_json"]))
        note = conn.execute(
            "SELECT target_kind, target_id, channel_kind, message, extra_json FROM notification_outbox WHERE channel_kind = 'academy'"
        ).fetchone()
        expect(note is not None and note["target_id"] == "capt-fail", str(dict(note) if note else None))
        expect("PG-PROVIDER live review failed" in note["message"], str(dict(note)))
        expect("sk-proj-" not in str(note["extra_json"]), str(note["extra_json"]))
        applied = ap.stage_academy_apply(conn, trainee_id=t["trainee_id"], adapter_name="ssh", live_authorized=True)
        expect(applied["writes_enabled"] is False and applied["academy_provider_review_ready"] is False, str(applied))
        print("PASS test_academy_live_trainer_failure_notifies_captain_and_blocks_provider_proof")
    finally:
        cleanup(tmp, old_env)


def test_academy_apply_stages_replaceable_soul_section() -> None:
    tmp, old_env, conn, _control, ap = with_db()
    try:
        import arclink_org_profile as op

        ap.seed_default_academy_programs(conn)
        t = ap.enroll_academy_trainee(conn, program_id="research_analyst", user_id="capt-s", deployment_id="dep-s",
                                      captain_steer={"share": "redacted_public"})  # D-E: public capsule needs explicit opt-in
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


def test_academy_apply_private_synthesis_drives_soul_not_central_shadow() -> None:
    """D-X1 (step4): when a FRESH live-authored private synthesis exists, it DRIVES the
    agent's applied Academy SOUL -- the central specialist capsule no longer SHADOWS it
    (the prior bug). The applied layer is bound (hash + manifest) to that authored
    artifact for the step6-7 graduation gate."""
    tmp, old_env, conn, _control, ap = with_db()
    try:
        ap.seed_default_academy_programs(conn)
        # Graduate WITH a public capsule so a central specialist capsule exists (the
        # thing that previously shadowed the private layer).
        t = ap.enroll_academy_trainee(conn, program_id="research_analyst", user_id="capt-x", deployment_id="dep-x",
                                      captain_steer={"share": "redacted_public"})
        tid = t["trainee_id"]
        s = ap.open_academy_mode(conn, trainee_id=tid, opened_by="capt-x")
        _propose(ap, conn, "dep-x", lane_id="web_article", title="Capsule source",
                 origin_url="https://example.test/capsule", summary="Derived notes that should land in the capsule.")
        ap.end_academy_mode(conn, session_id=s["session"]["session_id"], actor="capt-x", graduate=True)

        # Baseline: with NO synthesis, the central capsule drives (legacy behavior intact).
        before = ap.stage_academy_apply(conn, trainee_id=tid, adapter_name="fake")
        expect(before["academy_synthesis_drives"] is False, "no synthesis yet -> central capsule drives (fallback)")
        expect("Capsule source" in before["academy_soul_section"], "central capsule content drives when no synthesis")

        # Author a FRESH private synthesis bound to the current manifest.
        class FakeLive:
            live = True
            def synthesize(self, *, role_title, topic, charter, sources):
                return {"engine": "live-router", "authored": True,
                        "lesson_notes": [{"source_uid": s["source_uid"], "note": "Authored guidance."} for s in sources],
                        "soul_capsule": "PRIVATE-AUTHORED-SOUL: retrieve and cite before any specialist claim.",
                        "retrieval_rules": ["cite first"], "quality_metrics": {}}

        syn = ap.run_academy_trainer_synthesize(conn, trainee_id=tid, scope="private", client=FakeLive(), live_authorized=True)
        expect(syn["authored"] is True and syn["status"] == "authored", str(syn))

        applied = ap.stage_academy_apply(conn, trainee_id=tid, adapter_name="fake")
        expect(applied["academy_synthesis_drives"] is True, f"fresh authored private synthesis must DRIVE the applied SOUL: {applied}")
        expect(applied["academy_specialist_uid"].startswith("private:"), str(applied["academy_specialist_uid"]))
        expect("PRIVATE-AUTHORED-SOUL" in applied["academy_soul_section"], "the agent's SOUL is its OWN authored synthesis")
        expect("Capsule source" not in applied["academy_soul_section"], "the central capsule no longer SHADOWS the private layer (D-X1)")
        expect(applied["academy_synthesis_hash"] == syn["content_hash"], "applied layer bound to THIS authored artifact")
        expect(applied["academy_synthesis_manifest_id"] == applied["recomputed_manifest_id"], "synthesis bound to the recomputed manifest (fresh)")
        print("PASS test_academy_apply_private_synthesis_drives_soul_not_central_shadow")
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
    test_academy_graduation_absent_share_stays_private_failsafe()
    test_academy_discontinue_proposal_queues_review_without_quarantining_central_source()
    test_academy_opt_out_keeps_specialist_private()
    test_academy_opt_out_private_capsule_can_apply_without_public_corpus()
    test_academy_central_specialist_shared_and_deduped_across_captains()
    test_academy_public_cards_and_capsules_ignore_private_central_rows()
    test_academy_router_trainer_client_uses_llm_router_key()
    test_academy_router_trainer_redacts_secret_shaped_payload_fields()
    test_academy_mode_end_uses_live_trainer_when_pg_provider_authorized()
    test_academy_trainer_deep_dive_reviews_and_stamps_and_supports_live()
    test_academy_live_trainer_failure_notifies_captain_and_blocks_provider_proof()
    test_academy_apply_stages_replaceable_soul_section()
    test_academy_apply_private_synthesis_drives_soul_not_central_shadow()
    test_academy_apply_validates_staged_contract_and_fails_closed_on_major_drift()
    test_academy_apply_rejects_target_owner_mismatch()
    test_academy_continuing_education_uses_real_sources()
    test_academy_trainee_quota_enforced()
    test_academy_open_mode_scrubs_opened_via_and_is_idempotent()
    test_academy_mode_session_growth_is_bounded()
    test_academy_graduate_card_redacts_tenant_identity()
    test_academy_seed_refreshes_default_catalog_drift()
    test_academy_adopt_helper_blocks_cross_owner_clone()
    test_academy_helpers_reject_real_deployment_owner_mismatch()
    test_academy_central_adoption_rejects_real_deployment_owner_mismatch()
    test_academy_apply_is_fail_closed()
    test_academy_apply_requires_graduated_trainee()
    test_academy_curation_builds_corpus_plan_and_stages()
    test_academy_curation_without_real_sources_is_honest_draft()
    test_academy_charter_builds_with_failsafe_defaults_and_status()
    test_academy_charter_roundtrips_over_2000_chars_through_edit_path()
    test_academy_materialize_operator_sources_classifies_screens_and_graduatable()
    test_academy_extract_model_json_fence_tolerant()
    test_academy_synthesis_engine_two_pass_fail_closed()
    test_academy_synthesis_screens_all_fields_and_blocks_downgrade()
    test_academy_acceptance_exam_objective_checks_and_gate()
    test_academy_exam_step5_hardening()
    test_academy_4d_authored_curriculum_fresh_only()
    test_academy_exam_gate_rederives_and_blocks()
    test_academy_live_exam_runner_tool_loop()
    test_academy_graduation_state_and_endmode_hook()
    test_academy_materialize_targets_authorized_trainee_not_newest_open()
    test_academy_reuse_plan_inherits_or_pioneers_with_gap_map()
    test_academy_pointer_and_private_excluded_from_corpus_and_specialist_stamped()
    test_academy_foundation_seed_is_draft_governed_and_inheritable()
    test_academy_commit_curates_on_graduation()
    test_academy_continuing_education_is_no_write()
    test_academy_catalog_seed_is_idempotent_and_browsable()
    test_academy_enroll_open_sticky_and_graduate()
    test_academy_mode_records_steer_and_resource_proposals()
    test_academy_resource_proposal_insert_race_returns_deduped()
    test_academy_cancel_mode_returns_to_enrolled()
    test_academy_browse_graduates_and_adopt()
    test_academy_adopts_central_specialist_for_new_captain()
    test_academy_many_types_as_data_and_lane_validation()
    test_academy_source_lane_registry_failure_fails_closed()
    test_academy_enroll_surfaces_subscription_failure()
    test_academy_rejects_secret_material_and_unknown_program()
    print("PASS all academy programs tests")
