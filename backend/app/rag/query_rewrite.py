"""Query analysis / rewriting for retrieval (Module 5).

Deterministic core (always available) with optional LLM enhancement:

* expand_query_variants — multi-query retrieval variants (original +
  keyword-focused + decomposed sub-questions).
* detect_metadata_hints — surface metadata filters implicit in the question
  (year/date, document type words, department words) for the Planner /
  Metadata Agent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.services.embeddings import tokenize

_TYPE_HINTS: Dict[str, List[str]] = {
    "policy": ["policy", "policies", "guideline", "rules"],
    "manual": ["manual", "handbook", "guide", "instructions"],
    "report": ["report", "audit findings", "quarterly review"],
    "contract": ["contract", "agreement", "sla"],
    "specification": ["specification", "spec", "requirements document"],
}

_DEPARTMENT_HINTS: Dict[str, List[str]] = {
    "Human Resources": ["hr", "human resources", "employee handbook", "leave policy", "recruitment"],
    "Operations": ["maintenance", "machine", "plant", "factory floor", "safety"],
    "IT Security": ["security", "infosec", "cyber", "password policy", "access control"],
    "Finance": ["finance", "budget", "invoice", "reimbursement", "expense"],
    "Engineering": ["engineering", "development", "deployment", "api design"],
    "Legal": ["legal", "compliance", "liability", "contract terms"],
}

_YEAR_RE = re.compile(r"\b(20\d{2}|19\d{2})\b")
_SPLIT_RE = re.compile(r"\s+(?:and|also|plus)\s+|\?|\s+;\s+", re.IGNORECASE)

_STOPWORDS = set(
    "the a an and or of to in is are was were be what which who how why when where do does did can could should would "
    "i you we they it its for on with about regarding tell me please explain describe list give".split()
)


@dataclass
class QueryAnalysis:
    original: str
    variants: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    hints: Dict[str, object] = field(default_factory=dict)


def detect_metadata_hints(query: str) -> Dict[str, object]:
    """Extract implicit metadata filters from the question text."""
    lower = query.lower()
    hints: Dict[str, object] = {}

    years = [int(y) for y in _YEAR_RE.findall(query)]
    if years:
        hints["year_min"] = min(years)
        hints["year_max"] = max(years)

    for category, words in _TYPE_HINTS.items():
        if any(re.search(rf"\b{re.escape(w)}\b", lower) for w in words):
            hints["category"] = category
            break

    for department, words in _DEPARTMENT_HINTS.items():
        if any(re.search(rf"\b{re.escape(w)}\b", lower) for w in words):
            hints["department"] = department
            break

    quoted = re.findall(r'"([^"]{3,80})"', query) or re.findall(r"'([^']{3,80})'", query)
    if quoted:
        hints["exact_phrase"] = quoted[0]

    return hints


def extract_keywords(query: str, limit: int = 8) -> List[str]:
    tokens = [t for t in tokenize(query) if t not in _STOPWORDS and len(t) > 2]
    seen: List[str] = []
    for t in tokens:
        if t not in seen:
            seen.append(t)
    return seen[:limit]


def expand_query_variants(query: str, max_variants: int = 3) -> List[str]:
    """Build retrieval variants for multi-query retrieval.

    Deterministic: original + keyword-compressed form + sub-questions split
    on conjunctions. (The Answer Generator never uses variants; only the
    Retriever does, and results are de-duplicated by chunk id.)
    """
    variants: List[str] = [query.strip()]
    keywords = extract_keywords(query)
    if keywords and len(keywords) >= 2:
        keyword_variant = " ".join(keywords)
        if keyword_variant.lower() != query.strip().lower():
            variants.append(keyword_variant)

    parts = [p.strip(" ?,.") for p in _SPLIT_RE.split(query) if p and len(p.strip(" ?,.")) > 12]
    if len(parts) > 1:
        for part in parts[:max_variants]:
            if part not in variants:
                variants.append(part)

    return variants[:max_variants]


def analyze_query(query: str) -> QueryAnalysis:
    return QueryAnalysis(
        original=query.strip(),
        variants=expand_query_variants(query),
        keywords=extract_keywords(query),
        hints=detect_metadata_hints(query),
    )


def rewrite_with_llm(query: str, llm_generate) -> Optional[List[str]]:
    """Optional LLM-based expansion (used only when a real LLM is configured).

    Returns None on any failure so callers fall back to the deterministic
    variants — rewriting must never break retrieval.
    """
    prompt = (
        "You are a search query rewriter for an enterprise RAG system.\n"
        f"Original question: {query!r}\n"
        "Produce up to 3 alternative search queries that would retrieve the same "
        "information using different wording. Output one query per line, no numbering, "
        "no commentary."
    )
    try:
        result = llm_generate(prompt)
        lines = [l.strip(" -•\t") for l in result.text.splitlines() if l.strip()]
        lines = [l for l in lines if l.lower() != query.strip().lower()][:3]
        return lines or None
    except Exception:  # noqa: BLE001 — never fatal
        return None
