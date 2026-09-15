"""AGENT 7 — Verification Agent.

Responsibility: check whether the generated answer is actually supported by
the evidence:
* split the answer into claims (sentences);
* score each claim against the evidence pool (lexical entailment: content-word
  coverage + best-sentence similarity);
* detect contradictions (negation mismatch against the best-matching evidence);
* compute confidence, evidence coverage and a verified flag.

Method is deterministic by default (``lexical-entailment-v1``). An optional
LLM judge can be enabled with VERIFICATION_USE_LLM=true when a real Gemini
provider is configured (never with the offline mock — that would be fake
verification).

On failure the orchestrator either regenerates once with stronger evidence
instructions or falls back to a safe insufficient-evidence response. Retries
are bounded — no infinite loops.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Dict, List, Optional, Tuple

from app.agents.base import BaseAgent, PipelineContext
from app.agents.schemas import ClaimCheck, VerificationResult
from app.rag.query_rewrite import extract_keywords
from app.services.embeddings import tokenize

_SENT_RE = re.compile(r"(?<=[.!?])\s+")
_CITATION_RE = re.compile(r"\[(E\d+(?:\s*,\s*E\d+)*)\]")
_NEGATIONS = {"not", "no", "never", "none", "cannot", "can't", "don't", "doesn't", "isn't", "aren't", "without", "prohibited", "forbidden"}

_META_LINE_RE = re.compile(
    r"(answer produced in offline mock mode|based on the retrieved enterprise documents"
    r"|here is what they say|configure gemini_api_key)",
    re.IGNORECASE,
)


def split_claims(answer: str) -> List[str]:
    """Split answer text into verifiable claims (skip meta/preamble lines)."""
    # Filter boilerplate at LINE level first so meta lines fused with content
    # (no terminal punctuation) don't hide real claims.
    content_lines = [line for line in answer.splitlines() if not _META_LINE_RE.search(line)]
    text = " ".join(l.strip() for l in content_lines if l.strip())

    candidates: List[str] = []
    for raw in _SENT_RE.split(text):
        sentence = raw.strip().lstrip("-•* ").strip()
        if not sentence or len(sentence) < 12:
            continue
        if _META_LINE_RE.search(sentence):
            continue
        # strip citation markers for analysis, keep the claim text
        sentence = _CITATION_RE.sub("", sentence).strip()
        if len(sentence.split()) >= 3:
            candidates.append(sentence)
    return candidates


def _content_words(text: str) -> set:
    from app.rag.query_rewrite import _STOPWORDS  # reuse the same stopword list

    return {t for t in tokenize(text) if t not in _STOPWORDS and len(t) > 2}


def _best_sentence_match(claim: str, evidence_sentences: List[str]) -> Tuple[float, str]:
    claim_words = _content_words(claim)
    if not claim_words:
        return 0.0, ""
    best_score, best_sentence = 0.0, ""
    for sentence in evidence_sentences:
        sent_words = _content_words(sentence)
        if not sent_words:
            continue
        overlap = len(claim_words & sent_words)
        score = overlap / max(1, len(claim_words)) * 0.7 + overlap / max(1, len(sent_words)) * 0.3
        if score > best_score:
            best_score, best_sentence = score, sentence
    return best_score, best_sentence


def _negation_set(text: str) -> set:
    return {t for t in tokenize(text) if t in _NEGATIONS} or {
        w for w in text.lower().split() if w.strip(".,!?") in _NEGATIONS
    }


def verify_lexical(answer: str, evidences: List) -> VerificationResult:
    evidence_sentences: List[str] = []
    for ev in evidences:
        evidence_sentences.extend(s.strip() for s in _SENT_RE.split(ev.text) if s.strip())

    claims = split_claims(answer)
    if not claims:
        # No verifiable claims (e.g. refusal message) — treat refusal as verified-safe.
        return VerificationResult(
            verified=True,
            confidence=0.9 if not evidences else 0.7,
            method="lexical-entailment-v1",
            evidence_coverage=0.0,
            supported_ratio=1.0,
        )

    checks: List[ClaimCheck] = []
    unsupported: List[str] = []
    contradictions: List[str] = []
    used_evidence: set = set()

    for claim in claims:
        score, best = _best_sentence_match(claim, evidence_sentences)
        supported = score >= 0.55
        # contradiction heuristic: high lexical overlap but negation mismatch
        if best and score >= 0.4:
            claim_neg = _negation_set(claim)
            ev_neg = _negation_set(best)
            if bool(claim_neg) != bool(ev_neg) and score >= 0.5:
                contradictions.append(claim)
                supported = False
        if supported:
            for ev in evidences:
                if best and best in ev.text:
                    used_evidence.add(ev.evidence_id)
        else:
            unsupported.append(claim)
        checks.append(
            ClaimCheck(
                claim=claim[:300],
                supported=supported,
                support_score=round(score, 3),
                best_evidence=[best[:200]] if best else [],
            )
        )

    supported_count = sum(1 for c in checks if c.supported)
    supported_ratio = supported_count / len(checks)
    coverage = len(used_evidence) / len(evidences) if evidences else 0.0
    confidence = round(0.75 * supported_ratio + 0.25 * min(1.0, coverage * 2), 3)
    verified = supported_ratio >= 0.8 and not contradictions

    return VerificationResult(
        verified=verified,
        confidence=confidence,
        unsupported_claims=unsupported,
        contradictions=contradictions,
        evidence_coverage=round(coverage, 3),
        supported_ratio=round(supported_ratio, 3),
        method="lexical-entailment-v1",
        claim_checks=checks,
    )


def verify_with_llm(answer: str, evidences: List) -> Optional[VerificationResult]:
    """Optional LLM-judge verification. Returns None when unavailable."""
    from app.services.llm import MockLLM, get_llm_provider

    provider = get_llm_provider()
    if isinstance(provider, MockLLM):
        return None  # never pretend the mock judged itself

    evidence_text = "\n\n".join(f"[{ev.evidence_id}] {ev.text}" for ev in evidences)
    prompt = (
        "<EVIDENCE>\n" + evidence_text + "\n</EVIDENCE>\n\n"
        "<ANSWER>\n" + answer + "\n</ANSWER>\n\n"
        "Check whether every factual claim in the ANSWER is supported by the EVIDENCE. "
        'Reply with ONLY JSON: {"verified": bool, "confidence": 0.0-1.0, '
        '"unsupported_claims": ["..."], "contradictions": ["..."]}.'
    )
    try:
        result = provider.generate(prompt, system_instruction="You are a strict fact-checking engine. Output JSON only.",
                                   temperature=0.0, max_output_tokens=500)
        match = re.search(r"\{.*\}", result.text, re.DOTALL)
        if not match:
            return None
        data = json.loads(match.group())
        return VerificationResult(
            verified=bool(data.get("verified", False)),
            confidence=float(data.get("confidence", 0.0)),
            unsupported_claims=[str(c)[:300] for c in data.get("unsupported_claims", [])][:10],
            contradictions=[str(c)[:300] for c in data.get("contradictions", [])][:10],
            method="llm-judge-v1",
        )
    except Exception as exc:  # noqa: BLE001
        logger_warning = exc
        return None


class VerificationAgent(BaseAgent):
    name = "verifier"
    description = "Checks factual grounding of the answer against the evidence; detects unsupported claims."
    timeout_seconds = 30.0

    async def run(self, ctx: PipelineContext) -> Tuple[str, Dict[str, object]]:
        answer = ctx.answer
        if answer is None:
            ctx.verification = VerificationResult(verified=False, confidence=0.0,
                                                  unsupported_claims=["No answer was generated."])
            return "No answer to verify.", {"verified": False}

        if answer.insufficient_evidence:
            ctx.verification = VerificationResult(
                verified=True,
                confidence=1.0,
                method="insufficient-evidence-safe-path",
                supported_ratio=1.0,
            )
            return "Answer is an honest insufficient-evidence response — safe by construction.", {
                "verified": True, "method": "insufficient-evidence-safe-path",
            }

        if ctx.extra.get("canned_response"):
            ctx.verification = VerificationResult(
                verified=True,
                confidence=1.0,
                method="system-response",
                supported_ratio=1.0,
            )
            return "System-generated response (no claims requiring evidence).", {
                "verified": True, "method": "system-response",
            }

        evidences = (ctx.compressed.evidences if ctx.compressed else [])
        result = await asyncio.to_thread(self._verify, answer.text, evidences)
        ctx.verification = result

        summary = (
            f"Verification {'PASSED' if result.verified else 'FAILED'} "
            f"(confidence={result.confidence:.2f}, supported={result.supported_ratio:.0%}, "
            f"unsupported={len(result.unsupported_claims)}, contradictions={len(result.contradictions)}) "
            f"via {result.method}."
        )
        return summary, {
            "verified": result.verified,
            "confidence": result.confidence,
            "supported_ratio": result.supported_ratio,
            "unsupported_claims": len(result.unsupported_claims),
            "contradictions": len(result.contradictions),
            "evidence_coverage": result.evidence_coverage,
            "method": result.method,
        }

    def _verify(self, answer_text: str, evidences: List) -> VerificationResult:
        if self._settings.verification_use_llm:
            llm_result = verify_with_llm(answer_text, evidences)
            if llm_result is not None:
                return llm_result
        return verify_lexical(answer_text, evidences)
