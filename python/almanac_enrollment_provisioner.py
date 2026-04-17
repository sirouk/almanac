#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import pwd
import subprocess
import time
from pathlib import Path

from almanac_control import (
    Config,
    activation_trigger_path,
    auto_provision_retry_delay_seconds,
    config_env_value,
    connect_db,
    delete_onboarding_bot_token_secret,
    ensure_unix_user_ready,
    get_agent,
    issue_auto_provision_token,
    json_loads,
    list_pending_onboarding_bot_configurations,
    list_pending_auto_provision_requests,
    make_agent_id,
    mark_auto_provision_finished,
    mark_auto_provision_started,
    note_refresh_job,
    queue_notification,
    read_onboarding_bot_token_secret,
    save_onboarding_session,
    shell_quote,
    update_agent_channels,
)
from almanac_onboarding_flow import send_session_message


def _operator_target(cfg: Config) -> tuple[str, str]:
    return (
        cfg.operator_notify_channel_id or cfg.operator_notify_platform or "operator",
        cfg.operator_notify_platform or "tui-only",
    )


def _normalize_channels(row: dict) -> list[str]:
    requested = json_loads(str(row.get("requested_channels_json") or ""), [])
    if not requested:
        requested = json_loads(str(row.get("prior_defaults_json") or ""), {}).get("channels") or []
    channels: list[str] = []
    for raw in requested:
        value = str(raw).strip().lower()
        if value and value not in channels:
            channels.append(value)
    if any(channel in {"discord", "telegram"} for channel in channels):
        return ["tui-only"]
    if "tui-only" not in channels:
        channels.insert(0, "tui-only")
    return channels or ["tui-only"]


def _model_preset(cfg: Config, row: dict) -> str:
    requested = str(row.get("requested_model_preset") or "").strip().lower()
    if requested in cfg.model_presets:
        return requested
    prior = str(json_loads(str(row.get("prior_defaults_json") or ""), {}).get("model_preset") or "").strip().lower()
    if prior in cfg.model_presets:
        return prior
    return "codex"


def _log_dir(cfg: Config) -> Path:
    path = cfg.state_dir / "auto-provision"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _wait_for_user_bus(uid: str, timeout_seconds: int = 15) -> None:
    bus_path = Path(f"/run/user/{uid}/bus")
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if bus_path.exists():
            return
        time.sleep(0.5)


def _queue_operator_message(conn, cfg: Config, message: str) -> None:
    target_id, channel_kind = _operator_target(cfg)
    queue_notification(
        conn,
        target_kind="operator",
        target_id=target_id,
        channel_kind=channel_kind,
        message=message,
    )


def _write_env_values(path: Path, values: dict[str, str]) -> None:
    existing: dict[str, str] = {}
    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            existing[key.strip()] = value.strip().strip("'\"")
    existing.update(values)
    lines = [f"{key}={shell_quote(value)}" for key, value in sorted(existing.items())]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _notify_user_via_curator(cfg: Config, *, session: dict, message: str) -> None:
    try:
        send_session_message(cfg, session, message)
    except Exception:
        return


