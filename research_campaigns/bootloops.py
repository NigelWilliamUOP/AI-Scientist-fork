"""Opt-in BootLoops-inspired exact arithmetic checks; no upstream code execution."""
from fractions import Fraction
from math import isfinite
from .core import ContractError, Denied, digest, number, require

UPSTREAM = {"repository": "https://github.com/BootLoops-ai/bootloops",
            "commit": "66b680ce742e654cfe86da4f072a69061fe182b1"}

def exact_route(plan, source):
    """Independent rational route for the existing audited descriptive methods.
    Fractions represent the declared decimal values, not unknown measurement truth.
    """
    rows = source["payload"].get("rows")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100000:
        raise ContractError("Need 1-100,000 rows")
    method = plan.get("method")
    if method not in {"describe", "ols"}:
        raise Denied("No reviewed exact route for this method")
    columns = [plan["column"]] if method == "describe" else [plan["x"], plan["y"]]
    pairs = [[Fraction(str(number(row[c]))) for c in columns]
             for row in rows if all(c in row and row[c] is not None for c in columns)]
    n = len(pairs)
    if not n:
        raise ContractError("No complete observations")
    out = {"n": Fraction(n), "missing_rows": Fraction(len(rows)-n)}
    if method == "describe":
        ys = [r[0] for r in pairs]
        out.update(mean=sum(ys)/n, minimum=min(ys), maximum=max(ys))
    else:
        if n < 3:
            raise ContractError("OLS needs three rows")
        sx = sum(r[0] for r in pairs)
        sy = sum(r[1] for r in pairs)
        sxx = sum(r[0]**2 for r in pairs)
        sxy = sum(r[0]*r[1] for r in pairs)
        denominator = n*sxx-sx*sx
        if not denominator:
            raise ContractError("Constant exposure")
        slope = (n*sxy-sx*sy)/denominator
        intercept = (sy-slope*sx)/n
        rss = sum((y-intercept-slope*x)**2 for x,y in pairs)
        tss = sum(y*y for x,y in pairs)-sy*sy/n
        out.update(slope=slope, intercept=intercept, residual_sum_squares=rss,
                   r_squared=1-rss/tss if tss else None)
    return out

def seal(ledger, check_id, plan, source, candidate, *, role, cutoff,
         relative_tolerance=1e-10, absolute_tolerance=1e-12):
    """Freeze input bytes and tolerance before verification, using an immutable ledger."""
    from .core import instant, safe_id
    safe_id(check_id)
    if role not in {"study_producer", "programme_steward", "opportunity_scout"}:
        raise ContractError("Unknown lifecycle role")
    instant(cutoff)
    if instant(source["available_at"]) > instant(cutoff) or instant(source["captured_at"]) > instant(cutoff):
        raise Denied("Evidence postdates cutoff")
    if digest(source["payload"]) != source["sha256"]:
        raise Denied("Evidence checksum mismatch")
    for value in (relative_tolerance, absolute_tolerance):
        if isinstance(value, bool) or not isinstance(value, (int,float)) or not isfinite(value) or not 0 <= value <= 1e-6:
            raise ContractError("Tolerance must be finite and between zero and 1e-6")
    record = dict(plan=plan, source=source, candidate=candidate, role=role, cutoff=cutoff,
                  relative_tolerance=relative_tolerance, absolute_tolerance=absolute_tolerance,
                  upstream=UPSTREAM)
    ledger.put("bootloops_seals", check_id, record, role)
    return digest(record)

def verify(ledger, check_id):
    """Check sealed candidate; this does not promote a scientific claim."""
    record = ledger.get("bootloops_seals", check_id)
    if record is None:
        raise Denied("Seal inputs before checking")
    expected = exact_route(record["plan"], record["source"])
    candidate = record["candidate"]
    require(candidate, set(expected))
    differences = {}
    for key, value in expected.items():
        actual = candidate[key]
        if value is None:
            passed = actual is None
        else:
            actual = number(actual)
            error = abs(Fraction(str(actual))-value)
            tolerance = Fraction(str(record["absolute_tolerance"])) + Fraction(str(record["relative_tolerance"]))*abs(value)
            passed = error <= tolerance
        differences[key] = bool(passed)
    # Planted linear relation and deliberately corrupted output exercise both outcomes.
    control = exact_route({"method":"ols","x":"x","y":"y"},
                          {"payload":{"rows":[{"x":1,"y":3},{"x":2,"y":5},{"x":3,"y":7}]}})
    controls_passed = control["slope"] == 2 and control["intercept"] == 1 and control["slope"] != 3
    report = {"seal_sha256":digest(record), "status":"numerically_checked" if all(differences.values()) and controls_passed else "failed",
              "checks":differences, "controls_passed":controls_passed,
              "exact_values":{k:str(v) if v is not None else None for k,v in expected.items()},
              "unchecked_fields":sorted(set(candidate)-set(expected)),
              "scientific_validity":"unverified", "journal_readiness":"not_evaluated",
              "verification_class":"exact_decimal_arithmetic_comparator",
              "upstream_engine_executed":False}
    ledger.put("bootloops_checks",check_id,report,"exact_arithmetic_verifier")
    return report
