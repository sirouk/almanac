#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib.parse import urlencode


CHUTES_OAUTH_AUTHORIZE_URL = "https://api.chutes.ai/idp/authorize"
CHUTES_OAUTH_TOKEN_URL = "https://api.chutes.ai/idp/token"
CHUTES_OAUTH_REVOKE_URL = "https://api.chutes.ai/idp/token/revoke"
CHUTES_OAUTH_SECRET_REF_PREFIX = "secret://arclink/chutes/oauth/"
DEFAULT_CHUTES_OAUTH_SCOPES = ("openid", "profile", "chutes:invoke", "account:read")
OPTIONAL_CHUTES_OAUTH_SCOPES = ("usage:read", "billing:read", "quota:read")


class ChutesOAuthError(RuntimeError):
    pass


class ChutesOAuthTokenStore(Protocol):
    def store_token(self, user_id: str, kind: str, token: str) -> str:
        ...


class ChutesOAuthCodeExchanger(Protocol):
    def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        client_id: str,
        client_secret_ref: str,
        code_verifier: str,
    ) -> Mapping[str, Any]:
        ...


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_segment(value: Any, *, label: str) -> str:
    clean = _clean_text(value)
    if not clean or "/" in clean or ".." in clean:
        raise ChutesOAuthError(f"{label} is required and must be a single path segment")
    return clean


def _validate_secret_ref(secret_ref: str, *, label: str = "Chutes OAuth client secret") -> str:
    clean = _clean_text(secret_ref)
    if not clean.startswith("secret://"):
        raise ChutesOAuthError(f"{label} must be a secret:// reference")
    lowered = clean.lower()
    if any(marker in lowered for marker in ("cpk_", "cak_", "crt_", "csc_", "access_token", "refresh_token")):
        raise ChutesOAuthError(f"{label} looks like raw secret material, not a secret reference")
    return clean


def _validate_redirect_uri(value: str) -> str:
    clean = _clean_text(value)
    if not clean:
        raise ChutesOAuthError("Chutes OAuth redirect_uri is required")
    if clean.startswith("https://"):
        return clean
    if clean.startswith("http://127.0.0.1") or clean.startswith("http://localhost"):
        return clean
    raise ChutesOAuthError("Chutes OAuth redirect_uri must use HTTPS outside localhost")


def _normalize_scopes(scopes: list[str] | tuple[str, ...] | None, *, include_usage_read: bool = False, include_billing_read: bool = False) -> tuple[str, ...]:
    requested = list(scopes or DEFAULT_CHUTES_OAUTH_SCOPES)
    if include_usage_read:
        requested.append("usage:read")
    if include_billing_read:
        requested.append("billing:read")
    seen: set[str] = set()
    result: list[str] = []
    for scope in requested:
        clean = _clean_text(scope)
        if not clean or "/" in clean or " " in clean:
            raise ChutesOAuthError(f"invalid Chutes OAuth scope: {clean!r}")
        if clean not in DEFAULT_CHUTES_OAUTH_SCOPES and clean not in OPTIONAL_CHUTES_OAUTH_SCOPES:
            raise ChutesOAuthError(f"unsupported Chutes OAuth scope: {clean}")
        if clean not in seen:
            seen.add(clean)
            result.append(clean)
    return tuple(result)


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _secret_ref_for_token(user_id: str, kind: str, token: str) -> str:
    safe_user = _safe_segment(user_id, label="user_id")
    safe_kind = _safe_segment(kind, label="token kind")
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return f"{CHUTES_OAUTH_SECRET_REF_PREFIX}{safe_user}/{safe_kind}/{digest}"


@dataclass(frozen=True)
class ChutesOAuthConfig:
    client_id: str
    client_secret_ref: str
    redirect_uri: str
    authorize_url: str = CHUTES_OAUTH_AUTHORIZE_URL
    token_url: str = CHUTES_OAUTH_TOKEN_URL
    revoke_url: str = CHUTES_OAUTH_REVOKE_URL

    def __post_init__(self) -> None:
        object.__setattr__(self, "client_id", _safe_segment(self.client_id, label="client_id"))
        object.__setattr__(self, "client_secret_ref", _validate_secret_ref(self.client_secret_ref))
        object.__setattr__(self, "redirect_uri", _validate_redirect_uri(self.redirect_uri))


