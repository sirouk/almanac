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
        result = scheduler.run_academy_forward_maintenance(conn, env={"ARCLINK_ACADEMY_CE_LIVE_CRAWL": "0"})
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
        result = scheduler.run_academy_forward_maintenance(conn, env={"ARCLINK_ACADEMY_CE_LIVE_CRAWL": "0"}, limit=2)
        expect(result["eligible"] == 3, str(result))
        expect(result["processed"] == 2, str(result))
        expect(result["deferred_to_next_run"] == 1, "overflow is reported, never silently dropped")
        print("PASS test_forward_maintenance_caps_and_reports_overflow")
    finally:
        cleanup(tmp, old_env)


def test_forward_maintenance_limit_zero_processes_all() -> None:
    tmp, old_env, conn, _control, programs, scheduler = with_db()
    try:
        programs.seed_default_academy_programs(conn)
        for i in range(3):
            _graduate(programs, conn, "research_analyst", f"u{i}", f"dep-{i}")
        # limit <= 0 means "process all eligible" (explicit, documented).
        result = scheduler.run_academy_forward_maintenance(conn, env={"ARCLINK_ACADEMY_CE_LIVE_CRAWL": "0"}, limit=0)
        expect(result["eligible"] == 3 and result["processed"] == 3, str(result))
        expect(result["deferred_to_next_run"] == 0, str(result))
        neg = scheduler.run_academy_forward_maintenance(conn, env={"ARCLINK_ACADEMY_CE_LIVE_CRAWL": "0"}, limit=-5)
        expect(neg["processed"] == 3, "negative limit also means process all")
        print("PASS test_forward_maintenance_limit_zero_processes_all")
    finally:
        cleanup(tmp, old_env)


def _graduate_with_public_source(programs, conn, program_id, user_id, deployment_id):
    t = programs.enroll_academy_trainee(conn, program_id=program_id, user_id=user_id, deployment_id=deployment_id)
    s = programs.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by=user_id)
    programs.record_academy_resource_proposal(
        conn, deployment_id=deployment_id, lane_id="web_article", title="Weekly source",
        origin_url="https://example.test/weekly", summary="Compressed derived notes for the weekly source.",
        proposed_by="agent-x",
    )
    programs.end_academy_mode(conn, session_id=s["session"]["session_id"], actor=user_id, graduate=True)
    return t


def test_forward_maintenance_notifies_captain_and_refreshes_capsule_idempotently() -> None:
    tmp, old_env, conn, _control, programs, scheduler = with_db()
    try:
        programs.seed_default_academy_programs(conn)
        _graduate_with_public_source(programs, conn, "research_analyst", "capt-w", "dep-w")

        result = scheduler.run_academy_forward_maintenance(conn, env={"ARCLINK_ACADEMY_CE_LIVE_CRAWL": "0"})
        expect(result["captains_notified"] == 1, f"the Captain is notified weekly: {result}")
        # The capsule was already composed at graduation; weekly content is unchanged
        # for stable sources, so the version is NOT churned.
        expect(result["central_capsules_refreshed"] == 0, "idempotent capsule refresh does not churn versions")
        expect(result["no_write"] is True and result["writes_enabled"] is False, "weekly job never writes the Agent")

        notes = conn.execute(
            "SELECT target_kind, target_id, channel_kind, extra_json FROM notification_outbox WHERE channel_kind = 'academy'"
        ).fetchall()
        expect(len(notes) == 1 and notes[0]["target_id"] == "capt-w", str([dict(n) for n in notes]))
        expect("academy_forward_maintenance" in str(notes[0]["extra_json"]), str(notes[0]["extra_json"]))
        print("PASS test_forward_maintenance_notifies_captain_and_refreshes_capsule_idempotently")
    finally:
        cleanup(tmp, old_env)


