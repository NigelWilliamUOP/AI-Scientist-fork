# ScienceFlow pilot for the UK defence SRO reconstruction

This directory turns one part of the Senior Responsible Owner (SRO) reconstruction into a recoverable, machine-checkable research task. It is an overlay for [ScienceFlow](https://github.com/science-learner/ScienceFlow), kept inside this repository so the pilot can be reviewed without modifying an upstream checkout.

## What the pilot tests

The source panel contains 344 MOD interval-person records with public evidence about whether each SRO was serving military personnel or a civilian at the relevant snapshot. The preparation script creates a deterministic benchmark:

- 64 previously verified cells are masked as holdouts, split evenly between military and civilian cases;
- 244 verified cells are locked and must remain byte-for-byte unchanged in protected fields;
- 36 genuinely unresolved cells are frozen and excluded from the automated score;
- private holdout labels remain outside the agent workspace, task package and input dataset.

The authoritative metric is `verified_holdout_cells`. Abstention is allowed. One incorrect holdout classification invalidates the candidate, so coverage cannot be increased by guessing.

This is a retrodictive execution pilot. It tests whether an agent can reconstruct known classifications while respecting provenance and locked findings. It does not establish the military career mechanism and it does not yet test open-web discovery of genuinely missing evidence.

## Current result

| Candidate | Valid cells | Coverage | Wrong cells | Locked rows changed | Unresolved rows changed |
|---|---:|---:|---:|---:|---:|
| Unchanged baseline | 0 / 64 | 0.0% | 0 | 0 | 0 |
| Conservative keyword reference | 53 / 64 | 82.8% | 0 | 0 | 0 |

The reference route leaves 11 ambiguous cells unresolved. A ScienceFlow run should first beat 53 without an error, then target 64.

## Files

```text
experimental/sro_scienceflow_pilot/
├── README.md
├── PILOT_REPORT.md
├── requirements.txt
├── scripts/
│   ├── prepare_pilot.py
│   ├── evaluate_prepared.py
│   └── install_overlay.py
├── scienceflow_overlay/
│   ├── scienceflow/config/examples/tasks_sro_reconstruction_pilot.yaml
│   └── tasks/opt_solver/sro-reconstruction-pilot/
│       ├── description_lite.md
│       ├── evaluator.py
│       └── task.yaml
├── tests/test_evaluator.py
└── pilot_results/
    ├── pilot_metadata.json
    ├── baseline_evaluation.json
    ├── reference_evaluation.json
    └── validation_summary.json
```

Prepared data, runtime workspaces and private labels are excluded from Git.

## Reproduce the benchmark

Use Python 3.11 or later. From this directory:

```bash
python -m pip install -r requirements.txt

python scripts/prepare_pilot.py \
  --pack-root /path/to/SRO_Public_Reconstruction_Research_Pack_2015_2026/public_reconstruction

export SRO_PRIVATE_LABELS="$(pwd)/.private/holdout_labels.csv"
python scripts/evaluate_prepared.py
python -m pytest -q
```

`prepare_pilot.py` checks the source schema, creates stable cell identifiers, selects a balanced and snapshot-spanning holdout, masks the labels, writes a starter candidate and creates a conservative reference candidate. Re-running it against the same source file produces the same holdout and hashes.

## Install into ScienceFlow

Prepare the benchmark before installation. Then run:

```bash
python scripts/install_overlay.py --scienceflow-root /path/to/ScienceFlow
```

The installer copies the task package, example manifest and prepared public data. It deliberately does not copy private labels. In the ScienceFlow checkout:

```bash
export SRO_PRIVATE_LABELS=/absolute/path/to/sro_scienceflow_pilot/.private/holdout_labels.csv

uv run python -m scienceflow.cli parallel \
  -m scienceflow/config/examples/tasks_sro_reconstruction_pilot.yaml \
  -j 1
```

The example uses two CPU workers, a 45-minute worker budget within a one-hour task limit, the task-package evaluator and a high-validity stage gate. Provider credentials and model settings still need to be supplied through the ScienceFlow environment.

## Admission contract

A candidate is admitted only when it:

1. preserves the complete cell set and exact column order;
2. leaves protected identity, interval, evidence, source and record-state fields unchanged;
3. leaves all locked and genuinely unresolved records unchanged;
4. edits only `status_at_date` and `confidence` for holdout rows;
5. uses canonical lower-case statuses and confidence derived from the fixed source-tier rule;
6. contains no incorrect attempted holdout;
7. reads private labels from an external path that is outside the workspace, task package and input dataset.

The unit tests exercise each of these failure routes. The original SRO reconstruction pack's ten tests also pass unchanged.

## Next experimental stage

A second benchmark should mask the supporting evidence and source URL as well as the status. That would test public-source retrieval and provenance reconstruction rather than classification from supplied evidence. Newly discovered evidence should enter a human-adjudicated queue before it can alter the locked panel.
