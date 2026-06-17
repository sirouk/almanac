#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
from string import Template
from typing import Any, Mapping, Protocol, Sequence
import urllib.error
import urllib.request

from arclink_boundary import json_dumps_safe, reject_secret_material
from arclink_chutes import evaluate_chutes_deployment_boundary
from arclink_control import append_arclink_audit, append_arclink_event, utc_now_iso
from arclink_memory_synthesizer import UNSAFE_OUTPUT_PATTERNS
from arclink_onboarding import default_arclink_agent_profile


ALLOWED_CREW_PRESETS = {
    "frontier": "Frontier",
    "concourse": "Concourse",
    "salvage": "Salvage",
    "vanguard": "Vanguard",
}
ALLOWED_CREW_CAPACITIES = {
    "sales": "sales",
    "marketing": "marketing",
    "development": "development",
    "life coaching": "life coaching",
    "life-coaching": "life coaching",
    "companionship": "companionship",
}
CAPACITY_LABELS = {
    "sales": "Sales",
    "marketing": "Marketing",
    "development": "Development",
    "life coaching": "Life Coaching",
    "companionship": "Companionship",
}
PRESET_NOTES = {
    "Frontier": "bold, opportunistic, and comfortable improvising in ambiguous work",
    "Concourse": "proper, process-aware, and careful with compliance-heavy work",
    "Salvage": "resourceful, frugal, and strong at making progress with partial inputs",
    "Vanguard": "directive, regimented, and mission-first for operational clarity",
}
CAPACITY_NOTES = {
    "sales": "turn ambiguity into qualified pipeline and crisp next actions",
    "marketing": "shape positioning, campaigns, and learning loops",
    "development": "ship working systems through clear technical execution",
    "life coaching": "build momentum through reflective questions and accountable plans",
    "companionship": "stay present, useful, and warm without pretending to replace people",
}
CAPACITY_AGENT_TITLES = {
    "sales": ("Revenue Operator", "Pipeline Scout", "Deal Systems Builder", "Account Signal Watch"),
    "marketing": ("Market Signal Operator", "Campaign Architect", "Audience Researcher", "Brand Systems Builder"),
    "development": ("Mission Operator", "Systems Builder", "Code Cartographer", "Release Watch"),
    "life coaching": ("Momentum Coach", "Reflection Guide", "Routine Architect", "Accountability Watch"),
    "companionship": ("Presence Guide", "Memory Companion", "Conversation Steward", "Care Signal Watch"),
}
TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "CREW_RECIPE.md.tmpl"
MAX_PROVIDER_ATTEMPTS = 3


class ArcLinkCrewRecipeError(ValueError):
    pass


class CrewRecipeProvider(Protocol):
    def generate(self, *, prompt: str, model: str) -> str:
        ...


class OpenAICompatibleCrewRecipeProvider:
    """Small operator-configured provider for Crew Training recipe generation."""

    def __init__(self, *, endpoint: str, api_key: str = "", timeout_seconds: float = 45.0) -> None:
        clean_endpoint = str(endpoint or "").strip()
        if not clean_endpoint:
            raise ArcLinkCrewRecipeError("Crew recipe provider endpoint is blank")
        if clean_endpoint.rstrip("/").endswith("/chat/completions"):
            self.endpoint = clean_endpoint.rstrip("/")
        else:
            self.endpoint = clean_endpoint.rstrip("/") + "/chat/completions"
        self.api_key = str(api_key or "").strip()
        self.timeout_seconds = max(3.0, float(timeout_seconds or 45.0))

    def generate(self, *, prompt: str, model: str) -> str:
        clean_model = str(model or "").strip()
        if not clean_model:
            raise ArcLinkCrewRecipeError("Crew recipe provider model is blank")
        body = json.dumps(
            {
                "model": clean_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You write concise, safe ArcLink Crew Recipe prose. "
                            "Return JSON with a single recipe_text string. Do not include URLs, commands, secrets, or instructions to bypass policy."
                        ),
                    },
                    {"role": "user", "content": str(prompt or "")},
                ],
                "temperature": 0.35,
                "max_tokens": 420,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(self.endpoint, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ArcLinkCrewRecipeError(f"Crew recipe provider returned HTTP {exc.code}") from exc
        except (OSError, TimeoutError, json.JSONDecodeError) as exc:
            raise ArcLinkCrewRecipeError("Crew recipe provider request failed") from exc
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, Mapping):
                message = first.get("message")
                if isinstance(message, Mapping) and str(message.get("content") or "").strip():
                    return str(message.get("content") or "")
                if str(first.get("text") or "").strip():
                    return str(first.get("text") or "")
        raise ArcLinkCrewRecipeError("Crew recipe provider returned no usable choice")


def normalize_crew_preset(value: str) -> str:
    clean = re.sub(r"\s+", " ", str(value or "").strip()).casefold()
    if clean not in ALLOWED_CREW_PRESETS:
        raise ArcLinkCrewRecipeError(f"unsupported Crew preset: {value or 'blank'}")
    return ALLOWED_CREW_PRESETS[clean]


def normalize_crew_capacity(value: str) -> str:
    clean = re.sub(r"[\s_]+", " ", str(value or "").strip().replace("-", " ")).casefold()
    if clean not in ALLOWED_CREW_CAPACITIES:
        raise ArcLinkCrewRecipeError(f"unsupported Crew capacity: {value or 'blank'}")
    return ALLOWED_CREW_CAPACITIES[clean]


def _clean_text(value: str, *, label: str, limit: int = 800) -> str:
    clean = re.sub(r"\s+", " ", str(value or "").strip())
    if not clean:
        raise ArcLinkCrewRecipeError(f"Crew Training requires {label}")
    return clean[:limit].rstrip()


def _json_loads(value: str | None, default: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except (TypeError, json.JSONDecodeError):
        return default


def _json_dumps(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), sort_keys=True)


def _recipe_id() -> str:
    return f"crew_{secrets.token_hex(12)}"


def _user_row(conn: sqlite3.Connection, user_id: str) -> dict[str, Any]:
    clean = str(user_id or "").strip()
    row = conn.execute("SELECT * FROM arclink_users WHERE user_id = ?", (clean,)).fetchone()
    if row is None:
        raise KeyError(clean)
    return dict(row)


