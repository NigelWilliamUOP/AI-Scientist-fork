"""Local archival outbox reference. No Google credentials or network operations."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from datetime import datetime, timezone

class IntegrityError(ValueError):
    pass

class Outbox:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.objects = self.root / "objects"
        self.objects.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / "outbox.sqlite3", timeout=15)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS objects (
          id TEXT PRIMARY KEY, case_id TEXT NOT NULL, kind TEXT NOT NULL,
          sha256 TEXT NOT NULL, size INTEGER NOT NULL, path TEXT NOT NULL,
          status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
          drive_file_id TEXT, verified_at TEXT, last_error TEXT)""")
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def enqueue(self, case_id: str, kind: str, content: bytes) -> str:
        for identifier in (case_id, kind):
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identifier):
                raise ValueError("invalid case or kind")
        if not isinstance(content, bytes):
            raise TypeError("archive content must be bytes")
        digest = hashlib.sha256(content).hexdigest()
        identity = hashlib.sha256(f"{case_id}:{kind}:{digest}".encode()).hexdigest()
        path = self.objects / identity
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise IntegrityError("local immutable object changed")
        else:
            with tempfile.NamedTemporaryFile(dir=self.objects, delete=False) as handle:
                temp = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        with self.db:
            self.db.execute("""INSERT OR IGNORE INTO objects
                (id, case_id, kind, sha256, size, path, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
                (identity, case_id, kind, digest, len(content), str(path)))
        return identity

    def get(self, identity: str) -> dict:
        row = self.db.execute("SELECT * FROM objects WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise KeyError("unknown archive object")
        return dict(row)

    def begin_attempt(self, identity: str) -> None:
        with self.db:
            cur = self.db.execute("""UPDATE objects SET status='uploading', attempts=attempts+1,
                last_error=NULL WHERE id=? AND status='pending'""", (identity,))
            if cur.rowcount != 1:
                raise ValueError("object must be pending before an upload attempt")

    def mark_failure(self, identity: str, code: str) -> None:
        if not re.fullmatch(r"[A-Z0-9_]{1,80}", code):
            raise ValueError("use a non-sensitive error code")
        with self.db:
            cur = self.db.execute("""UPDATE objects SET status='failed', last_error=?
                WHERE id=? AND status='uploading'""", (code, identity))
            if cur.rowcount != 1:
                raise ValueError("only an active attempt may fail")

    def retry(self, identity: str) -> None:
        if self.get(identity)["status"] == "pending":
            return
        with self.db:
            cur = self.db.execute("""UPDATE objects SET status='pending'
                WHERE id=? AND status='failed'""", (identity,))
            if cur.rowcount != 1:
                raise ValueError("only failed objects may be requeued")

    def mark_verified(self, identity: str, drive_file_id: str, downloaded: bytes) -> None:
        row = self.get(identity)
        if row["status"] != "uploading":
            raise ValueError("readback belongs to an active upload")
        if not drive_file_id or not isinstance(downloaded, bytes):
            raise ValueError("remote identity and readback bytes are required")
        if len(downloaded) != row["size"] or hashlib.sha256(downloaded).hexdigest() != row["sha256"]:
            self.mark_failure(identity, "ARCHIVE_HASH_MISMATCH")
            raise IntegrityError("remote readback differs from archived object")
        now = datetime.now(timezone.utc).isoformat()
        with self.db:
            self.db.execute("""UPDATE objects SET status='verified', drive_file_id=?,
              verified_at=?, last_error=NULL WHERE id=? AND status='uploading'""",
              (drive_file_id, now, identity))
