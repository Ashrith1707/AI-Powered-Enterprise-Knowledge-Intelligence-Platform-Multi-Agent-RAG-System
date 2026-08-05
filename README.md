# AI-Powered Enterprise Knowledge Intelligence Platform

Multi-Agent AI + Retrieval-Augmented Generation (RAG) over enterprise documents.
FastAPI · PostgreSQL/SQLite · SQLAlchemy · LangChain · Gemini · FAISS · PyMuPDF · Tesseract · React + Vite.

---

## 1. Quick start

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # then add your GEMINI_API_KEY
uvicorn app.main:app --reload   # http://localhost:8000/docs
```
Runs on SQLite out of the box; set `DATABASE_URL` in `.env` for PostgreSQL.
Without a `GEMINI_API_KEY` the platform still works (upload, parse, OCR, search,
analytics, reports) using a local fallback embedder; only `/api/ask` needs Gemini.

### Frontend
```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173 (proxies /api to :8000)
```

### Tests
```bash
cd backend
pytest
```

---

## 2. The three phases

| Phase | Layer | Modules |
|---|---|---|
| 1 | Document Intelligence | upload → validate → store → parse (PyMuPDF) → OCR (Tesseract) → clean → pages → metadata → classify → persist |
| 2 | Multi-Agent AI | Coordinator, Registry, Task Planner, Task Queue, Workflow Engine, Shared Memory, 7 specialized agents |
| 3 | Knowledge Intelligence | chunking → Gemini embeddings → FAISS → retriever → reranker → prompt builder → Gemini LLM → citation engine |

Pipeline output: `Raw document → structured pages → metadata → DB → chunks → vectors → cited answers`.

---

## 3. Project structure

```
backend/
├── requirements.txt / .env.example
├── app/
│   ├── main.py                  # FastAPI app: routers, CORS, error mapping, startup
│   ├── core/
│   │   ├── config.py            # all settings from .env (single source of truth)
│   │   ├── database.py          # engine, SessionLocal, Base, get_db dependency
│   │   ├── logging_config.py    # structured logging
│   │   └── exceptions.py        # domain errors -> HTTP codes
│   ├── models/                  # SQLAlchemy tables (see §4)
│   ├── schemas/                 # Pydantic request/response contracts
│   ├── api/routes/              # thin HTTP layer: documents, search, analytics,
│   │                            #   reports, agents, health
│   ├── repositories/            # ALL database access (services never touch SQL)
│   ├── services/                # Phase 1 capabilities: storage, parsing, ocr,
│   │                            #   text_cleaning, metadata, classification,
│   │                            #   pipeline, analytics, report
│   ├── agents/                  # Phase 2: base_agent, registry, task_queue,
│   │                            #   memory, workflow, coordinator, specialized
│   └── rag/                     # Phase 3: chunker, embeddings, vector_store,
│                                #   retriever, reranker, prompt_builder,
│                                #   citation_engine, llm_client, rag_service
└── tests/                       # pytest: health, upload validation, services, agents

frontend/src/
├── api/client.js                # single fetch wrapper for every endpoint
├── App.jsx                      # sidebar layout + routes
└── pages/                       # Dashboard, Documents, Ask AI, Search, Reports
```

**Dependency direction (Clean Architecture):**

```
main.py → api/routes → services / agents / rag → repositories → models → database
                         (schemas define the contracts at the API boundary)
```
Inner layers never import outer layers. Agents wrap services (orchestration vs
capability). The FAISS index and Gemini clients are isolated behind `rag/` so the
vector store or LLM vendor can be swapped without touching business logic.

---

## 4. Database schema

```
users 1──* documents 1──* pages
                │ 1──1 document_metadata
                │ 1──* chunks 1──1 embeddings (FAISS id bookkeeping)
