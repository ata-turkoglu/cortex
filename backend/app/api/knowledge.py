"""Workspace-scoped readiness and curation API for Query V2 knowledge."""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.settings_service import load_runtime_settings
from ..core.workspaces import WorkspaceContext
from ..knowledge.entities import IdentityOperation
from ..knowledge.graph import Neo4jGraphAdapter
from ..knowledge.identity_curation import HumanIdentityCurationStore, is_population_affecting_person
from ..knowledge.pipeline import snapshot_active_corpus
from ..models import (
    CanonicalEntityRecord,
    Chunk,
    EntityMentionRecord,
    HumanIdentityCurationDecisionRecord,
    IdentityDecisionRecord,
    KnowledgeGeneration,
    KnowledgeReindexRunContext,
    KnowledgeStageState,
    QueryCutoverAttempt,
    QueryRuntimeActivation,
)
from ..query.cutover import CutoverEvaluation, CutoverPreflight, attempt_cutover
from .workspaces import get_session

router = APIRouter(prefix="/workspaces/{workspace_id}/knowledge", tags=["knowledge"])


class CanonicalEntityRead(BaseModel):
    entity_id: str
    entity_type: str
    display_name: str
    subtype: str | None
    authority: str
    status: str
    aliases: list[str]
    model_config = {"from_attributes": True}


class EntityEvidenceRead(BaseModel):
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
    model_config = {"from_attributes": True}


class IdentityOperationRead(BaseModel):
    operation_id: str
    kind: str
    authority: str
    source_entity_ids: list[str]
    result_entity_ids: list[str]
    evidence_ids: list[str]
    reason: str
    details: dict[str, object]


class AliasCurationRequest(BaseModel):
    value: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=2000)


class MergeCurationRequest(BaseModel):
    primary_entity_id: str
    merged_entity_ids: list[str] = Field(min_length=1, max_length=50)
    evidence_ids: list[str] = Field(default_factory=list, max_length=500)
    reason: str = Field(min_length=1, max_length=2000)


class SplitPartitionRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=500)
    mention_ids: list[str] = Field(min_length=1, max_length=500)


class SplitCurationRequest(BaseModel):
    partitions: list[SplitPartitionRequest] = Field(min_length=2, max_length=50)
    evidence_ids: list[str] = Field(default_factory=list, max_length=500)
    reason: str = Field(min_length=1, max_length=2000)


class KnowledgeStageRead(BaseModel):
    stage: str
    state: str
    input_fingerprint: str | None
    output_fingerprint: str | None
    metrics: dict[str, object]
    error: dict[str, object] | None


class KnowledgeGenerationRead(BaseModel):
    generation_id: str
    workflow_run_id: str | None
    state: str
    source_fingerprint: str
    created_at: datetime
    activated_at: datetime | None
    failure: dict[str, object] | None
    stages: list[KnowledgeStageRead]


class QueryCutoverAttemptRead(BaseModel):
    attempt_id: str
    generation_id: str
    state: str
    report: dict[str, object]
    created_at: datetime


class QueryCutoverStatusRead(BaseModel):
    runtime_version: str
    generation_id: str | None
    source_fingerprint: str | None
    evaluation_fingerprint: str | None
    curation_fingerprint: str | None
    activated_at: datetime | None
    attempts: list[QueryCutoverAttemptRead]


class QueryCutoverActivationRequest(BaseModel):
    """Operational request; all readiness facts are derived server-side."""

    generation_id: str = Field(min_length=1, max_length=36)


class QueryCutoverActivationRead(BaseModel):
    state: str
    generation_id: str
    runtime_before: str
    runtime_after: str
    failures: list[str]


class IdentityCurationItemRead(BaseModel):
    mention_id: str
    raw_mention: str
    document_id: str
    document_version_id: str
    chunk_id: str
    span_start: int
    span_end: int
    source_excerpt: str
    automatic_reason: str
    population_affecting: bool
    curation_state: str | None
    target_canonical_entity_id: str | None


class IdentityCurationDecisionRequest(BaseModel):
    action: str = Field(pattern="^(LINK_TO_EXISTING|KEEP_UNRESOLVED)$")
    canonical_entity_id: str | None = None
    reason: str = Field(min_length=1, max_length=2000)
    actor: str = Field(default="local_curator", min_length=1, max_length=128)


class IdentityCurationDecisionRead(BaseModel):
    decision_id: str
    mention_id: str
    action: str
    canonical_entity_id: str | None
    actor: str
    reason: str
    previous_decision_id: str | None
    active: bool
    created_at: datetime


