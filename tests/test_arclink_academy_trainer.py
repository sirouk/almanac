#!/usr/bin/env python3
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

from arclink_test_helpers import expect, load_module

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from arclink_secrets_regex import contains_secret_material


def _academy():
    return load_module("arclink_academy_trainer.py", "arclink_academy_trainer_test")


def _flatten(value: Any) -> list[str]:
    if dataclasses.is_dataclass(value):
        return _flatten(dataclasses.asdict(value))
    if isinstance(value, dict):
        parts: list[str] = []
        for key, nested in value.items():
            parts.append(str(key))
            parts.extend(_flatten(nested))
        return parts
    if isinstance(value, (list, tuple, set)):
        parts = []
        for nested in value:
            parts.extend(_flatten(nested))
        return parts
    return [str(value)]


def _assert_secret_free(value: Any) -> None:
    offenders = [text for text in _flatten(value) if contains_secret_material(text, allow_safe_refs=False)]
    expect(not offenders, f"Academy artifact leaked secret-looking material: {offenders[:3]}")


def _safe_sources(academy):
    return [
        academy.fake_academy_source(
            source_id="src-wikimedia-privacy",
            lane_id="wikimedia",
            title="Privacy Preserving Systems Overview",
            origin_url="https://example.test/wiki/privacy-systems",
            retrieved_at="2026-05-20T00:00:00Z",
            license_status="cc-by-sa",
            permission_status="public_allowed",
            storage_policy="derived_summary",
            content=(
                "Privacy preserving systems combine data minimization, access boundaries, "
                "audit trails, and careful disclosure controls."
            ),
            citations=["Example Reference 1", "Example Reference 2", "Example Reference 3"],
            metadata={"revision": "12345", "official": True, "examples": True, "freshness_days": 90},
        ),
        academy.fake_academy_source(
            source_id="src-github-agent-ops",
            lane_id="github_repository",
            title="Agent Operations Repository",
            origin_url="https://example.test/acme/agent-ops",
            retrieved_at="2026-05-21T00:00:00Z",
            license_status="mit",
            permission_status="public_allowed",
            storage_policy="derived_summary",
            content=(
                "The repository demonstrates release checklists, incident notes, tests, "
                "least privilege helpers, and rollback-first operational habits."
            ),
            citations=["README.md", "docs/operations.md", "tests/test_release.py"],
            metadata={
                "repo": "acme/agent-ops",
                "commit_or_tag": "v1.0.0",
                "license": "mit",
                "maintained": True,
                "examples": True,
                "cross_source_agreement": True,
            },
        ),
        academy.fake_academy_source(
            source_id="src-skill-review",
            lane_id="skill_tool_catalog",
            title="Reviewed Retrieval Skill",
            origin_url="local-skill-catalog://retrieval-review",
            retrieved_at="2026-05-22T00:00:00Z",
            license_status="internal-approved",
            permission_status="operator_approved",
            storage_policy="metadata_only",
            content="Use the governed knowledge.search-and-fetch rail before giving domain advice.",
            citations=["local skill review"],
            metadata={
                "public_skill": True,
                "review_status": "approved",
                "skill_id": "academy-retrieval-review",
                "tool_recipes": ["knowledge.search-and-fetch before specialist advice"],
            },
            review_status="approved",
        ),
    ]


