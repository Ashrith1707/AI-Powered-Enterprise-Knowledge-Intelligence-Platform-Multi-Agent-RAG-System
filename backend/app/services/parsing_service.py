"""Turns a stored file into a list of cleaned page texts.

PDF   -> PyMuPDF text layer, OCR fallback per page
DOCX  -> python-docx paragraphs (single logical page)
TXT   -> raw read
IMAGE -> OCR
"""
from pathlib import Path

from app.core.exceptions import ProcessingError
from app.services.ocr_service import OCRService
from app.services.text_cleaning import clean_text, word_count

MIN_TEXT_CHARS = 30  # below this a PDF page is treated as scanned


class ParsingService:
    def __init__(self, ocr: OCRService | None = None):
        self.ocr = ocr or OCRService()

    def parse(self, stored_path: str, file_type: str) -> tuple[list[dict], bool]:
        """Returns (pages, used_ocr). Each page dict matches the Page model."""
        path = Path(stored_path)
        if not path.exists():
            raise ProcessingError(f"Stored file missing: {stored_path}")
        if file_type == "pdf":
            return self._parse_pdf(path)
        if file_type == "docx":
            return self._parse_docx(path), False
        if file_type == "txt":
            return self._parse_txt(path), False
        if file_type == "image":
            return self._parse_image(path)
        raise ProcessingError(f"No parser for file type '{file_type}'.")

    def _parse_pdf(self, path: Path) -> tuple[list[dict], bool]:
        import fitz
        pages, used_ocr = [], False
        with fitz.open(path) as doc:
            for i, page in enumerate(doc, start=1):
                text = page.get_text("text")
                ocr_applied = False
                if len(text.strip()) < MIN_TEXT_CHARS:
                    text = self.ocr.pdf_page_to_text(page)
                    ocr_applied = bool(text.strip())
                    used_ocr = used_ocr or ocr_applied
                cleaned = clean_text(text)
                pages.append({"page_number": i, "text": cleaned,
                              "ocr_applied": ocr_applied,
                              "word_count": word_count(cleaned)})
        return pages, used_ocr

    def _parse_docx(self, path: Path) -> list[dict]:
        import docx
        document = docx.Document(str(path))
        text = "\n".join(p.text for p in document.paragraphs)
        for table in document.tables:
            for row in table.rows:
                text += "\n" + " | ".join(cell.text for cell in row.cells)
        cleaned = clean_text(text)
        return [{"page_number": 1, "text": cleaned, "ocr_applied": False,
                 "word_count": word_count(cleaned)}]

    def _parse_txt(self, path: Path) -> list[dict]:
        cleaned = clean_text(path.read_text(encoding="utf-8", errors="replace"))
        return [{"page_number": 1, "text": cleaned, "ocr_applied": False,
                 "word_count": word_count(cleaned)}]

    def _parse_image(self, path: Path) -> tuple[list[dict], bool]:
        text = self.ocr.image_bytes_to_text(path.read_bytes())
        cleaned = clean_text(text)
        return ([{"page_number": 1, "text": cleaned, "ocr_applied": True,
                  "word_count": word_count(cleaned)}], True)
