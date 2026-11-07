"""Clean seed memory bank for the vendor-payments assistant, plus reset().

Run:  python -m demo.seed     (from the memoryguard/ directory)
"""
import config
import db
from guard.provenance import remember
from store import get_store


def _vendor_records() -> list[tuple[str, str, str, str]]:
    sor = config.system_of_record()
    return [
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


def seed() -> list[str]:
    """Write the vendor records and seed memories (with lineage); return their ids."""
    return [
        remember(content, source_class, source_id, event_time=event_time)
        for source_class, source_id, content, event_time in _vendor_records() + SEED_MEMORIES
    ]


def reset() -> list[str]:
    """Wipe the store and all guard state, then restore the clean seed."""
    get_store().clear()
    db.reset()
    db.kv_set("guard_enabled", True)
    ids = seed()
    db.log_event("reset", f"Clean memory bank restored ({len(ids)} memories)")
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
