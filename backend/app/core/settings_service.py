"""Persistent, global-only settings with a small runtime cache.

Secrets deliberately remain environment/credential-store owned and never enter this table.
"""
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import GlobalSettings, GraphRagState, WorkspaceIndexState
from .config import Settings, get_settings

INDEX_DEPENDENT = {
    "embedding_provider",
    "embedding_model",
    "chunk_token_limit",
    "chunk_overlap_tokens",
}
PERSISTED_FIELDS = {
    name for name in Settings.model_fields
    if name
    not in {
        "openai_api_key", "anthropic_api_key", "database_url", "redis_url", "qdrant_url",
        "ollama_base_url", "data_path", "environment",
    }
}


def public_values(settings: Settings | None = None) -> dict[str, object]:
    source = settings or get_settings()
    return {name: getattr(source, name) for name in sorted(PERSISTED_FIELDS)}


def load_runtime_settings(session: Session) -> dict[str, object]:
    row = session.get(GlobalSettings, "runtime")
    if not row:
        return public_values()
    values = json.loads(row.value_json)
    runtime = get_settings()
    for name, value in values.items():
        if name in PERSISTED_FIELDS:
            setattr(runtime, name, value)
    return public_values(runtime)


def save_settings(session: Session, patch: dict[str, object]) -> tuple[dict[str, object], bool]:
    invalid = set(patch) - PERSISTED_FIELDS
    if invalid:
        raise ValueError(f"settings cannot be persisted: {', '.join(sorted(invalid))}")
    runtime = get_settings()
    before = {name: getattr(runtime, name) for name in INDEX_DEPENDENT}
    for name, value in patch.items():
        setattr(runtime, name, value)
    values = public_values(runtime)
    row = session.get(GlobalSettings, "runtime")
    now = datetime.now(UTC)
    if row:
        row.value_json, row.updated_at = json.dumps(values), now
    else:
        session.add(GlobalSettings(key="runtime", value_json=json.dumps(values), updated_at=now))
    index_changed = any(before[name] != getattr(runtime, name) for name in INDEX_DEPENDENT)
    if index_changed:
        for state in session.scalars(select(WorkspaceIndexState)):
            state.dense_state = "reindex_required"
            state.sparse_state = "reindex_required"
            state.updated_at = now
        for state in session.scalars(select(GraphRagState)):
            state.state = "stale"
            state.updated_at = now
    return values, index_changed
