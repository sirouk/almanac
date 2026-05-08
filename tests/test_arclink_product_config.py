#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
PRODUCT_PY = PYTHON_DIR / "arclink_product.py"
CONTROL_PY = PYTHON_DIR / "arclink_control.py"


EXPECTED_PRICE_IDS = {
    "ARCLINK_DEFAULT_PRICE_ID": "price_arclink_founders",
    "ARCLINK_FOUNDERS_PRICE_ID": "price_arclink_founders",
    "ARCLINK_SOVEREIGN_PRICE_ID": "price_arclink_sovereign",
    "ARCLINK_SCALE_PRICE_ID": "price_arclink_scale",
    "ARCLINK_FIRST_AGENT_PRICE_ID": "price_arclink_founders",
    "ARCLINK_SOVEREIGN_AGENT_EXPANSION_PRICE_ID": "price_arclink_sovereign_agent_expansion",
    "ARCLINK_SCALE_AGENT_EXPANSION_PRICE_ID": "price_arclink_scale_agent_expansion",
    "ARCLINK_ADDITIONAL_AGENT_PRICE_ID": "price_arclink_sovereign_agent_expansion",
}

EXPECTED_MONTHLY_CENTS = {
    "ARCLINK_FOUNDERS_MONTHLY_CENTS": 14900,
    "ARCLINK_SOVEREIGN_MONTHLY_CENTS": 19900,
    "ARCLINK_SCALE_MONTHLY_CENTS": 27500,
    "ARCLINK_FIRST_AGENT_MONTHLY_CENTS": 14900,
    "ARCLINK_SOVEREIGN_AGENT_EXPANSION_MONTHLY_CENTS": 9900,
    "ARCLINK_SCALE_AGENT_EXPANSION_MONTHLY_CENTS": 7900,
    "ARCLINK_ADDITIONAL_AGENT_MONTHLY_CENTS": 9900,
}

EXPECTED_PUBLIC_PRICE_LABELS = {
    "founders": ("Limited 100 Founders", "$149/month", "FOUNDERS_MONTHLY_DOLLARS"),
    "sovereign": ("Sovereign", "$199/month", "SOVEREIGN_MONTHLY_DOLLARS"),
    "scale": ("Scale", "$275/month", "SCALE_MONTHLY_DOLLARS"),
    "sovereign_agent_expansion": (
        "Sovereign Agentic Expansion",
        "$99/month",
        "SOVEREIGN_AGENT_EXPANSION_MONTHLY_DOLLARS",
    ),
    "scale_agent_expansion": (
        "Scale Agentic Expansion",
        "$79/month",
        "SCALE_AGENT_EXPANSION_MONTHLY_DOLLARS",
    ),
}


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_module(path: Path, name: str):
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def compose_env_default(compose_text: str, key: str) -> str:
    pattern = rf"^\s+{re.escape(key)}:\s+\$\{{{re.escape(key)}:-(.*?)\}}\s*$"
    match = re.search(pattern, compose_text, flags=re.MULTILINE)
    if not match:
        raise AssertionError(f"missing Compose default for {key}")
    return match.group(1)


def env_example_default(env_text: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}=(.*?)$", env_text, flags=re.MULTILINE)
    if not match:
        raise AssertionError(f"missing config/env.example default for {key}")
    return match.group(1)


def test_arclink_env_overrides_explicit_alias_without_exposing_values() -> None:
    mod = load_module(PRODUCT_PY, "arclink_product_config_override_test")
    env = {
        "ARCLINK_BASE_DOMAIN": "new.example",
        "ARC_BASE_DOMAIN": "fallback-alias.example",
    }
    resolved = mod.resolve_env("ARCLINK_BASE_DOMAIN", legacy_key="ARC_BASE_DOMAIN", default="fallback.test", env=env)
    expect(resolved.value == "new.example", str(resolved))
    expect(resolved.source == "ARCLINK_BASE_DOMAIN", str(resolved))
    expect(resolved.conflict, str(resolved))
    diagnostic = resolved.diagnostic()
    expect("ARCLINK_BASE_DOMAIN" in diagnostic and "ARC_BASE_DOMAIN" in diagnostic, diagnostic)
    expect("new.example" not in diagnostic and "fallback-alias.example" not in diagnostic, diagnostic)
    print("PASS test_arclink_env_overrides_explicit_alias_without_exposing_values")


