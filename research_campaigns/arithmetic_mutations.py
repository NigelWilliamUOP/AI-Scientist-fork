"""Synthetic same-route mutation controls; no model or scientific performance claim.

Run: python -m research_campaigns.arithmetic_mutations
Every mutation is repeated by the original route, so replay alone accepts it.
The independent gate must block drafting. Receipts are measurements of these
finite, declared fixtures, not validation of unseen errors or empirical truth.
"""
from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from . import agents
from .agents import StudyProducer
from .core import Ledger, code_fingerprint
from .demo import fixtures
from .providers import BaselineProvider, Budget, Session


class RecordingProvider(BaselineProvider):
    def __init__(self):
        self.tasks = []

    def complete(self, task, context):
        self.tasks.append(task)
        return super().complete(task, context)


def run_controls():
    mutations = [("describe", key, "add_one") for key in
                 ("n", "missing_rows", "mean", "minimum", "maximum", "sample_sd")]
    mutations += [("ols", key, "add_one") for key in
                  ("n", "missing_rows", "slope", "intercept", "residual_sum_squares", "r_squared")]
    mutations += [("describe", "n", "fractional_count"),
                  ("describe", "missing_rows", "float_count"),
                  ("describe", "sample_sd", "negative_sd"),
                  ("describe", "unreviewed_statistic", "extra_field")]
    receipts = []
    original = agents.analyse
    for method, field, mode in mutations:
        data = fixtures()
        data["brief"].update(allowed_methods=[method], exposure_column="buffer_days")
        provider = RecordingProvider()
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory) / "state.sqlite")
            session = Session(ledger, provider, Budget())

            def mutate(plan, source):
                output = copy.deepcopy(original(plan, source))
                values = output["result"]
                if mode == "fractional_count":
                    values[field] += 1e-10
                elif mode == "float_count":
                    values[field] = float(values[field])
                elif mode == "negative_sd":
                    values[field] = -values[field]
                elif mode == "extra_field":
                    values[field] = 999
                else:
                    values[field] += 1
                return output

            with patch("research_campaigns.agents.analyse", side_effect=mutate):
                outcome = StudyProducer(ledger, session, verify_arithmetic=True).run(
                    data["brief"], data["sources"], synthetic=True)
            blocked = (outcome["status"] == "abstained"
                       and outcome["arithmetic_replay"] == "passed_same_implementation"
                       and "manuscript_markdown" not in outcome
                       and provider.tasks == ["study_plan"]
                       and not ledger.items("study_drafts"))
            receipts.append({"method": method, "field": field, "mutation": mode,
                             "same_route_replay": outcome["arithmetic_replay"],
                             "gate_status": outcome["arithmetic_verification"]["status"],
                             "drafting_blocked": blocked,
                             "ledger_integrity": ledger.verify()["integrity"]})
            ledger.close()
    clean = []
    for method in ("describe", "ols"):
        data = fixtures()
        data["brief"].update(allowed_methods=[method], exposure_column="buffer_days")
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory) / "state.sqlite")
            session = Session(ledger, BaselineProvider(), Budget())
            outcome = StudyProducer(ledger, session, verify_arithmetic=True).run(
                data["brief"], data["sources"], synthetic=True)
            clean.append({"method": method, "gate_status": outcome["arithmetic_verification"]["status"],
                          "draft_produced": "manuscript_markdown" in outcome})
            ledger.close()
    return {"fixture_class": "synthetic_same_route_mutations", "runtime_fingerprint": code_fingerprint(),
            "mutations": receipts, "detected": sum(r["drafting_blocked"] for r in receipts),
            "total": len(receipts), "clean_controls": clean,
            "passed": all(r["drafting_blocked"] for r in receipts)
                      and all(r["gate_status"] == "numerically_checked" and r["draft_produced"] for r in clean),
            "live_model_calls": 0, "upstream_engine_executed": False,
            "scientific_validity": "not_evaluated"}


def main():
    report = run_controls()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
