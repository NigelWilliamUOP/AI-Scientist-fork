"""Synthetic offline demonstration for the social-science challenge harness."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .challenge_harness import (
    DeterministicChallengeWorker, baseline_mutation_detector,
    evaluate_mutations, generate_mutation_suite, mutation_gold,
    mutation_worker_view, run_challenge,
)
from .core import Ledger, write_once


def synthetic_packet() -> dict:
    return {
        "question_id": "SYN-CHALLENGE-001",
        "question": "Within a bounded organisation set, is exposure X associated with institutional stress Y?",
        "observation": "The supplied synthetic evidence contains an association plus one contrary boundary observation.",
        "claim_type": "associational",
        "scope": {"population": "synthetic organisations", "place": "synthetic UK", "time": "2025-2026"},
        "cutoff": "2026-09-30T23:59:59+00:00",
        "data_exposure": "fully_seen",
        "outcome": "institutional stress index",
        "unit_of_analysis": "organisation-period",
        "evidence": [
            {
                "evidence_id": "E1",
                "source_cluster": "survey-A",
                "source_extract": "Synthetic source: exposure and stress are positively associated in the primary sample.",
                "available_at": "2026-06-01T00:00:00+00:00",
                "direction": "supports",
                "numeric_facts": {"estimate": 0.42},
                "sample_size": 120,
            },
            {
                "evidence_id": "E2",
                "source_cluster": "survey-B",
                "source_extract": "Synthetic source: the relationship is weak in the low-volume subgroup.",
                "available_at": "2026-07-15T00:00:00+00:00",
                "direction": "challenges",
            },
        ],
        "candidate_propositions": [
            {
                "proposition_id": "P1",
                "statement": "Within the frozen synthetic scope, exposure X is associated with higher institutional stress Y.",
                "claim_type": "associational",
                "scope": {"population": "synthetic organisations", "place": "synthetic UK", "time": "2025-2026"},
                "outcome": "institutional stress index",
                "falsifier": "The relationship reverses or disappears under the prespecified boundary test.",
                "contribution": "A bounded proposition linking exposure to institutional stress while retaining a contrary subgroup observation.",
                "construct": "institutional stress",
                "measured_proxy": "institutional stress",
                "publishability": {"contribution": 0.65, "discriminating_test": 0.75, "scope_precision": 0.95, "robustness": 0.65},
            }
        ],
    }


def run_demo(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    packet = synthetic_packet()
    ledger = Ledger(output / "challenge-ledger.sqlite")
    try:
        report = run_challenge(packet, DeterministicChallengeWorker(), ledger, run_id="synthetic-demo")
        integrity = ledger.verify()
    finally:
        ledger.close()

    cases = generate_mutation_suite(packet)
    worker_cases = mutation_worker_view(cases)
    detections = {
        case["case_id"]: baseline_mutation_detector(case["packet"])
        for case in worker_cases
    }
    evaluation = evaluate_mutations(cases, detections)

    write_once(output / "question_packet.json", packet)
    write_once(output / "challenge_report.json", report)
    write_once(output / "mutation_cases_public.json", worker_cases)
    write_once(output / "mutation_gold_private.json", mutation_gold(cases))
    write_once(output / "mutation_evaluation.json", evaluation)

    summary = {
        "harness_version": report["version"],
        "selected_status": report["selected_status"],
        "mutation_cases": evaluation["mutations"],
        "mutation_recall": evaluation["mutation_recall"],
        "consequential_mutation_recall": evaluation["consequential_mutation_recall"],
        "clean_false_positive_rate": evaluation["clean_false_positive_rate"],
        "ledger_integrity": integrity["integrity"],
        "live_model_calls": 0,
        "external_spend_usd": 0,
        "empirical_evidence": False,
        "scientific_validity_established": False,
    }
    write_once(output / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("research_campaigns_runs/challenge-demo"))
    args = parser.parse_args()
    print(json.dumps(run_demo(args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
