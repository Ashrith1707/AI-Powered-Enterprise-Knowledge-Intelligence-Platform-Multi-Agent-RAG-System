"""Unit tests for the individual agents (planner, reranker, compressor, verifier, citation validator)."""
from __future__ import annotations

import asyncio

import pytest

from app.agents.base import PipelineContext, UserInfo
from app.agents.citation_validator import CitationValidationAgent, parse_markers
from app.agents.compressor import ContextCompressionAgent, is_near_duplicate, select_relevant_sentences
from app.agents.planner import PlannerAgent
from app.agents.reranker import LexicalCompositeReranker
from app.agents.schemas import (
    CompressedContext,
    Evidence,
    GeneratedAnswer,
    MetadataDecision,
    RankedChunk,
    RetrievedChunk,
)
from app.agents.verifier import VerificationAgent, split_claims, verify_lexical


def _ctx(query: str = "test query") -> PipelineContext:
    return PipelineContext(request_id="t-1", user=UserInfo(id=1, email="t@t.dev"), query=query)


def _chunk(cid: int, content: str, score: float = 0.5, **kw) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=cid, document_id=kw.get("document_id", 1),
        document_title=kw.get("title", "Doc"), filename=kw.get("filename", "doc.txt"),
        page_start=kw.get("page_start", 1), page_end=kw.get("page_end", 1),
        content=content, score=score, sources=kw.get("sources", ["vector"]),
        vector_score=kw.get("vector_score"), keyword_score=kw.get("keyword_score"),
    )


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------
def test_planner_knowledge_intent(env):
    ctx = _ctx("What are the safety requirements for machine maintenance?")
    step = asyncio.run(PlannerAgent().execute(ctx))
    assert step.status.value == "completed"
    plan = ctx.plan
    assert plan.intent == "knowledge_retrieval"
    assert plan.requires_retrieval is True
    assert plan.strategy == "hybrid"
    assert plan.top_k >= 4
    assert ctx.query in plan.sub_queries


def test_planner_smalltalk(env):
    ctx = _ctx("hello")
    asyncio.run(PlannerAgent().execute(ctx))
    assert ctx.plan.intent == "conversational"
    assert ctx.plan.requires_retrieval is False


def test_planner_analytics(env):
    ctx = _ctx("How many documents have I uploaded?")
    asyncio.run(PlannerAgent().execute(ctx))
    assert ctx.plan.intent == "analytics"
    assert ctx.plan.requires_retrieval is False


def test_planner_metadata_hints(env):
    ctx = _ctx("What does the HR leave policy from 2024 say about carry over?")
    asyncio.run(PlannerAgent().execute(ctx))
    plan = ctx.plan
    assert plan.requires_metadata_filter is True
    assert plan.filters.get("year_min") == 2024


def test_planner_dynamic_top_k_grows_with_complexity(env):
    simple = _ctx("What is the password policy?")
    asyncio.run(PlannerAgent().execute(simple))
    complex_q = _ctx(
        "Compare the safety requirements for machine maintenance and the emergency stop "
        "procedures, and also explain who is authorized to perform maintenance and what "
        "personal protective equipment is required on the production floor overall?"
    )
    asyncio.run(PlannerAgent().execute(complex_q))
    assert complex_q.plan.top_k > simple.plan.top_k


def test_planner_never_executes_code(env):
    """Prompt-injection style input must be treated as plain text."""
    ctx = _ctx("import os; os.system('rm -rf /')  # what does the policy say?")
    asyncio.run(PlannerAgent().execute(ctx))
    assert ctx.plan is not None
    assert ctx.plan.intent in ("knowledge_retrieval", "analytics", "conversational")


# ---------------------------------------------------------------------------
# Reranker
# ---------------------------------------------------------------------------
def test_reranker_prefers_lexically_relevant_chunk():
    strategy = LexicalCompositeReranker()
    chunks = [
        _chunk(1, "The annual budget report discusses quarterly financial results and revenue.", vector_score=0.31),
        _chunk(2, "Machine maintenance requires lockout tagout before servicing any machine.", vector_score=0.28),
    ]
    ranked = strategy.rerank("What are the safety requirements for machine maintenance?", chunks)
    assert ranked[0][0].chunk_id == 2
    assert ranked[0][1] > ranked[1][1]


