"""Support-seeking adversarial challenge harness for empirical social science.

The optimisation target is a defensible publishable proposition, not statistical
significance. Frozen outcomes, exclusions, evidence vintages and contrary
evidence cannot be changed to improve the score. Existing-data propositions stay
exploratory when their target outcomes have already been inspected.
"""
from __future__ import annotations

import copy
import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from .core import ContractError, Denied, Ledger, digest, instant, safe_id

VERSION = "challenge-harness-0.1"
CLAIM_TYPES = {"descriptive", "associational", "predictive", "causal", "mechanistic"}
THEORY_ROLES = (
    "mechanism_builder", "rival_theory_builder",
    "discriminating_test_designer", "theoretical_contribution_editor",
)
ATTACK_ROLES = (
    "support_builder", "falsifier", "rival_mechanisms",
    "measurement_confounds", "boundary_conditions",
)
GATE_ROLES = (
    "methods_verifier", "statistics_verifier", "evidence_verifier",
    "reproducibility_verifier", "publication_verifier",
)
ROLE_SPECS = {
    "proposition_builder": """Generate 2-5 defensible propositions. Optimise contribution, discriminating predictions, evidence alignment and precise scope. Never change frozen outcomes, exclusions, evidence vintages or suppress contrary evidence. Return {"candidates":[{"proposition_id":"...","statement":"...","claim_type":"descriptive|associational|predictive|causal|mechanistic","scope":{},"outcome":"exact frozen outcome","falsifier":"...","contribution":"...","publishability":{"contribution":0-1,"discriminating_test":0-1,"scope_precision":0-1,"robustness":0-1}}]}.""",
    "mechanism_builder": """Act as a theory-building collaborator. Turn the bounded proposition into an explicit mechanism without pretending the mechanism has been observed. Separate constructs, actors/units, causal or associational links, timing and boundary conditions. Return {"mechanism":"...","constructs":["..."],"links":[{"from":"...","to":"...","relation":"...","status":"proposed"}],"boundary_conditions":["..."],"assumptions":["..."],"limitations":["..."]}.""",
    "rival_theory_builder": """Build 2-4 serious rival theories from different explanatory classes. Do not create straw rivals. Return {"rivals":[{"rival_id":"R1","statement":"...","mechanism":"...","shared_predictions":["..."],"different_predictions":["..."],"boundary_conditions":["..."]}],"limitations":["..."]}.""",
    "discriminating_test_designer": """Design tests that separate the focal mechanism from at least one serious rival. Prefer existing data, untouched holdouts or new periods before proposing new collection. Every test needs predicted outcomes under the focal theory and rival, plus an inconclusive branch. Return {"tests":[{"test_id":"T1","measurement":"...","focal_prediction":"...","rival_id":"R1","rival_prediction":"...","inconclusive":"...","decision_consequence":"...","existing_data_possible":true}],"limitations":["..."]}.""",
    "theoretical_contribution_editor": """State what the theory changes relative to a weaker descriptive account: mechanism, boundary condition, construct relationship or rival resolution. Do not claim novelty from search absence. Return {"contribution":"...","strongest_publishable_formulation":"...","claims_to_avoid":["..."],"novelty_status":"unverified|bounded_search_support|established_by_review","limitations":["..."]}.""",
    "support_builder": """Build the strongest evidence-bounded case. State exactly what is supported and expose every auxiliary assumption. Return {"summary":"...","findings":["..."],"support_strength":"strong|moderate|weak|none","limitations":["..."]}.""",
    "falsifier": """Try to defeat the proposition with counterexamples, negative controls and observations incompatible with it under declared assumptions. Return {"summary":"...","findings":["..."],"support_strength":"not_applicable","limitations":["..."]}.""",
    "rival_mechanisms": """Develop genuinely different rivals including confounding, reverse causation, selection, context, competing mechanisms and chance. Give discriminating tests. Return {"summary":"...","findings":["..."],"support_strength":"not_applicable","limitations":["..."]}.""",
    "measurement_confounds": """Attack construct validity, proxy use, preprocessing, missingness, leakage and unit-of-analysis choices. Return {"summary":"...","findings":["..."],"support_strength":"not_applicable","limitations":["..."]}.""",
    "boundary_conditions": """Attack transportability and identify narrower population, place, period or mechanism boundaries that produce a stronger defensible proposition. Return {"summary":"...","findings":["..."],"support_strength":"not_applicable","limitations":["..."]}.""",
    "methods_verifier": """Verification gate: treat each methodological step as unestablished. Check design, estimand, sampling unit, confounding, selection, reverse causation, controls, multiplicity and prespecification. Return {"verdict":"accept|repair|reject|inconclusive","first_failing_step":"..." or null,"confirmed_steps":["..."],"findings":["..."],"codes":["..."]}.""",
    "statistics_verifier": """Verification gate: treat each numerical statement as unestablished. Check denominators, estimates, uncertainty, dependence, assumptions and robustness. Nonsignificance is not equivalence. Return {"verdict":"accept|repair|reject|inconclusive","first_failing_step":"..." or null,"confirmed_steps":["..."],"findings":["..."],"codes":["..."]}.""",
    "evidence_verifier": """Verification gate: treat each source-to-claim link as wrong until checked. Check contrary evidence, source dependence and temporal leakage. Independently rate how strongly the supplied evidence supports the bounded proposition. Return {"verdict":"accept|repair|reject|inconclusive","first_failing_step":"..." or null,"confirmed_steps":["..."],"findings":["..."],"codes":["..."],"support_strength":"strong|moderate|weak|none"}.""",
    "reproducibility_verifier": """Verification gate: check immutable inputs, provenance, code/environment/run evidence and that planned or failed work is not described as completed. Return {"verdict":"accept|repair|reject|inconclusive","first_failing_step":"..." or null,"confirmed_steps":["..."],"findings":["..."],"codes":["..."]}.""",
    "publication_verifier": """Verification gate for proposition value, not journal acceptance. Judge whether the bounded proposition could support a publishable contribution if the stated evidence survives. Novelty must be evidence-bounded; absence from a quick search is not novelty. Return {"verdict":"accept|repair|reject|inconclusive","first_failing_step":"..." or null,"confirmed_steps":["..."],"findings":["..."],"codes":["..."],"criteria":{"contribution":0-1,"novelty_positioning":0-1,"discriminating_test":0-1,"scope_precision":0-1,"robustness":0-1}}. Scores are search utilities, not publication probabilities.""",
    "comparative_reviewer": """Compare attempts side-by-side for shared assumptions, shared inputs, contradictions and false consensus caused by correlated evidence or models. Return {"verdict":"accept|repair|reject|inconclusive","first_failing_step":"..." or null,"confirmed_steps":["..."],"findings":["..."],"codes":["..."]}.""",
    "proposition_repair": """Repair by narrowing scope, sharpening a discriminating mechanism or increasing uncertainty. Never change frozen data/outcomes/exclusions/vintages or hide contrary evidence. Use a new proposition_id. Return {"proposition":{"proposition_id":"...","statement":"...","claim_type":"descriptive|associational|predictive|causal|mechanistic","scope":{},"outcome":"exact frozen outcome","falsifier":"...","contribution":"...","publishability":{"contribution":0-1,"discriminating_test":0-1,"scope_precision":0-1,"robustness":0-1}}}.""",
}


