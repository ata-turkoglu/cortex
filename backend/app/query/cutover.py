"""Fail-closed, evaluation-gated Query V2 sharp cutover."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..knowledge.construction import MANDATORY_KNOWLEDGE_STAGES
from ..models import (
    KnowledgeGeneration,
    KnowledgeStageState,
    QueryCutoverAttempt,
    QueryRuntimeActivation,
)


class CutoverEvaluation(BaseModel):
    """Detached output of the acceptance evaluator."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    suite_version: str = Field(min_length=1, max_length=64)
    total_cases: int = Field(ge=1)
    passed_cases: int = Field(ge=0)
    score: float = Field(ge=0, le=1)
    minimum_score: float = Field(ge=0, le=1)
    mandatory_failures: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_counts(self):
        if self.passed_cases > self.total_cases:
            raise ValueError("passed_cases cannot exceed total_cases")
        return self

    @property
    def passed(self) -> bool:
        return not self.mandatory_failures and self.score >= self.minimum_score

    @property
    def fingerprint(self) -> str:
        payload = self.model_dump_json(exclude_none=True)
        return hashlib.sha256(payload.encode()).hexdigest()


class CutoverPreflight(BaseModel):
    """Detached infrastructure/corpus checks gathered before the SQLite write."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_ready: bool
    config_ready: bool
    neo4j_ready: bool
    runtime_ready: bool
    current_source_fingerprint: str = Field(min_length=1, max_length=128)
    curation_before_fingerprint: str = Field(min_length=1, max_length=128)
    curation_after_fingerprint: str = Field(min_length=1, max_length=128)


class CutoverReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    state: str
    workspace_id: str
    generation_id: str
    runtime_before: str
    runtime_after: str
    failures: tuple[str, ...]
    evaluation_fingerprint: str


def active_runtime(session: Session, workspace_id: str) -> QueryRuntimeActivation | None:
    return session.get(QueryRuntimeActivation, workspace_id)


def _failures(
    session: Session,
    workspace_id: str,
    generation: KnowledgeGeneration | None,
    preflight: CutoverPreflight,
    evaluation: CutoverEvaluation,
) -> list[str]:
    failures = []
    if generation is None or generation.workspace_id != workspace_id:
        return ["candidate generation is missing or outside the workspace"]
    if generation.state != "active":
        failures.append("candidate generation is not the active complete projection")
    if generation.source_fingerprint != preflight.current_source_fingerprint:
        failures.append("active corpus changed after the generation snapshot")
    states = session.scalars(
        select(KnowledgeStageState).where(
            KnowledgeStageState.workspace_id == workspace_id,
            KnowledgeStageState.generation_id == generation.id,
        )
    ).all()
    by_stage = {item.stage: item for item in states}
    if any(
        stage not in by_stage
        or by_stage[stage].state != "ready"
        or by_stage[stage].input_fingerprint != generation.source_fingerprint
        or not by_stage[stage].output_fingerprint
        for stage in MANDATORY_KNOWLEDGE_STAGES
    ):
        failures.append("mandatory projections are not ready for one exact generation")
    for ready, label in (
        (preflight.schema_ready, "schema migration is not ready"),
        (preflight.config_ready, "V2 configuration is not ready"),
        (preflight.neo4j_ready, "Neo4j is not ready"),
        (preflight.runtime_ready, "Query V2 runtime is not ready"),
    ):
        if not ready:
            failures.append(label)
    if preflight.curation_before_fingerprint != preflight.curation_after_fingerprint:
        failures.append("user-curated knowledge changed during rebuild")
    if not evaluation.passed:
        failures.append("acceptance evaluation did not pass")
    return failures


def attempt_cutover(
    session: Session,
    workspace_id: str,
    generation_id: str,
    *,
    preflight: CutoverPreflight,
    evaluation: CutoverEvaluation,
) -> CutoverReport:
    """Atomically switch one workspace only when every detached gate passes."""
    timestamp = datetime.now(UTC)
    current = active_runtime(session, workspace_id)
    runtime_before = current.runtime_version if current else "v1"
    generation = session.get(KnowledgeGeneration, generation_id)
    failures = _failures(session, workspace_id, generation, preflight, evaluation)
    state = "rejected" if failures else "activated"
    runtime_after = runtime_before
    if not failures:
        if current is None:
            current = QueryRuntimeActivation(workspace_id=workspace_id, updated_at=timestamp)
            session.add(current)
        current.runtime_version = "v2"
        current.generation_id = generation_id
        current.source_fingerprint = preflight.current_source_fingerprint
        current.evaluation_fingerprint = evaluation.fingerprint
        current.curation_fingerprint = preflight.curation_after_fingerprint
        current.activated_at = timestamp
        current.updated_at = timestamp
        runtime_after = "v2"
    report = CutoverReport(
        state=state,
        workspace_id=workspace_id,
        generation_id=generation_id,
        runtime_before=runtime_before,
        runtime_after=runtime_after,
        failures=tuple(failures),
        evaluation_fingerprint=evaluation.fingerprint,
    )
    session.add(
        QueryCutoverAttempt(
            id=str(uuid4()),
            workspace_id=workspace_id,
            generation_id=generation_id,
            state=state,
            report_json=json.dumps(report.model_dump(), ensure_ascii=False, sort_keys=True),
            created_at=timestamp,
            finished_at=timestamp,
        )
    )
    session.flush()
    return report
