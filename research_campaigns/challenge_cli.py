"""Command-line entry points for the challenge harness and mutation benchmark."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .challenge_demo import run_demo, synthetic_packet
from .challenge_harness import (
    DeterministicChallengeWorker, baseline_mutation_detector,
    evaluate_mutations, generate_mutation_suite, mutation_gold,
    mutation_worker_view, run_challenge,
)
from .core import Ledger, read_json, write_once


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo")
    demo.add_argument("--output", type=Path, default=Path("research_campaigns_runs/challenge-demo"))

    challenge = sub.add_parser("challenge-baseline")
    challenge.add_argument("packet", type=Path)
    challenge.add_argument("--ledger", type=Path, required=True)
    challenge.add_argument("--run-id", required=True)
    challenge.add_argument("--output", type=Path, required=True)

    make = sub.add_parser("make-mutations")
    make.add_argument("packet", type=Path)
    make.add_argument("--public-output", type=Path, required=True)
    make.add_argument("--gold-output", type=Path, required=True)

    score = sub.add_parser("score-mutations-baseline")
    score.add_argument("packet", type=Path)
    score.add_argument("--output", type=Path, required=True)

    sub.add_parser("synthetic-packet")
    args = parser.parse_args()

    if args.command == "demo":
        result = run_demo(args.output)
    elif args.command == "challenge-baseline":
        ledger = Ledger(args.ledger)
        try:
            result = run_challenge(read_json(args.packet), DeterministicChallengeWorker(), ledger, run_id=args.run_id)
        finally:
            ledger.close()
        write_once(args.output, result)
    elif args.command == "make-mutations":
        cases = generate_mutation_suite(read_json(args.packet))
        write_once(args.public_output, mutation_worker_view(cases))
        write_once(args.gold_output, mutation_gold(cases))
        result = {"public_cases": str(args.public_output), "gold": str(args.gold_output), "cases": len(cases)}
    elif args.command == "score-mutations-baseline":
        cases = generate_mutation_suite(read_json(args.packet))
        public = mutation_worker_view(cases)
        detections = {c["case_id"]: baseline_mutation_detector(c["packet"]) for c in public}
        result = evaluate_mutations(cases, detections)
        write_once(args.output, result)
    else:
        result = synthetic_packet()

    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
