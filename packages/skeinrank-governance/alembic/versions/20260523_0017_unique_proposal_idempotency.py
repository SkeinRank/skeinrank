"""Make proposal idempotency keys unique per profile.

Revision ID: 20260523_0017
Revises: 20260523_0016
Create Date: 2026-05-23
"""

from __future__ import annotations

from alembic import op

revision = "20260523_0017"
down_revision = "20260523_0016"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_governance_suggestions_profile_idempotency"
TABLE_NAME = "governance_suggestions"


def upgrade() -> None:
    op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
    op.create_index(
        INDEX_NAME,
        TABLE_NAME,
        ["profile_id", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
    op.create_index(
        INDEX_NAME,
        TABLE_NAME,
        ["profile_id", "idempotency_key"],
        unique=False,
    )
