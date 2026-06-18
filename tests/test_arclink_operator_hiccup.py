#!/usr/bin/env python3
"""Tests for Feature C: real-only Operator hiccup notifications.

Product rule: "any hiccup from the system should be told to the Operator, but
only if it's not false." These tests pin the contract for the centralized
``report_operator_hiccup`` helper and the two newly-wired terminal-failure
sources (public-Agent bridge stuck turns; deployment provisioning exhausted):

  * a REAL, terminal failure notifies the Operator exactly once,
  * a transient / self-healing event (an early retry, an unconfirmed/held turn,
    a deployment that still has durable runtime) does NOT notify,
  * N repeated failures for one key dedup to a single notice,
  * the alert re-arms only after an explicit resolved/ok for that key,
  * a tui-only / unconfigured Operator is a safe no-op (no external channel),
  * the operator target is resolved from Config (ARCLINK_CONFIG_FILE), never raw
    os.environ.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from arclink_test_helpers import expect, load_module, memory_db

OPERATOR_PLATFORM = "telegram"
OPERATOR_CHAT_ID = "tg:operator-chat-9999"


def operator_cfg(
    control,
    *,
    platform: str = OPERATOR_PLATFORM,
    channel_id: str = OPERATOR_CHAT_ID,
):
    """Build a real Config whose operator target carries the operator chat.

    Mirrors production: the operator vars live in the config file the compose
    service exports (loaded via ARCLINK_CONFIG_FILE), NOT in the worker's raw
    process environment. Sourcing the target from the env would fall back to
    tui-only; sourcing from Config resolves the real platform + chat.
    """
    config_dir = Path(tempfile.mkdtemp(prefix="arclink-hiccup-cfg-"))
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


def _operator_notices(conn, *, target_id: str = OPERATOR_CHAT_ID) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM notification_outbox
        WHERE target_kind = 'operator' AND target_id = ?
        ORDER BY id
        """,
        (target_id,),
    ).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Centralized helper: report_operator_hiccup / resolve_operator_hiccup
# ---------------------------------------------------------------------------


def test_real_failure_notifies_once() -> None:
    control = load_module("arclink_control.py", "arclink_control_hiccup_one")
    conn = memory_db(control)
    cfg = operator_cfg(control)

    notification_id = control.report_operator_hiccup(
        conn,
        cfg,
        source="unit_test",
        key="thing_a",
        message="thing A failed for real",
    )
    expect(notification_id > 0, "a real failure must queue an operator notice")
    notices = _operator_notices(conn)
    expect(len(notices) == 1, f"a real failure notifies exactly once, got {len(notices)}")
    # Resolved to the REAL operator chat on the configured platform.
    expect(notices[0]["channel_kind"] == OPERATOR_PLATFORM, str(notices[0]))
    expect(notices[0]["target_id"] == OPERATOR_CHAT_ID, str(notices[0]))
    print("PASS test_real_failure_notifies_once")


def test_repeated_failures_dedup_to_one_notice() -> None:
    control = load_module("arclink_control.py", "arclink_control_hiccup_dedup")
    conn = memory_db(control)
    cfg = operator_cfg(control)

    first = control.report_operator_hiccup(
        conn, cfg, source="unit_test", key="thing_b", message="thing B failed"
    )
    expect(first > 0, "first real failure notifies")
    deduped = [
        control.report_operator_hiccup(
            conn, cfg, source="unit_test", key="thing_b", message="thing B still failing"
        )
        for _ in range(4)
    ]
    expect(all(value == 0 for value in deduped), f"repeats must dedup (return 0), got {deduped}")
    notices = _operator_notices(conn)
    expect(len(notices) == 1, f"sustained outage dedups to a single notice, got {len(notices)}")
    print("PASS test_repeated_failures_dedup_to_one_notice")


def test_dedup_survives_undelivered_notice() -> None:
    # Dedup is anchored on audit outcome state, NOT on undelivered-row presence.
    # Even if the prior notice is never read/delivered, a repeat must not re-queue.
    control = load_module("arclink_control.py", "arclink_control_hiccup_undelivered")
    conn = memory_db(control)
    cfg = operator_cfg(control)

    control.report_operator_hiccup(conn, cfg, source="unit_test", key="thing_c", message="C failed")
    # Operator never reads it (row stays undelivered). A repeat must still dedup.
    again = control.report_operator_hiccup(
        conn, cfg, source="unit_test", key="thing_c", message="C failed again"
    )
    expect(again == 0, "repeat deduped even though the prior notice never delivered")
    expect(len(_operator_notices(conn)) == 1, "still exactly one notice")
    print("PASS test_dedup_survives_undelivered_notice")


def test_rearm_after_resolved() -> None:
    control = load_module("arclink_control.py", "arclink_control_hiccup_rearm")
    conn = memory_db(control)
    cfg = operator_cfg(control)

    control.report_operator_hiccup(conn, cfg, source="unit_test", key="thing_d", message="D failed")
    expect(len(_operator_notices(conn)) == 1, "first failure notifies")

    # Without a resolve, a second failure is suppressed (still armed).
    suppressed = control.report_operator_hiccup(
        conn, cfg, source="unit_test", key="thing_d", message="D failed again"
    )
    expect(suppressed == 0, "second failure suppressed while still armed")
    expect(len(_operator_notices(conn)) == 1, "no new notice while armed")

    # Explicit recovery re-arms the alert.
    rearmed = control.resolve_operator_hiccup(conn, cfg, source="unit_test", key="thing_d")
    expect(rearmed is True, "resolve must re-arm a currently-armed alert")

    # The next real failure notifies again.
    refail = control.report_operator_hiccup(
        conn, cfg, source="unit_test", key="thing_d", message="D failed after recovery"
    )
    expect(refail > 0, "failure after a resolve must re-notify")
    expect(len(_operator_notices(conn)) == 2, "a fresh notice is queued after re-arm")
    print("PASS test_rearm_after_resolved")


