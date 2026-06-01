#!/usr/bin/env python3
"""ArcLink Academy weekly forward-maintenance scheduler.

Iterates graduated, forward-maintained Trainees and runs the no-write weekly
continuing-education review for each (see arclink_academy_programs.
academy_continuing_education). It records a control-plane event + audit per
trainee so the dashboard / Operator Raven can surface the weekly status.

This job performs NO live source crawling and NO Agent SOUL/skills/qmd/vault
writes. Live source acquisition stays behind PG-PROVIDER and the real apply
stays behind the PG-HERMES `academy_apply` action; this scheduler only refreshes
the local review model on a weekly cadence.

CLI mirrors the action worker: `--once --json` for the docker job loop.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from arclink_control import (
    Config,
    append_arclink_audit,
    append_arclink_event,
    connect_db,
    queue_notification,
    utc_now_iso,
)
from arclink_academy_programs import (
    academy_continuing_education,
    list_academy_trainees,
    refresh_specialist_capsule,
    seed_default_academy_programs,
)


DEFAULT_FORWARD_MAINTENANCE_LIMIT = 200


def _academy_week_key(value: str) -> str:
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        iso = dt.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    except Exception:
        return str(value or "")[:10] or "unknown-week"


def _rotating_forward_maintenance_candidates(
    conn: sqlite3.Connection,
    graduates: list[dict[str, Any]],
    *,
    created_at: str,
) -> tuple[list[dict[str, Any]], int, dict[str, str]]:
    """Pick one subscribed trainee per shared specialist for this weekly turn."""

    by_id = {str(item.get("trainee_id") or ""): item for item in graduates if str(item.get("trainee_id") or "")}
    if not by_id:
        return [], 0, {}
    placeholders = ",".join("?" for _ in by_id)
    rows = conn.execute(
        f"""
        SELECT specialist_uid, trainee_id
        FROM academy_specialist_subscriptions
        WHERE trainee_id IN ({placeholders})
        ORDER BY specialist_uid, trainee_id
        """,
        tuple(by_id.keys()),
    ).fetchall()
    grouped: dict[str, list[str]] = {}
    grouped_trainees: set[str] = set()
    for row in rows:
        specialist_uid = str(row["specialist_uid"] or "")
        trainee_id = str(row["trainee_id"] or "")
        if not specialist_uid or trainee_id not in by_id:
            continue
        grouped.setdefault(specialist_uid, []).append(trainee_id)
        grouped_trainees.add(trainee_id)

    selected_ids: set[str] = set()
    rotation_for: dict[str, str] = {}
    deferred = 0
    week_key = _academy_week_key(created_at)
    for specialist_uid, trainee_ids in grouped.items():
        ordered = sorted(set(trainee_ids))
        if not ordered:
            continue
        digest = hashlib.sha256(f"{specialist_uid}:{week_key}".encode("utf-8")).hexdigest()
        chosen = ordered[int(digest[:8], 16) % len(ordered)]
        selected_ids.add(chosen)
        rotation_for[chosen] = specialist_uid
        deferred += max(0, len(ordered) - 1)

    for trainee_id in by_id:
        if trainee_id not in grouped_trainees:
            selected_ids.add(trainee_id)

    selected = [item for item in graduates if str(item.get("trainee_id") or "") in selected_ids]
    return selected, deferred, rotation_for


def run_academy_forward_maintenance(
    conn: sqlite3.Connection,
    *,
    env: Mapping[str, str] | None = None,
    limit: int = DEFAULT_FORWARD_MAINTENANCE_LIMIT,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Run the weekly no-write continuing-education review for graduates.

    Returns a redacted summary. ``limit`` bounds the number of trainees handled
    in a single run; if more are eligible the overflow count is reported (never
    silently dropped).
    """
    _ = dict(env or {})  # reserved for future PG-PROVIDER observed-source wiring
    now = str(created_at or utc_now_iso())
    seed_default_academy_programs(conn)
    graduates = [t for t in list_academy_trainees(conn, status="graduated") if t.get("forward_maintained")]
    eligible = len(graduates)
    rotation_candidates, rotation_deferred, rotation_for = _rotating_forward_maintenance_candidates(
        conn,
        graduates,
        created_at=now,
    )
    # Explicit cap semantics: limit <= 0 means "process all eligible" (unbounded);
    # a positive limit caps this run and reports the remainder as deferred.
    n = int(limit)
    capped = len(rotation_candidates) if n <= 0 else min(n, len(rotation_candidates))
    batch = rotation_candidates[:capped]
    deferred = rotation_deferred + (len(rotation_candidates) - len(batch))

    reviews: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    notify_targets: list[dict[str, str]] = []
    for trainee in batch:
        trainee_id = str(trainee.get("trainee_id") or "")
        try:
            plan = academy_continuing_education(conn, trainee_id=trainee_id, observed_sources=None, created_at=now)
        except Exception as exc:  # noqa: BLE001 - one bad trainee must not abort the run
            errors.append({"trainee_id": trainee_id, "error": str(exc)[:200]})
            continue
        review = {
            "trainee_id": trainee_id,
            "user_id": str(trainee.get("user_id") or ""),
            "deployment_id": str(trainee.get("deployment_id") or ""),
            "name": str(trainee.get("name") or ""),
            "manifest_id": str(plan.get("manifest_id") or ""),
            "status": str(plan.get("status") or ""),
            "agent_update_status": str(plan.get("agent_update_status") or ""),
            "review_needed_count": int(plan.get("review_needed_count") or 0),
            "blocked_source_count": int(plan.get("blocked_source_count") or 0),
            "next_review_at": str(plan.get("next_review_at") or ""),
            "proof_gates": list(plan.get("proof_gates") or []),
            "rotation_specialist_uid": rotation_for.get(trainee_id, ""),
            "rotation_week": _academy_week_key(now),
        }
        reviews.append(review)
        subject_id = review["deployment_id"] or trainee_id
        subject_kind = "deployment" if review["deployment_id"] else "user"
        append_arclink_event(
            conn,
            subject_kind=subject_kind,
            subject_id=subject_id,
            event_type="academy_forward_maintenance_recorded",
            metadata={**review, "no_write": True, "writes_enabled": False},
            commit=False,
        )
        append_arclink_audit(
            conn,
            action="academy_forward_maintenance_recorded",
            actor_id="system:academy_scheduler",
            target_kind=subject_kind,
            target_id=subject_id,
            reason="Weekly Academy continuing-education review recorded; no Agent write was performed",
            metadata={**review, "no_write": True, "writes_enabled": False},
            commit=False,
        )
        if review["user_id"]:
            notify_targets.append(review)

    # "Living academy": refresh the central specialist capsules each week (derived
    # notes only; the live LLM Trainer enrichment + Agent-side observed-source sweep
    # layer on top behind PG-PROVIDER) and bump only when content actually changed.
    capsules_refreshed = 0
    specialist_uids = [
        str(row["specialist_uid"])
        for row in conn.execute(
            "SELECT DISTINCT specialist_uid FROM academy_corpus_specialists "
            "WHERE status = 'active' AND share_scope = 'redacted_public'"
        ).fetchall()
    ]
    for specialist_uid in specialist_uids:
        try:
            result = refresh_specialist_capsule(
                conn, specialist_uid=specialist_uid, actor="system:academy_scheduler",
                only_if_changed=True, commit=False,
            )
            if result.get("changed"):
                capsules_refreshed += 1
        except Exception as exc:  # noqa: BLE001 - one bad specialist must not abort the run
            errors.append({"specialist_uid": specialist_uid, "error": str(exc)[:200]})
    conn.commit()

    # Notify each Captain of their weekly review (vision: "notifies the Captain").
    # queue_notification commits per row, so it runs AFTER the batch commit above.
    notified = 0
    for review in notify_targets:
        try:
            label = review["name"] or review["deployment_id"] or review["trainee_id"]
            queue_notification(
                conn,
                target_kind="user",
                target_id=review["user_id"],
                channel_kind="academy",
                message=(
                    f"Academy weekly review for {label}: "
                    f"{review['review_needed_count']} source(s) to review, "
                    f"{review['blocked_source_count']} blocked. Next review {review['next_review_at'] or 'TBD'}."
                ),
                extra={
                    "kind": "academy_forward_maintenance",
                    "trainee_id": review["trainee_id"],
                    "deployment_id": review["deployment_id"],
                    "rotation_specialist_uid": review.get("rotation_specialist_uid", ""),
                    "rotation_week": review.get("rotation_week", ""),
                    "review_needed_count": review["review_needed_count"],
                    "blocked_source_count": review["blocked_source_count"],
                    "agent_update_status": review["agent_update_status"],
                    "next_review_at": review["next_review_at"],
                },
            )
            notified += 1
        except Exception as exc:  # noqa: BLE001 - notification failure must not abort the run
            errors.append({"trainee_id": review.get("trainee_id", ""), "error": f"notify: {str(exc)[:160]}"})
    return {
        "status": "ok",
        "eligible": eligible,
        "processed": len(reviews),
        "deferred_to_next_run": deferred,
        "shared_rotation_deferred": rotation_deferred,
        "errors": errors,
        "reviews": reviews,
        "captains_notified": notified,
        "central_capsules_refreshed": capsules_refreshed,
        "no_write": True,
        "writes_enabled": False,
        "proof_gates": ["PG-PROVIDER", "PG-HERMES"],
    }


def _db_connect(path: str) -> sqlite3.Connection:
    db_path = str(path or os.environ.get("ARCLINK_DB_PATH") or "/home/arclink/arclink/arclink-priv/state/arclink-control.sqlite3")
    cfg = Config.from_env()
    cfg = replace(cfg, db_path=Path(db_path).resolve(), state_dir=Path(db_path).resolve().parent)
    return connect_db(cfg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the weekly ArcLink Academy forward-maintenance review.")
    parser.add_argument("--db", default=os.environ.get("ARCLINK_DB_PATH", ""))
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.environ.get("ARCLINK_ACADEMY_CE_LIMIT", str(DEFAULT_FORWARD_MAINTENANCE_LIMIT))),
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    with _db_connect(args.db) as conn:
        payload = run_academy_forward_maintenance(conn, env=os.environ, limit=args.limit)
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(
            f"Academy forward-maintenance: processed {payload['processed']}/{payload['eligible']} graduate(s), "
            f"deferred {payload['deferred_to_next_run']}, errors {len(payload['errors'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