def _deployment_rows(conn: sqlite3.Connection, user_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM arclink_deployments
        WHERE user_id = ?
          AND status NOT IN ('cancelled', 'teardown_complete', 'torn_down')
        ORDER BY created_at ASC, deployment_id ASC
        """,
        (str(user_id or "").strip(),),
    ).fetchall()
    return [dict(row) for row in rows]


def _deployment_row_for_user(conn: sqlite3.Connection, *, user_id: str, deployment_id: str) -> dict[str, Any]:
    clean_user = str(user_id or "").strip()
    clean_deployment = str(deployment_id or "").strip()
    row = conn.execute(
        """
        SELECT *
        FROM arclink_deployments
        WHERE user_id = ? AND deployment_id = ?
          AND status NOT IN ('cancelled', 'teardown_complete', 'torn_down')
        """,
        (clean_user, clean_deployment),
    ).fetchone()
    if row is None:
        raise ArcLinkCrewRecipeError("Academy Training target Agent was not found on this Crew")
    return dict(row)


def _recipe_public(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    overlay = _json_loads(str(row.get("soul_overlay_json") or "{}"), {})
    return {
        "recipe_id": str(row.get("recipe_id") or ""),
        "user_id": str(row.get("user_id") or ""),
        "preset": str(row.get("preset") or ""),
        "capacity": str(row.get("capacity") or ""),
        "role": str(row.get("role") or ""),
        "mission": str(row.get("mission") or ""),
        "treatment": str(row.get("treatment") or ""),
        "soul_overlay": overlay if isinstance(overlay, dict) else {},
        "applied_at": str(row.get("applied_at") or ""),
        "archived_at": str(row.get("archived_at") or ""),
        "status": str(row.get("status") or ""),
    }


def current_crew_recipe(conn: sqlite3.Connection, *, user_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM arclink_crew_recipes
        WHERE user_id = ? AND status = 'active'
        ORDER BY applied_at DESC, recipe_id DESC
        LIMIT 1
        """,
        (str(user_id or "").strip(),),
    ).fetchone()
    return _recipe_public(dict(row)) if row is not None else None


