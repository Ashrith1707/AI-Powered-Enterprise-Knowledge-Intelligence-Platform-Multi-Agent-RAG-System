"""Retrieval tests: BM25, RRF fusion, vector store, search endpoint."""
from __future__ import annotations

import numpy as np

from app.rag.bm25 import BM25Index
from app.rag.hybrid import fuse_rankings, normalize_scores
from tests.conftest import HR_DOC, SAFETY_DOC, upload_document, wait_for_processing


# ---------------------------------------------------------------------------
# BM25
# ---------------------------------------------------------------------------
def test_bm25_ranks_relevant_document_first():
    index = BM25Index()
    index.build([
        (1, "machine maintenance requires lockout tagout and safety glasses"),
        (2, "annual leave entitlement is 24 days per year for employees"),
        (3, "passwords must be 14 characters and mfa is mandatory"),
    ])
    results = index.search("safety lockout maintenance machine", top_k=3)
    assert results[0][0] == 1
    assert results[0][1] > 0


def test_bm25_respects_allowed_filter():
    index = BM25Index()
    index.build([(1, "safety manual content"), (2, "safety policy content")])
    results = index.search("safety", top_k=5, allowed_chunk_ids={2})
    assert [cid for cid, _ in results] == [2]


def test_bm25_upsert_and_remove():
    index = BM25Index()
    index.build([(1, "first document about apples")])
    index.upsert(2, "second document about oranges")
    assert index.size == 2
    index.upsert(2, "second document about apples and oranges")
    results = index.search("apples", top_k=2)
    assert {cid for cid, _ in results} == {1, 2}
    index.remove([1])
    results = index.search("apples", top_k=2)
    assert [cid for cid, _ in results] == [2]


def test_bm25_no_match_returns_empty():
    index = BM25Index()
    index.build([(1, "apples and oranges")])
    assert index.search("quantum chromodynamics", top_k=5) == []


# ---------------------------------------------------------------------------
# Hybrid fusion (RRF)
# ---------------------------------------------------------------------------
def test_rrf_prefers_chunks_in_both_lists():
    vector = [(10, 0.9), (11, 0.8), (12, 0.7)]
    keyword = [(11, 5.0), (13, 4.0), (10, 3.0)]
    fused = fuse_rankings(vector, keyword)
    top_ids = [h.chunk_id for h in fused]
    # 10 and 11 appear in both lists → they must outrank single-list hits
    assert set(top_ids[:2]) == {10, 11}
    by_id = {h.chunk_id: h for h in fused}
    assert by_id[11].sources == ["vector", "keyword"]
    assert by_id[12].sources == ["vector"]
    assert by_id[11].keyword_rank == 1 and by_id[11].vector_rank == 2


def test_normalize_scores_bounds():
    fused = fuse_rankings([(1, 0.9), (2, 0.5)], [])
    norm = normalize_scores(fused)
    assert max(norm) == 1.0 and min(norm) == 0.0
    assert normalize_scores([]) == []


# ---------------------------------------------------------------------------
# Vector store
# ---------------------------------------------------------------------------
def test_vector_store_add_search_remove(env):
    from app.services.vector_store import get_vector_store

    store = get_vector_store(dimensions=64)
    rng = np.random.default_rng(42)
    vecs = rng.standard_normal((3, 64)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    store.add([101, 102, 103], vecs)
    assert store.count == 3

    results = store.search(vecs[1], top_k=1)
    assert results[0][0] == 102
    assert results[0][1] > 0.99  # self-similarity

    results = store.search(vecs[0], top_k=3, allowed_chunk_ids={103})
    assert [cid for cid, _ in results] == [103]

    store.remove([102])
    assert store.count == 2
    assert not store.contains(102)
    store.clear()
    assert store.count == 0


def test_vector_store_persists_across_instances(env):
    from app.services.vector_store import FaissIndex, get_vector_store

    store = get_vector_store(dimensions=32)
    vec = np.eye(32, dtype=np.float32)[0:1]
    store.add([7], vec)

    reloaded = FaissIndex(32)
    assert reloaded.count == 1
    results = reloaded.search(vec[0], top_k=1)
    assert results[0][0] == 7


# ---------------------------------------------------------------------------
# Search endpoint (integration)
# ---------------------------------------------------------------------------
def test_search_endpoint_hybrid(client, user_client):
    client, headers, _ = user_client
    doc = upload_document(client, headers, "safety.txt", SAFETY_DOC.encode())
    wait_for_processing(client, headers, doc["id"])
    upload_document(client, headers, "hr.txt", HR_DOC.encode())
    wait_for_processing(client, headers, doc["id"] + 1)

    r = client.post("/api/search", headers=headers,
                    json={"query": "lockout tagout machine maintenance", "mode": "hybrid", "top_k": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    top = body["hits"][0]
    assert top["document_id"] == doc["id"]
    assert "vector" in top["sources"] or "keyword" in top["sources"]
    assert top["page_start"] >= 1


def test_search_keyword_mode(client, user_client):
    client, headers, _ = user_client
    doc = upload_document(client, headers, "hr.txt", HR_DOC.encode())
    wait_for_processing(client, headers, doc["id"])
    r = client.post("/api/search", headers=headers,
                    json={"query": "annual leave 24 days", "mode": "keyword"})
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_search_with_metadata_filters(client, user_client):
    client, headers, _ = user_client
    d1 = upload_document(client, headers, "safety.txt", SAFETY_DOC.encode())
    wait_for_processing(client, headers, d1["id"])
    d2 = upload_document(client, headers, "hr.txt", HR_DOC.encode())
    wait_for_processing(client, headers, d2["id"])

    r = client.post("/api/search", headers=headers, json={
        "query": "leave days entitlement", "mode": "hybrid",
        "filters": {"department": "Human Resources"},
    })
    hits = r.json()["hits"]
    assert hits and all(h["document_id"] == d2["id"] for h in hits)


def test_search_requires_auth(client):
    r = client.post("/api/search", json={"query": "anything"})
    assert r.status_code == 401
