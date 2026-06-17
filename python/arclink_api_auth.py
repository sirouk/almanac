#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import hashlib
import hmac
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import tempfile
from typing import Any, Mapping

from arclink_control import (
    ARCLINK_CREDENTIAL_HANDOFF_STATUSES,
    ARCLINK_SESSION_STATUSES,
    ARCLINK_SHARE_GRANT_STATUSES,
    arclink_refuel_topup_options,
    append_arclink_audit,
    append_arclink_event,
    config_env_value,
    parse_utc_iso,
    quote_arclink_refuel_topup,
    queue_notification,
    utc_after_seconds_iso,
    utc_now,
    utc_now_iso,
)
from arclink_boundary import json_dumps_safe, json_loads_safe, reject_secret_material, rowdict
from arclink_dashboard import (
    queue_arclink_admin_action,
    read_arclink_admin_dashboard,
    read_arclink_user_dashboard,
    request_arclink_backup_deploy_key,
    request_arclink_backup_write_check,
)
from arclink_onboarding import (
    ARCLINK_ONBOARDING_CANCEL_IMMUTABLE_STATUSES,
    answer_arclink_onboarding_question,
    cancel_arclink_onboarding_session,
    create_or_resume_arclink_onboarding_session,
    normalize_arclink_public_onboarding_contact,
    open_arclink_onboarding_checkout,
)
from arclink_entitlements import ReconciliationDrift, detect_stripe_reconciliation_drift
from arclink_product import chutes_default_model, primary_provider
from arclink_provisioning import update_arclink_deployment_identity
from arclink_chutes import (
    chutes_credential_lifecycle,
    chutes_threshold_continuation_policy,
    evaluate_chutes_deployment_boundary,
    renewal_lifecycle_for_billing_state,
)
from arclink_crew_recipes import (
    apply_crew_recipe,
    crew_academy_status,
    current_crew_recipe,
    preview_crew_recipe,
    prior_crew_recipe,
    whats_changed,
)
from arclink_academy_programs import (
    ArcLinkAcademyProgramError,
    academy_graduate_card,
    academy_mode_status,
    adopt_central_specialist,
    adopt_academy_graduate,
    browse_academy_graduates,
    end_academy_mode,
    enroll_academy_trainee,
    get_academy_trainee,
    get_open_academy_mode,
    list_central_specialists,
    list_academy_trainees,
    open_academy_mode,
    seed_default_academy_programs,
)
from arclink_wrapped import list_user_wrapped_reports, set_wrapped_frequency, wrapped_admin_aggregate


ARCLINK_ADMIN_ROLES = frozenset({"owner", "admin", "ops", "support", "read_only"})
ARCLINK_ADMIN_MUTATION_ROLES = frozenset({"owner", "admin", "ops"})
ARCLINK_CREDENTIAL_HANDOFF_KINDS = frozenset({"dashboard_password", "chutes_api_key", "notion_token"})
ARCLINK_SHARE_RESOURCE_KINDS = frozenset({"drive", "code", "pod_comms", "notion"})
ARCLINK_SHARE_RESOURCE_ROOTS = frozenset({"vault", "workspace"})
ARCLINK_SHARE_NOTION_ROOTS = frozenset({"notion", "ssot"})
ARCLINK_SHARE_ACCESS_MODES = frozenset({"read", "read_write"})
ARCLINK_SHARE_STATUSES = ARCLINK_SHARE_GRANT_STATUSES
ARCLINK_SHARE_BROKER_ACTIVE_DEPLOYMENT_STATUSES = frozenset({"active"})
ARCLINK_CREDENTIAL_HANDOFF_TTL_SECONDS = 7 * 24 * 60 * 60
ARCLINK_SHARE_GRANT_TTL_SECONDS = 7 * 24 * 60 * 60
# Ephemeral, single-use claim nonces hand a scoped read share to whoever the owner
# gives the code to. Twelve hours mirrors the dashboard session TTL the user already sees.
ARCLINK_SHARE_CLAIM_NONCE_TTL_SECONDS = 12 * 60 * 60
ARCLINK_SHARE_CLAIM_NONCE_PREFIX = "asn_"
ARCLINK_LINKED_RESOURCE_MANIFEST = ".arclink-linked-resources.json"
ARCLINK_SESSION_ID_HEADER = "x-arclink-session-id"
ARCLINK_SESSION_TOKEN_HEADER = "x-arclink-session-token"
ARCLINK_CSRF_HEADER = "x-arclink-csrf-token"
ARCLINK_SHARE_REQUEST_BROKER_TOKEN_HEADER = "x-arclink-share-request-broker-token"
GENERIC_ARCLINK_API_ERROR = "Request blocked. Check input and try again."
GENERIC_ARCLINK_AUTH_ERROR = "unauthorized"
ARCLINK_PASSWORD_ALGORITHM = "pbkdf2_sha256"
ARCLINK_PASSWORD_ITERATIONS = 390_000
ARCLINK_ADMIN_PASSWORD_ALGORITHM = ARCLINK_PASSWORD_ALGORITHM
ARCLINK_ADMIN_PASSWORD_ITERATIONS = ARCLINK_PASSWORD_ITERATIONS
ARCLINK_SESSION_HASH_ALGORITHM = "hmac_sha256_v1"
ARCLINK_LEGACY_SESSION_HASH_ALGORITHM = "sha256_legacy"
LOCAL_DEV_DOMAINS = {"localhost", "127.0.0.1", "::1", "example.test"}
ARCLINK_ONBOARDING_CLAIM_REPLAY_SECONDS = 10 * 60


class ArcLinkApiAuthError(ValueError):
    pass


class ArcLinkRateLimitError(ArcLinkApiAuthError):
    """Raised when a rate limit is exceeded, carrying limit metadata."""

    def __init__(self, message: str, *, limit: int, remaining: int, reset_seconds: int) -> None:
        super().__init__(message)
        self.limit = limit
        self.remaining = remaining
        self.reset_seconds = reset_seconds


@dataclass(frozen=True)
class ArcLinkApiResponse:
    status: int
    payload: dict[str, Any]


def _validate_session_kind(session_kind: str, *, operation: str) -> str:
    clean_kind = str(session_kind or "").strip().lower()
    if clean_kind not in {"user", "admin"}:
        raise ArcLinkApiAuthError(f"ArcLink {operation} requires a supported session kind")
    return clean_kind


def _header(headers: Mapping[str, Any], name: str) -> str:
    target = name.lower()
    for key, value in dict(headers or {}).items():
        if str(key or "").lower() == target:
            return str(value or "").strip()
    return ""


def _cookie(headers: Mapping[str, Any], name: str) -> str:
    raw = _header(headers, "cookie")
    if not raw:
        return ""
    parsed = SimpleCookie()
    parsed.load(raw)
    morsel = parsed.get(name)
    return str(morsel.value or "").strip() if morsel is not None else ""


def _bearer_token(headers: Mapping[str, Any]) -> str:
    authorization = _header(headers, "authorization")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return ""
    return token.strip()


def extract_arclink_session_credentials(
    headers: Mapping[str, Any],
    *,
    session_kind: str,
) -> dict[str, str]:
    clean_kind = _validate_session_kind(session_kind, operation="session credential extraction")
    session_id = _header(headers, ARCLINK_SESSION_ID_HEADER) or _cookie(headers, f"arclink_{clean_kind}_session_id")
    session_token = (
        _bearer_token(headers)
        or _header(headers, ARCLINK_SESSION_TOKEN_HEADER)
        or _cookie(headers, f"arclink_{clean_kind}_session_token")
    )
    if not session_id or not session_token:
        raise ArcLinkApiAuthError("ArcLink session id and token are required")
    return {"session_id": session_id, "session_token": session_token}


def extract_arclink_browser_session_credentials(
    headers: Mapping[str, Any],
    *,
    session_kind: str,
) -> dict[str, str]:
    clean_kind = _validate_session_kind(session_kind, operation="browser session credential extraction")
    session_id = _cookie(headers, f"arclink_{clean_kind}_session_id")
    session_token = _cookie(headers, f"arclink_{clean_kind}_session_token")
    if not session_id or not session_token:
        raise ArcLinkApiAuthError("ArcLink browser session cookies are required")
    return {"session_id": session_id, "session_token": session_token}


def extract_arclink_csrf_token(headers: Mapping[str, Any], *, session_kind: str) -> str:
    _validate_session_kind(session_kind, operation="CSRF token extraction")
    csrf_token = _header(headers, ARCLINK_CSRF_HEADER)
    if not csrf_token:
        raise ArcLinkApiAuthError("ArcLink CSRF header is required")
    return csrf_token


def arclink_api_error_response(exc: BaseException, *, request_id: str = "") -> ArcLinkApiResponse:
    payload: dict[str, Any]
    if isinstance(exc, ArcLinkApiAuthError):
        status = 401
        payload = {"error": GENERIC_ARCLINK_AUTH_ERROR}
    elif isinstance(exc, KeyError):
        status = 404
        payload = {"error": "not_found"}
    else:
        status = 400
        payload = {"error": GENERIC_ARCLINK_API_ERROR}
    if request_id:
        payload["request_id"] = str(request_id)
    return ArcLinkApiResponse(status=status, payload=payload)


def _json(value: Mapping[str, Any] | None) -> str:
    return json_dumps_safe(value, label="ArcLink API boundary", error_cls=ArcLinkApiAuthError)


def _json_loads(value: str | None) -> dict[str, Any]:
    return json_loads_safe(value)


def _reject_secret_material(value: Any, *, path: str = "$") -> None:
    reject_secret_material(value, path=path, label="ArcLink API boundary", error_cls=ArcLinkApiAuthError)


