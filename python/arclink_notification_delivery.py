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
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from arclink_control import (
    Config,
    active_deploy_operation,
    config_env_value,
    connect_db,
    consume_curator_brief_fanout,
    fetch_undelivered_notifications,
    has_pending_curator_brief_fanout,
    mark_notification_delivered,
    mark_notification_error,
)
from arclink_discord import discord_create_dm_channel, discord_send_message
from arclink_http import http_request
from arclink_telegram import telegram_send_message


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
) -> str | None:
    if not bot_token:
        return "DISCORD_BOT_TOKEN is not configured"
    if not channel_id:
        return "discord channel_id is empty"
    if not channel_id.isdigit():
        return f"discord channel_id must be numeric, got {channel_id[:60]!r}"
    try:
        discord_send_message(bot_token=bot_token, channel_id=channel_id, text=message, components=components)
    except Exception as exc:  # noqa: BLE001
        return str(exc).strip() or "unknown discord delivery error"
    return None


def deliver_discord_user(
    message: str,
    *,
    bot_token: str,
    user_id: str,
    components: list[dict[str, Any]] | None = None,
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
        discord_send_message(bot_token=bot_token, channel_id=channel_id, text=message, components=components)
    except Exception as exc:  # noqa: BLE001
        return str(exc).strip() or "unknown discord user delivery error"
    return None


def deliver_telegram(
    message: str,
    *,
    bot_token: str,
    chat_id: str,
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str = "",
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
            parse_mode=parse_mode,
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


def _strip_public_channel_prefix(target_id: str, prefix: str) -> str:
    value = str(target_id or "").strip()
    marker = f"{prefix}:"
    if value.lower().startswith(marker):
        return value[len(marker):].strip()
    return value


ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def _int_env(name: str, default: int, *, minimum: int = 1, maximum: int = 1800) -> int:
    raw = config_env_value(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _compose_project_name(deployment_id: str) -> str:
    clean = re.sub(r"[^a-z0-9_-]+", "-", str(deployment_id or "").strip().lower()).strip("-_")
    return f"arclink-{clean}" if clean else ""


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


def _deployment_service_container(*, project_name: str, service: str) -> str:
    if not project_name or not service:
        return ""
    cmd = [
        "docker",
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
        if not compose_file.exists() or not env_file.exists():
            return "", "The deployment compose files are missing, so Raven cannot reach the agent runtime yet."
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


def _deliver_public_bot_user(
    cfg: Config,
    *,
    channel_kind: str,
    target_id: str,
    message: str,
    extra: dict[str, Any],
) -> str | None:
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
        return deliver_telegram(
            message,
            bot_token=bot_token,
            chat_id=chat_id,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
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
        return deliver_discord_user(
            message,
            bot_token=bot_token,
            user_id=user_id,
            components=discord_components,
        )
    return f"public-bot-user delivery for channel_kind={channel_kind!r} not implemented yet"


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
    response, error = _run_public_agent_turn(deployment_id=deployment_id, prefix=prefix, prompt=prompt)
    if error:
        message = f"{label} did not answer through Raven yet.\n\n{error}"
        if helm:
            message += f"\n\nHelm is still available: {helm}"
    else:
        message = f"{label}:\n\n{response}"
    return _deliver_public_bot_user(
        cfg,
        channel_kind=channel_kind,
        target_id=target_id,
        message=message,
        extra={},
    )


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
            discord_components = extra.get("discord_components")
            if not isinstance(discord_components, list):
                discord_components = None
            if target_kind == "webhook":
                return deliver_discord(row["message"], webhook_url=target_value)
            if target_kind == "channel":
                return deliver_discord_channel(
                    row["message"],
                    bot_token=_resolve_curator_discord_bot_token(cfg),
                    channel_id=target_value,
                    components=discord_components,
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
        )

    if target_kind == "public-agent-turn":
        return _deliver_public_agent_turn(cfg, row, extra)

    return f"unknown target_kind: {target_kind}"


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
            summary["processed"] += 1
            if deploy_operation is not None and _is_operator_upgrade_notification(row):
                summary["deferred_during_deploy"] += 1
                if verbose:
                    sys.stderr.write(
                        f"[deliver] id={row['id']} deferred during "
                        f"{deploy_operation.get('operation', 'deploy')}\n"
                    )
                continue
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
    parser = argparse.ArgumentParser(description="Deliver queued ArcLink notifications.")
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