def prior_crew_recipe(conn: sqlite3.Connection, *, user_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM arclink_crew_recipes
        WHERE user_id = ? AND status != 'active'
        ORDER BY archived_at DESC, applied_at DESC, recipe_id DESC
        LIMIT 1
        """,
        (str(user_id or "").strip(),),
    ).fetchone()
    return _recipe_public(dict(row)) if row is not None else None


def crew_academy_status(conn: sqlite3.Connection, *, user_id: str) -> dict[str, Any]:
    current = current_crew_recipe(conn, user_id=user_id)
    if current is None:
        return _academy_not_started_status(
            summary="Crew Training needs an active recipe before Academy artifacts can be staged.",
        )
    overlay = current.get("soul_overlay") if isinstance(current.get("soul_overlay"), Mapping) else {}
    academy = overlay.get("academy_training") if isinstance(overlay, Mapping) else None
    if not isinstance(academy, Mapping):
        status = _academy_not_started_status(
            summary="No Academy corpus has been staged for this active Crew Recipe.",
        )
        status["recipe_id"] = str(current.get("recipe_id") or "")
        status["recipe_applied_at"] = str(current.get("applied_at") or "")
        return status
    status = _academy_status_public(academy)
    status["recipe_id"] = str(current.get("recipe_id") or status.get("recipe_id") or "")
    status["recipe_applied_at"] = str(current.get("applied_at") or "")
    return status


def stage_crew_academy_review(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    manifest: Any,
    application_plan: Any | None = None,
    continuing_education_plan: Any | None = None,
    graduation_gate: Any | None = None,
    actor_id: str = "",
    reason: str = "Academy local review staged",
) -> dict[str, Any]:
    """Persist a review-only Academy status summary onto the active recipe."""
    clean_user_id = str(user_id or "").strip()
    _user_row(conn, clean_user_id)
    current = current_crew_recipe(conn, user_id=clean_user_id)
    if current is None:
        raise ArcLinkCrewRecipeError("Academy review requires an active Crew Recipe")
    from arclink_academy_trainer import build_academy_review_status

    now = utc_now_iso()
    academy_status = build_academy_review_status(
        manifest=manifest,
        application_plan=application_plan,
        continuing_education_plan=continuing_education_plan,
        graduation_gate=graduation_gate,
        staged_at=now,
    )
    academy_status["recipe_id"] = str(current.get("recipe_id") or "")
    academy_status["review_persisted"] = True
    reject_secret_material(
        academy_status,
        label="ArcLink Academy review",
        error_cls=ArcLinkCrewRecipeError,
    )

    overlay = dict(current.get("soul_overlay") or {})
    overlay["academy_training"] = academy_status
    reject_secret_material(
        overlay,
        label="ArcLink Crew Academy overlay",
        error_cls=ArcLinkCrewRecipeError,
    )
    conn.execute(
        """
        UPDATE arclink_crew_recipes
        SET soul_overlay_json = ?
        WHERE recipe_id = ? AND user_id = ? AND status = 'active'
        """,
        (
            json_dumps_safe(overlay, label="ArcLink Crew Academy overlay", error_cls=ArcLinkCrewRecipeError),
            str(current["recipe_id"]),
            clean_user_id,
        ),
    )
    audit_metadata = {
        "recipe_id": str(current["recipe_id"]),
        "manifest_id": str(academy_status.get("manifest_id") or ""),
        "status": str(academy_status.get("status") or ""),
        "source_count": int(academy_status.get("source_count") or 0),
        "weekly_review_status": str(academy_status.get("weekly_review_status") or ""),
        "evaluation_status": str(academy_status.get("evaluation_status") or ""),
        "graduation_status": str(academy_status.get("graduation_status") or ""),
        "agent_update_status": str(academy_status.get("agent_update_status") or ""),
        "review_needed_count": int(academy_status.get("review_needed_count") or 0),
        "blocked_source_count": int(academy_status.get("blocked_source_count") or 0),
        "next_review_at": str(academy_status.get("next_review_at") or ""),
        "proof_gates": list(academy_status.get("proof_gates") or []),
        "local_only": True,
        "no_network": True,
        "no_write": True,
        "writes_enabled": False,
        "live_proof_required": True,
    }
    clean_actor = str(actor_id or clean_user_id).strip()
    append_arclink_audit(
        conn,
        action="crew_academy_review_staged",
        actor_id=clean_actor,
        target_kind="user",
        target_id=clean_user_id,
        reason=str(reason or "Academy local review staged")[:240],
        metadata=audit_metadata,
        commit=False,
    )
    append_arclink_event(
        conn,
        subject_kind="user",
        subject_id=clean_user_id,
        event_type="crew_academy_review_staged",
        metadata=audit_metadata,
        commit=False,
    )
    conn.commit()
    return {
        "academy_training": crew_academy_status(conn, user_id=clean_user_id),
        "recipe": current_crew_recipe(conn, user_id=clean_user_id),
        "mutation_performed": True,
        "workspace_mutation_performed": False,
        "live_proof_required": True,
    }


def stage_crew_academy_weekly_review(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    manifest: Any,
    observed_sources: Mapping[str, Mapping[str, Any]],
    application_plan: Any | None = None,
    checked_at: str = "",
    next_review_at: str = "",
    actor_id: str = "",
    reason: str = "Academy weekly Continuing Education review staged",
) -> dict[str, Any]:
    """Build and persist a local weekly Academy review on the active recipe."""
    from arclink_academy_trainer import academy_graduation_gate, build_continuing_education_plan

    weekly_review = build_continuing_education_plan(
        manifest,
        observed_sources=observed_sources,
        checked_at=checked_at or utc_now_iso(),
        next_review_at=next_review_at or None,
    )
    graduation_gate = academy_graduation_gate(manifest=manifest)
    return stage_crew_academy_review(
        conn,
        user_id=user_id,
        manifest=manifest,
        application_plan=application_plan,
        continuing_education_plan=weekly_review,
        graduation_gate=graduation_gate,
        actor_id=actor_id,
        reason=reason,
    )


def _academy_not_started_status(*, summary: str) -> dict[str, Any]:
    return {
        "status": "not_started",
        "summary": str(summary or "No Academy corpus has been staged."),
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
        "application_plan_id": "",
        "application_agent_id": "",
        "application_role_id": "",
        "continuing_education_status": "not_started",
        "weekly_review_status": "not_started",
        "evaluation_status": "not_started",
        "graduation_status": "not_started",
        "agent_update_status": "not_started",
        "next_review_at": "",
        "source_state_counts": {
            "unchanged": 0,
            "changed": 0,
            "stale": 0,
            "superseded": 0,
            "removed": 0,
            "tombstoned": 0,
            "deleted_tombstoned": 0,
            "review_needed": 0,
        },
        "review_needed_count": 0,
        "blocked_source_count": 0,
        "blocked_source_ids": [],
        "review_required_source_ids": [],
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
        "review_persisted": False,
        "agent_count": 0,
        "trained_agent_count": 0,
        "pending_agent_count": 0,
        "skipped_agent_count": 0,
        "agents": [],
    }


def _academy_status_public(academy: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "status",
        "summary",
        "manifest_id",
        "role_id",
        "role_title",
        "topic",
        "source_count",
        "lane_count",
        "lanes",
        "quality",
        "curriculum_status",
        "application_status",
        "application_plan_id",
        "application_agent_id",
        "application_role_id",
        "continuing_education_status",
        "weekly_review_status",
        "evaluation_status",
        "graduation_status",
        "agent_update_status",
        "next_review_at",
        "source_state_counts",
        "review_needed_count",
        "blocked_source_count",
        "blocked_source_ids",
        "review_required_source_ids",
        "proof_gates",
        "next_actions",
        "review_surfaces",
        "local_only",
        "no_network",
        "no_write",
        "writes_enabled",
        "live_proof_required",
        "review_persisted",
        "staged_at",
        "agent_count",
        "trained_agent_count",
        "pending_agent_count",
        "skipped_agent_count",
        "agents",
    )
    payload = {key: academy.get(key) for key in allowed if key in academy}
    base = _academy_not_started_status(summary="No Academy corpus has been staged.")
    base.update(payload)
    reject_secret_material(
        base,
        label="ArcLink Academy status",
        error_cls=ArcLinkCrewRecipeError,
    )
    return base


def _slug(value: str, *, fallback: str = "academy") -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", str(value or "").strip().lower()).strip("-")
    return slug[:80] or fallback


def _agent_label(deployment: Mapping[str, Any]) -> str:
    return str(
        deployment.get("agent_name")
        or deployment.get("prefix")
        or deployment.get("deployment_id")
        or "Agent"
    ).strip()


def _agent_title(deployment: Mapping[str, Any]) -> str:
    return str(deployment.get("agent_title") or _agent_label(deployment)).strip()


def build_crew_academy_artifacts_for_agent(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    deployment_id: str,
    created_at: str = "",
) -> dict[str, Any]:
    """Build governed local Academy artifacts for one Captain-owned Agent.

    This is still the local/no-network Academy slice: it creates reviewable
    curriculum, source-map, SOUL-overlay, skill, qmd, and memory intents from
    approved local fixtures. It does not crawl, call providers, or write Agent
    workspace files.
    """
    clean_user = str(user_id or "").strip()
    current = current_crew_recipe(conn, user_id=clean_user)
    if current is None:
        raise ArcLinkCrewRecipeError("Academy Training requires an active Crew Recipe")
    deployment = _deployment_row_for_user(conn, user_id=clean_user, deployment_id=deployment_id)
    from arclink_academy_trainer import (
        academy_graduation_gate,
        build_academy_corpus,
        build_agent_application_plan,
        build_continuing_education_plan,
        fake_academy_source,
    )

    now = str(created_at or utc_now_iso())
    label = _agent_label(deployment)
    title = _agent_title(deployment)
    role_slug = _slug(f"{deployment_id}-{title}", fallback=_slug(deployment_id, fallback="agent"))
    mission = str(current.get("mission") or "").strip()
    capacity = str(current.get("capacity") or "").strip()
    preset = str(current.get("preset") or "").strip()
    topic = f"{title} specialist formation for {mission or capacity or 'the Captain mission'}"
    sources = [
        fake_academy_source(
            source_id=f"src-{role_slug}-crew-brief",
            lane_id="organization_private",
            title=f"{label} Crew mission brief",
            origin_url=f"arclink-crew-recipe://{current.get('recipe_id') or clean_user}/{deployment_id}",
            retrieved_at=now,
            license_status="internal-approved",
            permission_status="operator_approved",
            storage_policy="derived_summary",
            content=(
                f"Captain role: {current.get('role') or 'unspecified'}. "
                f"Mission: {mission or 'unspecified'}. "
                f"Preset: {preset or 'unspecified'}. Capacity: {capacity or 'unspecified'}. "
                f"{label} should specialize as {title}, retrieve before specialist claims, cite sources, "
                "and keep unsafe or unsupported work behind Raven and ArcLink proof gates."
            ),
            citations=["Crew Recipe", "Captain mission", "Agent title"],
            metadata={
                "owner": clean_user,
                "audience_scope": "role-training-only",
                "official": True,
                "examples": True,
                "cross_source_agreement": True,
            },
        ),
        fake_academy_source(
            source_id=f"src-{role_slug}-source-map",
            lane_id="wikimedia",
            title=f"{title} source map baseline",
            origin_url=f"https://example.test/academy/{role_slug}/source-map",
            retrieved_at=now,
            license_status="cc-by-sa",
            permission_status="public_allowed",
            storage_policy="derived_summary",
            content=(
                f"A {title} needs a topic map, vocabulary, decision checks, practice tasks, "
                "and cross-source agreement before giving specialist advice. The Agent should "
                "distinguish facts, assumptions, risks, and next retrieval targets."
            ),
            citations=["topic map", "vocabulary", "decision checks", "practice tasks"],
            metadata={
                "revision": f"{role_slug}-baseline-1",
                "official": True,
                "examples": True,
                "fresh": True,
            },
        ),
        fake_academy_source(
            source_id=f"src-{role_slug}-retrieval-skill",
            lane_id="skill_tool_catalog",
            title=f"{title} retrieval and tool-choice skill",
            origin_url="local-skill-catalog://academy-retrieval-and-tool-choice",
            retrieved_at=now,
            license_status="internal-approved",
            permission_status="operator_approved",
            storage_policy="metadata_only",
            content=(
                "Use knowledge.search-and-fetch or vault.search-and-fetch before specialist answers; "
                "use Drive, Code, Terminal, and MCP rails according to the Agent's authorized scope; "
                "ask Raven or the Captain for proof-gated work."
            ),
            citations=["knowledge.search-and-fetch", "vault.search-and-fetch", "authorized tool scope"],
            metadata={
                "skill_id": "academy-retrieval-and-tool-choice",
                "review_status": "approved",
                "public_skill": True,
                "maintained": True,
                "examples": True,
            },
            review_status="approved",
        ),
    ]
    manifest = build_academy_corpus(
        role_id=f"role-{role_slug}",
        role_title=title,
        topic=topic,
        sources=sources,
        created_at=now,
    )
    application = build_agent_application_plan(
        manifest,
        agent_id=str(deployment.get("deployment_id") or deployment_id),
        created_at=now,
    )
    refresh = build_continuing_education_plan(
        manifest,
        observed_sources={
            source_id: {"content_hash": source["content_hash"]}
            for source_id, source in manifest.sources.items()
        },
        checked_at=now,
    )
    graduation = academy_graduation_gate(manifest=manifest)
    return {
        "deployment": deployment,
        "manifest": manifest,
        "application_plan": application,
        "continuing_education_plan": refresh,
        "graduation_gate": graduation,
    }


def _academy_status_for_agent(
    *,
    deployment: Mapping[str, Any],
    manifest: Any,
    application_plan: Any,
    continuing_education_plan: Any,
    graduation_gate: Any,
    staged_at: str,
    skipped: bool = False,
) -> dict[str, Any]:
    if skipped:
        return {
            "deployment_id": str(deployment.get("deployment_id") or ""),
            "agent_name": _agent_label(deployment),
            "agent_title": _agent_title(deployment),
            "status": "skipped",
            "summary": "Captain skipped Academy Training for this Agent.",
            "manifest_id": "",
            "application_plan_id": "",
            "source_count": 0,
            "lane_count": 0,
            "graduation_status": "skipped",
            "staged_at": staged_at,
            "review_persisted": True,
            "local_only": True,
            "no_network": True,
            "no_write": True,
            "writes_enabled": False,
            "live_proof_required": False,
        }
    from arclink_academy_trainer import build_academy_review_status

    status = build_academy_review_status(
        manifest=manifest,
        application_plan=application_plan,
        continuing_education_plan=continuing_education_plan,
        graduation_gate=graduation_gate,
        staged_at=staged_at,
    )
    status.update(
        {
            "deployment_id": str(deployment.get("deployment_id") or ""),
            "agent_name": _agent_label(deployment),
            "agent_title": _agent_title(deployment),
            "review_persisted": True,
        }
    )
    return status


def _academy_agents_from_status(status: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(status, Mapping):
        return {}
    raw_agents = status.get("agents")
    agents: dict[str, dict[str, Any]] = {}
    if isinstance(raw_agents, Mapping):
        iterable = raw_agents.values()
    elif isinstance(raw_agents, list):
        iterable = raw_agents
    else:
        iterable = ()
    for item in iterable:
        if not isinstance(item, Mapping):
            continue
        deployment_id = str(item.get("deployment_id") or "").strip()
        if deployment_id:
            agents[deployment_id] = dict(item)
    return agents


def _academy_agent_public(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "deployment_id": str(item.get("deployment_id") or ""),
        "agent_name": str(item.get("agent_name") or ""),
        "agent_title": str(item.get("agent_title") or ""),
        "status": str(item.get("status") or "not_started"),
        "summary": str(item.get("summary") or ""),
        "manifest_id": str(item.get("manifest_id") or ""),
        "application_plan_id": str(item.get("application_plan_id") or ""),
        "source_count": int(item.get("source_count") or 0),
        "lane_count": int(item.get("lane_count") or 0),
        "graduation_status": str(item.get("graduation_status") or ""),
        "staged_at": str(item.get("staged_at") or ""),
        "proof_gates": list(item.get("proof_gates") or []),
        "local_only": bool(item.get("local_only", True)),
        "no_network": bool(item.get("no_network", True)),
        "no_write": bool(item.get("no_write", True)),
        "writes_enabled": bool(item.get("writes_enabled", False)),
        "live_proof_required": bool(item.get("live_proof_required", True)),
    }


def _academy_rollup_status(
    *,
    recipe: Mapping[str, Any],
    deployments: Sequence[Mapping[str, Any]],
    agents: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    public_agents = [_academy_agent_public(agents[str(dep.get("deployment_id") or "")]) for dep in deployments if str(dep.get("deployment_id") or "") in agents]
    trained = [item for item in public_agents if item["status"] not in {"skipped", "not_started"}]
    skipped = [item for item in public_agents if item["status"] == "skipped"]
    pending = max(0, len(deployments) - len(public_agents))
    source_count = sum(int(item.get("source_count") or 0) for item in trained)
    proof_gates = sorted({gate for item in trained for gate in item.get("proof_gates", [])})
    if trained:
        status = "ready_for_review"
        summary = (
            f"Academy Training staged for {len(trained)} of {len(deployments)} Agent(s); "
            f"{len(skipped)} skipped, {pending} pending. Provider and Hermes proof remain required before graduation."
        )
    elif skipped and not pending:
        status = "skipped"
        summary = "Captain skipped Academy Training for every Agent in this Crew."
    else:
        status = "not_started"
        summary = "No Academy corpus has been staged for this active Crew Recipe."
    first = trained[0] if trained else {}
    return {
        "status": status,
        "summary": summary,
        "manifest_id": str(first.get("manifest_id") or ""),
        "role_id": "",
        "role_title": str(first.get("agent_title") or ""),
        "topic": "",
        "source_count": source_count,
        "lane_count": max((int(item.get("lane_count") or 0) for item in trained), default=0),
        "lanes": [],
        "quality": {"accepted": source_count, "low_quality": 0, "min_score": 70, "average_score": 0},
        "curriculum_status": "ready_for_review" if trained else "not_started",
        "application_status": "ready_for_review" if trained else "not_started",
        "application_plan_id": str(first.get("application_plan_id") or ""),
        "application_agent_id": str(first.get("deployment_id") or ""),
        "application_role_id": "",
        "continuing_education_status": "ready_for_review" if trained else "not_started",
        "weekly_review_status": "ready_for_review" if trained else "not_started",
        "evaluation_status": "ready_for_review" if trained else "not_started",
        "graduation_status": "blocked_by_live_proof" if trained else status,
        "agent_update_status": "identity_projected" if trained else "not_started",
        "next_review_at": "",
        "source_state_counts": {
            "unchanged": source_count,
            "changed": 0,
            "stale": 0,
            "superseded": 0,
            "removed": 0,
            "tombstoned": 0,
            "deleted_tombstoned": 0,
            "review_needed": 0,
        },
        "review_needed_count": 0,
        "blocked_source_count": 0,
        "blocked_source_ids": [],
        "review_required_source_ids": [],
        "proof_gates": proof_gates or ["PG-PROVIDER", "PG-HERMES"],
        "next_actions": [
            "Review staged Academy plans for each Agent.",
            "Run provider and Hermes proof before graduating trained specialists.",
        ],
        "review_surfaces": ["Crew Training", "dashboard", "Operator Raven"],
        "local_only": True,
        "no_network": True,
        "no_write": True,
        "writes_enabled": False,
        "live_proof_required": bool(trained),
        "review_persisted": True,
        "recipe_id": str(recipe.get("recipe_id") or ""),
        "recipe_applied_at": str(recipe.get("applied_at") or ""),
        "agent_count": len(deployments),
        "trained_agent_count": len(trained),
        "pending_agent_count": pending,
        "skipped_agent_count": len(skipped),
        "agents": public_agents,
    }


def _persist_academy_agent_status(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    deployment: Mapping[str, Any],
    agent_status: Mapping[str, Any],
    actor_id: str = "",
    reason: str = "Academy Agent Training staged",
) -> dict[str, Any]:
    clean_user = str(user_id or "").strip()
    current = current_crew_recipe(conn, user_id=clean_user)
    if current is None:
        raise ArcLinkCrewRecipeError("Academy Training requires an active Crew Recipe")
    deployments = _deployment_rows(conn, clean_user)
    overlay = dict(current.get("soul_overlay") or {})
    agents = _academy_agents_from_status(overlay.get("academy_training") if isinstance(overlay, Mapping) else None)
    clean_status = _academy_agent_public(agent_status)
    deployment_id = str(deployment.get("deployment_id") or clean_status.get("deployment_id") or "").strip()
    clean_status["deployment_id"] = deployment_id
    agents[deployment_id] = clean_status
    rollup = _academy_rollup_status(recipe=current, deployments=deployments, agents=agents)
    overlay["academy_training"] = rollup
    reject_secret_material(overlay, label="ArcLink Crew Academy overlay", error_cls=ArcLinkCrewRecipeError)
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE arclink_crew_recipes
        SET soul_overlay_json = ?
        WHERE recipe_id = ? AND user_id = ? AND status = 'active'
        """,
        (
            json_dumps_safe(overlay, label="ArcLink Crew Academy overlay", error_cls=ArcLinkCrewRecipeError),
            str(current["recipe_id"]),
            clean_user,
        ),
    )
    metadata = _json_loads(str(deployment.get("metadata_json") or "{}"), {})
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["academy_training"] = clean_status
    conn.execute(
        """
        UPDATE arclink_deployments
        SET metadata_json = ?, updated_at = ?
        WHERE deployment_id = ? AND user_id = ?
        """,
        (_json_dumps(metadata), now, deployment_id, clean_user),
    )
    audit_metadata = {
        "recipe_id": str(current["recipe_id"]),
        "deployment_id": deployment_id,
        "agent_name": str(clean_status.get("agent_name") or ""),
        "agent_title": str(clean_status.get("agent_title") or ""),
        "manifest_id": str(clean_status.get("manifest_id") or ""),
        "status": str(clean_status.get("status") or ""),
        "source_count": int(clean_status.get("source_count") or 0),
        "graduation_status": str(clean_status.get("graduation_status") or ""),
        "local_only": True,
        "no_network": True,
        "no_write": True,
        "writes_enabled": False,
    }
    clean_actor = str(actor_id or clean_user).strip()
    append_arclink_audit(
        conn,
        action="crew_academy_agent_training_staged",
        actor_id=clean_actor,
        target_kind="deployment",
        target_id=deployment_id,
        reason=str(reason or "Academy Agent Training staged")[:240],
        metadata=audit_metadata,
        commit=False,
    )
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=deployment_id,
        event_type="crew_academy_agent_training_staged",
        metadata=audit_metadata,
        commit=False,
    )
    conn.commit()
    try:
        from arclink_provisioning import project_arclink_deployment_identity_context

        projection = project_arclink_deployment_identity_context(
            conn,
            deployment_id=deployment_id,
            source="academy_training",
        )
    except Exception as exc:  # noqa: BLE001 - projection is best-effort and audited above.
        projection = {"status": "skipped", "reason": str(exc)[:160]}
    return {
        "academy_training": crew_academy_status(conn, user_id=clean_user),
        "agent_academy_training": clean_status,
        "recipe": current_crew_recipe(conn, user_id=clean_user),
        "identity_projection": projection,
        "mutation_performed": True,
        "workspace_mutation_performed": False,
        "live_proof_required": bool(clean_status.get("live_proof_required", True)),
    }


