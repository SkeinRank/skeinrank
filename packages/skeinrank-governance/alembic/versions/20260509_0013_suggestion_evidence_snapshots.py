"""Add suggestion evidence snapshots.

Revision ID: 20260509_0013
Revises: 20260509_0012
Create Date: 2026-05-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260509_0013"
down_revision = "20260509_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("governance_suggestions") as batch_op:
        batch_op.add_column(sa.Column("evidence_snapshot", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column("evidence_checked_by", sa.String(length=128), nullable=True)
        )
        batch_op.add_column(
            sa.Column("evidence_checked_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("governance_suggestions") as batch_op:
        batch_op.drop_column("evidence_checked_at")
        batch_op.drop_column("evidence_checked_by")
        batch_op.drop_column("evidence_snapshot")
