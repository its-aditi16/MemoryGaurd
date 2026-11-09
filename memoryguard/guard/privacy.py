"""Pseudonymize sensitive values before text reaches a third-party LLM.

Account numbers and email addresses become stable tokens (ACCT_1, EMAIL_2) for one request;
the reply is un-masked afterwards. The gate and the score always work on the real values,
so the LLM provider never needs to see them.
"""
import re

import config
from guard import fields

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
TOKEN_RE = re.compile(r"\b(ACCT|EMAIL)[_-](\d+)\b")


class Pseudonymizer:
    def __init__(self):
        self.enabled = bool(config.POLICY.get("pseudonymize_llm_inputs", True))
        self._fwd: dict[tuple[str, str], str] = {}
        self._rev: dict[str, str] = {}

    def _token(self, kind: str, value: str, key: str) -> str:
        if (kind, key) not in self._fwd:
            tok = f"{kind}_{sum(1 for k, _ in self._fwd if k == kind) + 1}"
            self._fwd[(kind, key)] = tok
            self._rev[tok] = value
        return self._fwd[(kind, key)]

    def mask(self, text: str) -> str:
        if not self.enabled:
            return text
        text = EMAIL_RE.sub(lambda m: self._token("EMAIL", m.group(0), m.group(0).lower()), text)
        return fields.ACCOUNT_RE.sub(
            lambda m: self._token("ACCT", m.group(0).replace(" ", "-"), fields.normalize_account(m.group(0))), text)

    def unmask(self, obj):
        if isinstance(obj, str):
            return TOKEN_RE.sub(lambda m: self._rev.get(f"{m.group(1)}_{m.group(2)}", m.group(0)), obj)
        if isinstance(obj, list):
            return [self.unmask(x) for x in obj]
        if isinstance(obj, dict):
            return {k: self.unmask(v) for k, v in obj.items()}
        return obj
