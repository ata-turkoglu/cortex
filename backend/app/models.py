from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase): pass
class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
class WorkspaceResource(Base):
    __tablename__ = "workspace_resources"; __table_args__ = (UniqueConstraint("workspace_id","resource_type","logical_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    logical_name: Mapped[str] = mapped_column(String(128), nullable=False)
    backend_name: Mapped[str | None] = mapped_column(String(255)); path: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(nullable=False, default=True); created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
class WorkspaceIndexState(Base):
    __tablename__="workspace_index_states"
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), primary_key=True)
    dense_state: Mapped[str] = mapped_column(String(32), default="empty"); sparse_state: Mapped[str] = mapped_column(String(32), default="empty")
    embedding_config_hash: Mapped[str|None] = mapped_column(String(128)); indexed_at: Mapped[datetime|None] = mapped_column(DateTime); updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
class GraphRagState(Base):
    __tablename__="graphrag_states"
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), primary_key=True)
    state: Mapped[str] = mapped_column(String(32), default="not_indexed"); pending_document_count: Mapped[int] = mapped_column(Integer, default=0)
    graph_root: Mapped[str] = mapped_column(Text, nullable=False); updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
