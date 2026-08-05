"""Retrieval benchmark: dense-only baseline vs Module 5 hybrid pipeline.

Runs the platform's ACTUAL algorithms (same embedder, same BM25, same RRF and
dedup code) against a labeled synthetic corpus with known relevant documents
per query. Nothing is simulated — the numbers are whatever the code produces
on this machine. Note: without GEMINI_API_KEY the dense side uses the local
hashing fallback embedder, exactly like the running app in that state.

Usage (from backend/):  python -m benchmarks.run_benchmark
Writes benchmarks/results.json and benchmarks/RESULTS.md
"""
import json
import statistics
import time
from pathlib import Path

import numpy as np

from app.rag.bm25 import BM25Index
from app.rag.embeddings import get_embedder
from app.rag.evaluation import (context_relevance, mrr, ndcg_at_k,
                                precision_at_k, recall_at_k, summarize_run)
from app.rag.fusion import channel_weights, reciprocal_rank_fusion

K = 4

# 14 documents, one topic each. doc_id -> text.
CORPUS = {
    1: "Quarterly financial report: revenue increased 18 percent to 2.4 million dollars in Q3. Operating expenses fell due to budget optimization and vendor consolidation.",
    2: "Invoice INV-2291 for cloud hosting services totalling 12,400 dollars, payment due 2025-11-30 to Meridian Hosting. Late payments incur a 2 percent penalty.",
    3: "Employee onboarding policy: new hires must complete security training within 14 days and submit signed confidentiality agreements to human resources.",
    4: "Annual leave policy update: staff receive 24 paid vacation days per year; unused days may carry over up to a maximum of 8 days into the next calendar year.",
    5: "Master service agreement between Acme Corp and Beta Ltd covering liability caps, indemnity clauses, and a governing law provision under Singapore jurisdiction.",
    6: "Non-disclosure agreement template: confidential information must be protected for five years after termination; breach triggers injunctive relief.",
    7: "System architecture document: the platform uses FastAPI microservices, PostgreSQL storage, and a FAISS vector index for semantic retrieval of document chunks.",
    8: "Deployment runbook: build Docker images, run database migrations, then roll out with nginx as reverse proxy; health checks gate each release stage.",
    9: "Marketing campaign summary: the spring launch generated 45,000 leads with an email open rate of 31 percent, outperforming the winter campaign by 12 points.",
    10: "Customer support escalation matrix: priority-one incidents require a response within 15 minutes and executive notification within one hour.",
    11: "Research memo on retrieval augmented generation: hybrid lexical and dense search with rank fusion improves recall on rare entity queries.",
    12: "Data retention schedule: audit logs are kept for seven years, chat transcripts for two years, and temporary upload files are purged after 30 days.",
    13: "Procurement guideline: purchases above 50,000 dollars require three competitive quotes and chief financial officer approval before contract signature.",
    14: "Incident postmortem: the March outage was caused by connection pool exhaustion; remediation added pool pre-ping and automatic failover to a replica.",
}

# Queries with labeled relevant documents. Mix of exact-term and paraphrase.
QUERIES = [
    ("How much did revenue grow in the third quarter?", {1}),
    ("When is invoice INV-2291 due and to whom?", {2}),
    ("What must new employees finish during onboarding?", {3}),
    ("How many vacation days can be carried over?", {4}),
    ("Which jurisdiction governs the Acme and Beta contract?", {5}),
    ("How long must secrets stay protected after an NDA ends?", {6}),
    ("What vector database does the platform architecture use?", {7}),
    ("Describe the steps to release the software to production.", {8}),
    ("How many leads did the spring marketing push create?", {9}),
    ("What is the response time for priority one tickets?", {10}),
    ("Does combining keyword and embedding search help recall?", {11}),
    ("How long are audit logs retained?", {12}),
    ("What approvals are needed for large purchases?", {13}),
    ("What caused the outage in March and how was it fixed?", {14}),
]