def test_resolve_is_noop_when_not_armed() -> None:
    control = load_module("arclink_control.py", "arclink_control_hiccup_resolve_noop")
    conn = memory_db(control)
    cfg = operator_cfg(control)

    # Resolving a key that was never armed must be a no-op (no audit churn).
    result = control.resolve_operator_hiccup(conn, cfg, source="unit_test", key="never_armed")
    expect(result is False, "resolving an unarmed key is a no-op")
    print("PASS test_resolve_is_noop_when_not_armed")


def test_distinct_keys_each_notify() -> None:
    control = load_module("arclink_control.py", "arclink_control_hiccup_keys")
    conn = memory_db(control)
    cfg = operator_cfg(control)

    control.report_operator_hiccup(conn, cfg, source="unit_test", key="key_one", message="one")
    control.report_operator_hiccup(conn, cfg, source="unit_test", key="key_two", message="two")
    notices = _operator_notices(conn)
    expect(len(notices) == 2, f"distinct real outages each notify once, got {len(notices)}")
    print("PASS test_distinct_keys_each_notify")


def test_tui_only_operator_is_safe_noop() -> None:
    # A tui-only / unconfigured operator must NOT produce an external-channel
    # send: the row is queued as tui-only (readable in the TUI) but channel_kind
    # is tui-only so delivery is a no-op. Dedup state is still recorded.
    control = load_module("arclink_control.py", "arclink_control_hiccup_tui")
    conn = memory_db(control)
    cfg = operator_cfg(control, platform="tui-only", channel_id="")

    notification_id = control.report_operator_hiccup(
        conn, cfg, source="unit_test", key="tui_thing", message="tui-only failure"
    )
    expect(notification_id > 0, "tui-only still records a (tui-only) outbox row")
    rows = conn.execute(
        "SELECT channel_kind FROM notification_outbox WHERE id = ?",
        (notification_id,),
    ).fetchall()
    expect(len(rows) == 1, "one row recorded")
    expect(
        str(rows[0]["channel_kind"]) == "tui-only",
        f"tui-only operator must not target an external channel, got {rows[0]['channel_kind']!r}",
    )
    # Dedup still holds for tui-only.
    again = control.report_operator_hiccup(
        conn, cfg, source="unit_test", key="tui_thing", message="again"
    )
    expect(again == 0, "tui-only dedup still holds")
    print("PASS test_tui_only_operator_is_safe_noop")


def test_empty_key_rejected() -> None:
    control = load_module("arclink_control.py", "arclink_control_hiccup_emptykey")
    conn = memory_db(control)
    cfg = operator_cfg(control)
    raised = False
    try:
        control.report_operator_hiccup(conn, cfg, source="unit_test", key="  ", message="x")
    except ValueError:
        raised = True
    expect(raised, "an empty key must be rejected")
    print("PASS test_empty_key_rejected")


# ---------------------------------------------------------------------------
# Wired source (a): public-Agent bridge TERMINAL delivery failure
# ---------------------------------------------------------------------------


def _point_config_at_operator() -> None:
    """Point Config.from_env() (used inside the helpers) at a real operator cfg."""
    config_dir = Path(tempfile.mkdtemp(prefix="arclink-bridge-cfg-"))
    config_path = config_dir / "operator.env"
    config_path.write_text(
        f"OPERATOR_NOTIFY_CHANNEL_PLATFORM={OPERATOR_PLATFORM}\n"
        f"OPERATOR_NOTIFY_CHANNEL_ID={OPERATOR_CHAT_ID}\n",
        encoding="utf-8",
    )
    os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)


def _public_agent_turn_row(
    control,
    conn,
    *,
    attempt_count: int,
    target_kind: str = "public-agent-turn",
    terminal_failures: int | None = None,
) -> int:
    """Queue a public-agent-turn outbox row for the bridge-hiccup gate tests.

    ``attempt_count`` sets the row column (which the BUG #1 fix deliberately does
    NOT gate on). ``terminal_failures``, when given, pre-seeds the per-row
    consecutive-terminal-failure counter inside ``extra_json`` -- the value the
    gate actually reads. Each subsequent genuine-terminal gate call increments it
    by one; any non-terminal/uncertain outcome resets it.
    """
    extra: dict = {"deployment_id": "arcdep_test", "prefix": "arc-testpod"}
    if terminal_failures is not None:
        from arclink_notification_delivery import (  # local import: module already on sys.path
            PUBLIC_AGENT_BRIDGE_TERMINAL_FAILURE_KEY,
        )

        extra[PUBLIC_AGENT_BRIDGE_TERMINAL_FAILURE_KEY] = int(terminal_failures)
    notification_id = control.queue_notification(
        conn,
        target_kind=target_kind,
        target_id="tg:user-123",
        channel_kind="telegram",
        message="user message",
        extra=extra,
    )
    conn.execute(
        "UPDATE notification_outbox SET attempt_count = ? WHERE id = ?",
        (int(attempt_count), int(notification_id)),
    )
    conn.commit()
    return int(notification_id)


