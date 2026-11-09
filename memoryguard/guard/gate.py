"""Action gate: payment details are checked against the system of record, never taken from memory."""
import re
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


def check_email(email: dict) -> dict:
    """Data-leak gate for outgoing email: recipient vs company directory + DLP on confidential data."""
    d = config.directory()
    to = str(email.get("to") or "").strip()
    body = f"{email.get('subject', '')}\n{email.get('body', '')}"
    internal = to.lower().endswith("@" + d["internal_domain"])
    approved = to.lower() in {a.lower() for a in d["approved_external"]}
    verified = {fields.normalize_account(v["account"]): n for n, v in config.system_of_record().items()}
    leaked = [a for a in fields.extract_accounts(body) if fields.normalize_account(a) in verified]

    reasons, verdict, support = [], "allow", []
    if not internal and not approved:
        support = [m for m in get_store().list_all() if to.lower() in m.content.lower()]
        max_trust = max((m.trust for m in support), default=0.0)
        sources = ", ".join(sorted({m.metadata["source_class"] for m in support})) or "no memory at all"
        if max_trust < config.GATE_MIN_TRUST:
            verdict = "block"
            reasons.append(f"recipient {to} is not in the {d['company']} directory; backed only by low-trust "
                           f"memory ({sources}, max trust {max_trust:.1f})")
        else:
            verdict = "hold"
            reasons.append(f"recipient {to} is not in the directory; backed by {sources} - verify before sending")
    if leaked and not internal:
        verdict = "block"
        reasons.append(f"DLP: {len(leaked)} confidential vendor bank account(s) would leave {d['internal_domain']}")
    return {"decision": verdict, "reasons": reasons,
            "checks": [{"recipient": to, "internal": internal, "approved": approved, "confidential": leaked,
                        "supporting": [{"id": m.id, "trust": m.trust, "source_class": m.metadata["source_class"]}
                                       for m in support]}],
            "supporting_ids": [m.id for m in support], "checked_at": now_iso()}


ADMIN_ROLES = re.compile(r"\b(admin|administrator|superuser|root|domain admin|owner|full access)\b", re.I)


def find_employee(name: str) -> tuple[str, dict] | tuple[None, None]:
    """Match free text ('john', 'John Mathew', an email) to the IT directory."""
    low = (name or "").lower()
    for emp, rec in config.it_directory()["employees"].items():
        first, last = emp.lower().split()[0], emp.lower().split()[-1]
        if emp.lower() in low or rec["email"] in low or (first in low.split() and last in low):
            return emp, rec
    for emp, rec in config.it_directory()["employees"].items():
        if emp.lower().split()[0] in re.findall(r"[a-z]+", low):
            return emp, rec
    return None, None


def _low_trust_support(needles: list[str]) -> tuple[list, float, str]:
    support = [m for m in get_store().list_all() if all(n.lower() in m.content.lower() for n in needles)]
    max_trust = max((m.trust for m in support), default=0.0)
    sources = ", ".join(sorted({m.metadata["source_class"] for m in support})) or "no memory at all"
    return support, max_trust, sources


def _decision(verdict: str, reasons: list[str], support: list, check: dict) -> dict:
    return {"decision": verdict, "reasons": reasons, "supporting_ids": [m.id for m in support],
            "checks": [{**check, "supporting": [{"id": m.id, "trust": m.trust,
                                                  "source_class": m.metadata["source_class"]} for m in support]}],
            "checked_at": now_iso()}


