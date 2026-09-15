# RAG Improvements (Module 5) — what was implemented and why

This file documents the RAG modernization: the deprecated-model fix, retrieval upgrades, and the quality machinery around them. Everything listed here is implemented and covered by tests (`backend/tests/`).

---

## 1. Root-cause fix: the `text-embedding-004` 404

**Symptom (historical):**

```
404 models/text-embedding-004 is not found for API version v1beta
```

…while the frontend claimed *“The Gemini API key is INVALID.”*

**Root causes:**
1. `text-embedding-004` belongs to the legacy `google.generativeai` SDK surface and is deprecated/removed on `v1beta`.
2. Error handling collapsed every provider failure into one misleading “invalid key” message.

**Fixes:**
* The repo uses **only** the modern `google-genai` SDK (`genai.Client(...).models.embed_content / generate_content / generate_content_stream`).
* Default embedding model: **`gemini-embedding-001`** (configurable via `GEMINI_EMBEDDING_MODEL`); default generation model: `gemini-2.5-flash` (`GEMINI_MODEL`).
* `grep -rn "text-embedding-004\|google.generativeai" backend/app frontend/src` → **zero usages**; a CI job (`deprecated-model-guard`) fails the build if they ever reappear.
* `app/core/errors.py::classify_ai_error` maps provider exceptions to distinct codes — **401 invalid_api_key · 403 permission_denied · 404 model_not_found · 429 quota_exceeded · 5xx provider_error · network_error · timeout** — each with an honest, actionable user-facing message. The frontend renders `error.details.ai_error_code` (see the `ErrorBanner` and the Ask AI error card). A 404 now says *“model unavailable — text-embedding-004 is deprecated; use gemini-embedding-001”*, never “invalid key”.
* “Auto” provider modes **probe** Gemini and report fallbacks loudly (`/api/health`, Settings page, sidebar badge) — functionality is never silently downgraded.

Tests: `test_error_classification.py`, `test_embeddings.py::test_gemini_provider_maps_errors`.

## 2. Hybrid retrieval architecture

* **Vector:** FAISS `IndexFlatIP` over L2-normalized vectors (cosine), persisted (`faiss.write_index` + JSON id-map), thread-safe, with a pure-numpy fallback implementing the same interface if the wheel is unavailable.
* **Keyword:** dependency-free in-memory **BM25 (Okapi)** index (`app/rag/bm25.py`) synced from the DB at startup and incrementally on ingest/delete.
* **Fusion:** **Reciprocal Rank Fusion** (`app/rag/hybrid.py`, k=60) — rank-based, so cosine and BM25 scales need no fragile normalization. Per-source ranks/scores are retained on every hit.
* The `/api/search` endpoint exposes all three modes (`hybrid | semantic | keyword`) with metadata filters; the Retriever Agent uses the same building blocks.

Tests: `test_retrieval.py`.

## 3. Query rewriting & multi-query retrieval

`app/rag/query_rewrite.py` + Retriever Agent:

* Deterministic variant expansion: original + keyword-compressed form + sub-questions split on conjunctions/question marks (max 3 variants).
* Optional LLM rewriting hook (`rewrite_with_llm`) that **never breaks retrieval** — any failure falls back to deterministic variants.
* Each variant is embedded in one batch; results are fused per-variant and merged across variants with **duplicate-chunk elimination** (best score kept, all matching variants recorded in `matched_queries`).
* Metadata hints (years, departments, categories, quoted phrases) are extracted from the query and handed to the Planner/Metadata agents.

## 4. Dynamic top-K

The Planner scales `top_k` (4–16) with query complexity: multi-part questions (+2), comparisons (+2), long queries (+1), multiple retrieval variants (+2 over the base `RETRIEVAL_TOP_K=8`). Visible in the plan trace.

## 5. Reranking with absolute relevance

`RerankerAgent` (strategy pattern: `LexicalCompositeReranker` default, `LLMReranker` optional/off by default for cost):

```
score = 0.40·similarity + 0.30·keyword-coverage + 0.15·exact-phrase + 0.10·rare-term + 0.05·multi-query-agreement
```

* `similarity` uses **raw cosine** (or scaled BM25 for keyword-only hits) — deliberately **not** min-max-normalized RRF scores, which always inflate the top hit to 1.0 and make relevance floors meaningless. This is what enables honest refusal (below).
* The interface is ready for a cross-encoder drop-in later.

