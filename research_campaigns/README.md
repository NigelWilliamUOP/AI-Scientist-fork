# Three research-lifecycle agents, version 0.2.0

Executable first implementation for `NigelWilliamUOP/AI-Scientist-fork`.
Adds a self-contained package; it does not modify the legacy launchers, SRO pilot,
research manuscripts, accepted results, or evaluation holdouts.

## What is implemented

| Agent | Command | Implemented behaviour |
|---|---|---|
| Study Producer | `study` | Bounded method selection, frozen design, actual descriptive/OLS calculation, arithmetic replay, manuscript/claim package, separate critic, valid abstention. |
| Programme Steward | `programme-init`, `programme-update`, `programme-amend` | Frozen baseline and predictions, dated observation vintages, new-period/revision distinction, forecast compatibility tests, optional model interpretation, exploratory amendments. |
| Opportunity Scout | `scout`, `replay` | Claim-specific proposals, dataset and join prechecks, rejected lookalikes, contradictions, existing-programme routing, bounded review queue and date-locked replay. |

All three use a common result envelope. Execution completion, scientific validity
and journal-readiness are separate. No producing agent can award independent
journal-readiness. Every result remains scientifically unverified until external
review. Opportunity handovers are queued, not automatically executed or promoted.

The package runs on Python 3.10+ with the standard library only. It imports none
of the legacy GPU/model dependencies. Run commands from the repository root.

## Run everything without credentials

```bash
python -m unittest discover -s research_campaigns/tests -v
python -m research_campaigns demo --output ./research_campaigns_runs/demo
```

The demonstration creates an entirely synthetic bounded study, a programme with
an original release, revision and subsequent period, and a five-cutoff scout
replay. It costs zero external model/API charges. The deterministic baseline is
an executable test comparator, **not an LLM or evidence of autonomous discovery**.
The study's synthetic mean is 25 days; it is not a Missouri empirical result.

The programme should report independent periods `[1, 1, 2]` and observation
vintages `[1, 2, 3]`. The replay should admit `[0, 1, 1, 1, 2]` candidates at the
five cutoffs, rejecting the approval-timing proxy and withholding future work.
These outcomes exercise explicit fixture rules; they do not measure discovery
quality or acceptance by a journal.

## Invoke each agent separately

After creating the demo inputs, these commands run each public entry point:

```bash
python -m research_campaigns study \
  --brief research_campaigns_runs/demo/inputs/brief.json \
  --sources research_campaigns_runs/demo/inputs/sources.json \
  --workspace research_campaigns_runs/study --synthetic

python -m research_campaigns programme-init \
  --baseline research_campaigns_runs/demo/inputs/baseline.json \
  --workspace research_campaigns_runs/programme

python -m research_campaigns programme-update \
  --programme-id PROGRAMME-DEMO \
  --sources research_campaigns_runs/demo/inputs/programme_sources.json \
  --cutoff 2026-03-28T12:00:00Z \
  --workspace research_campaigns_runs/programme --synthetic

python -m research_campaigns scout \
  --portfolio research_campaigns_runs/demo/inputs/portfolio.json \
  --sources research_campaigns_runs/demo/inputs/sources.json \
  --cutoff 2026-04-30T12:00:00Z \
  --workspace research_campaigns_runs/scout --synthetic

python -m research_campaigns replay \
  --portfolio research_campaigns_runs/demo/inputs/portfolio.json \
  --sources research_campaigns_runs/demo/inputs/sources.json \
  --cutoffs research_campaigns_runs/demo/inputs/cutoffs.json \
  --workspace research_campaigns_runs/replay --synthetic

python -m research_campaigns audit --workspace research_campaigns_runs/study
```

`--synthetic` explicitly authorises fixtures. Remove it for actual secondary data;
do not relabel fixtures as observed data. Outputs go into content-addressed
artifact directories, with a SQLite event ledger in each workspace. Preserve the
workspace when resuming exactly the same run. A changed brief, admitted evidence,
provider, budget or runtime fingerprint needs a separately versioned workspace;
an old completed result must not silently answer a new question.

