"""Read-only, bounded research assurance. No network, shell or generated code.

A verified defect means a reproducible failure of a frozen check, not a verified
scientific conclusion. Human/model assertions and source metadata may be wrong.
"""
from __future__ import annotations

import json
import math
import re
import statistics
from typing import Any

from .core import (ContractError, Denied, Ledger, ReconciliationRequired, canonical,
                   code_fingerprint, digest, instant, number, safe_id,
                   select_sources, select_portfolio, portfolio_view, source_key, source_view)

VERSION = "assurance-0.1"
AGENTS = {"study_producer", "programme_steward", "opportunity_scout"}
OPERATIONS = {"exact_quote", "value_equal", "mean", "distinct_periods", "inference", "semantic"}
CLAIM_FIELDS = {"claim_id", "text", "kind", "source_keys", "analysis_hash", "interpretation",
                "excluded_interpretation", "assumptions", "section_ids", "asserted", "quote"}
RESERVED = {"SRO-001", "CEMENT-001"}
FORBIDDEN_KEYS = {"gold", "gold_label", "expected_answer", "expected_label", "answer_key",
                  "adjudication", "adjudications", "private_labels", "holdout", "protected_answers"}
CHECK_FIELDS = {"check_id", "claim_id", "operation", "source_key", "pointer", "field",
                "atol", "rtol", "consequential", "assumption", "reason"}
PACKET_FIELDS = {"version", "work_id", "parent_id", "agent", "cutoff", "knowledge_as_of",
                 "replay", "synthetic", "sources", "claims", "checks", "sections", "lineage",
                 "sha256"}


def clone(value: Any) -> Any:
    return json.loads(canonical(value))


def exact_keys(obj: dict, allowed: set[str], required: set[str] | None = None) -> None:
    if not isinstance(obj, dict) or set(obj) - allowed or not (required or allowed).issubset(obj):
        raise ContractError("Unexpected or missing schema fields")