@dataclass(frozen=True)
class ChutesOAuthConnectPlan:
    user_id: str
    session_id: str
    state: str
    csrf_token: str
    code_verifier: str
    scopes: tuple[str, ...]
    authorize_url: str
    created_at: float
    expires_at: float

    def to_public(self) -> dict[str, Any]:
        return {
            "provider": "chutes",
            "connect_status": "proof_gated_until_authorized_oauth_client_is_configured",
            "authorize_url": self.authorize_url,
            "scopes": list(self.scopes),
            "scope_display": describe_chutes_oauth_scopes(self.scopes),
            "state_present": bool(self.state),
            "csrf_required": True,
            "pkce": "S256",
            "callback": "server_validates_state_csrf_and_user_scope",
            "token_policy": "server_stores_tokens_by_secret_ref_only",
        }


@dataclass(frozen=True)
class ChutesOAuthConnection:
    user_id: str
    account_user_id: str
    username: str
    scopes: tuple[str, ...]
    access_token_ref: str
    refresh_token_ref: str
    connected_at: float
    revoked_at: float = 0.0

    def to_public(self) -> dict[str, Any]:
        return {
            "provider": "chutes",
            "connected": self.revoked_at <= 0,
            "account": {
                "user_id": self.account_user_id,
                "username": self.username,
            },
            "scopes": list(self.scopes),
            "scope_display": describe_chutes_oauth_scopes(self.scopes),
            "billing_readiness": "available" if "billing:read" in self.scopes else "not_requested",
            "usage_readiness": "available" if "usage:read" in self.scopes else "not_requested",
            "token_ref_present": bool(self.access_token_ref),
            "disconnect": {
                "status": "ready",
                "revocation_endpoint": "/idp/token/revoke",
                "live_revoke": "proof_gated_until_operator_authorizes_chutes_oauth_revoke",
            },
            "token_policy": "raw_tokens_never_returned_to_browser_or_api",
        }


class InMemoryChutesOAuthStateStore:
    def __init__(self) -> None:
        self._states: dict[str, ChutesOAuthConnectPlan] = {}

    def save(self, plan: ChutesOAuthConnectPlan) -> None:
        self._states[plan.state] = plan

    def get(self, state: str) -> ChutesOAuthConnectPlan | None:
        return self._states.get(state)

    def pop(self, state: str) -> ChutesOAuthConnectPlan | None:
        return self._states.pop(state, None)


class InMemoryChutesOAuthTokenStore:
    def __init__(self) -> None:
        self.tokens: dict[str, str] = {}

    def store_token(self, user_id: str, kind: str, token: str) -> str:
        if not token:
            raise ChutesOAuthError("Chutes OAuth token exchange returned empty token material")
        secret_ref = _secret_ref_for_token(user_id, kind, token)
        self.tokens[secret_ref] = token
        return secret_ref


class FakeChutesOAuthCodeExchanger:
    def __init__(self, *, account_user_id: str = "chutes_user_1", username: str = "arcuser") -> None:
        self.account_user_id = account_user_id
        self.username = username
        self.calls: list[dict[str, Any]] = []

    def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        client_id: str,
        client_secret_ref: str,
        code_verifier: str,
    ) -> Mapping[str, Any]:
        self.calls.append(
            {
                "code_present": bool(code),
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret_ref_present": bool(client_secret_ref),
                "code_verifier_present": bool(code_verifier),
            }
        )
        if not _clean_text(code):
            raise ChutesOAuthError("Chutes OAuth callback code is required")
        return {
            "access_token": "fake-chutes-access-token-material",
            "refresh_token": "fake-chutes-refresh-token-material",
            "id_token": "fake-chutes-id-token-material",
            "user": {"user_id": self.account_user_id, "username": self.username},
        }


def describe_chutes_oauth_scopes(scopes: tuple[str, ...] | list[str]) -> list[dict[str, str]]:
    descriptions = {
        "openid": "Confirm the connected Chutes identity.",
        "profile": "Read the Chutes account profile name.",
        "chutes:invoke": "Use the connected account for Chutes inference.",
        "account:read": "Read connected account metadata.",
        "usage:read": "Read usage summaries for ArcLink budget checks.",
        "billing:read": "Read billing summaries when ArcLink displays provider billing.",
        "quota:read": "Read quota status for the connected account.",
    }
    return [{"scope": scope, "description": descriptions.get(scope, scope)} for scope in scopes]


