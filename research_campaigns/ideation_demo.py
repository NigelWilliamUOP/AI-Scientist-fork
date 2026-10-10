"""Public synthetic AI-overload control, not NHS data or literature findings."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from .challenge_demo import synthetic_packet
from .challenge_harness import DeterministicChallengeWorker
from .core import Ledger, write_once
from .ideation import run_ideation_challenge


def synthetic_inputs() -> tuple[dict, dict]:
    packet = synthetic_packet()
    packet.update(question_id="SYN-AI-OVERLOAD-001",
                  question="How might AI-assisted challenges change staff work per resolved service episode?",
                  observation="PUBLIC SYNTHETIC FIXTURE; no observed healthcare findings.",
                  outcome="staff work per resolved episode", unit_of_analysis="service episode",
                  scope={"population": "synthetic service episodes", "place": "synthetic healthcare service", "time": "2026"},
                  cutoff="2026-10-10T00:00:00+00:00", candidate_propositions=[])
    papers = []
    for pid, method in (
        ("P1", "Ordinary queue workload depends on arrivals and service effort per episode."),
        ("P2", "Repeat-contact measurement links contacts to resolved episodes to avoid counting contacts as demand."),
        ("P3", "Verification work is measured as distinct claims checked and staff minutes per resolved episode."),
    ):
        papers.append({
            "paper_id": pid, "canonical_id": "urn:public-synthetic-method:" + pid,
            "title": "Fictional method control " + pid,
            "version": "public-synthetic-fixture-v1", "synthetic": True,
            "version_at": "2026-09-01T00:00:00+00:00", "available_at": "2026-09-01T00:00:00+00:00",
            "access_level": "full_text", "read_status": "read",
            "masking_attestation": "results_omitted_from_methods_and_views",
            "masked_views": {"problem_definition": "Synthetic workload measurement problem.",
                             "challenge": "Distinguish arrivals, contacts and verification effort.",
                             "intuition": method, "solution": "Specify separately measurable components."},
            "answers": [{"goal": "Explain the mechanism", "locator": "Synthetic Methods paragraph 1",
                         "answer": method, "kind": "mechanism", "access_level": "full_text"},
                        {"goal": "Describe reported outcomes", "locator": "Synthetic Results paragraph 1",
                         "answer": "RESULT_SEEN_SENTINEL: 99 percent gain (invented control).",
                         "kind": "result", "access_level": "full_text"}],
        })
    spec = {"axis": "Distinguish verification effort from episode and contact volume",
            "prior_candidate_exposure": False, "papers": papers,
            "discovery_coverage": "Three fictional method digests; no real literature search executed."}
    return packet, spec


def receipt(papers: list[dict], pid: str, claim: str = "Synthetic mechanism support") -> dict:
    paper = next(p for p in papers if p["paper_id"] == pid)
    answer = paper["answers"][0]
    return {"paper_id": pid, "version": paper["version"], "goal": answer["goal"],
            "locator": answer["locator"], "answer_text": answer["answer"],
            "claim": claim, "kind": "mechanism"}


class SyntheticSearcher:
    name = "synthetic-disconfirmation-fixture-v1"
    def search(self, request: dict) -> dict:
        return {"status": "searched", "origin": "synthetic_fixture",
                "candidate_hash": request["candidate_hash"], "papers": [],
                "coverage": "Deterministic planted search record, not an executed literature search.",
                "queries": [{"query": "verification workload AND staff work per resolved episode",
                             "searched_at": "2026-10-10T00:00:00+00:00",
                             "purpose": "mechanism_plus_problem_disconfirmation", "paper_ids": ["P1", "P2", "P3"]}]}


class SyntheticIdeationWorker(DeterministicChallengeWorker):
    name = "synthetic-ideation-control-v1"
    def __init__(self):
        self.role_calls = 0
    def complete(self, role: str, context: dict) -> dict:
        self.role_calls = getattr(self, "role_calls", 0) + 1
        papers = context.get("papers", [])
        if role == "ideation_gap_finder":
            return {"outcome": "gap", "reason": "Planted measurement gap for interface testing only.",
                    "gap": {"gap_id": "G1", "axis": context["axis"],
                            "statement": "Contact counts alone do not distinguish episode demand from verification effort.",
                            "contribution_type": "measurement", "near_miss_ids": ["P1", "P2"],
                            "supports": [receipt(papers, "P1"), receipt(papers, "P2")]}}
        if role == "ideation_blind_baseline":
            return {"proposal_exposed": False,
                    "mechanisms": [{"mechanism_id": "B1", "mechanism": "More arrivals or repeat contacts increase ordinary work.",
                                    "derivation": "Combine ordinary queue effort with episode-linked contact counting.",
                                    "supports": [receipt(papers, "P1"), receipt(papers, "P2")]}],
                    "limitations": ["Fictional source control; no baseline novelty claim."]}
        if role == "ideation_innovator":
            q = context["question"]
            return {"candidate": {
                "proposition_id": "I" + str(context["candidate_index"] + 1),
                "statement": "AI-assisted challenges may increase verification effort per resolved episode at fixed episode volume.",
                "claim_type": "associational", "scope": copy.deepcopy(q["scope"]), "outcome": q["outcome"],
                "falsifier": "Reduced repeat contacts offset added verification effort.",
                "contribution": "Separate verification effort from episode and contact counts.", "contribution_type": "measurement",
                "mechanism_transfer": {
                    "source_mechanism": "Verification workload per unit of completed service",
                    "target_mechanism": "Staff time checking additional patient-supplied claims per resolved episode",
                    "mapping": [{"source_element": "claim requiring verification", "target_element": "patient challenge assertion"},
                                {"source_element": "completed service unit", "target_element": "resolved healthcare episode"}],
                    "required_conditions": ["Additional claims require staff checking", "Episode resolution is recorded consistently"],
                    "failure_risk": "Improved challenge quality reduces repeat contacts enough to offset checking time."},
                "predictions": [{"prediction": "Work per resolved episode rises at fixed episode volume.",
                                 "kill_condition": "Added verification effort is fully offset by lower repeat-contact work."}],
                "supports": [receipt(papers, "P1"), receipt(papers, "P3")],
            }}
        if role == "ideation_reviewer":
            return {"verdict": "survive", "focus": None,
                    "strongest_objection": "Ordinary repeat-contact theory may cover this pattern.",
                    "reason": "Planted survivor for exercising subsequent gates, not a scientific judgement.",
                    "supports": [receipt(papers, "P1"), receipt(papers, "P3")]}
        if role == "ideation_baseline_comparator":
            return {"assessment": "added_mechanism", "reason": "Control candidate separates claim-verification effort from contact counts.",
                    "supports": [receipt(papers, "P3")]}
        return super().complete(role, context)


def run_demo(output: Path) -> dict:
    packet, spec = synthetic_inputs()
    ledger = Ledger(output / "ideation-ledger.sqlite")
    worker = SyntheticIdeationWorker()
    try:
        result = run_ideation_challenge(packet, spec, worker, ledger,
                                        run_id="synthetic-ideation", searcher=SyntheticSearcher())
        integrity = ledger.verify()
    finally:
        ledger.close()
    write_once(output / "question.json", packet)
    write_once(output / "literature_spec.json", spec)
    write_once(output / "report.json", result)
    summary = {"status": result["status"], "baseline_frozen": result["baseline"]["frozen"],
               "role_calls_reserved": result["role_calls_reserved"],
               "role_call_reservation_scope": "Ideation stages only",
               "total_worker_calls_measured": worker.role_calls,
               "search_operations_reserved": result["search_operations_reserved"],
               "ledger_integrity": integrity["integrity"], "real_nhs_data_used": False,
               "live_literature_searches": 0, "live_model_calls": 0, "external_spend_usd": 0,
               "scientific_validity_established": False}
    write_once(output / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("research_campaigns_runs/ideation-demo"))
    print(json.dumps(run_demo(parser.parse_args().output), indent=2))


if __name__ == "__main__":
    main()
