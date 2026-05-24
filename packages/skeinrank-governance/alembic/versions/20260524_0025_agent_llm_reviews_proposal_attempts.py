"""Add agent LLM reviews and proposal attempts.

Revision ID: 20260524_0025
Revises: 20260524_0024
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260524_0025"
down_revision = "20260524_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_llm_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_run_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("candidate_observation_id", sa.Integer(), nullable=True),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("binding_id", sa.Integer(), nullable=True),
        sa.Column("candidate_alias", sa.String(length=256), nullable=False),
        sa.Column("normalized_alias", sa.String(length=256), nullable=False),
        sa.Column("possible_canonical", sa.String(length=256), nullable=True),
        sa.Column("normalized_canonical", sa.String(length=256), nullable=True),
        sa.Column("slot", sa.String(length=64), nullable=True),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=128), nullable=True),
        sa.Column("response_id", sa.String(length=256), nullable=True),
        sa.Column("prompt_hash", sa.String(length=64), nullable=True),
        sa.Column("review_hash", sa.String(length=64), nullable=False),
        sa.Column("usage_json", sa.JSON(), nullable=False),
        sa.Column("judgment_json", sa.JSON(), nullable=False),
        sa.Column("raw_response_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "review_status IN ('proposed', 'rejected', 'needs_evidence', 'error')",
            name="agent_llm_review_status",
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["candidate_observation_id"],
            ["agent_candidate_observations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["terminology_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"], ["elasticsearch_bindings.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "agent_run_id",
            "normalized_alias",
            "review_hash",
            name="uq_agent_llm_reviews_run_alias_hash",
        ),
    )
    op.create_index(
        "ix_agent_llm_reviews_run_status",
        "agent_llm_reviews",
        ["agent_run_id", "review_status"],
        unique=False,
    )
    op.create_index(
        "ix_agent_llm_reviews_alias",
        "agent_llm_reviews",
        ["normalized_alias"],
        unique=False,
    )
    op.create_index(
        "ix_agent_llm_reviews_model_created",
        "agent_llm_reviews",
        ["model", "created_at"],
        unique=False,
    )

    op.create_table(
        "agent_proposal_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_run_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("candidate_observation_id", sa.Integer(), nullable=True),
        sa.Column("llm_review_id", sa.Integer(), nullable=True),
        sa.Column("governance_suggestion_id", sa.Integer(), nullable=True),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("binding_id", sa.Integer(), nullable=True),
        sa.Column("alias_value", sa.String(length=256), nullable=False),
        sa.Column("normalized_alias", sa.String(length=256), nullable=False),
        sa.Column("canonical_value", sa.String(length=256), nullable=True),
        sa.Column("normalized_canonical", sa.String(length=256), nullable=True),
        sa.Column("slot", sa.String(length=64), nullable=True),
        sa.Column("attempt_status", sa.String(length=64), nullable=False),
        sa.Column("validation_status", sa.String(length=64), nullable=True),
        sa.Column("validation_category", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=True),
        sa.Column("submitted", sa.Boolean(), nullable=False),
        sa.Column("proposal_source_type", sa.String(length=32), nullable=False),
        sa.Column("proposal_source_name", sa.String(length=128), nullable=True),
        sa.Column("validation_response_json", sa.JSON(), nullable=False),
        sa.Column("submission_response_json", sa.JSON(), nullable=False),
        sa.Column("source_payload_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempt_status IN ('validation_passed', 'validation_warning', "
            "'validation_blocked', 'submitted', 'created', "
            "'idempotent_existing_alias', 'manual_review_required', 'error')",
            name="agent_proposal_attempt_status",
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["candidate_observation_id"],
            ["agent_candidate_observations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["llm_review_id"], ["agent_llm_reviews.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["governance_suggestion_id"],
            ["governance_suggestions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["terminology_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"], ["elasticsearch_bindings.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "agent_run_id",
            "idempotency_key",
            name="uq_agent_proposal_attempts_run_idempotency",
        ),
    )
    op.create_index(
        "ix_agent_proposal_attempts_run_status",
        "agent_proposal_attempts",
        ["agent_run_id", "attempt_status"],
        unique=False,
    )
    op.create_index(
        "ix_agent_proposal_attempts_idempotency",
        "agent_proposal_attempts",
        ["idempotency_key"],
        unique=False,
    )
    op.create_index(
        "ix_agent_proposal_attempts_suggestion",
        "agent_proposal_attempts",
        ["governance_suggestion_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_proposal_attempts_suggestion",
        table_name="agent_proposal_attempts",
    )
    op.drop_index(
        "ix_agent_proposal_attempts_idempotency",
        table_name="agent_proposal_attempts",
    )
    op.drop_index(
        "ix_agent_proposal_attempts_run_status",
        table_name="agent_proposal_attempts",
    )
    op.drop_table("agent_proposal_attempts")
    op.drop_index("ix_agent_llm_reviews_model_created", table_name="agent_llm_reviews")
    op.drop_index("ix_agent_llm_reviews_alias", table_name="agent_llm_reviews")
    op.drop_index("ix_agent_llm_reviews_run_status", table_name="agent_llm_reviews")
    op.drop_table("agent_llm_reviews")