class Worker(Protocol):
    name: str
    def complete(self, role: str, context: dict[str, Any]) -> dict[str, Any]: ...


class SessionChallengeWorker:
    """Use existing budgeted provider Sessions; optionally separate verifier model."""
    def __init__(self, generator_session: Any, verifier_session: Any | None = None):
        self.generator_session = generator_session
        self.verifier_session = verifier_session or generator_session
        g = getattr(getattr(generator_session, "provider", None), "name", "unknown")
        v = getattr(getattr(self.verifier_session, "provider", None), "name", "unknown")
        self.name = f"challenge:{g}|verify:{v}"

    def complete(self, role: str, context: dict[str, Any]) -> dict[str, Any]:
        session = self.verifier_session if role in {*GATE_ROLES, "comparative_reviewer"} else self.generator_session
        return session.ask("challenge_role", {"challenge_role": role, **context})


@dataclass(frozen=True)
class ChallengeConfig:
    max_rounds: int = 3
    max_propositions: int = 5
    support_weight: float = 2.0
    gate_weight: float = 2.0
    contribution_weight: float = 1.25
    novelty_weight: float = 1.0
    discrimination_weight: float = 1.25
    scope_weight: float = 0.75
    robustness_weight: float = 1.0
    rejection_penalty: float = 2.5

    def validate(self) -> None:
        if not 1 <= self.max_rounds <= 8 or not 1 <= self.max_propositions <= 12:
            raise ContractError("Challenge round/proposition limits out of range")
        for value in self.__dict__.values():
            if isinstance(value, float) and (not math.isfinite(value) or value < 0):
                raise ContractError("Challenge weights must be finite and non-negative")


def _require_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(label + " must be a non-empty string")
    return value