def stage_crew_academy_agent_training(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    deployment_id: str,
    actor_id: str = "",
    reason: str = "Academy Agent Training staged",
) -> dict[str, Any]:
    artifacts = build_crew_academy_artifacts_for_agent(
        conn,
        user_id=user_id,
        deployment_id=deployment_id,
    )
    deployment = artifacts["deployment"]
    staged_at = utc_now_iso()
    agent_status = _academy_status_for_agent(
        deployment=deployment,
        manifest=artifacts["manifest"],
        application_plan=artifacts["application_plan"],
        continuing_education_plan=artifacts["continuing_education_plan"],
        graduation_gate=artifacts["graduation_gate"],
        staged_at=staged_at,
    )
    return _persist_academy_agent_status(
        conn,
        user_id=user_id,
        deployment=deployment,
        agent_status=agent_status,
        actor_id=actor_id,
        reason=reason,
    )


def skip_crew_academy_agent_training(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    deployment_id: str,
    actor_id: str = "",
    reason: str = "Academy Agent Training skipped",
) -> dict[str, Any]:
    deployment = _deployment_row_for_user(conn, user_id=user_id, deployment_id=deployment_id)
    agent_status = _academy_status_for_agent(
        deployment=deployment,
        manifest=None,
        application_plan=None,
        continuing_education_plan=None,
        graduation_gate=None,
        staged_at=utc_now_iso(),
        skipped=True,
    )
    return _persist_academy_agent_status(
        conn,
        user_id=user_id,
        deployment=deployment,
        agent_status=agent_status,
        actor_id=actor_id,
        reason=reason,
    )


