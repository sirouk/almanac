#!/usr/bin/env python3
"""ArcLink provider diagnostics.

Secret-safe diagnostic layer for external providers. Reports missing
credential names without returning credential values. Diagnostics are
no-op/read-only unless an explicit live E2E flag is set.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass
class DiagnosticCheck:
    provider: str
    name: str
    ok: bool
    detail: str = ""
    live: bool = False


@dataclass
class DiagnosticsResult:
    checks: list[DiagnosticCheck] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "all_ok": self.all_ok,
            "checks": [asdict(c) for c in self.checks],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def _credential_check(provider: str, env_var: str, env: Mapping[str, str]) -> DiagnosticCheck:
    present = bool(env.get(env_var, ""))
    return DiagnosticCheck(
        provider=provider,
        name=f"credential_{env_var}",
        ok=present,
        detail="present" if present else f"missing: {env_var}",
    )


def diagnose_stripe(env: Mapping[str, str] | None = None) -> list[DiagnosticCheck]:
    source = env if env is not None else os.environ
    return [
        _credential_check("stripe", "STRIPE_SECRET_KEY", source),
        _credential_check("stripe", "STRIPE_WEBHOOK_SECRET", source),
    ]


def diagnose_cloudflare(env: Mapping[str, str] | None = None) -> list[DiagnosticCheck]:
    source = env if env is not None else os.environ
    return [
        _credential_check("cloudflare", "CLOUDFLARE_API_TOKEN", source),
        _credential_check("cloudflare", "CLOUDFLARE_ZONE_ID", source),
    ]


def diagnose_chutes(env: Mapping[str, str] | None = None) -> list[DiagnosticCheck]:
    source = env if env is not None else os.environ
    return [
        _credential_check("chutes", "CHUTES_API_KEY", source),
    ]


def diagnose_telegram(env: Mapping[str, str] | None = None) -> list[DiagnosticCheck]:
    source = env if env is not None else os.environ
    return [
        _credential_check("telegram", "TELEGRAM_BOT_TOKEN", source),
    ]


def diagnose_discord(env: Mapping[str, str] | None = None) -> list[DiagnosticCheck]:
    source = env if env is not None else os.environ
    return [
        _credential_check("discord", "DISCORD_BOT_TOKEN", source),
        _credential_check("discord", "DISCORD_APP_ID", source),
    ]


def diagnose_docker(*, docker_binary: str = "docker") -> list[DiagnosticCheck]:
    path = shutil.which(docker_binary)
    checks = [
        DiagnosticCheck(
            provider="docker",
            name="docker_binary",
            ok=path is not None,
            detail=path or f"{docker_binary} not found in PATH",
        ),
    ]
    return checks


def run_diagnostics(
    *,
    env: Mapping[str, str] | None = None,
    docker_binary: str = "docker",
    live: bool = False,
) -> DiagnosticsResult:
    """Run all provider diagnostics.

    When live=False (default), only credential presence checks run.
    When live=True, real provider connectivity could be tested (future).
    """
    checks: list[DiagnosticCheck] = []
    checks.extend(diagnose_stripe(env))
    checks.extend(diagnose_cloudflare(env))
    checks.extend(diagnose_chutes(env))
    checks.extend(diagnose_telegram(env))
    checks.extend(diagnose_discord(env))
    checks.extend(diagnose_docker(docker_binary=docker_binary))
    return DiagnosticsResult(checks=checks)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run ArcLink provider diagnostics without printing secret values.")
    parser.add_argument("--docker-binary", default="docker", help="Docker binary name or path")
    parser.add_argument("--live", action="store_true", help="Reserve live connectivity mode for explicit credentialed runs")
    args = parser.parse_args(argv)

    result = run_diagnostics(docker_binary=args.docker_binary, live=args.live)
    print(result.to_json())
    return 0 if result.all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
