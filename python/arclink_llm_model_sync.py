#!/usr/bin/env python3
"""Periodic LLM router model-catalog sync worker.

Keeps the ArcLink LLM router's effective allow-list in sync with the Chutes
public catalog's confidential-compute (``-TEE``) models.

Design
------
The router's per-request effective allow-list is resolved from the
``arclink_model_catalog`` table (active Chutes ``-TEE`` rows), with the static
``ARCLINK_LLM_ROUTER_ALLOWED_MODELS`` env list as a never-empty safety
fallback. This worker refreshes that table; the router picks the new set up on
the very next request without a restart (it opens a DB connection per request).

Failure handling: if the Chutes fetch fails, returns no ``-TEE`` models,
returns fewer than ``ARCLINK_LLM_ROUTER_MODEL_SYNC_MIN_MODELS`` (default 8,
floored so a partial response can never be accepted), or drops suspiciously far
below the last-known active ``-TEE`` count, the existing catalog is left
untouched (last-known-good is preserved -- the allow-list is *never* emptied)
and the Operator is notified once (deduped on the audit-log outcome state, so a
sustained outage does not spam). A subsequent successful sync clears the alert
state so the next failure notifies again -- and this re-arm holds even if a
prior notice never delivered.

Run as a oneshot (``--once``) under ``bin/docker-job-loop.sh`` on an hourly
cadence, mirroring the other periodic ArcLink jobs.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from typing import Any, Mapping, Sequence

from arclink_chutes import ChutesCatalogClient, ChutesCatalogError
from arclink_control import (
    Config,
    append_arclink_audit,
    connect_db,
    ensure_schema,
    queue_notification,
    upsert_model_catalog,
    utc_now_iso,
)
from arclink_secrets_regex import redact_then_truncate

TEE_SUFFIX = "-TEE"
PROVIDER = "chutes"

# Audit/event action used to record sync outcomes; also the dedup anchor for
# the Operator failure notification.
AUDIT_ACTION_OK = "llm_router:model_sync_ok"
AUDIT_ACTION_FAILED = "llm_router:model_sync_failed"

OPERATOR_NOTICE_KEY = "llm_router_model_sync_failed"

# Absolute hard floor below which a -TEE catalog response is considered
# untrustworthy regardless of any configured minimum -- a real Chutes outage /
# partial response is a FAILED sync (last-known-good kept), never accepted.
# ``ARCLINK_LLM_ROUTER_MODEL_SYNC_MIN_MODELS`` is the operator-tunable floor that
# can only RAISE this (the compose default sets it to 8); the proportional-drop
# guard below catches drops that still clear the floor.
DEFAULT_MODEL_SYNC_MIN_MODELS = 2
# H1 fix: expected-minimum for the FIRST authoritative sync (when there is no
# last-known active -TEE baseline, so the proportional-drop guard below cannot
# fire). The very first destructive sync writes the baseline every later guard
# trusts, so it must itself look like a real, full catalog (the Chutes -TEE set
# is well into the double digits) -- not a degraded partial that happens to clear
# the lower per-request floor. Independent of (and higher than) the per-request
# floor so it bites even when the operator floor is left at its minimum.
DEFAULT_FIRST_SYNC_MIN_MODELS = 8
# If the fetched -TEE count drops to <= this fraction of the last-known active
# -TEE count, treat it as a suspicious partial response and FAIL the sync.
SUSPICIOUS_DROP_FRACTION = 0.5


def _env_text(source: Mapping[str, str], *keys: str, default: str = "") -> str:
    for key in keys:
        value = str(source.get(key) or "").strip()
        if value:
            return value
    return default


def _env_int(source: Mapping[str, str], key: str, default: int) -> int:
    try:
        return int(str(source.get(key) or default).strip())
    except (TypeError, ValueError):
        return default


def filter_tee_models(models: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only confidential-compute (``-TEE``) models from a catalog map."""
    return {
        model_id: model
        for model_id, model in models.items()
        if str(model_id or "").strip().endswith(TEE_SUFFIX)
    }


def fetch_tee_models(
    env: Mapping[str, str],
    *,
    http_client: Any | None = None,
) -> dict[str, Any]:
    """Fetch the Chutes catalog and return only the ``-TEE`` models.

    Raises ChutesCatalogError / OSError on transport failures; callers must
    treat any exception as a failed sync (and keep last-known-good).
    """
    base_url = _env_text(
        env,
        "ARCLINK_LLM_ROUTER_CHUTES_BASE_URL",
        default="https://llm.chutes.ai/v1",
    ).rstrip("/")
    api_key = _env_text(env, "ARCLINK_LLM_ROUTER_CHUTES_API_KEY")
    strategy = _env_text(
        env,
        "ARCLINK_LLM_ROUTER_MODEL_CATALOG_AUTH_STRATEGY",
        default="bearer",
    ).lower()
    if strategy not in {"bearer", "x-api-key", "none"}:
        strategy = "bearer"
    catalog = ChutesCatalogClient(http_client, base_url=base_url)
    models = catalog.list_models(
        api_key="" if strategy == "none" else api_key,
        auth_strategy="x-api-key" if strategy == "x-api-key" else "bearer",
    )
    return filter_tee_models(models)


