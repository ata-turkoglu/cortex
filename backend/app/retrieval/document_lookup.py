"""Document-oriented shaping for entity and document-list queries."""

import re
from dataclasses import dataclass

from .schemas import Evidence


@dataclass(frozen=True)
class DocumentMatch:
    document_id: str
    document_version_id: str | None
    document_code: str | None
    title: str
    score: float
    matched_chunks: tuple[Evidence, ...]
    page: str | None = None
    source_original: str | None = None
    document_type: str | None = None


def group_evidence_by_document(
    evidence: list[Evidence], *, exact_text: str | None = None
) -> list[DocumentMatch]:
    """Return one ranked result per document while retaining its matching chunks."""
    grouped: dict[str, list[Evidence]] = {}
    for item in evidence:
        if item.document_id:
            grouped.setdefault(item.document_id, []).append(item)

    needle = (exact_text or "").casefold().strip()
    documents: list[DocumentMatch] = []
    for document_id, chunks in grouped.items():
        chunks.sort(
            key=lambda item: (
                needle not in item.content.casefold() if needle else False,
                -item.score,
            )
        )
        best = chunks[0]
        metadata = best.metadata
        has_exact_match = needle and any(
            needle in item.content.casefold() for item in chunks
        )
        exact_bonus = 1.0 if has_exact_match else 0
        documents.append(
            DocumentMatch(
                document_id=document_id,
                document_version_id=best.document_version_id,
                document_code=metadata.get("document_code") or None,
                title=metadata.get("title") or best.source,
                score=max(item.score for item in chunks) + exact_bonus,
                matched_chunks=tuple(chunks),
                page=metadata.get("page") or None,
                source_original=metadata.get("source_original") or None,
                document_type=metadata.get("document_type") or None,
            )
        )
    return sorted(documents, key=lambda item: (-item.score, item.document_code or item.title))


def match_reason(document: DocumentMatch, exact_text: str | None = None) -> str:
    """Produce a compact explanation without copying an entire retrieval chunk."""
    best = document.matched_chunks[0]
    heading = best.metadata.get("heading")
    if heading:
        return heading
    sentences = re.split(r"(?<=[.!?])\s+|\n+", best.content.strip())
    needle = (exact_text or "").casefold().strip()
    sentence = next(
        (part for part in sentences if needle and needle in part.casefold()),
        sentences[0] if sentences else "İlgili ifade belgede geçiyor.",
    )
    return sentence if len(sentence) <= 160 else f"{sentence[:157].rstrip()}…"


def build_document_context(documents: list[DocumentMatch]) -> str:
    """Build LLM context as document blocks rather than anonymous chunk blocks."""
    blocks = []
    for document in documents:
        metadata = {
            "document_id": document.document_id,
            "document_code": document.document_code or "",
            "title": document.title,
            "page": document.page or "",
            "source_original": document.source_original or "",
            "document_type": document.document_type or "",
        }
        matches = "\n".join(f"- {item.content.strip()}" for item in document.matched_chunks)
        blocks.append(
            "Document\n"
            + "\n".join(f"{key}: {value}" for key, value in metadata.items())
            + f"\nmatching_chunks:\n{matches}"
        )
    return "\n\n".join(blocks)