def _hash_token(token: str) -> str:
    """Legacy plain SHA-256 hash.  Kept only for back-compat verification."""
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _hash_proof_token(token: str) -> str:
    """HMAC-SHA256 peppered hash for onboarding proof tokens."""
    digest = hmac.new(
        _session_hash_pepper().encode("utf-8"),
        str(token or "").encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{ARCLINK_SESSION_HASH_ALGORITHM}${digest}"


def _verify_proof_token_hash(token: str, stored_hash: str, *, allow_legacy: bool = True) -> bool:
    """Verify a proof token hash, optionally accepting legacy plain SHA-256."""
    stored = str(stored_hash or "").strip()
    if not stored:
        return False
    current = _hash_proof_token(token)
    if stored.startswith(f"{ARCLINK_SESSION_HASH_ALGORITHM}$"):
        return hmac.compare_digest(stored, current)
    if not allow_legacy:
        return False
    legacy = _hash_token(token)
    return hmac.compare_digest(stored, legacy)


def hash_share_request_broker_token(token: str) -> str:
    clean = str(token or "").strip()
    if not clean:
        raise ArcLinkApiAuthError("ArcLink share-request broker token is required")
    return _hash_proof_token(clean)


def _truthy_env(name: str) -> bool:
    return str(config_env_value(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _session_hash_pepper() -> str:
    pepper = str(config_env_value("ARCLINK_SESSION_HASH_PEPPER", "") or "").strip()
    if pepper:
        return pepper
    base_domain = str(config_env_value("ARCLINK_BASE_DOMAIN", "") or "").strip().lower()
    is_local_dev = bool(
        base_domain and (base_domain in LOCAL_DEV_DOMAINS or base_domain.endswith(".test"))
    )
    if _truthy_env("ARCLINK_SESSION_HASH_PEPPER_REQUIRED") or not is_local_dev:
        raise ArcLinkApiAuthError("ArcLink session hash pepper is not configured")
    return "arclink-dev-session-hash-pepper"


def _hash_session_token(token: str) -> str:
    digest = hmac.new(
        _session_hash_pepper().encode("utf-8"),
        str(token or "").encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{ARCLINK_SESSION_HASH_ALGORITHM}${digest}"


def _verify_session_token_hash(token: str, stored_hash: str) -> tuple[bool, str]:
    stored = str(stored_hash or "").strip()
    current = _hash_session_token(token)
    if stored.startswith(f"{ARCLINK_SESSION_HASH_ALGORITHM}$"):
        return hmac.compare_digest(stored, current), ARCLINK_SESSION_HASH_ALGORITHM
    legacy = _hash_token(token)
    return hmac.compare_digest(stored, legacy), ARCLINK_LEGACY_SESSION_HASH_ALGORITHM


def _require_session_id_prefix(session_id: str, *, kind: str) -> str:
    clean_kind = _validate_session_kind(kind, operation="session id prefix validation")
    clean_session = str(session_id or "").strip()
    expected = "asess_" if clean_kind == "admin" else "usess_"
    if not clean_session.startswith(expected):
        raise ArcLinkApiAuthError(f"ArcLink {clean_kind} session id prefix is invalid")
    return clean_session


def _public_onboarding_session(session: Mapping[str, Any]) -> dict[str, Any]:
    """Return browser-safe onboarding session fields.

    Internal metadata carries one-way browser proof hashes and should not be
    reflected back to public clients as part of the session object.
    """
    return {
        key: value
        for key, value in dict(session).items()
        if key not in {"metadata_json"}
    }


def hash_arclink_password(password: str, *, label: str = "ArcLink password") -> str:
    raw = str(password or "")
    if len(raw) < 12:
        raise ArcLinkApiAuthError(f"{label} must be at least 12 characters")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        raw.encode("utf-8"),
        salt.encode("ascii"),
        ARCLINK_PASSWORD_ITERATIONS,
    ).hex()
    return f"{ARCLINK_PASSWORD_ALGORITHM}${ARCLINK_PASSWORD_ITERATIONS}${salt}${digest}"


def verify_arclink_password(password: str, password_hash: str) -> bool:
    stored = str(password_hash or "").strip()
    parts = stored.split("$")
    if len(parts) != 4 or parts[0] != ARCLINK_PASSWORD_ALGORITHM:
        return False
    _algorithm, iterations_raw, salt, digest = parts
    try:
        iterations = int(iterations_raw)
    except ValueError:
        return False
    if iterations < 100_000 or not salt or not digest:
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        str(password or "").encode("utf-8"),
        salt.encode("ascii"),
        iterations,
    ).hex()
    return hmac.compare_digest(candidate, digest)


def hash_arclink_admin_password(password: str) -> str:
    return hash_arclink_password(password, label="ArcLink admin password")


def verify_arclink_admin_password(password: str, password_hash: str) -> bool:
    return verify_arclink_password(password, password_hash)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(16)}"


def _new_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def _require_active_time(row: Mapping[str, Any], *, kind: str) -> None:
    if str(row.get("status") or "") != "active" or str(row.get("revoked_at") or ""):
        raise ArcLinkApiAuthError(f"ArcLink {kind} session authentication failed")
    expires_at = parse_utc_iso(str(row.get("expires_at") or ""))
    if expires_at is None or expires_at <= utc_now():
        raise ArcLinkApiAuthError(f"ArcLink {kind} session authentication failed")


def mask_secret_ref(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if not text.startswith("secret://"):
        return "masked"
    return "secret://masked"


def check_arclink_rate_limit(
    conn: sqlite3.Connection,
    *,
    scope: str,
    subject: str,
    limit: int,
    window_seconds: int,
    commit: bool = True,
) -> dict[str, Any]:
    clean_scope = f"arclink:{str(scope or '').strip().lower()}"
    clean_subject = str(subject or "").strip().lower()
    if clean_scope == "arclink:" or not clean_subject:
        raise ArcLinkApiAuthError("ArcLink rate limit scope and subject are required")
    started_transaction = False
    if commit and not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
        started_transaction = True
    cutoff = (utc_now() - dt.timedelta(seconds=max(1, int(window_seconds or 1)))).replace(microsecond=0).isoformat()
    try:
        count = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM rate_limits
            WHERE scope = ? AND subject = ? AND observed_at >= ?
            """,
            (clean_scope, clean_subject, cutoff),
        ).fetchone()["n"]
        effective_limit = max(1, int(limit or 1))
        current_count = int(count)
        if current_count >= effective_limit:
            if started_transaction:
                conn.rollback()
            raise ArcLinkRateLimitError(
                "ArcLink rate limit exceeded",
                limit=effective_limit,
                remaining=0,
                reset_seconds=max(1, int(window_seconds or 1)),
            )
        conn.execute(
            "INSERT INTO rate_limits (scope, subject, observed_at) VALUES (?, ?, ?)",
            (clean_scope, clean_subject, utc_now_iso()),
        )
        if commit:
            conn.commit()
        return {"scope": clean_scope, "subject": clean_subject, "remaining": max(0, int(limit) - int(count) - 1)}
    except Exception:
        if started_transaction and conn.in_transaction:
            conn.rollback()
        raise


def _login_audit_subject(login_subject: str, clean_email: str) -> str:
    return str(login_subject or clean_email).strip().lower()


def _login_client_ip_subject(client_ip: str) -> str:
    clean = str(client_ip or "").strip().lower()
    if not clean or clean == "unknown":
        return ""
    return clean[:120]


def _check_login_rate_limits(
    conn: sqlite3.Connection,
    *,
    scope: str,
    clean_email: str,
    client_ip: str = "",
    account_limit: int,
    ip_limit: int,
    window_seconds: int = 900,
) -> None:
    """Rate-limit logins by server-derived account and source buckets.

    The optional login_subject field is retained only as audit metadata. It is
    never trusted as the throttle key because callers can change it per guess.
    """
    clean_account = str(clean_email or "").strip().lower()
    if not clean_account:
        raise ArcLinkApiAuthError("ArcLink login requires an email")
    clean_ip = _login_client_ip_subject(client_ip)
    clean_scope_prefix = str(scope or "").strip().lower()
    if not clean_scope_prefix:
        raise ArcLinkApiAuthError("ArcLink login rate limit scope is required")
    bucket_specs: list[tuple[str, str, int]] = [
        (f"arclink:{clean_scope_prefix}:account", clean_account, account_limit),
    ]
    if clean_ip:
        bucket_specs.extend(
            [
                (f"arclink:{clean_scope_prefix}:ip", clean_ip, ip_limit),
                (f"arclink:{clean_scope_prefix}:account_ip", f"{clean_account}|{clean_ip}", account_limit),
            ]
        )
    window = max(1, int(window_seconds or 1))
    cutoff = (utc_now() - dt.timedelta(seconds=window)).replace(microsecond=0).isoformat()
    started_transaction = False
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
        started_transaction = True
    try:
        for bucket_scope, bucket_subject, bucket_limit in bucket_specs:
            effective_limit = max(1, int(bucket_limit or 1))
            count = conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM rate_limits
                WHERE scope = ? AND subject = ? AND observed_at >= ?
                """,
                (bucket_scope, bucket_subject, cutoff),
            ).fetchone()["n"]
            if int(count) >= effective_limit:
                if started_transaction:
                    conn.rollback()
                raise ArcLinkRateLimitError(
                    "ArcLink rate limit exceeded",
                    limit=effective_limit,
                    remaining=0,
                    reset_seconds=window,
                )
        now = utc_now_iso()
        conn.executemany(
            "INSERT INTO rate_limits (scope, subject, observed_at) VALUES (?, ?, ?)",
            [(bucket_scope, bucket_subject, now) for bucket_scope, bucket_subject, _limit in bucket_specs],
        )
        conn.commit()
    except Exception:
        if started_transaction and conn.in_transaction:
            conn.rollback()
        raise


def upsert_arclink_admin(
    conn: sqlite3.Connection,
    *,
    admin_id: str,
    email: str,
    role: str = "owner",
    status: str = "active",
    role_scope: Mapping[str, Any] | None = None,
    password: str = "",
    password_hash: str = "",
    commit: bool = True,
) -> dict[str, Any]:
    clean_admin = str(admin_id or "").strip()
    clean_email = str(email or "").strip().lower()
    clean_role = str(role or "").strip().lower()
    if not clean_admin or not clean_email:
        raise ArcLinkApiAuthError("ArcLink admin id and email are required")
    if clean_role not in ARCLINK_ADMIN_ROLES:
        raise ArcLinkApiAuthError(f"unsupported ArcLink admin role: {clean_role or 'blank'}")
    clean_status = str(status or "").strip().lower() or "active"
    if clean_role == "owner" and clean_status == "active":
        existing_owner = conn.execute(
            """
            SELECT admin_id
            FROM arclink_admins
            WHERE role = 'owner'
              AND status = 'active'
              AND admin_id != ?
            ORDER BY created_at ASC, admin_id ASC
            LIMIT 1
            """,
            (clean_admin,),
        ).fetchone()
        if existing_owner is not None:
            raise ArcLinkApiAuthError("ArcLink single-operator policy allows only one active owner")
    clean_password_hash = str(password_hash or "").strip()
    if password:
        clean_password_hash = hash_arclink_admin_password(password)
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO arclink_admins (
          admin_id, email, role, status, password_hash, role_scope_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(admin_id) DO UPDATE SET
          email = excluded.email,
          role = excluded.role,
          status = excluded.status,
          password_hash = CASE
            WHEN excluded.password_hash != '' THEN excluded.password_hash
            ELSE arclink_admins.password_hash
          END,
          role_scope_json = excluded.role_scope_json,
          updated_at = excluded.updated_at
        """,
        (clean_admin, clean_email, clean_role, clean_status, clean_password_hash, _json(role_scope), now, now),
    )
    grant_arclink_admin_role(
        conn,
        admin_id=clean_admin,
        role=clean_role,
        granted_by="system",
        reason="primary admin role",
        commit=False,
    )
    if commit:
        conn.commit()
    return rowdict(conn.execute("SELECT * FROM arclink_admins WHERE admin_id = ?", (clean_admin,)).fetchone())


def set_arclink_admin_password(
    conn: sqlite3.Connection,
    *,
    email: str = "",
    admin_id: str = "",
    password: str,
    commit: bool = True,
) -> dict[str, Any]:
    clean_email = str(email or "").strip().lower()
    clean_admin = str(admin_id or "").strip()
    if not clean_email and not clean_admin:
        raise ArcLinkApiAuthError("ArcLink admin password update requires an email or admin id")
    if clean_admin:
        row = conn.execute("SELECT admin_id FROM arclink_admins WHERE admin_id = ?", (clean_admin,)).fetchone()
    else:
        row = conn.execute("SELECT admin_id FROM arclink_admins WHERE LOWER(email) = LOWER(?)", (clean_email,)).fetchone()
    if row is None:
        raise KeyError(clean_admin or clean_email)
    password_hash = hash_arclink_admin_password(password)
    target_admin = str(row["admin_id"] or "")
    conn.execute(
        "UPDATE arclink_admins SET password_hash = ?, updated_at = ? WHERE admin_id = ?",
        (password_hash, utc_now_iso(), target_admin),
    )
    if commit:
        conn.commit()
    return sanitized_arclink_admin(conn, admin_id=target_admin)


def set_arclink_user_password(
    conn: sqlite3.Connection,
    *,
    user_id: str = "",
    email: str = "",
    password: str = "",
    password_hash: str = "",
    commit: bool = True,
) -> dict[str, Any]:
    clean_user = str(user_id or "").strip()
    clean_email = str(email or "").strip().lower()
    if clean_user:
        row = conn.execute("SELECT user_id FROM arclink_users WHERE user_id = ?", (clean_user,)).fetchone()
    elif clean_email:
        row = conn.execute("SELECT user_id FROM arclink_users WHERE LOWER(email) = LOWER(?)", (clean_email,)).fetchone()
    else:
        raise ArcLinkApiAuthError("ArcLink user password update requires a user id or email")
    if row is None:
        raise KeyError(clean_user or clean_email)
    target_user = str(row["user_id"] or "")
    clean_password_hash = str(password_hash or "").strip()
    if password:
        clean_password_hash = hash_arclink_password(password, label="ArcLink user password")
    if not clean_password_hash:
        raise ArcLinkApiAuthError("ArcLink user password update requires password material")
    conn.execute(
        "UPDATE arclink_users SET password_hash = ?, updated_at = ? WHERE user_id = ?",
        (clean_password_hash, utc_now_iso(), target_user),
    )
    if commit:
        conn.commit()
    row = conn.execute(
        "SELECT user_id, email, password_hash, updated_at FROM arclink_users WHERE user_id = ?",
        (target_user,),
    ).fetchone()
    user = rowdict(row)
    return {
        "user_id": str(user.get("user_id") or ""),
        "email": str(user.get("email") or ""),
        "password": {
            "configured": bool(str(user.get("password_hash") or "").strip()),
            "updated_at": str(user.get("updated_at") or ""),
        },
    }


def grant_arclink_admin_role(
    conn: sqlite3.Connection,
    *,
    admin_id: str,
    role: str,
    granted_by: str,
    reason: str,
    commit: bool = True,
) -> dict[str, Any]:
    clean_admin = str(admin_id or "").strip()
    clean_role = str(role or "").strip().lower()
    if not clean_admin or clean_role not in ARCLINK_ADMIN_ROLES:
        raise ArcLinkApiAuthError("ArcLink admin role grant requires a supported role")
    conn.execute(
        """
        INSERT INTO arclink_admin_roles (admin_id, role, granted_by, reason, created_at, revoked_at)
        VALUES (?, ?, ?, ?, ?, '')
        ON CONFLICT(admin_id, role) DO UPDATE SET
          granted_by = excluded.granted_by,
          reason = excluded.reason,
          revoked_at = '',
          created_at = excluded.created_at
        """,
        (clean_admin, clean_role, str(granted_by or "").strip(), str(reason or "").strip(), utc_now_iso()),
    )
    if commit:
        conn.commit()
    return rowdict(
        conn.execute("SELECT * FROM arclink_admin_roles WHERE admin_id = ? AND role = ?", (clean_admin, clean_role)).fetchone()
    )


def enroll_arclink_admin_totp_factor(
    conn: sqlite3.Connection,
    *,
    admin_id: str,
    secret_ref: str,
    factor_id: str = "",
    commit: bool = True,
) -> dict[str, Any]:
    clean_admin = str(admin_id or "").strip()
    clean_ref = str(secret_ref or "").strip()
    if not clean_admin:
        raise ArcLinkApiAuthError("ArcLink TOTP enrollment requires an admin id")
    _reject_secret_material({"totp_secret_ref": clean_ref})
    if not clean_ref.startswith("secret://"):
        raise ArcLinkApiAuthError("ArcLink TOTP secret must be stored by reference")
    row = conn.execute("SELECT admin_id FROM arclink_admins WHERE admin_id = ?", (clean_admin,)).fetchone()
    if row is None:
        raise KeyError(clean_admin)
    clean_factor = str(factor_id or "").strip() or _new_id("totp")
    conn.execute(
        """
        INSERT INTO arclink_admin_totp_factors (factor_id, admin_id, status, secret_ref, enrolled_at)
        VALUES (?, ?, 'pending', ?, ?)
        """,
        (clean_factor, clean_admin, clean_ref, utc_now_iso()),
    )
    conn.execute(
        "UPDATE arclink_admins SET totp_secret_ref = ?, updated_at = ? WHERE admin_id = ?",
        (clean_ref, utc_now_iso(), clean_admin),
    )
    if commit:
        conn.commit()
    return sanitized_arclink_admin(conn, admin_id=clean_admin)


def verify_arclink_admin_totp_factor(
    conn: sqlite3.Connection,
    *,
    factor_id: str,
    commit: bool = True,
) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM arclink_admin_totp_factors WHERE factor_id = ?", (factor_id,)).fetchone()
    if row is None:
        raise KeyError(factor_id)
    now = utc_now_iso()
    conn.execute(
        "UPDATE arclink_admin_totp_factors SET status = 'verified', verified_at = ? WHERE factor_id = ?",
        (now, factor_id),
    )
    conn.execute(
        """
        UPDATE arclink_admins
        SET totp_enabled = 1, totp_verified_at = ?, updated_at = ?
        WHERE admin_id = ?
        """,
        (now, now, str(row["admin_id"] or "")),
    )
    if commit:
        conn.commit()
    return sanitized_arclink_admin(conn, admin_id=str(row["admin_id"] or ""))


def sanitized_arclink_admin(conn: sqlite3.Connection, *, admin_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM arclink_admins WHERE admin_id = ?", (admin_id,)).fetchone()
    if row is None:
        raise KeyError(admin_id)
    admin = dict(row)
    return {
        "admin_id": str(admin["admin_id"] or ""),
        "email": str(admin["email"] or ""),
        "role": str(admin["role"] or ""),
        "status": str(admin["status"] or ""),
        "role_scope": _json_loads(str(admin.get("role_scope_json") or "{}")),
        "totp": {
            "enabled": bool(admin.get("totp_enabled")),
            "secret_ref": mask_secret_ref(str(admin.get("totp_secret_ref") or "")),
            "verified_at": str(admin.get("totp_verified_at") or ""),
        },
        "password": {
            "configured": bool(str(admin.get("password_hash") or "").strip()),
        },
    }


def create_arclink_user_session(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    ttl_seconds: int = 86400,
    metadata: Mapping[str, Any] | None = None,
    session_id: str = "",
) -> dict[str, Any]:
    row = conn.execute("SELECT user_id FROM arclink_users WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        raise KeyError(user_id)
    token = _new_token("aus")
    csrf = _new_token("csrf")
    clean_session = str(session_id or "").strip() or _new_id("usess")
    clean_session = _require_session_id_prefix(clean_session, kind="user")
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO arclink_user_sessions (
          session_id, user_id, session_token_hash, csrf_token_hash, status,
          metadata_json, created_at, last_seen_at, expires_at
        ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)
        """,
        (clean_session, user_id, _hash_session_token(token), _hash_session_token(csrf), _json(metadata), now, now, utc_after_seconds_iso(ttl_seconds)),
    )
    conn.commit()
    record = rowdict(conn.execute("SELECT * FROM arclink_user_sessions WHERE session_id = ?", (clean_session,)).fetchone())
    return {**_public_session(record), "session_token": token, "csrf_token": csrf}


def create_arclink_admin_session(
    conn: sqlite3.Connection,
    *,
    admin_id: str,
    ttl_seconds: int = 3600,
    mfa_verified: bool = False,
    metadata: Mapping[str, Any] | None = None,
    session_id: str = "",
) -> dict[str, Any]:
    admin = conn.execute("SELECT * FROM arclink_admins WHERE admin_id = ?", (admin_id,)).fetchone()
    if admin is None:
        raise KeyError(admin_id)
    if str(admin["status"] or "") != "active":
        raise ArcLinkApiAuthError("ArcLink admin is not active")
    token = _new_token("aas")
    csrf = _new_token("csrf")
    clean_session = str(session_id or "").strip() or _new_id("asess")
    clean_session = _require_session_id_prefix(clean_session, kind="admin")
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO arclink_admin_sessions (
          session_id, admin_id, role, session_token_hash, csrf_token_hash, status,
          mfa_verified_at, metadata_json, created_at, last_seen_at, expires_at
        ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)
        """,
        (
            clean_session,
            admin_id,
            str(admin["role"] or ""),
            _hash_session_token(token),
            _hash_session_token(csrf),
            now if mfa_verified else "",
            _json(metadata),
            now,
            now,
            utc_after_seconds_iso(ttl_seconds),
        ),
    )
    conn.commit()
    record = rowdict(conn.execute("SELECT * FROM arclink_admin_sessions WHERE session_id = ?", (clean_session,)).fetchone())
    return {**_public_session(record), "session_token": token, "csrf_token": csrf}


def create_arclink_admin_login_session_api(
    conn: sqlite3.Connection,
    *,
    email: str,
    password: str,
    login_subject: str,
    client_ip: str = "",
    mfa_verified: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> ArcLinkApiResponse:
    clean_email = str(email or "").strip().lower()
    clean_subject = _login_audit_subject(login_subject, clean_email)
    if not clean_email:
        raise ArcLinkApiAuthError("ArcLink admin login requires an email")
    _check_login_rate_limits(
        conn,
        scope="admin_login",
        clean_email=clean_email,
        client_ip=client_ip,
        account_limit=5,
        ip_limit=30,
    )
    row = conn.execute(
        "SELECT admin_id, password_hash FROM arclink_admins WHERE LOWER(email) = LOWER(?) AND status = 'active'",
        (clean_email,),
    ).fetchone()
    if row is None:
        raise ArcLinkApiAuthError("Invalid ArcLink admin credentials")
    if not str(row["password_hash"] or "").strip():
        raise ArcLinkApiAuthError("Invalid ArcLink admin credentials")
    if not verify_arclink_admin_password(str(password or ""), str(row["password_hash"] or "")):
        raise ArcLinkApiAuthError("Invalid ArcLink admin credentials")
    session = create_arclink_admin_session(
        conn,
        admin_id=str(row["admin_id"] or ""),
        mfa_verified=mfa_verified,
        metadata={"login_subject": clean_subject, "login_client_ip": _login_client_ip_subject(client_ip), **dict(metadata or {})},
    )
    return ArcLinkApiResponse(status=201, payload={"session": session})


def create_arclink_login_session_api(
    conn: sqlite3.Connection,
    *,
    email: str,
    password: str,
    login_subject: str = "",
    client_ip: str = "",
    metadata: Mapping[str, Any] | None = None,
    allow_admin: bool = True,
) -> ArcLinkApiResponse:
    clean_email = str(email or "").strip().lower()
    clean_subject = _login_audit_subject(login_subject, clean_email)
    if not clean_email:
        raise ArcLinkApiAuthError("ArcLink login requires an email")
    _check_login_rate_limits(
        conn,
        scope="login",
        clean_email=clean_email,
        client_ip=client_ip,
        account_limit=10,
        ip_limit=50,
    )

    if allow_admin:
        admin = conn.execute(
            "SELECT admin_id, role, password_hash FROM arclink_admins WHERE LOWER(email) = LOWER(?) AND status = 'active'",
            (clean_email,),
        ).fetchone()
        if (
            admin is not None
            and str(admin["password_hash"] or "").strip()
            and verify_arclink_admin_password(str(password or ""), str(admin["password_hash"] or ""))
        ):
            session = create_arclink_admin_session(
                conn,
                admin_id=str(admin["admin_id"] or ""),
                mfa_verified=False,
                metadata={"login_subject": clean_subject, "login_client_ip": _login_client_ip_subject(client_ip), **dict(metadata or {})},
            )
            return ArcLinkApiResponse(
                status=201,
                payload={"session": session, "session_kind": "admin", "role": str(admin["role"] or "")},
            )

    user = conn.execute(
        "SELECT user_id, password_hash FROM arclink_users WHERE LOWER(email) = LOWER(?) AND status = 'active'",
        (clean_email,),
    ).fetchone()
    if (
        user is not None
        and str(user["password_hash"] or "").strip()
        and verify_arclink_password(str(password or ""), str(user["password_hash"] or ""))
    ):
        session = create_arclink_user_session(
            conn,
            user_id=str(user["user_id"] or ""),
            metadata={"login_subject": clean_subject, "login_client_ip": _login_client_ip_subject(client_ip), **dict(metadata or {})},
        )
        return ArcLinkApiResponse(
            status=201,
            payload={"session": session, "session_kind": "user", "role": "user"},
        )

    raise ArcLinkApiAuthError("Invalid ArcLink credentials")


def create_arclink_user_login_session_api(
    conn: sqlite3.Connection,
    *,
    email: str,
    password: str,
    login_subject: str = "",
    client_ip: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> ArcLinkApiResponse:
    clean_email = str(email or "").strip().lower()
    clean_subject = _login_audit_subject(login_subject, clean_email)
    if not clean_email:
        raise ArcLinkApiAuthError("ArcLink user login requires an email")
    _check_login_rate_limits(
        conn,
        scope="user_login",
        clean_email=clean_email,
        client_ip=client_ip,
        account_limit=10,
        ip_limit=50,
    )
    row = conn.execute(
        "SELECT user_id, password_hash FROM arclink_users WHERE LOWER(email) = LOWER(?) AND status = 'active'",
        (clean_email,),
    ).fetchone()
    if row is None:
        raise ArcLinkApiAuthError("Invalid ArcLink user credentials")
    if not str(row["password_hash"] or "").strip():
        raise ArcLinkApiAuthError("Invalid ArcLink user credentials")
    if not verify_arclink_password(str(password or ""), str(row["password_hash"] or "")):
        raise ArcLinkApiAuthError("Invalid ArcLink user credentials")
    session = create_arclink_user_session(
        conn,
        user_id=str(row["user_id"] or ""),
        metadata={"login_subject": clean_subject, "login_client_ip": _login_client_ip_subject(client_ip), **dict(metadata or {})},
    )
    return ArcLinkApiResponse(status=201, payload={"session": session})


def _public_session(row: Mapping[str, Any]) -> dict[str, Any]:
    public = {
        key: value
        for key, value in dict(row).items()
        if key not in {"session_token_hash", "csrf_token_hash", "metadata_json"}
    }
    public["metadata"] = _json_loads(str(row.get("metadata_json") or "{}"))
    return public


def _authenticate_session(
    conn: sqlite3.Connection, *, session_id: str, session_token: str, kind: str,
) -> dict[str, Any]:
    clean_kind = _validate_session_kind(kind, operation="session authentication")
    table = "arclink_admin_sessions" if clean_kind == "admin" else "arclink_user_sessions"
    clean_session = _require_session_id_prefix(session_id, kind=clean_kind)
    row = conn.execute(f"SELECT * FROM {table} WHERE session_id = ?", (clean_session,)).fetchone()
    if row is None:
        raise ArcLinkApiAuthError(f"ArcLink {clean_kind} session authentication failed")
    record = dict(row)
    _require_active_time(record, kind=clean_kind)
    verified, algorithm = _verify_session_token_hash(session_token, str(record["session_token_hash"] or ""))
    if not verified:
        raise ArcLinkApiAuthError(f"ArcLink {clean_kind} session authentication failed")
    if algorithm == ARCLINK_LEGACY_SESSION_HASH_ALGORITHM:
        conn.execute(
            f"UPDATE {table} SET session_token_hash = ?, last_seen_at = ? WHERE session_id = ?",
            (_hash_session_token(session_token), utc_now_iso(), clean_session),
        )
    else:
        conn.execute(f"UPDATE {table} SET last_seen_at = ? WHERE session_id = ?", (utc_now_iso(), clean_session))
    conn.commit()
    return _public_session(record)


def authenticate_arclink_user_session(conn: sqlite3.Connection, *, session_id: str, session_token: str) -> dict[str, Any]:
    return _authenticate_session(conn, session_id=session_id, session_token=session_token, kind="user")


def authenticate_arclink_admin_session(conn: sqlite3.Connection, *, session_id: str, session_token: str) -> dict[str, Any]:
    return _authenticate_session(conn, session_id=session_id, session_token=session_token, kind="admin")


def require_arclink_csrf(conn: sqlite3.Connection, *, session_id: str, csrf_token: str, session_kind: str) -> bool:
    clean_kind = _validate_session_kind(session_kind, operation="CSRF check")
    table = "arclink_admin_sessions" if clean_kind == "admin" else "arclink_user_sessions"
    clean_session = _require_session_id_prefix(session_id, kind=clean_kind)
    row = conn.execute(f"SELECT csrf_token_hash FROM {table} WHERE session_id = ?", (clean_session,)).fetchone()
    if row is None:
        raise ArcLinkApiAuthError("ArcLink CSRF check failed")
    verified, algorithm = _verify_session_token_hash(csrf_token, str(row["csrf_token_hash"] or ""))
    if not verified:
        raise ArcLinkApiAuthError("ArcLink CSRF check failed")
    if algorithm == ARCLINK_LEGACY_SESSION_HASH_ALGORITHM:
        conn.execute(
            f"UPDATE {table} SET csrf_token_hash = ? WHERE session_id = ?",
            (_hash_session_token(csrf_token), clean_session),
        )
        conn.commit()
    return True


def _admin_mutation_allowed(conn: sqlite3.Connection, session: Mapping[str, Any]) -> None:
    admin = conn.execute("SELECT role, totp_enabled FROM arclink_admins WHERE admin_id = ?", (str(session.get("admin_id") or ""),)).fetchone()
    if admin is None:
        raise ArcLinkApiAuthError("ArcLink admin session principal is missing")
    role = str(admin["role"] or session.get("role") or "").strip().lower()
    if role not in ARCLINK_ADMIN_MUTATION_ROLES:
        raise ArcLinkApiAuthError("ArcLink admin mutation requires an elevated role")
    if bool(admin["totp_enabled"]) and not str(session.get("mfa_verified_at") or ""):
        raise ArcLinkApiAuthError("ArcLink admin mutation requires MFA verification")


def start_public_onboarding_api(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    email_hint: str = "",
    display_name_hint: str = "",
    selected_plan_id: str = "founders",
    selected_model_id: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> ArcLinkApiResponse:
    contact = normalize_arclink_public_onboarding_contact(channel=channel, channel_identity=channel_identity)
    clean_channel = contact["channel"]
    clean_identity = contact["channel_identity"]
    check_arclink_rate_limit(conn, scope=f"onboarding:{clean_channel}", subject=clean_identity, limit=5, window_seconds=900)
    session = create_or_resume_arclink_onboarding_session(
        conn,
        channel=clean_channel,
        channel_identity=clean_identity,
        email_hint=email_hint,
        display_name_hint=display_name_hint,
        selected_plan_id=selected_plan_id,
        selected_model_id=selected_model_id or chutes_default_model({}),
        metadata=metadata,
    )
    claim_token = secrets.token_urlsafe(32)
    cancel_token = secrets.token_urlsafe(32)
    session_metadata = _json_loads(str(session.get("metadata_json") or "{}"))
    session_metadata.update({
        "browser_claim_proof_hash": _hash_proof_token(claim_token),
        "browser_cancel_proof_hash": _hash_proof_token(cancel_token),
        "browser_proofs_issued_at": utc_now_iso(),
        "browser_proofs_channel": clean_channel,
    })
    conn.execute(
        "UPDATE arclink_onboarding_sessions SET metadata_json = ?, updated_at = ? WHERE session_id = ?",
        (_json(session_metadata), utc_now_iso(), str(session["session_id"])),
    )
    conn.commit()
    refreshed = conn.execute(
        "SELECT * FROM arclink_onboarding_sessions WHERE session_id = ?",
        (str(session["session_id"]),),
    ).fetchone()
    return ArcLinkApiResponse(status=201, payload={
        "session": _public_onboarding_session(rowdict(refreshed) if refreshed is not None else session),
        "browser_claim_token": claim_token,
        "browser_cancel_token": cancel_token,
    })


def _require_nonempty(value: str, field: str) -> None:
    """Raise ArcLinkApiAuthError if *value* is blank or missing."""
    if not str(value or "").strip():
        raise ArcLinkApiAuthError(f"{field} is required")


def answer_public_onboarding_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    question_key: str,
    answer_summary: str = "",
    email_hint: str = "",
    display_name_hint: str = "",
    agent_name: str = "",
    agent_title: str = "",
    selected_plan_id: str = "",
    selected_model_id: str = "",
) -> ArcLinkApiResponse:
    _require_nonempty(session_id, "session_id")
    _require_nonempty(question_key, "question_key")
    session = answer_arclink_onboarding_question(
        conn,
        session_id=session_id,
        question_key=question_key,
        answer_summary=answer_summary,
        email_hint=email_hint,
        display_name_hint=display_name_hint,
        agent_name=agent_name,
        agent_title=agent_title,
        selected_plan_id=selected_plan_id,
        selected_model_id=selected_model_id,
    )
    return ArcLinkApiResponse(status=200, payload={"session": _public_onboarding_session(session)})


def open_public_onboarding_checkout_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    stripe_client: Any,
    price_id: str,
    success_url: str,
    cancel_url: str,
    base_domain: str = "",
    line_items: list[dict[str, Any]] | None = None,
) -> ArcLinkApiResponse:
    _require_nonempty(session_id, "session_id")
    _require_nonempty(price_id, "price_id")
    session = open_arclink_onboarding_checkout(
        conn,
        session_id=session_id,
        stripe_client=stripe_client,
        price_id=price_id,
        success_url=success_url,
        cancel_url=cancel_url,
        base_domain=base_domain,
        line_items=line_items,
    )
    return ArcLinkApiResponse(status=200, payload={"session": _public_onboarding_session(session)})


def read_user_dashboard_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    user_id: str = "",
) -> ArcLinkApiResponse:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    target_user = str(user_id or session["user_id"] or "").strip()
    if target_user != str(session["user_id"] or ""):
        raise ArcLinkApiAuthError("ArcLink user session cannot read another user")
    return ArcLinkApiResponse(status=200, payload=read_arclink_user_dashboard(conn, user_id=target_user))


def read_user_wrapped_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    limit: int = 20,
) -> ArcLinkApiResponse:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    target_user = str(session["user_id"] or "").strip()
    return ArcLinkApiResponse(status=200, payload=list_user_wrapped_reports(conn, target_user, limit=limit))


def update_user_wrapped_frequency_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
    frequency: str,
) -> ArcLinkApiResponse:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    require_arclink_csrf(conn, session_id=session_id, csrf_token=csrf_token, session_kind="user")
    updated = set_wrapped_frequency(
        conn,
        str(session["user_id"] or ""),
        frequency,
        actor_id=str(session["user_id"] or ""),
        reason="Captain updated ArcLink Wrapped cadence",
    )
    return ArcLinkApiResponse(
        status=200,
        payload={"wrapped_frequency": str(updated.get("wrapped_frequency") or "daily")},
    )


def user_update_agent_identity_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
    deployment_id: str,
    agent_name: str = "",
    agent_title: str = "",
) -> ArcLinkApiResponse:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    require_arclink_csrf(conn, session_id=session_id, csrf_token=csrf_token, session_kind="user")
    target_user = str(session["user_id"] or "").strip()
    clean_deployment = str(deployment_id or "").strip()
    row = conn.execute(
        "SELECT * FROM arclink_deployments WHERE deployment_id = ?",
        (clean_deployment,),
    ).fetchone()
    if row is None or str(row["user_id"] or "") != target_user:
        raise ArcLinkApiAuthError("ArcLink user session cannot update another user's Agent")
    result = update_arclink_deployment_identity(
        conn,
        deployment=row,
        agent_name=agent_name if str(agent_name or "").strip() else str(row["agent_name"] or ""),
        agent_title=agent_title if str(agent_title or "").strip() else str(row["agent_title"] or ""),
        actor_id=target_user,
        reason="user updated Agent identity",
        projection_source="user_dashboard_agent_identity_update",
    )
    updated = result["deployment"]
    return ArcLinkApiResponse(
        status=200,
        payload={
            "deployment": {
                "deployment_id": str(updated.get("deployment_id") or ""),
                "agent_name": str(updated.get("agent_name") or ""),
                "agent_title": str(updated.get("agent_title") or ""),
            },
            "identity_projection": result["identity_projection"],
        },
    )


def request_user_backup_deploy_key_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
    deployment_id: str,
    key_staging_dir: str,
) -> ArcLinkApiResponse:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    require_arclink_csrf(conn, session_id=session_id, csrf_token=csrf_token, session_kind="user")
    target_user = str(session["user_id"] or "").strip()
    clean_deployment = str(deployment_id or "").strip()
    if not clean_deployment:
        raise ArcLinkApiAuthError("ArcLink backup deploy-key staging requires a deployment")
    row = conn.execute(
        "SELECT user_id FROM arclink_deployments WHERE deployment_id = ?",
        (clean_deployment,),
    ).fetchone()
    if row is None or str(row["user_id"] or "") != target_user:
        raise ArcLinkApiAuthError("ArcLink user session cannot stage another user's backup deploy key")
    backup_setup = request_arclink_backup_deploy_key(
        conn,
        user_id=target_user,
        deployment_id=clean_deployment,
        key_staging_dir=key_staging_dir,
    )
    return ArcLinkApiResponse(status=200, payload={"backup_setup": backup_setup})


def request_user_backup_write_check_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
    deployment_id: str,
) -> ArcLinkApiResponse:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    require_arclink_csrf(conn, session_id=session_id, csrf_token=csrf_token, session_kind="user")
    target_user = str(session["user_id"] or "").strip()
    clean_deployment = str(deployment_id or "").strip()
    if not clean_deployment:
        raise ArcLinkApiAuthError("ArcLink backup write check requires a deployment")
    row = conn.execute(
        "SELECT user_id FROM arclink_deployments WHERE deployment_id = ?",
        (clean_deployment,),
    ).fetchone()
    if row is None or str(row["user_id"] or "") != target_user:
        raise ArcLinkApiAuthError("ArcLink user session cannot verify another user's backup")
    backup_setup = request_arclink_backup_write_check(
        conn,
        user_id=target_user,
        deployment_id=clean_deployment,
    )
    return ArcLinkApiResponse(status=200, payload={"backup_setup": backup_setup})


def _authenticated_user_id(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
) -> str:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    return str(session["user_id"] or "").strip()


def _csrf_user_id(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
) -> str:
    user_id = _authenticated_user_id(conn, session_id=session_id, session_token=session_token)
    require_arclink_csrf(conn, session_id=session_id, csrf_token=csrf_token, session_kind="user")
    return user_id


def _crew_recipe_args(
    *,
    role: str,
    mission: str,
    treatment: str,
    preset: str,
    capacity: str,
) -> dict[str, str]:
    return {
        "role": role,
        "mission": mission,
        "treatment": treatment,
        "preset": preset,
        "capacity": capacity,
    }


def read_user_crew_recipe_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
) -> ArcLinkApiResponse:
    user_id = _authenticated_user_id(conn, session_id=session_id, session_token=session_token)
    return ArcLinkApiResponse(
        status=200,
        payload={
            "current": current_crew_recipe(conn, user_id=user_id),
            "prior": prior_crew_recipe(conn, user_id=user_id),
            "whats_changed": whats_changed(conn, user_id=user_id),
            "academy_training": crew_academy_status(conn, user_id=user_id),
        },
    )


def preview_user_crew_recipe_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
    role: str,
    mission: str,
    treatment: str,
    preset: str,
    capacity: str,
) -> ArcLinkApiResponse:
    user_id = _csrf_user_id(conn, session_id=session_id, session_token=session_token, csrf_token=csrf_token)
    preview = preview_crew_recipe(
        conn,
        user_id=user_id,
        **_crew_recipe_args(role=role, mission=mission, treatment=treatment, preset=preset, capacity=capacity),
    )
    return ArcLinkApiResponse(status=200, payload={"preview": preview})


def apply_user_crew_recipe_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
    role: str,
    mission: str,
    treatment: str,
    preset: str,
    capacity: str,
) -> ArcLinkApiResponse:
    user_id = _csrf_user_id(conn, session_id=session_id, session_token=session_token, csrf_token=csrf_token)
    result = apply_crew_recipe(
        conn,
        user_id=user_id,
        **_crew_recipe_args(role=role, mission=mission, treatment=treatment, preset=preset, capacity=capacity),
        actor_id=user_id,
    )
    return ArcLinkApiResponse(status=200, payload=result)


def _primary_deployment_id(conn: sqlite3.Connection, user_id: str) -> str:
    """Best-effort resolve the user's ArcPod deployment for Academy enrollment.

    Returns the most recently created active deployment, falling back to any
    deployment, then to an empty string (apply remains proof-gated regardless).
    """
    row = conn.execute(
        """
        SELECT deployment_id FROM arclink_deployments
        WHERE user_id = ?
        ORDER BY CASE WHEN status = 'active' THEN 0 ELSE 1 END, created_at DESC
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    return str(row["deployment_id"] or "").strip() if row is not None else ""


def _require_owned_trainee(conn: sqlite3.Connection, trainee_id: str, user_id: str) -> dict[str, Any]:
    trainee = get_academy_trainee(conn, trainee_id)
    if trainee is None or str(trainee.get("user_id") or "") != user_id:
        raise ArcLinkAcademyProgramError("academy trainee not found for this account")
    return trainee


def read_user_academy_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
) -> ArcLinkApiResponse:
    """Owner-scoped Academy overview: Majors catalog, my Trainees, my graduate gallery.

    The graduate gallery is scoped to the caller's own graduates AND emitted
    through a redacted card projection, so no other tenant's identity
    (user_id/deployment_id/agent_id) or private Captain steer is ever disclosed.
    A cross-tenant "community" gallery would be a separate, consented + redacted
    feature; the default is owner-private.
    """
    user_id = _authenticated_user_id(conn, session_id=session_id, session_token=session_token)
    seed_default_academy_programs(conn)
    gallery = browse_academy_graduates(conn, user_id=user_id)
    return ArcLinkApiResponse(
        status=200,
        payload={
            "majors": gallery.get("programs", []),
            "graduates": [academy_graduate_card(g) for g in gallery.get("graduates", [])],
            "trainees": list_academy_trainees(conn, user_id=user_id),
            "central_specialists": list_central_specialists(conn),
        },
    )


