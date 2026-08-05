# Frontend ↔ Backend integration TODOs

The frontend never fakes API responses. Features below are visible in the UI
but disabled (with a toast explaining why) until the backend endpoint exists.

## Status after Module 4

| Feature | Endpoint | Status |
|---|---|---|
| Download original file | `GET /api/documents/{id}/download` | ✅ DONE |
| Rename / edit document | `PATCH /api/documents/{id}` (filename, category, description, tags) | ✅ DONE |
| Real authentication | `POST /api/auth/register`, `/login`, `/refresh` (rotation), `/logout`, `GET /me` | ✅ DONE — bcrypt + JWT, all data APIs protected |
| Chat history persistence | `GET/POST/PATCH/DELETE /api/conversations` + messages | ✅ DONE — survives any browser |
| Streaming answers | `POST /api/ask/stream` (SSE: stages, tokens, done) | ✅ DONE — real Gemini token stream, abortable |
| Search-over-time analytics | `GET /api/analytics/searches?days=N` | ✅ DONE — daily volume + top queries |
| Pipeline retry | `POST /api/documents/{id}/reprocess` | ✅ DONE |
| Metrics | `GET /api/metrics` (Prometheus text) | ✅ DONE |

## Still open (honest gaps)

| Feature | Required work |
|---|---|
| Per-document chunk count | include `chunk_count` in the detail schema |
| Server-side pagination totals | `X-Total-Count` header for true infinite scroll |
| RAG config introspection | read-only `GET /api/config` |
| CSV / Excel report export | openpyxl / csv writer next to ReportLab |
| Scheduled reports | APScheduler / Celery beat |
| Redis | swap the in-memory rate limiter + caches when running multi-instance |
| Distributed task queue | Celery/RQ to replace FastAPI BackgroundTasks at scale |
| OpenTelemetry export | wire the existing metrics middleware to OTLP |
| Malware scanning | hook point: StorageService.validate before save |

## Client-side by design (not backend gaps)

- Pinned documents / favorites — localStorage (`eki.pinned`), per browser.
- Theme — localStorage (`eki.theme`).
- Demo session — localStorage (`eki.session`) until JWT endpoints exist.

## Redesign queue (Module 3+)

- Ask AI chat page (currently v1 “legacy” styling, fully functional)
- Semantic Search page (legacy, functional)
- Reports page (legacy, functional)
- Analytics page (placeholder)
- Settings / Profile pages (placeholders)
