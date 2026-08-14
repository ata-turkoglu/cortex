"""Workspace-scoped, read-only graph explorer data."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.workspaces import WorkspaceContext
from ..graphrag.adapter import GraphRAGAdapter
from .workspaces import get_session

router = APIRouter(tags=["graph"])


class GraphNodeRead(BaseModel):
    id: str
    label: str
    description: str
    attributes: dict[str, str]


class GraphEdgeRead(BaseModel):
    id: str
    source: str
    target: str
    label: str | None = None


class GraphExplorerRead(BaseModel):
    state: str
    nodes: list[GraphNodeRead] = Field(default_factory=list)
    edges: list[GraphEdgeRead] = Field(default_factory=list)


@router.get("/workspaces/{workspace_id}/graph", response_model=GraphExplorerRead)
def graph_explorer(workspace_id: str, session: Session = Depends(get_session)):
    """Return a bounded visualization projection of canonical GraphRAG artifacts."""
    context = WorkspaceContext.load(session, workspace_id)
    adapter = GraphRAGAdapter(workspace_id, context.graph_root)
    entities = adapter.load_artifacts("entities")[:150]
    aliases: dict[str, str] = {}
    for entity in entities:
        canonical_id = entity.artifact_id
        aliases[canonical_id] = canonical_id
        for key in ("id", "human_readable_id", "title"):
            alias = entity.attributes.get(key)
            if alias:
                aliases.setdefault(alias, canonical_id)
    nodes = [
        GraphNodeRead(
            id=entity.artifact_id,
            label=entity.attributes.get("title") or entity.artifact_id,
            description=entity.text[:600],
            attributes=entity.attributes,
        )
        for entity in entities
    ]
    edges = []
    for relationship in adapter.load_artifacts("relationships"):
        source = aliases.get(relationship.attributes.get("source", ""))
        target = aliases.get(relationship.attributes.get("target", ""))
        if source and target:
            edges.append(
                GraphEdgeRead(
                    id=relationship.artifact_id,
                    source=source,
                    target=target,
                    label=relationship.attributes.get("description")
                    or relationship.attributes.get("relationship"),
                )
            )
        if len(edges) == 300:
            break
    return GraphExplorerRead(state=context.graphrag_state.state, nodes=nodes, edges=edges)
