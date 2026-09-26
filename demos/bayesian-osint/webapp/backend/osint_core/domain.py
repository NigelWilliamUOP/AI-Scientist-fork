"""Grouped, explicitly assumed Bayesian arithmetic. No learned probabilities."""
from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Iterable

@dataclass(frozen=True)
class Factor:
    key: str
    origin_group: str
    likelihood_ratio: float
    evidence_version: str
    approved: bool = True

def _positive_finite(value: float, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric, not boolean")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return number

def posterior(prior: float, factors: Iterable[Factor]) -> float:
    """Compute only approved factors from distinct declared independent origins.

    Reject duplicates instead of silently assuming independence or choosing a factor.
    The result is conditional on input assumptions, not a calibrated forecast.
    """
    p = _positive_finite(prior, "prior")
    if p >= 1:
        raise ValueError("prior must be strictly between zero and one")
    log_odds = math.log(p) - math.log1p(-p)
    origins: set[str] = set()
    keys: set[str] = set()
    for factor in factors:
        if not factor.approved:
            raise ValueError("unapproved factor cannot change accepted assessment")
        if not factor.key or not factor.origin_group or not factor.evidence_version:
            raise ValueError("factor needs key, origin and evidence version")
        if factor.key in keys or factor.origin_group in origins:
            raise ValueError("duplicate evidence key or dependent origin group")
        keys.add(factor.key)
        origins.add(factor.origin_group)
        log_odds += math.log(_positive_finite(factor.likelihood_ratio, "likelihood ratio"))
    if log_odds >= 0:
        return 1.0 / (1.0 + math.exp(-log_odds))
    odds = math.exp(log_odds)
    return odds / (1.0 + odds)

def replace_factor(factors: Iterable[Factor], key: str, replacement: Factor) -> list[Factor]:
    """Replace a reviewed version; never multiply both old and new versions."""
    result = list(factors)
    matches = [i for i, item in enumerate(result) if item.key == key]
    if len(matches) != 1:
        raise ValueError("replacement target must identify exactly one existing factor")
    original = result[matches[0]]
    if replacement.key != key or replacement.origin_group != original.origin_group:
        raise ValueError("replacement must preserve evidence identity and origin")
    if not replacement.approved:
        raise ValueError("replacement requires approval")
    _positive_finite(replacement.likelihood_ratio, "likelihood ratio")
    result[matches[0]] = replacement
    return result
