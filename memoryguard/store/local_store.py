"""SQLite + sentence-transformers memory store (cosine search over all rows)."""
import json
import sqlite3
import threading
import uuid

import numpy as np

import config
from embeddings import embed_one
from store.base import Memory, MemoryStore

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    seq       INTEGER PRIMARY KEY AUTOINCREMENT,
    id        TEXT UNIQUE NOT NULL,
    content   TEXT NOT NULL,
    metadata  TEXT NOT NULL,
    embedding BLOB NOT NULL
);
"""


class LocalStore(MemoryStore):
    name = "local"

    def __init__(self, db_path=config.LOCAL_STORE_DB):
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def retain(self, content: str, metadata: dict) -> str:
        vec = embed_one(content)
        with self._lock, self._conn() as c:
            # AUTOINCREMENT never reuses a seq, so ids of deleted (quarantined) memories stay unique.
            seq = c.execute(
                "INSERT INTO memories (id, content, metadata, embedding) VALUES (?, ?, '{}', ?)",
                (f"pending-{uuid.uuid4().hex}", content, vec.tobytes()),
            ).lastrowid
            memory_id = metadata.get("memory_id") or f"mem-{seq:03d}"
            meta = {**metadata, "memory_id": memory_id}
            c.execute("UPDATE memories SET id = ?, metadata = ? WHERE seq = ?", (memory_id, json.dumps(meta), seq))
        return memory_id

    def recall(self, query: str, k: int = 5) -> list[Memory]:
        with self._conn() as c:
            rows = c.execute("SELECT id, content, metadata, embedding FROM memories").fetchall()
        if not rows:
            return []
        q = embed_one(query)
        mat = np.stack([np.frombuffer(r[3], dtype=np.float32) for r in rows])
        sims = mat @ q  # vectors are normalised, so dot product == cosine
        top = np.argsort(-sims)[:k]
        return [Memory(rows[i][0], rows[i][1], json.loads(rows[i][2]), float(sims[i])) for i in top]

    def get(self, memory_id: str) -> Memory | None:
        with self._conn() as c:
            row = c.execute("SELECT id, content, metadata FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return Memory(row[0], row[1], json.loads(row[2])) if row else None

    def update_metadata(self, memory_id: str, **fields) -> None:
        with self._lock, self._conn() as c:
            row = c.execute("SELECT metadata FROM memories WHERE id = ?", (memory_id,)).fetchone()
            if row:
                meta = {**json.loads(row[0]), **fields}
                c.execute("UPDATE memories SET metadata = ? WHERE id = ?", (json.dumps(meta), memory_id))

    def delete(self, memory_id: str) -> None:
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM memories WHERE id = ?", (memory_id,))

    def list_all(self) -> list[Memory]:
        with self._conn() as c:
            rows = c.execute("SELECT id, content, metadata FROM memories ORDER BY seq").fetchall()
        return [Memory(r[0], r[1], json.loads(r[2])) for r in rows]

    def clear(self) -> None:
        # DROP (not DELETE) so AUTOINCREMENT restarts and ids are identical after every reset.
        with self._lock, self._conn() as c:
            c.execute("DROP TABLE IF EXISTS memories")
            c.executescript(SCHEMA)
