"""Scientific red-team tournament for theory-building research agents.

Creates blinded theory mutations at graded severity. Gold labels are stored
separately from worker packets. The tournament measures whether a reviewer detects
scientifically consequential defects, not whether it can guess a mutation label.
"""
from __future__ import annotations

import copy
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable

from .core import ContractError, digest

CODES = {
    "CIRCULAR_MECHANISM", "NON_DISCRIMINATING_TEST", "CONSTRUCT_DRIFT",
    "STRAW_RIVAL", "POST_TREATMENT_CONTROL", "COLLIDER_CONTROL",
    "NOVELTY_OVERCLAIM", "BOUNDARY_ERASURE", "MECHANISM_EVIDENCE_CONFLATION",
    "TEMPORAL_REVERSAL", "HIDDEN_AUXILIARY_ASSUMPTION", "LEVEL_MISMATCH",
}


@dataclass(frozen=True)
class TheoryMutation:
    family: str
    expected_code: str


FAMILIES = (
    TheoryMutation("circular_mechanism", "CIRCULAR_MECHANISM"),
    TheoryMutation("non_discriminating_test", "NON_DISCRIMINATING_TEST"),
    TheoryMutation("construct_drift", "CONSTRUCT_DRIFT"),
    TheoryMutation("straw_rival", "STRAW_RIVAL"),
    TheoryMutation("post_treatment_control", "POST_TREATMENT_CONTROL"),
    TheoryMutation("collider_control", "COLLIDER_CONTROL"),
    TheoryMutation("novelty_overclaim", "NOVELTY_OVERCLAIM"),
    TheoryMutation("boundary_erasure", "BOUNDARY_ERASURE"),
    TheoryMutation("mechanism_evidence_conflation", "MECHANISM_EVIDENCE_CONFLATION"),
    TheoryMutation("temporal_reversal", "TEMPORAL_REVERSAL"),
    TheoryMutation("hidden_auxiliary_assumption", "HIDDEN_AUXILIARY_ASSUMPTION"),
    TheoryMutation("level_mismatch", "LEVEL_MISMATCH"),
)


def base_theory_record() -> dict[str, Any]:
    return {
        "research_question": "Does exposure X increase institutional stress through verification workload in the bounded organisation-period sample?",
        "claim_type": "associational_with_proposed_mechanism",
        "scope": {"population": "synthetic organisations", "place": "synthetic UK", "time": "2025-2026"},
        "unit_of_analysis": "organisation-period",
        "constructs": {
            "exposure": {"name": "exposure X", "measure": "validated exposure index", "level": "organisation-period"},
            "mediator": {"name": "verification workload", "measure": "review minutes per case", "level": "organisation-period"},
            "outcome": {"name": "institutional stress", "measure": "validated stress index", "level": "organisation-period"},
        },
        "mechanism": {
            "statement": "Exposure X increases verification workload, which in turn is expected to increase institutional stress.",
            "temporal_order": ["exposure X", "verification workload", "institutional stress"],
            "observed_status": "proposed_not_directly_observed",
        },
        "rivals": [
            {
                "rival_id": "R1",
                "statement": "A common workload shock increases both exposure X and institutional stress.",
                "mechanism": "common cause",
                "focal_difference": "The focal mechanism predicts exposure precedes verification workload; the rival permits workload pressure to precede exposure.",
            },
            {
                "rival_id": "R2",
                "statement": "Institutional stress changes reporting behaviour and therefore measured exposure X.",
                "mechanism": "reverse causation",
                "focal_difference": "The rival predicts stress precedes changes in measured exposure.",
            },
        ],
        "test": {
            "measurement": "monthly exposure, verification workload and stress",
            "focal_prediction": "Exposure changes precede verification-workload changes, followed by stress changes.",
            "rival_id": "R1",
            "rival_prediction": "The common workload measure changes before or at the same time as both exposure and stress.",
            "inconclusive": "Monthly timing is too coarse to establish ordering.",
            "analysis_note": "Do not condition on verification workload when estimating the total exposure-stress association; analyse mediation separately.",
        },
        "novelty": {
            "status": "unverified",
            "statement": "Potential contribution is the bounded verification-workload mechanism and its rival-discriminating temporal test.",
        },
        "boundary_conditions": ["synthetic organisations", "2025-2026", "settings with measurable verification workload"],
        "assumptions": [
            "Exposure and stress measures are comparable across periods.",
            "Monthly measurement is sufficiently granular for the proposed timing test.",
        ],
        "strongest_publishable_formulation": "Within the frozen setting, exposure X is associated with institutional stress; a verification-workload mechanism generates temporal predictions that differ from a common-cause rival.",
    }


