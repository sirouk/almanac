#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Protocol
from urllib import request as urlrequest


CHUTES_API_BASE_URL = "https://api.chutes.ai"
CHUTES_LLM_BASE_URL = "https://llm.chutes.ai/v1"
CHUTES_SECRET_REF_PREFIX = "secret://arclink/chutes/"

_SENSITIVE_FIELD_RE = re.compile(
    r"(?i)^(api_key|key|secret|secret_key|access_token|refresh_token|id_token|client_secret|fingerprint|hotkey_seed)$"
)
_RAW_CHUTES_SECRET_RE = re.compile(r"(?i)\b(?:cpk|cak|crt|csc)_[a-z0-9]")


class ChutesLiveAdapterError(RuntimeError):
    pass


class ChutesSecretResolver(Protocol):
    def resolve_secret(self, secret_ref: str) -> str:
        ...


class ChutesLiveHttpTransport(Protocol):
    def get_json(self, path: str, *, headers: Mapping[str, str] | None = None) -> Mapping[str, Any]:
        ...

    def post_json(
        self,
        path: str,
        payload: Mapping[str, Any],
        *,
        headers: Mapping[str, str] | None = None,
    ) -> Mapping[str, Any]:
        ...

    def delete_json(self, path: str, *, headers: Mapping[str, str] | None = None) -> Mapping[str, Any]:
        ...


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def validate_chutes_secret_ref(secret_ref: str, *, purpose: str = "Chutes credential") -> str:
    clean = _clean_text(secret_ref)
    if not clean.startswith("secret://"):
        raise ChutesLiveAdapterError(f"{purpose} must be a secret:// reference")
    if _RAW_CHUTES_SECRET_RE.search(clean):
        raise ChutesLiveAdapterError(f"{purpose} looks like raw Chutes secret material, not a secret reference")
    return clean


def _path_part(value: Any, *, label: str) -> str:
    clean = _clean_text(value)
    if not clean or "/" in clean or ".." in clean:
        raise ChutesLiveAdapterError(f"{label} is required and must be a single path segment")
    return clean


def _safe_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _redact_chutes_payload(value: Any, *, secret_ref: str = "") -> Any:
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        removed: list[str] = []
        for key, child in value.items():
            key_text = str(key)
            if _SENSITIVE_FIELD_RE.search(key_text):
                if key_text == "api_key" and secret_ref:
                    redacted["secret_ref"] = secret_ref
                removed.append(key_text)
                continue
            redacted[key_text] = _redact_chutes_payload(child, secret_ref=secret_ref)
        if removed:
            redacted["redacted_fields"] = sorted(set(removed))
        return redacted
    if isinstance(value, list):
        return [_redact_chutes_payload(item, secret_ref=secret_ref) for item in value]
    if isinstance(value, str) and _RAW_CHUTES_SECRET_RE.search(value):
        return "[redacted]"
    return value


def _secret_ref_for_api_key(account_secret_ref: str, api_key_id: str) -> str:
    digest = hashlib.sha256(account_secret_ref.encode("utf-8")).hexdigest()[:16]
    safe_key_id = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", _clean_text(api_key_id)).strip("-") or "new"
    return f"{CHUTES_SECRET_REF_PREFIX}api-keys/{digest}/{safe_key_id}"


class UrlLibChutesLiveTransport:
    def __init__(self, *, base_url: str = CHUTES_API_BASE_URL) -> None:
        self.base_url = _clean_text(base_url).rstrip("/") or CHUTES_API_BASE_URL

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Mapping[str, Any]:
        body = None
        request_headers = {"Accept": "application/json", **dict(headers or {})}
        if payload is not None:
            body = json.dumps(dict(payload), sort_keys=True).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        req = urlrequest.Request(
            self.base_url + path,
            data=body,
            headers=request_headers,
            method=method,
        )
        with urlrequest.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
        parsed = json.loads(raw or "{}")
        if not isinstance(parsed, Mapping):
            raise ChutesLiveAdapterError("Chutes live response was not a JSON object")
        return parsed

    def get_json(self, path: str, *, headers: Mapping[str, str] | None = None) -> Mapping[str, Any]:
        return self._request("GET", path, headers=headers)

    def post_json(
        self,
        path: str,
        payload: Mapping[str, Any],
        *,
        headers: Mapping[str, str] | None = None,
    ) -> Mapping[str, Any]:
        return self._request("POST", path, payload=payload, headers=headers)

    def delete_json(self, path: str, *, headers: Mapping[str, str] | None = None) -> Mapping[str, Any]:
        return self._request("DELETE", path, headers=headers)


