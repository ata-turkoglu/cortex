"""add logical document boundaries for multi-document source files

Revision ID: 0010_logical_documents
Revises: 0009_chat_query
"""

import sqlalchemy as sa

from alembic import op

revision = "0010_logical_documents"
down_revision = "0009_chat_query"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "logical_documents",
        sa.Column("id", sa.String(72), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("source_document_id", sa.String(36), nullable=False),
        sa.Column("document_version_id", sa.String(36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("document_code", sa.String(128), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("document_type", sa.String(255), nullable=False),
        sa.Column("source_original", sa.String(512), nullable=False),
        sa.Column("page_start", sa.Integer()),
        sa.Column("page_end", sa.Integer()),
        sa.Column("normalized_content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"]),
        sa.UniqueConstraint("document_version_id", "ordinal"),
    )
    op.create_index(
        "ix_logical_documents_workspace_code",
        "logical_documents",
        ["workspace_id", "document_code"],
    )
    op.add_column("chunks", sa.Column("logical_document_id", sa.String(72)))
    op.create_index("ix_chunks_logical_document_id", "chunks", ["logical_document_id"])

    # Existing source-level rows become one legacy logical document so old imports remain usable.
    op.execute(
        """
        INSERT INTO logical_documents (
            id, workspace_id, source_document_id, document_version_id, ordinal,
            document_code, title, document_type, source_original,
            page_start, page_end, normalized_content, created_at, deleted_at
        )
        SELECT
            'legacy-' || dv.id, dv.workspace_id, d.id, dv.id, 0,
            d.title, d.title, COALESCE(dv.mime_type, 'document'), dv.source_filename,
            NULL, NULL, COALESCE((SELECT group_concat(c.content, char(10) || char(10))
                FROM chunks c WHERE c.document_version_id = dv.id), ''),
            dv.created_at, dv.deleted_at
        FROM document_versions dv
        JOIN documents d ON d.id = dv.document_id
        """
    )
    op.execute(
        """
        UPDATE chunks
        SET logical_document_id = 'legacy-' || document_version_id
        WHERE logical_document_id IS NULL
        """
    )


def downgrade():
    raise NotImplementedError(
        "Downgrade is intentionally unsupported for this data-bearing migration"
    )
