"""Trusted admission, temporal filtering, scoped evidence and append-only state.

The model receives JSON, never this database connection or filesystem tools.
This protects against model-issued writes, not a malicious local administrator.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

VERSION = "0.2.0"
KINDS = {"observed", "derived", "assumed", "synthetic", "literature_inference", "unavailable"}


class ContractError(ValueError):
    pass


class Denied(ContractError):
    pass


class BudgetStopped(ContractError):
    pass


class ReconciliationRequired(ContractError):
    pass


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def code_fingerprint() -> str:
    """Freeze the actual runtime files, not just a manually supplied version."""
    root = Path(__file__).resolve().parent
    return digest({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob("*.py"))})


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def instant(value: str) -> datetime:
    if not isinstance(value, str):
        raise ContractError("An explicit ISO timestamp with timezone is required")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("Invalid ISO timestamp") from exc
    if dt.tzinfo is None:
        raise ContractError("Timezone-free dates are not accepted")
    return dt.astimezone(timezone.utc)


def number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ContractError("Expected a finite number")
    return float(value)


def require(obj: dict, keys: set[str]) -> None:
    if not isinstance(obj, dict) or not keys.issubset(obj):
        raise ContractError("Missing required fields: " + ", ".join(sorted(keys - set(obj or {}))))


def safe_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", value):
        raise ContractError("Identifier must be 1-120 safe filename characters")
    return value


def read_json(path: Path) -> Any:
    if path.stat().st_size > 20_000_000:
        raise ContractError("JSON input exceeds 20 MB")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda x: (_ for _ in ()).throw(ContractError(x)))


def write_once(path: Path, value: Any, *, text: bool = False) -> None:
    data = value if text else json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise Denied("Refusing symlink output")
    if path.exists():
        if path.read_text(encoding="utf-8") != data:
            raise Denied("Refusing to overwrite existing artifact: " + path.name)
        return
    # Exclusive create: a second worker cannot silently replace this output.
    with path.open("x", encoding="utf-8") as out:
        out.write(data)


class Ledger:
    """Transactional, immutable facts with an independently checkable hash chain."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise Denied("Refusing symlink ledger")
        self.db = sqlite3.connect(str(path), timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS facts (
            seq INTEGER PRIMARY KEY, namespace TEXT NOT NULL, key TEXT NOT NULL,
            payload TEXT NOT NULL, actor TEXT NOT NULL, recorded_at TEXT NOT NULL,
            previous_hash TEXT NOT NULL, hash TEXT NOT NULL,
            UNIQUE(namespace,key));
          CREATE TRIGGER IF NOT EXISTS immutable_update BEFORE UPDATE ON facts
            BEGIN SELECT RAISE(ABORT,'append-only facts'); END;
          CREATE TRIGGER IF NOT EXISTS immutable_delete BEFORE DELETE ON facts
            BEGIN SELECT RAISE(ABORT,'append-only facts'); END;
        """)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        else:
            self.db.execute("COMMIT")

    def get(self, namespace: str, key: str) -> Any:
        row = self.db.execute("SELECT payload FROM facts WHERE namespace=? AND key=?", (namespace, key)).fetchone()
        return json.loads(row[0]) if row else None

    def items(self, namespace: str) -> list[tuple[str, Any]]:
        return [(r[0], json.loads(r[1])) for r in self.db.execute(
            "SELECT key,payload FROM facts WHERE namespace=? ORDER BY seq", (namespace,))]

    def _put(self, namespace: str, key: str, value: Any, actor: str) -> bool:
        old = self.get(namespace, key)
        if old is not None:
            if canonical(old) != canonical(value):
                raise Denied("Immutable record conflict: " + namespace + "/" + key)
            return False
        if value is None:
            raise ContractError("Null facts are forbidden")
        previous = self.db.execute("SELECT hash FROM facts ORDER BY seq DESC LIMIT 1").fetchone()
        previous = previous[0] if previous else "0" * 64
        at = now()
        body = [namespace, key, value, actor, at, previous]
        self.db.execute("INSERT INTO facts(namespace,key,payload,actor,recorded_at,previous_hash,hash) VALUES(?,?,?,?,?,?,?)",
                        (namespace, key, canonical(value), actor, at, previous, digest(body)))
        return True

    def put(self, namespace: str, key: str, value: Any, actor: str = "runtime") -> bool:
        with self.transaction():
            return self._put(namespace, key, value, actor)

    def verify(self) -> dict:
        previous, count = "0" * 64, 0
        for row in self.db.execute("SELECT * FROM facts ORDER BY seq"):
            body = [row["namespace"], row["key"], json.loads(row["payload"]), row["actor"], row["recorded_at"], previous]
            if row["previous_hash"] != previous or row["hash"] != digest(body):
                raise Denied("Ledger integrity failure at event " + str(row["seq"]))
            previous, count = row["hash"], count + 1
        return {"events": count, "head_hash": previous, "integrity": "passed", "external_anchor": "not_supplied"}

    def export(self) -> list[dict]:
        return [dict(row) for row in self.db.execute("SELECT * FROM facts ORDER BY seq")]

    def close(self) -> None:
        self.db.close()


def validate_snapshot(source: dict) -> None:
    require(source, {"source_id", "version", "available_at", "captured_at", "retrieved_at", "payload", "sha256", "kind", "access", "locator"})
    safe_id(source["source_id"])
    for name in ("available_at", "captured_at", "retrieved_at"):
        instant(source[name])
    if instant(source["retrieved_at"]) < instant(source["captured_at"]):
        raise ContractError("Retrieval cannot precede the archived capture")
    if instant(source["captured_at"]) < instant(source["available_at"]):
        raise ContractError("Capture cannot precede this version's availability")
    if not isinstance(source["payload"], dict):
        raise ContractError("Snapshot payload must be a JSON object")
    if source["sha256"] != digest(source["payload"]):
        raise Denied("Snapshot checksum mismatch")
    if source["kind"] not in KINDS:
        raise ContractError("Unknown evidence kind")
    if source["access"] not in {"public", "authorised", "synthetic"}:
        raise Denied("Unapproved source access class")
    if (source["kind"] == "synthetic") != (source["access"] == "synthetic"):
        raise ContractError("Synthetic source must retain synthetic access label")


def source_key(source: dict) -> str:
    return source["source_id"] + "@" + digest({k: source[k] for k in (
        "version", "sha256", "available_at", "captured_at", "kind", "access", "locator")})[:20]


def source_view(source: dict) -> dict:
    """Only whitelisted evidence fields reach the worker. No paths or grading data."""
    return {k: source[k] for k in ("source_id", "version", "available_at", "captured_at", "kind", "access", "locator", "payload", "sha256")}


def select_sources(sources: list[dict], cutoff: str, *, replay: bool = False,
                   allow_synthetic: bool = False, latest: bool = True) -> tuple[list[dict], list[dict]]:
    end = instant(cutoff)
    eligible, excluded = {}, []
    versions, all_eligible, invalid_ids = {}, {}, set()
    for source in sources:
        label = source.get("source_id", "unknown")
        try:
            validate_snapshot(source)
            identity = (source["source_id"], str(source["version"]))
            # Retrieval time can differ; the version's content/schema cannot.
            fingerprint = digest(source_view(source))
            if identity in versions and versions[identity] != fingerprint:
                invalid_ids.add(source["source_id"])
                raise Denied("Conflicting content under one source version")
            versions[identity] = fingerprint
            if source["kind"] == "synthetic" and not allow_synthetic:
                raise Denied("synthetic_source_not_authorised")
            if instant(source["available_at"]) > end:
                raise Denied("published_after_cutoff")
            if instant(source["captured_at"]) > end:
                raise Denied("capture_after_cutoff")
            if replay and source["kind"] != "synthetic":
                proof = source.get("archive_proof", {})
                if not proof.get("locator") or proof.get("sha256") != source["sha256"]:
                    raise Denied("missing_archive_provenance")
            all_eligible[source_key(source)] = source
            old = eligible.get(source["source_id"])
            order = (instant(source["available_at"]), instant(source["captured_at"]))
            if old is None or order > (instant(old["available_at"]), instant(old["captured_at"])):
                eligible[source["source_id"]] = source
            elif old["sha256"] != source["sha256"] and order == (instant(old["available_at"]), instant(old["captured_at"])):
                invalid_ids.add(source["source_id"])
                raise ContractError("Ambiguous source vintages with identical timestamps")
        except (ContractError, KeyError, TypeError) as exc:
            excluded.append({"source_id": label, "reason": str(exc)})
    chosen = eligible if latest else all_eligible
    return [chosen[k] for k in sorted(chosen) if chosen[k]["source_id"] not in invalid_ids], excluded


def select_portfolio(cards: list[dict], cutoff: str, *, replay: bool = False) -> tuple[list[dict], list[dict]]:
    selected, excluded = {}, []
    end = instant(cutoff)
    for card in cards:
        try:
            require(card, {"work_id", "version", "known_at", "captured_at", "claims", "sha256"})
            content = {k: v for k, v in card.items() if k not in {"sha256", "archive_proof"}}
            if digest(content) != card["sha256"]:
                raise Denied("portfolio_checksum_mismatch")
            if max(instant(card["known_at"]), instant(card["captured_at"])) > end:
                raise Denied("portfolio_version_after_cutoff")
            if replay and not card.get("synthetic", False):
                proof = card.get("archive_proof", {})
                if not proof.get("locator") or proof.get("sha256") != card["sha256"]:
                    raise Denied("missing_portfolio_archive_provenance")
            claim_ids = [c["claim_id"] for c in card["claims"]]
            if len(set(claim_ids)) != len(claim_ids):
                raise ContractError("Duplicate claim IDs")
            prior = selected.get(card["work_id"])
            if prior and instant(prior["known_at"]) == instant(card["known_at"]) and prior["sha256"] != card["sha256"]:
                raise ContractError("Ambiguous portfolio versions")
            if not prior or instant(card["known_at"]) > instant(prior["known_at"]):
                selected[card["work_id"]] = card
        except (ContractError, KeyError, TypeError) as exc:
            excluded.append({"work_id": card.get("work_id", "unknown"), "reason": str(exc)})
    return [selected[k] for k in sorted(selected)], excluded


def portfolio_view(card: dict) -> dict:
    return {k: card[k] for k in ("work_id", "version", "known_at", "claims", "title") if k in card}


class EvidenceBroker:
    """An exact-ID read capability. It cannot read arbitrary filesystem paths."""

    def __init__(self, sources: list[dict], ledger: Ledger):
        self.sources = {source_key(s): s for s in sources}
        self.ledger = ledger

    def read(self, key: str) -> dict:
        if key not in self.sources:
            self.ledger.put("denied_reads", digest(key), {"requested_id": key, "reason": "not_in_evidence_capability"})
            raise Denied("Source is outside the authorised evidence capability")
        return source_view(self.sources[key])

    def context(self) -> dict:
        return {key: self.read(key) for key in self.sources}


def result(agent: str, status: str, **fields: Any) -> dict:
    return {"harness_version": VERSION, "agent": agent, "status": status,
            "scientific_status": "unverified", "journal_readiness": "not_evaluated",
            "public_release": "not_authorised", **fields}
