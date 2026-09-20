"""Three separately invocable lifecycle agents over shared trusted components.

Generated Python is never executed. The initial Study Producer deliberately
restricts execution to two audited descriptive methods. Extend METHODS through
reviewed code, not model-supplied imports or shell commands.
"""
from __future__ import annotations

import math
import statistics
from typing import Any

from .core import (BudgetStopped, ContractError, Denied, EvidenceBroker, Ledger,
                   canonical, code_fingerprint, digest, instant, number, portfolio_view, require,
                   result, safe_id, select_portfolio, select_sources, source_key)
from .providers import Session

METHODS = {"describe", "ols"}
EXTENSIONS = {"new_application", "measurement_improvement", "boundary_test", "contradiction", "mechanism_discrimination"}


def analyse(plan: dict, source: dict) -> dict:
    require(plan, {"method", "source_key"})
    method = plan["method"]
    if method not in METHODS:
        raise Denied("Method is outside the audited method registry")
    rows = source["payload"].get("rows")
    if not isinstance(rows, list) or not rows or len(rows) > 100_000:
        raise ContractError("Need 1-100,000 structured data rows")
    columns = [plan["column"]] if method == "describe" else [plan["x"], plan["y"]]
    complete = [[number(row[c]) for c in columns] for row in rows
                if all(c in row and row[c] is not None for c in columns)]
    if not complete:
        raise ContractError("No complete finite observations for the selected columns")
    if method == "describe":
        values = [r[0] for r in complete]
        calculation = {"n": len(values), "missing_rows": len(rows) - len(values),
            "mean": statistics.mean(values), "minimum": min(values), "maximum": max(values),
            "sample_sd": statistics.stdev(values) if len(values) > 1 else None}
    else:
        if len(complete) < 3:
            raise ContractError("OLS requires at least three complete observations")
        x, y = zip(*complete)
        xbar, ybar = statistics.mean(x), statistics.mean(y)
        ssx = sum((v - xbar)**2 for v in x)
        if ssx <= 0:
            raise ContractError("OLS exposure has no variation")
        slope = sum((a - xbar) * (b - ybar) for a, b in complete) / ssx
        intercept = ybar - slope * xbar
        residual = sum((b - intercept - slope * a)**2 for a, b in complete)
        ssy = sum((v - ybar)**2 for v in y)
        calculation = {"n": len(complete), "missing_rows": len(rows) - len(complete),
            "slope": slope, "intercept": intercept, "residual_sum_squares": residual,
            "r_squared": 1 - residual / ssy if ssy else None,
            "identification": "descriptive_association_only"}
    canonical(calculation)
    return {"result": calculation, "analysis_hash": digest([plan, source["sha256"], calculation]),
            "method_version": "builtin-1", "source_sha256": source["sha256"], "source_kind": source["kind"]}


def manuscript(document: dict, status: str) -> str:
    parts = ["# " + document["title"], "Status: " + status + ". Independent journal review: not evaluated."]
    for key, text in document["sections"].items():
        parts += ["## " + key.replace("_", " ").title(), text]
    parts += ["## Claim ledger", canonical(document["claims"])]
    return "\n\n".join(parts) + "\n"


