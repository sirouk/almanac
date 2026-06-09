#!/usr/bin/env python3
"""ArcLink Academy: Programs (Majors), Trainees, and the sticky Academy Mode.

The Academy is a *skill/mode experience*, not a one-shot role preview. Every
ArcPod Agent can enter Academy Mode (from a button or ``/academy``); the mode is
STICKY -- it stays open until the Captain ends it. While open, an LLM Trainer and
the Captain curate a specialist corpus/curriculum (that live curation is the
proof-gated work in ``arclink_academy_trainer`` + ``GAP-034``). When the Captain
ENDS the mode, the staged plan is committed ("everything put in its place") and
forward-maintenance (weekly continuing education) is armed.

This module owns the CONTROL-PLANE scaffolding for that experience -- the
browsable catalog of Programs/Majors (pure data so new trainee TYPES are rows,
not code), the Trainee records that bind a Major to an Agent, the sticky Mode
sessions, and the browse-graduates / adopt-graduate surfaces. It is intentionally
no-write with respect to Agent SOUL/skills/qmd/vault state: the real apply path is
gated behind ``PG-HERMES`` (see ``docs/arclink/academy-trainer.md``). Live source
acquisition and provider-driven curation stay gated behind ``PG-PROVIDER``.
"""
from __future__ import annotations

import json
import os
import hashlib
import secrets
import sqlite3
import urllib.error
import urllib.request
from typing import Any, Mapping, Sequence

from arclink_secrets_regex import redact_then_truncate


class ArcLinkAcademyProgramError(ValueError):
    pass


def _dumps(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True)
    except (TypeError, ValueError):
        return "null"


def _loads(text: Any, *, default: Any) -> Any:
    if isinstance(text, (dict, list)):
        return text
    if not isinstance(text, str) or not text.strip():
        return default
    try:
        loaded = json.loads(text)
    except (TypeError, ValueError):
        return default
    return loaded if isinstance(loaded, type(default)) else default


TRAINEE_STATUSES = ("enrolled", "in_academy", "graduated", "archived")
MODE_SESSION_STATUSES = ("open", "closed", "cancelled")
PROGRAM_DEPTHS = ("survey", "working", "deep")

# Real Agent SOUL/skills/qmd/vault writes are gated; this module never performs
# them. The commit at mode-end records intent + arms forward-maintenance.
ACADEMY_APPLY_PROOF_GATES = ("PG-PROVIDER", "PG-HERMES")
DEFAULT_ACADEMY_TRAINER_MODEL = "moonshotai/Kimi-K2.6-TEE"

# Cross-tenant central-corpus access/promotion gate. Within one ArcLink instance
# the redacted_public corpus is shared across the operator's captains and crew;
# a future cross-OPERATOR marketplace read/promotion is gated behind this.
ACADEMY_CROSS_TENANT_PROOF_GATE = "PG-CONSENT"

# Proposal statuses whose derived notes may feed a trainee corpus and be considered
# for central promotion. 'rejected' is excluded (Trainer/Captain declined it).
USABLE_PROPOSAL_STATUSES = ("proposed", "review_pending", "accepted", "deduped")
ACADEMY_RESOURCE_PROPOSAL_KINDS = ("add_resource", "discontinue_resource")

# Per-account guardrail against unbounded trainee growth (DoS / scheduler load).
DEFAULT_MAX_TRAINEES_PER_USER = 50
# Closed/cancelled mode sessions retained per trainee (open/cancel churn bound).
MODE_SESSION_RETENTION_PER_TRAINEE = 25
# Fields the cross-account graduate gallery may expose. Identity columns
# (user_id, deployment_id, agent_id), private Captain steer, and internal staging
# pointers are intentionally withheld from the browsable gallery.
_GRADUATE_CARD_FIELDS = (
    "trainee_id",
    "name",
    "status",
    "depth",
    "program_id",
    "program_label",
    "source_lanes",
    "forward_maintained",
    "graduated_at",
)


def _max_trainees_per_user() -> int:
    raw = str(os.environ.get("ARCLINK_ACADEMY_MAX_TRAINEES_PER_USER") or "").strip()
    try:
        n = int(raw)
    except ValueError:
        return DEFAULT_MAX_TRAINEES_PER_USER
    return n if n > 0 else DEFAULT_MAX_TRAINEES_PER_USER


def _enforce_trainee_quota(conn: sqlite3.Connection, user_id: str) -> None:
    cap = _max_trainees_per_user()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM academy_trainees WHERE user_id = ? AND status != 'archived'",
        (str(user_id or "").strip(),),
    ).fetchone()
    if row is not None and int(row["n"]) >= cap:
        raise ArcLinkAcademyProgramError(
            f"academy trainee limit reached for this account ({cap}); archive a trainee before enrolling another"
        )


def _ensure_deployment_owner_consistency(conn: sqlite3.Connection, *, user_id: str, deployment_id: str) -> None:
    """Fail closed when a real ArcPod deployment row belongs to another Captain.

    Some unit tests exercise the Academy helpers without seeding deployment rows;
    those fixture-only ids are allowed. In production/API/bot paths, deployment
    rows exist and this guard prevents a caller from binding Academy state to
    another Captain's Agent by passing a borrowed deployment id.
    """
    clean_user = str(user_id or "").strip()
    clean_deployment = str(deployment_id or "").strip()
    if not clean_user or not clean_deployment:
        raise ArcLinkAcademyProgramError("academy trainee requires user_id and deployment_id")
    try:
        row = conn.execute(
            "SELECT user_id FROM arclink_deployments WHERE deployment_id = ?",
            (clean_deployment,),
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    if row is not None and str(row["user_id"] or "").strip() != clean_user:
        raise ArcLinkAcademyProgramError("academy deployment is outside this account")


def academy_graduate_card(graduate: Mapping[str, Any]) -> dict[str, Any]:
    """Redacted, owner-safe projection for the browsable graduate gallery.

    Withholds tenant identity (user_id/deployment_id/agent_id), private Captain
    steer, and internal staging pointers so the gallery never discloses one
    account's data to another.
    """
    return {key: graduate.get(key) for key in _GRADUATE_CARD_FIELDS}


def _default_programs() -> tuple[dict[str, Any], ...]:
    """The seeded catalog of specialist Majors.

    Each references governed source lanes from
    ``arclink_academy_trainer.default_source_lane_registry``. New Majors are added
    as rows via :func:`upsert_academy_program`, not code.
    """
    return (
        {
            "program_id": "systems_practice_engineer",
            "label": "Systems-Practice Engineer",
            "summary": "Builds and operates real systems: architecture, tooling, tests, release habits, failure modes.",
            "topic_map": "architecture, workflows, tooling, testing, automation, release engineering, incident response, tradeoffs",
            "source_lanes": ["github_repository", "scholarly_standard", "skill_tool_catalog"],
            "role_template": (
                "You are a systems-practice engineer. Reason from how real maintained "
                "repositories and standards structure systems. Prefer brokered tools; cite "
                "Academy sources before specialized advice."
            ),
            "boundaries": "Do not copy licensed code into the vault; prefer explanatory lesson cards and citations.",
            "default_depth": "deep",
            "quality_floor": 72,
            "required_skills": ["retrieval-and-cite", "tool-choice"],
        },
        {
            "program_id": "research_analyst",
            "label": "Research Analyst",
            "summary": "Surveys literature and standards; separates durable doctrine from provisional findings.",
            "topic_map": "primary papers, surveys, benchmarks, standards, claims, methods, evidence, open problems",
            "source_lanes": ["scholarly_standard", "wikimedia", "web_article"],
            "role_template": (
                "You are a research analyst. Map a domain, cite primary and survey sources, and "
                "flag speculative or contradicted findings rather than presenting them as truth."
            ),
            "boundaries": "Mark provisional research as provisional; never present early results as production doctrine.",
            "default_depth": "deep",
            "quality_floor": 75,
            "required_skills": ["retrieval-and-cite"],
        },
        {
            "program_id": "community_insight_specialist",
            "label": "Community Insight Specialist",
            "summary": "Reads practitioner discussion for vocabulary, recurring pain, edge cases, and field-tested patterns.",
            "topic_map": "practitioner vocabulary, recurring pain, edge cases, tool comparisons, common workflows, failure modes",
            "source_lanes": ["reddit_discussion", "web_article"],
            "role_template": (
                "You are a community insight specialist. Extract hypotheses, failure modes, and "
                "practical language from practitioner discussion. Never quote or expose private user details."
            ),
            "boundaries": "Never treat upvotes as truth; never expose private user identities; comply with deletion/tombstone policy.",
            "default_depth": "working",
            "quality_floor": 68,
            "required_skills": ["retrieval-and-cite"],
        },
        {
            "program_id": "standards_compliance_reader",
            "label": "Standards & Compliance Reader",
            "summary": "Tracks standards, official guidance, and organization policy for compliant decisions.",
            "topic_map": "standards bodies, official guidance, regulatory posture, org policy, change history",
            "source_lanes": ["scholarly_standard", "wikimedia", "organization_private"],
            "role_template": (
                "You are a standards and compliance reader. Ground guidance in standards and official "
                "documents, cite the controlling source, and flag where policy is ambiguous."
            ),
            "boundaries": "Do not store private/secret organization data in reusable corpora; scrub before lesson cards.",
            "default_depth": "working",
            "quality_floor": 74,
            "required_skills": ["retrieval-and-cite"],
        },
        {
            "program_id": "domain_tutor",
            "label": "Domain Tutor",
            "summary": "Teaches a domain from lectures, talks, and overviews with a beginner-to-expert ladder.",
            "topic_map": "core concepts, vocabulary, demonstrations, heuristics, mistakes-to-avoid, follow-up resources",
            "source_lanes": ["video_transcript", "wikimedia", "web_article"],
            "role_template": (
                "You are a domain tutor. Build a beginner-to-expert ladder, use demonstrations and "
                "heuristics, and point to where to look next. Cite Academy sources before advising."
            ),
            "boundaries": "Only use lawfully acquired transcripts; label machine-transcribed material as such.",
            "default_depth": "survey",
            "quality_floor": 66,
            "required_skills": ["retrieval-and-cite"],
        },
    )


def seed_default_academy_programs(conn: sqlite3.Connection) -> int:
    """Idempotently upsert the default Majors catalog. Returns the catalog size.

    Fast-path: if every default Major is already present *and current*, this is
    a single read (no writes/commits), so calling it on hot read paths does not
    amplify writes against the single-writer control DB. If a future ArcLink
    release changes a seeded Major's definition, the drift is repaired.
    """
    defaults = _default_programs()
    placeholders = ",".join("?" for _ in defaults)
    rows = conn.execute(
        f"SELECT * FROM academy_programs WHERE program_id IN ({placeholders})",
        tuple(str(p["program_id"]) for p in defaults),
    ).fetchall()
    current_by_id = {str(row["program_id"]): row for row in rows}
    if len(current_by_id) >= len(defaults) and all(
        _program_row_matches_default(current_by_id.get(str(program["program_id"])), program)
        for program in defaults
    ):
        return len(defaults)
    count = 0
    for program in defaults:
        upsert_academy_program(conn, origin="catalog", commit=False, **program)
        count += 1
    conn.commit()
    return count


def _program_row_matches_default(row: sqlite3.Row | None, program: Mapping[str, Any]) -> bool:
    if row is None:
        return False
    lanes = _validate_source_lanes(program.get("source_lanes") or ())
    skills = [str(s).strip() for s in (program.get("required_skills") or ()) if str(s).strip()]
    try:
        quality_floor = _clean_quality_floor(program.get("quality_floor", 70))
    except ArcLinkAcademyProgramError:
        return False
    return (
        str(row["program_id"] or "") == _slug(str(program.get("program_id") or ""))
        and str(row["label"] or "") == str(program.get("label") or "").strip()
        and str(row["summary"] or "") == str(program.get("summary") or "").strip()
        and str(row["topic_map"] or "") == str(program.get("topic_map") or "").strip()
        and str(row["source_lanes_json"] or "") == _dumps(lanes)
        and str(row["role_template"] or "") == str(program.get("role_template") or "").strip()
        and str(row["boundaries"] or "") == str(program.get("boundaries") or "").strip()
        and str(row["default_depth"] or "") == str(program.get("default_depth") or "working").strip().lower()
        and int(row["quality_floor"]) == quality_floor
        and str(row["required_skills_json"] or "") == _dumps(skills)
    )


def _clean_quality_floor(value: Any) -> int:
    try:
        floor = int(value)
    except (TypeError, ValueError) as exc:
        raise ArcLinkAcademyProgramError("academy quality_floor must be an integer") from exc
    return max(0, min(100, floor))


def upsert_academy_program(
    conn: sqlite3.Connection,
    *,
    program_id: str,
    label: str,
    summary: str = "",
    topic_map: str = "",
    source_lanes: Sequence[str] | None = None,
    role_template: str = "",
    boundaries: str = "",
    default_depth: str = "working",
    quality_floor: int = 70,
    required_skills: Sequence[str] | None = None,
    origin: str = "custom",
    commit: bool = True,
) -> dict[str, Any]:
    """Create or update a Major. New trainee TYPES are added with this, as data."""
    from arclink_boundary import reject_secret_material

    clean_id = _slug(program_id)
    if not clean_id:
        raise ArcLinkAcademyProgramError("academy program_id is required")
    clean_label = str(label or "").strip()
    if not clean_label:
        raise ArcLinkAcademyProgramError("academy program label is required")
    depth = str(default_depth or "working").strip().lower()
    if depth not in PROGRAM_DEPTHS:
        raise ArcLinkAcademyProgramError(f"unsupported academy depth: {depth}")
    lanes = _validate_source_lanes(source_lanes or ())
    skills = [str(s).strip() for s in (required_skills or ()) if str(s).strip()]
    reject_secret_material(
        {
            "label": clean_label,
            "summary": summary,
            "topic_map": topic_map,
            "role_template": role_template,
            "boundaries": boundaries,
        }
    )
    now = _now()
    existing = get_academy_program(conn, clean_id)
    created_at = str(existing.get("created_at")) if existing else now
    conn.execute(
        """
        INSERT INTO academy_programs (
          program_id, label, summary, topic_map, source_lanes_json, role_template,
          boundaries, default_depth, quality_floor, required_skills_json, origin,
          status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
        ON CONFLICT(program_id) DO UPDATE SET
          label = excluded.label,
          summary = excluded.summary,
          topic_map = excluded.topic_map,
          source_lanes_json = excluded.source_lanes_json,
          role_template = excluded.role_template,
          boundaries = excluded.boundaries,
          default_depth = excluded.default_depth,
          quality_floor = excluded.quality_floor,
          required_skills_json = excluded.required_skills_json,
          updated_at = excluded.updated_at
        """,
        (
            clean_id,
            clean_label,
            str(summary or "").strip(),
            str(topic_map or "").strip(),
            _dumps(lanes),
            str(role_template or "").strip(),
            str(boundaries or "").strip(),
            depth,
            _clean_quality_floor(quality_floor),
            _dumps(skills),
            str(origin or "custom").strip() or "custom",
            created_at,
            now,
        ),
    )
    if commit:
        conn.commit()
    return get_academy_program(conn, clean_id) or {}


def get_academy_program(conn: sqlite3.Connection, program_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM academy_programs WHERE program_id = ?",
        (_slug(program_id),),
    ).fetchone()
    return _program_public(row) if row is not None else None


def list_academy_programs(conn: sqlite3.Connection, *, include_archived: bool = False) -> list[dict[str, Any]]:
    """Browse the catalog of Majors."""
    if include_archived:
        rows = conn.execute("SELECT * FROM academy_programs ORDER BY label").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM academy_programs WHERE status = 'active' ORDER BY label"
        ).fetchall()
    return [_program_public(row) for row in rows]


