"""Maps [n] markers in the LLM answer back to real source chunks.

Only citations the model actually used appear in the response, and each
one carries document + page + snippet so the UI can show provenance.
"""
import re

from app.rag.retriever import RetrievedChunk


class CitationEngine:
    MARKER_RE = re.compile(r"\[(\d+)\]")

    def extract(self, answer: str, chunks: list[RetrievedChunk]) -> list[dict]:
        used = []
        seen = set()
        for match in self.MARKER_RE.finditer(answer):
            n = int(match.group(1))
            if n in seen or not (1 <= n <= len(chunks)):
                continue
            seen.add(n)
            chunk = chunks[n - 1]
            used.append({
                "marker": f"[{n}]",
                "document_id": chunk.document_id,
                "document_name": chunk.document_name,
                "page_number": chunk.page_number,
                "snippet": chunk.text[:300],
            })
        return used

    def confidence(self, answer: str, citations: list[dict]) -> float:
        """Heuristic confidence: grounded sentences / refusal detection."""
        if "does not contain enough information" in answer:
            return 0.0
        if not citations:
            return 0.3
        sentences = max(1, answer.count(".") + answer.count("\n"))
        return round(min(1.0, 0.5 + 0.5 * len(citations) / min(sentences, 4)), 2)