class StudyProducer:
    agent_id = "study_producer"

    def __init__(self, ledger: Ledger, session: Session):
        self.ledger, self.session = ledger, session

    def run(self, brief: dict, sources: list[dict], *, synthetic: bool = False) -> dict:
        require(brief, {"study_id", "title", "question", "target_journal", "allowed_methods", "source_ids", "cutoff"})
        ident = safe_id(brief["study_id"])
        instant(brief["cutoff"])
        if not brief["allowed_methods"] or not set(brief["allowed_methods"]).issubset(METHODS):
            raise Denied("The brief must specify audited methods only")
        self.ledger.put("study_briefs", ident, brief, "operator")
        authorised = [s for s in sources if s.get("source_id") in brief["source_ids"]]
        eligible, excluded = select_sources(authorised, brief["cutoff"], allow_synthetic=synthetic)
        self.ledger.put("study_input_manifests", ident, {"source_keys": [source_key(s) for s in eligible], "excluded": excluded})
        cached = self.ledger.get("study_results", ident)
        if cached is not None:
            return cached
        broker = EvidenceBroker(eligible, self.ledger)
        base = {"study_id": ident, "excluded_sources": excluded, "evidence_mode": "synthetic_fixture" if synthetic else "supplied_secondary_evidence"}
        if set(brief["source_ids"]) - {s["source_id"] for s in eligible}:
            return self._finish(ident, result(self.agent_id, "blocked_data", **base, reason="Required evidence missing or ineligible"))
        try:
            context = {"brief": brief, "sources": broker.context()}
            proposal = self.session.ask("study_plan", context)
            if proposal.get("abstain"):
                return self._finish(ident, result(self.agent_id, "abstained", **base, reason=proposal["abstain"]))
            require(proposal, {"analysis", "rationale"})
            plan = proposal["analysis"]
            if plan.get("method") not in brief["allowed_methods"]:
                raise Denied("The worker changed the authorised analysis scope")
            source = broker.read(plan.get("source_key", ""))
            self.ledger.put("study_designs", ident, proposal, self.agent_id)
            calculation = analyse(plan, source)
            replicated = analyse(plan, source)
            if calculation != replicated:
                raise ContractError("Arithmetic replay mismatch")
            self.ledger.put("study_analyses", ident, calculation, self.agent_id)
            write_context = {**context, "plan": plan, "analysis": calculation, "synthetic": source["kind"] == "synthetic"}
            draft = self.session.ask("study_write", write_context)
            require(draft, {"title", "sections", "claims", "fatal_defects"})
            require(draft["sections"], {"abstract", "methods", "results", "discussion", "limitations"})
            if not isinstance(draft["claims"], list) or not draft["claims"]:
                raise ContractError("A manuscript candidate requires traceable claims")
            if not isinstance(draft["fatal_defects"], list) or any(not isinstance(v, str) for v in draft["sections"].values()):
                raise ContractError("Malformed manuscript/defect record")
            defects = list(draft["fatal_defects"])
            claim_ids = []
            for claim in draft["claims"]:
                require(claim, {"claim_id", "text", "kind", "source_keys", "analysis_hash", "interpretation", "excluded_interpretation"})
                claim_ids.append(claim["claim_id"])
                if not claim["source_keys"] or set(claim["source_keys"]) != {plan["source_key"]}:
                    defects.append("Claim does not cite the analysed evidence")
                for key in claim["source_keys"]:
                    broker.read(key)
                expected_kind = "synthetic" if source["kind"] == "synthetic" else "derived"
                if claim["kind"] != expected_kind:
                    defects.append("Claim changed its evidence category")
                if claim["analysis_hash"] != calculation["analysis_hash"]:
                    defects.append("Claim cites an unknown analysis")
                if claim["interpretation"] != "descriptive":
                    defects.append("The executed methods do not identify causality")
            if len(set(claim_ids)) != len(claim_ids):
                defects.append("Duplicate claim identifiers")
            self.ledger.put("study_drafts", ident, draft, self.agent_id)
            critique = self.session.ask("study_critic", {**write_context, "candidate": draft})
            require(critique, {"fatal_defects", "comments"})
            if not isinstance(critique["fatal_defects"], list):
                raise ContractError("Malformed model critique")
            defects += critique["fatal_defects"]
            status = "abstained" if defects else "review_candidate"
            outcome = result(self.agent_id, status, **base, analysis=calculation, design=proposal,
                candidate=draft, manuscript_markdown=manuscript(draft, status), defects=defects,
                arithmetic_replay="passed_same_implementation", independent_replication="not_run",
                novelty_review="not_completed", semantic_claim_verification="requires_review",
                model_critique=critique, portfolio_amendment_status="proposal_only")
            return self._finish(ident, outcome)
        except BudgetStopped as exc:
            # Do not freeze a terminal study result: an authorised new budget can
            # resume in a new workspace using the exported checkpoints.
            return result(self.agent_id, "stopped_budget", **base, reason=str(exc), resources=self.session.resources())

    def _finish(self, ident: str, outcome: dict) -> dict:
        outcome["resources"] = self.session.resources()
        self.ledger.put("study_results", ident, outcome, self.agent_id)
        return outcome


