#!/usr/bin/env python3
"""ArcLink live journey model - Gap D scaffolding.

Ordered step model for the full customer journey proof:
  web onboarding -> checkout -> webhook/entitlement -> provisioning
  -> DNS/health -> user dashboard -> admin dashboard verification.

Each step declares required credentials, a skip reason when absent,
and evidence fields that are populated during a live run. The model
is usable without any live secrets for planning and dry-run validation.
"""
from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Step model
# ---------------------------------------------------------------------------

@dataclass
class JourneyStep:
    """One step in the ordered live journey."""
    name: str
    description: str
    required_env: list[str] = field(default_factory=list)
    status: str = "pending"          # pending | skipped | running | passed | failed
    skip_reason: str = ""
    error: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    started_at: float = 0.0
    finished_at: float = 0.0

    @property
    def duration_ms(self) -> float:
        if self.started_at and self.finished_at:
            return round((self.finished_at - self.started_at) * 1000, 1)
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["duration_ms"] = self.duration_ms
        return d


# ---------------------------------------------------------------------------
# Credential checking
# ---------------------------------------------------------------------------

def _env_present(key: str) -> bool:
    return bool(os.environ.get(key, "").strip())


def check_step_credentials(step: JourneyStep) -> bool:
    """Return True if all required env vars for the step are present."""
    return all(_env_present(k) for k in step.required_env)


def missing_credentials(step: JourneyStep) -> list[str]:
    """Return names of missing env vars (never values)."""
    return [k for k in step.required_env if not _env_present(k)]


# ---------------------------------------------------------------------------
# Journey definition
# ---------------------------------------------------------------------------

_JOURNEY_STEPS: list[dict[str, Any]] = [
    {
        "name": "web_onboarding_start",
        "description": "Start onboarding session via hosted API",
        "required_env": ["ARCLINK_E2E_LIVE"],
    },
    {
        "name": "web_onboarding_checkout",
        "description": "Create Stripe checkout session for onboarding",
        "required_env": ["ARCLINK_E2E_LIVE", "STRIPE_SECRET_KEY"],
    },
    {
        "name": "stripe_webhook_delivery",
        "description": "Deliver checkout.session.completed webhook",
        "required_env": ["ARCLINK_E2E_LIVE", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"],
    },
    {
        "name": "entitlement_activation",
        "description": "Verify entitlement transitions to paid after webhook",
        "required_env": ["ARCLINK_E2E_LIVE"],
    },
    {
        "name": "provisioning_request",
        "description": "Submit provisioning job for the deployment",
        "required_env": ["ARCLINK_E2E_LIVE"],
    },
    {
        "name": "dns_health_check",
        "description": "Verify DNS records and service health endpoints",
        "required_env": ["ARCLINK_E2E_LIVE", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ZONE_ID"],
    },
    {
        "name": "docker_deployment_check",
        "description": "Verify Docker Compose stack is running and healthy",
        "required_env": ["ARCLINK_E2E_LIVE", "ARCLINK_E2E_DOCKER"],
    },
    {
        "name": "chutes_key_provisioning",
        "description": "Verify per-deployment Chutes API key creation",
        "required_env": ["ARCLINK_E2E_LIVE", "CHUTES_API_KEY"],
    },
    {
        "name": "user_dashboard_verification",
        "description": "Login as user and verify dashboard data",
        "required_env": ["ARCLINK_E2E_LIVE"],
    },
    {
        "name": "admin_dashboard_verification",
        "description": "Login as admin and verify deployment visibility",
        "required_env": ["ARCLINK_E2E_LIVE"],
    },
    {
        "name": "telegram_bot_check",
        "description": "Verify Telegram bot reachability",
        "required_env": ["ARCLINK_E2E_LIVE", "TELEGRAM_BOT_TOKEN"],
    },
    {
        "name": "discord_bot_check",
        "description": "Verify Discord bot reachability",
        "required_env": ["ARCLINK_E2E_LIVE", "DISCORD_BOT_TOKEN"],
    },
]


def build_journey() -> list[JourneyStep]:
    """Build the ordered journey step list."""
    return [JourneyStep(**spec) for spec in _JOURNEY_STEPS]


# ---------------------------------------------------------------------------
# Journey runner
# ---------------------------------------------------------------------------

StepRunner = Callable[[JourneyStep], dict[str, Any]]


def evaluate_journey(
    steps: list[JourneyStep],
    runners: dict[str, StepRunner] | None = None,
    *,
    stop_on_failure: bool = True,
) -> list[JourneyStep]:
    """Evaluate journey steps in order.

    For each step:
    - If credentials are missing, mark skipped with reason.
    - If a runner is provided for the step name, call it and capture evidence.
    - If stop_on_failure and a step fails, remaining steps are skipped.

    Returns the same step list, mutated in place for convenience.
    """
    runners = runners or {}
    failed = False

    for step in steps:
        if failed and stop_on_failure:
            step.status = "skipped"
            step.skip_reason = "prior step failed"
            continue

        missing = missing_credentials(step)
        if missing:
            step.status = "skipped"
            step.skip_reason = f"missing env: {', '.join(missing)}"
            continue

        runner = runners.get(step.name)
        if runner is None:
            step.status = "skipped"
            step.skip_reason = "no runner registered"
            continue

        step.status = "running"
        step.started_at = time.time()
        try:
            evidence = runner(step)
            step.evidence = evidence or {}
            step.status = "passed"
        except Exception as exc:
            step.status = "failed"
            step.error = str(exc)
            failed = True
        finally:
            step.finished_at = time.time()

    return steps


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------

def journey_summary(steps: list[JourneyStep]) -> dict[str, Any]:
    """Return a summary dict suitable for evidence recording."""
    by_status: dict[str, int] = {}
    for s in steps:
        by_status[s.status] = by_status.get(s.status, 0) + 1
    return {
        "total": len(steps),
        "by_status": by_status,
        "steps": [s.to_dict() for s in steps],
    }


def all_passed(steps: list[JourneyStep]) -> bool:
    return all(s.status == "passed" for s in steps)


def all_skipped_or_passed(steps: list[JourneyStep]) -> bool:
    return all(s.status in ("passed", "skipped") for s in steps)
