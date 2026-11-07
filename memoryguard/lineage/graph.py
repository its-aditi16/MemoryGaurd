"""Lineage graph: source -> memory -> answer -> action, with BFS taint propagation.

Node types: source, memory, answer, action.
Edge kinds:  wrote (source/answer -> memory), used_in (memory -> answer), led_to (answer -> action).
Node status: clean | tainted | flagged | blocked | drafted | quarantined | superseded
"""
import json

import networkx as nx

import db
from guard.provenance import now_iso


def add_node(node_id: str, type_: str, label: str, status: str = "clean", **data) -> None:
    db.execute(
        "INSERT OR IGNORE INTO nodes (id, type, label, status, created_at, data) VALUES (?, ?, ?, ?, ?, ?)",
        (node_id, type_, label, status, now_iso(), json.dumps(data)),
    )


def add_edge(src: str, dst: str, kind: str) -> None:
    db.execute("INSERT OR IGNORE INTO edges (src, dst, kind) VALUES (?, ?, ?)", (src, dst, kind))


def set_status(node_ids: list[str], status: str) -> None:
    for nid in node_ids:
        db.execute("UPDATE nodes SET status = ? WHERE id = ?", (status, nid))


def update_data(node_id: str, **fields) -> None:
    rows = db.query("SELECT data FROM nodes WHERE id = ?", (node_id,))
    if rows:
        data = {**json.loads(rows[0]["data"]), **fields}
        db.execute("UPDATE nodes SET data = ? WHERE id = ?", (json.dumps(data), node_id))


def get_node(node_id: str) -> dict | None:
    rows = db.query("SELECT * FROM nodes WHERE id = ?", (node_id,))
    return {**rows[0], "data": json.loads(rows[0]["data"])} if rows else None


def get_graph() -> dict:
    nodes = [{**n, "data": json.loads(n["data"])} for n in db.query("SELECT * FROM nodes ORDER BY rowid")]
    edges = db.query("SELECT src, dst, kind FROM edges ORDER BY rowid")
    return {"nodes": nodes, "edges": edges}


def _digraph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_nodes_from(n["id"] for n in db.query("SELECT id FROM nodes"))
    g.add_edges_from((e["src"], e["dst"]) for e in db.query("SELECT src, dst FROM edges"))
    return g


def source_of(memory_id: str) -> str | None:
    """The node that wrote this memory (a source node, or an answer for agent-written memories)."""
    rows = db.query("SELECT src FROM edges WHERE dst = ? AND kind = 'wrote'", (memory_id,))
    return rows[0]["src"] if rows else None


def blast_radius(node_id: str) -> list[tuple[str, int]]:
    """All descendants of node_id (including itself) in BFS order, with hop depth."""
    g = _digraph()
    if node_id not in g:
        return []
    depths = nx.single_source_shortest_path_length(g, node_id)
    return sorted(depths.items(), key=lambda kv: (kv[1], kv[0]))


def taint(root_id: str) -> list[str]:
    """Mark the root and every descendant as tainted (blocked actions keep 'blocked').

    Each node records taint_seq = its BFS order so the UI can animate the spread.
    """
    radius = blast_radius(root_id)
    seq_start = len(db.query("SELECT id FROM nodes WHERE status IN ('tainted', 'blocked')"))
    for i, (nid, depth) in enumerate(radius):
        node = get_node(nid)
        if node["status"] in ("quarantined", "superseded"):
            continue
        if node["status"] != "blocked":
            set_status([nid], "tainted")
        if "taint_seq" not in node["data"]:
            update_data(nid, taint_seq=seq_start + i, taint_depth=depth)
    return [nid for nid, _ in radius]
