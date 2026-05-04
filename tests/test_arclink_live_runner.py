#!/usr/bin/env python3
"""Tests for arclink_live_runner - live proof orchestration."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from arclink_live_runner import LiveProofResult, run_live_proof, main, _collect_missing_env
from arclink_live_journey import build_journey
# Minimal env that satisfies host readiness (not journey steps)
_BASE_ENV: dict[str, str] = {
    "ARCLINK_PRODUCT_NAME": "test",
    "ARCLINK_BASE_DOMAIN": "test.local",
    "ARCLINK_PRIMARY_PROVIDER": "chutes",
}

# All journey env vars present
_FULL_ENV: dict[str, str] = {
    **_BASE_ENV,
    "ARCLINK_E2E_LIVE": "1",
    "STRIPE_SECRET_KEY": "sk_test_fake123456789",
    "STRIPE_WEBHOOK_SECRET": "whsec_fake123456789",
    "CLOUDFLARE_API_TOKEN": "cf_fake_token_123",
    "CLOUDFLARE_ZONE_ID": "zone_fake_123",
    "ARCLINK_E2E_DOCKER": "1",
    "CHUTES_API_KEY": "chutes_fake_key_123",
    "TELEGRAM_BOT_TOKEN": "123456:ABCfake",
    "DISCORD_BOT_TOKEN": "discord_fake_token",
}


class TestNoSecretDryRun(unittest.TestCase):
    """No-secret dry-run returns blocked summary with exact missing env names."""

    def test_blocked_with_missing_env_names(self):
        result = run_live_proof(env=_BASE_ENV, skip_ports=True)
        self.assertEqual(result.status, "blocked_missing_credentials")
        self.assertIn("ARCLINK_E2E_LIVE", result.missing_env)
        self.assertIn("STRIPE_SECRET_KEY", result.missing_env)
        self.assertIn("CLOUDFLARE_API_TOKEN", result.missing_env)
        self.assertIn("TELEGRAM_BOT_TOKEN", result.missing_env)
        self.assertIn("DISCORD_BOT_TOKEN", result.missing_env)
        self.assertEqual(result.exit_code, 0)

    def test_missing_env_never_contains_values(self):
        result = run_live_proof(env=_BASE_ENV, skip_ports=True)
        for name in result.missing_env:
            self.assertTrue(name.isupper() or name.startswith("ARCLINK_"),
                            f"missing_env should be var names, got: {name}")

    def test_journey_steps_marked_skipped(self):
        result = run_live_proof(env=_BASE_ENV, skip_ports=True)
        steps = result.journey_summary.get("steps", [])
        self.assertTrue(len(steps) > 0)
        for step in steps:
            self.assertEqual(step["status"], "skipped")


class TestRedaction(unittest.TestCase):
    """All returned/written artifacts redact secret-looking values."""

    def test_evidence_artifact_redacted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_live_proof(
                env=_FULL_ENV, skip_ports=True, artifact_dir=tmpdir,
            )
            self.assertTrue(result.evidence_path)
            with open(result.evidence_path) as f:
                data = json.load(f)
            raw = json.dumps(data)
            self.assertNotIn("sk_test_fake123456789", raw)
            self.assertNotIn("whsec_fake123456789", raw)
            self.assertNotIn("cf_fake_token_123", raw)
            self.assertNotIn("chutes_fake_key_123", raw)

    def test_result_json_no_secrets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_live_proof(env=_FULL_ENV, skip_ports=True, artifact_dir=tmpdir)
            raw = result.to_json()
            self.assertNotIn("sk_test_fake123456789", raw)
            self.assertNotIn("whsec_fake123456789", raw)


class TestCredentialPresentDryRun(unittest.TestCase):
    """Credential-present dry-run marks plan ready but does not claim live proof."""

    def test_dry_run_ready_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_live_proof(env=_FULL_ENV, skip_ports=True, live=False, artifact_dir=tmpdir)
            self.assertEqual(result.status, "dry_run_ready")
            self.assertEqual(result.missing_env, [])
            self.assertEqual(result.exit_code, 0)

    def test_no_live_claim_without_live_flag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_live_proof(env=_FULL_ENV, skip_ports=True, live=False, artifact_dir=tmpdir)
            self.assertNotEqual(result.status, "live_executed")

    def test_live_ready_pending_without_runners(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_live_proof(env=_FULL_ENV, skip_ports=True, live=True, artifact_dir=tmpdir)
            self.assertEqual(result.status, "live_ready_pending_execution")
            self.assertEqual(result.exit_code, 0)


class TestFakeRunners(unittest.TestCase):
    """Injected fake runners produce a passing evidence ledger."""

    def _make_fake_runners(self):
        def fake_runner(step):
            return {"fake": True, "step": step.name}
        steps = build_journey()
        return {s.name: fake_runner for s in steps}

    def test_live_executed_with_fake_runners(self):
        runners = self._make_fake_runners()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_live_proof(
                env=_FULL_ENV, skip_ports=True, live=True,
                runners=runners, artifact_dir=tmpdir,
            )
            self.assertEqual(result.status, "live_executed")
            self.assertEqual(result.exit_code, 0)
            self.assertTrue(result.evidence_path)
            with open(result.evidence_path) as f:
                data = json.load(f)
            self.assertTrue(len(data["records"]) > 0)
            for rec in data["records"]:
                self.assertEqual(rec["status"], "passed")

    def test_failing_runner_produces_nonzero(self):
        def failing_runner(step):
            raise RuntimeError("simulated failure")
        runners = {"web_onboarding_start": failing_runner}
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_live_proof(
                env=_FULL_ENV, skip_ports=True, live=True, runners=runners, artifact_dir=tmpdir,
            )
            self.assertEqual(result.status, "live_executed")
            self.assertEqual(result.exit_code, 1)


class TestCLI(unittest.TestCase):
    """CLI exits 0 for dry-run readiness."""

    def test_cli_dry_run_exits_zero(self):
        # With no env, blocked but exit 0
        import io
        from contextlib import redirect_stdout
        old_env = os.environ.copy()
        os.environ.clear()
        os.environ.update(_BASE_ENV)
        try:
            with redirect_stdout(io.StringIO()):
                code = main(["--json"])
        finally:
            os.environ.clear()
            os.environ.update(old_env)
        self.assertEqual(code, 0)

    def test_cli_json_output(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        old_env = os.environ.copy()
        os.environ.clear()
        os.environ.update(_BASE_ENV)
        try:
            with redirect_stdout(buf):
                main(["--json"])
        finally:
            os.environ.clear()
            os.environ.update(old_env)
        data = json.loads(buf.getvalue())
        self.assertIn("status", data)
        self.assertIn("missing_env", data)


class TestCollectMissing(unittest.TestCase):
    def test_deduplicates(self):
        steps = build_journey()
        missing = _collect_missing_env(steps, {})
        self.assertEqual(len(missing), len(set(missing)))


if __name__ == "__main__":
    unittest.main()
