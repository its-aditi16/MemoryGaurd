"""Shared sentence-transformers embedder (loaded once, reused by store and detectors)."""
from functools import lru_cache

import numpy as np

import config


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    try:  # use the cached copy so the demo works offline after the first download
        return SentenceTransformer(config.EMBED_MODEL, device="cpu", local_files_only=True)
    except Exception:
        return SentenceTransformer(config.EMBED_MODEL, device="cpu")


def embed(texts: list[str]) -> np.ndarray:
    """Return L2-normalised float32 embeddings, shape (len(texts), dim)."""
    vecs = _model().encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vecs, dtype=np.float32)


def embed_one(text: str) -> np.ndarray:
    return embed([text])[0]
