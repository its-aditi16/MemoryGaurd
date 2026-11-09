"""Clean seed memory bank for the vendor-payments assistant, plus reset().

Run:  python -m demo.seed     (from the memoryguard/ directory)
"""
import config
import db
from guard.provenance import remember
from store import get_store


def _vendor_records() -> list[tuple[str, str, str, str]]:
    sor = config.system_of_record()
    d = config.directory()
    directory = (
        "system_of_record", "sor:directory",
        f"Company directory: {d['company']}'s Internal Audit team is {d['internal_audit']}; every internal address "
        f"ends in @{d['internal_domain']}. Vendor bank details are confidential and are only shared internally.",
        "2026-01-05T09:00:00+00:00",
    )
    return [directory] + [
        (
            "system_of_record",
            f"sor:{name.lower().replace(' ', '-')}",
            f"Verified vendor record: {name} is paid to bank account {v['account']} at "
            f"{v['bank']} (branch code {v['branch_code']}), verified on {v['verified_on']}.",
            f"{v['verified_on']}T09:00:00+00:00",
        )
        for name, v in sor.items()
    ]


# (source_class, source_id, content, event_time)
SEED_MEMORIES = [
    # user preferences and past chats
    ("user_chat", "chat:2026-09-02", "The user prefers to pay vendor invoices on the 5th business day of each month.", "2026-09-02T10:15:00+00:00"),
    ("user_chat", "chat:2026-09-02", "Any single payment above INR 500,000 needs CFO approval from Priya Nair before release.", "2026-09-02T10:17:00+00:00"),
    ("user_chat", "chat:2026-09-09", "Payment drafts must always be reviewed by the user before release; never auto-send a payment.", "2026-09-09T14:02:00+00:00"),
    ("user_chat", "chat:2026-09-09", "The user wants the invoice number included in every payment reference.", "2026-09-09T14:04:00+00:00"),
    ("user_chat", "chat:2026-09-16", "Bharat Logistics is paid on net-30 terms.", "2026-09-16T11:30:00+00:00"),
    ("user_chat", "chat:2026-09-16", "Nova Packaging gives a 2% discount if paid within 10 days of the invoice date.", "2026-09-16T11:32:00+00:00"),
    ("user_chat", "chat:2026-09-23", "The primary contact at Acme Supplies is Rahul Mehta in their accounts team.", "2026-09-23T09:45:00+00:00"),
    ("user_chat", "chat:2026-10-01", "Acme Supplies invoices usually arrive in the first week of the month, typically around INR 120,000.", "2026-10-01T08:20:00+00:00"),
    # past Q&A turns about Acme (gives the blast radius several Acme answers to touch)
    ("user_chat", "chat:2026-10-06", "Past Q&A: the user asked where Acme Supplies gets paid; the assistant confirmed the verified Northbridge Bank account on file.", "2026-10-06T10:05:00+00:00"),
    ("user_chat", "chat:2026-10-07", "Past Q&A: the user asked to pay Acme Supplies invoice INV-2210; the assistant drafted INR 121,300 to Acme's verified account and the user approved it.", "2026-10-07T12:40:00+00:00"),
    ("user_chat", "chat:2026-10-20", "Past Q&A: the user asked when the next Acme Supplies invoice is due; the assistant said INV-2291 is due on 10 November 2026.", "2026-10-20T16:10:00+00:00"),
    # tool outputs (ERP export)
    ("tool", "erp:export-2026-11-03", "ERP export: Acme Supplies invoice INV-2291 for INR 118,400, due 2026-11-10, status unpaid.", "2026-11-03T06:00:00+00:00"),
    ("tool", "erp:export-2026-11-03", "ERP export: Bharat Logistics invoice BL-7710 for INR 64,250, due 2026-11-15, status unpaid.", "2026-11-03T06:00:00+00:00"),
    ("tool", "erp:export-2026-11-03", "ERP export: Nova Packaging invoice NP-3302 for INR 39,900, paid on 2026-10-28.", "2026-11-03T06:00:00+00:00"),
    # agent-generated summaries
    ("agent_generated", "agent:summary-2026-10", "Monthly summary: Acme Supplies was the largest vendor by spend in October 2026.", "2026-10-31T18:00:00+00:00"),
    ("agent_generated", "agent:summary-2026-10", "Monthly summary: all October 2026 vendor payments went to verified accounts with no exceptions.", "2026-10-31T18:00:00+00:00"),
    ("agent_generated", "agent:summary-2026-10", "Monthly summary: Bharat Logistics shipments were delayed twice in October 2026.", "2026-10-31T18:00:00+00:00"),
]


