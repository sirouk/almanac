#!/usr/bin/env python3
"""Local Academy Trainer schemas and fail-closed planning helpers.

This module intentionally owns only the no-network, no-write Academy foundation.
Live crawling, ASR/transcription, provider generation, qmd writes, Hermes-home
mutation, and dashboard/Raven workflows stay behind their proof and policy
gates.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from arclink_secrets_regex import contains_secret_material, redact_secret_material


ALLOWED_STORAGE_POLICIES = {"metadata_only", "derived_summary", "raw_snapshot"}
PASSING_GATE_STATUSES = {"ready_for_review", "live_proof_pending"}
ACADEMY_LIVE_PROOF_GATES = ("PG-PROVIDER", "PG-HERMES")
LIVE_ACTION_FLAGS = {
    "live_fetch",
    "live_crawl",
    "network_fetch",
    "provider_generation",
    "asr_transcription",
    "external_api_call",
    "write_to_vault",
    "write_to_qmd",
    "write_to_hermes_home",
}
ACADEMY_APPLICATION_PREVIEW_PROOF_GATES = ("PG-PROVIDER", "PG-HERMES")
ACADEMY_APPLICATION_PREVIEW_STATUSES = {"ready_for_review", "live_proof_pending"}
ACADEMY_APPLICATION_PREVIEW_LIVE_FLAGS = LIVE_ACTION_FLAGS | {
    "apply",
    "apply_now",
    "execute",
    "execute_now",
    "mutation_enabled",
    "run_provider",
    "run_hermes",
    "workspace_apply",
    "write",
    "writes",
    "writes_enabled",
}
ACADEMY_APPLICATION_PREVIEW_FORBIDDEN_KEYS = {
    "content",
    "raw_content",
    "source_content",
    "source_text",
    "prompt",
    "completion",
    "transcript",
    "body",
    "text_dump",
    "vault_path",
    "qmd_path",
    "hermes_home",
    "hermes-home",
    "workspace_path",
    "host_path",
    "filesystem_path",
    "skill_write_path",
    "soul_path",
}
ACADEMY_APPLICATION_PREVIEW_FORBIDDEN_VALUE_TERMS = (
    "../",
    "..\\",
    "/home/",
    "/root/",
    "soul.md",
    "vault/",
    "qmd/",
    "hermes_home",
    "hermes-home",
    "workspace",
    "docker",
    "compose",
    "systemd",
    "ssh ",
)
ACADEMY_WEEKLY_REVIEW_FORBIDDEN_KEYS = ACADEMY_APPLICATION_PREVIEW_FORBIDDEN_KEYS | {
    "raw",
    "raw_text",
    "raw_transcript",
    "html",
    "markdown",
}
ACADEMY_WEEKLY_REVIEW_FORBIDDEN_FLAGS = LIVE_ACTION_FLAGS | {
    "apply",
    "apply_now",
    "execute",
    "execute_now",
    "mutation_enabled",
    "run_provider",
    "run_hermes",
    "workspace_apply",
    "write",
    "writes",
    "writes_enabled",
}
ACADEMY_WEEKLY_STATE_KEYS = (
    "unchanged",
    "changed",
    "stale",
    "superseded",
    "removed",
    "tombstoned",
    "deleted_tombstoned",
    "review_needed",
)
OPEN_LICENSE_STATUSES = {
    "apache-2.0",
    "cc-by",
    "cc-by-sa",
    "cc0",
    "creator-permission",
    "internal-approved",
    "mit",
    "open-access",
    "operator-approved",
    "public-domain",
}
DENIED_STATUSES = {"", "missing", "unknown", "pending", "denied", "unlicensed", "forbidden"}
SECRET_KEY_RE = re.compile(
    r"(?i)(?:^|[_-])(?:token|api[_-]?key|apikey|password|passwd|secret|credential|authorization|cookie|jwt|oauth)(?:[_-]|$)"
)


class ArcLinkAcademyPolicyError(ValueError):
    """Raised when Academy local artifacts would overclaim or store unsafe data."""

    def __init__(self, violations: Sequence[str]) -> None:
        clean = [str(item or "").strip() for item in violations if str(item or "").strip()]
        self.violations = clean or ["Academy policy violation"]
        super().__init__("; ".join(self.violations))


@dataclass(frozen=True)
class SourceLanePolicy:
    lane_id: str
    label: str
    authorization_required: str
    permission_policy: str
    raw_storage_policy: str
    deletion_policy: str
    live_proof_boundary: str
    fake_fixture_supported: bool
    enabled: bool = True
    live_actions_enabled: bool = False
    required_metadata: tuple[str, ...] = ()
    quality_weight: int = 8

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["required_metadata"] = list(self.required_metadata)
        return payload


@dataclass(frozen=True)
class AcademySource:
    source_id: str
    lane_id: str
    title: str
    origin_url: str
    retrieved_at: str
    license_status: str
    permission_status: str
    storage_policy: str
    content: str = ""
    citations: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    review_status: str = "reviewed"
    tombstone_status: str = "active"
    acquisition_mode: str = "local_fixture"

    def content_hash(self) -> str:
        return _sha256(_clean_space(self.content, limit=20_000))[:32]

    def source_signature(self) -> str:
        return _sha256(
            _stable_json(
                {
                    "source_id": self.source_id,
                    "lane_id": self.lane_id,
                    "title": self.title,
                    "origin_url": self.origin_url,
                    "retrieved_at": self.retrieved_at,
                    "license_status": self.license_status,
                    "permission_status": self.permission_status,
                    "storage_policy": self.storage_policy,
                    "content_hash": self.content_hash(),
                    "citations": list(self.citations),
                    "metadata": dict(self.metadata),
                    "review_status": self.review_status,
                    "tombstone_status": self.tombstone_status,
                    "acquisition_mode": self.acquisition_mode,
                }
            )
        )


@dataclass(frozen=True)
class AcademyAcquisitionRequest:
    request_id: str
    fixtures: tuple[Any, ...] = ()
    requested_at: str = ""
    acquisition_mode: str = "local_fixture"
    no_network: bool = True
    no_write: bool = True
    live_actions_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "requested_at": self.requested_at,
            "acquisition_mode": self.acquisition_mode,
            "fixture_count": len(self.fixtures),
            "no_network": self.no_network,
            "no_write": self.no_write,
            "live_actions_enabled": self.live_actions_enabled,
        }


@dataclass(frozen=True)
class AcademyAcquisitionReport:
    request_id: str
    requested_at: str
    status: str
    accepted_count: int
    rejected_count: int
    proof_gated_count: int
    lane_counts: Mapping[str, int] = field(default_factory=dict)
    accepted_sources: tuple[dict[str, Any], ...] = ()
    rejected_fixtures: tuple[dict[str, Any], ...] = ()
    proof_gated_fixtures: tuple[dict[str, Any], ...] = ()
    proof_gates: tuple[str, ...] = ("PG-PROVIDER", "PG-HERMES")
    no_network: bool = True
    no_write: bool = True
    live_proof_required: bool = True
    local_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "requested_at": self.requested_at,
            "status": self.status,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "proof_gated_count": self.proof_gated_count,
            "lane_counts": dict(self.lane_counts),
            "accepted_sources": [dict(item) for item in self.accepted_sources],
            "rejected_fixtures": [dict(item) for item in self.rejected_fixtures],
            "proof_gated_fixtures": [dict(item) for item in self.proof_gated_fixtures],
            "proof_gates": list(self.proof_gates),
            "no_network": self.no_network,
            "no_write": self.no_write,
            "live_proof_required": self.live_proof_required,
            "local_only": self.local_only,
        }


@dataclass(frozen=True)
class AcademyAcquisitionResult:
    request: AcademyAcquisitionRequest
    accepted_sources: tuple[AcademySource, ...]
    report: AcademyAcquisitionReport
    rejected_fixtures: tuple[dict[str, Any], ...] = ()
    proof_gated_fixtures: tuple[dict[str, Any], ...] = ()
    artifact_kind: str = "academy-local-acquisition-result"
    no_network: bool = True
    no_write: bool = True
    local_only: bool = True

    @property
    def sources(self) -> tuple[AcademySource, ...]:
        return self.accepted_sources

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_kind": self.artifact_kind,
            "request": self.request.to_dict(),
            "report": self.report.to_dict(),
            "accepted_sources": [dict(item) for item in self.report.accepted_sources],
            "rejected_fixtures": [dict(item) for item in self.rejected_fixtures],
            "proof_gated_fixtures": [dict(item) for item in self.proof_gated_fixtures],
            "no_network": self.no_network,
            "no_write": self.no_write,
            "local_only": self.local_only,
            "live_proof_required": True,
        }


@dataclass(frozen=True)
class QualityRecord:
    source_id: str
    lane_id: str
    score: int
    status: str
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


@dataclass(frozen=True)
class CurriculumRecord:
    role_id: str
    role_title: str
    topic: str
    status: str
    modules: tuple[dict[str, Any], ...] = ()
    practice_tasks: tuple[str, ...] = ()
    evaluation_tasks: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["modules"] = [dict(item) for item in self.modules]
        payload["practice_tasks"] = list(self.practice_tasks)
        payload["evaluation_tasks"] = list(self.evaluation_tasks)
        return payload


@dataclass(frozen=True)
class EvaluationGate:
    status: str
    reasons: tuple[str, ...] = ()
    blocked_source_ids: tuple[str, ...] = ()
    required_live_proofs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        payload["blocked_source_ids"] = list(self.blocked_source_ids)
        payload["required_live_proofs"] = list(self.required_live_proofs)
        return payload


@dataclass(frozen=True)
class CorpusManifest:
    manifest_id: str
    role_id: str
    role_title: str
    topic: str
    created_at: str
    sources: Mapping[str, dict[str, Any]]
    quality_records: tuple[QualityRecord, ...]
    citation_map: Mapping[str, list[dict[str, Any]]]
    lesson_cards: tuple[dict[str, Any], ...]
    curriculum: CurriculumRecord
    evaluation_gate: EvaluationGate
    policy_violations: tuple[str, ...] = ()
    artifact_kind: str = "academy-local-corpus-manifest"
    no_network: bool = True
    no_write: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_kind": self.artifact_kind,
            "manifest_id": self.manifest_id,
            "role_id": self.role_id,
            "role_title": self.role_title,
            "topic": self.topic,
            "created_at": self.created_at,
            "sources": {key: dict(value) for key, value in self.sources.items()},
            "quality_records": [record.to_dict() for record in self.quality_records],
            "citation_map": {key: [dict(item) for item in value] for key, value in self.citation_map.items()},
            "lesson_cards": [dict(item) for item in self.lesson_cards],
            "curriculum": self.curriculum.to_dict(),
            "evaluation_gate": self.evaluation_gate.to_dict(),
            "policy_violations": list(self.policy_violations),
            "no_network": self.no_network,
            "no_write": self.no_write,
        }


@dataclass(frozen=True)
class AgentApplicationPlan:
    plan_id: str
    manifest_id: str
    agent_id: str
    role_id: str
    status: str
    created_at: str
    no_write: bool
    writes_enabled: bool
    soul_overlay_sections: tuple[dict[str, Any], ...] = ()
    vault_file_intents: tuple[dict[str, Any], ...] = ()
    qmd_memory_seed_intents: tuple[dict[str, Any], ...] = ()
    approved_skill_intents: tuple[dict[str, Any], ...] = ()
    first_week_practice_tasks: tuple[str, ...] = ()
    evaluation_tasks: tuple[str, ...] = ()
    blocked_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in (
            "soul_overlay_sections",
            "vault_file_intents",
            "qmd_memory_seed_intents",
            "approved_skill_intents",
        ):
            payload[key] = [dict(item) for item in payload[key]]
        payload["first_week_practice_tasks"] = list(self.first_week_practice_tasks)
        payload["evaluation_tasks"] = list(self.evaluation_tasks)
        payload["blocked_reasons"] = list(self.blocked_reasons)
        return payload


@dataclass(frozen=True)
class ContinuingEducationPlan:
    plan_id: str
    manifest_id: str
    checked_at: str
    status: str
    agent_update_status: str
    source_refreshes: tuple[dict[str, Any], ...] = ()
    blocked_source_ids: tuple[str, ...] = ()
    review_required_source_ids: tuple[str, ...] = ()
    review_id: str = ""
    next_review_at: str = ""
    source_state_counts: Mapping[str, int] = field(default_factory=dict)
    review_needed_count: int = 0
    blocked_source_count: int = 0
    proof_gates: tuple[str, ...] = ACADEMY_LIVE_PROOF_GATES
    no_network: bool = True
    no_write: bool = True
    writes_enabled: bool = False
    local_only: bool = True
    live_proof_required: bool = True
    artifact_kind: str = "academy-weekly-continuing-education-review"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source_refreshes"] = [dict(item) for item in self.source_refreshes]
        payload["blocked_source_ids"] = list(self.blocked_source_ids)
        payload["review_required_source_ids"] = list(self.review_required_source_ids)
        payload["source_state_counts"] = dict(self.source_state_counts)
        payload["proof_gates"] = list(self.proof_gates)
        return payload


@dataclass(frozen=True)
class AcademyApplicationPreviewRequest:
    request_id: str
    user_id: str
    recipe_id: str
    manifest_id: str
    application_plan_id: str
    agent_id: str
    target_kind: str = "user"
    target_id: str = ""
    requested_at: str = ""
    requested_by: str = ""
    local_only: bool = True
    no_write: bool = True
    writes_enabled: bool = False
    proof_gates: tuple[str, ...] = ACADEMY_APPLICATION_PREVIEW_PROOF_GATES
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "recipe_id": self.recipe_id,
            "manifest_id": self.manifest_id,
            "application_plan_id": self.application_plan_id,
            "agent_id": self.agent_id,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "requested_at": self.requested_at,
            "requested_by": self.requested_by,
            "local_only": self.local_only,
            "no_write": self.no_write,
            "writes_enabled": self.writes_enabled,
            "proof_gates": list(self.proof_gates),
            "metadata_keys": sorted(str(key) for key in dict(self.metadata or {}).keys()),
        }


@dataclass(frozen=True)
class AcademyApplicationPreviewResult:
    request: AcademyApplicationPreviewRequest
    status: str
    summary: str
    staged_status: str
    application_status: str
    source_count: int
    lane_count: int
    proof_gates: tuple[str, ...]
    created_at: str
    operation_kind: str = "academy_application_preview"
    local_only: bool = True
    no_write: bool = True
    writes_enabled: bool = False
    mutation_performed: bool = False
    workspace_mutation_performed: bool = False
    filesystem_mutation_performed: bool = False
    executor_called: bool = False
    live_proof_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "request": self.request.to_dict(),
            "user_id": self.request.user_id,
            "recipe_id": self.request.recipe_id,
            "manifest_id": self.request.manifest_id,
            "application_plan_id": self.request.application_plan_id,
            "agent_id": self.request.agent_id,
            "staged_status": self.staged_status,
            "application_status": self.application_status,
            "source_count": self.source_count,
            "lane_count": self.lane_count,
            "proof_gates": list(self.proof_gates),
            "created_at": self.created_at,
            "operation_kind": self.operation_kind,
            "local_only": self.local_only,
            "no_write": self.no_write,
            "writes_enabled": self.writes_enabled,
            "mutation_performed": self.mutation_performed,
            "workspace_mutation_performed": self.workspace_mutation_performed,
            "filesystem_mutation_performed": self.filesystem_mutation_performed,
            "executor_called": self.executor_called,
            "live_proof_required": self.live_proof_required,
            "next_action": "Run authorized PG-HERMES workspace application proof before applying Academy artifacts to an Agent.",
        }


def default_source_lane_registry() -> dict[str, SourceLanePolicy]:
    """Return the shipped local Academy lane registry.

    All lanes support fake/local fixtures here. Live acquisition remains off and
    must be proven through the named gate before any caller claims it works.
    """
    lanes = [
        SourceLanePolicy(
            lane_id="video_transcript",
            label="Video and transcript",
            authorization_required="creator, platform, Captain, or operator transcript authorization",
            permission_policy="transcripts require explicit access rights; ASR requires separate approval",
            raw_storage_policy="raw transcript only with recorded authorization; derived summaries preferred",
            deletion_policy="tombstone transcript snapshots when rights are revoked or source disappears",
            live_proof_boundary="policy decision plus PG-PROVIDER transcription proof",
            fake_fixture_supported=True,
            required_metadata=("transcript_source", "transcript_confidence"),
            quality_weight=10,
        ),
        SourceLanePolicy(
            lane_id="reddit_discussion",
            label="Reddit and practitioner discussion",
            authorization_required="official API/OAuth access and platform retention policy",
            permission_policy="raw user content is restricted; derived non-identifying lessons require policy approval",
            raw_storage_policy="never in the unattended local slice",
            deletion_policy="deleted or removed content must be tombstoned before Agent update",
            live_proof_boundary="policy decision plus PG-PROVIDER/PG-BOTS proof where used",
            fake_fixture_supported=True,
            required_metadata=("subreddit", "thread_quality"),
            quality_weight=7,
        ),
        SourceLanePolicy(
            lane_id="wikimedia",
            label="Wikipedia and Wikimedia",
            authorization_required="public API use with revision and license metadata",
            permission_policy="CC/license metadata required; use as map and bibliography, not sole authority",
            raw_storage_policy="allowed with compatible license, but derived summaries preferred",
            deletion_policy="track revision and supersession; keep citation to the exact revision when possible",
            live_proof_boundary="PG-PROVIDER for live generation, local fixtures only here",
            fake_fixture_supported=True,
            required_metadata=("revision",),
            quality_weight=12,
        ),
        SourceLanePolicy(
            lane_id="github_repository",
            label="GitHub repositories and systems practice",
            authorization_required="public or organization-approved repository access and license review",
            permission_policy="license and selected-file manifest required before copying code or docs",
            raw_storage_policy="raw files only when license and product policy allow; derived patterns preferred",
            deletion_policy="track commit/tag and repository archived/deleted state",
            live_proof_boundary="PG-HERMES workspace proof for applied repo-derived training",
            fake_fixture_supported=True,
            required_metadata=("repo", "commit_or_tag", "license"),
            quality_weight=11,
        ),
        SourceLanePolicy(
            lane_id="scholarly_standard",
            label="Scholarly, standards, and whitepapers",
            authorization_required="open-access, standards-body, or operator-approved full text rights",
            permission_policy="metadata/abstract allowed when full text is not licensed for storage",
            raw_storage_policy="metadata-only by default; raw full text only with open-access or approved rights",
            deletion_policy="track superseded, retracted, contradicted, and replaced documents",
            live_proof_boundary="PG-PROVIDER for provider-assisted synthesis from bounded source metadata",
            fake_fixture_supported=True,
            required_metadata=("identifier", "venue_or_body"),
            quality_weight=13,
        ),
        SourceLanePolicy(
            lane_id="web_article",
            label="Web articles, docs, blogs, newsletters, and threads",
            authorization_required="stable public URL, authorship/date, and allowed snapshot policy",
            permission_policy="store metadata and derived lesson cards unless snapshot rights are explicit",
            raw_storage_policy="derived summaries by default; raw snapshots require policy approval",
            deletion_policy="mark removed pages as removed; archive only when policy allows",
            live_proof_boundary="PG-PROVIDER for live search/acquisition and generated synthesis",
            fake_fixture_supported=True,
            required_metadata=("author_or_org", "published_at"),
            quality_weight=6,
        ),
        SourceLanePolicy(
            lane_id="skill_tool_catalog",
            label="Skills, MCP servers, tools, and templates",
            authorization_required="local, bundled, organization, or reviewed public skill source",
            permission_policy="public skills must be reviewed before they influence an Agent",
            raw_storage_policy="metadata-only until skill review accepts code/content storage",
            deletion_policy="remove or quarantine unapproved/superseded skills before Agent updates",
            live_proof_boundary="PG-HERMES for trained workspace behavior after skills are staged",
            fake_fixture_supported=True,
            required_metadata=("skill_id", "review_status"),
            quality_weight=8,
        ),
        SourceLanePolicy(
            lane_id="organization_private",
            label="Organization-provided private material",
            authorization_required="Captain/operator supplied material and private data governance approval",
            permission_policy="organization policy decides reuse, retention, and Agent audience boundaries",
            raw_storage_policy="private raw storage only with explicit operator policy and scoped access",
            deletion_policy="honor owner deletion, retention, and audience-scope changes before updates",
            live_proof_boundary="policy decision plus PG-HERMES workspace proof",
            fake_fixture_supported=True,
            required_metadata=("owner", "audience_scope"),
            quality_weight=9,
        ),
    ]
    return {lane.lane_id: lane for lane in lanes}


# Lanes whose Trainer-screened, redacted derived notes are eligible for the
# CENTRAL cross-captain shared corpus. organization_private is NEVER share-eligible
# -- Captain/operator-supplied private material stays per-tenant (Captain's chosen
# policy: "public lanes only"). Cross-tenant promotion of any other lane still
# passes the secret-screen + raw-content + license checks in the promotion path.
SHARE_INELIGIBLE_SOURCE_LANES = frozenset({"organization_private"})


def share_eligible_source_lanes(
    registry: Mapping[str, SourceLanePolicy] | None = None,
) -> frozenset[str]:
    """Return the lane ids whose redacted derived notes may join the central corpus.

    Everything in the governed registry except the always-private lanes in
    :data:`SHARE_INELIGIBLE_SOURCE_LANES`.
    """
    lanes = dict(registry or default_source_lane_registry())
    return frozenset(lane for lane in lanes if lane not in SHARE_INELIGIBLE_SOURCE_LANES)


def fake_academy_source(
    *,
    source_id: str,
    lane_id: str,
    title: str,
    origin_url: str,
    retrieved_at: str,
    license_status: str,
    permission_status: str,
    storage_policy: str,
    content: str = "",
    citations: Sequence[str] = (),
    metadata: Mapping[str, Any] | None = None,
    review_status: str = "reviewed",
    tombstone_status: str = "active",
    acquisition_mode: str = "local_fixture",
) -> AcademySource:
    return AcademySource(
        source_id=_clean_identifier(source_id, label="source_id"),
        lane_id=_clean_identifier(lane_id, label="lane_id"),
        title=_clean_required(title, label="source title", limit=180),
        origin_url=_clean_required(origin_url, label="source origin", limit=500),
        retrieved_at=_clean_required(retrieved_at, label="retrieved_at", limit=80),
        license_status=_clean_space(license_status, limit=80),
        permission_status=_clean_space(permission_status, limit=80),
        storage_policy=_clean_space(storage_policy, limit=60),
        content=_clean_space(content, limit=20_000),
        citations=tuple(_compact_unique(citations, limit=12, item_limit=180)),
        metadata=dict(metadata or {}),
        review_status=_clean_space(review_status, limit=80) or "reviewed",
        tombstone_status=_clean_space(tombstone_status, limit=80) or "active",
        acquisition_mode=_clean_space(acquisition_mode, limit=80) or "local_fixture",
    )


def acquire_fake_academy_sources(
    request: AcademyAcquisitionRequest | Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    registry: Mapping[str, SourceLanePolicy] | None = None,
) -> AcademyAcquisitionResult:
    """Adapt governed local fixture records into Academy sources.

    This is deliberately not a live fetcher. It accepts only local fixture rows,
    performs the same policy validation used by corpus construction, and returns
    compact redacted evidence about accepted, rejected, and proof-gated rows.
    """
    lane_registry = dict(registry or default_source_lane_registry())
    clean_request = _coerce_acquisition_request(request)
    accepted: list[AcademySource] = []
    rejected: list[dict[str, Any]] = []
    proof_gated: list[dict[str, Any]] = []
    seen_source_ids: set[str] = set()

    request_violations = _acquisition_request_violations(clean_request)
    for index, fixture in enumerate(clean_request.fixtures, start=1):
        if not isinstance(fixture, Mapping):
            rejected.append(
                _acquisition_issue(
                    index=index,
                    source_id=f"fixture-{index}",
                    lane_id="",
                    status="rejected",
                    reasons=("Academy acquisition fixture must be an object",),
                )
            )
            continue

        source_hint = _clean_space(fixture.get("source_id") or f"fixture-{index}", limit=120)
        lane_hint = _clean_space(fixture.get("lane_id") or "", limit=120)
        citations_value = fixture.get("citations")
        try:
            source = fake_academy_source(
                source_id=str(fixture.get("source_id") or ""),
                lane_id=str(fixture.get("lane_id") or ""),
                title=str(fixture.get("title") or ""),
                origin_url=str(fixture.get("origin_url") or ""),
                retrieved_at=str(fixture.get("retrieved_at") or clean_request.requested_at or ""),
                license_status=str(fixture.get("license_status") or ""),
                permission_status=str(fixture.get("permission_status") or ""),
                storage_policy=str(fixture.get("storage_policy") or ""),
                content=str(fixture.get("content") or ""),
                citations=citations_value
                if isinstance(citations_value, Sequence) and not isinstance(citations_value, (str, bytes))
                else (),
                metadata=fixture.get("metadata") if isinstance(fixture.get("metadata"), Mapping) else {},
                review_status=str(fixture.get("review_status") or "reviewed"),
                tombstone_status=str(fixture.get("tombstone_status") or "active"),
                acquisition_mode=str(fixture.get("acquisition_mode") or clean_request.acquisition_mode),
            )
        except ArcLinkAcademyPolicyError as exc:
            rejected.append(
                _acquisition_issue(
                    index=index,
                    source_id=source_hint or f"fixture-{index}",
                    lane_id=lane_hint,
                    status="rejected",
                    reasons=exc.violations,
                )
            )
            continue

        violations = list(request_violations)
        if source.source_id in seen_source_ids:
            violations.append(f"Academy source {source.source_id} is duplicated")
        seen_source_ids.add(source.source_id)
        lane = lane_registry.get(source.lane_id)
        if lane is not None:
            violations.extend(_required_metadata_violations(source, lane))
        violations.extend(validate_academy_sources([source], registry=lane_registry))

        if violations:
            issue = _acquisition_issue(
                index=index,
                source_id=source.source_id,
                lane_id=source.lane_id,
                status="proof_gated" if _only_proof_gated_violations(violations) else "rejected",
                reasons=violations,
                proof_gates=("PG-PROVIDER", "PG-HERMES") if _any_proof_gated_violation(violations) else (),
            )
            if issue["status"] == "proof_gated":
                proof_gated.append(issue)
            else:
                rejected.append(issue)
            continue

        accepted.append(source)

    lane_counts: dict[str, int] = {}
    for source in accepted:
        lane_counts[source.lane_id] = lane_counts.get(source.lane_id, 0) + 1
    accepted_summaries = tuple(_source_acquisition_summary(source, lane_registry[source.lane_id]) for source in accepted)
    status = _acquisition_status(
        accepted_count=len(accepted),
        rejected_count=len(rejected),
        proof_gated_count=len(proof_gated),
    )
    report = AcademyAcquisitionReport(
        request_id=clean_request.request_id,
        requested_at=clean_request.requested_at,
        status=status,
        accepted_count=len(accepted),
        rejected_count=len(rejected),
        proof_gated_count=len(proof_gated),
        lane_counts=dict(sorted(lane_counts.items())),
        accepted_sources=accepted_summaries,
        rejected_fixtures=tuple(rejected),
        proof_gated_fixtures=tuple(proof_gated),
        no_network=clean_request.no_network,
        no_write=clean_request.no_write,
    )
    return AcademyAcquisitionResult(
        request=clean_request,
        accepted_sources=tuple(accepted),
        report=report,
        rejected_fixtures=tuple(rejected),
        proof_gated_fixtures=tuple(proof_gated),
        no_network=clean_request.no_network,
        no_write=clean_request.no_write,
    )


def validate_academy_sources(
    sources: Sequence[AcademySource],
    *,
    registry: Mapping[str, SourceLanePolicy] | None = None,
) -> list[str]:
    source_list = list(sources or [])
    lane_registry = dict(registry or default_source_lane_registry())
    violations: list[str] = []
    if not source_list:
        return ["Academy corpus requires at least one local source fixture"]

    seen: set[str] = set()
    for source in source_list:
        source_id = _clean_space(source.source_id, limit=120)
        if not source_id:
            violations.append("Academy source is missing source_id")
            continue
        if source_id in seen:
            violations.append(f"Academy source {source_id} is duplicated")
        seen.add(source_id)

        lane = lane_registry.get(source.lane_id)
        if lane is None:
            violations.append(f"Academy source {source_id} uses unsupported lane {source.lane_id}")
            continue
        if not lane.enabled:
            violations.append(f"Academy source lane {source.lane_id} is disabled for {source_id}")
        if not lane.fake_fixture_supported:
            violations.append(f"Academy source lane {source.lane_id} has no fake/local fixture contract")
        if lane.live_actions_enabled:
            violations.append(f"Academy source lane {source.lane_id} unexpectedly enables live actions")
        violations.extend(_required_metadata_violations(source, lane))

        if source.acquisition_mode != "local_fixture":
            violations.append(f"Academy source {source_id} requests live acquisition mode {source.acquisition_mode}")
        if _requests_live_action(source.metadata):
            violations.append(f"Academy source {source_id} requests live crawling/provider/transcription action")

        license_status = source.license_status.casefold()
        permission_status = source.permission_status.casefold()
        if license_status in DENIED_STATUSES or permission_status in DENIED_STATUSES:
            violations.append(f"Academy source {source_id} is missing license or permission metadata")
        if source.storage_policy not in ALLOWED_STORAGE_POLICIES:
            violations.append(f"Academy source {source_id} has unsupported storage policy {source.storage_policy}")
        if source.storage_policy == "raw_snapshot" and not _raw_storage_allowed(source, lane):
            violations.append(f"Academy source {source_id} raw storage is not allowed by lane policy")

        if source.lane_id == "reddit_discussion":
            deleted = _boolish(source.metadata.get("deleted")) or _boolish(source.metadata.get("removed"))
            tombstoned = source.tombstone_status.casefold() == "tombstoned"
            if deleted and (not tombstoned or source.storage_policy != "metadata_only"):
                violations.append(f"Academy source {source_id} violates Reddit deletion/tombstone policy")

        if source.lane_id == "skill_tool_catalog":
            public_skill = _boolish(source.metadata.get("public_skill"))
            review_status = str(source.metadata.get("review_status") or source.review_status or "").casefold()
            if public_skill and review_status != "approved":
                violations.append(f"Academy source {source_id} is an unreviewed public skill")

        violations.extend(_secret_policy_violations(source))

    return violations


def build_academy_corpus(
    *,
    role_id: str,
    role_title: str,
    topic: str,
    sources: Sequence[AcademySource],
    registry: Mapping[str, SourceLanePolicy] | None = None,
    created_at: str | None = None,
    min_source_score: int = 70,
) -> CorpusManifest:
    lane_registry = dict(registry or default_source_lane_registry())
    violations = validate_academy_sources(sources, registry=lane_registry)
    if violations:
        raise ArcLinkAcademyPolicyError(violations)

    clean_role_id = _clean_identifier(role_id, label="role_id")
    clean_role_title = _clean_required(role_title, label="role title", limit=160)
    clean_topic = _clean_required(topic, label="topic", limit=220)
    timestamp = _clean_space(created_at or _utc_now_iso(), limit=80)

    quality_records = tuple(
        score_academy_source(source, lane_registry[source.lane_id], min_source_score=min_source_score)
        for source in sources
    )
    source_records = {
        source.source_id: _source_manifest_record(source, lane_registry[source.lane_id], quality_records)
        for source in sources
    }
    citation_map = {source.source_id: _citation_entries(source) for source in sources}
    lesson_cards = tuple(_lesson_card(source, source_records[source.source_id]) for source in sources)
    gate = academy_evaluation_gate(quality_records=quality_records, min_source_score=min_source_score)
    curriculum = _build_curriculum(
        role_id=clean_role_id,
        role_title=clean_role_title,
        topic=clean_topic,
        sources=sources,
        source_records=source_records,
        lesson_cards=lesson_cards,
        status=gate.status if gate.status != "live_proof_pending" else "ready_for_review",
    )
    manifest_seed = {
        "role_id": clean_role_id,
        "role_title": clean_role_title,
        "topic": clean_topic,
        "sources": [
            {
                "source_id": source.source_id,
                "lane_id": source.lane_id,
                "source_signature": source.source_signature(),
            }
            for source in sources
        ],
    }
    return CorpusManifest(
        manifest_id=f"academy-{_sha256(_stable_json(manifest_seed))[:16]}",
        role_id=clean_role_id,
        role_title=clean_role_title,
        topic=clean_topic,
        created_at=timestamp,
        sources=source_records,
        quality_records=quality_records,
        citation_map=citation_map,
        lesson_cards=lesson_cards,
        curriculum=curriculum,
        evaluation_gate=gate,
    )


def score_academy_source(
    source: AcademySource,
    lane: SourceLanePolicy,
    *,
    min_source_score: int = 70,
) -> QualityRecord:
    score = 52 + int(lane.quality_weight)
    reasons: list[str] = [f"lane_weight={lane.quality_weight}"]
    citation_count = len([item for item in source.citations if str(item or "").strip()])
    if citation_count:
        bump = min(12, citation_count * 3)
        score += bump
        reasons.append(f"citations=+{bump}")
    metadata = dict(source.metadata or {})
    positive_flags = {
        "official": 8,
        "examples": 7,
        "maintained": 6,
        "cross_source_agreement": 6,
        "practitioner_signal": 5,
        "fresh": 5,
    }
    for key, bump in positive_flags.items():
        if _boolish(metadata.get(key)):
            score += bump
            reasons.append(f"{key}=+{bump}")
    if metadata.get("freshness_days") not in (None, ""):
        score += 5
        reasons.append("freshness_policy=+5")
    if source.lane_id == "skill_tool_catalog" and str(metadata.get("review_status") or source.review_status).casefold() == "approved":
        score += 8
        reasons.append("skill_review=+8")

    negative_flags = {
        "low_signal": 20,
        "seo_content": 15,
        "contradiction_flags": 12,
        "stale": 10,
        "unsupported_claims": 15,
    }
    for key, penalty in negative_flags.items():
        if _boolish(metadata.get(key)):
            score -= penalty
            reasons.append(f"{key}=-{penalty}")

    score = max(0, min(100, score))
    status = "accepted" if score >= int(min_source_score) else "low_quality"
    return QualityRecord(
        source_id=source.source_id,
        lane_id=source.lane_id,
        score=score,
        status=status,
        reasons=tuple(reasons),
    )


def academy_evaluation_gate(
    *,
    manifest: CorpusManifest | None = None,
    policy_violations: Sequence[str] = (),
    quality_records: Sequence[QualityRecord] = (),
    live_proof_required: bool = False,
    min_source_score: int = 70,
) -> EvaluationGate:
    violations = [str(item or "").strip() for item in policy_violations if str(item or "").strip()]
    if manifest is not None:
        violations.extend(str(item or "").strip() for item in manifest.policy_violations if str(item or "").strip())
        if not quality_records:
            quality_records = manifest.quality_records
    if violations:
        return EvaluationGate(status="blocked_by_policy", reasons=tuple(violations))

    records = list(quality_records or ())
    low = [record.source_id for record in records if int(record.score) < int(min_source_score) or record.status != "accepted"]
    if not records:
        return EvaluationGate(status="blocked_by_quality", reasons=("Academy corpus has no quality-scored sources",))
    if low:
        return EvaluationGate(
            status="blocked_by_quality",
            reasons=(f"{len(low)} Academy source(s) are below the local quality threshold",),
            blocked_source_ids=tuple(low),
        )
    if live_proof_required:
        return EvaluationGate(
            status="live_proof_pending",
            reasons=("Local Academy artifacts are reviewable; live/provider/workspace proof is still required before graduation.",),
            required_live_proofs=("PG-PROVIDER", "PG-HERMES"),
        )
    return EvaluationGate(status="ready_for_review", reasons=("Academy local corpus is policy-clean and quality-scored.",))


def academy_graduation_gate(
    *,
    manifest: CorpusManifest | None = None,
    policy_violations: Sequence[str] = (),
    quality_records: Sequence[QualityRecord] = (),
    live_proof_evidence: Mapping[str, Any] | Sequence[Any] | None = None,
    min_source_score: int = 70,
) -> EvaluationGate:
    """Return the local graduation gate without claiming a trained Agent.

    This gate can only report review readiness or fail-closed blockers. It
    never returns trained/graduated/applied states; future authorized live proof
    evidence only moves the local summary back to review, not to application.
    """
    base = academy_evaluation_gate(
        manifest=manifest,
        policy_violations=policy_violations,
        quality_records=quality_records,
        live_proof_required=False,
        min_source_score=min_source_score,
    )
    if base.status in {"blocked_by_policy", "blocked_by_quality"}:
        return base

    satisfied = _satisfied_live_proof_gates(live_proof_evidence)
    missing = tuple(gate for gate in ACADEMY_LIVE_PROOF_GATES if gate not in satisfied)
    if missing:
        return EvaluationGate(
            status="blocked_by_live_proof",
            reasons=(
                "Academy local evaluation is reviewable, but provider generation and trained-Agent workspace proof are still required before graduation.",
            ),
            required_live_proofs=missing,
        )
    return EvaluationGate(
        status="ready_for_review",
        reasons=("Academy local evaluation and supplied proof references are ready for operator review.",),
        required_live_proofs=(),
    )


def build_agent_application_plan(
    manifest: CorpusManifest,
    *,
    agent_id: str,
    created_at: str | None = None,
) -> AgentApplicationPlan:
    clean_agent_id = _clean_identifier(agent_id, label="agent_id")
    timestamp = _clean_space(created_at or _utc_now_iso(), limit=80)
    role_slug = _slug(manifest.role_title or manifest.role_id)
    status = manifest.evaluation_gate.status
    blocked_reasons = tuple(manifest.evaluation_gate.reasons) if status not in PASSING_GATE_STATUSES else ()
    accepted_cards = [card for card in manifest.lesson_cards if str(card.get("quality_status") or "") == "accepted"]

    soul_sections = (
        {
            "section": "academy-expertise",
            "mode": "reviewed-overlay",
            "summary": f"Prepare {manifest.role_title} for {manifest.topic}.",
            "source_count": len(manifest.sources),
            "quality_gate": manifest.evaluation_gate.status,
        },
        {
            "section": "academy-boundaries",
            "mode": "append",
            "summary": "Use Academy sources through retrieval and cite before specialist advice; refuse unsupported or unsafe actions.",
        },
    )
    vault_intents = (
        {
            "path": f"Academy/{role_slug}/README.md",
            "kind": "vault_file_intent",
            "source": manifest.manifest_id,
        },
        {
            "path": f"Academy/{role_slug}/Curriculum.md",
            "kind": "vault_file_intent",
            "source": manifest.curriculum.status,
        },
        {
            "path": f"Academy/{role_slug}/Source_Map.md",
            "kind": "vault_file_intent",
            "source_count": len(manifest.sources),
        },
        *(
            {
                "path": f"Academy/{role_slug}/Lesson_Cards/{card['card_id']}.md",
                "kind": "vault_file_intent",
                "source_id": str(card.get("source_id") or ""),
            }
            for card in accepted_cards
        ),
    )
    memory_intents = tuple(
        {
            "kind": "memory_seed",
            "source_id": str(card.get("source_id") or ""),
            "lesson_card_id": str(card.get("card_id") or ""),
            "text": str(card.get("summary") or "")[:240],
            "routing": "Use knowledge.search-and-fetch or vault.search-and-fetch before citing.",
        }
        for card in accepted_cards
    ) + (
        {
            "kind": "qmd_index_hint",
            "path": f"Academy/{role_slug}",
            "collection": "vault",
            "note": "Index only after operator-approved Agent application; this plan writes nothing.",
        },
    )
    approved_skill_intents = tuple(
        _skill_intent(source_id, source)
        for source_id, source in manifest.sources.items()
        if source.get("lane_id") == "skill_tool_catalog"
        and str((source.get("metadata") or {}).get("review_status") or source.get("review_status") or "").casefold() == "approved"
    )
    plan_seed = {"manifest_id": manifest.manifest_id, "agent_id": clean_agent_id, "created_at": timestamp}
    return AgentApplicationPlan(
        plan_id=f"academy-plan-{_sha256(_stable_json(plan_seed))[:16]}",
        manifest_id=manifest.manifest_id,
        agent_id=clean_agent_id,
        role_id=manifest.role_id,
        status=status,
        created_at=timestamp,
        no_write=True,
        writes_enabled=False,
        soul_overlay_sections=tuple(soul_sections),
        vault_file_intents=tuple(vault_intents),
        qmd_memory_seed_intents=memory_intents,
        approved_skill_intents=approved_skill_intents,
        first_week_practice_tasks=manifest.curriculum.practice_tasks,
        evaluation_tasks=manifest.curriculum.evaluation_tasks,
        blocked_reasons=blocked_reasons,
    )


def build_continuing_education_plan(
    manifest: CorpusManifest,
    *,
    observed_sources: Mapping[str, Mapping[str, Any]],
    checked_at: str | None = None,
    next_review_at: str | None = None,
) -> ContinuingEducationPlan:
    timestamp = _clean_space(checked_at or _utc_now_iso(), limit=80)
    observed_payload = dict(observed_sources or {})
    violations = _observed_sources_payload_violations(observed_payload)
    if violations:
        raise ArcLinkAcademyPolicyError(violations)
    refreshes: list[dict[str, Any]] = []
    blocked: list[str] = []
    review_required: list[str] = []
    for source_id, source in manifest.sources.items():
        observed = dict(observed_payload.get(source_id) or {})
        status = "unchanged"
        reason = "source hash unchanged"
        if _boolish(observed.get("deleted")) or _boolish(observed.get("tombstoned")):
            status = "tombstoned"
            reason = "source was deleted or tombstoned; raw/derived update is blocked pending policy review"
            blocked.append(source_id)
        elif _boolish(observed.get("removed")):
            status = "removed"
            reason = "source disappeared; preserve only policy-allowed archived/derived material"
            blocked.append(source_id)
        elif str(observed.get("crawl_status") or "").strip() == "blocked":
            status = "blocked"
            reason = "source crawl was blocked by crawler policy; preserve current Agent state pending review"
            blocked.append(source_id)
        elif str(observed.get("crawl_status") or "").strip() == "failed":
            status = "crawl_failed"
            reason = "source crawl failed; refresh/review before Agent update"
            review_required.append(source_id)
        elif str(observed.get("superseded_by") or "").strip():
            status = "superseded"
            reason = f"source superseded by {redact_secret_material(observed.get('superseded_by'))}"
            review_required.append(source_id)
        else:
            current_hash = str(observed.get("content_hash") or source.get("content_hash") or "").strip()
            if current_hash and current_hash != str(source.get("content_hash") or ""):
                status = "changed"
                reason = "source digest changed; rebuild lesson card after review"
                review_required.append(source_id)
            elif _is_stale(source, checked_at=timestamp):
                status = "stale"
                reason = "freshness window expired; refresh/review before Agent update"
                review_required.append(source_id)
        refreshes.append(
            {
                "source_id": source_id,
                "lane_id": str(source.get("lane_id") or ""),
                "status": status,
                "reason": reason,
                "agent_update_blocked": status in {"removed", "tombstoned", "blocked", "crawl_failed"},
                "review_required": status in {"changed", "stale", "superseded", "crawl_failed"},
            }
        )

    if blocked:
        status = "blocked_by_policy"
        agent_update_status = "blocked"
    elif review_required:
        status = "ready_for_review"
        agent_update_status = "blocked_pending_review"
    else:
        status = "ready_for_agent_update"
        agent_update_status = "ready"
    seed = {"manifest_id": manifest.manifest_id, "checked_at": timestamp, "refreshes": refreshes}
    state_counts = _weekly_state_counts(refreshes, blocked_source_ids=blocked, review_required_source_ids=review_required)
    review_id = f"academy-weekly-{_sha256(_stable_json(seed))[:16]}"
    return ContinuingEducationPlan(
        plan_id=f"academy-refresh-{_sha256(_stable_json(seed))[:16]}",
        review_id=review_id,
        manifest_id=manifest.manifest_id,
        checked_at=timestamp,
        next_review_at=_clean_space(next_review_at or _next_week_iso(timestamp), limit=80),
        status=status,
        agent_update_status=agent_update_status,
        source_refreshes=tuple(refreshes),
        blocked_source_ids=tuple(blocked),
        review_required_source_ids=tuple(review_required),
        source_state_counts=state_counts,
        review_needed_count=len(review_required),
        blocked_source_count=len(blocked),
        proof_gates=ACADEMY_LIVE_PROOF_GATES,
    )


def build_academy_review_status(
    *,
    manifest: CorpusManifest | Mapping[str, Any] | None = None,
    application_plan: AgentApplicationPlan | Mapping[str, Any] | None = None,
    continuing_education_plan: ContinuingEducationPlan | Mapping[str, Any] | None = None,
    graduation_gate: EvaluationGate | Mapping[str, Any] | None = None,
    staged_at: str | None = None,
) -> dict[str, Any]:
    """Return the compact review artifact used by dashboard/Raven surfaces.

    The result is intentionally a status summary, not a corpus export. It keeps
    live proof gates visible and avoids raw source material.
    """
    manifest_data = _artifact_dict(manifest)
    application_data = _artifact_dict(application_plan)
    refresh_data = _artifact_dict(continuing_education_plan)
    graduation_data = _artifact_dict(graduation_gate)
    if not manifest_data:
        return {
            "status": "not_started",
            "summary": "No Academy corpus has been staged for this Crew Recipe.",
            "manifest_id": "",
            "role_id": "",
            "role_title": "",
            "topic": "",
            "source_count": 0,
            "lane_count": 0,
            "lanes": [],
            "quality": {"accepted": 0, "low_quality": 0, "min_score": 0, "average_score": 0},
            "curriculum_status": "not_started",
            "application_status": "not_started",
            "continuing_education_status": "not_started",
            "weekly_review_status": "not_started",
            "evaluation_status": "not_started",
            "graduation_status": "not_started",
            "agent_update_status": "not_started",
            "next_review_at": "",
            "source_state_counts": {key: 0 for key in ACADEMY_WEEKLY_STATE_KEYS},
            "review_needed_count": 0,
            "blocked_source_count": 0,
            "proof_gates": ["PG-PROVIDER", "PG-HERMES"],
            "next_actions": [
                "Build a local Academy corpus from approved source fixtures.",
                "Stage the no-write application plan for Crew Training review.",
            ],
            "review_surfaces": ["Crew Training", "dashboard", "Operator Raven"],
            "local_only": True,
            "no_network": True,
            "no_write": True,
            "writes_enabled": False,
            "live_proof_required": True,
        }

    sources = manifest_data.get("sources") if isinstance(manifest_data.get("sources"), Mapping) else {}
    source_records = [dict(item) for item in sources.values() if isinstance(item, Mapping)]
    lanes = sorted({str(item.get("lane_id") or "") for item in source_records if str(item.get("lane_id") or "").strip()})
    gate = manifest_data.get("evaluation_gate") if isinstance(manifest_data.get("evaluation_gate"), Mapping) else {}
    gate_status = _clean_space((gate or {}).get("status") or "ready_for_review", limit=80)
    graduation_status = _clean_space(graduation_data.get("status") or "", limit=80) if graduation_data else ""
    application_status = _clean_space(application_data.get("status") or "", limit=80) if application_data else ""
    application_plan_id = _clean_space(application_data.get("plan_id") or "", limit=120) if application_data else ""
    application_agent_id = _clean_space(application_data.get("agent_id") or "", limit=120) if application_data else ""
    application_role_id = _clean_space(application_data.get("role_id") or "", limit=120) if application_data else ""
    refresh_status = _clean_space(refresh_data.get("status") or "", limit=80) if refresh_data else ""
    agent_update_status = _clean_space(refresh_data.get("agent_update_status") or "", limit=80) if refresh_data else ""
    status = _academy_surface_status(
        gate_status=gate_status,
        application_status=application_status,
        refresh_status=refresh_status,
        agent_update_status=agent_update_status,
    )
    required_live_proofs = []
    if isinstance(gate, Mapping):
        required_live_proofs.extend(gate.get("required_live_proofs") or [])
    if graduation_data:
        required_live_proofs.extend(graduation_data.get("required_live_proofs") or [])
    required_live_proofs.extend(["PG-PROVIDER", "PG-HERMES"])
    summary = _academy_review_summary(status=status, source_count=len(source_records))
    no_write = bool(manifest_data.get("no_write", True))
    if application_data:
        no_write = no_write and bool(application_data.get("no_write", True))
    if refresh_data:
        no_write = no_write and bool(refresh_data.get("no_write", True))
    status_payload = {
        "status": status,
        "summary": summary,
        "manifest_id": _clean_space(manifest_data.get("manifest_id") or "", limit=120),
        "role_id": _clean_space(manifest_data.get("role_id") or "", limit=120),
        "role_title": _clean_space(manifest_data.get("role_title") or "", limit=160),
        "topic": _clean_space(manifest_data.get("topic") or "", limit=220),
        "source_count": len(source_records),
        "lane_count": len(lanes),
        "lanes": lanes,
        "quality": _quality_summary(manifest_data.get("quality_records") or ()),
        "curriculum_status": _clean_space(
            (manifest_data.get("curriculum") or {}).get("status") if isinstance(manifest_data.get("curriculum"), Mapping) else "",
            limit=80,
        ) or "not_started",
        "application_status": application_status or "not_started",
        "application_plan_id": application_plan_id,
        "application_agent_id": application_agent_id,
        "application_role_id": application_role_id,
        "continuing_education_status": refresh_status or "not_started",
        "weekly_review_status": refresh_status or "not_started",
        "evaluation_status": gate_status,
        "graduation_status": graduation_status
        or ("blocked_by_live_proof" if gate_status in PASSING_GATE_STATUSES else gate_status),
        "agent_update_status": agent_update_status or "not_started",
        "next_review_at": _clean_space(refresh_data.get("next_review_at") or "", limit=80) if refresh_data else "",
        "source_state_counts": _public_state_counts(refresh_data.get("source_state_counts") or {}),
        "review_needed_count": _intish(refresh_data.get("review_needed_count"))
        if refresh_data
        else 0,
        "blocked_source_count": _intish(refresh_data.get("blocked_source_count"))
        if refresh_data
        else 0,
        "blocked_source_ids": _compact_unique(
            list((gate or {}).get("blocked_source_ids") or [])
            + list(graduation_data.get("blocked_source_ids") or [])
            + list(refresh_data.get("blocked_source_ids") or []),
            limit=12,
            item_limit=120,
        ),
        "review_required_source_ids": _compact_unique(
            list(refresh_data.get("review_required_source_ids") or []),
            limit=12,
            item_limit=120,
        ),
        "proof_gates": _compact_unique(required_live_proofs, limit=6, item_limit=40),
        "next_actions": _academy_review_next_actions(
            status=status,
            application_present=bool(application_data),
            refresh_present=bool(refresh_data),
        ),
        "review_surfaces": ["Crew Training", "dashboard", "Operator Raven"],
        "local_only": True,
        "no_network": bool(manifest_data.get("no_network", True))
        and bool(refresh_data.get("no_network", True) if refresh_data else True),
        "no_write": no_write,
        "writes_enabled": bool(application_data.get("writes_enabled", False)) if application_data else False,
        "live_proof_required": True,
    }
    staged = _clean_space(staged_at or "", limit=80)
    if staged:
        status_payload["staged_at"] = staged
    return _redact_jsonable(status_payload)


def build_academy_application_preview_request(
    payload: AcademyApplicationPreviewRequest | Mapping[str, Any],
    *,
    request_id: str = "",
    target_kind: str = "",
    target_id: str = "",
    requested_at: str | None = None,
    requested_by: str = "",
) -> AcademyApplicationPreviewRequest:
    """Coerce an action-worker payload into a no-write Academy preview request."""
    if isinstance(payload, AcademyApplicationPreviewRequest):
        base = payload
        return AcademyApplicationPreviewRequest(
            request_id=_clean_identifier(base.request_id or request_id, label="application preview request_id"),
            user_id=_clean_identifier(base.user_id, label="application preview user_id"),
            recipe_id=_clean_identifier(base.recipe_id, label="application preview recipe_id"),
            manifest_id=_clean_identifier(base.manifest_id, label="application preview manifest_id"),
            application_plan_id=_clean_identifier(base.application_plan_id, label="application preview application_plan_id"),
            agent_id=_clean_identifier(base.agent_id, label="application preview agent_id"),
            target_kind=_clean_space(base.target_kind or target_kind or "user", limit=40),
            target_id=_clean_space(base.target_id or target_id or base.user_id, limit=160),
            requested_at=_clean_space(base.requested_at or requested_at or _utc_now_iso(), limit=80),
            requested_by=_clean_space(base.requested_by or requested_by, limit=120),
            local_only=bool(base.local_only),
            no_write=bool(base.no_write),
            writes_enabled=bool(base.writes_enabled),
            proof_gates=tuple(_compact_unique(base.proof_gates, limit=6, item_limit=40)),
            metadata=dict(base.metadata or {}),
        )

    if not isinstance(payload, Mapping):
        raise ArcLinkAcademyPolicyError(["Academy application preview request must be an object"])
    data = dict(payload)
    clean_target_kind = _clean_space(data.get("target_kind") or target_kind or "user", limit=40)
    clean_target_id = _clean_space(data.get("target_id") or target_id or "", limit=160)
    user_id = data.get("user_id") or (clean_target_id if clean_target_kind == "user" else "")
    proof_gates = data.get("proof_gates") or ACADEMY_APPLICATION_PREVIEW_PROOF_GATES
    if isinstance(proof_gates, (str, bytes)) or not isinstance(proof_gates, Sequence):
        proof_gates = ()
    return AcademyApplicationPreviewRequest(
        request_id=_clean_identifier(data.get("request_id") or request_id or "academy-application-preview", label="application preview request_id"),
        user_id=_clean_identifier(user_id, label="application preview user_id"),
        recipe_id=_clean_identifier(data.get("recipe_id") or "", label="application preview recipe_id"),
        manifest_id=_clean_identifier(data.get("manifest_id") or "", label="application preview manifest_id"),
        application_plan_id=_clean_identifier(
            data.get("application_plan_id") or data.get("plan_id") or "",
            label="application preview application_plan_id",
        ),
        agent_id=_clean_identifier(data.get("agent_id") or "", label="application preview agent_id"),
        target_kind=clean_target_kind,
        target_id=clean_target_id or _clean_space(user_id, limit=160),
        requested_at=_clean_space(data.get("requested_at") or requested_at or _utc_now_iso(), limit=80),
        requested_by=_clean_space(data.get("requested_by") or requested_by, limit=120),
        local_only=_default_true_bool(data.get("local_only")),
        no_write=_default_true_bool(data.get("no_write")),
        writes_enabled=_boolish(data.get("writes_enabled")),
        proof_gates=tuple(_compact_unique(proof_gates, limit=6, item_limit=40)),
        metadata=data,
    )


def build_academy_application_preview_result(
    request: AcademyApplicationPreviewRequest | Mapping[str, Any],
    *,
    staged_status: Mapping[str, Any],
    created_at: str | None = None,
) -> AcademyApplicationPreviewResult:
    """Validate a staged Academy review and return a compact no-write preview.

    This is the first worker boundary between staged Academy plans and future
    Agent application. It validates references and records readiness only; it
    never applies SOUL, vault, qmd, memory, skill, Hermes-home, or workspace
    writes.
    """
    clean_request = build_academy_application_preview_request(request)
    status = dict(staged_status or {})
    violations = _application_preview_request_violations(clean_request)
    violations.extend(_application_preview_status_violations(clean_request, status))
    if violations:
        raise ArcLinkAcademyPolicyError(violations)

    proof_gates = tuple(
        _compact_unique(
            list(clean_request.proof_gates) + list(status.get("proof_gates") or []) + list(ACADEMY_APPLICATION_PREVIEW_PROOF_GATES),
            limit=6,
            item_limit=40,
        )
    )
    source_count = _intish(status.get("source_count"))
    lane_count = _intish(status.get("lane_count"))
    staged = _clean_space(status.get("status") or "", limit=80)
    application_status = _clean_space(status.get("application_status") or "", limit=80)
    result = AcademyApplicationPreviewResult(
        request=clean_request,
        status="ready_for_application_proof",
        summary=(
            f"Academy application preview recorded for {source_count} source(s); "
            "no Agent files or workspace state were changed."
        ),
        staged_status=staged,
        application_status=application_status,
        source_count=source_count,
        lane_count=lane_count,
        proof_gates=proof_gates,
        created_at=_clean_space(created_at or _utc_now_iso(), limit=80),
    )
    return result


def _application_preview_request_violations(request: AcademyApplicationPreviewRequest) -> list[str]:
    violations: list[str] = []
    if not request.local_only:
        violations.append("Academy application preview requires local_only=true")
    if not request.no_write:
        violations.append("Academy application preview requires no_write=true")
    if request.writes_enabled:
        violations.append("Academy application preview requires writes_enabled=false")
    gates = {str(gate or "").strip() for gate in request.proof_gates}
    missing_gates = [gate for gate in ACADEMY_APPLICATION_PREVIEW_PROOF_GATES if gate not in gates]
    if missing_gates:
        violations.append(f"Academy application preview requires proof gates: {', '.join(missing_gates)}")
    violations.extend(_unsafe_application_preview_payload_violations(request.metadata, path="$.metadata"))
    for label, value in (
        ("user_id", request.user_id),
        ("recipe_id", request.recipe_id),
        ("manifest_id", request.manifest_id),
        ("application_plan_id", request.application_plan_id),
        ("agent_id", request.agent_id),
        ("target_id", request.target_id),
    ):
        violations.extend(_unsafe_application_preview_text_violations(value, path=f"$.{label}", allow_identifier=True))
    return violations


def _application_preview_status_violations(
    request: AcademyApplicationPreviewRequest,
    status: Mapping[str, Any],
) -> list[str]:
    violations: list[str] = []
    if not status:
        return ["Academy application preview requires a staged Academy review status on the active Crew Recipe"]
    staged_status = _clean_space(status.get("status") or "", limit=80)
    application_status = _clean_space(status.get("application_status") or "", limit=80)
    if staged_status not in ACADEMY_APPLICATION_PREVIEW_STATUSES:
        violations.append(f"Academy staged status is not previewable: {staged_status or 'missing'}")
    if application_status not in ACADEMY_APPLICATION_PREVIEW_STATUSES:
        violations.append(f"Academy application plan status is not previewable: {application_status or 'missing'}")
    for field, expected in (
        ("recipe_id", request.recipe_id),
        ("manifest_id", request.manifest_id),
        ("application_plan_id", request.application_plan_id),
        ("application_agent_id", request.agent_id),
    ):
        actual = _clean_space(status.get(field) or "", limit=160)
        if not actual:
            violations.append(f"Academy staged status is missing {field}")
        elif actual != expected:
            violations.append(f"Academy staged status {field} does not match preview request")
    if not _default_true_bool(status.get("local_only")):
        violations.append("Academy staged status must be local_only=true")
    if not _default_true_bool(status.get("no_network")):
        violations.append("Academy staged status must keep no_network=true")
    if not _default_true_bool(status.get("no_write")):
        violations.append("Academy staged status must keep no_write=true")
    if _boolish(status.get("writes_enabled")):
        violations.append("Academy staged status must keep writes_enabled=false")
    if not _boolish(status.get("live_proof_required")):
        violations.append("Academy staged status must keep live_proof_required=true")
    gates = {str(gate or "").strip() for gate in status.get("proof_gates") or []}
    missing_gates = [gate for gate in ACADEMY_APPLICATION_PREVIEW_PROOF_GATES if gate not in gates]
    if missing_gates:
        violations.append(f"Academy staged status is missing proof gates: {', '.join(missing_gates)}")
    if _intish(status.get("source_count")) < 1:
        violations.append("Academy application preview requires at least one staged source")
    if _boolish(status.get("review_persisted")) is False:
        violations.append("Academy application preview requires review_persisted=true on the active Crew Recipe")
    compact_status = {
        key: status.get(key)
        for key in (
            "status",
            "summary",
            "manifest_id",
            "recipe_id",
            "application_plan_id",
            "application_agent_id",
            "proof_gates",
            "next_actions",
        )
    }
    violations.extend(_secret_control_payload_violations(compact_status, path="$.staged_status"))
    return violations


def _unsafe_application_preview_payload_violations(value: Any, *, path: str) -> list[str]:
    violations: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key or "")
            key_path = f"{path}.{key_text}"
            key_fold = key_text.replace("-", "_").casefold()
            violations.extend(_unsafe_application_preview_text_violations(key_text, path=key_path, allow_identifier=True))
            if key_fold in ACADEMY_APPLICATION_PREVIEW_FORBIDDEN_KEYS:
                violations.append(f"Academy application preview rejects raw content or filesystem field {key_path}")
            if key_fold in ACADEMY_APPLICATION_PREVIEW_LIVE_FLAGS and _boolish(nested):
                violations.append(f"Academy application preview rejects live/write action flag {key_path}")
            if any(term in key_fold for term in ("vault", "qmd", "hermes_home", "workspace", "host_path", "filesystem", "skill_write", "soul")):
                violations.append(f"Academy application preview rejects workspace or host mutation field {key_path}")
            violations.extend(_unsafe_application_preview_payload_violations(nested, path=key_path))
        return violations
    if isinstance(value, (list, tuple, set)):
        for index, nested in enumerate(value):
            violations.extend(_unsafe_application_preview_payload_violations(nested, path=f"{path}[{index}]"))
        return violations
    violations.extend(_unsafe_application_preview_text_violations(value, path=path, allow_identifier=False))
    if _boolish(value) and path.rsplit(".", 1)[-1].replace("-", "_").casefold() in ACADEMY_APPLICATION_PREVIEW_LIVE_FLAGS:
        violations.append(f"Academy application preview rejects enabled live/write flag {path}")
    return violations


def _secret_control_payload_violations(value: Any, *, path: str) -> list[str]:
    violations: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key or "")
            key_path = f"{path}.{key_text}"
            violations.extend(_unsafe_application_preview_text_violations(key_text, path=key_path, allow_identifier=True))
            violations.extend(_secret_control_payload_violations(nested, path=key_path))
        return violations
    if isinstance(value, (list, tuple, set)):
        for index, nested in enumerate(value):
            violations.extend(_secret_control_payload_violations(nested, path=f"{path}[{index}]"))
        return violations
    violations.extend(_unsafe_application_preview_text_violations(value, path=path, allow_identifier=True))
    return violations


def _observed_sources_payload_violations(value: Any, *, path: str = "$.observed_sources") -> list[str]:
    violations: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key or "")
            key_path = f"{path}.{key_text}"
            key_fold = key_text.replace("-", "_").casefold()
            violations.extend(
                _unsafe_observed_source_text_violations(key_text, path=key_path, allow_identifier=True)
            )
            if key_fold in ACADEMY_WEEKLY_REVIEW_FORBIDDEN_KEYS:
                violations.append(f"Academy weekly review rejects raw content or filesystem field {key_path}")
            if key_fold in ACADEMY_WEEKLY_REVIEW_FORBIDDEN_FLAGS and _boolish(nested):
                violations.append(f"Academy weekly review rejects live/write action flag {key_path}")
            if any(term in key_fold for term in ("vault", "qmd", "hermes_home", "workspace", "host_path", "filesystem", "skill_write", "soul")):
                violations.append(f"Academy weekly review rejects workspace or host mutation field {key_path}")
            if SECRET_KEY_RE.search(key_path):
                violations.append(f"Academy weekly review rejects secret-looking key {key_path}")
            violations.extend(_observed_sources_payload_violations(nested, path=key_path))
        return violations
    if isinstance(value, (list, tuple, set)):
        for index, nested in enumerate(value):
            violations.extend(_observed_sources_payload_violations(nested, path=f"{path}[{index}]"))
        return violations
    violations.extend(_unsafe_observed_source_text_violations(value, path=path, allow_identifier=False))
    if _boolish(value) and path.rsplit(".", 1)[-1].replace("-", "_").casefold() in ACADEMY_WEEKLY_REVIEW_FORBIDDEN_FLAGS:
        violations.append(f"Academy weekly review rejects enabled live/write flag {path}")
    return violations


def _unsafe_observed_source_text_violations(
    value: Any,
    *,
    path: str,
    allow_identifier: bool,
) -> list[str]:
    text = str(value or "")
    if not text:
        return []
    violations: list[str] = []
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", text):
        violations.append(f"Academy weekly review rejects control characters at {path}")
    if contains_secret_material(text, allow_safe_refs=False):
        violations.append(f"Academy weekly review rejects secret-looking value at {path}")
    stripped = text.strip()
    lower = stripped.casefold()
    if allow_identifier:
        if stripped.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", stripped):
            violations.append(f"Academy weekly review rejects absolute path at {path}")
        if ".." in stripped:
            violations.append(f"Academy weekly review rejects parent-directory traversal at {path}")
    if not allow_identifier:
        if stripped.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", stripped):
            violations.append(f"Academy weekly review rejects absolute path at {path}")
        if ".." in stripped:
            violations.append(f"Academy weekly review rejects parent-directory traversal at {path}")
        if any(term in lower for term in ACADEMY_APPLICATION_PREVIEW_FORBIDDEN_VALUE_TERMS):
            violations.append(f"Academy weekly review rejects workspace or host mutation value at {path}")
    return violations


def _unsafe_application_preview_text_violations(
    value: Any,
    *,
    path: str,
    allow_identifier: bool,
) -> list[str]:
    text = str(value or "")
    if not text:
        return []
    violations: list[str] = []
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", text):
        violations.append(f"Academy application preview rejects control characters at {path}")
    if contains_secret_material(text, allow_safe_refs=False):
        violations.append(f"Academy application preview rejects secret-looking value at {path}")
    if not allow_identifier:
        stripped = text.strip()
        lower = stripped.casefold()
        if stripped.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", stripped):
            violations.append(f"Academy application preview rejects absolute path at {path}")
        if ".." in stripped:
            violations.append(f"Academy application preview rejects parent-directory traversal at {path}")
        if any(term in lower for term in ACADEMY_APPLICATION_PREVIEW_FORBIDDEN_VALUE_TERMS):
            violations.append(f"Academy application preview rejects workspace or host mutation value at {path}")
    return violations


def _coerce_acquisition_request(
    request: AcademyAcquisitionRequest | Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> AcademyAcquisitionRequest:
    if isinstance(request, AcademyAcquisitionRequest):
        return AcademyAcquisitionRequest(
            request_id=_clean_identifier(request.request_id, label="acquisition request_id"),
            fixtures=tuple(request.fixtures or ()),
            requested_at=_clean_space(request.requested_at or _utc_now_iso(), limit=80),
            acquisition_mode=_clean_space(request.acquisition_mode or "local_fixture", limit=80),
            no_network=bool(request.no_network),
            no_write=bool(request.no_write),
            live_actions_enabled=bool(request.live_actions_enabled),
        )
    if isinstance(request, Mapping):
        fixture_value = request.get("fixtures") or request.get("source_fixtures") or ()
        if isinstance(fixture_value, (str, bytes)) or not isinstance(fixture_value, Sequence):
            raise ArcLinkAcademyPolicyError(["Academy acquisition request fixtures must be a list"])
        return AcademyAcquisitionRequest(
            request_id=_clean_identifier(request.get("request_id") or "academy-local-acquisition", label="acquisition request_id"),
            fixtures=tuple(fixture_value),
            requested_at=_clean_space(request.get("requested_at") or _utc_now_iso(), limit=80),
            acquisition_mode=_clean_space(request.get("acquisition_mode") or "local_fixture", limit=80),
            no_network=not _boolish(request.get("network_fetch") or request.get("live_fetch")) and bool(request.get("no_network", True)),
            no_write=bool(request.get("no_write", True)),
            live_actions_enabled=_boolish(request.get("live_actions_enabled")),
        )
    if isinstance(request, (str, bytes)) or not isinstance(request, Sequence):
        raise ArcLinkAcademyPolicyError(["Academy acquisition request must be a request object or fixture list"])
    return AcademyAcquisitionRequest(
        request_id="academy-local-acquisition",
        fixtures=tuple(request),
        requested_at=_utc_now_iso(),
    )


def _acquisition_request_violations(request: AcademyAcquisitionRequest) -> list[str]:
    violations: list[str] = []
    if request.acquisition_mode != "local_fixture":
        violations.append(f"Academy acquisition request asks for live acquisition mode {request.acquisition_mode}")
    if not request.no_network:
        violations.append("Academy acquisition request asks for network/live source access")
    if not request.no_write:
        violations.append("Academy acquisition request asks for writes to vault, qmd, Hermes home, or workspace")
    if request.live_actions_enabled:
        violations.append("Academy acquisition request enables live actions")
    return violations


def _required_metadata_violations(source: AcademySource, lane: SourceLanePolicy) -> list[str]:
    missing = [
        key
        for key in lane.required_metadata
        if not _clean_space((source.metadata or {}).get(key), limit=240)
    ]
    if not missing:
        return []
    return [
        f"Academy source {source.source_id} is missing required {source.lane_id} metadata: {', '.join(missing)}"
    ]


def _only_proof_gated_violations(violations: Sequence[str]) -> bool:
    clean = [str(item or "").casefold() for item in violations if str(item or "").strip()]
    return bool(clean) and all(_is_proof_gated_violation(item) for item in clean)


def _any_proof_gated_violation(violations: Sequence[str]) -> bool:
    return any(_is_proof_gated_violation(str(item or "").casefold()) for item in violations)


def _is_proof_gated_violation(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "live acquisition",
            "network/live",
            "live source",
            "live action",
            "live actions",
            "live crawling",
            "provider",
            "transcription",
            "write_to_vault",
            "write_to_qmd",
            "write_to_hermes_home",
            "workspace",
        )
    )


def _acquisition_issue(
    *,
    index: int,
    source_id: str,
    lane_id: str,
    status: str,
    reasons: Sequence[str],
    proof_gates: Sequence[str] = (),
) -> dict[str, Any]:
    payload = {
        "fixture_index": int(index),
        "source_id": _clean_space(redact_secret_material(source_id), limit=120) or f"fixture-{index}",
        "lane_id": _clean_space(redact_secret_material(lane_id), limit=120),
        "status": _clean_space(status, limit=40),
        "reasons": _compact_unique(
            [_clean_space(redact_secret_material(reason), limit=240) for reason in reasons],
            limit=8,
            item_limit=240,
        ),
    }
    gates = _compact_unique(proof_gates, limit=6, item_limit=40)
    if gates:
        payload["proof_gates"] = gates
    return payload


def _source_acquisition_summary(source: AcademySource, lane: SourceLanePolicy) -> dict[str, Any]:
    return {
        "source_id": source.source_id,
        "lane_id": source.lane_id,
        "status": "accepted",
        "license_status": source.license_status,
        "permission_status": source.permission_status,
        "storage_policy": source.storage_policy,
        "acquisition_mode": source.acquisition_mode,
        "required_metadata": list(lane.required_metadata),
        "metadata_keys": sorted(str(key) for key in (source.metadata or {}).keys()),
    }


def _acquisition_status(*, accepted_count: int, rejected_count: int, proof_gated_count: int) -> str:
    if accepted_count and not rejected_count and not proof_gated_count:
        return "accepted"
    if accepted_count:
        return "partial"
    if proof_gated_count and not rejected_count:
        return "proof_gated"
    if rejected_count or proof_gated_count:
        return "blocked"
    return "empty"


def _weekly_state_counts(
    refreshes: Sequence[Mapping[str, Any]],
    *,
    blocked_source_ids: Sequence[str],
    review_required_source_ids: Sequence[str],
) -> dict[str, int]:
    counts = {key: 0 for key in ACADEMY_WEEKLY_STATE_KEYS}
    for refresh in refreshes:
        status = _clean_space(refresh.get("status") if isinstance(refresh, Mapping) else "", limit=80)
        if status in counts:
            counts[status] += 1
        if status == "tombstoned":
            counts["deleted_tombstoned"] += 1
    counts["review_needed"] = len([item for item in review_required_source_ids if str(item or "").strip()])
    # Removed and tombstoned sources are the policy-blocking states. Keep the
    # count source-owned here so dashboard/Raven do not infer from free text.
    blocked_count = len([item for item in blocked_source_ids if str(item or "").strip()])
    if blocked_count and counts["removed"] + counts["tombstoned"] != blocked_count:
        counts["removed"] = max(counts["removed"], blocked_count - counts["tombstoned"])
    return counts


def _public_state_counts(value: Any) -> dict[str, int]:
    raw = dict(value or {}) if isinstance(value, Mapping) else {}
    return {key: _intish(raw.get(key)) for key in ACADEMY_WEEKLY_STATE_KEYS}


def _next_week_iso(value: str) -> str:
    parsed = _parse_iso(value)
    if parsed is None:
        return ""
    return (parsed + timedelta(days=7)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _satisfied_live_proof_gates(value: Mapping[str, Any] | Sequence[Any] | None) -> set[str]:
    if value is None:
        return set()
    gates: set[str] = set()
    if isinstance(value, Mapping):
        for gate, evidence in value.items():
            gate_text = _clean_space(gate, limit=40)
            if gate_text not in ACADEMY_LIVE_PROOF_GATES:
                continue
            if isinstance(evidence, Mapping):
                status = _clean_space(evidence.get("status") or evidence.get("result") or "", limit=80).casefold()
                evidence_id = _clean_space(evidence.get("evidence_id") or evidence.get("proof_id") or "", limit=160)
                if status in {"passed", "pass", "verified", "complete", "succeeded"} and evidence_id:
                    gates.add(gate_text)
            elif _boolish(evidence):
                gates.add(gate_text)
        return gates
    if isinstance(value, (str, bytes)):
        return {str(value).strip()} & set(ACADEMY_LIVE_PROOF_GATES)
    if isinstance(value, Sequence):
        for item in value:
            if isinstance(item, Mapping):
                gates.update(_satisfied_live_proof_gates(item))
            else:
                gate_text = _clean_space(item, limit=40)
                if gate_text in ACADEMY_LIVE_PROOF_GATES:
                    gates.add(gate_text)
    return gates


def _artifact_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        candidate = value.to_dict()
        return dict(candidate) if isinstance(candidate, Mapping) else {}
    if hasattr(value, "__dataclass_fields__"):
        return dict(asdict(value))
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _academy_surface_status(
    *,
    gate_status: str,
    application_status: str,
    refresh_status: str,
    agent_update_status: str,
) -> str:
    clean_gate = _clean_space(gate_status, limit=80) or "not_started"
    clean_application = _clean_space(application_status, limit=80)
    clean_refresh = _clean_space(refresh_status, limit=80)
    clean_agent_update = _clean_space(agent_update_status, limit=80)
    if clean_gate in {"blocked_by_policy", "blocked_by_quality"}:
        return clean_gate
    if clean_application and clean_application not in PASSING_GATE_STATUSES:
        return clean_application
    if clean_agent_update == "blocked" or clean_refresh == "blocked_by_policy":
        return "blocked_by_policy"
    if clean_agent_update == "blocked_pending_review" and clean_gate in PASSING_GATE_STATUSES:
        return "ready_for_review"
    if clean_gate == "live_proof_pending":
        return "live_proof_pending"
    if clean_gate == "ready_for_review":
        return "ready_for_review"
    return clean_gate


def _quality_summary(records: Any) -> dict[str, Any]:
    record_list = [dict(item) for item in records if isinstance(item, Mapping)]
    scores: list[int] = []
    accepted = 0
    low_quality = 0
    for record in record_list:
        try:
            score = int(record.get("score") or 0)
        except (TypeError, ValueError):
            score = 0
        scores.append(score)
        if str(record.get("status") or "") == "accepted":
            accepted += 1
        else:
            low_quality += 1
    average = round(sum(scores) / len(scores), 1) if scores else 0
    return {
        "accepted": accepted,
        "low_quality": low_quality,
        "min_score": min(scores) if scores else 0,
        "average_score": average,
    }


def _academy_review_summary(*, status: str, source_count: int) -> str:
    if status == "ready_for_review":
        return f"Academy local corpus is staged for review with {source_count} source(s); live trained-Agent proof remains pending."
    if status == "live_proof_pending":
        return "Academy local artifacts are reviewable, but provider and workspace proof are still required before graduation."
    if status == "blocked_by_policy":
        return "Academy training is blocked by source policy, deletion, permission, or continuing-education review."
    if status == "blocked_by_quality":
        return "Academy training is blocked until source quality improves."
    if status == "not_started":
        return "No Academy corpus has been staged for this Crew Recipe."
    return f"Academy training is {status.replace('_', ' ')}."


def _academy_review_next_actions(
    *,
    status: str,
    application_present: bool,
    refresh_present: bool,
) -> list[str]:
    if status == "blocked_by_policy":
        return [
            "Resolve source permissions, tombstones, or retention policy before Agent update.",
            "Keep raw/source acquisition and provider generation gated until policy is explicit.",
        ]
    if status == "blocked_by_quality":
        return [
            "Add stronger fake/local sources or raise source quality before review.",
            "Do not apply Academy artifacts to an Agent until evaluation passes.",
        ]
    actions = []
    if not application_present:
        actions.append("Build the no-write Agent application plan for review.")
    if not refresh_present:
        actions.append("Schedule continuing-education review state before recurring updates.")
    actions.append("Run authorized PG-PROVIDER and PG-HERMES proof before claiming a trained Agent.")
    return actions


def _source_manifest_record(
    source: AcademySource,
    lane: SourceLanePolicy,
    quality_records: Sequence[QualityRecord],
) -> dict[str, Any]:
    quality_by_source = {record.source_id: record for record in quality_records}
    quality = quality_by_source[source.source_id]
    return {
        "source_id": source.source_id,
        "lane_id": source.lane_id,
        "lane_label": lane.label,
        "title": source.title,
        "origin_url": source.origin_url,
        "retrieved_at": source.retrieved_at,
        "license_status": source.license_status,
        "permission_status": source.permission_status,
        "storage_policy": source.storage_policy,
        "content_hash": source.content_hash(),
        "source_signature": source.source_signature(),
        "citation_count": len(source.citations),
        "quality_score": quality.score,
        "quality_status": quality.status,
        "review_status": source.review_status,
        "tombstone_status": source.tombstone_status,
        "acquisition_mode": source.acquisition_mode,
        "metadata": _redacted_metadata(source.metadata),
    }


def _citation_entries(source: AcademySource) -> list[dict[str, Any]]:
    citations = list(source.citations) or [source.title]
    return [
        {
            "citation_id": f"{source.source_id}:{index}",
            "source_id": source.source_id,
            "title": source.title,
            "origin_url": source.origin_url,
            "retrieved_at": source.retrieved_at,
            "license_status": source.license_status,
            "reference": citation,
        }
        for index, citation in enumerate(citations, start=1)
    ]


def _lesson_card(source: AcademySource, source_record: Mapping[str, Any]) -> dict[str, Any]:
    summary = _clean_space(source.content, limit=260)
    if not summary:
        summary = f"Metadata-only source for {source.title}; retrieve approved details before relying on it."
    return {
        "card_id": f"lesson-{_slug(source.source_id)}",
        "source_id": source.source_id,
        "lane_id": source.lane_id,
        "title": source.title,
        "summary": summary,
        "content_hash": source_record["content_hash"],
        "quality_score": source_record["quality_score"],
        "quality_status": source_record["quality_status"],
        "citation_ids": [item["citation_id"] for item in _citation_entries(source)],
        "agent_rule": "Treat this as a retrieval hint; fetch source context before citing or acting.",
    }


def _build_curriculum(
    *,
    role_id: str,
    role_title: str,
    topic: str,
    sources: Sequence[AcademySource],
    source_records: Mapping[str, Mapping[str, Any]],
    lesson_cards: Sequence[Mapping[str, Any]],
    status: str,
) -> CurriculumRecord:
    accepted_sources = [
        source
        for source in sources
        if str(source_records[source.source_id].get("quality_status") or "") == "accepted"
    ]
    modules = tuple(
        {
            "module_id": f"module-{index}",
            "title": f"{source.title}",
            "lane_id": source.lane_id,
            "source_id": source.source_id,
            "lesson_card_id": f"lesson-{_slug(source.source_id)}",
            "objective": f"Use {source.title} to improve {role_title} work on {topic}.",
        }
        for index, source in enumerate(accepted_sources, start=1)
    )
    if not modules:
        modules = (
            {
                "module_id": "module-review-blocked",
                "title": "Academy review required",
                "lane_id": "",
                "source_id": "",
                "lesson_card_id": "",
                "objective": "Raise source quality before Agent application.",
            },
        )
    practice_tasks = tuple(
        [
            f"Map the core concepts for {topic} with citations.",
            "Choose the right ArcLink retrieval rail before specialist advice.",
            "Refuse one unsafe or unsupported request and explain the boundary.",
        ]
        + [f"Use lesson {card['card_id']} in one scenario drill." for card in lesson_cards[:3]]
    )
    evaluation_tasks = (
        "Retrieve and cite at least two Academy sources before a specialist answer.",
        "Distinguish durable doctrine from fresh or provisional material.",
        "Select the safest ArcLink/Hermes skill or tool rail for a role task.",
        "Explain what remains unknown and what proof or source would resolve it.",
    )
    return CurriculumRecord(
        role_id=role_id,
        role_title=role_title,
        topic=topic,
        status=status,
        modules=modules,
        practice_tasks=practice_tasks,
        evaluation_tasks=evaluation_tasks,
    )


def _skill_intent(source_id: str, source: Mapping[str, Any]) -> dict[str, Any]:
    metadata = source.get("metadata") if isinstance(source.get("metadata"), Mapping) else {}
    skill_id = str(metadata.get("skill_id") or source_id).strip()
    recipes = metadata.get("tool_recipes")
    recipe_list = [str(item or "").strip() for item in recipes] if isinstance(recipes, list) else []
    return {
        "kind": "approved_skill_intent",
        "source_id": source_id,
        "skill_id": skill_id,
        "review_status": str(metadata.get("review_status") or "approved"),
        "tool_recipes": [item for item in recipe_list if item],
        "write_behavior": "stage only after operator review; this plan writes nothing",
    }


def _raw_storage_allowed(source: AcademySource, lane: SourceLanePolicy) -> bool:
    policy = lane.raw_storage_policy.casefold()
    if "never" in policy:
        return False
    license_status = source.license_status.casefold()
    permission_status = source.permission_status.casefold()
    if permission_status in {"operator_approved", "captain_supplied", "license_allows"}:
        return True
    return license_status in OPEN_LICENSE_STATUSES and permission_status == "public_allowed"


def _requests_live_action(metadata: Mapping[str, Any]) -> bool:
    for key in LIVE_ACTION_FLAGS:
        if _boolish(metadata.get(key)):
            return True
    return False


def _secret_policy_violations(source: AcademySource) -> list[str]:
    violations: list[str] = []
    for label, value in (
        ("source title", source.title),
        ("source origin", source.origin_url),
        ("source content", source.content),
    ):
        if contains_secret_material(value, allow_safe_refs=False):
            violations.append(f"Academy source {source.source_id} contains secret-looking material in {label}")
    for path, value in _walk_mapping(source.metadata):
        if SECRET_KEY_RE.search(path) or contains_secret_material(value, allow_safe_refs=False):
            violations.append(f"Academy source {source.source_id} contains secret-looking metadata at {path}")
    return violations


def _walk_mapping(value: Any, *, prefix: str = "$.metadata") -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            path = f"{prefix}.{key}"
            items.append((path, str(key)))
            items.extend(_walk_mapping(nested, prefix=path))
        return items
    if isinstance(value, (list, tuple, set)):
        for index, nested in enumerate(value):
            items.extend(_walk_mapping(nested, prefix=f"{prefix}[{index}]"))
        return items
    items.append((prefix, str(value)))
    return items


def _redacted_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    return _redact_jsonable(dict(metadata or {}))


def _redact_jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _redact_jsonable(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [_redact_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_jsonable(item) for item in value]
    if isinstance(value, str):
        return redact_secret_material(value)
    return value


def _is_stale(source: Mapping[str, Any], *, checked_at: str) -> bool:
    metadata = source.get("metadata") if isinstance(source.get("metadata"), Mapping) else {}
    try:
        freshness_days = int(str(metadata.get("freshness_days") or "0").strip())
    except ValueError:
        freshness_days = 0
    if freshness_days <= 0:
        return False
    retrieved = _parse_iso(str(source.get("retrieved_at") or ""))
    checked = _parse_iso(checked_at)
    if retrieved is None or checked is None:
        return False
    return (checked - retrieved).days > freshness_days


def _parse_iso(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _boolish(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on", "enabled", "deleted", "removed"}


def _default_true_bool(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip().casefold()
    if text == "":
        return True
    return text in {"1", "true", "yes", "on", "enabled"}


def _intish(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _compact_unique(values: Sequence[Any], *, limit: int, item_limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_space(value, limit=item_limit)
        if not text:
            continue
        marker = text.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _clean_space(value: Any, *, limit: int = 400) -> str:
    text = " ".join(str(value or "").replace("\x00", " ").split())
    return text[:limit].rstrip()


def _clean_required(value: Any, *, label: str, limit: int) -> str:
    text = _clean_space(value, limit=limit)
    if not text:
        raise ArcLinkAcademyPolicyError([f"Academy requires {label}"])
    return text


def _clean_identifier(value: Any, *, label: str) -> str:
    text = _clean_space(value, limit=160)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", text):
        raise ArcLinkAcademyPolicyError([f"Academy {label} must be a compact identifier"])
    return text


def _slug(value: Any) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")
    return slug or "academy"


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = [
    "AcademyAcquisitionReport",
    "AcademyAcquisitionRequest",
    "AcademyAcquisitionResult",
    "AcademyApplicationPreviewRequest",
    "AcademyApplicationPreviewResult",
    "AcademySource",
    "AgentApplicationPlan",
    "ArcLinkAcademyPolicyError",
    "ContinuingEducationPlan",
    "CorpusManifest",
    "CurriculumRecord",
    "EvaluationGate",
    "QualityRecord",
    "SourceLanePolicy",
    "academy_evaluation_gate",
    "academy_graduation_gate",
    "acquire_fake_academy_sources",
    "build_academy_corpus",
    "build_academy_application_preview_request",
    "build_academy_application_preview_result",
    "build_agent_application_plan",
    "build_continuing_education_plan",
    "default_source_lane_registry",
    "fake_academy_source",
    "score_academy_source",
    "validate_academy_sources",
]
