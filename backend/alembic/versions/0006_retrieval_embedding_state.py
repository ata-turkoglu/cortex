"""add retrieval embedding preparation state

Revision ID: 0006_retrieval_embedding_state
Revises: 0005_document_metadata
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_retrieval_embedding_state"
down_revision = "0005_document_metadata"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("chunks", sa.Column("prepared_embedding_hash", sa.String(128)))


def downgrade():
    op.drop_column("chunks", "prepared_embedding_hash")
