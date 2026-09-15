# KnowledgeIQ — Enterprise Knowledge Intelligence Platform

**Multi-Agent RAG System** that converts unstructured enterprise documents (PDF / DOCX / TXT / scans) into an intelligent, cited, verified knowledge system.

> **Honest status note:** this repository was built greenfield inside a sandboxed workspace (the original VS Code workspace was not accessible there). See [`PROJECT_AUDIT.md`](PROJECT_AUDIT.md) for the audit record and design decisions.

---

## What it does

1. **Upload** enterprise documents (PDF, DOCX, TXT, MD, PNG/JPG/TIFF scans).
2. **Process** them: validation → parsing → OCR (when needed) → metadata & entity extraction → page-aware chunking → embeddings → FAISS + BM25 indexes.
3. **Ask questions** in natural language. An **8-agent pipeline** plans, retrieves (hybrid), filters by metadata, reranks, compresses context, generates a grounded answer, **verifies** it against evidence, and **validates every citation** — with page-level sources and a live agent execution trace.
4. **Search** directly (semantic / keyword / hybrid) with metadata filters.
5. **Evaluate** RAG quality repeatably (`python -m app.evaluation.run`) against a labeled golden dataset — real computed metrics, never fabricated.
6. **Monitor** via analytics, reports, structured logs, request IDs and `/api/metrics`.

## Architecture at a glance

```
React (Vite, Tailwind, Recharts, Framer Motion)
        │  /api (Vite proxy → 127.0.0.1:8001)
        ▼
FastAPI backend ── JWT auth ── RBAC ── rate limiting ── audit log
        │
        ▼
Agent Orchestrator (one pipeline, one framework)
  Planner → (Retriever ∥ Metadata) → Reranker → Compressor
          → Answer Generator → Verifier → Citation Validator
        │                              │
        ▼                              ▼
 FAISS vectors + BM25            SQLite (dev) / PostgreSQL (prod)
 (gemini-embedding-001 or        documents · chunks · conversations
  offline local fallback)        messages · audit · evaluations
```

Full details and diagrams: [`ARCHITECTURE.md`](ARCHITECTURE.md) · RAG specifics: [`RAG_IMPROVEMENTS.md`](RAG_IMPROVEMENTS.md) · Deployment: [`DEPLOYMENT.md`](DEPLOYMENT.md)

---

## Quick start (development)

**Ports are fixed by convention:** frontend `http://localhost:5173`, backend `http://127.0.0.1:8001`, API docs `http://127.0.0.1:8001/docs`. The Vite proxy points at `http://127.0.0.1:8001`.

### 1. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # no Gemini key? The app runs in clearly-reported offline mock mode
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev                     # → http://localhost:5173
```

### 3. Use it

1. Register (the **first account becomes admin**).
2. Upload documents → watch live processing progress (parsing → OCR → metadata → chunking → embedding → indexing).
3. Go to **Ask AI** → ask a question → watch the agent trace, streamed answer, verification badge and page-level citations.

### Optional: real Gemini AI

Set in `backend/.env` and restart:

```env
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-2.5-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-001   # NOT the deprecated text-embedding-004
```

Without a key the platform **never fakes it**: the UI shows “AI: offline mock mode”, answers are extractive (quoted from evidence), and embeddings are lexical hashes. `/api/health` and the Settings page always report the active providers.

### Optional: OCR for scans

```bash
# Debian/Ubuntu
sudo apt-get install tesseract-ocr poppler-utils
pip install pdf2image
```

The Docker images already include tesseract + poppler. Without them, scanned uploads fail with an explicit, actionable error (never silently).

---

## Tests

```bash
cd backend
pytest            # 121 tests — auth, upload, OCR degradation, chunking, embeddings,
                  # BM25/hybrid retrieval, all 8 agents, orchestration, verification,
                  # citation validation, streaming, security, authorization, error
                  # classification, and a full evaluation-framework run.
