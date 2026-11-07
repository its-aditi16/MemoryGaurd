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
    from lineage import graph
    from store import get_store

    meta = make_envelope(content, source_class, source_id, session_id, event_time)
    memory_id = get_store().retain(content, meta)
    if writer_node is None:
        writer_node = f"src:{source_id}"
        graph.add_node(writer_node, "source", source_id, source_class=source_class,
                       trust=meta["trust"], seed=session_id == "seed")
    graph.add_node(memory_id, "memory", memory_id, source_class=source_class, trust=meta["trust"],
                   preview=content[:120], seed=session_id == "seed")
    graph.add_edge(writer_node, memory_id, "wrote")
    return memory_id
