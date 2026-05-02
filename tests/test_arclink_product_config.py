#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
PRODUCT_PY = PYTHON_DIR / "arclink_product.py"
CONTROL_PY = PYTHON_DIR / "arclink_control.py"


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


def test_existing_arclink_config_helper_still_reads_legacy_env() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_legacy_config_test")
    expect(mod.bool_env("ARCLINK_LEGACY_FLAG", env={"ARCLINK_LEGACY_FLAG": "yes"}), "legacy bool env should still resolve")
    print("PASS test_existing_arclink_config_helper_still_reads_legacy_env")


def main() -> int:
    test_arclink_env_overrides_explicit_alias_without_exposing_values()
    test_blank_arclink_value_falls_back_to_explicit_alias()
    test_arclink_defaults_are_chutes_first()
    test_existing_arclink_config_helper_still_reads_legacy_env()
    print("PASS all 4 ArcLink product/config tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
