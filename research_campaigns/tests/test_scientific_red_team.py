from __future__ import annotations

import unittest

from research_campaigns.scientific_red_team import (
    CODES, FAMILIES, create_tournament, evaluation_sample, gold_view, score, worker_view,
)


class ScientificRedTeamTests(unittest.TestCase):
    def test_tournament_size(self):
        cases = create_tournament()
        self.assertEqual(len(cases), 60)
        self.assertEqual(sum(c["gold"]["family"] is None for c in cases), 12)
        self.assertEqual(sum(c["gold"]["family"] is not None for c in cases), 48)

    def test_four_severity_levels_per_family(self):
        cases = create_tournament()
        for family in FAMILIES:
            levels = sorted(c["gold"]["severity"] for c in cases if c["gold"]["family"] == family.family)
            self.assertEqual(levels, [1, 2, 3, 4])

    def test_worker_view_is_blind(self):
        public = repr(worker_view(create_tournament()))
        self.assertNotIn("'gold'", public)
        for family in FAMILIES:
            self.assertNotIn(family.family, public)
            self.assertNotIn(family.expected_code, public)

    def test_expected_codes_are_registered(self):
        self.assertEqual({f.expected_code for f in FAMILIES}, CODES)

    def test_sample_is_hard_stratified(self):
        cases = create_tournament()
        sample = evaluation_sample(cases)
        self.assertEqual(len(sample), 28)
        self.assertEqual(sum(c["gold"]["family"] is None for c in sample), 4)
        for family in FAMILIES:
            levels = sorted(c["gold"]["severity"] for c in sample if c["gold"]["family"] == family.family)
            self.assertEqual(levels, [3, 4])

    def test_perfect_oracle_scores_one(self):
        cases = create_tournament()
        detections = {
            c["case_id"]: ([] if c["gold"]["expected_code"] is None else [c["gold"]["expected_code"]])
            for c in cases
        }
        result = score(cases, detections)
        self.assertEqual(result["mutation_recall"], 1.0)
        self.assertEqual(result["consequential_recall"], 1.0)
        self.assertEqual(result["clean_false_positive_rate"], 0.0)

    def test_empty_detector_scores_zero_recall_and_zero_false_positives(self):
        cases = create_tournament()
        result = score(cases, {})
        self.assertEqual(result["mutation_recall"], 0.0)
        self.assertEqual(result["consequential_recall"], 0.0)
        self.assertEqual(result["clean_false_positive_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
