# Shared research assurance, development release 0.1

Built 23 September 2026. Additive sidecar for the three research-lifecycle agents.
This is executable offline checking and evaluation infrastructure, not a live
semantic reviewer or evidence that autonomous research is scientifically valid.

## Scope and provenance

Base: `NigelWilliamUOP/AI-Scientist-fork`, PR #2,
`86feb9d7900f7b10f4d4b6d145a05bd994dd2156`.

The existing Study Producer, Programme Steward and Opportunity Scout are unchanged.
The extension reads their ledger namespaces and adds separate assurance records.
No legacy launcher, source dataset, original claim, programme baseline, frozen
prediction, existing paper gate, task version or benchmark condition is modified.

Coarse inspired evidence anchoring, challenges to reviewer criticisms, abstention,
and comparisons with a strong single-prompt reviewer. This is original code;
no Coarse code, paper, review, label or dataset is copied or installed.

Comparator source pin, verified through GitHub on 23 September 2026:
`Davidvandijcke/coarse@1e703c1a5178e05cd462daa264da8d094ffee93e`.
Source: https://github.com/Davidvandijcke/coarse/commit/1e703c1a5178e05cd462daa264da8d094ffee93e
Pinning is not executing, auditing or endorsing that comparator.

## Run

Python 3.10+ language features; tested locally on Python 3.13.5. Standard library
only. From the repository root:

```bash
python -m unittest discover -s research_campaigns/tests -p test_assurance.py -v
python -m research_campaigns.assurance_cli demo --output ./research_campaigns_runs/assurance-demo
python -m research_campaigns.assurance_cli --help
```

Use a NEW workspace after code changes: the existing runtime fingerprint and the
new diagnostic plan bind actual code. Old plans/checkpoints must not silently be
reused with a different implementation. Identical completed assurance runs are
reused; a changed plan under the same ID is rejected. An interrupted attempt needs
an explicitly new run ID after inspection; its original record remains visible.

## What is implemented

`assurance.py` creates detached, checksummed packets with exact source versions,
claims, sections, operator-frozen checks and inherited cutoffs. It uses the
existing core admission and append-only SQLite ledger, not a replacement runtime.

A claim extension records the original claim hash, criticism, check, assumptions,
rebuttal anchors and disposition. Original claims are not rewritten. The limited
mechanical checks are exact quotations, scalar/metadata equality, finite-value
means, distinct period counts and declared inference-category consistency.
A semantic check deliberately returns `unable_to_check`.

The scope and validity of each check are operator assumptions. Agreement with a
metadata field does not authenticate that metadata or validate a causal design.
Correct structured values can coexist with incorrect prose. The regression suite
explicitly demonstrates this failure mode; semantic entailment, scientific
validity and journal readiness remain unverified.

Quotations retain exact character offsets. Whitespace-only approximate matches
are separately labelled and do not become exact matches. Numeric and mathematical
symbol differences are not silently repaired. Empty quotations are unanchored.
An exact quotation demonstrates location, not support for a broader claim.

Imported criticisms are verified against frozen checks; a criticism of a passing
check is withdrawn. Rebuttals may cite only admitted evidence. Their exact anchors
are verified, while their semantic force remains unadjudicated. Rhetoric does not
overrule a numerical failure. This release does NOT autonomously generate the
strongest semantic rebuttal using an LLM; it accepts supplied rebuttals and exports
review instructions for that later, separately reviewed integration.

No criticism quota is imposed. `no_supported_issue_found`, `unable_to_check` and
`not_checked_budget` are distinct. A missing field, uncovered claim, empty check
set or exhausted budget cannot be treated as a scientific pass.

## One repair cycle, proposals only

`assess_repair(original, revised)` recomputes all frozen checks. It distinguishes
fixed checks, newly failing checks and unresolved checks. The revised packet must
bind `lineage.repair_of` to the original packet hash. Sources, cutoffs, scope,
checks and claim identities cannot change. A repair cannot itself be repaired.

Even a scoped improvement is not applied automatically. New prose errors may lie
outside the mechanical checks. A harmful repair is reported without overwriting
anything. Original evidence and predictions remain unchanged.

## Three-agent integration

`from_agent_record()` reads these existing namespaces:

| Agent | Reads | Output boundary |
|---|---|---|
| Study Producer | `study_briefs`, `study_results` | Original candidate claims and sections; matching study/cutoff required. |
| Programme Steward | `programme_baselines`, `programme_updates:<id>` | Baseline-hash-bound update interpretation; no prediction rewrite. |
| Opportunity Scout | `scout_runs` plus supplied archived portfolio | Exact parent/version/claim checks and inherited replay cutoff. |

The adapter is opt-in, not injected automatically into the existing workflows.
Programme/scout narrative reviews default to unresolved semantic checks. An
operator can freeze justified structured checks; the code does not invent a
measurement model to manufacture validation.

