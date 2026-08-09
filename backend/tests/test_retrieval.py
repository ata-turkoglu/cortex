import pytest

from app.core.config import Settings
from app.providers.embeddings import (
    EmbeddingConfiguration,
    prepare_embedding_text,
    prepared_text_hash,
)
from app.retrieval.hybrid import (
    HybridRetriever,
    RetrievalLimits,
    parent_neighbor_heading,
    reciprocal_rank_fusion,
    result_for,
)
from app.retrieval.index_state import (
    DenseIndexUnavailable,
    create_dense_reindex_run,
    mark_dense_index_ready,
    plan_dense_reindex,
    require_dense_index_ready,
)
from app.retrieval.qdrant import (
    VectorRecord,
    WorkspaceQdrantStore,
    deterministic_point_id,
    workspace_filter,
)
from app.retrieval.reranker import LocalBGEReranker, RerankerUnavailable
from app.retrieval.schemas import AnswerState, Evidence
from app.retrieval.sparse import SparseDocument, WorkspaceBM25Index


def evidence(chunk_id: str, score: float = 1.0) -> Evidence:
    return Evidence("workspace-a", "test", "Türkçe içerik", score, chunk_id=chunk_id)


def test_embedding_template_preserves_turkish_unicode_and_is_stable():
    text = prepare_embedding_text("İstanbul, ığdır ve şeker.", title="Başlık", heading="Özet")
    assert "İstanbul" in text
    assert prepared_text_hash(text) == prepared_text_hash(text)


def test_rrf_deduplicates_evidence_and_reports_unsupported_without_sources():
    fused = reciprocal_rank_fusion([evidence("one"), evidence("two")], [evidence("two")], limit=2)
    assert [item.chunk_id for item in fused] == ["two", "one"]
    assert result_for([]).state is AnswerState.UNSUPPORTED


def test_parent_neighbor_heading_expansion_is_deduplicated_and_workspace_safe():
    hit = Evidence(
        "workspace-a",
        "dense",
        "hit",
        1.0,
        chunk_id="hit",
        metadata={
            "parent_chunk_id": "parent",
            "next_chunk_id": "neighbor",
            "related_chunk_ids": "foreign",
        },
    )
    parent = evidence("parent")
    neighbor = evidence("neighbor")
    foreign = Evidence("workspace-b", "dense", "foreign", 1.0, chunk_id="foreign")
    expanded = parent_neighbor_heading(
        [hit],
        {"parent": parent, "neighbor": neighbor, "foreign": foreign},
    )
    assert [item.chunk_id for item in expanded] == ["hit", "parent", "neighbor"]


def test_qdrant_workspace_filter_and_point_ids_are_scoped():
    assert workspace_filter("workspace-a").must[0].key == "workspace_id"
    first = deterministic_point_id("chunks", "workspace-a", "chunk-1")
    second = deterministic_point_id("chunks", "workspace-b", "chunk-1")
    assert first != second


def test_qdrant_document_deletion_is_a_noop_when_no_collection_exists():
    from qdrant_client import QdrantClient

    WorkspaceQdrantStore(QdrantClient(":memory:"), "workspace-a").delete_document(
        "chunks", "document-a"
    )


def test_qdrant_dense_upsert_and_search_are_workspace_isolated():
    from qdrant_client import QdrantClient

    client = QdrantClient(":memory:")
    first = WorkspaceQdrantStore(client, "workspace-a", embedding_config_hash="config-a")
    second = WorkspaceQdrantStore(client, "workspace-b", embedding_config_hash="config-a")
    first.upsert(
        "chunks",
        [VectorRecord("same", [1.0, 0.0], {"content": "first", "chunk_id": "first"})],
        dimension=2,
    )
    second.upsert(
        "chunks",
        [VectorRecord("same", [1.0, 0.0], {"content": "second", "chunk_id": "second"})],
        dimension=2,
    )
    assert [item.content for item in first.search("chunks", [1.0, 0.0], 5)] == ["first"]
    with pytest.raises(ValueError, match="dimension"):
        first.upsert("chunks", [VectorRecord("bad", [1.0], {})], dimension=2)


def test_dense_vectors_require_one_active_embedding_configuration():
    from qdrant_client import QdrantClient

    store = WorkspaceQdrantStore(QdrantClient(":memory:"), "workspace-a")
    with pytest.raises(ValueError, match="active embedding configuration"):
        store.upsert("chunks", [VectorRecord("chunk", [1.0, 0.0], {})], dimension=2)


