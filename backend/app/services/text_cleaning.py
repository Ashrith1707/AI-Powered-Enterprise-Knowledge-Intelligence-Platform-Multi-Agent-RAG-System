"""Normalizes raw extracted text before it is stored or chunked."""
import re
import unicodedata


def clean_text(raw: str) -> str:
    if not raw:
        return ""
    text = unicodedata.normalize("NFKC", raw)
    text = text.replace("\x00", "")
    text = re.sub(r"-\n(\w)", r"\1", text)          # de-hyphenate line breaks
    text = re.sub(r"[ \t]+", " ", text)              # collapse spaces
    text = re.sub(r"\n{3,}", "\n\n", text)           # collapse blank lines
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def word_count(text: str) -> int:
    return len(text.split())
