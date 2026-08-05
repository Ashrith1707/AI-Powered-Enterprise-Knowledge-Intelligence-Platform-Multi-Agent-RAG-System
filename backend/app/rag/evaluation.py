"""Retrieval & answer evaluation metrics. Pure functions, unit-tested.

Retrieval metrics take a ranked list of retrieved ids and a set of relevant
ids (binary relevance). Answer metrics reuse the deterministic verifier.
"""
import math

from app.rag.bm25 import tokenize


# ---------------- retrieval metrics ----------------
def precision_at_k(retrieved: list, relevant: set, k: int) -> float:
    if k <= 0:
        return 0.0
    top = retrieved[:k]
    return sum(1 for r in top if r in relevant) / k


def recall_at_k(retrieved: list, relevant: set, k: int) -> float:
    if not relevant:
        return 0.0
    top = retrieved[:k]
    return sum(1 for r in top if r in relevant) / len(relevant)


def mrr(retrieved: list, relevant: set) -> float:
    for i, r in enumerate(retrieved, start=1):
        if r in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(retrieved: list, relevant: set, k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 1)
              for i, r in enumerate(retrieved[:k], start=1) if r in relevant)
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    return dcg / idcg if idcg else 0.0


# ---------------- context metrics ----------------
def context_relevance(query: str, texts: list[str]) -> float:
    """Mean fraction of query terms present per retrieved text (proxy metric —
    an LLM-judge variant can replace this when a key is configured)."""
    q_terms = set(tokenize(query))
    if not q_terms or not texts:
        return 0.0
    scores = [len(q_terms & set(tokenize(t))) / len(q_terms) for t in texts]
    return sum(scores) / len(scores)


def summarize_run(per_query: list[dict]) -> dict:
    """Averages a list of per-query metric dicts."""
    if not per_query:
        return {}
    keys = per_query[0].keys()
    return {k: round(sum(q[k] for q in per_query) / len(per_query), 4) for k in keys}
