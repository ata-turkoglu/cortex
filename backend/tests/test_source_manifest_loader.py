import hashlib
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.knowledge.construction import create_generation, validate_manifest_projection_agreement
from app.knowledge.pipeline import CorpusSnapshot, SourceChunk
from app.knowledge.source_manifest import (
    SourceManifestValidationError,
    load_generation_manifest,
    write_generation_manifest,
)
from app.models import Base, KnowledgeStageState, Workspace


def _prepared(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    session = sessionmaker(bind=engine)()
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    session.add(
        Workspace(
            id="workspace",
            slug="workspace",
            name="Workspace",
            state="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.flush()
    content = "authoritative content"
    snapshot = CorpusSnapshot(
        "workspace",
        "fingerprint",
        (
            SourceChunk(
                "chunk",
                "document",
                "version",
                "logical",
                0,
                content,
                hashlib.sha256(content.encode()).hexdigest(),
            ),
        ),
    )
    generation = create_generation(session, "workspace", "fingerprint")
    identity = write_generation_manifest(tmp_path, snapshot, generation.id)
    generation.source_manifest_uri = identity.uri
    generation.source_manifest_hash = identity.sha256
    generation.source_chunk_count = identity.chunk_count
    session.flush()
    return session, generation, tmp_path / identity.uri


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("not-json\n", "invalid manifest JSONL"),
        ("{}\n", "hash mismatch"),
    ],
)
def test_loader_rejects_corrupt_jsonl_or_hash_tampering(tmp_path, payload, message):
    session, generation, path = _prepared(tmp_path)
    path.write_bytes(payload.encode())
    if message == "invalid manifest JSONL":
        generation.source_manifest_hash = hashlib.sha256(payload.encode()).hexdigest()
    with pytest.raises(SourceManifestValidationError, match=message):
        load_generation_manifest(session, "workspace", generation.id, tmp_path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("workspace_id", "other", "workspace mismatch"),
        ("generation_id", "other", "generation mismatch"),
    ],
)
def test_loader_rejects_foreign_record_identity(tmp_path, field, value, message):
    session, generation, path = _prepared(tmp_path)
    record = json.loads(path.read_text(encoding="utf-8"))
    record[field] = value
    payload = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(payload)
    generation.source_manifest_hash = hashlib.sha256(payload).hexdigest()
    with pytest.raises(SourceManifestValidationError, match=message):
        load_generation_manifest(session, "workspace", generation.id, tmp_path)


def test_loader_rejects_duplicate_count_and_content_integrity(tmp_path):
    session, generation, path = _prepared(tmp_path)
    record = json.loads(path.read_text(encoding="utf-8"))
    payload = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n") * 2
    path.write_bytes(payload.encode())
    generation.source_manifest_hash = hashlib.sha256(payload.encode()).hexdigest()
    generation.source_chunk_count = 2
    with pytest.raises(SourceManifestValidationError, match="duplicate"):
        load_generation_manifest(session, "workspace", generation.id, tmp_path)


def test_readiness_rejects_projection_membership_or_content_mismatch(tmp_path):
    session, generation, _ = _prepared(tmp_path)
    expected_hash = hashlib.sha256(b"authoritative content").hexdigest()
    for stage in ("bm25", "dense_qdrant"):
        state = (
            session.query(KnowledgeStageState)
            .filter_by(generation_id=generation.id, stage=stage)
            .one()
        )
        state.metrics_json = json.dumps(
            {
                "chunk_count": 1,
                "chunk_ids": ["wrong"],
                "content_hashes": {"chunk": expected_hash},
                "source_manifest_hash": generation.source_manifest_hash,
            }
        )
    assert not validate_manifest_projection_agreement(session, generation, tmp_path)
