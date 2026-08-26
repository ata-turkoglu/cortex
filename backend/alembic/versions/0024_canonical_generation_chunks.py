"""persist canonical manifest chunk accounting

Revision ID: 0024_canonical_generation_chunks
Revises: 0023_canonical_membership_surname
"""

import sqlalchemy as sa

from alembic import op

revision = "0024_canonical_generation_chunks"
down_revision = "0023_canonical_membership_surname"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "canonical_generation_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column(
            "generation_id",
            sa.String(36),
            sa.ForeignKey("knowledge_generations.id"),
            nullable=False,
        ),
        sa.Column("chunk_id", sa.String(36), sa.ForeignKey("chunks.id"), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("processed_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("workspace_id", "generation_id", "chunk_id"),
    )
    op.create_index(
        "ix_canonical_generation_chunks_status",
        "canonical_generation_chunks",
        ["workspace_id", "generation_id", "status"],
    )


def downgrade():
    op.drop_table("canonical_generation_chunks")