def _pod_count_and_agents(deployments: list[Mapping[str, Any]]) -> tuple[int, str, str]:
    names: list[str] = []
    titles: list[str] = []
    for dep in deployments:
        label = str(dep.get("agent_name") or dep.get("prefix") or dep.get("deployment_id") or "").strip()
        title = str(dep.get("agent_title") or "").strip()
        if label:
            names.append(label)
        if title:
            titles.append(f"{label}: {title}" if label else title)
    return len(deployments), ", ".join(names), "; ".join(titles)


def curated_crew_agent_profiles(
    deployments: list[Mapping[str, Any]],
    *,
    preset: str,
    capacity: str,
) -> list[dict[str, str]]:
    clean_preset = normalize_crew_preset(preset)
    clean_capacity = normalize_crew_capacity(capacity)
    titles = CAPACITY_AGENT_TITLES.get(clean_capacity, ())
    profiles: list[dict[str, str]] = []
    for index, deployment in enumerate(deployments, start=1):
        base = default_arclink_agent_profile(index)
        title = titles[index - 1] if index <= len(titles) else str(base["title"])
        profiles.append(
            {
                "deployment_id": str(deployment.get("deployment_id") or ""),
                "agent_name": str(base["name"]),
                "agent_title": title,
                "agent_personality": (
                    f"{base['personality']} Crew Training tunes this Agent for "
                    f"{CAPACITY_NOTES[clean_capacity]} in a {PRESET_NOTES[clean_preset]} posture."
                ),
                "dashboard_theme": str(base["dashboard_theme"]),
                "theme_label": str(base["theme_label"]),
                "theme_accent_hex": str(base["theme_accent_hex"]),
            }
        )
    return profiles