def _terminal_failure_count(control, conn, notification_id: int) -> int:
    """Read the per-row consecutive-terminal-failure counter from extra_json."""
    import json as _json

    from arclink_notification_delivery import PUBLIC_AGENT_BRIDGE_TERMINAL_FAILURE_KEY

    row = conn.execute(
        "SELECT extra_json FROM notification_outbox WHERE id = ?",
        (int(notification_id),),
    ).fetchone()
    if row is None:
        return 0
    try:
        extra = _json.loads(str(row["extra_json"] or "{}"))
    except (ValueError, TypeError):
        return 0
    if not isinstance(extra, dict):
        return 0
    return int(extra.get(PUBLIC_AGENT_BRIDGE_TERMINAL_FAILURE_KEY) or 0)


def test_bridge_transient_failure_does_not_notify() -> None:
    # A public-agent turn that failed only a few times is still being retried
    # (no max-attempt cap on these rows) -- it may self-heal on the next attempt.
    # Below the threshold, NO operator notice may be queued (false-alarm guard).
    control = load_module("arclink_control.py", "arclink_control_bridge_transient")
    delivery = load_module(
        "arclink_notification_delivery.py", "arclink_delivery_bridge_transient"
    )
    conn = memory_db(control)
    operator_cfg(control)

    # The helper resolves Config via Config.from_env(); point it at the operator cfg
    # file so it reaches the real operator (and so a *false* notice would be visible).
    config_dir = Path(tempfile.mkdtemp(prefix="arclink-bridge-cfg-"))
    config_path = config_dir / "operator.env"
    config_path.write_text(
        f"OPERATOR_NOTIFY_CHANNEL_PLATFORM={OPERATOR_PLATFORM}\n"
        f"OPERATOR_NOTIFY_CHANNEL_ID={OPERATOR_CHAT_ID}\n",
        encoding="utf-8",
    )
    os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)

    nid = _public_agent_turn_row(control, conn, attempt_count=1)
    delivery._maybe_report_public_agent_bridge_hiccup(conn, nid, error="transient blip")
    expect(len(_operator_notices(conn)) == 0, "an early-retry turn must NOT page the operator")
    print("PASS test_bridge_transient_failure_does_not_notify")


def test_bridge_terminal_failure_notifies_once() -> None:
    control = load_module("arclink_control.py", "arclink_control_bridge_terminal")
    delivery = load_module(
        "arclink_notification_delivery.py", "arclink_delivery_bridge_terminal"
    )
    conn = memory_db(control)
    operator_cfg(control)  # ensure ARCLINK_CONFIG_FILE points at an operator cfg
    config_dir = Path(tempfile.mkdtemp(prefix="arclink-bridge-cfg2-"))
    config_path = config_dir / "operator.env"
    config_path.write_text(
        f"OPERATOR_NOTIFY_CHANNEL_PLATFORM={OPERATOR_PLATFORM}\n"
        f"OPERATOR_NOTIFY_CHANNEL_ID={OPERATOR_CHAT_ID}\n",
        encoding="utf-8",
    )
    os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)

    threshold = delivery._public_agent_bridge_hiccup_min_attempts()
    # Drive the REAL predicate: a fresh row (consecutive-terminal counter = 0), then
    # `threshold` CONSECUTIVE genuine terminal-error gate calls. The counter climbs
    # 1..threshold; the page fires only on the threshold-th call, never before.
    nid = _public_agent_turn_row(control, conn, attempt_count=0)
    for i in range(1, threshold):
        delivery._maybe_report_public_agent_bridge_hiccup(conn, nid, error=f"terminal failure {i}")
        expect(
            len(_operator_notices(conn)) == 0,
            f"below {threshold} consecutive terminal errors must NOT page (at {i}), "
            f"got {len(_operator_notices(conn))}",
        )
        expect(_terminal_failure_count(control, conn, nid) == i, "counter climbs by one per terminal error")
    # The threshold-th consecutive terminal error pages exactly once.
    delivery._maybe_report_public_agent_bridge_hiccup(conn, nid, error="terminal failure at threshold")
    notices = _operator_notices(conn)
    expect(len(notices) == 1, f"a terminally-stuck turn notifies exactly once, got {len(notices)}")
    expect("public-agent" in notices[0]["message"], str(notices[0]))
    # A further terminal pass dedups (still armed) -> still exactly one notice.
    delivery._maybe_report_public_agent_bridge_hiccup(conn, nid, error="terminal failure after threshold")
    expect(len(_operator_notices(conn)) == 1, "a further terminal pass dedups to one notice")
    print("PASS test_bridge_terminal_failure_notifies_once")


