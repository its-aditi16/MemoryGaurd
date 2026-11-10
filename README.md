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

## Memory backend: Hindsight

MemoryGuard stores the agent's long-term memory in [Hindsight](https://github.com/vectorize-io/hindsight)
(`MEMORY_BACKEND=hindsight`), with a local SQLite store as a fallback (`MEMORY_BACKEND=local`).

- Each memory is retained with its provenance envelope as Hindsight **metadata + tags** and its MemoryGuard id as
  the Hindsight **`document_id`**; recall results map back to memories through `document_id`.
- **One Hindsight memory bank per agent** (`memoryguard-payments`, `memoryguard-helpdesk`).
- Banks use extraction mode **`chunks`**, so the exact original text is kept (the gate needs exact account numbers),
  and observations are off (no background LLM rewriting).
- Quarantine deletes the Hindsight document, so a poisoned memory can never be recalled again.
- Seeding and multi-chunk ingest use one `retain_batch` call.

**Option A: Hindsight Cloud** (what the demo uses). Add to `.env`:
```
MEMORY_BACKEND=hindsight
HINDSIGHT_URL=https://api.hindsight.vectorize.io
HINDSIGHT_API_KEY=hsk_...        # keep secret; .env is gitignored
```

**Option B: local Hindsight server** (offline, no Docker; embedded PostgreSQL + local embeddings):
```powershell
py -3.12 -m venv .venv-hindsight
.\.venv-hindsight\Scripts\python -m pip install hindsight-api
# .env: MEMORY_BACKEND=hindsight and HINDSIGHT_URL=http://127.0.0.1:8888 (or leave HINDSIGHT_URL unset)
```
`npm run dev` then starts the server on 127.0.0.1:8888 using your `LLM_PROVIDER` / `LLM_API_KEY`
(the first start downloads the local embedding and reranker models). Tip: keep `.venv-hindsight` outside a
OneDrive-synced folder; installing ~1.6 GB of small files into a synced folder is very slow.

## Run

```powershell
npm run dev         # API on :8000 + dashboard on http://localhost:5173
npm run smoke       # (API running) acceptance suite: 3 A1 rounds, A2, A3, split screen, monitor mode, 14 security tests
npm run preflight   # (API running) go-live readiness report (FDE practice)
npm run preflight -- --full   # same, plus the full acceptance suite as the hand-off gate (fails if any test fails)
cd memoryguard; ..\.venv\Scripts\python -m deploy.audit verify          # check the audit hash chain
cd memoryguard; ..\.venv\Scripts\python -m deploy.audit export out.jsonl  # export it for a security team
npm run benchmark   # 30 labelled samples -> detection rate, false-positive rate, latency
```

**One-click demo:** click **Autopilot** (or open `http://localhost:5173/?autopilot`) to play the whole story with
captions: attack → poisoned answer → *Without vs With* split screen → blast radius → explanation → heal →
a second, non-money attack (data leak) → heal.

## Two agents, one engine

The top bar switches the protected agent. Each agent has its own memory bank, source of truth and gated actions;
the MemoryGuard engine (provenance, detectors, score, lineage, heal, audit) is identical.

| | Payments agent | IT Helpdesk agent |
|---|---|---|
| Source of truth | Verified vendor bank accounts + company directory | Official admin list + registered employee contacts |
| Gated actions | `draft_payment`, `draft_email` | `grant_access`, `reset_password` |
| Attacks | A1 fake bank account, A2 hidden extra recipient, A3 data leak | A4 fake admin grant + reset link to an outside address (account takeover) |
| Demo questions | "Pay Acme's invoice", "Send the vendor payment summary to the audit team" | "John Mathew asked for a password reset on Meera Iyer's account - send the link where he asked", "Grant John Mathew admin access to the finance server" |

To protect a new kind of agent you plug in two things: its source of truth and the actions to check.

## What's in the dashboard

- **Without vs With**: the same question to an unprotected agent and the protected one, side by side.
- **Benchmark**: 32 samples (21 benign incl. hard negatives, 11 attacks across 8 types, including Microsoft's
  Feb 2026 "AI Recommendation Poisoning" pattern). Last run: 91% detection, 0% false positives, 100% precision,
  ~140 ms median scoring. The samples are hand-written and were also used while
  tuning, so it's a sanity check, not an independent benchmark. The one miss (a subtle fake fact with no account
  number) still faces the action gate, which blocks any payment to an unverified account; a lie that changes no
  gated field can get through, so the gate's coverage is the real security boundary.
