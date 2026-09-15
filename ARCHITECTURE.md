# KnowledgeIQ — Architecture

This document describes the system as actually implemented in this repository, with the seven required diagrams.

---

## 1. High-level architecture

```
                              USER
                               │
                               ▼
                     React Frontend (Vite :5173)
        Login · Dashboard · Documents · Search · Ask AI · Analytics · Reports
                               │  /api  (dev: Vite proxy → 127.0.0.1:8001)
                               ▼                    (prod: Nginx :80/:8080)
                     FastAPI Backend (:8001)
                               │
             ┌─────────────────┼──────────────────────┐
             ▼                 ▼                      ▼
      Authentication     Middleware stack        API Gateway
      JWT access/refresh  request-id · headers    /api/auth /api/documents
      bcrypt · RBAC       rate limit · CORS       /api/search /api/chat
             │            audit · metrics         /api/agents /api/evaluation
             └─────────────────┼──────────────────────┘
                               ▼
                  AI Orchestration Layer (ONE orchestrator)
                               │
                               ▼
                       8-Agent RAG Pipeline
                               │
         ┌─────────────────────┼─────────────────────┐
         ▼                     ▼                     ▼
   Embeddings            Vector + Keyword        Relational DB
   gemini-embedding-001   FAISS (IndexFlatIP)    SQLite (dev)
   or local fallback      BM25 (in-memory)       PostgreSQL (prod)
         │                     │                     │
         └─────────────────────┴─────────────────────┘
                               │
                               ▼
                 Gemini LLM (google-genai SDK)
                 or offline mock provider (clearly reported)
```

**Key principle:** there is exactly one agent framework (`app/agents/`) and one orchestration layer (`app/agents/orchestrator.py`). Services (parsing, embeddings, vector store, BM25) are shared by the agents, the search endpoint, ingestion and evaluation — no duplicated RAG pipelines.

---

## 2. Document ingestion flow

```
PDF / DOCX / TXT / MD / PNG / JPG / TIFF
        │  POST /api/documents/upload  (auth required)
        ▼
┌ File Validation ─────────────────────────────┐
│ extension allow-list · size limit (25 MB)    │
│ magic-byte sniffing (%PDF-, PK…, ‰PNG, …)    │
│ filename sanitization → UUID stored name     │
└──────────────┬───────────────────────────────┘
               ▼
   Background Job (in-process thread pool; Document row = source of truth)
               │
               ▼
        Parsing (pypdf / python-docx / plain)          status: processing · 10%
               │
               ├─ embedded text present ──────────────┐
               │                                      │
               ▼ (< 20 chars/page ⇒ scanned)          │
             OCR (tesseract + poppler when available) │  status: ocr · 25%
               │   honest failure otherwise           │
               ▼                                      ▼
        Metadata extraction                    status: metadata · 45%
        (title, author, department, category, dates, version, tags)
               ▼
        Entity extraction (persons, orgs, emails, money, %, dates, ref codes)
               ▼
        Page-aware chunking (recursive, overlap, page_start/page_end)   · 55%
               ▼
        Embeddings (batched; gemini-embedding-001 or local hash)        · 70%
               ▼
   ┌───────────┴────────────┐
   ▼                        ▼
 FAISS index            PostgreSQL/SQLite
 (+ id map, persisted)  document_chunks rows        status: indexing · 88%
 BM25 upsert            metadata_json · entities_json
   └───────────┬────────────┘
               ▼
        status: completed · 100%   (or failed + actionable error message)
```

Progress is pollable at `GET /api/documents/{id}/status` (stage + percent + error).

---

## 3. RAG query pipeline

