#!/usr/bin/env python3
"""Prepare a masked, machine-checkable SRO panel repair benchmark."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Iterable

HOLDOUT_SIZE = 64
SEED = "20260818"
CONFIDENCE_BY_TIER = {
    "official_direct": "high",
    "public_direct": "high",
    "official_context": "medium_high",
    "prior_curated_public_evidence": "medium_high",
    "public_context": "medium",
    "secondary_structured": "medium",
}

CIVILIAN_PATTERNS = [
    r"\bcivilian\b",
    r"\bcivil service\b",
    r"\bcivil servant\b",
    r"\bsenior civil[- ]service\b",
    r"\bsenior civil servant\b",
    r"\bscs[123]\b",
    r"\bnon[- ]military\b",
    r"\broyal fleet auxiliary personnel are civilians\b",
    r"\bcivilian career\b",
    r"\bserving as a civilian\b",
    r"\bgovernment digital roles\b",
    r"\bchief executive of de&s\b",
]
MILITARY_PATTERNS = [
    r"\bserving officer\b",
    r"\bserving military\b",
    r"\broyal navy service\b",
    r"\bbritish army\b",
    r"\broyal air force\b",
    r"\barmy service\b",
    r"\braf\b",
    r"\barmy officer\b",
    r"\bnaval officer\b",
    r"\bair chief marshal\b",
    r"\bair marshal\b",
    r"\bair vice[- ]marshal\b",
    r"\bvice admiral\b",
    r"\brear admiral\b",
    r"\badmiral\b",
    r"\blieutenant general\b",
    r"\bmajor general\b",
    r"\bgeneral(?: sir| dame| [a-z])\b",
    r"\bbrig(?:adier)?\b",
    r"\bcommodore\b",
    r"\bgroup captain\b",
    r"\bcaptain royal navy\b",
    r"\bcommander\b",
    r"\blieutenant commander\b",
    r"\bcolonel\b",
    r"\bof-[5-9]\b",
    r"\bmilitary officer\b",
    r"\bair cdre\b",
    r"\btwo-star cohort\b",
]


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"missing CSV header: {path}")
        return list(reader.fieldnames), [{k: (v or "") for k, v in row.items()} for row in reader]


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cell_id(row: dict[str, str]) -> str:
    raw = "|".join([row.get("interval_row", ""), row.get("canonical_name", ""), row.get("from_date", "")])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def rank_key(row: dict[str, str]) -> str:
    raw = f"{SEED}|{row['cell_id']}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def choose_holdout(rows: list[dict[str, str]], total: int) -> set[str]:
    if total % 2:
        raise ValueError("holdout size must be even")
    per_status = total // 2
    chosen: set[str] = set()
    for status in ("military", "civilian"):
        eligible = [
            row
            for row in rows
            if row["status_at_date"] == status
            and row["source_url"].startswith("https://")
            and row["source_tier"] in CONFIDENCE_BY_TIER
        ]
        snapshots = sorted({row["from_snapshot"] for row in eligible})
        for snapshot in snapshots:
            options = sorted((row for row in eligible if row["from_snapshot"] == snapshot), key=rank_key)
            if options and len(chosen) < total:
                chosen.add(options[0]["cell_id"])
        status_chosen = {row_id for row_id in chosen if any(r["cell_id"] == row_id and r["status_at_date"] == status for r in eligible)}
        remaining = sorted((row for row in eligible if row["cell_id"] not in chosen), key=rank_key)
        for row in remaining:
            if len(status_chosen) >= per_status:
                break
            chosen.add(row["cell_id"])
            status_chosen.add(row["cell_id"])
        if len(status_chosen) != per_status:
            raise ValueError(f"could not select {per_status} {status} holdout rows")
    if len(chosen) != total:
        raise ValueError(f"holdout selection produced {len(chosen)} rows, expected {total}")
    return chosen


def conservative_status(text: str) -> str:
    value = text.lower()
    civilian = any(re.search(pattern, value) for pattern in CIVILIAN_PATTERNS)
    military = any(re.search(pattern, value) for pattern in MILITARY_PATTERNS)
    if civilian == military:
        return "unresolved"
    return "civilian" if civilian else "military"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack-root", required=True, type=Path, help="Path to the public_reconstruction directory.")
    parser.add_argument(
        "--pilot-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Pilot repository directory (default: inferred).",
    )
    parser.add_argument("--holdout-size", type=int, default=HOLDOUT_SIZE)
    args = parser.parse_args()

    pack_root = args.pack_root.resolve()
    pilot_root = args.pilot_root.resolve()
    source_path = pack_root / "data" / "person_status_evidence_max.csv"
    if not source_path.is_file():
        raise SystemExit(f"source evidence file not found: {source_path}")

    source_header, source_rows = read_csv(source_path)
    required = {
        "person_name_raw", "canonical_name", "status_at_date", "confidence", "former_military",
        "evidence_basis", "source_title", "source_url", "source_tier", "coding_note",
        "interval_row", "interval_id", "from_snapshot", "from_date",
    }
    missing = sorted(required - set(source_header))
    if missing:
        raise SystemExit(f"source evidence missing columns: {missing}")

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for source_row in source_rows:
        row = dict(source_row)
        row["cell_id"] = cell_id(row)
        if row["cell_id"] in seen:
            raise SystemExit(f"duplicate generated cell_id: {row['cell_id']}")
        seen.add(row["cell_id"])
        rows.append(row)

    holdout_ids = choose_holdout(rows, args.holdout_size)
    labels: list[dict[str, str]] = []
    visible: list[dict[str, str]] = []
    for row in rows:
        out = dict(row)
        if row["cell_id"] in holdout_ids:
            labels.append(
                {
                    "cell_id": row["cell_id"],
                    "expected_status_at_date": row["status_at_date"],
                    "original_confidence": row["confidence"],
                    "source_tier": row["source_tier"],
                    "from_snapshot": row["from_snapshot"],
                }
            )
            out["record_state"] = "holdout"
            out["status_at_date"] = "unresolved"
            out["confidence"] = ""
            out["former_military"] = ""
        elif row["status_at_date"] in {"military", "civilian"}:
            out["record_state"] = "locked"
        else:
            out["record_state"] = "unresolved"
        visible.append(out)

    fieldnames = ["cell_id", "record_state"] + source_header
    data_root = pilot_root / "data" / "benchmark"
    public_dir = data_root / "public"
    starter_dir = data_root / "starter" / "artifacts"
    reference_dir = pilot_root / "reference_workspace" / "artifacts"
    private_dir = pilot_root / ".private"

    if data_root.exists():
        shutil.rmtree(data_root)
    if reference_dir.parent.exists():
        shutil.rmtree(reference_dir.parent)
    private_dir.mkdir(parents=True, exist_ok=True)

    baseline_path = public_dir / "panel_baseline.csv"
    write_csv(baseline_path, fieldnames, visible)
    write_csv(
        private_dir / "holdout_labels.csv",
        ["cell_id", "expected_status_at_date", "original_confidence", "source_tier", "from_snapshot"],
        labels,
    )

    starter_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(baseline_path, starter_dir / "reconstructed_panel.csv")
    manifest = {"schema_version": "1.0", "panel_path": "artifacts/reconstructed_panel.csv"}
    (starter_dir / "result_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    reference_rows = [dict(row) for row in visible]
    for row in reference_rows:
        if row["record_state"] != "holdout":
            continue
        prediction = conservative_status(" ".join([row["evidence_basis"], row["source_title"], row["coding_note"]]))
        if prediction == "unresolved":
            continue
        row["status_at_date"] = prediction
        row["confidence"] = CONFIDENCE_BY_TIER[row["source_tier"]]
    reference_dir.mkdir(parents=True, exist_ok=True)
    write_csv(reference_dir / "reconstructed_panel.csv", fieldnames, reference_rows)
    (reference_dir / "result_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    state_counts = Counter(row["record_state"] for row in visible)
    holdout_status_counts = Counter(label["expected_status_at_date"] for label in labels)
    holdout_snapshot_counts = Counter(label["from_snapshot"] for label in labels)
    metadata = {
        "schema_version": "1.0",
        "seed": SEED,
        "source_file": str(source_path.relative_to(pack_root)),
        "source_sha256": sha256_file(source_path),
        "rows": len(visible),
        "record_state_counts": dict(sorted(state_counts.items())),
        "holdout_size": len(labels),
        "holdout_status_counts": dict(sorted(holdout_status_counts.items())),
        "holdout_snapshot_counts": dict(sorted(holdout_snapshot_counts.items())),
        "baseline_sha256": sha256_file(baseline_path),
        "private_labels_sha256": sha256_file(private_dir / "holdout_labels.csv"),
        "selection": "balanced by military/civilian, one deterministic row per available snapshot before hash-ranked fill",
        "benchmark_boundary": "genuinely unresolved rows are frozen and excluded from the automated score",
    }
    (public_dir / "pilot_metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
