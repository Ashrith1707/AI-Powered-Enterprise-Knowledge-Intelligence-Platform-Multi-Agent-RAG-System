"""Metadata extraction (heuristic + embedded document info).

Deterministic and fast: title/author/dates from embedded PDF/DOCX metadata,
department/category inference from keyword dictionaries, tags from term
frequency. No schema changes needed — everything lands in
``Document.metadata_json``.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.services.parsing import ParsedDocument

DEPARTMENT_KEYWORD_MAP: Dict[str, List[str]] = {
    "Human Resources": ["employee", "leave", "hr", "recruitment", "onboarding", "payroll", "performance review", "code of conduct"],
    "Engineering": ["engineering", "architecture", "deployment", "api", "system design", "sprint", "code review", "ci/cd"],
    "Operations": ["maintenance", "machine", "safety", "operation", "shift", "equipment", "production line", "lockout"],
    "Finance": ["invoice", "budget", "reimbursement", "financial", "audit", "expense", "quarterly"],
    "IT Security": ["security policy", "password", "access control", "encryption", "phishing", "incident response", "vpn", "mfa"],
    "Legal": ["contract", "liability", "compliance", "terms", "agreement", "regulation", "gdpr"],
    "Sales": ["customer", "sales", "crm", "pipeline", "quota", "prospect"],
}

CATEGORY_KEYWORD_MAP: Dict[str, List[str]] = {
    "policy": ["policy", "guideline", "standard", "procedure", "must", "shall", "prohibited"],
    "manual": ["manual", "how to", "step 1", "instructions", "guide", "operating"],
    "report": ["report", "summary of findings", "quarter", "analysis", "metrics"],
    "contract": ["contract", "agreement", "parties", "clause", "effective date"],
    "specification": ["specification", "requirement", "shall comply", "technical standard"],
}

_STOPWORDS = set(
    """the a an and or of to in for on with by is are was were be been being this that these those it its as at from
    into over under between within without may might must shall should will would can could have has had do does did
    not no but if then than too very just about above after before during while each all any both few more most other
    some such only own same so s t don now i you he she we they them his her their our your""".split()
)

_DATE_RE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b",
    re.IGNORECASE,
)
_VERSION_RE = re.compile(r"\b(?:version|rev\.?|v)\s*\.?\s*(\d+(?:\.\d+)*)", re.IGNORECASE)
_DOC_ID_RE = re.compile(r"\b([A-Z]{2,6}-\d{3,8})\b")


def extract_metadata(
    parsed: ParsedDocument,
    fallback_title: str,
) -> Dict[str, object]:
    text = parsed.full_text
    lower = text.lower()
    info = parsed.info or {}

    title = _pick_title(info.get("title"), text, fallback_title)
    author = info.get("author") or _guess_author(text)
    dates = _DATE_RE.findall(text[:5000])
    version = _VERSION_RE.search(text[:5000])
    doc_ids = _DOC_ID_RE.findall(text[:8000])

    metadata: Dict[str, object] = {
        "title": title,
        "author": author,
        "subject": info.get("subject"),
        "keywords": info.get("keywords"),
        "creator_tool": info.get("creator"),
        "document_date": _normalize_date(dates[0]) if dates else None,
        "dates_mentioned": [_normalize_date(d) for d in dates[:10]],
        "version": version.group(1) if version else None,
        "document_ids": sorted(set(doc_ids))[:5],
        "department": _score_keyword_map(lower, DEPARTMENT_KEYWORD_MAP),
        "category": (
            _category_from_title(str(title), fallback_title)
            or _score_keyword_map(lower, CATEGORY_KEYWORD_MAP)
            or _guess_from_extension(fallback_title)
        ),
        "tags": _top_tags(text, k=8),
        "language": "en" if re.search(r"\b(the|and|of)\b", lower) else None,
        "parser": parsed.parser,
        "ocr_used": parsed.ocr_attempted,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }
    return metadata


_TITLE_CATEGORY_WORDS = {
    "manual": ["manual", "handbook"],
    "policy": ["policy", "policies", "standard", "guideline"],
    "report": ["report", "review", "findings"],
    "contract": ["contract", "agreement"],
    "specification": ["specification", "spec"],
    "guide": ["guide", "how-to"],
}


def _category_from_title(title: str, filename: str) -> Optional[str]:
    """Category words in the title/filename are a stronger signal than body counts."""
    haystack = f"{title} {filename}".lower()
    for category, words in _TITLE_CATEGORY_WORDS.items():
        if any(re.search(rf"\b{re.escape(w)}\b", haystack) for w in words):
            return category
    return None


def _pick_title(embedded: Optional[str], text: str, fallback: str) -> str:
    if embedded and embedded.strip():
        return embedded.strip()[:200]
    # First non-trivial line of the body is often the title.
    for line in text.splitlines()[:12]:
        line = line.strip()
        if 3 < len(line) <= 160 and not line.endswith((".", ",", ":")) and sum(c.isalpha() for c in line) > len(line) * 0.5:
            return line
    return re.sub(r"\.[^.]+$", "", fallback)[:200]


def _guess_author(text: str) -> Optional[str]:
    m = re.search(r"(?i)\b(?:author|prepared by|written by|by)\s*[:\-]\s*([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})", text[:4000])
    return m.group(1).strip() if m else None


def _normalize_date(raw: str) -> str:
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return raw


def _score_keyword_map(lower_text: str, keyword_map: Dict[str, List[str]]) -> Optional[str]:
    scores = {
        label: sum(lower_text.count(kw) for kw in keywords)
        for label, keywords in keyword_map.items()
    }
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] >= 3 else None


def _guess_from_extension(filename: str) -> str:
    return "document"


def _top_tags(text: str, k: int = 8) -> List[str]:
    words = re.findall(r"[A-Za-z][a-z]{3,}", text.lower())
    counter = Counter(w for w in words if w not in _STOPWORDS)
    # Prefer capitalized candidate terms from the original text (likely domain terms)
    caps = Counter(re.findall(r"\b[A-Z][a-z]{3,}\b", text))
    ranked = counter.most_common(k * 3)
    tags: List[str] = []
    for word, _count in ranked:
        cap_form = next((c for c in caps if c.lower() == word), None)
        tags.append(cap_form or word)
        if len(tags) >= k:
            break
    return tags
