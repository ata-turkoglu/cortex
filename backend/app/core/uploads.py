"""Upload validation and storage. Uploaded bytes are never executed or unpacked."""

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

SUPPORTED_EXTENSIONS = {".md", ".txt", ".docx", ".pdf"}
TEXT_TYPES = {"text/plain", "text/markdown", "application/octet-stream"}


class UploadValidationError(ValueError):
    pass


@dataclass(frozen=True)
class StoredUpload:
    original_filename: str
    storage_path: Path
    sha256: str
    size_bytes: int
    media_type: str


def normalized_filename(filename: str) -> str:
    normalized = unicodedata.normalize("NFC", filename).replace("\\", "/")
    if "/" in normalized or not normalized or normalized in {".", ".."} or ".." in normalized:
        raise UploadValidationError("invalid filename")
    name = normalized
    safe = re.sub(r"[^\w. -]", "_", name, flags=re.UNICODE).strip(". ")
    if not safe:
        raise UploadValidationError("invalid filename")
    return safe


def validate_upload(filename: str, media_type: str | None, prefix: bytes) -> tuple[str, str]:
    name = normalized_filename(filename)
    extension = Path(name).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UploadValidationError("unsupported file format")
    supplied_type = (media_type or "application/octet-stream").lower()
    if extension == ".pdf" and not prefix.startswith(b"%PDF-"):
        raise UploadValidationError("file content is not a PDF")
    if extension == ".docx" and not prefix.startswith(b"PK\x03\x04"):
        raise UploadValidationError("file content is not a DOCX archive")
    if extension in {".md", ".txt"} and supplied_type not in TEXT_TYPES:
        raise UploadValidationError("invalid MIME type for text document")
    return name, extension


def store_upload(
    destination: Path, filename: str, media_type: str | None, content: bytes, maximum_size: int
) -> StoredUpload:
    if len(content) > maximum_size:
        raise UploadValidationError("file exceeds the configured upload limit")
    safe_name, extension = validate_upload(filename, media_type, content[:8])
    destination.mkdir(parents=True, exist_ok=True)
    target = (destination / f"{uuid4().hex}{extension}").resolve()
    root = destination.resolve()
    if root not in target.parents:
        raise UploadValidationError("unsafe storage path")
    target.write_bytes(content)
    return StoredUpload(
        original_filename=safe_name,
        storage_path=target,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        media_type=(media_type or "application/octet-stream").lower(),
    )
