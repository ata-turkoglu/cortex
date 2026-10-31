"""persist query-scoped canonical completeness

Revision ID: 0026_query_run_completeness
Revises: 0025_human_identity_curation
"""

import sqlalchemy as sa

from alembic import op

revision = "0026_query_run_completeness"
down_revision = "0025_human_identity_curation"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("query_runs", sa.Column("completeness_json", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("query_runs", "completeness_json")
