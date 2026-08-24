"""Immutable, generation-owned source manifests for candidate retrieval projections."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ..query.orchestration import TrustedSource

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from .pipeline import CorpusSnapshot


class SourceManifestValidationError(RuntimeError):
    """A candidate source authority is absent, corrupt, or belongs to another scope."""


@dataclass(frozen=True)
class SourceManifestIdentity:
    uri: str
    sha256: str
    chunk_count: int


def manifest_path(data_root: Path, workspace_id: str, generation_id: str) -> Path:
    root = data_root.resolve()
    path = (
        root
        / "workspaces"
        / workspace_id
        / "knowledge-candidates"
        / generation_id
        / "source"
        / "manifest.jsonl"
    ).resolve()
    if root not in path.parents:
        raise SourceManifestValidationError("manifest path escapes data root")
    return path


def _record(snapshot: CorpusSnapshot, generation_id: str, chunk) -> dict[str, object]:
    return {
        "workspace_id": snapshot.workspace_id,
        "generation_id": generation_id,
        "document_id": chunk.document_id,
        "document_version_id": chunk.document_version_id,
        "logical_document_id": chunk.logical_document_id,
        "chunk_id": chunk.chunk_id,
        "chunk_index": chunk.ordinal,
        "content_hash": chunk.content_hash,
        "content": chunk.content,
        "citation_label": f"passage {chunk.ordinal + 1}",
    }


def manifest_bytes(snapshot: CorpusSnapshot, generation_id: str) -> bytes:
    """Canonical JSONL bytes for a snapshot, including a final newline."""
    records = sorted(
        (_record(snapshot, generation_id, chunk) for chunk in snapshot.chunks),
        key=lambda item: (
            str(item["document_id"]),
            str(item["document_version_id"]),
            str(item["logical_document_id"]),
            int(item["chunk_index"]),
            str(item["chunk_id"]),
        ),
    )
    return b"".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        + b"\n"
        for record in records
    )


def write_generation_manifest(
    data_root: Path, snapshot: CorpusSnapshot, generation_id: str
) -> SourceManifestIdentity:
    path = manifest_path(data_root, snapshot.workspace_id, generation_id)
    payload = manifest_bytes(snapshot, generation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise SourceManifestValidationError("source manifest is immutable once written")
    else:
        path.write_bytes(payload)
    return SourceManifestIdentity(
        uri=path.relative_to(data_root.resolve()).as_posix(),
        sha256=hashlib.sha256(payload).hexdigest(),
        chunk_count=len(snapshot.chunks),
    )


def _resolved_uri(data_root: Path, uri: str) -> Path:
    root = data_root.resolve()
    path = (root / uri).resolve()
    if root not in path.parents:
        raise SourceManifestValidationError("manifest URI escapes data root")
    return path


def load_generation_manifest(
    session: Session, workspace_id: str, generation_id: str, data_root: Path
) -> tuple[TrustedSource, ...]:
    """Load a trusted candidate source set, failing closed on every integrity violation."""
    from ..models import KnowledgeGeneration

    generation = session.get(KnowledgeGeneration, generation_id)
    if generation is None or generation.workspace_id != workspace_id:
        raise SourceManifestValidationError("generation is missing or outside the workspace")
    if not generation.source_manifest_uri or not generation.source_manifest_hash:
        raise SourceManifestValidationError("generation has no immutable source manifest")
    if generation.source_chunk_count is None:
        raise SourceManifestValidationError("generation has no authoritative source chunk count")
    path = _resolved_uri(data_root, generation.source_manifest_uri)
    try:
        payload = path.read_bytes()
    except FileNotFoundError as error:
        raise SourceManifestValidationError("source manifest is missing") from error
    actual_hash = hashlib.sha256(payload).hexdigest()
    if actual_hash != generation.source_manifest_hash:
        raise SourceManifestValidationError("source manifest hash mismatch")
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(payload.splitlines(), start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise SourceManifestValidationError(
                f"invalid manifest JSONL at line {line_number}"
            ) from error
        if not isinstance(record, dict):
            raise SourceManifestValidationError("manifest record must be an object")
        records.append(record)
    if len(records) != generation.source_chunk_count:
        raise SourceManifestValidationError("source manifest count mismatch")
    required = {
        "workspace_id",
        "generation_id",
        "document_id",
        "document_version_id",
        "logical_document_id",
        "chunk_id",
        "content_hash",
        "content",
        "citation_label",
    }
    sources: list[TrustedSource] = []
    chunk_ids: set[str] = set()
    for record in records:
        missing = required - set(record)
        if missing:
            raise SourceManifestValidationError(
                "manifest record is missing required identity fields"
            )
        if record["workspace_id"] != workspace_id:
            raise SourceManifestValidationError("manifest workspace mismatch")
        if record["generation_id"] != generation_id:
            raise SourceManifestValidationError("manifest generation mismatch")
        chunk_id = str(record["chunk_id"])
        if chunk_id in chunk_ids:
            raise SourceManifestValidationError("manifest contains duplicate chunk_id")
        chunk_ids.add(chunk_id)
        content = str(record["content"])
        if hashlib.sha256(content.encode("utf-8")).hexdigest() != record["content_hash"]:
            raise SourceManifestValidationError("manifest content hash mismatch")
        try:
            sources.append(
                TrustedSource(
                    workspace_id=workspace_id,
                    generation_id=generation_id,
                    document_id=str(record["document_id"]),
                    document_version_id=str(record["document_version_id"]),
                    logical_document_id=str(record["logical_document_id"]),
                    chunk_id=chunk_id,
                    content=content,
                    citation_label=str(record["citation_label"]),
                )
            )
        except (TypeError, ValueError) as error:
            raise SourceManifestValidationError(
                "manifest record has invalid source identity"
            ) from error
    return tuple(sources)
