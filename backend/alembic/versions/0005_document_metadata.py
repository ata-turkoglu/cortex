"""add document metadata ownership

Revision ID: 0005_document_metadata
Revises: 0004_document_version_upload_metadata
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_document_metadata"
down_revision = "0004_document_version_upload_metadata"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_metadata",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("document_version_id", sa.String(36), sa.ForeignKey("document_versions.id")),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value_json", sa.Text, nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("document_id", "key", "origin"),
    )
    op.create_index("ix_document_metadata_workspace_document", "document_metadata", ["workspace_id", "document_id"])


def downgrade():
    op.drop_index("ix_document_metadata_workspace_document", table_name="document_metadata")
    op.drop_table("document_metadata")
