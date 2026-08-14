"""Chat-facing composition of the existing workspace hybrid retrieval boundaries."""

import asyncio
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.qdrant import get_qdrant_client
from ..core.workspaces import WorkspaceContext
from ..providers.embeddings import (
    OllamaEmbeddingAdapter,
    OpenAIEmbeddingAdapter,
    Qwen3EmbeddingAdapter,
)
from .hybrid import HybridRetriever, RetrievalLimits
from .qdrant import WorkspaceQdrantStore
from .reranker import LocalBGEReranker
from .schemas import Evidence, RetrievalResult
from .sparse import WorkspaceBM25Index

BM25_RESOURCE = "bm25_chunks"


class HybridRetrievalRuntime:
    """Resolve one workspace's persisted retrieval resources for a chat request."""

    def search(
        self,
        session: Session,
        workspace_id: str,
        query: str,
        *,
        final_evidence_limit: int | None = None,
    ) -> RetrievalResult:
        context = WorkspaceContext.load(session, workspace_id)
        settings = get_settings()
        sparse_error: str | None = None
        try:
            sparse_index = self._load_sparse(context, workspace_id)
        except Exception as exc:
            sparse_error = self._reason("bm25", exc)
            sparse_index = WorkspaceBM25Index(workspace_id)
        query_vector: list[float] | None = None
        dense_error: str | None = None
        try:
            query_vector = self._embed_query(query)
        except Exception as exc:  # Sparse retrieval remains a valid, explicit degradation.
            dense_error = self._reason("embedding", exc)

        store = WorkspaceQdrantStore(
            get_qdrant_client(),
            workspace_id,
            embedding_config_hash=context.index_state.embedding_config_hash,
        )

        def dense_search(vector: list[float], limit: int) -> list[Evidence]:
            nonlocal dense_error
            if dense_error or vector is None:
                return []
            try:
                return store.search("chunks", vector, limit)
            except Exception as exc:
                dense_error = self._reason("qdrant", exc)
                return []

        if sparse_error is None:
            try:
                # Validate the persisted resource now, rather than hiding a corrupt/missing index.
                sparse_index.search(query, 1)
            except Exception as exc:
                sparse_error = self._reason("bm25", exc)
                sparse_index = WorkspaceBM25Index(workspace_id)

        reranker = get_local_reranker(settings.reranker_model, settings.reranker_device)
        result = HybridRetriever(
            dense_search,
            sparse_index,
            RetrievalLimits.from_settings(settings),
            reranker,
        ).search(query, query_vector or [], final_evidence_limit=final_evidence_limit)
        return replace(
            result,
            trace=replace(
                result.trace,
                dense_executed=query_vector is not None and dense_error is None,
                dense_error=dense_error,
                bm25_executed=sparse_error is None,
                bm25_error=sparse_error,
            ),
        )

    def _load_sparse(self, context: WorkspaceContext, workspace_id: str) -> WorkspaceBM25Index:
        path: Path = context.resource_path(BM25_RESOURCE)
        return WorkspaceBM25Index.load(workspace_id, path)

    def _embed_query(self, query: str) -> list[float]:
        settings = get_settings()
        if settings.embedding_provider == "ollama":
            provider = (
                Qwen3EmbeddingAdapter()
                if settings.embedding_model.startswith("qwen3")
                else OllamaEmbeddingAdapter()
            )
            prepared = (
                provider.prepare_query(query)
                if isinstance(provider, Qwen3EmbeddingAdapter)
                else query
            )
        elif settings.embedding_provider == "openai":
            provider = OpenAIEmbeddingAdapter(settings.embedding_model)
            prepared = query
        else:
            raise ValueError("unsupported embedding provider")
        vectors = asyncio.run(provider.embed([prepared]))
        return vectors[0]

    @staticmethod
    def _reason(component: str, error: Exception) -> str:
        return f"{component}_unavailable:{type(error).__name__}"


def get_hybrid_retrieval_runtime() -> HybridRetrievalRuntime:
    """Factory kept small so tests and alternate process lifecycles can replace it."""
    return HybridRetrievalRuntime()


@lru_cache
def get_local_reranker(model_name: str | None, device: str | None) -> LocalBGEReranker | None:
    """Keep local model weights resident across chat requests when reranking is enabled."""
    return LocalBGEReranker(model_name, device) if model_name else None