def _all_lane_fixture_records() -> list[dict[str, Any]]:
    return [
        {
            "source_id": "src-acq-video-transcript",
            "lane_id": "video_transcript",
            "title": "Authorized Operations Walkthrough Transcript",
            "origin_url": "https://example.test/videos/operations-walkthrough",
            "retrieved_at": "2026-05-27T00:00:00Z",
            "license_status": "creator-permission",
            "permission_status": "operator_approved",
            "storage_policy": "derived_summary",
            "content": "An authorized transcript explains incident triage, escalation, and release review.",
            "citations": ["transcript segment 1", "transcript segment 2", "transcript segment 3"],
            "metadata": {
                "transcript_source": "creator_provided",
                "transcript_confidence": "0.98",
                "official": True,
                "examples": True,
            },
        },
        {
            "source_id": "src-acq-reddit-discussion",
            "lane_id": "reddit_discussion",
            "title": "Practitioner Discussion Pattern Card",
            "origin_url": "https://example.test/r/operator/comments/patterns",
            "retrieved_at": "2026-05-27T00:00:00Z",
            "license_status": "platform-restricted",
            "permission_status": "public_allowed",
            "storage_policy": "metadata_only",
            "content": "A non-identifying pattern card tracks recurring failure modes and safe next checks.",
            "citations": ["thread metadata", "moderator note", "accepted correction"],
            "metadata": {
                "subreddit": "operator",
                "thread_quality": "moderated-corrected",
                "practitioner_signal": True,
                "cross_source_agreement": True,
            },
        },
        {
            "source_id": "src-acq-wikimedia",
            "lane_id": "wikimedia",
            "title": "Systems Reliability Overview",
            "origin_url": "https://example.test/wiki/systems-reliability",
            "retrieved_at": "2026-05-27T00:00:00Z",
            "license_status": "cc-by-sa",
            "permission_status": "public_allowed",
            "storage_policy": "derived_summary",
            "content": "A high-level map of reliability terms, references, and adjacent concepts.",
            "citations": ["revision 789", "reference list", "category map"],
            "metadata": {"revision": "789", "official": True, "examples": True},
        },
        {
            "source_id": "src-acq-github",
            "lane_id": "github_repository",
            "title": "Operations Automation Repository",
            "origin_url": "https://example.test/acme/ops-automation",
            "retrieved_at": "2026-05-27T00:00:00Z",
            "license_status": "mit",
            "permission_status": "public_allowed",
            "storage_policy": "derived_summary",
            "content": "Repository docs show tested release automation and rollback-first maintenance.",
            "citations": ["README.md", "docs/runbook.md", "tests/test_rollback.py"],
            "metadata": {
                "repo": "acme/ops-automation",
                "commit_or_tag": "abc1234",
                "license": "mit",
                "maintained": True,
                "examples": True,
                "cross_source_agreement": True,
            },
        },
        {
            "source_id": "src-acq-standard",
            "lane_id": "scholarly_standard",
            "title": "Operational Safety Standard",
            "origin_url": "https://example.test/standards/ops-safety",
            "retrieved_at": "2026-05-27T00:00:00Z",
            "license_status": "open-access",
            "permission_status": "public_allowed",
            "storage_policy": "metadata_only",
            "content": "A standards-body abstract defines audit, approval, and rollback requirements.",
            "citations": ["OPS-2026", "section 3", "section 5"],
            "metadata": {"identifier": "OPS-2026", "venue_or_body": "Example Standards Body", "official": True},
        },
        {
            "source_id": "src-acq-web-article",
            "lane_id": "web_article",
            "title": "Incident Review Article",
            "origin_url": "https://example.test/articles/incident-review",
            "retrieved_at": "2026-05-27T00:00:00Z",
            "license_status": "public-domain",
            "permission_status": "public_allowed",
            "storage_policy": "derived_summary",
            "content": "A dated article explains incident review prompts and evidence capture.",
            "citations": ["article body", "appendix", "example checklist"],
            "metadata": {
                "author_or_org": "Example Ops Lab",
                "published_at": "2026-05-01",
                "examples": True,
                "fresh": True,
                "cross_source_agreement": True,
            },
        },
        {
            "source_id": "src-acq-skill",
            "lane_id": "skill_tool_catalog",
            "title": "Reviewed Academy Retrieval Skill",
            "origin_url": "local-skill-catalog://academy-retrieval",
            "retrieved_at": "2026-05-27T00:00:00Z",
            "license_status": "internal-approved",
            "permission_status": "operator_approved",
            "storage_policy": "metadata_only",
            "content": "Use governed retrieval before specialist answers.",
            "citations": ["local skill review", "tool recipe", "test result"],
            "metadata": {
                "skill_id": "academy-retrieval",
                "review_status": "approved",
                "public_skill": True,
                "tool_recipes": ["knowledge.search-and-fetch before advice"],
                "examples": True,
            },
            "review_status": "approved",
        },
        {
            "source_id": "src-acq-organization-private",
            "lane_id": "organization_private",
            "title": "Operator-Supplied Internal Playbook Summary",
            "origin_url": "org-private://academy/playbooks/ops-summary",
            "retrieved_at": "2026-05-27T00:00:00Z",
            "license_status": "internal-approved",
            "permission_status": "operator_approved",
            "storage_policy": "derived_summary",
            "content": "A governed private summary preserves audience boundaries and review cadence.",
            "citations": ["operator supplied summary", "review approval", "audience scope"],
            "metadata": {
                "owner": "Example Organization",
                "audience_scope": "role-training-only",
                "examples": True,
                "cross_source_agreement": True,
            },
        },
    ]


def test_default_registry_declares_governed_local_lanes() -> None:
    academy = _academy()
    registry = academy.default_source_lane_registry()
    expected = {
        "video_transcript",
        "reddit_discussion",
        "wikimedia",
        "github_repository",
        "scholarly_standard",
        "web_article",
        "skill_tool_catalog",
        "organization_private",
    }
    expect(set(registry) == expected, sorted(registry))
    for lane_id in expected:
        lane = registry[lane_id]
        data = lane.to_dict()
        for field in (
            "lane_id",
            "label",
            "authorization_required",
            "permission_policy",
            "raw_storage_policy",
            "deletion_policy",
            "live_proof_boundary",
            "fake_fixture_supported",
            "live_actions_enabled",
        ):
            expect(data.get(field) not in (None, ""), f"{lane_id} missing {field}: {data}")
        expect(data["fake_fixture_supported"] is True, data)
        expect(data["live_actions_enabled"] is False, data)
        expect("PG-" in data["live_proof_boundary"] or "policy" in data["live_proof_boundary"], data)
    print("PASS test_default_registry_declares_governed_local_lanes")


def test_fake_acquisition_adapters_cover_enabled_lanes_without_network() -> None:
    academy = _academy()
    request = academy.AcademyAcquisitionRequest(
        request_id="acq-all-lanes",
        requested_at="2026-05-27T00:00:00Z",
        fixtures=tuple(_all_lane_fixture_records()),
    )
    result = academy.acquire_fake_academy_sources(request)
    report = result.report.to_dict()
    expected_lanes = set(academy.default_source_lane_registry())

    expect(report["status"] == "accepted", report)
    expect(report["accepted_count"] == 8, report)
    expect(report["rejected_count"] == 0 and report["proof_gated_count"] == 0, report)
    expect(set(report["lane_counts"]) == expected_lanes, report)
    expect(all(count == 1 for count in report["lane_counts"].values()), report)
    expect(result.no_network is True and result.no_write is True and result.local_only is True, result.to_dict())
    expect(len(result.sources) == 8, result.to_dict())
    expect(not academy.validate_academy_sources(result.sources), result.to_dict())
    expect("content" not in json.dumps(report, sort_keys=True).casefold(), report)
    _assert_secret_free(result.to_dict())

    manifest = academy.build_academy_corpus(
        role_id="role-acquisition",
        role_title="Acquisition Agent",
        topic="safe local Academy acquisition",
        sources=result.sources,
        created_at="2026-05-27T01:00:00Z",
    )
    expect(manifest.evaluation_gate.status == "ready_for_review", manifest.to_dict())
    expect(len(manifest.sources) == 8, manifest.to_dict())
    expect({source["lane_id"] for source in manifest.sources.values()} == expected_lanes, manifest.to_dict())
    application = academy.build_agent_application_plan(
        manifest,
        agent_id="agent-acquisition",
        created_at="2026-05-27T02:00:00Z",
    )
    refresh = academy.build_continuing_education_plan(
        manifest,
        observed_sources={
            source_id: {"content_hash": source["content_hash"]}
            for source_id, source in manifest.sources.items()
        },
        checked_at="2026-05-28T00:00:00Z",
    )
    status = academy.build_academy_review_status(
        manifest=manifest,
        application_plan=application,
        continuing_education_plan=refresh,
        staged_at="2026-05-28T01:00:00Z",
    )
    expect(status["status"] == "ready_for_review", status)
    expect(status["source_count"] == 8 and status["lane_count"] == 8, status)
    expect(status["no_network"] is True and status["no_write"] is True, status)
    expect(status["live_proof_required"] is True, status)
    expect({"PG-PROVIDER", "PG-HERMES"} <= set(status["proof_gates"]), status)
    _assert_secret_free(manifest.to_dict())
    _assert_secret_free(application.to_dict())
    _assert_secret_free(refresh.to_dict())
    _assert_secret_free(status)
    print("PASS test_fake_acquisition_adapters_cover_enabled_lanes_without_network")


