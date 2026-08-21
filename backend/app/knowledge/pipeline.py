"""Worker-safe orchestration for one corpus-wide knowledge construction generation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Chunk, Document, KnowledgeGeneration
from .construction import (
    MANDATORY_KNOWLEDGE_STAGES,
    activate_if_ready,
    create_generation,
    fail_stage,
    mark_stage_ready,
    mark_stage_running,
)


@dataclass(frozen=True)
class SourceChunk:
    chunk_id: str
    document_id: str
    document_version_id: str
    logical_document_id: str
    ordinal: int
    content: str
    content_hash: str


@dataclass(frozen=True)
class CorpusSnapshot:
    workspace_id: str
    fingerprint: str
    chunks: tuple[SourceChunk, ...]


@dataclass(frozen=True)
class StageResult:
    generation_id: str
    input_fingerprint: str
    output_fingerprint: str
    metrics: dict[str, object]


class KnowledgeStageExecutor(Protocol):
    """External/model/store work. Implementations must preserve stronger graph authority."""

    def execute(
        self, stage: str, snapshot: CorpusSnapshot, generation_id: str
    ) -> StageResult: ...


def snapshot_active_corpus(session: Session, workspace_id: str) -> CorpusSnapshot:
    rows = session.execute(
        select(Chunk, Document)
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Chunk.workspace_id == workspace_id,
            Document.workspace_id == workspace_id,
            Chunk.deleted_at.is_(None),
            Document.deleted_at.is_(None),
            Chunk.document_version_id == Document.active_version_id,
        )
        .order_by(Chunk.document_id, Chunk.ordinal, Chunk.id)
    ).all()
    chunks = tuple(
        SourceChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            document_version_id=chunk.document_version_id,
            logical_document_id=chunk.logical_document_id or "",
            ordinal=chunk.ordinal,
            content=chunk.content,
            content_hash=chunk.content_hash,
        )
        for chunk, _document in rows
    )
    digest = hashlib.sha256()
    digest.update(workspace_id.encode())
    for chunk in chunks:
        digest.update(
            json.dumps(
                (
                    chunk.chunk_id,
                    chunk.document_id,
                    chunk.document_version_id,
                    chunk.logical_document_id,
                    chunk.ordinal,
                    chunk.content_hash,
                ),
                separators=(",", ":"),
            ).encode()
        )
    return CorpusSnapshot(workspace_id, digest.hexdigest(), chunks)


def run_knowledge_construction(
    session_factory, workspace_id: str, executor: KnowledgeStageExecutor
):
    """Run external stages between short commits, then atomically activate readiness."""
    session: Session = session_factory()
    try:
        snapshot = snapshot_active_corpus(session, workspace_id)
        generation = create_generation(session, workspace_id, snapshot.fingerprint)
        generation_id = generation.id
        mark_stage_ready(
            session,
            generation,
            "source_relational",
            input_fingerprint=snapshot.fingerprint,
            output_fingerprint=snapshot.fingerprint,
            metrics={"chunk_count": len(snapshot.chunks)},
        )
        session.commit()
    finally:
        session.close()

    for stage in MANDATORY_KNOWLEDGE_STAGES[1:]:
        session = session_factory()
        try:
            generation = session.get(KnowledgeGeneration, generation_id)
            if generation is None:
                raise RuntimeError("candidate generation disappeared")
            mark_stage_running(
                session,
                generation,
                stage,
                input_fingerprint=snapshot.fingerprint,
            )
            session.commit()
        finally:
            session.close()
        try:
            # Deliberately outside a SQLite transaction: this may invoke models or stores.
            result = executor.execute(stage, snapshot, generation_id)
            if (
                result.generation_id != generation_id
                or result.input_fingerprint != snapshot.fingerprint
            ):
                raise ValueError("stage result generation or source fingerprint mismatch")
        except Exception as exc:
            session = session_factory()
            try:
                generation = session.get(KnowledgeGeneration, generation_id)
                if generation is not None:
                    fail_stage(session, generation, stage, summary=str(exc))
                    session.commit()
            finally:
                session.close()
            raise
        session = session_factory()
        try:
            generation = session.get(KnowledgeGeneration, generation_id)
            if generation is None:
                raise RuntimeError("candidate generation disappeared")
            mark_stage_ready(
                session,
                generation,
                stage,
                input_fingerprint=snapshot.fingerprint,
                output_fingerprint=result.output_fingerprint,
                metrics=result.metrics,
            )
            session.commit()
        finally:
            session.close()

    session = session_factory()
    try:
        generation = session.get(KnowledgeGeneration, generation_id)
        if generation is None or not activate_if_ready(session, generation):
            raise RuntimeError("knowledge generation did not pass the readiness gate")
        session.commit()
        return generation_id
    finally:
        session.close()