def validate_proposition(prop: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    required = {"proposition_id", "statement", "claim_type", "scope", "outcome", "falsifier", "contribution"}
    if not isinstance(prop, dict) or not required.issubset(prop):
        raise ContractError("Invalid proposition schema")
    safe_id(_require_str(prop["proposition_id"], "proposition_id"))
    if prop["claim_type"] not in CLAIM_TYPES or not isinstance(prop["scope"], dict):
        raise ContractError("Invalid proposition claim type or scope")
    if prop["outcome"] != packet["outcome"]:
        prop.setdefault("structural_warnings", []).append("OUTCOME_SWITCH")
    prop["confirmatory_status"] = (
        "eligible_for_prospective_test" if packet["data_exposure"] == "unseen"
        else "exploratory_existing_data"
    )
    return prop


def validate_question_packet(packet: dict[str, Any]) -> dict[str, Any]:
    required = {
        "question_id", "question", "observation", "claim_type", "scope", "cutoff",
        "data_exposure", "outcome", "unit_of_analysis", "evidence",
        "candidate_propositions",
    }
    if not isinstance(packet, dict) or not required.issubset(packet):
        raise ContractError("Invalid question packet")
    safe_id(_require_str(packet["question_id"], "question_id"))
    if packet["claim_type"] not in CLAIM_TYPES or not isinstance(packet["scope"], dict):
        raise ContractError("Invalid question claim type or scope")
    instant(packet["cutoff"])
    if packet["data_exposure"] not in {"unseen", "partially_seen", "fully_seen", "unknown"}:
        raise ContractError("Invalid data_exposure")
    if not isinstance(packet["evidence"], list) or not packet["evidence"]:
        raise ContractError("Question requires evidence")
    if not isinstance(packet["candidate_propositions"], list):
        raise ContractError("candidate_propositions must be a list")
    ids = []
    for item in packet["evidence"]:
        needed = {"evidence_id", "source_cluster", "source_extract", "available_at", "direction"}
        if not isinstance(item, dict) or not needed.issubset(item):
            raise ContractError("Invalid evidence item")
        safe_id(item["evidence_id"])
        ids.append(item["evidence_id"])
        instant(item["available_at"])
        if item["direction"] not in {"supports", "challenges", "inconclusive", "context"}:
            raise ContractError("Invalid evidence direction")
    if len(ids) != len(set(ids)):
        raise ContractError("Duplicate evidence IDs")
    prop_ids = []
    for prop in packet["candidate_propositions"]:
        validate_proposition(prop, packet)
        prop_ids.append(prop["proposition_id"])
    if len(prop_ids) != len(set(prop_ids)):
        raise ContractError("Duplicate proposition IDs")
    return packet


def mechanical_scan(packet: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    cutoff = instant(packet["cutoff"])
    fingerprints: dict[str, list[dict[str, Any]]] = {}
    for item in packet["evidence"]:
        if item.get("admitted", True) and instant(item["available_at"]) > cutoff:
            findings.append({"code": "TEMPORAL_LEAK", "target": item["evidence_id"]})
        facts, claimed = item.get("numeric_facts", {}), item.get("claimed_numeric_facts", {})
        if isinstance(facts, dict) and isinstance(claimed, dict):
            for key in sorted(set(facts) & set(claimed)):
                if facts[key] != claimed[key]:
                    findings.append({"code": "NUMERIC_DRIFT", "target": item["evidence_id"], "field": key})
        if "sample_size" in item and "claimed_sample_size" in item and item["sample_size"] != item["claimed_sample_size"]:
            findings.append({"code": "DENOMINATOR_DRIFT", "target": item["evidence_id"]})
        fp = item.get("source_fingerprint")
        if fp:
            fingerprints.setdefault(fp, []).append(item)
    for members in fingerprints.values():
        if len(members) > 1 and len({m["source_cluster"] for m in members}) > 1:
            findings.append({"code": "FALSE_INDEPENDENCE", "target": [m["evidence_id"] for m in members]})
    for prop in packet["candidate_propositions"]:
        if prop["outcome"] != packet["outcome"]:
            findings.append({"code": "OUTCOME_SWITCH", "target": prop["proposition_id"]})
        if prop["claim_type"] == "causal" and packet["claim_type"] != "causal" and not prop.get("identification_strategy"):
            findings.append({"code": "CAUSAL_UPGRADE", "target": prop["proposition_id"]})
        statement = prop["statement"].lower()
        if prop.get("null_test_only") and any(x in statement for x in ("no effect", "equivalent", "no difference")):
            findings.append({"code": "NULL_TO_EQUIVALENCE", "target": prop["proposition_id"]})
        if prop.get("construct") and prop.get("measured_proxy") and prop["construct"] != prop["measured_proxy"] and not prop.get("proxy_validity_evidence"):
            findings.append({"code": "PROXY_SUBSTITUTION", "target": prop["proposition_id"]})
    return findings


def _invoke(worker: Worker, role: str, context: dict[str, Any]) -> dict[str, Any]:
    response = worker.complete(role, {"role_contract": ROLE_SPECS[role], **context})
    if not isinstance(response, dict):
        raise ContractError("Worker response must be a JSON object")
    return response


def _attack(response: dict[str, Any]) -> dict[str, Any]:
    needed = {"summary", "findings", "support_strength", "limitations"}
    if not needed.issubset(response) or response["support_strength"] not in {"strong", "moderate", "weak", "none", "not_applicable"}:
        raise ContractError("Invalid attack response")
    return response


def _gate(response: dict[str, Any]) -> dict[str, Any]:
    needed = {"verdict", "first_failing_step", "confirmed_steps", "findings", "codes"}
    if not needed.issubset(response) or response["verdict"] not in {"accept", "repair", "reject", "inconclusive"}:
        raise ContractError("Invalid gate response")
    if not all(isinstance(response[k], list) for k in ("confirmed_steps", "findings", "codes")):
        raise ContractError("Gate lists malformed")
    return response


def _unit(value: Any, default: float = 0.5) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)) and math.isfinite(value):
        return max(0.0, min(1.0, float(value)))
    return default


