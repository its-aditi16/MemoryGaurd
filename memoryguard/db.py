"""SQLite helpers for MemoryGuard's own state: lineage, answers, vault, events, scores, kv."""
import json
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
    memory_ids TEXT, payment TEXT, gate TEXT, action_id TEXT, replay_of TEXT, engine TEXT, created_at TEXT
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
    execute(
        "INSERT INTO events (ts, kind, message, data) VALUES (?, ?, ?, ?)",
        (now_iso(), kind, message, json.dumps(data)),
    )


def events() -> list[dict]:
    rows = query("SELECT ts, kind, message, data FROM events ORDER BY seq")
    return [{**r, "data": json.loads(r["data"])} for r in rows]


init()