def test_reranker_absolute_scores_enable_refusal():
    """Completely unrelated chunks must score below the relevance floor."""
    from app.config import get_settings

    strategy = LexicalCompositeReranker()
    chunks = [_chunk(1, "Recipes for chocolate cake and birthday parties with frosting.", vector_score=0.05)]
    ranked = strategy.rerank("What are the safety requirements for machine maintenance?", chunks)
    assert ranked[0][1] < get_settings().min_relevance_score


def test_reranker_phrase_bonus():
    strategy = LexicalCompositeReranker()
    chunks = [
        _chunk(1, "The policy mentions net-30 payment timing for invoices generally.", vector_score=0.2),
        _chunk(2, 'Standard payment terms for all vendors are "net-30 days" from invoice receipt.', vector_score=0.2),
    ]
    ranked = strategy.rerank('What are the "net-30 days" payment terms?', chunks)
    assert ranked[0][0].chunk_id == 2


# ---------------------------------------------------------------------------
# Compressor
# ---------------------------------------------------------------------------
def test_near_duplicate_detection():
    text = "The machine must be locked out before maintenance. " * 4
    dupe = "The machine must be locked out before maintenance. " * 4
    different = "Annual leave is 24 days per calendar year for all employees."
    assert is_near_duplicate(text, dupe, 0.8)
    assert not is_near_duplicate(text, different, 0.8)


def test_sentence_selection_prefers_relevant():
    content = (
        "The cafeteria menu changes weekly. Machine maintenance requires lockout tagout. "
        "Parking is available near the east gate. Maintenance personnel must isolate energy sources."
    )
    # Budget smaller than the full content forces relevance-based selection
    selected = select_relevant_sentences(content, ["maintenance", "lockout", "machine"], max_chars=120)
    assert "lockout" in selected.lower()
    assert "maintenance" in selected.lower()
    assert "cafeteria" not in selected.lower()
    assert "parking" not in selected.lower()
    assert len(selected) <= 120


def test_compressor_dedups_and_keeps_citation_metadata(env):
    ctx = _ctx("machine maintenance safety")
    chunk_a = _chunk(1, "Machine maintenance requires lockout tagout before servicing any machine. " * 3,
                     document_id=5, title="Safety Manual", page_start=3, page_end=4)
    chunk_b = _chunk(2, "Machine maintenance requires lockout tagout before servicing any machine. " * 3,
                     document_id=5, title="Safety Manual", page_start=3, page_end=4)
    ctx.ranked = [
        RankedChunk(**chunk_a.model_dump(), rerank_score=0.8, rerank_method="lexical-composite-v2"),
        RankedChunk(**chunk_b.model_dump(), rerank_score=0.75, rerank_method="lexical-composite-v2"),
    ]
    asyncio.run(ContextCompressionAgent().execute(ctx))
    assert ctx.compressed is not None
    assert len(ctx.compressed.evidences) == 1
    assert ctx.compressed.removed_duplicates == 1
    ev = ctx.compressed.evidences[0]
    # citation metadata fully preserved
    assert ev.chunk_id == 1 and ev.document_id == 5 and ev.page_start == 3 and ev.page_end == 4
    assert ev.evidence_id == "E1"


def test_compressor_drops_everything_below_floor(env):
    ctx = _ctx("rocket launch procedure")
    ctx.ranked = [
        RankedChunk(**_chunk(1, "Cake recipes and party planning guidance.").model_dump(),
                    rerank_score=0.1, rerank_method="lexical-composite-v2"),
    ]
    asyncio.run(ContextCompressionAgent().execute(ctx))
    assert ctx.compressed.evidences == []


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------
def _evidence(eid: str, text: str) -> Evidence:
    return Evidence(
        evidence_id=eid, chunk_id=1, document_id=1, document_title="Doc", filename="doc.txt",
        page_start=1, page_end=1, text=text, score=0.9,
        original_chars=len(text), compressed_chars=len(text),
    )


