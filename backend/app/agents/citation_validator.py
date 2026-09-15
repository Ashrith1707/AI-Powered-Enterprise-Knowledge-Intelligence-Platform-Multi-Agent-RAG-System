"""AGENT 8 — Citation Validation Agent.

Responsibility: guarantee that every citation in the final answer maps to
REAL retrieved evidence:
* parse [E#] markers from the answer;
* validate each marker against the compressed evidence pool and the actual
  retrieval candidates (chunk exists, belongs to an authorized document,
  page numbers come from the chunk record — never from the model);
* remove invalid citations from the text (never invent replacements);
* emit the final citation list with document/page/chunk provenance and quotes.
"""
from __future__ import annotations

import asyncio
import re
from typing import Dict, List, Tuple

from app.agents.base import BaseAgent, PipelineContext
from app.agents.schemas import Citation, CitationValidationResult
from app.core.logging_conf import get_logger

logger = get_logger("citation_validator")

_MARKER_RE = re.compile(r"\[\s*(E\d+(?:\s*,\s*E\d+)*)\s*\]")
_SENT_RE = re.compile(r"(?<=[.!?])\s+")


def parse_markers(text: str) -> List[str]:
    """Return every evidence id referenced in the text (in order, deduped)."""
    found: List[str] = []
    for group in _MARKER_RE.findall(text):
        for part in group.split(","):
            part = part.strip()
            if part and part not in found:
                found.append(part)
    return found


class CitationValidationAgent(BaseAgent):
    name = "citation_validator"
    description = "Validates that all citations map to real retrieved evidence; removes invalid ones."
    timeout_seconds = 10.0

    async def run(self, ctx: PipelineContext) -> Tuple[str, Dict[str, object]]:
        result = await asyncio.to_thread(self._validate, ctx)
        ctx.citation_validation = result
        if ctx.answer is not None:
            ctx.answer.text = result.cleaned_text

        summary = (
            f"Citations: {result.citations_valid}/{result.citations_found} valid"
            + (f", {len(result.removed_citations)} removed (not backed by evidence)."
               if result.removed_citations else ".")
        )
        return summary, {
            "citations_found": result.citations_found,
            "citations_valid": result.citations_valid,
            "citations_removed": len(result.removed_citations),
            "uncited_sentences": result.uncited_sentences,
        }

    def _validate(self, ctx: PipelineContext) -> CitationValidationResult:
        answer = ctx.answer
        text = answer.text if answer else ""
        evidences = {ev.evidence_id: ev for ev in (ctx.compressed.evidences if ctx.compressed else [])}
        candidate_ids = {c.chunk_id for c in ctx.candidates}
        authorized_docs = set(ctx.authorized_document_ids)

        referenced = parse_markers(text)
        valid_citations: List[Citation] = []
        removed: List[Dict[str, object]] = []
        valid_ids: set = set()

        for evidence_id in referenced:
            ev = evidences.get(evidence_id)
            ok = (
                ev is not None
                and ev.chunk_id in candidate_ids           # really was retrieved
                and (not authorized_docs or ev.document_id in authorized_docs)  # still authorized
            )
            if ok and ev is not None:
                valid_ids.add(evidence_id)
                valid_citations.append(
                    Citation(
                        citation_id=f"C{len(valid_citations) + 1}",
                        evidence_id=ev.evidence_id,
                        document_id=ev.document_id,
                        document_title=ev.document_title,
                        filename=ev.filename,
                        page_start=ev.page_start,
                        page_end=ev.page_end,
                        chunk_id=ev.chunk_id,
                        quote=ev.text[:220] + ("…" if len(ev.text) > 220 else ""),
                    )
                )
            else:
                removed.append({"marker": evidence_id, "reason": "no matching retrieved evidence"})

        # Rewrite text: strip invalid markers, normalize valid ones to [E#].
        def _replace(match: re.Match) -> str:
            ids = [p.strip() for p in match.group(1).split(",")]
            keep = [i for i in ids if i in valid_ids]
            return f" [{', '.join(keep)}]" if keep else ""

        cleaned = _MARKER_RE.sub(_replace, text)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()

        # Informational: factual sentences lacking any citation
        uncited = 0
        for sentence in _SENT_RE.split(cleaned):
            s = sentence.strip()
            if len(s.split()) >= 6 and not _MARKER_RE.search(s) and not s.startswith("("):
                uncited += 1

        if removed:
            logger.warning(
                "Removed %d invalid citation marker(s) request_id=%s markers=%s",
                len(removed), ctx.request_id, [r["marker"] for r in removed],
            )

        return CitationValidationResult(
            cleaned_text=cleaned,
            valid_citations=valid_citations,
            removed_citations=removed,
            citations_found=len(referenced),
            citations_valid=len(valid_citations),
            uncited_sentences=uncited,
        )
