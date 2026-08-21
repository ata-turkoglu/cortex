"""Generation-bound adapter over the existing BM25 and Qdrant workspace rebuild."""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from ..retrieval.indexing import IndexingSummary
from .pipeline import CorpusSnapshot, StageResult


@dataclass(frozen=True)
class RetrievalProjectionResult:
    bm25: StageResult
    dense_qdrant: StageResult


class WorkspaceRetrievalProjection:
    """Rebuild both active-corpus projections once and expose immutable stage outputs."""

    def __init__(self, rebuild: Callable[[str], IndexingSummary]) -> None:
        self.rebuild = rebuild
        self._results: dict[tuple[str, str], RetrievalProjectionResult] = {}

    def build(self, snapshot: CorpusSnapshot, generation_id: str) -> RetrievalProjectionResult:
        key = (snapshot.workspace_id, generation_id)
        if key in self._results:
            return self._results[key]
        summary = self.rebuild(snapshot.workspace_id)
        if summary.workspace_id != snapshot.workspace_id:
            raise ValueError("retrieval projection returned a different workspace")
        material = f"{generation_id}:{snapshot.fingerprint}:{summary.embedding_config_hash}"
        fingerprint = hashlib.sha256(material.encode()).hexdigest()
        result = RetrievalProjectionResult(
            StageResult(
                generation_id,
                snapshot.fingerprint,
                f"bm25:{fingerprint}",
                {"chunk_count": summary.chunk_count},
            ),
            StageResult(
                generation_id,
                snapshot.fingerprint,
                f"dense_qdrant:{fingerprint}",
                {
                    "chunk_count": summary.chunk_count,
                    "embedding_config_hash": summary.embedding_config_hash,
                },
            ),
        )
        self._results[key] = result
        return result
