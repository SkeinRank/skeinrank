"""Add enrichment job cancellation statuses.

Revision ID: 20260509_0014
Revises: 20260509_0013
Create Date: 2026-05-09
"""

from __future__ import annotations

from alembic import op

revision = "20260509_0014"
down_revision = "20260509_0013"
branch_labels = None
depends_on = None

OLD_STATUS_CHECK = "status IN ('queued', 'running', 'succeeded', 'failed')"
NEW_STATUS_CHECK = (
    "status IN ('queued', 'running', 'cancel_requested', 'cancelled', "
    "'succeeded', 'failed')"
)


def upgrade() -> None:
    with op.batch_alter_table("elasticsearch_enrichment_jobs") as batch_op:
        batch_op.drop_constraint(
            "elasticsearch_enrichment_job_status",
            type_="check",
        )
        batch_op.create_check_constraint(
            "elasticsearch_enrichment_job_status",
            NEW_STATUS_CHECK,
        )


def downgrade() -> None:
    op.execute(
        "UPDATE elasticsearch_enrichment_jobs "
        "SET status = 'failed' "
        "WHERE status IN ('cancel_requested', 'cancelled')"
    )
    with op.batch_alter_table("elasticsearch_enrichment_jobs") as batch_op:
        batch_op.drop_constraint(
            "elasticsearch_enrichment_job_status",
            type_="check",
        )
        batch_op.create_check_constraint(
            "elasticsearch_enrichment_job_status",
            OLD_STATUS_CHECK,
        )
