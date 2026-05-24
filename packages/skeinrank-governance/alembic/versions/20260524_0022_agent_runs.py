"""Add agent run registry.

Revision ID: 20260524_0022
Revises: 20260523_0021
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260524_0022"
down_revision = "20260523_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("agent_name", sa.String(length=128), nullable=False),
        sa.Column("agent_version", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("profile_name", sa.String(length=128), nullable=True),
        sa.Column("normalized_profile_name", sa.String(length=128), nullable=True),
        sa.Column("binding_id", sa.Integer(), nullable=True),
        sa.Column("openrouter_model", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=128), nullable=True),
        sa.Column("workflow_engine", sa.String(length=128), nullable=True),
        sa.Column("config_hash", sa.String(length=64), nullable=True),
        sa.Column("artifacts_uri", sa.Text(), nullable=True),
        sa.Column("report_uri", sa.Text(), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', "
            "'cancelled', 'needs_review')",
            name="agent_run_status",
        ),
        sa.CheckConstraint(
            "trigger_type IN ('manual', 'scheduled', 'api', 'worker', 'test')",
            name="agent_run_trigger_type",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["terminology_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"], ["elasticsearch_bindings.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("run_id", name="uq_agent_runs_run_id"),
    )
    op.create_index(
        "ix_agent_runs_status_created",
        "agent_runs",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_agent_runs_agent_created",
        "agent_runs",
        ["agent_name", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_agent_runs_profile_created",
        "agent_runs",
        ["profile_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_agent_runs_binding_created",
        "agent_runs",
        ["binding_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_runs_binding_created", table_name="agent_runs")
    op.drop_index("ix_agent_runs_profile_created", table_name="agent_runs")
    op.drop_index("ix_agent_runs_agent_created", table_name="agent_runs")
    op.drop_index("ix_agent_runs_status_created", table_name="agent_runs")
    op.drop_table("agent_runs")
