#!/usr/bin/env python3
"""Authoritative evaluator for the SRO reconstruction pilot."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

REQUIRED_COLUMNS = [
    "cell_id",
    "record_state",
    "person_name_raw",
    "canonical_name",
    "status_at_date",
    "confidence",
    "former_military",
    "evidence_basis",
    "source_title",
    "source_url",
    "source_tier",
    "coding_note",
    "interval_row",
    "interval_id",
    "from_snapshot",
    "from_date",
]

IDENTITY_AND_EVIDENCE_COLUMNS = [
    "cell_id",
    "record_state",
    "person_name_raw",
    "canonical_name",
    "evidence_basis",
    "source_title",
    "source_url",
    "source_tier",
    "coding_note",
    "interval_row",
    "interval_id",
    "from_snapshot",
    "from_date",
]

MUTABLE_COLUMNS = ["status_at_date", "confidence", "former_military"]
ALLOWED_STATUSES = {"unresolved", "military", "civilian"}
CONFIDENCE_BY_TIER = {
    "official_direct": "high",
    "public_direct": "high",
    "official_context": "medium_high",
    "prior_curated_public_evidence": "medium_high",
    "public_context": "medium",
    "secondary_structured": "medium",
}


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise FileNotFoundError(f"CSV not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        rows = [{key: (value or "") for key, value in row.items()} for row in reader]
        return list(reader.fieldnames), rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _index_unique(rows: Iterable[dict[str, str]], label: str) -> dict[str, dict[str, str]]:
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        cell_id = row.get("cell_id", "")
        if not cell_id:
            raise ValueError(f"{label} contains a blank cell_id")
        if cell_id in indexed:
            raise ValueError(f"{label} contains duplicate cell_id {cell_id}")
        indexed[cell_id] = row
    return indexed


def _safe_workspace_path(workspace_dir: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        raise ValueError("manifest panel_path must be relative to the workspace")
    workspace = workspace_dir.resolve()
    resolved = (workspace / candidate).resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError as exc:
        raise ValueError("manifest panel_path escapes the workspace") from exc
    return resolved


def _private_labels_path(*, workspace_dir: Path, task_dir: Path, dataset_dir: Path) -> Path:
    override = os.environ.get("SRO_PRIVATE_LABELS", "").strip()
    if not override:
        raise ValueError("SRO_PRIVATE_LABELS must point to labels outside the agent workspace")
    labels_path = Path(override).resolve()
    for label, root in (
        ("workspace", workspace_dir.resolve()),
        ("task package", task_dir.resolve()),
        ("input dataset", dataset_dir.resolve()),
    ):
        try:
            labels_path.relative_to(root)
        except ValueError:
            continue
        raise ValueError(f"private labels must not be stored inside the {label}")
    return labels_path


def evaluate(
    *,
    artifact_path: Path,
    workspace_dir: Path,
    task_dir: Path,
    dataset_dir: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    _ = config
    if not artifact_path.is_file():
        raise FileNotFoundError(f"manifest not found: {artifact_path}")
    try:
        manifest = json.loads(artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed manifest JSON: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "1.0":
        raise ValueError("manifest schema_version must be '1.0'")
    panel_path = _safe_workspace_path(workspace_dir, str(manifest.get("panel_path", "")))

    baseline_path = dataset_dir / "public" / "panel_baseline.csv"
    labels_path = _private_labels_path(
        workspace_dir=workspace_dir, task_dir=task_dir, dataset_dir=dataset_dir
    )
    baseline_header, baseline_rows = _read_csv(baseline_path)
    candidate_header, candidate_rows = _read_csv(panel_path)
    labels_header, labels_rows = _read_csv(labels_path)

    baseline_missing = [column for column in REQUIRED_COLUMNS if column not in baseline_header]
    if baseline_missing:
        raise ValueError(f"baseline panel is missing columns: {', '.join(baseline_missing)}")
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in candidate_header]
    if missing_columns:
        raise ValueError(f"candidate panel is missing columns: {', '.join(missing_columns)}")
    if candidate_header != baseline_header:
        raise ValueError("candidate panel columns and order must match the baseline exactly")
    if "expected_status_at_date" not in labels_header:
        raise ValueError("private holdout labels are malformed")

    baseline = _index_unique(baseline_rows, "baseline")
    candidate = _index_unique(candidate_rows, "candidate")
    labels = _index_unique(labels_rows, "holdout labels")
    if set(candidate) != set(baseline):
        missing = sorted(set(baseline) - set(candidate))[:5]
        extra = sorted(set(candidate) - set(baseline))[:5]
        raise ValueError(f"candidate cell set differs from baseline; missing={missing}, extra={extra}")

    holdout_ids = {cell_id for cell_id, row in baseline.items() if row["record_state"] == "holdout"}
    if set(labels) != holdout_ids:
        raise ValueError("private holdout label cells do not match baseline holdout cells")

    locked_count = 0
    unresolved_count = 0
    attempted = 0
    correct = 0
    wrong: list[str] = []

    for cell_id, base_row in baseline.items():
        cand_row = candidate[cell_id]
        for column in IDENTITY_AND_EVIDENCE_COLUMNS:
            if cand_row[column] != base_row[column]:
                raise ValueError(f"{cell_id}: protected column changed: {column}")

        state = base_row["record_state"]
        raw_status = cand_row["status_at_date"].strip()
        status = raw_status.lower()
        if raw_status != status:
            raise ValueError(f"{cell_id}: status_at_date must use canonical lower case")
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"{cell_id}: unsupported status_at_date {status!r}")

        if state == "locked":
            locked_count += 1
            if any(cand_row[column] != base_row[column] for column in MUTABLE_COLUMNS):
                raise ValueError(f"{cell_id}: locked record changed")
            continue

        if state == "unresolved":
            unresolved_count += 1
            if any(cand_row[column] != base_row[column] for column in MUTABLE_COLUMNS):
                raise ValueError(f"{cell_id}: genuinely unresolved record changed in benchmark mode")
            continue

        if state != "holdout":
            raise ValueError(f"{cell_id}: unsupported record_state {state!r}")

        if status == "unresolved":
            if cand_row["confidence"].strip() or cand_row["former_military"].strip():
                raise ValueError(f"{cell_id}: abstained holdout must keep confidence and former_military blank")
            continue

        attempted += 1
        source_url = cand_row["source_url"].strip()
        if not source_url.startswith("https://"):
            raise ValueError(f"{cell_id}: attempted holdout lacks an eligible HTTPS source")
        expected_confidence = CONFIDENCE_BY_TIER.get(cand_row["source_tier"].strip())
        if not expected_confidence:
            raise ValueError(f"{cell_id}: attempted holdout uses an unsupported source tier")
        if cand_row["confidence"].strip() != expected_confidence:
            raise ValueError(
                f"{cell_id}: confidence must be {expected_confidence!r} for source tier "
                f"{cand_row['source_tier']!r}"
            )
        if cand_row["former_military"].strip():
            raise ValueError(f"{cell_id}: former_military is outside the pilot target and must remain blank")

        expected_status = labels[cell_id]["expected_status_at_date"].strip().lower()
        if status == expected_status:
            correct += 1
        else:
            wrong.append(cell_id)

    if wrong:
        preview = ", ".join(wrong[:5])
        raise ValueError(f"incorrect holdout classifications ({len(wrong)}): {preview}")

    holdout_total = len(holdout_ids)
    coverage = correct / holdout_total if holdout_total else 0.0
    return {
        "metric": {"name": "verified_holdout_cells", "value": float(correct)},
        "valid": True,
        "authoritative": True,
        "holdout_total": holdout_total,
        "attempted_holdout_cells": attempted,
        "verified_holdout_cells": correct,
        "holdout_coverage": coverage,
        "holdout_remaining": holdout_total - correct,
        "locked_rows_preserved": locked_count,
        "genuine_unresolved_rows_preserved": unresolved_count,
        "baseline_sha256": _sha256(baseline_path),
        "candidate_sha256": _sha256(panel_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--task-dir", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = evaluate(
            artifact_path=args.artifact,
            workspace_dir=args.workspace,
            task_dir=args.task_dir,
            dataset_dir=args.dataset,
            config={},
        )
    except Exception as exc:  # command-line diagnostics
        print(f"sro_reconstruction_eval error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
