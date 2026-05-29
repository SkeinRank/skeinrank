"""Add context triggers to term aliases.

Revision ID: 20260530_0027
Revises: 20260529_0026
Create Date: 2026-05-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260530_0027"
down_revision = "20260529_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("term_aliases") as batch_op:
        batch_op.add_column(sa.Column("context_triggers", sa.JSON(), nullable=True))
    op.execute(
        "UPDATE term_aliases SET context_triggers = '[]' WHERE context_triggers IS NULL"
    )
    with op.batch_alter_table("term_aliases") as batch_op:
        batch_op.alter_column("context_triggers", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("term_aliases") as batch_op:
        batch_op.drop_column("context_triggers")
