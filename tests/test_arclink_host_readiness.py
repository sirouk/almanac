#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

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


def compose_ok_runner(*args, **kwargs):
    return SimpleNamespace(returncode=0, stdout="Docker Compose version v2.32.0\n", stderr="")


def compose_fail_runner(*args, **kwargs):
    return SimpleNamespace(returncode=1, stdout="", stderr="docker: 'compose' is not a docker command\n")


def test_docker_missing() -> None:
    mod = load_module("arclink_host_readiness.py", "arclink_host_readiness_docker_missing")
    check = mod.check_docker(docker_binary="arclink-nonexistent-docker-binary-xyz")
    expect(not check.ok, f"expected not ok: {check}")
    expect("not found" in check.detail, check.detail)
    print("PASS test_docker_missing")


def test_docker_present() -> None:
    mod = load_module("arclink_host_readiness.py", "arclink_host_readiness_docker_present")
    # Use 'python3' as a known-present binary stand-in
    check = mod.check_docker(docker_binary="python3")
    expect(check.ok, f"expected ok: {check}")
    expect("python3" in check.detail, check.detail)
    print("PASS test_docker_present")


def test_docker_compose_success_requires_subcommand() -> None:
    mod = load_module("arclink_host_readiness.py", "arclink_host_readiness_compose_success")
    check = mod.check_docker_compose(compose_binary="python3", runner=compose_ok_runner)
    expect(check.ok, f"expected ok: {check}")
    expect("Docker Compose version" in check.detail, check.detail)
    print("PASS test_docker_compose_success_requires_subcommand")


def test_docker_compose_failure_is_not_ready() -> None:
    mod = load_module("arclink_host_readiness.py", "arclink_host_readiness_compose_failure")
    check = mod.check_docker_compose(compose_binary="python3", runner=compose_fail_runner)
    expect(not check.ok, f"expected not ok: {check}")
    expect("compose" in check.detail.lower(), check.detail)
    print("PASS test_docker_compose_failure_is_not_ready")


def test_state_root_missing() -> None:
    mod = load_module("arclink_host_readiness.py", "arclink_host_readiness_state_missing")
    check = mod.check_state_root("/arclink-nonexistent-state-root-xyz")
    expect(not check.ok, f"expected not ok: {check}")
    expect("does not exist" in check.detail, check.detail)
    print("PASS test_state_root_missing")


def test_state_root_writable() -> None:
    mod = load_module("arclink_host_readiness.py", "arclink_host_readiness_state_writable")
    with tempfile.TemporaryDirectory() as tmp:
        check = mod.check_state_root(tmp)
        expect(check.ok, f"expected ok: {check}")
        expect(tmp in check.detail, check.detail)
    print("PASS test_state_root_writable")


def test_env_vars_missing() -> None:
    mod = load_module("arclink_host_readiness.py", "arclink_host_readiness_env_missing")
    checks = mod.check_env_vars(env={})
    expect(len(checks) > 0, "expected env checks")
    for c in checks:
        expect(not c.ok, f"expected not ok for empty env: {c}")
        expect("missing" in c.detail, c.detail)
    print("PASS test_env_vars_missing")


def test_env_vars_present() -> None:
    mod = load_module("arclink_host_readiness.py", "arclink_host_readiness_env_present")
    env = {
        "ARCLINK_PRODUCT_NAME": "ArcLink",
        "ARCLINK_BASE_DOMAIN": "arclink.online",
        "ARCLINK_PRIMARY_PROVIDER": "chutes",
    }
    checks = mod.check_env_vars(env=env)
    for c in checks:
        expect(c.ok, f"expected ok: {c}")
    print("PASS test_env_vars_present")


def test_secret_env_redaction() -> None:
    mod = load_module("arclink_host_readiness.py", "arclink_host_readiness_secret_redaction")
    secret_value = "sk_live_extremely_secret_value_12345"
    env = {"STRIPE_SECRET_KEY": secret_value, "CHUTES_API_KEY": ""}
    checks = mod.check_secret_env_presence(env=env)
    rendered = json.dumps([{"name": c.name, "ok": c.ok, "detail": c.detail} for c in checks])
    expect(secret_value not in rendered, f"secret value leaked: {rendered}")
    stripe_check = next(c for c in checks if "STRIPE_SECRET_KEY" in c.name)
    expect(stripe_check.ok, f"expected present: {stripe_check}")
    expect(stripe_check.detail == "present", stripe_check.detail)
    chutes_check = next(c for c in checks if "CHUTES_API_KEY" in c.name)
    expect(not chutes_check.ok, f"expected absent: {chutes_check}")
    print("PASS test_secret_env_redaction")