def test_dense_search_excludes_vectors_from_another_embedding_configuration():
    from qdrant_client import QdrantClient

    client = QdrantClient(":memory:")
    old = WorkspaceQdrantStore(client, "workspace-a", embedding_config_hash="old-config")
    current = WorkspaceQdrantStore(client, "workspace-a", embedding_config_hash="new-config")
    old.upsert("chunks", [VectorRecord("old", [1.0, 0.0], {"content": "old"})], dimension=2)
    current.upsert(
        "chunks", [VectorRecord("current", [1.0, 0.0], {"content": "current"})], dimension=2
    )
    assert [item.content for item in current.search("chunks", [1.0, 0.0], 5)] == ["current"]


def test_embedding_configuration_change_requires_full_reindex_before_search():
    from datetime import UTC, datetime
    from uuid import uuid4

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models import Base, Workspace, WorkspaceIndexState

    session = sessionmaker(bind=create_engine("sqlite:///:memory:"))()
    Base.metadata.create_all(session.bind)
    now = datetime.now(UTC)
    workspace = Workspace(
        id=str(uuid4()),
        slug="embedding-state",
        name="Embedding state",
        state="active",
        created_at=now,
        updated_at=now,
    )
    configuration = EmbeddingConfiguration("ollama", "bge-m3:latest", dimension=1024)
    state = WorkspaceIndexState(workspace_id=workspace.id, dense_state="empty", updated_at=now)
    session.add_all([workspace, state])
    session.commit()
    initial_plan = plan_dense_reindex(session, workspace.id, configuration)
    assert initial_plan.reason == "initial_dense_index_required"
    mark_dense_index_ready(session, workspace.id, configuration)
    require_dense_index_ready(state, configuration)
    changed = EmbeddingConfiguration("ollama", "qwen3-embedding:0.6b", dimension=1024)
    plan = plan_dense_reindex(session, workspace.id, changed)
    assert plan.reason == "embedding_configuration_changed"
    first_run = create_dense_reindex_run(session, workspace.id, changed)
    assert first_run.job_type == "dense_reindex"
    assert create_dense_reindex_run(session, workspace.id, changed).id == first_run.id
    with pytest.raises(DenseIndexUnavailable, match="full reindex"):
        require_dense_index_ready(state, changed)


def test_bm25_index_persists_per_workspace_and_rejects_cross_workspace_load(tmp_path):
    path = tmp_path / "workspace-a" / "bm25"
    index = WorkspaceBM25Index(
        "workspace-a",
        [
            SparseDocument("ankara", "Ankara Türkiye'nin başkentidir.", evidence("ankara")),
            SparseDocument("izmir", "İzmir Ege bölgesindedir.", evidence("izmir")),
        ],
        path,
    )
    index.save()
    loaded = WorkspaceBM25Index.load("workspace-a", path)
    assert [item.chunk_id for item in loaded.search("Türkiye başkenti", 1)] == ["ankara"]
    with pytest.raises(ValueError, match="different workspace"):
        WorkspaceBM25Index.load("workspace-b", path)


def test_hybrid_retriever_applies_configured_limits_and_falls_back_without_reranker():
    sparse = WorkspaceBM25Index(
        "workspace-a", [SparseDocument("sparse", "Ankara başkent", evidence("sparse"))]
    )

    class MissingReranker:
        def rerank(self, query, items, limit):
            from app.retrieval.reranker import RerankerUnavailable

            raise RerankerUnavailable("local_reranker_model_unavailable")

    settings = Settings(
        dense_top_k=1,
        bm25_top_k=1,
        fusion_candidate_limit=2,
        reranker_input_limit=1,
        final_evidence_top_k=1,
    )
    retriever = HybridRetriever(
        lambda _vector, limit: [evidence("dense")][:limit],
        sparse,
        RetrievalLimits.from_settings(settings),
        MissingReranker(),
    )
    result = retriever.search("Ankara", [1.0])
    assert [item.chunk_id for item in result.evidence] == ["dense"]
    assert result.state is AnswerState.PARTIAL
    assert result.fallback_reason == "local_reranker_model_unavailable"


def test_retrieval_limits_reject_non_positive_values():
    with pytest.raises(ValueError, match="positive"):
        RetrievalLimits.from_settings(Settings(dense_top_k=0))


def test_local_reranker_never_downloads_an_unconfigured_model():
    with pytest.raises(RerankerUnavailable, match="not_configured"):
        LocalBGEReranker(None).rerank("Ankara", [evidence("chunk")], 1)
