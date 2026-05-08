#!/usr/bin/env python3
"""Tests for arclink_evidence - deterministic output and secret redaction."""
from __future__ import annotations

import json
import unittest

from arclink_test_helpers import load_module

evidence = load_module("arclink_evidence.py", "evidence_test")
journey_mod = load_module("arclink_live_journey.py", "journey_ev_test")


class TestRedaction(unittest.TestCase):
    def test_redact_value_short(self):
        self.assertEqual(evidence.redact_value("abc"), "***")

    def test_redact_value_long(self):
        result = evidence.redact_value("sk_test_abcdef1234567890")
        self.assertTrue(result.startswith("sk_test_"))
        self.assertTrue(result.endswith("***"))
        self.assertNotIn("1234567890", result)

    def test_redact_value_empty(self):
        self.assertEqual(evidence.redact_value(""), "***")

    def test_redact_dict_sensitive_keys(self):
        d = {"STRIPE_SECRET_KEY": "sk_test_abc123longtoken", "safe_key": "visible"}
        result = evidence.redact_dict(d)
        self.assertIn("***", result["STRIPE_SECRET_KEY"])
        self.assertEqual(result["safe_key"], "visible")

    def test_redact_dict_nested(self):
        d = {"outer": {"CLOUDFLARE_API_TOKEN": "token_longvalue_here"}}
        result = evidence.redact_dict(d)
        self.assertIn("***", result["outer"]["CLOUDFLARE_API_TOKEN"])

    def test_redact_dict_preserves_non_string(self):
        d = {"STRIPE_SECRET_KEY": 42}
        result = evidence.redact_dict(d)
        self.assertEqual(result["STRIPE_SECRET_KEY"], 42)

    def test_redact_dict_sensitive_key_heuristic(self):
        d = {"api_token": "abcdef1234567890abcdef"}
        result = evidence.redact_dict(d)
        self.assertNotIn("1234567890", result["api_token"])
        self.assertIn("***", result["api_token"])

    def test_redact_text_url_query_secret(self):
        url = "https://example.test/callback?token=abcdef1234567890&ok=1"
        result = evidence.redact_text(url)
        self.assertIn("token=***", result)
        self.assertNotIn("abcdef1234567890", result)


class TestEvidenceRecord(unittest.TestCase):
    def test_to_dict(self):
        r = evidence.EvidenceRecord(step_name="test", status="passed", timestamp=1000.0)
        d = r.to_dict()
        self.assertEqual(d["step_name"], "test")
        self.assertEqual(d["status"], "passed")

    def test_to_dict_redacts_url_query_secret(self):
        r = evidence.EvidenceRecord(
            step_name="test",
            status="passed",
            url="https://example.test?api_key=secretvalue123456",
        )
        d = r.to_dict()
        self.assertIn("api_key=***", d["url"])
        self.assertNotIn("secretvalue123456", d["url"])

    def test_record_from_journey_step(self):
        step = journey_mod.JourneyStep(
            name="checkout", description="d", status="passed",
            finished_at=1000.0, evidence={"url": "https://example.test"},
        )
        r = evidence.record_from_step(step, commit_hash="abc1234")
        self.assertEqual(r.step_name, "checkout")
        self.assertEqual(r.status, "passed")
        self.assertEqual(r.commit_hash, "abc1234")

    def test_record_from_dict(self):
        d = {"name": "dns", "status": "skipped", "evidence": {}, "error": ""}
        r = evidence.record_from_step(d)
        self.assertEqual(r.step_name, "dns")


class TestEvidenceLedger(unittest.TestCase):
    def test_ledger_add_and_summary(self):
        ledger = evidence.EvidenceLedger(run_id="test_run")
        ledger.add(evidence.EvidenceRecord(step_name="a", status="passed"))
        ledger.add(evidence.EvidenceRecord(step_name="b", status="skipped"))
        self.assertEqual(len(ledger.records), 2)
        self.assertEqual(ledger.summary, {"passed": 1, "skipped": 1})
        self.assertFalse(ledger.all_passed)

    def test_ledger_to_json_deterministic(self):
        ledger = evidence.EvidenceLedger(
            run_id="run_abc", started_at=1000.0, finished_at=1001.0,
            commit_hash="abc1234",
        )
        ledger.add(evidence.EvidenceRecord(step_name="t", status="passed", timestamp=1000.5))
        j1 = ledger.to_json()
        j2 = ledger.to_json()
        self.assertEqual(j1, j2)
        parsed = json.loads(j1)
        self.assertEqual(parsed["run_id"], "run_abc")
        self.assertEqual(parsed["duration_ms"], 1000.0)

    def test_ledger_duration_zero_when_not_set(self):
        ledger = evidence.EvidenceLedger()
        self.assertEqual(ledger.duration_ms, 0.0)


