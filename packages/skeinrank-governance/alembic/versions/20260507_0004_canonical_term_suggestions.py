"""Add canonical term suggestions.

Revision ID: 20260507_0004
Revises: 20260506_0003
Create Date: 2026-05-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260507_0004"
down_revision = "20260506_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "governance_suggestions",
        sa.Column(
            "suggestion_type",
            sa.String(length=32),
            nullable=False,
            server_default="alias",
        ),
    )
    op.add_column(
        "governance_suggestions",
        sa.Column("term_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "governance_suggestions",
        sa.Column("description", sa.Text(), nullable=True),
    )

    with op.batch_alter_table("governance_suggestions") as batch_op:
        batch_op.alter_column(
            "alias_value",
            existing_type=sa.String(length=256),
            nullable=True,
        )
        batch_op.alter_column(
            "normalized_alias",
            existing_type=sa.String(length=256),
            nullable=True,
        )
        batch_op.create_foreign_key(
            op.f("fk_governance_suggestions_term_id_canonical_terms"),
            "canonical_terms",
            ["term_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_check_constraint(
            op.f("ck_governance_suggestions_governance_suggestion_type"),
            "suggestion_type IN ('alias', 'canonical_term')",
        )

    op.create_index(
        "ix_governance_suggestions_profile_type_status",
        "governance_suggestions",
        ["profile_id", "suggestion_type", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_governance_suggestions_profile_type_status",
        table_name="governance_suggestions",
    )
    op.execute("DELETE FROM governance_suggestions WHERE suggestion_type != 'alias'")

    with op.batch_alter_table("governance_suggestions") as batch_op:
        batch_op.drop_constraint(
            op.f("ck_governance_suggestions_governance_suggestion_type"),
            type_="check",
        )
        batch_op.drop_constraint(
            op.f("fk_governance_suggestions_term_id_canonical_terms"),
            type_="foreignkey",
        )
        batch_op.alter_column(
            "alias_value",
            existing_type=sa.String(length=256),
            nullable=False,
        )
        batch_op.alter_column(
            "normalized_alias",
            existing_type=sa.String(length=256),
            nullable=False,
        )
        batch_op.drop_column("description")
        batch_op.drop_column("term_id")
        batch_op.drop_column("suggestion_type")
