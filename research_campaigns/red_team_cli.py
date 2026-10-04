"""CLI for the graded scientific red-team tournament."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import read_json, write_once
from .scientific_red_team import create_tournament, evaluation_sample, gold_view, score, worker_view


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    make = sub.add_parser("make")
    make.add_argument("--public", type=Path, required=True)
    make.add_argument("--gold", type=Path, required=True)
    make.add_argument("--sample", type=Path)

    evaluate = sub.add_parser("score")
    evaluate.add_argument("--gold", type=Path, required=True)
    evaluate.add_argument("--detections", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)

    args = p.parse_args()
    if args.command == "make":
        cases = create_tournament()
        write_once(args.public, worker_view(cases))
        write_once(args.gold, gold_view(cases))
        if args.sample:
            write_once(args.sample, worker_view(evaluation_sample(cases)))
        result = {"cases": len(cases), "mutations": len(cases)-12, "clean_controls": 12}
    else:
        gold = read_json(args.gold)
        detections = read_json(args.detections)
        lookup = {c["case_id"]: c for c in gold["cases"]}
        public_cases = [{"case_id": cid, "record": {}} for cid in lookup]
        cases = [{"case_id": cid, "record": {}, "gold": g} for cid, g in lookup.items()]
        result = score(cases, detections)
        write_once(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
