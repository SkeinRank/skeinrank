"""Terminology governance REST endpoints."""

from __future__ import annotations

import hashlib
import html
import json
import re

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from skeinrank_governance.cli import (
    GovernanceCliError,
    add_alias,
    add_term,
    build_snapshot,
    create_profile,
    get_profile,
    get_term,
    set_term_tags,
)
from skeinrank_governance.models import (
    ALIAS_STATUSES,
    AMBIGUOUS_ALIAS_CANDIDATE_SOURCES,
    AMBIGUOUS_ALIAS_CANDIDATE_STATUSES,
    AMBIGUOUS_ALIAS_STATUSES,
    BINDING_POLICY_STATUSES,
    CONFLICT_REVIEW_STATUSES,
    CONFLICT_SEVERITIES,
    ELASTICSEARCH_BINDING_MODES,
    ELASTICSEARCH_BINDING_PROVIDERS,
    ELASTICSEARCH_BINDING_WRITE_STRATEGIES,
    PROPOSAL_SOURCE_TYPES,
    STOP_LIST_TARGETS,
    SUGGESTION_SOURCES,
    SUGGESTION_STATUSES,
    SUGGESTION_TYPES,
    TERM_STATUSES,
    CanonicalTerm,
    ElasticsearchBinding,
    ElasticsearchEnrichmentJob,
    GovernanceAmbiguousAlias,
    GovernanceAmbiguousAliasCandidate,
    GovernanceBindingPolicy,
    GovernanceGlobalStopListEntry,
    GovernanceStopListEntry,
    GovernanceSuggestion,
    TermAlias,
    TerminologyProfile,
    normalize_profile_name,
    normalize_value,
    utc_now,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..ambiguous_proposals import sync_ambiguous_alias_candidates_for_suggestion
from ..apply_policy import apply_policy_for_suggestion, ensure_apply_policy_summary
from ..auth import AuthContext, require_roles
from ..canonical_lifecycle import (
    CanonicalLifecycleError,
    apply_canonical_migration_suggestion,
    build_canonical_migration_plan,
    build_canonical_migration_validation_summary,
    is_canonical_migration_suggestion,
)
from ..conflict_detection import (
    build_conflict_report,
    find_current_conflict,
    merge_conflict_with_review_state,
    upsert_conflict_review_state,
)
from ..dependencies import get_session
from ..elasticsearch import (
    ElasticsearchDiscoveryClient,
    ElasticsearchDiscoveryError,
    compose_source_text,
    get_source_values,
    source_preview,
)
from ..observability.metrics import (
    record_proposal_batch_apply,
    record_proposal_review,
    record_proposal_submission,
)
from ..profile_isolation import build_profile_isolation_report
from ..prompt_injection import scan_untrusted_payload
from ..proposal_idempotency import (
    ProposalIdempotencyConflict,
    normalize_idempotency_key,
    resolve_idempotent_suggestion,
    resolve_idempotent_suggestion_from_validation_summary,
)
from ..proposal_lifecycle import (
    classify_proposal_lifecycle,
    proposal_validation_counts,
    proposal_validation_reasons,
    proposal_validation_status,
)
from ..proposal_quality import build_proposal_source_quality, validation_status
from ..proposal_validation import build_proposal_validation_summary
from ..review_dataset_events import update_review_dataset_events_for_suggestion
from ..role_boundaries import role_boundaries_document, role_boundary_for_auth_context
from ..runtime_snapshots import (
    alias_tuples_from_snapshot,
    binding_snapshot_status,
    build_runtime_snapshot_payload,
    clear_binding_pending_snapshot,
    mark_binding_snapshot_success,
    publish_binding_runtime_snapshot,
    restore_binding_previous_snapshot,
)
from ..schemas import (
    AliasCreateRequest,
    AliasResponse,
    AliasUpdateRequest,
    AmbiguousAliasCandidateResponse,
    AmbiguousAliasResponse,
    AmbiguousAliasUpdateRequest,
    AmbiguousAliasUpsertRequest,
    BindingPolicyResponse,
    BindingPolicyUpsertRequest,
    CanonicalMigrationCreateRequest,
    CanonicalMigrationPlanResponse,
    ConflictReportItemResponse,
    ConflictReportResponse,
    ConflictReviewUpdateRequest,
    ElasticsearchBindingCreateRequest,
    ElasticsearchBindingDryRunDocument,
    ElasticsearchBindingDryRunRequest,
    ElasticsearchBindingDryRunResponse,
    ElasticsearchBindingResponse,
    ElasticsearchBindingUpdateRequest,
    ElasticsearchConnectionStatusResponse,
    ElasticsearchDryRunMatchedAlias,
    ElasticsearchEnrichmentJobCancelRequest,
    ElasticsearchEnrichmentJobCreateRequest,
    ElasticsearchEnrichmentJobPauseRequest,
    ElasticsearchEnrichmentJobResponse,
    ElasticsearchEnrichmentJobResumeRequest,
    ElasticsearchEnrichmentJobRollbackRequest,
    ElasticsearchEnrichmentPreflightResponse,
    ElasticsearchEvidenceDocument,
    ElasticsearchEvidenceRequest,
    ElasticsearchEvidenceResponse,
    ElasticsearchIndexMappingResponse,
    ElasticsearchIndexResponse,
    ElasticsearchMappingFieldResponse,
    GlobalStopListCreateRequest,
    GlobalStopListEntryResponse,
    GlobalStopListUpdateRequest,
    ProfileCreateRequest,
    ProfileIsolationResponse,
    ProfileResponse,
    ProfileUpdateRequest,
    ProposalApplyPolicyResponse,
    ProposalBatchApplyRequest,
    ProposalBatchApplyResponse,
    ProposalBatchPreviewItemResponse,
    ProposalBatchPreviewResponse,
    ProposalBatchSnapshotResponse,
    ProposalSourceQualityResponse,
    RoleBoundariesResponse,
    RoleBoundaryCurrentUserResponse,
    RuntimeSnapshotResponse,
    SnapshotExportRequest,
    StopListCreateRequest,
    StopListEntryResponse,
    StopListUpdateRequest,
    SuggestionCreateRequest,
    SuggestionEvidenceRefreshRequest,
    SuggestionResponse,
    SuggestionReviewRequest,
    TermCreateRequest,
    TermResponse,
    TermUpdateRequest,
)
from ..worker_queue import (
    EnrichmentJobQueueError,
    enqueue_elasticsearch_enrichment_chunk,
    enqueue_elasticsearch_enrichment_job,
)

router = APIRouter(prefix="/v1/governance", tags=["governance"])


@router.get("/isolation-checks", response_model=ProfileIsolationResponse)
def get_profile_isolation_checks(
    sample_limit: int = Query(default=20, ge=0, le=100),
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> ProfileIsolationResponse:
    """Return read-only profile/binding isolation checks for operators."""

    return ProfileIsolationResponse(
        **build_profile_isolation_report(session, sample_limit=sample_limit)
    )


@router.get("/role-boundaries", response_model=RoleBoundariesResponse)
def get_role_boundaries(
    current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
) -> RoleBoundariesResponse:
    """Return operator-facing agent/reviewer/admin role boundaries."""

    document = role_boundaries_document()
    return RoleBoundariesResponse(
        **document,
        current_user=RoleBoundaryCurrentUserResponse(
            **role_boundary_for_auth_context(current_user)
        ),
    )


@router.get("/profiles", response_model=list[ProfileResponse])
def list_profiles(
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> list[ProfileResponse]:
    """List terminology profiles."""

    profiles = list(
        session.scalars(
            select(TerminologyProfile).order_by(TerminologyProfile.normalized_name)
        )
    )
    return [_profile_response(profile) for profile in profiles]


@router.post(
    "/profiles",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_profile_endpoint(
    request: ProfileCreateRequest,
    _admin: AuthContext = Depends(require_roles("admin")),
    session: Session = Depends(get_session),
) -> ProfileResponse:
    """Create a terminology profile."""

    try:
        profile = create_profile(
            session,
            request.name,
            description=request.description,
            actor="api",
        )
        session.commit()
        session.refresh(profile)
        return _profile_response(profile)
    except GovernanceCliError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.patch(
    "/profiles/{profile_name}",
    response_model=ProfileResponse,
)
def update_profile_endpoint(
    profile_name: str,
    request: ProfileUpdateRequest,
    _admin: AuthContext = Depends(require_roles("admin")),
    session: Session = Depends(get_session),
) -> ProfileResponse:
    """Update a terminology profile name or description."""

    profile = _get_profile_or_404(session, profile_name)
    fields = request.model_fields_set

    if "name" in fields and request.name is not None:
        normalized_name = normalize_profile_name(request.name)
        existing = session.scalar(
            select(TerminologyProfile).where(
                TerminologyProfile.normalized_name == normalized_name,
                TerminologyProfile.id != profile.id,
            )
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Profile already exists: {request.name}",
            )
        profile.name = request.name

    if "description" in fields:
        profile.description = request.description

    try:
        session.commit()
        session.refresh(profile)
        return _profile_response(profile)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.delete(
    "/profiles/{profile_name}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_profile_endpoint(
    profile_name: str,
    _admin: AuthContext = Depends(require_roles("admin")),
    session: Session = Depends(get_session),
) -> Response:
    """Delete a terminology profile and its child terms/aliases."""

    profile = _get_profile_or_404(session, profile_name)
    session.delete(profile)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/profiles/{profile_name}/stop-list",
    response_model=list[StopListEntryResponse],
)
def list_profile_stop_list(
    profile_name: str,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> list[StopListEntryResponse]:
    """List profile-scoped stop-list guardrails."""

    profile = _get_profile_or_404(session, profile_name)
    entries = list(
        session.scalars(
            select(GovernanceStopListEntry)
            .where(GovernanceStopListEntry.profile_id == profile.id)
            .order_by(
                GovernanceStopListEntry.target,
                GovernanceStopListEntry.normalized_value,
            )
        )
    )
    return [_stop_list_response(entry) for entry in entries]


@router.post(
    "/profiles/{profile_name}/stop-list",
    response_model=StopListEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_profile_stop_list_entry(
    profile_name: str,
    request: StopListCreateRequest,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> StopListEntryResponse:
    """Create a profile-scoped stop-list entry."""

    profile = _get_profile_or_404(session, profile_name)
    _validate_stop_list_target(request.target)
    normalized_value = normalize_value(request.value)
    _ensure_stop_list_entry_unique(
        session,
        profile,
        normalized_value=normalized_value,
        target=request.target,
    )

    entry = GovernanceStopListEntry(
        profile=profile,
        value=request.value,
        target=request.target,
        reason=request.reason,
        is_active=request.is_active,
    )
    session.add(entry)
    try:
        session.commit()
        session.refresh(entry)
        return _stop_list_response(entry)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.patch(
    "/profiles/{profile_name}/stop-list/{entry_id}",
    response_model=StopListEntryResponse,
)
def update_profile_stop_list_entry(
    profile_name: str,
    entry_id: int,
    request: StopListUpdateRequest,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> StopListEntryResponse:
    """Update a profile-scoped stop-list entry."""

    profile = _get_profile_or_404(session, profile_name)
    entry = _get_stop_list_entry_or_404(session, profile, entry_id)
    fields = request.model_fields_set

    next_value = (
        request.value
        if "value" in fields and request.value is not None
        else entry.value
    )
    next_target = (
        request.target
        if "target" in fields and request.target is not None
        else entry.target
    )
    _validate_stop_list_target(next_target)

    if next_value != entry.value or next_target != entry.target:
        _ensure_stop_list_entry_unique(
            session,
            profile,
            normalized_value=normalize_value(next_value),
            target=next_target,
            exclude_id=entry.id,
        )
        entry.value = next_value
        entry.target = next_target

    if "reason" in fields:
        entry.reason = request.reason
    if "is_active" in fields and request.is_active is not None:
        entry.is_active = request.is_active

    try:
        session.commit()
        session.refresh(entry)
        return _stop_list_response(entry)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.delete(
    "/profiles/{profile_name}/stop-list/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_profile_stop_list_entry(
    profile_name: str,
    entry_id: int,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> Response:
    """Delete a profile-scoped stop-list entry."""

    profile = _get_profile_or_404(session, profile_name)
    entry = _get_stop_list_entry_or_404(session, profile, entry_id)
    session.delete(entry)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/global-stop-list",
    response_model=list[GlobalStopListEntryResponse],
)
def list_global_stop_list(
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> list[GlobalStopListEntryResponse]:
    """List global stop-list guardrails."""

    entries = list(
        session.scalars(
            select(GovernanceGlobalStopListEntry).order_by(
                GovernanceGlobalStopListEntry.target,
                GovernanceGlobalStopListEntry.normalized_value,
            )
        )
    )
    return [_global_stop_list_response(entry) for entry in entries]


@router.post(
    "/global-stop-list",
    response_model=GlobalStopListEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_global_stop_list_entry(
    request: GlobalStopListCreateRequest,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> GlobalStopListEntryResponse:
    """Create a global stop-list entry."""

    _validate_stop_list_target(request.target)
    normalized_value = normalize_value(request.value)
    _ensure_global_stop_list_entry_unique(
        session,
        normalized_value=normalized_value,
        target=request.target,
    )

    entry = GovernanceGlobalStopListEntry(
        value=request.value,
        target=request.target,
        reason=request.reason,
        is_active=request.is_active,
    )
    session.add(entry)
    try:
        session.commit()
        session.refresh(entry)
        return _global_stop_list_response(entry)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.patch(
    "/global-stop-list/{entry_id}",
    response_model=GlobalStopListEntryResponse,
)
def update_global_stop_list_entry(
    entry_id: int,
    request: GlobalStopListUpdateRequest,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> GlobalStopListEntryResponse:
    """Update a global stop-list entry."""

    entry = _get_global_stop_list_entry_or_404(session, entry_id)
    fields = request.model_fields_set

    next_value = (
        request.value
        if "value" in fields and request.value is not None
        else entry.value
    )
    next_target = (
        request.target
        if "target" in fields and request.target is not None
        else entry.target
    )
    _validate_stop_list_target(next_target)

    if next_value != entry.value or next_target != entry.target:
        _ensure_global_stop_list_entry_unique(
            session,
            normalized_value=normalize_value(next_value),
            target=next_target,
            exclude_id=entry.id,
        )
        entry.value = next_value
        entry.target = next_target

    if "reason" in fields:
        entry.reason = request.reason
    if "is_active" in fields and request.is_active is not None:
        entry.is_active = request.is_active

    try:
        session.commit()
        session.refresh(entry)
        return _global_stop_list_response(entry)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.delete(
    "/global-stop-list/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_global_stop_list_entry(
    entry_id: int,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> Response:
    """Delete a global stop-list entry."""

    entry = _get_global_stop_list_entry_or_404(session, entry_id)
    session.delete(entry)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/elasticsearch/connection/status",
    response_model=ElasticsearchConnectionStatusResponse,
)
def get_elasticsearch_connection_status(
    request: Request,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
) -> ElasticsearchConnectionStatusResponse:
    """Test whether the configured Elasticsearch endpoint is reachable."""

    client = ElasticsearchDiscoveryClient(request.app.state.config)
    if not client.is_configured:
        return ElasticsearchConnectionStatusResponse(
            configured=False,
            ok=False,
            error="Elasticsearch URL is not configured.",
        )

    try:
        info = client.cluster_info()
    except ElasticsearchDiscoveryError as exc:
        return ElasticsearchConnectionStatusResponse(
            configured=True,
            ok=False,
            url=client.url,
            error=str(exc),
        )

    version = info.get("version") if isinstance(info, dict) else None
    version_number = version.get("number") if isinstance(version, dict) else None
    return ElasticsearchConnectionStatusResponse(
        configured=True,
        ok=True,
        url=client.url,
        cluster_name=str(info.get("cluster_name"))
        if isinstance(info, dict) and info.get("cluster_name")
        else None,
        cluster_version=str(version_number) if version_number else None,
    )


@router.get(
    "/elasticsearch/indices",
    response_model=list[ElasticsearchIndexResponse],
)
def list_elasticsearch_indices(
    request: Request,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
) -> list[ElasticsearchIndexResponse]:
    """List Elasticsearch indices when a connection is configured."""

    client = ElasticsearchDiscoveryClient(request.app.state.config)
    if not client.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Elasticsearch URL is not configured.",
        )
    try:
        indices = client.list_indices()
    except ElasticsearchDiscoveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return [ElasticsearchIndexResponse(**item) for item in indices]


@router.get(
    "/elasticsearch/indices/{index_name}/mapping",
    response_model=ElasticsearchIndexMappingResponse,
)
def get_elasticsearch_index_mapping(
    index_name: str,
    request: Request,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
) -> ElasticsearchIndexMappingResponse:
    """Return flattened mapping fields for one Elasticsearch index."""

    client = ElasticsearchDiscoveryClient(request.app.state.config)
    if not client.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Elasticsearch URL is not configured.",
        )
    try:
        fields = client.index_fields(index_name)
    except ElasticsearchDiscoveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return ElasticsearchIndexMappingResponse(
        index_name=index_name,
        fields=[
            ElasticsearchMappingFieldResponse(**field.__dict__) for field in fields
        ],
    )


@router.get(
    "/elasticsearch/bindings",
    response_model=list[ElasticsearchBindingResponse],
)
def list_elasticsearch_bindings(
    profile_name: str | None = Query(default=None),
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> list[ElasticsearchBindingResponse]:
    """List saved Elasticsearch enrichment bindings."""

    query = select(ElasticsearchBinding).join(TerminologyProfile)
    if profile_name is not None:
        profile = _get_profile_or_404(session, profile_name)
        query = query.where(ElasticsearchBinding.profile_id == profile.id)
    bindings = list(
        session.scalars(
            query.order_by(
                ElasticsearchBinding.is_enabled.desc(),
                ElasticsearchBinding.normalized_name,
            )
        )
    )
    return [_elasticsearch_binding_response(binding) for binding in bindings]


@router.post(
    "/elasticsearch/bindings",
    response_model=ElasticsearchBindingResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_elasticsearch_binding(
    request: ElasticsearchBindingCreateRequest,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> ElasticsearchBindingResponse:
    """Create a saved Elasticsearch enrichment binding."""

    profile = _get_profile_or_404(session, request.profile_name)
    _validate_elasticsearch_binding_mode(request.mode)
    _validate_elasticsearch_binding_write_strategy(request.write_strategy)
    _validate_elasticsearch_binding_provider("elasticsearch")
    text_fields = _normalize_text_fields(request.text_fields)
    filter_field, filter_value = _normalize_optional_filter(
        request.filter_field, request.filter_value
    )
    timestamp_field, time_window_days = _normalize_time_filter(
        request.timestamp_field, request.time_window_days
    )
    _ensure_elasticsearch_binding_name_unique(
        session,
        normalized_name=normalize_profile_name(request.name),
    )

    binding = ElasticsearchBinding(
        profile=profile,
        name=request.name,
        description=request.description,
        provider="elasticsearch",
        index_name=request.index_name,
        text_fields=text_fields,
        target_field=request.target_field,
        filter_field=filter_field,
        filter_value=filter_value,
        timestamp_field=timestamp_field,
        time_window_days=time_window_days,
        mode=request.mode,
        write_strategy=request.write_strategy,
        is_enabled=request.is_enabled,
    )
    session.add(binding)
    try:
        session.commit()
        session.refresh(binding)
        return _elasticsearch_binding_response(binding)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.patch(
    "/elasticsearch/bindings/{binding_id}",
    response_model=ElasticsearchBindingResponse,
)
def update_elasticsearch_binding(
    binding_id: int,
    request: ElasticsearchBindingUpdateRequest,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> ElasticsearchBindingResponse:
    """Update a saved Elasticsearch enrichment binding."""

    binding = _get_elasticsearch_binding_or_404(session, binding_id)
    fields = request.model_fields_set

    if "profile_name" in fields and request.profile_name is not None:
        binding.profile = _get_profile_or_404(session, request.profile_name)

    if "name" in fields and request.name is not None:
        _ensure_elasticsearch_binding_name_unique(
            session,
            normalized_name=normalize_profile_name(request.name),
            exclude_id=binding.id,
        )
        binding.name = request.name

    if "description" in fields:
        binding.description = request.description

    if "index_name" in fields and request.index_name is not None:
        binding.index_name = request.index_name

    if "text_fields" in fields and request.text_fields is not None:
        binding.text_fields = _normalize_text_fields(request.text_fields)

    if "target_field" in fields and request.target_field is not None:
        binding.target_field = request.target_field

    next_filter_field = (
        request.filter_field if "filter_field" in fields else binding.filter_field
    )
    next_filter_value = (
        request.filter_value if "filter_value" in fields else binding.filter_value
    )
    if "filter_field" in fields or "filter_value" in fields:
        binding.filter_field, binding.filter_value = _normalize_optional_filter(
            next_filter_field, next_filter_value
        )

    next_timestamp_field = (
        request.timestamp_field
        if "timestamp_field" in fields
        else binding.timestamp_field
    )
    next_time_window_days = (
        request.time_window_days
        if "time_window_days" in fields
        else binding.time_window_days
    )
    if "timestamp_field" in fields or "time_window_days" in fields:
        binding.timestamp_field, binding.time_window_days = _normalize_time_filter(
            next_timestamp_field, next_time_window_days
        )

    if "mode" in fields and request.mode is not None:
        _validate_elasticsearch_binding_mode(request.mode)
        binding.mode = request.mode

    if "write_strategy" in fields and request.write_strategy is not None:
        _validate_elasticsearch_binding_write_strategy(request.write_strategy)
        binding.write_strategy = request.write_strategy

    if "is_enabled" in fields and request.is_enabled is not None:
        binding.is_enabled = request.is_enabled

    try:
        session.commit()
        session.refresh(binding)
        return _elasticsearch_binding_response(binding)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.delete(
    "/elasticsearch/bindings/{binding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_elasticsearch_binding(
    binding_id: int,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> Response:
    """Delete a saved Elasticsearch enrichment binding."""

    binding = _get_elasticsearch_binding_or_404(session, binding_id)
    session.delete(binding)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/elasticsearch/bindings/{binding_id}/policy",
    response_model=BindingPolicyResponse,
)
def get_elasticsearch_binding_policy(
    binding_id: int,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> BindingPolicyResponse:
    """Return the policy attached to one runtime binding."""

    binding = _get_elasticsearch_binding_or_404(session, binding_id)
    policy = _get_binding_policy_or_404(session, binding)
    return _binding_policy_response(policy)


@router.put(
    "/elasticsearch/bindings/{binding_id}/policy",
    response_model=BindingPolicyResponse,
)
def upsert_elasticsearch_binding_policy(
    binding_id: int,
    request: BindingPolicyUpsertRequest,
    response: Response,
    current_user: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> BindingPolicyResponse:
    """Create or update binding-scoped runtime policy metadata."""

    _validate_status(request.status, BINDING_POLICY_STATUSES, "binding policy")
    binding = _get_elasticsearch_binding_or_404(session, binding_id)
    policy = session.scalar(
        select(GovernanceBindingPolicy).where(
            GovernanceBindingPolicy.binding_id == binding.id
        )
    )
    response_status = status.HTTP_200_OK
    context_rules = [
        rule.model_dump(exclude_none=True) for rule in request.context_rules
    ]
    if policy is None:
        response_status = status.HTTP_201_CREATED
        policy = GovernanceBindingPolicy(
            binding=binding,
            profile=binding.profile,
            status=request.status,
            preferred_slots=request.preferred_slots,
            allowed_tags=request.allowed_tags,
            deny_slots=request.deny_slots,
            context_rules=context_rules,
            created_by=current_user.username,
            updated_by=current_user.username,
        )
        session.add(policy)
    else:
        policy.status = request.status
        policy.preferred_slots = request.preferred_slots
        policy.allowed_tags = request.allowed_tags
        policy.deny_slots = request.deny_slots
        policy.context_rules = context_rules
        policy.updated_by = current_user.username
    try:
        session.commit()
        session.refresh(policy)
        response.status_code = response_status
        return _binding_policy_response(policy)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.delete(
    "/elasticsearch/bindings/{binding_id}/policy",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_elasticsearch_binding_policy(
    binding_id: int,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> Response:
    """Delete a binding policy without changing the binding or terminology."""

    binding = _get_elasticsearch_binding_or_404(session, binding_id)
    policy = _get_binding_policy_or_404(session, binding)
    session.delete(policy)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/elasticsearch/bindings/{binding_id}/dry-run",
    response_model=ElasticsearchBindingDryRunResponse,
)
def dry_run_elasticsearch_binding(
    binding_id: int,
    request: Request,
    request_body: ElasticsearchBindingDryRunRequest | None = Body(default=None),
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> ElasticsearchBindingDryRunResponse:
    """Preview enrichment for a binding without writing to Elasticsearch."""

    binding = _get_elasticsearch_binding_or_404(session, binding_id)
    if not binding.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Elasticsearch binding is disabled.",
        )

    limit = (request_body or ElasticsearchBindingDryRunRequest()).limit
    client = ElasticsearchDiscoveryClient(request.app.state.config)
    if not client.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Elasticsearch URL is not configured.",
        )

    try:
        hits = client.search_documents(
            index_name=binding.index_name,
            text_fields=list(binding.text_fields),
            limit=limit,
            filter_field=binding.filter_field,
            filter_value=binding.filter_value,
            timestamp_field=binding.timestamp_field,
            time_window_days=binding.time_window_days,
        )
    except ElasticsearchDiscoveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    alias_entries = _active_alias_entries_for_profile(session, binding.profile)
    snapshot_payload = build_runtime_snapshot_payload(session, binding.profile)
    documents: list[ElasticsearchBindingDryRunDocument] = []
    for hit in hits:
        text = compose_source_text(hit.source, list(binding.text_fields))
        matched_aliases = _match_alias_entries(text, alias_entries)
        would_write_payload = _dry_run_payload(
            binding,
            matched_aliases,
            snapshot_version=str(snapshot_payload["version"]),
        )
        preview_fields = list(binding.text_fields)
        if binding.filter_field:
            preview_fields = [*preview_fields, binding.filter_field]
        if binding.timestamp_field:
            preview_fields = [*preview_fields, binding.timestamp_field]
        documents.append(
            ElasticsearchBindingDryRunDocument(
                document_id=hit.id,
                index_name=hit.index,
                text_preview=text[:500],
                source_preview=source_preview(hit.source, preview_fields),
                matched_aliases=matched_aliases,
                would_write={binding.target_field: would_write_payload},
            )
        )

    warnings: list[str] = []
    if not hits:
        warnings.append("No sample documents matched this binding.")
    if binding.mode == "write":
        warnings.append(
            "Dry-run is read-only even though this binding is configured for write mode."
        )

    return ElasticsearchBindingDryRunResponse(
        binding=_elasticsearch_binding_response(binding),
        limit=limit,
        documents=documents,
        warnings=warnings,
    )


@router.post(
    "/elasticsearch/bindings/{binding_id}/evidence",
    response_model=ElasticsearchEvidenceResponse,
)
def find_elasticsearch_evidence(
    binding_id: int,
    request_body: ElasticsearchEvidenceRequest,
    request: Request,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> ElasticsearchEvidenceResponse:
    """Find bounded read-only evidence snippets for a term or alias."""

    binding = _get_elasticsearch_binding_or_404(session, binding_id)
    return _build_elasticsearch_evidence_response(
        request=request,
        session=session,
        binding=binding,
        request_body=request_body,
    )


@router.post(
    "/elasticsearch/bindings/{binding_id}/jobs/preflight",
    response_model=ElasticsearchEnrichmentPreflightResponse,
)
def preflight_elasticsearch_enrichment_job(
    binding_id: int,
    request: Request,
    request_body: ElasticsearchEnrichmentJobCreateRequest | None = Body(default=None),
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> ElasticsearchEnrichmentPreflightResponse:
    """Return a read-only safety plan before starting an enrichment job."""

    request_body = request_body or ElasticsearchEnrichmentJobCreateRequest()
    binding = _get_elasticsearch_binding_or_404(session, binding_id)
    snapshot_payload = build_runtime_snapshot_payload(
        session,
        binding.profile,
        snapshot_version=request_body.snapshot_version,
    )
    return _build_elasticsearch_enrichment_preflight_response(
        request=request,
        session=session,
        binding=binding,
        request_body=request_body,
        snapshot_payload=snapshot_payload,
    )


@router.post(
    "/elasticsearch/bindings/{binding_id}/jobs",
    response_model=ElasticsearchEnrichmentJobResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_elasticsearch_enrichment_job(
    binding_id: int,
    request: Request,
    request_body: ElasticsearchEnrichmentJobCreateRequest | None = Body(default=None),
    current_user: AuthContext = Depends(require_roles("admin")),
    session: Session = Depends(get_session),
) -> ElasticsearchEnrichmentJobResponse:
    """Start an enrichment job for one Elasticsearch binding."""

    request_body = request_body or ElasticsearchEnrichmentJobCreateRequest()
    binding = _get_elasticsearch_binding_or_404(session, binding_id)
    if not binding.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Elasticsearch binding is disabled.",
        )
    if binding.mode != "write":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Elasticsearch binding must be in write mode before starting an enrichment job.",
        )

    client = ElasticsearchDiscoveryClient(request.app.state.config)
    if not client.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Elasticsearch URL is not configured.",
        )

    snapshot_payload = build_runtime_snapshot_payload(
        session,
        binding.profile,
        snapshot_version=request_body.snapshot_version,
    )
    preflight = _build_elasticsearch_enrichment_preflight_response(
        request=request,
        session=session,
        binding=binding,
        request_body=request_body,
        snapshot_payload=snapshot_payload,
        elasticsearch_configured=True,
    )
    if not preflight.ready:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Elasticsearch enrichment preflight failed.",
                "blocking_issues": preflight.blocking_issues,
            },
        )
    if request_body.confirmation_token != preflight.confirmation_token:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": (
                    "Confirmation token missing or stale. Re-run preflight and "
                    "confirm the exact enrichment plan before starting the job."
                ),
                "expected_token_fields": preflight.confirmation_token_fields,
            },
        )
    previous_successful_job_id = binding.last_successful_job_id
    job = ElasticsearchEnrichmentJob(
        binding=binding,
        profile=binding.profile,
        status="queued",
        write_strategy=binding.write_strategy,
        source_index=binding.index_name,
        target_index=_job_target_index(binding, request_body.target_index_name),
        alias_name=_job_alias_name(binding, request_body.alias_name),
        snapshot_version=str(snapshot_payload["version"]),
        snapshot_json=snapshot_payload,
        previous_snapshot_version=binding.last_successful_snapshot_version,
        previous_snapshot_json=binding.runtime_snapshot_json,
        requested_by=current_user.username,
        result_json={},
    )
    binding.pending_snapshot_version = job.snapshot_version
    session.add(job)
    session.flush()
    if (
        binding.write_strategy == "reindex_alias_swap"
        and not request_body.target_index_name
    ):
        job.target_index = _default_reindex_target_name(binding, job.id)

    chunk_size = request_body.chunk_size or min(
        request.app.state.config.enrichment_chunk_size,
        request_body.max_documents,
    )
    job.result_json = {
        "job_backend": request.app.state.config.enrichment_jobs_backend,
        "max_documents": request_body.max_documents,
        "chunk_size": chunk_size,
        "snapshot_version": job.snapshot_version,
        "snapshot_aliases_total": len(
            (job.snapshot_json or {}).get("alias_entries") or []
        ),
        "previous_snapshot_version": job.previous_snapshot_version,
        "previous_successful_job_id": previous_successful_job_id,
    }

    if request.app.state.config.enrichment_jobs_backend == "celery":
        session.commit()
        session.refresh(job)
        try:
            queued_task = enqueue_elasticsearch_enrichment_job(
                config=request.app.state.config,
                job_id=job.id,
            )
        except EnrichmentJobQueueError as exc:
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = utc_now()
            clear_binding_pending_snapshot(binding)
            session.commit()
            session.refresh(job)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        job.result_json = {
            **(job.result_json or {}),
            "celery_task_id": queued_task.task_id,
            "celery_queue": queued_task.queue,
        }
        session.commit()
        session.refresh(job)
        return _elasticsearch_enrichment_job_response(job)

    job.status = "running"
    job.started_at = utc_now()
    session.commit()
    session.refresh(job)

    try:
        result = _execute_elasticsearch_enrichment_job(
            client=client,
            session=session,
            binding=binding,
            job=job,
            max_documents=request_body.max_documents,
        )
    except ElasticsearchDiscoveryError as exc:
        job.status = "failed"
        job.error_message = str(exc)
        job.finished_at = utc_now()
        clear_binding_pending_snapshot(binding)
        session.commit()
        session.refresh(job)
        return _elasticsearch_enrichment_job_response(job)

    result = {**result, "job_backend": "sync"}
    job.status = "succeeded"
    job.documents_seen = result["documents_seen"]
    job.documents_enriched = result["documents_enriched"]
    job.documents_failed = result.get("documents_failed", 0)
    job.result_json = result
    job.finished_at = utc_now()
    mark_binding_snapshot_success(
        binding=binding, job=job, completed_at=job.finished_at
    )
    session.commit()
    session.refresh(job)
    return _elasticsearch_enrichment_job_response(job)


@router.get(
    "/elasticsearch/jobs",
    response_model=list[ElasticsearchEnrichmentJobResponse],
)
def list_elasticsearch_enrichment_jobs(
    binding_id: int | None = Query(default=None),
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> list[ElasticsearchEnrichmentJobResponse]:
    """List Elasticsearch enrichment jobs."""

    query = select(ElasticsearchEnrichmentJob).join(ElasticsearchBinding)
    if binding_id is not None:
        query = query.where(ElasticsearchEnrichmentJob.binding_id == binding_id)
    jobs = list(
        session.scalars(
            query.order_by(
                ElasticsearchEnrichmentJob.created_at.desc(),
                ElasticsearchEnrichmentJob.id.desc(),
            )
        )
    )
    return [_elasticsearch_enrichment_job_response(job) for job in jobs]


@router.get(
    "/elasticsearch/jobs/{job_id}",
    response_model=ElasticsearchEnrichmentJobResponse,
)
def get_elasticsearch_enrichment_job(
    job_id: int,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> ElasticsearchEnrichmentJobResponse:
    """Return one Elasticsearch enrichment job."""

    job = _get_elasticsearch_enrichment_job_or_404(session, job_id)
    return _elasticsearch_enrichment_job_response(job)


@router.post(
    "/elasticsearch/jobs/{job_id}/cancel",
    response_model=ElasticsearchEnrichmentJobResponse,
)
def cancel_elasticsearch_enrichment_job(
    job_id: int,
    request_body: ElasticsearchEnrichmentJobCancelRequest | None = Body(default=None),
    current_user: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> ElasticsearchEnrichmentJobResponse:
    """Request safe cancellation for a queued or running enrichment job."""

    job = _get_elasticsearch_enrichment_job_or_404(session, job_id)
    request_body = request_body or ElasticsearchEnrichmentJobCancelRequest()
    now = utc_now()
    cancellation = {
        "requested_by": current_user.username,
        "requested_at": now.isoformat(),
    }
    if request_body.reason:
        cancellation["reason"] = request_body.reason

    if job.status in {"queued", "paused"}:
        job.status = "cancelled"
        job.finished_at = now
        job.error_message = None
        cancellation["cancelled_at"] = now.isoformat()
    elif job.status in {"running", "pause_requested"}:
        job.status = "cancel_requested"
    elif job.status == "cancel_requested":
        pass
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel enrichment job with status: {job.status}",
        )

    job.result_json = {
        **(job.result_json or {}),
        "cancellation": cancellation,
    }
    session.commit()
    session.refresh(job)
    return _elasticsearch_enrichment_job_response(job)


@router.post(
    "/elasticsearch/jobs/{job_id}/pause",
    response_model=ElasticsearchEnrichmentJobResponse,
)
def pause_elasticsearch_enrichment_job(
    job_id: int,
    request_body: ElasticsearchEnrichmentJobPauseRequest | None = Body(default=None),
    current_user: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> ElasticsearchEnrichmentJobResponse:
    """Request a checkpointed pause for a queued or running enrichment job."""

    job = _get_elasticsearch_enrichment_job_or_404(session, job_id)
    request_body = request_body or ElasticsearchEnrichmentJobPauseRequest()
    now = utc_now()
    pause = {
        "requested_by": current_user.username,
        "requested_at": now.isoformat(),
    }
    if request_body.reason:
        pause["reason"] = request_body.reason

    result_json = dict(job.result_json or {})
    result_json["pause"] = {**dict(result_json.get("pause") or {}), **pause}

    if job.status == "queued":
        job.status = "paused"
        result_json["pause"]["paused_at"] = now.isoformat()
    elif job.status == "running":
        job.status = "pause_requested"
    elif job.status in {"pause_requested", "paused"}:
        pass
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot pause enrichment job with status: {job.status}",
        )

    job.result_json = _refresh_enrichment_checkpoint(result_json)
    session.commit()
    session.refresh(job)
    return _elasticsearch_enrichment_job_response(job)


@router.post(
    "/elasticsearch/jobs/{job_id}/resume",
    response_model=ElasticsearchEnrichmentJobResponse,
)
def resume_elasticsearch_enrichment_job(
    job_id: int,
    request: Request,
    request_body: ElasticsearchEnrichmentJobResumeRequest | None = Body(default=None),
    current_user: AuthContext = Depends(require_roles("admin")),
    session: Session = Depends(get_session),
) -> ElasticsearchEnrichmentJobResponse:
    """Resume a paused enrichment job from its last chunk checkpoint."""

    job = _get_elasticsearch_enrichment_job_or_404(session, job_id)
    request_body = request_body or ElasticsearchEnrichmentJobResumeRequest()
    if job.status != "paused":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot resume enrichment job with status: {job.status}",
        )
    if request.app.state.config.enrichment_jobs_backend != "celery":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pause/resume is only supported for the celery enrichment backend.",
        )

    now = utc_now()
    result_json = dict(job.result_json or {})
    resume_event = {
        "requested_by": current_user.username,
        "requested_at": now.isoformat(),
    }
    if request_body.reason:
        resume_event["reason"] = request_body.reason
    resume_history = list(result_json.get("resume_history") or [])
    resume_history.append(resume_event)
    result_json["resume_history"] = resume_history
    result_json.pop("pause", None)

    chunked = dict(result_json.get("chunked_enrichment") or {})
    if not chunked:
        job.status = "queued"
        job.error_message = None
        job.finished_at = None
        job.result_json = _refresh_enrichment_checkpoint(result_json)
        session.commit()
        session.refresh(job)
        try:
            queued_task = enqueue_elasticsearch_enrichment_job(
                config=request.app.state.config,
                job_id=job.id,
            )
        except EnrichmentJobQueueError as exc:
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = utc_now()
            clear_binding_pending_snapshot(job.binding)
            session.commit()
            session.refresh(job)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        result_json = dict(job.result_json or {})
        result_json["resume_coordinator_task_id"] = queued_task.task_id
        result_json["resume_queue"] = queued_task.queue
        job.result_json = result_json
        session.commit()
        session.refresh(job)
        return _elasticsearch_enrichment_job_response(job)

    pending_specs = _pending_enrichment_chunk_specs(result_json)
    if not pending_specs:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No pending enrichment chunks are available to resume.",
        )

    job.status = "running"
    job.error_message = None
    job.finished_at = None
    job.result_json = _refresh_enrichment_checkpoint(result_json)
    session.commit()
    session.refresh(job)

    resumed_chunks: list[dict[str, object]] = []
    try:
        for spec in pending_specs:
            queued_task = enqueue_elasticsearch_enrichment_chunk(
                config=request.app.state.config,
                job_id=job.id,
                chunk_index=int(spec["chunk_index"]),
                offset=int(spec["offset"]),
                limit=int(spec["limit"]),
            )
            resumed_chunks.append(
                {
                    "chunk_index": int(spec["chunk_index"]),
                    "task_id": queued_task.task_id,
                    "queue": queued_task.queue,
                }
            )
    except EnrichmentJobQueueError as exc:
        job.status = "paused"
        result_json = dict(job.result_json or {})
        result_json["resume_error"] = str(exc)
        job.result_json = _refresh_enrichment_checkpoint(result_json)
        session.commit()
        session.refresh(job)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    result_json = dict(job.result_json or {})
    chunked = dict(result_json.get("chunked_enrichment") or {})
    resumed_history = list(chunked.get("resumed_chunks") or [])
    resumed_history.extend(resumed_chunks)
    chunked["resumed_chunks"] = resumed_history
    chunked["last_resumed_at"] = now.isoformat()
    result_json["chunked_enrichment"] = chunked
    job.result_json = _refresh_enrichment_checkpoint(result_json)
    session.commit()
    session.refresh(job)
    return _elasticsearch_enrichment_job_response(job)


@router.post(
    "/elasticsearch/jobs/{job_id}/rollback",
    response_model=ElasticsearchEnrichmentJobResponse,
)
def rollback_elasticsearch_enrichment_job(
    job_id: int,
    request: Request,
    request_body: ElasticsearchEnrichmentJobRollbackRequest | None = Body(default=None),
    current_user: AuthContext = Depends(require_roles("admin")),
    session: Session = Depends(get_session),
) -> ElasticsearchEnrichmentJobResponse:
    """Safely roll back a completed reindex+alias-swap enrichment job."""

    job = _get_elasticsearch_enrichment_job_or_404(session, job_id)
    request_body = request_body or ElasticsearchEnrichmentJobRollbackRequest()
    rollout = _validated_rollback_rollout(job)
    alias_name = str(rollout["alias_name"])
    rollback_index = str(rollout["rollback_candidate_index"])
    expected_current_indices = _rollout_expected_current_indices(rollout, job)

    try:
        client = ElasticsearchDiscoveryClient(request.app.state.config)
        if not client.is_configured:
            raise ElasticsearchDiscoveryError("Elasticsearch URL is not configured.")
        current_alias_indices = client.alias_indices(alias_name=alias_name)
        if sorted(current_alias_indices) != sorted(expected_current_indices):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Cannot rollback alias because current alias indices do not "
                    "match the expected post-rollout state."
                ),
            )
        alias_result = client.swap_alias(
            alias_name=alias_name,
            target_index=rollback_index,
        )
        alias_indices_after = client.alias_indices(alias_name=alias_name)
    except HTTPException:
        raise
    except ElasticsearchDiscoveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    now = utc_now()
    rollback_metadata = {
        "status": "rolled_back",
        "requested_by": current_user.username,
        "requested_at": now.isoformat(),
        "completed_at": now.isoformat(),
        "reason": request_body.reason,
        "alias_name": alias_name,
        "from_indices": current_alias_indices,
        "rollback_candidate_index": rollback_index,
        "alias_indices_after_rollback": alias_indices_after,
        "alias_result": alias_result,
    }
    result_json = dict(job.result_json or {})
    result_json["rollout"] = {
        **rollout,
        "status": "rolled_back",
        "rollback_available": False,
        "rollback_completed": True,
        "rollback_completed_at": now.isoformat(),
        "rollback": rollback_metadata,
        "rollback_hint": (
            f"Rollback completed: alias {alias_name} now points to {rollback_index}."
        ),
    }
    job.result_json = result_json
    restore_binding_previous_snapshot(binding=job.binding, job=job)
    session.commit()
    session.refresh(job)
    return _elasticsearch_enrichment_job_response(job)


@router.get(
    "/profiles/{profile_name}/terms",
    response_model=list[TermResponse],
)
def list_profile_terms(
    profile_name: str,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> list[TermResponse]:
    """List canonical terms and aliases for a terminology profile."""

    profile = _get_profile_or_404(session, profile_name)
    terms = list(
        session.scalars(
            select(CanonicalTerm)
            .where(CanonicalTerm.profile_id == profile.id)
            .order_by(CanonicalTerm.slot, CanonicalTerm.normalized_value)
        )
    )
    for term in terms:
        term.aliases.sort(key=lambda alias: alias.normalized_alias)
        term.tags.sort(key=lambda tag: tag.normalized_value)
    return [_term_response(term) for term in terms]


@router.post(
    "/profiles/{profile_name}/terms",
    response_model=TermResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_profile_term(
    profile_name: str,
    request: TermCreateRequest,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> TermResponse:
    """Add a canonical term to a terminology profile."""

    profile = _get_profile_or_404(session, profile_name)
    _ensure_not_stoplisted(
        session,
        profile,
        value=request.canonical_value,
        target="canonical",
        entity_name="Canonical term",
    )

    try:
        term = add_term(
            session,
            profile_name,
            request.canonical_value,
            slot=request.slot,
            description=request.description,
            status=request.status,
            tags=request.tags,
            actor="api",
        )
        session.commit()
        session.refresh(term)
        term.aliases.sort(key=lambda alias: alias.normalized_alias)
        term.tags.sort(key=lambda tag: tag.normalized_value)
        return _term_response(term)
    except GovernanceCliError as exc:
        session.rollback()
        status_code = (
            status.HTTP_404_NOT_FOUND
            if str(exc).startswith("Profile not found")
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=status_code, detail=str(exc))
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.get(
    "/profiles/{profile_name}/terms/{canonical_value}",
    response_model=TermResponse,
)
def get_profile_term(
    profile_name: str,
    canonical_value: str,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> TermResponse:
    """Return a canonical term and its aliases."""

    profile = _get_profile_or_404(session, profile_name)
    try:
        term = get_term(session, profile, canonical_value)
    except GovernanceCliError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    term.aliases.sort(key=lambda alias: alias.normalized_alias)
    term.tags.sort(key=lambda tag: tag.normalized_value)
    return _term_response(term)


@router.patch(
    "/profiles/{profile_name}/terms/{canonical_value}",
    response_model=TermResponse,
)
def update_profile_term(
    profile_name: str,
    canonical_value: str,
    request: TermUpdateRequest,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> TermResponse:
    """Update a canonical term inside a terminology profile."""

    profile = _get_profile_or_404(session, profile_name)
    try:
        term = get_term(session, profile, canonical_value)
    except GovernanceCliError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    fields = request.model_fields_set

    if "status" in fields and request.status is not None:
        _validate_status(request.status, TERM_STATUSES, "term")
        term.status = request.status

    if "canonical_value" in fields and request.canonical_value is not None:
        _ensure_not_stoplisted(
            session,
            profile,
            value=request.canonical_value,
            target="canonical",
            entity_name="Canonical term",
        )
        normalized_value = normalize_value(request.canonical_value)
        existing = session.scalar(
            select(CanonicalTerm).where(
                CanonicalTerm.profile_id == profile.id,
                CanonicalTerm.normalized_value == normalized_value,
                CanonicalTerm.id != term.id,
            )
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Canonical term already exists in profile {profile.name!r}: "
                    f"{request.canonical_value}"
                ),
            )
        term.canonical_value = request.canonical_value

    if "slot" in fields and request.slot is not None:
        term.slot = request.slot

    if "description" in fields:
        term.description = request.description

    if "tags" in fields:
        set_term_tags(session, term, request.tags or [])

    try:
        session.commit()
        session.refresh(term)
        term.aliases.sort(key=lambda alias: alias.normalized_alias)
        term.tags.sort(key=lambda tag: tag.normalized_value)
        return _term_response(term)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.delete(
    "/profiles/{profile_name}/terms/{canonical_value}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_profile_term(
    profile_name: str,
    canonical_value: str,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> Response:
    """Delete a canonical term and its aliases."""

    profile = _get_profile_or_404(session, profile_name)
    try:
        term = get_term(session, profile, canonical_value)
    except GovernanceCliError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    session.delete(term)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/profiles/{profile_name}/terms/{canonical_value}/aliases",
    response_model=AliasResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_term_alias(
    profile_name: str,
    canonical_value: str,
    request: AliasCreateRequest,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> AliasResponse:
    """Add an alias to a canonical term."""

    profile = _get_profile_or_404(session, profile_name)
    _ensure_not_stoplisted(
        session,
        profile,
        value=request.alias_value,
        target="alias",
        entity_name="Alias",
    )

    try:
        alias = add_alias(
            session,
            profile_name,
            canonical_value,
            request.alias_value,
            confidence=request.confidence,
            status=request.status,
            notes=request.notes,
            context_triggers=request.context_triggers,
            actor="api",
        )
        session.commit()
        session.refresh(alias)
        return _alias_response(alias)
    except GovernanceCliError as exc:
        session.rollback()
        message = str(exc)
        status_code = (
            status.HTTP_404_NOT_FOUND
            if message.startswith("Profile not found")
            or message.startswith("Canonical term not found")
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=status_code, detail=message)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.patch(
    "/profiles/{profile_name}/terms/{canonical_value}/aliases/{alias_id}",
    response_model=AliasResponse,
)
def update_term_alias(
    profile_name: str,
    canonical_value: str,
    alias_id: int,
    request: AliasUpdateRequest,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> AliasResponse:
    """Update an alias attached to a canonical term."""

    profile = _get_profile_or_404(session, profile_name)
    try:
        term = get_term(session, profile, canonical_value)
    except GovernanceCliError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    alias = _get_alias_or_404(session, term, alias_id)

    fields = request.model_fields_set

    if "status" in fields and request.status is not None:
        _validate_status(request.status, ALIAS_STATUSES, "alias")
        alias.status = request.status

    if "alias_value" in fields and request.alias_value is not None:
        _ensure_not_stoplisted(
            session,
            profile,
            value=request.alias_value,
            target="alias",
            entity_name="Alias",
        )
        normalized_alias = normalize_value(request.alias_value)
        existing = session.scalar(
            select(TermAlias).where(
                TermAlias.profile_id == profile.id,
                TermAlias.normalized_alias == normalized_alias,
                TermAlias.id != alias.id,
            )
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Alias already exists in profile {profile.name!r}: {request.alias_value}",
            )
        alias.alias_value = request.alias_value

    if "confidence" in fields and request.confidence is not None:
        alias.confidence = request.confidence

    if "notes" in fields:
        alias.notes = request.notes

    if "context_triggers" in fields and request.context_triggers is not None:
        alias.context_triggers = _normalize_context_triggers(request.context_triggers)

    try:
        session.commit()
        session.refresh(alias)
        return _alias_response(alias)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.delete(
    "/profiles/{profile_name}/terms/{canonical_value}/aliases/{alias_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_term_alias(
    profile_name: str,
    canonical_value: str,
    alias_id: int,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> Response:
    """Delete an alias attached to a canonical term."""

    profile = _get_profile_or_404(session, profile_name)
    try:
        term = get_term(session, profile, canonical_value)
    except GovernanceCliError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    alias = _get_alias_or_404(session, term, alias_id)
    session.delete(alias)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/proposals/source-quality",
    response_model=list[ProposalSourceQualityResponse],
)
def list_proposal_source_quality(
    profile_name: str | None = Query(default=None, min_length=1, max_length=128),
    proposal_source_type: str | None = Query(default=None, max_length=32),
    proposal_source_name: str | None = Query(default=None, max_length=128),
    _current_user: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> list[ProposalSourceQualityResponse]:
    """Return aggregate quality signals for proposal sources.

    This endpoint is intentionally computed from persisted proposal state rather
    than Prometheus counters, so reviewers can inspect source quality after
    restarts and across manual/agent proposal flows.
    """

    if proposal_source_type is not None:
        _validate_status(
            proposal_source_type,
            PROPOSAL_SOURCE_TYPES,
            "proposal source type",
        )
    rows = build_proposal_source_quality(
        session,
        profile_name=profile_name,
        proposal_source_type=proposal_source_type,
        proposal_source_name=proposal_source_name,
    )
    return [
        ProposalSourceQualityResponse(
            proposal_source_type=row.proposal_source_type,
            proposal_source_name=row.proposal_source_name,
            proposals_total=row.proposals_total,
            pending=row.pending,
            approved=row.approved,
            rejected=row.rejected,
            validation_passed=row.validation_passed,
            validation_warning=row.validation_warning,
            validation_blocked=row.validation_blocked,
            validation_unknown=row.validation_unknown,
            approval_rate=row.approval_rate,
            rejection_rate=row.rejection_rate,
            blocked_rate=row.blocked_rate,
            average_confidence=row.average_confidence,
        )
        for row in rows
    ]


@router.get(
    "/profiles/{profile_name}/ambiguous-aliases",
    response_model=list[AmbiguousAliasResponse],
)
def list_profile_ambiguous_aliases(
    profile_name: str,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> list[AmbiguousAliasResponse]:
    """List ambiguous alias surfaces for one terminology profile."""

    profile = _get_profile_or_404(session, profile_name)
    aliases = list(
        session.scalars(
            select(GovernanceAmbiguousAlias)
            .where(GovernanceAmbiguousAlias.profile_id == profile.id)
            .order_by(
                GovernanceAmbiguousAlias.normalized_surface,
                GovernanceAmbiguousAlias.id,
            )
        )
    )
    return [_ambiguous_alias_response(alias) for alias in aliases]


@router.post(
    "/profiles/{profile_name}/ambiguous-aliases",
    response_model=AmbiguousAliasResponse,
    status_code=status.HTTP_201_CREATED,
)
def upsert_profile_ambiguous_alias(
    profile_name: str,
    request: AmbiguousAliasUpsertRequest,
    response: Response,
    current_user: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> AmbiguousAliasResponse:
    """Create or update an ambiguous alias surface and candidate interpretations."""

    profile = _get_profile_or_404(session, profile_name)
    _validate_ambiguous_alias_status(request.status)
    normalized_surface = normalize_value(request.surface_value)
    ambiguous_alias = session.scalar(
        select(GovernanceAmbiguousAlias).where(
            GovernanceAmbiguousAlias.profile_id == profile.id,
            GovernanceAmbiguousAlias.normalized_surface == normalized_surface,
        )
    )
    response_status = status.HTTP_200_OK
    if ambiguous_alias is None:
        response_status = status.HTTP_201_CREATED
        ambiguous_alias = GovernanceAmbiguousAlias(
            profile=profile,
            surface_value=request.surface_value,
            normalized_surface=normalized_surface,
            status=request.status,
            created_by=current_user.username,
        )
        session.add(ambiguous_alias)
        session.flush()
    else:
        ambiguous_alias.surface_value = request.surface_value
        ambiguous_alias.status = request.status

    if "review_note" in request.model_fields_set:
        ambiguous_alias.review_note = request.review_note
        ambiguous_alias.reviewed_by = current_user.username
        ambiguous_alias.reviewed_at = utc_now()

    _upsert_ambiguous_alias_candidates(
        session,
        profile=profile,
        ambiguous_alias=ambiguous_alias,
        candidates=request.candidates,
    )
    try:
        session.commit()
        session.refresh(ambiguous_alias)
        response.status_code = response_status
        return _ambiguous_alias_response(ambiguous_alias)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.get(
    "/profiles/{profile_name}/ambiguous-aliases/{surface_value}",
    response_model=AmbiguousAliasResponse,
)
def get_profile_ambiguous_alias(
    profile_name: str,
    surface_value: str,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> AmbiguousAliasResponse:
    """Return one ambiguous alias surface by normalized value."""

    profile = _get_profile_or_404(session, profile_name)
    ambiguous_alias = _get_ambiguous_alias_or_404(session, profile, surface_value)
    return _ambiguous_alias_response(ambiguous_alias)


@router.patch(
    "/profiles/{profile_name}/ambiguous-aliases/{surface_value}",
    response_model=AmbiguousAliasResponse,
)
def update_profile_ambiguous_alias(
    profile_name: str,
    surface_value: str,
    request: AmbiguousAliasUpdateRequest,
    current_user: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> AmbiguousAliasResponse:
    """Update ambiguous alias reviewer state without changing candidates."""

    profile = _get_profile_or_404(session, profile_name)
    ambiguous_alias = _get_ambiguous_alias_or_404(session, profile, surface_value)
    if request.surface_value is not None:
        next_normalized = normalize_value(request.surface_value)
        if next_normalized != ambiguous_alias.normalized_surface:
            existing = session.scalar(
                select(GovernanceAmbiguousAlias).where(
                    GovernanceAmbiguousAlias.profile_id == profile.id,
                    GovernanceAmbiguousAlias.normalized_surface == next_normalized,
                    GovernanceAmbiguousAlias.id != ambiguous_alias.id,
                )
            )
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Ambiguous alias already exists in profile {profile.name!r}: "
                        f"{request.surface_value}"
                    ),
                )
            ambiguous_alias.normalized_surface = next_normalized
        ambiguous_alias.surface_value = request.surface_value
    if request.status is not None:
        _validate_ambiguous_alias_status(request.status)
        ambiguous_alias.status = request.status
        ambiguous_alias.reviewed_by = current_user.username
        ambiguous_alias.reviewed_at = utc_now()
    if "review_note" in request.model_fields_set:
        ambiguous_alias.review_note = request.review_note
        ambiguous_alias.reviewed_by = current_user.username
        ambiguous_alias.reviewed_at = utc_now()
    try:
        session.commit()
        session.refresh(ambiguous_alias)
        return _ambiguous_alias_response(ambiguous_alias)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.get(
    "/conflicts",
    response_model=ConflictReportResponse,
)
def list_terminology_conflicts(
    profile_name: str | None = Query(default=None, min_length=1, max_length=128),
    include_suggestions: bool = Query(default=True),
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> ConflictReportResponse:
    """Return a read-only report of terminology conflicts and drift risks."""

    if profile_name is not None:
        _get_profile_or_404(session, profile_name)
    report = build_conflict_report(
        session,
        profile_name=profile_name,
        include_suggestions=include_suggestions,
    )
    return ConflictReportResponse(**report)


@router.patch(
    "/conflicts/{fingerprint}/review",
    response_model=ConflictReportItemResponse,
)
def update_conflict_review_state(
    fingerprint: str,
    request: ConflictReviewUpdateRequest,
    profile_name: str | None = Query(default=None, min_length=1, max_length=128),
    admin_or_moderator: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> ConflictReportItemResponse:
    """Persist reviewer state for a current terminology conflict."""

    if request.severity is not None and request.severity not in CONFLICT_SEVERITIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported conflict severity: {request.severity}",
        )
    if (
        request.review_status is not None
        and request.review_status not in CONFLICT_REVIEW_STATUSES
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported conflict review status: {request.review_status}",
        )
    if profile_name is not None:
        _get_profile_or_404(session, profile_name)

    conflict = find_current_conflict(
        session,
        fingerprint=fingerprint,
        profile_name=profile_name,
        include_suggestions=True,
    )
    if conflict is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Current conflict not found: {fingerprint}",
        )

    review = upsert_conflict_review_state(
        session,
        conflict=conflict,
        severity=request.severity,
        review_status=request.review_status,
        review_note=request.review_note
        if "review_note" in request.model_fields_set
        else None,
        reviewed_by=admin_or_moderator.username,
    )
    session.commit()
    session.refresh(review)
    return ConflictReportItemResponse(
        **merge_conflict_with_review_state(conflict, review)
    )


@router.get(
    "/profiles/{profile_name}/suggestions",
    response_model=list[SuggestionResponse],
)
def list_profile_suggestions(
    profile_name: str,
    status_filter: str | None = Query(default=None, alias="status"),
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> list[SuggestionResponse]:
    """List governance suggestions for a terminology profile."""

    profile = _get_profile_or_404(session, profile_name)
    if status_filter is not None:
        _validate_status(status_filter, SUGGESTION_STATUSES, "suggestion")
    query = select(GovernanceSuggestion).where(
        GovernanceSuggestion.profile_id == profile.id
    )
    if status_filter is not None:
        query = query.where(GovernanceSuggestion.status == status_filter)
    suggestions = list(
        session.scalars(
            query.order_by(
                GovernanceSuggestion.status,
                GovernanceSuggestion.updated_at.desc(),
                GovernanceSuggestion.id.desc(),
            )
        )
    )
    return [_suggestion_response(suggestion) for suggestion in suggestions]


@router.post(
    "/profiles/{profile_name}/canonical-migrations/preview",
    response_model=CanonicalMigrationPlanResponse,
)
def preview_profile_canonical_migration(
    profile_name: str,
    request: CanonicalMigrationCreateRequest,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> CanonicalMigrationPlanResponse:
    """Preview a canonical migration without mutating active terminology."""

    profile = _get_profile_or_404(session, profile_name)
    try:
        plan = build_canonical_migration_plan(
            session,
            profile,
            old_canonical_value=request.old_canonical_value,
            new_canonical_value=request.new_canonical_value,
            slot=request.slot,
            extra_aliases_to_preserve=request.aliases_to_preserve,
            evidence=request.evidence,
        )
    except CanonicalLifecycleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return _canonical_migration_plan_response(plan.to_source_payload())


@router.post(
    "/profiles/{profile_name}/canonical-migrations",
    response_model=SuggestionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_profile_canonical_migration(
    profile_name: str,
    request: CanonicalMigrationCreateRequest,
    response: Response,
    current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> SuggestionResponse:
    """Create a reviewed proposal that migrates one canonical surface to another."""

    profile = _get_profile_or_404(session, profile_name)
    _validate_status(
        request.proposal_source_type,
        PROPOSAL_SOURCE_TYPES,
        "proposal source type",
    )
    binding_id = request.binding_id
    if request.binding_id is not None:
        binding = _get_elasticsearch_binding_or_404(session, request.binding_id)
        if binding.profile_id != profile.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Canonical migration binding must belong to the profile.",
            )
        binding_id = binding.id

    try:
        plan = build_canonical_migration_plan(
            session,
            profile,
            old_canonical_value=request.old_canonical_value,
            new_canonical_value=request.new_canonical_value,
            slot=request.slot,
            extra_aliases_to_preserve=request.aliases_to_preserve,
            evidence=request.evidence,
        )
    except CanonicalLifecycleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    idempotency_key = normalize_idempotency_key(request.idempotency_key)
    try:
        existing_suggestion = resolve_idempotent_suggestion(
            session,
            profile=profile,
            idempotency_key=idempotency_key,
            suggestion_type="canonical_term",
            canonical_value=plan.new_canonical_value,
            alias_value=None,
            slot=plan.slot,
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
        return _suggestion_response(existing_suggestion)

    source_payload = plan.to_source_payload()
    validation_summary = build_canonical_migration_validation_summary(plan)
    validation_summary = ensure_apply_policy_summary(
        validation_summary,
        suggestion_type="canonical_term",
        canonical_value=plan.new_canonical_value,
        alias_value=None,
        slot=plan.slot,
        confidence=request.confidence,
        proposal_source_type=request.proposal_source_type,
        proposal_source_name=request.proposal_source_name,
        source_payload=source_payload,
    )
    suggestion = GovernanceSuggestion(
        profile=profile,
        suggestion_type="canonical_term",
        canonical_value=plan.new_canonical_value,
        alias_value=None,
        slot=plan.slot,
        description=request.description,
        confidence=request.confidence,
        source="discovery",
        context=request.context,
        binding_id=binding_id,
        proposal_source_type=request.proposal_source_type,
        proposal_source_name=request.proposal_source_name,
        idempotency_key=idempotency_key,
        source_payload_json=source_payload,
        validation_summary_json=validation_summary,
        status="pending",
        created_by=current_user.username,
    )
    try:
        session.add(suggestion)
        session.commit()
        session.refresh(suggestion)
        record_proposal_submission(
            source_type=suggestion.proposal_source_type,
            suggestion_type=suggestion.suggestion_type,
            validation_status=validation_status(suggestion.validation_summary_json),
            outcome="created",
        )
        return _suggestion_response(suggestion)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.post(
    "/profiles/{profile_name}/suggestions",
    response_model=SuggestionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_profile_suggestion(
    profile_name: str,
    request: SuggestionCreateRequest,
    response: Response,
    current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> SuggestionResponse:
    """Create a pending governance suggestion without mutating active terms."""

    profile = _get_profile_or_404(session, profile_name)
    _validate_status(request.source, SUGGESTION_SOURCES, "suggestion source")
    _validate_status(request.suggestion_type, SUGGESTION_TYPES, "suggestion type")
    _validate_status(
        request.proposal_source_type,
        PROPOSAL_SOURCE_TYPES,
        "proposal source type",
    )

    binding_id = request.binding_id
    if request.binding_id is not None:
        binding = _get_elasticsearch_binding_or_404(session, request.binding_id)
        if binding.profile_id != profile.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Proposal binding must belong to the suggestion profile.",
            )
        binding_id = binding.id

    idempotency_key = normalize_idempotency_key(request.idempotency_key)
    try:
        existing_suggestion = resolve_idempotent_suggestion(
            session,
            profile=profile,
            idempotency_key=idempotency_key,
            suggestion_type=request.suggestion_type,
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
        return _suggestion_response(existing_suggestion)

    if request.suggestion_type == "alias":
        if request.alias_value is None or not request.alias_value.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Alias suggestions require alias_value.",
            )
        _ensure_not_stoplisted(
            session,
            profile,
            value=request.alias_value,
            target="alias",
            entity_name="Alias suggestion",
        )
    elif request.suggestion_type == "canonical_term":
        _ensure_not_stoplisted(
            session,
            profile,
            value=request.canonical_value,
            target="canonical",
            entity_name="Canonical term suggestion",
        )
        if request.alias_value is not None and request.alias_value.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Canonical term suggestions must not include alias_value.",
            )
        existing = session.scalar(
            select(CanonicalTerm).where(
                CanonicalTerm.profile_id == profile.id,
                CanonicalTerm.normalized_value
                == normalize_value(request.canonical_value),
            )
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Canonical term already exists in profile {profile.name!r}: "
                    f"{request.canonical_value}"
                ),
            )

    validation_summary = request.validation_summary
    if validation_summary is None:
        validation_summary = build_proposal_validation_summary(
            session,
            profile,
            suggestion_type=request.suggestion_type,
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
                suggestion_type=request.suggestion_type,
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
            return _suggestion_response(existing_suggestion)

    validation_summary = ensure_apply_policy_summary(
        validation_summary,
        suggestion_type=request.suggestion_type,
        canonical_value=request.canonical_value,
        alias_value=request.alias_value,
        slot=request.slot,
        confidence=request.confidence,
        proposal_source_type=request.proposal_source_type,
        proposal_source_name=request.proposal_source_name,
        source_payload=request.source_payload,
    )

    suggestion = GovernanceSuggestion(
        profile=profile,
        suggestion_type=request.suggestion_type,
        canonical_value=request.canonical_value,
        alias_value=request.alias_value,
        slot=request.slot,
        description=request.description,
        confidence=request.confidence,
        source=request.source,
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
        record_proposal_submission(
            source_type=suggestion.proposal_source_type,
            suggestion_type=suggestion.suggestion_type,
            validation_status=validation_status(suggestion.validation_summary_json),
            outcome="created",
        )
        return _suggestion_response(suggestion)
    except IntegrityError as exc:
        session.rollback()
        try:
            existing_suggestion = resolve_idempotent_suggestion(
                session,
                profile=profile,
                idempotency_key=idempotency_key,
                suggestion_type=request.suggestion_type,
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
            return _suggestion_response(existing_suggestion)
        raise _integrity_conflict(exc) from exc


@router.post(
    "/profiles/{profile_name}/suggestions/{suggestion_id}/evidence/refresh",
    response_model=SuggestionResponse,
)
def refresh_suggestion_evidence(
    profile_name: str,
    suggestion_id: int,
    request_body: SuggestionEvidenceRefreshRequest,
    request: Request,
    current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> SuggestionResponse:
    """Refresh and save an Elasticsearch evidence snapshot for a pending suggestion."""

    profile = _get_profile_or_404(session, profile_name)
    suggestion = _get_suggestion_or_404(session, profile, suggestion_id)
    _ensure_pending_suggestion(suggestion)

    binding = _get_elasticsearch_binding_or_404(session, request_body.binding_id)
    if binding.profile_id != profile.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Evidence binding must belong to the suggestion profile.",
        )

    query = request_body.query
    if query is None:
        query = suggestion.alias_value or suggestion.canonical_value

    evidence_response = _build_elasticsearch_evidence_response(
        request=request,
        session=session,
        binding=binding,
        request_body=ElasticsearchEvidenceRequest(
            query=query,
            canonical_value=suggestion.canonical_value,
            max_documents=request_body.max_documents,
            context_chars=request_body.context_chars,
        ),
    )

    suggestion.evidence_snapshot = _suggestion_evidence_snapshot(evidence_response)
    suggestion.evidence_checked_by = current_user.username
    suggestion.evidence_checked_at = utc_now()

    session.commit()
    session.refresh(suggestion)
    return _suggestion_response(suggestion)


@router.post(
    "/profiles/{profile_name}/suggestions/{suggestion_id}/approve",
    response_model=SuggestionResponse,
)
def approve_profile_suggestion(
    profile_name: str,
    suggestion_id: int,
    request: SuggestionReviewRequest | None = Body(default=None),
    reviewer: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> SuggestionResponse:
    """Approve a pending suggestion and create an active alias."""

    request = request or SuggestionReviewRequest()
    profile = _get_profile_or_404(session, profile_name)
    suggestion = _get_suggestion_or_404(session, profile, suggestion_id)
    _ensure_pending_suggestion(suggestion)
    _ensure_suggestion_lifecycle_allows_approval(
        suggestion, allow_warnings=request.allow_warnings
    )

    if is_canonical_migration_suggestion(suggestion):
        _approve_canonical_migration_suggestion(session, profile, suggestion)
    elif suggestion.suggestion_type == "alias":
        _approve_alias_suggestion(session, profile, suggestion)
    elif suggestion.suggestion_type == "canonical_term":
        _approve_canonical_term_suggestion(session, profile, suggestion)
    else:  # pragma: no cover - guarded by database/API validation
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid suggestion type: {suggestion.suggestion_type}",
        )

    suggestion.status = "approved"
    suggestion.reviewed_by = reviewer.username
    suggestion.review_comment = request.review_comment
    suggestion.reviewed_at = utc_now()
    update_review_dataset_events_for_suggestion(
        session,
        suggestion,
        decision="approved",
        reviewer=reviewer.username,
        review_comment=request.review_comment,
    )

    try:
        session.commit()
        session.refresh(suggestion)
        record_proposal_review(
            source_type=suggestion.proposal_source_type,
            decision="approved",
        )
        return _suggestion_response(suggestion)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.post(
    "/profiles/{profile_name}/suggestions/{suggestion_id}/reject",
    response_model=SuggestionResponse,
)
def reject_profile_suggestion(
    profile_name: str,
    suggestion_id: int,
    request: SuggestionReviewRequest | None = Body(default=None),
    reviewer: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> SuggestionResponse:
    """Reject a pending alias suggestion without changing active aliases."""

    request = request or SuggestionReviewRequest()
    profile = _get_profile_or_404(session, profile_name)
    suggestion = _get_suggestion_or_404(session, profile, suggestion_id)
    _ensure_pending_suggestion(suggestion)

    suggestion.status = "rejected"
    suggestion.reviewed_by = reviewer.username
    suggestion.review_comment = request.review_comment
    suggestion.reviewed_at = utc_now()
    update_review_dataset_events_for_suggestion(
        session,
        suggestion,
        decision="rejected",
        reviewer=reviewer.username,
        review_comment=request.review_comment,
    )

    session.commit()
    session.refresh(suggestion)
    record_proposal_review(
        source_type=suggestion.proposal_source_type,
        decision="rejected",
    )
    return _suggestion_response(suggestion)


@router.post(
    "/profiles/{profile_name}/suggestions/apply-batch/preview",
    response_model=ProposalBatchPreviewResponse,
)
def preview_profile_suggestion_batch(
    profile_name: str,
    request: ProposalBatchApplyRequest | None = Body(default=None),
    _reviewer: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> ProposalBatchPreviewResponse:
    """Preview a proposal batch without mutating terms, aliases, or snapshots."""

    request = request or ProposalBatchApplyRequest()
    profile = _get_profile_or_404(session, profile_name)
    binding = None
    if request.publish_snapshot and request.binding_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="publish_snapshot requires binding_id.",
        )
    if request.binding_id is not None:
        binding = _get_elasticsearch_binding_or_404(session, request.binding_id)
        if binding.profile_id != profile.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Proposal batch binding must belong to the profile.",
            )

    suggestions = _pending_suggestions_for_batch(
        session=session,
        profile=profile,
        suggestion_ids=request.suggestion_ids,
    )
    requested_ids = (
        list(dict.fromkeys(request.suggestion_ids))
        if request.suggestion_ids is not None
        else [suggestion.id for suggestion in suggestions]
    )
    return _proposal_batch_preview_response(
        profile=profile,
        request=request,
        requested_ids=requested_ids,
        suggestions=suggestions,
        binding_id=binding.id if binding is not None else None,
    )


@router.post(
    "/profiles/{profile_name}/suggestions/apply-batch",
    response_model=ProposalBatchApplyResponse,
)
def apply_profile_suggestion_batch(
    profile_name: str,
    request: ProposalBatchApplyRequest | None = Body(default=None),
    reviewer: AuthContext = Depends(require_roles("admin")),
    session: Session = Depends(get_session),
) -> ProposalBatchApplyResponse:
    """Apply pending proposals as one atomic batch and optionally publish a snapshot.

    This endpoint is the headless proposal release path: agents and tools submit
    pending suggestions, then a moderator/admin applies a reviewed set in one
    transaction. When requested, the same transaction pins a fresh runtime
    snapshot on the target binding.
    """

    request = request or ProposalBatchApplyRequest()
    profile = _get_profile_or_404(session, profile_name)
    binding = None
    if request.publish_snapshot and request.binding_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="publish_snapshot requires binding_id.",
        )
    if request.binding_id is not None:
        binding = _get_elasticsearch_binding_or_404(session, request.binding_id)
        if binding.profile_id != profile.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Proposal batch binding must belong to the profile.",
            )

    suggestions = _suggestions_for_batch_apply(
        session=session,
        profile=profile,
        suggestion_ids=request.suggestion_ids,
    )
    if not suggestions:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No pending suggestions are available for this batch.",
        )

    _ensure_batch_suggestions_are_applyable(
        suggestions, allow_warnings=request.allow_warnings
    )

    created_terms = 0
    created_aliases = 0
    migrated_canonicals = 0
    idempotent_suggestion_ids: list[int] = []
    now = utc_now()
    for suggestion in _ordered_suggestions_for_apply(suggestions):
        if suggestion.status == "approved":
            idempotent_suggestion_ids.append(suggestion.id)
            continue
        apply_result = _apply_suggestion_idempotently(session, profile, suggestion)
        if apply_result == "created_term":
            created_terms += 1
        elif apply_result == "created_alias":
            created_aliases += 1
        elif apply_result == "migrated_canonical":
            migrated_canonicals += 1
        elif apply_result == "idempotent_noop":
            idempotent_suggestion_ids.append(suggestion.id)
        else:  # pragma: no cover - guarded by helper return values
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Invalid proposal apply result: {apply_result}",
            )
        suggestion.status = "approved"
        suggestion.reviewed_by = reviewer.username
        suggestion.review_comment = request.review_comment
        suggestion.reviewed_at = now
        update_review_dataset_events_for_suggestion(
            session,
            suggestion,
            decision="batch_approved",
            reviewer=reviewer.username,
            review_comment=request.review_comment,
        )

    snapshot_response = ProposalBatchSnapshotResponse(published=False)
    if request.publish_snapshot and binding is not None:
        session.flush()
        snapshot_payload = publish_binding_runtime_snapshot(
            session,
            binding,
            snapshot_version=request.snapshot_version,
        )
        snapshot_response = ProposalBatchSnapshotResponse(
            published=True,
            binding_id=binding.id,
            snapshot_version=str(snapshot_payload.get("version") or ""),
            snapshot_status=binding_snapshot_status(binding),
            checksum=str(snapshot_payload.get("checksum") or ""),
            alias_entries_total=len(alias_tuples_from_snapshot(snapshot_payload)),
        )

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc

    record_proposal_batch_apply(
        status="applied",
        publish_snapshot=request.publish_snapshot,
        suggestions_count=len(suggestions),
    )
    for suggestion in suggestions:
        record_proposal_review(
            source_type=suggestion.proposal_source_type,
            decision="batch_approved",
        )

    for suggestion in suggestions:
        session.refresh(suggestion)
    if binding is not None:
        session.refresh(binding)
        if snapshot_response.published:
            snapshot_response = ProposalBatchSnapshotResponse(
                published=True,
                binding_id=binding.id,
                snapshot_version=binding.last_successful_snapshot_version,
                snapshot_status=binding_snapshot_status(binding),
                checksum=str(
                    (binding.runtime_snapshot_json or {}).get("checksum") or ""
                ),
                alias_entries_total=len(
                    alias_tuples_from_snapshot(binding.runtime_snapshot_json)
                ),
            )

    requested_ids = (
        list(dict.fromkeys(request.suggestion_ids))
        if request.suggestion_ids is not None
        else [suggestion.id for suggestion in suggestions]
    )
    response_status = (
        "idempotent"
        if len(idempotent_suggestion_ids) == len(suggestions)
        else "applied"
    )
    return ProposalBatchApplyResponse(
        status=response_status,
        profile_name=profile.name,
        normalized_profile_name=profile.normalized_name,
        requested_suggestion_ids=requested_ids,
        applied_suggestion_ids=[suggestion.id for suggestion in suggestions],
        idempotent_suggestion_ids=idempotent_suggestion_ids,
        created_terms=created_terms,
        created_aliases=created_aliases,
        migrated_canonicals=migrated_canonicals,
        snapshot=snapshot_response,
        suggestions=[_suggestion_response(suggestion) for suggestion in suggestions],
    )


@router.post(
    "/profiles/{profile_name}/snapshot/export",
    response_model=RuntimeSnapshotResponse,
)
def export_profile_snapshot(
    profile_name: str,
    request: SnapshotExportRequest | None = Body(default=None),
    _publisher: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> dict:
    """Build and return a runtime-compatible snapshot for a profile.

    The endpoint does not write files or publish state. It returns the same
    snapshot shape that the runtime packages can consume through
    ``--profile-file`` or ``load_attribute_profile(...)``.
    """

    request = request or SnapshotExportRequest()
    try:
        return build_snapshot(
            session,
            profile_name,
            snapshot_version=request.snapshot_version,
            description=request.description,
        )
    except GovernanceCliError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _active_alias_entries_for_profile(
    session: Session, profile: TerminologyProfile
) -> list[tuple[str, str, str, float]]:
    """Return active alias rows not blocked by profile/global stop-list entries."""

    blocked_alias_values = _active_stop_values_for_target(
        session, profile, targets=("alias", "both")
    ) | _active_global_stop_values_for_target(session, targets=("alias", "both"))
    blocked_canonical_values = _active_stop_values_for_target(
        session, profile, targets=("canonical", "both")
    ) | _active_global_stop_values_for_target(session, targets=("canonical", "both"))
    aliases = list(
        session.scalars(
            select(TermAlias)
            .join(CanonicalTerm)
            .where(
                TermAlias.profile_id == profile.id,
                TermAlias.status == "active",
                CanonicalTerm.status == "active",
            )
            .order_by(TermAlias.normalized_alias)
        )
    )
    entries: list[tuple[str, str, str, float]] = []
    for alias in aliases:
        if alias.normalized_alias in blocked_alias_values:
            continue
        if alias.term.normalized_value in blocked_canonical_values:
            continue
        entries.append(
            (
                alias.normalized_alias,
                alias.term.canonical_value,
                alias.term.slot,
                alias.confidence,
            )
        )
    return entries


def _active_stop_values_for_target(
    session: Session, profile: TerminologyProfile, *, targets: tuple[str, ...]
) -> set[str]:
    values = session.scalars(
        select(GovernanceStopListEntry.normalized_value).where(
            GovernanceStopListEntry.profile_id == profile.id,
            GovernanceStopListEntry.is_active.is_(True),
            GovernanceStopListEntry.target.in_(targets),
        )
    )
    return set(values)


def _active_global_stop_values_for_target(
    session: Session, *, targets: tuple[str, ...]
) -> set[str]:
    values = session.scalars(
        select(GovernanceGlobalStopListEntry.normalized_value).where(
            GovernanceGlobalStopListEntry.is_active.is_(True),
            GovernanceGlobalStopListEntry.target.in_(targets),
        )
    )
    return set(values)


def _build_elasticsearch_evidence_response(
    *,
    request: Request,
    session: Session,
    binding: ElasticsearchBinding,
    request_body: ElasticsearchEvidenceRequest,
) -> ElasticsearchEvidenceResponse:
    if not binding.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Elasticsearch binding is disabled.",
        )

    normalized_query = normalize_value(request_body.query)
    if not normalized_query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Evidence query must contain at least one non-space character.",
        )

    client = ElasticsearchDiscoveryClient(request.app.state.config)
    if not client.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Elasticsearch URL is not configured.",
        )

    try:
        hits = client.search_evidence_documents(
            index_name=binding.index_name,
            text_fields=list(binding.text_fields),
            query_text=request_body.query.strip(),
            limit=request_body.max_documents,
            filter_field=binding.filter_field,
            filter_value=binding.filter_value,
            timestamp_field=binding.timestamp_field,
            time_window_days=binding.time_window_days,
        )
    except ElasticsearchDiscoveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    documents: list[ElasticsearchEvidenceDocument] = []
    for hit in hits:
        document = _first_evidence_document_for_hit(
            hit_id=hit.id,
            hit_index=hit.index,
            source=hit.source,
            text_fields=list(binding.text_fields),
            query=request_body.query.strip(),
            context_chars=request_body.context_chars,
        )
        if document is not None:
            documents.append(document)
        if len(documents) >= request_body.max_documents:
            break

    warnings = _evidence_warnings(
        session=session,
        binding=binding,
        normalized_query=normalized_query,
        hits_count=len(hits),
        documents_count=len(documents),
    )
    risk_findings = scan_untrusted_payload(
        {
            "query": request_body.query.strip(),
            "canonical_value": request_body.canonical_value,
            "documents": [document.model_dump(mode="json") for document in documents],
        },
        base_path="evidence",
    )
    if risk_findings:
        warnings.append(
            "Prompt-like or tool-like instruction text was found in evidence snippets; treat findings as untrusted data for review."
        )

    return ElasticsearchEvidenceResponse(
        binding=_elasticsearch_binding_response(binding),
        query=request_body.query.strip(),
        normalized_query=normalized_query,
        canonical_value=request_body.canonical_value,
        max_documents=request_body.max_documents,
        documents=documents,
        warnings=warnings,
        risk_findings=[finding.to_dict() for finding in risk_findings],
    )


def _suggestion_evidence_snapshot(
    evidence_response: ElasticsearchEvidenceResponse,
) -> dict[str, object]:
    binding = evidence_response.binding
    return {
        "binding_id": binding.id,
        "binding_name": binding.name,
        "index_name": binding.index_name,
        "profile_name": binding.profile_name,
        "query": evidence_response.query,
        "normalized_query": evidence_response.normalized_query,
        "canonical_value": evidence_response.canonical_value,
        "max_documents": evidence_response.max_documents,
        "documents": [
            document.model_dump(mode="json") for document in evidence_response.documents
        ],
        "warnings": list(evidence_response.warnings),
        "risk_findings": [
            finding.model_dump(mode="json")
            for finding in evidence_response.risk_findings
        ],
    }


def _first_evidence_document_for_hit(
    *,
    hit_id: str,
    hit_index: str,
    source: dict[str, object],
    text_fields: list[str],
    query: str,
    context_chars: int,
) -> ElasticsearchEvidenceDocument | None:
    for field in text_fields:
        for value in get_source_values(source, field):
            fragment = _evidence_fragment(
                value, query=query, context_chars=context_chars
            )
            if fragment is None:
                continue
            return ElasticsearchEvidenceDocument(
                document_id=hit_id,
                index_name=hit_index,
                field=field,
                fragment=fragment["fragment"],
                highlighted_fragment=fragment["highlighted_fragment"],
                matched_text=fragment["matched_text"],
                match_start=fragment["match_start"],
                match_end=fragment["match_end"],
            )
    return None


def _evidence_fragment(
    text: str, *, query: str, context_chars: int
) -> dict[str, object] | None:
    pattern = re.compile(rf"(?<!\w){re.escape(query)}(?!\w)", re.IGNORECASE)
    match = pattern.search(text)
    if match is None:
        return None

    fragment_start = max(0, match.start() - context_chars)
    fragment_end = min(len(text), match.end() + context_chars)
    prefix = "…" if fragment_start > 0 else ""
    suffix = "…" if fragment_end < len(text) else ""
    core = text[fragment_start:fragment_end]
    match_start = len(prefix) + match.start() - fragment_start
    match_end = len(prefix) + match.end() - fragment_start
    fragment = f"{prefix}{core}{suffix}"
    highlighted_fragment = (
        html.escape(fragment[:match_start])
        + "<mark>"
        + html.escape(fragment[match_start:match_end])
        + "</mark>"
        + html.escape(fragment[match_end:])
    )
    return {
        "fragment": fragment,
        "highlighted_fragment": highlighted_fragment,
        "matched_text": match.group(0),
        "match_start": match_start,
        "match_end": match_end,
    }


def _evidence_warnings(
    *,
    session: Session,
    binding: ElasticsearchBinding,
    normalized_query: str,
    hits_count: int,
    documents_count: int,
) -> list[str]:
    warnings: list[str] = []
    if hits_count == 0:
        warnings.append("No Elasticsearch documents matched this evidence query.")
    elif documents_count == 0:
        warnings.append(
            "Elasticsearch returned candidates, but no exact literal evidence matches were found."
        )

    blocked_alias_values = _active_stop_values_for_target(
        session, binding.profile, targets=("alias", "both")
    ) | _active_global_stop_values_for_target(session, targets=("alias", "both"))
    blocked_canonical_values = _active_stop_values_for_target(
        session, binding.profile, targets=("canonical", "both")
    ) | _active_global_stop_values_for_target(session, targets=("canonical", "both"))
    if normalized_query in blocked_alias_values:
        warnings.append("Evidence query is blocked as an alias by an active stop list.")
    if normalized_query in blocked_canonical_values:
        warnings.append(
            "Evidence query is blocked as a canonical value by an active stop list."
        )
    return warnings


def _match_alias_entries(
    text: str, alias_entries: list[tuple[str, str, str, float]]
) -> list[ElasticsearchDryRunMatchedAlias]:
    normalized_text = normalize_value(text)
    matches: list[ElasticsearchDryRunMatchedAlias] = []
    seen: set[tuple[str, str, str]] = set()
    for alias_value, canonical_value, slot, confidence in alias_entries:
        if not alias_value or not _contains_alias(normalized_text, alias_value):
            continue
        key = (alias_value, canonical_value, slot)
        if key in seen:
            continue
        seen.add(key)
        matches.append(
            ElasticsearchDryRunMatchedAlias(
                alias_value=alias_value,
                canonical_value=canonical_value,
                slot=slot,
                matched_text=alias_value,
                confidence=confidence,
            )
        )
    return matches


def _contains_alias(normalized_text: str, normalized_alias: str) -> bool:
    import re

    return (
        re.search(rf"(?<!\w){re.escape(normalized_alias)}(?!\w)", normalized_text)
        is not None
    )


def _dry_run_payload(
    binding: ElasticsearchBinding,
    matches: list[ElasticsearchDryRunMatchedAlias],
    *,
    snapshot_version: str | None = None,
) -> dict[str, object]:
    canonical_values = sorted({match.canonical_value for match in matches})
    slots: dict[str, set[str]] = {}
    matched_aliases_by_value: dict[str, set[str]] = {}
    for match in matches:
        slots.setdefault(match.slot, set()).add(match.canonical_value)
        matched_aliases_by_value.setdefault(match.canonical_value, set()).add(
            match.alias_value
        )
    return {
        "profile_id": binding.profile.name,
        "binding_id": binding.id,
        "binding_name": binding.name,
        "snapshot_version": snapshot_version,
        "canonical_values": canonical_values,
        "slots": {slot: sorted(values) for slot, values in sorted(slots.items())},
        "matched_aliases": sorted({match.alias_value for match in matches}),
        "matched_aliases_by_value": {
            value: sorted(aliases)
            for value, aliases in sorted(matched_aliases_by_value.items())
        },
    }


ACTIVE_ENRICHMENT_JOB_STATUSES = {
    "queued",
    "running",
    "pause_requested",
    "paused",
    "cancel_requested",
}


def _active_elasticsearch_enrichment_job_for_binding(
    session: Session, *, binding_id: int
) -> ElasticsearchEnrichmentJob | None:
    """Return the newest active enrichment job for a binding, if one exists."""

    return session.scalar(
        select(ElasticsearchEnrichmentJob)
        .where(
            ElasticsearchEnrichmentJob.binding_id == binding_id,
            ElasticsearchEnrichmentJob.status.in_(
                tuple(ACTIVE_ENRICHMENT_JOB_STATUSES)
            ),
        )
        .order_by(
            ElasticsearchEnrichmentJob.created_at.desc(),
            ElasticsearchEnrichmentJob.id.desc(),
        )
    )


def _build_elasticsearch_enrichment_preflight_response(
    *,
    request: Request,
    session: Session,
    binding: ElasticsearchBinding,
    request_body: ElasticsearchEnrichmentJobCreateRequest,
    snapshot_payload: dict[str, object],
    elasticsearch_configured: bool | None = None,
) -> ElasticsearchEnrichmentPreflightResponse:
    """Build a read-only enrichment safety plan for operators and CI checks."""

    blocking_issues: list[str] = []
    warnings: list[str] = []
    config = request.app.state.config
    if elasticsearch_configured is None:
        elasticsearch_configured = ElasticsearchDiscoveryClient(config).is_configured
    if not elasticsearch_configured:
        blocking_issues.append("Elasticsearch URL is not configured.")

    if not binding.is_enabled:
        blocking_issues.append("Elasticsearch binding is disabled.")
    if binding.mode != "write":
        blocking_issues.append(
            "Elasticsearch binding must be in write mode before starting an enrichment job."
        )

    active_job = _active_elasticsearch_enrichment_job_for_binding(
        session, binding_id=binding.id
    )
    if active_job is not None:
        blocking_issues.append(
            "Another enrichment job is already active for this binding: "
            f"#{active_job.id} ({active_job.status})."
        )

    requested_target_index = _job_target_index(binding, request_body.target_index_name)
    target_index = requested_target_index
    target_index_generated = False
    if binding.write_strategy == "reindex_alias_swap" and not target_index:
        safe_source_index = binding.index_name.strip().lower().replace(" ", "_")
        target_index = f"{safe_source_index}__skeinrank_job_<job_id>"
        target_index_generated = True
    alias_name = _job_alias_name(binding, request_body.alias_name)

    if binding.write_strategy == "reindex_alias_swap":
        if not alias_name:
            blocking_issues.append("Alias name is required for alias-swap jobs.")
        if requested_target_index:
            if requested_target_index == binding.index_name:
                blocking_issues.append(
                    "Target index for reindex_alias_swap must differ from the source index."
                )
            if alias_name and requested_target_index == alias_name:
                blocking_issues.append(
                    "Target index for reindex_alias_swap must differ from the serving alias."
                )
        warnings.append(
            "reindex_alias_swap creates a fresh target index and swaps the serving alias only after enrichment completes."
        )
    elif binding.write_strategy == "in_place":
        warnings.append(
            "in_place writes directly to the configured source index and is not reversible by alias rollback; prefer reindex_alias_swap for production."
        )
    else:
        blocking_issues.append(f"Unsupported write strategy: {binding.write_strategy}")

    if binding.time_window_days and not binding.timestamp_field:
        blocking_issues.append(
            "time_window_days requires timestamp_field before enrichment can run safely."
        )
    if not binding.time_window_days:
        warnings.append(
            "No time window is configured; enrichment may scan the full binding scope."
        )
    if request_body.max_documents >= 10000:
        warnings.append(
            "max_documents is at the API limit; use smaller chunks or a narrower binding filter for first beta runs."
        )

    configured_chunk_size = request_body.chunk_size or min(
        config.enrichment_chunk_size,
        request_body.max_documents,
    )
    if configured_chunk_size > request_body.max_documents:
        blocking_issues.append("chunk_size cannot exceed max_documents.")

    snapshot_aliases_total = len((snapshot_payload or {}).get("alias_entries") or [])
    if snapshot_aliases_total == 0:
        warnings.append(
            "Selected snapshot has no active aliases; enrichment will not add canonical matches."
        )

    confirmation_token_fields = _elasticsearch_enrichment_confirmation_fields(
        binding=binding,
        snapshot_payload=snapshot_payload,
        target_index=target_index,
        alias_name=alias_name,
        max_documents=request_body.max_documents,
        chunk_size=configured_chunk_size,
    )
    confirmation_token = _elasticsearch_enrichment_confirmation_token(
        confirmation_token_fields
    )

    recommended_request = {
        "snapshot_version": str(snapshot_payload.get("version")),
        "max_documents": request_body.max_documents,
        "chunk_size": configured_chunk_size,
        "confirmation_token": confirmation_token,
    }
    if binding.write_strategy == "reindex_alias_swap":
        recommended_request["alias_name"] = alias_name
        if request_body.target_index_name:
            recommended_request["target_index_name"] = requested_target_index
    if binding.write_strategy == "in_place":
        recommended_request["target_index_name"] = binding.index_name

    safety = {
        "job_backend": config.enrichment_jobs_backend,
        "write_strategy": binding.write_strategy,
        "source_index": binding.index_name,
        "target_index": target_index,
        "target_index_generated_after_job_creation": target_index_generated,
        "alias_name": alias_name,
        "snapshot_version": str(snapshot_payload.get("version")),
        "snapshot_aliases_total": snapshot_aliases_total,
        "max_documents": request_body.max_documents,
        "chunk_size": configured_chunk_size,
        "timestamp_field": binding.timestamp_field,
        "time_window_days": binding.time_window_days,
        "active_job_id": active_job.id if active_job is not None else None,
        "active_job_status": active_job.status if active_job is not None else None,
        "confirmation_required": True,
        "confirmation_token_fields": confirmation_token_fields,
    }

    return ElasticsearchEnrichmentPreflightResponse(
        binding=_elasticsearch_binding_response(binding),
        ready=not blocking_issues,
        blocking_issues=blocking_issues,
        warnings=warnings,
        recommended_request=recommended_request,
        safety=safety,
        confirmation_token=confirmation_token,
        confirmation_token_fields=confirmation_token_fields,
    )


def _elasticsearch_enrichment_confirmation_fields(
    *,
    binding: ElasticsearchBinding,
    snapshot_payload: dict[str, object],
    target_index: str | None,
    alias_name: str | None,
    max_documents: int,
    chunk_size: int,
) -> dict[str, object]:
    """Return the exact write plan fields an operator must confirm."""

    return {
        "binding_id": binding.id,
        "binding_name": binding.name,
        "profile_id": binding.profile_id,
        "profile_name": binding.profile.name,
        "write_strategy": binding.write_strategy,
        "source_index": binding.index_name,
        "target_index": target_index,
        "target_field": binding.target_field,
        "alias_name": alias_name,
        "snapshot_version": str(snapshot_payload.get("version")),
        "max_documents": max_documents,
        "chunk_size": chunk_size,
        "filter_field": binding.filter_field,
        "filter_value": binding.filter_value,
        "timestamp_field": binding.timestamp_field,
        "time_window_days": binding.time_window_days,
    }


def _elasticsearch_enrichment_confirmation_token(fields: dict[str, object]) -> str:
    """Build a deterministic token for one preflight-approved write plan."""

    encoded = json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"skeinrank-es-enrichment-v1:{digest}"


def _job_target_index(
    binding: ElasticsearchBinding, target_index_name: str | None
) -> str | None:
    """Return the target index recorded for a new enrichment job."""

    if binding.write_strategy == "in_place":
        return binding.index_name
    if target_index_name:
        return target_index_name.strip()
    return None


def _job_alias_name(
    binding: ElasticsearchBinding, alias_name: str | None
) -> str | None:
    """Return the alias name used by reindex+alias-swap jobs."""

    if binding.write_strategy != "reindex_alias_swap":
        return None
    if alias_name:
        return alias_name.strip()
    return binding.index_name


def _default_reindex_target_name(binding: ElasticsearchBinding, job_id: int) -> str:
    """Build a deterministic target index name for reindex jobs."""

    safe_source_index = binding.index_name.strip().lower().replace(" ", "_")
    return f"{safe_source_index}__skeinrank_job_{job_id}"


def _execute_elasticsearch_enrichment_job(
    *,
    client: ElasticsearchDiscoveryClient,
    session: Session,
    binding: ElasticsearchBinding,
    job: ElasticsearchEnrichmentJob,
    max_documents: int,
) -> dict[str, object]:
    """Execute one synchronous Elasticsearch enrichment job."""

    if binding.write_strategy == "reindex_alias_swap":
        if not job.target_index:
            raise ElasticsearchDiscoveryError(
                "Target index is required for reindex jobs"
            )
        client.create_reindex_target_index(
            source_index=binding.index_name,
            target_index=job.target_index,
        )
        reindex_result = client.reindex_documents(
            source_index=binding.index_name,
            target_index=job.target_index,
            filter_field=binding.filter_field,
            filter_value=binding.filter_value,
            timestamp_field=binding.timestamp_field,
            time_window_days=binding.time_window_days,
        )
        update_index = job.target_index
    elif binding.write_strategy == "in_place":
        reindex_result = None
        update_index = binding.index_name
    else:  # pragma: no cover - guarded by API/model validation
        raise ElasticsearchDiscoveryError(
            f"Unsupported write strategy: {binding.write_strategy}"
        )

    alias_entries = alias_tuples_from_snapshot(job.snapshot_json)
    if not alias_entries:
        alias_entries = _active_alias_entries_for_profile(session, binding.profile)
    hits = client.search_documents(
        index_name=update_index,
        text_fields=list(binding.text_fields),
        limit=max_documents,
        filter_field=binding.filter_field,
        filter_value=binding.filter_value,
        timestamp_field=binding.timestamp_field,
        time_window_days=binding.time_window_days,
    )

    updates: list[tuple[str, dict[str, object]]] = []
    matched_documents: list[dict[str, object]] = []
    for hit in hits:
        text = compose_source_text(hit.source, list(binding.text_fields))
        matched_aliases = _match_alias_entries(text, alias_entries)
        if not matched_aliases:
            continue
        would_write_payload = _dry_run_payload(
            binding, matched_aliases, snapshot_version=job.snapshot_version
        )
        updates.append((hit.id, {binding.target_field: would_write_payload}))
        matched_documents.append(
            {
                "document_id": hit.id,
                "index_name": hit.index,
                "matched_aliases": [
                    {
                        "alias_value": match.alias_value,
                        "canonical_value": match.canonical_value,
                        "slot": match.slot,
                        "matched_text": match.matched_text,
                        "confidence": match.confidence,
                    }
                    for match in matched_aliases
                ],
                "would_write": {binding.target_field: would_write_payload},
            }
        )

    bulk_result = client.bulk_update_documents(index_name=update_index, updates=updates)
    alias_result = None
    rollout_metadata = None
    if binding.write_strategy == "reindex_alias_swap":
        if not job.alias_name:
            raise ElasticsearchDiscoveryError(
                "Alias name is required for alias-swap jobs"
            )
        previous_alias_indices = client.alias_indices(alias_name=job.alias_name)
        rollout_metadata = _build_reindex_rollout_metadata(
            alias_name=job.alias_name,
            source_index=binding.index_name,
            target_index=update_index,
            previous_alias_indices=previous_alias_indices,
        )
        alias_result = client.swap_alias(
            alias_name=job.alias_name,
            target_index=update_index,
        )
        rollout_metadata = _complete_reindex_rollout_metadata(
            rollout_metadata=rollout_metadata,
            alias_result=alias_result,
            new_alias_indices=client.alias_indices(alias_name=job.alias_name),
        )

    return {
        "write_strategy": binding.write_strategy,
        "source_index": binding.index_name,
        "target_index": update_index,
        "alias_name": job.alias_name,
        "snapshot_version": job.snapshot_version,
        "previous_snapshot_version": job.previous_snapshot_version,
        "snapshot_aliases_total": len(
            (job.snapshot_json or {}).get("alias_entries") or []
        ),
        "timestamp_field": binding.timestamp_field,
        "time_window_days": binding.time_window_days,
        "documents_seen": len(hits),
        "documents_enriched": len(updates),
        "documents_failed": 0,
        "updated_document_ids": [document_id for document_id, _document in updates],
        "matched_documents": matched_documents,
        "reindex_result": reindex_result,
        "bulk_result": bulk_result,
        "alias_result": alias_result,
        "rollout": rollout_metadata,
    }


def _rollback_candidate_index(
    previous_alias_indices: list[str], target_index: str
) -> str | None:
    candidates = [index for index in previous_alias_indices if index != target_index]
    if len(candidates) == 1:
        return candidates[0]
    return None


def _build_reindex_rollout_metadata(
    *,
    alias_name: str,
    source_index: str,
    target_index: str,
    previous_alias_indices: list[str],
) -> dict[str, object]:
    rollback_candidate = _rollback_candidate_index(previous_alias_indices, target_index)
    alias_bootstrapped = not previous_alias_indices
    if alias_bootstrapped:
        rollback_hint = (
            "This is the first successful publish for this alias; no previous "
            "alias target exists for automatic rollback."
        )
    elif rollback_candidate:
        rollback_hint = (
            f"Manual rollback candidate: repoint alias {alias_name} "
            f"to {rollback_candidate}."
        )
    else:
        rollback_hint = (
            "No single previous alias index was found for automatic rollback "
            "planning."
        )
    return {
        "strategy": "reindex_alias_swap",
        "status": "prepared",
        "alias_name": alias_name,
        "source_index": source_index,
        "target_index": target_index,
        "previous_alias_indices": previous_alias_indices,
        "new_alias_indices": [],
        "alias_bootstrapped": alias_bootstrapped,
        "rollback_candidate_index": rollback_candidate,
        "rollback_available": rollback_candidate is not None,
        "alias_swap_completed": False,
        "alias_swap_started_at": utc_now().isoformat(),
        "alias_swapped_at": None,
        "alias_result": None,
        "cleanup_hint": (
            "If this rollout is cancelled or fails before alias swap, "
            f"review or delete target index {target_index}."
        ),
        "rollback_hint": rollback_hint,
    }


def _complete_reindex_rollout_metadata(
    *,
    rollout_metadata: dict[str, object],
    alias_result: dict[str, object] | None,
    new_alias_indices: list[str],
) -> dict[str, object]:
    return {
        **rollout_metadata,
        "status": "alias_swapped",
        "new_alias_indices": new_alias_indices,
        "alias_swap_completed": True,
        "alias_swapped_at": utc_now().isoformat(),
        "alias_result": alias_result,
    }


def _validated_rollback_rollout(job: ElasticsearchEnrichmentJob) -> dict[str, object]:
    if job.write_strategy != "reindex_alias_swap":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only reindex_alias_swap jobs can be rolled back.",
        )
    if job.status != "succeeded":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot rollback enrichment job with status: {job.status}",
        )
    result_json = job.result_json or {}
    rollout = result_json.get("rollout")
    if not isinstance(rollout, dict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rollback metadata is not available for this job.",
        )
    if rollout.get("strategy") != "reindex_alias_swap":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rollback metadata does not describe a reindex alias-swap rollout.",
        )
    if rollout.get("rollback_completed") is True or isinstance(
        rollout.get("rollback"), dict
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This enrichment job has already been rolled back.",
        )
    alias_name = rollout.get("alias_name") or job.alias_name
    rollback_candidate = rollout.get("rollback_candidate_index")
    if not isinstance(alias_name, str) or not alias_name.strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rollback alias name is missing.",
        )
    if not isinstance(rollback_candidate, str) or not rollback_candidate.strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rollback candidate index is missing.",
        )
    if rollout.get("alias_swap_completed") is not True:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot rollback before alias swap has completed.",
        )
    if rollout.get("rollback_available") is not True:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rollback is not available for this job.",
        )
    return {
        **rollout,
        "alias_name": alias_name,
        "rollback_candidate_index": rollback_candidate,
    }


def _rollout_expected_current_indices(
    rollout: dict[str, object], job: ElasticsearchEnrichmentJob
) -> list[str]:
    new_alias_indices = rollout.get("new_alias_indices")
    if isinstance(new_alias_indices, list) and new_alias_indices:
        return [str(index) for index in new_alias_indices]
    target_index = rollout.get("target_index") or job.target_index
    if isinstance(target_index, str) and target_index:
        return [target_index]
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Expected post-rollout alias state is missing.",
    )


def _refresh_enrichment_checkpoint(result_json: dict[str, object]) -> dict[str, object]:
    """Return result JSON with operator-facing enrichment checkpoint metadata."""

    chunked_raw = result_json.get("chunked_enrichment")
    if not isinstance(chunked_raw, dict):
        return result_json
    chunked = dict(chunked_raw)
    chunk_specs = [
        dict(item)
        for item in chunked.get("chunk_specs") or []
        if isinstance(item, dict)
    ]
    chunks = [
        dict(item) for item in chunked.get("chunks") or [] if isinstance(item, dict)
    ]

    completed_indices = _chunk_indices_with_status(chunks, "succeeded")
    failed_indices = _chunk_indices_with_status(chunks, "failed")
    cancelled_indices = _chunk_indices_with_status(chunks, "cancelled")
    processed_indices = (
        set(completed_indices) | set(failed_indices) | set(cancelled_indices)
    )
    all_indices = [
        int(spec.get("chunk_index"))
        for spec in chunk_specs
        if spec.get("chunk_index") is not None
    ]
    remaining_indices = [
        index for index in all_indices if index not in processed_indices
    ]

    chunked["chunks_completed"] = len(completed_indices)
    chunked["chunks_failed"] = len(failed_indices)
    chunked["chunks_cancelled"] = len(cancelled_indices)
    chunked["checkpoint"] = {
        "chunks_total": int(chunked.get("chunks_total") or len(all_indices)),
        "completed_chunk_indices": completed_indices,
        "failed_chunk_indices": failed_indices,
        "cancelled_chunk_indices": cancelled_indices,
        "remaining_chunk_indices": remaining_indices,
        "last_completed_chunk_index": completed_indices[-1]
        if completed_indices
        else None,
        "documents_seen": sum(
            int(chunk.get("documents_seen") or 0) for chunk in chunks
        ),
        "documents_enriched": sum(
            int(chunk.get("documents_enriched") or 0) for chunk in chunks
        ),
        "documents_failed": sum(
            int(chunk.get("documents_failed") or 0) for chunk in chunks
        ),
        "updated_at": utc_now().isoformat(),
    }
    return {**result_json, "chunked_enrichment": chunked}


def _chunk_indices_with_status(
    chunks: list[dict[str, object]], status_value: str
) -> list[int]:
    return sorted(
        int(chunk.get("chunk_index"))
        for chunk in chunks
        if chunk.get("status") == status_value and chunk.get("chunk_index") is not None
    )


def _pending_enrichment_chunk_specs(
    result_json: dict[str, object],
) -> list[dict[str, int]]:
    refreshed = _refresh_enrichment_checkpoint(result_json)
    chunked = dict(refreshed.get("chunked_enrichment") or {})
    checkpoint = dict(chunked.get("checkpoint") or {})
    remaining_indices = {
        int(index) for index in checkpoint.get("remaining_chunk_indices") or []
    }
    pending: list[dict[str, int]] = []
    for item in chunked.get("chunk_specs") or []:
        if not isinstance(item, dict) or item.get("chunk_index") is None:
            continue
        chunk_index = int(item["chunk_index"])
        if chunk_index not in remaining_indices:
            continue
        pending.append(
            {
                "chunk_index": chunk_index,
                "offset": int(item.get("offset") or 0),
                "limit": int(item.get("limit") or 0),
            }
        )
    return pending


def _get_elasticsearch_enrichment_job_or_404(
    session: Session, job_id: int
) -> ElasticsearchEnrichmentJob:
    job = session.scalar(
        select(ElasticsearchEnrichmentJob).where(
            ElasticsearchEnrichmentJob.id == job_id
        )
    )
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Elasticsearch enrichment job not found: {job_id}",
        )
    return job


def _elasticsearch_enrichment_job_response(
    job: ElasticsearchEnrichmentJob,
) -> ElasticsearchEnrichmentJobResponse:
    return ElasticsearchEnrichmentJobResponse(
        id=job.id,
        binding_id=job.binding_id,
        profile_id=job.profile_id,
        binding_name=job.binding.name,
        profile_name=job.profile.name,
        status=job.status,
        write_strategy=job.write_strategy,
        source_index=job.source_index,
        target_index=job.target_index,
        alias_name=job.alias_name,
        snapshot_version=job.snapshot_version,
        previous_snapshot_version=job.previous_snapshot_version,
        requested_by=job.requested_by,
        documents_seen=job.documents_seen,
        documents_enriched=job.documents_enriched,
        documents_failed=job.documents_failed,
        result_json=job.result_json or {},
        error_message=job.error_message,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _get_elasticsearch_binding_or_404(
    session: Session, binding_id: int
) -> ElasticsearchBinding:
    binding = session.scalar(
        select(ElasticsearchBinding).where(ElasticsearchBinding.id == binding_id)
    )
    if binding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Elasticsearch binding not found: {binding_id}",
        )
    return binding


def _get_binding_policy_or_404(
    session: Session, binding: ElasticsearchBinding
) -> GovernanceBindingPolicy:
    policy = session.scalar(
        select(GovernanceBindingPolicy).where(
            GovernanceBindingPolicy.binding_id == binding.id
        )
    )
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Binding policy not found for binding: {binding.id}",
        )
    return policy


def _binding_policy_response(policy: GovernanceBindingPolicy) -> BindingPolicyResponse:
    return BindingPolicyResponse(
        id=policy.id,
        binding_id=policy.binding_id,
        profile_id=policy.profile_id,
        profile_name=policy.profile.name,
        binding_name=policy.binding.name,
        status=policy.status,
        preferred_slots=list(policy.preferred_slots or []),
        allowed_tags=list(policy.allowed_tags or []),
        deny_slots=list(policy.deny_slots or []),
        context_rules=list(policy.context_rules or []),
        created_by=policy.created_by,
        updated_by=policy.updated_by,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


def _validate_elasticsearch_binding_provider(provider: str) -> None:
    if provider not in ELASTICSEARCH_BINDING_PROVIDERS:
        allowed_values = ", ".join(ELASTICSEARCH_BINDING_PROVIDERS)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid Elasticsearch binding provider: {provider}. Allowed values: {allowed_values}",
        )


def _validate_elasticsearch_binding_mode(mode: str) -> None:
    if mode not in ELASTICSEARCH_BINDING_MODES:
        allowed_values = ", ".join(ELASTICSEARCH_BINDING_MODES)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid Elasticsearch binding mode: {mode}. Allowed values: {allowed_values}",
        )


def _validate_elasticsearch_binding_write_strategy(write_strategy: str) -> None:
    if write_strategy not in ELASTICSEARCH_BINDING_WRITE_STRATEGIES:
        allowed_values = ", ".join(ELASTICSEARCH_BINDING_WRITE_STRATEGIES)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Invalid Elasticsearch binding write strategy: {write_strategy}. "
                f"Allowed values: {allowed_values}"
            ),
        )


def _normalize_text_fields(text_fields: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for field in text_fields:
        value = field.strip()
        if not value:
            continue
        if value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Elasticsearch binding requires at least one text field.",
        )
    return normalized


def _normalize_optional_filter(
    filter_field: str | None, filter_value: str | None
) -> tuple[str | None, str | None]:
    field = filter_field.strip() if filter_field is not None else None
    value = filter_value.strip() if filter_value is not None else None
    field = field or None
    value = value or None
    if (field is None) != (value is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Elasticsearch binding filter requires both filter_field and filter_value.",
        )
    return field, value


def _normalize_time_filter(
    timestamp_field: str | None, time_window_days: int | None
) -> tuple[str | None, int | None]:
    field = timestamp_field.strip() if timestamp_field is not None else None
    field = field or None
    if time_window_days is not None and field is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Elasticsearch binding time window requires timestamp_field.",
        )
    return field, time_window_days


def _ensure_elasticsearch_binding_name_unique(
    session: Session,
    *,
    normalized_name: str,
    exclude_id: int | None = None,
) -> None:
    query = select(ElasticsearchBinding).where(
        ElasticsearchBinding.normalized_name == normalized_name
    )
    if exclude_id is not None:
        query = query.where(ElasticsearchBinding.id != exclude_id)
    existing = session.scalar(query)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Elasticsearch binding already exists: {existing.name}",
        )


def _get_stop_list_entry_or_404(
    session: Session, profile: TerminologyProfile, entry_id: int
) -> GovernanceStopListEntry:
    entry = session.scalar(
        select(GovernanceStopListEntry).where(
            GovernanceStopListEntry.id == entry_id,
            GovernanceStopListEntry.profile_id == profile.id,
        )
    )
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stop-list entry not found for profile {profile.name!r}: {entry_id}",
        )
    return entry


def _get_global_stop_list_entry_or_404(
    session: Session, entry_id: int
) -> GovernanceGlobalStopListEntry:
    entry = session.scalar(
        select(GovernanceGlobalStopListEntry).where(
            GovernanceGlobalStopListEntry.id == entry_id
        )
    )
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Global stop-list entry not found: {entry_id}",
        )
    return entry


