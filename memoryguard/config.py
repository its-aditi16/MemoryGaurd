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
