"""add SQLite minimal canonical core authority

Revision ID: 0022_minimal_canonical_core
Revises: 0021_generation_source_manifest
"""

import sqlalchemy as sa

from alembic import op

revision = "0022_minimal_canonical_core"
down_revision = "0021_generation_source_manifest"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "canonical_entities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("preferred_name", sa.String(512), nullable=False),
        sa.Column("normalized_preferred_name", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.CheckConstraint("entity_type = 'person'", name="ck_canonical_entities_person"),
    )
    op.create_index(
        "ix_canonical_entities_workspace_identity",
        "canonical_entities",
        ["workspace_id", "entity_type", "normalized_preferred_name"],
    )
    op.create_table(
        "entity_mentions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column(
            "generation_id",
            sa.String(36),
            sa.ForeignKey("knowledge_generations.id"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("surface_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("document_version_id", sa.String(36), nullable=False),
        sa.Column("logical_document_id", sa.String(72)),
        sa.Column("chunk_id", sa.String(36), nullable=False),
        sa.Column("span_start", sa.Integer(), nullable=False),
        sa.Column("span_end", sa.Integer(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("source_text_hash", sa.String(64), nullable=False),
        sa.Column("extraction_type", sa.String(64), nullable=False),
        sa.Column("extractor_version", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "workspace_id",
            "generation_id",
            "chunk_id",
            "span_start",
            "span_end",
            "entity_type",
            "extraction_type",
        ),
    )
    op.create_index(
        "ix_entity_mentions_generation_name",
        "entity_mentions",
        ["workspace_id", "generation_id", "entity_type", "normalized_text"],
    )
    op.create_table(
        "identity_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("mention_id", sa.String(36), sa.ForeignKey("entity_mentions.id"), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("canonical_entity_id", sa.String(36), sa.ForeignKey("canonical_entities.id")),
        sa.Column("decision_basis_json", sa.Text(), nullable=False),
        sa.Column("candidate_entity_ids_json", sa.Text(), nullable=False),
        sa.Column("resolver_version", sa.String(128), nullable=False),
        sa.Column("policy_version", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("workspace_id", "mention_id"),
        sa.CheckConstraint(
            "decision IN ('NEW', 'LINK', 'UNRESOLVED')", name="ck_identity_decision_kind"
        ),
        sa.CheckConstraint(
            "(decision IN ('NEW','LINK') AND canonical_entity_id IS NOT NULL) OR "
            "(decision='UNRESOLVED' AND canonical_entity_id IS NULL)",
            name="ck_identity_decision_binding",
        ),
    )
    op.create_index(
        "ix_identity_decisions_workspace_entity",
        "identity_decisions",
        ["workspace_id", "canonical_entity_id"],
    )
    op.create_table(
        "canonical_properties",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("property_kind", sa.String(32), nullable=False),
        sa.Column("province", sa.String(255)),
        sa.Column("district", sa.String(255)),
        sa.Column("neighborhood", sa.String(255)),
        sa.Column("pafta", sa.String(128)),
        sa.Column("ada", sa.String(128)),
        sa.Column("parsel", sa.String(128)),
        sa.Column("independent_section", sa.String(128)),
        sa.Column("identity_key", sa.Text(), nullable=False),
        sa.Column("identity_strength", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("workspace_id", "identity_key"),
    )
    op.create_table(
        "ownership_assertions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column(
            "generation_id",
            sa.String(36),
            sa.ForeignKey("knowledge_generations.id"),
            nullable=False,
        ),
        sa.Column(
            "person_id", sa.String(36), sa.ForeignKey("canonical_entities.id"), nullable=False
        ),
        sa.Column(
            "property_id", sa.String(36), sa.ForeignKey("canonical_properties.id"), nullable=False
        ),
        sa.Column("relation_type", sa.String(64), nullable=False),
        sa.Column(
            "person_mention_id", sa.String(36), sa.ForeignKey("entity_mentions.id"), nullable=False
        ),
        sa.Column(
            "property_mention_id",
            sa.String(36),
            sa.ForeignKey("entity_mentions.id"),
            nullable=False,
        ),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("document_version_id", sa.String(36), nullable=False),
        sa.Column("logical_document_id", sa.String(72)),
        sa.Column("chunk_id", sa.String(36), nullable=False),
        sa.Column("span_start", sa.Integer(), nullable=False),
        sa.Column("span_end", sa.Integer(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("source_text_hash", sa.String(64), nullable=False),
        sa.Column("share_numerator", sa.Integer()),
        sa.Column("share_denominator", sa.Integer()),
        sa.Column("recorded_date", sa.String(32)),
        sa.Column("assertion_rule_version", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "workspace_id",
            "generation_id",
            "person_mention_id",
            "property_mention_id",
            "relation_type",
        ),
    )
    op.create_index(
        "ix_ownership_assertions_generation_people",
        "ownership_assertions",
        ["workspace_id", "generation_id", "person_id", "property_id"],
    )
    op.create_table(
        "generation_canonical_memberships",
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), primary_key=True),
        sa.Column(
            "generation_id",
            sa.String(36),
            sa.ForeignKey("knowledge_generations.id"),
            primary_key=True,
        ),
        sa.Column(
            "canonical_entity_id",
            sa.String(36),
            sa.ForeignKey("canonical_entities.id"),
            primary_key=True,
        ),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column(
            "membership_basis_mention_id",
            sa.String(36),
            sa.ForeignKey("entity_mentions.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("workspace_id", "generation_id", "membership_basis_mention_id"),
    )
    op.create_table(
        "canonical_generation_status",
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), primary_key=True),
        sa.Column(
            "generation_id",
            sa.String(36),
            sa.ForeignKey("knowledge_generations.id"),
            primary_key=True,
        ),
        sa.Column("projection_version", sa.String(32), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column("manifest_chunk_count", sa.Integer(), nullable=False),
        sa.Column("processed_chunk_count", sa.Integer(), nullable=False),
        sa.Column("mention_count", sa.Integer(), nullable=False),
        sa.Column("resolved_mention_count", sa.Integer(), nullable=False),
        sa.Column("unresolved_mention_count", sa.Integer(), nullable=False),
        sa.Column("safe_property_count", sa.Integer(), nullable=False),
        sa.Column("assertion_count", sa.Integer(), nullable=False),
        sa.Column("rejected_assertion_count", sa.Integer(), nullable=False),
        sa.Column("failed_chunk_count", sa.Integer(), nullable=False),
        sa.Column("projection_row_count", sa.Integer(), nullable=False),
        sa.Column("failure_reason_json", sa.Text()),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    for table in (
        "canonical_generation_status",
        "generation_canonical_memberships",
        "ownership_assertions",
        "canonical_properties",
        "identity_decisions",
        "entity_mentions",
        "canonical_entities",
    ):
        op.drop_table(table)
