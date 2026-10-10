from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from research_campaigns.core import ContractError, Denied, Ledger, digest
from research_campaigns.ideation import (
    CONTRIBUTIONS, IdeationConfig, IdeationGuard, masked_papers, registry,
    run_ideation_challenge, validate_review, validate_supports,
)
from research_campaigns.ideation_demo import (
    SyntheticIdeationWorker, SyntheticSearcher, receipt, synthetic_inputs,
)


class ObservedWorker(SyntheticIdeationWorker):
    def __init__(self):
        self.calls = []
    def complete(self, role, context):
        self.calls.append((role, copy.deepcopy(context)))
        return super().complete(role, context)


class ChangedVerdictWorker(ObservedWorker):
    verdict = "reject"
    def complete(self, role, context):
        result = super().complete(role, context)
        if role == "ideation_reviewer":
            result["verdict"] = self.verdict
            result["focus"] = "mapping" if self.verdict == "revise" else None
        return result


class RevisedWorker(ChangedVerdictWorker):
    verdict = "revise"
    def complete(self, role, context):
        result = super().complete(role, context)
        if role == "ideation_reviewer" and context["candidate"]["proposition_id"].endswith("R1"):
            result["verdict"], result["focus"] = "survive", None
        return result


class ChangedVerdictWorkerWithRevision(ChangedVerdictWorker):
    verdict = "revise"


class TerminalWorker(ObservedWorker):
    outcome = "no_gap"
    def complete(self, role, context):
        if role == "ideation_gap_finder":
            self.calls.append((role, copy.deepcopy(context)))
            return {"outcome": self.outcome, "gap": None, "reason": "No gap within supplied coverage.",
                    "assessed_paper_ids": ["P1", "P2"],
                    "supports": [receipt(context["papers"], "P1"), receipt(context["papers"], "P2")]}
        return super().complete(role, context)


class IdeationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.temp.name) / "ledger.sqlite")
        self.packet, self.spec = synthetic_inputs()
    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()
    def run_pipeline(self, worker=None, searcher=None, config=None):
        return run_ideation_challenge(self.packet, self.spec, worker or SyntheticIdeationWorker(),
                                      self.ledger, run_id="r1", searcher=searcher, config=config)
    def guard(self, worker=None, searcher=None, config=None):
        guard = IdeationGuard(run_id="g1", packet=self.packet, spec=self.spec,
                              worker=worker or SyntheticIdeationWorker(), ledger=self.ledger,
                              searcher=searcher or SyntheticSearcher(), config=config or IdeationConfig())
        guard.prepare()
        return guard

    def test_full_path_uses_existing_harness_and_retains_contrary_evidence(self):
        report = self.run_pipeline(searcher=SyntheticSearcher())
        self.assertEqual(report["status"], "survives_current_challenge")
        challenge = report["challenge_reports"][0]
        self.assertEqual(challenge["contrary_evidence_retained"], ["E2"])
        self.assertEqual(challenge["confirmatory_status"], "exploratory_existing_data")
        self.assertIn("mechanism_builder", challenge["selected_theory_package"])
        self.assertFalse(report["scientific_validity_established"])
        self.assertEqual(self.ledger.verify()["integrity"], "passed")

    def test_baseline_completes_before_innovation_and_is_not_shown_to_innovator(self):
        worker = ObservedWorker()
        self.run_pipeline(worker, SyntheticSearcher())
        roles = [role for role, _ in worker.calls]
        self.assertLess(roles.index("ideation_blind_baseline"), roles.index("ideation_innovator"))
        context = next(c for r, c in worker.calls if r == "ideation_innovator")
        self.assertNotIn("baseline", context)
        self.assertNotIn("More arrivals or repeat contacts", repr(context))
        facts = self.ledger.export()
        baseline = next(r["seq"] for r in facts if r["namespace"] == "ideation:r1" and r["key"] == "baseline")
        innovation = next(r["seq"] for r in facts if r["namespace"] == "ideation:r1:calls" and r["key"] == "candidate-0")
        self.assertLess(baseline, innovation)

    def test_masked_projection_omits_results_and_observation(self):
        worker = ObservedWorker()
        self.run_pipeline(worker, SyntheticSearcher())
        for role, context in worker.calls:
            if role in {"ideation_gap_finder", "ideation_blind_baseline", "ideation_innovator"}:
                self.assertNotIn("RESULT_SEEN_SENTINEL", repr(context))
                self.assertNotIn("observation", context["question"])

    def test_existing_seed_refuses_retrospective_blindness(self):
        self.packet["candidate_propositions"] = [{"proposition_id": "P0", "statement": "known idea", "claim_type": "associational",
            "scope": self.packet["scope"], "outcome": self.packet["outcome"], "falsifier": "fails", "contribution": "test"}]
        with self.assertRaises(Denied):
            self.run_pipeline()

    def test_exposure_attestation_required(self):
        self.spec["prior_candidate_exposure"] = True
        with self.assertRaises(Denied):
            self.run_pipeline()

    def test_worker_exposure_refuses_baseline(self):
        class Exposed(SyntheticIdeationWorker):
            def complete(inner, role, context):
                result = super().complete(role, context)
                if role == "ideation_blind_baseline":
                    result["proposal_exposed"] = True
                return result
        with self.assertRaises(Denied):
            self.run_pipeline(Exposed())

    def test_no_gap_stops_without_candidate(self):
        worker = TerminalWorker()
        result = self.run_pipeline(worker)
        self.assertEqual(result["status"], "no_gap")
        self.assertIsNone(result["baseline"])
        self.assertEqual([r for r, _ in worker.calls], ["ideation_gap_finder"])

    def test_blocked_is_distinct_from_no_gap(self):
        worker = TerminalWorker()
        worker.outcome = "blocked"
        self.assertEqual(self.run_pipeline(worker)["status"], "blocked")

    def test_no_gap_requires_read_coverage(self):
        class Uncovered(TerminalWorker):
            def complete(inner, role, context):
                result = super().complete(role, context)
                result["supports"] = []
                return result
        with self.assertRaises(ContractError):
            self.run_pipeline(Uncovered())

    def test_missing_search_is_unverified_and_skips_downstream_theory(self):
        worker = ObservedWorker()
        result = self.run_pipeline(worker)
        self.assertEqual(result["status"], "unverified")
        self.assertNotIn("mechanism_builder", [r for r, _ in worker.calls])

    def test_reject_does_not_advance_to_full_theory(self):
        worker = ChangedVerdictWorker()
        result = self.run_pipeline(worker, SyntheticSearcher())
        self.assertEqual(result["status"], "no_surviving_candidate")
        self.assertEqual(len(result["challenge_reports"]), 3)
        self.assertNotIn("mechanism_builder", [r for r, _ in worker.calls])

    def test_repaired_candidate_gets_new_review(self):
        worker = RevisedWorker()
        result = self.run_pipeline(worker, SyntheticSearcher())
        reviews = [c["candidate"]["proposition_id"] for r, c in worker.calls if r == "ideation_reviewer"]
        self.assertEqual(reviews, ["I1", "I1R1"])
        self.assertEqual(result["challenge_reports"][0]["selected_proposition_id"], "I1R1")

    def test_unverified_repair_does_not_select_superseded_ancestor(self):
        result = self.run_pipeline(ChangedVerdictWorkerWithRevision(), SyntheticSearcher(),
                                   IdeationConfig(max_search_operations=6))
        report = result["challenge_reports"][0]
        self.assertEqual(result["status"], "unverified")
        self.assertEqual(report["selected_proposition_id"], "I1R1")
        self.assertEqual(report["selected_ideation_review"]["verdict"], "unverified")

    def test_changed_candidate_content_invalidates_review(self):
        g = self.guard()
        candidate = g.innovate(0)
        review = g.review(candidate)
        candidate["statement"] += " changed"
        with self.assertRaises(Denied):
            validate_review(review, candidate, g.papers)

    def test_same_id_cannot_claim_new_candidate_review(self):
        g = self.guard()
        candidate = g.innovate(0)
        g.review(candidate)
        candidate["statement"] += " changed"
        with self.assertRaises(Denied):
            g.review(candidate)

    def test_changed_answer_invalidates_receipt_and_review(self):
        g = self.guard()
        candidate = g.innovate(0)
        review = g.review(candidate)
        changed = copy.deepcopy(g.papers)
        changed["P1"]["answers"][0]["answer"] += " changed"
        with self.assertRaises(Denied):
            validate_supports(candidate["supports"], changed, mechanism=True)
        with self.assertRaises(Denied):
            validate_review(review, candidate, changed)

    def test_changed_gap_or_baseline_cannot_be_reused(self):
        g = self.guard()
        g.baseline["mechanisms"][0]["mechanism"] += " changed"
        with self.assertRaises(Denied):
            g.innovate(0)

    def test_abstract_does_not_support_mechanism(self):
        papers = registry(self.spec["papers"], self.packet["cutoff"])
        support = receipt(list(papers.values()), "P1")
        papers["P1"]["answers"][0]["access_level"] = "abstract"
        with self.assertRaises(Denied):
            validate_supports([support], papers, mechanism=True)

    def test_wrong_exact_version_is_rejected(self):
        papers = registry(self.spec["papers"], self.packet["cutoff"])
        support = receipt(list(papers.values()), "P1")
        support["version"] = "v2"
        with self.assertRaises(Denied):
            validate_supports([support], papers)

    def test_missing_locator_is_rejected(self):
        papers = registry(self.spec["papers"], self.packet["cutoff"])
        support = receipt(list(papers.values()), "P1")
        support["locator"] = ""
        with self.assertRaises(ContractError):
            validate_supports([support], papers)

    def test_post_cutoff_revision_not_just_first_publication_date(self):
        self.spec["papers"][0]["version_at"] = "2026-10-11T00:00:00+00:00"
        with self.assertRaises(Denied):
            self.run_pipeline()

    def test_unknown_exact_version_date_rejected(self):
        self.spec["papers"][0]["version_at"] = None
        with self.assertRaises(ContractError):
            self.run_pipeline()

    def test_result_masking_attestation_required(self):
        self.spec["papers"][0]["masking_attestation"] = "unknown"
        with self.assertRaises(Denied):
            self.run_pipeline()

    def test_missing_transfer_mapping_rejected(self):
        g = self.guard()
        prop = g.innovate(0)
        prop["mechanism_transfer"]["mapping"] = []
        with self.assertRaises(ContractError):
            g.validate_candidate(prop)

    def test_missing_kill_condition_rejected(self):
        g = self.guard()
        prop = g.innovate(0)
        del prop["predictions"][0]["kill_condition"]
        with self.assertRaises(ContractError):
            g.validate_candidate(prop)

    def test_social_science_contributions_are_admitted(self):
        g = self.guard()
        prop = g.innovate(0)
        for contribution in CONTRIBUTIONS:
            prop["contribution_type"] = contribution
            g.validate_candidate(prop)

    def test_single_near_miss_needs_scope_rationale(self):
        class OneSource(SyntheticIdeationWorker):
            def complete(inner, role, context):
                result = super().complete(role, context)
                if role == "ideation_gap_finder":
                    result["gap"]["near_miss_ids"] = ["P1"]
                    result["gap"]["supports"] = result["gap"]["supports"][:1]
                return result
        with self.assertRaises(ContractError):
            self.run_pipeline(OneSource())

    def test_search_must_bind_exact_candidate(self):
        class WrongSearch(SyntheticSearcher):
            def search(inner, request):
                result = super().search(request)
                result["candidate_hash"] = "wrong"
                return result
        with self.assertRaises(Denied):
            self.run_pipeline(searcher=WrongSearch())

    def test_search_must_attempt_disconfirmation(self):
        class FriendlySearch(SyntheticSearcher):
            def search(inner, request):
                result = super().search(request)
                result["queries"][0]["purpose"] = "support_only"
                return result
        with self.assertRaises(Denied):
            self.run_pipeline(searcher=FriendlySearch())

    def test_unavailable_comparison_source_requires_unverified(self):
        class UnavailableSearch(SyntheticSearcher):
            def search(inner, request):
                result = super().search(request)
                paper = copy.deepcopy(self.spec["papers"][0])
                paper.update(paper_id="P4", canonical_id="urn:public-synthetic-method:P4",
                             answers=[], read_status="unavailable", access_level="unavailable")
                result["papers"] = [paper]
                result["queries"][0]["paper_ids"].append("P4")
                return result
        self.assertEqual(self.run_pipeline(searcher=UnavailableSearch())["status"], "unverified")

    def test_search_cannot_replace_existing_answer(self):
        class ChangedSearch(SyntheticSearcher):
            def search(inner, request):
                result = super().search(request)
                paper = copy.deepcopy(self.spec["papers"][0])
                paper["answers"][0]["answer"] += " changed"
                result["papers"] = [paper]
                return result
        with self.assertRaises(Denied):
            self.run_pipeline(searcher=ChangedSearch())

    def test_search_budget_is_reserved_and_not_refunded(self):
        worker = ChangedVerdictWorker()
        cfg = IdeationConfig(max_search_operations=6)
        result = self.run_pipeline(worker, SyntheticSearcher(), cfg)
        self.assertEqual(result["search_operations_reserved"], 6)
        self.assertEqual(result["status"], "unverified")

    def test_role_budget_exhaustion_prevents_innovation(self):
        worker = ObservedWorker()
        with self.assertRaises(Denied):
            self.run_pipeline(worker, SyntheticSearcher(), IdeationConfig(max_role_calls=2))
        self.assertNotIn("ideation_innovator", [r for r, _ in worker.calls])

    def test_interrupted_search_cannot_reset_reservation(self):
        class Interrupted(SyntheticSearcher):
            def search(inner, request):
                raise RuntimeError("interrupted")
        g = self.guard(searcher=Interrupted())
        prop = g.innovate(0)
        with self.assertRaises(RuntimeError):
            g.review(prop)
        with self.assertRaises(Denied):
            g.review(prop)
        self.assertEqual(len(self.ledger.items(g.ns + ":search_reservations")), 1)

    def test_idempotent_completed_run_does_not_call_workers_again(self):
        worker = ObservedWorker()
        one = self.run_pipeline(worker, SyntheticSearcher())
        count = len(worker.calls)
        two = self.run_pipeline(worker, SyntheticSearcher())
        self.assertEqual(one, two)
        self.assertEqual(len(worker.calls), count)

    def test_changed_spec_cannot_reuse_run_id(self):
        self.run_pipeline(searcher=SyntheticSearcher())
        self.spec["discovery_coverage"] += " changed"
        with self.assertRaises(Denied):
            self.run_pipeline(searcher=SyntheticSearcher())

    def test_same_version_cannot_fake_two_papers(self):
        self.spec["papers"][1]["canonical_id"] = self.spec["papers"][0]["canonical_id"]
        with self.assertRaises(Denied):
            self.run_pipeline()

    def test_earliest_version_does_not_make_two_versions_independent_near_misses(self):
        self.spec["papers"][1]["canonical_id"] = self.spec["papers"][0]["canonical_id"]
        self.spec["papers"][1]["version"] = "fixture-v2"
        with self.assertRaises(Denied):
            self.run_pipeline()


if __name__ == "__main__":
    unittest.main()
