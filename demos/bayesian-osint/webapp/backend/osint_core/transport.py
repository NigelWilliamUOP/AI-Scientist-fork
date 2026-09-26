"""Bounded retrieval for an exact fixed-source registry, not a general web proxy.

Infrastructure must also deny private/link-local egress. DNS inspection here alone
is not a complete defence against DNS rebinding between resolution and connection.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import socket
from urllib.parse import urlparse
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

GOV_HOSTS = {"www.find-tender.service.gov.uk", "www.contractsfinder.service.gov.uk"}

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def validate_url(url: str, addresses: list[str]) -> None:
    p = urlparse(url)
    if p.scheme != "https" or p.hostname not in GOV_HOSTS or p.username or p.password or p.fragment:
        raise ValueError("only exact approved government HTTPS sources are supported")
    if p.port not in (None, 443):
        raise ValueError("nonstandard port blocked")
    if not p.path.startswith("/Notice/") or p.query:
        raise ValueError("only registered notice paths are supported")
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("non-public or unresolved destination blocked")

def capture(source: dict, destination: Path) -> dict:
    if source.get("capture_policy") != "government_full_content" or not source.get("enabled_for_live_fetch"):
        raise ValueError("source not approved for full live capture")
    url = source["url"]
    hostname = urlparse(url).hostname
    addresses = sorted({item[4][0] for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)})
    validate_url(url, addresses)
    # No proxy inherited from environment; no redirects; TLS uses the standard trust store.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    started = datetime.now(timezone.utc).isoformat()
    req = Request(url, headers={"User-Agent": "OSINT-Bayes-HEIF-Research-Demo/0.4",
                                "Accept": "text/html", "Accept-Encoding": "identity"})
    limit = min(int(source.get("max_bytes", 3000000)), 3000000)
    timeout = min(int(source.get("timeout_seconds", 20)), 30)
    with opener.open(req, timeout=timeout) as response:
        if response.status != 200:
            raise ValueError("source did not return HTTP 200")
        ctype = response.headers.get("Content-Type", "")
        if not ctype.lower().startswith("text/html"):
            raise ValueError("unexpected source content type")
        if response.headers.get("Content-Encoding", "identity").lower() not in ("", "identity"):
            raise ValueError("unexpected encoded response")
        content = response.read(limit + 1)
        if len(content) > limit:
            raise ValueError("source body exceeds limit")
        headers = {key: response.headers[key] for key in
                   ("Content-Type", "ETag", "Last-Modified") if key in response.headers}
    digest = hashlib.sha256(content).hexdigest()
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    name = f"{source['id']}-{stamp}-{digest}"
    raw = destination / (name + ".html")
    raw.write_bytes(content)
    metadata = {"source_id": source["id"], "url": url, "started_at": started,
                "acquired_at": datetime.now(timezone.utc).isoformat(),
                "representation": "original_http_capture", "http_status": 200,
                "upstream_body_sha256": digest, "size": len(content),
                "response_headers": headers, "raw_file": raw.name,
                "parser_status": "not_yet_parsed", "licence": source["licence"]}
    (destination / (name + ".json")).write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata
