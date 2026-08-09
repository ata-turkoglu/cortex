"""GraphRAG-specific vector mirror built on the workspace-safe Qdrant boundary."""

from collections.abc import Iterable

from qdrant_client import QdrantClient

from ..providers.base import EmbeddingProvider
from ..providers.embeddings import EmbeddingHealth
from ..retrieval.qdrant import VectorRecord, WorkspaceQdrantStore
from .adapter import GraphArtifact, GraphRAGAdapter

VECTOR_RESOURCE_TYPES = frozenset({"entities", "reports", "text_units"})


class GraphRAGQdrantAdapter:
    def __init__(self, client: QdrantClient, workspace_id: str) -> None:
        self.store = WorkspaceQdrantStore(client, workspace_id)

    def index_artifacts(
        self,
        resource_type: str,
        artifacts: Iterable[GraphArtifact],
        vectors: Iterable[list[float]],
        dimension: int,
    ) -> None:
        if resource_type not in VECTOR_RESOURCE_TYPES:
            raise ValueError(f"unsupported GraphRAG vector resource type: {resource_type}")
        records = []
        for artifact, vector in zip(artifacts, vectors, strict=True):
            if artifact.resource_type != resource_type:
                raise ValueError("artifact type does not match target vector resource")
            records.append(
                VectorRecord(
                    artifact.artifact_id,
                    vector,
                    {
                        "content": artifact.text,
                        "artifact_id": artifact.artifact_id,
                        **artifact.attributes,
                    },
                )
            )
        self.store.upsert(resource_type, records, dimension)

    def search(self, resource_type: str, query_vector: list[float], limit: int):
        if resource_type not in VECTOR_RESOURCE_TYPES:
            raise ValueError(f"unsupported GraphRAG vector resource type: {resource_type}")
        return self.store.search(resource_type, query_vector, limit)


async def mirror_graph_outputs(
    graph: GraphRAGAdapter,
    mirror: GraphRAGQdrantAdapter,
    provider: EmbeddingProvider,
) -> dict[str, int]:
    """Mirror canonical GraphRAG outputs after indexing without changing the source artifacts."""
    if graph.workspace_id != mirror.store.workspace_id:
        raise ValueError("GraphRAG mirror workspace does not match canonical graph workspace")
    mirrored: dict[str, int] = {}
    for resource_type in sorted(VECTOR_RESOURCE_TYPES):
        artifacts = [
            GraphArtifact(
                artifact.artifact_id,
                artifact.resource_type,
                artifact.text,
                {
                    **artifact.attributes,
                    "logical_document_ids": ",".join(
                        graph.logical_document_ids_for(artifact)
                    ),
                },
            )
            for artifact in graph.load_artifacts(resource_type)
        ]
        if not artifacts:
            mirrored[resource_type] = 0
            continue
        vectors = await provider.embed([artifact.text for artifact in artifacts])
        dimension = EmbeddingHealth.validate(vectors)
        mirror.index_artifacts(resource_type, artifacts, vectors, dimension)
        mirrored[resource_type] = len(artifacts)
    return mirrored
