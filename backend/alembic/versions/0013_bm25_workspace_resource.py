"""register persistent BM25 paths for existing workspaces

Revision ID: 0013_bm25_workspace_resource
Revises: 0012_active_document_source_hash
"""

from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision = "0013_bm25_workspace_resource"
down_revision = "0012_active_document_source_hash"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    workspaces = sa.table("workspaces", sa.column("id", sa.String()))
    resources = sa.table(
        "workspace_resources",
        sa.column("id", sa.String()),
        sa.column("workspace_id", sa.String()),
        sa.column("resource_type", sa.String()),
        sa.column("logical_name", sa.String()),
        sa.column("backend_name", sa.String()),
        sa.column("path", sa.Text()),
        sa.column("active", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
    )
    now = datetime.now(UTC)
    for workspace_id in bind.execute(sa.select(workspaces.c.id)).scalars():
        exists = bind.execute(
            sa.select(resources.c.id).where(
                resources.c.workspace_id == workspace_id,
                resources.c.resource_type == "bm25_chunks",
                resources.c.logical_name == "active",
            )
        ).scalar()
        if not exists:
            bind.execute(
                resources.insert().values(
                    id=str(uuid4()),
                    workspace_id=workspace_id,
                    resource_type="bm25_chunks",
                    logical_name="active",
                    backend_name=None,
                    path=f"workspaces/{workspace_id}/bm25",
                    active=True,
                    created_at=now,
                )
            )


def downgrade():
    op.execute(
        sa.text(
            "DELETE FROM workspace_resources "
            "WHERE resource_type = 'bm25_chunks' AND logical_name = 'active'"
        )
    )
