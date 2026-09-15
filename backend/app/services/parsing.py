"""Document parsing: PDF / DOCX / TXT / MD / images → page-aware text.

Page-aware extraction is essential for page-level citations later in the RAG
pipeline. For scanned (image-only) PDFs the parser flags the document for
OCR; OCR is performed by :mod:`app.services.ocr` when tesseract is available.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from app.core.errors import DocumentProcessingError
from app.core.logging_conf import get_logger

logger = get_logger("parsing")

# Average characters per page below this ⇒ likely a scanned document.
# Genuine scans extract ~0 chars/page; sparse-but-real text pages (title-only
# PDFs, forms) usually yield 20+ chars and must not trigger the OCR path.
_SCANNED_CHARS_PER_PAGE = 20


@dataclass
class PageText:
    number: int  # 1-based
    text: str


@dataclass
class ParsedDocument:
    pages: List[PageText] = field(default_factory=list)
    needs_ocr: bool = False
    ocr_attempted: bool = False
    parser: str = ""
    info: dict = field(default_factory=dict)  # embedded PDF metadata etc.

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text.strip())

    @property
    def char_count(self) -> int:
        return sum(len(p.text) for p in self.pages)


def parse_file(path: Path, extension: str) -> ParsedDocument:
    extension = extension.lower().lstrip(".")
    try:
        if extension == "pdf":
            return _parse_pdf(path)
        if extension == "docx":
            return _parse_docx(path)
        if extension in ("txt", "md"):
            return _parse_text(path)
        if extension in ("png", "jpg", "jpeg", "tiff"):
            return _parse_image(path)
    except DocumentProcessingError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Parsing failed for %s", path.name)
        raise DocumentProcessingError(f"Failed to parse '{path.name}': {exc}") from exc
    raise DocumentProcessingError(f"Unsupported file type '.{extension}'.")


# ---------------------------------------------------------------------------
def _parse_pdf(path: Path) -> ParsedDocument:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages: List[PageText] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001 — corrupt page shouldn't kill ingestion
            logger.warning("PDF page %d extraction failed: %s", i, exc)
            text = ""
        pages.append(PageText(number=i, text=_clean(text)))

    info: dict = {}
    try:
        meta = reader.metadata
        if meta:
            info = {
                "title": _md_field(meta.title),
                "author": _md_field(meta.author),
                "subject": _md_field(meta.subject),
                "keywords": _md_field(meta.get("/Keywords")),
                "creator": _md_field(meta.creator),
                "creation_date": str(meta.creation_date) if meta.creation_date else None,
            }
    except Exception:  # noqa: BLE001
        pass

    total_chars = sum(len(p.text) for p in pages)
    needs_ocr = bool(pages) and (total_chars / max(len(pages), 1)) < _SCANNED_CHARS_PER_PAGE
    return ParsedDocument(pages=pages, needs_ocr=needs_ocr, parser="pypdf", info=info)


def _md_field(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_docx(path: Path) -> ParsedDocument:
    import docx  # python-docx

    document = docx.Document(str(path))
    parts: List[str] = []
    for para in document.paragraphs:
        if para.text.strip():
            parts.append(para.text.strip())
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    text = "\n\n".join(parts)
    core = document.core_properties
    info = {
        "title": core.title or None,
        "author": core.author or None,
        "subject": core.subject or None,
        "keywords": core.keywords or None,
        "creation_date": str(core.created) if core.created else None,
    }
    # DOCX has no fixed pagination; treat as one logical page.
    return ParsedDocument(pages=[PageText(1, _clean(text))], parser="python-docx", info=info)


def _parse_text(path: Path) -> ParsedDocument:
    raw = path.read_bytes()
    for encoding in ("utf-8", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover
        raise DocumentProcessingError("Could not decode text file.")
    return ParsedDocument(pages=[PageText(1, _clean(text))], parser="plain-text")


def _parse_image(path: Path) -> ParsedDocument:
    """Images always require OCR."""
    return ParsedDocument(pages=[PageText(1, "")], needs_ocr=True, parser="image")


_WS_RE = re.compile(r"[ \t]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")


def _clean(text: str) -> str:
    text = text.replace("\x00", " ")
    text = _WS_RE.sub(" ", text)
    text = _MULTI_NL_RE.sub("\n\n", text)
    return text.strip()