def test_fake_acquisition_rejects_unsafe_or_proof_gated_fixtures() -> None:
    academy = _academy()
    registry = academy.default_source_lane_registry()
    disabled = dict(registry)
    disabled["wikimedia"] = dataclasses.replace(registry["wikimedia"], enabled=False)
    fixtures = [
        {
            "source_id": "src-accepted-duplicate-base",
            "lane_id": "web_article",
            "title": "Accepted Fixture",
            "origin_url": "https://example.test/articles/accepted",
            "retrieved_at": "2026-05-27T00:00:00Z",
            "license_status": "public-domain",
            "permission_status": "public_allowed",
            "storage_policy": "derived_summary",
            "content": "A safe local fixture remains accepted while later bad rows are rejected.",
            "citations": ["accepted one", "accepted two", "accepted three"],
            "metadata": {"author_or_org": "Example Lab", "published_at": "2026-05-01", "examples": True},
        },
        {
            "source_id": "src-accepted-duplicate-base",
            "lane_id": "web_article",
            "title": "Duplicate Fixture",
            "origin_url": "https://example.test/articles/duplicate",
            "retrieved_at": "2026-05-27T00:00:00Z",
            "license_status": "public-domain",
            "permission_status": "public_allowed",
            "storage_policy": "derived_summary",
            "content": "This duplicate must not create a second source.",
            "citations": ["duplicate one", "duplicate two", "duplicate three"],
            "metadata": {"author_or_org": "Example Lab", "published_at": "2026-05-02", "examples": True},
        },
        {
            "source_id": "src-disabled-wiki",
            "lane_id": "wikimedia",
            "title": "Disabled Wiki",
            "origin_url": "https://example.test/wiki/disabled",
            "retrieved_at": "2026-05-27T00:00:00Z",
            "license_status": "cc-by-sa",
            "permission_status": "public_allowed",
            "storage_policy": "derived_summary",
            "content": "Disabled lane.",
            "citations": ["disabled one", "disabled two", "disabled three"],
            "metadata": {"revision": "disabled-rev", "examples": True},
        },
        {
            "source_id": "src-unsupported-lane",
            "lane_id": "live_video_crawl",
            "title": "Unsupported Lane",
            "origin_url": "https://example.test/live",
            "retrieved_at": "2026-05-27T00:00:00Z",
            "license_status": "creator-permission",
            "permission_status": "operator_approved",
            "storage_policy": "derived_summary",
            "content": "Unsupported lane.",
            "citations": ["unsupported"],
            "metadata": {"transcript_source": "creator", "transcript_confidence": "0.9"},
        },
        {
            "source_id": "src-missing-permission",
            "lane_id": "web_article",
            "title": "Missing Permission",
            "origin_url": "https://example.test/articles/no-permission",
            "retrieved_at": "2026-05-27T00:00:00Z",
            "license_status": "",
            "permission_status": "",
            "storage_policy": "derived_summary",
            "content": "Missing license and permission metadata.",
            "citations": ["missing permission"],
            "metadata": {"author_or_org": "Example Lab", "published_at": "2026-05-03"},
        },
        {
            "source_id": "src-reddit-raw",
            "lane_id": "reddit_discussion",
            "title": "Raw Reddit",
            "origin_url": "https://example.test/r/example/comments/raw",
            "retrieved_at": "2026-05-27T00:00:00Z",
            "license_status": "platform-restricted",
            "permission_status": "public_allowed",
            "storage_policy": "raw_snapshot",
            "content": "Raw discussion text is not allowed in this unattended local slice.",
            "citations": ["raw thread"],
            "metadata": {"subreddit": "example", "thread_quality": "mixed"},
        },
        {
            "source_id": "src-reddit-deleted",
            "lane_id": "reddit_discussion",
            "title": "Deleted Reddit",
            "origin_url": "https://example.test/r/example/comments/deleted",
            "retrieved_at": "2026-05-27T00:00:00Z",
            "license_status": "platform-restricted",
            "permission_status": "public_allowed",
            "storage_policy": "metadata_only",
            "content": "Deleted user content should not survive without tombstone handling.",
            "citations": ["deleted thread"],
            "metadata": {"subreddit": "example", "thread_quality": "deleted", "deleted": True},
        },
        {
            "source_id": "src-unreviewed-skill",
            "lane_id": "skill_tool_catalog",
            "title": "Unreviewed Skill",
            "origin_url": "https://example.test/skills/unreviewed",
            "retrieved_at": "2026-05-27T00:00:00Z",
            "license_status": "apache-2.0",
            "permission_status": "public_allowed",
            "storage_policy": "metadata_only",
            "content": "An unreviewed public skill must be quarantined.",
            "citations": ["unreviewed skill"],
            "metadata": {"skill_id": "unreviewed", "review_status": "unreviewed", "public_skill": True},
        },
        {
            "source_id": "src-secret-content",
            "lane_id": "web_article",
            "title": "Secret Looking Fixture",
            "origin_url": "https://example.test/articles/secret",
            "retrieved_at": "2026-05-27T00:00:00Z",
            "license_status": "public-domain",
            "permission_status": "public_allowed",
            "storage_policy": "derived_summary",
            "content": "This fixture contains sk-proj-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA and must be blocked.",
            "citations": ["secret fixture"],
            "metadata": {"author_or_org": "Example Lab", "published_at": "2026-05-04"},
        },
        {
            "source_id": "src-live-action",
            "lane_id": "video_transcript",
            "title": "Live Transcript Request",
            "origin_url": "https://example.test/videos/live",
            "retrieved_at": "2026-05-27T00:00:00Z",
            "license_status": "creator-permission",
            "permission_status": "operator_approved",
            "storage_policy": "derived_summary",
            "content": "This row asks for live transcript acquisition.",
            "citations": ["live video"],
            "metadata": {
                "transcript_source": "needs_live_fetch",
                "transcript_confidence": "0.0",
                "live_fetch": True,
                "asr_transcription": True,
            },
        },
    ]
    result = academy.acquire_fake_academy_sources(
        academy.AcademyAcquisitionRequest(
            request_id="acq-fail-closed",
            requested_at="2026-05-27T00:00:00Z",
            fixtures=tuple(fixtures),
        ),
        registry=disabled,
    )
    report = result.report.to_dict()
    report_text = json.dumps(report, sort_keys=True).casefold()
    expect(report["status"] == "partial", report)
    expect(report["accepted_count"] == 1, report)
    expect(report["rejected_count"] == 8, report)
    expect(report["proof_gated_count"] == 1, report)
    for marker in ("duplicated", "disabled", "unsupported", "license", "raw storage", "tombstone", "unreviewed public skill", "secret"):
        expect(marker in report_text, f"{marker} missing from {report_text}")
    expect("live" in json.dumps(report["proof_gated_fixtures"], sort_keys=True).casefold(), report)
    expect("sk-proj" not in json.dumps(result.to_dict(), sort_keys=True).casefold(), result.to_dict())
    _assert_secret_free(result.to_dict())

    manifest = academy.build_academy_corpus(
        role_id="role-acquisition-rejections",
        role_title="Acquisition Rejection Agent",
        topic="acquisition rejection boundaries",
        sources=result.sources,
        created_at="2026-05-27T01:00:00Z",
    )
    rejected_ids = {
        item["source_id"]
        for item in report["rejected_fixtures"]
        if item["source_id"] != "src-accepted-duplicate-base"
    }
    proof_gated_ids = {item["source_id"] for item in report["proof_gated_fixtures"]}
    expect(rejected_ids.isdisjoint(manifest.sources), manifest.to_dict())
    expect(proof_gated_ids.isdisjoint(manifest.sources), manifest.to_dict())
    expect(list(manifest.sources) == ["src-accepted-duplicate-base"], manifest.to_dict())
    print("PASS test_fake_acquisition_rejects_unsafe_or_proof_gated_fixtures")


