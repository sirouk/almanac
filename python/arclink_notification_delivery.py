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
import urllib.error
import urllib.request
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
PUBLIC_AGENT_BRIDGE_PYTHON = "/opt/arclink/runtime/hermes-venv/bin/python3"
PUBLIC_AGENT_BRIDGE_SCRIPT = "/home/arclink/arclink/python/arclink_public_agent_bridge.py"
PUBLIC_AGENT_BRIDGE_CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
PUBLIC_AGENT_BRIDGE_PROJECT_RE = re.compile(r"^arclink(?:-[a-z0-9][a-z0-9_-]{0,80})?$")
GATEWAY_EXEC_BROKER_TOKEN_HEADER = "X-ArcLink-Gateway-Exec-Token"


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
        return True, ""
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
    expected_project = str(project_name or "").strip()

    if len(parts) == 6 and parts[:3] == ["docker", "exec", "-i"] and parts[4:] == bridge_tail:
        container_name = parts[3].strip()
        if not PUBLIC_AGENT_BRIDGE_CONTAINER_RE.fullmatch(container_name):
            return False, "", "public Agent bridge container name is not allowlisted"
        if "hermes-gateway" not in container_name:
            return False, "", "public Agent bridge may only exec the hermes-gateway service"
        if expected_project and not (
            container_name.startswith(f"{expected_project}-") or container_name.startswith(f"{expected_project}_")
        ):
            return False, "", "public Agent bridge container does not match the deployment project"
        return True, "docker-exec-hermes-gateway", ""

    if (
        len(parts) == 13
        and parts[:3] == ["docker", "compose", "-p"]
        and parts[4] == "--env-file"
        and parts[6] == "-f"
        and parts[8:11] == ["exec", "-T", "hermes-gateway"]
        and parts[11:] == bridge_tail
    ):
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
        for key in ("telegram_update_kind", "telegram_update_json", "telegram_native_callback"):
            value = extra.get(key)
            if value not in (None, ""):
                payload[key] = value
    return payload, ""


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
    bridge_cmd = [
        PUBLIC_AGENT_BRIDGE_PYTHON,
        PUBLIC_AGENT_BRIDGE_SCRIPT,
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
        try:
            _preflight_deployment_compose_config_files(
                env_file=env_file,
                compose_file=compose_file,
                context="public Agent gateway bridge",
            )
        except ValueError as exc:
            return False, f"Hermes public gateway bridge config rejected: {str(exc)[:220]}"
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
    if isinstance(payload_out, dict) and payload_out.get("ok") is True:
        return True, ""
    return False, "Hermes public gateway bridge completed without an ok response"


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
    bridge_cmd = [
        PUBLIC_AGENT_BRIDGE_PYTHON,
        PUBLIC_AGENT_BRIDGE_SCRIPT,
    ]
    container = _deployment_service_container(
        project_name=project_name,
        service="control-operator-hermes-gateway",
    )
    if not container:
        return False, "operator Hermes gateway container not found in the Control Node stack"
    cmd = ["docker", "exec", "-i", container, *bridge_cmd]
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
    if isinstance(payload_out, dict) and payload_out.get("ok") is True:
        return True, ""
    return False, "Hermes operator gateway bridge completed without an ok response"


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


def _write_public_agent_bridge_job(
    *,
    notification_id: int,
    cmd: list[str] | None = None,
    payload: dict[str, Any] | None = None,
    project_name: str = "",
    gateway_exec_request: dict[str, Any] | None = None,
) -> Path:
    body: dict[str, Any]
    if gateway_exec_request is not None:
        if not isinstance(gateway_exec_request, dict):
            raise ValueError("gateway exec broker request must be a JSON object")
        command_kind = "gateway-exec-broker-request"
        body = {
            "notification_id": int(notification_id),
            "command_kind": command_kind,
            "gateway_exec_request": gateway_exec_request,
            "timeout_seconds": _public_agent_bridge_max_seconds(),
        }
    else:
        clean_cmd = [str(part) for part in cmd or []]
        valid, command_kind, reason = _validate_public_agent_bridge_cmd(clean_cmd, project_name=project_name)
        if not valid:
            raise ValueError(reason)
        body = {
            "notification_id": int(notification_id),
            "cmd": clean_cmd,
            "command_kind": command_kind,
            "project_name": str(project_name or "").strip(),
            "payload": payload or {},
            "timeout_seconds": _public_agent_bridge_max_seconds(),
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


def _append_public_agent_bridge_log(message: str) -> None:
    try:
        log_path = _public_agent_bridge_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n")
    except OSError:
        return


def _run_public_agent_bridge_worker(job_path: Path) -> int:
    try:
        job = _load_public_agent_bridge_job(job_path)
        notification_id = int(job.get("notification_id") or 0)
        cmd = [str(part) for part in job.get("cmd") or []]
        project_name = str(job.get("project_name") or "").strip()
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        gateway_exec_request = job.get("gateway_exec_request") if isinstance(job.get("gateway_exec_request"), dict) else None
        timeout_seconds = int(job.get("timeout_seconds") or _public_agent_bridge_max_seconds())
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
                    mark_notification_delivered(conn, notification_id)
                _append_public_agent_bridge_log(
                    json.dumps(
                        {"event": "public_agent_bridge_broker_delivered", "notification_id": notification_id},
                        sort_keys=True,
                    )
                )
                return 0
            with connect_db(cfg) as conn:
                mark_notification_error(conn, notification_id, f"Hermes public gateway bridge failed: {error}")
            _append_public_agent_bridge_log(
                json.dumps(
                    {
                        "event": "public_agent_bridge_broker_failed",
                        "notification_id": notification_id,
                        "error": str(error)[:500],
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
                mark_notification_error(conn, notification_id, f"Hermes public gateway bridge rejected command: {reason}")
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
            with connect_db(cfg) as conn:
                mark_notification_error(conn, notification_id, "Hermes public gateway bridge timed out")
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
            with connect_db(cfg) as conn:
                mark_notification_error(conn, notification_id, f"Hermes public gateway bridge failed: {tail}")
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
        if isinstance(payload_out, dict) and payload_out.get("ok") is True:
            with connect_db(cfg) as conn:
                mark_notification_delivered(conn, notification_id)
            _append_public_agent_bridge_log(
                json.dumps({"event": "public_agent_bridge_delivered", "notification_id": notification_id}, sort_keys=True)
            )
            return 0
        with connect_db(cfg) as conn:
            mark_notification_error(
                conn,
                notification_id,
                "Hermes public gateway bridge completed without an ok response",
            )
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
        try:
            job_path = _write_public_agent_bridge_job(
                notification_id=notification_id,
                cmd=clean_cmd,
                payload=payload or {},
                project_name=project_name,
                gateway_exec_request=gateway_exec_request,
            )
        except (OSError, ValueError) as exc:
            return False, f"could not write public gateway bridge job: {str(exc)[:180]}"
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
                try:
                    returncode = proc.wait(timeout=0.25)
                except subprocess.TimeoutExpired:
                    return True, ""
                if returncode == 0:
                    return True, ""
                return False, f"Hermes public gateway bridge worker exited immediately with status {returncode}; see {log_path}"
        except OSError as exc:
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
            sent = discord_send_message(bot_token=bot_token, channel_id=channel_id, text=message, components=discord_components)
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
        "deferred_public_agent_bridge": 0,
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
                    summary["deferred_public_agent_bridge"] += 1
                    continue
                mark_notification_error(conn, int(row["id"]), error)
                summary["errors"] += 1
                if verbose:
                    sys.stderr.write(f"[deliver-public-agent] id={row['id']} error={error}\n")
                continue
            mark_notification_delivered(conn, int(row["id"]))
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
                summary["deferred_public_agent_bridge"] += 1
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
