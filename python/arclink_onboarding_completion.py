#!/usr/bin/env python3
from __future__ import annotations

import json
import pwd
import re
import secrets
import shutil
import shlex
import subprocess
from html import escape as html_escape
from pathlib import Path
from typing import Any

from arclink_agent_access import load_access_state
from arclink_control import Config, config_env_value, get_agent, get_agent_identity, save_onboarding_session
from arclink_resource_map import shared_resource_lines, shared_tailnet_host


def _release_state(cfg: Config) -> dict[str, Any]:
    path = cfg.release_state_file
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _repo_ref_contains_path(cfg: Config, ref: str, relative_path: str) -> bool | None:
    ref = str(ref or "").strip()
    if not ref or shutil.which("git") is None:
        return None
    try:
        ref_result = subprocess.run(
            ["git", "-C", str(cfg.repo_dir), "cat-file", "-e", f"{ref}^{{commit}}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if ref_result.returncode != 0:
            return None
        result = subprocess.run(
            ["git", "-C", str(cfg.repo_dir), "cat-file", "-e", f"{ref}:{relative_path}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.returncode == 0


def _remote_client_setup_url(cfg: Config) -> str:
    release_state = _release_state(cfg)
    raw_repo = str(
        release_state.get("tracked_upstream_repo_url")
        or release_state.get("deployed_source_repo")
        or cfg.upstream_repo_url
        or ""
    ).strip()
    deployed_commit = str(release_state.get("deployed_commit") or "").strip()
    branch = str(
        release_state.get("tracked_upstream_branch")
        or release_state.get("deployed_source_branch")
        or cfg.upstream_branch
        or "main"
    ).strip() or "main"
    ref = deployed_commit or branch
    helper_path = "bin/setup-remote-hermes-client.sh"
    if deployed_commit:
        contains_helper = _repo_ref_contains_path(cfg, deployed_commit, helper_path)
        if contains_helper is False:
            ref = branch
    prefix = ""
    if raw_repo.startswith("https://github.com/"):
        prefix = raw_repo.removeprefix("https://github.com/")
    elif raw_repo.startswith("git@github.com:"):
        prefix = raw_repo.removeprefix("git@github.com:")
    elif raw_repo.startswith("ssh://git@github.com/"):
        prefix = raw_repo.removeprefix("ssh://git@github.com/")
    else:
        return ""
    prefix = prefix.removesuffix(".git").strip("/")
    if not prefix:
        return ""
    return f"https://raw.githubusercontent.com/{prefix}/{ref}/bin/setup-remote-hermes-client.sh"


def completion_ack_callback_data(session_id: str) -> str:
    return f"arclink:onboarding-complete:ack:{session_id.strip()}"


def completion_setup_backup_callback_data(session_id: str) -> str:
    return f"arclink:onboarding-complete:setup-backup:{session_id.strip()}"


def completion_ack_telegram_markup(session_id: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [[
            {
                "text": "I recorded this safely",
                "callback_data": completion_ack_callback_data(session_id),
            }
        ]]
    }


def completion_ack_discord_components(session_id: str) -> list[dict[str, Any]]:
    return [
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 2,
                    "label": "I recorded this safely",
                    "custom_id": completion_ack_callback_data(session_id),
                }
            ],
        }
    ]


def completion_followup_telegram_markup(
    session_id: str,
    *,
    agent_backup_verified: bool = False,
) -> dict[str, Any] | None:
    if agent_backup_verified:
        return None
    return {
        "inline_keyboard": [[
            {
                "text": "Set up private backup",
                "callback_data": completion_setup_backup_callback_data(session_id),
            }
        ]]
    }


def completion_followup_discord_components(
    session_id: str,
    *,
    agent_backup_verified: bool = False,
) -> list[dict[str, Any]] | None:
    if agent_backup_verified:
        return None
    return [
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 1,
                    "label": "Set up private backup",
                    "custom_id": completion_setup_backup_callback_data(session_id),
                }
            ],
        }
    ]


def new_discord_agent_dm_confirmation_code() -> str:
    raw = secrets.token_hex(3).upper()
    return f"{raw[:3]}-{raw[3:]}"


