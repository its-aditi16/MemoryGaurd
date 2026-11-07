"""MemoryGuard JSON API.

Run from memoryguard/:  uvicorn api:app --reload --port 8000
"""
import json
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
import db
import llm
from agent import payments_agent as agent
from demo import attacks, seed
from guard import detectors
from guard.score import score_memory
from heal import heal
from lineage import graph
from store import Memory, get_store

_lock = threading.Lock()  # one mutating operation at a time keeps the demo state consistent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not get_store().list_all():
        seed.reset()
    detectors.attack_similarity("warm up the embedding model")
    yield


app = FastAPI(title="MemoryGuard", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ChatIn(BaseModel):
    question: str


class GuardIn(BaseModel):
    enabled: bool


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/chat")
def chat(body: ChatIn):
    q = body.question.strip()
    if not q:
        raise HTTPException(400, "question is empty")
    with _lock:
        return agent.ask(q)


@app.get("/answers")
def answers():
    return agent.list_answers()


@app.get("/memories")
def memories():
    scores = {r["memory_id"]: json.loads(r["result"])["score"] for r in db.query("SELECT * FROM scores")}
    live = [{**m.to_dict(), "suspicion": scores.get(m.id)} for m in get_store().list_all()]
    vaulted = [{"id": v["memory_id"], "content": v["content"], **v["metadata"], "status": "quarantined",
                "vault_state": v["state"], "suspicion": (v["score"] or {}).get("score")}
               for v in heal.vault() if v["state"] != "restored"]
    return live + vaulted


def _find_memory(memory_id: str) -> tuple[Memory | None, dict | None]:
    m = get_store().get(memory_id)
    if m:
        return m, None
    rows = [v for v in heal.vault() if v["memory_id"] == memory_id]
    if rows:
        v = rows[0]
        return Memory(memory_id, v["content"], v["metadata"]), v
    return None, None


@app.get("/score/{memory_id}")
def score(memory_id: str):
    m, vault_row = _find_memory(memory_id)
    if not m:
        raise HTTPException(404, f"unknown memory {memory_id}")
    result = vault_row["score"] if vault_row and vault_row["score"] else score_memory(m)
    node = graph.get_node(memory_id)
    return {
        "memory": {**m.to_dict(), "status": "quarantined" if vault_row else m.status,
                   "vault_state": vault_row["state"] if vault_row else None,
                   "graph_status": node["status"] if node else None},
        "score": result,
    }


@app.get("/node/{node_id}")
def node(node_id: str):
    n = graph.get_node(node_id)
    if not n:
        raise HTTPException(404, f"unknown node {node_id}")
    if n["type"] == "answer":
        n["answer"] = agent.get_answer(node_id)
    return n


@app.get("/graph")
def get_graph():
    return graph.get_graph()


@app.post("/inject/{attack_id}")
def inject(attack_id: str):
    if attack_id not in attacks.ATTACKS:
        raise HTTPException(404, f"unknown attack {attack_id}")
    with _lock:
        return attacks.inject(attack_id)


@app.get("/heal/plan")
def heal_plan():
    return heal.plan()


@app.post("/heal")
def do_heal():
    with _lock:
        return heal.heal()


@app.post("/approve")
def approve():
    with _lock:
        return {"purged": heal.approve()}


@app.post("/undo")
def undo():
    with _lock:
        return {"restored": heal.undo()}


@app.post("/reset")
def reset():
    with _lock:
        return {"memories": len(seed.reset())}


@app.post("/guard")
def set_guard(body: GuardIn):
    db.kv_set("guard_enabled", body.enabled)
    db.log_event("guard", f"Protection {'enabled' if body.enabled else 'DISABLED (unprotected agent)'}")
    return {"guard_enabled": body.enabled}


@app.get("/replays")
def replays():
    return heal.replays()


@app.get("/events")
def events():
    return db.events()


@app.get("/metrics")
def metrics():
    mems = get_store().list_all()
    incident = db.kv_get("incident") or {}
    vaulted = [v for v in heal.vault() if v["state"] in ("quarantined", "purged")]
    return {
        "live": sum(m.status == "live" for m in mems),
        "flagged": sum(m.status == "flagged" for m in mems),
        "quarantined": len(vaulted),
        "vault_pending": sum(v["state"] == "quarantined" for v in vaulted),
        "flagged_ids": incident.get("flagged", []),
        "time_to_detect": incident.get("time_to_detect"),
        "time_to_heal": incident.get("time_to_heal"),
        "incident_active": bool(incident.get("active")),
        "guard_enabled": db.kv_get("guard_enabled", True),
        "backend": get_store().name,
        "llm": config.LLM_PROVIDER if llm.available() else "fallback",
        "attacks": {k: v["name"] for k, v in attacks.ATTACKS.items()},
    }