def test_fake_corpus_curriculum_application_plan_and_quality_are_deterministic() -> None:
    academy = _academy()
    manifest = academy.build_academy_corpus(
        role_id="role-privacy-operator",
        role_title="Privacy Operations Agent",
        topic="privacy preserving agent operations",
        sources=_safe_sources(academy),
        created_at="2026-05-27T00:00:00Z",
    )
    repeat = academy.build_academy_corpus(
        role_id="role-privacy-operator",
        role_title="Privacy Operations Agent",
        topic="privacy preserving agent operations",
        sources=_safe_sources(academy),
        created_at="2026-05-27T09:00:00Z",
    )
    expect(manifest.manifest_id == repeat.manifest_id == "academy-01d202a21e14d8d3", manifest.manifest_id)
    expect(manifest.evaluation_gate.status == "ready_for_review", manifest.evaluation_gate)
    expect(len(manifest.sources) == 3, manifest.to_dict())
    expect(all(record.score >= 70 for record in manifest.quality_records), manifest.to_dict())
    expect(manifest.curriculum.status == "ready_for_review", manifest.curriculum.to_dict())
    expect(len(manifest.lesson_cards) == 3, manifest.lesson_cards)
    expect(set(manifest.citation_map) == {"src-wikimedia-privacy", "src-github-agent-ops", "src-skill-review"}, manifest.citation_map)

    plan = academy.build_agent_application_plan(
        manifest,
        agent_id="agent-privacy",
        created_at="2026-05-27T01:00:00Z",
    )
    expect(plan.status == "ready_for_review", plan.to_dict())
    expect(plan.no_write is True and plan.writes_enabled is False, plan.to_dict())
    expect(any(item["section"] == "academy-expertise" for item in plan.soul_overlay_sections), plan.to_dict())
    expect(any(item["path"].endswith("Curriculum.md") for item in plan.vault_file_intents), plan.to_dict())
    expect(any(item["kind"] == "memory_seed" for item in plan.qmd_memory_seed_intents), plan.to_dict())
    expect(plan.approved_skill_intents[0]["skill_id"] == "academy-retrieval-review", plan.to_dict())
    expect(len(plan.first_week_practice_tasks) >= 3, plan.to_dict())
    _assert_secret_free(manifest.to_dict())
    _assert_secret_free(plan.to_dict())
    print("PASS test_fake_corpus_curriculum_application_plan_and_quality_are_deterministic")


