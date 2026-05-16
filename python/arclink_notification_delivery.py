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
import os
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
    parse_utc_iso,
    utc_now,
    utc_after_seconds_iso,
    utc_now_iso,
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
    reply_to_message_id: int | None = None,
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
            reply_to_message_id=reply_to_message_id,
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


def _notification_due_now(row: dict[str, Any]) -> bool:
    next_attempt_at = str(row.get("next_attempt_at") or "").strip()
    if not next_attempt_at:
        return True
    parsed = parse_utc_iso(next_attempt_at)
    return parsed is not None and parsed <= utc_now()


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


def _run_public_agent_gateway_turn(
    *,
    deployment_id: str,
    prefix: str,
    channel_kind: str,
    target_id: str,
    prompt: str,
    extra: dict[str, Any],
) -> tuple[bool, str]:
    """Try to route a public bot turn through Hermes' native gateway pipeline.

    The legacy quiet CLI path can produce a text answer, but it bypasses
    platform behavior such as Telegram reactions, typing indicators, interim
    assistant messages, native command handling, and platform formatting. The
    bridge helper runs inside the deployment container and receives secrets via
    stdin so bot tokens never appear in argv.
    """
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
            return False, "DISCORD_BOT_TOKEN is not configured for Hermes public gateway bridge"
        if not chat_id and user_id:
            try:
                dm = discord_create_dm_channel(bot_token=bot_token, recipient_id=user_id)
                chat_id = str(dm.get("id") or "").strip() if isinstance(dm, dict) else ""
            except Exception as exc:  # noqa: BLE001
                return False, f"discord public gateway bridge could not open DM: {str(exc)[:180]}"
    else:
        return False, f"Hermes public gateway bridge is not implemented for {clean_channel or 'blank'}"
    if not bot_token:
        return False, f"{clean_channel.upper()}_BOT_TOKEN is not configured for Hermes public gateway bridge"
    if not chat_id:
        return False, f"{clean_channel} public gateway bridge requires a channel id"
    if not user_id:
        return False, f"{clean_channel} public gateway bridge requires a user id"
    project_name = _compose_project_name(deployment_id)
    if not project_name:
        return False, "deployment id is missing"
    timeout_seconds = _int_env("ARCLINK_PUBLIC_AGENT_TURN_TIMEOUT_SECONDS", 180, minimum=15, maximum=900)
    bridge_cmd = [
        "/opt/arclink/runtime/hermes-venv/bin/python3",
        "/home/arclink/arclink/python/arclink_public_agent_bridge.py",
    ]
    container = _deployment_service_container(project_name=project_name, service="hermes-gateway")
    if container:
        cmd = ["docker", "exec", "-i", container, *bridge_cmd]
    else:
        root = _deployment_root(deployment_id=deployment_id, prefix=prefix)
        if root is None:
            return False, "deployment container/root not found for gateway bridge"
        compose_file = root / "config" / "compose.yaml"
        env_file = root / "config" / "arclink.env"
        if not compose_file.exists() or not env_file.exists():
            return False, "deployment compose files are missing for gateway bridge"
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
            *bridge_cmd,
        ]
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
    }
    if clean_channel == "telegram":
        for key in ("telegram_update_kind", "telegram_update_json", "telegram_native_callback"):
            value = extra.get(key)
            if value not in (None, ""):
                payload[key] = value
    if _public_agent_bridge_detached_enabled():
        return _spawn_public_agent_gateway_bridge(cmd=cmd, payload=payload)
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
    if isinstance(payload_out, dict) and payload_out.get("ok") is True:
        return True, ""
    return False, "Hermes public gateway bridge completed without an ok response"


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


def _public_agent_bridge_log_path() -> Path:
    state_dir = config_env_value("STATE_DIR", "").strip() or os.environ.get("STATE_DIR", "").strip()
    if not state_dir:
        state_dir = str(Path.cwd() / "arclink-priv" / "state")
    return Path(state_dir) / "docker" / "jobs" / "public-agent-bridge.log"


def _spawn_public_agent_gateway_bridge(*, cmd: list[str], payload: dict[str, Any]) -> tuple[bool, str]:
    log_path = _public_agent_bridge_log_path()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = log_path.open("a", encoding="utf-8")
    except OSError as exc:
        return False, f"could not open public gateway bridge log: {str(exc)[:180]}"
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=log_file,
            stderr=log_file,
            text=True,
            start_new_session=True,
        )
        if proc.stdin is None:
            return False, "could not open public gateway bridge stdin"
        proc.stdin.write(json.dumps(payload, sort_keys=True))
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
        reply_to_message_id = None
        try:
            reply_to_message_id = int(str(extra.get("telegram_reply_to_message_id") or "").strip() or "0") or None
        except ValueError:
            reply_to_message_id = None
        return deliver_telegram(
            message,
            bot_token=bot_token,
            chat_id=chat_id,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            reply_to_message_id=reply_to_message_id,
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
    bridged, _bridge_error = _run_public_agent_gateway_turn(
        deployment_id=deployment_id,
        prefix=prefix,
        channel_kind=channel_kind,
        target_id=target_id,
        prompt=prompt,
        extra={**extra, "agent_label": label},
    )
    if bridged:
        return None
    if not _public_agent_quiet_fallback_enabled():
        message = f"{label} did not answer through the Hermes gateway bridge yet.\n\n{_bridge_error}"
        if helm:
            message += f"\n\nHelm is still available: {helm}"
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
            message += f"\n\nHelm is still available: {helm}"
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
    }
    clean_channel = str(channel_kind or "").strip().lower()
    clean_target = str(target_id or "").strip()
    where = ["delivered_at IS NULL", "target_kind = 'public-agent-turn'"]
    params: list[Any] = []
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
                lease_seconds=_int_env("ARCLINK_PUBLIC_AGENT_TURN_TIMEOUT_SECONDS", 180, minimum=15, maximum=900) + 90,
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
                mark_notification_error(conn, int(row["id"]), error)
                summary["errors"] += 1
                if verbose:
                    sys.stderr.write(f"[deliver-public-agent] id={row['id']} error={error}\n")
                continue
            mark_notification_delivered(conn, int(row["id"]))
            summary["delivered"] += 1
    return summary


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

    if target_kind == "captain-wrapped":
        # ArcLink Wrapped uses the same public-channel delivery rail as Raven
        # outreach, but carries a distinct target kind so reports can be
        # audited and retried independently from normal public bot messages.
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
            _mark_wrapped_report_delivered(conn, row)
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
