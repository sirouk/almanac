#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import os
import re
import secrets
import sqlite3
from typing import Any, Mapping
from urllib.parse import urlencode

from arclink_api_auth import (
    ARCLINK_CREDENTIAL_HANDOFF_TTL_SECONDS,
    accept_share_grant_for_recipient,
    check_arclink_rate_limit,
    _dashboard_password_ref_for_handoff,
    expire_revealable_user_material,
    queue_share_grant_recipient_notification,
    _resolve_revealable_credential_secret,
    _stable_handoff_id,
)
from arclink_adapters import arclink_access_urls
from arclink_boundary import json_dumps_safe, json_loads_safe
from arclink_control import (
    arclink_refuel_topup_options,
    append_arclink_audit,
    append_arclink_event,
    quote_arclink_refuel_topup,
    queue_notification,
    utc_after_seconds_iso,
    utc_now_iso,
)
from arclink_crew_recipes import (
    ArcLinkCrewRecipeError,
    apply_crew_recipe,
    crew_academy_status,
    preview_crew_recipe,
    skip_crew_academy_agent_training,
    stage_crew_academy_agent_training,
    whats_changed,
)
from arclink_onboarding import (
    ARCLINK_ONBOARDING_ACTIVE_STATUSES,
    answer_arclink_onboarding_question,
    cancel_arclink_onboarding_session,
    clean_arclink_agent_name,
    clean_arclink_agent_title,
    create_or_resume_arclink_onboarding_session,
    default_arclink_agent_profile,
    handoff_arclink_onboarding_channel,
    open_arclink_onboarding_checkout,
)
from arclink_product import base_domain as default_base_domain
from arclink_product import chutes_default_model, launch_phrase
from arclink_provisioning import update_arclink_deployment_identity
from arclink_wrapped import ArcLinkWrappedError, set_wrapped_frequency


ARCLINK_PUBLIC_BOT_CHANNELS = frozenset({"telegram", "discord"})
ARCLINK_PUBLIC_BOT_PLANS = frozenset({"founders", "sovereign", "scale"})
ARCLINK_PUBLIC_BOT_PLAN_ALIASES = {
    "starter": "founders",
    "founder": "founders",
    "founders": "founders",
    "limited": "founders",
    "limited founders": "founders",
    "limited 100 founders": "founders",
    "operator": "sovereign",
    "sovereign": "sovereign",
    "scale": "scale",
}
ARCLINK_PUBLIC_BOT_DIRECT_CHECKOUT_PLANS = ("founders", "scale")
ARCLINK_PUBLIC_BOT_DIRECT_CHECKOUT_PATH = "/api/v1/onboarding/public-bot-checkout"
ARCLINK_PUBLIC_BOT_PACKAGE_COMMANDS = frozenset({"/packages", "packages", "plans", "take me aboard", "aboard"})
ARCLINK_PUBLIC_BOT_STANDARD_PACKAGE_COMMANDS = frozenset({"/packages standard", "packages standard", "/standard-packages", "standard packages"})
ARCLINK_PUBLIC_BOT_TURN_LIMIT = 20
ARCLINK_PUBLIC_BOT_RATE_WINDOW_SECONDS = 900
ARCLINK_PUBLIC_BOT_CONNECT_NOTION_COMMANDS = frozenset(
    {"/connect-notion", "/connect_notion", "/notion", "connect-notion", "connect notion", "notion"}
)
ARCLINK_PUBLIC_BOT_CONFIG_BACKUP_COMMANDS = frozenset(
    {
        "/config-backup",
        "/config_backup",
        "config-backup",
        "config backup",
        "/setup-backup",
        "/setup_backup",
        "/backup",
        "backup",
    }
)
ARCLINK_PUBLIC_BOT_CREDENTIAL_COMMANDS = frozenset(
    {
        "/credentials",
        "/credential",
        "/show-credentials",
        "/show_credentials",
        "credentials",
        "credential",
        "show credentials",
    }
)
ARCLINK_PUBLIC_BOT_CREDENTIAL_ACK_COMMANDS = frozenset(
    {
        "/credentials-stored",
        "/credentials_stored",
        "/credential-stored",
        "/credential_stored",
        "credentials stored",
        "credential stored",
        "i stored it",
    }
)
ARCLINK_PUBLIC_BOT_HELP_COMMANDS = frozenset({"/help", "help", "commands", "/commands"})
ARCLINK_PUBLIC_BOT_LEARN_COMMANDS = frozenset({"/learn", "learn", "tour", "/tour", "how this works"})
ARCLINK_PUBLIC_BOT_CANCEL_COMMANDS = frozenset({"/cancel", "cancel", "stop"})
ARCLINK_PUBLIC_BOT_AGENTS_COMMANDS = frozenset({"/agents", "agents", "my agents", "agent roster"})
ARCLINK_PUBLIC_BOT_RETIRE_AGENT_COMMANDS = (
    "/retire-agent",
    "/retire_agent",
    "/remove-agent",
    "/remove_agent",
    "/delete-agent",
    "/delete_agent",
    "retire-agent",
    "retire agent",
    "remove-agent",
    "remove agent",
    "delete-agent",
    "delete agent",
)
ARCLINK_PUBLIC_BOT_RETIRE_AGENT_TARGET_PREFIXES = (
    "/retire-agent-",
    "/retire_agent_",
    "/remove-agent-",
    "/remove_agent_",
    "/delete-agent-",
    "/delete_agent_",
    "retire-agent-",
    "retire_agent_",
    "remove-agent-",
    "remove_agent_",
    "delete-agent-",
    "delete_agent_",
)
ARCLINK_PUBLIC_BOT_RETIRE_CONFIRM_COMMANDS = frozenset(
    {
        "/confirm-retire-agent",
        "/confirm_retire_agent",
        "/yes-retire-agent",
        "/yes_retire_agent",
        "confirm retire",
        "confirm-retire",
        "yes retire",
        "yes, retire",
        "yes delete",
        "retire now",
    }
)
ARCLINK_PUBLIC_BOT_RETIRE_CANCEL_COMMANDS = frozenset(
    {
        "/cancel-retire-agent",
        "/cancel_retire_agent",
        "/keep-agent",
        "/keep_agent",
        "no",
        "no cancel",
        "cancel retire",
        "keep agent",
        "keep-agent",
    }
)
ARCLINK_PUBLIC_BOT_TRAIN_CREW_COMMANDS = frozenset({"/train-crew", "/train_crew", "train-crew", "train crew"})
ARCLINK_PUBLIC_BOT_ACADEMY_COMMANDS = (
    "/academy",
    "/academy-training",
    "/academy_training",
    "/quick-training",
    "/quick_training",
    "/quick-briefing",
    "/quick_briefing",
    "/quick-align",
    "/quick_align",
    "/quick-huddle",
    "/quick_huddle",
    "academy",
    "academy training",
    "quick training",
    "quick briefing",
    "quick align",
    "quick huddle",
)
ARCLINK_PUBLIC_BOT_WHATS_CHANGED_COMMANDS = frozenset({"/whats-changed", "/whats_changed", "whats-changed", "what changed", "what's changed"})
ARCLINK_PUBLIC_BOT_CREW_CONFIRM_COMMANDS = frozenset({"/confirm", "confirm", "apply", "/apply"})
ARCLINK_PUBLIC_BOT_CREW_REGENERATE_COMMANDS = frozenset({"/regenerate", "regenerate", "try again", "/retry"})
ARCLINK_PUBLIC_BOT_REFUEL_COMMANDS = ("/top-up", "/top_up", "/refuel", "/credits", "top-up", "top up", "refuel", "credits")
CREW_TRAINING_WORKFLOW_KEYS = ("public_bot_workflow", "crew_training", "crew_training_updated_at")
ACADEMY_TRAINING_WORKFLOW_KEYS = ("public_bot_workflow", "academy_training", "academy_training_updated_at")
RETIRE_AGENT_WORKFLOW_KEYS = ("public_bot_workflow", "retire_agent", "retire_agent_updated_at")
CREW_TREATMENT_CHOICES = {
    "captain": "Like a Captain - formal, ready to take orders",
    "peer": "Like a peer - casual, give pushback",
    "coach": "Like a coach - supportive, ask great questions",
}
CREW_PRESET_CHOICES = ("Frontier", "Concourse", "Salvage", "Vanguard")
CREW_CAPACITY_CHOICES = ("sales", "marketing", "development", "life coaching", "companionship")
ARCLINK_PUBLIC_BOT_RAVEN_NAME_COMMANDS = (
    "/raven-name",
    "/raven_name",
    "raven-name",
    "raven_name",
    "raven name",
)
ARCLINK_PUBLIC_BOT_AGENT_NAME_COMMANDS = ("/agent-name", "/agent_name", "agent-name", "agent_name", "agent name")
ARCLINK_PUBLIC_BOT_AGENT_TITLE_COMMANDS = ("/agent-title", "/agent_title", "agent-title", "agent_title", "agent title")
ARCLINK_PUBLIC_BOT_AGENT_IDENTITY_COMMANDS = (
    "/agent-identity",
    "/agent_identity",
    "agent-identity",
    "agent_identity",
    "agent identity",
)
ARCLINK_PUBLIC_BOT_RENAME_AGENT_COMMANDS = ("/rename-agent", "/rename_agent", "rename-agent", "rename_agent")
ARCLINK_PUBLIC_BOT_RETITLE_AGENT_COMMANDS = ("/retitle-agent", "/retitle_agent", "retitle-agent", "retitle_agent")
ARCLINK_PUBLIC_BOT_WRAPPED_FREQUENCY_COMMANDS = (
    "/wrapped-frequency",
    "/wrapped_frequency",
    "wrapped-frequency",
    "wrapped_frequency",
)
ARCLINK_PUBLIC_BOT_ADD_AGENT_COMMANDS = frozenset(
    {"/add-agent", "/add_agent", "add-agent", "add agent", "hire another agent", "add another agent"}
)
ARCLINK_PUBLIC_BOT_PAIR_CHANNEL_COMMANDS = frozenset(
    {
        "/pair-channel",
        "/pair_channel",
        "/link-channel",
        "/link_channel",
        "pair-channel",
        "pair_channel",
        "link-channel",
        "link_channel",
        "pair channel",
        "link channel",
        "pair",
        "link",
    }
)
ARCLINK_PUBLIC_BOT_UPGRADE_HERMES_COMMANDS = frozenset(
    {
        "/upgrade-hermes",
        "/upgrade_hermes",
        "/update",
        "upgrade-hermes",
        "upgrade_hermes",
        "upgrade hermes",
    }
)
ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES = frozenset({"active", "first_contacted"})
ARCLINK_PUBLIC_BOT_DEPLOYMENT_RETIRING_STATUSES = frozenset({"teardown_requested", "teardown_running"})
ARCLINK_PUBLIC_BOT_DEPLOYMENT_RETIRED_STATUSES = frozenset({"torn_down", "teardown_complete", "cancelled"})
ARCLINK_PUBLIC_BOT_ADD_AGENT_ANCHOR_STATUSES = (
    ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES
    | ARCLINK_PUBLIC_BOT_DEPLOYMENT_RETIRING_STATUSES
    | ARCLINK_PUBLIC_BOT_DEPLOYMENT_RETIRED_STATUSES
    | frozenset({"teardown_failed"})
)
ARCLINK_PUBLIC_BOT_AGENT_SWITCH_RE = re.compile(r"^/(?:agent[-_])([a-z0-9][a-z0-9_-]{0,31})$")
ARCLINK_PUBLIC_BOT_PAIR_CODE_RE = re.compile(r"^[A-Z0-9]{6}$")
ARCLINK_PUBLIC_BOT_SHARE_ACTION_RE = re.compile(r"^/share-(approve|deny|accept)\s+(share_[0-9a-f]{32})$")
ARCLINK_PUBLIC_BOT_CREDENTIAL_TARGET_PREFIXES = (
    "/credentials ",
    "/credential ",
    "/show-credentials ",
    "/show_credentials ",
)
ARCLINK_PUBLIC_BOT_CREDENTIAL_ACK_TARGET_PREFIXES = (
    "/credentials-stored ",
    "/credentials_stored ",
    "/credential-stored ",
    "/credential_stored ",
)
ARCLINK_PUBLIC_BOT_RAVEN_DISPLAY_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 ._-]{0,31}$")
ARCLINK_PUBLIC_BOT_RAVEN_CONTROL_COMMANDS = frozenset({"/raven", "/arclink", "/arclink_control"})
ARCLINK_PUBLIC_BOT_RAVEN_CONTROL_FALLBACK_RE = re.compile(r"^/arclink_ops\d{0,2}$")
ARCLINK_PUBLIC_BOT_AGENT_POLICY_SUPPRESSED_COMMANDS = frozenset({"update"})
ARCLINK_PUBLIC_BOT_COMMAND_NAME_RE = re.compile(r"[^a-z0-9_]")
GITHUB_OWNER_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
PAIR_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PAIR_CODE_TTL_SECONDS = 10 * 60
ARCLINK_PUBLIC_BOT_AGENT_BRIDGE_INTRO_EVENT = "public_bot:agent_bridge_intro_sent"
ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME = "Raven"
FOUNDERS_MONTHLY_DOLLARS = 149
SOVEREIGN_MONTHLY_DOLLARS = 199
SCALE_MONTHLY_DOLLARS = 275
SOVEREIGN_AGENT_EXPANSION_MONTHLY_DOLLARS = 99
SCALE_AGENT_EXPANSION_MONTHLY_DOLLARS = 79


@dataclass(frozen=True)
class ArcLinkPublicBotAction:
    key: str
    telegram_command: str
    discord_command: str
    description: str
    discord_options: tuple[dict[str, Any], ...] = ()


ARCLINK_PUBLIC_BOT_ACTIONS: tuple[ArcLinkPublicBotAction, ...] = (
    ArcLinkPublicBotAction(
        key="start",
        telegram_command="start",
        discord_command="start",
        description="Begin your ArcLink launch path",
    ),
    ArcLinkPublicBotAction(
        key="help",
        telegram_command="help",
        discord_command="help",
        description="Open the ArcLink action palette",
    ),
    ArcLinkPublicBotAction(
        key="status",
        telegram_command="status",
        discord_command="status",
        description="Check onboarding or pod status",
    ),
    ArcLinkPublicBotAction(
        key="credentials",
        telegram_command="credentials",
        discord_command="credentials",
        description="Reveal and acknowledge your dashboard credential",
    ),
    ArcLinkPublicBotAction(
        key="name",
        telegram_command="name",
        discord_command="name",
        description="Set the Captain name Raven should use",
        discord_options=(
            {
                "type": 3,
                "name": "display_name",
                "description": "Your name or team name",
                "required": True,
            },
        ),
    ),
    ArcLinkPublicBotAction(
        key="agent_name",
        telegram_command="agent_name",
        discord_command="agent-name",
        description="Name your Agent",
        discord_options=(
            {
                "type": 3,
                "name": "name",
                "description": "Agent name",
                "required": True,
            },
        ),
    ),
    ArcLinkPublicBotAction(
        key="agent_title",
        telegram_command="agent_title",
        discord_command="agent-title",
        description="Set your Agent title",
        discord_options=(
            {
                "type": 3,
                "name": "title",
                "description": "Agent title",
                "required": True,
            },
        ),
    ),
    ArcLinkPublicBotAction(
        key="agent_identity",
        telegram_command="agent_identity",
        discord_command="agent-identity",
        description="Set Agent name and title",
        discord_options=(
            {
                "type": 3,
                "name": "identity",
                "description": "Name, title",
                "required": True,
            },
        ),
    ),
    ArcLinkPublicBotAction(
        key="rename_agent",
        telegram_command="rename_agent",
        discord_command="rename-agent",
        description="Rename your active Agent",
        discord_options=(
            {
                "type": 3,
                "name": "name",
                "description": "New Agent name",
                "required": True,
            },
        ),
    ),
    ArcLinkPublicBotAction(
        key="retitle_agent",
        telegram_command="retitle_agent",
        discord_command="retitle-agent",
        description="Retitle your active Agent",
        discord_options=(
            {
                "type": 3,
                "name": "title",
                "description": "New Agent title",
                "required": True,
            },
        ),
    ),
    ArcLinkPublicBotAction(
        key="wrapped_frequency",
        telegram_command="wrapped_frequency",
        discord_command="wrapped-frequency",
        description="Set ArcLink Wrapped cadence",
        discord_options=(
            {
                "type": 3,
                "name": "frequency",
                "description": "daily, weekly, or monthly",
                "required": True,
                "choices": [
                    {"name": "Daily", "value": "daily"},
                    {"name": "Weekly", "value": "weekly"},
                    {"name": "Monthly", "value": "monthly"},
                ],
            },
        ),
    ),
    ArcLinkPublicBotAction(
        key="plan",
        telegram_command="plan",
        discord_command="plan",
        description="Choose Founders, Sovereign, or Scale",
        discord_options=(
            {
                "type": 3,
                "name": "tier",
                "description": "ArcLink plan",
                "required": True,
                "choices": [
                    {"name": "Limited 100 Founders", "value": "founders"},
                    {"name": "Sovereign", "value": "sovereign"},
                    {"name": "Scale", "value": "scale"},
                ],
            },
        ),
    ),
    ArcLinkPublicBotAction(
        key="checkout",
        telegram_command="checkout",
        discord_command="checkout",
        description="Hire your first ArcLink agent",
    ),
    ArcLinkPublicBotAction(
        key="agents",
        telegram_command="agents",
        discord_command="agents",
        description="Open your ArcLink crew manifest",
    ),
    ArcLinkPublicBotAction(
        key="learn",
        telegram_command="learn",
        discord_command="learn",
        description="Learn how ArcLink surfaces fit together",
    ),
    ArcLinkPublicBotAction(
        key="train_crew",
        telegram_command="train_crew",
        discord_command="train-crew",
        description="Run Crew Training for your ArcLink Crew",
    ),
    ArcLinkPublicBotAction(
        key="academy",
        telegram_command="academy",
        discord_command="academy",
        description="Stage Academy specialist training for your Agents",
    ),
    ArcLinkPublicBotAction(
        key="whats_changed",
        telegram_command="whats_changed",
        discord_command="whats-changed",
        description="Show what changed in the current Crew Recipe",
    ),
    ArcLinkPublicBotAction(
        key="refuel",
        telegram_command="refuel",
        discord_command="refuel",
        description="Refuel your ArcPod's model fuel",
        discord_options=(
            {
                "type": 3,
                "name": "amount",
                "description": "Dollar amount, for example 25",
                "required": False,
            },
        ),
    ),
    ArcLinkPublicBotAction(
        key="agent",
        telegram_command="agent",
        discord_command="agent",
        description="Take the helm of one of your Agents by name",
        discord_options=(
            {
                "type": 3,
                "name": "name",
                "description": "Agent name from your Crew roster",
                "required": True,
            },
        ),
    ),
    ArcLinkPublicBotAction(
        key="raven_name",
        telegram_command="raven_name",
        discord_command="raven-name",
        description="Set Raven's display name for this channel or account",
        discord_options=(
            {
                "type": 3,
                "name": "scope",
                "description": "Where this Raven name applies",
                "required": False,
                "choices": [
                    {"name": "This channel", "value": "channel"},
                    {"name": "Whole account", "value": "account"},
                    {"name": "Reset this channel", "value": "reset"},
                    {"name": "Reset account default", "value": "reset-account"},
                ],
            },
            {
                "type": 3,
                "name": "display_name",
                "description": "New Raven display name",
                "required": False,
            },
        ),
    ),
    ArcLinkPublicBotAction(
        key="connect_notion",
        telegram_command="connect_notion",
        discord_command="connect-notion",
        description="Connect Notion to your live pod",
    ),
    ArcLinkPublicBotAction(
        key="config_backup",
        telegram_command="config_backup",
        discord_command="config-backup",
        description="Configure private pod backup",
    ),
    ArcLinkPublicBotAction(
        key="pair_channel",
        telegram_command="pair_channel",
        discord_command="pair-channel",
        description="Pair Telegram and Discord to the same ArcLink account",
        discord_options=(
            {
                "type": 3,
                "name": "code",
                "description": "Six-character code from Raven on the other channel",
                "required": False,
            },
        ),
    ),
    ArcLinkPublicBotAction(
        key="link_channel",
        telegram_command="link_channel",
        discord_command="link-channel",
        description="Link Telegram and Discord to the same ArcLink account",
        discord_options=(
            {
                "type": 3,
                "name": "code",
                "description": "Six-character code from Raven on the other channel",
                "required": False,
            },
        ),
    ),
    ArcLinkPublicBotAction(
        key="upgrade_hermes",
        telegram_command="upgrade_hermes",
        discord_command="upgrade-hermes",
        description="Check the ArcLink-managed Hermes upgrade lane",
    ),
    ArcLinkPublicBotAction(
        key="cancel",
        telegram_command="cancel",
        discord_command="cancel",
        description="Close the active setup workflow",
    ),
)


class ArcLinkPublicBotError(ValueError):
    pass


@dataclass(frozen=True)
class ArcLinkPublicBotButton:
    label: str
    command: str = ""
    url: str = ""
    style: str = "primary"
    copy_text: str = ""


@dataclass(frozen=True)
class ArcLinkPublicBotTurn:
    channel: str
    channel_identity: str
    session_id: str
    status: str
    current_step: str
    action: str
    reply: str
    checkout_url: str = ""
    user_id: str = ""
    deployment_id: str = ""
    bot_display_name: str = ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME
    buttons: tuple[ArcLinkPublicBotButton, ...] = ()
    telegram_reply: str = ""
    telegram_entities: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean_channel(channel: str) -> str:
    clean = str(channel or "").strip().lower()
    if clean not in ARCLINK_PUBLIC_BOT_CHANNELS:
        raise ArcLinkPublicBotError(f"unsupported ArcLink public bot channel: {clean or 'blank'}")
    return clean


def _clean_identity(identity: str) -> str:
    clean = str(identity or "").strip()
    if not clean:
        raise ArcLinkPublicBotError("ArcLink public bot channel identity is required")
    return clean


def _clean_raven_display_name(raw: str) -> str:
    clean = re.sub(r"\s+", " ", str(raw or "").strip())
    if not clean:
        return ""
    clean = clean[:32].rstrip()
    if not ARCLINK_PUBLIC_BOT_RAVEN_DISPLAY_NAME_RE.fullmatch(clean):
        raise ArcLinkPublicBotError(
            "Raven display name may use letters, numbers, spaces, dot, underscore, or hyphen"
        )
    return clean


def _public_bot_command_name(message: str) -> str:
    token = str(message or "").strip().split(maxsplit=1)[0].split("@", 1)[0]
    name = token.lower().lstrip("/").replace("-", "_")
    name = ARCLINK_PUBLIC_BOT_COMMAND_NAME_RE.sub("", name)
    return name[:32]


def _raven_control_rewrite(message: str, command: str) -> str | None:
    parts = str(message or "").strip().split(maxsplit=1)
    if not parts:
        return "/help"
    control = parts[0].lower().split("@", 1)[0]
    if control not in ARCLINK_PUBLIC_BOT_RAVEN_CONTROL_COMMANDS and not ARCLINK_PUBLIC_BOT_RAVEN_CONTROL_FALLBACK_RE.fullmatch(control):
        return None
    rest = parts[1].strip() if len(parts) > 1 else ""
    rest_parts = rest.split(maxsplit=1)
    raw_verb = rest_parts[0].strip().lower() if rest_parts else ""
    verb = raw_verb.replace("-", "_")
    tail = rest_parts[1].strip() if len(rest_parts) > 1 else ""
    if not verb or verb in {"help", "commands", "menu"}:
        return "/help"
    if verb in {"learn", "tour", "tutorial", "guide"}:
        return "/learn"
    if verb.startswith("agent_") and len(verb) > len("agent_"):
        return f"/agent-{verb[len('agent_'):]}"
    if verb == "agent" and tail:
        return f"/agent {tail}".strip()
    if verb in {"agent", "agents", "crew", "roster", "manifest"}:
        return "/agents"
    if verb in {"train", "train_crew", "train-crew", "crew_training"}:
        return "/train-crew"
    if verb in {
        "academy",
        "academy_training",
        "academy-training",
        "train_academy",
        "train-academy",
        "quick_training",
        "quick-training",
        "quick_briefing",
        "quick-briefing",
        "quick_align",
        "quick-align",
        "quick_huddle",
        "quick-huddle",
    }:
        return f"/academy {tail}".strip()
    if verb in {"whats_changed", "whats-changed", "changed", "changes"}:
        return "/whats-changed"
    if verb in {"top_up", "top-up", "topup", "refuel", "credits"}:
        return f"/refuel {tail}".strip()
    if verb in {"status", "health"}:
        return "/status"
    if verb in {"credentials", "credential"}:
        return f"/credentials {tail}".strip()
    if verb in {"credentials_stored", "credential_stored", "stored"}:
        return f"/credentials-stored {tail}".strip()
    if verb in {"notion", "ssot", "connect_notion", "connect-notion"}:
        return "/connect_notion"
    if verb in {"backup", "config_backup", "config-backup"}:
        return "/config_backup"
    if verb in {"link", "pair", "channel", "link_channel", "link-channel", "pair_channel", "pair-channel"}:
        return f"/link_channel {tail}".strip()
    if verb in {"add", "add_agent", "add-agent"}:
        return "/add-agent"
    if verb.startswith("retire_agent_") and len(verb) > len("retire_agent_"):
        return f"/retire-agent-{verb[len('retire_agent_'):]}"
    if verb.startswith("remove_agent_") and len(verb) > len("remove_agent_"):
        return f"/remove-agent-{verb[len('remove_agent_'):]}"
    if verb.startswith("delete_agent_") and len(verb) > len("delete_agent_"):
        return f"/delete-agent-{verb[len('delete_agent_'):]}"
    if verb in {"retire", "retire_agent", "retire-agent", "remove", "remove_agent", "remove-agent", "delete", "delete_agent", "delete-agent"}:
        return f"/retire-agent {tail}".strip()
    if verb in {"confirm_retire", "confirm_retire_agent", "confirm-retire", "confirm-retire-agent", "yes_retire", "yes-retire"}:
        return "/confirm-retire-agent"
    if verb in {"cancel_retire", "cancel_retire_agent", "cancel-retire", "cancel-retire-agent", "keep", "keep_agent", "keep-agent"}:
        return "/cancel-retire-agent"
    if verb in {"approve", "share_approve", "share-approve"}:
        return f"/share-approve {tail}".strip()
    if verb in {"deny", "share_deny", "share-deny"}:
        return f"/share-deny {tail}".strip()
    if verb in {"accept", "share_accept", "share-accept"}:
        return f"/share-accept {tail}".strip()
    if verb in {"upgrade", "upgrade_hermes", "upgrade-hermes", "update"}:
        return "/upgrade_hermes"
    if verb in {"cancel", "stop"}:
        return "/cancel"
    if verb in {"name", "raven_name", "raven-name"}:
        return f"/raven_name {tail}".strip()
    return "/help"