def test_bridge_unconfirmed_increments_then_one_terminal_does_not_page() -> None:
    # BUG #1 (the cardinal case): attempt_count is bumped by BOTH terminal errors
    # AND non-terminal "maybe delivered" outcomes (D5 held/unconfirmed). A row with
    # (threshold-1) UNCONFIRMED outcomes followed by ONE terminal error has
    # attempt_count >= threshold -- so the OLD attempt_count gate would have paged.
    # But those unconfirmed turns MAY have delivered, so paging is a FALSE ALARM.
    # The fix gates on the CONSECUTIVE-terminal counter, which the unconfirmed
    # outcomes reset to 0, so a single terminal error after them is counter=1 and
    # must NOT page. Driven through the REAL _mark_public_agent_bridge_unconfirmed
    # (which bumps attempt_count and resets the counter) and the REAL gate.
    control = load_module("arclink_control.py", "arclink_control_bridge_unconf_terminal")
    delivery = load_module("arclink_notification_delivery.py", "arclink_delivery_bridge_unconf_terminal")
    conn = memory_db(control)
    operator_cfg(control)
    _point_config_at_operator()

    threshold = delivery._public_agent_bridge_hiccup_min_attempts()
    nid = _public_agent_turn_row(control, conn, attempt_count=0)
    # (threshold - 1) genuine NON-terminal unconfirmed/held outcomes. Each bumps the
    # row's attempt_count (the maybe-delivered turns) and resets the terminal
    # counter to 0.
    for i in range(threshold - 1):
        delivery._mark_public_agent_bridge_unconfirmed(
            conn, nid, f"delivery_status unknown (maybe delivered) #{i}"
        )
    attempt_count = int(
        conn.execute("SELECT attempt_count FROM notification_outbox WHERE id = ?", (nid,)).fetchone()[0]
    )
    expect(
        attempt_count >= threshold - 1,
        f"unconfirmed outcomes inflated attempt_count to {attempt_count} (the OLD gate's input)",
    )
    expect(
        _terminal_failure_count(control, conn, nid) == 0,
        "non-terminal outcomes leave the consecutive-terminal counter at 0",
    )
    # Now ONE genuine terminal error, modelled exactly as production does it: the
    # terminal site calls mark_notification_error (which bumps attempt_count to >=
    # threshold) and THEN the gate. attempt_count is now >= threshold, but the
    # consecutive-terminal counter is only 1 -> MUST NOT page (cardinal sin avoided).
    control.mark_notification_error(conn, nid, "one terminal error after unconfirmed")
    delivery._maybe_report_public_agent_bridge_hiccup(conn, nid, error="one terminal error after unconfirmed")
    final_attempt = int(
        conn.execute("SELECT attempt_count FROM notification_outbox WHERE id = ?", (nid,)).fetchone()[0]
    )
    expect(
        final_attempt >= threshold,
        f"attempt_count is at/above the threshold ({final_attempt}) -- the OLD gate would have paged",
    )
    expect(
        _terminal_failure_count(control, conn, nid) == 1,
        "only ONE consecutive terminal error after the unconfirmed run",
    )
    expect(
        len(_operator_notices(conn)) == 0,
        "a row with mostly maybe-delivered outcomes + 1 terminal error must NOT page "
        "(consecutive-terminal counter, not attempt_count)",
    )
    print("PASS test_bridge_unconfirmed_increments_then_one_terminal_does_not_page")


def test_bridge_unconfirmed_resets_a_partial_terminal_run() -> None:
    # BUG #1 (interleaving): a partial run of consecutive terminal errors that is
    # INTERRUPTED by a single non-terminal (maybe-delivered) outcome must RESET --
    # the count cannot resume. Only a FRESH unbroken run of `threshold` terminal
    # errors pages. This proves the reset is on the same row the gate reads.
    control = load_module("arclink_control.py", "arclink_control_bridge_reset_run")
    delivery = load_module("arclink_notification_delivery.py", "arclink_delivery_bridge_reset_run")
    conn = memory_db(control)
    operator_cfg(control)
    _point_config_at_operator()

    threshold = delivery._public_agent_bridge_hiccup_min_attempts()
    nid = _public_agent_turn_row(control, conn, attempt_count=0)
    # Build a partial terminal run just short of paging.
    for i in range(threshold - 1):
        delivery._maybe_report_public_agent_bridge_hiccup(conn, nid, error=f"terminal {i}")
    expect(_terminal_failure_count(control, conn, nid) == threshold - 1, "partial run accumulated")
    expect(len(_operator_notices(conn)) == 0, "partial run has not paged yet")

    # A single non-terminal (maybe-delivered) outcome RESETS the run to 0.
    delivery._mark_public_agent_bridge_unconfirmed(conn, nid, "maybe delivered -- reset")
    expect(_terminal_failure_count(control, conn, nid) == 0, "one non-terminal outcome resets the run")

    # The next terminal error is counter=1, NOT threshold -> still no page.
    delivery._maybe_report_public_agent_bridge_hiccup(conn, nid, error="terminal after reset")
    expect(len(_operator_notices(conn)) == 0, "the interrupted run cannot resume -> no page")
    expect(_terminal_failure_count(control, conn, nid) == 1, "a fresh run starts at 1")

    # Only a fresh UNBROKEN run of `threshold` terminal errors pages, once.
    for i in range(threshold - 1):
        delivery._maybe_report_public_agent_bridge_hiccup(conn, nid, error=f"fresh terminal {i}")
    expect(len(_operator_notices(conn)) == 1, "a fresh full consecutive run pages exactly once")
    print("PASS test_bridge_unconfirmed_resets_a_partial_terminal_run")


