"""allow re-upload after a document is soft-deleted

Revision ID: 0012_active_document_source_hash
Revises: 0011_graphrag_usage_details
"""

import sqlalchemy as sa

from alembic import op

revision = "0012_active_document_source_hash"
down_revision = "0011_graphrag_usage_details"
branch_labels = None
depends_on = None


def _document_versions_table(*, include_workspace_source_hash: bool) -> sa.Table:
    metadata = sa.MetaData()
    constraints: list[sa.Constraint] = [
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.UniqueConstraint("document_id", "version_number"),
    ]
    if include_workspace_source_hash:
        constraints.append(sa.UniqueConstraint("workspace_id", "source_hash"))
    return sa.Table(
        "document_versions",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("source_hash", sa.String(128), nullable=False),
        sa.Column("normalized_content_hash", sa.String(128)),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("normalized_path", sa.Text()),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime()),
        sa.Column("source_filename", sa.String(512)),
        sa.Column("mime_type", sa.String(255)),
        sa.Column("size_bytes", sa.Integer()),
        *constraints,
    )


def _rebuild(*, include_workspace_source_hash: bool) -> None:
    with op.batch_alter_table(
        "document_versions",
        recreate="always",
        copy_from=_document_versions_table(
            include_workspace_source_hash=include_workspace_source_hash
        ),
    ):
        pass


def upgrade():
    _rebuild(include_workspace_source_hash=False)
    op.create_index(
        "ux_document_versions_workspace_active_source_hash",
        "document_versions",
        ["workspace_id", "source_hash"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
    )


def downgrade():
    op.drop_index("ux_document_versions_workspace_active_source_hash", "document_versions")
    _rebuild(include_workspace_source_hash=True)