def reject_answers(value: Any) -> None:
    """Defence in depth, not semantic data-loss prevention or an OS sandbox."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in FORBIDDEN_KEYS:
                raise Denied("Evaluator-only fields cannot enter reviewer context")
            reject_answers(item)
    elif isinstance(value, list):
        for item in value:
            reject_answers(item)


def boundary(work_id: str, parent_id: str, synthetic: bool) -> None:
    for ident in (work_id, parent_id):
        safe_id(ident)
        if ident.upper() in RESERVED:
            raise Denied("Reserved study is outside this development capability")
        if ident.upper() == "MISSOURI-001" and not synthetic:
            raise Denied("MISSOURI-001 remains synthetic calibration only")


def integer(value: Any, low: int = 0, high: int = 1000) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ContractError("Integer limit outside permitted bounds")
    return value


def pointer(value: Any, path: str) -> Any:
    """A JSON pointer, never a filename, URL, Python expression or shell command."""
    if not isinstance(path, str) or (path and not path.startswith("/")) or len(path) > 500:
        raise ContractError("Invalid JSON pointer")
    if not path:
        return value
    for item in path[1:].split("/"):
        if re.search(r"~(?![01])", item):
            raise ContractError("Invalid JSON pointer escape")
        item = item.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict):
            value = value[item]
        elif isinstance(value, list) and re.fullmatch(r"0|[1-9][0-9]*", item):
            value = value[int(item)]
        else:
            raise KeyError(path)
    return value


def quote_anchor(text: str, quote: str) -> dict:
    if not isinstance(text, str) or not isinstance(quote, str) or not quote.strip():
        return {"match": "unanchored", "start": None, "end": None}
    start = text.find(quote)
    if start >= 0:
        return {"match": "exact", "start": start, "end": start + len(quote)}
    if " ".join(quote.split()) in " ".join(text.split()):
        return {"match": "approximate_whitespace", "start": None, "end": None}
    return {"match": "not_found", "start": None, "end": None}


def freeze_packet(*, work_id: str, parent_id: str, agent: str, cutoff: str,
                  knowledge_as_of: str, sources: list[dict], claims: list[dict],
                  checks: list[dict], sections: dict | None = None,
                  replay: bool = False, synthetic: bool = False,
                  lineage: dict | None = None) -> tuple[dict, list[dict]]:
    """Return a detached, checksummed reviewer packet and a SEPARATE exclusion log."""
    boundary(work_id, parent_id, synthetic)
    if type(replay) is not bool or type(synthetic) is not bool or agent not in AGENTS:
        raise ContractError("Invalid agent or evidence mode")
    if instant(knowledge_as_of) > instant(cutoff):
        raise Denied("Artifact knowledge is later than the inherited cutoff")
    for source in sources:
        boundary(source.get("source_id", ""), source.get("source_id", ""), synthetic)
    admitted, excluded = select_sources(sources, cutoff, replay=replay,
                                        allow_synthetic=synthetic, latest=False)
    normal = {"published_after_cutoff", "capture_after_cutoff"}
    if any(item["reason"] not in normal for item in excluded):
        raise Denied("Invalid, conflicting or unauthorised source admission")
    body = {"version": VERSION, "work_id": work_id, "parent_id": parent_id,
            "agent": agent, "cutoff": cutoff, "knowledge_as_of": knowledge_as_of,
            "replay": replay, "synthetic": synthetic,
            "sources": {source_key(s): {**source_view(s),
                         "archive_verified": False,
                         "archive_asserted": bool(s.get("archive_proof"))} for s in admitted},
            "claims": claims, "checks": checks, "sections": sections or {},
            "lineage": lineage or {}}
    body = clone(body)
    body["sha256"] = digest(body)
    validate_packet(body)
    return body, excluded


def validate_packet(packet: dict) -> None:
    exact_keys(packet, PACKET_FIELDS)
    if packet["sha256"] != digest({k: v for k, v in packet.items() if k != "sha256"}):
        raise Denied("Frozen packet checksum mismatch")
    if packet["version"] != VERSION or packet["agent"] not in AGENTS:
        raise ContractError("Unsupported packet version or agent")
    if type(packet["synthetic"]) is not bool or type(packet["replay"]) is not bool:
        raise ContractError("Invalid evidence mode")
    boundary(packet["work_id"], packet["parent_id"], packet["synthetic"])
    end = instant(packet["cutoff"])
    if instant(packet["knowledge_as_of"]) > end:
        raise Denied("Artifact contains future knowledge")
    if len(canonical(packet).encode()) > 2_000_000:
        raise ContractError("Reviewer packet exceeds 2 MB")
    reject_answers(packet)
    if not isinstance(packet["sources"], dict) or not isinstance(packet["sections"], dict):
        raise ContractError("Malformed source/section map")
    for key, source in packet["sources"].items():
        boundary(source.get("source_id", ""), source.get("source_id", ""), packet["synthetic"])
        exact_keys(source, {"source_id", "version", "available_at", "captured_at", "kind",
                            "access", "locator", "payload", "sha256", "archive_verified", "archive_asserted"})
        if source_key(source) != key or digest(source["payload"]) != source["sha256"]:
            raise Denied("Source content or identity changed")
        if source["access"] not in {"public", "authorised", "synthetic"}:
            raise Denied("Source access not authorised")
        if source["kind"] not in {"observed", "derived", "assumed", "synthetic", "literature_inference", "unavailable"}:
            raise ContractError("Invalid source kind")
        if (source["kind"] == "synthetic") != (source["access"] == "synthetic"):
            raise Denied("Synthetic label mismatch")
        if source["kind"] == "synthetic" and not packet["synthetic"]:
            raise Denied("Synthetic evidence mode not authorised")
        if instant(source["available_at"]) > instant(source["captured_at"]) or instant(source["captured_at"]) > end:
            raise Denied("Source vintage outside cutoff")
        if source["archive_verified"] is not False or type(source["archive_asserted"]) is not bool:
            raise Denied("This layer cannot authenticate archives")
        if packet["replay"] and source["kind"] != "synthetic" and not source["archive_asserted"]:
            raise Denied("Replay needs archive provenance assertion")
    if not isinstance(packet["claims"], list) or not isinstance(packet["checks"], list):
        raise ContractError("Claims/checks must be lists")
    integer(len(packet["claims"]))
    integer(len(packet["checks"]))
    claims = {}
    for claim in packet["claims"]:
        exact_keys(claim, CLAIM_FIELDS, {"claim_id", "text", "kind", "source_keys"})
        ident = safe_id(claim["claim_id"])
        if ident in claims or not isinstance(claim["text"], str) or not isinstance(claim["source_keys"], list):
            raise ContractError("Duplicate or malformed claim")
        if not set(claim["source_keys"]).issubset(packet["sources"]):
            raise Denied("Claim cites unavailable evidence")
        if claim["kind"] not in {"observed", "derived", "assumed", "synthetic", "literature_inference", "unavailable"}:
            raise ContractError("Invalid claim kind")
        if any(packet["sources"][key]["kind"] == "synthetic" for key in claim["source_keys"]) and claim["kind"] != "synthetic":
            raise Denied("Synthetic evidence cannot be relabelled as an observed/derived claim")
        if claim.get("section_ids") and not set(claim["section_ids"]).issubset(packet["sections"]):
            raise Denied("Claim cites unknown section")
        claims[ident] = claim
    seen = set()
    for check in packet["checks"]:
        exact_keys(check, CHECK_FIELDS, {"check_id", "claim_id", "operation", "consequential"})
        ident = safe_id(check["check_id"])
        if ident in seen or check["claim_id"] not in claims or check["operation"] not in OPERATIONS:
            raise ContractError("Duplicate, unsupported or misbound check")
        seen.add(ident)
        if type(check["consequential"]) is not bool:
            raise ContractError("Consequential is an operator-declared boolean")
        if check["operation"] != "semantic":
            if check.get("source_key") not in claims[check["claim_id"]]["source_keys"]:
                raise Denied("Check must use the claim's admitted evidence")
            if not isinstance(check.get("pointer"), str):
                raise ContractError("Mechanical check requires a JSON pointer")
        for tol in ("atol", "rtol"):
            if number(check.get(tol, 0)) < 0:
                raise ContractError("Negative numerical tolerance")
    for section, text in packet["sections"].items():
        safe_id(section)
        if not isinstance(text, str):
            raise ContractError("Sections must be text")


def execute_check(packet: dict, check: dict) -> dict:
    """Recompute from frozen evidence, never from an evaluator answer or a review."""
    claim = next(c for c in packet["claims"] if c["claim_id"] == check["claim_id"])
    record = {"check_id": check["check_id"], "claim_id": claim["claim_id"],
              "consequential": check["consequential"], "operation": check["operation"],
              "assumption": check.get("assumption", "Supplied measurement/metadata are correct")}
    if check["operation"] == "semantic":
        return {**record, "state": "unable_to_check", "reason": "Semantic judgement requires external verification"}
    source = packet["sources"][check["source_key"]]
    record.update(source_key=check["source_key"], source_sha256=source["sha256"], pointer=check["pointer"])
    try:
        data = pointer(source["payload"], check["pointer"])
        op = check["operation"]
        if op == "exact_quote":
            anchor = quote_anchor(data, claim.get("quote", ""))
            state = {"exact": "passed", "not_found": "failed"}.get(anchor["match"], "unable_to_check")
            return {**record, "state": state, "anchor": anchor,
                    "reason": "Quotation location only; entailment not established"}
        asserted = claim["asserted"]
        if op == "mean":
            if not isinstance(data, list) or not data or len(data) > 100_000:
                raise ContractError("Mean needs 1-100000 finite supplied values")
            calculated = statistics.mean(number(x) for x in data)
            ok = math.isclose(number(asserted), calculated,
                              abs_tol=check.get("atol", 0), rel_tol=check.get("rtol", 0))
        elif op == "distinct_periods":
            if not isinstance(data, list) or len(data) > 100_000:
                raise ContractError("Invalid period list")
            calculated = len({canonical(pointer(row, check.get("field", "/period"))) for row in data})
            ok = number(asserted) == calculated
        elif op == "inference":
            if data not in {"descriptive", "causal"} or asserted not in {"descriptive", "causal"}:
                raise ContractError("Inference categories not specified")
            calculated = data
            ok = asserted == "descriptive" or data == "causal"
        else:
            calculated = data
            if type(asserted) in (int, float) and type(data) in (int, float):
                ok = math.isclose(number(asserted), number(data),
                                  abs_tol=check.get("atol", 0), rel_tol=check.get("rtol", 0))
            else:
                ok = canonical(asserted) == canonical(data)
        return {**record, "state": "passed" if ok else "failed", "asserted": asserted,
                "calculated": calculated, "reason": "Frozen structured-check comparison"}
    except (KeyError, IndexError, TypeError, ContractError, ValueError) as exc:
        return {**record, "state": "unable_to_check", "reason": type(exc).__name__ + ": " + str(exc)}


def review(packet: dict, ledger: Ledger, run_id: str, *, max_checks: int = 100,
           allegations: list[dict] | None = None, rebuttals: list[dict] | None = None) -> dict:
    """One bounded challenge/verification pass; imported criticisms are untrusted.

