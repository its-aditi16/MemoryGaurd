"""Heal: quarantine the blast radius to a vault, replay affected questions, prove the fix.

Quarantine is automatic and reversible (Undo). Permanent purge of high-impact memories
needs a human Approve click.
"""
import json
import time

import db
from guard import fields
from guard.provenance import now_iso
from guard.score import score_memory
from lineage import graph
from store import get_store


def quarantine(memory_ids: list[str], reason: str = "heal") -> list[str]:
    """Move memories from the live store into the vault (content kept for forensics)."""
    store, done = get_store(), []
    for mid in memory_ids:
        m = store.get(mid)
        if not m:
            continue
        result = score_memory(m)
        meta = {**m.metadata, "status": "quarantined"}
        db.execute(
            "INSERT OR REPLACE INTO vault (memory_id, content, metadata, score, quarantined_at, state) "
            "VALUES (?, ?, ?, ?, ?, 'quarantined')",
            (mid, m.content, json.dumps(meta), json.dumps(result), now_iso()),
        )
        store.delete(mid)
        graph.set_status([mid], "quarantined")
        done.append(mid)
    if done:
        db.log_event("quarantined", f"Quarantined {', '.join(done)} to vault ({reason})", memory_ids=done)
    return done


def plan() -> dict:
    """What a heal would touch: every node downstream of the incident's poisoned sources."""
    incident = db.kv_get("incident") or {}
    out = {"active": bool(incident.get("active")), "memories": [], "answers": [], "actions": [], "sources": []}
    if not incident.get("roots"):
        return out
    seen = set()
    store = get_store()
    for root in incident["roots"]:
        for nid, depth in graph.blast_radius(root):
            if nid in seen:
                continue
            seen.add(nid)
            node = graph.get_node(nid)
            if node["status"] == "superseded":
                continue
            if node["type"] == "memory":
                m = store.get(nid)
                content = m.content if m else _vault_content(nid)
                out["memories"].append({
                    "id": nid, "status": node["status"], "source_class": node["data"].get("source_class"),
                    "trust": node["data"].get("trust"), "preview": content[:140],
                    "high_impact": bool(fields.high_impact_fields(content)), "depth": depth,
                })
            elif node["type"] == "answer":
                out["answers"].append({"id": nid, "question": node["data"].get("question"), "depth": depth})
            elif node["type"] == "action":
                out["actions"].append({"id": nid, "label": node["label"], "status": node["status"]})
            else:
                out["sources"].append({"id": nid, "label": node["label"], "status": node["status"]})
    return out


def _vault_content(memory_id: str) -> str:
    rows = db.query("SELECT content FROM vault WHERE memory_id = ?", (memory_id,))
    return rows[0]["content"] if rows else ""


def heal() -> dict:
    """Quarantine the blast radius, then replay every affected question against the healed store."""
    from agent import payments_agent as agent

    started = time.perf_counter()
    p = plan()
    if not p["memories"] and not p["answers"]:
        return {"quarantined": [], "replays": [], "time_to_heal": None, "message": "Nothing to heal"}

    quarantined = quarantine([m["id"] for m in p["memories"] if m["status"] != "quarantined"])
    graph.set_status([s["id"] for s in p["sources"]], "quarantined")
    bad_accounts = _poisoned_accounts()

    replays = []
    for a in p["answers"]:
        old = agent.get_answer(a["id"])
        new = agent.ask(old["question"], guard=True, replay_of=old["id"])
        fixed = _is_fixed(new, bad_accounts)
        db.execute(
            "INSERT INTO replays (question, old_answer_id, new_answer_id, old_answer, new_answer, fixed, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (old["question"], old["id"], new["id"], _summary(old), _summary(new), int(fixed), now_iso()),
        )
        graph.set_status([old["id"]] + ([old["action_id"]] if old["action_id"] else []), "superseded")
        replays.append({"question": old["question"], "old": _summary(old), "new": _summary(new), "fixed": fixed,
                        "old_answer_id": old["id"], "new_answer_id": new["id"]})

    elapsed = round(time.perf_counter() - started, 2)
    incident = db.kv_get("incident") or {}
    incident.update(active=False, healed_at=now_iso())
    if replays or "time_to_heal" not in incident:  # a re-heal after Undo keeps the real heal time
        incident["time_to_heal"] = elapsed
    db.kv_set("incident", incident)
    n_fixed = sum(r["fixed"] for r in replays)
    db.log_event("healed", f"Healed in {elapsed:.1f}s: {len(quarantined)} memories quarantined, "
                           f"{n_fixed}/{len(replays)} answers fixed on replay", time_to_heal=elapsed)
    return {"quarantined": quarantined, "replays": replays, "time_to_heal": elapsed}


