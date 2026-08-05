"""Rank fusion and result shaping: RRF, dedup, adaptive selection,
context compression and retrieval-quality scoring. All deterministic."""
import re

from app.rag.bm25 import tokenize

RRF_K = 60


def reciprocal_rank_fusion(rankings: list[list[int]], k: int = RRF_K,
                           weights: list[float] | None = None) -> dict[int, float]:
    """rankings: lists of ids, best first. Returns id -> fused score.
    An item ranked highly in MULTIPLE lists beats one ranked highly in one.
    Optional per-ranking weights let a stronger channel dominate."""
    weights = weights or [1.0] * len(rankings)
    fused: dict[int, float] = {}
    for ranking, weight in zip(rankings, weights):
        for rank, item_id in enumerate(ranking):
            fused[item_id] = fused.get(item_id, 0.0) + weight / (k + rank + 1)
    return fused


def channel_weights(embedder) -> tuple[float, float]:
    """(dense_weight, lexical_weight). Benchmark-driven: the local hashing
    fallback embedder is itself lexical and strictly weaker than BM25, so its
    ranking must not dilute BM25's (see benchmarks/RESULTS.md). With real
    semantic embeddings the channels are complementary and weighted equally."""
    from app.rag.embeddings import HashingEmbedder
    if isinstance(embedder, HashingEmbedder):
        return (0.3, 1.0)
    return (1.0, 1.0)


def _shingles(text: str, size: int = 5) -> set:
    tokens = tokenize(text)
    if len(tokens) < size:
        return {tuple(tokens)}
    return {tuple(tokens[i:i + size]) for i in range(len(tokens) - size + 1)}


def deduplicate(chunks: list, threshold: float = 0.8) -> list:
    """Drops near-duplicate chunks (Jaccard over 5-token shingles).
    Duplicates arise from overlapping chunk windows and re-uploaded content."""
    kept = []
    kept_shingles = []
    for chunk in chunks:
        sh = _shingles(chunk.text)
        duplicate = False
        for existing in kept_shingles:
            union = len(sh | existing)
            if union and len(sh & existing) / union >= threshold:
                duplicate = True
                break
        if not duplicate:
            kept.append(chunk)
            kept_shingles.append(sh)
    return kept


def adaptive_select(chunks: list, max_chunks: int = 6, char_budget: int = 6000,
                    score_floor_ratio: float = 0.35) -> list:
    """Takes ranked chunks until the context budget is spent, stopping early
    at a score cliff — long tails of weak chunks dilute the prompt."""
    if not chunks:
        return []
    top_score = chunks[0].score or 1e-9
    selected, used = [], 0
    for chunk in chunks:
        if len(selected) >= max_chunks or used + len(chunk.text) > char_budget:
            break
        if len(selected) >= 2 and chunk.score < score_floor_ratio * top_score:
            break
        selected.append(chunk)
        used += len(chunk.text)
    return selected


SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def compress_chunk(text: str, query: str, trigger_chars: int = 800,
                   min_chars: int = 80) -> str:
    """Contextual compression for long chunks: keep sentences sharing terms
    with the query, each with one neighbouring sentence for context, plus the
    lead sentence. Reverts to the original only if almost nothing survives."""
    if len(text) <= trigger_chars:
        return text
    q_terms = set(tokenize(query))
    sentences = SENTENCE_RE.split(text)
    relevant = {i for i, s in enumerate(sentences) if q_terms & set(tokenize(s))}
    keep = {0}
    for i in relevant:
        keep |= {i - 1, i, i + 1}
    compressed = " ".join(s for i, s in enumerate(sentences) if i in keep)
    if len(compressed) < min_chars:
        return text
    return compressed


def retrieval_quality(query: str, chunks: list) -> dict:
    """Deterministic quality signals used for refusal gating and confidence."""
    q_terms = set(tokenize(query))
    if not chunks:
        return {"top_score": 0.0, "term_coverage": 0.0, "chunks": 0}
    covered = set()
    for chunk in chunks:
        covered |= q_terms & set(tokenize(chunk.text))
    return {
        "top_score": round(float(chunks[0].score), 4),
        "term_coverage": round(len(covered) / len(q_terms), 3) if q_terms else 0.0,
        "chunks": len(chunks),
    }


def evidence_sufficient(quality: dict) -> bool:
    """'I don't know' gate: refuse BEFORE spending an LLM call when the
    retrieved context clearly cannot support an answer."""
    if quality["chunks"] == 0:
        return False
    return not (quality["term_coverage"] < 0.15 and quality["top_score"] < 0.2)
