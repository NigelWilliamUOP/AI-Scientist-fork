"""Evidence-bound ideation before the existing social-science challenge harness.

Original implementation inspired by IdeaScientist's stage contracts. Imported
read receipts and search traces are assertions, not authenticated retrieval.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from .core import ContractError, Denied, Ledger, code_fingerprint, digest, instant, safe_id

VERSION = "social-science-ideation-0.2"
CONTRIBUTIONS = {"mechanism", "measurement", "boundary_condition", "replication",
                 "theory_discrimination", "method", "institutional_explanation"}
VIEWS = {"problem_definition", "challenge", "intuition", "solution"}
ROLE_SPECS = {
    "ideation_gap_finder": """Find one specific evidence-grounded gap on the assigned axis. Explain what closest studies already cover and where their explanation, measurement, boundary or method falls short. Measurement, replication, boundary conditions and institutional explanations are valid contributions. Missing data or a new setting alone is not a demonstrated gap. Return {outcome:gap|no_gap|blocked, gap:{gap_id,axis,statement,contribution_type,near_miss_ids:[...],supports:[...] } or null, reason:...}. Normally use two full-text near misses; a one-source gap needs single_source_rationale. Do not suggest the solution. Receipts have paper_id,version,goal,locator,answer_text,claim,kind (mechanism|context).""",
    "ideation_blind_baseline": """From ONLY the question, selected gap and result-masked near-miss methods, derive 1-4 plausible ordinary mechanisms. Do not search or use a candidate or the innovator's answer. Return {proposal_exposed:false,mechanisms:[{mechanism_id,mechanism,derivation,supports:[...]}],limitations:[...]}. If you have already seen any candidate for this run, return proposal_exposed:true. This is a pre-candidate comparison, not evidence of global originality.""",
    "ideation_innovator": """Generate exactly ONE short proposition for the supplied gap, never read the frozen baseline. Return {candidate:{proposition_id,statement,claim_type,scope,outcome,falsifier,contribution,contribution_type,mechanism_transfer:{source_mechanism,target_mechanism,mapping:[{source_element,target_element}],required_conditions:[...],failure_risk},predictions:[{prediction,kill_condition}],supports:[...]}}. Supports must include full-text borrowed mechanism and closest in-domain work. Cross-domain transfer is preferred, not mandatory. No invented results, equations, hyperparameters or significance optimisation. Keep frozen scope and outcome.""",
    "ideation_reviewer": """Try to defeat this exact candidate using the supplied disconfirming-search bundle and read receipts. Check novelty within documented coverage, mapping, feasibility, grounding and contribution. Search trace is an input from the acquisition boundary; do not fabricate searches. Return {verdict:survive|revise|reject|unverified,focus:null or novelty|mapping|feasibility|grounding|clarity,strongest_objection:...,reason:...,supports:[...]}. revise requires exactly one focus. Missing load-bearing evidence requires unverified. survive is bounded by the actual searched/read coverage, not global novelty.""",
    "ideation_baseline_comparator": """Compare the candidate with the already frozen independent baseline. Return {assessment:added_mechanism|already_derivable|unverified,reason:...,supports:[...]}. Explain the additional mechanism or why an ordinary derivation already covers it. Baseline difference does not prove novelty or quality. Measurement and replication contributions need not introduce a new mechanism.""",
}