def enroll_academy_trainee(
    conn: sqlite3.Connection,
    *,
    program_id: str,
    user_id: str,
    deployment_id: str,
    agent_id: str = "",
    name: str = "",
    depth: str = "",
    captain_steer: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Enroll a new Trainee: bind a Major to an Agent (deployment) + Captain steer."""
    from arclink_boundary import reject_secret_material

    program = get_academy_program(conn, program_id)
    if program is None or program.get("status") != "active":
        raise ArcLinkAcademyProgramError(f"unknown or archived academy program: {program_id}")
    clean_user = str(user_id or "").strip()
    clean_deployment = str(deployment_id or "").strip()
    if not clean_user or not clean_deployment:
        raise ArcLinkAcademyProgramError("academy trainee requires user_id and deployment_id")
    _ensure_deployment_owner_consistency(conn, user_id=clean_user, deployment_id=clean_deployment)
    _enforce_trainee_quota(conn, clean_user)
    clean_depth = str(depth or "").strip().lower() or str(program.get("default_depth") or "working")
    if clean_depth not in PROGRAM_DEPTHS:
        raise ArcLinkAcademyProgramError(f"unsupported academy depth: {clean_depth}")
    steer = dict(captain_steer or {})
    reject_secret_material({"name": name, **{f"steer.{k}": v for k, v in steer.items()}})
    trainee_id = "atrn_" + secrets.token_hex(8)
    now = _now()
    conn.execute(
        """
        INSERT INTO academy_trainees (
          trainee_id, program_id, user_id, deployment_id, agent_id, name, status,
          mode_open, depth, captain_steer_json, enrolled_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'enrolled', 0, ?, ?, ?, ?, ?)
        """,
        (
            trainee_id,
            program["program_id"],
            clean_user,
            clean_deployment,
            str(agent_id or "").strip(),
            str(name or "").strip() or str(program.get("label") or program["program_id"]),
            clean_depth,
            _dumps(steer),
            now,
            now,
            now,
        ),
    )
    conn.commit()
    # Cross-captain reuse: if a shared central specialist already exists for this
    # Major, subscribe the new trainee so it inherits the deduped shared corpus.
    try:
        subscribe_trainee_to_specialist(conn, trainee_id=trainee_id, commit=True)
    except Exception:  # noqa: BLE001 - inheritance is best-effort; enrollment must not fail on it
        pass
    return get_academy_trainee(conn, trainee_id) or {}


def get_academy_trainee(conn: sqlite3.Connection, trainee_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM academy_trainees WHERE trainee_id = ?",
        (str(trainee_id or "").strip(),),
    ).fetchone()
    return _trainee_public(row) if row is not None else None


def list_academy_trainees(
    conn: sqlite3.Connection,
    *,
    user_id: str | None = None,
    deployment_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(str(user_id).strip())
    if deployment_id is not None:
        clauses.append("deployment_id = ?")
        params.append(str(deployment_id).strip())
    if status is not None:
        clauses.append("status = ?")
        params.append(str(status).strip())
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM academy_trainees{where} ORDER BY created_at DESC",
        tuple(params),
    ).fetchall()
    return [_trainee_public(row) for row in rows]


def open_academy_mode(
    conn: sqlite3.Connection,
    *,
    trainee_id: str,
    opened_by: str,
    opened_via: str = "command",
) -> dict[str, Any]:
    """Enter the sticky Academy Mode for a trainee.

    Idempotent: if a session is already open for the trainee, the existing open
    session is returned (the mode stays open until the Captain ends it).
    """
    from arclink_boundary import reject_secret_material

    clean_via = str(opened_via or "command").strip() or "command"
    reject_secret_material({"opened_via": clean_via})
    trainee = get_academy_trainee(conn, trainee_id)
    if trainee is None:
        raise ArcLinkAcademyProgramError(f"unknown academy trainee: {trainee_id}")
    if trainee.get("status") == "archived":
        raise ArcLinkAcademyProgramError("cannot open Academy Mode for an archived trainee")
    existing = get_open_academy_mode(conn, trainee_id=trainee["trainee_id"])
    if existing is not None:
        return {"session": existing, "trainee": trainee, "created": False}
    session_id = "asess_" + secrets.token_hex(8)
    now = _now()
    try:
        conn.execute(
            """
            INSERT INTO academy_mode_sessions (
              session_id, trainee_id, deployment_id, program_id, opened_by, opened_via,
              status, opened_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'open', ?)
            """,
            (
                session_id,
                trainee["trainee_id"],
                str(trainee.get("deployment_id") or ""),
                str(trainee.get("program_id") or ""),
                str(opened_by or "").strip() or "captain",
                clean_via,
                now,
            ),
        )
    except sqlite3.IntegrityError:
        # The partial unique index (one open session per trainee) lost a race with
        # a concurrent open. Fail SAFE and idempotently: return the winner's session.
        conn.rollback()
        winner = get_open_academy_mode(conn, trainee_id=trainee["trainee_id"])
        if winner is not None:
            return {"session": winner, "trainee": trainee, "created": False}
        raise
    conn.execute(
        "UPDATE academy_trainees SET status = 'in_academy', mode_open = 1, updated_at = ? WHERE trainee_id = ?",
        (now, trainee["trainee_id"]),
    )
    conn.commit()
    return {
        "session": _session_public(conn.execute(
            "SELECT * FROM academy_mode_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()),
        "trainee": get_academy_trainee(conn, trainee["trainee_id"]),
        "created": True,
    }


def get_open_academy_mode(
    conn: sqlite3.Connection,
    *,
    trainee_id: str | None = None,
    deployment_id: str | None = None,
) -> dict[str, Any] | None:
    if trainee_id:
        row = conn.execute(
            "SELECT * FROM academy_mode_sessions WHERE trainee_id = ? AND status = 'open' ORDER BY opened_at DESC LIMIT 1",
            (str(trainee_id).strip(),),
        ).fetchone()
    elif deployment_id:
        row = conn.execute(
            "SELECT * FROM academy_mode_sessions WHERE deployment_id = ? AND status = 'open' ORDER BY opened_at DESC LIMIT 1",
            (str(deployment_id).strip(),),
        ).fetchone()
    else:
        return None
    return _session_public(row) if row is not None else None


def academy_mode_status(conn: sqlite3.Connection, *, trainee_id: str) -> dict[str, Any]:
    """Read model for surfaces: trainee + open session + program summary."""
    trainee = get_academy_trainee(conn, trainee_id)
    if trainee is None:
        return {"trainee": None, "mode_open": False, "session": None, "program": None}
    session = get_open_academy_mode(conn, trainee_id=trainee["trainee_id"])
    program = get_academy_program(conn, str(trainee.get("program_id") or ""))
    return {
        "trainee": trainee,
        "mode_open": bool(trainee.get("mode_open")),
        "session": session,
        "program": program,
    }


def update_academy_trainee_steer(
    conn: sqlite3.Connection,
    *,
    trainee_id: str,
    updates: Mapping[str, Any] | None = None,
    append_note: str = "",
    actor: str = "",
    commit: bool = True,
) -> dict[str, Any]:
    """Merge Captain steering into a Trainee while Academy Mode is open.

    Raven uses this during the turn-by-turn Academy bootstrap and while the
    sticky mode is active. It is intentionally control-plane-only: the Agent's
    SOUL, skills, qmd, vault, and workspace are still mutated only through the
    proof-gated apply path.
    """
    from arclink_boundary import reject_secret_material

    trainee = get_academy_trainee(conn, trainee_id)
    if trainee is None:
        raise ArcLinkAcademyProgramError(f"unknown academy trainee: {trainee_id}")
    if trainee.get("status") == "archived":
        raise ArcLinkAcademyProgramError("cannot update Academy steer for an archived trainee")
    if get_open_academy_mode(conn, trainee_id=str(trainee["trainee_id"])) is None:
        raise ArcLinkAcademyProgramError("Academy steering updates require an open Academy Mode")
    merged = dict(trainee.get("captain_steer") or {})
    clean_updates = dict(updates or {})
    note = str(append_note or "").strip()
    reject_secret_material(
        {
            **{f"steer.{key}": value for key, value in clean_updates.items()},
            "note": note,
            "actor": actor,
        }
    )
    for key, value in clean_updates.items():
        clean_key = _slug(str(key or ""))[:64]
        if not clean_key:
            continue
        if isinstance(value, (list, tuple)):
            cleaned = [str(item or "").strip()[:500] for item in value if str(item or "").strip()]
            merged[clean_key] = cleaned[:20]
        elif isinstance(value, Mapping):
            merged[clean_key] = {
                _slug(str(k or ""))[:64]: str(v or "").strip()[:500]
                for k, v in list(value.items())[:20]
                if _slug(str(k or ""))
            }
        else:
            merged[clean_key] = str(value or "").strip()[:2000]
    if note:
        notes = merged.get("captain_notes")
        if not isinstance(notes, list):
            notes = []
        notes.append(
            {
                "at": _now(),
                "actor": str(actor or "").strip()[:120] or "captain",
                "note": note[:2000],
            }
        )
        merged["captain_notes"] = notes[-50:]
    conn.execute(
        "UPDATE academy_trainees SET captain_steer_json = ?, updated_at = ? WHERE trainee_id = ?",
        (_dumps(merged), _now(), trainee["trainee_id"]),
    )
    if commit:
        conn.commit()
    return get_academy_trainee(conn, trainee["trainee_id"]) or {}


def active_academy_mode_for_deployment(conn: sqlite3.Connection, *, deployment_id: str) -> dict[str, Any] | None:
    """Return the open Academy Mode for one deployment, with trainee/program."""
    clean_deployment = str(deployment_id or "").strip()
    if not clean_deployment:
        return None
    session = get_open_academy_mode(conn, deployment_id=clean_deployment)
    if session is None:
        return None
    trainee = get_academy_trainee(conn, str(session.get("trainee_id") or ""))
    if trainee is None:
        return None
    return {
        "session": session,
        "trainee": trainee,
        "program": get_academy_program(conn, str(trainee.get("program_id") or "")),
    }


def record_academy_resource_proposal(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    title: str,
    origin_url: str,
    lane_id: str,
    summary: str,
    relevance: Mapping[str, Any] | None = None,
    citations: Sequence[str] | None = None,
    proposed_by: str = "",
    proposal_kind: str = "add_resource",
    target_source_uid: str = "",
    commit: bool = True,
) -> dict[str, Any]:
    """Record an Agent-proposed Academy source action for Trainer review.

    This is the central handoff from the Hermes Agent skill back into ArcLink:
    the Agent may gather and compress candidate resources or flag a shared
    resource as a dead end, but it submits only source metadata, citations, and
    concise derived notes/reasons. The Academy Trainer review/weekly refresh
    loop can then dedupe, promote, or queue the source for stronger discontinuation
    review without letting raw crawled content leak into reusable corpora.
    """
    from arclink_boundary import reject_secret_material

    active = active_academy_mode_for_deployment(conn, deployment_id=deployment_id)
    if active is None:
        raise ArcLinkAcademyProgramError("academy resource proposals require an open Academy Mode for this deployment")
    trainee = active["trainee"]
    session = active["session"]
    clean_kind = _clean_proposal_kind(proposal_kind)
    clean_lane = str(lane_id or "").strip()
    if not clean_lane:
        raise ArcLinkAcademyProgramError("academy resource proposal requires a source lane")
    _validate_source_lanes([clean_lane])
    clean_title = str(title or "").strip()[:240]
    clean_url = str(origin_url or "").strip()[:1000]
    clean_target_source = str(target_source_uid or "").strip()[:120]
    clean_target_canonical = _canonical_url(clean_url)
    clean_summary = str(summary or "").strip()[:4000]
    clean_citations = [str(item or "").strip()[:1000] for item in (citations or []) if str(item or "").strip()][:20]
    clean_relevance = {
        _slug(str(k or ""))[:64]: str(v or "").strip()[:1000]
        for k, v in list(dict(relevance or {}).items())[:25]
        if _slug(str(k or ""))
    }
    reject_secret_material(
        {
            "title": clean_title,
            "origin_url": clean_url,
            "summary": clean_summary,
            "lane_id": clean_lane,
            "proposal_kind": clean_kind,
            "target_source_uid": clean_target_source,
            "proposed_by": proposed_by,
            **{f"citation.{idx}": value for idx, value in enumerate(clean_citations)},
            **{f"relevance.{key}": value for key, value in clean_relevance.items()},
        }
    )
    if not clean_title:
        raise ArcLinkAcademyProgramError("academy resource proposal requires title")
    if not clean_url and not clean_summary:
        raise ArcLinkAcademyProgramError("academy resource proposal requires origin_url or summary")
    if clean_kind == "discontinue_resource" and not (clean_url or clean_target_source):
        raise ArcLinkAcademyProgramError("academy discontinue proposal requires origin_url or target_source_uid")
    dedupe_seed = f"{trainee['trainee_id']}|{clean_kind}|{clean_url or clean_target_source or clean_title.lower()}"
    proposal_id = "aprop_" + hashlib.sha256(dedupe_seed.encode("utf-8")).hexdigest()[:16]
    now = _now()
    status = "review_pending"
    existing = None
    if clean_url:
        existing = conn.execute(
            "SELECT * FROM academy_resource_proposals WHERE trainee_id = ? AND proposal_kind = ? AND origin_url = ?",
            (str(trainee["trainee_id"]), clean_kind, clean_url),
        ).fetchone()
    if existing is None:
        existing = conn.execute("SELECT * FROM academy_resource_proposals WHERE proposal_id = ?", (proposal_id,)).fetchone()
    if existing is not None:
        conn.execute(
            """
            UPDATE academy_resource_proposals
            SET session_id = ?, lane_id = ?, proposal_kind = ?, target_source_uid = ?,
                target_canonical_url = ?, title = ?, origin_url = ?, summary = ?,
                relevance_json = ?, citations_json = ?, proposed_by = ?,
                status = 'deduped', updated_at = ?
            WHERE proposal_id = ?
            """,
            (
                str(session.get("session_id") or ""),
                clean_lane,
                clean_kind,
                clean_target_source,
                clean_target_canonical,
                clean_title,
                clean_url,
                clean_summary,
                _dumps(clean_relevance),
                _dumps(clean_citations),
                str(proposed_by or "").strip()[:160],
                now,
                str(existing["proposal_id"]),
            ),
        )
        if commit:
            conn.commit()
        row = conn.execute("SELECT * FROM academy_resource_proposals WHERE proposal_id = ?", (str(existing["proposal_id"]),)).fetchone()
        return _proposal_public(row) if row is not None else {}
    conn.execute(
        """
        INSERT INTO academy_resource_proposals (
          proposal_id, trainee_id, session_id, user_id, deployment_id, program_id,
          lane_id, proposal_kind, target_source_uid, target_canonical_url,
          title, origin_url, summary, relevance_json, citations_json,
          proposed_by, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            proposal_id,
            str(trainee["trainee_id"]),
            str(session.get("session_id") or ""),
            str(trainee.get("user_id") or ""),
            str(trainee.get("deployment_id") or ""),
            str(trainee.get("program_id") or ""),
            clean_lane,
            clean_kind,
            clean_target_source,
            clean_target_canonical,
            clean_title,
            clean_url,
            clean_summary,
            _dumps(clean_relevance),
            _dumps(clean_citations),
            str(proposed_by or "").strip()[:160],
            status,
            now,
            now,
        ),
    )
    if commit:
        conn.commit()
    row = conn.execute("SELECT * FROM academy_resource_proposals WHERE proposal_id = ?", (proposal_id,)).fetchone()
    return _proposal_public(row) if row is not None else {}


