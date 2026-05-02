#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping


DEFAULT_MODEL_PROVIDERS: dict[str, dict[str, Any]] = {
    "chutes": {
        "display_name": "Chutes",
        "target": "chutes:moonshotai/Kimi-K2.6-TEE",
        "default_model": "moonshotai/Kimi-K2.6-TEE",
        "recommended_models": ["moonshotai/Kimi-K2.6-TEE", "zai-org/GLM-5.1-TEE", "model-router"],
        "legacy_default_targets": ["chutes:auto-failover", "chutes:model-router"],
        "legacy_default_models": ["auto-failover", "model-router"],
    },
    "opus": {
        "display_name": "Claude Opus",
        "target": "anthropic:claude-opus-4-7",
        "default_model": "claude-opus-4-7",
        "recommended_models": ["claude-opus-4-7"],
        "legacy_default_targets": ["anthropic:claude-opus", "anthropic:opus"],
        "legacy_default_models": ["claude-opus", "opus"],
    },
    "codex": {
        "display_name": "OpenAI Codex",
        "target": "openai-codex:gpt-5.5",
        "default_model": "gpt-5.5",
        "recommended_models": ["gpt-5.5"],
        "legacy_default_targets": ["openai:codex", "openai-codex:codex"],
        "legacy_default_models": ["codex", "openai:codex"],
    },
}


def model_providers_path(repo_dir: Path | str | None = None, env: Mapping[str, str] | None = None) -> Path:
    env = env or os.environ
    configured = str(env.get("ARCLINK_MODEL_PROVIDERS_FILE") or "").strip()
    if configured:
        return Path(configured).expanduser()
    base = Path(repo_dir).expanduser() if repo_dir is not None else Path(__file__).resolve().parents[1]
    return base / "config" / "model-providers.yaml"


def _load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import yaml  # type: ignore
    except Exception:
        return {}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_model_providers(repo_dir: Path | str | None = None, env: Mapping[str, str] | None = None) -> dict[str, dict[str, Any]]:
    data = _load_yaml_file(model_providers_path(repo_dir, env))
    providers = data.get("providers") if isinstance(data, dict) else None
    merged = {key: dict(value) for key, value in DEFAULT_MODEL_PROVIDERS.items()}
    if isinstance(providers, dict):
        for key, value in providers.items():
            normalized_key = str(key or "").strip().lower()
            if not normalized_key or not isinstance(value, dict):
                continue
            base = dict(merged.get(normalized_key) or {})
            base.update(value)
            merged[normalized_key] = base
    return merged


def provider_entry(preset: str, repo_dir: Path | str | None = None, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    normalized = str(preset or "").strip().lower()
    return dict(load_model_providers(repo_dir, env).get(normalized) or {})


def provider_preset_target(preset: str, repo_dir: Path | str | None = None, env: Mapping[str, str] | None = None) -> str:
    entry = provider_entry(preset, repo_dir, env)
    return str(entry.get("target") or "").strip()


def provider_default_model(preset: str, repo_dir: Path | str | None = None, env: Mapping[str, str] | None = None) -> str:
    entry = provider_entry(preset, repo_dir, env)
    model = str(entry.get("default_model") or "").strip()
    if model:
        return model
    target = str(entry.get("target") or "").strip()
    return target.split(":", 1)[1].strip() if ":" in target else target


def provider_recommended_models(preset: str, repo_dir: Path | str | None = None, env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    entry = provider_entry(preset, repo_dir, env)
    models = entry.get("recommended_models")
    if isinstance(models, list):
        return tuple(str(model).strip() for model in models if str(model).strip())
    default_model = provider_default_model(preset, repo_dir, env)
    return (default_model,) if default_model else ()


def resolve_preset_target(
    preset: str,
    raw_target: str,
    repo_dir: Path | str | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    normalized = str(preset or "").strip().lower()
    entry = provider_entry(normalized, repo_dir, env)
    default_target = str(entry.get("target") or "").strip()
    candidate = str(raw_target or "").strip()
    if not candidate:
        return default_target
    legacy_targets = {str(value).strip().lower() for value in entry.get("legacy_default_targets", []) if str(value).strip()}
    legacy_models = {str(value).strip().lower() for value in entry.get("legacy_default_models", []) if str(value).strip()}
    provider_hint, _, model_hint = candidate.partition(":")
    if candidate.lower() in legacy_targets or model_hint.strip().lower() in legacy_models:
        return default_target
    if normalized == "codex" and provider_hint.strip().lower() == "openai" and model_hint.strip().lower() == "codex":
        return default_target
    return candidate
