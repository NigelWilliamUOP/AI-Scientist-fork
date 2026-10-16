"""Public synthetic software controls. Not a blinded scientific evaluation."""
from dataclasses import FrozenInstanceError, replace
import unittest

from research_campaigns.teamwork_control import (
    Campaign, ClaimContract, contract_changes, dependency_order,
    fingerprint, invalidate_dependants, plan_campaign,
)


def contract():
    return ClaimContract("Does intervention A change outcome Y?", "Fictional organisations",
                         "organisation", "A", "no A", "Y per resolved episode",
                         "12 months", "causal", "constraints-v1", "2026-10-16")


def campaign(**kw):
    run = Campaign(contract(), **kw)
    run.add_candidate("A", "author-A", "Original research design")
    return run


class ContractTests(unittest.TestCase):
    def test_identity_is_structural_only(self):
        self.assertEqual(contract_changes(contract(), contract()), ())
        self.assertEqual(campaign().handoff("A")["semantic_equivalence"], "unverified")

    def test_changed_outcome_requires_reframe(self):
        with self.assertRaisesRegex(ValueError, "outcome"):
            campaign().add_candidate("B", "b", "Repair", contract=replace(contract(), outcome="contacts"))

    def test_changed_population_requires_reframe(self):
        with self.assertRaisesRegex(ValueError, "population"):
            campaign().add_candidate("B", "b", "Repair", contract=replace(contract(), population="selected users"))

    def test_causal_to_conceptual_is_not_repair(self):
        self.assertEqual(contract_changes(contract(), replace(contract(), inference_target="conceptual")),
                         ("inference_target",))

    def test_all_contract_fields_detected(self):
        original = contract()
        for field in original.__dataclass_fields__:
            new_value = "conceptual" if field == "inference_target" else "different"
            self.assertEqual(contract_changes(original, replace(original, **{field: new_value})), (field,))

    def test_blank_contract_rejected(self):
        with self.assertRaises(ValueError):
            replace(contract(), unit=" ")

    def test_invalid_inference_rejected(self):
        with self.assertRaises(ValueError):
            replace(contract(), inference_target="proved by agents")

    def test_contract_is_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            contract().outcome = "another outcome"


