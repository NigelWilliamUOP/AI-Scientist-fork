# Evidence-bound social-science ideation, v0.2

Use this pre-proposal stage for new question-only runs. Previously exposed
candidates remain eligible for the existing challenge harness, but cannot
acquire a retrospectively claimed blind baseline.

## Sequence

1. Freeze the question, scope, outcome, unit, data-exposure status and cutoff.
2. Find one specific gap on one axis. Usually require two full-text near-miss
   studies; one needs an explicit coverage rationale. `no_gap` requires
   documented read coverage. Unavailable evidence produces `blocked` or
   `unverified`, rather than an inferred gap or novelty claim.
3. Before innovation, freeze ordinary plausible mechanisms from only the
   question, gap and result-masked near-miss methods.
4. Generate one short candidate at a time without showing the baseline to the
   innovator. Require source-to-target mapping, transfer conditions, failure
   risk, closest-work evidence and predictions with kill conditions.
5. Acquire a candidate-bound disconfirming search through a separate boundary.
   Search mechanism-plus-problem combinations and read registered hits. Review
   may `survive`, `revise`, `reject` or remain `unverified`.
6. Compare a survivor with the frozen baseline. Ordinary derivability is a
   separate assessment from literature novelty.
7. Send the current survivor through the existing theory collaborators, five
   adversarial roles, five verifier gates and comparative reviewer. Repairs use
   new IDs, receive new pre-proposal reviews and rerun the gates.

Reject and unverified verdicts cannot advance to full theory development.
Unverified stops further candidate generation. Repairs retain the existing
three-round bound. All original frozen outcomes, contrary evidence, exploratory
status, append-only history and inference restrictions remain in force.

Valid contribution types include `mechanism`, `measurement`,
`boundary_condition`, `replication`, `theory_discrimination`, `method` and
`institutional_explanation`. A missing dataset or new application alone does
not demonstrate a contribution. Measurement and replication need not introduce
a new mechanism. The guarded mode keeps the exact frozen scope; use a separately
frozen narrower question when scope revision is necessary.

## Run the public synthetic control

```bash
python -m research_campaigns.challenge_cli ideation-demo \
  --output ./research_campaigns_runs/ideation-demo
python -m unittest research_campaigns.tests.test_ideation -v
python -m unittest discover -s research_campaigns/tests -q
```

The demo uses staff work per resolved service episode, fictional method digests
and a planted search record. It uses no NHS data, literature retrieval or model
calls. A survivor is an orchestration control, not a scientific finding.
It writes question/specification/report/summary files and an append-only ledger.

Plain `run_challenge` remains available for existing candidates and explicitly
records `ideation_status: not_run`. Existing mutation and scientific red-team
commands are preserved. Mechanical checks now scan each repaired proposition,
rather than only the initial candidate. Checkpoints fingerprint actual code.

## Actual integration

Use `run_ideation_challenge(packet, spec, worker, ledger, run_id=...,
searcher=..., config=...)` from `research_campaigns.ideation`.
The packet uses the existing question schema with an empty
`candidate_propositions` list. Seen outcomes retain exploratory status.

The specification contains one `axis`, `prior_candidate_exposure: false`,
substantive `discovery_coverage`, and `papers`. Each paper has `paper_id`,
`canonical_id` (DOI or exact source identity), `title`, exact `version`,
`version_at`, `available_at`, `read_status` and `access_level`.
It also supplies four `masked_views` (`problem_definition`, `challenge`,
`intuition`, `solution`), a `masking_attestation` equal to
`results_omitted_from_methods_and_views`, and `answers` containing `goal`,
precise `locator`, verbatim `answer`, `kind` (`mechanism`, `context`, `result`)
and `access_level`.

Support receipts bind paper ID, version, answered goal, locator, verbatim
`answer_text`, supported `claim` and `kind`. Mechanisms need full-text method
answers; abstracts can support context. Every near miss requires such a
receipt. Two aliases of one version are rejected, as are two versions of one
study masquerading as independent near misses. Unknown or post-cutoff version
dates are rejected. An early v1 date never authorises a later v2.
The runtime does not infer methods from titles or fabricate reads.

The `Searcher` protocol receives the exact candidate snapshot/hash, target
question, cutoff and operation allowance. It returns a candidate-bound bundle
with `status`, `origin`, `coverage`, `queries` and optional newly read `papers`.
Each query records text, `searched_at`, `purpose` and registered `paper_ids`.
At least one purpose must be `mechanism_plus_problem_disconfirmation`.
Origins are `operator_supplied`, `retrieval_adapter` or `synthetic_fixture`.
An absent adapter or unread hit forces `unverified`.

Adapters must record every search and metadata-resolution operation and respect
the maximum allowance. The controller checks returned counts; hidden adapter
operations are not observable. Imported search/read records are assertions,
not independent proof of retrieval. Retain excluded sources in the acquisition
log outside worker context. No live search adapter is activated by this change.

`SessionChallengeWorker` supports the new contracts via the existing bounded
provider session. Baseline/reviewer/comparator use the verifier session;
gap finding/innovation use the generator. The existing Responses adapter makes
fresh requests without previous-response IDs. Generic workers must honour
context isolation; a projection cannot erase stateful worker memory.

## Budgets and recovery

Defaults reserve at most 24 ideation role calls, 18 search operations, six
operations per review and three candidate attempts. These counters cover the
new stages; downstream challenge roles are bounded separately. Use shared
provider Session budgets to cap total model calls and spend. The demo reports
guard reservations separately from measured total worker calls.

Reservations precede execution and are never refunded. Interrupted role/search
calls require inspection and a new run ID; retries cannot reset budgets.
Completed identical runs are reused. Changed inputs, code, worker identity or
configuration under the same run ID are refused.

Reviews store exact candidate and paper-registry snapshots, hashes and empirical
evidence hashes. Changed candidates, answers, locators or source versions
invalidate approval. Gap and baseline snapshots are immutable. A repair must
retain mapping/prediction contracts and cannot inherit an earlier review.

## Limits and attribution

Receipt equality is consistency, not semantic entailment or authenticity.
Baseline chronology is enforced by this API and local append-only ledger, not
external timestamp authentication. Result fields are omitted by projection;
masked method text is a supplied attestation. Full registered answers are
restored for review and feasibility. Model-training hindsight remains possible.
Novelty is bounded by searched/read coverage. Baseline difference does not
establish scientific truth or journal readiness.

Design inspiration: junjiezhou1122's native IdeaScientist adaptation at
`ce9185bc8ebd3e0dfb29bccc318dfd33845304b1`, 10 October 2026:
https://github.com/junjiezhou1122/ideascientist-claude-code/tree/ce9185bc8ebd3e0dfb29bccc318dfd33845304b1
and the original IdeaScientist authors:
https://github.com/jiarui-liu/IdeaScientist

This is original code integrated with the existing ledger, sessions and
social-science harness. No upstream code, weights, corpus or plugin is copied
or installed. The adaptation's own full compliant scientific workflow remains
unverified. This change makes no claim to reproduce its research performance.