def test_verifier_passes_grounded_answer():
    evidence = [_evidence("E1", "Full-time employees are entitled to 24 days of paid annual leave per year.")]
    result = verify_lexical(
        "Employees receive 24 days of paid annual leave per year [E1].", evidence
    )
    assert result.verified is True
    assert result.confidence > 0.6
    assert result.unsupported_claims == []


def test_verifier_flags_hallucinated_claim():
    evidence = [_evidence("E1", "Annual leave is 24 days per year. Sick leave is 10 days per year.")]
    result = verify_lexical(
        "Annual leave is 24 days [E1]. The company also provides a free helicopter to every employee [E1].",
        evidence,
    )
    assert result.verified is False
    assert any("helicopter" in c for c in result.unsupported_claims)


def test_verifier_detects_contradiction():
    evidence = [_evidence("E1", "Hearing protection is required in zones above 85 decibels.")]
    result = verify_lexical("Hearing protection is not required in any zone [E1].", evidence)
    assert result.verified is False
    assert result.contradictions


def test_claim_splitting_skips_meta_lines():
    claims = split_claims(
        "Based on the retrieved enterprise documents:\n"
        "- Employees receive 24 days of annual leave [E1].\n"
        "(Answer produced in offline mock mode — configure GEMINI_API_KEY.)"
    )
    assert any("24 days" in c for c in claims)
    assert not any("mock mode" in c for c in claims)


def test_verification_agent_insufficient_evidence_is_safe(env):
    ctx = _ctx("anything")
    ctx.answer = GeneratedAnswer(text="The available documents do not contain enough information.",
                                 insufficient_evidence=True, provider="mock")
    asyncio.run(VerificationAgent().execute(ctx))
    assert ctx.verification.verified is True
    assert ctx.verification.method == "insufficient-evidence-safe-path"


# ---------------------------------------------------------------------------
# Citation validator
# ---------------------------------------------------------------------------
def test_parse_markers():
    assert parse_markers("A claim [E1] and more [E2, E3].") == ["E1", "E2", "E3"]
    assert parse_markers("No citations here.") == []


def test_citation_validator_removes_fake_citations(env):
    ctx = _ctx("leave policy")
    ctx.candidates = [_chunk(1, "Annual leave is 24 days.", document_id=9)]
    ctx.authorized_document_ids = [9]
    ctx.compressed = CompressedContext(
        evidences=[_evidence("E1", "Annual leave is 24 days per year.")],
        total_chars=30, budget_chars=6000,
    )
    ctx.compressed.evidences[0].chunk_id = 1
    ctx.compressed.evidences[0].document_id = 9
    ctx.answer = GeneratedAnswer(
        text="Employees get 24 days of leave [E1]. The board approved 99 extra holidays [E7].",
        provider="mock",
    )
    asyncio.run(CitationValidationAgent().execute(ctx))
    result = ctx.citation_validation
    assert result.citations_found == 2
    assert result.citations_valid == 1
    assert result.removed_citations and result.removed_citations[0]["marker"] == "E7"
    assert "[E7]" not in result.cleaned_text
    assert "[E1]" in result.cleaned_text
    citation = result.valid_citations[0]
    assert citation.document_id == 9 and citation.chunk_id == 1 and citation.quote


def test_citation_validator_rejects_unauthorized_document(env):
    ctx = _ctx("leave")
    ctx.candidates = [_chunk(1, "content", document_id=9)]
    ctx.authorized_document_ids = [42]  # evidence points at a doc the user lost access to
    ctx.compressed = CompressedContext(evidences=[_evidence("E1", "some text")])
    ctx.compressed.evidences[0].document_id = 9
    ctx.compressed.evidences[0].chunk_id = 1
    ctx.answer = GeneratedAnswer(text="Something claimed [E1].", provider="mock")
    asyncio.run(CitationValidationAgent().execute(ctx))
    assert ctx.citation_validation.citations_valid == 0
    assert "[E1]" not in ctx.citation_validation.cleaned_text
