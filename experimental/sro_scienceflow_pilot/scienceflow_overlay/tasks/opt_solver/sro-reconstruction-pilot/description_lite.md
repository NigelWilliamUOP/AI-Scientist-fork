# UK defence SRO panel repair pilot

Repair masked person-status cells in a public reconstruction of the UK Government Major Projects Portfolio Senior Responsible Owner panel.

## Objective

Maximise `verified_holdout_cells`. A cell scores only when its classification matches a hidden, previously verified label. One incorrect classification invalidates the candidate. Abstention is permitted.

## Non-negotiable constraints

1. Preserve every row and every `cell_id` in `public/panel_baseline.csv`.
2. Do not change identity, interval, evidence, source or record-state fields.
3. Do not change rows marked `locked` or `unresolved`.
4. Edit only `status_at_date` and `confidence` for rows marked `holdout`.
5. Use only `military`, `civilian` or `unresolved` for `status_at_date`.
6. Attempt a holdout only when the supplied evidence is unambiguous and has an HTTPS source URL.
7. Set confidence from source tier, rather than inventing it:
   - `official_direct` or `public_direct` -> `high`
   - `official_context` or `prior_curated_public_evidence` -> `medium_high`
   - `public_context` or `secondary_structured` -> `medium`
8. Leave `former_military` unchanged. It is not part of this pilot target.

## Required artefacts

Write a full reconstructed panel to `artifacts/reconstructed_panel.csv` and a manifest to `artifacts/result_manifest.json`:

```json
{
  "schema_version": "1.0",
  "panel_path": "artifacts/reconstructed_panel.csv"
}
```

Start by copying the baseline panel. Make conservative edits only to masked holdout rows. The evaluator rejects duplicate or missing cells, path traversal, altered locked records, changes to genuinely unresolved records, unsupported confidence values and any wrong holdout classification.