class ChutesLiveAdapter:
    """Secret-reference boundary for Chutes account, usage, OAuth, and key APIs."""

    def __init__(
        self,
        *,
        credential_ref: str,
        transport: ChutesLiveHttpTransport,
        secret_resolver: ChutesSecretResolver | None = None,
        allow_live_mutation: bool = False,
    ) -> None:
        self.credential_ref = validate_chutes_secret_ref(credential_ref)
        self.transport = transport
        self.secret_resolver = secret_resolver
        self.allow_live_mutation = bool(allow_live_mutation)

    def _auth_headers(self, *, secret_ref: str | None = None) -> dict[str, str]:
        ref = validate_chutes_secret_ref(secret_ref or self.credential_ref)
        if self.secret_resolver is None:
            raise ChutesLiveAdapterError("Chutes live calls require a secret resolver for the configured secret reference")
        material = _clean_text(self.secret_resolver.resolve_secret(ref))
        if not material:
            raise ChutesLiveAdapterError("Chutes secret reference resolved to empty material")
        return {"Authorization": f"Bearer {material}"}

    def _get(self, path: str) -> dict[str, Any]:
        return dict(_redact_chutes_payload(self.transport.get_json(path, headers=self._auth_headers())))

    def _post(self, path: str, payload: Mapping[str, Any], *, secret_ref: str = "") -> dict[str, Any]:
        result = self.transport.post_json(path, payload, headers=self._auth_headers())
        return dict(_redact_chutes_payload(result, secret_ref=secret_ref))

    def _delete(self, path: str) -> dict[str, Any]:
        result = self.transport.delete_json(path, headers=self._auth_headers())
        return dict(_redact_chutes_payload(result))

    def _require_mutation_proof(self, operation: str) -> None:
        if not self.allow_live_mutation:
            raise ChutesLiveAdapterError(f"Chutes {operation} is proof-gated until operator authorizes live mutation")

    def list_models(self) -> dict[str, Any]:
        return self._get("/models")

    def get_me(self) -> dict[str, Any]:
        return self._get("/users/me")

    def get_subscription_usage(self) -> dict[str, Any]:
        return self._get("/users/me/subscription_usage")

    def get_user_usage(
        self,
        user_id: str,
        page: int = 1,
        limit: int = 100,
        *,
        per_chute: bool = False,
        chute_id: str | None = None,
    ) -> dict[str, Any]:
        clean_user_id = _path_part(user_id, label="user_id")
        clean_page = _safe_int(page, default=1, minimum=1, maximum=100000)
        clean_limit = _safe_int(limit, default=100, minimum=1, maximum=1000)
        path = f"/users/{clean_user_id}/usage?page={clean_page}&limit={clean_limit}"
        if per_chute:
            path += "&per_chute=true"
        if chute_id:
            path += f"&chute_id={_path_part(chute_id, label='chute_id')}"
        return self._get(path)

    def get_quota_usage(self, chute_id: str) -> dict[str, Any]:
        return self._get(f"/users/me/quota_usage/{_path_part(chute_id, label='chute_id')}")

    def get_quotas(self) -> dict[str, Any]:
        return self._get("/users/me/quotas")

    def get_discounts(self) -> dict[str, Any]:
        return self._get("/users/me/discounts")

    def get_price_overrides(self) -> dict[str, Any]:
        return self._get("/users/me/price_overrides")

    def list_api_keys(self) -> dict[str, Any]:
        return self._get("/api_keys/")

    def create_api_key(self, name: str, admin: bool = False, scopes: list[str] | None = None) -> dict[str, Any]:
        self._require_mutation_proof("API-key creation")
        clean_name = _clean_text(name)
        if not clean_name:
            raise ChutesLiveAdapterError("API key name is required")
        clean_scopes = [_path_part(scope, label="scope") for scope in _as_list(scopes)]
        result = self.transport.post_json(
            "/api_keys/",
            {"name": clean_name, "admin": bool(admin), "scopes": clean_scopes},
            headers=self._auth_headers(),
        )
        api_key_id = _clean_text(result.get("api_key_id") or result.get("id") or clean_name)
        return dict(_redact_chutes_payload(result, secret_ref=_secret_ref_for_api_key(self.credential_ref, api_key_id)))

    def delete_api_key(self, api_key_id: str) -> dict[str, Any]:
        self._require_mutation_proof("API-key deletion")
        return self._delete(f"/api_keys/{_path_part(api_key_id, label='api_key_id')}")

    def transfer_balance(self, recipient_user_id: str, amount: int | float | str) -> dict[str, Any]:
        self._require_mutation_proof("balance transfer")
        clean_recipient = _path_part(recipient_user_id, label="recipient_user_id")
        try:
            clean_amount = float(amount)
        except (TypeError, ValueError) as exc:
            raise ChutesLiveAdapterError("balance transfer amount must be numeric") from exc
        if clean_amount <= 0:
            raise ChutesLiveAdapterError("balance transfer amount must be positive")
        return self._post("/users/balance_transfer", {"recipient_user_id": clean_recipient, "amount": clean_amount})

    def list_scopes(self) -> dict[str, Any]:
        return self._get("/idp/scopes")

    def introspect_oauth_token(self, token_ref: str) -> dict[str, Any]:
        clean_ref = validate_chutes_secret_ref(token_ref, purpose="Chutes OAuth token")
        if self.secret_resolver is None:
            raise ChutesLiveAdapterError("Chutes token introspection requires a secret resolver for the token reference")
        material = _clean_text(self.secret_resolver.resolve_secret(clean_ref))
        if not material:
            raise ChutesLiveAdapterError("Chutes OAuth token reference resolved to empty material")
        result = self.transport.post_json(
            "/idp/token/introspect",
            {"token": material},
            headers=self._auth_headers(),
        )
        public = dict(_redact_chutes_payload(result))
        public["token_ref_present"] = True
        return public


