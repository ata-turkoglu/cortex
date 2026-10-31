from qdrant_client import QdrantClient

from app.retrieval.qdrant import VectorRecord, WorkspaceQdrantStore


def test_generation_payloads_are_scoped_and_preserve_manifest_identity():
    client = QdrantClient(":memory:")
    store = WorkspaceQdrantStore(
        client,
        "workspace-a",
        embedding_config_hash="embedding-a",
        projection_key="generation-a",
    )
    store.upsert(
        "chunks",
        [
            VectorRecord(
                "chunk-a",
                [1.0, 0.0],
                {
                    "chunk_id": "chunk-a",
                    "document_id": "document-a",
                    "document_version_id": "version-a",
                    "logical_document_id": "logical-a",
                    "content_hash": "content-hash-a",
                    "content": "authoritative",
                },
            )
        ],
        2,
    )

    assert store.generation_payloads() == (
        {
            "chunk_id": "chunk-a",
            "document_id": "document-a",
            "document_version_id": "version-a",
            "logical_document_id": "logical-a",
            "content_hash": "content-hash-a",
            "content": "authoritative",
            "workspace_id": "workspace-a",
            "knowledge_generation_id": "generation-a",
            "embedding_config_hash": "embedding-a",
        },
    )