def _ensure_global_stop_list_entry_unique(
    session: Session,
    *,
    normalized_value: str,
    target: str,
    exclude_id: int | None = None,
) -> None:
    query = select(GovernanceGlobalStopListEntry).where(
        GovernanceGlobalStopListEntry.normalized_value == normalized_value
    )
    if exclude_id is not None:
        query = query.where(GovernanceGlobalStopListEntry.id != exclude_id)
    candidates = list(session.scalars(query))
    for entry in candidates:
        if entry.target == target or entry.target == "both" or target == "both":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Global stop-list entry already exists: "
                    f"{entry.value} ({entry.target})"
                ),
            )


def _validate_stop_list_target(target: str) -> None:
    if target not in STOP_LIST_TARGETS:
        allowed_values = ", ".join(STOP_LIST_TARGETS)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid stop-list target: {target}. Allowed values: {allowed_values}",
        )


def _ensure_stop_list_entry_unique(
    session: Session,
    profile: TerminologyProfile,
    *,
    normalized_value: str,
    target: str,
    exclude_id: int | None = None,
) -> None:
    query = select(GovernanceStopListEntry).where(
        GovernanceStopListEntry.profile_id == profile.id,
        GovernanceStopListEntry.normalized_value == normalized_value,
    )
    if exclude_id is not None:
        query = query.where(GovernanceStopListEntry.id != exclude_id)
    candidates = list(session.scalars(query))
    for entry in candidates:
        if entry.target == target or entry.target == "both" or target == "both":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Stop-list entry already exists in profile {profile.name!r}: "
                    f"{entry.value} ({entry.target})"
                ),
            )