class FakeChutesLiveTransport:
    """Fixture-backed Chutes transport for no-secret adapter proof."""

    def __init__(self, fixtures: Mapping[str, Any] | None = None) -> None:
        self.fixtures = dict(fixtures or default_chutes_live_fixtures())
        self.calls: list[dict[str, Any]] = []
        self.created_keys: dict[str, dict[str, Any]] = {}

    def _record(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> None:
        self.calls.append({"method": method, "path": path, "payload_keys": sorted((payload or {}).keys())})

    def get_json(self, path: str, *, headers: Mapping[str, str] | None = None) -> Mapping[str, Any]:
        self._record("GET", path)
        if path == "/models":
            return self.fixtures["models"]
        if path == "/users/me":
            return self.fixtures["me"]
        if path == "/users/me/subscription_usage":
            return self.fixtures["subscription_usage"]
        if path.startswith("/users/") and "/usage" in path:
            return self.fixtures["user_usage"]
        if path.startswith("/users/me/quota_usage/"):
            return self.fixtures["quota_usage"]
        if path == "/users/me/quotas":
            return self.fixtures["quotas"]
        if path == "/users/me/discounts":
            return self.fixtures["discounts"]
        if path == "/users/me/price_overrides":
            return self.fixtures["price_overrides"]
        if path == "/api_keys/":
            keys = list(self.fixtures["api_keys"].get("items", [])) + list(self.created_keys.values())
            return {"items": keys}
        if path == "/idp/scopes":
            return self.fixtures["scopes"]
        raise ChutesLiveAdapterError(f"unhandled fake Chutes GET path: {path}")

    def post_json(
        self,
        path: str,
        payload: Mapping[str, Any],
        *,
        headers: Mapping[str, str] | None = None,
    ) -> Mapping[str, Any]:
        self._record("POST", path, payload)
        if path == "/api_keys/":
            api_key_id = f"fake_key_{len(self.created_keys) + 1}"
            record = {
                "api_key_id": api_key_id,
                "user_id": self.fixtures["me"].get("user_id", "chutes-user"),
                "name": payload.get("name", ""),
                "admin": bool(payload.get("admin")),
                "scopes": _as_list(payload.get("scopes")),
                "api_key": "one-time-provider-secret-redacted-by-boundary",
                "created_at": "2026-05-09T00:00:00Z",
            }
            self.created_keys[api_key_id] = dict(record)
            return record
        if path == "/users/balance_transfer":
            return {
                "status": "fake_not_executed",
                "recipient_user_id": payload.get("recipient_user_id", ""),
                "amount": payload.get("amount", 0),
                "live_status": "proof_gated_until_authorized_provider_transfer",
            }
        if path == "/idp/token/introspect":
            return self.fixtures["token_introspection"]
        raise ChutesLiveAdapterError(f"unhandled fake Chutes POST path: {path}")

    def delete_json(self, path: str, *, headers: Mapping[str, str] | None = None) -> Mapping[str, Any]:
        self._record("DELETE", path)
        prefix = "/api_keys/"
        if not path.startswith(prefix):
            raise ChutesLiveAdapterError(f"unhandled fake Chutes DELETE path: {path}")
        api_key_id = path[len(prefix):]
        self.created_keys.pop(api_key_id, None)
        return {"api_key_id": api_key_id, "deleted": True}


class StaticSecretResolver:
    def __init__(self, secrets: Mapping[str, str]) -> None:
        self.secrets = dict(secrets)

    def resolve_secret(self, secret_ref: str) -> str:
        clean = validate_chutes_secret_ref(secret_ref)
        try:
            return self.secrets[clean]
        except KeyError as exc:
            raise ChutesLiveAdapterError("missing Chutes secret reference material") from exc


def default_chutes_live_fixtures() -> dict[str, Any]:
    return {
        "models": {
            "data": [
                {
                    "id": "moonshotai/Kimi-K2.6-TEE",
                    "object": "model",
                    "chute_id": "kimi-k2-6-tee",
                    "pricing": {"input_per_million": 0.95, "output_per_million": 4.0},
                    "capabilities": {"tools": True, "reasoning": True, "structured_outputs": True},
                }
            ]
        },
        "me": {"user_id": "chutes_user_1", "username": "arcuser", "status": "active"},
        "subscription_usage": {
            "period_start": "2026-05-01T00:00:00Z",
            "period_end": "2026-06-01T00:00:00Z",
            "usage_cents": 123,
            "currency": "usd",
        },
        "user_usage": {
            "items": [
                {
                    "chute_id": "kimi-k2-6-tee",
                    "requests": 3,
                    "input_tokens": 1200,
                    "output_tokens": 800,
                    "usage_cents": 12,
                }
            ],
            "page": 1,
            "limit": 100,
        },
        "quota_usage": {"chute_id": "kimi-k2-6-tee", "used": 3, "limit": 100},
        "quotas": {"items": [{"name": "default", "limit": 100, "period": "day"}]},
        "discounts": {"items": [{"scope": "account", "percent": 10}]},
        "price_overrides": {"items": [{"chute_id": "kimi-k2-6-tee", "input_per_million": 0.9}]},
        "api_keys": {
            "items": [
                {
                    "api_key_id": "fake_existing_key",
                    "user_id": "chutes_user_1",
                    "name": "ArcLink read",
                    "admin": False,
                    "scopes": ["chutes:invoke"],
                    "created_at": "2026-05-01T00:00:00Z",
                    "last_used_at": "2026-05-08T00:00:00Z",
                }
            ]
        },
        "scopes": {
            "items": [
                {"scope": "openid", "description": "OpenID identity"},
                {"scope": "profile", "description": "Basic profile"},
                {"scope": "chutes:invoke", "description": "Invoke Chutes inference"},
                {"scope": "account:read", "description": "Read account metadata"},
                {"scope": "billing:read", "description": "Read billing summaries"},
                {"scope": "quota:read", "description": "Read quotas"},
                {"scope": "usage:read", "description": "Read usage summaries"},
            ]
        },
        "token_introspection": {
            "active": True,
            "sub": "chutes_user_1",
            "scope": "openid profile chutes:invoke account:read",
            "exp": 1770000000,
        },
    }
