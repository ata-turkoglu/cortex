"""Concrete all-stage executor for one durable knowledge candidate generation."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from ..core.config import get_settings
from ..core.qdrant import get_qdrant_client
from ..graphrag.adapter import GraphRAGAdapter
from ..graphrag.neo4j import sync_graph_to_neo4j
from ..providers.embeddings import (
    EmbeddingConfiguration,
    OllamaEmbeddingAdapter,
    OpenAIEmbeddingAdapter,
    Qwen3EmbeddingAdapter,
    adaptive_embed,
)
from ..providers.ollama import OllamaProvider
from ..retrieval.qdrant import VectorRecord, WorkspaceQdrantStore
from ..retrieval.schemas import Evidence
from ..retrieval.sparse import SparseDocument, WorkspaceBM25Index
from .construction_projection import construct_from_bundle, promote_constructed_knowledge
from .entities import (
    CanonicalEntity,
    EntityMention,
    EntityType,
    IdentityDecisionKind,
    normalize_mention,
    resolve_conservatively,
)
from .extraction import (
    ExtractionMetadata,
    KnowledgeExtractionBundle,
    retain_exact_assertions,
    validate_extraction,
)
from .extraction_json import decode_extraction_json
from .graph import Neo4jGraphAdapter
from .model import KnowledgeAuthority, new_canonical_id
from .pipeline import CorpusSnapshot, StageResult
from .provider_extractor import OpenAIKnowledgeExtractor
from .workflow_executor import KnowledgeWorkflowExecutor


def _fingerprint(stage: str, generation_id: str, material: object) -> str:
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{stage}:{hashlib.sha256(f'{generation_id}:{encoded}'.encode()).hexdigest()}"


def _entity_type(value: str) -> EntityType:
    try:
        return EntityType(value.casefold())
    except ValueError:
        return EntityType.DYNAMIC


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
            {"id": item.local_id, "entity_type": item.entity_type, **span(item)}
            for item in bundle.mentions
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
                    {"mention_id": mention_id}
                    for mention_id in item.participant_mention_ids
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
        for key in ("mentions", "relations", "events", "temporals", "claims")
    }
    return decode_extraction_json(json.dumps(provider_payload, ensure_ascii=False), metadata)


class ProductionKnowledgeExecutor:
    """Executes every mandatory stage with durable, generation-scoped artifacts."""

    def __init__(self, workspace_id: str, extractor=None) -> None:
        self.workspace_id = workspace_id
        self.settings = get_settings()
        self.extractor = extractor or OpenAIKnowledgeExtractor(
            self.settings.graphrag_extraction_model,
            OllamaProvider()
            if self.settings.graphrag_extraction_provider == "ollama"
            else None,
            provider_name=self.settings.graphrag_extraction_provider,
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

    def as_workflow_executor(self) -> KnowledgeWorkflowExecutor:
        return KnowledgeWorkflowExecutor(
            {
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
                "canonical_graph": self.canonical_graph,
                "bm25": lambda snapshot, generation: self.retrieval(snapshot, generation)[0],
                "dense_qdrant": lambda snapshot, generation: self.retrieval(
                    snapshot, generation
                )[1],
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

    def _write_source_manifest(self, snapshot: CorpusSnapshot, generation_id: str) -> Path:
        """Persist the immutable source authority for one candidate generation."""
        artifact = self._artifact(generation_id, "source-manifest")
        payload = {
            "workspace_id": snapshot.workspace_id,
            "generation_id": generation_id,
            "source_fingerprint": snapshot.fingerprint,
            "chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "document_version_id": chunk.document_version_id,
                    "logical_document_id": chunk.logical_document_id,
                    "ordinal": chunk.ordinal,
                    "content": chunk.content,
                    "content_hash": chunk.content_hash,
                }
                for chunk in snapshot.chunks
            ],
        }
        artifact.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        return artifact

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
            collected = []
            rejected_assertion_count = 0
            for chunk in snapshot.chunks:
                chunk_artifact = chunk_root / f"{chunk.chunk_id}.json"
                if chunk_artifact.is_file():
                    bundle = _bundle_from_payload(
                        json.loads(chunk_artifact.read_text(encoding="utf-8"))
                    )
                    validate_extraction(bundle, snapshot, generation_id)
                else:
                    result = self.extractor.extract(
                        CorpusSnapshot(snapshot.workspace_id, snapshot.fingerprint, (chunk,)),
                        generation_id,
                    )
                    bundle = result.bundles[0]
                    rejected_assertion_count += result.rejected_assertion_count
                    chunk_artifact.write_text(
                        json.dumps(_bundle_payload(bundle), ensure_ascii=False, sort_keys=True),
                        encoding="utf-8",
                    )
                collected.append(bundle)
            bundles = tuple(collected)
            artifact.write_text(
                json.dumps({"bundles": [_bundle_payload(item) for item in bundles]},
                           ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
        bundles = tuple(retain_exact_assertions(item, snapshot)[0] for item in bundles)
        evidence_count = sum(
            len(validate_extraction(item, snapshot, generation_id)) for item in bundles
        )
        metrics = {
            "bundle_count": len(bundles),
            "mention_count": sum(len(item.mentions) for item in bundles),
            "evidence_count": evidence_count,
            "rejected_assertion_count": rejected_assertion_count,
            "artifact": str(artifact.relative_to(self.data_root)),
        }
        return StageResult(generation_id, snapshot.fingerprint,
                           _fingerprint("entity_mention", generation_id, metrics), metrics)

    def identity_resolution(self, snapshot: CorpusSnapshot, generation_id: str) -> StageResult:
        bundles = tuple(
            retain_exact_assertions(item, snapshot)[0]
            for item in self._load_bundles(generation_id)
        )
        mapping: list[dict[str, object]] = []
        auto_linked = 0
        unresolved = 0
        with Neo4jGraphAdapter.from_settings(snapshot.workspace_id) as graph:
            graph.ensure_schema()
            for bundle_index, bundle in enumerate(bundles):
                evidence = validate_extraction(bundle, snapshot, generation_id)
                for mention, provenance in zip(bundle.mentions, evidence, strict=False):
                    entity_type = _entity_type(mention.entity_type)
                    candidate_rows = graph.identity_candidates(
                        normalize_mention(mention.span.source_text), entity_type
                    )
                    transient = EntityMention(
                        new_canonical_id(), mention.span.source_text, entity_type, provenance
                    )
                    resolution = resolve_conservatively(transient, candidate_rows)
                    entity_id = resolution.resolved_entity_id or new_canonical_id()
                    auto_linked += int(resolution.decision == IdentityDecisionKind.AUTO_LINK)
                    unresolved += int(resolution.decision == IdentityDecisionKind.UNRESOLVED)
                    mapping.append(
                        {
                            "bundle_index": bundle_index,
                            "local_id": mention.local_id,
                            "mention_id": transient.mention_id,
                            "entity_id": entity_id,
                            "decision": resolution.decision.value,
                            "candidate_entity_ids": list(resolution.candidate_entity_ids),
                        }
                    )
        artifact = self._artifact(generation_id, "identity")
        artifact.write_text(json.dumps({"mapping": mapping}, sort_keys=True), encoding="utf-8")
        metrics = {
            "mention_count": len(mapping),
            "auto_linked_count": auto_linked,
            "unresolved_count": unresolved,
            "artifact": str(artifact.relative_to(self.data_root)),
        }
        return StageResult(generation_id, snapshot.fingerprint,
                           _fingerprint("identity_resolution", generation_id, metrics), metrics)

    def _mapping(self, generation_id: str) -> list[dict[str, object]]:
        return json.loads(self._artifact(generation_id, "identity").read_text("utf-8"))["mapping"]

    def _constructed(self, snapshot: CorpusSnapshot, generation_id: str):
        bundles = tuple(
            retain_exact_assertions(item, snapshot)[0]
            for item in self._load_bundles(generation_id)
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
                    if row["bundle_index"] == index
                },
            )
            for index, bundle in enumerate(bundles)
        )

    def typed_stage(self, stage: str, snapshot: CorpusSnapshot, generation_id: str) -> StageResult:
        constructed = self._constructed(snapshot, generation_id)
        attribute = {"relation": "relations", "event": "events", "temporal": "temporals",
                     "claim_fact": "claims"}[stage]
        count = sum(len(getattr(item, attribute)) for item in constructed)
        metrics = {f"{attribute}_count": count}
        return StageResult(generation_id, snapshot.fingerprint,
                           _fingerprint(stage, generation_id, metrics), metrics)

    def canonical_graph(self, snapshot: CorpusSnapshot, generation_id: str) -> StageResult:
        bundles = tuple(
            retain_exact_assertions(item, snapshot)[0]
            for item in self._load_bundles(generation_id)
        )
        rows = self._mapping(generation_id)
        rows_by_key = {(row["bundle_index"], row["local_id"]): row for row in rows}
        entities: dict[str, CanonicalEntity] = {}
        with Neo4jGraphAdapter.from_settings(snapshot.workspace_id) as graph:
            graph.ensure_schema()
            for index, bundle in enumerate(bundles):
                evidence = validate_extraction(bundle, snapshot, generation_id)
                for extracted, provenance in zip(bundle.mentions, evidence, strict=False):
                    row = rows_by_key[(index, extracted.local_id)]
                    entity_id = str(row["entity_id"])
                    mention = EntityMention(
                        str(row["mention_id"]), extracted.span.source_text,
                        _entity_type(extracted.entity_type), provenance,
                        tuple(row["candidate_entity_ids"]), entity_id,
                        IdentityDecisionKind(str(row["decision"])),
                    )
                    current = entities.get(entity_id)
                    entities[entity_id] = CanonicalEntity(
                        entity_id, mention.entity_type,
                        current.display_name if current else extracted.span.source_text,
                        KnowledgeAuthority.EXTRACTED,
                        mentions=(*current.mentions, mention) if current else (mention,),
                    )
            for entity in entities.values():
                graph.upsert_canonical_entity(entity, generation_id)
            counts = {"relations": 0, "events": 0, "temporals": 0, "claims": 0}
            for constructed in self._constructed(snapshot, generation_id):
                promoted = promote_constructed_knowledge(graph, snapshot, constructed)
                for key, value in promoted.items():
                    counts[key] += value
        metrics = {"entity_count": len(entities), **counts}
        return StageResult(generation_id, snapshot.fingerprint,
                           _fingerprint("canonical_graph", generation_id, metrics), metrics)

    def retrieval(
        self, snapshot: CorpusSnapshot, generation_id: str
    ) -> tuple[StageResult, StageResult]:
        if generation_id in self._retrieval:
            return self._retrieval[generation_id]
        manifest = self._write_source_manifest(snapshot, generation_id)
        evidence = [
            Evidence(snapshot.workspace_id, "knowledge_candidate", chunk.content, 0.0,
                     chunk.document_id, chunk.document_version_id, chunk.chunk_id,
                     f"passage {chunk.ordinal + 1}", {"knowledge_generation_id": generation_id})
            for chunk in snapshot.chunks
        ]
        bm25_path = self._generation_root(generation_id) / "bm25"
        WorkspaceBM25Index(
            snapshot.workspace_id,
            [SparseDocument(item.chunk_id or "", item.content, item) for item in evidence],
            bm25_path,
            generation_id=generation_id,
        ).save()
        provider = (
            Qwen3EmbeddingAdapter()
            if self.settings.embedding_provider == "ollama"
            and self.settings.embedding_model.startswith("qwen3")
            else OllamaEmbeddingAdapter()
            if self.settings.embedding_provider == "ollama"
            else OpenAIEmbeddingAdapter(self.settings.embedding_model)
        )
        texts = [item.content for item in evidence]
        vectors = asyncio.run(adaptive_embed(provider, texts,
            batch_size=self.settings.embedding_batch_size,
            min_batch_size=self.settings.embedding_min_batch_size)) if texts else []
        if not vectors:
            raise RuntimeError("knowledge candidate has no embeddings to index")
        configuration = EmbeddingConfiguration(
            self.settings.embedding_provider, self.settings.embedding_model, len(vectors[0])
        )
        store = WorkspaceQdrantStore(
            get_qdrant_client(), snapshot.workspace_id,
            embedding_config_hash=configuration.fingerprint, projection_key=generation_id,
        )
        store.upsert("chunks", [
            VectorRecord(item.chunk_id or "", vector, {
                "content": item.content, "chunk_id": item.chunk_id,
                "document_id": item.document_id,
                "document_version_id": item.document_version_id,
                "citation_label": item.citation_label,
            }) for item, vector in zip(evidence, vectors, strict=True)
        ], len(vectors[0]))
        common = {"chunk_count": len(evidence), "embedding_config_hash": configuration.fingerprint}
        result = (
            StageResult(generation_id, snapshot.fingerprint,
                        _fingerprint("bm25", generation_id, {**common, "path": str(bm25_path)}),
                        {
                            "chunk_count": len(evidence),
                            "artifact": str(bm25_path.relative_to(self.data_root)),
                            "source_manifest": str(manifest.relative_to(self.data_root)),
                        }),
            StageResult(generation_id, snapshot.fingerprint,
                        _fingerprint("dense_qdrant", generation_id, common), common),
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
            root / "settings.yaml"
            if (root / "settings.yaml").is_file()
            else adapter.initialize()
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
        return StageResult(generation_id, snapshot.fingerprint,
                           _fingerprint("graphrag", generation_id, metrics), metrics)


def create_production_executor(workspace_id: str) -> KnowledgeWorkflowExecutor:
    return ProductionKnowledgeExecutor(workspace_id).as_workflow_executor()
