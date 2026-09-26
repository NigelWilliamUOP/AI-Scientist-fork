"""Temporal admission for a selected corpus; authorisation belongs in the server."""
from __future__ import annotations
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

UTC = timezone.utc

def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return parsed.astimezone(UTC)

def publication_upper_bound(record: dict[str, Any]) -> datetime | None:
    """Conservative instant: end of the reported minute/day, not invented precision."""
    if record.get("publisher_timestamp"):
        instant = timestamp(record["publisher_timestamp"])
        precision = record.get("date_precision")
        if precision == "minute":
            return instant.replace(second=0, microsecond=0) + timedelta(minutes=1, microseconds=-1)
        if precision == "second":
            return instant.replace(microsecond=999999)
        raise ValueError("timestamp requires supported precision")
    if record.get("publisher_date"):
        if record.get("date_precision") != "day":
            raise ValueError("date requires day precision")
        day = date.fromisoformat(record["publisher_date"])
        zone = ZoneInfo(record.get("publication_timezone", "Europe/London"))
        return datetime.combine(day, time.max, zone).astimezone(UTC)
    return None

def admitted_at_cutoff(records: Iterable[dict[str, Any]], cutoff: str,
                       *, strict_as_observed: bool = False) -> list[dict[str, Any]]:
    """Filter already-authorised records. Reconstruction is NOT historical capture.

    The web app must additionally enforce case/session admission, version validity,
    field-level time scopes, graph filtering and cache keys. A record's whole current
    page must not be treated as historical merely because its notice is old.
    """
    limit = timestamp(cutoff)
    admitted = []
    for record in records:
        upper = publication_upper_bound(record)
        if upper is None or upper > limit:
            continue
        if strict_as_observed:
            acquired = record.get("acquired_at")
            if record.get("representation") != "original_http_capture" or not acquired:
                continue
            if timestamp(acquired) > limit:
                continue
        admitted.append(record)
    return admitted
