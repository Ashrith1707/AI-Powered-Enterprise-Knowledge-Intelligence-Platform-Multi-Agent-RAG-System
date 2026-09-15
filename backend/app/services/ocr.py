"""OCR service (Tesseract via pytesseract) with honest capability reporting.

* Images (png/jpg/tiff): OCR directly with Pillow + pytesseract.
* Scanned PDFs: rendered page-by-page with pdf2image/poppler when available.
* If the tesseract binary is missing, OCR is reported as unavailable and the
  document status explains exactly what is missing — never a silent failure.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from app.config import get_settings
from app.core.errors import DocumentProcessingError
from app.core.logging_conf import get_logger

logger = get_logger("ocr")


@dataclass
class OCRCapability:
    tesseract_available: bool
    tesseract_path: Optional[str]
    pdf_rendering_available: bool  # poppler + pdf2image for scanned PDFs
    languages: List[str]


def _tesseract_path() -> Optional[str]:
    settings = get_settings()
    candidate = settings.tesseract_cmd or "tesseract"
    return shutil.which(candidate)


def _pdf_render_available() -> bool:
    try:
        import pdf2image  # noqa: F401
    except ImportError:
        return False
    return shutil.which("pdftoppm") is not None


def get_ocr_capability() -> OCRCapability:
    path = _tesseract_path()
    languages: List[str] = []
    if path:
        try:
            import pytesseract

            langs = pytesseract.get_languages(config="")
            languages = list(langs)
        except Exception:  # noqa: BLE001
            languages = []
    return OCRCapability(
        tesseract_available=path is not None,
        tesseract_path=path,
        pdf_rendering_available=_pdf_render_available(),
        languages=languages,
    )


def ocr_image_file(path: Path) -> str:
    """Run OCR on an image file; raises if tesseract is unavailable."""
    capability = get_ocr_capability()
    if not capability.tesseract_available:
        raise DocumentProcessingError(
            "This document requires OCR but Tesseract is not installed on the server. "
            "Install tesseract-ocr (or set TESSERACT_CMD) and reprocess the document.",
        )
    import pytesseract
    from PIL import Image

    logger.info("Running OCR on image %s", path.name)
    with Image.open(path) as img:
        text = pytesseract.image_to_string(img)
    return text.strip()


def ocr_scanned_pdf(path: Path, progress_cb=None) -> List[str]:
    """OCR a scanned PDF page by page. Returns list of page texts (1-based order)."""
    capability = get_ocr_capability()
    if not capability.tesseract_available:
        raise DocumentProcessingError(
            "This PDF appears to be scanned (no embedded text) and requires OCR, but "
            "Tesseract is not installed on the server. Install tesseract-ocr (or set "
            "TESSERACT_CMD) and reprocess the document.",
        )
    if not capability.pdf_rendering_available:
        raise DocumentProcessingError(
            "This PDF appears to be scanned and requires OCR, but PDF page rendering "
            "(poppler-utils + pdf2image) is not installed on the server. Install "
            "poppler-utils and pip install pdf2image, then reprocess the document.",
        )
    import pytesseract
    from pdf2image import convert_from_path

    logger.info("Rendering scanned PDF for OCR: %s", path.name)
    images = convert_from_path(str(path), dpi=200)
    pages: List[str] = []
    for i, img in enumerate(images, start=1):
        pages.append(pytesseract.image_to_string(img).strip())
        if progress_cb:
            progress_cb(i, len(images))
    return pages
