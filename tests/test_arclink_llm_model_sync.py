#!/usr/bin/env python3
from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Mapping

from arclink_test_helpers import expect, load_module, memory_db

# The operator notify target mirrors production: the failure notice must
# resolve to the REAL operator chat (OPERATOR_NOTIFY_CHANNEL_ID) on the
# configured platform -- never a bogus "llm-router:model-sync" chat id.
OPERATOR_PLATFORM = "telegram"
OPERATOR_CHAT_ID = "tg:operator-chat-7777"

CHUTES_ENV = {
    "ARCLINK_LLM_ROUTER_CHUTES_BASE_URL": "https://llm.chutes.ai/v1",
    "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "test-key",
    "ARCLINK_LLM_ROUTER_MODEL_CATALOG_AUTH_STRATEGY": "bearer",
    "OPERATOR_NOTIFY_CHANNEL_PLATFORM": OPERATOR_PLATFORM,
    "OPERATOR_NOTIFY_CHANNEL_ID": OPERATOR_CHAT_ID,
}


def operator_cfg(
    control,
    *,
    platform: str = OPERATOR_PLATFORM,
    channel_id: str = OPERATOR_CHAT_ID,
):
    """Build a real Config whose operator target carries the operator chat.

    Production resolves the operator target from ``Config`` (loaded via
    ``ARCLINK_CONFIG_FILE``), NOT from the worker's raw process environment -- the
    operator vars live in the config file the compose service exports, not as
    literal compose env vars. We mirror that here by writing the operator vars to a
    temp config file and loading them through ``Config.from_env()``, exactly as the
    deployed ``llm-model-sync`` service does. This is what proves the fix: a target
    sourced from the env (where the operator vars are absent at runtime) would fall
    back to ``tui-only``; sourced from Config it resolves the real platform + chat.
    """
    # mkdtemp (not TemporaryDirectory) so the file persists for the test process;
    # Config is a frozen dataclass, so we cannot stash a cleanup handle on it.
    config_dir = Path(tempfile.mkdtemp(prefix="arclink-operator-cfg-"))
    config_path = config_dir / "operator.env"
    lines = [
        f"OPERATOR_NOTIFY_CHANNEL_PLATFORM={platform}",
        f"OPERATOR_NOTIFY_CHANNEL_ID={channel_id}",
    ]
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    prior = os.environ.get("ARCLINK_CONFIG_FILE")
    os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
    try:
        return control.Config.from_env()
    finally:
        if prior is None:
            os.environ.pop("ARCLINK_CONFIG_FILE", None)
        else:
            os.environ["ARCLINK_CONFIG_FILE"] = prior


class FixtureCatalogHttpClient:
    """Returns a fixed OpenAI-style /models payload."""

    def __init__(self, model_ids: list[str]) -> None:
        self.payload = {"data": [{"id": model_id} for model_id in model_ids]}
        self.headers: Mapping[str, str] = {}

    def get_json(self, path: str, *, headers: Mapping[str, str] | None = None) -> Mapping[str, Any]:
        expect(path == "/models", path)
        self.headers = dict(headers or {})
        return self.payload


class FailingCatalogHttpClient:
    def get_json(self, path: str, *, headers: Mapping[str, str] | None = None) -> Mapping[str, Any]:
        raise OSError("simulated chutes transport failure")


def _active_tee_models(control, conn) -> list[str]:
    rows = conn.execute(
        "SELECT model_id FROM arclink_model_catalog WHERE provider='chutes' AND status='active' ORDER BY model_id"
    ).fetchall()
    return [str(row["model_id"]) for row in rows]