def test_policy_refusals_fail_closed_before_ready_outputs() -> None:
    academy = _academy()
    registry = academy.default_source_lane_registry()

    disabled = dict(registry)
    disabled["wikimedia"] = dataclasses.replace(registry["wikimedia"], enabled=False)

    cases = [
        (
            "disabled lane",
            _safe_sources(academy)[:1],
            disabled,
            "disabled",
        ),
        (
            "missing permission",
            [
                academy.fake_academy_source(
                    source_id="src-missing-permission",
                    lane_id="web_article",
                    title="No Permission Article",
                    origin_url="https://example.test/no-permission",
                    retrieved_at="2026-05-20T00:00:00Z",
                    license_status="",
                    permission_status="",
                    storage_policy="derived_summary",
                    content="A thin article with no permission metadata.",
                    metadata={"author_or_org": "Example Lab", "published_at": "2026-05-20"},
                )
            ],
            registry,
            "license",
        ),
        (
            "reddit raw violation",
            [
                academy.fake_academy_source(
                    source_id="src-reddit-raw",
                    lane_id="reddit_discussion",
                    title="Practitioner Thread",
                    origin_url="https://example.test/r/example/comments/1",
                    retrieved_at="2026-05-20T00:00:00Z",
                    license_status="platform-restricted",
                    permission_status="public_allowed",
                    storage_policy="raw_snapshot",
                    content="User discussion should not be raw stored by this local slice.",
                    metadata={"subreddit": "example", "thread_quality": "mixed"},
                )
            ],
            registry,
            "raw storage",
        ),
        (
            "unreviewed public skill",
            [
                academy.fake_academy_source(
                    source_id="src-unreviewed-skill",
                    lane_id="skill_tool_catalog",
                    title="Unreviewed Public Skill",
                    origin_url="https://example.test/skills/unreviewed",
                    retrieved_at="2026-05-20T00:00:00Z",
                    license_status="apache-2.0",
                    permission_status="public_allowed",
                    storage_policy="metadata_only",
                    content="Skill claims it can run useful tools.",
                    metadata={"public_skill": True, "review_status": "unreviewed", "skill_id": "unreviewed"},
                )
            ],
            registry,
            "unreviewed public skill",
        ),
        (
            "secret metadata",
            [
                academy.fake_academy_source(
                    source_id="src-secret",
                    lane_id="web_article",
                    title="Secret Bearing Source",
                    origin_url="https://example.test/secret",
                    retrieved_at="2026-05-20T00:00:00Z",
                    license_status="public-domain",
                    permission_status="public_allowed",
                    storage_policy="derived_summary",
                    content="A source with unsafe metadata.",
                    metadata={
                        "author_or_org": "Example Lab",
                        "published_at": "2026-05-20",
                        "api_key": "sk-proj-" + "A" * 32,
                    },
                )
            ],
            registry,
            "secret",
        ),
        (
            "deleted reddit tombstone",
            [
                academy.fake_academy_source(
                    source_id="src-reddit-deleted",
                    lane_id="reddit_discussion",
                    title="Deleted Thread",
                    origin_url="https://example.test/r/example/comments/deleted",
                    retrieved_at="2026-05-20T00:00:00Z",
                    license_status="platform-restricted",
                    permission_status="public_allowed",
                    storage_policy="derived_summary",
                    content="Deleted user text should not survive as a live lesson.",
                    metadata={"subreddit": "example", "thread_quality": "deleted", "deleted": True},
                    tombstone_status="active",
                )
            ],
            registry,
            "tombstone",
        ),
        (
            "live action request",
            [
                academy.fake_academy_source(
                    source_id="src-live-fetch",
                    lane_id="video_transcript",
                    title="Live Transcript",
                    origin_url="https://example.test/video",
                    retrieved_at="2026-05-20T00:00:00Z",
                    license_status="creator-permission",
                    permission_status="operator_approved",
                    storage_policy="derived_summary",
                    content="A transcript fixture.",
                    metadata={
                        "transcript_source": "needs_live_fetch",
                        "transcript_confidence": "0.0",
                        "live_fetch": True,
                        "asr_transcription": True,
                    },
                )
            ],
            registry,
            "live",
        ),
    ]

    for label, sources, case_registry, expected in cases:
        try:
            academy.build_academy_corpus(
                role_id="role-policy",
                role_title="Policy Agent",
                topic="policy refusals",
                sources=sources,
                registry=case_registry,
                created_at="2026-05-27T00:00:00Z",
            )
        except academy.ArcLinkAcademyPolicyError as exc:
            message = " ".join(exc.violations).casefold()
            expect(expected in message, f"{label}: {message}")
        else:
            raise AssertionError(f"{label} did not fail closed")
    print("PASS test_policy_refusals_fail_closed_before_ready_outputs")


def test_evaluation_gate_statuses_are_explicit() -> None:
    academy = _academy()
    ready = academy.build_academy_corpus(
        role_id="role-ready",
        role_title="Ready Agent",
        topic="ready topic",
        sources=_safe_sources(academy),
        created_at="2026-05-27T00:00:00Z",
    )
    expect(academy.academy_evaluation_gate(manifest=ready).status == "ready_for_review", ready.to_dict())
    expect(academy.academy_evaluation_gate(manifest=ready, live_proof_required=True).status == "live_proof_pending", ready.to_dict())

    low_quality = [
        academy.fake_academy_source(
            source_id="src-low",
            lane_id="web_article",
            title="Thin Generic Post",
            origin_url="https://example.test/thin",
            retrieved_at="2026-05-20T00:00:00Z",
            license_status="public-domain",
            permission_status="public_allowed",
            storage_policy="derived_summary",
            content="Generic advice.",
            metadata={"author_or_org": "Thin Blog", "published_at": "2026-05-20", "low_signal": True, "seo_content": True},
        )
    ]
    low = academy.build_academy_corpus(
        role_id="role-low",
        role_title="Low Quality Agent",
        topic="thin advice",
        sources=low_quality,
        created_at="2026-05-27T00:00:00Z",
    )
    expect(low.evaluation_gate.status == "blocked_by_quality", low.to_dict())
    blocked = academy.academy_evaluation_gate(policy_violations=["missing permission metadata"])
    expect(blocked.status == "blocked_by_policy", blocked.to_dict())
    print("PASS test_evaluation_gate_statuses_are_explicit")


