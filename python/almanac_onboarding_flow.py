#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import pwd
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from almanac_agent_access import load_access_state
from almanac_control import (
    Config,
    RateLimitError,
    approve_request,
    cancel_onboarding_session,
    config_env_value,
    connect_db,
    find_latest_onboarding_session_for_sender,
    find_active_onboarding_session,
    get_agent,
    get_notion_identity_claim,
    onboarding_session_has_started_provisioning,
    operator_telegram_action_extra,
    queue_notification,
    request_bootstrap,
    request_operator_action,
    save_onboarding_session,
    start_notion_identity_claim,
    start_onboarding_session,
    utc_now_iso,
    write_onboarding_secret,
    write_onboarding_platform_token_secret,
)
from almanac_discord import discord_send_message
from almanac_onboarding_provider_auth import (
    ProviderSetupSpec,
    complete_anthropic_pkce_authorization,
    normalize_api_key_credential,
    normalize_reasoning_effort,
    provider_browser_auth_prompt,
    provider_credential_prompt,
    provider_secret_name,
    provider_setup_from_dict,
    resolve_provider_setup,
    start_anthropic_pkce_authorization,
    start_codex_device_authorization,
)
from almanac_model_providers import provider_default_model, provider_recommended_models
from almanac_onboarding_completion import remote_hermes_wrapper_name
from almanac_telegram import telegram_send_message


START_COMMANDS = {"/start", "/onboard", "start", "onboard"}
STATUS_COMMANDS = {"/status", "status"}
CANCEL_COMMANDS = {"/cancel", "cancel"}
VERIFY_NOTION_COMMANDS = {"/verify-notion", "/verify_notion", "verify-notion", "verify_notion", "verify notion"}
SETUP_BACKUP_COMMANDS = {"/setup-backup", "/setup_backup", "setup-backup", "setup_backup", "setup backup", "/backup", "backup"}
NOTION_READY_COMMANDS = {"ready"}
UNIX_USER_PATTERN = re.compile(r"^[a-z_][a-z0-9_-]{0,30}$")
GITHUB_OWNER_REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SSH_PUBLIC_KEY_PATTERN = re.compile(
    r"^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384|ecdsa-sha2-nistp521)\s+[A-Za-z0-9+/=]+(?:\s+.*)?$"
)
PLATFORM_ALIASES = {
    "telegram": "telegram",
    "tg": "telegram",
    "discord": "discord",
    "dc": "discord",
}
ORG_PROVIDED_PRESET = "org-provided"
MODEL_PROVIDER_ORDER = (ORG_PROVIDED_PRESET, "chutes", "opus", "codex")
MODEL_PROVIDER_LABELS = {
    ORG_PROVIDED_PRESET: "Org-provided",
    "chutes": "Chutes",
    "opus": "Claude Opus",
    "codex": "OpenAI Codex",
}
MODEL_PROVIDER_DESCRIPTIONS = {
    ORG_PROVIDED_PRESET: "organization default provider and model; no personal provider credential needed",
    "chutes": "recommended; Chutes API key + model id, wired as a custom OpenAI-compatible Hermes provider",
    "opus": "Claude account OAuth; best for long, careful collaboration",
    "codex": "OpenAI Codex sign-in; best for code-heavy lanes",
}
CHUTES_DEFAULT_MODEL = provider_default_model("chutes") or "moonshotai/Kimi-K2.6-TEE"
CHUTES_LEGACY_DEFAULT_MODELS = {"auto-failover", "model-router"}
CHUTES_RECOMMENDED_MODELS = (
    "moonshotai/Kimi-K2.6-TEE",
    "zai-org/GLM-5.1-TEE",
    "model-router",
)
MODEL_PROVIDER_ALIASES = {
    "chute": "chutes",
    "chutes": "chutes",
    "chutesai": "chutes",
    "chutes.ai": "chutes",
    "claude": "opus",
    "anthropic": "opus",
    "opus": "opus",
    "openai": "codex",
    "openaicodex": "codex",
    "codex": "codex",
    "org": ORG_PROVIDED_PRESET,
    "team": ORG_PROVIDED_PRESET,
    "default": ORG_PROVIDED_PRESET,
    "orgdefault": ORG_PROVIDED_PRESET,
    "orgprovided": ORG_PROVIDED_PRESET,
    "organizationdefault": ORG_PROVIDED_PRESET,
    "organizationprovided": ORG_PROVIDED_PRESET,
    "teamdefault": ORG_PROVIDED_PRESET,
    "teamprovided": ORG_PROVIDED_PRESET,
}
REASONING_EFFORT_OPTIONS = (
    ("xhigh", "Maximum depth where the provider supports it"),
    ("high", "Deeper thinking for harder work"),
    ("medium", "Recommended default; balanced speed and depth"),
    ("low", "Faster, lighter thinking"),
    ("minimal", "Smallest reasoning budget"),
    ("none", "Disable provider thinking/reasoning hints"),
)


@dataclass(frozen=True)
class IncomingMessage:
    platform: str
    chat_id: str
    sender_id: str
    text: str
    sender_username: str = ""
    sender_display_name: str = ""
    reply_to_message_id: int | None = None


@dataclass(frozen=True)
class OutboundMessage:
    chat_id: str
    text: str
    reply_to_message_id: int | None = None
    telegram_reply_markup: dict[str, Any] | None = None
    telegram_parse_mode: str = ""
    discord_components: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class BotIdentity:
    bot_id: str
    username: str = ""
    display_name: str = ""


BotTokenValidator = Callable[[str], BotIdentity]


def read_env_file_value(path: Path, key: str) -> str:
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


def resolve_curator_telegram_bot_token(cfg: Config) -> str:
    token = config_env_value("TELEGRAM_BOT_TOKEN", "").strip()
    if token:
        return token
    return read_env_file_value(cfg.curator_hermes_home / ".env", "TELEGRAM_BOT_TOKEN").strip()


def resolve_curator_discord_bot_token(cfg: Config) -> str:
    token = config_env_value("DISCORD_BOT_TOKEN", "").strip()
    if token:
        return token
    return read_env_file_value(cfg.curator_hermes_home / ".env", "DISCORD_BOT_TOKEN").strip()


def shared_notion_home_url() -> str:
    root_url = config_env_value("ALMANAC_SSOT_NOTION_ROOT_PAGE_URL", "").strip()
    if root_url:
        return root_url
    return config_env_value("ALMANAC_SSOT_NOTION_SPACE_URL", "").strip()


def shared_notion_self_serve_configured() -> bool:
    return bool(
        str(config_env_value("ALMANAC_SSOT_NOTION_TOKEN", "") or "").strip()
        and str(config_env_value("ALMANAC_SSOT_NOTION_SPACE_ID", "") or "").strip()
    )