reports, search_logs, audit_logs  (activity/observability tables)
```

| Table | Purpose |
|---|---|
| users | identity + role (admin/analyst/viewer) |
| documents | file, checksum (dedupe), status lifecycle `uploaded→parsing→parsed→indexed/failed`, category |
| pages | per-page text, OCR flag, word count |
| document_metadata | title, keywords, entities (dates/emails/amounts), summary |
| chunks | retrieval units with page number for citations |
| embeddings | chunk ↔ FAISS-id mapping + model/dimension |
| reports | generated PDF/DOCX artifacts |
| search_logs | every query, latency, evaluation score → dashboard |
| audit_logs | immutable action trail |

---

## 5. API surface

| Method | Endpoint | Purpose |
|---|---|---|
| POST | /api/documents/upload | multipart upload; validates type/size/duplicate; pipeline runs in background |
| GET | /api/documents | list documents with status |
| GET | /api/documents/{id} | detail + metadata |
| GET | /api/documents/{id}/pages | extracted page texts |
| DELETE | /api/documents/{id} | removes rows, vectors and the stored file |
| POST | /api/search | semantic search `{query, top_k}` |
| POST | /api/ask | RAG Q&A via Coordinator Agent; returns answer, citations, confidence, agent trace |
| GET | /api/analytics/dashboard | aggregated platform stats |
| POST | /api/reports | generate analytics / summary / qa report (pdf/docx) |
| GET | /api/reports, /api/reports/{id}/download | list + download |
| GET | /api/agents | registry introspection |
| GET | /api/health | liveness + LLM configured flag |

Errors: domain exceptions map to 400 (validation), 404 (not found),
422 (processing), 503 (LLM not configured); FastAPI/Pydantic handles schema
validation automatically. Interactive docs at `/docs`.

---

## 6. Multi-agent design (Phase 2)

**Why not one LLM call?** A single prompt can't parse files, OCR pages, query SQL,
build vector indexes, score its own answers and render PDFs. Each of those is a
different tool with different failure modes. Agents give: separation of concerns,
independent testability, per-step monitoring/tracing, retryable failure isolation,
and horizontal extensibility (add an agent = register it, nothing else changes).

| Agent | Capabilities | Wraps |
|---|---|---|
| Coordinator | plan → dispatch → aggregate | registry + workflow engine |
| Document | process_document, get_document | PipelineService |
| Metadata | extract_metadata | MetadataService |
| Search | semantic_search, rag_answer | RAGService |
| Analytics | dashboard_stats | AnalyticsService |
| Report | generate_report | ReportService |
| Evaluation | evaluate_answer (groundedness, refusal, citation count) | — |
| Notification | notify (audit log; extensible to email/Slack) | ActivityRepository |

**Communication:** blackboard pattern — each step writes its result to shared
`WorkflowMemory`; later steps read it via `task.context`. The engine records a
human-readable trace (surfaced in the UI under "agent execution trace").

Example plan for intent `ask`:
`rag_answer → evaluate_answer → notify` — the evaluation score is logged with the
search entry, giving you answer-quality analytics over time.

---

## 7. RAG design (Phase 3)

```
Question → embed → FAISS top-8 → lexical rerank to top-4
        → numbered context blocks + citation rules → Gemini
        → [n] markers mapped back to (document, page, snippet)
        → cited answer + confidence
```

Design decisions worth defending in a review:
- **Page-aware chunking** (RecursiveCharacterTextSplitter, 1000/150 overlap):
  every chunk keeps its page → citations point to exact pages.
- **FAISS IndexIDMap over IndexFlatIP** with normalized vectors: inner product ==
  cosine; FAISS ids == chunk DB ids, so hits map straight to citations.
- **Grounding prompt** forces refusal when context is insufficient → hallucination
  control, verified by the Evaluation Agent.
- **Reranker** blends dense score with query-term overlap (cheap cross-encoder
  stand-in) — dense-only retrieval can score topically-similar-but-irrelevant
  chunks highly.
- **Fallback embedder** keeps the whole demo alive without an API key (quality
  clearly reduced and logged).

---

## 8. Review talking points

- **Problem:** enterprise knowledge is trapped in unstructured PDFs/scans; keyword
  search misses meaning; answers lack provenance.
- **Solution:** end-to-end platform: OCR + parsing → knowledge base → multi-agent
  RAG with page-level citations, analytics and auto-generated reports.
- **Innovation:** agent-orchestrated RAG with self-evaluation and full execution
  tracing; citation engine that only surfaces sources the model actually used.
- **Applications:** legal contract review, financial audit trails, HR policy
  assistants, technical documentation search.
- **Future scope:** authentication/SSO, Celery + Redis task queue, pgvector,
  cross-encoder reranker, multilingual OCR, feedback-driven retrieval tuning.