def _operator_target(cfg: Config) -> tuple[str, str]:
    """Resolve the *real* Operator notification target from the loaded Config.

    Mirrors the canonical operator-alert path (health-watch's ``_operator_target``
    in ``arclink_health_watch.py``, which reads ``cfg.operator_notify_platform`` /
    ``cfg.operator_notify_channel_id``). The delivery router branches on
    ``target_kind == "operator"`` and re-derives the platform from ``channel_kind``
    (telegram/discord/tui-only); ``target_id`` must be the real operator chat/
    channel id.

    CRITICAL: this MUST come from ``Config`` (loaded via ``ARCLINK_CONFIG_FILE``),
    NOT from the worker's raw ``os.environ``. The compose ``llm-model-sync`` service
    runs Python directly and the entrypoint exports only ``ARCLINK_CONFIG_FILE`` --
    it does NOT source ``docker.env`` -- so ``OPERATOR_NOTIFY_CHANNEL_PLATFORM`` /
    ``OPERATOR_NOTIFY_CHANNEL_ID`` are absent from ``os.environ`` at runtime. Reading
    them from the environment fell back to ``tui-only`` and delivery never reached the
    real Telegram/Discord operator. ``Config.from_env()`` reads the config file, which
    DOES carry those operator values, so the notice routes to the real chat.
    """
    channel_kind = str(cfg.operator_notify_platform or "tui-only").strip().lower() or "tui-only"
    target_id = str(
        cfg.operator_notify_channel_id or channel_kind or "operator"
    ).strip() or "operator"
    return target_id, channel_kind


def _failure_already_notified(conn: sqlite3.Connection) -> bool:
    """True when the Operator was already notified for the current outage.

    Dedup is anchored on the audit-log success/failure state, NOT on the
    presence of an undelivered notification row. Basing it on undelivered rows
    means a notice that never delivers lingers forever and blocks every future
    notice even after a later success re-arms the alert. With audit state, one
    outage yields exactly one notice and a later successful sync re-arms cleanly.
    """
    last = conn.execute(
        """
        SELECT action
        FROM arclink_audit_log
        WHERE action IN (?, ?)
        ORDER BY created_at DESC, rowid DESC
        LIMIT 1
        """,
        (AUDIT_ACTION_OK, AUDIT_ACTION_FAILED),
    ).fetchone()
    if last is None:
        return False
    return str(last["action"]) == AUDIT_ACTION_FAILED


def _notify_operator_failure(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    reason: str,
) -> int:
    if _failure_already_notified(conn):
        return 0
    target_id, channel_kind = _operator_target(cfg)
    message = (
        "ArcLink LLM model sync FAILED. The router allow-list is frozen at the "
        f"last-known-good set (not emptied). Reason: {reason}"
    )
    notification_id = queue_notification(
        conn,
        target_kind="operator",
        target_id=target_id,
        channel_kind=channel_kind,
        message=message,
        extra={"notice_key": OPERATOR_NOTICE_KEY, "reason": reason},
        commit=False,
    )
    return int(notification_id)


