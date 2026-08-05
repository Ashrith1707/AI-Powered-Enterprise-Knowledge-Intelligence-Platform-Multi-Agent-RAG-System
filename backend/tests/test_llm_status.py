from app.rag.llm_client import classify_llm_error, gemini_status


def test_classify_invalid_key():
    status, msg = classify_llm_error(Exception(
        "400 API key not valid. [reason: API_KEY_INVALID]"))
    assert status == "invalid_key"
    assert "backend/.env" in msg


def test_classify_quota():
    status, msg = classify_llm_error(Exception("429 RESOURCE_EXHAUSTED: quota"))
    assert status == "quota_exceeded"


def test_classify_unknown_error_is_truncated():
    status, msg = classify_llm_error(Exception("x" * 500))
    assert status == "error"
    assert len(msg) < 260


def test_status_not_configured_without_key_and_no_network():
    # Tests run with GEMINI_API_KEY="" — must short-circuit before any network.
    result = gemini_status(force=True)
    assert result["status"] == "not_configured"


def test_health_reports_validated_llm_status(client):
    body = client.get("/api/health").json()
    assert body["llm_status"] == "not_configured"
    assert body["llm_configured"] is False
    assert "GEMINI_API_KEY" in body["llm_detail"]