def _retire_agent_command_value(message: str, command: str) -> str | None:
    value = _value_for_named_command(message, command, ARCLINK_PUBLIC_BOT_RETIRE_AGENT_COMMANDS)
    if value is not None:
        return value
    return _target_from_command(
        command,
        aliases=frozenset(ARCLINK_PUBLIC_BOT_RETIRE_AGENT_COMMANDS),
        prefixes=ARCLINK_PUBLIC_BOT_RETIRE_AGENT_TARGET_PREFIXES,
    )


def _academy_command_value(message: str, command: str) -> str | None:
    return _value_for_named_command(message, command, ARCLINK_PUBLIC_BOT_ACADEMY_COMMANDS)


def _raven_name_command_value(message: str, command: str) -> str | None:
    for name in ARCLINK_PUBLIC_BOT_RAVEN_NAME_COMMANDS:
        if command == name:
            return ""
        prefix = f"{name} "
        if command.startswith(prefix):
            return message[len(prefix):].strip()
    return None


def _value_for_named_command(message: str, command: str, names: tuple[str, ...]) -> str | None:
    for name in names:
        if command == name:
            return ""
        prefix = f"{name} "
        if command.startswith(prefix):
            return message[len(prefix):].strip()
    return None


def _workflow_value_for_named_command(message: str, command: str, names: tuple[str, ...]) -> str | None:
    explicit_value = _value_for_named_command(message, command, names)
    if explicit_value is not None:
        return explicit_value.strip()
    if command.startswith("/"):
        return None
    return str(message or "").strip()