class ProgrammeSteward:
    agent_id = "programme_steward"

    def __init__(self, ledger: Ledger, session: Session | None = None):
        self.ledger, self.session = ledger, session

    def initialise(self, baseline: dict) -> dict:
        require(baseline, {"programme_id", "title", "locked_at", "protocol_status", "outcomes", "hypotheses", "predictions"})
        ident = safe_id(baseline["programme_id"])
        locked = instant(baseline["locked_at"])
        if baseline["protocol_status"] not in {"draft", "internally_locked", "registered"}:
            raise ContractError("Unknown protocol status")
        if baseline["protocol_status"] == "registered" and not baseline.get("registration_receipt"):
            raise Denied("A registration status requires an operator-supplied receipt; no registration is performed")
        hypothesis_ids = {h["hypothesis_id"] for h in baseline["hypotheses"]}
        if len(hypothesis_ids) < 2:
            raise ContractError("Specify at least two competing hypotheses")
        prediction_ids = set()
        for prediction in baseline["predictions"]:
            require(prediction, {"prediction_id", "hypothesis_id", "series_id", "period", "issued_at", "interval"})
            if prediction["prediction_id"] in prediction_ids:
                raise ContractError("Duplicate prediction ID")
            prediction_ids.add(prediction["prediction_id"])
            if prediction["hypothesis_id"] not in hypothesis_ids:
                raise ContractError("Prediction has no registered rival hypothesis")
            if instant(prediction["issued_at"]) > locked:
                raise ContractError("A frozen baseline cannot contain later predictions")
            lo, hi = prediction["interval"]
            if number(lo) > number(hi):
                raise ContractError("Invalid prediction interval")
        self.ledger.put("programme_baselines", ident, baseline, "operator")
        return result(self.agent_id, "awaiting_release", programme_id=ident, baseline_hash=digest(baseline),
            protocol_status=baseline["protocol_status"], registration_receipt_verification="operator_asserted_not_independently_checked")

    def amend(self, programme_id: str, amendment: dict) -> dict:
        if self.ledger.get("programme_baselines", programme_id) is None:
            raise ContractError("Unknown programme")
        require(amendment, {"amendment_id", "reason", "proposed_at", "change"})
        instant(amendment["proposed_at"])
        record = {**amendment, "status": "exploratory_proposal", "changes_frozen_baseline": False}
        self.ledger.put("amendments:" + programme_id, safe_id(amendment["amendment_id"]), record, "operator")
        return record

    def update(self, programme_id: str, sources: list[dict], cutoff: str, *, synthetic: bool = False) -> dict:
        baseline = self.ledger.get("programme_baselines", programme_id)
        if baseline is None:
            raise ContractError("Initialise the programme first")
        if instant(cutoff) < instant(baseline["locked_at"]):
            raise Denied("Update cutoff precedes the frozen baseline")
        # All vintages are needed to distinguish the earliest release from a revision.
        eligible, excluded = select_sources(sources, cutoff, allow_synthetic=synthetic, latest=False)
        signature = digest([code_fingerprint(), digest(baseline), cutoff, [source_key(s) for s in eligible], excluded,
                            self.session.provider.name if self.session else "deterministic-steward"])
        cached = self.ledger.get("programme_updates:" + programme_id, signature)
        if cached is not None:
            return cached
        outcomes = {o["series_id"]: o for o in baseline["outcomes"]}
        additions, ignored = [], []
        namespace = "observations:" + programme_id
        for source in sorted(eligible, key=lambda s: (instant(s["available_at"]), source_key(s))):
            for observation in source["payload"].get("observations", []):
                require(observation, {"series_id", "period", "frequency", "unit", "value"})
                definition = outcomes.get(observation["series_id"])
                if not definition:
                    ignored.append({"source_key": source_key(source), "reason": "series_not_in_frozen_protocol"})
                    continue
                if any(observation.get(k) != definition.get(k) for k in ("frequency", "unit")):
                    ignored.append({"source_key": source_key(source), "reason": "frequency_or_unit_mismatch"})
                    continue
                number(observation["value"])
                period_key = digest([observation["series_id"], observation["period"], observation["frequency"], observation["unit"]])
                # Source metadata changes do not fabricate a new measurement vintage.
                key = digest([period_key, source["available_at"], observation["value"], source["kind"]])
                with self.ledger.transaction():
                    existing = self.ledger.get(namespace, key)
                    if existing is not None:
                        if existing.get("update_signature") == signature:
                            additions.append(existing)
                        continue
                    prior = [v for _, v in self.ledger.items(namespace) if v["period_key"] == period_key]
                    same_date = [v for v in prior if v["available_at"] == source["available_at"]]
                    if any(v["observation"]["value"] != observation["value"] for v in same_date):
                        raise Denied("Conflicting outcome values at one release timestamp")
                    change = "new_period" if not prior else "revision"
                    record = {"period_key": period_key, "observation": observation, "source_key": source_key(source),
                        "available_at": source["available_at"], "kind": source["kind"], "change": change, "update_signature": signature}
                    self.ledger._put(namespace, key, record, self.agent_id)
                    additions.append(record)
        # Historical cutoffs never see later observations already present in the ledger.
        history = [v for _, v in self.ledger.items(namespace) if instant(v["available_at"]) <= instant(cutoff)]
        latest = {}
        for value in history:
            key = value["period_key"]
            if key not in latest or instant(value["available_at"]) > instant(latest[key]["available_at"]):
                latest[key] = value
        prediction_tests = []
        for prediction in baseline["predictions"]:
            matches = [v for v in latest.values() if v["observation"]["series_id"] == prediction["series_id"]
                       and v["observation"]["period"] == prediction["period"]]
            for value in matches:
                earliest = min(instant(v["available_at"]) for v in history if v["period_key"] == value["period_key"])
                is_prospective = instant(prediction["issued_at"]) < earliest
                lo, hi = prediction["interval"]
                prediction_tests.append({"prediction_id": prediction["prediction_id"], "hypothesis_id": prediction["hypothesis_id"],
                    "source_key": value["source_key"], "within_declared_interval": lo <= value["observation"]["value"] <= hi,
                    "timing": "prospective_to_first_supplied_release" if is_prospective else "retrospective_not_confirmatory",
                    "evidence_kind": value["kind"], "empirical_confirmation": False,
                    "interpretation": "Synthetic discrimination only" if value["kind"] == "synthetic" else
                                      "Forecast compatibility; not causal mechanism confirmation"})
        status = "update_candidate" if additions else "no_eligible_update"
        outcome = result(self.agent_id, status, programme_id=programme_id, cutoff=cutoff,
            baseline_hash=digest(baseline), changes=additions, excluded_sources=excluded, ignored_observations=ignored,
            independent_periods=len(latest), admitted_vintages=len(history), prediction_tests=prediction_tests,
            prediction_history="unchanged", archive_coverage="limited_to_supplied_vintages",
            evidence_mode="synthetic_fixture" if synthetic else "supplied_secondary_evidence",
            external_model_calls=0, billed_model_usd=0)
        if self.session is not None and additions:
            context = {"cutoff": cutoff, "baseline": baseline, "changes": additions,
                "independent_periods": len(latest), "prediction_tests": prediction_tests,
                "sources": EvidenceBroker(eligible, self.ledger).context()}
            try:
                summary = self.session.ask("programme_review", context)
            except BudgetStopped as exc:
                return {**outcome, "status": "stopped_budget", "reason": str(exc),
                        "deterministic_update_preserved": True, "resources": self.session.resources()}
            require(summary, {"evidence_delta", "unresolved_questions", "next_measurements", "source_keys", "empirical_confirmation"})
            if summary["empirical_confirmation"] is not False:
                raise Denied("Model interpretation cannot confer empirical mechanism confirmation")
            if not isinstance(summary["source_keys"], list) or not set(summary["source_keys"]).issubset(context["sources"]):
                raise Denied("Programme interpretation cited ineligible evidence")
            outcome.update(model_interpretation=summary, model_interpretation_status="unverified_candidate",
                           resources=self.session.resources())
            outcome.pop("external_model_calls", None)
            outcome.pop("billed_model_usd", None)
        self.ledger.put("programme_updates:" + programme_id, signature, outcome, self.agent_id)
        return outcome


