#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import ipaddress
import json
import mimetypes
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
from typing import Any, Mapping, Sequence
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

_PYTHON_DIR = Path(__file__).resolve().parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from arclink_model_providers import provider_default_model, resolve_preset_target  # noqa: E402
from arclink_notion_ssot import (  # noqa: E402
    append_notion_block_children,
    create_notion_database,
    create_notion_page,
    DEFAULT_NOTION_API_VERSION,
    extract_notion_space_id,
    list_notion_block_children_all,
    normalize_notion_space_url,
    notion_database_data_source_id,
    query_notion_collection,
    query_notion_collection_all,
    query_notion_data_source,
    retrieve_notion_data_source,
    retrieve_notion_database,
    retrieve_notion_file_upload,
    retrieve_notion_page,
    retrieve_notion_page_markdown,
    retrieve_notion_user,
    update_notion_data_source,
    update_notion_page,
    resolve_notion_target,
)
from arclink_rpc_client import mcp_call  # noqa: E402
from arclink_resource_map import managed_resource_ref, shared_resource_lines, shared_tailnet_host  # noqa: E402


AUTO_PROVISION_UNIX_USER_PATTERN = re.compile(r"^[a-z_][a-z0-9_-]{0,30}$")


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def utc_now_iso() -> str:
    return utc_now().replace(microsecond=0).isoformat()


def utc_after_seconds_iso(seconds: int) -> str:
    return (utc_now() + dt.timedelta(seconds=max(1, int(seconds)))).replace(microsecond=0).isoformat()


def parse_utc_iso(value: str | None) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def format_utc_iso_brief(value: str | None) -> str:
    parsed = parse_utc_iso(value)
    if parsed is None:
        return str(value or "").strip()
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


def expiry_from_iso(value: str | None, *, ttl_seconds: int) -> str:
    base = parse_utc_iso(value) or utc_now()
    return (base + dt.timedelta(seconds=max(1, int(ttl_seconds)))).replace(microsecond=0).isoformat()


def active_deploy_operation(cfg: "Config") -> dict[str, str] | None:
    marker = cfg.state_dir / "arclink-deploy-operation.json"
    if not marker.is_file():
        return None
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    operation = str(payload.get("operation") or "").strip()
    if operation not in {"install", "upgrade", "docker-install", "docker-upgrade", "control-install", "control-upgrade"}:
        return None

    now = utc_now()
    expires_at = parse_utc_iso(str(payload.get("expires_at") or ""))
    if expires_at is not None:
        if expires_at <= now:
            return None
    else:
        try:
            marker_mtime = dt.datetime.fromtimestamp(marker.stat().st_mtime, dt.timezone.utc)
        except OSError:
            return None
        if marker_mtime + dt.timedelta(hours=6) <= now:
            return None

    return {
        "operation": operation,
        "path": str(marker),
        "expires_at": str(payload.get("expires_at") or ""),
    }


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


# (repo-sync no longer scans markdown for URLs or manages mirror exports. It
# now only pulls git checkouts that operators place in the vault. The constants
# and patterns that drove URL mining were removed with that rail.)


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
        "ARCLINK_OPERATOR_DEPLOYED_USER": "",
        "ARCLINK_OPERATOR_DEPLOYED_REPO_DIR": "",
        "ARCLINK_OPERATOR_DEPLOYED_PRIV_DIR": "",
        "ARCLINK_OPERATOR_DEPLOYED_CONFIG_FILE": "",
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
    explicit = os.environ.get("ARCLINK_CONFIG_FILE")
    if explicit:
        path = Path(explicit).expanduser()
        return path if _safe_path_is_file(path) else path

    repo_root = Path(os.environ.get("ARCLINK_REPO_DIR", _python_repo_root())).expanduser().resolve()
    operator_artifact = Path(
        os.environ.get("ARCLINK_OPERATOR_ARTIFACT_FILE", str(repo_root / ".arclink-operator.env"))
    ).expanduser()
    artifact_hints = _read_operator_artifact_hints(operator_artifact)
    artifact_user = artifact_hints.get("ARCLINK_OPERATOR_DEPLOYED_USER", "")
    artifact_repo = artifact_hints.get("ARCLINK_OPERATOR_DEPLOYED_REPO_DIR", "")
    artifact_priv = artifact_hints.get("ARCLINK_OPERATOR_DEPLOYED_PRIV_DIR", "")
    artifact_config = artifact_hints.get("ARCLINK_OPERATOR_DEPLOYED_CONFIG_FILE", "")
    artifact_home = _resolve_user_home(artifact_user)

    nested_priv = repo_root / "arclink-priv" / "config" / "arclink.env"
    sibling_priv = repo_root.parent / "arclink-priv" / "config" / "arclink.env"
    candidates: list[Path] = []
    if artifact_config:
        candidates.append(Path(artifact_config).expanduser())
    if artifact_priv:
        artifact_priv_path = Path(artifact_priv).expanduser()
        candidates.extend(
            (
                artifact_priv_path / "config" / "arclink.env",
                artifact_priv_path / "arclink.env",
            )
        )
    if artifact_repo:
        artifact_repo_path = Path(artifact_repo).expanduser()
        candidates.extend(
            (
                artifact_repo_path / "arclink-priv" / "config" / "arclink.env",
                artifact_repo_path / "config" / "arclink.env",
            )
        )
    if artifact_home is not None:
        candidates.extend(
            (
                artifact_home / "arclink" / "arclink-priv" / "config" / "arclink.env",
                artifact_home / "arclink-priv" / "config" / "arclink.env",
            )
        )
    candidates.extend(
        (
        repo_root / "config" / "arclink.env",
        nested_priv,
        sibling_priv,
        Path.home() / "arclink" / "arclink-priv" / "config" / "arclink.env",
        Path.home() / "arclink-priv" / "config" / "arclink.env",
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
        merged.setdefault("ARCLINK_CONFIG_FILE", str(config_path))
        return merged

    try:
        config_text = config_path.read_text(encoding="utf-8")
    except OSError:
        merged.setdefault("ARCLINK_CONFIG_FILE", str(config_path))
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

    merged.setdefault("ARCLINK_CONFIG_FILE", str(config_path))
    return merged


def config_env_value(name: str, default: str = "") -> str:
    return _load_config_env().get(name, default)


@dataclass(frozen=True)
class Config:
    arclink_user: str
    arclink_home: Path
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
    ssot_pending_write_ttl_seconds: int
    curator_fanout_retry_base_seconds: int
    curator_fanout_retry_max_seconds: int
    operator_notify_platform: str
    operator_notify_channel_id: str
    operator_telegram_user_ids: tuple[str, ...]
    operator_general_platform: str
    operator_general_channel_id: str
    qmd_url: str
    extra_mcp_name: str
    extra_mcp_label: str
    extra_mcp_url: str
    upstream_repo_url: str
    upstream_branch: str
    upstream_deploy_key_enabled: bool
    upstream_deploy_key_path: str
    upstream_known_hosts_file: str
    org_provider_enabled: bool
    org_provider_preset: str
    org_provider_model_id: str
    org_provider_reasoning_effort: str
    model_presets: dict[str, str]
    agent_dashboard_backend_port_base: int
    agent_dashboard_proxy_port_base: int
    agent_port_slot_span: int
    agent_enable_tailscale_serve: bool

    @classmethod
    def from_env(cls) -> "Config":
        env = _load_config_env()
        arclink_user = env.get("ARCLINK_USER", "arclink")
        repo_dir = Path(env.get("ARCLINK_REPO_DIR", os.getcwd())).resolve()
        private_dir = Path(env.get("ARCLINK_PRIV_DIR", repo_dir / "arclink-priv")).resolve()
        state_dir = Path(env.get("STATE_DIR", private_dir / "state")).resolve()
        runtime_dir = Path(env.get("RUNTIME_DIR", state_dir / "runtime")).resolve()
        vault_dir = Path(env.get("VAULT_DIR", private_dir / "vault")).resolve()
        public_mcp_port = int(env.get("ARCLINK_MCP_PORT", "8282"))
        public_mcp_host = env.get("ARCLINK_MCP_HOST", "127.0.0.1")
        notion_webhook_port = int(env.get("ARCLINK_NOTION_WEBHOOK_PORT", "8283"))
        notion_webhook_host = env.get("ARCLINK_NOTION_WEBHOOK_HOST", "127.0.0.1")
        qmd_url = env.get("ARCLINK_QMD_URL", f"http://127.0.0.1:{env.get('QMD_MCP_PORT', '8181')}/mcp")
        extra_mcp_name = env.get("ARCLINK_EXTRA_MCP_NAME", "external-kb").strip() or "external-kb"
        extra_mcp_label = env.get("ARCLINK_EXTRA_MCP_LABEL", "External knowledge rail").strip() or "External knowledge rail"
        extra_mcp_url = env.get("ARCLINK_EXTRA_MCP_URL", "")

        model_presets = {
            "codex": resolve_preset_target("codex", env.get("ARCLINK_MODEL_PRESET_CODEX", ""), repo_dir, env),
            "opus": resolve_preset_target("opus", env.get("ARCLINK_MODEL_PRESET_OPUS", ""), repo_dir, env),
            "chutes": resolve_preset_target("chutes", env.get("ARCLINK_MODEL_PRESET_CHUTES", ""), repo_dir, env),
        }
        org_provider_enabled = bool_env("ARCLINK_ORG_PROVIDER_ENABLED", default=False, env=env)
        org_provider_preset = env.get("ARCLINK_ORG_PROVIDER_PRESET", "").strip().lower()
        org_provider_secret = env.get("ARCLINK_ORG_PROVIDER_SECRET", "").strip()
        org_provider_reasoning_effort = env.get("ARCLINK_ORG_PROVIDER_REASONING_EFFORT", "medium").strip().lower() or "medium"
        org_provider_model_id = env.get("ARCLINK_ORG_PROVIDER_MODEL_ID", "").strip()

        def default_model_id_for_preset(preset: str) -> str:
            target = str(model_presets.get(preset) or "").strip()
            configured = target.split(":", 1)[1].strip() if ":" in target else target
            return configured or provider_default_model(preset, repo_dir, env)

        if org_provider_enabled and org_provider_preset in model_presets and org_provider_secret:
            org_provider_model_id = org_provider_model_id or default_model_id_for_preset(org_provider_preset)
            if org_provider_preset == "codex":
                model_presets["org-provided"] = f"openai-codex:{org_provider_model_id or provider_default_model('codex', repo_dir, env)}"
            elif org_provider_preset == "opus":
                model_presets["org-provided"] = f"anthropic:{org_provider_model_id or provider_default_model('opus', repo_dir, env)}"
            else:
                model_presets["org-provided"] = f"chutes:{org_provider_model_id or provider_default_model('chutes', repo_dir, env)}"
        else:
            org_provider_enabled = False
            org_provider_preset = ""
            org_provider_model_id = ""
            org_provider_reasoning_effort = "medium"
        curator_channels = {
            value.strip().lower()
            for value in env.get("ARCLINK_CURATOR_CHANNELS", "tui-only").split(",")
            if value.strip()
        }
        operator_notify_platform = env.get("OPERATOR_NOTIFY_CHANNEL_PLATFORM", "tui-only")
        operator_notify_channel_id = env.get("OPERATOR_NOTIFY_CHANNEL_ID", "")
        operator_telegram_user_ids_raw = env.get(
            "ARCLINK_OPERATOR_TELEGRAM_USER_IDS",
            "",
        )
        operator_telegram_user_ids = tuple(
            value.strip()
            for value in operator_telegram_user_ids_raw.split(",")
            if value.strip()
        )
        agent_enable_tailscale_serve = bool_env(
            "ARCLINK_AGENT_ENABLE_TAILSCALE_SERVE",
            default=bool_env("ENABLE_TAILSCALE_SERVE", default=False, env=env),
            env=env,
        )

        return cls(
            arclink_user=arclink_user,
            arclink_home=Path(env.get("ARCLINK_HOME", f"/home/{arclink_user}")).resolve(),
            repo_dir=repo_dir,
            private_dir=private_dir,
            state_dir=state_dir,
            runtime_dir=runtime_dir,
            vault_dir=vault_dir,
            db_path=Path(env.get("ARCLINK_DB_PATH", state_dir / "arclink-control.sqlite3")).resolve(),
            agents_state_dir=Path(env.get("ARCLINK_AGENTS_STATE_DIR", state_dir / "agents")).resolve(),
            curator_dir=Path(env.get("ARCLINK_CURATOR_DIR", state_dir / "curator")).resolve(),
            curator_manifest_path=Path(env.get("ARCLINK_CURATOR_MANIFEST", state_dir / "curator" / "manifest.json")).resolve(),
            curator_hermes_home=Path(env.get("ARCLINK_CURATOR_HERMES_HOME", state_dir / "curator" / "hermes-home")).resolve(),
            archived_agents_dir=Path(env.get("ARCLINK_ARCHIVED_AGENTS_DIR", state_dir / "archived-agents")).resolve(),
            release_state_file=Path(env.get("ARCLINK_RELEASE_STATE_FILE", state_dir / "arclink-release.json")).resolve(),
            public_mcp_host=public_mcp_host,
            public_mcp_port=public_mcp_port,
            notion_webhook_host=notion_webhook_host,
            notion_webhook_port=notion_webhook_port,
            bootstrap_window_seconds=int(env.get("ARCLINK_BOOTSTRAP_WINDOW_SECONDS", "3600")),
            bootstrap_per_ip_limit=int(env.get("ARCLINK_BOOTSTRAP_PER_IP_LIMIT", "5")),
            bootstrap_global_pending_limit=int(env.get("ARCLINK_BOOTSTRAP_GLOBAL_PENDING_LIMIT", "20")),
            bootstrap_pending_ttl_seconds=int(env.get("ARCLINK_BOOTSTRAP_PENDING_TTL_SECONDS", "900")),
            auto_provision_max_attempts=int(env.get("ARCLINK_AUTO_PROVISION_MAX_ATTEMPTS", "5")),
            auto_provision_retry_base_seconds=int(env.get("ARCLINK_AUTO_PROVISION_RETRY_BASE_SECONDS", "60")),
            auto_provision_retry_max_seconds=int(env.get("ARCLINK_AUTO_PROVISION_RETRY_MAX_SECONDS", "900")),
            curator_telegram_onboarding_enabled=bool_env(
                "ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED",
                default=("telegram" in curator_channels or operator_notify_platform == "telegram"),
                env=env,
            ),
            curator_discord_onboarding_enabled=bool_env(
                "ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED",
                default=("discord" in curator_channels or operator_notify_platform == "discord"),
                env=env,
            ),
            onboarding_window_seconds=int(env.get("ARCLINK_ONBOARDING_WINDOW_SECONDS", "3600")),
            onboarding_per_telegram_user_limit=int(
                env.get(
                    "ARCLINK_ONBOARDING_PER_USER_LIMIT",
                    env.get("ARCLINK_ONBOARDING_PER_TELEGRAM_USER_LIMIT", "3"),
                )
            ),
            onboarding_global_pending_limit=int(env.get("ARCLINK_ONBOARDING_GLOBAL_PENDING_LIMIT", "20")),
            onboarding_update_failure_limit=int(env.get("ARCLINK_ONBOARDING_UPDATE_FAILURE_LIMIT", "3")),
            ssot_pending_write_ttl_seconds=int(env.get("ARCLINK_SSOT_PENDING_WRITE_TTL_SECONDS", "86400")),
            curator_fanout_retry_base_seconds=int(env.get("ARCLINK_CURATOR_FANOUT_RETRY_BASE_SECONDS", "15")),
            curator_fanout_retry_max_seconds=int(env.get("ARCLINK_CURATOR_FANOUT_RETRY_MAX_SECONDS", "300")),
            operator_notify_platform=operator_notify_platform,
            operator_notify_channel_id=operator_notify_channel_id,
            operator_telegram_user_ids=operator_telegram_user_ids,
            operator_general_platform=env.get("OPERATOR_GENERAL_CHANNEL_PLATFORM", ""),
            operator_general_channel_id=env.get("OPERATOR_GENERAL_CHANNEL_ID", ""),
            qmd_url=qmd_url,
            extra_mcp_name=extra_mcp_name,
            extra_mcp_label=extra_mcp_label,
            extra_mcp_url=extra_mcp_url,
            upstream_repo_url=env.get("ARCLINK_UPSTREAM_REPO_URL", "https://github.com/example/arclink.git"),
            upstream_branch=env.get("ARCLINK_UPSTREAM_BRANCH", "main"),
            upstream_deploy_key_enabled=bool_env(
                "ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED",
                default=False,
                env=env,
            ),
            upstream_deploy_key_path=env.get("ARCLINK_UPSTREAM_DEPLOY_KEY_PATH", ""),
            upstream_known_hosts_file=env.get("ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE", ""),
            org_provider_enabled=org_provider_enabled,
            org_provider_preset=org_provider_preset,
            org_provider_model_id=org_provider_model_id,
            org_provider_reasoning_effort=org_provider_reasoning_effort,
            model_presets=model_presets,
            agent_dashboard_backend_port_base=int(env.get("ARCLINK_AGENT_DASHBOARD_BACKEND_PORT_BASE", "19000")),
            agent_dashboard_proxy_port_base=int(env.get("ARCLINK_AGENT_DASHBOARD_PROXY_PORT_BASE", "29000")),
            agent_port_slot_span=int(env.get("ARCLINK_AGENT_PORT_SLOT_SPAN", "5000")),
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
    conn = sqlite3.connect(cfg.db_path, timeout=15.0)
    conn.row_factory = sqlite3.Row
    default_journal_mode = "DELETE" if os.environ.get("ARCLINK_DOCKER_MODE") == "1" else "WAL"
    journal_mode = config_env_value("ARCLINK_SQLITE_JOURNAL_MODE", default_journal_mode).strip().upper()
    if journal_mode not in {"DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"}:
        journal_mode = default_journal_mode
    try:
        conn.execute(f"PRAGMA journal_mode = {journal_mode}")
    except sqlite3.OperationalError:
        if journal_mode != "WAL":
            raise
        conn.execute("PRAGMA journal_mode = DELETE")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    conn.execute("PRAGMA synchronous = NORMAL")
    ensure_schema(conn, cfg)
    _migrate_onboarding_bot_tokens(conn, cfg)
    expire_stale_ssot_pending_writes(conn)
    return conn


def ensure_schema(conn: sqlite3.Connection, cfg: Config | None = None) -> None:
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
          org_profile_person_id TEXT NOT NULL DEFAULT '',
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

        CREATE TABLE IF NOT EXISTS pin_upgrade_notifications (
          component TEXT PRIMARY KEY,
          field TEXT NOT NULL,
          current_pin TEXT NOT NULL,
          target_value TEXT NOT NULL,
          first_seen_at TEXT NOT NULL,
          last_notified_at TEXT,
          notify_count INTEGER NOT NULL DEFAULT 0,
          silenced INTEGER NOT NULL DEFAULT 0,
          applied_at TEXT,
          extra_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS notification_outbox (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          target_kind TEXT NOT NULL,
          target_id TEXT NOT NULL,
          channel_kind TEXT NOT NULL,
          message TEXT NOT NULL,
          extra_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          attempt_count INTEGER NOT NULL DEFAULT 0,
          last_attempt_at TEXT,
          next_attempt_at TEXT,
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

        CREATE TABLE IF NOT EXISTS ssot_pending_writes (
          pending_id TEXT PRIMARY KEY,
          agent_id TEXT NOT NULL,
          unix_user TEXT NOT NULL,
          notion_user_id TEXT NOT NULL DEFAULT '',
          operation TEXT NOT NULL,
          target_id TEXT NOT NULL,
          payload_json TEXT NOT NULL DEFAULT '{}',
          requested_by_actor TEXT NOT NULL DEFAULT '',
          request_source TEXT NOT NULL DEFAULT '',
          request_reason TEXT NOT NULL DEFAULT '',
          owner_identity TEXT NOT NULL DEFAULT '',
          owner_source TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'pending',
          requested_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          decision_surface TEXT NOT NULL DEFAULT '',
          decided_by_actor TEXT NOT NULL DEFAULT '',
          decided_at TEXT,
          decision_note TEXT NOT NULL DEFAULT '',
          applied_at TEXT,
          apply_result_json TEXT NOT NULL DEFAULT '{}'
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

        CREATE TABLE IF NOT EXISTS notion_index_documents (
          doc_key TEXT PRIMARY KEY,
          root_id TEXT NOT NULL,
          source_page_id TEXT NOT NULL,
          source_page_url TEXT NOT NULL DEFAULT '',
          source_kind TEXT NOT NULL DEFAULT 'page',
          file_path TEXT NOT NULL,
          page_title TEXT NOT NULL DEFAULT '',
          section_heading TEXT NOT NULL DEFAULT '',
          section_ordinal INTEGER NOT NULL DEFAULT 0,
          breadcrumb_json TEXT NOT NULL DEFAULT '[]',
          owners_json TEXT NOT NULL DEFAULT '[]',
          last_edited_time TEXT NOT NULL DEFAULT '',
          content_hash TEXT NOT NULL DEFAULT '',
          indexed_at TEXT NOT NULL,
          state TEXT NOT NULL DEFAULT 'active'
        );

        CREATE TABLE IF NOT EXISTS notion_retrieval_audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          agent_id TEXT NOT NULL,
          unix_user TEXT NOT NULL,
          operation TEXT NOT NULL,
          decision TEXT NOT NULL,
          query_text TEXT NOT NULL DEFAULT '',
          target_id TEXT NOT NULL DEFAULT '',
          root_id TEXT NOT NULL DEFAULT '',
          result_count INTEGER NOT NULL DEFAULT 0,
          note TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_synthesis_cards (
          card_id TEXT PRIMARY KEY,
          source_kind TEXT NOT NULL,
          source_key TEXT NOT NULL,
          source_title TEXT NOT NULL DEFAULT '',
          source_signature TEXT NOT NULL,
          prompt_version TEXT NOT NULL,
          model TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL,
          card_json TEXT NOT NULL DEFAULT '{}',
          card_text TEXT NOT NULL DEFAULT '',
          source_count INTEGER NOT NULL DEFAULT 0,
          token_estimate INTEGER NOT NULL DEFAULT 0,
          last_error TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS arclink_users (
          user_id TEXT PRIMARY KEY,
          email TEXT NOT NULL DEFAULT '',
          display_name TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL,
          password_hash TEXT NOT NULL DEFAULT '',
          stripe_customer_id TEXT NOT NULL DEFAULT '',
          entitlement_state TEXT NOT NULL DEFAULT 'none',
          entitlement_updated_at TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS arclink_webhook_events (
          provider TEXT NOT NULL,
          event_id TEXT NOT NULL,
          event_type TEXT NOT NULL DEFAULT '',
          received_at TEXT NOT NULL,
          processed_at TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'received',
          payload_json TEXT NOT NULL DEFAULT '{}',
          PRIMARY KEY (provider, event_id)
        );

        CREATE TABLE IF NOT EXISTS arclink_deployments (
          deployment_id TEXT PRIMARY KEY,
          user_id TEXT NOT NULL,
          prefix TEXT NOT NULL,
          base_domain TEXT NOT NULL DEFAULT '',
          agent_id TEXT NOT NULL DEFAULT '',
          session_id TEXT NOT NULL DEFAULT '',
          bootstrap_request_id TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL,
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS arclink_subscriptions (
          subscription_id TEXT PRIMARY KEY,
          user_id TEXT NOT NULL,
          stripe_customer_id TEXT NOT NULL DEFAULT '',
          stripe_subscription_id TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL,
          current_period_end TEXT NOT NULL DEFAULT '',
          raw_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS arclink_provisioning_jobs (
          job_id TEXT PRIMARY KEY,
          deployment_id TEXT NOT NULL,
          job_kind TEXT NOT NULL,
          status TEXT NOT NULL,
          attempt_count INTEGER NOT NULL DEFAULT 0,
          idempotency_key TEXT NOT NULL DEFAULT '',
          metadata_json TEXT NOT NULL DEFAULT '{}',
          requested_at TEXT NOT NULL,
          started_at TEXT,
          finished_at TEXT,
          error TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS arclink_dns_records (
          record_id TEXT PRIMARY KEY,
          deployment_id TEXT NOT NULL,
          hostname TEXT NOT NULL,
          record_type TEXT NOT NULL,
          target TEXT NOT NULL,
          provider_record_id TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL,
          last_checked_at TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS arclink_admins (
          admin_id TEXT PRIMARY KEY,
          email TEXT NOT NULL,
          role TEXT NOT NULL,
          status TEXT NOT NULL,
          password_hash TEXT NOT NULL DEFAULT '',
          role_scope_json TEXT NOT NULL DEFAULT '{}',
          totp_enabled INTEGER NOT NULL DEFAULT 0,
          totp_secret_ref TEXT NOT NULL DEFAULT '',
          totp_verified_at TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS arclink_user_sessions (
          session_id TEXT PRIMARY KEY,
          user_id TEXT NOT NULL,
          session_token_hash TEXT NOT NULL,
          csrf_token_hash TEXT NOT NULL,
          status TEXT NOT NULL,
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          last_seen_at TEXT NOT NULL DEFAULT '',
          expires_at TEXT NOT NULL,
          revoked_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS arclink_admin_sessions (
          session_id TEXT PRIMARY KEY,
          admin_id TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT '',
          session_token_hash TEXT NOT NULL,
          csrf_token_hash TEXT NOT NULL,
          status TEXT NOT NULL,
          mfa_verified_at TEXT NOT NULL DEFAULT '',
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          last_seen_at TEXT NOT NULL DEFAULT '',
          expires_at TEXT NOT NULL,
          revoked_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS arclink_admin_roles (
          admin_id TEXT NOT NULL,
          role TEXT NOT NULL,
          granted_by TEXT NOT NULL DEFAULT '',
          reason TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          revoked_at TEXT NOT NULL DEFAULT '',
          PRIMARY KEY (admin_id, role)
        );

        CREATE TABLE IF NOT EXISTS arclink_admin_totp_factors (
          factor_id TEXT PRIMARY KEY,
          admin_id TEXT NOT NULL,
          status TEXT NOT NULL,
          secret_ref TEXT NOT NULL,
          enrolled_at TEXT NOT NULL,
          verified_at TEXT NOT NULL DEFAULT '',
          last_used_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS arclink_audit_log (
          audit_id TEXT PRIMARY KEY,
          actor_id TEXT NOT NULL DEFAULT '',
          action TEXT NOT NULL,
          target_kind TEXT NOT NULL DEFAULT '',
          target_id TEXT NOT NULL DEFAULT '',
          reason TEXT NOT NULL DEFAULT '',
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS arclink_service_health (
          deployment_id TEXT NOT NULL,
          service_name TEXT NOT NULL,
          status TEXT NOT NULL,
          checked_at TEXT NOT NULL,
          detail_json TEXT NOT NULL DEFAULT '{}',
          PRIMARY KEY (deployment_id, service_name)
        );

        CREATE TABLE IF NOT EXISTS arclink_events (
          event_id TEXT PRIMARY KEY,
          subject_kind TEXT NOT NULL,
          subject_id TEXT NOT NULL,
          event_type TEXT NOT NULL,
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS arclink_model_catalog (
          provider TEXT NOT NULL,
          model_id TEXT NOT NULL,
          display_name TEXT NOT NULL DEFAULT '',
          capabilities_json TEXT NOT NULL DEFAULT '{}',
          confidential_compute INTEGER NOT NULL DEFAULT 0,
          raw_json TEXT NOT NULL DEFAULT '{}',
          updated_at TEXT NOT NULL,
          PRIMARY KEY (provider, model_id)
        );

        CREATE TABLE IF NOT EXISTS arclink_onboarding_sessions (
          session_id TEXT PRIMARY KEY,
          channel TEXT NOT NULL,
          channel_identity TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL,
          current_step TEXT NOT NULL DEFAULT '',
          email_hint TEXT NOT NULL DEFAULT '',
          display_name_hint TEXT NOT NULL DEFAULT '',
          selected_plan_id TEXT NOT NULL DEFAULT '',
          selected_model_id TEXT NOT NULL DEFAULT '',
          user_id TEXT NOT NULL DEFAULT '',
          deployment_id TEXT NOT NULL DEFAULT '',
          checkout_session_id TEXT NOT NULL DEFAULT '',
          checkout_url TEXT NOT NULL DEFAULT '',
          checkout_state TEXT NOT NULL DEFAULT '',
          stripe_customer_id TEXT NOT NULL DEFAULT '',
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          completed_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS arclink_onboarding_events (
          event_id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          event_type TEXT NOT NULL,
          channel TEXT NOT NULL DEFAULT '',
          channel_identity TEXT NOT NULL DEFAULT '',
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS arclink_channel_pairing_codes (
          code TEXT PRIMARY KEY,
          source_session_id TEXT NOT NULL,
          source_channel TEXT NOT NULL,
          source_channel_identity TEXT NOT NULL,
          user_id TEXT NOT NULL DEFAULT '',
          deployment_id TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          claimed_session_id TEXT NOT NULL DEFAULT '',
          claimed_channel TEXT NOT NULL DEFAULT '',
          claimed_channel_identity TEXT NOT NULL DEFAULT '',
          claimed_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS arclink_action_intents (
          action_id TEXT PRIMARY KEY,
          admin_id TEXT NOT NULL,
          action_type TEXT NOT NULL,
          target_kind TEXT NOT NULL,
          target_id TEXT NOT NULL,
          status TEXT NOT NULL,
          idempotency_key TEXT NOT NULL,
          reason TEXT NOT NULL,
          metadata_json TEXT NOT NULL DEFAULT '{}',
          audit_id TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        """
    )
    _migrate_notion_identity_claims_remove_legacy_nonce(conn)
    _ensure_column(conn, "agent_identity", "org_profile_person_id", "TEXT NOT NULL DEFAULT ''")
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
        CREATE INDEX IF NOT EXISTS idx_agent_identity_org_profile_person
        ON agent_identity (org_profile_person_id)
        WHERE org_profile_person_id != ''
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_identity_org_profile_person_active_unique
        ON agent_identity (org_profile_person_id)
        WHERE org_profile_person_id != ''
          AND COALESCE(suspended_at, '') = ''
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
        CREATE INDEX IF NOT EXISTS idx_ssot_pending_writes_status_requested
        ON ssot_pending_writes (status, requested_at)
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
        CREATE INDEX IF NOT EXISTS idx_notion_index_documents_root_page
        ON notion_index_documents (root_id, source_page_id, section_ordinal)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_notion_retrieval_audit_agent_created
        ON notion_retrieval_audit (agent_id, created_at)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_synthesis_cards_source
        ON memory_synthesis_cards (source_kind, source_key)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_memory_synthesis_cards_status_updated
        ON memory_synthesis_cards (status, updated_at)
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
    _ensure_column(conn, "notification_outbox", "attempt_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "notification_outbox", "last_attempt_at", "TEXT")
    _ensure_column(conn, "notification_outbox", "next_attempt_at", "TEXT")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_notification_outbox_pending_target_channel_next_attempt
        ON notification_outbox (delivered_at, target_kind, channel_kind, next_attempt_at, id)
        """
    )
    _ensure_column(conn, "ssot_pending_writes", "expires_at", "TEXT NOT NULL DEFAULT ''")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ssot_pending_writes_status_expires
        ON ssot_pending_writes (status, expires_at)
        """
    )
    _ensure_column(conn, "notion_identity_claims", "failure_reason", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "notion_identity_claims", "verified_notion_user_id", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "notion_identity_claims", "verified_notion_email", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "notion_webhook_events", "attempt_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "notion_webhook_events", "last_attempt_at", "TEXT")
    _ensure_column(conn, "notion_webhook_events", "last_error", "TEXT NOT NULL DEFAULT ''")
    if cfg is not None:
        _backfill_ssot_pending_write_expiry(conn, ttl_seconds=cfg.ssot_pending_write_ttl_seconds)
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_notion_webhook_events_status_received
        ON notion_webhook_events (batch_status, received_at)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_arclink_users_email
        ON arclink_users (LOWER(email))
        WHERE email != ''
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_arclink_deployments_prefix
        ON arclink_deployments (LOWER(prefix))
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_arclink_deployments_user_status
        ON arclink_deployments (user_id, status)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_arclink_subscriptions_stripe_id
        ON arclink_subscriptions (stripe_subscription_id)
        WHERE stripe_subscription_id != ''
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_arclink_subscriptions_user_status
        ON arclink_subscriptions (user_id, status)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_arclink_provisioning_jobs_idempotency
        ON arclink_provisioning_jobs (idempotency_key)
        WHERE idempotency_key != ''
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_arclink_provisioning_jobs_deployment_status
        ON arclink_provisioning_jobs (deployment_id, status)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_arclink_dns_records_host_type
        ON arclink_dns_records (LOWER(hostname), UPPER(record_type))
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_arclink_admins_email
        ON arclink_admins (LOWER(email))
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_arclink_audit_log_target_created
        ON arclink_audit_log (target_kind, target_id, created_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_arclink_events_subject_created
        ON arclink_events (subject_kind, subject_id, created_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_arclink_channel_pairing_codes_source
        ON arclink_channel_pairing_codes (source_session_id, status, expires_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_arclink_channel_pairing_codes_claimed
        ON arclink_channel_pairing_codes (claimed_session_id, claimed_at)
        WHERE claimed_session_id != ''
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_arclink_webhook_events_received
        ON arclink_webhook_events (provider, received_at)
        """
    )
    _ensure_column(conn, "arclink_users", "entitlement_state", "TEXT NOT NULL DEFAULT 'none'")
    _ensure_column(conn, "arclink_users", "entitlement_updated_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "arclink_users", "password_hash", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "arclink_admins", "password_hash", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "arclink_admins", "role_scope_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(conn, "arclink_admins", "totp_enabled", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "arclink_admins", "totp_secret_ref", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "arclink_admins", "totp_verified_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "arclink_onboarding_sessions", "completed_at", "TEXT NOT NULL DEFAULT ''")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_arclink_user_sessions_user_status
        ON arclink_user_sessions (user_id, status, expires_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_arclink_admin_sessions_admin_status
        ON arclink_admin_sessions (admin_id, status, expires_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_arclink_admin_roles_role_active
        ON arclink_admin_roles (role, revoked_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_arclink_admin_totp_admin_status
        ON arclink_admin_totp_factors (admin_id, status)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_arclink_onboarding_active_identity
        ON arclink_onboarding_sessions (LOWER(channel), LOWER(channel_identity))
        WHERE channel_identity != ''
          AND status IN (
            'started',
            'collecting',
            'checkout_open',
            'payment_pending',
            'paid',
            'provisioning_ready',
            'first_contacted'
          )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_arclink_onboarding_checkout_session
        ON arclink_onboarding_sessions (checkout_session_id)
        WHERE checkout_session_id != ''
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_arclink_onboarding_events_session_created
        ON arclink_onboarding_events (session_id, created_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_arclink_onboarding_events_type_created
        ON arclink_onboarding_events (event_type, created_at)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_arclink_action_intents_idempotency
        ON arclink_action_intents (idempotency_key)
        WHERE idempotency_key != ''
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_arclink_action_intents_target_status
        ON arclink_action_intents (target_kind, target_id, status, created_at)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS arclink_fleet_hosts (
          host_id TEXT PRIMARY KEY,
          hostname TEXT NOT NULL,
          region TEXT NOT NULL DEFAULT '',
          tags_json TEXT NOT NULL DEFAULT '{}',
          status TEXT NOT NULL DEFAULT 'active',
          drain INTEGER NOT NULL DEFAULT 0,
          capacity_slots INTEGER NOT NULL DEFAULT 10,
          observed_load INTEGER NOT NULL DEFAULT 0,
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS arclink_deployment_placements (
          placement_id TEXT PRIMARY KEY,
          deployment_id TEXT NOT NULL,
          host_id TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'active',
          placed_at TEXT NOT NULL,
          removed_at TEXT NOT NULL DEFAULT ''
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS arclink_action_attempts (
          attempt_id TEXT PRIMARY KEY,
          action_id TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'running',
          executor_adapter TEXT NOT NULL DEFAULT '',
          result_json TEXT NOT NULL DEFAULT '{}',
          error TEXT NOT NULL DEFAULT '',
          started_at TEXT NOT NULL,
          finished_at TEXT NOT NULL DEFAULT ''
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS arclink_rollouts (
          rollout_id TEXT PRIMARY KEY,
          deployment_id TEXT NOT NULL DEFAULT '',
          version_tag TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'planned',
          wave_count INTEGER NOT NULL DEFAULT 1,
          current_wave INTEGER NOT NULL DEFAULT 0,
          waves_json TEXT NOT NULL DEFAULT '[]',
          rollback_plan_json TEXT NOT NULL DEFAULT '{}',
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_arclink_fleet_hosts_hostname
        ON arclink_fleet_hosts (LOWER(hostname))
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_arclink_deployment_placements_deployment
        ON arclink_deployment_placements (deployment_id, status)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_arclink_deployment_placements_host
        ON arclink_deployment_placements (host_id, status)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_arclink_action_attempts_action
        ON arclink_action_attempts (action_id, started_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_arclink_rollouts_deployment_status
        ON arclink_rollouts (deployment_id, status)
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


def _backfill_ssot_pending_write_expiry(conn: sqlite3.Connection, *, ttl_seconds: int) -> int:
    rows = conn.execute(
        """
        SELECT pending_id, requested_at
        FROM ssot_pending_writes
        WHERE expires_at IS NULL OR expires_at = ''
        """
    ).fetchall()
    if not rows:
        return 0
    for row in rows:
        conn.execute(
            "UPDATE ssot_pending_writes SET expires_at = ? WHERE pending_id = ?",
            (
                expiry_from_iso(str(row["requested_at"] or ""), ttl_seconds=ttl_seconds),
                str(row["pending_id"] or "").strip(),
            ),
        )
    conn.commit()
    return len(rows)


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


ARCLINK_DEPLOYMENT_PREFIX_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$")
ARCLINK_DEPLOYMENT_PREFIX_DENYLIST = {
    "admin",
    "api",
    "billing",
    "cloudflare",
    "root",
    "stripe",
    "support",
    "ssh",
    "traefik",
    "www",
}
ARCLINK_PREFIX_ADJECTIVES = (
    "amber",
    "brisk",
    "calm",
    "clear",
    "cobalt",
    "dawn",
    "ember",
    "lunar",
    "novel",
    "silver",
)
ARCLINK_PREFIX_NOUNS = (
    "anchor",
    "bridge",
    "harbor",
    "lantern",
    "signal",
    "summit",
    "thread",
    "vault",
    "vertex",
    "window",
)
ARCLINK_ENTITLEMENT_STATES = {"none", "paid", "comp", "past_due", "cancelled"}
ARCLINK_PROVISIONING_JOB_STATUSES = {"queued", "running", "succeeded", "failed", "cancelled"}
ARCLINK_PROVISIONING_JOB_TRANSITIONS = {
    "queued": {"running", "cancelled"},
    "running": {"succeeded", "failed", "cancelled"},
    "failed": {"queued"},
    "succeeded": set(),
    "cancelled": set(),
}


def _arclink_json(value: Mapping[str, Any] | Sequence[Any] | str | None, *, default: str = "{}") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("ArcLink JSON fields must contain valid JSON") from exc
        return value
    return json.dumps(value, sort_keys=True)


def _arclink_commit(conn: sqlite3.Connection, *, commit: bool) -> None:
    if commit:
        conn.commit()


def _arclink_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def normalize_arclink_deployment_prefix(prefix: str) -> str:
    normalized = str(prefix or "").strip().lower()
    if not ARCLINK_DEPLOYMENT_PREFIX_PATTERN.match(normalized):
        raise ValueError("ArcLink deployment prefix must be 3-32 lowercase letters, numbers, or hyphens")
    for denied in ARCLINK_DEPLOYMENT_PREFIX_DENYLIST:
        if denied in normalized:
            raise ValueError(f"ArcLink deployment prefix contains a reserved substring: {denied}")
    return normalized


def _arclink_rng_choice(values: Sequence[str], rng: Any | None) -> str:
    if rng is not None and hasattr(rng, "choice"):
        return str(rng.choice(tuple(values)))
    return str(secrets.choice(tuple(values)))


def _arclink_rng_hex4(rng: Any | None) -> str:
    if rng is not None and hasattr(rng, "getrandbits"):
        return f"{int(rng.getrandbits(16)):04x}"
    return secrets.token_hex(2)


def generate_arclink_deployment_prefix(*, rng: Any | None = None) -> str:
    prefix = "-".join(
        (
            _arclink_rng_choice(ARCLINK_PREFIX_ADJECTIVES, rng),
            _arclink_rng_choice(ARCLINK_PREFIX_NOUNS, rng),
            _arclink_rng_hex4(rng),
        )
    )
    return normalize_arclink_deployment_prefix(prefix)


def reserve_generated_arclink_deployment_prefix(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    user_id: str,
    base_domain: str = "",
    agent_id: str = "",
    session_id: str = "",
    bootstrap_request_id: str = "",
    status: str = "reserved",
    metadata: Mapping[str, Any] | None = None,
    rng: Any | None = None,
    max_attempts: int = 8,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for _ in range(max(1, int(max_attempts))):
        prefix = generate_arclink_deployment_prefix(rng=rng)
        try:
            return reserve_arclink_deployment_prefix(
                conn,
                deployment_id=deployment_id,
                user_id=user_id,
                prefix=prefix,
                base_domain=base_domain,
                agent_id=agent_id,
                session_id=session_id,
                bootstrap_request_id=bootstrap_request_id,
                status=status,
                metadata=metadata,
            )
        except ValueError as exc:
            last_error = exc
            if "already reserved" not in str(exc):
                raise
    raise ValueError("ArcLink could not reserve a unique deployment prefix after retries") from last_error


def reserve_arclink_deployment_prefix(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    user_id: str,
    prefix: str,
    base_domain: str = "",
    agent_id: str = "",
    session_id: str = "",
    bootstrap_request_id: str = "",
    status: str = "reserved",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    clean_prefix = normalize_arclink_deployment_prefix(prefix)
    now = utc_now_iso()
    try:
        conn.execute(
            """
            INSERT INTO arclink_deployments (
              deployment_id, user_id, prefix, base_domain, agent_id, session_id,
              bootstrap_request_id, status, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                deployment_id,
                user_id,
                clean_prefix,
                base_domain,
                agent_id,
                session_id,
                bootstrap_request_id,
                status,
                _arclink_json(metadata),
                now,
                now,
            ),
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"ArcLink deployment prefix is already reserved: {clean_prefix}") from exc
    conn.commit()
    return dict(conn.execute("SELECT * FROM arclink_deployments WHERE deployment_id = ?", (deployment_id,)).fetchone())


def upsert_arclink_user(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    email: str = "",
    display_name: str = "",
    status: str = "active",
    stripe_customer_id: str = "",
    entitlement_state: str | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    entitlement_supplied = entitlement_state is not None
    clean_state = str(entitlement_state if entitlement_supplied else "none").strip().lower()
    if clean_state not in ARCLINK_ENTITLEMENT_STATES:
        raise ValueError(f"unsupported ArcLink entitlement state: {clean_state}")
    now = utc_now_iso()
    entitlement_updated_at = now if entitlement_supplied else ""
    conn.execute(
        """
        INSERT INTO arclink_users (
          user_id, email, display_name, status, stripe_customer_id,
          entitlement_state, entitlement_updated_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
          email = CASE WHEN excluded.email != '' THEN excluded.email ELSE arclink_users.email END,
          display_name = CASE WHEN excluded.display_name != '' THEN excluded.display_name ELSE arclink_users.display_name END,
          status = excluded.status,
          stripe_customer_id = CASE
            WHEN excluded.stripe_customer_id != '' THEN excluded.stripe_customer_id
            ELSE arclink_users.stripe_customer_id
          END,
          entitlement_state = CASE
            WHEN ? THEN excluded.entitlement_state
            ELSE arclink_users.entitlement_state
          END,
          entitlement_updated_at = CASE
            WHEN ? THEN excluded.entitlement_updated_at
            ELSE arclink_users.entitlement_updated_at
          END,
          updated_at = excluded.updated_at
        """,
        (
            user_id,
            email,
            display_name,
            status,
            stripe_customer_id,
            clean_state,
            entitlement_updated_at,
            now,
            now,
            1 if entitlement_supplied else 0,
            1 if entitlement_supplied else 0,
        ),
    )
    _arclink_commit(conn, commit=commit)
    return dict(conn.execute("SELECT * FROM arclink_users WHERE user_id = ?", (user_id,)).fetchone())


def set_arclink_user_entitlement(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    entitlement_state: str,
    stripe_customer_id: str = "",
    commit: bool = True,
) -> dict[str, Any]:
    clean_state = str(entitlement_state or "").strip().lower()
    if clean_state not in ARCLINK_ENTITLEMENT_STATES:
        raise ValueError(f"unsupported ArcLink entitlement state: {clean_state}")
    row = conn.execute("SELECT * FROM arclink_users WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        return upsert_arclink_user(
            conn,
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            entitlement_state=clean_state,
            commit=commit,
        )
    conn.execute(
        """
        UPDATE arclink_users
        SET entitlement_state = ?,
            entitlement_updated_at = ?,
            stripe_customer_id = CASE WHEN ? != '' THEN ? ELSE stripe_customer_id END,
            updated_at = ?
        WHERE user_id = ?
        """,
        (clean_state, utc_now_iso(), stripe_customer_id, stripe_customer_id, utc_now_iso(), user_id),
    )
    _arclink_commit(conn, commit=commit)
    return dict(conn.execute("SELECT * FROM arclink_users WHERE user_id = ?", (user_id,)).fetchone())


def append_arclink_event(
    conn: sqlite3.Connection,
    *,
    subject_kind: str,
    subject_id: str,
    event_type: str,
    metadata: Mapping[str, Any] | None = None,
    event_id: str = "",
    commit: bool = True,
) -> str:
    clean_id = event_id or _arclink_id("evt")
    conn.execute(
        """
        INSERT INTO arclink_events (event_id, subject_kind, subject_id, event_type, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (clean_id, subject_kind, subject_id, event_type, _arclink_json(metadata), utc_now_iso()),
    )
    _arclink_commit(conn, commit=commit)
    return clean_id


def _arclink_comp_audit_exists(conn: sqlite3.Connection, *, user_id: str, deployment_id: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM arclink_audit_log
        WHERE action = 'comp_subscription'
          AND (
            (target_kind = 'user' AND target_id = ?)
            OR (target_kind = 'deployment' AND target_id = ?)
          )
        LIMIT 1
        """,
        (user_id, deployment_id),
    ).fetchone()
    return row is not None


def arclink_deployment_entitlement_state(conn: sqlite3.Connection, *, deployment_id: str) -> str:
    row = conn.execute(
        """
        SELECT d.deployment_id, d.user_id, u.entitlement_state
        FROM arclink_deployments d
        LEFT JOIN arclink_users u ON u.user_id = d.user_id
        WHERE d.deployment_id = ?
        """,
        (deployment_id,),
    ).fetchone()
    if row is None:
        raise KeyError(deployment_id)
    user_id = str(row["user_id"] or "")
    if _arclink_comp_audit_exists(conn, user_id=user_id, deployment_id=deployment_id):
        return "comp"
    return str(row["entitlement_state"] or "none")


def arclink_deployment_can_provision(conn: sqlite3.Connection, *, deployment_id: str) -> bool:
    return arclink_deployment_entitlement_state(conn, deployment_id=deployment_id) in {"paid", "comp"}


def advance_arclink_entitlement_gate(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    commit: bool = True,
) -> bool:
    if not arclink_deployment_can_provision(conn, deployment_id=deployment_id):
        return False
    row = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = ?", (deployment_id,)).fetchone()
    if row is None:
        raise KeyError(deployment_id)
    if str(row["status"] or "") != "entitlement_required":
        return False
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE arclink_deployments
        SET status = 'provisioning_ready', updated_at = ?
        WHERE deployment_id = ? AND status = 'entitlement_required'
        """,
        (now, deployment_id),
    )
    _arclink_commit(conn, commit=commit)
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=deployment_id,
        event_type="entitlement_gate_lifted",
        metadata={"entitlement_state": arclink_deployment_entitlement_state(conn, deployment_id=deployment_id)},
        commit=commit,
    )
    return True


def advance_arclink_entitlement_gates_for_user(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    commit: bool = True,
) -> list[str]:
    rows = conn.execute(
        """
        SELECT deployment_id
        FROM arclink_deployments
        WHERE user_id = ? AND status = 'entitlement_required'
        ORDER BY created_at, deployment_id
        """,
        (user_id,),
    ).fetchall()
    advanced: list[str] = []
    for row in rows:
        deployment_id = str(row["deployment_id"] or "")
        if advance_arclink_entitlement_gate(conn, deployment_id=deployment_id, commit=commit):
            advanced.append(deployment_id)
    return advanced


def comp_arclink_subscription(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    actor_id: str,
    reason: str,
    deployment_id: str = "",
) -> dict[str, Any]:
    clean_reason = str(reason or "").strip()
    if not clean_reason:
        raise ValueError("ArcLink comp subscription actions require a reason")
    clean_deployment_id = str(deployment_id or "").strip()
    if clean_deployment_id:
        deployment = conn.execute(
            "SELECT user_id, status FROM arclink_deployments WHERE deployment_id = ?",
            (clean_deployment_id,),
        ).fetchone()
        if deployment is None:
            raise KeyError(clean_deployment_id)
        if str(deployment["user_id"] or "") != user_id:
            raise ValueError("targeted ArcLink comp deployment does not belong to user")
    target_kind = "deployment" if clean_deployment_id else "user"
    target_id = clean_deployment_id or user_id
    append_arclink_audit(
        conn,
        action="comp_subscription",
        actor_id=actor_id,
        target_kind=target_kind,
        target_id=target_id,
        reason=clean_reason,
        metadata={"user_id": user_id, "deployment_id": clean_deployment_id},
    )
    if clean_deployment_id:
        user = conn.execute("SELECT * FROM arclink_users WHERE user_id = ?", (user_id,)).fetchone()
        if user is None:
            user = upsert_arclink_user(conn, user_id=user_id, entitlement_state="none")
        else:
            user = dict(user)
        now = utc_now_iso()
        cursor = conn.execute(
            """
            UPDATE arclink_deployments
            SET status = 'provisioning_ready', updated_at = ?
            WHERE deployment_id = ? AND user_id = ? AND status = 'entitlement_required'
            """,
            (now, clean_deployment_id, user_id),
        )
        conn.commit()
        if cursor.rowcount:
            append_arclink_event(
                conn,
                subject_kind="deployment",
                subject_id=clean_deployment_id,
                event_type="entitlement_gate_lifted",
                metadata={"entitlement_state": "deployment_comp", "comp_scope": "deployment"},
            )
        return dict(user)
    user = set_arclink_user_entitlement(conn, user_id=user_id, entitlement_state="comp")
    advance_arclink_entitlement_gates_for_user(conn, user_id=user_id)
    return user


def append_arclink_audit(
    conn: sqlite3.Connection,
    *,
    action: str,
    actor_id: str = "",
    target_kind: str = "",
    target_id: str = "",
    reason: str = "",
    metadata: Mapping[str, Any] | None = None,
    audit_id: str = "",
    commit: bool = True,
) -> str:
    clean_id = audit_id or _arclink_id("aud")
    conn.execute(
        """
        INSERT INTO arclink_audit_log (
          audit_id, actor_id, action, target_kind, target_id, reason, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (clean_id, actor_id, action, target_kind, target_id, reason, _arclink_json(metadata), utc_now_iso()),
    )
    _arclink_commit(conn, commit=commit)
    return clean_id


def upsert_arclink_service_health(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    service_name: str,
    status: str,
    detail: Mapping[str, Any] | None = None,
    checked_at: str = "",
) -> None:
    checked = checked_at or utc_now_iso()
    conn.execute(
        """
        INSERT INTO arclink_service_health (deployment_id, service_name, status, checked_at, detail_json)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(deployment_id, service_name) DO UPDATE SET
          status = excluded.status,
          checked_at = excluded.checked_at,
          detail_json = excluded.detail_json
        """,
        (deployment_id, service_name, status, checked, _arclink_json(detail)),
    )
    conn.commit()


def upsert_arclink_subscription_mirror(
    conn: sqlite3.Connection,
    *,
    subscription_id: str,
    user_id: str,
    status: str,
    stripe_customer_id: str = "",
    stripe_subscription_id: str = "",
    current_period_end: str = "",
    raw: Mapping[str, Any] | None = None,
    commit: bool = True,
) -> None:
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO arclink_subscriptions (
          subscription_id, user_id, stripe_customer_id, stripe_subscription_id,
          status, current_period_end, raw_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(subscription_id) DO UPDATE SET
          user_id = excluded.user_id,
          stripe_customer_id = excluded.stripe_customer_id,
          stripe_subscription_id = excluded.stripe_subscription_id,
          status = excluded.status,
          current_period_end = excluded.current_period_end,
          raw_json = excluded.raw_json,
          updated_at = excluded.updated_at
        """,
        (
            subscription_id,
            user_id,
            stripe_customer_id,
            stripe_subscription_id,
            status,
            current_period_end,
            _arclink_json(raw),
            now,
            now,
        ),
    )
    _arclink_commit(conn, commit=commit)


def create_arclink_provisioning_job(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    deployment_id: str,
    job_kind: str,
    idempotency_key: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO arclink_provisioning_jobs (
          job_id, deployment_id, job_kind, status, idempotency_key, metadata_json, requested_at
        ) VALUES (?, ?, ?, 'queued', ?, ?, ?)
        """,
        (job_id, deployment_id, job_kind, idempotency_key, _arclink_json(metadata), utc_now_iso()),
    )
    conn.commit()


def transition_arclink_provisioning_job(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    status: str,
    error: str = "",
) -> None:
    clean_status = str(status or "").strip().lower()
    if clean_status not in ARCLINK_PROVISIONING_JOB_STATUSES:
        raise ValueError(f"unsupported ArcLink provisioning job status: {clean_status}")
    row = conn.execute("SELECT status, attempt_count FROM arclink_provisioning_jobs WHERE job_id = ?", (job_id,)).fetchone()
    if row is None:
        raise KeyError(job_id)
    current = str(row["status"] or "")
    if clean_status != current and clean_status not in ARCLINK_PROVISIONING_JOB_TRANSITIONS.get(current, set()):
        raise ValueError(f"invalid ArcLink provisioning job transition: {current} -> {clean_status}")
    now = utc_now_iso()
    reset_for_retry = current == "failed" and clean_status == "queued"
    started_at = now if clean_status == "running" else None
    finished_at = now if clean_status in {"succeeded", "failed", "cancelled"} else None
    attempt_increment = 1 if clean_status == "running" and current != "running" else 0
    conn.execute(
        """
        UPDATE arclink_provisioning_jobs
        SET status = ?,
            attempt_count = attempt_count + ?,
            started_at = CASE WHEN ? THEN NULL ELSE COALESCE(?, started_at) END,
            finished_at = CASE WHEN ? THEN NULL ELSE COALESCE(?, finished_at) END,
            error = ?
        WHERE job_id = ?
        """,
        (clean_status, attempt_increment, reset_for_retry, started_at, reset_for_retry, finished_at, error, job_id),
    )
    conn.commit()


def arclink_drift_checks(conn: sqlite3.Connection) -> list[dict[str, str]]:
    checks = [
        (
            "deployment_agent_missing",
            "arclink_deployments",
            "deployment_id",
            "agent_id",
            "agents",
            "agent_id",
        ),
        (
            "deployment_session_missing",
            "arclink_deployments",
            "deployment_id",
            "session_id",
            "onboarding_sessions",
            "session_id",
        ),
        (
            "deployment_bootstrap_request_missing",
            "arclink_deployments",
            "deployment_id",
            "bootstrap_request_id",
            "bootstrap_requests",
            "request_id",
        ),
        (
            "subscription_user_missing",
            "arclink_subscriptions",
            "subscription_id",
            "user_id",
            "arclink_users",
            "user_id",
        ),
    ]
    drift: list[dict[str, str]] = []
    for kind, source_table, source_id_col, ref_col, target_table, target_col in checks:
        rows = conn.execute(
            f"""
            SELECT s.{source_id_col} AS source_id, s.{ref_col} AS reference_id
            FROM {source_table} s
            LEFT JOIN {target_table} t ON t.{target_col} = s.{ref_col}
            WHERE s.{ref_col} != '' AND t.{target_col} IS NULL
            """
        ).fetchall()
        for row in rows:
            drift.append(
                {
                    "kind": kind,
                    "source_id": str(row["source_id"] or ""),
                    "reference_id": str(row["reference_id"] or ""),
                }
            )
    return drift


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
    org_profile_person_id: str | None = None,
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
        "org_profile_person_id": _clean_text(
            existing.get("org_profile_person_id")
            if org_profile_person_id is None
            else org_profile_person_id
        ),
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
    if row["org_profile_person_id"] and not row["suspended_at"]:
        duplicate = conn.execute(
            """
            SELECT unix_user, agent_id
            FROM agent_identity
            WHERE org_profile_person_id = ?
              AND COALESCE(suspended_at, '') = ''
              AND unix_user != ?
            LIMIT 1
            """,
            (row["org_profile_person_id"], row["unix_user"]),
        ).fetchone()
        if duplicate is not None:
            raise ValueError(
                "org_profile_person_id "
                f"{row['org_profile_person_id']} is already linked to "
                f"{duplicate['agent_id'] or duplicate['unix_user']}"
            )
    try:
        conn.execute(
            """
            INSERT INTO agent_identity (
              unix_user, agent_id, org_profile_person_id, human_display_name, agent_name, claimed_notion_email,
              notion_user_id, notion_user_email, verification_status, write_mode,
              verified_at, suspended_at, verification_source, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(unix_user) DO UPDATE SET
              agent_id = excluded.agent_id,
              org_profile_person_id = excluded.org_profile_person_id,
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
                row["org_profile_person_id"],
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
        if "idx_agent_identity_org_profile_person_active_unique" in str(exc):
            raise ValueError(f"org_profile_person_id {row['org_profile_person_id']} is already linked") from exc
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
        org_profile_person_id=str(identity.get("org_profile_person_id") or ""),
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
        org_profile_person_id=str(identity.get("org_profile_person_id") or ""),
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
                label="ArcLink verification database",
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
        title="ArcLink Verification",
        description=(
            "Self-serve verification claims for shared ArcLink Notion access. "
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
        label="ArcLink verification database",
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


def expire_stale_ssot_pending_writes(conn: sqlite3.Connection) -> int:
    now_iso = utc_now_iso()
    cursor = conn.execute(
        """
        UPDATE ssot_pending_writes
        SET status = 'expired',
            decision_surface = CASE
              WHEN decision_surface = '' THEN 'expiry'
              ELSE decision_surface
            END,
            decided_by_actor = CASE
              WHEN decided_by_actor = '' THEN 'system'
              ELSE decided_by_actor
            END,
            decided_at = COALESCE(decided_at, ?),
            decision_note = CASE
              WHEN decision_note = '' THEN 'expired before user approval'
              ELSE decision_note
            END
        WHERE status = 'pending'
          AND expires_at != ''
          AND expires_at < ?
        """,
        (now_iso, now_iso),
    )
    conn.commit()
    return int(cursor.rowcount or 0)


def _trash_notion_identity_claim_page(
    *,
    claim: dict[str, Any],
    settings: dict[str, str],
    notion_kwargs: dict[str, Any],
) -> bool:
    page_id = str(claim.get("notion_page_id") or "").strip()
    if not page_id:
        return False
    try:
        update_notion_page(
            page_id=page_id,
            token=settings["token"],
            api_version=settings["api_version"],
            payload={"in_trash": True},
            **notion_kwargs,
        )
    except Exception:
        return False
    return True


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
                        "text": {"content": f"ArcLink Verification: {unix_user}"},
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
                                        "ArcLink will verify the edit automatically."
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
                                "text": {"content": f"ArcLink Unix user: {unix_user}"},
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
    _trash_notion_identity_claim_page(
        claim=claim,
        settings=settings,
        notion_kwargs=notion_kwargs,
    )
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


def generate_ssot_pending_write_id() -> str:
    return f"ssotw_{secrets.token_hex(8)}"


class RateLimitError(RuntimeError):
    def __init__(self, message: str, *, retry_after_seconds: int, scope: str) -> None:
        super().__init__(message)
        self.retry_after_seconds = int(retry_after_seconds)
        self.scope = scope


class SSOTApprovalRequired(PermissionError):
    def __init__(
        self,
        message: str,
        *,
        owner_identity: str = "",
        owner_source: str = "",
    ) -> None:
        super().__init__(message)
        self.owner_identity = str(owner_identity or "").strip()
        self.owner_source = str(owner_source or "").strip()


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


def _resolved_onboarding_full_name(sender_display_name: str) -> str:
    return str(sender_display_name or "").strip()


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
    resolved_name = _resolved_onboarding_full_name(sender_display_name)
    if existing is not None:
        answers = existing.get("answers", {})
        if (
            resolved_name
            and str(existing.get("state") or "") == "awaiting-name"
            and not str(answers.get("full_name") or "").strip()
        ):
            return save_onboarding_session(
                conn,
                session_id=str(existing["session_id"]),
                state="awaiting-purpose",
                answers={"full_name": resolved_name},
                chat_id=chat_id,
                sender_username=sender_username,
                sender_display_name=resolved_name,
            )
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
    initial_state = "awaiting-purpose" if resolved_name else "awaiting-name"
    initial_answers = {"full_name": resolved_name} if resolved_name else {}
    conn.execute(
        """
        INSERT INTO onboarding_sessions (
          session_id, platform, chat_id, sender_id, sender_username, sender_display_name,
          state, answers_json, created_at, updated_at, last_prompt_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            platform,
            chat_id,
            sender_id,
            sender_username or None,
            sender_display_name or None,
            initial_state,
            json_dumps(initial_answers),
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


def is_ip_in_cidrs(value: str, cidrs: str) -> bool:
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        return False
    for raw_cidr in str(cidrs or "").split(","):
        cidr = raw_cidr.strip()
        if not cidr:
            continue
        try:
            if parsed in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def backend_client_allowed(remote_ip: str) -> bool:
    normalized = str(remote_ip or "").strip()
    if is_loopback_ip(normalized):
        return True
    return is_ip_in_cidrs(normalized, os.environ.get("ARCLINK_BACKEND_ALLOWED_CIDRS", ""))


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

    if added or removed or new_warnings or default_changed:
        bits: list[str] = []
        if added:
            bits.append(f"added={','.join(added)}")
        if removed:
            bits.append(f"removed={','.join(removed)}")
        if new_warnings:
            bits.append(f"warnings={len(new_warnings)}")
        if default_changed:
            bits.append(f"default_changed={','.join(default_changed)}")
        queue_notification(
            conn,
            target_kind="operator",
            target_id=cfg.operator_notify_channel_id or cfg.operator_notify_platform or "operator",
            channel_kind=cfg.operator_notify_platform or "tui-only",
            message="Vault catalog changed: " + "; ".join(bits),
        )
        if added or removed or default_changed:
            queue_notification(
                conn,
                target_kind="curator",
                target_id="curator",
                channel_kind="brief-fanout",
                message=(
                    f"catalog-reload: added={len(added)} removed={len(removed)} "
                    f"default_changed={len(default_changed)} warnings={len(new_warnings)}"
                ),
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
    existing opt-out - only adds missing rows."""
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


def _notification_due_now(next_attempt_at: str | None) -> bool:
    due_at = parse_utc_iso(next_attempt_at)
    return due_at is None or due_at <= utc_now()


def _queue_curator_fanout_agent_notification(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    message: str,
    source_notification_id: int = 0,
) -> int:
    normalized_agent_id = str(agent_id or "").strip()
    if not normalized_agent_id:
        raise ValueError("curator fanout agent id is required")
    now_iso = utc_now_iso()
    existing = conn.execute(
        """
        SELECT id, next_attempt_at
        FROM notification_outbox
        WHERE delivered_at IS NULL
          AND target_kind = 'curator'
          AND channel_kind = 'brief-fanout'
          AND target_id = ?
        ORDER BY id ASC
        LIMIT 1
        """,
        (normalized_agent_id,),
    ).fetchone()
    if existing is not None:
        conn.execute(
            """
            UPDATE notification_outbox
            SET next_attempt_at = CASE
                  WHEN next_attempt_at IS NULL OR next_attempt_at = '' OR next_attempt_at > ?
                    THEN ?
                  ELSE next_attempt_at
                END,
                message = CASE
                  WHEN message = '' THEN ?
                  ELSE message
                END
            WHERE id = ?
            """,
            (
                now_iso,
                now_iso,
                str(message or "").strip(),
                int(existing["id"]),
            ),
        )
        return int(existing["id"])
    cursor = conn.execute(
        """
        INSERT INTO notification_outbox (
          target_kind, target_id, channel_kind, message, extra_json, created_at,
          attempt_count, last_attempt_at, next_attempt_at, delivered_at, delivery_error
        ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL, ?, NULL, NULL)
        """,
        (
            "curator",
            normalized_agent_id,
            "brief-fanout",
            str(message or "").strip(),
            json_dumps(
                {
                    "fanout_scope": "agent",
                    "source_notification_id": int(source_notification_id) if source_notification_id else 0,
                }
            ),
            now_iso,
            now_iso,
        ),
    )
    return int(cursor.lastrowid)


def _record_curator_fanout_retry(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    notification_ids: list[int],
    error_message: str,
) -> int:
    normalized_ids = [int(value) for value in notification_ids]
    if not normalized_ids:
        return 0
    placeholders = ",".join("?" for _ in normalized_ids)
    rows = conn.execute(
        f"SELECT id, attempt_count FROM notification_outbox WHERE id IN ({placeholders})",
        tuple(normalized_ids),
    ).fetchall()
    now_iso = utc_now_iso()
    max_attempts = 0
    error_text = str(error_message or "").strip()[:500]
    for row in rows:
        attempts = int(row["attempt_count"] or 0) + 1
        max_attempts = max(max_attempts, attempts)
        conn.execute(
            """
            UPDATE notification_outbox
            SET attempt_count = ?,
                last_attempt_at = ?,
                next_attempt_at = ?,
                delivery_error = ?
            WHERE id = ?
            """,
            (
                attempts,
                now_iso,
                utc_after_seconds_iso(curator_fanout_retry_delay_seconds(cfg, attempts)),
                error_text,
                int(row["id"]),
            ),
        )
    conn.commit()
    return max_attempts


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
    reclaim_stale_running_seconds: int = 0,
) -> dict[str, Any] | None:
    if int(reclaim_stale_running_seconds or 0) > 0:
        stale_before = auto_provision_stale_before_iso(int(reclaim_stale_running_seconds))
        row = conn.execute(
            """
            SELECT *
            FROM operator_actions
            WHERE action_kind = ?
              AND (
                status = 'pending'
                OR (
                  status = 'running'
                  AND COALESCE(started_at, created_at, '') < ?
                )
              )
            ORDER BY CASE WHEN status = 'pending' THEN 0 ELSE 1 END, id ASC
            LIMIT 1
            """,
            (str(action_kind or "").strip(), stale_before),
        ).fetchone()
        return _operator_action_row_to_dict(row)

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
    dedupe_by_target: bool = False,
) -> tuple[dict[str, Any], bool]:
    normalized_kind = str(action_kind or "").strip().lower()
    if not normalized_kind:
        raise ValueError("action_kind is required")
    requested_target_value = str(requested_target or "").strip()
    if dedupe_by_target:
        row = conn.execute(
            """
            SELECT *
            FROM operator_actions
            WHERE action_kind = ?
              AND requested_target = ?
              AND status IN ('pending', 'running')
            ORDER BY id DESC
            LIMIT 1
            """,
            (normalized_kind, requested_target_value),
        ).fetchone()
        active = _operator_action_row_to_dict(row)
    else:
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
            requested_target_value,
            str(requested_by or "").strip() or "operator",
            str(request_source or "").strip(),
            now_iso,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM operator_actions WHERE id = ?", (int(cursor.lastrowid),)).fetchone()
    return _operator_action_row_to_dict(row) or {}, True


def _contact_match_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _contact_handle_key(value: str) -> str:
    return _contact_match_key(str(value or "").lstrip("@"))


def _discord_contact_candidate_label(session: dict[str, Any], agent: dict[str, Any] | None) -> str:
    answers = session.get("answers", {}) if isinstance(session.get("answers"), dict) else {}
    parts = [
        str(answers.get("full_name") or session.get("sender_display_name") or "").strip(),
        str((agent or {}).get("unix_user") or answers.get("unix_user") or "").strip(),
        str(session.get("sender_username") or "").strip(),
    ]
    visible = [part for part in parts if part]
    return " / ".join(visible) or str(session.get("session_id") or "contact")


def _discord_contact_session_score(
    session: dict[str, Any],
    *,
    target: str,
    target_key: str,
    handle_key: str,
    exact_agent: dict[str, Any] | None,
    session_agent: dict[str, Any] | None,
) -> int:
    answers = session.get("answers", {}) if isinstance(session.get("answers"), dict) else {}
    linked_agent_id = str(session.get("linked_agent_id") or "").strip()
    if exact_agent is not None and linked_agent_id == str(exact_agent.get("agent_id") or ""):
        return 100
    unix_values = {
        str(answers.get("unix_user") or "").strip(),
        str((session_agent or {}).get("unix_user") or "").strip(),
    }
    if target and target in unix_values:
        return 100
    if target.startswith("onb_") and str(session.get("session_id") or "").strip() == target:
        return 100
    if target.isdigit() and str(session.get("sender_id") or "").strip() == target:
        return 95
    username_values = [
        str(session.get("sender_username") or ""),
        str(answers.get("discord_handle") or ""),
        str(answers.get("bot_username") or ""),
    ]
    if handle_key and handle_key in {_contact_handle_key(value) for value in username_values if value}:
        return 90
    name_values = [
        str(session.get("sender_display_name") or ""),
        str(answers.get("full_name") or ""),
        str(answers.get("org_profile_person_label") or ""),
        str((session_agent or {}).get("display_name") or ""),
    ]
    if target_key and target_key in {_contact_match_key(value) for value in name_values if value}:
        return 80
    return 0


def _find_discord_contact_session(
    conn: sqlite3.Connection,
    target: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized = str(target or "").strip()
    if not normalized:
        raise ValueError("retry-contact target is required")
    target_key = _contact_match_key(normalized)
    handle_key = _contact_handle_key(normalized)
    exact_agent = get_agent(conn, normalized)
    candidates: list[tuple[int, str, dict[str, Any], dict[str, Any]]] = []
    for session in list_onboarding_sessions(conn, redact_secrets=False):
        answers = session.get("answers", {}) if isinstance(session.get("answers"), dict) else {}
        platform = str(session.get("platform") or "").strip().lower()
        bot_platform = str(answers.get("bot_platform") or platform).strip().lower()
        if platform != "discord" and bot_platform != "discord":
            continue
        if str(session.get("state") or "").strip().lower() in {"denied", "cancelled"}:
            continue
        agent_id = str(session.get("linked_agent_id") or "").strip()
        if not agent_id:
            continue
        agent = get_agent(conn, agent_id)
        if agent is None:
            continue
        score = _discord_contact_session_score(
            session,
            target=normalized,
            target_key=target_key,
            handle_key=handle_key,
            exact_agent=exact_agent,
            session_agent=agent,
        )
        if score > 0:
            candidates.append((score, str(session.get("updated_at") or ""), session, agent))
    if not candidates:
        raise ValueError(f"no Discord onboarding contact found for {normalized}")
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    top_score = candidates[0][0]
    top = [item for item in candidates if item[0] == top_score]
    top_agent_ids = {str(item[3].get("agent_id") or "") for item in top}
    if len(top_agent_ids) > 1:
        labels = ", ".join(_discord_contact_candidate_label(item[2], item[3]) for item in top[:5])
        raise ValueError(f"ambiguous retry-contact target {normalized}: {labels}")
    session = top[0][2]
    agent = top[0][3]
    if str(agent.get("role") or "") != "user" or str(agent.get("status") or "") != "active":
        raise ValueError(f"retry-contact target is not an active user agent: {normalized}")
    return session, agent


def _find_discord_contact_session_for_sender(
    conn: sqlite3.Connection,
    *,
    platform: str,
    sender_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized_platform = str(platform or "").strip().lower()
    normalized_sender_id = str(sender_id or "").strip()
    if normalized_platform != "discord" or not normalized_sender_id:
        raise ValueError("self-service retry-contact is only available from a Discord onboarding DM")
    for session in list_onboarding_sessions(conn, redact_secrets=False):
        answers = session.get("answers", {}) if isinstance(session.get("answers"), dict) else {}
        if str(session.get("platform") or "").strip().lower() != "discord":
            continue
        if str(session.get("sender_id") or "").strip() != normalized_sender_id:
            continue
        bot_platform = str(answers.get("bot_platform") or session.get("platform") or "").strip().lower()
        if bot_platform != "discord":
            continue
        if str(session.get("state") or "").strip().lower() in {"denied", "cancelled"}:
            continue
        agent_id = str(session.get("linked_agent_id") or "").strip()
        if not agent_id:
            continue
        agent = get_agent(conn, agent_id)
        if agent is None:
            continue
        if str(agent.get("role") or "") != "user" or str(agent.get("status") or "") != "active":
            continue
        return session, agent
    raise ValueError("no completed Discord agent handoff was found for your onboarding user yet")


def _queue_discord_contact_retry(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    session: dict[str, Any],
    agent: dict[str, Any],
    target: str,
    actor: str,
    request_source: str,
) -> dict[str, Any]:
    session_id = str(session.get("session_id") or "").strip()
    agent_id = str(agent.get("agent_id") or "").strip()
    recipient_id = str(session.get("sender_id") or "").strip()
    if not session_id or not agent_id or not recipient_id:
        raise ValueError("matched contact is missing session, agent, or Discord recipient id")
    answers = session.get("answers", {}) if isinstance(session.get("answers"), dict) else {}
    confirmation_code = str(answers.get("discord_agent_dm_confirmation_code") or "").strip()
    if not confirmation_code:
        raise ValueError(
            "matched Discord contact has no stored Curator confirmation code; "
            "retry-contact will not send an unverifiable handoff"
        )

    payload = {
        "session_id": session_id,
        "agent_id": agent_id,
        "recipient_id": recipient_id,
        "confirmation_code": confirmation_code,
        "force": True,
    }
    action_row, created = request_operator_action(
        conn,
        action_kind="send-discord-agent-dm",
        requested_by=str(actor or "").strip() or "operator",
        request_source=str(request_source or "").strip() or "retry-contact",
        requested_target=json.dumps(payload, sort_keys=True),
        dedupe_by_target=True,
    )
    now_iso = utc_now_iso()
    save_onboarding_session(
        conn,
        session_id=session_id,
        answers={
            "discord_agent_dm_retry_requested_at": now_iso,
            "discord_agent_dm_handoff_error": "",
        },
    )
    status = str(action_row.get("status") or "pending")
    label = _discord_contact_candidate_label(session, agent)
    if created:
        message = (
            f"Queued Discord contact retry for {label}. "
            f"The root maintenance loop will send the agent-bot DM with confirmation code {confirmation_code} "
            "within about a minute."
        )
    elif status == "running":
        message = f"Discord contact retry for {label} is already running with confirmation code {confirmation_code}."
    else:
        message = f"Discord contact retry for {label} is already queued with confirmation code {confirmation_code}."
    return {
        "target": target,
        "session_id": session_id,
        "agent_id": agent_id,
        "unix_user": str(agent.get("unix_user") or ""),
        "recipient_id": recipient_id,
        "confirmation_code": confirmation_code,
        "action_id": int(action_row.get("id") or 0),
        "action_status": status,
        "created": created,
        "message": message,
    }


def retry_discord_contact(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    target: str,
    actor: str,
    request_source: str,
) -> dict[str, Any]:
    session, agent = _find_discord_contact_session(conn, target)
    return _queue_discord_contact_retry(
        conn,
        cfg,
        session=session,
        agent=agent,
        target=target,
        actor=actor,
        request_source=request_source,
    )


def retry_discord_contact_for_onboarding_user(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    platform: str,
    sender_id: str,
    actor: str,
    request_source: str,
) -> dict[str, Any]:
    session, agent = _find_discord_contact_session_for_sender(
        conn,
        platform=platform,
        sender_id=sender_id,
    )
    return _queue_discord_contact_retry(
        conn,
        cfg,
        session=session,
        agent=agent,
        target=str(session.get("session_id") or sender_id or "self"),
        actor=actor,
        request_source=request_source,
    )


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


def _ssot_pending_write_row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = dict(row)
    payload["payload"] = json_loads(str(payload.pop("payload_json") or "{}"), {})
    payload["apply_result"] = json_loads(str(payload.pop("apply_result_json") or "{}"), {})
    return payload


def _ssot_pending_write_filters(
    *,
    status: str = "",
    agent_id: str = "",
) -> tuple[str, tuple[Any, ...]]:
    params: list[Any] = []
    clauses: list[str] = []
    normalized_status = str(status or "").strip().lower()
    normalized_agent_id = str(agent_id or "").strip()
    if normalized_status:
        clauses.append("status = ?")
        params.append(normalized_status)
    if normalized_agent_id:
        clauses.append("agent_id = ?")
        params.append(normalized_agent_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, tuple(params)


def get_ssot_pending_write(
    conn: sqlite3.Connection,
    pending_id: str,
) -> dict[str, Any] | None:
    expire_stale_ssot_pending_writes(conn)
    row = conn.execute(
        "SELECT * FROM ssot_pending_writes WHERE pending_id = ?",
        (str(pending_id or "").strip(),),
    ).fetchone()
    return _ssot_pending_write_row_to_dict(row)


def list_ssot_pending_writes(
    conn: sqlite3.Connection,
    *,
    status: str = "",
    agent_id: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    expire_stale_ssot_pending_writes(conn)
    where, params = _ssot_pending_write_filters(status=status, agent_id=agent_id)
    mutable_params = list(params)
    mutable_params.append(max(1, int(limit)))
    rows = conn.execute(
        f"""
        SELECT *
        FROM ssot_pending_writes
        {where}
        ORDER BY requested_at DESC
        LIMIT ?
        """,
        tuple(mutable_params),
    ).fetchall()
    return [item for item in (_ssot_pending_write_row_to_dict(row) for row in rows) if item is not None]


def count_ssot_pending_writes(
    conn: sqlite3.Connection,
    *,
    status: str = "",
    agent_id: str = "",
) -> int:
    expire_stale_ssot_pending_writes(conn)
    where, params = _ssot_pending_write_filters(status=status, agent_id=agent_id)
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM ssot_pending_writes
        {where}
        """,
        params,
    ).fetchone()
    return int(row["count"] if row else 0)


def list_agent_ssot_pending_writes(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    status: str = "pending",
    limit: int = 25,
) -> list[dict[str, Any]]:
    return list_ssot_pending_writes(
        conn,
        status=status,
        agent_id=agent_id,
        limit=limit,
    )


def _agent_ssot_pending_stub_lines(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    limit: int = 3,
) -> list[str]:
    normalized_agent_id = str(agent_id or "").strip()
    if not normalized_agent_id:
        return []
    pending_count = count_ssot_pending_writes(
        conn,
        status="pending",
        agent_id=normalized_agent_id,
    )
    if pending_count <= 0:
        return []
    pending_rows = list_agent_ssot_pending_writes(
        conn,
        agent_id=normalized_agent_id,
        status="pending",
        limit=limit,
    )
    lines = [
        f"- Pending shared-write approvals: {pending_count}. Use ssot.pending for live status and expiry details.",
    ]
    for row in pending_rows:
        operation = str(row.get("operation") or "write")
        target_id = str(row.get("target_id") or "unknown target")
        expires_at = format_utc_iso_brief(str(row.get("expires_at") or ""))
        lines.append(f"  - {row.get('pending_id') or 'pending'}: {operation} {target_id}; expires {expires_at}")
    return lines


def _find_matching_pending_ssot_write(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    operation: str,
    target_id: str,
    payload_json: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM ssot_pending_writes
        WHERE agent_id = ?
          AND operation = ?
          AND target_id = ?
          AND payload_json = ?
          AND status = 'pending'
        ORDER BY requested_at DESC
        LIMIT 1
        """,
        (
            str(agent_id or "").strip(),
            str(operation or "").strip().lower(),
            str(target_id or "").strip(),
            str(payload_json or "{}"),
        ),
    ).fetchone()
    return _ssot_pending_write_row_to_dict(row)


def request_ssot_pending_write(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    unix_user: str,
    notion_user_id: str,
    operation: str,
    target_id: str,
    payload: dict[str, Any],
    requested_by_actor: str,
    request_source: str,
    request_reason: str,
    owner_identity: str,
    owner_source: str,
    ttl_seconds: int,
) -> tuple[dict[str, Any], bool]:
    expire_stale_ssot_pending_writes(conn)
    payload_json = json_dumps(payload)
    existing = _find_matching_pending_ssot_write(
        conn,
        agent_id=agent_id,
        operation=operation,
        target_id=target_id,
        payload_json=payload_json,
    )
    if existing is not None:
        return existing, False
    now_iso = utc_now_iso()
    expires_at = utc_after_seconds_iso(ttl_seconds)
    pending_id = generate_ssot_pending_write_id()
    conn.execute(
        """
        INSERT INTO ssot_pending_writes (
          pending_id, agent_id, unix_user, notion_user_id, operation, target_id,
          payload_json, requested_by_actor, request_source, request_reason,
          owner_identity, owner_source, status, requested_at, expires_at, decision_surface,
          decided_by_actor, decided_at, decision_note, applied_at, apply_result_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, '', '', NULL, '', NULL, '{}')
        """,
        (
            pending_id,
            str(agent_id or "").strip(),
            str(unix_user or "").strip(),
            str(notion_user_id or "").strip(),
            str(operation or "").strip().lower(),
            str(target_id or "").strip(),
            payload_json,
            str(requested_by_actor or "").strip(),
            str(request_source or "").strip(),
            str(request_reason or "").strip(),
            str(owner_identity or "").strip(),
            str(owner_source or "").strip(),
            now_iso,
            expires_at,
        ),
    )
    conn.commit()
    return get_ssot_pending_write(conn, pending_id) or {}, True

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
        SELECT a.agent_id, s.subscribed, s.source
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
        source_kind = _subscription_source_kind(str(row["source"] or ""))
        if explicit is None or source_kind != "user":
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


def _vault_content_notification_message(vault_name: str, relative_paths: Sequence[str]) -> str:
    normalized_vault = str(vault_name or "").strip()
    paths = [str(path or "").strip() for path in relative_paths if str(path or "").strip()]
    count = len(paths)
    preview = ", ".join(paths[:3])
    if count > 3:
        preview += f" ... (+{count - 3} more)"
    if normalized_vault in {"Agents_Skills", "Skills"}:
        return f"Skill library update: {count} file(s) changed" + (f": {preview}" if preview else ".")
    if normalized_vault in {"Agents_Plugins", "Plugins"}:
        return f"Plugin library update: {count} file(s) changed" + (f": {preview}" if preview else ".")
    if normalized_vault == "Agents_KB" and paths and all(path.startswith("hermes-agent-docs/") for path in paths):
        return (
            f"Hermes documentation refreshed in the agent knowledge base: {count} doc file(s) changed. "
            "Use qmd/Hermes docs for current operating details before editing skills, plugins, or config."
        )
    if normalized_vault == "Repos" and paths and all(path.startswith("hermes-agent-docs/") for path in paths):
        return (
            f"Hermes documentation refreshed in the Repos vault: {count} doc file(s) changed. "
            "Use qmd/Hermes docs for current operating details before editing skills, plugins, or config."
        )
    if normalized_vault == "Repos":
        return f"Repo knowledge update: {count} file(s) changed" + (f": {preview}" if preview else ".")
    return f"Vault update: {normalized_vault} ({count} path(s))" + (f": {preview}" if preview else ".")


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
        message = _vault_content_notification_message(vault_name, relative_paths)
        for agent_id in subscribers:
            queue_notification(
                conn,
                target_kind="user-agent",
                target_id=agent_id,
                channel_kind="vault-change",
                message=message,
                extra={
                    "vault_name": vault_name,
                    "paths": relative_paths[:50],
                    "path_count": len(relative_paths),
                    "paths_truncated": len(relative_paths) > 50,
                    "source": source,
                },
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

    if changed_by_vault and agents_notified:
        summary = ", ".join(
            f"{vault_name}({len(relative_paths)} path(s))"
            for vault_name, relative_paths in sorted(changed_by_vault.items())
        )
        for agent_id in sorted(agents_notified):
            queue_notification(
                conn,
                target_kind="curator",
                target_id=agent_id,
                channel_kind="brief-fanout",
                message=(
                    "vault-content-refresh: "
                    f"{summary}. Refresh plugin-managed context only if this agent's "
                    "subscription-scoped context changed."
                ),
                extra={
                    "source": source,
                    "vaults_changed": sorted(changed_by_vault),
                    "subscription_scoped": True,
                },
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


def _repo_sync_slug_from_remote(remote_url: str, fallback_path: Path | None = None) -> str:
    """Derive a display slug from a git remote URL, falling back to a path
    component when the URL can't be parsed. Used only for logs/status output -
    repo identity in the new rail is the on-disk path, not the slug."""
    remote = str(remote_url or "").strip()
    if remote:
        if "github.com" in remote:
            suffix = remote.split("github.com", 1)[-1].lstrip(":/").strip()
            suffix = suffix.removesuffix(".git").strip("/")
            if "/" in suffix:
                owner, repo = suffix.split("/", 1)
                slug = safe_slug(f"{owner}-{repo}", fallback="repo-sync")
                if slug:
                    return slug
        sanitized = remote.rsplit("/", 1)[-1].removesuffix(".git")
        slug = safe_slug(sanitized, fallback="repo-sync")
        if slug:
            return slug
    if fallback_path is not None:
        slug = safe_slug(fallback_path.name, fallback="repo-sync")
        if slug:
            return slug
    return "repo-sync"


def _repo_sync_canonical_from_remote(remote_url: str) -> str:
    """Render a display-oriented canonical URL. For GitHub remotes we normalize
    to https://github.com/<owner>/<repo>. For anything else we return the raw
    remote URL so operators can see where the rail is pulling from."""
    remote = str(remote_url or "").strip()
    if not remote:
        return ""
    for prefix in ("https://github.com/", "git@github.com:", "ssh://git@github.com/"):
        if remote.startswith(prefix):
            suffix = remote[len(prefix):].removesuffix(".git").strip("/")
            if "/" in suffix:
                owner, repo = suffix.split("/", 1)
                return f"https://github.com/{owner}/{repo}"
    return remote.removesuffix(".git")


def _repo_sync_has_arclink_source_marker(root_path: Path, vault_root: Path) -> bool:
    """Walk upward from root_path looking for a `.arclink-source.json` file
    that would mark this subtree as a pinned-sync target owned by a different
    rail (sync-hermes-docs-into-vault.sh and siblings). Such subtrees are
    managed by their own sync script and must not be touched here."""
    current = root_path
    while True:
        if (current / ".arclink-source.json").is_file():
            return True
        if current == vault_root or current.parent == current:
            return False
        current = current.parent


def discover_vault_repo_sources(cfg: Config) -> list[dict[str, Any]]:
    """Find every git checkout inside the vault that has an `origin` remote.

    The rail no longer scans markdown for `github.com/...` URLs and it no
    longer creates managed mirrors. An operator includes a repo by cloning it
    into the vault (for example `git clone <url> vault/Repos/<name>` or
    `vault/Clients/<client>/<repo>`); the rail then hard-syncs that checkout
    to origin/<current-branch> on every pass.

    Skips:
      * the legacy `Repos/_mirrors/` subtree (kept out of the walk even if a
        stale checkout survived)
      * any subtree flagged with `.arclink-source.json` (pinned-sync trees
        from sync-hermes-docs-into-vault.sh and peers)
      * dotfile directories (`.git`, `.github`, etc.) and symlinks
    """
    discovered: list[dict[str, Any]] = []
    vault_root = cfg.vault_dir
    if not vault_root.exists():
        return []

    for root, dirs, _files in os.walk(vault_root, topdown=True, followlinks=False):
        root_path = Path(root)
        try:
            rel_parts = root_path.relative_to(vault_root).parts
        except ValueError:
            rel_parts = ()
        if rel_parts[:2] == ("Repos", "_mirrors"):
            dirs[:] = []
            continue
        if _repo_sync_has_arclink_source_marker(root_path, vault_root):
            dirs[:] = []
            continue

        if (root_path / ".git").exists():
            remote_url = ""
            try:
                remote_url = _repo_sync_git("remote", "get-url", "origin", cwd=root_path).stdout.strip()
            except RuntimeError:
                remote_url = ""
            canonical_url = _repo_sync_canonical_from_remote(remote_url)
            slug = _repo_sync_slug_from_remote(remote_url, fallback_path=root_path)
            discovered.append(
                {
                    "slug": slug,
                    "canonical_url": canonical_url,
                    "remote_url": remote_url,
                    "source_paths": [],
                    "local_repo_paths": [str(root_path)],
                }
            )
            # Don't descend into the checkout itself; no nested git pulls.
            dirs[:] = []
            continue

        dirs[:] = [
            name
            for name in dirs
            if not name.startswith(".") and not (root_path / name).is_symlink()
        ]

    discovered.sort(key=lambda entry: (str(entry.get("canonical_url") or ""), str(entry.get("local_repo_paths", [""])[0])))
    return discovered


def _repo_sync_safe_directory_args(*paths: Path | str | None) -> list[str]:
    args: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if path is None:
            continue
        safe_path = str(Path(path).resolve(strict=False))
        if safe_path in seen:
            continue
        seen.add(safe_path)
        args.extend(["-c", f"safe.directory={safe_path}"])
    return args


def _repo_sync_git(
    *args: str,
    cwd: Path | None = None,
    timeout: int = 180,
) -> subprocess.CompletedProcess[str]:
    if shutil.which("git") is None:
        raise RuntimeError("git is not installed")
    # Vault checkouts may be created by enrolled users while the scheduled sync
    # runs as the ArcLink service user. Mark only the checkout being operated on
    # as safe for this git invocation.
    command = ["git", *_repo_sync_safe_directory_args(cwd), *args]
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = "/bin/false"
    env["SSH_ASKPASS"] = "/bin/false"
    env["GCM_INTERACTIVE"] = "Never"
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o ConnectTimeout=15")
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
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


def _repo_sync_pull_local_repo(repo_dir: Path, remote_url: str = "") -> dict[str, Any]:
    """Hard-sync a local git checkout to origin/<current-branch>.

    Mirrors the remote: fetches the current branch, discards local commits and
    uncommitted changes via `git reset --hard origin/<branch>`, and cleans
    untracked files, including gitignored paths such as node_modules/, .venv/,
    and build caches. This keeps qmd from indexing local artifacts that are not
    part of the upstream repository.

    Detached HEAD or no `origin` remote raises - the caller treats those as
    per-repo failures and keeps going through the rest of the vault.
    """
    branch = _repo_sync_current_branch(repo_dir)
    if not branch:
        raise RuntimeError(f"local repo has no active branch at {repo_dir}")
    if not remote_url:
        try:
            remote_url = _repo_sync_git("remote", "get-url", "origin", cwd=repo_dir).stdout.strip()
        except RuntimeError as exc:
            raise RuntimeError(f"local repo has no origin remote at {repo_dir}: {exc}") from exc
    if not remote_url:
        raise RuntimeError(f"local repo has no origin remote at {repo_dir}")

    try:
        current_origin = _repo_sync_git("remote", "get-url", "origin", cwd=repo_dir).stdout.strip()
    except RuntimeError:
        current_origin = ""
    if current_origin:
        if current_origin != remote_url:
            _repo_sync_git("remote", "set-url", "origin", remote_url, cwd=repo_dir)
    else:
        _repo_sync_git("remote", "add", "origin", remote_url, cwd=repo_dir)

    before_commit = _repo_sync_git("rev-parse", "HEAD", cwd=repo_dir).stdout.strip()

    _repo_sync_git("fetch", "--prune", "origin", branch, cwd=repo_dir, timeout=300)
    _repo_sync_git("reset", "--hard", f"origin/{branch}", cwd=repo_dir, timeout=300)
    _repo_sync_git("clean", "-fdx", cwd=repo_dir, timeout=300)

    after_commit = _repo_sync_git("rev-parse", "HEAD", cwd=repo_dir).stdout.strip()

    changed_rel_paths: list[str] = []
    if before_commit and after_commit and before_commit != after_commit:
        diff_output = _repo_sync_git(
            "diff",
            "--name-only",
            before_commit,
            after_commit,
            cwd=repo_dir,
            timeout=300,
        ).stdout
        changed_rel_paths = [line.strip() for line in diff_output.splitlines() if line.strip()]

    return {
        "branch": branch,
        "before_commit": before_commit,
        "commit": after_commit,
        "changed_paths": [str((repo_dir / rel_path).resolve(strict=False)) for rel_path in changed_rel_paths],
        "changed_count": len(changed_rel_paths),
    }


def sync_vault_repo_mirrors(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    repo_sources: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Walk the vault for git checkouts and hard-sync each one to its remote.

    The rail finds every directory that has a `.git/` subdirectory, reads its
    current branch and `origin` remote, and applies the hard-reset pull in
    `_repo_sync_pull_local_repo`. Operators opt a repo into the rail simply
    by cloning it into the vault; there is no implicit URL mining, no shadow
    checkout under state/, and no managed `_mirrors/` tree.
    """
    raw_sources = discover_vault_repo_sources(cfg) if repo_sources is None else list(repo_sources)
    normalized_sources: list[dict[str, Any]] = []
    for raw_source in raw_sources:
        local_paths = [str(path).strip() for path in raw_source.get("local_repo_paths") or [] if str(path).strip()]
        if not local_paths:
            continue
        remote_url = str(raw_source.get("remote_url") or "").strip()
        canonical_url = str(raw_source.get("canonical_url") or _repo_sync_canonical_from_remote(remote_url)).strip()
        slug = str(raw_source.get("slug") or _repo_sync_slug_from_remote(remote_url, fallback_path=Path(local_paths[0]))).strip()
        normalized_sources.append(
            {
                "slug": slug or _repo_sync_slug_from_remote(remote_url, fallback_path=Path(local_paths[0])),
                "canonical_url": canonical_url,
                "remote_url": remote_url,
                "source_paths": sorted(str(p).strip() for p in raw_source.get("source_paths") or [] if str(p).strip()),
                "local_repo_paths": sorted(local_paths),
            }
        )
    normalized_sources.sort(key=lambda entry: (str(entry.get("canonical_url") or ""), str(entry["local_repo_paths"][0])))

    summary: dict[str, Any] = {
        "repos_total": len(normalized_sources),
        "repos_synced": [],
        "repos_failed": [],
        "changed_paths": [],
        "repo_statuses": [],
    }

    state_dir = _repo_sync_state_dir(cfg)
    state_dir.mkdir(parents=True, exist_ok=True)

    for source in normalized_sources:
        slug = str(source["slug"])
        remote_url = str(source.get("remote_url") or "")
        syncs: list[dict[str, Any]] = []
        failures: list[str] = []
        for repo_path in source["local_repo_paths"]:
            try:
                result = _repo_sync_pull_local_repo(Path(repo_path), remote_url)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{repo_path}:{exc}")
                continue
            syncs.append({"path": repo_path, **result})
            summary["changed_paths"].extend(result["changed_paths"])

        status_entry: dict[str, Any] = {
            "slug": slug,
            "canonical_url": str(source["canonical_url"]),
            "remote_url": remote_url,
            "source_paths": list(source["source_paths"]),
            "local_repo_paths": list(source["local_repo_paths"]),
            "mode": "in-place-pull",
        }
        if syncs:
            status_entry["syncs"] = syncs
            summary["repos_synced"].append(slug)
        if failures:
            status_entry["errors"] = failures
            summary["repos_failed"].extend(failures)
        summary["repo_statuses"].append(status_entry)

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
    include_curator: bool = True,
) -> list[dict[str, Any]]:
    where = ["delivered_at IS NULL"]
    if not include_user_agent:
        where.append("target_kind != 'user-agent'")
    if not include_curator:
        where.append("target_kind != 'curator'")
    rows = conn.execute(
        f"""
        SELECT id, target_kind, target_id, channel_kind, message, extra_json, created_at, delivery_error,
               attempt_count, last_attempt_at, next_attempt_at
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
    now_iso = utc_now_iso()
    row = conn.execute(
        """
        SELECT 1
        FROM notification_outbox
        WHERE delivered_at IS NULL
          AND target_kind = 'curator'
          AND channel_kind = 'brief-fanout'
          AND (next_attempt_at IS NULL OR next_attempt_at = '' OR next_attempt_at <= ?)
        LIMIT 1
        """
    , (now_iso,)).fetchone()
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
                {"text": "Approve", "callback_data": f"arclink:{normalized_scope}:approve:{target}"},
                {"text": "Deny", "callback_data": f"arclink:{normalized_scope}:deny:{target}"},
            ]]
        }
    }


def _short_commit(value: str) -> str:
    text = str(value or "").strip()
    return text[:12] if len(text) >= 12 else text


PIN_UPGRADE_NOTIFY_LIMIT = 1
_PIN_UPGRADE_ACTION_SETTING_PREFIX = "pin_upgrade_action:"
_PIN_UPGRADE_TOKEN_RE = re.compile(r"^[0-9a-f]{16}$")


def _normalize_pin_upgrade_notify_limit(value: Any) -> int:
    try:
        limit = int(value or PIN_UPGRADE_NOTIFY_LIMIT)
    except (TypeError, ValueError):
        return PIN_UPGRADE_NOTIFY_LIMIT
    return max(1, min(limit, 10))


def _normalize_pin_upgrade_item(item: dict[str, Any]) -> dict[str, str]:
    normalized = {
        "component": str(item.get("component") or "").strip(),
        "kind": str(item.get("kind") or "").strip(),
        "field": str(item.get("field") or "").strip(),
        "current": str(item.get("current") or "").strip(),
        "target": str(item.get("target") or "").strip(),
        "throttle_target": str(item.get("throttle_target") or item.get("target") or "").strip(),
    }
    if not normalized["component"]:
        raise ValueError("pin upgrade action item is missing component")
    if not normalized["target"]:
        raise ValueError(f"pin upgrade action item for {normalized['component']} is missing target")
    return normalized


def register_pin_upgrade_action(
    conn: sqlite3.Connection,
    *,
    items: Sequence[dict[str, Any]],
    install_items: Sequence[dict[str, Any]] | None = None,
    notify_limit: int = PIN_UPGRADE_NOTIFY_LIMIT,
) -> str:
    """Persist a compact callback token for one pinned-component digest."""
    normalized_items = [_normalize_pin_upgrade_item(dict(item)) for item in items]
    normalized_install_items = [
        _normalize_pin_upgrade_item(dict(item))
        for item in (install_items if install_items is not None else normalized_items)
    ]
    if not normalized_items:
        raise ValueError("pin upgrade action requires at least one digest item")
    if not normalized_install_items:
        raise ValueError("pin upgrade action requires at least one install item")
    payload_core = {
        "items": normalized_items,
        "install_items": normalized_install_items,
        "notify_limit": _normalize_pin_upgrade_notify_limit(notify_limit),
    }
    token = hashlib.sha256(json_dumps(payload_core).encode("utf-8")).hexdigest()[:16]
    payload = {
        "token": token,
        "created_at": utc_now_iso(),
        **payload_core,
    }
    upsert_setting(conn, f"{_PIN_UPGRADE_ACTION_SETTING_PREFIX}{token}", json_dumps(payload))
    return token


def get_pin_upgrade_action_payload(conn: sqlite3.Connection, token: str) -> dict[str, Any] | None:
    normalized_token = str(token or "").strip().lower()
    if not _PIN_UPGRADE_TOKEN_RE.fullmatch(normalized_token):
        return None
    payload = json_loads(
        get_setting(conn, f"{_PIN_UPGRADE_ACTION_SETTING_PREFIX}{normalized_token}", ""),
        {},
    )
    if not isinstance(payload, dict) or str(payload.get("token") or "") != normalized_token:
        return None
    try:
        items = [_normalize_pin_upgrade_item(dict(item)) for item in payload.get("items") or []]
        install_items = [
            _normalize_pin_upgrade_item(dict(item))
            for item in payload.get("install_items") or items
        ]
    except (TypeError, ValueError):
        return None
    if not items or not install_items:
        return None
    return {
        "token": normalized_token,
        "created_at": str(payload.get("created_at") or ""),
        "items": items,
        "install_items": install_items,
        "notify_limit": _normalize_pin_upgrade_notify_limit(payload.get("notify_limit")),
    }


def dismiss_pin_upgrade_action(conn: sqlite3.Connection, token: str) -> dict[str, Any]:
    payload = get_pin_upgrade_action_payload(conn, token)
    if payload is None:
        raise ValueError("unknown pinned-component upgrade action")
    now_iso = utc_now_iso()
    silenced: list[str] = []
    notify_limit = _normalize_pin_upgrade_notify_limit(payload.get("notify_limit"))
    for item in payload["items"]:
        cursor = conn.execute(
            """
            UPDATE pin_upgrade_notifications
            SET silenced = 1,
                notify_count = CASE
                  WHEN notify_count < ? THEN ?
                  ELSE notify_count
                END,
                last_notified_at = COALESCE(last_notified_at, ?)
            WHERE component = ?
              AND target_value IN (?, ?)
            """,
            (
                notify_limit,
                notify_limit,
                now_iso,
                item["component"],
                item["target"],
                item["throttle_target"],
            ),
        )
        if cursor.rowcount:
            silenced.append(item["component"])
    conn.commit()
    return {
        "token": payload["token"],
        "components": [item["component"] for item in payload["items"]],
        "silenced": silenced,
    }


def operator_pin_upgrade_action_extra(
    cfg: Config,
    *,
    token: str,
) -> dict[str, Any] | None:
    normalized_token = str(token or "").strip().lower()
    if not _PIN_UPGRADE_TOKEN_RE.fullmatch(normalized_token):
        return None
    callback_install = f"arclink:pin-upgrade:install:{normalized_token}"
    callback_dismiss = f"arclink:pin-upgrade:dismiss:{normalized_token}"
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


def operator_upgrade_action_extra(
    cfg: Config,
    *,
    upstream_commit: str,
) -> dict[str, Any] | None:
    target = str(upstream_commit or "").strip()
    if not target:
        return None
    callback_install = f"arclink:upgrade:install:{target}"
    callback_dismiss = f"arclink:upgrade:dismiss:{target}"
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


def operator_ssot_write_action_extra(
    cfg: Config,
    *,
    pending_id: str,
) -> dict[str, Any] | None:
    target = str(pending_id or "").strip()
    if not target:
        return None
    callback_approve = f"arclink:ssot:approve:{target}"
    callback_deny = f"arclink:ssot:deny:{target}"
    if cfg.operator_notify_platform == "telegram" and cfg.curator_telegram_onboarding_enabled:
        return {
            "telegram_reply_markup": {
                "inline_keyboard": [[
                    {"text": "Deny", "callback_data": callback_deny},
                    {"text": "Approve", "callback_data": callback_approve},
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
                            "label": "Deny",
                            "custom_id": callback_deny,
                        },
                        {
                            "type": 2,
                            "style": 1,
                            "label": "Approve",
                            "custom_id": callback_approve,
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


def _safe_token_surface(raw: str, default: str = "agent-refresh") -> str:
    value = re.sub(r"[^a-z0-9_.:-]+", "-", str(raw or "").strip().lower()).strip("-")
    return (value or default)[:80]


def _harden_agent_token_path(token_path: Path, *, unix_user: str) -> None:
    try:
        user_info = pwd.getpwnam(unix_user)
    except KeyError:
        user_info = None
    try:
        token_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    if user_info is not None:
        try:
            os.chown(token_path.parent, user_info.pw_uid, user_info.pw_gid)
        except PermissionError:
            pass
    try:
        token_path.parent.chmod(0o700)
    except PermissionError:
        pass
    if token_path.exists():
        if user_info is not None:
            try:
                os.chown(token_path, user_info.pw_uid, user_info.pw_gid)
            except PermissionError:
                pass
        try:
            token_path.chmod(0o600)
        except PermissionError:
            pass


def ensure_agent_mcp_bootstrap_token(
    conn: sqlite3.Connection,
    *,
    unix_user: str,
    hermes_home: str | Path,
    token_path: str | Path | None = None,
    actor: str = "agent-refresh",
) -> dict[str, Any]:
    """Ensure an active user agent has a valid private ArcLink MCP token file.

    This is shared by bare-metal realignment and Docker supervision. It never
    returns the raw token; callers get only repair status and paths so logs stay
    secret-free.
    """
    unix_user = str(unix_user or "").strip()
    if not unix_user:
        raise ValueError("unix_user is required")
    hermes_home_path = Path(hermes_home).expanduser()
    token_file = (
        Path(token_path).expanduser()
        if token_path is not None
        else hermes_home_path / "secrets" / "arclink-bootstrap-token"
    )

    agent = conn.execute(
        """
        SELECT agent_id, unix_user, display_name, hermes_home
        FROM agents
        WHERE role = 'user' AND status = 'active' AND unix_user = ?
        ORDER BY last_enrolled_at DESC
        LIMIT 1
        """,
        (unix_user,),
    ).fetchone()
    if agent is None:
        return {"applied": False, "reason": "no_active_agent", "unix_user": unix_user}

    agent_id = str(agent["agent_id"] or "")
    expected_home = str(agent["hermes_home"] or "").strip()
    if expected_home and os.path.abspath(expected_home) != os.path.abspath(str(hermes_home_path)):
        raise RuntimeError(f"refusing to repair MCP auth for {agent_id}: Hermes home mismatch")

    _harden_agent_token_path(token_file, unix_user=unix_user)
    try:
        existing_raw = token_file.read_text(encoding="utf-8").strip()
    except OSError:
        existing_raw = ""
    if existing_raw:
        try:
            token_row = validate_token(conn, existing_raw)
        except Exception:
            token_row = None
        if token_row is not None and str(token_row["agent_id"] or "") == agent_id:
            _harden_agent_token_path(token_file, unix_user=unix_user)
            return {
                "applied": True,
                "changed": False,
                "agent_id": agent_id,
                "unix_user": unix_user,
                "token_file": str(token_file),
            }

    surface = _safe_token_surface(actor)
    now_iso = utc_now_iso()
    conn.execute(
        """
        UPDATE bootstrap_tokens
        SET revoked_at = ?,
            revoked_by_surface = ?,
            revoked_by_actor = ?,
            revocation_reason = 'superseded by repaired agent MCP bootstrap token'
        WHERE agent_id = ? AND revoked_at IS NULL
        """,
        (now_iso, surface, unix_user, agent_id),
    )

    new_raw = generate_raw_token()
    token_id = generate_token_id()
    conn.execute(
        """
        INSERT INTO bootstrap_tokens (
          token_id, agent_id, token_hash, requester_identity, source_ip, issued_at, issued_by,
          activation_request_id, activated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
        """,
        (
            token_id,
            agent_id,
            hash_token(new_raw),
            str(agent["display_name"] or unix_user),
            "127.0.0.1",
            now_iso,
            surface,
            now_iso,
        ),
    )

    token_file.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(token_file.parent), prefix=f".{token_file.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(new_raw + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            tmp_path.chmod(0o600)
        except PermissionError:
            pass
        try:
            user_info = pwd.getpwnam(unix_user)
        except KeyError:
            user_info = None
        if user_info is not None:
            try:
                os.chown(tmp_path, user_info.pw_uid, user_info.pw_gid)
            except PermissionError:
                pass
        os.replace(tmp_path, token_file)
        _harden_agent_token_path(token_file, unix_user=unix_user)
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise

    conn.commit()
    return {
        "applied": True,
        "changed": True,
        "agent_id": agent_id,
        "unix_user": unix_user,
        "token_id": token_id,
        "token_file": str(token_file),
    }


def _subscription_source_kind(raw_source: str) -> str:
    source = str(raw_source or "").strip().lower()
    return "user" if source == "user" else "default"


def effective_subscriptions_for_agent(conn: sqlite3.Connection, agent_id: str) -> list[dict[str, Any]]:
    explicit_rows = {str(row["vault_name"]): dict(row) for row in subscriptions_for_agent(conn, agent_id)}
    result: list[dict[str, Any]] = []
    for vault in list_vaults(conn):
        vault_name = str(vault["vault_name"])
        explicit = explicit_rows.get(vault_name)
        default_subscribed = int(vault.get("default_subscribed") or 0)
        raw_source = str(explicit.get("source") or "").strip() if explicit else "default"
        source_kind = _subscription_source_kind(raw_source)
        effective_subscribed = int(explicit.get("subscribed") or 0) if source_kind == "user" and explicit is not None else default_subscribed
        explicit_override = source_kind == "user"
        if explicit_override:
            subscription_state = "user-opt-in" if effective_subscribed == 1 else "user-opt-out"
            hierarchy_source = "user-override"
        else:
            subscription_state = "default-in" if default_subscribed == 1 else "default-out"
            hierarchy_source = "catalog-default"
        result.append(
            {
                "vault_name": vault_name,
                "vault_path": vault.get("vault_path"),
                "description": vault.get("description"),
                "brief_template": vault.get("brief_template"),
                "category": vault.get("category"),
                "owner": vault.get("owner"),
                "default_subscribed": default_subscribed,
                "subscribed": effective_subscribed,
                "effective_subscribed": bool(effective_subscribed),
                "push_enabled": bool(effective_subscribed),
                "hierarchy_source": hierarchy_source,
                "explicit_override": explicit_override,
                "subscription_state": subscription_state,
                "source": raw_source,
                "updated_at": explicit.get("updated_at") if explicit else None,
            }
        )
    return result


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


def auto_provision_unix_user_available(
    conn: sqlite3.Connection,
    unix_user: str,
    *,
    exclude_session_id: str = "",
    exclude_request_id: str = "",
) -> tuple[bool, str]:
    candidate = str(unix_user or "").strip().lower()
    if not AUTO_PROVISION_UNIX_USER_PATTERN.fullmatch(candidate):
        return False, "Use 1-31 chars: lowercase letters, digits, `_`, or `-`, starting with a letter or `_`."
    try:
        pwd.getpwnam(candidate)
        return False, f"`{candidate}` already exists on the host. Pick another Unix username."
    except KeyError:
        pass

    agent = conn.execute(
        """
        SELECT agent_id
        FROM agents
        WHERE lower(unix_user) = ?
        LIMIT 1
        """,
        (candidate,),
    ).fetchone()
    if agent is not None:
        return False, f"`{candidate}` is already registered to an ArcLink agent. Pick another Unix username."

    request = conn.execute(
        """
        SELECT request_id
        FROM bootstrap_requests
        WHERE lower(unix_user) = ?
          AND request_id != ?
          AND auto_provision = 1
          AND status IN ('pending', 'approved')
          AND COALESCE(cancelled_at, '') = ''
          AND COALESCE(denied_at, '') = ''
          AND COALESCE(provisioned_at, '') = ''
        ORDER BY requested_at DESC
        LIMIT 1
        """,
        (candidate, exclude_request_id),
    ).fetchone()
    if request is not None:
        return False, f"`{candidate}` is already reserved by an active enrollment request. Pick another Unix username."

    sessions = conn.execute(
        """
        SELECT session_id, answers_json
        FROM onboarding_sessions
        WHERE session_id != ?
          AND state NOT IN ('denied', 'completed', 'cancelled')
        ORDER BY updated_at DESC
        """,
        (exclude_session_id,),
    ).fetchall()
    for session in sessions:
        answers = json_loads(session["answers_json"], {})
        if str(answers.get("unix_user") or "").strip().lower() == candidate:
            return False, f"`{candidate}` is already being used by an active onboarding session. Pick another Unix username."

    return True, ""


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


def curator_fanout_retry_delay_seconds(cfg: Config, attempts: int) -> int:
    step = max(1, int(attempts))
    delay = cfg.curator_fanout_retry_base_seconds * (2 ** max(0, step - 1))
    return max(
        cfg.curator_fanout_retry_base_seconds,
        min(cfg.curator_fanout_retry_max_seconds, delay),
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
        home / ".local" / "share" / "arclink-agent",
        home / ".local" / "state" / "arclink-agent",
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
            owner = pwd.getpwnam(cfg.arclink_user)
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


def _first_subuid_for_user(unix_user: str, *, subuid_file: Path = Path("/etc/subuid")) -> str:
    try:
        lines = subuid_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) < 3 or parts[0] != unix_user:
            continue
        try:
            start = int(parts[1])
            count = int(parts[2])
        except ValueError:
            continue
        if start > 0 and count > 0:
            return str(start)
    return ""


def grant_agent_runtime_access(
    cfg: Config,
    *,
    unix_user: str,
    agent_id: str,
) -> dict[str, Any]:
    """Idempotently restore enrolled-user access to shared ArcLink paths."""

    setfacl_bin = shutil.which("setfacl")
    if not setfacl_bin:
        raise RuntimeError(
            "setfacl is required so enrolled users can traverse the shared ArcLink runtime"
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
        if str(candidate_root).startswith(str(cfg.arclink_home)):
            runtime_python_root = candidate_root
            for parent in candidate_root.parents:
                if not str(parent).startswith(str(cfg.arclink_home)):
                    break
                extra_traverse.append(parent)

    traverse_only = [
        cfg.arclink_home,
        cfg.repo_dir,
        cfg.private_dir,
        cfg.state_dir,
        cfg.runtime_dir,
        *extra_traverse,
    ]
    # Rootless Podman/libcrun resolves bind-mount sources from the enrolled
    # user's namespace. Execute-only ACLs are enough for normal path traversal,
    # but libcrun may still fail with EACCES while stat'ing a shared vault under
    # the service user's private tree. Grant non-recursive rX on just the mount
    # source parent chain, while keeping private repo contents protected below.
    podman_mount_source_dirs: list[Path] = []
    for parent in cfg.vault_dir.parents:
        try:
            under_arclink_home = parent == cfg.arclink_home or parent.is_relative_to(cfg.arclink_home)
        except ValueError:
            under_arclink_home = False
        if under_arclink_home:
            podman_mount_source_dirs.append(parent)
    podman_mount_source_subjects = [unix_user]
    podman_root_subuid = _first_subuid_for_user(unix_user)
    if podman_root_subuid:
        podman_mount_source_subjects.append(podman_root_subuid)
    readable_trees = [
        cfg.repo_dir / "bin",
        cfg.repo_dir / "compose",
        cfg.repo_dir / "config",
        cfg.repo_dir / "docs",
        cfg.repo_dir / "plugins",
        cfg.repo_dir / "python",
        cfg.repo_dir / "skills",
        cfg.repo_dir / "systemd",
        cfg.repo_dir / "templates",
        cfg.runtime_dir / "hermes-venv",
        cfg.runtime_dir / "hermes-agent-src",
        activation_dir,
    ]
    if runtime_python_root is not None:
        readable_trees.append(runtime_python_root)
    writable_trees = [
        cfg.vault_dir,
    ]

    applied_traverse: list[str] = []
    applied_podman_mount_sources: list[str] = []
    applied_readable: list[str] = []
    applied_writable: list[str] = []
    applied_default_acl_dirs: list[str] = []
    for target in traverse_only:
        if target.exists():
            subprocess.run([setfacl_bin, "-m", f"u:{unix_user}:--x", str(target)], check=True)
            applied_traverse.append(str(target))
    for target in podman_mount_source_dirs:
        if target.exists():
            for subject in podman_mount_source_subjects:
                subprocess.run([setfacl_bin, "-m", f"u:{subject}:rX", str(target)], check=True)
            applied_podman_mount_sources.append(str(target))
    for target in readable_trees:
        if target.exists():
            subprocess.run([setfacl_bin, "-R", "-m", f"u:{unix_user}:rX", str(target)], check=True)
            applied_readable.append(str(target))
    for target in writable_trees:
        if target.exists():
            for subject in podman_mount_source_subjects:
                subprocess.run([setfacl_bin, "-R", "-m", f"u:{subject}:rwX", str(target)], check=True)
            applied_writable.append(str(target))
            for root, dirs, _files in os.walk(target):
                root_path = Path(root)
                for subject in podman_mount_source_subjects:
                    subprocess.run([setfacl_bin, "-m", f"d:u:{subject}:rwX", str(root_path)], check=True)
                applied_default_acl_dirs.append(str(root_path))
                dirs[:] = [name for name in dirs if not (root_path / name).is_symlink()]

    return {
        "unix_user": unix_user,
        "agent_id": agent_id,
        "traverse_only": applied_traverse,
        "podman_mount_sources": applied_podman_mount_sources,
        "podman_mount_source_subjects": podman_mount_source_subjects,
        "readable_trees": applied_readable,
        "writable_trees": applied_writable,
        "default_acl_dirs": applied_default_acl_dirs,
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
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp", prefix=".arclink-activation-")
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
    notify_operator: bool = True,
    exclude_onboarding_session_id: str = "",
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
                actor="arclink-mcp",
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

    if auto_provision:
        available, reason = auto_provision_unix_user_available(
            conn,
            unix_user,
            exclude_session_id=exclude_onboarding_session_id,
        )
        if not available:
            raise ValueError(reason)

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
    provisioning_note = " On approval, ArcLink will create the Unix user and provision the host-side agent automatically." if auto_provision else ""
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
        f"{prior_note}{provisioning_note} Approve via arclink-ctl request approve {request_id}"
    )
    if cfg.operator_notify_platform == "telegram" and cfg.curator_telegram_onboarding_enabled:
        message += " or tap Approve / Deny below."
    if notify_operator:
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
                "message": "Enrollment request submitted. Once approved, ArcLink will create the Unix user and provision the host-side agent automatically.",
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
                    f"Enrollment approved for {agent_id}. ArcLink activation is ready to run."
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
        actor="arclink-provisioner",
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
    # tui_enabled is a structural invariant - every agent has TUI access, the flag exists
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
        {"name": "arclink-mcp", "url": f"http://127.0.0.1:{cfg.public_mcp_port}/mcp"},
        {"name": "arclink-qmd", "url": cfg.qmd_url},
    ]
    if cfg.extra_mcp_url:
        allowed_mcps.append({"name": cfg.extra_mcp_name, "url": cfg.extra_mcp_url})

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
    model_preset: str | None = None,
    model_string: str | None = None,
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
    resolved_model_preset = (
        str(model_preset).strip() if model_preset is not None else str(row["model_preset"] or "").strip()
    )
    resolved_model_string = (
        str(model_string).strip() if model_string is not None else str(row["model_string"] or "").strip()
    )

    conn.execute(
        """
        UPDATE agents
        SET channels_json = ?,
            home_channel_json = ?,
            display_name = ?,
            model_preset = ?,
            model_string = ?
        WHERE agent_id = ?
        """,
        (
            json_dumps(channels_value),
            json_dumps(resolved_home_channel),
            resolved_display_name,
            resolved_model_preset,
            resolved_model_string,
            agent_id,
        ),
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
        model_preset=resolved_model_preset,
        model_string=resolved_model_string,
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
    subscriptions = effective_subscriptions_for_agent(conn, agent_id)
    active = [row["vault_name"] for row in subscriptions if bool(row.get("push_enabled"))]
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
    return effective_subscriptions_for_agent(conn, agent_id)


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
        for path in user_unit_dir.glob("arclink-user-agent*"):
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
SSOT_WRITE_OPERATIONS = ("insert", "update", "append", "create_page", "create_database")
SSOT_ALLOWED_OPERATIONS = SSOT_READ_OPERATIONS + SSOT_WRITE_OPERATIONS
SSOT_FORBIDDEN_OPERATIONS = ("archive", "delete", "trash", "destroy")
SSOT_MAX_BLOCK_CHILDREN_PER_REQUEST = 100
SSOT_MAX_INLINE_BLOCK_DEPTH = 2
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


def _notion_payload_people_property_names(payload: dict[str, Any]) -> list[str]:
    """Return every property name on the payload whose value carries a
    people-shaped assignment (a ``people`` list). Excludes the
    provenance-only "Changed By" column. Treats column names as opaque so
    a workspace using DRI / Lead / Reviewer / Approver gets the same
    ownership-channel protections as a workspace using Owner / Assignee.
    """
    properties = (payload or {}).get("properties") if isinstance(payload, dict) else None
    if not isinstance(properties, dict):
        return []
    names: list[str] = []
    for property_name, prop in properties.items():
        if not isinstance(prop, dict):
            continue
        if str(property_name or "").strip() == "Changed By":
            continue
        people = prop.get("people")
        if isinstance(people, list):
            names.append(str(property_name))
    return names


def _notion_payload_people_identities(payload: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (identity, source) pairs across every people-shaped column on
    the payload - the broad form of _notion_property_people_identities that
    iterates dynamic column names instead of a fixed Owner/Assignee tuple.
    """
    candidates: list[tuple[str, str]] = []
    for property_name in _notion_payload_people_property_names(payload):
        candidates.extend(_notion_property_people_identities(payload, property_name))
    return candidates


def _notion_principal_identities(payload: dict[str, Any]) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    candidates.extend(_notion_payload_people_identities(payload))
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
    first people-typed column (in declaration order, opaque to column name)
    -> created_by -> ('', 'needs-approval'). The first explicit assignment
    wins regardless of whether the workspace named the column Owner, DRI,
    Lead, etc. - see _notion_payload_people_identities.
    """
    for value, source in _notion_payload_people_identities(payload):
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


def _agent_has_prior_brokered_page_write(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    page_id: str,
) -> bool:
    normalized_page_id = str(page_id or "").strip()
    if not normalized_page_id:
        return False
    try:
        normalized_page_id = extract_notion_space_id(normalized_page_id)
    except ValueError:
        normalized_page_id = str(page_id or "").strip()
    row = conn.execute(
        """
        SELECT 1
        FROM ssot_access_audit
        WHERE agent_id = ?
          AND target_id = ?
          AND decision = 'allow'
          AND operation IN ('insert', 'update', 'append', 'create_page')
        ORDER BY id DESC
        LIMIT 1
        """,
        (str(agent_id or "").strip(), normalized_page_id),
    ).fetchone()
    return row is not None


def _page_access_matches_identity(
    payload: dict[str, Any],
    *,
    agent_row: sqlite3.Row,
    identity: dict[str, Any],
    conn: sqlite3.Connection | None = None,
    allow_prior_agent_touch: bool = False,
) -> tuple[bool, str]:
    match_values = {value.lower() for value in _ssot_identity_match_values(agent_row, identity)}
    for value, source in _notion_principal_identities(payload):
        normalized = _normalize_email(value) if "@" in value else value.strip().lower()
        if normalized in match_values:
            return True, source
    # Do not let local broker history override an explicit people-typed
    # assignment that points at somebody else. Treat every people-typed
    # column as an ownership channel, not just Owner/Assignee - a workspace
    # may have named the column DRI, Lead, Reviewer, Approver, etc.
    if _notion_payload_people_identities(payload):
        return False, "ownership-mismatch"
    last_edited_by = payload.get("last_edited_by") if isinstance(payload, dict) else {}
    # Local broker history is only meant to bridge over non-human integration
    # edits so a page does not fall out of scope immediately after ArcLink
    # writes it. If another human is now the last editor, require a fresh
    # human-based scope signal instead of extending the old thread forever.
    if isinstance(last_edited_by, dict) and str(last_edited_by.get("type") or "").strip() == "person":
        return False, "ownership-mismatch"
    if allow_prior_agent_touch and conn is not None:
        page_id = str(payload.get("id") or "").strip()
        if page_id and _agent_has_prior_brokered_page_write(
            conn,
            agent_id=str(agent_row["agent_id"] or ""),
            page_id=page_id,
        ):
            return True, "agent-write-history"
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
        SELECT i.agent_id, i.unix_user,
               COALESCE(NULLIF(i.human_display_name, ''), a.display_name) AS display_name
        FROM agent_identity i
        JOIN agents a ON a.agent_id = i.agent_id AND a.unix_user = i.unix_user
        WHERE a.role = 'user'
          AND a.status = 'active'
          AND i.verification_status = 'verified'
          AND (i.suspended_at IS NULL OR i.suspended_at = '')
          AND (
            i.agent_id = ?
            OR i.notion_user_id = ?
            OR LOWER(i.notion_user_email) = ?
          )
        ORDER BY i.updated_at DESC
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
        SELECT o.agent_id, o.unix_user, a.display_name
        FROM notion_identity_overrides o
        JOIN agents a ON a.agent_id = o.agent_id AND a.unix_user = o.unix_user
        WHERE a.role = 'user'
          AND a.status = 'active'
          AND (
            o.notion_user_id = ?
            OR LOWER(o.notion_user_email) = ?
          )
        ORDER BY o.updated_at DESC
        LIMIT 1
        """,
        (
            normalized_owner,
            normalized_email,
        ),
    ).fetchone()
    if override_row is not None:
        return dict(override_row)
    return None


def _notion_event_entity_ref(payload: dict[str, Any]) -> tuple[str, str]:
    entity = payload.get("entity")
    if not isinstance(entity, dict):
        return "", ""
    entity_id = str(entity.get("id") or "").strip()
    entity_type = str(entity.get("type") or entity.get("object") or "").strip().lower()
    return entity_id, entity_type


def _short_notion_ref(value: str, *, length: int = 8) -> str:
    text = str(value or "").strip()
    compact = text.replace("-", "")
    if len(compact) >= length and all(ch in "0123456789abcdefABCDEF" for ch in compact[:length]):
        return compact[:length].lower()
    return text[:length] if text else "unknown"


def _notion_event_entity_label(payload: dict[str, Any]) -> str:
    entity_id, entity_type = _notion_event_entity_ref(payload)
    object_type = entity_type or str(payload.get("object") or "item").strip().lower() or "item"
    title = ""
    if object_type == "page" or (isinstance(payload.get("properties"), dict) and not entity_type):
        title = _notion_title_from_page(payload)
    if not title and object_type in {"database", "data_source"}:
        raw_title = payload.get("title")
        if isinstance(raw_title, list):
            title = "".join(
                str(part.get("plain_text") or "").strip()
                for part in raw_title
                if isinstance(part, dict)
            ).strip()
    if not title:
        entity = payload.get("entity")
        if isinstance(entity, dict):
            for key in ("title", "name", "display_name"):
                candidate = str(entity.get(key) or "").strip()
                if candidate:
                    title = candidate
                    break
    short_id = _short_notion_ref(entity_id or str(payload.get("id") or ""))
    readable_type = object_type.replace("_", " ") if object_type else "item"
    if title:
        return f"{title} ({readable_type} {short_id})"
    return f"{readable_type} {short_id}"


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
        if entity_type == "data_source":
            return (
                retrieve_notion_data_source(
                    data_source_id=entity_id,
                    token=settings["token"],
                    api_version=settings["api_version"],
                ),
                True,
            )
        if entity_type == "file_upload":
            return (
                retrieve_notion_file_upload(
                    file_upload_id=entity_id,
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
        if str(target_meta.get("kind") or "").strip() == "data_source":
            return (
                retrieve_notion_data_source(
                    data_source_id=entity_id,
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
    space_url = str(config_env_value("ARCLINK_SSOT_NOTION_SPACE_URL", "")).strip()
    space_id = str(config_env_value("ARCLINK_SSOT_NOTION_SPACE_ID", "")).strip()
    space_kind = str(config_env_value("ARCLINK_SSOT_NOTION_SPACE_KIND", "")).strip()
    root_page_url = str(config_env_value("ARCLINK_SSOT_NOTION_ROOT_PAGE_URL", "")).strip()
    root_page_id = str(config_env_value("ARCLINK_SSOT_NOTION_ROOT_PAGE_ID", "")).strip()
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
        "token": str(config_env_value("ARCLINK_SSOT_NOTION_TOKEN", "")).strip(),
        "api_version": str(
            config_env_value("ARCLINK_SSOT_NOTION_API_VERSION", DEFAULT_NOTION_API_VERSION)
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


def _split_config_list(raw_value: str) -> list[str]:
    items: list[str] = []
    for chunk in str(raw_value or "").replace("\r", "\n").split("\n"):
        for value in chunk.split(","):
            normalized = str(value or "").strip()
            if normalized:
                items.append(normalized)
    return items


def _notion_index_collection_name() -> str:
    return str(config_env_value("ARCLINK_NOTION_INDEX_COLLECTION_NAME", "notion-shared") or "").strip() or "notion-shared"


def _notion_index_dir(cfg: Config) -> Path:
    raw_value = str(config_env_value("ARCLINK_NOTION_INDEX_DIR", str(cfg.state_dir / "notion-index")) or "").strip()
    return Path(raw_value or (cfg.state_dir / "notion-index")).expanduser().resolve()


def _notion_index_markdown_dir(cfg: Config) -> Path:
    return _notion_index_dir(cfg) / "markdown"


def _notion_index_full_sweep_interval_seconds() -> int:
    raw = str(config_env_value("ARCLINK_NOTION_INDEX_FULL_SWEEP_INTERVAL_SECONDS", "3600") or "").strip()
    try:
        return max(300, int(raw))
    except ValueError:
        return 3600


def _notion_reindex_unresolved_max_attempts() -> int:
    raw = str(config_env_value("ARCLINK_NOTION_REINDEX_UNRESOLVED_MAX_ATTEMPTS", "6") or "").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 6


def _configured_notion_index_root_refs() -> list[str]:
    explicit = _split_config_list(config_env_value("ARCLINK_NOTION_INDEX_ROOTS", ""))
    if explicit:
        return explicit
    fallback = (
        str(config_env_value("ARCLINK_SSOT_NOTION_ROOT_PAGE_URL", "") or "").strip()
        or str(config_env_value("ARCLINK_SSOT_NOTION_SPACE_URL", "") or "").strip()
    )
    return [fallback] if fallback else []


def _resolve_notion_index_root(
    *,
    root_ref: str,
    settings: dict[str, str],
    urlopen_fn=None,
) -> dict[str, str]:
    notion_kwargs: dict[str, Any] = {}
    if urlopen_fn is not None:
        notion_kwargs["urlopen_fn"] = urlopen_fn
    target = resolve_notion_target(
        target_id=root_ref,
        token=settings["token"],
        api_version=settings["api_version"],
        **notion_kwargs,
    )
    kind = str(target.get("kind") or "").strip() or "page"
    root_id = str(target.get("id") or "").strip()
    root_url = normalize_notion_space_url(str(target.get("url") or root_ref).strip())
    root_title = str(target.get("title") or "").strip()
    root_page_id = root_id
    root_page_url = root_url
    root_page_title = root_title
    if kind == "database":
        database_payload = retrieve_notion_database(
            database_id=root_id,
            token=settings["token"],
            api_version=settings["api_version"],
            **notion_kwargs,
        )
        parent = database_payload.get("parent") if isinstance(database_payload, dict) else {}
        if not isinstance(parent, dict) or str(parent.get("type") or "").strip() != "page_id":
            raise RuntimeError("Notion index roots that point at databases must live under a page parent")
        root_page_id = str(parent.get("page_id") or "").strip()
        page_payload = retrieve_notion_page(
            page_id=root_page_id,
            token=settings["token"],
            api_version=settings["api_version"],
            **notion_kwargs,
        )
        root_page_url = normalize_notion_space_url(str(page_payload.get("url") or "").strip())
        root_page_title = _notion_title_from_page(page_payload)
    return {
        "root_ref": str(root_ref or "").strip(),
        "root_kind": kind,
        "root_id": root_id,
        "root_url": root_url,
        "root_title": root_title,
        "root_page_id": root_page_id,
        "root_page_url": root_page_url,
        "root_page_title": root_page_title,
    }


def _resolve_notion_index_roots(
    *,
    settings: dict[str, str],
    urlopen_fn=None,
) -> list[dict[str, str]]:
    roots: list[dict[str, str]] = []
    seen: set[str] = set()
    for root_ref in _configured_notion_index_root_refs():
        root = _resolve_notion_index_root(root_ref=root_ref, settings=settings, urlopen_fn=urlopen_fn)
        dedupe_key = f"{root['root_kind']}:{root['root_id']}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        roots.append(root)
    return roots


def _notion_database_title(payload: dict[str, Any]) -> str:
    title = payload.get("title") if isinstance(payload, dict) else None
    if isinstance(title, list):
        return "".join(
            str(item.get("plain_text") or "")
            for item in title
            if isinstance(item, dict)
        ).strip()
    return str(title or "").strip()


def _walk_notion_parents_to_root(
    *,
    entity_id: str,
    entity_kind: str,
    settings: dict[str, str],
    roots: list[dict[str, str]],
    notion_kwargs: dict[str, Any],
    max_depth: int = 12,
) -> tuple[dict[str, str], list[str]] | None:
    """Walk an orphan entity's parent chain until a configured root is reached.

    Returns (root, breadcrumb_prefix) where breadcrumb_prefix lists ancestor
    titles from immediately-below-root down to the orphan's immediate parent
    (the orphan's own title is NOT included, matching what `_crawl_notion_*`
    helpers expect). Returns None when the chain hits the workspace, an
    inaccessible parent, or exceeds max_depth without matching a root.
    """
    root_index: dict[tuple[str, str], dict[str, str]] = {}
    for root in roots:
        kind = (str(root.get("root_kind") or "page").strip() or "page")
        rid = extract_notion_space_id(str(root.get("root_id") or ""))
        if rid:
            root_index[(kind, rid)] = root
    visited: set[str] = set()
    ancestors: list[str] = []
    current_id = extract_notion_space_id(str(entity_id or ""))
    current_kind = entity_kind if entity_kind in ("page", "database") else "page"
    iteration = 0
    while iteration < max_depth and current_id and current_id not in visited:
        visited.add(current_id)
        iteration += 1
        try:
            if current_kind == "database":
                payload = retrieve_notion_database(
                    database_id=current_id,
                    token=settings["token"],
                    api_version=settings["api_version"],
                    **notion_kwargs,
                )
            else:
                payload = retrieve_notion_page(
                    page_id=current_id,
                    token=settings["token"],
                    api_version=settings["api_version"],
                    **notion_kwargs,
                )
        except Exception:
            return None
        match = root_index.get((current_kind, current_id))
        if match is not None:
            root_prefix: list[str] = []
            root_page_title = str(match.get("root_page_title") or "").strip()
            root_title = str(match.get("root_title") or "").strip()
            if root_page_title:
                root_prefix.append(root_page_title)
            if str(match.get("root_kind") or "").strip() == "database" and root_title and root_title != root_page_title:
                root_prefix.append(root_title)
            return match, root_prefix + list(reversed(ancestors))
        if iteration > 1:
            current_title = (
                _notion_title_from_page(payload)
                if current_kind == "page"
                else _notion_database_title(payload)
            ) or current_id
            cleaned = str(current_title or "").strip()
            if cleaned:
                ancestors.append(cleaned)
        parent = payload.get("parent") if isinstance(payload, dict) else None
        if not isinstance(parent, dict):
            return None
        parent_type = str(parent.get("type") or "").strip()
        if parent_type == "page_id":
            next_id = extract_notion_space_id(str(parent.get("page_id") or "").strip())
            next_kind = "page"
        elif parent_type == "database_id":
            next_id = extract_notion_space_id(str(parent.get("database_id") or "").strip())
            next_kind = "database"
        elif parent_type == "data_source_id":
            # Notion 2026 API exposes a row's parent as data_source_id when
            # the row was created via the data-source endpoint. The data
            # source itself sits under a database; resolve the database id
            # by retrieving the data source and following its parent.
            data_source_id = extract_notion_space_id(str(parent.get("data_source_id") or "").strip())
            if not data_source_id:
                return None
            try:
                ds_payload = retrieve_notion_data_source(
                    data_source_id=data_source_id,
                    token=settings["token"],
                    api_version=settings["api_version"],
                    **notion_kwargs,
                )
            except Exception:
                return None
            ds_parent = ds_payload.get("parent") if isinstance(ds_payload, dict) else None
            if not isinstance(ds_parent, dict):
                return None
            ds_parent_type = str(ds_parent.get("type") or "").strip()
            if ds_parent_type == "database_id":
                next_id = extract_notion_space_id(str(ds_parent.get("database_id") or "").strip())
                next_kind = "database"
            elif ds_parent_type == "page_id":
                next_id = extract_notion_space_id(str(ds_parent.get("page_id") or "").strip())
                next_kind = "page"
            else:
                return None
        else:
            return None
        if not next_id:
            return None
        current_id = next_id
        current_kind = next_kind
    return None


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
    """Return every people-typed property name in the schema, in the order
    Notion declared them. The "Changed By" provenance column is excluded -
    it tracks writers, not ownership/assignment, and is handled separately
    by ``_configured_changed_by_property``. Property names are treated as
    opaque ownership channels (Owner, Assignee, Reviewer, DRI, Lead, ...);
    callers should use these names for filtering and surfacing without
    hard-coding any specific label.
    """
    properties = schema_payload.get("properties")
    if not isinstance(properties, dict):
        return []
    names: list[str] = []
    for property_name, prop in properties.items():
        if not isinstance(prop, dict):
            continue
        if str(prop.get("type") or "").strip() != "people":
            continue
        if str(property_name or "").strip() == "Changed By":
            continue
        names.append(str(property_name))
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
            "shared Notion SSOT must expose at least one people-typed property "
            "(any name - Owner, Assignee, Reviewer, DRI, Lead, etc.) so user-scoped reads can filter by membership"
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


def _notion_property_text(prop: dict[str, Any]) -> str:
    prop_type = str(prop.get("type") or "").strip()
    if prop_type in {"status", "select"}:
        value = prop.get(prop_type)
        return str(value.get("name") or "").strip() if isinstance(value, dict) else ""
    if prop_type in {"title", "rich_text"}:
        items = prop.get(prop_type)
        if not isinstance(items, list):
            return ""
        return "".join(str(item.get("plain_text") or "").strip() for item in items if isinstance(item, dict)).strip()
    if prop_type == "multi_select":
        items = prop.get("multi_select")
        if not isinstance(items, list):
            return ""
        return ", ".join(str(item.get("name") or "").strip() for item in items if isinstance(item, dict) and str(item.get("name") or "").strip())
    if prop_type == "date":
        value = prop.get("date")
        return str(value.get("start") or "").strip() if isinstance(value, dict) else ""
    if prop_type == "people":
        people = prop.get("people")
        if not isinstance(people, list):
            return ""
        names: list[str] = []
        for person in people:
            if not isinstance(person, dict):
                continue
            name = str(person.get("name") or "").strip()
            if not name:
                person_meta = person.get("person")
                if isinstance(person_meta, dict):
                    name = str(person_meta.get("email") or "").strip()
            if name:
                names.append(name)
        return ", ".join(names)
    if prop_type == "checkbox":
        return "yes" if bool(prop.get("checkbox")) else "no"
    if prop_type == "number":
        value = prop.get("number")
        return "" if value is None else str(value)
    return ""


def _notion_named_property_text(payload: dict[str, Any], preferred_names: tuple[str, ...]) -> str:
    properties = payload.get("properties")
    if not isinstance(properties, dict):
        return ""
    lowered = {str(name).strip().lower(): name for name in properties}
    for preferred in preferred_names:
        actual_name = lowered.get(preferred.lower())
        prop = properties.get(actual_name) if actual_name else None
        if isinstance(prop, dict):
            text = _notion_property_text(prop)
            if text:
                return text
    return ""


def _people_property_iter(payload: dict[str, Any]):
    """Yield (property_name, prop_dict) for every people-typed property on
    the payload, excluding the provenance-only 'Changed By' column.
    Property names are treated as opaque ownership channels - the caller
    decides the semantics, not this helper.
    """
    properties = payload.get("properties")
    if not isinstance(properties, dict):
        return
    for property_name, prop in properties.items():
        if not isinstance(prop, dict):
            continue
        if str(prop.get("type") or "").strip() != "people":
            continue
        if str(property_name or "").strip() == "Changed By":
            continue
        yield str(property_name), prop


def _notion_all_people_names(payload: dict[str, Any]) -> list[str]:
    """Return distinct people names across every ownership-channel property
    on the payload. Used when surfacing 'who is involved' without privileging
    any specific label like Owner/Assignee.
    """
    seen: set[str] = set()
    names: list[str] = []
    for property_name, _prop in _people_property_iter(payload):
        for name in _notion_people_names(payload, property_name):
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            names.append(name)
    return names


def _notion_user_role_properties(payload: dict[str, Any], notion_user_id: str) -> list[str]:
    """Return the list of people-typed property names that contain
    ``notion_user_id`` on this payload - i.e. every ownership channel the
    user appears in for this row. Empty when the user is unset.
    """
    if not notion_user_id:
        return []
    matched: list[str] = []
    for property_name, prop in _people_property_iter(payload):
        people = prop.get("people")
        if not isinstance(people, list):
            continue
        for person in people:
            if isinstance(person, dict) and str(person.get("id") or "").strip() == notion_user_id:
                matched.append(property_name)
                break
    return matched


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


def _notion_due_bucket(date_value: str) -> tuple[int, str]:
    compact = str(date_value or "").strip()
    if not compact:
        return (4, "")
    try:
        due_date = dt.date.fromisoformat(compact[:10])
    except ValueError:
        return (4, compact[:10])
    delta = (due_date - utc_now().date()).days
    if delta < 0:
        return (0, f"overdue {due_date.isoformat()}")
    if delta == 0:
        return (1, f"due today {due_date.isoformat()}")
    if delta <= 7:
        return (2, f"due {due_date.isoformat()}")
    return (3, f"due {due_date.isoformat()}")


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
        owners = _notion_all_people_names(item)
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


def _notion_markdown_text(markdown_payload: dict[str, Any]) -> str:
    if not isinstance(markdown_payload, dict):
        return ""
    return str(markdown_payload.get("markdown") or markdown_payload.get("content") or "").strip()


NOTION_ATTACHMENT_MAX_BYTES = 25 * 1024 * 1024
NOTION_ATTACHMENT_TEXT_SUFFIXES = {
    ".txt",
    ".text",
    ".md",
    ".markdown",
    ".mdx",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".csv",
    ".tsv",
    ".xml",
    ".html",
    ".htm",
}
NOTION_ATTACHMENT_TEXT_CONTENT_TYPES = {
    "application/json",
    "application/ld+json",
    "application/xml",
    "application/yaml",
    "application/x-yaml",
    "application/csv",
}
NOTION_ATTACHMENT_BLOCK_TYPES = ("file", "pdf", "image", "audio", "video")


def _notion_rich_text_plain_text(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    return "".join(
        str(item.get("plain_text") or "")
        for item in value
        if isinstance(item, dict)
    ).strip()


def _notion_attachment_filename(*, name: str, url: str, fallback: str = "attachment") -> str:
    explicit = str(name or "").strip()
    if explicit:
        return explicit
    parsed = urlparse.urlparse(str(url or "").strip())
    candidate = Path(urlparse.unquote(parsed.path or "")).name.strip()
    return candidate or fallback


def _notion_attachment_suffix(*, filename: str, url: str, content_type: str) -> str:
    for candidate in (str(filename or "").strip(), Path(urlparse.unquote(urlparse.urlparse(str(url or "")).path or "")).name):
        suffix = Path(candidate).suffix.strip()
        if suffix:
            return suffix.lower()
    guessed = mimetypes.guess_extension(str(content_type or "").split(";", 1)[0].strip().lower())
    return str(guessed or "").lower()


def _notion_attachment_block_ref(
    block: dict[str, Any],
    *,
    page_id: str,
) -> dict[str, Any] | None:
    block_type = str(block.get("type") or "").strip().lower()
    if block_type not in NOTION_ATTACHMENT_BLOCK_TYPES:
        return None
    payload = block.get(block_type)
    if not isinstance(payload, dict):
        return None
    ref_type = str(payload.get("type") or "").strip().lower()
    if ref_type not in {"file", "external"}:
        return None
    block_id = str(block.get("id") or "").strip()
    source_payload = payload.get(ref_type)
    if not isinstance(source_payload, dict):
        return None
    url = str(source_payload.get("url") or "").strip()
    filename = _notion_attachment_filename(
        name=str(payload.get("name") or "").strip(),
        url=url,
        fallback=f"{block_type}-attachment",
    )
    source_locator = f"block:{page_id}:{block_id or block_type}:{block_type}"
    return {
        "page_id": page_id,
        "origin": "block",
        "origin_id": block_id,
        "origin_label": block_type,
        "source_locator": source_locator,
        "name": filename,
        "url": url,
        "content_type": "",
        "external": ref_type == "external",
        "caption": _notion_rich_text_plain_text(payload.get("caption")),
        "attachment_key": hashlib.sha1(source_locator.encode("utf-8")).hexdigest()[:12],
    }


def _notion_attachment_property_refs(page_payload: dict[str, Any], *, page_id: str) -> list[dict[str, Any]]:
    properties = page_payload.get("properties")
    if not isinstance(properties, dict):
        return []
    refs: list[dict[str, Any]] = []
    for property_name, prop in properties.items():
        if not isinstance(prop, dict) or str(prop.get("type") or "").strip() != "files":
            continue
        values = prop.get("files")
        if not isinstance(values, list):
            continue
        for index, item in enumerate(values):
            if not isinstance(item, dict):
                continue
            ref_type = str(item.get("type") or "").strip().lower()
            if ref_type not in {"file", "external"}:
                continue
            source_payload = item.get(ref_type)
            if not isinstance(source_payload, dict):
                continue
            url = str(source_payload.get("url") or "").strip()
            source_locator = f"property:{page_id}:{property_name}:{index}"
            refs.append(
                {
                    "page_id": page_id,
                    "origin": "property",
                    "origin_id": property_name,
                    "origin_label": property_name,
                    "source_locator": source_locator,
                    "name": _notion_attachment_filename(
                        name=str(item.get("name") or "").strip(),
                        url=url,
                        fallback=f"{property_name or 'file'}-{index + 1}",
                    ),
                    "url": url,
                    "content_type": "",
                    "external": ref_type == "external",
                    "caption": "",
                    "attachment_key": hashlib.sha1(source_locator.encode("utf-8")).hexdigest()[:12],
                }
            )
    return refs


def _notion_page_attachment_refs(
    *,
    page_id: str,
    page_payload: dict[str, Any],
    notion_kwargs: dict[str, Any],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        blocks = list_notion_block_children_all(
            block_id=page_id,
            token=_require_shared_notion_settings()["token"],
            api_version=_require_shared_notion_settings()["api_version"],
            **notion_kwargs,
        )
    except Exception:
        blocks = []
    queue = [block for block in blocks if isinstance(block, dict)]
    visited_blocks: set[str] = {page_id}
    while queue:
        block = queue.pop(0)
        ref = _notion_attachment_block_ref(block, page_id=page_id)
        if ref is not None and ref["source_locator"] not in seen:
            seen.add(ref["source_locator"])
            refs.append(ref)
        block_id = str(block.get("id") or "").strip()
        block_type = str(block.get("type") or "").strip().lower()
        if not block_id or block_id in visited_blocks or not bool(block.get("has_children")):
            continue
        if block_type in {"child_page", "child_database"}:
            continue
        visited_blocks.add(block_id)
        try:
            children = list_notion_block_children_all(
                block_id=block_id,
                token=_require_shared_notion_settings()["token"],
                api_version=_require_shared_notion_settings()["api_version"],
                **notion_kwargs,
            )
        except Exception:
            continue
        queue.extend(child for child in children if isinstance(child, dict))
    for ref in _notion_attachment_property_refs(page_payload, page_id=page_id):
        if ref["source_locator"] in seen:
            continue
        seen.add(ref["source_locator"])
        refs.append(ref)
    return refs


def _download_notion_attachment(url: str, *, max_bytes: int = NOTION_ATTACHMENT_MAX_BYTES) -> tuple[bytes, str]:
    req = urlrequest.Request(
        str(url or "").strip(),
        headers={"User-Agent": "arclink-notion-index/1.0"},
        method="GET",
    )
    try:
        with urlrequest.urlopen(req, timeout=30) as response:
            raw_length = str(response.headers.get("Content-Length") or "").strip()
            if raw_length:
                try:
                    if int(raw_length) > max_bytes:
                        raise RuntimeError(f"attachment exceeds max ingest size ({raw_length} bytes)")
                except ValueError:
                    pass
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise RuntimeError(f"attachment exceeds max ingest size ({max_bytes} bytes)")
            return body, str(response.headers.get("Content-Type") or "").strip()
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
        raise RuntimeError(f"attachment download failed: http {exc.code} {detail[:120].strip()}".strip())
    except urlerror.URLError as exc:
        raise RuntimeError(f"attachment download failed: {getattr(exc, 'reason', exc)}") from exc


def _extract_pdf_text_from_path(source_path: Path) -> str:
    if shutil.which("pdftotext"):
        result = subprocess.run(
            ["pdftotext", "-enc", "UTF-8", "-nopgbrk", str(source_path), "-"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and str(result.stdout or "").strip():
            return str(result.stdout or "").strip()
    if shutil.which("docling"):
        with tempfile.TemporaryDirectory(prefix="arclink-notion-docling-") as tmpdir:
            result = subprocess.run(
                ["docling", "--from", "pdf", "--to", "md", "--output", tmpdir, str(source_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                error_text = (result.stderr or result.stdout or "docling failed").strip()
                raise RuntimeError(error_text)
            markdown_files = sorted(Path(tmpdir).rglob("*.md"))
            if markdown_files:
                text = markdown_files[0].read_text(encoding="utf-8", errors="replace").strip()
                if text:
                    return text
    raise RuntimeError("no PDF extractor available for Notion attachment")


def _extract_notion_attachment_text(ref: dict[str, Any]) -> dict[str, Any]:
    url = str(ref.get("url") or "").strip()
    filename = str(ref.get("name") or "").strip()
    caption = str(ref.get("caption") or "").strip()
    if not url:
        return {"status": "missing-url", "body": caption, "content_type": ""}
    if bool(ref.get("external")):
        body = caption or "External attachment linked from Notion."
        return {"status": "external-link", "body": body, "content_type": ""}
    data, content_type = _download_notion_attachment(url)
    normalized_content_type = str(content_type or "").split(";", 1)[0].strip().lower()
    suffix = _notion_attachment_suffix(filename=filename, url=url, content_type=normalized_content_type)
    if normalized_content_type == "application/pdf" or suffix == ".pdf":
        with tempfile.TemporaryDirectory(prefix="arclink-notion-attachment-") as tmpdir:
            source_path = Path(tmpdir) / (filename or "attachment.pdf")
            source_path.write_bytes(data)
            text = _extract_pdf_text_from_path(source_path).strip()
        combined = "\n\n".join(part for part in [caption, text] if part.strip()).strip()
        return {"status": "extracted", "body": combined, "content_type": normalized_content_type or "application/pdf"}
    if normalized_content_type.startswith("text/") or normalized_content_type in NOTION_ATTACHMENT_TEXT_CONTENT_TYPES or suffix in NOTION_ATTACHMENT_TEXT_SUFFIXES:
        text = data.decode("utf-8", errors="replace").strip()
        combined = "\n\n".join(part for part in [caption, text] if part.strip()).strip()
        return {"status": "extracted", "body": combined, "content_type": normalized_content_type}
    body = caption or f"Attachment present but body extraction is not supported for {normalized_content_type or suffix or 'this file type'}."
    return {"status": "metadata-only", "body": body, "content_type": normalized_content_type}


def _notion_attachment_doc_key(root_id: str, page_id: str, attachment_key: str, part_ordinal: int) -> str:
    return (
        f"{extract_notion_space_id(root_id)}:{extract_notion_space_id(page_id)}:"
        f"attachment:{str(attachment_key or '').strip() or 'attachment'}:{max(0, int(part_ordinal))}"
    )


def _notion_attachment_doc_relative_path(root_id: str, page_id: str, attachment_key: str, part_ordinal: int) -> Path:
    root_slug = extract_notion_space_id(root_id).replace("-", "")
    page_slug = extract_notion_space_id(page_id).replace("-", "")
    attachment_slug = safe_slug(str(attachment_key or ""), fallback="attachment")
    return Path(root_slug) / f"{page_slug}--attachment-{attachment_slug}--{max(0, int(part_ordinal)):03d}.md"


def _render_notion_index_attachment_document(
    *,
    page_title: str,
    page_url: str,
    page_id: str,
    root_title: str,
    root_id: str,
    breadcrumb: list[str],
    owners: list[str],
    last_edited_time: str,
    attachment_name: str,
    attachment_origin: str,
    attachment_status: str,
    attachment_content_type: str,
    body: str,
) -> str:
    breadcrumb_text = " > ".join(part for part in breadcrumb if str(part or "").strip())
    owner_text = ", ".join(owners) if owners else "Unassigned"
    title_text = str(page_title or "").strip() or page_id
    lines = [
        f"# {title_text}",
        "",
        f"- Notion page id: {page_id}",
        f"- Notion page url: {page_url}",
        f"- Indexed root: {str(root_title or '').strip() or root_id}",
        f"- Root id: {root_id}",
        f"- Breadcrumb: {breadcrumb_text or title_text}",
        f"- Section: Attachment: {attachment_name or 'attachment'}",
        f"- Owners: {owner_text}",
        f"- Last edited: {last_edited_time or 'unknown'}",
        f"- Attachment name: {attachment_name or 'attachment'}",
        f"- Attachment origin: {attachment_origin or 'attachment'}",
        f"- Attachment extraction: {attachment_status or 'metadata-only'}",
        f"- Attachment content type: {attachment_content_type or 'unknown'}",
        "",
        body.strip(),
        "",
    ]
    return "\n".join(lines)


def _split_large_markdown_section(heading: str, body: str, *, max_chars: int = 5000) -> list[tuple[str, str]]:
    compact_body = str(body or "").strip()
    normalized_heading = str(heading or "").strip() or "Overview"
    if len(compact_body) <= max_chars:
        return [(normalized_heading, compact_body)]
    paragraphs = [chunk.strip() for chunk in compact_body.split("\n\n") if chunk.strip()]
    if not paragraphs:
        return [(normalized_heading, compact_body[:max_chars].strip())]
    chunks: list[tuple[str, str]] = []
    current: list[str] = []
    current_size = 0
    part = 1
    for paragraph in paragraphs:
        addition = len(paragraph) + (2 if current else 0)
        if current and current_size + addition > max_chars:
            suffix = f" (part {part})" if part > 1 else ""
            chunks.append((normalized_heading + suffix, "\n\n".join(current).strip()))
            current = [paragraph]
            current_size = len(paragraph)
            part += 1
            continue
        current.append(paragraph)
        current_size += addition
    if current:
        suffix = f" (part {part})" if part > 1 else ""
        chunks.append((normalized_heading + suffix, "\n\n".join(current).strip()))
    return chunks or [(normalized_heading, compact_body)]


def _sectionize_notion_markdown(markdown_text: str) -> list[tuple[str, str]]:
    lines = str(markdown_text or "").splitlines()
    sections: list[tuple[str, str]] = []
    current_heading = "Overview"
    current_lines: list[str] = []
    saw_heading = False
    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("#"):
            if current_lines:
                sections.extend(_split_large_markdown_section(current_heading, "\n".join(current_lines).strip()))
            current_heading = stripped.lstrip("#").strip() or "Overview"
            current_lines = [line]
            saw_heading = True
            continue
        current_lines.append(line)
    if current_lines or not saw_heading:
        sections.extend(_split_large_markdown_section(current_heading, "\n".join(current_lines).strip()))
    return [(heading, body) for heading, body in sections if body or heading]


def _notion_index_doc_key(root_id: str, page_id: str, section_ordinal: int) -> str:
    return f"{extract_notion_space_id(root_id)}:{extract_notion_space_id(page_id)}:{max(0, int(section_ordinal))}"


def _notion_index_doc_relative_path(root_id: str, page_id: str, section_ordinal: int) -> Path:
    root_slug = extract_notion_space_id(root_id).replace("-", "")
    page_slug = extract_notion_space_id(page_id).replace("-", "")
    return Path(root_slug) / f"{page_slug}--{max(0, int(section_ordinal)):03d}.md"


def _render_notion_index_section_document(
    *,
    page_title: str,
    page_url: str,
    page_id: str,
    root_title: str,
    root_id: str,
    breadcrumb: list[str],
    section_heading: str,
    owners: list[str],
    last_edited_time: str,
    body: str,
) -> str:
    heading = str(section_heading or "").strip() or "Overview"
    breadcrumb_text = " > ".join(part for part in breadcrumb if str(part or "").strip())
    owner_text = ", ".join(owners) if owners else "Unassigned"
    title_text = str(page_title or "").strip() or page_id
    lines = [
        f"# {title_text}",
        "",
        f"- Notion page id: {page_id}",
        f"- Notion page url: {page_url}",
        f"- Indexed root: {str(root_title or '').strip() or root_id}",
        f"- Root id: {root_id}",
        f"- Breadcrumb: {breadcrumb_text or title_text}",
        f"- Section: {heading}",
        f"- Owners: {owner_text}",
        f"- Last edited: {last_edited_time or 'unknown'}",
        "",
        body.strip(),
        "",
    ]
    return "\n".join(lines)


def _log_notion_retrieval_audit(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    unix_user: str,
    operation: str,
    decision: str,
    query_text: str = "",
    target_id: str = "",
    root_id: str = "",
    result_count: int = 0,
    note: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO notion_retrieval_audit (
          agent_id, unix_user, operation, decision, query_text, target_id, root_id, result_count, note, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(agent_id or "").strip(),
            str(unix_user or "").strip(),
            str(operation or "").strip(),
            str(decision or "").strip(),
            str(query_text or "").strip(),
            str(target_id or "").strip(),
            str(root_id or "").strip(),
            max(0, int(result_count or 0)),
            str(note or "").strip()[:500],
            utc_now_iso(),
        ),
    )
    conn.commit()


def _index_document_lookup_key(cfg: Config, raw_file: str) -> str:
    text = str(raw_file or "").strip()
    if not text:
        return ""
    if text.startswith("qmd://"):
        text = text[len("qmd://"):]
    collection_prefix = _notion_index_collection_name().strip("/") + "/"
    if text.startswith(collection_prefix):
        text = text[len(collection_prefix):]
    path = Path(text)
    if not path.is_absolute():
        path = _notion_index_markdown_dir(cfg) / path
    return str(path.resolve())


def _upsert_notion_index_document(
    conn: sqlite3.Connection,
    *,
    doc_key: str,
    root_id: str,
    source_page_id: str,
    source_page_url: str,
    source_kind: str,
    file_path: Path,
    page_title: str,
    section_heading: str,
    section_ordinal: int,
    breadcrumb: list[str],
    owners: list[str],
    last_edited_time: str,
    content: str,
) -> bool:
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    existing = conn.execute(
        "SELECT content_hash FROM notion_index_documents WHERE doc_key = ?",
        (doc_key,),
    ).fetchone()
    changed = existing is None or str(existing["content_hash"] or "") != content_hash or not file_path.is_file()
    if changed:
        _atomic_write_text(file_path, content)
    conn.execute(
        """
        INSERT INTO notion_index_documents (
          doc_key, root_id, source_page_id, source_page_url, source_kind, file_path, page_title,
          section_heading, section_ordinal, breadcrumb_json, owners_json, last_edited_time,
          content_hash, indexed_at, state
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        ON CONFLICT(doc_key) DO UPDATE SET
          root_id = excluded.root_id,
          source_page_id = excluded.source_page_id,
          source_page_url = excluded.source_page_url,
          source_kind = excluded.source_kind,
          file_path = excluded.file_path,
          page_title = excluded.page_title,
          section_heading = excluded.section_heading,
          section_ordinal = excluded.section_ordinal,
          breadcrumb_json = excluded.breadcrumb_json,
          owners_json = excluded.owners_json,
          last_edited_time = excluded.last_edited_time,
          content_hash = excluded.content_hash,
          indexed_at = excluded.indexed_at,
          state = 'active'
        """,
        (
            doc_key,
            root_id,
            source_page_id,
            source_page_url,
            source_kind,
            str(file_path),
            page_title,
            section_heading,
            int(section_ordinal),
            json_dumps(breadcrumb),
            json_dumps(owners),
            last_edited_time,
            content_hash,
            utc_now_iso(),
        ),
    )
    return changed


def _delete_notion_index_doc(conn: sqlite3.Connection, *, doc_key: str) -> None:
    row = conn.execute("SELECT file_path FROM notion_index_documents WHERE doc_key = ?", (doc_key,)).fetchone()
    if row is not None:
        file_path = Path(str(row["file_path"] or ""))
        try:
            if file_path.is_file():
                file_path.unlink()
        except OSError:
            pass
    conn.execute("DELETE FROM notion_index_documents WHERE doc_key = ?", (doc_key,))


def _delete_notion_index_docs_for_page(
    conn: sqlite3.Connection,
    *,
    root_id: str,
    page_id: str,
) -> int:
    rows = conn.execute(
        "SELECT doc_key FROM notion_index_documents WHERE root_id = ? AND source_page_id = ?",
        (root_id, page_id),
    ).fetchall()
    removed = 0
    for row in rows:
        doc_key = str(row["doc_key"] or "")
        if doc_key:
            _delete_notion_index_doc(conn, doc_key=doc_key)
            removed += 1
    return removed


def _index_notion_page_payload(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    root: dict[str, str],
    page_payload: dict[str, Any],
    breadcrumb: list[str],
    notion_kwargs: dict[str, Any],
    active_doc_keys: set[str],
) -> int:
    page_id = str(page_payload.get("id") or "").strip()
    if not page_id:
        return 0
    page_id = extract_notion_space_id(page_id)
    if bool(page_payload.get("in_trash")) or bool(page_payload.get("archived")):
        return _delete_notion_index_docs_for_page(
            conn,
            root_id=str(root["root_id"]),
            page_id=page_id,
        )
    page_title = _notion_title_from_page(page_payload) or str(page_payload.get("url") or page_id)
    page_url = normalize_notion_space_url(str(page_payload.get("url") or "").strip())
    owners = _notion_all_people_names(page_payload)
    last_edited_time = str(page_payload.get("last_edited_time") or "").strip()
    markdown_payload = retrieve_notion_page_markdown(
        page_id=page_id,
        token=_require_shared_notion_settings()["token"],
        api_version=_require_shared_notion_settings()["api_version"],
        **notion_kwargs,
    )
    markdown_text = _notion_markdown_text(markdown_payload)
    sections = _sectionize_notion_markdown(markdown_text) or [("Overview", page_title)]
    page_doc_keys: set[str] = set()
    changed = 0
    for ordinal, (section_heading, section_body) in enumerate(sections):
        doc_key = _notion_index_doc_key(root["root_id"], page_id, ordinal)
        rel_path = _notion_index_doc_relative_path(root["root_id"], page_id, ordinal)
        file_path = _notion_index_markdown_dir(cfg) / rel_path
        content = _render_notion_index_section_document(
            page_title=page_title,
            page_url=page_url,
            page_id=page_id,
            root_title=str(root.get("root_title") or root.get("root_page_title") or ""),
            root_id=root["root_id"],
            breadcrumb=breadcrumb or [page_title],
            section_heading=section_heading,
            owners=owners,
            last_edited_time=last_edited_time,
            body=section_body,
        )
        if _upsert_notion_index_document(
            conn,
            doc_key=doc_key,
            root_id=root["root_id"],
            source_page_id=page_id,
            source_page_url=page_url,
            source_kind="page",
            file_path=file_path,
            page_title=page_title,
            section_heading=section_heading,
            section_ordinal=ordinal,
            breadcrumb=breadcrumb or [page_title],
            owners=owners,
            last_edited_time=last_edited_time,
            content=content,
        ):
            changed += 1
        active_doc_keys.add(doc_key)
        page_doc_keys.add(doc_key)
    for attachment_ref in _notion_page_attachment_refs(
        page_id=page_id,
        page_payload=page_payload,
        notion_kwargs=notion_kwargs,
    ):
        attachment_name = str(attachment_ref.get("name") or "attachment").strip() or "attachment"
        attachment_origin = str(attachment_ref.get("origin_label") or attachment_ref.get("origin") or "attachment").strip()
        try:
            attachment_result = _extract_notion_attachment_text(attachment_ref)
            attachment_body = str(attachment_result.get("body") or "").strip() or attachment_name
            attachment_status = str(attachment_result.get("status") or "").strip() or "metadata-only"
            attachment_content_type = str(attachment_result.get("content_type") or attachment_ref.get("content_type") or "").strip()
        except Exception as exc:
            attachment_body = (
                str(attachment_ref.get("caption") or "").strip()
                or f"Attachment present but extraction failed: {str(exc or 'unknown error').strip()[:240]}"
            )
            attachment_status = "extract-error"
            attachment_content_type = str(attachment_ref.get("content_type") or "").strip()
        attachment_heading = f"Attachment: {attachment_name}"
        attachment_sections = _split_large_markdown_section(attachment_heading, attachment_body)
        for ordinal, (_, attachment_part_body) in enumerate(attachment_sections):
            doc_key = _notion_attachment_doc_key(
                root["root_id"],
                page_id,
                str(attachment_ref.get("attachment_key") or ""),
                ordinal,
            )
            rel_path = _notion_attachment_doc_relative_path(
                root["root_id"],
                page_id,
                str(attachment_ref.get("attachment_key") or ""),
                ordinal,
            )
            file_path = _notion_index_markdown_dir(cfg) / rel_path
            content = _render_notion_index_attachment_document(
                page_title=page_title,
                page_url=page_url,
                page_id=page_id,
                root_title=str(root.get("root_title") or root.get("root_page_title") or ""),
                root_id=root["root_id"],
                breadcrumb=breadcrumb or [page_title],
                owners=owners,
                last_edited_time=last_edited_time,
                attachment_name=attachment_name,
                attachment_origin=attachment_origin,
                attachment_status=attachment_status,
                attachment_content_type=attachment_content_type,
                body=attachment_part_body,
            )
            if _upsert_notion_index_document(
                conn,
                doc_key=doc_key,
                root_id=root["root_id"],
                source_page_id=page_id,
                source_page_url=page_url,
                source_kind="attachment",
                file_path=file_path,
                page_title=page_title,
                section_heading=attachment_heading,
                section_ordinal=ordinal,
                breadcrumb=breadcrumb or [page_title],
                owners=owners,
                last_edited_time=last_edited_time,
                content=content,
            ):
                changed += 1
            active_doc_keys.add(doc_key)
            page_doc_keys.add(doc_key)
    stale_rows = conn.execute(
        """
        SELECT doc_key
        FROM notion_index_documents
        WHERE root_id = ? AND source_page_id = ?
        """,
        (root["root_id"], page_id),
    ).fetchall()
    for row in stale_rows:
        stale_key = str(row["doc_key"] or "")
        if stale_key and stale_key not in page_doc_keys:
            _delete_notion_index_doc(conn, doc_key=stale_key)
            changed += 1
    return changed


def _crawl_notion_database_rows(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    root: dict[str, str],
    database_id: str,
    breadcrumb_prefix: list[str],
    visited_databases: set[str],
    active_doc_keys: set[str],
    notion_kwargs: dict[str, Any],
) -> int:
    normalized_database_id = extract_notion_space_id(database_id)
    verification_database_id = get_setting(conn, NOTION_VERIFICATION_DB_ID_SETTING, "").strip()
    if verification_database_id and normalized_database_id == verification_database_id:
        return 0
    if normalized_database_id in visited_databases:
        return 0
    visited_databases.add(normalized_database_id)
    database_payload = retrieve_notion_database(
        database_id=normalized_database_id,
        token=_require_shared_notion_settings()["token"],
        api_version=_require_shared_notion_settings()["api_version"],
        **notion_kwargs,
    )
    if bool(database_payload.get("in_trash")) or bool(database_payload.get("archived")):
        return 0
    database_title = str(database_payload.get("title") or "")
    if isinstance(database_payload.get("title"), list):
        database_title = "".join(
            str(item.get("plain_text") or "")
            for item in database_payload.get("title")
            if isinstance(item, dict)
        ).strip()
    query_payload = query_notion_collection_all(
        database_id=normalized_database_id,
        token=_require_shared_notion_settings()["token"],
        api_version=_require_shared_notion_settings()["api_version"],
        payload={"page_size": 100},
        **notion_kwargs,
    )
    results = ((query_payload or {}).get("result") or {}).get("results") or []
    changed = 0
    for item in results:
        if not isinstance(item, dict):
            continue
        row_title = _notion_title_from_page(item) or str(item.get("id") or "untitled")
        breadcrumb = [part for part in [*breadcrumb_prefix, database_title, row_title] if str(part or "").strip()]
        changed += _index_notion_page_payload(
            conn,
            cfg,
            root=root,
            page_payload=item,
            breadcrumb=breadcrumb,
            notion_kwargs=notion_kwargs,
            active_doc_keys=active_doc_keys,
        )
    return changed


def _crawl_notion_page_tree(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    root: dict[str, str],
    page_id: str,
    breadcrumb_prefix: list[str],
    visited_pages: set[str],
    visited_databases: set[str],
    active_doc_keys: set[str],
    notion_kwargs: dict[str, Any],
) -> int:
    normalized_page_id = extract_notion_space_id(page_id)
    if normalized_page_id in visited_pages:
        return 0
    visited_pages.add(normalized_page_id)
    page_payload = retrieve_notion_page(
        page_id=normalized_page_id,
        token=_require_shared_notion_settings()["token"],
        api_version=_require_shared_notion_settings()["api_version"],
        **notion_kwargs,
    )
    if bool(page_payload.get("in_trash")) or bool(page_payload.get("archived")):
        return _delete_notion_index_docs_for_page(
            conn,
            root_id=str(root["root_id"]),
            page_id=normalized_page_id,
        )
    page_title = _notion_title_from_page(page_payload) or str(page_payload.get("id") or normalized_page_id)
    breadcrumb = [part for part in [*breadcrumb_prefix, page_title] if str(part or "").strip()]
    changed = _index_notion_page_payload(
        conn,
        cfg,
        root=root,
        page_payload=page_payload,
        breadcrumb=breadcrumb,
        notion_kwargs=notion_kwargs,
        active_doc_keys=active_doc_keys,
    )
    for child in list_notion_block_children_all(
        block_id=normalized_page_id,
        token=_require_shared_notion_settings()["token"],
        api_version=_require_shared_notion_settings()["api_version"],
        **notion_kwargs,
    ):
        if not isinstance(child, dict):
            continue
        child_type = str(child.get("type") or "").strip()
        child_id = str(child.get("id") or "").strip()
        if child_type == "child_page" and child_id:
            changed += _crawl_notion_page_tree(
                conn,
                cfg,
                root=root,
                page_id=child_id,
                breadcrumb_prefix=breadcrumb,
                visited_pages=visited_pages,
                visited_databases=visited_databases,
                active_doc_keys=active_doc_keys,
                notion_kwargs=notion_kwargs,
            )
        elif child_type == "child_database" and child_id:
            changed += _crawl_notion_database_rows(
                conn,
                cfg,
                root=root,
                database_id=child_id,
                breadcrumb_prefix=breadcrumb,
                visited_databases=visited_databases,
                active_doc_keys=active_doc_keys,
                notion_kwargs=notion_kwargs,
            )
    return changed


def _clear_stale_notion_index_documents_for_root(
    conn: sqlite3.Connection,
    *,
    root_id: str,
    active_doc_keys: set[str],
) -> int:
    rows = conn.execute(
        "SELECT doc_key FROM notion_index_documents WHERE root_id = ?",
        (root_id,),
    ).fetchall()
    removed = 0
    for row in rows:
        doc_key = str(row["doc_key"] or "")
        if doc_key and doc_key not in active_doc_keys:
            _delete_notion_index_doc(conn, doc_key=doc_key)
            removed += 1
    return removed


def _refresh_qmd_after_notion_sync(cfg: Config, *, embed: bool = False) -> None:
    script_path = cfg.repo_dir / "bin" / "qmd-refresh.sh"
    if not script_path.is_file():
        raise RuntimeError(f"missing qmd refresh script at {script_path}")
    command = [str(script_path), "--embed" if embed else "--skip-embed"]
    env = os.environ.copy()
    config_path = str(config_env_value("ARCLINK_CONFIG_FILE", "") or "").strip()
    if config_path:
        env["ARCLINK_CONFIG_FILE"] = config_path
    result = subprocess.run(
        command,
        cwd=str(cfg.repo_dir),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"qmd refresh failed after Notion sync: {detail or result.returncode}")


def _notion_index_run_embed() -> bool:
    return bool_env("ARCLINK_NOTION_INDEX_RUN_EMBED", default=True)


def sync_shared_notion_index(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    full: bool = False,
    page_ids: list[str] | None = None,
    database_ids: list[str] | None = None,
    actor: str = "system",
    urlopen_fn=None,
) -> dict[str, Any]:
    try:
        settings = _require_shared_notion_settings()
    except PermissionError as exc:
        return {"ok": False, "status": "skipped", "reason": str(exc), "roots": []}
    roots = _resolve_notion_index_roots(settings=settings, urlopen_fn=urlopen_fn)
    if not roots:
        return {"ok": False, "status": "skipped", "reason": "no Notion index roots configured", "roots": []}
    notion_kwargs: dict[str, Any] = {}
    if urlopen_fn is not None:
        notion_kwargs["urlopen_fn"] = urlopen_fn
    _notion_index_markdown_dir(cfg).mkdir(parents=True, exist_ok=True)
    normalized_page_ids = sorted({extract_notion_space_id(page_id) for page_id in (page_ids or []) if str(page_id or "").strip()})
    normalized_database_ids = sorted({extract_notion_space_id(database_id) for database_id in (database_ids or []) if str(database_id or "").strip()})
    changed_docs = 0
    removed_docs = 0
    indexed_pages: set[str] = set()
    unresolved_pages: list[str] = []
    unresolved_databases: list[str] = []
    processed_roots: list[str] = []

    if full or (not normalized_page_ids and not normalized_database_ids):
        for root in roots:
            active_doc_keys: set[str] = set()
            visited_pages: set[str] = set()
            visited_databases: set[str] = set()
            if root["root_kind"] == "database":
                changed_docs += _crawl_notion_database_rows(
                    conn,
                    cfg,
                    root=root,
                    database_id=root["root_id"],
                    breadcrumb_prefix=[part for part in [root.get("root_page_title"), root.get("root_title")] if str(part or "").strip()],
                    visited_databases=visited_databases,
                    active_doc_keys=active_doc_keys,
                    notion_kwargs=notion_kwargs,
                )
            else:
                changed_docs += _crawl_notion_page_tree(
                    conn,
                    cfg,
                    root=root,
                    page_id=root["root_id"],
                    breadcrumb_prefix=[],
                    visited_pages=visited_pages,
                    visited_databases=visited_databases,
                    active_doc_keys=active_doc_keys,
                    notion_kwargs=notion_kwargs,
                )
            removed_docs += _clear_stale_notion_index_documents_for_root(
                conn,
                root_id=root["root_id"],
                active_doc_keys=active_doc_keys,
            )
            indexed_pages.update(
                {
                    str(row["source_page_id"] or "")
                    for row in conn.execute(
                        "SELECT DISTINCT source_page_id FROM notion_index_documents WHERE root_id = ?",
                        (root["root_id"],),
                    ).fetchall()
                }
            )
            processed_roots.append(root["root_id"])
    else:
        root_map = {root["root_id"]: root for root in roots}
        page_rows = {}
        for page_id in normalized_page_ids:
            rows = conn.execute(
                "SELECT DISTINCT root_id, breadcrumb_json FROM notion_index_documents WHERE source_page_id = ?",
                (page_id,),
            ).fetchall()
            if not rows:
                walk = _walk_notion_parents_to_root(
                    entity_id=page_id,
                    entity_kind="page",
                    settings=settings,
                    roots=roots,
                    notion_kwargs=notion_kwargs,
                )
                if walk is None:
                    unresolved_pages.append(page_id)
                    continue
                walked_root, walked_prefix = walk
                changed_docs += _crawl_notion_page_tree(
                    conn,
                    cfg,
                    root=walked_root,
                    page_id=page_id,
                    breadcrumb_prefix=walked_prefix,
                    visited_pages=set(),
                    visited_databases=set(),
                    active_doc_keys=set(),
                    notion_kwargs=notion_kwargs,
                )
                page_rows.setdefault(page_id, set()).add(walked_root["root_id"])
                continue
            page_payload = retrieve_notion_page(
                page_id=page_id,
                token=settings["token"],
                api_version=settings["api_version"],
                **notion_kwargs,
            )
            for row in rows:
                root_id = str(row["root_id"] or "")
                root = root_map.get(root_id)
                if root is None:
                    unresolved_pages.append(page_id)
                    continue
                breadcrumb = json_loads(row["breadcrumb_json"], [])
                if not isinstance(breadcrumb, list):
                    breadcrumb = []
                changed_docs += _index_notion_page_payload(
                    conn,
                    cfg,
                    root=root,
                    page_payload=page_payload,
                    breadcrumb=[str(part) for part in breadcrumb if str(part or "").strip()],
                    notion_kwargs=notion_kwargs,
                    active_doc_keys=set(),
                )
                page_rows.setdefault(page_id, set()).add(root_id)
        for database_id in normalized_database_ids:
            matched_root = next((root for root in roots if root["root_kind"] == "database" and root["root_id"] == database_id), None)
            if matched_root is not None:
                changed_docs += _crawl_notion_database_rows(
                    conn,
                    cfg,
                    root=matched_root,
                    database_id=database_id,
                    breadcrumb_prefix=[part for part in [matched_root.get("root_page_title"), matched_root.get("root_title")] if str(part or "").strip()],
                    visited_databases=set(),
                    active_doc_keys=set(),
                    notion_kwargs=notion_kwargs,
                )
                processed_roots.append(matched_root["root_id"])
                continue
            walk = _walk_notion_parents_to_root(
                entity_id=database_id,
                entity_kind="database",
                settings=settings,
                roots=roots,
                notion_kwargs=notion_kwargs,
            )
            if walk is None:
                unresolved_databases.append(database_id)
                continue
            walked_root, walked_prefix = walk
            changed_docs += _crawl_notion_database_rows(
                conn,
                cfg,
                root=walked_root,
                database_id=database_id,
                breadcrumb_prefix=walked_prefix,
                visited_databases=set(),
                active_doc_keys=set(),
                notion_kwargs=notion_kwargs,
            )
            processed_roots.append(walked_root["root_id"])
        indexed_pages.update(page_rows.keys())

    conn.commit()
    if changed_docs or removed_docs:
        _refresh_qmd_after_notion_sync(cfg, embed=_notion_index_run_embed())
    status = "ok"
    if unresolved_pages or unresolved_databases:
        status = "warn"
    is_full_run = bool(full or (not normalized_page_ids and not normalized_database_ids))
    note_refresh_job(
        conn,
        job_name="notion-index-sync" if is_full_run else "notion-index-sync-incremental",
        job_kind="notion-index-sync",
        target_id="notion",
        schedule="webhook + 1h full sweep" if is_full_run else "webhook event",
        status=status,
        note=(
            f"full={is_full_run} roots={len(roots)} changed_docs={changed_docs} removed_docs={removed_docs} "
            f"indexed_pages={len(indexed_pages)} unresolved_pages={len(unresolved_pages)} "
            f"unresolved_databases={len(unresolved_databases)} actor={actor}"
        ),
    )
    return {
        "ok": True,
        "status": status,
        "full": is_full_run,
        "roots": roots,
        "changed_docs": changed_docs,
        "removed_docs": removed_docs,
        "indexed_pages": sorted(indexed_pages),
        "unresolved_pages": unresolved_pages,
        "unresolved_databases": unresolved_databases,
        "collection": _notion_index_collection_name(),
        "index_dir": str(_notion_index_dir(cfg)),
        "processed_roots": processed_roots,
    }


def _queue_notion_reindex_notification(
    conn: sqlite3.Connection,
    *,
    target_id: str,
    source_kind: str,
    message: str,
) -> int:
    normalized_target = str(target_id or "").strip() or "full"
    now_iso = utc_now_iso()
    existing = conn.execute(
        """
        SELECT id
        FROM notification_outbox
        WHERE delivered_at IS NULL
          AND target_kind = 'curator'
          AND channel_kind = 'notion-reindex'
          AND target_id = ?
        ORDER BY id ASC
        LIMIT 1
        """,
        (normalized_target,),
    ).fetchone()
    if existing is not None:
        conn.execute(
            """
            UPDATE notification_outbox
            SET next_attempt_at = CASE
                  WHEN next_attempt_at IS NULL OR next_attempt_at = '' OR next_attempt_at > ?
                    THEN ?
                  ELSE next_attempt_at
                END,
                message = CASE WHEN message = '' THEN ? ELSE message END,
                extra_json = ?
            WHERE id = ?
            """,
            (
                now_iso,
                now_iso,
                str(message or "").strip(),
                json_dumps({"source_kind": str(source_kind or "").strip() or "page"}),
                int(existing["id"]),
            ),
        )
        return int(existing["id"])
    cursor = conn.execute(
        """
        INSERT INTO notification_outbox (
          target_kind, target_id, channel_kind, message, extra_json, created_at,
          attempt_count, last_attempt_at, next_attempt_at, delivered_at, delivery_error
        ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL, ?, NULL, NULL)
        """,
        (
            "curator",
            normalized_target,
            "notion-reindex",
            str(message or "").strip(),
            json_dumps({"source_kind": str(source_kind or "").strip() or "page"}),
            now_iso,
            now_iso,
        ),
    )
    return int(cursor.lastrowid)


def _record_notion_reindex_retry(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    notification_ids: list[int],
    error_message: str,
) -> int:
    normalized_ids = [int(value) for value in notification_ids]
    if not normalized_ids:
        return 0
    placeholders = ",".join("?" for _ in normalized_ids)
    rows = conn.execute(
        f"SELECT id, attempt_count FROM notification_outbox WHERE id IN ({placeholders})",
        tuple(normalized_ids),
    ).fetchall()
    now_iso = utc_now_iso()
    max_attempts = 0
    error_text = str(error_message or "").strip()[:500]
    for row in rows:
        attempts = int(row["attempt_count"] or 0) + 1
        max_attempts = max(max_attempts, attempts)
        conn.execute(
            """
            UPDATE notification_outbox
            SET attempt_count = ?,
                last_attempt_at = ?,
                next_attempt_at = ?,
                delivery_error = ?
            WHERE id = ?
            """,
            (
                attempts,
                now_iso,
                utc_after_seconds_iso(curator_fanout_retry_delay_seconds(cfg, attempts)),
                error_text,
                int(row["id"]),
            ),
        )
    conn.commit()
    return max_attempts


def _notion_index_full_sweep_due(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT last_run_at FROM refresh_jobs WHERE job_name = 'notion-index-sync'"
    ).fetchone()
    if row is None:
        return True
    last_run = parse_utc_iso(str(row["last_run_at"] or "").strip())
    if last_run is None:
        return True
    return last_run <= utc_now() - dt.timedelta(seconds=_notion_index_full_sweep_interval_seconds())


def consume_notion_reindex_queue(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    limit: int = 50,
    actor: str = "curator-refresh",
) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT id, target_id, message, extra_json, next_attempt_at, attempt_count
        FROM notification_outbox
        WHERE delivered_at IS NULL
          AND target_kind = 'curator'
          AND channel_kind = 'notion-reindex'
        ORDER BY id ASC
        LIMIT ?
        """,
        (max(1, int(limit)),),
    ).fetchall()
    due_rows = [row for row in rows if _notification_due_now(str(row["next_attempt_at"] or ""))]
    run_full = _notion_index_full_sweep_due(conn)
    page_ids: list[str] = []
    database_ids: list[str] = []
    delivered_ids: list[int] = []
    reindex_targets_by_id: dict[int, tuple[str, str, int]] = {}
    for row in due_rows:
        notification_id = int(row["id"])
        delivered_ids.append(notification_id)
        target_id = str(row["target_id"] or "").strip()
        extra = json_loads(str(row["extra_json"] or "{}"), {})
        source_kind = str((extra or {}).get("source_kind") or "page").strip()
        reindex_targets_by_id[notification_id] = (
            target_id,
            source_kind,
            int(row["attempt_count"] or 0),
        )
        if target_id == "full":
            run_full = True
            continue
        if source_kind == "database":
            database_ids.append(target_id)
        else:
            page_ids.append(target_id)
    if not run_full and not page_ids and not database_ids:
        return {
            "ok": True,
            "status": "idle",
            "full": False,
            "processed_notifications": 0,
            "page_ids": [],
            "database_ids": [],
        }
    try:
        result = sync_shared_notion_index(
            conn,
            cfg,
            full=run_full,
            page_ids=page_ids,
            database_ids=database_ids,
            actor=actor,
        )
    except Exception as exc:
        if delivered_ids:
            _record_notion_reindex_retry(conn, cfg, notification_ids=delivered_ids, error_message=str(exc))
        note_refresh_job(
            conn,
            job_name="notion-index-sync" if run_full else "notion-index-sync-incremental",
            job_kind="notion-index-sync",
            target_id="notion",
            schedule="webhook + 1h full sweep" if run_full else "webhook event",
            status="fail",
            note=f"notion reindex failed (full={run_full}): {exc}",
        )
        return {
            "ok": False,
            "status": "fail",
            "error": str(exc),
            "processed_notifications": len(delivered_ids),
            "page_ids": sorted({*page_ids}),
            "database_ids": sorted({*database_ids}),
            "full": run_full,
        }
    retry_ids: list[int] = []
    dropped_ids: list[int] = []
    if not run_full and delivered_ids:
        unresolved_pages = {
            extract_notion_space_id(str(page_id or ""))
            for page_id in (result.get("unresolved_pages") or [])
            if str(page_id or "").strip()
        }
        unresolved_databases = {
            extract_notion_space_id(str(database_id or ""))
            for database_id in (result.get("unresolved_databases") or [])
            if str(database_id or "").strip()
        }
        max_unresolved_attempts = _notion_reindex_unresolved_max_attempts()
        for notification_id in delivered_ids:
            target_id, source_kind, previous_attempts = reindex_targets_by_id.get(notification_id, ("", "page", 0))
            normalized_target = extract_notion_space_id(target_id)
            unresolved = (
                source_kind == "database" and normalized_target in unresolved_databases
            ) or (
                source_kind != "database" and normalized_target in unresolved_pages
            )
            if not unresolved:
                continue
            if previous_attempts + 1 >= max_unresolved_attempts:
                dropped_ids.append(notification_id)
            else:
                retry_ids.append(notification_id)
        if retry_ids:
            _record_notion_reindex_retry(
                conn,
                cfg,
                notification_ids=retry_ids,
                error_message=(
                    "Notion entity is not reachable under configured index roots yet; "
                    "retrying so eventual-consistency and transient access races do not drop recall."
                ),
            )
        for notification_id in dropped_ids:
            conn.execute(
                """
                UPDATE notification_outbox
                SET attempt_count = attempt_count + 1,
                    last_attempt_at = ?,
                    delivered_at = ?,
                    delivery_error = ?
                WHERE id = ?
                """,
                (
                    utc_now_iso(),
                    utc_now_iso(),
                    "Notion entity stayed unresolved after retry budget; full sweep remains the backstop.",
                    notification_id,
                ),
            )
            conn.commit()

    retry_or_drop = set(retry_ids) | set(dropped_ids)
    for notification_id in delivered_ids:
        if notification_id in retry_or_drop:
            continue
        mark_notification_delivered(conn, notification_id)
    return {
        **result,
        "processed_notifications": len(delivered_ids),
        "retry_notifications": len(retry_ids),
        "dropped_unresolved_notifications": len(dropped_ids),
        "page_ids": sorted({*page_ids}),
        "database_ids": sorted({*database_ids}),
    }


def _cached_shared_notion_digest(
    *,
    settings: dict[str, str],
    notion_kwargs: dict[str, Any],
    notion_stub_cache: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    shared_key = f"shared-notion:{settings['space_id']}"
    shared_digest = notion_stub_cache.get(shared_key) if isinstance(notion_stub_cache, dict) else None
    if isinstance(shared_digest, dict):
        database_payload = shared_digest.get("database_payload") if isinstance(shared_digest.get("database_payload"), dict) else {}
        schema_payload = shared_digest.get("schema_payload") if isinstance(shared_digest.get("schema_payload"), dict) else {}
        team_result = shared_digest.get("team_result") if isinstance(shared_digest.get("team_result"), dict) else {}
        return database_payload, schema_payload, team_result

    database_payload, schema_payload = _load_notion_collection_schema(
        target_id=settings["space_id"],
        settings=settings,
        notion_kwargs=notion_kwargs,
    )
    team_result = query_notion_collection(
        database_id=settings["space_id"],
        token=settings["token"],
        api_version=settings["api_version"],
        payload={"page_size": 100},
        **notion_kwargs,
    )
    if isinstance(notion_stub_cache, dict):
        notion_stub_cache[shared_key] = {
            "database_payload": database_payload,
            "schema_payload": schema_payload,
            "team_result": team_result,
        }
    return database_payload, schema_payload, team_result


def _cached_scoped_notion_items(
    *,
    settings: dict[str, str],
    schema: dict[str, Any],
    agent_row: sqlite3.Row,
    identity: dict[str, Any],
    notion_kwargs: dict[str, Any],
    notion_stub_cache: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    scoped_key = f"scoped-notion:{settings['space_id']}:{agent_row['agent_id']}"
    scoped_digest = notion_stub_cache.get(scoped_key) if isinstance(notion_stub_cache, dict) else None
    if isinstance(scoped_digest, dict):
        items = scoped_digest.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]

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
        for item in scoped_items
        if isinstance(item, dict) and _page_access_matches_identity(item, agent_row=agent_row, identity=identity)[0]
    ]
    if isinstance(notion_stub_cache, dict):
        notion_stub_cache[scoped_key] = {"items": user_items}
    return user_items


def _build_notion_stub(
    conn: sqlite3.Connection,
    *,
    agent_row: sqlite3.Row,
    identity: dict[str, Any] | None,
    notion_stub_cache: dict[str, Any] | None = None,
) -> str:
    try:
        settings = _require_shared_notion_settings()
    except PermissionError as exc:
        return f"Shared Notion digest:\n- Shared organizational Notion is not configured on this host yet ({exc})."
    verification_status = str((identity or {}).get("verification_status") or "").strip()
    verified_email = str((identity or {}).get("notion_user_email") or (identity or {}).get("claimed_notion_email") or "").strip()
    claimed_email = _normalize_email(str((identity or {}).get("claimed_notion_email") or ""))
    pending_lines = _agent_ssot_pending_stub_lines(
        conn,
        agent_id=str(agent_row["agent_id"] or ""),
    )
    if settings["space_kind"] != "database":
        lines = [
            "Shared Notion digest:",
            "- Current SSOT shape: page-scoped. ArcLink cannot build a structured database digest from this target yet.",
            "- Read routing: use knowledge.search-and-fetch or notion.search-and-fetch for indexed shared Notion/vault context; use notion.fetch when an exact page URL or id is known. ssot.read page reads require verified Notion ownership and a scoped target.",
            "- Write routing: use ssot.write for permitted brokered updates on in-scope user work.",
            "- Best fit for repeated brokered writes is still a database row whose people-typed column(s) name the verified caller (any column name - Owner, Assignee, DRI, Lead, Reviewer, ...). Plain child pages can be more fragile under strict scope checks.",
            "- If a brokered action is denied, explain it as a verification, scope, or allowed-operation limit; do not describe that as the skill being missing or the rail disappearing.",
        ]
        if verification_status != "verified":
            if claimed_email:
                lines.append(f"- Verification: pending for {claimed_email}. Brokered ssot.read page reads and shared writes remain gated until the claim is verified.")
            else:
                lines.append("- Verification: not started yet. Brokered ssot.read page reads and shared writes remain gated until the user verifies their Notion identity.")
        else:
            lines.append(f"- Verification: confirmed for {verified_email or 'your verified Notion identity'}. Shared brokered reads and writes are enabled within scoped rails; broad plate or knowledge questions should still start with notion.search-and-fetch / knowledge.search-and-fetch.")
            lines.append("- Plain shared pages stay writable when they are in your user's edit lane or when this same agent already established brokered write history there. If a page is still outside scope, move the work into an owned database item or ask for approval instead of asking the user to re-touch it.")
        lines.extend(pending_lines)
        return "\n".join(lines)
    notion_kwargs: dict[str, Any] = {}
    try:
        database_payload, schema_payload, team_result = _cached_shared_notion_digest(
            settings=settings,
            notion_kwargs=notion_kwargs,
            notion_stub_cache=notion_stub_cache,
        )
        schema = schema_payload or database_payload
    except Exception as exc:
        return f"Shared Notion digest:\n- Curator could not refresh the shared Notion snapshot just now ({exc})."
    entries = team_result.get("result") if isinstance(team_result, dict) else {}
    items_raw = entries.get("results") if isinstance(entries, dict) else []
    team_items = [item for item in items_raw if isinstance(item, dict)]
    lines = [
        "Shared Notion digest:",
        "- Current SSOT shape: database-backed shared workflow.",
        "- Current rail map: use ssot.read for live scoped reads and ssot.write for permitted brokered inserts, updates, or append-only page notes on in-scope records.",
        "- Native Notion edit history shows the ArcLink integration. When the database exposes a Changed By people property, ArcLink also stamps the verified human there on every brokered write.",
        "- If a brokered action is queued or denied, explain it as a verification, scope, or allowed-operation limit; do not describe that as the skill being missing or the rail disappearing.",
    ]
    if identity is None or verification_status != "verified":
        if claimed_email:
            lines.append(f"- Verification: pending for {claimed_email}. Brokered ssot.read and shared writes remain gated until the claim is verified.")
        else:
            lines.append("- Verification: not started yet. Brokered ssot.read and shared writes remain gated until the user verifies their Notion identity.")
        lines.extend(pending_lines)
        lines.extend(_notion_team_summary(team_items))
        return "\n".join(lines)
    try:
        user_items = _cached_scoped_notion_items(
            settings=settings,
            schema=schema,
            agent_row=agent_row,
            identity=identity,
            notion_kwargs=notion_kwargs,
            notion_stub_cache=notion_stub_cache,
        )
    except Exception as exc:
        lines.append(f"- Verification: confirmed, but Curator could not refresh your scoped Notion digest right now ({exc}).")
        lines.extend(_notion_team_summary(team_items))
        return "\n".join(lines)
    due_soon = sum(1 for item in user_items if _notion_due_within_days(_notion_date_property(item), 7))
    recent_updates = sum(1 for item in user_items if _notion_recently_updated(item, days=7))
    lines.append(
        f"- Verification: confirmed for {verified_email}."
    )
    lines.extend(pending_lines)
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


def _today_plate_item_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or "").strip()


def _today_plate_work_line(item: dict[str, Any], *, is_new: bool = False) -> str:
    title = _notion_title_from_page(item) or str(item.get("id") or "untitled")
    status = _notion_named_property_text(item, ("Status", "State", "Stage"))
    priority = _notion_named_property_text(item, ("Priority", "Urgency", "Importance"))
    due_rank, due_label = _notion_due_bucket(_notion_date_property(item))
    parts = [title]
    roles = item.get("__arclink_user_roles__")
    if isinstance(roles, list):
        cleaned = [str(role).strip() for role in roles if str(role or "").strip()]
        if cleaned:
            parts.append(f"as {', '.join(cleaned)}")
    if status:
        parts.append(f"status {status}")
    if priority:
        parts.append(f"priority {priority}")
    if due_label:
        parts.append(due_label)
    if due_rank >= 4 and _notion_recently_updated(item, days=7):
        parts.append("updated recently")
    if is_new:
        parts.append("NEW since last plate")
    return " - ".join(parts)


def _today_plate_sort_key(item: dict[str, Any]) -> tuple[int, int, str, str]:
    due_rank, due_label = _notion_due_bucket(_notion_date_property(item))
    recently_updated_rank = 0 if _notion_recently_updated(item, days=7) else 1
    title = _notion_title_from_page(item).lower()
    return (due_rank, recently_updated_rank, due_label, title)


def _discover_child_task_databases(
    *,
    settings: dict[str, str],
    root_page_id: str,
    notion_kwargs: dict[str, Any],
    notion_stub_cache: dict[str, Any] | None = None,
    max_databases: int = 8,
    max_depth: int = 2,
) -> list[dict[str, Any]]:
    """Walk the SSOT root page tree and return child databases that expose
    at least one people-typed property - any label the workspace uses
    (Owner, Assignee, Reviewer, DRI, Lead, ...) qualifies as an ownership
    channel. Cached in ``notion_stub_cache`` so repeated calls within a
    single plugin-context build don't re-issue the same Notion API requests.
    """
    normalized_root = extract_notion_space_id(str(root_page_id or ""))
    if not normalized_root:
        return []
    cache_key = f"task-databases:{normalized_root}"
    if isinstance(notion_stub_cache, dict) and cache_key in notion_stub_cache:
        return list(notion_stub_cache[cache_key])
    discovered: list[dict[str, Any]] = []
    visited_pages: set[str] = set()
    visited_databases: set[str] = set()

    def _walk(block_id: str, depth: int) -> None:
        if len(discovered) >= max_databases or depth > max_depth:
            return
        normalized_block = extract_notion_space_id(block_id)
        if not normalized_block or normalized_block in visited_pages:
            return
        visited_pages.add(normalized_block)
        try:
            children = list_notion_block_children_all(
                block_id=normalized_block,
                token=settings["token"],
                api_version=settings["api_version"],
                **notion_kwargs,
            )
        except Exception:
            return
        for child in children:
            if not isinstance(child, dict):
                continue
            child_type = str(child.get("type") or "").strip()
            child_id = extract_notion_space_id(str(child.get("id") or "").strip())
            if not child_id:
                continue
            if child_type == "child_database":
                if child_id in visited_databases or len(discovered) >= max_databases:
                    continue
                visited_databases.add(child_id)
                try:
                    db_payload, ds_payload = _load_notion_collection_schema(
                        target_id=child_id,
                        settings=settings,
                        notion_kwargs=notion_kwargs,
                    )
                except Exception:
                    continue
                if bool(db_payload.get("in_trash")) or bool(db_payload.get("archived")):
                    continue
                schema = ds_payload or db_payload
                if not _configured_people_properties(schema):
                    continue
                title = _notion_database_title(db_payload) or "Unnamed database"
                url = normalize_notion_space_url(str(db_payload.get("url") or "").strip())
                discovered.append(
                    {
                        "id": child_id,
                        "title": title,
                        "url": url,
                        "schema": schema,
                        "people_properties": _configured_people_properties(schema),
                    }
                )
            elif child_type == "child_page" and depth < max_depth:
                _walk(child_id, depth + 1)

    _walk(normalized_root, 0)
    if isinstance(notion_stub_cache, dict):
        notion_stub_cache[cache_key] = list(discovered)
    return discovered


def _query_owner_items_in_database(
    *,
    settings: dict[str, str],
    database_id: str,
    schema_payload: dict[str, Any],
    notion_user_id: str,
    notion_kwargs: dict[str, Any],
    page_size: int = 50,
) -> list[dict[str, Any]]:
    """Return rows in ``database_id`` where any people-typed property on
    the row contains ``notion_user_id``. Property names are treated as
    opaque ownership channels - Owner, Assignee, Reviewer, DRI, Lead, or
    any other label the workspace uses. Empty list when the user is not
    verified or the database has no people-typed properties.
    """
    if not notion_user_id:
        return []
    people_props = _configured_people_properties(schema_payload)
    if not people_props:
        return []
    filter_clauses = [
        {"property": prop_name, "people": {"contains": notion_user_id}}
        for prop_name in people_props
    ]
    notion_filter: dict[str, Any] = (
        filter_clauses[0] if len(filter_clauses) == 1 else {"or": filter_clauses}
    )
    try:
        result = query_notion_collection_all(
            database_id=database_id,
            token=settings["token"],
            api_version=settings["api_version"],
            payload={"filter": notion_filter, "page_size": page_size},
            **notion_kwargs,
        )
    except Exception:
        return []
    rows = ((result or {}).get("result") or {}).get("results") or []
    return [row for row in rows if isinstance(row, dict)]


def _build_today_plate(
    conn: sqlite3.Connection,
    *,
    agent_row: sqlite3.Row,
    identity: dict[str, Any] | None,
    notion_stub_cache: dict[str, Any] | None = None,
    previous_item_ids: object = None,
) -> str:
    agent_id = str(agent_row["agent_id"] or "").strip()
    lines = [
        "Today plate:",
        "- Purpose: compact working-context snapshot for the current user; use live MCP reads before acting on stale or high-impact state.",
    ]
    pending_count = count_ssot_pending_writes(conn, status="pending", agent_id=agent_id) if agent_id else 0
    pending_lines = _agent_ssot_pending_stub_lines(conn, agent_id=agent_id, limit=2)

    try:
        settings = _require_shared_notion_settings()
    except PermissionError as exc:
        lines.append(f"- Shared Notion SSOT is not ready for a structured work plate yet ({exc}).")
        if pending_lines:
            lines.extend(pending_lines)
        lines.append("- Use qmd/vault retrieval for background and ask the user for the current priority if no SSOT lane is live.")
        return "\n".join(lines)

    if settings["space_kind"] != "database":
        verification_status = str((identity or {}).get("verification_status") or "").strip()
        verified_email = str((identity or {}).get("notion_user_email") or (identity or {}).get("claimed_notion_email") or "").strip()
        claimed_email = _normalize_email(str((identity or {}).get("claimed_notion_email") or ""))
        notion_user_id = str((identity or {}).get("notion_user_id") or "").strip()
        notion_kwargs: dict[str, Any] = {}
        try:
            task_dbs = _discover_child_task_databases(
                settings=settings,
                root_page_id=str(settings.get("space_id") or ""),
                notion_kwargs=notion_kwargs,
                notion_stub_cache=notion_stub_cache,
            )
        except Exception:
            task_dbs = []
        lines.append("- Real-time awareness path: Notion changes propagate via webhook -> ssot batcher (sub-second nudge + 1 min timer) -> qmd reindex; new pages, database rows, edits, and deletions under the SSOT root reach the qmd notion-shared index within seconds.")
        if not task_dbs:
            lines.append("- No structured ownership surfaces discovered: no child database under the SSOT root exposes a people-typed property the current user could appear in.")
            if pending_lines:
                lines.extend(pending_lines)
            lines.append("- When the user asks anything about their work, focus, recent activity, or what's on their plate: answer from this managed snapshot first. If it is thin, read the qmd notion-shared collection with one bounded knowledge.search-and-fetch or notion.search-and-fetch using the user's own framing - names, projects, intent - and reason from what comes back rather than matching specific keywords.")
            lines.append("- Live read routing: use notion.fetch for exact page URLs/ids and notion.query only for one exact live structured database target. Do not fan out notion.query across discovered databases during a generic plate check. Use ssot.read only after Notion verification and only for scoped brokered targets; unverified page reads are refused by design.")
            lines.append("- For brokered writes to the SSOT page or its descendants use ssot.write; use ssot.preflight first when scope is uncertain.")
            return "\n".join(lines)
        per_db_channels: list[str] = []
        for db in task_dbs[:6]:
            channels = ", ".join(db.get("people_properties") or []) or "-"
            per_db_channels.append(f"{db.get('title') or 'Unnamed'} ({channels})")
        lines.append(
            f"- Ownership surfaces discovered under the SSOT root ({len(task_dbs)} database(s)): "
            + "; ".join(per_db_channels[:6])
            + ("; ..." if len(task_dbs) > 6 else "")
            + ". Property names are treated as opaque ownership channels - any people-typed column qualifies."
        )
        if identity is None or verification_status != "verified" or not notion_user_id:
            if claimed_email:
                lines.append(f"- Verification: pending for {claimed_email}; per-user filtering across these databases needs Notion identity verification.")
            else:
                lines.append("- Verification: not started; per-user filtering across these databases needs Notion identity verification.")
            if pending_lines:
                lines.extend(pending_lines)
            lines.append("- Until verification completes, do not live-query these databases for per-user filtering; fall back to this snapshot and one bounded knowledge.search-and-fetch on the notion-shared collection for ambient context.")
            return "\n".join(lines)
        aggregated_items: list[dict[str, Any]] = []
        per_db_counts: list[tuple[str, str, int]] = []
        for db in task_dbs[:6]:
            db_title = str(db.get("title") or "").strip() or "Unnamed database"
            db_url = str(db.get("url") or "").strip()
            items = _query_owner_items_in_database(
                settings=settings,
                database_id=str(db.get("id") or ""),
                schema_payload=db.get("schema") or {},
                notion_user_id=notion_user_id,
                notion_kwargs=notion_kwargs,
            )
            for item in items:
                item.setdefault("__arclink_source_db_title__", db_title)
                item.setdefault(
                    "__arclink_user_roles__",
                    _notion_user_role_properties(item, notion_user_id),
                )
            aggregated_items.extend(items)
            per_db_counts.append((db_title, db_url, len(items)))
        current_item_ids = [_today_plate_item_id(item) for item in aggregated_items if _today_plate_item_id(item)]
        if isinstance(notion_stub_cache, dict):
            notion_stub_cache[f"today-plate-ids:{agent_id}"] = current_item_ids
        previous_ids: set[str] = set()
        has_previous_plate = previous_item_ids is not None
        if isinstance(previous_item_ids, (list, tuple, set)):
            previous_ids = {str(part or "").strip() for part in previous_item_ids if str(part or "").strip()}
        due_now = sum(1 for item in aggregated_items if _notion_due_bucket(_notion_date_property(item))[0] in {0, 1})
        due_soon = sum(1 for item in aggregated_items if _notion_due_bucket(_notion_date_property(item))[0] <= 2)
        recently_updated = sum(1 for item in aggregated_items if _notion_recently_updated(item, days=7))
        lines.append(f"- Verification: confirmed for {verified_email or 'the current user'}.")
        lines.append(
            f"- Scoped involvement across {len(per_db_counts)} surface(s): {len(aggregated_items)} record(s) where the user appears in any people-typed column. "
            f"Due today/overdue: {due_now}. Due within 7 days: {due_soon}. Updated in 7 days: {recently_updated}. "
            f"Pending write approvals: {pending_count}."
        )
        if pending_lines:
            lines.extend(pending_lines)
        non_empty = [(t, u, c) for (t, u, c) in per_db_counts if c > 0]
        if non_empty:
            lines.append("- Per-surface breakdown:")
            for title, _url, count in non_empty:
                lines.append(f"  - {title}: {count} record(s) involving the user")
        if aggregated_items:
            lines.append("- Top involvement candidates (sorted by due / recency, role tags show which ownership channel matched):")
            for item in sorted(aggregated_items, key=_today_plate_sort_key)[:5]:
                item_id = _today_plate_item_id(item)
                is_new = bool(has_previous_plate and item_id and item_id not in previous_ids)
                db_title = str(item.get("__arclink_source_db_title__") or "").strip()
                prefix = f"[{db_title}] " if db_title else ""
                lines.append(f"  - {prefix}{_today_plate_work_line(item, is_new=is_new)}")
            lines.append("- Agent posture: when the user asks about their work, focus, recent activity, or what's on their plate, lead with this structured snapshot. For broader or unstructured questions, supplement with one bounded knowledge.search-and-fetch on the notion-shared collection using the user's own framing. Use notion.query / ssot.read only for a specific live target or before changing shared state.")
        else:
            lines.append("- No record currently lists the verified user in any people-typed column across the discovered surfaces.")
            lines.append("- Agent posture: ask the user what they want to focus on, or use knowledge.search-and-fetch on the notion-shared collection to find content that mentions or references them - the index reflects Notion within seconds.")
        return "\n".join(lines)

    verification_status = str((identity or {}).get("verification_status") or "").strip()
    verified_email = str((identity or {}).get("notion_user_email") or (identity or {}).get("claimed_notion_email") or "").strip()
    claimed_email = _normalize_email(str((identity or {}).get("claimed_notion_email") or ""))
    if identity is None or verification_status != "verified":
        if claimed_email:
            lines.append(f"- Verification: pending for {claimed_email}; per-user filtering on this database's people-typed columns cannot be trusted until verified.")
        else:
            lines.append("- Verification: not started; per-user filtering on this database's people-typed columns is unavailable until the user verifies their Notion identity.")
        if pending_lines:
            lines.extend(pending_lines)
        lines.append("- Next action: help the user verify Notion or ask what they want to focus on, then reach for knowledge.search-and-fetch on the notion-shared collection if they need ambient context in the meantime.")
        return "\n".join(lines)

    notion_kwargs: dict[str, Any] = {}
    try:
        database_payload, schema_payload, _team_result = _cached_shared_notion_digest(
            settings=settings,
            notion_kwargs=notion_kwargs,
            notion_stub_cache=notion_stub_cache,
        )
        schema = schema_payload or database_payload
        user_items = _cached_scoped_notion_items(
            settings=settings,
            schema=schema,
            agent_row=agent_row,
            identity=identity or {},
            notion_kwargs=notion_kwargs,
            notion_stub_cache=notion_stub_cache,
        )
    except Exception as exc:
        lines.append(f"- Verification: confirmed for {verified_email or 'the current user'}, but Curator could not refresh scoped work right now ({exc}).")
        if pending_lines:
            lines.extend(pending_lines)
        lines.append("- Next action: use one targeted notion.query/ssot.read for a live check only if the user needs this now.")
        return "\n".join(lines)

    current_item_ids = [_today_plate_item_id(item) for item in user_items if _today_plate_item_id(item)]
    if isinstance(notion_stub_cache, dict):
        notion_stub_cache[f"today-plate-ids:{agent_id}"] = current_item_ids
    previous_ids: set[str] = set()
    has_previous_plate = previous_item_ids is not None
    if isinstance(previous_item_ids, (list, tuple, set)):
        previous_ids = {str(item or "").strip() for item in previous_item_ids if str(item or "").strip()}

    due_now = sum(1 for item in user_items if _notion_due_bucket(_notion_date_property(item))[0] in {0, 1})
    due_soon = sum(1 for item in user_items if _notion_due_bucket(_notion_date_property(item))[0] <= 2)
    recently_updated = sum(1 for item in user_items if _notion_recently_updated(item, days=7))
    lines.append(f"- Verification: confirmed for {verified_email or 'the current user'}.")
    lines.append(
        f"- Scoped involvement: {len(user_items)} record(s) where the user appears in any people-typed column. Due today/overdue: {due_now}. Due within 7 days: {due_soon}. Updated in 7 days: {recently_updated}. Pending write approvals: {pending_count}."
    )
    if pending_lines:
        lines.extend(pending_lines)
    if user_items:
        lines.append("- Work candidates:")
        for item in sorted(user_items, key=_today_plate_sort_key)[:5]:
            item_id = _today_plate_item_id(item)
            is_new = bool(has_previous_plate and item_id and item_id not in previous_ids)
            lines.append(f"  - {_today_plate_work_line(item, is_new=is_new)}")
        lines.append("- Agent posture: orient from this plate. Use notion.query/ssot.read only for a specific live target or before changing shared state.")
    else:
        lines.append("- Work candidates: none scoped to this user in the last Curator snapshot.")
        lines.append("- Agent posture: ask what the user wants to prioritize, or use notion.query if they expect newer Notion assignments.")
    return "\n".join(lines)


def notion_search(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    agent_id: str,
    query_text: str,
    limit: int = 5,
    rerank: bool = False,
    requested_by_actor: str,
) -> dict[str, Any]:
    agent_row = _active_user_agent_row(conn, agent_id)
    settings = _require_shared_notion_settings()
    roots = _resolve_notion_index_roots(settings=settings)
    compact_query = str(query_text or "").strip()
    if not compact_query:
        raise ValueError("notion.search requires a non-empty query")
    normalized_limit = max(1, min(int(limit or 5), 10))
    collection_name = _notion_index_collection_name()
    index_doc_count = int(
        conn.execute("SELECT COUNT(*) AS c FROM notion_index_documents WHERE state = 'active'").fetchone()["c"]
    )
    structured = mcp_call(
        cfg.qmd_url,
        "query",
        {
            "searches": [
                {"type": "lex", "query": compact_query},
                {"type": "vec", "query": compact_query},
            ],
            "collections": [collection_name],
            "intent": f"Search shared Notion knowledge for {compact_query}",
            "rerank": bool(rerank),
            "limit": normalized_limit,
        },
    )
    raw_results = structured.get("results") if isinstance(structured, dict) else []
    hits: list[dict[str, Any]] = []
    for raw in raw_results if isinstance(raw_results, list) else []:
        if not isinstance(raw, dict):
            continue
        file_key = _index_document_lookup_key(cfg, str(raw.get("file") or raw.get("path") or ""))
        row = (
            conn.execute(
                """
                SELECT root_id, source_page_id, source_page_url, file_path, page_title,
                       section_heading, breadcrumb_json, owners_json, last_edited_time
                FROM notion_index_documents
                WHERE file_path = ?
                """,
                (file_key,),
            ).fetchone()
            if file_key
            else None
        )
        snippet = ""
        for field in ("snippet", "text", "excerpt", "preview", "content"):
            value = str(raw.get(field) or "").strip()
            if value:
                snippet = value
                break
        breadcrumb = json_loads(str(row["breadcrumb_json"] or "[]"), []) if row is not None else []
        owners = json_loads(str(row["owners_json"] or "[]"), []) if row is not None else []
        if not isinstance(breadcrumb, list):
            breadcrumb = []
        if not isinstance(owners, list):
            owners = []
        hits.append(
            {
                "source": "index",
                "root_id": str(row["root_id"] or "") if row is not None else "",
                "page_id": str(row["source_page_id"] or "") if row is not None else "",
                "page_url": str(row["source_page_url"] or "") if row is not None else "",
                "page_title": str(row["page_title"] or "") if row is not None else "",
                "section_heading": str(row["section_heading"] or "") if row is not None else "",
                "breadcrumb": [str(part) for part in breadcrumb if str(part or "").strip()],
                "owners": [str(owner) for owner in owners if str(owner or "").strip()],
                "last_edited_time": str(row["last_edited_time"] or "") if row is not None else "",
                "file": file_key,
                "score": raw.get("score"),
                "snippet": snippet,
                "raw_result": raw,
            }
        )
    _log_notion_retrieval_audit(
        conn,
        agent_id=str(agent_row["agent_id"]),
        unix_user=str(agent_row["unix_user"]),
        operation="search",
        decision="allow",
        query_text=compact_query,
        result_count=len(hits),
        note=f"collection={collection_name} docs={index_doc_count} rerank={str(bool(rerank)).lower()}",
    )
    return {
        "ok": True,
        "query": compact_query,
        "collection": collection_name,
        "index_ready": bool(roots),
        "index_doc_count": index_doc_count,
        "roots": roots,
        "results": hits,
    }


def notion_fetch(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    agent_id: str,
    target_id: str,
    requested_by_actor: str,
    urlopen_fn=None,
) -> dict[str, Any]:
    agent_row = _active_user_agent_row(conn, agent_id)
    settings = _require_shared_notion_settings()
    notion_kwargs: dict[str, Any] = {}
    if urlopen_fn is not None:
        notion_kwargs["urlopen_fn"] = urlopen_fn
    normalized_target = str(target_id or "").strip()
    if not normalized_target:
        raise ValueError("notion.fetch requires a page or database id/url")
    target_meta = resolve_notion_target(
        target_id=normalized_target,
        token=settings["token"],
        api_version=settings["api_version"],
        **notion_kwargs,
    )
    target_uuid = str(target_meta.get("id") or "").strip()
    if str(target_meta.get("kind") or "") == "data_source":
        data_source = retrieve_notion_data_source(
            data_source_id=target_uuid,
            token=settings["token"],
            api_version=settings["api_version"],
            **notion_kwargs,
        )
        parent = data_source.get("parent") if isinstance(data_source, dict) else {}
        database_id = str(parent.get("database_id") or "").strip() if isinstance(parent, dict) else ""
        database = (
            retrieve_notion_database(
                database_id=database_id,
                token=settings["token"],
                api_version=settings["api_version"],
                **notion_kwargs,
            )
            if database_id
            else {}
        )
        _log_notion_retrieval_audit(
            conn,
            agent_id=str(agent_row["agent_id"]),
            unix_user=str(agent_row["unix_user"]),
            operation="fetch",
            decision="allow",
            target_id=target_uuid,
            root_id=database_id,
            result_count=1,
            note="live data source fetch",
        )
        return {
            "ok": True,
            "target_id": target_uuid,
            "target_kind": "data_source",
            "data_source_id": target_uuid,
            "data_source": data_source,
            "database_id": database_id,
            "database": database,
            "indexed": bool(database_id),
        }
    if str(target_meta.get("kind") or "") == "database":
        database = retrieve_notion_database(
            database_id=target_uuid,
            token=settings["token"],
            api_version=settings["api_version"],
            **notion_kwargs,
        )
        data_source_id = notion_database_data_source_id(database)
        data_source = {}
        if data_source_id:
            data_source = retrieve_notion_data_source(
                data_source_id=data_source_id,
                token=settings["token"],
                api_version=settings["api_version"],
                **notion_kwargs,
            )
        _log_notion_retrieval_audit(
            conn,
            agent_id=str(agent_row["agent_id"]),
            unix_user=str(agent_row["unix_user"]),
            operation="fetch",
            decision="allow",
            target_id=target_uuid,
            result_count=1,
            note="live database fetch",
        )
        return {
            "ok": True,
            "target_id": target_uuid,
            "target_kind": "database",
            "database": database,
            "data_source_id": data_source_id,
            "data_source": data_source,
            "indexed": False,
        }
    page = retrieve_notion_page(
        page_id=target_uuid,
        token=settings["token"],
        api_version=settings["api_version"],
        **notion_kwargs,
    )
    markdown_payload = retrieve_notion_page_markdown(
        page_id=target_uuid,
        token=settings["token"],
        api_version=settings["api_version"],
        **notion_kwargs,
    )
    rows = conn.execute(
        """
        SELECT DISTINCT root_id, source_page_url, page_title, breadcrumb_json, owners_json, last_edited_time
        FROM notion_index_documents
        WHERE source_page_id = ?
        ORDER BY root_id
        """,
        (target_uuid,),
    ).fetchall()
    indexed_roots = [str(row["root_id"] or "") for row in rows]
    attachments = _notion_page_attachment_refs(
        page_id=target_uuid,
        page_payload=page,
        notion_kwargs=notion_kwargs,
    )
    _log_notion_retrieval_audit(
        conn,
        agent_id=str(agent_row["agent_id"]),
        unix_user=str(agent_row["unix_user"]),
        operation="fetch",
        decision="allow",
        target_id=target_uuid,
        root_id=indexed_roots[0] if indexed_roots else "",
        result_count=1,
        note="live page fetch",
    )
    return {
        "ok": True,
        "target_id": target_uuid,
        "target_kind": "page",
        "page": page,
        "markdown": _notion_markdown_text(markdown_payload),
        "attachments": attachments,
        "indexed": bool(rows),
        "indexed_roots": indexed_roots,
    }


def notion_query(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    agent_id: str,
    target_id: str,
    query: dict[str, Any] | None,
    limit: int,
    requested_by_actor: str,
    urlopen_fn=None,
) -> dict[str, Any]:
    agent_row = _active_user_agent_row(conn, agent_id)
    settings = _require_shared_notion_settings()
    notion_kwargs: dict[str, Any] = {}
    if urlopen_fn is not None:
        notion_kwargs["urlopen_fn"] = urlopen_fn
    roots = _resolve_notion_index_roots(settings=settings, urlopen_fn=urlopen_fn)
    default_database_root = next((root for root in roots if root["root_kind"] == "database"), None)
    notion_target = str(target_id or "").strip() or (
        default_database_root["root_id"]
        if default_database_root is not None
        else (settings["space_id"] if settings["space_kind"] == "database" else "")
    )
    if not notion_target:
        raise ValueError("notion.query requires a database id/url when no default shared database is configured")
    target_meta = resolve_notion_target(
        target_id=notion_target,
        token=settings["token"],
        api_version=settings["api_version"],
        **notion_kwargs,
    )
    target_kind = str(target_meta.get("kind") or "")
    if target_kind not in {"database", "data_source"}:
        raise ValueError("notion.query requires a database or data source target")
    normalized_limit = max(1, min(int(limit or 25), 100))
    requested_query = dict(query or {})
    if "page_size" not in requested_query:
        requested_query["page_size"] = normalized_limit
    if target_kind == "data_source":
        data_source_id = str(target_meta.get("id") or "")
        data_source = retrieve_notion_data_source(
            data_source_id=data_source_id,
            token=settings["token"],
            api_version=settings["api_version"],
            **notion_kwargs,
        )
        parent = data_source.get("parent") if isinstance(data_source, dict) else {}
        database_id = str(parent.get("database_id") or "").strip() if isinstance(parent, dict) else ""
        database = (
            retrieve_notion_database(
                database_id=database_id,
                token=settings["token"],
                api_version=settings["api_version"],
                **notion_kwargs,
            )
            if database_id
            else {}
        )
        entries = query_notion_data_source(
            data_source_id=data_source_id,
            token=settings["token"],
            api_version=settings["api_version"],
            payload=requested_query,
            **notion_kwargs,
        )
        result = {
            "query_kind": "data_source",
            "data_source_id": data_source_id,
            "data_source": data_source,
            "database": database,
            "result": entries,
        }
    else:
        result = query_notion_collection(
            database_id=str(target_meta.get("id") or ""),
            token=settings["token"],
            api_version=settings["api_version"],
            payload=requested_query,
            **notion_kwargs,
        )
        entries = result.get("result") if isinstance(result, dict) else {}
    items = entries.get("results") if isinstance(entries, dict) else []
    items = [item for item in items if isinstance(item, dict)][:normalized_limit]
    root_match = next((root for root in roots if root["root_id"] == str(target_meta.get("id") or "").strip()), None)
    _log_notion_retrieval_audit(
        conn,
        agent_id=str(agent_row["agent_id"]),
        unix_user=str(agent_row["unix_user"]),
        operation="query",
        decision="allow",
        query_text=json_dumps(requested_query),
        target_id=str(target_meta.get("id") or ""),
        root_id=str((root_match or {}).get("root_id") or ""),
        result_count=len(items),
        note="live collection query",
    )
    return {
        "ok": True,
        "target_id": str(target_meta.get("id") or ""),
        "target_kind": target_kind,
        "query_kind": result.get("query_kind") if isinstance(result, dict) else "",
        "data_source_id": result.get("data_source_id") if isinstance(result, dict) else "",
        "data_source": result.get("data_source") if isinstance(result, dict) else {},
        "database": result.get("database") if isinstance(result, dict) else {},
        "results": items,
        "has_more": bool(entries.get("has_more")) if isinstance(entries, dict) else False,
        "next_cursor": str(entries.get("next_cursor") or "") if isinstance(entries, dict) else "",
        "root": root_match or {},
    }


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
    allowed, source = _page_access_matches_identity(
        page,
        agent_row=agent_row,
        identity=identity,
        conn=conn,
        allow_prior_agent_touch=True,
    )
    if not allowed:
        reason = "page read is outside the caller's scoped Notion edit lane"
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


def _normalize_ssot_append_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("shared Notion append requires a payload object")
    if "after" in payload and str(payload.get("after") or "").strip():
        raise ValueError("shared Notion append only supports appending at the end; omit 'after'")
    children = payload.get("children")
    children = _validate_ssot_block_children(children, operation="append", required=True)
    if set(payload.keys()) - {"children"}:
        raise ValueError("shared Notion append only supports a top-level 'children' field")
    return {"children": children}


def _validate_ssot_block_children(
    value: Any,
    *,
    operation: str,
    required: bool,
    depth: int = 1,
    path: str = "children",
    allow_missing: bool = True,
) -> list[dict[str, Any]]:
    if value is None:
        if not required and allow_missing:
            return []
        raise ValueError(f"shared Notion {operation} requires '{path}' to be a list")
    if not isinstance(value, list):
        raise ValueError(f"shared Notion {operation} requires '{path}' to be a list")
    if required and not value:
        raise ValueError(f"shared Notion {operation} requires a non-empty '{path}' list")
    if len(value) > SSOT_MAX_BLOCK_CHILDREN_PER_REQUEST:
        raise ValueError(
            f"shared Notion {operation} supports at most "
            f"{SSOT_MAX_BLOCK_CHILDREN_PER_REQUEST} child blocks per request"
        )
    normalized_children: list[dict[str, Any]] = []
    for index, child in enumerate(value, start=1):
        if not isinstance(child, dict):
            raise ValueError(f"shared Notion {operation} child block {index} must be an object")
        block_type = str(child.get("type") or "").strip()
        if not block_type:
            raise ValueError(f"shared Notion {operation} child block {index} is missing type")
        if block_type not in child:
            raise ValueError(f"shared Notion {operation} child block {index} is missing its '{block_type}' body")
        block_body = child.get(block_type)
        if not isinstance(block_body, dict):
            raise ValueError(f"shared Notion {operation} child block {index} body '{block_type}' must be an object")
        normalized_child = dict(child)
        normalized_body = dict(block_body)
        if "children" in normalized_body:
            if depth >= SSOT_MAX_INLINE_BLOCK_DEPTH:
                raise ValueError(
                    f"shared Notion {operation} supports at most "
                    f"{SSOT_MAX_INLINE_BLOCK_DEPTH} inline child block levels per request; "
                    "append deeper content in a later call"
                )
            normalized_body["children"] = _validate_ssot_block_children(
                normalized_body.get("children"),
                operation=operation,
                required=False,
                depth=depth + 1,
                path=f"{path}[{index}].{block_type}.children",
                allow_missing=False,
            )
        normalized_child[block_type] = normalized_body
        normalized_children.append(normalized_child)
    return normalized_children


def _ssot_rich_text_request_plain(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("title", "rich_text"):
            nested = value.get(key)
            if nested is not None:
                return _ssot_rich_text_request_plain(nested)
        text = value.get("text")
        if isinstance(text, dict):
            return str(text.get("content") or "").strip()
        return str(value.get("plain_text") or "").strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            text = _ssot_rich_text_request_plain(item)
            if text:
                parts.append(text)
        return "".join(parts).strip()
    return ""


def _normalize_ssot_create_database_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("shared Notion create_database requires a payload object")
    if "parent" in payload:
        raise ValueError("shared Notion create_database parent is controlled by target_id; omit payload.parent")
    allowed_keys = {"title", "name", "description", "properties", "initial_data_source", "is_inline"}
    unknown_keys = set(payload) - allowed_keys
    if unknown_keys:
        unknown_label = ", ".join(sorted(str(key) for key in unknown_keys))
        raise ValueError(f"shared Notion create_database payload has unsupported field(s): {unknown_label}")
    data_source = payload.get("initial_data_source")
    data_source_properties = data_source.get("properties") if isinstance(data_source, dict) else None
    raw_properties = payload.get("properties")
    properties = raw_properties if isinstance(raw_properties, dict) else data_source_properties
    if not isinstance(properties, dict):
        raise ValueError("shared Notion create_database requires payload.properties or payload.initial_data_source.properties")
    normalized_properties: dict[str, Any] = {}
    for property_name, property_schema in properties.items():
        if not isinstance(property_schema, dict):
            normalized_properties[str(property_name)] = property_schema
            continue
        schema = dict(property_schema)
        property_type = str(schema.pop("type", "") or "").strip()
        if property_type and property_type in schema:
            normalized_properties[str(property_name)] = {property_type: schema[property_type]}
        elif property_type and not schema:
            normalized_properties[str(property_name)] = {property_type: {}}
        else:
            normalized_properties[str(property_name)] = property_schema
    has_title_property = any(
        isinstance(prop, dict) and _expected_notion_property_type(prop) == "title"
        for prop in normalized_properties.values()
    )
    if not has_title_property:
        normalized_properties = {"Name": {"title": {}}, **normalized_properties}
    title = (
        _ssot_rich_text_request_plain(payload.get("title"))
        or _ssot_rich_text_request_plain(payload.get("name"))
        or "Shared ArcLink Database"
    )
    description = _ssot_rich_text_request_plain(payload.get("description"))
    return {
        "title": title,
        "description": description,
        "properties": normalized_properties,
        "is_inline": bool(payload["is_inline"]) if "is_inline" in payload else None,
    }


def _ssot_title_rich_text_request(value: Any, *, fallback: str) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("title", "rich_text"):
            nested = value.get(key)
            if isinstance(nested, list):
                return nested
    title = _ssot_rich_text_request_plain(value) or fallback
    return [
        {
            "type": "text",
            "text": {
                "content": title,
            },
        }
    ]


def _normalize_ssot_create_page_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("shared Notion create_page requires a payload object")
    if "parent" in payload:
        raise ValueError("shared Notion create_page parent is controlled by target_id; omit payload.parent")
    allowed_keys = {"title", "name", "properties", "children", "icon", "cover"}
    unknown_keys = set(payload) - allowed_keys
    if unknown_keys:
        unknown_label = ", ".join(sorted(str(key) for key in unknown_keys))
        raise ValueError(f"shared Notion create_page payload has unsupported field(s): {unknown_label}")
    create_payload = {
        key: value
        for key, value in payload.items()
        if key not in {"title", "name"}
    }
    if "children" in create_payload:
        create_payload["children"] = _validate_ssot_block_children(
            create_payload.get("children"),
            operation="create_page",
            required=False,
            allow_missing=False,
        )

    properties = create_payload.get("properties")
    if "properties" in create_payload and not isinstance(properties, dict):
        raise ValueError("shared Notion create_page properties must be an object when provided")
    normalized_properties = dict(properties) if isinstance(properties, dict) else {}
    title_property = normalized_properties.get("title")
    if title_property is None and "Title" in normalized_properties:
        title_property = normalized_properties.pop("Title")
    if title_property is None and set(normalized_properties) == {"Name"}:
        title_property = normalized_properties.pop("Name")
    if normalized_properties and set(normalized_properties) != {"title"}:
        raise ValueError(
            "shared Notion create_page under a page parent only supports the page title property; "
            "use create_database or insert into a database for structured fields"
        )
    title_source = (
        title_property
        if title_property is not None
        else payload.get("title")
        if payload.get("title") is not None
        else payload.get("name")
    )
    normalized_properties["title"] = _ssot_title_rich_text_request(
        title_source,
        fallback="Shared ArcLink Page",
    )
    create_payload["properties"] = normalized_properties
    return create_payload


def _validate_ssot_write_payload_shape(operation: str, payload: dict[str, Any]) -> None:
    op = str(operation or "").strip().lower()
    if op == "append":
        _normalize_ssot_append_payload(payload)
    elif op == "create_page":
        _normalize_ssot_create_page_payload(payload)
    elif op == "create_database":
        _normalize_ssot_create_database_payload(payload)


def _default_ssot_shared_parent_page_id(settings: dict[str, str]) -> str:
    root_page_id = str(settings.get("root_page_id") or "").strip()
    if root_page_id:
        return root_page_id
    if str(settings.get("space_kind") or "").strip() == "page":
        return str(settings.get("space_id") or "").strip()
    return ""


def _ssot_target_id_for_operation(settings: dict[str, str], *, operation: str, target_id: str) -> str:
    op = str(operation or "").strip().lower()
    raw_target = str(target_id or "").strip()
    if op in {"create_page", "create_database"}:
        raw_target = raw_target or _default_ssot_shared_parent_page_id(settings)
        if not raw_target:
            raise ValueError(
                f"shared Notion {op} requires a target page id or ARCLINK_SSOT_NOTION_ROOT_PAGE_ID"
            )
        return extract_notion_space_id(raw_target)
    return extract_notion_space_id(raw_target or settings["space_id"])


def _ssot_write_gate_reason(identity: dict[str, Any]) -> str:
    verification_status = str(identity.get("verification_status") or "").strip()
    write_mode = str(identity.get("write_mode") or "").strip()
    if verification_status != "verified" or write_mode != "verified_limited":
        return "shared Notion writes require a verified Notion claim and verified_limited write mode"
    return ""


def _notify_ssot_pending_write_resolution(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    pending_row: dict[str, Any],
    message: str,
) -> None:
    agent_id = str(pending_row.get("agent_id") or "").strip()
    if not agent_id:
        return
    queue_notification(
        conn,
        target_kind="user-agent",
        target_id=agent_id,
        channel_kind="ssot-approval",
        message=message,
    )
    try:
        signal_agent_refresh_from_curator(
            conn,
            cfg,
            agent_id=agent_id,
            note=f"ssot pending write resolution: {pending_row.get('pending_id') or ''}",
        )
    except Exception:
        return


def _queue_ssot_write_for_approval(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    agent_row: sqlite3.Row,
    identity: dict[str, Any],
    operation: str,
    target_id: str,
    payload: dict[str, Any],
    requested_by_actor: str,
    request_reason: str,
    request_source: str,
    owner_identity: str,
    owner_source: str,
    audit_payload: dict[str, Any],
) -> dict[str, Any]:
    pending_row, created = request_ssot_pending_write(
        conn,
        agent_id=str(agent_row["agent_id"] or ""),
        unix_user=str(agent_row["unix_user"] or ""),
        notion_user_id=str(identity.get("notion_user_id") or ""),
        operation=operation,
        target_id=target_id,
        payload=payload,
        requested_by_actor=requested_by_actor,
        request_source=request_source,
        request_reason=request_reason,
        owner_identity=owner_identity,
        owner_source=owner_source,
        ttl_seconds=cfg.ssot_pending_write_ttl_seconds,
    )
    pending_id = str(pending_row.get("pending_id") or "").strip()
    expires_label = format_utc_iso_brief(str(pending_row.get("expires_at") or ""))
    if created:
        owner_label = owner_identity or "unknown"
        queue_notification(
            conn,
            target_kind="user-agent",
            target_id=str(agent_row["agent_id"] or ""),
            channel_kind="ssot-approval",
            message=(
                "Notion write approval requested.\n"
                f"Pending: {pending_id}\n"
                f"Operation: {operation}\n"
                f"Target: {target_id}\n"
                f"Target owner/scope: {owner_label}\n"
                f"Expires: {expires_label}\n"
                f"Reason: {request_reason}\n"
                f"If the user approves in this chat, call ssot.approve with pending_id={pending_id}. "
                f"If they decline, call ssot.deny."
            ),
            extra={
                "pending_id": pending_id,
                "operation": operation,
                "target_id": target_id,
                "approval_owner": "user",
            },
        )
    note_refresh_job(
        conn,
        job_name=f"ssot-{operation}-{pending_id or secrets.token_hex(4)}",
        job_kind="ssot-write",
        target_id=target_id or str(agent_row["agent_id"]),
        schedule="manual",
        status="queued",
        note=json_dumps(
            {
                "pending_id": pending_id,
                "agent_id": str(agent_row["agent_id"] or ""),
                "operation": operation,
                "target_id": target_id,
                "expires_at": str(pending_row.get("expires_at") or ""),
                "owner_identity": owner_identity,
                "owner_source": owner_source,
                "requested_by_actor": requested_by_actor,
                "created": created,
            }
        ),
    )
    log_ssot_access_audit(
        conn,
        agent_id=str(agent_row["agent_id"]),
        unix_user=str(agent_row["unix_user"]),
        notion_user_id=str(identity.get("notion_user_id") or ""),
        operation=operation,
        target_id=target_id,
        decision="queue",
        reason=f"{request_reason}; user approval required",
        actor=requested_by_actor,
        request_payload={**audit_payload, "pending_id": pending_id, "created": created},
    )
    return {
        "applied": False,
        "queued": True,
        "agent_id": str(agent_row["agent_id"] or ""),
        "operation": operation,
        "target_id": target_id,
        "owner_identity": owner_identity,
        "owner_source": owner_source,
        "approval_required": True,
        "approval_owner": "user",
        "pending_id": pending_id,
        "pending_write": pending_row,
    }


def _apply_ssot_write(
    conn: sqlite3.Connection,
    *,
    settings: dict[str, str],
    agent_row: sqlite3.Row,
    identity: dict[str, Any],
    agent_id: str,
    operation: str,
    target_id: str,
    payload: dict[str, Any],
    requested_by_actor: str,
    audit_payload: dict[str, Any],
    bypass_scope: bool = False,
    pending_id: str = "",
    approval_actor: str = "",
    approval_surface: str = "",
) -> dict[str, Any]:
    notion_kwargs: dict[str, Any] = {}
    owner_identity, owner_source = ("", "insert")
    op = str(operation or "").strip().lower()
    normalized_target_id = str(target_id or "").strip()
    if op in {"create_page", "create_database"}:
        parent_meta = resolve_notion_target(
            target_id=normalized_target_id,
            token=settings["token"],
            api_version=settings["api_version"],
            **notion_kwargs,
        )
        parent_kind = str(parent_meta.get("kind") or "").strip()
        if parent_kind != "page":
            raise ValueError(f"shared Notion {op} requires a target page parent")
        parent_page = retrieve_notion_page(
            page_id=normalized_target_id,
            token=settings["token"],
            api_version=settings["api_version"],
            **notion_kwargs,
        )
        parent_approved, parent_access_source = _page_access_matches_identity(
            parent_page,
            agent_row=agent_row,
            identity=identity,
            conn=conn,
            allow_prior_agent_touch=True,
        )
        parent_owner_identity, _ = _notion_owner_identity(parent_page)
        owner_identity = parent_owner_identity or str(identity.get("notion_user_id") or identity.get("notion_user_email") or "")
        if not parent_approved and not bypass_scope:
            raise SSOTApprovalRequired(
                f"{op} target parent page is outside the verified caller's scoped Notion edit lane",
                owner_identity=owner_identity,
                owner_source=f"{op}-parent-ownership-mismatch",
            )
        owner_source = (
            f"page-parent-{parent_access_source or 'verified'}"
            if parent_approved
            else approval_surface or "approved-user-scope"
        )
        if op == "create_page":
            page_request = _normalize_ssot_create_page_payload(payload)
            applied_payload = create_notion_page(
                parent_id=normalized_target_id,
                parent_kind=parent_kind,
                token=settings["token"],
                api_version=settings["api_version"],
                payload=page_request,
                **notion_kwargs,
            )
            result_target_id = str(applied_payload.get("id") or "").strip() or normalized_target_id
            result_reason = f"brokered page creation applied under shared parent page {normalized_target_id}"
            result_note = {
                "agent_id": agent_id,
                "operation": op,
                "target_id": result_target_id,
                "target_kind": "page",
                "parent_id": normalized_target_id,
                "parent_kind": parent_kind,
                "owner_identity": owner_identity,
                "owner_source": owner_source,
                "parent_access_source": parent_access_source,
                "access_model": "inherits-parent-page-permissions",
                "actor": requested_by_actor,
            }
        else:
            database_request = _normalize_ssot_create_database_payload(payload)
            applied_payload = create_notion_database(
                parent_page_id=normalized_target_id,
                title=str(database_request["title"]),
                description=str(database_request["description"]),
                properties=database_request["properties"] if isinstance(database_request["properties"], dict) else {},
                is_inline=database_request["is_inline"] if isinstance(database_request.get("is_inline"), bool) else None,
                token=settings["token"],
                api_version=settings["api_version"],
                **notion_kwargs,
            )
            result_target_id = str(applied_payload.get("id") or "").strip() or normalized_target_id
            result_reason = f"brokered database creation applied under shared parent page {normalized_target_id}"
            result_note = {
                "agent_id": agent_id,
                "operation": op,
                "target_id": result_target_id,
                "target_kind": "database",
                "parent_id": normalized_target_id,
                "parent_kind": parent_kind,
                "owner_identity": owner_identity,
                "owner_source": owner_source,
                "parent_access_source": parent_access_source,
                "access_model": "inherits-parent-page-permissions",
                "actor": requested_by_actor,
            }
    elif op == "insert":
        owner_identity = str(identity.get("notion_user_id") or identity.get("notion_user_email") or "")
        parent_meta = resolve_notion_target(
            target_id=normalized_target_id,
            token=settings["token"],
            api_version=settings["api_version"],
            **notion_kwargs,
        )
        parent_kind = str(parent_meta.get("kind") or "").strip()
        parent_access_source = ""
        changed_by_property = ""
        applied_request_payload = _strip_attribution_properties(payload)
        if parent_kind == "database":
            approved, owner_source = _insert_payload_targets_verified_identity(payload, identity)
            if not approved and not bypass_scope:
                payload_owner_identity, payload_owner_source = _notion_owner_identity(payload)
                reason = (
                    "database insert is outside the verified caller's immediate Notion write lane; "
                    "user approval is required"
                )
                raise SSOTApprovalRequired(
                    reason,
                    owner_identity=payload_owner_identity or owner_identity,
                    owner_source=payload_owner_source or owner_source or "database-insert-scope",
                )
            if not approved:
                owner_source = approval_surface or "approved-user-scope"
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
        elif parent_kind == "page":
            parent_page = retrieve_notion_page(
                page_id=normalized_target_id,
                token=settings["token"],
                api_version=settings["api_version"],
                **notion_kwargs,
            )
            parent_approved, parent_access_source = _page_access_matches_identity(
                parent_page,
                agent_row=agent_row,
                identity=identity,
                conn=conn,
                allow_prior_agent_touch=True,
            )
            if not parent_approved and not bypass_scope:
                parent_owner_identity, _ = _notion_owner_identity(parent_page)
                raise SSOTApprovalRequired(
                    "target parent page is outside the verified caller's scoped Notion edit lane",
                    owner_identity=parent_owner_identity,
                    owner_source="page-parent-ownership-mismatch",
                )
            explicit_owner_channels = _notion_payload_people_property_names(payload)
            if explicit_owner_channels:
                approved, owner_source = _insert_payload_targets_verified_identity(payload, identity)
                if not approved and not bypass_scope:
                    payload_owner_identity, payload_owner_source = _notion_owner_identity(payload)
                    channels = ", ".join(explicit_owner_channels) or "people-typed columns"
                    reason = (
                        f"page child insert assigns {channels} outside the verified caller; "
                        "user approval is required"
                    )
                    raise SSOTApprovalRequired(
                        reason,
                        owner_identity=payload_owner_identity or owner_identity,
                        owner_source=payload_owner_source or owner_source or "page-child-owner-scope",
                    )
                if not approved:
                    owner_source = approval_surface or "approved-user-scope"
            else:
                owner_source = f"page-parent-{parent_access_source or 'verified'}"
        applied_payload = create_notion_page(
            parent_id=normalized_target_id,
            parent_kind=parent_kind,
            token=settings["token"],
            api_version=settings["api_version"],
            payload=applied_request_payload,
            **notion_kwargs,
        )
        result_target_id = str(applied_payload.get("id") or "").strip() or normalized_target_id
        result_reason = f"verified caller insert applied under {parent_kind} {normalized_target_id}"
        result_note = {
            "agent_id": agent_id,
            "operation": op,
            "target_id": result_target_id,
            "parent_id": normalized_target_id,
            "parent_kind": parent_kind,
            "owner_identity": owner_identity,
            "owner_source": owner_source,
            "parent_access_source": parent_access_source,
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
        approved, owner_source = _page_access_matches_identity(
            page,
            agent_row=agent_row,
            identity=identity,
            conn=conn,
            allow_prior_agent_touch=True,
        )
        owner_identity, _ = _notion_owner_identity(page)
        if not approved and not bypass_scope:
            raise SSOTApprovalRequired(
                "target page is outside the verified caller's scoped Notion edit lane",
                owner_identity=owner_identity,
                owner_source=owner_source,
            )
        if op == "append":
            applied_request_payload = _normalize_ssot_append_payload(payload)
            applied_payload = append_notion_block_children(
                block_id=normalized_target_id,
                token=settings["token"],
                api_version=settings["api_version"],
                payload=applied_request_payload,
                **notion_kwargs,
            )
            result_target_id = normalized_target_id
            result_reason = f"verified caller append applied to page {normalized_target_id}"
            result_note = {
                "agent_id": agent_id,
                "operation": op,
                "target_id": result_target_id,
                "owner_identity": owner_identity,
                "owner_source": owner_source,
                "appended_children": len(applied_request_payload["children"]),
                "actor": requested_by_actor,
            }
        else:
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

    if pending_id:
        result_note["pending_id"] = pending_id
    if approval_actor:
        result_note["approval_actor"] = approval_actor
        result_note["approval_surface"] = approval_surface
    note_refresh_job(
        conn,
        job_name=f"ssot-{op}-{result_target_id or secrets.token_hex(4)}",
        job_kind="ssot-write",
        target_id=result_target_id or agent_id,
        schedule="manual",
        status="applied",
        note=json_dumps(result_note),
    )
    allow_payload = dict(audit_payload)
    if pending_id:
        allow_payload["pending_id"] = pending_id
    if approval_actor:
        allow_payload["approved_by_actor"] = approval_actor
        allow_payload["approval_surface"] = approval_surface
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
        request_payload=allow_payload,
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
        "pending_id": pending_id,
        "notion_result": applied_payload,
    }


def preflight_ssot_write(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    agent_id: str,
    operation: str,
    target_id: str,
    payload: dict[str, Any],
    requested_by_actor: str,
) -> dict[str, Any]:
    """Check whether a shared Notion write would apply immediately or need
    explicit user approval. This intentionally performs no writes."""
    _ = cfg
    op = (operation or "").strip().lower()
    if op in SSOT_FORBIDDEN_OPERATIONS:
        return {
            "agent_id": agent_id,
            "operation": op,
            "target_id": str(target_id or "").strip(),
            "allowed": False,
            "would_queue": False,
            "approval_required": False,
            "recommended_action": "unsupported",
            "reason": f"operation '{op}' is not permitted; archive/delete are unsupported",
        }
    if op not in SSOT_WRITE_OPERATIONS:
        raise ValueError(f"unsupported SSOT operation '{op}'; allowed: {', '.join(SSOT_WRITE_OPERATIONS)}")

    settings = _require_shared_notion_settings()
    normalized_target_id = _ssot_target_id_for_operation(settings, operation=op, target_id=target_id)
    base = {
        "agent_id": agent_id,
        "operation": op,
        "target_id": normalized_target_id,
        "allowed": False,
        "would_queue": False,
        "approval_required": False,
        "approval_owner": "",
        "target_kind": "",
        "owner_source": "",
        "parent_access_source": "",
        "recommended_action": "do-not-write",
        "reason": "",
    }
    try:
        agent_row, identity = _ssot_principal(conn, agent_id)
    except PermissionError as exc:
        return {**base, "reason": str(exc), "recommended_action": "verify-notion"}
    gate_reason = _ssot_write_gate_reason(identity)
    if gate_reason:
        return {**base, "reason": gate_reason, "recommended_action": "verify-notion"}
    try:
        _validate_ssot_write_payload_shape(op, payload)
    except Exception as exc:  # noqa: BLE001
        return {**base, "reason": str(exc), "recommended_action": "fix-payload"}
    try:
        if op == "insert":
            parent_meta = resolve_notion_target(
                target_id=normalized_target_id,
                token=settings["token"],
                api_version=settings["api_version"],
            )
            parent_kind = str(parent_meta.get("kind") or "").strip()
            base["target_kind"] = parent_kind
            if parent_kind == "database":
                approved, owner_source = _insert_payload_targets_verified_identity(payload, identity)
                if approved:
                    return {
                        **base,
                        "allowed": True,
                        "owner_source": owner_source,
                        "recommended_action": "write",
                        "reason": "database insert is in the verified caller's lane",
                    }
                return {
                    **base,
                    "would_queue": True,
                    "approval_required": True,
                    "approval_owner": "user",
                    "owner_source": "database-insert-scope",
                    "recommended_action": "ask-user-approval",
                    "reason": "database insert needs explicit user approval before writing outside the immediate lane",
                }
            if parent_kind == "page":
                parent_page = retrieve_notion_page(
                    page_id=normalized_target_id,
                    token=settings["token"],
                    api_version=settings["api_version"],
                )
                parent_approved, parent_access_source = _page_access_matches_identity(
                    parent_page,
                    agent_row=agent_row,
                    identity=identity,
                    conn=conn,
                    allow_prior_agent_touch=True,
                )
                explicit_owner_channels = _notion_payload_people_property_names(payload)
                if not parent_approved:
                    return {
                        **base,
                        "would_queue": True,
                        "approval_required": True,
                        "approval_owner": "user",
                        "parent_access_source": parent_access_source,
                        "recommended_action": "ask-user-approval",
                        "reason": "target parent page is outside the verified caller's immediate write lane",
                    }
                if explicit_owner_channels:
                    approved, owner_source = _insert_payload_targets_verified_identity(payload, identity)
                    if not approved:
                        channels = ", ".join(explicit_owner_channels) or "people-typed columns"
                        return {
                            **base,
                            "would_queue": True,
                            "approval_required": True,
                            "approval_owner": "user",
                            "parent_access_source": parent_access_source,
                            "owner_source": "page-child-owner-scope",
                            "recommended_action": "ask-user-approval",
                            "reason": f"page child insert assigns {channels} outside the verified caller",
                        }
                    return {
                        **base,
                        "allowed": True,
                        "parent_access_source": parent_access_source,
                        "owner_source": owner_source,
                        "recommended_action": "write",
                        "reason": "page child insert is in the verified caller's lane",
                    }
                return {
                    **base,
                    "allowed": True,
                    "parent_access_source": parent_access_source,
                    "owner_source": f"page-parent-{parent_access_source or 'verified'}",
                    "recommended_action": "write",
                    "reason": "page child insert is in the verified caller's lane",
                }
            return {**base, "reason": f"unsupported Notion parent kind: {parent_kind or 'unknown'}"}

        if op in {"create_page", "create_database"}:
            parent_meta = resolve_notion_target(
                target_id=normalized_target_id,
                token=settings["token"],
                api_version=settings["api_version"],
            )
            parent_kind = str(parent_meta.get("kind") or "").strip()
            base["target_kind"] = parent_kind
            if parent_kind != "page":
                return {**base, "reason": f"{op} requires a target page parent"}
            parent_page = retrieve_notion_page(
                page_id=normalized_target_id,
                token=settings["token"],
                api_version=settings["api_version"],
            )
            parent_approved, parent_access_source = _page_access_matches_identity(
                parent_page,
                agent_row=agent_row,
                identity=identity,
                conn=conn,
                allow_prior_agent_touch=True,
            )
            created_kind = "page" if op == "create_page" else "database"
            if parent_approved:
                return {
                    **base,
                    "allowed": True,
                    "parent_access_source": parent_access_source,
                    "owner_source": f"page-parent-{parent_access_source or 'verified'}",
                    "recommended_action": "write",
                    "reason": f"{created_kind} creation will inherit the verified shared parent page permissions",
                }
            return {
                **base,
                "would_queue": True,
                "approval_required": True,
                "approval_owner": "user",
                "parent_access_source": parent_access_source,
                "owner_source": f"{op}-parent-ownership-mismatch",
                "recommended_action": "ask-user-approval",
                "reason": f"{created_kind} creation targets a shared parent page outside the verified caller's immediate write lane",
            }

        if op in {"update", "append"} and not normalized_target_id:
            raise ValueError(f"shared Notion {op}s require a target page id")
        page = retrieve_notion_page(
            page_id=normalized_target_id,
            token=settings["token"],
            api_version=settings["api_version"],
        )
        approved, owner_source = _page_access_matches_identity(
            page,
            agent_row=agent_row,
            identity=identity,
            conn=conn,
            allow_prior_agent_touch=True,
        )
        if approved:
            return {
                **base,
                "allowed": True,
                "target_kind": "page",
                "owner_source": owner_source,
                "recommended_action": "write",
                "reason": f"page {op} is in the verified caller's lane",
            }
        return {
            **base,
            "would_queue": True,
            "approval_required": True,
            "approval_owner": "user",
            "target_kind": "page",
            "owner_source": owner_source,
            "recommended_action": "ask-user-approval",
            "reason": f"page {op} is outside the verified caller's immediate write lane",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            **base,
            "reason": str(exc),
            "recommended_action": "inspect-target",
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
    """Accept brokered shared Notion writes. Reject archive/delete. Apply approved writes immediately."""
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
    if op in {"update", "append"} and not str(target_id or "").strip():
        raise ValueError(f"shared Notion {op}s require a target page id")
    normalized_target_id = _ssot_target_id_for_operation(settings, operation=op, target_id=target_id)
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
    reason = _ssot_write_gate_reason(identity)
    if reason:
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
        _validate_ssot_write_payload_shape(op, payload)
        return _apply_ssot_write(
            conn,
            settings=settings,
            agent_row=agent_row,
            identity=identity,
            agent_id=agent_id,
            operation=op,
            target_id=normalized_target_id,
            payload=payload,
            requested_by_actor=requested_by_actor,
            audit_payload=audit_payload,
        )
    except SSOTApprovalRequired as exc:
        return _queue_ssot_write_for_approval(
            conn,
            cfg,
            agent_row=agent_row,
            identity=identity,
            operation=op,
            target_id=normalized_target_id,
            payload=payload,
            requested_by_actor=requested_by_actor,
            request_reason=str(exc),
            request_source=exc.owner_source or "scope-mismatch",
            owner_identity=exc.owner_identity,
            owner_source=exc.owner_source,
            audit_payload=audit_payload,
        )
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


def approve_ssot_pending_write(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    pending_id: str,
    surface: str,
    actor: str,
) -> dict[str, Any]:
    pending_row = get_ssot_pending_write(conn, pending_id)
    if pending_row is None:
        raise ValueError(f"unknown pending SSOT write: {pending_id}")
    status = str(pending_row.get("status") or "").strip().lower()
    if status == "applied":
        return pending_row
    if status != "pending":
        reason = f"pending SSOT write is not awaiting approval: {status or 'unknown'}"
        log_ssot_access_audit(
            conn,
            agent_id=str(pending_row.get("agent_id") or ""),
            unix_user=str(pending_row.get("unix_user") or ""),
            notion_user_id=str(pending_row.get("notion_user_id") or ""),
            operation=str(pending_row.get("operation") or ""),
            target_id=str(pending_row.get("target_id") or ""),
            decision="deny",
            reason=f"pending SSOT write {pending_id} could not be approved: {reason}",
            actor=str(actor or "").strip(),
            request_payload={
                "pending_id": pending_id,
                "requested_by_actor": pending_row.get("requested_by_actor") or "",
                "decision_surface": surface,
            },
        )
        raise PermissionError(reason)
    try:
        agent_row, identity = _ssot_principal(conn, str(pending_row.get("agent_id") or ""))
    except PermissionError as exc:
        log_ssot_access_audit(
            conn,
            agent_id=str(pending_row.get("agent_id") or ""),
            unix_user=str(pending_row.get("unix_user") or ""),
            notion_user_id=str(pending_row.get("notion_user_id") or ""),
            operation=str(pending_row.get("operation") or ""),
            target_id=str(pending_row.get("target_id") or ""),
            decision="deny",
            reason=f"pending SSOT write {pending_id} cannot be approved right now: {exc}",
            actor=str(actor or "").strip(),
            request_payload={
                "pending_id": pending_id,
                "requested_by_actor": pending_row.get("requested_by_actor") or "",
                "decision_surface": surface,
            },
        )
        raise
    approval_gate_reason = _ssot_write_gate_reason(identity)
    if approval_gate_reason:
        reason = f"{approval_gate_reason} at approval time"
        log_ssot_access_audit(
            conn,
            agent_id=str(agent_row["agent_id"]),
            unix_user=str(agent_row["unix_user"]),
            notion_user_id=str(identity.get("notion_user_id") or ""),
            operation=str(pending_row.get("operation") or ""),
            target_id=str(pending_row.get("target_id") or ""),
            decision="deny",
            reason=f"pending SSOT write {pending_id} cannot be approved right now: {reason}",
            actor=str(actor or "").strip(),
            request_payload={
                "pending_id": pending_id,
                "requested_by_actor": pending_row.get("requested_by_actor") or "",
                "decision_surface": surface,
            },
        )
        raise PermissionError(reason)
    now_iso = utc_now_iso()
    conn.execute(
        """
        UPDATE ssot_pending_writes
        SET decision_surface = ?,
            decided_by_actor = ?,
            decided_at = ?,
            decision_note = 'approved'
        WHERE pending_id = ?
        """,
        (str(surface or "").strip(), str(actor or "").strip(), now_iso, str(pending_id or "").strip()),
    )
    conn.commit()
    try:
        log_ssot_access_audit(
            conn,
            agent_id=str(agent_row["agent_id"]),
            unix_user=str(agent_row["unix_user"]),
            notion_user_id=str(identity.get("notion_user_id") or ""),
            operation=str(pending_row.get("operation") or ""),
            target_id=str(pending_row.get("target_id") or ""),
            decision="approve",
            reason=f"{surface or 'approval'} approved pending SSOT write {pending_id}",
            actor=str(actor or "").strip(),
            request_payload={
                "pending_id": pending_id,
                "requested_by_actor": pending_row.get("requested_by_actor") or "",
                "decision_surface": surface,
            },
        )
        result = _apply_ssot_write(
            conn,
            settings=_require_shared_notion_settings(),
            agent_row=agent_row,
            identity=identity,
            agent_id=str(pending_row.get("agent_id") or ""),
            operation=str(pending_row.get("operation") or ""),
            target_id=str(pending_row.get("target_id") or ""),
            payload=pending_row.get("payload") if isinstance(pending_row.get("payload"), dict) else {},
            requested_by_actor=str(pending_row.get("requested_by_actor") or ""),
            audit_payload={
                "operation": str(pending_row.get("operation") or ""),
                "target_id": str(pending_row.get("target_id") or ""),
                "payload": pending_row.get("payload") if isinstance(pending_row.get("payload"), dict) else {},
                "pending_id": pending_id,
            },
            bypass_scope=True,
            pending_id=str(pending_id or ""),
            approval_actor=str(actor or "").strip(),
            approval_surface=str(surface or "").strip(),
        )
    except Exception as exc:
        conn.execute(
            """
            UPDATE ssot_pending_writes
            SET status = 'failed',
                decision_note = ?,
                apply_result_json = ?
            WHERE pending_id = ?
            """,
            (
                str(exc),
                json_dumps({"error": str(exc)}),
                str(pending_id or "").strip(),
            ),
        )
        conn.commit()
        log_ssot_access_audit(
            conn,
            agent_id=str(pending_row.get("agent_id") or ""),
            unix_user=str(pending_row.get("unix_user") or ""),
            notion_user_id=str(pending_row.get("notion_user_id") or ""),
            operation=str(pending_row.get("operation") or ""),
            target_id=str(pending_row.get("target_id") or ""),
            decision="fail",
            reason=f"approved pending SSOT write {pending_id} failed: {exc}",
            actor=str(actor or "").strip(),
            request_payload={
                "pending_id": pending_id,
                "requested_by_actor": pending_row.get("requested_by_actor") or "",
                "decision_surface": surface,
            },
        )
        raise
    conn.execute(
        """
        UPDATE ssot_pending_writes
        SET status = 'applied',
            applied_at = ?,
            apply_result_json = ?
        WHERE pending_id = ?
        """,
        (utc_now_iso(), json_dumps(result), str(pending_id or "").strip()),
    )
    conn.commit()
    updated = get_ssot_pending_write(conn, pending_id) or {}
    _notify_ssot_pending_write_resolution(
        conn,
        cfg,
        pending_row=updated,
        message=(
            f"SSOT pending write {pending_id} was approved by {actor or 'the user'} "
            f"and applied to {updated.get('target_id') or 'the requested target'}."
        ),
    )
    return updated


def deny_ssot_pending_write(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    pending_id: str,
    surface: str,
    actor: str,
    reason: str = "",
) -> dict[str, Any]:
    pending_row = get_ssot_pending_write(conn, pending_id)
    if pending_row is None:
        raise ValueError(f"unknown pending SSOT write: {pending_id}")
    status = str(pending_row.get("status") or "").strip().lower()
    if status == "denied":
        return pending_row
    if status != "pending":
        note = f"pending SSOT write is not awaiting approval: {status or 'unknown'}"
        log_ssot_access_audit(
            conn,
            agent_id=str(pending_row.get("agent_id") or ""),
            unix_user=str(pending_row.get("unix_user") or ""),
            notion_user_id=str(pending_row.get("notion_user_id") or ""),
            operation=str(pending_row.get("operation") or ""),
            target_id=str(pending_row.get("target_id") or ""),
            decision="deny",
            reason=f"pending SSOT write {pending_id} could not be denied: {note}",
            actor=str(actor or "").strip(),
            request_payload={
                "pending_id": pending_id,
                "requested_by_actor": pending_row.get("requested_by_actor") or "",
                "decision_surface": surface,
            },
        )
        raise PermissionError(note)
    note = str(reason or "").strip() or "denied"
    now_iso = utc_now_iso()
    conn.execute(
        """
        UPDATE ssot_pending_writes
        SET status = 'denied',
            decision_surface = ?,
            decided_by_actor = ?,
            decided_at = ?,
            decision_note = ?
        WHERE pending_id = ?
        """,
        (
            str(surface or "").strip(),
            str(actor or "").strip(),
            now_iso,
            note,
            str(pending_id or "").strip(),
        ),
    )
    conn.commit()
    log_ssot_access_audit(
        conn,
        agent_id=str(pending_row.get("agent_id") or ""),
        unix_user=str(pending_row.get("unix_user") or ""),
        notion_user_id=str(pending_row.get("notion_user_id") or ""),
        operation=str(pending_row.get("operation") or ""),
        target_id=str(pending_row.get("target_id") or ""),
        decision="deny",
        reason=f"{surface or 'approval'} denied pending SSOT write {pending_id}: {note}",
        actor=str(actor or "").strip(),
        request_payload={
            "pending_id": pending_id,
            "requested_by_actor": pending_row.get("requested_by_actor") or "",
            "decision_surface": surface,
        },
    )
    updated = get_ssot_pending_write(conn, pending_id) or {}
    _notify_ssot_pending_write_resolution(
        conn,
        cfg,
        pending_row=updated,
        message=(
            f"SSOT pending write {pending_id} was denied by {actor or 'the user'}"
            + (f": {note}" if note else ".")
        ),
    )
    return updated
def build_managed_memory_payload(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    agent_id: str,
    notion_stub_cache: dict[str, Any] | None = None,
    previous_today_plate_item_ids: object = None,
) -> dict[str, Any]:
    """Compose the canonical plugin-managed context payload for an agent.

    The skill contract is:
      [managed:arclink-skill-ref] default ArcLink skill routing hints
      [managed:org-profile]    operator-authored operating-context baseline and lineage
      [managed:user-responsibilities] current user's accountability, authority, and agent boundaries
      [managed:team-map]       other-person coordination context for this user's groups/teams
      [managed:vault-ref]      active vault path and role
      [managed:resource-ref]   user-specific access rails + shared host rails
      [managed:qmd-ref]        how to query qmd for retrieval
      [managed:notion-ref]     how to search/fetch/query shared Notion knowledge
      [managed:vault-topology] compact summary of subscribed vaults + briefs
      [managed:vault-landmarks] compact top-level vault map, including plain qmd-indexed folders
      [managed:recall-stubs]   small source-linked awareness cards that point to MCP retrieval for depth
      [managed:notion-landmarks] compact local-index map of shared Notion areas
      [managed:notion-stub]    Curator-produced shared Notion digest + verification state
      [managed:today-plate]    compact user-scoped involvement snapshot across any people-typed column on discovered task surfaces
    """
    agent = conn.execute(
        "SELECT agent_id, role, unix_user, display_name, hermes_home FROM agents WHERE agent_id = ?",
        (agent_id,),
    ).fetchone()
    if agent is None:
        raise ValueError(f"unknown agent: {agent_id}")

    catalog = list_vaults(conn)
    subscriptions = effective_subscriptions_for_agent(conn, agent_id)
    active_subscriptions = [row["vault_name"] for row in subscriptions if bool(row.get("push_enabled"))]

    topology_lines: list[str] = []
    for subscription in subscriptions:
        mark = "+" if bool(subscription.get("effective_subscribed")) else "-"
        source_label = "user" if subscription.get("hierarchy_source") == "user-override" else "default"
        default_label = "on" if int(subscription.get("default_subscribed") or 0) == 1 else "off"
        push_label = "on" if bool(subscription.get("push_enabled")) else "off"
        brief = (subscription.get("brief_template") or subscription.get("description") or "").strip()
        if brief:
            brief = brief.splitlines()[0][:140]
        line = (
            f"  {mark} {subscription['vault_name']}: "
            f"source={source_label}, default={default_label}, push={push_label}"
        )
        if brief:
            line += f" - {brief}"
        topology_lines.append(line)

    display_name = str(agent["display_name"] or "").strip()
    agent_role = str(agent["role"] or "").strip() or "user"
    agent_unix_user = str(agent["unix_user"] or "").strip()
    identity = get_agent_identity(conn, agent_id=agent_id, unix_user=agent_unix_user)
    hermes_home = Path(str(agent["hermes_home"] or "")).expanduser()
    access_state_path = hermes_home / "state" / "arclink-web-access.json"
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
    vault_root = str(workspace_root / "ArcLink")
    shared_host = shared_tailnet_host(
        tailscale_serve_enabled=(config_env_value("ENABLE_TAILSCALE_SERVE", "0").strip() == "1"),
        tailscale_dns_name=config_env_value("TAILSCALE_DNS_NAME", "").strip(),
        nextcloud_trusted_domain=config_env_value("NEXTCLOUD_TRUSTED_DOMAIN", "").strip(),
    )
    vault_ref = (
        f"Vault root: {vault_root}\n"
        "Use this user-visible path for vault file references in chat and VS Code.\n"
        "The shared vault is mounted through this alias; central service-user paths are internal infrastructure.\n"
        "Vault layout is organization-defined; top-level folders are allowed to be plain qmd-indexed folders or named .vault subscription lanes.\n"
        f"Agent id: {agent_id}\n"
        f"Dedicated agent name: {display_name or agent_id}\n"
        f"Assigned unix user: {agent_unix_user or '(unknown)'}\n"
        f"Role: {agent_role}\n"
        "Curator runs the shared ArcLink deployment and operator control plane.\n"
        "This agent works on behalf of one enrolled user inside that shared deployment."
    )
    skill_ref = (
        "Current ArcLink capability snapshot:\n"
        "- Installed ArcLink skills are live defaults on this dedicated user agent.\n"
        "- When a knowledge question could live in either files/PDFs or shared Notion, start with ArcLink MCP knowledge.search-and-fetch; it searches both rails with bounded defaults.\n"
        "- Use arclink-qmd-mcp for vault retrieval and follow-ups.\n"
        "- Use arclink-vaults for subscription, catalog, and curate-vaults work.\n"
        "- Use arclink-vault-reconciler for ArcLink memory drift or repair.\n"
        "- Use arclink-ssot for organization-aware SSOT coordination in the shared Notion workspace.\n"
        "- Use arclink-notion-knowledge for shared Notion knowledge search, exact page fetches, and targeted live structured database queries.\n"
        "- Use arclink-ssot-connect only for optional user-owned Notion MCP setup; it is not the default shared ArcLink Notion knowledge rail.\n"
        "- Use arclink-notion-mcp only as an optional personal Notion helper after that user-owned Notion MCP is actually live; do not treat it as the default shared ArcLink workspace-search lane.\n"
        "- For org-wide new Notion pages or databases, use the brokered ssot.write rail so creations are parented under the shared ArcLink page and inherit org access; do not use personal Notion MCP for shared SSOT creation.\n"
        "- Use arclink-resources for /arclink-resources, dashboard/code workspace links, remote helper setup, backup setup, and the user-visible ~/ArcLink vault path.\n"
        "- Use arclink-first-contact for ArcLink setup or diagnostic checks.\n"
        "- Org-published Hermes skills live under ~/ArcLink/Agents_Skills/*/skills and are wired into skills.external_dirs during install/refresh; use skills_list/skill_view when the skill is active, and qmd vault.search-and-fetch for source-level review or edits.\n"
        "- The shared vault does not require a fixed Projects/Repos taxonomy; qmd indexes text-like files anywhere under the vault root, and .vault files only define subscription/notification lanes.\n"
        "- All vaults remain retrievable through ArcLink/qmd even when a vault is unsubscribed; subscriptions only shape plugin-managed awareness and Curator push behavior.\n"
        "- Curator publishes a shared Notion digest into plugin-managed context so the agent has ambient SSOT orientation without live cross-user reads.\n"
        "- Curator publishes [managed:today-plate] as the user's compact involvement snapshot - every record across discovered task surfaces where the user appears in any people-typed column, regardless of what the workspace named that column. Use it as the structured starting point when the user asks about their work, focus, recent involvement, or what's on their plate; then verify live details before changing shared state.\n"
        "- The intended sync rail is curator fanout -> activation trigger / refresh timer -> user-agent-refresh -> local plugin context state and recent events.\n"
        "- ArcLink does not patch dynamic [managed:*] stubs into built-in MEMORY.md; the arclink-managed-context plugin hot-injects refreshed local ArcLink context into future turns without requiring /reset or a gateway restart once that plugin is loaded.\n"
        "- The arclink-managed-context plugin also injects [local:model-runtime] from Hermes's actual current-turn model argument, so model self-identification uses the live runtime instead of stale session prompts, saved memory, onboarding records, or config defaults after setup or model switches.\n"
        "- Treat the skill as the workflow and guardrail layer, and the wired broker/MCP/tool as the actuation layer.\n"
        "- For private/shared-vault questions, start with [managed:qmd-ref] and the current user's local ArcLink state; do not rediscover the qmd rail by repo-wide search unless that rail actually fails.\n"
        "- Human-facing completion or onboarding messages may omit machine-facing MCP/control rails for simplicity; [managed:resource-ref] is the authoritative map of the rails that this agent can try.\n"
        "- Do not decide that a rail is unavailable just because raw env vars are absent in a chat turn; use the installed skills, plugin-managed context, and ArcLink-provisioned rails as the source of truth.\n"
        "- When a brokered action is refused, explain whether the block is verification, ownership scope, or an unsupported archive/delete request instead of saying the skill is missing.\n"
        "- On a shared host, central service-user deployment paths are read-only shared infrastructure; use the current user's ~/ArcLink alias for vault files."
    )
    org_profile_sections: dict[str, Any] = {}
    try:
        from arclink_org_profile import build_managed_sections_for_agent

        org_profile_sections = build_managed_sections_for_agent(
            cfg,
            agent_id=agent_id,
            unix_user=agent_unix_user,
            display_name=display_name,
            org_profile_person_id=str((identity or {}).get("org_profile_person_id") or ""),
            human_display_name=str((identity or {}).get("human_display_name") or ""),
        )
    except Exception:
        org_profile_sections = {}
    qmd_ref = (
        f"qmd MCP (deep retrieval): {cfg.qmd_url}\n"
        "For private/shared-vault questions or follow-ups from the current\n"
        "discussion, start with this rail before searching repo files, docs,\n"
        "or the public web. Include the 'vault-pdf-ingest' collection when\n"
        "present for PDF-derived markdown.\n"
        "qmd indexes text-like files anywhere under the shared vault root;\n"
        "Repos/, Projects/, Research/, and org-specific folders are layout\n"
        "conventions, not retrieval boundaries. Moves and renames change qmd\n"
        "source paths, so old exact qmd file refs may go stale; search again\n"
        "by content after the watcher or 15-minute qmd refresh has run.\n"
        "If the user did not specify whether the answer is in the vault or\n"
        "shared Notion, prefer ArcLink MCP knowledge.search-and-fetch first;\n"
        "it searches vault/PDF and shared Notion together and returns tagged\n"
        "source buckets.\n"
        "Preferred normal path: call ArcLink MCP vault.search-and-fetch first;\n"
        "it wraps qmd query+get and returns fetched vault/PDF text as structured\n"
        "content. Keep it fast and bounded: one fetched result is usually enough.\n"
        "Use raw qmd query/get only for advanced retrieval or debugging.\n"
        "Live qmd MCP tool surface: query, get, multi_get, status.\n"
        "If you need routing confirmation, check [managed:resource-ref] and the\n"
        "current user's local ArcLink state before generic repo searches.\n"
        "Raw qmd MCP initialize/session-id details are for explicit ArcLink\n"
        "debugging only. Normal user answers should never expose or manually\n"
        "perform the raw MCP handshake. If a brokered ArcLink MCP tool reports a\n"
        "stale session error such as missing or invalid mcp-session-id, retry the\n"
        "same brokered ArcLink MCP tool once; if it still fails, tell the user the\n"
        "ArcLink knowledge rail needs operator repair and stop. Do not switch to\n"
        "raw curl or manual qmd protocol debugging unless the user explicitly asks\n"
        "to debug ArcLink itself.\n"
        "For advanced qmd debugging, query/get responses expose result.content[].text\n"
        "and result.structuredContent.results[]. For normal knowledge lookups,\n"
        "keep intent specific and consider combining lex and vec searches.\n"
        "Only inspect docs/hermes-qmd-config.yaml or qmd daemon files if the\n"
        "qmd path itself fails or the user is debugging ArcLink.\n"
        "Use arclink-ssot when the task is about organization state, Notion,\n"
        "or user-scoped SSOT updates; use qmd when the task is about vault depth.\n"
        "Use the already wired MCP endpoints and agent-local ArcLink state for\n"
        "site context even when a human-facing message leaves those rail URLs out.\n"
        "Never browse other users' home directories for ArcLink context.\n"
        "Do not read central deployment secrets such as arclink.env or source\n"
        "common.sh from a user-agent session."
    )
    notion_ref = (
        "Shared Notion knowledge rail: notion.search / notion.fetch / notion.query via ArcLink MCP.\n"
        "If the source is unclear, call knowledge.search-and-fetch before choosing\n"
        "a Notion-only or vault-only rail.\n"
        "Use notion.search for shared documentation, meeting notes, project pages,\n"
        "and user-generated knowledge that ArcLink has indexed into qmd.\n"
        "Use notion.fetch when you already know the exact page, database, or data\n"
        "source and need the live body or schema right now. Page fetches also\n"
        "return live attachment refs for Notion-hosted files on that page.\n"
        "Use notion.query for one exact live structured database or data-source target, such as a requested status view or due-date filter.\n"
        "For broad plate/focus/task orientation, answer from [managed:today-plate] first; if that is thin, use one bounded qmd-backed knowledge.search-and-fetch before any live query.\n"
        "Freshness depends on whether public webhook ingress is wired:\n"
        "- with ARCLINK_NOTION_WEBHOOK_PUBLIC_URL set and the webhook registered\n"
        "  in Notion, edits propagate to the index within seconds;\n"
        "- without it, the index only refreshes on the 1-hour Curator full sweep\n"
        "  (configurable via ARCLINK_NOTION_INDEX_FULL_SWEEP_INTERVAL_SECONDS),\n"
        "  so notion.search may be up to that interval behind live Notion edits.\n"
        "Fetch/query are live Notion API reads and never lag.\n"
        "This is a shared read rail, not the governed ssot.write approval path.\n"
        "Budget guidance: one search, then zero-to-three fetches before summarizing.\n"
        "notion.search defaults to hybrid BM25+vector scoring (rerank disabled) for\n"
        "sub-second responses; pass rerank:true when you need LLM-quality ranking and\n"
        "can absorb several seconds of latency per query.\n"
        "Bootstrap-token wrapper examples:\n"
        '{"tool":"notion.search","arguments":{"token":"<bootstrap token>","query":"Example Unicorn","limit":5}}\n'
        '{"tool":"notion.fetch","arguments":{"token":"<bootstrap token>","target_id":"https://www.notion.so/...page-id-or-data-source-id..."}}\n'
        '{"tool":"notion.query","arguments":{"token":"<bootstrap token>","target_id":"<database-or-data-source-id-or-url>","query":{"filter":{"property":"Status","status":{"equals":"In Progress"}}},"limit":25}}\n'
        "The default indexed qmd collection for this rail is notion-shared.\n"
        "Anything under the operator-configured shared Notion index roots becomes\n"
        "searchable by enrolled agents on this host; extractable Notion-hosted PDFs\n"
        "and text-like attachments on indexed pages are folded into that rail too.\n"
        "Do not assume per-user filtering on this rail.\n"
        "Do not fall back to repo-wide search just to rediscover this rail.\n"
        "When using the skill wrapper, let the local script read the bootstrap token\n"
        "from HERMES_HOME instead of copying secrets into chat.\n"
        "If notion.search returns thin or zero results, distinguish:\n"
        "- no indexed matches\n"
        "- not indexed yet / backfill still catching up\n"
        "- exact page is better served by notion.fetch\n"
        "- exact live structured state is better served by one targeted notion.query\n"
    )
    resource_ref = managed_resource_ref(
        access=access_state,
        workspace_root=workspace_root,
        shared_lines=shared_resource_lines(
            host=shared_host,
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
        ),
    )
    topology = (
        "Vault subscription hierarchy (precedence: user override > catalog default; push follows effective subscription):\n"
        + "\n".join(topology_lines)
    )
    vault_landmarks, vault_landmark_items = _build_vault_landmarks(
        cfg,
        subscriptions=subscriptions,
        vault_root=vault_root,
    )
    recall_stubs = _build_recall_stubs(
        conn,
        cfg,
        agent_row=agent,
        subscriptions=subscriptions,
        vault_root=vault_root,
    )
    notion_landmarks, notion_landmark_items = _build_notion_landmarks(conn)
    local_notion_stub_cache = notion_stub_cache if isinstance(notion_stub_cache, dict) else {}
    notion_stub = _build_notion_stub(
        conn,
        agent_row=agent,
        identity=identity,
        notion_stub_cache=local_notion_stub_cache,
    )
    today_plate = _build_today_plate(
        conn,
        agent_row=agent,
        identity=identity,
        notion_stub_cache=local_notion_stub_cache,
        previous_item_ids=previous_today_plate_item_ids,
    )
    today_plate_item_ids = [
        str(item or "").strip()
        for item in local_notion_stub_cache.get(f"today-plate-ids:{agent_id}", [])
        if str(item or "").strip()
    ]

    payload = {
        "agent_id": agent_id,
        "arclink-skill-ref": skill_ref,
        "org-profile": org_profile_sections.get("org-profile", ""),
        "user-responsibilities": org_profile_sections.get("user-responsibilities", ""),
        "team-map": org_profile_sections.get("team-map", ""),
        "org_profile_agent_context": org_profile_sections.get("org_profile_agent_context") or {},
        "org_profile_revision": org_profile_sections.get("org_profile_revision", ""),
        "vault-ref": vault_ref,
        "resource-ref": resource_ref,
        "qmd-ref": qmd_ref,
        "notion-ref": notion_ref,
        "vault-topology": topology,
        "vault-landmarks": vault_landmarks,
        "recall-stubs": recall_stubs,
        "notion-landmarks": notion_landmarks,
        "notion-stub": notion_stub,
        "today-plate": today_plate,
        "today_plate_item_ids": today_plate_item_ids,
        "vault_landmark_items": vault_landmark_items,
        "notion_landmark_items": notion_landmark_items,
        "catalog": catalog,
        "subscriptions": subscriptions,
        "active_subscriptions": active_subscriptions,
        "vault_path_contract": "user-home-arclink-v1",
    }
    payload["managed_memory_revision"] = _compute_managed_memory_revision(payload)
    payload["managed_payload_cache_key"] = _compute_managed_payload_cache_key(payload)
    return payload


_MEMORY_ENTRY_DELIMITER = "\n§\n"
_MANAGED_MEMORY_KEYS = (
    "arclink-skill-ref",
    "org-profile",
    "user-responsibilities",
    "team-map",
    "vault-ref",
    "resource-ref",
    "qmd-ref",
    "notion-ref",
    "vault-topology",
    "vault-landmarks",
    "recall-stubs",
    "notion-landmarks",
    "notion-stub",
    "today-plate",
)
_MANAGED_MEMORY_PREFIXES = tuple(f"[managed:{key}]" for key in _MANAGED_MEMORY_KEYS)
_MANAGED_PAYLOAD_CACHE_KEYS = (
    "agent_id",
    *_MANAGED_MEMORY_KEYS,
    "catalog",
    "subscriptions",
    "active_subscriptions",
    "vault_path_contract",
    "vault_landmark_items",
    "notion_landmark_items",
    "org_profile_agent_context",
    "org_profile_revision",
)


def _compute_managed_memory_revision(payload: dict[str, Any]) -> str:
    material = {
        key: str(payload.get(key) or "").strip()
        for key in _MANAGED_MEMORY_KEYS
    }
    blob = json.dumps(material, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _compute_managed_payload_cache_key(payload: dict[str, Any]) -> str:
    material = {
        key: payload.get(key)
        for key in _MANAGED_PAYLOAD_CACHE_KEYS
    }
    blob = json.dumps(material, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _first_nonempty_line(value: str, *, limit: int = 140) -> str:
    for raw_line in str(value or "").splitlines():
        line = raw_line.strip()
        if line:
            return line[:limit]
    return ""


def _render_changed_path_preview(paths: Sequence[str], *, limit: int = 4) -> str:
    normalized = [str(path or "").strip() for path in paths if str(path or "").strip()]
    if not normalized:
        return ""
    preview = ", ".join(normalized[:limit])
    if len(normalized) > limit:
        preview += f" ... (+{len(normalized) - limit} more)"
    return preview


def _recent_vault_change_rows_for_agent(conn: sqlite3.Connection, agent_id: str, *, limit: int = 8) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT message, extra_json, created_at
        FROM notification_outbox
        WHERE target_kind = 'user-agent'
          AND target_id = ?
          AND channel_kind = 'vault-change'
        ORDER BY id DESC
        LIMIT ?
        """,
        (str(agent_id or "").strip(), max(1, min(int(limit or 8), 20))),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        extra = json_loads(str(row["extra_json"] or "{}"), {})
        if not isinstance(extra, dict):
            extra = {}
        result.append(
            {
                "message": str(row["message"] or "").strip(),
                "created_at": str(row["created_at"] or "").strip(),
                "vault_name": str(extra.get("vault_name") or "").strip(),
                "paths": [
                    str(path or "").strip()
                    for path in (extra.get("paths") if isinstance(extra.get("paths"), list) else [])
                    if str(path or "").strip()
                ],
                "path_count": int(extra.get("path_count") or 0),
                "source": str(extra.get("source") or "").strip(),
            }
        )
    return result


_VAULT_LANDMARK_TEXT_SUFFIXES = {".md", ".markdown", ".mdx", ".txt", ".text"}
_VAULT_LANDMARK_REPO_DIR_NAMES = {"repos", "repositories"}


def _safe_list_dir(path: Path) -> list[Path]:
    try:
        if not path.is_dir():
            return []
        return sorted(path.iterdir(), key=lambda item: item.name.casefold())
    except OSError:
        return []


def _compact_unique(values: Sequence[str], *, limit: int = 4) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = " ".join(str(value or "").strip().split())
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
        if len(result) >= max(1, int(limit or 4)):
            break
    return result


def _compact_preview(values: Sequence[str], *, limit: int = 4) -> str:
    cleaned = _compact_unique(values, limit=200)
    if not cleaned:
        return ""
    visible = cleaned[:limit]
    preview = ", ".join(visible)
    if len(cleaned) > limit:
        preview += f" (+{len(cleaned) - limit} more)"
    return preview


def _landmark_query_terms(values: Sequence[str], *, limit: int = 24) -> list[str]:
    candidates: list[str] = []
    for value in values:
        cleaned = " ".join(str(value or "").strip().split())
        if not cleaned:
            continue
        candidates.append(cleaned)
        stem = Path(cleaned).stem
        if stem and stem != cleaned:
            candidates.append(stem)
        spaced = re.sub(r"[_\-.]+", " ", stem or cleaned).strip()
        if spaced and spaced.casefold() != cleaned.casefold():
            candidates.append(spaced)
    return _compact_unique(candidates, limit=limit)


def _build_vault_landmark_items(
    cfg: Config,
    *,
    subscriptions: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    vault_root = cfg.vault_dir
    if not vault_root.is_dir():
        return []
    subscriptions_by_name = {
        str(subscription.get("vault_name") or "").strip(): subscription
        for subscription in subscriptions
        if str(subscription.get("vault_name") or "").strip()
    }
    items: list[dict[str, Any]] = []
    for child in _safe_list_dir(vault_root):
        name = child.name
        if not name or name.startswith(".") or not child.is_dir():
            continue
        subscription = subscriptions_by_name.get(name, {})
        subscribed = bool(subscription.get("effective_subscribed")) or bool(subscription.get("push_enabled"))
        category = str(subscription.get("category") or "").strip()
        owner = str(subscription.get("owner") or "").strip()
        brief = _first_nonempty_line(
            str(subscription.get("brief_template") or subscription.get("description") or ""),
            limit=150,
        )
        children = _safe_list_dir(child)
        repo_inventory = name.casefold() in _VAULT_LANDMARK_REPO_DIR_NAMES or category.casefold() in {
            "repo",
            "repos",
            "repository",
            "repositories",
            "repository-inventory",
            "code",
        }
        repo_names: list[str] = []
        subfolders: list[str] = []
        file_names: list[str] = []
        pdf_names: list[str] = []
        for nested in children:
            nested_name = nested.name
            if not nested_name or nested_name.startswith("."):
                continue
            try:
                is_dir = nested.is_dir()
                is_file = nested.is_file()
            except OSError:
                continue
            if is_dir:
                if repo_inventory:
                    repo_names.append(nested_name)
                else:
                    subfolders.append(nested_name)
                continue
            if not is_file:
                continue
            suffix = nested.suffix.casefold()
            if suffix == ".pdf":
                pdf_names.append(nested_name)
            elif suffix in _VAULT_LANDMARK_TEXT_SUFFIXES:
                file_names.append(nested_name)

        kind = "subscription-lane" if subscription else "plain-folder"
        if (child / ".git").exists():
            kind = "git-repo"
        query_terms = _landmark_query_terms(
            [
                name,
                category,
                brief,
                *repo_names,
                *subfolders,
                *file_names,
                *pdf_names,
            ]
        )
        items.append(
            {
                "name": name,
                "kind": kind,
                "category": category,
                "owner": owner,
                "subscribed": subscribed,
                "repo_inventory": repo_inventory,
                "repo_names": _compact_unique(repo_names, limit=24),
                "subfolders": _compact_unique(subfolders, limit=24),
                "files": _compact_unique(file_names, limit=24),
                "pdfs": _compact_unique(pdf_names, limit=24),
                "brief": brief,
                "query_terms": query_terms,
            }
        )

    items.sort(
        key=lambda item: (
            0 if bool(item.get("subscribed")) else 1,
            0 if str(item.get("kind") or "") == "subscription-lane" else 1,
            str(item.get("name") or "").casefold(),
        )
    )
    return items


def _render_vault_landmarks(
    items: Sequence[dict[str, Any]],
    *,
    vault_root: str,
) -> str:
    lines = [
        "Vault landmarks:",
        "- Compact map only: names, folders, and filenames are recall cues, not evidence. Use knowledge.search-and-fetch or vault.search-and-fetch for content before answering.",
    ]
    if not items:
        lines.append("- Shared vault root is not readable yet, or no top-level vault folders have been discovered.")
        return "\n".join(lines)
    lines.append(
        f"- Coverage: {len(items)} top-level folder(s) under {vault_root}; .vault subscription lanes and plain qmd-indexed folders both count."
    )
    for item in items[:14]:
        name = str(item.get("name") or "").strip()
        traits: list[str] = []
        if bool(item.get("subscribed")):
            traits.append("subscribed")
        traits.append(str(item.get("kind") or "folder"))
        category = str(item.get("category") or "").strip()
        if category:
            traits.append(f"category={category}")
        owner = str(item.get("owner") or "").strip()
        if owner:
            traits.append(f"owner={owner}")

        details: list[str] = []
        brief = str(item.get("brief") or "").strip()
        if brief:
            details.append(brief)
        if bool(item.get("repo_inventory")):
            repo_preview = _compact_preview([str(v) for v in item.get("repo_names") or []], limit=5)
            if repo_preview:
                details.append(f"repos: {repo_preview}; do not infer deep subfolders until retrieved")
        else:
            folder_preview = _compact_preview([str(v) for v in item.get("subfolders") or []], limit=5)
            if folder_preview:
                details.append(f"subfolders: {folder_preview}")
        pdf_preview = _compact_preview([str(v) for v in item.get("pdfs") or []], limit=4)
        if pdf_preview:
            details.append(f"PDFs: {pdf_preview}")
        file_preview = _compact_preview([str(v) for v in item.get("files") or []], limit=4)
        if file_preview:
            details.append(f"files: {file_preview}")
        detail_suffix = f". {'; '.join(details)}" if details else "."
        lines.append(f"- {name}: {', '.join(traits)}{detail_suffix}")
    if len(items) > 14:
        lines.append(f"- Plus {len(items) - 14} more top-level folder(s); search by folder or project name for depth.")
    lines.append("- Routing: use this map to choose nouns; use retrieval tools for current text, PDFs, repo contents, and citations.")
    return "\n".join(lines)


def _build_vault_landmarks(
    cfg: Config,
    *,
    subscriptions: Sequence[dict[str, Any]],
    vault_root: str,
) -> tuple[str, list[dict[str, Any]]]:
    items = _build_vault_landmark_items(cfg, subscriptions=subscriptions)
    return _render_vault_landmarks(items, vault_root=vault_root), items


def _notion_landmark_area(breadcrumb: Sequence[Any], title: str) -> str:
    parts = [str(part or "").strip() for part in breadcrumb if str(part or "").strip()]
    compact_title = str(title or "").strip()
    if parts and compact_title and parts[-1].casefold() == compact_title.casefold():
        parts = parts[:-1]
    for part in reversed(parts):
        if part and part.casefold() not in {"untitled", "home"}:
            return part[:120]
    return (compact_title or "Root")[:120]


def _build_notion_landmark_items(conn: sqlite3.Connection, *, limit: int = 180) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(
            """
            SELECT source_page_id, source_page_url, source_kind, page_title,
                   breadcrumb_json, owners_json,
                   MAX(last_edited_time) AS last_edited_time,
                   MAX(indexed_at) AS indexed_at,
                   COUNT(*) AS section_count
            FROM notion_index_documents
            WHERE state = 'active'
            GROUP BY source_page_id
            ORDER BY MAX(CASE WHEN last_edited_time != '' THEN last_edited_time ELSE indexed_at END) DESC,
                     MAX(indexed_at) DESC
            LIMIT ?
            """,
            (max(1, min(int(limit or 180), 400)),),
        ).fetchall()
    except sqlite3.Error:
        return []

    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        page_id = str(row["source_page_id"] or "").strip()
        if not page_id:
            continue
        title = str(row["page_title"] or "").strip()
        breadcrumb = json_loads(str(row["breadcrumb_json"] or "[]"), [])
        if not isinstance(breadcrumb, list):
            breadcrumb = []
        owners = json_loads(str(row["owners_json"] or "[]"), [])
        if not isinstance(owners, list):
            owners = []
        area = _notion_landmark_area(breadcrumb, title)
        if not title:
            title = next((str(part).strip() for part in reversed(breadcrumb) if str(part).strip()), page_id[:8])
        entry = groups.setdefault(
            area,
            {
                "area": area,
                "count": 0,
                "examples": [],
                "owners": [],
                "last_edited_time": "",
                "indexed_at": "",
                "query_terms": [area],
            },
        )
        entry["count"] = int(entry.get("count") or 0) + 1
        if title:
            entry["examples"].append(title)
            entry["query_terms"].append(title)
        for owner in owners:
            owner_text = str(owner or "").strip()
            if owner_text:
                entry["owners"].append(owner_text)
                entry["query_terms"].append(owner_text)
        last_edited = str(row["last_edited_time"] or "").strip()
        indexed_at = str(row["indexed_at"] or "").strip()
        if last_edited and last_edited > str(entry.get("last_edited_time") or ""):
            entry["last_edited_time"] = last_edited
        if indexed_at and indexed_at > str(entry.get("indexed_at") or ""):
            entry["indexed_at"] = indexed_at

    items = list(groups.values())
    for item in items:
        item["examples"] = _compact_unique([str(value) for value in item.get("examples") or []], limit=8)
        item["owners"] = _compact_unique([str(value) for value in item.get("owners") or []], limit=6)
        item["query_terms"] = _landmark_query_terms([str(value) for value in item.get("query_terms") or []], limit=28)
    items.sort(
        key=lambda item: (
            int(item.get("count") or 0),
            str(item.get("last_edited_time") or str(item.get("indexed_at") or "")),
            str(item.get("area") or "").casefold(),
        ),
        reverse=True,
    )
    return items


def _render_notion_landmarks(items: Sequence[dict[str, Any]]) -> str:
    lines = [
        "Shared Notion landmarks:",
        "- Compact local-index map only: use these area names as query hints, not as evidence. Search/fetch/query before answering or changing shared state.",
    ]
    if not items:
        lines.append("- No active shared Notion index documents are visible locally yet. Use notion.fetch for exact URLs, or wait for the Notion index sync/backfill.")
        return "\n".join(lines)
    total_pages = sum(int(item.get("count") or 0) for item in items)
    lines.append(f"- Coverage: {total_pages} indexed page/source(s) across {len(items)} area(s).")
    for item in items[:10]:
        area = str(item.get("area") or "Root").strip()
        count = int(item.get("count") or 0)
        examples = _compact_preview([str(value) for value in item.get("examples") or []], limit=3)
        owners = _compact_preview([str(value) for value in item.get("owners") or []], limit=2)
        detail = f"{count} indexed page/source(s)"
        if examples:
            detail += f"; examples: {examples}"
        if owners:
            detail += f"; owners: {owners}"
        lines.append(f"- {area}: {detail}.")
    if len(items) > 10:
        lines.append(f"- Plus {len(items) - 10} more indexed Notion area(s); search by exact topic, owner, or page title.")
    lines.append("- Routing: docs/notes -> notion.search-and-fetch; exact page -> notion.fetch; one exact live database target -> notion.query; broad plate/focus questions -> [managed:today-plate] first.")
    return "\n".join(lines)


def _build_notion_landmarks(conn: sqlite3.Connection) -> tuple[str, list[dict[str, Any]]]:
    items = _build_notion_landmark_items(conn)
    return _render_notion_landmarks(items), items


def _memory_synthesis_card_lines(
    conn: sqlite3.Connection,
    *,
    subscriptions: Sequence[dict[str, Any]] | None = None,
) -> list[str]:
    try:
        limit = int(config_env_value("ARCLINK_MEMORY_SYNTH_CARDS_IN_CONTEXT", "8") or "8")
    except (TypeError, ValueError):
        limit = 8
    limit = max(1, min(limit, 30))
    subscribed_vaults = {
        str(subscription.get("vault_name") or "").strip()
        for subscription in (subscriptions or [])
        if bool(subscription.get("effective_subscribed")) or bool(subscription.get("push_enabled"))
    }
    subscribed_vaults.discard("")
    try:
        rows: list[sqlite3.Row] = []
        if subscribed_vaults:
            placeholders = ",".join("?" for _ in subscribed_vaults)
            rows.extend(
                conn.execute(
                    f"""
                    SELECT source_kind, source_key, source_title, card_text, updated_at
                    FROM memory_synthesis_cards
                    WHERE status = 'ok'
                      AND card_text != ''
                      AND source_kind = 'vault'
                      AND source_key IN ({placeholders})
                    ORDER BY updated_at DESC, source_key ASC
                    LIMIT ?
                    """,
                    (*sorted(subscribed_vaults), limit),
                ).fetchall()
            )
        rows.extend(
            conn.execute(
                """
                SELECT source_kind, source_key, source_title, card_text, updated_at
                FROM memory_synthesis_cards
                WHERE status = 'ok'
                  AND card_text != ''
                ORDER BY updated_at DESC, source_kind ASC, source_key ASC
                LIMIT ?
                """,
                (max(60, limit * 4),),
            ).fetchall()
        )
    except sqlite3.Error:
        return []
    deduped_rows: list[sqlite3.Row] = []
    seen_cards: set[tuple[str, str]] = set()
    for row in rows:
        marker = (str(row["source_kind"] or ""), str(row["source_key"] or ""))
        if marker in seen_cards:
            continue
        seen_cards.add(marker)
        deduped_rows.append(row)
    ranked_rows = sorted(
        deduped_rows,
        key=lambda row: (
            1 if str(row["source_kind"] or "") == "vault" and str(row["source_key"] or "") in subscribed_vaults else 0,
            str(row["updated_at"] or ""),
            str(row["source_kind"] or ""),
            str(row["source_key"] or ""),
        ),
        reverse=True,
    )
    lines = [str(row["card_text"] or "").strip() for row in ranked_rows[:limit] if str(row["card_text"] or "").strip()]
    if not lines:
        return []
    return [
        "Semantic synthesis cards:",
        "- LLM-compressed recall hints only: use retrieval tools for evidence, exact text, citations, or state changes.",
        *lines,
    ]


def _build_recall_stubs(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    agent_row: sqlite3.Row,
    subscriptions: Sequence[dict[str, Any]],
    vault_root: str,
) -> str:
    agent_id = str(agent_row["agent_id"] or "").strip()
    lines: list[str] = [
        "Retrieval memory stubs:",
        "- Treat these as awareness cards, not facts to answer from. Use MCP retrieval for the depth before citing or changing anything.",
        "- Default broad question path: knowledge.search-and-fetch with a specific natural-language query.",
        "- Vault/PDF/file path: vault.search-and-fetch; include vault-pdf-ingest for PDF-derived markdown.",
        "- Shared Notion path: notion.search-and-fetch for documentation/notes; notion.query only for one exact live structured database target.",
        f"- User-visible vault root for file references: {vault_root}",
    ]

    subscribed = [
        subscription
        for subscription in subscriptions
        if bool(subscription.get("effective_subscribed")) or bool(subscription.get("push_enabled"))
    ]
    if subscribed:
        lines.append("Subscribed awareness lanes:")
        for subscription in subscribed[:10]:
            vault_name = str(subscription.get("vault_name") or "").strip()
            category = str(subscription.get("category") or "").strip() or "vault"
            owner = str(subscription.get("owner") or "").strip() or "shared"
            brief = _first_nonempty_line(
                str(subscription.get("brief_template") or subscription.get("description") or ""),
                limit=120,
            )
            suffix = f" - {brief}" if brief else ""
            lines.append(
                f"- {vault_name}: category={category}, owner={owner}. "
                f"Ask vault.search-and-fetch for depth; current lane root is ~/ArcLink/{vault_name}.{suffix}"
            )
        if len(subscribed) > 10:
            lines.append(f"- Plus {len(subscribed) - 10} more subscribed vault(s); use vault-topology for the full list.")
    else:
        lines.append("Subscribed awareness lanes: none yet; use knowledge.search-and-fetch for broad discovery.")

    recent_changes = _recent_vault_change_rows_for_agent(conn, agent_id, limit=8)
    if recent_changes:
        lines.append("Recent hot-reload signals:")
        for change in recent_changes:
            vault_name = change.get("vault_name") or "vault"
            preview = _render_changed_path_preview(change.get("paths") or [])
            path_count = int(change.get("path_count") or len(change.get("paths") or []))
            created_at = str(change.get("created_at") or "").strip()
            source = str(change.get("source") or "").strip() or "vault-watch"
            detail = f"{path_count} path(s)"
            if preview:
                detail += f": {preview}"
            timestamp = f"{created_at} " if created_at else ""
            lines.append(
                f"- {timestamp}{vault_name} changed via {source}; {detail}. "
                "Use search-and-fetch for current contents; this stub only tells you where to look."
            )
    else:
        lines.append("Recent hot-reload signals: none queued for this agent.")

    synthesis_lines = _memory_synthesis_card_lines(conn, subscriptions=subscriptions)
    if synthesis_lines:
        lines.extend(synthesis_lines)

    lines.append(
        "Quality rule: if recall feels thin, say which rail was searched and retry once with narrower nouns, owner names, file titles, or source lane."
    )
    return "\n".join(lines)


def _read_text_file(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _read_json_dict(path: Path) -> dict[str, Any]:
    raw = _read_text_file(path)
    if not raw.strip():
        return {}
    payload = json_loads(raw, {})
    return payload if isinstance(payload, dict) else {}


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp", prefix=".arclink-memory-")
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


def _read_memory_entries(path: Path) -> list[str]:
    raw = _read_text_file(path)
    if not raw.strip():
        return []
    return [entry.strip() for entry in raw.split(_MEMORY_ENTRY_DELIMITER) if entry.strip()]


def _render_memory_entries(entries: list[str]) -> str:
    return _MEMORY_ENTRY_DELIMITER.join(entries) if entries else ""


def _write_memory_entries(path: Path, entries: list[str]) -> None:
    _atomic_write_text(path, _render_memory_entries(entries))


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
) -> dict[str, Any]:
    """Idempotently publish ArcLink's dynamic managed context for an agent.

    The canonical dynamic artifact is
    `$HERMES_HOME/state/arclink-vault-reconciler.json`, which the
    arclink-managed-context plugin reads and hot-injects into turns. Legacy
    markdown mirrors and `[managed:*]` entries in Hermes `MEMORY.md` are cleaned
    when encountered, but ArcLink no longer writes dynamic recall stubs through
    Hermes memory files.

    `SOUL.md` remains the durable onboarding/orientation prompt. It is
    materialized only when the payload carries org-profile agent context; a
    dynamic refresh without org-profile context does not clear an existing
    `SOUL.md` overlay.

    Returns the paths written. Called from the user-agent-refresh context
    running as the enrollment user - never from the central curator (which runs
    as a different uid and would violate the HOME boundary).
    """
    payload = dict(payload)
    if "arclink-skill-ref" not in payload and "skill-ref" in payload:
        payload["arclink-skill-ref"] = payload["skill-ref"]
    payload.setdefault(
        "arclink-skill-ref",
        "Installed ArcLink skills are live defaults on this dedicated user agent."
        " Use knowledge.search-and-fetch when the source could be either vault/PDF"
        " or shared Notion."
        " Use arclink-qmd-mcp for vault retrieval and follow-ups, arclink-vaults"
        " for subscription and catalog work, arclink-vault-reconciler for ArcLink"
        " memory drift or repair, arclink-ssot for organization-aware SSOT"
        " coordination, arclink-notion-knowledge for the shared Notion knowledge"
        " rail, arclink-ssot-connect only for optional user-owned"
        " Notion MCP setup, arclink-notion-mcp only as that separate personal"
        " Notion helper once the MCP is live, arclink-resources for"
        " /arclink-resources and user-facing dashboard/code/vault links, and arclink-first-contact for"
        " ArcLink setup or diagnostic checks. All vaults remain retrievable"
        " through ArcLink/qmd even when a vault is unsubscribed; subscriptions"
        " only shape plugin-managed awareness and Curator push behavior. On a"
        " shared host, central service-user deployment paths are read-only shared"
        " infrastructure; use the current user's ~/ArcLink alias for vault files.",
    )
    payload.setdefault(
        "resource-ref",
        "Canonical user access rails and shared ArcLink addresses:\n"
        "- Credentials are intentionally omitted from plugin-managed context.\n"
        "- Ask Curator or the operator to reissue access if the user loses those credentials.",
    )
    payload.setdefault(
        "notion-ref",
        "Shared Notion knowledge rail: notion.search / notion.fetch / notion.query via ArcLink MCP.\n"
        "Use notion.search for indexed knowledge, notion.fetch for an exact live page,"
        " and notion.query only for one exact live structured database target.",
    )
    payload.setdefault(
        "notion-stub",
        "Shared Notion digest:\n- Curator has not published a Notion digest into plugin-managed context yet.",
    )
    payload.setdefault(
        "vault-landmarks",
        "Vault landmarks:\n- Curator has not published a compact vault landmark map into plugin-managed context yet.",
    )
    payload.setdefault(
        "notion-landmarks",
        "Shared Notion landmarks:\n- Curator has not published a compact Notion landmark map into plugin-managed context yet.",
    )
    payload.setdefault(
        "today-plate",
        "Today plate:\n- Curator has not published a user-scoped work snapshot into plugin-managed context yet.",
    )
    payload.setdefault("vault_landmark_items", [])
    payload.setdefault("notion_landmark_items", [])
    payload.setdefault("managed_memory_revision", _compute_managed_memory_revision(payload))
    payload.setdefault("active_subscriptions", [
        str(row.get("vault_name") or "")
        for row in payload.get("subscriptions", [])
        if bool(row.get("push_enabled")) or int(row.get("subscribed") or 0) == 1
    ])
    payload.setdefault("managed_payload_cache_key", _compute_managed_payload_cache_key(payload))

    state_dir = hermes_home / "state"
    memories_dir = hermes_home / "memories"
    state_dir.mkdir(parents=True, exist_ok=True)

    now = utc_now_iso()
    state_path = state_dir / "arclink-vault-reconciler.json"
    state_payload = {
        "agent_id": payload["agent_id"],
        "arclink-skill-ref": payload["arclink-skill-ref"],
        "org-profile": payload.get("org-profile") or "",
        "user-responsibilities": payload.get("user-responsibilities") or "",
        "team-map": payload.get("team-map") or "",
        "org_profile_revision": payload.get("org_profile_revision") or "",
        "org_profile_agent_context": payload.get("org_profile_agent_context") or {},
        "vault-ref": payload["vault-ref"],
        "resource-ref": payload["resource-ref"],
        "qmd-ref": payload["qmd-ref"],
        "notion-ref": payload["notion-ref"],
        "vault-topology": payload["vault-topology"],
        "vault-landmarks": payload.get("vault-landmarks") or "",
        "recall-stubs": payload.get("recall-stubs") or "",
        "notion-landmarks": payload.get("notion-landmarks") or "",
        "notion-stub": payload.get("notion-stub") or "",
        "today-plate": payload.get("today-plate") or "",
        "vault_landmark_items": payload.get("vault_landmark_items") or [],
        "notion_landmark_items": payload.get("notion_landmark_items") or [],
        "catalog": payload["catalog"],
        "subscriptions": payload["subscriptions"],
        "active_subscriptions": payload.get("active_subscriptions") or [],
        "managed_memory_revision": str(payload["managed_memory_revision"]),
        "managed_payload_cache_key": str(payload["managed_payload_cache_key"]),
    }
    existing_state = _read_json_dict(state_path)
    comparable_existing_state = {
        key: existing_state.get(key)
        for key in state_payload
    }
    state_changed = (not state_path.is_file()) or comparable_existing_state != state_payload
    if state_changed:
        _atomic_write_text(
            state_path,
            json.dumps({**state_payload, "updated_at": now}, indent=2, sort_keys=True) + "\n",
        )

    stub_path = memories_dir / "arclink-managed-stubs.md"
    legacy_stub_removed = False
    if stub_path.exists():
        stub_path.unlink()
        legacy_stub_removed = True

    memory_path = memories_dir / "MEMORY.md"
    memory_changed = False
    if memory_path.exists():
        existing_entries = _read_memory_entries(memory_path)
        filtered_entries = [
            entry
            for entry in existing_entries
            if not any(entry.lstrip().startswith(prefix) for prefix in _MANAGED_MEMORY_PREFIXES)
        ]
        memory_changed = len(filtered_entries) != len(existing_entries)
        if memory_changed:
            desired_memory_content = _render_memory_entries(filtered_entries)
            _atomic_write_text(memory_path, desired_memory_content)

    org_profile_context = payload.get("org_profile_agent_context")
    org_profile_paths: dict[str, Any] = {}
    if isinstance(org_profile_context, dict) and org_profile_context:
        try:
            from arclink_org_profile import materialize_agent_context

            org_profile_paths = materialize_agent_context(hermes_home, org_profile_context)
        except Exception as exc:  # noqa: BLE001
            org_profile_paths = {"org_profile_error": str(exc)}

    org_profile_changed = bool(org_profile_paths.get("changed")) if org_profile_paths else False
    result = {
        "state_path": str(state_path),
        "stub_path": str(stub_path),
        "legacy_stub_path": str(stub_path),
        "memory_path": str(memory_path),
        "state_changed": state_changed,
        "stub_changed": legacy_stub_removed,
        "legacy_stub_removed": legacy_stub_removed,
        "memory_changed": memory_changed,
        "legacy_memory_cleaned": memory_changed,
        **org_profile_paths,
    }
    result["changed"] = state_changed or legacy_stub_removed or memory_changed or org_profile_changed
    return result


def _central_managed_payload_path(cfg: Config, agent_id: str) -> Path:
    return cfg.agents_state_dir / agent_id / "managed-memory.json"


def _grant_managed_payload_read_access(conn: sqlite3.Connection, cfg: Config, path: Path, agent_id: str) -> None:
    row = conn.execute(
        "SELECT unix_user FROM agents WHERE agent_id = ? AND role = 'user' AND status = 'active'",
        (agent_id,),
    ).fetchone()
    unix_user = str(row["unix_user"] or "").strip() if row else ""
    try:
        path.chmod(0o640)
    except PermissionError:
        pass
    if not unix_user or shutil.which("setfacl") is None:
        return
    dirs = []
    for directory in (cfg.private_dir, cfg.state_dir, cfg.agents_state_dir, path.parent):
        resolved = directory.resolve()
        if resolved not in dirs:
            dirs.append(resolved)
    for directory in dirs:
        perms = "rX" if directory == cfg.private_dir.resolve() else "x"
        subprocess.run(
            ["setfacl", "-m", f"u:{unix_user}:{perms}", str(directory)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    subprocess.run(
        ["setfacl", "-m", f"u:{unix_user}:r", str(path)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def publish_central_managed_memory(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    agent_id: str,
    notion_stub_cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write the agent's plugin-context payload into the shared state dir so
    the user-agent-refresh worker (running as the enrollment user) can read
    the curator's latest view without crossing uid boundaries."""
    out_path = _central_managed_payload_path(cfg, agent_id)
    existing_payload = _read_json_dict(out_path)
    previous_today_plate_item_ids = existing_payload.get("today_plate_item_ids")
    payload = build_managed_memory_payload(
        conn,
        cfg,
        agent_id=agent_id,
        notion_stub_cache=notion_stub_cache,
        previous_today_plate_item_ids=previous_today_plate_item_ids,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    existing_cache_key = str(
        existing_payload.get("managed_payload_cache_key")
        or (_compute_managed_payload_cache_key(existing_payload) if existing_payload else "")
    )
    changed = (not out_path.is_file()) or existing_cache_key != str(payload["managed_payload_cache_key"])
    if changed:
        _atomic_write_text(out_path, json.dumps({**payload, "updated_at": utc_now_iso()}, indent=2, sort_keys=True) + "\n")

    _grant_managed_payload_read_access(conn, cfg, out_path, agent_id)
    return {
        "path": str(out_path),
        "changed": changed,
        "managed_memory_revision": str(payload["managed_memory_revision"]),
        "managed_payload_cache_key": str(payload["managed_payload_cache_key"]),
    }


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
    plugin-context payloads for each impacted agent (shared state, no HERMES
    writes), and mark the notifications delivered.

    Each enrollment user's `user-agent-refresh.sh` then picks up the central
    payload on its next run (every 4h or on agent boot) and writes plugin state
    into the user's own HERMES_HOME. This respects the uid boundary between
    curator and user agents."""
    now_iso = utc_now_iso()
    due_rows = conn.execute(
        """
        SELECT id, target_id, message, next_attempt_at, attempt_count
        FROM notification_outbox
        WHERE delivered_at IS NULL
          AND target_kind = 'curator'
          AND channel_kind = 'brief-fanout'
          AND (next_attempt_at IS NULL OR next_attempt_at = '' OR next_attempt_at <= ?)
        ORDER BY id ASC
        """,
        (now_iso,),
    ).fetchall()

    expanded_notifications = 0
    expanded_agents = 0
    catalog_events: list[str] = []
    global_rows = [
        row for row in due_rows
        if str(row["target_id"] or "").strip() in {"", "curator"}
    ]
    if global_rows:
        active_agents = [
            str(agent["agent_id"] or "").strip()
            for agent in conn.execute(
                "SELECT agent_id FROM agents WHERE role = 'user' AND status = 'active'"
            ).fetchall()
        ]
        for row in global_rows:
            expanded_notifications += 1
            catalog_events.append(str(row["message"] or ""))
            for agent_id in active_agents:
                if not agent_id:
                    continue
                _queue_curator_fanout_agent_notification(
                    conn,
                    agent_id=agent_id,
                    message=str(row["message"] or ""),
                    source_notification_id=int(row["id"]),
                )
                expanded_agents += 1
        conn.executemany(
            """
            UPDATE notification_outbox
            SET delivered_at = ?, delivery_error = NULL
            WHERE id = ?
            """,
            [(now_iso, int(row["id"])) for row in global_rows],
        )
        conn.commit()

    agent_rows = conn.execute(
        """
        SELECT id, target_id, message, next_attempt_at, attempt_count
        FROM notification_outbox
        WHERE delivered_at IS NULL
          AND target_kind = 'curator'
          AND channel_kind = 'brief-fanout'
          AND target_id NOT IN ('', 'curator')
        ORDER BY id ASC
        """
    ).fetchall()

    published: list[dict[str, Any]] = []
    failures: list[str] = []
    cache_hits = 0
    refresh_signals = 0
    skipped_stale_agents = 0
    processed_notifications = len(global_rows)
    notion_stub_cache: dict[str, Any] = {}
    rows_by_agent: dict[str, list[sqlite3.Row]] = {}
    for row in agent_rows:
        agent_id = str(row["target_id"] or "").strip()
        if not agent_id:
            continue
        rows_by_agent.setdefault(agent_id, []).append(row)

    for agent_id in sorted(rows_by_agent):
        grouped_rows = rows_by_agent[agent_id]
        if not any(_notification_due_now(str(row["next_attempt_at"] or "")) for row in grouped_rows):
            continue
        processed_notifications += len(grouped_rows)
        agent_row = conn.execute(
            "SELECT role, status FROM agents WHERE agent_id = ?",
            (agent_id,),
        ).fetchone()
        if (
            agent_row is None
            or str(agent_row["role"] or "") != "user"
            or str(agent_row["status"] or "") != "active"
        ):
            skipped_stale_agents += 1
            stale_reason = f"stale or inactive agent target skipped: {agent_id}"
            conn.executemany(
                """
                UPDATE notification_outbox
                SET delivered_at = ?, delivery_error = ?
                WHERE id = ?
                """,
                [(utc_now_iso(), stale_reason, int(row["id"])) for row in grouped_rows],
            )
            conn.commit()
            continue
        try:
            publish_result = publish_central_managed_memory(
                conn,
                cfg,
                agent_id=agent_id,
                notion_stub_cache=notion_stub_cache,
            )
            published_payload = {"agent_id": agent_id, **publish_result}
            pending_agent_notifications = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM notification_outbox
                WHERE delivered_at IS NULL
                  AND target_kind = 'user-agent'
                  AND target_id = ?
                """,
                (agent_id,),
            ).fetchone()
            has_pending_agent_notifications = int(
                pending_agent_notifications["c"] if pending_agent_notifications is not None else 0
            ) > 0
            if bool(publish_result.get("changed")) or has_pending_agent_notifications:
                trigger_path = signal_agent_refresh_from_curator(
                    conn,
                    cfg,
                    agent_id=agent_id,
                    note=(
                        "curator brief-fanout: refresh plugin-managed context"
                        if bool(publish_result.get("changed"))
                        else "curator brief-fanout: consume pending ArcLink event notifications"
                    ),
                )
                if trigger_path is not None:
                    published_payload["activation_trigger_path"] = str(trigger_path)
                    refresh_signals += 1
            else:
                cache_hits += 1
            published.append(published_payload)
            conn.executemany(
                """
                UPDATE notification_outbox
                SET delivered_at = ?, delivery_error = NULL
                WHERE id = ?
                """,
                [(utc_now_iso(), int(row["id"])) for row in grouped_rows],
            )
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            attempts = _record_curator_fanout_retry(
                conn,
                cfg,
                notification_ids=[int(row["id"]) for row in grouped_rows],
                error_message=str(exc),
            )
            retry_at = conn.execute(
                """
                SELECT next_attempt_at
                FROM notification_outbox
                WHERE id = ?
                """,
                (int(grouped_rows[0]["id"]),),
            ).fetchone()
            retry_label = format_utc_iso_brief(str(retry_at["next_attempt_at"] or "")) if retry_at is not None else ""
            failures.append(
                f"{agent_id}:{exc} (attempt {attempts}; retry {retry_label or 'scheduled'})"
            )

    note_refresh_job(
        conn,
        job_name="curator-brief-fanout",
        job_kind="curator-fanout",
        target_id="curator",
        schedule="on-demand",
        status="ok" if not failures else "warn",
        note=(
            f"processed_notifications={processed_notifications}; "
            f"expanded_notifications={expanded_notifications}; "
            f"published {len(published)} central payload(s); "
            f"cache_hits={cache_hits}; refresh_signals={refresh_signals}; "
            f"skipped_stale_agents={skipped_stale_agents}; failures={len(failures)}"
        ),
    )
    return {
        "processed_notifications": processed_notifications,
        "expanded_notifications": expanded_notifications,
        "expanded_agents": expanded_agents,
        "published_agents": published,
        "failures": failures,
        "catalog_events": catalog_events,
        "cache_hits": cache_hits,
        "refresh_signals": refresh_signals,
        "skipped_stale_agents": skipped_stale_agents,
    }


def _map_event_to_affected_users(conn: sqlite3.Connection, payload: dict[str, Any]) -> tuple[list[str], bool, dict[str, Any]]:
    owner_identity, _ = _notion_owner_identity(payload)
    resolved = True
    routing_payload = payload
    if not owner_identity:
        hydrated_payload, resolved = _hydrate_notion_event_entity(payload)
        if hydrated_payload:
            routing_payload = hydrated_payload
            owner_identity, _ = _notion_owner_identity(hydrated_payload)
    if not owner_identity:
        return [], resolved, routing_payload
    agent = _find_agent_for_owner(conn, owner_identity)
    return ([agent["agent_id"]] if agent else []), resolved, routing_payload


def _signal_kind(event_type: str, payload: dict[str, Any]) -> str:
    kind = (event_type or "").lower()
    if "comment" in kind or "mention" in kind:
        return "focus-nudge"
    if "page" in kind and ("properties_updated" in kind or "content_updated" in kind):
        return "task-reminder"
    if "created" in kind:
        return "org-activity"
    return "org-activity"


def _notion_event_action_label(event_type: str) -> str:
    kind = str(event_type or "").strip().lower()
    if "mention" in kind:
        return "mention"
    if "comment" in kind:
        return "comment"
    if "properties_updated" in kind:
        return "properties updated"
    if "content_updated" in kind:
        return "content updated"
    if "created" in kind:
        return "created"
    if "deleted" in kind:
        return "deleted"
    if "restored" in kind:
        return "restored"
    return kind or "changed"


def _notion_signal_label(signal: str) -> str:
    normalized = str(signal or "").strip().lower()
    if normalized == "focus-nudge":
        return "focus nudge"
    if normalized == "task-reminder":
        return "work update"
    return "workspace activity"


def _render_notion_agent_nudge(entries: list[dict[str, str]]) -> str:
    clean_entries = [entry for entry in entries if isinstance(entry, dict)]
    if not clean_entries:
        return "Notion digest: shared Notion changed. Use notion.query/notion.fetch, or verified ssot.read for scoped brokered targets, before changing shared state."
    total = len(clean_entries)
    counts: dict[str, int] = {}
    for entry in clean_entries:
        label = str(entry.get("signal_label") or "workspace activity").strip()
        counts[label] = counts.get(label, 0) + 1
    count_text = ", ".join(f"{count} {label}" for label, count in sorted(counts.items()))
    examples: list[str] = []
    for entry in clean_entries[:3]:
        action = str(entry.get("action") or "changed").strip()
        target = str(entry.get("target") or "Notion item").strip()
        event_ref = _short_notion_ref(str(entry.get("event_id") or ""))
        examples.append(f"{action} on {target} (event {event_ref})")
    suffix = "" if total <= len(examples) else f"; +{total - len(examples)} more"
    return (
        f"Notion digest: {total} scoped update(s) for this user"
        + (f" ({count_text})" if count_text else "")
        + ". Examples: "
        + "; ".join(examples)
        + suffix
        + ". Check live details with notion.query/notion.fetch, or verified ssot.read for scoped brokered targets, before acting."
    )


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
    nudges_by_agent: dict[str, list[dict[str, str]]] = {}
    reindex_entities: set[tuple[str, str]] = set()
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
        claim_page_event = False
        if entity_id and entity_type == "page":
            claim = get_notion_identity_claim(conn, notion_page_id=entity_id)
            if claim is not None and str(claim.get("status") or "").strip() == "pending":
                claim_page_event = True
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
        if entity_id and not claim_page_event:
            if entity_type in {"page", "database"}:
                reindex_entities.add((entity_type, entity_id))
            elif entity_type in {"data_source", "file_upload"}:
                # These events can materially change shared search freshness,
                # but the webhook payload does not always give us a single
                # page target we can reindex cheaply. Fall back to a full sync
                # for correctness.
                reindex_entities.add(("full", "full"))
        affected, resolved, routing_payload = _map_event_to_affected_users(conn, payload)
        signal = _signal_kind(row["event_type"], routing_payload)

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
                {
                    "signal": signal,
                    "signal_label": _notion_signal_label(signal),
                    "event_type": str(row["event_type"] or ""),
                    "event_id": str(row["event_id"] or ""),
                    "action": _notion_event_action_label(str(row["event_type"] or "")),
                    "target": _notion_event_entity_label(routing_payload),
                }
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
            message=_render_notion_agent_nudge(tokens),
            extra={"events": tokens},
        )
        queue_notification(
            conn,
            target_kind="curator",
            target_id=agent_id,
            channel_kind="brief-fanout",
            message=f"notion event refresh for {agent_id}",
        )
    for entity_type, entity_id in sorted(reindex_entities):
        _queue_notion_reindex_notification(
            conn,
            target_id=entity_id,
            source_kind=entity_type,
            message=f"notion {entity_type} reindex for {entity_id}",
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
        schedule="every 1m",
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
        "reindex_entities": len(reindex_entities),
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
