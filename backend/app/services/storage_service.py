"""Validates uploads and writes them to disk with content-hash names."""
import hashlib
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import ValidationError

FILE_TYPE_MAP = {".pdf": "pdf", ".docx": "docx", ".txt": "txt",
                 ".png": "image", ".jpg": "image", ".jpeg": "image"}


class StorageService:
    def validate(self, filename: str, content: bytes) -> str:
        """Returns the logical file type or raises ValidationError."""
        ext = Path(filename).suffix.lower()
        if ext not in settings.allowed_extensions:
            raise ValidationError(
                f"Unsupported file type '{ext}'. Allowed: {', '.join(settings.allowed_extensions)}")
        max_bytes = settings.max_upload_mb * 1024 * 1024
        if len(content) == 0:
            raise ValidationError("Uploaded file is empty.")
        if len(content) > max_bytes:
            raise ValidationError(f"File exceeds {settings.max_upload_mb} MB limit.")
        return FILE_TYPE_MAP[ext]

    def checksum(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def save(self, filename: str, content: bytes) -> Path:
        """Stores as <sha256>_<original-name> to avoid collisions."""
        digest = self.checksum(content)[:16]
        safe_name = Path(filename).name.replace(" ", "_")
        target = settings.storage_dir / f"{digest}_{safe_name}"
        target.write_bytes(content)
        return target

    def delete(self, stored_path: str) -> None:
        path = Path(stored_path)
        if path.exists():
            path.unlink()
