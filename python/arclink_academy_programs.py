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
import secrets
import sqlite3
from typing import Any, Mapping, Sequence


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
    """Idempotently upsert the default Majors catalog. Returns the catalog size."""
    count = 0
    for program in _default_programs():
        upsert_academy_program(conn, origin="catalog", **program)
        count += 1
    return count


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
            int(quality_floor),
            _dumps(skills),
            str(origin or "custom").strip() or "custom",
            created_at,
            now,
        ),
    )
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
            str(opened_via or "command").strip() or "command",
            now,
        ),
    )
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


def end_academy_mode(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    actor: str,
    graduate: bool = True,
    staged_manifest_id: str = "",
    staged_plan_id: str = "",
    commit_summary: Mapping[str, Any] | None = None,
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
    summary.setdefault("graduated", bool(graduate))
    summary.setdefault("apply_status", "staged" if graduate else "cancelled")
    summary.setdefault("apply_proof_gates", list(ACADEMY_APPLY_PROOF_GATES))
    summary.setdefault(
        "apply_note",
        "Staged at control plane; real SOUL/skills/qmd/vault writes remain PG-HERMES gated.",
    )
    summary.setdefault("forward_maintenance", "weekly continuing education armed" if graduate else "not armed")
    summary.setdefault("actor", str(actor or "").strip() or "captain")
    now = _now()
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
            (
                str(staged_manifest_id or trainee.get("staged_manifest_id") or "").strip(),
                str(staged_plan_id or trainee.get("staged_plan_id") or "").strip(),
                now,
                now,
                trainee["trainee_id"],
            ),
        )
    else:
        conn.execute(
            "UPDATE academy_trainees SET status = 'enrolled', mode_open = 0, updated_at = ? WHERE trainee_id = ?",
            (now, trainee["trainee_id"]),
        )
    conn.commit()
    return {
        "session": _session_public(conn.execute(
            "SELECT * FROM academy_mode_sessions WHERE session_id = ?", (session["session_id"],)
        ).fetchone()),
        "trainee": get_academy_trainee(conn, trainee["trainee_id"]),
        "graduated": bool(graduate),
        "mutation_performed": False,
        "workspace_mutation_performed": False,
    }


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
    """Fast path: clone a graduate's Major + staged corpus into a new graduated Trainee."""
    source = get_academy_trainee(conn, source_trainee_id)
    if source is None or source.get("status") != "graduated":
        raise ArcLinkAcademyProgramError("can only adopt a graduated academy trainee")
    clean_user = str(user_id or "").strip()
    clean_deployment = str(deployment_id or "").strip()
    if not clean_user or not clean_deployment:
        raise ArcLinkAcademyProgramError("adopt requires user_id and deployment_id")
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


def _slug(value: str) -> str:
    import re

    return re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")


def _now() -> str:
    from arclink_control import utc_now_iso

    return utc_now_iso()
