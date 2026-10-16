"""Bounded research-team planning and objection-preserving handoffs.

Original Teamwork-inspired control prototype, not Google's implementation.
No model execution, evidence authentication or manuscript-release authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


def fingerprint(value: Any) -> str:
    """Hash a JSON-compatible snapshot; reject NaN and Infinity."""
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")


def _positive(value: int, name: str) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class ClaimContract:
    question: str
    population: str
    unit: str
    intervention: str
    comparator: str
    outcome: str
    time_horizon: str
    inference_target: str
    constraints_id: str
    evidence_cutoff: str

    def __post_init__(self) -> None:
        for field in fields(self):
            _text(getattr(self, field.name), field.name)
        if self.inference_target not in {"causal", "descriptive", "conceptual", "mechanism"}:
            raise ValueError("Unknown inference target")


def contract_changes(original: ClaimContract, revised: ClaimContract) -> tuple[str, ...]:
    """Exact field comparison only. An empty result is NOT semantic equivalence."""
    return tuple(f.name for f in fields(original)
                 if getattr(original, f.name) != getattr(revised, f.name))


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    author: str
    contract: ClaimContract
    strategy: str
    parents: tuple[str, ...]
    depth: int


@dataclass(frozen=True)
class Objection:
    objection_id: str
    target: str
    reason: str
    required_check: str
    reporter: str


class Campaign:
    """In-memory control experiment, not a persistent or authenticated service.

    Objections cannot be cleared by this prototype. Reviews are recorded as
    assertions, never promoted into empirical validation. A fresh run cannot
    establish a retrospective blind baseline or reset a real provider budget.
    """
    def __init__(self, contract: ClaimContract, *, max_roots: int = 3,
                 max_rounds: int = 3, max_records: int = 12) -> None:
        for name, value in (("max_roots", max_roots), ("max_rounds", max_rounds),
                            ("max_records", max_records)):
            _positive(value, name)
        self._contract = contract
        self._limits = (max_roots, max_rounds, max_records)
        self._candidates: dict[str, Candidate] = {}
        self._objections: dict[str, Objection] = {}
        self._reviews: list[dict[str, Any]] = []

    @property
    def contract(self) -> ClaimContract:
        return self._contract

    @property
    def max_roots(self) -> int:
        return self._limits[0]

    @property
    def max_rounds(self) -> int:
        return self._limits[1]

    @property
    def max_records(self) -> int:
        return self._limits[2]

    def candidate(self, candidate_id: str) -> Candidate:
        try:
            return self._candidates[candidate_id]
        except KeyError as exc:
            raise ValueError(f"Unknown candidate: {candidate_id}") from exc

    def add_candidate(self, candidate_id: str, author: str, strategy: str, *,
                      contract: ClaimContract | None = None,
                      parents: Sequence[str] = ()) -> Candidate:
        for name, value in (("candidate_id", candidate_id), ("author", author),
                            ("strategy", strategy)):
            _text(value, name)
        if candidate_id in self._candidates:
            raise ValueError("Candidate IDs are immutable; use a new ID")
        revised = self.contract if contract is None else contract
        changed = contract_changes(self.contract, revised)
        if changed:
            raise ValueError("Reframing requires a separately frozen campaign: " + ", ".join(changed))
        if isinstance(parents, (str, bytes)):
            raise ValueError("parents must be a sequence of candidate IDs")
        parent_ids = tuple(parents)
        if len(parent_ids) != len(set(parent_ids)):
            raise ValueError("Duplicate parent")
        predecessors = [self.candidate(p) for p in parent_ids]
        depth = 1 + max((p.depth for p in predecessors), default=0)
        if len(self._candidates) >= self.max_records or depth > self.max_rounds:
            raise ValueError("Campaign record/round budget exhausted")
        if not parent_ids and sum(not c.parents for c in self._candidates.values()) >= self.max_roots:
            raise ValueError("Independent candidate budget exhausted")
        result = Candidate(candidate_id, author, revised, strategy, parent_ids, depth)
        self._candidates[candidate_id] = result
        return result

    def _lineage(self, candidate_id: str) -> tuple[str, ...]:
        pending, seen = [candidate_id], set()
        while pending:
            current = pending.pop()
            if current not in seen:
                seen.add(current)
                pending.extend(self.candidate(current).parents)
        return tuple(sorted(seen))

    def object(self, objection_id: str, target: str, reason: str,
               required_check: str, reporter: str) -> None:
        self.candidate(target)
        for name, value in (("objection_id", objection_id), ("reason", reason),
                            ("required_check", required_check), ("reporter", reporter)):
            _text(value, name)
        if objection_id in self._objections:
            raise ValueError("Objection IDs are immutable")
        self._objections[objection_id] = Objection(objection_id, target, reason, required_check, reporter)

    def handoff(self, candidate_id: str) -> dict[str, Any]:
        """Return a fresh snapshot. Late objections propagate to existing descendants."""
        lineage = self._lineage(candidate_id)
        payload = {
            "candidate_id": candidate_id,
            "contract": asdict(self.contract),
            "lineage": [asdict(self.candidate(cid)) for cid in lineage],
            "unresolved_objections": [asdict(obj) for oid, obj in sorted(self._objections.items())
                                      if obj.target in lineage],
            "semantic_equivalence": "unverified",
            "empirical_validation": "unverified",
            "paper_release_authorised": False,
        }
        return {**payload, "snapshot_hash": fingerprint(payload)}

    def record_review(self, candidate_id: str, snapshot_hash: str, reviewer: str,
                      verdict: str, basis: str, *, reason: str = "",
                      required_check: str = "") -> None:
        _text(reviewer, "reviewer")
        if verdict not in {"pass", "fail", "unknown"}:
            raise ValueError("Unknown review verdict")
        if basis not in {"arithmetic", "synthetic", "empirical", "conceptual"}:
            raise ValueError("Unknown review basis")
        if verdict != "pass":
            _text(reason, "reason for fail/unknown review")
            _text(required_check, "required_check for fail/unknown review")
        packet = self.handoff(candidate_id)
        if packet["snapshot_hash"] != snapshot_hash:
            raise ValueError("Stale review: candidate or inherited objections changed")
        if reviewer in {self.candidate(cid).author for cid in self._lineage(candidate_id)}:
            raise ValueError("A declared author cannot review their own lineage")
        # Negative and incomplete reviews become durable objections, so a later
        # synthesis cannot drop them simply by giving the candidate a new ID.
        if verdict != "pass":
            objection_id = "review:" + fingerprint({"candidate": candidate_id,
                "snapshot": snapshot_hash, "reviewer": reviewer, "verdict": verdict,
                "basis": basis, "reason": reason, "check": required_check})
            self.object(objection_id, candidate_id, reason, required_check, reviewer)
        self._reviews.append({"candidate_id": candidate_id, "snapshot_hash": snapshot_hash,
                              "reviewer": reviewer, "verdict": verdict, "basis": basis,
                              "authenticity": "not_verified", "independence": "not_verified"})

    def diagnostic(self, candidate_id: str) -> dict[str, Any]:
        packet = self.handoff(candidate_id)
        relevant = [r for r in self._reviews if r["candidate_id"] == candidate_id]
        current = [dict(r) for r in relevant if r["snapshot_hash"] == packet["snapshot_hash"]]
        blocked = bool(packet["unresolved_objections"]) or any(r["verdict"] == "fail" for r in current)
        return {**packet,
                "next_step": "resolve_objections_or_stop" if blocked else "external_review_required",
                "current_asserted_reviews": current,
                "stale_review_count": len(relevant) - len(current)}


def dependency_order(dependencies: Mapping[str, Sequence[str]]) -> tuple[str, ...]:
    """Validate a dependency graph and return a deterministic topological order."""
    graph: dict[str, set[str]] = {}
    for node, parents in dependencies.items():
        _text(node, "node")
        if isinstance(parents, (str, bytes)):
            raise ValueError("Dependencies must be sequences, not text")
        raw = tuple(parents)
        for parent in raw:
            _text(parent, "dependency")
        if len(raw) != len(set(raw)):
            raise ValueError("Duplicate dependency")
        graph[node] = set(raw)
    if any(parent not in graph for parents in graph.values() for parent in parents):
        raise ValueError("Unknown dependency")
    result: list[str] = []
    while graph:
        ready = sorted(node for node, parents in graph.items() if not parents)
        if not ready:
            raise ValueError("Cyclic dependency graph")
        result.extend(ready)
        graph = {node: parents - set(ready) for node, parents in graph.items() if node not in ready}
    return tuple(result)


def invalidate_dependants(dependencies: Mapping[str, Sequence[str]],
                          withdrawn: Sequence[str]) -> tuple[str, ...]:
    """Return affected nodes only; does not inspect files or certify unaffected claims."""
    order = dependency_order(dependencies)
    if isinstance(withdrawn, (str, bytes)):
        raise ValueError("withdrawn must be a sequence of node IDs")
    affected = set(withdrawn)
    if not affected.issubset(dependencies):
        raise ValueError("Unknown withdrawn node")
    for node in order:
        if affected.intersection(dependencies[node]):
            affected.add(node)
    return tuple(node for node in order if node in affected)


def plan_campaign(pattern: str, *, phase: str, candidates: int = 3,
                  rounds: int = 2) -> dict[str, Any]:
    """Load our declarative blueprint. This is NOT a native Antigravity pattern."""
    _positive(candidates, "candidates")
    _positive(rounds, "rounds")
    if phase not in {"review", "design", "simulation", "tracking"}:
        raise ValueError("Unknown project phase")
    if candidates > 3 or rounds > 3:
        raise ValueError("Prototype plan exceeds its three-candidate/three-round bound")
    definitions = json.loads(Path(__file__).with_name("teamwork_patterns.json").read_text())
    if pattern not in definitions["patterns"]:
        raise ValueError("Unknown research pattern")
    selected = definitions["patterns"][pattern]
    if phase not in selected["allowed_phases"]:
        raise ValueError("Pattern forbidden in the current project phase")
    return {"pattern": pattern, "phase": phase, "candidates": candidates, "rounds": rounds,
            "roles": selected["roles"], "required_checks": selected["required_checks"],
            "model_calls_executed": 0, "runtime_dispatch": "not_implemented",
            "provider_budget_enforcement": "requires_existing_session_adapter",
            "human_acceptance_required": True, "paper_release_authorised": False,
            "pattern_hash": fingerprint(definitions)}
