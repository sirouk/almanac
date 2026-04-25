#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pwd
import subprocess
import time
from pathlib import Path
from typing import Any

from almanac_agent_access import (
    ensure_access_state,
    ensure_web_runtime,
    publish_tailscale_https,
    save_access_state,
    wait_for_http,
)
from almanac_control import (
    Config,
    activation_trigger_path,
    auto_provision_stale_before_iso,
    auto_provision_retry_delay_seconds,
    build_managed_memory_payload,
    config_env_value,
    connect_db,
    delete_onboarding_bot_token_secret,
    delete_onboarding_secret,
    ensure_unix_user_ready,
    expire_stale_notion_identity_claims,
    finish_operator_action,
    grant_agent_runtime_access,
    get_agent,
    get_agent_identity,
    get_notion_identity_claim,
    get_onboarding_session,
    get_pending_operator_action,
    issue_auto_provision_token,
    json_loads,
    list_onboarding_sessions,
    list_pending_onboarding_bot_configurations,
    list_pending_auto_provision_requests,
    mark_notion_identity_claim,
    make_agent_id,
    mark_auto_provision_finished,
    mark_auto_provision_started,
    NOTION_SLO_P50_SECONDS,
    NOTION_SLO_P99_SECONDS,
    note_refresh_job,
    operator_upgrade_action_extra,
    queue_notification,
    read_onboarding_bot_token_secret,
    read_onboarding_secret,
    save_onboarding_session,
    shell_quote,
    try_verify_notion_identity_claim,
    upsert_agent_identity,
    update_agent_channels,
    write_onboarding_secret,
    mark_operator_action_running,
)
from almanac_onboarding_flow import begin_onboarding_provisioning, send_session_message, session_prompt
from almanac_onboarding_completion import completion_bundle_for_session
from almanac_notion_ssot import retrieve_notion_page
from almanac_nextcloud_access import sync_nextcloud_user_access
from almanac_onboarding_provider_auth import (
    poll_codex_device_authorization,
    provider_browser_auth_prompt,
    provider_secret_name,
    provider_setup_from_dict,
    resolve_provider_setup,
    start_codex_device_authorization,
)


_DEFAULT_USER_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
# Deliberately limited to locale and terminal quality-of-life values. Do not add secrets here.
_SAFE_USER_ENV_KEYS = ("LANG", "LC_ALL", "LC_CTYPE", "TERM", "TMPDIR")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Provision Almanac enrollments and self-serve claim flow.")
    parser.add_argument(
        "--claims-only",
        action="store_true",
        help="Poll pending self-serve Notion claims without running the full enrollment provisioner loop.",
    )
    return parser.parse_args()


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


def _operator_action_log_dir(cfg: Config) -> Path:
    path = cfg.state_dir / "operator-actions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _config_file_for_child_process(cfg: Config) -> str:
    configured = str(os.environ.get("ALMANAC_CONFIG_FILE") or "").strip()
    if configured:
        return configured
    return str(cfg.private_dir / "config" / "almanac.env")


def _tail_text(path: Path, *, max_lines: int = 16) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    if len(lines) <= max_lines:
        text = "\n".join(lines).strip()
    else:
        text = "\n".join(lines[-max_lines:]).strip()
    if len(text) > 1400:
        return text[-1400:]
    return text


