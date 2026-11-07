"""Tiny LLM wrapper. One function: complete(system, user) -> str.

Providers (LLM_PROVIDER):
  groq      - OpenAI-compatible endpoint at api.groq.com
  openai    - any OpenAI-compatible endpoint (set LLM_BASE_URL)
  anthropic - Claude via the official SDK
  none      - no LLM; callers fall back to deterministic templates
"""
import json

import httpx

import config

DEFAULT_MODELS = {
    "groq": "openai/gpt-oss-120b",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-opus-5-5",
}
DEFAULT_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
}

_anthropic_client = None


def available() -> bool:
    return config.LLM_PROVIDER in DEFAULT_MODELS and bool(config.LLM_API_KEY)


def _model() -> str:
    return config.LLM_MODEL or DEFAULT_MODELS[config.LLM_PROVIDER]


def complete(system: str, user: str, max_tokens: int = 1024) -> str:
    """Return the model's text reply. Raises RuntimeError if no LLM is configured."""
    if not available():
        raise RuntimeError("No LLM configured (set LLM_PROVIDER and LLM_API_KEY in .env)")
    if config.LLM_PROVIDER == "anthropic":
        return _complete_anthropic(system, user, max_tokens)
    return _complete_openai_compatible(system, user, max_tokens)


def complete_json(system: str, user: str, max_tokens: int = 2048) -> dict:
    """Like complete(), but asks for a JSON object and parses it."""
    if not available():
        raise RuntimeError("No LLM configured (set LLM_PROVIDER and LLM_API_KEY in .env)")
    if config.LLM_PROVIDER == "anthropic":
        text = _complete_anthropic(system + "\nRespond with a single JSON object only.", user, max_tokens)
    else:
        text = _complete_openai_compatible(system, user, max_tokens, json_mode=True)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError(f"LLM did not return JSON: {text[:200]}")
    return json.loads(text[start : end + 1])


def _complete_openai_compatible(system: str, user: str, max_tokens: int, json_mode: bool = False) -> str:
    base = (config.LLM_BASE_URL or DEFAULT_BASE_URLS[config.LLM_PROVIDER]).rstrip("/")
    body = {
        "model": _model(),
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if "gpt-oss" in body["model"]:
        body["reasoning_effort"] = "low"  # fast, short reasoning for demo latency
    resp = httpx.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
        json=body,
        timeout=60,
    )
    resp.raise_for_status()
    return (resp.json()["choices"][0]["message"].get("content") or "").strip()


def _complete_anthropic(system: str, user: str, max_tokens: int) -> str:
    # Current Claude models reject sampling params (temperature) - low effort keeps
    # replies short and fast; determinism comes from fixed prompts and seed data.
    global _anthropic_client
    import anthropic

    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(api_key=config.LLM_API_KEY, timeout=60.0)
    resp = _anthropic_client.messages.create(
        model=_model(),
        max_tokens=max(max_tokens, 4000),  # leave room for adaptive thinking
        output_config={"effort": "low"},
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("LLM refused the request")
    return "".join(b.text for b in resp.content if b.type == "text").strip()
