"""LLM provider abstraction.

Two providers implement the same interface:

* ``GeminiLLM`` — modern ``google-genai`` SDK (no deprecated
  ``google.generativeai`` anywhere in this repo). Model name comes from
  ``GEMINI_MODEL`` (default ``gemini-2.5-flash``).
* ``MockLLM`` — deterministic offline extractive answerer used when no API
  key is configured or for tests. It never fabricates facts: it builds the
  answer from the evidence it is given and clearly reports its provider.

All provider exceptions pass through :func:`classify_ai_error` so callers see
a classified ``AIProviderError`` (401 vs 403 vs 404 vs 429 vs 5xx vs network
vs timeout) instead of a blanket "API key is invalid".
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator, List, Optional

from app.config import get_settings
from app.core.errors import AIProviderError, classify_ai_error
from app.core.logging_conf import get_logger

logger = get_logger("llm")


@dataclass
class ChatMessage:
    role: str  # "user" | "model" | "system"
    content: str


@dataclass
class CompletionResult:
    text: str
    model: str
    provider: str  # "gemini" | "mock"
    latency_ms: float
    prompt_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    streamed: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def total_tokens(self) -> Optional[int]:
        if self.prompt_tokens is None or self.output_tokens is None:
            return None
        return self.prompt_tokens + self.output_tokens


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        history: Optional[List[ChatMessage]] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
    ) -> CompletionResult:
        ...

    @abstractmethod
    def generate_stream(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        history: Optional[List[ChatMessage]] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
    ) -> Iterator[str]:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...


# ---------------------------------------------------------------------------
# Gemini provider (modern google-genai SDK)
# ---------------------------------------------------------------------------
class GeminiLLM(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str):
        from google import genai  # imported lazily so the package is optional in tests

        self._api_key = api_key
        self._model = model
        self._client = genai.Client(api_key=api_key)

    @property
    def model(self) -> str:
        return self._model

    def is_available(self) -> bool:
        return bool(self._api_key)

    def _build_contents(self, prompt: str, history: Optional[List[ChatMessage]]):
        contents = []
        for m in history or []:
            role = "model" if m.role in ("assistant", "model") else "user"
            contents.append({"role": role, "parts": [{"text": m.content}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})
        return contents

    def generate(self, prompt, system_instruction=None, history=None, temperature=None,
                 max_output_tokens=None) -> CompletionResult:
        from google.genai import types

        started = time.perf_counter()
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=self._build_contents(prompt, history),
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature if temperature is not None else get_settings().llm_temperature,
                    max_output_tokens=max_output_tokens or get_settings().llm_max_output_tokens,
                ),
            )
        except Exception as exc:  # noqa: BLE001 — classified below
            raise classify_ai_error(exc, model=self._model) from exc
        latency = (time.perf_counter() - started) * 1000

        text = getattr(response, "text", "") or ""
        usage = getattr(response, "usage_metadata", None)
        prompt_tokens = getattr(usage, "prompt_token_count", None) if usage else None
        output_tokens = getattr(usage, "candidates_token_count", None) if usage else None
        logger.info("gemini.generate model=%s latency_ms=%.0f tokens_in=%s tokens_out=%s",
                    self._model, latency, prompt_tokens, output_tokens)
        return CompletionResult(
            text=text,
            model=self._model,
            provider=self.name,
            latency_ms=latency,
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
        )

    def generate_stream(self, prompt, system_instruction=None, history=None, temperature=None,
                        max_output_tokens=None) -> Iterator[str]:
        from google.genai import types

        try:
            stream = self._client.models.generate_content_stream(
                model=self._model,
                contents=self._build_contents(prompt, history),
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature if temperature is not None else get_settings().llm_temperature,
                    max_output_tokens=max_output_tokens or get_settings().llm_max_output_tokens,
                ),
            )
            for chunk in stream:
                piece = getattr(chunk, "text", "") or ""
                if piece:
                    yield piece
        except Exception as exc:  # noqa: BLE001
            raise classify_ai_error(exc, model=self._model) from exc


# ---------------------------------------------------------------------------
# Mock provider — deterministic, offline, evidence-grounded extractive answers
# ---------------------------------------------------------------------------
class MockLLM(LLMProvider):
    """Offline provider used when GEMINI_API_KEY is not configured.

    It answers *extractively* from the EVIDENCE block embedded in the prompt,
    so the full agent pipeline (including verification and citation
    validation) works end-to-end without any network calls. It never invents
    facts; with no evidence it says so explicitly.
    """

    name = "mock"

    def is_available(self) -> bool:
        return True

    def _extract(self, prompt: str) -> str:
        import re

        evidence_match = re.search(
            r"<EVIDENCE>(.*?)</EVIDENCE>", prompt, re.DOTALL
        )
        question_match = re.search(r"<QUESTION>(.*?)</QUESTION>", prompt, re.DOTALL)
        question = question_match.group(1).strip() if question_match else ""
        if not evidence_match or not evidence_match.group(1).strip():
            return (
                "The available documents do not contain enough information to answer this "
                "question. Please upload relevant documents or rephrase your question."
            )
        blocks = re.findall(r"\[(E\d+)\][^\n]*\n(.*?)(?=\n\[E\d+\]|\Z)", evidence_match.group(1), re.DOTALL)
        if not blocks:
            blocks = [("E1", evidence_match.group(1).strip())]
        parts = [f"Based on the retrieved enterprise documents, here is what they say about \"{question}\":" if question
                 else "Based on the retrieved enterprise documents:"]
        for tag, body in blocks[:4]:
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body.strip()) if s.strip()]
            snippet = " ".join(sentences[:3])
            if len(snippet) > 420:
                snippet = snippet[:420].rsplit(" ", 1)[0] + "…"
            parts.append(f"- {snippet} [{tag}]")
        parts.append(
            "\n(Answer produced in offline mock mode — configure GEMINI_API_KEY for full "
            "generative answers.)"
        )
        return "\n".join(parts)

    def generate(self, prompt, system_instruction=None, history=None, temperature=None,
                 max_output_tokens=None) -> CompletionResult:
        started = time.perf_counter()
        text = self._extract(prompt)
        return CompletionResult(
            text=text,
            model="mock-extractive-v1",
            provider=self.name,
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    def generate_stream(self, prompt, system_instruction=None, history=None, temperature=None,
                        max_output_tokens=None) -> Iterator[str]:
        text = self._extract(prompt)
        # Emit in word chunks so the SSE pipeline exercises real streaming.
        words = text.split(" ")
        buf: List[str] = []
        for w in words:
            buf.append(w)
            if len(buf) >= 4:
                yield " ".join(buf) + " "
                buf = []
        if buf:
            yield " ".join(buf)


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------
_provider_cache: dict[str, LLMProvider] = {}


def get_llm_provider(force_refresh: bool = False) -> LLMProvider:
    """Return the configured LLM provider.

    ``auto``: use Gemini when an API key is configured, otherwise the offline
    mock provider (the app remains fully functional for demo/testing).
    """
    settings = get_settings()
    mode = settings.llm_provider.lower()
    cache_key = f"{mode}:{bool(settings.gemini_api_key)}:{settings.gemini_model}"
    if not force_refresh and cache_key in _provider_cache:
        return _provider_cache[cache_key]

    provider: LLMProvider
    if mode == "mock":
        provider = MockLLM()
    elif mode == "gemini":
        if not settings.gemini_api_key:
            raise _missing_key_error()
        provider = GeminiLLM(settings.gemini_api_key, settings.gemini_model)
    else:  # auto
        if settings.gemini_api_key:
            provider = GeminiLLM(settings.gemini_api_key, settings.gemini_model)
        else:
            logger.warning("GEMINI_API_KEY not set — using offline mock LLM provider.")
            provider = MockLLM()
    _provider_cache.clear()
    _provider_cache[cache_key] = provider
    return provider


def _missing_key_error() -> AIProviderError:
    from app.core.errors import AIErrorCode

    return AIProviderError(AIErrorCode.INVALID_API_KEY, "LLM_PROVIDER=gemini but GEMINI_API_KEY is empty")


def clear_provider_cache() -> None:
    _provider_cache.clear()
