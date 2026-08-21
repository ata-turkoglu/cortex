"""add durable Query V2 sharp-cutover state

Revision ID: 0020_query_v2_cutover
Revises: 0019_research_composition_runs
"""

import sqlalchemy as sa

from alembic import op

revision = "0020_query_v2_cutover"
down_revision = "0019_research_composition_runs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "query_runtime_activations",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("runtime_version", sa.String(length=16), nullable=False),
        sa.Column("generation_id", sa.String(length=36), nullable=True),
        sa.Column("source_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("evaluation_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("curation_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("activated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["generation_id"], ["knowledge_generations.id"]),
        sa.PrimaryKeyConstraint("workspace_id"),
    )
    op.create_table(
        "query_cutover_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("generation_id", sa.String(length=36), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("report_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_query_cutover_workspace_created",
        "query_cutover_attempts",
        ["workspace_id", "created_at"],
    )


def downgrade():
    op.drop_index(
        "ix_query_cutover_workspace_created", table_name="query_cutover_attempts"
    )
    op.drop_table("query_cutover_attempts")
    op.drop_table("query_runtime_activations")