def _mutate(record: dict[str, Any], family: str, severity: int) -> dict[str, Any]:
    r = copy.deepcopy(record)
    if severity not in {1, 2, 3, 4}:
        raise ContractError("severity must be 1-4")
    if family == "circular_mechanism":
        texts = {
            1: "Exposure X increases institutional strain, which raises institutional stress.",
            2: "Exposure X increases stress-generating pressure, thereby increasing institutional stress.",
            3: "Exposure X increases institutional stress because it activates a stress pathway represented by the stress index.",
            4: "Exposure X increases institutional stress because organisations under greater stress experience more institutional stress.",
        }
        r["mechanism"]["statement"] = texts[severity]
    elif family == "non_discriminating_test":
        if severity == 1:
            r["test"]["rival_prediction"] = "Exposure changes are positively associated with verification workload and stress."
        elif severity == 2:
            r["test"]["rival_prediction"] = "Exposure changes precede verification-workload changes, followed by stress changes."
        elif severity == 3:
            r["rivals"][0]["focal_difference"] = "Both theories predict the same temporal sequence under observed conditions."
            r["test"]["rival_prediction"] = r["test"]["focal_prediction"]
        else:
            r["test"]["rival_prediction"] = r["test"]["focal_prediction"]
            r["test"]["inconclusive"] = "A result matching both theories will be interpreted as support for the focal mechanism."
    elif family == "construct_drift":
        if severity == 1:
            r["constructs"]["outcome"]["measure"] = "complaint word count, used as a convenient stress proxy"
        elif severity == 2:
            r["constructs"]["mediator"]["measure"] = "number of documents received, treated as verification workload"
        elif severity == 3:
            r["constructs"]["outcome"]["name"] = "institutional stress / objection complexity"
            r["constructs"]["outcome"]["measure"] = "document length"
        else:
            r["constructs"]["outcome"] = {"name": "institutional stress", "measure": "document length", "level": "organisation-period"}
            r["strongest_publishable_formulation"] = r["strongest_publishable_formulation"].replace("institutional stress", "institutional stress measured by document length")
    elif family == "straw_rival":
        rivals = {
            1: "The association is entirely caused by lunar cycles.",
            2: "There is no process linking any organisational condition to either exposure or stress.",
            3: "The only rival is that all recorded values were randomly fabricated.",
            4: "The rival predicts no association under any conceivable condition and has no mechanism.",
        }
        r["rivals"][0]["statement"] = rivals[severity]
        r["rivals"][0]["mechanism"] = "implausible residual alternative"
        r["rivals"][0]["focal_difference"] = "Any observed association favours the focal theory."
    elif family == "post_treatment_control":
        phrases = {
            1: "For robustness, also adjust for verification workload while estimating the exposure-stress association.",
            2: "The preferred total-effect model controls for verification workload to remove workload differences.",
            3: "Verification workload is included as a mandatory covariate in the total-effect model.",
            4: "Evidence for the mechanism requires the exposure coefficient to remain after controlling for the proposed mediator, verification workload.",
        }
        r["test"]["analysis_note"] = phrases[severity]
    elif family == "collider_control":
        r["constructs"]["collider"] = {"name": "escalation to senior review", "caused_by": ["exposure X", "institutional stress"]}
        phrases = {
            1: "A sensitivity model may stratify by escalation to senior review.",
            2: "Control for escalation because it is associated with both exposure and stress.",
            3: "Restrict the analysis to escalated cases to improve comparability.",
            4: "The main analysis conditions on escalation to senior review, which is caused by both exposure and stress.",
        }
        r["test"]["analysis_note"] = phrases[severity]
    elif family == "novelty_overclaim":
        claims = {
            1: ("bounded_search_support", "A targeted search did not locate the same framing, suggesting possible novelty."),
            2: ("established_by_review", "No exact-title match was found, so the mechanism is novel."),
            3: ("established_by_review", "A quick web search returned no identical study; therefore this is the first study to identify the mechanism."),
            4: ("established_by_review", "Absence of an exact keyword match proves no prior theory or empirical test exists."),
        }
        r["novelty"]["status"], r["novelty"]["statement"] = claims[severity]
    elif family == "boundary_erasure":
        forms = {
            1: "The mechanism may apply across comparable UK organisations.",
            2: "Exposure X increases institutional stress across public organisations.",
            3: "Exposure X increases institutional stress across organisations internationally.",
            4: "Exposure X universally increases institutional stress regardless of sector, country or period.",
        }
        r["strongest_publishable_formulation"] = forms[severity]
        if severity >= 3:
            r["boundary_conditions"] = []
    elif family == "mechanism_evidence_conflation":
        statements = {
            1: "The observed association is consistent with the proposed verification-workload mechanism.",
            2: "The observed association supports the verification-workload mechanism.",
            3: "Because exposure and stress are associated, verification workload is the mechanism.",
            4: "The association directly demonstrates that verification workload causally mediates the effect.",
        }
        r["mechanism"]["observed_status"] = statements[severity]
    elif family == "temporal_reversal":
        orders = {
            1: ["exposure X", "institutional stress", "verification workload"],
            2: ["institutional stress", "exposure X", "verification workload"],
            3: ["institutional stress", "verification workload", "exposure X"],
            4: ["institutional stress", "exposure X", "verification workload"],
        }
        r["mechanism"]["temporal_order"] = orders[severity]
        if severity >= 3:
            r["test"]["focal_prediction"] = "Stress changes occur first, followed by exposure and then verification workload."
    elif family == "hidden_auxiliary_assumption":
        assumptions = {
            1: "Monthly measurement is sufficiently granular for the proposed timing test.",
            2: "Observed monthly ordering is assumed to represent process ordering even when events occur within the same month.",
            3: "The timing test assumes reporting dates equal causal-event dates; this is not measured.",
            4: "The theory is treated as identified only if recorded timestamps equal causal timing, measurement error is absent and no unmeasured common causes exist.",
        }
        r["assumptions"] = [r["assumptions"][0]]
        r["test"]["analysis_note"] = assumptions[severity]
    elif family == "level_mismatch":
        if severity == 1:
            r["constructs"]["outcome"]["level"] = "individual staff member"
        elif severity == 2:
            r["constructs"]["exposure"]["level"] = "organisation"
            r["constructs"]["outcome"]["level"] = "individual staff member"
        elif severity == 3:
            r["unit_of_analysis"] = "individual staff member"
            r["constructs"]["exposure"]["level"] = "organisation-period"
        else:
            r["unit_of_analysis"] = "organisation-period"
            r["constructs"]["outcome"]["level"] = "individual staff member"
            r["strongest_publishable_formulation"] = "Organisation-level exposure X explains individual-level stress differences."
    else:
        raise ContractError("unknown theory mutation")
    return r


