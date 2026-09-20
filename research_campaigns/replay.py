"""Date-locked scout replay with isolated agent state at every cutoff.

Only cutoff-eligible evidence enters the worker request. The evaluator sees
exclusion logs afterwards. Archive dates are operator-supplied assertions, not
independently authenticated by this package. Model training-data hindsight is
not removed by filtering documents.
"""
from __future__ import annotations

from pathlib import Path

from .agents import OpportunityScout
from .core import ContractError, Ledger, digest, instant, write_once
from .providers import Budget, Provider, Session


def run_replay(cards: list[dict], sources: list[dict], cutoffs: list[str], output: Path,
               provider: Provider, budget: Budget, *, synthetic: bool = False, queue_limit: int = 5) -> dict:
    if not cutoffs or len(cutoffs) > 1000:
        raise ContractError("Supply 1-1000 cutoffs")
    times = [instant(c) for c in cutoffs]
    if times != sorted(set(times)):
        raise ContractError("Replay cutoffs must be strictly increasing and unique")
    output.mkdir(parents=True, exist_ok=True)
    master = Ledger(output / "replay.sqlite")
    try:
        config = {"portfolio_hash": digest(cards), "sources_hash": digest(sources), "cutoffs": cutoffs,
                  "provider": provider.name, "synthetic": synthetic, "queue_limit": queue_limit}
        master.put("replay", "manifest", config, "operator")
        session = Session(master, provider, budget)
        steps, first_detected = [], {}
        for index, cutoff in enumerate(cutoffs):
            # New state database for each cutoff: no later opportunity, run output,
            # programme owner change or model memory can be inherited accidentally.
            directory = output / f"cutoff-{index:03d}"
            local = Ledger(directory / "state.sqlite")
            try:
                scout = OpportunityScout(local, session)
                outcome = scout.run(cards, sources, cutoff, replay=True, synthetic=synthetic, queue_limit=queue_limit)
                local.verify()
                write_once(directory / "result.json", outcome)
                step = {"cutoff": cutoff, "status": outcome["status"], "eligible_sources": outcome["coverage"]["eligible_sources"],
                        "eligible_works": outcome["coverage"]["eligible_works"], "candidates": len(outcome["candidates"]),
                        "source_manifest_hash": outcome["source_manifest_hash"],
                        "portfolio_manifest_hash": outcome["portfolio_manifest_hash"],
                        "result_hash": digest(outcome), "state_hash": local.verify()["head_hash"]}
                steps.append(step)
                for candidate in outcome["candidates"]:
                    first_detected.setdefault(candidate["opportunity_id"], {
                        "cutoff": cutoff, "work_id": candidate["work_id"], "claim_id": candidate["claim_id"],
                        "source_key": candidate["source_key"], "extension_type": candidate["extension_type"]})
                if outcome["status"] == "stopped_budget":
                    break
            finally:
                local.close()
        summary = {"mode": "synthetic_replay_fixture" if synthetic else "historical_source_replay",
                   "provider": provider.name, "steps": steps, "first_detected": first_detected,
                   "resources": session.resources(), "integrity": master.verify(),
                   "candidate_quality_evaluated": False,
                   "limitations": ["Replay validates source gating, not removal of model training-data hindsight.",
                       "Archive provenance and timestamp assertions need independent audit for real historical inference.",
                       "Synthetic baseline results are not evidence of autonomous scientific discovery.",
                       "Each cutoff has isolated agent state; recall across cutoffs is intentionally not scored."]}
        write_once(output / "replay_report.json", summary)
        return summary
    finally:
        master.close()
