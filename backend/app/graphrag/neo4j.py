"""Neo4j persistence bridge for Microsoft GraphRAG extraction output."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..knowledge.graph import GraphNode, GraphRelationship, GraphSyncResult, Neo4jGraphAdapter
from ..retrieval.schemas import AnswerState, Evidence
from .adapter import GraphArtifact, GraphRAGAdapter, GraphRoute


class ExtractedGraphStore(Protocol):
    workspace_id: str

    def ensure_schema(self) -> None: ...

    def replace_extracted_generation(
        self,
        generation: str,
        nodes: tuple[GraphNode, ...],
        relationships: tuple[GraphRelationship, ...],
    ) -> GraphSyncResult: ...


@dataclass(frozen=True)
class GraphRAGFinding:
    workspace_id: str
    route: GraphRoute
    text: str
    source: str
    confidence: float
    provenance: dict[str, object]


@dataclass(frozen=True)
class GraphRAGEngineOutput:
    """Phase 03 precursor to the common Phase 09 EngineResult contract."""

    workspace_id: str
    route: GraphRoute
    findings: tuple[GraphRAGFinding, ...]
    evidence: tuple[Evidence, ...]
    state: AnswerState
    fallback_reason: str | None
    final_answer_authored: bool = False


@dataclass(frozen=True)
class GraphRAGNeo4jSyncResult:
    graph: GraphSyncResult
    skipped_relationship_count: int


class Neo4jBackedGraphRAGAdapter:
    """Persist GraphRAG-produced knowledge and expose non-final typed findings."""

    node_resource_types = ("entities", "reports", "text_units", "documents")

    def __init__(self, graphrag: GraphRAGAdapter, graph_store: ExtractedGraphStore) -> None:
        if graphrag.workspace_id != graph_store.workspace_id:
            raise ValueError("GraphRAG and Neo4j adapters must use the same workspace")
        self.graphrag = graphrag
        self.graph_store = graph_store

    @staticmethod
    def _external_id(artifact: GraphArtifact) -> str:
        return f"{artifact.resource_type}:{artifact.artifact_id}"

    def _provenance(self, artifact: GraphArtifact) -> dict[str, object]:
        return {
            "producer": "microsoft_graphrag",
            "artifact_id": artifact.artifact_id,
            "resource_type": artifact.resource_type,
            "logical_document_ids": list(self.graphrag.logical_document_ids_for(artifact)),
        }

    def sync_extracted(self, generation: str) -> GraphRAGNeo4jSyncResult:
        artifacts_by_type = {
            resource_type: self.graphrag.load_artifacts(resource_type)
            for resource_type in self.node_resource_types
        }
        nodes = tuple(
            GraphNode(
                external_id=self._external_id(artifact),
                kind=resource_type,
                generation=generation,
                text=artifact.text,
                properties={"attributes": artifact.attributes},
                provenance=self._provenance(artifact),
            )
            for resource_type, artifacts in artifacts_by_type.items()
            for artifact in artifacts
        )
        entity_aliases: dict[str, str] = {}
        for artifact in artifacts_by_type["entities"]:
            external_id = self._external_id(artifact)
            aliases = {
                artifact.artifact_id,
                artifact.attributes.get("title", ""),
                artifact.attributes.get("name", ""),
                artifact.attributes.get("human_readable_id", ""),
            }
            entity_aliases.update(
                {alias.casefold(): external_id for alias in aliases if alias.strip()}
            )

        relationships: list[GraphRelationship] = []
        skipped = 0
        for artifact in self.graphrag.load_artifacts("relationships"):
            source = entity_aliases.get(artifact.attributes.get("source", "").casefold())
            target = entity_aliases.get(artifact.attributes.get("target", "").casefold())
            if not source or not target:
                skipped += 1
                continue
            relationships.append(
                GraphRelationship(
                    external_id=self._external_id(artifact),
                    kind=artifact.attributes.get("type", "related"),
                    source_id=source,
                    target_id=target,
                    generation=generation,
                    properties={"text": artifact.text, "attributes": artifact.attributes},
                    provenance=self._provenance(artifact),
                )
            )

        self.graph_store.ensure_schema()
        result = self.graph_store.replace_extracted_generation(
            generation,
            nodes,
            tuple(relationships),
        )
        return GraphRAGNeo4jSyncResult(result, skipped)

    def query_findings(
        self, route: GraphRoute, query: str, limit: int = 10
    ) -> GraphRAGEngineOutput:
        result = self.graphrag.query(route, query, limit)
        findings = tuple(
            GraphRAGFinding(
                workspace_id=item.workspace_id,
                route=route,
                text=item.content,
                source=item.source,
                confidence=item.score,
                provenance={
                    "document_id": item.document_id,
                    "document_version_id": item.document_version_id,
                    "chunk_id": item.chunk_id,
                    "metadata": item.metadata,
                },
            )
            for item in result.evidence
        )
        return GraphRAGEngineOutput(
            workspace_id=self.graphrag.workspace_id,
            route=route,
            findings=findings,
            evidence=result.evidence,
            state=result.state,
            fallback_reason=result.fallback_reason,
        )


def sync_graph_to_neo4j(
    graphrag: GraphRAGAdapter,
    generation: str,
) -> GraphRAGNeo4jSyncResult:
    """Open the configured store only for the worker-owned synchronization step."""
    with Neo4jGraphAdapter.from_settings(graphrag.workspace_id) as graph_store:
        return Neo4jBackedGraphRAGAdapter(graphrag, graph_store).sync_extracted(generation)