def _agent_identity_pair(value: str) -> tuple[str, str]:
    raw = str(value or "").strip()
    for delimiter in (",", " - ", " as "):
        if delimiter in raw:
            left, right = raw.split(delimiter, 1)
            return left.strip(), right.strip()
    parts = raw.split(maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return raw, ""


def _clean_agent_name(value: str, *, required: bool = True) -> str:
    return clean_arclink_agent_name(value, required=required)


def _clean_agent_title(value: str, *, required: bool = True) -> str:
    return clean_arclink_agent_title(value, required=required)


def _answer_agent_identity(
    conn: sqlite3.Connection,
    session: Mapping[str, Any],
    *,
    question_key: str,
    answer_summary: str,
    agent_name: str | None = None,
    agent_title: str | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if agent_name is not None:
        kwargs["agent_name"] = _clean_agent_name(agent_name)
    if agent_title is not None:
        kwargs["agent_title"] = _clean_agent_title(agent_title)
    return answer_arclink_onboarding_question(
        conn,
        session_id=str(session["session_id"]),
        question_key=question_key,
        answer_summary=answer_summary,
        **kwargs,
    )


def _clear_public_bot_workflow(conn: sqlite3.Connection, session: Mapping[str, Any]) -> dict[str, Any]:
    return _update_session_metadata(
        conn,
        session_id=str(session["session_id"]),
        updates={},
        clear=("public_bot_workflow",),
    )


def _session_has_agent_identity(session: Mapping[str, Any]) -> bool:
    return bool(str(session.get("agent_name") or "").strip() and str(session.get("agent_title") or "").strip())


def _raven_identity_user_id(
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
) -> str:
    return str((deployment or {}).get("user_id") or (session or {}).get("user_id") or "").strip()


def _raven_display_name(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None = None,
    deployment: Mapping[str, Any] | None = None,
) -> str:
    user_id = _raven_identity_user_id(session, deployment)
    channel_rows: list[sqlite3.Row] = []
    if user_id:
        channel_rows = conn.execute(
            """
            SELECT raven_display_name
            FROM arclink_public_bot_identity
            WHERE scope_kind = 'channel'
              AND LOWER(channel) = LOWER(?)
              AND channel_identity = ?
              AND user_id IN (?, '')
              AND raven_display_name != ''
            ORDER BY CASE WHEN user_id = ? THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (channel, channel_identity, user_id, user_id),
        ).fetchall()
    else:
        channel_rows = conn.execute(
            """
            SELECT raven_display_name
            FROM arclink_public_bot_identity
            WHERE scope_kind = 'channel'
              AND LOWER(channel) = LOWER(?)
              AND channel_identity = ?
              AND user_id = ''
              AND raven_display_name != ''
            LIMIT 1
            """,
            (channel, channel_identity),
        ).fetchall()
    if channel_rows:
        return str(channel_rows[0]["raven_display_name"] or ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME)

    if user_id:
        row = conn.execute(
            """
            SELECT raven_display_name
            FROM arclink_public_bot_identity
            WHERE scope_kind = 'user'
              AND user_id = ?
              AND channel = ''
              AND channel_identity = ''
              AND raven_display_name != ''
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        if row is not None:
            return str(row["raven_display_name"] or ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME)
    return ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME


def _store_raven_display_name(
    conn: sqlite3.Connection,
    *,
    scope_kind: str,
    user_id: str = "",
    channel: str = "",
    channel_identity: str = "",
    display_name: str = "",
) -> None:
    if scope_kind == "user" and not str(user_id or "").strip():
        raise ArcLinkPublicBotError("Account-scoped Raven display names require an ArcLink user id")
    now = utc_now_iso()
    if display_name:
        conn.execute(
            """
            INSERT INTO arclink_public_bot_identity (
              scope_kind, user_id, channel, channel_identity, raven_display_name, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(scope_kind, user_id, channel, channel_identity) DO UPDATE SET
              raven_display_name = excluded.raven_display_name,
              updated_at = excluded.updated_at
            """,
            (scope_kind, user_id, channel, channel_identity, display_name, now, now),
        )
    else:
        conn.execute(
            """
            DELETE FROM arclink_public_bot_identity
            WHERE scope_kind = ?
              AND user_id = ?
              AND channel = ?
              AND channel_identity = ?
            """,
            (scope_kind, user_id, channel, channel_identity),
        )
    conn.commit()


def _agent_switch_request(message: str, command: str) -> tuple[str, bool]:
    """Return a requested Agent selector plus whether it is a hard switch command.

    `/agent Jeff` and `/agent-jeff` are Raven-owned switch attempts. They never
    relay text to Hermes; once an Agent is at the helm, normal chat goes there
    directly.
    """
    match = ARCLINK_PUBLIC_BOT_AGENT_SWITCH_RE.match(command)
    if match:
        return match.group(1), True
    if command in {"/agent", "agent"}:
        return "", True
    for prefix in ("/agent ", "agent "):
        if command.startswith(prefix):
            value = str(message or "")[len(prefix) :].strip()
            return value, True
    return "", False


def _agent_bridge_channel_subject(channel: str, channel_identity: str) -> str:
    return f"{channel}:{channel_identity}"


def _agent_bridge_intro_already_sent(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM arclink_events
        WHERE subject_kind = 'public_bot_channel'
          AND subject_id = ?
          AND event_type = ?
        LIMIT 1
        """,
        (_agent_bridge_channel_subject(channel, channel_identity), ARCLINK_PUBLIC_BOT_AGENT_BRIDGE_INTRO_EVENT),
    ).fetchone()
    return row is not None


def _claim_agent_bridge_intro(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    deployment: Mapping[str, Any],
) -> bool:
    if _agent_bridge_intro_already_sent(conn, channel=channel, channel_identity=channel_identity):
        return False
    append_arclink_event(
        conn,
        subject_kind="public_bot_channel",
        subject_id=_agent_bridge_channel_subject(channel, channel_identity),
        event_type=ARCLINK_PUBLIC_BOT_AGENT_BRIDGE_INTRO_EVENT,
        metadata={
            "channel": channel,
            "channel_identity": channel_identity,
            "deployment_id": str(deployment.get("deployment_id") or ""),
            "user_id": str(deployment.get("user_id") or ""),
        },
    )
    return True


def _button(
    label: str,
    *,
    command: str = "",
    url: str = "",
    style: str = "primary",
    copy_text: str = "",
) -> ArcLinkPublicBotButton:
    return ArcLinkPublicBotButton(label=label, command=command, url=url, style=style, copy_text=copy_text)


def _reply(
    session: Mapping[str, Any],
    *,
    action: str,
    reply: str,
    bot_display_name: str = ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME,
    buttons: tuple[ArcLinkPublicBotButton, ...] = (),
) -> ArcLinkPublicBotTurn:
    return ArcLinkPublicBotTurn(
        channel=str(session.get("channel") or ""),
        channel_identity=str(session.get("channel_identity") or ""),
        session_id=str(session.get("session_id") or ""),
        status=str(session.get("status") or ""),
        current_step=str(session.get("current_step") or ""),
        action=action,
        reply=reply,
        checkout_url=str(session.get("checkout_url") or ""),
        user_id=str(session.get("user_id") or ""),
        deployment_id=str(session.get("deployment_id") or ""),
        bot_display_name=bot_display_name or ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME,
        buttons=buttons,
    )


def _telegram_utf16_offset(text: str, index: int) -> int:
    return len(text[:index].encode("utf-16-le")) // 2


def _telegram_code_entities(text: str, values: tuple[str, ...]) -> tuple[dict[str, Any], ...]:
    entities: list[dict[str, Any]] = []
    search_from = 0
    for value in values:
        if not value:
            continue
        index = text.find(value, search_from)
        if index < 0:
            index = text.find(value)
        if index < 0:
            continue
        end = index + len(value)
        entities.append(
            {
                "type": "code",
                "offset": _telegram_utf16_offset(text, index),
                "length": _telegram_utf16_offset(text, end) - _telegram_utf16_offset(text, index),
            }
        )
        search_from = end
    return tuple(entities)


def _package_prompt_reply(
    session: Mapping[str, Any],
    *,
    greeting: str = "",
    bot_display_name: str = ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME,
    standard: bool = False,
    checkout_buttons: tuple[ArcLinkPublicBotButton, ...] = (),
) -> ArcLinkPublicBotTurn:
    name = str(session.get("display_name_hint") or "").strip()
    raven = bot_display_name or ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME
    header = greeting or (f"Captain {name}, {raven} on the line." if name else f"{raven} on the line, Captain.")
    if standard:
        return _reply(
            session,
            action="prompt_package",
            reply=(
                f"{header}\n\n"
                "Choose how many Agents to bring live on ArcLink.\n\n"
                f"Sovereign is ${SOVEREIGN_MONTHLY_DOLLARS}/month: one Agent live on ArcLink.\n"
                f"Scale is ${SCALE_MONTHLY_DOLLARS}/month: three Agents live on ArcLink with Federation.\n\n"
                f"Agentic Expansion after launch: Sovereign agents are ${SOVEREIGN_AGENT_EXPANSION_MONTHLY_DOLLARS}/month each; "
                f"Scale agents are ${SCALE_AGENT_EXPANSION_MONTHLY_DOLLARS}/month each."
            ),
            buttons=(
                _button(f"Sovereign - ${SOVEREIGN_MONTHLY_DOLLARS}/month", command="/plan sovereign"),
                _button(f"Scale - ${SCALE_MONTHLY_DOLLARS}/month", command="/plan scale", style="secondary"),
            ),
            bot_display_name=raven,
        )
    return _reply(
        session,
        action="prompt_package",
        reply=(
            f"{header}\n\n"
            "ArcLink brings a private ArcPod online for you: Agent memory, files, code workspace, tool lanes, model access, and a live Hermes dashboard under one governed identity. "
            "Raven stays on the bridge while your Crew wakes up; the Agents do the work once the Pod is lit.\n\n"
            "Choose your launch lane.\n\n"
            f"Founders Offer is ${FOUNDERS_MONTHLY_DOLLARS}/mo: one ArcPod for the first 100 Captains.\n"
            f"3X Scale Plan is ${SCALE_MONTHLY_DOLLARS}/mo: three Agents live on ArcLink with Federation.\n\n"
            "Tap a lane to open secure Stripe checkout. After payment clears, I will show your initial Crew roster and give you Train My Crew or Show My Crew as the next clean step."
        ),
        buttons=checkout_buttons or (
            _button(f"Founders Offer ${FOUNDERS_MONTHLY_DOLLARS}/mo", command="/plan founders"),
            _button(f"3X Scale Plan ${SCALE_MONTHLY_DOLLARS}/mo", command="/plan scale", style="secondary"),
        ),
        bot_display_name=raven,
    )


def _agent_name_prompt_reply(
    conn: sqlite3.Connection,
    session: Mapping[str, Any],
    *,
    bot_display_name: str = ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME,
) -> ArcLinkPublicBotTurn:
    updated = _update_session_metadata(
        conn,
        session_id=str(session["session_id"]),
        updates={"public_bot_workflow": "agent_name", "agent_name_requested_at": utc_now_iso()},
    )
    return _reply(
        updated,
        action="prompt_agent_name",
        reply=(
            "Name your Agent.\n\n"
            "Send the Agent name as plain text, or use `/agent-name Atlas`. Keep it to 40 characters."
        ),
        buttons=(_button("Cancel", command="/cancel", style="secondary"),),
        bot_display_name=bot_display_name,
    )


def _agent_title_prompt_reply(
    conn: sqlite3.Connection,
    session: Mapping[str, Any],
    *,
    bot_display_name: str = ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME,
) -> ArcLinkPublicBotTurn:
    updated = _update_session_metadata(
        conn,
        session_id=str(session["session_id"]),
        updates={"public_bot_workflow": "agent_title", "agent_title_requested_at": utc_now_iso()},
    )
    name = str(updated.get("agent_name") or "").strip()
    name_line = f" for {name}" if name else ""
    return _reply(
        updated,
        action="prompt_agent_title",
        reply=(
            f"Give your Agent{name_line} a title.\n\n"
            "Send the title as plain text, or use `/agent-title the right hand`. Keep it to 80 characters."
        ),
        buttons=(_button("Cancel", command="/cancel", style="secondary"),),
        bot_display_name=bot_display_name,
    )


def _identity_or_package_prompt(
    conn: sqlite3.Connection,
    session: Mapping[str, Any],
    *,
    base_domain: str = "",
    greeting: str = "",
    bot_display_name: str = ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME,
    standard: bool = False,
) -> ArcLinkPublicBotTurn:
    if str(_metadata(session).get("public_bot_workflow") or "") in {"agent_name", "agent_title", "name_update"}:
        session = _clear_session_workflow(conn, session_id=str(session["session_id"]))
    session, checkout_buttons = _ensure_direct_checkout_buttons(conn, session, base_domain=base_domain)
    return _package_prompt_reply(
        session,
        greeting=greeting,
        bot_display_name=bot_display_name,
        standard=standard,
        checkout_buttons=checkout_buttons,
    )


def _public_bot_direct_checkout_label(plan: str) -> str:
    clean = str(plan or "").strip().lower()
    if clean == "scale":
        return f"3X Scale Plan ${SCALE_MONTHLY_DOLLARS}/mo"
    return f"Founders Offer ${FOUNDERS_MONTHLY_DOLLARS}/mo"


def _direct_checkout_url(*, session_id: str, plan: str, token: str, base_domain: str) -> str:
    root = f"https://{str(base_domain or default_base_domain({})).strip().strip('/')}"
    query = urlencode({"session": session_id, "plan": plan, "token": token})
    return f"{root}{ARCLINK_PUBLIC_BOT_DIRECT_CHECKOUT_PATH}?{query}"


def _direct_checkout_token_digest(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _ensure_direct_checkout_buttons(
    conn: sqlite3.Connection,
    session: Mapping[str, Any],
    *,
    base_domain: str,
) -> tuple[dict[str, Any], tuple[ArcLinkPublicBotButton, ...]]:
    session_id = str(session.get("session_id") or "").strip()
    if not session_id:
        return dict(session), ()
    payload = _metadata(session)
    tokens: dict[str, str] = {}
    verifiers: dict[str, str] = {}
    for plan in ARCLINK_PUBLIC_BOT_DIRECT_CHECKOUT_PLANS:
        token = secrets.token_urlsafe(24)
        tokens[plan] = token
        verifiers[plan] = _direct_checkout_token_digest(token)
    payload.pop("public_bot_checkout_tokens", None)
    payload.pop("public_bot_checkout_token_hashes", None)
    payload["public_bot_checkout_verifiers"] = verifiers
    conn.execute(
        """
        UPDATE arclink_onboarding_sessions
        SET metadata_json = ?, updated_at = ?
        WHERE session_id = ?
        """,
        (
            json_dumps_safe(payload, label="ArcLink public bot checkout verifier", error_cls=ArcLinkPublicBotError),
            utc_now_iso(),
            session_id,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM arclink_onboarding_sessions WHERE session_id = ?", (session_id,)).fetchone()
    if row is not None:
        session = dict(row)
    buttons = tuple(
        _button(
            _public_bot_direct_checkout_label(plan),
            url=_direct_checkout_url(
                session_id=session_id,
                plan=plan,
                token=str(tokens.get(plan) or ""),
                base_domain=base_domain,
            ),
            style="secondary" if plan == "scale" else "",
        )
        for plan in ARCLINK_PUBLIC_BOT_DIRECT_CHECKOUT_PLANS
    )
    return dict(session), buttons


def _turn(
    *,
    channel: str,
    channel_identity: str,
    action: str,
    reply: str,
    session: Mapping[str, Any] | None = None,
    deployment: Mapping[str, Any] | None = None,
    bot_display_name: str = ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME,
    buttons: tuple[ArcLinkPublicBotButton, ...] = (),
    telegram_reply: str = "",
    telegram_entities: tuple[dict[str, Any], ...] = (),
) -> ArcLinkPublicBotTurn:
    session = dict(session or {})
    deployment = dict(deployment or {})
    return ArcLinkPublicBotTurn(
        channel=channel,
        channel_identity=channel_identity,
        session_id=str(session.get("session_id") or ""),
        status=str(deployment.get("status") or session.get("status") or ""),
        current_step=str(session.get("current_step") or ""),
        action=action,
        reply=reply,
        checkout_url=str(session.get("checkout_url") or ""),
        user_id=str(deployment.get("user_id") or session.get("user_id") or ""),
        deployment_id=str(deployment.get("deployment_id") or session.get("deployment_id") or ""),
        bot_display_name=bot_display_name or ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME,
        buttons=buttons,
        telegram_reply=telegram_reply,
        telegram_entities=telegram_entities,
    )


def _parse_answer(text: str, prefix: str) -> str:
    _, _, value = text.partition(prefix)
    return value.strip()


def arclink_public_bot_actions() -> tuple[ArcLinkPublicBotAction, ...]:
    return ARCLINK_PUBLIC_BOT_ACTIONS


def arclink_public_bot_telegram_commands() -> list[dict[str, str]]:
    return [
        {"command": action.telegram_command, "description": action.description}
        for action in ARCLINK_PUBLIC_BOT_ACTIONS
    ]


def arclink_public_bot_discord_application_commands() -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = [
        {
            "name": "arclink",
            "type": 1,
            "description": "Talk to Raven, your ArcLink guide",
            "options": [
                {
                    "type": 3,
                    "name": "message",
                    "description": "Freeform onboarding message or command",
                    "required": True,
                }
            ],
        }
    ]
    for action in ARCLINK_PUBLIC_BOT_ACTIONS:
        payload: dict[str, Any] = {
            "name": action.discord_command,
            "type": 1,
            "description": action.description,
        }
        if action.discord_options:
            payload["options"] = [dict(item) for item in action.discord_options]
        commands.append(payload)
    return commands


def _active_raven_callback_command(command: str) -> str:
    value = str(command or "").strip()
    mapping = {
        "/help": "/raven help",
        "/commands": "/raven help",
        "/learn": "/raven learn",
        "/tour": "/raven learn",
        "/status": "/raven status",
        "/agents": "/raven agents",
        "/train-crew": "/raven train_crew",
        "/train_crew": "/raven train_crew",
        "/academy": "/raven academy",
        "/quick-training": "/raven academy",
        "/quick_training": "/raven academy",
        "/whats-changed": "/raven whats_changed",
        "/whats_changed": "/raven whats_changed",
        "/top-up": "/raven refuel",
        "/top_up": "/raven refuel",
        "/refuel": "/raven refuel",
        "/credits": "/raven credits",
        "/credentials": "/raven credentials",
        "/credentials-stored": "/raven credentials_stored",
        "/credentials_stored": "/raven credentials_stored",
        "/connect_notion": "/raven connect_notion",
        "/connect-notion": "/raven connect_notion",
        "/config_backup": "/raven config_backup",
        "/config-backup": "/raven config_backup",
        "/link_channel": "/raven link_channel",
        "/link-channel": "/raven link_channel",
        "/add-agent": "/raven add_agent",
        "/add_agent": "/raven add_agent",
        "/retire-agent": "/raven retire_agent",
        "/retire_agent": "/raven retire_agent",
        "/confirm-retire-agent": "/raven confirm_retire_agent",
        "/confirm_retire_agent": "/raven confirm_retire_agent",
        "/cancel-retire-agent": "/raven cancel_retire_agent",
        "/cancel_retire_agent": "/raven cancel_retire_agent",
        "/upgrade_hermes": "/raven upgrade_hermes",
        "/upgrade-hermes": "/raven upgrade_hermes",
        "/cancel": "/raven cancel",
    }
    if value.startswith("/credentials "):
        return f"/raven credentials {value.split(maxsplit=1)[1].strip()}".strip()
    if value.startswith("/top-up ") or value.startswith("/top_up ") or value.startswith("/refuel ") or value.startswith("/credits "):
        return f"/raven refuel {value.split(maxsplit=1)[1].strip()}".strip()
    if value.startswith("/credentials-stored ") or value.startswith("/credentials_stored "):
        return f"/raven credentials_stored {value.split(maxsplit=1)[1].strip()}".strip()
    if value.startswith("/retire-agent ") or value.startswith("/retire_agent "):
        return f"/raven retire_agent {value.split(maxsplit=1)[1].strip()}".strip()
    for prefix in ("/retire-agent-", "/retire_agent_", "/remove-agent-", "/remove_agent_", "/delete-agent-", "/delete_agent_"):
        if value.startswith(prefix):
            return f"/raven retire_agent {value[len(prefix):].strip()}".strip()
    if value.startswith("/agent-") or value.startswith("/agent_"):
        return f"/raven {value.lstrip('/')}"
    share_match = ARCLINK_PUBLIC_BOT_SHARE_ACTION_RE.match(value.lower())
    if share_match:
        action = str(share_match.group(1) or "")
        return f"/raven {action} {share_match.group(2)}"
    return mapping.get(value, value)


def arclink_public_bot_turn_telegram_reply_markup(turn: ArcLinkPublicBotTurn) -> dict[str, Any] | None:
    buttons = tuple(turn.buttons or ())
    if not buttons:
        return None
    active = turn.status in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES
    rows: list[list[dict[str, Any]]] = []
    row: list[dict[str, Any]] = []
    for button in buttons:
        payload: dict[str, Any] = {"text": button.label[:64]}
        if button.copy_text:
            payload["copy_text"] = {"text": button.copy_text[:256]}
        elif button.url:
            payload["url"] = button.url
        else:
            command = button.command or button.label
            if active:
                command = _active_raven_callback_command(command)
            payload["callback_data"] = f"arclink:{command}"[:64]
        row.append(payload)
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return {"inline_keyboard": rows}


def arclink_public_bot_turn_discord_components(turn: ArcLinkPublicBotTurn) -> list[dict[str, Any]]:
    buttons = tuple(turn.buttons or ())
    if not buttons:
        return []
    rows: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    for button in buttons:
        if button.copy_text:
            continue
        payload: dict[str, Any] = {
            "type": 2,
            "label": button.label[:80],
            "style": 5 if button.url else (2 if button.style == "secondary" else 1),
        }
        if button.url:
            payload["url"] = button.url
        else:
            payload["custom_id"] = f"arclink:{button.command or button.label}"[:100]
        current.append(payload)
        if len(current) == 5:
            rows.append({"type": 1, "components": current})
            current = []
    if current:
        rows.append({"type": 1, "components": current})
    return rows


def _command_value(message: str, command: str, names: tuple[str, ...]) -> str | None:
    for name in names:
        prefix = f"{name} "
        if command.startswith(prefix):
            return message[len(prefix):].strip()
    return None


def _is_raven_launch_command(message: str, command: str) -> bool:
    if command in ARCLINK_PUBLIC_BOT_PACKAGE_COMMANDS or command in ARCLINK_PUBLIC_BOT_STANDARD_PACKAGE_COMMANDS:
        return True
    if command in {"checkout", "/checkout", "name", "/name", "plan", "/plan"}:
        return True
    return (
        _command_value(message, command, ("name", "/name")) is not None
        or _command_value(message, command, ("plan", "/plan")) is not None
    )


def _normalize_public_bot_plan(raw: str) -> str:
    return ARCLINK_PUBLIC_BOT_PLAN_ALIASES.get(str(raw or "").strip().lower(), "")


def _plan_label(plan: str) -> str:
    clean = str(plan or "").strip().lower()
    if clean == "scale":
        return "3X Scale Plan"
    if clean == "founders":
        return "Founders Offer"
    return "Sovereign"


def _plan_agent_count(plan: str) -> int:
    return 3 if str(plan or "").strip().lower() == "scale" else 1


def _fleet_capacity_block(conn: sqlite3.Connection, *, required_slots: int, label: str) -> str:
    try:
        from arclink_fleet import fleet_capacity_summary

        summary = fleet_capacity_summary(conn)
    except Exception:
        return ""
    if int(summary.get("total_hosts") or 0) <= 0:
        return ""
    available = 0
    for host in summary.get("hosts") or []:
        if not isinstance(host, Mapping):
            continue
        if str(host.get("status") or "") != "active" or bool(host.get("drain")):
            continue
        available += max(0, int(host.get("headroom") or 0))
    if available >= required_slots:
        return ""
    slot_word = "slot" if required_slots == 1 else "slots"
    return (
        f"{label} needs {required_slots} open ArcPod {slot_word}, but the ArcLink fleet has {available} available right now.\n\n"
        "I will not open checkout until capacity is ready, so you are not charged for a launch that cannot complete. "
        "Check Status after capacity is added, then try again."
    )


def _plan_checkout_label(plan: str) -> str:
    clean = str(plan or "").strip().lower()
    if clean == "scale":
        return f"Fire Up 3X Scale Plan - ${SCALE_MONTHLY_DOLLARS}/month"
    if clean == "founders":
        return f"Fire Up Founders Offer - ${FOUNDERS_MONTHLY_DOLLARS}/month"
    return f"Hire Sovereign - ${SOVEREIGN_MONTHLY_DOLLARS}/month"


def _checkout_price_id_for_plan(
    plan: str,
    *,
    price_id: str,
    founders_price_id: str,
    scale_price_id: str,
) -> str:
    clean = _normalize_public_bot_plan(plan) or "founders"
    checkout_price_id = str(price_id or "").strip()
    if clean == "founders" and str(founders_price_id or "").strip():
        checkout_price_id = str(founders_price_id or "").strip()
    if clean == "founders" and not checkout_price_id:
        raise ArcLinkPublicBotError("Founders checkout requires ARCLINK_FOUNDERS_PRICE_ID")
    if clean == "scale" and str(scale_price_id or "").strip():
        checkout_price_id = str(scale_price_id or "").strip()
    if clean == "scale" and not str(scale_price_id or "").strip():
        raise ArcLinkPublicBotError("Scale checkout requires ARCLINK_SCALE_PRICE_ID")
    if not checkout_price_id:
        raise ArcLinkPublicBotError("Sovereign checkout requires ARCLINK_SOVEREIGN_PRICE_ID")
    return checkout_price_id


def _open_first_agent_checkout_turn(
    conn: sqlite3.Connection,
    session: Mapping[str, Any],
    *,
    stripe_client: Any,
    selected_plan: str,
    price_id: str,
    founders_price_id: str,
    scale_price_id: str,
    base_domain: str,
    bot_display_name: str = ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME,
) -> ArcLinkPublicBotTurn:
    root = f"https://{str(base_domain or default_base_domain({})).strip().strip('/')}"
    plan_label = _plan_label(selected_plan)
    capacity_message = _fleet_capacity_block(conn, required_slots=_plan_agent_count(selected_plan), label=plan_label)
    if capacity_message:
        return _reply(
            session,
            action="checkout_capacity_blocked",
            reply=capacity_message,
            buttons=(
                _button("Check Status", command="/status", style="secondary"),
                _button("Change Package", command="/packages", style="secondary"),
            ),
            bot_display_name=bot_display_name,
        )
    checkout_price_id = _checkout_price_id_for_plan(
        selected_plan,
        price_id=price_id,
        founders_price_id=founders_price_id,
        scale_price_id=scale_price_id,
    )
    session = open_arclink_onboarding_checkout(
        conn,
        session_id=str(session["session_id"]),
        stripe_client=stripe_client,
        price_id=checkout_price_id,
        success_url=f"{root}/checkout/success?session={str(session['session_id'])}",
        cancel_url=f"{root}/checkout/cancel?session={str(session['session_id'])}",
        base_domain=base_domain or default_base_domain({}),
    )
    return _reply(
        session,
        action="open_checkout",
        reply=(
            f"{plan_label} checkout is ready.\n\n"
            "Finish the secure Stripe checkout below. Once payment clears, I reserve your Crew roster, start the ArcPod launch, "
            "and report back here with Train My Crew and Show My Crew as the next actions."
        ),
        buttons=(
            _button(_plan_checkout_label(selected_plan), url=str(session.get("checkout_url") or "")),
        ),
        bot_display_name=bot_display_name,
    )


def _pair_channel_value(message: str, command: str) -> str | None:
    if command in ARCLINK_PUBLIC_BOT_PAIR_CHANNEL_COMMANDS:
        return ""
    return _command_value(
        message,
        command,
        (
            "/pair-channel",
            "/pair_channel",
            "/link-channel",
            "/link_channel",
            "pair-channel",
            "pair_channel",
            "link-channel",
            "link_channel",
            "pair channel",
            "link channel",
            "pair",
            "link",
        ),
    )


def _normalize_pair_code(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()


def _new_pair_code() -> str:
    return "".join(secrets.choice(PAIR_CODE_ALPHABET) for _ in range(6))


def _check_public_bot_rate_limit(conn: sqlite3.Connection, *, channel: str, channel_identity: str) -> None:
    check_arclink_rate_limit(
        conn,
        scope=f"onboarding:{channel}",
        subject=channel_identity,
        limit=ARCLINK_PUBLIC_BOT_TURN_LIMIT,
        window_seconds=ARCLINK_PUBLIC_BOT_RATE_WINDOW_SECONDS,
    )


def _latest_session_for_contact(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
) -> dict[str, Any] | None:
    ready_placeholders = ",".join("?" for _ in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES)
    active_placeholders = ",".join("?" for _ in ARCLINK_ONBOARDING_ACTIVE_STATUSES)
    inactive_deployment_statuses = (
        ARCLINK_PUBLIC_BOT_DEPLOYMENT_RETIRING_STATUSES
        | ARCLINK_PUBLIC_BOT_DEPLOYMENT_RETIRED_STATUSES
        | frozenset({"teardown_failed"})
    )
    inactive_placeholders = ",".join("?" for _ in inactive_deployment_statuses)
    row = conn.execute(
        f"""
        SELECT s.*
        FROM arclink_onboarding_sessions s
        LEFT JOIN arclink_deployments d ON d.deployment_id = s.deployment_id
        WHERE LOWER(s.channel) = LOWER(?)
          AND LOWER(s.channel_identity) = LOWER(?)
        ORDER BY
          CASE
            WHEN d.status IN ({ready_placeholders}) THEN 0
            WHEN s.status IN ({active_placeholders})
             AND (
               s.deployment_id = ''
               OR d.status IS NULL
               OR d.status NOT IN ({inactive_placeholders})
             ) THEN 1
            WHEN s.status IN ({active_placeholders}) THEN 2
            WHEN s.deployment_id != '' THEN 3
            ELSE 4
          END,
          s.updated_at DESC,
          s.created_at DESC,
          s.session_id DESC
        LIMIT 1
        """,
        (
            channel,
            channel_identity,
            *sorted(ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES),
            *sorted(ARCLINK_ONBOARDING_ACTIVE_STATUSES),
            *sorted(inactive_deployment_statuses),
            *sorted(ARCLINK_ONBOARDING_ACTIVE_STATUSES),
        ),
    ).fetchone()
    return dict(row) if row is not None else None


def _deployment_for_session(conn: sqlite3.Connection, session: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not session:
        return None
    session_user_id = str(session.get("user_id") or "").strip()
    active_deployment_id = str(_metadata(session).get("active_deployment_id") or "").strip()
    if active_deployment_id:
        row = conn.execute("SELECT * FROM arclink_deployments WHERE deployment_id = ?", (active_deployment_id,)).fetchone()
        if row is not None and str(row["user_id"] or "") == session_user_id:
            candidate = dict(row)
            if str(candidate.get("status") or "") in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES:
                return candidate
    deployment_id = str(session.get("deployment_id") or "").strip()
    if deployment_id:
        row = conn.execute("SELECT * FROM arclink_deployments WHERE deployment_id = ?", (deployment_id,)).fetchone()
        if row is not None and str(row["user_id"] or "") == session_user_id:
            candidate = dict(row)
            if str(candidate.get("status") or "") in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES:
                return candidate
    if not session_user_id:
        return None
    row = conn.execute(
        """
        SELECT *
        FROM arclink_deployments
        WHERE user_id = ?
        ORDER BY
          CASE status
            WHEN 'active' THEN 0
            WHEN 'first_contacted' THEN 1
            WHEN 'provisioning_ready' THEN 2
            WHEN 'provisioning' THEN 3
            WHEN 'provisioning_failed' THEN 4
            ELSE 5
          END,
          updated_at DESC,
          created_at DESC,
          deployment_id DESC
        LIMIT 1
        """,
        (session_user_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def _target_from_command(command: str, *, aliases: frozenset[str], prefixes: tuple[str, ...]) -> str | None:
    value = str(command or "").strip().lower()
    if value in aliases:
        return ""
    for prefix in prefixes:
        if value.startswith(prefix):
            return value[len(prefix):].strip()
    return None


def _deployment_for_selector(
    conn: sqlite3.Connection,
    *,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
    selector: str,
) -> dict[str, Any] | None:
    clean = str(selector or "").strip().lower()
    if not clean:
        return dict(deployment) if deployment is not None else None
    user_id = str((deployment or {}).get("user_id") or (session or {}).get("user_id") or "").strip()
    if not user_id:
        return None
    row = conn.execute(
        """
        SELECT *
        FROM arclink_deployments
        WHERE user_id = ?
          AND (
            LOWER(deployment_id) = ?
            OR LOWER(prefix) = ?
            OR LOWER(agent_id) = ?
          )
        LIMIT 1
        """,
        (user_id, clean, clean, clean),
    ).fetchone()
    return dict(row) if row is not None else None


def _agent_identity_update_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    deployment: Mapping[str, Any] | None,
    session: Mapping[str, Any] | None,
    agent_name: str | None = None,
    agent_title: str | None = None,
) -> ArcLinkPublicBotTurn:
    if deployment is None or str(deployment.get("status") or "") not in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="agent_identity_not_ready",
            reply="Agent rename and retitle commands open after your ArcPod is live. During onboarding, use `/agent-name`, `/agent-title`, or `/agent-identity Name, title`.",
            session=session,
            deployment=deployment,
            buttons=(_button("Take Me Aboard", command="/packages", style="secondary"),),
        )
    result = update_arclink_deployment_identity(
        conn,
        deployment=deployment,
        agent_name=agent_name,
        agent_title=agent_title,
        actor_id=str(deployment.get("user_id") or "").strip(),
        reason="public_bot updated Agent identity",
        channel=channel,
        projection_source="public_bot_agent_identity_update",
    )
    updated = result["deployment"]
    label = str(updated.get("agent_name") or _agent_label(updated)).strip()
    title = str(updated.get("agent_title") or "").strip()
    title_line = f", {title}" if title else ""
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="agent_identity_updated",
        reply=(
            f"Agent identity updated: {label}{title_line}.\n\n"
            "Raven recorded the change; managed context will carry the new identity on the next refresh."
        ),
        session=session,
        deployment=updated,
        buttons=(_button("Show My Crew", command="/agents", style="secondary"),),
    )


def _deployments_for_user(conn: sqlite3.Connection, user_id: str) -> list[dict[str, Any]]:
    clean_user_id = str(user_id or "").strip()
    if not clean_user_id:
        return []
    rows = conn.execute(
        """
        SELECT *
        FROM arclink_deployments
        WHERE user_id = ?
          AND status NOT IN ('cancelled', 'teardown_complete')
        ORDER BY
          CASE status
            WHEN 'active' THEN 0
            WHEN 'first_contacted' THEN 1
            WHEN 'provisioning_ready' THEN 2
            WHEN 'provisioning' THEN 3
            WHEN 'entitlement_required' THEN 4
            WHEN 'provisioning_failed' THEN 5
            ELSE 6
          END,
          created_at ASC,
          deployment_id ASC
        """,
        (clean_user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _agent_label(
    deployment: Mapping[str, Any],
    *,
    index: int = 0,
    conn: sqlite3.Connection | None = None,
) -> str:
    """Pick the friendliest available label for this deployment.

    Order of preference:
    1. Explicit metadata.agent_name / metadata.display_name
    2. Explicit agent_id
    3. A clean "Agent #<prefix-tail>" rather than the cryptic Title-Cased hash
    4. "Agent N" as a last resort.

    The onboarding display_name_hint is the human's name, not the agent's
    name. Reusing it here makes the roster read as if the agent were named
    after the user.
    """
    metadata = _metadata(deployment)
    candidate = str(deployment.get("agent_name") or metadata.get("agent_name") or metadata.get("display_name") or "").strip()
    if candidate:
        return candidate[:40]

    agent_id = str(deployment.get("agent_id") or "").strip()
    if agent_id:
        return agent_id[:40]
    prefix = str(deployment.get("prefix") or "").strip()
    if prefix:
        prefix_tail = prefix.rsplit("-", 1)[-1][:8]
        if prefix_tail:
            return f"Agent #{prefix_tail}"
    return f"Agent {index + 1}"


def _agent_slug(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(label or "").strip().lower()).strip("-")
    return slug or "agent"


def _agent_selector_aliases(deployment: Mapping[str, Any], *, label: str, index: int) -> set[str]:
    aliases: set[str] = set()

    def add(value: str) -> None:
        slug = _agent_slug(value)
        if not slug:
            return
        aliases.add(slug)
        if slug.startswith("agent-") and len(slug) > len("agent-"):
            aliases.add(slug[len("agent-") :])

    metadata = _metadata(deployment)
    for candidate in (
        label,
        str(deployment.get("agent_name") or ""),
        str(metadata.get("agent_name") or ""),
        str(metadata.get("display_name") or ""),
        str(deployment.get("agent_id") or ""),
        str(deployment.get("deployment_id") or ""),
    ):
        if candidate.strip():
            add(candidate)

    prefix = str(deployment.get("prefix") or "").strip()
    if prefix:
        add(prefix)
        tail = prefix.rsplit("-", 1)[-1]
        if tail:
            add(tail)
            numeric_tail = re.sub(r"^[a-z]+", "", tail.lower()).strip()
            if numeric_tail:
                add(numeric_tail)

    one_based = str(index + 1)
    aliases.add(one_based)
    aliases.add(f"agent-{one_based}")
    return aliases


def _agent_requested_aliases(requested: str) -> set[str]:
    slug = _agent_slug(requested)
    aliases = {slug}
    if slug.startswith("agent-") and len(slug) > len("agent-"):
        aliases.add(slug[len("agent-") :])
    return {item for item in aliases if item}


def _find_agent_deployment(
    deployments: list[dict[str, Any]],
    requested: str,
    *,
    conn: sqlite3.Connection | None = None,
) -> tuple[dict[str, Any], str] | None:
    requested_aliases = _agent_requested_aliases(requested)
    if not requested_aliases:
        return None
    for index, item in enumerate(deployments):
        label = _agent_label(item, index=index, conn=conn)
        if requested_aliases & _agent_selector_aliases(item, label=label, index=index):
            return item, label
    return None


def _metadata(row: Mapping[str, Any] | None) -> dict[str, Any]:
    return json_loads_safe(str((row or {}).get("metadata_json") or "{}"))


def _agent_command_names_from_context(
    turn_metadata: Mapping[str, Any],
    session: Mapping[str, Any] | None,
) -> set[str]:
    names: set[str] = set()
    session_meta = _metadata(session)
    for source in (turn_metadata, session_meta):
        for key in ("active_agent_command_names", "telegram_active_agent_command_names"):
            raw = source.get(key) if isinstance(source, Mapping) else None
            if isinstance(raw, (list, tuple, set)):
                for item in raw:
                    name = _public_bot_command_name(f"/{item}")
                    if name:
                        names.add(name)
    return names


def _deployment_plan_id(session: Mapping[str, Any] | None, deployment: Mapping[str, Any] | None) -> str:
    metadata = _metadata(deployment)
    plan = (
        str(metadata.get("selected_plan_id") or "").strip()
        or str((session or {}).get("selected_plan_id") or "").strip()
    )
    return _normalize_public_bot_plan(plan) or "sovereign"


def _agent_expansion_price_label(plan: str) -> str:
    return (
        f"${SCALE_AGENT_EXPANSION_MONTHLY_DOLLARS}/month"
        if _normalize_public_bot_plan(plan) == "scale"
        else f"${SOVEREIGN_AGENT_EXPANSION_MONTHLY_DOLLARS}/month"
    )


def _money(cents: int, *, currency: str = "usd") -> str:
    symbol = "$" if str(currency or "").lower() == "usd" else f"{str(currency or '').upper()} "
    whole, remainder = divmod(max(0, int(cents or 0)), 100)
    if remainder:
        return f"{symbol}{whole}.{remainder:02d}"
    return f"{symbol}{whole}"


def _parse_refuel_amount_cents(value: str) -> int:
    raw = str(value or "").strip().replace(",", "")
    if not raw:
        return 0
    match = re.search(r"\$?\s*([0-9]+(?:\.[0-9]{1,2})?)", raw)
    if not match:
        return 0
    try:
        dollars = Decimal(match.group(1))
    except InvalidOperation:
        return 0
    cents = int((dollars * Decimal("100")).to_integral_value())
    return cents if cents > 0 else 0


def _refuel_quote_lines(pricing: Mapping[str, Any]) -> list[str]:
    currency = str(pricing.get("currency") or "usd")
    lines = [
        "ArcPod fuel is prepaid model budget for your active Agent.",
        "Raven opens ArcPod Refueling, then the Control Node spends fuel at the selected model's current catalog price.",
        "",
        "| Refuel | Model fuel added | Reference capacity |",
        "| --- | --- | --- |",
    ]
    for quote in pricing.get("options") or ():
        if not isinstance(quote, Mapping):
            continue
        lines.append(
            "| "
            f"{_money(int(quote.get('retail_cents') or 0), currency=currency)} | "
            f"{_money(int(quote.get('provider_credit_cents') or 0), currency=currency)} | "
            f"~{quote.get('estimated_million_input_output_pairs') or 0} x (1M input + 1M output) |"
        )
    lines.extend(
        [
            "",
            (
                f"Reference model: {pricing.get('reference_model') or 'current routed model'} "
                f"at {_money(int(pricing.get('reference_input_cents_per_million') or 0), currency=currency)}/1M input "
                f"and {_money(int(pricing.get('reference_output_cents_per_million') or 0), currency=currency)}/1M output."
            ),
            (
                f"Custom refueling is available from "
                f"{_money(int(pricing.get('custom_min_cents') or 0), currency=currency)} to "
                f"{_money(int(pricing.get('custom_max_cents') or 0), currency=currency)}. "
                "Send `/refuel 40` or `/top-up 40` for a custom $40 checkout."
            ),
        ]
    )
    return lines


def _refuel_checkout_metadata(
    *,
    user_id: str,
    deployment_id: str,
    quote: Mapping[str, Any],
) -> dict[str, str]:
    return {
        "arclink_purchase_kind": "inference_refuel",
        "purchase_kind": "inference_refuel",
        "arclink_user_id": user_id,
        "user_id": user_id,
        "arclink_deployment_id": deployment_id,
        "deployment_id": deployment_id,
        "retail_cents": str(int(quote.get("retail_cents") or 0)),
        "credit_cents": str(int(quote.get("provider_credit_cents") or 0)),
        "provider_credit_bps": str(int(quote.get("provider_credit_bps") or 0)),
        "sku_id": str(quote.get("sku_id") or "arclink-arcpod-fuel"),
    }


def _refuel_line_items(quote: Mapping[str, Any]) -> list[dict[str, Any]]:
    price_data: dict[str, Any] = {
        "currency": str(quote.get("currency") or "usd"),
        "unit_amount": int(quote.get("retail_cents") or 0),
    }
    product_id = str(quote.get("stripe_product_id") or "").strip()
    if product_id:
        price_data["product"] = product_id
    else:
        price_data["product_data"] = {
            "name": str(quote.get("product_name") or "ArcPod Refueling"),
            "metadata": {
                "arclink_sku_id": str(quote.get("sku_id") or "arclink-arcpod-fuel"),
                "arclink_product_kind": "inference_refuel",
            },
        }
    return [{"price_data": price_data, "quantity": 1}]


def _refuel_reply(
    *,
    conn: sqlite3.Connection,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
    stripe_client: Any | None,
    requested_value: str,
    base_domain: str = "",
) -> ArcLinkPublicBotTurn:
    if not session or not deployment:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="refuel_unavailable",
            reply=_need_finished_onboarding_reply(),
            session=session,
            deployment=deployment,
            buttons=(_button("Take Me Aboard", command="/packages"),),
        )
    if str(deployment.get("status") or "") not in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="refuel_blocked",
            reply=_deployment_not_ready_reply(deployment),
            session=session,
            deployment=deployment,
            buttons=(_button("Check Status", command="/status", style="secondary"),),
        )
    pricing = arclink_refuel_topup_options()
    amount_cents = _parse_refuel_amount_cents(requested_value)
    if amount_cents <= 0:
        buttons = tuple(
            _button(
                f"Refuel {_money(int(quote.get('retail_cents') or 0), currency=str(pricing.get('currency') or 'usd'))}",
                command=f"/refuel {int(quote.get('retail_cents') or 0) // 100}",
            )
            for quote in pricing.get("options") or ()
            if isinstance(quote, Mapping)
        )
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="show_refuel_options",
            reply="\n".join(_refuel_quote_lines(pricing)),
            session=session,
            deployment=deployment,
            buttons=buttons,
        )
    if stripe_client is None:
        raise ArcLinkPublicBotError("ArcPod Refueling requires an injected Stripe client")
    try:
        quote = quote_arclink_refuel_topup(amount_cents)
    except ValueError as exc:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="refuel_invalid_amount",
            reply=f"{exc}\n\n" + "\n".join(_refuel_quote_lines(pricing)),
            session=session,
            deployment=deployment,
            buttons=(
                _button("Show Refueling", command="/refuel", style="secondary"),
            ),
        )
    user_id = str(deployment.get("user_id") or session.get("user_id") or "").strip()
    deployment_id = str(deployment.get("deployment_id") or "").strip()
    root = f"https://{str(base_domain or default_base_domain({})).strip().strip('/')}"
    checkout = stripe_client.create_checkout_session(
        user_id=user_id,
        price_id="",
        mode="payment",
        success_url=f"{root}/checkout/success?kind=refuel&deployment={deployment_id}",
        cancel_url=f"{root}/dashboard?tab=billing",
        client_reference_id=user_id,
        metadata=_refuel_checkout_metadata(user_id=user_id, deployment_id=deployment_id, quote=quote),
        idempotency_key=f"refuel:{deployment_id}:{quote['retail_cents']}:{secrets.token_hex(8)}",
        line_items=_refuel_line_items(quote),
    )
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=deployment_id,
        event_type="refuel_checkout_opened",
        metadata={
            "user_id": user_id,
            "retail_cents": int(quote.get("retail_cents") or 0),
            "provider_credit_cents": int(quote.get("provider_credit_cents") or 0),
            "checkout_session_id": str(checkout.get("id") or ""),
        },
    )
    checkout_session = {**dict(session), "checkout_url": str(checkout.get("url") or "")}
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="open_refuel_checkout",
        reply=(
            f"I opened ArcPod Refueling for {_money(int(quote['retail_cents']), currency=str(quote['currency']))}. "
            f"When Stripe clears it, {_money(int(quote['provider_credit_cents']), currency=str(quote['currency']))} becomes model fuel for this ArcPod."
        ),
        session=checkout_session,
        deployment=deployment,
        buttons=(
            _button(f"Refuel {_money(int(quote['retail_cents']), currency=str(quote['currency']))}", url=str(checkout.get("url") or "")),
            _button("Show My Crew", command="/agents", style="secondary"),
        ),
    )


def _update_session_metadata(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    updates: Mapping[str, Any],
    clear: tuple[str, ...] = (),
) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM arclink_onboarding_sessions WHERE session_id = ?", (session_id,)).fetchone()
    if row is None:
        raise KeyError(session_id)
    payload = _metadata(dict(row))
    for key in clear:
        payload.pop(key, None)
    payload.update(dict(updates))
    conn.execute(
        """
        UPDATE arclink_onboarding_sessions
        SET metadata_json = ?, current_step = ?, updated_at = ?
        WHERE session_id = ?
        """,
        (
            json_dumps_safe(payload, label="ArcLink public bot workflow", error_cls=ArcLinkPublicBotError),
            str(payload.get("public_bot_workflow") or ""),
            utc_now_iso(),
            session_id,
        ),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM arclink_onboarding_sessions WHERE session_id = ?", (session_id,)).fetchone())


def _clear_session_workflow(conn: sqlite3.Connection, *, session_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM arclink_onboarding_sessions WHERE session_id = ?", (session_id,)).fetchone()
    if row is None:
        raise KeyError(session_id)
    payload = _metadata(dict(row))
    payload.pop("public_bot_workflow", None)
    conn.execute(
        """
        UPDATE arclink_onboarding_sessions
        SET metadata_json = ?, updated_at = ?
        WHERE session_id = ?
        """,
        (
            json_dumps_safe(payload, label="ArcLink public bot workflow", error_cls=ArcLinkPublicBotError),
            utc_now_iso(),
            session_id,
        ),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM arclink_onboarding_sessions WHERE session_id = ?", (session_id,)).fetchone())


def _deployment_context(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    session = _latest_session_for_contact(conn, channel=channel, channel_identity=channel_identity)
    return session, _deployment_for_session(conn, session)


def _deployment_status_marker(deployment: Mapping[str, Any], *, active_id: str = "") -> str:
    status = str(deployment.get("status") or "unknown")
    if str(deployment.get("deployment_id") or "") == active_id and status in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES:
        return "at helm"
    if status in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES:
        return "ready"
    if status in ARCLINK_PUBLIC_BOT_DEPLOYMENT_RETIRING_STATUSES:
        return "retiring"
    if status in ARCLINK_PUBLIC_BOT_DEPLOYMENT_RETIRED_STATUSES:
        return "retired"
    if status == "teardown_failed":
        return "retirement needs operator attention"
    return status.replace("_", " ")


def _agent_title(deployment: Mapping[str, Any], *, index: int = 0) -> str:
    metadata = _metadata(deployment)
    title = str(deployment.get("agent_title") or metadata.get("agent_title") or "").strip()
    if title:
        return title[:80]
    return str(default_arclink_agent_profile(index + 1).get("title") or "ArcLink Agent")


def _agent_theme_label(deployment: Mapping[str, Any], *, index: int = 0) -> str:
    metadata = _metadata(deployment)
    label = str(metadata.get("theme_label") or metadata.get("theme_accent_name") or "").strip()
    if label:
        return label[:64]
    return str(default_arclink_agent_profile(index + 1).get("theme_label") or "ArcLink Signal Orange")


def _crew_roster_lines_and_buttons(
    deployments: list[dict[str, Any]],
    *,
    active_id: str = "",
    conn: sqlite3.Connection,
    include_links: bool = True,
) -> tuple[list[str], list[ArcLinkPublicBotButton]]:
    lines: list[str] = []
    buttons: list[ArcLinkPublicBotButton] = []
    for index, item in enumerate(deployments):
        label = _agent_label(item, index=index, conn=conn)
        title = _agent_title(item, index=index)
        theme = _agent_theme_label(item, index=index)
        marker = _deployment_status_marker(item, active_id=active_id)
        suffix = f" - {marker}" if marker not in {"ready", "at helm"} else ""
        lines.append(f"- {label} - {title} ({theme}){suffix}")
        if include_links and str(item.get("status") or "") in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES:
            dashboard = str(_deployment_access(item).get("dashboard") or "").strip()
            if dashboard:
                lines.append(f"  Helm: {dashboard}")
                buttons.append(_button(f"Open {label}"[:80], url=dashboard, style="secondary"))
    return lines, buttons


def _deployment_can_anchor_add_agent(deployment: Mapping[str, Any] | None) -> bool:
    if not deployment:
        return False
    return str(deployment.get("status") or "").strip() in ARCLINK_PUBLIC_BOT_ADD_AGENT_ANCHOR_STATUSES


def _retire_agent_workflow_data(session: Mapping[str, Any]) -> dict[str, Any]:
    payload = _metadata(session).get("retire_agent")
    return dict(payload) if isinstance(payload, Mapping) else {}


def _retire_agent_typed_name_matches(data: Mapping[str, Any], value: str) -> bool:
    clean = str(value or "").strip()
    if not clean:
        return False
    candidates = {
        str(data.get("agent_label") or "").strip(),
        str(data.get("agent_slug") or "").strip(),
        str(data.get("deployment_id") or "").strip(),
        str(data.get("prefix") or "").strip(),
    }
    slugs = {_agent_slug(candidate) for candidate in candidates if candidate}
    normalized = clean.lower()
    return normalized in {candidate.lower() for candidate in candidates if candidate} or _agent_slug(clean) in slugs


def _next_ready_deployment_for_user(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    exclude_deployment_id: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM arclink_deployments
        WHERE user_id = ?
          AND deployment_id <> ?
          AND status = 'active'
        ORDER BY updated_at DESC, created_at DESC, deployment_id DESC
        LIMIT 1
        """,
        (str(user_id or "").strip(), str(exclude_deployment_id or "").strip()),
    ).fetchone()
    return dict(row) if row is not None else None


def _clear_active_deployment_references(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    deployment_id: str,
    current_session_id: str = "",
    next_deployment: Mapping[str, Any] | None = None,
) -> int:
    rows = conn.execute(
        """
        SELECT session_id, deployment_id, metadata_json
        FROM arclink_onboarding_sessions
        WHERE user_id = ?
        """,
        (str(user_id or "").strip(),),
    ).fetchall()
    touched = 0
    next_id = str((next_deployment or {}).get("deployment_id") or "").strip()
    next_label = _agent_label(next_deployment, conn=conn) if next_deployment else ""
    for row in rows:
        session_id = str(row["session_id"] or "")
        payload = _metadata(dict(row))
        active_id = str(payload.get("active_deployment_id") or "").strip()
        owns_target = str(row["deployment_id"] or "").strip() == deployment_id
        current = session_id == current_session_id
        if active_id != deployment_id and not owns_target and not current:
            continue
        if next_id:
            payload["active_deployment_id"] = next_id
            payload["active_agent_label"] = next_label
        else:
            payload.pop("active_deployment_id", None)
            payload.pop("active_agent_label", None)
        retire_data = payload.get("retire_agent")
        retire_deployment_id = str(retire_data.get("deployment_id") if isinstance(retire_data, Mapping) else "")
        if current or retire_deployment_id == deployment_id:
            for key in RETIRE_AGENT_WORKFLOW_KEYS:
                payload.pop(key, None)
        conn.execute(
            """
            UPDATE arclink_onboarding_sessions
            SET metadata_json = ?, current_step = ?, updated_at = ?
            WHERE session_id = ?
            """,
            (
                json_dumps_safe(payload, label="ArcLink public bot retirement workflow", error_cls=ArcLinkPublicBotError),
                str(payload.get("public_bot_workflow") or ""),
                utc_now_iso(),
                session_id,
            ),
        )
        touched += 1
    return touched


def _cancel_pending_public_agent_turns_for_deployment(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    reason: str,
) -> int:
    rows = conn.execute(
        """
        SELECT id, extra_json
        FROM notification_outbox
        WHERE target_kind = 'public-agent-turn'
          AND delivered_at IS NULL
        """
    ).fetchall()
    ids: list[int] = []
    for row in rows:
        extra = json_loads_safe(str(row["extra_json"] or "{}"))
        if str(extra.get("deployment_id") or "").strip() == deployment_id:
            ids.append(int(row["id"]))
    if not ids:
        return 0
    now = utc_now_iso()
    for row_id in ids:
        conn.execute(
            """
            UPDATE notification_outbox
            SET delivered_at = ?,
                delivery_error = ?
            WHERE id = ?
            """,
            (now, reason[:500], row_id),
        )
    return len(ids)


def _retire_agent_deployment(
    conn: sqlite3.Connection,
    *,
    session: Mapping[str, Any],
    data: Mapping[str, Any],
    channel: str,
    channel_identity: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None, int]:
    deployment_id = str(data.get("deployment_id") or "").strip()
    user_id = str(data.get("user_id") or session.get("user_id") or "").strip()
    row = conn.execute(
        "SELECT * FROM arclink_deployments WHERE deployment_id = ? AND user_id = ?",
        (deployment_id, user_id),
    ).fetchone()
    if row is None:
        raise ArcLinkPublicBotError("That Agent is no longer on this account.")
    deployment = dict(row)
    status = str(deployment.get("status") or "").strip()
    next_deployment = _next_ready_deployment_for_user(conn, user_id=user_id, exclude_deployment_id=deployment_id)
    if status in ARCLINK_PUBLIC_BOT_DEPLOYMENT_RETIRING_STATUSES | ARCLINK_PUBLIC_BOT_DEPLOYMENT_RETIRED_STATUSES:
        _clear_active_deployment_references(
            conn,
            user_id=user_id,
            deployment_id=deployment_id,
            current_session_id=str(session.get("session_id") or ""),
            next_deployment=next_deployment,
        )
        conn.commit()
        updated_session = dict(conn.execute("SELECT * FROM arclink_onboarding_sessions WHERE session_id = ?", (str(session["session_id"]),)).fetchone())
        return updated_session, deployment, next_deployment, 0
    if status not in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES:
        raise ArcLinkPublicBotError(f"That Agent is currently `{status.replace('_', ' ')}` and cannot be retired from chat yet.")

    now = utc_now_iso()
    restore_until = utc_after_seconds_iso(30 * 24 * 60 * 60)
    metadata_json = _metadata(deployment)
    chutes_meta = dict(metadata_json.get("chutes") if isinstance(metadata_json.get("chutes"), Mapping) else {})
    chutes_meta.update({
        "status": "suspended",
        "suspended": True,
        "suspended_reason": "agent_retired",
        "suspended_at": now,
    })
    teardown_meta = dict(metadata_json.get("teardown") if isinstance(metadata_json.get("teardown"), Mapping) else {})
    teardown_meta.update({
        "reason": "agent_retirement",
        "requested_at": now,
        "remove_volumes": False,
        "preserve_state": True,
    })
    metadata_json["chutes"] = chutes_meta
    metadata_json["teardown"] = teardown_meta
    metadata_json["retirement"] = {
        "status": "requested",
        "requested_at": now,
        "requested_by_user_id": user_id,
        "requested_channel": channel,
        "requested_channel_identity": channel_identity,
        "agent_label": str(data.get("agent_label") or _agent_label(deployment, conn=conn)),
        "previous_status": status,
        "restore_until": restore_until,
        "state_policy": "preserve_volumes_for_restore",
        "routing_policy": "stop_chat_routing_immediately",
        "renewal_policy": "cancel_agent_renewal_at_period_end",
        "proration_policy": "no_automatic_proration",
        "usage_policy": "consumed_usage_is_final_and_new_spend_is_blocked",
        "unused_fuel_policy": "preserve_or_transfer_before_permanent_delete",
    }
    conn.execute(
        """
        UPDATE arclink_deployments
        SET status = 'teardown_requested',
            metadata_json = ?,
            updated_at = ?
        WHERE deployment_id = ?
          AND user_id = ?
        """,
        (
            json_dumps_safe(metadata_json, label="ArcLink deployment retirement metadata", error_cls=ArcLinkPublicBotError),
            now,
            deployment_id,
            user_id,
        ),
    )
    cancelled_pending = _cancel_pending_public_agent_turns_for_deployment(
        conn,
        deployment_id=deployment_id,
        reason="Agent retired before public chat turn delivery",
    )
    _clear_active_deployment_references(
        conn,
        user_id=user_id,
        deployment_id=deployment_id,
        current_session_id=str(session.get("session_id") or ""),
        next_deployment=next_deployment,
    )
    append_arclink_audit(
        conn,
        action="agent_retirement_requested",
        actor_id=user_id,
        target_kind="deployment",
        target_id=deployment_id,
        reason="Captain confirmed Agent retirement through Raven",
        metadata={
            "channel": channel,
            "channel_identity": channel_identity,
            "state_policy": "preserve_volumes_for_restore",
            "renewal_policy": "cancel_agent_renewal_at_period_end",
            "proration_policy": "no_automatic_proration",
            "cancelled_pending_public_agent_turns": cancelled_pending,
        },
        commit=False,
    )
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=deployment_id,
        event_type="agent_retirement_requested",
        metadata={
            "user_id": user_id,
            "channel": channel,
            "agent_label": str(data.get("agent_label") or ""),
            "restore_until": restore_until,
            "cancelled_pending_public_agent_turns": cancelled_pending,
        },
        commit=False,
    )
    conn.commit()
    updated_session = dict(conn.execute("SELECT * FROM arclink_onboarding_sessions WHERE session_id = ?", (str(session["session_id"]),)).fetchone())
    updated_deployment = dict(conn.execute("SELECT * FROM arclink_deployments WHERE deployment_id = ?", (deployment_id,)).fetchone())
    return updated_session, updated_deployment, next_deployment, cancelled_pending


def _retire_agent_start_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    requested_value: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
) -> ArcLinkPublicBotTurn:
    if not session or not deployment:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="retire_agent_unavailable",
            reply=_need_finished_onboarding_reply(),
            session=session,
            deployment=deployment,
            buttons=(_button("Take Me Aboard", command="/packages"),),
        )
    user_id = _raven_identity_user_id(session, deployment)
    deployments = _deployments_for_user(conn, user_id)
    requested = str(requested_value or "").strip()
    if not requested:
        retire_buttons = [
            _button(f"Retire: {_agent_label(item, index=index, conn=conn)}", command=f"/retire-agent-{_agent_slug(_agent_label(item, index=index, conn=conn))}", style="secondary")
            for index, item in enumerate(deployments)
            if str(item.get("status") or "") in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES
        ]
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="retire_agent_missing",
            reply="Which Agent should Raven retire? Use the roster button for the exact Agent you want to remove from active chat.",
            session=session,
            deployment=deployment,
            buttons=tuple(retire_buttons[:5]) + (_button("Show My Crew", command="/agents", style="secondary"),),
        )
    match = _find_agent_deployment(deployments, requested, conn=conn)
    if match is None:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="retire_agent_not_found",
            reply="That Agent is not on your roster. Open `/agents` and choose the retire button attached to the right Agent.",
            session=session,
            deployment=deployment,
            buttons=(_button("Show My Crew", command="/agents", style="secondary"),),
        )
    item, label = match
    status = str(item.get("status") or "")
    if status in ARCLINK_PUBLIC_BOT_DEPLOYMENT_RETIRING_STATUSES:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="retire_agent_already_running",
            reply=f"`{label}` is already retiring. Chat routing is closed for that Agent, and the pod teardown worker will preserve its state for restore.",
            session=session,
            deployment=item,
            buttons=(_button("Show My Crew", command="/agents", style="secondary"),),
        )
    if status in ARCLINK_PUBLIC_BOT_DEPLOYMENT_RETIRED_STATUSES:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="retire_agent_already_retired",
            reply=f"`{label}` is already retired. Its preserved state remains on the retention rail until an operator or restore flow removes it permanently.",
            session=session,
            deployment=item,
            buttons=(_button("Show My Crew", command="/agents", style="secondary"),),
        )
    if status not in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="retire_agent_not_ready",
            reply=f"`{label}` is `{status.replace('_', ' ')}` right now. Raven will only retire live Agents from chat; use `/status` or operator rails for provisioning failures.",
            session=session,
            deployment=item,
            buttons=(_button("Check Status", command="/status", style="secondary"),),
        )
    data = {
        "deployment_id": str(item.get("deployment_id") or ""),
        "user_id": user_id,
        "agent_label": label,
        "agent_slug": _agent_slug(label),
        "prefix": str(item.get("prefix") or ""),
        "requested_at": utc_now_iso(),
        "renewal_policy": "cancel_agent_renewal_at_period_end",
        "proration_policy": "no_automatic_proration",
        "usage_policy": "consumed_usage_is_final_and_new_spend_is_blocked",
        "state_policy": "preserve_volumes_for_restore",
    }
    updated = _update_session_metadata(
        conn,
        session_id=str(session["session_id"]),
        updates={
            "public_bot_workflow": "retire_agent_type_name",
            "retire_agent": data,
            "retire_agent_updated_at": utc_now_iso(),
        },
    )
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="retire_agent_confirm_name",
        reply=(
            f"Retiring `{label}` will stop Raven chat routing and new model spend immediately. "
            "The pod state is preserved for restore; renewal is recorded to stop at the period end with no automatic proration. "
            "Consumed token use stays final, and unused purchased fuel stays preserved or transferable before any permanent delete.\n\n"
            f"Type `{label}` to continue."
        ),
        session=updated,
        deployment=item,
        buttons=(_button("Cancel", command="/cancel-retire-agent", style="secondary"),),
    )


