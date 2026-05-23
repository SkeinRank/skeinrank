"""Add binding policies.

Revision ID: 20260523_0021
Revises: 20260523_0020
Create Date: 2026-05-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260523_0021"
down_revision = "20260523_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "governance_binding_policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("binding_id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("preferred_slots", sa.JSON(), nullable=False),
        sa.Column("allowed_tags", sa.JSON(), nullable=False),
        sa.Column("deny_slots", sa.JSON(), nullable=False),
        sa.Column("context_rules", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("updated_by", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')",
            name="governance_binding_policy_status",
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"], ["elasticsearch_bindings.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["terminology_profiles.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "binding_id", name="uq_governance_binding_policies_binding_id"
        ),
    )
    op.create_index(
        "ix_governance_binding_policies_profile",
        "governance_binding_policies",
        ["profile_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_binding_policies_status",
        "governance_binding_policies",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_governance_binding_policies_status",
        table_name="governance_binding_policies",
    )
    op.drop_index(
        "ix_governance_binding_policies_profile",
        table_name="governance_binding_policies",
    )
    op.drop_table("governance_binding_policies")
