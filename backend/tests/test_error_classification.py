"""AI error classification tests — the root-cause fix for the known issue.

The system must differentiate 401 / 403 / 404 / 429 / 5xx / network / timeout
instead of showing "The Gemini API key is INVALID" for everything.
"""
from __future__ import annotations

from app.core.errors import AIErrorCode, AIProviderError, classify_ai_error


class FakeAPIError(Exception):
    """Mimics google.genai.errors.APIError (has .code)."""

    def __init__(self, code: int, message: str):
        self.code = code
        super().__init__(message)


def test_404_model_not_found_is_not_api_key_error():
    """The exact historical failure: text-embedding-004 on v1beta."""
    exc = FakeAPIError(404, "models/text-embedding-004 is not found for API version v1beta")
    result = classify_ai_error(exc, model="text-embedding-004")
    assert result.error_code == AIErrorCode.MODEL_NOT_FOUND
    assert result.details["model"] == "text-embedding-004"
    # The user-facing message must mention the model, NOT the API key
    assert "api key" not in result.message.lower() or "invalid" not in result.message.lower()
    assert "gemini-embedding-001" in result.message  # actionable guidance


def test_404_from_plain_message():
    exc = Exception("404 models/text-embedding-004 is not found for API version v1beta")
    assert classify_ai_error(exc).error_code == AIErrorCode.MODEL_NOT_FOUND


def test_401_invalid_api_key():
    exc = FakeAPIError(401, "API key not valid. Please pass a valid API key.")
    result = classify_ai_error(exc)
    assert result.error_code == AIErrorCode.INVALID_API_KEY
    assert not result.retryable


def test_403_permission_denied():
    exc = FakeAPIError(403, "Permission denied. API key does not have access to this model.")
    assert classify_ai_error(exc).error_code == AIErrorCode.PERMISSION_DENIED


def test_429_quota_is_retryable():
    exc = FakeAPIError(429, "Resource has been exhausted (e.g. check quota).")
    result = classify_ai_error(exc)
    assert result.error_code == AIErrorCode.QUOTA_EXCEEDED
    assert result.retryable is True


def test_5xx_provider_error_is_retryable():
    exc = FakeAPIError(503, "The service is currently unavailable.")
    result = classify_ai_error(exc)
    assert result.error_code == AIErrorCode.PROVIDER_ERROR
    assert result.retryable is True


def test_timeout_classification():
    assert classify_ai_error(TimeoutError("read timed out")).error_code == AIErrorCode.TIMEOUT
    exc = Exception("Request deadline exceeded while calling generativelanguage.googleapis.com")
    assert classify_ai_error(exc).error_code == AIErrorCode.TIMEOUT


def test_network_classification():
    exc = ConnectionError("Connection refused while connecting to generativelanguage.googleapis.com")
    assert classify_ai_error(exc).error_code == AIErrorCode.NETWORK_ERROR
    exc2 = Exception("[Errno -2] Name or service not known")
    assert classify_ai_error(exc2).error_code == AIErrorCode.NETWORK_ERROR


def test_unknown_error_stays_classified_not_blanket_key_error():
    exc = Exception("something entirely unexpected happened")
    result = classify_ai_error(exc)
    assert result.error_code == AIErrorCode.UNKNOWN
    assert result.message  # never empty


def test_error_message_redacts_api_keys():
    exc = Exception("failed with key AIzaSyDFAKEKEYVALUE1234567890abcdefgh in header")
    result = classify_ai_error(exc)
    assert "AIzaSyDFAKEKEYVALUE" not in str(result.details)
    assert "REDACTED" in str(result.details)


def test_ai_provider_error_is_http_502_with_details():
    err = AIProviderError(AIErrorCode.MODEL_NOT_FOUND, "404 not found", model="gemini-x")
    assert err.http_status == 502
    assert err.details["ai_error_code"] == "model_not_found"
    assert err.details["model"] == "gemini-x"


def test_llm_generate_failure_classified(env, monkeypatch):
    """GeminiLLM.generate must raise classified errors, not raw SDK exceptions."""
    import pytest

    from app.services.llm import GeminiLLM

    llm = GeminiLLM("fake-key", "gemini-2.5-flash")

    class FakeModels:
        def generate_content(self, **kwargs):
            raise FakeAPIError(429, "You exceeded your current quota, please check your plan and billing details.")

    class FakeClient:
        models = FakeModels()

    llm._client = FakeClient()  # noqa: SLF001 — test seam

    with pytest.raises(AIProviderError) as excinfo:
        llm.generate("hello")
    assert excinfo.value.error_code == AIErrorCode.QUOTA_EXCEEDED
    assert excinfo.value.retryable