def test_blank_arclink_value_falls_back_to_explicit_alias() -> None:
    mod = load_module(PRODUCT_PY, "arclink_product_config_blank_test")
    env = {
        "ARCLINK_BASE_DOMAIN": "  ",
        "ARC_BASE_DOMAIN": "fallback-alias.example",
    }
    resolved = mod.resolve_env("ARCLINK_BASE_DOMAIN", legacy_key="ARC_BASE_DOMAIN", default="fallback.test", env=env)
    expect(resolved.value == "fallback-alias.example", str(resolved))
    expect(resolved.source == "ARC_BASE_DOMAIN", str(resolved))
    expect(not resolved.conflict, str(resolved))
    print("PASS test_blank_arclink_value_falls_back_to_explicit_alias")


def test_arclink_defaults_are_chutes_first() -> None:
    mod = load_module(PRODUCT_PY, "arclink_product_config_defaults_test")
    expect(mod.product_name({}) == "ArcLink", "bad product default")
    expect(mod.base_domain({}) == "localhost", "bad domain default")
    expect(mod.primary_provider({}) == "chutes", "bad provider default")
    expect(mod.chutes_default_model({}) == "moonshotai/Kimi-K2.6-TEE", "bad Chutes default model")
    expect(mod.model_reasoning_default({}) == "medium", "bad reasoning default")
    print("PASS test_arclink_defaults_are_chutes_first")


def test_plan_pricing_is_consistent_across_public_surfaces() -> None:
    bots = load_module(PYTHON_DIR / "arclink_public_bots.py", "arclink_public_bot_price_contract_test")
    compose_text = (REPO / "compose.yaml").read_text(encoding="utf-8")
    env_text = (REPO / "config" / "env.example").read_text(encoding="utf-8")
    api_reference = (REPO / "docs" / "API_REFERENCE.md").read_text(encoding="utf-8")
    operations_runbook = (REPO / "docs" / "arclink" / "operations-runbook.md").read_text(encoding="utf-8")
    web_onboarding = (REPO / "web" / "src" / "app" / "onboarding" / "page.tsx").read_text(encoding="utf-8")

    for key, expected in EXPECTED_PRICE_IDS.items():
        expect(compose_env_default(compose_text, key) == expected, f"bad Compose price id for {key}")
        expect(env_example_default(env_text, key) == expected, f"bad env.example price id for {key}")
        expect(f"| `{key}` | `{expected}` |" in api_reference, f"missing API reference row for {key}")
        expect(f"| `{key}` | `{expected}` |" in operations_runbook, f"missing operations row for {key}")

    for key, expected in EXPECTED_MONTHLY_CENTS.items():
        expected_text = str(expected)
        expect(compose_env_default(compose_text, key) == expected_text, f"bad Compose cents for {key}")
        expect(env_example_default(env_text, key) == expected_text, f"bad env.example cents for {key}")
        expect(f"| `{key}` | `{expected_text}` |" in api_reference, f"missing API reference cents row for {key}")
        expect(f"| `{key}` | `{expected_text}` |" in operations_runbook, f"missing operations cents row for {key}")

    for _, (name, label, bot_constant) in EXPECTED_PUBLIC_PRICE_LABELS.items():
        dollars = int(label.removeprefix("$").removesuffix("/month"))
        expect(getattr(bots, bot_constant) == dollars, f"bad public bot dollar constant for {bot_constant}")
        if name in {"Limited 100 Founders", "Sovereign", "Scale"}:
            expect(f'name: "{name}"' in web_onboarding, f"missing web plan name {name}")
            expect(f'price: "{label}"' in web_onboarding, f"missing web price label {label}")
        expect(label in api_reference, f"missing API reference price label {label}")
        expect(label in operations_runbook, f"missing operations price label {label}")

    print("PASS test_plan_pricing_is_consistent_across_public_surfaces")


def test_existing_arclink_config_helper_still_reads_legacy_env() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_legacy_config_test")
    expect(mod.bool_env("ARCLINK_LEGACY_FLAG", env={"ARCLINK_LEGACY_FLAG": "yes"}), "legacy bool env should still resolve")
    print("PASS test_existing_arclink_config_helper_still_reads_legacy_env")


def main() -> int:
    test_arclink_env_overrides_explicit_alias_without_exposing_values()
    test_blank_arclink_value_falls_back_to_explicit_alias()
    test_arclink_defaults_are_chutes_first()
    test_plan_pricing_is_consistent_across_public_surfaces()
    test_existing_arclink_config_helper_still_reads_legacy_env()
    print("PASS all 5 ArcLink product/config tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
