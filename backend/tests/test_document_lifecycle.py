from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.models import Base, Document, DocumentVersion, Workspace


def test_duplicate_source_hash_is_isolated_by_workspace():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    now = datetime.now(UTC)
    workspaces = [
        Workspace(
            id=str(uuid4()), slug="one", name="One", state="active", created_at=now, updated_at=now
        ),
        Workspace(
            id=str(uuid4()), slug="two", name="Two", state="active", created_at=now, updated_at=now
        ),
    ]
    session.add_all(workspaces)
    for workspace in workspaces:
        document = Document(
            id=str(uuid4()),
            workspace_id=workspace.id,
            title="a.txt",
            created_at=now,
            updated_at=now,
        )
        session.add(document)
        session.add(
            DocumentVersion(
                id=str(uuid4()),
                workspace_id=workspace.id,
                document_id=document.id,
                version_number=1,
                source_hash="a" * 64,
                source_path="a",
                source_filename="a.txt",
                size_bytes=1,
                state="uploaded",
                created_at=now,
            )
        )
    session.commit()
    assert session.query(DocumentVersion).count() == 2


def test_soft_deleted_source_hash_can_be_reuploaded_in_the_same_workspace():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    now = datetime.now(UTC)
    workspace = Workspace(
        id=str(uuid4()),
        slug="reupload",
        name="Reupload",
        state="active",
        created_at=now,
        updated_at=now,
    )
    deleted_document = Document(
        id=str(uuid4()),
        workspace_id=workspace.id,
        title="old.txt",
        created_at=now,
        updated_at=now,
        deleted_at=now,
    )
    deleted_version = DocumentVersion(
        id=str(uuid4()), workspace_id=workspace.id, document_id=deleted_document.id,
        version_number=1, source_hash="same-content", source_path="old", source_filename="old.txt",
        size_bytes=1, state="deleted", created_at=now, deleted_at=now,
    )
    active_document = Document(
        id=str(uuid4()), workspace_id=workspace.id, title="new.txt", created_at=now, updated_at=now
    )
    active_version = DocumentVersion(
        id=str(uuid4()), workspace_id=workspace.id, document_id=active_document.id,
        version_number=1, source_hash="same-content", source_path="new", source_filename="new.txt",
        size_bytes=1, state="uploaded", created_at=now,
    )
    session.add_all([workspace, deleted_document, deleted_version, active_document, active_version])
    session.commit()

    assert session.query(DocumentVersion).count() == 2


def test_changed_content_creates_a_new_version_for_the_same_document():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    now = datetime.now(UTC)
    workspace = Workspace(
        id=str(uuid4()),
        slug="versions",
        name="Versions",
        state="active",
        created_at=now,
        updated_at=now,
    )
    document = Document(
        id=str(uuid4()),
        workspace_id=workspace.id,
        title="notes.txt",
        content_hash="old",
        created_at=now,
        updated_at=now,
    )
    first = DocumentVersion(
        id=str(uuid4()),
        workspace_id=workspace.id,
        document_id=document.id,
        version_number=1,
        source_hash="old",
        source_path="old",
        source_filename="notes.txt",
        size_bytes=3,
        state="uploaded",
        created_at=now,
    )
    second = DocumentVersion(
        id=str(uuid4()),
        workspace_id=workspace.id,
        document_id=document.id,
        version_number=2,
        source_hash="new",
        source_path="new",
        source_filename="notes.txt",
        size_bytes=3,
        state="uploaded",
        created_at=now,
    )
    document.active_version_id = second.id
    document.content_hash = second.source_hash
    session.add_all([workspace, document, first, second])
    session.commit()
    assert (
        session.scalar(
            select(func.max(DocumentVersion.version_number)).where(
                DocumentVersion.document_id == document.id
            )
        )
        == 2
    )
    assert session.get(Document, document.id).active_version_id == second.id
