"""Audit regressions, numerical boundaries and process/recovery controls."""
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
from research_campaigns.agents import StudyProducer, analyse
from research_campaigns.arithmetic_mutations import RecordingProvider, run_controls
from research_campaigns.bootloops import exact_route, sd_agrees, seal, verify
from research_campaigns.core import ContractError, Denied, Ledger, digest
from research_campaigns.demo import fixtures
from research_campaigns.providers import BaselineProvider, Budget, Session


class ArithmeticAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / "state.sqlite"
        self.ledger = Ledger(self.path)
        self.provider = RecordingProvider()
        self.session = Session(self.ledger, self.provider, Budget())
        self.data = fixtures()

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def study(self):
        return StudyProducer(self.ledger, self.session, verify_arithmetic=True).run(
            self.data["brief"], self.data["sources"], synthetic=True)

    def check_rows(self, rows, method="describe", changes=None, **tolerances):
        plan = {"method": method, "source_key": "fixture", "column": "y", "x": "x", "y": "y"}
        payload = {"rows": rows}
        source = {"payload": payload, "sha256": digest(payload), "kind": "synthetic",
                  "available_at": "2026-01-01T00:00:00Z", "captured_at": "2026-01-01T00:00:00Z"}
        candidate = analyse(plan, source)["result"]
        candidate.update(changes or {})
        ident = "probe-" + digest([rows, method, changes, tolerances])[:16]
        seal(self.ledger, ident, plan, source, candidate, role="study_producer",
             cutoff="2026-02-01T00:00:00Z", **tolerances)
        return verify(self.ledger, ident)

    def assert_blocked(self, result):
        self.assertEqual(result["status"], "abstained")
        self.assertNotIn("manuscript_markdown", result)
        self.assertEqual(self.provider.tasks, ["study_plan"])
        self.assertFalse(self.ledger.items("study_drafts"))
        self.assertEqual(result, self.ledger.get("study_results", self.data["brief"]["study_id"]))
        self.assertEqual(self.ledger.verify()["integrity"], "passed")

    def test_field_mutations_that_replay_are_detected(self):
        report = run_controls()
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["detected"], 16)
        self.assertEqual(report["total"], 16)

    def test_verifier_exception_is_terminal_abstention(self):
        with patch("research_campaigns.bootloops.verify", side_effect=RuntimeError("unavailable")):
            result = self.study()
        self.assert_blocked(result)
        self.assertEqual(result["arithmetic_verification"]["status"], "verification_error")
        self.assertEqual(result["arithmetic_verification"]["error_type"], "RuntimeError")
        with patch("research_campaigns.bootloops.verify") as checker:
            self.assertEqual(result, self.study())
            checker.assert_not_called()

    def test_timeout_is_distinct_and_blocks_drafting(self):
        with patch("research_campaigns.bootloops.verify", side_effect=TimeoutError("deadline")):
            result = self.study()
        self.assert_blocked(result)
        self.assertEqual(result["arithmetic_verification"]["status"], "verification_timeout")

    def test_malformed_verifier_report_blocks_drafting(self):
        with patch("research_campaigns.bootloops.verify", return_value={"status": "numerically_checked"}):
            result = self.study()
        self.assert_blocked(result)
        self.assertEqual(result["arithmetic_verification"]["status"], "verification_error")

    def test_non_finite_analysis_is_recorded_without_non_finite_payload(self):
        original = agents.analyse
        def corrupt(plan, source):
            output = original(plan, source)
            output["result"]["mean"] = float("inf")
            return output
        with patch("research_campaigns.agents.analyse", side_effect=corrupt):
            result = self.study()
        self.assert_blocked(result)
        json.dumps(result, allow_nan=False)
        self.assertNotIn("analysis", result)

    def test_missing_checked_field_blocks_drafting(self):
        original = agents.analyse
        def corrupt(plan, source):
            output = original(plan, source)
            del output["result"]["sample_sd"]
            return output
        with patch("research_campaigns.agents.analyse", side_effect=corrupt):
            self.assert_blocked(self.study())

    def test_verification_scope_reaches_writer_critic_and_manuscript(self):
        contexts = {}
        original = self.provider.complete
        def record(task, context):
            contexts[task] = copy.deepcopy(context)
            return original(task, context)
        with patch.object(self.provider, "complete", side_effect=record):
            result = self.study()
        for task in ("study_write", "study_critic"):
            self.assertEqual(contexts[task]["arithmetic_verification"], result["arithmetic_verification"])
        self.assertIn("## Arithmetic verification", result["manuscript_markdown"])
        self.assertIn('"sample_sd":true', result["manuscript_markdown"])
        self.assertIn("does not establish measurement validity", result["manuscript_markdown"])

    def test_code_change_cannot_reuse_study_result(self):
        self.study()
        with patch("research_campaigns.agents.code_fingerprint", return_value="changed"):
            with self.assertRaises(Denied):
                self.study()

    def test_code_change_cannot_reuse_sealed_check(self):
        self.study()
        ident = self.ledger.items("bootloops_seals")[0][0]
        with patch("research_campaigns.bootloops.code_fingerprint", return_value="changed"):
            with self.assertRaises(Denied):
                verify(self.ledger, ident)

    def test_changed_source_cannot_reuse_cached_study(self):
        self.study()
        source = self.data["sources"][0]
        source["payload"]["rows"][0]["payment_days"] += 1
        source["sha256"] = digest(source["payload"])
        with self.assertRaises(Denied):
            self.study()

    def test_changed_synthetic_policy_cannot_reuse_cached_study(self):
        self.study()
        with self.assertRaises(Denied):
            StudyProducer(self.ledger, self.session, verify_arithmetic=True).run(
                self.data["brief"], self.data["sources"], synthetic=False)

    def test_recovery_after_seal_and_after_verification(self):
        for point in ("seal", "verified"):
            with self.subTest(point=point), tempfile.TemporaryDirectory() as tmp:
                ledger = Ledger(Path(tmp)/"state.sqlite")
                provider = RecordingProvider()
                session = Session(ledger, provider, Budget())
                from research_campaigns import bootloops
                original = bootloops.verify
                def interrupt(*args, **kwargs):
                    if point == "verified":
                        original(*args, **kwargs)
                    raise KeyboardInterrupt()
                with patch("research_campaigns.bootloops.verify", side_effect=interrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        StudyProducer(ledger, session, verify_arithmetic=True).run(
                            self.data["brief"], self.data["sources"], synthetic=True)
                self.assertIsNone(ledger.get("study_results", self.data["brief"]["study_id"]))
                self.assertEqual(provider.tasks, ["study_plan"])
                ledger.close()
                ledger = Ledger(Path(tmp)/"state.sqlite")
                session = Session(ledger, provider, Budget())
                result = StudyProducer(ledger, session, verify_arithmetic=True).run(
                    self.data["brief"], self.data["sources"], synthetic=True)
                self.assertEqual(result["arithmetic_verification"]["status"], "numerically_checked")
                self.assertEqual(provider.tasks.count("study_plan"), 1)
                self.assertEqual(provider.tasks.count("study_write"), 1)
                self.assertEqual(len(ledger.items("bootloops_checks")), 1)
                self.assertEqual(ledger.verify()["integrity"], "passed")
                ledger.close()

    def test_recovery_immediately_before_drafting(self):
        original = self.session.ask
        def interrupt(task, context):
            if task == "study_write":
                raise KeyboardInterrupt()
            return original(task, context)
        with patch.object(self.session, "ask", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.study()
        result = self.study()
        self.assertEqual(result["arithmetic_verification"]["status"], "numerically_checked")
        self.assertEqual(self.provider.tasks, ["study_plan", "study_write", "study_critic"])

    def test_fresh_process_resume_and_two_workspace_reproducibility(self):
        brief = self.root/"brief.json"
        sources = self.root/"sources.json"
        brief.write_text(json.dumps(self.data["brief"]))
        sources.write_text(json.dumps(self.data["sources"]))
        def run(workspace):
            completed = subprocess.run([sys.executable, "-m", "research_campaigns", "study",
                "--brief", str(brief), "--sources", str(sources), "--workspace", str(workspace),
                "--synthetic", "--verify-arithmetic"], capture_output=True, text=True, timeout=20)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            return json.loads(completed.stdout)
        first = run(self.root/"first")
        self.assertEqual(first, run(self.root/"first"))
        second = run(self.root/"second")
        self.assertEqual(first["analysis"], second["analysis"])
        self.assertEqual(first["arithmetic_verification"], second["arithmetic_verification"])
        self.assertEqual(first["manuscript_markdown"], second["manuscript_markdown"])

    def test_single_row_and_zero_variance(self):
        for rows in ([{"y": 2}], [{"y": 2}, {"y": 2}]):
            self.assertEqual(self.check_rows(rows)["status"], "numerically_checked")

    def test_sd_exact_tolerance_boundary_and_negative_value(self):
        variance = Fraction(4)
        self.assertTrue(sd_agrees(2.25, variance, Fraction(0), Fraction(1,4)))
        self.assertFalse(sd_agrees(2.25000000001, variance, Fraction(0), Fraction(1,4)))
        self.assertFalse(sd_agrees(-2, variance, Fraction(0), Fraction(1,4)))
        self.assertTrue(sd_agrees(1e-300, Fraction(1,10**600), Fraction(0), Fraction(0)))

    def test_mean_exact_tolerance_boundary(self):
        rows = [{"y": 1}]
        for value, status in ((1.000001, "numerically_checked"), (1.00000100001, "failed")):
            result = self.check_rows(rows, changes={"mean": value}, relative_tolerance=0, absolute_tolerance=1e-6)
            self.assertEqual(result["status"], status)

    def test_cancellation_preserves_declared_integer_and_detects_float_rounding(self):
        rows = [{"y": 2**53+1}, {"y": -(2**53)}]
        self.assertEqual(exact_route({"method": "describe", "column": "y"}, {"payload": {"rows": rows}})["mean"], Fraction(1,2))
        self.assertEqual(self.check_rows(rows)["status"], "failed")

    def test_large_sd_has_no_square_overflow_in_comparator(self):
        result = self.check_rows([{"y": 1e308}, {"y": -1e308}, {"y": 1e308}])
        self.assertEqual(result["status"], "numerically_checked")
        self.assertTrue(result["checks"]["sample_sd"])

    def test_subnormal_and_mixed_missing_rows(self):
        result = self.check_rows([{"y": 5e-324}, {"y": None}, {}, {"y": 5e-324}])
        self.assertEqual(result["status"], "numerically_checked")
        self.assertEqual(result["exact_values"]["missing_rows"], "2")

    def test_large_offset_and_constant_outcome_ols(self):
        for rows in ([{"x": 1e12+i, "y": 2*i+1} for i in range(3)],
                     [{"x": i, "y": 2} for i in range(3)]):
            self.assertEqual(self.check_rows(rows, "ols")["status"], "numerically_checked")

    def test_constant_and_nearly_constant_predictors(self):
        with self.assertRaises(ContractError):
            exact_route({"method": "ols", "x": "x", "y": "y"},
                        {"payload": {"rows": [{"x": 1, "y": i} for i in range(3)]}})
        rows = [{"x": 1+i*1e-12, "y": i} for i in range(3)]
        result = self.check_rows(rows, "ols")
        self.assertEqual(result["status"], "failed")  # Decimal-input and binary-float routes disagree.

    def test_bad_types_and_unknown_methods_refuse(self):
        for rows in ([False], [{"y": True}], [{"y": float("inf")}], [{"y": "1"}], [{"y": 10**1000}]):
            with self.assertRaises(ContractError):
                exact_route({"method": "describe", "column": "y"}, {"payload": {"rows": rows}})
        with self.assertRaises(Denied):
            exact_route({"method": "simulation"}, {"payload": {"rows": [{"y": 1}]}})

    def test_ols_overflow_records_abstention(self):
        self.data["brief"].update(allowed_methods=["ols"], exposure_column="buffer_days")
        source = self.data["sources"][0]
        source["payload"]["rows"] = [{"buffer_days": -1e308, "payment_days": 1},
                                       {"buffer_days": 0, "payment_days": 2},
                                       {"buffer_days": 1e308, "payment_days": 3}]
        source["sha256"] = digest(source["payload"])
        result = self.study()
        self.assert_blocked(result)
        self.assertEqual(result["arithmetic_verification"]["failure_phase"], "analysis")

    def test_count_types_and_altered_identification_fail(self):
        for count in (3.0, True, 3.0000000001):
            result = self.check_rows([{"y": 1}, {"y": 2}, {"y": 3}], changes={"n": count})
            self.assertEqual(result["status"], "failed")
        result = self.check_rows([{"x": i, "y": 2*i+1} for i in range(3)], "ols",
                                 changes={"identification": "causal"})
        self.assertEqual(result["status"], "failed")
        self.assertIn("identification", result["unsupported_fields"])

    def test_deadline_and_invalid_timeout_refuse(self):
        with patch("research_campaigns.bootloops.monotonic", return_value=2):
            with self.assertRaises(TimeoutError):
                exact_route({"method": "describe", "column": "y"},
                            {"payload": {"rows": [{"y": 1}]}}, deadline=1)
        self.study()
        ident = self.ledger.items("bootloops_seals")[0][0]
        for timeout in (0, -1, True, float("inf"), 61):
            with self.assertRaises(ContractError):
                verify(self.ledger, ident, timeout_seconds=timeout)


if __name__ == "__main__":
    unittest.main()