def _stop_list_targets_for(target: str) -> tuple[str, ...]:
    if target == "alias":
        return ("alias", "both")
    if target == "canonical":
        return ("canonical", "both")
    return STOP_LIST_TARGETS


def _ensure_not_stoplisted(
    session: Session,
    profile: TerminologyProfile,
    *,
    value: str,
    target: str,
    entity_name: str,
) -> None:
    normalized_value = normalize_value(value)
    target_values = _stop_list_targets_for(target)

    global_entry = session.scalar(
        select(GovernanceGlobalStopListEntry).where(
            GovernanceGlobalStopListEntry.normalized_value == normalized_value,
            GovernanceGlobalStopListEntry.target.in_(target_values),
            GovernanceGlobalStopListEntry.is_active.is_(True),
        )
    )
    if global_entry is not None:
        detail = f"{entity_name} is blocked by global stop list: {value}"
        if global_entry.reason:
            detail = f"{detail}. Reason: {global_entry.reason}"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    profile_entry = session.scalar(
        select(GovernanceStopListEntry).where(
            GovernanceStopListEntry.profile_id == profile.id,
            GovernanceStopListEntry.normalized_value == normalized_value,
            GovernanceStopListEntry.target.in_(target_values),
            GovernanceStopListEntry.is_active.is_(True),
        )
    )
    if profile_entry is None:
        return
    detail = (
        f"{entity_name} is blocked by stop list for profile {profile.name!r}: "
        f"{value}"
    )
    if profile_entry.reason:
        detail = f"{detail}. Reason: {profile_entry.reason}"
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _get_profile_or_404(session: Session, profile_name: str) -> TerminologyProfile:
    try:
        return get_profile(session, profile_name)
    except GovernanceCliError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _get_alias_or_404(
    session: Session, term: CanonicalTerm, alias_id: int
) -> TermAlias:
    alias = session.scalar(
        select(TermAlias).where(
            TermAlias.id == alias_id,
            TermAlias.term_id == term.id,
            TermAlias.profile_id == term.profile_id,
        )
    )
    if alias is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alias not found for canonical term {term.canonical_value!r}: {alias_id}",
        )
    return alias


