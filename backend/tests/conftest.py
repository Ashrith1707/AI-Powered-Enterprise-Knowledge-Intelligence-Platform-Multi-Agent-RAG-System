"""Shared test fixtures.

Every test gets an isolated environment: fresh SQLite DB, upload dir, vector
dir, offline providers (mock LLM + local embeddings) — no network, no real
API keys, deterministic results.
"""
from __future__ import annotations

import os
import time

import pytest

# Ensure offline/test configuration BEFORE any app module import.
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("EMBEDDING_PROVIDER", "local")
os.environ.setdefault("GEMINI_API_KEY", "")

TEST_SECRET = "unit-test-secret-key-32-bytes-long!"


def _reset_singletons() -> None:
    from app.config import get_settings
    from app.database import reset_engine_for_tests
    from app.rag.bm25 import reset_bm25_for_tests
    from app.services.embeddings import reset_embedding_provider
    from app.services.llm import clear_provider_cache
    from app.services.vector_store import reset_vector_store

    get_settings.cache_clear()
    reset_engine_for_tests()
    reset_vector_store()
    reset_embedding_provider()
    reset_bm25_for_tests()
    clear_provider_cache()


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("VECTOR_DIR", str(tmp_path / "vectors"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET)
    monkeypatch.setenv("APP_ENV", "development")

    _reset_singletons()

    from app.core.middleware import reset_rate_limiter_for_tests
    from app.database import init_db

    reset_rate_limiter_for_tests()
    init_db()
    yield tmp_path
    _reset_singletons()


@pytest.fixture()
def app(env):
    from app.main import create_app

    return create_app()


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def register_user(client, email: str = "user@test.dev", password: str = "Passw0rd123",
                  full_name: str = "Test User") -> dict:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )
    assert response.status_code == 201, response.text
    return response.json()


def login(client, email: str = "user@test.dev", password: str = "Passw0rd123") -> dict:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def auth_headers(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture()
def user_client(client):
    """A client with a registered+logged-in regular user; returns (client, headers, user)."""
    user = register_user(client)
    tokens = login(client)
    return client, auth_headers(tokens), user


def make_minimal_pdf(text: str = "Hello KnowledgeIQ") -> bytes:
    """Build a valid single-page PDF containing one line of text (no external libs)."""
    stream_content = f"BT /F1 18 Tf 72 700 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream_content)).encode() + b" >>\nstream\n"
        + stream_content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF".encode()
    )
    return bytes(out)


def upload_document(client, headers, filename: str, content: bytes, mime: str = "text/plain") -> dict:
    response = client.post(
        "/api/documents/upload",
        headers=headers,
        files={"file": (filename, content, mime)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def wait_for_processing(client, headers, document_id: int, timeout: float = 20.0,
                        expect: str = "completed") -> dict:
    deadline = time.time() + timeout
    status = {}
    while time.time() < deadline:
        status = client.get(f"/api/documents/{document_id}/status", headers=headers).json()
        if status["status"] in ("completed", "failed"):
            break
        time.sleep(0.1)
    assert status["status"] == expect, f"expected {expect}, got {status}"
    return status


SAFETY_DOC = (
    "Industrial Machine Safety Manual\n"
    "Document ID: SOP-4021 | Version 3.2 | Department: Operations\n\n"
    "All maintenance personnel must perform lockout-tagout (LOTO) before servicing any machine. "
    "The authorized technician must isolate all energy sources and apply a personal padlock. "
    "Maintenance work on energized equipment is strictly prohibited.\n\n"
    "Safety glasses, steel-toe boots and cut-resistant gloves are mandatory on the production floor. "
    "Only technicians who completed the Level-2 Maintenance Certification may open machine guards."
)

HR_DOC = (
    "Employee Leave Policy\n"
    "Document ID: POL-1102 | Department: Human Resources\n\n"
    "Full-time employees are entitled to 24 days of paid annual leave per calendar year. "
    "Employees may carry over a maximum of 5 unused leave days to the following year. "
    "Leave requests must be submitted through the HR portal at least 5 working days in advance."
)
