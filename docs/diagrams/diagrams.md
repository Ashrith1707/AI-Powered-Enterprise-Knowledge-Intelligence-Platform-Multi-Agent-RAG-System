# KnowledgeIQ — Diagram sources (Mermaid)

Renderable sources for the seven architecture diagrams (ASCII versions live in `ARCHITECTURE.md`).

## 1. High-level architecture

```mermaid
flowchart TB
    U[User] --> FE[React Frontend :5173]
    FE -->|/api proxy| BE[FastAPI Backend :8001]
    BE --> AUTH[JWT Auth + RBAC]
    BE --> MW[Middleware: request-id · headers · rate-limit · audit]
    AUTH --> ORCH[Agent Orchestrator]
    MW --> ORCH
    ORCH --> AGENTS[8-Agent RAG Pipeline]
    AGENTS --> EMB[Embeddings<br/>gemini-embedding-001 / local fallback]
    AGENTS --> VS[FAISS Vector Store]
    AGENTS --> BM[BM25 Keyword Index]
    AGENTS --> LLM[Gemini LLM / offline mock]
    BE --> DB[(SQLite dev / PostgreSQL prod)]
```

## 2. Document ingestion

```mermaid
flowchart TB
    UP[Upload] --> VAL[Validation: type · size · magic bytes · filename sanitize]
    VAL --> PARSE[Parse: pypdf / python-docx / text]
    PARSE -->|scanned?| OCR[OCR: tesseract + poppler]
    PARSE -->|embedded text| META
    OCR --> META[Metadata Extraction]
    META --> ENT[Entity Extraction]
    ENT --> CH[Page-aware Chunking]
    CH --> EMB[Embedding Generation]
    EMB --> FAISS[(FAISS Index)]
    EMB --> BM25[(BM25 Index)]
    CH --> DB[(document_chunks + metadata JSON)]
    FAISS --> READY[Queryable]
    BM25 --> READY
    DB --> READY
```

## 3. Multi-agent workflow

```mermaid
flowchart TB
    Q[User Query] --> P[1 · Planner Agent]
    P -->|knowledge_retrieval| R[2 · Retriever Agent]
    P --> M[3 · Metadata Agent]
    R --> MG{merge + metadata filter}
    M --> MG
    MG --> RR[4 · Reranker Agent]
    RR --> CC[5 · Context Compression Agent]
    CC --> AG[6 · Answer Generator Agent]
    AG --> V{7 · Verification Agent}
    V -->|fail ≤1 retry| AG
    V -->|fail exhausted| SAFE[Safe insufficient-evidence answer]
    V -->|pass| CV[8 · Citation Validation Agent]
    SAFE --> CV
    CV --> FR[FinalResponse: answer · citations · trace · metrics]
    P -->|conversational / analytics| CANNED[System answer, retrieval skipped]
    CANNED --> FR
```

## 4. RAG data flow (query)

```mermaid
flowchart LR
    A[Query] --> B[Query Analysis<br/>variants · keywords · hints]
    B --> C[Authorization Scope<br/>user's chunk ids]
    C --> D[FAISS cosine search]
    C --> E[BM25 keyword search]
    D --> F[RRF Fusion]
    E --> F
    F --> G[Absolute Relevance Rerank]
    G --> H[Dedupe + Compress → E1..En]
    H --> I[Grounded Generation + citations]
    I --> J[Verification]
    J --> K[Citation Validation]
    K --> L[Verified Answer + Sources + Trace]
```

## 5. Authentication flow

```mermaid
sequenceDiagram
    participant C as Client
    participant B as Backend
    C->>B: POST /api/auth/register
    B-->>C: 201 (first user ⇒ admin)
    C->>B: POST /api/auth/login
    B-->>C: access token (30m) + refresh token (7d)
    C->>B: GET /api/** (Bearer access)
    B-->>C: 200
    C->>B: GET /api/** (expired access)
    B-->>C: 401 authentication_failed
    C->>B: POST /api/auth/refresh (refresh token)
    B-->>C: new token pair
    C->>B: retry original request
    B-->>C: 200
```

## 6. Database / ER

```mermaid
erDiagram
    users ||--o{ documents : owns
    users ||--o{ conversations : has
    users ||--o{ audit_logs : generates
    documents ||--o{ document_chunks : contains
    conversations ||--o{ messages : contains
    users {
        int id PK
        string email UK
        string hashed_password
        enum role
        bool is_active
    }
    documents {
        int id PK
        int user_id FK
        string filename
        string stored_filename
        enum status
        json metadata_json
        json entities_json
        int page_count
        int processing_progress
    }
    document_chunks {
        int id PK
        int document_id FK
        int chunk_index
        int page_start
        int page_end
        text content
        int vector_position
    }
    conversations {
        int id PK
        int user_id FK
        string title
        text summary
        int summarized_until_message_id
    }
    messages {
        int id PK
        int conversation_id FK
        string role
        text content
        json citations_json
        json agent_trace_json
        json metrics_json
    }
    audit_logs {
        int id PK
        int user_id FK
        string action
        string outcome
        json detail_json
    }
    evaluation_results {
        int id PK
        string run_id UK
        json retrieval_metrics_json
        json generation_metrics_json
        json system_metrics_json
        float overall_score
    }
```

## 7. Deployment

```mermaid
flowchart TB
    I[Internet] --> NG[nginx :8080<br/>frontend container]
    NG -->|/ static| SPA[React build dist/]
    NG -->|/api/* proxy · SSE unbuffered| BK[backend container<br/>uvicorn ×2 · tesseract+poppler]
    BK --> PG[(postgres:16<br/>pgdata volume)]
    BK --> UV[volumes: uploads · vectors · evaldata]
    BK --> GEM[Gemini API<br/>google-genai SDK]
```
