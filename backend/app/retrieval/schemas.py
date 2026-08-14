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
class RetrievalTrace:
    """Sanitized component-level information for a hybrid retrieval request."""

    dense_executed: bool = False
    dense_candidate_count: int = 0
    dense_error: str | None = None
    bm25_executed: bool = False
    bm25_candidate_count: int = 0
    bm25_error: str | None = None
    fusion_candidate_count: int = 0
    neighbor_expansion_executed: bool = False
    reranker_executed: bool = False
    reranker_input_count: int = 0
    reranker_output_count: int = 0
    final_evidence_count: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "retrieval_mode": "hybrid",
            "dense": {
                "executed": self.dense_executed,
                "candidate_count": self.dense_candidate_count,
                "error": self.dense_error,
            },
            "bm25": {
                "executed": self.bm25_executed,
                "candidate_count": self.bm25_candidate_count,
                "error": self.bm25_error,
            },
            "fusion": {"candidate_count": self.fusion_candidate_count},
            "neighbor_expansion": {"executed": self.neighbor_expansion_executed},
            "reranker": {
                "executed": self.reranker_executed,
                "input_count": self.reranker_input_count,
                "output_count": self.reranker_output_count,
            },
            "final_evidence_count": self.final_evidence_count,
        }


@dataclass(frozen=True)
class RetrievalResult:
    evidence: tuple[Evidence, ...]
    state: AnswerState
    fallback_reason: str | None = None
    trace: RetrievalTrace = field(default_factory=RetrievalTrace)
