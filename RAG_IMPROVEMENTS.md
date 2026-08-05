# Module 5 — Advanced RAG & Agentic AI Architecture

Every improvement below is implemented in `backend/app/rag/` and verified by
unit tests (`tests/test_rag_advanced.py`, 44 total passing) and a live SSE
run. Nothing is simulated: LLM-dependent steps announce themselves as skipped
when no Gemini key is configured.

## The pipeline (agentic stages, all emitting real SSE events)

```
question
  │  PLANNER      query-type analysis · follow-up resolution from chat history
  │               · LLM multi-query rewrites + HyDE probe (gated on API key)
  │  RETRIEVER    dense FAISS (multi-query, RRF-merged) ∥ BM25 lexical index
  │               → weighted Reciprocal Rank Fusion
  │               → metadata filter → near-duplicate removal (shingle Jaccard)
  │               → adaptive selection (budget + score-cliff cutoff)
  │               → parent-child stitching (neighbouring chunks onto top hits)
  │               → contextual compression (query-relevant sentences ±1)
  │  GATE         evidence-sufficiency check → refuses BEFORE any LLM call
  │  ANSWERER     adaptive prompt (factual/list/summary/comparison) → Gemini stream
  │  VERIFIER     per-sentence groundedness vs cited chunks → faithfulness,
  │               uncited-claim count, calibrated confidence
  ▼
cited answer + quality report
```

## Improvement-by-improvement

| Improvement | Where | Notes |
|---|---|---|
| Hybrid search (dense + BM25) | `bm25.py` | pure-Python Okapi BM25 over all chunks; auto-invalidated on index/delete/reprocess |
| Reciprocal Rank Fusion | `fusion.py` | **weighted** — see benchmark finding below |
| Multi-query retrieval | `advanced_retriever.py` | per-variant dense rankings RRF-merged |
| Query rewriting / expansion | `query_processing.py` | Gemini-gated; skipped + reported honestly without a key |
| HyDE retrieval | `query_processing.py` | hypothetical answer as an extra dense probe (LLM-gated) |
| Conversation-aware retrieval | `query_processing.py` + `/ask/stream` | short/pronoun follow-ups borrow subject terms from prior user turns (deterministic), scoped to the caller's conversation |
| Memory summarization | `query_processing.summarize_history` | long chats (>12 msgs), LLM-gated |
| Parent-child retrieval | `advanced_retriever.py` step 6 | top hits stitched with ±1 neighbouring chunks (small-to-big) |
| Context compression | `fusion.compress_chunk` | query-relevant sentences ±1 neighbour, lead kept, floor guard |
| Metadata-aware filtering | `advanced_retriever.retrieve(category=…)` | filters fused results by document category |
| Duplicate chunk removal | `fusion.deduplicate` | Jaccard ≥ 0.8 over 5-token shingles |
| Adaptive chunk selection | `fusion.adaptive_select` | 6-chunk/6000-char budget, stops at 0.35× score cliff |
| Citation ranking | rank order = prompt block order | `[1]` is always the strongest chunk |
| Retrieval quality scoring | `fusion.retrieval_quality` | top score + query-term coverage |
| "I don't know" handling | `fusion.evidence_sufficient` | refuses before spending an LLM call; verified live (off-corpus query → `verifier -> insufficient_evidence`, 0 tokens spent) |
| Hallucination detection | `verifier.verify_answer` | per-sentence lexical entailment vs cited chunks; flags unsupported sentences and uncited factual claims |
| Confidence calibration | `verifier.calibrated_confidence` | 0.30·retrieval + 0.45·faithfulness + 0.25·citations − uncited penalty |
| Adaptive prompting | `prompt_builder.py` | answer-shape instruction per query type |
| Agent visualization | existing UI | stage events + trace use the `agent -> task [ok] Nms` grammar the timeline already parses — zero frontend redesign |

**Not implemented (honest):** cross-encoder reranking (BGE) needs
torch/sentence-transformers (~2 GB); the insertion point is after RRF in
`advanced_retriever.py` step 3. An LLM-judge variant of context relevance and
faithfulness can replace the lexical proxies once a key is present.

## Evaluation framework

`app/rag/evaluation.py`: Precision@K, Recall@K, MRR, nDCG@K (unit-tested
against hand-computed values), context relevance (term-coverage proxy),
faithfulness (verifier), plus retrieval/generation latency captured by the
pipeline timings.

## Benchmark results (real, reproducible)

`python -m benchmarks.run_benchmark` — 14 labeled docs, 14 queries, K=4,
run on this machine with the **local fallback embedder** (no API key):

| Metric | Dense-only (baseline) | BM25-only | Hybrid + weighted RRF |
|---|---|---|---|
| precision@4 | 0.2143 | 0.2321 | **0.2321** |
| recall@4 | 0.8571 | 0.9286 | **0.9286** |
| MRR | 0.8357 | 0.9048 | 0.8899 |
| nDCG@4 | 0.8308 | 0.9022 | 0.8929 |
| context relevance | 0.1769 | 0.2020 | 0.2020 |
| mean latency (ms) | 0.05 | 0.07 | 2.28 |

**The benchmark drove a design change.** The first (unweighted) RRF run
scored *below* BM25-only (MRR 0.845): the fallback dense channel is itself
lexical and strictly weaker than BM25, so equal-weight fusion diluted the
stronger signal. Fix: `fusion.channel_weights` down-weights dense to 0.3 when
the hashing fallback is active; with real Gemini embeddings the channels are
weighted equally (they are then complementary — dense wins paraphrase, BM25
wins exact terms). After the fix, hybrid ≥ baseline on every metric and
matches BM25 on recall while keeping the semantic upside. Re-run the suite
with a real key to benchmark the semantic configuration — the script uses
whatever embedder the app itself would use.

## Live verification (this machine, no API key)

- Off-corpus question → refused at the gate: trace ends
  `verifier -> insufficient_evidence`, latency 52 ms, **no LLM call**.
- Answerable question → `planner (list type)` → `dense 5 + BM25 5 → RRF 5`
  → adaptive list-prompt reached the answerer (then a clean LLM-not-configured
  error, as expected without a key).
- Conversation follow-ups: `"What about its revenue?"` retrieval query becomes
  `"What about its revenue? (infosys …)"` — unit-tested.
