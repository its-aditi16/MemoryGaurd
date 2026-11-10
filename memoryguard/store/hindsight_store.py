"""Hindsight memory backend.

Hindsight (https://github.com/vectorize-io/hindsight) owns the agent's long-term memory: every memory
is retained into a per-agent memory bank, and recall uses Hindsight's retrieval (semantic, keyword,
graph and temporal strategies, fused and reranked).

MemoryGuard adds what a security layer needs on top:
- each memory is retained with its provenance envelope as Hindsight metadata + tags, and its
  MemoryGuard id as the Hindsight document_id, so every recalled fact maps back to one memory;
- a small local mirror keeps MemoryGuard's own state (live / flagged) and the exact original text
  used by the detectors, gate and vault;
- quarantine deletes the document from Hindsight, so poisoned memories can never be recalled again.

Verified against hindsight-client 1.2.0 (method signatures inspected from the installed package).
"""
import json
import sqlite3
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import config
from store.base import Memory, MemoryStore

MIRROR_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, content TEXT NOT NULL, metadata TEXT NOT NULL
);
"""
# Provenance fields copied into Hindsight metadata (Hindsight metadata values are strings).
META_FIELDS = ("memory_id", "source_class", "source_id", "session_id", "trust", "sha256", "accepted_time")


class HindsightStore(MemoryStore):
    name = "hindsight"

    def __init__(self, base_url: str = config.HINDSIGHT_URL):
        from hindsight_client import Hindsight

        # The client runs async I/O on the calling thread's event loop, so every call goes through one
        # dedicated thread (one stable loop) no matter which API worker thread asks.
        self._hs = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hindsight")
        self.client = self._call(Hindsight, base_url=base_url, api_key=config.HINDSIGHT_API_KEY,
                                 timeout=120.0, user_agent="memoryguard/0.1")
        try:
            self._call(self.client.get_version)
        except Exception as exc:  # fail closed with a clear message instead of a stack trace later
            raise RuntimeError(
                f"Hindsight not reachable at {base_url}. For the local server run `npm run dev` with "
                f"MEMORY_BACKEND=hindsight; for Hindsight Cloud check HINDSIGHT_API_KEY "
                f"(or set MEMORY_BACKEND=local). Cause: {exc.__class__.__name__}") from exc
        self.namespace = "payments"
        self._lock = threading.Lock()
        self.db_path = str(config.DATA_DIR / "hindsight_mirror.db")
        with self._conn() as c:
            c.executescript(MIRROR_SCHEMA)

    # ---- helpers ----------------------------------------------------------
    def _call(self, fn, *args, **kwargs):
        return self._hs.submit(fn, *args, **kwargs).result()

    @property
    def bank_id(self) -> str:
        return f"{config.HINDSIGHT_BANK_PREFIX}-{self.namespace}"

    def set_namespace(self, name: str) -> None:
        """One Hindsight memory bank per protected agent."""
        self.namespace = name

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, check_same_thread=False, timeout=10)

    def _ensure_bank(self) -> None:
        self._call(
            self.client.create_bank, self.bank_id,
            name=f"MemoryGuard - {self.namespace} agent",
            mission="Long-term memory for an AI agent protected by MemoryGuard.",
            retain_extraction_mode=config.HINDSIGHT_EXTRACTION_MODE,  # keep exact wording for the gate
            enable_observations=False,  # no background LLM consolidation: deterministic, cheaper
        )

    # ---- MemoryStore interface --------------------------------------------
    def retain(self, content: str, metadata: dict) -> str:
        with self._lock, self._conn() as c:
            seq = c.execute("INSERT INTO memories (id, content, metadata) VALUES (?, ?, '{}')",
                            (f"pending-{uuid.uuid4().hex}", content)).lastrowid
            memory_id = metadata.get("memory_id") or f"mem-{seq:03d}"
            meta = {**metadata, "memory_id": memory_id}
            c.execute("UPDATE memories SET id = ?, metadata = ? WHERE seq = ?", (memory_id, json.dumps(meta), seq))
        try:
            item = self._item(memory_id, content, meta)
            self._call(self.client.retain, self.bank_id, item.pop("content"), **item)
        except Exception:
            with self._lock, self._conn() as c:  # keep mirror and Hindsight consistent
                c.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            raise
        return memory_id

    def retain_many(self, items: list[tuple[str, dict]]) -> list[str]:
        """One Hindsight retain_batch call for many memories (seeding, multi-chunk ingest)."""
        rows = []
        with self._lock, self._conn() as c:
            for content, metadata in items:
                seq = c.execute("INSERT INTO memories (id, content, metadata) VALUES (?, ?, '{}')",
                                (f"pending-{uuid.uuid4().hex}", content)).lastrowid
                memory_id = metadata.get("memory_id") or f"mem-{seq:03d}"
                meta = {**metadata, "memory_id": memory_id}
                c.execute("UPDATE memories SET id = ?, metadata = ? WHERE seq = ?",
                          (memory_id, json.dumps(meta), seq))
                rows.append((memory_id, content, meta))
        try:
            self._call(self.client.retain_batch, self.bank_id,
                       items=[self._item(mid, content, meta) for mid, content, meta in rows])
        except Exception:
            with self._lock, self._conn() as c:
                c.executemany("DELETE FROM memories WHERE id = ?", [(mid,) for mid, _, _ in rows])
            raise
        return [mid for mid, _, _ in rows]

    @staticmethod
    def _item(memory_id: str, content: str, meta: dict) -> dict:
        item = {
            "content": content,
            "context": f"{meta.get('source_class')} memory from {meta.get('source_id')}",
            "document_id": memory_id,
            "metadata": {k: str(meta[k]) for k in META_FIELDS if k in meta},
            "tags": [f"source:{meta.get('source_class')}", f"session:{meta.get('session_id')}"],
        }
        if meta.get("event_time"):
            item["timestamp"] = meta["event_time"]
        return item

    def recall(self, query: str, k: int = 5) -> list[Memory]:
        resp = self._call(self.client.recall, self.bank_id, query, max_tokens=4096, budget="mid")
        out, seen = [], set()
        results = resp.results or []
        for rank, r in enumerate(results):
            doc = r.document_id or (r.metadata or {}).get("memory_id")
            if not doc or doc in seen:
                continue
            m = self.get(doc)
            if m is None:  # deleted (quarantined) or unknown - never surface it
                continue
            seen.add(doc)
            m.score = round(1.0 - rank / max(len(results), 1), 4)  # Hindsight's fused, reranked order
            out.append(m)
            if len(out) >= k:
                break
        return out

    def get(self, memory_id: str) -> Memory | None:
        with self._conn() as c:
            row = c.execute("SELECT id, content, metadata FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return Memory(row[0], row[1], json.loads(row[2])) if row else None

    def update_metadata(self, memory_id: str, **fields) -> None:
        # MemoryGuard state (status, score) lives in the mirror; Hindsight keeps the original provenance.
        with self._lock, self._conn() as c:
            row = c.execute("SELECT metadata FROM memories WHERE id = ?", (memory_id,)).fetchone()
            if row:
                c.execute("UPDATE memories SET metadata = ? WHERE id = ?",
                          (json.dumps({**json.loads(row[0]), **fields}), memory_id))

    def delete(self, memory_id: str) -> None:
        from hindsight_client.hindsight_client import _run_async

        try:
            self._call(lambda: _run_async(self.client._documents_api.delete_document(
                self.bank_id, memory_id, _request_timeout=self.client._timeout)))
        finally:
            with self._lock, self._conn() as c:
                c.execute("DELETE FROM memories WHERE id = ?", (memory_id,))

    def list_all(self) -> list[Memory]:
        with self._conn() as c:
            rows = c.execute("SELECT id, content, metadata FROM memories ORDER BY seq").fetchall()
        return [Memory(r[0], r[1], json.loads(r[2])) for r in rows]

    def clear(self) -> None:
        """Delete and recreate this agent's Hindsight bank, and reset the mirror (ids restart)."""
        try:
            self._call(self.client.delete_bank, self.bank_id)
        except Exception:
            pass  # bank did not exist yet
        self._ensure_bank()
        with self._lock, self._conn() as c:
            c.execute("DROP TABLE IF EXISTS memories")
            c.executescript(MIRROR_SCHEMA)
