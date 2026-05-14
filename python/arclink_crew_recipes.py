#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
from string import Template
from typing import Any, Mapping, Protocol

from arclink_chutes import evaluate_chutes_deployment_boundary
from arclink_control import append_arclink_audit, append_arclink_event, utc_now_iso
from arclink_memory_synthesizer import UNSAFE_OUTPUT_PATTERNS


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
TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "CREW_RECIPE.md.tmpl"
MAX_PROVIDER_ATTEMPTS = 3


class ArcLinkCrewRecipeError(ValueError):
    pass


class CrewRecipeProvider(Protocol):
    def generate(self, *, prompt: str, model: str) -> str:
        ...


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


def _provider_context(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    deployments: list[Mapping[str, Any]],
    env: Mapping[str, str],
) -> dict[str, Any]:
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
    effective_env = dict(os.environ if env is None else env)
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
