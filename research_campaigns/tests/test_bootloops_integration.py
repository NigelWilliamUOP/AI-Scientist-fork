from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

from research_campaigns import agents
from research_campaigns.agents import StudyProducer
from research_campaigns.bootloops import declared_fraction, exact_route
from research_campaigns.core import ContractError, Denied, Ledger
from research_campaigns.demo import fixtures
from research_campaigns.providers import BaselineProvider, Budget, Session


class RecordingProvider(BaselineProvider):
    def __init__(self):
        self.tasks = []
    def complete(self, task, context):
        self.tasks.append(task)
        return super().complete(task, context)


class BootLoopsIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = Ledger(self.root / "state.sqlite")
        self.provider = RecordingProvider()
        self.session = Session(self.ledger, self.provider, Budget())
        self.data = fixtures()
    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()
    def run_study(self, enabled=True):
        return StudyProducer(self.ledger, self.session, verify_arithmetic=enabled).run(
            self.data["brief"], self.data["sources"], synthetic=True)

    def test_descriptive_output_independently_checked(self):
        result = self.run_study()
        report = result["arithmetic_verification"]
        self.assertEqual(report["status"], "numerically_checked")
        self.assertEqual(report["exact_values"]["mean"], "25")
        self.assertIn("sample_sd", report["unchecked_fields"])
        self.assertEqual(result["independent_replication"], "not_run")
        self.assertEqual(report["scientific_validity"], "unverified")
        self.assertFalse(report["upstream_engine_executed"])
        self.assertEqual(self.ledger.verify()["integrity"], "passed")

    def test_ols_output_independently_checked(self):
        self.data["brief"].update(allowed_methods=["ols"], exposure_column="buffer_days", outcome_column="payment_days")
        report = self.run_study()["arithmetic_verification"]
        self.assertEqual(report["status"], "numerically_checked")
        self.assertEqual(report["exact_values"]["slope"], "2")
        self.assertEqual(report["exact_values"]["intercept"], "0")
        self.assertIn("identification", report["unchecked_fields"])

    def test_corrupt_calculation_blocks_manuscript_even_when_same_route_replays(self):
        original = agents.analyse
        def corrupted(plan, source):
            calculation = original(plan, source)
            calculation["result"]["mean"] += 1
            return calculation
        with patch("research_campaigns.agents.analyse", side_effect=corrupted):
            result = self.run_study()
        self.assertEqual(result["status"], "abstained")
        self.assertEqual(result["arithmetic_verification"]["status"], "failed")
        self.assertEqual(result["arithmetic_replay"], "passed_same_implementation")
        self.assertEqual(self.provider.tasks, ["study_plan"])
        self.assertFalse(self.ledger.items("study_drafts"))
        self.assertNotIn("manuscript_markdown", result)

    def test_verification_precedes_manuscript_call(self):
        self.run_study()
        facts = self.ledger.export()
        check = next(r["seq"] for r in facts if r["namespace"] == "bootloops_checks")
        writes = [r["seq"] for r in facts if r["namespace"] == "model_start" and json.loads(r["payload"])["task"] == "study_write"]
        self.assertEqual(len(writes), 1)
        self.assertLess(check, writes[0])

    def test_optional_policy_preserves_plain_study(self):
        result = self.run_study(False)
        self.assertEqual(result["arithmetic_verification"]["status"], "not_requested")
        self.assertFalse(self.ledger.items("bootloops_seals"))

    def test_cannot_change_policy_under_existing_study_id(self):
        self.run_study(False)
        with self.assertRaises(Denied):
            self.run_study(True)

    def test_identical_resume_reuses_check_and_model_outputs(self):
        first = self.run_study()
        before = len(self.ledger.export())
        tasks = list(self.provider.tasks)
        self.assertEqual(first, self.run_study())
        self.assertEqual(len(self.ledger.export()), before)
        self.assertEqual(self.provider.tasks, tasks)

    def test_precise_declared_integer_is_not_rounded_before_exact_route(self):
        value = 2**53 + 1
        self.assertEqual(declared_fraction(value), Fraction(value))
        source = {"payload": {"rows": [{"y": value}, {"y": -2**53}]}}
        self.assertEqual(exact_route({"method": "describe", "column": "y"}, source)["mean"], Fraction(1, 2))

    def test_boolean_is_not_a_numeric_input(self):
        with self.assertRaises(ContractError):
            declared_fraction(True)

    def test_unknown_method_has_no_verification_route(self):
        with self.assertRaises(Denied):
            exact_route({"method": "simulation"}, {"payload": {"rows": [{"x": 1}]}})

    def test_policy_flag_must_be_boolean(self):
        with self.assertRaises(ContractError):
            StudyProducer(self.ledger, self.session, verify_arithmetic="yes")

    def test_cli_verifies_actual_study_output(self):
        brief_path, sources_path = self.root / "brief.json", self.root / "sources.json"
        brief_path.write_text(json.dumps(self.data["brief"]))
        sources_path.write_text(json.dumps(self.data["sources"]))
        result = subprocess.run([sys.executable, "-m", "research_campaigns", "study",
            "--brief", str(brief_path), "--sources", str(sources_path),
            "--workspace", str(self.root / "cli"), "--synthetic", "--verify-arithmetic"],
            capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["arithmetic_verification"]["status"], "numerically_checked")


if __name__ == "__main__":
    unittest.main()