def test_bridge_delivered_row_does_not_notify() -> None:
    # A delivered row is a success, never a hiccup -- even past the threshold.
    control = load_module("arclink_control.py", "arclink_control_bridge_delivered")
    delivery = load_module(
        "arclink_notification_delivery.py", "arclink_delivery_bridge_delivered"
    )
    conn = memory_db(control)
    operator_cfg(control)
    config_dir = Path(tempfile.mkdtemp(prefix="arclink-bridge-cfg3-"))
    config_path = config_dir / "operator.env"
    config_path.write_text(
        f"OPERATOR_NOTIFY_CHANNEL_PLATFORM={OPERATOR_PLATFORM}\n"
        f"OPERATOR_NOTIFY_CHANNEL_ID={OPERATOR_CHAT_ID}\n",
        encoding="utf-8",
    )
    os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)

    threshold = delivery._public_agent_bridge_hiccup_min_attempts()
    nid = _public_agent_turn_row(control, conn, attempt_count=threshold + 3)
    control.mark_notification_delivered(conn, nid)
    delivery._maybe_report_public_agent_bridge_hiccup(conn, nid, error="late error after deliver")
    expect(len(_operator_notices(conn)) == 0, "a delivered turn must never page the operator")
    print("PASS test_bridge_delivered_row_does_not_notify")


def test_bridge_page_then_deliver_resolves_alert() -> None:
    # BUG #1: a turn that pages at the threshold can still self-heal on a later
    # retry (no max-attempt cap) and be marked delivered. resolve-on-delivery must
    # CLEAR that turn's alert so it does not linger as a "could not deliver" page.
    # Verified through the real predicate: the alert is armed (audit state), then
    # delivery resolves it -- so a future failure for the SAME key would page
    # again, proving the alert is no longer armed (i.e. the false alarm cleared).
    control = load_module("arclink_control.py", "arclink_control_bridge_resolve")
    delivery = load_module("arclink_notification_delivery.py", "arclink_delivery_bridge_resolve")
    conn = memory_db(control)
    operator_cfg(control)
    _point_config_at_operator()

    threshold = delivery._public_agent_bridge_hiccup_min_attempts()
    # Pre-seed the consecutive-terminal counter to one-below-threshold so a single
    # genuine terminal error tips it over and pages (genuinely stuck so far).
    nid = _public_agent_turn_row(control, conn, attempt_count=threshold, terminal_failures=threshold - 1)
    delivery._maybe_report_public_agent_bridge_hiccup(conn, nid, error="terminal failure")
    expect(len(_operator_notices(conn)) == 1, "a turn stuck at the threshold pages once")
    key = delivery._public_agent_bridge_hiccup_key(nid)
    expect(
        control._operator_hiccup_already_armed(conn, key=key) is True,
        "the per-row alert is armed after the page",
    )

    # The very next retry self-heals -> delivered. resolve-on-delivery clears it.
    control.mark_notification_delivered(conn, nid)
    delivery._resolve_public_agent_bridge_hiccup(conn, nid)
    expect(
        control._operator_hiccup_already_armed(conn, key=key) is False,
        "resolve-on-delivery must clear the alert for a recovered turn (no lingering false alarm)",
    )
    # Still exactly one historical notice (the resolve does not queue a new page).
    expect(len(_operator_notices(conn)) == 1, "resolve does not queue a new operator notice")
    print("PASS test_bridge_page_then_deliver_resolves_alert")


