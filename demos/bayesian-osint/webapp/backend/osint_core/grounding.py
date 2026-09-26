"""Mechanical citation validation. This intentionally does not prove entailment."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

ALLOWED_KINDS = {"plan", "reported_observation", "projection", "data_quality_issue", "not_established"}

@dataclass(frozen=True)
class LocatedCitation:
    statement_index: int
    source_version_id: str
    segment_id: str
    start_codepoint: int
    end_codepoint: int
    quote_located: bool = True
    semantic_support_reviewed: bool = False

def _exact_keys(value: Any, required: set[str], kind: str) -> None:
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError(f"{kind}: missing or unexpected fields")

def _strings(value: Any, name: str, limit: int = 12) -> None:
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError(f"{name} must be a bounded list")
    if any(not isinstance(item, str) or not item.strip() or len(item) > 4000 for item in value):
        raise ValueError(f"{name} contains an invalid string")

def validate_answer(answer: dict[str, Any], records: dict[str, dict[str, Any]],
                    allowed_versions: set[str]) -> list[LocatedCitation]:
    _exact_keys(answer, {"statements", "uncertainties", "next_evidence"}, "answer")
    _strings(answer["uncertainties"], "uncertainties")
    _strings(answer["next_evidence"], "next_evidence")
    statements = answer["statements"]
    if not isinstance(statements, list) or len(statements) > 12:
        raise ValueError("statements must be a bounded list")
    if not statements and not answer["uncertainties"]:
        raise ValueError("empty answer requires a stated uncertainty")
    locations = []
    for index, statement in enumerate(statements):
        _exact_keys(statement, {"text", "kind", "citations"}, "statement")
        if not isinstance(statement["text"], str) or not statement["text"].strip() or len(statement["text"]) > 4000:
            raise ValueError("invalid statement text")
        if not isinstance(statement["kind"], str) or statement["kind"] not in ALLOWED_KINDS:
            raise ValueError("unsupported statement kind")
        cites = statement["citations"]
        if not isinstance(cites, list) or not 1 <= len(cites) <= 8:
            raise ValueError("each statement requires bounded citations")
        for cite in cites:
            _exact_keys(cite, {"source_version_id", "segment_id", "quote"}, "citation")
            if any(not isinstance(cite[key], str) or not cite[key].strip() for key in cite):
                raise ValueError("invalid citation strings")
            version = cite["source_version_id"]
            if version not in allowed_versions or version not in records:
                raise ValueError("citation version not admitted")
            segments = records[version].get("segments", [])
            matches = [segment for segment in segments if segment["id"] == cite["segment_id"]]
            if len(matches) != 1:
                raise ValueError("citation segment missing or ambiguous")
            quote = cite["quote"]
            if len(quote) > 1500:
                raise ValueError("quote too long")
            start = matches[0]["text"].find(quote)
            if start < 0:
                raise ValueError("quote not found verbatim in retained segment")
            locations.append(LocatedCitation(index, version, cite["segment_id"], start, start + len(quote)))
    return locations