None allegations generates mechanical candidates; [] explicitly makes none.
Rebuttal prose is preserved, but cannot overrule a reproducible check failure.
"""
    validate_packet(packet)
    safe_id(run_id)
    integer(max_checks)
    packet = clone(packet)
    checks = {c["check_id"]: c for c in packet["checks"]}
    rebuttals = clone(rebuttals or [])
    if allegations is not None:
        if not isinstance(allegations, list):
            raise ContractError("Allegations must be a list")
        seen = set()
        for item in allegations:
            exact_keys(item, {"check_id", "criticism"})
            if item["check_id"] not in checks or item["check_id"] in seen or not isinstance(item["criticism"], str):
                raise ContractError("Unknown, duplicate or malformed allegation")
            seen.add(item["check_id"])
    if not isinstance(rebuttals, list):
        raise ContractError("Rebuttals must be a list")
    for item in rebuttals:
        exact_keys(item, {"check_id", "explanation", "anchors"})
        if item["check_id"] not in checks or not isinstance(item["explanation"], str) or not isinstance(item["anchors"], list):
            raise ContractError("Malformed rebuttal")
        for anchor in item["anchors"]:
            exact_keys(anchor, {"source_key", "pointer", "quote"})
            if anchor["source_key"] not in packet["sources"]:
                raise Denied("Rebuttal cites evidence outside cutoff/capability")
    plan = {"packet_hash": packet["sha256"], "code": code_fingerprint(), "max_checks": max_checks,
            "allegations": allegations, "rebuttals": rebuttals, "repair_round_limit": 1,
            "external_spend_authorised_usd": 0}
    with ledger.transaction():
        prior = ledger.get("assurance_start", run_id)
        if prior is not None:
            if prior != plan:
                raise Denied("Changed plan under existing review ID")
            done = ledger.get("assurance_finish", run_id)
            if done is not None:
                return done
            raise ReconciliationRequired("Review interrupted; no hidden retry under same ID")
        ledger._put("assurance_start", run_id, plan, "assurance")
    try:
        executed = [execute_check(packet, c) if i < max_checks else
                    {"check_id": c["check_id"], "claim_id": c["claim_id"], "state": "not_checked_budget",
                     "consequential": c["consequential"]}
                    for i, c in enumerate(packet["checks"])]
        by_id = {c["check_id"]: c for c in executed}
        candidates = allegations if allegations is not None else [
            {"check_id": c["check_id"], "criticism": c.get("reason", "Unresolved check")}
            for c in executed if c["state"] in {"failed", "unable_to_check"}]
        findings = []
        for item in candidates:
            test = by_id[item["check_id"]]
            objections = []
            for objection in rebuttals:
                if objection["check_id"] != item["check_id"]:
                    continue
                anchors = []
                for anchor in objection["anchors"]:
                    try:
                        text = pointer(packet["sources"][anchor["source_key"]]["payload"], anchor["pointer"])
                    except (KeyError, IndexError, ContractError):
                        text = None
                    anchors.append({**anchor, **quote_anchor(text, anchor["quote"])})
                objections.append({**objection, "anchors": anchors, "semantic_disposition": "not_adjudicated"})
            disposition = {"failed": "verified_scoped_defect", "passed": "withdrawn"}.get(test["state"], "unresolved")
            findings.append({**item, "claim_id": test["claim_id"], "check": test,
                             "rebuttals": objections, "disposition": disposition,
                             "assumptions_unresolved": [checks[item["check_id"]].get("assumption", "Source semantics and check scope need independent review")],
                             "repair_authorised": False})
        counts = {state: sum(c["state"] == state for c in executed)
                  for state in ("passed", "failed", "unable_to_check", "not_checked_budget")}
        checked_claims = {c["claim_id"] for c in packet["checks"]}
        uncovered = [c["claim_id"] for c in packet["claims"] if c["claim_id"] not in checked_claims]
        incomplete = bool(uncovered or counts["unable_to_check"] or counts["not_checked_budget"] or not executed)
        status = "scoped_defects_found" if counts["failed"] else "review_incomplete" if incomplete else "no_supported_issue_found"
        output = {"version": VERSION, "run_id": run_id, "packet_hash": packet["sha256"],
                  "status": status, "checks": executed, "findings": findings,
                  "coverage": {**counts, "uncovered_claim_ids": uncovered},
                  "scientific_status": "unverified", "journal_readiness": "not_evaluated",
                  "semantic_entailment": "not_established", "source_data_changed": False,
                  "resources": {"live_model_calls": 0, "external_spend_usd": 0,
                                "imported_review_cost_usd": None, "human_minutes": None},
                  "evidence_mode": "public_synthetic_calibration" if packet["synthetic"] else "supplied_evidence_unadjudicated"}
        with ledger.transaction():
            for claim in packet["claims"]:
                extension = {"original_claim_hash": digest(claim), "packet_hash": packet["sha256"],
                             "run_id": run_id, "findings": [f for f in findings if f["claim_id"] == claim["claim_id"]]}
                ledger._put("assurance_claim_extensions", run_id + ":" + claim["claim_id"], extension, "assurance")
            ledger._put("assurance_finish", run_id, output, "assurance")
        return output
    except BaseException as exc:
        ledger.put("assurance_failure", run_id, {"exception": type(exc).__name__, "retry": "requires_new_explicit_run_id"})
        raise


def assess_repair(original: dict, revised: dict, *, round_number: int = 1) -> dict:
    """Assess a proposal, never apply it. All frozen checks must remain unchanged."""
    if round_number != 1 or type(round_number) is not int:
        raise Denied("Only one repair cycle is permitted")
    validate_packet(original)
    validate_packet(revised)
    for key in PACKET_FIELDS - {"claims", "sections", "sha256", "lineage"}:
        if original[key] != revised[key]:
            raise Denied("Repair cannot change sources, scope, cutoff or frozen checks")
    if revised["lineage"].get("repair_of") != original["sha256"] or "repair_of" in original["lineage"]:
        raise Denied("Repair must bind the original packet and cannot repair a repair")
    if [c["claim_id"] for c in original["claims"]] != [c["claim_id"] for c in revised["claims"]]:
        raise Denied("Repair cannot add, remove or reidentify claims")
    before = {c["check_id"]: execute_check(original, c)["state"] for c in original["checks"]}
    after = {c["check_id"]: execute_check(revised, c)["state"] for c in revised["checks"]}
    fixed = [key for key in before if before[key] == "failed" and after[key] == "passed"]
    harms = [key for key in before if before[key] == "passed" and after[key] == "failed"]
    unknown = [key for key in after if after[key] == "unable_to_check"]
    # Even mechanically successful rewrites remain proposals: prose can acquire errors.
    verdict = "repair_harm" if harms else "indeterminate" if unknown else "scoped_improvement" if fixed else "no_scoped_gain"
    return {"verdict": verdict, "fixed_check_ids": fixed, "new_failed_check_ids": harms,
            "unresolved_check_ids": unknown, "applied": False,
            "semantic_regression_review": "still_required", "round": 1,
            "before_packet_hash": original["sha256"], "after_packet_hash": revised["sha256"]}


def from_agent_record(ledger: Ledger, *, agent: str, key: str, work_id: str,
                      parent_id: str, sources: list[dict], cutoff: str,
                      checks: list[dict] | None = None, synthetic: bool = False,
                      portfolio_cards: list[dict] | None = None) -> tuple[dict, list[dict]]:
    """Sidecar adapter over actual lifecycle ledger namespaces; never edits them.