def _pending_suggestions_for_batch(
    *,
    session: Session,
    profile: TerminologyProfile,
    suggestion_ids: list[int] | None,
) -> list[GovernanceSuggestion]:
    query = select(GovernanceSuggestion).where(
        GovernanceSuggestion.profile_id == profile.id,
        GovernanceSuggestion.status == "pending",
    )
    requested_ids: list[int] | None = None
    if suggestion_ids is not None:
        requested_ids = list(dict.fromkeys(suggestion_ids))
        query = query.where(GovernanceSuggestion.id.in_(requested_ids))

    suggestions = list(
        session.scalars(
            query.order_by(
                GovernanceSuggestion.suggestion_type.desc(),
                GovernanceSuggestion.id,
            )
        )
    )
    if requested_ids is not None:
        found_ids = {suggestion.id for suggestion in suggestions}
        missing_ids = [
            suggestion_id
            for suggestion_id in requested_ids
            if suggestion_id not in found_ids
        ]
        if missing_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Pending suggestions not found for profile {profile.name!r}: "
                    f"{missing_ids}"
                ),
            )
    return suggestions


def _suggestions_for_batch_apply(
    *,
    session: Session,
    profile: TerminologyProfile,
    suggestion_ids: list[int] | None,
) -> list[GovernanceSuggestion]:
    """Return pending plus already-approved suggestions for idempotent apply."""

    if suggestion_ids is None:
        return _pending_suggestions_for_batch(
            session=session, profile=profile, suggestion_ids=None
        )

    requested_ids = list(dict.fromkeys(suggestion_ids))
    suggestions = list(
        session.scalars(
            select(GovernanceSuggestion)
            .where(
                GovernanceSuggestion.profile_id == profile.id,
                GovernanceSuggestion.id.in_(requested_ids),
                GovernanceSuggestion.status.in_(("pending", "approved")),
            )
            .order_by(
                GovernanceSuggestion.suggestion_type.desc(),
                GovernanceSuggestion.id,
            )
        )
    )
    found_ids = {suggestion.id for suggestion in suggestions}
    missing_ids = [
        suggestion_id
        for suggestion_id in requested_ids
        if suggestion_id not in found_ids
    ]
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Pending or approved suggestions not found for profile "
                f"{profile.name!r}: {missing_ids}"
            ),
        )
    return suggestions