def feasibility(source: dict, claim: dict) -> list[str]:
    """Hard prechecks over archived data dictionaries and actual supplied rows.
    Semantic equivalence and inferential validity still need independent review.
    """
    issues = []
    payload, requirements = source["payload"], claim.get("required_data", {})
    schema, rows = payload.get("schema", {}), payload.get("rows", [])
    if source["kind"] not in {"observed", "derived", "synthetic"}:
        issues.append("source_is_not_measured_or_derived_secondary_data")
    if not payload.get("primary_source", False):
        issues.append("primary_source_not_established")
    if not isinstance(rows, list) or not rows:
        issues.append("no_accessible_secondary_data_rows")
    if not requirements.get("variables"):
        issues.append("parent_data_requirements_incomplete")
    for field in ("variables", "join_keys"):
        required = set(requirements.get(field, []))
        if not required.issubset(set(schema.get(field, []))):
            issues.append(field + "_missing")
        if rows and any(not required.issubset(row) or any(row[v] is None for v in required) for row in rows):
            issues.append(field + "_missing_in_actual_rows")
    for field in ("unit", "population", "geography", "frequency"):
        if field not in requirements:
            issues.append("parent_" + field + "_unspecified")
        elif schema.get(field) != requirements[field]:
            issues.append(field + "_mismatch")
    return sorted(set(issues))