def test_continuing_education_marks_refresh_states_and_agent_update_gate() -> None:
    academy = _academy()
    sources = _safe_sources(academy)
    sources.extend(
        [
            academy.fake_academy_source(
                source_id="src-web-stale",
                lane_id="web_article",
                title="Weekly Operations Article",
                origin_url="https://example.test/ops-weekly",
                retrieved_at="2026-05-01T00:00:00Z",
                license_status="public-domain",
                permission_status="public_allowed",
                storage_policy="derived_summary",
                content="This article needs regular refresh because operations guidance changes.",
                citations=["ops weekly"],
                metadata={
                    "author_or_org": "Example Ops Lab",
                    "published_at": "2026-05-01",
                    "freshness_days": 7,
                    "examples": True,
                },
            ),
            academy.fake_academy_source(
                source_id="src-paper-old",
                lane_id="scholarly_standard",
                title="Prior Standard",
                origin_url="https://example.test/standards/old",
                retrieved_at="2026-05-01T00:00:00Z",
                license_status="open-access",
                permission_status="public_allowed",
                storage_policy="metadata_only",
                content="An older standard with a newer revision.",
                citations=["standard old"],
                metadata={"identifier": "STD-OLD", "venue_or_body": "Example Standards Body", "official": True},
            ),
            academy.fake_academy_source(
                source_id="src-reddit-watch",
                lane_id="reddit_discussion",
                title="Watched Practitioner Thread",
                origin_url="https://example.test/r/example/comments/watch",
                retrieved_at="2026-05-10T00:00:00Z",
                license_status="platform-restricted",
                permission_status="public_allowed",
                storage_policy="metadata_only",
                content="Non-identifying pattern card from practitioner discussion.",
                citations=["thread metadata"],
                metadata={"subreddit": "example", "thread_quality": "watched", "practitioner_signal": True},
            ),
        ]
    )
    manifest = academy.build_academy_corpus(
        role_id="role-refresh",
        role_title="Refresh Agent",
        topic="continuing education",
        sources=sources,
        created_at="2026-05-27T00:00:00Z",
    )
    observed = {
        "src-wikimedia-privacy": {"content_hash": manifest.sources["src-wikimedia-privacy"]["content_hash"]},
        "src-github-agent-ops": {"content_hash": "changed-" + manifest.sources["src-github-agent-ops"]["content_hash"]},
        "src-skill-review": {"removed": True},
        "src-web-stale": {"content_hash": manifest.sources["src-web-stale"]["content_hash"]},
        "src-paper-old": {"superseded_by": "src-paper-new"},
        "src-reddit-watch": {"deleted": True},
    }
    plan = academy.build_continuing_education_plan(
        manifest,
        observed_sources=observed,
        checked_at="2026-06-15T00:00:00Z",
    )
    statuses = {item["source_id"]: item["status"] for item in plan.source_refreshes}
    expect(statuses["src-wikimedia-privacy"] == "unchanged", statuses)
    expect(statuses["src-github-agent-ops"] == "changed", statuses)
    expect(statuses["src-skill-review"] == "removed", statuses)
    expect(statuses["src-web-stale"] == "stale", statuses)
    expect(statuses["src-paper-old"] == "superseded", statuses)
    expect(statuses["src-reddit-watch"] == "tombstoned", statuses)
    expect(plan.agent_update_status == "blocked", plan.to_dict())
    expect("src-reddit-watch" in plan.blocked_source_ids, plan.to_dict())
    _assert_secret_free(plan.to_dict())
    print("PASS test_continuing_education_marks_refresh_states_and_agent_update_gate")


def test_weekly_continuing_education_review_classifies_changes_and_keeps_no_write_boundary() -> None:
    academy = _academy()
    sources = _safe_sources(academy)
    sources.extend(
        [
            academy.fake_academy_source(
                source_id="src-weekly-stale",
                lane_id="web_article",
                title="Weekly Product Operations Article",
                origin_url="https://example.test/articles/product-ops",
                retrieved_at="2026-05-01T00:00:00Z",
                license_status="public-domain",
                permission_status="public_allowed",
                storage_policy="derived_summary",
                content="Weekly operations advice should be refreshed before it updates an Agent.",
                citations=["ops article", "ops appendix", "ops checklist"],
                metadata={
                    "author_or_org": "Example Ops Lab",
                    "published_at": "2026-05-01",
                    "freshness_days": 7,
                    "examples": True,
                },
            ),
            academy.fake_academy_source(
                source_id="src-weekly-standard",
                lane_id="scholarly_standard",
                title="Superseded Standard",
                origin_url="https://example.test/standards/old",
                retrieved_at="2026-05-01T00:00:00Z",
                license_status="open-access",
                permission_status="public_allowed",
                storage_policy="metadata_only",
                content="A prior standard with a newer revision.",
                citations=["standard abstract", "standard status", "standard errata"],
                metadata={"identifier": "STD-OLD", "venue_or_body": "Example Standards Body", "official": True},
            ),
            academy.fake_academy_source(
                source_id="src-weekly-discussion",
                lane_id="reddit_discussion",
                title="Discussion Pattern Card",
                origin_url="https://example.test/r/example/comments/watch",
                retrieved_at="2026-05-10T00:00:00Z",
                license_status="platform-restricted",
                permission_status="public_allowed",
                storage_policy="metadata_only",
                content="A non-identifying pattern card from practitioner discussion.",
                citations=["thread metadata", "moderator correction", "accepted answer"],
                metadata={"subreddit": "example", "thread_quality": "watched", "practitioner_signal": True},
            ),
        ]
    )
    manifest = academy.build_academy_corpus(
        role_id="role-weekly-review",
        role_title="Weekly Review Agent",
        topic="weekly continuing education",
        sources=sources,
        created_at="2026-05-27T00:00:00Z",
    )
    review = academy.build_continuing_education_plan(
        manifest,
        observed_sources={
            "src-wikimedia-privacy": {"content_hash": manifest.sources["src-wikimedia-privacy"]["content_hash"]},
            "src-github-agent-ops": {"content_hash": "changed-" + manifest.sources["src-github-agent-ops"]["content_hash"]},
            "src-skill-review": {"removed": True},
            "src-weekly-stale": {"content_hash": manifest.sources["src-weekly-stale"]["content_hash"]},
            "src-weekly-standard": {"superseded_by": "src-weekly-standard-v2"},
            "src-weekly-discussion": {"deleted": True},
        },
        checked_at="2026-06-15T00:00:00Z",
        next_review_at="2026-06-22T00:00:00Z",
    )
    data = review.to_dict()
    counts = data["source_state_counts"]
    expect(data["artifact_kind"] == "academy-weekly-continuing-education-review", data)
    expect(counts["unchanged"] == 1, counts)
    expect(counts["changed"] == 1, counts)
    expect(counts["removed"] == 1, counts)
    expect(counts["stale"] == 1, counts)
    expect(counts["superseded"] == 1, counts)
    expect(counts["tombstoned"] == 1 and counts["deleted_tombstoned"] == 1, counts)
    expect(counts["review_needed"] == 3, counts)
    expect(data["blocked_source_count"] == 2, data)
    expect(data["review_needed_count"] == 3, data)
    expect(data["next_review_at"] == "2026-06-22T00:00:00Z", data)
    expect(data["local_only"] is True and data["no_network"] is True and data["no_write"] is True, data)
    expect(data["writes_enabled"] is False and data["live_proof_required"] is True, data)
    expect({"PG-PROVIDER", "PG-HERMES"} <= set(data["proof_gates"]), data)
    rendered = json.dumps(data, sort_keys=True).casefold()
    expect("weekly operations advice should" not in rendered, rendered)
    expect("content" not in rendered, rendered)
    _assert_secret_free(data)

    unsafe_observed = [
        {"src-wikimedia-privacy": {"raw_content": "raw source text should not be accepted"}},
        {"src-wikimedia-privacy": {"workspace_path": "/home/example/SOUL.md"}},
        {"src-wikimedia-privacy": {"content_hash": "../escape"}},
        {"src-wikimedia-privacy": {"live_fetch": True}},
        {"src-wikimedia-privacy": {"api_key": "sk-proj-" + ("A" * 32)}},
    ]
    for observed in unsafe_observed:
        try:
            academy.build_continuing_education_plan(
                manifest,
                observed_sources=observed,
                checked_at="2026-06-15T00:00:00Z",
            )
        except academy.ArcLinkAcademyPolicyError as exc:
            message = " ".join(exc.violations).casefold()
            expect(
                any(marker in message for marker in ("raw content", "workspace", "absolute path", "traversal", "live", "secret")),
                message,
            )
        else:
            raise AssertionError(f"unsafe weekly observed-source payload passed: {observed}")
    print("PASS test_weekly_continuing_education_review_classifies_changes_and_keeps_no_write_boundary")