def _ordered_suggestions_for_apply(
    suggestions: list[GovernanceSuggestion],
) -> list[GovernanceSuggestion]:
    """Apply canonical-term proposals before alias proposals in one batch."""

    return sorted(
        suggestions,
        key=lambda suggestion: (
            0 if suggestion.suggestion_type == "canonical_term" else 1,
            suggestion.id,
        ),
    )


def _proposal_batch_preview_response(
    *,
    profile: TerminologyProfile,
    request: ProposalBatchApplyRequest,
    requested_ids: list[int],
    suggestions: list[GovernanceSuggestion],
    binding_id: int | None,
) -> ProposalBatchPreviewResponse:
    items = [
        _proposal_batch_preview_item(suggestion, allow_warnings=request.allow_warnings)
        for suggestion in suggestions
    ]
    blocked_suggestions = sum(
        1 for item in items if item.validation_status == "blocked"
    )
    warning_suggestions = sum(
        1 for item in items if item.validation_status == "warning"
    )
    applyable_suggestions = sum(1 for item in items if item.applyable)
    status_value = "ready"
    if not items:
        status_value = "empty"
    elif blocked_suggestions:
        status_value = "blocked"
    elif warning_suggestions and not request.allow_warnings:
        status_value = "needs_review"

    return ProposalBatchPreviewResponse(
        status=status_value,
        profile_name=profile.name,
        normalized_profile_name=profile.normalized_name,
        requested_suggestion_ids=requested_ids,
        suggestions_total=len(items),
        applyable_suggestions=applyable_suggestions,
        blocked_suggestions=blocked_suggestions,
        warning_suggestions=warning_suggestions,
        allow_warnings=request.allow_warnings,
        will_publish_snapshot=request.publish_snapshot,
        binding_id=binding_id,
        snapshot_version=request.snapshot_version,
        items=items,
    )