## Live model configuration

The provider interface is replaceable. The shipped remote adapter uses OpenAI's
Responses API with JSON output, `store=false`, no external tools, no prior
response IDs, and no server-side conversation state. No live model call was
performed during the build. The adapter was tested against a mocked response.

Set `OPENAI_API_KEY` in the process environment. Never put it in a JSON brief,
source manifest, command-line argument or repository. For `study`,
`programme-update`, `scout` or `replay`, add:

```text
--provider responses --model YOUR_APPROVED_MODEL_ID
--allow-network --max-usd YOUR_APPROVED_RUN_CEILING
--input-rate CURRENT_USD_PER_MILLION_INPUT_TOKENS
--output-rate CURRENT_USD_PER_MILLION_OUTPUT_TOKENS
```

No model identifier or current token price is assumed. Rates must be supplied by
the operator. The default budget is zero. Remote transmission of sources marked
`authorised` also requires `--allow-private-to-model`, representing a separate
approval of this processor for that evidence.

The runtime reserves a conservative token-priced cost before each call, enforces
a call ceiling, records returned usage/model identifiers, and stops after an
unexpected usage overrun. These are estimates, **not provider invoices**. Use
account-side spending controls too. A timeout or malformed remote response can
leave an uncertain charge; the runtime keeps the reservation and refuses further
calls rather than retry and potentially double-charge. Such incidents need
operator/provider-log reconciliation. This release deliberately has no automatic
financial reconciliation or retry facility.

## Evidence input contract

A source list contains immutable snapshots with:

```text
source_id, version, available_at, captured_at, retrieved_at,
locator, kind, access, payload, sha256
```

`sha256` is the SHA-256 of the UTF-8 canonical JSON `payload`, using
`research_campaigns.core.digest`. It is **not** a claimed hash of a PDF or other
binary that has not been retrieved. The acquisition connector separately records
`raw_sha256` for actual downloaded bytes. Data dictionaries and rows belong
inside the hashed payload, not in mutable metadata alongside it.

The permitted kinds are `observed`, `derived`, `assumed`, `synthetic`,
`literature_inference`, and `unavailable`. Access is `public`, `authorised`, or
`synthetic`; synthetic evidence must retain both synthetic labels. Study inputs
use `payload.rows`. Scout datasets also need `payload.schema` (variables, join
keys, unit, population, geography and frequency), `primary_source`, and actual
rows. Programme sources use `payload.observations` with series ID, period,
frequency, unit and value. No interpolation is performed.

Portfolio records carry a work ID, version, known/captured dates, title, claims,
and a checksum over all fields except `sha256` and `archive_proof`. Each scoutable
claim needs an exact claim ID and explicit `required_data` requirements. Set
`owner_programme` on an already-owned claim to route routine releases back to its
steward. Contradictions go to verification first. The built-in precheck tests
actual rows and declared dictionaries; it does not certify that two similarly
named measurements are scientifically equivalent.

The synthetic inputs produced by `demo` are executable examples of these formats.
They are not substitutes for the actual Missouri MO01 and CEMENT Phase 2 files.
Those packages were not imported or rerun in this implementation session.

## Date-locked replay

Replay takes increasing, timezone-aware ISO cutoffs. For each cutoff it builds a
fresh scout state and supplies only the latest eligible vintage of each source,
plus the latest eligible version of each portfolio work. Both availability and
capture dates must precede the cutoff. Retrieval can occur later when the bytes
come from an earlier archive. Real historical snapshots and work cards also need
an `archive_proof` containing a locator and matching canonical-content checksum.
This is a recorded provenance assertion, not independent authentication of the
archive service or its timestamp.

The worker never sees the list of excluded future sources, later portfolio notes,
replay results from later cutoffs, or an evaluator's labels. The orchestrator
retains exclusion logs outside the worker context. A shared budget covers the
whole replay; it is not reset at every cutoff. Source capture is a separate
command and is never invoked by replay. An optional remote model has only the
inference endpoint, with no browsing or execution tool in its request.

