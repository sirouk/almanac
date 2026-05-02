#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_module(filename: str, name: str):
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    path = PYTHON_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_stripe_credentials_missing() -> None:
    mod = load_module("arclink_diagnostics.py", "arclink_diag_stripe_missing")
    checks = mod.diagnose_stripe(env={})
    expect(len(checks) == 2, f"expected 2 checks, got {len(checks)}")
    for c in checks:
        expect(not c.ok, f"expected not ok: {c}")
        expect("missing" in c.detail, c.detail)
    print("PASS test_stripe_credentials_missing")


def test_stripe_credentials_present() -> None:
    mod = load_module("arclink_diagnostics.py", "arclink_diag_stripe_present")
    env = {"STRIPE_SECRET_KEY": "sk_test_xxx", "STRIPE_WEBHOOK_SECRET": "whsec_xxx"}
    checks = mod.diagnose_stripe(env=env)
    for c in checks:
        expect(c.ok, f"expected ok: {c}")
        expect(c.detail == "present", c.detail)
    print("PASS test_stripe_credentials_present")


def test_credential_values_never_in_output() -> None:
    mod = load_module("arclink_diagnostics.py", "arclink_diag_redaction")
    secret_values = {
        "STRIPE_SECRET_KEY": "sk_live_EXTREMELY_SECRET_123",
        "STRIPE_WEBHOOK_SECRET": "whsec_EXTREMELY_SECRET_456",
        "CLOUDFLARE_API_TOKEN": "cf_token_EXTREMELY_SECRET_789",
        "CLOUDFLARE_ZONE_ID": "zone_EXTREMELY_SECRET_abc",
        "CHUTES_API_KEY": "chutes_EXTREMELY_SECRET_def",
        "TELEGRAM_BOT_TOKEN": "tg_EXTREMELY_SECRET_ghi",
        "DISCORD_BOT_TOKEN": "dc_EXTREMELY_SECRET_jkl",
        "DISCORD_APP_ID": "app_EXTREMELY_SECRET_mno",
    }
    result = mod.run_diagnostics(env=secret_values, docker_binary="python3")
    rendered = result.to_json()
    for value in secret_values.values():
        expect(value not in rendered, f"secret value leaked in output: {value}")
    print("PASS test_credential_values_never_in_output")


def test_cloudflare_missing() -> None:
    mod = load_module("arclink_diagnostics.py", "arclink_diag_cf_missing")
    checks = mod.diagnose_cloudflare(env={})
    expect(len(checks) == 2, str(checks))
    for c in checks:
        expect(not c.ok, f"expected not ok: {c}")
    print("PASS test_cloudflare_missing")


def test_chutes_missing() -> None:
    mod = load_module("arclink_diagnostics.py", "arclink_diag_chutes_missing")
    checks = mod.diagnose_chutes(env={})
    expect(len(checks) == 1, str(checks))
    expect(not checks[0].ok, str(checks[0]))
    print("PASS test_chutes_missing")


def test_telegram_missing() -> None:
    mod = load_module("arclink_diagnostics.py", "arclink_diag_tg_missing")
    checks = mod.diagnose_telegram(env={})
    expect(len(checks) == 1, str(checks))
    expect(not checks[0].ok, str(checks[0]))
    print("PASS test_telegram_missing")


def test_discord_missing() -> None:
    mod = load_module("arclink_diagnostics.py", "arclink_diag_dc_missing")
    checks = mod.diagnose_discord(env={})
    expect(len(checks) == 2, str(checks))
    for c in checks:
        expect(not c.ok, f"expected not ok: {c}")
    print("PASS test_discord_missing")


def test_docker_diagnostic() -> None:
    mod = load_module("arclink_diagnostics.py", "arclink_diag_docker")
    checks = mod.diagnose_docker(docker_binary="python3")
    expect(len(checks) == 1, str(checks))
    expect(checks[0].ok, str(checks[0]))

    missing = mod.diagnose_docker(docker_binary="arclink-nonexistent-xyz")
    expect(not missing[0].ok, str(missing[0]))
    print("PASS test_docker_diagnostic")


def test_full_diagnostics_machine_readable() -> None:
    mod = load_module("arclink_diagnostics.py", "arclink_diag_full")
    result = mod.run_diagnostics(env={}, docker_binary="python3")
    output = result.to_dict()
    expect("all_ok" in output, str(output))
    expect("checks" in output, str(output))
    expect(isinstance(output["checks"], list), str(output))
    parsed = json.loads(result.to_json())
    expect(parsed["all_ok"] == output["all_ok"], str(parsed))
    # With empty env, not all ok (missing credentials)
    expect(not result.all_ok, "expected not all_ok with empty env")
    print("PASS test_full_diagnostics_machine_readable")


def test_full_diagnostics_all_present() -> None:
    mod = load_module("arclink_diagnostics.py", "arclink_diag_full_present")
    env = {
        "STRIPE_SECRET_KEY": "x",
        "STRIPE_WEBHOOK_SECRET": "x",
        "CLOUDFLARE_API_TOKEN": "x",
        "CLOUDFLARE_ZONE_ID": "x",
        "CHUTES_API_KEY": "x",
        "TELEGRAM_BOT_TOKEN": "x",
        "DISCORD_BOT_TOKEN": "x",
        "DISCORD_APP_ID": "x",
    }
    result = mod.run_diagnostics(env=env, docker_binary="python3")
    expect(result.all_ok, result.to_json())
    print("PASS test_full_diagnostics_all_present")


def test_diagnostics_noop_without_live_flag() -> None:
    mod = load_module("arclink_diagnostics.py", "arclink_diag_noop")
    # Default live=False should still return checks but no live operations
    result = mod.run_diagnostics(env={}, docker_binary="python3", live=False)
    for c in result.checks:
        expect(not c.live, f"expected no live checks: {c}")
    print("PASS test_diagnostics_noop_without_live_flag")


def main() -> int:
    test_stripe_credentials_missing()
    test_stripe_credentials_present()
    test_credential_values_never_in_output()
    test_cloudflare_missing()
    test_chutes_missing()
    test_telegram_missing()
    test_discord_missing()
    test_docker_diagnostic()
    test_full_diagnostics_machine_readable()
    test_full_diagnostics_all_present()
    test_diagnostics_noop_without_live_flag()
    print("PASS all 11 ArcLink diagnostics tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
