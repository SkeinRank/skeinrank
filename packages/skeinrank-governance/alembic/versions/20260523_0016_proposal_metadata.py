"""Add proposal metadata to governance suggestions.

Revision ID: 20260523_0016
Revises: 20260509_0015
Create Date: 2026-05-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260523_0016"
down_revision = "20260509_0015"
branch_labels = None
depends_on = None

PROPOSAL_SOURCE_TYPES = ("human", "agent", "cli", "api", "job", "import")


def upgrade() -> None:
    with op.batch_alter_table("governance_suggestions") as batch_op:
        batch_op.add_column(sa.Column("binding_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "proposal_source_type",
                sa.String(length=32),
                nullable=False,
                server_default="human",
            )
        )
        batch_op.add_column(
            sa.Column("proposal_source_name", sa.String(length=128), nullable=True)
        )
        batch_op.add_column(
            sa.Column("idempotency_key", sa.String(length=128), nullable=True)
        )
        batch_op.add_column(sa.Column("source_payload_json", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column("validation_summary_json", sa.JSON(), nullable=True)
        )
        batch_op.create_foreign_key(
            op.f("fk_governance_suggestions_binding_id_elasticsearch_bindings"),
            "elasticsearch_bindings",
            ["binding_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_check_constraint(
            op.f(
                "ck_governance_suggestions_governance_suggestion_proposal_source_type"
            ),
            f"proposal_source_type IN {PROPOSAL_SOURCE_TYPES!r}",
        )

    op.create_index(
        "ix_governance_suggestions_profile_source_type",
        "governance_suggestions",
        ["profile_id", "proposal_source_type"],
        unique=False,
    )
    op.create_index(
        "ix_governance_suggestions_profile_binding_status",
        "governance_suggestions",
        ["profile_id", "binding_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_governance_suggestions_profile_idempotency",
        "governance_suggestions",
        ["profile_id", "idempotency_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_governance_suggestions_profile_idempotency",
        table_name="governance_suggestions",
    )
    op.drop_index(
        "ix_governance_suggestions_profile_binding_status",
        table_name="governance_suggestions",
    )
    op.drop_index(
        "ix_governance_suggestions_profile_source_type",
        table_name="governance_suggestions",
    )

    with op.batch_alter_table("governance_suggestions") as batch_op:
        batch_op.drop_constraint(
            op.f(
                "ck_governance_suggestions_governance_suggestion_proposal_source_type"
            ),
            type_="check",
        )
        batch_op.drop_constraint(
            op.f("fk_governance_suggestions_binding_id_elasticsearch_bindings"),
            type_="foreignkey",
        )
        batch_op.drop_column("validation_summary_json")
        batch_op.drop_column("source_payload_json")
        batch_op.drop_column("idempotency_key")
        batch_op.drop_column("proposal_source_name")
        batch_op.drop_column("proposal_source_type")
        batch_op.drop_column("binding_id")