def _configure_user_telegram_gateway(conn, cfg: Config, session: dict) -> None:
    agent_id = str(session.get("linked_agent_id") or "")
    if not agent_id:
        raise ValueError(f"onboarding session {session['session_id']} is missing linked_agent_id")
    agent = get_agent(conn, agent_id)
    if agent is None:
        raise ValueError(f"unknown agent for onboarding session {session['session_id']}: {agent_id}")

    unix_user = str(agent["unix_user"])
    home = Path(pwd.getpwnam(unix_user).pw_dir)
    hermes_home = Path(str(agent["hermes_home"]))
    chat_id = str(session.get("chat_id") or "")
    pending_bot_token_path = str(session.get("pending_bot_token_path") or "")
    pending_bot_token = read_onboarding_bot_token_secret(pending_bot_token_path)
    if not pending_bot_token:
        pending_bot_token = str(session.get("pending_bot_token") or "")
    bot_username = str(session.get("telegram_bot_username") or "")
    if not pending_bot_token or not chat_id:
        raise ValueError(f"onboarding session {session['session_id']} is missing Telegram credentials")

    env_path = hermes_home / ".env"
    _write_env_values(
        env_path,
        {
            "TELEGRAM_BOT_TOKEN": pending_bot_token,
            "TELEGRAM_ALLOWED_USERS": chat_id,
            "TELEGRAM_HOME_CHANNEL": chat_id,
        },
    )
    try:
        subprocess.run(["chown", f"{unix_user}:{unix_user}", str(env_path)], check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"failed to chown {env_path}: {exc}") from exc

    update_agent_channels(
        conn,
        cfg,
        agent_id=agent_id,
        channels=["tui-only", "telegram"],
        home_channel={"platform": "telegram", "channel_id": chat_id},
    )

    uid = pwd.getpwnam(unix_user).pw_uid
    _wait_for_user_bus(str(uid))
    result = subprocess.run(
        [
            "runuser",
            "-u",
            unix_user,
            "--",
            str(cfg.repo_dir / "bin" / "install-agent-user-services.sh"),
            agent_id,
            str(cfg.repo_dir),
            str(hermes_home),
            json.dumps(["tui-only", "telegram"]),
            str(activation_trigger_path(cfg, agent_id)),
        ],
        env={
            **os.environ,
            "ALMANAC_CONFIG_FILE": os.environ.get("ALMANAC_CONFIG_FILE", ""),
            "HOME": str(home),
            "USER": unix_user,
            "LOGNAME": unix_user,
            "HERMES_HOME": str(hermes_home),
            "XDG_RUNTIME_DIR": f"/run/user/{uid}",
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{uid}/bus",
        },
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "install-agent-user-services failed").strip())

    save_onboarding_session(
        conn,
        session_id=str(session["session_id"]),
        state="completed",
        pending_bot_token="",
        pending_bot_token_path="",
        provision_error="",
        completed_at=dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
    )
    delete_onboarding_bot_token_secret(pending_bot_token_path)
    note_refresh_job(
        conn,
        job_name=f"onboarding-{session['session_id']}",
        job_kind="onboarding",
        target_id=agent_id,
        schedule="approval",
        status="ok",
        note=f"telegram gateway configured for @{bot_username or 'bot'}",
    )
    _queue_operator_message(
        conn,
        cfg,
        f"Onboarding complete for {agent_id} ({unix_user}); Telegram bot @{bot_username or 'unknown'} is live.",
    )
    _notify_user_via_curator(
        cfg,
        session=session,
        message=(
            f"Everything is ready. Your own bot is @{bot_username or 'your bot'} now. "
            f"Talk to it directly from here on out."
        ),
    )


