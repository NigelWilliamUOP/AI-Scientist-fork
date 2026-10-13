"""Deterministic, evidence-bound counterfactual peer review (no LLM calls).

The simulator reports failure mechanisms and conditional repairs. It does not
predict editorial decisions, establish scientific truth, or modify frozen gates.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
import json
from typing import Mapping, Sequence


FAILURES = {
    "novelty": "Contribution already established or not distinguished from prior work",
    "mechanism": "Causal mechanism or theoretical distinction insufficiently specified",
    "identification": "Empirical design does not identify the claimed effect",
    "measurement": "Construct or operationalisation lacks validity",
    "falsifiability": "No discriminating observation or plausible refutation",
    "evidence": "Central claims lack traceable supporting sources",
    "replication": "Results cannot be independently reproduced",
    "scope": "Claims exceed the sampled population or observed setting",
    "ethics": "Ethical or data governance requirements unresolved",
}
CRITICAL = frozenset({"identification", "evidence", "ethics", "replication"})


@dataclass(frozen=True)
class Finding:
    criterion: str
    passed: bool
    evidence_ids: tuple[str, ...] = ()
    explanation: str = ""
    reviewer_id: str = ""

    def __post_init__(self) -> None:
        if self.criterion not in FAILURES:
            raise ValueError(f"Unknown criterion: {self.criterion}")
        if self.passed and not self.evidence_ids:
            raise ValueError("Passing findings require traceable evidence IDs")


@dataclass(frozen=True)
class Repair:
    repair_id: str
    criterion: str
    description: str
    evidence_ids: tuple[str, ...]
    validation_test: str
    proposed_pass: bool = True

    def __post_init__(self) -> None:
        if self.criterion not in FAILURES:
            raise ValueError(f"Unknown criterion: {self.criterion}")
        if not self.validation_test.strip():
            raise ValueError("Repair needs a separately testable validation test")


def assess(findings: Sequence[Finding], *, frozen_version: str) -> dict:
    """Summarise failures without treating a model's rating as acceptance probability."""
    if not frozen_version.strip():
        raise ValueError("A frozen rubric version is mandatory")
    if len({f.criterion for f in findings}) != len(findings):
        raise ValueError("Duplicate criterion in assessment")
    by_criterion = {f.criterion: f for f in findings}
    missing = sorted(set(FAILURES) - set(by_criterion))
    failures = [key for key in FAILURES if key in by_criterion and not by_criterion[key].passed]
    result = {
        "rubric_version": frozen_version,
        "status": "unverified" if missing else ("blocked" if failures else "passes_recorded_checks"),
        "missing_criteria": missing,
        "failed_criteria": failures,
        "critical_failures": [key for key in failures if key in CRITICAL],
        "failure_mechanisms": {key: FAILURES[key] for key in failures},
        "caveat": "Diagnostic assessment only: not a peer-review or editorial acceptance forecast",
    }
    result["assessment_sha256"] = sha256(json.dumps(
        {"findings": [asdict(x) for x in findings], "rubric_version": frozen_version},
        sort_keys=True,
    ).encode()).hexdigest()
    return result


def simulate(
    baseline: Sequence[Finding],
    repairs: Sequence[Repair],
    *,
    frozen_version: str,
    verified_evidence_ids: Sequence[str],
) -> dict:
    """Produce counterfactuals, never silently turning proposed remedies into facts.

    The candidate is conditionally evaluated *if* its validation test succeeds
    and all its new evidence is independently verified. A changed finding does
    not become an observed pass until a fresh assessment is supplied.
    """
    base = assess(baseline, frozen_version=frozen_version)
    current = {f.criterion: f for f in baseline}
    allow = set(verified_evidence_ids)
    simulations = []
    for r in repairs:
        before = current.get(r.criterion)
        reasons = []
        if before is None:
            reasons.append("criterion_missing_from_baseline")
        elif before.passed:
            reasons.append("baseline_already_passes")
        if not r.evidence_ids:
            reasons.append("repair_has_no_evidence")
        if not set(r.evidence_ids).issubset(allow):
            reasons.append("evidence_not_independently_verified")
        admissible = not reasons
        if admissible:
            hypothetical = dict(current)
            hypothetical[r.criterion] = Finding(
                r.criterion, r.proposed_pass, r.evidence_ids,
                f"CONDITIONAL ONLY: {r.validation_test}", "counterfactual",
            )
            after = assess(list(hypothetical.values()), frozen_version=frozen_version)
        else:
            after = None
        simulations.append({
            "repair_id": r.repair_id,
            "target_failure": r.criterion,
            "proposed_change": r.description,
            "validation_test": r.validation_test,
            "admissible_for_scenario": admissible,
            "exclusions": reasons,
            "conditional_assessment": after,
            "observed_result": "not_tested",
        })
    return {
        "baseline": base,
        "counterfactuals": simulations,
        "quality_objective": "maximise independently defensible research quality; no cost/volume proxy",
        "rubric_lock": frozen_version,
        "guardrail": "A scenario is a hypothesis about a repair, not verified evidence or editorial prediction.",
    }
