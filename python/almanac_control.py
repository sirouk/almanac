#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import ipaddress
import json
import os
import pwd
import re
import secrets
import shlex
import shutil
import sqlite3
import string
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PYTHON_DIR = Path(__file__).resolve().parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from almanac_notion_ssot import (
    create_notion_database,
    create_notion_page,
    DEFAULT_NOTION_API_VERSION,
    extract_notion_space_id,
    notion_database_data_source_id,
    query_notion_collection,
    retrieve_notion_data_source,
    retrieve_notion_database,
    retrieve_notion_page,
    retrieve_notion_page_markdown,
    retrieve_notion_user,
    update_notion_data_source,
    update_notion_database,
    update_notion_page,
    resolve_notion_target,
)
from almanac_resource_map import managed_resource_ref, shared_resource_lines, shared_tailnet_host


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def utc_now_iso() -> str:
    return utc_now().replace(microsecond=0).isoformat()


def auto_provision_stale_before_iso(seconds: int = 300) -> str:
    return (utc_now() - dt.timedelta(seconds=seconds)).replace(microsecond=0).isoformat()


def bool_env(name: str, default: bool = False, env: dict[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    value = source.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized == "":
        return default
    return normalized in {"1", "true", "yes", "on"}


def json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def safe_slug(value: str, fallback: str = "agent") -> str:
    allowed = string.ascii_lowercase + string.digits + "-_"
    lowered = value.strip().lower().replace(" ", "-")
    cleaned = "".join(ch for ch in lowered if ch in allowed).strip("-_")
    return cleaned or fallback


def _clean_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


REPO_SYNC_MANAGED_MARKER = "<!-- managed: almanac-repo-sync -->"
REPO_SYNC_STATUS_FILENAME = "REPO-SYNC.md"
REPO_SYNC_SOURCE_SUFFIXES = {".md", ".markdown", ".mdx", ".txt", ".text"}
REPO_SYNC_EXCLUDED_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "venv",
}
REPO_SYNC_GITHUB_PATTERN = re.compile(
    r"(?P<raw>(?P<prefix>https?://github\.com/|git@github\.com:|ssh://git@github\.com/)"
    r"(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?)(?=[/?#\s)\]\}\"'`]|$)"
)


def _python_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _safe_path_is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _artifact_value(raw_value: str) -> str:
    try:
        parsed = shlex.split(raw_value.strip(), posix=True)
        return "" if not parsed else parsed[0]
    except ValueError:
        return raw_value.strip().strip("'\"")


def _read_operator_artifact_hints(operator_artifact: Path) -> dict[str, str]:
    hints = {
        "ALMANAC_OPERATOR_DEPLOYED_USER": "",
        "ALMANAC_OPERATOR_DEPLOYED_REPO_DIR": "",
        "ALMANAC_OPERATOR_DEPLOYED_PRIV_DIR": "",
        "ALMANAC_OPERATOR_DEPLOYED_CONFIG_FILE": "",
    }
    if not _safe_path_is_file(operator_artifact):
        return hints

    try:
        for raw_line in operator_artifact.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            key = key.strip()
            if key not in hints:
                continue
            hints[key] = _artifact_value(raw_value)
    except OSError:
        pass

    return hints


def _resolve_user_home(user: str) -> Path | None:
    if not user:
        return None
    try:
        return Path(pwd.getpwnam(user).pw_dir).expanduser()
    except KeyError:
        return Path("/home") / user


def _discover_config_file() -> Path | None:
    explicit = os.environ.get("ALMANAC_CONFIG_FILE")
    if explicit:
        path = Path(explicit).expanduser()
        return path if _safe_path_is_file(path) else path

    repo_root = Path(os.environ.get("ALMANAC_REPO_DIR", _python_repo_root())).expanduser().resolve()
    operator_artifact = Path(
        os.environ.get("ALMANAC_OPERATOR_ARTIFACT_FILE", str(repo_root / ".almanac-operator.env"))
    ).expanduser()
    artifact_hints = _read_operator_artifact_hints(operator_artifact)
    artifact_user = artifact_hints.get("ALMANAC_OPERATOR_DEPLOYED_USER", "")
    artifact_repo = artifact_hints.get("ALMANAC_OPERATOR_DEPLOYED_REPO_DIR", "")
    artifact_priv = artifact_hints.get("ALMANAC_OPERATOR_DEPLOYED_PRIV_DIR", "")
    artifact_config = artifact_hints.get("ALMANAC_OPERATOR_DEPLOYED_CONFIG_FILE", "")
    artifact_home = _resolve_user_home(artifact_user)

    nested_priv = repo_root / "almanac-priv" / "config" / "almanac.env"
    sibling_priv = repo_root.parent / "almanac-priv" / "config" / "almanac.env"
    candidates: list[Path] = []
    if artifact_config:
        candidates.append(Path(artifact_config).expanduser())
    if artifact_priv:
        artifact_priv_path = Path(artifact_priv).expanduser()
        candidates.extend(
            (
                artifact_priv_path / "config" / "almanac.env",
                artifact_priv_path / "almanac.env",
            )
        )
    if artifact_repo:
        artifact_repo_path = Path(artifact_repo).expanduser()
        candidates.extend(
            (
                artifact_repo_path / "almanac-priv" / "config" / "almanac.env",
                artifact_repo_path / "config" / "almanac.env",
            )
        )
    if artifact_home is not None:
        candidates.extend(
            (
                artifact_home / "almanac" / "almanac-priv" / "config" / "almanac.env",
                artifact_home / "almanac-priv" / "config" / "almanac.env",
            )
        )
    candidates.extend(
        (
        repo_root / "config" / "almanac.env",
        nested_priv,
        sibling_priv,
        Path.home() / "almanac" / "almanac-priv" / "config" / "almanac.env",
        Path.home() / "almanac-priv" / "config" / "almanac.env",
        )
    )
    return next((candidate for candidate in candidates if _safe_path_is_file(candidate)), None)


def _load_config_env() -> dict[str, str]:
    # Safe: this merged environment is consumed only in-process for config discovery
    # and default resolution. It must never be handed to child processes as-is.
    merged = dict(os.environ)
    config_path = _discover_config_file()
    if config_path is None:
        return merged

    if not _safe_path_is_file(config_path):
        merged.setdefault("ALMANAC_CONFIG_FILE", str(config_path))
        return merged

    try:
        config_text = config_path.read_text(encoding="utf-8")
    except OSError:
        merged.setdefault("ALMANAC_CONFIG_FILE", str(config_path))
        return merged

    for raw_line in config_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if not key:
            continue
        try:
            parsed = shlex.split(raw_value, posix=True)
            value = "" if not parsed else parsed[0]
        except ValueError:
            value = raw_value
        merged.setdefault(key, value)

    merged.setdefault("ALMANAC_CONFIG_FILE", str(config_path))
    return merged


def config_env_value(name: str, default: str = "") -> str:
    return _load_config_env().get(name, default)


@dataclass(frozen=True)
class Config:
    almanac_user: str
    almanac_home: Path
    repo_dir: Path
    private_dir: Path
    state_dir: Path
    runtime_dir: Path
    vault_dir: Path
    db_path: Path
    agents_state_dir: Path
    curator_dir: Path
    curator_manifest_path: Path
    curator_hermes_home: Path
    archived_agents_dir: Path
    release_state_file: Path
    public_mcp_host: str
    public_mcp_port: int
    notion_webhook_host: str
    notion_webhook_port: int
    bootstrap_window_seconds: int
    bootstrap_per_ip_limit: int
    bootstrap_global_pending_limit: int
    bootstrap_pending_ttl_seconds: int
    auto_provision_max_attempts: int
    auto_provision_retry_base_seconds: int
    auto_provision_retry_max_seconds: int
    curator_telegram_onboarding_enabled: bool
    curator_discord_onboarding_enabled: bool
    onboarding_window_seconds: int
    onboarding_per_telegram_user_limit: int
    onboarding_global_pending_limit: int
    onboarding_update_failure_limit: int
    operator_notify_platform: str
    operator_notify_channel_id: str
    operator_telegram_user_ids: tuple[str, ...]
    operator_general_platform: str
    operator_general_channel_id: str
    qmd_url: str
    chutes_mcp_url: str
    upstream_repo_url: str
    upstream_branch: str
    model_presets: dict[str, str]
    agent_dashboard_backend_port_base: int
    agent_dashboard_proxy_port_base: int
    agent_code_port_base: int
    agent_port_slot_span: int
    agent_code_server_image: str
    agent_enable_tailscale_serve: bool

    @classmethod
    def from_env(cls) -> "Config":
        env = _load_config_env()
        almanac_user = env.get("ALMANAC_USER", "almanac")
        repo_dir = Path(env.get("ALMANAC_REPO_DIR", os.getcwd())).resolve()
        private_dir = Path(env.get("ALMANAC_PRIV_DIR", repo_dir / "almanac-priv")).resolve()
        state_dir = Path(env.get("STATE_DIR", private_dir / "state")).resolve()
        runtime_dir = Path(env.get("RUNTIME_DIR", state_dir / "runtime")).resolve()
        vault_dir = Path(env.get("VAULT_DIR", private_dir / "vault")).resolve()
        public_mcp_port = int(env.get("ALMANAC_MCP_PORT", "8282"))
        public_mcp_host = env.get("ALMANAC_MCP_HOST", "127.0.0.1")
        notion_webhook_port = int(env.get("ALMANAC_NOTION_WEBHOOK_PORT", "8283"))
        notion_webhook_host = env.get("ALMANAC_NOTION_WEBHOOK_HOST", "127.0.0.1")
        qmd_url = env.get("ALMANAC_QMD_URL", f"http://127.0.0.1:{env.get('QMD_MCP_PORT', '8181')}/mcp")
        chutes_mcp_url = env.get("CHUTES_MCP_URL", "")

        model_presets = {
            "codex": env.get("ALMANAC_MODEL_PRESET_CODEX", "openai:codex"),
            "opus": env.get("ALMANAC_MODEL_PRESET_OPUS", "anthropic:claude-opus"),
            "chutes": env.get("ALMANAC_MODEL_PRESET_CHUTES", "chutes:auto-failover"),
        }
        curator_channels = {
            value.strip().lower()
            for value in env.get("ALMANAC_CURATOR_CHANNELS", "tui-only").split(",")
            if value.strip()
        }
        operator_notify_platform = env.get("OPERATOR_NOTIFY_CHANNEL_PLATFORM", "tui-only")
        operator_notify_channel_id = env.get("OPERATOR_NOTIFY_CHANNEL_ID", "")
        operator_telegram_user_ids_raw = env.get(
            "ALMANAC_OPERATOR_TELEGRAM_USER_IDS",
            "",
        )
        operator_telegram_user_ids = tuple(
            value.strip()
            for value in operator_telegram_user_ids_raw.split(",")
            if value.strip()
        )
        agent_enable_tailscale_serve = bool_env(
            "ALMANAC_AGENT_ENABLE_TAILSCALE_SERVE",
            default=bool_env("ENABLE_TAILSCALE_SERVE", default=False, env=env),
            env=env,
        )

        return cls(
            almanac_user=almanac_user,
            almanac_home=Path(env.get("ALMANAC_HOME", f"/home/{almanac_user}")).resolve(),
            repo_dir=repo_dir,
            private_dir=private_dir,
            state_dir=state_dir,
            runtime_dir=runtime_dir,
            vault_dir=vault_dir,
            db_path=Path(env.get("ALMANAC_DB_PATH", state_dir / "almanac-control.sqlite3")).resolve(),
            agents_state_dir=Path(env.get("ALMANAC_AGENTS_STATE_DIR", state_dir / "agents")).resolve(),
            curator_dir=Path(env.get("ALMANAC_CURATOR_DIR", state_dir / "curator")).resolve(),
            curator_manifest_path=Path(env.get("ALMANAC_CURATOR_MANIFEST", state_dir / "curator" / "manifest.json")).resolve(),
            curator_hermes_home=Path(env.get("ALMANAC_CURATOR_HERMES_HOME", state_dir / "curator" / "hermes-home")).resolve(),
            archived_agents_dir=Path(env.get("ALMANAC_ARCHIVED_AGENTS_DIR", state_dir / "archived-agents")).resolve(),
            release_state_file=Path(env.get("ALMANAC_RELEASE_STATE_FILE", state_dir / "almanac-release.json")).resolve(),
            public_mcp_host=public_mcp_host,
            public_mcp_port=public_mcp_port,
            notion_webhook_host=notion_webhook_host,
            notion_webhook_port=notion_webhook_port,
            bootstrap_window_seconds=int(env.get("ALMANAC_BOOTSTRAP_WINDOW_SECONDS", "3600")),
            bootstrap_per_ip_limit=int(env.get("ALMANAC_BOOTSTRAP_PER_IP_LIMIT", "5")),
            bootstrap_global_pending_limit=int(env.get("ALMANAC_BOOTSTRAP_GLOBAL_PENDING_LIMIT", "20")),
            bootstrap_pending_ttl_seconds=int(env.get("ALMANAC_BOOTSTRAP_PENDING_TTL_SECONDS", "900")),
            auto_provision_max_attempts=int(env.get("ALMANAC_AUTO_PROVISION_MAX_ATTEMPTS", "5")),
            auto_provision_retry_base_seconds=int(env.get("ALMANAC_AUTO_PROVISION_RETRY_BASE_SECONDS", "60")),
            auto_provision_retry_max_seconds=int(env.get("ALMANAC_AUTO_PROVISION_RETRY_MAX_SECONDS", "900")),
            curator_telegram_onboarding_enabled=bool_env(
                "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED",
                default=("telegram" in curator_channels or operator_notify_platform == "telegram"),
                env=env,
            ),
            curator_discord_onboarding_enabled=bool_env(
                "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED",
                default=("discord" in curator_channels or operator_notify_platform == "discord"),
                env=env,
            ),
            onboarding_window_seconds=int(env.get("ALMANAC_ONBOARDING_WINDOW_SECONDS", "3600")),
            onboarding_per_telegram_user_limit=int(
                env.get(
                    "ALMANAC_ONBOARDING_PER_USER_LIMIT",
                    env.get("ALMANAC_ONBOARDING_PER_TELEGRAM_USER_LIMIT", "3"),
                )
            ),
            onboarding_global_pending_limit=int(env.get("ALMANAC_ONBOARDING_GLOBAL_PENDING_LIMIT", "20")),
            onboarding_update_failure_limit=int(env.get("ALMANAC_ONBOARDING_UPDATE_FAILURE_LIMIT", "3")),
            operator_notify_platform=operator_notify_platform,
            operator_notify_channel_id=operator_notify_channel_id,
            operator_telegram_user_ids=operator_telegram_user_ids,
            operator_general_platform=env.get("OPERATOR_GENERAL_CHANNEL_PLATFORM", ""),
            operator_general_channel_id=env.get("OPERATOR_GENERAL_CHANNEL_ID", ""),
            qmd_url=qmd_url,
            chutes_mcp_url=chutes_mcp_url,
            upstream_repo_url=env.get("ALMANAC_UPSTREAM_REPO_URL", "https://github.com/sirouk/almanac.git"),
            upstream_branch=env.get("ALMANAC_UPSTREAM_BRANCH", "main"),
            model_presets=model_presets,
            agent_dashboard_backend_port_base=int(env.get("ALMANAC_AGENT_DASHBOARD_BACKEND_PORT_BASE", "19000")),
            agent_dashboard_proxy_port_base=int(env.get("ALMANAC_AGENT_DASHBOARD_PROXY_PORT_BASE", "29000")),
            agent_code_port_base=int(env.get("ALMANAC_AGENT_CODE_PORT_BASE", "39000")),
            agent_port_slot_span=int(env.get("ALMANAC_AGENT_PORT_SLOT_SPAN", "5000")),
            agent_code_server_image=env.get(
                "ALMANAC_AGENT_CODE_SERVER_IMAGE",
                "docker.io/codercom/code-server:4.116.0",
            ),
            agent_enable_tailscale_serve=agent_enable_tailscale_serve,
        )


def ensure_runtime_paths(cfg: Config) -> None:
    for path in (
        cfg.state_dir,
        cfg.runtime_dir,
        cfg.agents_state_dir,
        cfg.curator_dir,
        cfg.archived_agents_dir,
        cfg.db_path.parent,
    ):
        path.mkdir(parents=True, exist_ok=True)


def connect_db(cfg: Config) -> sqlite3.Connection:
    ensure_runtime_paths(cfg)
    conn = sqlite3.connect(cfg.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema(conn)
    _migrate_onboarding_bot_tokens(conn, cfg)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS settings (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS bootstrap_requests (
          request_id TEXT PRIMARY KEY,
          requester_identity TEXT NOT NULL,
          unix_user TEXT NOT NULL,
          source_ip TEXT NOT NULL,
          requested_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          status TEXT NOT NULL,
          prior_agent_id TEXT,
          prior_defaults_json TEXT,
          approval_surface TEXT,
          approval_actor TEXT,
          approved_at TEXT,
          denied_at TEXT,
          denied_by_surface TEXT,
          denied_by_actor TEXT,
          token_id TEXT,
          token_delivered_at TEXT,
          auto_provision INTEGER NOT NULL DEFAULT 0,
          requested_model_preset TEXT,
          requested_channels_json TEXT NOT NULL DEFAULT '[]',
          provision_started_at TEXT,
          provision_attempts INTEGER NOT NULL DEFAULT 0,
          provision_next_attempt_at TEXT,
          provisioned_at TEXT,
          provision_error TEXT,
          cancelled_at TEXT,
          cancelled_by_surface TEXT,
          cancelled_by_actor TEXT,
          cancelled_reason TEXT
        );

        CREATE TABLE IF NOT EXISTS bootstrap_tokens (
          token_id TEXT PRIMARY KEY,
          agent_id TEXT NOT NULL,
          token_hash TEXT NOT NULL,
          requester_identity TEXT NOT NULL,
          source_ip TEXT NOT NULL,
          issued_at TEXT NOT NULL,
          issued_by TEXT NOT NULL,
          activation_request_id TEXT,
          activated_at TEXT,
          revoked_at TEXT,
          revoked_by_surface TEXT,
          revoked_by_actor TEXT,
          revocation_reason TEXT
        );

        CREATE TABLE IF NOT EXISTS rate_limits (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          scope TEXT NOT NULL,
          subject TEXT NOT NULL,
          observed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS agents (
          agent_id TEXT PRIMARY KEY,
          role TEXT NOT NULL,
          unix_user TEXT NOT NULL UNIQUE,
          display_name TEXT NOT NULL,
          status TEXT NOT NULL,
          hermes_home TEXT NOT NULL,
          manifest_path TEXT,
          archived_state_path TEXT,
          model_preset TEXT,
          model_string TEXT,
          channels_json TEXT NOT NULL DEFAULT '[]',
          allowed_mcps_json TEXT NOT NULL DEFAULT '[]',
          home_channel_json TEXT,
          operator_notify_channel_json TEXT,
          notes TEXT,
          created_at TEXT NOT NULL,
          last_enrolled_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS agent_identity (
          unix_user TEXT PRIMARY KEY,
          agent_id TEXT NOT NULL UNIQUE,
          human_display_name TEXT NOT NULL DEFAULT '',
          agent_name TEXT NOT NULL DEFAULT '',
          claimed_notion_email TEXT NOT NULL DEFAULT '',
          notion_user_id TEXT NOT NULL DEFAULT '',
          notion_user_email TEXT NOT NULL DEFAULT '',
          verification_status TEXT NOT NULL DEFAULT 'unverified',
          write_mode TEXT NOT NULL DEFAULT 'read_only',
          verified_at TEXT,
          suspended_at TEXT,
          verification_source TEXT NOT NULL DEFAULT '',
          notes TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS vaults (
          vault_name TEXT PRIMARY KEY,
          vault_path TEXT NOT NULL UNIQUE,
          state TEXT NOT NULL,
          warning TEXT,
          owner TEXT,
          default_subscribed INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS vault_definitions (
          definition_path TEXT PRIMARY KEY,
          vault_name TEXT,
          vault_path TEXT NOT NULL,
          owner TEXT,
          description TEXT,
          default_subscribed INTEGER NOT NULL DEFAULT 0,
          tags_json TEXT NOT NULL DEFAULT '[]',
          category TEXT,
          brief_template TEXT,
          is_valid INTEGER NOT NULL,
          warning TEXT,
          discovered_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS agent_vault_subscriptions (
          agent_id TEXT NOT NULL,
          vault_name TEXT NOT NULL,
          subscribed INTEGER NOT NULL,
          source TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (agent_id, vault_name)
        );

        CREATE TABLE IF NOT EXISTS notification_outbox (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          target_kind TEXT NOT NULL,
          target_id TEXT NOT NULL,
          channel_kind TEXT NOT NULL,
          message TEXT NOT NULL,
          extra_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          delivered_at TEXT,
          delivery_error TEXT
        );

        CREATE TABLE IF NOT EXISTS operator_actions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          action_kind TEXT NOT NULL,
          requested_target TEXT NOT NULL DEFAULT '',
          requested_by TEXT NOT NULL,
          request_source TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL,
          note TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          started_at TEXT,
          finished_at TEXT,
          log_path TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS notion_webhook_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          event_id TEXT NOT NULL UNIQUE,
          event_type TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          received_at TEXT NOT NULL,
          batch_status TEXT NOT NULL DEFAULT 'pending',
          processed_at TEXT,
          attempt_count INTEGER NOT NULL DEFAULT 0,
          last_attempt_at TEXT,
          last_error TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS refresh_jobs (
          job_name TEXT PRIMARY KEY,
          job_kind TEXT NOT NULL,
          target_id TEXT NOT NULL,
          schedule TEXT,
          last_run_at TEXT,
          last_status TEXT,
          last_note TEXT
        );

        CREATE TABLE IF NOT EXISTS onboarding_sessions (
          session_id TEXT PRIMARY KEY,
          platform TEXT NOT NULL,
          chat_id TEXT NOT NULL,
          sender_id TEXT NOT NULL,
          sender_username TEXT,
          sender_display_name TEXT,
          state TEXT NOT NULL,
          answers_json TEXT NOT NULL DEFAULT '{}',
          operator_notified_at TEXT,
          approved_at TEXT,
          approved_by_actor TEXT,
          denied_at TEXT,
          denied_by_actor TEXT,
          denial_reason TEXT,
          linked_request_id TEXT,
          linked_agent_id TEXT,
          telegram_bot_id TEXT,
          telegram_bot_username TEXT,
          pending_bot_token TEXT,
          pending_bot_token_path TEXT,
          provision_error TEXT,
          completed_at TEXT,
          last_prompt_at TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS onboarding_update_failures (
          update_id TEXT PRIMARY KEY,
          failure_count INTEGER NOT NULL DEFAULT 0,
          first_failed_at TEXT NOT NULL,
          last_failed_at TEXT NOT NULL,
          last_error TEXT NOT NULL,
          skipped_at TEXT
        );

        CREATE TABLE IF NOT EXISTS ssot_access_audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          agent_id TEXT NOT NULL,
          unix_user TEXT NOT NULL,
          notion_user_id TEXT NOT NULL DEFAULT '',
          operation TEXT NOT NULL,
          target_id TEXT NOT NULL DEFAULT '',
          decision TEXT NOT NULL,
          reason TEXT NOT NULL,
          actor TEXT NOT NULL DEFAULT '',
          request_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notion_identity_claims (
          claim_id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL DEFAULT '',
          agent_id TEXT NOT NULL,
          unix_user TEXT NOT NULL,
          claimed_notion_email TEXT NOT NULL,
          notion_page_id TEXT NOT NULL DEFAULT '',
          notion_page_url TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'pending',
          failure_reason TEXT NOT NULL DEFAULT '',
          verified_notion_user_id TEXT NOT NULL DEFAULT '',
          verified_notion_email TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          verified_at TEXT
        );

        CREATE TABLE IF NOT EXISTS notion_identity_overrides (
          unix_user TEXT PRIMARY KEY,
          agent_id TEXT NOT NULL UNIQUE,
          notion_user_id TEXT NOT NULL DEFAULT '',
          notion_user_email TEXT NOT NULL DEFAULT '',
          notes TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        """
    )
    _migrate_notion_identity_claims_remove_legacy_nonce(conn)
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_identity_claimed_email_active
        ON agent_identity (LOWER(claimed_notion_email))
        WHERE claimed_notion_email != ''
          AND verification_status IN ('pending', 'verified')
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ssot_access_audit_agent_created
        ON ssot_access_audit (agent_id, created_at)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_notion_identity_claims_page_id
        ON notion_identity_claims (notion_page_id)
        WHERE notion_page_id != ''
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_notion_identity_claims_status_expires
        ON notion_identity_claims (status, expires_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_notion_identity_claims_session_created
        ON notion_identity_claims (session_id, created_at)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_notion_identity_overrides_user_id
        ON notion_identity_overrides (notion_user_id)
        WHERE notion_user_id != ''
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_notion_identity_overrides_email
        ON notion_identity_overrides (LOWER(notion_user_email))
        WHERE notion_user_email != ''
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_operator_actions_status_kind_created
        ON operator_actions (status, action_kind, created_at)
        """
    )
    _ensure_column(conn, "bootstrap_tokens", "activation_request_id", "TEXT")
    _ensure_column(conn, "bootstrap_tokens", "activated_at", "TEXT")
    _ensure_column(conn, "bootstrap_requests", "auto_provision", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "bootstrap_requests", "requested_model_preset", "TEXT")
    _ensure_column(conn, "bootstrap_requests", "requested_channels_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "bootstrap_requests", "provision_started_at", "TEXT")
    _ensure_column(conn, "bootstrap_requests", "provision_attempts", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "bootstrap_requests", "provision_next_attempt_at", "TEXT")
    _ensure_column(conn, "bootstrap_requests", "provisioned_at", "TEXT")
    _ensure_column(conn, "bootstrap_requests", "provision_error", "TEXT")
    _ensure_column(conn, "bootstrap_requests", "cancelled_at", "TEXT")
    _ensure_column(conn, "bootstrap_requests", "cancelled_by_surface", "TEXT")
    _ensure_column(conn, "bootstrap_requests", "cancelled_by_actor", "TEXT")
    _ensure_column(conn, "bootstrap_requests", "cancelled_reason", "TEXT")
    _ensure_column(conn, "onboarding_sessions", "approved_at", "TEXT")
    _ensure_column(conn, "onboarding_sessions", "approved_by_actor", "TEXT")
    _ensure_column(conn, "onboarding_sessions", "denied_at", "TEXT")
    _ensure_column(conn, "onboarding_sessions", "denied_by_actor", "TEXT")
    _ensure_column(conn, "onboarding_sessions", "denial_reason", "TEXT")
    _ensure_column(conn, "onboarding_sessions", "linked_request_id", "TEXT")
    _ensure_column(conn, "onboarding_sessions", "linked_agent_id", "TEXT")
    _ensure_column(conn, "onboarding_sessions", "telegram_bot_id", "TEXT")
    _ensure_column(conn, "onboarding_sessions", "telegram_bot_username", "TEXT")
    _ensure_column(conn, "onboarding_sessions", "pending_bot_token", "TEXT")
    _ensure_column(conn, "onboarding_sessions", "pending_bot_token_path", "TEXT")
    _ensure_column(conn, "onboarding_sessions", "provision_error", "TEXT")
    _ensure_column(conn, "onboarding_sessions", "completed_at", "TEXT")
    _ensure_column(conn, "onboarding_sessions", "last_prompt_at", "TEXT")
    _ensure_column(conn, "notification_outbox", "extra_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(conn, "notion_identity_claims", "failure_reason", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "notion_identity_claims", "verified_notion_user_id", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "notion_identity_claims", "verified_notion_email", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "notion_webhook_events", "attempt_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "notion_webhook_events", "last_attempt_at", "TEXT")
    _ensure_column(conn, "notion_webhook_events", "last_error", "TEXT NOT NULL DEFAULT ''")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_notion_webhook_events_status_received
        ON notion_webhook_events (batch_status, received_at)
        """
    )
    conn.commit()


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(row["name"]) for row in rows]


def _migrate_notion_identity_claims_remove_legacy_nonce(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "notion_identity_claims")
    if "verification_nonce" not in columns:
        return
    conn.executescript(
        """
        DROP TABLE IF EXISTS notion_identity_claims__new;
        CREATE TABLE notion_identity_claims__new (
          claim_id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL DEFAULT '',
          agent_id TEXT NOT NULL,
          unix_user TEXT NOT NULL,
          claimed_notion_email TEXT NOT NULL,
          notion_page_id TEXT NOT NULL DEFAULT '',
          notion_page_url TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'pending',
          failure_reason TEXT NOT NULL DEFAULT '',
          verified_notion_user_id TEXT NOT NULL DEFAULT '',
          verified_notion_email TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          verified_at TEXT
        );
        INSERT INTO notion_identity_claims__new (
          claim_id, session_id, agent_id, unix_user, claimed_notion_email,
          notion_page_id, notion_page_url, status, failure_reason,
          verified_notion_user_id, verified_notion_email, created_at, updated_at, expires_at, verified_at
        )
        SELECT
          claim_id, session_id, agent_id, unix_user, claimed_notion_email,
          notion_page_id, notion_page_url, status, failure_reason,
          verified_notion_user_id, verified_notion_email, created_at, updated_at, expires_at, verified_at
        FROM notion_identity_claims;
        DROP TABLE notion_identity_claims;
        ALTER TABLE notion_identity_claims__new RENAME TO notion_identity_claims;
        """
    )
    conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    names = set(_table_columns(conn, table))
    if column in names:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    conn.commit()


def upsert_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key, value, utc_now_iso()),
    )
    conn.commit()


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def _notion_identity_claim_row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = dict(row)
    for key in ("verified_at",):
        payload[key] = _clean_text(payload.get(key))
    return payload


def _normalize_email(value: str) -> str:
    return str(value or "").strip().lower()


def _agent_identity_row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = dict(row)
    for key in ("verified_at", "suspended_at"):
        payload[key] = _clean_text(payload.get(key))
    return payload


def _notion_identity_override_row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def get_agent_identity(
    conn: sqlite3.Connection,
    *,
    agent_id: str = "",
    unix_user: str = "",
) -> dict[str, Any] | None:
    normalized_agent_id = str(agent_id or "").strip()
    normalized_unix_user = str(unix_user or "").strip()
    if not normalized_agent_id and not normalized_unix_user:
        return None
    row = conn.execute(
        """
        SELECT *
        FROM agent_identity
        WHERE (? != '' AND agent_id = ?)
           OR (? != '' AND unix_user = ?)
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (normalized_agent_id, normalized_agent_id, normalized_unix_user, normalized_unix_user),
    ).fetchone()
    return _agent_identity_row_to_dict(row)


def list_agent_identities(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM agent_identity ORDER BY unix_user").fetchall()
    return [dict(row) for row in rows]


def get_notion_identity_override(
    conn: sqlite3.Connection,
    *,
    agent_id: str = "",
    unix_user: str = "",
    notion_user_id: str = "",
    notion_user_email: str = "",
) -> dict[str, Any] | None:
    normalized_agent_id = str(agent_id or "").strip()
    normalized_unix_user = str(unix_user or "").strip()
    normalized_user_id = str(notion_user_id or "").strip()
    normalized_email = _normalize_email(notion_user_email)
    if not any((normalized_agent_id, normalized_unix_user, normalized_user_id, normalized_email)):
        return None
    row = conn.execute(
        """
        SELECT *
        FROM notion_identity_overrides
        WHERE (? != '' AND agent_id = ?)
           OR (? != '' AND unix_user = ?)
           OR (? != '' AND notion_user_id = ?)
           OR (? != '' AND LOWER(notion_user_email) = ?)
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (
            normalized_agent_id,
            normalized_agent_id,
            normalized_unix_user,
            normalized_unix_user,
            normalized_user_id,
            normalized_user_id,
            normalized_email,
            normalized_email,
        ),
    ).fetchone()
    return _notion_identity_override_row_to_dict(row)


def list_notion_identity_overrides(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM notion_identity_overrides ORDER BY unix_user").fetchall()
    return [dict(row) for row in rows]


def upsert_notion_identity_override(
    conn: sqlite3.Connection,
    *,
    agent_id: str = "",
    unix_user: str = "",
    notion_user_id: str = "",
    notion_user_email: str = "",
    notes: str = "",
) -> dict[str, Any]:
    target = _resolve_identity_target(conn, agent_id=agent_id, unix_user=unix_user)
    normalized_user_id = str(notion_user_id or "").strip()
    normalized_email = _normalize_email(notion_user_email)
    if not normalized_user_id and not normalized_email:
        raise ValueError("identity override needs a Notion user id or Notion email")
    now_iso = utc_now_iso()
    existing = get_notion_identity_override(conn, agent_id=str(target["agent_id"]), unix_user=str(target["unix_user"])) or {}
    row = {
        "agent_id": str(target["agent_id"]),
        "unix_user": str(target["unix_user"]),
        "notion_user_id": normalized_user_id or str(existing.get("notion_user_id") or ""),
        "notion_user_email": normalized_email or _normalize_email(str(existing.get("notion_user_email") or "")),
        "notes": str(notes or existing.get("notes") or "").strip(),
        "created_at": str(existing.get("created_at") or now_iso),
        "updated_at": now_iso,
    }
    if not row["notion_user_id"] and not row["notion_user_email"]:
        raise ValueError("identity override needs a Notion user id or Notion email")
    conn.execute(
        """
        INSERT INTO notion_identity_overrides (
          unix_user, agent_id, notion_user_id, notion_user_email, notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(unix_user) DO UPDATE SET
          agent_id = excluded.agent_id,
          notion_user_id = excluded.notion_user_id,
          notion_user_email = excluded.notion_user_email,
          notes = excluded.notes,
          updated_at = excluded.updated_at
        """,
        (
            row["unix_user"],
            row["agent_id"],
            row["notion_user_id"],
            row["notion_user_email"],
            row["notes"],
            row["created_at"],
            row["updated_at"],
        ),
    )
    conn.commit()
    return get_notion_identity_override(conn, agent_id=row["agent_id"], unix_user=row["unix_user"]) or row


def clear_notion_identity_override(
    conn: sqlite3.Connection,
    *,
    agent_id: str = "",
    unix_user: str = "",
) -> bool:
    target = _resolve_identity_target(conn, agent_id=agent_id, unix_user=unix_user)
    cursor = conn.execute(
        "DELETE FROM notion_identity_overrides WHERE unix_user = ? OR agent_id = ?",
        (str(target["unix_user"]), str(target["agent_id"])),
    )
    conn.commit()
    return bool(cursor.rowcount)


AGENT_IDENTITY_VERIFICATION_STATUSES = ("unverified", "pending", "verified")
AGENT_IDENTITY_WRITE_MODES = ("read_only", "verified_limited")


def _resolve_identity_target(
    conn: sqlite3.Connection,
    *,
    agent_id: str = "",
    unix_user: str = "",
) -> dict[str, Any]:
    identity = get_agent_identity(conn, agent_id=agent_id, unix_user=unix_user)
    if identity is not None:
        return identity
    target = agent_id or unix_user
    agent = get_agent(conn, target)
    if agent is None:
        raise ValueError(f"unknown agent or unix user: {target}")
    return ensure_agent_identity_for_user(
        conn,
        agent_id=str(agent["agent_id"]),
        unix_user=str(agent["unix_user"]),
        human_display_name=str(agent.get("display_name") or ""),
    )


def _validate_agent_identity_transition(
    existing: dict[str, Any],
    row: dict[str, Any],
    *,
    allow_unsuspend: bool,
) -> None:
    if not existing:
        return
    was_suspended = bool(_clean_text(existing.get("suspended_at")))
    will_be_suspended = bool(row["suspended_at"])
    if not was_suspended:
        return
    if not will_be_suspended and not allow_unsuspend:
        raise ValueError("cannot clear a suspended identity without explicit unsuspend")
    locked_fields = (
        "claimed_notion_email",
        "notion_user_id",
        "notion_user_email",
        "verification_status",
        "write_mode",
        "verified_at",
    )
    for field in locked_fields:
        if _clean_text(existing.get(field)) != row[field]:
            raise ValueError("cannot modify verification state for a suspended identity")


def _validate_agent_identity_state(row: dict[str, Any]) -> None:
    status = row["verification_status"]
    write_mode = row["write_mode"]
    if status == "verified":
        if not row["notion_user_id"]:
            raise ValueError("verified identities require a Notion user id")
        if write_mode != "verified_limited":
            raise ValueError("verified identities require verified_limited write mode")
        if not row["verified_at"]:
            raise ValueError("verified identities require verified_at")
        return
    if write_mode != "read_only":
        raise ValueError(f"{status} identities must stay read_only")
    if row["notion_user_id"] or row["notion_user_email"]:
        raise ValueError(f"{status} identities may not retain verified Notion identifiers")
    if row["verified_at"]:
        raise ValueError(f"{status} identities may not retain verified_at")
    if status == "pending" and not row["claimed_notion_email"]:
        raise ValueError("pending identities require a claimed Notion email")


def upsert_agent_identity(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    unix_user: str,
    human_display_name: str | None = None,
    agent_name: str | None = None,
    claimed_notion_email: str | None = None,
    notion_user_id: str | None = None,
    notion_user_email: str | None = None,
    verification_status: str | None = None,
    write_mode: str | None = None,
    verified_at: str | None = None,
    suspended_at: str | None = None,
    verification_source: str | None = None,
    notes: str | None = None,
    allow_unsuspend: bool = False,
) -> dict[str, Any]:
    existing = get_agent_identity(conn, agent_id=agent_id, unix_user=unix_user) or {}
    now_iso = utc_now_iso()
    row = {
        "agent_id": _clean_text(agent_id),
        "unix_user": _clean_text(unix_user),
        "human_display_name": _clean_text(
            existing.get("human_display_name")
            if human_display_name is None
            else human_display_name
        ),
        "agent_name": _clean_text(existing.get("agent_name") if agent_name is None else agent_name),
        "claimed_notion_email": _normalize_email(
            existing.get("claimed_notion_email") if claimed_notion_email is None else claimed_notion_email
        ),
        "notion_user_id": _clean_text(existing.get("notion_user_id") if notion_user_id is None else notion_user_id),
        "notion_user_email": _normalize_email(
            existing.get("notion_user_email") if notion_user_email is None else notion_user_email
        ),
        "verification_status": _clean_text(
            existing.get("verification_status") if verification_status is None else verification_status
        )
        or "unverified",
        "write_mode": _clean_text(existing.get("write_mode") if write_mode is None else write_mode) or "read_only",
        "verified_at": _clean_text(existing.get("verified_at") if verified_at is None else verified_at),
        "suspended_at": _clean_text(existing.get("suspended_at") if suspended_at is None else suspended_at),
        "verification_source": _clean_text(
            existing.get("verification_source") if verification_source is None else verification_source
        ),
        "notes": _clean_text(existing.get("notes") if notes is None else notes),
        "created_at": _clean_text(existing.get("created_at") or now_iso),
        "updated_at": now_iso,
    }
    if row["verification_status"] not in AGENT_IDENTITY_VERIFICATION_STATUSES:
        raise ValueError(
            "verification_status must be one of "
            + ", ".join(AGENT_IDENTITY_VERIFICATION_STATUSES)
        )
    if row["write_mode"] not in AGENT_IDENTITY_WRITE_MODES:
        raise ValueError("write_mode must be one of " + ", ".join(AGENT_IDENTITY_WRITE_MODES))
    _validate_agent_identity_transition(existing, row, allow_unsuspend=allow_unsuspend)
    _validate_agent_identity_state(row)
    try:
        conn.execute(
            """
            INSERT INTO agent_identity (
              unix_user, agent_id, human_display_name, agent_name, claimed_notion_email,
              notion_user_id, notion_user_email, verification_status, write_mode,
              verified_at, suspended_at, verification_source, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(unix_user) DO UPDATE SET
              agent_id = excluded.agent_id,
              human_display_name = excluded.human_display_name,
              agent_name = excluded.agent_name,
              claimed_notion_email = excluded.claimed_notion_email,
              notion_user_id = excluded.notion_user_id,
              notion_user_email = excluded.notion_user_email,
              verification_status = excluded.verification_status,
              write_mode = excluded.write_mode,
              verified_at = excluded.verified_at,
              suspended_at = excluded.suspended_at,
              verification_source = excluded.verification_source,
              notes = excluded.notes,
              updated_at = excluded.updated_at
            """,
            (
                row["unix_user"],
                row["agent_id"],
                row["human_display_name"],
                row["agent_name"],
                row["claimed_notion_email"],
                row["notion_user_id"],
                row["notion_user_email"],
                row["verification_status"],
                row["write_mode"],
                row["verified_at"] or None,
                row["suspended_at"] or None,
                row["verification_source"],
                row["notes"],
                row["created_at"],
                row["updated_at"],
            ),
        )
    except sqlite3.IntegrityError as exc:
        if "idx_agent_identity_claimed_email_active" in str(exc):
            raise ValueError(
                f"another active identity already claims {_normalize_email(row['claimed_notion_email'])}"
            ) from exc
        raise
    conn.commit()
    return get_agent_identity(conn, agent_id=agent_id, unix_user=unix_user) or row


def set_agent_identity_claim(
    conn: sqlite3.Connection,
    *,
    agent_id: str = "",
    unix_user: str = "",
    claimed_notion_email: str,
    verification_source: str = "operator",
) -> dict[str, Any]:
    identity = _resolve_identity_target(conn, agent_id=agent_id, unix_user=unix_user)
    return upsert_agent_identity(
        conn,
        agent_id=str(identity["agent_id"]),
        unix_user=str(identity["unix_user"]),
        claimed_notion_email=claimed_notion_email,
        notion_user_id="",
        notion_user_email="",
        verification_status="pending" if claimed_notion_email.strip() else "unverified",
        write_mode="read_only",
        verified_at="",
        suspended_at="",
        verification_source=verification_source,
    )


def mark_agent_identity_verified(
    conn: sqlite3.Connection,
    *,
    agent_id: str = "",
    unix_user: str = "",
    notion_user_id: str,
    notion_user_email: str = "",
    verification_source: str = "operator",
) -> dict[str, Any]:
    identity = _resolve_identity_target(conn, agent_id=agent_id, unix_user=unix_user)
    return upsert_agent_identity(
        conn,
        agent_id=str(identity["agent_id"]),
        unix_user=str(identity["unix_user"]),
        claimed_notion_email=notion_user_email or str(identity.get("claimed_notion_email") or ""),
        notion_user_id=notion_user_id,
        notion_user_email=notion_user_email,
        verification_status="verified",
        write_mode="verified_limited",
        verified_at=utc_now_iso(),
        suspended_at="",
        verification_source=verification_source,
    )


def suspend_agent_identity(
    conn: sqlite3.Connection,
    *,
    agent_id: str = "",
    unix_user: str = "",
) -> dict[str, Any]:
    identity = _resolve_identity_target(conn, agent_id=agent_id, unix_user=unix_user)
    if str(identity.get("suspended_at") or "").strip():
        return identity
    return upsert_agent_identity(
        conn,
        agent_id=str(identity["agent_id"]),
        unix_user=str(identity["unix_user"]),
        human_display_name=str(identity.get("human_display_name") or ""),
        agent_name=str(identity.get("agent_name") or ""),
        claimed_notion_email=str(identity.get("claimed_notion_email") or ""),
        notion_user_id=str(identity.get("notion_user_id") or ""),
        notion_user_email=str(identity.get("notion_user_email") or ""),
        verification_status=str(identity.get("verification_status") or "unverified"),
        write_mode=str(identity.get("write_mode") or "read_only"),
        verified_at=str(identity.get("verified_at") or ""),
        suspended_at=utc_now_iso(),
        verification_source=str(identity.get("verification_source") or ""),
        notes=str(identity.get("notes") or ""),
    )


def unsuspend_agent_identity(
    conn: sqlite3.Connection,
    *,
    agent_id: str = "",
    unix_user: str = "",
) -> dict[str, Any]:
    identity = _resolve_identity_target(conn, agent_id=agent_id, unix_user=unix_user)
    if not str(identity.get("suspended_at") or "").strip():
        return identity
    return upsert_agent_identity(
        conn,
        agent_id=str(identity["agent_id"]),
        unix_user=str(identity["unix_user"]),
        human_display_name=str(identity.get("human_display_name") or ""),
        agent_name=str(identity.get("agent_name") or ""),
        claimed_notion_email=str(identity.get("claimed_notion_email") or ""),
        notion_user_id=str(identity.get("notion_user_id") or ""),
        notion_user_email=str(identity.get("notion_user_email") or ""),
        verification_status=str(identity.get("verification_status") or "unverified"),
        write_mode=str(identity.get("write_mode") or "read_only"),
        verified_at=str(identity.get("verified_at") or ""),
        suspended_at="",
        verification_source=str(identity.get("verification_source") or ""),
        notes=str(identity.get("notes") or ""),
        allow_unsuspend=True,
    )


def ensure_agent_identity_for_user(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    unix_user: str,
    human_display_name: str = "",
    agent_name: str = "",
) -> dict[str, Any]:
    return upsert_agent_identity(
        conn,
        agent_id=agent_id,
        unix_user=unix_user,
        human_display_name=human_display_name,
        agent_name=agent_name,
    )


def get_notion_identity_claim(
    conn: sqlite3.Connection,
    *,
    claim_id: str = "",
    session_id: str = "",
    notion_page_id: str = "",
    latest: bool = False,
) -> dict[str, Any] | None:
    where: list[str] = []
    params: list[Any] = []
    if claim_id:
        where.append("claim_id = ?")
        params.append(claim_id)
    if session_id:
        where.append("session_id = ?")
        params.append(session_id)
    if notion_page_id:
        where.append("notion_page_id = ?")
        params.append(extract_notion_space_id(notion_page_id))
    if not where:
        raise ValueError("claim lookup requires claim_id, session_id, or notion_page_id")
    order = "updated_at DESC" if latest or session_id else "created_at DESC"
    row = conn.execute(
        f"""
        SELECT *
        FROM notion_identity_claims
        WHERE {' AND '.join(where)}
        ORDER BY {order}
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    return _notion_identity_claim_row_to_dict(row)


def list_notion_identity_claims(
    conn: sqlite3.Connection,
    *,
    session_id: str = "",
    agent_id: str = "",
    status: str = "",
) -> list[dict[str, Any]]:
    where: list[str] = []
    params: list[Any] = []
    if session_id:
        where.append("session_id = ?")
        params.append(session_id)
    if agent_id:
        where.append("agent_id = ?")
        params.append(agent_id)
    if status:
        where.append("status = ?")
        params.append(status)
    query = "SELECT * FROM notion_identity_claims"
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY created_at DESC"
    return [
        _notion_identity_claim_row_to_dict(row) or {}
        for row in conn.execute(query, tuple(params)).fetchall()
    ]


def _notion_verification_db_property_schema() -> dict[str, Any]:
    return {
        "Name": {"title": {}},
        "Claimed Email": {"email": {}},
        "Unix User": {"rich_text": {}},
        "Agent ID": {"rich_text": {}},
        "Session ID": {"rich_text": {}},
        "Status": {"rich_text": {}},
        "Verified": {"checkbox": {}},
        "Verified At": {"date": {}},
    }


def _notion_rich_text_value(value: str) -> dict[str, Any]:
    text = str(value or "").strip()
    if not text:
        return {"rich_text": []}
    return {
        "rich_text": [
            {
                "type": "text",
                "text": {"content": text[:1900]},
            }
        ]
    }


def _notion_property_type(property_payload: Any) -> str:
    if not isinstance(property_payload, dict):
        return ""
    return str(property_payload.get("type") or "").strip()


def _expected_notion_property_type(property_payload: dict[str, Any]) -> str:
    if not isinstance(property_payload, dict):
        return ""
    return next(iter(property_payload.keys()), "")


def _managed_database_schema_drift(
    *,
    actual_properties: dict[str, Any],
    expected_properties: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    missing: dict[str, Any] = {}
    wrong_types: list[str] = []
    for property_name, property_schema in expected_properties.items():
        actual = actual_properties.get(property_name)
        if actual is None:
            missing[property_name] = property_schema
            continue
        expected_type = _expected_notion_property_type(property_schema)
        actual_type = _notion_property_type(actual)
        if expected_type and actual_type != expected_type:
            wrong_types.append(f"{property_name} expected {expected_type}, found {actual_type or 'unknown'}")
    return missing, wrong_types


def _ensure_managed_database_schema(
    *,
    database_payload: dict[str, Any],
    data_source_payload: dict[str, Any],
    expected_properties: dict[str, Any],
    token: str,
    api_version: str,
    label: str,
    notion_kwargs: dict[str, Any] | None = None,
) -> None:
    kwargs = notion_kwargs or {}
    schema_payload = data_source_payload or database_payload
    actual_properties = schema_payload.get("properties") if isinstance(schema_payload, dict) else {}
    if not isinstance(actual_properties, dict):
        actual_properties = {}
    missing, wrong_types = _managed_database_schema_drift(
        actual_properties=actual_properties,
        expected_properties=expected_properties,
    )
    if missing:
        data_source_id = notion_database_data_source_id(database_payload)
        if data_source_id:
            update_notion_data_source(
                data_source_id=data_source_id,
                token=token,
                api_version=api_version,
                payload={"properties": missing},
                **kwargs,
            )
            refreshed_database = retrieve_notion_database(
                database_id=str(database_payload.get("id") or ""),
                token=token,
                api_version=api_version,
                **kwargs,
            )
            refreshed_data_source = {}
            refreshed_data_source_id = notion_database_data_source_id(refreshed_database)
            if refreshed_data_source_id:
                refreshed_data_source = retrieve_notion_data_source(
                    data_source_id=refreshed_data_source_id,
                    token=token,
                    api_version=api_version,
                    **kwargs,
                )
            schema_payload = refreshed_data_source or refreshed_database
            actual_properties = schema_payload.get("properties") if isinstance(schema_payload, dict) else {}
            if not isinstance(actual_properties, dict):
                actual_properties = {}
            missing, wrong_types = _managed_database_schema_drift(
                actual_properties=actual_properties,
                expected_properties=expected_properties,
            )
        else:
            raise RuntimeError(
                f"{label} is missing required properties ({', '.join(sorted(missing))}) and does not expose a data source for repair"
            )
    if missing or wrong_types:
        details: list[str] = []
        if missing:
            details.append("missing: " + ", ".join(sorted(missing)))
        if wrong_types:
            details.append("wrong types: " + "; ".join(wrong_types))
        raise RuntimeError(f"{label} schema drift detected; {'; '.join(details)}")


def _verification_claim_parent_page_id(
    *,
    settings: dict[str, str],
    urlopen_fn=None,
) -> str:
    notion_kwargs: dict[str, Any] = {}
    if urlopen_fn is not None:
        notion_kwargs["urlopen_fn"] = urlopen_fn
    if settings.get("root_page_id"):
        return str(settings["root_page_id"]).strip()
    if settings["space_kind"] == "page":
        return settings["space_id"]
    database = retrieve_notion_database(
        database_id=settings["space_id"],
        token=settings["token"],
        api_version=settings["api_version"],
        **notion_kwargs,
    )
    parent = database.get("parent") if isinstance(database, dict) else {}
    if isinstance(parent, dict) and str(parent.get("type") or "").strip() == "page_id":
        return str(parent.get("page_id") or "").strip()
    raise RuntimeError(
        "shared Notion self-serve verification needs the SSOT target to be a page or a page-owned database"
    )


def _verification_db_parent_page_id(
    *,
    settings: dict[str, str],
    urlopen_fn=None,
) -> str:
    return _verification_claim_parent_page_id(settings=settings, urlopen_fn=urlopen_fn)


def ensure_notion_verification_database(
    conn: sqlite3.Connection,
    *,
    urlopen_fn=None,
) -> dict[str, str]:
    settings = _require_shared_notion_settings()
    cached_id = get_setting(conn, NOTION_VERIFICATION_DB_ID_SETTING, "").strip()
    cached_url = get_setting(conn, NOTION_VERIFICATION_DB_URL_SETTING, "").strip()
    cached_parent = get_setting(conn, NOTION_VERIFICATION_DB_PARENT_SETTING, "").strip()
    desired_parent = _verification_db_parent_page_id(settings=settings, urlopen_fn=urlopen_fn)
    notion_kwargs: dict[str, Any] = {}
    if urlopen_fn is not None:
        notion_kwargs["urlopen_fn"] = urlopen_fn
    if cached_id and (not desired_parent or not cached_parent or cached_parent == desired_parent):
        database_missing = False
        try:
            database = retrieve_notion_database(
                database_id=cached_id,
                token=settings["token"],
                api_version=settings["api_version"],
                **notion_kwargs,
            )
        except RuntimeError as exc:
            if "could not retrieve database" not in str(exc).lower():
                raise
            database_missing = True
        if not database_missing:
            data_source_payload = {}
            data_source_id = notion_database_data_source_id(database)
            if data_source_id:
                data_source_payload = retrieve_notion_data_source(
                    data_source_id=data_source_id,
                    token=settings["token"],
                    api_version=settings["api_version"],
                    **notion_kwargs,
                )
            _ensure_managed_database_schema(
                database_payload=database,
                data_source_payload=data_source_payload,
                expected_properties=_notion_verification_db_property_schema(),
                token=settings["token"],
                api_version=settings["api_version"],
                label="Almanac verification database",
                notion_kwargs=notion_kwargs,
            )
            return {
                "database_id": str(database.get("id") or cached_id).strip() or cached_id,
                "database_url": cached_url or str(database.get("url") or "").strip(),
                "parent_page_id": cached_parent or desired_parent,
            }
    parent_page_id = desired_parent
    database = create_notion_database(
        parent_page_id=parent_page_id,
        title="Almanac Verification",
        description=(
            "Self-serve verification claims for shared Almanac Notion access. "
            "Users edit their own claim row/page to prove control of the claimed Notion identity."
        ),
        properties=_notion_verification_db_property_schema(),
        token=settings["token"],
        api_version=settings["api_version"],
        **notion_kwargs,
    )
    database_id = str(database.get("id") or "").strip()
    database_url = str(database.get("url") or "").strip()
    if not database_id:
        raise RuntimeError("Notion created the verification database without returning an id")
    data_source_id = notion_database_data_source_id(database)
    data_source_payload = {}
    if data_source_id:
        data_source_payload = retrieve_notion_data_source(
            data_source_id=data_source_id,
            token=settings["token"],
            api_version=settings["api_version"],
            **notion_kwargs,
        )
    _ensure_managed_database_schema(
        database_payload=database,
        data_source_payload=data_source_payload,
        expected_properties=_notion_verification_db_property_schema(),
        token=settings["token"],
        api_version=settings["api_version"],
        label="Almanac verification database",
        notion_kwargs=notion_kwargs,
    )
    upsert_setting(conn, NOTION_VERIFICATION_DB_ID_SETTING, database_id)
    upsert_setting(conn, NOTION_VERIFICATION_DB_URL_SETTING, database_url)
    upsert_setting(conn, NOTION_VERIFICATION_DB_PARENT_SETTING, parent_page_id)
    return {
        "database_id": database_id,
        "database_url": database_url,
        "parent_page_id": parent_page_id,
    }


def mark_notion_identity_claim(
    conn: sqlite3.Connection,
    *,
    claim_id: str,
    status: str,
    failure_reason: str | None = None,
    verified_notion_user_id: str | None = None,
    verified_notion_email: str | None = None,
    verified_at: str | None = None,
) -> dict[str, Any]:
    current = get_notion_identity_claim(conn, claim_id=claim_id)
    if current is None:
        raise ValueError(f"unknown notion identity claim: {claim_id}")
    now_iso = utc_now_iso()
    conn.execute(
        """
        UPDATE notion_identity_claims
        SET status = ?,
            failure_reason = COALESCE(?, failure_reason),
            verified_notion_user_id = COALESCE(?, verified_notion_user_id),
            verified_notion_email = COALESCE(?, verified_notion_email),
            verified_at = COALESCE(?, verified_at),
            updated_at = ?
        WHERE claim_id = ?
        """,
        (
            str(status or "").strip() or current["status"],
            failure_reason,
            verified_notion_user_id,
            _normalize_email(verified_notion_email or ""),
            verified_at,
            now_iso,
            claim_id,
        ),
    )
    conn.commit()
    return get_notion_identity_claim(conn, claim_id=claim_id) or current


def expire_stale_notion_identity_claims(conn: sqlite3.Connection) -> int:
    now_iso = utc_now_iso()
    cursor = conn.execute(
        """
        UPDATE notion_identity_claims
        SET status = 'expired',
            updated_at = ?,
            failure_reason = CASE
              WHEN failure_reason = '' THEN 'claim expired before verification'
              ELSE failure_reason
            END
        WHERE status = 'pending' AND expires_at < ?
        """,
        (now_iso, now_iso),
    )
    conn.commit()
    return int(cursor.rowcount or 0)


def start_notion_identity_claim(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    agent_id: str,
    unix_user: str,
    claimed_notion_email: str,
    urlopen_fn=None,
) -> dict[str, Any]:
    normalized_email = _normalize_email(claimed_notion_email)
    if not normalized_email or "@" not in normalized_email:
        raise ValueError("Reply with the Notion email you use in the shared workspace, or `skip`.")
    for claim in list_notion_identity_claims(conn, session_id=session_id):
        if str(claim.get("status") or "") == "pending":
            mark_notion_identity_claim(
                conn,
                claim_id=str(claim["claim_id"]),
                status="expired",
                failure_reason="superseded by a newer verification claim",
            )
    identity = set_agent_identity_claim(
        conn,
        agent_id=agent_id,
        unix_user=unix_user,
        claimed_notion_email=normalized_email,
        verification_source=f"self-serve-claim:{normalized_email}",
    )
    claim_id = f"nclaim_{secrets.token_hex(8)}"
    now_iso = utc_now_iso()
    expires_at = (utc_now() + dt.timedelta(hours=24)).replace(microsecond=0).isoformat()
    settings = _require_shared_notion_settings()
    verification_parent_page_id = _verification_claim_parent_page_id(settings=settings, urlopen_fn=urlopen_fn)
    notion_kwargs: dict[str, Any] = {}
    if urlopen_fn is not None:
        notion_kwargs["urlopen_fn"] = urlopen_fn
    page = create_notion_page(
        parent_id=verification_parent_page_id,
        parent_kind="page",
        token=settings["token"],
        api_version=settings["api_version"],
        payload={
            "properties": {
                "title": [
                    {
                        "type": "text",
                        "text": {"content": f"Almanac Verification: {unix_user}"},
                    }
                ]
            },
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": (
                                        "Edit anything on this page to prove you control the claimed Notion user. "
                                        "Almanac will verify the edit automatically."
                                    )
                                },
                            }
                        ]
                    },
                },
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": f"Claimed Notion email: {normalized_email}"},
                            }
                        ]
                    },
                },
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": f"Almanac Unix user: {unix_user}"},
                            }
                        ]
                    },
                },
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": f"Agent ID: {agent_id}"},
                            }
                        ]
                    },
                }
            ],
        },
        **notion_kwargs,
    )
    notion_page_id = str(page.get("id") or "").strip()
    notion_page_url = str(page.get("url") or "").strip()
    conn.execute(
        """
        INSERT INTO notion_identity_claims (
          claim_id, session_id, agent_id, unix_user, claimed_notion_email,
          notion_page_id, notion_page_url, status, failure_reason,
          verified_notion_user_id, verified_notion_email, created_at, updated_at, expires_at, verified_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', '', '', '', ?, ?, ?, NULL)
        """,
        (
            claim_id,
            session_id,
            agent_id,
            unix_user,
            normalized_email,
            notion_page_id,
            notion_page_url,
            now_iso,
            now_iso,
            expires_at,
        ),
    )
    conn.commit()
    claim = get_notion_identity_claim(conn, claim_id=claim_id) or {}
    claim["identity"] = identity
    claim["verification_parent_page_id"] = verification_parent_page_id
    return claim


