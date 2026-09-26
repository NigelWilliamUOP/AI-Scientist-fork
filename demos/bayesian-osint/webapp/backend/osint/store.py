from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import secrets
import sqlite3
from typing import Any, Iterator

SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS auth (id TEXT PRIMARY KEY, actor TEXT NOT NULL, role TEXT NOT NULL,
 csrf TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS attempts (peer TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, actor TEXT NOT NULL, mode TEXT NOT NULL,
 cutoff TEXT, scope_revision INTEGER NOT NULL DEFAULT 0, selection TEXT NOT NULL,
 exclusions TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS snapshots (session_id TEXT PRIMARY KEY, assessment TEXT NOT NULL, audit TEXT NOT NULL, context TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS versions (id TEXT PRIMARY KEY, source_id TEXT NOT NULL,
 content_hash TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS versions_source ON versions(source_id, created_at);
CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, actor TEXT NOT NULL, session_id TEXT NOT NULL,
 kind TEXT NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL, result TEXT,
 error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT,
 session_id TEXT, job_id TEXT, kind TEXT NOT NULL, detail TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS captures (id TEXT PRIMARY KEY, source_id TEXT NOT NULL,
 version_id TEXT, state TEXT NOT NULL, metadata TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assessments (case_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
 body TEXT NOT NULL, stale INTEGER NOT NULL DEFAULT 0, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS exports (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, actor TEXT NOT NULL,
 path TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL, state TEXT NOT NULL,
 remote_id TEXT, manifest_id TEXT, error TEXT, created_at TEXT NOT NULL, verified_at TEXT);
CREATE TABLE IF NOT EXISTS model_runs (id TEXT PRIMARY KEY, job_id TEXT NOT NULL,
 session_id TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS budget (id TEXT PRIMARY KEY, actor TEXT NOT NULL,
 session_id TEXT NOT NULL, job_id TEXT NOT NULL, day TEXT NOT NULL,
 reservation REAL NOT NULL, actual REAL, state TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS oauth_states (id TEXT PRIMARY KEY, actor TEXT NOT NULL,
 verifier TEXT NOT NULL, expires REAL NOT NULL);
'''

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')

def uid(prefix: str = '') -> str:
    return prefix + secrets.token_hex(12)

def sha(content: bytes | str) -> str:
    return hashlib.sha256(content.encode() if isinstance(content, str) else content).hexdigest()

def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'observatory.sqlite3'
        for name in ('captures', 'exports', 'secrets'):
            (self.root / name).mkdir(exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript(SCHEMA)
            db.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version','1')")

    @contextmanager
    def connect(self, write: bool = False) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=10000')
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def one(self, sql: str, args: tuple = ()) -> dict | None:
        with self.connect() as db:
            row = db.execute(sql, args).fetchone()
            return dict(row) if row else None

    def all(self, sql: str, args: tuple = ()) -> list[dict]:
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql, args).fetchall()]

    def execute(self, sql: str, args: tuple = ()) -> None:
        with self.connect(write=True) as db:
            db.execute(sql, args)

    def event(self, kind: str, detail: dict, session_id: str | None = None, job_id: str | None = None) -> None:
        self.execute('INSERT INTO events(session_id,job_id,kind,detail,at) VALUES (?,?,?,?,?)',
                     (session_id, job_id, kind, dump(detail), now()))

    def seed(self, seed_dir: Path) -> None:
        registry = json.loads((seed_dir / 'sources.json').read_text())['sources']
        for source in registry:
            record = json.loads((seed_dir / (source['id'] + '.json')).read_text())
            for seg in record['segments']:
                if sha(seg['text']) != seg['sha256']:
                    raise ValueError('Seed integrity failed: ' + record['id'])
            content_hash = sha(dump(record['segments']))
            self.execute('INSERT OR IGNORE INTO versions VALUES (?,?,?,?,?)',
                         (record['version_id'], record['id'], content_hash, dump(record), now()))
        self.execute('INSERT OR IGNORE INTO assessments VALUES (?,?,?,?,?)',
                     ('SEA-CHANGE', 0, dump({'status':'NO_ACCEPTED_ASSESSMENT','statements':[], 'source_versions':[]}), 0, now()))

    def version(self, version_id: str) -> dict:
        row = self.one('SELECT body FROM versions WHERE id=?', (version_id,))
        if not row:
            raise KeyError('Version not found')
        return json.loads(row['body'])

    def new_job(self, actor: str, session_id: str, kind: str, payload: dict) -> str:
        identity = uid('job-')
        stamp = now()
        with self.connect(write=True) as db:
            active = db.execute("SELECT COUNT(*) FROM jobs WHERE actor=? AND state IN ('queued','running')", (actor,)).fetchone()[0]
            if active:
                raise ValueError('JOB_ALREADY_ACTIVE')
            count = db.execute("SELECT COUNT(*) FROM jobs WHERE actor=? AND substr(created_at,1,13)=?", (actor,stamp[:13])).fetchone()[0]
            if count >= 40:
                raise ValueError('RATE_LIMITED')
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (identity, actor, session_id, kind, 'queued', dump(payload), None, None, stamp, stamp))
        self.event('queued', {'kind':kind}, session_id, identity)
        return identity

    def claim_job(self) -> dict | None:
        with self.connect(write=True) as db:
            row = db.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created_at LIMIT 1").fetchone()
            if not row:
                return None
            db.execute("UPDATE jobs SET state='running',updated_at=? WHERE id=?", (now(),row['id']))
            return dict(row)

    def finish_job(self, job: dict, result: dict | None = None, error: str | None = None) -> None:
        state = 'failed' if error else 'completed'
        self.execute('UPDATE jobs SET state=?,result=?,error=?,updated_at=? WHERE id=?',
                     (state, dump(result) if result is not None else None, error, now(),job['id']))
        self.event(state, {'error':error} if error else {'kind':job['kind']}, job['session_id'], job['id'])

    def recover(self) -> None:
        # Never repeat a possibly billed inference after a crash. Reservations remain.
        jobs = self.all("SELECT * FROM jobs WHERE state='running'")
        for job in jobs:
            self.finish_job(job, error='INTERRUPTED_RETRY_REQUIRED')
        self.execute("UPDATE exports SET state='pending',error='INTERRUPTED_RETRY_REQUIRED' WHERE state='uploading'")

    def reserve(self, run_id: str, actor: str, session_id: str, job_id: str, amount: float,
                session_limit: float, daily_limit: float) -> None:
        day = now()[:10]
        if not math.isfinite(amount) or amount < 0 or amount > 1000:
            raise ValueError('INVALID_RESERVATION')
        with self.connect(write=True) as db:
            session_total = db.execute('SELECT COALESCE(SUM(COALESCE(actual,reservation)),0) FROM budget WHERE session_id=?', (session_id,)).fetchone()[0]
            daily_total = db.execute('SELECT COALESCE(SUM(COALESCE(actual,reservation)),0) FROM budget WHERE day=?', (day,)).fetchone()[0]
            if session_total + amount > session_limit or daily_total + amount > daily_limit:
                raise ValueError('BUDGET_EXCEEDED')
            db.execute('INSERT INTO budget VALUES (?,?,?,?,?,?,?,?)',
                       (run_id, actor, session_id, job_id, day, amount, None, 'reserved'))
