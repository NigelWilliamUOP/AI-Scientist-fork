# Research Teamwork control layer v0.1

Status: additive, deterministic prototype. It plans work and preserves objections;
it does not run agents or certify research. Source review and development date:
16 October 2026. No Google code, weights or private implementation was copied.

## Why this change

Google describes configurable research teams, candidate-specific falsification,
dependency-aware work and reuse of failed approaches with their objections [S1].
Its documentation separates implementation, challenge and final audit roles [S2].
We adapt those ideas to research design rather than treating mathematical proof
verification as a general test of social-scientific validity.

## What is implemented

`teamwork_control.py` provides frozen, explicit question contracts, bounded
candidate records, synthesis lineage and hash-bound handoffs. Every objection
from an ancestor remains visible. Objections raised after synthesis also change
its handoff hash and invalidate old review snapshots. Negative and incomplete
review reports become durable objections. Majority approval cannot remove them.

A contract records question, population, unit, intervention, comparator, outcome,
time horizon, inference target, constraint version and evidence cutoff. An
explicit change to any field requires a separately frozen campaign. Identical
fields mean structural consistency only. A misleading strategy can leave every
field unchanged; semantic claim preservation therefore always remains unverified.

Declared authors cannot review their own lineage. Distinct reviewer identifiers
are not proof of distinct people, models or independent contexts. All review
verdicts remain caller assertions. Even an asserted empirical pass leaves
`empirical_validation=unverified` and `paper_release_authorised=false`.

The dependency utilities validate a directed acyclic graph and identify exactly
which registered descendants depend on a withdrawn node. They do not inspect
source files, discover missing links or make automatic changes to manuscripts.

`teamwork_patterns.json` defines five local blueprints: document review, theory
tournament, design rescue, simulation verification and programme tracking.
`plan_campaign` enforces allowed phases and a three-candidate/three-round plan
limit. These are our configuration files, not an importable Google pattern API.
No dispatcher, model session, parallel worker or authentication adapter is added.

## Where this fits

The inspected baseline is `agent/research-design-rescue-v0-2` at
`0d91f4ac5c46e0f6c36c965ed215502b84b67cc8`, the head of draft PR #10.
The new files do not modify the existing ideation, challenge, rescue, arithmetic
verification, MCP or Study Producer entry points. Their existing release gates
remain unchanged. This is an optional preparation layer, not an end-to-end
integration claim.

Before a live integration, place the control layer around the existing worker
and ledger interfaces. Freeze the research question and evidence access first.
Create independently generated design candidates within the EXISTING shared
Session budget. Give each a candidate-bound falsifier using source-linked
objections. Only then expose candidates and critiques to a synthesiser. A fresh
reviewer examines the resulting candidate, including the inherited objections.
The existing scientific challenge and arithmetic checks remain downstream.

The candidate registry must not receive a hidden independent baseline before
its planned comparison stage. No current project may acquire a retrospectively
claimed blind baseline. A new run ID does not reset exposure, search coverage,
provider spending or the existing three-attempt allowance.

PR #10 currently trusts `preserves_original_claim`. This module does not patch
that function and must not be described as solving semantic equivalence. It
avoids that Boolean and offers stricter handoff records for a future adapter.
Do not use PR #10's caller-asserted repair fields as manuscript-release receipts.

## Research-quality operating policy

Separate four checks: computational correctness, construct/measurement validity,
causal identification and empirical correspondence. A correct simulation can
illustrate a mechanism without establishing a real-world causal effect. Supported
arithmetic stays with the existing arithmetic adapter; unsupported model checks
must abstain or use a reviewed independent implementation.

No candidate wins just because several agents approve it. Preserve disagreement
and identify the missing discriminating observation. Prefer a feasible empirical
repair that retains the research question. A theoretically useful but empirically
unidentified proposition may become a conceptual-and-simulation paper under a new
contract. That transition does not repair the original empirical claim.

Use task-specific teams rather than a permanently large swarm. Start with at most
three genuinely different designs; verify substantive diversity rather than
counting differently worded candidates. Increase effort only against an explicit
unresolved question, inside pre-approved call, spend and wall-time limits. Existing
Session reservation rules must apply across every agent and restart.

## Memory and handoffs: specification, not implemented storage

