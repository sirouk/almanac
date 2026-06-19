#!/usr/bin/env python3
"""Deliver queued ArcLink notifications to Discord, Telegram, or the TUI-only outbox.

Runs as a periodic/oneshot service. Idempotent: only picks up rows with
`delivered_at IS NULL`. Records per-row errors in `delivery_error` without blocking
the batch.

The TUI-only channel is intentionally a no-op delivery: it marks the row delivered
so it drops out of the undelivered queue but remains readable via
`arclink-ctl notifications list` and via MCP `notifications.list`.
"""
from __future__ import annotations

import argparse
import secrets
import json
import os
import re
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from arclink_control import (
    Config,
    active_deploy_operation,
    config_env_value,
    connect_db,
    consume_curator_brief_fanout,
    fetch_undelivered_notifications,
    has_pending_curator_brief_fanout,
    mark_notification_delivered,
    mark_notification_delivered_if_owned,
    mark_notification_error,
    mark_notification_error_if_owned,
    parse_utc_iso,
    report_operator_hiccup,
    resolve_operator_hiccup,
    utc_now,
    utc_after_seconds_iso,
    utc_now_iso,
)
from arclink_control import _notification_token_guard_sql
from arclink_discord import discord_create_dm_channel, discord_edit_message, discord_send_message
from arclink_http import http_request
from arclink_telegram import telegram_edit_message_text, telegram_send_message


def _http_post_json(url: str, payload: dict, headers: dict[str, str] | None = None, timeout: int = 10) -> tuple[int, str]:
    request_headers = {"Content-Type": "application/json"}
    request_headers.update(headers or {})
    response = http_request(
        url,
        method="POST",
        headers=request_headers,
        json_payload=payload,
        timeout=timeout,
        allow_loopback_http=False,
    )
    return response.status_code, response.text


def deliver_discord(message: str, *, webhook_url: str) -> str | None:
    if not webhook_url:
        return "discord webhook URL is not configured"
    if not (webhook_url.startswith("https://discord.com/api/webhooks/") or
            webhook_url.startswith("https://discordapp.com/api/webhooks/")):
        return f"discord target does not look like a webhook URL: {webhook_url[:60]}"
    # Discord hard-caps content at 2000 chars; truncate defensively.
    content = message if len(message) <= 1900 else message[:1897] + "..."
    status, body = _http_post_json(webhook_url, {"content": content})
    if status >= 300:
        return f"discord http {status}: {body[:200]}"
    return None


