#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _load_provider_spec(raw_json: str) -> dict[str, Any]:
    payload = json.loads(raw_json)
    if not isinstance(payload, dict):
        raise SystemExit("provider spec must be a json object")
    return payload


def _read_secret(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read().strip()


def _ensure_model_config(default_model: str) -> dict[str, Any]:
    from hermes_cli.config import load_config

    config = load_config()
    model_cfg = config.get("model")
    if isinstance(model_cfg, dict):
        payload = dict(model_cfg)
    elif isinstance(model_cfg, str) and model_cfg.strip():
        payload = {"default": model_cfg.strip()}
    else:
        payload = {}
    if not payload.get("default"):
        payload["default"] = default_model
    config["model"] = payload
    return config


def _seed_openai_codex(spec: dict[str, Any], secret_path: str) -> None:
    from hermes_cli.auth import _save_codex_tokens, _update_config_for_provider

    payload = json.loads(_read_secret(secret_path))
    if not isinstance(payload, dict):
        raise SystemExit("codex secret payload is invalid")
    tokens = {
        "access_token": str(payload.get("access_token") or ""),
        "refresh_token": str(payload.get("refresh_token") or ""),
    }
    if not tokens["access_token"] or not tokens["refresh_token"]:
        raise SystemExit("codex secret payload is missing tokens")
    _save_codex_tokens(tokens, last_refresh=str(payload.get("last_refresh") or "") or None)
    _update_config_for_provider(
        "openai-codex",
        str(payload.get("base_url") or spec.get("base_url") or ""),
        default_model=str(spec.get("model_id") or "gpt-5.4"),
    )


def _seed_anthropic(spec: dict[str, Any], secret_path: str) -> None:
    from hermes_cli.config import load_config, save_anthropic_api_key, save_anthropic_oauth_token, save_config

    secret = _read_secret(secret_path)
    if secret.startswith("sk-ant-api-"):
        save_anthropic_api_key(secret)
    else:
        save_anthropic_oauth_token(secret)

    config = load_config()
    model_cfg = config.get("model")
    if isinstance(model_cfg, dict):
        payload = dict(model_cfg)
    elif isinstance(model_cfg, str) and model_cfg.strip():
        payload = {"default": model_cfg.strip()}
    else:
        payload = {}
    payload["provider"] = "anthropic"
    payload["default"] = str(spec.get("model_id") or "claude-opus-4-6")
    payload.pop("base_url", None)
    config["model"] = payload
    save_config(config)


def _seed_custom_provider(spec: dict[str, Any], secret_path: str) -> None:
    from hermes_cli.config import load_config, save_config, save_env_value

    provider_id = str(spec.get("provider_id") or "").strip()
    key_env = str(spec.get("key_env") or "").strip()
    base_url = str(spec.get("base_url") or "").strip()
    model_id = str(spec.get("model_id") or "").strip()
    api_mode = str(spec.get("api_mode") or "").strip() or "chat_completions"
    display_name = str(spec.get("display_name") or provider_id).strip() or provider_id
    if not provider_id or not key_env or not base_url or not model_id:
        raise SystemExit("custom provider spec is incomplete")

    save_env_value(key_env, _read_secret(secret_path))
    config = _ensure_model_config(model_id)
    providers = config.get("providers")
    if not isinstance(providers, dict):
        providers = {}
    providers[provider_id] = {
        "name": display_name,
        "base_url": base_url,
        "key_env": key_env,
        "default_model": model_id,
        "api_mode": api_mode,
    }
    config["providers"] = providers
    model_cfg = dict(config.get("model") or {})
    model_cfg["provider"] = provider_id
    model_cfg["default"] = model_id
    model_cfg["base_url"] = base_url
    model_cfg["api_mode"] = api_mode
    config["model"] = model_cfg
    save_config(config)


def _seed_api_key_provider(spec: dict[str, Any], secret_path: str) -> None:
    from hermes_cli.auth import _update_config_for_provider
    from hermes_cli.config import save_env_value

    provider_id = str(spec.get("provider_id") or "").strip()
    key_env = str(spec.get("key_env") or "").strip()
    model_id = str(spec.get("model_id") or "").strip()
    if not provider_id or not key_env or not model_id:
        raise SystemExit("api-key provider spec is incomplete")

    save_env_value(key_env, _read_secret(secret_path))
    _update_config_for_provider(
        provider_id,
        str(spec.get("base_url") or ""),
        default_model=model_id,
    )


def _seed_almanac_prefill(bot_name: str, unix_user: str) -> str:
    from hermes_cli.config import load_config, save_config

    label = bot_name.strip() or "your Almanac agent"
    unix_user = unix_user.strip()
    hermes_home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    state_dir = hermes_home / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    prefill_path = state_dir / "almanac-prefill-messages.json"
    prefill_messages = [
        {
            "role": "system",
            "content": (
                f"Your public-facing bot name is {label}. Introduce yourself as {label}, "
                "not Hermes, unless you are explicitly explaining that Hermes is the runtime "
                "you run on. You are an Almanac user agent on a shared host"
                + (f" for unix user {unix_user}." if unix_user else ".")
                + " You already have the Almanac MCP and qmd MCP wired in, plus the default "
                "Almanac skills for first contact, vault work, vault reconciliation, and SSOT "
                "coordination. For vault-relevant questions, prefer qmd and Almanac resources "
                "before the public web. Respect shared-host boundaries and operate only within "
                "the current user's authorized Hermes home, channels, and Almanac resources."
            ),
        }
    ]
    prefill_path.write_text(json.dumps(prefill_messages, indent=2) + "\n", encoding="utf-8")

    config = load_config()
    config["prefill_messages_file"] = str(prefill_path)
    save_config(config)
    return str(prefill_path)


def _validate_runtime(spec: dict[str, Any]) -> dict[str, Any]:
    from hermes_cli.config import load_config
    from hermes_cli.runtime_provider import resolve_runtime_provider

    runtime = resolve_runtime_provider(requested=str(spec.get("provider_id") or ""))
    config = load_config()
    model_cfg = config.get("model")
    if isinstance(model_cfg, dict):
        model_id = str(model_cfg.get("default") or "")
        provider_id = str(model_cfg.get("provider") or "")
    else:
        model_id = str(model_cfg or "")
        provider_id = ""
    return {
        "provider": runtime.get("provider"),
        "base_url": runtime.get("base_url"),
        "api_mode": runtime.get("api_mode"),
        "model": model_id,
        "configured_provider": provider_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a Hermes home for headless Almanac onboarding.")
    parser.add_argument("--provider-spec-json", help="Provider setup spec as json.")
    parser.add_argument("--secret-path", help="Path to the staged provider secret.")
    parser.add_argument("--bot-name", default="", help="Public-facing bot name for Almanac prefill priming.")
    parser.add_argument("--unix-user", default="", help="Unix username being provisioned.")
    parser.add_argument("--prefill-only", action="store_true", help="Only refresh the Almanac prefill config.")
    args = parser.parse_args()

    prefill_path = _seed_almanac_prefill(args.bot_name, args.unix_user)
    if args.prefill_only:
        print(json.dumps({"prefill_messages_file": prefill_path, "prefill_only": True}, sort_keys=True))
        return

    if not args.provider_spec_json or not args.secret_path:
        raise SystemExit("--provider-spec-json and --secret-path are required unless --prefill-only is set")

    spec = _load_provider_spec(args.provider_spec_json)
    provider_id = str(spec.get("provider_id") or "").strip()
    if provider_id == "openai-codex":
        _seed_openai_codex(spec, args.secret_path)
    elif provider_id == "anthropic":
        _seed_anthropic(spec, args.secret_path)
    elif bool(spec.get("is_custom")):
        _seed_custom_provider(spec, args.secret_path)
    else:
        _seed_api_key_provider(spec, args.secret_path)

    print(json.dumps(_validate_runtime(spec), sort_keys=True))


if __name__ == "__main__":
    main()
