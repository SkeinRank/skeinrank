"""Add user account status controls.

Revision ID: 20260509_0012
Revises: 20260509_0011
Create Date: 2026-05-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260509_0012"
down_revision = "20260509_0011"
branch_labels = None
depends_on = None


USER_STATUS_CHECK = "status IN ('active', 'suspended', 'deactivated')"


def upgrade() -> None:
    with op.batch_alter_table("governance_users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default="active",
            )
        )
        batch_op.create_check_constraint(
            "ck_governance_users_governance_user_status",
            USER_STATUS_CHECK,
        )
        batch_op.create_index("ix_governance_users_status", ["status"], unique=False)

    governance_users = sa.table(
        "governance_users",
        sa.column("status", sa.String(length=32)),
        sa.column("is_active", sa.Boolean()),
    )
    op.execute(
        governance_users.update()
        .where(governance_users.c.is_active.is_(False))
        .values(status="suspended")
    )


def downgrade() -> None:
    with op.batch_alter_table("governance_users") as batch_op:
        batch_op.drop_index("ix_governance_users_status")
        batch_op.drop_constraint(
            "ck_governance_users_governance_user_status",
            type_="check",
        )
        batch_op.drop_column("status")
