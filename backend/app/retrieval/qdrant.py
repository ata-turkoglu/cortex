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


def generation_filter(workspace_id: str, generation_id: str, embedding_config_hash: str) -> Filter:
    if not workspace_id or not generation_id or not embedding_config_hash:
        raise ValueError("GENERATION_SCOPE_REQUIRED")
    return Filter(
        must=[
            FieldCondition(key="workspace_id", match=MatchValue(value=workspace_id)),
            FieldCondition(
                key="knowledge_generation_id", match=MatchValue(value=generation_id)
            ),
            FieldCondition(
                key="embedding_config_hash", match=MatchValue(value=embedding_config_hash)
            ),
        ]
    )


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
        projection_key: str | None = None,
    ) -> None:
        if not workspace_id:
            raise ValueError("workspace_id is required")
        self.client = client
        self.workspace_id = workspace_id
        self.embedding_config_hash = embedding_config_hash
        self.projection_key = projection_key

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
            "knowledge_generation_id",
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
            if resource_type == "chunks" and record.payload.get("embedding_config_hash") not in {
                None,
                self.embedding_config_hash,
            }:
                raise ValueError(
                    "record embedding configuration does not match active vector field"
                )
            payload = {**record.payload, "workspace_id": self.workspace_id}
            if self.projection_key:
                payload["knowledge_generation_id"] = self.projection_key
            if resource_type == "chunks":
                payload["embedding_config_hash"] = self.embedding_config_hash
            points.append(
                PointStruct(
                    id=deterministic_point_id(
                        resource_type,
                        self.workspace_id,
                        f"{self.projection_key}:{record.record_id}"
                        if self.projection_key
                        else record.record_id,
                    ),
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

    def search_generation(self, query_vector: list[float], limit: int, scope) -> list[Evidence]:
        """Dedicated V2 read; a generation scope is mandatory and there is no fallback."""
        if scope.workspace_id != self.workspace_id:
            raise ValueError("GENERATION_SCOPE_WORKSPACE_MISMATCH")
        if scope.embedding_config_hash != self.embedding_config_hash:
            raise ValueError("EMBEDDING_FINGERPRINT_REQUIRED")
        points = self.client.query_points(
            COLLECTIONS["chunks"],
            query=query_vector,
            query_filter=generation_filter(
                scope.workspace_id, scope.generation_id, scope.embedding_config_hash
            ),
            limit=limit,
        ).points
        evidence = [self._to_evidence("chunks", point) for point in points]
        if any(
            item.metadata.get("knowledge_generation_id") != scope.generation_id
            for item in evidence
        ):
            raise RuntimeError("GENERATION_MISMATCH")
        return evidence

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

        collection = COLLECTIONS[resource_type]
        # An unindexed document has no collection to clean up. Treat this as a
        # successful no-op so deletion remains idempotent across stores.
        if not self.client.collection_exists(collection):
            return
        selector = FilterSelector(
            filter=Filter(
                must=[
                    *workspace_filter(self.workspace_id).must,
                    FieldCondition(key="document_id", match=MatchValue(value=document_id)),
                ]
            )
        )
        self.client.delete(collection, points_selector=selector, wait=True)

    def clear_workspace(self, resource_type: str) -> None:
        """Replace only this workspace's projection during a full active-corpus rebuild."""
        from qdrant_client.models import FilterSelector

        collection = COLLECTIONS[resource_type]
        if self.client.collection_exists(collection):
            self.client.delete(
                collection,
                points_selector=FilterSelector(filter=workspace_filter(self.workspace_id)),
                wait=True,
            )

    def _require_embedding_configuration(self, resource_type: str) -> None:
        if resource_type == "chunks" and not self.embedding_config_hash:
            raise ValueError("active embedding configuration is required for dense chunk vectors")