class CampaignTests(unittest.TestCase):
    def test_duplicate_candidate_rejected(self):
        with self.assertRaises(ValueError):
            campaign().add_candidate("A", "a", "Changed text")

    def test_unknown_parent_rejected(self):
        with self.assertRaises(ValueError):
            campaign().add_candidate("B", "b", "Repair", parents=("unknown",))

    def test_parent_sequence_not_string(self):
        with self.assertRaises(ValueError):
            campaign().add_candidate("B", "b", "Repair", parents="A")

    def test_duplicate_parent_rejected(self):
        with self.assertRaises(ValueError):
            campaign().add_candidate("B", "b", "Repair", parents=("A", "A"))

    def test_root_budget_enforced(self):
        run = campaign(max_roots=1)
        with self.assertRaises(ValueError):
            run.add_candidate("B", "b", "Independent design")

    def test_depth_budget_enforced(self):
        with self.assertRaises(ValueError):
            campaign(max_rounds=1).add_candidate("B", "b", "Repair", parents=("A",))

    def test_record_budget_enforced(self):
        with self.assertRaises(ValueError):
            campaign(max_records=1).add_candidate("B", "b", "Repair", parents=("A",))

    def test_invalid_budgets_rejected(self):
        for value in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                Campaign(contract(), max_roots=value)

    def test_objection_inherited_by_synthesis(self):
        run = campaign()
        run.object("O1", "A", "Selection bias", "Check assignment mechanism", "critic")
        run.add_candidate("B", "b", "Second design")
        run.add_candidate("S", "s", "Synthesis", parents=("A", "B"))
        self.assertEqual([x["objection_id"] for x in run.handoff("S")["unresolved_objections"]], ["O1"])

    def test_late_objection_propagates(self):
        run = campaign()
        run.add_candidate("S", "s", "Synthesis", parents=("A",))
        before = run.handoff("S")["snapshot_hash"]
        run.object("O1", "A", "Bad measurement", "Audit denominator", "critic")
        self.assertNotEqual(before, run.handoff("S")["snapshot_hash"])
        self.assertEqual(run.diagnostic("S")["next_step"], "resolve_objections_or_stop")

    def test_unrelated_objection_does_not_contaminate(self):
        run = campaign()
        run.add_candidate("B", "b", "Independent design")
        before = run.handoff("A")["snapshot_hash"]
        run.object("O1", "B", "Specific flaw", "Specific test", "critic")
        self.assertEqual(before, run.handoff("A")["snapshot_hash"])

    def test_caller_cannot_delete_objection_by_editing_packet(self):
        run = campaign()
        run.object("O1", "A", "Flaw", "Test", "critic")
        run.handoff("A")["unresolved_objections"].clear()
        self.assertEqual(len(run.handoff("A")["unresolved_objections"]), 1)

    def test_duplicate_objection_rejected(self):
        run = campaign()
        run.object("O1", "A", "Flaw", "Test", "critic")
        with self.assertRaises(ValueError):
            run.object("O1", "A", "Erased", "Nothing", "critic")

    def test_objection_requires_check(self):
        with self.assertRaises(ValueError):
            campaign().object("O1", "A", "Flaw", " ", "critic")

    def test_synthetic_pass_cannot_validate_causal_claim(self):
        run = campaign()
        run.record_review("A", run.handoff("A")["snapshot_hash"], "checker", "pass", "synthetic")
        result = run.diagnostic("A")
        self.assertEqual(result["empirical_validation"], "unverified")
        self.assertFalse(result["paper_release_authorised"])

    def test_claimed_empirical_pass_is_not_authenticated(self):
        run = campaign()
        run.record_review("A", run.handoff("A")["snapshot_hash"], "checker", "pass", "empirical")
        result = run.diagnostic("A")
        self.assertEqual(result["current_asserted_reviews"][0]["authenticity"], "not_verified")
        self.assertFalse(result["paper_release_authorised"])

    def test_review_pass_cannot_clear_objection(self):
        run = campaign()
        run.object("O1", "A", "Flaw", "Test", "critic")
        run.record_review("A", run.handoff("A")["snapshot_hash"], "checker", "pass", "empirical")
        self.assertEqual(run.diagnostic("A")["next_step"], "resolve_objections_or_stop")

    def test_stale_review_rejected(self):
        run = campaign()
        old = run.handoff("A")["snapshot_hash"]
        run.object("O1", "A", "Flaw", "Test", "critic")
        with self.assertRaises(ValueError):
            run.record_review("A", old, "checker", "pass", "arithmetic")

    def test_existing_review_becomes_stale(self):
        run = campaign()
        run.record_review("A", run.handoff("A")["snapshot_hash"], "checker", "pass", "arithmetic")
        run.object("O1", "A", "Flaw", "Test", "critic")
        result = run.diagnostic("A")
        self.assertEqual(result["stale_review_count"], 1)
        self.assertEqual(result["current_asserted_reviews"], [])

    def test_self_review_rejected(self):
        run = campaign()
        with self.assertRaises(ValueError):
            run.record_review("A", run.handoff("A")["snapshot_hash"], "author-A", "pass", "arithmetic")

    def test_ancestor_author_cannot_review_synthesis(self):
        run = campaign()
        run.add_candidate("S", "s", "Synthesis", parents=("A",))
        with self.assertRaises(ValueError):
            run.record_review("S", run.handoff("S")["snapshot_hash"], "author-A", "pass", "conceptual")

    def test_contradictory_reviews_do_not_vote_away_failure(self):
        run = campaign()
        digest = run.handoff("A")["snapshot_hash"]
        run.record_review("A", digest, "checker1", "fail", "conceptual",
                          reason="Unresolved identification", required_check="Inspect assignment")
        run.record_review("A", run.handoff("A")["snapshot_hash"], "checker2", "pass", "conceptual")
        self.assertEqual(run.diagnostic("A")["next_step"], "resolve_objections_or_stop")

    def test_no_reviews_is_not_success(self):
        result = campaign().diagnostic("A")
        self.assertEqual(result["next_step"], "external_review_required")
        self.assertFalse(result["paper_release_authorised"])

    def test_campaign_contract_cannot_be_reassigned(self):
        with self.assertRaises(AttributeError):
            campaign().contract = replace(contract(), outcome="different")

    def test_campaign_limits_cannot_be_reassigned(self):
        with self.assertRaises(AttributeError):
            campaign().max_roots = 100

    def test_failed_review_inherited_by_future_synthesis(self):
        run = campaign()
        run.record_review("A", run.handoff("A")["snapshot_hash"], "checker", "fail", "conceptual",
                          reason="Alternative explanation", required_check="Discriminate mechanisms")
        run.add_candidate("S", "s", "Synthesis", parents=("A",))
        result = run.diagnostic("S")
        self.assertEqual(result["next_step"], "resolve_objections_or_stop")
        self.assertEqual(result["unresolved_objections"][0]["reason"], "Alternative explanation")

    def test_unknown_review_retains_missing_evidence(self):
        run = campaign()
        run.record_review("A", run.handoff("A")["snapshot_hash"], "checker", "unknown", "empirical",
                          reason="Source unavailable", required_check="Retrieve source")
        self.assertEqual(len(run.diagnostic("A")["unresolved_objections"]), 1)

    def test_failed_review_requires_reason(self):
        run = campaign()
        with self.assertRaises(ValueError):
            run.record_review("A", run.handoff("A")["snapshot_hash"], "checker", "fail", "conceptual")


class DependencyTests(unittest.TestCase):
    def test_topological_order(self):
        self.assertEqual(dependency_order({"result": ["source"], "source": []}), ("source", "result"))

    def test_cycle_rejected(self):
        with self.assertRaises(ValueError):
            dependency_order({"a": ["b"], "b": ["a"]})

    def test_missing_dependency_rejected(self):
        with self.assertRaises(ValueError):
            dependency_order({"a": ["b"]})

    def test_duplicate_dependency_rejected(self):
        with self.assertRaises(ValueError):
            dependency_order({"a": [], "b": ["a", "a"]})

    def test_selective_withdrawal_invalidation(self):
        graph = {"source": [], "other": [], "parameter": ["source"],
                 "result": ["parameter"], "claim": ["result"], "unrelated_claim": ["other"]}
        self.assertEqual(set(invalidate_dependants(graph, ["source"])),
                         {"source", "parameter", "result", "claim"})

    def test_unknown_withdrawal_rejected(self):
        with self.assertRaises(ValueError):
            invalidate_dependants({"a": []}, ["missing"])


class PlanTests(unittest.TestCase):
    def test_review_only_gate_blocks_simulation(self):
        with self.assertRaises(ValueError):
            plan_campaign("simulation_verification", phase="review")

    def test_review_only_gate_blocks_theory_tournament(self):
        with self.assertRaises(ValueError):
            plan_campaign("theory_tournament", phase="review")

    def test_document_review_allowed_without_execution(self):
        plan = plan_campaign("document_review", phase="review")
        self.assertEqual(plan["model_calls_executed"], 0)
        self.assertEqual(plan["runtime_dispatch"], "not_implemented")

    def test_all_five_patterns_load(self):
        for pattern, phase in (("document_review", "review"), ("theory_tournament", "design"),
                               ("design_rescue", "design"), ("simulation_verification", "simulation"),
                               ("programme_tracking", "tracking")):
            self.assertFalse(plan_campaign(pattern, phase=phase)["paper_release_authorised"])

    def test_plan_budget_cannot_expand_unbounded(self):
        with self.assertRaises(ValueError):
            plan_campaign("document_review", phase="review", candidates=4)

    def test_unknown_pattern_rejected(self):
        with self.assertRaises(ValueError):
            plan_campaign("invented", phase="review")

    def test_hash_rejects_nonfinite_values(self):
        with self.assertRaises(ValueError):
            fingerprint({"value": float("nan")})


if __name__ == "__main__":
    unittest.main()
