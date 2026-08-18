# SRO ScienceFlow pilot report

**Date:** 18 August 2026  
**Source:** `public_reconstruction/data/person_status_evidence_max.csv`  
**Source SHA-256:** `cd4364b254ec2265bbe75bad5dcc23fba1268f44230acc404b3d320b49d55d07`

## Decision

Proceed to a controlled ScienceFlow worker run. The benchmark and evaluator are working against the real SRO reconstruction, and the safeguards reject every tested route that could corrupt the accepted panel. The current task is suitable for testing recoverable execution and stage admission. It is not yet a test of open-web evidence discovery.

## Benchmark construction

The source contains 344 MOD interval-person evidence records. A deterministic seed (`20260818`) selects 64 previously verified records as hidden holdouts:

- 32 military and 32 civilian records;
- at least one selected record from every snapshot represented in the eligible source-backed cases, followed by hash-ranked filling;
- 244 other verified records locked against modification;
- 36 genuinely unresolved records frozen outside the score.

The public baseline SHA-256 is `d29c8484452cc98c44836385857f41c5e9d0238fc3db913e168b85b74ca77f7a`. Private labels have SHA-256 `6774d75f193e09b37e2c38c0fb594edca273446d9feca6b6091a7d95b8feb24a` and are not committed or copied into ScienceFlow.

## Evaluator design

The evaluator returns the number of correctly resolved holdout cells. It treats the score as authoritative and maximises it subject to hard validity gates. A wrong attempted classification invalidates the complete candidate. Abstention remains valid and scores zero for that cell.

The evaluator rejects:

- changes to locked records or the 36 genuinely unresolved records;
- changes to names, interval identifiers, evidence, source fields or record state;
- duplicate, missing or additional cells;
- schema or column-order changes;
- non-canonical status values or confidence inconsistent with source tier;
- manifest paths outside the workspace;
- private labels stored inside the workspace, task package or input dataset.

## Results

| Check | Result |
|---|---:|
| Original SRO reconstruction tests | 10 passed |
| Pilot evaluator tests | 11 passed |
| Baseline candidate | 0 of 64, valid |
| Conservative keyword reference | 53 of 64, valid |
| Reference coverage | 82.8125% |
| Incorrect reference classifications | 0 |
| Locked records preserved | 244 |
| Genuinely unresolved records preserved | 36 |

The reference candidate SHA-256 is `00cf4a99082d99a11fbbf2e6b1014016dc55945dec58c33de8dc5a35b5a6192b`. It abstains on 11 records where the visible text contains competing cues or only contextual evidence.

## Acceptance test for the worker run

A successful first ScienceFlow run should meet all five conditions:

1. score above 53, with 64 as the target;
2. zero incorrect attempted classifications;
3. preserve all 244 locked and 36 genuinely unresolved records;
4. keep the private-label file outside every agent-accessible directory;
5. reproduce its best admitted candidate after interruption and resume.

The fifth condition is the specific test of ScienceFlow's recoverable-stage design. Performance alone would not distinguish it from an ordinary classification script.

## Interpretation limits

The benchmark draws holdouts from classifications already verified in the project. It demonstrates controlled reconstruction, not discovery of new facts. The source evidence remains visible, so the task measures contextual classification and disciplined abstention. It does not validate the paper's causal mechanism, and its score should not be reported as evidence about SRO turnover or military career management.

A later retrieval benchmark can mask the evidence and source fields, accept only pre-registered source classes and send alternative sources for human review. Only after that stage should the system be allowed to propose additions to the genuinely unresolved set.

## Execution status

The data preparation, hidden evaluator, reference route, mutation tests and source-pack regression tests have been run. The full ScienceFlow LNR worker has not been run because model-provider credentials are deliberately absent from this execution environment. The pull request therefore remains a draft until a credentialled worker run produces a recoverable admitted stage.
