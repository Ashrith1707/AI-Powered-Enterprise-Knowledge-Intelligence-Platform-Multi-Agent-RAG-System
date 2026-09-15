"""Document upload / processing / management tests."""
from __future__ import annotations

from tests.conftest import (
    HR_DOC,
    SAFETY_DOC,
    auth_headers,
    login,
    make_minimal_pdf,
    register_user,
    upload_document,
    wait_for_processing,
)


def test_upload_txt_processes_to_completion(client, user_client):
    client, headers, _ = user_client
    doc = upload_document(client, headers, "safety_manual.txt", SAFETY_DOC.encode())
    assert doc["status"] == "pending"

    status = wait_for_processing(client, headers, doc["id"])
    assert status["progress"] == 100

    detail = client.get(f"/api/documents/{doc['id']}", headers=headers).json()
    assert detail["status"] == "completed"
    assert detail["chunk_count"] >= 1
    assert detail["char_count"] > 100
    assert detail["metadata"]["department"] == "Operations"
    assert detail["metadata"]["category"] == "manual"
    assert "SOP-4021" in detail["entities"]["reference_codes"]


def test_upload_pdf_and_metadata(client, user_client):
    client, headers, _ = user_client
    pdf = make_minimal_pdf("Quarterly Finance Report 2024-03-01")
    doc = upload_document(client, headers, "quarterly.pdf", pdf, "application/pdf")
    wait_for_processing(client, headers, doc["id"])
    detail = client.get(f"/api/documents/{doc['id']}", headers=headers).json()
    assert detail["status"] == "completed"
    assert detail["page_count"] == 1


def test_upload_rejects_bad_extension(client, user_client):
    client, headers, _ = user_client
    r = client.post("/api/documents/upload", headers=headers,
                    files={"file": ("malware.exe", b"MZ\x90\x00binary", "application/octet-stream")})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "upload_rejected"


def test_upload_rejects_spoofed_content(client, user_client):
    """A .pdf that isn't really a PDF must fail the magic-byte check."""
    client, headers, _ = user_client
    r = client.post("/api/documents/upload", headers=headers,
                    files={"file": ("fake.pdf", b"this is definitely not a pdf", "application/pdf")})
    assert r.status_code == 400
    assert "magic-byte" in r.json()["error"]["message"]


def test_upload_rejects_empty_file(client, user_client):
    client, headers, _ = user_client
    r = client.post("/api/documents/upload", headers=headers, files={"file": ("empty.txt", b"", "text/plain")})
    assert r.status_code == 400


def test_upload_rejects_oversize_file(client, user_client, monkeypatch):
    from app.config import get_settings

    client, headers, _ = user_client
    settings = get_settings()
    big = b"x" * (settings.max_upload_mb * 1024 * 1024 + 10)
    r = client.post("/api/documents/upload", headers=headers, files={"file": ("big.txt", big, "text/plain")})
    assert r.status_code == 400
    assert "upload limit" in r.json()["error"]["message"]


def test_filename_traversal_is_sanitized(client, user_client):
    client, headers, _ = user_client
    doc = upload_document(client, headers, "../../etc/passwd.txt", b"root:x:0:0 safe content here")
    assert "/" not in doc["filename"] and ".." not in doc["filename"]
    wait_for_processing(client, headers, doc["id"])

    from app.config import get_settings
    from pathlib import Path

    stored = Path(get_settings().upload_dir)
    files = list(stored.iterdir())
    assert all(not f.name.startswith("..") for f in files)


def test_document_list_and_pagination(client, user_client):
    client, headers, _ = user_client
    upload_document(client, headers, "a.txt", SAFETY_DOC.encode())
    upload_document(client, headers, "b.txt", HR_DOC.encode())
    wait_for_processing(client, headers, 1)
    wait_for_processing(client, headers, 2)

    r = client.get("/api/documents", headers=headers, params={"page": 1, "page_size": 1})
    body = r.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1


def test_document_content_preview(client, user_client):
    client, headers, _ = user_client
    doc = upload_document(client, headers, "safety.txt", SAFETY_DOC.encode())
    wait_for_processing(client, headers, doc["id"])
    r = client.get(f"/api/documents/{doc['id']}/content", headers=headers)
    assert r.status_code == 200
    pages = r.json()["pages"]
    assert pages and "lockout" in pages[0]["text"].lower()


def test_document_delete_removes_vectors(client, user_client):
    from app.services.vector_store import get_vector_store

    client, headers, _ = user_client
    doc = upload_document(client, headers, "safety.txt", SAFETY_DOC.encode())
    wait_for_processing(client, headers, doc["id"])
    store = get_vector_store()
    count_before = store.count
    assert count_before > 0

    r = client.delete(f"/api/documents/{doc['id']}", headers=headers)
    assert r.status_code == 204
    assert store.count < count_before
    assert client.get(f"/api/documents/{doc['id']}", headers=headers).status_code == 404


def test_document_reprocess(client, user_client):
    client, headers, _ = user_client
    doc = upload_document(client, headers, "hr.txt", HR_DOC.encode())
    wait_for_processing(client, headers, doc["id"])
    r = client.post(f"/api/documents/{doc['id']}/reprocess", headers=headers)
    assert r.status_code == 202
    wait_for_processing(client, headers, doc["id"], timeout=25)
    detail = client.get(f"/api/documents/{doc['id']}", headers=headers).json()
    assert detail["status"] == "completed"


def test_scanned_document_fails_with_clear_ocr_message(client, user_client):
    """An image-only upload without tesseract must fail with an honest OCR message."""
    import shutil

    if shutil.which("tesseract"):
        import pytest
        pytest.skip("tesseract is installed; graceful-degradation path not applicable")

    client, headers, _ = user_client
    # A real (tiny) PNG image — requires OCR to extract any text.
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 32), color="white").save(buf, format="PNG")
    doc = upload_document(client, headers, "scan.png", buf.getvalue(), "image/png")
    status = wait_for_processing(client, headers, doc["id"], expect="failed")
    assert "OCR" in (status["error_message"] or "") or "Tesseract" in (status["error_message"] or "")


def test_other_users_document_is_invisible(client):
    register_user(client, "alice@test.dev")
    alice = auth_headers(login(client, "alice@test.dev"))
    register_user(client, "bob@test.dev")
    bob = auth_headers(login(client, "bob@test.dev"))

    doc = upload_document(client, alice, "alice-secret.txt", SAFETY_DOC.encode())
    wait_for_processing(client, alice, doc["id"])

    assert client.get(f"/api/documents/{doc['id']}", headers=bob).status_code == 404
    assert client.delete(f"/api/documents/{doc['id']}", headers=bob).status_code == 404
    assert client.get("/api/documents", headers=bob).json()["total"] == 0