def ensure_discord_agent_dm_confirmation_code(conn, session: dict[str, Any]) -> tuple[dict[str, Any], str]:
    answers = session.get("answers", {}) if isinstance(session.get("answers"), dict) else {}
    code = str(answers.get("discord_agent_dm_confirmation_code") or "").strip()
    if code:
        return session, code
    code = new_discord_agent_dm_confirmation_code()
    updated = save_onboarding_session(
        conn,
        session_id=str(session["session_id"]),
        answers={"discord_agent_dm_confirmation_code": code},
    )
    return updated, code


def _completion_delivery(session: dict[str, Any]) -> dict[str, Any]:
    answers = session.get("answers", {})
    raw = answers.get("completion_delivery") if isinstance(answers, dict) else None
    return raw if isinstance(raw, dict) else {}


def stored_completion_scrubbed_text(session: dict[str, Any]) -> str:
    return str(_completion_delivery(session).get("scrubbed_text") or "").strip()


def stored_completion_followup_text(session: dict[str, Any]) -> str:
    return str(_completion_delivery(session).get("followup_text") or "").strip()


def stored_completion_followup_telegram_parse_mode(session: dict[str, Any]) -> str:
    return str(_completion_delivery(session).get("followup_telegram_parse_mode") or "").strip()


def _shared_tailnet_host() -> str:
    return shared_tailnet_host(
        tailscale_serve_enabled=(config_env_value("ENABLE_TAILSCALE_SERVE", "0").strip() == "1"),
        tailscale_dns_name=config_env_value("TAILSCALE_DNS_NAME", "").strip(),
        nextcloud_trusted_domain=config_env_value("NEXTCLOUD_TRUSTED_DOMAIN", "").strip(),
    )


def _shared_resource_lines(cfg: Config) -> list[str]:
    host = _shared_tailnet_host()
    shared_lines = shared_resource_lines(
        host=host,
        tailscale_serve_port=config_env_value("TAILSCALE_SERVE_PORT", "443").strip() or "443",
        nextcloud_enabled=(config_env_value("ENABLE_NEXTCLOUD", "1").strip() == "1"),
        qmd_url=cfg.qmd_url,
        public_mcp_host=cfg.public_mcp_host,
        public_mcp_port=cfg.public_mcp_port,
        qmd_path=config_env_value("TAILSCALE_QMD_PATH", "/mcp").strip() or "/mcp",
        arclink_mcp_path=config_env_value("TAILSCALE_ARCLINK_MCP_PATH", "/arclink-mcp").strip() or "/arclink-mcp",
        extra_mcp_label=cfg.extra_mcp_label,
        extra_mcp_url=cfg.extra_mcp_url,
        notion_space_url=(
            config_env_value("ARCLINK_SSOT_NOTION_ROOT_PAGE_URL", "").strip()
            or config_env_value("ARCLINK_SSOT_NOTION_SPACE_URL", "").strip()
        ),
    )
    human_lines = [
        line
        for line in shared_lines
        if not line.startswith("QMD MCP retrieval rail:")
        and not line.startswith("ArcLink MCP control rail:")
    ]
    return ["Shared ArcLink links:", *[f"- {line}" for line in human_lines]]


def _discord_handoff_followup_lines(code: str) -> list[str]:
    code = str(code or "").strip()
    return [
        "Discord handoff:",
        f"- Your agent bot will DM you directly now with confirmation code `{code}`." if code else "- Your agent bot will DM you directly now.",
        "- If the code matches here and in the bot DM, that DM is your private agent lane.",
        "- If the bot DM does not arrive, run `/retry-contact` here and I will ask it to try again with the same code.",
    ]


def _telegram_handoff_followup_lines(bot_reference: str) -> list[str]:
    bot_reference = str(bot_reference or "").strip()
    return [
        "Telegram handoff:",
        f"- Tap {bot_reference} and press Start to open your private agent chat." if bot_reference.startswith("@") else "- Open your agent bot and press Start to open your private agent chat.",
        "- Use that bot chat from here on out.",
    ]


def _remote_ssh_target(access: dict[str, Any]) -> tuple[str, str]:
    remote_user = str(access.get("unix_user") or access.get("username") or "").strip()
    remote_host = str(access.get("tailscale_host") or _shared_tailnet_host()).strip()
    return remote_user, remote_host


