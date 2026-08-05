"""Embedding provider abstraction.

Primary: Gemini text-embedding-004 via LangChain.
Fallback: deterministic local hashing embedder so the whole platform stays
demoable (upload, search, agents) even without an API key — with reduced
semantic quality, clearly logged.
"""
import hashlib
import math
import re

import numpy as np

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger("embeddings")
FALLBACK_DIM = 256


class HashingEmbedder:
    """Bag-of-hashed-words embedding. Deterministic, offline, demo-grade."""
    model_name = "local-hashing-v1"
    dimension = FALLBACK_DIM

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), FALLBACK_DIM), dtype="float32")
        for row, text in enumerate(texts):
            for word in re.findall(r"[a-z0-9]{2,}", text.lower()):
                slot = int(hashlib.md5(word.encode()).hexdigest(), 16) % FALLBACK_DIM
                vectors[row, slot] += 1.0
            norm = math.sqrt((vectors[row] ** 2).sum()) or 1.0
            vectors[row] /= norm
        return vectors


class GeminiEmbedder:
    model_name = settings.gemini_embedding_model
    dimension = 768

    def __init__(self):
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        self.client = GoogleGenerativeAIEmbeddings(
            model=settings.gemini_embedding_model,
            google_api_key=settings.gemini_api_key,
        )

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = np.array(self.client.embed_documents(texts), dtype="float32")
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vectors / norms


_embedder = None


def get_embedder():
    global _embedder
    if _embedder is None:
        if settings.gemini_api_key:
            try:
                candidate = GeminiEmbedder()
                candidate.embed(["connection probe"])   # invalid keys fail HERE, not at init
                _embedder = candidate
                logger.info("Using Gemini embeddings (%s).", _embedder.model_name)
            except Exception as exc:
                logger.error("Gemini embeddings unavailable (%s) — falling back to the "
                             "local hashing embedder. Check GEMINI_API_KEY.", exc)
                _embedder = HashingEmbedder()
        else:
            logger.warning("GEMINI_API_KEY not set — using local hashing embeddings.")
            _embedder = HashingEmbedder()
    return _embedder
