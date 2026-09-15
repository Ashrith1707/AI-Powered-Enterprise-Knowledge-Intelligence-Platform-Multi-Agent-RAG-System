# KnowledgeIQ — Deployment Guide

## 1. Production stack

| Component | Technology | Notes |
|---|---|---|
| Database | **PostgreSQL 16** | Production refuses SQLite at startup |
| Backend | FastAPI + uvicorn (2 workers) | non-root container user |
| Frontend | React build served by **Nginx** | SPA fallback + `/api` reverse proxy |
| OCR | tesseract-ocr + poppler-utils | baked into the backend image |
| Orchestration | Docker Compose | healthchecks on all services |

Redis / Celery are deliberately **not** included: document processing runs on an in-process thread-pool job registry (`app/services/jobs.py`), which is sufficient at the target scale. The registry interface is the documented swap point if a real queue is ever justified by measurements.

## 2. Docker Compose (recommended)

```bash
git clone <your-repo> && cd knowledgeiq
cp .env.example .env
```

Edit `.env` — **required**:

```env
SECRET_KEY=<long random string>          # e.g. openssl rand -hex 32
POSTGRES_PASSWORD=<strong password>
GEMINI_API_KEY=<your Google AI Studio key>   # optional but recommended
```

Start:

```bash
docker compose up --build -d
docker compose ps          # all services healthy
curl http://localhost:8080/api/health
curl http://localhost:8080/api/ready
```

App: `http://localhost:8080` (change with `FRONTEND_PORT`). The first registered account becomes **admin**.

Volumes: `pgdata` (database), `uploads` (stored files), `vectors` (FAISS index + id map), `evaldata` (evaluation JSON artifacts). Back these up.

## 3. Bare-metal deployment

```bash
# 1. PostgreSQL
createdb knowledgeiq
export DATABASE_URL="postgresql+psycopg2://kiq:PASSWORD@127.0.0.1:5432/knowledgeiq"

# 2. Backend
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cat > .env <<EOF
APP_ENV=production
DATABASE_URL=$DATABASE_URL
SECRET_KEY=<random>
GEMINI_API_KEY=<key>
CORS_ORIGINS=https://knowledgeiq.example.com
EOF
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 2

# 3. Frontend
cd frontend && npm ci && npm run build
# copy dist/ to /var/www/knowledgeiq/dist

# 4. Nginx — use nginx/nginx.conf (TLS termination, SSE-friendly proxying)
```

## 4. Health & readiness

| Endpoint | Purpose | Fails when |
|---|---|---|
| `GET /api/health` | liveness + dependency report (DB, vector store, providers, OCR, config problems) | never (informational) |
| `GET /api/ready` | readiness probe | DB unreachable or vector store unloadable → HTTP 503 |
| `GET /api/metrics` | Prometheus-style counters/latencies | — |

Docker `HEALTHCHECK`s use these endpoints.

## 5. Environment reference (backend)

| Variable | Default | Production requirement |
|---|---|---|
| `APP_ENV` | `development` | `production` (enables guards + HSTS header) |
| `DATABASE_URL` | SQLite file | **must** be PostgreSQL |
| `SECRET_KEY` | placeholder | **must** be a long random secret |
| `GEMINI_API_KEY` | empty | set for real AI; otherwise clearly-reported offline mode |
| `GEMINI_MODEL` | `gemini-2.5-flash` | verify availability with your key/tier |
| `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-001` | **not** the deprecated `text-embedding-004` |
| `EMBEDDING_DIMENSIONS` | `768` | must match the index; changing it requires re-indexing |
| `CORS_ORIGINS` | localhost:5173 | your public origin(s) |
| `MAX_UPLOAD_MB` | `25` | align with nginx `client_max_body_size` |
| `RATE_LIMIT_PER_MINUTE` / `RATE_LIMIT_AUTH_PER_MINUTE` | 120 / 10 | tune per traffic |
| `TESSERACT_CMD` | auto-detect | path if not on PATH |

Full list with comments: `backend/.env.example`.

## 6. Model/embedding configuration notes

* The platform uses the modern **`google-genai`** SDK exclusively. The legacy `google.generativeai` package and `text-embedding-004` appear nowhere in the code (a CI job enforces this).
* If a configured model 404s, the error surfaces as `model_not_found` with guidance — **not** “invalid API key”. Fix by setting a model your key/tier can access (`GEMINI_MODEL`, `GEMINI_EMBEDDING_MODEL`).
* `EMBEDDING_PROVIDER=auto` probes Gemini once at startup; on failure it falls back to local lexical embeddings **and reports the fallback** in `/api/health`, the Settings page and the sidebar badge.
* Switching embedding providers/dimensions invalidates the FAISS index. The store detects the mismatch and starts a fresh index; re-upload or reprocess documents afterwards (`POST /api/documents/{id}/reprocess`).

## 7. Upgrades & backups

* **DB:** `pg_dump` the `knowledgeiq` database.
* **Files:** back up the `uploads` volume; the `vectors` volume can be rebuilt by reprocessing documents.
* **Rollout:** `docker compose pull && docker compose up -d --build`. The schema is created idempotently at startup; for breaking model changes in future releases, adopt Alembic (tracked in TODO.md).

## 8. Security checklist for go-live

- [ ] `SECRET_KEY` unique & random; never in git
- [ ] `POSTGRES_PASSWORD` strong; DB not exposed publicly (compose keeps it internal)
- [ ] TLS terminated at nginx/load balancer; `APP_ENV=production` enables HSTS
- [ ] `CORS_ORIGINS` limited to real origins
- [ ] `GEMINI_API_KEY` scoped & quota-monitored (429s surface as `quota_exceeded`)
- [ ] Upload size limit aligned across backend + nginx
- [ ] Audit log retention policy decided (`audit_logs` table)
- [ ] Backups scheduled for `pgdata` + `uploads`
