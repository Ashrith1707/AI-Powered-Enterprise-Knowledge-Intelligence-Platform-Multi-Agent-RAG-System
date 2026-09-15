"""Conversation memory abstraction (Module 5 / 13).

Goals:
* bounded context — never send the whole conversation to the LLM forever;
* rolling summary — old turns are compressed into ``Conversation.summary``
  (LLM-summarized when Gemini is available, extractive otherwise);
* recency window — the last N messages are always included verbatim.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.logging_conf import get_logger
from app.models import Conversation, Message

logger = get_logger("memory")


@dataclass
class MemoryContext:
    summary: str
    recent_messages: List[dict]   # [{"role": "user"|"assistant", "content": str}]
    total_messages: int
    truncated: bool


def build_memory_context(
    session: Session,
    conversation: Optional[Conversation],
    max_messages: Optional[int] = None,
    max_chars: Optional[int] = None,
) -> MemoryContext:
    settings = get_settings()
    max_messages = max_messages or settings.memory_recent_messages
    max_chars = max_chars or settings.memory_max_chars

    if conversation is None:
        return MemoryContext(summary="", recent_messages=[], total_messages=0, truncated=False)

    all_messages: List[Message] = list(conversation.messages)
    recent = all_messages[-max_messages:]

    # Character budget: drop oldest of the recent window until we fit.
    budget_messages: List[Message] = []
    used = 0
    for msg in reversed(recent):
        if used + len(msg.content) > max_chars and budget_messages:
            break
        budget_messages.insert(0, msg)
        used += len(msg.content)

    return MemoryContext(
        summary=conversation.summary or "",
        recent_messages=[
            {"role": m.role if m.role != "assistant" else "assistant", "content": m.content}
            for m in budget_messages
        ],
        total_messages=len(all_messages),
        truncated=len(budget_messages) < len(all_messages),
    )


def maybe_summarize_conversation(session: Session, conversation: Conversation) -> bool:
    """Update the rolling summary once the conversation grows past a threshold.

    Uses the configured LLM when available; otherwise falls back to an
    extractive summary (first sentence of each of the last few answers).
    Returns True when the summary was updated.
    """
    settings = get_settings()
    messages: List[Message] = list(conversation.messages)
    last_summarized = conversation.summarized_until_message_id or 0
    new_messages = [m for m in messages if m.id > last_summarized]
    if len(messages) < settings.memory_summarize_every or len(new_messages) < settings.memory_summarize_every // 2:
        return False

    older = [m for m in messages if m.id <= (messages[-settings.memory_recent_messages].id if len(messages) > settings.memory_recent_messages else 0)]
    if not older:
        return False

    transcript = "\n".join(f"{m.role}: {m.content[:500]}" for m in older[-40:])
    summary = _llm_summarize(transcript) or _extractive_summarize(older)

    conversation.summary = (summary or "")[:2000]
    conversation.summarized_until_message_id = older[-1].id
    session.commit()
    logger.info("conversation.summary updated conversation_id=%d chars=%d", conversation.id, len(conversation.summary))
    return True


def _llm_summarize(transcript: str) -> Optional[str]:
    """Summarize with the configured provider; None on any failure/unavailability."""
    from app.services.llm import MockLLM, get_llm_provider

    try:
        provider = get_llm_provider()
        if isinstance(provider, MockLLM):
            return None  # mock summarization adds no value; use extractive
        result = provider.generate(
            prompt=(
                "Summarize this conversation so far in 3-5 bullet points. Keep key facts, "
                "document names and decisions. No preamble.\n\n" + transcript
            ),
            system_instruction="You are a concise summarization engine.",
            temperature=0.1,
            max_output_tokens=300,
        )
        return result.text.strip() or None
    except Exception as exc:  # noqa: BLE001 — memory must never break chat
        logger.warning("LLM summarization failed (%s); using extractive fallback.", exc)
        return None


def _extractive_summarize(messages: List[Message]) -> str:
    lines: List[str] = []
    for m in messages[-12:]:
        content = m.content.strip().replace("\n", " ")
        first_sentence = content.split(". ")[0][:180]
        if first_sentence:
            lines.append(f"- ({m.role}) {first_sentence}")
    return "\n".join(lines[:8])
