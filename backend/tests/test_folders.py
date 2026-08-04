from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ingestion.folders import resolve_folder_path
from app.models import Base, Workspace


def test_folder_path_is_created_within_its_workspace():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    now = datetime.now(UTC)
    workspace = Workspace(
        id=str(uuid4()),
        slug="folders",
        name="Folders",
        state="active",
        created_at=now,
        updated_at=now,
    )
    session.add(workspace)
    assert resolve_folder_path(session, workspace.id, "2026/Notlar")
    assert resolve_folder_path(session, workspace.id, "2026/Notlar")
    with pytest.raises(ValueError):
        resolve_folder_path(session, workspace.id, "../escape")
