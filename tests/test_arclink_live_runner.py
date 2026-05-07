#!/usr/bin/env python3
"""Tests for arclink_live_runner - live proof orchestration."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import arclink_live_runner as live_runner_mod
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

_WORKSPACE_ENV: dict[str, str] = {
    **_BASE_ENV,
    "ARCLINK_E2E_LIVE": "1",
    "ARCLINK_E2E_DOCKER": "1",
    "ARCLINK_WORKSPACE_PROOF_TLS_URL": "https://dashboard.example.test",
    "ARCLINK_WORKSPACE_PROOF_AUTH": "session_fake_secret",
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


class TestWorkspaceProofJourney(unittest.TestCase):
    """Workspace mode plans Drive, Code, and Terminal TLS proof without secrets."""

    def test_workspace_missing_env_names_do_not_include_hosted_provider_secrets(self):
        result = run_live_proof(env=_BASE_ENV, skip_ports=True, journey="workspace")
        self.assertEqual(result.status, "blocked_missing_credentials")
        self.assertEqual(result.journey, "workspace")
        self.assertIn("ARCLINK_WORKSPACE_PROOF_TLS_URL", result.missing_env)
        self.assertIn("ARCLINK_WORKSPACE_PROOF_AUTH", result.missing_env)
        self.assertNotIn("STRIPE_SECRET_KEY", result.missing_env)
        self.assertNotIn("TELEGRAM_BOT_TOKEN", result.missing_env)

    def test_workspace_dry_run_ready_does_not_claim_live_proof(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_live_proof(
                env=_WORKSPACE_ENV,
                skip_ports=True,
                live=False,
                artifact_dir=tmpdir,
                journey="workspace",
            )
            self.assertEqual(result.status, "dry_run_ready")
            self.assertEqual(result.journey, "workspace")
            self.assertEqual(result.missing_env, [])
            self.assertNotEqual(result.status, "live_executed")

    def test_workspace_fake_runners_cover_all_plugin_proof_steps(self):
        steps = build_journey("workspace")
        runners = {step.name: (lambda s: {"step": s.name}) for step in steps}
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_live_proof(
                env=_WORKSPACE_ENV,
                skip_ports=True,
                live=True,
                runners=runners,
                artifact_dir=tmpdir,
                journey="workspace",
            )
            self.assertEqual(result.status, "live_executed")
            self.assertEqual(result.exit_code, 0)
            names = [step["name"] for step in result.journey_summary["steps"]]
            self.assertIn("drive_tls_desktop_proof", names)
            self.assertIn("code_tls_mobile_proof", names)
            self.assertIn("terminal_tls_desktop_proof", names)

    def test_workspace_auth_value_redacted_from_artifact(self):
        def runner(step):
            return {"ARCLINK_WORKSPACE_PROOF_AUTH": _WORKSPACE_ENV["ARCLINK_WORKSPACE_PROOF_AUTH"]}

        runners = {step.name: runner for step in build_journey("workspace")}
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_live_proof(
                env=_WORKSPACE_ENV,
                skip_ports=True,
                live=True,
                runners=runners,
                artifact_dir=tmpdir,
                journey="workspace",
            )
            self.assertTrue(result.evidence_path)
            with open(result.evidence_path) as f:
                raw = json.dumps(json.load(f))
            self.assertNotIn("session_fake_secret", raw)

    def test_workspace_live_uses_default_real_runners_when_no_runners_injected(self):
        calls = []
        original_run = live_runner_mod.subprocess.run

        def fake_run(args, **kwargs):
            call_env = dict(kwargs.get("env") or {})
            calls.append({"args": list(args), "env": call_env})
            if args and args[0] == "node":
                payload = {
                    "plugin": call_env.get("ARCLINK_WORKSPACE_PROOF_PLUGIN"),
                    "viewport": call_env.get("ARCLINK_WORKSPACE_PROOF_VIEWPORT"),
                    "result": {"checks": 6},
                    "screenshot": "../evidence/workspace-screenshots/proof.png",
                }
                return SimpleNamespace(returncode=0, stdout=json.dumps(payload))
            return SimpleNamespace(returncode=0, stdout="redacted test output")

        live_runner_mod.subprocess.run = fake_run
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                result = run_live_proof(
                    env=_WORKSPACE_ENV,
                    skip_ports=True,
                    live=True,
                    artifact_dir=tmpdir,
                    journey="workspace",
                )
        finally:
            live_runner_mod.subprocess.run = original_run

        self.assertEqual(result.status, "live_executed")
        self.assertEqual(result.exit_code, 0)
        called_args = [call["args"] for call in calls]
        self.assertIn(["./deploy.sh", "docker", "upgrade"], called_args)
        self.assertIn(["./deploy.sh", "docker", "health"], called_args)
        browser_calls = [args for args in called_args if args and args[0] == "node"]
        self.assertEqual(len(browser_calls), 6)
        web_root = os.path.realpath(str(live_runner_mod._REPO_ROOT / "web"))
        for args in browser_calls:
            script_path = os.path.realpath(args[1])
            self.assertEqual(os.path.commonpath([web_root, script_path]), web_root)
        raw_args = json.dumps(called_args)
        self.assertNotIn(_WORKSPACE_ENV["ARCLINK_WORKSPACE_PROOF_AUTH"], raw_args)
        proof_calls = [
            call for call in calls
            if call["args"] and (call["args"][:2] == ["./deploy.sh", "docker"] or call["args"][0] == "node")
        ]
        self.assertTrue(all(call["env"].get("ARCLINK_WORKSPACE_PROOF_AUTH") == _WORKSPACE_ENV["ARCLINK_WORKSPACE_PROOF_AUTH"] for call in proof_calls))
        browser_evidence = [
            step["evidence"].get("browser")
            for step in result.journey_summary["steps"]
            if step["name"].endswith("_proof")
        ]
        self.assertTrue(all(item and item["checks"] == 6 for item in browser_evidence))
        screenshots = [
            step["evidence"].get("screenshot")
            for step in result.journey_summary["steps"]
            if step["name"].endswith("_proof")
        ]
        self.assertTrue(all(item and item.startswith("../evidence/workspace-screenshots/") for item in screenshots))

    def test_workspace_default_browser_runner_rejects_non_tls_target(self):
        bad_env = {**_WORKSPACE_ENV, "ARCLINK_WORKSPACE_PROOF_TLS_URL": "http://dashboard.example.test"}
        runners = {
            "workspace_docker_upgrade_reconcile": lambda _step: {"ok": True},
            "workspace_docker_health": lambda _step: {"ok": True},
            "drive_tls_desktop_proof": lambda _step: live_runner_mod._browser_proof_runner("drive_tls_desktop_proof", bad_env),
        }
        result = run_live_proof(
            env=bad_env,
            skip_ports=True,
            live=True,
            runners=runners,
            journey="workspace",
        )
        self.assertEqual(result.status, "live_executed")
        self.assertEqual(result.exit_code, 1)
        failed = [step for step in result.journey_summary["steps"] if step["status"] == "failed"]
        self.assertTrue(failed)
        self.assertIn("HTTPS", failed[0]["error"])

    def test_workspace_browser_script_uses_native_dashboard_plugin_navigation(self):
        script = live_runner_mod._browser_runner_script()
        self.assertIn("async function openPluginPage", script)
        self.assertIn("a[href$='/\" + plugin + \"']", script)
        self.assertIn('openPluginPage(page, "Drive", "New Folder")', script)
        self.assertIn('openPluginPage(page, "Code", "Explorer")', script)
        self.assertIn('openPluginPage(page, "Terminal", "Sessions")', script)
        self.assertIn("captureSanitizedScreenshot", script)
        self.assertIn("ARCLINK_WORKSPACE_PROOF_SCREENSHOT_DIR", script)


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
