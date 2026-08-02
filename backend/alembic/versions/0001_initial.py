"""initial Cortex schema placeholder
Revision ID: 0001_initial
"""

import sqlalchemy as sa

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "schema_metadata",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.String(255), nullable=False),
    )


def downgrade():
    op.drop_table("schema_metadata")