def _proposal_batch_preview_item(
    suggestion: GovernanceSuggestion, *, allow_warnings: bool
) -> ProposalBatchPreviewItemResponse:
    summary = suggestion.validation_summary_json or {}
    validation_status_value = _proposal_validation_status(summary)
    apply_policy = apply_policy_for_suggestion(suggestion)
    apply_action = (
        "migrate_canonical"
        if is_canonical_migration_suggestion(suggestion)
        else "apply"
    )
    idempotent_reason = None
    if suggestion.status == "approved":
        applyable = True
        apply_action = "idempotent_noop"
        idempotent_reason = "suggestion_already_approved"
    else:
        applyable = validation_status_value != "blocked" and (
            validation_status_value != "warning" or allow_warnings
        )
    return ProposalBatchPreviewItemResponse(
        suggestion_id=suggestion.id,
        suggestion_type=suggestion.suggestion_type,
        canonical_value=suggestion.canonical_value,
        alias_value=suggestion.alias_value,
        slot=suggestion.slot,
        status=suggestion.status,
        validation_status=validation_status_value,
        validation_counts=_proposal_validation_counts(summary),
        risk_level=str(apply_policy.get("risk_level") or "unknown"),
        apply_policy=ProposalApplyPolicyResponse(**apply_policy),
        policy_can_batch_apply=bool(apply_policy.get("can_batch_apply")),
        policy_requires_admin=bool(apply_policy.get("requires_admin")),
        policy_reasons=list(apply_policy.get("reasons") or []),
        applyable=applyable,
        apply_action=apply_action,
        idempotent_reason=idempotent_reason,
        warning_reasons=_proposal_validation_reasons(summary, "warning"),
        blocked_reasons=_proposal_validation_reasons(summary, "blocked"),
        proposal_source_type=suggestion.proposal_source_type,
        proposal_source_name=suggestion.proposal_source_name,
        idempotency_key=suggestion.idempotency_key,
    )