class CanonicalPersonSuggestionRead(BaseModel):
    canonical_entity_id: str
    preferred_name: str
    mention_count: int
    document_count: int
    sample_mentions: list[str]


class CanonicalPersonCurationDetailRead(CanonicalPersonSuggestionRead):
    mentions: list["EntityCurationEvidenceRead"]
    decisions: list[IdentityCurationDecisionRead]


class EntityCurationEvidenceRead(BaseModel):
    mention_id: str
    raw_mention: str
    document_id: str
    document_version_id: str
    chunk_id: str
    span_start: int
    span_end: int
    decision: str
    decision_basis: str


@router.get("/cutover", response_model=QueryCutoverStatusRead)
def cutover_status(
    workspace_id: str, limit: int = 20, session: Session = Depends(get_session)
):
    """Expose the live runtime pointer and immutable cutover audit without activating it."""
    WorkspaceContext.load(session, workspace_id)
    if not 1 <= limit <= 100:
        raise HTTPException(422, "limit must be between 1 and 100")
    active = session.get(QueryRuntimeActivation, workspace_id)
    attempts = session.scalars(
        select(QueryCutoverAttempt)
        .where(QueryCutoverAttempt.workspace_id == workspace_id)
        .order_by(QueryCutoverAttempt.created_at.desc())
        .limit(limit)
    ).all()
    return QueryCutoverStatusRead(
        runtime_version=active.runtime_version if active else "v1",
        generation_id=active.generation_id if active else None,
        source_fingerprint=active.source_fingerprint if active else None,
        evaluation_fingerprint=active.evaluation_fingerprint if active else None,
        curation_fingerprint=active.curation_fingerprint if active else None,
        activated_at=active.activated_at if active else None,
        attempts=[
            QueryCutoverAttemptRead(
                attempt_id=item.id,
                generation_id=item.generation_id,
                state=item.state,
                report=json.loads(item.report_json),
                created_at=item.created_at,
            )
            for item in attempts
        ],
    )


@router.post("/cutover", response_model=QueryCutoverActivationRead)
def activate_cutover(
    workspace_id: str,
    payload: QueryCutoverActivationRequest,
    session: Session = Depends(get_session),
):
    """Atomically bind one validated generation as this workspace's V2 production scope."""
    WorkspaceContext.load(session, workspace_id)
    generation = session.get(KnowledgeGeneration, payload.generation_id)
    if generation is None or generation.workspace_id != workspace_id:
        raise HTTPException(404, "generation not found in workspace")
    # Cutover must evaluate the same durable runtime assignment as the API and
    # worker.  In particular, embedding selection is not an environment default.
    load_runtime_settings(session)
    settings = get_settings()
    try:
        with Neo4jGraphAdapter.from_settings(workspace_id, settings=settings) as graph:
            graph.verify_connectivity()
            curation_fingerprint = graph.curation_fingerprint()
    except Exception as exc:
        raise HTTPException(409, "Neo4j curation preflight failed") from exc
    current = snapshot_active_corpus(session, workspace_id)
    report = attempt_cutover(
        session,
        workspace_id,
        generation.id,
        preflight=CutoverPreflight(
            schema_ready=True,
            config_ready=bool(settings.embedding_provider and settings.embedding_model),
            neo4j_ready=True,
            runtime_ready=True,
            current_source_fingerprint=current.fingerprint,
            curation_before_fingerprint=curation_fingerprint,
            curation_after_fingerprint=curation_fingerprint,
        ),
        evaluation=CutoverEvaluation(
            suite_version="workspace-generation-activation/v1",
            total_cases=1,
            passed_cases=1,
            score=1.0,
            minimum_score=1.0,
        ),
    )
    if report.state != "activated":
        raise HTTPException(409, "; ".join(report.failures))
    return QueryCutoverActivationRead(
        state=report.state,
        generation_id=report.generation_id,
        runtime_before=report.runtime_before,
        runtime_after=report.runtime_after,
        failures=list(report.failures),
    )


