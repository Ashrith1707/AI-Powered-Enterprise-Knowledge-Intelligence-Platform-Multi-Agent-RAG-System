"""Embedding provider tests (local provider; Gemini path mocked)."""
from __future__ import annotations

import numpy as np

from app.services.embeddings import (
    LocalHashEmbeddingProvider,
    embedding_provider_status,
    get_embedding_provider,
)


def test_local_provider_is_deterministic():
    provider = LocalHashEmbeddingProvider(dimensions=128)
    a = provider.embed_texts(["machine safety lockout"])
    b = provider.embed_texts(["machine safety lockout"])
    assert np.allclose(a, b)


def test_local_provider_outputs_are_normalized():
    provider = LocalHashEmbeddingProvider(dimensions=256)
    vectors = provider.embed_texts(["first text", "second text", "third text"])
    norms = np.linalg.norm(vectors, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)
    assert vectors.dtype == np.float32


def test_similar_texts_score_higher_than_unrelated():
    provider = LocalHashEmbeddingProvider(dimensions=384)
    q = provider.embed_query("machine maintenance safety requirements")
    similar = provider.embed_query("safety requirements for machine maintenance work")
    unrelated = provider.embed_query("chocolate cake birthday party recipe")
    assert float(q @ similar) > float(q @ unrelated)


def test_empty_input():
    provider = LocalHashEmbeddingProvider(dimensions=64)
    out = provider.embed_texts([])
    assert out.shape == (0, 64)


def test_configured_provider_is_local_in_tests(env):
    provider = get_embedding_provider()
    assert provider.name == "local-hash"
    status = embedding_provider_status()
    assert status["provider"] == "local-hash"
    assert "text-embedding-004" not in str(status)  # deprecated model must never appear


def test_gemini_provider_maps_errors(monkeypatch):
    """When the Gemini embedding call fails, errors are classified — e.g. a 404
    must surface as model_not_found, never as 'invalid API key'."""
    from app.core.errors import AIErrorCode
    from app.services.embeddings import GeminiEmbeddingProvider

    provider = GeminiEmbeddingProvider("fake-key", "text-embedding-004", 768)

    class FakeModels:
        def embed_content(self, **kwargs):
            raise Exception("404 models/text-embedding-004 is not found for API version v1beta")

    class FakeClient:
        models = FakeModels()

    provider._client = FakeClient()  # noqa: SLF001 — test seam

    import pytest

    from app.core.errors import AIProviderError

    with pytest.raises(AIProviderError) as excinfo:
        provider.embed_texts(["hello"])
    assert excinfo.value.error_code == AIErrorCode.MODEL_NOT_FOUND
    assert "api key" not in excinfo.value.message.lower()
