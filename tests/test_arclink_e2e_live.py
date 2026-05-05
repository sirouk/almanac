#!/usr/bin/env python3
"""ArcLink live E2E harness - Production 12.

Secret-gated live E2E provider checks that support the full journey proof.
Each provider test is independently gated on its credential env var and skips
gracefully when absent. Never leaks secrets or makes destructive calls.

Gate: ARCLINK_E2E_LIVE=1 plus provider-specific credentials. Docker proof has
an additional ARCLINK_E2E_DOCKER=1 opt-in because even read-only Docker access
should be deliberate on shared hosts.

The ordered journey model from arclink_live_journey is used to define step
ordering and credential gates. Individual provider tests below map to journey
steps and can feed evidence into the arclink_evidence ledger.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from typing import Any
from urllib import request as urlrequest

from arclink_test_helpers import load_module, memory_db

# ---------------------------------------------------------------------------
# Gate: skip entire module unless ARCLINK_E2E_LIVE=1
# ---------------------------------------------------------------------------

LIVE = os.environ.get("ARCLINK_E2E_LIVE", "") == "1"

# Load journey model (always available, no secrets needed)
journey_mod = load_module("arclink_live_journey.py", "journey_e2e_live")
evidence_mod = load_module("arclink_evidence.py", "evidence_e2e_live")


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def _skip_unless(cond: bool, reason: str):
    if not cond:
        raise unittest.SkipTest(reason)


def _read_json(url: str, *, headers: dict[str, str] | None = None) -> Any:
    request_headers = {
        "User-Agent": "DiscordBot (https://arclink.online, 0.1) Python/3",
        **dict(headers or {}),
    }
    req = urlrequest.Request(url, headers=request_headers)
    with urlrequest.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


class LiveE2EBase(unittest.TestCase):
    """Base for live E2E tests with shared module loading."""

    @classmethod
    def setUpClass(cls):
        if not LIVE:
            raise unittest.SkipTest("ARCLINK_E2E_LIVE not set")
        cls.control = load_module("arclink_control.py", "control_e2e_live")
        cls.api = load_module("arclink_api_auth.py", "api_e2e_live")
        cls.hosted = load_module("arclink_hosted_api.py", "hosted_e2e_live")
        cls.adapters = load_module("arclink_adapters.py", "adapters_e2e_live")
        cls.chutes = load_module("arclink_chutes.py", "chutes_e2e_live")
        cls.telegram = load_module("arclink_telegram.py", "telegram_e2e_live")
        cls.discord = load_module("arclink_discord.py", "discord_e2e_live")


class TestStripeE2ELive(LiveE2EBase):
    """Live Stripe checkout and webhook tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.stripe_key = _env("STRIPE_SECRET_KEY")
        cls.webhook_secret = _env("STRIPE_WEBHOOK_SECRET")
        if not cls.stripe_key:
            raise unittest.SkipTest("STRIPE_SECRET_KEY not set")

    def test_stripe_checkout_session_creation(self):
        """Create a real Stripe checkout session (test mode)."""
        _skip_unless(self.stripe_key.startswith("sk_test_"),
                     "Refusing non-test Stripe key")
        stripe_client = self.adapters.LiveStripeClient(secret_key=self.stripe_key)
        conn = memory_db(self.control)
        config = self.hosted.HostedApiConfig(env={
            "ARCLINK_BASE_DOMAIN": "example.test",
            "STRIPE_WEBHOOK_SECRET": self.webhook_secret or "whsec_test",
        })

        status, payload, _ = self.hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/onboarding/start",
            headers={},
            body=json.dumps({
                "channel": "web",
                "email": "live-e2e@example.test",
                "plan_id": "sovereign",
            }),
            config=config,
        )
        self.assertEqual(status, 201, f"onboarding/start failed: {payload}")
        session_id = payload["session"]["session_id"]

        price_id = _env("ARCLINK_TEST_PRICE_ID") or "price_arclink_sovereign"
        status, payload, _ = self.hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/onboarding/checkout",
            headers={},
            body=json.dumps({
                "session_id": session_id,
                "price_id": price_id,
                "success_url": "https://app.example.test/success",
                "cancel_url": "https://app.example.test/cancel",
            }),
            config=config,
            stripe_client=stripe_client,
        )
        self.assertEqual(status, 200, f"checkout failed: {payload}")
        self.assertTrue(payload["session"].get("checkout_url"), "no checkout_url")


