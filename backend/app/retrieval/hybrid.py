from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from ..core.config import Settings
from .reranker import EvidenceReranker, RerankerUnavailable
from .schemas import AnswerState, Evidence, RetrievalResult
from .sparse import WorkspaceBM25Index


@dataclass(frozen=True)
class RetrievalLimits:
    dense_top_k: int
    bm25_top_k: int
    fusion_candidate_limit: int
    reranker_input_limit: int
    final_evidence_top_k: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "RetrievalLimits":
        values = (
            settings.dense_top_k,
            settings.bm25_top_k,
            settings.fusion_candidate_limit,
            settings.reranker_input_limit,
            settings.final_evidence_top_k,
        )
        if any(value < 1 for value in values):
            raise ValueError("retrieval limits must be positive")
        return cls(*values)


class HybridRetriever:
    """Compose dense and sparse workspace retrieval before GraphRAG is ready."""

    def __init__(
        self,
        dense_search: Callable[[list[float], int], list[Evidence]],
        sparse_index: WorkspaceBM25Index,
        limits: RetrievalLimits,
        reranker: EvidenceReranker | None = None,
    ) -> None:
        self.dense_search = dense_search
        self.sparse_index = sparse_index
        self.limits = limits
        self.reranker = reranker

    def search(
        self,
        query: str,
        query_vector: list[float],
        lookup: dict[str, Evidence] | None = None,
    ) -> RetrievalResult:
        dense = self.dense_search(query_vector, self.limits.dense_top_k)
        sparse = self.sparse_index.search(query, self.limits.bm25_top_k)
        candidates = reciprocal_rank_fusion(dense, sparse, limit=self.limits.fusion_candidate_limit)
        if lookup:
            candidates = parent_neighbor_heading(candidates, lookup)
        fallback_reason = None
        if self.reranker:
            try:
                candidates = self.reranker.rerank(
                    query, candidates, self.limits.reranker_input_limit
                )
            except RerankerUnavailable as error:
                fallback_reason = str(error)
        return result_for(candidates[: self.limits.final_evidence_top_k], fallback_reason)


def reciprocal_rank_fusion(*rankings: list[Evidence], limit: int, k: int = 60) -> list[Evidence]:
    scores: dict[str, float] = defaultdict(float)
    sources: dict[str, Evidence] = {}
    for ranking in rankings:
        for position, item in enumerate(ranking, start=1):
            key = item.chunk_id or f"{item.source}:{item.content}"
            scores[key] += 1 / (k + position)
            sources[key] = item
    return [sources[key] for key in sorted(scores, key=scores.get, reverse=True)[:limit]]


def parent_neighbor_heading(
    evidence: list[Evidence], lookup: dict[str, Evidence]
) -> list[Evidence]:
    """Add contextual chunks without crossing the workspace boundary."""
    expanded: list[Evidence] = []
    seen: set[str] = set()
    for item in evidence:
        item_key = item.chunk_id or f"{item.source}:{item.content}"
        if item_key not in seen:
            expanded.append(item)
            seen.add(item_key)
        related_ids: list[str] = []
        for key in (
            "parent_chunk_id",
            "previous_chunk_id",
            "next_chunk_id",
            "heading_chunk_id",
        ):
            if item.metadata.get(key):
                related_ids.append(item.metadata[key])
        related_ids.extend(item.metadata.get("related_chunk_ids", "").split(","))
        for related_id in related_ids:
            if related_id and related_id in lookup:
                related = lookup[related_id]
                if related.workspace_id != item.workspace_id:
                    continue
                related_key = related.chunk_id or f"{related.source}:{related.content}"
                if related_key not in seen:
                    expanded.append(related)
                    seen.add(related_key)
    return expanded


def result_for(evidence: list[Evidence], fallback_reason: str | None = None) -> RetrievalResult:
    state = AnswerState.GROUNDED if evidence else AnswerState.UNSUPPORTED
    if evidence and fallback_reason:
        state = AnswerState.PARTIAL
    return RetrievalResult(tuple(evidence), state, fallback_reason)
