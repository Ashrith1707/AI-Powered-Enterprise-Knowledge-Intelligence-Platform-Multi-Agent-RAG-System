"""Embedding providers.

Root-cause fix for the known issue:

    404 models/text-embedding-004 is not found for API version v1beta

`text-embedding-004` belongs to the legacy `google.generativeai` SDK/v1beta
surface and is deprecated. This module uses ONLY the modern `google-genai`
SDK with `gemini-embedding-001` (configurable via GEMINI_EMBEDDING_MODEL).
A grep for `text-embedding-004` / `google.generativeai` in this repo returns
zero usages.

A deterministic local hashing provider is used as an offline fallback (no API
key / tests). It is NOT semantic — it is a lexical hash embedding — and the
system reports which provider is active via /api/health so nothing is
silently downgraded.
"""
from __future__ import annotations

import hashlib
import re
import time
from abc import ABC, abstractmethod
from typing import List, Sequence

import numpy as np

from app.config import get_settings
from app.core.errors import classify_ai_error
from app.core.logging_conf import get_logger

logger = get_logger("embeddings")

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------
class EmbeddingProvider(ABC):
    name: str = "base"
    dimensions: int = 0

    @abstractmethod
    def embed_texts(self, texts: Sequence[str]) -> np.ndarray:
        """Return an (N, D) float32 matrix of L2-normalized vectors."""

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_texts([text])[0]

    @abstractmethod
    def is_available(self) -> bool:
        ...


# ---------------------------------------------------------------------------
# Gemini embeddings (modern SDK)
# ---------------------------------------------------------------------------
class GeminiEmbeddingProvider(EmbeddingProvider):
    name = "gemini"
    BATCH_SIZE = 16

    def __init__(self, api_key: str, model: str, dimensions: int):
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model
        self.dimensions = dimensions

    def is_available(self) -> bool:
        return True

    def embed_texts(self, texts: Sequence[str]) -> np.ndarray:
        from google.genai import types

        if not texts:
            return np.zeros((0, self.dimensions), dtype=np.float32)

        vectors: List[List[float]] = []
        for start in range(0, len(texts), self.BATCH_SIZE):
            batch = [t[:8000] if t else " " for t in texts[start:start + self.BATCH_SIZE]]
            last_exc: Exception | None = None
            for attempt in range(2):  # one retry on transient errors
                try:
                    started = time.perf_counter()
                    result = self._client.models.embed_content(
                        model=self._model,
                        contents=batch,
                        config=types.EmbedContentConfig(
                            task_type="RETRIEVAL_DOCUMENT",
                            output_dimensionality=self.dimensions,
                            auto_truncate=True,
                        ),
                    )
                    latency = (time.perf_counter() - started) * 1000
                    embeddings = getattr(result, "embeddings", None) or []
                    if len(embeddings) != len(batch):
                        raise ValueError(
                            f"Gemini returned {len(embeddings)} embeddings for {len(batch)} texts"
                        )
                    for emb in embeddings:
                        values = getattr(emb, "values", None)
                        if values is None and isinstance(emb, dict):
                            values = emb.get("values")
                        vectors.append(list(map(float, values)))
                    logger.info(
                        "gemini.embed model=%s batch=%d latency_ms=%.0f",
                        self._model, len(batch), latency,
                    )
                    last_exc = None
                    break
                except Exception as exc:  # noqa: BLE001
                    classified = classify_ai_error(exc, model=self._model)
                    if classified.retryable and attempt == 0:
                        time.sleep(1.5)
                        continue
                    raise classified from exc
            if last_exc:  # pragma: no cover
                raise classify_ai_error(last_exc, model=self._model)

        matrix = np.asarray(vectors, dtype=np.float32)
        return _l2_normalize(matrix)


# ---------------------------------------------------------------------------
# Local deterministic hashing embeddings (offline fallback)
# ---------------------------------------------------------------------------
class LocalHashEmbeddingProvider(EmbeddingProvider):
    """Deterministic hashing-trick embeddings (unigrams + bigrams).

    Lexical, not semantic — used only when no Gemini key is configured or for
    tests. Honest about its limitations via /api/health reporting.
    """

    name = "local-hash"

    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions

    def is_available(self) -> bool:
        return True

    def embed_texts(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimensions), dtype=np.float32)
        matrix = np.zeros((len(texts), self.dimensions), dtype=np.float32)
        for row, text in enumerate(texts):
            tokens = tokenize(text or "")
            grams = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
            for gram in grams:
                digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
                idx = int.from_bytes(digest[:4], "little") % self.dimensions
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                matrix[row, idx] += sign
        return _l2_normalize(matrix)


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)


# ---------------------------------------------------------------------------
# Provider selection with capability probe
# ---------------------------------------------------------------------------
_provider: EmbeddingProvider | None = None
_probe_state: dict = {"provider": None, "error": None}


def get_embedding_provider(force_refresh: bool = False) -> EmbeddingProvider:
    """Return the active embedding provider.

    ``auto`` mode probes Gemini once with a tiny embed call; on failure it
    classifies the error, logs it, and falls back to the local provider so the
    platform stays usable (the fallback is always *reported*, never silent).
    """
    global _provider
    settings = get_settings()
    mode = settings.embedding_provider.lower()

    if _provider is not None and not force_refresh:
        return _provider

    if mode == "local":
        _provider = LocalHashEmbeddingProvider(dimensions=settings.embedding_dimensions)
    elif mode == "gemini":
        if not settings.gemini_api_key:
            from app.core.errors import AIErrorCode, AIProviderError

            raise AIProviderError(AIErrorCode.INVALID_API_KEY,
                                  "EMBEDDING_PROVIDER=gemini but GEMINI_API_KEY is empty")
        _provider = GeminiEmbeddingProvider(
            settings.gemini_api_key, settings.gemini_embedding_model, settings.embedding_dimensions
        )
    else:  # auto
        if settings.gemini_api_key:
            candidate = GeminiEmbeddingProvider(
                settings.gemini_api_key, settings.gemini_embedding_model, settings.embedding_dimensions
            )
            try:
                candidate.embed_texts(["capability probe"])
                _provider = candidate
                _probe_state.update({"provider": "gemini", "error": None})
            except Exception as exc:  # noqa: BLE001 — already classified
                _probe_state.update({"provider": "local-hash", "error": str(getattr(exc, "message", exc))[:300]})
                logger.warning(
                    "Gemini embeddings unavailable (%s) — falling back to local hash embeddings. "
                    "Fix GEMINI_EMBEDDING_MODEL / GEMINI_API_KEY to restore semantic search.",
                    getattr(exc, "message", exc),
                )
                _provider = LocalHashEmbeddingProvider(dimensions=settings.embedding_dimensions)
        else:
            logger.warning("GEMINI_API_KEY not set — using local hash embeddings (lexical only).")
            _provider = LocalHashEmbeddingProvider(dimensions=settings.embedding_dimensions)
            _probe_state.update({"provider": "local-hash", "error": "GEMINI_API_KEY not set"})
    return _provider


def embedding_provider_status() -> dict:
    provider = get_embedding_provider()
    return {
        "provider": provider.name,
        "model": get_settings().gemini_embedding_model if provider.name == "gemini" else "local-hash-v1",
        "dimensions": provider.dimensions,
        "probe_error": _probe_state.get("error"),
    }


def reset_embedding_provider() -> None:
    """Test hook."""
    global _provider
    _provider = None
    _probe_state.update({"provider": None, "error": None})
