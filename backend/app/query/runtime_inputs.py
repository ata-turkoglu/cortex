"""Short-transaction loader for detached V2 execution inputs."""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    CanonicalGenerationStatusRecord,
    KnowledgeGeneration,
    KnowledgeStageState,
    QueryRuntimeActivation,
)
from .briefing import WorkspaceBriefing
from .context import ConversationContext, load_conversation_context
from .ir import IRVocabulary
from .planning import CapabilityReadiness, PlanningReadinessSnapshot
from .scope import GenerationScope

CAPABILITY_FAMILIES = {
    "retrieval.grounded": ("retrieval.hybrid_search", "retrieval.semantic_search"),
    "graphrag.grounded": ("graphrag.local", "graphrag.global", "graphrag.drift"),
    "canonical.exhaustive": (
        "structured.enumerate",
        "structured.filter",
        "structured.join",
        "structured.distinct",
        "structured.group",
        "structured.aggregate",
        "structured.count",
        "structured.rank",
        "structured.sort",
        "structured.limit",
        "structured.project",
        "structured.temporal_filter",
        "structured.compare",
        "structured.exists",
        "structured.relation_aggregate",
    ),
    "canonical.graph": (
        "graph.entity_resolve",
        "graph.traverse",
        "graph.multi_hop",
        "graph.temporal_reasoning",
        "graph.event_population",
        "graph.event_filter",
        "graph.event_participation",
        "graph.provenance_traversal",
        "graph.contradiction_analysis",
    ),
}


class RuntimeInputError(ValueError):
    """Persisted state cannot safely produce one V2 execution snapshot."""


@dataclass(frozen=True)
class FixedGenerationScopeResolver:
    scope: GenerationScope

    def resolve(self, workspace_id: str) -> GenerationScope:
        if workspace_id != self.scope.workspace_id:
            raise RuntimeInputError("GENERATION_SCOPE_WORKSPACE_MISMATCH")
        return self.scope


@dataclass(frozen=True)
class V2RuntimeInputs:
    conversation_context: ConversationContext
    vocabulary: IRVocabulary
    readiness: PlanningReadinessSnapshot
    workspace_briefing: WorkspaceBriefing | None
    generation_scope: GenerationScope
    generation_scope_resolver: FixedGenerationScopeResolver


class V2RuntimeContextLoader:
    """Load persisted state once, then hand detached values to V2 execution."""

    def __init__(self, *, history_limit: int) -> None:
        self.history_limit = history_limit

    def load(
        self,
        session: Session,
        workspace_id: str,
        conversation_id: str,
        *,
        workspace_briefing: WorkspaceBriefing | None = None,
    ) -> V2RuntimeInputs:
        context = load_conversation_context(
            session, workspace_id, conversation_id, history_limit=self.history_limit
        )
        generation = _production_generation(session, workspace_id)
        scope = _scope_for_generation(session, generation)
        if workspace_briefing and (
            workspace_briefing.workspace_id != workspace_id
            or workspace_briefing.generation_id != scope.generation_id
        ):
            raise RuntimeInputError("workspace briefing crosses production generation scope")
        readiness = _readiness(session, workspace_id, scope.generation_id)
        return V2RuntimeInputs(
            conversation_context=context,
            vocabulary=IRVocabulary.core(),
            readiness=readiness,
            workspace_briefing=workspace_briefing,
            generation_scope=scope,
            generation_scope_resolver=FixedGenerationScopeResolver(scope),
        )


def _production_generation(session: Session, workspace_id: str) -> KnowledgeGeneration:
    activation = session.get(QueryRuntimeActivation, workspace_id)
    if activation is None or activation.runtime_version != "v2" or not activation.generation_id:
        raise RuntimeInputError("workspace has no validated V2 production generation")
    generation = session.get(KnowledgeGeneration, activation.generation_id)
    if generation is None or generation.workspace_id != workspace_id:
        raise RuntimeInputError("no active generation is available for V2 execution")
    if not (
        generation.source_manifest_uri
        and generation.source_manifest_hash
        and generation.source_chunk_count is not None
    ):
        raise RuntimeInputError("generation is not eligible for V2 trusted-source execution")
    return generation


