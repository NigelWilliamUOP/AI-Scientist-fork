from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_campaigns.challenge_demo import synthetic_packet
from research_campaigns.challenge_harness import (
    DEFAULT_MUTATIONS, ChallengeConfig, DeterministicChallengeWorker,
    SessionChallengeWorker, apply_mutation, baseline_mutation_detector,
    evaluate_mutations, generate_mutation_suite, mechanical_scan,
    mutation_gold, mutation_worker_view, run_challenge,
)
from research_campaigns.core import Denied, Ledger
from research_campaigns.providers import TASKS


class RepairWorker(DeterministicChallengeWorker):
    def complete(self, role, context):
        if role in {"methods_verifier", "statistics_verifier", "evidence_verifier", "reproducibility_verifier", "publication_verifier", "comparative_reviewer"}:
            answer = {"verdict": "repair", "first_failing_step": "scope",
                      "confirmed_steps": [], "findings": ["scope needs repair"], "codes": []}
            if role == "publication_verifier":
                answer["criteria"] = {"contribution": .5, "novelty_positioning": .5,
                                      "discriminating_test": .5, "scope_precision": .5,
                                      "robustness": .5}
            if role == "evidence_verifier":
                answer["support_strength"] = "moderate"
            return answer
        return super().complete(role, context)


class BadOutcomeRepairWorker(RepairWorker):
    def complete(self, role, context):
        if role == "proposition_repair":
            prop = dict(context["original_proposition"])
            prop["proposition_id"] += "R1"
            prop["outcome"] = "switched outcome"
            return {"proposition": prop}
        return super().complete(role, context)


class FakeSession:
    def __init__(self, name):
        self.provider = type("P", (), {"name": name})()
        self.calls = []
    def ask(self, task, context):
        self.calls.append((task, context["challenge_role"]))
        return {"ok": True}


class ChallengeHarnessTests(unittest.TestCase):
    def test_provider_task_is_registered(self):
        self.assertIn("challenge_role", TASKS)

    def test_clean_mechanical_scan(self):
        self.assertEqual(mechanical_scan(synthetic_packet()), [])

    def test_all_default_mutations_detected_by_baseline(self):
        packet = synthetic_packet()
        for mutation in DEFAULT_MUTATIONS:
            with self.subTest(mutation=mutation.mutation_id):
                mutated = apply_mutation(packet, mutation)
                self.assertIn(mutation.expected_code, baseline_mutation_detector(mutated))

    def test_mutation_suite_has_clean_plus_ten(self):
        cases = generate_mutation_suite(synthetic_packet())
        self.assertEqual(len(cases), 11)
        self.assertEqual(sum(c["gold"]["mutation_id"] is not None for c in cases), 10)

    def test_gold_is_not_in_worker_view(self):
        cases = generate_mutation_suite(synthetic_packet())
        public = repr(mutation_worker_view(cases))
        self.assertNotIn("'gold'", public)
        for mutation in DEFAULT_MUTATIONS:
            self.assertNotIn(mutation.mutation_id, public)
            self.assertNotIn(mutation.family, public)
        self.assertNotIn("mutation_probe", public)
        clean = cases[0]["packet"]["candidate_propositions"][0]
        mutated = cases[1]["packet"]["candidate_propositions"][0]
        self.assertEqual(clean.get("confirmatory_status"), mutated.get("confirmatory_status"))

    def test_gold_has_expected_labels(self):
        gold = mutation_gold(generate_mutation_suite(synthetic_packet()))
        self.assertEqual(gold["schema"], "research-mutation-gold-v1")
        self.assertEqual(sum(bool(c["expected_codes"]) for c in gold["cases"]), 10)

    def test_mutation_evaluation_perfect_baseline_control(self):
        cases = generate_mutation_suite(synthetic_packet())
        public = mutation_worker_view(cases)
        detections = {c["case_id"]: baseline_mutation_detector(c["packet"]) for c in public}
        result = evaluate_mutations(cases, detections)
        self.assertEqual(result["mutation_recall"], 1.0)
        self.assertEqual(result["consequential_mutation_recall"], 1.0)
        self.assertEqual(result["clean_false_positive_rate"], 0.0)

    def test_unknown_detection_case_rejected(self):
        cases = generate_mutation_suite(synthetic_packet())
        with self.assertRaises(Exception):
            evaluate_mutations(cases, {"not-a-case": ["X"]})

    def test_challenge_survives_clean_fixture(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Ledger(Path(td) / "ledger.sqlite")
            try:
                report = run_challenge(synthetic_packet(), DeterministicChallengeWorker(), ledger, run_id="run-1")
                self.assertEqual(report["selected_status"], "survives_current_challenge")
                self.assertEqual(report["confirmatory_status"], "exploratory_existing_data")
                self.assertEqual(report["contrary_evidence_retained"], ["E2"])
                self.assertEqual(ledger.verify()["integrity"], "passed")
            finally:
                ledger.close()

    def test_run_is_idempotent_for_same_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Ledger(Path(td) / "ledger.sqlite")
            try:
                a = run_challenge(synthetic_packet(), DeterministicChallengeWorker(), ledger, run_id="run-1")
                b = run_challenge(synthetic_packet(), DeterministicChallengeWorker(), ledger, run_id="run-1")
                self.assertEqual(a, b)
            finally:
                ledger.close()

    def test_run_id_conflict_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Ledger(Path(td) / "ledger.sqlite")
            try:
                run_challenge(synthetic_packet(), DeterministicChallengeWorker(), ledger, run_id="run-1")
                changed = synthetic_packet()
                changed["question"] += " changed"
                with self.assertRaises(Denied):
                    run_challenge(changed, DeterministicChallengeWorker(), ledger, run_id="run-1")
            finally:
                ledger.close()

    def test_repair_cannot_switch_outcome(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Ledger(Path(td) / "ledger.sqlite")
            try:
                with self.assertRaises(Denied):
                    run_challenge(synthetic_packet(), BadOutcomeRepairWorker(), ledger, run_id="run-1")
            finally:
                ledger.close()

    def test_ledger_is_append_only(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Ledger(Path(td) / "ledger.sqlite")
            try:
                run_challenge(synthetic_packet(), DeterministicChallengeWorker(), ledger, run_id="run-1")
                with self.assertRaises(Exception):
                    ledger.db.execute("DELETE FROM facts")
            finally:
                ledger.close()

    def test_verifier_session_is_separate(self):
        generator, verifier = FakeSession("generator"), FakeSession("verifier")
        worker = SessionChallengeWorker(generator, verifier)
        worker.complete("support_builder", {})
        worker.complete("methods_verifier", {})
        self.assertEqual(generator.calls, [("challenge_role", "support_builder")])
        self.assertEqual(verifier.calls, [("challenge_role", "methods_verifier")])

    def test_search_score_is_not_named_probability(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Ledger(Path(td) / "ledger.sqlite")
            try:
                report = run_challenge(synthetic_packet(), DeterministicChallengeWorker(), ledger, run_id="run-1")
                self.assertIn("search_score", report["ranked_candidates"][0])
                self.assertNotIn("probability", report["ranked_candidates"][0])
            finally:
                ledger.close()

    def test_round_limit_validates(self):
        with self.assertRaises(Exception):
            ChallengeConfig(max_rounds=0).validate()


if __name__ == "__main__":
    unittest.main()
