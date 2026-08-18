from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

PILOT_ROOT = Path(__file__).resolve().parents[1]
EVALUATOR_PATH = (
    PILOT_ROOT
    / "scienceflow_overlay"
    / "tasks"
    / "opt_solver"
    / "sro-reconstruction-pilot"
    / "evaluator.py"
)
SPEC = importlib.util.spec_from_file_location("sro_evaluator", EVALUATOR_PATH)
assert SPEC and SPEC.loader
EVALUATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVALUATOR)

FIELDS = EVALUATOR.REQUIRED_COLUMNS


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def base_row(cell_id: str, state: str, status: str, *, source_url: str = "https://example.org/source") -> dict[str, str]:
    return {
        "cell_id": cell_id,
        "record_state": state,
        "person_name_raw": f"Person {cell_id}",
        "canonical_name": f"person {cell_id}",
        "status_at_date": status,
        "confidence": "high" if status != "unresolved" else "",
        "former_military": "",
        "evidence_basis": "Official material identifies a Major General." if cell_id == "h1" else "Evidence",
        "source_title": "Official source",
        "source_url": source_url,
        "source_tier": "official_direct",
        "coding_note": "",
        "interval_row": cell_id,
        "interval_id": f"interval-{cell_id}",
        "from_snapshot": "2024-03",
        "from_date": "2024-03-31",
    }


@pytest.fixture()
def prepared(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dataset = tmp_path / "dataset"
    task_dir = tmp_path / "task"
    workspace = tmp_path / "workspace"
    private_dir = tmp_path / "private"
    artifacts = workspace / "artifacts"
    artifacts.mkdir(parents=True)

    rows = [
        base_row("l1", "locked", "civilian"),
        base_row("h1", "holdout", "unresolved"),
        base_row("u1", "unresolved", "unresolved", source_url=""),
    ]
    write_csv(dataset / "public" / "panel_baseline.csv", rows)
    labels = private_dir / "holdout_labels.csv"
    labels.parent.mkdir(parents=True)
    with labels.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["cell_id", "expected_status_at_date"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerow({"cell_id": "h1", "expected_status_at_date": "military"})
    monkeypatch.setenv("SRO_PRIVATE_LABELS", str(labels))

    write_csv(artifacts / "reconstructed_panel.csv", rows)
    manifest = artifacts / "result_manifest.json"
    manifest.write_text(
        json.dumps({"schema_version": "1.0", "panel_path": "artifacts/reconstructed_panel.csv"}),
        encoding="utf-8",
    )
    return dataset, task_dir, workspace, manifest, rows


def evaluate(prepared):
    dataset, task_dir, workspace, manifest, _ = prepared
    return EVALUATOR.evaluate(
        artifact_path=manifest,
        workspace_dir=workspace,
        task_dir=task_dir,
        dataset_dir=dataset,
        config={},
    )


def rewrite_candidate(prepared, mutate):
    dataset, task_dir, workspace, manifest, rows = prepared
    candidate = [dict(row) for row in rows]
    mutate(candidate)
    write_csv(workspace / "artifacts" / "reconstructed_panel.csv", candidate)
    return dataset, task_dir, workspace, manifest, rows


def test_baseline_is_valid_with_zero_score(prepared):
    result = evaluate(prepared)
    assert result["valid"] is True
    assert result["metric"]["value"] == 0.0


def test_correct_holdout_scores(prepared):
    rewrite_candidate(
        prepared,
        lambda rows: rows[1].update(status_at_date="military", confidence="high"),
    )
    result = evaluate(prepared)
    assert result["metric"]["value"] == 1.0
    assert result["holdout_coverage"] == 1.0


def test_wrong_holdout_is_rejected(prepared):
    rewrite_candidate(
        prepared,
        lambda rows: rows[1].update(status_at_date="civilian", confidence="high"),
    )
    with pytest.raises(ValueError, match="incorrect holdout"):
        evaluate(prepared)


def test_locked_change_is_rejected(prepared):
    rewrite_candidate(prepared, lambda rows: rows[0].update(status_at_date="military"))
    with pytest.raises(ValueError, match="locked record changed"):
        evaluate(prepared)


def test_genuine_unresolved_change_is_rejected(prepared):
    rewrite_candidate(
        prepared,
        lambda rows: rows[2].update(status_at_date="civilian", confidence="high"),
    )
    with pytest.raises(ValueError, match="genuinely unresolved"):
        evaluate(prepared)


def test_wrong_confidence_is_rejected(prepared):
    rewrite_candidate(
        prepared,
        lambda rows: rows[1].update(status_at_date="military", confidence="medium"),
    )
    with pytest.raises(ValueError, match="confidence must be"):
        evaluate(prepared)


def test_duplicate_cell_is_rejected(prepared):
    def duplicate(rows):
        rows.append(dict(rows[1]))

    rewrite_candidate(prepared, duplicate)
    with pytest.raises(ValueError, match="duplicate cell_id"):
        evaluate(prepared)


def test_protected_evidence_change_is_rejected(prepared):
    rewrite_candidate(prepared, lambda rows: rows[1].update(source_url="https://example.org/other"))
    with pytest.raises(ValueError, match="protected column changed"):
        evaluate(prepared)


def test_manifest_path_traversal_is_rejected(prepared):
    _, _, _, manifest, _ = prepared
    manifest.write_text(
        json.dumps({"schema_version": "1.0", "panel_path": "../outside.csv"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="escapes the workspace"):
        evaluate(prepared)


def test_private_labels_environment_is_required(prepared, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SRO_PRIVATE_LABELS")
    with pytest.raises(ValueError, match="SRO_PRIVATE_LABELS"):
        evaluate(prepared)


def test_private_labels_cannot_be_inside_workspace(prepared, monkeypatch: pytest.MonkeyPatch):
    dataset, _, workspace, _, _ = prepared
    labels = workspace / "private_labels.csv"
    labels.write_text("cell_id,expected_status_at_date\nh1,military\n", encoding="utf-8")
    monkeypatch.setenv("SRO_PRIVATE_LABELS", str(labels))
    with pytest.raises(ValueError, match="inside the workspace"):
        evaluate(prepared)
