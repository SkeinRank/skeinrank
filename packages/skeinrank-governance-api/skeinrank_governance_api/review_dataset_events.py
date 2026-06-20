"""DB-backed review dataset events and JSONL export helpers.

The governance database is the source of truth. JSONL is a portable export
format for later evaluation or fine-tuning workflows.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from skeinrank_governance.models import (
    AGENT_REVIEW_DATASET_EVENT_STATUSES,
    AGENT_REVIEW_DATASET_EVENT_TYPES,
    AgentCandidateObservation,
    AgentLlmReview,
    AgentProposalAttempt,
    AgentReviewDatasetEvent,
    GovernanceSuggestion,
)
from sqlalchemy import Select, select
from sqlalchemy.orm import Session


class ReviewDatasetEventError(ValueError):
    """Raised when a review dataset event command is invalid."""


def record_llm_review_dataset_event(
    session: Session,
    review: AgentLlmReview,
) -> AgentReviewDatasetEvent:
    """Persist or return the dataset event for one model judgment."""

    existing = _existing_event(
        session,
        event_type="model_judgment",
        llm_review_id=review.id,
        fallback_review=review,
    )
    if existing is not None:
        return existing
    observation = review.candidate_observation
    event = AgentReviewDatasetEvent(
        event_type="model_judgment",
        dataset_status="pending_review",
        agent_run=review.agent_run,
        run_id=review.run_id,
        candidate_observation=observation,
        llm_review=review,
        profile_id=review.profile_id,
        binding_id=review.binding_id,
        candidate_alias=review.candidate_alias,
        canonical_value=review.possible_canonical,
        slot=review.slot,
        model=review.model,
        prompt_version=review.prompt_version,
        input_pack_json=_input_pack_from_observation(observation),
        model_output_json=_model_output_from_review(review),
        final_payload_json={},
        metadata_json={
            "schema_version": "skeinrank.review_dataset_event.v1",
            "source": "agent_llm_review",
            "review_status": review.review_status,
            "action": review.action,
            "confidence": review.confidence,
            "response_id": review.response_id,
            "prompt_hash": review.prompt_hash,
            "review_hash": review.review_hash,
        },
    )
    session.add(event)
    return event


def record_proposal_attempt_dataset_event(
    session: Session,
    attempt: AgentProposalAttempt,
) -> AgentReviewDatasetEvent:
    """Persist or return the dataset event for one proposal attempt."""

    existing = _existing_event(
        session,
        event_type="proposal_attempt",
        proposal_attempt_id=attempt.id,
        fallback_attempt=attempt,
    )
    if existing is not None:
        return existing
    observation = attempt.candidate_observation
    review = attempt.llm_review
    event = AgentReviewDatasetEvent(
        event_type="proposal_attempt",
        dataset_status="pending_review",
        agent_run=attempt.agent_run,
        run_id=attempt.run_id,
        candidate_observation=observation,
        llm_review=review,
        proposal_attempt=attempt,
        governance_suggestion=attempt.governance_suggestion,
        profile_id=attempt.profile_id,
        binding_id=attempt.binding_id,
        candidate_alias=attempt.alias_value,
        canonical_value=attempt.canonical_value,
        slot=attempt.slot,
        model=(
            review.model if review is not None else attempt.agent_run.openrouter_model
        ),
        prompt_version=(
            review.prompt_version
            if review is not None
            else attempt.agent_run.prompt_version
        ),
        input_pack_json=_input_pack_from_observation(observation),
        model_output_json=_model_output_from_review(review),
        final_payload_json=_final_payload_from_attempt(attempt),
        metadata_json={
            "schema_version": "skeinrank.review_dataset_event.v1",
            "source": "agent_proposal_attempt",
            "attempt_status": attempt.attempt_status,
            "validation_status": attempt.validation_status,
            "validation_category": attempt.validation_category,
            "submitted": attempt.submitted,
            "idempotency_key": attempt.idempotency_key,
            "proposal_source_type": attempt.proposal_source_type,
            "proposal_source_name": attempt.proposal_source_name,
        },
    )
    session.add(event)
    return event


def update_review_dataset_events_for_suggestion(
    session: Session,
    suggestion: GovernanceSuggestion,
    *,
    decision: str,
    reviewer: str,
    review_comment: str | None = None,
) -> list[AgentReviewDatasetEvent]:
    """Attach human review labels to proposal-attempt dataset events."""

    normalized_decision = decision.strip().lower()
    human_decision = {
        "schema_version": "skeinrank.review_dataset_human_decision.v1",
        "decision": normalized_decision,
        "reviewer": reviewer,
        "review_comment": review_comment,
        "suggestion_id": suggestion.id,
        "suggestion_status": suggestion.status,
    }
    final_payload = _final_payload_from_suggestion(suggestion)
    attempts = list(
        session.scalars(
            select(AgentProposalAttempt).where(
                AgentProposalAttempt.governance_suggestion_id == suggestion.id
            )
        )
    )
    updated: list[AgentReviewDatasetEvent] = []
    for attempt in attempts:
        event = _existing_event(
            session,
            event_type="proposal_attempt",
            proposal_attempt_id=attempt.id,
            fallback_attempt=attempt,
        )
        if event is None:
            event = record_proposal_attempt_dataset_event(session, attempt)
        event.dataset_status = "reviewed"
        event.governance_suggestion = suggestion
        event.human_decision_json = human_decision
        event.final_payload_json = final_payload or event.final_payload_json or {}
        event.metadata_json = {
            **(event.metadata_json or {}),
            "human_review_attached": True,
        }
        updated.append(event)
    if updated:
        return updated

    if suggestion.proposal_source_type == "agent":
        event = AgentReviewDatasetEvent(
            event_type="human_review",
            dataset_status="reviewed",
            governance_suggestion=suggestion,
            profile_id=suggestion.profile_id,
            binding_id=suggestion.binding_id,
            candidate_alias=suggestion.alias_value or suggestion.canonical_value,
            canonical_value=suggestion.canonical_value,
            slot=suggestion.slot,
            input_pack_json={"source_payload": suggestion.source_payload_json or {}},
            model_output_json={},
            human_decision_json=human_decision,
            final_payload_json=final_payload,
            metadata_json={
                "schema_version": "skeinrank.review_dataset_event.v1",
                "source": "governance_suggestion_review",
                "proposal_source_type": suggestion.proposal_source_type,
                "proposal_source_name": suggestion.proposal_source_name,
                "idempotency_key": suggestion.idempotency_key,
            },
        )
        session.add(event)
        updated.append(event)
    return updated


def list_review_dataset_events(
    session: Session,
    *,
    run_id: str | None = None,
    profile_id: int | None = None,
    binding_id: int | None = None,
    event_type: str | None = None,
    dataset_status: str | None = None,
    include_export_excluded: bool = False,
    limit: int = 100,
) -> list[AgentReviewDatasetEvent]:
    """List review dataset events with bounded filters."""

    statement: Select[tuple[AgentReviewDatasetEvent]] = select(AgentReviewDatasetEvent)
    if run_id:
        statement = statement.where(AgentReviewDatasetEvent.run_id == run_id.strip())
    if profile_id is not None:
        statement = statement.where(AgentReviewDatasetEvent.profile_id == profile_id)
    if binding_id is not None:
        statement = statement.where(AgentReviewDatasetEvent.binding_id == binding_id)
    if event_type is not None:
        statement = statement.where(
            AgentReviewDatasetEvent.event_type == _validate_event_type(event_type)
        )
    if dataset_status is not None:
        statement = statement.where(
            AgentReviewDatasetEvent.dataset_status
            == _validate_dataset_status(dataset_status)
        )
    if not include_export_excluded:
        statement = statement.where(AgentReviewDatasetEvent.export_excluded.is_(False))
    statement = statement.order_by(
        AgentReviewDatasetEvent.created_at.asc(), AgentReviewDatasetEvent.id.asc()
    ).limit(max(1, min(limit, 5000)))
    return list(session.scalars(statement))


def export_review_dataset_jsonl(
    events: Iterable[AgentReviewDatasetEvent],
) -> str:
    """Serialize review dataset events as JSON Lines."""

    lines = [
        json.dumps(review_dataset_event_to_json(event), sort_keys=True, default=str)
        for event in events
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def review_dataset_event_to_json(event: AgentReviewDatasetEvent) -> dict[str, Any]:
    """Return the stable JSONL object for one dataset event."""

    return {
        "schema_version": "skeinrank.review_dataset_event.v1",
        "event_id": event.id,
        "event_type": event.event_type,
        "dataset_status": event.dataset_status,
        "run_id": event.run_id,
        "agent_run_id": event.agent_run_id,
        "candidate_observation_id": event.candidate_observation_id,
        "llm_review_id": event.llm_review_id,
        "proposal_attempt_id": event.proposal_attempt_id,
        "governance_suggestion_id": event.governance_suggestion_id,
        "profile_id": event.profile_id,
        "binding_id": event.binding_id,
        "candidate_alias": event.candidate_alias,
        "normalized_alias": event.normalized_alias,
        "canonical_value": event.canonical_value,
        "normalized_canonical": event.normalized_canonical,
        "slot": event.slot,
        "model": event.model,
        "prompt_version": event.prompt_version,
        "input": event.input_pack_json or {},
        "model_output": event.model_output_json or {},
        "human_decision": event.human_decision_json or {},
        "final_payload": event.final_payload_json or {},
        "metadata": event.metadata_json or {},
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "updated_at": event.updated_at.isoformat() if event.updated_at else None,
    }


def _existing_event(
    session: Session,
    *,
    event_type: str,
    llm_review_id: int | None = None,
    proposal_attempt_id: int | None = None,
    fallback_review: AgentLlmReview | None = None,
    fallback_attempt: AgentProposalAttempt | None = None,
) -> AgentReviewDatasetEvent | None:
    statement = select(AgentReviewDatasetEvent).where(
        AgentReviewDatasetEvent.event_type == event_type
    )
    if llm_review_id is not None:
        statement = statement.where(
            AgentReviewDatasetEvent.llm_review_id == llm_review_id
        )
    elif fallback_review is not None and fallback_review.id is not None:
        statement = statement.where(
            AgentReviewDatasetEvent.llm_review == fallback_review
        )
    elif proposal_attempt_id is not None:
        statement = statement.where(
            AgentReviewDatasetEvent.proposal_attempt_id == proposal_attempt_id
        )
    elif fallback_attempt is not None and fallback_attempt.id is not None:
        statement = statement.where(
            AgentReviewDatasetEvent.proposal_attempt == fallback_attempt
        )
    else:
        return None
    return session.scalar(statement)


def _input_pack_from_observation(
    observation: AgentCandidateObservation | None,
) -> dict[str, Any]:
    if observation is None:
        return {}
    return {
        "candidate_alias": observation.candidate_alias,
        "possible_canonical": observation.possible_canonical,
        "slot": observation.slot,
        "discovery_score": observation.discovery_score,
        "weighted_count": observation.weighted_count,
        "document_frequency": observation.document_frequency,
        "discovery_reasons": observation.discovery_reasons_json or [],
        "canonical_hint": observation.canonical_hint_json or {},
        "candidate_pack": observation.candidate_pack_json or {},
        "metadata": observation.metadata_json or {},
        "evidence_windows": [
            {
                "source_id": window.source_id,
                "source_type": window.source_type,
                "field": window.field,
                "start_char": window.start_char,
                "end_char": window.end_char,
                "text": window.text,
                "metadata": window.metadata_json or {},
            }
            for window in observation.evidence_windows
        ],
    }


def _model_output_from_review(review: AgentLlmReview | None) -> dict[str, Any]:
    if review is None:
        return {}
    return {
        "review_status": review.review_status,
        "action": review.action,
        "confidence": review.confidence,
        "usage": review.usage_json or {},
        "judgment": review.judgment_json or {},
        "raw_response": review.raw_response_json or {},
    }


def _final_payload_from_attempt(attempt: AgentProposalAttempt) -> dict[str, Any]:
    return {
        "alias_value": attempt.alias_value,
        "canonical_value": attempt.canonical_value,
        "slot": attempt.slot,
        "confidence": attempt.confidence,
        "validation_status": attempt.validation_status,
        "validation_category": attempt.validation_category,
        "validation_response": attempt.validation_response_json or {},
        "submission_response": attempt.submission_response_json or {},
        "source_payload": attempt.source_payload_json or {},
    }


def _final_payload_from_suggestion(suggestion: GovernanceSuggestion) -> dict[str, Any]:
    return {
        "suggestion_id": suggestion.id,
        "suggestion_type": suggestion.suggestion_type,
        "alias_value": suggestion.alias_value,
        "canonical_value": suggestion.canonical_value,
        "slot": suggestion.slot,
        "confidence": suggestion.confidence,
        "status": suggestion.status,
        "source_payload": suggestion.source_payload_json or {},
        "validation_summary": suggestion.validation_summary_json or {},
    }


def _validate_event_type(event_type: str) -> str:
    normalized = event_type.strip().lower()
    if normalized not in AGENT_REVIEW_DATASET_EVENT_TYPES:
        raise ReviewDatasetEventError(
            "Invalid review dataset event_type "
            f"{event_type!r}. Expected one of "
            f"{list(AGENT_REVIEW_DATASET_EVENT_TYPES)!r}."
        )
    return normalized


def _validate_dataset_status(dataset_status: str) -> str:
    normalized = dataset_status.strip().lower()
    if normalized not in AGENT_REVIEW_DATASET_EVENT_STATUSES:
        raise ReviewDatasetEventError(
            "Invalid review dataset status "
            f"{dataset_status!r}. Expected one of "
            f"{list(AGENT_REVIEW_DATASET_EVENT_STATUSES)!r}."
        )
    return normalized
