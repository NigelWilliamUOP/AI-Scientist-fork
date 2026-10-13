"""Research-design rescue: conservative, claim-preserving and abstention-aware.

This module is a deterministic rules engine over *externally assessed* claims.
It neither verifies evidence nor establishes theoretical value or feasibility.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Sequence


class Disposition(str, Enum):
    PASS = "passes_recorded_checks"
    REPAIR = "repairable_with_specified_test"
    REFRAME = "requires_reframing_or_new_design"
    CONCEPTUAL_SIM = "redirect_to_conceptual_and_simulation"
    UNRESOLVABLE = "unresolvable_under_frozen_constraints"
    UNKNOWN = "insufficient_information"


@dataclass(frozen=True)
class ResearchClaim:
    claim_id: str
    central_claim: str
    claim_type: str  # causal, descriptive, mechanism, conceptual
    theoretical_value_confirmed: bool | None
    scientific_review_id: str
    frozen_constraints_id: str

    def __post_init__(self):
        if self.claim_type not in {"causal", "descriptive", "mechanism", "conceptual"}:
            raise ValueError("Unknown claim type")
        if not all((self.claim_id.strip(), self.central_claim.strip(),
                    self.scientific_review_id.strip(), self.frozen_constraints_id.strip())):
            raise ValueError("Claim and assessment/constraint receipts required")


@dataclass(frozen=True)
class RescueOption:
    option_id: str
    target_failure: str
    strategy: str
    preserves_original_claim: bool | None
    feasible_under_constraints: bool | None
    independent_test: str
    evidence_ids: tuple[str, ...] = ()
    validated_success: bool = False

    def __post_init__(self):
        if not self.option_id.strip() or not self.target_failure.strip() or not self.strategy.strip():
            raise ValueError("Complete rescue identity/strategy required")
        if self.validated_success and (not self.independent_test.strip() or not self.evidence_ids):
            raise ValueError("Validated success must have test and evidence receipts")


def triage(
    claim: ResearchClaim,
    failures: Sequence[str],
    options: Sequence[RescueOption],
    *,
    assessment_complete: bool,
    identification_possible: bool | None,
    simulation_feasible: bool | None,
    verified_evidence_ids: Sequence[str],
    impossibility_proven: bool = False,
) -> dict:
    """Evaluate options without converting unvalidated repairs into observed passes."""
    if len(set(failures)) != len(failures):
        raise ValueError("Duplicate failure identifiers")
    if len({o.option_id for o in options}) != len(options):
        raise ValueError("Duplicate rescue identifiers")
    if any(o.target_failure not in failures for o in options):
        raise ValueError("Rescue options must target an observed failure")
    approved = set(verified_evidence_ids)
    evaluations = []
    for opt in options:
        receipt_ok = bool(opt.evidence_ids) and set(opt.evidence_ids).issubset(approved)
        completed = (opt.validated_success and receipt_ok and bool(opt.independent_test.strip()))
        evaluations.append({
            "option_id": opt.option_id, "failure": opt.target_failure,
            "strategy": opt.strategy, "preserves_original_claim": opt.preserves_original_claim,
            "feasible_under_constraints": opt.feasible_under_constraints,
            "validation_protocol": opt.independent_test,
            "evidence_admitted_by_id_only": receipt_ok,
            "validated_success_with_receipts": completed,
            "status": ("validated_claim_preserving_repair" if completed and opt.preserves_original_claim is True
                       and opt.feasible_under_constraints is True else
                       "scenario_only" if not completed else "requires_reframing"),
        })
    covered = {e["failure"] for e in evaluations if e["status"] == "validated_claim_preserving_repair"}
    all_repaired = bool(failures) and set(failures) <= covered
    available = [e for e in evaluations if e["feasible_under_constraints"] is True
                 and e["preserves_original_claim"] is True and bool(e["validation_protocol"])]
    if not assessment_complete:
        status = Disposition.UNKNOWN
    elif not failures:
        status = Disposition.PASS
    elif all_repaired:
        status = Disposition.REPAIR
    elif available:
        status = Disposition.REPAIR
    elif identification_possible is False and claim.theoretical_value_confirmed is True and simulation_feasible is True:
        status = Disposition.CONCEPTUAL_SIM
    elif impossibility_proven:
        status = Disposition.UNRESOLVABLE
    elif any(e["preserves_original_claim"] is False and e["feasible_under_constraints"] is True for e in evaluations):
        status = Disposition.REFRAME
    else:
        status = Disposition.UNKNOWN
    simulation_contract = None
    if status is Disposition.CONCEPTUAL_SIM:
        simulation_contract = {
            "format": "conceptual_paper_plus_simulation",
            "original_empirical_claim_status": "not_identified_not_validated",
            "simulation_role": "illustrate_mechanisms_and_discriminating_predictions",
            "prohibited_inference": "synthetic simulation results do not establish an empirical causal effect",
            "required_sections": [
                "formal_constructs_and_mechanisms", "rival_explanations",
                "explicit_model_assumptions", "parameter_provenance_and_uncertainty",
                "sensitivity_and_boundary_tests", "observable_predictions",
                "future_empirical_identification_plan",
            ],
        }
    return {
        "claim_id": claim.claim_id,
        "scientific_review_id": claim.scientific_review_id,
        "frozen_constraints_id": claim.frozen_constraints_id,
        "disposition": status.value,
        "remaining_failures": sorted(set(failures)-covered),
        "rescue_options": evaluations,
        "all_failed_dimensions_independently_validated_as_repaired": all_repaired,
        "conceptual_simulation_contract": simulation_contract,
        "caveat": "Receipt identifiers and expert assessments are caller-supplied; no external evidence verification performed.",
    }
