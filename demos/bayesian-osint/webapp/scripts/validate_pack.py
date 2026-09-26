#!/usr/bin/env python3
"""Verify retained source extracts and essential build-pack files; no network."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ["README.md", "AGENTS.md", "backend/osint/main.py", "seeds/answer.schema.json", "seeds/sources.json", "frontend/public/app.js"]

def validate(root: Path = ROOT) -> dict:
    errors = []
    for name in REQUIRED:
        if not (root / name).is_file():
            errors.append("missing: " + name)
    manifest = json.loads((root / "seeds/manifest.json").read_text(encoding="utf-8"))
    ids, versions = set(), set()
    for entry in manifest["records"]:
        path = (root / entry["path"]).resolve()
        if not path.is_relative_to(root.resolve()):
            errors.append("manifest path escapes pack")
            continue
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != entry["sha256"]:
            errors.append("extract file hash mismatch: " + entry["id"])
        record = json.loads(content)
        if record["id"] in ids or record["version_id"] in versions:
            errors.append("duplicate source/version identifier")
        ids.add(record["id"]); versions.add(record["version_id"])
        if record["representation"] != "curated_web_extract":
            errors.append("seed incorrectly labelled as original capture")
        if record["upstream_body_sha256"] is not None or record["upstream_http_status"] is not None:
            errors.append("seed claims unobserved upstream HTTP metadata")
        for segment in record["segments"]:
            if hashlib.sha256(segment["text"].encode()).hexdigest() != segment["sha256"]:
                errors.append("segment hash mismatch: " + record["id"])
        if sum(len(s["text"].split()) for s in record["segments"]) > 25:
            errors.append("seed source quote limit exceeded")
    if len(ids) != manifest["source_count"] or manifest["original_http_capture_count"] != 0:
        errors.append("source/capture count inconsistent")
    sources = json.loads((root / "seeds/sources.json").read_text())["sources"]
    if {s["id"] for s in sources} != ids:
        errors.append("registry and manifest do not match")
    enabled = [s for s in sources if s["enabled_for_live_fetch"]]
    if len(enabled) != 4:
        errors.append("expected exactly four approved government fetch sources")
    port = next(s for s in sources if s["id"] == "PORT-STATEMENT")
    if port["enabled_for_live_fetch"] or port["capture_policy"] != "curated_excerpt_only":
        errors.append("port statement full capture was not approved")
    return {"status": "passed" if not errors else "failed", "source_records": len(ids),
            "approved_government_fetch_sources": len(enabled), "errors": errors,
            "scope": "source bundle integrity only; not live provider or deployment validation"}

if __name__ == "__main__":
    try:
        result = validate()
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["status"] == "passed" else 1)
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        sys.exit(1)
