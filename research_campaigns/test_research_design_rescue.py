import unittest
from research_campaigns.research_design_rescue import ResearchClaim, RescueOption, triage

def claim(value=True):
    return ResearchClaim("C-1", "A causes B", "causal", value, "review-v1", "limits-v1")

def run(failures, options=(), **kw):
    return triage(claim(kw.pop("theory", True)), failures, options,
                  assessment_complete=kw.pop("complete", True),
                  identification_possible=kw.pop("identified", False),
                  simulation_feasible=kw.pop("simulation", True),
                  verified_evidence_ids=kw.pop("evidence", ()),
                  impossibility_proven=kw.pop("impossible", False))

class RescueTests(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(run([])["disposition"], "passes_recorded_checks")

    def test_redirect_unidentifiable_valuable_theory(self):
        result=run(["identification"])
        self.assertEqual(result["disposition"], "redirect_to_conceptual_and_simulation")
        self.assertEqual(result["conceptual_simulation_contract"]["original_empirical_claim_status"],
                         "not_identified_not_validated")

    def test_theoretical_value_not_confirmed_abstains(self):
        self.assertEqual(run(["identification"],theory=None)["disposition"], "insufficient_information")

    def test_no_simulation_does_not_redirect(self):
        self.assertEqual(run(["identification"],simulation=False)["disposition"],"insufficient_information")

    def test_missing_assessment_abstains(self):
        self.assertEqual(run(["identification"],complete=False)["disposition"],"insufficient_information")

    def test_viable_test_is_conditional_only(self):
        opt=RescueOption("r1","measurement","blinded coding",True,True,"Double-code texts",("source-1",))
        result=run(["measurement"],[opt],identified=True)
        self.assertEqual(result["disposition"],"repairable_with_specified_test")
        self.assertFalse(result["all_failed_dimensions_independently_validated_as_repaired"])

    def test_one_rescue_cannot_mask_second_failure(self):
        opt=RescueOption("r1","evidence","new citation",True,True,"Entailment audit",("s",),True)
        result=run(["identification","evidence"],[opt],identified=False,evidence=["s"])
        self.assertIn("identification",result["remaining_failures"])
        self.assertFalse(result["all_failed_dimensions_independently_validated_as_repaired"])

    def test_reframed_design_is_not_original_success(self):
        opt=RescueOption("r1","scope","narrow scope",False,True,"New question reviewed",("s",),True)
        result=run(["scope"],[opt],identified=True,evidence=["s"],simulation=False)
        self.assertEqual(result["disposition"],"requires_reframing_or_new_design")

    def test_unverified_receipt_not_success(self):
        opt=RescueOption("r1","measurement","coder audit",True,True,"Check agreement",("missing",),True)
        result=run(["measurement"],[opt],identified=True,evidence=[])
        self.assertEqual(result["disposition"],"repairable_with_specified_test")
        self.assertFalse(result["all_failed_dimensions_independently_validated_as_repaired"])

    def test_proved_impossibility(self):
        self.assertEqual(run(["evidence"],identified=True,simulation=False,impossible=True)["disposition"],
                         "unresolvable_under_frozen_constraints")

    def test_duplicate_rescue_rejected(self):
        o=RescueOption("r","scope","narrow",False,True,"Review")
        with self.assertRaises(ValueError):
            run(["scope"],[o,o])

    def test_no_unknown_failure_rescue(self):
        o=RescueOption("r","scope","narrow",False,True,"Review")
        with self.assertRaises(ValueError):
            run(["measurement"],[o])

if __name__=="__main__":
    unittest.main()
