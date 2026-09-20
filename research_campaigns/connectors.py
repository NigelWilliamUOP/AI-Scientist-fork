"""Explicit, bounded acquisition from an operator-approved HTTPS watchlist.

No agent-generated URL is fetched. Historical replay never invokes this module.
The initial live connector accepts normalised JSON datasets or text/RSS leads.
Leads without accessible data are correctly held at the scout's feasibility gate.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import urllib.parse
import urllib.request
from pathlib import Path

from .core import ContractError, Denied, digest, now, safe_id, write_once
from .providers import NoRedirect


def validate_url(url: str, allowed_hosts: list[str]) -> str:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.fragment or parts.port not in {None, 443}:
        raise Denied("Only ordinary HTTPS source URLs are permitted")
    host = parts.hostname.lower()
    if host not in {h.lower() for h in allowed_hosts}:
        raise Denied("Host is not on the operator-approved allowlist")
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise Denied("Private, loopback, link-local or reserved network destination")
    return url


def capture_watchlist(watchlist: dict, output: Path, *, allow_network: bool = False) -> dict:
    if not allow_network:
        raise Denied("Source acquisition requires --allow-network")
    specs = watchlist.get("sources", [])
    if not isinstance(specs, list) or not 1 <= len(specs) <= 20:
        raise ContractError("A capture is limited to 1-20 configured sources")
    max_bytes = watchlist.get("max_bytes_per_source", 2_000_000)
    if not isinstance(max_bytes, int) or not 1 <= max_bytes <= 10_000_000:
        raise ContractError("Source byte cap must be 1-10,000,000")
    captured, errors = [], []
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
    for spec in specs:
        ident = safe_id(spec["source_id"])
        try:
            url = validate_url(spec["url"], watchlist.get("allowed_hosts", []))
            if spec.get("storage_authorised") is not True:
                raise Denied("Source storage permission has not been recorded")
            request = urllib.request.Request(url, headers={"User-Agent": "ResearchCampaigns/0.2 (bounded academic evidence capture)"})
            with opener.open(request, timeout=30) as response:
                raw = response.read(max_bytes + 1)
                http_status = response.status
            if len(raw) > max_bytes:
                raise ContractError("Source exceeded byte cap")
            text = raw.decode("utf-8")
            at, raw_hash = now(), hashlib.sha256(raw).hexdigest()
            if spec.get("format") == "normalised_json":
                payload = json.loads(text)
                if not isinstance(payload, dict):
                    raise ContractError("Normalised JSON source must be an object")
                # Primary-source assertion and data dictionary come from the
                # approved watchlist when provided, never an LLM-generated URL.
                payload["primary_source"] = bool(spec.get("primary_source", False))
                if "schema" in spec:
                    payload["schema"] = spec["schema"]
            else:
                payload = {"title": spec.get("title", ident), "text": text,
                    "topics": spec.get("topics", []), "primary_source": bool(spec.get("primary_source", False))}
            payload["raw_sha256"] = raw_hash
            source = {"source_id": ident, "version": at, "available_at": at, "captured_at": at,
                "retrieved_at": at, "locator": url, "payload": payload, "sha256": digest(payload),
                "kind": "observed", "access": "public", "availability_basis": "first_observed_by_this_capture_not_first_publication",
                "rights_note": spec.get("rights_note", "Operator authorised storage"),
                "http_status": http_status,
                "archive_proof": {"locator": "raw/" + raw_hash + ".txt", "sha256": digest(payload), "raw_sha256": raw_hash}}
            write_once(output / "raw" / (raw_hash + ".txt"), text, text=True)
            captured.append(source)
        except Exception as exc:
            errors.append({"source_id": ident, "error_type": type(exc).__name__, "reason": str(exc)[:250]})
    report = {"snapshots": captured, "retrieval_errors": errors, "status": "scan_incomplete" if errors else "captured",
              "source_requests": len(specs), "external_billing": "not_measured", "schedule_activated": False}
    write_once(output / "capture.json", report)
    return report
