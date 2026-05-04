"""Initial governance schema.

Revision ID: 20260503_0001
Revises: None
Create Date: 2026-05-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260503_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "terminology_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("normalized_name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_terminology_profiles")),
        sa.UniqueConstraint("name", name=op.f("uq_terminology_profiles_name")),
        sa.UniqueConstraint(
            "normalized_name",
            name=op.f("uq_terminology_profiles_normalized_name"),
        ),
    )
    op.create_table(
        "canonical_terms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("canonical_value", sa.String(length=256), nullable=False),
        sa.Column("normalized_value", sa.String(length=256), nullable=False),
        sa.Column("slot", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'deprecated', 'disabled')",
            name=op.f("ck_canonical_terms_canonical_term_status"),
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["terminology_profiles.id"],
            name=op.f("fk_canonical_terms_profile_id_terminology_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_canonical_terms")),
        sa.UniqueConstraint(
            "profile_id",
            "normalized_value",
            name="uq_canonical_terms_profile_normalized_value",
        ),
    )
    op.create_index(
        "ix_canonical_terms_profile_slot",
        "canonical_terms",
        ["profile_id", "slot"],
        unique=False,
    )
    op.create_table(
        "profile_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("artifact_path", sa.Text(), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name=op.f("ck_profile_snapshots_profile_snapshot_status"),
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["terminology_profiles.id"],
            name=op.f("fk_profile_snapshots_profile_id_terminology_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profile_snapshots")),
        sa.UniqueConstraint(
            "profile_id",
            "version",
            name="uq_profile_snapshots_profile_version",
        ),
    )
    op.create_table(
        "term_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=False),
        sa.Column("alias_value", sa.String(length=256), nullable=False),
        sa.Column("normalized_alias", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'deprecated', 'disabled', 'ambiguous', 'pending', 'rejected')",
            name=op.f("ck_term_aliases_term_alias_status"),
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name=op.f("ck_term_aliases_term_alias_confidence_range"),
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["terminology_profiles.id"],
            name=op.f("fk_term_aliases_profile_id_terminology_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["term_id"],
            ["canonical_terms.id"],
            name=op.f("fk_term_aliases_term_id_canonical_terms"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_term_aliases")),
        sa.UniqueConstraint(
            "profile_id",
            "normalized_alias",
            name="uq_term_aliases_profile_normalized_alias",
        ),
    )
    op.create_index(
        "ix_term_aliases_term_status",
        "term_aliases",
        ["term_id", "status"],
        unique=False,
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["terminology_profiles.id"],
            name=op.f("fk_audit_events_profile_id_terminology_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_audit_events"),
        ),
    )
    op.create_index(
        "ix_audit_events_profile_created",
        "audit_events",
        ["profile_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_profile_created", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_term_aliases_term_status", table_name="term_aliases")
    op.drop_table("term_aliases")
    op.drop_table("profile_snapshots")
    op.drop_index("ix_canonical_terms_profile_slot", table_name="canonical_terms")
    op.drop_table("canonical_terms")
    op.drop_table("terminology_profiles")
