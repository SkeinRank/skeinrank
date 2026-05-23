"""Agent-friendly REST tools for proposal and runtime workflows."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from skeinrank_governance.models import (
    PROPOSAL_SOURCE_TYPES,
    ElasticsearchBinding,
    GovernanceSuggestion,
    TerminologyProfile,
    normalize_profile_name,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..ambiguous_proposals import sync_ambiguous_alias_candidates_for_suggestion
from ..auth import AuthContext, require_roles
from ..dependencies import get_session
from ..observability.metrics import record_proposal_submission
from ..proposal_idempotency import (
    ProposalIdempotencyConflict,
    normalize_idempotency_key,
    resolve_idempotent_suggestion,
    resolve_idempotent_suggestion_from_validation_summary,
)
from ..proposal_quality import validation_status
from ..proposal_validation import build_proposal_validation_summary
from ..runtime_snapshots import binding_snapshot_status
from ..schemas import (
    AgentToolBindingContextResponse,
    AgentToolExplainQueryRequest,
    AgentToolSuggestAliasRequest,
    AgentToolSuggestAliasResponse,
    AgentToolValidateAliasRequest,
    AgentToolValidateAliasResponse,
    QueryPlanResponse,
    SuggestionResponse,
)
from .search import _build_runtime_plan

router = APIRouter(prefix="/v1/tools", tags=["agent-tools"])


@router.get("/bindings", response_model=list[AgentToolBindingContextResponse])
def list_tool_bindings(
    profile_name: str | None = Query(default=None, min_length=1, max_length=128),
    enabled_only: bool = True,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> list[AgentToolBindingContextResponse]:
    """List runtime binding contexts available to agents and automation tools."""

    query = select(ElasticsearchBinding).join(ElasticsearchBinding.profile)
    if profile_name is not None:
        query = query.where(
            TerminologyProfile.normalized_name == normalize_profile_name(profile_name)
        )
    if enabled_only:
        query = query.where(ElasticsearchBinding.is_enabled.is_(True))

    bindings = list(
        session.scalars(
            query.order_by(
                TerminologyProfile.normalized_name,
                ElasticsearchBinding.normalized_name,
            )
        )
    )
    return [_tool_binding_response(binding) for binding in bindings]


@router.post("/validate-alias", response_model=AgentToolValidateAliasResponse)
def validate_alias_tool(
    request: AgentToolValidateAliasRequest,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> AgentToolValidateAliasResponse:
    """Validate an alias proposal without creating a pending suggestion."""

    _validate_proposal_source_type(request.proposal_source_type)
    profile, binding = _resolve_tool_profile_binding(
        session=session,
        profile_name=request.profile_name,
        binding_id=request.binding_id,
    )
    idempotency_key = normalize_idempotency_key(request.idempotency_key)
    validation_summary = build_proposal_validation_summary(
        session,
        profile,
        suggestion_type="alias",
        canonical_value=request.canonical_value,
        alias_value=request.alias_value,
        slot=request.slot,
        confidence=request.confidence,
        proposal_source_type=request.proposal_source_type,
        proposal_source_name=request.proposal_source_name,
        idempotency_key=idempotency_key,
        source_payload=request.source_payload,
    )
    return AgentToolValidateAliasResponse(
        profile_name=profile.name,
        normalized_profile_name=profile.normalized_name,
        binding_id=binding.id if binding is not None else None,
        canonical_value=request.canonical_value,
        alias_value=request.alias_value,
        slot=request.slot.strip().upper(),
        confidence=request.confidence,
        proposal_source_type=request.proposal_source_type,
        proposal_source_name=request.proposal_source_name,
        idempotency_key=idempotency_key,
        validation_summary=validation_summary,
    )


@router.post(
    "/suggest-alias",
    response_model=AgentToolSuggestAliasResponse,
    status_code=status.HTTP_201_CREATED,
)
def suggest_alias_tool(
    request: AgentToolSuggestAliasRequest,
    response: Response,
    current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> AgentToolSuggestAliasResponse:
    """Create a pending alias proposal from an agent, CLI, job, or API caller."""

    _validate_proposal_source_type(request.proposal_source_type)
    profile, binding = _resolve_tool_profile_binding(
        session=session,
        profile_name=request.profile_name,
        binding_id=request.binding_id,
    )
    binding_id = binding.id if binding is not None else None
    idempotency_key = normalize_idempotency_key(request.idempotency_key)
    try:
        existing_suggestion = resolve_idempotent_suggestion(
            session,
            profile=profile,
            idempotency_key=idempotency_key,
            suggestion_type="alias",
            canonical_value=request.canonical_value,
            alias_value=request.alias_value,
            slot=request.slot,
            binding_id=binding_id,
            proposal_source_type=request.proposal_source_type,
        )
    except ProposalIdempotencyConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if existing_suggestion is not None:
        response.status_code = status.HTTP_200_OK
        record_proposal_submission(
            source_type=existing_suggestion.proposal_source_type,
            suggestion_type=existing_suggestion.suggestion_type,
            validation_status=validation_status(
                existing_suggestion.validation_summary_json
            ),
            outcome="idempotent_retry",
        )
        return AgentToolSuggestAliasResponse(
            created=False,
            suggestion=_suggestion_response(existing_suggestion),
            validation_summary=existing_suggestion.validation_summary_json or {},
        )

    validation_summary = build_proposal_validation_summary(
        session,
        profile,
        suggestion_type="alias",
        canonical_value=request.canonical_value,
        alias_value=request.alias_value,
        slot=request.slot,
        confidence=request.confidence,
        proposal_source_type=request.proposal_source_type,
        proposal_source_name=request.proposal_source_name,
        idempotency_key=idempotency_key,
        source_payload=request.source_payload,
    )
    try:
        existing_suggestion = resolve_idempotent_suggestion_from_validation_summary(
            session,
            validation_summary,
            suggestion_type="alias",
            canonical_value=request.canonical_value,
            alias_value=request.alias_value,
            slot=request.slot,
            binding_id=binding_id,
            proposal_source_type=request.proposal_source_type,
        )
    except ProposalIdempotencyConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if existing_suggestion is not None:
        response.status_code = status.HTTP_200_OK
        record_proposal_submission(
            source_type=existing_suggestion.proposal_source_type,
            suggestion_type=existing_suggestion.suggestion_type,
            validation_status=validation_status(
                existing_suggestion.validation_summary_json
            ),
            outcome="idempotent_retry",
        )
        return AgentToolSuggestAliasResponse(
            created=False,
            suggestion=_suggestion_response(existing_suggestion),
            validation_summary=existing_suggestion.validation_summary_json or {},
        )

    suggestion = GovernanceSuggestion(
        profile=profile,
        suggestion_type="alias",
        canonical_value=request.canonical_value,
        alias_value=request.alias_value,
        slot=request.slot,
        description=request.description,
        confidence=request.confidence,
        source="discovery",
        context=request.context,
        binding_id=binding_id,
        proposal_source_type=request.proposal_source_type,
        proposal_source_name=request.proposal_source_name,
        idempotency_key=idempotency_key,
        source_payload_json=request.source_payload,
        validation_summary_json=validation_summary,
        status="pending",
        created_by=current_user.username,
    )
    try:
        session.add(suggestion)
        session.flush()
        sync_ambiguous_alias_candidates_for_suggestion(
            session, suggestion, actor=current_user.username
        )
        session.commit()
        session.refresh(suggestion)
    except IntegrityError as exc:
        session.rollback()
        try:
            existing_suggestion = resolve_idempotent_suggestion(
                session,
                profile=profile,
                idempotency_key=idempotency_key,
                suggestion_type="alias",
                canonical_value=request.canonical_value,
                alias_value=request.alias_value,
                slot=request.slot,
                binding_id=binding_id,
                proposal_source_type=request.proposal_source_type,
            )
        except ProposalIdempotencyConflict as conflict_exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(conflict_exc),
            ) from conflict_exc
        if existing_suggestion is not None:
            response.status_code = status.HTTP_200_OK
            record_proposal_submission(
                source_type=existing_suggestion.proposal_source_type,
                suggestion_type=existing_suggestion.suggestion_type,
                validation_status=validation_status(
                    existing_suggestion.validation_summary_json
                ),
                outcome="idempotent_retry",
            )
            return AgentToolSuggestAliasResponse(
                created=False,
                suggestion=_suggestion_response(existing_suggestion),
                validation_summary=existing_suggestion.validation_summary_json or {},
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not create alias proposal.",
        ) from exc

    record_proposal_submission(
        source_type=suggestion.proposal_source_type,
        suggestion_type=suggestion.suggestion_type,
        validation_status=validation_status(suggestion.validation_summary_json),
        outcome="created",
    )
    suggestion_response = _suggestion_response(suggestion)
    return AgentToolSuggestAliasResponse(
        created=True,
        suggestion=suggestion_response,
        validation_summary=validation_summary,
    )


@router.post("/explain-query", response_model=QueryPlanResponse)
def explain_query_tool(
    request: AgentToolExplainQueryRequest,
    http_request: Request,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> QueryPlanResponse:
    """Explain how a query is canonicalized in a runtime binding/profile context."""

    # Access app.state.config through the request so this endpoint has the same
    # dependency shape as other runtime endpoints when observability grows.
    _ = http_request.app.state.config
    plan = _build_runtime_plan(
        session=session,
        profile_name=request.profile_name,
        binding_id=request.binding_id,
        query_text=request.query,
        text_fields=request.text_fields,
        target_field=request.target_field,
        index_name=None,
        size=request.size,
        canonical_boost=request.canonical_boost,
        include_evidence=request.include_evidence,
        max_matches=request.max_matches,
        warn_without_binding=False,
        require_index=False,
    )
    return QueryPlanResponse(**plan)


def _resolve_tool_profile_binding(
    *, session: Session, profile_name: str | None, binding_id: int | None
) -> tuple[TerminologyProfile, ElasticsearchBinding | None]:
    if binding_id is not None:
        binding = session.scalar(
            select(ElasticsearchBinding).where(ElasticsearchBinding.id == binding_id)
        )
        if binding is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Elasticsearch binding not found: {binding_id}",
            )
        if profile_name is not None and (
            binding.profile.normalized_name != normalize_profile_name(profile_name)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Binding does not belong to the requested profile.",
            )
        return binding.profile, binding

    if profile_name is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Either binding_id or profile_name is required.",
        )
    profile = session.scalar(
        select(TerminologyProfile).where(
            TerminologyProfile.normalized_name == normalize_profile_name(profile_name)
        )
    )
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile not found: {profile_name}",
        )
    return profile, None


def _validate_proposal_source_type(value: str) -> None:
    if value not in PROPOSAL_SOURCE_TYPES:
        allowed = ", ".join(PROPOSAL_SOURCE_TYPES)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid proposal source type: {value}. Allowed values: {allowed}",
        )


def _tool_binding_response(
    binding: ElasticsearchBinding,
) -> AgentToolBindingContextResponse:
    return AgentToolBindingContextResponse(
        id=binding.id,
        name=binding.name,
        profile_name=binding.profile.name,
        normalized_profile_name=binding.profile.normalized_name,
        provider=binding.provider,
        index_name=binding.index_name,
        text_fields=list(binding.text_fields),
        target_field=binding.target_field,
        filter_field=binding.filter_field,
        filter_value=binding.filter_value,
        timestamp_field=binding.timestamp_field,
        time_window_days=binding.time_window_days,
        is_enabled=binding.is_enabled,
        snapshot_version=binding.last_successful_snapshot_version,
        snapshot_status=binding_snapshot_status(binding),
    )


def _suggestion_response(suggestion: GovernanceSuggestion) -> SuggestionResponse:
    return SuggestionResponse(
        id=suggestion.id,
        profile_id=suggestion.profile_id,
        term_id=suggestion.term_id,
        alias_id=suggestion.alias_id,
        binding_id=suggestion.binding_id,
        suggestion_type=suggestion.suggestion_type,
        canonical_value=suggestion.canonical_value,
        normalized_canonical=suggestion.normalized_canonical,
        alias_value=suggestion.alias_value,
        normalized_alias=suggestion.normalized_alias,
        slot=suggestion.slot,
        description=suggestion.description,
        confidence=suggestion.confidence,
        source=suggestion.source,
        context=suggestion.context,
        proposal_source_type=suggestion.proposal_source_type,
        proposal_source_name=suggestion.proposal_source_name,
        idempotency_key=suggestion.idempotency_key,
        source_payload=suggestion.source_payload_json,
        validation_summary=suggestion.validation_summary_json,
        status=suggestion.status,
        created_by=suggestion.created_by,
        reviewed_by=suggestion.reviewed_by,
        review_comment=suggestion.review_comment,
        reviewed_at=suggestion.reviewed_at,
        evidence_snapshot=suggestion.evidence_snapshot,
        evidence_checked_by=suggestion.evidence_checked_by,
        evidence_checked_at=suggestion.evidence_checked_at,
        created_at=suggestion.created_at,
        updated_at=suggestion.updated_at,
    )