def test_academy_graduation_gate_blocks_without_live_provider_and_workspace_proof() -> None:
    academy = _academy()
    manifest = academy.build_academy_corpus(
        role_id="role-graduation",
        role_title="Graduation Agent",
        topic="graduation proof boundaries",
        sources=_safe_sources(academy),
        created_at="2026-05-27T00:00:00Z",
    )
    blocked = academy.academy_graduation_gate(manifest=manifest)
    expect(blocked.status == "blocked_by_live_proof", blocked.to_dict())
    expect({"PG-PROVIDER", "PG-HERMES"} <= set(blocked.required_live_proofs), blocked.to_dict())
    expect(not {"trained", "graduated", "applied"} & {blocked.status}, blocked.to_dict())

    policy = academy.academy_graduation_gate(
        manifest=manifest,
        policy_violations=["source policy decision missing"],
    )
    expect(policy.status == "blocked_by_policy", policy.to_dict())

    ready_for_review = academy.academy_graduation_gate(
        manifest=manifest,
        live_proof_evidence={
            "PG-PROVIDER": {"status": "passed", "evidence_id": "pg-provider-scratch"},
            "PG-HERMES": {"status": "passed", "evidence_id": "pg-hermes-scratch"},
        },
    )
    expect(ready_for_review.status == "ready_for_review", ready_for_review.to_dict())
    expect(not {"trained", "graduated", "applied"} & {ready_for_review.status}, ready_for_review.to_dict())
    _assert_secret_free(blocked.to_dict())
    _assert_secret_free(policy.to_dict())
    _assert_secret_free(ready_for_review.to_dict())
    print("PASS test_academy_graduation_gate_blocks_without_live_provider_and_workspace_proof")


def test_review_status_is_compact_secret_free_and_live_proof_honest() -> None:
    academy = _academy()
    manifest = academy.build_academy_corpus(
        role_id="role-review",
        role_title="Review Agent",
        topic="reviewable local Academy status",
        sources=_safe_sources(academy),
        created_at="2026-05-27T00:00:00Z",
    )
    application = academy.build_agent_application_plan(
        manifest,
        agent_id="agent-review",
        created_at="2026-05-27T01:00:00Z",
    )
    refresh = academy.build_continuing_education_plan(
        manifest,
        observed_sources={
            "src-wikimedia-privacy": {"content_hash": manifest.sources["src-wikimedia-privacy"]["content_hash"]},
            "src-github-agent-ops": {"content_hash": manifest.sources["src-github-agent-ops"]["content_hash"]},
            "src-skill-review": {"content_hash": manifest.sources["src-skill-review"]["content_hash"]},
        },
        checked_at="2026-05-28T00:00:00Z",
    )
    status = academy.build_academy_review_status(
        manifest=manifest,
        application_plan=application,
        continuing_education_plan=refresh,
        staged_at="2026-05-28T01:00:00Z",
    )

    expect(status["status"] == "ready_for_review", str(status))
    expect(status["manifest_id"] == manifest.manifest_id, str(status))
    expect(status["source_count"] == 3, str(status))
    expect(status["lane_count"] == 3, str(status))
    expect(status["quality"]["accepted"] == 3, str(status))
    expect(status["application_status"] == "ready_for_review", str(status))
    expect(status["continuing_education_status"] == "ready_for_agent_update", str(status))
    expect(status["agent_update_status"] == "ready", str(status))
    expect(status["local_only"] is True and status["no_write"] is True, str(status))
    expect(status["writes_enabled"] is False, str(status))
    expect(status["live_proof_required"] is True, str(status))
    expect({"PG-PROVIDER", "PG-HERMES"} <= set(status["proof_gates"]), str(status))
    expect("content" not in json.dumps(status, sort_keys=True).casefold(), str(status))
    _assert_secret_free(status)

    not_started = academy.build_academy_review_status()
    expect(not_started["status"] == "not_started", str(not_started))
    expect(not_started["source_count"] == 0, str(not_started))
    print("PASS test_review_status_is_compact_secret_free_and_live_proof_honest")