def _proposal_validation_status(summary: object) -> str:
    return proposal_validation_status(summary)


def _proposal_validation_counts(summary: object) -> dict[str, int]:
    return proposal_validation_counts(summary)


def _proposal_validation_reasons(summary: object, expected_status: str) -> list[str]:
    return proposal_validation_reasons(summary, expected_status)


def _ensure_batch_suggestions_are_applyable(
    suggestions: list[GovernanceSuggestion], *, allow_warnings: bool
) -> None:
    blocked_ids: list[int] = []
    warning_ids: list[int] = []
    for suggestion in suggestions:
        if suggestion.status == "approved":
            continue
        validation_status_value = _proposal_validation_status(
            suggestion.validation_summary_json or {}
        )
        if validation_status_value == "blocked":
            blocked_ids.append(suggestion.id)
        elif validation_status_value == "warning":
            warning_ids.append(suggestion.id)
    if blocked_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Proposal batch contains blocked suggestions. "
                f"Review or reject them before applying: {blocked_ids}"
            ),
        )
    if warning_ids and not allow_warnings:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Proposal batch contains suggestions with validation warnings. "
                "Preview the batch, review warnings, or set allow_warnings=true "
                f"to apply them explicitly: {warning_ids}"
            ),
        )


def _ensure_suggestion_lifecycle_allows_approval(
    suggestion: GovernanceSuggestion, *, allow_warnings: bool
) -> None:
    decision = classify_proposal_lifecycle(suggestion)
    if decision.validation_status == "blocked":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Suggestion validation is blocked. Reject or resubmit the "
                f"proposal before approval: {suggestion.id}"
            ),
        )
    if decision.requires_warning_override and not allow_warnings:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Suggestion validation has warnings. Review the proposal or set "
                f"allow_warnings=true to approve explicitly: {suggestion.id}"
            ),
        )