```
User query
   ▼
Planner Agent ── intent · strategy · dynamic top-K · sub-queries · metadata hints
   ▼
   ├──────────────────────────┬───────────────────────────┐
   ▼                          ▼                           │
Retriever Agent           Metadata Agent                  │  (parallel)
 multi-query embedding     authorization scope            │
 FAISS cosine search       department/category/author/    │
 BM25 keyword search       date/tags/document-id filters  │
 RRF fusion per variant    honest fallback when filters   │
 cross-variant dedupe      match nothing                  │
   └────────────┬─────────────┘                           │
                ▼  merge (metadata-filtered candidates) ◄─┘
        Reranker Agent — absolute relevance composite
        (cosine · keyword coverage · phrase · rare-term · agreement)
                ▼
        Context Compression Agent
        (near-duplicate removal · relevance floor · sentence selection
         · char budget · citation metadata always preserved → E1..En)
                ▼
        Answer Generator Agent  (Gemini or offline extractive mock)
        grounded system prompt · <EVIDENCE> delimiters · memory context
                ▼
        Verification Agent — claim-level entailment, contradictions,
        confidence; failure ⇒ ONE bounded regeneration ⇒ safe fallback
                ▼
        Citation Validation Agent — every [E#] must map to a really
        retrieved, still-authorized chunk; invalid markers removed
                ▼
        FinalResponse { answer · citations · verification · trace · metrics }
        persisted: messages (with citations/trace/metrics JSON) · audit log
```

**Retrieval strategy matrix** (chosen by the Planner):

| Strategy | Vector | BM25 | When |
|---|---|---|---|
| `hybrid` (default) | ✓ | ✓ | knowledge questions |
| `vector` | ✓ | — | semantic/paraphrased queries |
| `keyword` | — | ✓ | exact codes/IDs, quoted phrases |
| `none` | — | — | conversational / analytics intents |

**Authorization is enforced twice:** the Retriever searches only within the user's authorized chunk-id set, and the Citation Validator re-checks document authorization before shipping citations.

---

## 4. Multi-agent workflow (execution view)

```
            ┌────────────────────────────────────────────────────┐
            │              AgentOrchestrator (async)             │
            │  PipelineContext · AgentTrace · retry policy       │
            │  per-agent timeouts · failure recovery · metrics   │
            └────────────────────────────────────────────────────┘
                 │
   [1] PlannerAgent          in : query                    out: Plan
                 │
        ┌────────┴─────────┐   asyncio.gather (parallel)
        ▼                  ▼
 [2] RetrieverAgent   [3] MetadataAgent
   in : Plan, auth      in : Plan.filters, user scope
   out: candidates      out: MetadataDecision
        └────────┬─────────┘   merge + metadata filter
                 ▼
 [4] RerankerAgent           in : candidates        out: ranked top-N
                 ▼
 [5] ContextCompressionAgent in : ranked            out: Evidence[E1..En]
                 ▼
 [6] AnswerGeneratorAgent    in : evidence, memory  out: GeneratedAnswer
                 ▼                                  (streaming capable)
 [7] VerificationAgent       in : answer, evidence  out: VerificationResult
                 │            fail ⇒ regenerate once (bounded) ⇒ safe fallback
                 ▼
 [8] CitationValidationAgent in : answer, evidence  out: cleaned answer +
                                                      validated Citations
```

Every agent extends `BaseAgent` (template method): status lifecycle (`pending → running → completed|failed|skipped`), wall-clock timing, timeout guard (`asyncio.wait_for`), classified error capture, structured `AGENT_EVENT` logs, and a **safe trace summary** (never raw prompts or hidden chain-of-thought). The trace is streamed live over SSE and persisted per message (`agent_trace_json`).

---

## 5. Authentication flow

```
Client                         Backend
  │ POST /api/auth/register      │  bcrypt hash · first user ⇒ admin
  │ POST /api/auth/login         │  verify bcrypt · audit log
  │ ◄── access (30 min) + refresh (7 days) JWTs ──┐
  │                                │              │ type claim: "access" | "refresh"
  │ GET /api/** (Bearer access)    │  decode+verify signature, expiry, TYPE
  │   401 expired ──────────────►  │ POST /api/auth/refresh (refresh token)
  │ ◄── new token pair ──────────  │  (refresh tokens rejected as access tokens)
  │                                │
  │ RBAC: role claim + DB check    │  admin: all docs/users · user: own resources only
  │ Rate limits: auth endpoints    │  10/min/IP · general API 120/min/IP (sliding window)
```

The frontend stores tokens in `localStorage`, attaches `Authorization: Bearer …`, and on 401 performs exactly one silent refresh-and-retry (`src/api/client.js`).