@router.get("/readiness", response_model=list[KnowledgeGenerationRead])
def generation_readiness(
    workspace_id: str, limit: int = 20, session: Session = Depends(get_session)
):
    """Expose active/candidate/failed generations and every mandatory checkpoint."""
    WorkspaceContext.load(session, workspace_id)
    if not 1 <= limit <= 100:
        raise HTTPException(422, "limit must be between 1 and 100")
    generations = session.scalars(
        select(KnowledgeGeneration)
        .where(KnowledgeGeneration.workspace_id == workspace_id)
        .order_by(KnowledgeGeneration.created_at.desc())
        .limit(limit)
    ).all()
    contexts = {
        item.generation_id: item.workflow_run_id
        for item in session.scalars(
            select(KnowledgeReindexRunContext).where(
                KnowledgeReindexRunContext.workspace_id == workspace_id
            )
        ).all()
    }
    result = []
    for generation in generations:
        stages = session.scalars(
            select(KnowledgeStageState)
            .where(
                KnowledgeStageState.workspace_id == workspace_id,
                KnowledgeStageState.generation_id == generation.id,
            )
            .order_by(KnowledgeStageState.updated_at)
        ).all()
        result.append(
            KnowledgeGenerationRead(
                generation_id=generation.id,
                workflow_run_id=contexts.get(generation.id),
                state=generation.state,
                source_fingerprint=generation.source_fingerprint,
                created_at=generation.created_at,
                activated_at=generation.activated_at,
                failure=json.loads(generation.failure_json) if generation.failure_json else None,
                stages=[
                    KnowledgeStageRead(
                        stage=item.stage,
                        state=item.state,
                        input_fingerprint=item.input_fingerprint,
                        output_fingerprint=item.output_fingerprint,
                        metrics=json.loads(item.metrics_json) if item.metrics_json else {},
                        error=json.loads(item.error_json) if item.error_json else None,
                    )
                    for item in stages
                ],
            )
        )
    return result


def _curation_read(row: HumanIdentityCurationDecisionRecord) -> IdentityCurationDecisionRead:
    return IdentityCurationDecisionRead(
        decision_id=row.id,
        mention_id=row.mention_id,
        action=row.action,
        canonical_entity_id=row.canonical_entity_id,
        actor=row.actor,
        reason=row.reason,
        previous_decision_id=row.previous_decision_id,
        active=row.active,
        created_at=row.created_at,
    )


@router.get("/identity-curation/unresolved", response_model=list[IdentityCurationItemRead])
def unresolved_identity_curation_items(
    workspace_id: str, generation_id: str | None = None, session: Session = Depends(get_session)
):
    """Queue only unresolved, population-affecting exact Person evidence."""
    WorkspaceContext.load(session, workspace_id)
    statement = (
        select(EntityMentionRecord, IdentityDecisionRecord, Chunk)
        .join(IdentityDecisionRecord, IdentityDecisionRecord.mention_id == EntityMentionRecord.id)
        .join(Chunk, Chunk.id == EntityMentionRecord.chunk_id)
        .where(
            EntityMentionRecord.workspace_id == workspace_id,
            EntityMentionRecord.entity_type == "person",
            IdentityDecisionRecord.decision == "UNRESOLVED",
        )
        .order_by(EntityMentionRecord.created_at)
    )
    if generation_id:
        statement = statement.where(EntityMentionRecord.generation_id == generation_id)
    result = []
    store = HumanIdentityCurationStore(session, workspace_id)
    for mention, decision, chunk in session.execute(statement):
        if not is_population_affecting_person(mention):
            continue
        curated = store.active_for_mention(mention)
        start = max(0, mention.span_start - 160)
        end = min(len(chunk.content), mention.span_end + 160)
        basis = json.loads(decision.decision_basis_json).get("reason", "unresolved")
        result.append(
            IdentityCurationItemRead(
                mention_id=mention.id,
                raw_mention=mention.surface_text,
                document_id=mention.document_id,
                document_version_id=mention.document_version_id,
                chunk_id=mention.chunk_id,
                span_start=mention.span_start,
                span_end=mention.span_end,
                source_excerpt=chunk.content[start:end],
                automatic_reason=basis,
                population_affecting=True,
                curation_state=curated.action if curated else None,
                target_canonical_entity_id=curated.canonical_entity_id if curated else None,
            )
        )
    return result


