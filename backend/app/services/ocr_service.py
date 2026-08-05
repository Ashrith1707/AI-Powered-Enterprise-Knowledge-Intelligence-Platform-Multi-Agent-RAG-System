"""Tesseract OCR wrapper. Used when a PDF page has no extractable text layer."""
import io
from pathlib import Path

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger("ocr")


class OCRService:
    def __init__(self):
        self._available = None

    def available(self) -> bool:
        if self._available is None:
            try:
                import pytesseract
                if Path(settings.tesseract_cmd).exists():
                    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
                pytesseract.get_tesseract_version()
                self._available = True
            except Exception:
                logger.warning("Tesseract not available — scanned pages will be skipped.")
                self._available = False
        return self._available

    def image_bytes_to_text(self, image_bytes: bytes) -> str:
        if not self.available():
            return ""
        import pytesseract
        from PIL import Image
        image = Image.open(io.BytesIO(image_bytes))
        return pytesseract.image_to_string(image)

    def pdf_page_to_text(self, page) -> str:
        """Rasterizes a PyMuPDF page at 2x zoom and OCRs it."""
        if not self.available():
            return ""
        import fitz
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        return self.image_bytes_to_text(pix.tobytes("png"))