def _active_tee_count(conn: sqlite3.Connection) -> int:
    """Last-known-good count of active ``-TEE`` rows in the catalog."""
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM arclink_model_catalog
            WHERE provider = ? AND status = 'active' AND model_id LIKE '%-TEE'
            """,
            (PROVIDER,),
        ).fetchone()
    except sqlite3.Error:
        return 0
    if row is None:
        return 0
    return int(row["count"] if isinstance(row, sqlite3.Row) else row[0])


def sync_llm_models(
    conn: sqlite3.Connection,
    env: Mapping[str, str],
    *,
    cfg: Config | None = None,
    http_client: Any | None = None,
) -> dict[str, Any]:
    """Run one sync pass. Never empties the allow-list on failure.

    ``env`` supplies the Chutes fetch settings and the operator-tunable minimum
    (these are literal env vars on the compose service). ``cfg`` supplies the
    *operator notification target* -- it MUST come from ``Config`` (loaded via
    ``ARCLINK_CONFIG_FILE``), because the operator vars live in the config file,
    not in the worker's raw process environment. When ``cfg`` is omitted it is
    loaded from the environment, matching the production ``main()`` path.

    Returns a JSON-serialisable status dict.
    """
    if cfg is None:
        cfg = Config.from_env()
    # Hard minimum (operator-tunable) with a sane default floor: a partial Chutes
    # response (e.g. 2 of 13 -TEE) must NOT be accepted as success -- accepting it
    # would mark the other models unavailable with no failure notice.
    min_models = max(
        DEFAULT_MODEL_SYNC_MIN_MODELS,
        _env_int(env, "ARCLINK_LLM_ROUTER_MODEL_SYNC_MIN_MODELS", DEFAULT_MODEL_SYNC_MIN_MODELS),
    )
    now = utc_now_iso()

    def _fail(reason: str) -> dict[str, Any]:
        notification_id = _notify_operator_failure(conn, cfg, reason=reason)
        append_arclink_audit(
            conn,
            action=AUDIT_ACTION_FAILED,
            target_kind="llm-router",
            target_id=PROVIDER,
            reason=redact_then_truncate(reason, limit=300),
            metadata={"reason": reason, "notification_id": notification_id},
            commit=False,
        )
        conn.commit()
        return {
            "status": "failed",
            "reason": reason,
            "notified": bool(notification_id),
            "notification_id": notification_id,
            "model_count": 0,
            "kept_last_known_good": True,
            "synced_at": now,
        }

    try:
        tee_models = fetch_tee_models(env, http_client=http_client)
    except (ChutesCatalogError, OSError, ValueError) as exc:
        return _fail(f"fetch_error: {redact_then_truncate(str(exc), limit=200)}")

    fetched = len(tee_models)
    if fetched < min_models:
        return _fail(
            f"too_few_models: got {fetched} -TEE models, require >= {min_models}"
        )

    last_active = _active_tee_count(conn)
    if last_active <= 0:
        # H1 first/empty-baseline guard: the proportional-drop guard below needs
        # a last-known active count to compare against. With no baseline (cold
        # start or after every row went unavailable) it cannot fire, so a degraded
        # partial response would otherwise become the authoritative baseline that
        # every later sync trusts. Require the first authoritative sync to look
        # like a real, full catalog before it is allowed to write that baseline.
        first_sync_min = max(
            min_models,
            _env_int(
                env,
                "ARCLINK_LLM_ROUTER_MODEL_SYNC_FIRST_SYNC_MIN_MODELS",
                DEFAULT_FIRST_SYNC_MIN_MODELS,
            ),
        )
        if fetched < first_sync_min:
            return _fail(
                f"first_sync_too_few: got {fetched} -TEE models on an empty baseline, "
                f"require >= {first_sync_min} before a destructive authoritative sync; "
                "keeping last-known-good"
            )
    # Proportional-drop sanity guard: even above the hard floor, a sudden large
    # drop versus the last-known active set is a strong signal of a partial /
    # degraded Chutes response. Treat it as a FAILED sync so we keep
    # last-known-good and notify rather than silently shrinking the allow-list.
    elif fetched <= int(last_active * SUSPICIOUS_DROP_FRACTION):
        return _fail(
            f"suspicious_drop: got {fetched} -TEE models vs last-known {last_active} active "
            f"(<= {int(SUSPICIOUS_DROP_FRACTION * 100)}% of current); keeping last-known-good"
        )

    # Success path: refresh the catalog. mark_missing_unavailable flips any
    # previously-active -TEE model that disappeared to 'unavailable', so it
    # drops out of the router's effective allow-list. Models that are still
    # present stay 'active'.
    # M4: commit=False folds the catalog refresh and the OK-audit into a single
    # transaction so a crash between them cannot leave a refreshed catalog with no
    # matching audit row (which would desync the failure-dedup / last-known state).
    rows = upsert_model_catalog(
        conn,
        provider=PROVIDER,
        models=tee_models,
        mark_missing_unavailable=True,
        commit=False,
    )
    append_arclink_audit(
        conn,
        action=AUDIT_ACTION_OK,
        target_kind="llm-router",
        target_id=PROVIDER,
        reason=f"synced {len(rows)} -TEE models",
        metadata={"model_count": len(rows), "model_ids": sorted(tee_models)},
        commit=False,
    )
    conn.commit()
    return {
        "status": "ok",
        "model_count": len(rows),
        "model_ids": sorted(tee_models),
        "synced_at": now,
        "kept_last_known_good": False,
    }


def _load_conn() -> tuple[sqlite3.Connection, Config]:
    cfg = Config.from_env()
    conn = connect_db(cfg)
    ensure_schema(conn, cfg)
    return conn, cfg


def main(argv: Sequence[str] | None = None) -> int:
    import os

    parser = argparse.ArgumentParser(prog="arclink-llm-model-sync")
    parser.add_argument("--once", action="store_true", help="run one sync pass")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        conn, cfg = _load_conn()
        try:
            # Operator target comes from the loaded Config (ARCLINK_CONFIG_FILE),
            # not raw os.environ -- the operator vars live in the config file the
            # service exports, not as literal compose env vars. The Chutes fetch
            # settings and the model-sync minimum DO come from os.environ.
            result = sync_llm_models(conn, os.environ, cfg=cfg)
        finally:
            conn.close()
        if args.json:
            print(json.dumps(result, sort_keys=True))
        else:
            print(
                f"llm_model_sync status={result['status']} "
                f"models={result.get('model_count', 0)}"
            )
        # A failed sync is a soft failure: we kept last-known-good and notified
        # the Operator. Return non-zero so the job loop surfaces it in status.
        return 0 if result.get("status") == "ok" else 1
    except Exception as exc:
        print(redact_then_truncate(str(exc), limit=300), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