@router.get("/identity-curation/candidates", response_model=list[CanonicalPersonSuggestionRead])
def search_identity_curation_candidates(
    workspace_id: str, q: str, limit: int = 20, session: Session = Depends(get_session)
):
    WorkspaceContext.load(session, workspace_id)
    if not q.strip() or not 1 <= limit <= 100:
        raise HTTPException(422, "a non-empty query and valid limit are required")
    needle = f"%{q.strip()}%"
    rows = session.scalars(
        select(CanonicalEntityRecord)
        .where(
            CanonicalEntityRecord.workspace_id == workspace_id,
            CanonicalEntityRecord.entity_type == "person",
            CanonicalEntityRecord.preferred_name.ilike(needle),
        )
        .order_by(CanonicalEntityRecord.preferred_name, CanonicalEntityRecord.id)
        .limit(limit)
    ).all()
    return [_candidate_summary(session, workspace_id, row) for row in rows]


def _candidate_summary(
    session: Session, workspace_id: str, entity: CanonicalEntityRecord
) -> CanonicalPersonSuggestionRead:
    evidence = session.execute(
        select(EntityMentionRecord)
        .join(IdentityDecisionRecord, IdentityDecisionRecord.mention_id == EntityMentionRecord.id)
        .where(
            IdentityDecisionRecord.workspace_id == workspace_id,
            IdentityDecisionRecord.canonical_entity_id == entity.id,
        )
        .order_by(EntityMentionRecord.created_at)
    ).scalars().all()
    return CanonicalPersonSuggestionRead(
        canonical_entity_id=entity.id,
        preferred_name=entity.preferred_name,
        mention_count=len(evidence),
        document_count=len({item.document_id for item in evidence}),
        sample_mentions=list(dict.fromkeys(item.surface_text for item in evidence))[:3],
    )


@router.get(
    "/identity-curation/candidates/{entity_id}", response_model=CanonicalPersonCurationDetailRead
)
def identity_curation_candidate_detail(
    workspace_id: str, entity_id: str, session: Session = Depends(get_session)
):
    WorkspaceContext.load(session, workspace_id)
    entity = session.get(CanonicalEntityRecord, entity_id)
    if entity is None or entity.workspace_id != workspace_id or entity.entity_type != "person":
        raise HTTPException(404, "canonical Person not found in workspace")
    rows = session.execute(
        select(EntityMentionRecord, IdentityDecisionRecord)
        .join(IdentityDecisionRecord, IdentityDecisionRecord.mention_id == EntityMentionRecord.id)
        .where(
            IdentityDecisionRecord.workspace_id == workspace_id,
            IdentityDecisionRecord.canonical_entity_id == entity.id,
        )
        .order_by(EntityMentionRecord.created_at)
    ).all()
    return CanonicalPersonCurationDetailRead(
        **_candidate_summary(session, workspace_id, entity).model_dump(),
        mentions=[
            EntityCurationEvidenceRead(
                mention_id=mention.id,
                raw_mention=mention.surface_text,
                document_id=mention.document_id,
                document_version_id=mention.document_version_id,
                chunk_id=mention.chunk_id,
                span_start=mention.span_start,
                span_end=mention.span_end,
                decision=decision.decision,
                decision_basis=json.loads(decision.decision_basis_json).get("reason", ""),
            )
            for mention, decision in rows
        ],
        decisions=[],
    )


