"""Generation-safe adapter for a worker-owned GraphRAG projection build."""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from .pipeline import CorpusSnapshot, StageResult


@dataclass(frozen=True)
class GraphRAGProjectionSummary:
    workspace_id: str
    generation_id: str
    node_count: int
    relationship_count: int


class GenerationBoundGraphRAGProjection:
    def __init__(
        self, build: Callable[[str, str], GraphRAGProjectionSummary]
    ) -> None:
        self.build = build

    def build_for_generation(self, snapshot: CorpusSnapshot, generation_id: str) -> StageResult:
        summary = self.build(snapshot.workspace_id, generation_id)
        if summary.workspace_id != snapshot.workspace_id:
            raise ValueError("GraphRAG projection returned a different workspace")
        if summary.generation_id != generation_id:
            raise ValueError("GraphRAG projection returned a different generation")
        fingerprint = hashlib.sha256(
            f"{generation_id}:{snapshot.fingerprint}:{summary.node_count}:{summary.relationship_count}".encode()
        ).hexdigest()
        return StageResult(
            generation_id,
            snapshot.fingerprint,
            f"graphrag:{fingerprint}",
            {
                "node_count": summary.node_count,
                "relationship_count": summary.relationship_count,
            },
        )