def _remote_wrapper_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")


def remote_hermes_wrapper_name(*, remote_user: str = "", org_name: str = "", remote_host: str = "") -> str:
    wrapper_org = _remote_wrapper_slug(org_name) or _remote_wrapper_slug(remote_host)
    wrapper_user = _remote_wrapper_slug(remote_user)
    if wrapper_user and wrapper_org:
        return f"hermes-{wrapper_org}-remote-{wrapper_user}"
    if wrapper_org:
        return f"hermes-{wrapper_org}-remote"
    return "hermes-<org>-remote-<user>"


def _telegram_followup_html(lines: list[str], *, remote_setup_command: str = "") -> str:
    html_lines: list[str] = []
    remote_setup_command = remote_setup_command.strip()
    remote_run_line = f"- Run: {remote_setup_command}" if remote_setup_command else ""
    for line in lines:
        if remote_run_line and line == remote_run_line:
            html_lines.append(f"- Run: <code>{html_escape(remote_setup_command, quote=False)}</code>")
        else:
            html_lines.append(html_escape(line, quote=False))
    return "\n".join(html_lines)


def _compact_message_lines(lines: list[str]) -> list[str]:
    compact: list[str] = []
    previous_blank = True
    for raw_line in lines:
        line = str(raw_line or "").rstrip()
        if not line:
            if compact and not previous_blank:
                compact.append("")
            previous_blank = True
            continue
        compact.append(line)
        previous_blank = False
    while compact and compact[-1] == "":
        compact.pop()
    return compact