def score_proposition(prop: dict[str, Any], attempts: dict[str, dict[str, Any]],
                      gates: dict[str, dict[str, Any]], comparative: dict[str, Any],
                      cfg: ChallengeConfig) -> dict[str, Any]:
    support_label = gates["evidence_verifier"].get("support_strength", attempts["support_builder"]["support_strength"])
    support = {"strong": 1.0, "moderate": .66, "weak": .33, "none": 0.0, "not_applicable": 0.0}.get(support_label, 0.0)
    verdicts = [gates[r]["verdict"] for r in GATE_ROLES] + [comparative["verdict"]]
    gate_map = {"accept": 1.0, "repair": .5, "inconclusive": .25, "reject": 0.0}
    gate_score = sum(gate_map[v] for v in verdicts) / len(verdicts)
    reject_fraction = verdicts.count("reject") / len(verdicts)
    pub = gates["publication_verifier"].get("criteria", {})
    contribution = _unit(pub.get("contribution"))
    novelty = _unit(pub.get("novelty_positioning"))
    discrimination = _unit(pub.get("discriminating_test"))
    scope = _unit(pub.get("scope_precision"))
    robustness = _unit(pub.get("robustness"))
    raw = (
        cfg.support_weight * support + cfg.gate_weight * gate_score
        + cfg.contribution_weight * contribution + cfg.novelty_weight * novelty
        + cfg.discrimination_weight * discrimination
        + cfg.scope_weight * scope + cfg.robustness_weight * robustness
        - cfg.rejection_penalty * reject_fraction
    )
    maximum = cfg.support_weight + cfg.gate_weight + cfg.contribution_weight + cfg.novelty_weight + cfg.discrimination_weight + cfg.scope_weight + cfg.robustness_weight
    score = max(0.0, min(1.0, raw / maximum))
    if "reject" in verdicts:
        status = "challenged"
    elif "repair" in verdicts:
        status = "repair_required"
    elif all(v == "accept" for v in verdicts) and support >= .66:
        status = "survives_current_challenge"
    elif support == 0:
        status = "unsupported"
    else:
        status = "inconclusive"
    return {
        "search_score": round(score, 6), "status": status,
        "support_component": support, "gate_component": gate_score,
        "publication_components": {"contribution": contribution, "novelty_positioning": novelty,
                                   "discriminating_test": discrimination, "scope_precision": scope,
                                   "robustness": robustness},
        "interpretation": "Search utility only; not probability of truth or publication.",
    }