def try_verify_notion_identity_claim(
    conn: sqlite3.Connection,
    *,
    claim: dict[str, Any],
    page_payload: dict[str, Any] | None = None,
    verification_source: str,
    urlopen_fn=None,
) -> dict[str, Any] | None:
    if str(claim.get("status") or "").strip() != "pending":
        return claim
    if str(claim.get("expires_at") or "").strip() and str(claim.get("expires_at")) < utc_now_iso():
        return mark_notion_identity_claim(
            conn,
            claim_id=str(claim["claim_id"]),
            status="expired",
            failure_reason="claim expired before verification",
        )
    settings = _require_shared_notion_settings()
    notion_kwargs: dict[str, Any] = {}
    if urlopen_fn is not None:
        notion_kwargs["urlopen_fn"] = urlopen_fn
    page = page_payload or retrieve_notion_page(
        page_id=str(claim.get("notion_page_id") or ""),
        token=settings["token"],
        api_version=settings["api_version"],
        **notion_kwargs,
    )
    agent_id = str(claim.get("agent_id") or "")
    unix_user = str(claim.get("unix_user") or "")
    target_id = str(claim.get("notion_page_id") or "")
    last_edited_by = page.get("last_edited_by") if isinstance(page, dict) else {}
    if not isinstance(last_edited_by, dict):
        return None
    if (
        str(last_edited_by.get("object") or "").strip() == "user"
        and str(last_edited_by.get("type") or "").strip() != "person"
    ):
        notion_user_id = str(last_edited_by.get("id") or "").strip()
        if notion_user_id:
            try:
                resolved_user = retrieve_notion_user(
                    user_id=notion_user_id,
                    token=settings["token"],
                    api_version=settings["api_version"],
                    **notion_kwargs,
                )
            except Exception:
                resolved_user = {}
            if isinstance(resolved_user, dict):
                merged_user = dict(resolved_user)
                merged_user.setdefault("id", notion_user_id)
                last_edited_by = merged_user
    if str(last_edited_by.get("type") or "").strip() != "person":
        mark_notion_identity_claim(
            conn,
            claim_id=str(claim["claim_id"]),
            status="pending",
            failure_reason="awaiting a human edit on the verification page",
        )
        log_ssot_access_audit(
            conn,
            agent_id=agent_id,
            unix_user=unix_user,
            notion_user_id="",
            operation="verify-identity",
            target_id=target_id,
            decision="deny",
            reason="verification page was last edited by a bot or non-person actor",
            actor=verification_source,
            request_payload={"claim_id": str(claim.get("claim_id") or ""), "claimed_email": str(claim.get("claimed_notion_email") or "")},
        )
        return None
    person = last_edited_by.get("person") if isinstance(last_edited_by.get("person"), dict) else {}
    email = _normalize_email(str(person.get("email") or last_edited_by.get("email") or ""))
    notion_user_id = str(last_edited_by.get("id") or "").strip()
    override = get_notion_identity_override(
        conn,
        agent_id=agent_id,
        unix_user=unix_user,
    )
    if email != _normalize_email(str(claim.get("claimed_notion_email") or "")):
        override_values = {value.lower() for value in _notion_identity_override_values(override)}
        if email.lower() not in override_values and notion_user_id.lower() not in override_values:
            mark_notion_identity_claim(
                conn,
                claim_id=str(claim["claim_id"]),
                status="pending",
                failure_reason="the most recent edit came from a different Notion email",
            )
            log_ssot_access_audit(
                conn,
                agent_id=agent_id,
                unix_user=unix_user,
                notion_user_id="",
                operation="verify-identity",
                target_id=target_id,
                decision="deny",
                reason="verification page edit came from a different Notion email",
                actor=verification_source,
                request_payload={"claim_id": str(claim.get("claim_id") or ""), "claimed_email": str(claim.get("claimed_notion_email") or ""), "observed_email": email},
            )
            return None
    if not notion_user_id:
        mark_notion_identity_claim(
            conn,
            claim_id=str(claim["claim_id"]),
            status="pending",
            failure_reason="the verification edit did not expose a Notion user id",
        )
        log_ssot_access_audit(
            conn,
            agent_id=agent_id,
            unix_user=unix_user,
            notion_user_id="",
            operation="verify-identity",
            target_id=target_id,
            decision="deny",
            reason="verification page edit did not expose a Notion user id",
            actor=verification_source,
            request_payload={"claim_id": str(claim.get("claim_id") or ""), "claimed_email": str(claim.get("claimed_notion_email") or ""), "observed_email": email},
        )
        return None
    if override is not None:
        override_values = {value.lower() for value in _notion_identity_override_values(override)}
        if override_values and notion_user_id.lower() not in override_values and email.lower() not in override_values:
            mark_notion_identity_claim(
                conn,
                claim_id=str(claim["claim_id"]),
                status="pending",
                failure_reason="the verification edit did not match the explicit Notion identity override",
            )
            log_ssot_access_audit(
                conn,
                agent_id=agent_id,
                unix_user=unix_user,
                notion_user_id=notion_user_id,
                operation="verify-identity",
                target_id=target_id,
                decision="deny",
                reason="verification page edit did not match the explicit Notion identity override",
                actor=verification_source,
                request_payload={"claim_id": str(claim.get("claim_id") or ""), "observed_email": email, "observed_user_id": notion_user_id},
            )
            return None
    mark_agent_identity_verified(
        conn,
        agent_id=str(claim.get("agent_id") or ""),
        unix_user=str(claim.get("unix_user") or ""),
        notion_user_id=notion_user_id,
        notion_user_email=email,
        verification_source=verification_source,
    )
    verified_at = utc_now_iso()
    verified_claim = mark_notion_identity_claim(
        conn,
        claim_id=str(claim["claim_id"]),
        status="verified",
        failure_reason="",
        verified_notion_user_id=notion_user_id,
        verified_notion_email=email,
        verified_at=verified_at,
    )
    page_parent = page.get("parent") if isinstance(page, dict) else {}
    page_parent_type = str(page_parent.get("type") or "").strip() if isinstance(page_parent, dict) else ""
    if page_parent_type in {"database_id", "data_source_id"}:
        try:
            update_notion_page(
                page_id=str(claim.get("notion_page_id") or ""),
                token=settings["token"],
                api_version=settings["api_version"],
                payload={
                    "properties": {
                        "Status": _notion_rich_text_value("verified"),
                        "Verified": {"checkbox": True},
                        "Verified At": {"date": {"start": verified_at}},
                    }
                },
                **notion_kwargs,
            )
        except Exception:
            pass
    queue_notification(
        conn,
        target_kind="curator",
        target_id=str(claim.get("agent_id") or ""),
        channel_kind="brief-fanout",
        message=f"shared notion verification updated for {claim.get('agent_id') or ''}",
    )
    log_ssot_access_audit(
        conn,
        agent_id=agent_id,
        unix_user=unix_user,
        notion_user_id=notion_user_id,
        operation="verify-identity",
        target_id=target_id,
        decision="allow",
        reason="self-serve notion verification succeeded",
        actor=verification_source,
        request_payload={"claim_id": str(claim.get("claim_id") or ""), "claimed_email": str(claim.get("claimed_notion_email") or ""), "verified_email": email},
    )
    return verified_claim