def deterministic_crew_recipe(
    *,
    role: str,
    mission: str,
    treatment: str,
    preset: str,
    capacity: str,
    applied_at: str = "",
) -> dict[str, Any]:
    clean_preset = normalize_crew_preset(preset)
    clean_capacity = normalize_crew_capacity(capacity)
    clean_role = _clean_text(role, label="Captain role")
    clean_mission = _clean_text(mission, label="Captain mission")
    clean_treatment = _clean_text(treatment, label="Captain treatment", limit=400)
    capacity_label = CAPACITY_LABELS[clean_capacity]
    when = applied_at or utc_now_iso()
    recipe_text = (
        f"{clean_preset} {capacity_label} Crew Recipe: treat the Captain as {clean_treatment}; "
        f"support their role as {clean_role}; focus the Crew on {clean_mission}; "
        f"operate in a style that is {PRESET_NOTES[clean_preset]} and tuned to {CAPACITY_NOTES[clean_capacity]}."
    )
    overlay = {
        "crew_preset": clean_preset,
        "crew_capacity": capacity_label,
        "captain_role": clean_role,
        "captain_mission": clean_mission,
        "captain_treatment": clean_treatment,
        "applied_at": when,
        "crew_recipe_text": recipe_text,
    }
    return {"recipe_text": recipe_text, "soul_overlay": overlay}


def _render_prompt(
    *,
    role: str,
    mission: str,
    treatment: str,
    preset: str,
    capacity: str,
    pod_count: int,
    agent_names: str,
    agent_titles: str,
    mode: str,
) -> str:
    values = {
        "captain_role": role,
        "captain_mission": mission,
        "captain_treatment": treatment,
        "crew_preset": preset,
        "crew_capacity": CAPACITY_LABELS[capacity],
        "pod_count": str(pod_count),
        "agent_names": agent_names or "not named yet",
        "agent_titles": agent_titles or "not titled yet",
        "generation_mode": mode,
    }
    if TEMPLATE_PATH.exists():
        raw = TEMPLATE_PATH.read_text(encoding="utf-8")
    else:
        raw = "Write one safe Crew Recipe for $captain_role, $captain_mission, $crew_preset, $crew_capacity."
    return Template(raw).safe_substitute(values)


def _has_unsafe_output(value: str) -> bool:
    text = str(value or "")
    return any(pattern.search(text) for pattern in UNSAFE_OUTPUT_PATTERNS)


def _extract_provider_recipe_text(output: str) -> str:
    raw = str(output or "").strip()
    if not raw:
        raise ArcLinkCrewRecipeError("Crew recipe provider returned empty output")
    parsed = _json_loads(raw, None)
    if isinstance(parsed, dict):
        candidate = str(parsed.get("recipe_text") or parsed.get("paragraph") or parsed.get("recipe") or "").strip()
        if candidate:
            return re.sub(r"\s+", " ", candidate)[:1200].rstrip()
    return re.sub(r"\s+", " ", raw)[:1200].rstrip()


def _call_provider(provider_client: Any, *, prompt: str, model: str) -> str:
    if hasattr(provider_client, "generate"):
        return str(provider_client.generate(prompt=prompt, model=model))
    if callable(provider_client):
        return str(provider_client(prompt=prompt, model=model))
    raise ArcLinkCrewRecipeError("Crew recipe provider client is not callable")