def enroll_user_academy_trainee_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
    program_id: str,
    name: str = "",
    depth: str = "",
) -> ArcLinkApiResponse:
    user_id = _csrf_user_id(conn, session_id=session_id, session_token=session_token, csrf_token=csrf_token)
    deployment_id = _primary_deployment_id(conn, user_id)
    if not deployment_id:
        return ArcLinkApiResponse(
            status=400,
            payload={"error": "no_arcpod", "detail": "Deploy an ArcPod before enrolling an Academy Trainee."},
        )
    seed_default_academy_programs(conn)
    trainee = enroll_academy_trainee(
        conn,
        program_id=str(program_id or "").strip(),
        user_id=user_id,
        deployment_id=deployment_id,
        name=str(name or "").strip(),
        depth=str(depth or "").strip() or None,
    )
    return ArcLinkApiResponse(status=200, payload={"trainee": trainee})


def open_user_academy_mode_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
    trainee_id: str,
    opened_via: str = "dashboard",
) -> ArcLinkApiResponse:
    user_id = _csrf_user_id(conn, session_id=session_id, session_token=session_token, csrf_token=csrf_token)
    _require_owned_trainee(conn, str(trainee_id or "").strip(), user_id)
    session = open_academy_mode(
        conn,
        trainee_id=str(trainee_id or "").strip(),
        opened_by=user_id,
        opened_via=str(opened_via or "").strip() or "dashboard",
    )
    return ArcLinkApiResponse(status=200, payload=session)


def read_user_academy_mode_status_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    trainee_id: str,
) -> ArcLinkApiResponse:
    user_id = _authenticated_user_id(conn, session_id=session_id, session_token=session_token)
    _require_owned_trainee(conn, str(trainee_id or "").strip(), user_id)
    return ArcLinkApiResponse(
        status=200,
        payload=academy_mode_status(conn, trainee_id=str(trainee_id or "").strip()),
    )


def end_user_academy_mode_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
    trainee_id: str,
    graduate: bool = True,
) -> ArcLinkApiResponse:
    """Captain ends the sticky Academy Mode: graduate (commit) or cancel."""
    user_id = _csrf_user_id(conn, session_id=session_id, session_token=session_token, csrf_token=csrf_token)
    trainee = _require_owned_trainee(conn, str(trainee_id or "").strip(), user_id)
    open_session = get_open_academy_mode(conn, trainee_id=str(trainee["trainee_id"]))
    if open_session is None:
        raise ArcLinkAcademyProgramError("no open Academy Mode for this trainee")
    result = end_academy_mode(
        conn,
        session_id=str(open_session["session_id"]),
        actor=user_id,
        graduate=bool(graduate),
    )
    return ArcLinkApiResponse(status=200, payload=result)


def adopt_user_academy_graduate_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
    source_trainee_id: str,
    name: str = "",
) -> ArcLinkApiResponse:
    user_id = _csrf_user_id(conn, session_id=session_id, session_token=session_token, csrf_token=csrf_token)
    # Owner-scoped: a Captain may only adopt a graduate they own (the gallery is
    # owner-private). This blocks cloning another tenant's private staged corpus.
    _require_owned_trainee(conn, str(source_trainee_id or "").strip(), user_id)
    deployment_id = _primary_deployment_id(conn, user_id)
    if not deployment_id:
        return ArcLinkApiResponse(
            status=400,
            payload={"error": "no_arcpod", "detail": "Deploy an ArcPod before adopting an Academy graduate."},
        )
    trainee = adopt_academy_graduate(
        conn,
        source_trainee_id=str(source_trainee_id or "").strip(),
        user_id=user_id,
        deployment_id=deployment_id,
        name=str(name or "").strip(),
    )
    return ArcLinkApiResponse(status=200, payload={"trainee": trainee})


def adopt_user_academy_specialist_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
    specialist_uid: str,
    name: str = "",
) -> ArcLinkApiResponse:
    user_id = _csrf_user_id(conn, session_id=session_id, session_token=session_token, csrf_token=csrf_token)
    deployment_id = _primary_deployment_id(conn, user_id)
    if not deployment_id:
        return ArcLinkApiResponse(
            status=400,
            payload={"error": "no_arcpod", "detail": "Deploy an ArcPod before adopting an Academy specialist."},
        )
    trainee = adopt_central_specialist(
        conn,
        specialist_uid=str(specialist_uid or "").strip(),
        user_id=user_id,
        deployment_id=deployment_id,
        name=str(name or "").strip(),
    )
    return ArcLinkApiResponse(status=200, payload={"trainee": trainee})


def admin_apply_user_crew_recipe_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
    user_id: str,
    role: str,
    mission: str,
    treatment: str,
    preset: str,
    capacity: str,
) -> ArcLinkApiResponse:
    session = authenticate_arclink_admin_session(conn, session_id=session_id, session_token=session_token)
    _admin_mutation_allowed(conn, session)
    require_arclink_csrf(conn, session_id=session_id, csrf_token=csrf_token, session_kind="admin")
    result = apply_crew_recipe(
        conn,
        user_id=user_id,
        **_crew_recipe_args(role=role, mission=mission, treatment=treatment, preset=preset, capacity=capacity),
        actor_id=str(session.get("admin_id") or ""),
        operator_on_behalf=True,
    )
    return ArcLinkApiResponse(status=200, payload=result)


def read_admin_dashboard_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    **filters: Any,
) -> ArcLinkApiResponse:
    authenticate_arclink_admin_session(conn, session_id=session_id, session_token=session_token)
    return ArcLinkApiResponse(status=200, payload=read_arclink_admin_dashboard(conn, **filters))


def read_admin_wrapped_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
) -> ArcLinkApiResponse:
    authenticate_arclink_admin_session(conn, session_id=session_id, session_token=session_token)
    return ArcLinkApiResponse(status=200, payload=wrapped_admin_aggregate(conn))


def read_user_billing_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
) -> ArcLinkApiResponse:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    target_user = str(session["user_id"] or "")
    dashboard = read_arclink_user_dashboard(conn, user_id=target_user)
    billing = {
        "entitlement": dashboard.get("entitlement", {}),
        "subscriptions": [],
        "renewal_lifecycle": renewal_lifecycle_for_billing_state(str(dashboard.get("entitlement", {}).get("state") or "")),
    }
    for dep in dashboard.get("deployments", []):
        for sub in dep.get("billing", {}).get("subscriptions", []):
            if sub not in billing["subscriptions"]:
                billing["subscriptions"].append(sub)
    return ArcLinkApiResponse(status=200, payload=billing)


def create_user_portal_link_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    stripe_client: Any,
    return_url: str = "",
) -> ArcLinkApiResponse:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    target_user = str(session["user_id"] or "")
    row = conn.execute(
        "SELECT stripe_customer_id FROM arclink_users WHERE user_id = ?",
        (target_user,),
    ).fetchone()
    customer_id = str(row["stripe_customer_id"] or "") if row else ""
    if not customer_id:
        return ArcLinkApiResponse(status=400, payload={"error": "no_stripe_customer"})
    portal = stripe_client.create_portal_session(customer_id=customer_id, return_url=return_url)
    return ArcLinkApiResponse(status=200, payload={"portal_url": portal.get("url", "")})