def read_academy_proposals(
    conn: sqlite3.Connection,
    *,
    trainee_id: str,
    statuses: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Read a trainee's proposed resources, ordered deterministically.

    This is the read-back the corpus builder and Captain surfaces use; without it
    ``academy_resource_proposals`` was write-only. Order is stable
    (``created_at`` then ``proposal_id``) so a recomputed corpus manifest id is
    deterministic for the same proposal set.
    """
    clean_id = str(trainee_id or "").strip()
    if not clean_id:
        return []
    params: list[Any] = [clean_id]
    where = "trainee_id = ?"
    status_list = [str(s).strip() for s in (statuses or ()) if str(s).strip()]
    if status_list:
        where += " AND status IN (%s)" % ",".join("?" for _ in status_list)
        params.extend(status_list)
    rows = conn.execute(
        f"SELECT * FROM academy_resource_proposals WHERE {where} ORDER BY created_at, proposal_id",
        tuple(params),
    ).fetchall()
    return [_proposal_public(row) for row in rows]


def _trainee_has_real_training_sources(conn: sqlite3.Connection, trainee: Mapping[str, Any]) -> bool:
    proposals = read_academy_proposals(conn, trainee_id=str(trainee["trainee_id"]), statuses=USABLE_PROPOSAL_STATUSES)
    if any(_proposal_kind(proposal) == "add_resource" for proposal in proposals):
        return True
    if read_central_specialist_sources(conn, trainee_id=str(trainee["trainee_id"])):
        return True
    program = get_academy_program(conn, str(trainee.get("program_id") or ""))
    if program is None:
        return False
    specialist_uid, _topic_fp = specialist_uid_for_program(program)
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM academy_sources src
        JOIN academy_specialist_sources link ON link.source_uid = src.source_uid
        WHERE link.specialist_uid = ?
          AND src.status = 'active'
          AND src.share_scope = 'redacted_public'
        """,
        (specialist_uid,),
    ).fetchone()
    return int(row["n"] if row is not None else 0) > 0


def end_academy_mode(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    actor: str,
    graduate: bool = True,
    staged_manifest_id: str = "",
    staged_plan_id: str = "",
    commit_summary: Mapping[str, Any] | None = None,
    trainer_client: Any | None = None,
    live_trainer_authorized: bool | None = None,
) -> dict[str, Any]:
    """End the sticky mode at the Captain's request.

    On graduate=True this is the "everything put in its place" moment: the staged
    plan reference is recorded, the trainee is marked graduated, and weekly
    forward-maintenance is armed. Real Agent SOUL/skills/qmd/vault writes remain
    gated behind PG-HERMES and are NOT performed here.
    """
    from arclink_boundary import reject_secret_material

    row = conn.execute(
        "SELECT * FROM academy_mode_sessions WHERE session_id = ?",
        (str(session_id or "").strip(),),
    ).fetchone()
    if row is None:
        raise ArcLinkAcademyProgramError(f"unknown academy mode session: {session_id}")
    session = _session_public(row)
    if session.get("status") != "open":
        raise ArcLinkAcademyProgramError("academy mode session is not open")
    trainee = get_academy_trainee(conn, str(session.get("trainee_id") or ""))
    if trainee is None:
        raise ArcLinkAcademyProgramError("academy mode session has no trainee")
    summary = dict(commit_summary or {})
    reject_secret_material({f"commit.{k}": v for k, v in summary.items()})
    final_status = "closed" if graduate else "cancelled"
    now = _now()
    resolved_manifest = str(staged_manifest_id or trainee.get("staged_manifest_id") or "").strip()
    resolved_plan = str(staged_plan_id or trainee.get("staged_plan_id") or "").strip()
    live_trainer = (
        academy_trainer_live_authorized_from_env()
        if live_trainer_authorized is None
        else bool(live_trainer_authorized)
    )
    # On graduation the Trainer promotes the trainee's public-lane, public-safe
    # proposals into the CENTRAL deduplicated shared corpus (opt-out sharing) and
    # subscribes the trainee to its specialist. No Agent write happens here.
    if graduate:
        if not _trainee_has_real_training_sources(conn, trainee):
            summary.setdefault("graduated", False)
            summary.setdefault("resource_proposal_count", 0)
            summary.setdefault("trainer_deep_dive_status", "needs_training_sources")
            summary.setdefault("canon_status", "blocked_until_real_training_sources")
            summary.setdefault("agent_write_status", "blocked_until_real_training_sources")
            summary.setdefault("apply_status", "blocked_until_real_training_sources")
            summary.setdefault("forward_maintenance", "not armed")
            summary.setdefault(
                "apply_note",
                "Academy Mode remains open: gather at least one governed real source or adopt a shared Academy specialist before graduation.",
            )
            summary.setdefault("actor", str(actor or "").strip() or "captain")
            conn.execute(
                "UPDATE academy_mode_sessions SET commit_summary_json = ? WHERE session_id = ?",
                (_dumps(summary), session["session_id"]),
            )
            conn.execute(
                "UPDATE academy_trainees SET status = 'in_academy', mode_open = 1, forward_maintained = 0, updated_at = ? WHERE trainee_id = ?",
                (now, trainee["trainee_id"]),
            )
            conn.commit()
            open_row = conn.execute(
                "SELECT * FROM academy_mode_sessions WHERE session_id = ?", (session["session_id"],)
            ).fetchone()
            return {
                "session": _session_public(open_row) if open_row is not None else session,
                "trainee": get_academy_trainee(conn, trainee["trainee_id"]),
                "graduated": False,
                "status": "needs_training_sources",
                "mutation_performed": False,
                "workspace_mutation_performed": False,
            }
        try:
            promotion = promote_proposals_to_central(conn, trainee_id=trainee["trainee_id"], actor=str(actor or ""), commit=False)
            specialist_uid = str(promotion.get("specialist_uid") or "")
            summary.setdefault("central_specialist_uid", specialist_uid)
            summary.setdefault("central_sources_promoted", int(promotion.get("promoted_count") or 0))
            summary.setdefault("central_sources_deduped", int(promotion.get("deduped_count") or 0))
            summary.setdefault("central_sources_discontinued", int(promotion.get("discontinued_count") or 0))
            summary.setdefault("central_source_discontinue_reviews", int(promotion.get("discontinue_review_pending_count") or 0))
            summary.setdefault("central_sources_skipped", int(promotion.get("skipped_count") or 0))
            summary.setdefault("central_share_scope", str(promotion.get("share_scope") or ""))
            summary.setdefault("central_capsule_version", int(promotion.get("capsule_version") or 0))
            # Trainer deep dive over the (now central) corpus. Deterministic by
            # default; the live LLM Trainer routes through the central ArcLink LLM
            # router only when PG-PROVIDER is explicitly authorized.
            if specialist_uid:
                trainer_result = run_academy_trainer_review(
                    conn,
                    specialist_uid=specialist_uid,
                    client=trainer_client,
                    live_authorized=live_trainer,
                    actor=str(actor or ""),
                    commit=False,
                )
                summary.setdefault("central_trainer_reviewed", True)
                summary.setdefault("central_trainer_engine", str(trainer_result.get("engine") or ""))
                summary.setdefault("central_trainer_live_status", str(trainer_result.get("live_enrichment_status") or ""))
        except Exception as exc:  # noqa: BLE001 - promotion/review must not crash graduation
            from arclink_secrets_regex import redact_then_truncate

            summary.setdefault("central_promotion_error", redact_then_truncate(str(exc), limit=200))
    # On graduation, curate the specialist corpus + staged application plan after
    # central promotion/trainer review, so the staged contract and later apply
    # recomputation use the same canonical source graph. This is no-write w.r.t.
    # the Agent; the real apply is the PG-HERMES gated academy_apply action.
    if graduate and not resolved_plan and not resolved_manifest:
        try:
            # commit=False: staging + session-close + graduation are one atomic txn.
            curated = curate_academy_trainee(conn, trainee_id=trainee["trainee_id"], created_at=now, commit=False)
            resolved_manifest = str(curated.get("manifest_id") or resolved_manifest)
            resolved_plan = str(curated.get("plan_id") or resolved_plan)
            review = curated.get("review") if isinstance(curated.get("review"), Mapping) else {}
            summary.setdefault("review_status", str(review.get("status") or ""))
            summary.setdefault("source_count", int(curated.get("source_count") or 0))
        except Exception as exc:  # noqa: BLE001 - mode end must not crash on curation
            from arclink_secrets_regex import redact_then_truncate

            summary.setdefault("curation_error", redact_then_truncate(str(exc), limit=200))
    summary.setdefault("graduated", bool(graduate))
    summary.setdefault("manifest_id", resolved_manifest)
    proposal_count = 0
    if graduate:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM academy_resource_proposals WHERE trainee_id = ?",
            (trainee["trainee_id"],),
        ).fetchone()
        proposal_count = int(row["n"] if row is not None else 0)
    summary.setdefault("resource_proposal_count", proposal_count)
    summary.setdefault("trainer_deep_dive_status", "queued_for_review" if graduate else "cancelled")
    summary.setdefault("canon_status", "not_canon_until_trainer_deep_dive_and_apply" if graduate else "cancelled")
    summary.setdefault("agent_write_status", "blocked_until_trainer_review_and_pg_hermes" if graduate else "cancelled")
    summary.setdefault("apply_status", "deep_dive_queued" if graduate else "cancelled")
    summary.setdefault("apply_proof_gates", list(ACADEMY_APPLY_PROOF_GATES))
    summary.setdefault(
        "apply_note",
        "Captain closed Academy Mode; Trainer deep dive must review/dedupe resources before canonical SOUL/skills/qmd/vault writes.",
    )
    summary.setdefault("forward_maintenance", "weekly continuing education armed" if graduate else "not armed")
    summary.setdefault("actor", str(actor or "").strip() or "captain")
    conn.execute(
        "UPDATE academy_mode_sessions SET status = ?, commit_summary_json = ?, closed_at = ? WHERE session_id = ?",
        (final_status, _dumps(summary), now, session["session_id"]),
    )
    if graduate:
        conn.execute(
            """
            UPDATE academy_trainees
            SET status = 'graduated', mode_open = 0, forward_maintained = 1,
                staged_manifest_id = ?, staged_plan_id = ?, graduated_at = ?, updated_at = ?
            WHERE trainee_id = ?
            """,
            (resolved_manifest, resolved_plan, now, now, trainee["trainee_id"]),
        )
    else:
        conn.execute(
            "UPDATE academy_trainees SET status = 'enrolled', mode_open = 0, updated_at = ? WHERE trainee_id = ?",
            (now, trainee["trainee_id"]),
        )
    # Read the closed session for the response BEFORE pruning, so retention can
    # never race-delete the row we are about to return.
    closed_row = conn.execute(
        "SELECT * FROM academy_mode_sessions WHERE session_id = ?", (session["session_id"],)
    ).fetchone()
    closed_session = _session_public(closed_row) if closed_row is not None else session
    _prune_mode_sessions(conn, trainee["trainee_id"], keep_session_id=session["session_id"])
    conn.commit()
    return {
        "session": closed_session,
        "trainee": get_academy_trainee(conn, trainee["trainee_id"]),
        "graduated": bool(graduate),
        "mutation_performed": False,
        "workspace_mutation_performed": False,
    }


def _prune_mode_sessions(conn: sqlite3.Connection, trainee_id: str, *, keep_session_id: str = "") -> None:
    """Bound closed/cancelled mode-session growth from open/cancel churn.

    Keeps the most recent MODE_SESSION_RETENTION_PER_TRAINEE non-open sessions per
    trainee (open sessions are never pruned), and never prunes ``keep_session_id``
    (the session the caller is finalizing). Runs inside the caller's transaction.
    """
    # Order by rowid (monotonic insertion order) so the most recently finalized
    # session is always retained regardless of equal timestamps.
    conn.execute(
        """
        DELETE FROM academy_mode_sessions
        WHERE trainee_id = ? AND status != 'open' AND session_id != ? AND rowid NOT IN (
            SELECT rowid FROM academy_mode_sessions
            WHERE trainee_id = ? AND status != 'open'
            ORDER BY rowid DESC
            LIMIT ?
        )
        """,
        (str(trainee_id), str(keep_session_id or ""), str(trainee_id), MODE_SESSION_RETENTION_PER_TRAINEE),
    )


def browse_academy_graduates(conn: sqlite3.Connection, *, user_id: str | None = None) -> dict[str, Any]:
    """The gallery: graduated Trainees (ready specialists) plus the Major catalog."""
    graduates = list_academy_trainees(conn, user_id=user_id, status="graduated")
    programs = list_academy_programs(conn)
    program_by_id = {p["program_id"]: p for p in programs}
    enriched = []
    for grad in graduates:
        program = program_by_id.get(str(grad.get("program_id") or ""))
        enriched.append({
            **grad,
            "program_label": (program or {}).get("label") or grad.get("program_id"),
            "source_lanes": (program or {}).get("source_lanes") or [],
        })
    return {"graduates": enriched, "programs": programs}


def adopt_academy_graduate(
    conn: sqlite3.Connection,
    *,
    source_trainee_id: str,
    user_id: str,
    deployment_id: str,
    agent_id: str = "",
    name: str = "",
) -> dict[str, Any]:
    """Fast path: clone a graduate's Major + staged corpus into a new graduated Trainee.

    The source graduate must belong to the target user. A future cross-tenant
    marketplace/adoption path should be a separate consented helper with a
    redacted public card, not this private-corpus clone.
    """
    from arclink_boundary import reject_secret_material

    reject_secret_material({"name": name})
    source = get_academy_trainee(conn, source_trainee_id)
    if source is None or source.get("status") != "graduated":
        raise ArcLinkAcademyProgramError("can only adopt a graduated academy trainee")
    clean_user = str(user_id or "").strip()
    clean_deployment = str(deployment_id or "").strip()
    if not clean_user or not clean_deployment:
        raise ArcLinkAcademyProgramError("adopt requires user_id and deployment_id")
    if str(source.get("user_id") or "") != clean_user:
        raise ArcLinkAcademyProgramError("can only adopt an academy graduate owned by this account")
    _ensure_deployment_owner_consistency(conn, user_id=clean_user, deployment_id=clean_deployment)
    _enforce_trainee_quota(conn, clean_user)
    trainee_id = "atrn_" + secrets.token_hex(8)
    now = _now()
    conn.execute(
        """
        INSERT INTO academy_trainees (
          trainee_id, program_id, user_id, deployment_id, agent_id, name, status,
          mode_open, depth, captain_steer_json, staged_manifest_id, staged_plan_id,
          forward_maintained, adopted_from_trainee_id, enrolled_at, graduated_at,
          created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'graduated', 0, ?, '{}', ?, ?, 1, ?, ?, ?, ?, ?)
        """,
        (
            trainee_id,
            str(source.get("program_id") or ""),
            clean_user,
            clean_deployment,
            str(agent_id or "").strip(),
            str(name or "").strip() or str(source.get("name") or ""),
            str(source.get("depth") or "working"),
            str(source.get("staged_manifest_id") or ""),
            str(source.get("staged_plan_id") or ""),
            source["trainee_id"],
            now,
            now,
            now,
            now,
        ),
    )
    conn.commit()
    return get_academy_trainee(conn, trainee_id) or {}


