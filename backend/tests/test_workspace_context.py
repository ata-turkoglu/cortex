from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.workspaces import WorkspaceContext, WorkspaceNotFoundError
from app.models import GraphRagState, Workspace, WorkspaceIndexState, WorkspaceResource


def test_workspace_context_isolated_and_resolves_resources():
    engine = create_engine("sqlite:///:memory:")
    from app.models import Base

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    now = datetime.now(timezone.utc)
    first = Workspace(id=str(uuid4()), slug="first", name="First", state="active", created_at=now, updated_at=now)
    second = Workspace(id=str(uuid4()), slug="second", name="Second", state="active", created_at=now, updated_at=now)
    session.add_all([first, second])
    for workspace in (first, second):
        session.add(WorkspaceResource(id=str(uuid4()), workspace_id=workspace.id, resource_type="qdrant_chunks", logical_name="active", backend_name="cortex_chunks", active=True, created_at=now))
        session.add(WorkspaceResource(id=str(uuid4()), workspace_id=workspace.id, resource_type="graphrag_root", logical_name="active", path=f"workspaces/{workspace.id}/graphrag", active=True, created_at=now))
        session.add(WorkspaceIndexState(workspace_id=workspace.id, updated_at=now))
        session.add(GraphRagState(workspace_id=workspace.id, graph_root=f"workspaces/{workspace.id}/graphrag", updated_at=now))
    session.commit()
    context = WorkspaceContext.load(session, first.id)
    assert context.workspace.id == first.id
    assert context.resource_name("qdrant_chunks") == "cortex_chunks"
    assert context.graph_root.name == "graphrag"
    with pytest.raises(WorkspaceNotFoundError):
        WorkspaceContext.load(session, str(uuid4()))
    session.close()