def log_ssot_access_audit(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    unix_user: str,
    notion_user_id: str,
    operation: str,
    target_id: str,
    decision: str,
    reason: str,
    actor: str = "",
    request_payload: dict[str, Any] | None = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO ssot_access_audit (
          agent_id, unix_user, notion_user_id, operation, target_id, decision,
          reason, actor, request_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            agent_id,
            unix_user,
            notion_user_id,
            operation,
            target_id,
            decision,
            reason,
            actor,
            json_dumps(request_payload or {}),
            utc_now_iso(),
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def list_ssot_access_audit(
    conn: sqlite3.Connection,
    *,
    agent_id: str = "",
    unix_user: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if agent_id:
        clauses.append("agent_id = ?")
        params.append(agent_id)
    if unix_user:
        clauses.append("unix_user = ?")
        params.append(unix_user)
    query = "SELECT * FROM ssot_access_audit"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, int(limit)))
    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_token_id() -> str:
    return f"tok_{secrets.token_hex(8)}"


def generate_raw_token() -> str:
    return secrets.token_urlsafe(32)


def generate_request_id() -> str:
    return f"req_{secrets.token_hex(16)}"


def generate_onboarding_session_id() -> str:
    return f"onb_{secrets.token_hex(8)}"


class RateLimitError(RuntimeError):
    def __init__(self, message: str, *, retry_after_seconds: int, scope: str) -> None:
        super().__init__(message)
        self.retry_after_seconds = int(retry_after_seconds)
        self.scope = scope


def ensure_request_expiry(conn: sqlite3.Connection) -> None:
    now_iso = utc_now_iso()
    conn.execute(
        """
        UPDATE bootstrap_requests
        SET status = 'expired'
        WHERE status = 'pending' AND expires_at < ?
        """,
        (now_iso,),
    )
    conn.commit()


def record_rate_limit_event(conn: sqlite3.Connection, scope: str, subject: str) -> None:
    conn.execute(
        "INSERT INTO rate_limits (scope, subject, observed_at) VALUES (?, ?, ?)",
        (scope, subject, utc_now_iso()),
    )
    conn.commit()


def rate_limit_count(conn: sqlite3.Connection, scope: str, subject: str, since_iso: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM rate_limits
        WHERE scope = ? AND subject = ? AND observed_at >= ?
        """,
        (scope, subject, since_iso),
    ).fetchone()
    return int(row["count"] if row else 0)


TERMINAL_ONBOARDING_STATES = ("denied", "completed", "cancelled")
NOTION_VERIFICATION_DB_ID_SETTING = "notion_verification_database_id"
NOTION_VERIFICATION_DB_URL_SETTING = "notion_verification_database_url"
NOTION_VERIFICATION_DB_PARENT_SETTING = "notion_verification_database_parent_page_id"
NOTION_SLO_P50_SECONDS = 60
NOTION_SLO_P99_SECONDS = 600
NOTION_CLAIM_ACTIVE_STATUSES = ("pending", "verified")
NOTION_CLAIM_TERMINAL_STATUSES = ("verified", "skipped", "expired", "failed")


def _write_private_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(value.strip() + "\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def onboarding_secret_dir(cfg: Config) -> Path:
    path = cfg.state_dir / "onboarding-secrets"
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def onboarding_bot_token_secret_path(cfg: Config, session_id: str) -> Path:
    return onboarding_platform_token_secret_path(cfg, session_id, "telegram")


def onboarding_named_secret_path(cfg: Config, session_id: str, secret_name: str) -> Path:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", str(secret_name or "secret").strip().lower()) or "secret"
    return onboarding_secret_dir(cfg) / session_id / normalized


def onboarding_platform_token_secret_path(cfg: Config, session_id: str, platform: str) -> Path:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", str(platform or "bot").strip().lower()) or "bot"
    return onboarding_secret_dir(cfg) / session_id / f"{normalized}-bot-token"


def write_onboarding_secret(cfg: Config, session_id: str, secret_name: str, raw_value: str) -> str:
    path = onboarding_named_secret_path(cfg, session_id, secret_name)
    _write_private_text(path, raw_value)
    return str(path)


def write_onboarding_bot_token_secret(cfg: Config, session_id: str, raw_token: str) -> str:
    path = onboarding_platform_token_secret_path(cfg, session_id, "telegram")
    _write_private_text(path, raw_token)
    return str(path)


def write_onboarding_platform_token_secret(
    cfg: Config,
    session_id: str,
    platform: str,
    raw_token: str,
) -> str:
    path = onboarding_platform_token_secret_path(cfg, session_id, platform)
    _write_private_text(path, raw_token)
    return str(path)


def read_onboarding_secret(raw_path: str) -> str:
    path = Path(raw_path).expanduser()
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def read_onboarding_bot_token_secret(raw_path: str) -> str:
    return read_onboarding_secret(raw_path)


def delete_onboarding_secret(raw_path: str) -> None:
    if not raw_path:
        return
    path = Path(raw_path).expanduser()
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return
    parent = path.parent
    try:
        parent.rmdir()
    except OSError:
        pass


def delete_onboarding_bot_token_secret(raw_path: str) -> None:
    delete_onboarding_secret(raw_path)


def _migrate_onboarding_bot_tokens(conn: sqlite3.Connection, cfg: Config) -> None:
    rows = conn.execute(
        """
        SELECT session_id, pending_bot_token, pending_bot_token_path
        FROM onboarding_sessions
        WHERE pending_bot_token IS NOT NULL
          AND pending_bot_token != ''
        """
    ).fetchall()
    if not rows:
        return
    now_iso = utc_now_iso()
    for row in rows:
        session_id = str(row["session_id"] or "").strip()
        token = str(row["pending_bot_token"] or "").strip()
        existing_path = str(row["pending_bot_token_path"] or "").strip()
        if not session_id or not token:
            continue
        if existing_path:
            _write_private_text(Path(existing_path), token)
            secret_path = existing_path
        else:
            secret_path = write_onboarding_platform_token_secret(cfg, session_id, "telegram", token)
        conn.execute(
            """
            UPDATE onboarding_sessions
            SET pending_bot_token = '',
                pending_bot_token_path = ?,
                updated_at = ?
            WHERE session_id = ?
            """,
            (secret_path, now_iso, session_id),
        )
    conn.commit()


def _onboarding_row_to_dict(
    row: sqlite3.Row | None,
    *,
    redact_secrets: bool = True,
) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = dict(row)
    payload["answers"] = json_loads(str(payload.get("answers_json") or ""), {})
    has_pending_secret = bool(
        str(payload.get("pending_bot_token") or "").strip()
        or str(payload.get("pending_bot_token_path") or "").strip()
    )
    payload["pending_bot_token_present"] = has_pending_secret
    if redact_secrets:
        payload["pending_bot_token"] = "[redacted]" if has_pending_secret else ""
        payload["pending_bot_token_path"] = (
            "[redacted]" if str(payload.get("pending_bot_token_path") or "").strip() else ""
        )
    return payload


def find_active_onboarding_session(
    conn: sqlite3.Connection,
    *,
    platform: str,
    sender_id: str,
    redact_secrets: bool = True,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM onboarding_sessions
        WHERE platform = ?
          AND sender_id = ?
          AND state NOT IN ('denied', 'completed', 'cancelled')
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (platform, sender_id),
    ).fetchone()
    return _onboarding_row_to_dict(row, redact_secrets=redact_secrets)


def get_onboarding_session(
    conn: sqlite3.Connection,
    session_id: str,
    *,
    redact_secrets: bool = True,
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM onboarding_sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    return _onboarding_row_to_dict(row, redact_secrets=redact_secrets)


def list_onboarding_sessions(
    conn: sqlite3.Connection,
    *,
    redact_secrets: bool = True,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM onboarding_sessions
        ORDER BY updated_at DESC
        """
    ).fetchall()
    return [
        _onboarding_row_to_dict(row, redact_secrets=redact_secrets) or {}
        for row in rows
    ]


def find_latest_onboarding_session_for_sender(
    conn: sqlite3.Connection,
    *,
    platform: str,
    sender_id: str,
    redact_secrets: bool = True,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM onboarding_sessions
        WHERE platform = ?
          AND sender_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (platform, sender_id),
    ).fetchone()
    return _onboarding_row_to_dict(row, redact_secrets=redact_secrets)


def start_onboarding_session(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    platform: str,
    chat_id: str,
    sender_id: str,
    sender_username: str = "",
    sender_display_name: str = "",
) -> dict[str, Any]:
    existing = find_active_onboarding_session(conn, platform=platform, sender_id=sender_id)
    if existing is not None:
        conn.execute(
            """
            UPDATE onboarding_sessions
            SET chat_id = ?, sender_username = ?, sender_display_name = ?, updated_at = ?
            WHERE session_id = ?
            """,
            (chat_id, sender_username or None, sender_display_name or None, utc_now_iso(), existing["session_id"]),
        )
        conn.commit()
        return get_onboarding_session(conn, str(existing["session_id"])) or existing

    window_start = (utc_now() - dt.timedelta(seconds=cfg.onboarding_window_seconds)).replace(microsecond=0).isoformat()
    subject = f"{platform}:{sender_id}"
    if rate_limit_count(conn, "onboarding-user", subject, window_start) >= cfg.onboarding_per_telegram_user_limit:
        raise RateLimitError(
            (
                "rate-limited: onboarding start limit "
                f"({cfg.onboarding_per_telegram_user_limit}) exceeded for {subject}"
            ),
            retry_after_seconds=cfg.onboarding_window_seconds,
            scope="onboarding-user",
        )

    pending_count = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM onboarding_sessions
        WHERE state NOT IN ('denied', 'completed', 'cancelled')
        """
    ).fetchone()
    if pending_count and int(pending_count["count"]) >= cfg.onboarding_global_pending_limit:
        raise RateLimitError(
            (
                "rate-limited: onboarding pending limit "
                f"({cfg.onboarding_global_pending_limit}) exceeded"
            ),
            retry_after_seconds=cfg.onboarding_window_seconds,
            scope="onboarding-global",
        )

    record_rate_limit_event(conn, "onboarding-user", subject)
    session_id = generate_onboarding_session_id()
    now_iso = utc_now_iso()
    conn.execute(
        """
        INSERT INTO onboarding_sessions (
          session_id, platform, chat_id, sender_id, sender_username, sender_display_name,
          state, answers_json, created_at, updated_at, last_prompt_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'awaiting-name', '{}', ?, ?, ?)
        """,
        (
            session_id,
            platform,
            chat_id,
            sender_id,
            sender_username or None,
            sender_display_name or None,
            now_iso,
            now_iso,
            now_iso,
        ),
    )
    conn.commit()
    return get_onboarding_session(conn, session_id) or {}


def save_onboarding_session(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    state: str | None = None,
    answers: dict[str, Any] | None = None,
    chat_id: str | None = None,
    sender_username: str | None = None,
    sender_display_name: str | None = None,
    operator_notified_at: str | None = None,
    approved_at: str | None = None,
    approved_by_actor: str | None = None,
    denied_at: str | None = None,
    denied_by_actor: str | None = None,
    denial_reason: str | None = None,
    linked_request_id: str | None = None,
    linked_agent_id: str | None = None,
    telegram_bot_id: str | None = None,
    telegram_bot_username: str | None = None,
    pending_bot_token: str | None = None,
    pending_bot_token_path: str | None = None,
    provision_error: str | None = None,
    completed_at: str | None = None,
    last_prompt_at: str | None = None,
) -> dict[str, Any]:
    current = get_onboarding_session(conn, session_id, redact_secrets=False)
    if current is None:
        raise ValueError(f"unknown onboarding session: {session_id}")
    merged_answers = current.get("answers", {})
    if answers is not None:
        merged_answers = dict(merged_answers)
        merged_answers.update(answers)
    conn.execute(
        """
        UPDATE onboarding_sessions
        SET state = COALESCE(?, state),
            answers_json = ?,
            chat_id = COALESCE(?, chat_id),
            sender_username = COALESCE(?, sender_username),
            sender_display_name = COALESCE(?, sender_display_name),
            operator_notified_at = COALESCE(?, operator_notified_at),
            approved_at = COALESCE(?, approved_at),
            approved_by_actor = COALESCE(?, approved_by_actor),
            denied_at = COALESCE(?, denied_at),
            denied_by_actor = COALESCE(?, denied_by_actor),
            denial_reason = COALESCE(?, denial_reason),
            linked_request_id = COALESCE(?, linked_request_id),
            linked_agent_id = COALESCE(?, linked_agent_id),
            telegram_bot_id = COALESCE(?, telegram_bot_id),
            telegram_bot_username = COALESCE(?, telegram_bot_username),
            pending_bot_token = CASE
                WHEN ? IS NOT NULL THEN ?
                ELSE pending_bot_token
            END,
            pending_bot_token_path = CASE
                WHEN ? IS NOT NULL THEN ?
                ELSE pending_bot_token_path
            END,
            provision_error = CASE
                WHEN ? IS NOT NULL THEN ?
                ELSE provision_error
            END,
            completed_at = COALESCE(?, completed_at),
            last_prompt_at = COALESCE(?, last_prompt_at),
            updated_at = ?
        WHERE session_id = ?
        """,
        (
            state,
            json_dumps(merged_answers),
            chat_id,
            sender_username,
            sender_display_name,
            operator_notified_at,
            approved_at,
            approved_by_actor,
            denied_at,
            denied_by_actor,
            denial_reason,
            linked_request_id,
            linked_agent_id,
            telegram_bot_id,
            telegram_bot_username,
            pending_bot_token,
            pending_bot_token,
            pending_bot_token_path,
            pending_bot_token_path,
            provision_error,
            provision_error,
            completed_at,
            last_prompt_at,
            utc_now_iso(),
            session_id,
        ),
    )
    conn.commit()
    return get_onboarding_session(conn, session_id) or {}


def onboarding_session_has_started_provisioning(session: dict[str, Any]) -> bool:
    state = str(session.get("state") or "").strip().lower()
    if state == "provision-pending":
        return True
    if str(session.get("linked_request_id") or "").strip():
        return True
    if str(session.get("linked_agent_id") or "").strip():
        return True
    return False


def delete_onboarding_session_secrets(cfg: Config, session_id: str) -> None:
    path = onboarding_secret_dir(cfg) / session_id
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        return
    except OSError:
        return


def cancel_onboarding_session(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    session_id: str,
) -> dict[str, Any]:
    session = get_onboarding_session(conn, session_id, redact_secrets=False)
    if session is None:
        raise ValueError(f"unknown onboarding session: {session_id}")
    if onboarding_session_has_started_provisioning(session):
        raise ValueError(f"onboarding session has already started provisioning: {session_id}")

    delete_onboarding_session_secrets(cfg, session_id)
    now_iso = utc_now_iso()
    conn.execute(
        """
        UPDATE onboarding_sessions
        SET state = 'cancelled',
            answers_json = '{}',
            operator_notified_at = '',
            approved_at = '',
            approved_by_actor = '',
            denied_at = '',
            denied_by_actor = '',
            denial_reason = '',
            linked_request_id = '',
            linked_agent_id = '',
            telegram_bot_id = '',
            telegram_bot_username = '',
            pending_bot_token = '',
            pending_bot_token_path = '',
            provision_error = '',
            completed_at = ?,
            updated_at = ?
        WHERE session_id = ?
        """,
        (now_iso, now_iso, session_id),
    )
    conn.commit()
    return get_onboarding_session(conn, session_id) or {}


def approve_onboarding_session(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    actor: str,
) -> dict[str, Any]:
    session = get_onboarding_session(conn, session_id)
    if session is None:
        raise ValueError(f"unknown onboarding session: {session_id}")
    if str(session["state"]) == "denied":
        raise ValueError("onboarding session is already denied")
    if str(session["state"]) == "completed":
        raise ValueError("onboarding session is already completed")
    if str(session["state"]) not in {"awaiting-operator-approval", "awaiting-bot-token", "provision-pending"}:
        raise ValueError(f"onboarding session is not ready for operator approval: {session['state']}")
    return save_onboarding_session(
        conn,
        session_id=session_id,
        state="awaiting-bot-token",
        approved_at=utc_now_iso(),
        approved_by_actor=actor,
        denied_at="",
        denied_by_actor="",
        denial_reason="",
        provision_error="",
    )


def deny_onboarding_session(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    actor: str,
    reason: str = "",
) -> dict[str, Any]:
    session = get_onboarding_session(conn, session_id)
    if session is None:
        raise ValueError(f"unknown onboarding session: {session_id}")
    if str(session["state"]) == "completed":
        raise ValueError("onboarding session is already completed")
    now_iso = utc_now_iso()
    return save_onboarding_session(
        conn,
        session_id=session_id,
        state="denied",
        denied_at=now_iso,
        denied_by_actor=actor,
        denial_reason=reason or "denied",
        completed_at=now_iso,
        provision_error="",
    )


def list_pending_onboarding_bot_configurations(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT s.*, r.status AS request_status, r.provisioned_at
        FROM onboarding_sessions AS s
        JOIN bootstrap_requests AS r
          ON r.request_id = s.linked_request_id
        WHERE (
                (s.pending_bot_token IS NOT NULL AND s.pending_bot_token != '')
             OR (s.pending_bot_token_path IS NOT NULL AND s.pending_bot_token_path != '')
              )
          AND s.state = 'provision-pending'
          AND r.provisioned_at IS NOT NULL
        ORDER BY s.updated_at ASC
        """
    ).fetchall()
    return [_onboarding_row_to_dict(row, redact_secrets=False) or {} for row in rows]


def get_onboarding_update_failure(conn: sqlite3.Connection, update_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM onboarding_update_failures WHERE update_id = ?",
        (update_id,),
    ).fetchone()
    return dict(row) if row else None


def record_onboarding_update_failure(
    conn: sqlite3.Connection,
    *,
    update_id: str,
    error: str,
) -> dict[str, Any]:
    now_iso = utc_now_iso()
    conn.execute(
        """
        INSERT INTO onboarding_update_failures (
          update_id, failure_count, first_failed_at, last_failed_at, last_error
        )
        VALUES (?, 1, ?, ?, ?)
        ON CONFLICT(update_id) DO UPDATE SET
          failure_count = onboarding_update_failures.failure_count + 1,
          last_failed_at = excluded.last_failed_at,
          last_error = excluded.last_error
        """,
        (update_id, now_iso, now_iso, error),
    )
    conn.commit()
    return get_onboarding_update_failure(conn, update_id) or {}


def clear_onboarding_update_failure(conn: sqlite3.Connection, update_id: str) -> None:
    conn.execute(
        "DELETE FROM onboarding_update_failures WHERE update_id = ?",
        (update_id,),
    )
    conn.commit()


def mark_onboarding_update_skipped(conn: sqlite3.Connection, update_id: str) -> dict[str, Any]:
    conn.execute(
        """
        UPDATE onboarding_update_failures
        SET skipped_at = COALESCE(skipped_at, ?)
        WHERE update_id = ?
        """,
        (utc_now_iso(), update_id),
    )
    conn.commit()
    return get_onboarding_update_failure(conn, update_id) or {}


def make_agent_id(unix_user: str, role: str) -> str:
    prefix = "curator" if role == "curator" else "agent"
    return f"{prefix}-{safe_slug(unix_user)}"


