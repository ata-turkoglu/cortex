"""add auditable exact-mention human identity adjudication

Revision ID: 0025_human_identity_curation
Revises: 0024_canonical_generation_chunks
"""

import sqlalchemy as sa

from alembic import op

revision = "0025_human_identity_curation"
down_revision = "0024_canonical_generation_chunks"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "human_identity_curation_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("mention_id", sa.String(36), sa.ForeignKey("entity_mentions.id"), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("document_version_id", sa.String(36), nullable=False),
        sa.Column("logical_document_id", sa.String(72)),
        sa.Column("chunk_id", sa.String(36), nullable=False),
        sa.Column("span_start", sa.Integer(), nullable=False),
        sa.Column("span_end", sa.Integer(), nullable=False),
        sa.Column("source_text_hash", sa.String(64), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("canonical_entity_id", sa.String(36), sa.ForeignKey("canonical_entities.id")),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_reference_json", sa.Text(), nullable=False),
        sa.Column("previous_decision_id", sa.String(36), sa.ForeignKey("human_identity_curation_decisions.id")),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("action IN ('LINK_TO_EXISTING', 'KEEP_UNRESOLVED')", name="ck_human_identity_curation_action"),
        sa.CheckConstraint(
            "(action = 'LINK_TO_EXISTING' AND canonical_entity_id IS NOT NULL) OR "
            "(action = 'KEEP_UNRESOLVED' AND canonical_entity_id IS NULL)",
            name="ck_human_identity_curation_target",
        ),
    )
    op.create_index(
        "ix_human_identity_curation_exact_active",
        "human_identity_curation_decisions",
        ["workspace_id", "document_version_id", "chunk_id", "span_start", "span_end", "source_text_hash", "active"],
    )


def downgrade():
    op.drop_table("human_identity_curation_decisions")
