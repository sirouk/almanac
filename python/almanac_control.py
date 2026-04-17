#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import ipaddress
import json
import os
import pwd
import secrets
import shlex
import sqlite3
import string
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def utc_now_iso() -> str:
    return utc_now().replace(microsecond=0).isoformat()


def bool_env(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


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


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _python_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _discover_config_file() -> Path | None:
    explicit = os.environ.get("ALMANAC_CONFIG_FILE")
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.is_file() else path

    repo_root = Path(os.environ.get("ALMANAC_REPO_DIR", _python_repo_root())).expanduser().resolve()
    operator_artifact = Path(
        os.environ.get("ALMANAC_OPERATOR_ARTIFACT_FILE", str(repo_root / ".almanac-operator.env"))
    ).expanduser()
    if operator_artifact.is_file():
        try:
            for raw_line in operator_artifact.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, raw_value = line.split("=", 1)
                if key.strip() != "ALMANAC_OPERATOR_DEPLOYED_CONFIG_FILE":
                    continue
                try:
                    parsed = shlex.split(raw_value.strip(), posix=True)
                    value = "" if not parsed else parsed[0]
                except ValueError:
                    value = raw_value.strip().strip("'\"")
                if value:
                    path = Path(value).expanduser()
                    return path
        except OSError:
            pass

    nested_priv = repo_root / "almanac-priv" / "config" / "almanac.env"
    sibling_priv = repo_root.parent / "almanac-priv" / "config" / "almanac.env"
    candidates = (
        repo_root / "config" / "almanac.env",
        nested_priv,
        sibling_priv,
        Path.home() / "almanac" / "almanac-priv" / "config" / "almanac.env",
        Path.home() / "almanac-priv" / "config" / "almanac.env",
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def _load_config_env() -> dict[str, str]:
    merged = dict(os.environ)
    config_path = _discover_config_file()
    if config_path is None or not config_path.is_file():
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
                default=(operator_notify_platform == "telegram"),
            ),
            onboarding_window_seconds=int(env.get("ALMANAC_ONBOARDING_WINDOW_SECONDS", "3600")),
            onboarding_per_telegram_user_limit=int(env.get("ALMANAC_ONBOARDING_PER_TELEGRAM_USER_LIMIT", "3")),
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
          created_at TEXT NOT NULL,
          delivered_at TEXT,
          delivery_error TEXT
        );

        CREATE TABLE IF NOT EXISTS notion_webhook_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          event_id TEXT NOT NULL UNIQUE,
          event_type TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          received_at TEXT NOT NULL,
          batch_status TEXT NOT NULL DEFAULT 'pending',
          processed_at TEXT
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
    conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    names = {str(row["name"]) for row in rows}
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
    return onboarding_secret_dir(cfg) / session_id / "telegram-bot-token"


def write_onboarding_bot_token_secret(cfg: Config, session_id: str, raw_token: str) -> str:
    path = onboarding_bot_token_secret_path(cfg, session_id)
    _write_private_text(path, raw_token)
    return str(path)


def read_onboarding_bot_token_secret(raw_path: str) -> str:
    path = Path(raw_path).expanduser()
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def delete_onboarding_bot_token_secret(raw_path: str) -> None:
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
            secret_path = write_onboarding_bot_token_secret(cfg, session_id, token)
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
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO notification_outbox (target_kind, target_id, channel_kind, message, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (target_kind, target_id, channel_kind, message, utc_now_iso()),
    )
    conn.commit()
    return int(cursor.lastrowid)


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
        SELECT id, target_kind, target_id, channel_kind, message, created_at, delivery_error
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
    try:
        path.chmod(0o755)
    except OSError:
        pass
    return path