def completion_message_bundle(
    cfg: Config,
    *,
    session_id: str,
    bot_reference: str,
    access: dict[str, Any],
    home: Path,
    notion_status_line: str = "",
    notion_followup_line: str = "",
    bot_platform: str = "",
    discord_note: bool = False,
    discord_dm_confirmation_code: str = "",
    agent_backup_verified: bool = False,
    agent_backup_owner_repo: str = "",
) -> dict[str, Any]:
    platform = str(bot_platform or "").strip().lower()
    first_lines = [
        "Your lane is ready.",
        "",
        "Agent lane:",
        f"- Bot: {bot_reference}",
        f"- Unix user: {access.get('unix_user') or access.get('username')}",
        notion_status_line,
        "",
        "Temporary shared password:",
        "This password unlocks your Hermes dashboard and the Drive, Code, and Terminal tools inside it.",
        "Save this password now.",
    ]
    if agent_backup_verified:
        backup_line = (
            f"Private backup: active for `{agent_backup_owner_repo}`. Hermes-home state backs up every 4 hours."
            if agent_backup_owner_repo
            else "Private backup: active. Hermes-home state backs up every 4 hours."
        )
    else:
        backup_line = "Private backup: Raven can set this up with `/setup-backup`; shell fallback: ~/.local/bin/arclink-agent-configure-backup."
    handoff_lines: list[str] = []
    if discord_note:
        handoff_lines = _discord_handoff_followup_lines(discord_dm_confirmation_code)
    elif platform == "telegram":
        handoff_lines = _telegram_handoff_followup_lines(bot_reference)
    followup_lines = [
        "────────",
        "Start here:",
        *handoff_lines,
        "",
        "Web access:",
        f"- Hermes dashboard: {access.get('dashboard_url')}",
        f"- Dashboard username: {access.get('username')}",
        f"- Code plugin: {access.get('code_url')}",
        "",
        "Drive roots:",
        f"- Workspace root: {home}",
        f"- ArcLink vault: {home / 'ArcLink'}",
        "",
        "Host helper:",
        "- Remote shell helper on the host: ~/.local/bin/arclink-agent-hermes",
        "",
        "Backups:",
        backup_line,
        "- Use a separate agent-backup deploy key. Do not reuse the ArcLink code-push key or shared arclink-priv backup key.",
        "",
        *_shared_resource_lines(cfg),
        "- The shared Vault and control rails are already wired into your agent by default.",
        notion_followup_line,
        "If you pasted any API keys or bot tokens during setup, scroll up and edit or delete those messages. Raven cannot remove your own messages for you.",
    ]
    remote_setup_command = ""
    remote_setup_url = _remote_client_setup_url(cfg)
    if remote_setup_url:
        remote_user, remote_host = _remote_ssh_target(access)
        if remote_user and remote_host:
            org_name = config_env_value("ARCLINK_ORG_NAME", "").strip()
            org_arg = f" --org {shlex.quote(org_name)}" if org_name else ""
            remote_setup_command = (
                f"curl -fsSL {remote_setup_url} | bash -s -- "
                f"--host {shlex.quote(remote_host)} --user {shlex.quote(remote_user)}{org_arg}"
            )
            wrapper_name = remote_hermes_wrapper_name(
                remote_user=remote_user,
                org_name=org_name,
                remote_host=remote_host,
            )
            followup_lines.append("")
            followup_lines.append("Optional remote agent CLI from your own machine:")
            if str(bot_platform or "").strip().lower() == "discord":
                followup_lines.extend(["Run:", "```bash", remote_setup_command, "```"])
            else:
                followup_lines.append(f"- Run: {remote_setup_command}")
            followup_lines.append(
                "- That helper creates a local SSH key and wrapper. When it prints the key, reply here with "
                "`/ssh-key <public key>`; Raven will bind it to your Unix user and install it with Tailscale-only SSH restrictions."
            )
            followup_lines.append(
                f"- Use the generated `{wrapper_name}` wrapper, not your local `hermes` command. "
                "The wrapper starts Hermes on this host inside your agent lane, so it uses the remote config, skills, MCP tools, plugins, and files."
            )
            followup_lines.append(f"- Raw SSH target for debugging after key install: {remote_user}@{remote_host}")
        else:
            followup_lines.append(
                "Optional tailnet-only remote CLI: unavailable until this host has a Tailscale DNS name and your Unix user is recorded."
            )
    first_lines = _compact_message_lines(first_lines)
    followup_lines = _compact_message_lines(followup_lines)
    password = str(access.get("password") or "")
    ack_line = "After you record it safely, click the button below. I’ll remove the password from this message and then send the rest of your links."
    followup_telegram_parse_mode = "HTML" if platform == "telegram" else ""
    followup_text = (
        _telegram_followup_html(followup_lines, remote_setup_command=remote_setup_command)
        if followup_telegram_parse_mode
        else "\n".join(followup_lines)
    )

    telegram_parse_mode = ""
    if platform == "discord":
        full_lines = list(first_lines)
        full_lines.extend(["Shared password:", "```", password, "```"])
        ack_text = ack_line
    elif platform == "telegram":
        full_lines = [html_escape(line, quote=False) for line in first_lines]
        full_lines.extend(["Shared password:", f"<code>{html_escape(password, quote=False)}</code>"])
        telegram_parse_mode = "HTML"
        ack_text = html_escape(ack_line, quote=False)
    else:
        full_lines = list(first_lines)
        full_lines.append(f"Shared password: {password}")
        ack_text = ack_line
    full_lines.append("")
    full_lines.append(ack_text)

    scrubbed_lines = list(first_lines)
    scrubbed_lines.append("Shared password: removed after confirmation.")

    return {
        "full_text": "\n".join(full_lines),
        "scrubbed_text": "\n".join(scrubbed_lines),
        "followup_text": followup_text,
        "followup_telegram_parse_mode": followup_telegram_parse_mode,
        "followup_telegram_reply_markup": completion_followup_telegram_markup(
            session_id,
            agent_backup_verified=agent_backup_verified,
        ),
        "followup_discord_components": completion_followup_discord_components(
            session_id,
            agent_backup_verified=agent_backup_verified,
        ),
        "telegram_reply_markup": completion_ack_telegram_markup(session_id),
        "telegram_parse_mode": telegram_parse_mode,
        "discord_components": completion_ack_discord_components(session_id),
    }