def create_tournament(*, clean_controls: int = 12,
                      families: Iterable[TheoryMutation] = FAMILIES) -> list[dict[str, Any]]:
    base = base_theory_record()
    cases: list[dict[str, Any]] = []
    for i in range(clean_controls):
        clean = copy.deepcopy(base)
        clean["replicate_note"] = f"clean-control-{i+1}"
        cases.append({
            "case_id": "rt-" + digest(clean)[:16],
            "record": clean,
            "gold": {"family": None, "severity": 0, "expected_code": None, "consequential": False},
        })
    for mutation in families:
        for severity in (1, 2, 3, 4):
            record = _mutate(base, mutation.family, severity)
            cases.append({
                "case_id": "rt-" + digest(record)[:16],
                "record": record,
                "gold": {"family": mutation.family, "severity": severity,
                         "expected_code": mutation.expected_code, "consequential": severity >= 2},
            })
    return sorted(cases, key=lambda c: c["case_id"])


def worker_view(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"case_id": c["case_id"], "record": copy.deepcopy(c["record"])} for c in cases]


def gold_view(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema": "scientific-red-team-gold-v1",
            "cases": [{"case_id": c["case_id"], **c["gold"]} for c in cases],
            "warning": "Do not expose this file to the system under test."}


def evaluation_sample(cases: list[dict[str, Any]], per_family: int = 2,
                      clean_controls: int = 4) -> list[dict[str, Any]]:
    """Deterministic blinded sample: hardest two severities per family + clean controls."""
    selected = []
    clean = [c for c in cases if c["gold"]["family"] is None][:clean_controls]
    selected.extend(clean)
    for family in sorted({c["gold"]["family"] for c in cases if c["gold"]["family"]}):
        candidates = [c for c in cases if c["gold"]["family"] == family]
        candidates.sort(key=lambda c: c["gold"]["severity"], reverse=True)
        selected.extend(candidates[:per_family])
    return sorted(selected, key=lambda c: c["case_id"])


