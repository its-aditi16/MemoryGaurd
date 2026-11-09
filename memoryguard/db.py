"""SQLite helpers for MemoryGuard's own state: lineage, answers, vault, events, scores, kv."""
import hashlib
import json
import os
import sqlite3
import threading

import config
from guard.provenance import now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY, type TEXT, label TEXT, status TEXT, created_at TEXT, data TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS edges (
    src TEXT, dst TEXT, kind TEXT, PRIMARY KEY (src, dst, kind)
);
CREATE TABLE IF NOT EXISTS answers (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE, question TEXT, answer TEXT,
    memory_ids TEXT, payment TEXT, gate TEXT, action_id TEXT, replay_of TEXT, engine TEXT, created_at TEXT,
    email TEXT
);
CREATE TABLE IF NOT EXISTS vault (
    memory_id TEXT PRIMARY KEY, content TEXT, metadata TEXT, score TEXT, quarantined_at TEXT,
    state TEXT  -- quarantined | purged | restored
);
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, message TEXT, data TEXT
);
CREATE TABLE IF NOT EXISTS scores (memory_id TEXT PRIMARY KEY, sha256 TEXT, result TEXT);
CREATE TABLE IF NOT EXISTS replays (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, old_answer_id TEXT, new_answer_id TEXT,
    old_answer TEXT, new_answer TEXT, fixed INTEGER, created_at TEXT
);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
"""
TABLES = ["nodes", "edges", "answers", "vault", "events", "scores", "replays", "kv"]

_lock = threading.RLock()


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(config.GUARD_DB), check_same_thread=False, timeout=10)
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    with _lock, _conn() as c:
        c.executescript(SCHEMA)
        try:  # migrate databases created before the email action existed
            c.execute("ALTER TABLE answers ADD COLUMN email TEXT")
        except sqlite3.OperationalError:
            pass


def reset() -> None:
    """Drop and recreate every table (AUTOINCREMENT counters restart)."""
    with _lock, _conn() as c:
        for t in TABLES:
            c.execute(f"DROP TABLE IF EXISTS {t}")
        c.executescript(SCHEMA)


def query(sql: str, args: tuple = ()) -> list[dict]:
    with _conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def execute(sql: str, args: tuple = ()) -> int:
    """Run a write; return lastrowid."""
    with _lock, _conn() as c:
        return c.execute(sql, args).lastrowid


def kv_get(key: str, default=None):
    rows = query("SELECT value FROM kv WHERE key = ?", (key,))
    return json.loads(rows[0]["value"]) if rows else default


def kv_set(key: str, value) -> None:
    execute("INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)", (key, json.dumps(value)))


def log_event(kind: str, message: str, **data) -> None:
    ts = now_iso()
    execute("INSERT INTO events (ts, kind, message, data) VALUES (?, ?, ?, ?)", (ts, kind, message, json.dumps(data)))
    _audit_append({"ts": ts, "kind": kind, "message": message, "data": data})


# ---- Tamper-evident audit log (append-only JSONL, SHA-256 hash chain) --------
# Survives Reset. Each line stores the previous line's hash, so editing or deleting
# history breaks the chain and verify_audit() reports where.
GENESIS = "0" * 64
_audit_lock = threading.Lock()


def _chain_hash(prev: str, entry: dict) -> str:
    return hashlib.sha256((prev + json.dumps(entry, sort_keys=True)).encode()).hexdigest()


def _lock_file(f, lock: bool) -> None:
    """Cross-process exclusive lock on the audit file (several processes may append)."""
    if os.name == "nt":
        import msvcrt

        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK if lock else msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(f.fileno(), fcntl.LOCK_EX if lock else fcntl.LOCK_UN)


def _last_hash_on_disk(f) -> str:
    """Hash of the last line actually in the file (never a cached value)."""
    f.seek(0, os.SEEK_END)
    size = f.tell()
    if size == 0:
        return GENESIS
    f.seek(max(0, size - 65536))
    tail = f.read().decode("utf-8").strip().splitlines()
    return json.loads(tail[-1])["hash"] if tail else GENESIS


def _audit_append(entry: dict) -> None:
    with _audit_lock, config.AUDIT_LOG.open("a+b") as f:
        _lock_file(f, True)
        try:
            prev = _last_hash_on_disk(f)
            line = json.dumps({**entry, "prev": prev, "hash": _chain_hash(prev, entry)}, sort_keys=True) + "\n"
            f.seek(0, os.SEEK_END)
            f.write(line.encode("utf-8"))
            f.flush()
        finally:
            _lock_file(f, False)


def verify_audit() -> dict:
    if not config.AUDIT_LOG.exists():
        return {"ok": True, "entries": 0, "broken_at": None, "head": GENESIS}
    prev, n = GENESIS, 0
    for n, line in enumerate(config.AUDIT_LOG.read_text(encoding="utf-8").splitlines(), start=1):
        rec = json.loads(line)
        entry = {k: v for k, v in rec.items() if k not in ("prev", "hash")}
        if rec.get("prev") != prev or rec.get("hash") != _chain_hash(prev, entry):
            return {"ok": False, "entries": n, "broken_at": n, "head": prev}
        prev = rec["hash"]
    return {"ok": True, "entries": n, "broken_at": None, "head": prev}


def events() -> list[dict]:
    rows = query("SELECT ts, kind, message, data FROM events ORDER BY seq")
    return [{**r, "data": json.loads(r["data"])} for r in rows]


init()
