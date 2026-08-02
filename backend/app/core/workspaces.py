from dataclasses import dataclass
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import GraphRagState, Workspace, WorkspaceIndexState, WorkspaceResource
from .config import get_settings


class WorkspaceNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class WorkspaceContext:
    workspace: Workspace
    resources: dict[tuple[str, str], WorkspaceResource]
    index_state: WorkspaceIndexState
    graphrag_state: GraphRagState

    @classmethod
    def load(cls, session: Session, workspace_id: str) -> "WorkspaceContext":
        workspace = session.scalar(
            select(Workspace).where(Workspace.id == workspace_id, Workspace.deleted_at.is_(None))
        )
        if not workspace:
            raise WorkspaceNotFoundError(workspace_id)
        resource_rows = session.scalars(
            select(WorkspaceResource).where(
                WorkspaceResource.workspace_id == workspace_id,
                WorkspaceResource.active.is_(True),
            )
        )
        resources = {(row.resource_type, row.logical_name): row for row in resource_rows}
        index_state = session.get(WorkspaceIndexState, workspace_id)
        graphrag_state = session.get(GraphRagState, workspace_id)
        if not index_state or not graphrag_state:
            raise RuntimeError("workspace state is incomplete")
        return cls(workspace, resources, index_state, graphrag_state)

    def resource_name(self, resource_type: str, logical_name: str = "active") -> str:
        value = self.resources.get((resource_type, logical_name))
        if not value or not value.backend_name:
            raise KeyError(resource_type)
        return value.backend_name

    def resource_path(self, resource_type: str, logical_name: str = "active") -> Path:
        value = self.resources.get((resource_type, logical_name))
        if not value or not value.path:
            raise KeyError(resource_type)
        root = get_settings().data_path.resolve()
        stored_path = Path(value.path)
        candidate = (root / stored_path).resolve() if not stored_path.is_absolute() else stored_path.resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("path escapes data root")
        return candidate

    @property
    def graph_root(self) -> Path:
        return self.resource_path("graphrag_root")

    @property
    def cache_path(self) -> Path:
        return self.resource_path("cache")