def test_bridge_real_delivery_success_resolves_armed_alert() -> None:
    # NON-tautological resolve test (Codex flag): instead of calling the resolve
    # helper directly, drive the REAL bridge delivery-success SITE -- the actual
    # _run_public_agent_bridge_worker success path, with a fake `subprocess.run`
    # that returns delivered=true -- and assert that site (which calls
    # mark_notification_delivered + _resolve_public_agent_bridge_hiccup) clears the
    # armed Operator alert. This proves the production success site resolves the
    # alert, not just the isolated helper.
    import json as _json

    control = load_module("arclink_control.py", "arclink_control_bridge_real_resolve")
    delivery = load_module("arclink_notification_delivery.py", "arclink_delivery_bridge_real_resolve")

    config_dir = Path(tempfile.mkdtemp(prefix="arclink-bridge-realresolve-"))
    db_path = config_dir / "control.sqlite3"
    config_path = config_dir / "operator.env"
    config_path.write_text(
        f"OPERATOR_NOTIFY_CHANNEL_PLATFORM={OPERATOR_PLATFORM}\n"
        f"OPERATOR_NOTIFY_CHANNEL_ID={OPERATOR_CHAT_ID}\n"
        f"ARCLINK_DB_PATH={db_path}\n"
        "TELEGRAM_BOT_TOKEN=telegram-public-token\n",
        encoding="utf-8",
    )
    prior = os.environ.get("ARCLINK_CONFIG_FILE")
    os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
    try:
        cfg = control.Config.from_env()
        threshold = delivery._public_agent_bridge_hiccup_min_attempts()
        # Queue a real public-agent-turn row (file-backed db so the worker, which
        # opens its OWN connect_db(cfg), sees the same row) and arm its alert via
        # the REAL gate (counter pre-seeded one below threshold, then one terminal).
        with control.connect_db(cfg) as conn:
            nid = control.queue_notification(
                conn,
                target_kind="public-agent-turn",
                target_id="tg:123",
                channel_kind="telegram",
                message="finish later",
                extra={
                    "deployment_id": "arcdep_test",
                    delivery.PUBLIC_AGENT_BRIDGE_TERMINAL_FAILURE_KEY: threshold - 1,
                },
            )
            delivery._maybe_report_public_agent_bridge_hiccup(conn, nid, error="terminal failure")
            key = delivery._public_agent_bridge_hiccup_key(nid)
            expect(
                control._operator_hiccup_already_armed(conn, key=key) is True,
                "the per-row alert is armed after a genuine terminal page",
            )
            expect(len(_operator_notices(conn)) == 1, "armed once")

        # Drive the REAL bridge worker success path with a fake subprocess.
        class _Proc:
            returncode = 0
            stdout = '{"delivered": true, "delivery_status": "confirmed", "message_ids": ["tg-msg-1"], "ok": true}\n'
            stderr = ""

        def _fake_run(cmd, input="", check=False, text=True, capture_output=True, timeout=None):
            return _Proc()

        original_run = delivery.subprocess.run
        delivery.subprocess.run = _fake_run
        try:
            job_path = delivery._write_public_agent_bridge_job(
                notification_id=nid,
                cmd=[
                    "docker",
                    "exec",
                    "-i",
                    "arclink-arcdep_test-hermes-gateway-1",
                    "/opt/arclink/runtime/hermes-venv/bin/python3",
                    "/home/arclink/arclink/python/arclink_public_agent_bridge.py",
                ],
                payload={"platform": "telegram", "bot_token": "detached-secret", "text": "finish later"},
                project_name="arclink-arcdep_test",
            )
            result = delivery._run_public_agent_bridge_worker(job_path)
            expect(result == 0, f"the real bridge success path returns 0, got {result}")
        finally:
            delivery.subprocess.run = original_run

        # Reopen and assert: the row delivered AND the armed alert is now cleared by
        # the REAL success site (so a future failure for the same key would re-page).
        with control.connect_db(cfg) as conn:
            row = conn.execute(
                "SELECT delivered_at, delivery_error FROM notification_outbox WHERE id = ?",
                (nid,),
            ).fetchone()
            expect(bool(row["delivered_at"]) and not row["delivery_error"], dict(row))
            expect(
                control._operator_hiccup_already_armed(conn, key=key) is False,
                "the REAL bridge delivery-success site must resolve the armed alert "
                "(no lingering false alarm)",
            )
            extra = _json.loads(
                str(conn.execute("SELECT extra_json FROM notification_outbox WHERE id = ?", (nid,)).fetchone()[0] or "{}")
            )
            # A delivered row never reaches the gate again, so the stale terminal
            # counter (if any) cannot cause a false page; not asserting its value.
            expect(isinstance(extra, dict), "extra_json remains a dict after delivery")
    finally:
        if prior is None:
            os.environ.pop("ARCLINK_CONFIG_FILE", None)
        else:
            os.environ["ARCLINK_CONFIG_FILE"] = prior
    print("PASS test_bridge_real_delivery_success_resolves_armed_alert")


def test_bridge_public_bot_user_error_does_not_page_as_bridge() -> None:
    # BUG #1b: an ordinary public-bot-user delivery error (e.g. missing token /
    # missing target) is NOT a public-agent BRIDGE turn. Even past the threshold,
    # the bridge gate must NOT page it -- doing so would be both wrong-sourced and
    # a false alarm.
    control = load_module("arclink_control.py", "arclink_control_bridge_botuser")
    delivery = load_module("arclink_notification_delivery.py", "arclink_delivery_bridge_botuser")
    conn = memory_db(control)
    operator_cfg(control)
    _point_config_at_operator()

    threshold = delivery._public_agent_bridge_hiccup_min_attempts()
    nid = _public_agent_turn_row(
        control, conn, attempt_count=threshold + 5, target_kind="public-bot-user"
    )
    delivery._maybe_report_public_agent_bridge_hiccup(
        conn, nid, error="TELEGRAM_BOT_TOKEN is not configured"
    )
    expect(
        len(_operator_notices(conn)) == 0,
        "a generic public-bot-user error must NOT page as a public-agent bridge failure",
    )
    print("PASS test_bridge_public_bot_user_error_does_not_page_as_bridge")


def test_bridge_d5_held_and_deferred_outcomes_do_not_page() -> None:
    # The D5 cases (deferred / unconfirmed-held / delivered) are NOT terminal: the
    # delivery loop short-circuits them BEFORE the error/hiccup path, so the bridge
    # gate is never reached. We assert the gate's own guards reject these even if
    # reached directly: a delivered row never pages (the held/unconfirmed turn is
    # eventually either delivered or terminally failed; while held it is delivered=
    # NULL but the loop `continue`s without calling the gate). Here we pin the two
    # gate-level guards that protect against a stray call: delivered => no page,
    # and below-threshold (a fresh held turn that has not exhausted retries) => no
    # page.
    control = load_module("arclink_control.py", "arclink_control_bridge_d5")
    delivery = load_module("arclink_notification_delivery.py", "arclink_delivery_bridge_d5")
    conn = memory_db(control)
    operator_cfg(control)
    _point_config_at_operator()

    # Held/unconfirmed turn that has only been attempted a little: below threshold.
    held = _public_agent_turn_row(control, conn, attempt_count=1)
    delivery._maybe_report_public_agent_bridge_hiccup(conn, held, error="held for reconciliation")
    expect(len(_operator_notices(conn)) == 0, "a below-threshold held turn must not page")

    # A delivered turn (the held turn later confirmed delivered) never pages.
    delivered = _public_agent_turn_row(
        control, conn, attempt_count=delivery._public_agent_bridge_hiccup_min_attempts() + 2
    )
    control.mark_notification_delivered(conn, delivered)
    delivery._maybe_report_public_agent_bridge_hiccup(conn, delivered, error="stray late call")
    expect(len(_operator_notices(conn)) == 0, "a delivered (reconciled) turn must not page")
    print("PASS test_bridge_d5_held_and_deferred_outcomes_do_not_page")