def adopt_central_specialist(
    conn: sqlite3.Connection,
    *,
    specialist_uid: str,
    user_id: str,
    deployment_id: str,
    agent_id: str = "",
    name: str = "",
    captain_steer: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Adopt a redacted public Academy specialist for a Captain's Agent.

    This is the cross-Captain reuse path. It does NOT clone another Captain's
    private trainee or steer; it creates a new graduated trainee subscribed to
    the shared ``redacted_public`` specialist corpus, then stages a fresh
    Captain-owned application contract for that Agent.
    """
    from arclink_boundary import reject_secret_material

    clean_specialist = str(specialist_uid or "").strip()
    clean_user = str(user_id or "").strip()
    clean_deployment = str(deployment_id or "").strip()
    if not clean_specialist or not clean_user or not clean_deployment:
        raise ArcLinkAcademyProgramError("central specialist adoption requires specialist_uid, user_id, and deployment_id")
    _ensure_deployment_owner_consistency(conn, user_id=clean_user, deployment_id=clean_deployment)
    spec = conn.execute(
        """
        SELECT * FROM academy_corpus_specialists
        WHERE specialist_uid = ? AND status = 'active' AND share_scope = 'redacted_public'
        """,
        (clean_specialist,),
    ).fetchone()
    if spec is None:
        raise ArcLinkAcademyProgramError("can only adopt an active redacted-public central Academy specialist")
    program = get_academy_program(conn, str(spec["program_id"] or ""))
    if program is None:
        raise ArcLinkAcademyProgramError("central Academy specialist has no active Major program")
    _enforce_trainee_quota(conn, clean_user)
    steer = dict(captain_steer or {})
    steer.update(
        {
            "adopted_central_specialist_uid": clean_specialist,
            "adoption_source": "academy_corpus_specialist",
            "share": str(steer.get("share") or "redacted_public"),
        }
    )
    reject_secret_material({"name": name, **{f"steer.{k}": v for k, v in steer.items()}})
    trainee_id = "atrn_" + secrets.token_hex(8)
    now = _now()
    conn.execute(
        """
        INSERT INTO academy_trainees (
          trainee_id, program_id, user_id, deployment_id, agent_id, name, status,
          mode_open, depth, captain_steer_json, staged_manifest_id, staged_plan_id,
          forward_maintained, adopted_from_trainee_id, enrolled_at, graduated_at,
          created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'graduated', 0, ?, ?, '', '', 1, '', ?, ?, ?, ?)
        """,
        (
            trainee_id,
            str(spec["program_id"] or ""),
            clean_user,
            clean_deployment,
            str(agent_id or "").strip(),
            str(name or "").strip() or str(spec["role_title"] or program.get("label") or "Academy Specialist"),
            str(program.get("default_depth") or "working"),
            _dumps(steer),
            now,
            now,
            now,
            now,
        ),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO academy_specialist_subscriptions (
          specialist_uid, trainee_id, user_id, subscribed_at, last_applied_capsule_version
        ) VALUES (?, ?, ?, ?, 0)
        """,
        (clean_specialist, trainee_id, clean_user, now),
    )
    curated = curate_academy_trainee(conn, trainee_id=trainee_id, created_at=now, commit=False)
    conn.commit()
    trainee = get_academy_trainee(conn, trainee_id) or {}
    trainee["adopted_central_specialist_uid"] = clean_specialist
    trainee["central_specialist"] = academy_specialist_public_card(conn, specialist_uid=clean_specialist)
    trainee["staged_source_count"] = int(curated.get("source_count") or 0)
    return trainee


# Lane-valid fixture metadata so locally-generated corpora pass the governed
# validation in arclink_academy_trainer.validate_academy_sources. Live source
# acquisition replaces these fixtures behind PG-PROVIDER (see academy-trainer.md).
_LANE_REQUIRED_META: dict[str, dict[str, Any]] = {
    "video_transcript": {"transcript_source": "creator-provided", "transcript_confidence": "high"},
    "reddit_discussion": {"subreddit": "r/practitioners", "thread_quality": "high"},
    "wikimedia": {"revision": "rev-1"},
    "github_repository": {"repo": "org/example", "commit_or_tag": "v1.0.0", "license": "mit"},
    "scholarly_standard": {"identifier": "openalex:W000", "venue_or_body": "Example Standards Body"},
    "web_article": {"author_or_org": "Example Practitioner", "published_at": "2026-01-01"},
    "skill_tool_catalog": {"skill_id": "retrieval-and-cite", "review_status": "approved"},
    "organization_private": {"owner": "operator", "audience_scope": "operator"},
}


def _fixture_sources_for_program(program: Mapping[str, Any], now: str) -> list[Any]:
    """Build governed local-fixture sources for a Major's lanes (no network).

    Live acquisition replaces this behind PG-PROVIDER; the fixtures here let the
    curation pipeline run, score, and stage a plan entirely locally.
    """
    from arclink_academy_trainer import fake_academy_source

    program_id = str(program.get("program_id") or "program")
    label = str(program.get("label") or program_id)
    sources: list[Any] = []
    for index, lane in enumerate(program.get("source_lanes") or []):
        meta = dict(_LANE_REQUIRED_META.get(str(lane), {}))
        meta.update({"examples": True, "fresh": True, "freshness_days": 7})
        sources.append(
            fake_academy_source(
                source_id=f"{program_id}-{lane}-{index}",
                lane_id=str(lane),
                title=f"{label}: {lane} reference",
                origin_url=f"https://example.test/academy/{program_id}/{lane}",
                retrieved_at=now,
                license_status="operator-approved",
                permission_status="operator-approved",
                storage_policy="derived_summary",
                content=f"Derived-summary lesson notes for {label} via the {lane} lane.",
                citations=[
                    f"https://example.test/cite/{program_id}/{lane}/1",
                    f"https://example.test/cite/{program_id}/{lane}/2",
                ],
                metadata=meta,
                review_status="approved" if str(lane) == "skill_tool_catalog" else "reviewed",
            )
        )
    return sources


def _plan_id(plan: Any) -> str:
    for attr in ("plan_id", "application_plan_id", "id"):
        value = getattr(plan, attr, "")
        if value:
            return str(value)
    return ""


# ---------------------------------------------------------------------------
# Central, deduplicated subject-matter-expert corpus (shared across captains).
# ---------------------------------------------------------------------------
#
# Per-trainee proposals (academy_resource_proposals) are the INTAKE layer. On
# graduation the Trainer screens each proposal and, for public lanes the Captain
# has not opted out of sharing, promotes a REDACTED, derived-notes-only canonical
# row into academy_sources (globally deduped by source_uid) attached to a deduped
# academy_corpus_specialists row. Any captain training the same Major SUBSCRIBES to
# that specialist and inherits its shared corpus -- review once, store once, reuse
# everywhere. Contributor identity lives only in academy_source_provenance and is
# never exposed cross-tenant.

_TRACKING_QUERY_PREFIXES = ("utm_", "fbclid", "gclid", "mc_", "ref_src", "spm")
_PLACEHOLDER_HOSTS = ("proposed.invalid", "central.invalid")

# Heuristics for raw content that must never reach the (compressed) central corpus.
_RAW_CONTENT_MARKERS = (
    "<html", "<!doctype", "<script", "<div", "<span", "</p>", "</div>", "</span>",
    "<table", "<tbody", "<svg", "<?xml",
)


def _canonical_url(value: Any) -> str:
    """Normalize a URL for global dedup: lowercase scheme/host, drop fragment and
    tracking params, trim trailing slash. Non-URLs return ''."""
    raw = str(value or "").strip()
    if not raw or "://" not in raw:
        return ""
    try:
        from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

        parts = urlsplit(raw)
        host = (parts.hostname or "").lower()
        if not host:
            return ""
        netloc = f"{host}:{parts.port}" if parts.port else host
        path = parts.path.rstrip("/") or "/"
        kept = [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=False)
            if not any(k.lower().startswith(p) for p in _TRACKING_QUERY_PREFIXES)
        ]
        query = urlencode(sorted(kept))
        return urlunsplit(((parts.scheme or "https").lower(), netloc, path, query, ""))[:1000]
    except Exception:  # noqa: BLE001 - a malformed URL just isn't canonicalizable
        return ""


def _looks_like_raw_content(text: Any) -> bool:
    """True when text resembles a raw HTML/markup dump rather than compressed
    derived notes. The central corpus stores only derived summaries."""
    lowered = str(text or "").lower()
    if any(marker in lowered for marker in _RAW_CONTENT_MARKERS):
        return True
    return lowered.count("<") >= 6 and lowered.count(">") >= 6


def specialist_uid_for_program(program: Mapping[str, Any]) -> tuple[str, str]:
    """Stable, cross-captain specialist identity for a Major+topic.

    Keyed on program_id + normalized topic so two captains training the same Major
    resolve to ONE shared specialist (vision: deduplicate the role and the SME).
    Returns ``(specialist_uid, topic_fingerprint)``.
    """
    program_id = _slug(str(program.get("program_id") or ""))
    topic = _slug(str(program.get("topic_map") or program.get("label") or ""))[:120]
    seed = f"{program_id}|{topic}"
    return "aspec_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16], topic


def _source_uid(*, canonical_url: str, specialist_uid: str, title: str) -> str:
    seed = canonical_url or f"{specialist_uid}|{_slug(str(title or ''))[:160]}"
    return "asrc_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]


def _proposal_to_source(proposal: Mapping[str, Any], *, stable_ts: str) -> Any:
    """Convert a stored proposal into a governed, lane-valid AcademySource.

    Fills lane-required metadata from the shared defaults so the source passes
    ``validate_academy_sources``. storage_policy is always derived_summary (we only
    ever hold compressed derived notes, never raw content), and a skill proposal is
    never allowed to masquerade as an approved public skill.
    """
    from arclink_academy_trainer import fake_academy_source

    if _proposal_kind(proposal) != "add_resource":
        raise ArcLinkAcademyProgramError("only add_resource proposals can become Academy sources")
    lane = str(proposal.get("lane_id") or "").strip()
    meta = dict(_LANE_REQUIRED_META.get(lane, {}))
    meta.update({"proposed": True, "fresh": True, "freshness_days": 7})
    if lane == "skill_tool_catalog":
        meta["review_status"] = "reviewed"
        meta.pop("public_skill", None)
    title = str(proposal.get("title") or "Proposed source")[:180]
    summary = str(proposal.get("summary") or "").strip()
    url = str(proposal.get("origin_url") or "").strip() or ("https://proposed.invalid/" + _slug(title)[:60])
    citations = [str(c).strip() for c in (proposal.get("citations") or []) if str(c).strip()][:12]
    return fake_academy_source(
        source_id=str(proposal.get("proposal_id") or "")[:120] or ("aprop_" + _slug(title)[:32]),
        lane_id=lane,
        title=title,
        origin_url=url[:500],
        retrieved_at=stable_ts,
        license_status="agent-reported",
        permission_status="captain-authorized",
        storage_policy="derived_summary",
        content=summary or f"Captain-authorized derived notes for {title}.",
        citations=citations,
        metadata=meta,
        review_status="reviewed",
    )


def _proposal_kind(proposal: Mapping[str, Any]) -> str:
    return _clean_proposal_kind(str(proposal.get("proposal_kind") or "add_resource"))


def _clean_proposal_kind(value: str) -> str:
    clean = _slug(str(value or "add_resource")).replace("__", "_")
    aliases = {
        "add": "add_resource",
        "add_source": "add_resource",
        "source": "add_resource",
        "resource": "add_resource",
        "retire_resource": "discontinue_resource",
        "retire_source": "discontinue_resource",
        "remove_resource": "discontinue_resource",
        "remove_source": "discontinue_resource",
        "discontinue": "discontinue_resource",
        "discontinue_source": "discontinue_resource",
        "dead_end": "discontinue_resource",
    }
    clean = aliases.get(clean, clean)
    if clean not in ACADEMY_RESOURCE_PROPOSAL_KINDS:
        raise ArcLinkAcademyProgramError(f"unsupported academy resource proposal kind: {value}")
    return clean


def _review_payload(
    *,
    proposal_kind: str,
    verdict: str,
    reason: str,
    specialist_uid: str,
    source_uid: str = "",
    engine: str = "deterministic",
) -> dict[str, Any]:
    return {
        "reviewed_at": _now(),
        "engine": engine,
        "live": False,
        "proposal_kind": proposal_kind,
        "verdict": verdict,
        "reason": str(reason or "")[:500],
        "specialist_uid": str(specialist_uid or ""),
        "source_uid": str(source_uid or ""),
        "proof_gate": "PG-PROVIDER",
        "live_enrichment_status": "pending_pg_provider",
    }