def _user_refuel_deployment(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    deployment_id: str = "",
) -> sqlite3.Row | None:
    clean_deployment = str(deployment_id or "").strip()
    if clean_deployment:
        return conn.execute(
            """
            SELECT deployment_id, user_id, prefix, status
            FROM arclink_deployments
            WHERE deployment_id = ? AND user_id = ?
            """,
            (clean_deployment, user_id),
        ).fetchone()
    return conn.execute(
        """
        SELECT deployment_id, user_id, prefix, status
        FROM arclink_deployments
        WHERE user_id = ?
          AND status NOT IN ('entitlement_required', 'teardown_complete', 'cancelled')
        ORDER BY updated_at DESC, created_at DESC
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()


def create_user_refuel_checkout_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    stripe_client: Any,
    deployment_id: str = "",
    amount_cents: int = 0,
    success_url: str = "",
    cancel_url: str = "",
    env: Mapping[str, str] | None = None,
) -> ArcLinkApiResponse:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    target_user = str(session["user_id"] or "").strip()
    deployment = _user_refuel_deployment(conn, user_id=target_user, deployment_id=deployment_id)
    if deployment is None:
        return ArcLinkApiResponse(status=404, payload={"error": "deployment_not_found"})
    clean_status = str(deployment["status"] or "")
    if clean_status in {"entitlement_required", "teardown_complete", "cancelled"}:
        return ArcLinkApiResponse(status=409, payload={"error": "deployment_not_ready", "status": clean_status})
    try:
        quote = quote_arclink_refuel_topup(int(amount_cents or 0), env)
    except ValueError as exc:
        options = arclink_refuel_topup_options(env)
        return ArcLinkApiResponse(
            status=400,
            payload={
                "error": "invalid_refuel_amount",
                "detail": str(exc),
                "pricing": options,
            },
        )
    root_success = str(success_url or "").strip() or "/checkout/success?kind=refuel"
    root_cancel = str(cancel_url or "").strip() or "/dashboard?tab=billing"
    metadata = {
        "arclink_purchase_kind": "inference_refuel",
        "purchase_kind": "inference_refuel",
        "arclink_user_id": target_user,
        "user_id": target_user,
        "arclink_deployment_id": str(deployment["deployment_id"] or ""),
        "deployment_id": str(deployment["deployment_id"] or ""),
        "retail_cents": str(quote["retail_cents"]),
        "credit_cents": str(quote["provider_credit_cents"]),
        "provider_credit_bps": str(quote["provider_credit_bps"]),
        "sku_id": str(quote["sku_id"]),
    }
    product_data: dict[str, Any]
    if str(quote.get("stripe_product_id") or "").strip():
        product_data = {"product": str(quote["stripe_product_id"]).strip()}
    else:
        product_data = {
            "product_data": {
                "name": str(quote["product_name"]),
                "metadata": {
                    "arclink_sku_id": str(quote["sku_id"]),
                    "arclink_product_kind": "inference_refuel",
                },
            }
        }
    checkout = stripe_client.create_checkout_session(
        user_id=target_user,
        price_id="",
        mode="payment",
        success_url=root_success,
        cancel_url=root_cancel,
        client_reference_id=target_user,
        metadata=metadata,
        idempotency_key=f"refuel:{metadata['deployment_id']}:{metadata['retail_cents']}:{secrets.token_hex(8)}",
        line_items=[
            {
                "price_data": {
                    "currency": str(quote["currency"]),
                    "unit_amount": int(quote["retail_cents"]),
                    **product_data,
                },
                "quantity": 1,
            }
        ],
    )
    return ArcLinkApiResponse(
        status=200,
        payload={
            "checkout_url": checkout.get("url", ""),
            "checkout_session_id": checkout.get("id", ""),
            "deployment_id": metadata["deployment_id"],
            "quote": quote,
            "pricing": arclink_refuel_topup_options(env),
        },
    )


def read_user_provisioning_status_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    deployment_id: str = "",
) -> ArcLinkApiResponse:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    target_user = str(session["user_id"] or "")
    clean_deployment_id = str(deployment_id or "").strip()
    if clean_deployment_id:
        row = conn.execute(
            "SELECT user_id FROM arclink_deployments WHERE deployment_id = ?",
            (clean_deployment_id,),
        ).fetchone()
        if row is None:
            return ArcLinkApiResponse(status=404, payload={"error": "deployment_not_found", "deployments": []})
        if str(row["user_id"] or "") != target_user:
            raise ArcLinkApiAuthError("ArcLink user session cannot read another user deployment")
    dashboard = read_arclink_user_dashboard(conn, user_id=target_user, deployment_id=deployment_id)
    from arclink_product import launch_phrase  # local import to avoid cycle
    deployments = []
    for dep in dashboard.get("deployments", []):
        deployments.append({
            "deployment_id": dep["deployment_id"],
            "status": dep["status"],
            "launch_phrase": launch_phrase(str(dep.get("status") or "")),
            "service_health": dep.get("service_health", []),
            "recent_events": dep.get("recent_events", []),
        })
    return ArcLinkApiResponse(status=200, payload={"deployments": deployments})


def _stable_handoff_id(deployment_id: str, credential_kind: str) -> str:
    digest = hashlib.sha256(f"{deployment_id}:{credential_kind}".encode("utf-8")).hexdigest()[:24]
    return f"cred_{digest}"


def _credential_label(kind: str) -> str:
    return {
        "dashboard_password": "Dashboard password",
        "chutes_api_key": "Chutes provider key",
        "notion_token": "Notion integration token",
    }.get(kind, kind.replace("_", " ").title())


def _secret_store_root() -> Path:
    configured = str(os.environ.get("ARCLINK_SECRET_STORE_DIR") or "").strip()
    if configured:
        return Path(configured).resolve()
    state_dir = str(os.environ.get("STATE_DIR") or "").strip()
    if state_dir:
        return (Path(state_dir) / "sovereign-secrets").resolve()
    return Path("/home/arclink/arclink/arclink-priv/state/sovereign-secrets").resolve()


def _dashboard_password_secret_path(*, deployment_id: str, user_id: str = "", secret_ref: str) -> Path | None:
    clean_deployment = str(deployment_id or "").strip()
    clean_user = str(user_id or "").strip()
    clean_ref = str(secret_ref or "").strip()
    root = _secret_store_root()
    if clean_deployment and clean_ref == f"secret://arclink/dashboard/{clean_deployment}/password":
        deployment_root = (root / clean_deployment).resolve()
        path = (deployment_root / f"{hashlib.sha256(clean_ref.encode('utf-8')).hexdigest()}.secret").resolve()
        try:
            path.relative_to(deployment_root)
        except ValueError:
            return None
        return path
    if clean_user and clean_ref == f"secret://arclink/dashboard/users/{clean_user}/password":
        users_root = (root / "users").resolve()
        path = (users_root / f"{hashlib.sha256(clean_ref.encode('utf-8')).hexdigest()}.secret").resolve()
        try:
            path.relative_to(users_root)
        except ValueError:
            return None
        return path
    return None


def _resolve_revealable_credential_secret(row: Mapping[str, Any]) -> str:
    kind = str(row.get("credential_kind") or "").strip()
    if kind != "dashboard_password":
        return ""
    path = _dashboard_password_secret_path(
        deployment_id=str(row.get("deployment_id") or ""),
        user_id=str(row.get("user_id") or ""),
        secret_ref=str(row.get("secret_ref") or ""),
    )
    if path is None or not path.is_file():
        return ""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return raw if raw.startswith("arc_") else ""


def _dashboard_password_ref_for_handoff(*, deployment_id: str, user_id: str, metadata: Mapping[str, Any]) -> str:
    refs = metadata.get("secret_refs") if isinstance(metadata.get("secret_refs"), Mapping) else {}
    explicit = str((refs or {}).get("dashboard_password") or metadata.get("dashboard_password_ref") or "").strip()
    if explicit:
        return explicit
    clean_user = str(user_id or "").strip()
    if clean_user:
        return f"secret://arclink/dashboard/users/{clean_user}/password"
    return f"secret://arclink/dashboard/{deployment_id}/password"


def _deployment_secret_refs(deployment_id: str, metadata: Mapping[str, Any], *, user_id: str = "") -> dict[str, str]:
    refs = metadata.get("secret_refs") if isinstance(metadata.get("secret_refs"), Mapping) else {}
    defaults = {
        "dashboard_password": _dashboard_password_ref_for_handoff(deployment_id=deployment_id, user_id=user_id, metadata=metadata),
        "chutes_api_key": f"secret://arclink/chutes/{deployment_id}",
    }
    result: dict[str, str] = {}
    for key in sorted(ARCLINK_CREDENTIAL_HANDOFF_KINDS):
        value = str((refs or {}).get(key) or defaults.get(key) or "").strip()
        if value:
            result[key] = value
    return result


def _ensure_credential_handoffs(conn: sqlite3.Connection, *, user_id: str, deployment_id: str) -> None:
    row = conn.execute(
        "SELECT metadata_json FROM arclink_deployments WHERE deployment_id = ? AND user_id = ?",
        (deployment_id, user_id),
    ).fetchone()
    if row is None:
        raise ArcLinkApiAuthError("ArcLink user session cannot read another user deployment")
    metadata = _json_loads(str(row["metadata_json"] or "{}"))
    now = utc_now_iso()
    expires_at = utc_after_seconds_iso(ARCLINK_CREDENTIAL_HANDOFF_TTL_SECONDS)
    for kind, secret_ref in _deployment_secret_refs(deployment_id, metadata, user_id=user_id).items():
        if kind not in ARCLINK_CREDENTIAL_HANDOFF_KINDS:
            continue
        _reject_secret_material({"secret_ref": secret_ref})
        delivery_hint = (
            "Copy the dashboard password shown here into your password manager, then acknowledge storage."
            if kind == "dashboard_password"
            else "This provider or integration credential is managed through ArcLink's scoped secret rail; ask Raven or the operator for a rotation workflow."
        )
        conn.execute(
            """
            INSERT INTO arclink_credential_handoffs (
              handoff_id, user_id, deployment_id, credential_kind, display_name,
              secret_ref, delivery_hint, status, expires_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'available', ?, ?, ?)
            ON CONFLICT(deployment_id, credential_kind) DO UPDATE SET
              user_id = excluded.user_id,
              secret_ref = CASE
                WHEN arclink_credential_handoffs.status = 'available' THEN excluded.secret_ref
                ELSE arclink_credential_handoffs.secret_ref
              END,
              expires_at = CASE
                WHEN arclink_credential_handoffs.status = 'available' AND arclink_credential_handoffs.expires_at = '' THEN excluded.expires_at
                ELSE arclink_credential_handoffs.expires_at
              END,
              updated_at = excluded.updated_at
            """,
            (
                _stable_handoff_id(deployment_id, kind),
                user_id,
                deployment_id,
                kind,
                _credential_label(kind),
                secret_ref,
                delivery_hint,
                expires_at,
                now,
                now,
            ),
        )
    conn.commit()


def expire_revealable_user_material(conn: sqlite3.Connection, *, commit: bool = True) -> dict[str, int]:
    now = utc_now_iso()
    handoff_cursor = conn.execute(
        """
        UPDATE arclink_credential_handoffs
        SET status = 'expired',
            removed_at = CASE WHEN removed_at = '' THEN ? ELSE removed_at END,
            updated_at = ?
        WHERE status = 'available'
          AND expires_at != ''
          AND expires_at <= ?
        """,
        (now, now, now),
    )
    share_cursor = conn.execute(
        """
        UPDATE arclink_share_grants
        SET status = 'expired',
            revoked_at = CASE WHEN revoked_at = '' THEN ? ELSE revoked_at END,
            updated_at = ?
        WHERE status IN ('pending_owner_approval', 'approved')
          AND expires_at != ''
          AND expires_at <= ?
        """,
        (now, now, now),
    )
    nonce_cursor = conn.execute(
        """
        UPDATE arclink_share_claim_nonces
        SET status = 'expired', updated_at = ?
        WHERE status = 'pending'
          AND expires_at != ''
          AND expires_at <= ?
        """,
        (now, now),
    )
    if commit:
        conn.commit()
    return {
        "credential_handoffs": handoff_cursor.rowcount,
        "share_grants": share_cursor.rowcount,
        "share_claim_nonces": nonce_cursor.rowcount,
    }


def _public_credential_handoff(row: Mapping[str, Any], *, raw_secret: str = "") -> dict[str, Any]:
    status = str(row.get("status") or "")
    expires_at = str(row.get("expires_at") or "")
    expired = status == "expired" or bool(expires_at and (parse_utc_iso(expires_at) or utc_now()) <= utc_now())
    removed = status in {"removed", "expired"} or bool(str(row.get("removed_at") or ""))
    allow_reveal = bool(row.get("_allow_reveal"))
    revealable = bool(raw_secret) and not removed and not expired and (allow_reveal or not str(row.get("revealed_at") or ""))
    payload = {
        "handoff_id": str(row.get("handoff_id") or ""),
        "deployment_id": str(row.get("deployment_id") or ""),
        "credential_kind": str(row.get("credential_kind") or ""),
        "display_name": str(row.get("display_name") or ""),
        "status": status,
        "revealed_at": str(row.get("revealed_at") or ""),
        "expires_at": expires_at,
        "acknowledged_at": str(row.get("acknowledged_at") or ""),
        "removed_at": str(row.get("removed_at") or ""),
        "delivery_hint": "" if removed else str(row.get("delivery_hint") or ""),
        "copy_guidance": "" if removed else "Store it in a password manager; do not paste it into shared channels.",
        "raw_secret": raw_secret if revealable else "",
    }
    if not removed:
        payload["secret_ref"] = mask_secret_ref(str(row.get("secret_ref") or ""))
        payload["reveal_mode"] = "user_dashboard" if revealable else "not_revealable_from_user_api"
    return payload


def read_user_credentials_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    deployment_id: str = "",
) -> ArcLinkApiResponse:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    expire_revealable_user_material(conn)
    target_user = str(session["user_id"] or "")
    deployment_args: list[Any] = [target_user]
    deployment_filter = ""
    clean_deployment = str(deployment_id or "").strip()
    if clean_deployment:
        deployment_filter = "AND deployment_id = ?"
        deployment_args.append(clean_deployment)
    deployments = [
        str(row["deployment_id"] or "")
        for row in conn.execute(
            f"SELECT deployment_id FROM arclink_deployments WHERE user_id = ? {deployment_filter}",
            tuple(deployment_args),
        ).fetchall()
    ]
    if clean_deployment and not deployments:
        raise ArcLinkApiAuthError("ArcLink user session cannot read another user deployment")
    for dep_id in deployments:
        _ensure_credential_handoffs(conn, user_id=target_user, deployment_id=dep_id)
    rows = conn.execute(
        """
        SELECT *
        FROM arclink_credential_handoffs
        WHERE user_id = ?
          AND (? = '' OR deployment_id = ?)
        ORDER BY deployment_id, credential_kind
        """,
        (target_user, clean_deployment, clean_deployment),
    ).fetchall()
    credentials = []
    revealed_ids: list[str] = []
    now = utc_now_iso()
    for row in rows:
        row_data = rowdict(row)
        if str(row_data.get("status") or "") in {"removed", "expired"}:
            continue
        raw_secret = _resolve_revealable_credential_secret(row_data)
        if raw_secret and not str(row_data.get("revealed_at") or ""):
            row_data["_allow_reveal"] = True
            row_data["revealed_at"] = now
            revealed_ids.append(str(row_data.get("handoff_id") or ""))
        credentials.append(_public_credential_handoff(row_data, raw_secret=raw_secret))
    if revealed_ids:
        conn.executemany(
            """
            UPDATE arclink_credential_handoffs
            SET revealed_at = CASE WHEN revealed_at = '' THEN ? ELSE revealed_at END,
                updated_at = ?
            WHERE handoff_id = ?
            """,
            [(now, now, hid) for hid in revealed_ids],
        )
        conn.commit()
    removed_count = sum(1 for row in rows if str(row["status"] or "") in {"removed", "expired"})
    return ArcLinkApiResponse(
        status=200,
        payload={
            "instructions": {
                "copy": "Copy any revealed dashboard credential into your password manager.",
                "acknowledge": "After acknowledgement, ArcLink removes the handoff from future user API responses.",
                "reissue": "Ask Raven or the operator to rotate or reissue a removed credential.",
            },
            "credentials": credentials,
            "removed_count": removed_count,
        },
    )


def acknowledge_user_credential_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
    handoff_id: str,
) -> ArcLinkApiResponse:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    require_arclink_csrf(conn, session_id=session_id, csrf_token=csrf_token, session_kind="user")
    target_user = str(session["user_id"] or "")
    clean_handoff = str(handoff_id or "").strip()
    row = conn.execute(
        "SELECT * FROM arclink_credential_handoffs WHERE handoff_id = ?",
        (clean_handoff,),
    ).fetchone()
    if row is None or str(row["user_id"] or "") != target_user:
        raise ArcLinkApiAuthError("ArcLink user session cannot acknowledge another user's credential")
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
        (now, now, now, clean_handoff, target_user),
    )
    append_arclink_audit(
        conn,
        action="credential_handoff_acknowledged",
        actor_id=target_user,
        target_kind="credential_handoff",
        target_id=clean_handoff,
        reason="user confirmed credential storage",
        metadata={"deployment_id": str(row["deployment_id"] or ""), "credential_kind": str(row["credential_kind"] or "")},
        commit=False,
    )
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=str(row["deployment_id"] or ""),
        event_type="credential_handoff_removed",
        metadata={"credential_kind": str(row["credential_kind"] or ""), "user_id": target_user},
        commit=False,
    )
    conn.commit()
    public = _public_credential_handoff(rowdict(conn.execute("SELECT * FROM arclink_credential_handoffs WHERE handoff_id = ?", (clean_handoff,)).fetchone()))
    return ArcLinkApiResponse(status=200, payload={"credential": public})


def _clean_share_path(value: str) -> str:
    text = str(value or "").replace("\\", "/").strip()
    if not text or text in {"/", ".", "./"}:
        raise ArcLinkApiAuthError("ArcLink share requires a named file or directory path")
    text = text.lstrip("/")
    parts: list[str] = []
    for part in text.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise ArcLinkApiAuthError("ArcLink share path traversal is not allowed")
        lowered = part.lower()
        if lowered in {".ssh", "secrets"} or lowered == ".env" or lowered.startswith(".env.") or "bootstrap-token" in lowered:
            raise ArcLinkApiAuthError("ArcLink share path cannot target private runtime or secret material")
        parts.append(part)
    if not parts:
        raise ArcLinkApiAuthError("ArcLink share requires a named file or directory path")
    return "/" + "/".join(parts)


def _safe_projection_segment(value: str, *, fallback: str = "linked-resource") -> str:
    segment = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in str(value or "").strip())
    segment = "-".join(part for part in segment.split("-") if part).strip(".-_")
    return (segment[:96] or fallback).strip(".-_") or fallback


def _render_share_state_roots(*, deployment_id: str, prefix: str, state_root_base: str) -> dict[str, str]:
    base = str(state_root_base or "/arcdata/deployments").rstrip("/")
    root = f"{base}/{_safe_projection_segment(deployment_id, fallback='deployment')}-{_safe_projection_segment(prefix, fallback='pod')}"
    return {
        "root": root,
        "vault": f"{root}/vault",
        "code_workspace": f"{root}/workspace",
        "linked_resources": f"{root}/linked-resources",
    }


def _deployment_state_roots_for_user(conn: sqlite3.Connection, user_id: str, *, deployment_id: str = "") -> dict[str, str]:
    clean_user = str(user_id or "").strip()
    clean_deployment = str(deployment_id or "").strip()
    if clean_deployment:
        rows = conn.execute(
            """
            SELECT deployment_id, prefix, status, metadata_json
            FROM arclink_deployments
            WHERE user_id = ? AND deployment_id = ?
            """,
            (clean_user, clean_deployment),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT deployment_id, prefix, status, metadata_json
            FROM arclink_deployments
            WHERE user_id = ?
            ORDER BY
              CASE status
                WHEN 'active' THEN 0
                WHEN 'running' THEN 1
                WHEN 'provisioning' THEN 2
                WHEN 'provisioning_ready' THEN 3
                ELSE 9
              END,
              updated_at DESC,
              deployment_id DESC
            """,
            (clean_user,),
        ).fetchall()
    for row in rows:
        metadata = json_loads_safe(str(row["metadata_json"] or "{}"))
        raw_roots = metadata.get("state_roots")
        if isinstance(raw_roots, Mapping):
            roots = {str(key): str(value) for key, value in raw_roots.items() if str(value or "").strip()}
            if roots.get("vault") or roots.get("code_workspace") or roots.get("linked_resources"):
                return roots
        state_root_base = str(metadata.get("state_root_base") or os.environ.get("ARCLINK_STATE_ROOT_BASE") or "/arcdata/deployments")
        return _render_share_state_roots(
            deployment_id=str(row["deployment_id"] or ""),
            prefix=str(row["prefix"] or ""),
            state_root_base=state_root_base,
        )
    return {}


def _write_json_file_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, sort_keys=True, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        try:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        except OSError:
            pass


def revoke_user_dashboard_access(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    actor_id: str,
    reason: str,
    commit: bool = True,
) -> dict[str, Any]:
    """Invalidate per-Agent dashboard cookies for every deployment owned by a user.

    The dashboard proxy is intentionally DB-free and reloads
    ``arclink-web-access.json`` for each request. Stamping a revocation epoch in
    that file lets hosted logout/admin revoke invalidate stateless dashboard JWTs
    and Crew-wide SSO cookies without widening proxy privileges.
    """

    clean_user = str(user_id or "").strip()
    if not clean_user:
        return {"revoked": False, "reason": "user_id_required", "updated_files": 0, "updated_deployments": 0}
    now = utc_now_iso()
    epoch = int(utc_now().timestamp())
    rows = [
        rowdict(row)
        for row in conn.execute(
            """
            SELECT deployment_id, metadata_json
            FROM arclink_deployments
            WHERE user_id = ?
            ORDER BY created_at, deployment_id
            """,
            (clean_user,),
        ).fetchall()
    ]
    updated_files = 0
    failed_files: list[str] = []
    for row in rows:
        metadata = json_loads_safe(str(row.get("metadata_json") or "{}"))
        roots = metadata.get("state_roots") if isinstance(metadata.get("state_roots"), Mapping) else {}
        hermes_home = str((roots or {}).get("hermes_home") or "").strip()
        if hermes_home:
            access_path = Path(hermes_home).expanduser() / "state" / "arclink-web-access.json"
            if access_path.is_file():
                try:
                    access = json_loads_safe(access_path.read_text(encoding="utf-8"))
                    if not isinstance(access, dict):
                        access = {}
                    access.update(
                        {
                            "dashboard_session_revoked_before": epoch,
                            "dashboard_sso_revoked_before": epoch,
                            "dashboard_auth_revoked_at": now,
                            "dashboard_auth_revoked_by": str(actor_id or "").strip()[:160],
                            "dashboard_auth_revocation_reason": str(reason or "").strip()[:240],
                        }
                    )
                    _write_json_file_atomic(access_path, access)
                    updated_files += 1
                except OSError:
                    failed_files.append(str(access_path))
        metadata["dashboard_auth_revoked_before"] = epoch
        metadata["dashboard_auth_revoked_at"] = now
        metadata["dashboard_auth_revoked_by"] = str(actor_id or "").strip()[:160]
        metadata["dashboard_auth_revocation_reason"] = str(reason or "").strip()[:240]
        conn.execute(
            "UPDATE arclink_deployments SET metadata_json = ?, updated_at = ? WHERE deployment_id = ?",
            (json_dumps_safe(metadata), now, str(row.get("deployment_id") or "")),
        )
    if commit:
        conn.commit()
    return {
        "revoked": bool(rows),
        "updated_files": updated_files,
        "updated_deployments": len(rows),
        "failed_files": failed_files[:10],
        "revoked_before": epoch,
    }


def _share_deployment_user(
    conn: sqlite3.Connection,
    deployment_id: str,
    *,
    expected_user_id: str = "",
    label: str = "deployment",
) -> str:
    clean_deployment = str(deployment_id or "").strip()
    if not clean_deployment:
        return ""
    row = conn.execute(
        "SELECT user_id FROM arclink_deployments WHERE deployment_id = ?",
        (clean_deployment,),
    ).fetchone()
    if row is None:
        raise ArcLinkApiAuthError(f"ArcLink share {label} deployment was not found")
    actual_user = str(row["user_id"] or "").strip()
    expected = str(expected_user_id or "").strip()
    if expected and actual_user != expected:
        raise ArcLinkApiAuthError(f"ArcLink share {label} deployment is outside the expected account")
    return actual_user


def set_deployment_share_request_broker_token_hash(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    token: str,
    token_ref: str = "",
) -> dict[str, Any]:
    clean_deployment = str(deployment_id or "").strip()
    if not clean_deployment:
        raise ArcLinkApiAuthError("ArcLink share-request broker deployment is required")
    row = conn.execute(
        "SELECT metadata_json FROM arclink_deployments WHERE deployment_id = ?",
        (clean_deployment,),
    ).fetchone()
    if row is None:
        raise KeyError(clean_deployment)
    metadata = json_loads_safe(str(row["metadata_json"] or "{}"))
    broker = metadata.get("share_request_broker")
    if not isinstance(broker, Mapping):
        broker = {}
    metadata["share_request_broker"] = {
        **dict(broker),
        "enabled": True,
        "token_hash": hash_share_request_broker_token(token),
        "token_ref": str(token_ref or "").strip(),
        "updated_at": utc_now_iso(),
    }
    conn.execute(
        "UPDATE arclink_deployments SET metadata_json = ?, updated_at = ? WHERE deployment_id = ?",
        (json.dumps(metadata, sort_keys=True), utc_now_iso(), clean_deployment),
    )
    conn.commit()
    return metadata["share_request_broker"]


def _share_request_broker_config(metadata: Mapping[str, Any]) -> dict[str, Any]:
    broker = metadata.get("share_request_broker")
    if isinstance(broker, Mapping):
        return dict(broker)
    legacy_hash = str(metadata.get("share_request_broker_token_hash") or "").strip()
    if legacy_hash:
        return {"enabled": True, "token_hash": legacy_hash}
    return {}


def _authenticate_share_request_broker(
    conn: sqlite3.Connection,
    *,
    owner_deployment_id: str,
    broker_token: str,
) -> dict[str, Any]:
    clean_deployment = str(owner_deployment_id or "").strip()
    clean_token = str(broker_token or "").strip()
    if not clean_deployment or not clean_token:
        raise ArcLinkApiAuthError("ArcLink share-request broker credentials are required")
    row = conn.execute(
        """
        SELECT deployment_id, user_id, status, metadata_json
        FROM arclink_deployments
        WHERE deployment_id = ?
        """,
        (clean_deployment,),
    ).fetchone()
    if row is None:
        raise ArcLinkApiAuthError("ArcLink share-request broker deployment was not found")
    deployment = rowdict(row)
    deployment_status = str(deployment.get("status") or "").strip()
    if deployment_status not in ARCLINK_SHARE_BROKER_ACTIVE_DEPLOYMENT_STATUSES:
        raise ArcLinkApiAuthError("ArcLink share-request broker deployment is not active")
    metadata = json_loads_safe(str(deployment.get("metadata_json") or "{}"))
    broker = _share_request_broker_config(metadata)
    if broker.get("enabled") is False:
        raise ArcLinkApiAuthError("ArcLink share-request broker is disabled")
    token_hash = str(broker.get("token_hash") or "").strip()
    if not token_hash or not _verify_proof_token_hash(clean_token, token_hash, allow_legacy=False):
        raise ArcLinkApiAuthError("ArcLink share-request broker token is invalid")
    return {
        "deployment_id": str(deployment.get("deployment_id") or ""),
        "user_id": str(deployment.get("user_id") or ""),
        "status": str(deployment.get("status") or ""),
        "metadata": metadata,
    }


def _resolve_share_recipient_user_id(
    conn: sqlite3.Connection,
    *,
    recipient_user_id: str = "",
    recipient_identity: str = "",
    recipient_deployment_id: str = "",
) -> str:
    clean_deployment = str(recipient_deployment_id or "").strip()
    clean_user = str(recipient_user_id or "").strip()
    if clean_deployment:
        resolved = _share_deployment_user(
            conn,
            clean_deployment,
            expected_user_id=clean_user,
            label="recipient",
        )
        if resolved:
            return resolved
    if clean_user:
        if conn.execute("SELECT 1 FROM arclink_users WHERE user_id = ?", (clean_user,)).fetchone() is None:
            raise KeyError(clean_user)
        return clean_user
    identity = str(recipient_identity or "").strip()
    if not identity:
        raise ArcLinkApiAuthError("ArcLink share requires a recipient user, email, or deployment")
    row = conn.execute(
        "SELECT user_id FROM arclink_users WHERE user_id = ?",
        (identity,),
    ).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT user_id FROM arclink_users WHERE LOWER(email) = LOWER(?) AND email != ''",
            (identity,),
        ).fetchone()
    if row is None:
        raise KeyError(identity)
    return str(row["user_id"] or "")


