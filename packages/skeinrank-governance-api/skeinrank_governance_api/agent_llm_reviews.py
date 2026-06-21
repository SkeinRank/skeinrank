"""DB-backed agent LLM review and proposal attempt helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from skeinrank_governance.models import (
    AGENT_LLM_REVIEW_STATUSES,
    AGENT_PROPOSAL_ATTEMPT_STATUSES,
    AgentCandidateObservation,
    AgentLlmReview,
    AgentProposalAttempt,
    GovernanceSuggestion,
    normalize_value,
)
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from .agent_run_registry import get_agent_run_by_run_id
from .review_dataset_events import (
    record_llm_review_dataset_event,
    record_proposal_attempt_dataset_event,
)


class AgentLlmReviewError(ValueError):
    """Raised when an LLM review/proposal attempt command is invalid."""


def record_llm_review(
    session: Session,
    *,
    run_id: str,
    candidate_alias: str,
    candidate_observation_id: int | None = None,
    possible_canonical: str | None = None,
    slot: str | None = None,
    review_status: str = "needs_evidence",
    action: str | None = None,
    confidence: float = 0.0,
    model: str | None = None,
    prompt_version: str | None = None,
    response_id: str | None = None,
    prompt_hash: str | None = None,
    review_hash: str | None = None,
    usage: dict[str, Any] | None = None,
    judgment: dict[str, Any] | None = None,
    raw_response: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> AgentLlmReview:
    """Persist one LLM judgment for an agent candidate."""

    agent_run = get_agent_run_by_run_id(session, run_id)
    if agent_run is None:
        raise AgentLlmReviewError(f"Agent run not found: {run_id}")
    normalized_alias = normalize_value(candidate_alias)
    if not normalized_alias:
        raise AgentLlmReviewError("candidate_alias must not be empty.")
    observation = _resolve_candidate_observation(
        session,
        candidate_observation_id=candidate_observation_id,
        agent_run_id=agent_run.id,
    )
    if observation is not None:
        possible_canonical = possible_canonical or observation.possible_canonical
        slot = slot or observation.slot
    normalized_canonical = (
        normalize_value(possible_canonical) if possible_canonical else None
    )
    normalized_status = _validate_llm_review_status(review_status)
    usage_json = usage or {}
    judgment_json = judgment or {}
    raw_response_json = raw_response or {}
    stable_hash = review_hash or compute_llm_review_hash(
        run_id=agent_run.run_id,
        normalized_alias=normalized_alias,
        possible_canonical=normalized_canonical,
        review_status=normalized_status,
        action=action,
        confidence=confidence,
        model=model or agent_run.openrouter_model,
        response_id=response_id,
        judgment=judgment_json,
    )
    review = AgentLlmReview(
        agent_run=agent_run,
        candidate_observation=observation,
        run_id=agent_run.run_id,
        profile_id=agent_run.profile_id,
        binding_id=agent_run.binding_id,
        candidate_alias=candidate_alias.strip(),
        normalized_alias=normalized_alias,
        possible_canonical=possible_canonical.strip() if possible_canonical else None,
        normalized_canonical=normalized_canonical,
        slot=slot.strip().upper() if slot else None,
        review_status=normalized_status,
        action=action.strip() if action else None,
        confidence=confidence,
        model=model or agent_run.openrouter_model,
        prompt_version=prompt_version or agent_run.prompt_version,
        response_id=response_id,
        prompt_hash=prompt_hash,
        review_hash=stable_hash,
        usage_json=usage_json,
        judgment_json=judgment_json,
        raw_response_json=raw_response_json,
        error_message=error_message,
    )
    session.add(review)
    record_llm_review_dataset_event(session, review)
    return review


def list_llm_reviews(
    session: Session,
    *,
    run_id: str,
    review_status: str | None = None,
    candidate_alias: str | None = None,
    limit: int = 100,
) -> list[AgentLlmReview]:
    """List persisted LLM reviews for one run."""

    agent_run = get_agent_run_by_run_id(session, run_id)
    if agent_run is None:
        raise AgentLlmReviewError(f"Agent run not found: {run_id}")
    statement: Select[tuple[AgentLlmReview]] = select(AgentLlmReview).where(
        AgentLlmReview.agent_run_id == agent_run.id
    )
    if review_status is not None:
        statement = statement.where(
            AgentLlmReview.review_status == _validate_llm_review_status(review_status)
        )
    if candidate_alias:
        statement = statement.where(
            AgentLlmReview.normalized_alias == normalize_value(candidate_alias)
        )
    statement = statement.order_by(AgentLlmReview.created_at.desc()).limit(
        max(1, min(limit, 500))
    )
    return list(session.scalars(statement))


def record_proposal_attempt(
    session: Session,
    *,
    run_id: str,
    alias_value: str,
    candidate_observation_id: int | None = None,
    llm_review_id: int | None = None,
    governance_suggestion_id: int | None = None,
    canonical_value: str | None = None,
    slot: str | None = None,
    attempt_status: str = "validation_passed",
    validation_status: str | None = None,
    validation_category: str | None = None,
    confidence: float = 0.0,
    idempotency_key: str | None = None,
    submitted: bool = False,
    proposal_source_type: str = "agent",
    proposal_source_name: str | None = None,
    validation_response: dict[str, Any] | None = None,
    submission_response: dict[str, Any] | None = None,
    source_payload: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> AgentProposalAttempt:
    """Persist one proposal validation/submission attempt."""

    agent_run = get_agent_run_by_run_id(session, run_id)
    if agent_run is None:
        raise AgentLlmReviewError(f"Agent run not found: {run_id}")
    normalized_alias = normalize_value(alias_value)
    if not normalized_alias:
        raise AgentLlmReviewError("alias_value must not be empty.")
    observation = _resolve_candidate_observation(
        session,
        candidate_observation_id=candidate_observation_id,
        agent_run_id=agent_run.id,
    )
    llm_review = _resolve_llm_review(
        session,
        llm_review_id=llm_review_id,
        agent_run_id=agent_run.id,
    )
    suggestion = _resolve_governance_suggestion(
        session,
        governance_suggestion_id=governance_suggestion_id,
    )
    if observation is not None:
        canonical_value = canonical_value or observation.possible_canonical
        slot = slot or observation.slot
    if llm_review is not None:
        canonical_value = canonical_value or llm_review.possible_canonical
        slot = slot or llm_review.slot
        if observation is None:
            observation = llm_review.candidate_observation
    normalized_canonical = normalize_value(canonical_value) if canonical_value else None
    normalized_status = _validate_proposal_attempt_status(attempt_status)
    attempt = AgentProposalAttempt(
        agent_run=agent_run,
        candidate_observation=observation,
        llm_review=llm_review,
        governance_suggestion=suggestion,
        run_id=agent_run.run_id,
        profile_id=agent_run.profile_id,
        binding_id=agent_run.binding_id,
        alias_value=alias_value.strip(),
        normalized_alias=normalized_alias,
        canonical_value=canonical_value.strip() if canonical_value else None,
        normalized_canonical=normalized_canonical,
        slot=slot.strip().upper() if slot else None,
        attempt_status=normalized_status,
        validation_status=validation_status,
        validation_category=validation_category,
        confidence=confidence,
        idempotency_key=idempotency_key,
        submitted=submitted,
        proposal_source_type=proposal_source_type,
        proposal_source_name=proposal_source_name,
        validation_response_json=validation_response or {},
        submission_response_json=submission_response or {},
        source_payload_json=source_payload or {},
        error_message=error_message,
    )
    session.add(attempt)
    record_proposal_attempt_dataset_event(session, attempt)
    return attempt


def list_proposal_attempts(
    session: Session,
    *,
    run_id: str,
    attempt_status: str | None = None,
    alias_value: str | None = None,
    limit: int = 100,
) -> list[AgentProposalAttempt]:
    """List persisted proposal attempts for one run."""

    agent_run = get_agent_run_by_run_id(session, run_id)
    if agent_run is None:
        raise AgentLlmReviewError(f"Agent run not found: {run_id}")
    statement: Select[tuple[AgentProposalAttempt]] = select(AgentProposalAttempt).where(
        AgentProposalAttempt.agent_run_id == agent_run.id
    )
    if attempt_status is not None:
        statement = statement.where(
            AgentProposalAttempt.attempt_status
            == _validate_proposal_attempt_status(attempt_status)
        )
    if alias_value:
        statement = statement.where(
            AgentProposalAttempt.normalized_alias == normalize_value(alias_value)
        )
    statement = statement.order_by(AgentProposalAttempt.created_at.desc()).limit(
        max(1, min(limit, 500))
    )
    return list(session.scalars(statement))


def compute_llm_review_hash(
    *,
    run_id: str,
    normalized_alias: str,
    possible_canonical: str | None,
    review_status: str,
    action: str | None,
    confidence: float,
    model: str | None,
    response_id: str | None,
    judgment: dict[str, Any],
) -> str:
    """Return a stable review hash for run-scoped LLM idempotency."""

    payload = {
        "run_id": run_id,
        "alias": normalized_alias,
        "canonical": possible_canonical,
        "review_status": review_status,
        "action": action,
        "confidence": confidence,
        "model": model,
        "response_id": response_id,
        "judgment": judgment,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _resolve_candidate_observation(
    session: Session,
    *,
    candidate_observation_id: int | None,
    agent_run_id: int,
) -> AgentCandidateObservation | None:
    if candidate_observation_id is None:
        return None
    observation = session.get(AgentCandidateObservation, candidate_observation_id)
    if observation is None:
        raise AgentLlmReviewError(
            f"Candidate observation not found: {candidate_observation_id}"
        )
    if observation.agent_run_id != agent_run_id:
        raise AgentLlmReviewError(
            "Candidate observation belongs to a different agent run."
        )
    return observation


def _resolve_llm_review(
    session: Session,
    *,
    llm_review_id: int | None,
    agent_run_id: int,
) -> AgentLlmReview | None:
    if llm_review_id is None:
        return None
    review = session.get(AgentLlmReview, llm_review_id)
    if review is None:
        raise AgentLlmReviewError(f"LLM review not found: {llm_review_id}")
    if review.agent_run_id != agent_run_id:
        raise AgentLlmReviewError("LLM review belongs to a different agent run.")
    return review


def _resolve_governance_suggestion(
    session: Session,
    *,
    governance_suggestion_id: int | None,
) -> GovernanceSuggestion | None:
    if governance_suggestion_id is None:
        return None
    suggestion = session.get(GovernanceSuggestion, governance_suggestion_id)
    if suggestion is None:
        raise AgentLlmReviewError(
            f"Governance suggestion not found: {governance_suggestion_id}"
        )
    return suggestion


def _validate_llm_review_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized not in AGENT_LLM_REVIEW_STATUSES:
        raise AgentLlmReviewError(
            "Invalid LLM review status "
            f"{status!r}. Expected one of {list(AGENT_LLM_REVIEW_STATUSES)!r}."
        )
    return normalized


def _validate_proposal_attempt_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized not in AGENT_PROPOSAL_ATTEMPT_STATUSES:
        raise AgentLlmReviewError(
            "Invalid proposal attempt status "
            f"{status!r}. Expected one of "
            f"{list(AGENT_PROPOSAL_ATTEMPT_STATUSES)!r}."
        )
    return normalized
