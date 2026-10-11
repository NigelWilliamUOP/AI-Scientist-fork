# Arithmetic gate audit and hardening, 11 October 2026

Audited PR #7 at `6f3c81a321f932bb49c970c1d92648a95ddb51a2` and PR #8 at
`b63a64f6d117d7b92c3dfd2481bc17e58f6c332f`. Independently reran their package
suites on Python 3.12.14: 187 and 205 tests passed respectively.
GitHub returned no submitted reviews, inline review comments, commit statuses
or PR-triggered workflow runs for those two heads. Sourcery guides and imported
validation receipts were not treated as independent approval.

## Reproduced gaps

- A corrupted `sample_sd=999` survived same-route replay, obtained
  `numerically_checked` and reached manuscript generation.
- A fractional observation count `3.0000000001` passed against exact count 3.
- A verifier RuntimeError blocked execution but left no terminal study result.

## Resulting implementation

The independent standard-library route now checks sample standard deviation
using rational inequalities on exact sample variance. It does not repeat the
original floating-point square-root algorithm. Counts require integer type and
exact equality. Unexpected fields and changed OLS identification metadata fail.

Analysis/check exceptions and cooperative deadline expiry record terminal
abstentions before drafting. Process interruption preserves existing checkpoints;
uncertain model calls still require Session reconciliation. The report reaches
writer and critic and is appended to the manuscript by trusted code.

Study policy and seals freeze actual code fingerprints. Ledger integrity is
checked before cached studies/checks are reused. Changed code, source or policy
requires a new workspace; old histories are retained, never silently migrated.

## New software controls

The final local package suite passes 231 tests, including 26 new audit tests.
All 16 declared numerical mutations were detected before drafting;
two clean descriptive/OLS controls passed. The original computation returns the
same mutated output on both calls, so same-route replay alone accepts each error.
Compilation and whitespace checks pass.

Controls include every supported returned numerical field, unexpected output,
integer/count types, negative standard deviation, tolerance boundaries,
large-integer cancellation, large standard deviation without square overflow,
subnormal values, missing observations, constant and nearly constant predictors,
constant outcomes, large predictor offsets and floating-point overflow.

Recovery tests interrupt after the seal, after verification and immediately
before drafting. Fresh-process tests reuse an unchanged run, and separate
workspaces reproduce analysis, verification report and manuscript. A changed
runtime fingerprint or admitted source cannot reuse a cached study.

Run:

```bash
python -m unittest discover -s research_campaigns/tests -q
python -m research_campaigns.arithmetic_mutations
python -m compileall -q research_campaigns
```

The adjacent mutation JSON is a measured synthetic control report. It is not
independent scientific validation or approval. CI reruns these controls and
retains a fresh report. No remote model calls or external model spend occur.

## Boundaries and remaining work

Verification remains opt-in. Its ten-second deadline is cooperative inside the
bounded standard-library calculation, not an OS-enforced process timeout.
Both routes share admitted inputs. Neither checks measurement truth, empirical
replication, causality or the semantic correctness of generated prose.

No upstream BootLoops engine was added or executed by this hardening. The pinned
upstream precision-linter self-test was independently rerun (11 passes), but
Baller's numerical engine and the full upstream suite were not rerun. Imported
42/4/3 package outcomes remain historical assertions with documented failures.
General simulation, interval/ODE calculations and upstream resource controls
remain unsupported by Study Producer. Do not relabel these capabilities validated.

A separate simulation adapter should start with one real simulation kernel,
analytical references, precision escalation, planted numerical failures, enforced
runtime limits and independent review. This comparator remains useful for the
supported descriptive/OLS fields. New CI results and substantive code review
must be assessed before promotion from draft or merging.

## Dependency-aware merge sequence

Current ancestry: #2 -> #3 -> #6 -> #7 -> #8, with #2 -> #5 -> #8 as the
second path. PR #8's audited head has #7 and #5 as its two parents. Once each
PR satisfies its own checks and review, use merge commits and retain branches:

1. Merge #2 into main.
2. Retarget #3 to main, inspect its residual diff, validate and merge.
3. Retarget #5 to main, inspect its residual diff, validate and merge.
4. Retarget #6 to main, validate and merge.
5. Retarget #7 to main, validate and merge.
6. Retarget #8 to main. Verify the residual diff contains only its integration
   and this hardening, rerun checks on that exact head and merge after review.

Re-read exact head SHAs immediately before merging and use
`gh pr merge N --merge --match-head-commit REVIEWED_FULL_SHA`.
A squash/rebase merge needs explicit restacking and fresh diff review.
No merge or approval was performed during this audit/hardening.
