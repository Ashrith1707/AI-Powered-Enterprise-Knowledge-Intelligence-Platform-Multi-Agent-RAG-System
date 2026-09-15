"""Lightweight entity extraction (deterministic, regex/statistical NER-lite).

Extracts: person-like names, organizations, dates, emails, monetary amounts,
percentages and reference codes. Results land in ``Document.entities_json``
and feed the Metadata Agent's filters and analytics.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_MONEY_RE = re.compile(r"(?:USD|EUR|GBP|INR|\$|€|£|₹)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:million|billion|k|cr|lakh))?")
_PERCENT_RE = re.compile(r"\b\d{1,3}(?:\.\d+)?\s?%")
_DATE_RE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+\d{4})\b"
)
_ORG_RE = re.compile(
    r"\b([A-Z][A-Za-z&.\-]*(?:\s+[A-Z][A-Za-z&.\-]*){0,4}\s+"
    r"(?:Inc|LLC|Ltd|Limited|Corp|Corporation|GmbH|Pvt|Private Limited|Technologies|Systems|Group|Industries|Foundation|Institute|University|Department|Ministry|Agency|Committee))\b"
)
_REF_CODE_RE = re.compile(r"\b(?:ISO|IEC|RFC|NIST|SOP|DOC|POL|STD)[\s-]?\d{2,6}(?:-\d+)?\b")
_PERSON_RE = re.compile(
    r"\b((?:Mr|Mrs|Ms|Dr|Prof|Eng)\.?\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})\b"
)
_CAPS_ORG_RE = re.compile(r"\b([A-Z]{2,6})\b")

_GENERIC = {"THE", "AND", "FOR", "NOT", "WITH", "THIS", "THAT", "FROM", "ISO"}


def extract_entities(text: str, limit: int = 15) -> Dict[str, List[str]]:
    sample = text[:120_000]  # bound work on huge documents

    persons = _dedup(_PERSON_RE.findall(sample), limit)
    orgs = _dedup(_ORG_RE.findall(sample), limit)
    acronyms = [
        a for a, c in Counter(_CAPS_ORG_RE.findall(sample)).most_common(limit)
        if a not in _GENERIC and c >= 2
    ]
    emails = _dedup(_EMAIL_RE.findall(sample), limit)
    money = _dedup(_MONEY_RE.findall(sample), limit)
    percentages = _dedup(_PERCENT_RE.findall(sample), limit)
    dates = _dedup(_DATE_RE.findall(sample), limit)
    references = _dedup(_REF_CODE_RE.findall(sample), limit)

    return {
        "persons": persons,
        "organizations": sorted(set(orgs + acronyms))[:limit],
        "emails": emails,
        "monetary_values": money,
        "percentages": percentages,
        "dates": dates,
        "reference_codes": references,
    }


def _dedup(items: List[str], limit: int) -> List[str]:
    seen: Dict[str, None] = {}
    for item in items:
        key = item.strip()
        if key and key not in seen:
            seen[key] = None
        if len(seen) >= limit:
            break
    return list(seen.keys())