def activation_trigger_path(cfg: Config, agent_id: str) -> Path:
    return activation_trigger_dir(cfg) / f"{agent_id}.json"


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
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
    queue_notification(
        conn,
        target_kind="operator",
        target_id=cfg.operator_notify_channel_id or cfg.operator_notify_platform or "operator",
        channel_kind=cfg.operator_notify_platform or "tui-only",
        message=message,
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
    rows = conn.execute(
        """
        SELECT *
        FROM bootstrap_requests
        WHERE status = 'approved'
          AND auto_provision = 1
          AND provisioned_at IS NULL
          AND COALESCE(provision_attempts, 0) < ?
          AND (provision_next_attempt_at IS NULL OR provision_next_attempt_at <= ?)
        ORDER BY COALESCE(provision_next_attempt_at, approved_at, requested_at) ASC
        """
        ,
        (cfg.auto_provision_max_attempts, now_iso),
    ).fetchall()
    return [dict(row) for row in rows]


def mark_auto_provision_started(conn: sqlite3.Connection, request_id: str) -> int:
    conn.execute(
        """
        UPDATE bootstrap_requests
        SET provision_started_at = ?,
            provision_attempts = COALESCE(provision_attempts, 0) + 1,
            provision_error = NULL,
            provision_next_attempt_at = NULL
        WHERE request_id = ?
        """,
        (utc_now_iso(), request_id),
    )
    conn.commit()
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
            SET provision_error = ?, provision_next_attempt_at = ?
            WHERE request_id = ?
            """,
            (error, next_attempt_at or None, request_id),
        )
    else:
        conn.execute(
            """
            UPDATE bootstrap_requests
            SET provisioned_at = ?, provision_error = NULL, provision_next_attempt_at = NULL
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

    conn.execute(
        """
        UPDATE agents
        SET channels_json = ?, home_channel_json = ?
        WHERE agent_id = ?
        """,
        (json_dumps(channels_value), json_dumps(resolved_home_channel), agent_id),
    )
    conn.commit()

    subscriptions = subscriptions_for_agent(conn, agent_id)
    manifest_path = write_shared_manifest(
        cfg,
        agent_id=agent_id,
        role=str(row["role"]),
        unix_user=str(row["unix_user"]),
        display_name=str(row["display_name"]),
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


SSOT_ALLOWED_OPERATIONS = ("read", "insert", "update")
SSOT_FORBIDDEN_OPERATIONS = ("archive", "delete", "trash", "destroy")


def _notion_owner_identity(payload: dict[str, Any]) -> tuple[str, str]:
    """Return (owner_identity, resolution_source) following the spec precedence:
    explicit Owner property -> created_by -> ('', 'needs-approval').
    """
    properties = payload.get("properties") or {}
    owner_prop = properties.get("Owner") if isinstance(properties, dict) else None
    if isinstance(owner_prop, dict):
        people = owner_prop.get("people") or []
        for person in people:
            if isinstance(person, dict):
                for key in ("name", "email", "id"):
                    value = person.get(key)
                    if value:
                        return str(value), "owner-property"
        raw_value = owner_prop.get("value") or owner_prop.get("text")
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip(), "owner-property"

    created_by = payload.get("created_by") or {}
    if isinstance(created_by, dict):
        for key in ("name", "email", "id"):
            value = created_by.get(key)
            if value:
                return str(value), "created-by"
    if isinstance(created_by, str) and created_by.strip():
        return created_by.strip(), "created-by"

    return "", "needs-approval"


def _find_agent_for_owner(conn: sqlite3.Connection, owner_identity: str) -> dict[str, Any] | None:
    if not owner_identity:
        return None
    row = conn.execute(
        """
        SELECT agent_id, unix_user, display_name
        FROM agents
        WHERE status = 'active'
          AND role = 'user'
          AND (unix_user = ? OR display_name = ?)
        ORDER BY last_enrolled_at DESC
        LIMIT 1
        """,
        (owner_identity, owner_identity),
    ).fetchone()
    return dict(row) if row else None


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
    """Accept insert/update only. Reject archive/delete. Ensure acting agent owns the target.

    Writes are intentionally not performed here — they are queued to refresh_jobs for
    the Curator/SSOT worker to execute with the operator's Notion credentials.
    """
    op = (operation or "").strip().lower()
    if op in SSOT_FORBIDDEN_OPERATIONS:
        raise PermissionError(
            f"SSOT rail violation: operation '{op}' is not permitted; archive/delete require operator."
        )
    if op not in SSOT_ALLOWED_OPERATIONS:
        raise ValueError(
            f"unsupported SSOT operation '{op}'; allowed: {', '.join(SSOT_ALLOWED_OPERATIONS)}"
        )

    owner_identity, owner_source = _notion_owner_identity(payload) if op != "insert" else ("", "insert")
    agent_row = conn.execute(
        "SELECT unix_user, display_name FROM agents WHERE agent_id = ?",
        (agent_id,),
    ).fetchone()
    if agent_row is None:
        raise PermissionError("agent is not active")

    if op == "insert":
        approved = True
    else:
        owner_agent = _find_agent_for_owner(conn, owner_identity)
        approved = owner_agent is not None and owner_agent["agent_id"] == agent_id
        if not approved:
            owner_label = owner_identity or "unknown"
            queue_notification(
                conn,
                target_kind="operator",
                target_id=cfg.operator_notify_channel_id or cfg.operator_notify_platform or "operator",
                channel_kind=cfg.operator_notify_platform or "tui-only",
                message=(
                    f"SSOT write approval requested: agent={agent_id} op={op} target={target_id} "
                    f"owner={owner_label} source={owner_source}"
                ),
            )

    job_name = f"ssot-{op}-{target_id or secrets.token_hex(4)}"
    note_refresh_job(
        conn,
        job_name=job_name,
        job_kind="ssot-write",
        target_id=target_id or agent_id,
        schedule="manual",
        status="queued" if approved else "awaiting-approval",
        note=json_dumps(
            {
                "agent_id": agent_id,
                "operation": op,
                "target_id": target_id,
                "owner_identity": owner_identity,
                "owner_source": owner_source,
                "actor": requested_by_actor,
            }
        ),
    )
    return {
        "queued": approved,
        "agent_id": agent_id,
        "operation": op,
        "target_id": target_id,
        "owner_identity": owner_identity,
        "owner_source": owner_source,
        "approval_required": not approved,
    }


def build_managed_memory_payload(
    conn: sqlite3.Connection,
    cfg: Config,
    *,
    agent_id: str,
) -> dict[str, Any]:
    """Compose the three canonical managed-memory stubs for an agent.

    The skill contract is:
      [managed:vault-ref]      active vault path and role
      [managed:qmd-ref]        how to query qmd for retrieval
      [managed:vault-topology] compact summary of subscribed vaults + briefs
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

    vault_ref = (
        f"Vault root: {vault_root}\n"
        f"Agent: {agent_id} (role={agent['role']}, unix_user={agent['unix_user']})"
    )
    qmd_ref = (
        f"qmd MCP (deep retrieval): {cfg.qmd_url}\n"
        "Always query qmd before web for vault-relevant work, including the\n"
        "'vault-pdf-ingest' collection when present for PDF-derived markdown."
    )
    topology = "Subscribed vaults (+ = subscribed, · = default, - = unsubscribed):\n" + "\n".join(
        topology_lines
    )

    return {
        "agent_id": agent_id,
        "vault-ref": vault_ref,
        "qmd-ref": qmd_ref,
        "vault-topology": topology,
        "catalog": catalog,
        "subscriptions": [dict(s) for s in subs.values()],
    }


def write_managed_memory_stubs(
    *,
    hermes_home: Path,
    payload: dict[str, Any],
) -> dict[str, str]:
    """Idempotently write the three managed-memory stubs into an agent's
    HERMES_HOME. Two artefacts are produced:

    1. `$HERMES_HOME/state/almanac-vault-reconciler.json` — structured state
       the vault-reconciler skill can read for drift detection.
    2. `$HERMES_HOME/memories/almanac-managed-stubs.md` — a markdown overlay the
       agent can include / reference from `MEMORY.md`.

    Returns the two paths written. Called from the user-agent-refresh context
    running as the enrollment user — never from the central curator (which runs
    as a different uid and would violate the HOME boundary).
    """
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
                "vault-ref": payload["vault-ref"],
                "qmd-ref": payload["qmd-ref"],
                "vault-topology": payload["vault-topology"],
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
        f"## [managed:vault-ref]\n\n{payload['vault-ref']}\n\n"
        f"## [managed:qmd-ref]\n\n{payload['qmd-ref']}\n\n"
        f"## [managed:vault-topology]\n\n{payload['vault-topology']}\n\n"
        f"_updated_at: {now}_\n"
    )
    stub_path.write_text(body, encoding="utf-8")

    return {"state_path": str(state_path), "stub_path": str(stub_path)}


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
            published.append({"agent_id": agent_id, "path": str(path)})
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


def _map_event_to_affected_users(conn: sqlite3.Connection, payload: dict[str, Any]) -> list[str]:
    owner_identity, _ = _notion_owner_identity(payload)
    if not owner_identity:
        return []
    agent = _find_agent_for_owner(conn, owner_identity)
    return [agent["agent_id"]] if agent else []


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
        affected = _map_event_to_affected_users(conn, payload)
        signal = _signal_kind(row["event_type"], payload)

        if not affected:
            unresolved_events.append(row["event_id"])

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

    conn.commit()
    note_refresh_job(
        conn,
        job_name="notion-ssot-batcher",
        job_kind="ssot-batcher",
        target_id="notion",
        schedule="every 5m",
        status="ok",
        note=f"processed {processed} event(s); unresolved {len(unresolved_events)}",
    )
    return {
        "processed": processed,
        "event_types": event_types,
        "nudges": {agent: len(v) for agent, v in nudges_by_agent.items()},
        "unresolved_event_ids": unresolved_events,
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
