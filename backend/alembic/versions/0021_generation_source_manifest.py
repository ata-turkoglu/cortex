"""add immutable generation source manifest identity

Revision ID: 0021_generation_source_manifest
Revises: 0020_query_v2_cutover
"""

import sqlalchemy as sa

from alembic import op

revision = "0021_generation_source_manifest"
down_revision = "0020_query_v2_cutover"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("knowledge_generations") as batch:
        batch.add_column(sa.Column("source_manifest_uri", sa.Text(), nullable=True))
        batch.add_column(sa.Column("source_manifest_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("source_chunk_count", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("knowledge_generations") as batch:
        batch.drop_column("source_chunk_count")
        batch.drop_column("source_manifest_hash")
        batch.drop_column("source_manifest_uri")
