"""Security tests: headers, rate limiting, sanitization, authorization, safe errors."""
from __future__ import annotations

from app.core.security import is_within_directory, sanitize_filename
from tests.conftest import auth_headers, login, register_user, upload_document, wait_for_processing


def test_security_headers_present(client):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "referrer-policy" in r.headers
    assert "x-request-id" in r.headers


def test_request_id_propagation(client):
    r = client.get("/api/health", headers={"X-Request-ID": "trace-me-123"})
    assert r.headers["x-request-id"] == "trace-me-123"


def test_auth_rate_limiting(client, env, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_AUTH_PER_MINUTE", "5")
    from app.config import get_settings
    from app.core.middleware import reset_rate_limiter_for_tests

    get_settings.cache_clear()
    reset_rate_limiter_for_tests()

    register_user(client)
    statuses = []
    for _ in range(8):
        r = client.post("/api/auth/login", json={"email": "user@test.dev", "password": "Passw0rd123"})
        statuses.append(r.status_code)
    assert 429 in statuses
    limited = client.post("/api/auth/login", json={"email": "user@test.dev", "password": "Passw0rd123"})
    if limited.status_code == 429:
        assert "Retry-After" in limited.headers
        assert limited.json()["error"]["code"] == "rate_limited"

    reset_rate_limiter_for_tests()


def test_api_rate_limiting_general(client, env, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "10")
    from app.config import get_settings
    from app.core.middleware import reset_rate_limiter_for_tests

    get_settings.cache_clear()
    reset_rate_limiter_for_tests()

    codes = [client.get("/api/health").status_code for _ in range(3)]
    assert all(c == 200 for c in codes)  # health is exempt

    register_user(client)
    headers = auth_headers(login(client))
    codes = [client.get("/api/documents", headers=headers).status_code for _ in range(15)]
    assert 429 in codes
    reset_rate_limiter_for_tests()


def test_filename_sanitization():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\windows\\system32\\x.dll") == "x.dll"
    # unicode tricks are normalized; unsafe chars become "_"
    assert sanitize_filename("hello\u202eworld.txt") in ("helloworld.txt", "hello_world.txt", "hello world.txt")
    assert "/" not in sanitize_filename("/absolute/path/file.pdf")
    assert sanitize_filename("") == "upload"
    assert sanitize_filename("...") == "upload"
    long_name = "a" * 500 + ".pdf"
    assert len(sanitize_filename(long_name)) <= 180


def test_path_containment():
    assert is_within_directory("/data/uploads/a.pdf", "/data/uploads")
    assert not is_within_directory("/data/uploads/../../etc/passwd", "/data/uploads")


def test_unauthorized_access_is_404_not_403(client):
    """Existence of other users' resources must not leak (404, not 403)."""
    register_user(client, "alice@test.dev")
    alice = auth_headers(login(client, "alice@test.dev"))
    register_user(client, "bob@test.dev")
    bob = auth_headers(login(client, "bob@test.dev"))

    from tests.conftest import SAFETY_DOC

    doc = upload_document(client, alice, "alice.txt", SAFETY_DOC.encode())
    wait_for_processing(client, alice, doc["id"])

    assert client.get(f"/api/documents/{doc['id']}", headers=bob).status_code == 404
    assert client.get(f"/api/documents/{doc['id']}/content", headers=bob).status_code == 404
    assert client.post(f"/api/documents/{doc['id']}/reprocess", headers=bob).status_code == 404


def test_search_cannot_see_other_users_documents(client):
    register_user(client, "alice@test.dev")
    alice = auth_headers(login(client, "alice@test.dev"))
    register_user(client, "bob@test.dev")
    bob = auth_headers(login(client, "bob@test.dev"))

    from tests.conftest import SAFETY_DOC

    doc = upload_document(client, alice, "alice-secret.txt", SAFETY_DOC.encode())
    wait_for_processing(client, alice, doc["id"])

    r = client.post("/api/search", headers=bob,
                    json={"query": "lockout tagout machine maintenance safety"})
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_error_messages_are_structured_and_safe(client):
    r = client.get("/api/documents/99999", headers={"Authorization": "Bearer invalid"})
    assert r.status_code == 401
    body = r.json()
    assert body["error"]["code"] == "authentication_failed"
    assert "Traceback" not in r.text
    assert "sqlalchemy" not in r.text.lower()


def test_404_unknown_route_structured(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "http_404"


def test_upload_requires_authentication(client):
    r = client.post("/api/documents/upload", files={"file": ("x.txt", b"content", "text/plain")})
    assert r.status_code == 401


def test_sql_injection_in_search_is_harmless(client, user_client):
    client, headers, _ = user_client
    payloads = [
        "'; DROP TABLE documents; --",
        "1' OR '1'='1",
        "\" UNION SELECT hashed_password FROM users --",
    ]
    for payload in payloads:
        r = client.post("/api/search", headers=headers, json={"query": payload})
        assert r.status_code == 200
    # tables still functional
    assert client.get("/api/documents", headers=headers).status_code == 200


def test_secrets_not_leaked_in_health(client):
    r = client.get("/api/health")
    body = r.text.lower()
    assert "secret_key" not in body
    assert "gemini_api_key" not in body or "AIza" not in r.text


def test_logging_redacts_keys():
    from app.core.logging_conf import RedactionFilter
    import logging

    f = RedactionFilter()
    record = logging.LogRecord("t", logging.INFO, "", 0,
                               "Calling with api_key=AIzaSyD-FAKE-KEY-1234567890abcdef now", (), None)
    f.filter(record)
    assert "AIzaSyD-FAKE" not in record.getMessage()
    assert "REDACTED" in record.getMessage()
