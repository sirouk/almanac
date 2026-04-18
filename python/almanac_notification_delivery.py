#!/usr/bin/env python3
"""Deliver queued Almanac notifications to Discord, Telegram, or the TUI-only outbox.

Runs as a periodic/oneshot service. Idempotent: only picks up rows with
`delivered_at IS NULL`. Records per-row errors in `delivery_error` without blocking
the batch.

The TUI-only channel is intentionally a no-op delivery: it marks the row delivered
so it drops out of the undelivered queue but remains readable via
`almanac-ctl notifications list` and via MCP `notifications.list`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from almanac_control import (
    Config,
    config_env_value,
    connect_db,
    consume_curator_brief_fanout,
    fetch_undelivered_notifications,
    has_pending_curator_brief_fanout,
    mark_notification_delivered,
    mark_notification_error,
)
from almanac_discord import discord_send_message
from almanac_http import http_request
from almanac_telegram import telegram_send_message


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


def deliver_discord_channel(message: str, *, bot_token: str, channel_id: str) -> str | None:
    if not bot_token:
        return "DISCORD_BOT_TOKEN is not configured"
    if not channel_id:
        return "discord channel_id is empty"
    if not channel_id.isdigit():
        return f"discord channel_id must be numeric, got {channel_id[:60]!r}"
    try:
        discord_send_message(bot_token=bot_token, channel_id=channel_id, text=message)
    except Exception as exc:  # noqa: BLE001
        return str(exc).strip() or "unknown discord delivery error"
    return None


def deliver_telegram(
    message: str,
    *,
    bot_token: str,
    chat_id: str,
    reply_markup: dict[str, Any] | None = None,
) -> str | None:
    if not bot_token:
        return "TELEGRAM_BOT_TOKEN is not configured"
    if not chat_id:
        return "telegram chat_id is empty"
    try:
        telegram_send_message(
            bot_token=bot_token,
            chat_id=chat_id,
            text=message,
            reply_markup=reply_markup,
        )
    except Exception as exc:  # noqa: BLE001
        return str(exc).strip() or "unknown telegram delivery error"
    return None


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


def deliver_row(cfg: Config, row: dict[str, Any]) -> str | None:
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
            if target_kind == "webhook":
                return deliver_discord(row["message"], webhook_url=target_value)
            if target_kind == "channel":
                return deliver_discord_channel(
                    row["message"],
                    bot_token=_resolve_curator_discord_bot_token(cfg),
                    channel_id=target_value,
                )
            return "discord target is not configured"
        if platform == "telegram":
            bot_token = config_env_value("TELEGRAM_BOT_TOKEN", "").strip()
            chat_id = str(row.get("target_id") or cfg.operator_notify_channel_id or "")
            reply_markup = extra.get("telegram_reply_markup")
            if not isinstance(reply_markup, dict):
                reply_markup = None
            return deliver_telegram(
                row["message"],
                bot_token=bot_token,
                chat_id=chat_id,
                reply_markup=reply_markup,
            )
        # tui-only: no external delivery; row stays readable via notifications.list.
        return None

    if target_kind == "curator":
        # Curator brief-fanout rows are actuated by consume_curator_brief_fanout,
        # which publishes central managed-memory JSON for each impacted agent and
        # marks its own rows delivered. Running it here is safe and idempotent —
        # the worker is the scheduler for Curator side-effects.
        return "HANDLED_BY_CONSUMER"

    if target_kind == "user-agent":
        # Per-agent notifications (SSOT nudges, subscription signals) are consumed
        # by the user agent itself via agents.consume-notifications during its
        # periodic refresh. Leave them undelivered so the agent can read them.
        return "DEFERRED_TO_AGENT"

    return f"unknown target_kind: {target_kind}"


def run_once(cfg: Config, *, limit: int = 50, verbose: bool = False) -> dict[str, Any]:
    summary = {
        "processed": 0,
        "delivered": 0,
        "errors": 0,
        "skipped_tui": 0,
        "curator_fanout_batches": 0,
        "curator_fanout_agents": 0,
        "deferred_to_agent": 0,
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

        rows = fetch_undelivered_notifications(conn, limit=limit, include_user_agent=False)

        for row in rows:
            summary["processed"] += 1
            try:
                error = deliver_row(cfg, row)
            except Exception as exc:  # noqa: BLE001
                error = f"exception: {exc}"

            if error == "DEFERRED_TO_AGENT":
                summary["deferred_to_agent"] += 1
                continue
            if error == "HANDLED_BY_CONSUMER":
                # Safety: any remaining curator rows are already handled above.
                continue
            if error:
                mark_notification_error(conn, int(row["id"]), error)
                summary["errors"] += 1
                if verbose:
                    sys.stderr.write(f"[deliver] id={row['id']} error={error}\n")
                continue
            mark_notification_delivered(conn, int(row["id"]))
            summary["delivered"] += 1
            if (row.get("channel_kind") or "").lower() == "tui-only":
                summary["skipped_tui"] += 1
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deliver queued Almanac notifications.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = Config.from_env()
    summary = run_once(cfg, limit=args.limit, verbose=args.verbose)
    json.dump(summary, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