def _get_suggestion_or_404(
    session: Session, profile: TerminologyProfile, suggestion_id: int
) -> GovernanceSuggestion:
    suggestion = session.scalar(
        select(GovernanceSuggestion).where(
            GovernanceSuggestion.id == suggestion_id,
            GovernanceSuggestion.profile_id == profile.id,
        )
    )
    if suggestion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Suggestion not found for profile {profile.name!r}: {suggestion_id}",
        )
    return suggestion


def _apply_suggestion_idempotently(
    session: Session, profile: TerminologyProfile, suggestion: GovernanceSuggestion
) -> str:
    """Apply a pending suggestion or mark it as an idempotent no-op."""

    if is_canonical_migration_suggestion(suggestion):
        try:
            apply_canonical_migration_suggestion(session, profile, suggestion)
        except CanonicalLifecycleError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        return "migrated_canonical"
    if suggestion.suggestion_type == "canonical_term":
        return _apply_canonical_term_suggestion_idempotently(
            session, profile, suggestion
        )
    if suggestion.suggestion_type == "alias":
        return _apply_alias_suggestion_idempotently(session, profile, suggestion)
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=f"Invalid suggestion type: {suggestion.suggestion_type}",
    )


def _apply_canonical_term_suggestion_idempotently(
    session: Session, profile: TerminologyProfile, suggestion: GovernanceSuggestion
) -> str:
    _ensure_not_stoplisted(
        session,
        profile,
        value=suggestion.canonical_value,
        target="canonical",
        entity_name="Canonical term suggestion",
    )
    existing_term = session.scalar(
        select(CanonicalTerm).where(
            CanonicalTerm.profile_id == profile.id,
            CanonicalTerm.normalized_value == suggestion.normalized_canonical,
        )
    )
    if existing_term is not None:
        if existing_term.slot != suggestion.slot:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Canonical term already exists with a different slot in "
                    f"profile {profile.name!r}: {suggestion.canonical_value}"
                ),
            )
        suggestion.term_id = existing_term.id
        return "idempotent_noop"

    term = CanonicalTerm(
        profile=profile,
        canonical_value=suggestion.canonical_value,
        slot=suggestion.slot,
        description=suggestion.description,
        status="active",
    )
    session.add(term)
    session.flush()
    suggestion.term_id = term.id
    return "created_term"


def _apply_alias_suggestion_idempotently(
    session: Session, profile: TerminologyProfile, suggestion: GovernanceSuggestion
) -> str:
    if suggestion.alias_value is None or suggestion.normalized_alias is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Alias suggestion is missing alias_value.",
        )

    _ensure_not_stoplisted(
        session,
        profile,
        value=suggestion.alias_value,
        target="alias",
        entity_name="Alias suggestion",
    )

    try:
        term = get_term(session, profile, suggestion.canonical_value)
    except GovernanceCliError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    existing_alias = session.scalar(
        select(TermAlias).where(
            TermAlias.profile_id == profile.id,
            TermAlias.normalized_alias == suggestion.normalized_alias,
        )
    )
    if existing_alias is not None:
        existing_term = existing_alias.term
        existing_normalized = (
            existing_term.normalized_value if existing_term is not None else None
        )
        if existing_normalized != suggestion.normalized_canonical:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Alias already exists in profile {profile.name!r}: "
                    f"{suggestion.alias_value}"
                ),
            )
        suggestion.term_id = term.id
        suggestion.alias_id = existing_alias.id
        return "idempotent_noop"

    alias = TermAlias(
        profile=profile,
        term=term,
        alias_value=suggestion.alias_value,
        confidence=suggestion.confidence,
        status="active",
        notes=suggestion.context,
    )
    session.add(alias)
    session.flush()
    suggestion.term_id = term.id
    suggestion.alias_id = alias.id
    return "created_alias"


def _approve_canonical_migration_suggestion(
    session: Session, profile: TerminologyProfile, suggestion: GovernanceSuggestion
) -> None:
    try:
        apply_canonical_migration_suggestion(session, profile, suggestion)
    except CanonicalLifecycleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


def _approve_alias_suggestion(
    session: Session, profile: TerminologyProfile, suggestion: GovernanceSuggestion
) -> None:
    if suggestion.alias_value is None or suggestion.normalized_alias is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Alias suggestion is missing alias_value.",
        )

    _ensure_not_stoplisted(
        session,
        profile,
        value=suggestion.alias_value,
        target="alias",
        entity_name="Alias suggestion",
    )

    try:
        term = get_term(session, profile, suggestion.canonical_value)
    except GovernanceCliError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    existing_alias = session.scalar(
        select(TermAlias).where(
            TermAlias.profile_id == profile.id,
            TermAlias.normalized_alias == suggestion.normalized_alias,
        )
    )
    if existing_alias is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Alias already exists in profile {profile.name!r}: {suggestion.alias_value}",
        )

    alias = TermAlias(
        profile=profile,
        term=term,
        alias_value=suggestion.alias_value,
        confidence=suggestion.confidence,
        status="active",
        notes=suggestion.context,
    )
    session.add(alias)
    session.flush()
    suggestion.alias_id = alias.id


def _approve_canonical_term_suggestion(
    session: Session, profile: TerminologyProfile, suggestion: GovernanceSuggestion
) -> None:
    _ensure_not_stoplisted(
        session,
        profile,
        value=suggestion.canonical_value,
        target="canonical",
        entity_name="Canonical term suggestion",
    )

    existing_term = session.scalar(
        select(CanonicalTerm).where(
            CanonicalTerm.profile_id == profile.id,
            CanonicalTerm.normalized_value == suggestion.normalized_canonical,
        )
    )
    if existing_term is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Canonical term already exists in profile {profile.name!r}: "
                f"{suggestion.canonical_value}"
            ),
        )

    term = CanonicalTerm(
        profile=profile,
        canonical_value=suggestion.canonical_value,
        slot=suggestion.slot,
        description=suggestion.description,
        status="active",
    )
    session.add(term)
    session.flush()
    suggestion.term_id = term.id


def _ensure_pending_suggestion(suggestion: GovernanceSuggestion) -> None:
    if suggestion.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Suggestion is not pending: {suggestion.status}",
        )


def _get_ambiguous_alias_or_404(
    session: Session,
    profile: TerminologyProfile,
    surface_value: str,
) -> GovernanceAmbiguousAlias:
    ambiguous_alias = session.scalar(
        select(GovernanceAmbiguousAlias).where(
            GovernanceAmbiguousAlias.profile_id == profile.id,
            GovernanceAmbiguousAlias.normalized_surface
            == normalize_value(surface_value),
        )
    )
    if ambiguous_alias is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Ambiguous alias not found for profile {profile.name!r}: "
                f"{surface_value}"
            ),
        )
    return ambiguous_alias


def _upsert_ambiguous_alias_candidates(
    session: Session,
    *,
    profile: TerminologyProfile,
    ambiguous_alias: GovernanceAmbiguousAlias,
    candidates: list,
) -> None:
    existing_by_key = {
        (candidate.normalized_canonical, candidate.slot): candidate
        for candidate in list(ambiguous_alias.candidates)
    }
    next_candidates: list[GovernanceAmbiguousAliasCandidate] = []
    for candidate_input in candidates:
        _validate_ambiguous_alias_candidate_status(candidate_input.status)
        _validate_ambiguous_alias_candidate_source(candidate_input.source)
        normalized_canonical = normalize_value(candidate_input.canonical_value)
        slot = candidate_input.slot.strip().upper()
        term = _resolve_candidate_term(
            session,
            profile=profile,
            term_id=candidate_input.term_id,
            normalized_canonical=normalized_canonical,
            slot=slot,
        )
        key = (normalized_canonical, slot)
        candidate = existing_by_key.get(key)
        if candidate is None:
            candidate = GovernanceAmbiguousAliasCandidate(
                ambiguous_alias=ambiguous_alias,
                canonical_value=candidate_input.canonical_value,
                normalized_canonical=normalized_canonical,
                slot=slot,
            )
            session.add(candidate)
        candidate.term = term
        candidate.canonical_value = candidate_input.canonical_value
        candidate.source = candidate_input.source
        candidate.confidence = candidate_input.confidence
        candidate.status = candidate_input.status
        candidate.evidence_json = candidate_input.evidence
        next_candidates.append(candidate)

    if candidates:
        ambiguous_alias.candidates = next_candidates
        session.flush()


def _resolve_candidate_term(
    session: Session,
    *,
    profile: TerminologyProfile,
    term_id: int | None,
    normalized_canonical: str,
    slot: str,
) -> CanonicalTerm | None:
    if term_id is not None:
        term = session.scalar(
            select(CanonicalTerm).where(
                CanonicalTerm.id == term_id,
                CanonicalTerm.profile_id == profile.id,
            )
        )
        if term is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Canonical term not found for profile {profile.name!r}: {term_id}",
            )
        if term.normalized_value != normalized_canonical or term.slot != slot:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Candidate term_id does not match canonical_value/slot: "
                    f"{term_id}"
                ),
            )
        return term

    return session.scalar(
        select(CanonicalTerm).where(
            CanonicalTerm.profile_id == profile.id,
            CanonicalTerm.normalized_value == normalized_canonical,
            CanonicalTerm.slot == slot,
        )
    )


def _validate_ambiguous_alias_status(value: str) -> None:
    if value not in AMBIGUOUS_ALIAS_STATUSES:
        allowed_values = ", ".join(AMBIGUOUS_ALIAS_STATUSES)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Invalid ambiguous alias status: {value}. "
                f"Allowed values: {allowed_values}"
            ),
        )


def _validate_ambiguous_alias_candidate_status(value: str) -> None:
    if value not in AMBIGUOUS_ALIAS_CANDIDATE_STATUSES:
        allowed_values = ", ".join(AMBIGUOUS_ALIAS_CANDIDATE_STATUSES)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Invalid ambiguous alias candidate status: {value}. "
                f"Allowed values: {allowed_values}"
            ),
        )


def _validate_ambiguous_alias_candidate_source(value: str) -> None:
    if value not in AMBIGUOUS_ALIAS_CANDIDATE_SOURCES:
        allowed_values = ", ".join(AMBIGUOUS_ALIAS_CANDIDATE_SOURCES)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Invalid ambiguous alias candidate source: {value}. "
                f"Allowed values: {allowed_values}"
            ),
        )


def _validate_status(value: str, allowed: tuple[str, ...], entity_name: str) -> None:
    if value not in allowed:
        allowed_values = ", ".join(allowed)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid {entity_name} status: {value}. Allowed values: {allowed_values}",
        )


def _integrity_conflict(exc: IntegrityError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Database integrity error: {exc.orig}",
    )


def _profile_response(profile: TerminologyProfile) -> ProfileResponse:
    return ProfileResponse(
        id=profile.id,
        name=profile.name,
        normalized_name=profile.normalized_name,
        description=profile.description,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def _term_response(term: CanonicalTerm) -> TermResponse:
    return TermResponse(
        id=term.id,
        canonical_value=term.canonical_value,
        normalized_value=term.normalized_value,
        slot=term.slot,
        status=term.status,
        description=term.description,
        tags=[
            tag.value
            for tag in sorted(term.tags, key=lambda item: item.normalized_value)
        ],
        aliases=[_alias_response(alias) for alias in term.aliases],
        created_at=term.created_at,
        updated_at=term.updated_at,
    )


def _ambiguous_alias_response(
    ambiguous_alias: GovernanceAmbiguousAlias,
) -> AmbiguousAliasResponse:
    return AmbiguousAliasResponse(
        id=ambiguous_alias.id,
        profile_id=ambiguous_alias.profile_id,
        profile_name=ambiguous_alias.profile.name,
        surface_value=ambiguous_alias.surface_value,
        normalized_surface=ambiguous_alias.normalized_surface,
        status=ambiguous_alias.status,
        created_by=ambiguous_alias.created_by,
        reviewed_by=ambiguous_alias.reviewed_by,
        reviewed_at=ambiguous_alias.reviewed_at,
        review_note=ambiguous_alias.review_note,
        candidates=[
            _ambiguous_alias_candidate_response(candidate)
            for candidate in sorted(
                ambiguous_alias.candidates,
                key=lambda item: (
                    item.status != "preferred",
                    item.normalized_canonical,
                    item.slot,
                    item.id,
                ),
            )
        ],
        created_at=ambiguous_alias.created_at,
        updated_at=ambiguous_alias.updated_at,
    )


def _ambiguous_alias_candidate_response(
    candidate: GovernanceAmbiguousAliasCandidate,
) -> AmbiguousAliasCandidateResponse:
    return AmbiguousAliasCandidateResponse(
        id=candidate.id,
        ambiguous_alias_id=candidate.ambiguous_alias_id,
        term_id=candidate.term_id,
        canonical_value=candidate.canonical_value,
        normalized_canonical=candidate.normalized_canonical,
        slot=candidate.slot,
        source=candidate.source,
        confidence=candidate.confidence,
        status=candidate.status,
        evidence=candidate.evidence_json,
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
    )


def _canonical_migration_plan_response(
    source_payload: dict[str, object],
) -> CanonicalMigrationPlanResponse:
    return CanonicalMigrationPlanResponse(
        schema_version=str(source_payload.get("schema_version") or ""),
        action=str(source_payload.get("action") or ""),
        old_canonical_value=str(source_payload.get("old_canonical_value") or ""),
        new_canonical_value=str(source_payload.get("new_canonical_value") or ""),
        slot=str(source_payload.get("slot") or ""),
        old_term_id=int(source_payload.get("old_term_id") or 0),
        new_term_id=source_payload.get("new_term_id")
        if isinstance(source_payload.get("new_term_id"), int)
        else None,
        old_status=str(source_payload.get("old_status") or ""),
        new_status=source_payload.get("new_status")
        if isinstance(source_payload.get("new_status"), str)
        else None,
        aliases_to_preserve=list(source_payload.get("aliases_to_preserve") or []),
        alias_conflicts=list(source_payload.get("alias_conflicts") or []),
        evidence=dict(source_payload.get("evidence") or {}),
        is_blocked=bool(source_payload.get("alias_conflicts") or []),
    )


def _suggestion_response(suggestion: GovernanceSuggestion) -> SuggestionResponse:
    lifecycle_decision = classify_proposal_lifecycle(suggestion)
    apply_policy = apply_policy_for_suggestion(suggestion)
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
        lifecycle_status=lifecycle_decision.lifecycle_status,
        lifecycle_reason=lifecycle_decision.lifecycle_reason,
        validation_status=lifecycle_decision.validation_status,
        risk_level=str(apply_policy.get("risk_level") or "unknown"),
        apply_policy=ProposalApplyPolicyResponse(**apply_policy),
        can_approve=lifecycle_decision.can_approve,
        can_apply=lifecycle_decision.can_apply,
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


def _global_stop_list_response(
    entry: GovernanceGlobalStopListEntry,
) -> GlobalStopListEntryResponse:
    return GlobalStopListEntryResponse(
        id=entry.id,
        value=entry.value,
        normalized_value=entry.normalized_value,
        target=entry.target,
        reason=entry.reason,
        is_active=entry.is_active,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def _stop_list_response(entry: GovernanceStopListEntry) -> StopListEntryResponse:
    return StopListEntryResponse(
        id=entry.id,
        profile_id=entry.profile_id,
        value=entry.value,
        normalized_value=entry.normalized_value,
        target=entry.target,
        reason=entry.reason,
        is_active=entry.is_active,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def _elasticsearch_binding_response(
    binding: ElasticsearchBinding,
) -> ElasticsearchBindingResponse:
    return ElasticsearchBindingResponse(
        id=binding.id,
        profile_id=binding.profile_id,
        profile_name=binding.profile.name,
        name=binding.name,
        normalized_name=binding.normalized_name,
        description=binding.description,
        provider=binding.provider,
        index_name=binding.index_name,
        text_fields=list(binding.text_fields),
        target_field=binding.target_field,
        filter_field=binding.filter_field,
        filter_value=binding.filter_value,
        timestamp_field=binding.timestamp_field,
        time_window_days=binding.time_window_days,
        mode=binding.mode,
        write_strategy=binding.write_strategy,
        is_enabled=binding.is_enabled,
        last_successful_snapshot_version=binding.last_successful_snapshot_version,
        last_successful_snapshot_at=binding.last_successful_snapshot_at,
        last_successful_job_id=binding.last_successful_job_id,
        pending_snapshot_version=binding.pending_snapshot_version,
        snapshot_status=binding_snapshot_status(binding),
        created_at=binding.created_at,
        updated_at=binding.updated_at,
    )


def _normalize_context_triggers(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized_value = normalize_value(str(value))
        if normalized_value and normalized_value not in seen:
            normalized.append(normalized_value)
            seen.add(normalized_value)
    return normalized


def _alias_response(alias: TermAlias) -> AliasResponse:
    return AliasResponse(
        id=alias.id,
        alias_value=alias.alias_value,
        normalized_alias=alias.normalized_alias,
        status=alias.status,
        confidence=alias.confidence,
        notes=alias.notes,
        context_triggers=list(alias.context_triggers or []),
        created_at=alias.created_at,
        updated_at=alias.updated_at,
    )