def _run_one(run_id: str, packet: dict[str, Any], prop: dict[str, Any], worker: Worker,
             ledger: Ledger, cfg: ChallengeConfig, round_number: int) -> dict[str, Any]:
    context = {
        "run_id": run_id, "round": round_number,
        "question": {k: packet[k] for k in ("question_id", "question", "observation", "claim_type", "scope", "cutoff", "data_exposure", "outcome", "unit_of_analysis")},
        "evidence": packet["evidence"], "proposition": prop,
        "objective": "Find the strongest defensible publishable proposition while retaining all contrary evidence and frozen boundaries.",
    }
    theory = {}
    for role in THEORY_ROLES:
        theory[role] = _invoke(worker, role, {**context, "prior_theory": theory})
        ledger.put(f"challenge_theory:{run_id}", f"r{round_number}:{prop['proposition_id']}:{role}",
                   theory[role], actor="collaborator:" + worker.name)
    context["theory_package"] = theory
    attempts = {}
    for role in ATTACK_ROLES:
        attempts[role] = _attack(_invoke(worker, role, context))
        ledger.put(f"challenge_attempts:{run_id}", f"r{round_number}:{prop['proposition_id']}:{role}", attempts[role], actor="worker:" + worker.name)
    gates = {}
    gate_context = {**context, "attempts": attempts, "mechanical_findings": mechanical_scan(packet)}
    for role in GATE_ROLES:
        gates[role] = _gate(_invoke(worker, role, gate_context))
        if role == "publication_verifier":
            criteria = gates[role].get("criteria")
            required_criteria = {"contribution", "novelty_positioning", "discriminating_test", "scope_precision", "robustness"}
            if not isinstance(criteria, dict) or not required_criteria.issubset(criteria):
                raise ContractError("publication_verifier missing criteria")
        ledger.put(f"challenge_gates:{run_id}", f"r{round_number}:{prop['proposition_id']}:{role}", gates[role], actor="verifier:" + worker.name)
    comparative = _gate(_invoke(worker, "comparative_reviewer", {**gate_context, "gates": gates}))
    ledger.put(f"challenge_gates:{run_id}", f"r{round_number}:{prop['proposition_id']}:comparative", comparative, actor="verifier:" + worker.name)
    score = score_proposition(prop, attempts, gates, comparative, cfg)
    codes = sorted(set(
        [f["code"] for f in gate_context["mechanical_findings"]]
        + [c for g in gates.values() for c in g["codes"]] + comparative["codes"]
    ))
    result = {"round": round_number, "proposition": prop, "theory_package": theory,
              "attempts": attempts, "gates": gates, "comparative_review": comparative,
              "score": score, "finding_codes": codes}
    ledger.put(f"challenge_rounds:{run_id}", f"r{round_number}:{prop['proposition_id']}", result)
    return result


def _repair(run_id: str, packet: dict[str, Any], result: dict[str, Any],
            worker: Worker, ledger: Ledger, round_number: int) -> dict[str, Any] | None:
    if result["score"]["status"] != "repair_required":
        return None
    response = _invoke(worker, "proposition_repair", {
        "run_id": run_id, "round": round_number,
        "original_proposition": result["proposition"],
        "frozen_question": {k: packet[k] for k in ("question_id", "question", "observation", "claim_type", "scope", "cutoff", "data_exposure", "outcome", "unit_of_analysis")},
        "theory_package": result.get("theory_package", {}),
        "gates": result["gates"], "comparative_review": result["comparative_review"],
        "contrary_evidence": [e for e in packet["evidence"] if e["direction"] == "challenges"],
    })
    prop = response.get("proposition")
    if not isinstance(prop, dict):
        raise ContractError("Repair must return proposition")
    validate_proposition(prop, packet)
    if prop["proposition_id"] == result["proposition"]["proposition_id"]:
        raise Denied("Repair requires a new proposition ID")
    if prop["outcome"] != result["proposition"]["outcome"]:
        raise Denied("Repair cannot switch the frozen outcome")
    ledger.put(f"challenge_repairs:{run_id}", prop["proposition_id"], {"repair_of": result["proposition"]["proposition_id"], "proposition": prop}, actor="worker:" + worker.name)
    return prop