def test_forward_maintenance_rotates_shared_specialist_subscribers() -> None:
    tmp, old_env, conn, _control, programs, scheduler = with_db()
    try:
        programs.seed_default_academy_programs(conn)
        # Captain A creates the shared central specialist.
        a = programs.enroll_academy_trainee(conn, program_id="systems_practice_engineer", user_id="capt-a2", deployment_id="dep-a2")
        sa = programs.open_academy_mode(conn, trainee_id=a["trainee_id"], opened_by="capt-a2")
        programs.record_academy_resource_proposal(
            conn,
            deployment_id="dep-a2",
            lane_id="github_repository",
            title="Shared systems repo",
            origin_url="https://example.test/systems",
            summary="Compressed systems practice notes.",
            proposed_by="agent-a",
        )
        programs.end_academy_mode(conn, session_id=sa["session"]["session_id"], actor="capt-a2", graduate=True)

        # Captain B trains the same Major and subscribes to the same central specialist.
        b = programs.enroll_academy_trainee(conn, program_id="systems_practice_engineer", user_id="capt-b", deployment_id="dep-b")
        sb = programs.open_academy_mode(conn, trainee_id=b["trainee_id"], opened_by="capt-b")
        programs.end_academy_mode(conn, session_id=sb["session"]["session_id"], actor="capt-b", graduate=True)

        result = scheduler.run_academy_forward_maintenance(
            conn,
            env={"ARCLINK_ACADEMY_CE_LIVE_CRAWL": "0"},
            created_at="2026-06-01T00:00:00Z",
        )
        expect(result["eligible"] >= 2, str(result))
        expect(result["processed"] == result["eligible"] - result["shared_rotation_deferred"], str(result))
        expect(result["shared_rotation_deferred"] >= 1, str(result))
        rotating = [review for review in result["reviews"] if review.get("rotation_specialist_uid")]
        expect(len(rotating) == 1, f"one subscriber should carry the shared specialist this week: {result}")
        first = rotating[0]["trainee_id"]
        result2 = scheduler.run_academy_forward_maintenance(
            conn,
            env={"ARCLINK_ACADEMY_CE_LIVE_CRAWL": "0"},
            created_at="2026-06-08T00:00:00Z",
        )
        rotating2 = [review for review in result2["reviews"] if review.get("rotation_specialist_uid")]
        expect(len(rotating2) == 1, str(result2))
        expect(rotating2[0]["trainee_id"] != first, f"shared specialist rotation should advance statefully: {result2}")
        print("PASS test_forward_maintenance_rotates_shared_specialist_subscribers")
    finally:
        cleanup(tmp, old_env)


class _FakeWeeklyLiveTrainer:
    live = True

    def review(self, *, role_title, topic, sources):
        return {
            "engine": "weekly-live-router",
            "live": True,
            "summary": f"Weekly live review for {role_title}",
            "verdicts": [{"source_uid": source["source_uid"], "verdict": "keep"} for source in sources],
        }


def test_forward_maintenance_can_run_live_trainer_review_without_agent_writes() -> None:
    tmp, old_env, conn, _control, programs, scheduler = with_db()
    old_factory = scheduler.academy_trainer_client_from_env
    try:
        programs.seed_default_academy_programs(conn)
        t = programs.enroll_academy_trainee(conn, program_id="research_analyst", user_id="capt-live", deployment_id="dep-live")
        s = programs.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="capt-live")
        programs.record_academy_resource_proposal(
            conn,
            deployment_id="dep-live",
            lane_id="web_article",
            title="Weekly live Trainer source",
            origin_url="https://example.test/weekly-live-trainer",
            summary="Compressed source notes for weekly live Trainer review.",
            proposed_by="agent-live",
        )
        programs.end_academy_mode(conn, session_id=s["session"]["session_id"], actor="capt-live", graduate=True)
        scheduler.academy_trainer_client_from_env = lambda env=None: _FakeWeeklyLiveTrainer()
        result = scheduler.run_academy_forward_maintenance(
            conn,
            env={"ARCLINK_ACADEMY_CE_LIVE_CRAWL": "0", "ARCLINK_ACADEMY_TRAINER_LIVE": "1"},
            created_at="2026-06-02T00:00:00Z",
        )
        expect(result["trainer_reviews"] >= 1, str(result))
        expect(result["live_trainer_reviews"] >= 1, str(result))
        expect(result["no_write"] is True and result["writes_enabled"] is False, str(result))
        row = conn.execute("SELECT enrichment_json FROM academy_corpus_specialists").fetchone()
        enrichment = json.loads(row["enrichment_json"])
        expect(enrichment["engine"] == "weekly-live-router", str(enrichment))
        expect(enrichment["live"] is True, str(enrichment))
        print("PASS test_forward_maintenance_can_run_live_trainer_review_without_agent_writes")
    finally:
        scheduler.academy_trainer_client_from_env = old_factory
        cleanup(tmp, old_env)


