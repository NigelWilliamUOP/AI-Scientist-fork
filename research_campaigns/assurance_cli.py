"""Offline entry point: python -m research_campaigns.assurance_cli --help."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .assurance import assess_repair, freeze_packet, from_agent_record, review
from .assurance_demo import demo
from .core import ContractError, Denied, Ledger, read_json, write_once


def safe_path(path: Path, *, exists: bool = True) -> Path:
    # Reject symlink components before input reads or any output directory writes.
    path = path.absolute()
    for item in (path, *path.parents):
        if item.is_symlink():
            raise Denied("Symlink paths are not accepted")
    if exists and not path.exists():
        raise ContractError("Input path does not exist")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    d = commands.add_parser("demo"); d.add_argument("--output", type=Path, required=True)
    p = commands.add_parser("prepare"); p.add_argument("--input", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    r = commands.add_parser("review"); r.add_argument("--packet", type=Path, required=True); r.add_argument("--output", type=Path, required=True)
    r.add_argument("--run-id", required=True); r.add_argument("--max-checks", type=int, default=100)
    r.add_argument("--criticisms", type=Path); r.add_argument("--rebuttals", type=Path)
    a = commands.add_parser("repair"); a.add_argument("--original", type=Path, required=True); a.add_argument("--revised", type=Path, required=True)
    a.add_argument("--output", type=Path, required=True)
    l = commands.add_parser("from-agent"); l.add_argument("--ledger", type=Path, required=True)
    l.add_argument("--spec", type=Path, required=True); l.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        output = safe_path(args.output, exists=False)
        if args.command == "demo":
            result = demo(output)
        elif args.command == "prepare":
            result, excluded = freeze_packet(**read_json(safe_path(args.input)))
            write_once(output / "packet.json", result)
            write_once(output / "operator_only_exclusions.json", excluded)
        elif args.command == "review":
            packet = read_json(safe_path(args.packet))
            allegations = read_json(safe_path(args.criticisms)) if args.criticisms else None
            rebuttals = read_json(safe_path(args.rebuttals)) if args.rebuttals else None
            ledger = Ledger(output / "assurance.sqlite")
            try:
                result = review(packet, ledger, args.run_id, max_checks=args.max_checks,
                                allegations=allegations, rebuttals=rebuttals)
                write_once(output / (args.run_id + ".json"), result)
                # The audit is live; do not overwrite an earlier immutable receipt.
                write_once(output / (args.run_id + ".audit.json"), ledger.verify())
            finally:
                ledger.close()
        elif args.command == "repair":
            result = assess_repair(read_json(safe_path(args.original)), read_json(safe_path(args.revised)))
            write_once(output, result)
        else:
            # Immutable SQLite URI reader: no migrations, triggers or WAL changes.
            import sqlite3
            path = safe_path(args.ledger)
            class Reader:
                def __init__(self) -> None:
                    self.db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
                def get(self, namespace: str, key: str):
                    row = self.db.execute("SELECT payload FROM facts WHERE namespace=? AND key=?", (namespace, key)).fetchone()
                    return json.loads(row[0]) if row else None
            reader = Reader()
            try:
                result, excluded = from_agent_record(reader, **read_json(safe_path(args.spec)))
            finally:
                reader.db.close()
            write_once(output / "packet.json", result)
            write_once(output / "operator_only_exclusions.json", excluded)
        print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
        return 0
    except (ContractError, OSError, KeyError, TypeError, ValueError) as exc:
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
