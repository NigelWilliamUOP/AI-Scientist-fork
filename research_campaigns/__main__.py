"""Command line entrypoint: python -m research_campaigns --help."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agents import OpportunityScout, ProgrammeSteward, StudyProducer
from .connectors import capture_watchlist
from .core import ContractError, Ledger, digest, number, read_json, safe_id, write_once
from .demo import run_demo
from .providers import BaselineProvider, Budget, ResponsesProvider, Session
from .replay import run_replay


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Three auditable research-lifecycle agents; no automatic publication or schedules.")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("study", "programme-init", "programme-update", "programme-amend", "scout", "replay", "audit", "human-time", "ingest"):
        sub = commands.add_parser(name)
        sub.add_argument("--workspace", type=Path, required=True)
        if name in {"study", "programme-update", "scout", "replay"}:
            sub.add_argument("--sources", type=Path, required=True)
            sub.add_argument("--synthetic", action="store_true", help="Explicitly permit labelled synthetic fixtures")
        if name in {"study", "scout", "replay", "programme-update"}:
            sub.add_argument("--provider", choices=["baseline", "responses"], default="baseline")
            sub.add_argument("--model")
            sub.add_argument("--max-calls", type=int, default=20)
            sub.add_argument("--max-usd", type=float, default=0)
            sub.add_argument("--input-rate", type=float, default=0, help="Current USD per million input tokens, operator supplied")
            sub.add_argument("--output-rate", type=float, default=0, help="Current USD per million output tokens, operator supplied")
            sub.add_argument("--max-output-tokens", type=int, default=4000)
            sub.add_argument("--max-input-bytes", type=int, default=100000)
            sub.add_argument("--allow-network", action="store_true")
            sub.add_argument("--allow-private-to-model", action="store_true")
        if name == "study":
            sub.add_argument("--brief", type=Path, required=True)
        if name == "programme-init":
            sub.add_argument("--baseline", type=Path, required=True)
        if name in {"programme-update", "programme-amend"}:
            sub.add_argument("--programme-id", required=True)
        if name in {"programme-update", "scout"}:
            sub.add_argument("--cutoff", required=True)
        if name == "programme-amend":
            sub.add_argument("--amendment", type=Path, required=True)
        if name in {"scout", "replay"}:
            sub.add_argument("--portfolio", type=Path, required=True)
            sub.add_argument("--queue-limit", type=int, default=5)
        if name == "replay":
            sub.add_argument("--cutoffs", type=Path, required=True, help="JSON array of increasing timezone-aware ISO cutoffs")
        if name == "human-time":
            sub.add_argument("--event-id", required=True)
            sub.add_argument("--category", choices=["production", "access_support", "verification", "evaluation", "rework"], required=True)
            sub.add_argument("--minutes", type=float, required=True)
            sub.add_argument("--note", default="")
        if name == "ingest":
            sub.add_argument("--watchlist", type=Path, required=True)
            sub.add_argument("--allow-network", action="store_true")
    demo = commands.add_parser("demo")
    demo.add_argument("--output", type=Path, required=True)
    return root


def execute(args: argparse.Namespace) -> dict:
    if args.command == "demo":
        return run_demo(args.output)
    if args.command == "ingest":
        return capture_watchlist(read_json(args.watchlist), args.workspace, allow_network=args.allow_network)
    sources, errors = [], []
    if hasattr(args, "sources"):
        supplied = read_json(args.sources)
        sources = supplied.get("snapshots", []) if isinstance(supplied, dict) else supplied
        errors = supplied.get("retrieval_errors", []) if isinstance(supplied, dict) else []
        if not isinstance(sources, list):
            raise ContractError("Sources must be a JSON array or a capture report")
    provider = budget = None
    if hasattr(args, "provider"):
        budget = Budget(max_calls=args.max_calls, max_usd=args.max_usd, max_input_bytes=args.max_input_bytes,
            max_output_tokens=args.max_output_tokens, input_usd_per_million=args.input_rate,
            output_usd_per_million=args.output_rate, allow_network=args.allow_network,
            allow_private_to_model=args.allow_private_to_model)
        provider = BaselineProvider() if args.provider == "baseline" else ResponsesProvider(args.model, args.max_output_tokens)
    if args.command == "replay":
        if errors:
            raise ContractError("Resolve source-capture errors before scoring a historical replay")
        return run_replay(read_json(args.portfolio), sources, read_json(args.cutoffs), args.workspace,
                          provider, budget, synthetic=args.synthetic, queue_limit=args.queue_limit)
    path = args.workspace / "state.sqlite"
    if args.command == "audit" and not path.exists():
        raise ContractError("No existing state.sqlite to audit")
    ledger = Ledger(path)
    try:
        if args.command == "audit":
            outcome = ledger.verify()
            write_once(args.workspace / "exports" / (outcome["head_hash"] + ".json"), ledger.export())
            return outcome
        if args.command == "human-time":
            if number(args.minutes) < 0:
                raise ContractError("Human minutes cannot be negative")
            value = {"category": args.category, "active_minutes": args.minutes, "note": args.note, "measurement": "operator_recorded"}
            ledger.put("human_time", safe_id(args.event_id), value, "operator")
            return {"status": "recorded", **value}
        if args.command.startswith("programme-"):
            programme_session = Session(ledger, provider, budget) if args.command == "programme-update" else None
            agent = ProgrammeSteward(ledger, programme_session)
            if args.command == "programme-init":
                outcome = agent.initialise(read_json(args.baseline))
            elif args.command == "programme-amend":
                outcome = agent.amend(args.programme_id, read_json(args.amendment))
            else:
                outcome = agent.update(args.programme_id, sources, args.cutoff, synthetic=args.synthetic)
                if errors:
                    outcome = {**outcome, "retrieval_errors": errors, "coverage_status": "incomplete"}
        else:
            session = Session(ledger, provider, budget)
            if args.command == "study":
                outcome = StudyProducer(ledger, session).run(read_json(args.brief), sources, synthetic=args.synthetic)
            else:
                outcome = OpportunityScout(ledger, session).run(read_json(args.portfolio), sources, args.cutoff,
                    synthetic=args.synthetic, queue_limit=args.queue_limit, retrieval_errors=errors)
        directory = args.workspace / "artifacts" / digest(outcome)[:24]
        write_once(directory / "result.json", outcome)
        if "manuscript_markdown" in outcome:
            write_once(directory / "manuscript.md", outcome["manuscript_markdown"], text=True)
        ledger.verify()
        return {**outcome, "artifact_directory": str(directory)}
    except Exception as exc:
        record = {"command": args.command, "error_type": type(exc).__name__, "reason": str(exc)[:500]}
        ledger.put("run_failures", digest(record), record)
        raise
    finally:
        ledger.close()


def main() -> int:
    try:
        outcome = execute(parser().parse_args())
        print(json.dumps(outcome, indent=2, ensure_ascii=False, allow_nan=False))
        return 3 if outcome.get("status") in {"stopped_budget", "blocked_data", "scan_incomplete"} else 0
    except (ContractError, KeyError, ValueError, TypeError, OSError) as exc:
        print(json.dumps({"status": "blocked", "error_type": type(exc).__name__, "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
