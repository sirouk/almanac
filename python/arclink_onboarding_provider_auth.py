#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.parse
from dataclasses import asdict, dataclass
from typing import Any

from arclink_http import http_request, parse_json_object
from arclink_model_providers import provider_default_model


CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_ISSUER = "https://auth.openai.com"
CODEX_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
ANTHROPIC_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
ANTHROPIC_OAUTH_AUTHORIZE_URL = "https://claude.ai/oauth/authorize"
ANTHROPIC_OAUTH_TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
ANTHROPIC_OAUTH_REDIRECT_URI = "https://console.anthropic.com/oauth/code/callback"
ANTHROPIC_OAUTH_SCOPES = "org:create_api_key user:profile user:inference"
ANTHROPIC_OAUTH_SCOPE_LIST = tuple(scope for scope in ANTHROPIC_OAUTH_SCOPES.split() if scope)
CHUTES_BASE_URL = "https://llm.chutes.ai/v1"
REASONING_EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "none")
DEFAULT_CODEX_MODEL = provider_default_model("codex") or "gpt-5.5"
DEFAULT_OPUS_MODEL = provider_default_model("opus") or "claude-opus-4-7"


@dataclass(frozen=True)
class ProviderSetupSpec:
    preset: str
    provider_id: str
    model_id: str
    display_name: str
    auth_flow: str
    key_env: str = ""
    base_url: str = ""
    api_mode: str = ""
    is_custom: bool = False
    reasoning_effort: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def provider_setup_from_dict(raw: dict[str, Any] | None) -> ProviderSetupSpec | None:
    if not isinstance(raw, dict):
        return None
    provider_id = str(raw.get("provider_id") or "").strip()
    model_id = str(raw.get("model_id") or "").strip()
    auth_flow = str(raw.get("auth_flow") or "").strip()
    if not provider_id or not model_id or not auth_flow:
        return None
    return ProviderSetupSpec(
        preset=str(raw.get("preset") or "").strip(),
        provider_id=provider_id,
        model_id=model_id,
        display_name=str(raw.get("display_name") or provider_id).strip() or provider_id,
        auth_flow=auth_flow,
        key_env=str(raw.get("key_env") or "").strip(),
        base_url=str(raw.get("base_url") or "").strip(),
        api_mode=str(raw.get("api_mode") or "").strip(),
        is_custom=bool(raw.get("is_custom")),
        reasoning_effort=normalize_reasoning_effort(str(raw.get("reasoning_effort") or ""), default="medium"),
    )


def normalize_reasoning_effort(raw_value: str, *, default: str = "") -> str:
    value = str(raw_value or "").strip().lower().replace(" ", "")
    aliases = {
        "": default,
        "default": default or "medium",
        "recommended": default or "medium",
        "normal": "medium",
        "standard": "medium",
        "med": "medium",
        "extra": "xhigh",
        "extrahigh": "xhigh",
        "veryhigh": "xhigh",
        "max": "xhigh",
        "maximum": "xhigh",
        "off": "none",
        "disabled": "none",
        "disable": "none",
        "no": "none",
        "false": "none",
    }
    value = aliases.get(value, value)
    return value if value in REASONING_EFFORTS else ""


def _chutes_model_for_reasoning(model_id: str, reasoning_effort: str) -> str:
    base_model = str(model_id or "").strip()
    if base_model.upper().endswith(":THINKING"):
        base_model = base_model[: -len(":THINKING")]
    effort = normalize_reasoning_effort(reasoning_effort)
    if effort and effort != "none":
        return f"{base_model}:THINKING"
    return base_model


