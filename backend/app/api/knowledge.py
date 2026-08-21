"""Workspace-scoped readiness and curation API for Query V2 knowledge."""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.workspaces import WorkspaceContext
from ..knowledge.entities import IdentityOperation
from ..knowledge.graph import Neo4jGraphAdapter
from ..models import (
    KnowledgeGeneration,
    KnowledgeReindexRunContext,
    KnowledgeStageState,
    QueryCutoverAttempt,
    QueryRuntimeActivation,
)
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
