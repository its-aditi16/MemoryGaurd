# One polite email taught my Hindsight agent to pay scammers

The email that broke my agent had no "ignore previous instructions" in it. It was polite, it was signed by the vendor's accounts team, and it said Acme Supplies had moved banks. The next time someone asked it to pay Acme, my payments agent drafted a ₹1,18,400 transfer to the attacker's account, explained its reasoning clearly, and was completely sure of itself.

Nothing was wrong with the model. The problem was memory.

## Memory turns a one-time injection into a standing order

Without memory, a prompt injection only lasts one conversation. Close the session and it's gone. Once an agent has long-term memory, an injection becomes a **fact the agent believes from now on**. It's retained once and recalled every time a related question comes up, often weeks later, long after anyone remembers where it came from. OWASP now lists this as its own agent risk (memory poisoning, ASI06), and it changes how you have to think about [what agent memory actually is](https://vectorize.io/what-is-agent-memory): it's no longer a cache, it's an attack surface that persists.

Write-time filters help, and you should have them. But my polite email would pass any keyword filter. So I built the part I couldn't find anywhere: **what happens after the poison is already in memory.** I called it MemoryGuard. It detects the harmful action, explains why the memory is suspicious, traces everything that memory touched, and removes only the poisoned parts, then proves the fix.

## How it hangs together

The agent's long-term memory lives in [Hindsight, an open-source agent memory system](https://github.com/vectorize-io/hindsight). Every time something enters memory, whether an email, a web page, a chat message, a tool output or the agent's own answers, it goes through Hindsight's retain path, and every question goes through recall. Each agent gets its own memory bank: my vendor-payments agent and my IT-helpdesk agent never share memories.

MemoryGuard sits around that memory layer, not inside the model:

```
 email / web / chat / tools
            │
            ▼
   provenance envelope ──► Hindsight retain (content + metadata)
            │                       │
            ▼                       ▼
     lineage graph ◄──────── Hindsight recall ──► LLM ──► drafted action
            │                                                   │
            ▼                                                   ▼
  detectors + explainable score                    action gate vs system of record
            │                                                   │
            └──────────────► heal: quarantine, replay, audit ◄──┘
```

Hindsight does what a memory layer should: durable storage, recall that fuses semantic, keyword, graph and temporal search, and metadata travelling with every memory. I didn't want to build a vector store; I wanted to build the security around one.

The integration is small on purpose. Every memory is retained with its MemoryGuard id as the Hindsight `document_id` and its provenance as metadata and tags. The bank uses the `chunks` extraction mode, so the exact original text is stored, which matters when a gate has to compare account numbers character by character:

```python
item = {
    "content": content,
    "context": f"{meta.get('source_class')} memory from {meta.get('source_id')}",
    "document_id": memory_id,
    "metadata": {k: str(meta[k]) for k in META_FIELDS if k in meta},
    "tags": [f"source:{meta.get('source_class')}", f"session:{meta.get('session_id')}"],
}
self.client.retain(self.bank_id, item.pop("content"), **item)
```

On the way back, every recalled fact carries that `document_id`, so it maps to exactly one memory with its provenance attached. A quarantined memory is deleted from Hindsight, so it can never be recalled again:

```python
for rank, r in enumerate(resp.results or []):
    doc = r.document_id or (r.metadata or {}).get("memory_id")
    m = self.get(doc)
    if m is None:  # deleted (quarantined) or unknown - never surface it
        continue
```

The rest of this post covers the decisions that mattered.

## Decision 1: trust comes from *where*, never from *what*

My first design scored each memory's trustworthiness by reading it. That's backwards: an attacker controls the content, so content-based trust is attacker-controlled trust. Instead, every memory gets a provenance envelope at write time, stored as Hindsight metadata, and **trust is set by the source class only**:

```python
def make_envelope(content, source_class, source_id, session_id="seed", event_time=None) -> dict:
    """Build the metadata attached to every memory. Trust comes from source_class only."""
    accepted = now_iso()
    return {
        "source_class": source_class,
        "source_id": source_id,
        "session_id": session_id,
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "event_time": event_time or accepted,  # what the content claims
        "accepted_time": accepted,             # when we stored it
        "trust": config.TRUST_BY_SOURCE[source_class],
        "status": "live",
    }
```

The scale is boring on purpose: system of record 1.0, user chat 0.6, tool output 0.5, the agent's own answers 0.4, email 0.3, web 0.2. The `event_time` / `accepted_time` split turned out to matter more than I expected: a memory that *claims* to be from last March but was *stored* five minutes ago is worth a second look.

You can't add provenance later. If it isn't recorded at write time, no amount of analysis will tell you afterwards whether a memory came from the user or from a web page.

## Decision 2: memory is never the authority for an action

This is the main idea of the project. The agent is allowed to *believe* whatever it recalls. It is not allowed to *act* on a high-impact field (a bank account, a payment recipient, admin rights, a password-reset address) unless that value matches the **system of record**.

Before any drafted payment goes anywhere, the gate looks up the vendor's verified account. If the drafted account differs, it collects every memory that mentions the drafted account and checks the most trusted one:

```python
support = _supporting_memories(account)
max_trust = max((m.trust for m in support), default=0.0)
if max_trust < config.GATE_MIN_TRUST:
    verdict = "block"
    reasons.append(f"{why}; backed only by low-trust memory ({sources}, max trust {max_trust:.1f})")
else:
    verdict = "hold"
```

There's no model in that path. The same input always gives the same decision, and no injected sentence can talk it out of it. When I later added an IT-helpdesk agent, the engine didn't change. I added two new checks against a different source of truth: admin rights only for people on the official admin list, and password-reset links only to an employee's registered email or phone. Supporting a new kind of agent means supplying two things: **its source of truth and the actions to check.**

## Decision 3: a score you can't explain is a score nobody acts on

When the gate blocks something, the supporting memories get scored. Five signals, each between 0 and 1: contradicts the verified record, low-trust source, injection markers, similarity to known attack phrasings, and whether the memory touches a high-impact field. The total is a weighted sum, and each signal's share of the total *is* the explanation:

```python
total = sum(config.WEIGHTS[k] * v for k, (v, _) in values.items())
for key, (value, detail) in values.items():
    contribution = config.WEIGHTS[key] * value
    signals.append({"key": key, "contribution": contribution,
                    "share": contribution / total if total else 0.0, "detail": detail})
```

For the polite email, the inspector shows **0.70: contradicts verified record 50%, low-trust source 25%, high-impact field 14%, similar to known attack 11%, injection markers 0%**. That last zero is the point. A keyword filter would have scored this email as clean. No model training, no black box, and a reviewer can disagree with a specific line instead of with a number.

## Decision 4: trace answers, not just inputs

The most uncomfortable finding: **the agent poisons itself.** After recalling the fake email, it answered "Acme is now paid to 9174-6620-3381", and because agents retain their own answers, that answer went back into memory as a new, separate memory. Deleting the email alone would have left the agent still believing the lie.

So every retain records a `source → memory` edge, every recall records `memory → answer`, and every drafted action records `answer → action`. When something is flagged, the blast radius is a breadth-first walk from the poisoned source:

```python
def blast_radius(node_id: str) -> list[tuple[str, int]]:
    """All descendants of node_id (including itself) in BFS order, with hop depth."""
    g = _digraph()
    if node_id not in g:
        return []
    depths = nx.single_source_shortest_path_length(g, node_id)
    return sorted(depths.items(), key=lambda kv: (kv[1], kv[0]))
```

For the bank-change email that walk returns six nodes: the email source, the email memory, the first answer, the memory the agent wrote from that answer, the second answer, and the blocked payment. Healing moves exactly those memories to a vault (kept for forensics, deletable only with human approval), leaves the other 21 memories alone, and **replays every affected question** against the cleaned memory:

| Question | Before | After |
|---|---|---|
| Where do we pay Acme Supplies? | "…their new Harbor Point Bank account 9174-6620-3381" | "…the verified Northbridge Bank account 4021-7783-1190" |
| Pay Acme's invoice | payment to 9174-6620-3381, **blocked** | payment to 4021-7783-1190, drafted for review |

The replay is what makes people trust the cleanup: you aren't asked to believe the agent is fixed, you're shown it.

## What it catches in practice

- **A fake fact in plain sight**, the polite bank-change email above: blocked at the gate, score 0.70, about three seconds from injection to block in my runs.
- **An instruction hidden from humans**: a vendor web page with a CSS-hidden line telling the agent to add a second recipient to every payment. The agent followed it and drafted two payees; the gate blocked the unknown one. Score 0.91, so it was quarantined automatically without waiting for a click.
- **A data leak, not money**: a fake "Internal Audit" email from a look-alike domain asking for every vendor's bank details. Blocked twice: the recipient isn't in the company directory, and a data-loss rule stops verified bank details leaving the company domain.
- **The same pattern in IT**: a fake service-desk email claiming a Sales employee is now an admin. The helpdesk agent tried to send a colleague's password-reset link to the attacker's "recovery" address, and the gate blocked it.

It also has to stay quiet on normal content. I ingested ten real public sites, including news, docs, GitHub and a government site. Together they contained more than 200 hidden HTML snippets, and none were flagged. On a set of 32 labelled samples I wrote myself (21 benign, including hard negatives, and 11 attacks), the scanner caught 10 of 11 attacks with zero false positives. Those samples were also used while tuning, so treat that as a sanity check, not a benchmark.

## Lessons learned

**1. Detection is a signal; the gate is the control.** My one benchmark miss was a subtle fake fact ("settle invoices with our parent company instead") with no account number and no suspicious wording. The scanner scored it 0.22. That's why the real guarantee doesn't depend on the scanner: whatever payee the agent drafts, the gate compares the *account* with the system of record, and an unverified account is blocked. The flip side is also true: a lie that doesn't change a field the gate checks can get through, so the gate's coverage is your security boundary. Know exactly what it checks.

**2. Record provenance on every write, especially your own agent's writes.** The agent's answer going back into memory was the most important path in the system, and it's the one most designs forget.

**3. LLM judges are useful and unreliable.** A privilege-escalation sample passed in one run because the judge changed its mind. I replaced that check with two deterministic markers (role override and approval bypass) and kept the judge as one input among five.

**4. Keep untrusted text away from your own security model.** MemoryGuard's judge reads attacker-written text, so it gets the same treatment as the agent: untrusted content is marked word by word as data (Microsoft's spotlighting technique), and account numbers and email addresses are swapped for placeholders before any third-party LLM sees them.

**5. Separate the memory layer from the security layer.** Because Hindsight owns storage and recall, MemoryGuard only has to own provenance, lineage, gating and healing. Each half is simpler, and the security engine doesn't change when the agent does. If you're building on agent memory, the [Hindsight docs on retain and recall](https://hindsight.vectorize.io/) are worth reading with this question in mind: *where does every memory come from, and what would I have to undo if it were a lie?*

Prompt injection isn't solved, and I don't claim to have solved it. What I can say is that when a lie gets into my agent's memory, I now know where it came from, what it touched, and how to undo exactly that.