def _configure_user_discord_gateway(conn, cfg: Config, session: dict) -> None:
    agent_id = str(session.get("linked_agent_id") or "")
    if not agent_id:
        raise ValueError(f"onboarding session {session['session_id']} is missing linked_agent_id")
    agent = get_agent(conn, agent_id)
    if agent is None:
        raise ValueError(f"unknown agent for onboarding session {session['session_id']}: {agent_id}")

    unix_user = str(agent["unix_user"])
    home = Path(pwd.getpwnam(unix_user).pw_dir)
    hermes_home = Path(str(agent["hermes_home"]))
    sender_id = str(session.get("sender_id") or "")
    pending_bot_token_path = str(session.get("pending_bot_token_path") or "")
    pending_bot_token = read_onboarding_bot_token_secret(pending_bot_token_path)
    if not pending_bot_token:
        pending_bot_token = str(session.get("pending_bot_token") or "")
    answers = session.get("answers", {})
    bot_username = str(answers.get("bot_username") or "")
    if not pending_bot_token or not sender_id:
        raise ValueError(f"onboarding session {session['session_id']} is missing Discord credentials")

    env_path = hermes_home / ".env"
    _write_env_values(
        env_path,
        {
            "DISCORD_BOT_TOKEN": pending_bot_token,
            "DISCORD_ALLOWED_USERS": sender_id,
        },
    )
    try:
        subprocess.run(["chown", f"{unix_user}:{unix_user}", str(env_path)], check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"failed to chown {env_path}: {exc}") from exc

    update_agent_channels(
        conn,
        cfg,
        agent_id=agent_id,
        channels=["tui-only", "discord"],
    )

    uid = pwd.getpwnam(unix_user).pw_uid
    _wait_for_user_bus(str(uid))
    result = subprocess.run(
        [
            "runuser",
            "-u",
            unix_user,
            "--",
            str(cfg.repo_dir / "bin" / "install-agent-user-services.sh"),
            agent_id,
            str(cfg.repo_dir),
            str(hermes_home),
            json.dumps(["tui-only", "discord"]),
            str(activation_trigger_path(cfg, agent_id)),
        ],
        env={
            **os.environ,
            "ALMANAC_CONFIG_FILE": os.environ.get("ALMANAC_CONFIG_FILE", ""),
            "HOME": str(home),
            "USER": unix_user,
            "LOGNAME": unix_user,
            "HERMES_HOME": str(hermes_home),
            "XDG_RUNTIME_DIR": f"/run/user/{uid}",
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{uid}/bus",
        },
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "install-agent-user-services failed").strip())

    save_onboarding_session(
        conn,
        session_id=str(session["session_id"]),
        state="completed",
        pending_bot_token="",
        pending_bot_token_path="",
        provision_error="",
        completed_at=dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
    )
    delete_onboarding_bot_token_secret(pending_bot_token_path)
    note_refresh_job(
        conn,
        job_name=f"onboarding-{session['session_id']}",
        job_kind="onboarding",
        target_id=agent_id,
        schedule="approval",
        status="ok",
        note=f"discord gateway configured for {bot_username or 'bot'}",
    )
    _queue_operator_message(
        conn,
        cfg,
        f"Onboarding complete for {agent_id} ({unix_user}); Discord bot {bot_username or 'unknown'} is live.",
    )
    _notify_user_via_curator(
        cfg,
        session=session,
        message=(
            f"Everything is ready. Your own bot is `{bot_username or 'your bot'}` now. "
            "Talk to it directly from here on out."
        ),
    )


def _run_pending_onboarding_gateway_configs(conn, cfg: Config) -> None:
    for session in list_pending_onboarding_bot_configurations(conn):
        try:
            answers = session.get("answers", {})
            bot_platform = str(answers.get("bot_platform") or "telegram").strip().lower() or "telegram"
            if bot_platform == "discord":
                _configure_user_discord_gateway(conn, cfg, session)
            else:
                _configure_user_telegram_gateway(conn, cfg, session)
        except Exception as exc:  # noqa: BLE001
            message = str(exc).strip().replace("\n", " ")[:500] or "unknown onboarding gateway error"
            save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="provision-pending",
                provision_error=message,
            )
            note_refresh_job(
                conn,
                job_name=f"onboarding-{session['session_id']}",
                job_kind="onboarding",
                target_id=str(session.get("linked_agent_id") or session["session_id"]),
                schedule="approval",
                status="warn",
                note=message,
            )


def _schedule_failure(
    conn,
    cfg: Config,
    *,
    request_id: str,
    agent_id: str,
    unix_user: str,
    message: str,
    attempts: int,
    log_path: Path,
) -> None:
    terminal = attempts >= cfg.auto_provision_max_attempts
    next_attempt_at = ""
    if not terminal:
        delay = auto_provision_retry_delay_seconds(cfg, attempts)
        next_attempt_at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=delay)).replace(microsecond=0).isoformat()

    mark_auto_provision_finished(
        conn,
        request_id=request_id,
        error=message,
        next_attempt_at=next_attempt_at,
    )
    note_refresh_job(
        conn,
        job_name=f"auto-provision-{request_id}",
        job_kind="auto-provision",
        target_id=agent_id,
        schedule="approval",
        status="fail" if terminal else "warn",
        note=(
            message
            if terminal
            else f"{message}; retry {attempts + 1}/{cfg.auto_provision_max_attempts} at {next_attempt_at}"
        ),
    )
    if terminal:
        _queue_operator_message(
            conn,
            cfg,
            f"Auto-provision failed permanently for {request_id} ({unix_user}) after {attempts} attempt(s): {message}. Log: {log_path}",
        )