class Searcher(Protocol):
    """Acquisition boundary; must return actual executed or supplied search records."""
    name: str
    def search(self, request: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class IdeationConfig:
    max_role_calls: int = 24
    max_search_operations: int = 18
    search_allowance_per_review: int = 6
    max_candidates: int = 3

    def validate(self) -> None:
        for name, value in asdict(self).items():
            if type(value) is not int or value < 1:
                raise ContractError(name + " must be a positive integer")
        if self.max_candidates > 3 or self.search_allowance_per_review > self.max_search_operations:
            raise ContractError("Ideation candidate/search bounds exceeded")


def text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(label + " requires substantive text")
    return value


def registry(papers: list[dict], cutoff: str) -> dict[str, dict]:
    """Exact-version admission. Unknown version dates are inadmissible here."""
    result = {}
    for original in papers:
        paper = copy.deepcopy(original)
        for field in ("paper_id", "canonical_id", "title", "version", "version_at", "available_at", "access_level",
                      "read_status", "answers", "masked_views", "masking_attestation"):
            if field not in paper:
                raise ContractError("Paper lacks " + field)
        pid = safe_id(paper["paper_id"])
        if pid in result:
            raise Denied("Duplicate paper ID; each ID identifies one exact version")
        text(paper["version"], "version")
        text(paper["canonical_id"], "canonical bibliographic identity")
        text(paper["title"], "paper title")
        if any(p["canonical_id"] == paper["canonical_id"] and p["version"] == paper["version"] for p in result.values()):
            raise Denied("Same exact version cannot be registered under multiple IDs")
        if instant(paper["version_at"]) > instant(cutoff) or instant(paper["available_at"]) > instant(cutoff):
            raise Denied("Post-cutoff exact version: " + pid)
        if paper["access_level"] not in {"full_text", "abstract", "unavailable"}:
            raise ContractError("Invalid access level")
        if paper["read_status"] not in {"read", "unavailable"}:
            raise ContractError("Invalid read status")
        if (paper["read_status"] == "unavailable") != (paper["access_level"] == "unavailable"):
            raise ContractError("Inconsistent read/access status")
        if not isinstance(paper["masked_views"], dict) or set(paper["masked_views"]) != VIEWS:
            raise ContractError("Four result-masked views required")
        for value in paper["masked_views"].values():
            text(value, "masked view")
        if paper["masking_attestation"] != "results_omitted_from_methods_and_views":
            raise Denied("Result masking must be explicitly attested")
        if not isinstance(paper["answers"], list):
            raise ContractError("answers must be a list")
        goals = set()
        for answer in paper["answers"]:
            for field in ("goal", "locator", "answer", "kind", "access_level"):
                text(answer.get(field), field)
            if answer["goal"] in goals or answer["kind"] not in {"mechanism", "context", "result"}:
                raise ContractError("Duplicate goal or invalid answer kind")
            goals.add(answer["goal"])
            if paper["read_status"] != "read" or answer["access_level"] not in {"abstract", "full_text"}:
                raise Denied("Unread evidence cannot supply an answer")
            if answer["access_level"] == "full_text" and paper["access_level"] != "full_text":
                raise Denied("Full-text answer needs full-text access")
            if answer["access_level"] == "abstract" and answer["locator"] != "Abstract":
                raise Denied("Abstract answer must use Abstract locator")
        result[pid] = paper
    return result


def validate_supports(supports: Any, papers: dict[str, dict], *, mechanism: bool = False) -> None:
    if not isinstance(supports, list) or not supports:
        raise ContractError("Evidence supports required")
    mechanism_count = 0
    for support in supports:
        for key in ("paper_id", "version", "goal", "locator", "answer_text", "claim", "kind"):
            text(support.get(key), key)
        paper = papers.get(support["paper_id"])
        if not paper or paper["read_status"] != "read" or support["version"] != paper["version"]:
            raise Denied("Support requires a read exact-version paper")
        answer = next((a for a in paper["answers"] if a["goal"] == support["goal"]), None)
        if not answer or answer["locator"] != support["locator"] or answer["answer"] != support["answer_text"]:
            raise Denied("Support receipt differs from the read answer/locator")
        if support["kind"] not in {"context", "mechanism"}:
            raise ContractError("Invalid support kind")
        if support["kind"] == "mechanism":
            if answer["access_level"] != "full_text" or answer["kind"] != "mechanism":
                raise Denied("Mechanism support needs full-text method answer")
            mechanism_count += 1
    if mechanism and not mechanism_count:
        raise Denied("At least one full-text mechanism support required")


def masked_papers(papers: dict[str, dict], ids: list[str]) -> list[dict]:
    # Explicit projection: no raw body, source outcome, direction, scores or result goals.
    return [{k: copy.deepcopy(papers[pid][k]) for k in
             ("paper_id", "canonical_id", "title", "version", "version_at", "masked_views")} |
            {"answers": copy.deepcopy([a for a in papers[pid]["answers"] if a["kind"] != "result"])}
            for pid in ids]


def validate_search(bundle: dict, papers: dict[str, dict]) -> None:
    if bundle.get("status") not in {"searched", "blocked"}:
        raise ContractError("Search status must be searched or blocked")
    if bundle.get("origin") not in {"operator_supplied", "retrieval_adapter", "synthetic_fixture"}:
        raise ContractError("Search origin must be declared")
    text(bundle.get("coverage"), "search coverage")
    if bundle["status"] == "blocked":
        text(bundle.get("reason"), "block reason")
        return
    queries = bundle.get("queries")
    if not isinstance(queries, list) or not queries:
        raise ContractError("Active disconfirmation requires executed query records")
    for query in queries:
        text(query.get("query"), "query")
        instant(query.get("searched_at"))
        text(query.get("purpose"), "query purpose")
        if not isinstance(query.get("paper_ids"), list) or any(pid not in papers for pid in query["paper_ids"]):
            raise Denied("Search hit lacks exact-version registration")
    if not any(q["purpose"] == "mechanism_plus_problem_disconfirmation" for q in queries):
        raise Denied("Search must try the mechanism with the target problem")


def validate_review(review: dict, candidate: dict, evidence: dict[str, dict]) -> None:
    """A review cannot be reused after candidate or dependency mutation."""
    if review.get("candidate_snapshot") != candidate or review.get("candidate_hash") != digest(candidate):
        raise Denied("Candidate changed after its review")
    if review.get("evidence_snapshot") != evidence or review.get("evidence_hash") != digest(evidence):
        raise Denied("Evidence changed after its review")
    if review.get("verdict") not in {"survive", "revise", "reject", "unverified"}:
        raise ContractError("Invalid ideation review verdict")
    focus = review.get("focus")
    if review["verdict"] == "revise":
        if focus not in {"novelty", "mapping", "feasibility", "grounding", "clarity"}:
            raise ContractError("Revision requires one focus")
    elif focus is not None:
        raise ContractError("Only revision has a focus")
    text(review.get("strongest_objection"), "strongest objection")
    text(review.get("reason"), "review reason")
    validate_search(review["search"], evidence)
    if review["verdict"] != "unverified":
        if review["search"]["status"] != "searched":
            raise Denied("Verified verdict requires active disconfirmation")
        # Every hit must be read before a verified judgement on this search coverage.
        if any(evidence[pid]["read_status"] != "read" for q in review["search"]["queries"] for pid in q["paper_ids"]):
            raise Denied("Unavailable search evidence requires unverified")
        validate_supports(review.get("supports"), evidence, mechanism=True)


class IdeationGuard:
    """Freeze a prelude; review each exact candidate, including repaired candidates."""
    def __init__(self, *, run_id: str, packet: dict, spec: dict, worker: Any,
                 ledger: Ledger, searcher: Searcher | None, config: IdeationConfig):
        self.run_id, self.packet, self.spec = run_id, copy.deepcopy(packet), copy.deepcopy(spec)
        self.worker, self.ledger, self.searcher, self.config = worker, ledger, searcher, config
        self.papers = registry(spec["papers"], packet["cutoff"])
        self.ns = "ideation:" + run_id
        self.fingerprint = digest({"version": VERSION, "runtime": code_fingerprint(), "packet": packet,
                                   "spec": spec, "worker": worker.name,
                                   "searcher": getattr(searcher, "name", None), "config": asdict(config)})
        self.gap, self.baseline = None, None
        self.empirical_hash = None

    def call(self, key: str, role: str, context: dict) -> dict:
        request = {"role": role, "context": context}
        start = self.ledger.get(self.ns + ":calls", key)
        done = self.ledger.get(self.ns + ":answers", key)
        if start is not None:
            if start != request:
                raise Denied("Call key conflicts with frozen task")
            if done is None:
                raise Denied("Interrupted role reservation needs a new run; no automatic retry")
            return copy.deepcopy(done)
        if len(self.ledger.items(self.ns + ":calls")) >= self.config.max_role_calls:
            raise Denied("Ideation role budget exhausted")
        self.ledger.put(self.ns + ":calls", key, request)
        answer = self.worker.complete(role, {"role_contract": ROLE_SPECS[role], **copy.deepcopy(context)})
        if not isinstance(answer, dict):
            raise ContractError("Ideation worker must return a JSON object")
        self.ledger.put(self.ns + ":answers", key, answer, actor="worker:" + self.worker.name)
        return copy.deepcopy(answer)

    def prepare(self) -> dict:
        axis = text(self.spec.get("axis"), "one challenge axis")
        if self.packet["candidate_propositions"] or self.spec.get("prior_candidate_exposure") is not False:
            raise Denied("Cannot backfill a blind baseline after candidate exposure; start a new question-only run")
        question = {k: copy.deepcopy(self.packet[k]) for k in
                    ("question_id", "question", "scope", "cutoff", "data_exposure", "outcome", "unit_of_analysis", "claim_type")}
        self.ledger.put(self.ns, "plan", {"fingerprint": self.fingerprint, "question": question, "axis": axis})
        gap_answer = self.call("gap", "ideation_gap_finder", {
            "question": question, "axis": axis,
            "papers": masked_papers(self.papers, list(self.papers)),
            "discovery_coverage": text(self.spec.get("discovery_coverage"), "discovery coverage"),
        })
        outcome = gap_answer.get("outcome")
        if outcome not in {"gap", "no_gap", "blocked"}:
            raise ContractError("Invalid gap outcome")
        text(gap_answer.get("reason"), "gap reason")
        if outcome != "gap":
            if gap_answer.get("gap") is not None:
                raise Denied("Terminal gap outcome cannot carry a selected gap")
            if outcome == "no_gap":
                assessed = gap_answer.get("assessed_paper_ids")
                if not isinstance(assessed, list) or not assessed:
                    raise Denied("no_gap requires explicit assessed coverage")
                validate_supports(gap_answer.get("supports"), self.papers, mechanism=True)
                covered = {s["paper_id"] for s in gap_answer["supports"] if s["kind"] == "mechanism"}
                if set(assessed) != covered:
                    raise Denied("no_gap assessed papers need full-text support")
            self.ledger.put(self.ns, "terminal", gap_answer)
            return gap_answer
        self.gap = gap_answer.get("gap")
        if not isinstance(self.gap, dict) or self.gap.get("axis") != axis:
            raise ContractError("Gap must bind the one assigned axis")
        safe_id(self.gap["gap_id"])
        text(self.gap.get("statement"), "specific gap")
        if self.gap.get("contribution_type") not in CONTRIBUTIONS:
            raise ContractError("Invalid social-science contribution")
        ids = self.gap.get("near_miss_ids")
        if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids):
            raise ContractError("Distinct near misses required")
        if len(ids) == 1:
            text(self.gap.get("single_source_rationale"), "single-source rationale")
        validate_supports(self.gap.get("supports"), self.papers, mechanism=True)
        covered = {s["paper_id"] for s in self.gap["supports"] if s["kind"] == "mechanism"}
        if not set(ids).issubset(covered) or not covered.issubset(set(ids)):
            raise Denied("Every near miss needs full-text mechanism support")
        if len(ids) > 1 and len({self.papers[pid]["canonical_id"] for pid in ids}) < 2:
            raise Denied("Two versions of one study are not two near-miss studies")
        self.ledger.put(self.ns, "gap", self.gap)
        baseline = self.call("baseline", "ideation_blind_baseline", {
            "question": question, "gap": self.gap,
            "papers": masked_papers(self.papers, ids),
        })
        if baseline.get("proposal_exposed") is not False:
            raise Denied("Baseline worker was exposed to a candidate")
        mechanisms = baseline.get("mechanisms")
        if not isinstance(mechanisms, list) or not 1 <= len(mechanisms) <= 4:
            raise ContractError("Baseline requires 1-4 ordinary mechanisms")
        for mechanism in mechanisms:
            safe_id(mechanism["mechanism_id"])
            text(mechanism.get("mechanism"), "baseline mechanism")
            text(mechanism.get("derivation"), "baseline derivation")
            validate_supports(mechanism.get("supports"), {pid: self.papers[pid] for pid in ids}, mechanism=True)
        self.baseline = {**baseline, "frozen": True, "gap_snapshot": copy.deepcopy(self.gap),
                         "input_snapshot": {"question": question, "papers": masked_papers(self.papers, ids)}}
        # This append precedes every innovator invocation in this API.
        self.ledger.put(self.ns, "baseline", self.baseline)
        return {"outcome": "gap", "gap": self.gap, "reason": gap_answer["reason"]}

    def validate_candidate(self, prop: dict) -> None:
        from .challenge_harness import validate_proposition
        validate_proposition(prop, self.packet)
        for field in ("statement", "falsifier", "contribution"):
            text(prop[field], field)
        if prop["outcome"] != self.packet["outcome"] or prop["scope"] != self.packet["scope"]:
            raise Denied("Initial ideation must retain frozen outcome and scope")
        if prop.get("contribution_type") not in CONTRIBUTIONS:
            raise ContractError("Candidate contribution type required")
        transfer = prop.get("mechanism_transfer", {})
        for field in ("source_mechanism", "target_mechanism", "failure_risk"):
            text(transfer.get(field), field)
        if not isinstance(transfer.get("mapping"), list) or not transfer["mapping"]:
            raise ContractError("Explicit source-to-target mapping required")
        for pair in transfer["mapping"]:
            text(pair.get("source_element"), "source element")
            text(pair.get("target_element"), "target element")
        if not isinstance(transfer.get("required_conditions"), list) or not transfer["required_conditions"]:
            raise ContractError("Transfer conditions required")
        for condition in transfer["required_conditions"]:
            text(condition, "transfer condition")
        if not isinstance(prop.get("predictions"), list) or not prop["predictions"]:
            raise ContractError("Falsifiable predictions required")
        for prediction in prop["predictions"]:
            text(prediction.get("prediction"), "prediction")
            text(prediction.get("kill_condition"), "kill condition")
        validate_supports(prop.get("supports"), self.papers, mechanism=True)
        if not any(s["paper_id"] in self.gap["near_miss_ids"] for s in prop["supports"]):
            raise Denied("Candidate must compare with closest in-domain work")

    def innovate(self, index: int) -> dict:
        if self.baseline is None or not 0 <= index < self.config.max_candidates:
            raise Denied("Candidate requires a preceding baseline within finite bounds")
        self.validate_prelude()
        # The baseline is deliberately absent, including mechanisms and comparison scores.
        answer = self.call("candidate-" + str(index), "ideation_innovator", {
            "question": self.ledger.get(self.ns, "plan")["question"], "gap": self.gap,
            "papers": masked_papers(self.papers, list(self.papers)), "candidate_index": index,
        })
        prop = answer.get("candidate")
        if not isinstance(prop, dict):
            raise ContractError("Exactly one candidate required")
        self.validate_candidate(prop)
        self.ledger.put(self.ns + ":candidates", prop["proposition_id"], prop)
        return prop

    def validate_prelude(self) -> None:
        if self.baseline != self.ledger.get(self.ns, "baseline") or self.gap != self.ledger.get(self.ns, "gap"):
            raise Denied("Frozen gap/baseline changed after admission")
        if self.baseline is None or self.baseline["gap_snapshot"] != self.gap:
            raise Denied("Baseline must bind the exact selected gap")

    def review(self, prop: dict) -> dict:
        self.validate_prelude()
        self.validate_candidate(prop)
        key = digest(prop)
        self.ledger.put(self.ns + ":candidate_ids", prop["proposition_id"], {"candidate_hash": key})
        prior = self.ledger.get(self.ns + ":reviews", key)
        if prior is not None:
            validate_review(prior, prop, prior["evidence_snapshot"])
            for pid, paper in prior["evidence_snapshot"].items():
                if pid in self.papers and self.papers[pid] != paper:
                    raise Denied("Changed paper answer invalidates prior review")
                self.papers[pid] = copy.deepcopy(paper)
            return copy.deepcopy(prior)
        request = {"candidate_snapshot": copy.deepcopy(prop), "candidate_hash": key,
                   "target_question": self.packet["question"], "cutoff": self.packet["cutoff"],
                   "max_search_operations": self.config.search_allowance_per_review}
        if self.searcher is None:
            bundle = {"status": "blocked", "origin": "operator_supplied", "queries": [],
                      "coverage": "No disconfirming search supplied", "reason": "Search acquisition unavailable"}
        else:
            reservations = self.ledger.items(self.ns + ":search_reservations")
            spent = sum(v["allowance"] for _, v in reservations)
            if self.ledger.get(self.ns + ":search_reservations", key) is not None:
                raise Denied("Interrupted search reservation cannot be silently retried")
            if spent + self.config.search_allowance_per_review > self.config.max_search_operations:
                bundle = {"status": "blocked", "origin": "operator_supplied", "queries": [],
                          "coverage": "Search budget exhausted", "reason": "Reserved allowances remain spent"}
            else:
                self.ledger.put(self.ns + ":search_reservations", key,
                                {"allowance": self.config.search_allowance_per_review, "request": request})
                bundle = copy.deepcopy(self.searcher.search(copy.deepcopy(request)))
                if bundle.get("candidate_hash") != key:
                    raise Denied("Disconfirming search must bind the exact candidate")
                for pid, paper in registry(bundle.pop("papers", []), self.packet["cutoff"]).items():
                    if pid in self.papers and self.papers[pid] != paper:
                        raise Denied("Existing paper/version receipt cannot be changed")
                    self.papers[pid] = paper
                if len(bundle.get("queries", [])) > self.config.search_allowance_per_review:
                    raise Denied("Search exceeded reserved operation allowance")
        validate_search(bundle, self.papers)
        blocked = bundle["status"] == "blocked" or any(
            self.papers[pid]["read_status"] != "read" for q in bundle.get("queries", []) for pid in q["paper_ids"])
        if blocked:
            verdict = {"verdict": "unverified", "focus": None, "supports": [],
                       "strongest_objection": "Disconfirming search or load-bearing source access is incomplete.",
                       "reason": bundle.get("reason", "A search hit could not be read")}
        else:
            verdict = self.call("review-" + key, "ideation_reviewer", {
                "candidate": prop, "gap": self.gap, "search": bundle,
                "papers": list(self.papers.values()),
            })
        review = {**verdict, "candidate_snapshot": copy.deepcopy(prop), "candidate_hash": key,
                  "evidence_snapshot": copy.deepcopy(self.papers), "evidence_hash": digest(self.papers),
                  "search": bundle, "empirical_evidence_hash": self.empirical_hash,
                  "coverage_status": "synthetic_only" if bundle["origin"] == "synthetic_fixture" else "asserted_search_and_read_receipts"}
        validate_review(review, prop, self.papers)
        comparison = {"assessment": "unverified", "reason": "Current candidate has not survived review", "supports": []}
        if review["verdict"] == "survive":
            comparison = self.call("comparison-" + key, "ideation_baseline_comparator", {
                "candidate": prop, "baseline": self.baseline, "review": verdict,
                "papers": list(self.papers.values()),
            })
            if comparison.get("assessment") not in {"added_mechanism", "already_derivable", "unverified"}:
                raise ContractError("Invalid baseline comparison")
            text(comparison.get("reason"), "baseline comparison reason")
            validate_supports(comparison.get("supports"), self.papers, mechanism=True)
        review["baseline_comparison"] = comparison
        self.ledger.put(self.ns + ":reviews", key, review)
        return copy.deepcopy(review)