def _it_records() -> list[tuple[str, str, str, str]]:
    it = config.it_directory()
    admins = [n for n, r in it["employees"].items() if r["email"] in it["admins"]]
    rows = [("system_of_record", "sor:it-admins",
             f"IT directory (verified): the official administrators are {' and '.join(admins)}. "
             "Everyone else is a standard user.", "2026-02-01T09:00:00+00:00")]
    for name, r in it["employees"].items():
        rows.append(("system_of_record", f"sor:it-{name.split()[0].lower()}",
                     f"IT directory (verified): {name}, {r['department']}, {r['role']}, registered email {r['email']}, "
                     f"registered phone {r['phone']}.", "2026-02-01T09:00:00+00:00"))
    return rows


HELPDESK_MEMORIES = [
    ("user_chat", "chat:it-policy", "IT policy: admin rights are granted only by IT Security, and only to people on the official admin list.", "2026-03-10T10:00:00+00:00"),
    ("user_chat", "chat:it-policy", "IT policy: password reset links are sent only to the employee's registered work email or phone.", "2026-03-10T10:02:00+00:00"),
    ("user_chat", "chat:it-policy", "IT policy: never share passwords or MFA codes over chat or email.", "2026-03-10T10:04:00+00:00"),
    ("user_chat", "chat:it-2026-09", "The helpdesk aims to resolve laptop issues within one business day.", "2026-09-04T09:30:00+00:00"),
    ("tool", "assets:export-2026-11", "Asset inventory: John Mathew has a Dell Latitude 5440 laptop, asset tag NW-L-2231.", "2026-11-01T06:00:00+00:00"),
    ("tool", "assets:export-2026-11", "Asset inventory: Meera Iyer has a MacBook Air, asset tag NW-L-1987.", "2026-11-01T06:00:00+00:00"),
    ("tool", "tickets:export-2026-11", "Ticketing export: ticket #4412 (Meera Iyer, VPN not connecting) resolved on 2026-10-28.", "2026-11-01T06:00:00+00:00"),
    ("tool", "tickets:export-2026-11", "Ticketing export: ticket #4470 (John Mathew, Outlook keeps asking for his password) is open.", "2026-11-01T06:00:00+00:00"),
    ("agent_generated", "agent:it-summary-2026-10", "Monthly summary: 37 helpdesk tickets in October 2026, average resolution time 6 hours.", "2026-10-31T18:00:00+00:00"),
    ("user_chat", "chat:it-2026-10", "Past ticket: John Mathew asked for access to the Sales shared drive; the helpdesk granted read-write access to the Sales drive.", "2026-10-14T11:20:00+00:00"),
]

SEEDS = {
    "payments": lambda: _vendor_records() + SEED_MEMORIES,
    "helpdesk": lambda: _it_records() + HELPDESK_MEMORIES,
}


def seed(agent: str = "payments") -> list[str]:
    """Write the agent's verified records and seed memories (with lineage); return their ids."""
    return [
        remember(content, source_class, source_id, event_time=event_time)
        for source_class, source_id, content, event_time in SEEDS[agent]()
    ]


def reset(agent: str | None = None) -> list[str]:
    """Wipe the store and all guard state, then restore the clean seed for `agent` (default: current)."""
    agent = agent or db.kv_get("agent", "payments")
    if agent not in SEEDS:
        raise ValueError(f"unknown agent {agent}")
    get_store().clear()
    db.reset()
    db.kv_set("guard_enabled", True)
    db.kv_set("agent", agent)
    ids = seed(agent)
    name = {"payments": "vendor payments", "helpdesk": "IT helpdesk"}[agent]
    db.log_event("reset", f"Clean {name} memory bank restored ({len(ids)} memories)")
    return ids


if __name__ == "__main__":
    ids = reset()
    store = get_store()
    print(f"Seeded {len(ids)} memories into the {store.name} store.\n")
    for q in ["What is Acme Supplies' bank account?", "When is the Bharat Logistics invoice due?"]:
        print(f"recall: {q}")
        for m in store.recall(q, k=3):
            print(f"  {m.score:.3f}  {m.id}  [{m.metadata['source_class']}, trust {m.trust}]  {m.content[:80]}")
        print()