def _handle_retire_agent_workflow(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    message: str,
    command: str,
    session: Mapping[str, Any],
    deployment: Mapping[str, Any] | None,
    workflow: str,
) -> ArcLinkPublicBotTurn | None:
    if not workflow.startswith("retire_agent_"):
        return None
    data = _retire_agent_workflow_data(session)
    label = str(data.get("agent_label") or "this Agent")
    if command in ARCLINK_PUBLIC_BOT_CANCEL_COMMANDS or command in ARCLINK_PUBLIC_BOT_RETIRE_CANCEL_COMMANDS:
        updated = _update_session_metadata(
            conn,
            session_id=str(session["session_id"]),
            updates={},
            clear=RETIRE_AGENT_WORKFLOW_KEYS,
        )
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="retire_agent_cancelled",
            reply=f"`{label}` stays active. No routing, billing, or pod state changed.",
            session=updated,
            deployment=deployment,
            buttons=(_button("Show My Crew", command="/agents", style="secondary"),),
        )
    if workflow == "retire_agent_type_name":
        if command.startswith("/"):
            return None
        if not _retire_agent_typed_name_matches(data, message):
            return _turn(
                channel=channel,
                channel_identity=channel_identity,
                action="retire_agent_name_mismatch",
                reply=f"Type `{label}` exactly to continue, or send `cancel` to keep the Agent active.",
                session=session,
                deployment=deployment,
                buttons=(_button("Cancel", command="/cancel-retire-agent", style="secondary"),),
            )
        updated_data = dict(data)
        updated_data["typed_confirmation_at"] = utc_now_iso()
        updated = _update_session_metadata(
            conn,
            session_id=str(session["session_id"]),
            updates={
                "public_bot_workflow": "retire_agent_final_confirm",
                "retire_agent": updated_data,
                "retire_agent_updated_at": utc_now_iso(),
            },
        )
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="retire_agent_final_confirm",
            reply=(
                f"Final check: retire `{label}` now?\n\n"
                "Raven will close chat routing, cancel undelivered queued turns, suspend new model spend, queue state-preserving teardown, and record renewal/no-proration policy for billing rails."
            ),
            session=updated,
            deployment=deployment,
            buttons=(
                _button("Yes, Retire Agent", command="/confirm-retire-agent"),
                _button("No, Cancel", command="/cancel-retire-agent", style="secondary"),
            ),
        )
    if workflow == "retire_agent_final_confirm":
        if command not in ARCLINK_PUBLIC_BOT_RETIRE_CONFIRM_COMMANDS:
            return _turn(
                channel=channel,
                channel_identity=channel_identity,
                action="retire_agent_waiting_final_confirm",
                reply=f"Use `Yes, Retire Agent` to retire `{label}`, or `No, Cancel` to keep it active.",
                session=session,
                deployment=deployment,
                buttons=(
                    _button("Yes, Retire Agent", command="/confirm-retire-agent"),
                    _button("No, Cancel", command="/cancel-retire-agent", style="secondary"),
                ),
            )
        try:
            updated_session, retired_deployment, next_deployment, cancelled_pending = _retire_agent_deployment(
                conn,
                session=session,
                data=data,
                channel=channel,
                channel_identity=channel_identity,
            )
        except ArcLinkPublicBotError as exc:
            updated = _update_session_metadata(
                conn,
                session_id=str(session["session_id"]),
                updates={},
                clear=RETIRE_AGENT_WORKFLOW_KEYS,
            )
            return _turn(
                channel=channel,
                channel_identity=channel_identity,
                action="retire_agent_failed",
                reply=str(exc),
                session=updated,
                deployment=deployment,
                buttons=(_button("Show My Crew", command="/agents", style="secondary"),),
            )
        next_line = (
            f"\n\nFocus moved to `{_agent_label(next_deployment, conn=conn)}`."
            if next_deployment is not None
            else "\n\nNo other live Agent is at the helm. Add or restore an Agent when you are ready."
        )
        pending_line = f" Cancelled queued turns: {cancelled_pending}." if cancelled_pending else ""
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="retire_agent_requested",
            reply=(
                f"`{label}` is retired from active chat. New routing and model spend are stopped, and state-preserving teardown is queued."
                f"{pending_line}\n\n"
                "Billing policy recorded: stop this Agent's renewal at period end, no automatic proration, consumed tokens final, unused purchased fuel preserved or transferable before permanent delete."
                f"{next_line}"
            ),
            session=updated_session,
            deployment=next_deployment or retired_deployment,
            buttons=(
                _button("Show My Crew", command="/agents", style="secondary"),
                _button("Add Agent", command="/add-agent", style="secondary"),
            ),
        )
    return None