def test_bridge_worker_metadata_write_race_does_not_resurrect_counter() -> None:
    # BUG #1 regression -- the stale-extra_json metadata-write RACE.
    #
    # _spawn_public_agent_gateway_bridge starts the detached child BEFORE it calls
    # _record_public_agent_bridge_worker (a whole-row extra_json write). The OLD
    # implementation read the whole extra_json, mutated only the worker key, and
    # wrote the whole dict back. Interleaving:
    #   1. parent reads extra_json while the counter is threshold-1,
    #   2. the child RESETS the counter to 0 on a maybe-delivered (D5) outcome,
    #   3. the parent writes its STALE whole extra_json back, RESURRECTING the
    #      counter at threshold-1,
    #   4. the next genuine terminal bump reaches threshold and PAGES -- a false
    #      alarm, because a maybe-delivered turn contributed to the threshold.
    #
    # The fix makes EVERY extra_json writer on this row merge-safe (json_set/
    # json_remove on its own key only). This test reproduces the exact interleave
    # and asserts: the merge-safe metadata write preserves the child's reset (does
    # NOT resurrect the counter), the counter writers preserve the worker key, and
    # the turn does NOT page.
    import json as _json

    control = load_module("arclink_control.py", "arclink_control_bridge_race")
    delivery = load_module("arclink_notification_delivery.py", "arclink_delivery_bridge_race")

    # File-backed DB: _record_public_agent_bridge_worker opens its OWN connect_db
    # (Config.from_env()), so it must point at the same on-disk database the test
    # row lives in -- exactly the production parent/child topology.
    config_dir = Path(tempfile.mkdtemp(prefix="arclink-bridge-race-"))
    db_path = config_dir / "control.sqlite3"
    config_path = config_dir / "operator.env"
    config_path.write_text(
        f"OPERATOR_NOTIFY_CHANNEL_PLATFORM={OPERATOR_PLATFORM}\n"
        f"OPERATOR_NOTIFY_CHANNEL_ID={OPERATOR_CHAT_ID}\n"
        f"ARCLINK_DB_PATH={db_path}\n",
        encoding="utf-8",
    )
    prior = os.environ.get("ARCLINK_CONFIG_FILE")
    os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
    try:
        cfg = control.Config.from_env()
        threshold = delivery._public_agent_bridge_hiccup_min_attempts()

        with control.connect_db(cfg) as conn:
            # Arm a turn at the brink: a consecutive-terminal run one short of paging.
            nid = control.queue_notification(
                conn,
                target_kind="public-agent-turn",
                target_id="tg:race-1",
                channel_kind="telegram",
                message="user message",
                extra={
                    "deployment_id": "arcdep_race",
                    delivery.PUBLIC_AGENT_BRIDGE_TERMINAL_FAILURE_KEY: threshold - 1,
                },
            )
            conn.commit()
            expect(
                _terminal_failure_count(control, conn, nid) == threshold - 1,
                "the row starts at the brink counter (threshold-1)",
            )

        # Reproduce the TRUE read-then-write window of the parent metadata write: the
        # child's reset must land AFTER the parent has read extra_json but BEFORE the
        # parent writes it. _record_public_agent_bridge_worker builds its worker dict
        # (calling utc_now_iso) BETWEEN its read and its write, so we hook utc_now_iso
        # to fire the child reset exactly once, in-window, on its OWN connection.
        # * OLD whole-dict writer: read sees counter=threshold-1 -> reset clears it to
        #   0 -> write serialises the STALE dict -> counter RESURRECTED to threshold-1.
        # * NEW merge-safe writer: no stale dict is held; the json_set touches only the
        #   worker key against the CURRENT row, so the reset survives (counter stays 0).
        original_now_iso = delivery.utc_now_iso
        reset_fired = {"done": False}

        def _now_iso_then_reset():
            value = original_now_iso()
            if not reset_fired["done"]:
                reset_fired["done"] = True
                # CHILD interleave: a maybe-delivered (D5) outcome resets the counter,
                # committed on a SEPARATE connection (as the real child would).
                with control.connect_db(cfg) as child_conn:
                    delivery._reset_public_agent_bridge_terminal_failures(child_conn, nid)
            return value

        delivery.utc_now_iso = _now_iso_then_reset
        try:
            # (PARENT) record worker metadata via the REAL writer (opens its own
            # connect_db at db_path -- same DB). The child reset fires mid-call.
            delivery._record_public_agent_bridge_worker(
                int(nid), pid=987654, job_path=Path(config_dir / "race-job.json")
            )
        finally:
            delivery.utc_now_iso = original_now_iso
        expect(reset_fired["done"], "the in-window child reset must have fired")

        with control.connect_db(cfg) as conn:
            # The merge-safe metadata write must NOT have resurrected the counter...
            expect(
                _terminal_failure_count(control, conn, nid) == 0,
                "the merge-safe metadata write must NOT resurrect the reset counter",
            )
            # ...and it MUST have written its own worker key (both writers coexist).
            after = _json.loads(
                str(conn.execute("SELECT extra_json FROM notification_outbox WHERE id = ?", (nid,)).fetchone()[0])
            )
            worker_meta = after.get("_public_agent_bridge_worker")
            expect(
                isinstance(worker_meta, dict) and int(worker_meta.get("pid") or 0) == 987654,
                f"the metadata write must persist the worker key, got {worker_meta!r}",
            )
            expect(
                after.get("deployment_id") == "arcdep_race",
                "the merge-safe writes must preserve unrelated extra_json keys",
            )

            # (4) The next genuine terminal bump starts a FRESH run at 1, NOT
            # threshold -> the turn does NOT page (the maybe-delivered outcome never
            # contributes to the threshold).
            delivery._maybe_report_public_agent_bridge_hiccup(conn, nid, error="terminal after race")
            expect(
                _terminal_failure_count(control, conn, nid) == 1,
                "the post-race terminal error starts a fresh consecutive run at 1",
            )
            expect(
                len(_operator_notices(conn)) == 0,
                "a maybe-delivered turn must NOT be resurrected into a false-alarm page",
            )

            # Symmetric direction: a counter bump must NOT clobber the worker key.
            delivery._bump_public_agent_bridge_terminal_failures(conn, nid)
            still = _json.loads(
                str(conn.execute("SELECT extra_json FROM notification_outbox WHERE id = ?", (nid,)).fetchone()[0])
            )
            expect(
                isinstance(still.get("_public_agent_bridge_worker"), dict),
                "a counter bump must NOT clobber the worker-metadata key",
            )
    finally:
        if prior is None:
            os.environ.pop("ARCLINK_CONFIG_FILE", None)
        else:
            os.environ["ARCLINK_CONFIG_FILE"] = prior
    print("PASS test_bridge_worker_metadata_write_race_does_not_resurrect_counter")