def _run_host_upgrade(cfg: Config, *, log_path: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["ALMANAC_CONFIG_FILE"] = _config_file_for_child_process(cfg)
    if cfg.upstream_repo_url:
        env.setdefault("ALMANAC_UPSTREAM_REPO_URL", str(cfg.upstream_repo_url))
    if cfg.upstream_branch:
        env.setdefault("ALMANAC_UPSTREAM_BRANCH", str(cfg.upstream_branch))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as handle:
        return subprocess.run(
            [str(cfg.repo_dir / "deploy.sh"), "upgrade"],
            cwd=str(cfg.repo_dir),
            env=env,
            text=True,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )


def _fail_stale_running_operator_actions(
    conn,
    cfg: Config,
    *,
    action_kind: str,
    label: str,
    stale_seconds: int,
) -> None:
    stale_before = auto_provision_stale_before_iso(stale_seconds)
    rows = conn.execute(
        """
        SELECT *
        FROM operator_actions
        WHERE action_kind = ?
          AND status = 'running'
          AND COALESCE(started_at, created_at, '') < ?
        ORDER BY id ASC
        """,
        (str(action_kind or "").strip(), stale_before),
    ).fetchall()
    for row in rows:
        action_id = int(row["id"])
        requested_by = str(row["requested_by"] or "operator").strip() or "operator"
        log_path = str(row["log_path"] or "").strip()
        note = (
            f"{label} action {action_id} marked failed after being stuck in running state "
            f"for more than {stale_seconds} second(s); the previous worker likely exited before completion"
        )
        finish_operator_action(
            conn,
            action_id=action_id,
            status="failed",
            note=note,
            log_path=log_path,
        )
        _queue_operator_message(
            conn,
            cfg,
            f"{note}.\nRequested by: {requested_by}" + (f"\nLog: {log_path}" if log_path else ""),
        )


def _run_install_agent_ssh_key(
    cfg: Config,
    *,
    unix_user: str,
    pubkey: str,
    log_path: Path,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["ALMANAC_CONFIG_FILE"] = _config_file_for_child_process(cfg)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as handle:
        return subprocess.run(
            [
                str(cfg.repo_dir / "bin" / "install-agent-ssh-key.sh"),
                "--unix-user",
                unix_user,
                "--pubkey",
                pubkey,
            ],
            cwd=str(cfg.repo_dir),
            env=env,
            text=True,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )


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
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _notify_user_via_curator(
    cfg: Config,
    *,
    session: dict,
    message: str,
    telegram_reply_markup: dict[str, Any] | None = None,
    telegram_parse_mode: str = "",
    discord_components: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    try:
        return send_session_message(
            cfg,
            session,
            message,
            telegram_reply_markup=telegram_reply_markup,
            telegram_parse_mode=telegram_parse_mode,
            discord_components=discord_components,
        )
    except Exception:
        return None


def _session_bot_label(session: dict[str, Any]) -> str:
    answers = session.get("answers", {})
    return (
        str(answers.get("bot_display_name") or "")
        or str(answers.get("bot_username") or "")
        or str(answers.get("preferred_bot_name") or "")
        or "your bot"
    ).strip() or "your bot"


def _session_runtime_model(cfg: Config, session: dict[str, Any], provider_runtime: dict[str, Any]) -> tuple[str, str]:
    answers = session.get("answers", {})
    model_preset = str(answers.get("model_preset") or "codex").strip().lower() or "codex"
    provider = str(provider_runtime.get("provider") or "").strip()
    model = str(provider_runtime.get("model") or "").strip()
    if provider and model:
        return model_preset, f"{provider}:{model}"
    return model_preset, str(cfg.model_presets.get(model_preset) or "").strip()


def _run_as_user(
    *,
    unix_user: str,
    home: Path,
    uid: int,
    cmd: list[str],
    hermes_home: Path,
    extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = _user_subprocess_env(
        unix_user=unix_user,
        home=home,
        uid=uid,
        hermes_home=hermes_home,
        extra=extra,
    )
    return subprocess.run(
        ["runuser", "-u", unix_user, "--", *cmd],
        env=env,
        text=True,
        capture_output=True,
    )


def _user_subprocess_env(
    *,
    unix_user: str,
    home: Path,
    uid: int,
    hermes_home: Path,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    env = {
        "PATH": _DEFAULT_USER_PATH,
        "HOME": str(home),
        "USER": unix_user,
        "LOGNAME": unix_user,
        "HERMES_HOME": str(hermes_home),
        "XDG_RUNTIME_DIR": f"/run/user/{uid}",
        "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{uid}/bus",
    }
    for key in _SAFE_USER_ENV_KEYS:
        value = os.environ.get(key)
        if value:
            env[key] = value
    if extra:
        for key, value in extra.items():
            if value is None:
                continue
            env[str(key)] = str(value)
    return env


def _resolve_user_gateway_bin(cfg: Config) -> Path:
    runtime_hermes = cfg.runtime_dir / "hermes-venv" / "bin" / "hermes"
    if runtime_hermes.exists():
        return runtime_hermes
    wrapper = cfg.repo_dir / "bin" / "hermes-shell.sh"
    if wrapper.exists():
        return wrapper
    return runtime_hermes


def _grant_auto_provision_access(cfg: Config, *, unix_user: str, agent_id: str) -> None:
    grant_agent_runtime_access(cfg, unix_user=unix_user, agent_id=agent_id)


def _assert_user_unit_active(
    *,
    unix_user: str,
    home: Path,
    hermes_home: Path,
    uid: int,
    unit_name: str,
) -> None:
    result = _run_as_user(
        unix_user=unix_user,
        home=home,
        uid=uid,
        hermes_home=hermes_home,
        cmd=["systemctl", "--user", "is-active", unit_name],
    )
    if result.returncode != 0 or result.stdout.strip() != "active":
        detail = (result.stderr or result.stdout or "inactive").strip()
        raise RuntimeError(f"{unit_name} is not active for {unix_user}: {detail}")


def _provision_user_access_surfaces(
    conn,
    cfg: Config,
    *,
    agent_id: str,
    unix_user: str,
    home: Path,
    hermes_home: Path,
    uid: int,
    channels: list[str],
    display_name: str = "",
) -> dict[str, Any]:
    ensure_web_runtime(cfg)
    access = ensure_access_state(
        conn,
        cfg,
        agent_id=agent_id,
        unix_user=unix_user,
        hermes_home=hermes_home,
        uid=uid,
    )
    result = _run_as_user(
        unix_user=unix_user,
        home=home,
        uid=uid,
        hermes_home=hermes_home,
        cmd=[
            str(cfg.repo_dir / "bin" / "install-agent-user-services.sh"),
            agent_id,
            str(cfg.repo_dir),
            str(hermes_home),
            json.dumps(channels),
            str(activation_trigger_path(cfg, agent_id)),
            str(_resolve_user_gateway_bin(cfg)),
        ],
        extra={"ALMANAC_AGENT_VAULT_DIR": str(cfg.vault_dir)},
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "install-agent-user-services failed").strip())
    _assert_user_unit_active(
        unix_user=unix_user,
        home=home,
        hermes_home=hermes_home,
        uid=uid,
        unit_name="almanac-user-agent-dashboard.service",
    )
    _assert_user_unit_active(
        unix_user=unix_user,
        home=home,
        hermes_home=hermes_home,
        uid=uid,
        unit_name="almanac-user-agent-dashboard-proxy.service",
    )
    _assert_user_unit_active(
        unix_user=unix_user,
        home=home,
        hermes_home=hermes_home,
        uid=uid,
        unit_name="almanac-user-agent-code.service",
    )
    wait_for_http(
        str(access["dashboard_local_url"]),
        expected_statuses={200},
        username=str(access["username"]),
        password=str(access["password"]),
    )
    wait_for_http(
        str(access["code_local_url"]),
        expected_statuses={200, 302},
    )
    if cfg.agent_enable_tailscale_serve:
        access = publish_tailscale_https(access)
        save_access_state(hermes_home, access, unix_user=unix_user)
    nextcloud_access = sync_nextcloud_user_access(
        cfg,
        username=str(access["username"]),
        password=str(access["password"]),
        display_name=display_name or unix_user,
    )
    if nextcloud_access.get("enabled"):
        access["nextcloud_username"] = str(nextcloud_access.get("username") or access.get("username") or "")
        save_access_state(hermes_home, access, unix_user=unix_user)
    return access


def _operator_completion_message(
    *,
    agent_id: str,
    unix_user: str,
    bot_line: str,
    access: dict[str, Any],
    notion_line: str = "",
) -> str:
    nextcloud_line = ""
    nextcloud_username = str(access.get("nextcloud_username") or access.get("username") or "").strip()
    if nextcloud_username:
        nextcloud_line = f"Nextcloud: shared login username={nextcloud_username}"
    return "\n".join(
        [
            f"Onboarding complete for {agent_id} ({unix_user}); {bot_line}",
            f"Dashboard: {access.get('dashboard_url')} username={access.get('username')}",
            f"Code: {access.get('code_url')}",
            *([nextcloud_line] if nextcloud_line else []),
            *([notion_line] if notion_line else []),
            f"Shared password: {access.get('password')}",
        ]
    )


def _send_completion_bundle(conn, cfg: Config, session: dict[str, Any]) -> None:
    answers = session.get("answers", {}) if isinstance(session.get("answers"), dict) else {}
    if str(answers.get("completion_bundle_sent_at") or "").strip():
        return
    completion_bundle = completion_bundle_for_session(conn, cfg, session)
    delivery = None
    if completion_bundle is not None:
        delivery = _notify_user_via_curator(
            cfg,
            session=session,
            message=str(completion_bundle.get("full_text") or ""),
            telegram_reply_markup=completion_bundle.get("telegram_reply_markup"),
            telegram_parse_mode=str(completion_bundle.get("telegram_parse_mode") or ""),
            discord_components=completion_bundle.get("discord_components"),
        )
    if isinstance(delivery, dict):
        platform = str(session.get("platform") or "").strip().lower()
        message_id = ""
        if platform == "telegram":
            message_id = str(delivery.get("message_id") or "")
        elif platform == "discord":
            message_id = str(delivery.get("id") or "")
        save_onboarding_session(
            conn,
            session_id=str(session["session_id"]),
            answers={
                "completion_delivery": {
                    "platform": platform,
                    "chat_id": str(session.get("chat_id") or delivery.get("channel_id") or ""),
                    "message_id": message_id,
                    "scrubbed_text": str(completion_bundle.get("scrubbed_text") or ""),
                    "followup_text": str(completion_bundle.get("followup_text") or ""),
                    "followup_telegram_parse_mode": str(completion_bundle.get("followup_telegram_parse_mode") or ""),
                    "password_scrubbed": False,
                    "followup_sent": False,
                }
            },
        )
        save_onboarding_session(
            conn,
            session_id=str(session["session_id"]),
            answers={"completion_bundle_sent_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()},
        )


def _finalize_completed_onboarding(conn, cfg: Config, session: dict[str, Any]) -> None:
    updated_session = save_onboarding_session(
        conn,
        session_id=str(session["session_id"]),
        state="completed",
        provision_error="",
        completed_at=dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
    )
    _send_completion_bundle(conn, cfg, updated_session)


def _shared_notion_self_serve_configured() -> bool:
    return bool(
        str(config_env_value("ALMANAC_SSOT_NOTION_TOKEN", "") or "").strip()
        and str(config_env_value("ALMANAC_SSOT_NOTION_SPACE_ID", "") or "").strip()
    )


def _begin_notion_onboarding_phase(conn, cfg: Config, session: dict[str, Any]) -> None:
    updated_session = save_onboarding_session(
        conn,
        session_id=str(session["session_id"]),
        state="awaiting-notion-access",
        pending_bot_token="",
        pending_bot_token_path="",
        provision_error="",
        answers={
            "notion_verification_skipped": False,
            "notion_claim_email": "",
            "notion_claim_id": "",
            "notion_claim_url": "",
            "notion_claim_expires_at": "",
        },
    )
    _notify_user_via_curator(cfg, session=updated_session, message=session_prompt(cfg, updated_session))


def _stage_provider_secret_for_user(
    *,
    session: dict,
    unix_user: str,
    hermes_home: Path,
) -> Path:
    session_id = str(session["session_id"])
    answers = session.get("answers", {})
    pending_provider_secret_path = str(answers.get("pending_provider_secret_path") or "")
    if not pending_provider_secret_path:
        raise ValueError(f"onboarding session {session_id} is missing provider credentials")

    provider_secret = read_onboarding_secret(pending_provider_secret_path)
    if not provider_secret:
        raise ValueError(f"onboarding session {session_id} provider credentials are unreadable")

    passwd = pwd.getpwnam(unix_user)
    secrets_dir = hermes_home / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    os.chown(secrets_dir, passwd.pw_uid, passwd.pw_gid)
    try:
        secrets_dir.chmod(0o700)
    except OSError:
        pass

    staged_path = secrets_dir / f"almanac-onboarding-{session_id}.secret"
    staged_path.write_text(provider_secret, encoding="utf-8")
    os.chown(staged_path, passwd.pw_uid, passwd.pw_gid)
    staged_path.chmod(0o600)
    return staged_path


def _seed_user_provider(cfg: Config, *, session: dict, unix_user: str, home: Path, hermes_home: Path, uid: int) -> dict[str, Any]:
    answers = session.get("answers", {})
    provider_setup = provider_setup_from_dict(answers.get("provider_setup"))
    if provider_setup is None:
        raise ValueError(f"onboarding session {session['session_id']} is missing provider setup")

    agent_id = str(session.get("linked_agent_id") or "")
    if agent_id:
        _grant_auto_provision_access(cfg, unix_user=unix_user, agent_id=agent_id)

    python_bin = cfg.runtime_dir / "hermes-venv" / "bin" / "python3"
    if not python_bin.exists():
        raise RuntimeError(f"missing Hermes runtime at {python_bin}")
    script_path = cfg.repo_dir / "python" / "almanac_headless_hermes_setup.py"
    staged_secret_path = _stage_provider_secret_for_user(
        session=session,
        unix_user=unix_user,
        hermes_home=hermes_home,
    )
    try:
        result = _run_as_user(
            unix_user=unix_user,
            home=home,
            uid=uid,
            hermes_home=hermes_home,
            cmd=[
                str(python_bin),
                str(script_path),
                "--provider-spec-json",
                json.dumps(provider_setup.as_dict(), sort_keys=True),
                "--secret-path",
                str(staged_secret_path),
                "--bot-name",
                _session_bot_label(session),
                "--unix-user",
                unix_user,
                "--user-name",
                str(answers.get("full_name") or session.get("sender_display_name") or "").strip(),
            ],
        )
    finally:
        try:
            staged_secret_path.unlink()
        except FileNotFoundError:
            pass
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "headless hermes setup failed").strip())
    try:
        return json.loads((result.stdout or "{}").strip() or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"headless hermes setup returned invalid json: {result.stdout[:200]}") from exc


def _describe_user_gateway(*, unix_user: str, home: Path, hermes_home: Path, uid: int) -> str:
    result = _run_as_user(
        unix_user=unix_user,
        home=home,
        uid=uid,
        hermes_home=hermes_home,
        cmd=[
            "systemctl",
            "--user",
            "show",
            "almanac-user-agent-gateway.service",
            "--property=LoadState",
            "--property=ActiveState",
            "--property=SubState",
            "--property=Result",
            "--property=ExecMainCode",
            "--property=ExecMainStatus",
            "--no-pager",
        ],
    )
    text = (result.stdout or result.stderr or "").strip().replace("\n", " ")
    return text or "gateway details unavailable"


def _assert_user_gateway_active(*, unix_user: str, home: Path, hermes_home: Path, uid: int) -> None:
    deadline = time.time() + 45
    stable_window_seconds = 10
    status = ""
    active_since: float | None = None
    while time.time() < deadline:
        result = _run_as_user(
            unix_user=unix_user,
            home=home,
            uid=uid,
            hermes_home=hermes_home,
            cmd=["systemctl", "--user", "is-active", "almanac-user-agent-gateway.service"],
        )
        status = (result.stdout or result.stderr or "").strip()
        if result.returncode == 0 and status == "active":
            if active_since is None:
                active_since = time.time()
            if time.time() - active_since >= stable_window_seconds:
                return
        else:
            active_since = None
        time.sleep(1)
    details = _describe_user_gateway(
        unix_user=unix_user,
        home=home,
        hermes_home=hermes_home,
        uid=uid,
    )
    raise RuntimeError(
        "user gateway service did not stay active long enough "
        f"(last status: {status or 'unknown'}; {details})"
    )


def _refresh_user_agent_memory(
    conn,
    cfg: Config,
    *,
    agent_id: str,
    unix_user: str,
    home: Path,
    hermes_home: Path,
    uid: int,
) -> None:
    managed_payload = build_managed_memory_payload(conn, cfg, agent_id=agent_id)
    expected_entry = "[managed:resource-ref]"
    if not str(managed_payload.get("resource-ref") or "").strip():
        raise RuntimeError(f"managed resource map is blank for {agent_id}")

    result = _run_as_user(
        unix_user=unix_user,
        home=home,
        uid=uid,
        hermes_home=hermes_home,
        cmd=["systemctl", "--user", "start", "almanac-user-agent-refresh.service"],
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "managed-memory refresh failed").strip()
        raise RuntimeError(f"user-agent refresh failed for {agent_id}: {detail}")

    stub_path = hermes_home / "memories" / "almanac-managed-stubs.md"
    memory_path = hermes_home / "memories" / "MEMORY.md"
    deadline = time.time() + 30
    while time.time() < deadline:
        stub_text = stub_path.read_text(encoding="utf-8") if stub_path.is_file() else ""
        memory_text = memory_path.read_text(encoding="utf-8") if memory_path.is_file() else ""
        if expected_entry in stub_text and expected_entry in memory_text:
            return
        time.sleep(1)
    raise RuntimeError(
        f"user-agent refresh completed without persisting {expected_entry} for {agent_id}"
    )


def _refresh_user_agent_identity_prompt(
    cfg: Config,
    *,
    unix_user: str,
    home: Path,
    hermes_home: Path,
    uid: int,
    bot_name: str,
    user_name: str,
) -> None:
    python_bin = cfg.runtime_dir / "hermes-venv" / "bin" / "python3"
    if not python_bin.exists():
        raise RuntimeError(f"missing Hermes runtime at {python_bin}")
    script_path = cfg.repo_dir / "python" / "almanac_headless_hermes_setup.py"
    result = _run_as_user(
        unix_user=unix_user,
        home=home,
        uid=uid,
        hermes_home=hermes_home,
        cmd=[
            str(python_bin),
            str(script_path),
            "--identity-only",
            "--bot-name",
            bot_name,
            "--unix-user",
            unix_user,
            "--user-name",
            user_name,
        ],
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "identity refresh failed").strip()
        raise RuntimeError(f"user-agent identity refresh failed for {unix_user}: {detail}")


def _restart_user_agent_gateway_if_enabled(
    *,
    unix_user: str,
    home: Path,
    hermes_home: Path,
    uid: int,
) -> bool:
    enabled_result = _run_as_user(
        unix_user=unix_user,
        home=home,
        uid=uid,
        hermes_home=hermes_home,
        cmd=["systemctl", "--user", "is-enabled", "almanac-user-agent-gateway.service"],
    )
    enabled_status = (enabled_result.stdout or enabled_result.stderr or "").strip().lower()
    if enabled_result.returncode != 0 and enabled_status not in {"enabled", "static", "indirect"}:
        return False

    restart_result = _run_as_user(
        unix_user=unix_user,
        home=home,
        uid=uid,
        hermes_home=hermes_home,
        cmd=["systemctl", "--user", "restart", "almanac-user-agent-gateway.service"],
    )
    if restart_result.returncode != 0:
        detail = (restart_result.stderr or restart_result.stdout or "gateway restart failed").strip()
        raise RuntimeError(f"user-agent gateway restart failed for {unix_user}: {detail}")
    _assert_user_gateway_active(
        unix_user=unix_user,
        home=home,
        hermes_home=hermes_home,
        uid=uid,
    )
    return True


def _run_pending_onboarding_provider_authorizations(conn, cfg: Config) -> None:
    for session in list_onboarding_sessions(conn, redact_secrets=False):
        if str(session.get("state") or "") != "awaiting-provider-browser-auth":
            continue
        provider_setup = provider_setup_from_dict((session.get("answers") or {}).get("provider_setup"))
        if provider_setup is None or provider_setup.provider_id != "openai-codex":
            continue
        browser_auth = (session.get("answers") or {}).get("provider_browser_auth")
        if not isinstance(browser_auth, dict):
            continue
        previous_status = str(browser_auth.get("status") or "")
        try:
            token_payload, updated_auth = poll_codex_device_authorization(browser_auth)
        except Exception as exc:  # noqa: BLE001
            token_payload = None
            updated_auth = dict(browser_auth)
            updated_auth["status"] = "error"
            updated_auth["error_message"] = str(exc).strip() or "unknown OpenAI Codex auth error"

        if token_payload is None:
            new_status = str(updated_auth.get("status") or "")
            if new_status and new_status != previous_status and new_status in {"error", "expired"}:
                updated = save_onboarding_session(
                    conn,
                    session_id=str(session["session_id"]),
                    answers={"provider_browser_auth": updated_auth},
                    provision_error=str(updated_auth.get("error_message") or ""),
                )
                _notify_user_via_curator(
                    cfg,
                    session=updated,
                    message=provider_browser_auth_prompt(provider_setup, updated_auth),
                )
            continue

        try:
            provider_secret_path = write_onboarding_secret(
                cfg,
                str(session["session_id"]),
                provider_secret_name(provider_setup),
                json.dumps(token_payload, sort_keys=True),
            )
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                answers={
                    "provider_browser_auth": updated_auth,
                    "pending_provider_secret_path": provider_secret_path,
                },
                provision_error="",
            )
            updated = begin_onboarding_provisioning(
                conn,
                cfg,
                updated,
                provider_secret_path=provider_secret_path,
            )
            bot_label = str(updated.get("answers", {}).get("bot_username") or updated.get("answers", {}).get("bot_display_name") or "your bot")
            unix_user = str(updated.get("answers", {}).get("unix_user") or updated.get("sender_id") or "")
            if str(updated.get("answers", {}).get("bot_platform") or "") == "discord":
                message = (
                    f"I have your OpenAI Codex authorization. I’m provisioning `{unix_user}` now "
                    f"and wiring `{bot_label}`. I’ll tell you when the lane is ready."
                )
            else:
                message = (
                    f"I have your OpenAI Codex authorization. I’m provisioning `{unix_user}` now "
                    f"and wiring @{bot_label}. I’ll tell you when the lane is ready."
                )
            _notify_user_via_curator(cfg, session=updated, message=message)
        except Exception as exc:  # noqa: BLE001
            save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                answers={"provider_browser_auth": updated_auth},
                provision_error=str(exc).strip() or "failed to continue onboarding after OpenAI approval",
            )


def _migrate_legacy_onboarding_session(conn, cfg: Config, session: dict[str, Any]) -> dict[str, Any] | None:
    if str(session.get("state") or "") != "provision-pending":
        return session

    answers = session.get("answers", {})
    if answers.get("pending_provider_secret_path"):
        return session

    model_preset = str(answers.get("model_preset") or "codex").strip().lower() or "codex"
    provider_setup = resolve_provider_setup(
        cfg,
        model_preset,
        model_id=str(answers.get("model_id") or ""),
        reasoning_effort=str(answers.get("reasoning_effort") or ""),
    )
    update_answers: dict[str, Any] = {"provider_setup": provider_setup.as_dict()}
    new_state = "awaiting-provider-credential"
    if provider_setup.auth_flow == "codex-device":
        new_state = "awaiting-provider-browser-auth"
        update_answers["provider_browser_auth"] = start_codex_device_authorization()

    updated = save_onboarding_session(
        conn,
        session_id=str(session["session_id"]),
        state=new_state,
        answers=update_answers,
        provision_error="",
    )
    _notify_user_via_curator(cfg, session=updated, message=session_prompt(cfg, updated))
    note_refresh_job(
        conn,
        job_name=f"onboarding-{session['session_id']}",
        job_kind="onboarding",
        target_id=str(session.get("linked_agent_id") or session["session_id"]),
        schedule="approval",
        status="warn",
        note="migrated legacy onboarding session into provider authorization flow",
    )
    return None


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
    answers = session.get("answers", {})

    uid = pwd.getpwnam(unix_user).pw_uid
    _wait_for_user_bus(str(uid))
    provider_runtime = _seed_user_provider(
        cfg,
        session=session,
        unix_user=unix_user,
        home=home,
        hermes_home=hermes_home,
        uid=uid,
    )

    env_path = hermes_home / ".env"
    _write_env_values(
        env_path,
        {
            "TELEGRAM_BOT_TOKEN": pending_bot_token,
            "TELEGRAM_ALLOWED_USERS": chat_id,
            "TELEGRAM_HOME_CHANNEL": chat_id,
            "TELEGRAM_REACTIONS": "true",
            "DISCORD_REACTIONS": "true",
        },
    )
    try:
        subprocess.run(["chown", f"{unix_user}:{unix_user}", str(env_path)], check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"failed to chown {env_path}: {exc}") from exc

    model_preset, model_string = _session_runtime_model(cfg, session, provider_runtime)
    update_agent_channels(
        conn,
        cfg,
        agent_id=agent_id,
        channels=["tui-only", "telegram"],
        home_channel={"platform": "telegram", "channel_id": chat_id},
        display_name=_session_bot_label(session),
        model_preset=model_preset,
        model_string=model_string,
    )
    upsert_agent_identity(
        conn,
        agent_id=agent_id,
        unix_user=unix_user,
        human_display_name=str(answers.get("full_name") or session.get("sender_display_name") or unix_user),
        agent_name=_session_bot_label(session),
    )

    access = _provision_user_access_surfaces(
        conn,
        cfg,
        agent_id=agent_id,
        unix_user=unix_user,
        home=home,
        hermes_home=hermes_home,
        uid=uid,
        channels=["tui-only", "telegram"],
        display_name=str(answers.get("full_name") or session.get("sender_display_name") or unix_user),
    )
    _assert_user_gateway_active(unix_user=unix_user, home=home, hermes_home=hermes_home, uid=uid)
    _refresh_user_agent_memory(
        conn,
        cfg,
        agent_id=agent_id,
        unix_user=unix_user,
        home=home,
        hermes_home=hermes_home,
        uid=uid,
    )

    updated_session = save_onboarding_session(
        conn,
        session_id=str(session["session_id"]),
        pending_bot_token="",
        pending_bot_token_path="",
        provision_error="",
    )
    delete_onboarding_bot_token_secret(pending_bot_token_path)
    delete_onboarding_secret(str((session.get("answers") or {}).get("pending_provider_secret_path") or ""))
    note_refresh_job(
        conn,
        job_name=f"onboarding-{session['session_id']}",
        job_kind="onboarding",
        target_id=agent_id,
        schedule="approval",
        status="ok",
        note=(
            f"telegram gateway configured for @{bot_username or 'bot'} "
            f"(provider={provider_runtime.get('provider') or 'unknown'} model={provider_runtime.get('model') or 'unknown'})"
        ),
    )
    if _shared_notion_self_serve_configured():
        _begin_notion_onboarding_phase(conn, cfg, updated_session)
    else:
        _finalize_completed_onboarding(conn, cfg, updated_session)
    _queue_operator_message(
        conn,
        cfg,
        _operator_completion_message(
            agent_id=agent_id,
            unix_user=unix_user,
            bot_line=f"Telegram bot @{bot_username or 'unknown'} is live.",
            access=access,
            notion_line=(
                "Shared Notion verification is now waiting on the user's self-serve claim."
                if _shared_notion_self_serve_configured()
                else "Shared Notion self-serve verification is not configured on this host."
            ),
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

    uid = pwd.getpwnam(unix_user).pw_uid
    _wait_for_user_bus(str(uid))
    provider_runtime = _seed_user_provider(
        cfg,
        session=session,
        unix_user=unix_user,
        home=home,
        hermes_home=hermes_home,
        uid=uid,
    )

    env_path = hermes_home / ".env"
    _write_env_values(
        env_path,
        {
            "DISCORD_BOT_TOKEN": pending_bot_token,
            "DISCORD_ALLOWED_USERS": sender_id,
            "DISCORD_HOME_CHANNEL": str(session.get("chat_id") or ""),
            "DISCORD_HOME_CHANNEL_NAME": "Home",
            "TELEGRAM_REACTIONS": "true",
            "DISCORD_REACTIONS": "true",
        },
    )
    try:
        subprocess.run(["chown", f"{unix_user}:{unix_user}", str(env_path)], check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"failed to chown {env_path}: {exc}") from exc

    model_preset, model_string = _session_runtime_model(cfg, session, provider_runtime)
    update_agent_channels(
        conn,
        cfg,
        agent_id=agent_id,
        channels=["tui-only", "discord"],
        home_channel={
            "platform": "discord",
            "channel_id": str(session.get("chat_id") or ""),
        },
        display_name=_session_bot_label(session),
        model_preset=model_preset,
        model_string=model_string,
    )
    upsert_agent_identity(
        conn,
        agent_id=agent_id,
        unix_user=unix_user,
        human_display_name=str(answers.get("full_name") or session.get("sender_display_name") or unix_user),
        agent_name=_session_bot_label(session),
    )

    access = _provision_user_access_surfaces(
        conn,
        cfg,
        agent_id=agent_id,
        unix_user=unix_user,
        home=home,
        hermes_home=hermes_home,
        uid=uid,
        channels=["tui-only", "discord"],
        display_name=str(answers.get("full_name") or session.get("sender_display_name") or unix_user),
    )
    _assert_user_gateway_active(unix_user=unix_user, home=home, hermes_home=hermes_home, uid=uid)
    _refresh_user_agent_memory(
        conn,
        cfg,
        agent_id=agent_id,
        unix_user=unix_user,
        home=home,
        hermes_home=hermes_home,
        uid=uid,
    )

    updated_session = save_onboarding_session(
        conn,
        session_id=str(session["session_id"]),
        pending_bot_token="",
        pending_bot_token_path="",
        provision_error="",
    )
    delete_onboarding_bot_token_secret(pending_bot_token_path)
    delete_onboarding_secret(str((session.get("answers") or {}).get("pending_provider_secret_path") or ""))
    note_refresh_job(
        conn,
        job_name=f"onboarding-{session['session_id']}",
        job_kind="onboarding",
        target_id=agent_id,
        schedule="approval",
        status="ok",
        note=(
            f"discord gateway configured for {bot_username or 'bot'} "
            f"(provider={provider_runtime.get('provider') or 'unknown'} model={provider_runtime.get('model') or 'unknown'})"
        ),
    )
    if _shared_notion_self_serve_configured():
        _begin_notion_onboarding_phase(conn, cfg, updated_session)
    else:
        _finalize_completed_onboarding(conn, cfg, updated_session)
    _queue_operator_message(
        conn,
        cfg,
        _operator_completion_message(
            agent_id=agent_id,
            unix_user=unix_user,
            bot_line=f"Discord bot {bot_username or 'unknown'} is live.",
            access=access,
            notion_line=(
                "Shared Notion verification is now waiting on the user's self-serve claim."
                if _shared_notion_self_serve_configured()
                else "Shared Notion self-serve verification is not configured on this host."
            ),
        ),
    )


def _run_pending_onboarding_gateway_configs(conn, cfg: Config) -> None:
    for session in list_pending_onboarding_bot_configurations(conn):
        try:
            session = _migrate_legacy_onboarding_session(conn, cfg, session)
            if session is None:
                continue
            answers = session.get("answers", {})
            bot_platform = str(answers.get("bot_platform") or "telegram").strip().lower() or "telegram"
            if bot_platform == "discord":
                _configure_user_discord_gateway(conn, cfg, session)
            else:
                _configure_user_telegram_gateway(conn, cfg, session)
        except Exception as exc:  # noqa: BLE001
            message = str(exc).strip().replace("\n", " ")[:500] or "unknown onboarding gateway error"
            updated = save_onboarding_session(
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
            previous_error = str(session.get("provision_error") or "").strip()
            if message != previous_error:
                _notify_user_via_curator(cfg, session=updated, message=session_prompt(cfg, updated))


def _run_pending_onboarding_notion_verifications(conn, cfg: Config) -> None:
    expired_claims = expire_stale_notion_identity_claims(conn)
    pending_sessions = 0
    verified_sessions = 0
    poll_failures: list[str] = []
    for session in list_onboarding_sessions(conn, redact_secrets=False):
        state = str(session.get("state") or "").strip()
        if state != "awaiting-notion-verification":
            continue
        pending_sessions += 1
        claim_id = str((session.get("answers") or {}).get("notion_claim_id") or "").strip()
        if not claim_id:
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-notion-access",
                answers={
                    "notion_claim_email": "",
                    "notion_claim_id": "",
                    "notion_claim_url": "",
                    "notion_claim_expires_at": "",
                },
                provision_error="",
            )
            _notify_user_via_curator(cfg, session=updated, message=session_prompt(cfg, updated))
            continue
        claim = get_notion_identity_claim(conn, claim_id=claim_id)
        if claim is None:
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-notion-access",
                answers={
                    "notion_claim_email": "",
                    "notion_claim_id": "",
                    "notion_claim_url": "",
                    "notion_claim_expires_at": "",
                },
                provision_error="",
            )
            _notify_user_via_curator(cfg, session=updated, message=session_prompt(cfg, updated))
            continue
        status = str(claim.get("status") or "").strip()
        if status == "expired":
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-notion-access",
                answers={
                    "notion_claim_email": "",
                    "notion_claim_id": "",
                    "notion_claim_url": "",
                    "notion_claim_expires_at": "",
                },
                provision_error="",
            )
            _notify_user_via_curator(
                cfg,
                session=updated,
                message=(
                    "That Notion verification claim expired before I saw the edit.\n\n"
                    + session_prompt(cfg, updated)
                ),
            )
            continue
        if status == "skipped":
            _finalize_completed_onboarding(conn, cfg, session)
            continue
        if status == "pending":
            try:
                page_payload = retrieve_notion_page(page_id=str(claim.get("notion_page_id") or ""), token=str(config_env_value("ALMANAC_SSOT_NOTION_TOKEN", "") or ""), api_version=str(config_env_value("ALMANAC_SSOT_NOTION_API_VERSION", "") or "") or "2026-03-11")
                verified_claim = try_verify_notion_identity_claim(
                    conn,
                    claim=claim,
                    page_payload=page_payload,
                    verification_source="notion-poll",
                )
                if verified_claim is not None:
                    claim = verified_claim
                    status = str(claim.get("status") or "").strip()
            except Exception as exc:
                poll_failures.append(f"{claim_id or session.get('session_id')}: {str(exc).strip() or 'unknown error'}")
                status = "pending"
        if status != "verified":
            continue
        pending_sessions = max(0, pending_sessions - 1)
        verified_sessions += 1
        identity = get_agent_identity(
            conn,
            agent_id=str(session.get("linked_agent_id") or ""),
            unix_user=str((session.get("answers") or {}).get("unix_user") or ""),
        ) or {}
        updated = save_onboarding_session(
            conn,
            session_id=str(session["session_id"]),
            answers={
                "notion_claim_email": str(claim.get("claimed_notion_email") or ""),
                "notion_verified_email": str(identity.get("notion_user_email") or claim.get("verified_notion_email") or ""),
                "notion_verification_skipped": False,
            },
            provision_error="",
        )
        refresh_warning = ""
        try:
            agent_id = str(updated.get("linked_agent_id") or "").strip()
            unix_user = str((updated.get("answers") or {}).get("unix_user") or "").strip()
            if agent_id and unix_user:
                agent_row = get_agent(conn, agent_id)
                if agent_row is not None:
                    try:
                        passwd = pwd.getpwnam(unix_user)
                    except KeyError as exc:
                        raise RuntimeError(f"missing unix user for verified Notion refresh: {unix_user}") from exc
                    _refresh_user_agent_identity_prompt(
                        cfg,
                        unix_user=unix_user,
                        home=Path(passwd.pw_dir),
                        hermes_home=Path(str(agent_row["hermes_home"])),
                        uid=passwd.pw_uid,
                        bot_name=_session_bot_label(updated),
                        user_name=str((updated.get("answers") or {}).get("full_name") or updated.get("sender_display_name") or unix_user),
                    )
                    _refresh_user_agent_memory(
                        conn,
                        cfg,
                        agent_id=agent_id,
                        unix_user=unix_user,
                        home=Path(passwd.pw_dir),
                        hermes_home=Path(str(agent_row["hermes_home"])),
                        uid=passwd.pw_uid,
                    )
                    _restart_user_agent_gateway_if_enabled(
                        unix_user=unix_user,
                        home=Path(passwd.pw_dir),
                        hermes_home=Path(str(agent_row["hermes_home"])),
                        uid=passwd.pw_uid,
                    )
        except Exception as exc:  # noqa: BLE001
            refresh_warning = str(exc).strip() or "unknown user-agent refresh failure after Notion verification"
            queue_notification(
                conn,
                target_kind="operator",
                target_id=cfg.operator_notify_channel_id or cfg.operator_notify_platform or "operator",
                channel_kind=cfg.operator_notify_platform or "tui-only",
                message=f"Notion verification succeeded for {updated.get('linked_agent_id') or updated.get('session_id')}, but user-agent refresh failed: {refresh_warning}",
            )
        _notify_user_via_curator(
            cfg,
            session=updated,
            message=(
                "Verified. I can now write to shared Notion on your behalf through Almanac's brokered rail, "
                "and every supported row write will stamp your Notion account in the Changed By field."
                + (f"\n\nOne note: your agent's local Notion context refresh hit a snag, so it may speak from stale state until the next refresh cycle. The operator has been notified." if refresh_warning else "")
            ),
        )
        _finalize_completed_onboarding(conn, cfg, updated)
    status = "ok"
    if poll_failures:
        status = "fail"
    elif pending_sessions:
        status = "warn"
    note_refresh_job(
        conn,
        job_name="notion-claim-poll",
        job_kind="notion-claim-poll",
        target_id="shared-notion",
        schedule="every 2m",
        status=status,
        note=(
            f"pending_sessions={pending_sessions}; verified_sessions={verified_sessions}; "
            f"expired_claims={expired_claims}; poll_failures={len(poll_failures)}; "
            f"SLO targets p50<{NOTION_SLO_P50_SECONDS}s p99<{NOTION_SLO_P99_SECONDS}s"
        ),
    )


def _run_pending_operator_actions(conn, cfg: Config) -> None:
    _fail_stale_running_operator_actions(
        conn,
        cfg,
        action_kind="upgrade",
        label="Almanac upgrade",
        stale_seconds=6 * 60 * 60,
    )
    action = get_pending_operator_action(conn, action_kind="upgrade")
    if action is None:
        return
    action_id = int(action["id"])
    requested_by = str(action.get("requested_by") or "operator").strip() or "operator"
    requested_target = str(action.get("requested_target") or "").strip()
    log_path = _operator_action_log_dir(cfg) / f"upgrade-{action_id}.log"
    mark_operator_action_running(
        conn,
        action_id=action_id,
        note=f"starting upgrade requested by {requested_by}",
        log_path=str(log_path),
    )
    note_refresh_job(
        conn,
        job_name="operator-upgrade",
        job_kind="operator-action",
        target_id="upgrade",
        schedule="on demand via operator buttons",
        status="warn",
        note=f"running upgrade request {action_id} for {requested_target or 'latest upstream'} by {requested_by}",
    )
    _queue_operator_message(
        conn,
        cfg,
        (
            "Starting Almanac upgrade from the operator action queue.\n"
            f"Requested by: {requested_by}\n"
            f"Requested target: {requested_target or 'latest upstream'}"
        ),
    )
    result = _run_host_upgrade(cfg, log_path=log_path)
    tail = _tail_text(log_path)
    if result.returncode == 0:
        finish_operator_action(
            conn,
            action_id=action_id,
            status="completed",
            note=f"upgrade completed for {requested_target or 'latest upstream'}",
            log_path=str(log_path),
        )
        note_refresh_job(
            conn,
            job_name="operator-upgrade",
            job_kind="operator-action",
            target_id="upgrade",
            schedule="on demand via operator buttons",
            status="ok",
            note=f"completed upgrade request {action_id} for {requested_target or 'latest upstream'}",
        )
        _queue_operator_message(
            conn,
            cfg,
            (
                "Almanac upgrade completed successfully.\n"
                f"Requested by: {requested_by}\n"
                f"Log: {log_path}"
            ),
        )
        return

    finish_operator_action(
        conn,
        action_id=action_id,
        status="failed",
        note=f"upgrade failed with exit code {result.returncode}",
        log_path=str(log_path),
    )
    note_refresh_job(
        conn,
        job_name="operator-upgrade",
        job_kind="operator-action",
        target_id="upgrade",
        schedule="on demand via operator buttons",
        status="fail",
        note=f"failed upgrade request {action_id} with exit code {result.returncode}",
    )
    failure_message = (
        "Almanac upgrade failed.\n"
        f"Requested by: {requested_by}\n"
        f"Exit code: {result.returncode}\n"
        f"Log: {log_path}"
    )
    if tail:
        failure_message += "\nRecent output:\n" + tail
    queue_notification(
        conn,
        target_kind="operator",
        target_id=cfg.operator_notify_channel_id or cfg.operator_notify_platform or "operator",
        channel_kind=cfg.operator_notify_platform or "tui-only",
        message=failure_message,
        extra=operator_upgrade_action_extra(cfg, upstream_commit=requested_target),
    )


def _run_pending_remote_ssh_key_actions(conn, cfg: Config) -> None:
    while True:
        action = get_pending_operator_action(
            conn,
            action_kind="install-agent-ssh-key",
            reclaim_stale_running_seconds=300,
        )
        if action is None:
            return
        action_id = int(action["id"])
        requested_by = str(action.get("requested_by") or "user").strip() or "user"
        try:
            payload = json.loads(str(action.get("requested_target") or "{}"))
            if not isinstance(payload, dict):
                raise ValueError("requested_target is not a JSON object")
            unix_user = str(payload.get("unix_user") or "").strip()
            pubkey = str(payload.get("pubkey") or "").strip()
            tailnet_host = str(payload.get("tailscale_host") or "").strip()
            session_id = str(payload.get("session_id") or "").strip()
            if not unix_user:
                raise ValueError("missing unix_user")
            if not pubkey:
                raise ValueError("missing pubkey")
        except Exception as exc:  # noqa: BLE001
            finish_operator_action(
                conn,
                action_id=action_id,
                status="failed",
                note=f"invalid remote ssh key action payload: {exc}",
            )
            _queue_operator_message(
                conn,
                cfg,
                f"Remote SSH key install request {action_id} failed before execution: {exc}",
            )
            continue

        log_path = _operator_action_log_dir(cfg) / f"install-agent-ssh-key-{action_id}.log"
        mark_operator_action_running(
            conn,
            action_id=action_id,
            note=f"installing remote SSH key for {unix_user} requested by {requested_by}",
            log_path=str(log_path),
        )
        note_refresh_job(
            conn,
            job_name="operator-install-agent-ssh-key",
            job_kind="operator-action",
            target_id=unix_user,
            schedule="on demand via onboarding remote SSH key intake",
            status="warn",
            note=f"installing remote SSH key action {action_id} for {unix_user}",
        )
        result = _run_install_agent_ssh_key(cfg, unix_user=unix_user, pubkey=pubkey, log_path=log_path)
        tail = _tail_text(log_path)
        if result.returncode == 0:
            finish_operator_action(
                conn,
                action_id=action_id,
                status="completed",
                note=f"installed remote SSH key for {unix_user}",
                log_path=str(log_path),
            )
            note_refresh_job(
                conn,
                job_name="operator-install-agent-ssh-key",
                job_kind="operator-action",
                target_id=unix_user,
                schedule="on demand via onboarding remote SSH key intake",
                status="ok",
                note=f"installed remote SSH key action {action_id} for {unix_user}",
            )
            session = get_onboarding_session(conn, session_id, redact_secrets=False) if session_id else None
            if session is not None:
                target = f"{unix_user}@{tailnet_host}" if tailnet_host else unix_user
                send_session_message(
                    cfg,
                    session,
                    (
                        "Remote agent key installed. Run your generated `hermes-almanac-*` wrapper from your own machine "
                        "to start Hermes inside this remote agent lane with its remote config, skills, MCP tools, and files. "
                        f"For debugging only, raw SSH is available over Tailscale as `ssh {target}`."
                    ),
                )
            _queue_operator_message(
                conn,
                cfg,
                f"Installed remote SSH key for {unix_user}. Log: {log_path}",
            )
            continue

        finish_operator_action(
            conn,
            action_id=action_id,
            status="failed",
            note=f"remote SSH key install failed with exit code {result.returncode}",
            log_path=str(log_path),
        )
        note_refresh_job(
            conn,
            job_name="operator-install-agent-ssh-key",
            job_kind="operator-action",
            target_id=unix_user,
            schedule="on demand via onboarding remote SSH key intake",
            status="fail",
            note=f"failed remote SSH key action {action_id} for {unix_user}",
        )
        message = (
            f"Remote SSH key install failed for {unix_user}.\n"
            f"Requested by: {requested_by}\n"
            f"Exit code: {result.returncode}\n"
            f"Log: {log_path}"
        )
        if tail:
            message += "\nRecent output:\n" + tail
        _queue_operator_message(conn, cfg, message)
        session = get_onboarding_session(conn, session_id, redact_secrets=False) if session_id else None
        if session is not None:
            send_session_message(
                cfg,
                session,
                "I could not install that remote SSH key yet. The operator has the failure log and can retry after repair.",
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
    if attempts <= 0:
        return
    log_path = _log_dir(cfg) / f"{request_id}.log"

    try:
        info = ensure_unix_user_ready(unix_user)
        home = Path(info["home"])
        uid = int(info["uid"])
        _grant_auto_provision_access(cfg, unix_user=unix_user, agent_id=agent_id)
        _wait_for_user_bus(uid)

        token_payload = issue_auto_provision_token(conn, request_id)
        channels = _normalize_channels(row)
        model_preset = _model_preset(cfg, row)
        hermes_home = home / ".local" / "share" / "almanac-agent" / "hermes-home"
        activation_path = activation_trigger_path(cfg, agent_id)

        env = _user_subprocess_env(
            unix_user=unix_user,
            home=home,
            uid=uid,
            hermes_home=hermes_home,
            extra={
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
                "ALMANAC_SHARED_REPO_DIR": str(cfg.repo_dir),
                "RUNTIME_DIR": str(cfg.runtime_dir),
                "ALMANAC_ACTIVATION_TRIGGER_PATH": str(activation_path),
            },
        )

        result = subprocess.run(
            ["runuser", "-u", unix_user, "--", str(cfg.repo_dir / "bin" / "init.sh"), "agent"],
            env=env,
            text=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
        )
        log_path.write_text(
            (result.stdout or "")
            + ("\n--- STDERR ---\n" + result.stderr if result.stderr else ""),
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or f"exit {result.returncode}").strip())
        agent = get_agent(conn, agent_id)
        if agent is None:
            raise RuntimeError(f"auto-provision did not register agent {agent_id}")
        hermes_home = Path(str(agent["hermes_home"]))
        access = _provision_user_access_surfaces(
            conn,
            cfg,
            agent_id=agent_id,
            unix_user=unix_user,
            home=home,
            hermes_home=hermes_home,
            uid=uid,
            channels=channels,
            display_name=requester_identity or unix_user,
        )
        _refresh_user_agent_memory(
            conn,
            cfg,
            agent_id=agent_id,
            unix_user=unix_user,
            home=home,
            hermes_home=hermes_home,
            uid=uid,
        )
        upsert_agent_identity(
            conn,
            agent_id=agent_id,
            unix_user=unix_user,
            human_display_name=requester_identity or unix_user,
        )
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
        "\n".join(
            [
                f"Auto-provisioned {agent_id} for {requester_identity} ({unix_user}).",
                f"Dashboard: {access.get('dashboard_url')} username={access.get('username')}",
                f"Code: {access.get('code_url')}",
                *(
                    [f"Nextcloud: shared login username={access.get('nextcloud_username') or access.get('username')}"]
                    if (access.get("nextcloud_username") or access.get("username"))
                    else []
                ),
                f"Shared password: {access.get('password')}",
            ]
        ),
    )


def main() -> None:
    args = parse_args()
    if os.geteuid() != 0:
        raise SystemExit("Run this as root.")
    cfg = Config.from_env()
    with connect_db(cfg) as conn:
        if args.claims_only:
            _run_pending_onboarding_notion_verifications(conn, cfg)
            return
        _run_pending_onboarding_provider_authorizations(conn, cfg)
        for row in list_pending_auto_provision_requests(conn, cfg):
            _run_one(conn, cfg, row)
        _run_pending_onboarding_gateway_configs(conn, cfg)
        _run_pending_onboarding_notion_verifications(conn, cfg)
        _run_pending_remote_ssh_key_actions(conn, cfg)
        _run_pending_operator_actions(conn, cfg)


if __name__ == "__main__":
    main()
