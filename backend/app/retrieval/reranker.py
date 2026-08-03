"""Local BGE reranking boundary.

Weights are loaded only from the local Sentence Transformers cache. Cortex never
downloads a reranker during a retrieval request.
"""
from dataclasses import replace
from typing import Protocol

from .schemas import Evidence


class EvidenceReranker(Protocol):
    def rerank(self, query: str, evidence: list[Evidence], limit: int) -> list[Evidence]: ...


class RerankerUnavailable(RuntimeError):
    pass


class LocalBGEReranker:
    def __init__(self, model_name: str | None, device: str | None = None) -> None:
        self.model_name = model_name
        self.device = device
        self._model = None

    def _load(self):
        if not self.model_name:
            raise RerankerUnavailable("local_reranker_not_configured")
        if self._model is None:
            from sentence_transformers import CrossEncoder

            try:
                self._model = CrossEncoder(
                    self.model_name,
                    device=self.device,
                    local_files_only=True,
                )
            except OSError as error:
                raise RerankerUnavailable("local_reranker_model_unavailable") from error
        return self._model

    def rerank(self, query: str, evidence: list[Evidence], limit: int) -> list[Evidence]:
        if limit < 1:
            raise ValueError("limit must be positive")
        candidates = evidence[:limit]
        if not candidates:
            return []
        scores = self._load().predict([(query, item.content) for item in candidates])
        return [
            replace(item, score=float(score))
            for item, score in sorted(
                zip(candidates, scores, strict=True), key=lambda pair: float(pair[1]), reverse=True
            )
        ]