```bash
python -m research_campaigns.assurance_cli from-agent \
  --ledger /path/to/frozen-lifecycle.sqlite \
  --spec /path/to/adapter-spec.json \
  --output ./research_campaigns_runs/assurance-packet
python -m research_campaigns.assurance_cli review \
  --packet ./research_campaigns_runs/assurance-packet/packet.json \
  --output ./research_campaigns_runs/assurance-review --run-id review-001
```

The adapter spec contains `agent`, `key`, `work_id`, `parent_id`, `sources`,
`cutoff`, optional `checks`, `synthetic` and, for Scout, `portfolio_cards`.
Sources use the existing snapshot schema. The CLI opens the lifecycle database in
SQLite read-only mode; assurance writes go to a different output ledger. Use a
consistent frozen database snapshot rather than a concurrently changing live DB.

A `prepare` command accepts the keyword arguments of `freeze_packet()` as JSON.
The demo's worker packets show the full review schema. Criticism files contain a
list of `{check_id, criticism}`; optional rebuttals contain
`{check_id, explanation, anchors:[{source_key,pointer,quote}]}`.

## Separate reviewer-effectiveness diagnostic

`assurance_eval.py` freezes three REVIEW ARCHITECTURE conditions:
`single_prompt`, `coarse_pinned`, `assurance_minimal`.
These are separate from, and do not replace, the BusinessArticleBenchmark
fixed-lower, fixed-higher and static-routing conditions or its five paper gates.

Each arm receives the same frozen JSON evidence, checks, model configuration and
no model tools. Settings and policy hashes are pinned; total calls and costs are
to be measured, not assumed equal. A matched-budget comparison is separate.
No Coarse adapter is implemented or executed. Preserving its substantive pipeline
while enforcing identical evidence/tool restrictions needs explicit review;
a modified Coarse pipeline must be named as modified, not silently substituted.

The demo creates 12 original public synthetic packets (six parent sources, six
clean and six flawed variants across six families) and 36 prepared requests.
All packets remain development material. Evaluator answer records are written
outside `worker/` and `requests/`; worker construction never accepts adjudications.
This is logical file/interface separation, NOT an operating-system sandbox.
A later worker process must receive only its projected request, not the demo folder.

Attempt initiation precedes result import. Failed, malformed, unexecuted and
interrupted attempts remain distinguishable. Duplicate primary attempts are
rejected; unknown costs and human effort remain null rather than zero.

The scorer requires separate, packet-bound judgements for every criticism.
Matching the expected check ID alone earns no credit. Metrics include resolved
precision and bounds for unresolved judgements, unique consequential defects
found, complete check coverage, clean-case abstention, repairs fixed/newly
introduced, calls, known costs and human time. Duplicate comments cannot inflate
unique-defect recall. Adjudicators must judge redundant criticisms explicitly.

Reviewer/adjudicator IDs must differ, but identity and independence are asserted,
not authenticated. Public synthetic expected answers are not independent panel
judgements. Real-panel import needs a separately reviewed trusted boundary.

All variants of a parent source must share a split. There are only six public
synthetic parents here; inferential confidence intervals are suppressed. Paired
real-source inference and a predeclared smallest worthwhile gain remain future
study requirements, not implemented empirical results.

## Validation and the observed synthetic demonstration

75 new tests passed locally, including exact parent-core blob identity, cutoff
exclusion, source/packet tampering, synthetic-label preservation, protected-ID
boundaries, false criticism, unresolved semantics, interruption accounting,
repair harm, actual Ledger namespace adapters, Scout parent-vintage exclusion,
metric denominators, unknown costs, split leakage and CLI execution.
`compileall` passed. The demo ran twice identically in its regression test.

The offline demonstration detected six deliberately injected scoped defects,
left six clean variants without supported issues, withdrew a false criticism,
and detected a proposal that fixed one error while introducing another.
These are deterministic fault-injection checks, NOT model performance estimates.
All three model/comparator conditions remain unexecuted. Live model calls: 0.
External API spend: USD0 (GBP0). Total human effort is not measured.

The fetched parent `core.py` was checked byte-for-byte against Git blob
`134c691c999ace083259228be127eaabf49a71d0`. The local test workspace contained this
actual dependency and the new files, not the full legacy repository. The original
51-test lifecycle suite and live integrations were NOT rerun in this session.
No claim of whole-repository regression success is made.

## Hard exclusions and remaining work

SRO-001 and CEMENT-001 supplied work/parent/source IDs are refused. Protected SRO
repairs, answers and holdouts were not fetched or used. Real CEMENT evidence was
not imported. MISSOURI-001 remains synthetic calibration. The benchmark repository
and its frozen amendment are untouched.

No remote provider calls, unrestricted tools, paper submissions, preprint release,
registration, automatic merge or recurring monitoring are activated. Remote spend
is not authorised. Models/settings, independent real adjudication, a reviewed
provider/Coarse adapter and worker isolation are still required for a live study.

Source hashes ensure consistency, not authenticity. Archive proofs are assertions;
cutoffs do not remove model-training hindsight. Reserved-ID checks and rejection
of named answer fields are defence in depth, not semantic leak detection. Hostile
local administrators are outside the boundary. Do not provide protected material
to a worker, this demo, or the current local annotation scorer.
