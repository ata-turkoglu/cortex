from dataclasses import dataclass, field
from enum import Enum


class AnswerState(str, Enum):
    GROUNDED = "grounded"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class Evidence:
    workspace_id: str
    source: str
    content: str
    score: float
    document_id: str | None = None
    document_version_id: str | None = None
    chunk_id: str | None = None
    citation_label: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalResult:
    evidence: tuple[Evidence, ...]
    state: AnswerState
    fallback_reason: str | None = None
