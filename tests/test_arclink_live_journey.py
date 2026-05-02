#!/usr/bin/env python3
"""Tests for arclink_live_journey — no live secrets required."""
from __future__ import annotations

import os
import unittest

from arclink_test_helpers import load_module

journey_mod = load_module("arclink_live_journey.py", "journey_test")


class TestJourneyStepModel(unittest.TestCase):
    def test_step_default_status(self):
        step = journey_mod.JourneyStep(name="test", description="desc")
        self.assertEqual(step.status, "pending")
        self.assertEqual(step.skip_reason, "")
        self.assertEqual(step.evidence, {})

    def test_step_to_dict_includes_duration(self):
        step = journey_mod.JourneyStep(name="t", description="d",
                                       started_at=100.0, finished_at=100.5)
        d = step.to_dict()
        self.assertEqual(d["duration_ms"], 500.0)
        self.assertEqual(d["name"], "t")

    def test_step_duration_zero_when_not_run(self):
        step = journey_mod.JourneyStep(name="t", description="d")
        self.assertEqual(step.duration_ms, 0.0)


class TestCredentialChecking(unittest.TestCase):
    def test_missing_credentials_reports_names(self):
        step = journey_mod.JourneyStep(
            name="t", description="d",
            required_env=["ARCLINK_NONEXISTENT_VAR_XYZ"],
        )
        missing = journey_mod.missing_credentials(step)
        self.assertEqual(missing, ["ARCLINK_NONEXISTENT_VAR_XYZ"])

    def test_check_step_credentials_false_when_missing(self):
        step = journey_mod.JourneyStep(
            name="t", description="d",
            required_env=["ARCLINK_NONEXISTENT_VAR_XYZ"],
        )
        self.assertFalse(journey_mod.check_step_credentials(step))

    def test_check_step_credentials_true_with_no_requirements(self):
        step = journey_mod.JourneyStep(name="t", description="d")
        self.assertTrue(journey_mod.check_step_credentials(step))


class TestBuildJourney(unittest.TestCase):
    def test_build_journey_returns_ordered_steps(self):
        steps = journey_mod.build_journey()
        self.assertGreater(len(steps), 5)
        self.assertEqual(steps[0].name, "web_onboarding_start")
        for step in steps:
            self.assertEqual(step.status, "pending")

    def test_all_steps_have_live_gate(self):
        for step in journey_mod.build_journey():
            self.assertIn("ARCLINK_E2E_LIVE", step.required_env,
                          f"{step.name} missing ARCLINK_E2E_LIVE gate")


class TestEvaluateJourney(unittest.TestCase):
    def test_all_skip_without_credentials(self):
        """Without ARCLINK_E2E_LIVE, all steps skip cleanly."""
        old = os.environ.pop("ARCLINK_E2E_LIVE", None)
        try:
            steps = journey_mod.build_journey()
            journey_mod.evaluate_journey(steps)
            for step in steps:
                self.assertEqual(step.status, "skipped", f"{step.name} not skipped")
                self.assertIn("missing env", step.skip_reason)
        finally:
            if old is not None:
                os.environ["ARCLINK_E2E_LIVE"] = old

    def test_runner_called_when_credentials_present(self):
        step = journey_mod.JourneyStep(name="test_step", description="d")
        called = []

        def runner(s):
            called.append(s.name)
            return {"key": "value"}

        journey_mod.evaluate_journey([step], {"test_step": runner})
        self.assertEqual(step.status, "passed")
        self.assertEqual(step.evidence, {"key": "value"})
        self.assertEqual(called, ["test_step"])

    def test_stop_on_failure(self):
        s1 = journey_mod.JourneyStep(name="fail", description="d")
        s2 = journey_mod.JourneyStep(name="after", description="d")

        def fail_runner(s):
            raise RuntimeError("boom")

        journey_mod.evaluate_journey([s1, s2], {"fail": fail_runner, "after": lambda s: {}})
        self.assertEqual(s1.status, "failed")
        self.assertIn("boom", s1.error)
        self.assertEqual(s2.status, "skipped")
        self.assertEqual(s2.skip_reason, "prior step failed")

    def test_continue_on_failure(self):
        s1 = journey_mod.JourneyStep(name="fail", description="d")
        s2 = journey_mod.JourneyStep(name="ok", description="d")

        journey_mod.evaluate_journey(
            [s1, s2],
            {"fail": lambda s: (_ for _ in ()).throw(RuntimeError("x")),
             "ok": lambda s: {}},
            stop_on_failure=False,
        )
        self.assertEqual(s1.status, "failed")
        self.assertEqual(s2.status, "passed")

    def test_no_runner_skips(self):
        step = journey_mod.JourneyStep(name="unregistered", description="d")
        journey_mod.evaluate_journey([step], {})
        self.assertEqual(step.status, "skipped")
        self.assertIn("no runner", step.skip_reason)


class TestSummaryHelpers(unittest.TestCase):
    def test_journey_summary_structure(self):
        steps = [
            journey_mod.JourneyStep(name="a", description="d", status="passed"),
            journey_mod.JourneyStep(name="b", description="d", status="skipped"),
        ]
        summary = journey_mod.journey_summary(steps)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["by_status"]["passed"], 1)
        self.assertEqual(summary["by_status"]["skipped"], 1)

    def test_all_passed(self):
        steps = [journey_mod.JourneyStep(name="a", description="d", status="passed")]
        self.assertTrue(journey_mod.all_passed(steps))
        steps.append(journey_mod.JourneyStep(name="b", description="d", status="skipped"))
        self.assertFalse(journey_mod.all_passed(steps))

    def test_all_skipped_or_passed(self):
        steps = [
            journey_mod.JourneyStep(name="a", description="d", status="passed"),
            journey_mod.JourneyStep(name="b", description="d", status="skipped"),
        ]
        self.assertTrue(journey_mod.all_skipped_or_passed(steps))


if __name__ == "__main__":
    unittest.main(verbosity=2)