def _scope_for_generation(session: Session, generation: KnowledgeGeneration) -> GenerationScope:
    dense = session.scalar(
        select(KnowledgeStageState).where(
            KnowledgeStageState.workspace_id == generation.workspace_id,
            KnowledgeStageState.generation_id == generation.id,
            KnowledgeStageState.stage == "dense_qdrant",
            KnowledgeStageState.state == "ready",
        )
    )
    try:
        embedding_config_hash = json.loads(dense.metrics_json or "{}")["embedding_config_hash"]
    except (AttributeError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeInputError(
            "active generation has no compatible dense embedding scope"
        ) from error
    return GenerationScope(generation.workspace_id, generation.id, str(embedding_config_hash))


def _readiness(
    session: Session, workspace_id: str, generation_id: str
) -> PlanningReadinessSnapshot:
    states = {
        state.stage: state
        for state in session.scalars(
            select(KnowledgeStageState).where(
                KnowledgeStageState.workspace_id == workspace_id,
                KnowledgeStageState.generation_id == generation_id,
            )
        )
    }
    required = ("source_relational", "bm25", "dense_qdrant")
    if any(states.get(stage) is None or states[stage].state != "ready" for stage in required):
        raise RuntimeInputError("active generation V2 source/retrieval projections are not ready")
    canonical_status = session.scalar(
        select(CanonicalGenerationStatusRecord).where(
            CanonicalGenerationStatusRecord.workspace_id == workspace_id,
            CanonicalGenerationStatusRecord.generation_id == generation_id,
            CanonicalGenerationStatusRecord.projection_version == "minimal-core-v1",
        )
    )
    canonical_ready = bool(canonical_status and canonical_status.status == "READY")
    graphrag_ready = states.get("graphrag") is not None and states["graphrag"].state == "ready"
    canonical_capabilities = CAPABILITY_FAMILIES["canonical.exhaustive"]
    canonical_entries = tuple(
        CapabilityReadiness(
            workspace_id=workspace_id,
            engine=("structured" if capability.startswith("structured.") else "knowledge_graph"),
            capability=capability,
            state=("ready" if canonical_ready else "unavailable"),
            generation_id=generation_id,
            ready_projections=("sqlite_canonical_core",) if canonical_ready else (),
            detail=(
                None
                if canonical_ready
                else (
                    f"canonical exhaustive status is {canonical_status.status.lower()}"
                    if canonical_status
                    else "SQLite canonical completeness is not ready for this generation"
                )
            ),
        )
        for capability in canonical_capabilities
    )
    graph_entries = tuple(
        CapabilityReadiness(
            workspace_id=workspace_id,
            engine="knowledge_graph",
            capability=capability,
            state="unavailable",
            generation_id=None,
            ready_projections=(),
            detail="Neo4j is a rebuildable projection and canonical.graph is not implemented",
        )
        for capability in CAPABILITY_FAMILIES["canonical.graph"]
    )
    graphrag_entries = tuple(
        CapabilityReadiness(
            workspace_id=workspace_id,
            engine="graphrag",
            capability=f"graphrag.{mode}",
            state="ready" if graphrag_ready and mode != "community_context" else "unavailable",
            generation_id=(
                generation_id if graphrag_ready and mode != "community_context" else None
            ),
            ready_projections=(
                ("graphrag",) if graphrag_ready and mode != "community_context" else ()
            ),
            detail=(
                None
                if graphrag_ready and mode != "community_context"
                else (
                    "community-context is not a production V2 GraphRAG mode"
                    if mode == "community_context"
                    else (
                        "generation GraphRAG artifacts are not ready for trusted provenance "
                        "validation"
                    )
                )
            ),
        )
        for mode in ("local", "global", "drift", "community_context")
    )
    return PlanningReadinessSnapshot(
        workspace_id=workspace_id,
        active_generation_id=generation_id,
        capabilities=(
            *canonical_entries,
            *graph_entries,
            CapabilityReadiness(
                workspace_id=workspace_id,
                engine="retrieval",
                capability="retrieval.hybrid_search",
                state="ready",
                generation_id=generation_id,
                ready_projections=("bm25", "dense_qdrant"),
            ),
            *graphrag_entries,
            CapabilityReadiness(
                workspace_id=workspace_id,
                engine="retrieval",
                capability="retrieval.semantic_search",
                state="ready",
                generation_id=generation_id,
                ready_projections=("dense_qdrant",),
            ),
            CapabilityReadiness(
                workspace_id=workspace_id,
                engine="reasoning",
                capability="reasoning.evidence_synthesis",
                state="ready",
            ),
            CapabilityReadiness(
                workspace_id=workspace_id,
                engine="result_evidence",
                capability="evidence.reconcile_and_validate",
                state="ready",
            ),
        ),
    )
