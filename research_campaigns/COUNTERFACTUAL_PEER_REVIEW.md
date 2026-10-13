# Counterfactual peer-review simulator (v0.1)

**Status:** deterministic diagnostic core, not an AI reviewer, deployed MCP service, peer-review prediction model or empirically calibrated probability estimator.

## Purpose

Identify **why** a proposition might fail scientific review and test which **minimal change** could remedy a particular weakness. Research quality is the optimisation objective, not number of proposals, inference cost, reviewer-pleasing language or a synthetic acceptance probability.

The module `counterfactual_peer_review.py` defines nine review dimensions: novelty, mechanism, identification, measurement, falsifiability, evidence, replication, scope, ethics. A criterion can pass only with traceable evidence identifiers; unsupported claims must not be promoted. The current initial `CRITICAL` set (identification, evidence, ethics and replication) is a proposed configuration, **not** an empirically validated editorial rule.

## Contract

1. Freeze a rubric version **before** reviewers assess the candidate; keep later evolving rubrics separate.
2. Supply one independent review finding per dimension, with reviewer identifier, explanation, pass/fail and traceable evidence IDs. Missing dimensions cause an `unverified` status. The tool does not itself verify source content or scientific entailment.
3. Call `assess(findings, frozen_version=...)` to identify failure mechanisms. A clean result means only `passes_recorded_checks`, never that a paper will be accepted.
4. Propose one-at-a-time repairs using a targeted dimension, new source IDs and a **separately testable** validation test.
5. Call `simulate(..., verified_evidence_ids=...)`. Sources not in the independently verified set block even hypothetical promotion.
6. Conditional improvements must be tested outside the simulator and re-assessed as a **new observed baseline** before a manuscript gate can change.
7. Retain the original failure result, rubric version, evidence receipts and the calculated assessment SHA-256 for independent audit.

## Example (synthetic only)

```python
from research_campaigns.counterfactual_peer_review import Finding, Repair, simulate, FAILURES

baseline = [
    Finding(k, k != "measurement", (f"source-{k}",), "Synthetic assessment", "r1")
    for k in FAILURES
]
repair = Repair("codebook", "measurement",
                "Introduce blinded coding validation", ("validation-protocol-1",),
                "Run an independent dual-coder reliability and construct-validity study")
result = simulate(baseline, [repair], frozen_version="research-rubric-v1",
                  verified_evidence_ids=["validation-protocol-1"])
assert result["baseline"]["status"] == "blocked"
assert result["counterfactuals"][0]["observed_result"] == "not_tested"
```

Run targeted tests with:

```bash
python -m unittest research_campaigns.test_counterfactual_peer_review -v
```

## Integration and release gates

The module is intentionally standalone and makes **no changes** to the challenge harness, Study Producer, model calls, authoring or existing verification gates. It is stacked on PR #8, which is stacked on #7 and earlier dependencies. Do not merge without testing this branch against the exact dependent head and ensuring the full `research_campaigns` suite passes.

Next integration should derive initial findings from the challenge harness ledger (without fabricating missing evidence), run independent reviewer assessments, preserve a locked benchmark rubric, and store scenario/validation outcomes append-only. A reviewer simulator based on language models would need blinded comparison, evidence-entailment checking, source withdrawal, rank stability tests, adversarial controls and academic adjudication.

**Not yet demonstrated:** forecast accuracy for actual editorial decisions; efficacy of the proposed repairs; inter-reviewer agreement; valid relative importance of criteria; model-driven generation; integration into an MCP server; improvement on real research programmes. No actual peer-review or model experiments have been run.