Tests: `test_agents.py::test_reranker_*`.

## 6. Context compression

`ContextCompressionAgent`:

* Near-duplicate removal (5-shingle Jaccard ≥ 0.80).
* **Absolute relevance floor** (`MIN_RELEVANCE_SCORE=0.30`): chunks below the floor never become evidence — *including top-ranked ones*. An unanswerable question therefore yields zero evidence → the generator returns an honest refusal **without an LLM call**. (Exception: when the Metadata Agent actively narrowed scope with matched filters, the top-2 are kept.)
* Sentence-level selection keeps query-relevant sentences within a per-evidence cap, then a global budget (`MAX_EVIDENCE_CHARS=6000`), highest-scoring evidence first.
* **Citation metadata is never dropped**: every evidence block keeps chunk id, document id/title and page range, and is labeled `E1..En` for the generator.

Tests: `test_agents.py::test_compressor_*`, refusal behavior in `test_orchestrator.py`.

## 7. Conversation-aware retrieval & memory

`app/memory/conversation_memory.py`:

* Bounded context: rolling summary (`Conversation.summary`, refreshed every ~10 messages via LLM when available, extractive otherwise) + last N messages within a character budget. The full history is **never** sent to the model.
* The generator prompt embeds `<CONVERSATION_SUMMARY>` and `<RECENT_CONVERSATION>` so follow-up questions (“And the carry-over limit?”) resolve against prior turns.

## 8. Grounded generation, verification, citations

* Strict grounding system prompt + `<EVIDENCE>` delimiters + explicit instruction to ignore directives embedded in documents (prompt-injection defense).
* **Verification Agent:** claim splitting → lexical entailment against evidence sentences → contradiction detection (negation mismatch) → confidence & coverage; optional LLM judge (`VERIFICATION_USE_LLM`, never with the mock provider — no fake judging).
* **Bounded retry:** verification failure ⇒ at most `MAX_REGENERATION_ATTEMPTS=1` regeneration with a stricter prompt ⇒ if still unverified, the answer is replaced by a safe insufficient-evidence response (marked in the trace). No infinite loops.
* **Citation Validation Agent:** every `[E#]` marker must map to an evidence block whose chunk was *actually retrieved* and is *still authorized*; invalid markers are stripped from the text; final citations carry document/title/pages/chunk-id/quote.

Tests: `test_agents.py`, `test_orchestrator.py::test_verification_failure_triggers_regeneration_then_safe_fallback`.

## 9. Measured quality — the evaluation framework

`python -m app.evaluation.run` (Module 7) executes the real pipeline over a labeled corpus and reports, per run:

* **Retrieval:** Precision@{3,5,10}, Recall@{3,5,10}, MRR, nDCG@{3,5,10} against chunk-level ground truth derived from human labels (relevant file + evidence keywords).
* **Generation:** faithfulness (boilerplate-filtered lexical coverage), answer relevance, citation accuracy (citations ⊆ retrieved chunks), groundedness (same entailment logic as the runtime verifier).
* **System:** per-stage latencies, token usage, chunk counts, verification failures, regenerations.
* **Refusal handling:** the unanswerable golden query must return insufficient-evidence.

Example offline run (mock LLM + local embeddings, this repo’s CI environment):

```
recall@5 = 1.0   mrr = 1.0   ndcg@5 = 1.0   citation_accuracy = 1.0
faithfulness = 1.0   groundedness = 1.0   refusal 1/1 correct   overall 1.0
```

(Scores on a 4-document labeled corpus with lexical embeddings saturate easily — with your real documents and Gemini embeddings, expect meaningful spread. The framework reports whatever it measures; it never fabricates.)

Results persist to `evaluation_results` + JSON artifacts and surface in the UI (Settings → RAG evaluation) and API (`/api/evaluation/results`).

## 10. Performance work (measured, not guessed)

* Index warm-up at startup (BM25 built once; FAISS loaded from disk).
* One batched embedding call per ingestion and per multi-query retrieval (≤3 variants).
* Local reranking by default — zero LLM cost for ranking (`RERANKER_USE_LLM=false`).
* Over-fetch-then-filter vector search keeps authorization enforcement O(results), not O(corpus).
* Per-stage latency percentiles exposed via `/api/analytics/performance` and `/api/metrics` — optimize from data.
