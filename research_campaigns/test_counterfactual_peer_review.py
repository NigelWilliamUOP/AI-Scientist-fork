import unittest

from research_campaigns.counterfactual_peer_review import (
    CRITICAL, FAILURES, Finding, Repair, assess, simulate,
)


def complete(*failed):
    return [
        Finding(key, key not in failed, (f"src-{key}",), "Synthetic fixture", "reviewer-a")
        for key in FAILURES
    ]


class CounterfactualPeerReviewTests(unittest.TestCase):
    def test_rejects_unfounded_pass(self):
        with self.assertRaises(ValueError):
            Finding("novelty", True)

    def test_missing_criteria_abstains(self):
        result = assess([Finding("novelty", False)], frozen_version="rubric-v1")
        self.assertEqual(result["status"], "unverified")

    def test_failure_is_not_acceptance_prediction(self):
        result = assess(complete("identification", "mechanism"), frozen_version="v1")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["critical_failures"], ["identification"])
        self.assertNotIn("acceptance_probability", result)

    def test_unverified_repair_never_promoted(self):
        repair = Repair("r1", "identification", "Introduce instrument", ("new-source",),
                        "Test exclusion restriction")
        out = simulate(complete("identification"), [repair],
                       frozen_version="v1", verified_evidence_ids=[])
        cf = out["counterfactuals"][0]
        self.assertFalse(cf["admissible_for_scenario"])
        self.assertIsNone(cf["conditional_assessment"])
        self.assertEqual(out["baseline"]["status"], "blocked")

    def test_verified_repair_remains_conditional(self):
        repair = Repair("r1", "measurement", "Validate coding", ("audit-1",),
                        "Blind dual-coder agreement study")
        out = simulate(complete("measurement"), [repair],
                       frozen_version="v1", verified_evidence_ids=["audit-1"])
        cf = out["counterfactuals"][0]
        self.assertEqual(cf["conditional_assessment"]["status"], "passes_recorded_checks")
        self.assertEqual(cf["observed_result"], "not_tested")
        self.assertEqual(out["baseline"]["status"], "blocked")

    def test_no_rewriting_frozen_rubric(self):
        out = simulate(complete("scope"), [], frozen_version="frozen-2026-10",
                       verified_evidence_ids=[])
        self.assertEqual(out["rubric_lock"], "frozen-2026-10")

    def test_deterministic_digest(self):
        a = assess(complete("scope"), frozen_version="v1")
        b = assess(complete("scope"), frozen_version="v1")
        self.assertEqual(a["assessment_sha256"], b["assessment_sha256"])

    def test_duplicate_findings_rejected(self):
        with self.assertRaises(ValueError):
            assess([Finding("scope", False), Finding("scope", False)], frozen_version="v1")


if __name__ == "__main__":
    unittest.main()
