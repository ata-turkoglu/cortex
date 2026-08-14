"""Worker-owned construction of the active workspace retrieval projections."""

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.qdrant import get_qdrant_client
from ..core.workspaces import WorkspaceContext
from ..models import Chunk, Document, LogicalDocument
from ..providers.embeddings import (
    EmbeddingConfiguration,
    OllamaEmbeddingAdapter,
    OpenAIEmbeddingAdapter,
    Qwen3EmbeddingAdapter,
    adaptive_embed,
    prepared_text_hash,
)
from .index_state import mark_dense_index_ready
from .qdrant import VectorRecord, WorkspaceQdrantStore
from .schemas import Evidence
from .sparse import SparseDocument, WorkspaceBM25Index


@dataclass(frozen=True)
class IndexingSummary:
    workspace_id: str
    chunk_count: int
    embedding_config_hash: str


def rebuild_active_workspace(session: Session, workspace_id: str) -> IndexingSummary:
    """Rebuild sparse and dense projections from exactly the active relational corpus."""
    context = WorkspaceContext.load(session, workspace_id)
    rows = session.execute(
        select(Chunk, Document, LogicalDocument)
        .join(Document, Document.id == Chunk.document_id)
        .outerjoin(LogicalDocument, LogicalDocument.id == Chunk.logical_document_id)
        .where(
            Chunk.workspace_id == workspace_id,
            Chunk.deleted_at.is_(None),
            Document.deleted_at.is_(None),
            Chunk.document_version_id == Document.active_version_id,
        )
        .order_by(Chunk.id)
    ).all()
    evidence: list[Evidence] = []
    for chunk, document, logical in rows:
        metadata = {
            key: str(value) for key, value in json.loads(chunk.metadata_json or "{}").items()
        }
        evidence.append(
            Evidence(
                workspace_id=workspace_id,
                source=logical.title if logical else document.title,
                content=chunk.content,
                score=0.0,
                document_id=logical.id if logical else document.id,
                document_version_id=chunk.document_version_id,
                chunk_id=chunk.id,
                citation_label=(
                    f"{logical.document_code}, passage {chunk.ordinal + 1}"
                    if logical
                    else f"{document.title}, passage {chunk.ordinal + 1}"
                ),
                metadata=metadata,
            )
        )
    sparse = WorkspaceBM25Index(
        workspace_id,
        [SparseDocument(item.chunk_id or "", item.content, item) for item in evidence],
        context.resource_path("bm25_chunks"),
    )
    sparse.save()
    state = context.index_state
    state.sparse_state, state.updated_at = "ready", datetime.now(UTC)
    settings = get_settings()
    provider = (
        Qwen3EmbeddingAdapter()
        if settings.embedding_provider == "ollama" and settings.embedding_model.startswith("qwen3")
        else OllamaEmbeddingAdapter()
        if settings.embedding_provider == "ollama"
        else OpenAIEmbeddingAdapter(settings.embedding_model)
    )
    texts = [
        provider.prepare_document(
            item.content, title=item.source, heading=item.metadata.get("heading")
        )
        if isinstance(provider, Qwen3EmbeddingAdapter)
        else item.content
        for item in evidence
    ]
    vectors = (
        asyncio.run(
            adaptive_embed(
                provider,
                texts,
                batch_size=settings.embedding_batch_size,
                min_batch_size=settings.embedding_min_batch_size,
            )
        )
        if texts
        else []
    )
    if not vectors:
        raise RuntimeError("active workspace has no embeddings to index")
    dimension = len(vectors[0]) if vectors else 0
    configuration = EmbeddingConfiguration(
        settings.embedding_provider, settings.embedding_model, dimension
    )
    store = WorkspaceQdrantStore(
        get_qdrant_client(), workspace_id, embedding_config_hash=configuration.fingerprint
    )
    if vectors:
        store.clear_workspace("chunks")
        store.upsert(
            "chunks",
            [
                VectorRecord(
                    item.chunk_id or "",
                    vector,
                    {
                        "content": item.content,
                        "chunk_id": item.chunk_id,
                        "document_id": item.document_id,
                        "document_version_id": item.document_version_id,
                        "citation_label": item.citation_label,
                        **item.metadata,
                    },
                )
                for item, vector in zip(evidence, vectors, strict=True)
            ],
            dimension,
        )
        for (chunk, _, _), text in zip(rows, texts, strict=True):
            chunk.prepared_embedding_hash = prepared_text_hash(text)
    mark_dense_index_ready(session, workspace_id, configuration)
    return IndexingSummary(workspace_id, len(evidence), configuration.fingerprint)
