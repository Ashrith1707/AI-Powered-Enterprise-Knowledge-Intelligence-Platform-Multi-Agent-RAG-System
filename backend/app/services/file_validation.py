"""Upload validation: extension allow-list, size limits, magic-byte sniffing.

Files are never executed; they are only parsed. Content type is verified from
magic bytes so a renamed executable/script cannot masquerade as a PDF.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings
from app.core.errors import UploadError

MAGIC_SIGNATURES: dict[str, list[bytes]] = {
    "pdf": [b"%PDF-"],
    "docx": [b"PK\x03\x04"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "tiff": [b"II\x2a\x00", b"MM\x00\x2a"],
}
TEXT_TYPES = {"txt", "md"}


@dataclass
class ValidatedFile:
    extension: str
    size_bytes: int
    is_text_like: bool


def validate_upload(filename: str, content: bytes) -> ValidatedFile:
    settings = get_settings()

    if not filename or "." not in filename:
        raise UploadError("File must have an extension.")
    ext = filename.rsplit(".", 1)[-1].lower()

    if ext not in settings.allowed_extension_set:
        raise UploadError(
            f"File type '.{ext}' is not allowed. Allowed: {sorted(settings.allowed_extension_set)}",
            details={"allowed": sorted(settings.allowed_extension_set)},
        )

    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise UploadError(
            f"File exceeds the {settings.max_upload_mb} MB upload limit.",
            details={"max_mb": settings.max_upload_mb},
        )
    if len(content) == 0:
        raise UploadError("File is empty.")

    if ext in TEXT_TYPES:
        # Must decode as UTF-8 text; reject binary payloads renamed to .txt
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            raise UploadError("File content is not valid UTF-8 text.") from None
        return ValidatedFile(ext, len(content), True)

    if ext == "md":  # pragma: no cover (in TEXT_TYPES above)
        return ValidatedFile(ext, len(content), True)

    signatures = MAGIC_SIGNATURES.get(ext, [])
    head = content[:16]
    if not any(head.startswith(sig) for sig in signatures):
        raise UploadError(
            f"File content does not match a genuine '.{ext}' file (magic-byte check failed). "
            "The upload was rejected for security reasons.",
            details={"extension": ext},
        )

    if ext == "docx":
        # PK zip: ensure it is really a docx (word/ entry) not arbitrary zip
        if b"word/" not in content[: min(len(content), 65536)]:
            raise UploadError("DOCX file is malformed (missing word/ document part).")

    return ValidatedFile(ext, len(content), False)
