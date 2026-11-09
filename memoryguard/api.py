"""MemoryGuard JSON API.

Run from memoryguard/:  uvicorn api:app --reload --port 8000
"""
import hmac
import json
import threading
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

import config
import db
import ingest as ingest_mod
import llm
from agent import payments_agent as agent
from demo import attacks, benchmark, seed
from guard import detectors, gate
from guard.score import score_memory
from heal import heal
from lineage import graph
from store import Memory, get_store

_lock = threading.Lock()  # one mutating operation at a time keeps the demo state consistent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not get_store().list_all():
        seed.reset()
    heal.enforce_retention()  # policy: vault content older than vault_retention_days is purged
    detectors.attack_similarity("warm up the embedding model")
    yield


app = FastAPI(title="MemoryGuard", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
# Sample pages (fictional) so the Ingest feature can be demonstrated offline: /samples/<file>.html
app.mount("/samples", StaticFiles(directory=config.PKG_DIR / "demo" / "samples", html=True), name="samples")

PUBLIC_PATHS = ("/health", "/samples/")


@app.middleware("http")
async def access_control(request: Request, call_next):
    """Local API lockdown (no CORS at all - the dashboard reaches us through the Vite proxy):
    1. cross-site browser requests are refused (CSRF, including via the proxy);
    2. every other request must carry the per-run token that only the Vite proxy holds."""
    path = request.url.path
    if not path.startswith(PUBLIC_PATHS):
        origin = request.headers.get("origin")
        if request.headers.get("sec-fetch-site") == "cross-site" or (origin and origin not in config.ALLOWED_ORIGINS):
            return JSONResponse({"detail": "cross-site request refused"}, status_code=403)
        token = request.headers.get("x-memoryguard-token", "")
        if not hmac.compare_digest(token, config.API_TOKEN):
            return JSONResponse({"detail": "missing or invalid API token"}, status_code=401)
    return await call_next(request)


# Host header allowlist (defeats DNS rebinding). Added last so it runs first.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.ALLOWED_HOSTS)


class IngestIn(BaseModel):
    url: str | None = Field(None, max_length=2048)
    text: str | None = Field(None, max_length=config.MAX_INGEST_TEXT_CHARS)
    source_class: str = Field("web", max_length=20)
    scan: bool = True
    title: str = Field("", max_length=200)


@app.post("/ingest")
def ingest(body: IngestIn):
    if body.source_class not in ("web", "email", "user_chat", "tool"):
        raise HTTPException(400, "source_class must be web, email, user_chat or tool")
    try:
        with _lock:
            if body.url:
                return ingest_mod.ingest_url(body.url.strip(), body.source_class, body.scan)
            return ingest_mod.ingest_text(body.text or "", body.source_class, body.scan, body.title)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(400, f"Could not fetch that URL: {exc.__class__.__name__}") from exc


class ChatIn(BaseModel):
    question: str = Field(..., max_length=config.MAX_QUESTION_CHARS)


class GuardIn(BaseModel):
    enabled: bool


class EnforcementIn(BaseModel):
    mode: str = Field(..., pattern="^(monitor|enforce)$")


@app.post("/compare")
def compare(body: ChatIn):
    """Split screen: the same question to an unprotected agent (dry run) and the protected agent."""
    q = body.question.strip()
    with _lock:
        without = agent.ask(q, guard=False, dry_run=True)
        with_guard = agent.ask(q, guard=True)
    return {"question": q, "without": without, "with": with_guard}


@app.post("/benchmark/run")
def benchmark_run():
    return benchmark.run()


@app.get("/benchmark")
def benchmark_latest():
    return benchmark.latest() or {"summary": None, "rows": []}


@app.post("/enforcement")
def set_enforcement(body: EnforcementIn):
    db.kv_set("enforcement", body.mode)
    db.log_event("policy", f"Enforcement mode set to {body.mode.upper()}"
                           + (" (shadow mode: log only, nothing blocked)" if body.mode == "monitor" else ""))
    return {"enforcement": body.mode}


@app.get("/audit/verify")
def audit_verify():
    return db.verify_audit()


@app.get("/audit/export")
def audit_export():
    if not config.AUDIT_LOG.exists():
        raise HTTPException(404, "no audit log yet")
    return FileResponse(config.AUDIT_LOG, media_type="application/x-ndjson", filename="memoryguard-audit.jsonl")


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
    try:
        with _lock:
            return attacks.inject(attack_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class AgentIn(BaseModel):
    agent: str = Field(..., pattern="^(payments|helpdesk)$")


@app.post("/agent")
def switch_agent(body: AgentIn):
    """Switch the protected agent; loads that agent's clean memory bank. Same MemoryGuard engine."""
    with _lock:
        return {"agent": body.agent, "memories": len(seed.reset(body.agent))}


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
        return {"purged": heal.approve(), "retention_purged": heal.enforce_retention()}


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
        "enforcement": gate.enforcement(),
        "would_block": db.kv_get("would_block", 0),
        "audit": db.verify_audit(),
        "customer": config.POLICY.get("customer"),
        "backend": get_store().name,
        "llm": config.LLM_PROVIDER if llm.available() else "fallback",
        "attacks": {k: v["name"] for k, v in attacks.for_agent(agent.current_agent()).items()},
        "agent": agent.current_agent(),
        "agent_name": agent.AGENTS[agent.current_agent()]["name"],
    }
