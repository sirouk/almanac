#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import json
import os
import pwd
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from almanac_agent_access import clear_tailscale_https, load_access_state
from almanac_notion_ssot import (
    DEFAULT_NOTION_API_VERSION,
    handshake_notion_space,
    preflight_notion_root_children,
    retrieve_notion_user,
)
from almanac_nextcloud_access import delete_nextcloud_user_access
from almanac_onboarding_flow import notify_session_state, send_session_message
from almanac_control import (
    Config,
    approve_ssot_pending_write,
    approve_request,
    archive_agent_files,
    cancel_auto_provision_request,
    config_env_value,
    consume_notion_reindex_queue,
    connect_db,
    deny_request,
    deny_ssot_pending_write,
    deny_onboarding_session,
    ensure_unix_user_ready,
    ensure_config_file_update,
    generate_raw_token,
    grant_agent_runtime_access,
    get_agent,
    get_notion_identity_override,
    get_onboarding_session,
    get_setting,
    get_ssot_pending_write,
    hash_token,
    list_agents,
    list_agent_identities,
    list_notifications,
    list_onboarding_sessions,
    list_auto_provision_requests,
    list_notion_identity_overrides,
    list_requests,
    list_ssot_access_audit,
    list_ssot_pending_writes,
    list_tokens,
    list_vault_warnings,
    list_vaults,
    make_agent_id,
    mark_agent_deenrolled,
    mark_notification_delivered,
    mark_notification_error,
    note_refresh_job,
    operator_upgrade_action_extra,
    process_pending_notion_events,
    queue_notification,
    queue_vault_content_notifications,
    reinstate_token,
    reload_vault_definitions,
    retry_auto_provision_request,
    revoke_token,
    approve_onboarding_session,
    signal_agent_refresh_from_curator,
    log_ssot_access_audit,
    mark_agent_identity_verified,
    set_agent_identity_claim,
    suspend_agent_identity,
    subscriptions_for_agent,
    sync_vault_repo_mirrors,
    sync_shared_notion_index,
    unsuspend_agent_identity,
    utc_now_iso,
    upsert_notion_identity_override,
    clear_notion_identity_override,
    upsert_setting,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Operator CLI for Almanac control-plane state.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human-readable text.")
    subparsers = parser.add_subparsers(dest="domain", required=True)

    token = subparsers.add_parser("token")
    token_sub = token.add_subparsers(dest="action", required=True)
    token_sub.add_parser("list")
    revoke = token_sub.add_parser("revoke")
    revoke.add_argument("target")
    revoke.add_argument("--surface", default="ctl")
    revoke.add_argument("--actor", default=os.environ.get("USER", "operator"))
    revoke.add_argument("--reason", default="revoked via almanac-ctl")
    reinstate = token_sub.add_parser("reinstate")
    reinstate.add_argument("token_id")
    reinstate.add_argument("--surface", default="ctl")
    reinstate.add_argument("--actor", default=os.environ.get("USER", "operator"))

    request = subparsers.add_parser("request")
    request_sub = request.add_subparsers(dest="action", required=True)
    request_sub.add_parser("list")
    approve = request_sub.add_parser("approve")
    approve.add_argument("request_id")
    approve.add_argument("--surface", default="ctl")
    approve.add_argument("--actor", default=os.environ.get("USER", "operator"))
    deny = request_sub.add_parser("deny")
    deny.add_argument("request_id")
    deny.add_argument("--surface", default="ctl")
    deny.add_argument("--actor", default=os.environ.get("USER", "operator"))

    onboarding = subparsers.add_parser("onboarding")
    onboarding_sub = onboarding.add_subparsers(dest="action", required=True)
    onboarding_sub.add_parser("list")
    onboarding_show = onboarding_sub.add_parser("show")
    onboarding_show.add_argument("session_id")
    onboarding_approve = onboarding_sub.add_parser("approve")
    onboarding_approve.add_argument("session_id")
    onboarding_approve.add_argument("--actor", default=os.environ.get("USER", "operator"))
    onboarding_deny = onboarding_sub.add_parser("deny")
    onboarding_deny.add_argument("session_id")
    onboarding_deny.add_argument("--actor", default=os.environ.get("USER", "operator"))
    onboarding_deny.add_argument("--reason", default="")

    ssot = subparsers.add_parser("ssot")
    ssot_sub = ssot.add_subparsers(dest="action", required=True)
    ssot_list = ssot_sub.add_parser("list")
    ssot_list.add_argument("--status", default="pending")
    ssot_list.add_argument("--agent-id", default="")
    ssot_list.add_argument("--limit", type=int, default=100)
    ssot_show = ssot_sub.add_parser("show")
    ssot_show.add_argument("pending_id")
    ssot_approve = ssot_sub.add_parser("approve")
    ssot_approve.add_argument("pending_id")
    ssot_approve.add_argument("--surface", default="ctl")
    ssot_approve.add_argument("--actor", default=os.environ.get("USER", "operator"))
    ssot_deny = ssot_sub.add_parser("deny")
    ssot_deny.add_argument("pending_id")
    ssot_deny.add_argument("--surface", default="ctl")
    ssot_deny.add_argument("--actor", default=os.environ.get("USER", "operator"))
    ssot_deny.add_argument("--reason", default="")

    agent = subparsers.add_parser("agent")
    agent_sub = agent.add_subparsers(dest="action", required=True)
    agent_sub.add_parser("list")
    show = agent_sub.add_parser("show")
    show.add_argument("target")
    deenroll = agent_sub.add_parser("deenroll")
    deenroll.add_argument("target")
    deenroll.add_argument("--actor", default=os.environ.get("USER", "operator"))

    vault = subparsers.add_parser("vault")
    vault_sub = vault.add_subparsers(dest="action", required=True)
    vault_sub.add_parser("list")
    vault_sub.add_parser("reload-defs")
    notify_paths = vault_sub.add_parser("notify-paths")
    notify_paths.add_argument("paths", nargs="+")
    notify_paths.add_argument("--source", default="vault-watch")
    refresh = vault_sub.add_parser("refresh")
    refresh.add_argument("vault_name")

    channel = subparsers.add_parser("channel")
    channel_sub = channel.add_subparsers(dest="action", required=True)
    reconfigure = channel_sub.add_parser("reconfigure")
    reconfigure.add_argument("scope", choices=["operator"])
    reconfigure.add_argument("--platform")
    reconfigure.add_argument("--channel-id", default="")

    user = subparsers.add_parser("user")
    user_sub = user.add_subparsers(dest="action", required=True)
    prepare = user_sub.add_parser("prepare")
    prepare.add_argument("unix_user")
    sync_access = user_sub.add_parser("sync-access")
    sync_access.add_argument("unix_user")
    sync_access.add_argument("--agent-id", required=True)
    purge_enrollment = user_sub.add_parser("purge-enrollment")
    purge_enrollment.add_argument("unix_user")
    purge_enrollment.add_argument("--actor", default=os.environ.get("USER", "operator"))
    purge_enrollment.add_argument("--remove-unix-user", action="store_true")
    purge_enrollment.add_argument("--remove-archives", action="store_true")
    purge_enrollment.add_argument("--purge-rate-limits", action="store_true")
    purge_enrollment.add_argument("--remove-nextcloud-user", action="store_true")
    purge_enrollment.add_argument("--extra-rate-limit-subject", action="append", default=[])

    upgrade = subparsers.add_parser("upgrade")
    upgrade_sub = upgrade.add_subparsers(dest="action", required=True)
    upgrade_check = upgrade_sub.add_parser("check")
    upgrade_check.add_argument("--notify", action="store_true", help="Queue an operator notification when a new upstream commit is detected.")
    upgrade_check.add_argument("--actor", default=os.environ.get("USER", "operator"), help="Actor label recorded for this check.")

    internal = subparsers.add_parser("internal")
    internal_sub = internal.add_subparsers(dest="action", required=True)
    internal_register = internal_sub.add_parser("register-curator")
    internal_register.add_argument("--unix-user", required=True)
    internal_register.add_argument("--display-name", default="Curator")
    internal_register.add_argument("--hermes-home", required=True)
    internal_register.add_argument("--model-preset", required=True)
    internal_register.add_argument("--model-string", required=True)
    internal_register.add_argument("--channels-json", default='["tui-only"]')
    internal_register.add_argument("--notify-platform", default="tui-only")
    internal_register.add_argument("--notify-channel-id", default="")

    internal_refresh = internal_sub.add_parser("curator-refresh")
    internal_refresh.add_argument("--actor", default="curator-refresh")
    internal_sub.add_parser("vault-repo-sync")

    notion = subparsers.add_parser("notion")
    notion_sub = notion.add_subparsers(dest="action", required=True)
    notion_sub.add_parser("process-pending")
    notion_sub.add_parser("webhook-reset-token")
    notion_handshake = notion_sub.add_parser("handshake")
    notion_handshake.add_argument("--space-url", default="")
    notion_handshake.add_argument("--token", default="")
    notion_handshake.add_argument("--api-version", default="")
    notion_preflight = notion_sub.add_parser("preflight-root")
    notion_preflight.add_argument("--root-page-id", default="")
    notion_preflight.add_argument("--token", default="")
    notion_preflight.add_argument("--api-version", default="")
    notion_index_sync = notion_sub.add_parser("index-sync")
    notion_index_sync.add_argument("--full", action="store_true")
    notion_index_sync.add_argument("--page-id", action="append", default=[])
    notion_index_sync.add_argument("--database-id", action="append", default=[])
    notion_index_sync.add_argument("--actor", default=os.environ.get("USER", "operator"))
    notion_identity_list = notion_sub.add_parser("identity-list")
    notion_identity_list.add_argument("--show-sensitive", dest="show_sensitive", action="store_true")
    notion_identity_list.add_argument("--show-emails", dest="show_sensitive", action="store_true", help=argparse.SUPPRESS)
    notion_override_list = notion_sub.add_parser("override-list")
    notion_override_list.add_argument("--show-sensitive", dest="show_sensitive", action="store_true")
    notion_override_list.add_argument("--show-emails", dest="show_sensitive", action="store_true", help=argparse.SUPPRESS)
    notion_override_set = notion_sub.add_parser("override-set")
    notion_override_set.add_argument("target")
    notion_override_set.add_argument("notion_user_id")
    notion_override_set.add_argument("--email", default="")
    notion_override_set.add_argument("--notes", default="")
    notion_override_set.add_argument("--show-sensitive", dest="show_sensitive", action="store_true")
    notion_override_set.add_argument("--show-emails", dest="show_sensitive", action="store_true", help=argparse.SUPPRESS)
    notion_override_clear = notion_sub.add_parser("override-clear")
    notion_override_clear.add_argument("target")
    notion_claim = notion_sub.add_parser("claim-email")
    notion_claim.add_argument("target")
    notion_claim.add_argument("email")
    notion_claim.add_argument("--actor", default=os.environ.get("USER", "operator"))
    notion_verify = notion_sub.add_parser("verify-identity")
    notion_verify.add_argument("target")
    notion_verify.add_argument("notion_user_id")
    notion_verify.add_argument("--email", default="")
    notion_verify.add_argument("--actor", default=os.environ.get("USER", "operator"))
    notion_suspend = notion_sub.add_parser("suspend")
    notion_suspend.add_argument("target")
    notion_suspend.add_argument("--actor", default=os.environ.get("USER", "operator"))
    notion_suspend.add_argument("--reason", default="identity suspended via almanac-ctl")
    notion_unsuspend = notion_sub.add_parser("unsuspend")
    notion_unsuspend.add_argument("target")
    notion_unsuspend.add_argument("--actor", default=os.environ.get("USER", "operator"))
    notion_unsuspend.add_argument("--reason", default="identity unsuspended via almanac-ctl")
    notion_audit = notion_sub.add_parser("audit")
    notion_audit.add_argument("--agent-id", default="")
    notion_audit.add_argument("--unix-user", default="")
    notion_audit.add_argument("--limit", type=int, default=50)

    notifications = subparsers.add_parser("notifications")
    notifications_sub = notifications.add_subparsers(dest="action", required=True)
    list_cmd = notifications_sub.add_parser("list")
    list_cmd.add_argument("--target-kind")
    list_cmd.add_argument("--target-id")
    list_cmd.add_argument("--undelivered-only", action="store_true")

    for provision_name in ("provision", "provisions"):
        provision = subparsers.add_parser(provision_name)
        provision_sub = provision.add_subparsers(dest="action", required=True)
        provision_sub.add_parser("list")
        cancel = provision_sub.add_parser("cancel")
        cancel.add_argument("request_id")
        cancel.add_argument("--surface", default="ctl")
        cancel.add_argument("--actor", default=os.environ.get("USER", "operator"))
        cancel.add_argument("--reason", default="cancelled via almanac-ctl")
        retry = provision_sub.add_parser("retry")
        retry.add_argument("request_id")
        retry.add_argument("--surface", default="ctl")
        retry.add_argument("--actor", default=os.environ.get("USER", "operator"))

    return parser.parse_args()


def require_root(message: str) -> None:
    if os.geteuid() != 0:
        raise SystemExit(message)


def dump_output(args: argparse.Namespace, payload: object) -> None:
    if args.json:
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return
    if isinstance(payload, str):
        print(payload)
        return
    print(json.dumps(payload, indent=2, sort_keys=True))


def _redacted_email(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    local, sep, domain = normalized.partition("@")
    if not sep:
        return "***"
    lead = local[:1] or "*"
    return f"{lead}***@{domain}"


def _redacted_identifier(value: str) -> str:
    return "[redacted]" if str(value or "").strip() else ""


def _redact_identity_rows(rows: list[dict[str, Any]], *, show_sensitive: bool) -> list[dict[str, Any]]:
    if show_sensitive:
        return rows
    scrubbed: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["claimed_notion_email"] = _redacted_email(item.get("claimed_notion_email", ""))
        item["notion_user_email"] = _redacted_email(item.get("notion_user_email", ""))
        item["notion_user_id"] = _redacted_identifier(item.get("notion_user_id", ""))
        scrubbed.append(item)
    return scrubbed


def _redact_override_rows(rows: list[dict[str, Any]], *, show_sensitive: bool) -> list[dict[str, Any]]:
    if show_sensitive:
        return rows
    scrubbed: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["notion_user_email"] = _redacted_email(item.get("notion_user_email", ""))
        item["notion_user_id"] = _redacted_identifier(item.get("notion_user_id", ""))
        scrubbed.append(item)
    return scrubbed


def _manual_verify_notion_user(user_id: str, *, expected_email: str = "") -> tuple[str, str]:
    token = str(config_env_value("ALMANAC_SSOT_NOTION_TOKEN", "") or "").strip()
    if not token:
        raise SystemExit("shared Notion SSOT integration secret is not configured")
    api_version = (
        str(config_env_value("ALMANAC_SSOT_NOTION_API_VERSION", DEFAULT_NOTION_API_VERSION) or "").strip()
        or DEFAULT_NOTION_API_VERSION
    )
    payload = retrieve_notion_user(
        user_id=user_id,
        token=token,
        api_version=api_version,
    )
    notion_user_id = str(payload.get("id") or "").strip()
    if not notion_user_id:
        raise SystemExit("Notion did not return a stable user id for that account")
    if str(payload.get("type") or "").strip().lower() != "person":
        raise SystemExit("manual verification requires a person account from Notion, not a bot or integration account")
    person = payload.get("person")
    notion_user_email = str(person.get("email") or "").strip().lower() if isinstance(person, dict) else ""
    if not notion_user_email:
        raise SystemExit("Notion did not expose an email for that user account")
    normalized_expected = str(expected_email or "").strip().lower()
    if normalized_expected and notion_user_email != normalized_expected:
        raise SystemExit(
            f"Notion user email mismatch: expected {normalized_expected}, got {notion_user_email}"
        )
    return notion_user_id, notion_user_email


def read_env_file_value(path: Path, key: str) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, raw_value = line.split("=", 1)
        if name.strip() != key:
            continue
        raw_value = raw_value.strip()
        try:
            parsed = shlex.split(raw_value, posix=True)
            return "" if not parsed else parsed[0]
        except ValueError:
            return raw_value.strip("'\"")
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


def _discord_error_suggests_target_retry(error: str, *, target_kind: str = "") -> bool:
    normalized = error.strip().lower()
    if not normalized:
        return False
    if target_kind == "webhook":
        return True
    return any(
        marker in normalized
        for marker in (
            "unknown channel",
            "missing access",
            "missing permissions",
            "channel_id must be numeric",
            "channel_id is empty",
            "discord target is not configured",
            "discord target does not look like a webhook url",
            "discord platform requires either a discord channel id or a discord webhook url",
            "http 404",
        )
    )


def _user_home(unix_user: str) -> Path:
    return Path(pwd.getpwnam(unix_user).pw_dir)


USER_AGENT_UNIT_NAMES = (
    "almanac-user-agent-code.service",
    "almanac-user-agent-dashboard-proxy.service",
    "almanac-user-agent-dashboard.service",
    "almanac-user-agent-gateway.service",
    "almanac-user-agent-activate.path",
    "almanac-user-agent-refresh.timer",
    "almanac-user-agent-refresh.service",
)


def _json_object(raw_value: Any) -> dict[str, Any]:
    if isinstance(raw_value, dict):
        return raw_value
    if not isinstance(raw_value, str) or not raw_value.strip():
        return {}
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _user_home_guess(unix_user: str) -> Path:
    try:
        return _user_home(unix_user)
    except KeyError:
        return Path("/home") / unix_user


def _user_uid(unix_user: str) -> int | None:
    try:
        return pwd.getpwnam(unix_user).pw_uid
    except KeyError:
        return None


def _run_quiet(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def _disable_user_agent_units(unix_user: str) -> None:
    uid = _user_uid(unix_user)
    if uid is None:
        return
    _run_quiet(
        [
            "runuser",
            "-u",
            unix_user,
            "--",
            "env",
            f"XDG_RUNTIME_DIR=/run/user/{uid}",
            f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus",
            "systemctl",
            "--user",
            "disable",
            "--now",
            *USER_AGENT_UNIT_NAMES,
        ]
    )


def _reload_user_systemd(unix_user: str) -> None:
    uid = _user_uid(unix_user)
    if uid is None:
        return
    _run_quiet(
        [
            "runuser",
            "-u",
            unix_user,
            "--",
            "env",
            f"XDG_RUNTIME_DIR=/run/user/{uid}",
            f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus",
            "systemctl",
            "--user",
            "daemon-reload",
        ]
    )


def _candidate_user_homes(unix_user: str, *, agents: list[dict[str, Any]] | None = None) -> list[Path]:
    homes: list[Path] = []
    for agent in agents or []:
        hermes_home_raw = str(agent.get("hermes_home") or "").strip()
        if not hermes_home_raw:
            continue
        hermes_home = Path(hermes_home_raw)
        try:
            candidate = hermes_home.parents[3]
        except IndexError:
            continue
        homes.append(candidate)
    homes.append(_user_home_guess(unix_user))
    deduped: list[Path] = []
    seen: set[str] = set()
    for home in homes:
        key = str(home)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(home)
    return deduped


def _remove_user_agent_unit_files(
    unix_user: str,
    *,
    agents: list[dict[str, Any]] | None = None,
) -> list[str]:
    removed: list[str] = []
    for home in _candidate_user_homes(unix_user, agents=agents):
        unit_dir = home / ".config" / "systemd" / "user"
        for name in USER_AGENT_UNIT_NAMES:
            path = unit_dir / name
            try:
                if not path.exists():
                    continue
                path.unlink()
            except OSError:
                continue
            removed.append(str(path))
    return removed


def _stop_code_container(unix_user: str, container_name: str) -> bool:
    uid = _user_uid(unix_user)
    if uid is None or not container_name or shutil.which("podman") is None:
        return False
    result = _run_quiet(
        ["runuser", "-u", unix_user, "--", "podman", "rm", "-f", container_name]
    )
    return result.returncode == 0


def _remove_path(path: Path) -> bool:
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
            return True
        if path.is_dir():
            shutil.rmtree(path)
            return True
    except FileNotFoundError:
        return False
    return False


def _collect_enrollment_matches(conn, unix_user: str) -> dict[str, Any]:
    derived_agent_id = make_agent_id(unix_user, "user")
    agents = [
        dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM agents
            WHERE role = 'user' AND (unix_user = ? OR agent_id = ?)
            ORDER BY last_enrolled_at DESC
            """,
            (unix_user, derived_agent_id),
        ).fetchall()
    ]
    agent_ids = {derived_agent_id}
    for row in agents:
        agent_id = str(row.get("agent_id") or "").strip()
        if agent_id:
            agent_ids.add(agent_id)

    sessions: list[dict[str, Any]] = []
    session_ids: set[str] = set()
    request_ids: set[str] = set()
    rate_limit_subjects: set[str] = set()
    for row in conn.execute("SELECT * FROM onboarding_sessions ORDER BY updated_at DESC").fetchall():
        payload = dict(row)
        answers = _json_object(payload.get("answers_json"))
        linked_agent_id = str(payload.get("linked_agent_id") or "").strip()
        linked_request_id = str(payload.get("linked_request_id") or "").strip()
        answers_unix_user = str(answers.get("unix_user") or "").strip()
        if answers_unix_user != unix_user and linked_agent_id not in agent_ids:
            continue
        if linked_agent_id:
            agent_ids.add(linked_agent_id)
        if linked_request_id:
            request_ids.add(linked_request_id)
        session_id = str(payload.get("session_id") or "").strip()
        if session_id:
            session_ids.add(session_id)
        platform = str(payload.get("platform") or "").strip()
        sender_id = str(payload.get("sender_id") or "").strip()
        if platform and sender_id:
            rate_limit_subjects.add(f"{platform}:{sender_id}")
        sessions.append(payload)

    request_markers = sorted(request_ids)
    requests_query = (
        """
        SELECT *
        FROM bootstrap_requests
        WHERE unix_user = ?
        """
    )
    request_params: list[str] = [unix_user]
    if agent_ids:
        request_placeholders = ",".join("?" for _ in agent_ids)
        requests_query += f" OR prior_agent_id IN ({request_placeholders})"
        request_params.extend(sorted(agent_ids))
    if request_markers:
        request_placeholders = ",".join("?" for _ in request_markers)
        requests_query += f" OR request_id IN ({request_placeholders})"
        request_params.extend(request_markers)
    requests = [
        dict(row)
        for row in conn.execute(
            requests_query + " ORDER BY requested_at DESC",
            tuple(request_params),
        ).fetchall()
    ]
    for row in requests:
        request_id = str(row.get("request_id") or "").strip()
        if request_id:
            request_ids.add(request_id)
        prior_agent_id = str(row.get("prior_agent_id") or "").strip()
        if prior_agent_id:
            agent_ids.add(prior_agent_id)
        source_ip = str(row.get("source_ip") or "").strip()
        if source_ip:
            rate_limit_subjects.add(source_ip)

    token_ids: set[str] = set()
    tokens: list[dict[str, Any]] = []
    if agent_ids or request_ids:
        clauses: list[str] = []
        params: list[str] = []
        if agent_ids:
            placeholders = ",".join("?" for _ in agent_ids)
            clauses.append(f"agent_id IN ({placeholders})")
            params.extend(sorted(agent_ids))
        if request_ids:
            placeholders = ",".join("?" for _ in request_ids)
            clauses.append(f"activation_request_id IN ({placeholders})")
            params.extend(sorted(request_ids))
        query = "SELECT * FROM bootstrap_tokens WHERE " + " OR ".join(clauses) + " ORDER BY issued_at DESC"
        tokens = [dict(row) for row in conn.execute(query, tuple(params)).fetchall()]
    for row in tokens:
        token_id = str(row.get("token_id") or "").strip()
        if token_id:
            token_ids.add(token_id)

    markers = sorted(agent_ids | request_ids | session_ids | token_ids)
    notification_ids: list[int] = []
    for row in conn.execute("SELECT id, target_id, message, extra_json FROM notification_outbox ORDER BY id").fetchall():
        target_id = str(row["target_id"] or "")
        message = str(row["message"] or "")
        extra_json = str(row["extra_json"] or "")
        if target_id in markers or any(marker and (marker in message or marker in extra_json) for marker in markers):
            notification_ids.append(int(row["id"]))

    refresh_job_names: list[str] = []
    for row in conn.execute("SELECT job_name, target_id, last_note FROM refresh_jobs ORDER BY job_name").fetchall():
        job_name = str(row["job_name"] or "")
        target_id = str(row["target_id"] or "")
        last_note = str(row["last_note"] or "")
        if (
            target_id in markers
            or job_name in {f"{agent_id}-refresh" for agent_id in agent_ids}
            or job_name in {f"onboarding-{session_id}" for session_id in session_ids}
            or job_name in {f"auto-provision-{request_id}" for request_id in request_ids}
            or any(marker and marker in last_note for marker in markers)
        ):
            refresh_job_names.append(job_name)

    return {
        "unix_user": unix_user,
        "agent_ids": sorted(agent_ids),
        "agents": agents,
        "sessions": sessions,
        "session_ids": sorted(session_ids),
        "requests": requests,
        "request_ids": sorted(request_ids),
        "tokens": tokens,
        "token_ids": sorted(token_ids),
        "rate_limit_subjects": sorted(rate_limit_subjects),
        "notification_ids": notification_ids,
        "refresh_job_names": refresh_job_names,
    }

def user_prepare(cfg: Config, unix_user: str) -> dict:
    require_root("almanac-ctl user prepare must run as root.")
    info = ensure_unix_user_ready(unix_user)
    home = Path(info["home"])
    return {
        "unix_user": unix_user,
        "home": str(home),
        "external_steps": [
            f"authorize an SSH key for {unix_user}",
            f"ensure Tailscale SSH or ACL policy permits {unix_user} to access the host",
            "confirm any tailnet identity mapping or host-access policy outside Almanac",
        ],
    }


def user_sync_access(cfg: Config, unix_user: str, agent_id: str) -> dict:
    require_root("almanac-ctl user sync-access must run as root.")
    return grant_agent_runtime_access(cfg, unix_user=unix_user, agent_id=agent_id)


def user_purge_enrollment(
    cfg: Config,
    unix_user: str,
    *,
    actor: str,
    remove_unix_user: bool,
    remove_archives: bool,
    purge_rate_limits: bool,
    extra_rate_limit_subjects: list[str] | None = None,
    remove_nextcloud_user: bool,
) -> dict[str, Any]:
    require_root("almanac-ctl user purge-enrollment must run as root.")
    if unix_user == cfg.almanac_user:
        raise SystemExit(f"refusing to purge the Almanac service user: {unix_user}")

    extra_subjects = sorted({value.strip() for value in (extra_rate_limit_subjects or []) if value.strip()})
    with connect_db(cfg) as conn:
        matches = _collect_enrollment_matches(conn, unix_user)
        agent_ids = list(matches["agent_ids"])
        session_ids = list(matches["session_ids"])
        request_ids = list(matches["request_ids"])
        token_ids = list(matches["token_ids"])

        removed_paths: list[str] = []
        removed_unit_files: list[str] = []
        archives_created: list[str] = []
        code_containers_removed: list[str] = []

        _disable_user_agent_units(unix_user)
        for agent in matches["agents"]:
            if str(agent.get("role") or "") != "user":
                continue
            agent_id = str(agent.get("agent_id") or "").strip()
            hermes_home = Path(str(agent.get("hermes_home") or "").strip()) if str(agent.get("hermes_home") or "").strip() else None
            if hermes_home is not None:
                try:
                    clear_tailscale_https(hermes_home)
                except Exception:
                    pass
                access_state = load_access_state(hermes_home)
                container_name = str(access_state.get("code_container_name") or "").strip()
                if container_name and _stop_code_container(unix_user, container_name):
                    code_containers_removed.append(container_name)
                if not remove_archives and str(agent.get("status") or "") in {"active", "pending"} and hermes_home.exists():
                    archive_path = archive_agent_files(
                        cfg,
                        agent_id=agent_id,
                        unix_user=unix_user,
                        hermes_home=str(hermes_home),
                    )
                    archives_created.append(str(archive_path))
                if _remove_path(hermes_home):
                    removed_paths.append(str(hermes_home))

            manifest_path = Path(str(agent.get("manifest_path") or "").strip()) if str(agent.get("manifest_path") or "").strip() else None
            if manifest_path is not None and _remove_path(manifest_path):
                removed_paths.append(str(manifest_path))

        removed_unit_files.extend(_remove_user_agent_unit_files(unix_user, agents=matches["agents"]))
        _reload_user_systemd(unix_user)

        for agent_id in agent_ids:
            for path in (
                cfg.agents_state_dir / agent_id,
                cfg.state_dir / "activation-triggers" / f"{agent_id}.json",
            ):
                if _remove_path(path):
                    removed_paths.append(str(path))
            if remove_archives:
                archive_root = cfg.archived_agents_dir / agent_id
                if _remove_path(archive_root):
                    removed_paths.append(str(archive_root))

        for session_id in session_ids:
            secret_dir = cfg.state_dir / "onboarding-secrets" / session_id
            if _remove_path(secret_dir):
                removed_paths.append(str(secret_dir))

        for request_id in request_ids:
            log_path = cfg.state_dir / "auto-provision" / f"{request_id}.log"
            if _remove_path(log_path):
                removed_paths.append(str(log_path))

        repo_checkout = cfg.state_dir / "repo-sync" / "checkouts" / f"{unix_user}-almanac"
        if _remove_path(repo_checkout):
            removed_paths.append(str(repo_checkout))
        repo_mirror = cfg.vault_dir / "Repos" / "_mirrors" / f"{unix_user}-almanac"
        if _remove_path(repo_mirror):
            removed_paths.append(str(repo_mirror))

        nextcloud_result: dict[str, Any] | None = None
        if remove_nextcloud_user:
            nextcloud_result = delete_nextcloud_user_access(cfg, username=unix_user)
            for path in (
                cfg.state_dir / "nextcloud" / "data" / unix_user,
                cfg.state_dir / "nextcloud" / "html" / "data" / unix_user,
            ):
                if _remove_path(path):
                    removed_paths.append(str(path))

        delete_counts = {
            "agent_vault_subscriptions": 0,
            "notification_outbox": 0,
            "refresh_jobs": 0,
            "bootstrap_tokens": 0,
            "bootstrap_requests": 0,
            "onboarding_sessions": 0,
            "agents": 0,
            "rate_limits": 0,
        }

        if agent_ids:
            before = conn.total_changes
            placeholders = ",".join("?" for _ in agent_ids)
            conn.execute(
                f"DELETE FROM agent_vault_subscriptions WHERE agent_id IN ({placeholders})",
                tuple(agent_ids),
            )
            delete_counts["agent_vault_subscriptions"] = conn.total_changes - before

        before = conn.total_changes
        notification_ids = list(matches["notification_ids"])
        if notification_ids:
            placeholders = ",".join("?" for _ in notification_ids)
            conn.execute(
                f"DELETE FROM notification_outbox WHERE id IN ({placeholders})",
                tuple(notification_ids),
            )
        delete_counts["notification_outbox"] = conn.total_changes - before

        before = conn.total_changes
        refresh_job_names = list(matches["refresh_job_names"])
        if refresh_job_names:
            placeholders = ",".join("?" for _ in refresh_job_names)
            conn.execute(
                f"DELETE FROM refresh_jobs WHERE job_name IN ({placeholders})",
                tuple(refresh_job_names),
            )
        delete_counts["refresh_jobs"] = conn.total_changes - before

        before = conn.total_changes
        if token_ids:
            placeholders = ",".join("?" for _ in token_ids)
            conn.execute(
                f"DELETE FROM bootstrap_tokens WHERE token_id IN ({placeholders})",
                tuple(token_ids),
            )
        elif agent_ids or request_ids:
            clauses: list[str] = []
            params: list[str] = []
            if agent_ids:
                placeholders = ",".join("?" for _ in agent_ids)
                clauses.append(f"agent_id IN ({placeholders})")
                params.extend(agent_ids)
            if request_ids:
                placeholders = ",".join("?" for _ in request_ids)
                clauses.append(f"activation_request_id IN ({placeholders})")
                params.extend(request_ids)
            conn.execute(
                "DELETE FROM bootstrap_tokens WHERE " + " OR ".join(clauses),
                tuple(params),
            )
        delete_counts["bootstrap_tokens"] = conn.total_changes - before

        before = conn.total_changes
        request_clauses = ["unix_user = ?"]
        request_params: list[str] = [unix_user]
        if request_ids:
            placeholders = ",".join("?" for _ in request_ids)
            request_clauses.append(f"request_id IN ({placeholders})")
            request_params.extend(request_ids)
        if agent_ids:
            placeholders = ",".join("?" for _ in agent_ids)
            request_clauses.append(f"prior_agent_id IN ({placeholders})")
            request_params.extend(agent_ids)
        conn.execute(
            "DELETE FROM bootstrap_requests WHERE " + " OR ".join(request_clauses),
            tuple(request_params),
        )
        delete_counts["bootstrap_requests"] = conn.total_changes - before

        before = conn.total_changes
        session_clauses = []
        session_params: list[str] = []
        if session_ids:
            placeholders = ",".join("?" for _ in session_ids)
            session_clauses.append(f"session_id IN ({placeholders})")
            session_params.extend(session_ids)
        if request_ids:
            placeholders = ",".join("?" for _ in request_ids)
            session_clauses.append(f"linked_request_id IN ({placeholders})")
            session_params.extend(request_ids)
        if agent_ids:
            placeholders = ",".join("?" for _ in agent_ids)
            session_clauses.append(f"linked_agent_id IN ({placeholders})")
            session_params.extend(agent_ids)
        if session_clauses:
            conn.execute(
                "DELETE FROM onboarding_sessions WHERE " + " OR ".join(session_clauses),
                tuple(session_params),
            )
        delete_counts["onboarding_sessions"] = conn.total_changes - before

        before = conn.total_changes
        agent_clauses = ["unix_user = ?"]
        agent_params: list[str] = [unix_user]
        if agent_ids:
            placeholders = ",".join("?" for _ in agent_ids)
            agent_clauses.append(f"agent_id IN ({placeholders})")
            agent_params.extend(agent_ids)
        conn.execute(
            "DELETE FROM agents WHERE " + " OR ".join(agent_clauses),
            tuple(agent_params),
        )
        delete_counts["agents"] = conn.total_changes - before

        rate_subjects = sorted(set(matches["rate_limit_subjects"]) | set(extra_subjects))
        if purge_rate_limits and rate_subjects:
            before = conn.total_changes
            placeholders = ",".join("?" for _ in rate_subjects)
            conn.execute(
                f"DELETE FROM rate_limits WHERE subject IN ({placeholders})",
                tuple(rate_subjects),
            )
            delete_counts["rate_limits"] = conn.total_changes - before

        conn.commit()

    unix_user_removed = False
    if remove_unix_user and _user_uid(unix_user) is not None:
        uid = _user_uid(unix_user)
        if uid is not None:
            _run_quiet(["loginctl", "disable-linger", unix_user])
            _run_quiet(["loginctl", "kill-user", unix_user])
            _run_quiet(["loginctl", "terminate-user", unix_user])
            _run_quiet(["systemctl", "stop", f"user@{uid}.service"])
        _run_quiet(["pkill", "-u", unix_user])
        result = _run_quiet(["userdel", "-r", unix_user])
        if result.returncode != 0:
            _run_quiet(["userdel", unix_user])
            _remove_path(_user_home_guess(unix_user))
        unix_user_removed = _user_uid(unix_user) is None

    return {
        "unix_user": unix_user,
        "actor": actor,
        "removed_unix_user": unix_user_removed,
        "remove_unix_user_requested": remove_unix_user,
        "remove_archives_requested": remove_archives,
        "remove_nextcloud_user_requested": remove_nextcloud_user,
        "purge_rate_limits_requested": purge_rate_limits,
        "agent_ids": agent_ids,
        "session_ids": session_ids,
        "request_ids": request_ids,
        "token_ids": token_ids,
        "rate_limit_subjects": rate_subjects if purge_rate_limits else [],
        "deleted_rows": delete_counts,
        "archives_created": archives_created,
        "removed_unit_files": removed_unit_files,
        "removed_code_containers": code_containers_removed,
        "removed_paths": sorted(dict.fromkeys(removed_paths)),
        "nextcloud": nextcloud_result,
    }


def agent_deenroll(cfg: Config, target: str, actor: str) -> dict:
    require_root("almanac-ctl agent deenroll must run as root.")
    with connect_db(cfg) as conn:
        agent = get_agent(conn, target)
        if agent is None:
            raise SystemExit(f"unknown agent: {target}")
        if agent["role"] != "user":
            raise SystemExit("only user agents can be deenrolled")
        revoked = revoke_token(
            conn,
            target=str(agent["agent_id"]),
            surface="ctl",
            actor=actor,
            reason="agent deenrolled",
        )
        unix_user = str(agent["unix_user"])
        uid = pwd.getpwnam(unix_user).pw_uid
        systemd_env = [
            "runuser",
            "-u",
            unix_user,
            "--",
            "env",
            f"XDG_RUNTIME_DIR=/run/user/{uid}",
            f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus",
            "systemctl",
            "--user",
            "disable",
            "--now",
            "almanac-user-agent-code.service",
            "almanac-user-agent-dashboard-proxy.service",
            "almanac-user-agent-dashboard.service",
            "almanac-user-agent-gateway.service",
            "almanac-user-agent-activate.path",
            "almanac-user-agent-refresh.timer",
            "almanac-user-agent-refresh.service",
        ]
        subprocess.run(systemd_env, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        hermes_home_path = Path(str(agent["hermes_home"]))
        clear_tailscale_https(hermes_home_path)
        archive_path = archive_agent_files(
            cfg,
            agent_id=str(agent["agent_id"]),
            unix_user=unix_user,
            hermes_home=str(agent["hermes_home"]),
        )
        manifest_path = Path(str(agent.get("manifest_path") or ""))
        if manifest_path.exists():
            manifest_path.unlink()

        unit_dir = Path(f"/home/{unix_user}/.config/systemd/user")
        for name in (
            "almanac-user-agent-code.service",
            "almanac-user-agent-dashboard-proxy.service",
            "almanac-user-agent-dashboard.service",
            "almanac-user-agent-gateway.service",
            "almanac-user-agent-activate.path",
            "almanac-user-agent-refresh.service",
            "almanac-user-agent-refresh.timer",
        ):
            path = unit_dir / name
            if path.exists():
                path.unlink()

        if hermes_home_path.exists():
            shutil.rmtree(hermes_home_path)

        subprocess.run(
            [
                "runuser",
                "-u",
                unix_user,
                "--",
                "env",
                f"XDG_RUNTIME_DIR=/run/user/{uid}",
                f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus",
                "systemctl",
                "--user",
                "daemon-reload",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        mark_agent_deenrolled(conn, agent_id=str(agent["agent_id"]), archive_path=str(archive_path))
        queue_notification(
            conn,
            target_kind="operator",
            target_id=cfg.operator_notify_channel_id or cfg.operator_notify_platform or "operator",
            channel_kind=cfg.operator_notify_platform or "tui-only",
            message=f"Deenrolled {agent['display_name']} ({agent['agent_id']}); archived to {archive_path}",
        )
        return {
            "agent_id": agent["agent_id"],
            "revoked_tokens": revoked,
            "archive_path": str(archive_path),
        }


def register_curator(cfg: Config, args: argparse.Namespace) -> dict:
    from almanac_control import register_agent

    with connect_db(cfg) as conn:
        token_id = f"curator-{args.unix_user}"
        raw_token = _ensure_curator_token_file(cfg, token_id)
        conn.execute(
            """
            INSERT OR REPLACE INTO bootstrap_tokens (
              token_id, agent_id, token_hash, requester_identity, source_ip, issued_at, issued_by, revoked_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                token_id,
                "curator",
                hash_token(raw_token),
                args.display_name,
                "127.0.0.1",
                utc_now_iso(),
                "deploy",
            ),
        )
        conn.commit()
        return register_agent(
            conn,
            cfg,
            raw_token=raw_token,
            unix_user=args.unix_user,
            display_name=args.display_name,
            role="curator",
            hermes_home=args.hermes_home,
            model_preset=args.model_preset,
            model_string=args.model_string,
            channels=json.loads(args.channels_json),
            operator_notify_channel={
                "platform": args.notify_platform,
                "channel_id": args.notify_channel_id,
            },
        )


def _ensure_curator_token_file(cfg: Config, token_id: str) -> str:
    """Return the curator raw token, minting and persisting it on first use."""
    token_path = cfg.curator_dir / "secrets" / "operator-token"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    if token_path.is_file():
        existing = token_path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    raw_token = generate_raw_token()
    token_path.write_text(raw_token + "\n", encoding="utf-8")
    try:
        token_path.chmod(0o600)
    except PermissionError:
        pass
    return raw_token


def _read_release_state(cfg: Config) -> dict[str, object]:
    path = cfg.release_state_file
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _short_sha(value: str) -> str:
    return value[:12] if value else ""


def _resolve_deployed_commit(cfg: Config, release_state: dict[str, object]) -> str:
    commit = str(release_state.get("deployed_commit") or "").strip()
    if commit:
        return commit
    if shutil.which("git") is None:
        return ""
    result = subprocess.run(
        ["git", "-C", str(cfg.repo_dir), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _query_upstream_head(repo_url: str, branch: str) -> str:
    if shutil.which("git") is None:
        raise RuntimeError("git is not installed")
    result = subprocess.run(
        ["git", "ls-remote", "--heads", repo_url, branch],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(detail or f"git ls-remote exited {result.returncode}")
    ref_suffix = f"refs/heads/{branch}"
    for raw_line in result.stdout.splitlines():
        parts = raw_line.strip().split()
        if len(parts) >= 2 and parts[1] == ref_suffix:
            return parts[0]
    raise RuntimeError(f"branch {branch!r} was not found at {repo_url}")


def _git_run(repo_dir: Path, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _git_commit_exists(repo_dir: Path, commit: str) -> bool:
    if not commit:
        return False
    result = _git_run(repo_dir, "cat-file", "-e", f"{commit}^{{commit}}")
    return result.returncode == 0


def _git_is_ancestor(repo_dir: Path, older: str, newer: str) -> bool | None:
    if not older or not newer:
        return None
    result = _git_run(repo_dir, "merge-base", "--is-ancestor", older, newer)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None


def _classify_upstream_relation(
    repo_dir: Path,
    repo_url: str,
    branch: str,
    deployed_commit: str,
    upstream_commit: str,
) -> str:
    if not deployed_commit or not upstream_commit:
        return "unknown"
    if deployed_commit == upstream_commit:
        return "equal"
    if shutil.which("git") is None or not (repo_dir / ".git").is_dir():
        return "different"

    fetch_result = _git_run(repo_dir, "fetch", "--quiet", "--depth", "1", repo_url, branch, timeout=60)
    if fetch_result.returncode != 0:
        return "different"

    fetch_head = _git_run(repo_dir, "rev-parse", "FETCH_HEAD")
    fetched_commit = fetch_head.stdout.strip() if fetch_head.returncode == 0 else ""
    compare_target = fetched_commit or upstream_commit

    if not _git_commit_exists(repo_dir, deployed_commit) or not _git_commit_exists(repo_dir, compare_target):
        return "different"

    deployed_is_ancestor = _git_is_ancestor(repo_dir, deployed_commit, compare_target)
    upstream_is_ancestor = _git_is_ancestor(repo_dir, compare_target, deployed_commit)

    if deployed_is_ancestor is True:
        return "behind"
    if upstream_is_ancestor is True:
        return "ahead"
    if deployed_is_ancestor is False and upstream_is_ancestor is False:
        return "diverged"
    return "different"


def upgrade_check(
    conn,
    cfg: Config,
    *,
    actor: str,
    notify: bool = False,
) -> dict[str, object]:
    release_state = _read_release_state(cfg)
    upstream_repo_url = str(
        release_state.get("tracked_upstream_repo_url") or cfg.upstream_repo_url or ""
    ).strip()
    upstream_branch = str(
        release_state.get("tracked_upstream_branch") or cfg.upstream_branch or "main"
    ).strip() or "main"
    deployed_commit = _resolve_deployed_commit(cfg, release_state)

    result: dict[str, object] = {
        "release_state_file": str(cfg.release_state_file),
        "release_state_present": cfg.release_state_file.is_file(),
        "deployed_from": str(release_state.get("deployed_from") or ""),
        "deployed_commit": deployed_commit,
        "deployed_commit_short": _short_sha(deployed_commit),
        "deployed_source_repo": str(release_state.get("deployed_source_repo") or ""),
        "deployed_source_branch": str(release_state.get("deployed_source_branch") or ""),
        "tracked_upstream_repo_url": upstream_repo_url,
        "tracked_upstream_branch": upstream_branch,
        "notification_sent": False,
        "relation": "unknown",
    }

    try:
        upstream_commit = _query_upstream_head(upstream_repo_url, upstream_branch)
    except Exception as exc:  # noqa: BLE001
        note = f"upstream check failed for {upstream_repo_url}#{upstream_branch}: {exc}"
        note_refresh_job(
            conn,
            job_name="almanac-upgrade-check",
            job_kind="upgrade-check",
            target_id="almanac",
            schedule="every 1h",
            status="warn",
            note=note,
        )
        result.update(
            {
                "status": "warn",
                "update_available": False,
                "upstream_commit": "",
                "upstream_commit_short": "",
                "note": note,
                "error": str(exc),
            }
        )
        return result

    relation = _classify_upstream_relation(
        cfg.repo_dir,
        upstream_repo_url,
        upstream_branch,
        deployed_commit,
        upstream_commit,
    )
    update_available = relation in {"behind", "diverged", "different"}
    if not deployed_commit:
        status = "warn"
        note = (
            f"upstream {_short_sha(upstream_commit)} known, but deployed release state is missing or incomplete"
        )
    elif relation == "behind":
        status = "warn"
        note = (
            f"update available: {_short_sha(deployed_commit)} -> {_short_sha(upstream_commit)} "
            f"from {upstream_repo_url}#{upstream_branch}"
        )
    elif relation == "ahead":
        status = "warn"
        note = (
            f"deployed release is ahead of tracked upstream: {_short_sha(deployed_commit)} "
            f"vs {_short_sha(upstream_commit)} from {upstream_repo_url}#{upstream_branch}"
        )
    elif relation == "diverged":
        status = "warn"
        note = (
            f"deployed release diverges from tracked upstream: {_short_sha(deployed_commit)} "
            f"vs {_short_sha(upstream_commit)} from {upstream_repo_url}#{upstream_branch}"
        )
    elif relation == "different":
        status = "warn"
        note = (
            f"deployed release differs from tracked upstream: {_short_sha(deployed_commit)} "
            f"vs {_short_sha(upstream_commit)} from {upstream_repo_url}#{upstream_branch}"
        )
    else:
        status = "ok"
        note = f"up to date at {_short_sha(upstream_commit)} from {upstream_repo_url}#{upstream_branch}"

    result.update(
        {
            "status": status,
            "update_available": update_available,
            "upstream_commit": upstream_commit,
            "upstream_commit_short": _short_sha(upstream_commit),
            "note": note,
            "relation": relation,
        }
    )

    upsert_setting(conn, "almanac_upgrade_last_seen_sha", upstream_commit)
    upsert_setting(conn, "almanac_upgrade_relation", relation)

    if notify and update_available:
        last_notified_sha = get_setting(conn, "almanac_upgrade_last_notified_sha", "")
        if upstream_commit != last_notified_sha:
            operator_extra = operator_upgrade_action_extra(cfg, upstream_commit=upstream_commit)
            operator_tail = (
                "Review with Curator using almanac-upgrade-orchestrator, then run ./deploy.sh upgrade on the host."
            )
            if operator_extra is not None:
                operator_tail += " You can also use the Dismiss / Install buttons below."
            queue_notification(
                conn,
                target_kind="operator",
                target_id=cfg.operator_notify_channel_id or cfg.operator_notify_platform or "operator",
                channel_kind=cfg.operator_notify_platform or "tui-only",
                message=(
                    "Almanac update available: "
                    f"deployed {_short_sha(deployed_commit)} -> upstream {_short_sha(upstream_commit)} "
                    f"on {upstream_repo_url}#{upstream_branch}. "
                    f"{operator_tail}"
                ),
                extra=operator_extra,
            )
            for row in conn.execute(
                "SELECT agent_id FROM agents WHERE role = 'user' AND status = 'active' ORDER BY agent_id"
            ).fetchall():
                agent_id = str(row["agent_id"] or "")
                if not agent_id:
                    continue
                queue_notification(
                    conn,
                    target_kind="user-agent",
                    target_id=agent_id,
                    channel_kind="almanac-upgrade",
                    message=(
                        "Curator reports an Almanac host update is available: "
                        f"{_short_sha(deployed_commit)} -> {_short_sha(upstream_commit)}. "
                        "Let your user know shared infrastructure will be refreshed once the operator runs ./deploy.sh upgrade."
                    ),
                    extra={
                        "deployed_commit": deployed_commit,
                        "upstream_commit": upstream_commit,
                        "tracked_upstream_repo_url": upstream_repo_url,
                        "tracked_upstream_branch": upstream_branch,
                    },
                )
                signal_agent_refresh_from_curator(
                    conn,
                    cfg,
                    agent_id=agent_id,
                    note="curator upgrade notification ready",
                )
            upsert_setting(conn, "almanac_upgrade_last_notified_sha", upstream_commit)
            result["notification_sent"] = True

    note_refresh_job(
        conn,
        job_name="almanac-upgrade-check",
        job_kind="upgrade-check",
        target_id="almanac",
        schedule="every 1h",
        status=status,
        note=note,
    )
    return result


def main() -> None:
    args = parse_args()
    cfg = Config.from_env()

    if args.domain == "user" and args.action == "prepare":
        dump_output(args, user_prepare(cfg, args.unix_user))
        return
    if args.domain == "user" and args.action == "sync-access":
        dump_output(args, user_sync_access(cfg, args.unix_user, args.agent_id))
        return
    if args.domain == "user" and args.action == "purge-enrollment":
        dump_output(
            args,
            user_purge_enrollment(
                cfg,
                args.unix_user,
                actor=args.actor,
                remove_unix_user=args.remove_unix_user,
                remove_archives=args.remove_archives,
                purge_rate_limits=args.purge_rate_limits,
                extra_rate_limit_subjects=args.extra_rate_limit_subject,
                remove_nextcloud_user=args.remove_nextcloud_user,
            ),
        )
        return

    if args.domain == "agent" and args.action == "deenroll":
        dump_output(args, agent_deenroll(cfg, args.target, args.actor))
        return

    with connect_db(cfg) as conn:
        if args.domain == "token" and args.action == "list":
            dump_output(args, list_tokens(conn))
            return
        if args.domain == "token" and args.action == "revoke":
            revoked = revoke_token(
                conn,
                target=args.target,
                surface=args.surface,
                actor=args.actor,
                reason=args.reason,
                cfg=cfg,
            )
            dump_output(args, {"revoked": revoked, "target": args.target})
            return
        if args.domain == "token" and args.action == "reinstate":
            dump_output(
                args,
                reinstate_token(
                    conn,
                    token_id=args.token_id,
                    actor=args.actor,
                    surface=args.surface,
                    cfg=cfg,
                ),
            )
            return

        if args.domain == "request" and args.action == "list":
            dump_output(args, list_requests(conn))
            return
        if args.domain == "request" and args.action == "approve":
            dump_output(
                args,
                approve_request(
                    conn, request_id=args.request_id, surface=args.surface, actor=args.actor, cfg=cfg
                ),
            )
            return
        if args.domain == "request" and args.action == "deny":
            dump_output(
                args,
                deny_request(
                    conn, request_id=args.request_id, surface=args.surface, actor=args.actor, cfg=cfg
                ),
            )
            return

        if args.domain == "onboarding" and args.action == "list":
            dump_output(args, list_onboarding_sessions(conn))
            return
        if args.domain == "onboarding" and args.action == "show":
            session = get_onboarding_session(conn, args.session_id)
            if session is None:
                raise SystemExit(f"unknown onboarding session: {args.session_id}")
            dump_output(args, session)
            return
        if args.domain == "onboarding" and args.action == "approve":
            session = approve_onboarding_session(
                conn,
                session_id=args.session_id,
                actor=args.actor,
            )
            notify_session_state(cfg, session)
            dump_output(args, session)
            return
        if args.domain == "onboarding" and args.action == "deny":
            session = deny_onboarding_session(
                conn,
                session_id=args.session_id,
                actor=args.actor,
                reason=args.reason,
            )
            send_session_message(cfg, session, f"The operator declined this onboarding request: {session.get('denial_reason') or 'denied'}")
            dump_output(args, session)
            return

        if args.domain == "ssot" and args.action == "list":
            dump_output(
                args,
                list_ssot_pending_writes(
                    conn,
                    status=args.status,
                    agent_id=args.agent_id,
                    limit=args.limit,
                ),
            )
            return
        if args.domain == "ssot" and args.action == "show":
            pending = get_ssot_pending_write(conn, args.pending_id)
            if pending is None:
                raise SystemExit(f"unknown pending SSOT write: {args.pending_id}")
            dump_output(args, pending)
            return
        if args.domain == "ssot" and args.action == "approve":
            dump_output(
                args,
                approve_ssot_pending_write(
                    conn,
                    cfg,
                    pending_id=args.pending_id,
                    surface=args.surface,
                    actor=args.actor,
                ),
            )
            return
        if args.domain == "ssot" and args.action == "deny":
            dump_output(
                args,
                deny_ssot_pending_write(
                    conn,
                    cfg,
                    pending_id=args.pending_id,
                    surface=args.surface,
                    actor=args.actor,
                    reason=args.reason,
                ),
            )
            return

        if args.domain == "agent" and args.action == "list":
            dump_output(args, list_agents(conn))
            return
        if args.domain == "agent" and args.action == "show":
            agent = get_agent(conn, args.target)
            if agent is None:
                raise SystemExit(f"unknown agent: {args.target}")
            agent["subscriptions"] = subscriptions_for_agent(conn, str(agent["agent_id"]))
            dump_output(args, agent)
            return

        if args.domain == "vault" and args.action == "list":
            dump_output(args, {"vaults": list_vaults(conn), "warnings": list_vault_warnings(conn)})
            return
        if args.domain == "vault" and args.action == "reload-defs":
            dump_output(args, reload_vault_definitions(conn, cfg))
            return
        if args.domain == "vault" and args.action == "notify-paths":
            dump_output(
                args,
                queue_vault_content_notifications(
                    conn,
                    cfg,
                    changed_paths=args.paths,
                    source=args.source,
                ),
            )
            return
        if args.domain == "vault" and args.action == "refresh":
            scan = reload_vault_definitions(conn, cfg)
            match = next(
                (d for d in scan.get("active_vaults", []) if d["vault_name"] == args.vault_name),
                None,
            )
            invalid = next(
                (
                    d
                    for d in scan.get("definitions", [])
                    if d["vault_name"] == args.vault_name and not d.get("is_valid")
                ),
                None,
            )
            status = "ok" if match else ("warn" if invalid else "missing")
            note = (
                f"manual refresh; vault {'active' if match else 'missing'}"
                + (f"; warning: {invalid['warning']}" if invalid else "")
            )
            note_refresh_job(
                conn,
                job_name=f"vault-refresh-{args.vault_name}",
                job_kind="vault-refresh",
                target_id=args.vault_name,
                schedule="manual",
                status=status,
                note=note,
            )
            queue_notification(
                conn,
                target_kind="curator",
                target_id="curator",
                channel_kind="brief-fanout",
                message=f"Vault refresh: {args.vault_name} status={status}",
            )
            dump_output(
                args,
                {
                    "vault_name": args.vault_name,
                    "status": status,
                    "active": bool(match),
                    "warning": invalid["warning"] if invalid else None,
                },
            )
            return

        if args.domain == "notifications" and args.action == "list":
            dump_output(
                args,
                list_notifications(
                    conn,
                    target_kind=args.target_kind,
                    target_id=args.target_id,
                    undelivered_only=args.undelivered_only,
                ),
            )
            return

        if args.domain in {"provision", "provisions"} and args.action == "list":
            dump_output(args, list_auto_provision_requests(conn, cfg))
            return
        if args.domain in {"provision", "provisions"} and args.action == "cancel":
            dump_output(
                args,
                cancel_auto_provision_request(
                    conn,
                    request_id=args.request_id,
                    surface=args.surface,
                    actor=args.actor,
                    reason=args.reason,
                    cfg=cfg,
                ),
            )
            return
        if args.domain in {"provision", "provisions"} and args.action == "retry":
            dump_output(
                args,
                retry_auto_provision_request(
                    conn,
                    request_id=args.request_id,
                    surface=args.surface,
                    actor=args.actor,
                    cfg=cfg,
                ),
            )
            return

        if args.domain == "upgrade" and args.action == "check":
            dump_output(args, upgrade_check(conn, cfg, actor=args.actor, notify=args.notify))
            return

        if args.domain == "channel" and args.action == "reconfigure":
            if args.scope != "operator":
                raise SystemExit("only operator channel reconfiguration is supported")
            platform = args.platform or input("Operator notification platform [discord|telegram|tui-only]: ").strip() or "tui-only"
            channel_id = args.channel_id or ""
            telegram_bot_token = ""
            discord_bot_token = ""
            discord_target_kind = ""
            discord_candidates: list[tuple[str, str]] = []
            if platform != "tui-only" and not channel_id:
                if platform == "discord":
                    channel_id = input("Discord channel ID or webhook URL: ").strip()
                else:
                    channel_id = input("Channel ID / chat ID: ").strip()

            # Shape validation before we persist anything.
            if platform == "discord":
                discord_target_kind = _discord_target_kind(channel_id)
                if not discord_target_kind:
                    raise SystemExit(
                        "discord platform requires either a Discord channel ID or a Discord webhook URL "
                        "in --channel-id"
                    )
                if discord_target_kind == "channel":
                    discord_bot_token = config_env_value("DISCORD_BOT_TOKEN", "").strip()
                    hermes_discord_bot_token = read_env_file_value(cfg.curator_hermes_home / ".env", "DISCORD_BOT_TOKEN").strip()
                    if discord_bot_token:
                        discord_candidates.append(("almanac.env", discord_bot_token))
                    if hermes_discord_bot_token and hermes_discord_bot_token != discord_bot_token:
                        discord_candidates.append(("curator Hermes .env", hermes_discord_bot_token))
                    if not discord_candidates and sys.stdin.isatty():
                        try:
                            discord_bot_token = getpass.getpass("Discord bot token: ").strip()
                        except (EOFError, KeyboardInterrupt):
                            discord_bot_token = ""
                        if discord_bot_token:
                            discord_candidates.append(("prompt", discord_bot_token))
                    if not discord_candidates:
                        raise SystemExit(
                            "discord channel delivery requires DISCORD_BOT_TOKEN; rerun interactively to enter it "
                            "or set it in almanac.env before running this command"
                        )
            elif platform == "telegram":
                if not channel_id:
                    raise SystemExit("telegram platform requires a chat_id in --channel-id")
                telegram_bot_token = config_env_value("TELEGRAM_BOT_TOKEN", "").strip()
                hermes_telegram_bot_token = read_env_file_value(cfg.curator_hermes_home / ".env", "TELEGRAM_BOT_TOKEN").strip()
                telegram_candidates: list[tuple[str, str]] = []
                if telegram_bot_token:
                    telegram_candidates.append(("almanac.env", telegram_bot_token))
                if hermes_telegram_bot_token and hermes_telegram_bot_token != telegram_bot_token:
                    telegram_candidates.append(("curator Hermes .env", hermes_telegram_bot_token))
                if not telegram_candidates and sys.stdin.isatty():
                    try:
                        telegram_bot_token = getpass.getpass("Telegram bot token: ").strip()
                    except (EOFError, KeyboardInterrupt):
                        telegram_bot_token = ""
                    if telegram_bot_token:
                        telegram_candidates.append(("prompt", telegram_bot_token))
                if not telegram_candidates:
                    raise SystemExit(
                        "telegram platform requires TELEGRAM_BOT_TOKEN; rerun interactively to enter it "
                        "or set it in almanac.env before running this command"
                    )
            elif platform != "tui-only":
                raise SystemExit(f"unsupported operator notify platform: {platform}")

            # Synchronous test ping BEFORE persisting config.
            if platform != "tui-only":
                from almanac_notification_delivery import (
                    deliver_discord,
                    deliver_discord_channel,
                    deliver_telegram,
                )

                test_msg = f"almanac-ctl channel reconfigure operator test ping at {utc_now_iso()}"
                if platform == "discord":
                    if discord_target_kind == "webhook":
                        err = deliver_discord(test_msg, webhook_url=channel_id)
                    else:
                        err = ""
                        for source_name, candidate_token in discord_candidates:
                            err = deliver_discord_channel(
                                test_msg,
                                bot_token=candidate_token,
                                channel_id=channel_id,
                            ) or ""
                            if not err:
                                discord_bot_token = candidate_token
                                break
                    if err and sys.stdin.isatty():
                        while True:
                            if _discord_error_suggests_target_retry(err, target_kind=discord_target_kind):
                                print(
                                    f"Discord test ping failed for the current channel target ({err}).",
                                    file=sys.stderr,
                                )
                                try:
                                    candidate_target = input(
                                        "Discord channel ID or webhook URL (leave blank to abort): "
                                    ).strip()
                                except (EOFError, KeyboardInterrupt):
                                    candidate_target = ""
                                if not candidate_target:
                                    break
                                channel_id = candidate_target
                                discord_target_kind = _discord_target_kind(channel_id)
                                if not discord_target_kind:
                                    err = (
                                        "discord platform requires either a Discord channel ID or "
                                        "a Discord webhook URL in --channel-id"
                                    )
                                    continue
                                if discord_target_kind == "webhook":
                                    err = deliver_discord(test_msg, webhook_url=channel_id) or ""
                                    if not err:
                                        break
                                    continue
                                if not discord_candidates:
                                    try:
                                        candidate_token = getpass.getpass("Discord bot token: ").strip()
                                    except (EOFError, KeyboardInterrupt):
                                        candidate_token = ""
                                    if not candidate_token:
                                        err = (
                                            "discord channel delivery requires DISCORD_BOT_TOKEN; "
                                            "not persisting configuration"
                                        )
                                        break
                                    discord_candidates = [("prompt", candidate_token)]
                                err = ""
                                for source_name, candidate_token in discord_candidates:
                                    err = deliver_discord_channel(
                                        test_msg,
                                        bot_token=candidate_token,
                                        channel_id=channel_id,
                                    ) or ""
                                    if not err:
                                        discord_bot_token = candidate_token
                                        break
                                if not err:
                                    break
                                continue

                            print(
                                f"Discord test ping failed using the saved token ({err}).",
                                file=sys.stderr,
                            )
                            try:
                                candidate_token = getpass.getpass(
                                    "Discord bot token (leave blank to abort): "
                                ).strip()
                            except (EOFError, KeyboardInterrupt):
                                candidate_token = ""
                            if not candidate_token:
                                break
                            err = deliver_discord_channel(
                                test_msg,
                                bot_token=candidate_token,
                                channel_id=channel_id,
                            ) or ""
                            if not err:
                                discord_bot_token = candidate_token
                                discord_candidates = [("prompt", candidate_token)]
                                break
                else:
                    err = ""
                    for source_name, candidate_token in telegram_candidates:
                        err = deliver_telegram(
                            test_msg,
                            bot_token=candidate_token,
                            chat_id=channel_id,
                        ) or ""
                        if not err:
                            telegram_bot_token = candidate_token
                            break
                    if err and sys.stdin.isatty():
                        while True:
                            print(
                                f"Telegram test ping failed using the saved token ({err}).",
                                file=sys.stderr,
                            )
                            try:
                                candidate_token = getpass.getpass(
                                    "Telegram bot token (leave blank to abort): "
                                ).strip()
                            except (EOFError, KeyboardInterrupt):
                                candidate_token = ""
                            if not candidate_token:
                                break
                            err = deliver_telegram(
                                test_msg,
                                bot_token=candidate_token,
                                chat_id=channel_id,
                            ) or ""
                            if not err:
                                telegram_bot_token = candidate_token
                                break
                if err:
                    raise SystemExit(
                        f"channel test ping failed ({err}); not persisting configuration. "
                        "Fix the credentials/URL and retry."
                    )

            config_path = cfg.private_dir / "config" / "almanac.env"
            config_updates = {
                "OPERATOR_NOTIFY_CHANNEL_PLATFORM": platform,
                "OPERATOR_NOTIFY_CHANNEL_ID": channel_id,
            }
            if platform == "discord" and discord_target_kind == "channel" and discord_bot_token:
                config_updates["DISCORD_BOT_TOKEN"] = discord_bot_token
            if platform == "telegram" and telegram_bot_token:
                config_updates["TELEGRAM_BOT_TOKEN"] = telegram_bot_token
            ensure_config_file_update(config_path, config_updates)
            upsert_setting(conn, "operator_notify_platform", platform)
            upsert_setting(conn, "operator_notify_channel_id", channel_id)
            # Enqueue a delivered confirmation row so the audit trail shows the
            # test ping happened (and when).
            notif_id = queue_notification(
                conn,
                target_kind="operator",
                target_id=channel_id or platform,
                channel_kind=platform,
                message=(
                    f"Operator notification channel configured for {platform}; "
                    "test ping succeeded." if platform != "tui-only"
                    else "Operator notification channel configured for tui-only (no external send)."
                ),
            )
            mark_notification_delivered(conn, notif_id)
            dump_output(args, {
                "platform": platform,
                "channel_id": channel_id,
                "config_path": str(config_path),
                "test_ping": "ok" if platform != "tui-only" else "skipped (tui-only)",
            })
            return

        if args.domain == "internal" and args.action == "register-curator":
            dump_output(args, register_curator(cfg, args))
            return
        if args.domain == "internal" and args.action == "curator-refresh":
            from almanac_control import consume_curator_brief_fanout

            repo_sync = sync_vault_repo_mirrors(conn, cfg)
            scan = reload_vault_definitions(conn, cfg)
            notion_index = consume_notion_reindex_queue(conn, cfg, actor=args.actor)
            fanout = consume_curator_brief_fanout(conn, cfg)
            upgrade = upgrade_check(conn, cfg, actor=args.actor, notify=True)
            note_refresh_job(
                conn,
                job_name="curator-refresh",
                job_kind="curator-refresh",
                target_id="curator",
                schedule="every 1h",
                status="ok" if not repo_sync.get("repos_failed") else "warn",
                note=(
                    f"repo sync changed {len(repo_sync.get('changed_paths', []))} path(s); "
                    f"notion index status: {notion_index.get('status', 'unknown')}; "
                    f"vault warnings: {len(scan['warnings'])}; "
                    f"published {len(fanout.get('published_agents', []))} central stub(s)"
                ),
            )
            dump_output(args, {"repo_sync": repo_sync, "scan": scan, "notion_index": notion_index, "fanout": fanout, "upgrade": upgrade})
            return
        if args.domain == "internal" and args.action == "vault-repo-sync":
            dump_output(args, sync_vault_repo_mirrors(conn, cfg))
            return

        if args.domain == "notion" and args.action == "process-pending":
            dump_output(args, process_pending_notion_events(conn))
            return
        if args.domain == "notion" and args.action == "webhook-reset-token":
            previously_set = bool(str(get_setting(conn, "notion_webhook_verification_token", "") or "").strip())
            upsert_setting(conn, "notion_webhook_verification_token", "")
            conn.commit()
            dump_output(args, {
                "ok": True,
                "previously_set": previously_set,
                "note": "stored verification token cleared; next handshake POST from Notion will install a fresh secret",
            })
            return
        if args.domain == "notion" and args.action == "handshake":
            try:
                payload = handshake_notion_space(
                    space_url=args.space_url or config_env_value("ALMANAC_SSOT_NOTION_SPACE_URL", "").strip(),
                    token=args.token or config_env_value("ALMANAC_SSOT_NOTION_TOKEN", "").strip(),
                    api_version=(
                        args.api_version
                        or config_env_value("ALMANAC_SSOT_NOTION_API_VERSION", DEFAULT_NOTION_API_VERSION).strip()
                        or DEFAULT_NOTION_API_VERSION
                    ),
                )
            except RuntimeError as exc:
                raise SystemExit(str(exc)) from exc
            dump_output(args, payload)
            return
        if args.domain == "notion" and args.action == "preflight-root":
            try:
                payload = preflight_notion_root_children(
                    root_page_id=(
                        args.root_page_id
                        or config_env_value("ALMANAC_SSOT_NOTION_ROOT_PAGE_ID", "").strip()
                        or config_env_value("ALMANAC_SSOT_NOTION_SPACE_ID", "").strip()
                    ),
                    token=args.token or config_env_value("ALMANAC_SSOT_NOTION_TOKEN", "").strip(),
                    api_version=(
                        args.api_version
                        or config_env_value("ALMANAC_SSOT_NOTION_API_VERSION", DEFAULT_NOTION_API_VERSION).strip()
                        or DEFAULT_NOTION_API_VERSION
                    ),
                )
            except RuntimeError as exc:
                raise SystemExit(str(exc)) from exc
            dump_output(args, payload)
            return
        if args.domain == "notion" and args.action == "index-sync":
            dump_output(
                args,
                sync_shared_notion_index(
                    conn,
                    cfg,
                    full=bool(args.full),
                    page_ids=list(args.page_id or []),
                    database_ids=list(args.database_id or []),
                    actor=args.actor,
                ),
            )
            return
        if args.domain == "notion" and args.action == "identity-list":
            dump_output(
                args,
                {
                    "identities": _redact_identity_rows(
                        list_agent_identities(conn),
                        show_sensitive=args.show_sensitive,
                    )
                },
            )
            return
        if args.domain == "notion" and args.action == "override-list":
            dump_output(
                args,
                {
                    "overrides": _redact_override_rows(
                        list_notion_identity_overrides(conn),
                        show_sensitive=args.show_sensitive,
                    )
                },
            )
            return
        if args.domain == "notion" and args.action == "override-set":
            payload = upsert_notion_identity_override(
                conn,
                agent_id=args.target if args.target.startswith("agent-") else "",
                unix_user="" if args.target.startswith("agent-") else args.target,
                notion_user_id=args.notion_user_id,
                notion_user_email=args.email,
                notes=args.notes,
            )
            log_ssot_access_audit(
                conn,
                agent_id=str(payload.get("agent_id") or ""),
                unix_user=str(payload.get("unix_user") or ""),
                notion_user_id=str(payload.get("notion_user_id") or ""),
                operation="override-identity",
                target_id=str(payload.get("unix_user") or payload.get("agent_id") or args.target),
                decision="allow",
                reason="identity override upserted",
                actor="operator-cli",
                request_payload={
                    "target": args.target,
                    "notion_user_id": args.notion_user_id,
                    "notion_user_email": args.email,
                    "notes": args.notes,
                },
            )
            dump_output(args, payload if args.show_sensitive else _redact_override_rows([payload], show_sensitive=False)[0])
            return
        if args.domain == "notion" and args.action == "override-clear":
            existing_override = get_notion_identity_override(
                conn,
                agent_id=args.target if args.target.startswith("agent-") else "",
                unix_user="" if args.target.startswith("agent-") else args.target,
            ) or {}
            removed = clear_notion_identity_override(
                conn,
                agent_id=args.target if args.target.startswith("agent-") else "",
                unix_user="" if args.target.startswith("agent-") else args.target,
            )
            if removed:
                log_ssot_access_audit(
                    conn,
                    agent_id=str(existing_override.get("agent_id") or (args.target if args.target.startswith("agent-") else "")),
                    unix_user=str(existing_override.get("unix_user") or ("" if args.target.startswith("agent-") else args.target)),
                    notion_user_id="",
                    operation="override-identity-clear",
                    target_id=args.target,
                    decision="allow",
                    reason="identity override cleared",
                    actor="operator-cli",
                    request_payload={"target": args.target},
                )
            dump_output(args, {"cleared": bool(removed), "target": args.target})
            return
        if args.domain == "notion" and args.action == "claim-email":
            payload = set_agent_identity_claim(
                conn,
                agent_id=args.target if args.target.startswith("agent-") else "",
                unix_user="" if args.target.startswith("agent-") else args.target,
                claimed_notion_email=args.email,
                verification_source=f"claim-email:{args.actor}",
            )
            dump_output(args, payload)
            return
        if args.domain == "notion" and args.action == "verify-identity":
            notion_user_id, notion_user_email = _manual_verify_notion_user(
                args.notion_user_id,
                expected_email=args.email,
            )
            payload = mark_agent_identity_verified(
                conn,
                agent_id=args.target if args.target.startswith("agent-") else "",
                unix_user="" if args.target.startswith("agent-") else args.target,
                notion_user_id=notion_user_id,
                notion_user_email=notion_user_email,
                verification_source=f"notion-live-check:{notion_user_email}",
            )
            dump_output(args, payload)
            return
        if args.domain == "notion" and args.action == "suspend":
            payload = suspend_agent_identity(
                conn,
                agent_id=args.target if args.target.startswith("agent-") else "",
                unix_user="" if args.target.startswith("agent-") else args.target,
            )
            log_ssot_access_audit(
                conn,
                agent_id=str(payload.get("agent_id") or ""),
                unix_user=str(payload.get("unix_user") or ""),
                notion_user_id=str(payload.get("notion_user_id") or ""),
                operation="suspend",
                target_id=str(payload.get("unix_user") or payload.get("agent_id") or args.target),
                decision="allow",
                reason=str(args.reason or "").strip() or "identity suspended",
                actor=args.actor,
                request_payload={"target": args.target, "reason": args.reason},
            )
            dump_output(args, payload)
            return
        if args.domain == "notion" and args.action == "unsuspend":
            payload = unsuspend_agent_identity(
                conn,
                agent_id=args.target if args.target.startswith("agent-") else "",
                unix_user="" if args.target.startswith("agent-") else args.target,
            )
            log_ssot_access_audit(
                conn,
                agent_id=str(payload.get("agent_id") or ""),
                unix_user=str(payload.get("unix_user") or ""),
                notion_user_id=str(payload.get("notion_user_id") or ""),
                operation="unsuspend",
                target_id=str(payload.get("unix_user") or payload.get("agent_id") or args.target),
                decision="allow",
                reason=str(args.reason or "").strip() or "identity unsuspended",
                actor=args.actor,
                request_payload={"target": args.target, "reason": args.reason},
            )
            dump_output(args, payload)
            return
        if args.domain == "notion" and args.action == "audit":
            dump_output(
                args,
                {
                    "audit": list_ssot_access_audit(
                        conn,
                        agent_id=args.agent_id,
                        unix_user=args.unix_user,
                        limit=args.limit,
                    )
                },
            )
            return

    raise SystemExit("unsupported command")


if __name__ == "__main__":
    main()