def run_challenge(packet: dict[str, Any], worker: Worker, ledger: Ledger, *,
                  run_id: str, config: ChallengeConfig | None = None) -> dict[str, Any]:
    safe_id(run_id)
    cfg = config or ChallengeConfig()
    cfg.validate()
    packet = validate_question_packet(copy.deepcopy(packet))
    question_hash = digest(packet)
    run_record = {"version": VERSION, "question_hash": question_hash, "config": cfg.__dict__, "worker": worker.name}
    old = ledger.get("challenge_runs", run_id)
    if old is not None:
        if old != run_record:
            raise Denied("run_id conflicts with frozen inputs/configuration")
        final = ledger.get("challenge_reports", run_id)
        if final is not None:
            return final
    else:
        ledger.put("challenge_runs", run_id, run_record)

    candidates = copy.deepcopy(packet["candidate_propositions"])[:cfg.max_propositions]
    if len(candidates) < cfg.max_propositions:
        built = _invoke(worker, "proposition_builder", {
            "question": packet,
            "seed_propositions": candidates,
            "max_propositions": cfg.max_propositions,
            "instruction": "Add distinct defensible alternatives where useful; do not merely paraphrase seed propositions.",
        })
        proposed = built.get("candidates", [])
        if not isinstance(proposed, list):
            raise ContractError("proposition_builder candidates must be a list")
        seen = {p["proposition_id"] for p in candidates}
        for prop in proposed:
            validate_proposition(prop, packet)
            if prop["proposition_id"] not in seen and len(candidates) < cfg.max_propositions:
                candidates.append(prop)
                seen.add(prop["proposition_id"])
    if not candidates:
        raise ContractError("Challenge requires at least one usable proposition")
    ledger.put(f"challenge_candidates:{run_id}", "initial", {"candidates": candidates})

    results = []
    repaired_ids = set()
    for round_number in range(1, cfg.max_rounds + 1):
        next_round = []
        for prop in candidates:
            result = _run_one(run_id, packet, prop, worker, ledger, cfg, round_number)
            results.append(result)
            if result["score"]["status"] == "repair_required" and prop["proposition_id"] not in repaired_ids:
                revised = _repair(run_id, packet, result, worker, ledger, round_number)
                if revised is not None:
                    repaired_ids.add(prop["proposition_id"])
                    next_round.append(revised)
        if any(r["score"]["status"] == "survives_current_challenge" for r in results):
            break
        candidates = next_round
        if not candidates:
            break

    ranked = sorted(results, key=lambda r: (
        r["score"]["status"] == "survives_current_challenge",
        r["score"]["search_score"], -r["round"],
    ), reverse=True)
    if not ranked:
        raise ContractError("Challenge run produced no result")
    selected = ranked[0]
    report = {
        "version": VERSION, "run_id": run_id, "question_id": packet["question_id"],
        "question_hash": question_hash,
        "objective": "Maximise defensible publishable-proposition yield without significance hunting or evidence suppression.",
        "selected_proposition_id": selected["proposition"]["proposition_id"],
        "selected_status": selected["score"]["status"],
        "selected_search_score": selected["score"]["search_score"],
        "confirmatory_status": selected["proposition"].get("confirmatory_status"),
        "selected_theory_package": selected.get("theory_package", {}),
        "ranked_candidates": [
            {"proposition_id": r["proposition"]["proposition_id"], "round": r["round"],
             "status": r["score"]["status"], "search_score": r["score"]["search_score"],
             "finding_codes": r["finding_codes"], "statement": r["proposition"]["statement"]}
            for r in ranked
        ],
        "contrary_evidence_retained": [e["evidence_id"] for e in packet["evidence"] if e["direction"] == "challenges"],
        "limits": [
            "Search score is not probability of truth, effect or publication.",
            "Same-data challenge is not independent replication.",
            "Existing-data propositions remain exploratory when target outcomes were already seen.",
        ],
        "journal_readiness": "not_independently_evaluated",
        "scientific_status": selected["score"]["status"],
    }
    ledger.put("challenge_reports", run_id, report)
    return report


@dataclass(frozen=True)
class Mutation:
    mutation_id: str
    family: str
    expected_code: str
    consequential: bool = True


DEFAULT_MUTATIONS = (
    Mutation("M01", "causal_upgrade", "CAUSAL_UPGRADE"),
    Mutation("M02", "proxy_substitution", "PROXY_SUBSTITUTION"),
    Mutation("M03", "numeric_drift", "NUMERIC_DRIFT"),
    Mutation("M04", "denominator_drift", "DENOMINATOR_DRIFT"),
    Mutation("M05", "temporal_leak", "TEMPORAL_LEAK"),
    Mutation("M06", "outcome_switch", "OUTCOME_SWITCH"),
    Mutation("M07", "null_to_equivalence", "NULL_TO_EQUIVALENCE"),
    Mutation("M08", "false_independence", "FALSE_INDEPENDENCE"),
    Mutation("M09", "source_direction_flip", "SOURCE_DIRECTION_FLIP"),
    Mutation("M10", "boundary_overreach", "BOUNDARY_OVERREACH"),
)


