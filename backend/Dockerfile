# ============================================================
# KnowledgeIQ Backend — production image
# Python 3.12 slim + tesseract OCR + poppler (scanned-PDF OCR)
# ============================================================
FROM python:3.12-slim AS runtime

# System deps: tesseract (OCR), poppler-utils (PDF rendering for OCR of scans)
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        poppler-utils \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/knowledgeiq

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data/evaluation ./data/evaluation

# Non-root user (enterprise security practice)
RUN useradd --create-home --uid 1000 kiq \
    && mkdir -p /srv/knowledgeiq/data \
    && chown -R kiq:kiq /srv/knowledgeiq
USER kiq

ENV PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    TESSERACT_CMD=/usr/bin/tesseract

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8001/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]
