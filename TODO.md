# TODO.md — honest remaining work

Everything below is a genuine limitation or planned improvement. Nothing here is required for the acceptance criteria already met (see PROJECT_AUDIT.md §6), but a reviewer should know about it.

## High priority

- [ ] **Verify with a real GEMINI_API_KEY.** The sandbox had no key, so Gemini paths are unit-tested against the SDK surface with error injection, not against the live API. On first run with a key: confirm `gemini-2.5-flash` + `gemini-embedding-001` respond for your tier; the app reports the active providers in `/api/health`.
- [ ] **Re-indexing after provider/dimension change.** Switching `EMBEDDING_PROVIDER` or `EMBEDDING_DIMENSIONS` starts a fresh FAISS index (detected + logged), but existing documents must be reprocessed manually (`POST /api/documents/{id}/reprocess`). Add a one-click “re-index all” admin endpoint/UI.
- [ ] **Alembic migrations.** Schema is created with `create_all` (fine for greenfield); before evolving models in production, add Alembic with an initial baseline migration.

## Medium priority

- [ ] **Docker build verification.** Dockerfiles/compose are complete and conventional but no docker daemon existed in the sandbox to build them. Run `docker compose up --build` once and fix anything environment-specific.
- [ ] **Vector delete at scale.** FAISS removal rebuilds the flat index (fine for ≤10⁵ chunks). For larger corpora switch to `IndexIDMap` + tombstones or an HNSW/IVF index and batch rebuilds.
- [ ] **Cross-encoder reranker.** `RerankerStrategy` interface is ready; add a sentence-transformers cross-encoder implementation for higher-quality reranking when CPU/GPU budget allows.
- [ ] **Refresh-token revocation list.** Logout is audited but stateless; add a `jti` denylist (DB or Redis) for hard revocation before expiry.
- [ ] **Multi-language OCR.** Only the default tesseract language pack ships in the image; add `tesseract-ocr-<lang>` packages and a per-document language hint.

## Low priority / nice-to-have

- [ ] **Semantic dedupe at ingestion** (currently dedupe happens at query time in the compressor).
- [ ] **Per-department access groups** (currently: owner + admin; RBAC roles exist but document ACLs are per-user).
- [ ] **Evaluation dataset growth** — add real (anonymized) enterprise Q&A pairs; the current golden set is a synthetic 4-doc corpus.
- [ ] **Frontend bundle splitting** — 757 kB JS (219 kB gzip) single chunk; add route-level `React.lazy` code splitting.
- [ ] **WebSocket option for chat** (SSE works well; WS only needed for bidirectional mid-answer interaction).
- [ ] **Prometheus scrape endpoint** in strict exposition format (current `/api/metrics` returns JSON + text lines).

## Explicitly rejected (with reasons)

- **Redis / Celery** — no measured bottleneck; the in-process job registry documents the swap point. Adding a queue “for appearance” violates the project rules.
- **LangChain dependency** — the RAG primitives (chunking, hybrid retrieval, RRF, reranking, compression, memory) are implemented directly; they are small, typed, tested, and avoid a heavy abstraction layer whose defaults we would fight anyway. The stack list allowed LangChain “where appropriate” — it wasn’t.
- **Replacing FAISS with pgvector** — FAISS is in the required stack and persists to disk; pgvector could consolidate storage later but adds a migration for no functional gain today.
