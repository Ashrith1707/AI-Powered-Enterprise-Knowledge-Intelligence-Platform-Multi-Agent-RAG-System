"""AGENT 1 — Planner Agent.

Responsibility: understand the question and produce an execution Plan:
intent, whether retrieval/metadata filtering is needed, retrieval strategy,
dynamic top-K, sub-queries for multi-query retrieval, and metadata filters.

The planner is deterministic (rule + query-analysis based) and NEVER executes
code or free-form LLM output — its output is validated against the Plan
schema. An optional LLM assist can refine intent, but any failure falls back
to the deterministic plan.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Tuple

from app.agents.base import BaseAgent, PipelineContext
from app.agents.schemas import Plan
from app.rag.query_rewrite import analyze_query

_SMALLTALK = re.compile(
    r"^\s*(hi|hey|hello|good (morning|evening|afternoon)|thanks|thank you|bye|ok(ay)?|who are you|"
    r"what can you do|help)\s*[!.?]*\s*$",
    re.IGNORECASE,
)
_ANALYTICS = re.compile(
    # System-usage questions only ("how many documents…"), NOT document-content
    # questions that happen to start with "how many" ("how many days of leave…").
    r"\b(?:how many|number of|count of|statistics|stats|list)\b.{0,40}"
    r"\b(?:documents?|files?|uploads?|pdfs?|conversations?|questions?|chunks?|users?)\b"
    r"|\bwhat did i (?:upload|ask)\b"
    r"|\brecent (?:activity|uploads)\b"
    r"|\bsystem usage\b",
    re.IGNORECASE | re.DOTALL,
)
_COMPARISON = re.compile(r"\b(compare|versus|vs\.?|difference between|differences)\b", re.IGNORECASE)
_MULTI_QUESTION = re.compile(r"\?.+\?")


class PlannerAgent(BaseAgent):
    name = "planner"
    description = "Analyzes intent and builds the retrieval/generation execution plan."
    timeout_seconds = 10.0

    async def run(self, ctx: PipelineContext) -> Tuple[str, Dict[str, Any]]:
        query = ctx.query.strip()
        settings = self._settings

        # --- Intent ----------------------------------------------------------
        if _SMALLTALK.match(query) and len(query) < 60:
            intent = "conversational"
        elif _ANALYTICS.search(query):
            intent = "analytics"
        else:
            intent = "knowledge_retrieval"

        analysis = analyze_query(query)

        if intent != "knowledge_retrieval":
            ctx.plan = Plan(
                intent=intent,
                requires_retrieval=False,
                requires_metadata_filter=False,
                strategy="none",
                top_k=0,
                sub_queries=[],
                filters={},
                reasoning_summary=f"Classified as {intent}; no document retrieval required.",
            )
            return (
                f"Intent '{intent}' — retrieval not required.",
                {"intent": intent, "requires_retrieval": False, "strategy": "none"},
            )

        # --- Strategy ---------------------------------------------------------
        strategy = "hybrid"
        if analysis.hints.get("exact_phrase"):
            strategy = "hybrid"  # phrase bonus handled by the reranker
        elif len(analysis.keywords) >= 6:
            strategy = "hybrid"

        # --- Dynamic top-K ------------------------------------------------------
        top_k = settings.retrieval_top_k
        complexity = 0
        if len(analysis.variants) > 1:
            complexity += 1
        if _COMPARISON.search(query) or _MULTI_QUESTION.search(query):
            complexity += 2
        if len(query.split()) > 20:
            complexity += 1
        top_k = max(4, min(16, top_k + complexity * 2))

        # --- Metadata filters from query hints ------------------------------------
        filters: Dict[str, Any] = {}
        for key in ("category", "department", "year_min", "year_max", "exact_phrase"):
            if key in analysis.hints:
                filters[key] = analysis.hints[key]
        requires_metadata_filter = bool(filters)

        plan = Plan(
            intent=intent,
            requires_retrieval=True,
            requires_metadata_filter=requires_metadata_filter,
            strategy=strategy,
            top_k=top_k,
            sub_queries=analysis.variants,
            filters=filters,
            reasoning_summary=(
                f"Knowledge question; {len(analysis.variants)} retrieval variant(s); "
                f"strategy={strategy}; top_k={top_k}"
                + (f"; metadata hints: {', '.join(sorted(filters))}" if filters else "")
            ),
        )
        ctx.plan = plan
        ctx.extra["query_analysis"] = {
            "keywords": analysis.keywords,
            "hints": {k: v for k, v in analysis.hints.items()},
        }
        return (
            plan.reasoning_summary,
            {
                "intent": plan.intent,
                "strategy": plan.strategy,
                "top_k": plan.top_k,
                "sub_queries": len(plan.sub_queries),
                "requires_metadata_filter": plan.requires_metadata_filter,
            },
        )