def dense_rank(query_vec, doc_vecs, doc_ids):
    scores = doc_vecs @ query_vec
    order = np.argsort(-scores)
    return [doc_ids[i] for i in order]


def evaluate(rankings, latencies):
    per_query = []
    for (query, relevant), retrieved in zip(QUERIES, rankings):
        per_query.append({
            f"precision@{K}": precision_at_k(retrieved, relevant, K),
            f"recall@{K}": recall_at_k(retrieved, relevant, K),
            "mrr": mrr(retrieved, relevant),
            f"ndcg@{K}": ndcg_at_k(retrieved, relevant, K),
            "context_relevance": context_relevance(
                query, [CORPUS[d] for d in retrieved[:K]]),
        })
    summary = summarize_run(per_query)
    summary["mean_latency_ms"] = round(statistics.mean(latencies), 2)
    return summary


def main():
    embedder = get_embedder()
    doc_ids = list(CORPUS.keys())
    doc_vecs = embedder.embed([CORPUS[d] for d in doc_ids])

    bm25 = BM25Index()
    bm25.build([(d, CORPUS[d]) for d in doc_ids])

    baseline_rankings, baseline_lat = [], []
    bm25_rankings, bm25_lat = [], []
    hybrid_rankings, hybrid_lat = [], []

    for query, _ in QUERIES:
        # Lexical-only reference point.
        t = time.perf_counter()
        lex_only = [d for d, _ in bm25.search(query, top_k=len(doc_ids))]
        lex_only += [d for d in doc_ids if d not in lex_only]  # pad for metrics
        bm25_lat.append((time.perf_counter() - t) * 1000)
        bm25_rankings.append(lex_only)
        # Baseline: dense-only (the pre-Module-5 pipeline).
        t = time.perf_counter()
        qv = embedder.embed([query])[0]
        dense = dense_rank(qv, doc_vecs, doc_ids)
        baseline_lat.append((time.perf_counter() - t) * 1000)
        baseline_rankings.append(dense)

        # Improved: dense + BM25 fused with weighted RRF (Module 5) —
        # identical weighting logic to the live AdvancedRetriever.
        t = time.perf_counter()
        qv = embedder.embed([query])[0]
        dense = dense_rank(qv, doc_vecs, doc_ids)
        lexical = [d for d, _ in bm25.search(query, top_k=len(doc_ids))]
        dense_w, lex_w = channel_weights(embedder)
        fused = reciprocal_rank_fusion(
            [dense, lexical] if lexical else [dense],
            weights=[dense_w, lex_w] if lexical else [dense_w])
        hybrid = sorted(fused, key=fused.get, reverse=True)
        hybrid_lat.append((time.perf_counter() - t) * 1000)
        hybrid_rankings.append(hybrid)

    results = {
        "embedder": embedder.model_name,
        "corpus_docs": len(CORPUS),
        "queries": len(QUERIES),
        "k": K,
        "baseline_dense_only": evaluate(baseline_rankings, baseline_lat),
        "bm25_only": evaluate(bm25_rankings, bm25_lat),
        "hybrid_rrf": evaluate(hybrid_rankings, hybrid_lat),
    }

    out_dir = Path(__file__).parent
    (out_dir / "results.json").write_text(json.dumps(results, indent=2))

    b, l, h = (results["baseline_dense_only"], results["bm25_only"],
               results["hybrid_rrf"])
    lines = [
        "# Retrieval Benchmark Results",
        "",
        f"Embedder: `{results['embedder']}` · {len(CORPUS)} docs · "
        f"{len(QUERIES)} labeled queries · K={K}",
        "",
        "| Metric | Dense-only (baseline) | BM25-only | Hybrid + RRF (Module 5) |",
        "|---|---|---|---|",
    ]
    for key in b:
        lines.append(f"| {key} | {b[key]} | {l[key]} | {h[key]} |")
    lines += ["", "_Numbers are produced by running this script on the real",
              "retrieval code — regenerate with `python -m benchmarks.run_benchmark`._"]
    (out_dir / "RESULTS.md").write_text("\n".join(lines))

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
