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
    token_ok = bool(source.get("CLOUDFLARE_API_TOKEN", "") or source.get("CLOUDFLARE_API_TOKEN_REF", ""))
    return [
        DiagnosticCheck(
            provider="cloudflare",
            name="credential_CLOUDFLARE_API_TOKEN",
            ok=token_ok,
            detail="present" if token_ok else "missing: CLOUDFLARE_API_TOKEN_REF or CLOUDFLARE_API_TOKEN",
        ),
        _credential_check("cloudflare", "CLOUDFLARE_ZONE_ID", source),
    ]


def diagnose_tailscale(env: Mapping[str, str] | None = None) -> list[DiagnosticCheck]:
    source = env if env is not None else os.environ
    return [
        _credential_check("tailscale", "ARCLINK_TAILSCALE_DNS_NAME", source),
    ]


def _ingress_mode(env: Mapping[str, str] | None = None) -> str:
    source = env if env is not None else os.environ
    return str(source.get("ARCLINK_INGRESS_MODE") or "").strip().lower()


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


def diagnose_qmd_pending_embeddings(
    env: Mapping[str, str] | None = None,
    *,
    state_file: str = "",
    now: float | None = None,
) -> list[DiagnosticCheck]:
    """Alert when qmd documents have been waiting for embeddings too long.

    Reads the marker maintained by bin/common.sh qmd_note_pending_embeddings_state
    (refreshed by every qmd-refresh.sh run). Embed failures are
    swallowed-and-retried by design, so a starved embed lane otherwise leaves
    vector search stale with only `qmd status "Pending: N"` as a signal.
    A missing marker means the qmd lane is not provisioned here: no check.
    """
    import time

    source = env if env is not None else os.environ
    path = str(state_file or source.get("QMD_PENDING_EMBED_STATE_FILE", "") or "").strip()
    if not path or not os.path.isfile(path):
        return []
    try:
        max_age = int(str(source.get("QMD_PENDING_EMBED_MAX_AGE_SECONDS", "") or 21600))
    except ValueError:
        max_age = 21600
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return [
            DiagnosticCheck(
                provider="qmd",
                name="pending_embeddings_age",
                ok=False,
                detail=f"unreadable pending-embeddings marker at {path}",
            )
        ]
    if not isinstance(payload, dict):
        payload = {}
    try:
        pending = int(payload.get("pending") or 0)
        pending_since = int(payload.get("pending_since_epoch") or 0)
    except (TypeError, ValueError):
        pending, pending_since = 0, 0
    if pending <= 0 or pending_since <= 0:
        return [
            DiagnosticCheck(
                provider="qmd",
                name="pending_embeddings_age",
                ok=True,
                detail="no documents waiting for embeddings",
            )
        ]
    current = float(now if now is not None else time.time())
    age = int(current) - pending_since
    if age < 0:
        return [
            DiagnosticCheck(
                provider="qmd",
                name="pending_embeddings_age",
                ok=False,
                detail="pending-embeddings marker is from the future; check host clock sync",
            )
        ]
    stale = age > max_age
    detail = f"{pending} document(s) pending embeddings for ~{age // 3600}h" + (
        f" (exceeds {max_age // 3600}h threshold; vector search is stale)" if stale else ""
    )
    return [
        DiagnosticCheck(
            provider="qmd",
            name="pending_embeddings_age",
            ok=not stale,
            detail=detail,
        )
    ]


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
    if _ingress_mode(env) == "tailscale":
        checks.extend(diagnose_tailscale(env))
    else:
        checks.extend(diagnose_cloudflare(env))
    checks.extend(diagnose_chutes(env))
    checks.extend(diagnose_telegram(env))
    checks.extend(diagnose_discord(env))
    checks.extend(diagnose_docker(docker_binary=docker_binary))
    checks.extend(diagnose_qmd_pending_embeddings(env))
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
