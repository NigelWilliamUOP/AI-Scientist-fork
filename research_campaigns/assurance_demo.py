"""Original public synthetic cases and offline fault-injection demonstration."""
from __future__ import annotations

from pathlib import Path

from .assurance import assess_repair, clone, freeze_packet, review
from .assurance_eval import (CONDITIONS, FAMILIES, attempt_summary, make_plan,
                            score_attempt, worker_request)
from .core import Ledger, digest, source_key, write_once

AT = "2026-09-01T00:00:00Z"
CUTOFF = "2026-09-10T00:00:00Z"


def fixtures() -> tuple[list[dict], dict]:
    """Six source parents, each with two variants; all publicly synthetic.

Expected labels are returned separately, never embedded in reviewer packets.
All pairs belong to development, not an independent or contamination-free test.
"""
    packets, expected = [], {}
    specs = [
        ("exact_quote", "/text", "Capacity is 100 units.", "Capacity is 10 units."),
        ("value_equal", "/unit", "GBP_per_tonne", "USD_per_tonne"),
        ("mean", "/values", 4, 8),
        ("inference", "/design", "descriptive", "causal"),
        ("distinct_periods", "/observations", 2, 3),
        ("value_equal", "/parent_version", "v1", "v2"),
    ]
    for i, (family, (op, ptr, correct, flawed)) in enumerate(zip(FAMILIES, specs)):
        payload = {"text": "Capacity is 100 units.", "unit": "GBP_per_tonne",
                   "values": [2, 4, 6], "design": "descriptive", "parent_version": "v1",
                   "observations": [{"period": "2026-07", "value": 10},
                                    {"period": "2026-07", "value": 11},
                                    {"period": "2026-08", "value": 12}],
                   "note": "Synthetic evidence only; no real market or study data."}
        source = {"source_id": "syn-source-" + str(i), "version": "v1", "payload": payload,
                  "sha256": digest(payload), "available_at": AT, "captured_at": AT,
                  "retrieved_at": AT, "kind": "synthetic", "access": "synthetic",
                  "locator": "synthetic://assurance/" + str(i)}
        key = source_key(source)
        for variant, asserted in enumerate((correct, flawed)):
            ident = "syn-" + str(i) + "-" + str(variant)
            claim = {"claim_id": "C1", "text": "Check the declared synthetic assertion against the evidence.",
                     "kind": "synthetic", "source_keys": [key],
                     "quote" if op == "exact_quote" else "asserted": asserted,
                     "assumptions": ["These are artificial calibration values."]}
            guard = {"claim_id": "C2", "text": "The source unit is GBP_per_tonne.",
                     "kind": "synthetic", "source_keys": [key], "asserted": "GBP_per_tonne"}
            checks = [{"check_id": "K1", "claim_id": "C1", "operation": op,
                       "source_key": key, "pointer": ptr, "consequential": True},
                      {"check_id": "K2", "claim_id": "C2", "operation": "value_equal",
                       "source_key": key, "pointer": "/unit", "consequential": True}]
            packet, _ = freeze_packet(work_id=ident, parent_id="syn-parent-" + str(i),
                agent="study_producer" if i < 4 else "programme_steward" if i == 4 else "opportunity_scout",
                cutoff=CUTOFF, knowledge_as_of=AT, sources=[source], claims=[claim, guard],
                checks=checks, sections={"results": "Public synthetic development packet."}, synthetic=True)
            packets.append(packet)
            expected[packet["sha256"]] = {"family": family,
                "defects": [{"defect_id": "D1", "check_id": "K1", "consequential": True}] if variant else []}
    return packets, expected


def demo(output: Path) -> dict:
    packets, expected = fixtures()
    plan = make_plan(packets)
    output.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(output / "assurance.sqlite")
    try:
        reports, scores = [], []
        for packet in packets:
            ident = packet["work_id"]
            report = review(packet, ledger, ident)
            reports.append(report)
            write_once(output / "worker" / (ident + ".json"), packet)
            write_once(output / "reports" / (ident + ".json"), report)
            for condition in CONDITIONS:
                write_once(output / "requests" / condition / (ident + ".json"), worker_request(plan, packet, condition))
            # Synthetic scorer self-test, NOT a run of any comparison condition.
            rows = [{"finding_id": "F" + str(i), "check_id": f["check_id"], "criticism": f["criticism"]}
                    for i, f in enumerate(report["findings"]) if f["disposition"] == "verified_scoped_defect"]
            labels = expected[packet["sha256"]]
            adjudication = {"packet_hash": packet["sha256"], "basis": "public_synthetic_expected",
                "reviewer_id": "deterministic-fixture-checker", "adjudicator_id": "public-synthetic-answer-fixture",
                "defects": labels["defects"], "finding_judgements": [
                    {"finding_id": f["finding_id"], "validity": "valid", "defect_ids": ["D1"]} for f in rows],
                "coverage": {c["check_id"]: "checked" for c in packet["checks"]}, "repair": None}
            attempt = {"status": "completed", "findings": rows, "cost_usd": 0, "calls": 0, "human_minutes": None}
            scores.append(score_attempt(packet=packet, attempt=attempt, adjudication=adjudication))
        # A plausible-sounding but false accusation is withdrawn after recomputation.
        false_criticism = review(packets[4], ledger, "false-criticism", allegations=[
            {"check_id": "K1", "criticism": "The mean is wrong despite correct supplied arithmetic."}])
        # Fix one error while damaging a previously correct assertion; apply neither.
        original = packets[5]
        harmful = clone(original)
        harmful["claims"][0]["asserted"] = 4
        harmful["claims"][1]["asserted"] = "USD_per_tonne"
        harmful["lineage"] = {"repair_of": original["sha256"]}
        harmful["sha256"] = digest({k: v for k, v in harmful.items() if k != "sha256"})
        repair = assess_repair(original, harmful)
        clean = clone(harmful)
        clean["claims"][1]["asserted"] = "GBP_per_tonne"
        clean["sha256"] = digest({k: v for k, v in clean.items() if k != "sha256"})
        good_repair = assess_repair(original, clean)
        summary = {"mode": "offline_public_synthetic_fault_injection_not_model_evaluation",
            "packets": len(packets), "parent_sources": 6, "families": list(FAMILIES),
            "clean_packets": sum(not x["defects"] for x in expected.values()),
            "flawed_packets": sum(bool(x["defects"]) for x in expected.values()),
            "mechanically_detected_injected_defects": sum(s["defects_detected"] for s in scores),
            "clean_packets_without_supported_issue": sum(r["status"] == "no_supported_issue_found" for r in reports),
            "false_criticism_disposition": false_criticism["findings"][0]["disposition"],
            "harmful_repair": repair, "scoped_repair": good_repair,
            "prepared_requests": len(packets) * len(CONDITIONS),
            "comparison": attempt_summary(ledger, plan),
            "live_model_calls": 0, "external_spend_usd": 0, "human_minutes": None,
            "independent_adjudication": "not_performed", "scientific_status": "not_established"}
        write_once(output / "plan.json", plan)
        write_once(output / "evaluator_only_public_synthetic" / "expected.json", expected)
        write_once(output / "evaluator_only_public_synthetic" / "scorer_self_test.json", scores)
        write_once(output / "repair_checks.json", {"harmful": repair, "scoped": good_repair})
        write_once(output / "false_criticism.json", false_criticism)
        write_once(output / "summary.json", summary)
        write_once(output / "ledger_audit.json", ledger.verify())
        return summary
    finally:
        ledger.close()
