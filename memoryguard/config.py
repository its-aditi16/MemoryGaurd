"""Environment settings and tunable constants for MemoryGuard."""
import os
from pathlib import Path

from dotenv import load_dotenv

PKG_DIR = Path(__file__).resolve().parent
ROOT_DIR = PKG_DIR.parent
load_dotenv(ROOT_DIR / ".env")
load_dotenv(PKG_DIR / ".env")

# Keep demo console output clean (HF Hub / transformers chatter on Windows).
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

DATA_DIR = PKG_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
LOCAL_STORE_DB = DATA_DIR / "local_store.db"
GUARD_DB = DATA_DIR / "guard.db"
SYSTEM_OF_RECORD = PKG_DIR / "demo" / "system_of_record.json"

MEMORY_BACKEND = os.getenv("MEMORY_BACKEND", "local").lower()  # local | hindsight
EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

# LLM: groq | anthropic | openai (any OpenAI-compatible endpoint) | none
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "none").lower()
LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")

# Trust is set by source class ONLY, never by content.
TRUST_BY_SOURCE = {
    "system_of_record": 1.0,
    "user_chat": 0.6,
    "tool": 0.5,
    "agent_generated": 0.4,
    "email": 0.3,
    "web": 0.2,
}

# Explainable suspicion score weights (sum to 1.0).
WEIGHTS = {
    "contradicts_verified": 0.35,
    "low_trust": 0.25,
    "injection_markers": 0.20,
    "attack_similarity": 0.10,
    "high_impact_field": 0.10,
}
FLAG_THRESHOLD = 0.5
QUARANTINE_THRESHOLD = 0.7
GATE_MIN_TRUST = 0.5  # payment details must be backed by memory at least this trusted

RECALL_K = 8


def system_of_record() -> dict:
    """Verified vendor records: {vendor_name: {account, bank, branch_code, verified_on}}."""
    import json

    return json.loads(SYSTEM_OF_RECORD.read_text())["vendors"]


def it_directory() -> dict:
    """IT source of truth: official admin list + registered employee contacts (truth for the helpdesk gate)."""
    import json

    return json.loads(SYSTEM_OF_RECORD.read_text())["it"]


def directory() -> dict:
    """Company directory: internal domain + approved external recipients (truth for the email gate)."""
    import json

    return json.loads(SYSTEM_OF_RECORD.read_text())["directory"]


# ---- Local API access (security) --------------------------------------------
# A random token shared only by the API and the Vite proxy (dev.mjs creates it per run).
# Browser JavaScript never sees it, so other websites cannot call the API.
API_TOKEN_FILE = DATA_DIR / ".api_token"


def _api_token() -> str:
    import secrets

    token = os.getenv("MG_API_TOKEN")
    if token:
        return token
    if API_TOKEN_FILE.exists() and API_TOKEN_FILE.read_text().strip():
        return API_TOKEN_FILE.read_text().strip()
    token = secrets.token_urlsafe(32)
    API_TOKEN_FILE.write_text(token)
    return token


API_TOKEN = _api_token()
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
ALLOWED_ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173"}
MAX_QUESTION_CHARS = 1000
MAX_INGEST_TEXT_CHARS = 20000

# ---- Deployment policy (FDE): one reviewed file per customer, fail closed ----
POLICY_FILE = PKG_DIR / "deploy" / "policy.json"
AUDIT_LOG = DATA_DIR / "audit.jsonl"
KNOWN_ACTIONS = {"draft_payment", "draft_email", "grant_access", "reset_password"}


def _load_policy() -> dict:
    import json

    try:
        p = json.loads(POLICY_FILE.read_text())
    except FileNotFoundError:
        raise SystemExit(f"[MemoryGuard] Refusing to start: policy file missing ({POLICY_FILE})")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[MemoryGuard] Refusing to start: policy file is not valid JSON ({exc})")
    problems = []
    if p.get("enforcement") not in ("monitor", "enforce"):
        problems.append("enforcement must be 'monitor' or 'enforce'")
    if not isinstance(p.get("allowed_actions"), list) or not set(p["allowed_actions"]) <= KNOWN_ACTIONS:
        problems.append(f"allowed_actions must be a subset of {sorted(KNOWN_ACTIONS)}")
    if not isinstance(p.get("ingest_domain_allowlist"), list):
        problems.append("ingest_domain_allowlist must be a list (empty = any public site)")
    if not isinstance(p.get("ingest_sender_allowlist"), list):
        problems.append("ingest_sender_allowlist must be a list of addresses or @domains (empty = any sender)")
    if not isinstance(p.get("llm_providers_allowed"), list):
        problems.append("llm_providers_allowed must be a list")
    elif LLM_PROVIDER not in p["llm_providers_allowed"]:
        problems.append(f"LLM_PROVIDER '{LLM_PROVIDER}' is not in llm_providers_allowed {p['llm_providers_allowed']}")
    if not isinstance(p.get("vault_retention_days"), int) or p["vault_retention_days"] < 1:
        problems.append("vault_retention_days must be a positive integer")
    if problems:
        raise SystemExit("[MemoryGuard] Refusing to start, policy invalid: " + "; ".join(problems))
    return p


POLICY = _load_policy()
