"""store upload metadata on document versions

Revision ID: 0004_document_version_upload_metadata
Revises: 0003_workspace_schema
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_document_version_upload_metadata"
down_revision = "0003_workspace_schema"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("document_versions", sa.Column("source_filename", sa.String(512), nullable=True))
    op.add_column("document_versions", sa.Column("mime_type", sa.String(255), nullable=True))
    op.add_column("document_versions", sa.Column("size_bytes", sa.Integer, nullable=True))


def downgrade():
    op.drop_column("document_versions", "size_bytes")
    op.drop_column("document_versions", "mime_type")
    op.drop_column("document_versions", "source_filename")