def _path_within(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _sensitive_share_projection_path(path: Path) -> bool:
    lowered_parts = {part.lower() for part in path.parts}
    if lowered_parts & {".ssh", "secrets"}:
        return True
    name = path.name.lower()
    if name == ".env" or name.startswith(".env.") or "bootstrap-token" in name:
        return True
    if name in {"id_dsa", "id_ecdsa", "id_ed25519", "id_rsa"}:
        return True
    return False


def _chmod_read_only(path: Path) -> None:
    try:
        path.chmod(0o555 if path.is_dir() else 0o444)
    except OSError:
        pass


def _clean_share_access_mode(value: str, *, default: str = "read_write") -> str:
    mode = str(value or default).strip().lower().replace("-", "_")
    return mode or default


def _share_projection_read_only(access_mode: str, resource_kind: str = "") -> bool:
    mode = _clean_share_access_mode(access_mode)
    kind = str(resource_kind or "").strip().lower()
    return not (mode == "read_write" and kind in {"drive", "code"})


def _linked_manifest_path(linked_root: Path) -> Path:
    return linked_root / ARCLINK_LINKED_RESOURCE_MANIFEST


def _load_linked_manifest(linked_root: Path) -> dict[str, Any]:
    try:
        payload = json.loads(_linked_manifest_path(linked_root).read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        entries = {}
    return {"version": 1, "entries": entries}


def _write_linked_manifest(linked_root: Path, payload: Mapping[str, Any]) -> None:
    linked_root.mkdir(parents=True, exist_ok=True)
    path = _linked_manifest_path(linked_root)
    fd, tmp_name = tempfile.mkstemp(dir=str(linked_root), prefix=".arclink-linked-", suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
        _chmod_read_only(path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _upsert_linked_manifest_entry(
    linked_root: Path,
    *,
    slug: str,
    grant_id: str,
    source: Path,
    linked_path: str,
    entry_path: str,
    resource_kind: str,
    owner_user_id: str,
    read_only: bool,
    access_mode: str,
    updated_at: str,
) -> None:
    payload = _load_linked_manifest(linked_root)
    entries = dict(payload.get("entries") or {})
    entries[slug] = {
        "grant_id": grant_id,
        "source_path": str(source),
        "linked_path": linked_path,
        "entry_path": entry_path,
        "resource_kind": resource_kind,
        "owner_user_id": owner_user_id,
        "read_only": bool(read_only),
        "access_mode": access_mode,
        "projection_mode": "living_symlink",
        "updated_at": updated_at,
    }
    payload["entries"] = entries
    _write_linked_manifest(linked_root, payload)


def _remove_linked_manifest_entry(linked_root: Path, *, slug: str) -> None:
    payload = _load_linked_manifest(linked_root)
    entries = dict(payload.get("entries") or {})
    if slug in entries:
        entries.pop(slug, None)
        payload["entries"] = entries
        _write_linked_manifest(linked_root, payload)


def _remove_projection_path(root: Path, target: Path) -> bool:
    root_resolved = root.expanduser().resolve(strict=False)
    target_path = target.expanduser()
    if target_path.is_symlink():
        parent_resolved = target_path.parent.resolve(strict=False)
        if parent_resolved != root_resolved and not _path_within(root_resolved, parent_resolved):
            raise ArcLinkApiAuthError("ArcLink linked resource projection path is outside the linked root")
        target_path.unlink(missing_ok=True)
        return True
    target_resolved = target_path.resolve(strict=False)
    if target_resolved != root_resolved and not _path_within(root_resolved, target_resolved):
        raise ArcLinkApiAuthError("ArcLink linked resource projection path is outside the linked root")
    if not target_resolved.exists() and not target_resolved.is_symlink():
        return False
    if target_resolved.is_symlink() or target_resolved.is_file():
        try:
            target_resolved.chmod(0o600)
        except OSError:
            pass
        target_resolved.unlink(missing_ok=True)
        return True
    for current_root, dirnames, filenames in os.walk(target_resolved, topdown=False):
        current = Path(current_root)
        for name in filenames:
            child = current / name
            try:
                child.chmod(0o600)
            except OSError:
                pass
        for name in dirnames:
            child = current / name
            try:
                child.chmod(0o700)
            except OSError:
                pass
        try:
            current.chmod(0o700)
        except OSError:
            pass
    shutil.rmtree(target_resolved)
    return True


def _copy_projection_tree(source: Path, destination: Path) -> int:
    skipped = 0
    if source.is_symlink():
        raise ArcLinkApiAuthError("ArcLink share projections do not follow symlinks")
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        _chmod_read_only(destination)
        return skipped
    destination.mkdir(parents=True, exist_ok=True)
    for current_root, dirnames, filenames in os.walk(source):
        current = Path(current_root)
        rel = current.relative_to(source)
        dirnames[:] = [
            name
            for name in dirnames
            if not (current / name).is_symlink() and not _sensitive_share_projection_path(current / name)
        ]
        skipped += len([name for name in filenames if _sensitive_share_projection_path(current / name) or (current / name).is_symlink()])
        target_dir = destination / rel
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in filenames:
            child = current / name
            if child.is_symlink() or _sensitive_share_projection_path(child):
                continue
            target_file = target_dir / name
            shutil.copy2(child, target_file)
            _chmod_read_only(target_file)
    for current_root, dirnames, _filenames in os.walk(destination, topdown=False):
        for name in dirnames:
            _chmod_read_only(Path(current_root) / name)
        _chmod_read_only(Path(current_root))
    return skipped


def _share_projection_public(metadata: Mapping[str, Any]) -> dict[str, Any]:
    projection = metadata.get("projection")
    if not isinstance(projection, Mapping):
        return {
            "status": "not_materialized",
            "linked_root": "linked",
            "linked_path": "",
            "entry_path": "",
            "owner_deployment_id": str(metadata.get("owner_deployment_id") or metadata.get("deployment_id") or ""),
            "recipient_deployment_id": str(metadata.get("recipient_deployment_id") or ""),
            "read_only": True,
            "access_mode": "read",
        }
    return {
        "status": str(projection.get("status") or "not_materialized"),
        "linked_root": str(projection.get("linked_root") or "linked"),
        "linked_path": str(projection.get("linked_path") or ""),
        "entry_path": str(projection.get("entry_path") or ""),
        "resource_kind": str(projection.get("resource_kind") or ""),
        "owner_deployment_id": str(projection.get("owner_deployment_id") or metadata.get("owner_deployment_id") or metadata.get("deployment_id") or ""),
        "recipient_deployment_id": str(projection.get("recipient_deployment_id") or metadata.get("recipient_deployment_id") or ""),
        "projection_mode": str(projection.get("projection_mode") or ""),
        "materialized_at": str(projection.get("materialized_at") or ""),
        "removed_at": str(projection.get("removed_at") or ""),
        "reason": str(projection.get("reason") or ""),
        "read_only": bool(projection.get("read_only", True)),
        "access_mode": str(projection.get("access_mode") or metadata.get("access_mode") or ""),
        "inherited_subpages": bool(projection.get("inherited_subpages") or metadata.get("inherit_subpages") or False),
        "skipped_sensitive_count": int(projection.get("skipped_sensitive_count") or 0),
    }


def _public_share_grant(row: Mapping[str, Any]) -> dict[str, Any]:
    metadata = json_loads_safe(str(row.get("metadata_json") or "{}"))
    projection = _share_projection_public(metadata)
    return {
        "grant_id": str(row.get("grant_id") or ""),
        "owner_user_id": str(row.get("owner_user_id") or ""),
        "recipient_user_id": str(row.get("recipient_user_id") or ""),
        "owner_deployment_id": str(metadata.get("owner_deployment_id") or metadata.get("deployment_id") or ""),
        "recipient_deployment_id": str(metadata.get("recipient_deployment_id") or ""),
        "resource_kind": str(row.get("resource_kind") or ""),
        "resource_root": str(row.get("resource_root") or ""),
        "resource_path": str(row.get("resource_path") or ""),
        "display_name": str(row.get("display_name") or ""),
        "access_mode": str(row.get("access_mode") or ""),
        "status": str(row.get("status") or ""),
        "expires_at": str(row.get("expires_at") or ""),
        "reshare_allowed": False,
        "linked_root": projection["linked_root"],
        "linked_path": projection["linked_path"],
        "projection": projection,
        "approved_at": str(row.get("approved_at") or ""),
        "accepted_at": str(row.get("accepted_at") or ""),
        "revoked_at": str(row.get("revoked_at") or ""),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def _share_approval_button_extra(*, channel: str, grant_id: str) -> dict[str, Any]:
    approve_command = f"/share-approve {grant_id}"
    deny_command = f"/share-deny {grant_id}"
    if channel == "telegram":
        return {
            "telegram_reply_markup": {
                "inline_keyboard": [[
                    {"text": "Deny", "callback_data": f"arclink:/raven deny {grant_id}"},
                    {"text": "Approve", "callback_data": f"arclink:/raven approve {grant_id}"},
                ]]
            }
        }
    if channel == "discord":
        return {
            "discord_components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "style": 2,
                            "label": "Deny",
                            "custom_id": f"arclink:{deny_command}",
                        },
                        {
                            "type": 2,
                            "style": 1,
                            "label": "Approve",
                            "custom_id": f"arclink:{approve_command}",
                        },
                    ],
                }
            ]
        }
    return {}


def _share_accept_button_extra(*, channel: str, grant_id: str) -> dict[str, Any]:
    accept_command = f"/share-accept {grant_id}"
    if channel == "telegram":
        return {
            "telegram_reply_markup": {
                "inline_keyboard": [[
                    {"text": "Accept Share", "callback_data": f"arclink:/raven accept {grant_id}"},
                ]]
            }
        }
    if channel == "discord":
        return {
            "discord_components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "style": 1,
                            "label": "Accept Share",
                            "custom_id": f"arclink:{accept_command}",
                        },
                    ],
                }
            ]
        }
    return {}


def _share_public_channel_for_user(conn: sqlite3.Connection, user_id: str) -> dict[str, Any]:
    clean_user = str(user_id or "").strip()
    if not clean_user:
        return {"available": False, "channel": "", "target_id": "", "reason": "missing_user"}
    row = conn.execute(
        """
        SELECT channel, channel_identity
        FROM arclink_onboarding_sessions
        WHERE user_id = ?
          AND LOWER(channel) IN ('telegram', 'discord')
          AND channel_identity != ''
        ORDER BY
          CASE WHEN deployment_id != '' THEN 0 ELSE 1 END,
          updated_at DESC,
          created_at DESC,
          session_id DESC
        LIMIT 1
        """,
        (clean_user,),
    ).fetchone()
    if row is None:
        return {"available": False, "channel": "", "target_id": "", "reason": "no_public_channel"}
    channel = str(row["channel"] or "").strip().lower()
    target = str(row["channel_identity"] or "").strip()
    if channel not in {"telegram", "discord"} or not target:
        return {"available": False, "channel": channel, "target_id": "", "reason": "unsupported_public_channel"}
    return {"available": True, "channel": channel, "target_id": target, "reason": ""}


def _share_public_channel_hint(status: Mapping[str, Any]) -> dict[str, Any]:
    available = bool(status.get("available"))
    reason = str(status.get("reason") or ("public_channel_available" if available else "no_public_channel"))
    return {
        "queued_possible": available,
        "channel": str(status.get("channel") or "") if available else "",
        "reason": reason,
        "recovery_action": "" if available else "use_dashboard_or_link_public_channel",
    }


def _queue_share_grant_owner_notification(
    conn: sqlite3.Connection,
    *,
    grant: Mapping[str, Any],
) -> dict[str, Any]:
    owner_user = str(grant.get("owner_user_id") or "").strip()
    grant_id = str(grant.get("grant_id") or "").strip()
    if not owner_user or not grant_id:
        return {"queued": False, "reason": "missing_owner_or_grant"}
    channel_status = _share_public_channel_for_user(conn, owner_user)
    if not channel_status["available"]:
        return {"queued": False, "reason": str(channel_status.get("reason") or "no_public_channel")}
    channel = str(channel_status["channel"])
    target = str(channel_status["target_id"])

    resource_label = str(grant.get("display_name") or grant.get("resource_path") or "linked resource").strip()
    resource_kind = str(grant.get("resource_kind") or "").strip().lower()
    access_label = "read/write" if resource_kind in {"drive", "code"} else "read-only"
    accept_label = "read/write Linked resource" if resource_kind in {"drive", "code"} else "read-only Linked resource"
    resource_root = str(grant.get("resource_root") or "").strip()
    resource_path = str(grant.get("resource_path") or "").strip()
    recipient = str(grant.get("recipient_user_id") or "").strip()
    message = (
        "Raven share approval requested.\n\n"
        f"Recipient `{recipient}` is asking for {access_label} access to `{resource_label}` "
        f"from `{resource_root}:{resource_path}`.\n\n"
        f"Approve to let the recipient accept it as a {accept_label}. "
        "Deny leaves the share closed. Accepted Linked resources cannot be reshared."
    )
    notification_id = queue_notification(
        conn,
        target_kind="public-bot-user",
        target_id=target,
        channel_kind=channel,
        message=message,
        extra={
            "share_grant_id": grant_id,
            "recipient_user_id": recipient,
            "resource_kind": str(grant.get("resource_kind") or ""),
            "resource_root": resource_root,
            "resource_path": resource_path,
            **_share_approval_button_extra(channel=channel, grant_id=grant_id),
        },
    )
    append_arclink_event(
        conn,
        subject_kind="share_grant",
        subject_id=grant_id,
        event_type="share_grant_owner_notification_queued",
        metadata={"channel": channel, "notification_id": notification_id},
    )
    return {"queued": True, "channel": channel, "notification_id": notification_id}


def queue_share_grant_recipient_notification(
    conn: sqlite3.Connection,
    *,
    grant: Mapping[str, Any],
) -> dict[str, Any]:
    recipient_user = str(grant.get("recipient_user_id") or "").strip()
    grant_id = str(grant.get("grant_id") or "").strip()
    if not recipient_user or not grant_id:
        return {"queued": False, "reason": "missing_recipient_or_grant"}
    channel_status = _share_public_channel_for_user(conn, recipient_user)
    if not channel_status["available"]:
        return {"queued": False, "reason": str(channel_status.get("reason") or "no_public_channel")}
    channel = str(channel_status["channel"])
    target = str(channel_status["target_id"])

    resource_label = str(grant.get("display_name") or grant.get("resource_path") or "linked resource").strip()
    resource_kind = str(grant.get("resource_kind") or "").strip().lower()
    access_label = "read/write" if resource_kind in {"drive", "code"} else "read-only"
    linked_label = "Accepted Drive/Code shares are writable" if resource_kind in {"drive", "code"} else "Linked resources stay read-only"
    resource_root = str(grant.get("resource_root") or "").strip()
    resource_path = str(grant.get("resource_path") or "").strip()
    inherited = " with inherited subpages" if resource_kind == "notion" else ""
    message = (
        "Raven share ready.\n\n"
        f"The owner approved {access_label} access to `{resource_label}` from `{resource_root}:{resource_path}`{inherited}.\n\n"
        f"Accept to add it to your Linked resources. {linked_label} and cannot be reshared."
    )
    notification_id = queue_notification(
        conn,
        target_kind="public-bot-user",
        target_id=target,
        channel_kind=channel,
        message=message,
        extra={
            "share_grant_id": grant_id,
            "owner_user_id": str(grant.get("owner_user_id") or ""),
            "resource_kind": resource_kind,
            "resource_root": resource_root,
            "resource_path": resource_path,
            **_share_accept_button_extra(channel=channel, grant_id=grant_id),
        },
    )
    append_arclink_event(
        conn,
        subject_kind="share_grant",
        subject_id=grant_id,
        event_type="share_grant_recipient_notification_queued",
        metadata={"channel": channel, "notification_id": notification_id},
    )
    return {"queued": True, "channel": channel, "notification_id": notification_id}


def _materialize_share_projection(
    conn: sqlite3.Connection,
    *,
    grant: Mapping[str, Any],
    now: str,
) -> dict[str, Any]:
    grant_id = str(grant.get("grant_id") or "").strip()
    owner_user = str(grant.get("owner_user_id") or "").strip()
    recipient_user = str(grant.get("recipient_user_id") or "").strip()
    resource_root = str(grant.get("resource_root") or "").strip().lower()
    resource_kind = str(grant.get("resource_kind") or "").strip().lower()
    access_mode = _clean_share_access_mode(str(grant.get("access_mode") or ""), default="read")
    projection_read_only = _share_projection_read_only(access_mode, resource_kind)
    source_key = "vault" if resource_root == "vault" else "code_workspace"
    metadata = json_loads_safe(str(grant.get("metadata_json") or "{}"))
    if resource_kind == "pod_comms":
        metadata["projection"] = {
            "status": "not_applicable",
            "linked_root": "",
            "linked_path": "",
            "entry_path": "",
            "resource_kind": "pod_comms",
            "read_only": True,
        }
        return metadata
    if resource_kind == "notion":
        clean_path = str(grant.get("resource_path") or "").strip()
        projection = {
            "status": "materialized",
            "linked_root": "notion",
            "linked_path": clean_path,
            "entry_path": clean_path,
            "resource_kind": "notion",
            "owner_deployment_id": str(metadata.get("owner_deployment_id") or metadata.get("deployment_id") or ""),
            "recipient_deployment_id": str(metadata.get("recipient_deployment_id") or ""),
            "projection_mode": "ssot_inherited_subtree",
            "materialized_at": now,
            "inherited_subpages": bool(metadata.get("inherit_subpages", True)),
            "reason": "",
            "read_only": True,
        }
        metadata["projection"] = projection
        append_arclink_event(
            conn,
            subject_kind="share_grant",
            subject_id=grant_id,
            event_type="share_notion_subtree_materialized",
            metadata={
                "recipient_user_id": recipient_user,
                "resource_root": str(grant.get("resource_root") or ""),
                "resource_path": clean_path,
                "projection_mode": "ssot_inherited_subtree",
                "inherited_subpages": projection["inherited_subpages"],
            },
            commit=False,
        )
        return metadata
    owner_deployment = str(metadata.get("owner_deployment_id") or metadata.get("deployment_id") or "").strip()
    recipient_deployment = str(metadata.get("recipient_deployment_id") or "").strip()
    projection: dict[str, Any] = {
        "status": "not_materialized",
        "linked_root": "linked",
        "linked_path": "",
        "entry_path": "",
        "read_only": projection_read_only,
        "access_mode": access_mode,
    }
    linked_root: Path | None = None
    projection_root: Path | None = None
    try:
        owner_roots = _deployment_state_roots_for_user(conn, owner_user, deployment_id=owner_deployment)
        recipient_roots = _deployment_state_roots_for_user(conn, recipient_user, deployment_id=recipient_deployment)
        source_root_text = str(owner_roots.get(source_key) or "").strip()
        linked_root_text = str(recipient_roots.get("linked_resources") or "").strip()
        if not source_root_text or not linked_root_text:
            projection.update({"status": "pending_materialization", "reason": "deployment_roots_unavailable"})
            metadata["projection"] = projection
            return metadata

        source_root = Path(source_root_text).expanduser().resolve(strict=False)
        linked_root = Path(linked_root_text).expanduser().resolve(strict=False)
        clean_share_path = _clean_share_path(str(grant.get("resource_path") or ""))
        source = (source_root / clean_share_path.strip("/")).resolve(strict=False)
        if source != source_root and not _path_within(source_root, source):
            projection.update({"status": "blocked", "reason": "source_outside_owner_root"})
            metadata["projection"] = projection
            return metadata
        if _sensitive_share_projection_path(source):
            projection.update({"status": "blocked", "reason": "source_private"})
            metadata["projection"] = projection
            return metadata
        if not source.exists():
            projection.update({"status": "pending_materialization", "reason": "source_unavailable"})
            metadata["projection"] = projection
            return metadata
        if source.is_symlink():
            projection.update({"status": "blocked", "reason": "source_symlink"})
            metadata["projection"] = projection
            return metadata

        label = str(grant.get("display_name") or source.name or "linked-resource")
        slug = f"{_safe_projection_segment(grant_id, fallback='share')}-{_safe_projection_segment(label)}"
        projection_root = (linked_root / slug).resolve(strict=False)
        if projection_root != linked_root and not _path_within(linked_root, projection_root):
            projection.update({"status": "blocked", "reason": "projection_outside_linked_root"})
            metadata["projection"] = projection
            return metadata

        linked_root.mkdir(parents=True, exist_ok=True)
        _remove_projection_path(linked_root, projection_root)
        if source.is_file():
            projection_root.mkdir(parents=True, exist_ok=True)
            entry_path = projection_root / source.name
            os.symlink(str(source), str(entry_path), target_is_directory=False)
            if projection_read_only:
                _chmod_read_only(projection_root)
            linked_path = "/" + slug
            entry_display = f"/{slug}/{source.name}"
            resource_kind = "file"
        elif source.is_dir():
            os.symlink(str(source), str(projection_root), target_is_directory=True)
            linked_path = "/" + slug
            entry_display = linked_path
            resource_kind = "directory"
        else:
            projection.update({"status": "blocked", "reason": "source_not_file_or_directory"})
            metadata["projection"] = projection
            return metadata
        _upsert_linked_manifest_entry(
            linked_root,
            slug=slug,
            grant_id=grant_id,
            source=source,
            linked_path=linked_path,
            entry_path=entry_display,
            resource_kind=resource_kind,
            owner_user_id=owner_user,
            read_only=projection_read_only,
            access_mode=access_mode,
            updated_at=now,
        )

        projection.update(
            {
                "status": "materialized",
                "linked_path": linked_path,
                "entry_path": entry_display,
                "resource_kind": resource_kind,
                "owner_deployment_id": owner_deployment,
                "recipient_deployment_id": recipient_deployment,
                "projection_mode": "living_symlink",
                "materialized_at": now,
                "skipped_sensitive_count": 0,
                "reason": "",
                "read_only": projection_read_only,
                "access_mode": access_mode,
            }
        )
        metadata["projection"] = projection
        append_arclink_event(
            conn,
            subject_kind="share_grant",
            subject_id=grant_id,
            event_type="share_projection_materialized",
            metadata={
                "recipient_user_id": recipient_user,
                "linked_path": linked_path,
                "entry_path": entry_display,
                "resource_kind": resource_kind,
                "projection_mode": "living_symlink",
                "skipped_sensitive_count": 0,
            },
            commit=False,
        )
        return metadata
    except (OSError, ArcLinkApiAuthError, ValueError):
        if linked_root is not None and projection_root is not None:
            try:
                _remove_projection_path(linked_root, projection_root)
            except (OSError, ArcLinkApiAuthError, ValueError):
                pass
        projection.update({"status": "pending_materialization", "reason": "materialization_failed"})
        metadata["projection"] = projection
        append_arclink_event(
            conn,
            subject_kind="share_grant",
            subject_id=grant_id,
            event_type="share_projection_materialization_failed",
            metadata={"recipient_user_id": recipient_user, "reason": projection["reason"]},
            commit=False,
        )
        return metadata


def _remove_share_projection(
    conn: sqlite3.Connection,
    *,
    grant: Mapping[str, Any],
    now: str,
) -> dict[str, Any]:
    metadata = json_loads_safe(str(grant.get("metadata_json") or "{}"))
    if str(grant.get("resource_kind") or "").strip().lower() == "pod_comms":
        metadata["projection"] = {
            "status": "not_applicable",
            "linked_root": "",
            "linked_path": "",
            "entry_path": "",
            "resource_kind": "pod_comms",
            "removed_at": now,
            "read_only": True,
        }
        return metadata
    if str(grant.get("resource_kind") or "").strip().lower() == "notion":
        projection = metadata.get("projection")
        if not isinstance(projection, Mapping):
            projection = {
                "linked_root": "notion",
                "linked_path": str(grant.get("resource_path") or ""),
                "entry_path": str(grant.get("resource_path") or ""),
                "resource_kind": "notion",
                "projection_mode": "ssot_inherited_subtree",
                "inherited_subpages": bool(metadata.get("inherit_subpages", True)),
                "read_only": True,
            }
        updated_projection = dict(projection)
        updated_projection.update({"status": "removed", "removed_at": now, "read_only": True})
        metadata["projection"] = updated_projection
        append_arclink_event(
            conn,
            subject_kind="share_grant",
            subject_id=str(grant.get("grant_id") or ""),
            event_type="share_notion_subtree_removed",
            metadata={
                "recipient_user_id": str(grant.get("recipient_user_id") or ""),
                "resource_path": str(grant.get("resource_path") or ""),
            },
            commit=False,
        )
        return metadata
    projection = metadata.get("projection")
    if not isinstance(projection, Mapping):
        metadata["projection"] = {
            "status": "removed",
            "linked_root": "linked",
            "linked_path": "",
            "entry_path": "",
            "removed_at": now,
            "read_only": True,
        }
        return metadata

    linked_path = str(projection.get("linked_path") or "").strip()
    removed = False
    if linked_path.startswith("/"):
        recipient_user = str(grant.get("recipient_user_id") or "").strip()
        recipient_deployment = str(metadata.get("recipient_deployment_id") or "").strip()
        recipient_roots = _deployment_state_roots_for_user(conn, recipient_user, deployment_id=recipient_deployment)
        linked_root_text = str(recipient_roots.get("linked_resources") or "").strip()
        if linked_root_text:
            linked_root = Path(linked_root_text).expanduser().resolve(strict=False)
            target = linked_root / linked_path.strip("/")
            try:
                removed = _remove_projection_path(linked_root, target)
                slug = linked_path.strip("/").split("/", 1)[0]
                if slug:
                    _remove_linked_manifest_entry(linked_root, slug=slug)
            except (OSError, ArcLinkApiAuthError):
                removed = False
    updated_projection = dict(projection)
    updated_projection.update({"status": "removed", "removed_at": now, "read_only": True})
    metadata["projection"] = updated_projection
    append_arclink_event(
        conn,
        subject_kind="share_grant",
        subject_id=str(grant.get("grant_id") or ""),
        event_type="share_projection_removed",
        metadata={
            "recipient_user_id": str(grant.get("recipient_user_id") or ""),
            "linked_path": linked_path,
            "removed": removed,
        },
        commit=False,
    )
    return metadata


