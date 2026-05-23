"""Add ambiguous alias candidates.

Revision ID: 20260523_0020
Revises: 20260523_0019
Create Date: 2026-05-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260523_0020"
down_revision = "20260523_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "governance_ambiguous_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("surface_value", sa.String(length=256), nullable=False),
        sa.Column("normalized_surface", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("reviewed_by", sa.String(length=128), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('open', 'resolved', 'ignored')",
            name="governance_ambiguous_alias_status",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["terminology_profiles.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "profile_id",
            "normalized_surface",
            name="uq_governance_ambiguous_aliases_profile_surface",
        ),
    )
    op.create_index(
        "ix_governance_ambiguous_aliases_profile_status",
        "governance_ambiguous_aliases",
        ["profile_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_governance_ambiguous_aliases_surface",
        "governance_ambiguous_aliases",
        ["normalized_surface"],
        unique=False,
    )

    op.create_table(
        "governance_ambiguous_alias_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ambiguous_alias_id", sa.Integer(), nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=True),
        sa.Column("canonical_value", sa.String(length=256), nullable=False),
        sa.Column("normalized_canonical", sa.String(length=256), nullable=False),
        sa.Column("slot", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('candidate', 'preferred', 'rejected')",
            name="governance_ambiguous_alias_candidate_status",
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'active_alias', 'suggestion', 'conflict', 'agent', 'import')",
            name="governance_ambiguous_alias_candidate_source",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="governance_ambiguous_alias_candidate_confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["ambiguous_alias_id"],
            ["governance_ambiguous_aliases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["term_id"], ["canonical_terms.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "ambiguous_alias_id",
            "normalized_canonical",
            "slot",
            name="uq_governance_ambiguous_alias_candidates_canonical_slot",
        ),
    )
    op.create_index(
        "ix_governance_ambiguous_alias_candidates_term",
        "governance_ambiguous_alias_candidates",
        ["term_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_ambiguous_alias_candidates_status",
        "governance_ambiguous_alias_candidates",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_governance_ambiguous_alias_candidates_status",
        table_name="governance_ambiguous_alias_candidates",
    )
    op.drop_index(
        "ix_governance_ambiguous_alias_candidates_term",
        table_name="governance_ambiguous_alias_candidates",
    )
    op.drop_table("governance_ambiguous_alias_candidates")
    op.drop_index(
        "ix_governance_ambiguous_aliases_surface",
        table_name="governance_ambiguous_aliases",
    )
    op.drop_index(
        "ix_governance_ambiguous_aliases_profile_status",
        table_name="governance_ambiguous_aliases",
    )
    op.drop_table("governance_ambiguous_aliases")