def deliver_discord_channel(
    message: str,
    *,
    bot_token: str,
    channel_id: str,
    components: list[dict[str, Any]] | None = None,
    embeds: list[dict[str, Any]] | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> str | None:
    if not bot_token:
        return "DISCORD_BOT_TOKEN is not configured"
    if not channel_id:
        return "discord channel_id is empty"
    if not channel_id.isdigit():
        return f"discord channel_id must be numeric, got {channel_id[:60]!r}"
    try:
        kwargs: dict[str, Any] = {
            "bot_token": bot_token,
            "channel_id": channel_id,
            "text": message,
            "components": components,
        }
        if embeds is not None:
            kwargs["embeds"] = embeds
        if attachments is not None:
            kwargs["attachments"] = attachments
        discord_send_message(**kwargs)
    except Exception as exc:  # noqa: BLE001
        return str(exc).strip() or "unknown discord delivery error"
    return None


def deliver_discord_user(
    message: str,
    *,
    bot_token: str,
    user_id: str,
    components: list[dict[str, Any]] | None = None,
    embeds: list[dict[str, Any]] | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> str | None:
    if not bot_token:
        return "DISCORD_BOT_TOKEN is not configured"
    if not user_id:
        return "discord user_id is empty"
    if not user_id.isdigit():
        return f"discord user_id must be numeric, got {user_id[:60]!r}"
    try:
        dm = discord_create_dm_channel(bot_token=bot_token, recipient_id=user_id)
        channel_id = str(dm.get("id") or "").strip()
        if not channel_id:
            return "discord DM channel response did not include an id"
        kwargs = {
            "bot_token": bot_token,
            "channel_id": channel_id,
            "text": message,
            "components": components,
        }
        if embeds is not None:
            kwargs["embeds"] = embeds
        if attachments is not None:
            kwargs["attachments"] = attachments
        discord_send_message(**kwargs)
    except Exception as exc:  # noqa: BLE001
        return str(exc).strip() or "unknown discord user delivery error"
    return None


def _discord_payload_list(extra: dict[str, Any], key: str) -> list[dict[str, Any]] | None:
    value = extra.get(key)
    if not isinstance(value, list):
        return None
    safe: list[dict[str, Any]] = []
    for item in value[:10]:
        if isinstance(item, dict):
            safe.append(dict(item))
    return safe or None


def deliver_telegram(
    message: str,
    *,
    bot_token: str,
    chat_id: str,
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str = "",
    entities: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    reply_to_message_id: int | None = None,
) -> str | None:
    if not bot_token:
        return "TELEGRAM_BOT_TOKEN is not configured"
    if not chat_id:
        return "telegram chat_id is empty"
    try:
        kwargs: dict[str, Any] = {
            "bot_token": bot_token,
            "chat_id": chat_id,
            "text": message,
            "reply_markup": reply_markup,
            "parse_mode": parse_mode,
            "reply_to_message_id": reply_to_message_id,
        }
        if entities:
            kwargs["entities"] = entities
        telegram_send_message(**kwargs)
    except Exception as exc:  # noqa: BLE001
        return str(exc).strip() or "unknown telegram delivery error"
    return None


def _provisioning_message_ref(conn: Any, *, session_id: str, channel: str) -> dict[str, str]:
    clean_session_id = str(session_id or "").strip()
    clean_channel = str(channel or "").strip().lower()
    if not clean_session_id or clean_channel not in {"telegram", "discord"}:
        return {}
    try:
        row = conn.execute(
            "SELECT metadata_json FROM arclink_onboarding_sessions WHERE session_id = ?",
            (clean_session_id,),
        ).fetchone()
    except Exception:  # noqa: BLE001 - delivery fallback should still send.
        return {}
    if row is None:
        return {}
    try:
        metadata = json.loads(str(row["metadata_json"] or "{}"))
    except (TypeError, json.JSONDecodeError):
        metadata = {}
    if not isinstance(metadata, dict):
        return {}
    refs = metadata.get("public_bot_provisioning_messages")
    if not isinstance(refs, dict):
        return {}
    ref = refs.get(clean_channel)
    if not isinstance(ref, dict):
        return {}
    return {str(key): str(value) for key, value in ref.items() if str(value or "").strip()}


def _store_provisioning_message_ref(
    conn: Any,
    *,
    session_id: str,
    channel: str,
    message_id: str,
    channel_id: str = "",
) -> None:
    clean_session_id = str(session_id or "").strip()
    clean_channel = str(channel or "").strip().lower()
    clean_message_id = str(message_id or "").strip()
    if not clean_session_id or clean_channel not in {"telegram", "discord"} or not clean_message_id:
        return
    try:
        row = conn.execute(
            "SELECT metadata_json FROM arclink_onboarding_sessions WHERE session_id = ?",
            (clean_session_id,),
        ).fetchone()
        if row is None:
            return
        metadata = json.loads(str(row["metadata_json"] or "{}"))
        if not isinstance(metadata, dict):
            metadata = {}
    except (TypeError, json.JSONDecodeError):
        metadata = {}
    refs = metadata.get("public_bot_provisioning_messages")
    if not isinstance(refs, dict):
        refs = {}
    ref = {"message_id": clean_message_id, "updated_at": utc_now_iso()}
    if channel_id:
        ref["channel_id"] = str(channel_id)
    refs[clean_channel] = ref
    metadata["public_bot_provisioning_messages"] = refs
    conn.execute(
        """
        UPDATE arclink_onboarding_sessions
        SET metadata_json = ?, updated_at = ?
        WHERE session_id = ?
        """,
        (json.dumps(metadata, sort_keys=True), utc_now_iso(), clean_session_id),
    )
    conn.commit()


def _read_env_file_value(path: Path, key: str) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() != key:
            continue
        return value.strip().strip("'\"")
    return ""


def _discord_target_kind(value: str) -> str:
    target = value.strip()
    if not target:
        return ""
    if (
        target.startswith("https://discord.com/api/webhooks/")
        or target.startswith("https://discordapp.com/api/webhooks/")
    ):
        return "webhook"
    if target.isdigit():
        return "channel"
    return ""


def _resolve_curator_discord_bot_token(cfg: Config) -> str:
    token = config_env_value("DISCORD_BOT_TOKEN", "").strip()
    if token:
        return token
    return _read_env_file_value(cfg.curator_hermes_home / ".env", "DISCORD_BOT_TOKEN").strip()


def _resolve_discord_target(cfg: Config, row: dict[str, Any]) -> tuple[str, str]:
    """Resolve the current Discord operator target.

    Preferred order is the per-row target_id, then the configured operator
    channel id, then the legacy DISCORD_WEBHOOK_URL env var.
    """
    candidates = [
        str(row.get("target_id") or "").strip(),
        str(cfg.operator_notify_channel_id or "").strip(),
        config_env_value("DISCORD_WEBHOOK_URL", "").strip(),
    ]
    for value in candidates:
        kind = _discord_target_kind(value)
        if kind:
            return kind, value
    return "", ""


def _operator_platform(cfg: Config, row: dict[str, Any]) -> str:
    """The channel_kind we stamped at enqueue time wins; else fall back to
    the configured operator platform."""
    channel_kind = (row.get("channel_kind") or "").lower()
    if channel_kind in ("discord", "telegram", "tui-only"):
        return channel_kind
    return (cfg.operator_notify_platform or "tui-only").lower()


def _strip_public_channel_prefix(target_id: str, prefix: str) -> str:
    value = str(target_id or "").strip()
    marker = f"{prefix}:"
    if value.lower().startswith(marker):
        return value[len(marker):].strip()
    return value


ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
PUBLIC_AGENT_BRIDGE_DEFERRED = "DEFERRED_TO_PUBLIC_AGENT_BRIDGE"
PUBLIC_AGENT_BRIDGE_UNCONFIRMED = "PROCESSED_UNCONFIRMED_BY_PUBLIC_AGENT_BRIDGE"
PUBLIC_AGENT_BRIDGE_PYTHON = "/opt/arclink/runtime/hermes-venv/bin/python3"
PUBLIC_AGENT_BRIDGE_SCRIPT = "/home/arclink/arclink/python/arclink_public_agent_bridge.py"
PUBLIC_AGENT_BRIDGE_ROOT_WRAPPER_SCRIPT = "/home/arclink/arclink/python/arclink_public_agent_bridge_root.py"
PUBLIC_AGENT_BRIDGE_ROOT_USER = "0:0"
PUBLIC_AGENT_BRIDGE_CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
PUBLIC_AGENT_BRIDGE_PROJECT_RE = re.compile(r"^arclink(?:-[a-z0-9][a-z0-9_-]{0,80})?$")
GATEWAY_EXEC_BROKER_TOKEN_HEADER = "X-ArcLink-Gateway-Exec-Token"

# --- Operator hiccup: public-Agent bridge TERMINAL delivery failure ---------
#
# What counts as a REAL hiccup here (vs. transient / self-healing):
#   * NOT a "deferred" turn (PUBLIC_AGENT_BRIDGE_DEFERRED) -- the bridge is still
#     running; the row is leased, not failed.
#   * NOT an "unconfirmed" / hold-for-reconciliation turn (delivery_status
#     "unknown", or "failed" WITH platform message ids) -- this is the D5 case
#     where the turn may STILL have delivered; it is explicitly held and
#     reconciled for up to 24h, so paging now would be a false alarm.
#   * NOT a single terminal error -- public-agent-turn rows have NO max-attempt
#     cap; mark_notification_error() schedules a RETRY with exponential backoff,
#     so the very next attempt may self-heal. Paging on the first error would be
#     a false alarm.
# A real, terminal hiccup is a turn that has accumulated MANY CONSECUTIVE genuine
# terminal-error attempts (returncode!=0, timeout, delivery_status=="failed" with
# no message ids, rejected command, or no-ok) -- i.e. retries are clearly not
# self-healing. We gate on a per-row CONSECUTIVE-terminal-failure counter (NOT on
# the row's attempt_count column) >= the threshold below, so a turn that recovers
# on an early retry -- or whose attempt_count was inflated by non-terminal "maybe
# delivered" outcomes -- never pages the Operator. Dedup is per outbox row id (one
# notice per stuck turn).
#
# THREE guards make this self-correcting (BUG #1 fix), so the Operator only ends up
# with bridge alerts for turns that are GENUINELY, PERSISTENTLY failing:
#   1. consecutive-terminal threshold (below) -- a turn that recovers on an early
#      retry never reaches the gate. We count ONLY genuine terminal errors, in a
#      run: any non-terminal/uncertain outcome (deferred, or D5 held/unconfirmed,
#      which may actually have delivered) RESETS the counter to 0. This is the core
#      BUG #1 fix: gating on attempt_count would let e.g. 7 maybe-delivered turns +
#      1 terminal error cross an "8 attempts" threshold and page -- a false alarm.
#      Gating on the consecutive-terminal counter means only 8 terminal errors in a
#      row -- never interleaved with a maybe-delivered outcome -- can page.
#   2. resolve-on-delivery (_resolve_public_agent_bridge_hiccup, called at every
#      public-agent-turn delivery-success site) -- public-agent-turn rows have NO
#      max-attempt cap, so a turn that pages at attempt N can still self-heal and
#      be marked delivered at attempt N+1. When that happens we resolve the alert
#      for that row's key, so a recovered turn clears its own page. Only turns that
#      STAY failed leave a lingering alert.
#   3. delivered-row short-circuit -- a delivered row never reaches the gate, and
#      its counter is moot (the gate returns early for a delivered row).
#
# Threshold reasoning (raised 5 -> 8): a single user turn already survives several
# layers of self-healing retry before it ever counts as one "terminal attempt"
# here -- the agent's own in-process LLM retries (~3), plus a couple of bridge-
# level retries with exponential backoff. An ordinary transient blip (e.g. an LLM
# connection error that recovers within those layers) must NOT page. 5 was low
# enough that a noisy-but-recovering turn could cross it before delivering; 8
# consecutive genuine terminal-error attempts (each already past the agent's inner
# retries, spread over ~hours of exponential backoff) is a clear "retries are not
# self-healing" signal. Combined with resolve-on-delivery, a turn that crosses 8
# and then finally delivers still clears its alert, so the net effect is: persistent
# failure only. Override via ARCLINK_PUBLIC_AGENT_BRIDGE_HICCUP_MIN_ATTEMPTS.
PUBLIC_AGENT_BRIDGE_HICCUP_MIN_ATTEMPTS_DEFAULT = 8


def _public_agent_bridge_hiccup_min_attempts() -> int:
    return _int_env(
        "ARCLINK_PUBLIC_AGENT_BRIDGE_HICCUP_MIN_ATTEMPTS",
        PUBLIC_AGENT_BRIDGE_HICCUP_MIN_ATTEMPTS_DEFAULT,
        minimum=2,
        maximum=100,
    )


# BUG #1 fix: the per-outbox-row extra_json key under which we track a turn's
# CONSECUTIVE genuine-terminal-failure count. This is deliberately separate from
# ``attempt_count`` (the row column): attempt_count is bumped for BOTH terminal
# errors (mark_notification_error) AND non-terminal "maybe delivered" outcomes
# (_mark_public_agent_bridge_unconfirmed -- D5 held/unknown), so gating the
# Operator page on attempt_count would page a turn that had e.g. 7 unconfirmed
# (possibly-delivered) outcomes + 1 terminal error -- a false alarm. Instead we
# gate on this counter, which is incremented ONLY at genuine terminal-error sites
# and RESET to 0 on any non-terminal/uncertain outcome (held/unconfirmed/deferred)
# AND on delivery. Net: only a turn that strings together N CONSECUTIVE genuine
# terminal errors -- never interleaved with a maybe-delivered outcome -- can page.
PUBLIC_AGENT_BRIDGE_TERMINAL_FAILURE_KEY = "_public_agent_bridge_consecutive_terminal_failures"

# M3 fix: a turn that the bridge reports as ok-but-unconfirmed (held for
# reconciliation, no message ids) is NON-terminal, so the terminal-failure gate
# deliberately excludes it -- but a stuck "delivers but never confirms" outage
# would then page the operator NEVER, a silent blind spot. We track a separate
# consecutive-UNCONFIRMED counter and escalate via a DISTINCT operator hiccup key
# once a turn stays unconfirmed across too many cycles, so the blind spot is
# observable without conflating it with the terminal-failure gate.
PUBLIC_AGENT_BRIDGE_UNCONFIRMED_COUNT_KEY = "_public_agent_bridge_consecutive_unconfirmed"


def _public_agent_bridge_unconfirmed_count_json_path() -> str:
    return f"$.{PUBLIC_AGENT_BRIDGE_UNCONFIRMED_COUNT_KEY}"


def _public_agent_bridge_unconfirmed_escalate_after() -> int:
    """How many CONSECUTIVE unconfirmed cycles before the operator is paged (M3)."""
    return _int_env(
        "ARCLINK_PUBLIC_AGENT_BRIDGE_UNCONFIRMED_ESCALATE_AFTER",
        3,
        minimum=2,
        maximum=100,
    )


def _public_agent_bridge_terminal_failure_json_path() -> str:
    """SQLite ``json`` path for the consecutive-terminal-failure key.

    The key never contains JSON-path metacharacters, so the literal ``$.<key>``
    form is safe; we centralise it so every merge-safe writer uses the same path.
    """
    return f"$.{PUBLIC_AGENT_BRIDGE_TERMINAL_FAILURE_KEY}"


# C1 fix: the per-outbox-row extra_json path under which a detached worker records
# the unique lease token it owns. Every terminal write from a detached worker is
# guarded on this path so a worker whose pid was recycled and whose row was
# re-leased to a NEW worker (different token) is a NO-OP -- only the worker that
# currently owns the lease can finalise the row. The token never contains JSON-path
# metacharacters, so the literal nested ``$._public_agent_bridge_worker.token`` form
# is safe.
PUBLIC_AGENT_BRIDGE_WORKER_TOKEN_JSON_PATH = "$._public_agent_bridge_worker.token"


def _bump_public_agent_bridge_terminal_failures(conn: Any, notification_id: int) -> int:
    """Increment and persist the row's consecutive-terminal-failure counter.

    Called ONLY from genuine terminal-error sites (via the hiccup gate). Returns
    the NEW count (0 when the row is missing/delivered and nothing was written).

    BUG #1 fix -- MERGE-SAFE write: the increment is done with a single atomic
    ``UPDATE ... SET extra_json = json_set(..., +1)`` statement that reads AND
    writes the on-disk row value inside SQLite's per-row write lock, touching ONLY
    the counter key. It never serialises a whole Python dict back, so a concurrent
    writer of a DIFFERENT key on this same row (the parent's worker-metadata write
    in _record_public_agent_bridge_worker, or the orphan reaper) can never clobber
    this counter, and this bump can never clobber their keys. This closes the
    parent/child stale-extra_json RACE that could resurrect a reset counter and
    page on a maybe-delivered turn. We then re-read the freshly-persisted value so
    the gate's threshold check sees exactly this row's current counter.
    """
    cursor = conn.execute(
        """
        UPDATE notification_outbox
        SET extra_json = json_set(
            COALESCE(extra_json, '{}'),
            ?,
            COALESCE(
                CAST(json_extract(COALESCE(extra_json, '{}'), ?) AS INTEGER),
                0
            ) + 1
        )
        WHERE id = ? AND delivered_at IS NULL
        """,
        (
            _public_agent_bridge_terminal_failure_json_path(),
            _public_agent_bridge_terminal_failure_json_path(),
            int(notification_id),
        ),
    )
    conn.commit()
    if int(getattr(cursor, "rowcount", 0) or 0) <= 0:
        # Row missing or already delivered -- nothing was written.
        return 0
    row = conn.execute(
        "SELECT json_extract(COALESCE(extra_json, '{}'), ?) AS count FROM notification_outbox WHERE id = ?",
        (_public_agent_bridge_terminal_failure_json_path(), int(notification_id)),
    ).fetchone()
    if row is None:
        return 0
    try:
        count = int(row["count"])
    except (TypeError, ValueError):
        count = 1
    return count if count >= 1 else 1


def _reset_public_agent_bridge_terminal_failures(conn: Any, notification_id: int) -> None:
    """Reset the row's consecutive-terminal-failure counter to 0 (best-effort).

    Called on EVERY non-terminal/uncertain outcome (held/unconfirmed/deferred) and
    on delivery, so a "maybe delivered" turn never carries terminal credit forward.
    Best-effort and fail-closed: any error is swallowed so counter bookkeeping can
    never break delivery. A missing key is left absent (treated as 0 by the gate).

    BUG #1 fix -- MERGE-SAFE write: the reset is a single atomic
    ``UPDATE ... SET extra_json = json_remove(..., <counter-key>)`` statement that
    removes ONLY the counter key inside SQLite's per-row write lock. It never reads
    a whole Python dict and writes it back, so the parent's concurrent
    worker-metadata write (or the orphan reaper) cannot be clobbered by this reset,
    and the parent's STALE whole-dict write can no longer resurrect a counter this
    reset cleared -- the exact parent/child race in BUG #1. ``json_remove`` of an
    absent path is a no-op, so a row without the key is left untouched.
    """
    try:
        conn.execute(
            """
            UPDATE notification_outbox
            SET extra_json = json_remove(COALESCE(extra_json, '{}'), ?)
            WHERE id = ? AND delivered_at IS NULL
            """,
            (_public_agent_bridge_terminal_failure_json_path(), int(notification_id)),
        )
        conn.commit()
    except Exception:  # noqa: BLE001 - counter bookkeeping must never break delivery.
        return


def _bump_public_agent_bridge_unconfirmed_count(conn: Any, notification_id: int) -> int:
    """M3: increment and return the row's consecutive-unconfirmed counter.

    Merge-safe (single atomic json_set, same pattern as the terminal-failure
    counter) so it never clobbers a concurrent writer of another key on the row.
    Returns the new count (0 when the row is missing/delivered).
    """
    path = _public_agent_bridge_unconfirmed_count_json_path()
    cursor = conn.execute(
        """
        UPDATE notification_outbox
        SET extra_json = json_set(
            COALESCE(extra_json, '{}'),
            ?,
            COALESCE(CAST(json_extract(COALESCE(extra_json, '{}'), ?) AS INTEGER), 0) + 1
        )
        WHERE id = ? AND delivered_at IS NULL
        """,
        (path, path, int(notification_id)),
    )
    conn.commit()
    if int(getattr(cursor, "rowcount", 0) or 0) <= 0:
        return 0
    row = conn.execute(
        "SELECT json_extract(COALESCE(extra_json, '{}'), ?) AS count FROM notification_outbox WHERE id = ?",
        (path, int(notification_id)),
    ).fetchone()
    if row is None:
        return 0
    try:
        count = int(row["count"])
    except (TypeError, ValueError):
        count = 1
    return count if count >= 1 else 1


def _reset_public_agent_bridge_unconfirmed_count(conn: Any, notification_id: int) -> None:
    """M3: clear the consecutive-unconfirmed counter (best-effort, fail-closed).

    Called on delivery and on any genuine TERMINAL error so the unconfirmed run is
    only ever a run of CONSECUTIVE unconfirmed cycles.
    """
    try:
        conn.execute(
            """
            UPDATE notification_outbox
            SET extra_json = json_remove(COALESCE(extra_json, '{}'), ?)
            WHERE id = ?
            """,
            (_public_agent_bridge_unconfirmed_count_json_path(), int(notification_id)),
        )
        conn.commit()
    except Exception:  # noqa: BLE001 - counter bookkeeping must never break delivery.
        return


def _public_agent_bridge_unconfirmed_hiccup_key(notification_id: int) -> str:
    """M3: distinct operator-hiccup key for the unconfirmed-escalation blind spot.

    Deliberately separate from _public_agent_bridge_hiccup_key (the terminal-failure
    gate) so a "delivers but never confirms" outage is observable on its own and
    does not conflate with genuine terminal failures.
    """
    return f"public_agent_bridge_unconfirmed:{int(notification_id)}"


def _maybe_escalate_public_agent_bridge_unconfirmed(conn: Any, notification_id: int) -> None:
    """M3: page the operator once a turn stays UNCONFIRMED across too many cycles.

    Bumps the consecutive-unconfirmed counter and, once it crosses the threshold,
    reports a hiccup under the distinct unconfirmed key. Best-effort/fail-closed so
    it can never break delivery. The alert re-arms on delivery via the resolve path.
    """
    try:
        count = _bump_public_agent_bridge_unconfirmed_count(conn, notification_id)
        if count < _public_agent_bridge_unconfirmed_escalate_after():
            return
        cfg = Config.from_env()
        message = (
            "ArcLink public-agent bridge has been UNCONFIRMED (delivered through "
            f"the gateway but never confirmed on the platform) for {count} "
            f"consecutive cycles (notification #{int(notification_id)}). This is the "
            "\"delivers but never confirms\" blind spot -- the platform send may be "
            "silently failing even though the turn keeps reporting ok."
        )
        report_operator_hiccup(
            conn,
            cfg,
            source="public_agent_bridge_unconfirmed",
            key=_public_agent_bridge_unconfirmed_hiccup_key(notification_id),
            message=message,
            reason=f"public-agent bridge turn unconfirmed for {count} consecutive cycles",
        )
    except Exception:  # noqa: BLE001 - escalation must never break delivery.
        return


def _public_agent_bridge_hiccup_key(notification_id: int) -> str:
    """Per-row dedup/resolve key for a public-agent-turn hiccup.

    Shared by report (page) and resolve (clear-on-delivery) so a turn that pages
    and then recovers clears the SAME armed alert. The row id is unique, so each
    stuck turn is its own key and never spams across turns.
    """
    return f"public_agent_bridge_turn:{int(notification_id)}"


def _resolve_public_agent_bridge_hiccup(conn: Any, notification_id: int) -> None:
    """Clear a public-agent-turn's Operator alert when the turn finally delivers.

    BUG #1 fix (resolve-on-delivery): public-agent-turn rows have no max-attempt
    cap, so a turn that paged at the threshold can still self-heal on a later
    retry and be marked delivered. Calling this at every public-agent-turn
    delivery-success site re-arms the per-row key, so a recovered turn does not
    leave a lingering "could not deliver" alert -- only turns that STAY failed
    keep an armed alert. resolve_operator_hiccup is a no-op when the key was never
    armed (the common case: most turns deliver well before the threshold), so this
    adds no audit churn for healthy turns.

    Best-effort and fail-closed: any error is swallowed so resolve bookkeeping can
    never break delivery (exactly like the report path).
    """
    try:
        cfg = Config.from_env()
        resolve_operator_hiccup(
            conn,
            cfg,
            source="public_agent_bridge",
            key=_public_agent_bridge_hiccup_key(notification_id),
            reason="public-agent bridge turn delivered after prior terminal attempts",
        )
        # M3: a delivered turn also clears any unconfirmed-escalation alert (and its
        # consecutive-unconfirmed counter) for the same row.
        resolve_operator_hiccup(
            conn,
            cfg,
            source="public_agent_bridge_unconfirmed",
            key=_public_agent_bridge_unconfirmed_hiccup_key(notification_id),
            reason="public-agent bridge turn confirmed-delivered after prior unconfirmed cycles",
        )
        _reset_public_agent_bridge_unconfirmed_count(conn, notification_id)
    except Exception:  # noqa: BLE001 - resolve bookkeeping must never break delivery.
        return


def _maybe_report_public_agent_bridge_hiccup(
    conn: Any,
    notification_id: int,
    *,
    error: str,
) -> None:
    """Page the Operator when a single public-Agent turn is terminally stuck.

    Call this ONLY at genuine terminal-error sites (returncode!=0, timeout,
    delivery_status=="failed" with no message ids, rejected command, no-ok) for a
    ``public-agent-turn`` row -- never for generic ``public-bot-user`` sends, and
    never for deferred, unconfirmed/hold-for-reconciliation, or delivered
    outcomes. Because this is only ever called at a genuine terminal-error site, it
    is also where we INCREMENT the per-row consecutive-terminal-failure counter
    (BUG #1). The gate then pages on THAT counter -- not on ``attempt_count`` -- so
    a turn whose attempt_count was inflated by non-terminal "maybe delivered" (D5
    held/unconfirmed) outcomes can never cross the threshold: any such outcome
    RESETS the counter via _reset_public_agent_bridge_terminal_failures, so only a
    run of N CONSECUTIVE genuine terminal errors (never interleaved with a maybe-
    delivered outcome) pages. Combined with resolve-on-delivery, the Operator only
    ever sees a bridge alert for a turn that is GENUINELY, PERSISTENTLY failing.

    Best-effort and fail-closed: any error resolving config / reading the row is
    swallowed so hiccup reporting can never break delivery. Resolving the operator
    target from Config (not os.environ) is handled inside report_operator_hiccup.
    """
    try:
        row = conn.execute(
            "SELECT target_kind, attempt_count, delivered_at FROM notification_outbox WHERE id = ?",
            (int(notification_id),),
        ).fetchone()
        if row is None:
            return
        target_kind = str(row["target_kind"] or "").strip().lower()
        # BUG #1b fix: scope the bridge alert to the public-agent-BRIDGE turn kind
        # ONLY. Generic ``public-bot-user`` sends (provisioning hub edits, ordinary
        # missing-token/missing-target errors in _deliver_public_bot_user) are NOT
        # bridge turns -- paging them as "public-agent bridge could not deliver a
        # turn" is both wrong-sourced and a false alarm (those rows are not the
        # streaming bridge path and have their own retry/handling). Only a
        # public-agent-turn row is a bridge turn.
        if target_kind != "public-agent-turn":
            return
        # A delivered row is a success, never a hiccup.
        if str(row["delivered_at"] or "").strip():
            return
        # M3: a genuine terminal error breaks any consecutive-unconfirmed run, so
        # clear that counter -- the unconfirmed escalation only fires for an
        # uninterrupted run of "delivers but never confirms" cycles.
        _reset_public_agent_bridge_unconfirmed_count(conn, notification_id)
        # BUG #1 fix: this site IS a genuine terminal error, so credit one
        # CONSECUTIVE terminal failure to the same row the gate reads, then gate on
        # that counter. We deliberately do NOT use attempt_count here: attempt_count
        # also counts non-terminal "maybe delivered" outcomes (D5 held/unconfirmed),
        # which would let e.g. 7 possibly-delivered turns + 1 terminal error cross
        # the threshold and page as "8 terminal attempts" -- a false alarm.
        consecutive_terminal = _bump_public_agent_bridge_terminal_failures(conn, notification_id)
        if consecutive_terminal < _public_agent_bridge_hiccup_min_attempts():
            return
        cfg = Config.from_env()
        # Per-row key: one Operator notice per terminally-stuck turn. The row id is
        # unique, so this never spams across turns. The alert re-arms only via
        # _resolve_public_agent_bridge_hiccup when this row is later delivered.
        key = _public_agent_bridge_hiccup_key(notification_id)
        message = (
            "ArcLink public-agent bridge could not deliver a turn after "
            f"{consecutive_terminal} consecutive terminal attempts "
            f"(notification #{int(notification_id)}). "
            "The user's last message may not have been answered on their public "
            f"channel.\nLast error: {str(error or '').strip()[:300]}"
        )
        report_operator_hiccup(
            conn,
            cfg,
            source="public_agent_bridge",
            key=key,
            message=message,
            reason=(
                "public-agent bridge turn stuck after "
                f"{consecutive_terminal} consecutive terminal attempts"
            ),
            extra={
                "notification_id": int(notification_id),
                "consecutive_terminal_failures": consecutive_terminal,
            },
        )
    except Exception:  # noqa: BLE001 - hiccup reporting must never break delivery.
        return


def _int_env(name: str, default: int, *, minimum: int = 1, maximum: int = 1800) -> int:
    raw = config_env_value(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _notification_due_now(row: dict[str, Any]) -> bool:
    next_attempt_at = str(row.get("next_attempt_at") or "").strip()
    if not next_attempt_at:
        return True
    parsed = parse_utc_iso(next_attempt_at)
    return parsed is not None and parsed <= utc_now()


def _compose_project_name(deployment_id: str) -> str:
    clean = re.sub(r"[^a-z0-9_-]+", "-", str(deployment_id or "").strip().lower()).strip("-_")
    return f"arclink-{clean}" if clean else ""


def _gateway_exec_broker_url() -> str:
    return config_env_value("ARCLINK_GATEWAY_EXEC_BROKER_URL", "").strip().rstrip("/")


def _gateway_exec_broker_token() -> str:
    return config_env_value("ARCLINK_GATEWAY_EXEC_BROKER_TOKEN", "").strip()


def _gateway_exec_broker_request(
    *,
    deployment_id: str,
    prefix: str,
    project_name: str,
    payload: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    return {
        "deployment_id": str(deployment_id or "").strip(),
        "prefix": str(prefix or "").strip(),
        "project_name": str(project_name or "").strip(),
        "payload": payload,
        "timeout_seconds": int(timeout_seconds),
    }


def _operator_gateway_exec_broker_request(
    *,
    project_name: str,
    payload: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    return {
        "operator_stack": True,
        "project_name": str(project_name or "").strip(),
        "payload": payload,
        "timeout_seconds": int(timeout_seconds),
    }


def _bridge_message_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    for item in value:
        clean = str(item or "").strip()
        if clean and clean not in ids:
            ids.append(clean)
    return ids


def public_agent_bridge_delivery_result(payload_out: Any) -> dict[str, Any]:
    """Normalize a bridge/broker response into ArcLink's delivery contract."""
    if not isinstance(payload_out, dict):
        return {
            "ok": False,
            "processed": False,
            "delivered": False,
            "delivery_status": "failed",
            "message_ids": [],
            "error": "Hermes public gateway bridge did not return a JSON object",
        }
    if payload_out.get("ok") is not True:
        return {
            "ok": False,
            "processed": False,
            "delivered": False,
            "delivery_status": "failed",
            "message_ids": [],
            "error": str(payload_out.get("error") or "Hermes public gateway bridge did not return ok")[:500],
        }
    message_ids = _bridge_message_ids(payload_out.get("message_ids"))
    raw_status = str(payload_out.get("delivery_status") or "").strip().lower()
    error = str(payload_out.get("delivery_error") or payload_out.get("error") or "").strip()
    if payload_out.get("delivered") is True and message_ids:
        status = "confirmed"
    elif raw_status == "failed":
        status = "failed"
    elif raw_status == "confirmed" and message_ids:
        status = "confirmed"
    else:
        status = "unknown"
        if not error:
            error = "Hermes public gateway bridge completed without confirmed platform message ids"
    return {
        "ok": True,
        "processed": bool(payload_out.get("processed", True)),
        "delivered": status == "confirmed",
        "delivery_status": status,
        "message_ids": message_ids,
        "error": error[:500],
    }


def _public_agent_bridge_unconfirmed_error(result: Mapping[str, Any]) -> str:
    status = str(result.get("delivery_status") or "unknown")
    error = str(result.get("error") or "").strip()
    suffix = f"{status}: {error}" if error else status
    return f"{PUBLIC_AGENT_BRIDGE_UNCONFIRMED}: {suffix}"[:500]


def _public_agent_bridge_should_hold_for_reconciliation(result: Mapping[str, Any]) -> bool:
    status = str(result.get("delivery_status") or "").strip().lower()
    if status == "unknown":
        return True
    return status == "failed" and bool(_bridge_message_ids(result.get("message_ids")))


def _public_agent_bridge_delivery_error(result: Mapping[str, Any], *, label: str) -> str:
    status = str(result.get("delivery_status") or "").strip().lower()
    error = str(result.get("error") or "").strip()
    if error:
        return error[:500]
    if status:
        return f"{label} ended with delivery_status={status}"[:500]
    return f"{label} completed without confirmed platform delivery"[:500]


def _is_public_agent_bridge_unconfirmed(error: Any) -> bool:
    return str(error or "").startswith(PUBLIC_AGENT_BRIDGE_UNCONFIRMED)


def _run_gateway_exec_broker_request(request_body: dict[str, Any]) -> tuple[bool, str]:
    broker_url = _gateway_exec_broker_url()
    if not broker_url:
        return False, "gateway exec broker URL is not configured"
    token = _gateway_exec_broker_token()
    if not token:
        return False, "gateway exec broker token is not configured"
    timeout_seconds = _int_env("ARCLINK_GATEWAY_EXEC_BROKER_TIMEOUT_SECONDS", 240, minimum=15, maximum=900)
    raw_timeout = request_body.get("timeout_seconds")
    try:
        timeout_seconds = max(timeout_seconds, min(86400, int(raw_timeout) + 30))
    except (TypeError, ValueError):
        pass
    payload_bytes = json.dumps(request_body, sort_keys=True).encode("utf-8")
    request = urllib.request.Request(
        f"{broker_url}/v1/public-agent-bridge",
        data=payload_bytes,
        method="POST",
        headers={
            "Content-Type": "application/json",
            GATEWAY_EXEC_BROKER_TOKEN_HEADER: token,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - internal broker URL
            body = response.read(65536).decode("utf-8", errors="replace")
            status = int(getattr(response, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        body = exc.read(65536).decode("utf-8", errors="replace")
        status = int(exc.code or 500)
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        return False, f"gateway exec broker request failed: {str(exc)[:180]}"
    try:
        parsed = json.loads(body or "{}")
    except json.JSONDecodeError:
        parsed = {}
    if 200 <= status < 300 and isinstance(parsed, dict) and parsed.get("ok") is True:
        result = public_agent_bridge_delivery_result(parsed)
        if result.get("delivered") is True:
            return True, ""
        if _public_agent_bridge_should_hold_for_reconciliation(result):
            return False, _public_agent_bridge_unconfirmed_error(result)
        return False, _public_agent_bridge_delivery_error(result, label="Hermes public gateway bridge")
    if isinstance(parsed, dict):
        error = str(parsed.get("error") or "").strip()
        if error:
            return False, error[:500]
    return False, f"gateway exec broker returned HTTP {status}"


def _deployment_root(*, deployment_id: str, prefix: str) -> Path | None:
    base = Path(config_env_value("ARCLINK_STATE_ROOT_BASE", "/arcdata/deployments") or "/arcdata/deployments")
    if deployment_id and prefix:
        candidate = base / f"{deployment_id}-{prefix}"
        if candidate.exists():
            return candidate
    if deployment_id:
        matches = sorted(base.glob(f"{deployment_id}-*"))
        if matches:
            return matches[0]
    return None


def _path_within(path: Path, base: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(base.resolve(strict=False))
    except (OSError, ValueError):
        return False
    return True


def _deployment_state_root_base() -> Path:
    return Path(config_env_value("ARCLINK_STATE_ROOT_BASE", "/arcdata/deployments") or "/arcdata/deployments")


def _validate_deployment_config_directory(path: Path, *, label: str, context: str) -> None:
    try:
        stat_result = path.lstat()
    except OSError as exc:
        raise ValueError(f"{context} {label} is missing") from exc
    if stat.S_ISLNK(stat_result.st_mode):
        raise ValueError(f"{context} {label} must not be a symlink")
    if not stat.S_ISDIR(stat_result.st_mode):
        raise ValueError(f"{context} {label} must be a directory")


def _validate_deployment_config_file(path: Path, *, label: str, context: str) -> None:
    try:
        stat_result = path.lstat()
    except OSError as exc:
        raise ValueError(f"{context} {label} is missing") from exc
    if stat.S_ISLNK(stat_result.st_mode):
        raise ValueError(f"{context} {label} must not be a symlink")
    if not stat.S_ISREG(stat_result.st_mode):
        raise ValueError(f"{context} {label} must be a regular file")
    if stat_result.st_mode & 0o444 == 0:
        raise ValueError(f"{context} {label} must be readable")


def _preflight_deployment_compose_config_files(
    *,
    env_file: Path,
    compose_file: Path,
    context: str,
) -> None:
    if env_file.name != "arclink.env" or compose_file.name != "compose.yaml":
        raise ValueError(f"{context} Compose files are not deployment config files")
    if env_file.parent != compose_file.parent or env_file.parent.name != "config":
        raise ValueError(f"{context} Compose files must share a deployment config directory")
    state_root = _deployment_state_root_base()
    if not _path_within(env_file, state_root) or not _path_within(compose_file, state_root):
        raise ValueError(f"{context} Compose files must stay under ARCLINK_STATE_ROOT_BASE")
    deployment_root = env_file.parent.parent
    _validate_deployment_config_directory(deployment_root, label="deployment root", context=context)
    _validate_deployment_config_directory(env_file.parent, label="config directory", context=context)
    _validate_deployment_config_file(env_file, label="config/arclink.env", context=context)
    _validate_deployment_config_file(compose_file, label="config/compose.yaml", context=context)


def _validate_public_agent_bridge_cmd(cmd: list[str], *, project_name: str = "") -> tuple[bool, str, str]:
    """Constrain detached public-Agent bridge jobs to one Docker operation.

    Detached jobs are stored on disk so the notification worker can release its
    lease while Hermes finishes. Treat that job file as data, not authority:
    only the two command shapes generated by this module are allowed.
    """
    parts = [str(part) for part in cmd]
    bridge_tail = [PUBLIC_AGENT_BRIDGE_PYTHON, PUBLIC_AGENT_BRIDGE_SCRIPT]
    root_wrapper_tail = [PUBLIC_AGENT_BRIDGE_PYTHON, PUBLIC_AGENT_BRIDGE_ROOT_WRAPPER_SCRIPT]
    expected_project = str(project_name or "").strip()

    root_wrapper_exec = (
        len(parts) == 8
        and parts[:3] == ["docker", "exec", "-i"]
        and parts[3:5] == ["-u", PUBLIC_AGENT_BRIDGE_ROOT_USER]
        and parts[6:] == root_wrapper_tail
    )
    legacy_exec = len(parts) == 6 and parts[:3] == ["docker", "exec", "-i"] and parts[4:] == bridge_tail
    if root_wrapper_exec or legacy_exec:
        container_name = parts[5].strip() if root_wrapper_exec else parts[3].strip()
        if not PUBLIC_AGENT_BRIDGE_CONTAINER_RE.fullmatch(container_name):
            return False, "", "public Agent bridge container name is not allowlisted"
        service_suffix = container_name
        if expected_project:
            service_suffix = ""
            for separator in ("-", "_"):
                prefix = f"{expected_project}{separator}"
                if container_name.startswith(prefix):
                    service_suffix = container_name[len(prefix):]
                    break
            if not service_suffix:
                return False, "", "public Agent bridge container does not match the deployment project"
        allowed_services = ("hermes-gateway", "operator-hermes-gateway", "control-operator-hermes-gateway")
        if not any(
            service_suffix == service
            or service_suffix.startswith(f"{service}-")
            or service_suffix.startswith(f"{service}_")
            for service in allowed_services
        ):
            return False, "", "public Agent bridge may only exec the hermes-gateway service"
        return True, "docker-exec-hermes-gateway", ""

    legacy_compose_exec = (
        len(parts) == 13
        and parts[:3] == ["docker", "compose", "-p"]
        and parts[4] == "--env-file"
        and parts[6] == "-f"
        and parts[8:11] == ["exec", "-T", "hermes-gateway"]
        and parts[11:] == bridge_tail
    )
    root_wrapper_compose_exec = (
        len(parts) == 15
        and parts[:3] == ["docker", "compose", "-p"]
        and parts[4] == "--env-file"
        and parts[6] == "-f"
        and parts[8:13] == ["exec", "-T", "-u", PUBLIC_AGENT_BRIDGE_ROOT_USER, "hermes-gateway"]
        and parts[13:] == root_wrapper_tail
    )
    if legacy_compose_exec or root_wrapper_compose_exec:
        project = parts[3].strip()
        if not PUBLIC_AGENT_BRIDGE_PROJECT_RE.fullmatch(project):
            return False, "", "public Agent bridge Compose project is not allowlisted"
        if expected_project and project != expected_project:
            return False, "", "public Agent bridge Compose project does not match the job project"
        env_file = Path(parts[5])
        compose_file = Path(parts[7])
        try:
            _preflight_deployment_compose_config_files(
                env_file=env_file,
                compose_file=compose_file,
                context="public Agent bridge",
            )
        except ValueError as exc:
            return False, "", str(exc)
        return True, "docker-compose-exec-hermes-gateway", ""

    return False, "", "public Agent bridge command is not allowlisted"


def _public_agent_bridge_root_wrapper_enabled() -> bool:
    # The root-exec wrapper exists ONLY so L2 (the Telegram getMe cache) can keep a
    # root-owned cache; it hard-depends on arclink_public_agent_bridge_root.py being
    # baked into the gateway container image (the scripts are NOT host-mounted). Gate
    # it on the L2 flag so the default — and ANY pre-wrapper or partially-upgraded
    # image — uses the proven legacy command. This makes a missing/skewed wrapper a
    # no-L2 degradation instead of a total bridge outage (lock-step safety).
    # Read os.environ (same source the bridge's _bool_env uses, and the same as the
    # DETACHED flag in this module) so the gate only picks the wrapper once the gateway
    # was actually (re)created WITH the flag AND the new image — never from a live
    # docker.env edit that the running gateway image hasn't picked up yet.
    raw = str(os.environ.get("ARCLINK_BRIDGE_GETME_CACHE", "0") or "").strip().lower()
    return raw not in {"", "0", "false", "no", "off"}


_ROOT_WRAPPER_PRESENT_CACHE: dict[tuple[str, ...], tuple[float, bool]] = {}
_ROOT_WRAPPER_PRESENT_TTL_SECONDS = 300


def _gateway_has_public_agent_bridge_root_wrapper(exec_prefix: list[str]) -> bool:
    """Cached read-only PREFLIGHT: does the target gateway image carry the L2 root
    wrapper script? If it is absent — or we cannot verify it — callers fall back to the
    legacy bridge command. This is what prevents a flag-on-but-image-not-rebuilt skew
    from hard-failing every turn (the 2026-06-18 outage). exec_prefix is the docker /
    compose exec prefix (no bridge tail); the probe runs `<prefix> test -e <wrapper>`.
    """
    key = tuple(str(part) for part in exec_prefix)
    now = time.time()
    cached = _ROOT_WRAPPER_PRESENT_CACHE.get(key)
    # Only ever trust a cached NEGATIVE (which only routes to the always-safe legacy
    # command). A cached POSITIVE is ALWAYS re-probed: the container name is the cache
    # key and survives recreate, so a rollback/recreate that drops the wrapper while L2
    # is enabled would otherwise keep emitting the wrapper command — re-opening the
    # wrapper-missing hard-fail for up to the TTL. Re-probing positives catches that on
    # the very next turn; the cost is one cheap `test -e` per turn only while L2 is on.
    if cached is not None and cached[1] is False and (now - cached[0]) < _ROOT_WRAPPER_PRESENT_TTL_SECONDS:
        return False
    docker_binary = str(os.environ.get("ARCLINK_DOCKER_BINARY") or "").strip() or "docker"
    probe = [docker_binary, *list(exec_prefix)[1:], "test", "-e", PUBLIC_AGENT_BRIDGE_ROOT_WRAPPER_SCRIPT]
    try:
        proc = subprocess.run(probe, capture_output=True, timeout=15, check=False)
    except Exception:
        # H4 fix: a thrown/timed-out probe (transient docker hiccup, 15s timeout)
        # tells us NOTHING about whether the wrapper exists -- caching that as a
        # NEGATIVE would pin L2 off for the full TTL (300s) after a single blip.
        # Return the safe legacy answer (False) WITHOUT caching, so the very next
        # turn re-probes and L2 recovers as soon as docker does.
        return False
    # Only a probe that genuinely RAN and returned is authoritative; cache that
    # present/absent result.
    present = proc.returncode == 0
    _ROOT_WRAPPER_PRESENT_CACHE[key] = (now, present)
    return present


def _should_use_public_agent_bridge_root_wrapper(exec_prefix: list[str]) -> bool:
    # Use the L2 root wrapper ONLY when the flag is on AND the wrapper is provably
    # present in the gateway image; otherwise fall back to legacy (never hard-fail).
    if not _public_agent_bridge_root_wrapper_enabled():
        return False
    return _gateway_has_public_agent_bridge_root_wrapper(exec_prefix)


def _public_agent_bridge_root_exec_cmd(container: str) -> list[str]:
    if not _should_use_public_agent_bridge_root_wrapper(["docker", "exec", container]):
        return ["docker", "exec", "-i", container, PUBLIC_AGENT_BRIDGE_PYTHON, PUBLIC_AGENT_BRIDGE_SCRIPT]
    return [
        "docker",
        "exec",
        "-i",
        "-u",
        PUBLIC_AGENT_BRIDGE_ROOT_USER,
        container,
        PUBLIC_AGENT_BRIDGE_PYTHON,
        PUBLIC_AGENT_BRIDGE_ROOT_WRAPPER_SCRIPT,
    ]


def _public_agent_bridge_compose_root_exec_cmd(*, project_name: str, env_file: Path, compose_file: Path) -> list[str]:
    compose_prefix = [
        "docker", "compose", "-p", project_name,
        "--env-file", str(env_file), "-f", str(compose_file),
        "exec", "-T", "hermes-gateway",
    ]
    if not _should_use_public_agent_bridge_root_wrapper(compose_prefix):
        return [
            "docker", "compose", "-p", project_name,
            "--env-file", str(env_file), "-f", str(compose_file),
            "exec", "-T", "hermes-gateway",
            PUBLIC_AGENT_BRIDGE_PYTHON, PUBLIC_AGENT_BRIDGE_SCRIPT,
        ]
    return [
        "docker",
        "compose",
        "-p",
        project_name,
        "--env-file",
        str(env_file),
        "-f",
        str(compose_file),
        "exec",
        "-T",
        "-u",
        PUBLIC_AGENT_BRIDGE_ROOT_USER,
        "hermes-gateway",
        PUBLIC_AGENT_BRIDGE_PYTHON,
        PUBLIC_AGENT_BRIDGE_ROOT_WRAPPER_SCRIPT,
    ]


def _deployment_service_container(*, project_name: str, service: str, docker_binary: str = "docker") -> str:
    if not project_name or not service:
        return ""
    cmd = [
        str(docker_binary or "docker"),
        "ps",
        "--filter",
        f"label=com.docker.compose.project={project_name}",
        "--filter",
        f"label=com.docker.compose.service={service}",
        "--format",
        "{{.Names}}",
    ]
    try:
        proc = subprocess.run(cmd, check=False, text=True, capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if proc.returncode != 0:
        return ""
    for line in str(proc.stdout or "").splitlines():
        value = line.strip()
        if value:
            return value
    return ""


def _extract_hermes_quiet_response(stdout: str) -> str:
    text = ANSI_RE.sub("", str(stdout or "")).replace("\r", "")
    lines = [line.rstrip() for line in text.splitlines()]
    clean: list[str] = []
    for line in lines:
        if line.startswith("session_id:"):
            break
        clean.append(line)
    response = "\n".join(clean).strip()
    return response[:6000].rstrip()


def _run_public_agent_turn(*, deployment_id: str, prefix: str, prompt: str) -> tuple[str, str]:
    project_name = _compose_project_name(deployment_id)
    if not project_name:
        return "", "The deployment id is missing, so Raven cannot choose an agent runtime."
    timeout_seconds = _int_env("ARCLINK_PUBLIC_AGENT_TURN_TIMEOUT_SECONDS", 180, minimum=15, maximum=900)
    turn_cmd = [
        "timeout",
        "--kill-after=10s",
        f"{timeout_seconds}s",
        "/opt/arclink/runtime/hermes-venv/bin/hermes",
        "chat",
        "-Q",
        "--source",
        "arclink-public-bot",
        "-q",
        prompt[:8000],
    ]
    container = _deployment_service_container(project_name=project_name, service="hermes-gateway")
    if container:
        cmd = ["docker", "exec", container, *turn_cmd]
    else:
        root = _deployment_root(deployment_id=deployment_id, prefix=prefix)
        if root is None:
            return "", "I could not find the running deployment container or deployment root on this control node."
        compose_file = root / "config" / "compose.yaml"
        env_file = root / "config" / "arclink.env"
        try:
            _preflight_deployment_compose_config_files(
                env_file=env_file,
                compose_file=compose_file,
                context="public Agent turn",
            )
        except ValueError as exc:
            return "", f"The deployment compose files failed preflight, so Raven cannot reach the agent runtime yet: {str(exc)[:180]}"
        cmd = [
            "docker",
            "compose",
            "-p",
            project_name,
            "--env-file",
            str(env_file),
            "-f",
            str(compose_file),
            "exec",
            "-T",
            "hermes-gateway",
            *turn_cmd,
        ]
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout_seconds + 20,
        )
    except subprocess.TimeoutExpired:
        return "", "The agent turn timed out before a reply came back."
    except OSError as exc:
        return "", f"The control node could not start the agent turn runner: {str(exc)[:180]}"
    if proc.returncode != 0:
        detail = ANSI_RE.sub("", (proc.stderr or proc.stdout or "")).strip().splitlines()
        tail = detail[-1][:180] if detail else f"exit status {proc.returncode}"
        return "", f"The agent runtime returned an error: {tail}"
    response = _extract_hermes_quiet_response(proc.stdout)
    if not response:
        return "", "The agent turn completed without a reply."
    return response, ""


def _public_agent_gateway_payload(
    *,
    channel_kind: str,
    target_id: str,
    prompt: str,
    extra: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    clean_channel = channel_kind.strip().lower()
    if clean_channel == "telegram":
        bot_token = config_env_value("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = _strip_public_channel_prefix(target_id, "tg")
        user_id = chat_id
        message_id = str(extra.get("telegram_reply_to_message_id") or "").strip()
        chat_type = "dm"
    elif clean_channel == "discord":
        bot_token = config_env_value("DISCORD_BOT_TOKEN", "").strip()
        user_id = str(extra.get("discord_user_id") or _strip_public_channel_prefix(target_id, "discord")).strip()
        chat_id = str(extra.get("discord_channel_id") or "").strip()
        message_id = str(extra.get("discord_message_id") or "").strip()
        chat_type = str(extra.get("discord_chat_type") or "dm").strip() or "dm"
        if not bot_token:
            return {}, "DISCORD_BOT_TOKEN is not configured for Hermes public gateway bridge"
        if not chat_id and user_id:
            try:
                dm = discord_create_dm_channel(bot_token=bot_token, recipient_id=user_id)
                chat_id = str(dm.get("id") or "").strip() if isinstance(dm, dict) else ""
            except Exception as exc:  # noqa: BLE001
                return {}, f"discord public gateway bridge could not open DM: {str(exc)[:180]}"
    else:
        return {}, f"Hermes public gateway bridge is not implemented for {clean_channel or 'blank'}"
    if not bot_token:
        return {}, f"{clean_channel.upper()}_BOT_TOKEN is not configured for Hermes public gateway bridge"
    if not chat_id:
        return {}, f"{clean_channel} public gateway bridge requires a channel id"
    if not user_id:
        return {}, f"{clean_channel} public gateway bridge requires a user id"
    payload = {
        "platform": clean_channel,
        "bot_token": bot_token,
        "chat_id": chat_id,
        "channel_id": chat_id,
        "user_id": user_id,
        "text": prompt[:8000],
        "message_id": message_id,
        "display_name": str(extra.get("display_name") or extra.get("agent_label") or "").strip(),
        "chat_type": chat_type,
        "streaming_enabled": _public_agent_bridge_streaming_enabled(),
    }
    if clean_channel == "telegram":
        for key in (
            "telegram_update_kind",
            "telegram_update_json",
            "telegram_update_json_list",
            "telegram_native_callback",
            "telegram_callback_family",
        ):
            value = extra.get(key)
            if value not in (None, ""):
                payload[key] = value
    return payload, ""


def _bridge_delivery_tuple(payload_out: Any, *, label: str) -> tuple[bool, str]:
    result = public_agent_bridge_delivery_result(payload_out)
    if result.get("delivered") is True:
        return True, ""
    if result.get("ok") is True:
        if _public_agent_bridge_should_hold_for_reconciliation(result):
            return False, _public_agent_bridge_unconfirmed_error(result)
        return False, _public_agent_bridge_delivery_error(result, label=label)
    return False, str(result.get("error") or f"{label} completed without an ok response")[:500]


def _run_public_agent_gateway_turn(
    *,
    deployment_id: str,
    prefix: str,
    channel_kind: str,
    target_id: str,
    prompt: str,
    extra: dict[str, Any],
    notification_id: int | None = None,
) -> tuple[bool, str]:
    """Try to route a public bot turn through Hermes' native gateway pipeline.

    The legacy quiet CLI path can produce a text answer, but it bypasses
    platform behavior such as Telegram reactions, typing indicators, interim
    assistant messages, native command handling, and platform formatting. The
    bridge helper runs inside the deployment container and receives secrets via
    stdin so bot tokens never appear in argv.
    """
    payload, error = _public_agent_gateway_payload(
        channel_kind=channel_kind,
        target_id=target_id,
        prompt=prompt,
        extra=extra,
    )
    if error:
        return False, error
    project_name = _compose_project_name(deployment_id)
    if not project_name:
        return False, "deployment id is missing"
    timeout_seconds = _int_env("ARCLINK_PUBLIC_AGENT_TURN_TIMEOUT_SECONDS", 180, minimum=15, maximum=900)
    broker_request = _gateway_exec_broker_request(
        deployment_id=deployment_id,
        prefix=prefix,
        project_name=project_name,
        payload=payload,
        timeout_seconds=timeout_seconds + 30,
    )
    if _gateway_exec_broker_url():
        if _public_agent_bridge_detached_enabled() and notification_id is not None:
            started, error = _spawn_public_agent_gateway_bridge(
                gateway_exec_request=broker_request,
                notification_id=notification_id,
            )
            if started:
                return True, PUBLIC_AGENT_BRIDGE_DEFERRED
            return False, error
        return _run_gateway_exec_broker_request(broker_request)
    container = _deployment_service_container(project_name=project_name, service="hermes-gateway")
    if container:
        cmd = _public_agent_bridge_root_exec_cmd(container)
    else:
        root = _deployment_root(deployment_id=deployment_id, prefix=prefix)
        if root is None:
            return False, "deployment container/root not found for gateway bridge"
        compose_file = root / "config" / "compose.yaml"
        env_file = root / "config" / "arclink.env"
        try:
            _preflight_deployment_compose_config_files(
                env_file=env_file,
                compose_file=compose_file,
                context="public Agent gateway bridge",
            )
        except ValueError as exc:
            return False, f"Hermes public gateway bridge config rejected: {str(exc)[:220]}"
        cmd = _public_agent_bridge_compose_root_exec_cmd(
            project_name=project_name,
            env_file=env_file,
            compose_file=compose_file,
        )
    valid, _command_kind, reason = _validate_public_agent_bridge_cmd(cmd, project_name=project_name)
    if not valid:
        return False, f"Hermes public gateway bridge command rejected: {reason}"
    if _public_agent_bridge_detached_enabled():
        started, error = _spawn_public_agent_gateway_bridge(
            cmd=cmd,
            payload=payload,
            notification_id=notification_id,
            project_name=project_name,
        )
        if started and notification_id is not None:
            return True, PUBLIC_AGENT_BRIDGE_DEFERRED
        return started, error
    try:
        proc = subprocess.run(
            cmd,
            input=json.dumps(payload, sort_keys=True),
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout_seconds + 30,
        )
    except subprocess.TimeoutExpired:
        return False, "Hermes public gateway bridge timed out"
    except OSError as exc:
        return False, f"could not start Hermes public gateway bridge: {str(exc)[:180]}"
    if proc.returncode != 0:
        detail = ANSI_RE.sub("", (proc.stderr or proc.stdout or "")).strip().splitlines()
        tail = detail[-1][:220] if detail else f"exit status {proc.returncode}"
        return False, f"Hermes public gateway bridge failed: {tail}"
    try:
        payload_out = json.loads(str(proc.stdout or "{}").strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        payload_out = {}
    return _bridge_delivery_tuple(payload_out, label="Hermes public gateway bridge")


def _run_operator_agent_gateway_turn(
    *,
    channel_kind: str,
    target_id: str,
    prompt: str,
    extra: dict[str, Any],
    notification_id: int | None = None,
) -> tuple[bool, str]:
    """Route an Operator chat turn into the Control Node's in-stack Hermes gateway."""
    payload, error = _public_agent_gateway_payload(
        channel_kind=channel_kind,
        target_id=target_id,
        prompt=prompt,
        extra=extra,
    )
    if error:
        return False, error
    project_name = config_env_value("ARCLINK_CONTROL_COMPOSE_PROJECT", "").strip() or "arclink"
    if not PUBLIC_AGENT_BRIDGE_PROJECT_RE.fullmatch(project_name):
        return False, "operator Hermes gateway Compose project is not allowlisted"
    timeout_seconds = _int_env("ARCLINK_PUBLIC_AGENT_TURN_TIMEOUT_SECONDS", 180, minimum=15, maximum=900)
    broker_request = _operator_gateway_exec_broker_request(
        project_name=project_name,
        payload=payload,
        timeout_seconds=timeout_seconds + 30,
    )
    if _gateway_exec_broker_url():
        if _public_agent_bridge_detached_enabled() and notification_id is not None:
            started, error = _spawn_public_agent_gateway_bridge(
                gateway_exec_request=broker_request,
                notification_id=notification_id,
            )
            if started:
                return True, PUBLIC_AGENT_BRIDGE_DEFERRED
            return False, error
        return _run_gateway_exec_broker_request(broker_request)
    container = _deployment_service_container(
        project_name=project_name,
        service="control-operator-hermes-gateway",
    )
    if not container:
        return False, "operator Hermes gateway container not found in the Control Node stack"
    cmd = _public_agent_bridge_root_exec_cmd(container)
    valid, _command_kind, reason = _validate_public_agent_bridge_cmd(cmd, project_name=project_name)
    if not valid:
        return False, f"Hermes operator gateway bridge command rejected: {reason}"
    if _public_agent_bridge_detached_enabled():
        started, error = _spawn_public_agent_gateway_bridge(
            cmd=cmd,
            payload=payload,
            notification_id=notification_id,
            project_name=project_name,
        )
        if started and notification_id is not None:
            return True, PUBLIC_AGENT_BRIDGE_DEFERRED
        return started, error
    try:
        proc = subprocess.run(
            cmd,
            input=json.dumps(payload, sort_keys=True),
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout_seconds + 30,
        )
    except subprocess.TimeoutExpired:
        return False, "Hermes operator gateway bridge timed out"
    except OSError as exc:
        return False, f"could not start Hermes operator gateway bridge: {str(exc)[:180]}"
    if proc.returncode != 0:
        detail = ANSI_RE.sub("", (proc.stderr or proc.stdout or "")).strip().splitlines()
        tail = detail[-1][:220] if detail else f"exit status {proc.returncode}"
        return False, f"Hermes operator gateway bridge failed: {tail}"
    try:
        payload_out = json.loads(str(proc.stdout or "{}").strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        payload_out = {}
    return _bridge_delivery_tuple(payload_out, label="Hermes operator gateway bridge")


def _public_agent_bridge_detached_enabled() -> bool:
    """Return whether public Agent bridge turns should outlive the trigger worker.

    Telegram/Discord webhooks must stay snappy, while Hermes turns can stream
    for minutes or run much longer. The bridge process owns the synthetic
    platform event until Hermes finishes, so the notification worker should
    start it and release its slot instead of imposing a hard turn timeout.
    """
    return os.environ.get("ARCLINK_PUBLIC_AGENT_BRIDGE_DETACHED", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _public_agent_bridge_streaming_enabled() -> bool:
    """Return whether public Agent turns should opt into Hermes streaming.

    The public bridge is a short-lived synthetic gateway process, separate from
    Hermes' normal long-lived platform adapters. Default on so bridged Operator
    and Captain chats preserve native Hermes progress, approval, and interim
    status behavior; operators can still force final-message delivery with
    ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING=0.
    """
    return config_env_value("ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _public_agent_bridge_max_seconds() -> int:
    return _int_env("ARCLINK_PUBLIC_AGENT_BRIDGE_MAX_SECONDS", 7200, minimum=60, maximum=86400)


def _public_agent_turn_lease_seconds() -> int:
    if _public_agent_bridge_detached_enabled():
        return _public_agent_bridge_max_seconds() + 300
    return _int_env("ARCLINK_PUBLIC_AGENT_TURN_TIMEOUT_SECONDS", 180, minimum=15, maximum=900) + 90


def _public_agent_bridge_log_path() -> Path:
    state_dir = config_env_value("STATE_DIR", "").strip() or os.environ.get("STATE_DIR", "").strip()
    if not state_dir:
        state_dir = str(Path.cwd() / "arclink-priv" / "state")
    return Path(state_dir) / "docker" / "jobs" / "public-agent-bridge.log"


def _public_agent_bridge_job_dir() -> Path:
    return _public_agent_bridge_log_path().parent / "public-agent-bridge-jobs"


def _strip_public_agent_bridge_payload_secrets(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    clean = dict(payload)
    if "bot_token" not in clean:
        return clean, False
    clean.pop("bot_token", None)
    return clean, True


def _hydrate_public_agent_bridge_payload_secret(payload: dict[str, Any], *, required: bool) -> dict[str, Any]:
    clean = dict(payload)
    if not required or str(clean.get("bot_token") or "").strip():
        return clean
    platform = str(clean.get("platform") or "").strip().lower()
    env_name = {
        "telegram": "TELEGRAM_BOT_TOKEN",
        "discord": "DISCORD_BOT_TOKEN",
    }.get(platform)
    if not env_name:
        raise RuntimeError("public Agent bridge job cannot resolve the bot token for this platform")
    token = config_env_value(env_name, "").strip()
    if not token:
        raise RuntimeError(f"{env_name} is not configured for Hermes public gateway bridge")
    clean["bot_token"] = token
    return clean


def _strip_gateway_exec_request_secrets(request_body: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    clean = dict(request_body)
    payload = clean.get("payload")
    if not isinstance(payload, dict):
        return clean, False
    clean_payload, requires_runtime_secret = _strip_public_agent_bridge_payload_secrets(payload)
    clean["payload"] = clean_payload
    return clean, requires_runtime_secret


def _hydrate_gateway_exec_request_secret(request_body: dict[str, Any], *, required: bool) -> dict[str, Any]:
    clean = dict(request_body)
    payload = clean.get("payload")
    if isinstance(payload, dict):
        clean["payload"] = _hydrate_public_agent_bridge_payload_secret(payload, required=required)
    return clean


def _write_public_agent_bridge_job(
    *,
    notification_id: int,
    cmd: list[str] | None = None,
    payload: dict[str, Any] | None = None,
    project_name: str = "",
    gateway_exec_request: dict[str, Any] | None = None,
    worker_token: str = "",
) -> Path:
    body: dict[str, Any]
    # C1 fix: every detached worker carries a unique lease token, embedded in the
    # job body so the worker can prove it still owns the row's lease before any
    # terminal write. The SAME token is stamped into the row's extra_json at spawn
    # (see _record_public_agent_bridge_worker), so a row that was re-leased to a
    # NEW worker (different token) rejects this worker's late delivered/error/
    # unconfirmed update -- closing the recycled-pid duplicate-send race.
    clean_token = str(worker_token or "").strip()
    if gateway_exec_request is not None:
        if not isinstance(gateway_exec_request, dict):
            raise ValueError("gateway exec broker request must be a JSON object")
        command_kind = "gateway-exec-broker-request"
        clean_request, requires_runtime_secret = _strip_gateway_exec_request_secrets(gateway_exec_request)
        body = {
            "notification_id": int(notification_id),
            "command_kind": command_kind,
            # M4: carry the project so a broker FAILURE can be enriched with
            # kind=gateway-exec-broker + project (the broker path previously had no
            # project in its job body, so the enriched operator page could not name
            # the failing turn's deployment).
            "project_name": str(project_name or "").strip(),
            "gateway_exec_request": clean_request,
            "gateway_exec_request_requires_runtime_secret": requires_runtime_secret,
            "timeout_seconds": _public_agent_bridge_max_seconds(),
            "worker_token": clean_token,
        }
    else:
        clean_cmd = [str(part) for part in cmd or []]
        valid, command_kind, reason = _validate_public_agent_bridge_cmd(clean_cmd, project_name=project_name)
        if not valid:
            raise ValueError(reason)
        clean_payload, requires_runtime_secret = _strip_public_agent_bridge_payload_secrets(payload or {})
        body = {
            "notification_id": int(notification_id),
            "cmd": clean_cmd,
            "command_kind": command_kind,
            "project_name": str(project_name or "").strip(),
            "payload": clean_payload,
            "payload_requires_runtime_secret": requires_runtime_secret,
            "timeout_seconds": _public_agent_bridge_max_seconds(),
            "worker_token": clean_token,
        }
    job_dir = _public_agent_bridge_job_dir()
    job_dir.mkdir(parents=True, exist_ok=True)
    nonce = secrets.token_hex(4)
    tmp_path = job_dir / f"bridge-{int(notification_id)}-{os.getpid()}-{nonce}.json.tmp"
    job_path = job_dir / f"bridge-{int(notification_id)}-{os.getpid()}-{nonce}.json"
    fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(body, handle, sort_keys=True)
        handle.write("\n")
    os.replace(tmp_path, job_path)
    return job_path


def _load_public_agent_bridge_job(job_path: Path) -> dict[str, Any]:
    try:
        raw = job_path.read_text(encoding="utf-8")
    finally:
        try:
            job_path.unlink()
        except OSError:
            pass
    body = json.loads(raw)
    if not isinstance(body, dict):
        raise RuntimeError("public Agent bridge job must be a JSON object")
    return body


def _unlink_public_agent_bridge_job(job_path: Path) -> None:
    try:
        job_path.unlink()
    except OSError:
        pass


def _append_public_agent_bridge_log(message: str) -> None:
    try:
        log_path = _public_agent_bridge_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n")
    except OSError:
        return


def _public_agent_bridge_log_tail(max_lines: int = 6, max_chars: int = 320) -> str:
    """Return the last few lines of the per-turn bridge log (best-effort).

    Used by M4 to make an otherwise-opaque operator page (e.g. a bare "exit
    status 1" with empty stdout/stderr) actionable by quoting the most recent
    bridge-log lines. Never raises -- a missing/unreadable log yields ''.
    """
    try:
        log_path = _public_agent_bridge_log_path()
        if not log_path.exists():
            return ""
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    tail_lines = [line.strip() for line in lines if line.strip()][-max(1, int(max_lines)):]
    tail = " | ".join(tail_lines)
    return tail[-max(1, int(max_chars)):] if tail else ""


def _enrich_public_agent_bridge_error(
    base_error: str,
    *,
    command_kind: str = "",
    project_name: str = "",
    include_log_tail: bool = False,
) -> str:
    """M4: enrich a terminal bridge error with the command kind/project (and, when
    the subprocess gave us nothing, the tail of the per-turn bridge log) so the
    operator page actually says WHICH turn failed instead of just "exit status N".
    """
    parts = [str(base_error or "").strip() or "Hermes public gateway bridge failed"]
    context: list[str] = []
    clean_kind = str(command_kind or "").strip()
    clean_project = str(project_name or "").strip()
    if clean_kind:
        context.append(f"kind={clean_kind}")
    if clean_project:
        context.append(f"project={clean_project}")
    if context:
        parts.append(f"[{', '.join(context)}]")
    if include_log_tail:
        tail = _public_agent_bridge_log_tail()
        if tail:
            parts.append(f"log-tail: {tail}")
    return " ".join(parts)


def _public_agent_bridge_unconfirmed_retry_seconds() -> int:
    return _int_env("ARCLINK_PUBLIC_AGENT_BRIDGE_UNCONFIRMED_RETRY_SECONDS", 86400, minimum=900, maximum=604800)


def _mark_public_agent_bridge_unconfirmed(
    conn: Any, notification_id: int, reason: str, *, worker_token: str = ""
) -> bool:
    """Mark a turn unconfirmed/held. Returns True only when the guarded write applied.

    C1: the UPDATE carries the lease-token guard (see _notification_token_guard_sql in
    arclink_control) so the ownership check and the write are ONE statement. A
    non-empty ``worker_token`` (detached worker) must still own the lease; an empty
    token (the in-process claim-holder loop) only applies when no detached worker
    owns the row. The merge-safe terminal-counter reset and operator escalation run
    ONLY when the write applied, so a stale owner's late unconfirmed-mark touches
    nothing.
    """
    guard_sql, guard_params = _notification_token_guard_sql(worker_token)
    row = conn.execute(
        "SELECT attempt_count FROM notification_outbox WHERE id = ?" + guard_sql + " AND delivered_at IS NULL",
        [int(notification_id), *guard_params],
    ).fetchone()
    if row is None:
        return False
    attempts = int(row["attempt_count"] or 0) + 1
    now_iso = utc_now_iso()
    clean_reason = str(reason or "bridge completed without confirmed platform delivery").strip()
    error_text = (
        clean_reason
        if clean_reason.startswith(PUBLIC_AGENT_BRIDGE_UNCONFIRMED)
        else f"{PUBLIC_AGENT_BRIDGE_UNCONFIRMED}: {clean_reason}"
    )
    cursor = conn.execute(
        "UPDATE notification_outbox "
        "SET attempt_count = ?, last_attempt_at = ?, next_attempt_at = ?, delivery_error = ? "
        "WHERE id = ?" + guard_sql + " AND delivered_at IS NULL",
        [
            attempts,
            now_iso,
            utc_after_seconds_iso(_public_agent_bridge_unconfirmed_retry_seconds()),
            error_text[:500],
            int(notification_id),
            *guard_params,
        ],
    )
    conn.commit()
    if int(getattr(cursor, "rowcount", 0) or 0) < 1:
        return False
    # BUG #1 fix: an unconfirmed/held outcome is NON-terminal and may actually have
    # delivered, so it must NOT carry any prior terminal credit forward -- reset the
    # consecutive-terminal-failure counter so a later genuine terminal error starts
    # a FRESH consecutive run rather than tipping a mixed history over the threshold.
    _reset_public_agent_bridge_terminal_failures(conn, notification_id)
    # M3 fix: track the consecutive-unconfirmed run and page the operator once a turn
    # stays "delivers but never confirms" across too many cycles (distinct key).
    _maybe_escalate_public_agent_bridge_unconfirmed(conn, notification_id)
    return True


def _worker_mark_notification_delivered(conn: Any, notification_id: int, worker_token: str) -> bool:
    """C1: ATOMIC token-guarded delivered-mark for a detached worker.

    Returns False (no write) when the row was re-leased to a DIFFERENT worker since
    this worker spawned -- so a recycled-pid worker that finishes after the row was
    handed to a new worker cannot stamp a duplicate delivery (and the new worker's
    own send stays authoritative). Only the lease owner finalises the row. The
    ownership check and the write are a SINGLE SQL UPDATE (mark_notification_delivered_if_owned),
    so there is no check-then-write race, and a MISSING recorded token rejects the
    worker (a tokenless row is not provably owned by this worker).
    """
    applied = mark_notification_delivered_if_owned(conn, notification_id, worker_token) >= 1
    if applied:
        _resolve_public_agent_bridge_hiccup(conn, notification_id)
    return applied


def _worker_mark_notification_error(conn: Any, notification_id: int, error: str, worker_token: str) -> bool:
    """C1: ATOMIC token-guarded error-mark for a detached worker (see delivered variant)."""
    return mark_notification_error_if_owned(conn, notification_id, error, worker_token) >= 1


def _worker_mark_public_agent_bridge_unconfirmed(
    conn: Any, notification_id: int, reason: str, worker_token: str
) -> bool:
    """C1: ATOMIC token-guarded unconfirmed/held-mark for a detached worker.

    The unconfirmed UPDATE itself carries the token guard (see
    _mark_public_agent_bridge_unconfirmed), so the held-mark only applies when this
    worker still owns the lease; the merge-safe terminal-counter reset and the
    operator-escalation side-effects then run ONLY when the guarded write applied.
    """
    if not _mark_public_agent_bridge_unconfirmed(conn, notification_id, reason, worker_token=worker_token):
        return False
    return True


def _public_agent_bridge_worker_stale_seconds() -> int:
    return _int_env("ARCLINK_PUBLIC_AGENT_BRIDGE_ORPHAN_REAPER_SECONDS", 600, minimum=60, maximum=86400)


def _record_public_agent_bridge_worker(
    notification_id: int, *, pid: int, job_path: Path, worker_token: str = ""
) -> None:
    if int(notification_id or 0) <= 0 or int(pid or 0) <= 0:
        return
    try:
        cfg = Config.from_env()
        with connect_db(cfg) as conn:
            # BUG #1 fix -- MERGE-SAFE write. This metadata write happens AFTER the
            # detached child is already running (see _spawn_public_agent_gateway_bridge:
            # Popen() precedes this call), so the child may have already reset/bumped
            # the consecutive-terminal-failure counter on this same row. The previous
            # read-whole-dict / write-whole-dict here would serialise a STALE
            # extra_json back and resurrect a counter the child just reset -- the core
            # BUG #1 race that could page a maybe-delivered turn. We instead set ONLY
            # the ``_public_agent_bridge_worker`` key with a single atomic
            # ``json_set`` (json() so the object is stored as JSON, not a quoted
            # string), inside SQLite's per-row write lock. The counter key is never
            # read or written here, so this metadata write can never clobber it, and
            # the counter writers never clobber this key.
            worker_meta = json.dumps(
                {
                    "pid": int(pid),
                    "job_path": str(job_path),
                    "spawned_at": utc_now_iso(),
                    # C1: the unique lease token this worker owns; the worker carries
                    # the same token in its job body and guards every terminal write
                    # on it, so a row re-leased to a newer token rejects this worker.
                    "token": str(worker_token or "").strip(),
                },
                sort_keys=True,
            )
            conn.execute(
                """
                UPDATE notification_outbox
                SET extra_json = json_set(COALESCE(extra_json, '{}'), '$._public_agent_bridge_worker', json(?))
                WHERE id = ? AND delivered_at IS NULL
                """,
                (worker_meta, int(notification_id)),
            )
            conn.commit()
    except Exception as exc:  # noqa: BLE001 - spawn must not fail because metadata could not be recorded.
        _append_public_agent_bridge_log(
            json.dumps(
                {
                    "event": "public_agent_bridge_worker_metadata_error",
                    "notification_id": int(notification_id),
                    "error": str(exc)[:220],
                },
                sort_keys=True,
            )
        )


def _public_agent_bridge_worker_pid_active(pid: int, *, expected_job_path: str = "") -> bool:
    """True when ``pid`` is genuinely THIS row's live bridge worker.

    C1 fix: the worker is spawned as ``python ... --public-agent-bridge-worker
    <job_path>`` and the job_path is unique per spawn (it embeds the pid + nonce),
    so when ``expected_job_path`` is supplied we require it to appear on the live
    process's cmdline. Matching only ``--public-agent-bridge-worker`` (the old
    behaviour) would treat ANY bridge worker as alive, so a recycled pid now
    running a DIFFERENT turn's worker would wrongly keep this row leased forever
    (or, conversely, never let the reaper re-arm a genuinely-dead worker). The
    job_path check ties liveness to the specific lease.
    """
    if int(pid or 0) <= 0:
        return False
    proc_cmdline = Path("/proc") / str(int(pid)) / "cmdline"
    clean_job_path = str(expected_job_path or "").strip()
    try:
        if proc_cmdline.exists():
            cmdline = proc_cmdline.read_text(encoding="utf-8", errors="replace").replace("\x00", " ")
            is_bridge_worker = (
                "--public-agent-bridge-worker" in cmdline and "arclink_notification_delivery.py" in cmdline
            )
            if not is_bridge_worker:
                return False
            if clean_job_path:
                # The pid is a bridge worker, but only OURS if it is running our job.
                return clean_job_path in cmdline
            return True
        # No /proc (non-Linux / restricted): fall back to a bare liveness probe. We
        # cannot verify the job_path, so we conservatively treat a live pid as our
        # worker (the worker's own token-guarded writes still prevent duplicates).
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return True


def reap_orphaned_public_agent_bridge_leases(cfg: Config, *, limit: int = 50) -> int:
    """Re-arm leased public Agent turns whose detached bridge worker died."""
    now_iso = utc_now_iso()
    stale_cutoff = utc_now().timestamp() - _public_agent_bridge_worker_stale_seconds()
    reclaimed = 0
    with connect_db(cfg) as conn:
        rows = conn.execute(
            """
            SELECT id, extra_json, last_attempt_at, next_attempt_at
            FROM notification_outbox
            WHERE delivered_at IS NULL
              AND target_kind = 'public-agent-turn'
              AND last_attempt_at IS NOT NULL
              AND last_attempt_at != ''
              AND next_attempt_at IS NOT NULL
              AND next_attempt_at != ''
              AND next_attempt_at > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (now_iso, max(1, int(limit))),
        ).fetchall()
        for raw_row in rows:
            row = dict(raw_row)
            last_attempt = parse_utc_iso(str(row.get("last_attempt_at") or ""))
            if last_attempt is None or last_attempt.timestamp() > stale_cutoff:
                continue
            try:
                extra = json.loads(str(row.get("extra_json") or "{}"))
            except json.JSONDecodeError:
                extra = {}
            if not isinstance(extra, dict):
                extra = {}
            worker = extra.get("_public_agent_bridge_worker")
            if not isinstance(worker, dict):
                continue
            pid = int(worker.get("pid") or 0)
            recorded_job_path = str(worker.get("job_path") or "").strip()
            recorded_token = str(worker.get("token") or "").strip()
            # C1: a worker is only "provably alive for this row" when the row records
            # BOTH a lease token AND a job_path AND the recorded pid is running THAT
            # specific job. A missing token (the worker never stamped its lease) or a
            # missing job_path (we cannot tie a live pid to THIS lease) means the
            # worker is NOT provably alive, so the lease is ELIGIBLE to re-arm -- a
            # bare pid liveness check on an empty job_path would otherwise let a
            # recycled pid running a DIFFERENT turn pin this lease forever. Only when
            # token+job_path are both present and the pid runs that job do we leave the
            # still-running worker alone.
            if (
                recorded_token
                and recorded_job_path
                and _public_agent_bridge_worker_pid_active(pid, expected_job_path=recorded_job_path)
            ):
                continue
            # BUG #1 fix -- MERGE-SAFE write: stamp ONLY the worker-metadata
            # ``reclaimed_at`` subkey via ``json_set`` instead of serialising the
            # whole (possibly-stale) ``extra`` dict back. The read above is only used
            # for the pid/decision logic; writing the whole dict here would clobber a
            # concurrent counter reset/bump on the same row. Touching just the
            # ``$._public_agent_bridge_worker.reclaimed_at`` path keeps the
            # consecutive-terminal-failure counter (and any other key) intact.
            cursor = conn.execute(
                """
                UPDATE notification_outbox
                SET next_attempt_at = ?,
                    delivery_error = ?,
                    extra_json = json_set(
                        COALESCE(extra_json, '{}'),
                        '$._public_agent_bridge_worker.reclaimed_at',
                        ?
                    )
                WHERE id = ?
                  AND delivered_at IS NULL
                  AND next_attempt_at > ?
                """,
                (
                    now_iso,
                    f"public_agent_bridge_orphan_reclaimed: pid={pid}"[:500],
                    now_iso,
                    int(row["id"]),
                    now_iso,
                ),
            )
            if int(getattr(cursor, "rowcount", 0) or 0) == 1:
                reclaimed += 1
        if reclaimed:
            conn.commit()
    return reclaimed


def _run_public_agent_bridge_worker(job_path: Path) -> int:
    try:
        job = _load_public_agent_bridge_job(job_path)
        notification_id = int(job.get("notification_id") or 0)
        cmd = [str(part) for part in job.get("cmd") or []]
        project_name = str(job.get("project_name") or "").strip()
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        payload = _hydrate_public_agent_bridge_payload_secret(
            payload,
            required=job.get("payload_requires_runtime_secret") is True,
        )
        gateway_exec_request = job.get("gateway_exec_request") if isinstance(job.get("gateway_exec_request"), dict) else None
        if gateway_exec_request is not None:
            gateway_exec_request = _hydrate_gateway_exec_request_secret(
                gateway_exec_request,
                required=job.get("gateway_exec_request_requires_runtime_secret") is True,
            )
        timeout_seconds = int(job.get("timeout_seconds") or _public_agent_bridge_max_seconds())
        # C1: the lease token this worker owns. All terminal writes below are guarded
        # on it so a recycled-pid worker whose row was re-leased to a newer worker
        # cannot finalise (and duplicate-send) the row.
        worker_token = str(job.get("worker_token") or "").strip()
        if notification_id <= 0:
            raise RuntimeError("public Agent bridge job is missing notification_id")
        cfg = Config.from_env()
        if gateway_exec_request is not None:
            _append_public_agent_bridge_log(
                json.dumps(
                    {
                        "event": "public_agent_bridge_broker_started",
                        "notification_id": notification_id,
                        "timeout_seconds": timeout_seconds,
                    },
                    sort_keys=True,
                )
            )
            ok, error = _run_gateway_exec_broker_request(gateway_exec_request)
            if ok:
                with connect_db(cfg) as conn:
                    # Resolve-on-delivery is folded into the guarded helper.
                    owned = _worker_mark_notification_delivered(conn, notification_id, worker_token)
                _append_public_agent_bridge_log(
                    json.dumps(
                        {
                            "event": "public_agent_bridge_broker_delivered",
                            "notification_id": notification_id,
                            "lease_owned": owned,
                        },
                        sort_keys=True,
                    )
                )
                return 0
            if _is_public_agent_bridge_unconfirmed(error):
                with connect_db(cfg) as conn:
                    _worker_mark_public_agent_bridge_unconfirmed(conn, notification_id, error, worker_token)
                _append_public_agent_bridge_log(
                    json.dumps(
                        {
                            "event": "public_agent_bridge_broker_unconfirmed",
                            "notification_id": notification_id,
                            "error": str(error)[:500],
                        },
                        sort_keys=True,
                    )
                )
                return 0
            # M4 (STILL-BROKEN fix): the broker failure path previously wrote/paged the
            # RAW broker error with no context -- only the direct-subprocess path was
            # enriched. Route it through the SAME enrichment so the operator page names
            # the command kind (gateway-exec-broker) + project and, when the broker
            # handed us nothing, the tail of the per-turn bridge log.
            broker_error = _enrich_public_agent_bridge_error(
                f"Hermes public gateway bridge failed: {error}",
                command_kind="gateway-exec-broker",
                project_name=project_name,
                include_log_tail=not str(error or "").strip(),
            )
            with connect_db(cfg) as conn:
                if _worker_mark_notification_error(conn, notification_id, broker_error, worker_token):
                    _maybe_report_public_agent_bridge_hiccup(conn, notification_id, error=broker_error)
            _append_public_agent_bridge_log(
                json.dumps(
                    {
                        "event": "public_agent_bridge_broker_failed",
                        "notification_id": notification_id,
                        "error": str(broker_error)[:500],
                    },
                    sort_keys=True,
                )
            )
            return 1
        if not cmd:
            raise RuntimeError("public Agent bridge job is missing cmd")
        valid, command_kind, reason = _validate_public_agent_bridge_cmd(cmd, project_name=project_name)
        if not valid:
            with connect_db(cfg) as conn:
                if _worker_mark_notification_error(
                    conn, notification_id, f"Hermes public gateway bridge rejected command: {reason}", worker_token
                ):
                    _maybe_report_public_agent_bridge_hiccup(conn, notification_id, error=f"rejected command: {reason}")
            _append_public_agent_bridge_log(
                json.dumps(
                    {
                        "event": "public_agent_bridge_rejected_command",
                        "notification_id": notification_id,
                        "reason": reason,
                    },
                    sort_keys=True,
                )
            )
            return 1
        _append_public_agent_bridge_log(
            json.dumps(
                {
                    "event": "public_agent_bridge_started",
                    "command_kind": command_kind,
                    "notification_id": notification_id,
                    "timeout_seconds": timeout_seconds,
                },
                sort_keys=True,
            )
        )
        try:
            proc = subprocess.run(
                cmd,
                input=json.dumps(payload, sort_keys=True),
                check=False,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            # M4: make the operator page actionable -- name the command kind/project
            # so a bare "timed out" is not the only signal.
            timeout_error = _enrich_public_agent_bridge_error(
                "Hermes public gateway bridge timed out",
                command_kind=command_kind,
                project_name=project_name,
                include_log_tail=False,
            )
            with connect_db(cfg) as conn:
                if _worker_mark_notification_error(conn, notification_id, timeout_error, worker_token):
                    _maybe_report_public_agent_bridge_hiccup(conn, notification_id, error=timeout_error)
            _append_public_agent_bridge_log(
                json.dumps({"event": "public_agent_bridge_timeout", "notification_id": notification_id}, sort_keys=True)
            )
            return 1
        if proc.stdout:
            _append_public_agent_bridge_log(proc.stdout)
        if proc.stderr:
            _append_public_agent_bridge_log(proc.stderr)
        if proc.returncode != 0:
            detail = ANSI_RE.sub("", (proc.stderr or proc.stdout or "")).strip().splitlines()
            tail = detail[-1][:220] if detail else f"exit status {proc.returncode}"
            # M4: an exit-N with empty stdout/stderr collapses to a useless
            # "exit status N". Enrich with command kind/project and the tail of the
            # per-turn bridge log so the operator page points at the failing turn.
            failure_error = _enrich_public_agent_bridge_error(
                f"Hermes public gateway bridge failed: {tail}",
                command_kind=command_kind,
                project_name=project_name,
                include_log_tail=not (proc.stderr or proc.stdout or "").strip(),
            )
            with connect_db(cfg) as conn:
                if _worker_mark_notification_error(conn, notification_id, failure_error, worker_token):
                    _maybe_report_public_agent_bridge_hiccup(conn, notification_id, error=failure_error)
            _append_public_agent_bridge_log(
                json.dumps(
                    {
                        "event": "public_agent_bridge_failed",
                        "notification_id": notification_id,
                        "returncode": proc.returncode,
                    },
                    sort_keys=True,
                )
            )
            return proc.returncode or 1
        try:
            payload_out = json.loads(str(proc.stdout or "{}").strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            payload_out = {}
        result = public_agent_bridge_delivery_result(payload_out)
        if result.get("delivered") is True:
            with connect_db(cfg) as conn:
                owned = _worker_mark_notification_delivered(conn, notification_id, worker_token)
            _append_public_agent_bridge_log(
                json.dumps(
                    {
                        "event": "public_agent_bridge_delivered",
                        "notification_id": notification_id,
                        "message_ids": result.get("message_ids") or [],
                        "lease_owned": owned,
                    },
                    sort_keys=True,
                )
            )
            return 0
        if result.get("ok") is True and _public_agent_bridge_should_hold_for_reconciliation(result):
            reason = _public_agent_bridge_unconfirmed_error(result)
            with connect_db(cfg) as conn:
                _worker_mark_public_agent_bridge_unconfirmed(conn, notification_id, reason, worker_token)
            _append_public_agent_bridge_log(
                json.dumps(
                    {
                        "event": "public_agent_bridge_unconfirmed",
                        "notification_id": notification_id,
                        "delivery_status": result.get("delivery_status"),
                    },
                    sort_keys=True,
                )
            )
            return 0
        if result.get("ok") is True:
            error = _public_agent_bridge_delivery_error(result, label="Hermes public gateway bridge")
            failure_error = _enrich_public_agent_bridge_error(
                f"Hermes public gateway bridge failed: {error}",
                command_kind=command_kind,
                project_name=project_name,
                include_log_tail=False,
            )
            with connect_db(cfg) as conn:
                if _worker_mark_notification_error(conn, notification_id, failure_error, worker_token):
                    _maybe_report_public_agent_bridge_hiccup(conn, notification_id, error=failure_error)
            _append_public_agent_bridge_log(
                json.dumps(
                    {
                        "event": "public_agent_bridge_delivery_failed",
                        "notification_id": notification_id,
                        "delivery_status": result.get("delivery_status"),
                    },
                    sort_keys=True,
                )
            )
            return 1
        no_ok_error = _enrich_public_agent_bridge_error(
            str(result.get("error") or "Hermes public gateway bridge completed without an ok response"),
            command_kind=command_kind,
            project_name=project_name,
            include_log_tail=not str(result.get("error") or "").strip(),
        )
        with connect_db(cfg) as conn:
            if _worker_mark_notification_error(conn, notification_id, no_ok_error, worker_token):
                _maybe_report_public_agent_bridge_hiccup(conn, notification_id, error=no_ok_error)
        _append_public_agent_bridge_log(
            json.dumps({"event": "public_agent_bridge_no_ok", "notification_id": notification_id}, sort_keys=True)
        )
        return 1
    except Exception as exc:  # noqa: BLE001
        _append_public_agent_bridge_log(
            json.dumps({"event": "public_agent_bridge_worker_error", "error": str(exc)[:500]}, sort_keys=True)
        )
        return 1


def _spawn_public_agent_gateway_bridge(
    *,
    cmd: list[str] | None = None,
    payload: dict[str, Any] | None = None,
    notification_id: int | None = None,
    project_name: str = "",
    gateway_exec_request: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    if gateway_exec_request is None:
        clean_cmd = [str(part) for part in cmd or []]
        valid, _command_kind, reason = _validate_public_agent_bridge_cmd(clean_cmd, project_name=project_name)
        if not valid:
            return False, f"Hermes public gateway bridge command rejected: {reason}"
    else:
        clean_cmd = []
    if notification_id is not None:
        # C1: mint a unique lease token for THIS worker. It is embedded in the job
        # body (the worker proves ownership with it) and stamped into the row's
        # extra_json BEFORE the worker is spawned, so the row carries the owning
        # token from the moment the lease is handed out. A later re-lease overwrites
        # the token, and the stale worker's guarded terminal writes then no-op.
        worker_token = secrets.token_hex(16)
        try:
            job_path = _write_public_agent_bridge_job(
                notification_id=notification_id,
                cmd=clean_cmd,
                payload=payload or {},
                project_name=project_name,
                gateway_exec_request=gateway_exec_request,
                worker_token=worker_token,
            )
        except (OSError, ValueError) as exc:
            return False, f"could not write public gateway bridge job: {str(exc)[:180]}"
        # C1: the lease token MUST land on the row BEFORE the worker spawns -- every
        # terminal write the worker makes is guarded on the row's recorded token, and
        # a MISSING recorded token is treated as not-owned, so a worker that ran
        # without its token stamped could never finalise its own row (it would loop /
        # be reaped and risk a duplicate send). If the stamp fails (or matches no
        # undelivered row), ABORT the spawn so a tokenless worker never runs.
        try:
            with connect_db(Config.from_env()) as conn:
                cursor = conn.execute(
                    """
                    UPDATE notification_outbox
                    SET extra_json = json_set(COALESCE(extra_json, '{}'), ?, ?)
                    WHERE id = ? AND delivered_at IS NULL
                    """,
                    (PUBLIC_AGENT_BRIDGE_WORKER_TOKEN_JSON_PATH, worker_token, int(notification_id)),
                )
                conn.commit()
                stamped = int(getattr(cursor, "rowcount", 0) or 0) >= 1
        except Exception as exc:  # noqa: BLE001 - a stamp failure must abort the spawn, not run tokenless.
            _unlink_public_agent_bridge_job(job_path)
            return False, f"could not stamp public gateway bridge lease token: {str(exc)[:180]}"
        if not stamped:
            _unlink_public_agent_bridge_job(job_path)
            return False, "could not stamp public gateway bridge lease token (row missing or already delivered)"
        log_path = _public_agent_bridge_log_path()
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as log_file:
                proc = subprocess.Popen(
                    [sys.executable, str(Path(__file__).resolve()), "--public-agent-bridge-worker", str(job_path)],
                    stdout=log_file,
                    stderr=log_file,
                    text=True,
                    start_new_session=True,
                    close_fds=True,
                )
                _record_public_agent_bridge_worker(
                    int(notification_id),
                    pid=int(getattr(proc, "pid", 0) or 0),
                    job_path=job_path,
                    worker_token=worker_token,
                )
                try:
                    returncode = proc.wait(timeout=0.25)
                except subprocess.TimeoutExpired:
                    return True, ""
                if returncode == 0:
                    return True, ""
                _unlink_public_agent_bridge_job(job_path)
                return False, f"Hermes public gateway bridge worker exited immediately with status {returncode}; see {log_path}"
        except OSError as exc:
            _unlink_public_agent_bridge_job(job_path)
            return False, f"could not start Hermes public gateway bridge worker: {str(exc)[:180]}"

    log_path = _public_agent_bridge_log_path()
    if gateway_exec_request is not None:
        return _run_gateway_exec_broker_request(gateway_exec_request)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = log_path.open("a", encoding="utf-8")
    except OSError as exc:
        return False, f"could not open public gateway bridge log: {str(exc)[:180]}"
    try:
        proc = subprocess.Popen(
            clean_cmd,
            stdin=subprocess.PIPE,
            stdout=log_file,
            stderr=log_file,
            text=True,
            start_new_session=True,
        )
        if proc.stdin is None:
            return False, "could not open public gateway bridge stdin"
        proc.stdin.write(json.dumps(payload or {}, sort_keys=True))
        proc.stdin.close()
        try:
            returncode = proc.wait(timeout=0.25)
        except subprocess.TimeoutExpired:
            return True, ""
        if returncode == 0:
            return True, ""
        return False, f"Hermes public gateway bridge exited immediately with status {returncode}; see {log_path}"
    except (BrokenPipeError, OSError) as exc:
        return False, f"could not start Hermes public gateway bridge: {str(exc)[:180]}"
    finally:
        log_file.close()


def _public_agent_quiet_fallback_enabled() -> bool:
    """Return whether degraded quiet CLI delivery is explicitly allowed.

    Public channel delivery is a product contract for native Hermes behavior.
    Falling back to ``hermes chat -Q`` hides bridge failures while severing
    streaming, reactions, command handling, and platform formatting, so the
    default is fail-closed. Operators can still opt into the degraded path for a
    maintenance window with ARCLINK_PUBLIC_AGENT_QUIET_FALLBACK=1.
    """
    return os.environ.get("ARCLINK_PUBLIC_AGENT_QUIET_FALLBACK", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _deliver_public_bot_user(
    cfg: Config,
    *,
    channel_kind: str,
    target_id: str,
    message: str,
    extra: dict[str, Any],
    conn: Any | None = None,
) -> str | None:
    session_id = str(extra.get("onboarding_session_id") or extra.get("edit_existing_session_id") or "").strip()
    capture = bool(extra.get("capture_provisioning_message"))
    edit_existing = bool(extra.get("edit_existing_message") or extra.get("edit_existing_provisioning_message"))
    if channel_kind == "telegram":
        bot_token = config_env_value("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = _strip_public_channel_prefix(target_id, "tg")
        if not bot_token:
            return "TELEGRAM_BOT_TOKEN is not configured"
        if not chat_id:
            return "public-bot-user telegram delivery requires target_id"
        reply_markup = extra.get("telegram_reply_markup")
        if not isinstance(reply_markup, dict):
            reply_markup = None
        parse_mode = str(extra.get("telegram_parse_mode") or "")
        entities = extra.get("telegram_entities")
        if not isinstance(entities, list):
            entities = None
        reply_to_message_id = None
        try:
            reply_to_message_id = int(str(extra.get("telegram_reply_to_message_id") or "").strip() or "0") or None
        except ValueError:
            reply_to_message_id = None
        edit_message_id = str(extra.get("telegram_edit_message_id") or "").strip()
        if edit_existing and not edit_message_id and session_id and conn is not None:
            edit_message_id = _provisioning_message_ref(conn, session_id=session_id, channel="telegram").get("message_id", "")
        if edit_existing and edit_message_id:
            try:
                kwargs: dict[str, Any] = {
                    "bot_token": bot_token,
                    "chat_id": chat_id,
                    "message_id": int(edit_message_id),
                    "text": message,
                    "reply_markup": reply_markup,
                    "parse_mode": parse_mode,
                }
                if entities:
                    kwargs["entities"] = entities
                telegram_edit_message_text(**kwargs)
                return None
            except Exception as exc:  # noqa: BLE001 - fall back to a fresh ready hub.
                if not bool(extra.get("edit_fallback_to_send", True)):
                    return str(exc).strip() or "unknown telegram edit error"
        try:
            kwargs = {
                "bot_token": bot_token,
                "chat_id": chat_id,
                "text": message,
                "reply_markup": reply_markup,
                "parse_mode": parse_mode,
                "reply_to_message_id": reply_to_message_id,
            }
            if entities:
                kwargs["entities"] = entities
            sent = telegram_send_message(**kwargs)
            if capture and session_id and conn is not None:
                _store_provisioning_message_ref(
                    conn,
                    session_id=session_id,
                    channel="telegram",
                    message_id=str(sent.get("message_id") or ""),
                    channel_id=chat_id,
                )
        except Exception as exc:  # noqa: BLE001
            return str(exc).strip() or "unknown telegram delivery error"
        return None
    if channel_kind == "discord":
        bot_token = config_env_value("DISCORD_BOT_TOKEN", "").strip()
        user_id = _strip_public_channel_prefix(target_id, "discord")
        if not bot_token:
            return "DISCORD_BOT_TOKEN is not configured"
        if not user_id:
            return "public-bot-user discord delivery requires target_id"
        discord_components = extra.get("discord_components")
        if not isinstance(discord_components, list):
            discord_components = None
        discord_embeds = _discord_payload_list(extra, "discord_embeds")
        discord_attachments = _discord_payload_list(extra, "discord_attachments")
        ref: dict[str, str] = {}
        if session_id and conn is not None:
            ref = _provisioning_message_ref(conn, session_id=session_id, channel="discord")
        edit_channel_id = str(extra.get("discord_edit_channel_id") or ref.get("channel_id") or "").strip()
        edit_message_id = str(extra.get("discord_edit_message_id") or ref.get("message_id") or "").strip()
        if edit_existing and edit_channel_id and edit_message_id:
            try:
                discord_edit_message(
                    bot_token=bot_token,
                    channel_id=edit_channel_id,
                    message_id=edit_message_id,
                    text=message,
                    components=discord_components,
                    embeds=discord_embeds,
                    attachments=discord_attachments,
                )
                return None
            except Exception as exc:  # noqa: BLE001 - fall back to a fresh ready hub.
                if not bool(extra.get("edit_fallback_to_send", True)):
                    return str(exc).strip() or "unknown discord edit error"
        try:
            dm = discord_create_dm_channel(bot_token=bot_token, recipient_id=user_id)
            channel_id = str(dm.get("id") or "").strip()
            if not channel_id:
                return "discord DM channel response did not include an id"
            send_kwargs: dict[str, Any] = {
                "bot_token": bot_token,
                "channel_id": channel_id,
                "text": message,
                "components": discord_components,
            }
            if discord_embeds is not None:
                send_kwargs["embeds"] = discord_embeds
            if discord_attachments is not None:
                send_kwargs["attachments"] = discord_attachments
            sent = discord_send_message(**send_kwargs)
            if capture and session_id and conn is not None:
                _store_provisioning_message_ref(
                    conn,
                    session_id=session_id,
                    channel="discord",
                    message_id=str(sent.get("id") or sent.get("message_id") or ""),
                    channel_id=channel_id,
                )
        except Exception as exc:  # noqa: BLE001
            return str(exc).strip() or "unknown discord user delivery error"
        return None
    return f"public-bot-user delivery for channel_kind={channel_kind!r} not implemented yet"


def _public_delivery_identity(channel: str, channel_identity: str) -> str:
    clean_channel = str(channel or "").strip().lower()
    clean_identity = str(channel_identity or "").strip()
    if clean_channel not in {"telegram", "discord"} or not clean_identity:
        return ""
    base_identity = clean_identity.split("#", 1)[0].strip()
    if clean_channel == "telegram":
        return base_identity if base_identity.startswith("tg:") else f"tg:{base_identity}"
    if clean_channel == "discord":
        return base_identity if base_identity.startswith("discord:") else f"discord:{base_identity}"
    return ""


def _resolve_captain_wrapped_public_channel(cfg: Config, *, user_id: str) -> tuple[str, str]:
    clean_user_id = str(user_id or "").strip()
    if not clean_user_id:
        return "", ""
    try:
        with connect_db(cfg) as conn:
            row = conn.execute(
                """
                SELECT channel, channel_identity, status
                FROM arclink_onboarding_sessions
                WHERE user_id = ?
                  AND channel IN ('telegram', 'discord')
                  AND channel_identity != ''
                  AND status NOT IN ('payment_cancelled', 'payment_expired', 'payment_failed', 'abandoned', 'expired')
                ORDER BY
                  CASE status
                    WHEN 'first_contacted' THEN 0
                    WHEN 'completed' THEN 1
                    WHEN 'provisioning_ready' THEN 2
                    WHEN 'paid' THEN 3
                    ELSE 4
                  END,
                  updated_at DESC,
                  completed_at DESC,
                  created_at DESC,
                  session_id DESC
                LIMIT 1
                """,
                (clean_user_id,),
            ).fetchone()
    except Exception:  # noqa: BLE001 - delivery must fail closed without leaking internals.
        return "", ""
    if row is None:
        return "", ""
    channel_kind = str(row["channel"] or "").strip().lower()
    target_id = _public_delivery_identity(channel_kind, str(row["channel_identity"] or ""))
    return (channel_kind, target_id) if target_id else ("", "")


TELEGRAM_ALBUM_QUIESCE_SECONDS = 1.5
TELEGRAM_ALBUM_MAX_WAIT_SECONDS = 4.0
TELEGRAM_ALBUM_MAX_UPDATE_BYTES = 45000


def _telegram_media_group_id(extra: Mapping[str, Any]) -> str:
    raw = str(extra.get("telegram_update_json") or "").strip()
    if not raw or "media_group_id" not in raw:
        return ""
    try:
        update = json.loads(raw)
    except ValueError:
        return ""
    message = update.get("message") or update.get("edited_message") or {}
    return str((message or {}).get("media_group_id") or "").strip()


def _absorb_telegram_album_siblings(
    cfg: Config,
    *,
    row: Mapping[str, Any],
    extra: dict[str, Any],
    media_group_id: str,
) -> str | None:
    """Merge a Telegram album's sibling outbox rows into this turn.

    Telegram delivers an album as one webhook update per item; each becomes its
    own outbox row, and Hermes' native media-group debounce can only merge
    items inside one process. The lowest-id undelivered row becomes the
    leader: it waits briefly for stragglers, absorbs sibling updates into
    ``telegram_update_json_list`` (so one bridge process replays them all and
    Hermes merges them natively), and marks the siblings delivered. Non-leader
    rows defer; if the leader dies, their lease expiry retries them solo.
    """
    import time as _time

    target_id = str(row.get("target_id") or "")
    channel_kind = str(row.get("channel_kind") or "").lower()
    own_id = int(row["id"]) if str(row.get("id") or "").isdigit() else None
    if own_id is None:
        return None
    deadline = _time.monotonic() + TELEGRAM_ALBUM_MAX_WAIT_SECONDS

    def _group_rows(conn: Any) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT id, message, extra_json, created_at, delivered_at
            FROM notification_outbox
            WHERE target_kind = 'public-agent-turn'
              AND channel_kind = ?
              AND target_id = ?
              AND created_at >= datetime('now', '-120 seconds')
            ORDER BY id ASC
            """,
            (channel_kind, target_id),
        ).fetchall()
        group: list[dict[str, Any]] = []
        for candidate in rows:
            item = dict(candidate)
            try:
                item_extra = json.loads(str(item.get("extra_json") or "{}"))
            except ValueError:
                continue
            if not isinstance(item_extra, dict):
                continue
            if _telegram_media_group_id(item_extra) != media_group_id:
                continue
            item["_extra"] = item_extra
            group.append(item)
        return group

    while True:
        with connect_db(cfg) as conn:
            group = _group_rows(conn)
            if not group:
                return None
            newest = max(str(item.get("created_at") or "") for item in group)
            newest_dt = parse_utc_iso(newest)
            quiesced = (
                newest_dt is None
                or (utc_now().timestamp() - newest_dt.timestamp()) >= TELEGRAM_ALBUM_QUIESCE_SECONDS
            )
            if quiesced or _time.monotonic() >= deadline:
                undelivered = [item for item in group if not str(item.get("delivered_at") or "").strip()]
                if not undelivered:
                    return None
                leader_id = min(int(item["id"]) for item in undelivered)
                if leader_id != own_id:
                    return PUBLIC_AGENT_BRIDGE_DEFERRED
                updates: list[str] = []
                absorbed: list[int] = []
                total = 0
                for item in undelivered:
                    update_json = str(item["_extra"].get("telegram_update_json") or "").strip()
                    if not update_json:
                        continue
                    if int(item["id"]) != own_id and total + len(update_json) > TELEGRAM_ALBUM_MAX_UPDATE_BYTES:
                        break
                    total += len(update_json)
                    updates.append(update_json)
                    if int(item["id"]) != own_id:
                        absorbed.append(int(item["id"]))
                if len(updates) > 1:
                    extra["telegram_update_json_list"] = updates
                    # M1 fix: persist the merged album (and the absorbed ids) into the
                    # LEADER row's extra_json BEFORE marking siblings delivered. The
                    # merged list was previously in-memory only, so if the leader turn
                    # then FAILED, its retry re-loaded the leader row (siblings already
                    # delivered -> no re-merge) and lost every non-leader media item.
                    # Persisting it means a leader retry replays the full album from
                    # the row. Merge-safe json_set of two keys, scoped to the
                    # still-undelivered leader row.
                    #
                    # M1 (STILL-BROKEN fix): the persist is NO LONGER best-effort. We
                    # mark siblings delivered ONLY when the leader-row persist actually
                    # landed (rowcount >= 1). A failed/zero-row persist that still
                    # delivered the siblings would strand the album: the leader retry
                    # would re-load a leader row WITHOUT the merged list and the
                    # siblings would already be delivered (un-re-mergeable). So a failed
                    # persist now LEAVES the siblings undelivered for a later retry.
                    persisted = False
                    try:
                        cursor = conn.execute(
                            """
                            UPDATE notification_outbox
                            SET extra_json = json_set(
                                json_set(COALESCE(extra_json, '{}'), '$.telegram_update_json_list', json(?)),
                                '$._absorbed_album_sibling_ids', json(?)
                            )
                            WHERE id = ? AND delivered_at IS NULL
                            """,
                            (
                                json.dumps(updates),
                                json.dumps([int(absorbed_id) for absorbed_id in absorbed]),
                                int(own_id),
                            ),
                        )
                        conn.commit()
                        persisted = int(getattr(cursor, "rowcount", 0) or 0) >= 1
                    except Exception:  # noqa: BLE001 - a persist failure leaves siblings for retry.
                        persisted = False
                    if not persisted:
                        # The merged album did not land on the leader row, so we must
                        # NOT mark siblings delivered (that would lose them). Drop the
                        # in-memory merge too so this leader turn does not send a
                        # partial album, and let the next cycle retry the merge.
                        extra.pop("telegram_update_json_list", None)
                        return None
                    for absorbed_id in absorbed:
                        # C1: deliver the sibling with the in-process claim-holder's
                        # (empty-token) guard: it applies ONLY when no detached worker
                        # currently owns the sibling row. A sibling re-leased to its own
                        # detached worker is left for that worker to finalise, so the
                        # leader never duplicate-delivers a row out from under a worker.
                        if mark_notification_delivered_if_owned(conn, absorbed_id, "") < 1:
                            continue
                        # Resolve-on-delivery: an absorbed album turn is served via
                        # the leader, so clear any prior alert for it (BUG #1).
                        _resolve_public_agent_bridge_hiccup(conn, absorbed_id)
                        # C2 fix: the sibling is now DELIVERED, so recording the
                        # "absorbed" provenance via mark_notification_error would be a
                        # no-op (the delivered guard rejects it) AND would otherwise
                        # clobber a clean delivery_error=NULL with a non-error string.
                        # Persist the provenance note in extra_json instead, so the
                        # sibling row stays delivered with a clean error column and the
                        # leader linkage is still auditable. Merge-safe json_set of a
                        # single key, scoped to the just-delivered row.
                        try:
                            conn.execute(
                                """
                                UPDATE notification_outbox
                                SET extra_json = json_set(
                                    COALESCE(extra_json, '{}'),
                                    '$._absorbed_into_album_leader',
                                    ?
                                )
                                WHERE id = ? AND delivered_at IS NOT NULL
                                """,
                                (int(own_id), int(absorbed_id)),
                            )
                            conn.commit()
                        except Exception:  # noqa: BLE001 - provenance note must never break delivery.
                            pass
                return None
        _time.sleep(0.4)


def _deliver_public_agent_turn(cfg: Config, row: dict[str, Any], extra: dict[str, Any]) -> str | None:
    channel_kind = str(row.get("channel_kind") or "").lower()
    target_id = str(row.get("target_id") or "")
    deployment_id = str(extra.get("deployment_id") or "").strip()
    prefix = str(extra.get("prefix") or "").strip()
    label = str(extra.get("agent_label") or prefix or "your agent").strip()
    helm = str(extra.get("helm_url") or "").strip()
    prompt = str(row.get("message") or "").strip()
    if not prompt:
        return None
    notification_id = int(row["id"]) if str(row.get("id") or "").isdigit() else None
    if channel_kind == "telegram":
        media_group_id = _telegram_media_group_id(extra)
        if media_group_id:
            album_state = _absorb_telegram_album_siblings(
                cfg,
                row=row,
                extra=extra,
                media_group_id=media_group_id,
            )
            if album_state == PUBLIC_AGENT_BRIDGE_DEFERRED:
                return PUBLIC_AGENT_BRIDGE_DEFERRED
            if extra.get("telegram_update_json_list"):
                extra["telegram_album_size"] = len(extra["telegram_update_json_list"])
    if bool(extra.get("operator_turn")) or str(extra.get("source_kind") or "").strip() == "operator_chat":
        bridged, _bridge_error = _run_operator_agent_gateway_turn(
            channel_kind=channel_kind,
            target_id=target_id,
            prompt=prompt,
            extra={**extra, "agent_label": label},
            notification_id=notification_id,
        )
    else:
        bridged, _bridge_error = _run_public_agent_gateway_turn(
            deployment_id=deployment_id,
            prefix=prefix,
            channel_kind=channel_kind,
            target_id=target_id,
            prompt=prompt,
            extra={**extra, "agent_label": label},
            notification_id=notification_id,
        )
    if bridged:
        if _bridge_error == PUBLIC_AGENT_BRIDGE_DEFERRED:
            return PUBLIC_AGENT_BRIDGE_DEFERRED
        return None
    if _is_public_agent_bridge_unconfirmed(_bridge_error):
        return _bridge_error
    if not _public_agent_quiet_fallback_enabled():
        message = f"{label} did not answer through the Hermes gateway bridge yet.\n\n{_bridge_error}"
        if helm:
            message += f"\n\nHermes Dashboard is still available: {helm}"
        return _deliver_public_bot_user(
            cfg,
            channel_kind=channel_kind,
            target_id=target_id,
            message=message,
            extra={
                "telegram_reply_to_message_id": str(extra.get("telegram_reply_to_message_id") or ""),
            },
        )
    response, error = _run_public_agent_turn(deployment_id=deployment_id, prefix=prefix, prompt=prompt)
    if error:
        message = f"{label} did not answer through Raven yet.\n\n{error}"
        if helm:
            message += f"\n\nHermes Dashboard is still available: {helm}"
    else:
        message = f"{label}:\n\n{response}"
    return _deliver_public_bot_user(
        cfg,
        channel_kind=channel_kind,
        target_id=target_id,
        message=message,
        extra={
            "telegram_reply_to_message_id": str(extra.get("telegram_reply_to_message_id") or ""),
        },
    )


def _claim_notification_for_delivery(
    conn: Any,
    notification_id: int,
    *,
    lease_seconds: int,
) -> bool:
    """Lease a notification row so live triggers and polling cannot duplicate it."""
    now_iso = utc_now_iso()
    cursor = conn.execute(
        """
        UPDATE notification_outbox
        SET last_attempt_at = ?,
            next_attempt_at = ?
        WHERE id = ?
          AND delivered_at IS NULL
          AND (next_attempt_at IS NULL OR next_attempt_at = '' OR next_attempt_at <= ?)
        """,
        (now_iso, utc_after_seconds_iso(lease_seconds), int(notification_id), now_iso),
    )
    conn.commit()
    return int(getattr(cursor, "rowcount", 0) or 0) == 1


def run_public_agent_turns_once(
    cfg: Config,
    *,
    channel_kind: str = "",
    target_id: str = "",
    limit: int = 3,
    verbose: bool = False,
) -> dict[str, Any]:
    """Immediately deliver queued public-agent turns for live webhook triggers.

    Public Telegram/Discord webhooks use this as an edge-triggered fast path:
    the outbox row remains the durable contract, but the active agent is kicked
    right away instead of waiting for the periodic notification loop.
    """
    summary = {
        "processed": 0,
        "delivered": 0,
        "errors": 0,
        "not_due": 0,
        "claimed_elsewhere": 0,
        "deferred_public_agent_bridge": 0,
        "unconfirmed_public_agent_bridge": 0,
        "reclaimed_public_agent_bridge_orphans": reap_orphaned_public_agent_bridge_leases(cfg, limit=max(1, int(limit))),
    }
    clean_channel = str(channel_kind or "").strip().lower()
    clean_target = str(target_id or "").strip()
    where = ["delivered_at IS NULL", "target_kind = 'public-agent-turn'"]
    params: list[Any] = []
    now_iso = utc_now_iso()
    where.append("(next_attempt_at IS NULL OR next_attempt_at = '' OR next_attempt_at <= ?)")
    params.append(now_iso)
    if clean_channel:
        where.append("channel_kind = ?")
        params.append(clean_channel)
    if clean_target:
        where.append("target_id = ?")
        params.append(clean_target)
    params.append(max(1, int(limit)))
    with connect_db(cfg) as conn:
        rows = conn.execute(
            f"""
            SELECT id, target_kind, target_id, channel_kind, message, extra_json, created_at, delivery_error,
                   attempt_count, last_attempt_at, next_attempt_at
            FROM notification_outbox
            WHERE {' AND '.join(where)}
            ORDER BY id ASC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        for raw_row in rows:
            row = dict(raw_row)
            if not _notification_due_now(row):
                summary["not_due"] += 1
                continue
            if not _claim_notification_for_delivery(
                conn,
                int(row["id"]),
                lease_seconds=_public_agent_turn_lease_seconds(),
            ):
                summary["claimed_elsewhere"] += 1
                continue
            summary["processed"] += 1
            try:
                extra_raw = str(row.get("extra_json") or "").strip()
                extra = json.loads(extra_raw) if extra_raw else {}
                if not isinstance(extra, dict):
                    extra = {}
                error = _deliver_public_agent_turn(cfg, row, extra)
            except Exception as exc:  # noqa: BLE001
                error = f"exception: {exc}"
            if error:
                if error == PUBLIC_AGENT_BRIDGE_DEFERRED:
                    # Non-terminal: the bridge job detached and will report later.
                    # Clear any prior terminal credit so a later genuine terminal
                    # error starts a fresh consecutive run (BUG #1).
                    _reset_public_agent_bridge_terminal_failures(conn, int(row["id"]))
                    summary["deferred_public_agent_bridge"] += 1
                    continue
                # C1: this loop is the in-process claim-holder, NOT a detached worker,
                # so every terminal write uses the empty-token guard -- it applies only
                # when no detached worker currently owns the row. A row re-leased to a
                # detached bridge worker is left for that worker to finalise, so this
                # loop never duplicate-marks (delivered/error/unconfirmed) a row another
                # owner is authoritative for.
                if _is_public_agent_bridge_unconfirmed(error):
                    _mark_public_agent_bridge_unconfirmed(conn, int(row["id"]), error)
                    summary["unconfirmed_public_agent_bridge"] += 1
                    continue
                if mark_notification_error_if_owned(conn, int(row["id"]), error, "") >= 1:
                    _maybe_report_public_agent_bridge_hiccup(conn, int(row["id"]), error=error)
                summary["errors"] += 1
                if verbose:
                    sys.stderr.write(f"[deliver-public-agent] id={row['id']} error={error}\n")
                continue
            if mark_notification_delivered_if_owned(conn, int(row["id"]), "") >= 1:
                # Resolve-on-delivery: this loop only handles public-agent-turn rows,
                # so a delivered row clears any prior terminal-attempt alert (BUG #1).
                _resolve_public_agent_bridge_hiccup(conn, int(row["id"]))
            summary["delivered"] += 1
    return summary


def deliver_row(cfg: Config, row: dict[str, Any], conn: Any | None = None) -> str | None:
    target_kind = (row.get("target_kind") or "").lower()
    extra_raw = str(row.get("extra_json") or "").strip()
    try:
        extra = json.loads(extra_raw) if extra_raw else {}
    except json.JSONDecodeError:
        extra = {}
    if not isinstance(extra, dict):
        extra = {}

    if target_kind == "operator":
        platform = _operator_platform(cfg, row)
        if platform == "discord":
            target_kind, target_value = _resolve_discord_target(cfg, row)
            discord_components = extra.get("discord_components")
            if not isinstance(discord_components, list):
                discord_components = None
            discord_embeds = _discord_payload_list(extra, "discord_embeds")
            discord_attachments = _discord_payload_list(extra, "discord_attachments")
            if target_kind == "webhook":
                return deliver_discord(row["message"], webhook_url=target_value)
            if target_kind == "channel":
                return deliver_discord_channel(
                    row["message"],
                    bot_token=_resolve_curator_discord_bot_token(cfg),
                    channel_id=target_value,
                    components=discord_components,
                    embeds=discord_embeds,
                    attachments=discord_attachments,
                )
            return "discord target is not configured"
        if platform == "telegram":
            bot_token = config_env_value("TELEGRAM_BOT_TOKEN", "").strip()
            chat_id = str(row.get("target_id") or cfg.operator_notify_channel_id or "")
            reply_markup = extra.get("telegram_reply_markup")
            if not isinstance(reply_markup, dict):
                reply_markup = None
            parse_mode = str(extra.get("telegram_parse_mode") or "")
            return deliver_telegram(
                row["message"],
                bot_token=bot_token,
                chat_id=chat_id,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
        # tui-only: no external delivery; row stays readable via notifications.list.
        return None

    if target_kind == "curator":
        # Curator brief-fanout rows are actuated by consume_curator_brief_fanout,
        # which publishes central managed-memory JSON for plugin context and
        # marks its own rows delivered. Running it here is safe and idempotent -
        # the worker is the scheduler for Curator side-effects.
        return "HANDLED_BY_CONSUMER"

    if target_kind == "user-agent":
        # Per-agent notifications (SSOT nudges, subscription signals) are consumed
        # by the user agent itself via agents.consume-notifications during its
        # periodic refresh. Leave them undelivered so the agent can read them.
        return "DEFERRED_TO_AGENT"

    if target_kind == "public-bot-user":
        # Outbound from Raven back to a paying/onboarding user on their original
        # public channel. target_id may be raw ("123") or normalized
        # ("tg:123"/"discord:123"); channel_kind picks the platform.
        channel_kind = (row.get("channel_kind") or "").lower()
        return _deliver_public_bot_user(
            cfg,
            channel_kind=channel_kind,
            target_id=str(row.get("target_id") or ""),
            message=str(row.get("message") or ""),
            extra=extra,
            conn=conn,
        )

    if target_kind == "captain-wrapped":
        # ArcLink Wrapped uses the same public-channel delivery rail as Raven
        # outreach, but carries a distinct target kind so reports can be
        # audited and retried independently from normal public bot messages.
        channel_kind = (row.get("channel_kind") or "").lower()
        target_id = str(row.get("target_id") or "")
        if channel_kind not in {"telegram", "discord"}:
            resolved_kind, resolved_target = _resolve_captain_wrapped_public_channel(
                cfg,
                user_id=str(extra.get("user_id") or ""),
            )
            channel_kind = resolved_kind
            target_id = resolved_target
        if channel_kind not in {"telegram", "discord"} or not target_id:
            return "captain-wrapped public delivery channel is not available"
        return _deliver_public_bot_user(
            cfg,
            channel_kind=channel_kind,
            target_id=target_id,
            message=str(row.get("message") or ""),
            extra=extra,
            conn=conn,
        )

    if target_kind == "public-agent-turn":
        return _deliver_public_agent_turn(cfg, row, extra)

    return f"unknown target_kind: {target_kind}"


def _mark_wrapped_report_delivered(conn: Any, row: dict[str, Any]) -> None:
    if str(row.get("target_kind") or "").lower() != "captain-wrapped":
        return
    try:
        extra = json.loads(str(row.get("extra_json") or "{}"))
    except json.JSONDecodeError:
        extra = {}
    if not isinstance(extra, dict):
        return
    report_id = str(extra.get("report_id") or "").strip()
    if not report_id:
        return
    conn.execute(
        """
        UPDATE arclink_wrapped_reports
        SET status = 'delivered',
            delivered_at = ?
        WHERE report_id = ?
          AND status IN ('generated', 'delivered')
        """,
        (utc_now_iso(), report_id),
    )
    conn.commit()


def _is_operator_upgrade_notification(row: dict[str, Any]) -> bool:
    return (
        str(row.get("target_kind") or "").lower() == "operator"
        and str(row.get("message") or "").startswith("ArcLink update available:")
    )


def run_once(cfg: Config, *, limit: int = 50, verbose: bool = False) -> dict[str, Any]:
    summary = {
        "processed": 0,
        "delivered": 0,
        "errors": 0,
        "skipped_tui": 0,
        "curator_fanout_batches": 0,
        "curator_fanout_agents": 0,
        "deferred_to_agent": 0,
        "deferred_public_agent_bridge": 0,
        "unconfirmed_public_agent_bridge": 0,
        "reclaimed_public_agent_bridge_orphans": reap_orphaned_public_agent_bridge_leases(cfg, limit=limit),
        "claimed_elsewhere": 0,
        "deferred_during_deploy": 0,
    }
    with connect_db(cfg) as conn:
        if has_pending_curator_brief_fanout(conn):
            fanout = consume_curator_brief_fanout(conn, cfg)
            summary["curator_fanout_batches"] += 1
            summary["curator_fanout_agents"] += len(fanout.get("published_agents", []))
            if verbose:
                sys.stderr.write(
                    f"[deliver] curator brief-fanout processed "
                    f"{fanout.get('processed_notifications', 0)} row(s); "
                    f"published {summary['curator_fanout_agents']} payload(s)\n"
                )

        rows = fetch_undelivered_notifications(
            conn,
            limit=limit,
            include_user_agent=False,
            include_curator=False,
        )
        deploy_operation = active_deploy_operation(cfg)

        for row in rows:
            if not _notification_due_now(row):
                continue
            summary["processed"] += 1
            if str(row.get("target_kind") or "").lower() == "public-agent-turn" and not (
                _claim_notification_for_delivery(
                    conn,
                    int(row["id"]),
                    lease_seconds=_public_agent_turn_lease_seconds(),
                )
            ):
                summary["claimed_elsewhere"] += 1
                continue
            if deploy_operation is not None and _is_operator_upgrade_notification(row):
                summary["deferred_during_deploy"] += 1
                if verbose:
                    sys.stderr.write(
                        f"[deliver] id={row['id']} deferred during "
                        f"{deploy_operation.get('operation', 'deploy')}\n"
                    )
                continue
            try:
                error = deliver_row(cfg, row, conn=conn)
            except Exception as exc:  # noqa: BLE001
                error = f"exception: {exc}"

            if error == "DEFERRED_TO_AGENT":
                summary["deferred_to_agent"] += 1
                continue
            if error == PUBLIC_AGENT_BRIDGE_DEFERRED:
                # Non-terminal: the bridge job detached and will report later.
                # Clear any prior terminal credit (BUG #1).
                if str(row.get("target_kind") or "").strip().lower() == "public-agent-turn":
                    _reset_public_agent_bridge_terminal_failures(conn, int(row["id"]))
                summary["deferred_public_agent_bridge"] += 1
                continue
            if _is_public_agent_bridge_unconfirmed(error):
                _mark_public_agent_bridge_unconfirmed(conn, int(row["id"]), error)
                summary["unconfirmed_public_agent_bridge"] += 1
                continue
            if error == "HANDLED_BY_CONSUMER":
                # Safety: any remaining curator rows are already handled above.
                continue
            is_public_agent_turn = (
                str(row.get("target_kind") or "").strip().lower() == "public-agent-turn"
            )
            if error:
                # C1: public-agent-turn rows can be owned by a DETACHED bridge worker.
                # This generic loop is the in-process claim-holder, not a detached
                # worker, so its terminal writes for bridge rows use the empty-token
                # guard -- they finalise ONLY a row no detached worker currently owns
                # (and only when not yet delivered). A row re-leased to a detached
                # worker is left for that worker to finalise, so this loop never
                # clobbers a delivery/error another owner is authoritative for. The
                # hiccup page then fires ONLY when this caller actually recorded the
                # error. Non-bridge kinds keep the bare retry-scheduling write.
                if is_public_agent_turn:
                    if mark_notification_error_if_owned(conn, int(row["id"]), error, "") >= 1:
                        _maybe_report_public_agent_bridge_hiccup(
                            conn, int(row["id"]), error=error
                        )
                else:
                    mark_notification_error(conn, int(row["id"]), error)
                    _maybe_report_public_agent_bridge_hiccup(conn, int(row["id"]), error=error)
                summary["errors"] += 1
                if verbose:
                    sys.stderr.write(f"[deliver] id={row['id']} error={error}\n")
                continue
            if is_public_agent_turn:
                # C1: empty-token guarded delivered-mark. Only run the resolve and
                # count it as delivered when THIS write actually finalised the row
                # (rowcount>=1). If a detached worker owns the row the write is a
                # no-op -- leave the resolve and the delivered side effects to that
                # owning worker. Mirrors the dedicated loop at :3116.
                if mark_notification_delivered_if_owned(conn, int(row["id"]), "") >= 1:
                    # Resolve-on-delivery: a turn that paged at the terminal-attempt
                    # threshold can still self-heal and deliver on a later retry (no
                    # max-attempt cap), so clear its alert (BUG #1).
                    _resolve_public_agent_bridge_hiccup(conn, int(row["id"]))
                    summary["delivered"] += 1
                continue
            mark_notification_delivered(conn, int(row["id"]))
            _mark_wrapped_report_delivered(conn, row)
            summary["delivered"] += 1
            if (row.get("channel_kind") or "").lower() == "tui-only":
                summary["skipped_tui"] += 1
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deliver queued ArcLink notifications.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--public-agent-bridge-worker", default="", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.public_agent_bridge_worker:
        raise SystemExit(_run_public_agent_bridge_worker(Path(args.public_agent_bridge_worker)))
    cfg = Config.from_env()
    summary = run_once(cfg, limit=args.limit, verbose=args.verbose)
    json.dump(summary, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