def create_user_share_grant_for_owner(
    conn: sqlite3.Connection,
    *,
    owner_user_id: str,
    recipient_user_id: str,
    resource_kind: str,
    resource_root: str,
    resource_path: str,
    owner_deployment_id: str = "",
    recipient_deployment_id: str = "",
    display_name: str = "",
    access_mode: str = "",
    metadata: Mapping[str, Any] | None = None,
    requested_by_agent_id: str = "",
) -> ArcLinkApiResponse:
    owner_user = str(owner_user_id or "").strip()
    recipient = str(recipient_user_id or "").strip()
    owner_deployment = str(owner_deployment_id or "").strip()
    recipient_deployment = str(recipient_deployment_id or "").strip()
    if not owner_user:
        raise ArcLinkApiAuthError("ArcLink share requires an owner user")
    if conn.execute("SELECT 1 FROM arclink_users WHERE user_id = ?", (owner_user,)).fetchone() is None:
        raise KeyError(owner_user)
    if owner_deployment:
        _share_deployment_user(conn, owner_deployment, expected_user_id=owner_user, label="owner")
    if recipient_deployment:
        recipient_for_deployment = _share_deployment_user(
            conn,
            recipient_deployment,
            expected_user_id=recipient,
            label="recipient",
        )
        recipient = recipient or recipient_for_deployment
    if not recipient:
        raise ArcLinkApiAuthError("ArcLink share requires a recipient user or recipient deployment")
    if conn.execute("SELECT 1 FROM arclink_users WHERE user_id = ?", (recipient,)).fetchone() is None:
        raise KeyError(recipient)
    same_account = recipient == owner_user
    if same_account:
        if not owner_deployment or not recipient_deployment:
            raise ArcLinkApiAuthError("ArcLink same-account share requires owner and recipient deployments")
        if owner_deployment == recipient_deployment:
            raise ArcLinkApiAuthError("ArcLink same-account share requires different owner and recipient deployments")
    kind = str(resource_kind or "").strip().lower()
    root = str(resource_root or "").strip().lower()
    mode = _clean_share_access_mode(access_mode, default="read_write" if kind in {"drive", "code"} else "read")
    if kind not in ARCLINK_SHARE_RESOURCE_KINDS:
        raise ArcLinkApiAuthError("ArcLink share requires a supported resource kind")
    if kind == "pod_comms":
        root = root or "pod_comms"
        if root != "pod_comms":
            raise ArcLinkApiAuthError("ArcLink Pod Comms grants require the pod_comms root")
        clean_path = str(resource_path or "*").strip() or "*"
        if clean_path not in {"*", "pod_comms"}:
            clean_path = _clean_share_path(clean_path)
    elif kind == "notion":
        root = root or "notion"
        if root not in ARCLINK_SHARE_NOTION_ROOTS:
            raise ArcLinkApiAuthError("ArcLink Notion shares require the notion or ssot root")
        clean_path = _clean_share_path(resource_path)
    elif root not in ARCLINK_SHARE_RESOURCE_ROOTS:
        raise ArcLinkApiAuthError("ArcLink share cannot originate from linked or unknown roots")
    else:
        clean_path = _clean_share_path(resource_path)
    if mode not in ARCLINK_SHARE_ACCESS_MODES:
        raise ArcLinkApiAuthError("ArcLink share grants support read or read_write access")
    if mode == "read_write" and kind not in {"drive", "code"}:
        raise ArcLinkApiAuthError("ArcLink read_write shares are limited to Drive and Code")
    safe_metadata = dict(metadata or {})
    if owner_deployment:
        safe_metadata["owner_deployment_id"] = owner_deployment
        safe_metadata.setdefault("deployment_id", owner_deployment)
    if recipient_deployment:
        safe_metadata["recipient_deployment_id"] = recipient_deployment
    if same_account:
        safe_metadata["same_account_share"] = True
    if kind == "notion":
        safe_metadata["inherit_subpages"] = bool(safe_metadata.get("inherit_subpages", True))
        safe_metadata.setdefault("notion_share_model", "brokered_ssot_subtree")
    clean_agent = str(requested_by_agent_id or "").strip()
    if clean_agent:
        safe_metadata["requested_by_agent_id"] = clean_agent
    _reject_secret_material(safe_metadata)
    now = utc_now_iso()
    expires_at = utc_after_seconds_iso(ARCLINK_SHARE_GRANT_TTL_SECONDS)
    grant_id = _new_id("share")
    initial_status = "accepted" if same_account else "pending_owner_approval"
    approved_at = now if same_account else ""
    accepted_at = now if same_account else ""
    conn.execute(
        """
        INSERT INTO arclink_share_grants (
          grant_id, owner_user_id, recipient_user_id, resource_kind, resource_root,
          resource_path, display_name, access_mode, status, expires_at, approved_at, accepted_at,
          metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            grant_id,
            owner_user,
            recipient,
            kind,
            root,
            clean_path,
            str(display_name or "").strip()[:160],
            mode,
            initial_status,
            expires_at,
            approved_at,
            accepted_at,
            _json(safe_metadata),
            now,
            now,
        ),
    )
    audit_metadata = {
        "recipient_user_id": recipient,
        "resource_kind": kind,
        "resource_root": root,
        "resource_path": clean_path,
    }
    if owner_deployment:
        audit_metadata["owner_deployment_id"] = owner_deployment
    if recipient_deployment:
        audit_metadata["recipient_deployment_id"] = recipient_deployment
    if same_account:
        audit_metadata["same_account_share"] = True
    if clean_agent:
        audit_metadata["requested_by_agent_id"] = clean_agent
    append_arclink_audit(
        conn,
        action="share_grant_requested",
        actor_id=owner_user,
        target_kind="share_grant",
        target_id=grant_id,
        reason="linked resource share requested",
        metadata=audit_metadata,
        commit=False,
    )
    grant = rowdict(conn.execute("SELECT * FROM arclink_share_grants WHERE grant_id = ?", (grant_id,)).fetchone())
    if same_account:
        updated_metadata = _materialize_share_projection(conn, grant=grant, now=now)
        conn.execute(
            """
            UPDATE arclink_share_grants
            SET metadata_json = ?, updated_at = ?
            WHERE grant_id = ?
            """,
            (_json(updated_metadata), now, grant_id),
        )
        append_arclink_audit(
            conn,
            action="share_grant_auto_accepted",
            actor_id=owner_user,
            target_kind="share_grant",
            target_id=grant_id,
            reason="same-account linked resource share auto-accepted",
            metadata={
                "owner_deployment_id": owner_deployment,
                "recipient_deployment_id": recipient_deployment,
                "resource_kind": kind,
                "resource_root": root,
                "resource_path": clean_path,
            },
            commit=False,
        )
        append_arclink_event(
            conn,
            subject_kind="share_grant",
            subject_id=grant_id,
            event_type="share_grant_auto_accepted",
            metadata={
                "owner_user_id": owner_user,
                "owner_deployment_id": owner_deployment,
                "recipient_deployment_id": recipient_deployment,
            },
            commit=False,
        )
        conn.commit()
        grant = rowdict(conn.execute("SELECT * FROM arclink_share_grants WHERE grant_id = ?", (grant_id,)).fetchone())
        owner_notification = {"queued": False, "reason": "same_account_auto_accepted"}
    else:
        conn.commit()
        owner_notification = _queue_share_grant_owner_notification(conn, grant=grant)
    return ArcLinkApiResponse(
        status=201,
        payload={
            "grant": _public_share_grant(grant),
            "owner_notification": owner_notification,
        },
    )


def create_user_share_grant_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
    recipient_user_id: str,
    resource_kind: str,
    resource_root: str,
    resource_path: str,
    owner_deployment_id: str = "",
    recipient_deployment_id: str = "",
    display_name: str = "",
    access_mode: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> ArcLinkApiResponse:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    require_arclink_csrf(conn, session_id=session_id, csrf_token=csrf_token, session_kind="user")
    return create_user_share_grant_for_owner(
        conn,
        owner_user_id=str(session["user_id"] or ""),
        recipient_user_id=recipient_user_id,
        resource_kind=resource_kind,
        resource_root=resource_root,
        resource_path=resource_path,
        owner_deployment_id=owner_deployment_id,
        recipient_deployment_id=recipient_deployment_id,
        display_name=display_name,
        access_mode=access_mode,
        metadata=metadata,
    )


def create_user_share_grant_from_broker_api(
    conn: sqlite3.Connection,
    *,
    broker_token: str,
    owner_deployment_id: str,
    recipient_user_id: str = "",
    recipient: str = "",
    recipient_deployment_id: str = "",
    resource_kind: str = "",
    resource_root: str = "",
    resource_path: str = "",
    display_name: str = "",
    access_mode: str = "",
    requested_access: str = "",
    source_plugin: str = "",
    item_kind: str = "",
    contract: str = "",
    share_mode: str = "",
    reshare_allowed: Any = False,
    metadata: Mapping[str, Any] | None = None,
) -> ArcLinkApiResponse:
    if str(contract or "").strip() != "arclink-share-grants":
        raise ArcLinkApiAuthError("ArcLink share-request broker contract is invalid")
    clean_share_mode = str(share_mode or "owner_approval").strip() or "owner_approval"
    if clean_share_mode not in {"owner_approval", "claim_nonce"}:
        raise ArcLinkApiAuthError("ArcLink share-request broker only supports owner approval or claim nonce")
    if bool(reshare_allowed):
        raise ArcLinkApiAuthError("ArcLink share grants cannot be reshared")
    source = str(source_plugin or "").strip().lower()
    if source not in {"drive", "code"}:
        raise ArcLinkApiAuthError("ArcLink share-request broker requires a supported source plugin")
    owner = _authenticate_share_request_broker(
        conn,
        owner_deployment_id=owner_deployment_id,
        broker_token=broker_token,
    )
    clean_owner_deployment = str(owner["deployment_id"] or "")
    raw_kind = str(resource_kind or "").strip().lower()
    clean_item_kind = str(item_kind or "").strip().lower()
    if raw_kind in {"file", "directory"} and not clean_item_kind:
        clean_item_kind = raw_kind
    clean_resource_kind = raw_kind if raw_kind in ARCLINK_SHARE_RESOURCE_KINDS else source
    if clean_resource_kind != source:
        raise ArcLinkApiAuthError("ArcLink share-request broker source and resource kind do not match")
    if clean_item_kind and clean_item_kind not in {"file", "directory"}:
        raise ArcLinkApiAuthError("ArcLink share-request broker item kind is unsupported")
    clean_access = _clean_share_access_mode(access_mode or requested_access)
    if clean_share_mode == "claim_nonce":
        nonce_metadata = dict(metadata or {})
        if clean_item_kind:
            nonce_metadata["item_kind"] = clean_item_kind
        return mint_share_claim_nonce_for_owner(
            conn,
            owner_user_id=str(owner["user_id"] or ""),
            owner_deployment_id=clean_owner_deployment,
            resource_kind=clean_resource_kind,
            resource_root=resource_root,
            resource_path=resource_path,
            display_name=display_name,
            access_mode=clean_access,
            source_plugin=source,
            metadata=nonce_metadata,
        )
    recipient_user = _resolve_share_recipient_user_id(
        conn,
        recipient_user_id=recipient_user_id,
        recipient_identity=recipient,
        recipient_deployment_id=recipient_deployment_id,
    )
    broker_metadata = dict(metadata or {})
    broker_metadata.update(
        {
            "requested_via": "share_request_broker",
            "source_plugin": source,
            "share_mode": "owner_approval",
            "reshare_allowed": False,
        }
    )
    if clean_item_kind:
        broker_metadata["item_kind"] = clean_item_kind
    return create_user_share_grant_for_owner(
        conn,
        owner_user_id=str(owner["user_id"] or ""),
        recipient_user_id=recipient_user,
        resource_kind=clean_resource_kind,
        resource_root=resource_root,
        resource_path=resource_path,
        owner_deployment_id=clean_owner_deployment,
        recipient_deployment_id=recipient_deployment_id,
        display_name=display_name,
        access_mode=clean_access,
        metadata=broker_metadata,
    )


def _validate_drive_code_share(resource_kind: str, resource_root: str, resource_path: str) -> tuple[str, str, str]:
    kind = str(resource_kind or "").strip().lower()
    root = str(resource_root or "").strip().lower()
    if kind not in {"drive", "code"}:
        raise ArcLinkApiAuthError("ArcLink claim-nonce shares support only Drive and Code resources")
    if root not in ARCLINK_SHARE_RESOURCE_ROOTS:
        raise ArcLinkApiAuthError("ArcLink share cannot originate from linked or unknown roots")
    return kind, root, _clean_share_path(resource_path)


def _generate_share_claim_nonce() -> str:
    return f"{ARCLINK_SHARE_CLAIM_NONCE_PREFIX}{secrets.token_hex(24)}"


def _share_claim_accept_command(nonce: str) -> str:
    return f"/arclink_share_accept {nonce}"


def _share_claim_copy_text(nonce: str) -> str:
    return "A share request is available for review by Raven:\n" + _share_claim_accept_command(nonce)


def _public_share_claim_nonce(row: Mapping[str, Any]) -> dict[str, Any]:
    """Sanitized view of a claim nonce. Never includes the nonce value or its hash."""
    return {
        "nonce_id": str(row.get("nonce_id") or ""),
        "owner_user_id": str(row.get("owner_user_id") or ""),
        "owner_deployment_id": str(row.get("owner_deployment_id") or ""),
        "resource_kind": str(row.get("resource_kind") or ""),
        "resource_root": str(row.get("resource_root") or ""),
        "resource_path": str(row.get("resource_path") or ""),
        "display_name": str(row.get("display_name") or ""),
        "access_mode": str(row.get("access_mode") or ""),
        "status": str(row.get("status") or ""),
        "expires_at": str(row.get("expires_at") or ""),
        "claimed_by_user_id": str(row.get("claimed_by_user_id") or ""),
        "claimed_grant_id": str(row.get("claimed_grant_id") or ""),
        "claimed_at": str(row.get("claimed_at") or ""),
        "revoked_at": str(row.get("revoked_at") or ""),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def mint_share_claim_nonce_for_owner(
    conn: sqlite3.Connection,
    *,
    owner_user_id: str,
    resource_kind: str,
    resource_root: str,
    resource_path: str,
    owner_deployment_id: str = "",
    display_name: str = "",
    access_mode: str = "read_write",
    source_plugin: str = "",
    metadata: Mapping[str, Any] | None = None,
    requested_by_agent_id: str = "",
) -> ArcLinkApiResponse:
    """Mint a single-use, 12h share claim nonce.

    Minting *is* the owner's approval: whoever the owner hands the nonce to can
    claim a Linked resource by running ``/arclink_share_accept <nonce>``.
    """
    owner_user = str(owner_user_id or "").strip()
    if not owner_user:
        raise ArcLinkApiAuthError("ArcLink claim-nonce share requires an owner user")
    if conn.execute("SELECT 1 FROM arclink_users WHERE user_id = ?", (owner_user,)).fetchone() is None:
        raise KeyError(owner_user)
    owner_deployment = str(owner_deployment_id or "").strip()
    if owner_deployment:
        _share_deployment_user(conn, owner_deployment, expected_user_id=owner_user, label="owner")
    kind, root, clean_path = _validate_drive_code_share(resource_kind, resource_root, resource_path)
    mode = _clean_share_access_mode(access_mode)
    if mode not in ARCLINK_SHARE_ACCESS_MODES:
        raise ArcLinkApiAuthError("ArcLink share grants support read or read_write access")
    if mode == "read_write" and kind not in {"drive", "code"}:
        raise ArcLinkApiAuthError("ArcLink read_write shares are limited to Drive and Code")
    safe_metadata = dict(metadata or {})
    if source_plugin:
        safe_metadata["source_plugin"] = str(source_plugin).strip().lower()
    safe_metadata["requested_via"] = "claim_nonce"
    safe_metadata["share_mode"] = "claim_nonce"
    safe_metadata["reshare_allowed"] = False
    clean_agent = str(requested_by_agent_id or "").strip()
    if clean_agent:
        safe_metadata["requested_by_agent_id"] = clean_agent
    _reject_secret_material(safe_metadata)
    now = utc_now_iso()
    expires_at = utc_after_seconds_iso(ARCLINK_SHARE_CLAIM_NONCE_TTL_SECONDS)
    nonce = _generate_share_claim_nonce()
    nonce_id = _new_id("snonce")
    display = str(display_name or "").strip()[:160]
    conn.execute(
        """
        INSERT INTO arclink_share_claim_nonces (
          nonce_id, nonce_hash, owner_user_id, owner_deployment_id, resource_kind, resource_root,
          resource_path, display_name, access_mode, status, expires_at, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
        """,
        (
            nonce_id,
            _hash_proof_token(nonce),
            owner_user,
            owner_deployment,
            kind,
            root,
            clean_path,
            display,
            mode,
            expires_at,
            _json(safe_metadata),
            now,
            now,
        ),
    )
    append_arclink_audit(
        conn,
        action="share_claim_nonce_minted",
        actor_id=owner_user,
        target_kind="share_claim_nonce",
        target_id=nonce_id,
        reason="owner minted single-use share claim nonce",
        metadata={
            "resource_kind": kind,
            "resource_root": root,
            "resource_path": clean_path,
            "owner_deployment_id": owner_deployment,
            "expires_at": expires_at,
        },
        commit=False,
    )
    append_arclink_event(
        conn,
        subject_kind="share_claim_nonce",
        subject_id=nonce_id,
        event_type="share_claim_nonce_minted",
        metadata={"owner_user_id": owner_user, "resource_kind": kind, "resource_root": root},
        commit=False,
    )
    conn.commit()
    return ArcLinkApiResponse(
        status=201,
        payload={
            "ok": True,
            "mode": "claim_nonce",
            "broker": "arclink-share-grants",
            "nonce": nonce,
            "nonce_id": nonce_id,
            "accept_command": _share_claim_accept_command(nonce),
            "copy_text": _share_claim_copy_text(nonce),
            "expires_at": expires_at,
            "expires_in_seconds": ARCLINK_SHARE_CLAIM_NONCE_TTL_SECONDS,
            "expires_in_hours": ARCLINK_SHARE_CLAIM_NONCE_TTL_SECONDS // 3600,
            "resource_kind": kind,
            "resource_root": root,
            "resource_path": clean_path,
            "display_name": display,
            "access_mode": mode,
            "reshare_allowed": False,
        },
    )


def _insert_accepted_share_grant(
    conn: sqlite3.Connection,
    *,
    grant_id: str,
    owner_user: str,
    recipient_user: str,
    resource_kind: str,
    resource_root: str,
    resource_path: str,
    display_name: str,
    access_mode: str,
    metadata: Mapping[str, Any],
    now: str,
    actor_id: str,
    audit_reason: str,
) -> dict[str, Any]:
    """Insert an already-accepted share grant and materialize its projection.

    Used by the claim-nonce flow, where minting the nonce was the owner's approval.
    """
    kind, root, clean_path = _validate_drive_code_share(resource_kind, resource_root, resource_path)
    mode = _clean_share_access_mode(access_mode)
    if mode not in ARCLINK_SHARE_ACCESS_MODES:
        raise ArcLinkApiAuthError("ArcLink share grants support read or read_write access")
    if mode == "read_write" and kind not in {"drive", "code"}:
        raise ArcLinkApiAuthError("ArcLink read_write shares are limited to Drive and Code")
    safe_metadata = dict(metadata or {})
    _reject_secret_material(safe_metadata)
    conn.execute(
        """
        INSERT INTO arclink_share_grants (
          grant_id, owner_user_id, recipient_user_id, resource_kind, resource_root,
          resource_path, display_name, access_mode, status, expires_at, approved_at, accepted_at,
          metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'accepted', ?, ?, ?, ?, ?, ?)
        """,
        (
            grant_id,
            owner_user,
            recipient_user,
            kind,
            root,
            clean_path,
            str(display_name or "").strip()[:160],
            mode,
            utc_after_seconds_iso(ARCLINK_SHARE_GRANT_TTL_SECONDS),
            now,
            now,
            _json(safe_metadata),
            now,
            now,
        ),
    )
    append_arclink_audit(
        conn,
        action="share_grant_requested",
        actor_id=owner_user,
        target_kind="share_grant",
        target_id=grant_id,
        reason="claim-nonce linked resource share created",
        metadata={
            "recipient_user_id": recipient_user,
            "resource_kind": kind,
            "resource_root": root,
            "resource_path": clean_path,
        },
        commit=False,
    )
    grant = rowdict(conn.execute("SELECT * FROM arclink_share_grants WHERE grant_id = ?", (grant_id,)).fetchone())
    updated_metadata = _materialize_share_projection(conn, grant=grant, now=now)
    conn.execute(
        "UPDATE arclink_share_grants SET metadata_json = ?, updated_at = ? WHERE grant_id = ?",
        (_json(updated_metadata), now, grant_id),
    )
    append_arclink_audit(
        conn,
        action="share_grant_accepted",
        actor_id=str(actor_id or recipient_user).strip(),
        target_kind="share_grant",
        target_id=grant_id,
        reason=audit_reason,
        commit=False,
    )
    append_arclink_event(
        conn,
        subject_kind="share_grant",
        subject_id=grant_id,
        event_type="share_grant_accepted",
        metadata={"recipient_user_id": recipient_user, "via": "claim_nonce"},
        commit=False,
    )
    return rowdict(conn.execute("SELECT * FROM arclink_share_grants WHERE grant_id = ?", (grant_id,)).fetchone())


def claim_share_nonce_for_recipient(
    conn: sqlite3.Connection,
    *,
    recipient_user_id: str,
    nonce: str,
    recipient_deployment_id: str = "",
    actor_id: str = "",
    reason: str = "recipient claimed linked resource via share nonce",
    commit: bool = True,
) -> dict[str, Any]:
    recipient = str(recipient_user_id or "").strip()
    if not recipient:
        raise ArcLinkApiAuthError("ArcLink share claim requires a recipient user")
    clean_nonce = str(nonce or "").strip()
    invalid = ArcLinkApiAuthError("ArcLink share link is invalid or has expired")
    if not clean_nonce.startswith(ARCLINK_SHARE_CLAIM_NONCE_PREFIX):
        raise invalid
    row = conn.execute(
        "SELECT * FROM arclink_share_claim_nonces WHERE nonce_hash = ?",
        (_hash_proof_token(clean_nonce),),
    ).fetchone()
    if row is None:
        raise invalid
    nonce_row = rowdict(row)
    now = utc_now_iso()
    status = str(nonce_row.get("status") or "")
    expires_at = parse_utc_iso(str(nonce_row.get("expires_at") or ""))
    now_dt = parse_utc_iso(now)
    if status == "pending" and expires_at is not None and now_dt is not None and expires_at <= now_dt:
        conn.execute(
            "UPDATE arclink_share_claim_nonces SET status = 'expired', updated_at = ? WHERE nonce_id = ? AND status = 'pending'",
            (now, str(nonce_row.get("nonce_id") or "")),
        )
        conn.commit()
        raise invalid
    if status != "pending":
        raise invalid
    if conn.execute("SELECT 1 FROM arclink_users WHERE user_id = ?", (recipient,)).fetchone() is None:
        raise KeyError(recipient)
    recipient_deployment = str(recipient_deployment_id or "").strip()
    if recipient_deployment:
        resolved = _share_deployment_user(conn, recipient_deployment, expected_user_id=recipient, label="recipient")
        recipient = recipient or resolved
    owner_user = str(nonce_row.get("owner_user_id") or "")
    owner_deployment = str(nonce_row.get("owner_deployment_id") or "")
    nonce_metadata = json_loads_safe(str(nonce_row.get("metadata_json") or "{}"))
    grant_metadata: dict[str, Any] = {
        "requested_via": "claim_nonce",
        "share_mode": "claim_nonce",
        "reshare_allowed": False,
        "claim_nonce_id": str(nonce_row.get("nonce_id") or ""),
    }
    if str(nonce_metadata.get("source_plugin") or ""):
        grant_metadata["source_plugin"] = str(nonce_metadata.get("source_plugin") or "")
    if str(nonce_metadata.get("item_kind") or ""):
        grant_metadata["item_kind"] = str(nonce_metadata.get("item_kind") or "")
    if owner_deployment:
        grant_metadata["owner_deployment_id"] = owner_deployment
        grant_metadata.setdefault("deployment_id", owner_deployment)
    if recipient_deployment:
        grant_metadata["recipient_deployment_id"] = recipient_deployment
    grant_id = _new_id("share")
    # Claim the nonce atomically before creating the grant so it can only be spent once.
    claimed = conn.execute(
        """
        UPDATE arclink_share_claim_nonces
        SET status = 'claimed', claimed_grant_id = ?, claimed_by_user_id = ?, claimed_at = ?, updated_at = ?
        WHERE nonce_id = ? AND status = 'pending'
        """,
        (grant_id, recipient, now, now, str(nonce_row.get("nonce_id") or "")),
    )
    if claimed.rowcount != 1:
        raise invalid
    try:
        grant = _insert_accepted_share_grant(
            conn,
            grant_id=grant_id,
            owner_user=owner_user,
            recipient_user=recipient,
            resource_kind=str(nonce_row.get("resource_kind") or ""),
            resource_root=str(nonce_row.get("resource_root") or ""),
            resource_path=str(nonce_row.get("resource_path") or ""),
            display_name=str(nonce_row.get("display_name") or ""),
            access_mode=str(nonce_row.get("access_mode") or "read"),
            metadata=grant_metadata,
            now=now,
            actor_id=str(actor_id or recipient),
            audit_reason=reason,
        )
        append_arclink_event(
            conn,
            subject_kind="share_claim_nonce",
            subject_id=str(nonce_row.get("nonce_id") or ""),
            event_type="share_claim_nonce_claimed",
            metadata={"recipient_user_id": recipient, "grant_id": grant_id},
            commit=False,
        )
        if commit:
            conn.commit()
    except Exception:
        if commit:
            conn.rollback()
        raise
    return _public_share_grant(grant)


def claim_user_share_nonce_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
    nonce: str,
) -> ArcLinkApiResponse:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    require_arclink_csrf(conn, session_id=session_id, csrf_token=csrf_token, session_kind="user")
    expire_revealable_user_material(conn)
    recipient = str(session["user_id"] or "")
    grant = claim_share_nonce_for_recipient(conn, recipient_user_id=recipient, nonce=nonce, actor_id=recipient)
    return ArcLinkApiResponse(status=200, payload={"grant": grant})


def revoke_share_claim_nonce_for_owner(
    conn: sqlite3.Connection,
    *,
    owner_user_id: str,
    nonce_id: str,
    commit: bool = True,
) -> dict[str, Any]:
    """Owner-revoke a minted-but-unclaimed share nonce so it can no longer be claimed.

    Gives the owner recourse inside the 12h window (mistaken mint / wrong person).
    Idempotent for an already-revoked nonce; a claimed/expired nonce is not revocable.
    """
    owner = str(owner_user_id or "").strip()
    clean_nonce_id = str(nonce_id or "").strip()
    if not owner or not clean_nonce_id:
        raise ArcLinkApiAuthError("ArcLink share nonce revoke requires an owner and nonce id")
    row = conn.execute(
        "SELECT * FROM arclink_share_claim_nonces WHERE nonce_id = ?",
        (clean_nonce_id,),
    ).fetchone()
    if row is None or str(row["owner_user_id"] or "") != owner:
        raise ArcLinkApiAuthError("ArcLink user cannot revoke this share nonce")
    status = str(row["status"] or "")
    if status == "revoked":
        return _public_share_claim_nonce(rowdict(row))
    if status != "pending":
        raise ArcLinkApiAuthError("ArcLink share nonce is not revocable")
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE arclink_share_claim_nonces
        SET status = 'revoked',
            revoked_at = CASE WHEN revoked_at = '' THEN ? ELSE revoked_at END,
            updated_at = ?
        WHERE nonce_id = ? AND owner_user_id = ? AND status = 'pending'
        """,
        (now, now, clean_nonce_id, owner),
    )
    append_arclink_audit(
        conn,
        action="share_claim_nonce_revoked",
        actor_id=owner,
        target_kind="share_claim_nonce",
        target_id=clean_nonce_id,
        reason="owner revoked an unclaimed share nonce",
        commit=False,
    )
    append_arclink_event(
        conn,
        subject_kind="share_claim_nonce",
        subject_id=clean_nonce_id,
        event_type="share_claim_nonce_revoked",
        metadata={"owner_user_id": owner},
        commit=False,
    )
    if commit:
        conn.commit()
    return _public_share_claim_nonce(rowdict(conn.execute("SELECT * FROM arclink_share_claim_nonces WHERE nonce_id = ?", (clean_nonce_id,)).fetchone()))


def revoke_user_share_nonce_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
    nonce_id: str,
) -> ArcLinkApiResponse:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    require_arclink_csrf(conn, session_id=session_id, csrf_token=csrf_token, session_kind="user")
    expire_revealable_user_material(conn)
    owner = str(session["user_id"] or "")
    nonce = revoke_share_claim_nonce_for_owner(conn, owner_user_id=owner, nonce_id=nonce_id)
    return ArcLinkApiResponse(status=200, payload={"nonce": nonce})