def _raven_name_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    message: str,
    command: str,
) -> ArcLinkPublicBotTurn:
    session, deployment = _deployment_context(conn, channel=channel, channel_identity=channel_identity)
    value = _raven_name_command_value(message, command)
    user_id = _raven_identity_user_id(session, deployment)
    current = _raven_display_name(
        conn,
        channel=channel,
        channel_identity=channel_identity,
        session=session,
        deployment=deployment,
    )
    if value is None:
        value = ""
    requested = value.strip()
    if not requested:
        account_line = "Account default: not available until this channel is linked to an ArcLink account."
        if user_id:
            row = conn.execute(
                """
                SELECT raven_display_name
                FROM arclink_public_bot_identity
                WHERE scope_kind = 'user'
                  AND user_id = ?
                  AND channel = ''
                  AND channel_identity = ''
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            account_line = f"Account default: `{str(row['raven_display_name'] or 'Raven') if row else 'Raven'}`."
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="raven_name_help",
            reply=(
                "Raven display names are local to ArcLink messages; Telegram and Discord profile names stay controlled by the platform bot registration.\n\n"
                f"Current name in this channel: `{current}`.\n"
                f"{account_line}\n\n"
                "Use `/raven_name channel <name>` for this channel, `/raven_name account <name>` for all linked channels, "
                "`/raven_name reset` for this channel, or `/raven_name reset-account` for the account default."
            ),
            session=session,
            deployment=deployment,
            bot_display_name=current,
            buttons=(
                _button("Show My Crew", command="/agents", style="secondary"),
                _button("Check Status", command="/status", style="secondary"),
            ),
        )

    parts = requested.split(maxsplit=1)
    selector = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""
    scope = "channel"
    reset = False
    raw_name = requested
    if selector in {"channel", "here"}:
        raw_name = rest
    elif selector in {"account", "user", "all"}:
        scope = "user"
        raw_name = rest
    elif selector in {"reset", "default"}:
        raw_name = ""
        reset = True
    elif selector in {"reset-account", "account-reset", "reset_account"}:
        scope = "user"
        raw_name = ""
        reset = True

    if scope == "user" and not user_id:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="raven_name_account_unavailable",
            reply=(
                "Account-wide Raven display names open after this channel is linked to an ArcLink account.\n\n"
                "I can still set a channel-only name here: `/raven_name channel <name>`."
            ),
            session=session,
            deployment=deployment,
            bot_display_name=current,
            buttons=(_button("Take Me Aboard", command="/packages", style="secondary"),),
        )
    if not raw_name and not reset:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="raven_name_missing",
            reply="Send the display name after the scope, for example `/raven_name channel Raven Prime`.",
            session=session,
            deployment=deployment,
            bot_display_name=current,
        )

    display_name = _clean_raven_display_name(raw_name)
    if scope == "user":
        _store_raven_display_name(
            conn,
            scope_kind="user",
            user_id=user_id,
            display_name=display_name,
        )
    else:
        _store_raven_display_name(
            conn,
            scope_kind="channel",
            user_id=user_id,
            channel=channel,
            channel_identity=channel_identity,
            display_name=display_name,
        )
        if user_id and not display_name:
            _store_raven_display_name(
                conn,
                scope_kind="channel",
                user_id="",
                channel=channel,
                channel_identity=channel_identity,
                display_name="",
            )

    updated = _raven_display_name(
        conn,
        channel=channel,
        channel_identity=channel_identity,
        session=session,
        deployment=deployment,
    )
    if scope == "user":
        action = "raven_name_account_reset" if not display_name else "raven_name_account_set"
        reply = (
            f"Account default reset. I will show as `{updated}` unless a channel override is set."
            if not display_name
            else f"Done. Across your linked ArcLink channels I will show as `{display_name}` unless a channel override is set."
        )
    else:
        action = "raven_name_channel_reset" if not display_name else "raven_name_channel_set"
        reply = (
            f"Channel override reset. I will show as `{updated}` here."
            if not display_name
            else f"Done. In this channel I will show as `{display_name}` in ArcLink messages."
        )
    reply += "\n\nPlatform bot profile names are not changed by this local preference."
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action=action,
        reply=reply,
        session=session,
        deployment=deployment,
        bot_display_name=updated,
        buttons=(
            _button("Show My Crew", command="/agents", style="secondary"),
            _button("Check Status", command="/status", style="secondary"),
        ),
    )


def _deployment_access(deployment: Mapping[str, Any]) -> dict[str, str]:
    metadata = _metadata(deployment)
    publish_state = metadata.get("tailnet_app_publication")
    tailnet_apps_unavailable = isinstance(publish_state, Mapping) and str(publish_state.get("status") or "") == "unavailable"
    base_domain = str(deployment.get("base_domain") or metadata.get("base_domain") or "").strip().lower().strip(".")
    ingress_mode = str(metadata.get("ingress_mode") or "").strip().lower()
    if not ingress_mode:
        ingress_mode = "tailscale" if base_domain.endswith(".ts.net") else "domain"
    tailscale_dns_name = str(metadata.get("tailscale_dns_name") or base_domain).strip().lower().strip(".")
    tailscale_strategy = str(metadata.get("tailscale_host_strategy") or "path").strip().lower()
    if ingress_mode == "tailscale" and tailscale_strategy == "path":
        if tailnet_apps_unavailable:
            return {"dashboard": f"https://{tailscale_dns_name or base_domain}/u/{deployment.get('prefix') or ''}"}
        tailnet_ports = metadata.get("tailnet_service_ports") if isinstance(metadata.get("tailnet_service_ports"), Mapping) else None
        try:
            hermes_port = int((tailnet_ports or {}).get("hermes") or 0)
        except (TypeError, ValueError):
            hermes_port = 0
        if 0 < hermes_port < 65536:
            access = arclink_access_urls(
                prefix=str(deployment.get("prefix") or ""),
                base_domain=base_domain,
                ingress_mode=ingress_mode,
                tailscale_dns_name=tailscale_dns_name,
                tailscale_host_strategy=tailscale_strategy,
                tailnet_service_ports=tailnet_ports,
            )
            access["notion"] = f"https://{tailscale_dns_name or base_domain}/u/{deployment.get('prefix') or ''}/notion/webhook"
            return access
        stored_urls = metadata.get("access_urls")
        if isinstance(stored_urls, Mapping):
            safe_urls = {
                str(role): str(url).strip()
                for role, url in stored_urls.items()
                if str(role).strip() and str(url).strip().startswith("https://")
            }
            if {"dashboard", "files", "code", "hermes"} <= set(safe_urls):
                return safe_urls
        return arclink_access_urls(
            prefix=str(deployment.get("prefix") or ""),
            base_domain=base_domain,
            ingress_mode=ingress_mode,
            tailscale_dns_name=tailscale_dns_name,
            tailscale_host_strategy=tailscale_strategy,
            tailnet_service_ports=tailnet_ports,
        )
    stored_urls = metadata.get("access_urls")
    if isinstance(stored_urls, Mapping):
        safe_urls = {
            str(role): str(url).strip()
            for role, url in stored_urls.items()
            if str(role).strip() and str(url).strip().startswith("https://")
        }
        if {"dashboard", "files", "code", "hermes"} <= set(safe_urls):
            return safe_urls
        if tailnet_apps_unavailable and safe_urls.get("dashboard"):
            return {"dashboard": safe_urls["dashboard"]}
    if ingress_mode == "tailscale" and tailnet_apps_unavailable:
        return {"dashboard": f"https://{tailscale_dns_name or base_domain}/u/{deployment.get('prefix') or ''}"}
    return arclink_access_urls(
        prefix=str(deployment.get("prefix") or ""),
        base_domain=base_domain,
        ingress_mode=ingress_mode,
        tailscale_dns_name=tailscale_dns_name,
        tailscale_host_strategy=tailscale_strategy,
    )


def _normalize_dashboard_username(value: str) -> str:
    clean = str(value or "").strip().lower()
    return "".join(ch for ch in clean if ch.isalnum() or ch in "@._-").strip(".-_") or ""


def _dashboard_username(conn: sqlite3.Connection, deployment: Mapping[str, Any]) -> str:
    metadata = _metadata(deployment)
    for candidate in (
        metadata.get("dashboard_username"),
        metadata.get("helm_username"),
        metadata.get("username"),
    ):
        value = _normalize_dashboard_username(str(candidate or ""))
        if value:
            return value
    user_id = str(deployment.get("user_id") or "").strip()
    if user_id:
        row = conn.execute("SELECT email FROM arclink_users WHERE user_id = ?", (user_id,)).fetchone()
        email = _normalize_dashboard_username(str(row["email"] or "")) if row is not None else ""
        if email:
            return email
        fallback_user = _normalize_dashboard_username(user_id)
        if fallback_user:
            return fallback_user
    prefix = str(deployment.get("prefix") or "").strip()
    if prefix:
        return _normalize_dashboard_username(prefix) or "arclink"
    return "arclink"


def _join_url_path(base_url: str, path: str) -> str:
    clean_base = str(base_url or "").strip().rstrip("/")
    if not clean_base:
        return ""
    if not clean_base.startswith(("https://", "http://")):
        clean_base = f"https://{clean_base}"
    clean_path = "/" + str(path or "/").strip().lstrip("/")
    return f"{clean_base}{clean_path}"


def _control_notion_webhook_public_url() -> str:
    explicit = str(os.environ.get("ARCLINK_NOTION_WEBHOOK_PUBLIC_URL") or "").strip()
    if explicit:
        return explicit
    path = str(
        os.environ.get("ARCLINK_TAILSCALE_NOTION_PATH")
        or os.environ.get("TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH")
        or "/notion/webhook"
    ).strip() or "/notion/webhook"
    control_url = str(os.environ.get("ARCLINK_TAILSCALE_CONTROL_URL") or "").strip()
    if control_url:
        return _join_url_path(control_url, path)
    host = str(
        os.environ.get("ARCLINK_TAILSCALE_DNS_NAME")
        or os.environ.get("TAILSCALE_DNS_NAME")
        or ""
    ).strip().lower().strip(".")
    if not host:
        return ""
    # This is the shared control-node callback, not an agent Helm/dashboard URL.
    # TAILSCALE_SERVE_PORT belongs to per-app Tailscale Serve publishing and can
    # point at the Hermes dashboard port (for example 8444); never let it leak
    # into the Notion webhook URL.
    port = str(
        os.environ.get("ARCLINK_TAILSCALE_HTTPS_PORT")
        or os.environ.get("TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT")
        or "443"
    ).strip()
    if port and port != "443":
        host = f"{host}:{port}"
    return _join_url_path(host, path)


def _notion_callback_url(deployment: Mapping[str, Any]) -> str:
    shared_url = _control_notion_webhook_public_url()
    if shared_url:
        return shared_url
    access = _deployment_access(deployment)
    if str(access.get("notion") or "").strip():
        return str(access.get("notion") or "").strip()
    dashboard_url = str(access.get("dashboard") or "").rstrip("/")
    return f"{dashboard_url}/notion/webhook" if dashboard_url else ""


def _dashboard_credential_row(conn: sqlite3.Connection, deployment: Mapping[str, Any]) -> dict[str, Any] | None:
    deployment_id = str(deployment.get("deployment_id") or "").strip()
    user_id = str(deployment.get("user_id") or "").strip()
    if not deployment_id or not user_id:
        return None
    now = utc_now_iso()
    expires_at = utc_after_seconds_iso(ARCLINK_CREDENTIAL_HANDOFF_TTL_SECONDS)
    metadata = _metadata(deployment)
    secret_ref = _dashboard_password_ref_for_handoff(
        deployment_id=deployment_id,
        user_id=user_id,
        metadata=metadata,
    )
    handoff_id = _stable_handoff_id(deployment_id, "dashboard_password")
    conn.execute(
        """
        INSERT INTO arclink_credential_handoffs (
          handoff_id, user_id, deployment_id, credential_kind, display_name,
          secret_ref, delivery_hint, status, expires_at, created_at, updated_at
        ) VALUES (?, ?, ?, 'dashboard_password', 'Dashboard password', ?, ?, 'available', ?, ?, ?)
        ON CONFLICT(deployment_id, credential_kind) DO UPDATE SET
          user_id = excluded.user_id,
          secret_ref = CASE
            WHEN arclink_credential_handoffs.status = 'available' THEN excluded.secret_ref
            ELSE arclink_credential_handoffs.secret_ref
          END,
          delivery_hint = CASE
            WHEN arclink_credential_handoffs.status = 'available' THEN excluded.delivery_hint
            ELSE arclink_credential_handoffs.delivery_hint
          END,
          expires_at = CASE
            WHEN arclink_credential_handoffs.status = 'available' AND arclink_credential_handoffs.expires_at = '' THEN excluded.expires_at
            ELSE arclink_credential_handoffs.expires_at
          END,
          updated_at = excluded.updated_at
        """,
        (
            handoff_id,
            user_id,
            deployment_id,
            secret_ref,
            "Copy this dashboard password into your password manager, then confirm storage.",
            expires_at,
            now,
            now,
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM arclink_credential_handoffs WHERE deployment_id = ? AND credential_kind = 'dashboard_password'",
        (deployment_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def _credentials_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
) -> ArcLinkPublicBotTurn:
    if deployment is None or str(deployment.get("status") or "") not in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="credentials_not_ready",
            reply=_need_finished_onboarding_reply(),
            session=session,
            deployment=deployment,
            buttons=(_button("Check Status", command="/status", style="secondary"),),
        )
    row = _dashboard_credential_row(conn, deployment)
    if row is None:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="credentials_unavailable",
            reply="I could not find the dashboard credential handoff for this deployment yet. Check status, then try `/credentials` again.",
            session=session,
            deployment=deployment,
            buttons=(_button("Check Status", command="/status", style="secondary"),),
        )
    if str(row.get("status") or "") == "removed" or str(row.get("removed_at") or "").strip():
        access = _deployment_access(deployment)
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="credentials_already_stored",
            reply=(
                "That credential handoff is already closed and removed from future responses.\n\n"
                "If you lost it, ask Raven or the operator to rotate/reissue dashboard access."
            ),
            session=session,
            deployment=deployment,
            buttons=tuple(
                button for button in (
                    _button("Open Helm", url=str(access.get("dashboard") or "")) if access.get("dashboard") else None,
                    _button("Check Status", command="/status", style="secondary"),
                )
                if button is not None
            ),
        )
    expire_revealable_user_material(conn)
    refreshed = conn.execute("SELECT * FROM arclink_credential_handoffs WHERE handoff_id = ?", (row["handoff_id"],)).fetchone()
    row = dict(refreshed) if refreshed is not None else None
    if row is None or str(row["status"] or "") in {"removed", "expired"} or str(row["revealed_at"] or ""):
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="credentials_reveal_unavailable",
            reply=(
                "That credential handoff is no longer revealable. "
                "Use the saved password, or ask Raven or the operator to rotate/reissue dashboard access."
            ),
            session=session,
            deployment=deployment,
            buttons=(_button("Check Status", command="/status", style="secondary"),),
        )
    raw_secret = _resolve_revealable_credential_secret(row)
    if not raw_secret:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="credentials_secret_not_materialized",
            reply=(
                "The dashboard credential exists, but the secure secret file is not materialized on this control node yet. "
                "I will not invent it. Check status, then try `/credentials` again; if it still does not appear, the operator should rotate/reissue dashboard access."
            ),
            session=session,
            deployment=deployment,
            buttons=(_button("Check Status", command="/status", style="secondary"),),
        )
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE arclink_credential_handoffs
        SET revealed_at = CASE WHEN revealed_at = '' THEN ? ELSE revealed_at END,
            updated_at = ?
        WHERE handoff_id = ? AND user_id = ?
        """,
        (now, now, row["handoff_id"], row["user_id"]),
    )
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=str(deployment.get("deployment_id") or ""),
        event_type="public_bot:dashboard_credential_revealed",
        metadata={"channel": channel, "credential_kind": "dashboard_password"},
        commit=False,
    )
    conn.commit()
    access = _deployment_access(deployment)
    helm = str(access.get("dashboard") or "").rstrip("/")
    username = _dashboard_username(conn, deployment)
    lines = [
        "Dashboard credential handoff.",
        "",
        "Use this exact Helm username and password. This same pair opens each of your ArcLink agent dashboards.",
        "",
        f"Username: `{username}`",
        "",
        f"Password: `{raw_secret}`",
        "",
        "Copy both into your password manager now. After you confirm storage, ArcLink removes the handoff from future responses.",
    ]
    if helm:
        lines.extend(["", f"Helm: {helm}"])
    telegram_lines = [
        "Dashboard credential handoff.",
        "",
        "Use this exact Helm username and password. This same pair opens each of your ArcLink agent dashboards.",
        "",
        f"Username: {username}",
        "",
        "Password:",
        raw_secret,
        "",
        "Copy both into your password manager now. After you confirm storage, ArcLink removes the handoff from future responses.",
    ]
    if helm:
        telegram_lines.extend(["", f"Helm: {helm}"])
    telegram_reply = "\n".join(telegram_lines)
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="credentials_revealed",
        reply="\n".join(lines),
        session=session,
        deployment=deployment,
        buttons=tuple(
            button for button in (
                _button("Copy Username", copy_text=username),
                _button("Copy Password", copy_text=raw_secret),
                _button("I Stored It", command="/credentials-stored"),
                _button("Open Helm", url=helm) if helm else None,
            )
            if button is not None
        ),
        telegram_reply=telegram_reply,
        telegram_entities=_telegram_code_entities(telegram_reply, (username, raw_secret)),
    )


def _credentials_stored_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
) -> ArcLinkPublicBotTurn:
    if deployment is None:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="credentials_ack_no_deployment",
            reply=_need_finished_onboarding_reply(),
            session=session,
            buttons=(_button("Check Status", command="/status", style="secondary"),),
        )
    row = _dashboard_credential_row(conn, deployment)
    if row is None:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="credentials_ack_unavailable",
            reply="I could not find an open dashboard credential handoff to close.",
            session=session,
            deployment=deployment,
            buttons=(_button("Check Status", command="/status", style="secondary"),),
        )
    user_id = str(deployment.get("user_id") or "")
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE arclink_credential_handoffs
        SET status = 'removed',
            acknowledged_at = CASE WHEN acknowledged_at = '' THEN ? ELSE acknowledged_at END,
            removed_at = CASE WHEN removed_at = '' THEN ? ELSE removed_at END,
            updated_at = ?
        WHERE handoff_id = ? AND user_id = ?
        """,
        (now, now, now, row["handoff_id"], user_id),
    )
    append_arclink_audit(
        conn,
        action="credential_handoff_acknowledged",
        actor_id=user_id,
        target_kind="credential_handoff",
        target_id=str(row["handoff_id"]),
        reason="user confirmed dashboard credential storage through Raven",
        metadata={"deployment_id": str(deployment.get("deployment_id") or ""), "credential_kind": "dashboard_password"},
        commit=False,
    )
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=str(deployment.get("deployment_id") or ""),
        event_type="credential_handoff_removed",
        metadata={"credential_kind": "dashboard_password", "user_id": user_id, "channel": channel},
        commit=False,
    )
    conn.commit()
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="credentials_stored",
        reply=(
            "Locked in. I removed that dashboard credential handoff from future ArcLink responses.\n\n"
            "Next clean moves: open Helm, wire Notion, or set private backups."
        ),
        session=session,
        deployment=deployment,
        buttons=(
            _button("Wire Notion", command="/connect_notion", style="secondary"),
            _button("Check Status", command="/status", style="secondary"),
        ),
    )


def _credential_handoffs_confirmed_for_setup(
    conn: sqlite3.Connection,
    deployment: Mapping[str, Any],
) -> tuple[bool, dict[str, Any]]:
    deployment_id = str(deployment.get("deployment_id") or "").strip()
    user_id = str(deployment.get("user_id") or "").strip()
    if not deployment_id or not user_id:
        return False, {"reason": "missing_deployment_identity", "pending": []}
    rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT credential_kind, display_name, status, acknowledged_at, removed_at
            FROM arclink_credential_handoffs
            WHERE deployment_id = ? AND user_id = ?
            ORDER BY credential_kind
            """,
            (deployment_id, user_id),
        ).fetchall()
    ]
    if not rows:
        return False, {"reason": "not_started", "pending": ["credential handoff"], "removed": []}
    pending = [
        str(row.get("display_name") or row.get("credential_kind") or "credential").strip()
        for row in rows
        if str(row.get("status") or "").strip() != "removed" and not str(row.get("removed_at") or "").strip()
    ]
    removed = [
        str(row.get("display_name") or row.get("credential_kind") or "credential").strip()
        for row in rows
        if str(row.get("status") or "").strip() == "removed" or str(row.get("removed_at") or "").strip()
    ]
    return not pending, {"reason": "pending" if pending else "confirmed", "pending": pending, "removed": removed}


def _credential_handoff_required_turn(
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any],
    deployment: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> ArcLinkPublicBotTurn:
    access = _deployment_access(deployment)
    helm = str(access.get("dashboard") or "").rstrip("/")
    pending = [item for item in summary.get("pending", []) if str(item).strip()]
    pending_line = ", ".join(str(item) for item in pending) if pending else "credential handoff"
    lines = [
        "I need the credential handoff closed before I open Notion setup.",
        "",
        f"Still waiting on: {pending_line}.",
        "",
        "Use `/credentials`, copy the dashboard password into your password manager, and confirm storage. After ArcLink removes that handoff from future responses, I can record the brokered SSOT setup intent.",
        "",
        "This keeps Notion setup on the dashboard/operator verification rail. No Notion tokens or API keys belong in chat.",
    ]
    if helm:
        lines.insert(3, f"Helm: {helm}")
        lines.insert(4, "")
    buttons: list[ArcLinkPublicBotButton] = []
    if helm:
        buttons.append(_button("Open Helm", url=helm))
    buttons.append(_button("Credentials", command="/credentials", style="secondary"))
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="connect_notion_credentials_required",
        reply="\n".join(lines),
        session=session,
        deployment=deployment,
        buttons=tuple(buttons),
    )


def _aboard_freeform_reply(
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any],
    bot_display_name: str = ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME,
    conn: sqlite3.Connection | None = None,
    source_kind: str = "chat",
    include_bridge_intro: bool = False,
) -> ArcLinkPublicBotTurn:
    """Queue a public-channel message or command for the selected agent.

    Raven-owned slash commands are handled before this function. Anything that
    reaches here belongs to the selected agent and is processed asynchronously
    so Telegram/Discord webhook handlers do not block on model runtime.
    """
    label = _agent_label(deployment, index=0, conn=conn)
    raven = bot_display_name or ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME
    access = _deployment_access(deployment)
    helm = str(access.get("dashboard") or "").rstrip("/")
    if conn is not None:
        extra = {
            "deployment_id": str(deployment.get("deployment_id") or ""),
            "prefix": str(deployment.get("prefix") or ""),
            "user_id": str(deployment.get("user_id") or ""),
            "agent_label": label,
            "raven_display_name": raven,
            "helm_url": helm,
            "source_kind": source_kind,
        }
        turn_metadata = deployment.get("_public_bot_metadata")
        reply_to_message_id = str(deployment.get("_public_bot_reply_to_message_id") or "").strip()
        if channel == "telegram" and reply_to_message_id:
            extra["telegram_reply_to_message_id"] = reply_to_message_id
        if channel == "telegram" and isinstance(turn_metadata, Mapping):
            for key in (
                "telegram_update_kind",
                "telegram_update_json",
                "telegram_native_callback",
            ):
                value = turn_metadata.get(key)
                if value not in (None, ""):
                    extra[key] = value
        if channel == "discord":
            if isinstance(turn_metadata, Mapping):
                for key in ("discord_channel_id", "discord_user_id", "discord_message_id", "discord_chat_type"):
                    value = str(turn_metadata.get(key) or "").strip()
                    if value:
                        extra[key] = value
            if reply_to_message_id and "discord_message_id" not in extra:
                extra["discord_message_id"] = reply_to_message_id
        queue_notification(
            conn,
            target_kind="public-agent-turn",
            target_id=channel_identity,
            channel_kind=channel,
            message=str(deployment.get("_public_bot_message") or ""),
            extra=extra,
        )
        append_arclink_event(
            conn,
            subject_kind="deployment",
            subject_id=str(deployment.get("deployment_id") or ""),
            event_type="public_bot:agent_turn_queued",
            metadata={"channel": channel, "agent_label": label, "source_kind": source_kind},
        )
    lines: list[str] = []
    if include_bridge_intro:
        lines.extend(
            [
                f"From now on, your normal messages in this channel will be routed to your active agent, **{label}**.",
                "Use `/raven` any time for ArcLink controls and agent selection. Bare slash commands belong to the agent at the helm.",
                "",
            ]
        )
    if include_bridge_intro:
        lines.extend(
            [
                "Your active agent replies here. Raven controls stay behind `/raven`; bare slash commands belong to the agent at the helm.",
            ]
        )
        if helm:
            lines.extend(["", f"Helm stays open too: {helm}"])
    buttons: list[ArcLinkPublicBotButton] = []
    if include_bridge_intro and helm:
        buttons.append(_button("Open Helm", url=helm))
    if include_bridge_intro:
        buttons.append(_button("Show My Crew", command="/agents", style="secondary"))
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="agent_message_queued",
        reply="\n".join(lines),
        session=session,
        deployment=deployment,
        bot_display_name=raven,
        buttons=tuple(buttons),
    )


def _need_finished_onboarding_reply() -> str:
    return (
        "That lane opens once your first agent is awake aboard ArcLink. Send `/start` and I will walk you through onboarding, "
        "or finish checkout if your launch is already in motion."
    )


def _deployment_not_ready_reply(deployment: Mapping[str, Any]) -> str:
    status = str(deployment.get("status") or "unknown").strip()
    phrase = launch_phrase(status)
    if status == "entitlement_required":
        return (
            f"{phrase} Stripe has not cleared the handoff yet - send `checkout` and I will reopen the gate."
        )
    if status == "provisioning_failed":
        return f"{phrase} Next: check `/status`; I will come back to you on this same channel the moment the lane is safe again."
    return f"{phrase} I will move when it reaches active - not before."


def _record_bot_action(
    conn: sqlite3.Connection,
    *,
    deployment: Mapping[str, Any],
    action: str,
    channel: str,
    channel_identity: str,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    deployment_id = str(deployment.get("deployment_id") or "").strip()
    if not deployment_id:
        return
    payload = {
        "action": action,
        "channel": channel,
        "channel_identity": channel_identity,
    }
    payload.update(dict(metadata or {}))
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=deployment_id,
        event_type=f"public_bot:{action}",
        metadata=payload,
    )


def _create_pair_channel_code(
    conn: sqlite3.Connection,
    *,
    session: Mapping[str, Any],
    deployment: Mapping[str, Any] | None,
) -> tuple[str, str]:
    session_id = str(session.get("session_id") or "").strip()
    if not session_id:
        raise ArcLinkPublicBotError("pair-channel requires an onboarding session")
    now = utc_now_iso()
    expires_at = utc_after_seconds_iso(PAIR_CODE_TTL_SECONDS)
    conn.execute(
        """
        UPDATE arclink_channel_pairing_codes
        SET status = 'superseded'
        WHERE source_session_id = ?
          AND status = 'open'
        """,
        (session_id,),
    )
    for _ in range(24):
        code = _new_pair_code()
        try:
            conn.execute(
                """
                INSERT INTO arclink_channel_pairing_codes (
                  code, source_session_id, source_channel, source_channel_identity,
                  user_id, deployment_id, status, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?)
                """,
                (
                    code,
                    session_id,
                    str(session.get("channel") or ""),
                    str(session.get("channel_identity") or ""),
                    str((deployment or {}).get("user_id") or session.get("user_id") or ""),
                    str((deployment or {}).get("deployment_id") or session.get("deployment_id") or ""),
                    now,
                    expires_at,
                ),
            )
            conn.commit()
            return code, expires_at
        except sqlite3.IntegrityError:
            continue
    raise ArcLinkPublicBotError("could not mint an ArcLink pair-channel code")


def _pair_channel_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any],
    deployment: Mapping[str, Any] | None,
    code_value: str,
    bot_display_name: str = ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME,
) -> ArcLinkPublicBotTurn:
    raven = bot_display_name or ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME
    clean_code = _normalize_pair_code(code_value)
    if not clean_code:
        code, expires_at = _create_pair_channel_code(conn, session=session, deployment=deployment)
        updated = _update_session_metadata(
            conn,
            session_id=str(session["session_id"]),
            updates={
                "public_bot_workflow": "pair_channel",
                "pair_channel_code": code,
                "pair_channel_expires_at": expires_at,
            },
        )
        live_note = (
            "If your agent is already online, the other channel gets the same ArcLink identity, crew, tools, vault, Notion lane, and status. "
            "The chat session stays separate; ArcLink links both channels to the same agent account."
            if deployment
            else "If you are still prelaunch, the other channel joins this same launch path."
        )
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="pair_channel_code",
            reply=(
                "Pairing lane open.\n\n"
                f"On the other channel, tell {raven}: `/link-channel {code}`\n\n"
                f"This code expires in 10 minutes. {live_note}"
            ),
            session=updated,
            deployment=deployment,
            bot_display_name=raven,
            buttons=(
                _button("Show My Crew", command="/agents", style="secondary"),
                _button("Check Status", command="/status", style="secondary"),
            ),
        )

    if not ARCLINK_PUBLIC_BOT_PAIR_CODE_RE.fullmatch(clean_code):
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="pair_channel_invalid_code",
            reply="That pairing code does not look right. Open `/link-channel` on the other channel and send me the six-character code it gives you.",
            session=session,
            deployment=deployment,
            bot_display_name=raven,
            buttons=(_button("Try Again", command="/link-channel", style="secondary"),),
        )

    row = conn.execute(
        """
        SELECT *
        FROM arclink_channel_pairing_codes
        WHERE code = ?
          AND status = 'open'
        """,
        (clean_code,),
    ).fetchone()
    now = utc_now_iso()
    if row is None or str(row["expires_at"] or "") < now:
        if row is not None:
            conn.execute("UPDATE arclink_channel_pairing_codes SET status = 'expired' WHERE code = ?", (clean_code,))
            conn.commit()
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="pair_channel_expired",
            reply="That pairing code has gone cold. Open `/link-channel` on the first channel and I will mint a fresh one.",
            session=session,
            deployment=deployment,
            bot_display_name=raven,
            buttons=(_button("Open Pairing", command="/link-channel", style="secondary"),),
        )
    source_channel = str(row["source_channel"] or "")
    source_identity = str(row["source_channel_identity"] or "")
    if source_channel == channel and source_identity == channel_identity:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="pair_channel_same_channel",
            reply="You are holding that code in the channel that minted it. Take it to the other channel and I will bridge the identity there.",
            session=session,
            deployment=deployment,
            bot_display_name=raven,
        )

    source_user_id = str(row["user_id"] or "").strip()
    source_deployment_id = str(row["deployment_id"] or "").strip()
    target_user_id = str(session.get("user_id") or "").strip()
    target_deployment_id = str(session.get("deployment_id") or "").strip()
    if target_user_id:
        target_is_other_account = not source_user_id or target_user_id != source_user_id
    else:
        target_is_other_account = bool(
            target_deployment_id
            and (not source_deployment_id or target_deployment_id != source_deployment_id)
        )
    if target_is_other_account:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="pair_channel_account_mismatch",
            reply=(
                "That channel is already linked to a different ArcLink account. "
                "Open `/link-channel` from the account you want to use, or continue in the original channel."
            ),
            session=session,
            deployment=deployment,
            bot_display_name=raven,
            buttons=(_button("Show My Crew", command="/agents", style="secondary"),),
        )

    target = handoff_arclink_onboarding_channel(
        conn,
        source_session_id=str(row["source_session_id"]),
        target_channel=channel,
        target_channel_identity=channel_identity,
    )
    source = conn.execute("SELECT * FROM arclink_onboarding_sessions WHERE session_id = ?", (str(row["source_session_id"]),)).fetchone()
    source_meta = _metadata(dict(source or {}))
    target_updates: dict[str, Any] = {
        "paired_from_session_id": str(row["source_session_id"]),
        "paired_from_channel": source_channel,
        "paired_from_channel_identity": source_identity,
        "paired_at": now,
    }
    active_deployment_id = str(source_meta.get("active_deployment_id") or row["deployment_id"] or target.get("deployment_id") or "")
    if active_deployment_id:
        target_updates["active_deployment_id"] = active_deployment_id
    target = _update_session_metadata(
        conn,
        session_id=str(target["session_id"]),
        updates=target_updates,
        clear=("public_bot_workflow", "pair_channel_code", "pair_channel_expires_at"),
    )
    _update_session_metadata(
        conn,
        session_id=str(row["source_session_id"]),
        updates={
            "paired_to_session_id": str(target["session_id"]),
            "paired_to_channel": channel,
            "paired_to_channel_identity": channel_identity,
            "paired_at": now,
        },
        clear=("public_bot_workflow", "pair_channel_code", "pair_channel_expires_at"),
    )
    conn.execute(
        """
        UPDATE arclink_channel_pairing_codes
        SET status = 'claimed',
            claimed_session_id = ?,
            claimed_channel = ?,
            claimed_channel_identity = ?,
            claimed_at = ?
        WHERE code = ?
        """,
        (str(target["session_id"]), channel, channel_identity, now, clean_code),
    )
    conn.commit()
    linked_deployment = _deployment_for_session(conn, target)
    if linked_deployment:
        _record_bot_action(
            conn,
            deployment=linked_deployment,
            action="pair_channel_claimed",
            channel=channel,
            channel_identity=channel_identity,
            metadata={"source_channel": source_channel, "target_session_id": str(target["session_id"])},
        )
    buttons: list[ArcLinkPublicBotButton] = [_button("Show My Crew", command="/agents", style="secondary")]
    access = _deployment_access(linked_deployment or {}) if linked_deployment else {}
    if access.get("dashboard"):
        buttons.insert(0, _button("Open Helm", url=str(access["dashboard"])))
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="pair_channel_claimed",
        reply=(
            "Channels paired.\n\n"
            "Same ArcLink identity, same crew, same tools, same vault, same Notion rail. "
            f"Telegram and Discord keep separate chat threads, but {raven} is now looking at the same ArcLink account."
        ),
        session=target,
        deployment=linked_deployment,
        bot_display_name=raven,
        buttons=tuple(buttons),
    )


