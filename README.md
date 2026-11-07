# MemoryGuard

**Incident response for AI agent memory: detect, explain, trace, heal.**

MemoryGuard defends AI agents with long-term memory against **memory poisoning** (OWASP ASI06).
Write-time filters already exist; MemoryGuard handles what happens *after* a poisoned memory gets in:
it blocks the harmful action, explains why the memory is suspicious, traces everything the memory
touched (blast radius), and heals only the tainted parts, with a before/after replay as proof.

## Setup (once)

Requires Python 3.11+ and Node 20+.

```powershell
# from the project root
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python -m pip install -r requirements.txt
cd web; npm install; cd ..
copy .env.example .env     # then put your Groq key in .env
```

`.env` keys: `LLM_PROVIDER` (`groq` | `anthropic` | `openai` | `none`), `LLM_API_KEY`, optional `LLM_MODEL`,
`LLM_BASE_URL`, and `MEMORY_BACKEND=local`. With no key the agent falls back to a deterministic template,
so the demo still runs. The first start downloads the MiniLM embedding model (~90 MB); after that it works offline.

## Run

```powershell
npm run dev        # API on :8000 + dashboard on http://localhost:5173
npm run smoke      # (API must be running) full loop x3 + A2 over HTTP
```

## Demo click path (about 2 minutes)

1. **Reset**: clean memory bank (20 memories, 3 verified vendor accounts). Status pill: *All clear*.
2. *(optional: prove the threat)* Click **Protection on** to turn it off, **Inject A1**, ask
   *"Pay Acme's invoice"*: the unprotected agent drafts a payment to the attacker's account. Reset, turn protection back on.
3. **Inject A1**: a polite email saying Acme Supplies moved banks lands in memory. Nothing flags it at write time.
4. Click the suggestion *"Where do we pay Acme Supplies?"*: the agent repeats the attacker's account, and
   remembers its own answer, so the poison spreads.
5. Click *"Pay Acme's invoice"*: **the action gate blocks it**. The account isn't in the system of record and is backed
   only by low-trust memory. Toast + red *Action blocked* card; the pill turns *Incident active*.
6. **Blast radius**: taint spreads node by node, email → memory → answers → derived memory → drafted payment.
7. **Inspector** auto-opens the poisoned memory: suspicion score 0.70 with contribution bars
   (*contradicts verified record 50%, low-trust source 25%, high-impact field 14%, similar to known attack 11%*).
8. **Heal**: tainted memories move to the vault (only those two; the 20 clean memories stay). Every affected
   question is replayed. The before/after table shows both answers fixed. KPIs show **time to detect** and **time to heal**.
9. **Approve deletion** (human-in-the-loop permanent purge) or **Undo** (quarantine is reversible).
10. **Reset** for the next run. **Inject A2** + *"Pay the Bharat Logistics invoice"* shows the hidden-instruction
    attack (an extra recipient): blocked, scored 0.91, auto-quarantined.

## How it works

| Piece | Where | What it does |
|---|---|---|
| Provenance envelope | `memoryguard/guard/provenance.py` | Every memory gets source class, ids, SHA-256, claimed vs stored time, and **trust set by source class only** (system of record 1.0 … web 0.2). |
| Lineage | `memoryguard/lineage/graph.py` | SQLite nodes/edges: source → memory → answer → action (and answer → derived memory). BFS gives the blast radius. |
| Detectors | `memoryguard/guard/detectors.py` | Tier 0 regex injection markers · Tier 1 embedding similarity to known attack phrasings · contradiction with verified records (field extractor first, **LLM judge only when a high-impact field is present**). |
| Explainable score | `memoryguard/guard/score.py` | `Σ weight × signal`; each signal's share of the total *is* the explanation. ≥ 0.5 flag, ≥ 0.7 auto-quarantine. No training. |
| Action gate | `memoryguard/guard/gate.py` | Payment recipients are checked against `demo/system_of_record.json`. A mismatch backed only by memory with trust < 0.5 → **block**; better-backed → hold. Memory is never the authority for payment details. |
| Heal | `memoryguard/heal/heal.py` | Quarantine the blast radius to a vault (content kept for forensics), replay affected questions, diff before/after, Approve/Undo. |
| Victim agent | `memoryguard/agent/payments_agent.py` | Deliberately naive (newest memory wins, follows instructions in memory), because that's how real poisoning succeeds. |

Nothing is hardcoded to the attacks: blocks come from the gate's system-of-record check, and flags come from the signals.

## Layout

```
memoryguard/   FastAPI backend (api.py), store/, guard/, lineage/, heal/, agent/, demo/
web/           React + Vite + TypeScript + Tailwind dashboard (Cytoscape.js graph)
dev.mjs        starts both servers
```

All names, accounts and domains in the demo are fictional. Attack text exists only to test this system.