def apply_mutation(base: dict[str, Any], mutation: Mutation) -> dict[str, Any]:
    packet = validate_question_packet(copy.deepcopy(base))
    prop, evidence = packet["candidate_propositions"][0], packet["evidence"][0]
    family = mutation.family
    if family == "causal_upgrade":
        prop["claim_type"], prop["statement"] = "causal", "The exposure causes the frozen outcome."
        prop.pop("identification_strategy", None)
    elif family == "proxy_substitution":
        prop["construct"], prop["measured_proxy"] = prop.get("construct", "institutional stress"), "document word count"
        prop.pop("proxy_validity_evidence", None)
    elif family == "numeric_drift":
        facts = evidence.setdefault("numeric_facts", {"estimate": 10})
        key = sorted(facts)[0]
        evidence["claimed_numeric_facts"] = copy.deepcopy(facts)
        evidence["claimed_numeric_facts"][key] = facts[key] + 1
    elif family == "denominator_drift":
        evidence.setdefault("sample_size", 100)
        evidence["claimed_sample_size"] = evidence["sample_size"] + 7
    elif family == "temporal_leak":
        evidence["available_at"], evidence["admitted"] = "2999-01-01T00:00:00+00:00", True
    elif family == "outcome_switch":
        prop["outcome"] = packet["outcome"] + " alternative"
    elif family == "null_to_equivalence":
        prop["statement"], prop["null_test_only"] = "There is no effect and groups are equivalent.", True
    elif family == "false_independence":
        if len(packet["evidence"]) < 2:
            duplicate = copy.deepcopy(evidence)
            duplicate["evidence_id"] += "_dup"
            packet["evidence"].append(duplicate)
        a, b = packet["evidence"][0], packet["evidence"][1]
        fp = a.get("source_fingerprint") or digest(a["source_extract"])
        a["source_fingerprint"] = b["source_fingerprint"] = fp
        a["source_cluster"], b["source_cluster"] = "cluster_A", "cluster_B"
    elif family == "source_direction_flip":
        evidence["claimed_direction"] = "challenges" if evidence["direction"] == "supports" else "supports"
    elif family == "boundary_overreach":
        prop["scope"] = {"population": "all organisations", "place": "global", "time": "all periods"}
    return packet


def generate_mutation_suite(base: dict[str, Any],
                            mutations: Iterable[Mutation] = DEFAULT_MUTATIONS) -> list[dict[str, Any]]:
    normalised = validate_question_packet(copy.deepcopy(base))
    cases = [{"case_id": "case-" + digest(normalised)[:16], "packet": copy.deepcopy(normalised),
              "gold": {"mutation_id": None, "family": None, "expected_codes": [], "consequential": False}}]
    for mutation in mutations:
        packet = apply_mutation(normalised, mutation)
        case_id = "case-" + digest(packet)[:16]
        cases.append({"case_id": case_id, "packet": packet,
                      "gold": {"mutation_id": mutation.mutation_id, "family": mutation.family,
                               "expected_codes": [mutation.expected_code], "consequential": mutation.consequential}})
    return cases


def mutation_worker_view(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"case_id": case["case_id"], "packet": copy.deepcopy(case["packet"])} for case in cases]


def mutation_gold(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema": "research-mutation-gold-v1",
            "cases": [{"case_id": c["case_id"], **c["gold"]} for c in cases],
            "warning": "Gold labels must never enter worker context."}


def baseline_mutation_detector(packet: dict[str, Any]) -> list[str]:
    packet = validate_question_packet(copy.deepcopy(packet))
    codes = {f["code"] for f in mechanical_scan(packet)}
    for item in packet["evidence"]:
        if "claimed_direction" in item and item.get("claimed_direction") != item.get("direction"):
            codes.add("SOURCE_DIRECTION_FLIP")
    broad_scope_tokens = {"all organisations", "global", "all periods", "all populations", "all settings"}
    for prop in packet["candidate_propositions"]:
        changed = prop.get("scope") != packet.get("scope")
        broadened = any(str(value).strip().lower() in broad_scope_tokens for value in prop.get("scope", {}).values())
        if changed and broadened:
            codes.add("BOUNDARY_OVERREACH")
    return sorted(codes)


def evaluate_mutations(cases: list[dict[str, Any]],
                       detections: dict[str, list[str]]) -> dict[str, Any]:
    valid = {c["case_id"] for c in cases}
    if set(detections) - valid:
        raise ContractError("Detection includes unknown case ID")
    family_total, family_hit = Counter(), Counter()
    mutations = consequential = hits = consequential_hits = 0
    clean_total = clean_fp = 0
    rows = []
    for case in cases:
        gold, detected = case["gold"], set(detections.get(case["case_id"], []))
        expected = set(gold["expected_codes"])
        if gold["mutation_id"] is None:
            clean_total += 1
            clean_fp += bool(detected)
        else:
            mutations += 1
            family_total[gold["family"]] += 1
            hit = bool(expected & detected)
            hits += hit
            family_hit[gold["family"]] += hit
            if gold["consequential"]:
                consequential += 1
                consequential_hits += hit
        rows.append({"case_id": case["case_id"], "family": gold["family"],
                     "expected_codes": sorted(expected), "detected_codes": sorted(detected),
                     "hit": (not detected if not expected else bool(expected & detected))})
    return {
        "schema": "research-mutation-evaluation-v1",
        "mutations": mutations, "consequential_mutations": consequential,
        "mutation_recall": hits / mutations if mutations else None,
        "consequential_mutation_recall": consequential_hits / consequential if consequential else None,
        "clean_false_positive_rate": clean_fp / clean_total if clean_total else None,
        "family_recall": {f: family_hit[f] / family_total[f] for f in sorted(family_total)},
        "rows": rows,
        "interpretation": "Fault-injection performance only; not scientific validity or autonomous-research capability.",
    }