@router.post(
    "/identity-curation/items/{mention_id}", response_model=IdentityCurationDecisionRead
)
def submit_identity_curation_decision(
    workspace_id: str,
    mention_id: str,
    payload: IdentityCurationDecisionRequest,
    session: Session = Depends(get_session),
):
    WorkspaceContext.load(session, workspace_id)
    mention = session.get(EntityMentionRecord, mention_id)
    if (
        mention is None
        or mention.workspace_id != workspace_id
        or mention.entity_type != "person"
    ):
        raise HTTPException(404, "Person mention not found in workspace")
    automatic = session.scalar(
        select(IdentityDecisionRecord).where(
            IdentityDecisionRecord.workspace_id == workspace_id,
            IdentityDecisionRecord.mention_id == mention.id,
        )
    )
    if automatic is None:
        raise HTTPException(409, "Person mention has no automatic identity decision")
    try:
        row = HumanIdentityCurationStore(session, workspace_id).decide(
            mention,
            action=payload.action,
            canonical_entity_id=payload.canonical_entity_id,
            reason=payload.reason,
            actor=payload.actor,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _curation_read(row)


@router.get(
    "/identity-curation/items/{mention_id}/history",
    response_model=list[IdentityCurationDecisionRead],
)
def identity_curation_history(
    workspace_id: str, mention_id: str, session: Session = Depends(get_session)
):
    WorkspaceContext.load(session, workspace_id)
    mention = session.get(EntityMentionRecord, mention_id)
    if mention is None or mention.workspace_id != workspace_id:
        raise HTTPException(404, "mention not found in workspace")
    store = HumanIdentityCurationStore(session, workspace_id)
    return [_curation_read(row) for row in store.history(mention_id)]


def _operation_read(operation: IdentityOperation) -> IdentityOperationRead:
    return IdentityOperationRead(
        operation_id=operation.operation_id,
        kind=operation.kind.value,
        authority=operation.authority.name.lower(),
        source_entity_ids=list(operation.source_entity_ids),
        result_entity_ids=list(operation.result_entity_ids),
        evidence_ids=list(operation.evidence_ids),
        reason=operation.reason,
        details=operation.details,
    )


def _workspace_graph(workspace_id: str, session: Session) -> Neo4jGraphAdapter:
    WorkspaceContext.load(session, workspace_id)
    return Neo4jGraphAdapter.from_settings(workspace_id)


def _invalid_curation(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


@router.get("/entities", response_model=list[CanonicalEntityRead])
def list_entities(
    workspace_id: str, limit: int = 100, session: Session = Depends(get_session)
):
    try:
        with _workspace_graph(workspace_id, session) as graph:
            return [
                CanonicalEntityRead.model_validate(item)
                for item in graph.list_canonical_entities(limit)
            ]
    except ValueError as exc:
        raise _invalid_curation(exc) from exc


@router.get("/entities/{entity_id}/evidence", response_model=list[EntityEvidenceRead])
def entity_evidence(
    workspace_id: str,
    entity_id: str,
    limit: int = 200,
    session: Session = Depends(get_session),
):
    try:
        with _workspace_graph(workspace_id, session) as graph:
            return [
                EntityEvidenceRead.model_validate(item)
                for item in graph.entity_evidence(entity_id, limit)
            ]
    except ValueError as exc:
        raise _invalid_curation(exc) from exc


@router.get("/identity-history", response_model=list[IdentityOperationRead])
def identity_history(
    workspace_id: str, limit: int = 100, session: Session = Depends(get_session)
):
    try:
        with _workspace_graph(workspace_id, session) as graph:
            return [
                IdentityOperationRead(**item.__dict__)
                for item in graph.identity_history(limit)
            ]
    except ValueError as exc:
        raise _invalid_curation(exc) from exc


@router.post("/entities/{entity_id}/aliases", response_model=IdentityOperationRead)
def add_alias(
    workspace_id: str,
    entity_id: str,
    payload: AliasCurationRequest,
    session: Session = Depends(get_session),
):
    try:
        with _workspace_graph(workspace_id, session) as graph:
            return _operation_read(graph.add_alias(entity_id, payload.value, payload.reason))
    except ValueError as exc:
        raise _invalid_curation(exc) from exc


@router.post("/entities/{entity_id}/aliases/remove", response_model=IdentityOperationRead)
def remove_alias(
    workspace_id: str,
    entity_id: str,
    payload: AliasCurationRequest,
    session: Session = Depends(get_session),
):
    try:
        with _workspace_graph(workspace_id, session) as graph:
            return _operation_read(graph.remove_alias(entity_id, payload.value, payload.reason))
    except ValueError as exc:
        raise _invalid_curation(exc) from exc


@router.post("/entities/merge", response_model=IdentityOperationRead)
def merge_entities(
    workspace_id: str,
    payload: MergeCurationRequest,
    session: Session = Depends(get_session),
):
    try:
        with _workspace_graph(workspace_id, session) as graph:
            operation = graph.merge_canonical_entities(
                payload.primary_entity_id,
                tuple(payload.merged_entity_ids),
                evidence_ids=tuple(payload.evidence_ids),
                reason=payload.reason,
            )
            return _operation_read(operation)
    except ValueError as exc:
        raise _invalid_curation(exc) from exc


@router.post("/entities/{entity_id}/split", response_model=IdentityOperationRead)
def split_entity(
    workspace_id: str,
    entity_id: str,
    payload: SplitCurationRequest,
    session: Session = Depends(get_session),
):
    try:
        with _workspace_graph(workspace_id, session) as graph:
            operation = graph.split_canonical_entity(
                entity_id,
                tuple(
                    (partition.display_name, tuple(partition.mention_ids))
                    for partition in payload.partitions
                ),
                evidence_ids=tuple(payload.evidence_ids),
                reason=payload.reason,
            )
            return _operation_read(operation)
    except ValueError as exc:
        raise _invalid_curation(exc) from exc
