"""Opt-in BootLoops-inspired exact arithmetic checks; no upstream code execution."""
from fractions import Fraction
from math import isfinite
from time import monotonic
from .core import ContractError, Denied, code_fingerprint, digest, number, require

VERSION = "rational-comparator-2"
DEFAULT_TIMEOUT_SECONDS = 10.0


def _deadline_check(deadline):
    if deadline is not None and monotonic() >= deadline:
        raise TimeoutError("Arithmetic verification deadline exceeded")

UPSTREAM = {"repository": "https://github.com/BootLoops-ai/bootloops",
            "commit": "66b680ce742e654cfe86da4f072a69061fe182b1"}

def declared_fraction(value):
    try:
        number(value)  # Validate without using the float conversion for arithmetic.
    except OverflowError as exc:
        raise ContractError("Numeric input exceeds the finite-float admission range") from exc
    return Fraction(str(value))

def exact_route(plan, source, *, deadline=None):
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
    # Validate finiteness/type without rounding declared integer values to float.
    pairs = []
    for row in rows:
        _deadline_check(deadline)
        if not isinstance(row, dict):
            raise ContractError("Each data row must be a JSON object")
        if all(c in row and row[c] is not None for c in columns):
            pairs.append([declared_fraction(row[c]) for c in columns])
    n = len(pairs)
    if not n:
        raise ContractError("No complete observations")
    out = {"n": Fraction(n), "missing_rows": Fraction(len(rows)-n)}
    if method == "describe":
        ys = [r[0] for r in pairs]
        total = sum_checked(ys, deadline)
        mean = total/n
        variance = sum_checked(((y-mean)**2 for y in ys), deadline)/(n-1) if n > 1 else None
        out.update(mean=mean, minimum=min(ys), maximum=max(ys), sample_sd_squared=variance)
    else:
        if n < 3:
            raise ContractError("OLS needs three rows")
        sx = sum_checked((r[0] for r in pairs), deadline)
        sy = sum_checked((r[1] for r in pairs), deadline)
        sxx = sum_checked((r[0]**2 for r in pairs), deadline)
        sxy = sum_checked((r[0]*r[1] for r in pairs), deadline)
        denominator = n*sxx-sx*sx
        if not denominator:
            raise ContractError("Constant exposure")
        slope = (n*sxy-sx*sy)/denominator
        intercept = (sy-slope*sx)/n
        rss = sum_checked(((y-intercept-slope*x)**2 for x,y in pairs), deadline)
        tss = sum_checked((y*y for x,y in pairs), deadline)-sy*sy/n
        out.update(slope=slope, intercept=intercept, residual_sum_squares=rss,
                   r_squared=1-rss/tss if tss else None)
    return out


def sum_checked(values, deadline):
    total = Fraction(0)
    for value in values:
        _deadline_check(deadline)
        total += value
    return total


def sd_agrees(actual, variance, relative, absolute):
    """Check |a-sqrt(v)| <= absolute + relative*sqrt(v) without rounding sqrt.

    With a >= 0 and relative < 1, rearrange to rational bounds on sqrt(v),
    then square the non-negative bounds. No floating-point square root is used.
    """
    if variance is None:
        return actual is None
    value = declared_fraction(actual)
    if value < 0:
        return False
    lower = max(Fraction(0), (value-absolute)/(1+relative))
    upper = (value+absolute)/(1-relative)
    return lower**2 <= variance <= upper**2

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
                  upstream=UPSTREAM, comparator_version=VERSION,
                  runtime_fingerprint=code_fingerprint())
    ledger.put("bootloops_seals", check_id, record, role)
    return digest(record)

def verify(ledger, check_id, *, timeout_seconds=DEFAULT_TIMEOUT_SECONDS):
    """Check sealed candidate; this does not promote a scientific claim."""
    if type(timeout_seconds) not in (int, float) or not isfinite(timeout_seconds) or not 0 < timeout_seconds <= 60:
        raise ContractError("Verification timeout must be finite, positive and at most 60 seconds")
    deadline = monotonic() + timeout_seconds
    ledger.verify()
    record = ledger.get("bootloops_seals", check_id)
    if record is None:
        raise Denied("Seal inputs before checking")
    if record.get("comparator_version") != VERSION or record.get("runtime_fingerprint") != code_fingerprint():
        raise Denied("Sealed comparator code changed; use a new workspace")
    cached = ledger.get("bootloops_checks", check_id)
    if cached is not None:
        return cached
    expected = exact_route(record["plan"], record["source"], deadline=deadline)
    candidate = record["candidate"]
    fields = set(expected) - {"sample_sd_squared"}
    if "sample_sd_squared" in expected:
        fields.add("sample_sd")
    require(candidate, fields)
    metadata_fields = {"identification"} if record["plan"]["method"] == "ols" else set()
    unsupported = sorted(set(candidate)-fields-metadata_fields)
    if "identification" in candidate and candidate["identification"] != "descriptive_association_only":
        unsupported.append("identification")
    relative = Fraction(str(record["relative_tolerance"]))
    absolute = Fraction(str(record["absolute_tolerance"]))
    differences = {}
    for key, value in expected.items():
        _deadline_check(deadline)
        if key == "sample_sd_squared":
            differences["sample_sd"] = sd_agrees(candidate["sample_sd"], value, relative, absolute)
            continue
        actual = candidate[key]
        if key in {"n", "missing_rows"}:
            passed = type(actual) is int and actual == value
        elif value is None:
            passed = actual is None
        else:
            error = abs(declared_fraction(actual)-value)
            tolerance = absolute + relative*abs(value)
            passed = error <= tolerance
        differences[key] = bool(passed)
    # Planted linear relation and deliberately corrupted output exercise both outcomes.
    control = exact_route({"method":"ols","x":"x","y":"y"},
                          {"payload":{"rows":[{"x":1,"y":3},{"x":2,"y":5},{"x":3,"y":7}]}})
    controls_passed = control["slope"] == 2 and control["intercept"] == 1 and control["slope"] != 3
    _deadline_check(deadline)
    report = {"seal_sha256":digest(record), "status":"numerically_checked" if all(differences.values()) and controls_passed and not unsupported else "failed",
              "checks":differences, "controls_passed":controls_passed,
              "exact_values":{k:str(v) if v is not None else None for k,v in expected.items()},
              "unchecked_fields":sorted(set(candidate)-fields),
              "unsupported_fields":unsupported,
              "checked_fields":sorted(differences),
              "sample_sd_basis":"rational_bounds_on_exact_sample_variance" if "sample_sd_squared" in expected else "not_applicable",
              "comparator_version":VERSION, "runtime_fingerprint":record["runtime_fingerprint"],
              "scientific_validity":"unverified", "journal_readiness":"not_evaluated",
              "verification_class":"exact_decimal_arithmetic_comparator",
              "upstream_engine_executed":False}
    ledger.put("bootloops_checks",check_id,report,"exact_arithmetic_verifier")
    return report
