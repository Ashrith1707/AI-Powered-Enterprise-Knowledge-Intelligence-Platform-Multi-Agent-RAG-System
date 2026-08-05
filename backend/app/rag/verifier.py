"""Source-grounded answer verification (deterministic, LLM-free).

For every sentence in the answer that cites a block [n], we check whether the
sentence's content words actually appear in the cited chunk. Sentences that
fail are flagged as potentially hallucinated. Produces:

  faithfulness  — supported cited sentences / cited sentences
  uncited_claims — factual-looking sentences with no citation
  calibrated confidence — retrieval quality + faithfulness + citation coverage
"""
import re

from app.rag.bm25 import tokenize

MARKER_RE = re.compile(r"\[(\d+)\]")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
REFUSAL_PHRASE = "does not contain enough information"

STOP = set("""the a an and or of to in on for with is are was were be been this that
it its as by from at not no yes can could should would may might will have has had""".split())


def _content_words(text: str) -> set:
    return {t for t in tokenize(text) if t not in STOP}


def verify_answer(answer: str, chunks: list) -> dict:
    if REFUSAL_PHRASE in answer:
        return {"refused": True, "faithfulness": 1.0, "supported": 0,
                "cited_sentences": 0, "uncited_claims": 0, "flagged": []}

    sentences = [s.strip() for s in SENTENCE_RE.split(answer) if s.strip()]
    cited_sentences = 0
    supported = 0
    uncited_claims = 0
    flagged = []

    for sentence in sentences:
        markers = [int(m) for m in MARKER_RE.findall(sentence)]
        words = _content_words(MARKER_RE.sub("", sentence))
        if not markers:
            # Heuristic: sentences with numbers/entities but no citation are claims.
            if len(words) >= 4 and re.search(r"\d|[A-Z][a-z]{2,}", sentence):
                uncited_claims += 1
            continue
        cited_sentences += 1
        cited_text = " ".join(
            chunks[n - 1].text for n in markers if 1 <= n <= len(chunks))
        overlap = len(words & _content_words(cited_text)) / len(words) if words else 1.0
        if overlap >= 0.3 or len(words) < 4:
            supported += 1
        else:
            flagged.append(sentence[:120])

    faithfulness = supported / cited_sentences if cited_sentences else 0.0
    return {"refused": False, "faithfulness": round(faithfulness, 3),
            "supported": supported, "cited_sentences": cited_sentences,
            "uncited_claims": uncited_claims, "flagged": flagged}


def calibrated_confidence(quality: dict, verification: dict,
                          citation_count: int) -> float:
    """Blends retrieval quality, groundedness and citation coverage into a
    score the UI can display honestly."""
    if verification["refused"]:
        return 0.0
    retrieval_part = min(1.0, 0.6 * quality.get("term_coverage", 0)
                         + 0.4 * min(1.0, quality.get("top_score", 0) * 2))
    citation_part = min(1.0, citation_count / 3)
    score = (0.3 * retrieval_part
             + 0.45 * verification["faithfulness"]
             + 0.25 * citation_part)
    # Uncited factual claims drag confidence down.
    score -= 0.05 * min(3, verification["uncited_claims"])
    return round(max(0.0, min(1.0, score)), 2)
