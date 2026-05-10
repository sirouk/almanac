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
    append_arclink_audit,
    append_arclink_event,
    parse_utc_iso,
    queue_notification,
    utc_after_seconds_iso,
    utc_now,
    utc_now_iso,
)
from arclink_boundary import json_dumps_safe, json_loads_safe, reject_secret_material, rowdict
from arclink_dashboard import queue_arclink_admin_action, read_arclink_admin_dashboard, read_arclink_user_dashboard
from arclink_onboarding import (
    answer_arclink_onboarding_question,
    cancel_arclink_onboarding_session,
    create_or_resume_arclink_onboarding_session,
    normalize_arclink_public_onboarding_contact,
    open_arclink_onboarding_checkout,
)
from arclink_entitlements import ReconciliationDrift, detect_stripe_reconciliation_drift
from arclink_product import chutes_default_model, primary_provider
from arclink_chutes import (
    chutes_credential_lifecycle,
    chutes_threshold_continuation_policy,
    evaluate_chutes_deployment_boundary,
    renewal_lifecycle_for_billing_state,
)


ARCLINK_ADMIN_ROLES = frozenset({"owner", "admin", "ops", "support", "read_only"})
ARCLINK_ADMIN_MUTATION_ROLES = frozenset({"owner", "admin", "ops"})
ARCLINK_SESSION_STATUSES = frozenset({"active", "revoked"})
ARCLINK_CREDENTIAL_HANDOFF_KINDS = frozenset({"dashboard_password", "chutes_api_key", "notion_token"})
ARCLINK_CREDENTIAL_HANDOFF_STATUSES = frozenset({"available", "removed"})
ARCLINK_SHARE_RESOURCE_KINDS = frozenset({"drive", "code"})
ARCLINK_SHARE_RESOURCE_ROOTS = frozenset({"vault", "workspace"})
ARCLINK_SHARE_ACCESS_MODES = frozenset({"read"})
ARCLINK_SHARE_STATUSES = frozenset({"pending_owner_approval", "approved", "accepted", "revoked", "denied"})
ARCLINK_LINKED_RESOURCE_MANIFEST = ".arclink-linked-resources.json"
ARCLINK_SESSION_ID_HEADER = "x-arclink-session-id"
ARCLINK_SESSION_TOKEN_HEADER = "x-arclink-session-token"
ARCLINK_CSRF_HEADER = "x-arclink-csrf-token"
GENERIC_ARCLINK_API_ERROR = "Request blocked. Check input and try again."
ARCLINK_PASSWORD_ALGORITHM = "pbkdf2_sha256"
ARCLINK_PASSWORD_ITERATIONS = 390_000
ARCLINK_ADMIN_PASSWORD_ALGORITHM = ARCLINK_PASSWORD_ALGORITHM
ARCLINK_ADMIN_PASSWORD_ITERATIONS = ARCLINK_PASSWORD_ITERATIONS


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
        payload = {"error": str(exc)}
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
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


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
        raise ArcLinkApiAuthError(f"ArcLink {kind} session is not active")
    expires_at = parse_utc_iso(str(row.get("expires_at") or ""))
    if expires_at is None or expires_at <= utc_now():
        raise ArcLinkApiAuthError(f"ArcLink {kind} session is expired")


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
    cutoff = (utc_now() - dt.timedelta(seconds=max(1, int(window_seconds or 1)))).replace(microsecond=0).isoformat()
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
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO arclink_user_sessions (
          session_id, user_id, session_token_hash, csrf_token_hash, status,
          metadata_json, created_at, last_seen_at, expires_at
        ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)
        """,
        (clean_session, user_id, _hash_token(token), _hash_token(csrf), _json(metadata), now, now, utc_after_seconds_iso(ttl_seconds)),
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
            _hash_token(token),
            _hash_token(csrf),
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
    mfa_verified: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> ArcLinkApiResponse:
    clean_email = str(email or "").strip().lower()
    clean_subject = str(login_subject or clean_email).strip().lower()
    if not clean_email:
        raise ArcLinkApiAuthError("ArcLink admin login requires an email")
    check_arclink_rate_limit(conn, scope="admin_login", subject=clean_subject, limit=5, window_seconds=900)
    row = conn.execute(
        "SELECT admin_id, password_hash FROM arclink_admins WHERE LOWER(email) = LOWER(?) AND status = 'active'",
        (clean_email,),
    ).fetchone()
    if row is None:
        raise ArcLinkApiAuthError("Invalid ArcLink admin credentials")
    if not str(row["password_hash"] or "").strip():
        raise ArcLinkApiAuthError("ArcLink admin password is not configured")
    if not verify_arclink_admin_password(str(password or ""), str(row["password_hash"] or "")):
        raise ArcLinkApiAuthError("Invalid ArcLink admin credentials")
    session = create_arclink_admin_session(
        conn,
        admin_id=str(row["admin_id"] or ""),
        mfa_verified=mfa_verified,
        metadata={"login_subject": clean_subject, **dict(metadata or {})},
    )
    return ArcLinkApiResponse(status=201, payload={"session": session})


def create_arclink_user_login_session_api(
    conn: sqlite3.Connection,
    *,
    email: str,
    password: str,
    login_subject: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> ArcLinkApiResponse:
    clean_email = str(email or "").strip().lower()
    clean_subject = str(login_subject or clean_email).strip().lower()
    if not clean_email:
        raise ArcLinkApiAuthError("ArcLink user login requires an email")
    check_arclink_rate_limit(conn, scope="user_login", subject=clean_subject, limit=10, window_seconds=900)
    row = conn.execute(
        "SELECT user_id, password_hash FROM arclink_users WHERE LOWER(email) = LOWER(?) AND status = 'active'",
        (clean_email,),
    ).fetchone()
    if row is None:
        raise ArcLinkApiAuthError("Invalid ArcLink user credentials")
    if not str(row["password_hash"] or "").strip():
        raise ArcLinkApiAuthError("ArcLink user password is not configured")
    if not verify_arclink_password(str(password or ""), str(row["password_hash"] or "")):
        raise ArcLinkApiAuthError("Invalid ArcLink user credentials")
    session = create_arclink_user_session(
        conn,
        user_id=str(row["user_id"] or ""),
        metadata={"login_subject": clean_subject, **dict(metadata or {})},
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
    row = conn.execute(f"SELECT * FROM {table} WHERE session_id = ?", (session_id,)).fetchone()
    if row is None:
        raise ArcLinkApiAuthError(f"ArcLink {clean_kind} session not found")
    record = dict(row)
    _require_active_time(record, kind=clean_kind)
    if not hmac.compare_digest(str(record["session_token_hash"] or ""), _hash_token(session_token)):
        raise ArcLinkApiAuthError(f"ArcLink {clean_kind} session token mismatch")
    conn.execute(f"UPDATE {table} SET last_seen_at = ? WHERE session_id = ?", (utc_now_iso(), session_id))
    conn.commit()
    return _public_session(record)


def authenticate_arclink_user_session(conn: sqlite3.Connection, *, session_id: str, session_token: str) -> dict[str, Any]:
    return _authenticate_session(conn, session_id=session_id, session_token=session_token, kind="user")


def authenticate_arclink_admin_session(conn: sqlite3.Connection, *, session_id: str, session_token: str) -> dict[str, Any]:
    return _authenticate_session(conn, session_id=session_id, session_token=session_token, kind="admin")


def require_arclink_csrf(conn: sqlite3.Connection, *, session_id: str, csrf_token: str, session_kind: str) -> bool:
    clean_kind = _validate_session_kind(session_kind, operation="CSRF check")
    table = "arclink_admin_sessions" if clean_kind == "admin" else "arclink_user_sessions"
    row = conn.execute(f"SELECT csrf_token_hash FROM {table} WHERE session_id = ?", (session_id,)).fetchone()
    if row is None or not hmac.compare_digest(str(row["csrf_token_hash"] or ""), _hash_token(csrf_token)):
        raise ArcLinkApiAuthError("ArcLink CSRF check failed")
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
        "browser_claim_proof_hash": _hash_token(claim_token),
        "browser_cancel_proof_hash": _hash_token(cancel_token),
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


def read_admin_dashboard_api(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    session_token: str,
    **filters: Any,
) -> ArcLinkApiResponse:
    authenticate_arclink_admin_session(conn, session_id=session_id, session_token=session_token)
    return ArcLinkApiResponse(status=200, payload=read_arclink_admin_dashboard(conn, **filters))


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
        if row is not None and str(row["user_id"] or "") != target_user:
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


def _dashboard_password_secret_path(*, deployment_id: str, secret_ref: str) -> Path | None:
    clean_deployment = str(deployment_id or "").strip()
    clean_ref = str(secret_ref or "").strip()
    if not clean_deployment or clean_ref != f"secret://arclink/dashboard/{clean_deployment}/password":
        return None
    root = _secret_store_root()
    deployment_root = (root / clean_deployment).resolve()
    path = (deployment_root / f"{hashlib.sha256(clean_ref.encode('utf-8')).hexdigest()}.secret").resolve()
    try:
        path.relative_to(deployment_root)
    except ValueError:
        return None
    return path


def _resolve_revealable_credential_secret(row: Mapping[str, Any]) -> str:
    kind = str(row.get("credential_kind") or "").strip()
    if kind != "dashboard_password":
        return ""
    path = _dashboard_password_secret_path(
        deployment_id=str(row.get("deployment_id") or ""),
        secret_ref=str(row.get("secret_ref") or ""),
    )
    if path is None or not path.is_file():
        return ""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return raw if raw.startswith("arc_") else ""


def _deployment_secret_refs(deployment_id: str, metadata: Mapping[str, Any]) -> dict[str, str]:
    refs = metadata.get("secret_refs") if isinstance(metadata.get("secret_refs"), Mapping) else {}
    defaults = {
        "dashboard_password": f"secret://arclink/dashboard/{deployment_id}/password",
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
    for kind, secret_ref in _deployment_secret_refs(deployment_id, metadata).items():
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
              secret_ref, delivery_hint, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'available', ?, ?)
            ON CONFLICT(deployment_id, credential_kind) DO UPDATE SET
              user_id = excluded.user_id,
              secret_ref = CASE
                WHEN arclink_credential_handoffs.status = 'available' THEN excluded.secret_ref
                ELSE arclink_credential_handoffs.secret_ref
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
                now,
                now,
            ),
        )
    conn.commit()


def _public_credential_handoff(row: Mapping[str, Any], *, raw_secret: str = "") -> dict[str, Any]:
    status = str(row.get("status") or "")
    removed = status == "removed" or bool(str(row.get("removed_at") or ""))
    revealable = bool(raw_secret) and not removed
    payload = {
        "handoff_id": str(row.get("handoff_id") or ""),
        "deployment_id": str(row.get("deployment_id") or ""),
        "credential_kind": str(row.get("credential_kind") or ""),
        "display_name": str(row.get("display_name") or ""),
        "status": status,
        "revealed_at": str(row.get("revealed_at") or ""),
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
        if str(row_data.get("status") or "") == "removed":
            continue
        raw_secret = _resolve_revealable_credential_secret(row_data)
        if raw_secret and not str(row_data.get("revealed_at") or ""):
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
    removed_count = sum(1 for row in rows if str(row["status"] or "") == "removed")
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


def _deployment_state_roots_for_user(conn: sqlite3.Connection, user_id: str) -> dict[str, str]:
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
        (str(user_id or "").strip(),),
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
        "read_only": True,
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
            "read_only": True,
        }
    return {
        "status": str(projection.get("status") or "not_materialized"),
        "linked_root": "linked",
        "linked_path": str(projection.get("linked_path") or ""),
        "entry_path": str(projection.get("entry_path") or ""),
        "resource_kind": str(projection.get("resource_kind") or ""),
        "projection_mode": str(projection.get("projection_mode") or ""),
        "materialized_at": str(projection.get("materialized_at") or ""),
        "removed_at": str(projection.get("removed_at") or ""),
        "reason": str(projection.get("reason") or ""),
        "read_only": True,
        "skipped_sensitive_count": int(projection.get("skipped_sensitive_count") or 0),
    }


def _public_share_grant(row: Mapping[str, Any]) -> dict[str, Any]:
    metadata = json_loads_safe(str(row.get("metadata_json") or "{}"))
    projection = _share_projection_public(metadata)
    return {
        "grant_id": str(row.get("grant_id") or ""),
        "owner_user_id": str(row.get("owner_user_id") or ""),
        "recipient_user_id": str(row.get("recipient_user_id") or ""),
        "resource_kind": str(row.get("resource_kind") or ""),
        "resource_root": str(row.get("resource_root") or ""),
        "resource_path": str(row.get("resource_path") or ""),
        "display_name": str(row.get("display_name") or ""),
        "access_mode": str(row.get("access_mode") or ""),
        "status": str(row.get("status") or ""),
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
                    {"text": "Deny", "callback_data": f"arclink:{deny_command}"},
                    {"text": "Approve", "callback_data": f"arclink:{approve_command}"},
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


def _queue_share_grant_owner_notification(
    conn: sqlite3.Connection,
    *,
    grant: Mapping[str, Any],
) -> dict[str, Any]:
    owner_user = str(grant.get("owner_user_id") or "").strip()
    grant_id = str(grant.get("grant_id") or "").strip()
    if not owner_user or not grant_id:
        return {"queued": False, "reason": "missing_owner_or_grant"}
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
        (owner_user,),
    ).fetchone()
    if row is None:
        return {"queued": False, "reason": "no_public_channel"}

    channel = str(row["channel"] or "").strip().lower()
    target = str(row["channel_identity"] or "").strip()
    if channel not in {"telegram", "discord"} or not target:
        return {"queued": False, "reason": "unsupported_public_channel"}

    resource_label = str(grant.get("display_name") or grant.get("resource_path") or "linked resource").strip()
    resource_root = str(grant.get("resource_root") or "").strip()
    resource_path = str(grant.get("resource_path") or "").strip()
    recipient = str(grant.get("recipient_user_id") or "").strip()
    message = (
        "Raven share approval requested.\n\n"
        f"Recipient `{recipient}` is asking for read-only access to `{resource_label}` "
        f"from `{resource_root}:{resource_path}`.\n\n"
        "Approve to let the recipient accept it as a read-only Linked resource. "
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
    source_key = "vault" if resource_root == "vault" else "code_workspace"
    metadata = json_loads_safe(str(grant.get("metadata_json") or "{}"))
    projection: dict[str, Any] = {
        "status": "not_materialized",
        "linked_root": "linked",
        "linked_path": "",
        "entry_path": "",
        "read_only": True,
    }
    try:
        owner_roots = _deployment_state_roots_for_user(conn, owner_user)
        recipient_roots = _deployment_state_roots_for_user(conn, recipient_user)
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
            updated_at=now,
        )

        projection.update(
            {
                "status": "materialized",
                "linked_path": linked_path,
                "entry_path": entry_display,
                "resource_kind": resource_kind,
                "projection_mode": "living_symlink",
                "materialized_at": now,
                "skipped_sensitive_count": 0,
                "reason": "",
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
        recipient_roots = _deployment_state_roots_for_user(conn, recipient_user)
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
    display_name: str = "",
    access_mode: str = "read",
    metadata: Mapping[str, Any] | None = None,
    requested_by_agent_id: str = "",
) -> ArcLinkApiResponse:
    owner_user = str(owner_user_id or "").strip()
    recipient = str(recipient_user_id or "").strip()
    if not owner_user:
        raise ArcLinkApiAuthError("ArcLink share requires an owner user")
    if conn.execute("SELECT 1 FROM arclink_users WHERE user_id = ?", (owner_user,)).fetchone() is None:
        raise KeyError(owner_user)
    if not recipient or recipient == owner_user:
        raise ArcLinkApiAuthError("ArcLink share requires a different recipient user")
    if conn.execute("SELECT 1 FROM arclink_users WHERE user_id = ?", (recipient,)).fetchone() is None:
        raise KeyError(recipient)
    kind = str(resource_kind or "").strip().lower()
    root = str(resource_root or "").strip().lower()
    mode = str(access_mode or "read").strip().lower()
    if kind not in ARCLINK_SHARE_RESOURCE_KINDS:
        raise ArcLinkApiAuthError("ArcLink share requires a supported resource kind")
    if root not in ARCLINK_SHARE_RESOURCE_ROOTS:
        raise ArcLinkApiAuthError("ArcLink share cannot originate from linked or unknown roots")
    if mode not in ARCLINK_SHARE_ACCESS_MODES:
        raise ArcLinkApiAuthError("ArcLink share grants are read-only")
    clean_path = _clean_share_path(resource_path)
    safe_metadata = dict(metadata or {})
    clean_agent = str(requested_by_agent_id or "").strip()
    if clean_agent:
        safe_metadata["requested_by_agent_id"] = clean_agent
    _reject_secret_material(safe_metadata)
    now = utc_now_iso()
    grant_id = _new_id("share")
    conn.execute(
        """
        INSERT INTO arclink_share_grants (
          grant_id, owner_user_id, recipient_user_id, resource_kind, resource_root,
          resource_path, display_name, access_mode, status, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending_owner_approval', ?, ?, ?)
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
    if clean_agent:
        audit_metadata["requested_by_agent_id"] = clean_agent
    append_arclink_audit(
        conn,
        action="share_grant_requested",
        actor_id=owner_user,
        target_kind="share_grant",
        target_id=grant_id,
        reason="read-only linked resource share requested",
        metadata=audit_metadata,
        commit=False,
    )
    conn.commit()
    grant = rowdict(conn.execute("SELECT * FROM arclink_share_grants WHERE grant_id = ?", (grant_id,)).fetchone())
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
    display_name: str = "",
    access_mode: str = "read",
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
        display_name=display_name,
        access_mode=access_mode,
        metadata=metadata,
    )


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
    return ArcLinkApiResponse(status=200, payload={"grant": _public_share_grant(grant)})


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
    recipient = str(session["user_id"] or "")
    clean_grant = str(grant_id or "").strip()
    row = conn.execute("SELECT * FROM arclink_share_grants WHERE grant_id = ?", (clean_grant,)).fetchone()
    if row is None or str(row["recipient_user_id"] or "") != recipient:
        raise ArcLinkApiAuthError("ArcLink user session cannot accept another user's share")
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
        actor_id=recipient,
        target_kind="share_grant",
        target_id=clean_grant,
        reason="recipient accepted read-only linked resource",
        commit=False,
    )
    conn.commit()
    grant = rowdict(conn.execute("SELECT * FROM arclink_share_grants WHERE grant_id = ?", (clean_grant,)).fetchone())
    return ArcLinkApiResponse(status=200, payload={"grant": _public_share_grant(grant)})


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
    metadata: Mapping[str, Any] | None = None,
) -> ArcLinkApiResponse:
    session = authenticate_arclink_admin_session(conn, session_id=session_id, session_token=session_token)
    require_arclink_csrf(conn, session_id=session_id, csrf_token=csrf_token, session_kind="admin")
    _admin_mutation_allowed(conn, session)
    action = queue_arclink_admin_action(
        conn,
        admin_id=str(session["admin_id"] or ""),
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
    table = "arclink_admin_sessions" if clean_kind == "admin" else "arclink_user_sessions"
    clean_session = str(session_id or "").strip()
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
    if not expected_hash or not hmac.compare_digest(expected_hash, _hash_token(browser_claim_token)):
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
    session_metadata["browser_claim_proof_used_at"] = utc_now_iso()
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
    if current_status in {"completed", "payment_cancelled", "payment_expired", "payment_failed", "abandoned"}:
        return ArcLinkApiResponse(status=200, payload={
            "session_id": clean_id,
            "status": current_status,
            "changed": False,
        })
    session_metadata = _json_loads(str(row["metadata_json"] or "{}"))
    expected_hash = str(session_metadata.get("browser_cancel_proof_hash") or "").strip()
    if not expected_hash or not hmac.compare_digest(expected_hash, _hash_token(browser_cancel_token)):
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