def completion_bundle_for_session(
    conn,
    cfg: Config,
    session: dict[str, Any],
) -> dict[str, Any] | None:
    agent_id = str(session.get("linked_agent_id") or "").strip()
    session_id = str(session.get("session_id") or "").strip()
    if not agent_id or not session_id:
        return None
    agent = get_agent(conn, agent_id)
    if agent is None:
        return None

    unix_user = str(agent.get("unix_user") or "").strip()
    hermes_home = Path(str(agent.get("hermes_home") or "")).expanduser()
    access = load_access_state(hermes_home)
    if not access:
        return None

    try:
        home = Path(pwd.getpwnam(unix_user).pw_dir)
    except KeyError:
        home = hermes_home.parent.parent.parent if hermes_home.parts else Path("/")

    answers = session.get("answers", {})
    bot_platform = str(answers.get("bot_platform") or "").strip().lower()
    bot_username = str(answers.get("bot_username") or session.get("telegram_bot_username") or "").strip()
    bot_display = str(answers.get("bot_display_name") or answers.get("preferred_bot_name") or "your bot").strip() or "your bot"
    if bot_platform == "telegram":
        bot_reference = f"@{bot_username or bot_display}"
    elif bot_platform == "discord":
        bot_reference = f"`{bot_username or bot_display}`"
    else:
        bot_reference = bot_display

    identity = get_agent_identity(conn, agent_id=agent_id, unix_user=unix_user) or {}
    verification_status = str(identity.get("verification_status") or "").strip()
    notion_email = str(identity.get("notion_user_email") or identity.get("claimed_notion_email") or answers.get("notion_claim_email") or "").strip()
    if verification_status == "verified":
        notion_status_line = (
            f"Shared Notion writes: enabled for {notion_email or 'your verified Notion identity'} "
            "(native Notion history shows the ArcLink integration; Changed By is stamped to you on supported rows)"
        )
        notion_followup_line = ""
    elif bool(answers.get("notion_verification_skipped")):
        notion_status_line = "Shared Notion writes: read-only until you verify your Notion identity with Raven."
        notion_followup_line = "When you're ready, reply `/verify-notion` here and I'll reopen the verification step."
    else:
        notion_status_line = "Shared Notion writes: read-only until your Notion identity is verified."
        notion_followup_line = "Reply `/verify-notion` here any time you want Raven to resume that step."

    return completion_message_bundle(
        cfg,
        session_id=session_id,
        bot_reference=bot_reference,
        access=access,
        home=home,
        notion_status_line=notion_status_line,
        notion_followup_line=notion_followup_line,
        bot_platform=bot_platform,
        discord_note=(bot_platform == "discord"),
        discord_dm_confirmation_code=str(answers.get("discord_agent_dm_confirmation_code") or "").strip(),
        agent_backup_verified=bool(answers.get("agent_backup_verified")),
        agent_backup_owner_repo=str(answers.get("agent_backup_owner_repo") or "").strip(),
    )


def completion_scrubbed_text_for_session(
    conn,
    cfg: Config,
    session: dict[str, Any],
) -> str:
    stored = stored_completion_scrubbed_text(session)
    if stored:
        return stored
    bundle = completion_bundle_for_session(conn, cfg, session)
    if bundle is None:
        return ""
    return str(bundle.get("scrubbed_text") or "").strip()


def completion_followup_text_for_session(
    conn,
    cfg: Config,
    session: dict[str, Any],
) -> str:
    stored = stored_completion_followup_text(session)
    if stored:
        answers = session.get("answers", {}) if isinstance(session.get("answers"), dict) else {}
        code = str(answers.get("discord_agent_dm_confirmation_code") or "").strip()
        if (
            str(answers.get("bot_platform") or "").strip().lower() == "discord"
            and code
            and "Discord handoff:" not in stored
        ):
            stored = stored.rstrip() + "\n" + "\n".join(_discord_handoff_followup_lines(code))
        return stored
    bundle = completion_bundle_for_session(conn, cfg, session)
    if bundle is None:
        return ""
    return str(bundle.get("followup_text") or "").strip()


def completion_followup_telegram_parse_mode_for_session(
    conn,
    cfg: Config,
    session: dict[str, Any],
) -> str:
    if stored_completion_followup_text(session):
        return stored_completion_followup_telegram_parse_mode(session)
    stored = stored_completion_followup_telegram_parse_mode(session)
    if stored:
        return stored
    bundle = completion_bundle_for_session(conn, cfg, session)
    if bundle is None:
        return ""
    return str(bundle.get("followup_telegram_parse_mode") or "").strip()
