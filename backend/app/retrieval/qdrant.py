"""The sole Qdrant boundary. All public operations require a workspace id."""
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID, uuid5

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from .schemas import Evidence

COLLECTIONS = {
    "chunks": "cortex_chunks",
    "entities": "cortex_graphrag_entities",
    "reports": "cortex_graphrag_reports",
    "text_units": "cortex_graphrag_text_units",
}
POINT_NAMESPACE = UUID("2e6bc1ee-5778-48c7-aad8-594d9065c057")


def deterministic_point_id(resource_type: str, workspace_id: str, record_id: str) -> str:
    return str(uuid5(POINT_NAMESPACE, f"{resource_type}:{workspace_id}:{record_id}"))


def workspace_filter(workspace_id: str) -> Filter:
    if not workspace_id:
        raise ValueError("workspace_id is required for Qdrant operations")
    return Filter(must=[FieldCondition(key="workspace_id", match=MatchValue(value=workspace_id))])


@dataclass(frozen=True)
class VectorRecord:
    record_id: str
    vector: list[float]
    payload: dict[str, object]


class WorkspaceQdrantStore:
    def __init__(
        self,
        client: QdrantClient,
        workspace_id: str,
        *,
        embedding_config_hash: str | None = None,
    ) -> None:
        if not workspace_id:
            raise ValueError("workspace_id is required")
        self.client = client
        self.workspace_id = workspace_id
        self.embedding_config_hash = embedding_config_hash

    def ensure_collection(self, resource_type: str, dimension: int) -> str:
        collection = COLLECTIONS[resource_type]
        if not self.client.collection_exists(collection):
            self.client.create_collection(
                collection,
                vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
            )
        for key in (
            "workspace_id",
            "document_id",
            "document_version_id",
            "folder_id",
            "embedding_config_hash",
        ):
            self.client.create_payload_index(collection, key, PayloadSchemaType.KEYWORD, wait=True)
        return collection

    def upsert(self, resource_type: str, records: Iterable[VectorRecord], dimension: int) -> None:
        self._require_embedding_configuration(resource_type)
        collection = self.ensure_collection(resource_type, dimension)
        points = []
        for record in records:
            if len(record.vector) != dimension:
                raise ValueError("vector dimension does not match active collection")
            if (
                resource_type == "chunks"
                and record.payload.get("embedding_config_hash")
                not in {None, self.embedding_config_hash}
            ):
                raise ValueError(
                    "record embedding configuration does not match active vector field"
                )
            payload = {**record.payload, "workspace_id": self.workspace_id}
            if resource_type == "chunks":
                payload["embedding_config_hash"] = self.embedding_config_hash
            points.append(
                PointStruct(
                    id=deterministic_point_id(resource_type, self.workspace_id, record.record_id),
                    vector=record.vector,
                    payload=payload,
                )
            )
        if points:
            self.client.upsert(collection, points, wait=True)

    def search(self, resource_type: str, query_vector: list[float], limit: int) -> list[Evidence]:
        collection = COLLECTIONS[resource_type]
        query_filter = workspace_filter(self.workspace_id)
        if resource_type == "chunks":
            self._require_embedding_configuration(resource_type)
            query_filter.must.append(
                FieldCondition(
                    key="embedding_config_hash",
                    match=MatchValue(value=self.embedding_config_hash),
                )
            )
        result = self.client.query_points(
            collection,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
        ).points
        return [self._to_evidence(resource_type, point) for point in result]

    def _to_evidence(self, resource_type: str, point) -> Evidence:
        payload = point.payload
        return Evidence(
            workspace_id=self.workspace_id,
            source=f"qdrant:{resource_type}",
            content=str(payload.get("content", "")),
            score=float(point.score),
            document_id=payload.get("document_id"),
            document_version_id=payload.get("document_version_id"),
            chunk_id=payload.get("chunk_id"),
            citation_label=payload.get("citation_label"),
            metadata={
                key: str(value)
                for key, value in payload.items()
                if key not in {"content", "workspace_id"}
            },
        )

    def delete_document(self, resource_type: str, document_id: str) -> None:
        from qdrant_client.models import FilterSelector
        selector = FilterSelector(
            filter=Filter(
                must=[
                    *workspace_filter(self.workspace_id).must,
                    FieldCondition(key="document_id", match=MatchValue(value=document_id)),
                ]
            )
        )
        self.client.delete(COLLECTIONS[resource_type], points_selector=selector, wait=True)

    def _require_embedding_configuration(self, resource_type: str) -> None:
        if resource_type == "chunks" and not self.embedding_config_hash:
            raise ValueError("active embedding configuration is required for dense chunk vectors")
