#!/usr/bin/env python3
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


PRODUCT_NAME = "ArcLink"
DEFAULT_BASE_DOMAIN = "localhost"

ARCLINK_ENV_ALIASES: dict[str, str] = {}

ARCLINK_DEFAULTS: dict[str, str] = {
    "ARCLINK_PRODUCT_NAME": PRODUCT_NAME,
    "ARCLINK_BASE_DOMAIN": DEFAULT_BASE_DOMAIN,
    "ARCLINK_PRIMARY_PROVIDER": "chutes",
    "ARCLINK_CHUTES_BASE_URL": "https://llm.chutes.ai/v1",
    "ARCLINK_CHUTES_DEFAULT_MODEL": "moonshotai/Kimi-K2.6-TEE",
    "ARCLINK_MODEL_REASONING_DEFAULT": "medium",
}


@dataclass(frozen=True)
class EnvResolution:
    key: str
    value: str
    source: str
    legacy_key: str = ""
    conflict: bool = False

    def diagnostic(self) -> str:
        if not self.conflict or not self.legacy_key:
            return ""
        return f"{self.key} and {self.legacy_key} are both set; {self.key} takes precedence"


def _source(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def resolve_env(
    key: str,
    *,
    legacy_key: str | None = None,
    default: str = "",
    env: Mapping[str, str] | None = None,
) -> EnvResolution:
    source = _source(env)
    legacy = legacy_key if legacy_key is not None else ARCLINK_ENV_ALIASES.get(key, "")
    raw_value = source.get(key)
    raw_legacy = source.get(legacy, "") if legacy else ""
    value = str(raw_value or "").strip()
    legacy_value = str(raw_legacy or "").strip()

    if raw_value is not None and value:
        return EnvResolution(
            key=key,
            value=value,
            source=key,
            legacy_key=legacy,
            conflict=bool(legacy and legacy_value and legacy_value != value),
        )
    if legacy and legacy_value:
        return EnvResolution(key=key, value=legacy_value, source=legacy, legacy_key=legacy)
    return EnvResolution(key=key, value=default, source="default", legacy_key=legacy)


def env_value(
    key: str,
    default: str = "",
    *,
    legacy_key: str | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    return resolve_env(key, legacy_key=legacy_key, default=default, env=env).value


def product_name(env: Mapping[str, str] | None = None) -> str:
    return env_value("ARCLINK_PRODUCT_NAME", ARCLINK_DEFAULTS["ARCLINK_PRODUCT_NAME"], env=env)


def base_domain(env: Mapping[str, str] | None = None) -> str:
    return env_value("ARCLINK_BASE_DOMAIN", ARCLINK_DEFAULTS["ARCLINK_BASE_DOMAIN"], env=env)


def primary_provider(env: Mapping[str, str] | None = None) -> str:
    return env_value("ARCLINK_PRIMARY_PROVIDER", ARCLINK_DEFAULTS["ARCLINK_PRIMARY_PROVIDER"], env=env).lower()


def chutes_base_url(env: Mapping[str, str] | None = None) -> str:
    return env_value("ARCLINK_CHUTES_BASE_URL", ARCLINK_DEFAULTS["ARCLINK_CHUTES_BASE_URL"], env=env)


def chutes_default_model(env: Mapping[str, str] | None = None) -> str:
    return env_value("ARCLINK_CHUTES_DEFAULT_MODEL", ARCLINK_DEFAULTS["ARCLINK_CHUTES_DEFAULT_MODEL"], env=env)


def model_reasoning_default(env: Mapping[str, str] | None = None) -> str:
    return env_value(
        "ARCLINK_MODEL_REASONING_DEFAULT",
        ARCLINK_DEFAULTS["ARCLINK_MODEL_REASONING_DEFAULT"],
        env=env,
    ).lower()


def conflict_diagnostics(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    diagnostics: list[str] = []
    for key in sorted(ARCLINK_ENV_ALIASES):
        resolved = resolve_env(key, default=ARCLINK_DEFAULTS.get(key, ""), env=env)
        diagnostic = resolved.diagnostic()
        if diagnostic:
            diagnostics.append(diagnostic)
    return tuple(diagnostics)