def _connect_notion_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
) -> ArcLinkPublicBotTurn:
    if not session or not deployment:
        return _turn(channel=channel, channel_identity=channel_identity, action="connect_notion_unavailable", reply=_need_finished_onboarding_reply(), session=session)
    if str(deployment.get("status") or "") not in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="connect_notion_blocked",
            reply=_deployment_not_ready_reply(deployment),
            session=session,
            deployment=deployment,
        )
    confirmed, summary = _credential_handoffs_confirmed_for_setup(conn, deployment)
    if not confirmed:
        _record_bot_action(
            conn,
            deployment=deployment,
            action="connect_notion_credentials_required",
            channel=channel,
            channel_identity=channel_identity,
            metadata={"credential_handoff_status": str(summary.get("reason") or "unknown")},
        )
        return _credential_handoff_required_turn(
            channel=channel,
            channel_identity=channel_identity,
            session=session,
            deployment=deployment,
            summary=summary,
        )
    callback_url = _notion_callback_url(deployment)
    session = _update_session_metadata(
        conn,
        session_id=str(session["session_id"]),
        updates={
            "public_bot_workflow": "connect_notion",
            "connect_notion_requested_at": utc_now_iso(),
            "connect_notion_public_status": "awaiting_user_setup",
        },
    )
    _record_bot_action(
        conn,
        deployment=deployment,
        action="connect_notion_requested",
        channel=channel,
        channel_identity=channel_identity,
        metadata={
            "deployment_status": str(deployment.get("status") or ""),
            "setup_mode": "public_preparation_only",
        },
    )
    lines = [
        "Opening the Notion SSOT preparation lane for your ArcLink account.",
        "",
        "Current model: ArcLink uses a brokered shared-root Notion SSOT rail with dashboard/operator verification. This command records setup intent and callback only; it does not verify the Notion integration, install secrets, support user-owned OAuth, or bypass the verification rail.",
        "",
        "Drop this shared control-node callback into the Notion webhook/subscription panel:",
        callback_url or "(callback URL is not available yet)",
        "Do not add a Helm, Drive, Code, or Agent port/path to it.",
        "",
        "Then share the page or database with the ArcLink integration. Email sharing alone is not treated as proof of API access. No tokens in chat - when I need a secret, the secure dashboard field is the only door.",
        "",
        "Send `ready` after you finish the Notion-side setup. I will mark it ready for dashboard verification, or send `cancel` and I will seal the lane.",
    ]
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="connect_notion",
        reply="\n".join(lines),
        session=session,
        deployment=deployment,
    )


def _config_backup_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
) -> ArcLinkPublicBotTurn:
    if not session or not deployment:
        return _turn(channel=channel, channel_identity=channel_identity, action="config_backup_unavailable", reply=_need_finished_onboarding_reply(), session=session)
    if str(deployment.get("status") or "") not in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="config_backup_blocked",
            reply=_deployment_not_ready_reply(deployment),
            session=session,
            deployment=deployment,
        )
    session = _update_session_metadata(
        conn,
        session_id=str(session["session_id"]),
        updates={
            "public_bot_workflow": "config_backup_repo",
            "config_backup_requested_at": utc_now_iso(),
            "config_backup_public_status": "awaiting_private_repo",
        },
    )
    _record_bot_action(
        conn,
        deployment=deployment,
        action="config_backup_requested",
        channel=channel,
        channel_identity=channel_identity,
        metadata={
            "deployment_status": str(deployment.get("status") or ""),
            "setup_mode": "public_preparation_only",
        },
    )
    example = f"{str(deployment.get('user_id') or 'you').replace('_', '-')}/arclink-{str(deployment.get('prefix') or 'pod')}"
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="prompt_backup_repo",
        reply=(
            "Opening the private backup preparation lane.\n\n"
            "This public command records the intended private GitHub repository. It does not mint, install, or verify the deploy key; the dashboard/operator backup rail completes that step.\n\n"
            "Choose a private GitHub repository - this is where Hermes' home and the pod's configuration snapshots will rest after key setup is verified. "
            "Send me `owner/repo` and I will attach it to this deployment as pending setup.\n\n"
            f"Example: `{example}`\n\n"
            "Use a dedicated deploy key for this pod. The ArcLink upstream key and the arclink-priv backup key stay where they are."
        ),
        session=session,
        deployment=deployment,
    )


def _agents_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
) -> ArcLinkPublicBotTurn:
    if not session or not deployment:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="agents_unavailable",
            reply=(
                f"No crew on your manifest yet. Limited 100 Founders brings single-ArcPod access for ${FOUNDERS_MONTHLY_DOLLARS}/month. "
                f"Sovereign is ${SOVEREIGN_MONTHLY_DOLLARS}/month. Scale launches three agents with Federation for ${SCALE_MONTHLY_DOLLARS}/month."
            ),
            session=session,
            buttons=(
                _button("Take Me Aboard", command="/packages"),
            ),
        )
    user_id = str(deployment.get("user_id") or session.get("user_id") or "").strip()
    deployments = _deployments_for_user(conn, user_id)
    active_id = str(deployment.get("deployment_id") or "")
    roster_lines, open_buttons = _crew_roster_lines_and_buttons(deployments, active_id=active_id, conn=conn)
    lines = [
        "Your ArcLink crew",
        "",
        "Names, roles, and dashboard orientation:",
    ]
    lines.extend(roster_lines or ["- No active roster rows found yet."])
    lines.extend(
        [
            "",
            "Each Agent has one Helm link. Drive, Code, and Terminal live inside that Hermes dashboard as plugins; you do not need separate control links.",
            "Your dashboard username/password works across the Crew control interfaces. Use `/credentials` if you need the handoff again.",
            "",
            "Use `/train-crew` any time to recurate names, roles, personalities, and SOUL.md overlays. Use `/academy` to stage subject-matter specialist training for one Agent or the whole Crew. Use `/name Your Name` if you want the Crew to call you something other than your Telegram or Discord handle.",
        ]
    )
    buttons: list[ArcLinkPublicBotButton] = open_buttons[:4]
    buttons.extend(
        [
            _button("Train My Crew", command="/train-crew", style="secondary"),
            _button("Academy", command="/academy", style="secondary"),
            _button("Credentials", command="/credentials", style="secondary"),
        ]
    )
    if deployments:
        buttons.append(_button("Add Agent", command="/add-agent", style="secondary"))
    buttons = buttons[:8]
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="show_agents",
        reply="\n".join(lines),
        session=session,
        deployment=deployment,
        buttons=tuple(buttons),
    )


def _switch_agent_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    requested_slug: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
) -> ArcLinkPublicBotTurn:
    if not session or not deployment:
        return _turn(channel=channel, channel_identity=channel_identity, action="switch_agent_unavailable", reply=_need_finished_onboarding_reply(), session=session)
    deployments = _deployments_for_user(conn, str(deployment.get("user_id") or ""))
    match = _find_agent_deployment(deployments, requested_slug, conn=conn)
    if match is not None:
        item, label = match
        status = str(item.get("status") or "")
        if status not in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES:
            return _turn(
                channel=channel,
                channel_identity=channel_identity,
                action="switch_agent_not_ready",
                reply=f"`{label}` is {_deployment_status_marker(item)} and cannot take the helm. Choose a ready Agent from `/agents`.",
                session=session,
                deployment=deployment,
                buttons=(_button("Show My Crew", command="/agents", style="secondary"),),
            )
        updated = _update_session_metadata(
            conn,
            session_id=str(session["session_id"]),
            updates={"active_deployment_id": str(item.get("deployment_id") or ""), "active_agent_label": label},
        )
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="switch_agent",
            reply=f"Focus moved. {label} is at the helm. Notion, backup, status, and Agent messages will route there until you choose another.",
            session=updated,
            deployment=item,
            buttons=(
                _button("Show My Crew", command="/agents", style="secondary"),
                _button("Check Status", command="/status", style="secondary"),
            ),
        )
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="switch_agent_not_found",
        reply="That name is not on your ArcLink roster. Open `/agents` and take the helm from the buttons I build for your account.",
        session=session,
        deployment=deployment,
        buttons=(_button("Show My Crew", command="/agents"),),
    )


def _add_agent_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
    stripe_client: Any | None,
    additional_agent_price_id: str,
    sovereign_agent_expansion_price_id: str = "",
    scale_agent_expansion_price_id: str = "",
    base_domain: str = "",
) -> ArcLinkPublicBotTurn:
    if not session or not deployment:
        return _turn(channel=channel, channel_identity=channel_identity, action="add_agent_unavailable", reply=_need_finished_onboarding_reply(), session=session)
    if not _deployment_can_anchor_add_agent(deployment):
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="add_agent_blocked",
            reply=_deployment_not_ready_reply(deployment),
            session=session,
            deployment=deployment,
        )
    if stripe_client is None:
        raise ArcLinkPublicBotError("additional agent checkout requires an injected Stripe client")
    plan = _deployment_plan_id(session, deployment)
    expansion_label = _agent_expansion_price_label(plan)
    if plan == "scale":
        price_id = str(scale_agent_expansion_price_id or additional_agent_price_id or "").strip()
    else:
        price_id = str(sovereign_agent_expansion_price_id or additional_agent_price_id or "").strip()
    if not price_id:
        raise ArcLinkPublicBotError("Agentic Expansion checkout requires a configured expansion Stripe price")

    user_id = str(deployment.get("user_id") or session.get("user_id") or "").strip()
    capacity_message = _fleet_capacity_block(conn, required_slots=1, label="Agentic Expansion")
    if capacity_message:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="add_agent_capacity_blocked",
            reply=capacity_message,
            session=session,
            deployment=deployment,
            buttons=(
                _button("Check Status", command="/status", style="secondary"),
                _button("Back To My Crew", command="/agents", style="secondary"),
            ),
        )
    root = f"https://{str(base_domain or default_base_domain({})).strip().strip('/')}"
    add_token = secrets.token_hex(10)
    extra_identity = f"{channel_identity}#add:{add_token}"
    extra_session = create_or_resume_arclink_onboarding_session(
        conn,
        channel=channel,
        channel_identity=extra_identity,
        session_id=f"onb_add_{add_token}",
        display_name_hint=str(session.get("display_name_hint") or ""),
        selected_plan_id=f"agent_expansion_{plan}",
        selected_model_id=chutes_default_model({}),
        current_step="additional_agent",
        metadata={
            "purchase_kind": "additional_agent",
            "agent_expansion_plan_id": plan,
            "agent_expansion_monthly_price": expansion_label,
            "public_channel_identity": channel_identity,
            "parent_deployment_id": str(deployment.get("deployment_id") or ""),
            "parent_session_id": str(session.get("session_id") or ""),
            "active_deployment_id": str(deployment.get("deployment_id") or ""),
        },
        force_new=True,
    )
    conn.execute(
        """
        UPDATE arclink_onboarding_sessions
        SET user_id = ?, updated_at = ?
        WHERE session_id = ?
        """,
        (user_id, utc_now_iso(), str(extra_session["session_id"])),
    )
    conn.commit()
    extra_session = open_arclink_onboarding_checkout(
        conn,
        session_id=str(extra_session["session_id"]),
        stripe_client=stripe_client,
        price_id=price_id,
        success_url=f"{root}/checkout/success?kind=additional_agent&session={str(extra_session['session_id'])}",
        cancel_url=f"{root}/checkout/cancel?kind=additional_agent&session={str(extra_session['session_id'])}",
        base_domain=base_domain or default_base_domain({}),
    )
    return _reply(
        extra_session,
        action="open_add_agent_checkout",
        reply=(
            f"Agentic Expansion for your {_plan_label(plan)} plan is {expansion_label}. "
            "Clear the Stripe handoff and I will move the new agent into the launch queue with the rest of your crew."
        ),
        buttons=(
            _button(f"Hire Agent - {expansion_label}", url=str(extra_session.get("checkout_url") or "")),
            _button("Back To My Crew", command="/agents", style="secondary"),
        ),
    )


def _share_grant_action_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    requested_action: str,
    grant_id: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
) -> ArcLinkPublicBotTurn:
    if not session or not str(session.get("user_id") or "").strip():
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="share_grant_unavailable",
            reply="I cannot approve a share from this channel until it is linked to your ArcLink account.",
            session=session,
            deployment=deployment,
            buttons=(_button("Link Channel", command="/link-channel", style="secondary"),),
        )
    session_user = str(session.get("user_id") or "").strip()
    row = conn.execute("SELECT * FROM arclink_share_grants WHERE grant_id = ?", (grant_id,)).fetchone()
    if row is None:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="share_grant_not_found",
            reply="I cannot find a share action for this ArcLink account.",
            session=session,
            deployment=deployment,
            buttons=(_button("Show My Crew", command="/agents", style="secondary"),),
        )
    grant = dict(row)
    current_status = str(grant.get("status") or "")
    label = str(grant.get("display_name") or grant.get("resource_path") or "linked resource")
    if requested_action == "accept":
        if str(grant.get("recipient_user_id") or "") != session_user:
            return _turn(
                channel=channel,
                channel_identity=channel_identity,
                action="share_grant_not_found",
                reply="I cannot accept that share from this ArcLink account.",
                session=session,
                deployment=deployment,
                buttons=(_button("Show My Crew", command="/agents", style="secondary"),),
            )
        if current_status == "accepted":
            return _turn(
                channel=channel,
                channel_identity=channel_identity,
                action="share_grant_noop",
                reply=f"`{label}` is already accepted in your Linked resources.",
                session=session,
                deployment=deployment,
                buttons=(_button("Show My Crew", command="/agents", style="secondary"),),
            )
        try:
            accepted = accept_share_grant_for_recipient(
                conn,
                recipient_user_id=session_user,
                grant_id=grant_id,
                actor_id=session_user,
                reason="recipient accepted read-only linked resource via Raven",
            )
        except Exception:
            return _turn(
                channel=channel,
                channel_identity=channel_identity,
                action="share_grant_noop",
                reply=f"No change made. `{label}` is not ready to accept.",
                session=session,
                deployment=deployment,
                buttons=(_button("Show My Crew", command="/agents", style="secondary"),),
            )
        projection = accepted.get("projection") if isinstance(accepted, Mapping) else {}
        linked_path = str((projection or {}).get("linked_path") or "").strip()
        location = f" at `{linked_path}`" if linked_path else ""
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="share_grant_accepted",
            reply=f"Accepted. `{label}` is now available as a read-only Linked resource{location}. It cannot be reshared.",
            session=session,
            deployment=deployment,
            buttons=(_button("Show My Crew", command="/agents", style="secondary"),),
        )
    owner_user = session_user
    if str(grant.get("owner_user_id") or "") != owner_user:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="share_grant_not_found",
            reply="I cannot approve that share from this ArcLink account.",
            session=session,
            deployment=deployment,
            buttons=(_button("Show My Crew", command="/agents", style="secondary"),),
        )
    if current_status != "pending_owner_approval":
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="share_grant_noop",
            reply=f"No change made. `{label}` is already `{current_status or 'unknown'}`.",
            session=session,
            deployment=deployment,
            buttons=(_button("Show My Crew", command="/agents", style="secondary"),),
        )

    now = utc_now_iso()
    if requested_action == "approve":
        new_status = "approved"
        sql = """
            UPDATE arclink_share_grants
            SET status = 'approved', approved_at = ?, updated_at = ?
            WHERE grant_id = ? AND owner_user_id = ? AND status = 'pending_owner_approval'
        """
        params = (now, now, grant_id, owner_user)
        audit_action = "share_grant_approved"
        reply = (
            f"Approved. `{label}` is ready for the recipient to accept as a read-only Linked resource. "
            "They still cannot reshare it from their account."
        )
        turn_action = "share_grant_approved"
    else:
        new_status = "denied"
        sql = """
            UPDATE arclink_share_grants
            SET status = 'denied', updated_at = ?
            WHERE grant_id = ? AND owner_user_id = ? AND status = 'pending_owner_approval'
        """
        params = (now, grant_id, owner_user)
        audit_action = "share_grant_denied"
        reply = f"Denied. `{label}` stays closed and will not appear in the recipient's Linked resources."
        turn_action = "share_grant_denied"
    cursor = conn.execute(sql, params)
    if cursor.rowcount != 1:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="share_grant_noop",
            reply=f"No change made. `{label}` is no longer awaiting owner approval.",
            session=session,
            deployment=deployment,
        )
    append_arclink_audit(
        conn,
        action=audit_action,
        actor_id=owner_user,
        target_kind="share_grant",
        target_id=grant_id,
        reason=f"owner {new_status} linked resource share via Raven",
        metadata={"channel": channel, "resource_root": str(grant.get("resource_root") or ""), "resource_path": str(grant.get("resource_path") or "")},
        commit=False,
    )
    append_arclink_event(
        conn,
        subject_kind="share_grant",
        subject_id=grant_id,
        event_type=f"public_bot:{audit_action}",
        metadata={"channel": channel, "owner_user_id": owner_user},
        commit=False,
    )
    conn.commit()
    recipient_notification = {"queued": False, "reason": "not_approved"}
    if requested_action == "approve":
        updated = conn.execute("SELECT * FROM arclink_share_grants WHERE grant_id = ?", (grant_id,)).fetchone()
        if updated is not None:
            recipient_notification = queue_share_grant_recipient_notification(conn, grant=dict(updated))
        if recipient_notification.get("queued"):
            reply += " I also notified the recipient so they can accept it now."
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action=turn_action,
        reply=reply,
        session=session,
        deployment=deployment,
        buttons=(_button("Show My Crew", command="/agents", style="secondary"),),
    )


def _crew_training_data(session: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = _metadata(session)
    data = payload.get("crew_training")
    return dict(data) if isinstance(data, Mapping) else {}


def _crew_training_update(
    conn: sqlite3.Connection,
    session: Mapping[str, Any],
    *,
    workflow: str,
    data: Mapping[str, Any],
) -> dict[str, Any]:
    return _update_session_metadata(
        conn,
        session_id=str(session["session_id"]),
        updates={
            "public_bot_workflow": workflow,
            "crew_training": dict(data),
            "crew_training_updated_at": utc_now_iso(),
        },
    )


def _clear_crew_training_workflow(conn: sqlite3.Connection, session: Mapping[str, Any]) -> dict[str, Any]:
    return _update_session_metadata(
        conn,
        session_id=str(session["session_id"]),
        updates={},
        clear=CREW_TRAINING_WORKFLOW_KEYS,
    )


def _academy_training_data(session: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = _metadata(session)
    data = payload.get("academy_training")
    return dict(data) if isinstance(data, Mapping) else {}


def _academy_training_update(
    conn: sqlite3.Connection,
    session: Mapping[str, Any],
    *,
    workflow: str,
    data: Mapping[str, Any],
) -> dict[str, Any]:
    return _update_session_metadata(
        conn,
        session_id=str(session["session_id"]),
        updates={
            "public_bot_workflow": workflow,
            "academy_training": dict(data),
            "academy_training_updated_at": utc_now_iso(),
        },
    )


def _clear_academy_training_workflow(conn: sqlite3.Connection, session: Mapping[str, Any]) -> dict[str, Any]:
    return _update_session_metadata(
        conn,
        session_id=str(session["session_id"]),
        updates={},
        clear=ACADEMY_TRAINING_WORKFLOW_KEYS,
    )


def _clear_retire_agent_workflow_if_open(conn: sqlite3.Connection, session: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if not session or not str(_metadata(session).get("public_bot_workflow") or "").startswith("retire_agent_"):
        return session
    return _update_session_metadata(
        conn,
        session_id=str(session["session_id"]),
        updates={},
        clear=RETIRE_AGENT_WORKFLOW_KEYS,
    )


def _crew_choice_buttons(
    choices: tuple[tuple[str, str], ...],
    *,
    include_cancel: bool = False,
) -> tuple[ArcLinkPublicBotButton, ...]:
    buttons = tuple(
        _button(label, command=command, style="primary" if index == 0 else "secondary")
        for index, (label, command) in enumerate(choices)
    )
    if include_cancel:
        buttons = (*buttons, _button("Cancel", command="/cancel", style="secondary"))
    return buttons


def _crew_training_start_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
) -> ArcLinkPublicBotTurn:
    user_id = str((deployment or {}).get("user_id") or (session or {}).get("user_id") or "").strip()
    deployments = _deployments_for_user(conn, user_id) if user_id else []
    if session is None or not user_id or not deployments:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="crew_training_not_ready",
            reply="Crew Training opens after checkout creates your ArcPod roster. Pick Founders Offer or 3X Scale Plan first, then I can tune the Crew.",
            session=session,
            deployment=deployment,
            buttons=(_button("Take Me Aboard", command="/packages"),),
        )
    count = len(deployments)
    count_label = "one Agent" if count == 1 else f"{count} Agents"
    updated = _crew_training_update(conn, session, workflow="crew_training_role", data={})
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="crew_training_prompt_role",
        reply=(
            f"Crew Training is open. I see {count_label} in your Crew.\n\n"
            "I will ask a few short questions, then shape Agent names, roles, personalities, and the additive SOUL.md overlay. "
            "After that, Quick Training can take any Agent into the Academy lane for specialist source maps, curriculum, practice tasks, and continuing review. "
            "You can send `cancel` at any time.\n\n"
            "What is your role? Send one line, for example `founder building a startup`."
        ),
        session=updated,
        deployment=deployment,
        buttons=(_button("Cancel", command="/cancel", style="secondary"),),
    )


def _crew_training_prompt(
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any],
    deployment: Mapping[str, Any] | None,
    action: str,
    reply: str,
    buttons: tuple[ArcLinkPublicBotButton, ...] = (),
) -> ArcLinkPublicBotTurn:
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action=action,
        reply=reply,
        session=session,
        deployment=deployment,
        buttons=buttons or (_button("Cancel", command="/cancel", style="secondary"),),
    )


def _crew_training_review_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any],
    deployment: Mapping[str, Any] | None,
    data: Mapping[str, Any],
) -> ArcLinkPublicBotTurn:
    user_id = str((deployment or {}).get("user_id") or session.get("user_id") or "").strip()
    if not user_id:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="crew_training_not_ready",
            reply=_need_finished_onboarding_reply(),
            session=session,
            deployment=deployment,
        )
    try:
        preview = preview_crew_recipe(
            conn,
            user_id=user_id,
            role=str(data.get("role") or ""),
            mission=str(data.get("mission") or ""),
            treatment=str(data.get("treatment") or ""),
            preset=str(data.get("preset") or ""),
            capacity=str(data.get("capacity") or ""),
        )
    except (ArcLinkCrewRecipeError, KeyError) as exc:
        updated = _crew_training_update(conn, session, workflow="crew_training_role", data={})
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="crew_training_restart",
            reply=f"Crew Training needs a clean restart: {exc}. Send your role again.",
            session=updated,
            deployment=deployment,
            buttons=(_button("Cancel", command="/cancel", style="secondary"),),
        )
    review_data = dict(data)
    review_data["last_preview_mode"] = str(preview.get("mode") or "")
    review_data["last_fallback_reason"] = str(preview.get("fallback_reason") or "")
    updated = _crew_training_update(conn, session, workflow="crew_training_review", data=review_data)
    fallback_line = f"\n\n{preview['fallback_reason']}" if preview.get("fallback") else ""
    crew_agents = preview.get("soul_overlay", {}).get("crew_agents", [])
    agent_lines = []
    if isinstance(crew_agents, list):
        for item in crew_agents[:6]:
            if isinstance(item, Mapping):
                agent_lines.append(f"- {item.get('agent_name', '')} - {item.get('agent_title', '')}")
    agents_block = "\n\nCrew shape:\n" + "\n".join(agent_lines) if agent_lines else ""
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="crew_training_review",
        reply=(
            "Review this Crew Recipe.\n\n"
            f"{preview['recipe_text']}"
            f"{agents_block}"
            f"{fallback_line}\n\n"
            "Send `confirm` to apply it, `regenerate` to try again, or `cancel` to close without changes."
        ),
        session=updated,
        deployment=deployment,
        buttons=(
            _button("Confirm", command="/confirm"),
            _button("Regenerate", command="/regenerate", style="secondary"),
            _button("Cancel", command="/cancel", style="secondary"),
        ),
    )


