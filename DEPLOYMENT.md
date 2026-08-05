# Deployment Guide — Enterprise Knowledge Intelligence Platform

## Prerequisites

| Requirement | Local dev | Docker |
|---|---|---|
| Python 3.11–3.13 | ✅ | — (image provides 3.12) |
| Node 18+ | ✅ | — (build stage provides 20) |
| PostgreSQL 14+ | optional (SQLite fallback) | ✅ bundled |
| Tesseract OCR | optional (scanned docs only) | ✅ bundled |
| Gemini API key | needed for Ask AI only | same |

## Environment variables (backend/.env)

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | SQLite file in backend/ | `postgresql+psycopg2://user:pass@host:5432/knowledge_db` for Postgres |
| `GEMINI_API_KEY` | empty | enables Gemini answers + embeddings; without it a local fallback embedder runs and `/api/ask` returns 503 |
| `TESSERACT_CMD` | Windows install path | full path to tesseract binary |
| `APP_ENV` | development | shown in /api/health |
| `MAX_UPLOAD_MB` | 50 | upload size limit |

Real environment variables override `.env` (useful for one-off runs):
`DATABASE_URL="sqlite:///./knowledge.db" uvicorn app.main:app`

## Running locally

```bash
# Backend (from backend/)
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # edit values
uvicorn app.main:app --reload   # http://localhost:8000/docs

# Frontend (from frontend/)
npm install
npm run dev                     # http://localhost:5173 (proxies /api → :8000)

# Tests
cd backend && pytest            # 13 tests
cd frontend && npm run build    # must pass with zero warnings
```

## PostgreSQL setup (local, without Docker)

1. Install PostgreSQL, start the service.
2. `createdb -U postgres knowledge_db` (or via pgAdmin).
3. Uncomment/set `DATABASE_URL` in `backend/.env`.
4. Restart uvicorn — tables are created automatically at startup.

## Gemini configuration

Where the key is read: `backend/app/core/config.py` loads `GEMINI_API_KEY`
from `backend/.env` via pydantic-settings (a real environment variable
overrides the file). SDK: `langchain-google-genai` — chat `gemini-2.0-flash`,
embeddings `models/text-embedding-004`.

1. Create a free key at https://aistudio.google.com/apikey
2. In `backend/.env`, replace the placeholder line with the real value
   (no quotes): `GEMINI_API_KEY=AIza...`
3. Validate BEFORE starting the app:
   `venv\Scripts\python -m scripts.check_gemini`
   — prints key source, embedding check, and a live streaming check with the
   exact failure cause (invalid key / quota / permission) if any step fails.
4. Restart uvicorn. Startup logs one unmissable line:
   `GEMINI: AVAILABLE — …` or `GEMINI: NOT AVAILABLE (invalid_key) — …`
5. Verify over HTTP: `GET /api/health` →
   `"llm_status": "ok"` (the key is actually VALIDATED with a probe call,
   not just checked for presence; result cached 10 minutes).

Failure causes surfaced to the UI and logs:

| llm_status | Meaning | Fix |
|---|---|---|
| `not_configured` | no key set | add the key, restart |
| `invalid_key` | Google returned `400 API_KEY_INVALID` (e.g. the placeholder value) | paste a real key, restart |
| `quota_exceeded` | `429 / RESOURCE_EXHAUSTED` | wait for quota reset or upgrade |
| `permission_denied` | key can't use the model | enable the Generative Language API |

If Gemini is unavailable, the platform degrades gracefully: uploads/search/
analytics keep working on a local fallback embedder (logged loudly), and
Ask AI returns the friendly message above instead of a stack trace. Restart
the backend after fixing the key — the embedder choice is made at startup.

## Running with Docker

```bash
# from the project root
GEMINI_API_KEY=your-real-key docker compose up --build
# → app on http://localhost  (nginx serves the SPA and proxies /api)
```

Compose runs three services: `db` (Postgres 16 + volume), `backend`
(FastAPI + Tesseract, health-checked), `frontend` (nginx: gzip, SPA
fallback, immutable asset caching, 60 MB upload limit, 180 s LLM timeout).
Uploaded files, the FAISS index and generated reports live in named volumes.

## Production checklist

- [x] JWT authentication (bcrypt, refresh rotation) — all data APIs protected
- [x] Rate limiting on /api/auth and /api/ask (in-memory; move to Redis for multi-instance)
- [x] Security headers + CORS origins via `CORS_ORIGINS` env var
- [x] /api/metrics (Prometheus text) + slow-request logging
- [ ] `SECRET_KEY` set to a long random value (the app warns if the dev default reaches production)
- [ ] `GEMINI_API_KEY` set and verified via /api/health
- [ ] PostgreSQL with backups (SQLite is dev-only)
- [ ] TLS termination in front of nginx (Caddy / cloud LB / certbot)
- [ ] Log aggregation for the structured uvicorn/agent logs

## Troubleshooting

| Symptom | Cause → fix |
|---|---|
| `Application startup failed` + `Connection refused ... 5432` | `DATABASE_URL` points at Postgres that isn't running → start Postgres or comment the line (SQLite fallback) |
| `/api/ask` returns 503 | `GEMINI_API_KEY` missing → add key, restart |
| Documents stuck on `failed` with auth error | key set but invalid → fix or remove key |
| Scanned PDFs produce empty pages | Tesseract not installed / wrong `TESSERACT_CMD` |
| Frontend "backend offline" badge | backend not running on :8000, or Vite proxy target changed |
| Vector search returns nothing after switching embedders | index dimension changed → delete `backend/vector_index/` and re-upload |
| 413 on big uploads behind nginx | raise `client_max_body_size` in nginx.conf |

## Health checks

- `GET /api/health` — liveness + `llm_configured`
- `GET /api/analytics/dashboard` — end-to-end DB read
- `docker compose ps` — backend container has a built-in healthcheck
