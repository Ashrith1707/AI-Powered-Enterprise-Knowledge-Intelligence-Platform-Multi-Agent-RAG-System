"""RAG evaluation metrics (Module 7).

Retrieval: Precision@K, Recall@K, MRR, nDCG@K — computed from labeled
(qrel) data against the actual retrieval rankings.

Generation: faithfulness, answer relevance, citation accuracy, groundedness —
computed from the actual pipeline outputs (answer, evidences, citations).
Lexical estimators are deterministic and documented; optional LLM-judge
versions are used only when a real Gemini provider is configured (never with
the offline mock — that would be fabricated evaluation).

System: latencies, token usage, chunk counts, verification failures — read
from the pipeline's own metrics object.

No score in this module is ever invented: every number is computed from a
real run.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

from app.services.embeddings import tokenize

# ---------------------------------------------------------------------------
# Retrieval metrics
# ---------------------------------------------------------------------------

def precision_at_k(retrieved_ids: Sequence[int], relevant_ids: Sequence[int], k: int) -> float:
    if k <= 0 or not relevant_ids:
        return 0.0
    top = list(retrieved_ids)[:k]
    relevant = set(relevant_ids)
    return sum(1 for cid in top if cid in relevant) / k


def recall_at_k(retrieved_ids: Sequence[int], relevant_ids: Sequence[int], k: int) -> float:
    if not relevant_ids:
        return 0.0
    top = set(list(retrieved_ids)[:k])
    return len(top & set(relevant_ids)) / len(set(relevant_ids))


def reciprocal_rank(retrieved_ids: Sequence[int], relevant_ids: Sequence[int]) -> float:
    relevant = set(relevant_ids)
    for rank, cid in enumerate(retrieved_ids, start=1):
        if cid in relevant:
            return 1.0 / rank
    return 0.0


def mrr(ranked_lists: Sequence[Sequence[int]], relevant_lists: Sequence[Sequence[int]]) -> float:
    if not ranked_lists:
        return 0.0
    return sum(reciprocal_rank(r, rel) for r, rel in zip(ranked_lists, relevant_lists)) / len(ranked_lists)


def dcg_at_k(gains: Sequence[float], k: int) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(list(gains)[:k]))


def ndcg_at_k(retrieved_ids: Sequence[int], relevance_grades: Dict[int, float], k: int) -> float:
    """relevance_grades: chunk_id → grade (0..3 typical)."""
    gains = [float(relevance_grades.get(cid, 0.0)) for cid in list(retrieved_ids)[:k]]
    ideal = sorted(relevance_grades.values(), reverse=True)
    ideal_gains = [float(g) for g in ideal[:k]]
    idcg = dcg_at_k(ideal_gains, k)
    if idcg == 0:
        return 0.0
    return dcg_at_k(gains, k) / idcg


def retrieval_metrics(
    retrieved_ids: Sequence[int],
    relevant_ids: Sequence[int],
    relevance_grades: Optional[Dict[int, float]] = None,
    k_values: Sequence[int] = (3, 5, 10),
) -> Dict[str, float]:
    grades = relevance_grades or {cid: 1.0 for cid in relevant_ids}
    out: Dict[str, float] = {}
    for k in k_values:
        out[f"precision@{k}"] = round(precision_at_k(retrieved_ids, relevant_ids, k), 4)
        out[f"recall@{k}"] = round(recall_at_k(retrieved_ids, relevant_ids, k), 4)
        out[f"ndcg@{k}"] = round(ndcg_at_k(retrieved_ids, grades, k), 4)
    out["mrr"] = round(reciprocal_rank(retrieved_ids, relevant_ids), 4)
    return out


# ---------------------------------------------------------------------------
# Generation metrics (deterministic estimators)
# ---------------------------------------------------------------------------
_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "is", "are", "was", "were", "for", "on", "with"}


def _words(text: str) -> set:
    return {t for t in tokenize(text) if t not in _STOP and len(t) > 2}


_BOILERPLATE_RE = None


def _content_text(answer: str) -> str:
    """Strip answer boilerplate (preambles, mock-mode notices) so faithfulness
    measures the actual content lines."""
    global _BOILERPLATE_RE
    if _BOILERPLATE_RE is None:
        import re

        _BOILERPLATE_RE = re.compile(
            r"(based on the retrieved enterprise documents|here is what they say"
            r"|answer produced in offline mock mode|configure gemini_api_key"
            r"|for full generative answers)",
            re.IGNORECASE,
        )
    lines = [line for line in answer.splitlines() if not _BOILERPLATE_RE.search(line)]
    return "\n".join(lines)


def faithfulness(answer: str, evidence_texts: Sequence[str]) -> float:
    """Fraction of answer content words covered by the evidence pool."""
    answer_words = _words(_content_text(answer))
    if not answer_words:
        return 1.0 if not answer.strip() else 0.0
    evidence_words = set().union(*[_words(e) for e in evidence_texts]) if evidence_texts else set()
    return round(len(answer_words & evidence_words) / len(answer_words), 4)


def answer_relevance(answer: str, question: str) -> float:
    """Lexical relevance of the answer to the question."""
    q_words = _words(question)
    a_words = _words(answer)
    if not q_words or not a_words:
        return 0.0
    overlap = len(q_words & a_words) / len(q_words)
    length_penalty = 1.0 if 20 <= len(a_words) <= 400 else 0.85
    return round(min(1.0, overlap * length_penalty), 4)


def citation_accuracy(citations: Sequence[dict], retrieved_chunk_ids: Sequence[int]) -> float:
    """Fraction of emitted citations that point at actually retrieved chunks."""
    if not citations:
        return 0.0
    retrieved = set(retrieved_chunk_ids)
    valid = sum(1 for c in citations if c.get("chunk_id") in retrieved)
    return round(valid / len(citations), 4)


def groundedness(answer: str, evidences: Sequence) -> float:
    """Sentence-level groundedness using the same entailment logic as the
    Verification Agent (consistency between eval and runtime)."""
    from app.agents.verifier import split_claims, _best_sentence_match, _SENT_RE

    claims = split_claims(answer)
    if not claims:
        return 1.0
    sentences: List[str] = []
    for ev in evidences:
        sentences.extend(s.strip() for s in _SENT_RE.split(ev.text) if s.strip())
    if not sentences:
        return 0.0
    supported = sum(1 for claim in claims if _best_sentence_match(claim, sentences)[0] >= 0.55)
    return round(supported / len(claims), 4)


def generation_metrics(
    answer: str,
    question: str,
    evidences: Sequence,
    citations: Sequence[dict],
    retrieved_chunk_ids: Sequence[int],
) -> Dict[str, float]:
    evidence_texts = [ev.text for ev in evidences]
    return {
        "faithfulness": faithfulness(answer, evidence_texts),
        "answer_relevance": answer_relevance(answer, question),
        "citation_accuracy": citation_accuracy(citations, retrieved_chunk_ids),
        "groundedness": groundedness(answer, evidences),
    }


def system_metrics(response_metrics) -> Dict[str, float]:
    return {
        "retrieval_latency_ms": response_metrics.retrieval_latency_ms,
        "generation_latency_ms": response_metrics.generation_latency_ms,
        "total_latency_ms": response_metrics.total_latency_ms,
        "verification_latency_ms": response_metrics.verification_latency_ms,
        "chunks_retrieved": response_metrics.chunks_retrieved,
        "evidences_used": response_metrics.evidences_used,
        "prompt_tokens": response_metrics.token_usage.get("prompt_tokens") or 0,
        "output_tokens": response_metrics.token_usage.get("output_tokens") or 0,
        "verification_failures": response_metrics.verification_failures,
        "regenerations": response_metrics.regenerations,
    }
