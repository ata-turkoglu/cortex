"""allow unknown GraphRAG usage fields and store query aggregates

Revision ID: 0011_graphrag_usage_details
Revises: 0010_logical_documents
"""

import sqlalchemy as sa

from alembic import op

revision = "0011_graphrag_usage_details"
down_revision = "0010_logical_documents"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("graphrag_stage_reports") as batch:
        batch.alter_column("input_tokens", existing_type=sa.Integer(), nullable=True)
        batch.alter_column("output_tokens", existing_type=sa.Integer(), nullable=True)
        batch.alter_column("estimated_cost_usd", existing_type=sa.Float(), nullable=True)
        batch.add_column(sa.Column("request_count", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("duration_ms", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("query_run_id", sa.String(36), nullable=True))


def downgrade():
    with op.batch_alter_table("graphrag_stage_reports") as batch:
        batch.drop_column("query_run_id")
        batch.drop_column("duration_ms")
        batch.drop_column("request_count")
        batch.alter_column("estimated_cost_usd", existing_type=sa.Float(), nullable=False)
        batch.alter_column("output_tokens", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("input_tokens", existing_type=sa.Integer(), nullable=False)
