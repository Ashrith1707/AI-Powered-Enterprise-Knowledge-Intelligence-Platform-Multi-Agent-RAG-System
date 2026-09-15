"""Hybrid retrieval fusion (Reciprocal Rank Fusion).

Combines vector (semantic) and BM25 (keyword) rankings with RRF:

    score(d) = Σ_lists 1 / (k + rank_list(d))

RRF is rank-based, so heterogeneous score scales (cosine vs BM25) need no
normalization. Per-source scores are retained for the reranker.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

DEFAULT_RRF_K = 60


@dataclass
class FusedHit:
    chunk_id: int
    rrf_score: float
    vector_rank: int | None = None
    vector_score: float | None = None
    keyword_rank: int | None = None
    keyword_score: float | None = None
    sources: List[str] = field(default_factory=list)


def fuse_rankings(
    vector_results: Sequence[Tuple[int, float]],
    keyword_results: Sequence[Tuple[int, float]],
    rrf_k: int = DEFAULT_RRF_K,
) -> List[FusedHit]:
    """Fuse two ranked lists into one RRF-ranked list."""
    fused: Dict[int, FusedHit] = {}

    for rank, (cid, score) in enumerate(vector_results):
        hit = fused.setdefault(cid, FusedHit(chunk_id=cid, rrf_score=0.0))
        hit.rrf_score += 1.0 / (rrf_k + rank + 1)
        hit.vector_rank = rank + 1
        hit.vector_score = score
        if "vector" not in hit.sources:
            hit.sources.append("vector")

    for rank, (cid, score) in enumerate(keyword_results):
        hit = fused.setdefault(cid, FusedHit(chunk_id=cid, rrf_score=0.0))
        hit.rrf_score += 1.0 / (rrf_k + rank + 1)
        hit.keyword_rank = rank + 1
        hit.keyword_score = score
        if "keyword" not in hit.sources:
            hit.sources.append("keyword")

    ordered = sorted(fused.values(), key=lambda h: h.rrf_score, reverse=True)
    return ordered


def normalize_scores(hits: Sequence[FusedHit]) -> List[float]:
    """Min-max normalize RRF scores into 0..1 (stable for empty/degenerate input)."""
    if not hits:
        return []
    scores = [h.rrf_score for h in hits]
    lo, hi = min(scores), max(scores)
    if hi - lo < 1e-9:
        return [1.0] * len(hits)
    return [(s - lo) / (hi - lo) for s in scores]