def start_chutes_oauth_connect(
    *,
    user_id: str,
    session_id: str,
    config: ChutesOAuthConfig,
    state_store: InMemoryChutesOAuthStateStore,
    scopes: list[str] | tuple[str, ...] | None = None,
    include_usage_read: bool = False,
    include_billing_read: bool = False,
    now: float | None = None,
) -> ChutesOAuthConnectPlan:
    clean_user_id = _safe_segment(user_id, label="user_id")
    clean_session_id = _safe_segment(session_id, label="session_id")
    issued = float(now if now is not None else time.time())
    state = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(48)
    normalized_scopes = _normalize_scopes(
        scopes,
        include_usage_read=include_usage_read,
        include_billing_read=include_billing_read,
    )
    query = urlencode(
        {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "scope": " ".join(normalized_scopes),
            "state": state,
            "code_challenge": _pkce_challenge(code_verifier),
            "code_challenge_method": "S256",
        }
    )
    plan = ChutesOAuthConnectPlan(
        user_id=clean_user_id,
        session_id=clean_session_id,
        state=state,
        csrf_token=csrf_token,
        code_verifier=code_verifier,
        scopes=normalized_scopes,
        authorize_url=f"{config.authorize_url}?{query}",
        created_at=issued,
        expires_at=issued + 10 * 60,
    )
    state_store.save(plan)
    return plan


def complete_chutes_oauth_callback(
    *,
    user_id: str,
    session_id: str,
    state: str,
    csrf_token: str,
    code: str,
    config: ChutesOAuthConfig,
    state_store: InMemoryChutesOAuthStateStore,
    token_store: ChutesOAuthTokenStore,
    exchanger: ChutesOAuthCodeExchanger,
    now: float | None = None,
) -> ChutesOAuthConnection:
    clean_user_id = _safe_segment(user_id, label="user_id")
    clean_session_id = _safe_segment(session_id, label="session_id")
    clean_state = _clean_text(state)
    plan = state_store.get(clean_state)
    if plan is None:
        raise ChutesOAuthError("Chutes OAuth state mismatch")
    if plan.user_id != clean_user_id or plan.session_id != clean_session_id:
        raise ChutesOAuthError("Chutes OAuth callback is not scoped to this user session")
    if not secrets.compare_digest(plan.csrf_token, _clean_text(csrf_token)):
        raise ChutesOAuthError("Chutes OAuth CSRF token mismatch")
    if float(now if now is not None else time.time()) > plan.expires_at:
        state_store.pop(clean_state)
        raise ChutesOAuthError("Chutes OAuth state expired")
    state_store.pop(clean_state)
    token_payload = exchanger.exchange_code(
        code=_clean_text(code),
        redirect_uri=config.redirect_uri,
        client_id=config.client_id,
        client_secret_ref=config.client_secret_ref,
        code_verifier=plan.code_verifier,
    )
    user = token_payload.get("user") if isinstance(token_payload.get("user"), Mapping) else {}
    access_token_ref = token_store.store_token(clean_user_id, "access", _clean_text(token_payload.get("access_token")))
    refresh_token_ref = token_store.store_token(clean_user_id, "refresh", _clean_text(token_payload.get("refresh_token")))
    return ChutesOAuthConnection(
        user_id=clean_user_id,
        account_user_id=_clean_text(user.get("user_id")) or "connected",
        username=_clean_text(user.get("username")) or "connected",
        scopes=plan.scopes,
        access_token_ref=access_token_ref,
        refresh_token_ref=refresh_token_ref,
        connected_at=float(now if now is not None else time.time()),
    )


def disconnect_chutes_oauth(connection: ChutesOAuthConnection, *, revoke_live: bool = False) -> dict[str, Any]:
    if revoke_live:
        raise ChutesOAuthError("Chutes OAuth live revoke is proof-gated until operator authorization")
    return {
        "provider": "chutes",
        "connected": False,
        "revocation": "ready_but_not_executed",
        "live_revoke": "proof_gated_until_operator_authorizes_chutes_oauth_revoke",
        "token_refs_removed": bool(connection.access_token_ref or connection.refresh_token_ref),
    }
