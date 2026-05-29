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
    utc_now_iso,
)
from arclink_academy_programs import (
    academy_continuing_education,
    list_academy_trainees,
    seed_default_academy_programs,
)


DEFAULT_FORWARD_MAINTENANCE_LIMIT = 200


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
    # Explicit cap semantics: limit <= 0 means "process all eligible" (unbounded);
    # a positive limit caps this run and reports the remainder as deferred.
    n = int(limit)
    capped = eligible if n <= 0 else min(n, eligible)
    batch = graduates[:capped]
    deferred = eligible - len(batch)

    reviews: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for trainee in batch:
        trainee_id = str(trainee.get("trainee_id") or "")
        try:
            plan = academy_continuing_education(conn, trainee_id=trainee_id, observed_sources=None, created_at=now)
        except Exception as exc:  # noqa: BLE001 - one bad trainee must not abort the run
            errors.append({"trainee_id": trainee_id, "error": str(exc)[:200]})
            continue
        review = {
            "trainee_id": trainee_id,
            "deployment_id": str(trainee.get("deployment_id") or ""),
            "manifest_id": str(plan.get("manifest_id") or ""),
            "status": str(plan.get("status") or ""),
            "agent_update_status": str(plan.get("agent_update_status") or ""),
            "review_needed_count": int(plan.get("review_needed_count") or 0),
            "blocked_source_count": int(plan.get("blocked_source_count") or 0),
            "next_review_at": str(plan.get("next_review_at") or ""),
            "proof_gates": list(plan.get("proof_gates") or []),
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
    conn.commit()
    return {
        "status": "ok",
        "eligible": eligible,
        "processed": len(reviews),
        "deferred_to_next_run": deferred,
        "errors": errors,
        "reviews": reviews,
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