class TestCloudflareE2ELive(LiveE2EBase):
    """Live Cloudflare DNS tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cf_token = _env("CLOUDFLARE_API_TOKEN")
        cls.cf_zone = _env("CLOUDFLARE_ZONE_ID")
        if not cls.cf_token or not cls.cf_zone:
            raise unittest.SkipTest("CLOUDFLARE_API_TOKEN or CLOUDFLARE_ZONE_ID not set")

    def test_cloudflare_dns_drift_check(self):
        """Check Cloudflare DNS API reachability without mutating records."""
        payload = _read_json(
            f"https://api.cloudflare.com/client/v4/zones/{self.cf_zone}/dns_records?per_page=1",
            headers={"Authorization": f"Bearer {self.cf_token}"},
        )
        self.assertTrue(payload.get("success"), f"Cloudflare API was not successful: {payload}")
        self.assertIsInstance(payload.get("result"), list, "Cloudflare result should be a list")


class TestChutesE2ELive(LiveE2EBase):
    """Live Chutes inference tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.chutes_key = _env("CHUTES_API_KEY")
        if not cls.chutes_key:
            raise unittest.SkipTest("CHUTES_API_KEY not set")

    def test_chutes_model_catalog(self):
        """Fetch model catalog from live Chutes API (read-only)."""
        catalog_client = self.chutes.ChutesCatalogClient()
        catalog = catalog_client.list_models(api_key=self.chutes_key)
        self.assertIsInstance(catalog, dict, "catalog should be a dict keyed by model id")
        self.assertGreater(len(catalog), 0, "catalog should not be empty")


class TestTelegramE2ELive(LiveE2EBase):
    """Live Telegram bot tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tg_token = _env("TELEGRAM_BOT_TOKEN")
        if not cls.tg_token:
            raise unittest.SkipTest("TELEGRAM_BOT_TOKEN not set")

    def test_telegram_bot_info(self):
        """Fetch bot info from Telegram API (read-only)."""
        config = self.telegram.TelegramConfig(
            bot_token=self.tg_token,
            bot_username="",
            webhook_url="",
        )
        result = self.telegram.LiveTelegramTransport(config)._call("getMe")
        self.assertTrue(result.get("ok"), f"unexpected Telegram getMe response: {result}")
        self.assertTrue((result.get("result") or {}).get("id"), f"missing Telegram bot id: {result}")


class TestDiscordE2ELive(LiveE2EBase):
    """Live Discord bot tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.discord_token = _env("DISCORD_BOT_TOKEN")
        if not cls.discord_token:
            raise unittest.SkipTest("DISCORD_BOT_TOKEN not set")

    def test_discord_bot_info(self):
        """Fetch bot info from Discord API (read-only)."""
        info = _read_json(
            "https://discord.com/api/v10/users/@me",
            headers={"Authorization": f"Bot {self.discord_token}"},
        )
        self.assertTrue(info.get("id") or info.get("username"), f"unexpected bot info: {info}")


class TestDockerE2ELive(LiveE2EBase):
    """Read-only Docker availability proof for live host validation."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if _env("ARCLINK_E2E_DOCKER") != "1":
            raise unittest.SkipTest("ARCLINK_E2E_DOCKER not set")
        if shutil.which("docker") is None:
            raise unittest.SkipTest("docker command not found")

    def test_docker_compose_version(self):
        """Verify Docker Compose is reachable without mutating containers."""
        result = subprocess.run(
            ["docker", "compose", "version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr.strip() or result.stdout.strip())
        self.assertIn("Docker Compose", result.stdout)


class TestJourneyModelSkipsCleanly(unittest.TestCase):
    """Verify the ordered journey model skips cleanly without credentials."""

    def test_journey_skips_without_live_flag(self):
        old = os.environ.pop("ARCLINK_E2E_LIVE", None)
        try:
            steps = journey_mod.build_journey()
            journey_mod.evaluate_journey(steps)
            self.assertTrue(journey_mod.all_skipped_or_passed(steps))
            for step in steps:
                self.assertEqual(step.status, "skipped")
        finally:
            if old is not None:
                os.environ["ARCLINK_E2E_LIVE"] = old

    def test_evidence_ledger_from_skipped_journey(self):
        old = os.environ.pop("ARCLINK_E2E_LIVE", None)
        try:
            steps = journey_mod.build_journey()
            journey_mod.evaluate_journey(steps)
            ledger = evidence_mod.ledger_from_journey(steps, run_id="test_skip")
            self.assertEqual(len(ledger.records), len(steps))
            for r in ledger.records:
                self.assertEqual(r.status, "skipped")
            j = ledger.to_json()
            self.assertNotIn("sk_test_", j)
            self.assertNotIn("sk_live_", j)
        finally:
            if old is not None:
                os.environ["ARCLINK_E2E_LIVE"] = old


if __name__ == "__main__":
    unittest.main(verbosity=2)
