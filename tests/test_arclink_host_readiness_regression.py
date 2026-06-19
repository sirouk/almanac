#!/usr/bin/env python3
"""Regression tests for host readiness: serving-port probe + docker daemon ping."""
from __future__ import annotations

import importlib.util
import socket
import sys
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


def test_serving_port_is_ready_but_strict_bind_is_not() -> None:
    mod = load_module("arclink_host_readiness.py", "arclink_host_readiness_serving")
    # Bind+listen a real port so it is "serving".
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        # The liveness-aware check: a serving port is READY (a live ingress host
        # must not read as not-ready).
        serving = mod.check_port_serving_or_free(port)
        expect(serving.ok, f"serving port must be ready: {serving}")
        expect("serving" in serving.detail, serving.detail)
        # The strict fresh-bring-up bind check still reports the port as in use.
        strict = mod.check_port_available(port)
        expect(not strict.ok, f"strict bind must fail on an in-use port: {strict}")
    finally:
        srv.close()

    # A free port is ready under the liveness-aware check too.
    free = mod.check_port_serving_or_free(0)  # 0 is bindable
    expect(free.ok, f"free port must be ready: {free}")
    print("PASS test_serving_port_is_ready_but_strict_bind_is_not")


def test_run_readiness_default_does_not_mark_live_host_not_ready_on_busy_port() -> None:
    mod = load_module("arclink_host_readiness.py", "arclink_host_readiness_runready_serving")
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    env = {
        "ARCLINK_PRODUCT_NAME": "ArcLink",
        "ARCLINK_BASE_DOMAIN": "arclink.online",
        "ARCLINK_PRIMARY_PROVIDER": "chutes",
    }

    def ok_compose(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="Docker Compose version v2.0.0\n", stderr="")

    import tempfile

    try:
        with tempfile.TemporaryDirectory() as tmp:
            # Default (not fresh_bringup): the serving port keeps the host ready.
            serving_check = next(
                c for c in mod.run_readiness(
                    state_root=tmp, env=env, ports=(port,), docker_binary="python3",
                    compose_runner=ok_compose, skip_docker_daemon=True,
                ).checks if c.name == f"port_{port}"
            )
            expect(serving_check.ok, f"serving port must keep host ready: {serving_check}")
            # fresh_bringup: the same in-use port now fails (needs a free bind).
            fresh_check = next(
                c for c in mod.run_readiness(
                    state_root=tmp, env=env, ports=(port,), docker_binary="python3",
                    compose_runner=ok_compose, skip_docker_daemon=True, fresh_bringup=True,
                ).checks if c.name == f"port_{port}"
            )
            expect(not fresh_check.ok, f"fresh bring-up must require a free port: {fresh_check}")
    finally:
        srv.close()
    print("PASS test_run_readiness_default_does_not_mark_live_host_not_ready_on_busy_port")


def test_docker_daemon_check_pings_and_fails_on_nonzero_or_timeout() -> None:
    import subprocess

    mod = load_module("arclink_host_readiness.py", "arclink_host_readiness_daemon")

    def daemon_ok(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="24.0.7\n", stderr="")

    def daemon_down(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="Cannot connect to the Docker daemon\n")

    def daemon_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="docker info", timeout=10)

    ok = mod.check_docker_daemon(docker_binary="python3", runner=daemon_ok)
    expect(ok.ok, f"reachable daemon must pass: {ok}")
    down = mod.check_docker_daemon(docker_binary="python3", runner=daemon_down)
    expect(not down.ok, f"dead daemon must fail: {down}")
    expect("Cannot connect" in down.detail, down.detail)
    timed = mod.check_docker_daemon(docker_binary="python3", runner=daemon_timeout)
    expect(not timed.ok, f"daemon timeout must fail: {timed}")
    expect("did not respond" in timed.detail, timed.detail)
    print("PASS test_docker_daemon_check_pings_and_fails_on_nonzero_or_timeout")


def main() -> int:
    test_serving_port_is_ready_but_strict_bind_is_not()
    test_run_readiness_default_does_not_mark_live_host_not_ready_on_busy_port()
    test_docker_daemon_check_pings_and_fails_on_nonzero_or_timeout()
    print("PASS all 3 ArcLink host readiness regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