def _poisoned_accounts() -> set[str]:
    """Account numbers in vaulted memories that are not verified accounts."""
    verified = {fields.normalize_account(fields.verified_account(v)) for v in fields.config.system_of_record()}
    accts = set()
    for row in db.query("SELECT content FROM vault WHERE state = 'quarantined'"):
        accts |= {fields.normalize_account(a) for a in fields.extract_accounts(row["content"])}
    return accts - verified


def _is_fixed(answer: dict, bad_accounts: set[str]) -> bool:
    used_bad_memory = any(m["status"] == "quarantined" for m in answer["memories"])
    text = answer["answer"] + json.dumps(answer["payment"] or {})
    mentions_bad = any(a in fields.normalize_account(text) for a in bad_accounts)
    gate_ok = not answer["gate"] or answer["gate"]["decision"] == "allow"
    return not used_bad_memory and not mentions_bad and gate_ok


def _summary(answer: dict) -> str:
    s = answer["answer"]
    if answer["payment"]:
        payees = "; ".join(f"{r.get('name')} -> {r['account']}" for r in answer["payment"]["recipients"])
        status = answer["action_status"] or "drafted"
        s += f" [payment {status}: {payees}]"
    return s


def replays() -> list[dict]:
    rows = db.query("SELECT * FROM replays ORDER BY seq")
    return [{**r, "fixed": bool(r["fixed"])} for r in rows]


def vault() -> list[dict]:
    rows = db.query("SELECT * FROM vault ORDER BY quarantined_at")
    return [{**r, "metadata": json.loads(r["metadata"]), "score": json.loads(r["score"] or "null")} for r in rows]


def approve() -> list[str]:
    """Human approval: permanently purge quarantined high-impact memories (keeps hash + metadata)."""
    purged = []
    for row in db.query("SELECT memory_id, content FROM vault WHERE state = 'quarantined'"):
        if fields.high_impact_fields(row["content"]):
            db.execute("UPDATE vault SET state = 'purged', content = '[purged after human approval]' "
                       "WHERE memory_id = ?", (row["memory_id"],))
            graph.update_data(row["memory_id"], purged=True)
            purged.append(row["memory_id"])
    if purged:
        db.log_event("approved", f"Human approved permanent deletion of {', '.join(purged)}", memory_ids=purged)
    return purged


def undo() -> list[str]:
    """Reverse quarantine: restore every non-purged vaulted memory to the store as 'flagged'."""
    store, restored = get_store(), []
    for row in db.query("SELECT * FROM vault WHERE state = 'quarantined'"):
        meta = {**json.loads(row["metadata"]), "status": "flagged"}
        store.retain(row["content"], meta)  # keeps the original memory_id
        db.execute("UPDATE vault SET state = 'restored' WHERE memory_id = ?", (row["memory_id"],))
        graph.set_status([row["memory_id"]], "tainted")
        restored.append(row["memory_id"])
    if restored:
        incident = db.kv_get("incident") or {}
        graph.set_status([r for r in incident.get("roots", []) if r.startswith("src:")], "tainted")
        incident["active"] = True
        db.kv_set("incident", incident)
        db.log_event("undone", f"Quarantine undone: {', '.join(restored)} restored as flagged", memory_ids=restored)
    return restored
