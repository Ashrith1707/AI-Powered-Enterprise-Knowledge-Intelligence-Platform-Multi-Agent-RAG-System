"""Single gateway to the Gemini chat model via LangChain, plus key
validation and human-readable error classification."""
import time

from app.core.config import settings
from app.core.exceptions import LLMNotConfiguredError
from app.core.logging_config import get_logger

logger = get_logger("llm")
_llm = None
_status_cache: dict = {"result": None, "at": 0.0}
STATUS_TTL_SECONDS = 600


def classify_llm_error(exc: Exception) -> tuple[str, str]:
    """Maps raw Google/SDK errors to (status, user-friendly message)."""
    s = str(exc)
    if "API_KEY_INVALID" in s or "API key not valid" in s:
        return ("invalid_key",
                "The Gemini API key is INVALID. Replace GEMINI_API_KEY in "
                "backend/.env with a real key from aistudio.google.com/apikey "
                "and restart the backend.")
    if "RESOURCE_EXHAUSTED" in s or "429" in s or "quota" in s.lower():
        return ("quota_exceeded",
                "Gemini quota exceeded — wait for the quota window to reset "
                "or upgrade the plan, then retry.")
    if "PERMISSION_DENIED" in s:
        return ("permission_denied",
                "The Gemini API key lacks permission for this model — check "
                "that the Generative Language API is enabled for the key.")
    return ("error", f"Gemini request failed: {s[:200]}")


def friendly_llm_error(exc: Exception) -> str:
    return classify_llm_error(exc)[1]


def gemini_status(force: bool = False) -> dict:
    """Validates the configured key with ONE cheap embedding call, cached for
    {TTL} seconds so health polling never spams Google. Returns
    {status, detail, model} where status ∈ ok | not_configured | invalid_key |
    quota_exceeded | permission_denied | error."""
    if not settings.gemini_api_key:
        return {"status": "not_configured",
                "detail": "GEMINI_API_KEY is not set in backend/.env — "
                          "Ask AI is disabled; a local fallback embedder is used.",
                "model": None}
    now = time.monotonic()
    if not force and _status_cache["result"] and now - _status_cache["at"] < STATUS_TTL_SECONDS:
        return _status_cache["result"]
    try:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        GoogleGenerativeAIEmbeddings(
            model=settings.gemini_embedding_model,
            google_api_key=settings.gemini_api_key,
        ).embed_query("connection probe")
        result = {"status": "ok",
                  "detail": f"Gemini validated ({settings.gemini_chat_model} + "
                            f"{settings.gemini_embedding_model}).",
                  "model": settings.gemini_chat_model}
    except Exception as exc:
        status, detail = classify_llm_error(exc)
        result = {"status": status, "detail": detail,
                  "model": settings.gemini_chat_model}
    _status_cache.update(result=result, at=now)
    return result


def get_llm():
    global _llm
    if _llm is None:
        if not settings.gemini_api_key:
            raise LLMNotConfiguredError(
                "GEMINI_API_KEY is not set. Add it to backend/.env to enable AI answers.")
        from langchain_google_genai import ChatGoogleGenerativeAI
        _llm = ChatGoogleGenerativeAI(
            model=settings.gemini_chat_model,
            google_api_key=settings.gemini_api_key,
            temperature=0.2,
        )
    return _llm


def generate(prompt: str) -> str:
    response = get_llm().invoke(prompt)
    return response.content if hasattr(response, "content") else str(response)