def _undelivered_operator_notices(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM notification_outbox
        WHERE delivered_at IS NULL AND target_kind='operator' AND target_id=?
        ORDER BY id
        """,
        (OPERATOR_CHAT_ID,),
    ).fetchall()
    return [dict(row) for row in rows]


def test_filter_tee_models_keeps_only_tee_suffix() -> None:
    sync = load_module("arclink_llm_model_sync.py", "arclink_llm_model_sync_filter_test")
    models = {
        "moonshotai/Kimi-K2.6-TEE": {"model_id": "moonshotai/Kimi-K2.6-TEE"},
        "zai-org/GLM-5.1-TEE": {"model_id": "zai-org/GLM-5.1-TEE"},
        "openai/gpt-plain": {"model_id": "openai/gpt-plain"},
        "model-router": {"model_id": "model-router"},
    }
    filtered = sync.filter_tee_models(models)
    expect(set(filtered) == {"moonshotai/Kimi-K2.6-TEE", "zai-org/GLM-5.1-TEE"}, str(set(filtered)))
    print("PASS test_filter_tee_models_keeps_only_tee_suffix")


def test_fetch_tee_models_filters_catalog() -> None:
    sync = load_module("arclink_llm_model_sync.py", "arclink_llm_model_sync_fetch_test")
    client = FixtureCatalogHttpClient(
        ["moonshotai/Kimi-K2.6-TEE", "zai-org/GLM-5.1-TEE", "vendor/plain-model"]
    )
    models = sync.fetch_tee_models(CHUTES_ENV, http_client=client)
    expect(set(models) == {"moonshotai/Kimi-K2.6-TEE", "zai-org/GLM-5.1-TEE"}, str(set(models)))
    # Bearer auth header is set per env strategy.
    expect(client.headers.get("Authorization") == "Bearer test-key", str(client.headers))
    print("PASS test_fetch_tee_models_filters_catalog")


def test_operator_target_resolves_real_chat_from_config_not_environ() -> None:
    # FIX A: the deployed llm-model-sync service runs Python directly; the
    # entrypoint exports only ARCLINK_CONFIG_FILE and does NOT source docker.env,
    # so OPERATOR_NOTIFY_* are absent from the worker's os.environ at runtime.
    # Resolving the operator target from os.environ therefore fell back to
    # 'tui-only' and the Operator never got a real Telegram/Discord notice. The
    # fix resolves the target from the loaded Config (which reads the config file
    # that DOES carry the operator vars), exactly like health-watch.
    control = load_module("arclink_control.py", "arclink_control_operator_target_test")
    sync = load_module("arclink_llm_model_sync.py", "arclink_llm_model_sync_operator_target_test")

    # Config built from a config file carrying the operator vars (production shape).
    cfg = operator_cfg(control, platform="telegram", channel_id="tg:operator-chat-7777")
    target_id, channel_kind = sync._operator_target(cfg)
    expect(channel_kind == "telegram", channel_kind)
    expect(target_id == "tg:operator-chat-7777", target_id)
    expect(channel_kind != "tui-only", channel_kind)
    expect(target_id != "operator", target_id)

    # A Discord operator resolves to the discord channel + numeric id.
    discord_cfg = operator_cfg(control, platform="discord", channel_id="123456789012345678")
    d_target, d_kind = sync._operator_target(discord_cfg)
    expect(d_kind == "discord", d_kind)
    expect(d_target == "123456789012345678", d_target)

    # End-to-end: a failed sync resolves the real operator notice target from cfg.
    conn = memory_db(control)
    failed = sync.sync_llm_models(conn, CHUTES_ENV, cfg=cfg, http_client=FailingCatalogHttpClient())
    expect(failed["status"] == "failed", str(failed))
    expect(failed["notified"] is True, str(failed))
    notices = _undelivered_operator_notices(conn)
    expect(len(notices) == 1, str(notices))
    expect(notices[0]["channel_kind"] == "telegram", str(notices[0]))
    expect(notices[0]["target_id"] == "tg:operator-chat-7777", str(notices[0]))
    expect(notices[0]["channel_kind"] != "tui-only", str(notices[0]))
    print("PASS test_operator_target_resolves_real_chat_from_config_not_environ")


def test_sync_success_populates_catalog() -> None:
    control = load_module("arclink_control.py", "arclink_control_model_sync_success_test")
    sync = load_module("arclink_llm_model_sync.py", "arclink_llm_model_sync_success_test")
    conn = memory_db(control)
    cfg = operator_cfg(control)
    client = FixtureCatalogHttpClient(["moonshotai/Kimi-K2.6-TEE", "zai-org/GLM-5.1-TEE"])

    result = sync.sync_llm_models(conn, CHUTES_ENV, cfg=cfg, http_client=client)
    expect(result["status"] == "ok", str(result))
    expect(result["model_count"] == 2, str(result))
    expect(_active_tee_models(control, conn) == ["moonshotai/Kimi-K2.6-TEE", "zai-org/GLM-5.1-TEE"], str(result))
    expect(_undelivered_operator_notices(conn) == [], "success must not queue an operator notice")
    print("PASS test_sync_success_populates_catalog")


def test_failure_keeps_last_known_good_and_notifies_operator() -> None:
    control = load_module("arclink_control.py", "arclink_control_model_sync_fail_test")
    sync = load_module("arclink_llm_model_sync.py", "arclink_llm_model_sync_fail_test")
    conn = memory_db(control)
    cfg = operator_cfg(control)

    # First a good sync to establish last-known-good.
    ok = sync.sync_llm_models(
        conn, CHUTES_ENV, cfg=cfg, http_client=FixtureCatalogHttpClient(["moonshotai/Kimi-K2.6-TEE", "zai-org/GLM-5.1-TEE"])
    )
    expect(ok["status"] == "ok", str(ok))
    baseline = _active_tee_models(control, conn)
    expect(len(baseline) == 2, str(baseline))

    # Now the fetch fails -- allow-list must be preserved, operator notified.
    failed = sync.sync_llm_models(conn, CHUTES_ENV, cfg=cfg, http_client=FailingCatalogHttpClient())
    expect(failed["status"] == "failed", str(failed))
    expect(failed["kept_last_known_good"] is True, str(failed))
    expect(failed["notified"] is True, str(failed))
    expect(_active_tee_models(control, conn) == baseline, "allow-list must NOT be emptied on failure")

    notices = _undelivered_operator_notices(conn)
    expect(len(notices) == 1, str(notices))
    # BUG #4: the notice must resolve to the REAL operator target -- the
    # configured platform channel + operator chat id -- exactly like the
    # canonical health-watch operator alert. The old bogus "operator"
    # channel_kind / "llm-router:model-sync" target id never delivered.
    expect(notices[0]["target_kind"] == "operator", str(notices[0]))
    expect(notices[0]["channel_kind"] == OPERATOR_PLATFORM, str(notices[0]))
    expect(notices[0]["target_id"] == OPERATOR_CHAT_ID, str(notices[0]))
    expect(notices[0]["target_id"] != "llm-router:model-sync", str(notices[0]))
    expect("FAILED" in notices[0]["message"], notices[0]["message"])
    print("PASS test_failure_keeps_last_known_good_and_notifies_operator")


def test_failure_with_empty_db_does_not_create_empty_allow_list() -> None:
    control = load_module("arclink_control.py", "arclink_control_model_sync_empty_test")
    sync = load_module("arclink_llm_model_sync.py", "arclink_llm_model_sync_empty_test")
    conn = memory_db(control)
    cfg = operator_cfg(control)

    failed = sync.sync_llm_models(conn, CHUTES_ENV, cfg=cfg, http_client=FailingCatalogHttpClient())
    expect(failed["status"] == "failed", str(failed))
    # No catalog rows existed and none were created/cleared.
    expect(_active_tee_models(control, conn) == [], str(failed))
    expect(len(_undelivered_operator_notices(conn)) == 1, "operator notified on first failure")
    print("PASS test_failure_with_empty_db_does_not_create_empty_allow_list")


def test_too_few_models_treated_as_failure() -> None:
    control = load_module("arclink_control.py", "arclink_control_model_sync_toofew_test")
    sync = load_module("arclink_llm_model_sync.py", "arclink_llm_model_sync_toofew_test")
    conn = memory_db(control)
    cfg = operator_cfg(control)
    env = dict(CHUTES_ENV, ARCLINK_LLM_ROUTER_MODEL_SYNC_MIN_MODELS="5")

    # Catalog returns 2 -TEE models but we require >= 5.
    failed = sync.sync_llm_models(
        conn, env, cfg=cfg, http_client=FixtureCatalogHttpClient(["a-TEE", "b-TEE"])
    )
    expect(failed["status"] == "failed", str(failed))
    expect("too_few_models" in failed["reason"], failed["reason"])
    expect(_active_tee_models(control, conn) == [], "must not write a too-small set")
    print("PASS test_too_few_models_treated_as_failure")


def test_failure_notification_is_deduped() -> None:
    control = load_module("arclink_control.py", "arclink_control_model_sync_dedup_test")
    sync = load_module("arclink_llm_model_sync.py", "arclink_llm_model_sync_dedup_test")
    conn = memory_db(control)
    cfg = operator_cfg(control)

    for _ in range(3):
        sync.sync_llm_models(conn, CHUTES_ENV, cfg=cfg, http_client=FailingCatalogHttpClient())
    notices = _undelivered_operator_notices(conn)
    expect(len(notices) == 1, f"repeated failures must dedup to a single notice, got {len(notices)}")
    print("PASS test_failure_notification_is_deduped")


def test_success_after_failure_clears_alert_state() -> None:
    control = load_module("arclink_control.py", "arclink_control_model_sync_clear_test")
    sync = load_module("arclink_llm_model_sync.py", "arclink_llm_model_sync_clear_test")
    conn = memory_db(control)
    cfg = operator_cfg(control)

    # Fail, then succeed, then fail again -- the second failure must re-notify
    # because the success cleared the alert state.
    sync.sync_llm_models(conn, CHUTES_ENV, cfg=cfg, http_client=FailingCatalogHttpClient())
    # Operator "reads" the notice (mark delivered). Even though the undelivered
    # row is gone, the audit-state dedup must still suppress a second failure --
    # dedup is keyed on audit outcome, not undelivered-row presence.
    conn.execute(
        "UPDATE notification_outbox SET delivered_at=? WHERE target_id=?",
        (control.utc_now_iso(), OPERATOR_CHAT_ID),
    )
    conn.commit()

    # Without a success, a second failure would be suppressed by the audit
    # state (last action == failed).
    suppressed = sync.sync_llm_models(conn, CHUTES_ENV, cfg=cfg, http_client=FailingCatalogHttpClient())
    expect(suppressed["notified"] is False, "second failure suppressed by audit dedup")

    ok = sync.sync_llm_models(
        conn, CHUTES_ENV, cfg=cfg, http_client=FixtureCatalogHttpClient(["a-TEE", "b-TEE"])
    )
    expect(ok["status"] == "ok", str(ok))

    conn.execute(
        "UPDATE notification_outbox SET delivered_at=? WHERE target_id=? AND delivered_at IS NULL",
        (control.utc_now_iso(), OPERATOR_CHAT_ID),
    )
    conn.commit()

    refail = sync.sync_llm_models(conn, CHUTES_ENV, cfg=cfg, http_client=FailingCatalogHttpClient())
    expect(refail["notified"] is True, "failure after a success must re-notify the operator")
    print("PASS test_success_after_failure_clears_alert_state")


def test_rearm_after_success_even_if_prior_notice_never_delivered() -> None:
    # BUG #4b: if the first notice never delivers (its undelivered row lingers
    # forever), a later successful sync must STILL re-arm so the next outage
    # notifies again. Dedup keyed on undelivered rows would block forever.
    control = load_module("arclink_control.py", "arclink_control_model_sync_rearm_test")
    sync = load_module("arclink_llm_model_sync.py", "arclink_llm_model_sync_rearm_test")
    conn = memory_db(control)
    cfg = operator_cfg(control)

    # Establish last-known-good so a later success isn't blocked by the floor.
    ok0 = sync.sync_llm_models(
        conn, CHUTES_ENV, cfg=cfg, http_client=FixtureCatalogHttpClient(["a-TEE", "b-TEE"])
    )
    expect(ok0["status"] == "ok", str(ok0))

    # First failure notifies; the notice is NEVER delivered (row stays undelivered).
    first = sync.sync_llm_models(conn, CHUTES_ENV, cfg=cfg, http_client=FailingCatalogHttpClient())
    expect(first["notified"] is True, str(first))
    expect(len(_undelivered_operator_notices(conn)) == 1, "exactly one undelivered notice")

    # A successful sync clears the alert state (re-arms) WITHOUT requiring the
    # prior notice to have been delivered. The stale undelivered row is still here.
    ok = sync.sync_llm_models(
        conn, CHUTES_ENV, cfg=cfg, http_client=FixtureCatalogHttpClient(["a-TEE", "b-TEE"])
    )
    expect(ok["status"] == "ok", str(ok))
    expect(len(_undelivered_operator_notices(conn)) == 1, "old undelivered notice still lingers")

    # The next outage must notify again -- proving re-arm does not depend on the
    # earlier notice ever delivering.
    second = sync.sync_llm_models(conn, CHUTES_ENV, cfg=cfg, http_client=FailingCatalogHttpClient())
    expect(second["notified"] is True, "outage after success must re-notify despite lingering row")
    expect(len(_undelivered_operator_notices(conn)) == 2, "a fresh notice is queued for the new outage")
    print("PASS test_rearm_after_success_even_if_prior_notice_never_delivered")


def test_partial_response_below_floor_is_failed_keeps_last_known_good() -> None:
    # BUG #3 (floor): a partial response under the sane default minimum (2) must
    # be a FAILED sync -- never accepted as success with mark-missing.
    control = load_module("arclink_control.py", "arclink_control_model_sync_floor_test")
    sync = load_module("arclink_llm_model_sync.py", "arclink_llm_model_sync_floor_test")
    conn = memory_db(control)
    cfg = operator_cfg(control)

    # Seed a healthy last-known-good set of 13 -TEE models (production count).
    full = [f"vendor/model-{i:02d}-TEE" for i in range(13)]
    ok = sync.sync_llm_models(conn, CHUTES_ENV, cfg=cfg, http_client=FixtureCatalogHttpClient(full))
    expect(ok["status"] == "ok", str(ok))
    baseline = _active_tee_models(control, conn)
    expect(len(baseline) == 13, str(baseline))

    # Default env: no MIN override -> floor is 2. A single-model partial response
    # is below the floor and must FAIL (the old min=1 would have accepted it).
    failed = sync.sync_llm_models(
        conn, CHUTES_ENV, cfg=cfg, http_client=FixtureCatalogHttpClient(["vendor/model-00-TEE"])
    )
    expect(failed["status"] == "failed", str(failed))
    expect("too_few_models" in failed["reason"], failed["reason"])
    expect(failed["kept_last_known_good"] is True, str(failed))
    expect(_active_tee_models(control, conn) == baseline, "LKG must be preserved -- no mark-missing")
    expect(len(_undelivered_operator_notices(conn)) == 1, "operator notified on partial response")
    print("PASS test_partial_response_below_floor_is_failed_keeps_last_known_good")


def test_suspicious_proportional_drop_is_failed_keeps_last_known_good() -> None:
    # BUG #3 (proportional drop): even above the hard floor, a large drop vs the
    # last-known active count (e.g. 2 of 13) is treated as a FAILED sync so the
    # allow-list is not silently shrunk and the other models are not marked
    # unavailable.
    control = load_module("arclink_control.py", "arclink_control_model_sync_drop_test")
    sync = load_module("arclink_llm_model_sync.py", "arclink_llm_model_sync_drop_test")
    conn = memory_db(control)
    cfg = operator_cfg(control)

    full = [f"vendor/model-{i:02d}-TEE" for i in range(13)]
    ok = sync.sync_llm_models(conn, CHUTES_ENV, cfg=cfg, http_client=FixtureCatalogHttpClient(full))
    expect(ok["status"] == "ok", str(ok))
    baseline = _active_tee_models(control, conn)
    expect(len(baseline) == 13, str(baseline))

    # 2 of 13 is above the floor (2) but a >50% proportional drop -> suspicious.
    partial = ["vendor/model-00-TEE", "vendor/model-01-TEE"]
    failed = sync.sync_llm_models(conn, CHUTES_ENV, cfg=cfg, http_client=FixtureCatalogHttpClient(partial))
    expect(failed["status"] == "failed", str(failed))
    expect("suspicious_drop" in failed["reason"], failed["reason"])
    expect(failed["kept_last_known_good"] is True, str(failed))
    # The other 11 must NOT have been marked unavailable.
    expect(_active_tee_models(control, conn) == baseline, "LKG preserved -- no mark-missing on drop")
    expect(len(_undelivered_operator_notices(conn)) == 1, "operator notified on suspicious drop")
    print("PASS test_suspicious_proportional_drop_is_failed_keeps_last_known_good")


# --- Router-side: DB-backed effective allow-list (no restart) ---------------

def _seed_catalog(control, conn, model_ids: list[str], *, status: str = "active") -> None:
    now = control.utc_now_iso()
    for model_id in model_ids:
        conn.execute(
            """
            INSERT INTO arclink_model_catalog
              (provider, model_id, status, family, version_sort_key, updated_at, last_seen_at)
            VALUES ('chutes', ?, ?, '', '', ?, ?)
            """,
            (model_id, status, now, now),
        )
    conn.commit()


def test_router_effective_allow_list_reflects_synced_catalog() -> None:
    control = load_module("arclink_control.py", "arclink_control_router_effective_test")
    router = load_module("arclink_llm_router.py", "arclink_llm_router_effective_test")
    conn = memory_db(control)
    config = router.load_router_config(
        {
            "ARCLINK_LLM_ROUTER_ALLOWED_MODELS": "env-only-model",
            "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "k",
            "ARCLINK_DB_PATH": ":memory:",
        }
    )
    # No catalog rows -> fall back to the static env allow-list.
    expect(
        router._effective_global_allowed_models(conn, config) == ("env-only-model",),
        "empty catalog must fall back to env allow-list",
    )

    _seed_catalog(control, conn, ["moonshotai/Kimi-K2.6-TEE", "zai-org/GLM-5.1-TEE"])
    # An inactive / non-TEE row must be ignored.
    _seed_catalog(control, conn, ["vendor/old-TEE"], status="unavailable")
    _seed_catalog(control, conn, ["vendor/plain"], status="active")

    effective = router._effective_global_allowed_models(conn, config)
    expect(
        effective == ("moonshotai/Kimi-K2.6-TEE", "zai-org/GLM-5.1-TEE"),
        f"effective allow-list should reflect active -TEE rows, got {effective}",
    )
    print("PASS test_router_effective_allow_list_reflects_synced_catalog")


def test_startup_refresh_tee_heavy_drop_keeps_glm_and_kimi() -> None:
    # FIX D: a successful /models response that is heavy on NON-TEE models but
    # carries zero (or few) -TEE models must NOT drop GLM/Kimi from the allow-list.
    # The old startup path counted ALL Chutes models for its floor/proportional
    # guard, so such a response cleared the guard, then mark_missing_unavailable
    # flipped every active -TEE row to unavailable -> the -TEE allow-list emptied.
    # The fix makes the startup refresh purely additive (mark_missing always off);
    # destructive -TEE removals are owned by the guarded hourly sync worker.
    control = load_module("arclink_control.py", "arclink_control_startup_tee_drop_test")
    router = load_module("arclink_llm_router.py", "arclink_llm_router_startup_tee_drop_test")

    config_dir = Path(tempfile.mkdtemp(prefix="arclink-router-tee-drop-"))
    db_path = str(config_dir / "router.sqlite3")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        control.ensure_schema(conn)
        # Seed the production -TEE allow-list (GLM + Kimi) as active.
        control.upsert_model_catalog(
            conn,
            provider="chutes",
            models={
                "zai-org/GLM-5.2-TEE": {"confidential_compute": True},
                "moonshotai/Kimi-K2.6-TEE": {"confidential_compute": True},
            },
        )
        baseline = [
            str(row["model_id"])
            for row in conn.execute(
                "SELECT model_id FROM arclink_model_catalog "
                "WHERE provider='chutes' AND status='active' AND model_id LIKE '%-TEE' ORDER BY model_id"
            ).fetchall()
        ]
    finally:
        conn.close()
    expect(baseline == ["moonshotai/Kimi-K2.6-TEE", "zai-org/GLM-5.2-TEE"], str(baseline))

    config = router.load_router_config(
        {
            "ARCLINK_DB_PATH": db_path,
            "ARCLINK_LLM_ROUTER_ENABLED": "1",
            "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
            "ARCLINK_LLM_ROUTER_REFRESH_MODEL_CATALOG_ON_STARTUP": "1",
            "ARCLINK_LLM_ROUTER_MARK_MISSING_MODELS_UNAVAILABLE": "1",
        }
    )
    # A response that is HEAVY on non-TEE models (clears any all-models floor) but
    # carries ZERO -TEE models -- the exact shape that used to empty the allow-list.
    non_tee_heavy = FixtureCatalogHttpClient(
        [f"vendor/plain-model-{i:02d}" for i in range(8)]
    )
    result = router._refresh_model_catalog_once(config, http_client=non_tee_heavy)
    expect(result["status"] == "ok", str(result))
    expect(result["mark_missing_unavailable"] is False, str(result))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        after_tee = [
            str(row["model_id"])
            for row in conn.execute(
                "SELECT model_id FROM arclink_model_catalog "
                "WHERE provider='chutes' AND status='active' AND model_id LIKE '%-TEE' ORDER BY model_id"
            ).fetchall()
        ]
    finally:
        conn.close()
    # GLM-5.2-TEE + Kimi-K2.6-TEE must still be active -- not dropped to unavailable.
    expect(after_tee == baseline, f"-TEE allow-list must survive a TEE-light startup: {after_tee} != {baseline}")
    print("PASS test_startup_refresh_tee_heavy_drop_keeps_glm_and_kimi")


def main() -> int:
    test_filter_tee_models_keeps_only_tee_suffix()
    test_fetch_tee_models_filters_catalog()
    test_operator_target_resolves_real_chat_from_config_not_environ()
    test_sync_success_populates_catalog()
    test_failure_keeps_last_known_good_and_notifies_operator()
    test_failure_with_empty_db_does_not_create_empty_allow_list()
    test_too_few_models_treated_as_failure()
    test_failure_notification_is_deduped()
    test_success_after_failure_clears_alert_state()
    test_rearm_after_success_even_if_prior_notice_never_delivered()
    test_partial_response_below_floor_is_failed_keeps_last_known_good()
    test_suspicious_proportional_drop_is_failed_keeps_last_known_good()
    test_router_effective_allow_list_reflects_synced_catalog()
    test_startup_refresh_tee_heavy_drop_keeps_glm_and_kimi()
    print("PASS all 14 ArcLink LLM model-sync tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
