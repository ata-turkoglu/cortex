"""Concrete all-stage executor for one durable knowledge candidate generation."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path

from ..core.config import Settings, get_settings
from ..core.embedding_runtime import build_production_embedder
from ..core.qdrant import get_qdrant_client
from ..graphrag.adapter import GraphRAGAdapter
from ..graphrag.neo4j import sync_graph_to_neo4j
from ..models import KnowledgeGeneration
from ..providers.base import EmbeddingProvider
from ..providers.embeddings import (
    EmbeddingConfiguration,
    adaptive_embed,
)
from ..providers.ollama import OllamaProvider
from ..retrieval.qdrant import VectorRecord, WorkspaceQdrantStore
from ..retrieval.schemas import Evidence
from ..retrieval.sparse import SparseDocument, WorkspaceBM25Index
from .canonical_core import CanonicalCoreStore
from .construction_projection import construct_from_bundle, promote_constructed_knowledge
from .entities import (
    CanonicalEntity,
    CanonicalEntityProperty,
    EntityMention,
    EntityPropertyValueType,
    EntityType,
    IdentityDecisionKind,
)
from .extraction import (
    ExtractionMetadata,
    KnowledgeExtractionBundle,
    retain_exact_assertions,
    split_composite_person_mentions,
    validate_extraction,
)
from .extraction_json import decode_extraction_json
from .graph import Neo4jGraphAdapter
from .model import KnowledgeAuthority, new_canonical_id
from .pipeline import CorpusSnapshot, StageResult
from .provider_extractor import OpenAIKnowledgeExtractor
from .source_manifest import (
    SourceManifestIdentity,
    load_generation_manifest,
    write_generation_manifest,
)
from .workflow_executor import KnowledgeWorkflowExecutor


def _fingerprint(stage: str, generation_id: str, material: object) -> str:
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{stage}:{hashlib.sha256(f'{generation_id}:{encoded}'.encode()).hexdigest()}"


def _entity_type(value: str) -> EntityType:
    try:
        return EntityType(value.casefold())
    except ValueError:
        return EntityType.DYNAMIC


_NON_SURNAME_TERMINALS = frozenset({"bey", "hanım", "hanim", "av", "dr", "hakim"})


# An extracted ``owns`` edge is countable only when its exact relation span
# actually states ownership. Endpoint containment proves locality, but not the
# relationship itself: a person and a property can co-occur without ownership.
_DIRECT_OWNERSHIP_PATTERN = re.compile(
    r"\b(?:owns?|owner(?:ship)?|malik\w*|sahib\w*|mülkiyet\w*|tasarruf\w*)\b",
    flags=re.IGNORECASE,
)


def _has_direct_ownership_support(source_text: str) -> bool:
    """Return whether an exact relation span contains explicit ownership language."""
    return bool(_DIRECT_OWNERSHIP_PATTERN.search(source_text))


_LABEL_BOUND_PROPERTY_FIELDS = (
    ("province", re.compile(r"^(?P<value>[^\d,.;]+?)\s+ili\b", re.IGNORECASE)),
    ("district", re.compile(r"\bili\s+(?P<value>[^\d,.;]+?)\s+il\u00e7esi\b", re.IGNORECASE)),
    (
        "neighborhood",
        re.compile(r"\bil\u00e7esi\s+(?P<value>[^\d,.;]+?)\s+mahallesi\b", re.IGNORECASE),
    ),
    ("pafta", re.compile(r"(?P<value>\d+)\s+pafta\b", re.IGNORECASE)),
    ("ada", re.compile(r"(?P<value>\d+)\s+ada\b", re.IGNORECASE)),
    ("parsel", re.compile(r"(?P<value>\d+)\s+parsel\b", re.IGNORECASE)),
)


def _label_bound_property_fields(source_text: str) -> dict[str, str]:
    """Recover omitted property keys only from their explicit labels in the mention span.

    This is intentionally not relation inference: it neither creates an ownership
    edge nor changes extracted values.  The caller only uses a recovered value
    when the extractor omitted that key and the label is in exact property evidence.
    """
    fields: dict[str, str] = {}
    for key, pattern in _LABEL_BOUND_PROPERTY_FIELDS:
        match = pattern.search(source_text)
        if match:
            value = match.group("value").strip()
            if value:
                fields[key] = value
    return fields


def _surname_from_identity_evidence(value: str, provenance):
    """Conservatively project a surname from the exact canonical identity mention.

    This is a generation-time identity projection, never a query-time name parse.
    A single-token, titled, punctuated, or parenthesized mention remains unprojected.
    """
    normalized = value.strip()
    if any(marker in normalized for marker in "()[]"):
        return None
    parts = re.findall(r"[^\W\d_]+", normalized, flags=re.UNICODE)
    if len(parts) < 2 or parts[-1].casefold() in _NON_SURNAME_TERMINALS:
        return None
    surname = parts[-1]
    offset = value.rfind(surname)
    if offset < 0:
        return None
    return surname, replace(
        provenance,
        start_offset=provenance.start_offset + offset,
        end_offset=provenance.start_offset + offset + len(surname),
        source_text=surname,
    )


def _bundle_payload(bundle: KnowledgeExtractionBundle) -> dict[str, object]:
    def span(item) -> dict[str, object]:
        return {
            "chunk_id": item.span.chunk_id,
            "start_offset": item.span.start_offset,
            "end_offset": item.span.end_offset,
            "source_text": item.span.source_text,
            "confidence": item.span.confidence,
        }

    return {
        "metadata": {
            "extraction_run_id": bundle.metadata.extraction_run_id,
            "provider": bundle.metadata.provider,
            "model": bundle.metadata.model,
            "prompt_version": bundle.metadata.prompt_version,
            "schema_version": bundle.metadata.schema_version,
        },
        "mentions": [
            {
                "id": item.local_id,
                "entity_type": item.entity_type,
                "identity_candidates": [
                    {"canonical_entity_id": value}
                    for value in item.candidate_canonical_entity_ids
                ],
                "candidate_provenance": item.candidate_provenance,
                **span(item),
            }
            for item in bundle.mentions
        ],
        "entity_properties": [
            {"mention_id": item.mention_id, "key": item.key, "value": item.value, **span(item)}
            for item in bundle.entity_properties
        ],
        "relations": [
            {
                "relation_type": item.relation_type,
                "source_mention_id": item.source_mention_id,
                "target_mention_id": item.target_mention_id,
                **span(item),
            }
            for item in bundle.relations
        ],
        "events": [
            {
                "id": item.local_id,
                "event_type": item.event_type,
                "participants": [
                    {"mention_id": mention_id} for mention_id in item.participant_mention_ids
                ],
                **span(item),
            }
            for item in bundle.events
        ],
        "temporals": [
            {
                "id": item.local_id,
                "original_text": item.original_text,
                "normalized_start": item.normalized_start,
                "normalized_end": item.normalized_end,
                "semantic_role": item.semantic_role,
                "precision": item.precision,
                "uncertain": item.uncertain,
                **span(item),
            }
            for item in bundle.temporals
        ],
        "claims": [
            {
                "subject_mention_id": item.subject_mention_id,
                "predicate": item.predicate,
                "value": item.value,
                **span(item),
            }
            for item in bundle.claims
        ],
    }


def _bundle_from_payload(payload: dict[str, object]) -> KnowledgeExtractionBundle:
    metadata = ExtractionMetadata(**payload["metadata"])
    provider_payload = {
        key: payload.get(key, [])
        for key in ("mentions", "entity_properties", "relations", "events", "temporals", "claims")
    }
    return split_composite_person_mentions(
        decode_extraction_json(json.dumps(provider_payload, ensure_ascii=False), metadata)
    )


class ProductionKnowledgeExecutor:
    """Executes every mandatory stage with durable, generation-scoped artifacts."""

    def __init__(
        self,
        workspace_id: str,
        extractor=None,
        *,
        settings: Settings | None = None,
        embedding_configuration: EmbeddingConfiguration | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        session_factory=None,
    ) -> None:
        self.workspace_id = workspace_id
        self.settings = settings or get_settings()
        if embedding_configuration is None or embedding_provider is None:
            raise RuntimeError("production knowledge embeddings require persisted configuration")
        self.embedding_configuration = embedding_configuration
        self.embedding_provider = embedding_provider
        self.extractor = extractor or OpenAIKnowledgeExtractor(
            self.settings.graphrag_extraction_model,
            OllamaProvider() if self.settings.graphrag_extraction_provider == "ollama" else None,
            provider_name=self.settings.graphrag_extraction_provider,
            request_timeout_seconds=self.settings.knowledge_extraction_request_timeout_seconds,
            concurrency=self.settings.knowledge_extraction_concurrency,
        )
        root = (
            self.settings.data_path / "workspaces" / workspace_id / "knowledge-candidates"
        ).resolve()
        data_root = self.settings.data_path.resolve()
        self.data_root = data_root
        if data_root not in root.parents:
            raise ValueError("knowledge candidate path escapes the data root")
        self.root = root
        self._retrieval: dict[str, tuple[StageResult, StageResult]] = {}
        self.session_factory = session_factory

    def as_workflow_executor(self) -> KnowledgeWorkflowExecutor:
        return KnowledgeWorkflowExecutor(
            {
                "source_relational": self.source_relational,
                "entity_mention": self.entity_mentions,
                "identity_resolution": self.identity_resolution,
                "relation": lambda snapshot, generation: self.typed_stage(
                    "relation", snapshot, generation
                ),
                "event": lambda snapshot, generation: self.typed_stage(
                    "event", snapshot, generation
                ),
                "temporal": lambda snapshot, generation: self.typed_stage(
                    "temporal", snapshot, generation
                ),
                "claim_fact": lambda snapshot, generation: self.typed_stage(
                    "claim_fact", snapshot, generation
                ),
                "canonical_graph": self.canonical_projection,
                "bm25": lambda snapshot, generation: self.retrieval(snapshot, generation)[0],
                "dense_qdrant": lambda snapshot, generation: self.retrieval(snapshot, generation)[
                    1
                ],
                "graphrag": self.graphrag,
            }
        )

    def _generation_root(self, generation_id: str) -> Path:
        root = (self.root / generation_id).resolve()
        if self.root not in root.parents:
            raise ValueError("candidate generation path escapes its workspace")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _artifact(self, generation_id: str, name: str) -> Path:
        return self._generation_root(generation_id) / f"{name}.json"

    def _write_source_manifest(
        self, snapshot: CorpusSnapshot, generation_id: str
    ) -> SourceManifestIdentity:
        """Persist the immutable source authority for one candidate generation."""
        return write_generation_manifest(self.data_root, snapshot, generation_id)

    def source_relational(self, snapshot: CorpusSnapshot, generation_id: str) -> StageResult:
        manifest = self._write_source_manifest(snapshot, generation_id)
        metrics = {
            "chunk_count": manifest.chunk_count,
            "source_manifest_uri": manifest.uri,
            "source_manifest_hash": manifest.sha256,
            "source_chunk_count": manifest.chunk_count,
        }
        return StageResult(
            generation_id,
            snapshot.fingerprint,
            _fingerprint("source_relational", generation_id, metrics),
            metrics,
        )

    def _load_bundles(self, generation_id: str) -> tuple[KnowledgeExtractionBundle, ...]:
        payload = json.loads(self._artifact(generation_id, "extraction").read_text("utf-8"))
        return tuple(_bundle_from_payload(item) for item in payload["bundles"])

    def entity_mentions(self, snapshot: CorpusSnapshot, generation_id: str) -> StageResult:
        artifact = self._artifact(generation_id, "extraction")
        if artifact.is_file():
            bundles = self._load_bundles(generation_id)
            rejected_assertion_count = 0
        else:
            chunk_root = self._generation_root(generation_id) / "extraction-chunks"
            chunk_root.mkdir(parents=True, exist_ok=True)
            collected_by_chunk: dict[str, KnowledgeExtractionBundle] = {}
            missing_chunks = []
            rejected_assertion_count = 0
            for chunk in snapshot.chunks:
                chunk_artifact = chunk_root / f"{chunk.chunk_id}.json"
                if chunk_artifact.is_file():
                    collected_by_chunk[chunk.chunk_id] = _bundle_from_payload(
                        json.loads(chunk_artifact.read_text(encoding="utf-8"))
                    )
                else:
                    missing_chunks.append(chunk)
            if missing_chunks:
                # Each successful bounded provider batch is checkpointed before
                # the next starts.  A later transient failure therefore resumes
                # from validated chunk artifacts rather than recharging or
                # reprocessing the entire candidate corpus.
                batch_size = getattr(self.extractor, "concurrency", len(missing_chunks))
                for offset in range(0, len(missing_chunks), batch_size):
                    batch = missing_chunks[offset : offset + batch_size]
                    result = self.extractor.extract(
                        CorpusSnapshot(
                            snapshot.workspace_id, snapshot.fingerprint, tuple(batch)
                        ),
                        generation_id,
                    )
                    if len(result.bundles) != len(batch):
                        raise RuntimeError("knowledge extractor returned an incomplete chunk batch")
                    rejected_assertion_count += result.rejected_assertion_count
                    for chunk, bundle in zip(batch, result.bundles, strict=True):
                        chunk_artifact = chunk_root / f"{chunk.chunk_id}.json"
                        chunk_artifact.write_text(
                            json.dumps(_bundle_payload(bundle), ensure_ascii=False, sort_keys=True),
                            encoding="utf-8",
                        )
                        collected_by_chunk[chunk.chunk_id] = bundle
            bundles = tuple(collected_by_chunk[chunk.chunk_id] for chunk in snapshot.chunks)
            artifact.write_text(
                json.dumps(
                    {"bundles": [_bundle_payload(item) for item in bundles]},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
        retained_bundles = tuple(retain_exact_assertions(item, snapshot) for item in bundles)
        bundles = tuple(item[0] for item in retained_bundles)
        rejected_assertion_count += sum(item[1] for item in retained_bundles)
        evidence_count = sum(
            len(validate_extraction(item, snapshot, generation_id)) for item in bundles
        )
        metrics = {
            "bundle_count": len(bundles),
            "mention_count": sum(len(item.mentions) for item in bundles),
            "entity_property_candidate_count": sum(len(item.entity_properties) for item in bundles),
            "evidence_count": evidence_count,
            "rejected_assertion_count": rejected_assertion_count,
            "artifact": str(artifact.relative_to(self.data_root)),
        }
        return StageResult(
            generation_id,
            snapshot.fingerprint,
            _fingerprint("entity_mention", generation_id, metrics),
            metrics,
        )

    def identity_resolution(self, snapshot: CorpusSnapshot, generation_id: str) -> StageResult:
        if self.session_factory is None:
            raise RuntimeError("canonical construction requires a SQLite session factory")
        if snapshot.workspace_id != self.workspace_id:
            raise ValueError("canonical construction snapshot crosses executor workspace")
        bundles = self._load_bundles(generation_id)
        session = self.session_factory()
        mapping: list[dict[str, object]] = []
        rejected_assertion_count = 0
        try:
            sources = load_generation_manifest(
                session, snapshot.workspace_id, generation_id, self.data_root
            )
            generation = session.get(KnowledgeGeneration, generation_id)
            if generation is None or generation.workspace_id != snapshot.workspace_id:
                raise ValueError(
                    "canonical generation is missing or outside the snapshot workspace"
                )
            if generation.source_fingerprint != snapshot.fingerprint:
                raise ValueError("canonical snapshot does not match the target generation")
            source_by_chunk = {source.chunk_id: source for source in sources}
            snapshot_by_chunk = {chunk.chunk_id: chunk for chunk in snapshot.chunks}
            if set(source_by_chunk) != set(snapshot_by_chunk):
                raise ValueError("canonical manifest does not agree with the generation snapshot")
            if len(bundles) != len(snapshot.chunks):
                raise ValueError("canonical extraction bundles do not cover the full manifest")
            store = CanonicalCoreStore(session, snapshot.workspace_id)
            for bundle_index, (bundle, chunk) in enumerate(
                zip(bundles, snapshot.chunks, strict=True)
            ):
                source = source_by_chunk.get(chunk.chunk_id)
                if source is None or (
                    source.document_id != chunk.document_id
                    or source.document_version_id != chunk.document_version_id
                    or source.logical_document_id != chunk.logical_document_id
                    or source.content != chunk.content
                    or hashlib.sha256(source.content.encode()).hexdigest() != chunk.content_hash
                ):
                    raise ValueError("canonical source evidence is outside its immutable manifest")
                one_chunk = CorpusSnapshot(snapshot.workspace_id, snapshot.fingerprint, (chunk,))
                retained, rejected_evidence_count = retain_exact_assertions(bundle, one_chunk)
                try:
                    # A dropped exact-evidence assertion can otherwise make a
                    # countable ownership/property claim disappear and falsely
                    # advertise this generation as exhaustive-ready.
                    rejected_assertion_count += rejected_evidence_count
                    validate_extraction(retained, one_chunk, generation_id)
                    if any(item.span.chunk_id != chunk.chunk_id for item in retained.mentions):
                        raise ValueError("canonical extraction crosses manifest chunk boundaries")
                    durable_people = {}
                    durable_properties = {}
                    for item in retained.mentions:
                        if item.entity_type == "person":
                            durable = store.persist_person_mention(
                                generation_id=generation_id,
                                document_id=chunk.document_id,
                                document_version_id=chunk.document_version_id,
                                logical_document_id=chunk.logical_document_id or None,
                                chunk_id=chunk.chunk_id,
                                span_start=item.span.start_offset,
                                span_end=item.span.end_offset,
                                source_text=item.span.source_text,
                                extractor_version=retained.metadata.schema_version,
                            )
                            decision = store.decide_person(
                                durable,
                                candidate_ids=item.candidate_canonical_entity_ids,
                                candidate_provenance=item.candidate_provenance,
                            )
                            durable_people[item.local_id] = durable
                            mapping.append(
                                {
                                    "bundle_index": bundle_index,
                                    "local_id": item.local_id,
                                    "mention_id": durable.id,
                                    "entity_id": decision.canonical_entity_id,
                                    "decision": {
                                        "NEW": "new_canonical",
                                        "LINK": "auto_link",
                                        "UNRESOLVED": "unresolved",
                                    }[decision.decision],
                                    "canonical_display_name": durable.surface_text,
                                    "candidate_entity_ids": json.loads(
                                        decision.candidate_entity_ids_json
                                    ),
                                }
                            )
                        elif item.entity_type == "asset_property":
                            durable_properties[item.local_id] = store.persist_property_mention(
                                generation_id=generation_id,
                                document_id=chunk.document_id,
                                document_version_id=chunk.document_version_id,
                                logical_document_id=chunk.logical_document_id or None,
                                chunk_id=chunk.chunk_id,
                                span_start=item.span.start_offset,
                                span_end=item.span.end_offset,
                                source_text=item.span.source_text,
                                extractor_version=retained.metadata.schema_version,
                            )
                    fields_by_property: dict[str, dict[str, str]] = {}
                    for item in retained.entity_properties:
                        if item.mention_id in durable_properties and item.key in {
                            "province",
                            "district",
                            "neighborhood",
                            "pafta",
                            "ada",
                            "parsel",
                            "independent_section",
                        }:
                            fields_by_property.setdefault(item.mention_id, {})[item.key] = (
                                item.value
                            )
                    for item in retained.mentions:
                        if (
                            item.entity_type != "asset_property"
                            or item.local_id not in durable_properties
                        ):
                            continue
                        fields = fields_by_property.setdefault(item.local_id, {})
                        repaired_fields = _label_bound_property_fields(item.span.source_text)
                        for key, value in repaired_fields.items():
                            fields.setdefault(key, value)
                    for relation in retained.relations:
                        if relation.relation_type != "owns":
                            continue
                        person = durable_people.get(relation.source_mention_id)
                        property_mention = durable_properties.get(relation.target_mention_id)
                        if (
                            person is None
                            or property_mention is None
                            or relation.span.start_offset > person.span_start
                            or relation.span.end_offset < person.span_end
                            or relation.span.start_offset > property_mention.span_start
                            or relation.span.end_offset < property_mention.span_end
                            or not _has_direct_ownership_support(relation.span.source_text)
                        ):
                            rejected_assertion_count += 1
                            if person is not None:
                                store.persist_rejected_ownership_blocker(
                                    generation_id=generation_id,
                                    person_mention=person,
                                    span_start=relation.span.start_offset,
                                    span_end=relation.span.end_offset,
                                    source_text=relation.span.source_text,
                                    reason="ownership assertion lacks direct local support",
                                )
                            continue
                        property_record = store.upsert_property(
                            fields_by_property.get(relation.target_mention_id, {})
                        )
                        if property_record is None:
                            rejected_assertion_count += 1
                            store.persist_rejected_ownership_blocker(
                                generation_id=generation_id,
                                person_mention=person,
                                span_start=relation.span.start_offset,
                                span_end=relation.span.end_offset,
                                source_text=relation.span.source_text,
                                reason="ownership assertion lacks a safely identified property",
                            )
                            continue
                        store.persist_ownership_assertion(
                            generation_id=generation_id,
                            person_mention=person,
                            property_mention=property_mention,
                            property_record=property_record,
                            span_start=relation.span.start_offset,
                            span_end=relation.span.end_offset,
                            source_text=relation.span.source_text,
                            assertion_rule_version=retained.metadata.schema_version,
                        )
                    store.record_chunk(generation_id, chunk.chunk_id, chunk.content_hash)
                    session.commit()
                except Exception as error:
                    session.rollback()
                    store = CanonicalCoreStore(session, snapshot.workspace_id)
                    store.record_chunk(
                        generation_id, chunk.chunk_id, chunk.content_hash, failed=str(error)[:500]
                    )
                    session.commit()
            generation = session.get(KnowledgeGeneration, generation_id)
            if generation is None:
                raise ValueError("canonical generation disappeared")
            remapped_people = CanonicalCoreStore(
                session, snapshot.workspace_id
            ).consolidate_exact_person_identities(generation_id)
            for row in mapping:
                if row["mention_id"] in remapped_people:
                    row["entity_id"] = remapped_people[row["mention_id"]]
                    row["decision"] = "auto_link"
            CanonicalCoreStore(session, snapshot.workspace_id).record_status(
                generation_id=generation_id,
                manifest_hash=generation.source_manifest_hash,
                manifest_chunk_count=generation.source_chunk_count,
                rejected_assertion_count=rejected_assertion_count,
            )
            session.commit()
        finally:
            session.close()
        artifact = self._artifact(generation_id, "identity")
        artifact.write_text(json.dumps({"mapping": mapping}, sort_keys=True), encoding="utf-8")
        metrics = {
            "mention_count": len(mapping),
            "rejected_assertion_count": rejected_assertion_count,
            "canonical_projection": "sqlite",
            "artifact": str(artifact.relative_to(self.data_root)),
        }
        return StageResult(
            generation_id,
            snapshot.fingerprint,
            _fingerprint("identity_resolution", generation_id, metrics),
            metrics,
        )

    def _mapping(self, generation_id: str) -> list[dict[str, object]]:
        return json.loads(self._artifact(generation_id, "identity").read_text("utf-8"))["mapping"]

    def _constructed(self, snapshot: CorpusSnapshot, generation_id: str):
        bundles = tuple(
            retain_exact_assertions(item, snapshot)[0] for item in self._load_bundles(generation_id)
        )
        rows = self._mapping(generation_id)
        return tuple(
            construct_from_bundle(
                retain_exact_assertions(bundle, snapshot)[0],
                snapshot,
                generation_id,
                {
                    row["local_id"]: row["entity_id"]
                    for row in rows
                    if row["bundle_index"] == index and row.get("entity_id")
                },
            )
            for index, bundle in enumerate(bundles)
        )

    def typed_stage(self, stage: str, snapshot: CorpusSnapshot, generation_id: str) -> StageResult:
        constructed = self._constructed(snapshot, generation_id)
        attribute = {
            "relation": "relations",
            "event": "events",
            "temporal": "temporals",
            "claim_fact": "claims",
        }[stage]
        count = sum(len(getattr(item, attribute)) for item in constructed)
        metrics = {f"{attribute}_count": count}
        return StageResult(
            generation_id,
            snapshot.fingerprint,
            _fingerprint(stage, generation_id, metrics),
            metrics,
        )

    def canonical_projection(self, snapshot: CorpusSnapshot, generation_id: str) -> StageResult:
        """Checkpoint SQLite authority; Neo4j materialization remains deferred."""
        if self.session_factory is None:
            raise RuntimeError("canonical construction requires a SQLite session factory")
        session = self.session_factory()
        try:
            from ..models import CanonicalGenerationStatusRecord

            row = session.get(
                CanonicalGenerationStatusRecord,
                (snapshot.workspace_id, generation_id, "minimal-core-v1"),
            )
            if row is None:
                raise ValueError("SQLite canonical construction did not produce a status record")
            metrics = {
                "sqlite_canonical_status": row.status,
                "manifest_chunk_count": row.manifest_chunk_count,
                "processed_chunk_count": row.processed_chunk_count,
                "failed_chunk_count": row.failed_chunk_count,
            }
        finally:
            session.close()
        return StageResult(
            generation_id,
            snapshot.fingerprint,
            _fingerprint("canonical_sqlite_projection", generation_id, metrics),
            metrics,
        )

    def canonical_graph(self, snapshot: CorpusSnapshot, generation_id: str) -> StageResult:
        bundles = tuple(
            retain_exact_assertions(item, snapshot)[0] for item in self._load_bundles(generation_id)
        )
        rows = self._mapping(generation_id)
        rows_by_key = {(row["bundle_index"], row["local_id"]): row for row in rows}
        entities: dict[str, CanonicalEntity] = {}
        property_candidates: dict[tuple[str, str], list[CanonicalEntityProperty]] = {}
        with Neo4jGraphAdapter.from_settings(
            snapshot.workspace_id, settings=self.settings
        ) as graph:
            graph.ensure_schema()
            graph.clear_generation_materialization(generation_id)
            for index, bundle in enumerate(bundles):
                evidence = validate_extraction(bundle, snapshot, generation_id)
                for extracted, provenance in zip(bundle.mentions, evidence, strict=False):
                    row = rows_by_key.get((index, extracted.local_id))
                    if row is None:
                        # Extraction retention can reject one mention while preserving
                        # other exact assertions in the same bundle.  It cannot become
                        # a canonical entity without a resolved identity decision.
                        continue
                    if not row.get("entity_id"):
                        # Unresolved/ambiguous mentions retain their artifact
                        # provenance only; they never enter canonical state.
                        continue
                    entity_id = str(row["entity_id"])
                    mention = EntityMention(
                        str(row["mention_id"]),
                        extracted.span.source_text,
                        _entity_type(extracted.entity_type),
                        provenance,
                        tuple(row["candidate_entity_ids"]),
                        entity_id,
                        IdentityDecisionKind(str(row["decision"])),
                    )
                    current = entities.get(entity_id)
                    entities[entity_id] = CanonicalEntity(
                        entity_id,
                        mention.entity_type,
                        current.display_name
                        if current
                        else str(row.get("canonical_display_name") or extracted.span.source_text),
                        KnowledgeAuthority.EXTRACTED,
                        mentions=(*current.mentions, mention) if current else (mention,),
                    )
                    if mention.entity_type is EntityType.PERSON:
                        derived = _surname_from_identity_evidence(
                            extracted.span.source_text, provenance
                        )
                        if derived:
                            value, surname_provenance = derived
                            candidate = CanonicalEntityProperty(
                                new_canonical_id(),
                                entity_id,
                                "surname",
                                value,
                                EntityPropertyValueType.STRING,
                                KnowledgeAuthority.EXTRACTED,
                                generation_id,
                                surname_provenance,
                            )
                            property_candidates.setdefault((entity_id, candidate.key), []).append(
                                candidate
                            )
                property_start = len(bundle.mentions)
                property_evidence = evidence[
                    property_start : property_start + len(bundle.entity_properties)
                ]
                for extracted_property, provenance in zip(
                    bundle.entity_properties, property_evidence, strict=True
                ):
                    row = rows_by_key.get((index, extracted_property.mention_id))
                    if row is None:
                        continue
                    entity_id = str(row["entity_id"])
                    entity = entities.get(entity_id)
                    if entity is None or entity.entity_type is not EntityType.PERSON:
                        continue
                    candidate = CanonicalEntityProperty(
                        new_canonical_id(),
                        entity_id,
                        extracted_property.key,
                        extracted_property.value,
                        EntityPropertyValueType.STRING,
                        KnowledgeAuthority.EXTRACTED,
                        generation_id,
                        provenance,
                    )
                    property_candidates.setdefault((entity_id, candidate.key), []).append(candidate)
            for entity in entities.values():
                graph.upsert_canonical_entity(entity, generation_id)
            resolved_property_count = 0
            conflicted_property_count = 0
            for candidates in property_candidates.values():
                values = {candidate.normalized_value for candidate in candidates}
                if len(values) != 1:
                    conflicted_property_count += 1
                    for candidate in candidates:
                        graph.upsert_canonical_entity_property(
                            replace(candidate, status="conflicted")
                        )
                    continue
                # A repeated identical assertion remains independently evidenced; choose a stable
                # representative rather than exposing competing values as canonical truth.
                graph.upsert_canonical_entity_property(
                    min(candidates, key=lambda candidate: candidate.property_id)
                )
                resolved_property_count += 1
            counts = {"relations": 0, "events": 0, "temporals": 0, "claims": 0}
            governed_ownership_relation_count = 0
            for constructed in self._constructed(snapshot, generation_id):
                governed_ownership_relation_count += sum(
                    relation.relation_type == "owns" for relation in constructed.relations
                )
                promoted = promote_constructed_knowledge(graph, snapshot, constructed)
                for key, value in promoted.items():
                    counts[key] += value
        metrics = {
            "entity_count": len(entities),
            "resolved_entity_property_count": resolved_property_count,
            "conflicted_entity_property_count": conflicted_property_count,
            "entity_property_schema_version": "1",
            "governed_ownership_relation_count": governed_ownership_relation_count,
            "governed_relation_projection_schema_version": "1",
            **counts,
        }
        return StageResult(
            generation_id,
            snapshot.fingerprint,
            _fingerprint("canonical_graph", generation_id, metrics),
            metrics,
        )

    def retrieval(
        self, snapshot: CorpusSnapshot, generation_id: str
    ) -> tuple[StageResult, StageResult]:
        if generation_id in self._retrieval:
            return self._retrieval[generation_id]
        manifest = self._write_source_manifest(snapshot, generation_id)
        evidence = [
            Evidence(
                snapshot.workspace_id,
                "knowledge_candidate",
                chunk.content,
                0.0,
                chunk.document_id,
                chunk.document_version_id,
                chunk.chunk_id,
                f"passage {chunk.ordinal + 1}",
                {
                    "knowledge_generation_id": generation_id,
                    "logical_document_id": chunk.logical_document_id,
                    "content_hash": chunk.content_hash,
                },
            )
            for chunk in snapshot.chunks
        ]
        bm25_path = self._generation_root(generation_id) / "bm25"
        WorkspaceBM25Index(
            snapshot.workspace_id,
            [SparseDocument(item.chunk_id or "", item.content, item) for item in evidence],
            bm25_path,
            generation_id=generation_id,
        ).save()
        provider = self.embedding_provider
        texts = [item.content for item in evidence]
        vectors = (
            asyncio.run(
                adaptive_embed(
                    provider,
                    texts,
                    batch_size=self.settings.embedding_batch_size,
                    min_batch_size=self.settings.embedding_min_batch_size,
                )
            )
            if texts
            else []
        )
        if not vectors:
            raise RuntimeError("knowledge candidate has no embeddings to index")
        configuration = EmbeddingConfiguration(
            self.embedding_configuration.provider,
            self.embedding_configuration.model,
            len(vectors[0]),
            self.embedding_configuration.model_digest,
            self.embedding_configuration.normalized,
            self.embedding_configuration.text_template_version,
        )
        store = WorkspaceQdrantStore(
            get_qdrant_client(),
            snapshot.workspace_id,
            embedding_config_hash=configuration.fingerprint,
            projection_key=generation_id,
        )
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
                        "logical_document_id": item.metadata["logical_document_id"],
                        "content_hash": item.metadata["content_hash"],
                        "citation_label": item.citation_label,
                    },
                )
                for item, vector in zip(evidence, vectors, strict=True)
            ],
            len(vectors[0]),
        )
        expected = {
            chunk.chunk_id: {
                "workspace_id": snapshot.workspace_id,
                "knowledge_generation_id": generation_id,
                "document_id": chunk.document_id,
                "document_version_id": chunk.document_version_id,
                "logical_document_id": chunk.logical_document_id,
                "chunk_id": chunk.chunk_id,
                "content_hash": chunk.content_hash,
                "embedding_config_hash": configuration.fingerprint,
            }
            for chunk in snapshot.chunks
        }
        persisted_bm25 = WorkspaceBM25Index.load(snapshot.workspace_id, bm25_path)
        bm25 = {
            item.chunk_id: {
                "workspace_id": item.evidence.workspace_id,
                "knowledge_generation_id": item.evidence.metadata.get("knowledge_generation_id"),
                "document_id": item.evidence.document_id,
                "document_version_id": item.evidence.document_version_id,
                "logical_document_id": item.evidence.metadata.get("logical_document_id"),
                "chunk_id": item.evidence.chunk_id,
                "content_hash": item.evidence.metadata.get("content_hash"),
                "embedding_config_hash": configuration.fingerprint,
            }
            for item in persisted_bm25.documents
        }
        qdrant = {
            str(payload.get("chunk_id")): {
                key: payload.get(key)
                for key in (
                    "workspace_id",
                    "knowledge_generation_id",
                    "document_id",
                    "document_version_id",
                    "logical_document_id",
                    "chunk_id",
                    "content_hash",
                    "embedding_config_hash",
                )
            }
            for payload in store.generation_payloads()
        }
        if bm25 != expected:
            raise ValueError("BM25 candidate projection does not agree with source manifest")
        if qdrant != expected:
            raise ValueError("Qdrant candidate projection does not agree with source manifest")

        common = {
            "chunk_count": len(evidence),
            "chunk_ids": sorted(item.chunk_id or "" for item in evidence),
            "content_hashes": {
                item.chunk_id or "": item.metadata["content_hash"] for item in evidence
            },
            "embedding_config_hash": configuration.fingerprint,
            "source_manifest_uri": manifest.uri,
            "source_manifest_hash": manifest.sha256,
            "source_chunk_count": manifest.chunk_count,
        }
        result = (
            StageResult(
                generation_id,
                snapshot.fingerprint,
                _fingerprint("bm25", generation_id, {**common, "path": str(bm25_path)}),
                {
                    "chunk_count": len(evidence),
                    "artifact": str(bm25_path.relative_to(self.data_root)),
                    "source_manifest": manifest.uri,
                    **common,
                },
            ),
            StageResult(
                generation_id,
                snapshot.fingerprint,
                _fingerprint("dense_qdrant", generation_id, common),
                common,
            ),
        )
        self._retrieval[generation_id] = result
        return result

    def graphrag(self, snapshot: CorpusSnapshot, generation_id: str) -> StageResult:
        root = self._generation_root(generation_id) / "graphrag"
        input_root = root / "input"
        input_root.mkdir(parents=True, exist_ok=True)
        for chunk in snapshot.chunks:
            (input_root / f"{chunk.chunk_id}.md").write_text(chunk.content, encoding="utf-8")
        adapter = GraphRAGAdapter(snapshot.workspace_id, root)
        adapter.config_path = (
            root / "settings.yaml" if (root / "settings.yaml").is_file() else adapter.initialize()
        )
        adapter.index()
        adapter.rebuild_networkx()
        synced = sync_graph_to_neo4j(adapter, generation_id)
        summary = synced.graph
        if summary.generation != generation_id or summary.workspace_id != snapshot.workspace_id:
            raise ValueError("GraphRAG candidate returned a mismatched generation")
        metrics = {
            "node_count": summary.node_count,
            "relationship_count": summary.relationship_count,
            "skipped_relationship_count": synced.skipped_relationship_count,
            "artifact": str(root.relative_to(self.data_root)),
        }
        return StageResult(
            generation_id,
            snapshot.fingerprint,
            _fingerprint("graphrag", generation_id, metrics),
            metrics,
        )


def create_production_executor(workspace_id: str, session) -> KnowledgeWorkflowExecutor:
    configuration, provider = build_production_embedder(session)
    from sqlalchemy.orm import sessionmaker

    return ProductionKnowledgeExecutor(
        workspace_id,
        embedding_configuration=configuration,
        embedding_provider=provider,
        session_factory=sessionmaker(bind=session.get_bind(), autoflush=False),
    ).as_workflow_executor()
