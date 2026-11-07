"""Store factory: get_store() returns the singleton for MEMORY_BACKEND."""
from functools import lru_cache

import config
from store.base import Memory, MemoryStore


@lru_cache(maxsize=1)
def get_store() -> MemoryStore:
    if config.MEMORY_BACKEND == "hindsight":
        from store.hindsight_store import HindsightStore  # added in build step 10

        return HindsightStore()
    from store.local_store import LocalStore

    return LocalStore()


__all__ = ["get_store", "Memory", "MemoryStore"]