def check_access(access: dict) -> dict:
    """IT gate: admin-level access only for people on the official admin list (the system of record)."""
    emp, rec = find_employee(str(access.get("user") or ""))
    role = str(access.get("role") or "")
    check = {"user": access.get("user"), "employee": emp, "role": role, "system": access.get("system")}
    if not emp:
        return _decision("block", [f"'{access.get('user')}' is not in the IT directory"], [], check)
    if not ADMIN_ROLES.search(role) or rec["email"] in config.it_directory()["admins"]:
        return _decision("allow", [], [], check)
    support, max_trust, sources = _low_trust_support([emp.split()[0]])
    support = [m for m in support if ADMIN_ROLES.search(m.content)]
    max_trust = max((m.trust for m in support), default=0.0)
    sources = ", ".join(sorted({m.metadata["source_class"] for m in support})) or "no memory at all"
    why = f"{emp} is a {rec['role']} ({rec['department']}), not on the official admin list"
    if max_trust < config.GATE_MIN_TRUST:
        return _decision("block", [f"{why}; the admin claim is backed only by low-trust memory "
                                   f"({sources}, max trust {max_trust:.1f})"], support, check)
    return _decision("hold", [f"{why}; backed by {sources} - IT Security must approve"], support, check)


def check_reset(reset: dict) -> dict:
    """IT gate: password-reset links go only to the employee's registered work email or phone."""
    emp, rec = find_employee(str(reset.get("user") or ""))
    send_to = str(reset.get("send_to") or "").strip()
    check = {"user": reset.get("user"), "employee": emp, "send_to": send_to}
    if not emp:
        return _decision("block", [f"'{reset.get('user')}' is not in the IT directory"], [], check)
    registered = {rec["email"].lower(), re.sub(r"\D", "", rec["phone"])}
    if not send_to or send_to.lower() in registered or re.sub(r"\D", "", send_to) in registered - {""}:
        return _decision("allow", [], [], check)
    support, max_trust, sources = _low_trust_support([send_to])
    why = f"reset link for {emp} would go to {send_to}, not the registered {rec['email']} / {rec['phone']} (account takeover)"
    if max_trust < config.GATE_MIN_TRUST:
        return _decision("block", [f"{why}; backed only by low-trust memory ({sources}, max trust {max_trust:.1f})"],
                         support, check)
    return _decision("hold", [f"{why}; verify with the employee first"], support, check)


def enforcement() -> str:
    """'enforce' blocks; 'monitor' (shadow mode) only logs what would have been blocked."""
    return db.kv_get("enforcement", config.POLICY["enforcement"])


def record_block(action_id: str, decision: dict, noun: str = "Payment") -> dict:
    """Detection by the gate: block the action, then flag + taint the memories that backed it."""
    graph.set_status([action_id], "blocked")
    incident, auto_quarantine = flag_memories(decision["supporting_ids"])
    incident["blocked_actions"].append(action_id)
    db.kv_set("incident", incident)
    db.log_event("blocked", f"{noun} blocked: {'; '.join(decision['reasons'])}", action_id=action_id)
    _auto_quarantine(auto_quarantine)
    return incident


def raise_incident(memory_ids: list[str]) -> dict:
    """Detection by a scan (e.g. scan-on-ingest): flag + taint, auto-quarantine above threshold."""
    incident, auto_quarantine = flag_memories(memory_ids)
    _auto_quarantine(auto_quarantine)
    return incident


def _auto_quarantine(memory_ids: list[str]) -> None:
    if memory_ids:  # score >= quarantine threshold -> automatic, reversible quarantine
        from heal import heal

        heal.quarantine(memory_ids, reason="auto: score above quarantine threshold")


def flag_memories(memory_ids: list[str]) -> tuple[dict, list[str]]:
    """Score + flag memories, taint their blast radius, open/extend the incident.

    Returns (incident, ids whose score is above the quarantine threshold).
    """
    store = get_store()
    detected_at = now_iso()
    incident = db.kv_get("incident") or {"active": False, "flagged": [], "roots": [], "blocked_actions": []}
    auto_quarantine, injected_times = [], []
    for mid in memory_ids:
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

    if not incident["active"]:
        incident.update(active=True, detected_at=detected_at)
        if injected_times:
            t0 = datetime.fromisoformat(min(injected_times))
            incident["injected_at"] = min(injected_times)
            incident["time_to_detect"] = round((datetime.fromisoformat(detected_at) - t0).total_seconds(), 2)
    db.kv_set("incident", incident)
    return incident, auto_quarantine
