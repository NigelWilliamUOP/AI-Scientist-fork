#!/usr/bin/env python3
"""Evaluate the unchanged baseline and the conservative reference candidate."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType
from typing import Any


def _load_evaluator(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("sro_reconstruction_evaluator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load evaluator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _evaluate(module: ModuleType, *, workspace: Path, task_dir: Path, dataset: Path) -> dict[str, Any]:
    return module.evaluate(
        artifact_path=workspace / "artifacts" / "result_manifest.json",
        workspace_dir=workspace,
        task_dir=task_dir,
        dataset_dir=dataset,
        config={},
    )


def main() -> int:
    pilot_root = Path(__file__).resolve().parents[1]
    task_dir = pilot_root / "scienceflow_overlay" / "tasks" / "opt_solver" / "sro-reconstruction-pilot"
    evaluator_path = task_dir / "evaluator.py"
    dataset = pilot_root / "data" / "benchmark"
    labels = pilot_root / ".private" / "holdout_labels.csv"
    baseline_workspace = dataset / "starter"
    reference_workspace = pilot_root / "reference_workspace"

    required = [
        evaluator_path,
        dataset / "public" / "panel_baseline.csv",
        labels,
        baseline_workspace / "artifacts" / "result_manifest.json",
        reference_workspace / "artifacts" / "result_manifest.json",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("pilot is not prepared; missing:\n" + "\n".join(missing))

    os.environ["SRO_PRIVATE_LABELS"] = str(labels)
    evaluator = _load_evaluator(evaluator_path)
    baseline = _evaluate(
        evaluator,
        workspace=baseline_workspace,
        task_dir=task_dir,
        dataset=dataset,
    )
    reference = _evaluate(
        evaluator,
        workspace=reference_workspace,
        task_dir=task_dir,
        dataset=dataset,
    )
    if baseline["metric"]["value"] != 0.0:
        raise RuntimeError("unchanged baseline should score zero")

    results_dir = pilot_root / "pilot_results"
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "baseline_evaluation.json").write_text(
        json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (results_dir / "reference_evaluation.json").write_text(
        json.dumps(reference, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"baseline": baseline, "reference": reference}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
