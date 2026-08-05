"""Rule-based metadata extraction: title, keywords, entities, summary."""
import re
from collections import Counter

STOPWORDS = set("""a an and are as at be by for from has have in is it its of on or that the
this to was were will with we you your our their not can may shall must such other than then
these those there which who whom into over under between about after before during each per
also more most any all been being do does did done how what when where why but if no yes
""".split())

DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
AMOUNT_RE = re.compile(r"(?:\$|₹|€|£|USD|INR|EUR)\s?[\d,]+(?:\.\d+)?", re.IGNORECASE)
PHONE_RE = re.compile(r"\+?\d[\d\s-]{8,14}\d")


class MetadataService:
    def extract(self, filename: str, pages: list[dict]) -> dict:
        full_text = "\n".join(p["text"] for p in pages)
        return {
            "title": self._title(filename, pages),
            "author": "",
            "language": "en",
            "keywords": self._keywords(full_text),
            "entities": {
                "dates": sorted(set(DATE_RE.findall(full_text)))[:20],
                "emails": sorted(set(EMAIL_RE.findall(full_text)))[:20],
                "amounts": sorted(set(AMOUNT_RE.findall(full_text)))[:20],
                "phones": sorted(set(PHONE_RE.findall(full_text)))[:10],
            },
            "summary": self._lead_summary(full_text),
        }

    def _title(self, filename: str, pages: list[dict]) -> str:
        if pages and pages[0]["text"]:
            first_line = pages[0]["text"].split("\n", 1)[0].strip()
            if 5 <= len(first_line) <= 150:
                return first_line
        stem = filename.rsplit(".", 1)[0]
        return stem.replace("_", " ").replace("-", " ").strip()

    def _keywords(self, text: str, top_n: int = 10) -> list[str]:
        words = re.findall(r"[a-zA-Z]{4,}", text.lower())
        counts = Counter(w for w in words if w not in STOPWORDS)
        return [word for word, _ in counts.most_common(top_n)]

    def _lead_summary(self, text: str, max_chars: int = 400) -> str:
        lead = " ".join(text.split())[:max_chars]
        return lead + ("..." if len(text) > max_chars else "")
