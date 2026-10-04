# Social-science challenge harness v0.1

This module extends the research-lifecycle and assurance work with an adversarial
research-question harness. Its optimisation target is **a defensible proposition
worth developing for publication**, not the largest effect or smallest p-value.

## What it does

A challenge run freezes the question, scope, outcome, unit of analysis, cutoff,
data-exposure status and evidence set. It then searches up to five proposition
formulations. Each proposition receives five independent attacks:

- strongest evidence-bounded supporting case;
- falsification/counterexample search;
- rival-mechanism search;
- measurement/confounding challenge;
- boundary-condition and transportability challenge.

Five verification gates then check methods, statistics, evidence, reproducibility
and publication contribution/positioning. A comparative reviewer checks the whole
round for assumptions or source dependencies shared by every attempt. Failing
propositions can be repaired across bounded rounds, with each revision receiving a
new proposition ID. The final state is one of
`survives_current_challenge`, `repair_required`, `challenged`,
`unsupported` or `inconclusive`.

The score is a **search utility**, not a probability of truth, effect,
publication or acceptance. It favours independently verified evidence support, passing gates, theoretical
contribution, novelty positioning, discriminating tests, precise scope and
robustness. The proposition generator cannot award itself those components: the
evidence and publication verifiers supply them. A rejection penalty prevents a
superficially novel but methodologically broken proposition from winning.

## Publication-seeking constraints

The harness may narrow the population, time period, context or mechanism and may
propose discriminating tests. It must not improve a proposition by:

- switching the frozen outcome, evidence vintage or exclusions;
- omitting contrary evidence;
- converting an outcome-informed existing-data result into confirmatory work;
- searching specifications for statistical significance;
- treating repeated analyses of the same data as independent replication;
- converting a null test into equivalence or a descriptive association into
  causality without the required design/identification logic.

When the target outcome has already been inspected,
`confirmatory_status=exploratory_existing_data`. A later untouched holdout,
new period or independent dataset is needed for a prospective test.

## Model separation and budgets

`SessionChallengeWorker` uses the existing budgeted provider `Session`.
Generator/attack roles can use one session and verification roles a second
session with a different provider/model. Keep their provider accounting ledgers
separate if their session configurations differ. The challenge result itself is
written to the supplied append-only research ledger.

No model, network or spend is enabled by default. The existing provider adapter
still requires explicit network permission, a positive spend cap, current
operator-supplied rates and credentials.

## Research mutation benchmark

The benchmark creates one clean control plus ten single-fault mutations:

| Family | Expected detection |
|---|---|
| causal upgrade | `CAUSAL_UPGRADE` |
| unvalidated proxy substitution | `PROXY_SUBSTITUTION` |
| numerical drift | `NUMERIC_DRIFT` |
| denominator drift | `DENOMINATOR_DRIFT` |
| post-cutoff evidence | `TEMPORAL_LEAK` |
| outcome switching | `OUTCOME_SWITCH` |
| null-to-equivalence overclaim | `NULL_TO_EQUIVALENCE` |
| duplicated evidence presented as independent | `FALSE_INDEPENDENCE` |
| source meaning/direction flip | `SOURCE_DIRECTION_FLIP` |
| boundary overreach | `BOUNDARY_OVERREACH` |

`mutation_worker_view()` strips mutation IDs, families and expected labels.
`mutation_gold()` is for the evaluator only. Never pass the raw case objects or
gold file to a model under test.

Metrics are mutation recall, consequential-mutation recall, clean-control false
positive rate and per-family recall. They measure **fault-detection performance**,
not scientific validity or autonomous-research capability.

## Run the offline control

```bash
python -m research_campaigns.challenge_cli demo \
  --output ./research_campaigns_runs/challenge-demo

python -m unittest research_campaigns.tests.test_challenge_harness -v
```

The deterministic worker is only an orchestration and mutation-control fixture.
It does not perform semantic peer review, novelty assessment or scientific
reasoning.

## Recommended live evaluation

Use the same blinded mutation cases for:
1. a single-prompt critic;
2. the assurance sidecar reviewer architecture;
3. this multi-role challenge harness.

Freeze model IDs/settings, source packets, token/spend limits and adjudication
rules before execution. Keep labels and adjudications outside worker context.
Report every initiated attempt, including refusals, interruptions and abstentions.

A useful primary outcome is consequential-mutation recall at a prespecified
clean-control false-positive ceiling. A secondary outcome is whether the harness
produces a narrower proposition that survives more gates without changing the
frozen evidence boundary.