def _crew_training_confirm_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any],
    deployment: Mapping[str, Any] | None,
    data: Mapping[str, Any],
) -> ArcLinkPublicBotTurn:
    user_id = str((deployment or {}).get("user_id") or session.get("user_id") or "").strip()
    result = apply_crew_recipe(
        conn,
        user_id=user_id,
        role=str(data.get("role") or ""),
        mission=str(data.get("mission") or ""),
        treatment=str(data.get("treatment") or ""),
        preset=str(data.get("preset") or ""),
        capacity=str(data.get("capacity") or ""),
        actor_id=user_id,
    )
    updated = _update_session_metadata(
        conn,
        session_id=str(session["session_id"]),
        updates={},
        clear=CREW_TRAINING_WORKFLOW_KEYS,
    )
    recipe = result.get("recipe") or {}
    deployments = _deployments_for_user(conn, user_id)
    active_id = str((deployment or {}).get("deployment_id") or "")
    roster_lines, open_buttons = _crew_roster_lines_and_buttons(deployments, active_id=active_id, conn=conn)
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="crew_training_applied",
        reply=(
            f"Crew Training applied: {recipe.get('preset', '')} / {recipe.get('capacity', '')}.\n\n"
            f"Mission: {recipe.get('mission', '')}\n\n"
            "Your tuned Crew:\n"
            f"{chr(10).join(roster_lines or ['- Crew roster is still being prepared.'])}\n\n"
            "The additive SOUL.md overlay is projected for your Crew. Memories and sessions were not rewritten.\n\n"
            "You can rerun Training any time with `/train-crew`. If you want your Crew to call you something else, use `/name Your Name`."
        ),
        session=updated,
        deployment=deployment,
        buttons=tuple([
            *open_buttons[:2],
            _button("Quick Training", command="/academy", style="secondary"),
            _button("Show My Crew", command="/agents", style="secondary"),
            _button("What Changed", command="/whats-changed", style="secondary"),
        ]),
    )


def _academy_training_buttons(deployments: list[Mapping[str, Any]]) -> tuple[ArcLinkPublicBotButton, ...]:
    buttons: list[ArcLinkPublicBotButton] = [_button("Train All", command="/academy all")]
    for index, item in enumerate(deployments[:4], start=1):
        label = _agent_label(item, index=index, conn=None)
        buttons.append(_button(label[:32], command=f"/academy {item.get('deployment_id')}", style="secondary"))
    buttons.append(_button("Show My Crew", command="/agents", style="secondary"))
    return tuple(buttons[:8])


def _academy_status_lines(status: Mapping[str, Any]) -> list[str]:
    agents = status.get("agents") if isinstance(status.get("agents"), list) else []
    lines = [
        f"Academy: {status.get('status') or 'not_started'}",
        str(status.get("summary") or ""),
    ]
    for item in agents[:8]:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("agent_name") or item.get("deployment_id") or "Agent")
        title = str(item.get("agent_title") or "").strip()
        status_label = str(item.get("status") or "not_started")
        source_count = int(item.get("source_count") or 0)
        suffix = f" — {title}" if title else ""
        lines.append(f"- {name}{suffix}: {status_label}, {source_count} source(s)")
    return [line for line in lines if line]


def _academy_training_start_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
    requested_value: str = "",
) -> ArcLinkPublicBotTurn:
    user_id = str((deployment or {}).get("user_id") or (session or {}).get("user_id") or "").strip()
    deployments = _deployments_for_user(conn, user_id) if user_id else []
    if session is None or not user_id or not deployments:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="academy_training_not_ready",
            reply="Academy Training opens after checkout creates your ArcPod roster.",
            session=session,
            deployment=deployment,
            buttons=(_button("Take Me Aboard", command="/packages"),),
        )
    try:
        status = crew_academy_status(conn, user_id=user_id)
        current_ready = str(status.get("recipe_id") or "").strip()
    except Exception:
        current_ready = ""
    if not current_ready:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="academy_training_needs_crew_recipe",
            reply=(
                "Academy Training needs an active Crew Recipe first. "
                "Run Crew Training so I know each Agent's role, mission, and treatment, then come back to `/academy`."
            ),
            session=session,
            deployment=deployment,
            buttons=(_button("Train My Crew", command="/train-crew"),),
        )
    clean_value = str(requested_value or "").strip()
    if clean_value:
        if clean_value.casefold() in {"all", "crew", "everyone", "each"}:
            data = {
                "queue": [str(item.get("deployment_id") or "") for item in deployments if str(item.get("deployment_id") or "").strip()],
                "index": 0,
                "trained": [],
                "skipped": [],
            }
            updated = _academy_training_update(conn, session, workflow="academy_training_walk", data=data)
            return _academy_training_walk_prompt(
                conn,
                channel=channel,
                channel_identity=channel_identity,
                session=updated,
                deployment=deployment,
                data=data,
            )
        match = _find_agent_deployment(deployments, clean_value, conn=conn)
        if match is not None:
            item, label = match
            return _academy_training_stage_one_reply(
                conn,
                channel=channel,
                channel_identity=channel_identity,
                session=session,
                deployment=deployment,
                target=item,
                label=label,
                clear_workflow=False,
            )
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="academy_training_agent_not_found",
            reply="That Agent is not on your Crew roster. Pick one of the buttons or use `/agents` to inspect the names.",
            session=session,
            deployment=deployment,
            buttons=_academy_training_buttons(deployments),
        )
    updated = _academy_training_update(conn, session, workflow="academy_training_select", data={})
    count_label = "one Agent" if len(deployments) == 1 else f"{len(deployments)} Agents"
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="academy_training_select_agent",
        reply=(
            f"Academy Training is open for {count_label}.\n\n"
            "This stages a role-specific specialist corpus, curriculum, source map, SOUL overlay plan, skill/tool recipes, "
            "practice tasks, and continuing-education review for each Agent. It is local and governed: no live crawling, "
            "no raw workspace writes, and graduation still needs provider + Hermes proof.\n\n"
            "Pick one Agent, or Train All to walk the Crew one by one with Skip available. You can also call this lane Quick Training, Quick Briefing, Quick Align, or Quick Huddle."
        ),
        session=updated,
        deployment=deployment,
        buttons=_academy_training_buttons(deployments),
    )


def _academy_training_stage_one_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any],
    deployment: Mapping[str, Any] | None,
    target: Mapping[str, Any],
    label: str,
    clear_workflow: bool,
) -> ArcLinkPublicBotTurn:
    user_id = str((deployment or {}).get("user_id") or session.get("user_id") or target.get("user_id") or "").strip()
    try:
        result = stage_crew_academy_agent_training(
            conn,
            user_id=user_id,
            deployment_id=str(target.get("deployment_id") or ""),
            actor_id=user_id,
        )
    except (ArcLinkCrewRecipeError, KeyError) as exc:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="academy_training_failed",
            reply=f"Academy Training could not stage `{label}`: {exc}",
            session=session,
            deployment=deployment,
            buttons=(_button("Academy", command="/academy", style="secondary"),),
        )
    updated = _clear_academy_training_workflow(conn, session) if clear_workflow else session
    agent_status = result.get("agent_academy_training") or {}
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="academy_training_agent_staged",
        reply=(
            f"Academy staged for {label}.\n\n"
            f"Status: {agent_status.get('status') or 'ready_for_review'}\n"
            f"Sources: {agent_status.get('source_count') or 0}\n"
            f"Graduation: {agent_status.get('graduation_status') or 'blocked_by_live_proof'}\n\n"
            "I projected the specialist identity context for this Agent. The staged plan covers curriculum, source map, lesson cards, "
            "SOUL overlay sections, qmd/memory seed intents, approved skill/tool recipes, practice tasks, and weekly review. "
            "Live provider/Hermes proof is still required before calling the Agent graduated."
        ),
        session=updated,
        deployment=deployment,
        buttons=(
            _button("Academy", command="/academy", style="secondary"),
            _button("Show My Crew", command="/agents", style="secondary"),
        ),
    )


def _academy_training_skip_one(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    deployment_id: str,
) -> dict[str, Any]:
    return skip_crew_academy_agent_training(
        conn,
        user_id=user_id,
        deployment_id=deployment_id,
        actor_id=user_id,
    )


def _academy_training_walk_prompt(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any],
    deployment: Mapping[str, Any] | None,
    data: Mapping[str, Any],
) -> ArcLinkPublicBotTurn:
    user_id = str((deployment or {}).get("user_id") or session.get("user_id") or "").strip()
    deployments = _deployments_for_user(conn, user_id) if user_id else []
    queue = [str(item or "").strip() for item in (data.get("queue") if isinstance(data.get("queue"), list) else []) if str(item or "").strip()]
    index = int(data.get("index") or 0)
    if index >= len(queue):
        updated = _clear_academy_training_workflow(conn, session)
        status = crew_academy_status(conn, user_id=user_id)
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="academy_training_walk_complete",
            reply="\n".join(["Academy Training pass complete.", "", *_academy_status_lines(status)]),
            session=updated,
            deployment=deployment,
            buttons=(
                _button("Show My Crew", command="/agents", style="secondary"),
                _button("Academy", command="/academy", style="secondary"),
            ),
        )
    current_id = queue[index]
    match = _find_agent_deployment(deployments, current_id, conn=conn)
    if match is None:
        next_data = dict(data)
        next_data["index"] = index + 1
        updated = _academy_training_update(conn, session, workflow="academy_training_walk", data=next_data)
        return _academy_training_walk_prompt(
            conn,
            channel=channel,
            channel_identity=channel_identity,
            session=updated,
            deployment=deployment,
            data=next_data,
        )
    item, label = match
    trained = len(data.get("trained") or [])
    skipped = len(data.get("skipped") or [])
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="academy_training_walk_prompt",
        reply=(
            f"Academy pass {index + 1}/{len(queue)}.\n\n"
            f"Train {label} as `{item.get('agent_title') or 'specialist'}`?\n\n"
            f"Done so far: {trained} trained, {skipped} skipped."
        ),
        session=session,
        deployment=deployment,
        buttons=(
            _button("Train This Agent", command="train"),
            _button("Skip", command="skip", style="secondary"),
            _button("Cancel", command="/cancel", style="secondary"),
        ),
    )


def _handle_academy_training_workflow(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    message: str,
    command: str,
    session: Mapping[str, Any],
    deployment: Mapping[str, Any] | None,
    workflow: str,
) -> ArcLinkPublicBotTurn | None:
    data = _academy_training_data(session)
    user_id = str((deployment or {}).get("user_id") or session.get("user_id") or "").strip()
    deployments = _deployments_for_user(conn, user_id) if user_id else []
    if workflow == "academy_training_select":
        value = _academy_command_value(message, command)
        if value is None:
            value = message.strip()
        return _academy_training_start_reply(
            conn,
            channel=channel,
            channel_identity=channel_identity,
            session=session,
            deployment=deployment,
            requested_value=value,
        )
    if workflow == "academy_training_walk":
        queue = [str(item or "").strip() for item in (data.get("queue") if isinstance(data.get("queue"), list) else []) if str(item or "").strip()]
        index = int(data.get("index") or 0)
        if index >= len(queue):
            return _academy_training_walk_prompt(
                conn,
                channel=channel,
                channel_identity=channel_identity,
                session=session,
                deployment=deployment,
                data=data,
            )
        deployment_id = queue[index]
        match = _find_agent_deployment(deployments, deployment_id, conn=conn)
        next_data = dict(data)
        next_data["index"] = index + 1
        if command in {"train", "yes", "y", "/train"}:
            if match is not None:
                item, _label = match
                stage_crew_academy_agent_training(
                    conn,
                    user_id=user_id,
                    deployment_id=str(item.get("deployment_id") or deployment_id),
                    actor_id=user_id,
                )
                trained = list(next_data.get("trained") or [])
                trained.append(str(item.get("deployment_id") or deployment_id))
                next_data["trained"] = trained
            updated = _academy_training_update(conn, session, workflow="academy_training_walk", data=next_data)
            return _academy_training_walk_prompt(
                conn,
                channel=channel,
                channel_identity=channel_identity,
                session=updated,
                deployment=deployment,
                data=next_data,
            )
        if command in {"skip", "no", "n", "/skip"}:
            if match is not None:
                item, _label = match
                _academy_training_skip_one(
                    conn,
                    user_id=user_id,
                    deployment_id=str(item.get("deployment_id") or deployment_id),
                )
                skipped = list(next_data.get("skipped") or [])
                skipped.append(str(item.get("deployment_id") or deployment_id))
                next_data["skipped"] = skipped
            updated = _academy_training_update(conn, session, workflow="academy_training_walk", data=next_data)
            return _academy_training_walk_prompt(
                conn,
                channel=channel,
                channel_identity=channel_identity,
                session=updated,
                deployment=deployment,
                data=next_data,
            )
        return _academy_training_walk_prompt(
            conn,
            channel=channel,
            channel_identity=channel_identity,
            session=session,
            deployment=deployment,
            data=data,
        )
    return None


def _whats_changed_reply(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
) -> ArcLinkPublicBotTurn:
    user_id = str((deployment or {}).get("user_id") or (session or {}).get("user_id") or "").strip()
    if not user_id:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="crew_recipe_not_ready",
            reply=_need_finished_onboarding_reply(),
            session=session,
            deployment=deployment,
        )
    diff = whats_changed(conn, user_id=user_id)
    current = diff.get("current") or {}
    if diff["status"] == "none":
        reply = "No Crew Recipe is active yet. Send `/train-crew` to create one."
    elif diff["status"] == "first_recipe":
        reply = f"Current Crew Recipe: {current.get('preset', '')} / {current.get('capacity', '')}. No prior recipe is archived yet."
    else:
        reply = f"Crew Recipe changes: {diff['summary']}"
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="crew_recipe_whats_changed",
        reply=reply,
        session=session,
        deployment=deployment,
        buttons=(_button("Train Crew", command="/train-crew", style="secondary"),),
    )


def _handle_active_workflow(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    message: str,
    command: str,
    base_domain: str = "",
) -> ArcLinkPublicBotTurn | None:
    session, deployment = _deployment_context(conn, channel=channel, channel_identity=channel_identity)
    if not session:
        return None
    workflow = str(_metadata(session).get("public_bot_workflow") or "").strip()
    if not workflow:
        return None
    if workflow.startswith("retire_agent_"):
        return _handle_retire_agent_workflow(
            conn,
            channel=channel,
            channel_identity=channel_identity,
            message=message,
            command=command,
            session=session,
            deployment=deployment,
            workflow=workflow,
        )
    if command in ARCLINK_PUBLIC_BOT_CANCEL_COMMANDS:
        if workflow.startswith("academy_training_"):
            updated = _clear_academy_training_workflow(conn, session)
        else:
            updated = _clear_crew_training_workflow(conn, session)
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="workflow_cancelled",
            reply=(
                "Lane sealed.\n\n"
                "Nothing was lost in the closing. When you return, I can put you back on the launch path or surface the next clean step."
            ),
            session=updated,
            deployment=deployment,
            buttons=(
                _button("Take Me Aboard", command="/packages"),
                _button("Check Status", command="/status", style="secondary"),
            ),
        )
    if workflow.startswith("academy_training_"):
        return _handle_academy_training_workflow(
            conn,
            channel=channel,
            channel_identity=channel_identity,
            message=message,
            command=command,
            session=session,
            deployment=deployment,
            workflow=workflow,
        )
    if workflow.startswith("crew_training_"):
        data = _crew_training_data(session)
        if workflow == "crew_training_role":
            if command.startswith("/") and command not in {"/train-crew", "/train_crew"}:
                return None
            role = message.strip()
            if not role or role.startswith("/"):
                return _crew_training_prompt(
                    channel=channel,
                    channel_identity=channel_identity,
                    session=session,
                    deployment=deployment,
                    action="crew_training_prompt_role",
                    reply="What is your role? Send one line, for example `founder building a startup`.",
                )
            data["role"] = role
            updated = _crew_training_update(conn, session, workflow="crew_training_mission", data=data)
            return _crew_training_prompt(
                channel=channel,
                channel_identity=channel_identity,
                session=updated,
                deployment=deployment,
                action="crew_training_prompt_mission",
                reply="What should your Crew help you ship in the next 12 weeks?",
            )
        if workflow == "crew_training_mission":
            if command.startswith("/"):
                return None
            mission = message.strip()
            if not mission:
                return _crew_training_prompt(
                    channel=channel,
                    channel_identity=channel_identity,
                    session=session,
                    deployment=deployment,
                    action="crew_training_prompt_mission",
                    reply="Send the mission in one line.",
                )
            data["mission"] = mission
            updated = _crew_training_update(conn, session, workflow="crew_training_treatment", data=data)
            return _crew_training_prompt(
                channel=channel,
                channel_identity=channel_identity,
                session=updated,
                deployment=deployment,
                action="crew_training_prompt_treatment",
                reply="How should your Crew treat you? Reply `captain`, `peer`, `coach`, or a custom one-line preference.",
                buttons=_crew_choice_buttons(tuple((label.title(), label) for label in CREW_TREATMENT_CHOICES), include_cancel=True),
            )
        if workflow == "crew_training_treatment":
            if command.startswith("/"):
                return None
            treatment = CREW_TREATMENT_CHOICES.get(command, message.strip())
            if not treatment:
                return _crew_training_prompt(
                    channel=channel,
                    channel_identity=channel_identity,
                    session=session,
                    deployment=deployment,
                    action="crew_training_prompt_treatment",
                    reply="Reply `captain`, `peer`, `coach`, or a custom one-line preference.",
                )
            data["treatment"] = treatment
            updated = _crew_training_update(conn, session, workflow="crew_training_preset", data=data)
            return _crew_training_prompt(
                channel=channel,
                channel_identity=channel_identity,
                session=updated,
                deployment=deployment,
                action="crew_training_prompt_preset",
                reply="Pick a Crew preset: Frontier, Concourse, Salvage, or Vanguard.",
                buttons=_crew_choice_buttons(tuple((preset, preset) for preset in CREW_PRESET_CHOICES), include_cancel=True),
            )
        if workflow == "crew_training_preset":
            if command.startswith("/"):
                return None
            preset = message.strip().title()
            if preset not in CREW_PRESET_CHOICES:
                return _crew_training_prompt(
                    channel=channel,
                    channel_identity=channel_identity,
                    session=session,
                    deployment=deployment,
                    action="crew_training_prompt_preset",
                    reply="Pick one preset: Frontier, Concourse, Salvage, or Vanguard.",
                )
            data["preset"] = preset
            updated = _crew_training_update(conn, session, workflow="crew_training_capacity", data=data)
            return _crew_training_prompt(
                channel=channel,
                channel_identity=channel_identity,
                session=updated,
                deployment=deployment,
                action="crew_training_prompt_capacity",
                reply="Pick a Crew capacity: sales, marketing, development, life coaching, or companionship.",
                buttons=_crew_choice_buttons(tuple((capacity.title(), capacity) for capacity in CREW_CAPACITY_CHOICES)),
            )
        if workflow == "crew_training_capacity":
            if command.startswith("/"):
                return None
            capacity = command.replace("_", " ").replace("-", " ")
            if capacity not in CREW_CAPACITY_CHOICES:
                return _crew_training_prompt(
                    channel=channel,
                    channel_identity=channel_identity,
                    session=session,
                    deployment=deployment,
                    action="crew_training_prompt_capacity",
                    reply="Pick one capacity: sales, marketing, development, life coaching, or companionship.",
                )
            data["capacity"] = capacity
            return _crew_training_review_reply(
                conn,
                channel=channel,
                channel_identity=channel_identity,
                session=session,
                deployment=deployment,
                data=data,
            )
        if workflow == "crew_training_review":
            if command in ARCLINK_PUBLIC_BOT_CREW_CONFIRM_COMMANDS:
                return _crew_training_confirm_reply(
                    conn,
                    channel=channel,
                    channel_identity=channel_identity,
                    session=session,
                    deployment=deployment,
                    data=data,
                )
            if command in ARCLINK_PUBLIC_BOT_CREW_REGENERATE_COMMANDS:
                return _crew_training_review_reply(
                    conn,
                    channel=channel,
                    channel_identity=channel_identity,
                    session=session,
                    deployment=deployment,
                    data=data,
                )
            return _turn(
                channel=channel,
                channel_identity=channel_identity,
                action="crew_training_review_waiting",
                reply="Send `confirm` to apply this Crew Recipe, `regenerate` to try again, or `cancel` to close without changes.",
                session=session,
                deployment=deployment,
                buttons=(
                    _button("Confirm", command="/confirm"),
                    _button("Regenerate", command="/regenerate", style="secondary"),
                    _button("Cancel", command="/cancel", style="secondary"),
                ),
            )
    if workflow == "name_update":
        explicit_name = _command_value(message, command, ("name", "/name"))
        if explicit_name is not None:
            new_name = explicit_name.strip()
        elif command in {"name", "/name"}:
            new_name = ""
        elif command.startswith("/"):
            return None
        else:
            new_name = message.strip()
        if not new_name:
            return _turn(
                channel=channel,
                channel_identity=channel_identity,
                action="prompt_name_input",
                reply="I am listening. Send the name you want Raven to use, or send `cancel` to close this lane.",
                session=session,
                deployment=deployment,
                buttons=(_button("Cancel", command="/cancel", style="secondary"),),
            )
        updated = answer_arclink_onboarding_question(
            conn,
            session_id=str(session["session_id"]),
            question_key="name",
            answer_summary="display name captured",
            display_name_hint=new_name,
        )
        updated = _update_session_metadata(
            conn,
            session_id=str(updated["session_id"]),
            updates={},
            clear=("public_bot_workflow",),
        )
        return _identity_or_package_prompt(
            conn,
            updated,
            base_domain=base_domain,
            greeting=f"Captain {new_name}, Raven has your manifest name.",
        )
    if workflow == "agent_name":
        new_name = _workflow_value_for_named_command(message, command, ARCLINK_PUBLIC_BOT_AGENT_NAME_COMMANDS)
        if new_name is None:
            return None
        if not new_name:
            return _agent_name_prompt_reply(conn, session)
        updated = _answer_agent_identity(
            conn,
            session,
            question_key="agent_name",
            answer_summary="agent name captured",
            agent_name=new_name,
        )
        updated = _clear_public_bot_workflow(conn, updated)
        return _agent_title_prompt_reply(conn, updated)
    if workflow == "agent_title":
        new_title = _workflow_value_for_named_command(message, command, ARCLINK_PUBLIC_BOT_AGENT_TITLE_COMMANDS)
        if new_title is None:
            return None
        if not new_title:
            return _agent_title_prompt_reply(conn, session)
        updated = _answer_agent_identity(
            conn,
            session,
            question_key="agent_title",
            answer_summary="agent title captured",
            agent_title=new_title,
        )
        updated = _clear_public_bot_workflow(conn, updated)
        return _identity_or_package_prompt(conn, updated, base_domain=base_domain)
    if workflow == "connect_notion":
        if command in {"ready", "done", "verified", "complete"}:
            updated = _update_session_metadata(
                conn,
                session_id=str(session["session_id"]),
                updates={
                    "connect_notion_user_marked_ready_at": utc_now_iso(),
                    "connect_notion_public_status": "ready_for_dashboard_verification",
                },
                clear=("public_bot_workflow",),
            )
            if deployment:
                _record_bot_action(
                    conn,
                    deployment=deployment,
                    action="connect_notion_ready",
                    channel=channel,
                    channel_identity=channel_identity,
                    metadata={"verification_status": "pending_dashboard_verification"},
                )
            return _turn(
                channel=channel,
                channel_identity=channel_identity,
                action="connect_notion_ready",
                reply="Logged as ready for dashboard verification. This is not a completed Notion verification yet; open the dashboard Notion panel or operator rail to arm and confirm the verification-token install window.",
                session=updated,
                deployment=deployment,
            )
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="prompt_notion_ready",
            reply="Send `ready` once Notion completes the verification handshake. Send `cancel` and I will seal the Notion lane.",
            session=session,
            deployment=deployment,
        )
    if workflow == "config_backup_repo":
        owner_repo = message.strip().removeprefix("repo ").strip()
        if not GITHUB_OWNER_REPO_RE.fullmatch(owner_repo):
            return _turn(
                channel=channel,
                channel_identity=channel_identity,
                action="prompt_backup_repo",
                reply="Send the private GitHub repository in `owner/repo` form. Send `cancel` and I will seal the backup lane.",
                session=session,
                deployment=deployment,
            )
        updated = _update_session_metadata(
            conn,
            session_id=str(session["session_id"]),
            updates={
                "config_backup_owner_repo": owner_repo,
                "config_backup_requested_at": utc_now_iso(),
                "config_backup_public_status": "repo_recorded_pending_key_setup",
            },
            clear=("public_bot_workflow",),
        )
        if deployment:
            _record_bot_action(
                conn,
                deployment=deployment,
                action="config_backup_repo_recorded",
                channel=channel,
                channel_identity=channel_identity,
                metadata={"owner_repo": owner_repo, "verification_status": "pending_deploy_key_setup"},
            )
        settings_url = f"https://github.com/{owner_repo}/settings/keys"
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="record_backup_repo",
            reply=(
                f"Logged as pending key setup. `{owner_repo}` is attached to this pod's private backup lane, but backup is not active yet.\n\n"
                "Keep the repository private. ArcLink will mint a dedicated pod deploy key with write access; "
                "when the dashboard/operator rail produces the key, set it here:\n"
                f"{settings_url}\n\n"
                "Recorded to the deployment event stream - operators on the admin bridge can see this move and finish verification."
            ),
            session=updated,
            deployment=deployment,
        )
    return None


def _help_reply(
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None = None,
    deployment: Mapping[str, Any] | None = None,
) -> ArcLinkPublicBotTurn:
    ready = bool(deployment and str(deployment.get("status") or "") in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES)
    if not ready:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="show_help",
            reply=(
                "Comms are open.\n\n"
                "I will keep this simple until your first agent is live. I can help you pick Founders, Sovereign, or Scale, open checkout, or read the board.\n\n"
                "After launch, I reveal the working controls: credentials, your crew, Notion, private backups, channel pairing, files, code, and health."
            ),
            session=session,
            buttons=(
                _button("Take Me Aboard", command="/packages"),
                _button("Update Name", command="/name", style="secondary"),
            ),
        )
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="show_help",
        reply=(
            "Bridge is open.\n\n"
            "Your first agent is aboard, so I can show you the machinery now. Use the buttons for the common work. If you prefer typed controls, use `/raven agents`, `/raven status`, `/raven credentials`, `/raven connect_notion`, `/raven config_backup`, `/raven link_channel`, `/raven retire_agent`, or `/raven cancel`.\n\n"
            "Pick one lane and I will keep the steps tight and the path clean."
        ),
        session=session,
        deployment=deployment,
        buttons=(
            _button("Show My Crew", command="/agents", style="secondary"),
            _button("Wire Notion", command="/connect_notion", style="secondary"),
        ),
    )