```

No network access or API keys are needed — tests run against the offline providers with isolated per-test databases.

## Evaluation (Module 7)

```bash
cd backend
python -m app.evaluation.run
```

Ingests a labeled 4-document enterprise corpus, runs every golden query through the **real** pipeline, and reports Precision@K, Recall@K, MRR, nDCG, faithfulness, answer relevance, citation accuracy, groundedness, latencies, token usage and refusal handling. Results are persisted (JSON + `evaluation_results` table) and visible under **Settings → RAG evaluation** (admins can trigger runs from the UI or `POST /api/evaluation/run`).

## Production (Docker Compose)

```bash
cp .env.example .env    # set SECRET_KEY, POSTGRES_PASSWORD, GEMINI_API_KEY
docker compose up --build
# → http://localhost:8080  (nginx serves the SPA and proxies /api, SSE included)
```

Production refuses to boot on SQLite or with the default `SECRET_KEY`. Details: [`DEPLOYMENT.md`](DEPLOYMENT.md).

---

## API surface

| Prefix | Purpose |
|---|---|
| `/api/auth/*` | register · login · refresh · me · logout |
| `/api/documents/*` | upload · list · status (polling) · content preview · reprocess · delete |
| `/api/search` | hybrid / semantic / keyword search with metadata filters |
| `/api/chat/ask` · `/api/chat/ask/stream` | multi-agent Q&A (JSON + SSE) · `/api/chat/mode` |
| `/api/conversations/*` | history |
| `/api/agents/*` | agent registry · persisted execution traces |
| `/api/analytics/*` · `/api/reports/*` | overview · performance · top documents · summary · CSV export |
| `/api/evaluation/*` | trigger runs · results |
| `/api/health` · `/api/ready` · `/api/metrics` | liveness · readiness · counters |

Interactive docs: `http://127.0.0.1:8001/docs`.

## Repository layout

```
backend/
  app/
    agents/        base · planner · retriever · metadata · reranker · compressor
                   answer_generator · verifier · citation_validator · orchestrator · schemas
    api/           auth · documents · search · chat · conversations · agents
                   analytics · reports · evaluation · system
    core/          security (JWT/bcrypt/sanitization) · errors (AI error classification)
                   middleware (request-id, headers, rate limit, metrics) · deps · logging
    evaluation/    metrics · dataset · run (CLI)
    memory/        conversation_memory (bounded context + rolling summary)
    models/        User · Document · DocumentChunk · Conversation · Message · AuditLog · EvaluationResult
    rag/           bm25 · hybrid (RRF) · query_rewrite
    services/      file_validation · parsing · ocr · chunking · metadata_extraction
                   entity_extraction · embeddings · vector_store (FAISS) · ingestion · jobs · llm
  data/evaluation/ golden_dataset.json + labeled corpus (synthetic enterprise docs)
  tests/           121 pytest tests
frontend/
  src/pages/       Login · Register · Dashboard · Documents · Search · AskAI
                   Analytics · Reports · Settings · Profile
  src/components/  Layout · AgentTrace · CitationList · ProtectedRoute · ui primitives
nginx/             standalone reverse-proxy config (TLS termination variant)
docs/              diagrams
```

## Security highlights

JWT access + refresh (type-confusion safe) · bcrypt · RBAC (admin/user) · per-user document isolation (enforced at retrieval time, 404s don't leak existence) · magic-byte upload validation · filename sanitization + UUID storage names · path-traversal guards · sliding-window rate limiting (stricter on auth) · security headers · CORS allow-list · prompt-injection defenses (evidence delimiters + instruction-ignoring system prompt) · redaction of secrets in logs/errors · audit log for auth, uploads, deletions, asks · SQL injection-safe ORM usage. Details: [`ARCHITECTURE.md`](ARCHITECTURE.md#security).

## Known limitations (honest list)

See [`TODO.md`](TODO.md) — includes: lexical (non-semantic) offline embeddings, single-node FAISS index rebuilt on delete, LLM-judge metrics skipped without an API key, and no Alembic migrations yet (schema via `create_all`).