Study claims retain their fields. Programme/scout prose is explicitly scoped for
semantic review; operator-frozen structured checks can be added separately.
"""
    boundary(work_id, parent_id, synthetic)  # Before any lifecycle record read.
    if agent == "study_producer":
        brief = ledger.get("study_briefs", work_id)
        record = ledger.get("study_results", key)
        if not brief or not record or record.get("study_id") != work_id or brief["cutoff"] != cutoff:
            raise Denied("Study artifact or inherited cutoff mismatch")
        candidate = record.get("candidate", {})
        claims = [{k: v for k, v in c.items() if k in CLAIM_FIELDS} for c in candidate.get("claims", [])]
        sections = candidate.get("sections", {})
        replay = False
    elif agent in {"programme_steward", "opportunity_scout"}:
        namespace = "programme_updates:" + work_id if agent == "programme_steward" else "scout_runs"
        record = ledger.get(namespace, key)
        if not record or record.get("cutoff") != cutoff:
            raise Denied("Lifecycle artifact or inherited cutoff mismatch")
        if agent == "programme_steward":
            baseline = ledger.get("programme_baselines", work_id)
            if not baseline or digest(baseline) != record.get("baseline_hash") or instant(baseline["locked_at"]) > instant(cutoff):
                raise Denied("Programme baseline binding mismatch")
            text = record.get("model_interpretation", {}).get("evidence_delta", "No semantic programme interpretation supplied")
            sections = {"update": text}
            citations = list(dict.fromkeys(c["source_key"] for c in record.get("changes", [])))
            claims = [{"claim_id": "update", "text": text, "kind": "synthetic" if synthetic else "literature_inference", "source_keys": citations}]
            replay = False
        else:
            if portfolio_cards is None:
                raise Denied("Scout assurance requires the cutoff-filtered parent portfolio")
            portfolio, exclusions = select_portfolio(portfolio_cards, cutoff, replay=record.get("replay", False))
            if exclusions:
                raise Denied("Scout portfolio is ineligible for this replay cutoff")
            works = {(c["work_id"], str(c["version"])): c for c in portfolio}
            sections, claims = {}, []
            for i, candidate in enumerate(record.get("candidates", [])):
                boundary(candidate["work_id"], candidate["work_id"], synthetic)
                if candidate["work_id"] != parent_id:
                    raise Denied("Scout sidecar requires one exact parent per packet")
                parent = works.get((candidate["work_id"], str(candidate["work_version"])))
                if not parent or candidate["claim_id"] not in {c["claim_id"] for c in parent["claims"]}:
                    raise Denied("Scout parent claim/version is unavailable at cutoff")
                if parent.get("synthetic") and not synthetic:
                    raise Denied("Synthetic parent requires synthetic assurance mode")
                sections["parent-" + str(i)] = canonical(portfolio_view(parent))
                ident = "opportunity-" + str(i)
                text = canonical({k: candidate[k] for k in ("work_id", "work_version", "claim_id", "what_changed", "mechanism", "minimum_test")})
                claims.append({"claim_id": ident, "text": text, "kind": "synthetic" if synthetic else "literature_inference", "source_keys": [candidate["source_key"]]})
                sections[ident] = text
            replay = record.get("replay", False)
    else:
        raise ContractError("Unknown lifecycle agent")
    # Avoid exporting exclusions, grading material, resource secrets or later state.
    if checks is None:
        checks = [{"check_id": "semantic-" + c["claim_id"], "claim_id": c["claim_id"],
                   "operation": "semantic", "consequential": True} for c in claims]
    return freeze_packet(work_id=work_id, parent_id=parent_id, agent=agent, cutoff=cutoff,
                         knowledge_as_of=cutoff, sources=sources, claims=claims, checks=checks,
                         sections=sections, replay=replay, synthetic=synthetic,
                         lineage={"agent_record_hash": digest(record), "agent_record_key": key,
                                  "temporal_provenance": "inherited_runtime_assertion_not_independent_authentication"})
