#!/usr/bin/env python3
"""ArcLink live proof orchestration runner.

Composes host readiness, provider diagnostics, journey model, and evidence
ledger into a single dry-run or live proof pass. Default mode is dry-run
with no secrets required. Missing credentials are reported by env var name
only; secret values are never printed, logged, or written.

Statuses:
  blocked_missing_credentials - required env vars absent
  dry_run_ready               - all env vars present, live not requested
  live_ready_pending_execution - live requested but no runners registered
  live_executed                - live run completed (passed or failed)
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from arclink_diagnostics import run_diagnostics
from arclink_evidence import (
    generate_run_id,
    get_commit_hash,
    ledger_from_journey,
)
from arclink_host_readiness import run_readiness
from arclink_live_journey import (
    JourneyStep,
    build_journey,
    evaluate_journey,
    journey_summary,
)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

@dataclass
class LiveProofResult:
    """Result of a live proof orchestration run."""
    status: str  # blocked_missing_credentials | dry_run_ready | live_ready_pending_execution | live_executed
    missing_env: list[str] = field(default_factory=list)
    host_readiness: dict[str, Any] = field(default_factory=dict)
    provider_diagnostics: dict[str, Any] = field(default_factory=dict)
    journey_summary: dict[str, Any] = field(default_factory=dict)
    evidence_path: str = ""
    exit_code: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


# ---------------------------------------------------------------------------
# Credential collection
# ---------------------------------------------------------------------------

def _collect_missing_env(steps: list[JourneyStep], env: Mapping[str, str]) -> list[str]:
    """Return deduplicated list of missing env var names across all steps."""
    seen: set[str] = set()
    result: list[str] = []
    for step in steps:
        for key in step.required_env:
            if key not in seen and not env.get(key, "").strip():
                seen.add(key)
                result.append(key)
    return result


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_live_proof(
    *,
    env: Mapping[str, str] | None = None,
    runners: dict[str, Any] | None = None,
    live: bool = False,
    artifact_dir: str | None = None,
    skip_ports: bool = True,
    docker_binary: str = "docker",
    compose_runner: Any | None = None,
) -> LiveProofResult:
    """Execute live proof orchestration.

    Args:
        env: Environment mapping (defaults to os.environ).
        runners: Step runners keyed by step name for live execution.
        live: If True and ARCLINK_E2E_LIVE is set, attempt live execution.
        artifact_dir: Directory to write evidence JSON. Defaults to ./evidence/.
        skip_ports: Skip port bind checks (default True for CI).
        docker_binary: Docker binary for readiness checks.
        compose_runner: Injected compose runner for readiness checks.
    """
    source = dict(env) if env is not None else dict(os.environ)

    # Phase 1: Host readiness
    readiness = run_readiness(
        env=source,
        skip_ports=skip_ports,
        docker_binary=docker_binary,
        compose_runner=compose_runner,
    )

    # Phase 2: Provider diagnostics
    diagnostics = run_diagnostics(env=source, docker_binary=docker_binary)

    # Phase 3: Journey planning
    steps = build_journey()
    all_missing = _collect_missing_env(steps, source)

    # Determine status
    live_requested = live and bool(source.get("ARCLINK_E2E_LIVE", "").strip())

    if all_missing:
        status = "blocked_missing_credentials"
    elif not live_requested:
        status = "dry_run_ready"
    elif not runners:
        status = "live_ready_pending_execution"
    else:
        status = "live_executed"

    # Phase 4: Evaluate journey (runs step runners if live_executed)
    if status == "live_executed":
        # evaluate_journey checks os.environ for credentials, so patch it
        old_env = os.environ.copy()
        os.environ.update(source)
        try:
            evaluate_journey(steps, runners=runners, stop_on_failure=True)
        finally:
            os.environ.clear()
            os.environ.update(old_env)
    elif status == "blocked_missing_credentials":
        # Mark steps with their skip reasons
        for step in steps:
            m = [k for k in step.required_env if not source.get(k, "").strip()]
            if m:
                step.status = "skipped"
                step.skip_reason = f"missing env: {', '.join(m)}"

    # Phase 5: Build evidence ledger
    commit = get_commit_hash()
    run_id = generate_run_id(commit=commit)
    ledger = ledger_from_journey(steps, run_id=run_id, commit_hash=commit)

    # Phase 6: Write artifact
    evidence_path = ""
    if artifact_dir is not None or status in ("dry_run_ready", "live_executed"):
        out_dir = Path(artifact_dir or "evidence")
        out_dir.mkdir(parents=True, exist_ok=True)
        artifact_file = out_dir / f"{run_id}.json"
        artifact_file.write_text(ledger.to_json())
        evidence_path = str(artifact_file)

    # Determine exit code
    if status == "live_executed":
        exit_code = 0 if ledger.all_passed else 1
    elif status in ("dry_run_ready", "blocked_missing_credentials", "live_ready_pending_execution"):
        exit_code = 0
    else:
        exit_code = 1

    return LiveProofResult(
        status=status,
        missing_env=all_missing,
        host_readiness=readiness.to_dict(),
        provider_diagnostics=diagnostics.to_dict(),
        journey_summary=journey_summary(steps),
        evidence_path=evidence_path,
        exit_code=exit_code,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="ArcLink live proof orchestration. Dry-run by default.",
    )
    parser.add_argument(
        "--live", action="store_true",
        help="Attempt live execution (requires ARCLINK_E2E_LIVE=1 and credentials)",
    )
    parser.add_argument(
        "--artifact-dir", default=None,
        help="Directory for evidence JSON output (default: evidence/)",
    )
    parser.add_argument(
        "--docker-binary", default="docker",
        help="Docker binary name or path",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output full result as JSON",
    )
    args = parser.parse_args(argv)

    result = run_live_proof(
        live=args.live,
        artifact_dir=args.artifact_dir,
        docker_binary=args.docker_binary,
    )

    if args.json_output:
        print(result.to_json())
    else:
        print(f"Status: {result.status}")
        if result.missing_env:
            print(f"Missing: {', '.join(result.missing_env)}")
        if result.evidence_path:
            print(f"Evidence: {result.evidence_path}")
        summary = result.journey_summary.get("by_status", {})
        if summary:
            parts = [f"{k}={v}" for k, v in sorted(summary.items())]
            print(f"Journey: {', '.join(parts)}")

    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
