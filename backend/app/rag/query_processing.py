"""Query understanding: type analysis, conversation-aware rewriting, and
LLM-gated expansion (multi-query + HyDE).

LLM steps run ONLY when Gemini is configured; otherwise they are skipped and
the pipeline reports that honestly in its trace — never simulated.
"""
import re

from app.core.config import settings
from app.core.logging_config import get_logger
from app.rag.bm25 import tokenize

logger = get_logger("query")

LIST_HINTS = ("list", "enumerate", "what are", "which", "all the")
SUMMARY_HINTS = ("summarize", "summary", "overview", "key points", "tl;dr")
COMPARE_HINTS = ("compare", "difference", "versus", " vs ", "better")
FOLLOWUP_PRONOUNS = re.compile(r"\b(it|its|this|that|they|them|those|these|he|she)\b", re.I)


def analyze(question: str) -> dict:
    q = question.lower()
    if any(h in q for h in SUMMARY_HINTS):
        qtype = "summary"
    elif any(h in q for h in COMPARE_HINTS):
        qtype = "comparison"
    elif any(h in q for h in LIST_HINTS):
        qtype = "list"
    else:
        qtype = "factual"
    return {"type": qtype, "terms": tokenize(question)}


def history_aware_query(question: str, prior_user_messages: list[str]) -> str:
    """Deterministic follow-up resolution: short or pronoun-heavy questions
    borrow key terms from the previous user turn so retrieval has a subject.
    ('What about its revenue?' after 'Tell me about Infosys' -> +infosys)"""
    if not prior_user_messages:
        return question
    is_followup = len(tokenize(question)) <= 4 or FOLLOWUP_PRONOUNS.search(question)
    if not is_followup:
        return question
    prev_terms = tokenize(prior_user_messages[-1])
    current = set(tokenize(question))
    borrowed = [t for t in prev_terms if t not in current][:6]
    if not borrowed:
        return question
    return f"{question} ({' '.join(borrowed)})"


def llm_expansions(question: str, max_variants: int = 2) -> list[str]:
    """Multi-query rewriting via Gemini. Returns [] when no key or on error."""
    if not settings.gemini_api_key:
        return []
    try:
        from app.rag.llm_client import generate
        raw = generate(
            "Rewrite the following search query in "
            f"{max_variants} different ways that preserve its meaning but use "
            "different words. Return ONLY the rewrites, one per line, no numbering.\n\n"
            f"Query: {question}")
        variants = [line.strip("-• ").strip() for line in raw.split("\n") if line.strip()]
        return [v for v in variants if len(v) > 5][:max_variants]
    except Exception as exc:
        logger.warning("Query expansion skipped: %s", exc)
        return []


def hyde_document(question: str) -> str | None:
    """HyDE: a hypothetical answer used as an extra dense-retrieval probe.
    Returns None when the LLM is unavailable."""
    if not settings.gemini_api_key:
        return None
    try:
        from app.rag.llm_client import generate
        return generate(
            "Write a short factual paragraph (3 sentences max) that would "
            f"plausibly answer this question:\n{question}")
    except Exception as exc:
        logger.warning("HyDE skipped: %s", exc)
        return None


def summarize_history(messages: list[dict], trigger_after: int = 12) -> str | None:
    """Memory summarization for long chats (LLM-gated). Returns a compact
    summary string used as retrieval context, or None."""
    if len(messages) < trigger_after or not settings.gemini_api_key:
        return None
    try:
        from app.rag.llm_client import generate
        transcript = "\n".join(f"{m['role']}: {m['content'][:200]}" for m in messages[-12:])
        return generate("Summarize this conversation in 2 sentences, keeping "
                        f"names, entities and topics:\n{transcript}")
    except Exception as exc:
        logger.warning("History summarization skipped: %s", exc)
        return None