def approve_user_share_grant_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
    grant_id: str,
) -> ArcLinkApiResponse:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    require_arclink_csrf(conn, session_id=session_id, csrf_token=csrf_token, session_kind="user")
    expire_revealable_user_material(conn)
    owner_user = str(session["user_id"] or "")
    clean_grant = str(grant_id or "").strip()
    row = conn.execute("SELECT * FROM arclink_share_grants WHERE grant_id = ?", (clean_grant,)).fetchone()
    if row is None or str(row["owner_user_id"] or "") != owner_user:
        raise ArcLinkApiAuthError("ArcLink user session cannot approve another user's share")
    if str(row["status"] or "") != "pending_owner_approval":
        raise ArcLinkApiAuthError("ArcLink share is not awaiting owner approval")
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE arclink_share_grants
        SET status = 'approved', approved_at = ?, updated_at = ?
        WHERE grant_id = ? AND owner_user_id = ?
        """,
        (now, now, clean_grant, owner_user),
    )
    append_arclink_audit(
        conn,
        action="share_grant_approved",
        actor_id=owner_user,
        target_kind="share_grant",
        target_id=clean_grant,
        reason="owner approved linked resource share",
        commit=False,
    )
    conn.commit()
    grant = rowdict(conn.execute("SELECT * FROM arclink_share_grants WHERE grant_id = ?", (clean_grant,)).fetchone())
    recipient_notification = queue_share_grant_recipient_notification(conn, grant=grant)
    return ArcLinkApiResponse(status=200, payload={"grant": _public_share_grant(grant), "recipient_notification": recipient_notification})


def deny_user_share_grant_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
    grant_id: str,
) -> ArcLinkApiResponse:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    require_arclink_csrf(conn, session_id=session_id, csrf_token=csrf_token, session_kind="user")
    expire_revealable_user_material(conn)
    owner_user = str(session["user_id"] or "")
    clean_grant = str(grant_id or "").strip()
    row = conn.execute("SELECT * FROM arclink_share_grants WHERE grant_id = ?", (clean_grant,)).fetchone()
    if row is None or str(row["owner_user_id"] or "") != owner_user:
        raise ArcLinkApiAuthError("ArcLink user session cannot deny another user's share")
    if str(row["status"] or "") != "pending_owner_approval":
        raise ArcLinkApiAuthError("ArcLink share is not awaiting owner approval")
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE arclink_share_grants
        SET status = 'denied', updated_at = ?
        WHERE grant_id = ? AND owner_user_id = ?
        """,
        (now, clean_grant, owner_user),
    )
    append_arclink_audit(
        conn,
        action="share_grant_denied",
        actor_id=owner_user,
        target_kind="share_grant",
        target_id=clean_grant,
        reason="owner denied linked resource share",
        commit=False,
    )
    conn.commit()
    grant = rowdict(conn.execute("SELECT * FROM arclink_share_grants WHERE grant_id = ?", (clean_grant,)).fetchone())
    return ArcLinkApiResponse(status=200, payload={"grant": _public_share_grant(grant)})


def accept_share_grant_for_recipient(
    conn: sqlite3.Connection,
    *,
    recipient_user_id: str,
    grant_id: str,
    actor_id: str = "",
    reason: str = "recipient accepted linked resource",
    commit: bool = True,
) -> dict[str, Any]:
    recipient = str(recipient_user_id or "").strip()
    clean_grant = str(grant_id or "").strip()
    row = conn.execute("SELECT * FROM arclink_share_grants WHERE grant_id = ?", (clean_grant,)).fetchone()
    if row is None or str(row["recipient_user_id"] or "") != recipient:
        raise ArcLinkApiAuthError("ArcLink user session cannot accept another user's share")
    if str(row["status"] or "") == "accepted":
        return _public_share_grant(rowdict(row))
    if str(row["status"] or "") != "approved":
        raise ArcLinkApiAuthError("ArcLink share is not ready to accept")
    now = utc_now_iso()
    updated_metadata = _materialize_share_projection(conn, grant=rowdict(row), now=now)
    conn.execute(
        """
        UPDATE arclink_share_grants
        SET status = 'accepted', accepted_at = ?, metadata_json = ?, updated_at = ?
        WHERE grant_id = ? AND recipient_user_id = ?
        """,
        (now, _json(updated_metadata), now, clean_grant, recipient),
    )
    append_arclink_audit(
        conn,
        action="share_grant_accepted",
        actor_id=str(actor_id or recipient).strip(),
        target_kind="share_grant",
        target_id=clean_grant,
        reason=reason,
        commit=False,
    )
    if commit:
        conn.commit()
    grant = rowdict(conn.execute("SELECT * FROM arclink_share_grants WHERE grant_id = ?", (clean_grant,)).fetchone())
    return _public_share_grant(grant)


def accept_user_share_grant_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
    grant_id: str,
) -> ArcLinkApiResponse:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    require_arclink_csrf(conn, session_id=session_id, csrf_token=csrf_token, session_kind="user")
    expire_revealable_user_material(conn)
    recipient = str(session["user_id"] or "")
    grant = accept_share_grant_for_recipient(conn, recipient_user_id=recipient, grant_id=grant_id, actor_id=recipient)
    return ArcLinkApiResponse(status=200, payload={"grant": grant})


def revoke_user_share_grant_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
    grant_id: str,
) -> ArcLinkApiResponse:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    require_arclink_csrf(conn, session_id=session_id, csrf_token=csrf_token, session_kind="user")
    expire_revealable_user_material(conn)
    owner_user = str(session["user_id"] or "")
    clean_grant = str(grant_id or "").strip()
    row = conn.execute("SELECT * FROM arclink_share_grants WHERE grant_id = ?", (clean_grant,)).fetchone()
    if row is None or str(row["owner_user_id"] or "") != owner_user:
        raise ArcLinkApiAuthError("ArcLink user session cannot revoke another user's share")
    status = str(row["status"] or "")
    if status == "denied":
        raise ArcLinkApiAuthError("ArcLink share is already denied")
    if status == "revoked":
        grant = rowdict(row)
        return ArcLinkApiResponse(status=200, payload={"grant": _public_share_grant(grant)})
    if status not in {"pending_owner_approval", "approved", "accepted"}:
        raise ArcLinkApiAuthError("ArcLink share is not revocable")
    now = utc_now_iso()
    updated_metadata = _remove_share_projection(conn, grant=rowdict(row), now=now)
    conn.execute(
        """
        UPDATE arclink_share_grants
        SET status = 'revoked',
            revoked_at = CASE WHEN revoked_at = '' THEN ? ELSE revoked_at END,
            metadata_json = ?,
            updated_at = ?
        WHERE grant_id = ? AND owner_user_id = ?
        """,
        (now, _json(updated_metadata), now, clean_grant, owner_user),
    )
    append_arclink_audit(
        conn,
        action="share_grant_revoked",
        actor_id=owner_user,
        target_kind="share_grant",
        target_id=clean_grant,
        reason="owner revoked linked resource share",
        metadata={"previous_status": status},
        commit=False,
    )
    append_arclink_event(
        conn,
        subject_kind="share_grant",
        subject_id=clean_grant,
        event_type="share_grant_revoked",
        metadata={"owner_user_id": owner_user, "recipient_user_id": str(row["recipient_user_id"] or ""), "previous_status": status},
        commit=False,
    )
    conn.commit()
    grant = rowdict(conn.execute("SELECT * FROM arclink_share_grants WHERE grant_id = ?", (clean_grant,)).fetchone())
    return ArcLinkApiResponse(status=200, payload={"grant": _public_share_grant(grant)})


def _share_grant_retry_target(grant: Mapping[str, Any], target: str) -> tuple[str, str]:
    clean_target = str(target or "auto").strip().lower() or "auto"
    if clean_target not in {"auto", "owner", "recipient"}:
        raise ArcLinkApiAuthError("ArcLink share notification retry target must be auto, owner, or recipient")
    status = str(grant.get("status") or "")
    expected = ""
    if status == "pending_owner_approval":
        expected = "owner"
    elif status == "approved":
        expected = "recipient"
    if not expected:
        return "", f"share_status_{status or 'unknown'}_not_retryable"
    if clean_target != "auto" and clean_target != expected:
        return "", f"{clean_target}_notification_not_waiting"
    return expected, ""


def retry_user_share_grant_notification_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
    grant_id: str,
    target: str = "auto",
) -> ArcLinkApiResponse:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    require_arclink_csrf(conn, session_id=session_id, csrf_token=csrf_token, session_kind="user")
    expire_revealable_user_material(conn)
    actor_user = str(session["user_id"] or "").strip()
    clean_grant = str(grant_id or "").strip()
    row = conn.execute("SELECT * FROM arclink_share_grants WHERE grant_id = ?", (clean_grant,)).fetchone()
    if row is None:
        raise ArcLinkApiAuthError("ArcLink share notification retry is not available")
    grant = rowdict(row)
    owner_user = str(grant.get("owner_user_id") or "").strip()
    recipient_user = str(grant.get("recipient_user_id") or "").strip()
    if actor_user not in {owner_user, recipient_user}:
        raise ArcLinkApiAuthError("ArcLink user session cannot retry another user's share notification")

    retry_target, blocked_reason = _share_grant_retry_target(grant, target)
    public_grant = _public_share_grant_for_viewer(conn, grant, viewer_user_id=actor_user)
    if blocked_reason:
        return ArcLinkApiResponse(
            status=200,
            payload={
                "grant": public_grant,
                "notification": {
                    "queued": False,
                    "target": retry_target,
                    "reason": blocked_reason,
                    "recovery_action": "",
                },
            },
        )

    target_user = owner_user if retry_target == "owner" else recipient_user
    channel_hint = _share_public_channel_hint(_share_public_channel_for_user(conn, target_user))
    if not channel_hint["queued_possible"]:
        return ArcLinkApiResponse(
            status=200,
            payload={
                "grant": public_grant,
                "notification": {
                    "queued": False,
                    "target": retry_target,
                    "reason": str(channel_hint.get("reason") or "no_public_channel"),
                    "channel": "",
                    "recovery_action": str(channel_hint.get("recovery_action") or "use_dashboard_or_link_public_channel"),
                },
            },
        )

    if retry_target == "owner":
        notification = _queue_share_grant_owner_notification(conn, grant=grant)
    else:
        notification = queue_share_grant_recipient_notification(conn, grant=grant)
    notification = dict(notification)
    notification["target"] = retry_target
    if notification.get("queued"):
        append_arclink_audit(
            conn,
            action="share_grant_notification_retried",
            actor_id=actor_user,
            target_kind="share_grant",
            target_id=clean_grant,
            reason=f"{retry_target} notification retry queued",
            metadata={
                "target": retry_target,
                "target_user_id": target_user,
                "channel": str(notification.get("channel") or ""),
                "notification_id": notification.get("notification_id"),
                "share_status": str(grant.get("status") or ""),
            },
            commit=False,
        )
        append_arclink_event(
            conn,
            subject_kind="share_grant",
            subject_id=clean_grant,
            event_type="share_grant_notification_retry_queued",
            metadata={
                "actor_user_id": actor_user,
                "target": retry_target,
                "target_user_id": target_user,
                "channel": str(notification.get("channel") or ""),
                "notification_id": notification.get("notification_id"),
            },
        )
    else:
        notification.setdefault("recovery_action", "use_dashboard_or_link_public_channel")
    return ArcLinkApiResponse(status=200, payload={"grant": public_grant, "notification": notification})


def _share_grant_viewer_actions(grant: Mapping[str, Any], *, viewer_user_id: str) -> tuple[str, list[str], str]:
    owner = str(grant.get("owner_user_id") or "")
    recipient = str(grant.get("recipient_user_id") or "")
    status = str(grant.get("status") or "")
    roles: list[str] = []
    actions: list[str] = []
    waiting_on = ""
    if viewer_user_id == owner:
        roles.append("owner")
        if status == "pending_owner_approval":
            actions.extend(["approve", "deny", "retry_notification"])
        elif status in {"approved", "accepted"}:
            actions.append("revoke")
    if viewer_user_id == recipient:
        roles.append("recipient")
        if status == "pending_owner_approval":
            waiting_on = "owner_approval"
        elif status == "approved":
            actions.extend(["accept", "retry_notification"])
        elif status == "accepted":
            waiting_on = "accepted"
    if not roles:
        roles.append("unrelated")
    return "_and_".join(roles), actions, waiting_on


def _share_grant_dashboard_guidance(grant: Mapping[str, Any], *, viewer_user_id: str) -> str:
    owner = str(grant.get("owner_user_id") or "")
    recipient = str(grant.get("recipient_user_id") or "")
    status = str(grant.get("status") or "")
    if viewer_user_id == owner and status == "pending_owner_approval":
        return "Owner approval is pending; use this dashboard to approve or deny if Raven cannot deliver a public-channel prompt."
    if viewer_user_id == recipient and status == "pending_owner_approval":
        return "Waiting on owner approval; this dashboard remains the durable status view if Raven cannot deliver a public-channel prompt."
    if viewer_user_id == recipient and status == "approved":
        return "Owner approval is complete; accept from this dashboard if Raven cannot deliver the recipient prompt."
    return ""


def _public_share_grant_for_viewer(
    conn: sqlite3.Connection,
    row: Mapping[str, Any],
    *,
    viewer_user_id: str,
) -> dict[str, Any]:
    grant = _public_share_grant(row)
    owner_channel = _share_public_channel_hint(_share_public_channel_for_user(conn, grant["owner_user_id"]))
    recipient_channel = _share_public_channel_hint(_share_public_channel_for_user(conn, grant["recipient_user_id"]))
    viewer_role, actions, waiting_on = _share_grant_viewer_actions(grant, viewer_user_id=viewer_user_id)
    grant.update(
        {
            "viewer_role": viewer_role,
            "available_actions": actions,
            "waiting_on": waiting_on,
            "dashboard_guidance": _share_grant_dashboard_guidance(grant, viewer_user_id=viewer_user_id),
            "notification_status": {
                "owner": owner_channel,
                "recipient": recipient_channel,
            },
        }
    )
    return grant


def _share_inbox_summary(grants: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "pending_owner_approvals": sum(1 for grant in grants if grant["viewer_role"].startswith("owner") and grant["status"] == "pending_owner_approval"),
        "waiting_on_owner_approval": sum(1 for grant in grants if "recipient" in grant["viewer_role"] and grant["status"] == "pending_owner_approval"),
        "pending_recipient_acceptance": sum(1 for grant in grants if "recipient" in grant["viewer_role"] and grant["status"] == "approved"),
        "accepted": sum(1 for grant in grants if grant["status"] == "accepted"),
        "denied": sum(1 for grant in grants if grant["status"] == "denied"),
        "revoked": sum(1 for grant in grants if grant["status"] == "revoked"),
        "expired": sum(1 for grant in grants if grant["status"] == "expired"),
    }