def run_ideation_challenge(packet: dict, spec: dict, worker: Any, ledger: Ledger, *,
                           run_id: str, searcher: Searcher | None = None,
                           config: IdeationConfig | None = None) -> dict:
    """Generate one intuition at a time; send survivors to the existing harness."""
    from .challenge_harness import ChallengeConfig, run_challenge, validate_question_packet
    safe_id(run_id)
    cfg = config or IdeationConfig()
    cfg.validate()
    packet = validate_question_packet(copy.deepcopy(packet))
    guard = IdeationGuard(run_id=run_id, packet=packet, spec=spec, worker=worker,
                          ledger=ledger, searcher=searcher, config=cfg)
    old = ledger.get("ideation_plans", run_id)
    if old is not None and old["fingerprint"] != guard.fingerprint:
        raise Denied("Ideation run ID conflicts with frozen inputs/code/configuration")
    ledger.put("ideation_plans", run_id, {"fingerprint": guard.fingerprint})
    final = ledger.get("ideation_reports", run_id)
    if final is not None:
        return final
    preparation = guard.prepare()
    results = []
    if preparation["outcome"] == "gap":
        for index in range(cfg.max_candidates):
            prop = guard.innovate(index)
            generated = copy.deepcopy(packet)
            generated["candidate_propositions"] = [prop]
            guard.empirical_hash = digest(generated["evidence"])
            result = run_challenge(generated, worker, ledger, run_id=f"{run_id}-c{index + 1}",
                                   config=ChallengeConfig(max_propositions=1), ideation_guard=guard)
            results.append(result)
            if result["selected_status"] == "survives_current_challenge" or result["selected_ideation_review"]["verdict"] == "unverified":
                break
    status = preparation["outcome"] if not results else (
        "survives_current_challenge" if any(r["selected_status"] == "survives_current_challenge" for r in results)
        else "unverified" if any(r["selected_ideation_review"]["verdict"] == "unverified" for r in results)
        else "no_surviving_candidate")
    report = {"version": VERSION, "run_id": run_id, "status": status,
              "gap": guard.gap, "baseline": guard.baseline, "challenge_reports": results,
              "role_calls_reserved": len(ledger.items(guard.ns + ":calls")),
              "role_call_reservation_scope": "Ideation stages only; downstream challenge rounds are separately bounded and share provider Session limits when configured.",
              "search_operations_reserved": sum(v["allowance"] for _, v in ledger.items(guard.ns + ":search_reservations")),
              "scientific_validity_established": False,
              "limits": ["Receipt equality does not establish semantic citation support.",
                         "Baseline order is enforced by this API and local ledger; external chronology is not authenticated.",
                         "Result masking is an explicit projection and supplied attestation; model training hindsight remains.",
                         "Baseline derivability and searched novelty are separate from journal readiness."]}
    ledger.put("ideation_reports", run_id, report)
    return report
