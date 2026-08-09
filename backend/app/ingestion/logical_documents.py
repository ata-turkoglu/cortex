"""Split normalized Markdown into first-class Heading 2 documents."""

import re
from dataclasses import dataclass
from pathlib import Path

from .parsers import ParsedDocument

HEADING_2 = re.compile(r"^##(?!#)\s+(?P<title>\S.*)\s*$")


@dataclass(frozen=True)
class LogicalDocumentDraft:
    ordinal: int
    document_code: str
    title: str
    document_type: str
    source_original: str
    page_start: int | None
    page_end: int | None
    markdown: str


def _document_type(title: str, markdown: str, fallback_type: str) -> str:
    searchable = f"{title}\n{markdown[:500]}".casefold()
    for terms, detected_type in (
        (("tapu", "malik", "mal sahibi"), "tapu"),
        (("veraset", "miras"), "veraset"),
        (("nüfus", "nufus"), "nüfus kaydı"),
        (("mahkeme", "dava"), "dava"),
    ):
        if any(term in searchable for term in terms):
            return detected_type
    return fallback_type


def detect_logical_documents(
    parsed: ParsedDocument, source_original: str, document_type: str
) -> tuple[LogicalDocumentDraft, ...]:
    """Split only at Markdown level-2 headings, matching KnowledgeOS."""
    lines = parsed.markdown.splitlines()
    boundaries = [
        (index, match.group("title").strip())
        for index, line in enumerate(lines)
        if (match := HEADING_2.fullmatch(line)) is not None
    ]
    if not boundaries:
        fallback = Path(source_original).stem
        return (
            LogicalDocumentDraft(
                0,
                fallback,
                fallback,
                document_type,
                source_original,
                1 if parsed.total_pages else None,
                parsed.total_pages,
                parsed.markdown.strip(),
            ),
        )

    drafts = []
    for ordinal, (start, heading) in enumerate(boundaries):
        end = boundaries[ordinal + 1][0] if ordinal + 1 < len(boundaries) else len(lines)
        markdown = "\n".join(lines[start:end]).strip()
        page_start = (
            parsed.heading2_pages[ordinal][1]
            if ordinal < len(parsed.heading2_pages) and parsed.heading2_pages[ordinal][0] == heading
            else None
        )
        next_page = None
        if ordinal + 1 < len(boundaries) and ordinal + 1 < len(parsed.heading2_pages):
            next_heading, next_page_candidate = parsed.heading2_pages[ordinal + 1]
            if next_heading == boundaries[ordinal + 1][1]:
                next_page = next_page_candidate
        page_end = None
        if page_start and next_page:
            page_end = max(page_start, next_page - 1)
        elif page_start:
            page_end = parsed.total_pages or page_start
        drafts.append(
            LogicalDocumentDraft(
                ordinal,
                heading,
                heading,
                _document_type(heading, markdown, document_type),
                source_original,
                page_start,
                page_end,
                markdown,
            )
        )
    return tuple(drafts)