def resolve_provider_setup(
    cfg: Any,
    preset: str,
    *,
    model_id: str = "",
    reasoning_effort: str = "",
) -> ProviderSetupSpec:
    normalized_preset = str(preset or "").strip().lower() or "codex"
    raw_target = str(getattr(cfg, "model_presets", {}).get(normalized_preset) or "").strip()
    if not raw_target or ":" not in raw_target:
        raise ValueError(f"Model preset `{normalized_preset}` is not configured for headless onboarding.")

    provider_hint, model_hint = raw_target.split(":", 1)
    provider_hint = provider_hint.strip().lower()
    model_hint = model_hint.strip()
    requested_model_id = str(model_id or "").strip() or model_hint
    normalized_reasoning_effort = normalize_reasoning_effort(reasoning_effort, default="medium")
    if not provider_hint or not model_hint:
        raise ValueError(f"Model preset `{normalized_preset}` is incomplete: {raw_target}")

    if provider_hint == "openai" and model_hint.lower() == "codex":
        return ProviderSetupSpec(
            preset=normalized_preset,
            provider_id="openai-codex",
            model_id=requested_model_id
            if requested_model_id.lower() not in {"codex", "openai:codex"}
            else DEFAULT_CODEX_MODEL,
            display_name="OpenAI Codex",
            auth_flow="codex-device",
            base_url=CODEX_BASE_URL,
            reasoning_effort=normalized_reasoning_effort,
        )

    if provider_hint == "anthropic" and model_hint.lower() in {"claude-opus", "opus"}:
        return ProviderSetupSpec(
            preset=normalized_preset,
            provider_id="anthropic",
            model_id=_normalize_anthropic_model(
                requested_model_id
                if requested_model_id.lower() not in {"claude-opus", "opus"}
                else DEFAULT_OPUS_MODEL
            ),
            display_name="Claude Opus",
            auth_flow="anthropic-credential",
            reasoning_effort=normalized_reasoning_effort,
        )

    if provider_hint == "chutes":
        return ProviderSetupSpec(
            preset=normalized_preset,
            provider_id="chutes",
            model_id=_chutes_model_for_reasoning(requested_model_id, normalized_reasoning_effort),
            display_name="Chutes",
            auth_flow="api-key",
            key_env="CHUTES_API_KEY",
            base_url=CHUTES_BASE_URL,
            api_mode="chat_completions",
            is_custom=True,
            reasoning_effort=normalized_reasoning_effort,
        )

    if provider_hint == "openai-codex":
        return ProviderSetupSpec(
            preset=normalized_preset,
            provider_id="openai-codex",
            model_id=requested_model_id or DEFAULT_CODEX_MODEL,
            display_name="OpenAI Codex",
            auth_flow="codex-device",
            base_url=CODEX_BASE_URL,
            reasoning_effort=normalized_reasoning_effort,
        )

    if provider_hint == "anthropic":
        return ProviderSetupSpec(
            preset=normalized_preset,
            provider_id="anthropic",
            model_id=_normalize_anthropic_model(requested_model_id),
            display_name="Anthropic",
            auth_flow="anthropic-credential",
            reasoning_effort=normalized_reasoning_effort,
        )

    generic_api_key_providers: dict[str, tuple[str, str, str]] = {
        "openrouter": ("OpenRouter", "OPENROUTER_API_KEY", ""),
        "gemini": ("Google AI Studio", "GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai"),
        "zai": ("Z.AI / GLM", "GLM_API_KEY", "https://api.z.ai/api/paas/v4"),
        "kimi-coding": ("Kimi / Moonshot", "KIMI_API_KEY", "https://api.moonshot.ai/v1"),
        "minimax": ("MiniMax", "MINIMAX_API_KEY", "https://api.minimax.io/anthropic"),
        "deepseek": ("DeepSeek", "DEEPSEEK_API_KEY", "https://api.deepseek.com/v1"),
        "xai": ("xAI", "XAI_API_KEY", "https://api.x.ai/v1"),
        "alibaba": ("Alibaba Cloud (DashScope)", "DASHSCOPE_API_KEY", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
        "arcee": ("Arcee AI", "ARCEEAI_API_KEY", "https://api.arcee.ai/api/v1"),
    }
    generic = generic_api_key_providers.get(provider_hint)
    if generic:
        display_name, key_env, base_url = generic
        return ProviderSetupSpec(
            preset=normalized_preset,
            provider_id=provider_hint,
            model_id=requested_model_id,
            display_name=display_name,
            auth_flow="api-key",
            key_env=key_env,
            base_url=base_url,
            reasoning_effort=normalized_reasoning_effort,
        )

    raise ValueError(
        f"Model preset `{normalized_preset}` targets `{raw_target}`, which is not supported by headless onboarding yet."
    )


def provider_secret_name(spec: ProviderSetupSpec) -> str:
    if spec.provider_id == "openai-codex":
        return "openai-codex-oauth"
    if spec.provider_id == "anthropic":
        return "anthropic-credential"
    if spec.key_env:
        return spec.key_env.lower()
    return f"{spec.provider_id}-credential"


def provider_credential_prompt(spec: ProviderSetupSpec, *, shared_credential_available: bool = False) -> str:
    if spec.auth_flow == "anthropic-credential":
        return (
            f"One more thing for {spec.display_name}: this lane uses Claude Code OAuth, not an Anthropic API key.\n\n"
            "Reply `oauth` and I’ll create a browser sign-in link.\n\n"
            "After you authorize, Claude will show a callback code string. Paste that whole string back here and I’ll store the refreshable Claude Code credentials privately for this agent."
        )
    if spec.auth_flow == "api-key":
        runtime_note = (
            "I can only validate that the credential is present here; live provider validation happens during provisioning."
        )
        if shared_credential_available:
            if spec.provider_id == "chutes":
                return (
                    "Your team already provided a Chutes API key for this lane.\n\n"
                    "Reply `default` to use it.\n"
                    "Or paste a different Chutes API key if you prefer.\n\n"
                    f"I’ll use model `{spec.model_id}`.\n\n"
                    f"{runtime_note}"
                )
            return (
                f"Your team already provided a {spec.display_name} API key for this lane.\n\n"
                "Reply `default` to use it, or paste a different key if you prefer.\n\n"
                f"{runtime_note}"
            )
        if spec.provider_id == "chutes":
            return (
                "One more thing for Chutes: send the Chutes API key for this agent lane.\n\n"
                "I’ll store it privately and wire it into Hermes. "
                "Runtime validation is pending until provisioning reaches the provider.\n\n"
                f"Model: `{spec.model_id}`"
            )
        return (
            f"One more thing for {spec.display_name}: send the API key for this agent lane.\n\n"
            "I’ll store it privately and wire it into Hermes. "
            "Runtime validation is pending until provisioning reaches the provider."
        )
    if spec.auth_flow == "codex-device":
        return "One more thing for OpenAI Codex: I’m creating a sign-in code for you now."
    return f"Send the credential for {spec.display_name} now."


def provider_browser_auth_prompt(spec: ProviderSetupSpec, auth_state: dict[str, Any]) -> str:
    if spec.auth_flow == "codex-device":
        status = str(auth_state.get("status") or "pending").strip().lower()
        if status == "expired":
            return "That OpenAI Codex sign-in code expired. Send `restart` and I’ll mint a fresh one."
        if status == "error":
            return (
                f"OpenAI Codex sign-in hit an error: {auth_state.get('error_message') or 'unknown error'}. "
                "Send `restart` and I’ll try again."
            )
        return (
            "OpenAI Codex sign-in:\n"
            f"1. Open {auth_state.get('verification_url') or f'{CODEX_ISSUER}/codex/device'}\n"
            f"2. Enter this code: `{auth_state.get('user_code') or '(missing)'}`\n\n"
            "You do not need to paste anything here. I’ll keep watching and continue automatically once OpenAI approves it."
        )

    if spec.provider_id == "anthropic":
        return (
            f"Claude Code OAuth for {spec.display_name}:\n\n"
            "Open this link with the Claude account you want tied to this lane, such as Claude Max:\n"
            f"{auth_state.get('auth_url') or '(missing auth url)'}\n"
            "\nWhen Claude shows the callback code, paste the whole code string back here.\n\n"
            "No Anthropic API key or setup token is needed. ArcLink stores Claude Code credentials privately for this agent.\n"
            "If the link goes stale, reply `restart` and I’ll mint a fresh one."
        )

    return f"Finish browser authorization for {spec.display_name} and come back here."


def start_codex_device_authorization() -> dict[str, Any]:
    payload = _request_json(
        f"{CODEX_ISSUER}/api/accounts/deviceauth/usercode",
        payload={"client_id": CODEX_OAUTH_CLIENT_ID},
        headers={"Content-Type": "application/json"},
    )
    user_code = str(payload.get("user_code") or "").strip()
    device_auth_id = str(payload.get("device_auth_id") or "").strip()
    interval = max(3, int(payload.get("interval") or 5))
    if not user_code or not device_auth_id:
        raise RuntimeError("OpenAI device auth did not return a usable code.")
    expires_in = 15 * 60
    return {
        "flow": "device_code",
        "provider": "openai-codex",
        "user_code": user_code,
        "device_auth_id": device_auth_id,
        "verification_url": f"{CODEX_ISSUER}/codex/device",
        "poll_interval": interval,
        "status": "pending",
        "started_at": int(time.time()),
        "expires_in": expires_in,
        "expires_at": int(time.time()) + expires_in,
    }


def poll_codex_device_authorization(auth_state: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    updated = dict(auth_state or {})
    if not updated:
        raise RuntimeError("OpenAI Codex authorization state is missing.")
    if int(updated.get("expires_at") or 0) <= int(time.time()):
        updated["status"] = "expired"
        updated["error_message"] = "Device code expired before approval."
        return None, updated

    response = _request_json(
        f"{CODEX_ISSUER}/api/accounts/deviceauth/token",
        payload={
            "device_auth_id": str(updated.get("device_auth_id") or ""),
            "user_code": str(updated.get("user_code") or ""),
        },
        headers={"Content-Type": "application/json"},
        pending_statuses=(403, 404),
    )
    if response is None:
        return None, updated

    authorization_code = str(response.get("authorization_code") or "").strip()
    code_verifier = str(response.get("code_verifier") or "").strip()
    if not authorization_code or not code_verifier:
        updated["status"] = "error"
        updated["error_message"] = "OpenAI device auth returned an incomplete authorization response."
        return None, updated

    tokens = _request_json(
        CODEX_OAUTH_TOKEN_URL,
        form_payload={
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": f"{CODEX_ISSUER}/deviceauth/callback",
            "client_id": CODEX_OAUTH_CLIENT_ID,
            "code_verifier": code_verifier,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    access_token = str(tokens.get("access_token") or "").strip()
    refresh_token = str(tokens.get("refresh_token") or "").strip()
    if not access_token or not refresh_token:
        updated["status"] = "error"
        updated["error_message"] = "OpenAI token exchange did not return both access and refresh tokens."
        return None, updated

    updated["status"] = "approved"
    updated["approved_at"] = int(time.time())
    return (
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "last_refresh": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "base_url": CODEX_BASE_URL,
        },
        updated,
    )


def start_anthropic_pkce_authorization() -> dict[str, Any]:
    verifier, challenge = _generate_pkce_pair()
    params = {
        "code": "true",
        "client_id": ANTHROPIC_OAUTH_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": ANTHROPIC_OAUTH_REDIRECT_URI,
        "scope": ANTHROPIC_OAUTH_SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": verifier,
    }
    return {
        "flow": "claude_code_oauth",
        "provider": "anthropic",
        "status": "pending",
        "verifier": verifier,
        "state": verifier,
        "auth_url": f"{ANTHROPIC_OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}",
        "started_at": int(time.time()),
    }


def complete_anthropic_pkce_authorization(
    auth_state: dict[str, Any],
    code_input: str,
) -> tuple[str, dict[str, Any]]:
    updated = dict(auth_state or {})
    code_parts = str(code_input or "").strip().split("#", 1)
    code = code_parts[0].strip()
    callback_state = code_parts[1].strip() if len(code_parts) > 1 else ""
    if not code:
        raise RuntimeError("Claude did not return a usable authorization code.")

    response = _request_json(
        ANTHROPIC_OAUTH_TOKEN_URL,
        payload={
            "grant_type": "authorization_code",
            "client_id": ANTHROPIC_OAUTH_CLIENT_ID,
            "code": code,
            "state": callback_state or str(updated.get("state") or ""),
            "redirect_uri": ANTHROPIC_OAUTH_REDIRECT_URI,
            "code_verifier": str(updated.get("verifier") or ""),
        },
        headers={
            "Content-Type": "application/json",
            "User-Agent": "arclink-curator-onboarding/1.0",
        },
    )
    access_token = str(response.get("access_token") or "").strip()
    if not access_token:
        raise RuntimeError("Claude token exchange did not return an access token.")
    refresh_token = str(response.get("refresh_token") or "").strip()
    if not refresh_token:
        raise RuntimeError("Claude token exchange did not return a refresh token.")
    try:
        expires_in = int(response.get("expires_in") or 3600)
    except (TypeError, ValueError):
        expires_in = 3600
    expires_at_ms = int(time.time() * 1000) + (max(60, expires_in) * 1000)
    raw_scope = response.get("scope")
    if isinstance(raw_scope, str) and raw_scope.strip():
        scopes = [scope for scope in raw_scope.split() if scope]
    elif isinstance(raw_scope, list):
        scopes = [str(scope).strip() for scope in raw_scope if str(scope).strip()]
    else:
        scopes = list(ANTHROPIC_OAUTH_SCOPE_LIST)

    updated["status"] = "approved"
    updated["approved_at"] = int(time.time())
    updated["credential_shape"] = "claude_code_credentials"
    credential_payload = {
        "kind": "claude_code_oauth",
        "accessToken": access_token,
        "refreshToken": refresh_token,
        "expiresAt": expires_at_ms,
        "scopes": scopes,
    }
    return json.dumps(credential_payload, sort_keys=True), updated


def normalize_anthropic_credential(raw_value: str) -> str:
    raise RuntimeError(
        "Claude Opus onboarding is OAuth-only. Reply `oauth` to use the Claude Code OAuth flow; "
        "do not send Anthropic API keys or Claude setup tokens."
    )


def normalize_api_key_credential(spec: ProviderSetupSpec, raw_value: str) -> str:
    value = str(raw_value or "").strip()
    if not value:
        raise RuntimeError(f"That {spec.display_name} credential was empty.")
    return value


def _normalize_anthropic_model(raw_model: str) -> str:
    normalized = str(raw_model or "").strip()
    if not normalized:
        return DEFAULT_OPUS_MODEL
    if normalized.lower().startswith("anthropic/"):
        normalized = normalized.split("/", 1)[1]
    return normalized.replace(".", "-")


def _generate_pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("utf-8")).digest()).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _request_json(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    form_payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
    pending_statuses: tuple[int, ...] = (),
) -> dict[str, Any] | None:
    if payload is not None and form_payload is not None:
        raise ValueError("choose either payload or form_payload")
    request_headers = dict(headers or {})
    response = http_request(
        url,
        method="POST",
        headers=request_headers,
        json_payload=payload,
        form_payload=form_payload,
        timeout=timeout,
        allow_loopback_http=False,
    )
    if response.status_code in pending_statuses:
        return None
    if response.status_code >= 400:
        raise RuntimeError(f"{url} returned {response.status_code}: {response.text[:200]}")
    return parse_json_object(response, label=url)