def is_loopback_ip(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def is_tailnet_ip(value: str) -> bool:
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        return False
    if parsed.version == 4:
        return parsed in ipaddress.ip_network("100.64.0.0/10")
    return parsed in ipaddress.ip_network("fd7a:115c:a1e0::/48")


def parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        return value[1:-1]
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return value


def parse_vault_definition(definition_path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_list_key: str | None = None
    # block scalar state: when a value was introduced with `|` or `>`, subsequent
    # lines indented past the current threshold are consumed as part of the scalar.
    block_key: str | None = None
    block_style: str = ""  # "|" literal or ">" folded
    block_indent: int | None = None
    block_lines: list[str] = []

    def _flush_block() -> None:
        nonlocal block_key, block_style, block_indent, block_lines
        if block_key is None:
            return
        if block_style == "|":
            data[block_key] = "\n".join(block_lines).rstrip("\n")
        else:  # ">" folded
            folded: list[str] = []
            buffer: list[str] = []
            for line in block_lines:
                if line.strip() == "":
                    if buffer:
                        folded.append(" ".join(buffer))
                        buffer = []
                    folded.append("")
                else:
                    buffer.append(line.strip())
            if buffer:
                folded.append(" ".join(buffer))
            data[block_key] = "\n".join(folded).strip("\n")
        block_key = None
        block_style = ""
        block_indent = None
        block_lines = []

    lines = definition_path.read_text(encoding="utf-8").splitlines()
    for lineno, raw_line in enumerate(lines, start=1):
        indent = len(raw_line) - len(raw_line.lstrip(" "))

        if block_key is not None:
            if raw_line.strip() == "":
                block_lines.append("")
                continue
            if block_indent is None:
                block_indent = max(indent, 1)
            if indent >= block_indent:
                block_lines.append(raw_line[block_indent:] if indent >= block_indent else raw_line.lstrip())
                continue
            _flush_block()

        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        stripped = raw_line.strip()
        if stripped.startswith("- "):
            if current_list_key is None or indent == 0:
                raise ValueError(f"{definition_path}:{lineno}: list item without a parent key")
            data.setdefault(current_list_key, []).append(str(parse_scalar(stripped[2:])))
            continue

        current_list_key = None
        if ":" not in stripped:
            raise ValueError(f"{definition_path}:{lineno}: expected 'key: value'")

        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()

        if raw_value in ("|", ">"):
            block_key = key
            block_style = raw_value
            block_indent = None
            block_lines = []
            continue

        if not raw_value:
            current_list_key = key
            data[key] = []
            continue

        data[key] = parse_scalar(raw_value)

    _flush_block()

    required = {"name", "description", "owner", "default_subscribed"}
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"{definition_path}: missing required key(s): {', '.join(missing)}")
    if not isinstance(data["default_subscribed"], bool):
        raise ValueError(f"{definition_path}: default_subscribed must be true or false")
    if "tags" in data and not isinstance(data["tags"], list):
        raise ValueError(f"{definition_path}: tags must be a YAML list")
    data.setdefault("tags", [])
    return data


def _top_level_missing_vault_warnings(vault_root: Path) -> list[str]:
    warnings: list[str] = []
    if not vault_root.exists():
        return warnings
    for child in sorted(vault_root.iterdir()):
        if child.name.startswith(".") or child.is_symlink() or not child.is_dir():
            continue
        if (child / ".vault").exists():
            continue
        if any(grand.name.startswith(".") for grand in child.iterdir() if grand.exists()):
            pass
        warnings.append(f"top-level vault directory is missing .vault: {child}")
    return warnings


def scan_vault_definitions(cfg: Config) -> dict[str, Any]:
    definitions: list[dict[str, Any]] = []
    active_roots: list[Path] = []
    active_vaults: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen_names: set[str] = set()
    vault_root = cfg.vault_dir

    if not vault_root.exists():
        return {
            "definitions": [],
            "active_vaults": [],
            "warnings": [f"vault root does not exist: {vault_root}"],
        }

    warnings.extend(_top_level_missing_vault_warnings(vault_root))

    for root, dirs, files in os.walk(vault_root, topdown=True, followlinks=False):
        root_path = Path(root)
        dirs[:] = [
            name
            for name in dirs
            if not name.startswith(".") and not (root_path / name).is_symlink()
        ]
        if ".vault" not in files:
            continue

        definition_path = root_path / ".vault"
        discovered_at = utc_now_iso()

        nested_parent = next((parent for parent in active_roots if parent in root_path.parents), None)
        if nested_parent is not None:
            warning = f"nested .vault is invalid in v1: {definition_path} sits under {nested_parent}"
            warnings.append(warning)
            definitions.append(
                {
                    "definition_path": str(definition_path),
                    "vault_name": root_path.name,
                    "vault_path": str(root_path),
                    "owner": "",
                    "description": "",
                    "default_subscribed": 0,
                    "tags_json": "[]",
                    "category": None,
                    "brief_template": None,
                    "is_valid": 0,
                    "warning": warning,
                    "discovered_at": discovered_at,
                }
            )
            continue

        try:
            parsed = parse_vault_definition(definition_path)
            name = str(parsed["name"]).strip()
            if name in seen_names:
                raise ValueError(f"{definition_path}: duplicate vault name '{name}'")
            seen_names.add(name)
            active_roots.append(root_path)
            row = {
                "definition_path": str(definition_path),
                "vault_name": name,
                "vault_path": str(root_path),
                "owner": str(parsed["owner"]).strip(),
                "description": str(parsed["description"]).strip(),
                "default_subscribed": 1 if parsed["default_subscribed"] else 0,
                "tags_json": json_dumps(parsed.get("tags", [])),
                "category": str(parsed["category"]).strip() if parsed.get("category") else None,
                "brief_template": str(parsed["brief_template"]).strip() if parsed.get("brief_template") else None,
                "is_valid": 1,
                "warning": None,
                "discovered_at": discovered_at,
            }
            definitions.append(row)
            active_vaults.append(row)
        except Exception as exc:  # noqa: BLE001
            warning = str(exc)
            warnings.append(warning)
            definitions.append(
                {
                    "definition_path": str(definition_path),
                    "vault_name": root_path.name,
                    "vault_path": str(root_path),
                    "owner": "",
                    "description": "",
                    "default_subscribed": 0,
                    "tags_json": "[]",
                    "category": None,
                    "brief_template": None,
                    "is_valid": 0,
                    "warning": warning,
                    "discovered_at": discovered_at,
                }
            )

    return {
        "definitions": definitions,
        "active_vaults": active_vaults,
        "warnings": warnings,
    }


def reload_vault_definitions(conn: sqlite3.Connection, cfg: Config) -> dict[str, Any]:
    """Rescan `.vault` files. On catalog changes (new/removed vaults, new warnings),
    fan out default subscriptions to active user agents and queue an operator
    alert + curator brief-fanout signal."""
    prior_active = {
        row["vault_name"]: dict(row)
        for row in conn.execute(
            "SELECT vault_name, vault_path, owner, default_subscribed FROM vaults"
        ).fetchall()
    }
    prior_warnings = set(list_vault_warnings(conn))

    scan = scan_vault_definitions(cfg)
    now_iso = utc_now_iso()

    conn.execute("DELETE FROM vault_definitions")
    conn.execute("DELETE FROM vaults")
    for definition in scan["definitions"]:
        conn.execute(
            """
            INSERT INTO vault_definitions (
              definition_path, vault_name, vault_path, owner, description,
              default_subscribed, tags_json, category, brief_template,
              is_valid, warning, discovered_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                definition["definition_path"],
                definition["vault_name"],
                definition["vault_path"],
                definition["owner"],
                definition["description"],
                definition["default_subscribed"],
                definition["tags_json"],
                definition["category"],
                definition["brief_template"],
                definition["is_valid"],
                definition["warning"],
                definition["discovered_at"],
            ),
        )
    for vault in scan["active_vaults"]:
        conn.execute(
            """
            INSERT INTO vaults (vault_name, vault_path, state, warning, owner, default_subscribed, updated_at)
            VALUES (?, ?, 'active', NULL, ?, ?, ?)
            """,
            (
                vault["vault_name"],
                vault["vault_path"],
                vault["owner"],
                vault["default_subscribed"],
                now_iso,
            ),
        )
    conn.commit()

    active_names = {v["vault_name"] for v in scan["active_vaults"]}
    prior_names = set(prior_active)
    added = sorted(active_names - prior_names)
    removed = sorted(prior_names - active_names)
    default_changed = sorted(
        v["vault_name"]
        for v in scan["active_vaults"]
        if v["vault_name"] in prior_names
        and int(prior_active[v["vault_name"]]["default_subscribed"]) != int(v["default_subscribed"])
    )
    new_warnings = sorted(set(scan["warnings"]) - prior_warnings)

    fanout_summary: dict[str, int] = {"default_subscribed_added": 0, "agents_notified": 0}
    if added or default_changed:
        fanout_summary = _fanout_default_subscriptions(conn, cfg, vault_names=set(added) | set(default_changed))

    if added or removed or new_warnings:
        bits: list[str] = []
        if added:
            bits.append(f"added={','.join(added)}")
        if removed:
            bits.append(f"removed={','.join(removed)}")
        if new_warnings:
            bits.append(f"warnings={len(new_warnings)}")
        queue_notification(
            conn,
            target_kind="operator",
            target_id=cfg.operator_notify_channel_id or cfg.operator_notify_platform or "operator",
            channel_kind=cfg.operator_notify_platform or "tui-only",
            message="Vault catalog changed: " + "; ".join(bits),
        )
        queue_notification(
            conn,
            target_kind="curator",
            target_id="curator",
            channel_kind="brief-fanout",
            message=f"catalog-reload: added={len(added)} removed={len(removed)} warnings={len(new_warnings)}",
        )

    scan["diff"] = {
        "added": added,
        "removed": removed,
        "default_subscribed_changed": default_changed,
        "new_warnings": new_warnings,
    }
    scan["fanout"] = fanout_summary
    return scan


def _fanout_default_subscriptions(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    vault_names: set[str],
) -> dict[str, int]:
    """For each active user agent, ensure it has a subscription row for every
    vault in `vault_names` where default_subscribed=1. Never overrides an
    existing opt-out — only adds missing rows."""
    rows = conn.execute(
        "SELECT vault_name, default_subscribed FROM vaults WHERE vault_name IN ({})".format(
            ",".join(["?"] * len(vault_names)) or "NULL"
        ),
        tuple(vault_names),
    ).fetchall() if vault_names else []
    applicable = {r["vault_name"]: int(r["default_subscribed"]) for r in rows}
    if not applicable:
        return {"default_subscribed_added": 0, "agents_notified": 0}

    agents = conn.execute(
        "SELECT agent_id FROM agents WHERE role = 'user' AND status = 'active'"
    ).fetchall()
    now_iso = utc_now_iso()
    added_count = 0
    notified: set[str] = set()

    for agent in agents:
        agent_id = str(agent["agent_id"])
        for vault_name, default_subscribed in applicable.items():
            existing = conn.execute(
                "SELECT subscribed FROM agent_vault_subscriptions WHERE agent_id = ? AND vault_name = ?",
                (agent_id, vault_name),
            ).fetchone()
            if existing is not None:
                # respect prior opt-in/opt-out
                continue
            if default_subscribed != 1:
                continue
            conn.execute(
                """
                INSERT INTO agent_vault_subscriptions (agent_id, vault_name, subscribed, source, updated_at)
                VALUES (?, ?, 1, 'default-fanout', ?)
                """,
                (agent_id, vault_name, now_iso),
            )
            added_count += 1
            notified.add(agent_id)

    for agent_id in notified:
        queue_notification(
            conn,
            target_kind="curator",
            target_id=agent_id,
            channel_kind="brief-fanout",
            message=f"default-fanout: new vault(s) applied to {agent_id}",
        )

    conn.commit()
    return {
        "default_subscribed_added": added_count,
        "agents_notified": len(notified),
    }


def list_vaults(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT v.vault_name, v.vault_path, v.state, v.warning, v.owner,
               v.default_subscribed, d.description, d.tags_json, d.category, d.brief_template
        FROM vaults v
        LEFT JOIN vault_definitions d ON d.vault_name = v.vault_name AND d.is_valid = 1
        ORDER BY v.vault_name
        """
    ).fetchall()
    return [dict(row) for row in rows]


def list_vault_warnings(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT warning
        FROM vault_definitions
        WHERE is_valid = 0 AND warning IS NOT NULL
        ORDER BY definition_path
        """
    ).fetchall()
    return [str(row["warning"]) for row in rows]


def queue_notification(
    conn: sqlite3.Connection,
    *,
    target_kind: str,
    target_id: str,
    channel_kind: str,
    message: str,
    extra: dict[str, Any] | None = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO notification_outbox (target_kind, target_id, channel_kind, message, extra_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (target_kind, target_id, channel_kind, message, json_dumps(extra or {}), utc_now_iso()),
    )
    conn.commit()
    return int(cursor.lastrowid)


def _operator_action_row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def get_active_operator_action(
    conn: sqlite3.Connection,
    *,
    action_kind: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM operator_actions
        WHERE action_kind = ?
          AND status IN ('pending', 'running')
        ORDER BY id DESC
        LIMIT 1
        """,
        (str(action_kind or "").strip(),),
    ).fetchone()
    return _operator_action_row_to_dict(row)


def get_pending_operator_action(
    conn: sqlite3.Connection,
    *,
    action_kind: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM operator_actions
        WHERE action_kind = ?
          AND status = 'pending'
        ORDER BY id ASC
        LIMIT 1
        """,
        (str(action_kind or "").strip(),),
    ).fetchone()
    return _operator_action_row_to_dict(row)


def request_operator_action(
    conn: sqlite3.Connection,
    *,
    action_kind: str,
    requested_by: str,
    request_source: str = "",
    requested_target: str = "",
) -> tuple[dict[str, Any], bool]:
    normalized_kind = str(action_kind or "").strip().lower()
    if not normalized_kind:
        raise ValueError("action_kind is required")
    active = get_active_operator_action(conn, action_kind=normalized_kind)
    if active is not None:
        return active, False
    now_iso = utc_now_iso()
    cursor = conn.execute(
        """
        INSERT INTO operator_actions (
          action_kind, requested_target, requested_by, request_source, status, note, created_at
        ) VALUES (?, ?, ?, ?, 'pending', '', ?)
        """,
        (
            normalized_kind,
            str(requested_target or "").strip(),
            str(requested_by or "").strip() or "operator",
            str(request_source or "").strip(),
            now_iso,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM operator_actions WHERE id = ?", (int(cursor.lastrowid),)).fetchone()
    return _operator_action_row_to_dict(row) or {}, True


def mark_operator_action_running(
    conn: sqlite3.Connection,
    *,
    action_id: int,
    note: str = "",
    log_path: str = "",
) -> dict[str, Any]:
    now_iso = utc_now_iso()
    conn.execute(
        """
        UPDATE operator_actions
        SET status = 'running',
            started_at = ?,
            note = ?,
            log_path = ?
        WHERE id = ?
        """,
        (now_iso, str(note or ""), str(log_path or ""), int(action_id)),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM operator_actions WHERE id = ?", (int(action_id),)).fetchone()
    return _operator_action_row_to_dict(row) or {}


def finish_operator_action(
    conn: sqlite3.Connection,
    *,
    action_id: int,
    status: str,
    note: str = "",
    log_path: str = "",
) -> dict[str, Any]:
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in {"completed", "failed", "dismissed"}:
        raise ValueError(f"unsupported operator action status: {status}")
    now_iso = utc_now_iso()
    conn.execute(
        """
        UPDATE operator_actions
        SET status = ?,
            note = ?,
            finished_at = ?,
            log_path = CASE WHEN ? != '' THEN ? ELSE log_path END
        WHERE id = ?
        """,
        (
            normalized_status,
            str(note or ""),
            now_iso,
            str(log_path or ""),
            str(log_path or ""),
            int(action_id),
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM operator_actions WHERE id = ?", (int(action_id),)).fetchone()
    return _operator_action_row_to_dict(row) or {}


def subscribed_agent_ids_for_vault(conn: sqlite3.Connection, vault_name: str) -> list[str]:
    vault = conn.execute(
        "SELECT default_subscribed FROM vaults WHERE vault_name = ? AND state = 'active'",
        (vault_name,),
    ).fetchone()
    if vault is None:
        return []
    default_subscribed = int(vault["default_subscribed"] or 0)
    rows = conn.execute(
        """
        SELECT a.agent_id, s.subscribed
        FROM agents a
        LEFT JOIN agent_vault_subscriptions s
          ON s.agent_id = a.agent_id AND s.vault_name = ?
        WHERE a.role = 'user' AND a.status = 'active'
        ORDER BY a.agent_id
        """,
        (vault_name,),
    ).fetchall()
    result: list[str] = []
    for row in rows:
        explicit = row["subscribed"]
        if explicit is None:
            if default_subscribed == 1:
                result.append(str(row["agent_id"]))
            continue
        if int(explicit) == 1:
            result.append(str(row["agent_id"]))
    return result


def _changed_paths_by_vault(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    changed_paths: Sequence[str],
) -> dict[str, list[str]]:
    active_vaults = [
        (str(row["vault_name"]), Path(str(row["vault_path"])).expanduser().resolve(strict=False))
        for row in conn.execute(
            "SELECT vault_name, vault_path FROM vaults WHERE state = 'active' ORDER BY LENGTH(vault_path) DESC"
        ).fetchall()
    ]
    grouped: dict[str, set[str]] = {}
    for raw_path in changed_paths:
        if not raw_path:
            continue
        path = Path(str(raw_path)).expanduser()
        if not path.is_absolute():
            path = cfg.vault_dir / path
        path = path.resolve(strict=False)
        for vault_name, vault_root in active_vaults:
            if path == vault_root or path.is_relative_to(vault_root):
                try:
                    rel_path = str(path.relative_to(vault_root))
                except ValueError:
                    rel_path = path.name
                grouped.setdefault(vault_name, set()).add(rel_path or ".")
                break
    return {vault_name: sorted(paths) for vault_name, paths in grouped.items()}


def queue_vault_content_notifications(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    changed_paths: Sequence[str],
    source: str = "vault-watch",
) -> dict[str, Any]:
    changed_by_vault = _changed_paths_by_vault(conn, cfg, changed_paths=changed_paths)
    queued_notifications = 0
    agents_notified: set[str] = set()
    activation_triggers: dict[str, str] = {}
    brief_fanout_queued = False

    for vault_name, relative_paths in changed_by_vault.items():
        subscribers = subscribed_agent_ids_for_vault(conn, vault_name)
        if not subscribers:
            continue
        preview = ", ".join(relative_paths[:3])
        if len(relative_paths) > 3:
            preview += f" ... (+{len(relative_paths) - 3} more)"
        message = f"Vault content changed: {vault_name} ({len(relative_paths)} path(s)): {preview}"
        for agent_id in subscribers:
            queue_notification(
                conn,
                target_kind="user-agent",
                target_id=agent_id,
                channel_kind="vault-change",
                message=message,
                extra={"vault_name": vault_name, "paths": relative_paths, "source": source},
            )
            queued_notifications += 1
            agents_notified.add(agent_id)
        note_refresh_job(
            conn,
            job_name=f"vault-notify-{vault_name}",
            job_kind="vault-notify",
            target_id=vault_name,
            schedule=source,
            status="ok",
            note=f"queued {len(subscribers)} notification(s) for {len(relative_paths)} changed path(s)",
        )

    for agent_id in sorted(agents_notified):
        trigger_path = signal_agent_refresh_from_curator(
            conn,
            cfg,
            agent_id=agent_id,
            note=f"{source}: vault content notifications ready",
        )
        if trigger_path is not None:
            activation_triggers[agent_id] = str(trigger_path)

    if changed_by_vault:
        summary = ", ".join(
            f"{vault_name}({len(relative_paths)} path(s))"
            for vault_name, relative_paths in sorted(changed_by_vault.items())
        )
        queue_notification(
            conn,
            target_kind="curator",
            target_id="curator",
            channel_kind="brief-fanout",
            message=(
                "vault-content-refresh: "
                f"{summary}. Refresh managed-memory stubs for org-wide vault awareness."
            ),
        )
        brief_fanout_queued = True

    return {
        "vaults_changed": sorted(changed_by_vault),
        "paths_by_vault": changed_by_vault,
        "queued_notifications": queued_notifications,
        "agents_notified": sorted(agents_notified),
        "activation_triggers": activation_triggers,
        "brief_fanout_queued": brief_fanout_queued,
    }


def _repo_sync_state_dir(cfg: Config) -> Path:
    return cfg.state_dir / "repo-sync"


def _repo_sync_checkout_root(cfg: Config) -> Path:
    return _repo_sync_state_dir(cfg) / "checkouts"


def _repo_sync_mirror_root(cfg: Config) -> Path:
    return cfg.vault_dir / "Repos" / "_mirrors"


def _repo_sync_remote_priority(remote_url: str) -> int:
    if remote_url.startswith("git@github.com:"):
        return 3
    if remote_url.startswith("ssh://git@github.com/"):
        return 2
    if remote_url.startswith("https://github.com/"):
        return 1
    return 0


def _repo_sync_slug_from_url(canonical_url: str) -> str:
    suffix = canonical_url.split("github.com/", 1)[-1].strip("/")
    if "/" in suffix:
        owner, repo = suffix.split("/", 1)
        return safe_slug(f"{owner}-{repo}", fallback="repo-sync")
    return safe_slug(suffix, fallback="repo-sync")


def _repo_sync_remote_url(raw_value: str, owner: str, repo: str) -> str:
    raw = str(raw_value or "").strip()
    if raw.startswith("git@github.com:"):
        return f"git@github.com:{owner}/{repo}.git"
    if raw.startswith("ssh://git@github.com/"):
        return f"ssh://git@github.com/{owner}/{repo}.git"
    return f"https://github.com/{owner}/{repo}.git"


def _repo_sync_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _repo_sync_github_remote(remote_value: str) -> tuple[str, str] | None:
    remote = str(remote_value or "").strip()
    if not remote:
        return None
    match = REPO_SYNC_GITHUB_PATTERN.search(remote)
    if match is None:
        return None
    owner = match.group("owner")
    repo = match.group("repo")
    canonical_url = f"https://github.com/{owner}/{repo}"
    remote_url = _repo_sync_remote_url(remote, owner, repo)
    return canonical_url, remote_url


def _repo_sync_local_repo_remote(root_path: Path) -> tuple[str, str] | None:
    if not (root_path / ".git").exists():
        return None
    try:
        remote = _repo_sync_git("remote", "get-url", "origin", cwd=root_path).stdout.strip()
    except RuntimeError:
        return None
    return _repo_sync_github_remote(remote)


def discover_vault_repo_sources(cfg: Config) -> list[dict[str, Any]]:
    discovered: dict[str, dict[str, Any]] = {}
    vault_root = cfg.vault_dir
    if not vault_root.exists():
        return []

    for root, dirs, files in os.walk(vault_root, topdown=True, followlinks=False):
        root_path = Path(root)
        try:
            rel_parts = root_path.relative_to(vault_root).parts
        except ValueError:
            rel_parts = ()
        if rel_parts[:2] == ("Repos", "_mirrors"):
            dirs[:] = []
            continue

        local_repo = _repo_sync_local_repo_remote(root_path)
        if local_repo is not None:
            canonical_url, remote_url = local_repo
            entry = discovered.setdefault(
                canonical_url,
                {
                    "slug": _repo_sync_slug_from_url(canonical_url),
                    "canonical_url": canonical_url,
                    "remote_url": remote_url,
                    "source_paths": set(),
                    "local_repo_paths": set(),
                },
            )
            if _repo_sync_remote_priority(remote_url) > _repo_sync_remote_priority(str(entry.get("remote_url") or "")):
                entry["remote_url"] = remote_url
            local_paths = entry.setdefault("local_repo_paths", set())
            if isinstance(local_paths, set):
                local_paths.add(str(root_path))

        dirs[:] = [
            name
            for name in dirs
            if not name.startswith(".") and not (root_path / name).is_symlink()
        ]
        for name in files:
            if name == ".vault" or name.startswith("."):
                continue
            path = root_path / name
            if path.suffix.lower() not in REPO_SYNC_SOURCE_SUFFIXES:
                continue
            try:
                text = _repo_sync_read_text(path)
            except OSError:
                continue
            if REPO_SYNC_MANAGED_MARKER in "\n".join(text.splitlines()[:3]):
                continue
            for match in REPO_SYNC_GITHUB_PATTERN.finditer(text):
                owner = match.group("owner")
                repo = match.group("repo")
                canonical_url = f"https://github.com/{owner}/{repo}"
                remote_url = _repo_sync_remote_url(match.group("raw") or canonical_url, owner, repo)
                entry = discovered.setdefault(
                    canonical_url,
                    {
                        "slug": _repo_sync_slug_from_url(canonical_url),
                        "canonical_url": canonical_url,
                        "remote_url": remote_url,
                        "source_paths": set(),
                        "local_repo_paths": set(),
                    },
                )
                if _repo_sync_remote_priority(remote_url) > _repo_sync_remote_priority(str(entry.get("remote_url") or "")):
                    entry["remote_url"] = remote_url
                cast_source_paths = entry.setdefault("source_paths", set())
                if isinstance(cast_source_paths, set):
                    cast_source_paths.add(str(path))

    results: list[dict[str, Any]] = []
    for canonical_url in sorted(discovered):
        entry = discovered[canonical_url]
        results.append(
            {
                "slug": str(entry["slug"]),
                "canonical_url": str(entry["canonical_url"]),
                "remote_url": str(entry["remote_url"]),
                "source_paths": sorted(str(p) for p in entry.get("source_paths", set())),
                "local_repo_paths": sorted(str(p) for p in entry.get("local_repo_paths", set())),
            }
        )
    return results


def _repo_sync_git(*args: str, cwd: Path | None = None, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    if shutil.which("git") is None:
        raise RuntimeError("git is not installed")
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(detail or f"git {' '.join(args)} exited {result.returncode}")
    return result


def _repo_sync_current_branch(checkout_dir: Path) -> str:
    branch = _repo_sync_git("rev-parse", "--abbrev-ref", "HEAD", cwd=checkout_dir).stdout.strip()
    if branch and branch != "HEAD":
        return branch
    try:
        origin_head = _repo_sync_git("symbolic-ref", "refs/remotes/origin/HEAD", cwd=checkout_dir).stdout.strip()
    except RuntimeError:
        return ""
    return origin_head.rsplit("/", 1)[-1].strip()


def _repo_sync_pull_local_repo(repo_dir: Path, remote_url: str) -> dict[str, Any]:
    status = _repo_sync_git("status", "--porcelain", cwd=repo_dir).stdout.strip()
    if status:
        raise RuntimeError(f"local repo has uncommitted changes at {repo_dir}")
    branch = _repo_sync_current_branch(repo_dir)
    if not branch:
        raise RuntimeError(f"local repo has no active branch at {repo_dir}")
    before_commit = _repo_sync_git("rev-parse", "HEAD", cwd=repo_dir).stdout.strip()
    _repo_sync_git("fetch", "--prune", remote_url, branch, cwd=repo_dir, timeout=300)
    diff_output = _repo_sync_git("diff", "--name-only", "HEAD..FETCH_HEAD", cwd=repo_dir, timeout=300).stdout
    changed_rel_paths = [line.strip() for line in diff_output.splitlines() if line.strip()]
    if changed_rel_paths:
        _repo_sync_git("merge", "--ff-only", "FETCH_HEAD", cwd=repo_dir, timeout=300)
    after_commit = _repo_sync_git("rev-parse", "HEAD", cwd=repo_dir).stdout.strip()
    return {
        "branch": branch,
        "before_commit": before_commit,
        "commit": after_commit,
        "changed_paths": [str((repo_dir / rel_path).resolve(strict=False)) for rel_path in changed_rel_paths],
        "changed_count": len(changed_rel_paths),
    }


def _repo_sync_checkout(checkout_dir: Path, remote_url: str) -> dict[str, str]:
    checkout_dir.parent.mkdir(parents=True, exist_ok=True)
    if (checkout_dir / ".git").is_dir():
        current_remote = ""
        try:
            current_remote = _repo_sync_git("remote", "get-url", "origin", cwd=checkout_dir).stdout.strip()
        except RuntimeError:
            current_remote = ""
        if current_remote != remote_url:
            _repo_sync_git("remote", "remove", "origin", cwd=checkout_dir)
            _repo_sync_git("remote", "add", "origin", remote_url, cwd=checkout_dir)
        _repo_sync_git("fetch", "--prune", "origin", cwd=checkout_dir, timeout=300)
        branch = _repo_sync_current_branch(checkout_dir)
        if branch:
            _repo_sync_git("checkout", "-B", branch, f"origin/{branch}", cwd=checkout_dir, timeout=300)
        else:
            _repo_sync_git("reset", "--hard", "FETCH_HEAD", cwd=checkout_dir, timeout=300)
        _repo_sync_git("clean", "-fd", cwd=checkout_dir, timeout=300)
    else:
        if checkout_dir.exists():
            shutil.rmtree(checkout_dir)
        _repo_sync_git("clone", "--depth", "1", remote_url, str(checkout_dir), timeout=300)
    branch = _repo_sync_current_branch(checkout_dir)
    commit = _repo_sync_git("rev-parse", "HEAD", cwd=checkout_dir).stdout.strip()
    return {"branch": branch, "commit": commit}


def _repo_sync_collect_export_files(checkout_dir: Path) -> dict[str, str]:
    exported: dict[str, str] = {}
    for root, dirs, files in os.walk(checkout_dir, topdown=True, followlinks=False):
        root_path = Path(root)
        dirs[:] = [
            name
            for name in dirs
            if name not in REPO_SYNC_EXCLUDED_DIR_NAMES and not name.startswith(".")
        ]
        for name in files:
            if name.startswith("."):
                continue
            path = root_path / name
            if path.suffix.lower() not in REPO_SYNC_SOURCE_SUFFIXES:
                continue
            try:
                if path.stat().st_size > 1024 * 1024:
                    continue
            except OSError:
                continue
            rel_path = path.relative_to(checkout_dir).as_posix()
            try:
                exported[rel_path] = _repo_sync_read_text(path)
            except OSError:
                continue
    return exported


def _repo_sync_status_note(
    *,
    canonical_url: str,
    remote_url: str,
    branch: str,
    commit: str,
    source_paths: Sequence[str],
    exported_file_count: int,
) -> str:
    lines = [
        REPO_SYNC_MANAGED_MARKER,
        "# Repo sync status",
        "",
        f"Repository URL: {canonical_url}",
        f"Remote URL: {remote_url}",
        f"Branch: {branch or '(detached)'}",
        f"Commit: `{commit}`",
        f"Exported text files: {exported_file_count}",
        f"Last synced at: {utc_now_iso()}",
        "",
        "This directory is managed by Almanac's GitHub repo sync rail.",
        "Human-owned source note(s):",
    ]
    for source_path in source_paths:
        lines.append(f"- `{source_path}`")
    lines.extend(
        [
            "",
            "Only markdown/text files are mirrored here so qmd can index them through the existing vault-watch rail.",
            "Do not hand-edit files in this mirror; the next sync overwrites managed content.",
            "",
        ]
    )
    return "\n".join(lines)


def _repo_sync_apply_tree(target_dir: Path, desired_files: dict[str, str]) -> dict[str, Any]:
    changed_paths: list[str] = []
    created = 0
    updated = 0
    removed = 0
    existing_files: dict[str, Path] = {}
    if target_dir.exists():
        for path in sorted(target_dir.rglob("*")):
            if path.is_file():
                existing_files[path.relative_to(target_dir).as_posix()] = path

    for rel_path, content in sorted(desired_files.items()):
        path = target_dir / rel_path
        existing_path = existing_files.get(rel_path)
        current = None
        if existing_path is not None and existing_path.is_file():
            try:
                current = _repo_sync_read_text(existing_path)
            except OSError:
                current = None
        if current == content:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        changed_paths.append(str(path))
        if existing_path is None:
            created += 1
        else:
            updated += 1

    for rel_path, path in sorted(existing_files.items()):
        if rel_path in desired_files:
            continue
        try:
            path.unlink()
            changed_paths.append(str(path))
            removed += 1
        except FileNotFoundError:
            continue

    if target_dir.exists():
        for path in sorted(target_dir.rglob("*"), reverse=True):
            if path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    continue
    return {
        "changed_paths": changed_paths,
        "created": created,
        "updated": updated,
        "removed": removed,
    }


def _repo_sync_remove_tree(path: Path) -> list[str]:
    if not path.exists():
        return []
    changed_paths = [str(file_path) for file_path in sorted(path.rglob("*")) if file_path.is_file()]
    shutil.rmtree(path)
    return changed_paths


def sync_vault_repo_mirrors(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    repo_sources: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    raw_sources = discover_vault_repo_sources(cfg) if repo_sources is None else list(repo_sources)
    merged_sources: dict[str, dict[str, Any]] = {}
    for raw_source in raw_sources:
        canonical_url = str(raw_source.get("canonical_url") or "").strip()
        if not canonical_url:
            continue
        slug = str(raw_source.get("slug") or _repo_sync_slug_from_url(canonical_url)).strip() or _repo_sync_slug_from_url(canonical_url)
        remote_url = str(raw_source.get("remote_url") or f"{canonical_url}.git").strip()
        source_paths = {
            str(path).strip()
            for path in raw_source.get("source_paths") or []
            if str(path).strip()
        }
        local_repo_paths = {
            str(path).strip()
            for path in raw_source.get("local_repo_paths") or []
            if str(path).strip()
        }
        entry = merged_sources.setdefault(
            canonical_url,
            {
                "slug": slug,
                "canonical_url": canonical_url,
                "remote_url": remote_url,
                "source_paths": set(),
                "local_repo_paths": set(),
            },
        )
        if _repo_sync_remote_priority(remote_url) > _repo_sync_remote_priority(str(entry.get("remote_url") or "")):
            entry["remote_url"] = remote_url
        cast_source_paths = entry.setdefault("source_paths", set())
        if isinstance(cast_source_paths, set):
            cast_source_paths.update(source_paths)
        cast_local_repo_paths = entry.setdefault("local_repo_paths", set())
        if isinstance(cast_local_repo_paths, set):
            cast_local_repo_paths.update(local_repo_paths)

    state_dir = _repo_sync_state_dir(cfg)
    checkout_root = _repo_sync_checkout_root(cfg)
    mirror_root = _repo_sync_mirror_root(cfg)
    state_dir.mkdir(parents=True, exist_ok=True)
    checkout_root.mkdir(parents=True, exist_ok=True)

    normalized_sources = [
        {
            "slug": str(entry["slug"]),
            "canonical_url": canonical_url,
            "remote_url": str(entry["remote_url"]),
            "source_paths": sorted(str(path) for path in entry.get("source_paths", set())),
            "local_repo_paths": sorted(str(path) for path in entry.get("local_repo_paths", set())),
        }
        for canonical_url, entry in sorted(merged_sources.items())
    ]

    summary: dict[str, Any] = {
        "repos_total": len(normalized_sources),
        "repos_synced": [],
        "repos_failed": [],
        "changed_paths": [],
        "repo_statuses": [],
    }

    repos_vault_dir = cfg.vault_dir / "Repos"
    requires_mirror_vault = any(not source.get("local_repo_paths") for source in normalized_sources)
    if requires_mirror_vault and not (repos_vault_dir / ".vault").is_file():
        summary["repos_failed"].append("Repos vault is missing .vault metadata; refusing to create managed mirrors")
        note_refresh_job(
            conn,
            job_name="vault-github-sync",
            job_kind="vault-github-sync",
            target_id="Repos",
            schedule="every 1h via curator-refresh",
            status="warn",
            note="repos=0 synced=0 changed_paths=0 failures=1 (Repos vault missing .vault)",
        )
        return summary

    mirror_root.mkdir(parents=True, exist_ok=True)
    active_slugs = {str(source["slug"]) for source in normalized_sources if not source.get("local_repo_paths")}

    for source in normalized_sources:
        slug = str(source["slug"])
        checkout_dir = checkout_root / slug
        mirror_dir = mirror_root / slug
        try:
            if source.get("local_repo_paths"):
                local_results = []
                for repo_path in source["local_repo_paths"]:
                    local_result = _repo_sync_pull_local_repo(Path(repo_path), str(source["remote_url"]))
                    local_results.append({"path": repo_path, **local_result})
                    summary["changed_paths"].extend(local_result["changed_paths"])
                summary["repos_synced"].append(slug)
                summary["repo_statuses"].append(
                    {
                        "slug": slug,
                        "canonical_url": str(source["canonical_url"]),
                        "remote_url": str(source["remote_url"]),
                        "source_paths": list(source["source_paths"]),
                        "local_repo_paths": list(source["local_repo_paths"]),
                        "mode": "in-place",
                        "syncs": local_results,
                    }
                )
                continue

            checkout = _repo_sync_checkout(checkout_dir, str(source["remote_url"]))
            desired_files = _repo_sync_collect_export_files(checkout_dir)
            desired_files[REPO_SYNC_STATUS_FILENAME] = _repo_sync_status_note(
                canonical_url=str(source["canonical_url"]),
                remote_url=str(source["remote_url"]),
                branch=str(checkout.get("branch") or ""),
                commit=str(checkout.get("commit") or ""),
                source_paths=source["source_paths"],
                exported_file_count=len(desired_files),
            )
            applied = _repo_sync_apply_tree(mirror_dir, desired_files)
            summary["changed_paths"].extend(applied["changed_paths"])
            summary["repos_synced"].append(slug)
            summary["repo_statuses"].append(
                {
                    "slug": slug,
                    "canonical_url": str(source["canonical_url"]),
                    "remote_url": str(source["remote_url"]),
                    "branch": str(checkout.get("branch") or ""),
                    "commit": str(checkout.get("commit") or ""),
                    "source_paths": list(source["source_paths"]),
                    "local_repo_paths": list(source["local_repo_paths"]),
                    "mode": "mirror",
                    "created": int(applied["created"]),
                    "updated": int(applied["updated"]),
                    "removed": int(applied["removed"]),
                }
            )
        except Exception as exc:  # noqa: BLE001
            summary["repos_failed"].append(f"{slug}:{exc}")
            summary["repo_statuses"].append(
                {
                    "slug": slug,
                    "canonical_url": str(source["canonical_url"]),
                    "remote_url": str(source["remote_url"]),
                    "source_paths": list(source["source_paths"]),
                    "local_repo_paths": list(source["local_repo_paths"]),
                    "error": str(exc),
                }
            )

    if mirror_root.exists():
        for stale_dir in sorted(path for path in mirror_root.iterdir() if path.is_dir() and path.name not in active_slugs):
            summary["changed_paths"].extend(_repo_sync_remove_tree(stale_dir))
    if checkout_root.exists():
        for stale_dir in sorted(path for path in checkout_root.iterdir() if path.is_dir() and path.name not in active_slugs):
            shutil.rmtree(stale_dir, ignore_errors=True)

    summary["changed_paths"] = sorted(set(str(path) for path in summary["changed_paths"]))
    (state_dir / "status.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    note_refresh_job(
        conn,
        job_name="vault-github-sync",
        job_kind="vault-github-sync",
        target_id="Repos",
        schedule="every 1h via curator-refresh",
        status="warn" if summary["repos_failed"] else "ok",
        note=(
            f"repos={summary['repos_total']} synced={len(summary['repos_synced'])} "
            f"changed_paths={len(summary['changed_paths'])} failures={len(summary['repos_failed'])}"
        ),
    )
    return summary


def mark_notification_delivered(conn: sqlite3.Connection, notification_id: int) -> None:
    conn.execute(
        "UPDATE notification_outbox SET delivered_at = ?, delivery_error = NULL WHERE id = ?",
        (utc_now_iso(), notification_id),
    )
    conn.commit()


def mark_notification_error(conn: sqlite3.Connection, notification_id: int, error: str) -> None:
    conn.execute(
        "UPDATE notification_outbox SET delivery_error = ? WHERE id = ?",
        (error[:500], notification_id),
    )
    conn.commit()


def fetch_undelivered_notifications(
    conn: sqlite3.Connection,
    limit: int = 50,
    *,
    include_user_agent: bool = True,
) -> list[dict[str, Any]]:
    where = ["delivered_at IS NULL"]
    if not include_user_agent:
        where.append("target_kind != 'user-agent'")
    rows = conn.execute(
        f"""
        SELECT id, target_kind, target_id, channel_kind, message, extra_json, created_at, delivery_error
        FROM notification_outbox
        WHERE {' AND '.join(where)}
        ORDER BY
          CASE target_kind
            WHEN 'operator' THEN 0
            WHEN 'curator' THEN 1
            ELSE 2
          END,
          id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def has_pending_curator_brief_fanout(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM notification_outbox
        WHERE delivered_at IS NULL
          AND target_kind = 'curator'
          AND channel_kind = 'brief-fanout'
        LIMIT 1
        """
    ).fetchone()
    return row is not None


def operator_telegram_action_extra(
    cfg: Config,
    *,
    scope: str,
    target_id: str,
) -> dict[str, Any] | None:
    normalized_scope = scope.strip().lower()
    target = target_id.strip()
    if (
        cfg.operator_notify_platform != "telegram"
        or not cfg.curator_telegram_onboarding_enabled
        or normalized_scope not in {"request", "onboarding"}
        or not target
    ):
        return None
    return {
        "telegram_reply_markup": {
            "inline_keyboard": [[
                {"text": "Approve", "callback_data": f"almanac:{normalized_scope}:approve:{target}"},
                {"text": "Deny", "callback_data": f"almanac:{normalized_scope}:deny:{target}"},
            ]]
        }
    }


def _short_commit(value: str) -> str:
    text = str(value or "").strip()
    return text[:12] if len(text) >= 12 else text


def operator_upgrade_action_extra(
    cfg: Config,
    *,
    upstream_commit: str,
) -> dict[str, Any] | None:
    target = str(upstream_commit or "").strip()
    if not target:
        return None
    callback_install = f"almanac:upgrade:install:{target}"
    callback_dismiss = f"almanac:upgrade:dismiss:{target}"
    if cfg.operator_notify_platform == "telegram" and cfg.curator_telegram_onboarding_enabled:
        return {
            "telegram_reply_markup": {
                "inline_keyboard": [[
                    {"text": "Dismiss", "callback_data": callback_dismiss},
                    {"text": "Install", "callback_data": callback_install},
                ]]
            }
        }
    if (
        cfg.operator_notify_platform == "discord"
        and cfg.curator_discord_onboarding_enabled
        and str(cfg.operator_notify_channel_id or "").strip().isdigit()
    ):
        return {
            "discord_components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "style": 2,
                            "label": "Dismiss",
                            "custom_id": callback_dismiss,
                        },
                        {
                            "type": 2,
                            "style": 1,
                            "label": "Install",
                            "custom_id": callback_install,
                        },
                    ],
                }
            ]
        }
    return None


def consume_agent_notifications(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Atomically return + ack undelivered notifications for a specific agent.

    This is the authenticated read path for user agents: they poll during the
    periodic refresh, act on the signals (SSOT nudges, subscription change
    markers), and never see the same row twice. Rows are marked delivered with
    an `agent-ack` channel_kind suffix so the audit trail shows who consumed it.
    """
    rows = conn.execute(
        """
        SELECT id, target_kind, target_id, channel_kind, message, created_at
        FROM notification_outbox
        WHERE delivered_at IS NULL
          AND target_kind = 'user-agent'
          AND target_id = ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (agent_id, limit),
    ).fetchall()
    if rows:
        now = utc_now_iso()
        conn.executemany(
            "UPDATE notification_outbox SET delivered_at = ? WHERE id = ?",
            [(now, int(r["id"])) for r in rows],
        )
        conn.commit()
    return [dict(r) for r in rows]


def list_notifications(
    conn: sqlite3.Connection,
    *,
    target_kind: str | None = None,
    target_id: str | None = None,
    undelivered_only: bool = False,
) -> list[dict[str, Any]]:
    where = []
    params: list[Any] = []
    if target_kind:
        where.append("target_kind = ?")
        params.append(target_kind)
    if target_id:
        where.append("target_id = ?")
        params.append(target_id)
    if undelivered_only:
        where.append("delivered_at IS NULL")
    query = "SELECT * FROM notification_outbox"
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY id DESC"
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def fetch_active_token_rows(conn: sqlite3.Connection, target: str) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT *
        FROM bootstrap_tokens
        WHERE revoked_at IS NULL AND (token_id = ? OR agent_id = ?)
        ORDER BY issued_at DESC
        """,
        (target, target),
    ).fetchall()
    return rows


def revoke_token(
    conn: sqlite3.Connection,
    *,
    target: str,
    surface: str,
    actor: str,
    reason: str,
    cfg: Config | None = None,
) -> int:
    rows = fetch_active_token_rows(conn, target)
    if not rows:
        return 0
    surface = normalize_surface(surface, default="ctl")
    now_iso = utc_now_iso()
    conn.execute(
        """
        UPDATE bootstrap_tokens
        SET revoked_at = ?, revoked_by_surface = ?, revoked_by_actor = ?, revocation_reason = ?
        WHERE revoked_at IS NULL AND (token_id = ? OR agent_id = ?)
        """,
        (now_iso, surface, actor, reason, target, target),
    )
    conn.commit()

    if cfg is not None:
        agent_ids = sorted({str(r["agent_id"]) for r in rows})
        queue_notification(
            conn,
            target_kind="operator",
            target_id=cfg.operator_notify_channel_id or cfg.operator_notify_platform or "operator",
            channel_kind=cfg.operator_notify_platform or "tui-only",
            message=(
                f"Token revoked via {surface} by {actor}: target={target} "
                f"agents={','.join(agent_ids)} reason={reason}"
            ),
        )
    return len(rows)


def reinstate_token(
    conn: sqlite3.Connection,
    *,
    token_id: str,
    actor: str,
    surface: str = "ctl",
    cfg: Config | None = None,
) -> dict[str, Any]:
    """Reinstate a revoked token. This only un-revokes the token for an agent
    whose runtime still exists; it WILL NOT resurrect a de-enrolled agent
    because `agent_deenroll` already tore down the systemd units, the
    HERMES_HOME, and the manifest. The DB row alone cannot rebuild those, and
    silently flipping status back to 'active' would produce a zombie agent."""
    row = conn.execute(
        "SELECT * FROM bootstrap_tokens WHERE token_id = ?",
        (token_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown token: {token_id}")
    if row["revoked_at"] is None:
        return {"token_id": token_id, "already_active": True}

    agent_row = conn.execute(
        "SELECT status FROM agents WHERE agent_id = ?",
        (row["agent_id"],),
    ).fetchone()
    if agent_row is not None and str(agent_row["status"]) == "deenrolled":
        raise PermissionError(
            f"agent {row['agent_id']} has been de-enrolled; its runtime "
            "(HERMES_HOME + systemd units) was removed. Reinstating the DB "
            "row alone would create a zombie agent. Re-enroll via `init.sh "
            "agent` instead."
        )

    surface = normalize_surface(surface, default="ctl")
    conn.execute(
        """
        UPDATE bootstrap_tokens
        SET revoked_at = NULL, revoked_by_surface = NULL, revoked_by_actor = NULL,
            revocation_reason = NULL
        WHERE token_id = ?
        """,
        (token_id,),
    )
    conn.execute(
        "UPDATE agents SET status = 'active' WHERE agent_id = ?",
        (row["agent_id"],),
    )
    conn.commit()
    if cfg is not None:
        queue_notification(
            conn,
            target_kind="operator",
            target_id=cfg.operator_notify_channel_id or cfg.operator_notify_platform or "operator",
            channel_kind=cfg.operator_notify_platform or "tui-only",
            message=(
                f"Token reinstated via {surface} by {actor}: token_id={token_id} "
                f"agent_id={row['agent_id']}"
            ),
        )
    return {
        "token_id": token_id,
        "agent_id": row["agent_id"],
        "reinstated_by_surface": surface,
        "reinstated_by_actor": actor,
    }


def validate_token(conn: sqlite3.Connection, raw_token: str) -> sqlite3.Row:
    token_hash = hash_token(raw_token)
    row = conn.execute(
        """
        SELECT *
        FROM bootstrap_tokens
        WHERE token_hash = ? AND revoked_at IS NULL
        ORDER BY issued_at DESC
        LIMIT 1
        """,
        (token_hash,),
    ).fetchone()
    if row is None:
        raise PermissionError("token is missing or revoked")
    activation_request_id = str(row["activation_request_id"] or "")
    if activation_request_id:
        request_row = conn.execute(
            """
            SELECT status, expires_at
            FROM bootstrap_requests
            WHERE request_id = ?
            """,
            (activation_request_id,),
        ).fetchone()
        if request_row is None:
            raise PermissionError("token handshake is missing its bootstrap request")
        status = str(request_row["status"] or "")
        if status != "approved":
            if status == "pending":
                raise PermissionError("token is pending operator approval")
            if status == "denied":
                raise PermissionError("token enrollment request was denied")
            if status == "cancelled":
                raise PermissionError("token enrollment request was cancelled")
            if status == "expired":
                raise PermissionError("token enrollment request expired")
            raise PermissionError(f"token is not active (request status: {status or 'unknown'})")
        if not row["activated_at"]:
            activated_at = utc_now_iso()
            conn.execute(
                "UPDATE bootstrap_tokens SET activated_at = ? WHERE token_id = ?",
                (activated_at, row["token_id"]),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM bootstrap_tokens WHERE token_id = ?",
                (row["token_id"],),
            ).fetchone()
    return row


OPERATOR_ROLES = ("curator", "operator")
VALID_APPROVAL_SURFACES = ("curator-channel", "curator-tui", "ctl")


def validate_operator_token(conn: sqlite3.Connection, raw_token: str) -> sqlite3.Row:
    token_row = validate_token(conn, raw_token)
    agent_row = conn.execute(
        "SELECT role FROM agents WHERE agent_id = ? AND status = 'active'",
        (token_row["agent_id"],),
    ).fetchone()
    if agent_row is None or str(agent_row["role"]) not in OPERATOR_ROLES:
        raise PermissionError("operator-class token required")
    return token_row


def normalize_surface(raw: str, default: str = "curator-tui") -> str:
    value = (raw or "").strip().lower()
    if value not in VALID_APPROVAL_SURFACES:
        return default
    return value


def subscriptions_for_agent(conn: sqlite3.Connection, agent_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT s.vault_name, s.subscribed, s.source, s.updated_at, v.vault_path, v.owner,
               v.default_subscribed, d.description
        FROM agent_vault_subscriptions s
        LEFT JOIN vaults v ON v.vault_name = s.vault_name
        LEFT JOIN vault_definitions d ON d.vault_name = s.vault_name AND d.is_valid = 1
        WHERE s.agent_id = ?
        ORDER BY s.vault_name
        """,
        (agent_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def ensure_default_subscriptions(conn: sqlite3.Connection, agent_id: str) -> None:
    existing = conn.execute(
        "SELECT COUNT(*) AS count FROM agent_vault_subscriptions WHERE agent_id = ?",
        (agent_id,),
    ).fetchone()
    if existing and int(existing["count"]) > 0:
        return
    now_iso = utc_now_iso()
    for row in conn.execute("SELECT vault_name, default_subscribed FROM vaults ORDER BY vault_name"):
        conn.execute(
            """
            INSERT INTO agent_vault_subscriptions (agent_id, vault_name, subscribed, source, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (agent_id, row["vault_name"], int(row["default_subscribed"]), "default", now_iso),
        )
    conn.commit()


def set_vault_subscription(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    vault_name: str,
    subscribed: bool,
    source: str,
) -> dict[str, Any]:
    vault = conn.execute("SELECT vault_name FROM vaults WHERE vault_name = ?", (vault_name,)).fetchone()
    if vault is None:
        raise ValueError(f"unknown vault: {vault_name}")
    now_iso = utc_now_iso()
    conn.execute(
        """
        INSERT INTO agent_vault_subscriptions (agent_id, vault_name, subscribed, source, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(agent_id, vault_name)
        DO UPDATE SET subscribed = excluded.subscribed, source = excluded.source, updated_at = excluded.updated_at
        """,
        (agent_id, vault_name, int(subscribed), source, now_iso),
    )
    conn.commit()
    return {
        "agent_id": agent_id,
        "vault_name": vault_name,
        "subscribed": bool(subscribed),
        "source": source,
        "updated_at": now_iso,
    }


def _prior_defaults(conn: sqlite3.Connection, prior_agent_id: str | None) -> dict[str, Any]:
    if not prior_agent_id:
        return {}
    agent = conn.execute(
        "SELECT model_preset, model_string, channels_json, archived_state_path FROM agents WHERE agent_id = ?",
        (prior_agent_id,),
    ).fetchone()
    if agent is None:
        return {}
    subscriptions = [
        row["vault_name"]
        for row in conn.execute(
            """
            SELECT vault_name
            FROM agent_vault_subscriptions
            WHERE agent_id = ? AND subscribed = 1
            ORDER BY vault_name
            """,
            (prior_agent_id,),
        )
    ]
    return {
        "prior_agent_id": prior_agent_id,
        "model_preset": agent["model_preset"],
        "model_string": agent["model_string"],
        "channels": json_loads(agent["channels_json"], []),
        "subscriptions": subscriptions,
        "archived_state_path": agent["archived_state_path"],
    }


def find_prior_agent(conn: sqlite3.Connection, requester_identity: str, unix_user: str) -> str | None:
    row = conn.execute(
        """
        SELECT agent_id
        FROM agents
        WHERE role = 'user' AND (unix_user = ? OR display_name = ?)
        ORDER BY last_enrolled_at DESC
        LIMIT 1
        """,
        (unix_user, requester_identity),
    ).fetchone()
    return str(row["agent_id"]) if row else None


def find_pending_bootstrap_request(
    conn: sqlite3.Connection,
    *,
    unix_user: str,
    source_ip: str,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT r.*, t.agent_id, t.issued_at AS token_issued_at, t.activated_at
        FROM bootstrap_requests r
        LEFT JOIN bootstrap_tokens t ON t.token_id = r.token_id
        WHERE r.status = 'pending'
          AND r.unix_user = ?
          AND r.source_ip = ?
        ORDER BY r.requested_at DESC
        LIMIT 1
        """,
        (unix_user, source_ip),
    ).fetchone()


def _issue_bootstrap_token(
    conn: sqlite3.Connection,
    *,
    request_id: str | None,
    agent_id: str,
    requester_identity: str,
    source_ip: str,
    issued_by: str,
    activate_now: bool,
) -> dict[str, str]:
    issued_at = utc_now_iso()
    token_id = generate_token_id()
    raw_token = generate_raw_token()
    activated_at = issued_at if activate_now else ""
    conn.execute(
        """
        INSERT INTO bootstrap_tokens (
          token_id, agent_id, token_hash, requester_identity, source_ip, issued_at, issued_by,
          activation_request_id, activated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            token_id,
            agent_id,
            hash_token(raw_token),
            requester_identity,
            source_ip,
            issued_at,
            issued_by,
            request_id,
            activated_at or None,
        ),
    )
    return {
        "token_id": token_id,
        "raw_token": raw_token,
        "issued_at": issued_at,
        "activated_at": activated_at,
        "agent_id": agent_id,
    }


def auto_provision_retry_delay_seconds(cfg: Config, attempts: int) -> int:
    step = max(1, int(attempts))
    delay = cfg.auto_provision_retry_base_seconds * (2 ** max(0, step - 1))
    return max(
        cfg.auto_provision_retry_base_seconds,
        min(cfg.auto_provision_retry_max_seconds, delay),
    )


def _revoke_request_tokens(
    conn: sqlite3.Connection,
    *,
    request_id: str,
    surface: str,
    actor: str,
    reason: str,
    except_token_id: str = "",
) -> int:
    rows = conn.execute(
        """
        SELECT token_id
        FROM bootstrap_tokens
        WHERE activation_request_id = ? AND revoked_at IS NULL
        """,
        (request_id,),
    ).fetchall()
    token_ids = [
        str(row["token_id"])
        for row in rows
        if str(row["token_id"]) and str(row["token_id"]) != except_token_id
    ]
    if not token_ids:
        return 0
    now_iso = utc_now_iso()
    conn.executemany(
        """
        UPDATE bootstrap_tokens
        SET revoked_at = ?, revoked_by_surface = ?, revoked_by_actor = ?, revocation_reason = ?
        WHERE token_id = ?
        """,
        [(now_iso, surface, actor, reason, token_id) for token_id in token_ids],
    )
    return len(token_ids)


def ensure_unix_user_ready(unix_user: str) -> dict[str, str]:
    if subprocess.run(["id", "-u", unix_user], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
        subprocess.run(["useradd", "-m", "-s", "/bin/bash", unix_user], check=True)
    home = Path(pwd.getpwnam(unix_user).pw_dir)
    uid = pwd.getpwnam(unix_user).pw_uid
    subprocess.run(["loginctl", "enable-linger", unix_user], check=True)
    subprocess.run(["systemctl", "start", f"user@{uid}.service"], check=False)
    for path in (
        home / ".config" / "systemd" / "user",
        home / ".local" / "share" / "almanac-agent",
        home / ".local" / "state" / "almanac-agent",
    ):
        path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["chown", "-R", f"{unix_user}:{unix_user}", str(home / ".config"), str(home / ".local")], check=False)
    return {
        "unix_user": unix_user,
        "home": str(home),
        "uid": str(uid),
    }


def activation_trigger_dir(cfg: Config) -> Path:
    path = cfg.state_dir / "activation-triggers"
    path.mkdir(parents=True, exist_ok=True)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        try:
            owner = pwd.getpwnam(cfg.almanac_user)
            os.chown(path, owner.pw_uid, owner.pw_gid)
        except (KeyError, OSError):
            pass
    try:
        path.chmod(0o755)
    except OSError:
        pass
    return path


def activation_trigger_path(cfg: Config, agent_id: str) -> Path:
    return activation_trigger_dir(cfg) / f"{agent_id}.json"


def grant_agent_runtime_access(
    cfg: Config,
    *,
    unix_user: str,
    agent_id: str,
) -> dict[str, Any]:
    """Idempotently restore enrolled-user access to shared Almanac paths."""

    setfacl_bin = shutil.which("setfacl")
    if not setfacl_bin:
        raise RuntimeError(
            "setfacl is required so enrolled users can traverse the shared Almanac runtime"
        )

    activation_dir = activation_trigger_path(cfg, agent_id).parent
    activation_dir.mkdir(parents=True, exist_ok=True)
    runtime_python = cfg.runtime_dir / "hermes-venv" / "bin" / "python3"
    runtime_python_root: Path | None = None
    extra_traverse: list[Path] = []
    try:
        resolved_runtime_python = runtime_python.resolve(strict=True)
    except FileNotFoundError:
        resolved_runtime_python = None

    if resolved_runtime_python is not None:
        candidate_root = (
            resolved_runtime_python.parent.parent
            if resolved_runtime_python.parent.name == "bin"
            else resolved_runtime_python.parent
        )
        if str(candidate_root).startswith(str(cfg.almanac_home)):
            runtime_python_root = candidate_root
            for parent in candidate_root.parents:
                if not str(parent).startswith(str(cfg.almanac_home)):
                    break
                extra_traverse.append(parent)

    traverse_only = [
        cfg.almanac_home,
        cfg.private_dir,
        cfg.state_dir,
        cfg.runtime_dir,
        *extra_traverse,
    ]
    readable_trees = [
        cfg.repo_dir,
        cfg.runtime_dir / "hermes-venv",
        cfg.runtime_dir / "hermes-agent-src",
        activation_dir,
    ]
    if runtime_python_root is not None:
        readable_trees.append(runtime_python_root)

    applied_traverse: list[str] = []
    applied_readable: list[str] = []
    for target in traverse_only:
        if target.exists():
            subprocess.run([setfacl_bin, "-m", f"u:{unix_user}:--x", str(target)], check=True)
            applied_traverse.append(str(target))
    for target in readable_trees:
        if target.exists():
            subprocess.run([setfacl_bin, "-R", "-m", f"u:{unix_user}:rX", str(target)], check=True)
            applied_readable.append(str(target))

    return {
        "unix_user": unix_user,
        "agent_id": agent_id,
        "traverse_only": applied_traverse,
        "readable_trees": applied_readable,
    }


def write_activation_trigger(
    cfg: Config,
    *,
    agent_id: str,
    request_id: str,
    status: str,
    requester_identity: str,
    unix_user: str,
    source_ip: str,
    token_id: str | None = None,
    note: str = "",
) -> Path:
    path = activation_trigger_path(cfg, agent_id)
    payload = {
        "agent_id": agent_id,
        "request_id": request_id,
        "status": status,
        "requester_identity": requester_identity,
        "unix_user": unix_user,
        "source_ip": source_ip,
        "token_id": token_id or "",
        "note": note,
        "updated_at": utc_now_iso(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp", prefix=".almanac-activation-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, str(path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    try:
        path.chmod(0o644)
    except OSError:
        pass
    return path


def request_bootstrap(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    requester_identity: str,
    unix_user: str,
    source_ip: str,
    tailnet_identity: dict[str, str] | None = None,
    issue_pending_token: bool = False,
    auto_provision: bool = False,
    requested_model_preset: str = "",
    requested_channels: list[str] | None = None,
) -> dict[str, Any]:
    tailnet_identity = tailnet_identity or {}
    # When Tailscale Serve forwards the request, the raw source_ip is always
    # loopback (the local proxy), so an IP-keyed rate limit pools every tailnet
    # caller into the same bucket. Use the verified tailnet login as the
    # subject when present so the bucket is per-user, not per-proxy.
    rate_limit_subject = tailnet_identity.get("login") or source_ip
    ensure_request_expiry(conn)
    existing = find_pending_bootstrap_request(conn, unix_user=unix_user, source_ip=source_ip)
    if existing is not None:
        agent_id = str(existing["agent_id"] or existing["prior_agent_id"] or make_agent_id(str(existing["unix_user"]), "user"))
        existing_auto_provision = bool(int(existing["auto_provision"] or 0))
        if auto_provision or existing_auto_provision:
            write_activation_trigger(
                cfg,
                agent_id=agent_id,
                request_id=str(existing["request_id"]),
                status="pending",
                requester_identity=str(existing["requester_identity"]),
                unix_user=str(existing["unix_user"]),
                source_ip=str(existing["source_ip"]),
                token_id=str(existing["token_id"] or ""),
                note="Resumed existing pending auto-provision handshake.",
            )
            return {
                "request_id": str(existing["request_id"]),
                "status": "pending",
                "expires_at": str(existing["expires_at"]),
                "prior_defaults": json_loads(existing["prior_defaults_json"], {}),
                "prior_agent_id": existing["prior_agent_id"],
                "agent_id": agent_id,
                "activation_state": "pending-operator-approval",
                "resume_existing": True,
                "auto_provision": True,
                "message": "A pending remote auto-provision enrollment already exists for this user and source. Wait for operator approval instead of submitting another request.",
            }

    if issue_pending_token:
        if existing is not None:
            pending_token = _issue_bootstrap_token(
                conn,
                request_id=str(existing["request_id"]),
                agent_id=agent_id,
                requester_identity=str(existing["requester_identity"]),
                source_ip=str(existing["source_ip"]),
                issued_by="bootstrap.handshake.resume",
                activate_now=False,
            )
            _revoke_request_tokens(
                conn,
                request_id=str(existing["request_id"]),
                surface="bootstrap.handshake",
                actor="almanac-mcp",
                reason="superseded by resumed pending handshake",
                except_token_id=pending_token["token_id"],
            )
            conn.execute(
                """
                UPDATE bootstrap_requests
                SET token_id = ?, token_delivered_at = ?
                WHERE request_id = ?
                """,
                (pending_token["token_id"], pending_token["issued_at"], str(existing["request_id"])),
            )
            conn.commit()
            write_activation_trigger(
                cfg,
                agent_id=agent_id,
                request_id=str(existing["request_id"]),
                status="pending",
                requester_identity=str(existing["requester_identity"]),
                unix_user=str(existing["unix_user"]),
                source_ip=str(existing["source_ip"]),
                token_id=pending_token["token_id"],
                note="Resumed existing pending handshake with a freshly minted local token.",
            )
            return {
                "request_id": str(existing["request_id"]),
                "status": "pending",
                "expires_at": str(existing["expires_at"]),
                "prior_defaults": json_loads(existing["prior_defaults_json"], {}),
                "prior_agent_id": existing["prior_agent_id"],
                "agent_id": agent_id,
                "token_id": pending_token["token_id"],
                "raw_token": pending_token["raw_token"],
                "token_delivered_at": pending_token["issued_at"],
                "activation_state": "pending-operator-approval",
                "resume_existing": True,
                "auto_provision": False,
                "message": "A pending bootstrap handshake already exists for this user and source. A fresh local token was minted for this client; it will activate automatically once the operator approves the request.",
            }

    now = utc_now()
    window_start = (now - dt.timedelta(seconds=cfg.bootstrap_window_seconds)).replace(microsecond=0).isoformat()
    if rate_limit_count(conn, "ip", rate_limit_subject, window_start) >= cfg.bootstrap_per_ip_limit:
        raise RateLimitError(
            f"rate-limited: per-source limit ({cfg.bootstrap_per_ip_limit}) exceeded for {rate_limit_subject}",
            retry_after_seconds=cfg.bootstrap_window_seconds,
            scope="per-ip",
        )

    pending_count = conn.execute(
        "SELECT COUNT(*) AS count FROM bootstrap_requests WHERE status = 'pending'"
    ).fetchone()
    if pending_count and int(pending_count["count"]) >= cfg.bootstrap_global_pending_limit:
        raise RateLimitError(
            f"rate-limited: global pending limit ({cfg.bootstrap_global_pending_limit}) exceeded",
            retry_after_seconds=cfg.bootstrap_pending_ttl_seconds,
            scope="global-pending",
        )

    record_rate_limit_event(conn, "ip", rate_limit_subject)
    record_rate_limit_event(conn, "global", "pending")

    request_id = generate_request_id()
    expires_at = (now + dt.timedelta(seconds=cfg.bootstrap_pending_ttl_seconds)).replace(microsecond=0).isoformat()
    prior_agent_id = find_prior_agent(conn, requester_identity, unix_user)
    defaults = _prior_defaults(conn, prior_agent_id)
    agent_id = prior_agent_id or make_agent_id(str(unix_user), "user")
    requested_channels_json = json_dumps(_channels_payload(requested_channels or []))
    conn.execute(
        """
        INSERT INTO bootstrap_requests (
          request_id, requester_identity, unix_user, source_ip, requested_at, expires_at,
          status, prior_agent_id, prior_defaults_json, auto_provision,
          requested_model_preset, requested_channels_json
        )
        VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)
        """,
        (
            request_id,
            requester_identity,
            unix_user,
            source_ip,
            now.replace(microsecond=0).isoformat(),
            expires_at,
            prior_agent_id,
            json_dumps(defaults),
            int(bool(auto_provision)),
            requested_model_preset or None,
            requested_channels_json,
        ),
    )

    pending_token: dict[str, str] | None = None
    if issue_pending_token and not auto_provision:
        pending_token = _issue_bootstrap_token(
            conn,
            request_id=request_id,
            agent_id=agent_id,
            requester_identity=requester_identity,
            source_ip=source_ip,
            issued_by="bootstrap.handshake",
            activate_now=False,
        )
        conn.execute(
            """
            UPDATE bootstrap_requests
            SET token_id = ?, token_delivered_at = ?
            WHERE request_id = ?
            """,
            (pending_token["token_id"], pending_token["issued_at"], request_id),
        )
    conn.commit()
    write_activation_trigger(
        cfg,
        agent_id=agent_id,
        request_id=request_id,
        status="pending",
        requester_identity=requester_identity,
        unix_user=unix_user,
        source_ip=source_ip,
        token_id=(pending_token or {}).get("token_id"),
        note="Pending operator approval.",
    )

    prior_note = ""
    if prior_agent_id:
        prior_note = f" previously enrolled as {prior_agent_id}; archived defaults detected."
    provisioning_note = " On approval, Almanac will create the Unix user and provision the host-side agent automatically." if auto_provision else ""
    # Build an origin string that's actually useful. Behind Tailscale Serve the
    # raw source_ip is 127.0.0.1 (the proxy), so prefer the verified tailnet
    # login when present. Fall back to the IP for direct (non-proxied) calls.
    tailnet_login = str(tailnet_identity.get("login") or "").strip()
    tailnet_name = str(tailnet_identity.get("name") or "").strip()
    if tailnet_login:
        if tailnet_name and tailnet_name != tailnet_login:
            origin_note = f"tailnet identity {tailnet_name} <{tailnet_login}>"
        else:
            origin_note = f"tailnet identity {tailnet_login}"
    else:
        origin_note = f"source {source_ip}"
    message = (
        f"{requester_identity} ({unix_user}) is requesting enrollment from {origin_note}."
        f"{prior_note}{provisioning_note} Approve via almanac-ctl request approve {request_id}"
    )
    if cfg.operator_notify_platform == "telegram" and cfg.curator_telegram_onboarding_enabled:
        message += " or tap Approve / Deny below."
    queue_notification(
        conn,
        target_kind="operator",
        target_id=cfg.operator_notify_channel_id or cfg.operator_notify_platform or "operator",
        channel_kind=cfg.operator_notify_platform or "tui-only",
        message=message,
        extra=operator_telegram_action_extra(cfg, scope="request", target_id=request_id),
    )

    response = {
        "request_id": request_id,
        "status": "pending",
        "expires_at": expires_at,
        "prior_defaults": defaults,
        "agent_id": agent_id,
        "auto_provision": bool(auto_provision),
    }
    if pending_token is not None:
        response.update(
            {
                "token_id": pending_token["token_id"],
                "raw_token": pending_token["raw_token"],
                "token_delivered_at": pending_token["issued_at"],
                "activation_state": "pending-operator-approval",
                "message": "Bootstrap token issued; it will activate automatically once the operator approves the request.",
            }
        )
    elif auto_provision:
        response.update(
            {
                "activation_state": "pending-operator-approval",
                "message": "Enrollment request submitted. Once approved, Almanac will create the Unix user and provision the host-side agent automatically.",
            }
        )
    return response


def list_requests(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    ensure_request_expiry(conn)
    rows = conn.execute(
        """
        SELECT *
        FROM bootstrap_requests
        ORDER BY requested_at DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def approve_request(
    conn: sqlite3.Connection,
    *,
    request_id: str,
    surface: str,
    actor: str,
    cfg: Config | None = None,
) -> dict[str, Any]:
    ensure_request_expiry(conn)
    row = conn.execute(
        "SELECT * FROM bootstrap_requests WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown bootstrap request: {request_id}")
    if row["status"] != "pending":
        raise ValueError(f"bootstrap request is not pending: {row['status']}")
    surface = normalize_surface(surface, default="curator-tui")
    now_iso = utc_now_iso()
    conn.execute(
        """
        UPDATE bootstrap_requests
        SET status = 'approved', approval_surface = ?, approval_actor = ?, approved_at = ?
        WHERE request_id = ?
        """,
        (surface, actor, now_iso, request_id),
    )
    conn.execute(
        """
        UPDATE bootstrap_tokens
        SET activated_at = COALESCE(activated_at, ?)
        WHERE activation_request_id = ?
        """,
        (now_iso, request_id),
    )
    conn.commit()
    agent_id = str(row["prior_agent_id"] or make_agent_id(str(row["unix_user"]), "user"))
    auto_provision = bool(int(row["auto_provision"] or 0))
    token_row = conn.execute(
        "SELECT token_id FROM bootstrap_tokens WHERE activation_request_id = ? ORDER BY issued_at DESC LIMIT 1",
        (request_id,),
    ).fetchone()
    token_id = str(token_row["token_id"]) if token_row is not None else ""
    if cfg is not None:
        write_activation_trigger(
            cfg,
            agent_id=agent_id,
            request_id=request_id,
            status="approved",
            requester_identity=str(row["requester_identity"]),
            unix_user=str(row["unix_user"]),
            source_ip=str(row["source_ip"]),
            token_id=token_id,
            note=f"Approved via {surface} by {actor}.",
        )
        if not auto_provision:
            queue_notification(
                conn,
                target_kind="user-agent",
                target_id=agent_id,
                channel_kind="activate",
                message=(
                    f"Enrollment approved for {agent_id}. Almanac activation is ready to run."
                ),
            )
    if cfg is not None:
        suffix = (
            " Root auto-provisioning is queued and will run on the next system timer pass."
            if auto_provision
            else ""
        )
        queue_notification(
            conn,
            target_kind="operator",
            target_id=cfg.operator_notify_channel_id or cfg.operator_notify_platform or "operator",
            channel_kind=cfg.operator_notify_platform or "tui-only",
            message=(
                f"Approved enrollment request {request_id} for "
                f"{row['requester_identity']} ({row['unix_user']}) via {surface} by {actor}.{suffix}"
            ),
        )
    return {
        "request_id": request_id,
        "agent_id": agent_id,
        "status": "approved",
        "approved_at": now_iso,
        "approved_by_surface": surface,
        "approved_by_actor": actor,
    }


def deny_request(
    conn: sqlite3.Connection,
    *,
    request_id: str,
    surface: str,
    actor: str,
    cfg: Config | None = None,
) -> dict[str, Any]:
    ensure_request_expiry(conn)
    row = conn.execute(
        "SELECT * FROM bootstrap_requests WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown bootstrap request: {request_id}")
    if row["status"] != "pending":
        raise ValueError(f"bootstrap request is not pending: {row['status']}")
    surface = normalize_surface(surface, default="curator-tui")
    now_iso = utc_now_iso()
    conn.execute(
        """
        UPDATE bootstrap_requests
        SET status = 'denied', denied_by_surface = ?, denied_by_actor = ?, denied_at = ?
        WHERE request_id = ?
        """,
        (surface, actor, now_iso, request_id),
    )
    conn.commit()
    if cfg is not None:
        agent_id = str(row["prior_agent_id"] or make_agent_id(str(row["unix_user"]), "user"))
        write_activation_trigger(
            cfg,
            agent_id=agent_id,
            request_id=request_id,
            status="denied",
            requester_identity=str(row["requester_identity"]),
            unix_user=str(row["unix_user"]),
            source_ip=str(row["source_ip"]),
            token_id=str(row["token_id"] or ""),
            note=f"Denied via {surface} by {actor}.",
        )
        queue_notification(
            conn,
            target_kind="operator",
            target_id=cfg.operator_notify_channel_id or cfg.operator_notify_platform or "operator",
            channel_kind=cfg.operator_notify_platform or "tui-only",
            message=(
                f"Denied enrollment request {request_id} for "
                f"{row['requester_identity']} ({row['unix_user']}) via {surface} by {actor}."
            ),
        )
    return {
        "request_id": request_id,
        "status": "denied",
        "denied_at": now_iso,
        "denied_by_surface": surface,
        "denied_by_actor": actor,
    }


def bootstrap_status(conn: sqlite3.Connection, cfg: Config, request_id: str) -> dict[str, Any]:
    ensure_request_expiry(conn)
    row = conn.execute(
        "SELECT * FROM bootstrap_requests WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown bootstrap request: {request_id}")

    response = {
        "request_id": request_id,
        "status": row["status"],
        "expires_at": row["expires_at"],
        "prior_defaults": json_loads(row["prior_defaults_json"], {}),
        "prior_agent_id": row["prior_agent_id"],
        "auto_provision": bool(int(row["auto_provision"] or 0)),
        "provision_attempts": int(row["provision_attempts"] or 0),
        "provision_next_attempt_at": row["provision_next_attempt_at"],
        "provision_started_at": row["provision_started_at"],
        "provisioned_at": row["provisioned_at"],
        "provision_error": row["provision_error"],
    }

    if row["status"] != "approved":
        return response

    if bool(int(row["auto_provision"] or 0)):
        return response

    if row["token_id"]:
        response["token_id"] = row["token_id"]
        token_row = conn.execute(
            """
            SELECT agent_id, activated_at
            FROM bootstrap_tokens
            WHERE token_id = ?
            """,
            (row["token_id"],),
        ).fetchone()
        if token_row is not None:
            response["agent_id"] = token_row["agent_id"]
            if token_row["activated_at"]:
                response["activated_at"] = token_row["activated_at"]
        return response

    agent_id = row["prior_agent_id"] or make_agent_id(str(row["unix_user"]), "user")
    token_payload = _issue_bootstrap_token(
        conn,
        request_id=request_id,
        agent_id=agent_id,
        requester_identity=str(row["requester_identity"]),
        source_ip=str(row["source_ip"]),
        issued_by=str(row["approval_surface"] or "unknown"),
        activate_now=True,
    )
    delivered_at = token_payload["issued_at"]
    conn.execute(
        """
        UPDATE bootstrap_requests
        SET token_id = ?, token_delivered_at = ?
        WHERE request_id = ?
        """,
        (token_payload["token_id"], delivered_at, request_id),
    )
    conn.commit()
    response.update(
        {
            "token_id": token_payload["token_id"],
            "raw_token": token_payload["raw_token"],
            "token_delivered_at": delivered_at,
            "agent_id": agent_id,
            "activated_at": token_payload["activated_at"],
        }
    )
    return response


def issue_auto_provision_token(conn: sqlite3.Connection, request_id: str) -> dict[str, str]:
    row = conn.execute(
        "SELECT * FROM bootstrap_requests WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown bootstrap request: {request_id}")
    if str(row["status"]) != "approved":
        raise PermissionError(f"bootstrap request is not approved: {row['status']}")
    agent_id = str(row["prior_agent_id"] or make_agent_id(str(row["unix_user"]), "user"))
    _revoke_request_tokens(
        conn,
        request_id=request_id,
        surface="bootstrap.auto-provision",
        actor="almanac-provisioner",
        reason="superseded by auto-provision runtime token",
    )
    payload = _issue_bootstrap_token(
        conn,
        request_id=request_id,
        agent_id=agent_id,
        requester_identity=str(row["requester_identity"]),
        source_ip=str(row["source_ip"]),
        issued_by="bootstrap.auto-provision",
        activate_now=True,
    )
    conn.execute(
        """
        UPDATE bootstrap_requests
        SET token_id = ?, token_delivered_at = ?
        WHERE request_id = ?
        """,
        (payload["token_id"], payload["issued_at"], request_id),
    )
    conn.commit()
    return payload


def list_pending_auto_provision_requests(conn: sqlite3.Connection, cfg: Config) -> list[dict[str, Any]]:
    now_iso = utc_now_iso()
    stale_before_iso = auto_provision_stale_before_iso()
    rows = conn.execute(
        """
        SELECT *
        FROM bootstrap_requests
        WHERE status = 'approved'
          AND auto_provision = 1
          AND provisioned_at IS NULL
          AND COALESCE(provision_attempts, 0) < ?
          AND (provision_next_attempt_at IS NULL OR provision_next_attempt_at <= ?)
          AND (provision_started_at IS NULL OR provision_started_at <= ?)
        ORDER BY COALESCE(provision_next_attempt_at, approved_at, requested_at) ASC
        """
        ,
        (cfg.auto_provision_max_attempts, now_iso, stale_before_iso),
    ).fetchall()
    return [dict(row) for row in rows]


def mark_auto_provision_started(conn: sqlite3.Connection, request_id: str) -> int:
    stale_before_iso = auto_provision_stale_before_iso()
    cursor = conn.execute(
        """
        UPDATE bootstrap_requests
        SET provision_started_at = ?,
            provision_attempts = COALESCE(provision_attempts, 0) + 1,
            provision_error = NULL,
            provision_next_attempt_at = NULL
        WHERE request_id = ?
          AND status = 'approved'
          AND auto_provision = 1
          AND provisioned_at IS NULL
          AND (provision_started_at IS NULL OR provision_started_at <= ?)
        """,
        (utc_now_iso(), request_id, stale_before_iso),
    )
    conn.commit()
    if cursor.rowcount == 0:
        return 0
    row = conn.execute(
        "SELECT provision_attempts FROM bootstrap_requests WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    return int(row["provision_attempts"] if row else 0)


def mark_auto_provision_finished(
    conn: sqlite3.Connection,
    *,
    request_id: str,
    error: str = "",
    next_attempt_at: str = "",
) -> None:
    if error:
        conn.execute(
            """
            UPDATE bootstrap_requests
            SET provision_started_at = NULL,
                provision_error = ?,
                provision_next_attempt_at = ?
            WHERE request_id = ?
            """,
            (error, next_attempt_at or None, request_id),
        )
    else:
        conn.execute(
            """
            UPDATE bootstrap_requests
            SET provision_started_at = NULL,
                provisioned_at = ?,
                provision_error = NULL,
                provision_next_attempt_at = NULL
            WHERE request_id = ?
            """,
            (utc_now_iso(), request_id),
        )
    conn.commit()


def list_auto_provision_requests(conn: sqlite3.Connection, cfg: Config) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM bootstrap_requests
        WHERE auto_provision = 1
        ORDER BY requested_at DESC
        """
    ).fetchall()
    payload: list[dict[str, Any]] = []
    for raw_row in rows:
        row = dict(raw_row)
        attempts = int(row.get("provision_attempts") or 0)
        status = str(row.get("status") or "")
        if row.get("provisioned_at"):
            provision_state = "completed"
        elif status == "cancelled":
            provision_state = "cancelled"
        elif status != "approved":
            provision_state = status or "pending"
        elif row.get("provision_error") and attempts >= cfg.auto_provision_max_attempts and not row.get("provision_next_attempt_at"):
            provision_state = "failed"
        elif row.get("provision_error"):
            provision_state = "retry-scheduled"
        elif row.get("provision_started_at"):
            provision_state = "running"
        else:
            provision_state = "queued"
        row["provision_state"] = provision_state
        payload.append(row)
    return payload


def cancel_auto_provision_request(
    conn: sqlite3.Connection,
    *,
    request_id: str,
    surface: str,
    actor: str,
    reason: str = "",
    cfg: Config | None = None,
) -> dict[str, Any]:
    ensure_request_expiry(conn)
    row = conn.execute(
        "SELECT * FROM bootstrap_requests WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown bootstrap request: {request_id}")
    if not bool(int(row["auto_provision"] or 0)):
        raise ValueError("request is not an auto-provision enrollment")
    if str(row["status"]) != "approved":
        raise ValueError(f"auto-provision request is not approved: {row['status']}")
    if row["provisioned_at"]:
        raise ValueError("auto-provision request is already complete")

    surface = normalize_surface(surface, default="ctl")
    now_iso = utc_now_iso()
    cancel_reason = reason or "cancelled via operator"
    conn.execute(
        """
        UPDATE bootstrap_requests
        SET status = 'cancelled',
            cancelled_at = ?,
            cancelled_by_surface = ?,
            cancelled_by_actor = ?,
            cancelled_reason = ?,
            provision_next_attempt_at = NULL
        WHERE request_id = ?
        """,
        (now_iso, surface, actor, cancel_reason, request_id),
    )
    _revoke_request_tokens(
        conn,
        request_id=request_id,
        surface=surface,
        actor=actor,
        reason=cancel_reason,
    )
    conn.commit()

    agent_id = str(row["prior_agent_id"] or make_agent_id(str(row["unix_user"]), "user"))
    if cfg is not None:
        write_activation_trigger(
            cfg,
            agent_id=agent_id,
            request_id=request_id,
            status="cancelled",
            requester_identity=str(row["requester_identity"]),
            unix_user=str(row["unix_user"]),
            source_ip=str(row["source_ip"]),
            token_id="",
            note=f"Auto-provision cancelled via {surface} by {actor}.",
        )
        queue_notification(
            conn,
            target_kind="operator",
            target_id=cfg.operator_notify_channel_id or cfg.operator_notify_platform or "operator",
            channel_kind=cfg.operator_notify_platform or "tui-only",
            message=(
                f"Cancelled auto-provision request {request_id} for "
                f"{row['requester_identity']} ({row['unix_user']}) via {surface} by {actor}."
            ),
        )
    return {
        "request_id": request_id,
        "status": "cancelled",
        "cancelled_at": now_iso,
        "cancelled_by_surface": surface,
        "cancelled_by_actor": actor,
        "reason": cancel_reason,
    }


def retry_auto_provision_request(
    conn: sqlite3.Connection,
    *,
    request_id: str,
    surface: str,
    actor: str,
    cfg: Config | None = None,
) -> dict[str, Any]:
    ensure_request_expiry(conn)
    row = conn.execute(
        "SELECT * FROM bootstrap_requests WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown bootstrap request: {request_id}")
    if not bool(int(row["auto_provision"] or 0)):
        raise ValueError("request is not an auto-provision enrollment")
    if str(row["status"]) != "approved":
        raise ValueError(f"auto-provision request is not approved: {row['status']}")
    if row["provisioned_at"]:
        raise ValueError("auto-provision request is already complete")

    surface = normalize_surface(surface, default="ctl")
    now_iso = utc_now_iso()
    conn.execute(
        """
        UPDATE bootstrap_requests
        SET provision_attempts = 0,
            provision_started_at = NULL,
            provision_error = NULL,
            provision_next_attempt_at = ?
        WHERE request_id = ?
        """,
        (now_iso, request_id),
    )
    conn.commit()
    if cfg is not None:
        row = conn.execute(
            "SELECT requester_identity, unix_user FROM bootstrap_requests WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        queue_notification(
            conn,
            target_kind="operator",
            target_id=cfg.operator_notify_channel_id or cfg.operator_notify_platform or "operator",
            channel_kind=cfg.operator_notify_platform or "tui-only",
            message=(
                f"Reset auto-provision retries for {request_id} "
                f"({row['requester_identity']} / {row['unix_user']}) via {surface} by {actor}."
            ),
        )
    return {
        "request_id": request_id,
        "status": "approved",
        "retry_reset_at": now_iso,
        "retry_reset_by_surface": surface,
        "retry_reset_by_actor": actor,
    }


def _channels_payload(channels: list[str]) -> list[str]:
    normalized = []
    for channel in channels:
        value = str(channel).strip().lower()
        if not value:
            continue
        if value not in normalized:
            normalized.append(value)
    return normalized


def _manifest_path_for(cfg: Config, agent_id: str, role: str) -> Path:
    if role == "curator":
        return cfg.curator_manifest_path
    return cfg.agents_state_dir / agent_id / "manifest.json"


def write_shared_manifest(
    cfg: Config,
    *,
    agent_id: str,
    role: str,
    unix_user: str,
    display_name: str,
    hermes_home: str,
    model_preset: str,
    model_string: str,
    channels: list[str],
    allowed_mcps: list[dict[str, Any]],
    subscriptions: list[dict[str, Any]],
    home_channel: dict[str, Any] | None = None,
    operator_notify_channel: dict[str, Any] | None = None,
) -> Path:
    manifest_path = _manifest_path_for(cfg, agent_id, role)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    # tui_enabled is a structural invariant — every agent has TUI access, the flag exists
    # so downstream tooling can assert it and refuse to disable it.
    payload = {
        "agent_id": agent_id,
        "role": role,
        "unix_user": unix_user,
        "display_name": display_name,
        "hermes_home": hermes_home,
        "model_preset": model_preset,
        "model_string": model_string,
        "channels": channels,
        "tui_enabled": True,
        "allowed_mcps": allowed_mcps,
        "subscriptions": subscriptions,
        "home_channel": home_channel or {},
        "operator_notify_channel": operator_notify_channel,
        "updated_at": utc_now_iso(),
    }
    if role == "curator":
        payload["operator_general_channel"] = {
            "platform": cfg.operator_general_platform or "",
            "channel_id": cfg.operator_general_channel_id or "",
        }
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def register_agent(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    raw_token: str,
    unix_user: str,
    display_name: str,
    role: str,
    hermes_home: str,
    model_preset: str,
    model_string: str,
    channels: list[str],
    home_channel: dict[str, Any] | None = None,
    operator_notify_channel: dict[str, Any] | None = None,
) -> dict[str, Any]:
    token_row = validate_token(conn, raw_token)
    agent_id = str(token_row["agent_id"])
    now_iso = utc_now_iso()
    channels_value = _channels_payload(channels)
    allowed_mcps = [
        {"name": "almanac-mcp", "url": f"http://127.0.0.1:{cfg.public_mcp_port}/mcp"},
        {"name": "almanac-qmd", "url": cfg.qmd_url},
    ]
    if cfg.chutes_mcp_url:
        allowed_mcps.append({"name": "chutes-kb", "url": cfg.chutes_mcp_url})

    conn.execute(
        """
        INSERT INTO agents (
          agent_id, role, unix_user, display_name, status, hermes_home, manifest_path,
          archived_state_path, model_preset, model_string, channels_json,
          allowed_mcps_json, home_channel_json, operator_notify_channel_json,
          created_at, last_enrolled_at
        )
        VALUES (?, ?, ?, ?, 'active', ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(agent_id) DO UPDATE SET
          unix_user = excluded.unix_user,
          display_name = excluded.display_name,
          status = 'active',
          hermes_home = excluded.hermes_home,
          model_preset = excluded.model_preset,
          model_string = excluded.model_string,
          channels_json = excluded.channels_json,
          allowed_mcps_json = excluded.allowed_mcps_json,
          home_channel_json = excluded.home_channel_json,
          operator_notify_channel_json = excluded.operator_notify_channel_json,
          last_enrolled_at = excluded.last_enrolled_at
        """,
        (
            agent_id,
            role,
            unix_user,
            display_name,
            hermes_home,
            str(_manifest_path_for(cfg, agent_id, role)),
            model_preset,
            model_string,
            json_dumps(channels_value),
            json_dumps(allowed_mcps),
            json_dumps(home_channel or {}),
            json_dumps(operator_notify_channel or {}),
            now_iso,
            now_iso,
        ),
    )
    conn.commit()

    if role == "user":
        ensure_agent_identity_for_user(
            conn,
            agent_id=agent_id,
            unix_user=unix_user,
            human_display_name=display_name,
            agent_name="",
        )
        ensure_default_subscriptions(conn, agent_id)
    subscriptions = subscriptions_for_agent(conn, agent_id)

    # home_channel resolution: explicit arg wins. Otherwise infer from the first
    # non-tui channel; if only tui-only is enabled, treat TUI as the home channel.
    resolved_home_channel: dict[str, Any] = dict(home_channel or {}) if home_channel else {}
    if not resolved_home_channel:
        non_tui = [c for c in channels_value if c and c != "tui-only"]
        if non_tui:
            resolved_home_channel = {"platform": non_tui[0], "channel_id": ""}
        else:
            resolved_home_channel = {"platform": "tui", "channel_id": ""}

    conn.execute(
        "UPDATE agents SET home_channel_json = ? WHERE agent_id = ?",
        (json_dumps(resolved_home_channel), agent_id),
    )
    conn.commit()

    manifest_path = write_shared_manifest(
        cfg,
        agent_id=agent_id,
        role=role,
        unix_user=unix_user,
        display_name=display_name,
        hermes_home=hermes_home,
        model_preset=model_preset,
        model_string=model_string,
        channels=channels_value,
        allowed_mcps=allowed_mcps,
        subscriptions=subscriptions,
        home_channel=resolved_home_channel,
        operator_notify_channel=operator_notify_channel,
    )
    conn.execute("UPDATE agents SET manifest_path = ? WHERE agent_id = ?", (str(manifest_path), agent_id))
    conn.commit()

    # Trigger initial Curator brief fanout so the Curator knows a new agent wants briefs.
    if role == "user":
        queue_notification(
            conn,
            target_kind="curator",
            target_id=agent_id,
            channel_kind="brief-fanout",
            message=(
                f"new user agent enrolled: {agent_id} ({display_name}). "
                f"Subscriptions: {','.join(s['vault_name'] for s in subscriptions if int(s.get('subscribed') or 0))}"
            ),
        )

    return {
        "agent_id": agent_id,
        "manifest_path": str(manifest_path),
        "allowed_mcps": allowed_mcps,
        "subscriptions": subscriptions,
        "home_channel": resolved_home_channel,
    }


def get_agent(conn: sqlite3.Connection, target: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM agents
        WHERE agent_id = ? OR unix_user = ?
        ORDER BY last_enrolled_at DESC
        LIMIT 1
        """,
        (target, target),
    ).fetchone()
    return dict(row) if row else None


def update_agent_channels(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    agent_id: str,
    channels: list[str],
    home_channel: dict[str, Any] | None = None,
    display_name: str | None = None,
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM agents WHERE agent_id = ?",
        (agent_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown agent: {agent_id}")

    channels_value = _channels_payload(channels)
    resolved_home_channel = dict(home_channel or {})
    if not resolved_home_channel:
        non_tui = [channel for channel in channels_value if channel != "tui-only"]
        if non_tui:
            resolved_home_channel = {"platform": non_tui[0], "channel_id": ""}
        else:
            resolved_home_channel = {"platform": "tui", "channel_id": ""}
    resolved_display_name = str(display_name or row["display_name"]).strip() or str(row["display_name"])

    conn.execute(
        """
        UPDATE agents
        SET channels_json = ?, home_channel_json = ?, display_name = ?
        WHERE agent_id = ?
        """,
        (json_dumps(channels_value), json_dumps(resolved_home_channel), resolved_display_name, agent_id),
    )
    conn.commit()

    subscriptions = subscriptions_for_agent(conn, agent_id)
    manifest_path = write_shared_manifest(
        cfg,
        agent_id=agent_id,
        role=str(row["role"]),
        unix_user=str(row["unix_user"]),
        display_name=resolved_display_name,
        hermes_home=str(row["hermes_home"]),
        model_preset=str(row["model_preset"] or ""),
        model_string=str(row["model_string"] or ""),
        channels=channels_value,
        allowed_mcps=json_loads(str(row["allowed_mcps_json"] or ""), []),
        subscriptions=subscriptions,
        home_channel=resolved_home_channel,
        operator_notify_channel=json_loads(str(row["operator_notify_channel_json"] or ""), {}),
    )
    conn.execute(
        "UPDATE agents SET manifest_path = ? WHERE agent_id = ?",
        (str(manifest_path), agent_id),
    )
    conn.commit()
    if str(row["role"]) == "user":
        ensure_agent_identity_for_user(
            conn,
            agent_id=agent_id,
            unix_user=str(row["unix_user"]),
            agent_name=resolved_display_name,
        )
    return get_agent(conn, agent_id) or {}


def update_agent_display_name(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    agent_id: str,
    display_name: str,
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM agents WHERE agent_id = ?",
        (agent_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown agent: {agent_id}")

    resolved_display_name = str(display_name or "").strip() or str(row["display_name"])
    conn.execute(
        "UPDATE agents SET display_name = ? WHERE agent_id = ?",
        (resolved_display_name, agent_id),
    )
    conn.commit()

    subscriptions = subscriptions_for_agent(conn, agent_id)
    manifest_path = write_shared_manifest(
        cfg,
        agent_id=agent_id,
        role=str(row["role"]),
        unix_user=str(row["unix_user"]),
        display_name=resolved_display_name,
        hermes_home=str(row["hermes_home"]),
        model_preset=str(row["model_preset"] or ""),
        model_string=str(row["model_string"] or ""),
        channels=json_loads(str(row["channels_json"] or ""), []),
        allowed_mcps=json_loads(str(row["allowed_mcps_json"] or ""), []),
        subscriptions=subscriptions,
        home_channel=json_loads(str(row["home_channel_json"] or ""), {}),
        operator_notify_channel=json_loads(str(row["operator_notify_channel_json"] or ""), {}),
    )
    conn.execute(
        "UPDATE agents SET manifest_path = ? WHERE agent_id = ?",
        (str(manifest_path), agent_id),
    )
    conn.commit()
    if str(row["role"]) == "user":
        ensure_agent_identity_for_user(
            conn,
            agent_id=agent_id,
            unix_user=str(row["unix_user"]),
            agent_name=resolved_display_name,
        )
    return get_agent(conn, agent_id) or {}


def list_agents(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM agents ORDER BY role, unix_user").fetchall()
    return [dict(row) for row in rows]


def list_tokens(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT token_id, agent_id, requester_identity, source_ip, issued_at, issued_by,
               activation_request_id, activated_at,
               revoked_at, revoked_by_surface, revoked_by_actor, revocation_reason
        FROM bootstrap_tokens
        ORDER BY issued_at DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def note_refresh_job(
    conn: sqlite3.Connection,
    *,
    job_name: str,
    job_kind: str,
    target_id: str,
    schedule: str,
    status: str,
    note: str,
) -> None:
    conn.execute(
        """
        INSERT INTO refresh_jobs (job_name, job_kind, target_id, schedule, last_run_at, last_status, last_note)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(job_name) DO UPDATE SET
          target_id = excluded.target_id,
          schedule = excluded.schedule,
          last_run_at = excluded.last_run_at,
          last_status = excluded.last_status,
          last_note = excluded.last_note
        """,
        (job_name, job_kind, target_id, schedule, utc_now_iso(), status, note),
    )
    conn.commit()


def refresh_agent_context(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    raw_token: str,
) -> dict[str, Any]:
    token_row = validate_token(conn, raw_token)
    agent_id = str(token_row["agent_id"])
    ensure_default_subscriptions(conn, agent_id)
    subscriptions = subscriptions_for_agent(conn, agent_id)
    active = [row["vault_name"] for row in subscriptions if int(row["subscribed"]) == 1]
    note_refresh_job(
        conn,
        job_name=f"{agent_id}-refresh",
        job_kind="agent-refresh",
        target_id=agent_id,
        schedule="every 4h",
        status="ok",
        note=f"active subscriptions: {', '.join(active) if active else 'none'}",
    )
    return {
        "agent_id": agent_id,
        "active_subscriptions": active,
        "subscriptions": subscriptions,
        "qmd_url": cfg.qmd_url,
    }


def subscription_catalog(conn: sqlite3.Connection, raw_token: str) -> list[dict[str, Any]]:
    token_row = validate_token(conn, raw_token)
    agent_id = str(token_row["agent_id"])
    subscriptions = {
        row["vault_name"]: bool(row["subscribed"])
        for row in conn.execute(
            "SELECT vault_name, subscribed FROM agent_vault_subscriptions WHERE agent_id = ?",
            (agent_id,),
        )
    }
    result = []
    for row in list_vaults(conn):
        result.append(
            {
                "vault_name": row["vault_name"],
                "vault_path": row["vault_path"],
                "description": row.get("description"),
                "owner": row.get("owner"),
                "default_subscribed": bool(row.get("default_subscribed", 0)),
                "subscribed": subscriptions.get(row["vault_name"], False),
            }
        )
    return result


def set_subscription_from_token(
    conn: sqlite3.Connection,
    *,
    raw_token: str,
    vault_name: str,
    subscribed: bool,
) -> dict[str, Any]:
    token_row = validate_token(conn, raw_token)
    return set_vault_subscription(
        conn,
        agent_id=str(token_row["agent_id"]),
        vault_name=vault_name,
        subscribed=subscribed,
        source="user",
    )


def archive_agent_files(
    cfg: Config,
    *,
    agent_id: str,
    unix_user: str,
    hermes_home: str,
) -> Path:
    timestamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    archive_dir = cfg.archived_agents_dir / agent_id / timestamp
    archive_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = _manifest_path_for(cfg, agent_id, "user")
    if manifest_path.exists():
        subprocess.run(["cp", "-a", str(manifest_path), str(archive_dir / "manifest.json")], check=True)

    user_unit_dir = Path(f"/home/{unix_user}/.config/systemd/user")
    if user_unit_dir.exists():
        archive_unit_dir = archive_dir / "systemd-user"
        archive_unit_dir.mkdir(parents=True, exist_ok=True)
        for path in user_unit_dir.glob("almanac-user-agent*"):
            subprocess.run(["cp", "-a", str(path), str(archive_unit_dir / path.name)], check=True)

    hermes_home_path = Path(hermes_home)
    if hermes_home_path.exists():
        subprocess.run(["cp", "-a", str(hermes_home_path), str(archive_dir / "hermes-home")], check=True)

    return archive_dir


def mark_agent_deenrolled(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    archive_path: str,
) -> None:
    conn.execute(
        """
        UPDATE agents
        SET status = 'deenrolled', archived_state_path = ?
        WHERE agent_id = ?
        """,
        (archive_path, agent_id),
    )
    conn.commit()


def notion_verify_signature(raw_body: bytes, header_value: str, verification_token: str) -> bool:
    expected = "sha256=" + hmac.new(
        verification_token.encode("utf-8"),
        raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, header_value or "")


def store_notion_event(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO notion_webhook_events (event_id, event_type, payload_json, received_at)
        VALUES (?, ?, ?, ?)
        """,
        (event_id, event_type, json_dumps(payload), utc_now_iso()),
    )
    conn.commit()


SSOT_READ_OPERATIONS = ("read",)
SSOT_WRITE_OPERATIONS = ("insert", "update")
SSOT_ALLOWED_OPERATIONS = SSOT_READ_OPERATIONS + SSOT_WRITE_OPERATIONS
SSOT_FORBIDDEN_OPERATIONS = ("archive", "delete", "trash", "destroy")
NOTION_WEBHOOK_EVENT_MAX_ATTEMPTS = 10


def _notion_candidate_values(raw_value: Any) -> list[str]:
    values: list[str] = []
    if isinstance(raw_value, dict):
        nested_person = raw_value.get("person")
        if isinstance(nested_person, dict):
            email = _normalize_email(str(nested_person.get("email") or ""))
            if email:
                values.append(email)
        for key in ("id", "email"):
            value = raw_value.get(key)
            if isinstance(value, str) and value.strip():
                values.append(_normalize_email(value) if key == "email" else value.strip())
    elif isinstance(raw_value, str) and raw_value.strip():
        normalized = raw_value.strip()
        if "@" in normalized:
            values.append(_normalize_email(normalized))
        elif re.fullmatch(r"[0-9a-fA-F-]{32,36}", normalized):
            values.append(normalized)
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        marker = value.lower()
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(value)
    return deduped


def _notion_property_people_identities(payload: dict[str, Any], property_name: str) -> list[tuple[str, str]]:
    properties = payload.get("properties") or {}
    prop = properties.get(property_name) if isinstance(properties, dict) else None
    if not isinstance(prop, dict):
        return []
    candidates: list[tuple[str, str]] = []
    people = prop.get("people") or []
    if isinstance(people, list):
        for person in people:
            for value in _notion_candidate_values(person):
                candidates.append((value, f"{property_name.lower()}-property"))
    for value in _notion_candidate_values(prop):
        candidates.append((value, f"{property_name.lower()}-property"))
    return candidates


def _notion_principal_identities(payload: dict[str, Any]) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    for property_name in ("Owner", "Assignee"):
        candidates.extend(_notion_property_people_identities(payload, property_name))
    for field_name in ("created_by", "last_edited_by"):
        raw_value = payload.get(field_name)
        for value in _notion_candidate_values(raw_value):
            candidates.append((value, field_name.replace("_", "-")))
    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for value, source in candidates:
        marker = (value.lower(), source)
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append((value, source))
    return deduped


def _notion_owner_identity(payload: dict[str, Any]) -> tuple[str, str]:
    """Return (owner_identity, resolution_source) following the spec precedence:
    explicit Owner property -> created_by -> ('', 'needs-approval').
    """
    for value, source in _notion_property_people_identities(payload, "Owner"):
        return value, source
    created_by = payload.get("created_by") or {}
    for value in _notion_candidate_values(created_by):
        return value, "created-by"
    return "", "needs-approval"


def _notion_identity_override_values(override: dict[str, Any] | None) -> set[str]:
    if not isinstance(override, dict):
        return set()
    values = {
        _normalize_email(str(override.get("notion_user_email") or "")),
        str(override.get("notion_user_id") or "").strip(),
    }
    return {value for value in values if value}


def _ssot_identity_match_values(agent_row: sqlite3.Row, identity: dict[str, Any]) -> set[str]:
    _ = agent_row
    values = {
        _normalize_email(str(identity.get("notion_user_email") or "")),
        str(identity.get("notion_user_id") or "").strip(),
    }
    values.update(_notion_identity_override_values(identity.get("override")))
    return {value for value in values if value}


def _page_access_matches_identity(
    payload: dict[str, Any],
    *,
    agent_row: sqlite3.Row,
    identity: dict[str, Any],
) -> tuple[bool, str]:
    match_values = {value.lower() for value in _ssot_identity_match_values(agent_row, identity)}
    for value, source in _notion_principal_identities(payload):
        normalized = _normalize_email(value) if "@" in value else value.strip().lower()
        if normalized in match_values:
            return True, source
    return False, "ownership-mismatch"


def _insert_payload_targets_verified_identity(payload: dict[str, Any], identity: dict[str, Any]) -> tuple[bool, str]:
    match_values = {
        str(value).strip().lower()
        for value in {
            str(identity.get("notion_user_id") or "").strip(),
            _normalize_email(str(identity.get("notion_user_email") or "")),
            *_notion_identity_override_values(identity.get("override")),
        }
        if str(value).strip()
    }
    match_values = {value for value in match_values if value}
    if not match_values:
        return False, "verified-identity-missing"
    for value, source in _notion_principal_identities(payload):
        normalized = _normalize_email(value) if "@" in value else value.strip().lower()
        if normalized in match_values:
            return True, source
    return False, "insert-missing-verified-owner"


def _find_agent_for_owner(conn: sqlite3.Connection, owner_identity: str) -> dict[str, Any] | None:
    if not owner_identity:
        return None
    normalized_owner = owner_identity.strip()
    normalized_email = _normalize_email(owner_identity)
    identity_row = conn.execute(
        """
        SELECT agent_id, unix_user, human_display_name AS display_name
        FROM agent_identity
        WHERE agent_id = ?
           OR notion_user_id = ?
           OR LOWER(notion_user_email) = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (
            normalized_owner,
            normalized_owner,
            normalized_email,
        ),
    ).fetchone()
    if identity_row is not None:
        return dict(identity_row)
    override_row = conn.execute(
        """
        SELECT agent_id, unix_user
        FROM notion_identity_overrides
        WHERE notion_user_id = ?
           OR LOWER(notion_user_email) = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (
            normalized_owner,
            normalized_email,
        ),
    ).fetchone()
    if override_row is not None:
        agent_row = conn.execute(
            """
            SELECT agent_id, unix_user, display_name
            FROM agents
            WHERE agent_id = ?
            LIMIT 1
            """,
            (str(override_row["agent_id"]),),
        ).fetchone()
        if agent_row is not None:
            return dict(agent_row)
    return None


def _notion_event_entity_ref(payload: dict[str, Any]) -> tuple[str, str]:
    entity = payload.get("entity")
    if not isinstance(entity, dict):
        return "", ""
    entity_id = str(entity.get("id") or "").strip()
    entity_type = str(entity.get("type") or entity.get("object") or "").strip().lower()
    return entity_id, entity_type


def _hydrate_notion_event_entity(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    entity_id, entity_type = _notion_event_entity_ref(payload)
    if not entity_id:
        return {}, True
    try:
        settings = _require_shared_notion_settings()
    except PermissionError:
        return {}, False
    try:
        if entity_type == "page":
            return (
                retrieve_notion_page(
                    page_id=entity_id,
                    token=settings["token"],
                    api_version=settings["api_version"],
                ),
                True,
            )
        if entity_type == "database":
            return (
                retrieve_notion_database(
                    database_id=entity_id,
                    token=settings["token"],
                    api_version=settings["api_version"],
                ),
                True,
            )
        target_meta = resolve_notion_target(
            target_id=entity_id,
            token=settings["token"],
            api_version=settings["api_version"],
        )
        if str(target_meta.get("kind") or "").strip() == "page":
            return (
                retrieve_notion_page(
                    page_id=entity_id,
                    token=settings["token"],
                    api_version=settings["api_version"],
                ),
                True,
            )
        if str(target_meta.get("kind") or "").strip() == "database":
            return (
                retrieve_notion_database(
                    database_id=entity_id,
                    token=settings["token"],
                    api_version=settings["api_version"],
                ),
                True,
            )
    except Exception:
        return {}, False
    return {}, True


def _record_notion_event_retry(
    conn: sqlite3.Connection,
    *,
    row_id: int,
    error_message: str,
) -> str:
    now_iso = utc_now_iso()
    row = conn.execute(
        "SELECT attempt_count FROM notion_webhook_events WHERE id = ?",
        (row_id,),
    ).fetchone()
    attempt_count = int(row["attempt_count"] if row is not None else 0) + 1
    status = "failed" if attempt_count >= NOTION_WEBHOOK_EVENT_MAX_ATTEMPTS else "pending"
    conn.execute(
        """
        UPDATE notion_webhook_events
        SET attempt_count = ?,
            last_attempt_at = ?,
            last_error = ?,
            batch_status = ?,
            processed_at = CASE WHEN ? = 'failed' THEN ? ELSE processed_at END
        WHERE id = ?
        """,
        (
            attempt_count,
            now_iso,
            str(error_message or "").strip()[:500],
            status,
            status,
            now_iso,
            row_id,
        ),
    )
    return status


def _active_user_agent_row(conn: sqlite3.Connection, agent_id: str) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT agent_id, unix_user, display_name, role, status
        FROM agents
        WHERE agent_id = ?
        """,
        (agent_id,),
    ).fetchone()
    if row is None or str(row["status"] or "") != "active" or str(row["role"] or "") != "user":
        raise PermissionError("agent is not active")
    return row


def _ssot_principal(conn: sqlite3.Connection, agent_id: str) -> tuple[sqlite3.Row, dict[str, Any]]:
    agent_row = _active_user_agent_row(conn, agent_id)
    try:
        identity = get_agent_identity(conn, agent_id=agent_id, unix_user=str(agent_row["unix_user"]))
        if identity is None:
            identity = ensure_agent_identity_for_user(
                conn,
                agent_id=str(agent_row["agent_id"]),
                unix_user=str(agent_row["unix_user"]),
                human_display_name=str(agent_row["display_name"] or ""),
            )
    except sqlite3.Error as exc:
        raise PermissionError("shared Notion identity registry is unavailable") from exc
    override = get_notion_identity_override(
        conn,
        agent_id=str(agent_row["agent_id"]),
        unix_user=str(agent_row["unix_user"]),
    )
    if override is not None:
        identity = dict(identity)
        identity["override"] = override
    if str(identity.get("suspended_at") or "").strip():
        raise PermissionError("shared Notion access is suspended for this identity")
    return agent_row, identity


def _log_ssot_principal_denial(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    operation: str,
    target_id: str,
    actor: str,
    reason: str,
    request_payload: dict[str, Any],
) -> None:
    try:
        agent_row = _active_user_agent_row(conn, agent_id)
    except PermissionError:
        return
    notion_user_id = ""
    try:
        identity = get_agent_identity(conn, agent_id=agent_id, unix_user=str(agent_row["unix_user"])) or {}
        notion_user_id = str(identity.get("notion_user_id") or "")
    except sqlite3.Error:
        notion_user_id = ""
    log_ssot_access_audit(
        conn,
        agent_id=str(agent_row["agent_id"]),
        unix_user=str(agent_row["unix_user"]),
        notion_user_id=notion_user_id,
        operation=operation,
        target_id=target_id,
        decision="deny",
        reason=reason,
        actor=actor,
        request_payload=request_payload,
    )


def _shared_notion_settings() -> dict[str, str]:
    space_url = str(config_env_value("ALMANAC_SSOT_NOTION_SPACE_URL", "")).strip()
    space_id = str(config_env_value("ALMANAC_SSOT_NOTION_SPACE_ID", "")).strip()
    space_kind = str(config_env_value("ALMANAC_SSOT_NOTION_SPACE_KIND", "")).strip()
    root_page_url = str(config_env_value("ALMANAC_SSOT_NOTION_ROOT_PAGE_URL", "")).strip()
    root_page_id = str(config_env_value("ALMANAC_SSOT_NOTION_ROOT_PAGE_ID", "")).strip()
    if not root_page_id and space_kind == "page":
        root_page_id = space_id
    if not root_page_url and space_kind == "page":
        root_page_url = space_url
    return {
        "space_url": space_url,
        "space_id": space_id,
        "space_kind": space_kind,
        "root_page_url": root_page_url,
        "root_page_id": root_page_id,
        "token": str(config_env_value("ALMANAC_SSOT_NOTION_TOKEN", "")).strip(),
        "api_version": str(
            config_env_value("ALMANAC_SSOT_NOTION_API_VERSION", DEFAULT_NOTION_API_VERSION)
        ).strip()
        or DEFAULT_NOTION_API_VERSION,
    }


def _require_shared_notion_settings() -> dict[str, str]:
    settings = _shared_notion_settings()
    if not settings["token"]:
        raise PermissionError("shared Notion SSOT is not configured with an integration secret")
    if not settings["space_id"]:
        raise PermissionError("shared Notion SSOT target is not configured")
    return settings


def _load_notion_collection_schema(
    *,
    target_id: str,
    settings: dict[str, str],
    notion_kwargs: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    kwargs = notion_kwargs or {}
    database_payload = retrieve_notion_database(
        database_id=target_id,
        token=settings["token"],
        api_version=settings["api_version"],
        **kwargs,
    )
    properties = database_payload.get("properties")
    if isinstance(properties, dict) and properties:
        return database_payload, {}
    data_sources = database_payload.get("data_sources") if isinstance(database_payload, dict) else None
    if isinstance(data_sources, list) and data_sources:
        first = data_sources[0] if isinstance(data_sources[0], dict) else {}
        data_source_id = str(first.get("id") or "").strip()
        if data_source_id:
            data_source_payload = retrieve_notion_data_source(
                data_source_id=data_source_id,
                token=settings["token"],
                api_version=settings["api_version"],
                **kwargs,
            )
            return database_payload, data_source_payload
    return database_payload, {}


def _configured_people_properties(schema_payload: dict[str, Any]) -> list[str]:
    properties = schema_payload.get("properties")
    if not isinstance(properties, dict):
        return []
    names: list[str] = []
    for property_name in ("Owner", "Assignee"):
        prop = properties.get(property_name)
        if isinstance(prop, dict) and str(prop.get("type") or "").strip() == "people":
            names.append(property_name)
    return names


def _configured_changed_by_property(schema_payload: dict[str, Any]) -> str:
    properties = schema_payload.get("properties")
    if not isinstance(properties, dict):
        return ""
    prop = properties.get("Changed By")
    if isinstance(prop, dict) and str(prop.get("type") or "").strip() == "people":
        return "Changed By"
    return ""


def _stamp_changed_by_property(
    payload: dict[str, Any],
    *,
    schema_payload: dict[str, Any],
    notion_user_id: str,
) -> tuple[dict[str, Any], str]:
    property_name = _configured_changed_by_property(schema_payload)
    if not property_name or not notion_user_id:
        return dict(payload or {}), ""
    stamped_payload = dict(payload or {})
    properties = stamped_payload.get("properties")
    if not isinstance(properties, dict):
        properties = {}
    else:
        properties = dict(properties)
    properties[property_name] = {
        "people": [
            {
                "object": "user",
                "id": notion_user_id,
            }
        ]
    }
    stamped_payload["properties"] = properties
    return stamped_payload, property_name


def _strip_attribution_properties(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(payload or {})
    properties = sanitized.get("properties")
    if not isinstance(properties, dict):
        return sanitized
    cleaned = dict(properties)
    # Strip the canonical field plus older synonym names so caller-supplied
    # attribution cannot survive schema drift or legacy database templates.
    for property_name in ("Changed By", "Author", "Requested By"):
        cleaned.pop(property_name, None)
    sanitized["properties"] = cleaned
    return sanitized


def _identity_people_filter(database_payload: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
    notion_user_id = str(identity.get("notion_user_id") or "").strip()
    if not notion_user_id:
        raise PermissionError("shared Notion database queries require a verified Notion user claim")
    property_names = _configured_people_properties(database_payload)
    if not property_names:
        raise PermissionError(
            "shared Notion SSOT must expose Owner and/or Assignee people properties for user-scoped reads"
        )
    filters = [
        {"property": property_name, "people": {"contains": notion_user_id}}
        for property_name in property_names
    ]
    if len(filters) == 1:
        return filters[0]
    return {"or": filters}


def _combine_notion_filters(required_filter: dict[str, Any], requested_filter: dict[str, Any] | None) -> dict[str, Any]:
    if not requested_filter:
        return required_filter
    return {"and": [required_filter, requested_filter]}


def _notion_title_from_page(payload: dict[str, Any]) -> str:
    properties = payload.get("properties")
    if not isinstance(properties, dict):
        return ""
    for prop in properties.values():
        if not isinstance(prop, dict):
            continue
        if str(prop.get("type") or "").strip() != "title":
            continue
        title = prop.get("title")
        if not isinstance(title, list):
            continue
        parts = [str(item.get("plain_text") or "").strip() for item in title if isinstance(item, dict)]
        text = "".join(parts).strip()
        if text:
            return text
    return ""


def _notion_date_property(payload: dict[str, Any]) -> str:
    properties = payload.get("properties")
    if not isinstance(properties, dict):
        return ""
    preferred_names = ("Due", "Deadline", "Target Date")
    for property_name in preferred_names:
        prop = properties.get(property_name)
        if isinstance(prop, dict) and str(prop.get("type") or "").strip() == "date":
            date_payload = prop.get("date")
            if isinstance(date_payload, dict):
                return str(date_payload.get("start") or "").strip()
    for prop in properties.values():
        if not isinstance(prop, dict) or str(prop.get("type") or "").strip() != "date":
            continue
        date_payload = prop.get("date")
        if isinstance(date_payload, dict):
            return str(date_payload.get("start") or "").strip()
    return ""


def _notion_people_names(payload: dict[str, Any], property_name: str) -> list[str]:
    properties = payload.get("properties")
    prop = properties.get(property_name) if isinstance(properties, dict) else None
    if not isinstance(prop, dict):
        return []
    people = prop.get("people")
    if not isinstance(people, list):
        return []
    names: list[str] = []
    seen: set[str] = set()
    for person in people:
        if not isinstance(person, dict):
            continue
        name = str(person.get("name") or "").strip()
        if not name:
            person_meta = person.get("person")
            if isinstance(person_meta, dict):
                name = str(person_meta.get("email") or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def _notion_due_within_days(date_value: str, days: int) -> bool:
    compact = str(date_value or "").strip()
    if not compact:
        return False
    try:
        due_date = dt.date.fromisoformat(compact[:10])
    except ValueError:
        return False
    today = utc_now().date()
    return today <= due_date <= (today + dt.timedelta(days=days))


def _notion_recently_updated(payload: dict[str, Any], *, days: int) -> bool:
    compact = str(payload.get("last_edited_time") or "").strip()
    if not compact:
        return False
    try:
        updated = dt.datetime.fromisoformat(compact.replace("Z", "+00:00"))
    except ValueError:
        return False
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=dt.timezone.utc)
    return updated >= utc_now() - dt.timedelta(days=days)


def _notion_team_summary(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["- Team snapshot: no shared SSOT records were visible during the last Curator refresh."]
    owner_counts: dict[str, int] = {}
    due_soon = 0
    recent_updates = 0
    for item in items:
        owners = _notion_people_names(item, "Owner") or _notion_people_names(item, "Assignee")
        owner_label = owners[0] if owners else "Unassigned"
        owner_counts[owner_label] = owner_counts.get(owner_label, 0) + 1
        if _notion_due_within_days(_notion_date_property(item), 7):
            due_soon += 1
        if _notion_recently_updated(item, days=7):
            recent_updates += 1
    load_buckets: dict[int, int] = {}
    for count in owner_counts.values():
        load_buckets[count] = load_buckets.get(count, 0) + 1
    top_loads = sorted(load_buckets.items(), key=lambda item: (-item[0], -item[1]))[:3]
    load_text = (
        ", ".join(f"{owners} owner(s) at {count} record(s)" for count, owners in top_loads)
        if top_loads
        else "none yet"
    )
    return [
        f"- Team snapshot (Curator aggregate, not raw cross-user pages): {len(items)} visible shared SSOT record(s).",
        f"- Recently updated in the last 7 days: {recent_updates}. Due within 7 days: {due_soon}.",
        f"- Largest current owner loads: {load_text}.",
    ]


def _build_notion_stub(
    conn: sqlite3.Connection,
    *,
    agent_row: sqlite3.Row,
    identity: dict[str, Any] | None,
) -> str:
    try:
        settings = _require_shared_notion_settings()
    except PermissionError as exc:
        return f"Shared Notion digest:\n- Shared organizational Notion is not configured on this host yet ({exc})."
    verification_status = str((identity or {}).get("verification_status") or "").strip()
    verified_email = str((identity or {}).get("notion_user_email") or (identity or {}).get("claimed_notion_email") or "").strip()
    claimed_email = _normalize_email(str((identity or {}).get("claimed_notion_email") or ""))
    if settings["space_kind"] != "database":
        lines = [
            "Shared Notion digest:",
            "- The shared SSOT target is page-scoped right now, so Almanac cannot build a structured database digest yet.",
            "- Shared organizational writes still stay on the brokered ssot.write rail for concrete user-scoped page work.",
            "- Use ssot.read for specific page lookups.",
        ]
        if verification_status != "verified":
            if claimed_email:
                lines.append(f"- Verification: pending for {claimed_email}. Shared writes remain read-only until the claim is verified.")
            else:
                lines.append("- Verification: not started yet. Shared writes remain read-only until the user verifies their Notion identity.")
        else:
            lines.append(f"- Verification: confirmed for {verified_email or 'your verified Notion identity'}. Shared brokered writes are enabled within your scoped rails.")
        return "\n".join(lines)
    notion_kwargs: dict[str, Any] = {}
    try:
        database_payload, schema_payload = _load_notion_collection_schema(
            target_id=settings["space_id"],
            settings=settings,
            notion_kwargs=notion_kwargs,
        )
        schema = schema_payload or database_payload
        team_result = query_notion_collection(
            database_id=settings["space_id"],
            token=settings["token"],
            api_version=settings["api_version"],
            payload={"page_size": 100},
            **notion_kwargs,
        )
    except Exception as exc:
        return f"Shared Notion digest:\n- Curator could not refresh the shared Notion snapshot just now ({exc})."
    entries = team_result.get("result") if isinstance(team_result, dict) else {}
    items_raw = entries.get("results") if isinstance(entries, dict) else []
    team_items = [item for item in items_raw if isinstance(item, dict)]
    lines = [
        "Shared Notion digest:",
        "- Shared organizational writes stay on the brokered ssot.write rail.",
        "- Native Notion edit history shows the Almanac integration. When the database exposes a Changed By people property, Almanac also stamps the verified human there on every brokered write.",
    ]
    if identity is None or verification_status != "verified":
        if claimed_email:
            lines.append(f"- Verification: pending for {claimed_email}. Shared writes remain read-only until the claim is verified.")
        else:
            lines.append("- Verification: not started yet. Shared writes remain read-only until the user verifies their Notion identity.")
        lines.extend(_notion_team_summary(team_items))
        return "\n".join(lines)
    try:
        scoped_result = query_notion_collection(
            database_id=settings["space_id"],
            token=settings["token"],
            api_version=settings["api_version"],
            payload={
                "page_size": 25,
                "filter": _identity_people_filter(schema, identity),
            },
            **notion_kwargs,
        )
        scoped_entries = scoped_result.get("result") if isinstance(scoped_result, dict) else {}
        scoped_items = scoped_entries.get("results") if isinstance(scoped_entries, dict) else []
        user_items = [
            item
            for item in scoped_items if isinstance(item, dict) and _page_access_matches_identity(item, agent_row=agent_row, identity=identity)[0]
        ]
    except Exception as exc:
        lines.append(f"- Verification: confirmed, but Curator could not refresh your scoped Notion digest right now ({exc}).")
        lines.extend(_notion_team_summary(team_items))
        return "\n".join(lines)
    due_soon = sum(1 for item in user_items if _notion_due_within_days(_notion_date_property(item), 7))
    recent_updates = sum(1 for item in user_items if _notion_recently_updated(item, days=7))
    lines.append(
        f"- Verification: confirmed for {verified_email}."
    )
    lines.append(f"- My scoped SSOT records: {len(user_items)}. Due within 7 days: {due_soon}. Updated in the last 7 days: {recent_updates}.")
    if user_items:
        lines.append("- Current focus rows:")
        for item in user_items[:5]:
            title = _notion_title_from_page(item) or str(item.get("id") or "untitled")
            due_text = _notion_date_property(item)
            suffix = f" (due {due_text[:10]})" if due_text else ""
            lines.append(f"  - {title}{suffix}")
    else:
        lines.append("- Current focus rows: none were scoped to you on the last Curator refresh.")
    lines.extend(_notion_team_summary(team_items))
    return "\n".join(lines)


def read_ssot(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    agent_id: str,
    target_id: str,
    query: dict[str, Any] | None = None,
    include_markdown: bool = False,
    requested_by_actor: str,
    urlopen_fn=None,
) -> dict[str, Any]:
    settings = _require_shared_notion_settings()
    notion_target = str(target_id or settings["space_id"]).strip()
    target_uuid = extract_notion_space_id(notion_target)
    audit_payload = {"target_id": target_uuid, "query": query or {}, "include_markdown": bool(include_markdown)}
    notion_kwargs: dict[str, Any] = {}
    if urlopen_fn is not None:
        notion_kwargs["urlopen_fn"] = urlopen_fn
    try:
        agent_row, identity = _ssot_principal(conn, agent_id)
    except PermissionError as exc:
        _log_ssot_principal_denial(
            conn,
            agent_id=agent_id,
            operation="read",
            target_id=target_uuid,
            actor=requested_by_actor,
            reason=str(exc),
            request_payload=audit_payload,
        )
        raise

    if target_uuid == settings["space_id"] and settings["space_kind"] == "database":
        if str(identity.get("verification_status") or "").strip() != "verified":
            reason = "database reads require verified Notion ownership"
            log_ssot_access_audit(
                conn,
                agent_id=str(agent_row["agent_id"]),
                unix_user=str(agent_row["unix_user"]),
                notion_user_id=str(identity.get("notion_user_id") or ""),
                operation="read",
                target_id=target_uuid,
                decision="deny",
                reason=reason,
                actor=requested_by_actor,
                request_payload=audit_payload,
            )
            raise PermissionError(reason)
        database_payload, schema_payload = _load_notion_collection_schema(
            target_id=target_uuid,
            settings=settings,
            notion_kwargs=notion_kwargs,
        )
        requested_query = dict(query or {})
        result = query_notion_collection(
            database_id=target_uuid,
            token=settings["token"],
            api_version=settings["api_version"],
            payload={
                **requested_query,
                "filter": _combine_notion_filters(
                    _identity_people_filter(schema_payload or database_payload, identity),
                    requested_query.get("filter") if isinstance(requested_query, dict) else None,
                ),
            },
            **notion_kwargs,
        )
        entries = result.get("result") if isinstance(result, dict) else {}
        items = entries.get("results") if isinstance(entries, dict) else []
        filtered_items = []
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict):
                allowed, _ = _page_access_matches_identity(item, agent_row=agent_row, identity=identity)
                if allowed:
                    filtered_items.append(item)
        log_ssot_access_audit(
            conn,
            agent_id=str(agent_row["agent_id"]),
            unix_user=str(agent_row["unix_user"]),
            notion_user_id=str(identity.get("notion_user_id") or ""),
            operation="read",
            target_id=target_uuid,
            decision="allow",
            reason=f"database scoped read returned {len(filtered_items)} item(s)",
            actor=requested_by_actor,
            request_payload=audit_payload,
        )
        return {
            "target_id": target_uuid,
            "target_kind": "database",
            "query_kind": result.get("query_kind") if isinstance(result, dict) else "",
            "data_source_id": result.get("data_source_id") if isinstance(result, dict) else "",
            "database": result.get("database") if isinstance(result, dict) else {},
            "results": filtered_items,
            "has_more": bool(entries.get("has_more")) if isinstance(entries, dict) else False,
            "next_cursor": str(entries.get("next_cursor") or "") if isinstance(entries, dict) else "",
        }

    target_meta = resolve_notion_target(
        target_id=target_uuid,
        token=settings["token"],
        api_version=settings["api_version"],
        **notion_kwargs,
    )
    if str(target_meta.get("kind") or "") != "page":
        raise PermissionError("shared Notion database queries must target the configured shared database")
    if str(identity.get("verification_status") or "").strip() != "verified":
        reason = "page reads require verified Notion ownership"
        log_ssot_access_audit(
            conn,
            agent_id=str(agent_row["agent_id"]),
            unix_user=str(agent_row["unix_user"]),
            notion_user_id=str(identity.get("notion_user_id") or ""),
            operation="read",
            target_id=target_uuid,
            decision="deny",
            reason=reason,
            actor=requested_by_actor,
            request_payload=audit_payload,
        )
        raise PermissionError(reason)
    page = retrieve_notion_page(
        page_id=target_uuid,
        token=settings["token"],
        api_version=settings["api_version"],
        **notion_kwargs,
    )
    allowed, source = _page_access_matches_identity(page, agent_row=agent_row, identity=identity)
    if not allowed:
        reason = "page read is outside the caller's owned/assigned Notion scope"
        log_ssot_access_audit(
            conn,
            agent_id=str(agent_row["agent_id"]),
            unix_user=str(agent_row["unix_user"]),
            notion_user_id=str(identity.get("notion_user_id") or ""),
            operation="read",
            target_id=target_uuid,
            decision="deny",
            reason=reason,
            actor=requested_by_actor,
            request_payload=audit_payload,
        )
        raise PermissionError(reason)
    markdown_payload = {}
    if include_markdown:
        markdown_payload = retrieve_notion_page_markdown(
            page_id=target_uuid,
            token=settings["token"],
            api_version=settings["api_version"],
            **notion_kwargs,
        )
    log_ssot_access_audit(
        conn,
        agent_id=str(agent_row["agent_id"]),
        unix_user=str(agent_row["unix_user"]),
        notion_user_id=str(identity.get("notion_user_id") or ""),
        operation="read",
        target_id=target_uuid,
        decision="allow",
        reason=f"page scoped read via {source}",
        actor=requested_by_actor,
        request_payload=audit_payload,
    )
    return {
        "target_id": target_uuid,
        "target_kind": "page",
        "page": page,
        "markdown": markdown_payload.get("markdown") or "",
    }


def enqueue_ssot_write(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    agent_id: str,
    operation: str,
    target_id: str,
    payload: dict[str, Any],
    requested_by_actor: str,
) -> dict[str, Any]:
    """Accept insert/update only. Reject archive/delete. Apply approved writes immediately."""
    op = (operation or "").strip().lower()
    if op in SSOT_FORBIDDEN_OPERATIONS:
        raise PermissionError(
            f"SSOT rail violation: operation '{op}' is not permitted; archive/delete require operator."
        )
    if op not in SSOT_WRITE_OPERATIONS:
        raise ValueError(
            f"unsupported SSOT operation '{op}'; allowed: {', '.join(SSOT_WRITE_OPERATIONS)}"
        )

    settings = _require_shared_notion_settings()
    if op == "update" and not str(target_id or "").strip():
        raise ValueError("shared Notion updates require a target page id")
    notion_kwargs: dict[str, Any] = {}
    notion_target = str(target_id or settings["space_id"]).strip()
    normalized_target_id = extract_notion_space_id(notion_target)
    audit_payload = {"operation": op, "target_id": normalized_target_id, "payload": payload}
    try:
        agent_row, identity = _ssot_principal(conn, agent_id)
    except PermissionError as exc:
        _log_ssot_principal_denial(
            conn,
            agent_id=agent_id,
            operation=op,
            target_id=normalized_target_id,
            actor=requested_by_actor,
            reason=str(exc),
            request_payload=audit_payload,
        )
        raise
    verification_status = str(identity.get("verification_status") or "").strip()
    write_mode = str(identity.get("write_mode") or "").strip()
    if verification_status != "verified" or write_mode != "verified_limited":
        reason = "shared Notion writes require a verified Notion claim and verified_limited write mode"
        log_ssot_access_audit(
            conn,
            agent_id=str(agent_row["agent_id"]),
            unix_user=str(agent_row["unix_user"]),
            notion_user_id=str(identity.get("notion_user_id") or ""),
            operation=op,
            target_id=normalized_target_id,
            decision="deny",
            reason=reason,
            actor=requested_by_actor,
            request_payload=audit_payload,
        )
        raise PermissionError(reason)

    try:
        owner_identity, owner_source = ("", "insert")
        if op == "insert":
            approved, owner_source = _insert_payload_targets_verified_identity(payload, identity)
            owner_identity = str(identity.get("notion_user_id") or identity.get("notion_user_email") or "")
            if not approved:
                reason = "insert payload must assign Owner or Assignee to the verified caller"
                log_ssot_access_audit(
                    conn,
                    agent_id=str(agent_row["agent_id"]),
                    unix_user=str(agent_row["unix_user"]),
                    notion_user_id=str(identity.get("notion_user_id") or ""),
                    operation=op,
                    target_id=normalized_target_id,
                    decision="deny",
                    reason=reason,
                    actor=requested_by_actor,
                    request_payload=audit_payload,
                )
                raise PermissionError(reason)
            parent_meta = resolve_notion_target(
                target_id=normalized_target_id,
                token=settings["token"],
                api_version=settings["api_version"],
                **notion_kwargs,
            )
            parent_kind = str(parent_meta.get("kind") or "").strip()
            changed_by_property = ""
            applied_request_payload = _strip_attribution_properties(payload)
            if parent_kind == "database":
                database_payload, schema_payload = _load_notion_collection_schema(
                    target_id=normalized_target_id,
                    settings=settings,
                    notion_kwargs=notion_kwargs,
                )
                applied_request_payload, changed_by_property = _stamp_changed_by_property(
                    applied_request_payload,
                    schema_payload=schema_payload or database_payload,
                    notion_user_id=str(identity.get("notion_user_id") or ""),
                )
            applied_payload = create_notion_page(
                parent_id=normalized_target_id,
                parent_kind=parent_kind,
                token=settings["token"],
                api_version=settings["api_version"],
                payload=applied_request_payload,
                **notion_kwargs,
            )
            result_target_id = str(applied_payload.get("id") or "").strip() or normalized_target_id
            result_status = "applied"
            result_reason = f"verified caller insert applied under {parent_kind} {normalized_target_id}"
            result_note = {
                "agent_id": agent_id,
                "operation": op,
                "target_id": result_target_id,
                "parent_id": normalized_target_id,
                "parent_kind": parent_kind,
                "owner_identity": owner_identity,
                "owner_source": owner_source,
                "changed_by_property": changed_by_property,
                "actor": requested_by_actor,
            }
        else:
            page = retrieve_notion_page(
                page_id=normalized_target_id,
                token=settings["token"],
                api_version=settings["api_version"],
                **notion_kwargs,
            )
            approved, owner_source = _page_access_matches_identity(page, agent_row=agent_row, identity=identity)
            owner_identity, _ = _notion_owner_identity(page)
            if not approved:
                owner_label = owner_identity or "unknown"
                queue_notification(
                    conn,
                    target_kind="operator",
                    target_id=cfg.operator_notify_channel_id or cfg.operator_notify_platform or "operator",
                    channel_kind=cfg.operator_notify_platform or "tui-only",
                    message=(
                        f"SSOT write approval requested: agent={agent_id} op={op} target={normalized_target_id} "
                        f"owner={owner_label} source={owner_source}"
                    ),
                )
                reason = "target page is outside the verified caller's owned/assigned Notion scope"
                log_ssot_access_audit(
                    conn,
                    agent_id=str(agent_row["agent_id"]),
                    unix_user=str(agent_row["unix_user"]),
                    notion_user_id=str(identity.get("notion_user_id") or ""),
                    operation=op,
                    target_id=normalized_target_id,
                    decision="deny",
                    reason=reason,
                    actor=requested_by_actor,
                    request_payload=audit_payload,
                )
                raise PermissionError(reason)
            changed_by_property = ""
            applied_request_payload = _strip_attribution_properties(payload)
            parent = page.get("parent") if isinstance(page, dict) else {}
            if isinstance(parent, dict) and str(parent.get("type") or "").strip() == "data_source_id":
                schema_payload = retrieve_notion_data_source(
                    data_source_id=str(parent.get("data_source_id") or "").strip(),
                    token=settings["token"],
                    api_version=settings["api_version"],
                    **notion_kwargs,
                )
                applied_request_payload, changed_by_property = _stamp_changed_by_property(
                    applied_request_payload,
                    schema_payload=schema_payload,
                    notion_user_id=str(identity.get("notion_user_id") or ""),
                )
            elif isinstance(parent, dict) and str(parent.get("type") or "").strip() == "database_id":
                database_payload, schema_payload = _load_notion_collection_schema(
                    target_id=str(parent.get("database_id") or "").strip(),
                    settings=settings,
                    notion_kwargs=notion_kwargs,
                )
                applied_request_payload, changed_by_property = _stamp_changed_by_property(
                    applied_request_payload,
                    schema_payload=schema_payload or database_payload,
                    notion_user_id=str(identity.get("notion_user_id") or ""),
                )
            applied_payload = update_notion_page(
                page_id=normalized_target_id,
                token=settings["token"],
                api_version=settings["api_version"],
                payload=applied_request_payload,
                **notion_kwargs,
            )
            result_target_id = str(applied_payload.get("id") or "").strip() or normalized_target_id
            result_status = "applied"
            result_reason = f"verified caller update applied to page {normalized_target_id}"
            result_note = {
                "agent_id": agent_id,
                "operation": op,
                "target_id": result_target_id,
                "owner_identity": owner_identity,
                "owner_source": owner_source,
                "changed_by_property": changed_by_property,
                "actor": requested_by_actor,
            }

        job_name = f"ssot-{op}-{result_target_id or secrets.token_hex(4)}"
        note_refresh_job(
            conn,
            job_name=job_name,
            job_kind="ssot-write",
            target_id=result_target_id or agent_id,
            schedule="manual",
            status=result_status,
            note=json_dumps(result_note),
        )
        log_ssot_access_audit(
            conn,
            agent_id=str(agent_row["agent_id"]),
            unix_user=str(agent_row["unix_user"]),
            notion_user_id=str(identity.get("notion_user_id") or ""),
            operation=op,
            target_id=result_target_id,
            decision="allow",
            reason=result_reason,
            actor=requested_by_actor,
            request_payload=audit_payload,
        )
        return {
            "applied": True,
            "queued": False,
            "agent_id": agent_id,
            "operation": op,
            "target_id": result_target_id,
            "owner_identity": owner_identity,
            "owner_source": owner_source,
            "approval_required": False,
            "notion_result": applied_payload,
        }
    except PermissionError:
        raise
    except Exception as exc:
        note_refresh_job(
            conn,
            job_name=f"ssot-{op}-{normalized_target_id or secrets.token_hex(4)}",
            job_kind="ssot-write",
            target_id=normalized_target_id or agent_id,
            schedule="manual",
            status="fail",
            note=json_dumps(
                {
                    "agent_id": agent_id,
                    "operation": op,
                    "target_id": normalized_target_id,
                    "actor": requested_by_actor,
                    "error": str(exc),
                }
            ),
        )
        log_ssot_access_audit(
            conn,
            agent_id=str(agent_row["agent_id"]),
            unix_user=str(agent_row["unix_user"]),
            notion_user_id=str(identity.get("notion_user_id") or ""),
            operation=op,
            target_id=normalized_target_id,
            decision="fail",
            reason=f"shared Notion write failed: {exc}",
            actor=requested_by_actor,
            request_payload=audit_payload,
        )
        raise
def build_managed_memory_payload(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    agent_id: str,
) -> dict[str, Any]:
    """Compose the canonical managed-memory stubs for an agent.

    The skill contract is:
      [managed:almanac-skill-ref] default Almanac skill routing hints
      [managed:vault-ref]      active vault path and role
      [managed:resource-ref]   user-specific access rails + shared host rails
      [managed:qmd-ref]        how to query qmd for retrieval
      [managed:vault-topology] compact summary of subscribed vaults + briefs
      [managed:notion-stub]    Curator-produced shared Notion digest + verification state
    """
    agent = conn.execute(
        "SELECT role, unix_user, display_name, hermes_home FROM agents WHERE agent_id = ?",
        (agent_id,),
    ).fetchone()
    if agent is None:
        raise ValueError(f"unknown agent: {agent_id}")

    catalog = list_vaults(conn)
    subs = {row["vault_name"]: dict(row) for row in subscriptions_for_agent(conn, agent_id)}
    vault_root = str(cfg.vault_dir)

    topology_lines: list[str] = []
    for vault in catalog:
        sub = subs.get(vault["vault_name"])
        subscribed = bool(sub and int(sub.get("subscribed") or 0) == 1)
        mark = "+" if subscribed else ("·" if int(vault.get("default_subscribed") or 0) else "-")
        brief = (vault.get("brief_template") or vault.get("description") or "").strip()
        if brief:
            brief = brief.splitlines()[0][:140]
        topology_lines.append(f"  {mark} {vault['vault_name']}: {brief}")

    display_name = str(agent["display_name"] or "").strip()
    agent_role = str(agent["role"] or "").strip() or "user"
    agent_unix_user = str(agent["unix_user"] or "").strip()
    identity = get_agent_identity(conn, agent_id=agent_id, unix_user=agent_unix_user)
    hermes_home = Path(str(agent["hermes_home"] or "")).expanduser()
    access_state_path = hermes_home / "state" / "almanac-web-access.json"
    try:
        access_state_raw = access_state_path.read_text(encoding="utf-8") if access_state_path.is_file() else ""
    except OSError:
        access_state_raw = ""
    access_state = json_loads(access_state_raw, {})
    try:
        workspace_root = Path(pwd.getpwnam(agent_unix_user).pw_dir)
    except KeyError:
        try:
            workspace_root = hermes_home.parents[3]
        except IndexError:
            workspace_root = Path("/home") / agent_unix_user if agent_unix_user else hermes_home
    shared_host = shared_tailnet_host(
        tailscale_serve_enabled=(config_env_value("ENABLE_TAILSCALE_SERVE", "0").strip() == "1"),
        tailscale_dns_name=config_env_value("TAILSCALE_DNS_NAME", "").strip(),
        nextcloud_trusted_domain=config_env_value("NEXTCLOUD_TRUSTED_DOMAIN", "").strip(),
    )
    vault_ref = (
        f"Vault root: {vault_root}\n"
        f"Shared deployment root: {cfg.repo_dir}\n"
        f"Agent id: {agent_id}\n"
        f"Dedicated agent name: {display_name or agent_id}\n"
        f"Assigned unix user: {agent_unix_user or '(unknown)'}\n"
        f"Role: {agent_role}\n"
        "Curator runs the shared Almanac deployment and operator control plane.\n"
        "This agent works on behalf of one enrolled user inside that shared deployment."
    )
    skill_ref = (
        "Installed Almanac skills are live defaults on this dedicated user agent."
        " Use almanac-qmd-mcp for vault retrieval and follow-ups, almanac-vaults"
        " for subscription, catalog, and curate-vaults work, almanac-vault-reconciler"
        " for Almanac memory drift or repair, almanac-ssot for organization-aware"
        " SSOT coordination in the shared Notion workspace, almanac-ssot-connect"
        " when the user wants to link their own Notion through the official Notion"
        " MCP flow, almanac-notion-mcp once that user-owned Notion MCP is live,"
        " and almanac-first-contact for Almanac setup or diagnostic checks. All"
        " vaults remain retrievable through Almanac/qmd even when a vault is"
        " unsubscribed; subscriptions only shape managed-memory awareness and"
        " Curator push behavior. Curator also publishes a shared Notion digest"
        " into managed memory so the agent has ambient SSOT orientation without"
        " live cross-user reads. First flight should already have run the initial"
        " vault discovery and managed-memory stubbing. After that, the intended"
        " sync rail is curator fanout -> activation trigger / refresh timer ->"
        " user-agent-refresh -> local managed-memory stubs and recent events. Use"
        " those stubs plus qmd for depth instead of trying to memorize the vault."
        " On a shared host, the shared deployment root may live under"
        " /home/almanac/almanac; treat that as read-only shared infrastructure,"
        " not another enrolled user's workspace."
    )
    qmd_ref = (
        f"qmd MCP (deep retrieval): {cfg.qmd_url}\n"
        "Always query qmd before web for vault-relevant work, including the\n"
        "'vault-pdf-ingest' collection when present for PDF-derived markdown.\n"
        "Use almanac-ssot when the task is about organization state, Notion,\n"
        "or user-scoped SSOT updates; use qmd when the task is about vault depth.\n"
        "Never browse other users' home directories for Almanac context.\n"
        "Use the already wired MCP endpoints and agent-local Almanac state for\n"
        "site context. Do not read central deployment secrets such as\n"
        "almanac.env or source common.sh from a user-agent session."
    )
    resource_ref = managed_resource_ref(
        access=access_state,
        workspace_root=workspace_root,
        shared_lines=shared_resource_lines(
            host=shared_host,
            nextcloud_enabled=(config_env_value("ENABLE_NEXTCLOUD", "1").strip() == "1"),
            qmd_url=cfg.qmd_url,
            public_mcp_host=cfg.public_mcp_host,
            public_mcp_port=cfg.public_mcp_port,
            qmd_path=config_env_value("TAILSCALE_QMD_PATH", "/mcp").strip() or "/mcp",
            almanac_mcp_path=config_env_value("TAILSCALE_ALMANAC_MCP_PATH", "/almanac-mcp").strip() or "/almanac-mcp",
            chutes_mcp_url=cfg.chutes_mcp_url,
            notion_space_url=(
                config_env_value("ALMANAC_SSOT_NOTION_ROOT_PAGE_URL", "").strip()
                or config_env_value("ALMANAC_SSOT_NOTION_SPACE_URL", "").strip()
            ),
        ),
    )
    topology = "Subscribed vaults (+ = subscribed, · = default, - = unsubscribed):\n" + "\n".join(
        topology_lines
    )
    notion_stub = _build_notion_stub(conn, agent_row=agent, identity=identity)

    return {
        "agent_id": agent_id,
        "almanac-skill-ref": skill_ref,
        "vault-ref": vault_ref,
        "resource-ref": resource_ref,
        "qmd-ref": qmd_ref,
        "vault-topology": topology,
        "notion-stub": notion_stub,
        "catalog": catalog,
        "subscriptions": [dict(s) for s in subs.values()],
    }


_MEMORY_ENTRY_DELIMITER = "\n§\n"
_MANAGED_MEMORY_KEYS = ("almanac-skill-ref", "vault-ref", "resource-ref", "qmd-ref", "vault-topology", "notion-stub")
_MANAGED_MEMORY_PREFIXES = tuple(f"[managed:{key}]" for key in _MANAGED_MEMORY_KEYS)


def _read_memory_entries(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    if not raw.strip():
        return []
    return [entry.strip() for entry in raw.split(_MEMORY_ENTRY_DELIMITER) if entry.strip()]


def _write_memory_entries(path: Path, entries: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = _MEMORY_ENTRY_DELIMITER.join(entries) if entries else ""
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp", prefix=".almanac-memory-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, str(path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _managed_memory_entries(payload: dict[str, Any]) -> list[str]:
    entries: list[str] = []
    for key in _MANAGED_MEMORY_KEYS:
        prefix = f"[managed:{key}]"
        value = str(payload.get(key) or "").strip()
        if value:
            entries.append(f"{prefix}\n{value}")
    return entries


def write_managed_memory_stubs(
    *,
    hermes_home: Path,
    payload: dict[str, Any],
) -> dict[str, str]:
    """Idempotently write the managed-memory stubs into an agent's
    HERMES_HOME. Three artefacts are produced:

    1. `$HERMES_HOME/state/almanac-vault-reconciler.json` — structured state
       the vault-reconciler skill can read for drift detection.
    2. `$HERMES_HOME/memories/almanac-managed-stubs.md` — a human-readable
       markdown mirror of the managed entries.
    3. `$HERMES_HOME/memories/MEMORY.md` — the actual Hermes built-in memory
       store, patched in-place using Hermes's `§`-delimited entry format so the
       next session start sees the Almanac routing hints immediately.

    Returns the paths written. Called from the user-agent-refresh context
    running as the enrollment user — never from the central curator (which runs
    as a different uid and would violate the HOME boundary).
    """
    payload = dict(payload)
    if "almanac-skill-ref" not in payload and "skill-ref" in payload:
        payload["almanac-skill-ref"] = payload["skill-ref"]
    payload.setdefault(
        "almanac-skill-ref",
        "Installed Almanac skills are live defaults on this dedicated user agent."
        " Use almanac-qmd-mcp for vault retrieval and follow-ups, almanac-vaults"
        " for subscription and catalog work, almanac-vault-reconciler for Almanac"
        " memory drift or repair, almanac-ssot for organization-aware SSOT"
        " coordination, almanac-ssot-connect when the user wants to link their"
        " own Notion through the official Notion MCP flow, almanac-notion-mcp"
        " once that user-owned Notion MCP is live, and almanac-first-contact for"
        " Almanac setup or diagnostic checks. All vaults remain retrievable"
        " through Almanac/qmd even when a vault is unsubscribed; subscriptions"
        " only shape managed-memory awareness and Curator push behavior. On a"
        " shared host, the shared deployment root may live under"
        " /home/almanac/almanac; treat that as read-only shared infrastructure,"
        " not another enrolled user's workspace.",
    )
    payload.setdefault(
        "resource-ref",
        "Canonical user access rails and shared Almanac addresses:\n"
        "- Credentials are intentionally omitted from managed memory.\n"
        "- Ask Curator or the operator to reissue access if the user loses those credentials.",
    )
    payload.setdefault(
        "notion-stub",
        "Shared Notion digest:\n- Curator has not published a Notion digest into managed memory yet.",
    )
    state_dir = hermes_home / "state"
    memories_dir = hermes_home / "memories"
    state_dir.mkdir(parents=True, exist_ok=True)
    memories_dir.mkdir(parents=True, exist_ok=True)

    now = utc_now_iso()
    state_path = state_dir / "almanac-vault-reconciler.json"
    state_path.write_text(
        json.dumps(
            {
                "agent_id": payload["agent_id"],
                "almanac-skill-ref": payload["almanac-skill-ref"],
                "vault-ref": payload["vault-ref"],
                "resource-ref": payload["resource-ref"],
                "qmd-ref": payload["qmd-ref"],
                "vault-topology": payload["vault-topology"],
                "notion-stub": payload.get("notion-stub") or "",
                "catalog": payload["catalog"],
                "subscriptions": payload["subscriptions"],
                "updated_at": now,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    stub_path = memories_dir / "almanac-managed-stubs.md"
    body = (
        "# Almanac managed memory stubs\n\n"
        "Maintained by the user-agent-refresh worker every 4 hours. Do not\n"
        "hand-edit; changes are overwritten on next refresh.\n\n"
        f"## [managed:almanac-skill-ref]\n\n{payload['almanac-skill-ref']}\n\n"
        f"## [managed:vault-ref]\n\n{payload['vault-ref']}\n\n"
        f"## [managed:resource-ref]\n\n{payload['resource-ref']}\n\n"
        f"## [managed:qmd-ref]\n\n{payload['qmd-ref']}\n\n"
        f"## [managed:vault-topology]\n\n{payload['vault-topology']}\n\n"
        f"## [managed:notion-stub]\n\n{payload.get('notion-stub') or ''}\n\n"
        f"_updated_at: {now}_\n"
    )
    stub_path.write_text(body, encoding="utf-8")

    memory_path = memories_dir / "MEMORY.md"
    existing_entries = _read_memory_entries(memory_path)
    filtered_entries = [
        entry
        for entry in existing_entries
        if not any(entry.lstrip().startswith(prefix) for prefix in _MANAGED_MEMORY_PREFIXES)
    ]
    _write_memory_entries(memory_path, filtered_entries + _managed_memory_entries(payload))

    return {
        "state_path": str(state_path),
        "stub_path": str(stub_path),
        "memory_path": str(memory_path),
    }


def _central_managed_payload_path(cfg: Config, agent_id: str) -> Path:
    return cfg.agents_state_dir / agent_id / "managed-memory.json"


def publish_central_managed_memory(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    agent_id: str,
) -> Path:
    """Write the agent's managed-memory payload into the shared state dir so
    the user-agent-refresh worker (running as the enrollment user) can read
    the curator's latest view without crossing uid boundaries."""
    payload = build_managed_memory_payload(conn, cfg, agent_id=agent_id)
    out_path = _central_managed_payload_path(cfg, agent_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({**payload, "updated_at": utc_now_iso()}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    # world-readable so the enrollment user can read it without ACL fuss.
    try:
        out_path.chmod(0o644)
    except PermissionError:
        pass
    return out_path


def signal_agent_refresh_from_curator(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    agent_id: str,
    note: str,
) -> Path | None:
    row = conn.execute(
        "SELECT role, status, unix_user, display_name FROM agents WHERE agent_id = ?",
        (agent_id,),
    ).fetchone()
    if row is None:
        return None
    if str(row["role"] or "") != "user" or str(row["status"] or "") != "active":
        return None
    unix_user = str(row["unix_user"] or "").strip()
    if not unix_user:
        return None
    requester_identity = str(row["display_name"] or unix_user or agent_id).strip() or agent_id
    return write_activation_trigger(
        cfg,
        agent_id=agent_id,
        request_id=f"curator-refresh:{agent_id}",
        status="refresh",
        requester_identity=requester_identity,
        unix_user=unix_user,
        source_ip="127.0.0.1",
        note=note,
    )


def consume_curator_brief_fanout(conn: sqlite3.Connection, cfg: Config) -> dict[str, Any]:
    """Pull pending curator:brief-fanout notifications, publish fresh central
    managed-memory payloads for each impacted agent (shared state, no HERMES
    writes), and mark the notifications delivered.

    Each enrollment user's `user-agent-refresh.sh` then picks up the central
    payload on its next run (every 4h or on agent boot) and writes it into the
    user's own HERMES_HOME. This respects the uid boundary between curator and
    user agents."""
    rows = conn.execute(
        """
        SELECT id, target_id, message
        FROM notification_outbox
        WHERE delivered_at IS NULL
          AND target_kind = 'curator'
          AND channel_kind = 'brief-fanout'
        ORDER BY id ASC
        """
    ).fetchall()

    regen_targets: set[str] = set()
    catalog_events: list[str] = []
    for row in rows:
        target = str(row["target_id"])
        if target in ("", "curator"):
            for agent in conn.execute(
                "SELECT agent_id FROM agents WHERE role = 'user' AND status = 'active'"
            ):
                regen_targets.add(str(agent["agent_id"]))
            catalog_events.append(row["message"] or "")
        else:
            regen_targets.add(target)

    published: list[dict[str, str]] = []
    failures: list[str] = []
    for agent_id in sorted(regen_targets):
        try:
            path = publish_central_managed_memory(conn, cfg, agent_id=agent_id)
            trigger_path = signal_agent_refresh_from_curator(
                conn,
                cfg,
                agent_id=agent_id,
                note="curator brief-fanout: refresh managed memory stubs",
            )
            published_payload = {"agent_id": agent_id, "path": str(path)}
            if trigger_path is not None:
                published_payload["activation_trigger_path"] = str(trigger_path)
            published.append(published_payload)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{agent_id}:{exc}")

    if rows:
        conn.executemany(
            "UPDATE notification_outbox SET delivered_at = ? WHERE id = ?",
            [(utc_now_iso(), int(r["id"])) for r in rows],
        )
        conn.commit()

    note_refresh_job(
        conn,
        job_name="curator-brief-fanout",
        job_kind="curator-fanout",
        target_id="curator",
        schedule="on-demand",
        status="ok" if not failures else "warn",
        note=f"published {len(published)} central payload(s); failures={len(failures)}",
    )
    return {
        "processed_notifications": len(rows),
        "published_agents": published,
        "failures": failures,
        "catalog_events": catalog_events,
    }


def _map_event_to_affected_users(conn: sqlite3.Connection, payload: dict[str, Any]) -> tuple[list[str], bool]:
    owner_identity, _ = _notion_owner_identity(payload)
    resolved = True
    if not owner_identity:
        hydrated_payload, resolved = _hydrate_notion_event_entity(payload)
        if hydrated_payload:
            owner_identity, _ = _notion_owner_identity(hydrated_payload)
    if not owner_identity:
        return [], resolved
    agent = _find_agent_for_owner(conn, owner_identity)
    return ([agent["agent_id"]] if agent else []), resolved


def _signal_kind(event_type: str, payload: dict[str, Any]) -> str:
    kind = (event_type or "").lower()
    if "comment" in kind or "mention" in kind:
        return "focus-nudge"
    if "page" in kind and ("properties_updated" in kind or "content_updated" in kind):
        return "task-reminder"
    if "created" in kind:
        return "org-activity"
    return "org-activity"


def process_pending_notion_events(conn: sqlite3.Connection) -> dict[str, Any]:
    """Dedupe + batch pending webhook events. Resolve owners. Emit per-user nudges."""
    rows = conn.execute(
        """
        SELECT id, event_id, event_type, payload_json
        FROM notion_webhook_events
        WHERE batch_status = 'pending'
        ORDER BY received_at
        """
    ).fetchall()

    processed = 0
    event_types: dict[str, int] = {}
    nudges_by_agent: dict[str, list[str]] = {}
    unresolved_events: list[str] = []
    failed_events: list[str] = []
    verified_claims = 0

    # batch-level dedupe on (event_id, event_type). events get stored IGNORE on insert,
    # but an upstream replay can reintroduce identical event_ids; guard in case.
    seen_event_ids: set[str] = set()

    for row in rows:
        if row["event_id"] in seen_event_ids:
            conn.execute(
                "UPDATE notion_webhook_events SET batch_status = 'duplicate', processed_at = ? WHERE id = ?",
                (utc_now_iso(), row["id"]),
            )
            continue
        seen_event_ids.add(row["event_id"])

        payload = json_loads(row["payload_json"], {}) or {}
        entity_id, entity_type = _notion_event_entity_ref(payload)
        if entity_id and entity_type == "page":
            claim = get_notion_identity_claim(conn, notion_page_id=entity_id)
            if claim is not None and str(claim.get("status") or "").strip() == "pending":
                hydrated_page, resolved_claim = _hydrate_notion_event_entity(payload)
                if not resolved_claim:
                    unresolved_events.append(row["event_id"])
                    retry_status = _record_notion_event_retry(
                        conn,
                        row_id=int(row["id"]),
                        error_message="claim verification page hydration failed",
                    )
                    if retry_status == "failed":
                        failed_events.append(row["event_id"])
                    continue
                if resolved_claim and hydrated_page:
                    verified_claim = try_verify_notion_identity_claim(
                        conn,
                        claim=claim,
                        page_payload=hydrated_page,
                        verification_source="notion-webhook",
                    )
                    if verified_claim is not None and str(verified_claim.get("status") or "").strip() == "verified":
                        verified_claims += 1
                processed += 1
                event_types[row["event_type"]] = event_types.get(row["event_type"], 0) + 1
                conn.execute(
                    """
                    UPDATE notion_webhook_events
                    SET batch_status = 'processed', processed_at = ?
                    WHERE id = ?
                    """,
                    (utc_now_iso(), row["id"]),
                )
                continue
        affected, resolved = _map_event_to_affected_users(conn, payload)
        signal = _signal_kind(row["event_type"], payload)

        if not affected:
            unresolved_events.append(row["event_id"])
        if not resolved:
            retry_status = _record_notion_event_retry(
                conn,
                row_id=int(row["id"]),
                error_message="event hydration failed",
            )
            if retry_status == "failed":
                failed_events.append(row["event_id"])
            continue

        for agent_id in affected:
            nudges_by_agent.setdefault(agent_id, []).append(
                f"{signal}:{row['event_type']}:{row['event_id']}"
            )

        processed += 1
        event_types[row["event_type"]] = event_types.get(row["event_type"], 0) + 1
        conn.execute(
            """
            UPDATE notion_webhook_events
            SET batch_status = 'processed', processed_at = ?
            WHERE id = ?
            """,
            (utc_now_iso(), row["id"]),
        )

    # emit batched per-user nudges
    for agent_id, tokens in nudges_by_agent.items():
        queue_notification(
            conn,
            target_kind="user-agent",
            target_id=agent_id,
            channel_kind="notion-webhook",
            message=f"SSOT signals ({len(tokens)}): " + ", ".join(tokens[:10])
            + ("" if len(tokens) <= 10 else f" ... (+{len(tokens) - 10} more)"),
        )
        queue_notification(
            conn,
            target_kind="curator",
            target_id=agent_id,
            channel_kind="brief-fanout",
            message=f"notion event refresh for {agent_id}",
        )

    conn.commit()
    batch_status = "ok"
    if failed_events:
        batch_status = "fail"
    elif unresolved_events:
        batch_status = "warn"
    note_refresh_job(
        conn,
        job_name="notion-ssot-batcher",
        job_kind="ssot-batcher",
        target_id="notion",
        schedule="every 5m",
        status=batch_status,
        note=(
            f"processed {processed} event(s); verified_claims={verified_claims}; "
            f"unresolved {len(unresolved_events)}; failed {len(failed_events)}; "
            f"SLO targets p50<{NOTION_SLO_P50_SECONDS}s p99<{NOTION_SLO_P99_SECONDS}s"
        ),
    )
    return {
        "processed": processed,
        "verified_claims": verified_claims,
        "event_types": event_types,
        "nudges": {agent: len(v) for agent, v in nudges_by_agent.items()},
        "unresolved_event_ids": unresolved_events,
        "failed_event_ids": failed_events,
    }


def ensure_config_file_update(path: Path, updates: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    existing: dict[str, bool] = {key: False for key in updates}
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    new_lines = []
    for line in lines:
        replaced = False
        for key, value in updates.items():
            if line.startswith(f"{key}="):
                new_lines.append(f"{key}={shell_quote(value)}")
                existing[key] = True
                replaced = True
                break
        if not replaced:
            new_lines.append(line)
    for key, seen in existing.items():
        if not seen:
            new_lines.append(f"{key}={shell_quote(updates[key])}")
    path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")