def _learn_reply(
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None = None,
    deployment: Mapping[str, Any] | None = None,
) -> ArcLinkPublicBotTurn:
    ready = bool(deployment and str(deployment.get("status") or "") in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES)
    if not ready:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="learn_before_launch",
            reply=(
                "ArcLink brings up a private ArcPod for your Agent, then Raven hands you the controls here.\n\n"
                "After launch, one Helm login opens the Agent dashboard. Drive, Code, Terminal, memory, model fuel, Notion setup, and Crew controls all hang off that governed workspace."
            ),
            session=session,
            deployment=deployment,
            buttons=(_button("Take Me Aboard", command="/packages"),),
        )
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="learn",
        reply=(
            "Quick tour:\n\n"
            "- Raven is this bridge: roster, credentials, Notion, backups, billing, and setup.\n"
            "- Each Agent lives in an ArcPod with its own Hermes dashboard, memory, Drive, Code, Terminal, model lane, and health checks.\n"
            "- Show My Crew lists every Agent and Helm link; use it to switch who owns bare chat.\n"
            "- Login Credentials reveals the shared dashboard login until you confirm it is stored.\n"
            "- Crew Training shapes names, roles, tone, mission, and SOUL overlays.\n"
            "- Quick Training is the Academy lane: pick one Agent or train all, with Skip available, to stage specialist source maps, curriculum, practice tasks, and continuing review.\n\n"
            "Start with Show My Crew, Login Credentials, or Crew Training."
        ),
        session=session,
        deployment=deployment,
        buttons=(
            _button("Show My Crew", command="/agents", style="secondary"),
            _button("Login Credentials", command="/credentials", style="secondary"),
            _button("Crew Training", command="/train-crew", style="secondary"),
            _button("Quick Training", command="/academy", style="secondary"),
        ),
    )


def _upgrade_hermes_reply(
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any] | None,
    deployment: Mapping[str, Any] | None,
) -> ArcLinkPublicBotTurn:
    ready = bool(deployment and str(deployment.get("status") or "") in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES)
    if not ready:
        return _turn(
            channel=channel,
            channel_identity=channel_identity,
            action="upgrade_hermes_unavailable",
            reply=(
                "Hermes upgrades stay on ArcLink-managed rails.\n\n"
                "I cannot run an unmanaged `hermes update` from public chat. Once your first agent is live, I can show the active agent and status; operators use ArcLink deploy/control upgrade checks for runtime changes."
            ),
            session=session,
            deployment=deployment,
            buttons=(
                _button("Take Me Aboard", command="/packages"),
                _button("Check Status", command="/status", style="secondary"),
            ),
        )
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="upgrade_hermes_controlled",
        reply=(
            "Hermes is pinned and upgraded through ArcLink, not direct `hermes update` commands.\n\n"
            "For this agent, use the operator-controlled upgrade rails: component pin checks, ArcLink deploy upgrade, and the post-upgrade health/smoke path. I will keep user chat on status, agents, Notion, backups, channels, files, code, and health."
        ),
        session=session,
        deployment=deployment,
        buttons=(
            _button("Check Status", command="/status", style="secondary"),
            _button("Show My Crew", command="/agents", style="secondary"),
        ),
    )


def _status_reply(
    *,
    channel: str,
    channel_identity: str,
    session: Mapping[str, Any],
    deployment: Mapping[str, Any] | None,
    conn: sqlite3.Connection,
) -> ArcLinkPublicBotTurn:
    deployment_label = _agent_label(deployment or {}, index=0, conn=conn) if deployment else ""
    live_status_code = str((deployment or {}).get("status") or session.get("status") or "")
    phrase = launch_phrase(live_status_code)
    lines = [
        f"Reading the board.\n\n{phrase}",
    ]
    if deployment_label:
        lines.append(f"Agent at the helm: {deployment_label}.")
    lines.append(
        f"\n_session `{session['session_id']}` · state `{live_status_code or 'unknown'}` · "
        f"step `{session.get('current_step') or 'started'}`_"
    )
    buttons: list[ArcLinkPublicBotButton] = [_button("Show My Crew", command="/agents", style="secondary")]
    access = _deployment_access(deployment or {}) if deployment else {}
    if access.get("dashboard"):
        buttons.append(_button("Open Helm", url=str(access["dashboard"])))
    else:
        buttons.append(_button("Choose Package", command="/packages", style="secondary"))
    return _turn(
        channel=channel,
        channel_identity=channel_identity,
        action="show_status",
        reply="\n".join(lines),
        session=session,
        deployment=deployment,
        buttons=tuple(buttons),
    )


def handle_arclink_public_bot_turn(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    text: str,
    stripe_client: Any | None = None,
    price_id: str = "price_arclink_sovereign",
    founders_price_id: str = "price_arclink_founders",
    scale_price_id: str = "",
    additional_agent_price_id: str = "",
    sovereign_agent_expansion_price_id: str = "",
    scale_agent_expansion_price_id: str = "",
    base_domain: str = "",
    metadata: Mapping[str, Any] | None = None,
    display_name_hint: str = "",
) -> ArcLinkPublicBotTurn:
    clean_channel = _clean_channel(channel)
    clean_identity = _clean_identity(channel_identity)
    _check_public_bot_rate_limit(conn, channel=clean_channel, channel_identity=clean_identity)
    message = str(text or "").strip()
    command = message.lower()
    captured_display_name = str(display_name_hint or "").strip()[:40]
    turn_metadata = dict(metadata or {})
    reply_to_message_id = str(
        turn_metadata.get("telegram_message_id")
        or turn_metadata.get("discord_message_id")
        or turn_metadata.get("message_id")
        or ""
    ).strip()
    raven_control_requested = False
    rewritten = _raven_control_rewrite(message, command)
    if rewritten is not None:
        message = rewritten
        command = message.lower()
        raven_control_requested = True

    if message.startswith("/") and not raven_control_requested:
        context_session, context_deployment = _deployment_context(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
        )
        if (
            context_deployment
            and str(context_deployment.get("status") or "") in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES
        ):
            command_name = _public_bot_command_name(message)
            agent_command_names = _agent_command_names_from_context(turn_metadata, context_session)
            if command_name in ARCLINK_PUBLIC_BOT_AGENT_POLICY_SUPPRESSED_COMMANDS:
                return _upgrade_hermes_reply(
                    channel=clean_channel,
                    channel_identity=clean_identity,
                    session=context_session,
                    deployment=context_deployment,
                )
            if command_name and command_name in agent_command_names:
                raven = _raven_display_name(
                    conn,
                    channel=clean_channel,
                    channel_identity=clean_identity,
                    session=context_session,
                    deployment=context_deployment,
                )
                return _aboard_freeform_reply(
                    channel=clean_channel,
                    channel_identity=clean_identity,
                    session=context_session,
                    deployment={
                        **context_deployment,
                        "_public_bot_message": message,
                        "_public_bot_reply_to_message_id": reply_to_message_id,
                        "_public_bot_metadata": turn_metadata,
                    },
                    bot_display_name=raven,
                    conn=conn,
                    source_kind="agent_command",
                    include_bridge_intro=False,
                )

    if _raven_name_command_value(message, command) is not None:
        return _raven_name_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            message=message,
            command=command,
        )

    if command in ARCLINK_PUBLIC_BOT_HELP_COMMANDS:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        return _help_reply(
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
        )

    if command in ARCLINK_PUBLIC_BOT_LEARN_COMMANDS:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        return _learn_reply(
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
        )

    if command in {"status", "/status"}:
        context_session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        if context_session is not None:
            return _status_reply(
                channel=clean_channel,
                channel_identity=clean_identity,
                session=context_session,
                deployment=deployment,
                conn=conn,
            )

    if command in ARCLINK_PUBLIC_BOT_AGENTS_COMMANDS:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        session = _clear_retire_agent_workflow_if_open(conn, session)
        return _agents_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
        )

    retire_value = _retire_agent_command_value(message, command)
    if retire_value is not None:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        return _retire_agent_start_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            requested_value=retire_value,
            session=session,
            deployment=deployment,
        )

    if command in ARCLINK_PUBLIC_BOT_TRAIN_CREW_COMMANDS:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        session = _clear_retire_agent_workflow_if_open(conn, session)
        return _crew_training_start_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
        )

    academy_value = _academy_command_value(message, command)
    if academy_value is not None:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        session = _clear_retire_agent_workflow_if_open(conn, session)
        return _academy_training_start_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
            requested_value=academy_value,
        )

    if command in ARCLINK_PUBLIC_BOT_WHATS_CHANGED_COMMANDS:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        return _whats_changed_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
        )

    rename_value = _value_for_named_command(message, command, ARCLINK_PUBLIC_BOT_RENAME_AGENT_COMMANDS)
    if rename_value is not None:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        if not rename_value.strip():
            return _turn(
                channel=clean_channel,
                channel_identity=clean_identity,
                action="rename_agent_missing",
                reply="Send the new Agent name after the command, for example `/rename-agent Atlas`.",
                session=session,
                deployment=deployment,
            )
        return _agent_identity_update_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
            agent_name=rename_value,
        )

    retitle_value = _value_for_named_command(message, command, ARCLINK_PUBLIC_BOT_RETITLE_AGENT_COMMANDS)
    if retitle_value is not None:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        if not retitle_value.strip():
            return _turn(
                channel=clean_channel,
                channel_identity=clean_identity,
                action="retitle_agent_missing",
                reply="Send the new Agent title after the command, for example `/retitle-agent the right hand`.",
                session=session,
                deployment=deployment,
            )
        return _agent_identity_update_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
            agent_title=retitle_value,
        )

    wrapped_frequency_value = _value_for_named_command(message, command, ARCLINK_PUBLIC_BOT_WRAPPED_FREQUENCY_COMMANDS)
    if wrapped_frequency_value is not None:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        user_id = str((deployment or {}).get("user_id") or (session or {}).get("user_id") or "").strip()
        if not user_id:
            return _turn(
                channel=clean_channel,
                channel_identity=clean_identity,
                action="wrapped_frequency_unavailable",
                reply=_need_finished_onboarding_reply(),
                session=session,
                deployment=deployment,
                buttons=(_button("Take Me Aboard", command="/packages"),),
            )
        requested_frequency = wrapped_frequency_value.strip().lower()
        if not requested_frequency:
            return _turn(
                channel=clean_channel,
                channel_identity=clean_identity,
                action="wrapped_frequency_missing",
                reply="Send the Wrapped cadence after the command: `/wrapped-frequency daily`, `/wrapped-frequency weekly`, or `/wrapped-frequency monthly`.",
                session=session,
                deployment=deployment,
            )
        try:
            updated = set_wrapped_frequency(
                conn,
                user_id,
                requested_frequency,
                actor_id=user_id,
                reason="Captain updated ArcLink Wrapped cadence from Raven",
            )
        except ArcLinkWrappedError:
            return _turn(
                channel=clean_channel,
                channel_identity=clean_identity,
                action="wrapped_frequency_invalid",
                reply="ArcLink Wrapped cadence can be daily, weekly, or monthly. Nothing more frequent than daily is supported.",
                session=session,
                deployment=deployment,
            )
        return _turn(
            channel=clean_channel,
            channel_identity=clean_identity,
            action="wrapped_frequency_updated",
            reply=f"ArcLink Wrapped is now set to {updated['wrapped_frequency']}.",
            session=session,
            deployment=deployment,
        )

    refuel_value = _value_for_named_command(message, command, ARCLINK_PUBLIC_BOT_REFUEL_COMMANDS)
    if refuel_value is not None:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        return _refuel_reply(
            conn=conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
            stripe_client=stripe_client,
            requested_value=refuel_value,
            base_domain=base_domain,
        )

    # Retirement confirmations can be labels such as "Agent #587". Handle
    # open workflows before the plain "agent <selector>" helm-switch parser.
    active_workflow = _handle_active_workflow(
        conn,
        channel=clean_channel,
        channel_identity=clean_identity,
        message=message,
        command=command,
        base_domain=base_domain,
    )
    if active_workflow is not None:
        return active_workflow

    switch_requested, switch_is_hard = _agent_switch_request(message, command)
    if switch_requested or switch_is_hard:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        if switch_requested:
            return _switch_agent_reply(
                conn,
                channel=clean_channel,
                channel_identity=clean_identity,
                requested_slug=switch_requested,
                session=session,
                deployment=deployment,
            )
        return _turn(
            channel=clean_channel,
            channel_identity=clean_identity,
            action="switch_agent_missing",
            reply="Open `/agents` or send `/agent Jeff` with an Agent name from your Crew roster. `/agent` is only for switching helm; normal messages go straight to the Agent already at helm.",
            session=session,
            deployment=deployment,
            buttons=(_button("Show My Crew", command="/agents", style="secondary"),),
        )

    pair_value = _pair_channel_value(message, command)
    if pair_value is not None:
        session = create_or_resume_arclink_onboarding_session(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            selected_model_id=chutes_default_model({}),
            metadata=metadata,
            display_name_hint=captured_display_name,
        )
        context_session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        raven = _raven_display_name(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=context_session or session,
            deployment=deployment,
        )
        return _pair_channel_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=context_session or session,
            deployment=deployment,
            code_value=pair_value,
            bot_display_name=raven,
        )

    if command in ARCLINK_PUBLIC_BOT_ADD_AGENT_COMMANDS:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        session = _clear_retire_agent_workflow_if_open(conn, session)
        return _add_agent_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
            stripe_client=stripe_client,
            additional_agent_price_id=additional_agent_price_id,
            sovereign_agent_expansion_price_id=sovereign_agent_expansion_price_id,
            scale_agent_expansion_price_id=scale_agent_expansion_price_id,
            base_domain=base_domain,
        )

    if command in ARCLINK_PUBLIC_BOT_UPGRADE_HERMES_COMMANDS:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        return _upgrade_hermes_reply(
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
        )

    share_match = ARCLINK_PUBLIC_BOT_SHARE_ACTION_RE.match(command)
    if share_match:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        return _share_grant_action_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            requested_action=share_match.group(1),
            grant_id=share_match.group(2),
            session=session,
            deployment=deployment,
        )

    if command in ARCLINK_PUBLIC_BOT_CANCEL_COMMANDS:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        if session and str(_metadata(session).get("public_bot_workflow") or "").startswith("retire_agent_"):
            active_workflow = _handle_active_workflow(
                conn,
                channel=clean_channel,
                channel_identity=clean_identity,
                message=message,
                command=command,
                base_domain=base_domain,
            )
            if active_workflow is not None:
                return active_workflow
        if deployment and str(deployment.get("status") or "") in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES:
            return _turn(
                channel=clean_channel,
                channel_identity=clean_identity,
                action="cancel_unavailable",
                reply=(
                    "No setup workflow is open to cancel. Your agent is already live; use `/agents` or `/status` from here."
                ),
                session=session,
                deployment=deployment,
                buttons=(
                    _button("Show My Crew", command="/agents", style="secondary"),
                    _button("Check Status", command="/status", style="secondary"),
                ),
            )
        if session:
            updated = cancel_arclink_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                reason="public bot cancel command",
            )
            return _turn(
                channel=clean_channel,
                channel_identity=clean_identity,
                action="onboarding_cancelled",
                reply=(
                    "Launch setup cancelled.\n\n"
                    "I closed the open onboarding and checkout state. Send `/packages` when you want to resume with a clean handoff."
                ),
                session=updated,
                deployment=deployment,
                buttons=(
                    _button("Take Me Aboard", command="/packages"),
                    _button("Check Status", command="/status", style="secondary"),
                ),
            )
        return _turn(
            channel=clean_channel,
            channel_identity=clean_identity,
            action="nothing_to_cancel",
            reply="No open ArcLink setup workflow is waiting on this channel. Send `/packages` when you want to start.",
            buttons=(_button("Take Me Aboard", command="/packages"),),
        )

    credential_target = _target_from_command(
        command,
        aliases=ARCLINK_PUBLIC_BOT_CREDENTIAL_COMMANDS,
        prefixes=ARCLINK_PUBLIC_BOT_CREDENTIAL_TARGET_PREFIXES,
    )
    if credential_target is not None:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        deployment = _deployment_for_selector(conn, session=session, deployment=deployment, selector=credential_target)
        return _credentials_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
        )

    credential_ack_target = _target_from_command(
        command,
        aliases=ARCLINK_PUBLIC_BOT_CREDENTIAL_ACK_COMMANDS,
        prefixes=ARCLINK_PUBLIC_BOT_CREDENTIAL_ACK_TARGET_PREFIXES,
    )
    if credential_ack_target is not None:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        deployment = _deployment_for_selector(conn, session=session, deployment=deployment, selector=credential_ack_target)
        return _credentials_stored_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
        )

    if command in ARCLINK_PUBLIC_BOT_CONNECT_NOTION_COMMANDS:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        return _connect_notion_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
        )

    active_workflow = _handle_active_workflow(
        conn,
        channel=clean_channel,
        channel_identity=clean_identity,
        message=message,
        command=command,
        base_domain=base_domain,
    )
    if active_workflow is not None:
        return active_workflow

    if command in ARCLINK_PUBLIC_BOT_CONFIG_BACKUP_COMMANDS:
        session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        return _config_backup_reply(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=session,
            deployment=deployment,
        )

    # Routing law: if the user is already aboard with a live pod, every
    # remaining branch below this point would re-trigger onboarding copy
    # ("Stripe collects your email", "Send /name Your Name") that makes no
    # sense for a paying customer. Hand them a clean Helm pointer instead.
    aboard_session, aboard_deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
    if aboard_deployment and str(aboard_deployment.get("status") or "") in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES:
        if command in {"/start", "start", "restart"} or _is_raven_launch_command(message, command):
            return _help_reply(
                channel=clean_channel,
                channel_identity=clean_identity,
                session=aboard_session,
                deployment=aboard_deployment,
            )
        raven = _raven_display_name(
            conn,
            channel=clean_channel,
            channel_identity=clean_identity,
            session=aboard_session,
            deployment=aboard_deployment,
        )
        return _aboard_freeform_reply(
            channel=clean_channel,
            channel_identity=clean_identity,
            session=aboard_session,
            deployment={
                **aboard_deployment,
                "_public_bot_message": message,
                "_public_bot_reply_to_message_id": reply_to_message_id,
                "_public_bot_metadata": turn_metadata,
            },
            bot_display_name=raven,
            conn=conn,
            source_kind="agent_command" if message.startswith("/") else "chat",
            include_bridge_intro=(
                bool(message)
                and not message.startswith("/")
                and _claim_agent_bridge_intro(
                    conn,
                    channel=clean_channel,
                    channel_identity=clean_identity,
                    deployment=aboard_deployment,
                )
            ),
        )

    session = create_or_resume_arclink_onboarding_session(
        conn,
        channel=clean_channel,
        channel_identity=clean_identity,
        selected_model_id=chutes_default_model({}),
        metadata=metadata,
        display_name_hint=captured_display_name,
    )
    raven = _raven_display_name(conn, channel=clean_channel, channel_identity=clean_identity, session=session)

    if command in {"", "/start", "start", "restart"}:
        name = str(session.get("display_name_hint") or "").strip()
        greeting = f"Captain {name}, {raven} on the line." if name else f"{raven} on the line, Captain."
        return _identity_or_package_prompt(
            conn,
            session,
            base_domain=base_domain,
            greeting=greeting,
            bot_display_name=raven,
        )
    if command in {"status", "/status"}:
        context_session, deployment = _deployment_context(conn, channel=clean_channel, channel_identity=clean_identity)
        return _status_reply(
            channel=clean_channel,
            channel_identity=clean_identity,
            session=context_session or session,
            deployment=deployment,
            conn=conn,
        )
    email = _command_value(message, command, ("email", "/email"))
    if email is not None:
        return _reply(
            session,
            action="prompt_name",
            reply="Keep your email out of comms. Stripe collects it at checkout, and only there. Tap Update Name, then just send the name you want Raven to use.",
        )
    agent_identity_value = _value_for_named_command(message, command, ARCLINK_PUBLIC_BOT_AGENT_IDENTITY_COMMANDS)
    if agent_identity_value is not None:
        if not agent_identity_value.strip():
            return _agent_name_prompt_reply(conn, session, bot_display_name=raven)
        parsed_name, parsed_title = _agent_identity_pair(agent_identity_value)
        session = _answer_agent_identity(
            conn,
            session,
            question_key="agent_identity",
            answer_summary="agent identity captured",
            agent_name=parsed_name,
            agent_title=parsed_title,
        )
        return _identity_or_package_prompt(conn, session, base_domain=base_domain, bot_display_name=raven)
    agent_name_value = _value_for_named_command(message, command, ARCLINK_PUBLIC_BOT_AGENT_NAME_COMMANDS)
    if agent_name_value is not None:
        if not agent_name_value.strip():
            return _agent_name_prompt_reply(conn, session, bot_display_name=raven)
        session = _answer_agent_identity(
            conn,
            session,
            question_key="agent_name",
            answer_summary="agent name captured",
            agent_name=agent_name_value,
        )
        return _identity_or_package_prompt(conn, session, base_domain=base_domain, bot_display_name=raven)
    agent_title_value = _value_for_named_command(message, command, ARCLINK_PUBLIC_BOT_AGENT_TITLE_COMMANDS)
    if agent_title_value is not None:
        if not agent_title_value.strip():
            return _agent_title_prompt_reply(conn, session, bot_display_name=raven)
        session = _answer_agent_identity(
            conn,
            session,
            question_key="agent_title",
            answer_summary="agent title captured",
            agent_title=agent_title_value,
        )
        return _identity_or_package_prompt(conn, session, base_domain=base_domain, bot_display_name=raven)
    if command in ARCLINK_PUBLIC_BOT_STANDARD_PACKAGE_COMMANDS:
        return _identity_or_package_prompt(conn, session, base_domain=base_domain, standard=True, bot_display_name=raven)
    if command in ARCLINK_PUBLIC_BOT_PACKAGE_COMMANDS:
        return _identity_or_package_prompt(conn, session, base_domain=base_domain, bot_display_name=raven)
    if command in {"name", "/name"}:
        # Bare /name (or the Update Name button) opens a short listening lane.
        # The next plain-text message becomes the display name.
        current = str(session.get("display_name_hint") or "").strip()
        current_line = f"\n\nCurrent name: {current}" if current else ""
        session = _update_session_metadata(
            conn,
            session_id=str(session["session_id"]),
            updates={"public_bot_workflow": "name_update", "name_update_requested_at": utc_now_iso()},
        )
        return _reply(
            session,
            action="prompt_name_input",
            reply=(
                "What should I call you on the ArcLink manifest?\n\n"
                "Send the name as plain text. I am listening."
                f"{current_line}"
            ),
            buttons=(
                _button("Cancel", command="/cancel", style="secondary"),
            ),
        )
    name = _command_value(message, command, ("name", "/name"))
    if name is not None:
        session = answer_arclink_onboarding_question(
            conn,
            session_id=str(session["session_id"]),
            question_key="name",
            answer_summary="display name captured",
            display_name_hint=name,
        )
        return _identity_or_package_prompt(
            conn,
            session,
            base_domain=base_domain,
            greeting=f"Captain {name}, Raven has your manifest name.",
            bot_display_name=raven,
        )
    plan_answer = _command_value(message, command, ("plan", "/plan"))
    if plan_answer is None:
        bare_plan = _normalize_public_bot_plan(command)
        if bare_plan:
            plan_answer = bare_plan
    if plan_answer is not None:
        plan = _normalize_public_bot_plan(plan_answer)
        if plan not in ARCLINK_PUBLIC_BOT_PLANS:
            raise ArcLinkPublicBotError(f"unsupported ArcLink public bot plan: {plan or 'blank'}")
        session = answer_arclink_onboarding_question(
            conn,
            session_id=str(session["session_id"]),
            question_key="plan",
            answer_summary=f"selected {plan}",
            selected_plan_id=plan,
            selected_model_id=chutes_default_model({}),
        )
        if plan == "scale":
            plan_reply = (
                "3X Scale Plan is locked.\n\n"
                f"Three Agents live on ArcLink with Federation for ${SCALE_MONTHLY_DOLLARS}/month. "
                "Stripe handles the handoff, then I move onboarding into the launch queue and report back here."
            )
        elif plan == "founders":
            plan_reply = (
                "Founders Offer is locked.\n\n"
                f"Single-ArcPod access for ${FOUNDERS_MONTHLY_DOLLARS}/month. "
                "One Agent lives on ArcLink while the Founders cohort is open."
            )
        else:
            plan_reply = (
                "Sovereign is locked.\n\n"
                f"One Agent lives on ArcLink for ${SOVEREIGN_MONTHLY_DOLLARS}/month. "
                "Stripe handles the handoff, then I move onboarding into the launch queue and report back here."
            )
        if stripe_client is not None:
            return _open_first_agent_checkout_turn(
                conn,
                session,
                stripe_client=stripe_client,
                selected_plan=plan,
                price_id=price_id,
                founders_price_id=founders_price_id,
                scale_price_id=scale_price_id,
                base_domain=base_domain,
                bot_display_name=raven,
            )
        return _reply(
            session,
            action="prompt_checkout",
            reply=plan_reply,
            buttons=(
                _button(_plan_checkout_label(plan), command="/checkout"),
                _button("Change Package", command="/packages", style="secondary"),
            ),
            bot_display_name=raven,
        )
    if command in {"checkout", "/checkout"}:
        if stripe_client is None:
            raise ArcLinkPublicBotError("checkout requires an injected Stripe client")
        selected_plan = _normalize_public_bot_plan(str(session.get("selected_plan_id") or "founders"))
        return _open_first_agent_checkout_turn(
            conn,
            session,
            stripe_client=stripe_client,
            selected_plan=selected_plan,
            price_id=price_id,
            founders_price_id=founders_price_id,
            scale_price_id=scale_price_id,
            base_domain=base_domain,
            bot_display_name=raven,
        )
    return _reply(
        session,
        action="prompt_command",
        reply=(
            f"I read you. {raven} on the line.\n\n"
            "Use Take Me Aboard to choose Founders Offer or 3X Scale Plan, Update Name to change what your Crew calls you, or `/status` to read the board. "
            "Once an Agent is live, I open the deeper controls: credentials, Crew, Notion, backup, Drive, Code, Terminal, model lane, and health."
        ),
        buttons=(
            _button("Take Me Aboard", command="/packages"),
            _button("Update Name", command="/name", style="secondary"),
        ),
        bot_display_name=raven,
    )
