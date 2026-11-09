"""Simple field extractors for high-impact data: account numbers, vendors, sensitive fields."""
import re

import config

ACCOUNT_RE = re.compile(r"\b\d{4}[- ]\d{4}[- ]\d{4}\b|\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")

HIGH_IMPACT_PATTERNS = {
    "bank_account": r"\b(bank|account number|account no|iban|routing|branch code|ifsc|swift)\b",
    "recipient": r"\b(recipient|beneficiary|payee|pay(ment)?s? to|send (the )?(money|funds|payment))\b",
    "permission": r"\b(permissions?|admin|access rights?|approv(e|al|als)|authori[sz](e|ed|ation))\b",
    "contact": r"\b(contact|email address|phone|@[\w-]+\.\w+)\b",
    # A memory that tries to set who the agent trusts or recommends from now on changes future decisions.
    "standing_trust_instruction": r"\b(remember|store|save|keep|treat|memori[sz]e)\b.{0,80}?\b(trusted|authoritative|"
                                  r"preferred|go-to|official|recommended)\b.{0,40}\b(source|site|website|provider|reference)",
}


def normalize_account(acct: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", acct).upper()


def extract_accounts(text: str) -> list[str]:
    seen, out = set(), []
    for m in ACCOUNT_RE.findall(text):
        n = normalize_account(m)
        if n not in seen:
            seen.add(n)
            out.append(m.replace(" ", "-"))
    return out


def vendor_for(name: str) -> str | None:
    """Map free text (e.g. 'Acme', 'acme supplies ltd') to a system-of-record vendor name."""
    low = name.lower()
    for vendor in config.system_of_record():
        if vendor.lower() in low or re.search(rf"\b{re.escape(vendor.split()[0].lower())}\b", low):
            return vendor
    return None


def vendors_mentioned(text: str) -> list[str]:
    low = text.lower()
    return [
        v for v in config.system_of_record()
        if v.lower() in low or re.search(rf"\b{re.escape(v.split()[0].lower())}\b", low)
    ]


def verified_account(vendor: str) -> str | None:
    rec = config.system_of_record().get(vendor)
    return rec["account"] if rec else None


def high_impact_fields(text: str) -> list[str]:
    low = text.lower()
    found = [name for name, pat in HIGH_IMPACT_PATTERNS.items() if re.search(pat, low)]
    if extract_accounts(text) and "bank_account" not in found:
        found.insert(0, "bank_account")
    return found