def send_session_message(
    cfg: Config,
    session: dict[str, Any],
    text: str,
    *,
    telegram_reply_markup: dict[str, Any] | None = None,
    telegram_parse_mode: str = "",
    discord_components: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    platform = str(session.get("platform") or "").strip().lower()
    chat_id = str(session.get("chat_id") or "").strip()
    if not platform or not chat_id or not text:
        return None
    if platform == "telegram":
        token = resolve_curator_telegram_bot_token(cfg)
        if token:
            try:
                return telegram_send_message(
                    bot_token=token,
                    chat_id=chat_id,
                    text=text,
                    reply_markup=telegram_reply_markup,
                    parse_mode=telegram_parse_mode,
                )
            except Exception:
                return None
        return None
    if platform == "discord":
        token = resolve_curator_discord_bot_token(cfg)
        if token:
            try:
                return discord_send_message(
                    bot_token=token,
                    channel_id=chat_id,
                    text=text,
                    components=discord_components,
                )
            except Exception:
                return None
    return None


def session_prompt_telegram_parse_mode(session: dict[str, Any]) -> str:
    platform = str(session.get("platform") or "").strip().lower()
    if platform != "telegram":
        return ""
    state = str(session.get("state") or "")
    if state != "awaiting-model-id":
        return ""
    answers = session.get("answers", {})
    if not isinstance(answers, dict):
        answers = {}
    model_preset = str(answers.get("model_preset") or "chutes").strip().lower() or "chutes"
    if model_preset == "chutes":
        return "Markdown"
    return ""


def notify_session_state(cfg: Config, session: dict[str, Any]) -> None:
    send_session_message(
        cfg,
        session,
        session_prompt(cfg, session),
        telegram_parse_mode=session_prompt_telegram_parse_mode(session),
    )


def _session_prompt_reply(
    cfg: Config,
    incoming: IncomingMessage,
    session: dict[str, Any],
    reply_to_message_id: int | None = None,
) -> OutboundMessage:
    return OutboundMessage(
        incoming.chat_id,
        session_prompt(cfg, session),
        reply_to_message_id,
        telegram_parse_mode=session_prompt_telegram_parse_mode(session),
    )


def format_user_label(platform: str, username: str, display_name: str, sender_id: str) -> str:
    normalized_platform = str(platform or "").strip().lower()
    if username:
        return f"@{username}" if normalized_platform == "telegram" else username
    if display_name:
        return display_name
    return f"{normalized_platform or 'user'}:{sender_id}"


def desired_unix_user_available(unix_user: str) -> tuple[bool, str]:
    candidate = unix_user.strip().lower()
    if not UNIX_USER_PATTERN.fullmatch(candidate):
        return False, "Use 1-31 chars: lowercase letters, digits, `_`, or `-`, starting with a letter or `_`."
    try:
        pwd.getpwnam(candidate)
        return False, f"`{candidate}` already exists on the host. Pick another Unix username."
    except KeyError:
        return True, ""


def _as_strings(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _profile_match_norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _profile_match_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _profile_handle_key(value: str) -> str:
    return _profile_match_key(str(value or "").lstrip("@"))


def _profile_identity_match_visibility(profile: dict[str, Any]) -> str:
    identity = profile.get("identity_verification") if isinstance(profile.get("identity_verification"), dict) else {}
    if identity.get("safe_roster_prompt") is False:
        return "none"
    visibility = str(identity.get("allowed_match_visibility") or "unclaimed_people_only").strip().lower()
    if visibility not in {"none", "unclaimed_people_only", "team_visible", "all_profile_people"}:
        visibility = "unclaimed_people_only"
    return visibility


def _profile_match_privacy_allows_list(profile: dict[str, Any]) -> bool:
    policies = profile.get("policies") if isinstance(profile.get("policies"), dict) else {}
    privacy = policies.get("privacy") if isinstance(policies.get("privacy"), dict) else {}
    visibility = str(privacy.get("default_people_visibility") or "").strip().lower()
    return visibility in {"org_visible", "group_visible", "team_visible", "household_visible"}


def _profile_person_matchable(person: dict[str, Any]) -> bool:
    metadata = person.get("metadata") if isinstance(person.get("metadata"), dict) else {}
    return metadata.get("onboarding_matchable") is not False


def _profile_person_label(profile: dict[str, Any], person: dict[str, Any]) -> str:
    roles = profile.get("roles") if isinstance(profile.get("roles"), dict) else {}
    teams = profile.get("teams") if isinstance(profile.get("teams"), list) else []
    role_id = str(person.get("role") or "").strip()
    role = roles.get(role_id) if isinstance(roles.get(role_id), dict) else {}
    title = str(person.get("title") or "").strip()
    role_label = title or str(role.get("description") or role_id).strip()
    primary_team = str(person.get("primary_team") or "").strip()
    team_name = ""
    for team in teams:
        if isinstance(team, dict) and str(team.get("id") or "").strip() == primary_team:
            team_name = str(team.get("name") or "").strip()
            break
    label = str(person.get("display_name") or person.get("id") or "").strip()
    details = [part for part in (role_label, team_name) if part]
    if details:
        label += " - " + ", ".join(details[:2])
    return label[:180]


def _profile_person_match_score(person: dict[str, Any], incoming: IncomingMessage, full_name: str) -> int:
    identity = person.get("identity_hints") if isinstance(person.get("identity_hints"), dict) else {}
    contact = person.get("contact") if isinstance(person.get("contact"), dict) else {}
    github = person.get("github") if isinstance(person.get("github"), dict) else {}
    agent = person.get("agent") if isinstance(person.get("agent"), dict) else {}

    score = 0
    platform = incoming.platform.strip().lower()
    sender_id = incoming.sender_id.strip()
    if platform == "discord" and sender_id and str(identity.get("discord_user_id") or "").strip() == sender_id:
        score = max(score, 100)
    if platform == "telegram" and sender_id and str(identity.get("telegram_user_id") or "").strip() == sender_id:
        score = max(score, 100)

    username_key = _profile_handle_key(incoming.sender_username)
    if username_key:
        handle_values = [
            str(identity.get("discord_handle") or ""),
            str(contact.get("discord_handle") or ""),
            str(identity.get("github_username") or ""),
            str(github.get("username") or ""),
        ]
        if username_key in {_profile_handle_key(value) for value in handle_values if value}:
            score = max(score, 80)

    name_values = [
        str(person.get("display_name") or ""),
        str(person.get("preferred_name") or ""),
        str(agent.get("name") or ""),
        *_as_strings(identity.get("aliases")),
    ]
    probe_values = [
        full_name,
        incoming.sender_display_name,
        incoming.sender_username,
    ]
    name_keys = {_profile_match_key(value) for value in name_values if value}
    probe_keys = {_profile_match_key(value) for value in probe_values if value}
    if name_keys and probe_keys and name_keys & probe_keys:
        score = max(score, 70)

    name_words = set()
    for value in name_values:
        name_words.update(_profile_match_norm(value).split())
    probe_words = set()
    for value in probe_values:
        probe_words.update(_profile_match_norm(value).split())
    if name_words and probe_words and name_words & probe_words:
        score = max(score, 35)
    return score


def _active_profile_links(conn) -> tuple[set[str], set[str]]:
    rows = conn.execute(
        """
        SELECT a.unix_user, COALESCE(i.org_profile_person_id, '') AS org_profile_person_id
        FROM agents a
        LEFT JOIN agent_identity i
          ON i.unix_user = a.unix_user
        WHERE a.role = 'user' AND a.status = 'active'
        """
    ).fetchall()
    active_unix_users = {str(row["unix_user"] or "").strip().lower() for row in rows if str(row["unix_user"] or "").strip()}
    linked_person_ids = {
        str(row["org_profile_person_id"] or "").strip()
        for row in rows
        if str(row["org_profile_person_id"] or "").strip()
    }
    return active_unix_users, linked_person_ids


def _org_profile_match_candidates(conn, cfg: Config, incoming: IncomingMessage, full_name: str) -> list[dict[str, Any]]:
    try:
        from almanac_org_profile import load_applied_profile
    except Exception:
        return []
    profile = load_applied_profile(cfg)
    match_visibility = _profile_identity_match_visibility(profile)
    if not profile or match_visibility == "none" or not _profile_match_privacy_allows_list(profile):
        return []
    people = profile.get("people") if isinstance(profile.get("people"), list) else []
    active_unix_users, linked_person_ids = _active_profile_links(conn)
    candidates: list[dict[str, Any]] = []
    for person in people:
        if not isinstance(person, dict) or not _profile_person_matchable(person):
            continue
        person_id = str(person.get("id") or "").strip()
        if not person_id or person_id in linked_person_ids:
            continue
        unix_user = str(person.get("unix_user") or "").strip().lower()
        if unix_user and unix_user in active_unix_users:
            continue
        score = _profile_person_match_score(person, incoming, full_name)
        if score <= 0 and match_visibility != "all_profile_people":
            continue
        candidates.append(
            {
                "id": person_id,
                "label": _profile_person_label(profile, person),
                "suggested_unix_user": unix_user,
                "score": score,
            }
        )
    candidates.sort(key=lambda item: (-int(item.get("score") or 0), str(item.get("label") or "").casefold()))
    return candidates[:10]


def _maybe_stage_profile_match_prompt(conn, cfg: Config, incoming: IncomingMessage, session: dict[str, Any]) -> dict[str, Any]:
    if str(session.get("state") or "") != "awaiting-purpose":
        return session
    answers = session.get("answers", {}) if isinstance(session.get("answers"), dict) else {}
    if str(answers.get("org_profile_match_status") or "").strip():
        return session
    full_name = str(answers.get("full_name") or incoming.sender_display_name or "").strip()
    if not full_name:
        return session
    candidates = _org_profile_match_candidates(conn, cfg, incoming, full_name)
    if not candidates:
        return session
    safe_candidates = [
        {
            "id": str(candidate.get("id") or ""),
            "label": str(candidate.get("label") or ""),
            "suggested_unix_user": str(candidate.get("suggested_unix_user") or ""),
            "score": int(candidate.get("score") or 0),
        }
        for candidate in candidates
    ]
    return save_onboarding_session(
        conn,
        session_id=str(session["session_id"]),
        state="awaiting-profile-match",
        answers={
            "org_profile_candidates": safe_candidates,
            "org_profile_match_status": "prompted",
        },
        chat_id=incoming.chat_id,
        sender_username=incoming.sender_username,
        sender_display_name=incoming.sender_display_name or full_name,
    )


def _operator_target(cfg: Config) -> tuple[str, str]:
    return (
        cfg.operator_notify_channel_id or cfg.operator_notify_platform or "operator",
        cfg.operator_notify_platform or "tui-only",
    )


def _parse_platform_choice(raw_text: str) -> str:
    return PLATFORM_ALIASES.get(raw_text.strip().lower(), "")


def _parse_model_preset(cfg: Config, raw_text: str) -> str:
    normalized = raw_text.strip().lower()
    rows = _model_option_rows(cfg)
    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(rows):
            return rows[index][0]
    if normalized in cfg.model_presets:
        return normalized
    compact = normalized.replace(" ", "").replace("-", "").replace("_", "")
    alias = MODEL_PROVIDER_ALIASES.get(compact) or MODEL_PROVIDER_ALIASES.get(normalized)
    if alias in cfg.model_presets:
        return alias
    for key in cfg.model_presets:
        if compact == key.replace("-", "").replace("_", ""):
            return key
    return ""


def _org_provider_secret() -> str:
    return config_env_value("ALMANAC_ORG_PROVIDER_SECRET", "").strip()


def _org_provider_reasoning_effort(cfg: Config | None = None) -> str:
    configured = ""
    if cfg is not None:
        configured = str(getattr(cfg, "org_provider_reasoning_effort", "") or "").strip()
    configured = configured or config_env_value("ALMANAC_ORG_PROVIDER_REASONING_EFFORT", "medium")
    return normalize_reasoning_effort(configured, default="medium") or "medium"


def _resolve_org_provider_setup(cfg: Config) -> ProviderSetupSpec | None:
    if ORG_PROVIDED_PRESET not in cfg.model_presets:
        return None
    try:
        return resolve_provider_setup(
            cfg,
            ORG_PROVIDED_PRESET,
            model_id=_configured_model_id(cfg, ORG_PROVIDED_PRESET),
            reasoning_effort=_org_provider_reasoning_effort(cfg),
        )
    except Exception:
        return None


def _model_provider_label(cfg: Config, preset: str) -> str:
    if preset == ORG_PROVIDED_PRESET:
        spec = _resolve_org_provider_setup(cfg)
        if spec is not None:
            return f"Org-provided ({spec.display_name})"
    return MODEL_PROVIDER_LABELS.get(preset, preset)


def _model_provider_description(cfg: Config, preset: str) -> str:
    if preset == ORG_PROVIDED_PRESET:
        spec = _resolve_org_provider_setup(cfg)
        if spec is not None:
            model_id = _configured_model_id(cfg, ORG_PROVIDED_PRESET) or spec.model_id
            return (
                f"organization default: {spec.display_name} with `{model_id}`; "
                "no personal provider credential needed"
            )
    return MODEL_PROVIDER_DESCRIPTIONS.get(preset, str(cfg.model_presets.get(preset) or ""))


def _model_option_rows(cfg: Config) -> list[tuple[str, str, str]]:
    ordered_keys = [key for key in MODEL_PROVIDER_ORDER if key in cfg.model_presets]
    ordered_keys.extend(sorted(key for key in cfg.model_presets if key not in ordered_keys))
    rows: list[tuple[str, str, str]] = []
    for key in ordered_keys:
        rows.append(
            (
                key,
                _model_provider_label(cfg, key),
                _model_provider_description(cfg, key),
            )
        )
    return rows


def _model_options(cfg: Config) -> str:
    lines = []
    for index, (key, label, description) in enumerate(_model_option_rows(cfg), start=1):
        lines.append(f"{index}. {label} (`{key}`) - {description}")
    return "\n".join(lines)


def _configured_model_id(cfg: Config, preset: str) -> str:
    target = str(cfg.model_presets.get(preset) or "").strip()
    if ":" not in target:
        return target
    return target.split(":", 1)[1].strip()


def _default_model_id(cfg: Config, preset: str) -> str:
    configured = _configured_model_id(cfg, preset)
    if preset == "chutes" and configured.lower() in {"", *CHUTES_LEGACY_DEFAULT_MODELS}:
        return CHUTES_DEFAULT_MODEL
    return configured


def _recommended_models(cfg: Config, preset: str) -> tuple[str, ...]:
    configured = provider_recommended_models(preset, cfg.repo_dir)
    if configured:
        return configured
    if preset == "chutes":
        return CHUTES_RECOMMENDED_MODELS
    default_model = _default_model_id(cfg, preset)
    return (default_model,) if default_model else ()


def _parse_model_id(cfg: Config, preset: str, raw_text: str) -> tuple[str, str]:
    value = raw_text.strip().strip("`").rstrip("\\").strip()
    default_model = _default_model_id(cfg, preset)
    if value.lower() in {"", "default", "recommended", "auto"}:
        return default_model, ""
    if any(char.isspace() for char in value):
        examples = ", ".join(f"`{model}`" for model in _recommended_models(cfg, preset))
        return "", f"Use a single model id with no spaces, like {examples}."
    if value.upper().endswith(":THINKING"):
        value = value[: -len(":THINKING")]
    return value, ""


def _parse_github_owner_repo(raw_text: str) -> tuple[str, str]:
    value = raw_text.strip().strip("`").rstrip("\\").strip()
    if value.startswith("https://github.com/"):
        value = value.removeprefix("https://github.com/")
    elif value.startswith("git@github.com:"):
        value = value.removeprefix("git@github.com:")
    elif value.startswith("ssh://git@github.com/"):
        value = value.removeprefix("ssh://git@github.com/")
    value = value.removesuffix(".git").strip("/")
    if not value:
        return "", ""
    if not GITHUB_OWNER_REPO_PATTERN.fullmatch(value):
        return "", "Reply with a GitHub `owner/repo` path like `example/almanac-guide`, or `skip`."
    if value.endswith("/.git") or "//" in value:
        return "", "Reply with a GitHub `owner/repo` path like `example/almanac-guide`, or `skip`."
    return value, ""


def _github_ssh_remote(owner_repo: str) -> str:
    return f"git@github.com:{owner_repo.strip('/')}.git"


def _parse_reasoning_effort(raw_text: str) -> str:
    normalized = raw_text.strip().lower()
    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(REASONING_EFFORT_OPTIONS):
            return REASONING_EFFORT_OPTIONS[index][0]
    return normalize_reasoning_effort(normalized, default="medium")


def _operator_review_message(cfg: Config, session: dict[str, Any]) -> str:
    answers = session.get("answers", {})
    requester = format_user_label(
        str(session.get("platform") or ""),
        str(session.get("sender_username") or ""),
        str(session.get("sender_display_name") or answers.get("full_name") or ""),
        str(session.get("sender_id") or ""),
    )
    session_id = str(session.get("session_id") or "")
    model_preset = str(answers.get("model_preset") or "codex")
    model_id = str(answers.get("model_id") or "").strip()
    reasoning_effort = str(answers.get("reasoning_effort") or "").strip()
    bot_platform = str(answers.get("bot_platform") or "telegram")
    lines = [
        f"Onboarding request {session_id}",
        f"Requester: {requester}",
        f"Intake platform: {session.get('platform') or '(missing)'}",
        f"Name: {answers.get('full_name') or '(missing)'}",
        f"Unix user: {answers.get('unix_user') or '(missing)'}",
        f"Purpose: {answers.get('purpose') or '(missing)'}",
        f"Bot platform: {bot_platform}",
        f"Preferred bot name: {answers.get('preferred_bot_name') or '(missing)'}",
        f"Model provider: {_model_provider_label(cfg, model_preset)} (`{model_preset}`)",
        f"Model id: {model_id or _configured_model_id(cfg, model_preset) or '(provider default)'}",
        f"Thinking level: {reasoning_effort or 'medium'}",
        f"Approve: ./bin/almanac-ctl onboarding approve {session_id}",
        f"Deny: ./bin/almanac-ctl onboarding deny {session_id} --reason 'optional reason'",
    ]
    org_person_id = str(answers.get("org_profile_person_id") or "").strip()
    if org_person_id:
        lines.insert(
            5,
            (
                "Profile match: "
                f"{answers.get('org_profile_person_label') or org_person_id} "
                f"(`{org_person_id}`, user-selected, unverified)"
            ),
        )
    if cfg.operator_notify_platform == "telegram":
        lines.extend(
            [
                "Tap Approve / Deny below, or use one of these commands:",
                f"Telegram approve: /approve {session_id}",
                f"Telegram deny: /deny {session_id} optional reason",
            ]
        )
    elif cfg.operator_notify_platform == "discord":
        lines.extend(
            [
                "Use the configured primary Discord operator channel for approvals:",
                f"Discord approve: /approve {session_id}",
                f"Discord deny: /deny {session_id} optional reason",
            ]
        )
    return "\n".join(lines)


def _notify_operator(conn, cfg: Config, session: dict[str, Any]) -> None:
    target_id, channel_kind = _operator_target(cfg)
    queue_notification(
        conn,
        target_kind="operator",
        target_id=target_id,
        channel_kind=channel_kind,
        message=_operator_review_message(cfg, session),
        extra=operator_telegram_action_extra(
            cfg,
            scope="onboarding",
            target_id=str(session.get("session_id") or ""),
        ),
    )


def _bot_platform_name(session: dict[str, Any]) -> str:
    return str(session.get("answers", {}).get("bot_platform") or "telegram").strip().lower() or "telegram"


def _preferred_bot_name(session: dict[str, Any]) -> str:
    return str(session.get("answers", {}).get("preferred_bot_name") or "your bot")


def _session_requester_identity(session: dict[str, Any]) -> str:
    answers = session.get("answers", {})
    return format_user_label(
        str(session.get("platform") or ""),
        str(session.get("sender_username") or ""),
        str(session.get("sender_display_name") or answers.get("full_name") or ""),
        str(session.get("sender_id") or ""),
    )


def _provider_setup(session: dict[str, Any]) -> ProviderSetupSpec | None:
    answers = session.get("answers", {})
    return provider_setup_from_dict(answers.get("provider_setup"))


def _shared_provider_secret(spec: ProviderSetupSpec | None) -> str:
    if spec is None or spec.auth_flow != "api-key" or not spec.key_env:
        return ""
    return config_env_value(spec.key_env, "").strip()


def _shared_provider_credential_available(spec: ProviderSetupSpec | None) -> bool:
    return bool(_shared_provider_secret(spec))


def _org_provider_selection_note(cfg: Config, session: dict[str, Any]) -> str:
    answers = session.get("answers", {})
    if str(answers.get("model_preset") or "").strip().lower() != ORG_PROVIDED_PRESET:
        return ""
    spec = _resolve_org_provider_setup(cfg)
    if spec is None:
        return ""
    model_id = str(answers.get("model_id") or "").strip() or _configured_model_id(cfg, ORG_PROVIDED_PRESET) or spec.model_id
    lines = [
        f"Using organization-provided {spec.display_name} with default model `{model_id}`.",
    ]
    wrapper_name = remote_hermes_wrapper_name(
        remote_user=str(answers.get("unix_user") or "").strip(),
        org_name=config_env_value("ALMANAC_ORG_NAME", "").strip() or config_env_value("ALMANAC_NAME", "almanac").strip(),
    )
    if spec.provider_id == "chutes":
        lines.append(
            f"To change Chutes models later, use the remote Hermes wrapper: `{wrapper_name} setup model`. "
            "Chat `/model <model name>` does not switch Chutes custom-provider models."
        )
    else:
        lines.append(
            "To change models later, send your agent `/model <model name>`, "
            f"or use the remote Hermes wrapper: `{wrapper_name} setup model`."
        )
    return "\n\n".join(lines)


def _provider_auth_state(session: dict[str, Any]) -> dict[str, Any]:
    answers = session.get("answers", {})
    raw = answers.get("provider_browser_auth")
    return raw if isinstance(raw, dict) else {}


def _shared_tailnet_host() -> str:
    try:
        from almanac_resource_map import shared_tailnet_host

        return shared_tailnet_host(
            tailscale_serve_enabled=(config_env_value("ENABLE_TAILSCALE_SERVE", "0").strip() == "1"),
            tailscale_dns_name=config_env_value("TAILSCALE_DNS_NAME", "").strip(),
            nextcloud_trusted_domain=config_env_value("NEXTCLOUD_TRUSTED_DOMAIN", "").strip(),
        )
    except Exception:
        return ""


def _extract_remote_ssh_pubkey(raw_text: str) -> tuple[bool, str]:
    text = raw_text.strip()
    if not text:
        return False, ""
    lowered = text.lower()
    for prefix in ("/ssh-key", "/ssh_key", "/sshkey", "ssh-key", "ssh_key", "sshkey"):
        if lowered == prefix:
            return True, ""
        if lowered.startswith(prefix + " "):
            return True, text[len(prefix):].strip()
    if SSH_PUBLIC_KEY_PATTERN.fullmatch(text):
        return True, text
    return False, ""


def _remote_ssh_target_for_agent(agent: dict[str, Any]) -> tuple[str, str]:
    unix_user = str(agent.get("unix_user") or "").strip()
    hermes_home = Path(str(agent.get("hermes_home") or "")).expanduser()
    access = load_access_state(hermes_home) if hermes_home else {}
    return unix_user, str(access.get("tailscale_host") or _shared_tailnet_host()).strip()


def _queue_remote_ssh_key_install(
    conn,
    cfg: Config,
    incoming: IncomingMessage,
    *,
    pubkey: str,
) -> list[OutboundMessage]:
    if not SSH_PUBLIC_KEY_PATTERN.fullmatch(pubkey.strip()):
        return [
            OutboundMessage(
                incoming.chat_id,
                "That does not look like an SSH public key. Run the remote helper again and reply with `/ssh-key ` followed by the printed `ssh-ed25519 ...` line.",
            )
        ]
    session = find_latest_onboarding_session_for_sender(
        conn,
        platform=incoming.platform,
        sender_id=incoming.sender_id,
        redact_secrets=False,
    )
    if session is None or str(session.get("state") or "") != "completed":
        return [
            OutboundMessage(
                incoming.chat_id,
                "I can install a remote SSH key after your agent lane is completed. Finish onboarding first, then send `/ssh-key <public key>` here.",
            )
        ]
    agent_id = str(session.get("linked_agent_id") or "").strip()
    if not agent_id:
        return [OutboundMessage(incoming.chat_id, "I found your completed onboarding session, but it is not linked to an agent yet.")]
    agent = get_agent(conn, agent_id)
    if agent is None:
        return [OutboundMessage(incoming.chat_id, "I found your lane record, but the linked agent is missing. Ask the operator to run a health check.")]
    unix_user, tailnet_host = _remote_ssh_target_for_agent(agent)
    if not unix_user:
        return [OutboundMessage(incoming.chat_id, "I found your agent, but its Unix user is missing. Ask the operator to repair the enrollment record.")]
    if not tailnet_host:
        return [
            OutboundMessage(
                incoming.chat_id,
                "I can queue the key, but this host does not have a Tailscale hostname recorded yet. Ask the operator to set `TAILSCALE_DNS_NAME` or enable Tailscale Serve first.",
            )
        ]
    payload = {
        "session_id": str(session.get("session_id") or ""),
        "agent_id": agent_id,
        "unix_user": unix_user,
        "pubkey": pubkey.strip(),
        "platform": incoming.platform,
        "chat_id": incoming.chat_id,
        "sender_id": incoming.sender_id,
        "tailscale_host": tailnet_host,
    }
    action, created = request_operator_action(
        conn,
        action_kind="install-agent-ssh-key",
        requested_by=format_user_label(
            incoming.platform,
            incoming.sender_username,
            incoming.sender_display_name,
            incoming.sender_id,
        ),
        request_source=f"{incoming.platform}-remote-ssh-key",
        requested_target=json.dumps(payload, sort_keys=True),
        dedupe_by_target=True,
    )
    queued_text = "queued" if created else "already queued"
    ssh_target = f"{unix_user}@{tailnet_host}"
    return [
        OutboundMessage(
            incoming.chat_id,
            (
                f"Remote agent key install {queued_text} for `{unix_user}`. "
                "The root maintenance loop will install it with Tailscale-only restrictions. "
                "After it confirms, run your generated `hermes-<org>-remote-<user>` wrapper. "
                "That wrapper starts Hermes on the remote agent lane, so it uses the agent's remote config, skills, MCP tools, and files. "
                f"Raw SSH is available for debugging as `{ssh_target}`."
            ),
        )
    ]


def _agent_for_completed_session(conn, session: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    agent_id = str(session.get("linked_agent_id") or "").strip()
    if not agent_id:
        return None, "I found your onboarding session, but it is not linked to an agent yet."
    agent = get_agent(conn, agent_id)
    if agent is None:
        return None, "I found your lane record, but the linked agent is missing. Ask the operator to run a health check."
    return agent, ""


def _agent_backup_payload(session: dict[str, Any], agent: dict[str, Any], *, owner_repo: str, phase: str) -> dict[str, Any]:
    unix_user = str(agent.get("unix_user") or (session.get("answers") or {}).get("unix_user") or "").strip()
    hermes_home = str(agent.get("hermes_home") or "").strip()
    return {
        "phase": phase,
        "session_id": str(session.get("session_id") or ""),
        "agent_id": str(session.get("linked_agent_id") or agent.get("agent_id") or ""),
        "unix_user": unix_user,
        "hermes_home": hermes_home,
        "owner_repo": owner_repo,
        "remote": _github_ssh_remote(owner_repo),
        "branch": "main",
        "include_sessions": "1",
        "platform": str(session.get("platform") or ""),
        "chat_id": str(session.get("chat_id") or ""),
        "sender_id": str(session.get("sender_id") or ""),
    }


def _queue_agent_backup_action(
    conn,
    incoming: IncomingMessage,
    session: dict[str, Any],
    agent: dict[str, Any],
    *,
    owner_repo: str,
    phase: str,
) -> tuple[dict[str, Any], bool]:
    payload = _agent_backup_payload(session, agent, owner_repo=owner_repo, phase=phase)
    return request_operator_action(
        conn,
        action_kind="configure-agent-backup",
        requested_by=format_user_label(
            incoming.platform,
            incoming.sender_username,
            incoming.sender_display_name,
            incoming.sender_id,
        ),
        request_source=f"{incoming.platform}-agent-backup-{phase}",
        requested_target=json.dumps(payload, sort_keys=True),
        dedupe_by_target=True,
    )


def _resume_agent_backup_session(conn, cfg: Config, incoming: IncomingMessage) -> list[OutboundMessage]:
    session = find_latest_onboarding_session_for_sender(
        conn,
        platform=incoming.platform,
        sender_id=incoming.sender_id,
        redact_secrets=False,
    )
    if session is None or str(session.get("state") or "") != "completed":
        return [OutboundMessage(incoming.chat_id, "I can set up the private agent backup after your agent lane is completed.")]
    agent, reason = _agent_for_completed_session(conn, session)
    if agent is None:
        return [OutboundMessage(incoming.chat_id, reason)]
    updated = save_onboarding_session(
        conn,
        session_id=str(session["session_id"]),
        state="awaiting-agent-backup-repo",
        chat_id=incoming.chat_id,
        sender_username=incoming.sender_username,
        sender_display_name=incoming.sender_display_name or str(session.get("sender_display_name") or ""),
        completed_at="",
        last_prompt_at=utc_now_iso(),
        answers={
            "agent_backup_next_phase": "completed",
            "agent_backup_owner_repo": "",
            "agent_backup_remote": "",
            "agent_backup_public_key": "",
        },
    )
    return [_session_prompt_reply(cfg, incoming, updated)]

def _codex_browser_auth_error_state(message: str) -> dict[str, Any]:
    compact = message.strip() or "unknown OpenAI Codex auth error"
    return {
        "flow": "device_code",
        "provider": "openai-codex",
        "status": "error",
        "error_message": compact,
    }


def _bot_identity_answers(bot_platform: str, bot_identity: BotIdentity) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "bot_platform": bot_platform,
        "bot_id": bot_identity.bot_id,
        "bot_username": bot_identity.username,
        "bot_display_name": bot_identity.display_name,
    }
    if bot_platform == "telegram":
        payload["telegram_bot_id"] = bot_identity.bot_id
        payload["telegram_bot_username"] = bot_identity.username
    return payload


def begin_onboarding_provisioning(
    conn,
    cfg: Config,
    session: dict[str, Any],
    *,
    provider_secret_path: str,
) -> dict[str, Any]:
    if str(session.get("linked_request_id") or "").strip() and str(session.get("state") or "") == "provision-pending":
        return session

    answers = session.get("answers", {})
    bot_platform = _bot_platform_name(session)
    request = request_bootstrap(
        conn,
        cfg,
        requester_identity=_session_requester_identity(session),
        unix_user=str(answers.get("unix_user") or session.get("sender_id") or ""),
        source_ip=f"{session.get('platform') or 'chat'}:{session.get('sender_id') or 'unknown'}",
        tailnet_identity=None,
        issue_pending_token=False,
        auto_provision=True,
        requested_model_preset=str(answers.get("model_preset") or "codex"),
        requested_channels=[bot_platform],
        notify_operator=False,
    )
    approve_request(
        conn,
        request_id=str(request["request_id"]),
        surface="curator-channel",
        actor=str(session.get("approved_by_actor") or f"{session.get('platform') or 'chat'}-operator"),
        cfg=cfg,
    )
    save_kwargs: dict[str, Any] = {
        "session_id": str(session["session_id"]),
        "state": "provision-pending",
        "answers": {
            "pending_provider_secret_path": provider_secret_path,
            "provider_browser_auth": {},
        },
        "linked_request_id": str(request["request_id"]),
        "linked_agent_id": str(request.get("agent_id") or ""),
        "provision_error": "",
    }
    if bot_platform == "telegram":
        save_kwargs["telegram_bot_id"] = str(answers.get("bot_id") or "")
        save_kwargs["telegram_bot_username"] = str(answers.get("bot_username") or "")
    return save_onboarding_session(conn, **save_kwargs)


def _provisioning_started_reply(incoming: IncomingMessage, session: dict[str, Any]) -> OutboundMessage:
    bot_label = str(
        session.get("answers", {}).get("bot_username")
        or session.get("answers", {}).get("bot_display_name")
        or _preferred_bot_name(session)
    )
    unix_user = str(session.get("answers", {}).get("unix_user") or incoming.sender_id)
    if _bot_platform_name(session) == "discord":
        return OutboundMessage(
            incoming.chat_id,
            f"Good. I have what I need. I’m provisioning `{unix_user}` now and wiring `{bot_label}`. I’ll tell you when the lane is ready.",
        )
    return OutboundMessage(
        incoming.chat_id,
        f"Good. I have what I need. I’m provisioning `{unix_user}` now and wiring @{bot_label}. I’ll tell you when the lane is ready.",
    )


def _begin_org_provider_provisioning(conn, cfg: Config, incoming: IncomingMessage, session: dict[str, Any]) -> OutboundMessage:
    provider_setup = _provider_setup(session)
    if provider_setup is None:
        return OutboundMessage(incoming.chat_id, "I lost track of the provider setup for this session. Send /start and we’ll begin again.")
    provider_secret = _org_provider_secret()
    if not provider_secret:
        return OutboundMessage(
            incoming.chat_id,
            "The organization-provided model option is enabled, but its credential is missing. Ask the operator to rerun deploy setup and provide the org provider credential.",
        )
    provider_secret_path = write_onboarding_secret(
        cfg,
        str(session["session_id"]),
        provider_secret_name(provider_setup),
        provider_secret,
    )
    updated = save_onboarding_session(
        conn,
        session_id=str(session["session_id"]),
        answers={"pending_provider_secret_path": provider_secret_path},
    )
    updated = begin_onboarding_provisioning(conn, cfg, updated, provider_secret_path=provider_secret_path)
    return _provisioning_started_reply(incoming, updated)


def session_prompt(cfg: Config, session: dict[str, Any]) -> str:
    state = str(session.get("state") or "")
    answers = session.get("answers", {})
    preferred_bot_name = _preferred_bot_name(session)
    bot_platform = _bot_platform_name(session)
    provider_setup = _provider_setup(session)
    browser_auth = _provider_auth_state(session)
    if state == "awaiting-name":
        return (
            "Hi, I’m Almanac’s Curator. I’ll help get your private agent lane set up and keep the handoff tidy.\n\n"
            "First up: what should I call you?"
        )
    if state == "awaiting-profile-match":
        candidates = answers.get("org_profile_candidates") if isinstance(answers, dict) else []
        lines = [
            "I found prepared operating-profile entries that are not linked to a live agent yet.",
            "",
            "If one of these is you, reply with its number. Reply `none` to continue without linking a profile entry.",
            "",
        ]
        for index, candidate in enumerate(candidates if isinstance(candidates, list) else [], start=1):
            if isinstance(candidate, dict) and candidate.get("label"):
                lines.append(f"{index}. {candidate.get('label')}")
        lines.extend(
            [
                "",
                "This only orients your agent from the operator-authored profile. It is not identity verification, and it does not grant permissions by itself.",
            ]
        )
        return "\n".join(lines)
    if state == "awaiting-unix-user":
        suggested_unix_user = str(answers.get("org_profile_suggested_unix_user") or "").strip().lower()
        suggestion = ""
        if suggested_unix_user:
            available, _reason = desired_unix_user_available(suggested_unix_user)
            if available:
                suggestion = (
                    f"\n\nThe selected profile entry suggests `{suggested_unix_user}`. "
                    "Reply `default` to use it, or type any available username you prefer."
                )
        return (
            "Now let’s pick your host username.\n"
            "Almanac runs on a shared host. Each enrolled user gets a private Unix account, home directory, Hermes state, and code workspace.\n\n"
            "What Unix username should I create for you?\n"
            "Use lowercase letters, digits, `_`, or `-`; start with a letter or `_`."
            f"{suggestion}"
        )
    if state == "awaiting-purpose":
        return (
            "A little context helps me shape the agent properly.\n\n"
            "In a sentence or a short paragraph, what should this agent help you practice, build, or keep moving?"
        )
    if state == "awaiting-bot-platform":
        return "I can only wire the same platform you're onboarding from right now. Reply with `telegram` or `discord` to match this DM."
    if state == "awaiting-bot-name":
        return (
            f"Now name your {bot_platform or 'chat'} bot.\n"
            "This will be the bot you talk to after onboarding.\n\n"
            "What should it be called? A short plain-English name is perfect."
        )
    if state == "awaiting-model-preset":
        return (
            "Now let’s pick the model provider.\n"
            "Choose what should power this agent. Reply with the number or provider name.\n\n"
            f"{_model_options(cfg)}"
        )
    if state == "awaiting-model-id":
        model_preset = str(answers.get("model_preset") or "chutes").strip().lower() or "chutes"
        default_model = _default_model_id(cfg, model_preset) or CHUTES_DEFAULT_MODEL
        label = _model_provider_label(cfg, model_preset)
        if model_preset == "chutes":
            examples = "\n".join(f"- `{model}`" for model in _recommended_models(cfg, "chutes"))
            return (
                "Great, Chutes it is. Which model should this agent use?\n\n"
                f"Reply with a model id, or `default` for `{default_model}`.\n"
                "Good starting points:\n"
                f"{examples}\n\n"
                "I’ll wire Chutes through Hermes as an OpenAI-compatible provider at `https://llm.chutes.ai/v1`."
            )
        return (
            f"Which {label} model should this agent use?\n\n"
            f"Reply with a model id, or `default` for `{default_model}`."
        )
    if state == "awaiting-thinking-level":
        model_preset = str(answers.get("model_preset") or "").strip().lower()
        chutes_note = (
            "\n\nFor Chutes, any level except `none` enables Chutes thinking mode when the selected model supports it."
            if model_preset == "chutes"
            else ""
        )
        options = "\n".join(
            f"{index}. {effort} - {description}"
            for index, (effort, description) in enumerate(REASONING_EFFORT_OPTIONS, start=1)
        )
        return (
            "How much thinking room should this agent use by default?\n"
            "Pick the default reasoning depth for this agent. Reply with the number or name.\n\n"
            f"{options}"
            f"{chutes_note}"
        )
    if state == "awaiting-operator-approval":
        org_provider_note = _org_provider_selection_note(cfg, session)
        notified_at = str(session.get("operator_notified_at") or "").strip()
        waiting_note = ""
        if notified_at:
            try:
                queued_at = dt.datetime.fromisoformat(notified_at)
                if queued_at.tzinfo is None:
                    queued_at = queued_at.replace(tzinfo=dt.timezone.utc)
                if (dt.datetime.now(dt.timezone.utc) - queued_at) >= dt.timedelta(minutes=10):
                    waiting_note = " If this has been sitting for a while, ask the operator to check the onboarding queue and reply `/status` here any time."
            except ValueError:
                waiting_note = ""
        prefix = f"{org_provider_note}\n\n" if org_provider_note else ""
        return prefix + (
            "Thanks. I sent this onboarding request to the operator for approval.\n\n"
            "I’ll keep watch and continue here automatically once it is approved."
            + waiting_note
        )
    if state == "awaiting-bot-token":
        if bot_platform == "discord":
            return (
                "Approved. Next I need the Discord bot token for your private agent lane.\n\n"
                "Discord setup steps:\n"
                "1. Go to https://discord.com/developers/applications and click `New Application`.\n"
                f"2. Name the app `{preferred_bot_name}` or any bot name you prefer.\n"
                "3. Open the app’s `Bot` page.\n"
                "4. Turn `Message Content Intent` on.\n"
                "5. Click `Reset Token`, copy the bot token, and paste that token here.\n\n"
                "Important: send the token for the new agent bot only, not Curator’s Discord token. You do not need to add this bot to a server; after setup, Curator will show a confirmation code and the bot will DM you directly with the same code."
            )
        return (
            "Approved. Next I need the Telegram bot token for your private agent lane.\n\n"
            "Telegram setup steps:\n"
            "1. Open Telegram and message @BotFather.\n"
            "2. Send `/newbot`.\n"
            f"3. Give it the display name `{preferred_bot_name}` or any bot name you prefer.\n"
            "4. Choose a username that ends in `bot`.\n"
            "5. Copy the API token BotFather prints.\n"
            "6. Paste that token here.\n\n"
            "Important: send the token for the new agent bot only, not Curator’s Telegram token. After I receive it, I’ll ask for the model credential and finish the handoff."
        )
    if state == "awaiting-provider-credential" and provider_setup is not None:
        return provider_credential_prompt(
            provider_setup,
            shared_credential_available=_shared_provider_credential_available(provider_setup),
        )
    if state == "awaiting-provider-browser-auth" and provider_setup is not None:
        return provider_browser_auth_prompt(provider_setup, browser_auth)
    if state == "provision-pending":
        provision_error = str(session.get("provision_error") or "").strip()
        if provision_error:
            return (
                "I hit a provisioning problem while wiring your lane:\n"
                f"{provision_error}\n\n"
                "I’ve kept your session open so the operator can recover it cleanly. Reply `/status` here any time for the latest state."
            )
        return "Provisioning is underway. I’m creating your Unix lane, wiring Hermes, installing the agent services, and connecting your bot. This usually lands within a minute; I’ll ping you when it is ready."
    if state == "awaiting-agent-backup-repo":
        unix_user = str(answers.get("unix_user") or "").strip() or "your-user"
        bot_slug = re.sub(r"[^a-z0-9]+", "-", str(answers.get("preferred_bot_name") or answers.get("bot_display_name") or "agent").strip().lower()).strip("-") or "agent"
        example = f"{unix_user}/almanac-{bot_slug}"
        return (
            "Your agent lane is live. Next, let’s set up its private backup repo.\n\n"
            "Create or choose a private GitHub repository for this agent’s Hermes home. "
            "I’ll refuse public repositories, generate a separate per-user deploy key, and only activate the backup after GitHub proves the key has write access.\n\n"
            f"Reply with the GitHub `owner/repo` path, for example `{example}`.\n"
            "Reply `skip` to finish without the private agent backup for now."
        )
    if state == "agent-backup-prepare-pending":
        owner_repo = str(answers.get("agent_backup_owner_repo") or "").strip()
        suffix = f" for `{owner_repo}`" if owner_repo else ""
        return f"I queued the private backup key setup{suffix}. I’ll send the deploy key here once the host has prepared it."
    if state == "awaiting-agent-backup-key-install":
        owner_repo = str(answers.get("agent_backup_owner_repo") or "").strip()
        public_key = str(answers.get("agent_backup_public_key") or "").strip()
        settings_url = f"https://github.com/{owner_repo}/settings/keys" if owner_repo else "the repository deploy-key settings"
        lines = [
            "Private backup key is ready.",
            "",
            f"Repository: `{owner_repo}`" if owner_repo else "",
            f"Add this deploy key in GitHub: {settings_url}",
            "Enable `Allow write access`.",
            "",
            "Deploy key:",
            f"`{public_key}`" if public_key else "(the host prepared the key, but I could not read the public half; ask the operator to check the backup setup log)",
            "",
            "Reply `done` after the key is installed. I’ll re-check that the repo is not public and verify read plus dry-run write access before activating the Hermes cron backup job.",
            "Reply `skip` to finish without activating this backup now.",
        ]
        return "\n".join(line for line in lines if line)
    if state == "agent-backup-verify-pending":
        owner_repo = str(answers.get("agent_backup_owner_repo") or "").strip()
        suffix = f" for `{owner_repo}`" if owner_repo else ""
        return f"I’m verifying the private backup repo{suffix}: non-public visibility, deploy-key read access, and dry-run write access. I’ll continue automatically when that passes."
    if state == "awaiting-notion-access":
        shared_page_url = shared_notion_home_url().strip()
        lines = [
            "Your agent lane is live. Optional final step: shared Notion access.",
            "",
            "First, make sure you can open the shared Almanac page in this Notion workspace:",
        ]
        if shared_page_url:
            lines.append(shared_page_url)
        lines.append("")
        lines.append(
            "If Notion says `Request access`, tell the operator you need edit access to the shared Almanac page. "
            "On free Notion that usually means `Full access`, plus the operator may need to invite you into the workspace or teamspace first."
        )
        lines.append("")
        lines.append("Reply `ready` once you can open it. Reply `skip` to finish now with shared Notion writes disabled.")
        return "\n".join(lines)
    if state == "awaiting-notion-email":
        return (
            "Shared Notion verification, step 2 of 3.\n"
            "Reply with the Notion email you use in this organization’s workspace.\n\n"
            "Reply `skip` to finish now with shared Notion writes disabled."
        )
    if state == "awaiting-notion-verification":
        claim_url = str(answers.get("notion_claim_url") or "").strip()
        claimed_email = str(answers.get("notion_claim_email") or "").strip()
        expiry = str(answers.get("notion_claim_expires_at") or "").strip()
        expiry_note = ""
        if expiry:
            try:
                expires_at = dt.datetime.fromisoformat(expiry)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=dt.timezone.utc)
                expires_at_utc = expires_at.astimezone(dt.timezone.utc)
                if str(session.get("platform") or "").strip().lower() == "discord":
                    epoch = int(expires_at_utc.timestamp())
                    expiry_note = (
                        f" This claim expires <t:{epoch}:R> "
                        f"(<t:{epoch}:F> / {expires_at_utc.strftime('%Y-%m-%d %H:%M UTC')})."
                    )
                else:
                    expiry_note = f" This claim expires around {expires_at_utc.strftime('%Y-%m-%d %H:%M UTC')}."
            except ValueError:
                expiry_note = ""
        lines = [
            "Shared Notion verification, step 3 of 3.",
            "Open your Almanac verification page in Notion and make any small edit there. A keystroke or property change is enough.",
        ]
        if claim_url:
            lines.append(claim_url)
        if claimed_email:
            lines.append(f"I’m watching for an edit from `{claimed_email}` and will finish automatically once it lands.{expiry_note}")
        else:
            lines.append("I’m watching for your verification edit and will finish automatically once it lands." + expiry_note)
        lines.append(
            "If Notion says `Request access`, tell the operator you need edit access to the shared Almanac page. "
            "On free Notion that usually means `Full access`. Once they fix it, reply `/verify-notion` here to reissue the claim."
        )
        lines.append("If you want to finish now and leave shared Notion writes disabled, reply `skip`.")
        return "\n".join(lines)
    if state == "denied":
        reason = str(session.get("denial_reason") or "").strip()
        return (
            f"The operator declined this onboarding request: {reason}"
            if reason
            else "The operator declined this onboarding request."
        )
    if state == "completed":
        bot_username = str(answers.get("bot_username") or session.get("telegram_bot_username") or "").strip()
        if bot_platform == "discord" and bot_username:
            return (
                f"Your agent lane is live through the Discord bot `{bot_username}`. "
                "It already has the Almanac skills active by default, plus the shared Vault/qmd wiring. "
                "Curator will show a confirmation code before that bot DMs you directly; use the bot DM from here on out when the codes match."
            )
        if bot_platform == "telegram" and bot_username:
            return (
                f"Your agent lane is live at @{bot_username}. "
                "It already has the Almanac skills active by default, plus the shared Vault/qmd wiring. "
                f"Tap @{bot_username}, press Start, and use that bot chat from here on out."
            )
        return "Your agent lane is live. It already has the Almanac skills active by default, plus the shared Vault/qmd wiring."
    return "Send /start when you want to begin onboarding."


def _requester_identity(incoming: IncomingMessage, session: dict[str, Any]) -> str:
    answers = session.get("answers", {})
    return format_user_label(
        incoming.platform,
        incoming.sender_username,
        incoming.sender_display_name or str(answers.get("full_name") or ""),
        incoming.sender_id,
    )


def _status_or_cancel(
    cfg: Config,
    conn,
    session: dict[str, Any],
    incoming: IncomingMessage,
) -> tuple[dict[str, Any] | None, list[OutboundMessage] | None]:
    normalized = incoming.text.strip().lower()
    if normalized in STATUS_COMMANDS:
        return session, [_session_prompt_reply(cfg, incoming, session)]
    if normalized in CANCEL_COMMANDS:
        if onboarding_session_has_started_provisioning(session):
            request_id = str(session.get("linked_request_id") or "").strip()
            detail = (
                f" Ask an operator to cancel request `{request_id}` if provisioning has not started yet, "
                "or purge the enrollment after the lane is live."
                if request_id
                else " Ask an operator to use the enrollment purge flow if you still want this removed."
            )
            return session, [
                OutboundMessage(
                    incoming.chat_id,
                    "I have already started provisioning your lane, so I cannot wipe this clean from chat anymore."
                    + detail,
                )
            ]
        updated = cancel_onboarding_session(conn, cfg, session_id=str(session["session_id"]))
        return updated, [
            OutboundMessage(
                incoming.chat_id,
                f"Cancelled {updated['session_id']}. I wiped the staged onboarding state. Send /start when you want to try again.",
            )
        ]
    return None, None


def _completion_reply_for_session(
    conn,
    cfg: Config,
    session: dict[str, Any],
    *,
    fallback_text: str,
) -> list[OutboundMessage]:
    from almanac_onboarding_completion import completion_bundle_for_session

    bundle = completion_bundle_for_session(conn, cfg, session)
    if bundle is None:
        return [OutboundMessage(session["chat_id"], fallback_text)]
    return [
        OutboundMessage(
            str(session.get("chat_id") or ""),
            str(bundle.get("full_text") or fallback_text),
            telegram_reply_markup=bundle.get("telegram_reply_markup"),
            telegram_parse_mode=str(bundle.get("telegram_parse_mode") or ""),
            discord_components=bundle.get("discord_components"),
        )
    ]


def _resume_verify_notion_session(
    conn,
    cfg: Config,
    incoming: IncomingMessage,
) -> list[OutboundMessage]:
    session = find_latest_onboarding_session_for_sender(
        conn,
        platform=incoming.platform,
        sender_id=incoming.sender_id,
        redact_secrets=False,
    )
    if session is None or not str(session.get("linked_agent_id") or "").strip():
        return [OutboundMessage(incoming.chat_id, "Send /start when you want Curator to open an onboarding session.")]
    updated = save_onboarding_session(
        conn,
        session_id=str(session["session_id"]),
        state="awaiting-notion-access",
        chat_id=incoming.chat_id,
        sender_username=incoming.sender_username,
        sender_display_name=incoming.sender_display_name or str(session.get("sender_display_name") or ""),
        completed_at="",
        last_prompt_at=utc_now_iso(),
    )
    return [_session_prompt_reply(cfg, incoming, updated)]


def _advance_after_agent_backup_from_chat(conn, cfg: Config, incoming: IncomingMessage, session: dict[str, Any]) -> list[OutboundMessage]:
    answers = session.get("answers", {}) if isinstance(session.get("answers"), dict) else {}
    if str(answers.get("agent_backup_next_phase") or "").strip() == "completed":
        updated = save_onboarding_session(
            conn,
            session_id=str(session["session_id"]),
            state="completed",
            completed_at=utc_now_iso(),
        )
        return [OutboundMessage(incoming.chat_id, "Okay. I left the private agent backup inactive. Reply `/setup-backup` here any time to try again.")]
    if shared_notion_self_serve_configured():
        updated = save_onboarding_session(
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
        return [_session_prompt_reply(cfg, incoming, updated)]
    updated = save_onboarding_session(
        conn,
        session_id=str(session["session_id"]),
        state="completed",
        completed_at=utc_now_iso(),
    )
    return _completion_reply_for_session(
        conn,
        cfg,
        updated,
        fallback_text="Your lane is ready. The private agent backup can be set up later with `/setup-backup`.",
    )


def process_onboarding_message(
    cfg: Config,
    incoming: IncomingMessage,
    *,
    validate_bot_token: BotTokenValidator,
) -> list[OutboundMessage]:
    text = incoming.text.strip()
    lower = text.lower()
    with connect_db(cfg) as conn:
        if lower in START_COMMANDS:
            try:
                session = start_onboarding_session(
                    conn,
                    cfg,
                    platform=incoming.platform,
                    chat_id=incoming.chat_id,
                    sender_id=incoming.sender_id,
                    sender_username=incoming.sender_username,
                    sender_display_name=incoming.sender_display_name,
                )
            except RateLimitError as exc:
                return [OutboundMessage(incoming.chat_id, f"Slow down a bit. Try again in about {exc.retry_after_seconds}s.")]
            session = _maybe_stage_profile_match_prompt(conn, cfg, incoming, session)
            return [_session_prompt_reply(cfg, incoming, session, incoming.reply_to_message_id)]

        is_remote_ssh_key, remote_ssh_pubkey = _extract_remote_ssh_pubkey(text)
        if is_remote_ssh_key:
            return _queue_remote_ssh_key_install(conn, cfg, incoming, pubkey=remote_ssh_pubkey)
        if lower in SETUP_BACKUP_COMMANDS:
            return _resume_agent_backup_session(conn, cfg, incoming)

        session = find_active_onboarding_session(conn, platform=incoming.platform, sender_id=incoming.sender_id)
        if session is None and lower in VERIFY_NOTION_COMMANDS:
            return _resume_verify_notion_session(conn, cfg, incoming)
        if session is None:
            return [OutboundMessage(incoming.chat_id, "Send /start when you want Curator to open an onboarding session.")]

        _, early_messages = _status_or_cancel(cfg, conn, session, incoming)
        if early_messages is not None:
            return early_messages

        state = str(session.get("state") or "")
        if state == "awaiting-name":
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-purpose",
                answers={"full_name": text},
                chat_id=incoming.chat_id,
                sender_username=incoming.sender_username,
                sender_display_name=incoming.sender_display_name or text,
            )
            updated = _maybe_stage_profile_match_prompt(conn, cfg, incoming, updated)
            return [_session_prompt_reply(cfg, incoming, updated)]

        if state == "awaiting-profile-match":
            answers = session.get("answers", {}) if isinstance(session.get("answers"), dict) else {}
            candidates = answers.get("org_profile_candidates") if isinstance(answers.get("org_profile_candidates"), list) else []
            if lower in {"none", "no", "skip", "not me", "notme"}:
                updated = save_onboarding_session(
                    conn,
                    session_id=str(session["session_id"]),
                    state="awaiting-purpose",
                    answers={
                        "org_profile_match_status": "skipped",
                        "org_profile_person_id": "",
                        "org_profile_person_label": "",
                        "org_profile_suggested_unix_user": "",
                    },
                )
                return [_session_prompt_reply(cfg, incoming, updated)]
            selected: dict[str, Any] | None = None
            if lower.isdigit():
                index = int(lower) - 1
                if 0 <= index < len(candidates) and isinstance(candidates[index], dict):
                    selected = candidates[index]
            if selected is None:
                for candidate in candidates:
                    if isinstance(candidate, dict) and str(candidate.get("id") or "").strip().lower() == lower:
                        selected = candidate
                        break
            if selected is None:
                return [
                    OutboundMessage(
                        incoming.chat_id,
                        "Reply with one of the listed numbers, or `none` to continue without linking a profile entry.",
                    )
                ]
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-purpose",
                answers={
                    "org_profile_match_status": "user_selected_unverified",
                    "org_profile_person_id": str(selected.get("id") or ""),
                    "org_profile_person_label": str(selected.get("label") or ""),
                    "org_profile_suggested_unix_user": str(selected.get("suggested_unix_user") or ""),
                },
            )
            return [_session_prompt_reply(cfg, incoming, updated)]

        if state == "awaiting-unix-user":
            answers = session.get("answers", {}) if isinstance(session.get("answers"), dict) else {}
            suggested_unix_user = str(answers.get("org_profile_suggested_unix_user") or "").strip().lower()
            if lower in {"default", "suggested", "use default", "use suggested"} and suggested_unix_user:
                candidate = suggested_unix_user
            else:
                candidate = text.lower()
            ok, reason = desired_unix_user_available(candidate)
            if not ok:
                return [OutboundMessage(incoming.chat_id, reason)]
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-bot-name",
                answers={
                    "unix_user": candidate,
                    "bot_platform": incoming.platform,
                },
                chat_id=incoming.chat_id,
                sender_username=incoming.sender_username,
                sender_display_name=incoming.sender_display_name,
            )
            return [_session_prompt_reply(cfg, incoming, updated)]

        if state == "awaiting-purpose":
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-unix-user",
                answers={"purpose": text},
            )
            return [_session_prompt_reply(cfg, incoming, updated)]

        if state == "awaiting-bot-platform":
            bot_platform = _parse_platform_choice(text)
            if not bot_platform:
                return [OutboundMessage(incoming.chat_id, "Please answer with `telegram` or `discord`.")]
            if bot_platform != incoming.platform:
                return [
                    OutboundMessage(
                        incoming.chat_id,
                        (
                            "For now, choose the same platform you’re onboarding from. "
                            "That lets me lock your private DM identity correctly before I hand you off."
                        ),
                    )
                ]
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-bot-name",
                answers={"bot_platform": bot_platform},
            )
            return [_session_prompt_reply(cfg, incoming, updated)]

        if state == "awaiting-bot-name":
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-model-preset",
                answers={"preferred_bot_name": text},
            )
            return [_session_prompt_reply(cfg, incoming, updated)]

        if state == "awaiting-model-preset":
            model_preset = _parse_model_preset(cfg, text)
            if not model_preset:
                return [OutboundMessage(incoming.chat_id, "Choose one of these providers:\n" + _model_options(cfg))]
            if model_preset == ORG_PROVIDED_PRESET:
                updated = save_onboarding_session(
                    conn,
                    session_id=str(session["session_id"]),
                    state="awaiting-operator-approval",
                    answers={
                        "model_preset": model_preset,
                        "model_id": _default_model_id(cfg, model_preset),
                        "reasoning_effort": _org_provider_reasoning_effort(cfg),
                    },
                )
                if not updated.get("operator_notified_at"):
                    _notify_operator(conn, cfg, updated)
                    updated = save_onboarding_session(
                        conn,
                        session_id=str(session["session_id"]),
                        operator_notified_at=utc_now_iso(),
                    )
                return [_session_prompt_reply(cfg, incoming, updated)]
            next_state = "awaiting-thinking-level"
            answers_update: dict[str, Any] = {"model_preset": model_preset}
            if model_preset == "chutes":
                next_state = "awaiting-model-id"
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state=next_state,
                answers=answers_update,
            )
            return [_session_prompt_reply(cfg, incoming, updated)]

        if state == "awaiting-model-id":
            answers = session.get("answers", {})
            model_preset = str(answers.get("model_preset") or "chutes").strip().lower() or "chutes"
            model_id, reason = _parse_model_id(cfg, model_preset, text)
            if not model_id:
                return [
                    OutboundMessage(
                        incoming.chat_id,
                        reason or session_prompt(cfg, session),
                        telegram_parse_mode=session_prompt_telegram_parse_mode(session),
                    )
                ]
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-thinking-level",
                answers={"model_id": model_id},
            )
            return [_session_prompt_reply(cfg, incoming, updated)]

        if state == "awaiting-thinking-level":
            reasoning_effort = _parse_reasoning_effort(text)
            if not reasoning_effort:
                return [_session_prompt_reply(cfg, incoming, session)]
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-operator-approval",
                answers={"reasoning_effort": reasoning_effort},
            )
            if not updated.get("operator_notified_at"):
                _notify_operator(conn, cfg, updated)
                updated = save_onboarding_session(
                    conn,
                    session_id=str(session["session_id"]),
                    operator_notified_at=utc_now_iso(),
                )
            return [_session_prompt_reply(cfg, incoming, updated)]

        if state == "awaiting-operator-approval":
            return [_session_prompt_reply(cfg, incoming, session)]

        if state == "awaiting-bot-token":
            bot_platform = _bot_platform_name(session)
            try:
                bot_identity = validate_bot_token(text)
            except Exception as exc:  # noqa: BLE001
                return [OutboundMessage(incoming.chat_id, str(exc).strip() or "That token was rejected.")]
            answers = session.get("answers", {})
            try:
                pending_bot_token_path = write_onboarding_platform_token_secret(
                    cfg,
                    str(session["session_id"]),
                    bot_platform,
                    text,
                )
                provider_setup = resolve_provider_setup(
                    cfg,
                    str(answers.get("model_preset") or "codex"),
                    model_id=str(answers.get("model_id") or ""),
                    reasoning_effort=str(answers.get("reasoning_effort") or ""),
                )
            except Exception as exc:  # noqa: BLE001
                return [OutboundMessage(incoming.chat_id, f"I couldn't continue onboarding yet: {exc}")]

            extra_answers = _bot_identity_answers(bot_platform, bot_identity)
            extra_answers["provider_setup"] = provider_setup.as_dict()
            save_kwargs: dict[str, Any] = {
                "session_id": str(session["session_id"]),
                "state": "awaiting-provider-credential",
                "answers": extra_answers,
                "pending_bot_token": "",
                "pending_bot_token_path": pending_bot_token_path,
                "provision_error": "",
            }
            if bot_platform == "telegram":
                save_kwargs["telegram_bot_id"] = bot_identity.bot_id
                save_kwargs["telegram_bot_username"] = bot_identity.username
            updated = save_onboarding_session(conn, **save_kwargs)
            if str(answers.get("model_preset") or "").strip().lower() == ORG_PROVIDED_PRESET:
                try:
                    return [_begin_org_provider_provisioning(conn, cfg, incoming, updated)]
                except Exception as exc:  # noqa: BLE001
                    return [OutboundMessage(incoming.chat_id, str(exc).strip() or "That organization provider credential could not be staged.")]
            if provider_setup.auth_flow == "codex-device":
                try:
                    auth_state = start_codex_device_authorization()
                except Exception as exc:  # noqa: BLE001
                    updated = save_onboarding_session(
                        conn,
                        session_id=str(session["session_id"]),
                        state="awaiting-provider-browser-auth",
                        answers={"provider_browser_auth": _codex_browser_auth_error_state(str(exc))},
                        provision_error=str(exc).strip() or "failed to mint OpenAI Codex sign-in code",
                    )
                    return [_session_prompt_reply(cfg, incoming, updated)]
                updated = save_onboarding_session(
                    conn,
                    session_id=str(session["session_id"]),
                    state="awaiting-provider-browser-auth",
                    answers={"provider_browser_auth": auth_state},
                    provision_error="",
                )
            elif provider_setup.auth_flow == "anthropic-credential":
                try:
                    auth_state = start_anthropic_pkce_authorization()
                    updated = save_onboarding_session(
                        conn,
                        session_id=str(session["session_id"]),
                        state="awaiting-provider-browser-auth",
                        answers={"provider_browser_auth": auth_state},
                        provision_error="",
                    )
                except Exception as exc:  # noqa: BLE001
                    return [OutboundMessage(incoming.chat_id, f"I couldn't start the Claude authorization flow: {exc}")]
            return [_session_prompt_reply(cfg, incoming, updated)]

        if state == "awaiting-provider-credential":
            provider_setup = _provider_setup(session)
            if provider_setup is None:
                return [OutboundMessage(incoming.chat_id, "I lost track of the provider setup for this session. Send /start and we’ll begin again.")]
            if provider_setup.auth_flow == "codex-device":
                try:
                    updated = save_onboarding_session(
                        conn,
                        session_id=str(session["session_id"]),
                        state="awaiting-provider-browser-auth",
                        answers={"provider_browser_auth": start_codex_device_authorization()},
                        provision_error="",
                    )
                except Exception as exc:  # noqa: BLE001
                    updated = save_onboarding_session(
                        conn,
                        session_id=str(session["session_id"]),
                        state="awaiting-provider-browser-auth",
                        answers={"provider_browser_auth": _codex_browser_auth_error_state(str(exc))},
                        provision_error=str(exc).strip() or "failed to mint OpenAI Codex sign-in code",
                    )
                return [_session_prompt_reply(cfg, incoming, updated)]
            try:
                if provider_setup.provider_id == "anthropic":
                    if lower in {"oauth", "/oauth", "browser"}:
                        updated = save_onboarding_session(
                            conn,
                            session_id=str(session["session_id"]),
                            state="awaiting-provider-browser-auth",
                            answers={"provider_browser_auth": start_anthropic_pkce_authorization()},
                        )
                        return [_session_prompt_reply(cfg, incoming, updated)]
                    return [
                        OutboundMessage(
                            incoming.chat_id,
                            "Claude Opus onboarding here is OAuth-only. Reply `oauth` and I’ll open the Claude Code OAuth flow.",
                        )
                    ]
                shared_provider_secret = _shared_provider_secret(provider_setup)
                if shared_provider_secret and lower in {
                    "",
                    "default",
                    "/default",
                    "team",
                    "team key",
                    "shared",
                    "shared key",
                    "use team key",
                    "use shared key",
                }:
                    provider_secret = shared_provider_secret
                else:
                    provider_secret = normalize_api_key_credential(provider_setup, text)
                provider_secret_path = write_onboarding_secret(
                    cfg,
                    str(session["session_id"]),
                    provider_secret_name(provider_setup),
                    provider_secret,
                )
                updated = save_onboarding_session(
                    conn,
                    session_id=str(session["session_id"]),
                    answers={"pending_provider_secret_path": provider_secret_path},
                )
                updated = begin_onboarding_provisioning(conn, cfg, updated, provider_secret_path=provider_secret_path)
            except Exception as exc:  # noqa: BLE001
                return [OutboundMessage(incoming.chat_id, str(exc).strip() or "That credential was rejected.")]

            bot_label = str(updated.get("answers", {}).get("bot_username") or updated.get("answers", {}).get("bot_display_name") or _preferred_bot_name(updated))
            unix_user = str(updated.get("answers", {}).get("unix_user") or incoming.sender_id)
            if _bot_platform_name(updated) == "discord":
                return [OutboundMessage(incoming.chat_id, f"Good. I have what I need. I’m provisioning `{unix_user}` now and wiring `{bot_label}`. I’ll tell you when the lane is ready.")]
            return [OutboundMessage(incoming.chat_id, f"Good. I have what I need. I’m provisioning `{unix_user}` now and wiring @{bot_label}. I’ll tell you when the lane is ready.")]

        if state == "awaiting-provider-browser-auth":
            provider_setup = _provider_setup(session)
            if provider_setup is None:
                return [OutboundMessage(incoming.chat_id, "I lost track of the provider setup for this session. Send /start and we’ll begin again.")]
            if lower in {"restart", "/restart"} and provider_setup.auth_flow == "codex-device":
                try:
                    auth_state = start_codex_device_authorization()
                    updated = save_onboarding_session(
                        conn,
                        session_id=str(session["session_id"]),
                        answers={"provider_browser_auth": auth_state},
                        provision_error="",
                    )
                except Exception as exc:  # noqa: BLE001
                    updated = save_onboarding_session(
                        conn,
                        session_id=str(session["session_id"]),
                        answers={"provider_browser_auth": _codex_browser_auth_error_state(str(exc))},
                        provision_error=str(exc).strip() or "failed to mint OpenAI Codex sign-in code",
                    )
                return [_session_prompt_reply(cfg, incoming, updated)]
            if provider_setup.provider_id != "anthropic":
                return [_session_prompt_reply(cfg, incoming, session)]
            try:
                if lower in {"restart", "/restart"}:
                    updated = save_onboarding_session(
                        conn,
                        session_id=str(session["session_id"]),
                        answers={"provider_browser_auth": start_anthropic_pkce_authorization()},
                        provision_error="",
                    )
                    return [_session_prompt_reply(cfg, incoming, updated)]
                stripped = text.strip()
                if stripped.startswith("sk-ant-api-") or stripped.startswith("sk-ant-oat-"):
                    return [
                        OutboundMessage(
                            incoming.chat_id,
                            "Claude Opus onboarding here uses browser OAuth tied to the user's Claude account. Please finish the link flow instead of pasting an Anthropic token.",
                        )
                    ]
                provider_secret, auth_state = complete_anthropic_pkce_authorization(_provider_auth_state(session), text)
                provider_secret_path = write_onboarding_secret(
                    cfg,
                    str(session["session_id"]),
                    provider_secret_name(provider_setup),
                    provider_secret,
                )
                updated = save_onboarding_session(
                    conn,
                    session_id=str(session["session_id"]),
                    answers={
                        "provider_browser_auth": auth_state,
                        "pending_provider_secret_path": provider_secret_path,
                    },
                )
                updated = begin_onboarding_provisioning(conn, cfg, updated, provider_secret_path=provider_secret_path)
            except Exception as exc:  # noqa: BLE001
                return [OutboundMessage(incoming.chat_id, str(exc).strip() or "That Claude authorization code was rejected.")]

            bot_label = str(updated.get("answers", {}).get("bot_username") or updated.get("answers", {}).get("bot_display_name") or _preferred_bot_name(updated))
            unix_user = str(updated.get("answers", {}).get("unix_user") or incoming.sender_id)
            if _bot_platform_name(updated) == "discord":
                return [OutboundMessage(incoming.chat_id, f"Good. I have what I need. I’m provisioning `{unix_user}` now and wiring `{bot_label}`. I’ll tell you when the lane is ready.")]
            return [OutboundMessage(incoming.chat_id, f"Good. I have what I need. I’m provisioning `{unix_user}` now and wiring @{bot_label}. I’ll tell you when the lane is ready.")]

        if state == "awaiting-agent-backup-repo":
            if lower == "skip":
                updated = save_onboarding_session(
                    conn,
                    session_id=str(session["session_id"]),
                    answers={"agent_backup_skipped": True},
                )
                return _advance_after_agent_backup_from_chat(conn, cfg, incoming, updated)
            owner_repo, reason = _parse_github_owner_repo(text)
            if not owner_repo:
                return [OutboundMessage(incoming.chat_id, reason or session_prompt(cfg, session))]
            agent, agent_reason = _agent_for_completed_session(conn, session)
            if agent is None:
                return [OutboundMessage(incoming.chat_id, agent_reason)]
            action, created = _queue_agent_backup_action(
                conn,
                incoming,
                session,
                agent,
                owner_repo=owner_repo,
                phase="prepare",
            )
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="agent-backup-prepare-pending",
                answers={
                    "agent_backup_owner_repo": owner_repo,
                    "agent_backup_remote": _github_ssh_remote(owner_repo),
                    "agent_backup_prepare_action_id": int(action.get("id") or 0),
                    "agent_backup_public_key": "",
                    "agent_backup_skipped": False,
                },
            )
            queued = "queued" if created else "already queued"
            return [
                OutboundMessage(
                    incoming.chat_id,
                    f"Private backup setup {queued} for `{owner_repo}`. I’ll send the deploy key here once the host prepares it.",
                ),
                _session_prompt_reply(cfg, incoming, updated),
            ]

        if state == "agent-backup-prepare-pending":
            return [_session_prompt_reply(cfg, incoming, session)]

        if state == "awaiting-agent-backup-key-install":
            if lower == "skip":
                updated = save_onboarding_session(
                    conn,
                    session_id=str(session["session_id"]),
                    answers={"agent_backup_skipped": True},
                )
                return _advance_after_agent_backup_from_chat(conn, cfg, incoming, updated)
            if lower not in {"done", "ready", "completed", "complete", "installed", "ok", "okay"}:
                return [_session_prompt_reply(cfg, incoming, session)]
            owner_repo = str((session.get("answers") or {}).get("agent_backup_owner_repo") or "").strip()
            if not owner_repo:
                return [OutboundMessage(incoming.chat_id, "I lost the backup repo path. Reply with the GitHub `owner/repo` path again.")]
            agent, agent_reason = _agent_for_completed_session(conn, session)
            if agent is None:
                return [OutboundMessage(incoming.chat_id, agent_reason)]
            action, created = _queue_agent_backup_action(
                conn,
                incoming,
                session,
                agent,
                owner_repo=owner_repo,
                phase="verify",
            )
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="agent-backup-verify-pending",
                answers={"agent_backup_verify_action_id": int(action.get("id") or 0)},
            )
            queued = "queued" if created else "already queued"
            return [
                OutboundMessage(incoming.chat_id, f"Backup verification {queued}. I’ll check the repo and key from the host now."),
                _session_prompt_reply(cfg, incoming, updated),
            ]

        if state == "agent-backup-verify-pending":
            return [_session_prompt_reply(cfg, incoming, session)]

        if state == "awaiting-notion-access":
            if lower == "skip":
                updated = save_onboarding_session(
                    conn,
                    session_id=str(session["session_id"]),
                    state="completed",
                    answers={
                        "notion_verification_skipped": True,
                        "notion_claim_email": "",
                        "notion_claim_id": "",
                        "notion_claim_url": "",
                        "notion_claim_expires_at": "",
                    },
                    completed_at=utc_now_iso(),
                )
                return _completion_reply_for_session(
                    conn,
                    cfg,
                    updated,
                    fallback_text=(
                        "Your lane is ready. Shared Notion writes stay read-only until you reply "
                        "`/verify-notion` here and finish the claim."
                    ),
                )
            if lower in NOTION_READY_COMMANDS:
                answers = session.get("answers", {})
                agent_id = str(session.get("linked_agent_id") or "").strip()
                unix_user = str(answers.get("unix_user") or "").strip()
                claimed_email = str(answers.get("notion_claim_email") or "").strip()
                if claimed_email and agent_id and unix_user:
                    try:
                        claim = start_notion_identity_claim(
                            conn,
                            session_id=str(session["session_id"]),
                            agent_id=agent_id,
                            unix_user=unix_user,
                            claimed_notion_email=claimed_email,
                        )
                    except Exception as exc:  # noqa: BLE001
                        return [OutboundMessage(incoming.chat_id, str(exc).strip() or "I couldn't restart Notion verification yet.")]
                    updated = save_onboarding_session(
                        conn,
                        session_id=str(session["session_id"]),
                        state="awaiting-notion-verification",
                        answers={
                            "notion_verification_skipped": False,
                            "notion_claim_email": str(claim.get("claimed_notion_email") or claimed_email),
                            "notion_claim_id": str(claim.get("claim_id") or ""),
                            "notion_claim_url": str(claim.get("notion_page_url") or ""),
                            "notion_claim_expires_at": str(claim.get("expires_at") or ""),
                        },
                    )
                    return [
                        OutboundMessage(
                            incoming.chat_id,
                            "Great. I opened a fresh Notion verification page for you.\n\n" + session_prompt(cfg, updated),
                        )
                    ]
                updated = save_onboarding_session(
                    conn,
                    session_id=str(session["session_id"]),
                    state="awaiting-notion-email",
                    answers={
                        "notion_verification_skipped": False,
                        "notion_claim_id": "",
                        "notion_claim_url": "",
                        "notion_claim_expires_at": "",
                    },
                )
                return [_session_prompt_reply(cfg, incoming, updated)]

        if state == "awaiting-notion-email":
            if lower in NOTION_READY_COMMANDS:
                return [_session_prompt_reply(cfg, incoming, session)]
            if lower == "skip":
                updated = save_onboarding_session(
                    conn,
                    session_id=str(session["session_id"]),
                    state="completed",
                    answers={
                        "notion_verification_skipped": True,
                        "notion_claim_email": "",
                        "notion_claim_id": "",
                        "notion_claim_url": "",
                        "notion_claim_expires_at": "",
                    },
                    completed_at=utc_now_iso(),
                )
                return _completion_reply_for_session(
                    conn,
                    cfg,
                    updated,
                    fallback_text=(
                        "Your lane is ready. Shared Notion writes stay read-only until you reply "
                        "`/verify-notion` here and finish the claim."
                    ),
                )
            agent_id = str(session.get("linked_agent_id") or "").strip()
            answers = session.get("answers", {})
            unix_user = str(answers.get("unix_user") or "").strip()
            if not agent_id or not unix_user:
                return [OutboundMessage(incoming.chat_id, "I lost track of your lane details. Send /start and I’ll re-open onboarding cleanly.")]
            try:
                claim = start_notion_identity_claim(
                    conn,
                    session_id=str(session["session_id"]),
                    agent_id=agent_id,
                    unix_user=unix_user,
                    claimed_notion_email=text,
                )
            except Exception as exc:  # noqa: BLE001
                return [OutboundMessage(incoming.chat_id, str(exc).strip() or "I couldn't start Notion verification yet.")]
            updated = save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-notion-verification",
                answers={
                    "notion_verification_skipped": False,
                    "notion_claim_email": str(claim.get("claimed_notion_email") or ""),
                    "notion_claim_id": str(claim.get("claim_id") or ""),
                    "notion_claim_url": str(claim.get("notion_page_url") or ""),
                    "notion_claim_expires_at": str(claim.get("expires_at") or ""),
                },
            )
            return [_session_prompt_reply(cfg, incoming, updated)]

        if state == "awaiting-notion-verification":
            if lower == "skip":
                claim_id = str((session.get("answers") or {}).get("notion_claim_id") or "").strip()
                if claim_id:
                    try:
                        from almanac_control import mark_notion_identity_claim

                        mark_notion_identity_claim(
                            conn,
                            claim_id=claim_id,
                            status="skipped",
                            failure_reason="user skipped self-serve notion verification during onboarding",
                        )
                    except Exception:
                        pass
                updated = save_onboarding_session(
                    conn,
                    session_id=str(session["session_id"]),
                    state="completed",
                    answers={"notion_verification_skipped": True},
                    completed_at=utc_now_iso(),
                )
                return _completion_reply_for_session(
                    conn,
                    cfg,
                    updated,
                    fallback_text=(
                        "Your lane is ready. Shared Notion writes stay read-only until you reply "
                        "`/verify-notion` here and finish the claim."
                    ),
                )
            if lower in VERIFY_NOTION_COMMANDS:
                claimed_email = str((session.get("answers") or {}).get("notion_claim_email") or "").strip()
                agent_id = str(session.get("linked_agent_id") or "").strip()
                unix_user = str((session.get("answers") or {}).get("unix_user") or "").strip()
                if claimed_email and agent_id and unix_user:
                    try:
                        claim = start_notion_identity_claim(
                            conn,
                            session_id=str(session["session_id"]),
                            agent_id=agent_id,
                            unix_user=unix_user,
                            claimed_notion_email=claimed_email,
                        )
                    except Exception as exc:  # noqa: BLE001
                        return [OutboundMessage(incoming.chat_id, str(exc).strip() or "I couldn't restart Notion verification yet.")]
                    updated = save_onboarding_session(
                        conn,
                        session_id=str(session["session_id"]),
                        state="awaiting-notion-verification",
                        answers={
                            "notion_verification_skipped": False,
                            "notion_claim_email": str(claim.get("claimed_notion_email") or claimed_email),
                            "notion_claim_id": str(claim.get("claim_id") or ""),
                            "notion_claim_url": str(claim.get("notion_page_url") or ""),
                            "notion_claim_expires_at": str(claim.get("expires_at") or ""),
                        },
                    )
                    return [
                        OutboundMessage(
                            incoming.chat_id,
                            "I opened a fresh Notion verification page for you.\n\n" + session_prompt(cfg, updated),
                        )
                    ]
                updated = save_onboarding_session(
                    conn,
                    session_id=str(session["session_id"]),
                    state="awaiting-notion-email",
                    answers={
                        "notion_verification_skipped": False,
                        "notion_claim_id": "",
                        "notion_claim_url": "",
                        "notion_claim_expires_at": "",
                    },
                )
                return [_session_prompt_reply(cfg, incoming, updated)]
            if lower == "status":
                claim_id = str((session.get("answers") or {}).get("notion_claim_id") or "").strip()
                claim = get_notion_identity_claim(conn, claim_id=claim_id) if claim_id else None
                if claim is not None and str(claim.get("status") or "").strip() == "expired":
                    updated = save_onboarding_session(
                        conn,
                        session_id=str(session["session_id"]),
                        state="awaiting-notion-access",
                        answers={
                            "notion_verification_skipped": False,
                            "notion_claim_email": "",
                            "notion_claim_id": "",
                            "notion_claim_url": "",
                            "notion_claim_expires_at": "",
                        },
                    )
                    return [
                        OutboundMessage(
                            incoming.chat_id,
                            "That verification link expired, so I opened a fresh claim step for you.\n\n"
                            + session_prompt(cfg, updated),
                        )
                    ]
            return [_session_prompt_reply(cfg, incoming, session)]

        return [_session_prompt_reply(cfg, incoming, session)]