A date lock cannot remove an LLM's knowledge from training. Treat a real replay
as a test of source-controlled recommendations, not proof of historical
ignorance. Entity masking and a held-out prospective discovery-quality evaluation
are not implemented. First-detection dates are reported; precision/recall are
not invented without an external adjudicated opportunity set.

## Source acquisition and scheduling

`ingest --watchlist FILE --workspace NEW_CAPTURE_DIR --allow-network` captures up
to 20 approved HTTPS sources. The watchlist supplies `allowed_hosts` and `sources`
with `source_id`, `url`, `format`, `storage_authorised`, and rights notes. The
`normalised_json` format supports structured datasets. Other UTF-8 formats are
captured as text leads; they do not pass as executable datasets without a real
data path. The connector rejects non-HTTPS, unauthorised hosts, redirects,
loopback/private/reserved destinations, and oversized bodies.

Capture sets availability to when this runtime first observed those bytes. It
does not assert first publication or backdate a newly downloaded page. A capture
report can be passed directly to `--sources`, preserving retrieval errors.
Historical evidence should instead be imported as dated archived snapshots with
provenance. Do not use an unrestricted live crawler inside historical replay.

This release does not schedule anything, scan the whole web, fetch paid data,
contact authors, post a preprint, register a protocol, or submit a paper. The
narrow, operator-approved feed is intentional. No live source fetch was executed
in the offline build environment.

## Research and resource boundaries

The audited method registry contains descriptive statistics and one-variable
ordinary least squares (OLS). OLS results are labelled descriptive association.
There is no generated-code execution, shell tool, arbitrary import, or implicit
call to the legacy launcher. Integrating the Missouri fundability optimiser
requires a reviewed adapter and its actual regression data; it is not replaced
by the synthetic arithmetic example.

The programme preserves the imported baseline and accepts amendments only as
exploratory proposals. An imported `registered` status needs a receipt and is
explicitly labelled operator-asserted, not independently checked. Interval
compatibility tests do not confirm causal mechanisms. Model interpretations are
separate unverified candidates and cannot set empirical confirmation to true.
The original model output is retained even when a gate rejects it.

Human effort is logged separately:

```bash
python -m research_campaigns human-time \
  --workspace research_campaigns_runs/study \
  --event-id independent-review-001 --category evaluation --minutes 12
```

Categories are production, access support, verification, evaluation, and rework.
Use one unique event ID per actual interval of work. Missing human time is not
asserted to be zero; completeness remains unasserted. Independent journal review
and total cost per journal-ready output are external evaluation tasks, not an
LLM's self-score.

The ledger uses SQLite transactions, update/delete-denial triggers and hash
chaining. This is a model-action boundary and a tamper-evident history, not an OS
sandbox against malicious local code or a database administrator. Keep holdouts,
credentials and unpublished institutional data outside authorised manifests and
out of public Git. A party with full filesystem access can replace a complete
ledger; an independently stored head hash is needed for stronger tamper evidence.

## Test coverage and external validation still needed

`test_agents.py` implements all 16 behaviour scenarios from the design pack,
plus temporal, proxy, confidentiality, budget and permission tests.
`test_integration.py` exercises each command-line agent, replay resume, immutable
inputs, interpretation gates and a mocked Responses payload. Tests run offline
using synthetic data and the deterministic comparator. The complete build report
and logs are delivered with this implementation.

Still unexecuted: real provider connectivity/billing, live watchlist integration,
actual Missouri/CEMENT regression, independent scientific or journal review,
historical archive authentication, and discovery-quality evaluation on a held-out
or prospective set. The legacy launcher's previously reported failure paths have
not been patched as an incidental side effect of adding this package.

Technical references checked while building:
- Python SQLite documentation: https://docs.python.org/3/library/sqlite3.html
- OpenAI text generation: https://developers.openai.com/api/docs/guides/text

Repository state: separate implementation branch and draft pull request; no
automatic merge, public research release or recurring scan is implied.