def test_ingress_strategy_cloudflare() -> None:
    mod = load_module("arclink_host_readiness.py", "arclink_host_readiness_ingress_cf")
    env = {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ZONE_ID": "zone"}
    check = mod.check_ingress_strategy(env=env)
    expect(check.ok, f"expected ok: {check}")
    expect(check.detail == "cloudflare", check.detail)
    print("PASS test_ingress_strategy_cloudflare")


def test_ingress_strategy_traefik_fallback() -> None:
    mod = load_module("arclink_host_readiness.py", "arclink_host_readiness_ingress_traefik")
    check = mod.check_ingress_strategy(env={})
    expect(check.ok, f"expected ok: {check}")
    expect(check.detail == "traefik_local", check.detail)
    print("PASS test_ingress_strategy_traefik_fallback")


def test_full_readiness_machine_readable() -> None:
    mod = load_module("arclink_host_readiness.py", "arclink_host_readiness_full")
    with tempfile.TemporaryDirectory() as tmp:
        env = {
            "ARCLINK_PRODUCT_NAME": "ArcLink",
            "ARCLINK_BASE_DOMAIN": "arclink.online",
            "ARCLINK_PRIMARY_PROVIDER": "chutes",
        }
        result = mod.run_readiness(
            state_root=tmp,
            env=env,
            docker_binary="python3",
            compose_runner=compose_ok_runner,
            skip_ports=True,
        )
        output = result.to_dict()
        expect(isinstance(output, dict), str(output))
        expect("ready" in output, str(output))
        expect("checks" in output, str(output))
        expect(isinstance(output["checks"], list), str(output))
        # JSON round-trip
        parsed = json.loads(result.to_json())
        expect(parsed["ready"] == output["ready"], str(parsed))
    print("PASS test_full_readiness_machine_readable")


def test_full_readiness_fails_without_docker() -> None:
    mod = load_module("arclink_host_readiness.py", "arclink_host_readiness_fail")
    with tempfile.TemporaryDirectory() as tmp:
        result = mod.run_readiness(
            state_root=tmp,
            env={"ARCLINK_PRODUCT_NAME": "ArcLink", "ARCLINK_BASE_DOMAIN": "arclink.online", "ARCLINK_PRIMARY_PROVIDER": "chutes"},
            docker_binary="arclink-nonexistent-docker-binary-xyz",
            skip_ports=True,
        )
        expect(not result.ready, f"expected not ready: {result.to_json()}")
    print("PASS test_full_readiness_fails_without_docker")


def test_full_readiness_fails_on_unavailable_port() -> None:
    mod = load_module("arclink_host_readiness.py", "arclink_host_readiness_port_fail")
    with tempfile.TemporaryDirectory() as tmp:
        result = mod.run_readiness(
            state_root=tmp,
            env={"ARCLINK_PRODUCT_NAME": "ArcLink", "ARCLINK_BASE_DOMAIN": "arclink.online", "ARCLINK_PRIMARY_PROVIDER": "chutes"},
            docker_binary="python3",
            compose_runner=compose_ok_runner,
            ports=(-1,),
        )
        expect(not result.ready, f"expected not ready when port check fails: {result.to_json()}")
    print("PASS test_full_readiness_fails_on_unavailable_port")


def main() -> int:
    test_docker_missing()
    test_docker_present()
    test_docker_compose_success_requires_subcommand()
    test_docker_compose_failure_is_not_ready()
    test_state_root_missing()
    test_state_root_writable()
    test_env_vars_missing()
    test_env_vars_present()
    test_secret_env_redaction()
    test_ingress_strategy_cloudflare()
    test_ingress_strategy_traefik_fallback()
    test_full_readiness_machine_readable()
    test_full_readiness_fails_without_docker()
    test_full_readiness_fails_on_unavailable_port()
    print("PASS all 14 ArcLink host readiness tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
