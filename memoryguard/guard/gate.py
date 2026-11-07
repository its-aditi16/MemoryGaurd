"""Action gate: payment details are checked against the system of record, never taken from memory."""
from datetime import datetime

import config
import db
from guard import fields
from guard.provenance import now_iso
from guard.score import explain, score_memory
from lineage import graph
from store import get_store


def _supporting_memories(account: str) -> list:
    """Every stored memory that contains this account number."""
    norm = fields.normalize_account(account)
    return [m for m in get_store().list_all()
            if norm in {fields.normalize_account(a) for a in fields.extract_accounts(m.content)}]


def check_payment(payment: dict) -> dict:
    """Return {decision: allow|hold|block, reasons, checks, supporting_ids}."""
    checks, reasons, supporting_ids = [], [], []
    for r in payment["recipients"]:
        name, account = str(r.get("name") or "?"), str(r["account"])
        vendor = fields.vendor_for(name)
        expected = fields.verified_account(vendor) if vendor else None
        check = {"recipient": name, "account": account, "vendor": vendor, "expected": expected}
        if expected and fields.normalize_account(expected) == fields.normalize_account(account):
            checks.append({**check, "verdict": "ok", "supporting": []})
            continue

        support = _supporting_memories(account)
        max_trust = max((m.trust for m in support), default=0.0)
        sources = ", ".join(sorted({m.metadata["source_class"] for m in support})) or "no memory at all"
        if vendor:
            why = f"{account} is not the verified account for {vendor} ({expected})"
        else:
            why = f"recipient '{name}' ({account}) is not in the system of record"
        if max_trust < config.GATE_MIN_TRUST:
            verdict = "block"
            reasons.append(f"{why}; backed only by low-trust memory ({sources}, max trust {max_trust:.1f})")
        else:
            verdict = "hold"
            reasons.append(f"{why}; backed by {sources} (trust {max_trust:.1f}) - verify before paying")
        supporting_ids += [m.id for m in support]
        checks.append({**check, "verdict": verdict,
                       "supporting": [{"id": m.id, "trust": m.trust, "source_class": m.metadata["source_class"]}
                                      for m in support]})

    verdicts = {c["verdict"] for c in checks}
    decision = "block" if "block" in verdicts else "hold" if "hold" in verdicts else "allow"
    return {"decision": decision, "reasons": reasons, "checks": checks,
            "supporting_ids": list(dict.fromkeys(supporting_ids)), "checked_at": now_iso()}


def record_block(action_id: str, decision: dict) -> dict:
    """Detection: block the action, score + flag the supporting memories, taint their blast radius."""
    store = get_store()
    detected_at = now_iso()
    graph.set_status([action_id], "blocked")

    incident = db.kv_get("incident") or {"active": False, "flagged": [], "roots": [], "blocked_actions": []}
    auto_quarantine, injected_times = [], []
    for mid in decision["supporting_ids"]:
        m = store.get(mid)
        if not m:
            continue
        result = score_memory(m)
        status = "quarantined" if result["suggested_status"] == "quarantined" else "flagged"
        store.update_metadata(mid, status="flagged", score=result["score"])
        graph.update_data(mid, flagged=True, score=result["score"])
        if mid not in incident["flagged"]:
            incident["flagged"].append(mid)
            db.log_event("flagged", f"{mid} flagged, score {result['score']:.2f}: {explain(result)}",
                         memory_id=mid, score=result["score"])
        if status == "quarantined":
            auto_quarantine.append(mid)
        if m.metadata.get("session_id") not in ("seed", "chat"):
            injected_times.append(m.metadata["accepted_time"])
        root = graph.source_of(mid) or mid
        if root not in incident["roots"]:
            incident["roots"].append(root)
        graph.taint(root)

    incident["blocked_actions"].append(action_id)
    if not incident["active"]:
        incident.update(active=True, detected_at=detected_at)
        if injected_times:
            t0 = datetime.fromisoformat(min(injected_times))
            incident["injected_at"] = min(injected_times)
            incident["time_to_detect"] = round((datetime.fromisoformat(detected_at) - t0).total_seconds(), 2)
    db.kv_set("incident", incident)
    db.log_event("blocked", f"Payment blocked: {decision['reasons'][0]}", action_id=action_id)

    if auto_quarantine:  # score >= quarantine threshold -> automatic, reversible quarantine
        from heal import heal

        heal.quarantine(auto_quarantine, reason="auto: score above quarantine threshold")
    return incident
