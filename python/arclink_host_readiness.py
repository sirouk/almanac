#!/usr/bin/env python3
"""ArcLink host readiness checks.

Executable, no-secret tooling that validates Docker, Docker Compose,
available ports, writable state root, expected env vars, and
ingress strategy without mutating live providers.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping


_REQUIRED_ENV_VARS = (
    "ARCLINK_PRODUCT_NAME",
    "ARCLINK_BASE_DOMAIN",
    "ARCLINK_PRIMARY_PROVIDER",
)

_OPTIONAL_SECRET_ENV_VARS = (
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_API_TOKEN_REF",
    "CLOUDFLARE_ZONE_ID",
    "CHUTES_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "DISCORD_BOT_TOKEN",
    "DISCORD_APP_ID",
)

_DEFAULT_PORTS = (80, 443, 8080)

_DEFAULT_STATE_ROOT = "/arcdata"


@dataclass
class ReadinessCheck:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class ReadinessResult:
    ready: bool
    checks: list[ReadinessCheck] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "checks": [asdict(c) for c in self.checks],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def check_docker(*, docker_binary: str = "docker") -> ReadinessCheck:
    path = shutil.which(docker_binary)
    if path is None:
        return ReadinessCheck(name="docker", ok=False, detail=f"{docker_binary} not found in PATH")
    return ReadinessCheck(name="docker", ok=True, detail=path)


ComposeRunner = Callable[..., subprocess.CompletedProcess[str]]


def check_docker_compose(*, compose_binary: str = "docker", runner: ComposeRunner | None = None) -> ReadinessCheck:
    """Verify that Docker Compose v2 is callable, not just that docker exists."""
    path = shutil.which(compose_binary)
    if path is None:
        return ReadinessCheck(name="docker_compose", ok=False, detail=f"{compose_binary} not found in PATH")
    run = runner or subprocess.run
    try:
        result = run(
            [compose_binary, "compose", "version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ReadinessCheck(name="docker_compose", ok=False, detail=f"docker compose unavailable: {exc}")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "docker compose version failed").strip()
        return ReadinessCheck(name="docker_compose", ok=False, detail=detail[:240])
    detail = (result.stdout or f"{path} compose").strip()
    return ReadinessCheck(name="docker_compose", ok=True, detail=detail[:240])


def check_port_available(port: int) -> ReadinessCheck:
    if port < 0 or port > 65535:
        return ReadinessCheck(name=f"port_{port}", ok=False, detail=f"invalid port: {port}")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.bind(("0.0.0.0", port))
        return ReadinessCheck(name=f"port_{port}", ok=True, detail=f"port {port} available")
    except OSError as exc:
        return ReadinessCheck(name=f"port_{port}", ok=False, detail=f"port {port} unavailable: {exc}")


def check_state_root(state_root: str | None = None) -> ReadinessCheck:
    root = state_root or os.environ.get("ARCLINK_STATE_ROOT") or _DEFAULT_STATE_ROOT
    path = Path(root)
    if not path.exists():
        return ReadinessCheck(name="state_root", ok=False, detail=f"state root does not exist: {root}")
    # Check writable by attempting a temp file
    try:
        with tempfile.NamedTemporaryFile(dir=root, prefix=".arclink_readiness_", delete=True):
            pass
        return ReadinessCheck(name="state_root", ok=True, detail=root)
    except OSError as exc:
        return ReadinessCheck(name="state_root", ok=False, detail=f"state root not writable: {root}: {exc}")


def check_env_vars(env: Mapping[str, str] | None = None) -> list[ReadinessCheck]:
    source = env if env is not None else os.environ
    checks: list[ReadinessCheck] = []
    for var in _REQUIRED_ENV_VARS:
        value = source.get(var, "")
        if value:
            checks.append(ReadinessCheck(name=f"env_{var}", ok=True, detail="set"))
        else:
            checks.append(ReadinessCheck(name=f"env_{var}", ok=False, detail="missing or empty"))
    return checks


def check_secret_env_presence(env: Mapping[str, str] | None = None) -> list[ReadinessCheck]:
    """Report which optional secret env vars are set, without revealing values."""
    source = env if env is not None else os.environ
    checks: list[ReadinessCheck] = []
    for var in _OPTIONAL_SECRET_ENV_VARS:
        present = bool(source.get(var, ""))
        # Never include the value
        checks.append(ReadinessCheck(
            name=f"secret_{var}",
            ok=present,
            detail="present" if present else "absent",
        ))
    return checks


def check_ingress_strategy(env: Mapping[str, str] | None = None) -> ReadinessCheck:
    source = env if env is not None else os.environ
    has_cf_token = bool(source.get("CLOUDFLARE_API_TOKEN", "") or source.get("CLOUDFLARE_API_TOKEN_REF", ""))
    has_cf_zone = bool(source.get("CLOUDFLARE_ZONE_ID", ""))
    if has_cf_token and has_cf_zone:
        return ReadinessCheck(name="ingress_strategy", ok=True, detail="cloudflare")
    # Traefik is the local fallback
    return ReadinessCheck(name="ingress_strategy", ok=True, detail="traefik_local")


def run_readiness(
    *,
    state_root: str | None = None,
    ports: tuple[int, ...] | None = None,
    env: Mapping[str, str] | None = None,
    docker_binary: str = "docker",
    compose_runner: ComposeRunner | None = None,
    skip_ports: bool = False,
) -> ReadinessResult:
    checks: list[ReadinessCheck] = []
    checks.append(check_docker(docker_binary=docker_binary))
    checks.append(check_docker_compose(compose_binary=docker_binary, runner=compose_runner))
    checks.append(check_state_root(state_root))
    checks.extend(check_env_vars(env))
    checks.extend(check_secret_env_presence(env))
    checks.append(check_ingress_strategy(env))
    if not skip_ports:
        for port in (ports or _DEFAULT_PORTS):
            checks.append(check_port_available(port))
    ready = all(c.ok for c in checks if not c.name.startswith("secret_"))
    return ReadinessResult(ready=ready, checks=checks)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run ArcLink host readiness checks without printing secret values.")
    parser.add_argument("--state-root", default=None, help="ArcLink state root to check, defaults to ARCLINK_STATE_ROOT or /arcdata")
    parser.add_argument("--docker-binary", default="docker", help="Docker binary name or path")
    parser.add_argument("--skip-ports", action="store_true", help="Skip local bind checks for ingress ports")
    parser.add_argument("--ports", default="80,443,8080", help="Comma-separated ports to bind-check")
    args = parser.parse_args(argv)

    try:
        ports = tuple(int(item.strip()) for item in str(args.ports).split(",") if item.strip())
    except ValueError:
        print(json.dumps({"ready": False, "error": "ports must be comma-separated integers"}), file=sys.stderr)
        return 2

    result = run_readiness(
        state_root=args.state_root,
        ports=ports,
        docker_binary=args.docker_binary,
        skip_ports=args.skip_ports,
    )
    print(result.to_json())
    return 0 if result.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
