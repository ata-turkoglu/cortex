"""add durable Query V2 conversation contexts

Revision ID: 0018_conversation_contexts
Revises: 0017_knowledge_reindex_run_context
"""

import sqlalchemy as sa

from alembic import op

revision = "0018_conversation_contexts"
down_revision = "0017_knowledge_reindex_run_context"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "conversation_contexts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("state_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "conversation_id"),
    )
    op.create_index(
        "ix_conversation_contexts_workspace_updated",
        "conversation_contexts",
        ["workspace_id", "updated_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_conversation_contexts_workspace_updated", table_name="conversation_contexts")
    op.drop_table("conversation_contexts")
