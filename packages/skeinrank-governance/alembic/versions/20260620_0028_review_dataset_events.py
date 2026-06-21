"""add review dataset events

Revision ID: 20260620_0028
Revises: 20260530_0027
Create Date: 2026-06-20 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260620_0028"
down_revision: str | None = "20260530_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_review_dataset_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("dataset_status", sa.String(length=32), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=True),
        sa.Column("agent_run_id", sa.Integer(), nullable=True),
        sa.Column("candidate_observation_id", sa.Integer(), nullable=True),
        sa.Column("llm_review_id", sa.Integer(), nullable=True),
        sa.Column("proposal_attempt_id", sa.Integer(), nullable=True),
        sa.Column("governance_suggestion_id", sa.Integer(), nullable=True),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("binding_id", sa.Integer(), nullable=True),
        sa.Column("candidate_alias", sa.String(length=256), nullable=True),
        sa.Column("normalized_alias", sa.String(length=256), nullable=True),
        sa.Column("canonical_value", sa.String(length=256), nullable=True),
        sa.Column("normalized_canonical", sa.String(length=256), nullable=True),
        sa.Column("slot", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=128), nullable=True),
        sa.Column("input_pack_json", sa.JSON(), nullable=False),
        sa.Column("model_output_json", sa.JSON(), nullable=False),
        sa.Column("human_decision_json", sa.JSON(), nullable=False),
        sa.Column("final_payload_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("export_excluded", sa.Boolean(), nullable=False),
        sa.Column("export_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('model_judgment', 'proposal_attempt', 'human_review')",
            name="agent_review_dataset_event_type",
        ),
        sa.CheckConstraint(
            "dataset_status IN ('pending_review', 'reviewed', 'excluded')",
            name="agent_review_dataset_event_status",
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"], ["elasticsearch_bindings.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["candidate_observation_id"],
            ["agent_candidate_observations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["governance_suggestion_id"],
            ["governance_suggestions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["llm_review_id"], ["agent_llm_reviews.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["terminology_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["proposal_attempt_id"],
            ["agent_proposal_attempts.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_type",
            "llm_review_id",
            name="uq_agent_review_dataset_events_type_review",
        ),
        sa.UniqueConstraint(
            "event_type",
            "proposal_attempt_id",
            name="uq_agent_review_dataset_events_type_attempt",
        ),
    )
    op.create_index(
        "ix_agent_review_dataset_events_export",
        "agent_review_dataset_events",
        ["dataset_status", "export_excluded", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_agent_review_dataset_events_profile_created",
        "agent_review_dataset_events",
        ["profile_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_agent_review_dataset_events_run_status",
        "agent_review_dataset_events",
        ["agent_run_id", "dataset_status"],
        unique=False,
    )
    op.create_index(
        "ix_agent_review_dataset_events_suggestion",
        "agent_review_dataset_events",
        ["governance_suggestion_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_review_dataset_events_suggestion",
        table_name="agent_review_dataset_events",
    )
    op.drop_index(
        "ix_agent_review_dataset_events_run_status",
        table_name="agent_review_dataset_events",
    )
    op.drop_index(
        "ix_agent_review_dataset_events_profile_created",
        table_name="agent_review_dataset_events",
    )
    op.drop_index(
        "ix_agent_review_dataset_events_export",
        table_name="agent_review_dataset_events",
    )
    op.drop_table("agent_review_dataset_events")