def test_forward_maintenance_live_crawls_public_sources_digest_only() -> None:
    tmp, old_env, conn, _control, programs, scheduler = with_db()
    try:
        programs.seed_default_academy_programs(conn)
        _graduate_with_public_source(programs, conn, "research_analyst", "capt-crawl", "dep-crawl")
        calls: list[str] = []

        def fake_fetcher(*, url, headers, timeout, max_bytes):
            calls.append(url)
            if url.endswith("/robots.txt"):
                return {"status_code": 404, "headers": {}, "text": ""}
            return {
                "status_code": 200,
                "headers": {"etag": "v2", "last-modified": "Tue, 02 Jun 2026 00:00:00 GMT"},
                "text": "<html><body>Updated public Academy weekly source with enough safe derived observable content for review.</body></html>",
            }

        result = scheduler.run_academy_forward_maintenance(
            conn,
            env={"ARCLINK_ACADEMY_CE_ALLOW_TEST_URLS": "1"},
            fetcher=fake_fetcher,
            created_at="2026-06-02T00:00:00Z",
        )
        expect(result["live_crawl"]["enabled"] is True, str(result))
        expect(result["live_crawl"]["attempted"] == 1, str(result))
        expect(result["live_crawl"]["changed"] == 1, str(result))
        expect(result["reviews"][0]["review_needed_count"] == 1, str(result))
        expect(result["no_write"] is True and result["writes_enabled"] is False, str(result))
        expect(any(url.endswith("/robots.txt") for url in calls), f"crawler must check robots.txt: {calls}")
        observations = conn.execute("SELECT * FROM academy_source_crawl_observations").fetchall()
        expect(len(observations) == 1, str([dict(r) for r in observations]))
        row = observations[0]
        expect(row["status"] == "changed", str(dict(row)))
        expect(row["content_hash"], "digest-only observation should record a hash")
        expect("Updated public Academy" not in str(row["metadata_json"]), "raw fetched content leaked into metadata")
        after_intents = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]
        expect(after_intents == 0, "live weekly crawl must not queue Agent writes")
        source = conn.execute("SELECT content_hash, enrichment_json FROM academy_sources").fetchone()
        enrich = json.loads(source["enrichment_json"])
        expect(enrich["crawl"]["observed_content_hash"] == row["content_hash"], str(enrich))
        expect(source["content_hash"] != row["content_hash"], "accepted source hash should not change before Trainer/apply review")
        print("PASS test_forward_maintenance_live_crawls_public_sources_digest_only")
    finally:
        cleanup(tmp, old_env)


def test_forward_maintenance_live_crawl_blocks_unsafe_url_without_fetching() -> None:
    tmp, old_env, conn, _control, programs, scheduler = with_db()
    try:
        programs.seed_default_academy_programs(conn)
        t = programs.enroll_academy_trainee(conn, program_id="research_analyst", user_id="capt-ssrf", deployment_id="dep-ssrf")
        s = programs.open_academy_mode(conn, trainee_id=t["trainee_id"], opened_by="capt-ssrf")
        programs.record_academy_resource_proposal(
            conn,
            deployment_id="dep-ssrf",
            lane_id="web_article",
            title="Unsafe local source",
            origin_url="http://127.0.0.1/secret",
            summary="Compressed safe notes for an unsafe local URL.",
            proposed_by="agent-x",
        )
        programs.end_academy_mode(conn, session_id=s["session"]["session_id"], actor="capt-ssrf", graduate=True)

        def fail_fetcher(*, url, headers, timeout, max_bytes):
            raise AssertionError(f"unsafe URL should not be fetched: {url}")

        result = scheduler.run_academy_forward_maintenance(
            conn,
            env={"ARCLINK_ACADEMY_CE_ALLOW_TEST_URLS": "1"},
            fetcher=fail_fetcher,
            created_at="2026-06-02T00:00:00Z",
        )
        expect(result["live_crawl"]["blocked"] >= 1, str(result))
        rows = [dict(row) for row in conn.execute("SELECT status, reason FROM academy_source_crawl_observations")]
        expect(rows and rows[0]["status"] == "blocked", str(rows))
        expect(
            any(term in rows[0]["reason"] for term in ("loopback", "https", "non-public")),
            str(rows),
        )
        print("PASS test_forward_maintenance_live_crawl_blocks_unsafe_url_without_fetching")
    finally:
        cleanup(tmp, old_env)


if __name__ == "__main__":
    test_forward_maintenance_reviews_graduates_without_writes()
    test_forward_maintenance_caps_and_reports_overflow()
    test_forward_maintenance_limit_zero_processes_all()
    test_forward_maintenance_notifies_captain_and_refreshes_capsule_idempotently()
    test_forward_maintenance_rotates_shared_specialist_subscribers()
    test_forward_maintenance_can_run_live_trainer_review_without_agent_writes()
    test_forward_maintenance_live_crawls_public_sources_digest_only()
    test_forward_maintenance_live_crawl_blocks_unsafe_url_without_fetching()
    print("PASS all academy scheduler tests")
