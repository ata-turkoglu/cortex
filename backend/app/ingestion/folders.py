from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Folder


def resolve_folder_path(session: Session, workspace_id: str, folder_path: str | None) -> str | None:
    if not folder_path:
        return None
    parts = [part for part in folder_path.replace("\\", "/").split("/") if part]
    if not parts or any(part in {".", ".."} or ".." in part for part in parts):
        raise ValueError("invalid folder path")
    parent_id = None
    now = datetime.now(timezone.utc)
    for name in parts:
        folder = session.scalar(
            select(Folder).where(
                Folder.workspace_id == workspace_id,
                Folder.parent_id == parent_id,
                Folder.name == name,
                Folder.deleted_at.is_(None),
            )
        )
        if folder is None:
            folder = Folder(
                id=str(uuid4()), workspace_id=workspace_id, parent_id=parent_id,
                name=name, created_at=now, updated_at=now,
            )
            session.add(folder)
            session.flush()
        parent_id = folder.id
    return parent_id