def _review_discontinue_resource_proposal(
    conn: sqlite3.Connection,
    *,
    specialist_uid: str,
    proposal: Mapping[str, Any],
    now: str,
) -> dict[str, Any]:
    """Critic-review a request to review a central Academy source for removal.

    A single Agent cannot delete corpus history. A discontinuation proposal must
    identify an existing source attached to the same shared specialist. A match
    records a PG-PROVIDER review queue item and leaves the shared source active;
    central corpus removal requires a stronger live/provider or Operator gate.
    """

    pid = str(proposal.get("proposal_id") or "")
    lane = str(proposal.get("lane_id") or "").strip()
    target_uid = str(proposal.get("target_source_uid") or "").strip()
    canonical = str(proposal.get("target_canonical_url") or "").strip() or _canonical_url(proposal.get("origin_url"))
    summary = str(proposal.get("summary") or "").strip()
    if not summary:
        review = _review_payload(
            proposal_kind="discontinue_resource",
            verdict="reject",
            reason="discontinuation proposal requires a concise reason",
            specialist_uid=specialist_uid,
        )
        conn.execute(
            "UPDATE academy_resource_proposals SET status = 'rejected', trainer_review_json = ?, updated_at = ? WHERE proposal_id = ?",
            (_dumps(review), now, pid),
        )
        return {"proposal_id": pid, "status": "rejected", "reason": review["reason"]}
    clauses = ["link.specialist_uid = ?"]
    params: list[Any] = [specialist_uid]
    if target_uid:
        clauses.append("src.source_uid = ?")
        params.append(target_uid)
    elif canonical:
        clauses.append("src.canonical_url = ?")
        params.append(canonical)
    else:
        review = _review_payload(
            proposal_kind="discontinue_resource",
            verdict="reject",
            reason="discontinuation proposal requires target_source_uid or canonical origin_url",
            specialist_uid=specialist_uid,
        )
        conn.execute(
            "UPDATE academy_resource_proposals SET status = 'rejected', trainer_review_json = ?, updated_at = ? WHERE proposal_id = ?",
            (_dumps(review), now, pid),
        )
        return {"proposal_id": pid, "status": "rejected", "reason": review["reason"]}
    row = conn.execute(
        f"""
        SELECT src.* FROM academy_sources src
        JOIN academy_specialist_sources link ON link.source_uid = src.source_uid
        WHERE {' AND '.join(clauses)}
        ORDER BY src.first_seen_at, src.source_uid
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    if row is None:
        review = _review_payload(
            proposal_kind="discontinue_resource",
            verdict="reject",
            reason="target source is not attached to this shared Academy specialist",
            specialist_uid=specialist_uid,
        )
        conn.execute(
            "UPDATE academy_resource_proposals SET status = 'rejected', trainer_review_json = ?, updated_at = ? WHERE proposal_id = ?",
            (_dumps(review), now, pid),
        )
        return {"proposal_id": pid, "status": "rejected", "reason": review["reason"]}
    source_uid = str(row["source_uid"])
    if lane and lane != str(row["lane_id"] or ""):
        review = _review_payload(
            proposal_kind="discontinue_resource",
            verdict="reject",
            reason="proposal lane does not match the target source lane",
            specialist_uid=specialist_uid,
            source_uid=source_uid,
        )
        conn.execute(
            "UPDATE academy_resource_proposals SET status = 'rejected', trainer_review_json = ?, updated_at = ? WHERE proposal_id = ?",
            (_dumps(review), now, pid),
        )
        return {"proposal_id": pid, "status": "rejected", "source_uid": source_uid, "reason": review["reason"]}
    enrichment = _loads(row["enrichment_json"], default={})
    if not isinstance(enrichment, dict):
        enrichment = {}
    review = _review_payload(
        proposal_kind="discontinue_resource",
        verdict="pending_live_review",
        reason=summary,
        specialist_uid=specialist_uid,
        source_uid=source_uid,
    )
    queue = enrichment.get("discontinue_review_queue")
    if not isinstance(queue, list):
        queue = []
    queue = [item for item in queue if str((item if isinstance(item, dict) else {}).get("proposal_id") or "") != pid]
    queue.append(
        {
            "proposal_id": pid,
            "queued_at": review["reviewed_at"],
            "engine": review["engine"],
            "reason": review["reason"],
            "status": "pending_pg_provider",
        }
    )
    enrichment["discontinue_review"] = {
        "proposal_id": pid,
        "reviewed_at": review["reviewed_at"],
        "engine": review["engine"],
        "reason": review["reason"],
        "status": "pending_pg_provider",
    }
    enrichment["discontinue_review_queue"] = queue[-20:]
    conn.execute(
        """
        UPDATE academy_sources
        SET enrichment_json = ?, last_reviewed_at = ?, updated_at = ?
        WHERE source_uid = ?
        """,
        (_dumps(enrichment), now, now, source_uid),
    )
    conn.execute(
        "UPDATE academy_resource_proposals SET status = 'review_pending', trainer_review_json = ?, updated_at = ? WHERE proposal_id = ?",
        (_dumps(review), now, pid),
    )
    return {
        "proposal_id": pid,
        "status": "review_pending",
        "source_uid": source_uid,
        "reason": review["reason"],
        "review_required": "PG-PROVIDER",
    }


def promote_proposals_to_central(
    conn: sqlite3.Connection,
    *,
    trainee_id: str,
    actor: str = "system:trainer",
    commit: bool = True,
) -> dict[str, Any]:
    """Trainer step: promote a trainee's public-lane, public-safe proposals into the
    CENTRAL deduplicated SME corpus, then subscribe the trainee to that specialist.

    Opt-out sharing (Captain's chosen policy): every public-lane proposal that passes
    the secret-screen, raw-content, and lane-eligibility checks is promoted as
    ``redacted_public`` UNLESS the Captain set ``steer['share']`` to a private value.
    ``organization_private`` is never promoted (public lanes only). Global dedup by
    source_uid collapses the same canonical source contributed by any captain into
    one row -- "review once, store once, reuse everywhere".
    """
    from arclink_boundary import reject_secret_material
    from arclink_academy_trainer import share_eligible_source_lanes

    trainee = get_academy_trainee(conn, trainee_id)
    if trainee is None:
        raise ArcLinkAcademyProgramError(f"unknown academy trainee: {trainee_id}")
    program = get_academy_program(conn, str(trainee.get("program_id") or ""))
    if program is None:
        raise ArcLinkAcademyProgramError("academy trainee has no Major program")

    steer = trainee.get("captain_steer") or {}
    opted_out = str(steer.get("share") or "").strip().lower() in {"private", "off", "no", "none", "false"}
    eligible_lanes = share_eligible_source_lanes()
    now = _now()
    specialist_uid, topic_fp = specialist_uid_for_program(program)
    share_scope = "private" if opted_out else "redacted_public"

    proposals = read_academy_proposals(conn, trainee_id=trainee["trainee_id"], statuses=USABLE_PROPOSAL_STATUSES)
    existing_spec = conn.execute(
        "SELECT * FROM academy_corpus_specialists WHERE specialist_uid = ?", (specialist_uid,)
    ).fetchone()
    # No shareable footprint and no specialist yet (e.g. a fixture-only graduate):
    # do not create an empty central specialist.
    has_candidate = (not opted_out) and any(
        _proposal_kind(p) == "add_resource" and str(p.get("lane_id") or "") in eligible_lanes for p in proposals
    )
    if not has_candidate and existing_spec is None:
        reviewed_discontinuations: list[dict[str, Any]] = []
        for proposal in proposals:
            if _proposal_kind(proposal) != "discontinue_resource":
                continue
            pid = str(proposal.get("proposal_id") or "")
            review = _review_payload(
                proposal_kind="discontinue_resource",
                verdict="reject",
                reason="no shared Academy specialist exists for this discontinuation target yet",
                specialist_uid="",
            )
            conn.execute(
                "UPDATE academy_resource_proposals SET status = 'rejected', trainer_review_json = ?, updated_at = ? WHERE proposal_id = ?",
                (_dumps(review), now, pid),
            )
            reviewed_discontinuations.append({"proposal_id": pid, "status": "rejected", "reason": review["reason"]})
        if commit:
            conn.commit()
        return {
            "specialist_uid": "",
            "share_scope": share_scope,
            "promoted_source_uids": [],
            "deduped_source_uids": [],
            "discontinued_sources": reviewed_discontinuations,
            "skipped": [{"reason": "no_share_eligible_proposals"}] if proposals else [],
            "promoted_count": 0,
            "deduped_count": 0,
            "discontinued_count": 0,
            "discontinue_review_pending_count": 0,
            "skipped_count": len(proposals) if opted_out or proposals else 0,
            "opted_out": opted_out,
            "cross_tenant_proof_gate": ACADEMY_CROSS_TENANT_PROOF_GATE,
        }
    spec_created = str(existing_spec["first_seen_at"]) if existing_spec is not None else now
    # Once a specialist is shared it stays shared (another captain may rely on it).
    spec_scope = "redacted_public" if (existing_spec is not None and str(existing_spec["share_scope"]) == "redacted_public") else share_scope
    conn.execute(
        """
        INSERT INTO academy_corpus_specialists (
          specialist_uid, program_id, role_title, topic_fingerprint,
          compressed_soul_capsule, capsule_version, enrichment_json, captain_count,
          share_scope, status, first_seen_at, last_enriched_at, updated_at
        ) VALUES (?, ?, ?, ?, '', 0, '{}', 0, ?, 'active', ?, '', ?)
        ON CONFLICT(specialist_uid) DO UPDATE SET
          role_title = excluded.role_title,
          topic_fingerprint = excluded.topic_fingerprint,
          share_scope = excluded.share_scope,
          updated_at = excluded.updated_at
        """,
        (
            specialist_uid,
            str(program.get("program_id") or ""),
            str(program.get("label") or program.get("program_id") or ""),
            topic_fp,
            spec_scope,
            spec_created,
            now,
        ),
    )

    promoted: list[str] = []
    deduped: list[str] = []
    discontinued: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for proposal in proposals:
        pid = str(proposal.get("proposal_id") or "")
        kind = _proposal_kind(proposal)
        if kind == "discontinue_resource":
            reviewed = _review_discontinue_resource_proposal(
                conn,
                specialist_uid=specialist_uid,
                proposal=proposal,
                now=now,
            )
            discontinued.append({"proposal_id": pid, **reviewed})
            continue
        lane = str(proposal.get("lane_id") or "").strip()
        title = str(proposal.get("title") or "").strip()[:240]
        notes = str(proposal.get("summary") or "").strip()
        citations = [str(c).strip()[:1000] for c in (proposal.get("citations") or []) if str(c).strip()][:20]
        if lane not in eligible_lanes:
            skipped.append({"proposal_id": pid, "reason": "lane_not_share_eligible", "lane_id": lane})
            continue
        if opted_out:
            skipped.append({"proposal_id": pid, "reason": "captain_opted_out", "lane_id": lane})
            continue
        if _looks_like_raw_content(notes):
            skipped.append({"proposal_id": pid, "reason": "raw_content_not_derived", "lane_id": lane})
            continue
        try:
            reject_secret_material(
                {"title": title, "derived_notes": notes, **{f"citation.{i}": c for i, c in enumerate(citations)}}
            )
        except Exception:  # noqa: BLE001 - secret-looking material is screened out, not promoted
            skipped.append({"proposal_id": pid, "reason": "secret_screen_rejected", "lane_id": lane})
            continue
        canonical = _canonical_url(proposal.get("origin_url"))
        suid = _source_uid(canonical_url=canonical, specialist_uid=specialist_uid, title=title)
        content_hash = hashlib.sha256(notes.encode("utf-8")).hexdigest()[:32]
        existing_src = conn.execute("SELECT * FROM academy_sources WHERE source_uid = ?", (suid,)).fetchone()
        if existing_src is not None:
            merged = list(dict.fromkeys((_loads(existing_src["citations_json"], default=[]) or []) + citations))[:30]
            # Central source body is trainer-governed shared material. A later
            # captain can add provenance/citations, but cannot silently replace the
            # already accepted shared notes for everyone subscribed to this source.
            retained_title = str(existing_src["title"] or "").strip() or title
            retained_notes = str(existing_src["derived_notes"] or "").strip() or notes
            retained_hash = str(existing_src["content_hash"] or "").strip() or hashlib.sha256(
                retained_notes.encode("utf-8")
            ).hexdigest()[:32]
            retained_lane = str(existing_src["lane_id"] or "").strip() or lane
            conn.execute(
                """
                UPDATE academy_sources
                SET title = ?, derived_notes = ?, citations_json = ?, content_hash = ?,
                    lane_id = ?, last_observed_at = ?, updated_at = ?, status = 'active'
                WHERE source_uid = ?
                """,
                (retained_title, retained_notes, _dumps(merged), retained_hash, retained_lane, now, now, suid),
            )
            deduped.append(suid)
        else:
            conn.execute(
                """
                INSERT INTO academy_sources (
                  source_uid, canonical_url, lane_id, title, derived_notes, citations_json,
                  content_hash, license_status, enrichment_json, quality_score, share_scope,
                  status, first_seen_at, last_reviewed_at, last_observed_at, freshness_days, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'agent-reported', '{}', 0, 'redacted_public', 'active', ?, ?, '', 7, ?)
                """,
                (suid, canonical, lane, title, notes, _dumps(citations), content_hash, now, now, now),
            )
            promoted.append(suid)
        conn.execute(
            "INSERT OR IGNORE INTO academy_specialist_sources (specialist_uid, source_uid, weight, added_at) VALUES (?, ?, 0, ?)",
            (specialist_uid, suid, now),
        )
        prov_id = "aprov_" + hashlib.sha256(f"{suid}|{trainee['trainee_id']}".encode("utf-8")).hexdigest()[:16]
        conn.execute(
            """
            INSERT INTO academy_source_provenance (
              provenance_id, source_uid, contributor_user_id, contributor_trainee_id,
              share_consent, redaction_applied, consented_at, revoked_at
            ) VALUES (?, ?, ?, ?, 'redacted_public', 1, ?, '')
            ON CONFLICT(source_uid, contributor_trainee_id) DO UPDATE SET
              share_consent = 'redacted_public', redaction_applied = 1, revoked_at = ''
            """,
            (prov_id, suid, str(trainee.get("user_id") or ""), str(trainee["trainee_id"]), now),
        )
        conn.execute(
            "UPDATE academy_resource_proposals SET status = 'accepted', updated_at = ? WHERE proposal_id = ?",
            (now, pid),
        )

    if not opted_out:
        conn.execute(
            """
            INSERT OR IGNORE INTO academy_specialist_subscriptions (
              specialist_uid, trainee_id, user_id, subscribed_at, last_applied_capsule_version
            ) VALUES (?, ?, ?, ?, 0)
            """,
            (specialist_uid, str(trainee["trainee_id"]), str(trainee.get("user_id") or ""), now),
        )
    crow = conn.execute(
        """
        SELECT COUNT(DISTINCT p.contributor_user_id) AS n
        FROM academy_source_provenance p
        JOIN academy_specialist_sources s ON s.source_uid = p.source_uid
        WHERE s.specialist_uid = ? AND p.revoked_at = '' AND p.share_consent != 'none'
        """,
        (specialist_uid,),
    ).fetchone()
    conn.execute(
        "UPDATE academy_corpus_specialists SET captain_count = ?, updated_at = ? WHERE specialist_uid = ?",
        (int(crow["n"] if crow is not None else 0), now, specialist_uid),
    )
    # Recompose the replaceable knowledge capsule from the (deduped) central sources.
    capsule_version = 0
    if promoted or deduped or any(item.get("status") == "accepted" for item in discontinued):
        capsule = refresh_specialist_capsule(conn, specialist_uid=specialist_uid, actor=actor, commit=False)
        capsule_version = int(capsule.get("capsule_version") or 0)
    pending_discontinue_count = len([item for item in discontinued if item.get("status") == "review_pending"])
    if commit:
        conn.commit()
    return {
        "specialist_uid": specialist_uid,
        "share_scope": share_scope,
        "promoted_source_uids": promoted,
        "deduped_source_uids": deduped,
        "discontinued_sources": discontinued,
        "skipped": skipped,
        "promoted_count": len(promoted),
        "deduped_count": len(deduped),
        "discontinued_count": len([item for item in discontinued if item.get("status") == "accepted"]),
        "discontinue_review_pending_count": pending_discontinue_count,
        "skipped_count": len(skipped),
        "capsule_version": capsule_version,
        "opted_out": opted_out,
        "cross_tenant_proof_gate": ACADEMY_CROSS_TENANT_PROOF_GATE,
    }


ACADEMY_CAPSULE_CHAR_LIMIT = 6000


def _private_trainee_capsule_from_manifest(manifest: Any, *, program: Mapping[str, Any]) -> str:
    """Compose a private, per-trainee Academy capsule from reviewed lesson cards.

    This is the non-public apply path for Captains who opt out of the shared
    central corpus or whose useful training sources are private lanes. It uses the
    same validated, derived lesson cards as the staged application plan and never
    promotes anything into the reusable public Academy.
    """
    data = manifest.to_dict() if hasattr(manifest, "to_dict") else dict(manifest or {})
    cards = [dict(item) for item in (data.get("lesson_cards") or []) if isinstance(item, Mapping)]
    accepted = [card for card in cards if str(card.get("quality_status") or "") == "accepted"]
    if not accepted:
        return ""
    role_title = str(program.get("label") or data.get("role_title") or "Specialist").strip()
    topic = str(program.get("topic_map") or data.get("topic") or "").strip()
    lines = [
        f"# Academy specialist: {role_title}",
        "",
        "<!-- Private Academy capsule for this Captain-owned Agent.",
        "Derived notes only; not published to the central reusable Academy. -->",
        "",
    ]
    if topic:
        lines += ["## Topic map", topic, ""]
    lines.append("## Curated private sources (derived notes; retrieve and cite before advising)")
    for card in accepted[:12]:
        title = " ".join(str(card.get("title") or "source").split())[:180]
        lane = " ".join(str(card.get("lane_id") or "source").split())[:80]
        summary = " ".join(str(card.get("summary") or "").split())
        if len(summary) > 400:
            summary = summary[:397] + "..."
        lines.append(f"- **{title}** ({lane}): {summary or 'Metadata-only source; retrieve approved details before relying on it.'}")
    return "\n".join(lines)[:ACADEMY_CAPSULE_CHAR_LIMIT]


def refresh_specialist_capsule(
    conn: sqlite3.Connection,
    *,
    specialist_uid: str,
    actor: str = "system:trainer",
    only_if_changed: bool = False,
    commit: bool = True,
) -> dict[str, Any]:
    """Trainer (deterministic) step: compose the specialist's REPLACEABLE compressed
    knowledge capsule from its central sources and bump ``capsule_version``.

    The capsule is the replaceable section that accompanies the Agent SOUL (rendered
    and written behind ``PG-HERMES`` by the apply path; kept fresh weekly). It is
    built ONLY from already redacted, derived-notes-only central sources -- never raw
    content. Live LLM enrichment/compression by the Academy Trainer (same inference
    model) layers on top of this deterministic capsule behind ``PG-PROVIDER``.
    """
    clean = str(specialist_uid or "").strip()
    spec = conn.execute(
        "SELECT * FROM academy_corpus_specialists WHERE specialist_uid = ?", (clean,)
    ).fetchone()
    if spec is None:
        raise ArcLinkAcademyProgramError(f"unknown central specialist: {specialist_uid}")
    program = get_academy_program(conn, str(spec["program_id"] or "")) or {}
    rows = conn.execute(
        """
        SELECT src.* FROM academy_sources src
        JOIN academy_specialist_sources link ON link.source_uid = src.source_uid
        WHERE link.specialist_uid = ? AND src.status = 'active' AND src.share_scope = 'redacted_public'
        ORDER BY src.quality_score DESC, src.first_seen_at
        """,
        (clean,),
    ).fetchall()
    role_title = str(spec["role_title"] or program.get("label") or "Specialist")
    topic = str(program.get("topic_map") or spec["topic_fingerprint"] or "")
    role_template = str(program.get("role_template") or "")
    lanes = sorted({str(r["lane_id"]) for r in rows})
    lines = [
        f"# Academy specialist: {role_title}",
        "",
        "<!-- Replaceable Academy knowledge capsule. Refreshed weekly by continuing",
        "education; safe to swap if the Captain changes the role. Derived notes only. -->",
        "",
    ]
    if role_template:
        lines += ["## Role", role_template.strip(), ""]
    if topic:
        lines += ["## Topic map", topic.strip(), ""]
    lines.append("## Curated sources (derived notes; cite before advising)")
    for r in rows:
        note = " ".join(str(r["derived_notes"] or "").split())
        if len(note) > 400:
            note = note[:397] + "..."
        cites = _loads(r["citations_json"], default=[]) or []
        cite = f" [cite: {str(cites[0])[:200]}]" if cites else (f" [cite: {str(r['canonical_url'])[:200]}]" if r["canonical_url"] else "")
        lines.append(f"- **{str(r['title'] or 'source').strip()}** ({r['lane_id']}): {note}{cite}")
    if not rows:
        lines.append("- (no curated sources yet)")
    capsule = "\n".join(lines)[:ACADEMY_CAPSULE_CHAR_LIMIT]
    now = _now()
    if only_if_changed and capsule == str(spec["compressed_soul_capsule"] or ""):
        return {
            "specialist_uid": clean,
            "capsule_chars": len(capsule),
            "capsule_version": int(spec["capsule_version"]),
            "source_count": len(rows),
            "lanes": lanes,
            "changed": False,
            "live_enrichment_status": "pending_pg_provider",
        }
    next_version = int(spec["capsule_version"]) + 1
    enrichment = {
        "source_count": len(rows),
        "lanes": lanes,
        "deterministic": True,
        "live_enrichment_status": "pending_pg_provider",
        "refreshed_at": now,
        "actor": str(actor or "").strip() or "system:trainer",
    }
    conn.execute(
        """
        UPDATE academy_corpus_specialists
        SET compressed_soul_capsule = ?, capsule_version = ?, enrichment_json = ?,
            last_enriched_at = ?, updated_at = ?
        WHERE specialist_uid = ?
        """,
        (capsule, next_version, _dumps(enrichment), now, now, clean),
    )
    if commit:
        conn.commit()
    return {
        "specialist_uid": clean,
        "capsule_chars": len(capsule),
        "capsule_version": next_version,
        "source_count": len(rows),
        "lanes": lanes,
        "changed": True,
        "live_enrichment_status": "pending_pg_provider",
    }


def _truthy_env(name: str, *, default: bool = False, env: Mapping[str, str] | None = None) -> bool:
    raw = str((env or os.environ).get(name, "")).strip().lower()
    if raw in {"1", "true", "yes", "on", "enabled"}:
        return True
    if raw in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def academy_trainer_live_authorized_from_env(env: Mapping[str, str] | None = None) -> bool:
    """Return whether PG-PROVIDER live Trainer review is explicitly enabled."""
    return _truthy_env("ARCLINK_ACADEMY_TRAINER_LIVE", default=False, env=env)


def _trainer_env_text(env: Mapping[str, str] | None, *names: str, default: str = "") -> str:
    source = env or os.environ
    for name in names:
        value = str(source.get(name) or "").strip()
        if value:
            return value
    return default


def _read_trainer_router_key(env: Mapping[str, str] | None = None) -> str:
    key = _trainer_env_text(env, "ARCLINK_ACADEMY_TRAINER_ROUTER_KEY")
    if key:
        return key
    key_file = _trainer_env_text(env, "ARCLINK_ACADEMY_TRAINER_ROUTER_KEY_FILE")
    if not key_file:
        return ""
    try:
        return open(key_file, "r", encoding="utf-8").read().strip()
    except OSError:
        return ""


def _compact_trainer_source(source: Mapping[str, Any]) -> dict[str, Any]:
    citations = _loads(source.get("citations_json"), default=[])
    safe_citations: list[str] = []
    if isinstance(citations, list):
        for citation in citations[:8]:
            safe_citations.append(redact_then_truncate(citation, limit=600))
    return {
        "source_uid": redact_then_truncate(source.get("source_uid") or "", limit=120),
        "lane_id": redact_then_truncate(source.get("lane_id") or "", limit=80),
        "title": redact_then_truncate(source.get("title") or "", limit=240),
        "canonical_url": redact_then_truncate(source.get("canonical_url") or "", limit=600),
        "derived_notes": redact_then_truncate(source.get("derived_notes") or "", limit=1600),
        "citations": safe_citations,
    }


def _safe_trainer_verdicts(parsed: Mapping[str, Any], sources: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    by_uid = {str(source.get("source_uid") or "") for source in sources}
    verdicts: list[dict[str, str]] = []
    raw = parsed.get("verdicts")
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            uid = str(item.get("source_uid") or "").strip()
            if uid not in by_uid:
                continue
            verdict = str(item.get("verdict") or "keep").strip().lower()
            if verdict not in {"keep", "watch", "replace", "block"}:
                verdict = "keep"
            verdicts.append(
                {
                    "source_uid": uid,
                    "lane_id": str(item.get("lane_id") or "")[:80],
                    "verdict": verdict,
                    "note": str(item.get("note") or "")[:500],
                }
            )
    seen = {item["source_uid"] for item in verdicts}
    for source in sources:
        uid = str(source.get("source_uid") or "")
        if uid and uid not in seen:
            verdicts.append(
                {
                    "source_uid": uid,
                    "lane_id": str(source.get("lane_id") or "")[:80],
                    "verdict": "keep",
                    "note": "Trainer retained this derived source; cite before advising.",
                }
            )
    return verdicts


class RouterAcademyTrainerClient:
    """Live Academy Trainer client backed by the ArcLink LLM router.

    This client is intentionally narrow: it sends compact derived source notes to
    the control-plane router and never sees the upstream provider key directly.
    """

    live = True

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int = 45,
    ) -> None:
        self.base_url = str(base_url or "").rstrip("/")
        self.api_key = str(api_key or "").strip()
        self.model = str(model or "").strip() or DEFAULT_ACADEMY_TRAINER_MODEL
        self.timeout_seconds = max(5, min(120, int(timeout_seconds or 45)))

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "RouterAcademyTrainerClient | None":
        base_url = _trainer_env_text(
            env,
            "ARCLINK_ACADEMY_TRAINER_ROUTER_BASE_URL",
            "ARCLINK_LLM_ROUTER_BASE_URL",
            default="http://control-llm-router:8090/v1",
        ).rstrip("/")
        api_key = _read_trainer_router_key(env)
        if not base_url or not api_key:
            return None
        timeout_raw = _trainer_env_text(env, "ARCLINK_ACADEMY_TRAINER_TIMEOUT_SECONDS", default="45")
        try:
            timeout = int(timeout_raw)
        except ValueError:
            timeout = 45
        return cls(
            base_url=base_url,
            api_key=api_key,
            model=_trainer_env_text(
                env,
                "ARCLINK_ACADEMY_TRAINER_MODEL",
                "ARCLINK_LLM_ROUTER_DEFAULT_MODEL",
                "ARCLINK_CHUTES_DEFAULT_MODEL",
                default=DEFAULT_ACADEMY_TRAINER_MODEL,
            ),
            timeout_seconds=timeout,
        )

    def review(self, *, role_title: str, topic: str, sources: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        payload_sources = [_compact_trainer_source(source) for source in sources[:40]]
        request_payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 900,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the ArcLink Academy Trainer. Review only the derived source notes supplied. "
                        "Return strict JSON with summary and verdicts. Do not include secrets or raw source text."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "role_title": str(role_title or "")[:200],
                            "topic": str(topic or "")[:1000],
                            "sources": payload_sources,
                            "verdict_schema": {
                                "source_uid": "source identifier from input",
                                "lane_id": "source lane from input",
                                "verdict": "keep|watch|replace|block",
                                "note": "short derived rationale",
                            },
                        },
                        sort_keys=True,
                    ),
                },
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(request_payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - control router URL is operator-configured
                response_body = response.read(262_144).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = exc.read(4096).decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
            raise RuntimeError(f"llm-router trainer request failed status={exc.code}: {body[:240]}") from exc
        parsed = _loads(response_body, default={})
        choices = parsed.get("choices") if isinstance(parsed, Mapping) else None
        content = ""
        if isinstance(choices, Sequence) and choices and isinstance(choices[0], Mapping):
            message = choices[0].get("message")
            if isinstance(message, Mapping):
                content = str(message.get("content") or "")
        content_json = _loads(content, default={})
        summary = ""
        if isinstance(content_json, Mapping):
            summary = str(content_json.get("summary") or "")[:2000]
        if not summary:
            summary = content.strip()[:2000] or f"Live Trainer reviewed {len(payload_sources)} source(s)."
        verdict_source = content_json if isinstance(content_json, Mapping) else {}
        return {
            "engine": "llm-router",
            "live": True,
            "summary": summary,
            "verdicts": _safe_trainer_verdicts(verdict_source, sources),
            "topic": topic,
            "model": self.model,
        }


def academy_trainer_client_from_env(env: Mapping[str, str] | None = None) -> RouterAcademyTrainerClient | None:
    return RouterAcademyTrainerClient.from_env(env)


class DeterministicAcademyTrainer:
    """Default, no-network Academy Trainer.

    Produces governed per-source verdicts + a deterministic review summary. The LIVE
    Academy Trainer -- the SAME inference model used for the Agent, routed through
    ``arclink_llm_router`` -- is an injectable client exposing the same ``.review()``
    surface with ``live = True``; it is consulted ONLY when ``PG-PROVIDER``
    authorization (``live_authorized``) is present, and any failure falls closed to
    this deterministic engine.
    """

    live = False

    def review(self, *, role_title: str, topic: str, sources: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        verdicts = [
            {
                "source_uid": str(s.get("source_uid") or ""),
                "lane_id": str(s.get("lane_id") or ""),
                "verdict": "keep",
                "note": "derived notes retained; cite before advising",
            }
            for s in sources
        ]
        return {
            "engine": "deterministic",
            "live": False,
            "summary": f"Deterministic Trainer review of {len(verdicts)} source(s) for {role_title}.",
            "verdicts": verdicts,
            "topic": topic,
        }


def run_academy_trainer_review(
    conn: sqlite3.Connection,
    *,
    specialist_uid: str,
    client: Any | None = None,
    live_authorized: bool = False,
    actor: str = "system:trainer",
    commit: bool = True,
) -> dict[str, Any]:
    """The Academy Trainer deep dive: review/dedupe/enrich a specialist's central
    corpus and refresh its replaceable capsule.

    Deterministic by default (no network). When ``live_authorized`` (``PG-PROVIDER``)
    AND a live ``client`` (same inference model via ``arclink_llm_router``) is
    supplied, the live review is used; otherwise it fails CLOSED to the deterministic
    engine and records that live enrichment is still pending. Records the review on
    the specialist ``enrichment_json`` and stamps ``trainer_review_json`` on the
    contributing proposals so the Captain can see the deep dive ran.
    """
    clean = str(specialist_uid or "").strip()
    spec = conn.execute(
        "SELECT * FROM academy_corpus_specialists WHERE specialist_uid = ?", (clean,)
    ).fetchone()
    if spec is None:
        raise ArcLinkAcademyProgramError(f"unknown central specialist: {specialist_uid}")
    program = get_academy_program(conn, str(spec["program_id"] or "")) or {}
    rows = conn.execute(
        """
        SELECT src.* FROM academy_sources src
        JOIN academy_specialist_sources link ON link.source_uid = src.source_uid
        WHERE link.specialist_uid = ? AND src.status = 'active' AND src.share_scope = 'redacted_public'
        ORDER BY src.first_seen_at, src.source_uid
        """,
        (clean,),
    ).fetchall()
    role_title = str(spec["role_title"] or program.get("label") or "Specialist")
    topic = str(program.get("topic_map") or spec["topic_fingerprint"] or "")
    sources = [dict(r) for r in rows]

    if bool(live_authorized) and client is None:
        client = academy_trainer_client_from_env()
    use_live = bool(live_authorized) and client is not None and bool(getattr(client, "live", False))
    trainer = client if use_live else DeterministicAcademyTrainer()
    try:
        review = trainer.review(role_title=role_title, topic=topic, sources=sources)
    except Exception as exc:  # noqa: BLE001 - a live Trainer failure falls closed to deterministic
        review = DeterministicAcademyTrainer().review(role_title=role_title, topic=topic, sources=sources)
        review["live_error"] = str(exc)[:200]
        use_live = False
    now = _now()
    engine = str(review.get("engine") or ("live" if use_live else "deterministic"))
    enrichment = {
        "reviewed_at": now,
        "live": bool(use_live),
        "live_authorized": bool(live_authorized),
        "engine": engine,
        "summary": str(review.get("summary") or "")[:2000],
        "verdict_count": len(review.get("verdicts") or []),
        "source_count": len(sources),
        "proof_gate": "PG-PROVIDER",
        "live_enrichment_status": "live_reviewed" if use_live else "pending_pg_provider",
        "actor": str(actor or "").strip() or "system:trainer",
    }
    # Recompose the capsule FIRST. refresh_specialist_capsule writes its own
    # deterministic enrichment_json whenever the capsule body changes, so the Trainer
    # enrichment (engine/live/summary/verdicts) must be written AFTER it or it would be
    # clobbered and the live review metadata lost on any week the capsule changes.
    capsule_result = refresh_specialist_capsule(
        conn, specialist_uid=clean, actor=actor, only_if_changed=True, commit=False
    )
    conn.execute(
        "UPDATE academy_corpus_specialists SET enrichment_json = ?, last_enriched_at = ?, updated_at = ? WHERE specialist_uid = ?",
        (_dumps(enrichment), now, now, clean),
    )
    # Stamp the contributing trainees' promoted proposals so the Captain sees the
    # Trainer deep dive ran on what they gathered.
    contributors = {
        str(pr["trainee_id"])
        for pr in conn.execute(
            "SELECT DISTINCT p.contributor_trainee_id AS trainee_id FROM academy_source_provenance p "
            "JOIN academy_specialist_sources s ON s.source_uid = p.source_uid "
            "WHERE s.specialist_uid = ? AND p.revoked_at = ''",
            (clean,),
        ).fetchall()
        if pr["trainee_id"]
    }
    reviewed_proposals = 0
    for tid in contributors:
        rv = {"reviewed_at": now, "engine": engine, "live": bool(use_live), "specialist_uid": clean}
        cur = conn.execute(
            "UPDATE academy_resource_proposals SET trainer_review_json = ?, updated_at = ? WHERE trainee_id = ? AND status = 'accepted'",
            (_dumps(rv), now, tid),
        )
        reviewed_proposals += int(cur.rowcount or 0)
    if commit:
        conn.commit()
    return {
        "specialist_uid": clean,
        "engine": engine,
        "live": bool(use_live),
        "live_authorized": bool(live_authorized),
        "source_count": len(sources),
        "verdict_count": len(review.get("verdicts") or []),
        "reviewed_proposals": reviewed_proposals,
        # Surface the capsule refresh outcome so the weekly scheduler's live-trainer
        # branch can count genuinely-refreshed capsules (it keys on result["changed"]).
        "changed": bool(capsule_result.get("changed")),
        "capsule_version": int(capsule_result.get("capsule_version") or 0),
        "live_enrichment_status": enrichment["live_enrichment_status"],
        "proof_gate": "PG-PROVIDER",
    }


def subscribe_trainee_to_specialist(
    conn: sqlite3.Connection, *, trainee_id: str, commit: bool = True
) -> str | None:
    """Subscribe a trainee to its Major's central specialist when one exists and is
    shared, so the trainee inherits the shared corpus (cross-captain reuse)."""
    trainee = get_academy_trainee(conn, trainee_id)
    if trainee is None:
        return None
    program = get_academy_program(conn, str(trainee.get("program_id") or ""))
    if program is None:
        return None
    specialist_uid, _ = specialist_uid_for_program(program)
    spec = conn.execute(
        "SELECT specialist_uid FROM academy_corpus_specialists "
        "WHERE specialist_uid = ? AND status = 'active' AND share_scope = 'redacted_public'",
        (specialist_uid,),
    ).fetchone()
    if spec is None:
        return None
    conn.execute(
        """
        INSERT OR IGNORE INTO academy_specialist_subscriptions (
          specialist_uid, trainee_id, user_id, subscribed_at, last_applied_capsule_version
        ) VALUES (?, ?, ?, ?, 0)
        """,
        (specialist_uid, str(trainee["trainee_id"]), str(trainee.get("user_id") or ""), _now()),
    )
    if commit:
        conn.commit()
    return specialist_uid


def read_central_specialist_sources(conn: sqlite3.Connection, *, trainee_id: str) -> list[dict[str, Any]]:
    """Active, shared central sources a trainee inherits via subscription."""
    clean = str(trainee_id or "").strip()
    if not clean:
        return []
    rows = conn.execute(
        """
        SELECT src.* FROM academy_sources src
        JOIN academy_specialist_sources link ON link.source_uid = src.source_uid
        JOIN academy_specialist_subscriptions sub ON sub.specialist_uid = link.specialist_uid
        WHERE sub.trainee_id = ? AND src.status = 'active' AND src.share_scope = 'redacted_public'
        ORDER BY src.first_seen_at, src.source_uid
        """,
        (clean,),
    ).fetchall()
    return [dict(row) for row in rows]


def _central_source_to_academy_source(row: Mapping[str, Any], *, stable_ts: str) -> Any:
    from arclink_academy_trainer import fake_academy_source

    lane = str(row.get("lane_id") or "").strip()
    meta = dict(_LANE_REQUIRED_META.get(lane, {}))
    meta.update({"central": True, "fresh": True, "freshness_days": int(row.get("freshness_days") or 7)})
    if lane == "skill_tool_catalog":
        meta["review_status"] = "reviewed"
        meta.pop("public_skill", None)
    notes = str(row.get("derived_notes") or "").strip()
    url = str(row.get("canonical_url") or "").strip() or ("https://central.invalid/" + str(row.get("source_uid") or "src"))
    citations = [str(c).strip() for c in (_loads(row.get("citations_json"), default=[]) or []) if str(c).strip()][:12]
    return fake_academy_source(
        source_id=str(row.get("source_uid") or "")[:120],
        lane_id=lane,
        title=str(row.get("title") or "Central source")[:180],
        origin_url=url[:500],
        retrieved_at=stable_ts,
        license_status="agent-reported",
        permission_status="captain-authorized",
        storage_policy="derived_summary",
        content=notes or f"Central derived notes for {row.get('title') or lane}.",
        citations=citations,
        metadata=meta,
        review_status="reviewed",
    )


def academy_specialist_public_card(
    conn: sqlite3.Connection, *, specialist_uid: str, allow_private: bool = False
) -> dict[str, Any] | None:
    """Redacted, cross-tenant-safe projection of a central specialist.

    Exposes role/topic/freshness/source-lane counts and capsule version; withholds
    contributor identity, private Captain steer, and raw notes (mirrors
    :func:`academy_graduate_card`).
    """
    clean = str(specialist_uid or "").strip()
    spec = conn.execute(
        "SELECT * FROM academy_corpus_specialists WHERE specialist_uid = ?", (clean,)
    ).fetchone()
    if spec is None:
        return None
    if not allow_private and str(spec["share_scope"] or "") != "redacted_public":
        return None
    lane_rows = conn.execute(
        """
        SELECT src.lane_id AS lane_id, COUNT(*) AS n
        FROM academy_sources src
        JOIN academy_specialist_sources link ON link.source_uid = src.source_uid
        WHERE link.specialist_uid = ? AND src.status = 'active' AND src.share_scope = 'redacted_public'
        GROUP BY src.lane_id ORDER BY src.lane_id
        """,
        (clean,),
    ).fetchall()
    lane_counts = {str(r["lane_id"]): int(r["n"]) for r in lane_rows}
    return {
        "specialist_uid": str(spec["specialist_uid"]),
        "program_id": str(spec["program_id"]),
        "role_title": str(spec["role_title"]),
        "topic_fingerprint": str(spec["topic_fingerprint"]),
        "capsule_version": int(spec["capsule_version"]),
        "captain_count": int(spec["captain_count"]),
        "share_scope": str(spec["share_scope"]),
        "status": str(spec["status"]),
        "source_count": sum(lane_counts.values()),
        "source_lane_counts": lane_counts,
        "last_enriched_at": str(spec["last_enriched_at"]),
    }


def list_central_specialists(conn: sqlite3.Connection, *, include_private: bool = False) -> list[dict[str, Any]]:
    """Browse the central, cross-captain specialist gallery (redacted cards)."""
    if include_private:
        rows = conn.execute(
            "SELECT specialist_uid FROM academy_corpus_specialists WHERE status = 'active' ORDER BY role_title"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT specialist_uid FROM academy_corpus_specialists "
            "WHERE status = 'active' AND share_scope = 'redacted_public' ORDER BY role_title"
        ).fetchall()
    cards = []
    for row in rows:
        card = academy_specialist_public_card(
            conn,
            specialist_uid=str(row["specialist_uid"]),
            allow_private=bool(include_private),
        )
        if card is not None:
            cards.append(card)
    return cards


def search_academy_reuse_candidates(
    conn: sqlite3.Connection,
    *,
    query: str = "",
    user_id: str = "",
    program_id: str = "",
    limit: int = 5,
) -> dict[str, Any]:
    """Search reusable Academy graduates/specialists before starting training.

    Returns redacted public central specialists plus the requesting Captain's own
    graduates. It never exposes another Captain's identity, steer, deployment id,
    or private organization material.
    """

    seed_default_academy_programs(conn)
    clean_query = str(query or "").strip()
    clean_user = str(user_id or "").strip()
    clean_program = _slug(str(program_id or ""))
    tokens = _search_tokens(" ".join([clean_query, clean_program]))
    programs = {p["program_id"]: p for p in list_academy_programs(conn)}
    candidates: list[dict[str, Any]] = []

    for card in list_central_specialists(conn):
        program = programs.get(str(card.get("program_id") or ""))
        haystack = " ".join(
            [
                str(card.get("role_title") or ""),
                str(card.get("topic_fingerprint") or ""),
                str(card.get("program_id") or ""),
                str((program or {}).get("label") or ""),
                str((program or {}).get("summary") or ""),
                " ".join((card.get("source_lane_counts") or {}).keys())
                if isinstance(card.get("source_lane_counts"), Mapping)
                else "",
            ]
        )
        score = _candidate_match_score(
            haystack,
            tokens=tokens,
            program_id=clean_program,
            candidate_program_id=str(card.get("program_id") or ""),
        )
        if score <= 0 and (tokens or clean_program):
            continue
        candidates.append(
            {
                "kind": "central_specialist",
                "score": score,
                "program_label": str((program or {}).get("label") or card.get("program_id") or ""),
                **card,
            }
        )

    if clean_user:
        gallery = browse_academy_graduates(conn, user_id=clean_user)
        for grad in gallery.get("graduates") or []:
            card = academy_graduate_card(grad)
            program = programs.get(str(card.get("program_id") or ""))
            haystack = " ".join(
                [
                    str(card.get("name") or ""),
                    str(card.get("program_id") or ""),
                    str(card.get("program_label") or ""),
                    str((program or {}).get("summary") or ""),
                    " ".join(card.get("source_lanes") or []),
                ]
            )
            score = _candidate_match_score(
                haystack,
                tokens=tokens,
                program_id=clean_program,
                candidate_program_id=str(card.get("program_id") or ""),
            )
            if score <= 0 and (tokens or clean_program):
                continue
            candidates.append({"kind": "captain_graduate", "score": score, **card})

    candidates.sort(
        key=lambda item: (
            -int(item.get("score") or 0),
            0 if item.get("kind") == "central_specialist" else 1,
            str(item.get("program_label") or item.get("role_title") or item.get("name") or ""),
        )
    )
    cap = max(1, min(20, int(limit or 5)))
    return {
        "query": clean_query,
        "program_id": clean_program,
        "candidates": candidates[:cap],
        "candidate_count": len(candidates),
        "privacy": "central candidates are redacted_public; Captain graduates are scoped to the requesting user",
        "cross_tenant_proof_gate": ACADEMY_CROSS_TENANT_PROOF_GATE,
    }


def _search_tokens(value: str) -> set[str]:
    return {
        token
        for token in re_split_tokens(value)
        if len(token) >= 3 and token not in {"agent", "academy", "training", "specialist"}
    }


def re_split_tokens(value: str) -> list[str]:
    import re

    return [item for item in re.split(r"[^a-z0-9]+", str(value or "").lower()) if item]


def _candidate_match_score(
    haystack: str,
    *,
    tokens: set[str],
    program_id: str,
    candidate_program_id: str,
) -> int:
    text = " ".join(re_split_tokens(haystack))
    score = 0
    if program_id and _slug(candidate_program_id) == program_id:
        score += 40
    for token in tokens:
        if token in text:
            score += 8
    return score


def _source_dedup_key(source: Any) -> str:
    cu = _canonical_url(getattr(source, "origin_url", ""))
    if cu and not any(host in cu for host in _PLACEHOLDER_HOSTS):
        return cu
    return "t:" + _slug(getattr(source, "title", ""))[:160]


def _resolve_trainee_sources(
    conn: sqlite3.Connection,
    trainee: Mapping[str, Any],
    program: Mapping[str, Any],
    stable: str,
) -> list[Any]:
    """Real corpus sources for a trainee: its OWN proposed resources PLUS the central
    shared specialist corpus it is subscribed to, deduped and governed-validated.

    Falls back to lane-valid local fixtures only when no real sources exist
    (fixture-only Majors / tests). This is what ends the write-only proposal
    dead-table and makes the corpus reflect real gathered research.
    """
    from arclink_academy_trainer import validate_academy_sources

    candidates: list[Any] = []
    seen_keys: set[str] = set()

    def _add(source: Any) -> None:
        key = _source_dedup_key(source)
        if key in seen_keys:
            return
        if validate_academy_sources([source]):
            return  # drop sources that don't pass governed validation
        seen_keys.add(key)
        candidates.append(source)

    for row in read_central_specialist_sources(conn, trainee_id=str(trainee["trainee_id"])):
        try:
            _add(_central_source_to_academy_source(row, stable_ts=stable))
        except Exception:  # noqa: BLE001
            continue
    for proposal in read_academy_proposals(
        conn, trainee_id=str(trainee["trainee_id"]), statuses=USABLE_PROPOSAL_STATUSES
    ):
        try:
            _add(_proposal_to_source(proposal, stable_ts=stable))
        except Exception:  # noqa: BLE001 - a malformed proposal is skipped, not fatal
            continue
    return candidates if candidates else _fixture_sources_for_program(program, stable)


def _compose_trainee_corpus(
    conn: sqlite3.Connection,
    trainee_id: str,
    *,
    sources: Sequence[Any] | None,
    now: str,
) -> dict[str, Any]:
    """Compose the governed corpus + application plan + review for a Trainee.

    Shared by curation (staging) and the apply action (intent extraction) so both
    derive from the exact same deterministic builders.
    """
    from arclink_academy_trainer import (
        build_academy_corpus,
        build_agent_application_plan,
        build_academy_review_status,
    )

    trainee = get_academy_trainee(conn, trainee_id)
    if trainee is None:
        raise ArcLinkAcademyProgramError(f"unknown academy trainee: {trainee_id}")
    program = get_academy_program(conn, str(trainee.get("program_id") or ""))
    if program is None:
        raise ArcLinkAcademyProgramError("academy trainee has no Major program")
    # Identity (manifest_id / plan_id) is derived from a STABLE per-trainee
    # timestamp, not wall-clock `now`, so the same (trainee, Major-state) always
    # produces the same staged ids. This lets the apply path validate the recomputed
    # corpus against the Captain-approved staged ids (a Major edit changes the
    # content -> changes the id -> apply fail-closes). `now` is used only for the
    # cosmetic review staged_at.
    stable = str(trainee.get("created_at") or trainee.get("enrolled_at") or now)
    src = list(sources) if sources is not None else _resolve_trainee_sources(conn, trainee, program, stable)
    steer = trainee.get("captain_steer") or {}
    focus = str(steer.get("focus") or "").strip() or str(program.get("topic_map") or program.get("label") or "")
    quality_floor = program.get("quality_floor")
    min_score = int(quality_floor) if quality_floor is not None else 70
    manifest = build_academy_corpus(
        role_id=str(program["program_id"]),
        role_title=str(program.get("label") or program["program_id"]),
        topic=focus,
        sources=src,
        min_source_score=min_score,
        created_at=stable,
    )
    plan = build_agent_application_plan(
        manifest,
        agent_id=str(trainee.get("deployment_id") or trainee["trainee_id"]),
        created_at=stable,
    )
    review = build_academy_review_status(manifest=manifest, application_plan=plan, staged_at=now)
    return {
        "trainee": trainee,
        "program": program,
        "manifest": manifest,
        "plan": plan,
        "review": review,
        "source_count": len(src),
        "manifest_id": str(getattr(manifest, "manifest_id", "") or review.get("manifest_id") or ""),
        "plan_id": _plan_id(plan),
    }


def curate_academy_trainee(
    conn: sqlite3.Connection,
    *,
    trainee_id: str,
    sources: Sequence[Any] | None = None,
    created_at: str | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    """Curate a Trainee's specialist corpus + curriculum + staged application plan.

    Composes the governed corpus/plan/review builders in arclink_academy_trainer.
    Uses lane-valid local fixtures when ``sources`` is not supplied (live source
    acquisition + LLM-Trainer synthesis replace those behind PG-PROVIDER). It is
    no-write with respect to the Agent: it stages the manifest/plan ids on the
    trainee; real Agent SOUL/skills/qmd/vault writes remain PG-HERMES gated and
    are performed only by the ``academy_apply`` action.

    Pass ``commit=False`` when the caller (e.g. ``end_academy_mode``) wraps the
    staging in a larger atomic transaction.
    """
    now = str(created_at or _now())
    composed = _compose_trainee_corpus(conn, trainee_id, sources=sources, now=now)
    manifest_id = composed["manifest_id"]
    plan_id = composed["plan_id"]
    conn.execute(
        "UPDATE academy_trainees SET staged_manifest_id = ?, staged_plan_id = ?, updated_at = ? WHERE trainee_id = ?",
        (manifest_id, plan_id, now, composed["trainee"]["trainee_id"]),
    )
    if commit:
        conn.commit()
    return {
        "trainee_id": composed["trainee"]["trainee_id"],
        "manifest_id": manifest_id,
        "plan_id": plan_id,
        "review": composed["review"],
        "source_count": composed["source_count"],
        "mutation_performed": False,
        "workspace_mutation_performed": False,
    }


def stage_academy_apply(
    conn: sqlite3.Connection,
    *,
    trainee_id: str,
    adapter_name: str = "fake",
    live_authorized: bool = False,
    actor: str = "",
    created_at: str | None = None,
    target_kind: str = "",
    target_id: str = "",
) -> dict[str, Any]:
    """Build the redacted result for the ``academy_apply`` action (fail-closed).

    Resolves a graduated Trainee's Captain-APPROVED staged application plan,
    extracts the additive imparting intents (SOUL overlay sections / approved
    skills / qmd memory seeds / vault files), and computes whether live Agent-home
    writes are enabled.

    Fail-closed gates (ALL must hold for ``writes_enabled``):
    - the Trainee is ``graduated`` with Academy Mode closed;
    - it carries a persisted ``staged_manifest_id``/``staged_plan_id`` (the
      Captain-approved contract);
    - the corpus recomputed from the CURRENT Major still matches those staged ids
      (a Major edited after graduation changes the content -> changes the id ->
      this fails closed as ``stale_requires_regraduation``, blocking an unreviewed
      write);
    - the action target (when supplied) is consistent with the Trainee's owner /
      deployment;
    - a live executor adapter is selected AND explicit PG-HERMES authorization
      (``live_authorized``) is present.

    When any gate fails the result is ``staged`` / ``failed_closed`` /
    ``stale_requires_regraduation`` / ``not_staged`` with ``writes_enabled=False`` --
    no SOUL/skill/qmd/vault file is written. The real imparting is performed by the
    PG-HERMES authorized Hermes-home seam (``bin/install-deployment-hermes-home.sh``).
    """
    now = str(created_at or _now())
    composed = _compose_trainee_corpus(conn, trainee_id, sources=None, now=now)
    trainee = composed["trainee"]
    if str(trainee.get("status") or "") != "graduated":
        raise ArcLinkAcademyProgramError("academy_apply requires a graduated trainee")
    if trainee.get("mode_open"):
        raise ArcLinkAcademyProgramError("academy_apply cannot run while Academy Mode is open")

    trainee_deployment = str(trainee.get("deployment_id") or "")
    trainee_user = str(trainee.get("user_id") or "")
    # Target/owner consistency: the action's target must match the Trainee it acts
    # on, so an apply cannot be bound to a deployment/owner other than the
    # Trainee's. Mirrors the academy_apply_preview / dns_repair guards.
    clean_target_kind = str(target_kind or "").strip()
    clean_target_id = str(target_id or "").strip()
    if clean_target_id:
        if clean_target_kind == "deployment" and trainee_deployment and clean_target_id != trainee_deployment:
            raise ArcLinkAcademyProgramError("academy_apply target deployment does not match the trainee")
        if clean_target_kind == "user" and trainee_user and clean_target_id != trainee_user:
            raise ArcLinkAcademyProgramError("academy_apply target user does not match the trainee owner")

    # The Captain-approved contract is the PERSISTED staged identity, not a fresh
    # recompute. Validate the recomputed corpus against it.
    staged_manifest = str(trainee.get("staged_manifest_id") or "")
    staged_plan = str(trainee.get("staged_plan_id") or "")
    recomputed_manifest = composed["manifest_id"]
    recomputed_plan = composed["plan_id"]
    contract_ok = bool(staged_manifest) and bool(staged_plan)
    contract_fresh = contract_ok and staged_manifest == recomputed_manifest and staged_plan == recomputed_plan

    plan = composed["plan"]
    plan_dict = plan.to_dict() if hasattr(plan, "to_dict") else dict(plan)
    intent_counts = {
        "soul_overlay_sections": len(plan_dict.get("soul_overlay_sections") or []),
        "approved_skill_intents": len(plan_dict.get("approved_skill_intents") or []),
        "qmd_memory_seed_intents": len(plan_dict.get("qmd_memory_seed_intents") or []),
        "vault_file_intents": len(plan_dict.get("vault_file_intents") or []),
    }
    review = composed["review"] if isinstance(composed["review"], Mapping) else {}
    review_ready = str(review.get("status") or "") in {"ready_for_review", "live_proof_pending"}
    adapter = str(adapter_name or "fake").strip().lower()
    live_adapter = adapter in {"local", "ssh", "live"}

    # Render the REPLACEABLE Academy SOUL section from the central specialist
    # capsule before deciding whether live writes are enabled. This is the
    # fail-closed Trainer gate: a live apply can only materialize a capsule that
    # the Trainer deep dive already stamped.
    academy_soul_section = ""
    academy_capsule_version = 0
    academy_specialist_uid = ""
    academy_trainer_reviewed_at = ""
    academy_trainer_live_status = ""
    trainer_review_ready = False
    program_row = composed["program"] if isinstance(composed.get("program"), Mapping) else {}
    try:
        spec_uid, _ = specialist_uid_for_program(program_row)
        academy_specialist_uid = spec_uid
        spec_row = conn.execute(
            "SELECT compressed_soul_capsule, capsule_version, role_title, enrichment_json FROM academy_corpus_specialists WHERE specialist_uid = ?",
            (spec_uid,),
        ).fetchone()
        if spec_row is not None and str(spec_row["compressed_soul_capsule"] or "").strip():
            from arclink_org_profile import render_academy_overlay

            enrichment = _loads(spec_row["enrichment_json"], default={})
            if isinstance(enrichment, Mapping):
                academy_trainer_reviewed_at = str(enrichment.get("reviewed_at") or "")
                academy_trainer_live_status = str(enrichment.get("live_enrichment_status") or "")
            academy_capsule_version = int(spec_row["capsule_version"] or 0)
            academy_soul_section = render_academy_overlay(
                role_title=str(spec_row["role_title"] or program_row.get("label") or ""),
                topic=str(program_row.get("topic_map") or ""),
                capsule_body=str(spec_row["compressed_soul_capsule"] or ""),
                capsule_version=academy_capsule_version,
                specialist_uid=spec_uid,
            )
            trainer_review_ready = bool(academy_soul_section.strip()) and bool(academy_trainer_reviewed_at)
    except Exception:  # noqa: BLE001 - a missing/empty capsule just omits the section
        academy_soul_section = ""

    if not academy_soul_section and review_ready:
        # Private/opt-out Academy graduates intentionally do not publish a central
        # redacted_public specialist. They still need a safe, replaceable Agent
        # capsule, but only when real Captain/Agent proposals exist; fixture-only
        # graduates remain staged until real training material is gathered.
        proposal_count = len(read_academy_proposals(conn, trainee_id=trainee["trainee_id"], statuses=USABLE_PROPOSAL_STATUSES))
        if proposal_count:
            private_capsule = _private_trainee_capsule_from_manifest(composed.get("manifest"), program=program_row)
            if private_capsule.strip():
                from arclink_org_profile import render_academy_overlay

                academy_specialist_uid = "private:" + str(trainee["trainee_id"])
                academy_capsule_version = 1
                academy_trainer_reviewed_at = str(trainee.get("graduated_at") or now)
                academy_trainer_live_status = "private_corpus_pending_pg_provider"
                academy_soul_section = render_academy_overlay(
                    role_title=str(program_row.get("label") or trainee.get("name") or ""),
                    topic=str(program_row.get("topic_map") or ""),
                    capsule_body=private_capsule,
                    capsule_version=academy_capsule_version,
                    specialist_uid=academy_specialist_uid,
                )
                trainer_review_ready = True

    if not contract_ok:
        status = "not_staged"
        writes_enabled = False
        note = "Trainee has no Captain-approved staged plan; re-graduate before applying. No Agent-home write."
    elif not contract_fresh:
        status = "stale_requires_regraduation"
        writes_enabled = False
        note = (
            "Staged plan no longer matches the current Major (the Major changed after graduation); "
            "re-graduate to re-review. Fail-closed: no Agent-home write."
        )
    elif live_adapter and live_authorized and review_ready and trainer_review_ready:
        status = "handoff_to_hermes_home"
        writes_enabled = True
        note = (
            "PG-HERMES authorized: Captain-approved staged contract handed to the Hermes-home installer "
            "(bin/install-deployment-hermes-home.sh) for the additive SOUL/skills/qmd/vault apply."
        )
    elif live_adapter and live_authorized and not trainer_review_ready:
        status = "failed_closed"
        writes_enabled = False
        note = "Academy Trainer deep-dive/capsule is not ready; no Agent-home write was performed."
    elif live_adapter and not live_authorized:
        status = "failed_closed"
        writes_enabled = False
        note = "Live adapter without PG-HERMES authorization; no Agent-home write was performed."
    else:
        status = "staged"
        writes_enabled = False
        note = "Record-only adapter; application plan staged, no Agent-home write was performed."

    return {
        "operation_kind": "academy_agent_apply",
        "trainee_id": trainee["trainee_id"],
        "program_id": str(trainee.get("program_id") or ""),
        "deployment_id": trainee_deployment,
        "user_id": trainee_user,
        # Report the Captain-APPROVED staged ids as the authoritative contract.
        "manifest_id": staged_manifest or recomputed_manifest,
        "plan_id": staged_plan or recomputed_plan,
        "recomputed_manifest_id": recomputed_manifest,
        "recomputed_plan_id": recomputed_plan,
        "contract_fresh": contract_fresh,
        "adapter": adapter,
        "status": status,
        "note": note,
        "writes_enabled": writes_enabled,
        "live_authorized": bool(live_authorized),
        "review_status": str(review.get("status") or ""),
        "intent_counts": intent_counts,
        "vault_file_intents": list(plan_dict.get("vault_file_intents") or []),
        "qmd_memory_seed_intents": list(plan_dict.get("qmd_memory_seed_intents") or []),
        "approved_skill_intents": list(plan_dict.get("approved_skill_intents") or []),
        "first_week_practice_tasks": list(plan_dict.get("first_week_practice_tasks") or []),
        "evaluation_tasks": list(plan_dict.get("evaluation_tasks") or []),
        # The replaceable Academy SOUL section (marker-bounded; merged additively by
        # the PG-HERMES installer, never overwriting the human SOUL body).
        "academy_soul_section": academy_soul_section,
        "academy_soul_marker": "ARCLINK ACADEMY SPECIALIST",
        "academy_capsule_version": academy_capsule_version,
        "academy_specialist_uid": academy_specialist_uid,
        "academy_trainer_review_ready": trainer_review_ready,
        "academy_trainer_reviewed_at": academy_trainer_reviewed_at,
        "academy_trainer_live_status": academy_trainer_live_status,
        "proof_gates": list(ACADEMY_APPLY_PROOF_GATES),
        "actor": str(actor or "").strip() or "system:action_worker",
        "mutation_performed": False,
        "workspace_mutation_performed": False,
        "filesystem_mutation_performed": False,
    }


def academy_continuing_education(
    conn: sqlite3.Connection,
    *,
    trainee_id: str,
    observed_sources: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build the weekly forward-maintenance plan for a graduate (no-write).

    Live source sweeps populate ``observed_sources`` behind PG-PROVIDER; the
    classification (unchanged/changed/stale/superseded/removed/tombstoned) and the
    agent_update gate are produced locally. Real SOUL/skill deltas are applied
    only by ``academy_apply`` and only when the gate says ready (PG-HERMES).
    """
    from arclink_academy_trainer import build_academy_corpus, build_continuing_education_plan

    trainee = get_academy_trainee(conn, trainee_id)
    if trainee is None:
        raise ArcLinkAcademyProgramError(f"unknown academy trainee: {trainee_id}")
    program = get_academy_program(conn, str(trainee.get("program_id") or ""))
    if program is None:
        raise ArcLinkAcademyProgramError("academy trainee has no Major program")
    if not bool(trainee.get("forward_maintained")) or not _trainee_has_real_training_sources(conn, trainee):
        return {
            "artifact_kind": "academy-weekly-continuing-education-review",
            "trainee_id": trainee["trainee_id"],
            "status": "needs_training_sources",
            "continuing_education_status": "blocked_until_real_training_sources",
            "source_refreshes": [],
            "mutation_performed": False,
            "no_write": True,
        }
    now = str(created_at or _now())
    # Sources use the stable per-trainee timestamp so the manifest is deterministic
    # and the weekly freshness window is measured against the original acquisition
    # time, not the run time (so staleness can actually fire).
    stable = str(trainee.get("created_at") or trainee.get("enrolled_at") or now)
    sources = _resolve_trainee_sources(conn, trainee, program, stable)
    quality_floor = program.get("quality_floor")
    manifest = build_academy_corpus(
        role_id=str(program["program_id"]),
        role_title=str(program.get("label") or program["program_id"]),
        topic=str(program.get("topic_map") or program.get("label") or ""),
        sources=sources,
        min_source_score=int(quality_floor) if quality_floor is not None else 70,
        created_at=stable,
    )
    # The trainer expects observed_sources keyed by source_id. Accept either a
    # mapping or a list of source dicts (each carrying its own source_id).
    observed_map: dict[str, Mapping[str, Any]] = {}
    if isinstance(observed_sources, Mapping):
        observed_map = {str(k): v for k, v in observed_sources.items()}
    else:
        for entry in observed_sources or []:
            sid = str(entry.get("source_id") or "").strip()
            if sid:
                observed_map[sid] = entry
    plan = build_continuing_education_plan(
        manifest,
        observed_sources=observed_map,
        checked_at=now,
    )
    payload = plan.to_dict() if hasattr(plan, "to_dict") else dict(plan)
    payload["trainee_id"] = trainee["trainee_id"]
    payload["mutation_performed"] = False
    return payload


def _validate_source_lanes(source_lanes: Sequence[str]) -> list[str]:
    lanes = [str(lane).strip() for lane in (source_lanes or ()) if str(lane).strip()]
    if not lanes:
        return []
    try:
        from arclink_academy_trainer import default_source_lane_registry

        known = set(default_source_lane_registry().keys())
    except Exception:  # noqa: BLE001 - if the registry can't load, accept the lanes as-is
        return lanes
    unknown = [lane for lane in lanes if lane not in known]
    if unknown:
        raise ArcLinkAcademyProgramError(f"unknown academy source lane(s): {', '.join(unknown)}")
    return lanes


def _program_public(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["source_lanes"] = _loads(data.pop("source_lanes_json", "[]"), default=[])
    data["required_skills"] = _loads(data.pop("required_skills_json", "[]"), default=[])
    return data


def _trainee_public(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["captain_steer"] = _loads(data.pop("captain_steer_json", "{}"), default={})
    data["mode_open"] = bool(data.get("mode_open"))
    data["forward_maintained"] = bool(data.get("forward_maintained"))
    return data


def _session_public(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["commit_summary"] = _loads(data.pop("commit_summary_json", "{}"), default={})
    return data


def _proposal_public(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["relevance"] = _loads(data.pop("relevance_json", "{}"), default={})
    data["citations"] = _loads(data.pop("citations_json", "[]"), default=[])
    data["trainer_review"] = _loads(data.pop("trainer_review_json", "{}"), default={})
    return data


def _slug(value: str) -> str:
    import re

    return re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")


def _now() -> str:
    from arclink_control import utc_now_iso

    return utc_now_iso()
