from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from ..core.config import Settings
from .reranker import EvidenceReranker, RerankerUnavailable
from .schemas import AnswerState, Evidence, RetrievalResult, RetrievalTrace
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
        final_evidence_limit: int | None = None,
    ) -> RetrievalResult:
        dense = self.dense_search(query_vector, self.limits.dense_top_k)
        sparse = self.sparse_index.search(query, self.limits.bm25_top_k)
        candidates = reciprocal_rank_fusion(dense, sparse, limit=self.limits.fusion_candidate_limit)
        fusion_candidate_count = len(candidates)
        fusion_candidate_ids = [item.document_id for item in candidates]
        reranker_executed = False
        reranker_input_count = 0
        reranker_output_count = 0
        if lookup:
            candidates = parent_neighbor_heading(candidates, lookup)
        fallback_reason = None
        if self.reranker:
            try:
                reranker_executed = True
                reranker_input_count = min(len(candidates), self.limits.reranker_input_limit)
                candidates = self.reranker.rerank(
                    query, candidates, self.limits.reranker_input_limit
                )
                reranker_output_count = len(candidates)
            except RerankerUnavailable as error:
                fallback_reason = str(error)
        final_limit = final_evidence_limit or self.limits.final_evidence_top_k
        if final_limit < 1:
            raise ValueError("final evidence limit must be positive")
        final = candidates[:final_limit]
        return result_for(
            final,
            fallback_reason,
            trace=RetrievalTrace(
                dense_executed=True,
                dense_candidate_count=len(dense),
                bm25_executed=True,
                bm25_candidate_count=len(sparse),
                fusion_candidate_count=fusion_candidate_count,
                neighbor_expansion_executed=lookup is not None,
                reranker_executed=reranker_executed,
                reranker_input_count=reranker_input_count,
                reranker_output_count=reranker_output_count,
                final_evidence_count=len(final),
                stage_rankings={
                    "bm25": [item.document_id for item in sparse],
                    "dense": [item.document_id for item in dense],
                    "fusion": fusion_candidate_ids,
                    "final": [item.document_id for item in final],
                },
            ),
        )


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


def result_for(
    evidence: list[Evidence],
    fallback_reason: str | None = None,
    *,
    trace: RetrievalTrace | None = None,
) -> RetrievalResult:
    state = AnswerState.GROUNDED if evidence else AnswerState.UNSUPPORTED
    if evidence and fallback_reason:
        state = AnswerState.PARTIAL
    return RetrievalResult(tuple(evidence), state, fallback_reason, trace or RetrievalTrace())
