from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.graphrag.adapter import GraphRAGAdapter
from app.graphrag.input import GraphRAGInputMaterializer
from app.graphrag.updates import (
    complete_deferred_update,
    fail_deferred_update,
    prepare_deferred_update,
    register_pending_document,
    run_deferred_update,
)
from app.models import Base, Document, DocumentVersion, GraphRagState, Workspace


def graph_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    now = datetime.now(UTC)
    workspace = Workspace(
        id=str(uuid4()),
        slug="graph-updates",
        name="Graph updates",
        state="active",
        created_at=now,
        updated_at=now,
    )
    session.add(workspace)
    session.add(
        GraphRagState(
            workspace_id=workspace.id,
            graph_root=f"workspaces/{workspace.id}/graphrag",
            updated_at=now,
        )
    )
    session.commit()
    return session, workspace.id


def test_manual_mode_is_the_safe_default_and_threshold_mode_queues():
    session, workspace_id = graph_session()
    manual = register_pending_document(session, workspace_id, settings=Settings())
    assert manual.action == "none"
    threshold_settings = Settings(
        graphrag_update_mode="threshold",
        graphrag_pending_document_threshold=2,
    )
    threshold = register_pending_document(session, workspace_id, settings=threshold_settings)
    assert threshold.action == "queue"


def test_graph_update_controls_require_confirmation_before_costly_work():
    session, workspace_id = graph_session()
    settings = Settings(graphrag_cost_warning_usd=1.0, graphrag_max_documents_per_run=1)
    cost_plan = register_pending_document(
        session, workspace_id, settings=settings, estimated_cost_usd=1.0
    )
    assert cost_plan.action == "confirmation_required"
    count_plan = register_pending_document(session, workspace_id, settings=settings)
    assert count_plan.reason == "maximum_documents_exceeded"


def test_deferred_update_materializes_then_runs_without_a_database_session(tmp_path):
    session, workspace_id = graph_session()
    now = datetime.now(UTC)
    source = tmp_path / "data" / "normalized" / "document.md"
    source.parent.mkdir(parents=True)
    source.write_text("# Ankara", encoding="utf-8")
    document = Document(
        id=str(uuid4()),
        workspace_id=workspace_id,
        title="Document",
        created_at=now,
        updated_at=now,
    )
    version = DocumentVersion(
        id="version-1",
        workspace_id=workspace_id,
        document_id=document.id,
        version_number=1,
        source_hash="source-hash",
        source_path="uploads/document.md",
        normalized_path="normalized/document.md",
        source_filename="document.md",
        size_bytes=1,
        state="ready",
        created_at=now,
    )
    session.add_all([document, version])
    session.commit()
    calls = []

    class Runner:
        def initialize(self, root):
            config = root / "settings.yaml"
            config.write_text("models: {}", encoding="utf-8")
            calls.append("initialize")
            return config

        def index(self, root, config, method):
            calls.append(method)

        def query(self, root, config, route, query):
            return "unused"

    graph_root = tmp_path / "graph"
    materializer = GraphRAGInputMaterializer(tmp_path / "data")
    update = prepare_deferred_update(
        session,
        workspace_id,
        graph_root,
        materializer,
        settings=Settings(graphrag_use_batch_api=True),
    )
    assert update.batch_plan.eligible_stages == ("entity_extraction", "community_summarization")
    result = run_deferred_update(
        update,
        materializer,
        GraphRAGAdapter(workspace_id, graph_root, runner=Runner()),
        method="fast",
    )
    assert result.manifest.document_version_ids == ("version-1",)
    assert (graph_root / "input" / "version-1.md").read_text(encoding="utf-8") == "# Ankara"
    assert calls == ["initialize", "fast"]
    complete_deferred_update(session, workspace_id)
    assert session.get(GraphRagState, workspace_id).state == "ready"
    assert session.get(GraphRagState, workspace_id).pending_document_count == 0
    fail_deferred_update(session, workspace_id)
    assert session.get(GraphRagState, workspace_id).state == "stale"