class OpportunityScout:
    agent_id = "opportunity_scout"

    def __init__(self, ledger: Ledger, session: Session):
        self.ledger, self.session = ledger, session

    def run(self, cards: list[dict], sources: list[dict], cutoff: str, *, replay: bool = False,
            synthetic: bool = False, queue_limit: int = 5, retrieval_errors: list[dict] | None = None) -> dict:
        if isinstance(queue_limit, bool) or not isinstance(queue_limit, int) or queue_limit < 1:
            raise ContractError("Queue limit must be a positive integer")
        eligible, exclusions = select_sources(sources, cutoff, replay=replay, allow_synthetic=synthetic)
        portfolio, card_exclusions = select_portfolio(cards, cutoff, replay=replay)
        errors = list(retrieval_errors or [])
        # Malformed or unverifiable inputs are failures of scan coverage, unlike
        # deliberately excluded future evidence, which is normal in replay.
        normal_exclusions = {"published_after_cutoff", "capture_after_cutoff", "portfolio_version_after_cutoff", "synthetic_source_not_authorised"}
        errors += [e for e in exclusions + card_exclusions if e["reason"] not in normal_exclusions]
        if not synthetic and any(c.get("synthetic") for c in portfolio):
            raise Denied("Synthetic portfolio needs explicit fixture mode")
        broker = EvidenceBroker(eligible, self.ledger)
        public_context = {"cutoff": cutoff, "sources": broker.context(), "portfolio": [portfolio_view(c) for c in portfolio]}
        signature = digest([public_context, queue_limit, errors, replay, synthetic, self.session.provider.name])
        cached = self.ledger.get("scout_runs", signature)
        if cached is not None:
            return cached
        base = {"cutoff": cutoff, "replay": replay, "evidence_mode": "synthetic_fixture" if synthetic else "historical_replay" if replay else "supplied_secondary_evidence",
            "exclusions": exclusions, "portfolio_exclusions": card_exclusions,
            "coverage": {"eligible_sources": len(eligible), "eligible_works": len(portfolio), "errors": errors},
            "source_manifest_hash": digest([source_key(s) for s in eligible]),
            "portfolio_manifest_hash": digest([c["sha256"] for c in portfolio]),
            "parametric_hindsight": "not_applicable_deterministic_baseline" if not self.session.provider.remote else "not_eliminated_by_source_cutoffs"}
        if not eligible or not portfolio:
            status = "scan_incomplete" if errors or not portfolio else "no_useful_opportunity"
            return self._finish(signature, result(self.agent_id, status, **base, candidates=[], rejected=[], handovers=[]))
        try:
            proposed = self.session.ask("scout", public_context)
        except BudgetStopped as exc:
            return result(self.agent_id, "stopped_budget", **base, candidates=[], rejected=[], handovers=[], reason=str(exc), resources=self.session.resources())
        require(proposed, {"candidates"})
        if not isinstance(proposed["candidates"], list) or len(proposed["candidates"]) > 200:
            raise ContractError("Worker candidate list is malformed or exceeds 200")
        accepted, rejected, handovers, local_ids = [], [], [], set()
        works = {(c["work_id"], str(c["version"])): c for c in portfolio}
        for candidate in proposed["candidates"]:
            try:
                require(candidate, {"source_key", "work_id", "work_version", "claim_id", "extension_type", "what_changed", "mechanism", "minimum_test"})
                source = broker.read(candidate["source_key"])
                work = works.get((candidate["work_id"], str(candidate["work_version"])))
                if work is None:
                    raise Denied("unknown_or_future_parent_version")
                claim = next((c for c in work["claims"] if c["claim_id"] == candidate["claim_id"]), None)
                if claim is None:
                    raise Denied("unknown_parent_claim")
                if candidate["extension_type"] not in EXTENSIONS:
                    raise ContractError("Unknown extension class")
                test = candidate["minimum_test"]
                require(test, {"analysis", "comparator", "rival_predictions", "falsifier", "max_usd", "human_minutes"})
                if not all(isinstance(test[k], str) and test[k].strip() for k in ("analysis", "comparator", "falsifier")):
                    raise ContractError("Incomplete informative test")
                if not isinstance(test["rival_predictions"], list) or len(test["rival_predictions"]) < 2 or any(not isinstance(p, str) or not p.strip() for p in test["rival_predictions"]):
                    raise ContractError("Need at least two explicit rival predictions")
                if number(test["max_usd"]) < 0 or number(test["human_minutes"]) < 0:
                    raise ContractError("Pilot resource estimates cannot be negative")
                issues = feasibility(source, claim)
                if issues:
                    rejected.append({"candidate": candidate, "reasons": issues, "status": "watch_data_gap"})
                    continue
                # Stable across repeated releases containing identical dataset bytes.
                identity = digest([candidate["work_id"], str(candidate["work_version"]), candidate["claim_id"], source["sha256"], candidate["extension_type"]])
                if identity in local_ids or self.ledger.get("opportunities", identity) is not None:
                    rejected.append({"candidate": candidate, "reasons": ["duplicate_opportunity"], "status": "duplicate"})
                    continue
                local_ids.add(identity)
                owner = claim.get("owner_programme")
                destination = "verification_queue" if candidate["extension_type"] == "contradiction" else "programme_steward" if owner else "study_producer"
                revisions = [v for _, v in self.ledger.items("scout_seen_sources") if v["source_id"] == source["source_id"] and v["sha256"] != source["sha256"]]
                accepted.append({**candidate, "opportunity_id": identity, "destination": destination,
                    "programme_id": owner, "source_revision": bool(revisions), "data_prechecks": "passed",
                    "semantic_comparability": "requires_verification", "candidate_status": "proposed_not_accepted",
                    "pilot_authorised": False, "source_kind": source["kind"], "source_available_at": source["available_at"]})
            except (ContractError, KeyError, TypeError) as exc:
                rejected.append({"candidate": candidate, "reasons": [str(exc)], "status": "rejected"})
        accepted.sort(key=lambda c: (c["extension_type"] != "contradiction", c["opportunity_id"]))
        deferred, accepted = accepted[queue_limit:], accepted[:queue_limit]
        with self.ledger.transaction():
            for candidate in accepted:
                ident = candidate["opportunity_id"]
                self.ledger._put("opportunities", ident, candidate, self.agent_id)
                handover = {"opportunity_id": ident, "destination": candidate["destination"], "programme_id": candidate["programme_id"], "status": "queued_not_executed"}
                self.ledger._put("handovers", ident, handover, self.agent_id)
                handovers.append(handover)
            for key, source in broker.context().items():
                self.ledger._put("scout_seen_sources", key, {"source_id": source["source_id"], "sha256": source["sha256"]}, self.agent_id)
            status = "scan_incomplete" if errors else "candidate_for_review" if accepted else "watch_data_gap" if any(r["status"] == "watch_data_gap" for r in rejected) else "no_useful_opportunity"
            outcome = result(self.agent_id, status, **base, candidates=accepted, rejected=rejected, deferred=deferred,
                handovers=handovers, resources=self.session.resources())
            self.ledger._put("scout_runs", signature, outcome, self.agent_id)
        return outcome

    def _finish(self, signature: str, outcome: dict) -> dict:
        outcome["resources"] = self.session.resources()
        self.ledger.put("scout_runs", signature, outcome, self.agent_id)
        return outcome