def _truthy_env(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def default_crew_recipe_provider(env: Mapping[str, str]) -> CrewRecipeProvider | None:
    if _truthy_env(env.get("ARCLINK_CREW_RECIPE_LIVE_DISABLED")):
        return None
    endpoint = (
        str(env.get("ARCLINK_CREW_RECIPE_ENDPOINT") or "").strip()
        or str(env.get("ARCLINK_LLM_ROUTER_URL") or "").strip()
        or str(env.get("OPENAI_BASE_URL") or "").strip()
    )
    if not endpoint:
        return None
    api_key = (
        str(env.get("ARCLINK_CREW_RECIPE_API_KEY") or "").strip()
        or str(env.get("ARCLINK_CREW_RECIPE_BEARER_TOKEN") or "").strip()
        or str(env.get("OPENAI_API_KEY") or "").strip()
    )
    try:
        timeout = float(str(env.get("ARCLINK_CREW_RECIPE_TIMEOUT_SECONDS") or "45").strip())
    except ValueError:
        timeout = 45.0
    return OpenAICompatibleCrewRecipeProvider(endpoint=endpoint, api_key=api_key, timeout_seconds=timeout)


def _provider_context(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    deployments: list[Mapping[str, Any]],
    env: Mapping[str, str],
) -> dict[str, Any]:
    explicit_endpoint = (
        str(env.get("ARCLINK_CREW_RECIPE_ENDPOINT") or "").strip()
        or str(env.get("ARCLINK_LLM_ROUTER_URL") or "").strip()
        or str(env.get("OPENAI_BASE_URL") or "").strip()
    )
    explicit_model = (
        str(env.get("ARCLINK_CREW_RECIPE_MODEL") or "").strip()
        or str(env.get("ARCLINK_CREW_RECIPE_FALLBACK_MODEL") or "").strip()
    )
    if explicit_endpoint and explicit_model and not _truthy_env(env.get("ARCLINK_CREW_RECIPE_LIVE_DISABLED")):
        return {
            "allow": True,
            "deployment_id": "crew-recipe-provider",
            "model": explicit_model,
            "reason": "operator-configured Crew Recipe provider",
        }
    user = _user_row(conn, user_id)
    for dep in deployments:
        metadata = _json_loads(str(dep.get("metadata_json") or "{}"), {})
        if not isinstance(metadata, dict):
            metadata = {}
        boundary = evaluate_chutes_deployment_boundary(
            deployment_id=str(dep.get("deployment_id") or ""),
            user_id=user_id,
            metadata=metadata,
            billing_state=str(user.get("entitlement_state") or ""),
            env=env,
        )
        if boundary.allow_inference:
            model = (
                str(metadata.get("provider_model_id") or "").strip()
                or str((metadata.get("chutes") or {}).get("model_id") if isinstance(metadata.get("chutes"), Mapping) else "").strip()
                or str(env.get("ARCLINK_CREW_RECIPE_FALLBACK_MODEL") or "").strip()
            )
            return {
                "allow": True,
                "deployment_id": str(dep.get("deployment_id") or ""),
                "model": model,
                "reason": boundary.reason,
            }
    return {
        "allow": False,
        "deployment_id": "",
        "model": str(env.get("ARCLINK_CREW_RECIPE_FALLBACK_MODEL") or "").strip(),
        "reason": "Live recipe generation requires configured provider credentials. Using preset-only overlay.",
    }


def preview_crew_recipe(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    role: str,
    mission: str,
    treatment: str,
    preset: str,
    capacity: str,
    provider_client: CrewRecipeProvider | Any | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    _user_row(conn, user_id)
    deployments = _deployment_rows(conn, user_id)
    clean_preset = normalize_crew_preset(preset)
    clean_capacity = normalize_crew_capacity(capacity)
    clean_role = _clean_text(role, label="Captain role")
    clean_mission = _clean_text(mission, label="Captain mission")
    clean_treatment = _clean_text(treatment, label="Captain treatment", limit=400)
    now = utc_now_iso()
    fallback = deterministic_crew_recipe(
        role=clean_role,
        mission=clean_mission,
        treatment=clean_treatment,
        preset=clean_preset,
        capacity=clean_capacity,
        applied_at=now,
    )
    crew_agents = curated_crew_agent_profiles(deployments, preset=clean_preset, capacity=clean_capacity)
    fallback["soul_overlay"]["crew_agents"] = crew_agents
    effective_env = dict(os.environ if env is None else env)
    if provider_client is None:
        provider_client = default_crew_recipe_provider(effective_env)
    provider = _provider_context(conn, user_id=user_id, deployments=deployments, env=effective_env)
    pod_count, agent_names, agent_titles = _pod_count_and_agents(deployments)
    prompt = _render_prompt(
        role=clean_role,
        mission=clean_mission,
        treatment=clean_treatment,
        preset=clean_preset,
        capacity=clean_capacity,
        pod_count=pod_count,
        agent_names=agent_names,
        agent_titles=agent_titles,
        mode="live" if provider["allow"] else "fallback",
    )
    model = str(provider.get("model") or "").strip()
    attempts = 0
    unsafe_rejections = 0
    errors: list[str] = []
    if provider_client is not None and provider["allow"] and model:
        for _ in range(MAX_PROVIDER_ATTEMPTS):
            attempts += 1
            try:
                output = _call_provider(provider_client, prompt=prompt, model=model)
                if _has_unsafe_output(output):
                    unsafe_rejections += 1
                    continue
                recipe_text = _extract_provider_recipe_text(output)
                if _has_unsafe_output(recipe_text):
                    unsafe_rejections += 1
                    continue
                overlay = dict(fallback["soul_overlay"])
                overlay["crew_recipe_text"] = recipe_text
                return {
                    "mode": "provider",
                    "fallback": False,
                    "fallback_reason": "",
                    "model": model,
                    "provider_deployment_id": str(provider.get("deployment_id") or ""),
                    "attempts": attempts,
                    "unsafe_rejections": unsafe_rejections,
                    "errors": errors,
                    "prompt": prompt,
                    "recipe_text": recipe_text,
                    "soul_overlay": overlay,
                }
            except Exception as exc:  # noqa: BLE001 - provider boundary is intentionally injectable.
                errors.append(str(exc)[:240])
    reason = str(provider.get("reason") or "Crew recipe provider unavailable; using deterministic preset-only overlay.")
    if provider["allow"] and (provider_client is None or not model):
        reason = "Crew recipe provider unavailable in this environment; using deterministic preset-only overlay."
    elif unsafe_rejections:
        reason = "Crew recipe provider output failed the unsafe-output boundary; using deterministic preset-only overlay."
    return {
        "mode": "fallback",
        "fallback": True,
        "fallback_reason": reason,
        "model": model,
        "provider_deployment_id": str(provider.get("deployment_id") or ""),
        "attempts": attempts,
        "unsafe_rejections": unsafe_rejections,
        "errors": errors,
        "prompt": prompt,
        "recipe_text": str(fallback["recipe_text"]),
        "soul_overlay": dict(fallback["soul_overlay"]),
    }


def apply_crew_recipe(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    role: str,
    mission: str,
    treatment: str,
    preset: str,
    capacity: str,
    provider_client: CrewRecipeProvider | Any | None = None,
    env: Mapping[str, str] | None = None,
    actor_id: str = "",
    operator_on_behalf: bool = False,
) -> dict[str, Any]:
    preview = preview_crew_recipe(
        conn,
        user_id=user_id,
        role=role,
        mission=mission,
        treatment=treatment,
        preset=preset,
        capacity=capacity,
        provider_client=provider_client,
        env=env,
    )
    clean_user_id = str(user_id or "").strip()
    clean_actor = str(actor_id or clean_user_id).strip()
    now = str(preview["soul_overlay"]["applied_at"])
    recipe_id = _recipe_id()
    crew_agents = [
        dict(item)
        for item in preview["soul_overlay"].get("crew_agents", [])
        if isinstance(item, Mapping)
    ]
    conn.execute(
        """
        UPDATE arclink_crew_recipes
        SET status = 'archived', archived_at = ?
        WHERE user_id = ? AND status = 'active'
        """,
        (now, clean_user_id),
    )
    conn.execute(
        """
        INSERT INTO arclink_crew_recipes (
          recipe_id, user_id, preset, capacity, role, mission, treatment,
          soul_overlay_json, applied_at, archived_at, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', 'active')
        """,
        (
            recipe_id,
            clean_user_id,
            str(preview["soul_overlay"]["crew_preset"]),
            normalize_crew_capacity(capacity),
            str(preview["soul_overlay"]["captain_role"]),
            str(preview["soul_overlay"]["captain_mission"]),
            str(preview["soul_overlay"]["captain_treatment"]),
            _json_dumps(preview["soul_overlay"]),
            now,
        ),
    )
    deployments = _deployment_rows(conn, clean_user_id)
    profiles_by_deployment = {str(item.get("deployment_id") or ""): item for item in crew_agents}
    for index, deployment in enumerate(deployments, start=1):
        deployment_id = str(deployment.get("deployment_id") or "")
        profile = profiles_by_deployment.get(deployment_id)
        if profile is None:
            profile = curated_crew_agent_profiles([deployment], preset=str(preview["soul_overlay"]["crew_preset"]), capacity=normalize_crew_capacity(capacity))[0]
        metadata = _json_loads(str(deployment.get("metadata_json") or "{}"), {})
        if not isinstance(metadata, dict):
            metadata = {}
        metadata.update(
            {
                "crew_recipe_id": recipe_id,
                "crew_training_applied_at": now,
                "agent_personality": str(profile.get("agent_personality") or ""),
                "dashboard_theme": str(profile.get("dashboard_theme") or metadata.get("dashboard_theme") or ""),
                "theme_label": str(profile.get("theme_label") or metadata.get("theme_label") or ""),
                "theme_accent_hex": str(profile.get("theme_accent_hex") or metadata.get("theme_accent_hex") or ""),
            }
        )
        conn.execute(
            """
            UPDATE arclink_deployments
            SET agent_name = ?, agent_title = ?, metadata_json = ?, updated_at = ?
            WHERE deployment_id = ? AND user_id = ?
            """,
            (
                str(profile.get("agent_name") or deployment.get("agent_name") or ""),
                str(profile.get("agent_title") or deployment.get("agent_title") or ""),
                _json_dumps(metadata),
                now,
                deployment_id,
                clean_user_id,
            ),
        )
    conn.execute(
        """
        UPDATE arclink_users
        SET captain_role = ?, captain_mission = ?, captain_treatment = ?, updated_at = ?
        WHERE user_id = ?
        """,
        (
            str(preview["soul_overlay"]["captain_role"]),
            str(preview["soul_overlay"]["captain_mission"]),
            str(preview["soul_overlay"]["captain_treatment"]),
            now,
            clean_user_id,
        ),
    )
    action = "crew_recipe_applied_by_operator" if operator_on_behalf else "crew_recipe_applied"
    audit_metadata = {
        "recipe_id": recipe_id,
        "preset": str(preview["soul_overlay"]["crew_preset"]),
        "capacity": normalize_crew_capacity(capacity),
        "mode": str(preview["mode"]),
        "fallback": bool(preview["fallback"]),
        "operator_on_behalf": bool(operator_on_behalf),
    }
    append_arclink_audit(
        conn,
        action=action,
        actor_id=clean_actor,
        target_kind="user",
        target_id=clean_user_id,
        reason="Crew Training confirmed",
        metadata=audit_metadata,
        commit=False,
    )
    append_arclink_event(
        conn,
        subject_kind="user",
        subject_id=clean_user_id,
        event_type="crew_recipe_applied",
        metadata=audit_metadata,
        commit=False,
    )
    conn.commit()

    from arclink_provisioning import project_arclink_deployment_identity_context

    projections: dict[str, Any] = {}
    for deployment in _deployment_rows(conn, clean_user_id):
        deployment_id = str(deployment.get("deployment_id") or "")
        projections[deployment_id] = project_arclink_deployment_identity_context(
            conn,
            deployment_id=deployment_id,
            source="crew_training",
        )
    recipe = current_crew_recipe(conn, user_id=clean_user_id)
    return {
        "recipe": recipe,
        "preview": preview,
        "identity_projection": projections,
    }


def whats_changed(conn: sqlite3.Connection, *, user_id: str) -> dict[str, Any]:
    current = current_crew_recipe(conn, user_id=user_id)
    if current is None:
        return {"status": "none", "summary": "No Crew Recipe is active yet.", "current": None, "prior": None, "changes": []}
    prior = prior_crew_recipe(conn, user_id=user_id)
    if prior is None:
        return {
            "status": "first_recipe",
            "summary": "This is the first active Crew Recipe.",
            "current": current,
            "prior": None,
            "changes": [],
        }
    changes: list[str] = []
    for key in ("preset", "capacity", "role", "mission", "treatment"):
        before = str(prior.get(key) or "")
        after = str(current.get(key) or "")
        if before != after:
            changes.append(f"{key}: {before} -> {after}")
    summary = "No Crew Recipe fields changed." if not changes else "; ".join(changes)
    return {"status": "changed", "summary": summary, "current": current, "prior": prior, "changes": changes}