- **A1 / A2 / A3**: fake bank account (email), hidden instruction (web page), data exfiltration (email to a look-alike domain).
- **Monitor / Enforce**: shadow mode logs "would have blocked" without blocking, which is how security tools are rolled out.
- **Audit chain**: every security event is appended to `memoryguard/data/audit.jsonl` with a SHA-256 hash chain;
  the badge turns red if history is edited. Export: `GET /audit/export` (through the dashboard proxy: `/api/audit/export`).

## Security model (MemoryGuard itself)

| Risk | Control |
|---|---|
| Other websites calling the local API | No CORS; per-run random token added only by the Vite proxy (never visible to browser JS); 401 without it |
| Cross-site request forgery (also via the proxy) | Requests with a foreign `Origin` or `Sec-Fetch-Site: cross-site` are refused (403) |
| DNS rebinding | Host header allowlist (`127.0.0.1`, `localhost`) |
| SSRF through Ingest | http/https on ports 80/443 only; every DNS answer and the actually-connected IP must be public; redirects followed manually (max 3) and re-checked; 3 MB streamed cap; optional domain allowlist in the policy |
| Prompt injection against MemoryGuard's own judge | Spotlighting / datamarking of untrusted text; deterministic checks run first and can't be overridden |
| Sensitive data sent to the LLM provider | Account numbers and email addresses are replaced by placeholders (`ACCT_1`, `EMAIL_2`) before any LLM call |
| Data leaving the company | Email gate: recipient must be in the company directory; DLP rule blocks verified bank details going outside the domain |
| Answers leaking data | Disclosure gate: if untrusted (email/web) memory shaped an answer, verified bank details of vendors the user didn't ask about are redacted |
| Untrusted senders | `ingest_sender_allowlist` in the policy (addresses or `@domains`); pasted emails from other senders are refused when the list is set |
| Keeping poisoned content forever | `vault_retention_days`: vault content older than this is purged at startup and on Approve (hash + metadata kept) |
| Audit integrity | Append-only JSONL, SHA-256 hash chain, cross-process file lock; every chat answer and security event is recorded |
| Oversized inputs | Request size limits (question 1,000 chars, pasted text 20,000) |
| Unreviewed deployments | `memoryguard/deploy/policy.json` (allowed actions, ingest allowlist, allowed LLM providers, retention); server refuses to start if invalid; `npm run preflight` |

Prompt injection is not solved by anyone. MemoryGuard's real safety net is the deterministic gate checked against a
system of record, not the model.

## Demo click path (about 2 minutes)

1. **Reset**: clean memory bank (21 memories: 3 verified vendor accounts + the company directory). Status pill: *All clear*.
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

## Real content: any web page or email (Ingest)

Click **Ingest** in the top bar.

- **Web page URL**: MemoryGuard fetches the page and writes it into the agent's memory in chunks (source `web`, trust 0.2).
  Like a real scraper it keeps text that humans can't see (HTML comments, `display:none` elements, CSS-class-hidden
  blocks, zero-width characters), because that's where prompt injections hide. Hidden chunks are labelled.
- **Paste email / text**: paste any email or message and choose how it arrived (email 0.3, user chat 0.6, tool 0.5).
- **Scan on write** (default on): suspicious chunks are flagged (≥ 0.5) or quarantined (≥ 0.7) immediately.
  Turn it off to simulate a pipeline with no write-time defense: the agent gets poisoned and the action gate has to catch it.

Quick picks include a **poisoned vendor page** served locally at
`http://127.0.0.1:8000/samples/acme-payment-update.html` (visible bank change + CSS-hidden instruction + HTML-comment
injection) and a **phishing email** about Bharat Logistics. Benign real pages (example.com, python.org) score
about 0.2–0.3 and stay live.

Limits: pages rendered by JavaScript may have little text, and some sites block bots. Wikipedia requires a
User-Agent with contact details (set `FETCH_USER_AGENT` in `.env`). Use paste mode for any page that won't fetch.

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