def score(cases: list[dict[str, Any]], detections: dict[str, list[str]]) -> dict[str, Any]:
    by_id = {c["case_id"]: c for c in cases}
    if set(detections) - set(by_id):
        raise ContractError("Unknown red-team case ID")
    rows = []
    mutated = consequential = hit = consequential_hit = clean = clean_fp = 0
    severity_total, severity_hit = Counter(), Counter()
    family_total, family_hit = Counter(), Counter()
    for case_id, case in by_id.items():
        gold = case["gold"]
        detected = set(detections.get(case_id, []))
        expected = gold["expected_code"]
        if expected is None:
            clean += 1
            clean_fp += bool(detected)
            success = not detected
        else:
            mutated += 1
            family_total[gold["family"]] += 1
            severity_total[gold["severity"]] += 1
            success = expected in detected
            hit += success
            family_hit[gold["family"]] += success
            severity_hit[gold["severity"]] += success
            if gold["consequential"]:
                consequential += 1
                consequential_hit += success
        rows.append({"case_id": case_id, "family": gold["family"], "severity": gold["severity"],
                     "expected_code": expected, "detected_codes": sorted(detected), "hit": success})
    return {
        "schema": "scientific-red-team-evaluation-v1",
        "cases": len(cases),
        "mutation_recall": hit / mutated if mutated else None,
        "consequential_recall": consequential_hit / consequential if consequential else None,
        "clean_false_positive_rate": clean_fp / clean if clean else None,
        "family_recall": {f: family_hit[f] / family_total[f] for f in sorted(family_total)},
        "severity_recall": {str(k): severity_hit[k] / severity_total[k] for k in sorted(severity_total)},
        "rows": sorted(rows, key=lambda r: r["case_id"]),
        "interpretation": "Detecting planted theory defects is a diagnostic of review sensitivity, not proof of scientific validity.",
    }


def oracle_detector(case: dict[str, Any], gold: dict[str, Any]) -> list[str]:
    """Evaluator-only control. Never use as a worker baseline."""
    return [gold["expected_code"]] if gold["expected_code"] else []