class DeterministicChallengeWorker:
    """Offline orchestration fixture, not an LLM or scientific reviewer."""
    name = "deterministic-challenge-baseline-v1"

    def complete(self, role: str, context: dict[str, Any]) -> dict[str, Any]:
        evidence = context.get("evidence", [])
        codes = sorted({f["code"] for f in context.get("mechanical_findings", [])})
        prop = context.get("proposition") or context.get("original_proposition")
        if role == "proposition_builder":
            q = context["question"]
            return {"candidates": [{
                "proposition_id": "P1",
                "statement": "Within the frozen scope, the exposure is associated with the frozen outcome.",
                "claim_type": "associational", "scope": q["scope"], "outcome": q["outcome"],
                "falsifier": "The association reverses or disappears under a prespecified boundary test.",
                "contribution": "Bounded empirical proposition for adversarial development.",
                "publishability": {"contribution": .6, "discriminating_test": .7, "scope_precision": .9, "robustness": .6},
            }]}
        if role == "mechanism_builder":
            return {"mechanism": "Exposure X changes verification workload, which increases the bounded stress outcome.",
                    "constructs": ["exposure X", "verification workload", "institutional stress"],
                    "links": [{"from": "exposure X", "to": "verification workload", "relation": "increases", "status": "proposed"},
                              {"from": "verification workload", "to": "institutional stress", "relation": "increases", "status": "proposed"}],
                    "boundary_conditions": ["synthetic organisations", "2025-2026"],
                    "assumptions": ["verification workload is measured comparably"], "limitations": ["Mechanism unobserved."]}
        if role == "rival_theory_builder":
            return {"rivals": [{"rival_id": "R1", "statement": "A common workload shock drives both exposure and stress.",
                                "mechanism": "common cause", "shared_predictions": ["positive association"],
                                "different_predictions": ["association attenuates after workload control"],
                                "boundary_conditions": ["high workload periods"]}],
                    "limitations": ["Synthetic fixture."]}
        if role == "discriminating_test_designer":
            return {"tests": [{"test_id": "T1", "measurement": "verification workload",
                               "focal_prediction": "exposure precedes increased verification workload",
                               "rival_id": "R1", "rival_prediction": "workload rises before or independently of exposure",
                               "inconclusive": "timing is too coarse", "decision_consequence": "retain both explanations",
                               "existing_data_possible": True}], "limitations": ["Synthetic fixture."]}
        if role == "theoretical_contribution_editor":
            return {"contribution": "Reframes the association as a bounded verification-workload mechanism.",
                    "strongest_publishable_formulation": "A bounded mechanism proposition plus a rival-discriminating test.",
                    "claims_to_avoid": ["universal causality"], "novelty_status": "unverified",
                    "limitations": ["No live novelty review."]}
        if role in ATTACK_ROLES:
            strength = "moderate" if role == "support_builder" and any(e["direction"] == "supports" for e in evidence) else "not_applicable"
            findings = ["Contrary evidence retained."] if role == "falsifier" and any(e["direction"] == "challenges" for e in evidence) else []
            return {"summary": "Deterministic fixture", "findings": findings,
                    "support_strength": strength, "limitations": ["No semantic scientific judgement."]}
        if role in GATE_ROLES or role == "comparative_reviewer":
            relevant = codes if role in {"methods_verifier", "statistics_verifier", "evidence_verifier", "comparative_reviewer"} else []
            answer = {"verdict": "reject" if relevant else "accept",
                      "first_failing_step": relevant[0] if relevant else None,
                      "confirmed_steps": [] if relevant else ["fixture_structure"],
                      "findings": relevant, "codes": relevant}
            if role == "evidence_verifier":
                answer["support_strength"] = "moderate" if any(e["direction"] == "supports" for e in evidence) else "none"
            if role == "publication_verifier":
                answer["criteria"] = {"contribution": .6, "novelty_positioning": .5, "discriminating_test": .7, "scope_precision": .9, "robustness": .6}
            return answer
        if role == "proposition_repair":
            revised = copy.deepcopy(prop)
            revised["proposition_id"] += "R1"
            revised["statement"] = "Within the frozen scope, evidence is compatible with a bounded association; mechanism remains unresolved."
            revised["claim_type"] = "associational"
            revised["publishability"] = {"contribution": .55, "discriminating_test": .8, "scope_precision": 1.0, "robustness": .7}
            return {"proposition": revised}
        raise ContractError("Unsupported challenge role")
