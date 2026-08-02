"""Deterministic Markdown chunking with heading and neighbor context."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkDraft:
    ordinal: int
    content: str
    heading: str | None


def chunk_markdown(markdown: str, token_limit: int, overlap: int) -> list[ChunkDraft]:
    if token_limit < 1 or overlap < 0 or overlap >= token_limit:
        raise ValueError("invalid chunk settings")
    heading = None
    paragraphs: list[tuple[str | None, str]] = []
    for block in re.split(r"\n\s*\n", markdown.strip()):
        if block.startswith("#"):
            first, *rest = block.splitlines()
            heading = first.lstrip("#").strip() or None
            block = "\n".join(rest).strip()
        if block:
            paragraphs.append((heading, block))
    drafts: list[ChunkDraft] = []
    words: list[str] = []
    active_heading = None
    for block_heading, block in paragraphs:
        block_words = block.split()
        if words and len(words) + len(block_words) > token_limit:
            drafts.append(ChunkDraft(len(drafts), " ".join(words), active_heading))
            words = words[-overlap:] if overlap else []
        active_heading = block_heading or active_heading
        while len(block_words) > token_limit:
            prefix = words + block_words[: token_limit - len(words)]
            drafts.append(ChunkDraft(len(drafts), " ".join(prefix), active_heading))
            words = prefix[-overlap:] if overlap else []
            block_words = block_words[token_limit - len(words) :]
        words.extend(block_words)
    if words:
        drafts.append(ChunkDraft(len(drafts), " ".join(words), active_heading))
    return drafts
