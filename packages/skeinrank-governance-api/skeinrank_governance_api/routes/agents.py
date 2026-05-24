"""Agent run registry endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from skeinrank_governance.models import (
    AgentCandidateObservation,
    AgentDocumentVisit,
    AgentEvidenceWindow,
    AgentLlmReview,
    AgentProposalAttempt,
    AgentRun,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..agent_candidate_observations import (
    AgentCandidateObservationError,
    list_candidate_observations,
    list_evidence_windows,
    record_candidate_observation,
)
from ..agent_document_visits import (
    AgentDocumentVisitError,
    list_document_visits,
    record_document_visit,
)
from ..agent_llm_reviews import (
    AgentLlmReviewError,
    list_llm_reviews,
    list_proposal_attempts,
    record_llm_review,
    record_proposal_attempt,
)
from ..agent_run_registry import (
    AgentRunRegistryError,
    create_agent_run,
    get_agent_run_by_run_id,
    list_agent_runs,
    update_agent_run,
)
from ..auth import AuthContext, require_roles, require_scopes
from ..dependencies import get_session
from ..schemas import (
    AgentCandidateObservationCreateRequest,
    AgentCandidateObservationResponse,
    AgentDocumentVisitCreateRequest,
    AgentDocumentVisitResponse,
    AgentEvidenceWindowResponse,
    AgentLlmReviewCreateRequest,
    AgentLlmReviewResponse,
    AgentProposalAttemptCreateRequest,
    AgentProposalAttemptResponse,
    AgentRunCreateRequest,
    AgentRunResponse,
    AgentRunUpdateRequest,
)

router = APIRouter(prefix="/v1/agents", tags=["agents"])


@router.post(
    "/runs",
    response_model=AgentRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_agent_run_endpoint(
    request: AgentRunCreateRequest,
    current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    _scope: AuthContext = Depends(require_scopes("agent:runs:write")),
    session: Session = Depends(get_session),
) -> AgentRunResponse:
    """Register one agent workflow run without executing the agent."""

    try:
        agent_run = create_agent_run(
            session,
            run_id=request.run_id,
            agent_name=request.agent_name,
            agent_version=request.agent_version,
            status=request.status,
            trigger_type=request.trigger_type,
            profile_name=request.profile_name,
            binding_id=request.binding_id,
            openrouter_model=request.openrouter_model,
            prompt_version=request.prompt_version,
            workflow_engine=request.workflow_engine,
            config_hash=request.config_hash,
            artifacts_uri=request.artifacts_uri,
            report_uri=request.report_uri,
            summary_json=request.summary,
            error_message=request.error_message,
            requested_by=request.requested_by or current_user.username,
        )
        session.commit()
        session.refresh(agent_run)
        return _agent_run_response(agent_run)
    except AgentRunRegistryError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Agent run already exists for this run_id.",
        ) from exc


@router.get("/runs", response_model=list[AgentRunResponse])
def list_agent_runs_endpoint(
    status_filter: str | None = Query(default=None, alias="status"),
    agent_name: str | None = None,
    profile_name: str | None = None,
    binding_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    _scope: AuthContext = Depends(require_scopes("agent:runs:read")),
    session: Session = Depends(get_session),
) -> list[AgentRunResponse]:
    """List registered agent runs."""

    try:
        runs = list_agent_runs(
            session,
            status=status_filter,
            agent_name=agent_name,
            profile_name=profile_name,
            binding_id=binding_id,
            limit=limit,
        )
    except AgentRunRegistryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return [_agent_run_response(agent_run) for agent_run in runs]


@router.get("/runs/{run_id}", response_model=AgentRunResponse)
def get_agent_run_endpoint(
    run_id: str,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    _scope: AuthContext = Depends(require_scopes("agent:runs:read")),
    session: Session = Depends(get_session),
) -> AgentRunResponse:
    """Return one registered agent run by stable run id."""

    agent_run = get_agent_run_by_run_id(session, run_id)
    if agent_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found"
        )
    return _agent_run_response(agent_run)


@router.patch("/runs/{run_id}", response_model=AgentRunResponse)
def update_agent_run_endpoint(
    run_id: str,
    request: AgentRunUpdateRequest,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    _scope: AuthContext = Depends(require_scopes("agent:runs:write")),
    session: Session = Depends(get_session),
) -> AgentRunResponse:
    """Update lifecycle metadata for one registered agent run."""

    agent_run = get_agent_run_by_run_id(session, run_id)
    if agent_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found"
        )
    try:
        update_agent_run(
            agent_run,
            status=request.status,
            artifacts_uri=request.artifacts_uri,
            report_uri=request.report_uri,
            summary_json=request.summary,
            error_message=request.error_message,
            started_at_set=request.mark_started,
            finished_at_set=request.mark_finished,
        )
        session.commit()
        session.refresh(agent_run)
        return _agent_run_response(agent_run)
    except AgentRunRegistryError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/runs/{run_id}/document-visits",
    response_model=AgentDocumentVisitResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_agent_document_visit_endpoint(
    run_id: str,
    request: AgentDocumentVisitCreateRequest,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    _scope: AuthContext = Depends(require_scopes("agent:tracking:write")),
    session: Session = Depends(get_session),
) -> AgentDocumentVisitResponse:
    """Record one source document visit for an agent run."""

    try:
        visit = record_document_visit(
            session,
            run_id=run_id,
            source_id=request.source_id,
            external_document_id=request.external_document_id,
            source_type=request.source_type,
            index_name=request.index_name,
            content_hash=request.content_hash,
            content=request.content,
            processing_context_hash=request.processing_context_hash,
            agent_version=request.agent_version,
            prompt_version=request.prompt_version,
            openrouter_model=request.openrouter_model,
            metadata_json=request.metadata,
            evidence_windows_found=request.evidence_windows_found,
            error_message=request.error_message,
            force_rescan=request.force_rescan,
        )
        session.commit()
        session.refresh(visit)
        return _agent_document_visit_response(visit)
    except AgentDocumentVisitError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document visit already exists for this run and source_id.",
        ) from exc


@router.get(
    "/runs/{run_id}/document-visits",
    response_model=list[AgentDocumentVisitResponse],
)
def list_agent_document_visits_endpoint(
    run_id: str,
    visit_status: str | None = Query(default=None, alias="status"),
    should_scan: bool | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    _scope: AuthContext = Depends(require_scopes("agent:tracking:read")),
    session: Session = Depends(get_session),
) -> list[AgentDocumentVisitResponse]:
    """List document visits recorded for one agent run."""

    try:
        visits = list_document_visits(
            session,
            run_id=run_id,
            visit_status=visit_status,
            should_scan=should_scan,
            limit=limit,
        )
    except AgentDocumentVisitError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return [_agent_document_visit_response(visit) for visit in visits]


@router.post(
    "/runs/{run_id}/candidate-observations",
    response_model=AgentCandidateObservationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_agent_candidate_observation_endpoint(
    run_id: str,
    request: AgentCandidateObservationCreateRequest,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    _scope: AuthContext = Depends(require_scopes("agent:tracking:write")),
    session: Session = Depends(get_session),
) -> AgentCandidateObservationResponse:
    """Record one candidate alias observation and its evidence windows."""

    try:
        observation = record_candidate_observation(
            session,
            run_id=run_id,
            candidate_alias=request.candidate_alias,
            document_visit_id=request.document_visit_id,
            possible_canonical=request.possible_canonical,
            slot=request.slot,
            observation_status=request.observation_status,
            discovery_score=request.discovery_score,
            weighted_count=request.weighted_count,
            document_frequency=request.document_frequency,
            discovery_reasons=request.discovery_reasons,
            canonical_hint=request.canonical_hint,
            candidate_pack=request.candidate_pack,
            metadata_json=request.metadata,
            evidence_windows=[
                window.model_dump() for window in request.evidence_windows
            ],
            error_message=request.error_message,
        )
        session.commit()
        session.refresh(observation)
        return _agent_candidate_observation_response(observation)
    except AgentCandidateObservationError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Candidate observation already exists for this run and alias.",
        ) from exc


@router.get(
    "/runs/{run_id}/candidate-observations",
    response_model=list[AgentCandidateObservationResponse],
)
def list_agent_candidate_observations_endpoint(
    run_id: str,
    observation_status: str | None = Query(default=None, alias="status"),
    candidate_alias: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    _scope: AuthContext = Depends(require_scopes("agent:tracking:read")),
    session: Session = Depends(get_session),
) -> list[AgentCandidateObservationResponse]:
    """List candidate observations recorded for one agent run."""

    try:
        observations = list_candidate_observations(
            session,
            run_id=run_id,
            observation_status=observation_status,
            candidate_alias=candidate_alias,
            limit=limit,
        )
    except AgentCandidateObservationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return [
        _agent_candidate_observation_response(observation)
        for observation in observations
    ]


@router.get(
    "/runs/{run_id}/evidence-windows",
    response_model=list[AgentEvidenceWindowResponse],
)
def list_agent_evidence_windows_endpoint(
    run_id: str,
    candidate_observation_id: int | None = None,
    source_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    _scope: AuthContext = Depends(require_scopes("agent:tracking:read")),
    session: Session = Depends(get_session),
) -> list[AgentEvidenceWindowResponse]:
    """List persisted evidence windows for one agent run."""

    try:
        windows = list_evidence_windows(
            session,
            run_id=run_id,
            candidate_observation_id=candidate_observation_id,
            source_id=source_id,
            limit=limit,
        )
    except AgentCandidateObservationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return [_agent_evidence_window_response(window) for window in windows]


@router.post(
    "/runs/{run_id}/llm-reviews",
    response_model=AgentLlmReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_agent_llm_review_endpoint(
    run_id: str,
    request: AgentLlmReviewCreateRequest,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    _scope: AuthContext = Depends(require_scopes("agent:tracking:write")),
    session: Session = Depends(get_session),
) -> AgentLlmReviewResponse:
    """Record one LLM review for an agent run."""

    try:
        review = record_llm_review(
            session,
            run_id=run_id,
            candidate_alias=request.candidate_alias,
            candidate_observation_id=request.candidate_observation_id,
            possible_canonical=request.possible_canonical,
            slot=request.slot,
            review_status=request.review_status,
            action=request.action,
            confidence=request.confidence,
            model=request.model,
            prompt_version=request.prompt_version,
            response_id=request.response_id,
            prompt_hash=request.prompt_hash,
            review_hash=request.review_hash,
            usage=request.usage,
            judgment=request.judgment,
            raw_response=request.raw_response,
            error_message=request.error_message,
        )
        session.commit()
        session.refresh(review)
        return _agent_llm_review_response(review)
    except AgentLlmReviewError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="LLM review already exists for this run, alias, and hash.",
        ) from exc


@router.get(
    "/runs/{run_id}/llm-reviews",
    response_model=list[AgentLlmReviewResponse],
)
def list_agent_llm_reviews_endpoint(
    run_id: str,
    review_status: str | None = Query(default=None, alias="status"),
    candidate_alias: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    _scope: AuthContext = Depends(require_scopes("agent:tracking:read")),
    session: Session = Depends(get_session),
) -> list[AgentLlmReviewResponse]:
    """List persisted LLM reviews for one agent run."""

    try:
        reviews = list_llm_reviews(
            session,
            run_id=run_id,
            review_status=review_status,
            candidate_alias=candidate_alias,
            limit=limit,
        )
    except AgentLlmReviewError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return [_agent_llm_review_response(review) for review in reviews]


@router.post(
    "/runs/{run_id}/proposal-attempts",
    response_model=AgentProposalAttemptResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_agent_proposal_attempt_endpoint(
    run_id: str,
    request: AgentProposalAttemptCreateRequest,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    _scope: AuthContext = Depends(require_scopes("agent:tracking:write")),
    session: Session = Depends(get_session),
) -> AgentProposalAttemptResponse:
    """Record one proposal validation/submission attempt for an agent run."""

    try:
        attempt = record_proposal_attempt(
            session,
            run_id=run_id,
            alias_value=request.alias_value,
            candidate_observation_id=request.candidate_observation_id,
            llm_review_id=request.llm_review_id,
            governance_suggestion_id=request.governance_suggestion_id,
            canonical_value=request.canonical_value,
            slot=request.slot,
            attempt_status=request.attempt_status,
            validation_status=request.validation_status,
            validation_category=request.validation_category,
            confidence=request.confidence,
            idempotency_key=request.idempotency_key,
            submitted=request.submitted,
            proposal_source_type=request.proposal_source_type,
            proposal_source_name=request.proposal_source_name,
            validation_response=request.validation_response,
            submission_response=request.submission_response,
            source_payload=request.source_payload,
            error_message=request.error_message,
        )
        session.commit()
        session.refresh(attempt)
        return _agent_proposal_attempt_response(attempt)
    except AgentLlmReviewError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Proposal attempt already exists for this run and idempotency key.",
        ) from exc


@router.get(
    "/runs/{run_id}/proposal-attempts",
    response_model=list[AgentProposalAttemptResponse],
)
def list_agent_proposal_attempts_endpoint(
    run_id: str,
    attempt_status: str | None = Query(default=None, alias="status"),
    alias_value: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    _scope: AuthContext = Depends(require_scopes("agent:tracking:read")),
    session: Session = Depends(get_session),
) -> list[AgentProposalAttemptResponse]:
    """List persisted proposal attempts for one agent run."""

    try:
        attempts = list_proposal_attempts(
            session,
            run_id=run_id,
            attempt_status=attempt_status,
            alias_value=alias_value,
            limit=limit,
        )
    except AgentLlmReviewError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return [_agent_proposal_attempt_response(attempt) for attempt in attempts]


def _agent_run_response(agent_run: AgentRun) -> AgentRunResponse:
    return AgentRunResponse(
        id=agent_run.id,
        run_id=agent_run.run_id,
        agent_name=agent_run.agent_name,
        agent_version=agent_run.agent_version,
        status=agent_run.status,
        trigger_type=agent_run.trigger_type,
        profile_name=agent_run.profile_name,
        normalized_profile_name=agent_run.normalized_profile_name,
        binding_id=agent_run.binding_id,
        openrouter_model=agent_run.openrouter_model,
        prompt_version=agent_run.prompt_version,
        workflow_engine=agent_run.workflow_engine,
        config_hash=agent_run.config_hash,
        artifacts_uri=agent_run.artifacts_uri,
        report_uri=agent_run.report_uri,
        summary=agent_run.summary_json or {},
        error_message=agent_run.error_message,
        requested_by=agent_run.requested_by,
        started_at=agent_run.started_at,
        finished_at=agent_run.finished_at,
        created_at=agent_run.created_at,
        updated_at=agent_run.updated_at,
    )


def _agent_document_visit_response(
    visit: AgentDocumentVisit,
) -> AgentDocumentVisitResponse:
    return AgentDocumentVisitResponse(
        id=visit.id,
        agent_run_id=visit.agent_run_id,
        run_id=visit.run_id,
        source_id=visit.source_id,
        external_document_id=visit.external_document_id,
        source_type=visit.source_type,
        index_name=visit.index_name,
        content_hash=visit.content_hash,
        processing_context_hash=visit.processing_context_hash,
        agent_name=visit.agent_name,
        agent_version=visit.agent_version,
        prompt_version=visit.prompt_version,
        openrouter_model=visit.openrouter_model,
        profile_name=visit.agent_run.profile_name if visit.agent_run else None,
        binding_id=visit.binding_id,
        visit_status=visit.visit_status,
        should_scan=visit.should_scan,
        evidence_windows_found=visit.evidence_windows_found,
        metadata=visit.metadata_json or {},
        error_message=visit.error_message,
        created_at=visit.created_at,
        updated_at=visit.updated_at,
    )


def _agent_candidate_observation_response(
    observation: AgentCandidateObservation,
) -> AgentCandidateObservationResponse:
    return AgentCandidateObservationResponse(
        id=observation.id,
        agent_run_id=observation.agent_run_id,
        run_id=observation.run_id,
        document_visit_id=observation.document_visit_id,
        candidate_alias=observation.candidate_alias,
        normalized_alias=observation.normalized_alias,
        possible_canonical=observation.possible_canonical,
        normalized_canonical=observation.normalized_canonical,
        slot=observation.slot,
        observation_status=observation.observation_status,
        discovery_score=observation.discovery_score,
        weighted_count=observation.weighted_count,
        document_frequency=observation.document_frequency,
        evidence_windows_found=observation.evidence_windows_found,
        discovery_reasons=observation.discovery_reasons_json or [],
        canonical_hint=observation.canonical_hint_json or {},
        candidate_pack=observation.candidate_pack_json or {},
        metadata=observation.metadata_json or {},
        error_message=observation.error_message,
        evidence_windows=[
            _agent_evidence_window_response(window)
            for window in observation.evidence_windows
        ],
        created_at=observation.created_at,
        updated_at=observation.updated_at,
    )


def _agent_evidence_window_response(
    window: AgentEvidenceWindow,
) -> AgentEvidenceWindowResponse:
    return AgentEvidenceWindowResponse(
        id=window.id,
        agent_run_id=window.agent_run_id,
        candidate_observation_id=window.candidate_observation_id,
        document_visit_id=window.document_visit_id,
        run_id=window.run_id,
        candidate_alias=window.candidate_alias,
        source_id=window.source_id,
        source_type=window.source_type,
        field=window.field,
        start_char=window.start_char,
        end_char=window.end_char,
        text=window.text,
        evidence_hash=window.evidence_hash,
        metadata=window.metadata_json or {},
        created_at=window.created_at,
        updated_at=window.updated_at,
    )


def _agent_llm_review_response(review: AgentLlmReview) -> AgentLlmReviewResponse:
    return AgentLlmReviewResponse(
        id=review.id,
        agent_run_id=review.agent_run_id,
        run_id=review.run_id,
        candidate_observation_id=review.candidate_observation_id,
        candidate_alias=review.candidate_alias,
        normalized_alias=review.normalized_alias,
        possible_canonical=review.possible_canonical,
        normalized_canonical=review.normalized_canonical,
        slot=review.slot,
        review_status=review.review_status,
        action=review.action,
        confidence=review.confidence,
        model=review.model,
        prompt_version=review.prompt_version,
        response_id=review.response_id,
        prompt_hash=review.prompt_hash,
        review_hash=review.review_hash,
        usage=review.usage_json or {},
        judgment=review.judgment_json or {},
        raw_response=review.raw_response_json or {},
        error_message=review.error_message,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


def _agent_proposal_attempt_response(
    attempt: AgentProposalAttempt,
) -> AgentProposalAttemptResponse:
    return AgentProposalAttemptResponse(
        id=attempt.id,
        agent_run_id=attempt.agent_run_id,
        run_id=attempt.run_id,
        candidate_observation_id=attempt.candidate_observation_id,
        llm_review_id=attempt.llm_review_id,
        governance_suggestion_id=attempt.governance_suggestion_id,
        alias_value=attempt.alias_value,
        normalized_alias=attempt.normalized_alias,
        canonical_value=attempt.canonical_value,
        normalized_canonical=attempt.normalized_canonical,
        slot=attempt.slot,
        attempt_status=attempt.attempt_status,
        validation_status=attempt.validation_status,
        validation_category=attempt.validation_category,
        confidence=attempt.confidence,
        idempotency_key=attempt.idempotency_key,
        submitted=attempt.submitted,
        proposal_source_type=attempt.proposal_source_type,
        proposal_source_name=attempt.proposal_source_name,
        validation_response=attempt.validation_response_json or {},
        submission_response=attempt.submission_response_json or {},
        source_payload=attempt.source_payload_json or {},
        error_message=attempt.error_message,
        created_at=attempt.created_at,
        updated_at=attempt.updated_at,
    )
