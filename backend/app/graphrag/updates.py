"""Deferred GraphRAG update planning and transaction-safe execution stages."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from ..core.config import Settings, get_settings
from ..models import GraphRagState
from .adapter import GraphRAGAdapter
from .input import GraphRAGInputDocument, GraphRAGInputManifest, GraphRAGInputMaterializer


@dataclass(frozen=True)
class GraphUpdatePlan:
    action: Literal["none", "queue", "confirmation_required"]
    reason: str
    pending_document_count: int
    cost_warning: bool


@dataclass(frozen=True)
class GraphRAGBatchPlan:
    enabled: bool
    eligible_stages: tuple[str, ...]


@dataclass(frozen=True)
class DeferredGraphRAGUpdate:
    workspace_id: str
    graph_root: Path
    documents: tuple[GraphRAGInputDocument, ...]
    batch_plan: GraphRAGBatchPlan


@dataclass(frozen=True)
class DeferredGraphRAGResult:
    manifest: GraphRAGInputManifest
    graph_root: Path


def eligible_batch_plan(settings: Settings | None = None) -> GraphRAGBatchPlan:
    active_settings = settings or get_settings()
    return GraphRAGBatchPlan(
        enabled=active_settings.graphrag_use_batch_api,
        eligible_stages=(
            ("entity_extraction", "community_summarization")
            if active_settings.graphrag_use_batch_api
            else ()
        ),
    )


def register_pending_document(
    session: Session,
    workspace_id: str,
    *,
    settings: Settings | None = None,
    estimated_cost_usd: float = 0.0,
) -> GraphUpdatePlan:
    """Persist a deferred index candidate without starting expensive graph work."""
    active_settings = settings or get_settings()
    state = session.get(GraphRagState, workspace_id)
    if state is None:
        raise LookupError(f"missing GraphRAG state for workspace {workspace_id}")
    state.pending_document_count += 1
    state.updated_at = datetime.now(UTC)
    cost_warning = (
        active_settings.graphrag_cost_warning_usd > 0
        and estimated_cost_usd >= active_settings.graphrag_cost_warning_usd
    )
    if state.pending_document_count > active_settings.graphrag_max_documents_per_run:
        return GraphUpdatePlan(
            "confirmation_required",
            "maximum_documents_exceeded",
            state.pending_document_count,
            cost_warning,
        )
    if cost_warning:
        return GraphUpdatePlan(
            "confirmation_required",
            "cost_warning",
            state.pending_document_count,
            cost_warning,
        )
    if (
        active_settings.graphrag_update_mode == "threshold"
        and state.pending_document_count >= active_settings.graphrag_pending_document_threshold
    ):
        return GraphUpdatePlan("queue", "threshold_reached", state.pending_document_count, False)
    return GraphUpdatePlan(
        "none",
        "manual_update_required",
        state.pending_document_count,
        False,
    )


def prepare_deferred_update(
    session: Session,
    workspace_id: str,
    graph_root: Path,
    materializer: GraphRAGInputMaterializer,
    *,
    settings: Settings | None = None,
) -> DeferredGraphRAGUpdate:
    """Collect DB inputs and mark indexing before closing the transaction."""
    state = session.get(GraphRagState, workspace_id)
    if state is None:
        raise LookupError(f"missing GraphRAG state for workspace {workspace_id}")
    documents = materializer.collect(session, workspace_id)
    state.state = "indexing"
    state.updated_at = datetime.now(UTC)
    return DeferredGraphRAGUpdate(
        workspace_id,
        graph_root,
        documents,
        eligible_batch_plan(settings),
    )


def run_deferred_update(
    update: DeferredGraphRAGUpdate,
    materializer: GraphRAGInputMaterializer,
    adapter: GraphRAGAdapter,
    *,
    method: str = "standard",
) -> DeferredGraphRAGResult:
    """Run file/model work with no SQLAlchemy session or transaction open."""
    if adapter.workspace_id != update.workspace_id or adapter.graph_root != update.graph_root:
        raise ValueError("GraphRAG adapter does not match the deferred update workspace")
    manifest = materializer.write(update.documents, update.workspace_id, update.graph_root)
    if adapter.config_path is None:
        adapter.initialize()
    adapter.index(method)
    adapter.rebuild_networkx()
    return DeferredGraphRAGResult(manifest, update.graph_root)


def complete_deferred_update(session: Session, workspace_id: str) -> None:
    state = session.get(GraphRagState, workspace_id)
    if state is None:
        raise LookupError(f"missing GraphRAG state for workspace {workspace_id}")
    state.state = "ready"
    state.pending_document_count = 0
    state.updated_at = datetime.now(UTC)


def fail_deferred_update(session: Session, workspace_id: str) -> None:
    state = session.get(GraphRagState, workspace_id)
    if state is None:
        raise LookupError(f"missing GraphRAG state for workspace {workspace_id}")
    state.state = "stale"
    state.updated_at = datetime.now(UTC)
