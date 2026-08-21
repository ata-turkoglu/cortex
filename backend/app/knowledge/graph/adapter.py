"""Workspace-scoped Neo4j boundary for extracted and canonical Cortex knowledge."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from ...core.config import Settings, get_settings
from ...core.secrets import SecretStore
from ..claims import ClaimConflict, KnowledgeClaim
from ..entities import (
    CanonicalEntity,
    EntityType,
    IdentityDecisionKind,
    IdentityOperation,
    ResolutionCandidate,
    normalize_mention,
)
from ..events import CanonicalEvent
from ..model import KnowledgeAuthority, new_canonical_id, require_canonical_id
from ..relations import CanonicalRelation
from ..temporal import TemporalExpression


class Neo4jConfigurationError(RuntimeError):
    """Raised when Cortex cannot create an authenticated Neo4j adapter."""


@dataclass(frozen=True)
class GraphNode:
    external_id: str
    kind: str
    generation: str
    text: str = ""
    properties: dict[str, object] = field(default_factory=dict)
    provenance: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphRelationship:
    external_id: str
    kind: str
    source_id: str
    target_id: str
    generation: str
    properties: dict[str, object] = field(default_factory=dict)
    provenance: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphSyncResult:
    workspace_id: str
    generation: str
    node_count: int
    relationship_count: int


@dataclass(frozen=True)
class CanonicalEntityView:
    entity_id: str
    entity_type: str
    display_name: str
    subtype: str | None
    authority: str
    status: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class IdentityHistoryView:
    operation_id: str
    kind: str
    authority: str
    source_entity_ids: tuple[str, ...]
    result_entity_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    reason: str
    details: dict[str, object]


@dataclass(frozen=True)
class EntityEvidenceView:
    evidence_id: str
    mention_id: str
    original_text: str
    document_id: str
    document_version_id: str
    logical_document_id: str
    chunk_id: str
    start_offset: int
    end_offset: int
    source_text: str
    extraction_run_id: str
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    confidence: float
    validation_state: str
    generation: str


@dataclass(frozen=True)
class CanonicalEvidenceQueryView:
    evidence_id: str
    document_id: str
    document_version_id: str
    logical_document_id: str
    chunk_id: str
    start_offset: int
    end_offset: int
    source_text: str
    confidence: float
    generation: str


@dataclass(frozen=True)
class CanonicalEntityQueryView:
    entity_id: str
    entity_type: str
    display_name: str
    subtype: str | None
    evidence: tuple[CanonicalEvidenceQueryView, ...]


@dataclass(frozen=True)
class CanonicalPathQueryView:
    path_id: str
    node_ids: tuple[str, ...]
    relation_ids: tuple[str, ...]
    relation_types: tuple[str, ...]
    evidence: tuple[CanonicalEvidenceQueryView, ...]


@dataclass(frozen=True)
class CanonicalConflictQueryView:
    left_claim_id: str
    right_claim_id: str
    subject_id: str
    predicate: str
    left_value: object
    right_value: object
    reason: str
    evidence: tuple[CanonicalEvidenceQueryView, ...]


@dataclass(frozen=True)
class CanonicalPopulationQueryView:
    workspace_id: str
    generation: str
    resource: str
    entities: tuple[CanonicalEntityQueryView, ...]
    candidate_count: int
    safely_enumerable: bool


class GraphTransaction(Protocol):
    def run(self, query: str, **parameters: object) -> Any: ...


class GraphSession(Protocol):
    def __enter__(self) -> GraphSession: ...

    def __exit__(self, *args: object) -> None: ...

    def execute_write(self, callback, *args: object, **kwargs: object) -> object: ...


class GraphDriver(Protocol):
    def verify_connectivity(self) -> None: ...

    def execute_query(self, query: str, **parameters: object) -> object: ...

    def session(self, **parameters: object) -> GraphSession: ...

    def close(self) -> None: ...


class Neo4jGraphAdapter:
    """The only application boundary allowed to execute Neo4j driver operations."""

    def __init__(self, workspace_id: str, driver: GraphDriver, *, database: str = "neo4j") -> None:
        if not workspace_id.strip():
            raise ValueError("workspace_id is required")
        self.workspace_id = workspace_id
        self.driver = driver
        self.database = database

    @classmethod
    def from_settings(
        cls,
        workspace_id: str,
        *,
        settings: Settings | None = None,
        secrets: SecretStore | None = None,
    ) -> Neo4jGraphAdapter:
        active = settings or get_settings()
        password = active.neo4j_password or (secrets or SecretStore()).get("neo4j_password")
        if not password:
            raise Neo4jConfigurationError("Neo4j credential is not configured")
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            active.neo4j_uri,
            auth=(active.neo4j_username, password),
            connection_timeout=active.neo4j_connection_timeout_seconds,
        )
        return cls(workspace_id, driver, database=active.neo4j_database)

    def __enter__(self) -> Neo4jGraphAdapter:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self.driver.close()

    def verify_connectivity(self) -> None:
        self.driver.verify_connectivity()

    def ensure_schema(self) -> None:
        statements = (
            "CREATE CONSTRAINT cortex_node_identity IF NOT EXISTS "
            "FOR (n:CortexNode) REQUIRE (n.workspace_id, n.layer, n.external_id) IS UNIQUE",
            "CREATE INDEX cortex_node_workspace IF NOT EXISTS "
            "FOR (n:CortexNode) ON (n.workspace_id)",
            "CREATE INDEX cortex_node_generation IF NOT EXISTS "
            "FOR (n:CortexNode) ON (n.workspace_id, n.layer, n.generation)",
            "CREATE CONSTRAINT cortex_alias_identity IF NOT EXISTS "
            "FOR (n:CortexAlias) REQUIRE (n.workspace_id, n.alias_id) IS UNIQUE",
            "CREATE CONSTRAINT cortex_mention_identity IF NOT EXISTS "
            "FOR (n:CortexMention) REQUIRE (n.workspace_id, n.mention_id) IS UNIQUE",
            "CREATE CONSTRAINT cortex_evidence_identity IF NOT EXISTS "
            "FOR (n:CortexEvidence) REQUIRE (n.workspace_id, n.evidence_id) IS UNIQUE",
            "CREATE CONSTRAINT cortex_identity_operation IF NOT EXISTS "
            "FOR (n:CortexIdentityOperation) REQUIRE (n.workspace_id, n.operation_id) IS UNIQUE",
            "CREATE CONSTRAINT cortex_claim_identity IF NOT EXISTS "
            "FOR (n:CortexClaim) REQUIRE (n.workspace_id, n.claim_id) IS UNIQUE",
        )
        for statement in statements:
            self.driver.execute_query(statement, database_=self.database)

    def extracted_node_count(self, generation: str) -> int:
        """Count one generation without allowing reads to cross workspace boundaries."""
        if not generation.strip():
            raise ValueError("generation is required")
        records, _, _ = self.driver.execute_query(
            "MATCH (n:CortexNode:ExtractedKnowledge "
            "{workspace_id: $workspace_id, layer: 'extracted', generation: $generation}) "
            "RETURN count(n) AS node_count",
            workspace_id=self.workspace_id,
            generation=generation,
            database_=self.database,
        )
        return int(records[0]["node_count"]) if records else 0

    @staticmethod
    def _upsert_canonical_entity_transaction(
        transaction: GraphTransaction,
        *,
        workspace_id: str,
        generation: str,
        entity: CanonicalEntity,
    ) -> None:
        transaction.run(
            "MERGE (n:CortexNode:CanonicalKnowledge:CanonicalEntity "
            "{workspace_id: $workspace_id, layer: 'canonical', external_id: $entity_id}) "
            "ON CREATE SET n.entity_type = $entity_type, n.display_name = $display_name, "
            "n.subtype = $subtype, n.authority = $authority, n.authority_rank = $authority_rank, "
            "n.status = $status, n.generation = $generation "
            "ON MATCH SET n.generation = $generation "
            "FOREACH (_ IN CASE WHEN coalesce(n.authority_rank, 0) <= $authority_rank "
            "THEN [1] ELSE [] END | SET n.entity_type = $entity_type, "
            "n.display_name = $display_name, n.subtype = $subtype, n.authority = $authority, "
            "n.authority_rank = $authority_rank, n.status = $status)",
            workspace_id=workspace_id,
            generation=generation,
            entity_id=entity.entity_id,
            entity_type=entity.entity_type.value,
            display_name=entity.display_name,
            subtype=entity.subtype,
            authority=entity.authority.name.lower(),
            authority_rank=int(entity.authority),
            status=entity.status,
        ).consume()
        if entity.aliases:
            transaction.run(
                "MATCH (n:CortexNode:CanonicalKnowledge:CanonicalEntity "
                "{workspace_id: $workspace_id, layer: 'canonical', external_id: $entity_id}) "
                "UNWIND $aliases AS row "
                "MERGE (a:CortexAlias:CanonicalKnowledge "
                "{workspace_id: $workspace_id, alias_id: row.alias_id}) "
                "ON CREATE SET a.value = row.value, a.normalized_value = row.normalized_value, "
                "a.authority = row.authority, a.authority_rank = row.authority_rank, "
                "a.active = row.active "
                "FOREACH (_ IN CASE WHEN coalesce(a.authority_rank, 0) <= row.authority_rank "
                "THEN [1] ELSE [] END | SET a.value = row.value, "
                "a.normalized_value = row.normalized_value, a.authority = row.authority, "
                "a.authority_rank = row.authority_rank, a.active = row.active) "
                "MERGE (n)-[:HAS_ALIAS]->(a)",
                workspace_id=workspace_id,
                entity_id=entity.entity_id,
                aliases=[
                    {
                        "alias_id": alias.alias_id,
                        "value": alias.value,
                        "normalized_value": alias.normalized_value,
                        "authority": alias.authority.name.lower(),
                        "authority_rank": int(alias.authority),
                        "active": alias.active,
                    }
                    for alias in entity.aliases
                ],
            ).consume()
        if entity.mentions:
            transaction.run(
                "MATCH (entity:CortexNode:CanonicalKnowledge:CanonicalEntity "
                "{workspace_id: $workspace_id, layer: 'canonical', external_id: $entity_id}) "
                "UNWIND $mentions AS row "
                "MERGE (w:CortexWorkspace {workspace_id: $workspace_id}) "
                "MERGE (d:CortexDocument:CanonicalKnowledge "
                "{workspace_id: $workspace_id, document_id: row.document_id}) "
                "MERGE (v:CortexDocumentVersion:CanonicalKnowledge "
                "{workspace_id: $workspace_id, document_version_id: row.document_version_id}) "
                "MERGE (l:CortexLogicalDocument:CanonicalKnowledge "
                "{workspace_id: $workspace_id, logical_document_id: row.logical_document_id}) "
                "MERGE (c:CortexChunk:CanonicalKnowledge "
                "{workspace_id: $workspace_id, chunk_id: row.chunk_id}) "
                "MERGE (e:CortexEvidence:CanonicalKnowledge "
                "{workspace_id: $workspace_id, evidence_id: row.evidence_id}) "
                "SET e.start_offset = row.start_offset, e.end_offset = row.end_offset, "
                "e.source_text = row.source_text, e.extraction_run_id = row.extraction_run_id, "
                "e.provider = row.provider, e.model = row.model, "
                "e.prompt_version = row.prompt_version, e.schema_version = row.schema_version, "
                "e.confidence = row.confidence, e.validation_state = row.validation_state, "
                "e.generation = row.generation "
                "MERGE (m:CortexMention:CanonicalKnowledge "
                "{workspace_id: $workspace_id, mention_id: row.mention_id}) "
                "SET m.original_text = row.original_text, m.normalized_text = row.normalized_text, "
                "m.entity_type = row.entity_type, m.decision = row.decision "
                "MERGE (w)-[:HAS_DOCUMENT]->(d) "
                "MERGE (d)-[:HAS_VERSION]->(v) "
                "MERGE (v)-[:HAS_LOGICAL_DOCUMENT]->(l) "
                "MERGE (l)-[:HAS_CHUNK]->(c) "
                "MERGE (c)-[:HAS_EVIDENCE]->(e) "
                "MERGE (m)-[:SUPPORTED_BY]->(e) "
                "MERGE (m)-[:RESOLVES_TO]->(entity)",
                workspace_id=workspace_id,
                entity_id=entity.entity_id,
                mentions=[
                    {
                        **asdict(mention.provenance),
                        "evidence_id": mention.provenance.evidence_id,
                        "mention_id": mention.mention_id,
                        "original_text": mention.original_text,
                        "normalized_text": mention.normalized_text,
                        "entity_type": mention.entity_type.value,
                        "decision": mention.decision.value,
                    }
                    for mention in entity.mentions
                ],
            ).consume()

    def upsert_canonical_entity(self, entity: CanonicalEntity, generation: str) -> None:
        """Persist canonical knowledge without permitting lower-precedence overwrites."""
        if not generation.strip():
            raise ValueError("generation is required")
        if any(
            mention.provenance.workspace_id != self.workspace_id
            or mention.provenance.generation != generation
            for mention in entity.mentions
        ):
            raise ValueError("entity provenance must match the adapter workspace and generation")
        with self.driver.session(database=self.database) as session:
            session.execute_write(
                self._upsert_canonical_entity_transaction,
                workspace_id=self.workspace_id,
                generation=generation,
                entity=entity,
            )

    @staticmethod
    def _record_identity_operation_transaction(
        transaction: GraphTransaction, *, workspace_id: str, operation: IdentityOperation
    ) -> None:
        transaction.run(
            "MERGE (op:CortexIdentityOperation:CanonicalKnowledge "
            "{workspace_id: $workspace_id, operation_id: $operation_id}) "
            "ON CREATE SET op.kind = $kind, op.authority = $authority, "
            "op.authority_rank = $authority_rank, op.source_entity_ids_json = $source_ids_json, "
            "op.result_entity_ids_json = $result_ids_json, "
            "op.evidence_ids_json = $evidence_ids_json, op.reason = $reason, "
            "op.details_json = $details_json "
            "WITH op "
            "UNWIND $source_ids AS source_id "
            "MATCH (source:CortexNode:CanonicalKnowledge:CanonicalEntity "
            "{workspace_id: $workspace_id, layer: 'canonical', external_id: source_id}) "
            "MERGE (source)-[:IDENTITY_OPERATION_SOURCE]->(op) "
            "FOREACH (_ IN CASE WHEN NOT source_id IN $result_ids THEN [1] ELSE [] END | "
            "SET source.status = CASE WHEN $kind = 'split' THEN 'split' ELSE 'superseded' END, "
            "source.authority = $authority, source.authority_rank = $authority_rank) "
            "WITH DISTINCT op "
            "UNWIND $result_ids AS result_id "
            "MATCH (result:CortexNode:CanonicalKnowledge:CanonicalEntity "
            "{workspace_id: $workspace_id, layer: 'canonical', external_id: result_id}) "
            "MERGE (op)-[:IDENTITY_OPERATION_RESULT]->(result)",
            workspace_id=workspace_id,
            operation_id=operation.operation_id,
            kind=operation.kind.value,
            authority=operation.authority.name.lower(),
            authority_rank=int(operation.authority),
            source_ids=list(operation.source_entity_ids),
            result_ids=list(operation.result_entity_ids),
            source_ids_json=json.dumps(operation.source_entity_ids),
            result_ids_json=json.dumps(operation.result_entity_ids),
            evidence_ids_json=json.dumps(operation.evidence_ids),
            reason=operation.reason,
            details_json=json.dumps(operation.details, ensure_ascii=False, sort_keys=True),
        ).consume()

    def record_identity_operation(self, operation: IdentityOperation) -> None:
        with self.driver.session(database=self.database) as session:
            session.execute_write(
                self._record_identity_operation_transaction,
                workspace_id=self.workspace_id,
                operation=operation,
            )

    def list_canonical_entities(self, limit: int = 100) -> tuple[CanonicalEntityView, ...]:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        records, _, _ = self.driver.execute_query(
            "MATCH (n:CortexNode:CanonicalKnowledge:CanonicalEntity "
            "{workspace_id: $workspace_id, layer: 'canonical'}) "
            "OPTIONAL MATCH (n)-[:HAS_ALIAS]->(a:CortexAlias {workspace_id: $workspace_id}) "
            "WITH n, [item IN collect(a) WHERE item.active | item.value] AS aliases "
            "RETURN n.external_id AS entity_id, n.entity_type AS entity_type, "
            "n.display_name AS display_name, n.subtype AS subtype, n.authority AS authority, "
            "n.status AS status, aliases ORDER BY n.display_name LIMIT $limit",
            workspace_id=self.workspace_id,
            limit=limit,
            database_=self.database,
        )
        return tuple(
            CanonicalEntityView(
                record["entity_id"],
                record["entity_type"],
                record["display_name"],
                record["subtype"],
                record["authority"],
                record["status"],
                tuple(record["aliases"]),
            )
            for record in records
        )

    def list_generation_entities(
        self, generation: str, limit: int = 100
    ) -> tuple[CanonicalEntityView, ...]:
        """Return only active canonical identities from one workspace generation."""
        if not generation.strip() or not 1 <= limit <= 500:
            raise ValueError("generation and a bounded limit are required")
        records, _, _ = self.driver.execute_query(
            "MATCH (n:CortexNode:CanonicalKnowledge:CanonicalEntity "
            "{workspace_id: $workspace_id, layer: 'canonical', generation: $generation, "
            "status: 'active'}) "
            "OPTIONAL MATCH (n)-[:HAS_ALIAS]->(a:CortexAlias "
            "{workspace_id: $workspace_id, active: true}) "
            "WITH n, [item IN collect(a) WHERE item.active | item.value] AS aliases "
            "RETURN n.external_id AS entity_id, n.entity_type AS entity_type, "
            "n.display_name AS display_name, n.subtype AS subtype, n.authority AS authority, "
            "n.status AS status, aliases ORDER BY n.display_name LIMIT $limit",
            workspace_id=self.workspace_id,
            generation=generation,
            limit=limit,
            database_=self.database,
        )
        return tuple(
            CanonicalEntityView(
                record["entity_id"],
                record["entity_type"],
                record["display_name"],
                record["subtype"],
                record["authority"],
                record["status"],
                tuple(record["aliases"]),
            )
            for record in records
        )

    def identity_candidates(
        self, normalized_name: str, entity_type: EntityType
    ) -> tuple[ResolutionCandidate, ...]:
        """Return exact-name candidates with independent evidence/version support."""
        records, _, _ = self.driver.execute_query(
            "MATCH (n:CortexNode:CanonicalKnowledge:CanonicalEntity "
            "{workspace_id: $workspace_id, layer: 'canonical', entity_type: $entity_type}) "
            "OPTIONAL MATCH (n)-[:HAS_ALIAS]->(a:CortexAlias "
            "{workspace_id: $workspace_id, active: true}) "
            "WITH n, collect(DISTINCT a.normalized_value) + "
            "[toLower(trim(n.display_name))] AS aliases "
            "WHERE $normalized_name IN aliases "
            "OPTIONAL MATCH (m:CortexMention)-[:RESOLVES_TO]->(n) "
            "OPTIONAL MATCH (m)-[:SUPPORTED_BY]->(e:CortexEvidence "
            "{workspace_id: $workspace_id}) "
            "RETURN n.external_id AS entity_id, aliases, "
            "collect(DISTINCT e.evidence_id) AS evidence_ids, "
            "collect(DISTINCT e.document_version_id) AS version_ids",
            workspace_id=self.workspace_id,
            entity_type=entity_type.value,
            normalized_name=normalized_name,
            database_=self.database,
        )
        return tuple(
            ResolutionCandidate(
                record["entity_id"],
                entity_type,
                frozenset(value for value in record["aliases"] if value),
                frozenset(value for value in record["evidence_ids"] if value),
                frozenset(value for value in record["version_ids"] if value),
            )
            for record in records
        )

    def identity_history(self, limit: int = 100) -> tuple[IdentityHistoryView, ...]:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        records, _, _ = self.driver.execute_query(
            "MATCH (op:CortexIdentityOperation:CanonicalKnowledge "
            "{workspace_id: $workspace_id}) "
            "RETURN op.operation_id AS operation_id, op.kind AS kind, "
            "op.authority AS authority, op.source_entity_ids_json AS source_ids, "
            "op.result_entity_ids_json AS result_ids, op.evidence_ids_json AS evidence_ids, "
            "op.reason AS reason, op.details_json AS details "
            "ORDER BY op.operation_id DESC LIMIT $limit",
            workspace_id=self.workspace_id,
            limit=limit,
            database_=self.database,
        )
        return tuple(
            IdentityHistoryView(
                record["operation_id"],
                record["kind"],
                record["authority"],
                tuple(json.loads(record["source_ids"])),
                tuple(json.loads(record["result_ids"])),
                tuple(json.loads(record["evidence_ids"])),
                record["reason"],
                json.loads(record["details"]),
            )
            for record in records
        )

    def curation_fingerprint(self) -> str:
        """Hash every workspace-scoped user-curated identity decision and current value."""
        records, _, _ = self.driver.execute_query(
            "CALL () { "
            "MATCH (n:CortexNode:CanonicalKnowledge:CanonicalEntity "
            "{workspace_id: $workspace_id, authority: 'user_curated'}) "
            "RETURN 'entity' AS kind, n.external_id AS item_id, "
            "{entity_type: n.entity_type, display_name: n.display_name, "
            "status: n.status} AS value "
            "UNION ALL "
            "MATCH (a:CortexAlias:CanonicalKnowledge "
            "{workspace_id: $workspace_id, authority: 'user_curated'}) "
            "RETURN 'alias' AS kind, a.alias_id AS item_id, "
            "{value: a.value, normalized_value: a.normalized_value, active: a.active} AS value "
            "UNION ALL "
            "MATCH (op:CortexIdentityOperation:CanonicalKnowledge "
            "{workspace_id: $workspace_id, authority: 'user_curated'}) "
            "RETURN 'operation' AS kind, op.operation_id AS item_id, "
            "{kind: op.kind, source_ids: op.source_entity_ids_json, "
            "result_ids: op.result_entity_ids_json, evidence_ids: op.evidence_ids_json, "
            "reason: op.reason, details: op.details_json} AS value "
            "} RETURN kind, item_id, value ORDER BY kind, item_id",
            workspace_id=self.workspace_id,
            database_=self.database,
        )
        payload = [
            {
                "kind": record["kind"],
                "item_id": record["item_id"],
                "value": dict(record["value"]),
            }
            for record in records
        ]
        encoded = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _canonical_entity_rows(
        self, entity_ids: tuple[str, ...], generation: str | None = None
    ) -> tuple[dict, ...]:
        for entity_id in entity_ids:
            require_canonical_id(entity_id)
        records, _, _ = self.driver.execute_query(
            "MATCH (n:CortexNode:CanonicalKnowledge:CanonicalEntity "
            "{workspace_id: $workspace_id, layer: 'canonical'}) "
            "WHERE n.external_id IN $entity_ids "
            "AND ($generation IS NULL OR n.generation = $generation) "
            "RETURN n.external_id AS entity_id, n.entity_type AS entity_type, "
            "n.display_name AS display_name, n.subtype AS subtype",
            workspace_id=self.workspace_id,
            entity_ids=list(entity_ids),
            generation=generation,
            database_=self.database,
        )
        return tuple(dict(record) for record in records)

    def add_alias(self, entity_id: str, value: str, reason: str) -> IdentityOperation:
        require_canonical_id(entity_id)
        normalized = normalize_mention(value)
        if not normalized or not reason.strip():
            raise ValueError("alias value and curation reason are required")
        if len(self._canonical_entity_rows((entity_id,))) != 1:
            raise ValueError("canonical entity not found in this workspace")
        alias_id = new_canonical_id()
        operation = IdentityOperation(
            new_canonical_id(),
            IdentityDecisionKind.ALIAS_ADD,
            KnowledgeAuthority.USER_CURATED,
            (entity_id,),
            (entity_id,),
            (),
            reason,
            {"alias_id": alias_id, "value": value, "normalized_value": normalized},
        )
        with self.driver.session(database=self.database) as session:
            session.execute_write(
                self._alias_transaction,
                workspace_id=self.workspace_id,
                entity_id=entity_id,
                alias_id=alias_id,
                value=value,
                normalized_value=normalized,
                active=True,
                operation=operation,
            )
        return operation

    def remove_alias(self, entity_id: str, value: str, reason: str) -> IdentityOperation:
        require_canonical_id(entity_id)
        normalized = normalize_mention(value)
        if not normalized or not reason.strip():
            raise ValueError("alias value and curation reason are required")
        records, _, _ = self.driver.execute_query(
            "MATCH (n:CortexNode:CanonicalKnowledge:CanonicalEntity "
            "{workspace_id: $workspace_id, layer: 'canonical', external_id: $entity_id})"
            "-[:HAS_ALIAS]->(a:CortexAlias {workspace_id: $workspace_id, "
            "normalized_value: $normalized_value}) WHERE a.active "
            "RETURN a.alias_id AS alias_id, a.value AS value LIMIT 1",
            workspace_id=self.workspace_id,
            entity_id=entity_id,
            normalized_value=normalized,
            database_=self.database,
        )
        if not records:
            raise ValueError("active alias not found in this workspace")
        alias_id = records[0]["alias_id"]
        operation = IdentityOperation(
            new_canonical_id(),
            IdentityDecisionKind.ALIAS_REMOVE,
            KnowledgeAuthority.USER_CURATED,
            (entity_id,),
            (entity_id,),
            (),
            reason,
            {"alias_id": alias_id, "value": records[0]["value"]},
        )
        with self.driver.session(database=self.database) as session:
            session.execute_write(
                self._alias_transaction,
                workspace_id=self.workspace_id,
                entity_id=entity_id,
                alias_id=alias_id,
                value=records[0]["value"],
                normalized_value=normalized,
                active=False,
                operation=operation,
            )
        return operation

    @classmethod
    def _alias_transaction(
        cls,
        transaction: GraphTransaction,
        *,
        workspace_id: str,
        entity_id: str,
        alias_id: str,
        value: str,
        normalized_value: str,
        active: bool,
        operation: IdentityOperation,
    ) -> None:
        transaction.run(
            "MATCH (n:CortexNode:CanonicalKnowledge:CanonicalEntity "
            "{workspace_id: $workspace_id, layer: 'canonical', external_id: $entity_id}) "
            "MERGE (a:CortexAlias:CanonicalKnowledge "
            "{workspace_id: $workspace_id, alias_id: $alias_id}) "
            "SET a.value = $value, a.normalized_value = $normalized_value, "
            "a.authority = 'user_curated', a.authority_rank = 30, a.active = $active "
            "MERGE (n)-[:HAS_ALIAS]->(a)",
            workspace_id=workspace_id,
            entity_id=entity_id,
            alias_id=alias_id,
            value=value,
            normalized_value=normalized_value,
            active=active,
        ).consume()
        cls._record_identity_operation_transaction(
            transaction, workspace_id=workspace_id, operation=operation
        )

    def merge_canonical_entities(
        self,
        primary_entity_id: str,
        merged_entity_ids: tuple[str, ...],
        *,
        evidence_ids: tuple[str, ...],
        reason: str,
    ) -> IdentityOperation:
        entity_ids = (primary_entity_id, *merged_entity_ids)
        if not merged_entity_ids or len(set(entity_ids)) != len(entity_ids):
            raise ValueError("merge requires distinct primary and merged entity IDs")
        rows = self._canonical_entity_rows(entity_ids)
        if len(rows) != len(entity_ids):
            raise ValueError("every merge entity must exist in this workspace")
        if len({row["entity_type"] for row in rows}) != 1:
            raise ValueError("entities of different upper types cannot be merged")
        operation = IdentityOperation(
            new_canonical_id(),
            IdentityDecisionKind.MERGE,
            KnowledgeAuthority.USER_CURATED,
            entity_ids,
            (primary_entity_id,),
            evidence_ids,
            reason,
        )
        with self.driver.session(database=self.database) as session:
            session.execute_write(
                self._merge_transaction,
                workspace_id=self.workspace_id,
                primary_entity_id=primary_entity_id,
                merged_entity_ids=merged_entity_ids,
                operation=operation,
            )
        return operation

    @classmethod
    def _merge_transaction(
        cls,
        transaction: GraphTransaction,
        *,
        workspace_id: str,
        primary_entity_id: str,
        merged_entity_ids: tuple[str, ...],
        operation: IdentityOperation,
    ) -> None:
        transaction.run(
            "MATCH (primary:CortexNode:CanonicalKnowledge:CanonicalEntity "
            "{workspace_id: $workspace_id, layer: 'canonical', external_id: $primary_id}) "
            "MATCH (duplicate:CortexNode:CanonicalKnowledge:CanonicalEntity "
            "{workspace_id: $workspace_id, layer: 'canonical'}) "
            "WHERE duplicate.external_id IN $merged_ids "
            "OPTIONAL MATCH (duplicate)-[:HAS_ALIAS]->(alias:CortexAlias) "
            "FOREACH (_ IN CASE WHEN alias IS NULL THEN [] ELSE [1] END | "
            "MERGE (primary)-[:HAS_ALIAS]->(alias)) "
            "WITH DISTINCT primary, duplicate "
            "OPTIONAL MATCH (mention:CortexMention)-[old:RESOLVES_TO]->(duplicate) "
            "FOREACH (_ IN CASE WHEN old IS NULL THEN [] ELSE [1] END | SET old.active = false) "
            "FOREACH (_ IN CASE WHEN mention IS NULL THEN [] ELSE [1] END | "
            "MERGE (mention)-[:RESOLVES_TO {active: true}]->(primary)) "
            "SET primary.authority = 'user_curated', primary.authority_rank = 30",
            workspace_id=workspace_id,
            primary_id=primary_entity_id,
            merged_ids=list(merged_entity_ids),
        ).consume()
        cls._record_identity_operation_transaction(
            transaction, workspace_id=workspace_id, operation=operation
        )

    def split_canonical_entity(
        self,
        source_entity_id: str,
        partitions: tuple[tuple[str, tuple[str, ...]], ...],
        *,
        evidence_ids: tuple[str, ...],
        reason: str,
    ) -> IdentityOperation:
        require_canonical_id(source_entity_id)
        invalid_partition = any(
            not name.strip() or not mentions for name, mentions in partitions
        )
        if len(partitions) < 2 or invalid_partition:
            raise ValueError("split requires at least two named, non-empty mention partitions")
        records, _, _ = self.driver.execute_query(
            "MATCH (m:CortexMention {workspace_id: $workspace_id})"
            "-[r:RESOLVES_TO]->(source:CortexNode:CanonicalKnowledge:CanonicalEntity "
            "{workspace_id: $workspace_id, layer: 'canonical', external_id: $source_id}) "
            "WHERE coalesce(r.active, true) RETURN source.entity_type AS entity_type, "
            "m.mention_id AS mention_id",
            workspace_id=self.workspace_id,
            source_id=source_entity_id,
            database_=self.database,
        )
        current_mentions = {record["mention_id"] for record in records}
        assigned = [mention_id for _, mention_ids in partitions for mention_id in mention_ids]
        if len(assigned) != len(set(assigned)) or set(assigned) != current_mentions:
            raise ValueError("split must assign every active mention exactly once")
        if not records:
            raise ValueError("canonical entity with active mentions not found")
        result_rows = [
            {
                "entity_id": new_canonical_id(),
                "display_name": display_name,
                "mention_ids": list(mention_ids),
            }
            for display_name, mention_ids in partitions
        ]
        operation = IdentityOperation(
            new_canonical_id(),
            IdentityDecisionKind.SPLIT,
            KnowledgeAuthority.USER_CURATED,
            (source_entity_id,),
            tuple(row["entity_id"] for row in result_rows),
            evidence_ids,
            reason,
        )
        with self.driver.session(database=self.database) as session:
            session.execute_write(
                self._split_transaction,
                workspace_id=self.workspace_id,
                source_entity_id=source_entity_id,
                entity_type=records[0]["entity_type"],
                result_rows=result_rows,
                operation=operation,
            )
        return operation

    @classmethod
    def _split_transaction(
        cls,
        transaction: GraphTransaction,
        *,
        workspace_id: str,
        source_entity_id: str,
        entity_type: str,
        result_rows: list[dict[str, object]],
        operation: IdentityOperation,
    ) -> None:
        transaction.run(
            "MATCH (source:CortexNode:CanonicalKnowledge:CanonicalEntity "
            "{workspace_id: $workspace_id, layer: 'canonical', external_id: $source_id}) "
            "SET source.status = 'split', source.authority = 'user_curated', "
            "source.authority_rank = 30 "
            "WITH source UNWIND $results AS row "
            "CREATE (result:CortexNode:CanonicalKnowledge:CanonicalEntity "
            "{workspace_id: $workspace_id, layer: 'canonical', external_id: row.entity_id, "
            "entity_type: $entity_type, display_name: row.display_name, authority: 'user_curated', "
            "authority_rank: 30, status: 'active'}) "
            "WITH source, result, row "
            "MATCH (mention:CortexMention {workspace_id: $workspace_id})"
            "-[old:RESOLVES_TO]->(source) WHERE mention.mention_id IN row.mention_ids "
            "SET old.active = false MERGE (mention)-[:RESOLVES_TO {active: true}]->(result)",
            workspace_id=workspace_id,
            source_id=source_entity_id,
            entity_type=entity_type,
            results=result_rows,
        ).consume()
        cls._record_identity_operation_transaction(
            transaction, workspace_id=workspace_id, operation=operation
        )

    def entity_evidence(self, entity_id: str, limit: int = 200) -> tuple[EntityEvidenceView, ...]:
        require_canonical_id(entity_id)
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        records, _, _ = self.driver.execute_query(
            "MATCH (m:CortexMention {workspace_id: $workspace_id})"
            "-[resolution:RESOLVES_TO]->(n:CortexNode:CanonicalKnowledge:CanonicalEntity "
            "{workspace_id: $workspace_id, layer: 'canonical', external_id: $entity_id}) "
            "WHERE coalesce(resolution.active, true) "
            "MATCH (m)-[:SUPPORTED_BY]->(e:CortexEvidence {workspace_id: $workspace_id}) "
            "MATCH (c:CortexChunk {workspace_id: $workspace_id})-[:HAS_EVIDENCE]->(e) "
            "MATCH (l:CortexLogicalDocument {workspace_id: $workspace_id})-[:HAS_CHUNK]->(c) "
            "MATCH (v:CortexDocumentVersion {workspace_id: $workspace_id})"
            "-[:HAS_LOGICAL_DOCUMENT]->(l) "
            "MATCH (d:CortexDocument {workspace_id: $workspace_id})-[:HAS_VERSION]->(v) "
            "RETURN e.evidence_id AS evidence_id, m.mention_id AS mention_id, "
            "m.original_text AS original_text, d.document_id AS document_id, "
            "v.document_version_id AS document_version_id, "
            "l.logical_document_id AS logical_document_id, c.chunk_id AS chunk_id, "
            "e.start_offset AS start_offset, e.end_offset AS end_offset, "
            "e.source_text AS source_text, e.extraction_run_id AS extraction_run_id, "
            "e.provider AS provider, e.model AS model, e.prompt_version AS prompt_version, "
            "e.schema_version AS schema_version, e.confidence AS confidence, "
            "e.validation_state AS validation_state, e.generation AS generation "
            "ORDER BY e.evidence_id LIMIT $limit",
            workspace_id=self.workspace_id,
            entity_id=entity_id,
            limit=limit,
            database_=self.database,
        )
        return tuple(EntityEvidenceView(**dict(record)) for record in records)

    def query_canonical_entities(
        self, generation: str, entity_ids: tuple[str, ...]
    ) -> tuple[CanonicalEntityQueryView, ...]:
        """Read canonical identities and exact evidence for one workspace generation."""
        if not generation.strip():
            raise ValueError("generation is required")
        rows = self._canonical_entity_rows(entity_ids, generation)
        output = []
        for row in rows:
            evidence = tuple(
                CanonicalEvidenceQueryView(
                    item.evidence_id,
                    item.document_id,
                    item.document_version_id,
                    item.logical_document_id,
                    item.chunk_id,
                    item.start_offset,
                    item.end_offset,
                    item.source_text,
                    item.confidence,
                    item.generation,
                )
                for item in self.entity_evidence(row["entity_id"])
                if item.generation == generation
            )
            output.append(
                CanonicalEntityQueryView(
                    row["entity_id"],
                    row["entity_type"],
                    row["display_name"],
                    row.get("subtype"),
                    evidence,
                )
            )
        return tuple(output)

    def query_canonical_population(
        self, generation: str, resource: str, *, safe_limit: int = 500
    ) -> CanonicalPopulationQueryView:
        """Snapshot a bounded canonical population without upgrading truncation to completeness."""
        if not generation.strip() or not resource.strip() or not 1 <= safe_limit <= 500:
            raise ValueError("generation, resource, and a safe population limit are required")
        counts, _, _ = self.driver.execute_query(
            "MATCH (n:CortexNode:CanonicalKnowledge:CanonicalEntity "
            "{workspace_id: $workspace_id, layer: 'canonical', generation: $generation, "
            "entity_type: $resource, status: 'active'}) RETURN count(n) AS candidate_count",
            workspace_id=self.workspace_id,
            generation=generation,
            resource=resource,
            database_=self.database,
        )
        candidate_count = int(counts[0]["candidate_count"]) if counts else 0
        records, _, _ = self.driver.execute_query(
            "MATCH (n:CortexNode:CanonicalKnowledge:CanonicalEntity "
            "{workspace_id: $workspace_id, layer: 'canonical', generation: $generation, "
            "entity_type: $resource, status: 'active'}) "
            "RETURN n.external_id AS entity_id ORDER BY entity_id LIMIT $limit",
            workspace_id=self.workspace_id,
            generation=generation,
            resource=resource,
            limit=safe_limit,
            database_=self.database,
        )
        ids = tuple(record["entity_id"] for record in records)
        safely_enumerable = candidate_count <= safe_limit
        selected = ids
        entities = self.query_canonical_entities(generation, selected) if selected else ()
        return CanonicalPopulationQueryView(
            self.workspace_id,
            generation,
            resource,
            entities,
            candidate_count,
            safely_enumerable,
        )

    def query_canonical_artifact_evidence(
        self, generation: str, artifact_ids: tuple[str, ...], *, limit: int = 500
    ) -> tuple[CanonicalEvidenceQueryView, ...]:
        if not generation.strip() or not 1 <= limit <= 500:
            raise ValueError("generation and bounded evidence limit are required")
        records, _, _ = self.driver.execute_query(
            "MATCH (artifact:CortexNode:CanonicalKnowledge:CanonicalArtifact "
            "{workspace_id: $workspace_id, layer: 'canonical'})-[:SUPPORTED_BY]->"
            "(e:CortexEvidence {workspace_id: $workspace_id, generation: $generation}) "
            "MATCH (c:CortexChunk {workspace_id: $workspace_id})-[:HAS_EVIDENCE]->(e) "
            "MATCH (l:CortexLogicalDocument {workspace_id: $workspace_id})-[:HAS_CHUNK]->(c) "
            "MATCH (v:CortexDocumentVersion {workspace_id: $workspace_id})"
            "-[:HAS_LOGICAL_DOCUMENT]->(l) "
            "MATCH (d:CortexDocument {workspace_id: $workspace_id})-[:HAS_VERSION]->(v) "
            "WHERE artifact.external_id IN $artifact_ids "
            "RETURN DISTINCT e.evidence_id AS evidence_id, d.document_id AS document_id, "
            "v.document_version_id AS document_version_id, "
            "l.logical_document_id AS logical_document_id, c.chunk_id AS chunk_id, "
            "e.start_offset AS start_offset, e.end_offset AS end_offset, "
            "e.source_text AS source_text, e.confidence AS confidence, "
            "e.generation AS generation ORDER BY evidence_id LIMIT $limit",
            workspace_id=self.workspace_id,
            generation=generation,
            artifact_ids=list(artifact_ids),
            limit=limit,
            database_=self.database,
        )
        return tuple(CanonicalEvidenceQueryView(**dict(record)) for record in records)

    def query_canonical_paths(
        self,
        generation: str,
        start_entity_ids: tuple[str, ...],
        relation_type: str,
        direction: str,
        minimum_hops: int,
        maximum_hops: int,
        *,
        limit: int = 500,
    ) -> tuple[CanonicalPathQueryView, ...]:
        """Traverse only fixed canonical Cortex relationships; no driver leaks to engines."""
        if not generation.strip() or not relation_type.strip():
            raise ValueError("generation and relation type are required")
        if direction not in {"outgoing", "incoming", "either"}:
            raise ValueError("unsupported graph direction")
        if not 1 <= minimum_hops <= maximum_hops <= 10 or not 1 <= limit <= 500:
            raise ValueError("graph traversal bounds are invalid")
        for entity_id in start_entity_ids:
            require_canonical_id(entity_id)
        arrows = {
            "outgoing": ("-", "->"),
            "incoming": ("<-", "-"),
            "either": ("-", "-"),
        }[direction]
        pattern = (
            f"{arrows[0]}[rels:CORTEX_CANONICAL_RELATION*"
            f"{minimum_hops}..{maximum_hops}]{arrows[1]}"
        )
        records, _, _ = self.driver.execute_query(
            "MATCH path=(start:CortexNode:CanonicalKnowledge:CanonicalEntity "
            "{workspace_id: $workspace_id, layer: 'canonical'})"
            + pattern
            + "(target:CortexNode:CanonicalKnowledge:CanonicalEntity "
            "{workspace_id: $workspace_id, layer: 'canonical'}) "
            "WHERE start.external_id IN $start_entity_ids "
            "AND all(rel IN rels WHERE rel.workspace_id = $workspace_id "
            "AND rel.generation = $generation AND rel.relation_type = $relation_type) "
            "RETURN [node IN nodes(path) | node.external_id] AS node_ids, "
            "[rel IN rels | rel.relation_id] AS relation_ids, "
            "[rel IN rels | rel.relation_type] AS relation_types "
            "ORDER BY relation_ids LIMIT $limit",
            workspace_id=self.workspace_id,
            generation=generation,
            start_entity_ids=list(start_entity_ids),
            relation_type=relation_type,
            limit=limit,
            database_=self.database,
        )
        output = []
        for record in records:
            node_ids = tuple(record["node_ids"])
            relation_ids = tuple(record["relation_ids"])
            evidence = self.query_canonical_artifact_evidence(generation, relation_ids)
            output.append(
                CanonicalPathQueryView(
                    "path-" + "-".join(relation_ids),
                    node_ids,
                    relation_ids,
                    tuple(record["relation_types"]),
                    evidence,
                )
            )
        return tuple(output)

    def query_event_paths(
        self,
        generation: str,
        entity_ids: tuple[str, ...],
        *,
        normalized_start: str | None = None,
        normalized_end: str | None = None,
        limit: int = 500,
    ) -> tuple[CanonicalPathQueryView, ...]:
        for entity_id in entity_ids:
            require_canonical_id(entity_id)
        if not generation.strip() or not 1 <= limit <= 500:
            raise ValueError("generation and bounded event limit are required")
        records, _, _ = self.driver.execute_query(
            "MATCH (event:CortexNode:CanonicalKnowledge:CanonicalArtifact "
            "{workspace_id: $workspace_id, layer: 'canonical', artifact_type: 'event'})"
            "-[participation:HAS_PARTICIPANT {workspace_id: $workspace_id, "
            "generation: $generation}]->"
            "(entity:CortexNode:CanonicalKnowledge:CanonicalEntity "
            "{workspace_id: $workspace_id, layer: 'canonical'}) "
            "OPTIONAL MATCH (event)-[:OCCURRED_AT {workspace_id: $workspace_id, "
            "generation: $generation}]->(temporal:CortexNode:CanonicalKnowledge) "
            "WHERE entity.external_id IN $entity_ids "
            "AND ($normalized_start IS NULL OR temporal.normalized_start >= $normalized_start) "
            "AND ($normalized_end IS NULL OR "
            "coalesce(temporal.normalized_end, temporal.normalized_start) <= $normalized_end) "
            "RETURN entity.external_id AS entity_id, event.external_id AS event_id, "
            "participation.role AS role, temporal.external_id AS temporal_id "
            "ORDER BY event_id LIMIT $limit",
            workspace_id=self.workspace_id,
            generation=generation,
            entity_ids=list(entity_ids),
            normalized_start=normalized_start,
            normalized_end=normalized_end,
            limit=limit,
            database_=self.database,
        )
        output = []
        for record in records:
            artifact_ids = tuple(
                item for item in (record["event_id"], record.get("temporal_id")) if item
            )
            output.append(
                CanonicalPathQueryView(
                    f"event-path-{record['event_id']}-{record['entity_id']}",
                    (record["entity_id"], record["event_id"]),
                    (f"participation:{record['event_id']}:{record['entity_id']}",),
                    (f"event_participation:{record['role']}",),
                    self.query_canonical_artifact_evidence(generation, artifact_ids),
                )
            )
        return tuple(output)

    def query_claim_conflicts(
        self, generation: str, subject_ids: tuple[str, ...], *, limit: int = 500
    ) -> tuple[CanonicalConflictQueryView, ...]:
        if not generation.strip() or not 1 <= limit <= 500:
            raise ValueError("generation and bounded conflict limit are required")
        records, _, _ = self.driver.execute_query(
            "MATCH (left:CortexClaim:CanonicalKnowledge "
            "{workspace_id: $workspace_id, generation: $generation})"
            "-[conflict:CONFLICTS_WITH]->(right:CortexClaim:CanonicalKnowledge "
            "{workspace_id: $workspace_id, generation: $generation}) "
            "WHERE left.subject_id IN $subject_ids "
            "OPTIONAL MATCH (left)-[:SUPPORTED_BY]->(le:CortexEvidence) "
            "OPTIONAL MATCH (right)-[:SUPPORTED_BY]->(re:CortexEvidence) "
            "RETURN left.claim_id AS left_claim_id, right.claim_id AS right_claim_id, "
            "left.subject_id AS subject_id, left.predicate AS predicate, "
            "left.value_json AS left_value, right.value_json AS right_value, "
            "conflict.reason AS reason, "
            "[item IN collect(DISTINCT le) + collect(DISTINCT re) WHERE item IS NOT NULL | "
            "item.evidence_id] AS evidence_ids ORDER BY left_claim_id LIMIT $limit",
            workspace_id=self.workspace_id,
            generation=generation,
            subject_ids=list(subject_ids),
            limit=limit,
            database_=self.database,
        )
        output = []
        for record in records:
            evidence = self.query_evidence_by_id(
                generation, tuple(record["evidence_ids"])
            )
            output.append(
                CanonicalConflictQueryView(
                    record["left_claim_id"],
                    record["right_claim_id"],
                    record["subject_id"],
                    record["predicate"],
                    json.loads(record["left_value"]),
                    json.loads(record["right_value"]),
                    record["reason"],
                    evidence,
                )
            )
        return tuple(output)

    def query_evidence_by_id(
        self, generation: str, evidence_ids: tuple[str, ...], *, limit: int = 500
    ) -> tuple[CanonicalEvidenceQueryView, ...]:
        records, _, _ = self.driver.execute_query(
            "MATCH (d:CortexDocument {workspace_id: $workspace_id})-[:HAS_VERSION]->"
            "(v:CortexDocumentVersion {workspace_id: $workspace_id})"
            "-[:HAS_LOGICAL_DOCUMENT]->(l:CortexLogicalDocument "
            "{workspace_id: $workspace_id})-[:HAS_CHUNK]->"
            "(c:CortexChunk {workspace_id: $workspace_id})-[:HAS_EVIDENCE]->"
            "(e:CortexEvidence {workspace_id: $workspace_id, generation: $generation}) "
            "WHERE e.evidence_id IN $evidence_ids "
            "RETURN e.evidence_id AS evidence_id, d.document_id AS document_id, "
            "v.document_version_id AS document_version_id, "
            "l.logical_document_id AS logical_document_id, c.chunk_id AS chunk_id, "
            "e.start_offset AS start_offset, e.end_offset AS end_offset, "
            "e.source_text AS source_text, e.confidence AS confidence, "
            "e.generation AS generation ORDER BY evidence_id LIMIT $limit",
            workspace_id=self.workspace_id,
            generation=generation,
            evidence_ids=list(evidence_ids),
            limit=limit,
            database_=self.database,
        )
        return tuple(CanonicalEvidenceQueryView(**dict(record)) for record in records)

    @staticmethod
    def _upsert_claim_transaction(
        transaction: GraphTransaction, *, workspace_id: str, claim: KnowledgeClaim
    ) -> None:
        transaction.run(
            "MERGE (claim:CortexClaim:CanonicalKnowledge "
            "{workspace_id: $workspace_id, claim_id: $claim_id}) "
            "ON CREATE SET claim.subject_id = $subject_id, claim.predicate = $predicate, "
            "claim.value_json = $value_json, claim.stage = $stage, claim.authority = $authority, "
            "claim.authority_rank = $authority_rank, claim.generation = $generation, "
            "claim.validator_json = $validator_json, claim.conflicted = $conflicted "
            "FOREACH (_ IN CASE WHEN coalesce(claim.authority_rank, 0) <= $authority_rank "
            "THEN [1] ELSE [] END | SET claim.subject_id = $subject_id, "
            "claim.predicate = $predicate, claim.value_json = $value_json, claim.stage = $stage, "
            "claim.authority = $authority, claim.authority_rank = $authority_rank, "
            "claim.generation = $generation, claim.validator_json = $validator_json, "
            "claim.conflicted = $conflicted) "
            "FOREACH (_ IN CASE WHEN $stage = 'verified_fact' THEN [1] ELSE [] END | "
            "SET claim:VerifiedFact)",
            workspace_id=workspace_id,
            claim_id=claim.claim_id,
            subject_id=claim.subject_id,
            predicate=claim.predicate,
            value_json=json.dumps(claim.value, ensure_ascii=False, sort_keys=True),
            stage=claim.stage.value,
            authority=claim.authority.name.lower(),
            authority_rank=int(claim.authority),
            generation=claim.generation,
            validator_json=(
                json.dumps(asdict(claim.validator), ensure_ascii=False, sort_keys=True)
                if claim.validator
                else None
            ),
            conflicted=claim.conflicted,
        ).consume()
        if claim.evidence:
            transaction.run(
                "MATCH (claim:CortexClaim:CanonicalKnowledge "
                "{workspace_id: $workspace_id, claim_id: $claim_id}) "
                "UNWIND $evidence AS row "
                "MERGE (w:CortexWorkspace {workspace_id: $workspace_id}) "
                "MERGE (d:CortexDocument:CanonicalKnowledge "
                "{workspace_id: $workspace_id, document_id: row.document_id}) "
                "MERGE (v:CortexDocumentVersion:CanonicalKnowledge "
                "{workspace_id: $workspace_id, document_version_id: row.document_version_id}) "
                "MERGE (l:CortexLogicalDocument:CanonicalKnowledge "
                "{workspace_id: $workspace_id, logical_document_id: row.logical_document_id}) "
                "MERGE (c:CortexChunk:CanonicalKnowledge "
                "{workspace_id: $workspace_id, chunk_id: row.chunk_id}) "
                "MERGE (e:CortexEvidence:CanonicalKnowledge "
                "{workspace_id: $workspace_id, evidence_id: row.evidence_id}) "
                "SET e.start_offset = row.start_offset, e.end_offset = row.end_offset, "
                "e.source_text = row.source_text, e.extraction_run_id = row.extraction_run_id, "
                "e.provider = row.provider, e.model = row.model, "
                "e.prompt_version = row.prompt_version, e.schema_version = row.schema_version, "
                "e.confidence = row.confidence, e.validation_state = row.validation_state, "
                "e.generation = row.generation "
                "MERGE (w)-[:HAS_DOCUMENT]->(d) MERGE (d)-[:HAS_VERSION]->(v) "
                "MERGE (v)-[:HAS_LOGICAL_DOCUMENT]->(l) MERGE (l)-[:HAS_CHUNK]->(c) "
                "MERGE (c)-[:HAS_EVIDENCE]->(e) MERGE (claim)-[:SUPPORTED_BY]->(e)",
                workspace_id=workspace_id,
                claim_id=claim.claim_id,
                evidence=[
                    {**asdict(item), "evidence_id": item.evidence_id}
                    for item in claim.evidence
                ],
            ).consume()

    def upsert_claim(self, claim: KnowledgeClaim) -> None:
        if any(
            item.workspace_id != self.workspace_id or item.generation != claim.generation
            for item in claim.evidence
        ):
            raise ValueError("claim evidence must match the adapter workspace and generation")
        with self.driver.session(database=self.database) as session:
            session.execute_write(
                self._upsert_claim_transaction,
                workspace_id=self.workspace_id,
                claim=claim,
            )

    @staticmethod
    def _upsert_canonical_artifact_transaction(
        transaction: GraphTransaction,
        *,
        workspace_id: str,
        artifact_id: str,
        artifact_type: str,
        generation: str,
        authority: KnowledgeAuthority,
        properties: dict[str, object],
        evidence: tuple,
    ) -> None:
        transaction.run(
            "MERGE (n:CortexNode:CanonicalKnowledge:CanonicalArtifact "
            "{workspace_id: $workspace_id, layer: 'canonical', external_id: $artifact_id}) "
            "ON CREATE SET n.artifact_type = $artifact_type, n.generation = $generation, "
            "n.authority = $authority, n.authority_rank = $authority_rank, "
            "n.properties_json = $properties_json "
            "FOREACH (_ IN CASE WHEN coalesce(n.authority_rank, 0) <= $authority_rank "
            "THEN [1] ELSE [] END | SET n.artifact_type = $artifact_type, "
            "n.generation = $generation, n.authority = $authority, "
            "n.authority_rank = $authority_rank, n.properties_json = $properties_json) "
            "WITH n UNWIND $evidence AS row "
            "MERGE (w:CortexWorkspace {workspace_id: $workspace_id}) "
            "MERGE (d:CortexDocument:CanonicalKnowledge "
            "{workspace_id: $workspace_id, document_id: row.document_id}) "
            "MERGE (v:CortexDocumentVersion:CanonicalKnowledge "
            "{workspace_id: $workspace_id, document_version_id: row.document_version_id}) "
            "MERGE (l:CortexLogicalDocument:CanonicalKnowledge "
            "{workspace_id: $workspace_id, logical_document_id: row.logical_document_id}) "
            "MERGE (c:CortexChunk:CanonicalKnowledge "
            "{workspace_id: $workspace_id, chunk_id: row.chunk_id}) "
            "MERGE (e:CortexEvidence:CanonicalKnowledge "
            "{workspace_id: $workspace_id, evidence_id: row.evidence_id}) "
            "SET e.source_text = row.source_text, e.start_offset = row.start_offset, "
            "e.end_offset = row.end_offset, e.generation = row.generation, "
            "e.extraction_run_id = row.extraction_run_id, e.provider = row.provider, "
            "e.model = row.model, e.prompt_version = row.prompt_version, "
            "e.schema_version = row.schema_version, e.confidence = row.confidence, "
            "e.validation_state = row.validation_state "
            "MERGE (w)-[:HAS_DOCUMENT]->(d) MERGE (d)-[:HAS_VERSION]->(v) "
            "MERGE (v)-[:HAS_LOGICAL_DOCUMENT]->(l) MERGE (l)-[:HAS_CHUNK]->(c) "
            "MERGE (c)-[:HAS_EVIDENCE]->(e) MERGE (n)-[:SUPPORTED_BY]->(e)",
            workspace_id=workspace_id,
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            generation=generation,
            authority=authority.name.lower(),
            authority_rank=int(authority),
            properties_json=json.dumps(properties, ensure_ascii=False, sort_keys=True),
            evidence=[{**asdict(item), "evidence_id": item.evidence_id} for item in evidence],
        ).consume()
        if artifact_type == "relation":
            transaction.run(
                "MATCH (source:CortexNode:CanonicalKnowledge:CanonicalEntity "
                "{workspace_id: $workspace_id, layer: 'canonical', "
                "external_id: $source_entity_id}) "
                "MATCH (target:CortexNode:CanonicalKnowledge:CanonicalEntity "
                "{workspace_id: $workspace_id, layer: 'canonical', "
                "external_id: $target_entity_id}) "
                "MERGE (source)-[rel:CORTEX_CANONICAL_RELATION "
                "{workspace_id: $workspace_id, relation_id: $artifact_id}]->(target) "
                "SET rel.generation = $generation, rel.relation_type = $relation_type, "
                "rel.conflicted = $conflicted",
                workspace_id=workspace_id,
                artifact_id=artifact_id,
                generation=generation,
                source_entity_id=properties["source_entity_id"],
                target_entity_id=properties["target_entity_id"],
                relation_type=properties["relation_type"],
                conflicted=properties["conflicted"],
            ).consume()
        elif artifact_type == "event":
            transaction.run(
                "MATCH (event:CortexNode:CanonicalKnowledge:CanonicalArtifact "
                "{workspace_id: $workspace_id, layer: 'canonical', "
                "external_id: $artifact_id}) "
                "SET event.event_type = $event_type, event.display_name = $display_name, "
                "event.temporal_expression_ids = $temporal_ids "
                "WITH event UNWIND $participants AS participant "
                "MATCH (entity:CortexNode:CanonicalKnowledge:CanonicalEntity "
                "{workspace_id: $workspace_id, layer: 'canonical', "
                "external_id: participant.entity_id}) "
                "MERGE (event)-[edge:HAS_PARTICIPANT "
                "{workspace_id: $workspace_id, entity_id: participant.entity_id}]->(entity) "
                "SET edge.role = participant.role, edge.generation = $generation",
                workspace_id=workspace_id,
                artifact_id=artifact_id,
                generation=generation,
                event_type=properties["event_type"],
                display_name=properties["display_name"],
                temporal_ids=properties["temporal_expression_ids"],
                participants=properties["participants"],
            ).consume()
        elif artifact_type == "temporal":
            transaction.run(
                "MATCH (temporal:CortexNode:CanonicalKnowledge:CanonicalArtifact "
                "{workspace_id: $workspace_id, layer: 'canonical', "
                "external_id: $artifact_id}) "
                "SET temporal.normalized_start = $normalized_start, "
                "temporal.normalized_end = $normalized_end, temporal.semantic_role = $role, "
                "temporal.precision = $precision, temporal.uncertain = $uncertain "
                "WITH temporal MATCH (event:CortexNode:CanonicalKnowledge:CanonicalArtifact "
                "{workspace_id: $workspace_id, layer: 'canonical', artifact_type: 'event'}) "
                "WHERE $artifact_id IN coalesce(event.temporal_expression_ids, []) "
                "MERGE (event)-[:OCCURRED_AT {workspace_id: $workspace_id, "
                "generation: $generation}]->(temporal)",
                workspace_id=workspace_id,
                artifact_id=artifact_id,
                generation=generation,
                normalized_start=properties["normalized_start"],
                normalized_end=properties["normalized_end"],
                role=properties["semantic_role"],
                precision=properties["precision"],
                uncertain=properties["uncertain"],
            ).consume()

    def _upsert_canonical_artifact(
        self,
        artifact_id: str,
        artifact_type: str,
        generation: str,
        authority: KnowledgeAuthority,
        properties: dict[str, object],
        evidence: tuple,
    ) -> None:
        if any(
            item.workspace_id != self.workspace_id or item.generation != generation
            for item in evidence
        ):
            raise ValueError("artifact evidence must match the adapter workspace and generation")
        with self.driver.session(database=self.database) as session:
            session.execute_write(
                self._upsert_canonical_artifact_transaction,
                workspace_id=self.workspace_id,
                artifact_id=artifact_id,
                artifact_type=artifact_type,
                generation=generation,
                authority=authority,
                properties=properties,
                evidence=evidence,
            )

    def upsert_relation(self, relation: CanonicalRelation) -> None:
        self._upsert_canonical_artifact(
            relation.relation_id,
            "relation",
            relation.generation,
            relation.authority,
            {
                "source_entity_id": relation.source_entity_id,
                "target_entity_id": relation.target_entity_id,
                "relation_type": relation.relation_type,
                "support": relation.support.value,
                "conflicted": relation.conflicted,
                **relation.properties,
            },
            relation.evidence,
        )

    def upsert_event(self, event: CanonicalEvent) -> None:
        self._upsert_canonical_artifact(
            event.event_id,
            "event",
            event.generation,
            event.authority,
            {
                "event_type": event.event_type,
                "display_name": event.display_name,
                "participants": [asdict(item) for item in event.participants],
                "temporal_expression_ids": list(event.temporal_expression_ids),
            },
            event.evidence,
        )

    def upsert_temporal(self, temporal: TemporalExpression) -> None:
        self._upsert_canonical_artifact(
            temporal.temporal_id,
            "temporal",
            temporal.generation,
            KnowledgeAuthority.EXTRACTED,
            {
                "original_text": temporal.original_text,
                "normalized_start": temporal.normalized_start,
                "normalized_end": temporal.normalized_end,
                "semantic_role": temporal.semantic_role,
                "precision": temporal.precision.value,
                "uncertain": temporal.uncertain,
            },
            (temporal.provenance,),
        )

    def link_claim_conflict(self, conflict: ClaimConflict) -> None:
        for claim_id in (conflict.left_claim_id, conflict.right_claim_id):
            require_canonical_id(claim_id)
        self.driver.execute_query(
            "MATCH (left:CortexClaim:CanonicalKnowledge "
            "{workspace_id: $workspace_id, claim_id: $left_claim_id}) "
            "MATCH (right:CortexClaim:CanonicalKnowledge "
            "{workspace_id: $workspace_id, claim_id: $right_claim_id}) "
            "MERGE (left)-[conflict:CONFLICTS_WITH]->(right) "
            "SET conflict.reason = $reason, left.conflicted = true, right.conflicted = true",
            workspace_id=self.workspace_id,
            left_claim_id=conflict.left_claim_id,
            right_claim_id=conflict.right_claim_id,
            reason=conflict.reason,
            database_=self.database,
        )

    @staticmethod
    def _validate_generation(
        generation: str,
        nodes: tuple[GraphNode, ...],
        relationships: tuple[GraphRelationship, ...],
    ) -> None:
        if not generation.strip():
            raise ValueError("generation is required")
        if any(node.generation != generation for node in nodes):
            raise ValueError("all graph nodes must belong to the requested generation")
        if any(relationship.generation != generation for relationship in relationships):
            raise ValueError("all graph relationships must belong to the requested generation")
        node_ids = {node.external_id for node in nodes}
        if len(node_ids) != len(nodes):
            raise ValueError("graph node external IDs must be unique within a generation")
        relationship_ids = {relationship.external_id for relationship in relationships}
        if len(relationship_ids) != len(relationships):
            raise ValueError("graph relationship external IDs must be unique within a generation")
        for relationship in relationships:
            if relationship.source_id not in node_ids or relationship.target_id not in node_ids:
                raise ValueError("graph relationship endpoints must exist in the same generation")

    @staticmethod
    def _node_payload(node: GraphNode) -> dict[str, str]:
        return {
            "external_id": node.external_id,
            "kind": node.kind,
            "text": node.text,
            "properties_json": json.dumps(node.properties, ensure_ascii=False, sort_keys=True),
            "provenance_json": json.dumps(node.provenance, ensure_ascii=False, sort_keys=True),
        }

    @staticmethod
    def _relationship_payload(relationship: GraphRelationship) -> dict[str, str]:
        return {
            "external_id": relationship.external_id,
            "kind": relationship.kind,
            "source_id": relationship.source_id,
            "target_id": relationship.target_id,
            "properties_json": json.dumps(
                relationship.properties, ensure_ascii=False, sort_keys=True
            ),
            "provenance_json": json.dumps(
                relationship.provenance, ensure_ascii=False, sort_keys=True
            ),
        }

    @classmethod
    def _replace_extracted_transaction(
        cls,
        transaction: GraphTransaction,
        *,
        workspace_id: str,
        generation: str,
        nodes: tuple[GraphNode, ...],
        relationships: tuple[GraphRelationship, ...],
    ) -> None:
        transaction.run(
            "MATCH (n:CortexNode:ExtractedKnowledge "
            "{workspace_id: $workspace_id, generation: $generation}) "
            "DETACH DELETE n",
            workspace_id=workspace_id,
            generation=generation,
        ).consume()
        if nodes:
            transaction.run(
                "UNWIND $nodes AS row "
                "MERGE (n:CortexNode:ExtractedKnowledge "
                "{workspace_id: $workspace_id, layer: 'extracted', external_id: row.external_id}) "
                "SET n.kind = row.kind, n.generation = $generation, n.text = row.text, "
                "n.properties_json = row.properties_json, "
                "n.provenance_json = row.provenance_json",
                workspace_id=workspace_id,
                generation=generation,
                nodes=[cls._node_payload(node) for node in nodes],
            ).consume()
        if relationships:
            transaction.run(
                "UNWIND $relationships AS row "
                "MATCH (source:CortexNode:ExtractedKnowledge "
                "{workspace_id: $workspace_id, layer: 'extracted', external_id: row.source_id}) "
                "MATCH (target:CortexNode:ExtractedKnowledge "
                "{workspace_id: $workspace_id, layer: 'extracted', external_id: row.target_id}) "
                "MERGE (source)-[r:CORTEX_RELATION "
                "{workspace_id: $workspace_id, layer: 'extracted', external_id: row.external_id}]"
                "->(target) "
                "SET r.kind = row.kind, r.generation = $generation, "
                "r.properties_json = row.properties_json, "
                "r.provenance_json = row.provenance_json",
                workspace_id=workspace_id,
                generation=generation,
                relationships=[
                    cls._relationship_payload(relationship) for relationship in relationships
                ],
            ).consume()

    def replace_extracted_generation(
        self,
        generation: str,
        nodes: tuple[GraphNode, ...],
        relationships: tuple[GraphRelationship, ...],
    ) -> GraphSyncResult:
        """Atomically replace only this workspace's GraphRAG-produced extracted layer."""
        self._validate_generation(generation, nodes, relationships)
        with self.driver.session(database=self.database) as session:
            session.execute_write(
                self._replace_extracted_transaction,
                workspace_id=self.workspace_id,
                generation=generation,
                nodes=nodes,
                relationships=relationships,
            )
        return GraphSyncResult(
            self.workspace_id,
            generation,
            len(nodes),
            len(relationships),
        )