A future durable pitfall registry should store `pitfall_id`, a generic failure
mechanism, applicability conditions, a discriminating check, source-run reference,
verification status and access classification. Examples include denominator drift
and conditioning on post-treatment variables. Keep candidate-specific objections
in their originating run. Do not turn a failed attempt into an eternal prohibition.

Separate reusable methodological lessons from case answers, held-out labels,
private data and outcome-exposed summaries. A coordinator handoff should include
frozen contracts, code/source fingerprints, outstanding objections, dependency
status, consumed budgets and the exact next permitted action. A returning agent
must not reset failure history or silently broaden the objective.

Human-AI interaction records should distinguish who chose the question, supplied
the data, altered the design, wrote code, checked claims and approved publication.
Aletheia proposes interaction cards and separate autonomy/novelty reporting [S3].
For this development turn: one ChatGPT assistant wrote and tested the original
code; no independent subagents, live research agents or human scientific panel ran.

## MOVE37 restriction

For the MOVE37 project, use `document_review` with `phase="review"`. This planner
refuses the tournament and simulation patterns in that phase. Complete the review
and evidence-to-design decision before any simulation. AI screening/appraisal is
provisional; no second human reviewer is implied. This development did not read,
change, screen or synthesise that project's review corpus.

Phase is a caller-supplied planning input, not authenticated project authority.
A production wrapper must bind phase changes to the existing approved protocol.

## Reproduce the software controls

From the repository root, with Python 3.10 or later:

```bash
python -m unittest discover -s research_campaigns/tests -p 'test_teamwork_control.py' -v
```

The development environment was Python 3.13.5. All 49 named public synthetic tests
passed locally. The separate output archive contains the actual command log and
source hashes. No full upstream regression suite or remote CI result is claimed.
The container could not resolve github.com for git transport; the connected GitHub
reader supplied the baseline inspection. No project dataset or model API was used.

The controls cover explicit claim changes, immutable IDs, bounded revisions,
objection propagation, stale reviews, self-review declarations, review laundering,
synthetic-versus-empirical status, graph errors and the review-before-simulation rule.
These are developer-authored unit tests, not a held-out capability benchmark.

## Next evaluation: specified but not executed

Compare a single researcher-plus-critic, the existing harness and this bounded
team design on the same frozen cases, evidence and shared token/spend limits.
Predeclare source exposure and randomly order anonymised outputs for assessment.
Do not use the unit-test cases as a blinded evaluation. An initial set of 24
separately curated research-design cases is a proposed pilot, not a power claim.
Include recoverable designs, impossible-under-current-constraints cases and
valuable conceptual reframings. Exclude MOVE37 until its review is complete.

Primary error: a changed, unsupported or unidentified claim labelled repaired.
Measure incorrect rejection of repairable designs separately, alongside review
minutes, resource consumption and unresolved defects. Count abstentions, failed
runs and human interventions in denominators. Report case-level results and
uncertainty; do not claim multi-agent benefit without a fair comparison.

## Limitations and release blockers

Objections cannot be resolved automatically in v0.1. That is deliberate: an
unauthenticated approval is not an adequate clearance mechanism. A future trusted
adjudication interface must bind a resolution to the exact claim, objection,
evidence and protocol version while retaining the original failed route.

State is in memory. There is no durable append-only ledger, checkpoint/restart
integrity, process sandbox, financial budget enforcement, dynamic worker spawning,
source authenticity check or semantic-equivalence classifier in this module.
Private Python attributes are not a security boundary. Counts constrain this
object only; they do not enforce budgets across processes or campaigns.

The existing full regression suite, worker adapters, trusted admission controls,
independent scientific review and live comparative evaluation are release blockers.
The main branch and existing PR #10 implementation are unchanged by these files.

## Sources

[S1] The Antigravity Team (27 August 2026), "Teamwork: when AI becomes a research
partner". Read 16 October 2026.
https://antigravity.google/blog/teamwork-when-ai-becomes-a-research-partner

[S2] Google Antigravity documentation, "Teamwork agent teams
(/teamwork-preview)". Read 16 October 2026. Product documentation, not an
independent social-science validation study.
https://antigravity.google/docs/teamwork

[S3] Feng et al., "Towards Autonomous Mathematics Research", arXiv:2602.10177v3,
6 March 2026. Abstract and metadata read 16 October 2026; full paper not appraised.
https://arxiv.org/abs/2602.10177v3

These sources motivate an original adaptation. No reported Google benchmark score
is treated as an expected effect size for social-science research.