class TestRunIdGeneration(unittest.TestCase):
    def test_deterministic_with_same_inputs(self):
        id1 = evidence.generate_run_id(prefix="run", commit="abc", ts=1000.0)
        id2 = evidence.generate_run_id(prefix="run", commit="abc", ts=1000.0)
        self.assertEqual(id1, id2)
        self.assertTrue(id1.startswith("run_"))

    def test_different_inputs_different_ids(self):
        id1 = evidence.generate_run_id(prefix="run", commit="abc", ts=1000.0)
        id2 = evidence.generate_run_id(prefix="run", commit="xyz", ts=1000.0)
        self.assertNotEqual(id1, id2)


class TestLedgerFromJourney(unittest.TestCase):
    def test_builds_from_journey_steps(self):
        steps = [
            journey_mod.JourneyStep(name="a", description="d", status="passed",
                                    started_at=100.0, finished_at=100.5,
                                    evidence={"STRIPE_SECRET_KEY": "sk_test_longval"}),
            journey_mod.JourneyStep(name="b", description="d", status="skipped",
                                    started_at=0, finished_at=0),
        ]
        ledger = evidence.ledger_from_journey(steps, run_id="test", commit_hash="abc")
        self.assertEqual(len(ledger.records), 2)
        self.assertEqual(ledger.records[0].step_name, "a")
        # Evidence should be redacted
        self.assertIn("***", ledger.records[0].detail.get("STRIPE_SECRET_KEY", ""))
        self.assertEqual(ledger.commit_hash, "abc")

    def test_empty_journey(self):
        ledger = evidence.ledger_from_journey([], run_id="empty", commit_hash="x")
        self.assertEqual(len(ledger.records), 0)


class TestEvidenceDBStorage(unittest.TestCase):
    """Tests for evidence DB store/retrieve functions."""

    @classmethod
    def setUpClass(cls):
        cls.control = load_module("arclink_control.py", "control_ev_db_test")

    def _db(self):
        import sqlite3
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        self.control.ensure_schema(conn)
        return conn

    def _sample_ledger(self, *, run_id="run_abc", status="passed"):
        records = [
            evidence.EvidenceRecord(step_name="step1", status=status, timestamp=100.0),
            evidence.EvidenceRecord(step_name="step2", status=status, timestamp=101.0),
        ]
        ledger = evidence.EvidenceLedger(
            run_id=run_id, started_at=100.0, finished_at=101.0, commit_hash="abc123",
        )
        for r in records:
            ledger.add(r)
        return ledger

    def test_store_and_retrieve(self):
        conn = self._db()
        ledger = self._sample_ledger()
        stored = evidence.store_evidence_run(conn, ledger=ledger, deployment_id="dep_1")
        self.assertEqual(stored["run_id"], "run_abc")
        self.assertEqual(stored["deployment_id"], "dep_1")
        self.assertEqual(stored["status"], "passed")

        retrieved = evidence.get_evidence_run(conn, run_id="run_abc")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["status"], "passed")

    def test_status_derivation_failed(self):
        conn = self._db()
        ledger = self._sample_ledger(run_id="run_fail", status="failed")
        stored = evidence.store_evidence_run(conn, ledger=ledger)
        self.assertEqual(stored["status"], "failed")

    def test_status_derivation_skipped(self):
        conn = self._db()
        ledger = self._sample_ledger(run_id="run_skip", status="skipped")
        stored = evidence.store_evidence_run(conn, ledger=ledger)
        self.assertEqual(stored["status"], "skipped")

    def test_status_derivation_pending(self):
        conn = self._db()
        ledger = evidence.EvidenceLedger(run_id="run_empty", commit_hash="x")
        stored = evidence.store_evidence_run(conn, ledger=ledger)
        self.assertEqual(stored["status"], "pending")

    def test_list_evidence_runs(self):
        conn = self._db()
        for i in range(3):
            ledger = self._sample_ledger(run_id=f"run_{i}")
            evidence.store_evidence_run(conn, ledger=ledger, deployment_id="dep_1")
        runs = evidence.list_evidence_runs(conn, deployment_id="dep_1")
        self.assertEqual(len(runs), 3)

    def test_latest_evidence_status_no_runs(self):
        conn = self._db()
        result = evidence.latest_evidence_status(conn)
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["note"], "no evidence runs recorded")

    def test_latest_evidence_status_with_runs(self):
        conn = self._db()
        ledger = self._sample_ledger()
        evidence.store_evidence_run(conn, ledger=ledger, deployment_id="dep_1")
        result = evidence.latest_evidence_status(conn, deployment_id="dep_1")
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["run_id"], "run_abc")

    def test_get_nonexistent_returns_none(self):
        conn = self._db()
        self.assertIsNone(evidence.get_evidence_run(conn, run_id="nonexistent"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
