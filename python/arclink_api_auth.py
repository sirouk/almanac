#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import hashlib
import hmac
from http.cookies import SimpleCookie
import json
import secrets
import sqlite3
from typing import Any, Mapping

from arclink_control import append_arclink_audit, parse_utc_iso, utc_after_seconds_iso, utc_now, utc_now_iso
from arclink_boundary import json_dumps_safe, json_loads_safe, reject_secret_material, rowdict
from arclink_dashboard import queue_arclink_admin_action, read_arclink_admin_dashboard, read_arclink_user_dashboard
from arclink_onboarding import (
    answer_arclink_onboarding_question,
    create_or_resume_arclink_onboarding_session,
    normalize_arclink_public_onboarding_contact,
    open_arclink_onboarding_checkout,
)
from arclink_entitlements import ReconciliationDrift, detect_stripe_reconciliation_drift
from arclink_product import chutes_default_model, primary_provider


ARCLINK_ADMIN_ROLES = frozenset({"owner", "admin", "ops", "support", "read_only"})
ARCLINK_ADMIN_MUTATION_ROLES = frozenset({"owner", "admin", "ops"})
ARCLINK_SESSION_STATUSES = frozenset({"active", "revoked"})
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
    clean_kind = _validate_session_kind(session_kind, operation="CSRF token extraction")
    csrf_token = _header(headers, ARCLINK_CSRF_HEADER) or _cookie(headers, f"arclink_{clean_kind}_csrf")
    if not csrf_token:
        raise ArcLinkApiAuthError("ArcLink CSRF token is required")
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
        (clean_admin, clean_email, clean_role, status, clean_password_hash, _json(role_scope), now, now),
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
    return ArcLinkApiResponse(status=201, payload={"session": session})


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
    return ArcLinkApiResponse(status=200, payload={"session": session})


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
    return ArcLinkApiResponse(status=200, payload={"session": session})


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
) -> ArcLinkApiResponse:
    """Read current provider/model configuration state."""
    if session_kind == "admin":
        authenticate_arclink_admin_session(conn, session_id=session_id, session_token=session_token)
    else:
        authenticate_arclink_user_session(conn, session_id=session_id, session_token=session_token)
    provider = primary_provider()
    default_model = chutes_default_model()
    # Gather per-deployment model assignments from arclink_deployments
    deployments = conn.execute(
        "SELECT deployment_id, user_id, metadata_json FROM arclink_deployments WHERE status NOT IN ('teardown_complete', 'cancelled')"
    ).fetchall()
    deployment_models = []
    for row in deployments:
        meta = json_loads_safe(row["metadata_json"] or "{}")
        model_id = str(meta.get("selected_model_id") or meta.get("model_id") or default_model)
        deployment_models.append({"deployment_id": row["deployment_id"], "user_id": row["user_id"], "model_id": model_id})
    return ArcLinkApiResponse(status=200, payload={
        "provider": provider,
        "default_model": default_model,
        "deployment_models": deployment_models,
    })


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