def read_user_share_grants_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    user_id: str = "",
) -> ArcLinkApiResponse:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    target_user = str(user_id or session["user_id"] or "").strip()
    if target_user != str(session["user_id"] or ""):
        raise ArcLinkApiAuthError("ArcLink user session cannot read another user's share grants")
    rows = conn.execute(
        """
        SELECT *
        FROM arclink_share_grants
        WHERE owner_user_id = ? OR recipient_user_id = ?
        ORDER BY
          CASE status
            WHEN 'pending_owner_approval' THEN 0
            WHEN 'approved' THEN 1
            WHEN 'accepted' THEN 2
            WHEN 'denied' THEN 3
            WHEN 'revoked' THEN 4
            WHEN 'expired' THEN 5
            ELSE 6
          END,
          updated_at DESC,
          created_at DESC
        LIMIT 100
        """,
        (target_user, target_user),
    ).fetchall()
    grants = [_public_share_grant_for_viewer(conn, rowdict(row), viewer_user_id=target_user) for row in rows]
    return ArcLinkApiResponse(
        status=200,
        payload={
            "share_grants": grants,
            "pending_owner_approvals": [
                grant for grant in grants
                if grant["viewer_role"].startswith("owner") and grant["status"] == "pending_owner_approval"
            ],
            "waiting_on_owner_approval": [
                grant for grant in grants
                if "recipient" in grant["viewer_role"] and grant["status"] == "pending_owner_approval"
            ],
            "pending_recipient_acceptance": [
                grant for grant in grants
                if "recipient" in grant["viewer_role"] and grant["status"] == "approved"
            ],
            "summary": _share_inbox_summary(grants),
        },
    )


def read_user_linked_resources_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    user_id: str = "",
) -> ArcLinkApiResponse:
    session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    target_user = str(user_id or session["user_id"] or "").strip()
    if target_user != str(session["user_id"] or ""):
        raise ArcLinkApiAuthError("ArcLink user session cannot read another user's linked resources")
    rows = conn.execute(
        """
        SELECT *
        FROM arclink_share_grants
        WHERE recipient_user_id = ?
          AND status = 'accepted'
          AND revoked_at = ''
        ORDER BY accepted_at DESC, created_at DESC
        """,
        (target_user,),
    ).fetchall()
    return ArcLinkApiResponse(status=200, payload={"linked_resources": [_public_share_grant(rowdict(row)) for row in rows]})


def _read_admin_dashboard_slice_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    payload_key: str,
    dashboard_key: str = "",
    post_filter: Any = None,
    **filters: Any,
) -> ArcLinkApiResponse:
    authenticate_arclink_admin_session(conn, session_id=session_id, session_token=session_token)
    dashboard = read_arclink_admin_dashboard(conn, **filters)
    source_key = dashboard_key or payload_key
    data = dashboard.get(source_key, [])
    if post_filter is not None:
        data = [item for item in data if post_filter(item)]
    return ArcLinkApiResponse(status=200, payload={payload_key: data})


def read_admin_service_health_api(
    conn: sqlite3.Connection, *, session_id: str, session_token: str, **filters: Any,
) -> ArcLinkApiResponse:
    authenticate_arclink_admin_session(conn, session_id=session_id, session_token=session_token)
    dashboard = read_arclink_admin_dashboard(conn, **filters)
    return ArcLinkApiResponse(status=200, payload={
        "service_health": dashboard.get("service_health", []),
        "recent_failures": [f for f in dashboard.get("recent_failures", []) if f.get("kind") == "service_health"],
    })


def read_admin_provisioning_jobs_api(
    conn: sqlite3.Connection, *, session_id: str, session_token: str, **filters: Any,
) -> ArcLinkApiResponse:
    return _read_admin_dashboard_slice_api(conn, session_id=session_id, session_token=session_token, payload_key="provisioning_jobs", **filters)


def read_admin_dns_drift_api(
    conn: sqlite3.Connection, *, session_id: str, session_token: str, **filters: Any,
) -> ArcLinkApiResponse:
    return _read_admin_dashboard_slice_api(conn, session_id=session_id, session_token=session_token, payload_key="dns_drift", **filters)


def read_admin_audit_api(
    conn: sqlite3.Connection, *, session_id: str, session_token: str, **filters: Any,
) -> ArcLinkApiResponse:
    return _read_admin_dashboard_slice_api(conn, session_id=session_id, session_token=session_token, payload_key="audit", **filters)


def read_admin_events_api(
    conn: sqlite3.Connection, *, session_id: str, session_token: str, **filters: Any,
) -> ArcLinkApiResponse:
    return _read_admin_dashboard_slice_api(conn, session_id=session_id, session_token=session_token, payload_key="events", **filters)


def read_admin_queued_actions_api(
    conn: sqlite3.Connection, *, session_id: str, session_token: str, **filters: Any,
) -> ArcLinkApiResponse:
    return _read_admin_dashboard_slice_api(conn, session_id=session_id, session_token=session_token, payload_key="actions", dashboard_key="action_intents", **filters)


def _zero_llm_router_usage_summary() -> dict[str, Any]:
    return {
        "request_count": 0,
        "succeeded_count": 0,
        "failed_count": 0,
        "cancelled_count": 0,
        "stream_request_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "estimated_cents": 0,
        "actual_cents": 0,
        "last_request_at": "",
    }


def _llm_router_provider_state(conn: sqlite3.Connection, deployment_ids: list[str]) -> dict[str, dict[str, Any]]:
    clean_ids = [str(item or "").strip() for item in deployment_ids if str(item or "").strip()]
    if not clean_ids:
        return {}
    placeholders = ",".join("?" for _ in clean_ids)
    summaries: dict[str, dict[str, Any]] = {
        deployment_id: {
            "mode": "arclink_llm_router",
            "credential_material": "never_returned",
            "secret_ref_present": False,
            "active_credential_count": 0,
            "total_credential_count": 0,
            "usage": _zero_llm_router_usage_summary(),
            "reservations": {
                "open_count": 0,
                "reserved_cents": 0,
            },
        }
        for deployment_id in clean_ids
    }
    for row in conn.execute(
        f"""
        SELECT
          deployment_id,
          COUNT(*) AS total_credential_count,
          SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active_credential_count
        FROM arclink_llm_router_keys
        WHERE deployment_id IN ({placeholders})
        GROUP BY deployment_id
        """,
        clean_ids,
    ).fetchall():
        deployment_id = str(row["deployment_id"] or "")
        if deployment_id in summaries:
            summaries[deployment_id]["secret_ref_present"] = int(row["total_credential_count"] or 0) > 0
            summaries[deployment_id]["active_credential_count"] = int(row["active_credential_count"] or 0)
            summaries[deployment_id]["total_credential_count"] = int(row["total_credential_count"] or 0)
    for row in conn.execute(
        f"""
        SELECT
          deployment_id,
          COUNT(*) AS request_count,
          SUM(CASE WHEN status = 'succeeded' THEN 1 ELSE 0 END) AS succeeded_count,
          SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
          SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled_count,
          SUM(CASE WHEN stream != 0 THEN 1 ELSE 0 END) AS stream_request_count,
          SUM(input_tokens) AS input_tokens,
          SUM(output_tokens) AS output_tokens,
          SUM(total_tokens) AS total_tokens,
          SUM(estimated_cents) AS estimated_cents,
          SUM(actual_cents) AS actual_cents,
          MAX(COALESCE(NULLIF(completed_at, ''), started_at)) AS last_request_at
        FROM arclink_llm_usage_events
        WHERE deployment_id IN ({placeholders})
        GROUP BY deployment_id
        """,
        clean_ids,
    ).fetchall():
        deployment_id = str(row["deployment_id"] or "")
        if deployment_id not in summaries:
            continue
        summaries[deployment_id]["usage"] = {
            "request_count": int(row["request_count"] or 0),
            "succeeded_count": int(row["succeeded_count"] or 0),
            "failed_count": int(row["failed_count"] or 0),
            "cancelled_count": int(row["cancelled_count"] or 0),
            "stream_request_count": int(row["stream_request_count"] or 0),
            "input_tokens": int(row["input_tokens"] or 0),
            "output_tokens": int(row["output_tokens"] or 0),
            "total_tokens": int(row["total_tokens"] or 0),
            "estimated_cents": int(row["estimated_cents"] or 0),
            "actual_cents": int(row["actual_cents"] or 0),
            "last_request_at": str(row["last_request_at"] or ""),
        }
    for row in conn.execute(
        f"""
        SELECT
          deployment_id,
          COUNT(*) AS open_count,
          SUM(reserved_cents) AS reserved_cents
        FROM arclink_llm_budget_reservations
        WHERE deployment_id IN ({placeholders}) AND status = 'reserved'
        GROUP BY deployment_id
        """,
        clean_ids,
    ).fetchall():
        deployment_id = str(row["deployment_id"] or "")
        if deployment_id in summaries:
            summaries[deployment_id]["reservations"] = {
                "open_count": int(row["open_count"] or 0),
                "reserved_cents": int(row["reserved_cents"] or 0),
            }
    return summaries


def _sum_llm_router_usage(summaries: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    total = _zero_llm_router_usage_summary()
    open_count = 0
    reserved_cents = 0
    active_credentials = 0
    last_request_at = ""
    for item in summaries.values():
        usage = item.get("usage") if isinstance(item, Mapping) else {}
        if not isinstance(usage, Mapping):
            usage = {}
        for key in (
            "request_count",
            "succeeded_count",
            "failed_count",
            "cancelled_count",
            "stream_request_count",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "estimated_cents",
            "actual_cents",
        ):
            total[key] += int(usage.get(key) or 0)
        observed_at = str(usage.get("last_request_at") or "")
        if observed_at > last_request_at:
            last_request_at = observed_at
        reservations = item.get("reservations") if isinstance(item, Mapping) else {}
        if isinstance(reservations, Mapping):
            open_count += int(reservations.get("open_count") or 0)
            reserved_cents += int(reservations.get("reserved_cents") or 0)
        active_credentials += int(item.get("active_credential_count") or 0)
    total["last_request_at"] = last_request_at
    return {
        "mode": "arclink_llm_router",
        "deployment_count": len(summaries),
        "active_credential_count": active_credentials,
        "usage": total,
        "reservations": {
            "open_count": open_count,
            "reserved_cents": reserved_cents,
        },
    }


def read_provider_state_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    session_kind: str = "user",
    env: Mapping[str, str] | None = None,
) -> ArcLinkApiResponse:
    """Read current provider/model configuration state.

    User route returns only that user's deployments; admin route sees all.
    """
    if session_kind == "admin":
        authenticate_arclink_admin_session(conn, session_id=session_id, session_token=session_token)
        deployments = conn.execute(
            """
            SELECT d.deployment_id, d.user_id, d.metadata_json, u.entitlement_state
            FROM arclink_deployments d
            LEFT JOIN arclink_users u ON u.user_id = d.user_id
            WHERE d.status NOT IN ('teardown_complete', 'cancelled')
            """
        ).fetchall()
    else:
        session = authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
        user_id = str(session.get("user_id") or "").strip()
        if not user_id:
            raise ArcLinkApiAuthError("ArcLink user session has no associated user")
        deployments = conn.execute(
            """
            SELECT d.deployment_id, d.user_id, d.metadata_json, u.entitlement_state
            FROM arclink_deployments d
            LEFT JOIN arclink_users u ON u.user_id = d.user_id
            WHERE d.status NOT IN ('teardown_complete', 'cancelled') AND d.user_id = ?
            """,
            (user_id,),
        ).fetchall()
    env_source = env or {}
    provider = primary_provider(env_source)
    default_model = chutes_default_model(env_source)
    deployment_models = []
    state_counts: dict[str, int] = {}
    deployment_ids = [str(row["deployment_id"] or "") for row in deployments]
    router_state = _llm_router_provider_state(conn, deployment_ids)
    for row in deployments:
        meta = json_loads_safe(row["metadata_json"] or "{}")
        model_id = str(meta.get("selected_model_id") or meta.get("model_id") or default_model)
        item = {"deployment_id": row["deployment_id"], "user_id": row["user_id"], "model_id": model_id}
        if provider == "chutes":
            boundary = evaluate_chutes_deployment_boundary(
                str(row["deployment_id"] or ""),
                str(row["user_id"] or ""),
                meta,
                env=env_source,
                billing_state=str(row["entitlement_state"] or "none"),
            )
            public_boundary = boundary.to_public(include_user_id=session_kind == "admin", include_admin_fields=session_kind == "admin")
            item["credential_state"] = boundary.credential_state
            item["allow_inference"] = boundary.allow_inference
            item["chutes"] = public_boundary
            item["provider_detail"] = public_boundary
            llm_router = router_state.get(str(row["deployment_id"] or ""), {})
            if llm_router:
                llm_router = dict(llm_router)
                llm_router["quota"] = dict(public_boundary.get("budget", {}))
                item["llm_router"] = llm_router
            state_counts[boundary.credential_state] = state_counts.get(boundary.credential_state, 0) + 1
        deployment_models.append(item)
    payload = {
        "provider": provider,
        "default_model": default_model,
        "provider_boundary": {
            "credential_isolation": "per-user or per-deployment secret:// reference required",
            "operator_shared_key_policy": "not accepted as user isolation",
            "credential_lifecycle": chutes_credential_lifecycle(),
            "budget_enforcement": "fail_closed",
            "live_key_creation": "proof_gated",
            "threshold_continuation": chutes_threshold_continuation_policy(force_policy_question=True),
        },
        "provider_settings": {
            "self_service_provider_add": "policy_question",
            "dashboard_mutation": "disabled",
            "current_change_path": "operator_managed_deployment_config_or_secure_credential_handoff",
            "secret_input_policy": "dashboard_never_collects_raw_provider_tokens",
            "live_provider_mutation": "proof_gated",
            "operator_decision_needed": (
                "Decide whether users may self-service provider changes in ArcLink settings, "
                "or whether provider changes remain operator-managed deployment config."
            ),
            "guidance": (
                "The dashboard shows provider state only. Provider changes use secure credential "
                "handoff or operator-managed config until product policy defines a self-service flow."
            ),
        },
        "deployment_models": deployment_models,
    }
    if provider == "chutes":
        payload["chutes_summary"] = {
            "deployment_count": len(deployment_models),
            "credential_states": state_counts,
            "blocked_count": sum(1 for item in deployment_models if not item.get("allow_inference")),
            "llm_router": _sum_llm_router_usage(router_state),
        }
    return ArcLinkApiResponse(status=200, payload=payload)


def read_admin_reconciliation_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
) -> ArcLinkApiResponse:
    """Read Stripe-vs-local reconciliation drift summary."""
    authenticate_arclink_admin_session(conn, session_id=session_id, session_token=session_token)
    drift_items = detect_stripe_reconciliation_drift(conn)
    return ArcLinkApiResponse(status=200, payload={
        "reconciliation": [
            {"kind": d.kind, "user_id": d.user_id, "detail": d.detail}
            for d in drift_items
        ],
        "drift_count": len(drift_items),
    })


def queue_admin_action_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    csrf_token: str,
    action_type: str,
    target_kind: str,
    target_id: str,
    reason: str,
    idempotency_key: str,
    confirm: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> ArcLinkApiResponse:
    session = authenticate_arclink_admin_session(conn, session_id=session_id, session_token=session_token)
    require_arclink_csrf(conn, session_id=session_id, csrf_token=csrf_token, session_kind="admin")
    _admin_mutation_allowed(conn, session)
    if confirm is not True:
        raise ArcLinkApiAuthError("ArcLink admin action queueing requires explicit confirmation")
    admin_id = str(session["admin_id"] or "")
    check_arclink_rate_limit(conn, scope="admin_action:admin", subject=admin_id, limit=30, window_seconds=60)
    check_arclink_rate_limit(
        conn,
        scope="admin_action:target",
        subject=f"{str(target_kind or '').strip().lower()}:{str(target_id or '').strip()}",
        limit=12,
        window_seconds=60,
    )
    action = queue_arclink_admin_action(
        conn,
        admin_id=admin_id,
        action_type=action_type,
        target_kind=target_kind,
        target_id=target_id,
        reason=reason,
        idempotency_key=idempotency_key,
        metadata=metadata,
    )
    return ArcLinkApiResponse(status=202, payload={"action": dict(action)})


def revoke_arclink_session(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_kind: str,
    actor_id: str,
    reason: str,
    commit: bool = True,
) -> dict[str, Any]:
    clean_kind = _validate_session_kind(session_kind, operation="session revoke")
    if not commit and not conn.in_transaction:
        raise ArcLinkApiAuthError("ArcLink staged session revocation requires an explicit transaction")
    table = "arclink_admin_sessions" if clean_kind == "admin" else "arclink_user_sessions"
    clean_session = _require_session_id_prefix(session_id, kind=clean_kind)
    existing = conn.execute(f"SELECT * FROM {table} WHERE session_id = ?", (clean_session,)).fetchone()
    if existing is None:
        raise ArcLinkApiAuthError(f"ArcLink {clean_kind} session not found")
    now = utc_now_iso()
    conn.execute(
        f"UPDATE {table} SET status = 'revoked', revoked_at = ? WHERE session_id = ?",
        (now, clean_session),
    )
    append_arclink_audit(
        conn,
        action=f"session_revoke:{clean_kind}",
        actor_id=actor_id,
        target_kind=f"{clean_kind}_session",
        target_id=clean_session,
        reason=reason,
        commit=False,
    )
    if commit:
        conn.commit()
    return _public_session(rowdict(conn.execute(f"SELECT * FROM {table} WHERE session_id = ?", (clean_session,)).fetchone()))


def claim_session_from_onboarding_api(
    conn: sqlite3.Connection,
    *,
    onboarding_session_id: str,
    browser_claim_token: str,
) -> ArcLinkApiResponse:
    """Create a user session from a paid onboarding session.

    This is the bridge between the public onboarding flow and the
    authenticated user dashboard: after Stripe confirms payment, the
    browser exchanges the onboarding session_id for a user session.
    Rate-limited to prevent brute-force session enumeration.
    """
    _require_nonempty(onboarding_session_id, "session_id")
    clean_id = str(onboarding_session_id).strip()
    check_arclink_rate_limit(
        conn, scope="onboarding_claim", subject=clean_id, limit=5, window_seconds=900,
    )
    _require_nonempty(browser_claim_token, "claim_token")
    row = conn.execute(
        "SELECT session_id, user_id, status, email_hint, metadata_json FROM arclink_onboarding_sessions WHERE session_id = ?",
        (clean_id,),
    ).fetchone()
    if row is None:
        raise ArcLinkApiAuthError("Onboarding session not found")
    session_dict = dict(row)
    session_metadata = _json_loads(str(session_dict.get("metadata_json") or "{}"))
    expected_hash = str(session_metadata.get("browser_claim_proof_hash") or "").strip()
    replay_hash = str(session_metadata.get("browser_claim_proof_used_hash") or "").strip()
    replay_until = parse_utc_iso(str(session_metadata.get("browser_claim_replay_until") or ""))
    proof_hash_for_replay = ""
    if expected_hash:
        if not _verify_proof_token_hash(browser_claim_token, expected_hash):
            raise ArcLinkApiAuthError("Onboarding claim proof failed")
        proof_hash_for_replay = expected_hash
    elif replay_hash and replay_until and replay_until > utc_now():
        if not _verify_proof_token_hash(browser_claim_token, replay_hash):
            raise ArcLinkApiAuthError("Onboarding claim proof failed")
        proof_hash_for_replay = replay_hash
    else:
        raise ArcLinkApiAuthError("Onboarding claim proof failed")
    user_id = str(session_dict.get("user_id") or "").strip()
    if not user_id:
        raise ArcLinkApiAuthError("Onboarding session has no associated user yet")
    user_row = conn.execute(
        "SELECT user_id, entitlement_state FROM arclink_users WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if user_row is None:
        raise ArcLinkApiAuthError("User account not found")
    if str(user_row["entitlement_state"] or "") != "paid":
        return ArcLinkApiResponse(status=402, payload={
            "error": "entitlement_not_paid",
            "entitlement_state": str(user_row["entitlement_state"] or "unknown"),
            "user_id": user_id,
        })
    user_session = create_arclink_user_session(
        conn,
        user_id=user_id,
        metadata={"source": "onboarding_claim", "onboarding_session_id": clean_id},
    )
    session_metadata.pop("browser_claim_proof_hash", None)
    session_metadata["browser_claim_proof_used_hash"] = proof_hash_for_replay
    session_metadata["browser_claim_proof_used_at"] = utc_now_iso()
    session_metadata["browser_claim_replay_until"] = utc_after_seconds_iso(ARCLINK_ONBOARDING_CLAIM_REPLAY_SECONDS)
    conn.execute(
        "UPDATE arclink_onboarding_sessions SET metadata_json = ?, updated_at = ? WHERE session_id = ?",
        (_json(session_metadata), utc_now_iso(), clean_id),
    )
    conn.commit()
    return ArcLinkApiResponse(status=201, payload={
        "session": user_session,
        "user_id": user_id,
        "email": str(session_dict.get("email_hint") or ""),
    })


def cancel_onboarding_session_api(
    conn: sqlite3.Connection,
    *,
    onboarding_session_id: str,
    browser_cancel_token: str,
) -> ArcLinkApiResponse:
    """Mark an onboarding session as cancelled.

    Called by the checkout cancel page so the backend can distinguish
    abandoned sessions from active ones. The session can still be
    resumed later via a new start call with the same channel identity.
    """
    _require_nonempty(onboarding_session_id, "session_id")
    _require_nonempty(browser_cancel_token, "cancel_token")
    clean_id = str(onboarding_session_id).strip()
    row = conn.execute(
        "SELECT session_id, status, metadata_json FROM arclink_onboarding_sessions WHERE session_id = ?",
        (clean_id,),
    ).fetchone()
    if row is None:
        return ArcLinkApiResponse(status=404, payload={"error": "session_not_found"})
    current_status = str(row["status"] or "").strip()
    if current_status in ARCLINK_ONBOARDING_CANCEL_IMMUTABLE_STATUSES:
        return ArcLinkApiResponse(status=200, payload={
            "session_id": clean_id,
            "status": current_status,
            "changed": False,
        })
    session_metadata = _json_loads(str(row["metadata_json"] or "{}"))
    expected_hash = str(session_metadata.get("browser_cancel_proof_hash") or "").strip()
    if not _verify_proof_token_hash(browser_cancel_token, expected_hash):
        raise ArcLinkApiAuthError("Onboarding cancel proof failed")
    cancelled = cancel_arclink_onboarding_session(
        conn,
        session_id=clean_id,
        reason="checkout cancel page",
    )
    session_metadata.pop("browser_cancel_proof_hash", None)
    session_metadata["browser_cancel_proof_used_at"] = utc_now_iso()
    conn.execute(
        "UPDATE arclink_onboarding_sessions SET metadata_json = ?, updated_at = ? WHERE session_id = ?",
        (_json(session_metadata), utc_now_iso(), clean_id),
    )
    conn.commit()
    return ArcLinkApiResponse(status=200, payload={
        "session_id": clean_id,
        "status": str(cancelled.get("status") or ""),
        "changed": True,
    })