def _run_one(conn, cfg: Config, row: dict) -> None:
    request_id = str(row["request_id"])
    unix_user = str(row["unix_user"])
    requester_identity = str(row["requester_identity"])
    source_ip = str(row["source_ip"])
    agent_id = str(row["prior_agent_id"] or make_agent_id(unix_user, "user"))

    existing = conn.execute(
        "SELECT status FROM agents WHERE agent_id = ?",
        (agent_id,),
    ).fetchone()
    if existing is not None and str(existing["status"]) == "active":
        mark_auto_provision_finished(conn, request_id=request_id)
        note_refresh_job(
            conn,
            job_name=f"auto-provision-{request_id}",
            job_kind="auto-provision",
            target_id=agent_id,
            schedule="approval",
            status="ok",
            note="agent already active; marked request provisioned",
        )
        return

    attempts = mark_auto_provision_started(conn, request_id)
    log_path = _log_dir(cfg) / f"{request_id}.log"

    try:
        info = ensure_unix_user_ready(unix_user)
        home = Path(info["home"])
        uid = info["uid"]
        _wait_for_user_bus(uid)

        token_payload = issue_auto_provision_token(conn, request_id)
        channels = _normalize_channels(row)
        model_preset = _model_preset(cfg, row)
        hermes_home = home / ".local" / "share" / "almanac-agent" / "hermes-home"

        env = dict(os.environ)
        env.update(
            {
                "ALMANAC_CONFIG_FILE": os.environ.get("ALMANAC_CONFIG_FILE", ""),
                "ALMANAC_REQUESTER_IDENTITY": requester_identity,
                "ALMANAC_BOOTSTRAP_REQUEST_ID": request_id,
                "ALMANAC_BOOTSTRAP_RAW_TOKEN": token_payload["raw_token"],
                "ALMANAC_BOOTSTRAP_AGENT_ID": agent_id,
                "ALMANAC_BOOTSTRAP_SOURCE_IP": source_ip,
                "ALMANAC_INIT_SKIP_HERMES_SETUP": "1",
                "ALMANAC_INIT_SKIP_GATEWAY_SETUP": "1",
                "ALMANAC_INIT_MODEL_PRESET": model_preset,
                "ALMANAC_INIT_CHANNELS": ",".join(channels),
                "ALMANAC_MCP_URL": f"http://127.0.0.1:{cfg.public_mcp_port}/mcp",
                "ALMANAC_BOOTSTRAP_URL": f"http://127.0.0.1:{cfg.public_mcp_port}/mcp",
                "ALMANAC_QMD_URL": cfg.qmd_url,
                "HOME": str(home),
                "USER": unix_user,
                "LOGNAME": unix_user,
                "XDG_RUNTIME_DIR": f"/run/user/{uid}",
                "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{uid}/bus",
                "HERMES_HOME": str(hermes_home),
            }
        )

        result = subprocess.run(
            ["runuser", "-u", unix_user, "--", str(cfg.repo_dir / "bin" / "init.sh"), "agent"],
            env=env,
            text=True,
            capture_output=True,
        )
        log_path.write_text(
            (result.stdout or "")
            + ("\n--- STDERR ---\n" + result.stderr if result.stderr else ""),
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or f"exit {result.returncode}").strip())
    except Exception as exc:  # noqa: BLE001
        message = str(exc).strip().replace("\n", " ")[:500] or "unknown auto-provision error"
        log_path.write_text(message + "\n", encoding="utf-8")
        _schedule_failure(
            conn,
            cfg,
            request_id=request_id,
            agent_id=agent_id,
            unix_user=unix_user,
            message=message,
            attempts=attempts,
            log_path=log_path,
        )
        return

    mark_auto_provision_finished(conn, request_id=request_id)
    note_refresh_job(
        conn,
        job_name=f"auto-provision-{request_id}",
        job_kind="auto-provision",
        target_id=agent_id,
        schedule="approval",
        status="ok",
        note=f"provisioned unix_user={unix_user} channels={','.join(channels)} model={model_preset}",
    )
    _queue_operator_message(
        conn,
        cfg,
        f"Auto-provisioned {agent_id} for {requester_identity} ({unix_user}).",
    )


def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("Run this as root.")
    cfg = Config.from_env()
    with connect_db(cfg) as conn:
        for row in list_pending_auto_provision_requests(conn, cfg):
            _run_one(conn, cfg, row)
        _run_pending_onboarding_gateway_configs(conn, cfg)


if __name__ == "__main__":
    main()
