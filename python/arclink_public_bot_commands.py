#!/usr/bin/env python3
from __future__ import annotations

import os
import pathlib
import json
import shlex
import sqlite3
import subprocess
import sys
from typing import Any, Mapping

_PYTHON_DIR = pathlib.Path(__file__).resolve().parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from arclink_discord import DiscordConfig, register_arclink_public_discord_commands
from arclink_control import queue_notification, utc_now_iso
from arclink_telegram import (
    TelegramConfig,
    arclink_public_bot_telegram_active_command_plan,
    arclink_public_bot_telegram_agent_commands,
    ensure_arclink_public_telegram_webhook,
    refresh_arclink_public_telegram_chat_commands,
    register_arclink_public_telegram_commands,
)


def _load_shell_env_file(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    candidate = pathlib.Path(str(path or "")).expanduser()
    if not candidate.is_file():
        return env
    for raw_line in candidate.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        try:
            parts = shlex.split(f"VALUE={raw_value}", posix=True)
            value = parts[0].split("=", 1)[1] if parts else ""
        except ValueError:
            value = raw_value.strip().strip("'\"")
        env[key] = value
    return env


def _merged_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    merged = dict(os.environ)
    config_file = str(merged.get("ARCLINK_CONFIG_FILE") or "").strip()
    if config_file:
        for key, value in _load_shell_env_file(config_file).items():
            merged.setdefault(key, value)
    if env:
        merged.update(dict(env))
    return merged


def _host_path(env: Mapping[str, str], path_value: str) -> str:
    path = str(path_value or "").strip()
    container_priv = str(env.get("ARCLINK_DOCKER_CONTAINER_PRIV_DIR") or "/home/arclink/arclink/arclink-priv").rstrip("/")
    host_priv = str(env.get("ARCLINK_DOCKER_HOST_PRIV_DIR") or "").rstrip("/")
    if host_priv and path.startswith(container_priv + "/"):
        return f"{host_priv}/{path[len(container_priv) + 1:]}"
    return path


def _control_db_path(env: Mapping[str, str]) -> str:
    db_path = str(env.get("ARCLINK_DB_PATH") or "").strip()
    if not db_path:
        state_dir = str(env.get("STATE_DIR") or "").strip()
        if state_dir:
            db_path = f"{state_dir.rstrip('/')}/arclink-control.sqlite3"
    return _host_path(env, db_path)


def _json_loads(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(str(raw or "{}"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _redacted_identity(identity: str) -> str:
    clean = str(identity or "").strip()
    if clean.startswith("tg:") and len(clean) > 7:
        return f"tg:*{clean[-4:]}"
    if len(clean) > 8:
        return f"*{clean[-4:]}"
    return clean


def _agent_commands_from_gateway_container(deployment_id: str) -> tuple[list[dict[str, str]], str, int]:
    clean_deployment = str(deployment_id or "").strip()
    if not clean_deployment:
        return [], "missing-deployment", 0
    container = f"arclink-{clean_deployment}-hermes-gateway-1"
    script = r"""
import json
from hermes_cli.commands import telegram_menu_commands
cmds, hidden = telegram_menu_commands(max_commands=100)
print(json.dumps({"commands":[{"command": n, "description": d} for n, d in cmds], "hidden": hidden}, separators=(",", ":")))
"""
    command = [
        "docker",
        "exec",
        container,
        "bash",
        "-lc",
        "PYTHONPATH=/opt/arclink/runtime/hermes-agent-src "
        "/opt/arclink/runtime/hermes-venv/bin/python3 - <<'PY'\n"
        f"{script}\n"
        "PY",
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        commands = payload.get("commands")
        if isinstance(commands, list):
            return [item for item in commands if isinstance(item, dict)], container, int(payload.get("hidden") or 0)
    except Exception:
        return [], "fallback", 0
    return [], "fallback", 0


def _update_session_command_scope_metadata(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    metadata: dict[str, Any],
) -> None:
    conn.execute(
        "UPDATE arclink_onboarding_sessions SET metadata_json = ?, updated_at = ? WHERE session_id = ?",
        (json.dumps(metadata, sort_keys=True, separators=(",", ":")), utc_now_iso(), session_id),
    )


def refresh_active_telegram_command_scopes(env: Mapping[str, str]) -> dict[str, Any]:
    token = str(env.get("TELEGRAM_BOT_TOKEN") or "").strip()
    db_path = _control_db_path(env)
    if not token or not db_path or not pathlib.Path(db_path).is_file():
        return {"skipped": True, "reason": "missing_token_or_db"}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT session_id, channel_identity, deployment_id, metadata_json
        FROM arclink_onboarding_sessions
        WHERE channel = 'telegram'
          AND deployment_id != ''
          AND status IN ('active', 'first_contacted')
        ORDER BY updated_at DESC
        """
    ).fetchall()
    refreshed = 0
    issues: list[dict[str, Any]] = []
    try:
        for row in rows:
            identity = str(row["channel_identity"] or "")
            chat_id = identity.removeprefix("tg:")
            if not chat_id:
                continue
            commands, source, source_hidden_count = _agent_commands_from_gateway_container(str(row["deployment_id"] or ""))
            if not commands:
                commands = arclink_public_bot_telegram_agent_commands(env=env)
            plan = arclink_public_bot_telegram_active_command_plan(agent_commands=commands, env=env)
            result = refresh_arclink_public_telegram_chat_commands(
                bot_token=token,
                chat_id=chat_id,
                include_agent_commands=True,
                env=env,
                force=True,
            )
            # refresh_arclink_public_telegram_chat_commands uses local runtime
            # discovery. Re-register with the exact per-agent command plan when
            # we got one from the running gateway container.
            if source != "fallback":
                from arclink_telegram import telegram_set_my_commands, _telegram_chat_scope  # local import for testability

                telegram_set_my_commands(
                    bot_token=token,
                    commands=list(plan["commands"]),
                    scope=_telegram_chat_scope(chat_id),
                )
                result = {**result, **plan, "command_count": len(plan["commands"])}
            metadata = _json_loads(str(row["metadata_json"] or "{}"))
            metadata["telegram_active_agent_command_names"] = list(plan.get("agent_command_names") or [])
            metadata["telegram_raven_control_command"] = str(plan.get("raven_command") or "raven")
            metadata["telegram_command_scope_refreshed_at"] = utc_now_iso()
            metadata["telegram_command_scope_source"] = source
            metadata["telegram_command_scope_legacy_conflicts"] = list(plan.get("legacy_raven_conflicts") or [])
            metadata["telegram_command_scope_hard_conflicts"] = list(plan.get("hard_raven_conflicts") or [])
            metadata["telegram_command_scope_policy_suppressed"] = list(plan.get("policy_suppressed") or [])
            metadata["telegram_command_scope_hidden_count"] = max(
                int(source_hidden_count or 0),
                int(plan.get("hidden_count") or 0),
            )
            signature = "|".join(
                [
                    ",".join(metadata["telegram_command_scope_legacy_conflicts"]),
                    ",".join(metadata["telegram_command_scope_hard_conflicts"]),
                    ",".join(metadata["telegram_command_scope_policy_suppressed"]),
                    str(metadata["telegram_command_scope_hidden_count"]),
                    str(plan.get("raven_command") or ""),
                ]
            )
            if (
                metadata["telegram_command_scope_legacy_conflicts"]
                or metadata["telegram_command_scope_hard_conflicts"]
                or metadata["telegram_command_scope_policy_suppressed"]
                or metadata["telegram_command_scope_hidden_count"]
            ):
                if metadata.get("telegram_command_scope_alert_signature") != signature:
                    issues.append(
                        {
                            "session_id": str(row["session_id"] or ""),
                            "channel": _redacted_identity(identity),
                            "deployment_id": str(row["deployment_id"] or ""),
                            "raven_command": str(plan.get("raven_command") or "raven"),
                            "legacy_conflicts": metadata["telegram_command_scope_legacy_conflicts"],
                            "hard_conflicts": metadata["telegram_command_scope_hard_conflicts"],
                            "policy_suppressed": metadata["telegram_command_scope_policy_suppressed"],
                            "hidden_count": metadata["telegram_command_scope_hidden_count"],
                        }
                    )
                    metadata["telegram_command_scope_alert_signature"] = signature
            _update_session_command_scope_metadata(
                conn,
                session_id=str(row["session_id"] or ""),
                metadata=metadata,
            )
            refreshed += 1
        conn.commit()
        if issues:
            snippets = []
            for issue in issues[:5]:
                snippets.append(
                    f"{issue['channel']} raven=/{issue['raven_command']} "
                    f"legacy={','.join(issue['legacy_conflicts']) or '-'} "
                    f"hard={','.join(issue['hard_conflicts']) or '-'} "
                    f"suppressed={','.join(issue['policy_suppressed']) or '-'} "
                    f"hidden={issue['hidden_count'] or 0}"
                )
            message = (
                "ArcLink Telegram command scope drift detected after command refresh.\n\n"
                "Raven kept the visible active-chat menu conflict-free by moving ArcLink controls behind the Raven command and letting the active agent own the bare slash namespace. Telegram command menus are capped, so hidden counts mean some active-agent commands remain reachable by typing them or through Helm even though Telegram cannot show them all.\n\n"
                + "\n".join(f"- {line}" for line in snippets)
            )
            queue_notification(
                conn,
                target_kind="operator",
                target_id=str(env.get("OPERATOR_NOTIFY_CHANNEL_ID") or env.get("OPERATOR_NOTIFY_CHANNEL_PLATFORM") or "operator"),
                channel_kind=str(env.get("OPERATOR_NOTIFY_CHANNEL_PLATFORM") or "tui-only"),
                message=message,
                extra={"source": "public-bot-command-scope-refresh", "issue_count": len(issues)},
            )
        conn.commit()
    finally:
        conn.close()
    return {"refreshed": refreshed, "issues": len(issues), "skipped": False}


def register_public_bot_commands(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    merged = _merged_env(env)
    results: dict[str, Any] = {"telegram": {"skipped": True}, "discord": {"skipped": True}, "errors": []}

    telegram = TelegramConfig.from_env(merged)
    if telegram.bot_token:
        try:
            results["telegram"] = register_arclink_public_telegram_commands(telegram.bot_token)
            results["telegram"]["webhook"] = ensure_arclink_public_telegram_webhook(
                telegram.bot_token,
                telegram.webhook_url,
            )
            results["telegram"]["active_scopes"] = refresh_active_telegram_command_scopes(merged)
        except Exception as exc:  # noqa: BLE001 - keep registering other platforms
            results["telegram"] = {"error": str(exc)}
            results["errors"].append("telegram")

    discord = DiscordConfig.from_env(merged)
    if discord.bot_token and discord.app_id:
        try:
            results["discord"] = register_arclink_public_discord_commands(discord)
        except Exception as exc:  # noqa: BLE001 - keep the deploy flow resilient
            results["discord"] = {"error": str(exc)}
            results["errors"].append("discord")

    return results


def main() -> int:
    result = register_public_bot_commands()

    telegram = result.get("telegram") or {}
    discord = result.get("discord") or {}
    if telegram.get("skipped"):
        print("Telegram public bot actions: skipped (no bot token)")
    elif telegram.get("error"):
        print(f"Telegram public bot actions: failed ({telegram.get('error')})", file=sys.stderr)
    else:
        webhook = telegram.get("webhook") or {}
        webhook_note = ""
        if webhook.get("skipped"):
            webhook_note = " (webhook unchanged)"
        elif webhook.get("allowed_updates"):
            webhook_note = " (webhook accepts callback_query)"
        print(
            "Telegram public bot actions: registered "
            f"{len(telegram.get('registered') or [])} command(s) across "
            f"{', '.join(telegram.get('scopes') or [])}"
            f"{webhook_note}"
        )
        active_scopes = telegram.get("active_scopes") or {}
        if active_scopes.get("skipped"):
            print(f"Telegram active agent command scopes: skipped ({active_scopes.get('reason')})")
        else:
            print(
                "Telegram active agent command scopes: refreshed "
                f"{active_scopes.get('refreshed', 0)} chat(s), "
                f"{active_scopes.get('issues', 0)} issue alert(s)"
            )
    if discord.get("skipped"):
        print("Discord public bot actions: skipped (missing bot token or application ID)")
    elif discord.get("error"):
        print(f"Discord public bot actions: failed ({discord.get('error')})", file=sys.stderr)
    else:
        print(
            "Discord public bot actions: registered "
            f"{len(discord.get('registered') or [])} command(s) to {discord.get('scope')}"
        )
    return 1 if result.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
