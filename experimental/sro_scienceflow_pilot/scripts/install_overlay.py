#!/usr/bin/env python3
"""Install the SRO task overlay and prepared public data into ScienceFlow."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def _copy_tree(source_root: Path, target_root: Path) -> int:
    copied = 0
    for source in sorted(source_root.rglob("*")):
        if not source.is_file():
            continue
        if any(part in {".private", "__pycache__", ".pytest_cache"} for part in source.parts):
            continue
        if source.suffix in {".pyc", ".pyo"}:
            continue
        relative = source.relative_to(source_root)
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1
        print(f"copied {relative}")
    return copied


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scienceflow-root", required=True, type=Path)
    parser.add_argument(
        "--pilot-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Pilot directory containing scienceflow_overlay (default: inferred).",
    )
    args = parser.parse_args()

    root = args.scienceflow_root.resolve()
    pilot_root = args.pilot_root.resolve()
    overlay = pilot_root / "scienceflow_overlay"
    prepared_data = pilot_root / "data" / "benchmark"
    if not (root / "scienceflow" / "cli.py").is_file():
        raise SystemExit(f"not a ScienceFlow checkout: {root}")
    if not overlay.is_dir():
        raise SystemExit(f"overlay not found: {overlay}")
    if not (prepared_data / "public" / "panel_baseline.csv").is_file():
        raise SystemExit("prepared benchmark not found; run scripts/prepare_pilot.py first")

    overlay_count = _copy_tree(overlay, root)
    data_target = root / "data" / "sro_reconstruction_pilot"
    if data_target.exists():
        shutil.rmtree(data_target)
    data_count = _copy_tree(prepared_data, data_target)

    labels_path = pilot_root / ".private" / "holdout_labels.csv"
    if not labels_path.is_file():
        raise SystemExit(f"external private labels not found: {labels_path}")

    print(f"installed {overlay_count} overlay files and {data_count} prepared data files")
    print("private labels were not copied into ScienceFlow")
    print(f"set SRO_PRIVATE_LABELS={labels_path} before running the manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
