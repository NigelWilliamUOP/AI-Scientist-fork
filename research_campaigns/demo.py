"""Entirely synthetic fixtures. No Missouri or CEMENT empirical data are implied."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from .agents import ProgrammeSteward, StudyProducer
from .core import Ledger, digest, write_once
from .providers import BaselineProvider, Budget, Session
from .replay import run_replay


def stamp(month: int, day: int = 10) -> str:
    return f"2026-{month:02d}-{day:02d}T12:00:00Z"


def snapshot(ident: str, month: int, payload: dict, version: str = "1", captured: str | None = None) -> dict:
    at = stamp(month)
    return {"source_id": ident, "version": version, "available_at": at, "captured_at": captured or at,
        "retrieved_at": "2026-09-20T12:00:00Z", "payload": payload, "sha256": digest(payload),
        "kind": "synthetic", "access": "synthetic", "locator": "fixture://" + ident}


def fixtures() -> dict:
    schema = {"variables": ["project_id", "payment_days", "buffer_days"], "join_keys": ["project_id"],
              "unit": "days", "population": "synthetic_projects", "geography": "synthetic_region", "frequency": "monthly"}
    payload = {"title": "Synthetic release of payment timing measurements", "primary_source": True,
        "topics": ["project_buffer"], "schema": schema,
        "rows": [{"project_id": i, "payment_days": i * 10, "buffer_days": i * 5} for i in range(1, 5)]}
    initial = snapshot("payment-data", 1, payload)
    revised_payload = deepcopy(payload)
    revised_payload["title"] = "Synthetic revised payment measurements"
    revised_payload["rows"][0]["payment_days"] = 12
    revised = snapshot("payment-data", 3, revised_payload, "2")
    proxy_payload = deepcopy(payload)
    proxy_payload["title"] = "Synthetic approval timing proxy, not settlement timing"
    proxy_payload["schema"]["unit"] = "approval_days"
    proxy = snapshot("approval-proxy", 2, proxy_payload)
    contrary = deepcopy(payload)
    contrary["title"] = "Synthetic counterexample dataset for the buffer relationship"
    contrary["rows"] = [{"project_id": i, "payment_days": 10 * i, "buffer_days": 25 - 5 * i} for i in range(1, 5)]
    contradiction = snapshot("counterexample-data", 4, contrary)
    future = snapshot("future-data", 5, deepcopy(payload))
    late = snapshot("late-capture", 1, deepcopy(payload), captured=stamp(6))
    card = {"work_id": "BUFFER-DEMO", "version": "1", "known_at": stamp(1, 1), "captured_at": stamp(1, 1),
        "synthetic": True, "title": "Synthetic project-buffer work card",
        "claims": [{"claim_id": "C1", "text": "The descriptive buffer relationship needs a settlement-timing test.",
                    "topics": ["project_buffer"], "required_data": deepcopy(schema)}]}
    card["sha256"] = digest(card)
    later = {k: deepcopy(v) for k, v in card.items() if k != "sha256"}
    later.update(version="2", known_at=stamp(6, 1), captured_at=stamp(6, 1))
    later["claims"].append({"claim_id": "FUTURE-CLAIM", "text": "WITHHELD_FUTURE_PORTFOLIO_NOTE", "topics": ["project_buffer"], "required_data": deepcopy(schema)})
    later["sha256"] = digest(later)
    brief = {"study_id": "STUDY-DEMO", "title": "Synthetic payment timing: bounded study demonstration",
        "question": "What is the distribution of payment days in the supplied synthetic rows?",
        "target_journal": "IEEE Transactions on Engineering Management (scope target only)",
        "allowed_methods": ["describe"], "outcome_column": "payment_days", "source_ids": ["payment-data"], "cutoff": stamp(2, 1)}
    baseline = {"programme_id": "PROGRAMME-DEMO", "title": "Synthetic evolving-price programme",
        "locked_at": stamp(1, 1), "protocol_status": "internally_locked",
        "outcomes": [{"series_id": "price", "frequency": "monthly", "unit": "index"}],
        "hypotheses": [{"hypothesis_id": "H1", "text": "A stable synthetic index"}, {"hypothesis_id": "H2", "text": "A shifted synthetic index"}],
        "predictions": [{"prediction_id": h, "hypothesis_id": h, "series_id": "price", "period": "2026-01", "issued_at": stamp(1, 1), "interval": bounds}
                        for h, bounds in [("H1", [90, 110]), ("H2", [120, 140])]]}
    observation = {"series_id": "price", "period": "2026-01", "frequency": "monthly", "unit": "index", "value": 100}
    release = snapshot("price-series", 2, {"observations": [observation]})
    revision = snapshot("price-series", 3, {"observations": [{**observation, "value": 105}]}, "2")
    new_period = snapshot("next-period", 4, {"observations": [{**observation, "period": "2026-02", "value": 130}]})
    annual = snapshot("annual-proxy", 2, {"observations": [{**observation, "frequency": "annual", "period": "2025", "value": 120}]})
    return {"sources": [initial, proxy, revised, contradiction, future, late], "portfolio": [card, later],
        "brief": brief, "baseline": baseline, "programme_sources": [release, revision, new_period, annual],
        "cutoffs": [stamp(1, 5), stamp(1, 31), stamp(2, 28), stamp(3, 31), stamp(4, 30)]}


def run_demo(output: Path) -> dict:
    data = fixtures()
    for key, value in data.items():
        write_once(output / "inputs" / (key + ".json"), value)
    study_db = Ledger(output / "study" / "state.sqlite")
    try:
        session = Session(study_db, BaselineProvider(), Budget())
        study = StudyProducer(study_db, session).run(data["brief"], data["sources"], synthetic=True)
        write_once(output / "study" / "result.json", study)
        write_once(output / "study" / "manuscript.md", study["manuscript_markdown"], text=True)
    finally:
        study_db.close()
    programme_db = Ledger(output / "programme" / "state.sqlite")
    try:
        steward = ProgrammeSteward(programme_db, Session(programme_db, BaselineProvider(), Budget()))
        steward.initialise(data["baseline"])
        updates = []
        for month in (2, 3, 4):
            outcome = steward.update("PROGRAMME-DEMO", data["programme_sources"], stamp(month, 28), synthetic=True)
            updates.append(outcome)
            write_once(output / "programme" / (f"update-{month}.json"), outcome)
        unchanged = steward.update("PROGRAMME-DEMO", data["programme_sources"], stamp(4, 28), synthetic=True)
        assert unchanged == updates[-1]
    finally:
        programme_db.close()
    replay = run_replay(data["portfolio"], data["sources"], data["cutoffs"], output / "replay",
                        BaselineProvider(), Budget(), synthetic=True)
    summary = {"demonstration": "synthetic_only", "study_status": study["status"],
        "study_mean": study["analysis"]["result"]["mean"], "programme_independent_periods": [u["independent_periods"] for u in updates],
        "programme_vintages": [u["admitted_vintages"] for u in updates], "duplicate_update_identical": unchanged == updates[-1],
        "replay": replay, "live_provider_called": False, "empirical_scientific_validation": "not_performed"}
    write_once(output / "demo_report.json", summary)
    return summary
