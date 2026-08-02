"""Docling adapter. Parser details do not leak into upload or retrieval code."""

import hashlib
from dataclasses import dataclass
from pathlib import Path


class DocumentParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedDocument:
    markdown: str
    content_hash: str


def parse_to_markdown(path: Path, filename: str) -> ParsedDocument:
    extension = Path(filename).suffix.lower()
    try:
        if extension in {".md", ".txt"}:
            markdown = path.read_text(encoding="utf-8")
        else:
            from docling.document_converter import DocumentConverter

            result = DocumentConverter().convert(path)
            markdown = result.document.export_to_markdown()
    except UnicodeDecodeError as exc:
        raise DocumentParseError("text document is not valid UTF-8") from exc
    except Exception as exc:
        raise DocumentParseError("document parsing failed") from exc
    markdown = markdown.replace("\r\n", "\n").replace("\r", "\n")
    if not markdown.strip():
        raise DocumentParseError("document did not contain extractable text")
    return ParsedDocument(markdown=markdown, content_hash=hashlib.sha256(markdown.encode()).hexdigest())