---

## 6. Database / ER architecture

```
users 1───* documents 1───* document_chunks
  │            │                 (document_id, chunk_index UNIQUE;
  │            │                  page_start/page_end for citations;
  │            │                  vector_position → FAISS row)
  │            └── metadata_json  {title, author, department, category,
  │                entities_json   dates, version, tags, …}
  │                               {persons, organizations, emails, money, …}
  │
  ├───* conversations 1───* messages
  │        (summary = rolling memory)   (role, content,
  │                                      citations_json,
  │                                      agent_trace_json,
  │                                      metrics_json)
  │
  └───* audit_logs   (action, resource, outcome, ip, user_agent, detail_json)

evaluation_results   (run_id UNIQUE, dataset, retrieval/generation/system
                      metric JSON blobs, per-query detail, overall_score)
```

* SQLite (dev) / PostgreSQL (prod) via `DATABASE_URL`; pooling + pre-ping for Postgres.
* Indexes: `documents.user_id`, `documents.status`, `document_chunks.document_id`, `messages.conversation_id`, `audit_logs.action/created_at`, `conversations.user_id/updated_at`.
* Schema is created with `create_all` (no destructive migrations yet — see TODO).

---

## 7. Deployment architecture

**Development**

```
Browser → Vite dev server :5173 ── proxy /api → uvicorn :8001 → SQLite file
                                        FAISS index + uploads under backend/data/
```

**Production (docker compose)**

```
Internet → :8080 nginx (frontend container)
              ├── /            static SPA (vite build output, gzip, asset caching)
              ├── /api/*       proxy_pass → backend:8001
              │                (SSE: proxy_buffering off, 300s read timeout)
              ▼
        backend (uvicorn ×2 workers, non-root user, tesseract+poppler inside)
              ├── DATABASE_URL → postgres:5432 (postgresql+psycopg2)
              ├── volumes: uploads / vectors / evaluation results
              └── healthcheck: GET /api/health
        db (postgres:16-alpine, pg_isready healthcheck, pgdata volume)
```

Startup guards: with `APP_ENV=production`, the backend logs configuration problems for SQLite URLs, default `SECRET_KEY`, or missing `GEMINI_API_KEY`, and compose **requires** `SECRET_KEY` (`:?` interpolation fails fast).

Alternative bare-metal layout (TLS-terminating host nginx): see `nginx/nginx.conf`.

---

## Error handling philosophy

| Class | Example | Client sees |
|---|---|---|
| Auth | 401 invalid/expired token | `authentication_failed` + safe message |
| Access | other user's document | **404** (existence never leaked) |
| Upload | bad type/size/magic bytes | `upload_rejected` + reason |
| AI 401 | invalid Gemini key | `ai_provider_error` / `invalid_api_key` |
| AI 403 | key lacks model access | `permission_denied` |
| AI 404 | deprecated/unknown model (e.g. text-embedding-004) | `model_not_found` **+ actionable guidance** |
| AI 429 | quota | `quota_exceeded` (retryable) |
| AI 5xx | provider down | `provider_error` (retryable) |
| Network/timeout | DNS, refused, deadline | `network_error` / `timeout` (retryable) |
| Evidence | nothing relevant retrieved | HTTP 200 + honest insufficient-evidence answer |

The historical bug — *"The Gemini API key is INVALID"* shown for a **model 404** — is fixed at the root: `app/core/errors.py::classify_ai_error` distinguishes every class above, and the frontend renders `error.details.ai_error_code` with the provider message. A CI job additionally greps the repo to keep `text-embedding-004` and the legacy `google.generativeai` SDK out forever.

## Observability

* Structured logs: `AGENT_EVENT agent=… status=… duration_ms=… request_id=… user_id=…`
* `X-Request-ID` per request (client-provided or generated), echoed in responses and logs.
* In-process counters + latency percentiles at `/api/metrics`; per-stage latencies persisted with every answer (`metrics_json`) and aggregated in `/api/analytics/performance`.
* Redaction filter scrubs API keys/tokens/passwords from every log line and error payload.