# ---------------------------------------------------------------------------
# Wired source (b): deployment provisioning exhausted (terminal)
# ---------------------------------------------------------------------------


def test_provisioning_terminal_failure_notifies_once() -> None:
    control = load_module("arclink_control.py", "arclink_control_prov_terminal")
    worker = load_module("arclink_sovereign_worker.py", "arclink_sovereign_prov_terminal")
    conn = memory_db(control)
    operator_cfg(control)
    config_dir = Path(tempfile.mkdtemp(prefix="arclink-prov-cfg-"))
    config_path = config_dir / "operator.env"
    config_path.write_text(
        f"OPERATOR_NOTIFY_CHANNEL_PLATFORM={OPERATOR_PLATFORM}\n"
        f"OPERATOR_NOTIFY_CHANNEL_ID={OPERATOR_CHAT_ID}\n",
        encoding="utf-8",
    )
    os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)

    worker._report_provisioning_failed_operator_hiccup(
        conn,
        deployment_id="arcdep_terminal",
        job_id="job-1",
        reason="max_attempts_exhausted",
        error="docker compose up failed",
    )
    notices = _operator_notices(conn)
    expect(len(notices) == 1, f"a terminally-failed deployment notifies once, got {len(notices)}")
    expect("arcdep_terminal" in notices[0]["message"], str(notices[0]))

    # A second worker pass for the same deployment must dedup.
    worker._report_provisioning_failed_operator_hiccup(
        conn,
        deployment_id="arcdep_terminal",
        job_id="job-1",
        reason="max_attempts_exhausted_after_failure",
        error="docker compose up failed again",
    )
    expect(len(_operator_notices(conn)) == 1, "repeated terminal passes dedup to one notice")
    print("PASS test_provisioning_terminal_failure_notifies_once")


def main() -> int:
    test_real_failure_notifies_once()
    test_repeated_failures_dedup_to_one_notice()
    test_dedup_survives_undelivered_notice()
    test_rearm_after_resolved()
    test_resolve_is_noop_when_not_armed()
    test_distinct_keys_each_notify()
    test_tui_only_operator_is_safe_noop()
    test_empty_key_rejected()
    test_bridge_transient_failure_does_not_notify()
    test_bridge_terminal_failure_notifies_once()
    test_bridge_unconfirmed_increments_then_one_terminal_does_not_page()
    test_bridge_unconfirmed_resets_a_partial_terminal_run()
    test_bridge_delivered_row_does_not_notify()
    test_bridge_page_then_deliver_resolves_alert()
    test_bridge_real_delivery_success_resolves_armed_alert()
    test_bridge_public_bot_user_error_does_not_page_as_bridge()
    test_bridge_d5_held_and_deferred_outcomes_do_not_page()
    test_bridge_worker_metadata_write_race_does_not_resurrect_counter()
    test_provisioning_terminal_failure_notifies_once()
    print("ALL operator-hiccup tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
