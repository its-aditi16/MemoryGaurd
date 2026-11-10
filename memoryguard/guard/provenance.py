"""Provenance envelope: who wrote a memory, when, and how much we trust that source."""
import hashlib
from datetime import datetime, timezone

import config


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def make_envelope(
    content: str,
    source_class: str,
    source_id: str,
    session_id: str = "seed",
    event_time: str | None = None,
) -> dict:
    """Build the metadata attached to every memory. Trust comes from source_class only."""
    if source_class not in config.TRUST_BY_SOURCE:
        raise ValueError(f"unknown source_class: {source_class}")
    accepted = now_iso()
    return {
        "source_class": source_class,
        "source_id": source_id,
        "session_id": session_id,
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "event_time": event_time or accepted,  # what the content claims
        "accepted_time": accepted,  # when we stored it
        "trust": config.TRUST_BY_SOURCE[source_class],
        "status": "live",
    }


def remember(
    content: str,
    source_class: str,
    source_id: str,
    session_id: str = "seed",
    event_time: str | None = None,
    writer_node: str | None = None,
) -> str:
    """Retain a memory with its envelope and record source -> memory in the lineage graph.

    writer_node: an existing lineage node that wrote this memory (e.g. an answer).
    When omitted, a source node 'src:<source_id>' is created.
    """
    from store import get_store

    meta = make_envelope(content, source_class, source_id, session_id, event_time)
    memory_id = get_store().retain(content, meta)
    _record_write(memory_id, content, meta, writer_node)
    return memory_id


def remember_many(rows: list[tuple[str, str, str, str, str | None]]) -> list[str]:
    """Batch version of remember(): rows of (content, source_class, source_id, session_id, event_time).

    One store call (Hindsight: one retain_batch), then the same lineage records as remember().
    """
    from store import get_store

    metas = [make_envelope(content, sc, sid, sess, et) for content, sc, sid, sess, et in rows]
    ids = get_store().retain_many([(row[0], meta) for row, meta in zip(rows, metas)])
    for memory_id, row, meta in zip(ids, rows, metas):
        _record_write(memory_id, row[0], meta, None)
    return ids


def _record_write(memory_id: str, content: str, meta: dict, writer_node: str | None) -> None:
    from lineage import graph

    session_id, source_id, source_class = meta["session_id"], meta["source_id"], meta["source_class"]
    if writer_node is None:
        writer_node = f"src:{source_id}"
        graph.add_node(writer_node, "source", source_id, source_class=source_class,
                       trust=meta["trust"], seed=session_id == "seed")
    graph.add_node(memory_id, "memory", memory_id, source_class=source_class, trust=meta["trust"],
                   preview=content[:120], seed=session_id == "seed")
    graph.add_edge(writer_node, memory_id, "wrote")