def test_academy_application_preview_result_is_secret_free_no_write() -> None:
    academy = _academy()
    manifest = academy.build_academy_corpus(
        role_id="role-preview",
        role_title="Preview Agent",
        topic="no-write application preview",
        sources=_safe_sources(academy),
        created_at="2026-05-27T00:00:00Z",
    )
    application = academy.build_agent_application_plan(
        manifest,
        agent_id="agent-preview",
        created_at="2026-05-27T01:00:00Z",
    )
    status = academy.build_academy_review_status(
        manifest=manifest,
        application_plan=application,
        staged_at="2026-05-27T02:00:00Z",
    )
    status["recipe_id"] = "crew-preview"
    status["review_persisted"] = True
    request = academy.build_academy_application_preview_request(
        {
            "request_id": "academy-preview-request",
            "user_id": "user-preview",
            "recipe_id": "crew-preview",
            "manifest_id": manifest.manifest_id,
            "application_plan_id": application.plan_id,
            "agent_id": "agent-preview",
            "local_only": True,
            "no_write": True,
            "writes_enabled": False,
            "proof_gates": ["PG-PROVIDER", "PG-HERMES"],
        },
        requested_at="2026-05-27T03:00:00Z",
    )
    result = academy.build_academy_application_preview_result(
        request,
        staged_status=status,
        created_at="2026-05-27T04:00:00Z",
    )
    data = result.to_dict()
    expect(data["status"] == "ready_for_application_proof", str(data))
    expect(data["local_only"] is True and data["no_write"] is True, str(data))
    expect(data["writes_enabled"] is False, str(data))
    expect(data["mutation_performed"] is False, str(data))
    expect(data["workspace_mutation_performed"] is False, str(data))
    expect(data["filesystem_mutation_performed"] is False, str(data))
    expect(data["executor_called"] is False, str(data))
    expect({"PG-PROVIDER", "PG-HERMES"} <= set(data["proof_gates"]), str(data))
    rendered = json.dumps(data, sort_keys=True).casefold()
    expect("content" not in rendered and "secret://" not in rendered, rendered)
    _assert_secret_free(data)
    print("PASS test_academy_application_preview_result_is_secret_free_no_write")


def test_academy_application_worker_request_refuses_workspace_writes() -> None:
    academy = _academy()
    manifest = academy.build_academy_corpus(
        role_id="role-preview-refusal",
        role_title="Preview Refusal Agent",
        topic="unsafe application preview",
        sources=_safe_sources(academy),
        created_at="2026-05-27T00:00:00Z",
    )
    application = academy.build_agent_application_plan(
        manifest,
        agent_id="agent-preview-refusal",
        created_at="2026-05-27T01:00:00Z",
    )
    status = academy.build_academy_review_status(
        manifest=manifest,
        application_plan=application,
        staged_at="2026-05-27T02:00:00Z",
    )
    status["recipe_id"] = "crew-preview-refusal"
    status["review_persisted"] = True
    unsafe_requests = [
        {
            "request_id": "academy-preview-write",
            "user_id": "user-preview",
            "recipe_id": "crew-preview-refusal",
            "manifest_id": manifest.manifest_id,
            "application_plan_id": application.plan_id,
            "agent_id": "agent-preview-refusal",
            "writes_enabled": True,
            "proof_gates": ["PG-PROVIDER", "PG-HERMES"],
        },
        {
            "request_id": "academy-preview-workspace",
            "user_id": "user-preview",
            "recipe_id": "crew-preview-refusal",
            "manifest_id": manifest.manifest_id,
            "application_plan_id": application.plan_id,
            "agent_id": "agent-preview-refusal",
            "workspace_path": "/home/user/.local/share/arclink-agent/hermes-home/SOUL.md",
            "proof_gates": ["PG-PROVIDER", "PG-HERMES"],
        },
        {
            "request_id": "academy-preview-secret",
            "user_id": "user-preview",
            "recipe_id": "crew-preview-refusal",
            "manifest_id": manifest.manifest_id,
            "application_plan_id": application.plan_id,
            "agent_id": "agent-preview-refusal",
            "raw_content": "sk-proj-" + ("A" * 32),
            "proof_gates": ["PG-PROVIDER", "PG-HERMES"],
        },
    ]
    for payload in unsafe_requests:
        try:
            academy.build_academy_application_preview_result(payload, staged_status=status)
        except academy.ArcLinkAcademyPolicyError as exc:
            message = " ".join(exc.violations).casefold()
            expect(
                any(marker in message for marker in ("writes_enabled", "workspace", "absolute path", "secret", "raw content")),
                message,
            )
        else:
            raise AssertionError(f"unsafe Academy preview request passed: {payload}")

    mismatched = dict(unsafe_requests[0])
    mismatched["writes_enabled"] = False
    mismatched["manifest_id"] = "academy-other"
    try:
        academy.build_academy_application_preview_result(mismatched, staged_status=status)
    except academy.ArcLinkAcademyPolicyError as exc:
        expect("manifest_id" in " ".join(exc.violations), str(exc.violations))
    else:
        raise AssertionError("mismatched Academy manifest preview request passed")
    print("PASS test_academy_application_worker_request_refuses_workspace_writes")


if __name__ == "__main__":
    test_default_registry_declares_governed_local_lanes()
    test_fake_acquisition_adapters_cover_enabled_lanes_without_network()
    test_fake_acquisition_rejects_unsafe_or_proof_gated_fixtures()
    test_fake_corpus_curriculum_application_plan_and_quality_are_deterministic()
    test_policy_refusals_fail_closed_before_ready_outputs()
    test_evaluation_gate_statuses_are_explicit()
    test_continuing_education_marks_refresh_states_and_agent_update_gate()
    test_weekly_continuing_education_review_classifies_changes_and_keeps_no_write_boundary()
    test_academy_graduation_gate_blocks_without_live_provider_and_workspace_proof()
    test_review_status_is_compact_secret_free_and_live_proof_honest()
    test_academy_application_preview_result_is_secret_free_no_write()
    test_academy_application_worker_request_refuses_workspace_writes()
    print("PASS all 12 ArcLink Academy Trainer tests")
