# Retrieval Benchmark Results

Embedder: `local-hashing-v1` · 14 docs · 14 labeled queries · K=4

| Metric | Dense-only (baseline) | BM25-only | Hybrid + RRF (Module 5) |
|---|---|---|---|
| precision@4 | 0.2143 | 0.2321 | 0.2321 |
| recall@4 | 0.8571 | 0.9286 | 0.9286 |
| mrr | 0.8357 | 0.9048 | 0.8899 |
| ndcg@4 | 0.8308 | 0.9022 | 0.8929 |
| context_relevance | 0.1769 | 0.202 | 0.202 |
| mean_latency_ms | 0.05 | 0.06 | 2.28 |

_Numbers are produced by running this script on the real
retrieval code — regenerate with `python -m benchmarks.run_benchmark`._